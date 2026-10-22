"""Prüft das 3D-Greifmaß in der Stangenoptimierung (Patrick 22.10.2026, Plan kalkulation/3d-schnitt, F4):
- G1 letztes Teil mit 3D-Bearbeitung an Ende B: 6.000 mm, Greiferrest 142, Greifmaß 300 -> nutzbar bis 5.700
- G2 dasselbe Teil ohne 3D: nutzbar bis 5.858 (wie bisher)
- G3 keine doppelte Berücksichtigung: Greiferrest 400 > Greifmaß 300 -> 400, nie 700
- G4 Reihenfolge: ein Teil ohne 3D kommt ans Ende, wenn es so passt; sonst zwei Stangen; nie eine unzulässige Stange
- G5 zufällige Gruppen mit und ohne 3D: unabhängige Prüfung (pruefe) und ohne 3D gleiche Ergebnisse wie vorher
- G6 12-m-Zuschnitt: Werkstück = Belegung + 3D-Greifmaß des letzten Teils
- G7 Angebot: Stangenbild-Daten (Greiferrest wirksam, 3D), FEHLER bei zu langem Teil, Prüfsumme ohne 3D unverändert

Aufruf: python tests/test_3d_greifmass.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import random
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import optimierung as opt  # noqa: E402
from rohrlaser.optimierung import Gruppe, Teil, anordnen, belegt, hinten, optimiere, passt, pruefe  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


def gruppe(teile, greif=142.0, stange=6000):
    g = Gruppe("QR 40x40x3", "S235", stange, 10, greif, 0.2, 5)
    g.teile = teile
    return g


def teil(nr, laenge, rest=0.0, zeile=13):
    return Teil(zeile, 10, "A", nr, laenge, True, True, 160, 160, rest=rest)


# ------------------------------------------------------------------ G1–G3
# Belegung eines Teils allein: 10 + L + 0,2
g = gruppe([teil(1, 5689.8, 300)])
assert passt(g, g.teile) and not passt(gruppe([teil(1, 5690, 300)]), [teil(1, 5690, 300)])
f = anordnen(g.teile, g)
assert hinten(g, f) == 300 and abs(belegt(g, f) + g.greiferrest - 6000) < EPS
ok("G1 letztes Teil mit 3D an Ende B: nutzbar bis 5.700 mm (Teil 5.689,8 passt, 5.690 nicht)")
g2 = gruppe([teil(1, 5847.8)])
assert passt(g2, g2.teile) and not passt(g2, [teil(1, 5848)]) and hinten(g2, anordnen(g2.teile, g2)) == 142
ok("G2 ohne 3D: nutzbar bis 5.858 mm wie bisher")
g3 = gruppe([teil(1, 5589.8, 300)], greif=400)
assert hinten(g3, anordnen(g3.teile, g3)) == 400 and passt(g3, g3.teile) and not passt(g3, [teil(1, 5590, 300)])
ok("G3 Greiferrest 400 > Greifmaß 300: es zählt 400, nicht 700 (keine doppelte Berücksichtigung)")

# ------------------------------------------------------------------ G4 Reihenfolge
a3, b2 = teil(1, 3000, 300, zeile=13), teil(1, 2700, 0, zeile=14)
g4 = gruppe([a3, b2])
f = anordnen(g4.teile, g4)
assert f[-1][0] is b2 and passt(g4, g4.teile), f        # 10 + 3000 + 0,2 + 2700 + 0,2 = 5710,4 ≤ 5858
st = optimiere(g4)
assert len(st) == 1 and st[0][-1][0] is b2
pruefe([g4], [st])
ok("G4 Teil ohne 3D ans Ende: 3.000 (3D) + 2.700 auf einer Stange")
a3b = teil(1, 2700, 300, zeile=14)
g5 = gruppe([a3, a3b])                                 # beide mit 3D: 5.710,4 + (300 − 142) > 5.858
assert not passt(g5, g5.teile) and len(optimiere(g5)) == 2
g5b = replace(g5, teile=[replace(a3, rest=0), replace(a3b, rest=0)])
assert passt(g5b, g5b.teile)
ok("G4 zwei Teile mit 3D: zwei Stangen (ohne 3D eine)")

# ------------------------------------------------------------------ G5 Zufall
rnd = random.Random(42)
for runde in range(40):
    teile = []
    for z in range(rnd.randint(1, 4)):
        laenge = rnd.choice((450, 800, 1250, 1999.5, 2400, 2950, 3800))
        rest = rnd.choice((0, 0, 300, 180, 120))
        teile += [teil(n, laenge, rest, zeile=13 + z) for n in range(1, rnd.randint(1, 9))]
    g = gruppe(teile)
    st = optimiere(g)
    pruefe([g], [st])
    for f in st:
        assert opt.verbrauch(g, f) + hinten(g, f) <= g.stange + EPS
    ohne = gruppe([replace(t, rest=0) for t in teile])
    assert len(optimiere(ohne)) <= len(st)
ok("G5 40 zufällige Gruppen mit 3D-Teilen: keine Stange überbelegt (inkl. 3D-Greifmaß), nie besser als ohne 3D")

# ------------------------------------------------------------------ G6 12-m-Zuschnitt
g6 = gruppe([teil(n, 2000, 300 if n == 1 else 0) for n in range(1, 4)])
assert opt.werkstueck_laenge(g6, [(teil(1, 2000, 300), 0)]) == 10 + 2000 + 0.2 + 300 - 0.2 + 1   # ceil(2310,2)
z = opt.zuschnitt(g6, 12000, 6500, 3)
opt.pruefe_zuschnitt(g6, z, 12000, 6500, 3)
ok("G6 12-m-Zuschnitt: Werkstück mit 3D-Teil am Ende um das Greifmaß länger, Prüfung bestanden")

# ------------------------------------------------------------------ G7 Angebot
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
mid = next(z["id"] for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
db.aendern("maschinen", mid, "d3", "ja")
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
t3d = json.dumps(dict(quelle="Schneidweg-Rechner", d3=True, a={}, b=dict(winkel=30, d3=True), konturen=[]))
db.position_neu(a, dict(pos=10, artikel="G3D", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=3000,
                        stueck=1, schneidweg=340, einstiche=2, a_schnitt=160, b_schnitt=180, a_gerade="ja",
                        b_gerade="nein", technik=t3d))
db.position_neu(a, dict(pos=20, artikel="G2D", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=2700,
                        stueck=1, schneidweg=320, einstiche=2, a_schnitt=160, b_schnitt=160))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
st = s.ergebnis["stangen"]
assert len(st) == 1 and st[0]["teile"][-1]["artikel"] == "G2D" and st[0]["greif"] == 142 and not st[0]["greif_3d"], st
ok("G7 Angebot: 3D-Teil vorn, Teil ohne 3D hinten, Greiferrest 142")
db.position_aendern(s.positionen[1]["id"], "technik", t3d)
db.position_aendern(s.positionen[1]["id"], "b_gerade", "nein")
s.neu_laden()
assert s.optimieren()
st = s.ergebnis["stangen"]
assert len(st) == 2 and all(x["greif"] == 300 and x["greif_3d"] for x in st), [(x["greif"], x["greif_3d"]) for x in st]
werte = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)
assert all(abs(w["rest"] - (x["stange"] - w["belegt"])) < EPS and w["rest"] >= 300 for w, x in zip(werte, st))
ok("G7 beide mit 3D: zwei Stangen, je 3D-Greifmaß 300 statt Greiferrest 142 (Stangenbild „3D“)")
db.position_aendern(s.positionen[0]["id"], "laenge", 5695)
s.neu_laden()
w0 = rechnen.position_werte(s.positionen[0], s.kopf, s.k, s.tabellen)
assert rechnen.status(s.positionen[0], w0, s.kopf, s.k) == "FEHLER: Teil zu lang für das 3D-Greifmaß der Maschine"
gr, fehler, _ = rechnen.gruppen_bilden(s.kopf, s.positionen, s.k)
assert any(f["grund"] == "Teil zu lang für das 3D-Greifmaß der Maschine" for f in fehler)
ok("G7 Teil 5.695 mm mit 3D: FEHLER „Teil zu lang für das 3D-Greifmaß“, nicht eingeplant")
t_alt = Teil(13, 10, "A", 1, 1000, True, True, 100, 100)
assert rechnen.teil_kennung(t_alt) == rechnen.teil_kennung(replace(t_alt, rest=0.0))
assert rechnen.teil_kennung(replace(t_alt, rest=300)) != rechnen.teil_kennung(t_alt)
ok("G7 Prüfsumme: Teile ohne 3D wie bisher (Angebote bleiben aktuell), mit 3D-Greifmaß neu")
print("Alle 3D-Greifmaß-Tests bestanden.")
