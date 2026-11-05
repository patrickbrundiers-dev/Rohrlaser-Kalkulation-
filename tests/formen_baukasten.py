"""Formenbaukasten für die Erkennungs-Testreihen (Dreh-/Frästeile, Bleche): Zylinder, Kegel, Quader, Prismen, Fasen,
Radien, Lage im Raum, STEP schreiben (Patrick 03.11.2026: „Test für verschiedene Dreh- und Frästeile für sichere
Erkennung“)."""
import math, os, sys
from pathlib import Path
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone, BRepPrimAPI_MakeSphere, BRepPrimAPI_MakePrism
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec


def zyl(r, h, z=0.0, x=0.0, y=0.0, d=(0, 0, 1)):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(*d)), r, h).Shape()


def kegel(r1, r2, h, z=0.0):
    return BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, z), gp_Dir(0, 0, 1)), r1, r2, h).Shape()


def kugel(r, z):
    return BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, z), r).Shape()


def quader(a, b, c, x=0.0, y=0.0, z=0.0):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), a, b, c).Shape()


def prisma(punkte, h):
    p = BRepBuilderAPI_MakePolygon()
    for x, y in punkte:
        p.Add(gp_Pnt(x, y, 0))
    p.Close()
    return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(p.Wire()).Face(), gp_Vec(0, 0, h)).Shape()


def plus(*s):
    a = s[0]
    for b in s[1:]:
        a = BRepAlgoAPI_Fuse(a, b).Shape()
    return a


def ohne(a, *s):
    for b in s:
        a = BRepAlgoAPI_Cut(a, b).Shape()
    return a


def _kanten(s, wahl):
    ex = TopExp_Explorer(s, TopAbs_EDGE)
    while ex.More():
        e = TopoDS.Edge_s(ex.Current()) if hasattr(TopoDS, "Edge_s") else TopoDS.Edge(ex.Current())
        if wahl(e):
            yield e
        ex.Next()


def kreiskanten_bei(z_werte, r_min=0.0):
    def w(e):
        c = BRepAdaptor_Curve(e)
        if c.GetType() != GeomAbs_Circle:
            return False
        k = c.Circle()
        return any(abs(k.Location().Z() - z) < 1e-6 for z in z_werte) and k.Radius() > r_min
    return w


def fase(s, wahl, m):
    f = BRepFilletAPI_MakeChamfer(s)
    for e in _kanten(s, wahl):
        f.Add(m, e)
    return f.Shape()


def radius(s, wahl, r):
    f = BRepFilletAPI_MakeFillet(s)
    for e in _kanten(s, wahl):
        f.Add(r, e)
    return f.Shape()


def gerade_kanten_parallel(achse):
    def w(e):
        c = BRepAdaptor_Curve(e)
        if c.GetType() != GeomAbs_Line:
            return False
        d = c.Line().Direction()
        return abs(abs(d.X() * achse[0] + d.Y() * achse[1] + d.Z() * achse[2]) - 1) < 1e-6
    return w


def lage(s, ax=(1, 1, 0), grad=37.0, v=(120, -40, 75)):
    t = gp_Trsf()
    n = math.sqrt(sum(x * x for x in ax))
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*(x / n for x in ax))), math.radians(grad))
    t2 = gp_Trsf(); t2.SetTranslation(gp_Vec(*v))
    return BRepBuilderAPI_Transform(BRepBuilderAPI_Transform(s, t, True).Shape(), t2, True).Shape()


def verschiebe(s, x, y, z):
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(x, y, z))
    return BRepBuilderAPI_Transform(s, t, True).Shape()


def schreibe(teile, ziel):
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    ziel = Path(ziel)
    fd, alt = sys.stdout.fileno(), os.dup(sys.stdout.fileno())
    sys.stdout.flush()
    os.dup2(os.open(os.devnull, os.O_WRONLY), fd)
    try:
        for name, form in teile.items():
            w = STEPControl_Writer()
            w.Transfer(form, STEPControl_AsIs)
            assert w.Write(str(ziel / f"{name}.step")) == IFSelect_RetDone, name
    finally:
        os.dup2(alt, fd)


def kant(mitte, t, R=None, lg=500):
    """Blech der Dicke t um die Mittellinie (offener Zug); Biegeradius innen R (Vorgabe t), außen R + t."""
    R = t if R is None else R
    def off(s):
        pts = []
        n = len(mitte)
        for i in range(n):
            if i == 0 or i == n - 1:
                a, b = (mitte[0], mitte[1]) if i == 0 else (mitte[-2], mitte[-1])
                dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy)
                nx, ny = -dy / L, dx / L
                pts.append((mitte[i][0] + s * nx * t / 2, mitte[i][1] + s * ny * t / 2))
            else:
                a, b, c = mitte[i - 1], mitte[i], mitte[i + 1]
                d1 = ((b[0] - a[0]), (b[1] - a[1])); l1 = math.hypot(*d1); d1 = (d1[0] / l1, d1[1] / l1)
                d2 = ((c[0] - b[0]), (c[1] - b[1])); l2 = math.hypot(*d2); d2 = (d2[0] / l2, d2[1] / l2)
                n1, n2 = (-d1[1], d1[0]), (-d2[1], d2[0])
                bx, by = n1[0] + n2[0], n1[1] + n2[1]; bl = math.hypot(bx, by)
                cosh = (n1[0] * bx + n1[1] * by) / bl
                f = s * t / 2 / cosh
                pts.append((round(b[0] + bx / bl * f, 6), round(b[1] + by / bl * f, 6)))
        return pts
    links, rechts = off(1), off(-1)
    radien = {}
    for i in range(1, len(mitte) - 1):
        a, b, c = mitte[i - 1], mitte[i], mitte[i + 1]
        kreuz = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if R > 0:
            radien[links[i]] = R if kreuz > 0 else R + t
            radien[rechts[i]] = R + t if kreuz > 0 else R
    poly = links + list(reversed(rechts))
    from erzeuge_testteile import profil
    return profil(poly, lg, radien or None)
