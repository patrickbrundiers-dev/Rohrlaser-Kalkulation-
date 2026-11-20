"""Testteile der Importengine (Laserhub-Vergleich, Patrick 20.11.2026): erzeugt tests/step_importengine/*.step.

Aufruf: python tests/importengine_teile.py  (braucht OCP). Die erzeugten Dateien liegen im Repository, damit die
Testreihe ohne Neuerzeugen reproduzierbar ist; das Skript dokumentiert, wie sie entstanden sind (Referenzmaße im
Dateinamen und in tests/test_importengine.py REFERENZ).
- I01 Flachoval 60 × 30 × 2, L 800, zwei Bohrungen Ø 8 oben
- I02 Elliptisch 60 × 30 × 2 (Innenkontur als echter Abstand, B-Spline), L 800
- I03 Halbflachoval 80 × 30 × 2, L 600
- I04 L-Profil 50 × 30 × 4 (scharfkantig), L 700
- I05 große Baugruppe: 24 × QR 40 × 3 L 500, 16 × RE 60 × 40 × 3 L 1000, 8 × RR 42,4 × 2 L 300 (48 Körper)
- I06 gemischte Baugruppe: QR 40 × 3 L 600 mit Langloch, RR 33,7 × 2,6 L 400, Blech 200 × 100 × 5, Frästeil
  (Klotz 60 × 40 × 30 mit Bohrung Ø 10 und Tasche)
- I07 Fertigbarkeit: QR 40 × 3 L 800 oben mit Loch Ø 1,5 (x 100), zwei Löchern Ø 10 mit 1 mm Steg (x 300/311),
  Loch Ø 8 mit 1 mm Steg zum Ende A (x 5), Gravur 20 × 5 × 0,8 mm tief (x 500), Ausschnitt 20 × 10 mit scharfen
  Ecken (x 650)
- I08 Gravur/Einnietmutter: QR 40 × 3 L 600 oben Gravur 10 × 5 × 0,3 (x 300–305) mit Loch Ø 10 bei x 311 (1 mm
  Abstand), Loch Ø 9 (M6-Einnietmutter) bei x 8 (3,5 mm zum Ende A), Loch Ø 9 bei x 450 (frei)
- I09 Umfang offen: QR 40 × 3 L 400 oben fünf Fenster 34 × 16 an den Prüfpunkten (x 12, 100, 200, 300, 388):
  Umfang an keinem der 5 Prüfpunkte geschlossen
- I10 Rundrohr 40 × 2 L 300 oben Loch Ø 25 (x 150) und Ø 8 (x 250): bei XY zu groß bzw. in Ordnung
"""
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from OCP.BRep import BRep_Builder  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut  # noqa: E402
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,  # noqa: E402
                                BRepBuilderAPI_MakeWire, BRepBuilderAPI_Transform)
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism  # noqa: E402
from OCP.GC import GC_MakeArcOfCircle, GC_MakeSegment  # noqa: E402
from OCP.GeomAPI import GeomAPI_PointsToBSpline  # noqa: E402
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: E402
try:
    from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt  # noqa: E402
except ImportError:
    from OCP.TColgp import TColgp_Array1OfPnt  # noqa: E402
from OCP.TopoDS import TopoDS_Compound  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Elips, gp_Pnt, gp_Trsf, gp_Vec  # noqa: E402

ORDNER = Path(__file__).parent / "step_importengine"


def _p(x, y):
    return gp_Pnt(x, y, 0)


def _seg(a, b):
    return BRepBuilderAPI_MakeEdge(GC_MakeSegment(_p(*a), _p(*b)).Value()).Edge()


def _bogen(a, m, b):
    return BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(_p(*a), _p(*m), _p(*b)).Value()).Edge()


def _flaeche(*kanten):
    w = BRepBuilderAPI_MakeWire()
    for k in kanten:
        w.Add(k)
    return BRepBuilderAPI_MakeFace(w.Wire()).Face()


def flachoval(a, b, dy=0.0):
    r, g = b / 2, a - b
    return _flaeche(_seg((-g / 2, -r + dy), (g / 2, -r + dy)), _bogen((g / 2, -r + dy), (g / 2 + r, dy), (g / 2, r + dy)),
                    _seg((g / 2, r + dy), (-g / 2, r + dy)), _bogen((-g / 2, r + dy), (-g / 2 - r, dy), (-g / 2, -r + dy)))


def halbflachoval(a, b, s=0.0):
    """Außenkontur (s = 0) bzw. Innenkontur im echten Abstand s: unten gerade, an den Enden Viertelkreise um
    (±(a/2 − b), 0) mit Radius b − s, oben gerade."""
    h, r = a / 2 - b, b - s
    x0 = h + math.sqrt(r * r - s * s)
    w0, w1 = math.asin(s / r), math.pi / 2
    wm = (w0 + w1) / 2
    m = (h + r * math.cos(wm), r * math.sin(wm))
    return _flaeche(_seg((-x0, s), (x0, s)), _bogen((x0, s), m, (h, r)), _seg((h, r), (-h, r)),
                    _bogen((-h, r), (-m[0], m[1]), (-x0, s)))


def ellipse(a, b):
    el = gp_Elips(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), a / 2, b / 2)
    return BRepBuilderAPI_MakeFace(BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(el).Edge()).Wire()).Face()


def ellipse_innen(a, b, s, n=360):
    """Innenkontur einer Ellipse im Abstand s (echter Abstand wie eine Schale im CAD), als geschlossener B-Spline."""
    p, q = a / 2, b / 2
    pts = TColgp_Array1OfPnt(1, n + 1)
    for i in range(n + 1):
        t = 2 * math.pi * (i % n) / n
        x, y = p * math.cos(t), q * math.sin(t)
        nx, ny = math.cos(t) / p, math.sin(t) / q
        ln = math.hypot(nx, ny)
        pts.SetValue(i + 1, gp_Pnt(x - s * nx / ln, y - s * ny / ln, 0))
    kurve = GeomAPI_PointsToBSpline(pts, 3, 8).Curve()
    return BRepBuilderAPI_MakeFace(BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(kurve).Edge()).Wire()).Face()


def _prisma(flaeche, lg):
    return BRepPrimAPI_MakePrism(flaeche, gp_Vec(0, 0, lg)).Shape()


def rohr(aussen, innen, lg):
    return BRepAlgoAPI_Cut(_prisma(aussen, lg), _prisma(innen, lg)).Shape()


def kasten(a, b, s, lg, r=None):
    """Quadrat-/Rechteckrohr mit Außenradius r (Vorgabe 2 × s) und Innenradius r − s."""
    r = 2 * s if r is None else r

    def umriss(a_, b_, r_):
        x, y = a_ / 2, b_ / 2
        k = r_ * (1 - math.sqrt(0.5))
        return _flaeche(_seg((-x + r_, -y), (x - r_, -y)), _bogen((x - r_, -y), (x - k, -y + k), (x, -y + r_)),
                        _seg((x, -y + r_), (x, y - r_)), _bogen((x, y - r_), (x - k, y - k), (x - r_, y)),
                        _seg((x - r_, y), (-x + r_, y)), _bogen((-x + r_, y), (-x + k, y - k), (-x, y - r_)),
                        _seg((-x, y - r_), (-x, -y + r_)), _bogen((-x, -y + r_), (-x + k, -y + k), (-x + r_, -y)))
    return rohr(umriss(a, b, r), umriss(a - 2 * s, b - 2 * s, r - s), lg)


def rund(d, s, lg):
    au = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), d / 2, lg).Shape()
    inn = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), d / 2 - s, lg).Shape()
    return BRepAlgoAPI_Cut(au, inn).Shape()


def bohrung(form, z, d, y0=0.0):
    """Bohrung Ø d senkrecht von oben (+Y) bei z."""
    zyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, y0, z), gp_Dir(0, 1, 0)), d / 2, 200).Shape()
    return BRepAlgoAPI_Cut(form, zyl).Shape()


def langloch(form, z, lg, br, y0=0.0):
    box = BRepPrimAPI_MakeBox(gp_Pnt(-br / 2, y0, z - lg / 2), br, 200, lg).Shape()
    return BRepAlgoAPI_Cut(form, box).Shape()


def bewegen(form, dx=0.0, dy=0.0, dz=0.0, drehen_y=False):
    t = gp_Trsf()
    if drehen_y:
        from OCP.gp import gp_Ax1
        t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), math.pi / 2)
        t2 = gp_Trsf()
        t2.SetTranslation(gp_Vec(dx, dy, dz))
        t = t2.Multiplied(t)
    else:
        t.SetTranslation(gp_Vec(dx, dy, dz))
    return BRepBuilderAPI_Transform(form, t, True).Shape()


def verbund(formen):
    c = TopoDS_Compound()
    bb = BRep_Builder()
    bb.MakeCompound(c)
    for f in formen:
        bb.Add(c, f)
    return c


def schreiben(form, name):
    w = STEPControl_Writer()
    w.Transfer(form, STEPControl_AsIs)
    ORDNER.mkdir(exist_ok=True)
    w.Write(str(ORDNER / name))


def alle():
    fo = rohr(flachoval(60, 30), flachoval(56, 26), 800)
    fo = bohrung(bohrung(fo, 200, 8, 5), 600, 8, 5)
    schreiben(fo, "I01_FO60x30x2_L800_2xBohrung8.step")
    schreiben(rohr(ellipse(60, 30), ellipse_innen(60, 30, 2), 800), "I02_EO60x30x2_L800.step")
    schreiben(rohr(halbflachoval(80, 30), halbflachoval(80, 30, 2), 600), "I03_HFO80x30x2_L600.step")
    l_prof = _prisma(_flaeche(_seg((0, 0), (30, 0)), _seg((30, 0), (30, 4)), _seg((30, 4), (4, 4)),
                              _seg((4, 4), (4, 50)), _seg((4, 50), (0, 50)), _seg((0, 50), (0, 0))), 700)
    schreiben(l_prof, "I04_L50x30x4_L700.step")
    teile = []
    for i in range(24):
        teile.append(bewegen(kasten(40, 40, 3, 500), dx=(i % 6) * 80, dy=(i // 6) * 80))
    for i in range(16):
        teile.append(bewegen(kasten(60, 40, 3, 1000), dx=600 + (i % 4) * 100, dy=(i // 4) * 80))
    for i in range(8):
        teile.append(bewegen(rund(42.4, 2, 300), dx=1100 + (i % 4) * 80, dy=(i // 4) * 80))
    schreiben(verbund(teile), "I05_Baugruppe_48Teile.step")
    qr = langloch(kasten(40, 40, 3, 600), 300, 40, 10, 10)
    rr = bewegen(rund(33.7, 2.6, 400), dx=100)
    blech = BRepPrimAPI_MakeBox(gp_Pnt(200, -50, 0), 200, 5, 100).Shape()
    klotz = BRepPrimAPI_MakeBox(gp_Pnt(500, 0, 0), 60, 40, 30).Shape()
    klotz = BRepAlgoAPI_Cut(klotz, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(520, 20, -1), gp_Dir(0, 0, 1)), 5,
                                                                    40).Shape()).Shape()
    klotz = BRepAlgoAPI_Cut(klotz, BRepPrimAPI_MakeBox(gp_Pnt(535, 10, 15), 20, 20, 20).Shape()).Shape()
    schreiben(verbund([qr, rr, blech, klotz]), "I06_Baugruppe_gemischt.step")
    fertigbarkeit_teil()
    pruefregeln_teile()


def pruefregeln_teile():
    qr = kasten(40, 40, 3, 600)
    qr = BRepAlgoAPI_Cut(qr, BRepPrimAPI_MakeBox(gp_Pnt(-5, 19.7, 300), 10, 5, 5).Shape()).Shape()
    for z, d in ((311, 10), (8, 9), (450, 9)):
        qr = bohrung(qr, z, d, 5)
    schreiben(qr, "I08_QR40x3_L600_Gravur_Nietmutter.step")
    qr = kasten(40, 40, 3, 400)
    for z in (12, 100, 200, 300, 388):
        qr = langloch(qr, z, 16, 34, 5)
    schreiben(qr, "I09_QR40x3_L400_Umfang_offen.step")
    rr = bohrung(bohrung(rund(40, 2, 300), 150, 25, 5), 250, 8, 5)
    schreiben(rr, "I10_RR40x2_L300_Loch25.step")


def fertigbarkeit_teil():
    qr = kasten(40, 40, 3, 800)
    for z, d in ((100, 1.5), (300, 10), (311, 10), (5, 8)):
        qr = bohrung(qr, z, d, 5)
    qr = BRepAlgoAPI_Cut(qr, BRepPrimAPI_MakeBox(gp_Pnt(-10, 19.2, 500), 20, 5, 5).Shape()).Shape()
    qr = langloch(qr, 650, 20, 10, 5)
    schreiben(qr, "I07_QR40x3_L800_Fertigbarkeit.step")


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    alle()
    print("geschrieben:", ", ".join(sorted(p.name for p in ORDNER.glob("*.step"))))
