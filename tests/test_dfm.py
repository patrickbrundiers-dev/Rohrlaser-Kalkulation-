"""Fertigungsprüfung (DFM) für Rohr und Blech (Plan S5, Abschnitt 5.6): je Regel ein Teil mit und ohne Verstoß.
- P1 Bohrung zu klein (Rohr und Blech), Bohrungen ohne Lage zählen mit.
- P2 Steg zu schmal: Muster längs, über eine Kante des Quadratrohrs (Abwicklung), Blech.
- P3 Kontur zu nah am Rand: Ende des Rohrs (Schlitz zählt nicht), Blechkante und Polygon-Außenkontur.
- P4 Teil zu kurz für die Maschine (Maschinen 'Kürzestes Teil', leer = keine Grenze).
- P5 Gravur über Kante (Umriss über mehrere Flächen aus dem STEP-Import).
- P6 Kantbarkeit als Befund der Blech-Position.
- P7 Regeltabelle: abschalten, Grenzwert, Stufe; Datendatei mit Vorgaben (ältere Datei Schema 47 bekommt sie);
  Status der Position (FEHLER vor anderen Prüfungen, WARNUNG, HINWEIS), Blech-Position, Schneidweg-Rechner und
  Blech-Editor zeigen die Befunde.

Aufruf: python tests/test_dfm.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import blech, dfm, schneidweg as sw  # noqa: E402


def ok(t):
    print("OK    ", t)


QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")


def rohr(konturen, laenge=500, maschine=None, zeilen=None, profil=QR):
    p = dict(laenge=laenge, technik=json.dumps(dict(quelle=sw.QUELLE, konturen=konturen)))
    return dfm.rohr(p, profil, maschine, zeilen)


def regeln_von(befunde):
    return [b.regel for b in befunde]


def bl(konturen, **e):
    e = dict(dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100, konturen=konturen), **e)
    return dfm.blech(e, blech.zuschnitt(e))


# ------------------------------------------------------------------ P1 Bohrung zu klein
b = rohr([dict(art=sw.BOHRUNG, anzahl=2, d=2.5, x=100, abstand=50, seite="oben")])
assert regeln_von(b) == [dfm.BOHRUNG_KLEIN] and b[0].stufe == dfm.WARNUNG
assert b[0].text.startswith("2 Bohrung(en) ab Ø 2,5 mm unter 1 × Wand (3 mm)") and "bei x = 100 mm, oben" in b[0].text
assert rohr([dict(art=sw.BOHRUNG, anzahl=2, d=3, x=100, abstand=50)]) == []
assert regeln_von(rohr([dict(art=sw.SENKUNG, anzahl=1, d=2, D=6)])) == [dfm.BOHRUNG_KLEIN]     # ohne Lage
assert rohr([dict(art=sw.BOHRUNG, anzahl=1, d=0.5, x=100)]) == []                                # Markierloch
assert rohr([dict(art=sw.FLOWDRILL, anzahl=1, d=2, x=100)]) == []
assert regeln_von(bl([dict(art=sw.BOHRUNG, anzahl=1, d=2, x=100, y=50)])) == [dfm.BOHRUNG_KLEIN]
assert bl([dict(art=sw.BOHRUNG, anzahl=1, d=3, x=100, y=50)]) == []
ok("P1 Bohrung zu klein (Rohr und Blech, auch ohne Lage; Markierloch und Flowdrill nicht)")

# ------------------------------------------------------------------ P2 Steg zu schmal
# Muster Ø 10 mit Abstand 14: Steg 4 mm < 1,5 × 3 = 4,5 mm; Abstand 15: Steg 5 mm
b = rohr([dict(art=sw.BOHRUNG, anzahl=3, d=10, x=100, abstand=14, seite="oben")])
assert regeln_von(b) == [dfm.STEG] and "schmalster 4 mm zwischen Kontur 1.1 und 1.2" in b[0].text, b
assert rohr([dict(art=sw.BOHRUNG, anzahl=3, d=10, x=100, abstand=15, seite="oben")]) == []
# über die Kante: zwei Bohrungen Ø 10 je 7 mm neben der Kante (Abwicklung, Steg 4 mm), gegenüberliegend nicht
kante = 20 - 5 - 2           # Mitte 13 mm von der Flächenmitte: Rand 2 mm vor der Kante oben/vorne
b = rohr([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben", q=kante),
          dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="vorne", q=-kante)])
c = rohr([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben", q=-kante),
          dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="vorne", q=kante)])
assert regeln_von(b) == [dfm.STEG] and "schmalster 4 mm zwischen Kontur 1 und 2" in b[0].text and c == [], (b, c)
assert regeln_von(bl([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=50, y=50),
                      dict(art=sw.LANGLOCH, anzahl=1, l=20, b=10, x=69, y=50)])) == [dfm.STEG]
assert bl([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=50, y=50), dict(art=sw.LANGLOCH, anzahl=1, l=20, b=10, x=70,
                                                                      y=50)]) == []
# gekreuzte schmale Rechtecke ohne Ecke im anderen: schneiden sich, Steg 0
assert dfm.abstand([(-50, -2), (50, -2), (50, 2), (-50, 2)], [(-2, -50), (2, -50), (2, 50), (-2, 50)]) == 0
assert regeln_von(bl([dict(art=sw.RECHTECK, anzahl=1, b=60, h=4, x=100, y=50),
                      dict(art=sw.RECHTECK, anzahl=1, b=4, h=60, x=100, y=50)])) == [dfm.STEG]
ok("P2 Steg zu schmal: Muster, über die Kante des Quadratrohrs, Blech")

# ------------------------------------------------------------------ P3 Kontur zu nah am Rand
b = rohr([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=7, seite="oben")])               # Rand 2 mm am Ende A
assert regeln_von(b) == [dfm.RAND] and "kleinster Abstand 2 mm" in b[0].text
assert regeln_von(rohr([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=494, seite="oben")])) == [dfm.RAND]   # Ende B
assert rohr([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=8, seite="oben")]) == []
assert rohr([dict(art=sw.SCHLITZ, anzahl=1, l=20, b=8, seite="oben")]) == []                         # offen
assert regeln_von(bl([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=7, y=50)])) == [dfm.RAND]
assert bl([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=8, y=50)]) == []
assert regeln_von(bl([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=50, y=-10)])) == [dfm.RAND]             # außerhalb
poly = dict(form=blech.POLYGON, punkte="100,100; 300,100; 300,200; 100,200")
assert regeln_von(bl([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=150, y=106)], **poly)) == [dfm.RAND]
assert bl([dict(art=sw.BOHRUNG, anzahl=1, d=10, x=150, y=150)], **poly) == []
ok("P3 Kontur zu nah am Rand: Enden des Rohrs (Schlitz offen), Blechkante und Polygon")

# ------------------------------------------------------------------ P4 Teil zu kurz
b = rohr([], laenge=40, maschine=dict(min_teil=50))
assert regeln_von(b) == [dfm.KURZ] and b[0].stufe == dfm.FEHLER and b[0].text == "40 mm, die Maschine nimmt Teile " \
                                                                                  "ab 50 mm"
assert rohr([], laenge=50, maschine=dict(min_teil=50)) == [] and rohr([], laenge=40, maschine=dict()) == []
assert dfm.rohr(dict(laenge=40), QR, dict(min_teil=50))[0].regel == dfm.KURZ                  # ohne technik
ok("P4 Teil zu kurz für die Maschine (leer = keine Grenze)")

# ------------------------------------------------------------------ P5 Gravur über Kante
umriss = [[-5, -3], [5, -3], [5, 3], [-5, 3]]
b = rohr([dict(art=sw.GRAVUR, anzahl=1, x=100, seite="oben", umriss=umriss, waende=["oben", "vorne"], tiefe=0.2)])
assert regeln_von(b) == [dfm.GRAVUR_KANTE]
assert rohr([dict(art=sw.GRAVUR, anzahl=1, x=100, seite="oben", umriss=umriss, waende=["oben"], tiefe=0.2)]) == []
# Gravur ist keine Schnittkontur: kein Steg, kein Rand
assert rohr([dict(art=sw.GRAVUR, anzahl=1, x=2, seite="oben", umriss=umriss, waende=["oben"], tiefe=0.2),
             dict(art=sw.BOHRUNG, anzahl=1, d=10, x=12, seite="oben")]) == []
ok("P5 Gravur über Kante; Gravuren zählen nicht bei Steg und Rand")

# ------------------------------------------------------------------ P6 Kantbarkeit
kant = dict(art=blech.KANTTEIL, dicke=2, kantlaenge=200, form=blech.RECHTECK,
            schenkel=[dict(laenge=10, winkel=90), dict(laenge=80)], konturen=[])
b = dfm.blech(kant, blech.zuschnitt(kant))
assert regeln_von(b) == [dfm.KANTBARKEIT] and b[0].stufe == dfm.HINWEIS and b[0].text.startswith("Schenkel 1")
assert dfm.blech(kant, blech.zuschnitt(kant), kantbarkeit=False) == []
assert dfm.blech(dict(kant, schenkel=[dict(laenge=50, winkel=90), dict(laenge=80)]),
                 blech.zuschnitt(dict(kant, schenkel=[dict(laenge=50, winkel=90), dict(laenge=80)]))) == []
assert regeln_von(dfm.blech_position(dict(technik=blech.speichern(kant)))) == [dfm.KANTBARKEIT]
# Einstellungen der Kantbarkeit gelten auch im Status (Faktor 0 = aus, wie im Blech-Editor)
assert dfm.blech_position(dict(technik=blech.speichern(kant)), einst=dict(blech_kant_schenkel=0.0)) == []
ok("P6 Kantbarkeit als Befund (Vorgabe HINWEIS)")

# ------------------------------------------------------------------ P7 Regeltabelle und Anzeige
steg = [dict(art=sw.BOHRUNG, anzahl=3, d=10, x=100, abstand=14, seite="oben")]
assert rohr(steg, zeilen=[dict(regel=dfm.STEG, aktiv="nein")]) == []
assert rohr(steg, zeilen=[dict(regel=dfm.STEG, aktiv="ja", grenzwert=1.0, stufe=dfm.WARNUNG)]) == []
assert rohr(steg, zeilen=[dict(regel=dfm.STEG, aktiv="ja", grenzwert=None, stufe=dfm.FEHLER)])[0].stufe == dfm.FEHLER
assert dfm.regeln([dict(regel="Unsinn", aktiv="nein")]) == dfm.regeln()
st = dfm.status(rohr(steg + [dict(art=sw.BOHRUNG, anzahl=1, d=2, x=300)], laenge=500))
assert st.startswith("WARNUNG: ") and st.endswith("(+1 weitere Prüfung)"), st
assert dfm.status([]) is None

from rohrlaser import rechnen, stammdaten  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
zeilen = db.zeilen("pruefregeln")
assert [z["regel"] for z in zeilen] == list(dfm.REGELN) and all(z["aktiv"] == "ja" for z in zeilen)
assert "Kürzestes Teil [mm]" in [f.titel for f in stammdaten.MASCHINEN.felder]
assert db.tabellen()["pruefregeln"] == zeilen
k = db.kontext()
kopf = dict(maschine="T11", stange=6000)
mid = next(z["id"] for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
p = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, schneidweg=800, einstiche=4,
         technik=json.dumps(dict(quelle=sw.QUELLE, konturen=steg)))


def status(p, kopf=kopf):
    return rechnen.status(p, rechnen.position_werte(p, kopf, k, db.tabellen()), kopf, k)


assert status(p).startswith("WARNUNG: Steg zu schmal"), status(p)
db.aendern("maschinen", mid, "min_teil", 600)
k = db.kontext()
assert status(p).startswith("FEHLER: Teil zu kurz für die Maschine: 500 mm"), status(p)
rid = next(z["id"] for z in db.zeilen("pruefregeln") if z["regel"] == dfm.KURZ)
db.aendern("pruefregeln", rid, "aktiv", "nein")
sid = next(z["id"] for z in db.zeilen("pruefregeln") if z["regel"] == dfm.STEG)
db.aendern("pruefregeln", sid, "stufe", dfm.HINWEIS)
assert status(p).startswith("HINWEIS: Steg zu schmal"), status(p)
db.aendern("pruefregeln", sid, "aktiv", "nein")
assert not status(p).startswith(("HINWEIS: Steg", "FEHLER: Teil zu kurz")), status(p)
ok("P7 Regeltabelle: abschalten, Grenzwert, Stufe; Status der Position nach Stufe")

# Blech-Position (Zukaufteil): Befund im Status
blech_p = dict(positionsart="Zukaufteil", technik=blech.speichern(dict(kant, quelle=blech.QUELLE)), stueck=10)
assert rechnen.zukaufteil_status(dict(blech_p, zukauf=None)).startswith("FEHLER: Zukaufartikel fehlt")
assert regeln_von(dfm.blech_position(blech_p, db.zeilen("pruefregeln"))) == [dfm.KANTBARKEIT]
w_b = rechnen.position_werte(blech_p, kopf, k, dict(db.tabellen(), einstellungen=dict(db.einstellungen(),
                                                                                       blech_kant_schenkel=0.0)))
assert w_b["einstellungen"]["blech_kant_schenkel"] == 0.0

# ältere Datei (Schema 47) bekommt die Tabelle mit den Vorgaben
db.schliessen()
alt = tmp / "alt.db"
shutil.copy(tmp / "rohrlaser.db", alt)
con = sqlite3.connect(alt)
con.execute("DROP TABLE pruefregeln")
con.execute("PRAGMA user_version = 47")
con.commit()
con.close()
db = Datenbank(alt)
assert db.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 48
assert len(db.zeilen("pruefregeln")) == len(dfm.REGELN)
ok("P7 Datendatei: Vorgaben in neuen und älteren Dateien (Schema 47)")

# Anzeige im Schneidweg-Rechner und im Blech-Editor
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
d = BlechDialog(None, db, dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100,
                               werkstoff=werkstoff, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=7, y=50)]))
assert "Prüfung WARNUNG: Kontur zu nah am Rand" in d.summe.text(), d.summe.text()
k = db.kontext()
p = dict(p, technik=json.dumps(dict(quelle=sw.QUELLE, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=7,
                                                                     seite="oben")])))
sd = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], kopf, k, db.tabellen(), db)
assert "Prüfung WARNUNG: Kontur zu nah am Rand" in sd.summe.text(), sd.summe.text()
db.schliessen()
ok("P7 Schneidweg-Rechner und Blech-Editor zeigen die Befunde")
