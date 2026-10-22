"""Erzeugt die STEP-Testteile der RP-Profile (tests/step_rp) aus den MegaCAD-Makros in tests/rp: Querschnitt als
Polygon (Bögen fein unterteilt), als Prisma extrudiert, dazu Gehrung, Bohrung, Lage im Raum, eine Mehrkammer-
Variante (Zwischensteg) und ein Verbundprofil (Kunststoffkern als zweiter Körper).

Aufruf: python tests/erzeuge_rp_teile.py   (braucht OpenCascade, wie tests/erzeuge_testteile.py)
"""
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism  # noqa: E402
from OCP.gp import gp_Pnt, gp_Vec  # noqa: E402

from erzeuge_testteile import baugruppe, bohrung_quer, drehe_beliebig, gehrung, schreibe, verschiebe  # noqa: E402
from rohrlaser import rp_profile  # noqa: E402

ZIEL = HIER / "step_rp"
MAKROS = HIER / "rp"


def draht(pts):
    p = BRepBuilderAPI_MakePolygon()
    for x, y in pts:
        p.Add(gp_Pnt(x, y, 0))
    p.Close()
    return p.Wire()


def rp_rohr(name, laenge):
    """RP-Profil aus dem Makro tests/rp/<name>.mac als Prisma (Ecke unten links im Nullpunkt). Ergebnis: (Form,
    Querschnitt)."""
    q = rp_profile.querschnitt(rp_profile.lies_mac(MAKROS / f"{name}.mac"), mit_konturen=True)
    x0, y0 = q["x0"], q["y0"]
    (aussen,) = q["konturen"]["aussen"]
    f = BRepBuilderAPI_MakeFace(draht([(x - x0, y - y0) for x, y in rp_profile.ausduennen(aussen)]))
    for k in q["konturen"]["kammern"]:
        w = draht([(x - x0, y - y0) for x, y in reversed(rp_profile.ausduennen(k))])
        f.Add(w)
    return BRepPrimAPI_MakePrism(f.Face(), gp_Vec(0, 0, laenge)).Shape(), q


def fuse(a, b):
    return BRepAlgoAPI_Fuse(a, b).Shape()


if __name__ == "__main__":
    s, q = rp_rohr("0106-35", 1000)
    schreibe(s, "RP01_0106-35_L1000", ZIEL)
    s, q = rp_rohr("0103-50", 800)
    schreibe(drehe_beliebig(s), "RP02_0103-50_schraeg_L800", ZIEL)
    s, q = rp_rohr("0142-34", 600)
    schreibe(gehrung(verschiebe(s, -q["breite"] / 2, -q["hoehe"] / 2, 0), 600, 45), "RP03_0142-34_Gehrung45_L600",
             ZIEL)
    s, q = rp_rohr("0106-35", 700)
    schreibe(bohrung_quer(bohrung_quer(s, 8, 200, (0, 1, 0)), 8, 500, (0, 1, 0)), "RP04_0106-35_2xD8_L700", ZIEL)
    # Mehrkammer: Zwischensteg 2 mm mitten in der Kammer von 0106-35 (Kammer etwa x 2 … 48, y 2 … 32)
    s, q = rp_rohr("0106-35", 500)
    steg = BRepPrimAPI_MakeBox(gp_Pnt(24, 1.5, 0), 2, 31, 500).Shape()
    schreibe(fuse(s, steg), "RP05_0106-35_Zwischensteg_L500", ZIEL)
    # Verbund: Kunststoffkern (Quader in der Kammer) als zweiter Körper
    s, q = rp_rohr("0106-35", 500)
    kern = BRepPrimAPI_MakeBox(gp_Pnt(10, 8, 0), 20, 15, 500).Shape()
    schreibe(baugruppe(s, kern), "RP06_0106-35_Verbund_L500", ZIEL)
    print("RP-Testteile in", ZIEL)
