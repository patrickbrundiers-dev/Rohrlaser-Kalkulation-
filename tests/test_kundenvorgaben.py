"""Prüft die Kundenvorgaben (Plan „Arbeitsabläufe effizienter“ W2, Schritt AB3): eigene Tabelle je Kunde; neues
Angebot und Wählen des Kunden übernehmen Maschine, Stangenlänge, Gewinn, Lieferzeit, Material und Standard-Staffeln;
von Hand geänderte Kopfwerte bleiben; ohne Vorgabe gelten wieder die Einstellungen.

Aufruf: python tests/test_kundenvorgaben.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import kundenvorgabe  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import KALENDERWOCHE, KUNDENMATERIAL, TABELLE, VERWEISE, WOCHEN  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert SCHEMA_VERSION >= 51 and db.anzahl("kundenvorgaben") == 0
assert TABELLE["kundenvorgaben"].feld("kundennr").auswahl == "kunde"
assert ("kundenvorgaben", "kundennr") in VERWEISE[("kunden", "kundennr")]
ok("Tabelle Kundenvorgaben (leer), Kunde als Auswahl, Verweis beim Umbenennen der Kundennummer")

kunden = db.zeilen("kunden")
k1, k2 = kunden[0]["kundennr"], kunden[1]["kundennr"]
maschinen = sorted(z["maschinen_id"] for z in db.zeilen("maschinen"))
std_m = db.einstellung("standard_maschine")
andere = next(m for m in maschinen if m != std_m)
db.neu("kundenvorgaben", dict(kundennr=k1, maschine=andere, stange=12000, gewinn=22.5, lieferzeit_art=WOCHEN,
                              lieferzeit_wert="3", lieferzeit_zusatz="frei Haus", material_vorgabe=KUNDENMATERIAL,
                              staffeln="1; 3"))
assert kundenvorgabe.staffeln_text(db, k1) == "1; 3" and kundenvorgabe.staffeln_text(db, k2) == \
    db.einstellung("staffeln_standard")

# Neues Angebot für den Kunden: Vorgaben statt Einstellungen
a = db.angebot(db.angebot_neu(dict(kundennr=k1)))
assert (a["maschine"], a["stange"], a["gewinn"], a["material_vorgabe"]) == (andere, 12000, 22.5, KUNDENMATERIAL), a
assert (a["lieferzeit_art"], a["lieferzeit_wert"], a["lieferzeit_zusatz"]) == (WOCHEN, "3", "frei Haus")
b = db.angebot(db.angebot_neu(dict(kundennr=k2)))
assert (b["maschine"], b["stange"]) == (std_m, db.einstellung("standard_stange"))
ok("Neues Angebot: Vorgaben des Kunden, anderer Kunde ohne Vorgabe: Einstellungen")

# Kunde im Angebot wählen: Felder mit Einstellungswert werden ersetzt, von Hand geänderte bleiben
c = db.angebot_neu()
db.angebot_aendern(c, "stange", 7000)                  # von Hand
k = db.kunde_uebernehmen(c, k1)
a = db.angebot(c)
assert (a["maschine"], a["stange"], a["gewinn"], a["lieferzeit_wert"]) == (andere, 7000, 22.5, "3"), a
assert "Maschine" in k["vorgaben"] and "Lieferzeit" in k["vorgaben"] and "Stangenlänge" not in k["vorgaben"], k
ok("Kunde gewählt: Maschine, Gewinn, Lieferzeit übernommen; Stangenlänge von Hand bleibt")

# Wechsel auf einen Kunden ohne Vorgabe: Werte des alten Kunden gehen auf die Einstellungen zurück
db.angebot_aendern(c, "gewinn", 30)                    # von Hand
db.kunde_uebernehmen(c, k2)
a = db.angebot(c)
assert a["maschine"] == std_m and a["gewinn"] == 30 and a["stange"] == 7000 and a["material_vorgabe"] is None, a
assert a["lieferzeit_art"] == (db.einstellung("lieferzeit_art") or None), a["lieferzeit_art"]
ok("Wechsel auf Kunden ohne Vorgabe: Vorgaben zurück auf Einstellungen, eigene Werte bleiben")

# Lieferzeit, die nicht zur Art passt, wird nicht übernommen
db.aendern("kundenvorgaben", db.zeilen("kundenvorgaben")[0]["id"], "lieferzeit_art", KALENDERWOCHE)
db.aendern("kundenvorgaben", db.zeilen("kundenvorgaben")[0]["id"], "lieferzeit_wert", "60")
w = kundenvorgabe.kopfwerte(db, k1, "2026-10-24")
assert "lieferzeit_art" not in w and w["lieferzeit_zusatz"] == "frei Haus", w
db.aendern("kundenvorgaben", db.zeilen("kundenvorgaben")[0]["id"], "lieferzeit_wert", "50")
assert kundenvorgabe.kopfwerte(db, k1, "2026-10-24")["lieferzeit_wert"] == "50/2026"
ok("Lieferzeit der Vorgabe wird geprüft (KW ohne Jahr: Jahr des Angebots)")

# Oberfläche: Kunde wählen, Meldung, Standard-Staffeln mit den Faktoren des Kunden
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(db.angebot_neu())
s.kunde_waehlen(k1)
assert s.kopf["maschine"] == andere and s.kopf["gewinn"] == 22.5
assert "Kundenvorgaben" in fenster.statusBar().currentMessage(), fenster.statusBar().currentMessage()
db.position_neu(s.id, dict(pos=1, artikel="T1", profil_id=db.zeilen("profile")[0]["profil_id"],
                           werkstoff_id=db.zeilen("werkstoffe")[0]["werkstoff_id"], laenge=500, stueck=10))
s.neu_laden()
ids = s.st_seite.standard()
mengen = sorted(z["menge"] for z in db.staffeln(s.id))
assert len(ids) == 2 and mengen == [10, 30], mengen
db.aendern("kundenvorgaben", db.zeilen("kundenvorgaben")[0]["id"], "staffeln", "0")
assert kundenvorgabe.staffeln_text(db, k1) == "0"
ok("Oberfläche: Kunde gewählt, Statuszeile nennt Kundenvorgaben, Standard-Staffeln 1; 3 des Kunden, 0 = keine")

# Einstellungen: eigene Seite unter Kunden
unter = fenster.bereich.unter
seiten = [unter.tabText(i) for i in range(unter.count())]
assert "Kundenvorgaben" in seiten, seiten
ok("Einstellungen: Seite Kundenvorgaben")

print("Alle Prüfungen bestanden.")
