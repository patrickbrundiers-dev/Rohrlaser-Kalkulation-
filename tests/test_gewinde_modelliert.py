"""Modellierte Gewinde schnell als Drehteil (Verbesserungsplan 06.11.2026, Paket 3 A1/C2): 0003-400-001 hat 18 Körper
mit Gewindeflanken als Freiformflächen (Gewindestangen, Gewindegänge als eigener Körper). Die Profilsuche schnitt jeden
2–26 Minuten und fand doch kein Profil. Jetzt erkennt eine Vorprüfung das Gewinde (step_drehfraes.gewinde) und misst
das Teil gleich als Drehteil, vereinfacht (Ampel gelb, Hinweis „vereinfacht gemessen“).
- Gewindestange M12 × 40 (Flanken als Wendel-Sweep): Drehteil Ø12 × 40, Außengewinde, unter 10 s
- nur die Gewindegänge als eigener Körper (Ring Ø9,3–12): Drehteil mit Merkmal „nur Gewindegänge“
- ein Rohr, ein Rundstahl und eine Stufenwelle ohne Gewinde: Vorprüfung greift nicht
- Länge eines Drehteils mit gegenläufigen Zylinderachsen weit weg vom Nullpunkt (Rolle 10 mm kam als 2534 mm)

Aufruf: python tests/test_gewinde_modelliert.py
"""
import math
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeWire  # noqa: E402
from OCP.BRepLib import BRepLib  # noqa: E402
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.Geom import Geom_CylindricalSurface  # noqa: E402
from OCP.Geom2d import Geom2d_Line, Geom2d_TrimmedCurve  # noqa: E402
from OCP.gp import gp_Ax2, gp_Ax3, gp_Dir, gp_Dir2d, gp_Pnt, gp_Pnt2d  # noqa: E402

import step_drehfraes as df  # noqa: E402
import step_geometrie as g  # noqa: E402


def ok(text):
    print("OK    ", text)


def zylinder(r, z0, h):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), r, h).Shape()


def gewindegang(d, p, l):
    """Gewindeflanken als Wendel-Sweep (wie aus dem CAD: Freiformflächen) und Kernradius."""
    r, rk = d / 2, d / 2 - 0.6 * p
    flaeche = Geom_CylindricalSurface(gp_Ax3(gp_Pnt(0, 0, -p), gp_Dir(0, 0, 1)), rk)
    gaenge = (l + 2 * p) / p
    linie = Geom2d_Line(gp_Pnt2d(0, 0), gp_Dir2d(2 * math.pi, p))
    kante = BRepBuilderAPI_MakeEdge(Geom2d_TrimmedCurve(linie, 0, gaenge * math.hypot(2 * math.pi, p)), flaeche).Edge()
    BRepLib.BuildCurves3d_s(kante)
    profil = BRepBuilderAPI_MakePolygon(gp_Pnt(rk - 0.1, 0, -1.45 * p), gp_Pnt(r, 0, -1.05 * p), gp_Pnt(r, 0, -0.95 * p),
                                        gp_Pnt(rk - 0.1, 0, -0.55 * p), True).Wire()
    ps = BRepOffsetAPI_MakePipeShell(BRepBuilderAPI_MakeWire(kante).Wire())
    ps.SetMode(gp_Dir(0, 0, 1))
    ps.Add(profil)
    ps.Build()
    ps.MakeSolid()
    return ps.Shape(), rk


def messen(solid):
    t0 = time.time()
    t = g.analysiere(solid, "test", 1)
    return t, time.time() - t0


# Gewindestange M12 × 40
gang, rk = gewindegang(12, 1.75, 40)
stange = BRepAlgoAPI_Common(BRepAlgoAPI_Fuse(zylinder(rk, -4, 48), gang).Shape(), zylinder(7, 0, 40)).Shape()
t, sek = messen(stange)
assert t.bauteiltyp == df.DREHTEIL and t.abm_a == 12 and abs(t.laenge - 40) < 0.01, (t.bauteiltyp, t.abm_a, t.laenge)
assert "Außengewinde Ø12 modelliert" in t.drehfraes["merkmale"], t.drehfraes["merkmale"]
assert t.sicherheit["profil"] == "unsicher" and any("vereinfacht gemessen" in h for h in t.hinweise), t.hinweise
assert sek < 10, f"{sek:.1f} s"
ok(f"Gewindestange M12 × 40 mit Gewindeflanken: Drehteil Ø12 × 40, gelb „vereinfacht gemessen“, {sek:.1f} s")

# nur die Gewindegänge (Kern ist ein anderer Körper), wie in 0003-400-001
ring = BRepAlgoAPI_Cut(stange, zylinder(rk - 0.3, -1, 42)).Shape()
t, sek = messen(ring)
assert t.bauteiltyp == df.DREHTEIL and "nur Gewindegänge" in t.drehfraes["merkmale"], (t.bauteiltyp, t.drehfraes)
assert sek < 10, f"{sek:.1f} s"
ok(f"nur Gewindegänge als eigener Körper: Drehteil mit Merkmal „nur Gewindegänge“, {sek:.1f} s")

# ohne Gewinde: Vorprüfung greift nicht
rohr = BRepAlgoAPI_Cut(zylinder(20, 0, 500), zylinder(17, -1, 502)).Shape()
welle = BRepAlgoAPI_Fuse(zylinder(10, 0, 60), zylinder(15, 60, 30)).Shape()
for name, s in (("Rohr Ø40 × 3", rohr), ("Rundstahl Ø20", zylinder(10, 0, 300)), ("Stufenwelle", welle)):
    assert g._gewindeteil(s, "test", 1) is None, name
t, _ = messen(rohr)
assert t.profilform == "Rundrohr", t.profilform
ok("Rohr, Rundstahl und Stufenwelle ohne Gewinde: Vorprüfung greift nicht, Rohr bleibt Rundrohr")
# Länge eines Drehteils, dessen Zylinder gegenläufige Achsen haben, weit weg vom Nullpunkt (Prüfsammlung 07.11.2026:
# Rolle 10 mm lang kam als 2534 mm, Schraube M10 × 80 als 2149 mm)
schaft = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 1000), gp_Dir(0, 0, 1)), 5, 80).Shape()
kopf = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 1086.4), gp_Dir(0, 0, -1)), 8, 6.4).Shape()
fase = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 1000), gp_Dir(0, 0, 1)), 3, 2).Shape()
bolzen = BRepAlgoAPI_Cut(BRepAlgoAPI_Fuse(schaft, kopf).Shape(), fase).Shape()
fl = df.flaechen(bolzen)
assert any(e["typ"] == "zylinder" and e["achse"][1][2] < 0 for e in fl), "Testteil braucht eine gegenläufige Achse"
info = df.drehteil(fl)
assert info is not None and abs(info["laenge"] - 86.4) < 0.01, info and info["laenge"]
ok(f"Drehteil weit weg vom Nullpunkt, Zylinder mit gegenläufigen Achsen: Länge {info['laenge']} mm (vorher doppelter "
   "Abstand vom Nullpunkt)")
print("Alle Tests OK")
