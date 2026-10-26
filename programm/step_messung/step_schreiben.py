"""STEP-Export (Plan 3D-Editor 3E-8, Patrick 24.10.2026): baut aus einem Bauplan (JSON, programm/rohrlaser/
step_export.py) echte Volumenkörper mit OpenCascade und schreibt sie als STEP (AP214, mm).

Wie die Messung läuft das als eigener Prozess (STEP-Import.exe --export …): OpenCascade bleibt aus dem Programm
heraus. Der Bauplan beschreibt je Teil einen Grundkörper mit echten Radien und Bögen und die Werkzeuge, die
abgezogen werden:

- Grundkörper 'rohr': Querschnitt (Kreis oder Eckpunkte mit Bulge = Bogen zum nächsten Punkt) außen und innen,
  entlang Z von 0 bis laenge. 'platte': Außenkontur mit Löchern, entlang Z um die Dicke.
- Gekantete Platte (3E-13): 'platte' mit 'biegungen' (Abwicklung, wie die 3D-Ansicht blech3d): die ebene Platte samt
  Löchern und Gravur wird gefaltet. Ebene Stücke zwischen den Biegezonen werden starr gedreht, jede Biegezone ist ein
  Drehkörper um die Biegeachse (Innenradius ri, neutrale Faser = Bogenlänge ba). Was in einer Biegezone fehlt (Loch,
  Außenkontur), wird als gefaltetes Netz abgezogen; danach werden alle Stücke vereinigt.
- Werkzeuge: 'ebene' (Halbraum auf der Seite der Normalen), 'zylinder' (Bohrung), 'quader' (Gravurrille),
  'prisma' (Vieleck in XY entlang Z), 'flach' (Kontur mit Bögen auf einer ebenen Wand, senkrecht hindurch), 'netz' (geschlossenes Dreiecksnetz, z. B. Schnitt eines Endes, Ausklinkung).
  Jedes Werkzeug kann 'ohne': [Werkzeuge] haben, die vorher von ihm abgezogen werden (Nasen einer Steckverbindung
  bleiben stehen).

- Baugruppe (3E-14): mit 'baugruppe' {name, kinder: [Unterbaugruppen wie oben], einsatz: [{teil: Nr. in teile,
  lage: 3 × 4 Matrix | ausrichten: {p, t} (Netz der STEP-Messung in der Datei: Lage durch Ausrichten der
  Hauptträgheitsachsen und Abgleich der Oberfläche) | daneben: true (ohne Lage, neben die Baugruppe)}]} wird jedes
  Teil einmal gebaut und als Komponente eingesetzt (echte STEP-Baugruppe). Grundkörper 'netz' = Dreiecksnetz {p, t}
  (Teil, das nur als Netz der STEP-Messung vorliegt).

Aufruf:
    STEP-Import.exe --export BAUPLAN.json --step ZIEL.step [--ergebnis ERGEBNIS.json]
    python step_schreiben.py BAUPLAN.json ZIEL.step [ERGEBNIS.json]

ERGEBNIS.json: {"ok": true/false, "teile": [{"name", "gueltig", "volumen", "flaechen", "meldungen"}], "fehler"}.
Rückgabewert 0 = geschrieben, 1 = Fehler.
"""
import json
import math
import sys
from pathlib import Path

GROSS = 1.0e5           # halbe Kantenlänge der Ebene für den Halbraum [mm]
NAEHEN_TOL = 1e-4       # Toleranz beim Nähen der Dreiecksnetze [mm]


def _pnt(p):
    from OCP.gp import gp_Pnt
    return gp_Pnt(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)


def _dir(v):
    from OCP.gp import gp_Dir
    return gp_Dir(float(v[0]), float(v[1]), float(v[2]))


def _kante(a, b, bulge, z):
    """Kante von a nach b in der Ebene z: Gerade oder Kreisbogen (Bulge = tan(Öffnungswinkel / 4), + = gegen den
    Uhrzeigersinn)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.GC import GC_MakeArcOfCircle
    if abs(bulge) < 1e-9:
        return BRepBuilderAPI_MakeEdge(_pnt((a[0], a[1], z)), _pnt((b[0], b[1], z))).Edge()
    th = 4 * math.atan(bulge)
    c = math.dist(a, b)
    r = c / (2 * math.sin(abs(th) / 2))
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    nx, ny = -(b[1] - a[1]) / c, (b[0] - a[0]) / c          # links von a -> b
    s = 1 if th > 0 else -1
    d = r * math.cos(th / 2)
    cx, cy = mx + nx * d * s, my + ny * d * s
    w = math.atan2(a[1] - cy, a[0] - cx) + th / 2           # Mitte des Bogens
    m = (cx + r * math.cos(w), cy + r * math.sin(w), z)
    bogen = GC_MakeArcOfCircle(_pnt((a[0], a[1], z)), _pnt(m), _pnt((b[0], b[1], z))).Value()
    return BRepBuilderAPI_MakeEdge(bogen).Edge()


def draht(kontur, z=0.0):
    """Geschlossener Draht aus {"kreis": [cx, cy, r]} oder {"punkte": [[x, y, bulge], …]}."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Ax2, gp_Circ
    if kontur.get("kreis"):
        cx, cy, r = kontur["kreis"]
        kreis = gp_Circ(gp_Ax2(_pnt((cx, cy, z)), _dir((0, 0, 1))), float(r))
        return BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(kreis).Edge()).Wire()
    pk = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in kontur["punkte"]]
    pk = [p for i, p in enumerate(pk) if math.dist(p[:2], pk[i - 1][:2]) > 1e-7]     # doppelte Punkte weg
    w = BRepBuilderAPI_MakeWire()
    for i, a in enumerate(pk):
        b = pk[(i + 1) % len(pk)]
        w.Add(_kante(a[:2], b[:2], a[2], z))
    if not w.IsDone():
        raise ValueError("Kontur nicht geschlossen")
    return w.Wire()


def flaeche(aussen, loecher=(), z=0.0):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    mf = BRepBuilderAPI_MakeFace(draht(aussen, z), True)
    for k in loecher:
        w = draht(k, z)
        w.Reverse()
        mf.Add(w)
    if not mf.IsDone():
        raise ValueError("Fläche nicht erzeugt")
    from OCP.ShapeFix import ShapeFix_Face
    fix = ShapeFix_Face(mf.Face())
    fix.Perform()                   # Löcher richtig herum
    return fix.Face()


def _prisma(f, h, richtung=(0, 0, 1)):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec
    return BRepPrimAPI_MakePrism(f, gp_Vec(*(float(c) * h for c in richtung))).Shape()


def grundkoerper(k):
    if k["art"] == "rohr":
        f = flaeche(k["aussen"], [k["innen"]] if k.get("innen") else [])
        return _prisma(f, float(k["laenge"]))
    if k["art"] == "platte":
        f = flaeche(k["aussen"], k.get("loecher") or [])
        return _prisma(f, float(k["dicke"]))
    if k["art"] == "netz":
        return netz_koerper(k["p"], k["t"])
    if k["art"] == "step":
        return step_koerper(k["pfad"], k.get("matrix"))
    raise ValueError(f"Grundkörper {k['art']!r} unbekannt")


def step_koerper(pfad, matrix=None):
    """Körper aus einer STEP-Datei (virtuelles Bauteil der Messung, exakt statt facettiert), mit matrix (3 × 4
    zeilenweise) in das System des Teils gebracht."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    r = STEPControl_Reader()
    if r.ReadFile(str(pfad)) != IFSelect_RetDone or not r.TransferRoots():
        raise ValueError(f"STEP nicht lesbar: {pfad}")
    k = r.OneShape()
    if k is None or k.IsNull():
        raise ValueError(f"STEP ohne Körper: {pfad}")
    return BRepBuilderAPI_Transform(k, _trsf(matrix), True).Shape() if matrix else k


def netz_koerper(p, t):
    """Geschlossenes Dreiecksnetz (Punkte flach x, y, z …, Dreiecke i, j, k …) als Volumenkörper."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    pts = [_pnt(p[i:i + 3]) for i in range(0, len(p), 3)]
    naehen = BRepBuilderAPI_Sewing(NAEHEN_TOL)
    n = 0
    for i in range(0, len(t), 3):
        a, b, c = pts[t[i]], pts[t[i + 1]], pts[t[i + 2]]
        if a.Distance(b) < 1e-7 or b.Distance(c) < 1e-7 or a.Distance(c) < 1e-7:
            continue
        poly = BRepBuilderAPI_MakePolygon(a, b, c, True)
        mf = BRepBuilderAPI_MakeFace(poly.Wire(), True)
        if mf.IsDone():
            naehen.Add(mf.Face())
            n += 1
    if not n:
        raise ValueError("leeres Netz")
    naehen.Perform()
    genaeht = naehen.SewedShape()
    ex = TopExp_Explorer(genaeht, TopAbs_SHELL)
    if not ex.More():
        raise ValueError("Netz nicht geschlossen")
    ms = BRepBuilderAPI_MakeSolid()
    while ex.More():
        ms.Add(TopoDS.Shell(ex.Current()))
        ex.Next()
    fix = ShapeFix_Solid(ms.Solid())
    fix.Perform()
    k = fix.Solid()
    if _volumen(k) < 0:             # Dreiecke andersherum: Körper umdrehen
        k = TopoDS.Solid(k.Reversed())
    return k


def _volumen(k):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(k, g)
    return g.Mass()


def werkzeug(w):
    """Werkzeug als Körper (siehe Kopf)."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeHalfSpace
    from OCP.gp import gp_Ax2, gp_Pln
    art = w["art"]
    if art == "ebene":
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        pln = gp_Pln(_pnt(w["p"]), _dir(w["n"]))
        f = BRepBuilderAPI_MakeFace(pln, -GROSS, GROSS, -GROSS, GROSS).Face()
        ref = [w["p"][i] + w["n"][i] for i in range(3)]
        k = BRepPrimAPI_MakeHalfSpace(f, _pnt(ref)).Solid()
    elif art == "zylinder":
        k = BRepPrimAPI_MakeCylinder(gp_Ax2(_pnt(w["p"]), _dir(w["achse"])), float(w["r"]), float(w["h"])).Shape()
    elif art == "quader":
        k = BRepPrimAPI_MakeBox(gp_Ax2(_pnt(w["p"]), _dir(w["z"]), _dir(w["x"])), float(w["l"]), float(w["b"]),
                                float(w["h"])).Shape()
    elif art == "prisma":
        f = flaeche({"punkte": w["punkte"]}, z=float(w["z0"]))
        k = _prisma(f, float(w["z1"]) - float(w["z0"]))
    elif art == "netz":
        k = netz_koerper(w["p"], w["t"])
    elif art == "flach":            # Kontur in der Ebene (o, Normale n, Richtung x), entlang −n um h
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Ax3, gp_Trsf
        tr = gp_Trsf()
        tr.SetDisplacement(gp_Ax3(), gp_Ax3(_pnt(w["o"]), _dir(w["n"]), _dir(w["x"])))
        f = BRepBuilderAPI_Transform(flaeche(w["kontur"]), tr, True).Shape()
        k = _prisma(f, -float(w["h"]), w["n"])
    else:
        raise ValueError(f"Werkzeug {art!r} unbekannt")
    if w.get("ohne"):
        k = abziehen(k, [werkzeug(x) for x in w["ohne"]])
    return k


def abziehen(k, werkzeuge):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    try:  # OCP >= 7.8
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    except ImportError:
        from OCP.TopTools import TopTools_ListOfShape
    if not werkzeuge:
        return k
    arg, wz = TopTools_ListOfShape(), TopTools_ListOfShape()
    arg.Append(k)
    for w in werkzeuge:
        wz.Append(w)
    cut = BRepAlgoAPI_Cut()
    cut.SetArguments(arg)
    cut.SetTools(wz)
    cut.SetRunParallel(True)
    cut.Build()
    if not cut.IsDone():
        raise ValueError("Boolesche Operation fehlgeschlagen")
    return cut.Shape()


GRUPPE_SPALT = 0.05     # Hüllquader so weit vergrößert prüfen: Werkzeuge mit kleinerem Abstand gelten als überlappend [mm]
GRUPPE_ZELLEN = 4000    # Werkzeuge über so viele Rasterzellen allein abziehen
GRUPPE_GROSS = 1.0e4    # Werkzeuge mit größerem Hüllquader (Halbraum der Enden) immer einzeln abziehen [mm]


def _huelle(w):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.Add_s(w, b)
    if b.IsVoid():
        return None
    a, c = b.CornerMin(), b.CornerMax()
    x0, y0, z0, x1, y1, z1 = a.X(), a.Y(), a.Z(), c.X(), c.Y(), c.Z()
    if max(x1 - x0, y1 - y0, z1 - z0) > GRUPPE_GROSS:
        return None
    s = GRUPPE_SPALT
    return (x0 - s, y0 - s, z0 - s, x1 + s, y1 + s, z1 + s)


def werkzeug_gruppen(werkzeuge, huelle=_huelle):
    """Werkzeuge in Gruppen, deren Hüllquader sich nicht berühren: eine Gruppe wird in einer Operation abgezogen
    (Performance-Update P4: 1.000 Bohrungen in wenigen Durchgängen statt 1.000 einzelnen). Werkzeuge, deren
    Hüllquader sich berühren, und sehr große (Halbraum) kommen in verschiedene Gruppen bzw. allein; die Reihenfolge
    im Ergebnis ist egal, Abziehen ist vertauschbar."""
    gruppen, raster, zelle = [], [], None
    allein = []
    boxen = []
    for w in werkzeuge:
        b = huelle(w)
        if b is None:
            allein.append([w])
        else:
            boxen.append((w, b))
    if boxen:
        groessen = sorted(max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) for _, b in boxen)
        zelle = max(groessen[len(groessen) // 2], 1.0)

    def zellen(b):
        return [(i, j, k) for i in range(int(b[0] // zelle), int(b[3] // zelle) + 1)
                for j in range(int(b[1] // zelle), int(b[4] // zelle) + 1)
                for k in range(int(b[2] // zelle), int(b[5] // zelle) + 1)]

    def beruehrt(a, b):
        return a[0] <= b[3] and b[0] <= a[3] and a[1] <= b[4] and b[1] <= a[4] and a[2] <= b[5] and b[2] <= a[5]

    for w, b in boxen:
        n = 1
        for a in range(3):
            n *= int(b[a + 3] // zelle) - int(b[a] // zelle) + 1
        if n > GRUPPE_ZELLEN:           # viel größer als die übrigen (Ende, lange Kontur): allein
            allein.append([w])
            continue
        z = zellen(b)
        for g, r in zip(gruppen, raster):
            if not any(beruehrt(b, a) for c in z for a in r.get(c, ())):
                break
        else:
            g, r = [], {}
            gruppen.append(g)
            raster.append(r)
        g.append(w)
        for c in z:
            r.setdefault(c, []).append(b)
    return allein + gruppen


def vereinfachen(k):
    """Gleiche Flächen zusammenlegen (ebene Dreiecke eines Werkzeugs werden eine Fläche)."""
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    u = ShapeUpgrade_UnifySameDomain(k, True, True, True)
    u.Build()
    return u.Shape()


def _kennwerte(k):
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(k, g)

    def anzahl(typ):
        ex, n = TopExp_Explorer(k, typ), 0
        while ex.More():
            n += 1
            ex.Next()
        return n
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(k, box, False, False)
    return dict(gueltig=bool(BRepCheck_Analyzer(k).IsValid()), volumen=round(g.Mass(), 3),
                flaechen=anzahl(TopAbs_FACE), koerper=anzahl(TopAbs_SOLID),
                box=[round(c, 4) for c in (box.CornerMin().X(), box.CornerMin().Y(), box.CornerMin().Z(),
                                           box.CornerMax().X(), box.CornerMax().Y(), box.CornerMax().Z())])


# ------------------------------------------------------------------ gekantete Platte (3E-13)


def _biegung(b, s):
    """Biegung des Bauplans mit Rechengrößen: Achse (Punkt, Richtung), Winkel."""
    phi = float(b["phi"])
    oben = 1.0 if phi > 0 else -1.0
    o, n, d = [float(c) for c in b["o"]], [float(c) for c in b["n"]], [float(c) for c in b["d"]]
    return dict(b, o=o, n=n, d=d, ba=float(b["ba"]), winkel=abs(phi), t=[float(c) for c in b["t"]],
                achse_p=(o[0], o[1], oben * (s / 2 + float(b["ri"]))), achse_d=(n[1] * oben, -n[0] * oben, 0.0))


def _w_t(b, x, y):
    return (x - b["o"][0]) * b["n"][0] + (y - b["o"][1]) * b["n"][1], x * b["d"][0] + y * b["d"][1]


def _wirksam(bg, x, y, ohne=None, tol=1e-6):
    """Biegungen, hinter denen (bzw. in deren Zone) der Punkt der Abwicklung liegt, die äußerste zuerst."""
    out = []
    for b in bg:
        if b is ohne:
            continue
        w, t = _w_t(b, x, y)
        if w > tol and b["t"][0] + tol - 1e-6 <= t <= b["t"][1] - tol + 1e-6:
            out.append((b["abstand"], b, min(w, b["ba"])))
    return [(b, w) for _, b, w in sorted(out, key=lambda z: -z[0])]


def _trsf_biegung(b, w):
    """Starre Lage nach w mm der Biegung b: um −n·w schieben, dann um die Achse um winkel·w/ba drehen."""
    from OCP.gp import gp_Ax1, gp_Trsf, gp_Vec
    sch, dreh = gp_Trsf(), gp_Trsf()
    sch.SetTranslation(gp_Vec(-b["n"][0] * w, -b["n"][1] * w, 0.0))
    dreh.SetRotation(gp_Ax1(_pnt(b["achse_p"]), _dir(b["achse_d"])), b["winkel"] * w / b["ba"])
    return dreh.Multiplied(sch)


def _trsf_kette(kette):
    from OCP.gp import gp_Trsf
    t = gp_Trsf()
    for b, w in kette:                      # äußerste zuerst: jede weitere wirkt danach
        t = _trsf_biegung(b, w).Multiplied(t)
    return t


def _bewegt(k, trsf):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    return BRepBuilderAPI_Transform(k, trsf, True).Shape()


def _zone_prisma(b, lo, hi, z0, z1, rand=0.0, w0=0.0, w1=None):
    """Quader der Biegezone (Abwicklung) von z0 bis z1, längs der Biegelinie lo … hi (quer w0 … w1, Vorgabe die
    ganze Zone)."""
    o, n, d = b["o"], b["n"], b["d"]
    w1 = b["ba"] if w1 is None else w1
    ecken = []
    for w, t in ((w0 - rand, lo), (w1 + rand, lo), (w1 + rand, hi), (w0 - rand, hi)):
        ecken.append([o[0] + n[0] * w + d[0] * (t - (o[0] * d[0] + o[1] * d[1])),
                      o[1] + n[1] * w + d[1] * (t - (o[0] * d[0] + o[1] * d[1])), 0.0])
    if (ecken[1][0] - ecken[0][0]) * (ecken[2][1] - ecken[0][1]) - (ecken[1][1] - ecken[0][1]) * \
            (ecken[2][0] - ecken[0][0]) < 0:
        ecken.reverse()
    return werkzeug(dict(art="prisma", punkte=ecken, z0=z0, z1=z1))


def _feste_koerper(k):
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    out, ex = [], TopExp_Explorer(k, TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def _schwerpunkt(k):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(k, g)
    c = g.CentreOfMass()
    return c.X(), c.Y(), c.Z(), g.Mass()


def _ecken(k):
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    out, ex = [], TopExp_Explorer(k, TopAbs_VERTEX)
    while ex.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current()))
        out.append((p.X(), p.Y()))
        ex.Next()
    return out


def _boden_zuege(k, z0):
    """Je Kante des Umrisses von k in der Ebene z0 die Punkte [(x, y)] (Kanten der Reihe nach, Bögen fein)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Plane
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    ex = TopExp_Explorer(k, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face(ex.Current())
        ex.Next()
        fl = BRepAdaptor_Surface(f)
        if fl.GetType() != GeomAbs_Plane:
            continue
        pl = fl.Plane()
        if abs(abs(pl.Axis().Direction().Z()) - 1) > 1e-9 or abs(pl.Location().Z() - z0) > 1e-6:
            continue
        zuege = []
        we = BRepTools_WireExplorer(BRepTools.OuterWire_s(f))
        while we.More():
            e = we.Current()
            c = BRepAdaptor_Curve(e)
            u0, u1 = c.FirstParameter(), c.LastParameter()
            n = 2 if c.GetType() == GeomAbs_Line else 33
            pk = [c.Value(u0 + (u1 - u0) * i / (n - 1)) for i in range(n)]
            pk = [(p.X(), p.Y()) for p in pk]
            if e.Orientation() == TopAbs_REVERSED:
                pk.reverse()
            zuege.append(pk)
            we.Next()
        return zuege
    return []


def _gefaltetes_werkzeug(f, b, z0, z1):
    """Fehlendes Stück f (Prisma z0 … z1 in der Abwicklung) in der Zone von b gefaltet: Regelfläche je Kante
    zwischen Unter- und Oberseite (B-Spline durch die gefalteten Punkte), als Volumenkörper."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.GeomAPI import GeomAPI_PointsToBSpline
    try:  # OCP >= 7.8
        from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
    except ImportError:
        from OCP.TColgp import TColgp_Array1OfPnt
    zuege = _boden_zuege(f, z0)
    if not zuege:
        raise ValueError("Umriss nicht gefunden")

    def gefaltet(x, y, z):
        w = min(max(_w_t(b, x, y)[0], 0.0), b["ba"])
        return _pnt((x, y, z)).Transformed(_trsf_biegung(b, w))

    draehte = []
    for z in (z0, z1):
        mw = BRepBuilderAPI_MakeWire()
        for pk in zuege:
            dw = abs(_w_t(b, *pk[-1])[0] - _w_t(b, *pk[0])[0])
            if len(pk) == 2 and dw > 1e-6:          # Gerade quer zur Biegelinie: folgt dem Bogen
                pk = [(pk[0][0] + (pk[1][0] - pk[0][0]) * i / 24, pk[0][1] + (pk[1][1] - pk[0][1]) * i / 24)
                      for i in range(25)]
            pts = [gefaltet(x, y, z) for x, y in pk]
            if len(pts) == 2:
                mw.Add(BRepBuilderAPI_MakeEdge(pts[0], pts[1]).Edge())
                continue
            arr = TColgp_Array1OfPnt(1, len(pts))
            for i, p in enumerate(pts):
                arr.SetValue(i + 1, p)
            mw.Add(BRepBuilderAPI_MakeEdge(GeomAPI_PointsToBSpline(arr, 3, 8, GeomAbs_C2, 1e-5).Curve()).Edge())
        if not mw.IsDone():
            raise ValueError("Umriss nicht geschlossen")
        draehte.append(mw.Wire())
    ts = BRepOffsetAPI_ThruSections(True, True, 1e-6)
    for d in draehte:
        ts.AddWire(d)
    ts.CheckCompatibility(False)
    ts.Build()
    if not ts.IsDone():
        raise ValueError("Regelfläche nicht erzeugt")
    from OCP.TopoDS import TopoDS
    k = TopoDS.Solid(ts.Shape())
    return TopoDS.Solid(k.Reversed()) if _volumen(k) < 0 else k


def _gemeinsam(a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    c = BRepAlgoAPI_Common(a, b)
    c.Build()
    return c.Shape() if c.IsDone() else None


def _gefaltete_scheiben(f, b, lo, hi, s, n=16):
    """Stück f einer Gravurrille in der Zone von b gefaltet: in n Scheiben quer zur Biegelinie, jede mit der Lage
    ihrer Mitte (Fehler bei 16 Scheiben unter 0,01 mm, für die 0,1 mm tiefe Rille genug)."""
    out = []
    for i in range(n):
        w0, w1 = b["ba"] * i / n, b["ba"] * (i + 1) / n
        stueck = _gemeinsam(f, _zone_prisma(b, lo, hi, -s, s, rand=1e-3, w0=w0, w1=w1))
        for x in _feste_koerper(stueck) if stueck is not None else ():
            if _schwerpunkt(x)[3] > 1e-12:
                out.append(_bewegt(x, _trsf_biegung(b, (w0 + w1) / 2)))
    return out


def platte_falten(k, koerper, meldungen, rillen=()):
    """Ebene Platte k (z von 0 bis s, mit Löchern und Gravur) an den Biegungen falten -> ein Körper. rillen: die
    Gravurwerkzeuge (Körper wie k); was davon in einer Biegezone liegt, wird mitgefaltet und dort abgezogen."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.gp import gp_Ax1, gp_Trsf, gp_Vec
    try:  # OCP >= 7.8
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    except ImportError:
        from OCP.TopTools import TopTools_ListOfShape
    s = float(koerper["dicke"])
    halb = gp_Trsf()
    halb.SetTranslation(gp_Vec(0, 0, -s / 2))
    k = _bewegt(k, halb)                                # Mittelfläche z = 0
    bg = [_biegung(b, s) for b in koerper["biegungen"]]
    umriss = flaeche(koerper["aussen"], koerper.get("loecher") or [])       # Abwicklung in z = 0
    xs = [p[0] for p in _ecken(k)]
    ys = [p[1] for p in _ecken(k)]
    stuecke, zonen = [], []
    for b in bg:
        ts = [x * b["d"][0] + y * b["d"][1] for x in (min(xs), max(xs)) for y in (min(ys), max(ys))]
        lo, hi = max(b["t"][0], min(ts)), min(b["t"][1], max(ts))
        zonen.append((b, lo, hi))
    flach = abziehen(k, [_zone_prisma(b, lo, hi, -s, s) for b, lo, hi in zonen])
    ohne_freischnitt = 0
    for f in _feste_koerper(flach):
        x, y, _, vol = _schwerpunkt(f)
        if vol < 1e-6:
            continue
        kette = _wirksam(bg, x, y)
        satz = {id(b) for b, _ in kette}
        for px, py in _ecken(f):
            andere = {id(b) for b, _ in _wirksam(bg, px, py, tol=1e-3)}
            if andere - satz:
                ohne_freischnitt += 1
                break
        stuecke.append(_bewegt(f, _trsf_kette([(b, b["ba"]) for b, _ in kette])) if kette else f)
    if ohne_freischnitt:
        meldungen.append(f"{ohne_freischnitt} ebene Stücke reichen über eine Biegung ohne Freischnitt: Lage prüfen")
    for b, lo, hi in zonen:
        o, d = b["o"], b["d"]
        t0 = o[0] * d[0] + o[1] * d[1]
        a0 = (o[0] + d[0] * (lo - t0), o[1] + d[1] * (lo - t0))
        a1 = (o[0] + d[0] * (hi - t0), o[1] + d[1] * (hi - t0))
        poly = BRepBuilderAPI_MakePolygon(_pnt((a0[0], a0[1], -s / 2)), _pnt((a1[0], a1[1], -s / 2)),
                                          _pnt((a1[0], a1[1], s / 2)), _pnt((a0[0], a0[1], s / 2)), True)
        start = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
        bogen = BRepPrimAPI_MakeRevol(start, gp_Ax1(_pnt(b["achse_p"]), _dir(b["achse_d"])), b["winkel"]).Shape()
        ri = float(b["ri"])
        innen = min(1.0, 0.5 * ri) if ri > 0.02 else 0.01
        oben = 1.0 if b["phi"] > 0 else -1.0
        z0, z1 = (-s / 2 - 1.0, s / 2 + innen) if oben > 0 else (-s / 2 - innen, s / 2 + 1.0)
        hoch = gp_Trsf()
        hoch.SetTranslation(gp_Vec(0, 0, z0))
        fehlt = abziehen(_zone_prisma(b, lo, hi, z0, z1), [_bewegt(_prisma(umriss, z1 - z0), hoch)])
        mx, my = o[0] + b["n"][0] * b["ba"] / 2, o[1] + b["n"][1] * b["ba"] / 2
        kette = [(c, c["ba"]) for c, _ in _wirksam(bg, mx, my, ohne=b)]
        teile = [f for f in _feste_koerper(fehlt) if _schwerpunkt(f)[3] > 1e-6]
        if teile:
            try:
                bogen = abziehen(bogen, [_gefaltetes_werkzeug(f, b, z0, z1) for f in teile])
            except Exception as ex:
                meldungen.append(f"Kontur in einer Biegezone nicht erzeugt ({ex})")
        zone = _zone_prisma(b, lo, hi, -s, s)
        gravur = []
        for r in rillen:                    # Gravur in der Biegezone: mitgefaltet (Rille 0,1 mm tief)
            stueck = _gemeinsam(zone, _bewegt(r, halb))
            for f in _feste_koerper(stueck) if stueck is not None else ():
                if _schwerpunkt(f)[3] > 1e-9:
                    gravur += _gefaltete_scheiben(f, b, lo, hi, s)
        if gravur:
            try:
                bogen = abziehen(bogen, gravur)
            except Exception as ex:
                meldungen.append(f"Gravur in einer Biegezone nicht erzeugt ({ex})")
        stuecke.append(_bewegt(bogen, _trsf_kette(kette)) if kette else bogen)
    zurueck = gp_Trsf()
    zurueck.SetTranslation(gp_Vec(0, 0, s / 2))
    if len(stuecke) == 1:
        return _bewegt(stuecke[0], zurueck)
    arg, wz = TopTools_ListOfShape(), TopTools_ListOfShape()
    arg.Append(stuecke[0])
    for x in stuecke[1:]:
        wz.Append(x)
    fuse = BRepAlgoAPI_Fuse()
    fuse.SetArguments(arg)
    fuse.SetTools(wz)
    fuse.SetFuzzyValue(1e-5)
    fuse.Build()
    if not fuse.IsDone():
        raise ValueError("Stücke der Kantung nicht vereinigt")
    return _bewegt(fuse.Shape(), zurueck)


def teil_bauen(teil):
    """Körper eines Teils und Meldungen."""
    meldungen = []
    k = grundkoerper(teil["koerper"])
    wz = []
    for w in teil.get("werkzeuge") or ():
        try:
            wz.append(werkzeug(w))
        except Exception as ex:             # ein Werkzeug fehlt: Teil trotzdem schreiben, mit Meldung
            meldungen.append(f"{w.get('name') or w['art']}: nicht erzeugt ({ex})")
    for gruppe in werkzeug_gruppen(wz):     # überlappende Werkzeuge (Stücke einer Kontur, Enden) nie zusammen
        k = abziehen(k, gruppe)
    rillen = []
    for w in teil.get("rillen") or ():
        try:
            rillen.append(werkzeug(w))
        except Exception:
            pass
    if rillen:
        k = abziehen(k, rillen)
    if teil["koerper"].get("biegungen"):
        k = platte_falten(k, teil["koerper"], meldungen, rillen)
    try:
        k = vereinfachen(k)
    except Exception as ex:
        meldungen.append(f"Flächen nicht zusammengelegt ({ex})")
    if teil.get("lage"):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Trsf
        m = teil["lage"]                    # 3 × 4 Matrix zeilenweise
        tr = gp_Trsf()
        tr.SetValues(*[float(x) for x in m])
        k = BRepBuilderAPI_Transform(k, tr, True).Shape()
    return k, meldungen


# ------------------------------------------------------------------ Baugruppe (3E-14)
ABSTAND_DANEBEN = 50.0  # Teile ohne Lage so weit neben die Baugruppe [mm]
PROBE = 1500            # so viele Punkte je Oberfläche beim Ausrichten


def _trsf(m):
    from OCP.gp import gp_Trsf
    t = gp_Trsf()
    t.SetValues(*[float(x) for x in m])
    return t


def _dreiecke(k):
    """Dreiecke der Oberfläche eines Körpers (BRepMesh) als [(p1, p2, p3)]."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    BRepMesh_IncrementalMesh(k, 0.2, False, 0.3, True)
    out, ex = [], TopExp_Explorer(k, TopAbs_FACE)
    while ex.More():
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(TopoDS.Face(ex.Current()), loc)
        ex.Next()
        if tri is None:
            continue
        tr = loc.Transformation()
        pts = [tri.Node(i).Transformed(tr) for i in range(1, tri.NbNodes() + 1)]
        for i in range(1, tri.NbTriangles() + 1):
            out.append(tuple((q.X(), q.Y(), q.Z()) for q in (pts[j - 1] for j in tri.Triangle(i).Get())))
    return out


def _flaechen_punkte(dreiecke, n=PROBE):
    """Gleichmäßig verteilte Punkte auf einer Oberfläche aus Dreiecken (nach Fläche), höchstens etwa n."""
    flaechen = [0.5 * math.sqrt(sum(c * c for c in _kreuz3(_sub3(b, a), _sub3(c, a)))) for a, b, c in dreiecke]
    gesamt = sum(flaechen) or 1.0
    out = []
    for (a, b, c), f in zip(dreiecke, flaechen):
        k = max(1, round(math.sqrt(f / gesamt * n * 2)))
        for i in range(k):
            for j in range(k - i):
                u, v = (i + 1 / 3) / k, (j + 1 / 3) / k
                out.append(tuple(a[q] + (b[q] - a[q]) * u + (c[q] - a[q]) * v for q in range(3)))
    return out


def _sub3(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _kreuz3(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _traegheit(punkte):
    """Schwerpunkt und Hauptachsen (Spalten, nach Größe der Streuung) einer Punktwolke (Jacobi-Verfahren)."""
    n = len(punkte)
    c = [sum(p[i] for p in punkte) / n for i in range(3)]
    m = [[sum((p[i] - c[i]) * (p[j] - c[j]) for p in punkte) / n for j in range(3)] for i in range(3)]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(50):
        i, j = max(((0, 1), (0, 2), (1, 2)), key=lambda q: abs(m[q[0]][q[1]]))
        if abs(m[i][j]) < 1e-12:
            break
        th = 0.5 * math.atan2(2 * m[i][j], m[j][j] - m[i][i])
        co, si = math.cos(th), math.sin(th)
        for k in range(3):
            a_, b_ = m[k][i], m[k][j]
            m[k][i], m[k][j] = co * a_ - si * b_, si * a_ + co * b_
        for k in range(3):
            a_, b_ = m[i][k], m[j][k]
            m[i][k], m[j][k] = co * a_ - si * b_, si * a_ + co * b_
        for k in range(3):
            a_, b_ = v[k][i], v[k][j]
            v[k][i], v[k][j] = co * a_ - si * b_, si * a_ + co * b_
    ordnung = sorted(range(3), key=lambda k: -m[k][k])
    return c, [[v[r][k] for r in range(3)] for k in ordnung]


class _Raster:
    """Punkte im Würfelraster für die Suche des nächsten Punkts."""

    def __init__(self, punkte, zelle):
        self.z, self.zellen = zelle, {}
        for p in punkte:
            self.zellen.setdefault(tuple(int(math.floor(c / zelle)) for c in p), []).append(p)

    def abstand(self, p, weit=2):
        k = tuple(int(math.floor(c / self.z)) for c in p)
        best = None
        for dx in range(-weit, weit + 1):
            for dy in range(-weit, weit + 1):
                for dz in range(-weit, weit + 1):
                    for q in self.zellen.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                        if best is None or d < best:
                            best = d
        return math.sqrt(best) if best is not None else self.z * (weit + 1)

    def naechster(self, p, weit=2):
        """Nächster Punkt (oder p selbst, wenn im Umkreis keiner liegt)."""
        k = tuple(int(math.floor(c / self.z)) for c in p)
        best, nah = None, p
        for dx in range(-weit, weit + 1):
            for dy in range(-weit, weit + 1):
                for dz in range(-weit, weit + 1):
                    for q in self.zellen.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                        if best is None or d < best:
                            best, nah = d, q
        return nah


def _flaechen_schwerpunkt(dreiecke):
    """Flächenschwerpunkt einer Oberfläche aus Dreiecken (exakt, unabhängig von der Vernetzung)."""
    summe, c = 0.0, [0.0, 0.0, 0.0]
    for a, b, d in dreiecke:
        f = 0.5 * math.sqrt(sum(x * x for x in _kreuz3(_sub3(b, a), _sub3(d, a))))
        summe += f
        for i in range(3):
            c[i] += f * (a[i] + b[i] + d[i]) / 3
    return [x / summe for x in c] if summe > 1e-12 else None


def _einheit3(v):
    n = math.sqrt(sum(x * x for x in v))
    return tuple(x / n for x in v) if n > 1e-12 else None


def _kanten_rahmen(dreiecke):
    """Achsen aus der Geometrie selbst (Bleche, Flachstahl): Normale der größten ebenen Fläche und die häufigste
    Richtung der Kanten quer dazu (Seitenflächen), gewichtet nach Länge. Bei quadratischen oder symmetrischen
    Teilen eindeutig, wo die Hauptachsen der Streuung beliebig in der Ebene liegen. None, wenn es keine gibt."""
    normalen = {}
    for a, b, d in dreiecke:
        n = _kreuz3(_sub3(b, a), _sub3(d, a))
        f = math.sqrt(sum(x * x for x in n))
        if f < 1e-9:
            continue
        n = tuple(x / f for x in n)
        if n[0] < -1e-9 or (abs(n[0]) <= 1e-9 and (n[1] < -1e-9 or (abs(n[1]) <= 1e-9 and n[2] < 0))):
            n = tuple(-x for x in n)
        k = tuple(round(x, 3) for x in n)
        alt = normalen.get(k)
        normalen[k] = (alt[0] + f, alt[1]) if alt else (f, n)
    if not normalen:
        return None
    n1 = max(normalen.values())[1]
    hilf = (1.0, 0.0, 0.0) if abs(n1[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _einheit3(_kreuz3(n1, hilf))
    w = _kreuz3(n1, u)
    winkel = {}
    for a, b, d in dreiecke:
        n = _einheit3(_kreuz3(_sub3(b, a), _sub3(d, a)))
        if n is None or abs(sum(n[i] * n1[i] for i in range(3))) > 0.05:
            continue                                # nur Seitenflächen (senkrecht zur großen Fläche)
        for p, q in ((a, b), (b, d), (d, a)):
            v = _sub3(q, p)
            x, y = sum(v[i] * u[i] for i in range(3)), sum(v[i] * w[i] for i in range(3))
            lang = math.hypot(x, y)
            if lang < 1e-6:
                continue
            g = round(math.degrees(math.atan2(y, x)) % 90.0, 1) % 90.0
            winkel[g] = winkel.get(g, 0.0) + lang
    if not winkel:
        return None
    g = math.radians(max(winkel, key=winkel.get))
    e1 = tuple(math.cos(g) * u[i] + math.sin(g) * w[i] for i in range(3))
    return [list(e1), list(_kreuz3(n1, e1)), list(n1)]


def _drehungen(a_n, a_e):
    """Die 24 Drehungen, die die Achsen a_e (des gebauten Teils) auf die Achsen a_n (des Netzes) legen."""
    for perm in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)):
        for vz in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1), (-1, 1, 1), (1, -1, 1),
                   (1, 1, -1)):
            r = [[sum(vz[i] * a_n[perm[i]][z] * a_e[i][s_] for i in range(3)) for s_ in range(3)] for z in range(3)]
            det = (r[0][0] * (r[1][1] * r[2][2] - r[1][2] * r[2][1]) - r[0][1] * (r[1][0] * r[2][2] - r[1][2] * r[2][0])
                   + r[0][2] * (r[1][0] * r[2][1] - r[1][1] * r[2][0]))
            if det > 0:
                yield r


def _glatt(r):
    """Drehmatrix, die fast achsparallel ist (Rundung der Messung), auf 0 und ±1 setzen."""
    if all(min(abs(x), abs(abs(x) - 1)) < 2e-3 for zeile in r for x in zeile):
        return [[float(round(x)) for x in zeile] for zeile in r]
    return r


def ausrichten(k, p, t, achsen=None):
    """Lage des gebauten Teils k in der Datei aus dem Netz der STEP-Messung (Punkte p flach, Dreiecke t, in der
    Datei). Kandidaten: je 24 Drehungen auf die Achsen der Einbaulage (achsen = [X, Y, Z] der Messung), der Datei,
    der Kanten (größte Fläche + Seitenkanten) und der Hauptachsen der Streuung; Verschiebung aus dem exakten
    Flächenschwerpunkt, danach nachgeführt (nächste Punkte). Gewählt wird die kleinste mittlere Abweichung der
    Oberflächen (beidseitig). Ergebnis (3 × 4 Matrix, mittlere Abweichung [mm])."""
    pts = [tuple(p[i:i + 3]) for i in range(0, len(p), 3)]
    d_netz = [(pts[t[i]], pts[t[i + 1]], pts[t[i + 2]]) for i in range(0, len(t), 3)]
    d_eigen = _dreiecke(k)
    netz, eigen = _flaechen_punkte(d_netz), _flaechen_punkte(d_eigen)
    if len(netz) < 4 or len(eigen) < 4:
        raise ValueError("zu wenig Punkte zum Ausrichten")
    c_n, a_n = _traegheit(netz)
    c_e, a_e = _traegheit(eigen)
    c_n, c_e = _flaechen_schwerpunkt(d_netz) or c_n, _flaechen_schwerpunkt(d_eigen) or c_e
    welt = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    rahmen = [(welt, welt)]
    if achsen and len(achsen) == 3:
        rahmen.append(([list(a) for a in achsen], welt))
    k_n, k_e = _kanten_rahmen(d_netz), _kanten_rahmen(d_eigen)
    if k_n and k_e:
        rahmen.append((k_n, k_e))
    rahmen.append((a_n, a_e))
    groesse = max(max(q[i] for q in netz) - min(q[i] for q in netz) for i in range(3))
    zelle = max(groesse / 30, 0.5)
    r_netz = _Raster(netz, zelle)
    stich_e, stich_n = eigen[::max(1, len(eigen) // 400)], netz[::max(1, len(netz) // 400)]

    def bewegen(r, tr, punkte):
        return [tuple(sum(r[z][s_] * q[s_] for s_ in range(3)) + tr[z] for z in range(3)) for q in punkte]

    def fehler_von(r, tr):
        bewegt = bewegen(r, tr, stich_e)
        hin = sum(r_netz.abstand(q) for q in bewegt) / len(bewegt)
        r_eigen = _Raster(bewegt, zelle)
        return (hin + sum(r_eigen.abstand(q) for q in stich_n) / len(stich_n)) / 2

    kandidaten = []
    for a_ziel, a_quelle in rahmen:
        for r in _drehungen(a_ziel, a_quelle):
            r = _glatt(r)
            tr = [c_n[z] - sum(r[z][s_] * c_e[s_] for s_ in range(3)) for z in range(3)]
            bewegt = bewegen(r, tr, stich_e)
            kandidaten.append((sum(r_netz.abstand(q) for q in bewegt) / len(bewegt), r, tr))
    kandidaten.sort(key=lambda x: x[0])
    best = None
    for _, r, tr in kandidaten[:6]:
        fehler = fehler_von(r, tr)
        for _ in range(4):                  # Verschiebung nachführen: mittlerer Abstand zum nächsten Punkt
            bewegt = bewegen(r, tr, stich_e)
            schub = [0.0, 0.0, 0.0]
            for q in bewegt:
                z = r_netz.naechster(q)
                for i in range(3):
                    schub[i] += (z[i] - q[i]) / len(bewegt)
            if math.sqrt(sum(x * x for x in schub)) < 1e-3:
                break
            tr2 = [tr[i] + schub[i] for i in range(3)]
            f2 = fehler_von(r, tr2)
            if f2 >= fehler:
                break
            tr, fehler = tr2, f2
        if best is None or fehler < best[0] - 1e-6:
            best = (fehler, [r[0][0], r[0][1], r[0][2], tr[0], r[1][0], r[1][1], r[1][2], tr[1],
                             r[2][0], r[2][1], r[2][2], tr[2]])
    return best[1], best[0]


def _box(formen):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    for f in formen:
        BRepBndLib.Add_s(f, box)
    if box.IsVoid():
        return None
    a, b = box.CornerMin(), box.CornerMax()
    return [a.X(), a.Y(), a.Z(), b.X(), b.Y(), b.Z()]


def baugruppe_schreiben(bauplan, ziel):
    """Baugruppe: jedes Teil einmal bauen, als Komponenten in ihrer Lage einsetzen, Unterbaugruppen wie im Bauplan;
    als STEP schreiben -> Ergebnis (dict) mit teile (je Teil), einsaetze, hinweise, box (alles in der Datei)."""
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.gp import gp_Trsf, gp_Vec
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    teile, formen, labels, hinweise = [], [], [], []
    for teil in bauplan.get("teile") or ():
        try:
            k, meldungen = teil_bauen(teil)
        except Exception as ex:
            k, meldungen = None, [f"nicht gebaut ({ex})"]
            hinweise.append(f"{teil.get('name') or 'Teil'}: nicht gebaut ({ex})")
        formen.append(k)
        if k is None:
            labels.append(None)
            teile.append(dict(name=teil.get("name"), meldungen=meldungen, gueltig=False))
            continue
        lab = st.AddShape(k, False)
        TDataStd_Name.Set_s(lab, TCollection_ExtendedString(str(teil.get("name") or "Teil"), True))
        labels.append(lab)
        teile.append(dict(name=teil.get("name"), meldungen=meldungen, **_kennwerte(k)))
    gesetzt, daneben = [], []          # (Knoten-Label, Teil-Nr., Trsf) bzw. ohne Lage

    def name(lab, text):
        TDataStd_Name.Set_s(lab, TCollection_ExtendedString(str(text or "Baugruppe"), True))

    def knoten(spec, eltern):
        lab = st.NewShape()
        name(lab, spec.get("name"))
        for e in spec.get("einsatz") or ():
            nr = int(e["teil"])
            if formen[nr] is None:
                continue
            if e.get("lage"):
                gesetzt.append((lab, nr, _trsf(e["lage"])))
            elif e.get("ausrichten"):
                try:
                    m, fehler = ausrichten(formen[nr], e["ausrichten"]["p"], e["ausrichten"]["t"],
                                           e["ausrichten"].get("achsen"))
                except Exception as ex:
                    hinweise.append(f"{teile[nr]['name']}: Lage nicht bestimmt ({ex}), neben die Baugruppe gelegt")
                    daneben.append((lab, nr))
                    continue
                grenze = max(1.0, 0.02 * max(teile[nr]["box"][i + 3] - teile[nr]["box"][i] for i in range(3)))
                if fehler > grenze:
                    hinweise.append(f"{teile[nr]['name']}: Lage aus der STEP-Messung geschätzt (Abweichung "
                                    f"{fehler:.1f} mm), bitte prüfen")
                gesetzt.append((lab, nr, _trsf(m)))
            else:
                daneben.append((lab, nr))
        for kind in spec.get("kinder") or ():
            knoten(kind, lab)
        if eltern is not None:
            st.AddComponent(eltern, lab, TopLoc_Location())
        return lab

    knoten(bauplan["baugruppe"], None)
    platziert = []
    for lab, nr, tr in gesetzt:
        st.AddComponent(lab, labels[nr], TopLoc_Location(tr))
        platziert.append(formen[nr].Moved(TopLoc_Location(tr)))
    box = _box(platziert) or [0.0] * 6
    x = box[3] + ABSTAND_DANEBEN if platziert else 0.0
    for lab, nr in daneben:
        b = teile[nr]["box"]
        tr = gp_Trsf()
        tr.SetTranslation(gp_Vec(x - b[0], box[1] - b[1], box[2] - b[2]))
        st.AddComponent(lab, labels[nr], TopLoc_Location(tr))
        platziert.append(formen[nr].Moved(TopLoc_Location(tr)))
        x += b[3] - b[0] + ABSTAND_DANEBEN
    if daneben:
        hinweise.append(f"{len(daneben)} Teil(e) ohne Lage aus der STEP-Datei neben die Baugruppe gelegt")
    if not platziert:
        raise ValueError("keine Teile in der Baugruppe")
    st.UpdateAssemblies()
    _step_schreiben(doc, ziel, bauplan["baugruppe"].get("name"))
    return dict(ok=all(t.get("gueltig") for t in teile), teile=teile, einsaetze=len(platziert), hinweise=hinweise,
                box=[round(c, 3) for c in _box(platziert)], volumen=round(sum(_volumen(f) for f in platziert), 3))


def _step_schreiben(doc, ziel, produkt):
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetCVal_s("write.step.product.name", str(produkt or "Teil"))
    w = STEPCAFControl_Writer()
    w.SetNameMode(True)
    if not w.Transfer(doc, STEPControl_AsIs):
        raise ValueError("Übertragung nach STEP fehlgeschlagen")
    if w.Write(str(ziel)) != IFSelect_RetDone:
        raise ValueError(f"STEP-Datei nicht geschrieben: {ziel}")


def form_schreiben(form, ziel, name):
    """Einen fertigen Körper (OpenCascade-Form, mm) unverändert als STEP schreiben (virtuelles Bauteil der Messung,
    step_geometrie.virtuell_ablegen)."""
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    lab = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).AddShape(form, False)
    TDataStd_Name.Set_s(lab, TCollection_ExtendedString(str(name or "Teil"), True))
    _step_schreiben(doc, ziel, name)


def schreiben(bauplan, ziel):
    """Alle Teile bauen und als STEP schreiben -> Ergebnis (dict)."""
    if bauplan.get("baugruppe"):
        return baugruppe_schreiben(bauplan, ziel)
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    werkzeug_formen = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    teile = []
    for teil in bauplan.get("teile") or ():
        k, meldungen = teil_bauen(teil)
        lab = werkzeug_formen.AddShape(k, False)
        TDataStd_Name.Set_s(lab, TCollection_ExtendedString(str(teil.get("name") or "Teil"), True))
        teile.append(dict(name=teil.get("name"), meldungen=meldungen, **_kennwerte(k)))
    if not teile:
        raise ValueError("keine Teile im Bauplan")
    _step_schreiben(doc, ziel, bauplan.get("name") or teile[0]["name"])
    return dict(ok=all(t["gueltig"] for t in teile), teile=teile)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--export":          # STEP-Import.exe --export BAUPLAN --step ZIEL [--ergebnis E]
        werte = dict(zip(argv[::2], argv[1::2]))
        plan, ziel, erg_pfad = werte.get("--export"), werte.get("--step"), werte.get("--ergebnis")
    else:
        plan, ziel, erg_pfad = (argv + [None, None, None])[:3]
    if not plan or not ziel:
        print(__doc__)
        return 2
    try:
        bauplan = json.loads(Path(plan).read_text(encoding="utf-8"))
        erg = schreiben(bauplan, ziel)
        code = 0
    except Exception as ex:
        erg, code = dict(ok=False, fehler=str(ex), teile=[]), 1
    text = json.dumps(erg, ensure_ascii=False)
    if erg_pfad:
        Path(erg_pfad).write_text(text, encoding="utf-8")
    print(text, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
