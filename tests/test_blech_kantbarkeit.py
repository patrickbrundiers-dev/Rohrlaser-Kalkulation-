"""Kantbarkeit als Hinweis im Blech-Editor (Plan S4, Patrick 23.10.2026 „1a“):
- KB1 Kleinster Schenkel (Außenmaß) ≥ Faktor × V-Öffnung, V-Öffnung = Faktor × Dicke.
- KB2 Kleinster Innenradius = Faktor × Dicke.
- KB3 Abstand Innenkontur–Biegelinie ≥ Innenradius + Faktor × Dicke (Kantteil und mehrachsig gekantet).
- KB4 Mehrachsig gekantetes Rechteck mit sich kreuzenden Biegelinien: Freischnitt fehlt.
- KB5 Faktor 0 schaltet eine Regel aus; ohne Befund keine Hinweise; mit Befund der Satz „Biegefolge und
  Werkzeugkollision prüft das Programm nicht“; der Blech-Editor zeigt die Hinweise.

Aufruf: python tests/test_blech_kantbarkeit.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import blech, schneidweg as sw  # noqa: E402


def ok(t):
    print("OK    ", t)


def pruefen(e, **einst):
    return blech.kantbarkeit(e, blech.zuschnitt(e), einst)


winkel = dict(art=blech.KANTTEIL, dicke=2, kantlaenge=200, form=blech.RECHTECK,
              schenkel=[dict(laenge=50, winkel=90), dict(laenge=80)], konturen=[])
assert pruefen(winkel) == []

# KB1 Schenkel: V = 8 × 2 = 16 mm, kleinster Schenkel 0,7 × 16 = 11,2 mm
kurz = dict(winkel, schenkel=[dict(laenge=10, winkel=90), dict(laenge=80)])
h = pruefen(kurz)
assert h[0] == "Kantbarkeit: Schenkel 1 kürzer als 11,2 mm (V-Öffnung 16 mm)" and h[-1].endswith(blech.NICHT_GEPRUEFT)
assert pruefen(kurz, blech_kant_schenkel=0) == [] and pruefen(kurz, blech_kant_v=4) == []     # 0,7 × 8 = 5,6
ok("KB1 Kleinster Schenkel nach V-Öffnung (Faktor 0 = aus)")

# KB2 Innenradius 0,5 < 0,5 × 2 = 1 mm
spitz = dict(winkel, schenkel=[dict(laenge=50, winkel=90, radius=0.5), dict(laenge=80)])
assert "Innenradius unter 1 mm" in pruefen(spitz)[0]
assert pruefen(dict(winkel, schenkel=[dict(laenge=50, winkel=90, radius=1), dict(laenge=80)])) == []
ok("KB2 Kleinster Innenradius")

# KB3 Bohrung Ø 6 nah an der Biegelinie (Abstand Rand 2 mm < r 2 + 2 × 2 = 6 mm), weit weg ohne Befund
lage = blech.zuschnitt(winkel)["biegungen"][0][0]
nah = dict(winkel, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=6, x=100, y=lage + 5)])
weit = dict(winkel, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=6, x=100, y=lage + 10)])
ohne_lage = dict(winkel, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=6)])
assert "1 Innenkontur(en) näher als Innenradius + 2 × Dicke" in pruefen(nah)[0]
assert pruefen(weit) == [] and pruefen(ohne_lage) == [] and pruefen(nah, blech_kant_loch=0) == []
quer = dict(winkel, konturen=[dict(art=sw.LANGLOCH, anzahl=1, l=20, b=6, x=100, y=lage + 10, quer=True)])
assert pruefen(quer)[0].startswith("Kantbarkeit: 1 Innenkontur")          # quer: halbe Länge 10 zur Biegelinie
ok("KB3 Abstand Innenkontur–Biegelinie (Kantteil, Langloch quer)")

# KB3/KB4 mehrachsig: Schale 240 × 200 mit zwei sich kreuzenden Biegelinien
schale = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=2, laenge=240, breite=200, eckradius=0, kantungen=2,
              biegelinien=[dict(punkte=[[20, 0], [20, 200]], winkel=-90), dict(punkte=[[0, 20], [240, 20]],
                                                                               winkel=-90)], konturen=[])
h = pruefen(schale)
assert h == ["Kantbarkeit: Biegelinien kreuzen sich, Außenkontur ohne Freischnitt an den Biegeecken",
             f"Kantbarkeit: {blech.NICHT_GEPRUEFT}"], h
frei = dict(schale, form=blech.POLYGON, punkte="20,0; 240,0; 240,200; 0,200; 0,20; 20,20")
assert pruefen(frei) == []
loch = dict(frei, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=8, x=25, y=100)])
assert "1 Innenkontur(en) näher" in pruefen(loch)[0]
assert pruefen(dict(schale, biegelinien=schale["biegelinien"][:1], kantungen=1)) == []
# gemessener Innenradius aus dem STEP-Import: Abstand mit r = 8 statt Dicke, kleiner Radius als Hinweis
mitte = dict(frei, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=8, x=33, y=100)])      # Rand 9 mm von x = 20
assert pruefen(mitte) == []
gemessen = dict(mitte, biegelinien=[dict(b, radius=8) for b in frei["biegelinien"]])
assert "1 Innenkontur(en) näher" in pruefen(gemessen)[0]
assert "Innenradius unter 1 mm" in pruefen(dict(frei, biegelinien=[dict(frei["biegelinien"][0], radius=0.4)]))[0]
st = blech.aus_step(dict(dicke=2, laenge=240, breite=200, kontur="gekantet", abwicklung=dict(
    laenge=240, breite=200, mehrachsig=True, kantungen=1,
    biegelinien=[dict(punkte=[[20, 0], [20, 200]], winkel=-90, radius=8, ba=15)])), "S235JR")
assert st["biegelinien"][0]["radius"] == 8, st
assert pruefen(dict(winkel, art=blech.ZUSCHNITT, laenge=100, breite=50)) == []          # flaches Blech
ok("KB4 Mehrachsig: Freischnitt an Biegeecken, Abstand zu schrägen Biegelinien")

# KB5 Richtpreis und Blech-Editor
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
werkstoffe = {z["blech_werkstoff_id"]: z for z in db.zeilen("blech_werkstoffe")}
erg = blech.rechnen(dict(kurz, werkstoff="S235JR"), werkstoffe, db.zeilen("blechlaser"), db.blech_einstellungen())
assert not erg["fehler"] and erg["richtpreis"] and erg["hinweise"][0].startswith("Kantbarkeit: Schenkel 1")
erg = blech.rechnen(dict(kurz, werkstoff="S235JR"), werkstoffe, db.zeilen("blechlaser"),
                    dict(db.blech_einstellungen(), blech_kant_schenkel=0.0))
assert erg["hinweise"] == []
d = BlechDialog(None, db, dict(kurz, werkstoff="S235JR"))
assert "Kantbarkeit: Schenkel 1 kürzer" in d.summe.text() and blech.NICHT_GEPRUEFT in d.summe.text()
db.schliessen()
ok("KB5 Hinweise im Richtpreis und im Blech-Editor, Regeln abschaltbar")
