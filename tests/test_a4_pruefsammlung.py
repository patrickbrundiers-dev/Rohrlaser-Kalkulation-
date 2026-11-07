"""Erkennung nach der Prüfsammlung A4 (Patrick 07.11.2026): 53 typische Teile aus Baggerschaufel, Dach und
0003-400-001 hat Patrick bestätigt, 23 waren falsch erkannt. Nachgebaute Formen, je Regel eine:
- Normteile: Kugel und Gewindestange mit zwei Sechskantmuttern (waren Rundstahl/Rundrohr)
- Drehteile: Ring mit Kugelkalotten (war Sonderprofil), Hülse mit Boden (war Rundrohr)
- Kantteile: Winkel ohne Normmaß (Zoll 50,8 × 3,2), Winkel L 30×30×3 mit Biegeradius, gespiegelte Kopie eines
  Kantteils mit krummer Dicke 3,0378 (der Klassierer hielt seine Toleranz nicht ein: kein Kantteil)
- Bleche: Brennteil 640 × 80 mit Schweißfasen, Flachstahl mit Langlöchern, kurze Lasche mit Bohrung, Platte mit
  Einpressbolzen; ein glatter langer Flachstahl bleibt Flachstahl
- Frästeil: Klotz 25 × 15 × 18,5 mit Bohrung (war Rechteckrohr)
- mehrere Teile in einem Körper (Platte mit angeschweißter Mutter): gelb, nicht übernommen, Hinweis

Aufruf: python tests/test_a4_pruefsammlung.py
"""
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf  # noqa: E402

import step_geometrie as g  # noqa: E402
from formen_baukasten import kant, kugel, ohne, plus, prisma, quader, verschiebe, zyl  # noqa: E402
from step_abwicklung import abwickeln  # noqa: E402


def ok(text):
    print("OK    ", text)


def messen(form):
    return g.analysiere(form, "test", 1)


def sechskant(sw, h, z=0.0, x=0.0, y=0.0):
    r = sw / math.sqrt(3)
    return verschiebe(prisma([(r * math.cos(math.radians(30 + 60 * i)), r * math.sin(math.radians(30 + 60 * i)))
                              for i in range(6)], h), x, y, z)


# ---------------------------------------------------------------- Normteile
t = messen(kugel(4.365, 0))
assert t.bauteiltyp == "Drehteil" and t.drehfraes.get("normteil") == "Kugel" and t.abm_a == 8.73, (t.bauteiltyp, t.drehfraes)
assert any("Normteil: Kugel Ø8,73" in h for h in t.hinweise), t.hinweise
ok("Kugel Ø8,73: Normteil (Zukauf), nicht Rundstahl")

stange = plus(zyl(6.35, 100), sechskant(19.05, 11, 6), sechskant(19.05, 11, 83))
t = messen(stange)
assert t.drehfraes and "Gewindestange mit Mutter" in t.drehfraes.get("normteil", ""), (t.bauteiltyp, t.profilform, t.drehfraes)
assert abs(t.laenge - 100) < 0.01 and t.abm_a == 12.7, (t.laenge, t.abm_a)
ok("Gewindestange Ø12,7 × 100 mit zwei Muttern SW 19,05: Normteil, nicht Rundrohr")

# ---------------------------------------------------------------- Drehteile
ring = ohne(zyl(18.75, 6.8), zyl(14.75, 6.8))
for i in range(4):
    a = math.radians(45 + 90 * i)
    k = verschiebe(kugel(3, 0), 16.75 * math.cos(a), 16.75 * math.sin(a), 6.8)
    ring = ohne(ring, k)
t = messen(ring)
assert t.bauteiltyp == "Drehteil" and "Kalotten/Taschen (gefräst)" in t.drehfraes["merkmale"], (t.bauteiltyp, t.drehfraes)
assert t.abm_a == 37.5 and abs(t.laenge - 6.8) < 0.01, (t.abm_a, t.laenge)
ok("Ring Ø37,5 × 6,8 mit vier Kugelkalotten: Drehteil, nicht Sonderprofil")

huelse = ohne(zyl(9.5, 97), zyl(4.5, 95))
t = messen(huelse)
assert t.bauteiltyp == "Drehteil" and "Sackbohrung" in t.drehfraes["merkmale"], (t.bauteiltyp, t.profilform, t.drehfraes)
ok("Hülse Ø19 × 97 mit Boden (Bohrung Ø9 nicht durch): Drehteil, nicht Rundrohr")

# ---------------------------------------------------------------- Kantteile
zoll = plus(quader(50.8, 3.175, 600), quader(3.175, 50.8, 600))
t = messen(zoll)
assert t.bauteiltyp == "Blech gekantet" and "Normmaß" in t.art_grund, (t.bauteiltyp, t.profilform, t.art_grund)
ok("Winkel 50,8 × 50,8 × 3,175 scharfkantig (kein Normmaß): Kantteil, Profil als Auswahl")

t = messen(kant([(0, 30 - 1.5), (0, 0), (30 - 1.5, 0)], 3, lg=150))
assert t.bauteiltyp == "Blech gekantet", (t.bauteiltyp, t.profilform, t.normprofil)
ok("Winkel L 30 × 30 × 3 mit Biegeradius (außen = innen + Dicke): Kantteil, auch im L-Normmaß")

d = 3.0378
haken = plus(quader(150, d, 900), quader(d, 60, 900), quader(150, d, 900, 0, 60 - d))
haken = verschiebe(haken, -4164.92, 370.3, 1244.4)
spiegel = gp_Trsf()
spiegel.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)))
gespiegelt = BRepBuilderAPI_Transform(haken, spiegel, True).Shape()
for name, form in (("Original", haken), ("gespiegelte Kopie", gespiegelt)):
    a = abwickeln(form, round(d, 3))
    assert "fehler" not in a, (name, a.get("fehler"))
ok("U-Kantteil mit Dicke 3,0378 weit vom Nullpunkt, Original und gespiegelte Kopie: beide abwickelbar")


class Klassierer:
    """Wie im echten 0003-400-001: 0,2 µm hinter der Gegenfläche „außen“ trotz Toleranz 1 µm."""
    def __init__(self, dicke):
        self.dicke, self.a = dicke, None

    def Perform(self, q, tol):
        self.a = round(-q.X(), 6)

    def State(self):
        from OCP.TopAbs import TopAbs_IN, TopAbs_OUT
        return TopAbs_IN if self.a < self.dicke else TopAbs_OUT


import step_abwicklung  # noqa: E402
from OCP.gp import gp_Vec  # noqa: E402
assert step_abwicklung._gegenflaeche(Klassierer(3.0378), gp_Pnt(0, 0, 0), gp_Vec(1, 0, 0), 3.038)
assert not step_abwicklung._gegenflaeche(Klassierer(4.0), gp_Pnt(0, 0, 0), gp_Vec(1, 0, 0), 3.038)
ok("Blechhaut: Gegenfläche 0,2 µm vor der gerundeten Dicke zählt (Klassierer ohne Toleranz), 1 mm daneben nicht")

# ---------------------------------------------------------------- Bleche
brenn = prisma([(0, 0), (640, 0), (640, 40), (570, 80), (10, 80), (0, 70)], 2274)
t = messen(brenn)
assert t.bauteiltyp == "Blech" and t.wandstaerke == 80, (t.bauteiltyp, t.profilform, t.wandstaerke)
assert any("Fasen" in h for h in t.hinweise), t.hinweise
ok("Brennteil 640 × 80 × 2274 mit Schweißfasen: Blech mit Hinweis Fasen, kein Flachstahl")

langloch = ohne(quader(150, 35, 8.5), quader(20, 9, 8.5, 20, 13), zyl(4.5, 8.5, 0, 20, 17.5), zyl(4.5, 8.5, 0, 40, 17.5),
                quader(20, 9, 8.5, 110, 13), zyl(4.5, 8.5, 0, 110, 17.5), zyl(4.5, 8.5, 0, 130, 17.5))
t = messen(langloch)
assert t.bauteiltyp == "Blech" and t.art_regel == "Flachstahl → Blech", (t.bauteiltyp, t.profilform, t.art_regel)
assert t.alternative is not None and t.alternative.profilform == "Flachstahl", t.alternative
ok("Flachstahl 35 × 8,5 × 150 mit zwei Langlöchern: Blech, Flachstahl als Auswahl")

lasche = ohne(quader(25, 15, 5), zyl(4.5, 5, 0, 10, 7.5))
t = messen(lasche)
assert t.bauteiltyp == "Blech", (t.bauteiltyp, t.profilform, t.art_regel)
ok("Lasche 25 × 15 × 5 mit Bohrung Ø9: Blech, kein Flachstahl")

t = messen(quader(1700, 100, 16))
assert t.bauteiltyp == "Profil" and t.profilform == "Flachstahl", (t.bauteiltyp, t.profilform)
ok("glatter Flachstahl 100 × 16 × 1700 bleibt Flachstahl")

platte = plus(quader(380, 250, 9.5), *(zyl(4, 9.5, 9.5, 40 + 100 * i, 60 + 130 * j) for i in range(3) for j in range(2)))
t = messen(platte)
assert t.bauteiltyp == "Blech" and t.wandstaerke == 9.5, (t.bauteiltyp, t.profilform, t.wandstaerke)
assert any("Aufgesetzte Kleinteile" in h for h in t.hinweise), t.hinweise
ok("Platte 380 × 250 × 9,5 mit sechs Einpressbolzen: Blech mit Hinweis, kein Frästeil")

# ---------------------------------------------------------------- Frästeil
klotz = ohne(quader(25, 15, 18.5), zyl(5, 18.5, 0, 12.5, 7.5))
t = messen(klotz)
assert t.bauteiltyp == "Frästeil", (t.bauteiltyp, t.profilform, t.art_regel)
ok("Klotz 25 × 15 × 18,5 mit Bohrung Ø10: Frästeil, kein Rechteckrohr")

# ---------------------------------------------------------------- mehrere Teile in einem Körper
mutter = ohne(sechskant(36, 20, 9.5, 73, 20), zyl(12, 20, 9.5, 73, 20))
t = messen(plus(quader(146, 40, 9.5), mutter))
assert t.sicherheit.get("profil") == "unsicher" and "Mehrere Teile in einem Körper" in t.hinweise[0], t.hinweise
ok("Platte mit angeschweißter Mutter SW 36 in einem Körper: gelb, nicht übernommen, Hinweis „mehrere Teile“")

print("Alle Tests OK")
