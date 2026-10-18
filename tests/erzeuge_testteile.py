"""Erzeugt Test-STEP-Dateien mit bekannten Sollwerten (tests/step/)."""
import math
import sys
from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeBox
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Line
from OCP.BRep import BRep_Builder
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir, gp_Trsf, gp_Ax1, gp_Vec

ZIEL = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "step"


def cut(a, b):
    return BRepAlgoAPI_Cut(a, b).Shape()


def rundrohr(d, t, l):
    a = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), d / 2, l).Shape()
    i = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -1), gp_Dir(0, 0, 1)), d / 2 - t, l + 2).Shape()
    return cut(a, i)


def kastenrohr(b, h, t, l, r_aussen):
    def box(bb, hh, z0, ll, r):
        s = BRepPrimAPI_MakeBox(gp_Pnt(-bb / 2, -hh / 2, z0), bb, hh, ll).Shape()
        if r <= 0:
            return s
        f = BRepFilletAPI_MakeFillet(s)
        ex = TopExp_Explorer(s, TopAbs_EDGE)
        while ex.More():
            e = TopoDS.Edge(ex.Current())
            c = BRepAdaptor_Curve(e)
            if c.GetType() == GeomAbs_Line and abs(abs(c.Line().Direction().Z()) - 1) < 1e-9:
                f.Add(r, e)
            ex.Next()
        return f.Shape()
    return cut(box(b, h, 0, l, r_aussen), box(b - 2 * t, h - 2 * t, -1, l + 2, max(r_aussen - t, 0)))


def bohrung_quer(shape, d, z, achse=(1, 0, 0)):
    zyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(-200 * achse[0], -200 * achse[1], z), gp_Dir(*achse)), d / 2, 400).Shape()
    return cut(shape, zyl)


def gehrung(shape, l, winkel_grad, breite=500):
    """Schneidet das obere Ende unter Winkel ab (um Y-Achse geneigte Ebene durch (0,0,l))."""
    k = BRepPrimAPI_MakeBox(gp_Pnt(-breite / 2, -breite / 2, 0), breite, breite, breite).Shape()
    tr = gp_Trsf(); tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), math.radians(winkel_grad))
    k = BRepBuilderAPI_Transform(k, tr, True).Shape()
    tr2 = gp_Trsf(); tr2.SetTranslation(gp_Vec(0, 0, l))
    k = BRepBuilderAPI_Transform(k, tr2, True).Shape()
    return cut(shape, k)


def drehe_beliebig(shape):
    """Lage im Raum schräg, damit die Achsenerkennung geprüft wird."""
    tr = gp_Trsf(); tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 1, 0)), math.radians(37))
    tr2 = gp_Trsf(); tr2.SetTranslation(gp_Vec(120, -45, 300))
    return BRepBuilderAPI_Transform(BRepBuilderAPI_Transform(shape, tr, True).Shape(), tr2, True).Shape()


def verschiebe(shape, x, y, z):
    tr = gp_Trsf(); tr.SetTranslation(gp_Vec(x, y, z))
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def baugruppe(*shapes):
    """Mehrere Körper in einer Datei (wie eine Baugruppe aus dem CAD)."""
    c = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c


def schreibe(shape, name, ziel=None):
    ziel = ziel or ZIEL
    ziel.mkdir(parents=True, exist_ok=True)
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    w.Write(str(ziel / f"{name}.step"))


if __name__ == "__main__":
    # 1 Rundrohr glatt
    schreibe(rundrohr(42.4, 2.0, 1250), "T01_RR42-4x2_L1250")
    # 2 Rundrohr mit Querbohrung Ø10 (durch beide Wände), räumlich gedreht
    s = bohrung_quer(rundrohr(42.4, 2.0, 860), 10, 430)
    schreibe(drehe_beliebig(s), "T02_RR42-4x2_L860_Bohrung")
    # 3 Quadratrohr 40x40x3 mit Eckradius 6, Querbohrung Ø8 durch eine Seite
    s = kastenrohr(40, 40, 3, 2150, 6)
    zyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 1000), gp_Dir(1, 0, 0)), 4, 100).Shape()
    schreibe(cut(s, zyl), "T03_QR40x3_L2150_Bohrung")
    # 4 Rechteckrohr 60x40x3 scharfkantig, ein Ende 45° Gehrung
    schreibe(gehrung(kastenrohr(60, 40, 3, 1795.5 + 60, 0), 1795.5, 45), "T04_RE60x40x3_Gehrung")
    # 5 Rundrohr 33,7x2,6 (nicht in den Beispiel-Stammdaten)
    schreibe(rundrohr(33.7, 2.6, 500), "T05_RR33-7x2-6_L500")
    # 6 Quadratrohr 40x40x3 mit Langloch 20 breit von 10 % bis 90 % der Länge in einer Wand
    s = kastenrohr(40, 40, 3, 1000, 6)
    schlitz = BRepPrimAPI_MakeBox(gp_Pnt(10, -10, 100), 20, 20, 800).Shape()
    schreibe(cut(s, schlitz), "T06_QR40x3_L1000_Langloch")
    # 7 Quadratrohr 40x40x3 L1000, r6: 4x Kernloch Ø5 (M6) in +X-Wand, Rechteckausschnitt 10x20 in -X-Wand,
    #   Gravur 24x5 (0,3 tief) in +Y-Wand, Ausklinkung 16 breit x 15 tief am Ende B in +X-Wand
    s = kastenrohr(40, 40, 3, 1000, 6)
    for z in (100, 150, 200, 250):
        s = cut(s, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(10, 0, z), gp_Dir(1, 0, 0)), 2.5, 20).Shape())
    s = cut(s, BRepPrimAPI_MakeBox(gp_Pnt(-21, -5, 600), 5, 10, 20).Shape())
    s = cut(s, BRepPrimAPI_MakeBox(gp_Pnt(-12, 19.7, 400), 24, 2, 5).Shape())
    s = cut(s, BRepPrimAPI_MakeBox(gp_Pnt(15, -8, 985), 10, 16, 20).Shape())
    schreibe(s, "T07_QR40x3_L1000_Gewinde_Gravur")
    # 8 Baugruppe (eigener Ordner step_satz, damit die Einzelteil-Tests unverändert bleiben): 3x Quadratrohr
    #   40x40x3 L600 (eines gedreht, eines gespiegelt) mit Bohrung Ø8 + 1x Rundrohr 42,4x2 L900 = 2 verschiedene Teile
    q = kastenrohr(40, 40, 3, 600, 6)
    q = cut(q, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 150), gp_Dir(1, 0, 0)), 4, 100).Shape())
    gespiegelt = gp_Trsf(); gespiegelt.SetRotation(gp_Ax1(gp_Pnt(0, 0, 300), gp_Dir(0, 1, 0)), math.pi)
    schreibe(baugruppe(q, verschiebe(q, 100, 0, 0), BRepBuilderAPI_Transform(verschiebe(q, 200, 0, 0), gespiegelt, True).Shape(),
                       drehe_beliebig(rundrohr(42.4, 2.0, 900))),
             "T08_Gestell_Baugruppe", ZIEL.parent / "step_satz")
    print("Testteile geschrieben nach", ZIEL)
