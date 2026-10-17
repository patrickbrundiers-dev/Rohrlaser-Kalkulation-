"""Geometrieauswertung von Rohrlaserteilen aus STEP-Dateien (OpenCascade).

Je Volumenkörper wird ermittelt:
- Rohrachse, Teilelänge (Ausdehnung entlang der Achse)
- Profilform, Abmessungen, Wandstärke, Querschnittsfläche
- Schneidweg getrennt nach Anfangsschnitt (Ende A), Endschnitt (Ende B) und
  Innenkonturen; Gravuren (nicht durchgehend) separat
- Anzahl Konturen (= Einstiche, ohne Gravur), Rundbohrungen je Durchmesser
- Innenkonturen je Kontur mit Größe (größtes Hüllmaß) für die Einteilung klein/mittel/groß

Annahmen:
- Gerades Rohr mit konstantem Querschnitt (nicht gebogen).
- Jede Fläche, die nicht zur Außen- oder Innenwand gehört, gehört zu einem
  Merkmal. Reicht das Merkmal bis zur Innenwand, ist es ein Schnitt
  (Enden, Bohrungen, Ausschnitte), sonst eine Gravur.
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

# ISO-Regelgewinde: Kernlochbohrung nach DIN 336 (bearbeitbar im Blatt 'Gewinde' der Mappe)
KERNLOCH = [("M3", 2.5), ("M4", 3.3), ("M5", 4.2), ("M6", 5.0), ("M8", 6.8), ("M10", 8.5),
            ("M12", 10.2), ("M14", 12.0), ("M16", 14.0), ("M20", 17.5)]

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
    ende_a: float = 0.0         # Schnittlänge Ende A (Anfang, kleineres Achsmaß) [mm]
    ende_a_gerade: bool = False # Ende A ist ein gerader Schnitt (senkrecht zur Achse)
    ende_b: float = 0.0
    ende_b_gerade: bool = False
    innen: float = 0.0          # Schneidweg aller Innenkonturen (Bohrungen, Ausschnitte)
    innen_konturen: int = 0
    gravur: float = 0.0         # Konturlänge nicht durchgehender Merkmale (Gravur/Markierung)
    gravur_konturen: int = 0
    bohrungen: dict = field(default_factory=dict)  # Ø -> Anzahl (durchgehende Rundbohrungen)
    innen_liste: list = field(default_factory=list)  # je Innenkontur (Größe = größtes Hüllmaß, Länge) [mm]
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
    """Rohrachse: die OBB-Achse, zu der die meiste Fläche 'parallel extrudiert' ist,
    danach exakt aus den Wandflächen nachgeschärft (OBB ist bei unsymmetrischen Teilen leicht schief)."""
    obb = Bnd_OBB()
    BRepBndLib.AddOBB_s(solid, obb, False, True, False)
    TOL_GROB = 0.02
    flaechen = []
    for f in _liste(solid, TopAbs_FACE):
        s = BRepAdaptor_Surface(TopoDS.Face(f))
        if s.GetType() == GeomAbs_Plane:
            flaechen.append(("P", _vec(s.Plane().Axis().Direction()), _flaeche(f)))
        elif s.GetType() == GeomAbs_Cylinder:
            flaechen.append(("Z", _vec(s.Cylinder().Axis().Direction()), _flaeche(f)))
    best, best_a = None, -1.0
    for k in (obb.XDirection(), obb.YDirection(), obb.ZDirection()):
        kv = _vec(k)
        a = sum(fl for typ, d, fl in flaechen
                if (typ == "P" and abs(d.Dot(kv)) < TOL_GROB) or (typ == "Z" and abs(abs(d.Dot(kv)) - 1) < TOL_GROB))
        if a > best_a:
            best, best_a = kv, a
    # Nachschärfen: größte parallele Zylinderwand, sonst Kreuzprodukt der zwei größten nicht parallelen Wandebenen
    zyl = sorted([(fl, d) for typ, d, fl in flaechen if typ == "Z" and abs(abs(d.Dot(best)) - 1) < TOL_GROB],
                 key=lambda x: -x[0])
    if zyl:
        achse = zyl[0][1]
    else:
        ebenen = sorted([(fl, d) for typ, d, fl in flaechen if typ == "P" and abs(d.Dot(best)) < TOL_GROB],
                        key=lambda x: -x[0])
        achse = best
        for _, d2 in ebenen[1:]:
            kreuz = ebenen[0][1].Crossed(d2)
            if kreuz.Magnitude() > 0.5:
                achse = kreuz
                break
    achse = achse.Normalized()
    if achse.Dot(best) < 0:
        achse.Reverse()
    return achse, obb.Center()


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
    # dicht über die ganze Länge abtasten, damit auch lange Ausschnitte umgangen werden
    # krumme Anteile, damit die Ebene nicht genau auf einer Merkmalskante liegt
    for anteil in [0.5037] + [(i + 0.37) / 50 for i in range(1, 49)]:
        z = zmin + anteil * t.laenge
        ws = _schnitt(lok, z)
        if len(ws) != 2:
            continue
        netto = ws[0][0] - ws[1][0]
        if best is None or netto > best[0] * 1.001:
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

    # Merkmale = zusammenhängende Schnittflächen (über gemeinsame Kanten)
    eltern = {}

    def finde(x):
        while eltern.setdefault(x, x) != x:
            eltern[x] = eltern[eltern[x]]
            x = eltern[x]
        return x

    kanten_info = []   # (Kante, Menge Flächenindizes)
    for i in range(1, kf.Extent() + 1):
        fi = {faces.FindIndex(f) for f in kf.FindFromIndex(i)}
        kanten_info.append((kf.FindKey(i), fi))
        s_faces = [f for f in fi if art[f] == "S"]
        for f in s_faces:
            finde(f)
            if f != s_faces[0]:
                eltern[finde(f)] = finde(s_faces[0])

    merkmale = {}  # Wurzel -> dict(faces, aussenkanten, durch)
    for f, a_ in art.items():
        if a_ == "S":
            merkmale.setdefault(finde(f), dict(faces=[], kanten=[], durch=False))["faces"].append(f)
    for e, fi in kanten_info:
        arten = {art[f] for f in fi}
        for f in fi:
            if art[f] == "S":
                m = merkmale[finde(f)]
                if "A" in arten:
                    m["kanten"].append(e)
                if "I" in arten:
                    m["durch"] = True

    def konturzuege(kanten):
        """Kanten zu geschlossenen Konturzügen gruppieren (über gemeinsame Eckpunkte)."""
        ve = {}

        def fv(x):
            while ve.setdefault(x, x) != x:
                ve[x] = ve[ve[x]]
                x = ve[x]
            return x
        for e in kanten:
            vs = [vmap.FindIndex(v) for v in _liste(e, TopAbs_VERTEX)]
            for v in vs:
                ve[fv(v)] = fv(vs[0])
        zuege = {}
        for e in kanten:
            zuege.setdefault(fv(vmap.FindIndex(_liste(e, TopAbs_VERTEX)[0])), []).append(e)
        return list(zuege.values())

    def konturen_zaehlen(kanten):
        return len(konturzuege(kanten))

    TOL_Z = 0.01
    bohrungen = {}
    for m in merkmale.values():
        kanten = m["kanten"]
        if not kanten:
            continue
        laenge = sum(_kantenlaenge(e) for e in kanten)
        n = konturen_zaehlen(kanten)
        if not m["durch"]:
            t.gravur += laenge
            t.gravur_konturen += n
            continue
        bb = Bnd_Box()
        for e in kanten:
            BRepBndLib.AddOptimal_s(e, bb, False, False)
        gz0, gz1 = bb.CornerMin().Z(), bb.CornerMax().Z()
        if gz0 - zmin < TOL_Z:
            t.ende_a += laenge
            t.ende_a_gerade = (gz1 - zmin < TOL_Z) if t.ende_a == laenge else False
        elif zmax - gz1 < TOL_Z:
            t.ende_b += laenge
            t.ende_b_gerade = (zmax - gz0 < TOL_Z) if t.ende_b == laenge else False
        else:
            t.innen += laenge
            t.innen_konturen += n
            for zug in konturzuege(kanten):
                zb = Bnd_Box()
                for e in zug:
                    BRepBndLib.AddOptimal_s(e, zb, False, False)
                mn, mx = zb.CornerMin(), zb.CornerMax()
                groesse = max(mx.X() - mn.X(), mx.Y() - mn.Y(), mx.Z() - mn.Z())
                t.innen_liste.append((groesse, sum(_kantenlaenge(e) for e in zug)))
            # Rundbohrung: nur Zylinderflächen gleichen Radius, Achse quer zum Rohr
            radien = set()
            for f in m["faces"]:
                sf = BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(f)))
                if sf.GetType() != GeomAbs_Cylinder or abs(sf.Cylinder().Axis().Direction().Z()) > 0.99:
                    radien = None
                    break
                radien.add(round(sf.Cylinder().Radius(), 2))
            if radien and len(radien) == 1:
                d = round(2 * radien.pop(), 2)
                bohrungen[d] = bohrungen.get(d, 0) + n
        t.konturen += n
    t.bohrungen = dict(sorted(bohrungen.items()))
    t.schneidweg = t.ende_a + t.ende_b + t.innen
    return t


def gewinde_vorschlag(bohrungen, tabelle=None, tol=0.05):
    """Ordnet Bohrungsdurchmesser einem Kernloch zu. Ergebnis z. B. '4xM6' (so in Auftrag AG übernehmbar). Nur Vorschlag."""
    tabelle = tabelle or KERNLOCH
    out = []
    for d, n in bohrungen.items():
        for gew, kern in tabelle:
            if abs(d - kern) <= tol:
                out.append(f"{n}x{gew}")
                break
    return "; ".join(out)


# Vorgabe Konturklassen, wenn im Blatt 'Maschinen' nichts eingetragen ist
KLEIN_BIS, MITTEL_BIS = 10.0, 50.0


def konturklassen(innen_liste, klein_bis=KLEIN_BIS, mittel_bis=MITTEL_BIS):
    """Teilt Innenkonturen nach Größe (größtes Hüllmaß) ein: klein ≤ klein_bis < mittel ≤ mittel_bis < groß.
    Ergebnis: {'klein': (Anzahl, Länge), 'mittel': ..., 'gross': ...}"""
    out = {"klein": [0, 0.0], "mittel": [0, 0.0], "gross": [0, 0.0]}
    for groesse, laenge in innen_liste:
        groesse = round(groesse, 2)  # Ø10 genau auf der Grenze zählt als klein
        k = "klein" if groesse <= klein_bis else "mittel" if groesse <= mittel_bis else "gross"
        out[k][0] += 1
        out[k][1] += laenge
    return {k: tuple(v) for k, v in out.items()}


def bohrungen_text(bohrungen):
    return "; ".join(f"{n}xØ{f'{d:g}'.replace('.', ',')}" for d, n in bohrungen.items())


def analysiere_datei(pfad):
    from pathlib import Path
    name = Path(pfad).stem
    solids = lies_step(pfad)
    if not solids:
        t = Teil(datei=name, koerper=0)
        t.hinweise.append("Kein Volumenkörper in der Datei")
        return [t]
    return [analysiere(s, name, i) for i, s in enumerate(solids, start=1)]
