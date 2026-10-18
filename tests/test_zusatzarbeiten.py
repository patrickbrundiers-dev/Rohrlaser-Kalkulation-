"""Prüft Zusatzarbeiten (Verzinken, Pulverbeschichten, Gravur extra …), Festpreis je Gewinde und die
manuelle Schneidzeit: Rechnung, Status, Angebotstext, Datenbank (Erweiterung alter Dateien, Übernahme aus
der Mappe) und Oberfläche (Dialog, Positionstabelle).

Aufruf: python tests/test_zusatzarbeiten.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import ausgabe, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

MAPPE = HIER.parent / "mappe" / "Rohrlaser_Kalkulation_v02.xlsm"
tmp = Path(tempfile.mkdtemp())


def nah(a, b, tol=1e-9):
    return abs(a - b) <= tol


db = Datenbank(tmp / "a" / "rohrlaser.db")
assert [z["name"] for z in db.zeilen("zusatzarbeiten")] == ["Feuerverzinken", "Galvanisch verzinken", "Pulverbeschichten",
                                                             "Entgraten", "Gravur extra"]
a = db.auftrag_neu(dict(kunde="Test"))
p1 = db.position_neu(a, dict(pos=10, artikel="A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                             stueck=10, schneidweg=300, einstiche=2))
p2 = db.position_neu(a, dict(pos=20, artikel="B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500,
                             stueck=4, schneidweg=200, einstiche=2))
k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
satz_h = k.maschinen["RL-1"]["stundensatz"]
zf, zfl, gew = einst["zuschlag_fertigung"], einst["zuschlag_fremdleistung"], einst["gewinn"]


def rechnung():
    kopf, pos = db.auftrag(a), db.positionen(a)
    erg = rechnen.optimieren(kopf, pos, k)
    return pos, rechnen.kalkulation(kopf, pos, erg, k, tab, einst)


pos, (basis, s0) = rechnung()
assert all(z["zusatz_teil"] == 0 and z["zeit_extra"] == 0 and z["gewinde_preis"] == 0 for z in basis)
assert s0["zusatz"] == 0

# 1) Feuerverzinken (€/kg, Mindestbetrag 120 €): Menge automatisch = Teilegewicht, Summe unter Mindestbetrag
kg = rechnen.kg_je_m("RR 42,4x2,0", "S235-10219", k)
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Feuerverzinken")]))
pos, (z, s) = rechnung()
assert nah(z[0]["zusatzarbeiten"][0]["menge"], kg) and 10 * kg * 0.65 < 120
assert nah(z[0]["zusatz_teil"], 12.0), z[0]["zusatz_teil"]            # 120 € auf 10 Teile angehoben
assert nah(z[0]["herstell_teil"] - basis[0]["herstell_teil"], 12.0 * (1 + zfl))
assert nah(z[0]["preis_teil"] - basis[0]["preis_teil"], 12.0 * (1 + zfl) * (1 + gew))
assert nah(s["zusatz"], 120.0) and z[1]["zusatz_teil"] == 0
assert "feuerverzinkt" in ausgabe.angebotstext(pos[0], k, ",", z[0]["zusatzarbeiten"])

# 2) Über dem Mindestbetrag zählt die Menge × Preis; eigener Preis und Menge, Text im Angebot
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Pulverbeschichten", menge=0.5, preis=20, text="RAL 7016")]))
pos, (z, s) = rechnung()
assert nah(z[0]["zusatz_teil"], 10.0)                                  # 10 × 0,5 m² × 20 € = 100 € > 90 €
assert "pulverbeschichtet RAL 7016" in ausgabe.angebotstext(pos[0], k, ",", z[0]["zusatzarbeiten"])
assert rechnen.zusatz_text(pos[0]) == "Pulverbeschichten RAL 7016"
# Außenfläche automatisch: Umfang × Länge
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Pulverbeschichten")]))
pos, (z, s) = rechnung()
assert nah(z[0]["zusatzarbeiten"][0]["menge"], 3.141592653589793 * 42.4 * 1000 / 1e6)

# 3) Eigene Leistung (Fremdleistung = nein) mit Zuschlag Fertigung, gemeinsamer Mindestbetrag über Positionen
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Entgraten")]))
db.position_aendern(p2, "zusatz", json.dumps([dict(name="Entgraten"), dict(name="Feuerverzinken")]))
pos, (z, s) = rechnung()
assert nah(z[0]["herstell_teil"] - basis[0]["herstell_teil"], 0.5 * (1 + zf))
kg2 = rechnen.kg_je_m("QR 40x40x3", "S235-10219", k) * 0.5
assert nah(z[1]["zusatz_teil"], 0.5 + 120 / 4) and kg2 * 0.65 * 4 < 120

# 4) Gravur extra (s/Stück): Zeit kommt zur Schneidzeit, Kosten über den Stundensatz
db.position_aendern(p2, "zusatz", None)
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Gravur extra", menge=2)]))
pos, (z, s) = rechnung()
assert z[0]["zeit_extra"] == 40 and nah(z[0]["laser_netto"], basis[0]["laser_netto"] + 40)
assert nah(z[0]["laser_teil"] - basis[0]["laser_teil"], 40 / 3600 * satz_h) and z[0]["zusatz_teil"] == 0
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Gravur extra", menge=1, preis=7.5)]))
pos, (z, s) = rechnung()
assert z[0]["zeit_extra"] == 7.5

# 5) Schneidzeit manuell ersetzt die berechnete Zeit (ohne Abzug), Gravur extra kommt dazu; Status-Hinweis
db.position_aendern(p1, "zeit_manuell", 30.0)
pos, (z, s) = rechnung()
assert z[0]["laser_netto"] == 37.5 and z[0]["zeit_manuell"] == "ja" and z[0]["laser_brutto"] == basis[0]["laser_brutto"]
assert nah(z[0]["laser_teil"], 37.5 / 3600 * satz_h)
kopf = db.auftrag(a)
st = rechnen.status(pos[0], rechnen.position_werte(pos[0], kopf, k, tab), kopf, k)
assert st == "HINWEIS: Schneidzeit manuell", st
db.position_aendern(p1, "schneidweg", None)                           # ohne Schneidweg trotzdem kein Hinweis darauf
pos = db.positionen(a)
assert rechnen.status(pos[0], rechnen.position_werte(pos[0], kopf, k, tab), kopf, k) == "HINWEIS: Schneidzeit manuell"
pos, (z, s) = rechnung()
assert z[0]["laser_netto"] == 37.5 and z[0]["hinweis"] == ""
db.position_aendern(p1, "schneidweg", 300)
db.position_aendern(p1, "zeit_manuell", None)
db.position_aendern(p1, "zusatz", None)

# 6) Gewinde mit festem Preis (Beispiel M6 0,90 €) statt Zeit; ohne Preis wieder die Zeit
db.position_aendern(p1, "gewinde", "4xM6; 2xM8")
pos, (z, s) = rechnung()
assert nah(z[0]["gewinde_preis"], 4 * 0.90 + 2 * 1.10) and z[0]["gewindezeit"] == 0
assert nah(z[0]["laser_teil"] - basis[0]["laser_teil"], 5.8)
g6 = next(g for g in db.zeilen("gewinde") if g["gewinde"] == "M6")
db.aendern("gewinde", g6["id"], "preis", None)
db.aendern("gewinde", g6["id"], "zeit", 12)
tab = db.tabellen()
pos, (z, s) = rechnung()
assert nah(z[0]["gewinde_preis"], 2.2) and z[0]["gewindezeit"] == 48
assert "Gewinde 4xM6; 2xM8" in ausgabe.angebotstext(pos[0], k)

# 7) Unbekannte Zusatzarbeit: Warnung im Status, Hinweis in der Kalkulation, keine Kosten
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Vergolden")]))
pos, (z, s) = rechnung()
w = rechnen.position_werte(pos[0], kopf, k, tab)
assert rechnen.status(pos[0], w, kopf, k) == "WARNUNG: Zusatzarbeit 'Vergolden' unbekannt"
assert z[0]["hinweis"] == "Zusatzarbeit unbekannt" and z[0]["zusatz_teil"] == 0
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Feuerverzinken")]))

# 8) Staffeln: jede Stufe ist ein eigener Auftrag, der Mindestbetrag gilt je Stufe
pos = db.positionen(a)
st1 = staffeln.stufe_rechnen(db.auftrag(a), pos, "10", 1, k, tab, einst)
st100 = staffeln.stufe_rechnen(db.auftrag(a), pos, "10", 100, k, tab, einst)
assert st1["preis_einheit"] > st100["preis_einheit"]

# 9) Übernahme aus der Mappe behält Preis je Gewinde und die Zusatzarbeiten
from rohrlaser.mappe_import import lies_mappe  # noqa: E402
g8 = next(g for g in db.zeilen("gewinde") if g["gewinde"] == "M8")["preis"]
daten, e, _ = lies_mappe(MAPPE)
db.stammdaten_ersetzen(daten, e, "Mappe")
assert next(g for g in db.zeilen("gewinde") if g["gewinde"] == "M8")["preis"] == g8 == 1.10
assert db.anzahl("zusatzarbeiten") == 5
db.schliessen()

# 10) Datei einer älteren Programmversion (Schema 4) wird erweitert und bekommt die Beispiel-Zusatzarbeiten
alt = tmp / "alt" / "rohrlaser.db"
d = Datenbank(alt)
d.schliessen()
con = sqlite3.connect(alt)
con.execute("DROP TABLE zusatzarbeiten")
con.execute("PRAGMA user_version=4")
con.commit()
con.close()
d = Datenbank(alt)
assert d.anzahl("zusatzarbeiten") == 5 and d.con.execute("PRAGMA user_version").fetchone()[0] == 5
d.schliessen()

# 11) Oberfläche: Dialog liefert Gewinde und Zusatzarbeiten, Übernahme für mehrere Positionen, Tabellenspalte
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.zusatz_dialog import ZusatzDialog  # noqa: E402
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "a" / "rohrlaser.db")
fenster = Hauptfenster(db, stumm=True)
seite = fenster.auftrag_oeffnen(a)
dlg = ZusatzDialog(seite, seite.positionen[1], 2, seite.k, seite.tabellen)
dlg.gewinde.setText("2xM8")
r = dlg.zeile_neu()
dlg.tabelle.cellWidget(r, 0).setCurrentText("Pulverbeschichten")
assert dlg.tabelle.cellWidget(r, 1).text() == "€/m²" and "auto:" in dlg.tabelle.cellWidget(r, 2).placeholderText()
dlg.tabelle.cellWidget(r, 4).setText("RAL 9005")
r = dlg.zeile_neu()
dlg.tabelle.cellWidget(r, 0).setCurrentText("Gravur extra")
dlg.tabelle.cellWidget(r, 3).setText("12,5")
werte = dlg.werte()
assert werte[0] == "2xM8" and json.loads(werte[1]) == [
    dict(name="Pulverbeschichten", menge=None, preis=None, text="RAL 9005"),
    dict(name="Gravur extra", menge=None, preis=12.5, text=None)]
dlg.tabelle.cellWidget(r, 2).setText("abc")
try:
    dlg.werte()
    raise AssertionError("falsche Menge nicht abgewiesen")
except ValueError:
    pass
assert seite.zusatzarbeiten([0, 1], werte)
assert all(p["gewinde"] == "2xM8" and json.loads(p["zusatz"])[0]["name"] == "Pulverbeschichten" for p in seite.positionen)
m = seite.pos_modell
c = next(i for i, (art, _) in enumerate(m.spalten) if art == "zusatz")
assert m.data(m.index(0, c)) == "Pulverbeschichten RAL 9005; Gravur extra"
c = next(i for i, (art, f) in enumerate(m.spalten) if art == "feld" and f.name == "zeit_manuell")
assert m.setData(m.index(0, c), "45")
assert seite.positionen[0]["zeit_manuell"] == 45 and m.status[0] == "HINWEIS: Schneidzeit manuell"
assert "Zusatzarbeiten" in seite.uebersicht.text()
fenster.close()
db.schliessen()
print("OK: Zusatzarbeiten, Gewinde-Festpreis und manuelle Schneidzeit")
