"""Geometrieauswertung von Rohrlaserteilen aus STEP-Dateien (OpenCascade).

Je Volumenkörper wird ermittelt:
- Rohrachse, Teilelänge (Ausdehnung entlang der Achse)
- Profilform, Abmessungen, Wandstärke, Querschnittsfläche
- Schneidweg: Länge aller Schnittkonturen auf der Außenhaut des Rohrs
- Anzahl Konturen (= Einstiche)

Annahmen:
- Gerades Rohr mit konstantem Querschnitt (nicht gebogen).
- Der Laser schneidet durch die Wand; jede Fläche, die nicht zur Außen- oder
  Innenwand gehört, ist eine Schnittfläche (Enden, Bohrungen, Ausschnitte).
- Der Schneidweg wird auf der Außenhaut gemessen. Beide Endschnitte zählen
  voll je Teil (kein gemeinsamer Trennschnitt).
"""
import math
from dataclasses import dataclass, field

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_OBB, Bnd_Box
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeVertex, BRepBuilderAPI_Transform
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Line
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
try:  # OCP >= 7.8
    from OCP.collections import (IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape,
                                 IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher
                                 as TopTools_IndexedDataMapOfShapeListOfShape,
                                 HSequence_TopoDS_Shape as TopTools_HSequenceOfShape)
except ImportError:  # ältere OCP-Versionen
    from OCP.TopTools import (TopTools_IndexedMapOfShape, TopTools_IndexedDataMapOfShapeListOfShape,
                              TopTools_HSequenceOfShape)
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Pln, gp_Pnt, gp_Dir, gp_Vec, gp_Ax3, gp_Trsf

TOL_WAND = 0.05     # mm, Abstand eines Punkts zur Profilkontur
TOL_PARALLEL = 1e-3


@dataclass
class Teil:
    datei: str
    koerper: int
    profilform: str = ""
    abm_a: float = 0.0          # Ø bzw. Breite
    abm_b: float = 0.0          # Höhe (0 bei Rundrohr)
    wandstaerke: float = 0.0
    flaeche: float = 0.0        # Querschnitt mm²
    laenge: float = 0.0
    schneidweg: float = 0.0
    konturen: int = 0
    hinweise: list = field(default_factory=list)

    @property
    def profil_id_vorschlag(self):
        f = lambda x: (f"{x:.1f}".rstrip("0").rstrip(".")).replace(".", ",")
        if self.profilform == "Rundrohr":
            return f"RR {f(self.abm_a)}x{f(self.wandstaerke)}"
        if self.profilform == "Quadratrohr":
            return f"QR {f(self.abm_a)}x{f(self.abm_a)}x{f(self.wandstaerke)}"
        if self.profilform == "Rechteckrohr":
            return f"RE {f(self.abm_a)}x{f(self.abm_b)}x{f(self.wandstaerke)}"
        return ""


def lies_step(pfad):
    r = STEPControl_Reader()
    if r.ReadFile(str(pfad)) != IFSelect_RetDone:
        raise ValueError(f"STEP-Datei nicht lesbar: {pfad}")
    r.TransferRoots()
    shape = r.OneShape()
    solids = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        solids.append(TopoDS.Solid(ex.Current()))
        ex.Next()
    return solids


def _liste(shape, typ):
    out = []
    ex = TopExp_Explorer(shape, typ)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def _flaeche(shape):
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, p)
    return p.Mass()


def _kantenlaenge(kante):
    return GCPnts_AbscissaPoint.Length_s(BRepAdaptor_Curve(TopoDS.Edge(kante)))


def _vec(d):
    return gp_Vec(d.X(), d.Y(), d.Z())


def _achse(solid):
    """Rohrachse: die OBB-Achse, zu der die meiste Fläche 'parallel extrudiert' ist."""
    obb = Bnd_OBB()
    BRepBndLib.AddOBB_s(solid, obb, False, True, False)
    kandidaten = [obb.XDirection(), obb.YDirection(), obb.ZDirection()]
    best, best_a = None, -1.0
    for k in kandidaten:
        kv = _vec(k)
        a = 0.0
        for f in _liste(solid, TopAbs_FACE):
            s = BRepAdaptor_Surface(TopoDS.Face(f))
            t = s.GetType()
            if t == GeomAbs_Plane:
                if abs(_vec(s.Plane().Axis().Direction()).Dot(kv)) < TOL_PARALLEL:
                    a += _flaeche(f)
            elif t == GeomAbs_Cylinder:
                if abs(abs(_vec(s.Cylinder().Axis().Direction()).Dot(kv)) - 1) < TOL_PARALLEL:
                    a += _flaeche(f)
        if a > best_a:
            best, best_a = k, a
    return best, obb.Center()


def _lokal(solid, achse, zentrum):
    """Transformation in ein System mit Z = Rohrachse."""
    ax3 = gp_Ax3(gp_Pnt(zentrum.X(), zentrum.Y(), zentrum.Z()), gp_Dir(achse.X(), achse.Y(), achse.Z()))
    tr = gp_Trsf()
    tr.SetTransformation(ax3)
    return BRepBuilderAPI_Transform(solid, tr, True).Shape()


def _schnitt(shape, z):
    sec = BRepAlgoAPI_Section(shape, gp_Pln(gp_Pnt(0, 0, z), gp_Dir(0, 0, 1)))
    sec.Build()
    kanten = TopTools_HSequenceOfShape()
    for e in _liste(sec.Shape(), TopAbs_EDGE):
        kanten.Append(e)
    if kanten.Length() == 0:
        return []
    wires = ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(kanten, 1e-4, False)
    out = []
    for i in range(1, wires.Length() + 1):
        w = TopoDS.Wire(wires.Value(i))
        mf = BRepBuilderAPI_MakeFace(w, True)
        if not mf.IsDone():
            continue
        out.append((abs(_flaeche(mf.Face())), w))
    out.sort(key=lambda x: -x[0])
    return out


def _abstand(a, b):
    d = BRepExtrema_DistShapeShape(a, b)
    return d.Value() if d.IsDone() else float("inf")


def analysiere(solid, datei="", koerper=1):
    t = Teil(datei=datei, koerper=koerper)
    achse, zentrum = _achse(solid)
    lok = _lokal(solid, achse, zentrum)

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(lok, box, False, False)
    zmin, zmax = box.CornerMin().Z(), box.CornerMax().Z()
    t.laenge = zmax - zmin

    # Querschnitt: Lage mit größter Netto-Fläche und genau 2 Konturen (Außen/Innen)
    best = None
    for anteil in (0.5, 0.43, 0.57, 0.35, 0.65, 0.27, 0.73, 0.2, 0.8, 0.12, 0.88):
        z = zmin + anteil * t.laenge
        ws = _schnitt(lok, z)
        if len(ws) != 2:
            continue
        netto = ws[0][0] - ws[1][0]
        if best is None or netto > best[0] + 1e-6:
            best = (netto, z, ws)
    if best is None:
        t.hinweise.append("Kein Rohrquerschnitt gefunden (kein Hohlprofil?)")
        return t
    t.flaeche, z0, ws = best
    aussen, innen = ws[0][1], ws[1][1]
    t.wandstaerke = _abstand(aussen, innen)

    # Profilform aus der Außenkontur (Ecken/Kreise können je nach CAD als Kreis, Ellipse oder Spline kommen)
    n_linien = 0
    for e in _liste(aussen, TopAbs_EDGE):
        if BRepAdaptor_Curve(TopoDS.Edge(e)).GetType() == GeomAbs_Line:
            n_linien += 1
    wb = Bnd_Box()
    BRepBndLib.AddOptimal_s(aussen, wb, False, False)
    bx = wb.CornerMax().X() - wb.CornerMin().X()
    by = wb.CornerMax().Y() - wb.CornerMin().Y()
    a, b = max(bx, by), min(bx, by)
    if n_linien == 0 and a - b < 0.1:
        t.profilform, t.abm_a = "Rundrohr", (a + b) / 2
    elif n_linien >= 4 and a - b < 0.1:
        t.profilform, t.abm_a = "Quadratrohr", (a + b) / 2
    elif n_linien >= 4:
        t.profilform, t.abm_a, t.abm_b = "Rechteckrohr", a, b
    else:
        t.profilform, t.abm_a, t.abm_b = "Sonderprofil", a, b
        t.hinweise.append("Profil nicht erkannt, Fläche manuell prüfen")

    # Wandflächen bestimmen: alle Punkte der Fläche liegen (in Z projiziert) auf Außen- bzw. Innenkontur
    def projiziert(p):
        return BRepBuilderAPI_MakeVertex(gp_Pnt(p.X(), p.Y(), z0)).Vertex()

    def punkte(face):
        pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in _liste(face, TopAbs_VERTEX)]
        for e in _liste(face, TopAbs_EDGE):
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            for u in (0.25, 0.5, 0.75):
                pts.append(c.Value(c.FirstParameter() + u * (c.LastParameter() - c.FirstParameter())))
        return pts

    def auf(pts, kontur):
        return all(_abstand(projiziert(p), kontur) < TOL_WAND for p in pts)

    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(lok, TopAbs_FACE, faces)
    art = {}   # Index -> "A" außen, "I" innen, "S" Schnitt
    for i in range(1, faces.Extent() + 1):
        f = faces.FindKey(i)
        pts = punkte(f)
        if auf(pts, aussen):
            art[i] = "A"
        elif auf(pts, innen):
            art[i] = "I"
        else:
            art[i] = "S"

    kf = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(lok, TopAbs_EDGE, TopAbs_FACE, kf)
    vmap = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(lok, TopAbs_VERTEX, vmap)
    schnittkanten = []
    for i in range(1, kf.Extent() + 1):
        e = kf.FindKey(i)
        arten = {art[faces.FindIndex(f)] for f in kf.FindFromIndex(i)}
        if "A" in arten and "S" in arten:
            schnittkanten.append(e)
    t.schneidweg = sum(_kantenlaenge(e) for e in schnittkanten)

    # Konturen zählen: zusammenhängende Kantenzüge über gemeinsame Eckpunkte
    eltern = {}

    def finde(x):
        while eltern.setdefault(x, x) != x:
            eltern[x] = eltern[eltern[x]]
            x = eltern[x]
        return x

    for e in schnittkanten:
        vs = [vmap.FindIndex(v) for v in _liste(e, TopAbs_VERTEX)]
        for v in vs[1:]:
            eltern[finde(vs[0])] = finde(v)
        finde(vs[0])
    t.konturen = len({finde(v) for v in list(eltern)})
    return t


def analysiere_datei(pfad):
    from pathlib import Path
    name = Path(pfad).stem
    solids = lies_step(pfad)
    if not solids:
        t = Teil(datei=name, koerper=0)
        t.hinweise.append("Kein Volumenkörper in der Datei")
        return [t]
    return [analysiere(s, name, i) for i, s in enumerate(solids, start=1)]
