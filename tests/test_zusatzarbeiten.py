"""Prüft Zusatzarbeiten (Verzinken, Pulverbeschichten, Gravur extra …), Festpreis je Gewinde und die
manuelle Schneidzeit: Rechnung, Status, Angebotstext, Datenbank (Erweiterung alter Dateien) und
Oberfläche (Dialog, Positionstabelle).

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
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())


def nah(a, b, tol=1e-9):
    return abs(a - b) <= tol


db = Datenbank(tmp / "a" / "rohrlaser.db")
assert [z["name"] for z in db.zeilen("zusatzarbeiten")] == ["Feuerverzinken", "Galvanisch verzinken", "Pulverbeschichten",
                                                             "Entgraten", "Gravur extra", "Senken", "Flowdrill",
                                                             "Bohren"]
a = db.angebot_neu(dict(kunde="Test", skonto=0))
p1 = db.position_neu(a, dict(pos=10, artikel="A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                             stueck=10, schneidweg=300, einstiche=2))
p2 = db.position_neu(a, dict(pos=20, artikel="B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500,
                             stueck=4, schneidweg=200, einstiche=2))
k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
satz_h = k.maschinen["T11"]["stundensatz"]
zf, zfl, gew = einst["zuschlag_fertigung"], einst["zuschlag_fremdleistung"], einst["gewinn"]


def rechnung():
    kopf, pos = db.angebot(a), db.positionen(a)
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
kopf = db.angebot(a)
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

# 6) Gewinde nur mit Preis je Stück (Beispiel M6 0,90 €); ohne Preis 0 € und Warnung, Zeit zählt nicht
db.position_aendern(p1, "gewinde", "4xM6; 2xM8")
pos, (z, s) = rechnung()
assert nah(z[0]["gewinde_preis"], 4 * 0.90 + 2 * 1.10) and z[0]["gewindezeit"] == 0
assert nah(z[0]["laser_teil"] - basis[0]["laser_teil"], 5.8)
g6 = next(g for g in db.zeilen("gewinde") if g["gewinde"] == "M6")
db.aendern("gewinde", g6["id"], "preis", None)
db.aendern("gewinde", g6["id"], "zeit", 12)
tab = db.tabellen()
pos, (z, s) = rechnung()
assert nah(z[0]["gewinde_preis"], 2.2) and z[0]["gewindezeit"] == 0
assert rechnen.status(pos[0], rechnen.position_werte(pos[0], kopf, k, tab), kopf, k) == \
    "WARNUNG: Gewinde M6 ohne Preis je Stück (Einstellungen › Gewinde)"
assert z[0]["hinweis"] == "Gewinde M6 ohne Preis", z[0]["hinweis"]
t = ausgabe.angebotstext(pos[0], k)
assert "\ninkl. Gewinde 4xM6; 2xM8" in t and ", " not in t, t       # jede Angabe in einer eigenen Zeile

# 7) Unbekannte Zusatzarbeit: Warnung im Status, Hinweis in der Kalkulation, keine Kosten
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Vergolden")]))
pos, (z, s) = rechnung()
w = rechnen.position_werte(pos[0], kopf, k, tab)
assert rechnen.status(pos[0], w, kopf, k) == "WARNUNG: Zusatzarbeit 'Vergolden' unbekannt"
assert z[0]["hinweis"] == "Zusatzarbeit unbekannt" and z[0]["zusatz_teil"] == 0
db.position_aendern(p1, "zusatz", json.dumps([dict(name="Feuerverzinken")]))

# 8) Staffeln: jede Stufe ist ein eigenes Angebot, der Mindestbetrag gilt je Stufe
pos = db.positionen(a)
st1 = staffeln.stufe_rechnen(db.angebot(a), pos, "10", 1, k, tab, einst)
st100 = staffeln.stufe_rechnen(db.angebot(a), pos, "10", 100, k, tab, einst)
assert st1["preis_einheit"] > st100["preis_einheit"]

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
assert d.anzahl("zusatzarbeiten") == 8 and d.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
d.schliessen()

# 11) Datei vor 0.8.12 ohne Senken/Flowdrill/Bohren: werden einmalig ergänzt, eigene Zeile gleichen Namens bleibt;
#     Stand 0.8.12 (Bohren als Zeit × Stundensatz) wird Festpreis, Gewinde ohne Preis bekommen einen Preis je Stück
con = sqlite3.connect(alt)
con.execute("DELETE FROM zusatzarbeiten WHERE name IN ('Flowdrill')")
con.execute("UPDATE zusatzarbeiten SET preis=NULL, zeit=0.5, zeit_einheit='min', satz_id='Nachbearbeitung' "
            "WHERE name='Bohren'")
con.execute("UPDATE gewinde SET preis=NULL, zeit=36 WHERE gewinde='M6'")
con.execute("UPDATE zusatzarbeiten SET preis=1.25, zeit=NULL WHERE name='Senken'")
con.execute("DELETE FROM stundensaetze WHERE satz_id='Nachbearbeitung'")
con.execute("DELETE FROM einstellungen WHERE name='bohr_zusatz_stand'")
con.commit()
con.close()
d = Datenbank(alt)
zs = {z["name"]: z for z in d.zeilen("zusatzarbeiten")}
assert {"Senken", "Flowdrill", "Bohren"} <= set(zs) and zs["Senken"]["preis"] == 1.25, zs
assert zs["Bohren"]["satz_id"] is None and zs["Bohren"]["zeit"] is None and zs["Bohren"]["preis"] == 0.40
assert zs["Flowdrill"]["preis"] == 0.60 and zs["Flowdrill"]["art"] == "€/Stück" and zs["Flowdrill"]["zeit"] is None
m6 = next(g for g in d.zeilen("gewinde") if g["gewinde"] == "M6")
satz = d.con.execute("SELECT stundensatz FROM maschinen ORDER BY rowid").fetchone()[0]
assert nah(m6["preis"], round(36 / 3600 * satz, 2)), (m6, satz)
d.schliessen()

# 11) Oberfläche: Dialog liefert Gewinde und Zusatzarbeiten, Übernahme für mehrere Positionen, Tabellenspalte
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.zusatz_dialog import ZusatzDialog  # noqa: E402
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "a" / "rohrlaser.db")
fenster = Hauptfenster(db, stumm=True)
seite = fenster.angebot_oeffnen(a)
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
liste = json.loads(werte[1])
staende = [e.pop("stand") for e in liste]      # Preisstand der Stammdaten beim Hinzufügen
assert werte[0] == "2xM8" and liste == [
    dict(name="Pulverbeschichten", menge=None, preis=None, text="RAL 9005"),
    dict(name="Gravur extra", menge=None, preis=12.5, text=None)]
assert [(s["art"], s["preis"]) for s in staende] == [("€/m²", 18.0), ("s/Stück", 20.0)]
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
berechnet = m.zeiten[0]
assert berechnet and m.data(m.index(0, c)) == m.data(m.index(0, c), Qt.EditRole) != ""   # grau: berechnete Zeit
m.setData(m.index(0, c), m.data(m.index(0, c), Qt.EditRole))
assert seite.positionen[0]["zeit_manuell"] is None          # unverändert bestätigt = bleibt berechnet
assert m.setData(m.index(0, c), "45")
assert seite.positionen[0]["zeit_manuell"] == 45 and m.status[0] == "HINWEIS: Schneidzeit manuell"
assert "Zusatzarbeiten" in seite.uebersicht_bereich.einzeln.text()

# Kalkulationswerte je Angebot: Vorgabe aus den Einstellungen, im Angebot änderbar
vorg = db.kalkulation_vorgaben()
assert all(seite.kopf[n] == w for n, w in vorg.items()) and vorg["gewinn"] == round(db.einstellung("gewinn") * 100, 4)
e = rechnen.einstellungen_angebot(dict(gewinn=25.0, angebotsaufschlag=None), dict(gewinn=0.1, angebotsaufschlag=50))
assert e["gewinn"] == 0.25 and e["angebotsaufschlag"] == 50
seite.optimieren()
vorher = seite._rechnung()[1]["verkauf"]
db.angebot_aendern(seite.id, "gewinn", vorg["gewinn"] + 10)
seite.neu_laden()
assert abs(seite.einst["gewinn"] - (vorg["gewinn"] + 10) / 100) < 1e-12 and seite._rechnung()[1]["verkauf"] > vorher
assert db.einstellung("gewinn") * 100 == vorg["gewinn"]       # Einstellungen bleiben unverändert
assert seite.kalkulation_zuruecksetzen() and seite.kopf["gewinn"] == vorg["gewinn"]
assert abs(seite._rechnung()[1]["verkauf"] - vorher) < 1e-9
fenster.close()
db.schliessen()
print("OK: Zusatzarbeiten, Gewinde-Festpreis und manuelle Schneidzeit")
