"""Testteile: Quadrat-/Rechteckrohr, an Biegestellen bis auf die Außenwand eingeschnitten und mit Radius gebogen
(Plan „gebogene und geknickte Rohre abwickeln“, Patrick 17.11.2026). Erzeugt das gebogene Teil, wie es eine STEP
zeigt, und die bekannte gestreckte Länge.

Rohr im eigenen Rahmen: Achse +Y, Querschnitt a (X) × b (Z), Mitte im Ursprung. gebogen(...) setzt gerade Stücke
und Biegestreifen aneinander: jedes Stück reicht innen bis zur Winkelhalbierenden der Biegung (Kerbflanke, SPALT
Schnittspalt), der Biegestreifen (bis rand unter der Außenseite) ist um die Biegeachse gedreht. Die Außenwand einer
Biegung wählt aussen: "-x", "+x", "-z", "+z" (Kerbe auf der Gegenseite), so gehen Biegungen in verschiedenen Ebenen.
"""
import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeRevol
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax1, gp_Ax2, gp_Ax3, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec

import erzeuge_testteile as et
import step_geometrie as g

SPALT = 0.2             # mm: Schnittspalt an der Kerbflanke
G = 3000.0              # mm: Größe der Hilfskörper

RICHTUNG = {"-x": (-1, 0, 0), "+x": (1, 0, 0), "-z": (0, 0, -1), "+z": (0, 0, 1)}


def _bool(op, a, b):
    o = op(a, b)
    o.SetFuzzyValue(1e-4)
    o.Build()
    return o.Shape()


def _trsf(shape, tr):
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def _halbraum(p, n):
    """Halbraum {q: (q − p)·n ≥ 0} als großer Quader."""
    ax = gp_Ax3(gp_Pnt(*p), gp_Dir(*n))
    tr = gp_Trsf()
    tr.SetTransformation(ax, gp_Ax3())
    return _trsf(BRepPrimAPI_MakeBox(gp_Pnt(-G, -G, 0), 2 * G, 2 * G, G).Shape(), tr)


def _zylinder(c, w, r):
    p = tuple(c[i] - w[i] * G for i in range(3))
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p), gp_Dir(*w)), r, 2 * G).Shape()


def rohr(a, b, s, rk, y0, y1):
    """Rohr entlang Y von y0 bis y1, Querschnitt a (X) × b (Z)."""
    r = et.kastenrohr(a, b, s, y1 - y0, rk)          # Achse Z, a in X, b in Y
    tr = gp_Trsf()
    tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), -math.pi / 2)     # Z → Y, Y → −Z
    r = _trsf(r, tr)
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(0, y0, 0))
    return _trsf(r, tr)


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _biegung_lokal(bg, y, a, b):
    """Achspunkt C, Achse w, Außenrichtung u einer Biegung am Bogenanfang y (Rahmen des Stücks davor)."""
    u = RICHTUNG[bg["aussen"]]
    h = a / 2 if u[0] else b / 2
    c = (u[0] * (h - bg["r"]), y, u[2] * (h - bg["r"]))
    w = _kreuz((0, 1, 0), u)
    return c, w, u


def _drehung(c, w, winkel):
    tr = gp_Trsf()
    tr.SetRotation(gp_Ax1(gp_Pnt(*c), gp_Dir(*w)), winkel)
    return tr


def gebogen(schenkel, biegungen, a=50.0, b=30.0, s=2.6, rk=5.2, rand=6.0, bohrungen=()):
    """Gebogenes Rohr: schenkel = gerade Längen (eine mehr als Biegungen), biegungen = [dict(winkel, r, aussen)],
    bohrungen = [(Schenkel-Nr., Lage ab Schenkelanfang, Ø, Richtung "x"/"z")]. Ergebnis (Körper, gestreckte Länge)."""
    teile = []
    rahmen = gp_Trsf()
    for i, lg in enumerate(schenkel):
        st = rohr(a, b, s, rk, -G / 10 if i else 0.0, lg + G / 10 if i < len(biegungen) else lg)
        if i > 0:       # Kerbflanke und Streifengrenze der Biegung davor (Bogenende bei y = 0)
            bv = biegungen[i - 1]
            c, w, u = _biegung_lokal(bv, 0.0, a, b)
            th = math.radians(bv["winkel"])
            n = tuple(math.cos(th / 2) * (0, 1, 0)[k] + math.sin(th / 2) * u[k] for k in range(3))
            st = _bool(BRepAlgoAPI_Common, st, _halbraum(tuple(c[k] + n[k] * SPALT / 2 for k in range(3)), n))
            weg = _bool(BRepAlgoAPI_Cut, _halbraum((0, 0, 0), (0, -1, 0)), _zylinder(c, w, bv["r"] - rand))
            st = _bool(BRepAlgoAPI_Cut, st, weg)
        if i < len(biegungen):      # Kerbflanke und Streifengrenze der Biegung danach (Bogenanfang bei y = lg)
            bn = biegungen[i]
            c, w, u = _biegung_lokal(bn, lg, a, b)
            th = math.radians(bn["winkel"])
            n = tuple(-(math.cos(th / 2) * (0, 1, 0)[k] - math.sin(th / 2) * u[k]) for k in range(3))
            st = _bool(BRepAlgoAPI_Common, st, _halbraum(tuple(c[k] + n[k] * SPALT / 2 for k in range(3)), n))
            weg = _bool(BRepAlgoAPI_Cut, _halbraum((0, lg, 0), (0, 1, 0)), _zylinder(c, w, bn["r"] - rand))
            st = _bool(BRepAlgoAPI_Cut, st, weg)
        for nr, lage, d, ri in bohrungen:
            if nr == i:
                achse = (1, 0, 0) if ri == "x" else (0, 0, 1)
                st = _bool(BRepAlgoAPI_Cut, st, _zylinder((0, lage, 0), achse, d / 2))
        teile.append(_trsf(st, rahmen))
        if i < len(biegungen):
            bn = biegungen[i]
            c, w, u = _biegung_lokal(bn, lg, a, b)
            th = math.radians(bn["winkel"])
            teile.append(_trsf(_streifen(a, b, s, rk, lg, c, w, bn["r"], rand, th), rahmen))
            rahmen = rahmen.Multiplied(_drehung(c, w, -th)).Multiplied(_schieben((0, lg, 0)))
    form = teile[0]
    for x in teile[1:]:
        form = _bool(BRepAlgoAPI_Fuse, form, x)
    gestreckt = sum(schenkel) + sum((x["r"] - s / 2) * math.radians(x["winkel"]) for x in biegungen)
    return form, gestreckt


def _schieben(v):
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(*v))
    return tr


def _streifen(a, b, s, rk, y, c, w, r, rand, th):
    """Biegestreifen: Querschnitt des Rohrs bei y (Teil bis rand unter der Außenseite), um (c, w) um −th gedreht."""
    rr = rohr(a, b, s, rk, y - 1, y + 1)
    sec = BRepAlgoAPI_Section(rr, gp_Pln(gp_Pnt(0, y, 0), gp_Dir(0, 1, 0)), False)
    sec.Build()
    kanten = g.TopTools_HSequenceOfShape()
    for e in g._liste(sec.Shape(), TopAbs_EDGE):
        kanten.Append(e)
    ws = ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(kanten, 1e-4, False)
    ws = sorted((TopoDS.Wire(ws.Value(i)) for i in range(1, ws.Length() + 1)),
                key=lambda x: -g._flaeche(BRepBuilderAPI_MakeFace(x, True).Face()))
    mf = BRepBuilderAPI_MakeFace(ws[0], True)
    for x in ws[1:]:
        x.Reverse()
        mf.Add(x)
    rev = BRepPrimAPI_MakeRevol(mf.Face(), gp_Ax1(gp_Pnt(*c), gp_Dir(*(-x for x in w))), th).Shape()
    ring = _bool(BRepAlgoAPI_Cut, _zylinder(c, w, r + 1), _zylinder(c, w, r - rand))
    return _bool(BRepAlgoAPI_Common, rev, ring)
