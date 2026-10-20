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
- Offene Profile (U, C, L, Flachstahl): eine Kontur im Querschnitt; Schnittlänge = halbe Länge der Konturkanten
  (der Laser schneidet jede Wand einmal), siehe _offen_konturen.
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
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Line, GeomAbs_BSplineSurface, GeomAbs_BezierSurface
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

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))     # programm/: Normtabellen aus rohrlaser
from rohrlaser import normprofile  # noqa: E402

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
    innen_a: float = 0.0        # Innenmaß Ø bzw. Breite (Hohlprofile)
    innen_b: float = 0.0        # Innenmaß Höhe
    wand_messungen: list = field(default_factory=list)  # je Messstelle (z ab Ende A, x, y, Wert, Seite) [mm]
    sicherheit: dict = field(default_factory=dict)       # je Merkmal: sicher / wahrscheinlich / unsicher / …
    achse_global: tuple = ()    # Richtung der Rohrachse (Ende A -> B) in der Datei, Einheitsvektor
    ende_a_global: tuple = ()   # Mitte von Ende A (Schwerlinie, z = 0) in der Datei [mm]
    konturen_liste: list = field(default_factory=list)  # je Kontur ein dict: Art, Lage (z, Winkel, Seite), Maße
    # Import (je Datei bzw. je Körper)
    einheit: str = ""           # Längeneinheit laut Datei (mm, cm, m, inch, ft); gemessen wird immer in mm
    meldungen: list = field(default_factory=list)  # Meldungen des STEP-Lesers zur Datei
    koerperart: str = ""        # Volumenkörper / aus Flächenmodell genäht / Flächenmodell offen
    gueltig: bool = None        # Geometrieprüfung (OpenCascade) bestanden; None = nicht geprüft
    volumen: float = 0.0        # mm³
    oberflaeche: float = 0.0    # mm²
    n_flaechen: int = 0
    n_kanten: int = 0
    huelle: tuple = ()          # Hüllquader in Dateilage (dx, dy, dz) [mm]
    netz: dict = None           # 3D-Ansicht: {p: [x, y, z, …], t: {Art: [i, j, k, …]}, l: {Art: [[x, y, z, …], …]}}
    bauteiltyp: str = ""        # Profil, Blech oder Blech gekantet ("" = nicht erkannt)
    stegdicke: float = 0.0      # I-/H-Träger, T-Profil (Wandstärke = Stegdicke)
    flanschdicke: float = 0.0   # I-/H-Träger (Mittel beider Flansche), T-Profil
    symmetrisch: bool = None    # Träger: Steg mittig, Flansche gleich
    radius: float = 0.0         # Träger: Ausrundung Steg/Flansch (aus der Fläche, ca.)
    normprofil: str = ""        # zugeordnetes Normprofil (IPE 200, HEB 160, UPN 100, L 50x50x5, T 50) oder leer
    blech: dict = None          # nur Bleche: Länge, Breite, Dicke, Flächen, Kontur, Bohrungen, Fingerabdruck (_blech_daten)

    @property
    def pruefstatus(self):
        """'nicht messbar' (kein Profil erkannt), 'prüfen' (unsichere Merkmale, Hinweise, ungültige Geometrie) oder
        'plausibel'. Plausibel heißt nur: die Messung ist in sich stimmig – keine Fertigungsfreigabe."""
        if not self.profilform or self.laenge <= 0:
            return "nicht messbar"
        if self.hinweise or self.gueltig is False or "unsicher" in self.sicherheit.values() or \
                "Sonderprofil" in self.profilform:
            return "prüfen"
        return "plausibel"

    @property
    def profil_id_vorschlag(self):
        f = lambda x: (f"{x:.1f}".rstrip("0").rstrip(".")).replace(".", ",")
        if self.profilform == "Rundrohr":
            return f"RR {f(self.abm_a)}x{f(self.wandstaerke)}"
        if self.profilform == "Quadratrohr":
            return f"QR {f(self.abm_a)}x{f(self.abm_a)}x{f(self.wandstaerke)}"
        if self.profilform == "Rechteckrohr":
            return f"RE {f(self.abm_a)}x{f(self.abm_b)}x{f(self.wandstaerke)}"
        if self.normprofil and self.profilform in ("U-Profil",) + TRAEGER:
            return self.normprofil
        if self.profilform == "I-/H-Träger":
            return f"I {f(self.abm_a)}x{f(self.abm_b)}x{f(self.stegdicke)}x{f(self.flanschdicke)}"
        if self.profilform == "T-Profil":
            return f"T {f(self.abm_a)}x{f(self.abm_b)}x{f(self.stegdicke)}x{f(self.flanschdicke)}"
        kurz = {"U-Profil": "U", "C-Profil": "C", "L-Profil": "L"}.get(self.profilform)
        if kurz:
            return f"{kurz} {f(self.abm_a)}x{f(self.abm_b)}x{f(self.wandstaerke)}"
        if self.profilform == "Flachstahl":
            return f"FL {f(self.abm_a)}x{f(self.abm_b)}"
        if self.profilform == "Vierkantstahl":
            return f"VK {f(self.abm_a)}"
        if self.profilform == "Rundstahl":
            return f"RD {f(self.abm_a)}"
        return ""


EINHEITEN = {".MILLI.": "mm", ".CENTI.": "cm", ".DECI.": "dm", ".KILO.": "km", "$": "m"}


def _einheit(pfad):
    """Längeneinheit laut STEP-Datei (nur zur Information: OpenCascade rechnet beim Lesen in mm um)."""
    import re
    try:
        text = open(pfad, encoding="latin-1", errors="replace").read()
    except OSError:
        return ""
    text = re.sub(r"\s+", "", text.upper())
    m = re.search(r"CONVERSION_BASED_UNIT\('([^']*)'[^;]*LENGTH_UNIT", text) or \
        re.search(r"LENGTH_UNIT\(\)[^;]*CONVERSION_BASED_UNIT\('([^']*)'", text)
    if m:
        return {"INCH": "inch", "FOOT": "ft"}.get(m.group(1), m.group(1).lower())
    m = re.search(r"LENGTH_UNIT\(\)NAMED_UNIT\(\*\)SI_UNIT\(([^,]*),\.METRE\.\)", text) or \
        re.search(r"SI_UNIT\(([^,]*),\.METRE\.\)[^;]*LENGTH_UNIT", text)
    return EINHEITEN.get(m.group(1), m.group(1)) if m else "unbekannt"


def _konsole_mitschneiden(fn):
    """Führt fn aus und gibt (Ergebnis, Konsolenausgabe) zurück. OpenCascade schreibt Lesefehler direkt auf die
    Konsole (Dateideskriptor 1), nicht über Python."""
    import os
    import re
    import tempfile
    sys_out = None
    try:
        import sys
        sys.stdout.flush()
        sys_out = os.dup(1)
    except (OSError, ValueError):
        return fn(), ""
    with tempfile.TemporaryFile(mode="w+b") as tmp:
        os.dup2(tmp.fileno(), 1)
        try:
            erg = fn()
        finally:
            os.dup2(sys_out, 1)
            os.close(sys_out)
        tmp.seek(0)
        text = tmp.read().decode("utf-8", "replace")
    return erg, re.sub(r"\x1b\[[0-9;]*m", "", text)


def lies_step_info(pfad):
    """Liest eine STEP-Datei. Ergebnis: (Körper, Info). Körper = Liste (Art, Shape) mit Art 'Volumenkörper',
    'aus Flächenmodell genäht' (geschlossene Fläche zu Volumen gemacht) oder 'Flächenmodell offen' (nicht messbar).
    Info: einheit, meldungen (Fehler/Warnungen des Lesers), baugruppe (mehrere Körper). Nichts wird still verworfen:
    alles, was weder Volumenkörper noch nähbar ist, kommt als 'Flächenmodell offen' zurück.
    Wirft ValueError, wenn die Datei nicht lesbar ist."""
    from OCP.IFSelect import IFSelect_RetVoid
    r = STEPControl_Reader()
    status, ausgabe = _konsole_mitschneiden(lambda: r.ReadFile(str(pfad)))
    fehler = [z.strip(" *") for z in ausgabe.splitlines() if "ERR" in z or "Fail" in z]
    if status != IFSelect_RetDone:
        grund = "leer oder kein STEP" if status == IFSelect_RetVoid else "Syntaxfehler"
        raise ValueError(f"STEP-Datei nicht lesbar ({grund})" + (": " + "; ".join(fehler[:3]) if fehler else ""))
    meldungen = list(fehler)
    chk = r.WS().ModelCheckList(False)
    chk.Start()
    while chk.More():
        c = chk.Value()
        meldungen += [f"Fehler: {c.CFail(i)}" for i in range(1, c.NbFails() + 1)]
        meldungen += [f"Warnung: {c.CWarning(i)}" for i in range(1, c.NbWarnings() + 1)]
        chk.Next()
    r.TransferRoots()
    shape = r.OneShape()
    koerper = [("Volumenkörper", TopoDS.Solid(x)) for x in _liste(shape, TopAbs_SOLID)]
    # Flächen außerhalb von Volumenkörpern (Flächenmodelle): zusammennähen, geschlossene Schalen werden Volumen
    lose = []
    ex = TopExp_Explorer(shape, TopAbs_FACE, TopAbs_SOLID)
    while ex.More():
        lose.append(ex.Current())
        ex.Next()
    if lose:
        koerper += _naehen(lose)
    meldungen = list(dict.fromkeys(m for m in meldungen if m))
    return koerper, dict(einheit=_einheit(pfad), meldungen=meldungen[:20], baugruppe=len(koerper) > 1)


def _naehen(flaechen, tol=0.01):
    """Lose Flächen zu Schalen nähen; geschlossene Schalen werden Volumenkörper."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.BRepCheck import BRepCheck_Analyzer
    naht = BRepBuilderAPI_Sewing(tol)
    for f in flaechen:
        naht.Add(f)
    naht.Perform()
    erg = naht.SewedShape()
    out = []
    schalen = _liste(erg, TopAbs_SHELL)
    for sh in schalen:
        sh = TopoDS.Shell(sh)
        if BRep_Tool.IsClosed_s(sh):
            ms = BRepBuilderAPI_MakeSolid(sh)
            if ms.IsDone():
                fix = ShapeFix_Solid(ms.Solid())
                fix.Perform()
                sol = _liste(fix.Shape(), TopAbs_SOLID)
                if sol and BRepCheck_Analyzer(sol[0]).IsValid():
                    out.append(("aus Flächenmodell genäht", TopoDS.Solid(sol[0])))
                    continue
        out.append(("Flächenmodell offen", sh))
    # einzelne Flächen, die zu keiner Schale gehören, werden ebenfalls gemeldet (nichts still verwerfen)
    in_schalen = TopTools_IndexedMapOfShape()
    for sh in schalen:
        TopExp.MapShapes_s(sh, TopAbs_FACE, in_schalen)
    out += [("Flächenmodell offen", f) for f in _liste(erg, TopAbs_FACE) if not in_schalen.Contains(f)]
    return out


def lies_step(pfad):
    """Nur die messbaren Volumenkörper (auch aus Flächenmodellen genähte) einer STEP-Datei."""
    return [k for art, k in lies_step_info(pfad)[0] if art != "Flächenmodell offen"]


def _koerper_daten(t, shape, art):
    """Kenndaten eines Körpers (in Dateilage, mm) und Geometrieprüfung."""
    from OCP.BRepCheck import BRepCheck_Analyzer
    t.koerperart = art
    p = GProp_GProps()
    if art != "Flächenmodell offen":
        BRepGProp.VolumeProperties_s(shape, p)
        t.volumen = abs(p.Mass())
    t.oberflaeche = _flaeche(shape)
    for typ, attr in ((TopAbs_FACE, "n_flaechen"), (TopAbs_EDGE, "n_kanten")):
        m = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, typ, m)
        setattr(t, attr, m.Extent())
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if not box.IsVoid():
        a, b = box.CornerMin(), box.CornerMax()
        t.huelle = (b.X() - a.X(), b.Y() - a.Y(), b.Z() - a.Z())
    t.gueltig = BRepCheck_Analyzer(shape).IsValid()
    if not t.gueltig:
        t.hinweise.append("Geometrie laut Prüfung ungültig (Fehler im CAD-Modell), Messwerte prüfen")
    if art == "aus Flächenmodell genäht":
        t.hinweise.append("Flächenmodell: zu einem Volumen zusammengenäht, Messwerte prüfen")


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
    # Richtung festlegen (sonst zufällig): größter Anteil positiv. Ende A liegt damit in der Datei vorn
    # (kleinere Koordinate in der Hauptrichtung des Rohrs).
    k = max((achse.X(), achse.Y(), achse.Z()), key=abs)
    if k < 0:
        achse.Reverse()
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


TOL_WAND_GLEICH = 0.05  # mm: Einzelmessungen der Wandstärke, die weiter auseinanderliegen, gelten als widersprüchlich
OFFENE_PROFILE = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl", "Vierkantstahl", "Rundstahl", "I-/H-Träger",
                  "T-Profil")


def _kanten_punkte(draht):
    """Je Kante die Punktfolge (x, y) des Polygonzugs (Teilung wie _strecken)."""
    out = []
    for e in _liste(draht, TopAbs_EDGE):
        c = BRepAdaptor_Curve(TopoDS.Edge(e))
        lg = _kantenlaenge(e)
        n = max(2, min(2000, int(lg / (1.0 if c.GetType() == GeomAbs_Line else 0.5)) + 1))
        u0, u1 = c.FirstParameter(), c.LastParameter()
        out.append([(q.X(), q.Y()) for q in (c.Value(u0 + (u1 - u0) * k / n) for k in range(n + 1))])
    return out


def _gerade(pts, tol=0.01):
    """True, wenn alle Punkte auf der Verbindung erster–letzter Punkt liegen (auch bei Freiformkurven)."""
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    lg = math.hypot(x2 - x1, y2 - y1)
    return lg > 0 and all(abs((x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)) / lg < tol for x, y in pts)


def _im_material(x, y, strecken):
    """Punkt im Querschnitt (Gerade nach +X schneidet die Konturen ungerade oft)."""
    n = 0
    for x1, y1, x2, y2 in strecken:
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            n += 1
    return n % 2 == 1


def _strahl(x, y, dx, dy, strecken):
    """Abstand vom Punkt in Richtung (dx, dy) bis zur nächsten Kontur (ohne den Startpunkt selbst)."""
    best = None
    for x1, y1, x2, y2 in strecken:
        ex, ey = x2 - x1, y2 - y1
        nenner = dx * ey - dy * ex
        if abs(nenner) < 1e-12:
            continue
        s = ((x1 - x) * ey - (y1 - y) * ex) / nenner
        u = ((x1 - x) * dy - (y1 - y) * dx) / nenner
        if s > 1e-4 and -1e-9 <= u <= 1 + 1e-9 and (best is None or s < best):
            best = s
    return best


def _wand_messungen(ws, kreis, z):
    """Wandstärke an mehreren Stellen des Querschnitts: senkrecht von der Außenkontur ins Material bis zur nächsten
    Kontur. Messstellen auf geraden Kanten bei 25/50/75 % (in Rundungen nicht, dort sind Außen- und Innenradius oft
    nicht gleichmittig), beim Kreis an 8 Stellen rundum. Ergebnis: Liste (z, x, y, Wert, Seite)."""
    alle = [s for w in ws for s in _strecken(w[1])]
    stellen = []
    kanten = _kanten_punkte(ws[0][1])
    if kreis:
        pts = [p for k in kanten for p in k]
        mx = (max(p[0] for p in pts) + min(p[0] for p in pts)) / 2
        my = (max(p[1] for p in pts) + min(p[1] for p in pts)) / 2
        for i in range(8):
            w = math.radians(22.5 + 45 * i)
            # Punkt der Außenkontur in dieser Richtung: Strahl von der Mitte nach außen, letzter Schnittpunkt
            d = max((s for s in (_strahl_alle(mx, my, math.cos(w), math.sin(w), alle))), default=None)
            if d:
                stellen.append((mx + d * math.cos(w), my + d * math.sin(w), -math.cos(w), -math.sin(w), "rund", None))
    else:
        for k in kanten:
            if not _gerade(k):
                continue
            (x1, y1), (x2, y2) = k[0], k[-1]
            lg = math.hypot(x2 - x1, y2 - y1)
            if lg < 3:
                continue
            nx, ny = -(y2 - y1) / lg, (x2 - x1) / lg
            for u in (0.25, 0.5, 0.75):
                px, py = x1 + u * (x2 - x1), y1 + u * (y2 - y1)
                if not _im_material(px + 0.01 * nx, py + 0.01 * ny, alle):
                    nx, ny = -nx, -ny
                seite = "x" if abs(nx) > abs(ny) else "y"
                stellen.append((px, py, nx, ny, f"{seite}{'+' if (px if seite == 'x' else py) > 0 else '-'}", lg))
    out = []
    for px, py, nx, ny, seite, lg in stellen:
        d = _strahl(px, py, nx, ny, alle)
        # eine Wand ist länger als dick: kurze Kanten (Stirnseite eines Schenkels o. ä.) messen keine Wand
        if d is not None and (lg is None or lg >= 2 * d):
            out.append((z, px, py, d, seite))
    return out


def _strahl_alle(x, y, dx, dy, strecken):
    """Alle Abstände, in denen ein Strahl die Konturen schneidet."""
    out = []
    for x1, y1, x2, y2 in strecken:
        ex, ey = x2 - x1, y2 - y1
        nenner = dx * ey - dy * ex
        if abs(nenner) < 1e-12:
            continue
        s = ((x1 - x) * ey - (y1 - y) * ex) / nenner
        u = ((x1 - x) * dy - (y1 - y) * dx) / nenner
        if s > 0 and -1e-9 <= u <= 1 + 1e-9:
            out.append(s)
    return out


def _seiten_belegung(strecken, x0, y0, x1, y1, tol=0.05):
    """Je Seite des Hüllrechtecks (links, rechts, unten, oben) die belegten Abschnitte [(von, bis)] entlang der Seite."""
    seiten = {"links": [], "rechts": [], "unten": [], "oben": []}
    for ax, ay, bx, by in strecken:
        for name, wert, koord, lauf in (("links", x0, (ax, bx), (ay, by)), ("rechts", x1, (ax, bx), (ay, by)),
                                        ("unten", y0, (ay, by), (ax, bx)), ("oben", y1, (ay, by), (ax, bx))):
            if abs(koord[0] - wert) < tol and abs(koord[1] - wert) < tol:
                seiten[name].append((min(lauf), max(lauf)))
    for name, ab in seiten.items():
        ab.sort()
        verbunden = []
        for a, b in ab:
            if verbunden and a <= verbunden[-1][1] + 0.6:
                verbunden[-1] = (verbunden[-1][0], max(verbunden[-1][1], b))
            else:
                verbunden.append((a, b))
        seiten[name] = verbunden
    return seiten


def _offenes_profil(draht, flaeche, x0, y0, x1, y1, je_seite):
    """Form eines Querschnitts mit nur einer Kontur. Ergebnis (Form, A, B, Bemerkung) oder None.
    Flachstahl/Vierkantstahl: Rechteck voll; Rundstahl: Kreis voll; L: zwei benachbarte Seiten des Hüllrechtecks voll
    belegt, die beiden anderen nur am Ende (Schenkeldicke); U: drei Seiten voll, die vierte nur an beiden Enden in
    Wanddicke; C: wie U, aber die vierte Seite an den Enden länger belegt (Abkantung)."""
    w, h = x1 - x0, y1 - y0
    st = _strecken(draht)
    if flaeche >= 0.97 * w * h:
        return ("Vierkantstahl" if abs(w - h) < 0.1 else "Flachstahl"), max(w, h), min(w, h), ""
    if _profilform(draht, w, h) == "Kreis":
        if flaeche >= 0.97 * math.pi / 4 * w * h:
            return "Rundstahl", (w + h) / 2, 0.0, ""
        return None
    s = _seiten_belegung(st, x0, y0, x1, y1)
    lang = {"links": h, "rechts": h, "unten": w, "oben": w}
    voll = {n for n, ab in s.items() if len(ab) == 1 and ab[0][1] - ab[0][0] >= 0.6 * lang[n]}
    gegen = {"links": "rechts", "rechts": "links", "unten": "oben", "oben": "unten"}
    if len(voll) == 2 and not any(gegen[n] in voll for n in voll):
        rest = [n for n in s if n not in voll]
        if all(len(s[n]) == 1 and s[n][0][1] - s[n][0][0] < 0.5 * lang[n] for n in rest):
            return "L-Profil", max(w, h), min(w, h), ""
    if len(voll) == 3:
        offen = next(n for n in s if n not in voll)
        if gegen[offen] in voll and len(s[offen]) == 2:
            # Ausdehnung der Enden von der Ecke des Hüllrechtecks aus (Außenradien an den Ecken zählen mit)
            von, bis = (y0, y1) if offen in ("links", "rechts") else (x0, x1)
            enden = [min(b - von, bis - a) for a, b in s[offen]]
            steg = lang[offen]     # Höhe = Länge der Stegseite, Breite = Flanschlänge
            breite = lang["unten" if offen in ("links", "rechts") else "links"]
            # Flanschdicke: gemessen von den Flansch-Außenseiten (quer zur offenen Seite)
            wand = je_seite.get("y" if offen in ("links", "rechts") else "x")
            if wand and all(abs(e - wand) <= max(0.2, 0.1 * wand) for e in enden):
                return "U-Profil", steg, breite, ""
            if wand and all(e >= 1.5 * wand for e in enden):
                return "C-Profil", steg, breite, f"Abkantung {min(enden):.1f} mm"
    # I/H: zwei gegenüberliegende Seiten voll (Flansche außen), die beiden anderen an beiden Enden in Flanschdicke
    # belegt. T: eine Seite voll (Flansch), die Gegenseite einmal (Stegende), die beiden anderen einmal (Flanschkante).
    if len(voll) == 2 and all(gegen[n] in voll for n in voll):
        quer = [n for n in s if n not in voll]
        if all(len(s[n]) == 2 for n in quer):
            return _traeger(st, flaeche, x0, y0, x1, y1, "oben" in voll, "I-/H-Träger")
    if len(voll) == 1:
        f = next(iter(voll))
        quer = [n for n in s if n not in (f, gegen[f])]
        if len(s[gegen[f]]) == 1 and all(len(s[n]) == 1 for n in quer):
            return _traeger(st, flaeche, x0, y0, x1, y1, f in ("oben", "unten"), "T-Profil")
    return None


def _traeger(st, flaeche, x0, y0, x1, y1, waagerecht, form):
    """Maße eines I-/H-Trägers oder T-Profils. waagerecht: Flansche liegen waagerecht (sonst werden x und y
    getauscht). Stegdicke: waagerechter Strahl durch den Steg; Flanschdicke: senkrechter Strahl bei (b − tw) / 4
    von der Flanschkante (Messstelle der Norm, auch bei geneigten Flanschen). Ausrundung aus dem Flächenüberschuss
    gegenüber dem scharfkantigen Querschnitt. Ergebnis (Form, h, b, Bemerkung, Zusatz) oder None."""
    if not waagerecht:
        st = [(ay, ax, by, bx) for ax, ay, bx, by in st]
        x0, y0, x1, y1 = y0, x0, y1, x1
    h, b = y1 - y0, x1 - x0
    s = _seiten_belegung(st, x0, y0, x1, y1)
    if form == "T-Profil":
        oben = len(s["oben"]) == 1 and s["oben"][0][1] - s["oben"][0][0] >= 0.6 * b
        y_steg = y0 + 0.35 * h if oben else y1 - 0.35 * h
    else:
        y_steg = (y0 + y1) / 2
    def alle(x, y, dx, dy):     # Treffer an einer Teilungsstelle der Kontur nur einmal zählen
        out = []
        for d in sorted(_strahl_alle(x, y, dx, dy, st)):
            if not out or d - out[-1] > 1e-6:
                out.append(d)
        return out
    treffer = alle(x0 - 1, y_steg + 0.0137 * h, 1, 0)
    if len(treffer) != 2:
        return None
    tw = treffer[1] - treffer[0]
    xm = x0 - 1 + (treffer[0] + treffer[1]) / 2
    dicken = []
    for xs in (x0 + (b - tw) / 4, x1 - (b - tw) / 4):
        z = alle(xs + 0.0113 * b, y0 - 1, 0, 1)
        if len(z) % 2 or not z:
            return None
        dicken.append([z[k + 1] - z[k] for k in range(0, len(z), 2)])
    if form == "T-Profil":
        if any(len(d) != 1 for d in dicken):
            return None
        tf, tf2 = dicken[0][0], dicken[1][0]
        scharf = b * tf + (h - tf) * tw
        ecken = 2
    else:
        if any(len(d) != 2 for d in dicken):
            return None
        tf, tf2 = dicken[0][0], dicken[0][1]
        tf = (tf + dicken[1][0]) / 2
        tf2 = (tf2 + dicken[1][1]) / 2
        scharf = b * (tf + tf2) + (h - tf - tf2) * tw
        ecken = 4
    if tw <= 0 or tf <= 0 or tw >= b or tf + (tf2 if form != "T-Profil" else 0) >= h:
        return None
    breiten = [ab[0][1] - ab[0][0] for ab in (s["unten"], s["oben"]) if len(ab) == 1]
    symmetrisch = (abs(xm - (x0 + x1) / 2) <= 0.1 and abs(tf - tf2) <= 0.1 and
                   (form == "T-Profil" or len(breiten) == 2 and abs(breiten[0] - breiten[1]) <= 0.2))
    ueber = max(0.0, flaeche - scharf)
    r = math.sqrt(ueber / (ecken * (1 - math.pi / 4))) if ueber > 0.5 else 0.0
    zusatz = dict(stegdicke=tw, flanschdicke=max(tf, tf2) if form == "T-Profil" else (tf + tf2) / 2,
                  flansch_oben=tf2, flansch_unten=tf, symmetrisch=symmetrisch, radius=r)
    bemerkung = "" if symmetrisch else "unsymmetrisch: " + (
        f"Flansche {tf:.1f} / {tf2:.1f} mm" if abs(tf - tf2) > 0.1 else "Steg außermittig oder Flansche ungleich breit")
    return form, h, b, bemerkung, zusatz


class _Abwicklung:
    """Abwicklung der Außenkontur (konvexe Hohlprofile): Umfangswinkel und Umfangsposition eines Punkts.

    Winkel: um die Rohrachse rechtsdrehend (Daumen der rechten Hand zeigt von Ende A nach Ende B), 0° = Bezugsrichtung
    ref (Richtung im Querschnitt, siehe _bezug). Umfangsposition u: Bogenlänge auf der Außenkontur ab 0° [mm]."""

    def __init__(self, s_aussen, ref):
        xs = [s[0] for s in s_aussen] + [s[2] for s in s_aussen]
        ys = [s[1] for s in s_aussen] + [s[3] for s in s_aussen]
        self.cx, self.cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        self.ref = ref
        pts = sorted({(round(self.theta(x, y), 9), x, y) for x, y in zip(xs, ys)})
        self.th, self.s, self.xy = [], [], []
        lauf = 0.0
        for i, (th, x, y) in enumerate(pts):
            if i:
                lauf += math.hypot(x - pts[i - 1][1], y - pts[i - 1][2])
            self.th.append(th)
            self.s.append(lauf)
            self.xy.append((x, y))
        self.umfang = lauf + math.hypot(pts[0][1] - pts[-1][1], pts[0][2] - pts[-1][2])
        self.versatz = 0.0
        self.versatz = self._u_th(0.0)      # u = 0 genau bei 0°

    def theta(self, x, y):
        return (math.degrees(math.atan2(-(x - self.cx), y - self.cy)) - self.ref) % 360

    def u(self, x, y):
        return self._u_th(self.theta(x, y))

    def _u_th(self, th):
        import bisect
        i = bisect.bisect_left(self.th, th)
        if i <= 0:
            t0, t1, s0, s1 = self.th[-1] - 360, self.th[0], self.s[-1] - self.umfang, self.s[0]
        elif i >= len(self.th):
            t0, t1, s0, s1 = self.th[-1], self.th[0] + 360, self.s[-1], self.umfang
        else:
            t0, t1, s0, s1 = self.th[i - 1], self.th[i], self.s[i - 1], self.s[i]
        return ((s0 + (s1 - s0) * (th - t0) / (t1 - t0) if t1 > t0 else s0) - self.versatz) % self.umfang

    def punkt(self, u):
        """(Winkel, x, y) des Punkts der Außenkontur an der Umfangsposition u."""
        import bisect
        u = (u + self.versatz) % self.umfang
        i = min(max(bisect.bisect_right(self.s, u), 1), len(self.s) - 1)
        s0, s1 = self.s[i - 1], self.s[i]
        f = (u - s0) / (s1 - s0) if s1 > s0 else 0.0
        x = self.xy[i - 1][0] + f * (self.xy[i][0] - self.xy[i - 1][0])
        y = self.xy[i - 1][1] + f * (self.xy[i][1] - self.xy[i - 1][1])
        return self.theta(x, y), x, y


def _bezug(ax3, profilform):
    """Bezugsrichtung 0° des Umfangswinkels im Messsystem (Grad, gleiche Zählung wie _Abwicklung.theta).
    Kastenprofile: Mitte der breiten Seite (±Y), und zwar die, die in der Datei eher nach oben (+Z) zeigt.
    Rundrohre: die in der Datei oberste Stelle (+Z der Datei quer zur Achse; liegt das Rohr senkrecht, +Y der Datei)."""
    def lokal(g):
        return (g.Dot(_vec(ax3.XDirection())), g.Dot(_vec(ax3.YDirection())))
    gx, gy = lokal(gp_Vec(0, 0, 1))
    if math.hypot(gx, gy) < 0.1:
        gx, gy = lokal(gp_Vec(0, 1, 0))
    if profilform == "Rundrohr":
        return math.degrees(math.atan2(-gx, gy))
    return 0.0 if gy >= 0 else 180.0


def _punkte_kanten(kanten, schritt=0.5):
    out = []
    for e in kanten:
        c = BRepAdaptor_Curve(TopoDS.Edge(e))
        n = max(4, min(400, int(_kantenlaenge(e) / schritt) + 1))
        u0, u1 = c.FirstParameter(), c.LastParameter()
        out += [c.Value(u0 + (u1 - u0) * k / n) for k in range(n + 1)]
    return out


def _form_2d(uv, tol=0.05):
    """Form einer abgewickelten Kontur: ('Kreis', Ø) / ('Langloch', L, B) / ('Rechteck', L, B) / ('Ausschnitt', L, B),
    dazu Mittelpunkt (u, v) und Drehwinkel der Längsrichtung gegen die Rohrachse [Grad]."""
    w = _min_rechteck(uv)
    c, s = math.cos(w), math.sin(w)
    p = [(x * c + y * s, -x * s + y * c) for x, y in uv]
    p0, p1 = min(q[0] for q in p), max(q[0] for q in p)
    q0, q1 = min(q[1] for q in p), max(q[1] for q in p)
    lg, br = p1 - p0, q1 - q0
    mp, mq = (p0 + p1) / 2, (q0 + q1) / 2
    mitte = (mp * c - mq * s, mp * s + mq * c)
    lage = math.degrees(w) % 180          # 0° = Längsrichtung der Kontur quer zur Rohrachse (entlang u)
    rel = [(a - mp, b - mq) for a, b in p]
    r = [math.hypot(a, b) for a, b in rel]
    if max(r) - min(r) < 2 * tol:
        return ("Kreis", (max(r) + min(r)), 0.0), mitte, lage
    if lg > br + tol:
        h = (lg - br) / 2
        if all(abs(math.hypot(max(abs(a) - h, 0), b) - br / 2) < tol for a, b in rel):
            return ("Langloch", lg, br), mitte, lage
    auf_seite = sum(1 for a, b in rel if abs(abs(a) - lg / 2) < tol or abs(abs(b) - br / 2) < tol)
    if auf_seite >= 0.6 * len(rel):
        return ("Rechteck", lg, br), mitte, lage
    return ("Ausschnitt", lg, br), mitte, lage


def _ebene(face, tol=1e-4):
    """Ebene (gp_Pln) einer Fläche oder None, auch bei ebenen Freiformflächen."""
    from OCP.GeomLib import GeomLib_IsPlanarSurface
    sf = BRepAdaptor_Surface(TopoDS.Face(face))
    if sf.GetType() == GeomAbs_Plane:
        return sf.Plane()
    pr = GeomLib_IsPlanarSurface(BRep_Tool.Surface_s(TopoDS.Face(face)), tol)
    return pr.Plan() if pr.IsPlanar() else None


def _endform(flaechen, laenge, ref=0.0):
    """Form eines Endes aus seinen Schnittflächen: gerade, Gehrung (Neigung um eine Querachse), Schrägschnitt zwei-
    achsig oder komplex (mehrere Ebenen, gekrümmt: Ausklinkung, Sattel …). Winkel in Grad gegen den geraden Schnitt:
    gehrung = Gesamtneigung, um_x = Neigung zur 0°-Richtung hin (Drehung um die Querachse 270°–90°), um_y = Neigung
    zur 270°-Richtung hin (Drehung um die Querachse 0°–180°). ref: Bezugsrichtung 0° (siehe _bezug)."""
    normalen = []
    for f in flaechen:
        pl = _ebene(f)
        if pl is None:
            return dict(form="komplex", gehrung=None, um_x=None, um_y=None, schnittlaenge=round(laenge, 2))
        d = pl.Axis().Direction()
        n = (d.X(), d.Y(), d.Z()) if d.Z() >= 0 else (-d.X(), -d.Y(), -d.Z())
        if not any(sum(a * b for a, b in zip(n, m)) > 1 - 1e-6 for m in normalen):
            normalen.append(n)
    if len(normalen) != 1:
        return dict(form="komplex", gehrung=None, um_x=None, um_y=None, schnittlaenge=round(laenge, 2))
    nx0, ny0, nz = normalen[0]
    r = math.radians(ref)      # Querachsen so drehen, dass Y in die 0°-Richtung zeigt
    nx, ny = nx0 * math.cos(r) + ny0 * math.sin(r), -nx0 * math.sin(r) + ny0 * math.cos(r)
    ges = math.degrees(math.acos(min(1.0, nz)))
    um_x, um_y = math.degrees(math.atan2(abs(ny), nz)), math.degrees(math.atan2(abs(nx), nz))
    form = "gerade" if ges < 0.05 else "Gehrung" if min(um_x, um_y) < 0.05 else "Schrägschnitt zweiachsig"
    return dict(form=form, gehrung=round(ges, 2), um_x=round(um_x, 2), um_y=round(um_y, 2),
                schnittlaenge=round(laenge, 2))


def _offen_auswerten(t, lok, aussen, passend, x0, y0, x1, y1, zmin, netz):
    """Profil mit einer Kontur im Querschnitt (U, C, L, Flach-, Vierkant-, Rundstahl): Form, Maße, Wandstärken.
    Konturen werden bei diesen Profilen noch nicht ausgewertet (sie werden auch noch nicht kalkuliert)."""
    messungen = []
    for z, wsz in passend:
        messungen += _wand_messungen(wsz, False, z - zmin)
    werte = sorted(m[3] for m in messungen)
    wand = werte[len(werte) // 2] if werte else 0.0
    seiten = {}
    for m in messungen:
        seiten.setdefault(m[4][0], []).append(m[3])
    je_seite = {k: sorted(v)[len(v) // 2] for k, v in seiten.items()}
    erg = _offenes_profil(aussen, t.flaeche, x0, y0, x1, y1, je_seite)
    if erg is None:
        t.profilform, t.abm_a, t.abm_b = "offenes Sonderprofil", max(x1 - x0, y1 - y0), min(x1 - x0, y1 - y0)
        t.hinweise.append("Offenes Profil nicht erkannt, Fläche manuell prüfen")
        t.sicherheit["profil"] = "unsicher"
    else:
        t.profilform, t.abm_a, t.abm_b, bemerkung = erg[:4]
        zusatz = erg[4] if len(erg) > 4 else {}
        t.sicherheit["profil"] = "sicher"
        if bemerkung:
            t.hinweise.append(bemerkung)
        if zusatz:
            t.stegdicke, t.flanschdicke = zusatz["stegdicke"], zusatz["flanschdicke"]
            t.symmetrisch, t.radius = zusatz["symmetrisch"], zusatz["radius"]
    if t.profilform in ("Flachstahl", "Vierkantstahl", "Rundstahl"):
        t.wandstaerke = 0.0          # Vollprofil: keine Wand
        t.sicherheit["wandstaerke"] = "sicher"
    elif werte:
        t.wand_messungen = messungen
        if max(werte) - min(werte) <= TOL_WAND_GLEICH:
            t.wandstaerke = wand
            t.sicherheit["wandstaerke"] = "sicher" if len(werte) >= 4 else "wahrscheinlich"
        elif all(max(v) - min(v) <= TOL_WAND_GLEICH for v in seiten.values()):
            t.wandstaerke = min(je_seite.values())    # z. B. Steg und Flansch verschieden dick
            t.sicherheit["wandstaerke"] = "wahrscheinlich"
            t.hinweise.append("Wandstärken verschieden: " + ", ".join(
                f"{'senkrecht' if k == 'x' else 'waagerecht'} {v:.2f} mm" for k, v in sorted(je_seite.items())))
        else:
            t.wandstaerke = min(werte)
            t.sicherheit["wandstaerke"] = "unsicher"
            t.hinweise.append(f"Wandstärke nicht einheitlich: {min(werte):.2f} bis {max(werte):.2f} mm")
    if t.profilform in TRAEGER:
        # Steg und Flansch sind bei Trägern verschieden dick: Wandstärke = Stegdicke, Flanschdicke eigenes Feld
        t.hinweise = [h for h in t.hinweise if not h.startswith("Wandstärke")]
        t.wandstaerke = t.stegdicke
        t.sicherheit["wandstaerke"] = "sicher"
    if t.profilform in ("U-Profil", "L-Profil") + TRAEGER:
        tf = t.flanschdicke or t.wandstaerke
        if t.profilform == "U-Profil" and len(je_seite) == 2:      # Steg dünner als die Flansche (UPN)
            tf = max(je_seite.values())
        t.normprofil = normprofile.zuordnen(t.profilform, t.abm_a, t.abm_b, t.wandstaerke, tf, t.flaeche) or ""
        if t.normprofil and t.profilform == "U-Profil":
            t.stegdicke, t.flanschdicke = t.wandstaerke, tf
            t.hinweise = [h for h in t.hinweise if not h.startswith("Wandstärken verschieden")]
            t.sicherheit["wandstaerke"] = "sicher"
    if t.profilform in OFFEN_KALKULIERT:
        return _offen_konturen(t, lok, aussen, zmin, netz)
    t.sicherheit["konturen"] = "nicht ausgewertet"
    t.hinweise.append(f"{t.profilform}: wird noch nicht kalkuliert, Konturen nicht ausgewertet")
    if netz:
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(lok, TopAbs_FACE, faces)
        t.netz = dreiecksnetz(lok, faces, {i: "A" for i in range(1, faces.Extent() + 1)}, [], zmin,
                              max(t.abm_a, t.abm_b))
    return t


# Offene Profile, die das Programm kalkuliert (Patrick 20.10.2026: Plan Frage 2 b). Vierkant- und Rundstahl
# (Vollmaterial) und nicht erkannte offene Profile bleiben nur gemeldet.
OFFEN_KALKULIERT = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl", "I-/H-Träger", "T-Profil")
TRAEGER = ("I-/H-Träger", "T-Profil")      # seit 20.10.2026 erkannt und kalkuliert (Frage 2 a)


def _normale(face, p):
    """Nach außen zeigende Flächennormale (x, y, z) im Punkt p (auf der Fläche) oder None."""
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
    from OCP.BRepGProp import BRepGProp_Face
    f = TopoDS.Face(face)
    uv = ShapeAnalysis_Surface(BRep_Tool.Surface_s(f)).ValueOfUV(p, 1e-3)
    q, v = gp_Pnt(), gp_Vec()
    BRepGProp_Face(f).Normal(uv.X(), uv.Y(), q, v)
    m = v.Magnitude()
    return (v.X() / m, v.Y() / m, v.Z() / m) if m > 1e-12 else None


def _offen_konturen(t, lok, aussen, zmin, netz):
    """Schnitte an offenen Profilen (U, C, L, Flachstahl). Profil und Wand liegen auf einer einzigen Kontur; eine
    Fläche, die nicht auf ihr liegt, gehört zu einem Merkmal (Ende, Bohrung, Ausschnitt). Ein Merkmal geht durch,
    wenn es Wandflächen beider Seiten der Wand berührt (Normalen entgegengesetzt), sonst ist es eine Gravur oder
    Sackbohrung. Der Laser schneidet von einer Seite: Schnittlänge = halbe Länge der Kanten zur Wand (oben und
    unten je einmal), Einstiche = halbe Anzahl Konturzüge (aufgerundet). Lage: z ab Ende A; die Lage um das Profil
    (Steg/Flansch) wird nicht angegeben."""
    zmax = zmin + t.laenge
    s_aussen = _strecken(aussen)
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(lok, TopAbs_FACE, faces)

    def punkte(face):
        pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in _liste(face, TopAbs_VERTEX)]
        for e in _liste(face, TopAbs_EDGE):
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            for u in (0.25, 0.5, 0.75):
                pts.append(c.Value(c.FirstParameter() + u * (c.LastParameter() - c.FirstParameter())))
        return pts

    art, fl_art = {}, {"A": 0.0, "S": 0.0}
    for i in range(1, faces.Extent() + 1):
        f = faces.FindKey(i)
        # Wandflächen liegen auf der Kontur und laufen längs; eine Stirnfläche hat ihren Rand auch auf der Kontur
        pl = _ebene(f)
        laengs = pl is None or abs(pl.Axis().Direction().Z()) < 1e-3
        art[i] = "A" if laengs and all(_nah_zug(p.X(), p.Y(), s_aussen, TOL_WAND) for p in punkte(f)) else "S"
        fl_art[art[i]] += _flaeche(f)
    if fl_art["S"] > fl_art["A"]:
        t.hinweise.append("Erkennung unsicher: Schnittflächen größer als die Profilflächen, Konturen nicht "
                          "ausgewertet. Teil bitte prüfen.")
        t.sicherheit["konturen"] = "unsicher"
        return t
    kf = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(lok, TopAbs_EDGE, TopAbs_FACE, kf)
    vmap = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(lok, TopAbs_VERTEX, vmap)
    eltern = {}

    def finde(x):
        while eltern.setdefault(x, x) != x:
            eltern[x] = eltern[eltern[x]]
            x = eltern[x]
        return x
    kanten_info = []
    for i in range(1, kf.Extent() + 1):
        fi = {faces.FindIndex(f) for f in kf.FindFromIndex(i)}
        kanten_info.append((kf.FindKey(i), fi))
        sf = [f for f in fi if art[f] == "S"]
        for f in sf[1:]:
            eltern[finde(f)] = finde(sf[0])
    merkmale = {}
    for f, a_ in art.items():
        if a_ == "S":
            merkmale.setdefault(finde(f), dict(faces=[], kanten=[], normalen=[]))["faces"].append(f)
    for e, fi in kanten_info:
        s_f = [f for f in fi if art[f] == "S"]
        a_f = [f for f in fi if art[f] == "A"]
        if s_f and a_f:
            m = merkmale[finde(s_f[0])]
            m["kanten"].append(e)
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            n = _normale(faces.FindKey(a_f[0]), c.Value((c.FirstParameter() + c.LastParameter()) / 2))
            if n:
                m["normalen"].append(n)

    def zuege(kanten):
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
        out = {}
        for e in kanten:
            out.setdefault(fv(vmap.FindIndex(_liste(e, TopAbs_VERTEX)[0])), []).append(e)
        return list(out.values())

    TOL_Z = 0.01
    enden = {"EA": [[], 0.0], "EB": [[], 0.0]}
    liste, bohrungen = [], {}
    for m in merkmale.values():
        kanten = m["kanten"]
        if not kanten:
            continue
        laenge = sum(_kantenlaenge(e) for e in kanten)
        zg = zuege(kanten)
        nm = m["normalen"]
        durch = any(sum(p * q for p, q in zip(a_, b_)) < -0.5 for i, a_ in enumerate(nm) for b_ in nm[i + 1:])
        bb = Bnd_Box()
        for e in kanten:
            BRepBndLib.AddOptimal_s(e, bb, False, False)
        gz0, gz1 = bb.CornerMin().Z(), bb.CornerMax().Z()
        # Rundbohrung: nur Zylinderflächen gleichen Radius quer zur Achse (Sackbohrung: dazu ein ebener/kegeliger
        # Grund)
        radien, andere = set(), False
        for f in m["faces"]:
            fk = faces.FindKey(f)
            z_ = _zylinder(fk)
            if z_ is not None and abs(z_.Axis().Direction().Z()) < 0.99:
                radien.add(round(z_.Radius(), 2))
            elif durch or not (_ebene(fk) is not None or
                               BRepAdaptor_Surface(TopoDS.Face(fk)).GetType() == GeomAbs_Cone):
                andere = True
        rund = (None, round(2 * radien.pop(), 2)) if len(radien) == 1 and not andere else None
        if not durch:
            m["art"] = "G"
            t.gravur += laenge
            t.gravur_konturen += len(zg)
            d = dict(durchgehend=False, z=round((gz0 + gz1) / 2 - zmin, 2), winkel=None, u=None, seite=None,
                     schnittlaenge=round(laenge, 2))
            if rund:
                d.update(art="Sackbohrung", durchmesser=rund[1], hinweis="nicht durchgehend, mit dem Laser nicht "
                         "herstellbar")
                t.hinweise.append(f"Sackbohrung Ø{rund[1]:g} gefunden (nicht laserbar), prüfen")
            else:
                d.update(art="Gravur", hinweis="nicht durchgehend (Markierung/Vertiefung), nicht im Schneidweg")
            liste.append(d)
            continue
        schnitt = laenge / 2
        einstiche = (len(zg) + 1) // 2
        if gz0 - zmin < TOL_Z:
            m["art"] = "EA"
            t.ende_a += schnitt
            t.ende_a_gerade = gz1 - zmin < TOL_Z
        elif zmax - gz1 < TOL_Z:
            m["art"] = "EB"
            t.ende_b += schnitt
            t.ende_b_gerade = zmax - gz0 < TOL_Z
        else:
            m["art"] = "K"
            t.innen += schnitt
            t.innen_konturen += einstiche
            mn, mx = bb.CornerMin(), bb.CornerMax()
            dz = mx.Z() - mn.Z()
            quer = max(mx.X() - mn.X(), mx.Y() - mn.Y())
            d = dict(durchgehend=True, z=round((gz0 + gz1) / 2 - zmin, 2), winkel=None, u=None, seite=None,
                     schnittlaenge=round(schnitt, 2))
            if rund:
                bohrungen[rund[1]] = bohrungen.get(rund[1], 0) + 1
                d.update(art="Bohrung", durchmesser=rund[1], huellmass=rund[1])
                t.innen_liste.append((rund[1], schnitt))
            else:
                # Maße in der Wandebene: entlang der Achse (dz) und quer dazu; die Wanddicke steckt mit im Hüllmaß
                d.update(art="Ausschnitt", laenge=round(max(dz, quer), 2), breite=round(min(dz, quer), 2),
                         huellmass=round(max(dz, quer), 2))
                t.innen_liste.append((max(dz, quer), schnitt))
            liste.append(d)
        if m["art"] in enden:
            enden[m["art"]][0] += [faces.FindKey(f) for f in m["faces"]]
            enden[m["art"]][1] += schnitt
        t.konturen += einstiche
    kopf = []
    for art_, name, z in (("EA", "Ende A", 0.0), ("EB", "Ende B", t.laenge)):
        fl, lg = enden[art_]
        e = _endform(fl, lg) if fl else dict(form="nicht erkannt", gehrung=None, um_x=None, um_y=None,
                                         schnittlaenge=0.0)
        kopf.append(dict(art=name, durchgehend=True, z=round(z, 2), winkel=None, u=None, seite=None, **e))
    t.konturen_liste = kopf + sorted(liste, key=lambda d: d["z"])
    t.bohrungen = dict(sorted(bohrungen.items()))
    t.schneidweg = t.ende_a + t.ende_b + t.innen
    t.sicherheit["konturen"] = "wahrscheinlich" if any(
        d["art"] == "Ausschnitt" or d.get("form") in ("komplex", "nicht erkannt") for d in t.konturen_liste) \
        else "sicher"
    if netz:
        art_flaeche = dict(art)
        for m in merkmale.values():
            for f in m["faces"]:
                art_flaeche[f] = m.get("art", "K")
        t.netz = dreiecksnetz(lok, faces, art_flaeche, [(m.get("art", "K"), m["kanten"]) for m in merkmale.values()],
                              zmin, max(t.abm_a, t.abm_b))
    return t


def _innen_liegend(innen, aussen):
    """True, wenn der Hüllquader von innen in dem von aussen liegt (Hohlprofil). Zwei nebeneinanderliegende
    Konturen (z. B. U-Profil im Schnitt durch eine Stegbohrung) sind kein Hohlprofil."""
    bi, ba = Bnd_Box(), Bnd_Box()
    BRepBndLib.AddOptimal_s(innen, bi, False, False)
    BRepBndLib.AddOptimal_s(aussen, ba, False, False)
    return (ba.CornerMin().X() < bi.CornerMin().X() and bi.CornerMax().X() < ba.CornerMax().X() and
            ba.CornerMin().Y() < bi.CornerMin().Y() and bi.CornerMax().Y() < ba.CornerMax().Y())


def _profil_messen(solid, datei="", koerper=1, netz=False):
    """Messung als gerades Profil (Rohr, offenes Profil, Flachstahl) mit konstantem Querschnitt."""
    t = Teil(datei=datei, koerper=koerper)
    ax3, regel = _lage(solid)
    lok = _transformiere(solid, ax3)

    zmin, zmax = _z_bereich(lok)
    t.laenge = zmax - zmin
    d, p = ax3.Direction(), _global(ax3, 0, 0, zmin)
    t.achse_global = (d.X(), d.Y(), d.Z())
    t.ende_a_global = (p.X(), p.Y(), p.Z())

    # Querschnitt: Lage mit größter Netto-Fläche, zuerst als Hohlprofil (genau 2 Konturen: außen/innen), sonst mit
    # einer Kontur (U, L, C, Flach …). Bis zu 49 Lagen über die ganze Länge, damit auch lange Ausschnitte umgangen
    # werden; krumme Anteile, damit die Ebene nicht genau auf einer Merkmalskante liegt. Von der Mitte nach außen;
    # sobald drei Lagen den größten Querschnitt zeigen, ist er gefunden (ein Schnitt durch ein Merkmal hat weniger
    # Fläche oder mehr Konturen). Die drei Lagen dienen auch als Messstellen der Wandstärke.
    def suche(n_konturen):
        best, passend = None, []
        for anteil in sorted([0.5037] + [(i + 0.37) / 50 for i in range(1, 49)], key=lambda a: abs(a - 0.5037)):
            z = zmin + anteil * t.laenge
            ws = _schnitt(lok, z)
            if len(ws) != n_konturen or n_konturen == 2 and not _innen_liegend(ws[1][1], ws[0][1]):
                continue
            netto = ws[0][0] - sum(w[0] for w in ws[1:])
            if best is None or netto > best[0] * 1.001:
                best, passend = (netto, z, ws), [(z, ws)]
            elif netto >= best[0] * 0.999:
                passend.append((z, ws))
            if len(passend) >= 3:
                break
        return best, passend

    t.sicherheit["achse"] = t.sicherheit["laenge"] = \
        "sicher" if len(regel) >= 3 else "wahrscheinlich" if len(regel) == 2 else "unsicher"
    best, passend = suche(2)
    hohl = best is not None
    if not hohl:
        best, passend = suche(1)
    if best is None:
        t.hinweise.append("Kein Profilquerschnitt gefunden (Querschnitt nicht über die Länge gleich?)")
        t.sicherheit.update(achse="unsicher", laenge="unsicher", profil="unsicher")
        return t
    t.flaeche, z0, ws = best
    aussen = ws[0][1]
    wb = Bnd_Box()
    BRepBndLib.AddOptimal_s(aussen, wb, False, False)
    x0, y0, x1, y1 = wb.CornerMin().X(), wb.CornerMin().Y(), wb.CornerMax().X(), wb.CornerMax().Y()
    bx, by = x1 - x0, y1 - y0
    a, b = max(bx, by), min(bx, by)

    if not hohl:
        return _offen_auswerten(t, lok, aussen, passend, x0, y0, x1, y1, zmin, netz)

    innen = ws[1][1]
    s_aussen, s_innen = _strecken(aussen), _strecken(innen)
    t.wandstaerke = _wandstaerke(aussen, innen, s_aussen, s_innen, z0)
    ib = Bnd_Box()
    BRepBndLib.AddOptimal_s(innen, ib, False, False)
    ia, ibb = ib.CornerMax().X() - ib.CornerMin().X(), ib.CornerMax().Y() - ib.CornerMin().Y()

    # Profilform aus der Außenkontur (Ecken/Kreise können je nach CAD als Kreis, Ellipse, Spline oder Freiform-
    # kurve kommen, darum geometrisch statt über Kurventypen)
    form = _profilform(aussen, bx, by)
    t.sicherheit["profil"] = "sicher"
    if form == "Kreis" and a - b < 0.1:
        t.profilform, t.abm_a, t.innen_a = "Rundrohr", (a + b) / 2, (ia + ibb) / 2
    elif form == "Rechteck" and a - b < 0.1:
        t.profilform, t.abm_a, t.innen_a, t.innen_b = "Quadratrohr", (a + b) / 2, max(ia, ibb), min(ia, ibb)
    elif form == "Rechteck":
        t.profilform, t.abm_a, t.abm_b, t.innen_a, t.innen_b = "Rechteckrohr", a, b, max(ia, ibb), min(ia, ibb)
    else:
        t.profilform, t.abm_a, t.abm_b, t.innen_a, t.innen_b = "Sonderprofil", a, b, max(ia, ibb), min(ia, ibb)
        t.hinweise.append("Profil nicht erkannt, Fläche manuell prüfen")
        t.sicherheit["profil"] = "unsicher"

    # Wandstärke an mehreren Stellen (je Querschnittslage mehrere Messstellen) und Gegenprobe
    for z, wsz in passend:
        t.wand_messungen += _wand_messungen(wsz, form == "Kreis", z - zmin)
    werte = [m[3] for m in t.wand_messungen] + [t.wandstaerke]
    if max(werte) - min(werte) > TOL_WAND_GLEICH:
        t.sicherheit["wandstaerke"] = "unsicher"
        t.hinweise.append(f"Wandstärke nicht einheitlich: {min(werte):.2f} bis {max(werte):.2f} mm an "
                          f"{len(werte)} Messstellen, Profil prüfen")
    else:
        t.sicherheit["wandstaerke"] = "sicher" if len(t.wand_messungen) >= 4 else "wahrscheinlich"

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
    ref = _bezug(ax3, t.profilform)
    abw = _Abwicklung(s_aussen, ref)
    kasten = t.profilform in ("Quadratrohr", "Rechteckrohr")
    hx, hy = bx / 2, by / 2
    enden = {"EA": [[], 0.0], "EB": [[], 0.0]}     # Flächen und Schnittlänge je Ende
    liste = []

    def lage_auf_rohr(zug):
        """Abgewickelte Kontur -> Form, Maße, Mitte (z ab Ende A, Winkel, Seite), Normale der Wand dort."""
        uv = [(abw.u(p.X(), p.Y()), p.Z() - zmin) for p in _punkte_kanten(zug)]
        if max(u for u, _ in uv) - min(u for u, _ in uv) > abw.umfang / 2:     # über die 0°-Naht
            uv = [(u + abw.umfang if u < abw.umfang / 2 else u, v) for u, v in uv]
        form, (uc, vc), lage = _form_2d(uv)
        winkel, px, py = abw.punkt(uc)
        seite = None
        if kasten:
            dx, dy = px - abw.cx, py - abw.cy
            if abs(abs(dx) - hx) < 0.05 or abs(abs(dy) - hy) < 0.05:
                seite = f"{round(winkel / 90) % 4 * 90}°"
            else:
                seite = "Ecke"
        (_, ax_, ay_), (_, bx_, by_) = abw.punkt(uc - 0.5), abw.punkt(uc + 0.5)
        tl = math.hypot(bx_ - ax_, by_ - ay_) or 1.0
        normale = ((by_ - ay_) / tl, -(bx_ - ax_) / tl)
        u = uc % abw.umfang
        d = dict(z=round(vc, 2), winkel=round(winkel % 360, 1) % 360,
                 u=round(0.0 if abw.umfang - u < 0.005 else u, 2), seite=seite)
        return form, lage, d, normale

    def zylinder_einheitlich(fl, mit_boden=False):
        """(gp_Cylinder, Ø), wenn alle Flächen Zylinder gleichen Radius quer zum Rohr sind (bei mit_boden dürfen
        ebene oder kegelige Bohrungsgründe dazukommen), sonst None."""
        zyl, radien = None, set()
        for f in fl:
            z_ = _zylinder(faces.FindKey(f))
            if z_ is None:
                if mit_boden and _ebene(faces.FindKey(f)) is not None or mit_boden and \
                        BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(f))).GetType() == GeomAbs_Cone:
                    continue
                return None
            if abs(z_.Axis().Direction().Z()) > 0.99:
                return None
            zyl = z_
            radien.add(round(z_.Radius(), 2))
        return (zyl, round(2 * radien.pop(), 2)) if zyl is not None and len(radien) == 1 else None

    def schraeg(zyl, normale):
        dz = zyl.Axis().Direction()
        c = abs(dz.X() * normale[0] + dz.Y() * normale[1])
        return round(math.degrees(math.acos(min(1.0, c))), 2)

    for m in merkmale.values():
        kanten = m["kanten"]
        if not kanten:
            liste.append(dict(art="Innenmerkmal", durchgehend=False, z=None, winkel=None, u=None, seite=None,
                              schnittlaenge=0.0, hinweis="nur auf der Innenseite, von außen nicht sichtbar"))
            t.hinweise.append("Merkmal nur auf der Innenseite gefunden, nicht gerechnet")
            continue
        laenge = sum(_kantenlaenge(e) for e in kanten)
        n = konturen_zaehlen(kanten)
        if not m["durch"]:
            m["art"] = "G"
            t.gravur += laenge
            t.gravur_konturen += n
            sack = zylinder_einheitlich(m["faces"], mit_boden=True)
            for zug in konturzuege(kanten):
                form, lage, d, normale = lage_auf_rohr(zug)
                if sack:
                    d.update(art="Sackbohrung", durchgehend=False, durchmesser=sack[1], schraeg=schraeg(sack[0], normale),
                             hinweis="nicht durchgehend, mit dem Laser nicht herstellbar")
                else:
                    d.update(art="Gravur", durchgehend=False, laenge=round(form[1], 2), breite=round(form[2], 2),
                             hinweis="nicht durchgehend (Markierung/Vertiefung), nicht im Schneidweg")
                d["schnittlaenge"] = round(sum(_kantenlaenge(e) for e in zug), 2)
                liste.append(d)
            if sack:
                t.hinweise.append(f"Sackbohrung Ø{sack[1]:g} gefunden (nicht laserbar), prüfen")
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
            rund = zylinder_einheitlich(m["faces"])
            if rund:
                d = rund[1]
                bohrungen[d] = bohrungen.get(d, 0) + n
            for zug in konturzuege(kanten):
                form, lage, d, normale = lage_auf_rohr(zug)
                d.update(durchgehend=True, schnittlaenge=round(sum(_kantenlaenge(e) for e in zug), 2),
                         huellmass=round(t.innen_liste[-1][0] if len(konturzuege(kanten)) == 1 else max(form[1:]), 2))
                if rund:
                    d.update(art="Bohrung", durchmesser=rund[1], schraeg=schraeg(rund[0], normale))
                    ax = rund[0].Axis()
                    d["_achse"] = (ax.Location(), ax.Direction())
                elif form[0] == "Kreis":
                    d.update(art="Bohrung", durchmesser=round(form[1], 2))
                elif form[0] == "Langloch":
                    d.update(art="Langloch", laenge=round(form[1], 2), breite=round(form[2], 2),
                             richtung=round(lage, 1))
                elif form[0] == "Rechteck":
                    d.update(art="Rechteckausschnitt", laenge=round(form[1], 2), breite=round(form[2], 2),
                             richtung=round(lage, 1))
                else:
                    d.update(art="Ausschnitt", laenge=round(form[1], 2), breite=round(form[2], 2))
                liste.append(d)
        if m["art"] in enden:
            enden[m["art"]][0] += [faces.FindKey(f) for f in m["faces"]]
            enden[m["art"]][1] += laenge
        t.konturen += n
    # gegenüberliegende Bohrungen (gleiche Achse, gleicher Ø): eine Bohrung durch beide Wände
    bo = [d for d in liste if d.get("_achse")]
    for i, a_ in enumerate(bo):
        for b_ in bo[i + 1:]:
            (pa, da), (pb, db) = a_["_achse"], b_["_achse"]
            if a_["durchmesser"] == b_["durchmesser"] and abs(abs(da.Dot(db)) - 1) < 1e-6 and \
                    gp_Vec(pa, pb).Crossed(_vec(da)).Magnitude() < 0.01:
                a_["gegenueber"], b_["gegenueber"] = True, True
    for d in liste:
        d.pop("_achse", None)
    kopf = []
    for art_, name, z in (("EA", "Ende A", 0.0), ("EB", "Ende B", t.laenge)):
        fl, lg = enden[art_]
        e = _endform(fl, lg, ref) if fl else dict(form="nicht erkannt", gehrung=None, um_x=None, um_y=None,
                                              schnittlaenge=0.0)
        kopf.append(dict(art=name, durchgehend=True, z=round(z, 2), winkel=None, u=None, seite=None, **e))
    t.konturen_liste = kopf + sorted(liste, key=lambda d: (d["z"] is None, d["z"] or 0, d["winkel"] or 0))
    t.sicherheit["konturen"] = "wahrscheinlich" if any(
        d["art"] in ("Ausschnitt", "Innenmerkmal") or d.get("form") in ("komplex", "nicht erkannt") or
        d.get("seite") == "Ecke" for d in t.konturen_liste) else "sicher"
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


# ------------------------------------------------------------------ Bleche
# Ein Körper ist ein (ebenes) Blech, wenn er zwei parallele Hauptflächen hat, das Volumen der Hauptfläche mal ihrem
# Abstand entspricht (also überall gleich dick, keine Absätze oder Taschen) und die Dicke klein gegenüber der Breite
# ist. Die Dicke ist der Abstand der Hauptebenen, nicht die kleinste Kante des Hüllquaders: so stimmt sie auch bei
# gedrehten oder schräg liegenden Teilen. Länge und Breite kommen aus dem kleinsten umschreibenden Rechteck der
# Außenkontur in der Hauptebene.
# Flachstahl ist ein flacher Körper, der wie ein Stab aussieht (Patrick 20.10.2026, Frage 1 a): Breite bis
# FLACHSTAHL_BIS (Einstellung im Programm), Länge mindestens FLACHSTAHL_LAENGE × Breite und beide Längsseiten
# gerade über den größten Teil der Länge (Enden dürfen schräg oder ausgeklinkt sein). Alles andere Flache ist Blech.
FLACHSTAHL_BIS = 150.0          # mm
FLACHSTAHL_LAENGE = 3.0         # Länge mindestens 3 × Breite
BLECH_DICKE_ANTEIL = 0.2        # Dicke höchstens 1/5 der Breite
TOL_BLECH_VOLUMEN = 0.03        # Volumen = Hauptfläche × Dicke auf 3 %
TOL_EBENE = 0.01                # mm: Flächen in derselben Ebene
# Gleich dicke, gekantete Körper mit gleichbleibendem Querschnitt bleiben Profile (L, U, C, Kantprofil). Als
# gekantetes Blech gelten sie, wenn das Volumen deutlich unter Querschnitt × Länge liegt (Schenkel unterschiedlich
# lang oder ausgeschnitten, also kein Stangenmaterial).
GEKANTET_ANTEIL = 0.85


def _ebenen_gruppen(solid):
    """Ebene Flächen nach Normalenrichtung (ohne Vorzeichen) und Lage gruppiert:
    [(Richtung gp_Dir, [(Abstand, Fläche, [faces])])] – je Richtung die Ebenen, flächengrößte zuerst."""
    gruppen = []
    for f in _liste(solid, TopAbs_FACE):
        pl = _ebene(f)
        if pl is None:
            continue
        n, o = pl.Axis().Direction(), pl.Location()
        for g in gruppen:
            if abs(abs(g[0].Dot(n)) - 1) < 1e-5:
                break
        else:
            g = (n, [])
            gruppen.append(g)
        d = g[0]
        ab = o.X() * d.X() + o.Y() * d.Y() + o.Z() * d.Z()
        a = _flaeche(f)
        for e in g[1]:
            if abs(e[0] - ab) < TOL_EBENE:
                e[1] += a
                e[2].append(f)
                break
        else:
            g[1].append([ab, a, [f]])
    for g in gruppen:
        g[1].sort(key=lambda e: -e[1])
    return gruppen


def _zylinder_paare(solid, dicke, tol=0.02):
    """Fläche der Zylinderflächen, die paarweise koaxial im Abstand 'dicke' liegen (Biegezonen gekanteter Bleche)."""
    zyl = []
    for f in _liste(solid, TopAbs_FACE):
        sf = BRepAdaptor_Surface(TopoDS.Face(f))
        if sf.GetType() == GeomAbs_Cylinder:
            c = sf.Cylinder()
            zyl.append((c.Axis(), c.Radius(), _flaeche(f)))
    summe, benutzt = 0.0, set()
    for i, (ax1, r1, a1) in enumerate(zyl):
        for j in range(i + 1, len(zyl)):
            ax2, r2, a2 = zyl[j]
            if i in benutzt or j in benutzt or abs(abs(r1 - r2) - dicke) > tol:
                continue
            if abs(abs(ax1.Direction().Dot(ax2.Direction())) - 1) < 1e-5 and \
                    gp_Vec(ax1.Location(), ax2.Location()).Crossed(_vec(ax1.Direction())).Magnitude() < tol:
                summe += a1 + a2
                benutzt |= {i, j}
    return summe


def _flach_pruefen(solid, volumen):
    """Blechmerkmale eines Körpers oder None. Ergebnis dict: art 'eben' (Hauptflächen tragen das ganze Volumen)
    oder 'gekantet' (gleich dicke Schenkel in mindestens zwei Richtungen, verbunden über Biegezonen), dicke,
    hauptflaeche (Face), richtung (Normale), mitte (Punkt der Hauptebene)."""
    gruppen = _ebenen_gruppen(solid)
    kandidaten = [(g, g[1][0], g[1][1]) for g in gruppen if len(g[1]) >= 2]
    if not kandidaten or volumen <= 0:
        return None
    g, e1, e2 = max(kandidaten, key=lambda k: k[1][1])
    # die zweite Hauptfläche: die größte parallele Ebene in einem anderen Abstand
    dicke = abs(e1[0] - e2[0])
    if dicke < 0.05:
        return None
    haupt = max(e1[2], key=_flaeche)
    pl = _ebene(haupt)
    erg = dict(dicke=dicke, hauptflaeche=haupt, richtung=g[0], mitte=pl.Location(), flaeche_oben=e1[1],
               flaeche_unten=e2[1])
    # eben: nur diese beiden Ebenen in der Richtung (keine Absätze, Taschen oder Gravuren), Volumen = Fläche × Dicke
    weitere = [e for e in g[1][2:] if e[1] > 1e-3 * e1[1]]
    if not weitere and e2[1] >= 0.9 * e1[1] and \
            abs(volumen - min(e1[1], e2[1]) * dicke) <= TOL_BLECH_VOLUMEN * volumen:
        return dict(erg, art="eben")
    # gekantet: alle Ebenenpaare im Abstand 'dicke' (je Richtung) und koaxiale Biegezonen tragen das Volumen
    paare, richtungen = 0.0, 0
    for _, ebenen in gruppen:
        frei = sorted(ebenen, key=lambda e: e[0])
        gefunden = False
        while frei:
            a = frei.pop(0)
            b = next((x for x in frei if abs(abs(x[0] - a[0]) - dicke) < 0.02), None)
            if b is not None:
                frei.remove(b)
                paare += a[1] + b[1]
                gefunden = True
        richtungen += gefunden
    biegungen = _zylinder_paare(solid, dicke)
    paare += biegungen
    # ohne Biegezone (koaxiale Zylinder r und r + Dicke) ist es kein Kantteil, sondern z. B. ein T- oder L-Profil
    if biegungen > 0 and richtungen >= 2 and abs(volumen - paare / 2 * dicke) <= TOL_BLECH_VOLUMEN * 1.5 * volumen:
        return dict(erg, art="gekantet")
    return None


def _wire_kreis(draht):
    """Durchmesser, wenn der Draht ein Kreis ist (Kreiskanten mit gleichem Mittelpunkt und Radius), sonst None."""
    from OCP.GeomAbs import GeomAbs_Circle
    kreise = []
    for e in _liste(draht, TopAbs_EDGE):
        c = BRepAdaptor_Curve(TopoDS.Edge(e))
        if c.GetType() != GeomAbs_Circle:
            return None
        kreise.append(c.Circle())
    if not kreise:
        return None
    r, m = kreise[0].Radius(), kreise[0].Location()
    if all(abs(k.Radius() - r) < 1e-3 and k.Location().Distance(m) < 1e-3 for k in kreise):
        return round(2 * r, 3)
    return None


def _draht_laenge(draht):
    return sum(_kantenlaenge(e) for e in _liste(draht, TopAbs_EDGE))


def _blech_daten(solid, fl):
    """Maße eines ebenen Blechs in der Hauptebene: Länge/Breite (kleinstes umschreibendes Rechteck der Außenkontur),
    Kontur rechteckig/frei, Innenkonturen und Bohrungen, Längsseiten gerade (für die Abgrenzung zum Flachstahl).
    Dazu das System ax3 (Z = Länge, X = Breite, Y = Normale) für die 3D-Ansicht."""
    from OCP.BRepTools import BRepTools
    face = TopoDS.Face(fl["hauptflaeche"])
    n = fl["richtung"]
    ax0 = gp_Ax3(fl["mitte"], n)
    aussen = BRepTools.OuterWire_s(face)
    lok = _transformiere(aussen, ax0)
    st = _strecken(lok)
    pts = [(x, y) for x1, y1, x2, y2 in st for x, y in ((x1, y1), (x2, y2))]
    w = _min_rechteck(pts)
    c, s_ = math.cos(w), math.sin(w)
    us = [x * c + y * s_ for x, y in pts]
    vs = [-x * s_ + y * c for x, y in pts]
    laenge, breite = max(us) - min(us), max(vs) - min(vs)
    if breite > laenge:      # _min_rechteck liefert die Richtung der längeren Seite; zur Sicherheit
        laenge, breite = breite, laenge
        c, s_ = -s_, c
        us, vs = vs, [-u for u in us]
    # Längsseiten: gerade Abschnitte auf den beiden langen Seiten des Rechtecks
    seiten = [0.0, 0.0]
    for x1, y1, x2, y2 in st:
        v1, v2 = -x1 * s_ + y1 * c, -x2 * s_ + y2 * c
        lg = math.hypot(x2 - x1, y2 - y1)
        for k, grenze in enumerate((min(vs), max(vs))):
            if abs(v1 - grenze) < 0.05 and abs(v2 - grenze) < 0.05:
                seiten[k] += lg
    mf = BRepBuilderAPI_MakeFace(aussen, True)
    flaeche_aussen = _flaeche(mf.Face()) if mf.IsDone() else laenge * breite
    innen = [TopoDS.Wire(d) for d in _liste(face, TopAbs_WIRE) if not d.IsSame(aussen)]
    bohrungen, innen_liste, innen_laenge = {}, [], 0.0
    for d in innen:
        lg = _draht_laenge(d)
        innen_laenge += lg
        dm = _wire_kreis(d)
        if dm is not None:
            bohrungen[dm] = bohrungen.get(dm, 0) + 1
        b = Bnd_Box()
        BRepBndLib.AddOptimal_s(d, b, False, False)
        q0, q1 = b.CornerMin(), b.CornerMax()
        innen_liste.append((round(max(q1.X() - q0.X(), q1.Y() - q0.Y(), q1.Z() - q0.Z()), 2), round(lg, 2)))
    # System für die 3D-Ansicht und Lage in der Datei: Z = Längsrichtung, Y = Normale der Hauptfläche
    xd, yd = ax0.XDirection(), ax0.YDirection()
    lr = _vec(xd).Multiplied(c).Added(_vec(yd).Multiplied(s_))
    ax3 = gp_Ax3(fl["mitte"], gp_Dir(lr.X(), lr.Y(), lr.Z()), gp_Dir(_vec(n).Crossed(lr).X(), _vec(n).Crossed(lr).Y(),
                                                                       _vec(n).Crossed(lr).Z()))
    rechteckig = abs(flaeche_aussen - laenge * breite) <= 0.002 * laenge * breite
    return dict(laenge=laenge, breite=breite, dicke=fl["dicke"], flaeche_aussen=flaeche_aussen,
                flaeche_netto=_flaeche(face), umfang_aussen=_draht_laenge(aussen), umfang_innen=innen_laenge,
                innen=len(innen), bohrungen=dict(sorted(bohrungen.items())), innen_liste=innen_liste,
                kontur="rechteckig" if rechteckig else "frei", laengsseiten_gerade=min(seiten) >= 0.8 * laenge,
                ax3=ax3)


def ist_flachstahl(laenge, breite, laengsseiten_gerade, flach_bis=FLACHSTAHL_BIS):
    """Abgrenzung Flachstahl/Blech (Frage 1 a): stabförmig, schmal, gerade Längsseiten."""
    return laengsseiten_gerade and breite <= flach_bis + 1e-6 and laenge >= FLACHSTAHL_LAENGE * breite - 1e-6


def fingerabdruck(b):
    """Geometrie-Fingerabdruck eines Blechs für den Dublettenvergleich (gerundete Kennwerte als Text)."""
    bo = ",".join(f"{d:g}x{n}" for d, n in b.get("bohrungen", {}).items())
    return (f"{b['dicke']:.1f}|{b['laenge']:.0f}|{b['breite']:.0f}|{b.get('flaeche_netto', 0):.0f}|"
            f"{b.get('umfang_aussen', 0) + b.get('umfang_innen', 0):.0f}|{b.get('innen', 0)}|{bo}")


def _blech_teil(solid, datei, koerper, fl, volumen, netz, daten=None):
    """Teil für ein ebenes oder gekantetes Blech."""
    t = Teil(datei=datei, koerper=koerper)
    d = fl["dicke"]
    if fl["art"] == "eben":
        b = daten or _blech_daten(solid, fl)
        ax3 = b.pop("ax3")
        t.bauteiltyp = t.profilform = "Blech"
        t.abm_a, t.abm_b, t.wandstaerke, t.laenge = b["laenge"], b["breite"], d, b["laenge"]
        t.bohrungen, t.innen_liste, t.innen_konturen = b["bohrungen"], b["innen_liste"], b["innen"]
        t.innen, t.konturen = b["umfang_innen"], 1 + b["innen"]
        t.schneidweg = b["umfang_aussen"] + b["umfang_innen"]
        t.sicherheit.update(profil="sicher", laenge="sicher", wandstaerke="sicher", konturen="nicht ausgewertet")
        b.pop("laengsseiten_gerade", None)
    else:
        # Außenmaße im System der Hauptfläche: Grundriss = kleinstes umschreibendes Rechteck, Höhe = senkrecht dazu
        ax0 = gp_Ax3(fl["mitte"], fl["richtung"])
        lok0 = _transformiere(solid, ax0)
        pts = [(x, y) for x1, y1, x2, y2 in _strecken(lok0, 2.0) for x, y in ((x1, y1), (x2, y2))]
        w = _min_rechteck(pts)
        c, s_ = math.cos(w), math.sin(w)
        us, vs = [x * c + y * s_ for x, y in pts], [-x * s_ + y * c for x, y in pts]
        z0, z1 = _z_bereich(lok0)
        masse = sorted((max(us) - min(us), max(vs) - min(vs), z1 - z0), reverse=True)
        t.bauteiltyp = t.profilform = "Blech gekantet"
        t.abm_a, t.abm_b, t.wandstaerke, t.laenge = masse[0], masse[1], d, masse[0]
        b = dict(laenge=masse[0], breite=masse[1], hoehe=masse[2], dicke=d, kontur="gekantet",
                 abwicklung_flaeche=volumen / d, flaeche_netto=volumen / d, umfang_aussen=0.0, umfang_innen=0.0,
                 innen=0, bohrungen={}, innen_liste=[])
        t.sicherheit.update(profil="wahrscheinlich", laenge="wahrscheinlich", wandstaerke="sicher",
                            konturen="nicht ausgewertet")
        t.hinweise.append(f"Gekantetes Blech: Außenmaße {masse[0]:.1f} × {masse[1]:.1f} × {masse[2]:.1f} mm, "
                          f"Abwicklung ca. {volumen / d / 1e6:.4f} m² (ohne Biegefaktor), Zuschnitt prüfen")
        lr = _vec(ax0.XDirection()).Multiplied(c).Added(_vec(ax0.YDirection()).Multiplied(s_))
        ax3 = gp_Ax3(fl["mitte"], gp_Dir(lr.X(), lr.Y(), lr.Z()), fl["richtung"])
    b["volumen"] = volumen
    b["fingerabdruck"] = fingerabdruck(b)
    t.blech = b
    t.flaeche = 0.0       # kein Profilquerschnitt
    lok = _transformiere(solid, ax3)
    zmin, _ = _z_bereich(lok)
    dz, p = ax3.Direction(), _global(ax3, 0, 0, zmin)
    t.achse_global, t.ende_a_global = (dz.X(), dz.Y(), dz.Z()), (p.X(), p.Y(), p.Z())
    if netz:
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(lok, TopAbs_FACE, faces)
        t.netz = dreiecksnetz(lok, faces, {i: "A" for i in range(1, faces.Extent() + 1)}, [], zmin, t.abm_a)
    return t


def analysiere(solid, datei="", koerper=1, netz=False, flach_bis=FLACHSTAHL_BIS):
    """Ein Körper: zuerst die Blechprüfung (ebene Bleche, die kein Flachstahl sind, werden als Blech gemessen), sonst
    die Profilmessung. Gekantete Bleche gelten nur dann als Blech, wenn die Profilmessung keinen gleichbleibenden
    Querschnitt findet (ein Kantprofil mit konstantem Querschnitt bleibt L/U/C-Profil)."""
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, p)
    volumen = abs(p.Mass())
    try:
        fl = _flach_pruefen(solid, volumen)
    except Exception:  # Blechprüfung darf die Profilmessung nie verhindern
        fl = None
    if fl and fl["art"] == "eben":
        daten = _blech_daten(solid, fl)
        dicke_ok = fl["dicke"] <= BLECH_DICKE_ANTEIL * daten["breite"] + 1e-6
        if dicke_ok and not ist_flachstahl(daten["laenge"], daten["breite"], daten["laengsseiten_gerade"], flach_bis):
            return _blech_teil(solid, datei, koerper, fl, volumen, netz, daten)
    t = None
    try:
        t = _profil_messen(solid, datei, koerper, netz)
    except Exception:
        if not (fl and fl["art"] == "gekantet"):
            raise
    if fl and fl["art"] == "gekantet" and (t is None or not t.profilform or t.sicherheit.get("achse") != "sicher"
                                           or t.profilform == "offenes Sonderprofil" or volumen < GEKANTET_ANTEIL * t.flaeche * t.laenge):
        return _blech_teil(solid, datei, koerper, fl, volumen, netz)
    if t.profilform:
        t.bauteiltyp = "Profil"
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


def analysiere_datei(pfad, netz=False, flach_bis=FLACHSTAHL_BIS):
    """Alle Körper einer STEP-Datei messen. Je Körper ein Teil, auch für nicht messbare (Flächenmodell offen,
    Messfehler) – mit Hinweis statt Maßen. Wirft ValueError, wenn die Datei nicht lesbar ist."""
    from pathlib import Path
    name = Path(pfad).stem
    koerper, info = lies_step_info(pfad)
    if not koerper:
        t = Teil(datei=name, koerper=0, einheit=info["einheit"], meldungen=info["meldungen"])
        t.hinweise.append("Kein Körper und keine Fläche in der Datei")
        return [t]
    out = []
    for i, (art, k) in enumerate(koerper, start=1):
        if art == "Flächenmodell offen":
            t = Teil(datei=name, koerper=i)
            t.hinweise.append("Flächenmodell nicht geschlossen, nicht messbar")
        else:
            try:
                t = analysiere(k, name, i, netz, flach_bis)
            except Exception as e:  # Messung dieses Körpers gescheitert: melden, andere Körper weiter messen
                t = Teil(datei=name, koerper=i)
                t.hinweise.append(f"Messung fehlgeschlagen: {e or type(e).__name__}")
        t.einheit, t.meldungen = info["einheit"], info["meldungen"]
        if t.meldungen:
            t.hinweise.append(f"STEP-Leser meldet: {t.meldungen[0]}"
                              + (f" (+{len(t.meldungen) - 1} weitere)" if len(t.meldungen) > 1 else ""))
        _koerper_daten(t, k, art)
        out.append(t)
    return out
