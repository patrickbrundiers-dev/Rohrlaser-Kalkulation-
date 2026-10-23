"""Prüft Schweißen als Zusatzarbeit nach Zeit und den Schalter Mindestauftragswert je Angebot (Patrick 23.10.2026):
- S1 Vorgaben: Stundensatz 'Schweißen' 75 €/h, Zusatzarbeit 'Schweißen' mit Abrechnung €/h
- S2 Rechnung: Sekunden je Teil ÷ 3600 × 75 €/h, Stundensatz je Position änderbar, Preisstand beim Hinzufügen
- S3 ohne Sekunden: Warnung in der Position, 0 €; Vorgabezeit der Stammdaten gilt, wenn gesetzt
- S4 Dialog Zusatzarbeiten und Formular der Verwaltung zeigen Sekunden und €/h
- S5 ältere Datei: Stundensatz und Zusatzarbeit werden einmalig ergänzt, eigene Zeile gleichen Namens bleibt
- M1 Mindestauftragswert je Angebot aus: kein Anheben; an (Vorgabe): Anheben wie bisher, Betrag aus Einstellungen

Aufruf: python tests/test_schweissen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.zusatz_dialog import ZusatzDialog  # noqa: E402
from rohrlaser.zusatz_verwaltung import ZusatzFormular, rechenzeilen, vorgaben  # noqa: E402

EPS = 1e-6


def nah(a, b):
    return abs(a - b) < EPS


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)

# ------------------------------------------------------------------ S1 Vorgaben
saetze = {z["satz_id"]: z["satz"] for z in db.zeilen("stundensaetze")}
sw = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == "Schweißen")
assert saetze["Schweißen"] == 75
assert (sw["art"], sw["satz_id"], sw["zeit"], sw["aktiv"]) == ("€/h", "Schweißen", None, "ja")
pr = rechnen.zusatz_preis(sw, saetze)
assert pr["preis"] == 75 and pr["zeit_s"] == 0 and pr["arbeit"] == 0
ok("S1 Stundensatz Schweißen 75 €/h, Zusatzarbeit Schweißen (€/h, Sekunden je Position)")

# ------------------------------------------------------------------ S2 Rechnung
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.einstellung_setzen("mindestpreis", 0.0)
for pos, stueck in ((10, 10), (20, 4)):
    db.position_neu(a, dict(pos=pos, artikel=f"T{pos}", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                            laenge=1000, stueck=stueck, schneidweg=320, einstiche=2))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
stand = rechnen.zusatz_stand(sw, saetze, "2026-10-23")
assert stand["art"] == "€/h" and stand["preis"] == 75 and stand["zeit_s"] is None
p1, p2 = s.positionen
db.position_aendern(p1["id"], "zusatz", json.dumps([dict(name="Schweißen", menge=48, stand=stand)]))
db.position_aendern(p2["id"], "zusatz", json.dumps([dict(name="Schweißen", menge=120, preis=90, stand=stand)]))
s.neu_laden()
(w1,) = rechnen.zusatz_werte(s.positionen[0], s.k, s.tabellen)
(w2,) = rechnen.zusatz_werte(s.positionen[1], s.k, s.tabellen)
assert (w1["einheit"], w1["menge"], w1["preis"]) == ("s", 48, 75) and nah(w1["betrag"], 48 / 3600 * 75)    # 1,00 €
assert nah(w2["betrag"], 120 / 3600 * 90) and w2["zeit"] == 0                                          # 3,00 €
z, su = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
assert nah(z[0]["zusatz_teil"], 1.0) and nah(z[1]["zusatz_teil"], 3.0) and nah(su["zusatz"], 10 * 1 + 4 * 3)
assert z[0]["zusatz_text"] == "Schweißen 48 s"
assert not s.pos_modell.status[0].startswith("WARNUNG"), s.pos_modell.status[0]
ok("S2 48 s × 75 €/h = 1,00 € je Teil, 120 s × 90 €/h (je Position) = 3,00 €; nicht zur Laserzeit")

# Zeiten (Plan Preisaufbau Z1): Schweißen als Personalzeit 10 × 48 s + 4 × 120 s = 16 min, 22,00 €; Rest ohne Zeit
zs = {x["schritt"]: x for x in su["zeiten"]}
sz = zs["Zusatzarbeiten mit Zeit"]
assert sz["art"] == "Personal" and not sz["parallel"] and nah(sz["gesamt_min"], 16) and nah(sz["kosten"], 22)
assert nah(zs["Zusatzarbeiten (€)"]["kosten"], 0) and nah(sum(x["kosten"] for x in su["zeiten"]),
                                                       su["laser_schneiden"] + su["gewinde"] + su["ruesten_maschine"]
                                                       + su["ruesten_abmessungen"] + su["stangenwechsel_kosten"]
                                                       + su["arbeitsschritte"] + su["programmierung"] + su["zusatz"])
k = rechnen.zeit_summen(su["zeiten"], su["teile"])
assert nah(k["je_teil_min"], k["bearbeitung_min"] / 14) and k["personal_min"] >= 16 - 1e-9
s.uebersicht_bereich.offene_zeiten = {"Personal"}
s.uebersicht_bereich.zeiten_setzen(k)
text = s.uebersicht_bereich.zeiten.text()
assert "Zusatzarbeiten mit Zeit" in text and "Arbeitszeit gesamt" in text and "Durchlaufzeit" in text, text
assert "Programmierung (parallel)" in text and "▾ Personal" in text and "▸ Maschine" in text
assert "(Maschine + Personal, das nicht parallel läuft)" in rechnen.zeiten_text(k)
ok("S2 Zeiten: Schweißen 16 min Personalzeit (22,00 €), Übersicht aufklappbar nach Maschine und Personal")

# ------------------------------------------------------------------ S3 ohne Sekunden, Vorgabezeit
db.position_aendern(p1["id"], "zusatz", json.dumps([dict(name="Schweißen", stand=stand)]))
s.neu_laden()
(w1,) = rechnen.zusatz_werte(s.positionen[0], s.k, s.tabellen)
assert w1["menge"] is None and w1["betrag"] == 0
assert s.pos_modell.status[0] == "WARNUNG: Schweißen ohne Zeit (Sekunden je Teil unter Zusatzarbeiten …)", \
    s.pos_modell.status[0]
sw_vorgabe = dict(sw, zeit=30, zeit_einheit="s")
st30 = rechnen.zusatz_stand(sw_vorgabe, saetze)
assert st30["zeit_s"] == 30 and nah(rechnen.zusatz_preis(sw_vorgabe, saetze)["arbeit"], 30 / 3600 * 75)
db.position_aendern(p1["id"], "zusatz", json.dumps([dict(name="Schweißen", stand=st30)]))
s.neu_laden()
(w1,) = rechnen.zusatz_werte(s.positionen[0], s.k, s.tabellen)
assert w1["menge"] == 30 and nah(w1["betrag"], 0.625) and not s.pos_modell.status[0].startswith("WARNUNG")
ok("S3 ohne Sekunden: 0 € und WARNUNG; Vorgabezeit 30 s der Stammdaten gilt ohne Eingabe")

# ------------------------------------------------------------------ S4 Dialog und Verwaltung
dlg = ZusatzDialog(s, s.positionen[1], 1, s.k, s.tabellen)
r = dlg.zeile_neu()
dlg.tabelle.cellWidget(r, 0).setCurrentText("Schweißen")
assert dlg.tabelle.cellWidget(r, 1).text() == "€/h"
assert dlg.tabelle.cellWidget(r, 2).placeholderText() == "Sekunden je Teil eingeben"
assert dlg.tabelle.cellWidget(r, 3).placeholderText() == "Stammdaten: 75 €/h"
dlg.tabelle.cellWidget(r, 2).setText("45")
neu = json.loads(dlg.werte()[1])[-1]
assert neu["name"] == "Schweißen" and neu["menge"] == 45 and neu["stand"]["preis"] == 75
fo = ZusatzFormular(db)
fo.laden(sw, sw["id"], "Bearbeiten")
assert fo.zeit_einheit.currentText() == "s" and not fo.box3.isVisible()
assert fo.zeit_titel.text().startswith("Vorgabezeit je Teil")
zeilen = rechenzeilen(sw, saetze, vorgaben(db))
assert zeilen[0] == ("Stundensatz", "75,00 €/h", True), zeilen
fo.satz_id.setCurrentIndex(0)          # eigener Stundensatz ohne Wert: Fehler
fo.satz.setText("")
try:
    fo.werte()
    raise AssertionError("ohne Stundensatz gespeichert")
except ValueError as e:
    assert "Stundensatz" in str(e)
ok("S4 Dialog: Sekunden je Teil und 75 €/h als Vorgabe; Formular: Vorgabezeit in s, Stundensatz Pflicht")

# ------------------------------------------------------------------ M1 Mindestauftragswert ein/aus
db.einstellung_setzen("mindestpreis", 5000.0)
s.neu_laden()
an = s._rechnung()[1]
assert an["mindestpreis_gilt"] and nah(an["verkauf"], 5000)
assert s.kopf_bereich.mindest_an.isChecked() and "5.000,00 € netto" in s.kopf_bereich.mindest_an.text()
s.kopf_bereich.mindest_an.setChecked(False)              # speichert sofort
assert db.angebot(a)["mindestpreis_anwenden"] == "nein" and s.einst["mindestpreis"] == 0
aus = s._rechnung()[1]
assert not aus["mindestpreis_gilt"] and nah(aus["verkauf"], an["verkauf_kalkuliert"])
assert "ohne Mindestauftragswert" in s.kopf_bereich.kalk_kurz.text()
s.kopf_bereich.mindest_an.setChecked(True)
assert db.angebot(a)["mindestpreis_anwenden"] is None and nah(s._rechnung()[1]["verkauf"], 5000)
assert rechnen.einstellungen_angebot(dict(mindestpreis_anwenden="nein"), dict(mindestpreis=200))["mindestpreis"] == 0
ok("M1 Mindestauftragswert je Angebot aus: Verkaufspreis = kalkuliert; an (Vorgabe): angehoben auf 5.000 €")
db.schliessen()

# ------------------------------------------------------------------ S5 ältere Datei
alt = tmp / "alt" / "rohrlaser.db"
Datenbank(alt).schliessen()
con = sqlite3.connect(alt)
con.execute("DELETE FROM stundensaetze WHERE satz_id='Schweißen'")
con.execute("UPDATE zusatzarbeiten SET name='Schweißen alt' WHERE name='Schweißen'")
con.execute("UPDATE zusatzarbeiten SET name='Schweißen', art='€/Stück', preis=2 WHERE name='Entgraten'")
con.execute("DELETE FROM einstellungen WHERE name='schweissen_stand'")
con.execute("ALTER TABLE angebote DROP COLUMN mindestpreis_anwenden")
con.execute("PRAGMA user_version=44")
con.commit()
con.close()
d = Datenbank(alt)
assert d.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert {z["satz_id"]: z["satz"] for z in d.zeilen("stundensaetze")}["Schweißen"] == 75
eigene = [z for z in d.zeilen("zusatzarbeiten") if z["name"] == "Schweißen"]
assert len(eigene) == 1 and eigene[0]["art"] == "€/Stück" and eigene[0]["preis"] == 2      # eigene Zeile bleibt
assert "mindestpreis_anwenden" in {r[1] for r in d.con.execute("PRAGMA table_info(angebote)")}
d.schliessen()
ok("S5 Datei Schema 44: Stundensatz Schweißen ergänzt, eigene Zusatzarbeit gleichen Namens bleibt, Spalte ergänzt")
print("OK: Schweißen nach Zeit und Mindestauftragswert je Angebot")
