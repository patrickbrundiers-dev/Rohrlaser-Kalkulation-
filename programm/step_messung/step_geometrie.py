"""Geometrieauswertung von Rohrlaserteilen aus STEP-Dateien (OpenCascade).

Je Volumenkörper wird ermittelt:
- Rohrachse, Teilelänge (Ausdehnung entlang der Achse)
- Profilform, Abmessungen, Wandstärke, Querschnittsfläche
- Schneidweg getrennt nach Anfangsschnitt (Ende A), Endschnitt (Ende B) und
  Innenkonturen; Gravuren (nicht durchgehend) separat
- Anzahl Konturen (= Einstiche, ohne Gravur), Rundbohrungen je Durchmesser
- Innenkonturen je Kontur mit Größe (größtes Hüllmaß) für die Einteilung klein/mittel/groß
- auf Wunsch (netz=True) ein Dreiecksnetz für die 3D-Ansicht im Programm: Flächen und Schnittkonturen nach Art
  (Außenwand, Innenwand, Anfangsschnitt, Endschnitt, Innenkontur, Gravur), Rohrachse = Z ab 0

Lokales Rohrkoordinatensystem (_lage): Z = Rohrachse, Ursprung auf der Schwerlinie des Querschnitts, X = Breite
(längere Seite des kleinsten umschreibenden Rechtecks), Y = Höhe. Die Achse kommt aus den Flächennormalen eines
groben Netzes, damit sie auch bei Freiformflächen (B-Spline) und beliebiger Lage im Raum stimmt.

Annahmen:
- Gerades Rohr mit konstantem Querschnitt (nicht gebogen).
- Schnitt- und Merkmalsflächen sind zusammen kleiner als der Außenmantel; sonst gilt die Erkennung als unsicher
  und es werden keine Maße ausgegeben.
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
from OCP.Bnd import Bnd_Box
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_BSplineSurface, GeomAbs_BezierSurface
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

# ISO-Regelgewinde: Kernlochbohrung nach DIN 336 (Vorgabe; im Programm gelten die Stammdaten 'Gewinde')
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
    netz: dict = None           # 3D-Ansicht: {p: [x, y, z, …], t: {Art: [i, j, k, …]}, l: {Art: [[x, y, z, …], …]}}

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


def _netz_dreiecke(shape, abw):
    """Dreiecke eines groben Netzes als (Fläche, Normale). Unabhängig davon, wie das CAD die Flächen speichert
    (Ebene, Zylinder oder Freiformfläche). Das Netz wird danach wieder entfernt."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.TopLoc import TopLoc_Location
    BRepMesh_IncrementalMesh(shape, abw, False, 0.3, True)
    out = []
    for f in _liste(shape, TopAbs_FACE):
        ort = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(TopoDS.Face(f), ort)
        if tri is None:
            continue
        tr = ort.Transformation()
        p = [None] + [tri.Node(j).Transformed(tr) for j in range(1, tri.NbNodes() + 1)]
        for j in range(1, tri.NbTriangles() + 1):
            i1, i2, i3 = tri.Triangle(j).Get()
            n = gp_Vec(p[i1], p[i2]).Crossed(gp_Vec(p[i1], p[i3]))
            m = n.Magnitude()
            if m > 1e-12:
                out.append((m / 2, n.Divided(m)))
    BRepTools.Clean_s(shape)
    return out


def _eigen3(m):
    """Eigenwerte und -vektoren (Spalten) einer symmetrischen 3x3-Matrix (Jacobi-Verfahren)."""
    a = [list(r) for r in m]
    v = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    for _ in range(60):
        p, q = max(((0, 1), (0, 2), (1, 2)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) <= 1e-14 * (abs(a[0][0]) + abs(a[1][1]) + abs(a[2][2])) + 1e-300:
            break
        th = (a[q][q] - a[p][p]) / (2 * a[p][q])
        tt = (1 if th >= 0 else -1) / (abs(th) + math.sqrt(th * th + 1))
        c = 1 / math.sqrt(tt * tt + 1)
        s = tt * c
        j = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        j[p][p], j[q][q], j[p][q], j[q][p] = c, c, s, -s
        a = [[sum(j[k][i] * a[k][l] * j[l][jj] for k in range(3) for l in range(3)) for jj in range(3)]
             for i in range(3)]
        v = [[sum(v[i][k] * j[k][jj] for k in range(3)) for jj in range(3)] for i in range(3)]
    return [a[i][i] for i in range(3)], v


def _achse_grob(solid):
    """Rohrachse aus den Flächennormalen: Mantelflächen (außen, innen) stehen parallel zur Achse, ihre Normalen
    also senkrecht dazu. Die Achse ist die Richtung, zu der die Normalen (flächengewichtet) am wenigsten zeigen
    = Eigenvektor zum kleinsten Eigenwert von Σ Fläche·n·nᵀ. Funktioniert auch bei Freiformflächen."""
    box = Bnd_Box()
    BRepBndLib.Add_s(solid, box, False)
    p0, p1 = box.CornerMin(), box.CornerMax()
    diag = p0.Distance(p1)
    tris = _netz_dreiecke(solid, max(0.01, diag / 2000))
    m = [[0.0] * 3 for _ in range(3)]
    for fl, n in tris:
        k = (n.X(), n.Y(), n.Z())
        for i in range(3):
            for j in range(3):
                m[i][j] += fl * k[i] * k[j]
    werte, vek = _eigen3(m)
    i = min(range(3), key=lambda k: werte[k])
    achse = gp_Vec(vek[0][i], vek[1][i], vek[2][i]).Normalized()
    mitte = gp_Pnt((p0.X() + p1.X()) / 2, (p0.Y() + p1.Y()) / 2, (p0.Z() + p1.Z()) / 2)
    return achse, mitte


def _transformiere(shape, ax3):
    """Shape in das System ax3 (Z = Rohrachse) umrechnen."""
    tr = gp_Trsf()
    tr.SetTransformation(ax3)
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def _global(ax3, x, y, z):
    """Lokale Koordinaten in ax3 als globaler Punkt."""
    o, dx, dy, dz = ax3.Location(), ax3.XDirection(), ax3.YDirection(), ax3.Direction()
    return gp_Pnt(o.X() + x * dx.X() + y * dy.X() + z * dz.X(), o.Y() + x * dx.Y() + y * dy.Y() + z * dz.Y(),
                  o.Z() + x * dx.Z() + y * dy.Z() + z * dz.Z())


def _z_bereich(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    return box.CornerMin().Z(), box.CornerMax().Z()


def _schnitt(shape, z):
    """Konturen der Schnittebene Z = z, größte zuerst: Liste (Fläche, Draht, Schwerpunkt x, y)."""
    sec = BRepAlgoAPI_Section(shape, gp_Pln(gp_Pnt(0, 0, z), gp_Dir(0, 0, 1)), False)
    sec.SetRunParallel(True)   # Freiformflächen schneiden ist langsam
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
        p = GProp_GProps()
        BRepGProp.SurfaceProperties_s(mf.Face(), p)
        c = p.CentreOfMass()
        out.append((abs(p.Mass()), w, c.X(), c.Y()))
    out.sort(key=lambda x: -x[0])
    return out


def _querschnitt_daten(ws):
    """Netto-Fläche und Schwerpunkt eines Schnitts (größte Kontur außen, alle anderen innen)."""
    netto = ws[0][0] - sum(w[0] for w in ws[1:])
    if netto <= 0:
        return 0.0, 0.0, 0.0
    sx = ws[0][0] * ws[0][2] - sum(w[0] * w[2] for w in ws[1:])
    sy = ws[0][0] * ws[0][3] - sum(w[0] * w[3] for w in ws[1:])
    return netto, sx / netto, sy / netto


def _regelquerschnitt(lok, zmin, zmax, n=7):
    """Schnitte an n Stellen; die häufigste Kombination aus Konturanzahl und Fläche ist der Regelquerschnitt
    (Schnitte durch Bohrungen o. ä. weichen ab). Ergebnis: Liste (z, Konturen, Fläche, Schwerpunkt x, y)."""
    schnitte = []
    for i in range(n):
        z = zmin + (i + 0.537) / (n + 0.1) * (zmax - zmin)
        ws = _schnitt(lok, z)
        if ws:
            netto, cx, cy = _querschnitt_daten(ws)
            if netto > 0:
                schnitte.append((z, ws, netto, cx, cy))
    gruppen = []
    for s in schnitte:
        for g in gruppen:
            if len(g[0][1]) == len(s[1]) and abs(g[0][2] - s[2]) <= 0.002 * g[0][2]:
                g.append(s)
                break
        else:
            gruppen.append([s])
    if not gruppen:
        return []
    return max(gruppen, key=lambda g: (len(g), g[0][2]))


def _min_rechteck(pts):
    """Drehwinkel des flächenkleinsten umschreibenden Rechtecks (über die konvexe Hülle)."""
    pts = sorted(set((round(x, 6), round(y, 6)) for x, y in pts))
    if len(pts) < 3:
        return 0.0

    def kreuz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    unten, oben = [], []
    for p in pts:
        while len(unten) >= 2 and kreuz(unten[-2], unten[-1], p) <= 0:
            unten.pop()
        unten.append(p)
    for p in reversed(pts):
        while len(oben) >= 2 and kreuz(oben[-2], oben[-1], p) <= 0:
            oben.pop()
        oben.append(p)
    huelle = unten[:-1] + oben[:-1]
    best = None
    for i in range(len(huelle)):
        (x1, y1), (x2, y2) = huelle[i], huelle[(i + 1) % len(huelle)]
        w = math.atan2(y2 - y1, x2 - x1)
        c, s = math.cos(w), math.sin(w)
        us = [x * c + y * s for x, y in huelle]
        vs = [-x * s + y * c for x, y in huelle]
        du, dv = max(us) - min(us), max(vs) - min(vs)
        fl = du * dv
        if best is None or fl < best[0] - 1e-9:
            best = (fl, w if du >= dv else w + math.pi / 2)
    return best[1]


def _strecken(draht, schritt=0.5):
    """Kontur als Polygonzug-Strecken (x1, y1, x2, y2) in der XY-Ebene, Teilung höchstens 'schritt' mm
    (Gerade: 1 mm, damit Punkte auch in der Mitte langer Seiten liegen)."""
    out = []
    for e in _liste(draht, TopAbs_EDGE):
        c = BRepAdaptor_Curve(TopoDS.Edge(e))
        lg = _kantenlaenge(e)
        n = max(2, min(2000, int(lg / (1.0 if c.GetType() == GeomAbs_Line else schritt)) + 1))
        u0, u1 = c.FirstParameter(), c.LastParameter()
        q = [c.Value(u0 + (u1 - u0) * k / n) for k in range(n + 1)]
        out += [(a.X(), a.Y(), b.X(), b.Y()) for a, b in zip(q, q[1:])]
    return out


def _abst_strecke(x, y, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    ll = dx * dx + dy * dy
    u = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / ll))
    return math.hypot(x - x1 - u * dx, y - y1 - u * dy)


def _abstand_zug(x, y, strecken):
    return min(_abst_strecke(x, y, s) for s in strecken)


def _nah_zug(x, y, strecken, tol):
    return any(_abst_strecke(x, y, s) < tol for s in strecken)


def _zylinder(face, tol=1e-3):
    """Zylinder (gp_Cylinder) einer Fläche oder None. Freiformflächen werden versuchsweise in einen Zylinder
    umgerechnet (Abweichung höchstens tol mm), weil manche CAD-Systeme auch Bohrungen als B-Spline exportieren."""
    sf = BRepAdaptor_Surface(TopoDS.Face(face))
    if sf.GetType() == GeomAbs_Cylinder:
        return sf.Cylinder()
    if sf.GetType() not in (GeomAbs_BSplineSurface, GeomAbs_BezierSurface):
        return None
    from OCP.GeomConvert import GeomConvert_SurfToAnaSurf
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    ana = GeomConvert_SurfToAnaSurf(BRep_Tool.Surface_s(TopoDS.Face(face))).ConvertToAnalytical(tol)
    if ana is None:
        return None
    ga = GeomAdaptor_Surface(ana)
    return ga.Cylinder() if ga.GetType() == GeomAbs_Cylinder else None


def _wandstaerke(aussen, innen, s_aussen, s_innen, z0):
    """Kleinster Abstand zwischen Außen- und Innenkontur. Der exakte Abstand Kontur–Kontur hängt bei gleichmittigen
    Freiformkurven (unendlich viele kürzeste Verbindungen), darum: Kandidaten über die Polygonzüge suchen und für die
    nächstgelegenen Punkte den exakten Abstand Punkt–Kontur rechnen."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    werte = []
    for von, nach, draht in ((s_aussen, s_innen, innen), (s_innen, s_aussen, aussen)):
        kand = sorted((_abstand_zug(s[0], s[1], nach), s[0], s[1]) for s in von)[:5]
        for _, x, y in kand:
            d = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(x, y, z0)).Vertex(), draht)
            if d.IsDone():
                werte.append(d.Value())
    return min(werte) if werte else 0.0


def _lage(solid):
    """Lokales Rohrkoordinatensystem: Z = Rohrachse, Ursprung auf der Schwerlinie des Regelquerschnitts,
    X = Richtung der längeren Seite des kleinsten umschreibenden Rechtecks (Breite), Y = Höhe.
    1. grobe Achse aus den Flächennormalen, 2. zweimal nachschärfen über die Schwerpunkte von zwei weit
    auseinanderliegenden Regelquerschnitten (bei konstantem Querschnitt liegen sie auf einer achsparallelen Linie),
    3. Drehung um die Achse aus dem Querschnitt. Ergebnis: (gp_Ax3, Regelquerschnitt im neuen System)."""
    achse, mitte = _achse_grob(solid)
    ax3 = gp_Ax3(mitte, gp_Dir(achse.X(), achse.Y(), achse.Z()))
    gruppe = []
    for _ in range(3):
        lok = _transformiere(solid, ax3)
        zmin, zmax = _z_bereich(lok)
        gruppe = _regelquerschnitt(lok, zmin, zmax)
        if len(gruppe) < 2 or gruppe[-1][0] - gruppe[0][0] < 0.2 * (zmax - zmin):
            break
        (z1, _, _, x1, y1), (z2, _, _, x2, y2) = gruppe[0], gruppe[-1]
        dx, dy = (x2 - x1) / (z2 - z1), (y2 - y1) / (z2 - z1)
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            break
        p1 = _global(ax3, x1, y1, z1)
        g = _vec(ax3.XDirection()).Multiplied(dx).Added(_vec(ax3.YDirection()).Multiplied(dy)).Added(
            _vec(ax3.Direction()))
        ax3 = gp_Ax3(p1, gp_Dir(g.X(), g.Y(), g.Z()))
    if not gruppe:
        return ax3, []
    mitte_g = min(gruppe, key=lambda s: abs(s[0] - (gruppe[0][0] + gruppe[-1][0]) / 2))
    z, ws, _, cx, cy = mitte_g
    pts = [(s[0], s[1]) for s in _strecken(ws[0][1])]
    w = _min_rechteck(pts)
    o = _global(ax3, cx, cy, z)
    xr = _vec(ax3.XDirection()).Multiplied(math.cos(w)).Added(_vec(ax3.YDirection()).Multiplied(math.sin(w)))
    ax3 = gp_Ax3(o, ax3.Direction(), gp_Dir(xr.X(), xr.Y(), xr.Z()))
    return ax3, gruppe


def _profilform(aussen, a, b, tol=0.05):
    """Form der Außenkontur (im ausgerichteten System, Mitte ≈ 0): Kreis = alle Punkte gleich weit von der Mitte,
    Rechteck = die vier Seiten der Hülle sind mit geraden Abschnitten belegt (Ecken dürfen gerundet sein)."""
    st = _strecken(aussen)
    xs = [s[0] for s in st]
    ys = [s[1] for s in st]
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    r = [math.hypot(x - mx, y - my) for x, y in zip(xs, ys)]
    if max(r) - min(r) < 2 * tol:
        return "Kreis"
    belegt = [0.0] * 4
    gesamt = 0.0
    for x1, y1, x2, y2 in st:
        lg = math.hypot(x2 - x1, y2 - y1)
        gesamt += lg
        for k, (u1, u2, grenze) in enumerate(((x1, x2, a / 2), (x1, x2, -a / 2), (y1, y2, b / 2), (y1, y2, -b / 2))):
            if abs(u1 - (mx if k < 2 else my) - grenze) < tol and abs(u2 - (mx if k < 2 else my) - grenze) < tol:
                belegt[k] += lg
    if gesamt > 0 and sum(belegt) >= 0.5 * gesamt and min(belegt[0:2]) >= 0.1 * b and min(belegt[2:4]) >= 0.1 * a:
        return "Rechteck"
    return ""


def analysiere(solid, datei="", koerper=1, netz=False):
    t = Teil(datei=datei, koerper=koerper)
    ax3, _ = _lage(solid)
    lok = _transformiere(solid, ax3)

    zmin, zmax = _z_bereich(lok)
    t.laenge = zmax - zmin

    # Querschnitt: Lage mit größter Netto-Fläche und genau 2 Konturen (Außen/Innen)
    best, treffer = None, 0
    # bis zu 49 Lagen über die ganze Länge, damit auch lange Ausschnitte umgangen werden; krumme Anteile, damit die
    # Ebene nicht genau auf einer Merkmalskante liegt. Von der Mitte nach außen; sobald drei Lagen den größten
    # Querschnitt zeigen, ist er gefunden (ein Schnitt durch ein Merkmal hat weniger Fläche oder mehr Konturen).
    for anteil in sorted([0.5037] + [(i + 0.37) / 50 for i in range(1, 49)], key=lambda a: abs(a - 0.5037)):
        z = zmin + anteil * t.laenge
        ws = _schnitt(lok, z)
        if len(ws) != 2:
            continue
        netto = ws[0][0] - ws[1][0]
        if best is None or netto > best[0] * 1.001:
            best, treffer = (netto, z, ws), 1
        elif netto >= best[0] * 0.999:
            treffer += 1
        if treffer >= 3:
            break
    if best is None:
        t.hinweise.append("Kein Rohrquerschnitt gefunden (kein Hohlprofil?)")
        return t
    t.flaeche, z0, ws = best
    aussen, innen = ws[0][1], ws[1][1]
    s_aussen, s_innen = _strecken(aussen), _strecken(innen)
    t.wandstaerke = _wandstaerke(aussen, innen, s_aussen, s_innen, z0)

    # Profilform aus der Außenkontur (Ecken/Kreise können je nach CAD als Kreis, Ellipse, Spline oder Freiform-
    # kurve kommen, darum geometrisch statt über Kurventypen)
    wb = Bnd_Box()
    BRepBndLib.AddOptimal_s(aussen, wb, False, False)
    bx = wb.CornerMax().X() - wb.CornerMin().X()
    by = wb.CornerMax().Y() - wb.CornerMin().Y()
    a, b = max(bx, by), min(bx, by)
    form = _profilform(aussen, bx, by)
    if form == "Kreis" and a - b < 0.1:
        t.profilform, t.abm_a = "Rundrohr", (a + b) / 2
    elif form == "Rechteck" and a - b < 0.1:
        t.profilform, t.abm_a = "Quadratrohr", (a + b) / 2
    elif form == "Rechteck":
        t.profilform, t.abm_a, t.abm_b = "Rechteckrohr", a, b
    else:
        t.profilform, t.abm_a, t.abm_b = "Sonderprofil", a, b
        t.hinweise.append("Profil nicht erkannt, Fläche manuell prüfen")

    # Wandflächen bestimmen: alle Punkte der Fläche liegen (in Z projiziert) auf Außen- bzw. Innenkontur
    def punkte(face):
        pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in _liste(face, TopAbs_VERTEX)]
        for e in _liste(face, TopAbs_EDGE):
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            for u in (0.25, 0.5, 0.75):
                pts.append(c.Value(c.FirstParameter() + u * (c.LastParameter() - c.FirstParameter())))
        return pts

    def auf(pts, strecken):
        return all(_nah_zug(p.X(), p.Y(), strecken, TOL_WAND) for p in pts)

    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(lok, TopAbs_FACE, faces)
    art = {}   # Index -> "A" außen, "I" innen, "S" Schnitt
    flaeche_art = {"A": 0.0, "I": 0.0, "S": 0.0}
    for i in range(1, faces.Extent() + 1):
        f = faces.FindKey(i)
        pts = punkte(f)
        if auf(pts, s_aussen):
            art[i] = "A"
        elif auf(pts, s_innen):
            art[i] = "I"
        else:
            art[i] = "S"
        flaeche_art[art[i]] += _flaeche(f)
    # Gegenprobe: Schnitt- und Merkmalsflächen sind bei einem Rohrteil viel kleiner als der Außenmantel. Sonst ist
    # die Lage falsch erkannt (z. B. der Mantel als Schnittkontur) – dann lieber keine Maße als falsche.
    if flaeche_art["S"] > flaeche_art["A"]:
        u = Teil(datei=datei, koerper=koerper)
        u.hinweise.append("Erkennung unsicher: Schnittflächen größer als der Außenmantel, keine Maße übernommen. "
                          "Teil bitte prüfen.")
        return u

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
            m["art"] = "G"
            t.gravur += laenge
            t.gravur_konturen += n
            continue
        bb = Bnd_Box()
        for e in kanten:
            BRepBndLib.AddOptimal_s(e, bb, False, False)
        gz0, gz1 = bb.CornerMin().Z(), bb.CornerMax().Z()
        m["art"] = "EA" if gz0 - zmin < TOL_Z else "EB" if zmax - gz1 < TOL_Z else "K"
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
                zyl = _zylinder(faces.FindKey(f))
                if zyl is None or abs(zyl.Axis().Direction().Z()) > 0.99:
                    radien = None
                    break
                radien.add(round(zyl.Radius(), 2))
            if radien and len(radien) == 1:
                d = round(2 * radien.pop(), 2)
                bohrungen[d] = bohrungen.get(d, 0) + n
        t.konturen += n
    t.bohrungen = dict(sorted(bohrungen.items()))
    t.schneidweg = t.ende_a + t.ende_b + t.innen
    if netz:
        art_flaeche = dict(art)
        for m in merkmale.values():
            for f in m["faces"]:
                art_flaeche[f] = m.get("art", "K")
        t.netz = dreiecksnetz(lok, faces, art_flaeche, [(m.get("art", "K"), m["kanten"]) for m in merkmale.values()],
                              zmin, max(t.abm_a, t.abm_b))
    return t


NETZ_ARTEN = {"A": "Außenwand", "I": "Innenwand", "EA": "Anfangsschnitt", "EB": "Endschnitt", "K": "Innenkontur",
              "G": "Gravur"}


def dreiecksnetz(lok, faces, art_flaeche, konturen, zmin, groesse):
    """Dreiecksnetz des Teils (lokal, Rohrachse = Z, Z ab 0) mit der Art je Fläche und den Schnittkonturen auf der
    Außenhaut als Linienzüge. Koordinaten auf 0,01 mm gerundet."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopAbs import TopAbs_REVERSED
    abw = min(0.5, max(0.02, (groesse or 40) / 250))
    BRepMesh_IncrementalMesh(lok, abw, False, 0.35, True)
    punkte, dreiecke = [], {}
    for i in range(1, faces.Extent() + 1):
        f = TopoDS.Face(faces.FindKey(i))
        ort = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, ort)
        if tri is None:
            continue
        tr = ort.Transformation()
        basis = len(punkte) // 3
        for j in range(1, tri.NbNodes() + 1):
            q = tri.Node(j).Transformed(tr)
            punkte += [round(q.X(), 2), round(q.Y(), 2), round(q.Z() - zmin, 2)]
        umdrehen = f.Orientation() == TopAbs_REVERSED
        liste = dreiecke.setdefault(art_flaeche.get(i, "K"), [])
        for j in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(j).Get()
            liste += [basis + a - 1, basis + c - 1, basis + b - 1] if umdrehen else \
                [basis + a - 1, basis + b - 1, basis + c - 1]
    linien = {}
    for art_, kanten in konturen:
        for e in kanten:
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            u0, u1 = c.FirstParameter(), c.LastParameter()
            n = max(2, min(120, int(_kantenlaenge(e) / max(abw * 4, 0.5)) + 1))
            zug = []
            for k in range(n + 1):
                q = c.Value(u0 + (u1 - u0) * k / n)
                zug += [round(q.X(), 2), round(q.Y(), 2), round(q.Z() - zmin, 2)]
            linien.setdefault(art_, []).append(zug)
    return dict(p=punkte, t=dreiecke, l=linien)


def gewinde_vorschlag(bohrungen, tabelle=None, tol=0.05):
    """Ordnet Bohrungsdurchmesser einem Kernloch zu. Ergebnis z. B. '4xM6' (so in Angebot AG übernehmbar). Nur Vorschlag."""
    tabelle = tabelle or KERNLOCH
    out = []
    for d, n in bohrungen.items():
        for gew, kern in tabelle:
            if abs(d - kern) <= tol:
                out.append(f"{n}x{gew}")
                break
    return "; ".join(out)


# Vorgabe Konturklassen, wenn in den Maschinen-Stammdaten nichts eingetragen ist
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


def analysiere_datei(pfad, netz=False):
    from pathlib import Path
    name = Path(pfad).stem
    solids = lies_step(pfad)
    if not solids:
        t = Teil(datei=name, koerper=0)
        t.hinweise.append("Kein Volumenkörper in der Datei")
        return [t]
    return [analysiere(s, name, i, netz) for i, s in enumerate(solids, start=1)]
