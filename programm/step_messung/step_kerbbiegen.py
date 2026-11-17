"""Eingeschnittenes und gebogenes Quadrat-/Rechteckrohr abwickeln (Patrick 17.11.2026, tube-laser-cut-1:
Bend_Profile_Long, „Ja, Abwicklung bauen“; Plan B1: Biegungen in verschiedenen Ebenen).

Das Rohr wird gerade gelasert: an jeder Biegestelle sind die Seitenwände und die Innenwand ausgeschnitten, nur die
Außenwand (mit einem schmalen Rand der Seitenwände) bleibt stehen. Danach wird es gebogen: die Außenwand legt sich um
einen Radius, die Schnittkanten der Seitenwände stoßen aneinander. Die STEP zeigt das fertig gebogene Teil, gelasert
wird das gerade Rohr – die Messung braucht also die Abwicklung.

Erkennung: gleichachsige Zylinderflächen mit großem Radius (mindestens RADIUS_MIN) gehören zu einer Biegung; je Achse
gibt der größte Radius die Außenseite R, der nächste die Innenseite der Außenwand (R − s), der kleinste den Rand der
Seitenwände (Tiefe des Biegestreifens). Der Winkelbereich der Außenfläche gibt Anfang, Ende und Winkel der Biegung.
Jede Biegung hat ihre eigene Achse; die Biegungen werden über die geraden Stücke dazwischen verkettet (Tangenten
am Ende der einen und am Anfang der nächsten Biegung gegenläufig parallel) – so gehen auch Biegungen in verschiedenen
Ebenen (Kerben auf verschiedenen Seiten).

Abwicklung: Der Biegestreifen (alles im Winkelbereich mit Radius über dem Rand) wird durch ein gerades Stück mit
demselben Querschnitt ersetzt, Länge = neutrale Faser der Außenwand × Winkel (R − s/2). Die übrigen Körper (gerade
Rohrstücke mit ihren Schnittkanten) werden je nach Lage dem Stück zwischen zwei Biegungen zugeordnet, starr um die
Biegeachse zurückgedreht und um die gestreckte Länge verschoben. Die Schnittkanten bleiben genau wie in der STEP, nur
ihre Lage folgt dem Stück. Das gerade Rohr wird dann wie jedes Rohr gemessen (Profil, Länge, Konturen).
"""
import math

import step_geometrie as g
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.GProp import GProp_GProps
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax1, gp_Ax2, gp_Ax3, gp_Dir, gp_Lin, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec

HINWEIS = "Gebogenes Rohr abgewickelt"
RADIUS_MIN = 20.0       # mm: kleinere Zylinder sind Ecken, Bohrungen, Schnittrundungen
ACHSE_TOL = 0.05        # mm: gleiche Biegeachse
WINKEL_MIN = 3.0        # Grad: kleinere Biegungen gibt es nicht
GROSS = 1e4             # mm: Ausdehnung der Hilfskörper (höchstens; sonst doppelte Diagonale des Körpers)
VOR = 0.05              # mm: Querschnitt des Streifens so weit vor dem Bogenanfang (im geraden Stück)
EPS = 0.01              # mm: Rand des Biegestreifens etwas tiefer, damit nichts übrig bleibt
PARALLEL = 1e-4         # Tangenten zweier Biegungen am geraden Stück: gegenläufig parallel


# ------------------------------------------------------------------ Vektoren (Tupel)
def _v(p):
    return (p.X(), p.Y(), p.Z())


def _add(a, b, k=1.0):
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _pnt(a):
    return gp_Pnt(*a)


# ------------------------------------------------------------------ Biegungen
def _zylindergruppen(solid):
    """Gleichachsige Zylinder ab RADIUS_MIN mit weniger als einem halben Umlauf: [(gp_Ax1, [(Radius, Fläche)])]."""
    gruppen = []
    for f in g._liste(solid, TopAbs_FACE):
        f = TopoDS.Face(f)
        s = BRepAdaptor_Surface(f)
        if s.GetType() != GeomAbs_Cylinder:
            continue
        zy = s.Cylinder()
        if zy.Radius() < RADIUS_MIN or s.LastUParameter() - s.FirstUParameter() > math.pi:
            continue
        ax = zy.Axis()
        for gr in gruppen:
            if gr[0].IsParallel(ax, 1e-6) and gp_Lin(gr[0]).Distance(ax.Location()) < ACHSE_TOL:
                gr[1].append((zy.Radius(), f))
                break
        else:
            gruppen.append((ax, [(zy.Radius(), f)]))
    return gruppen


def vorpruefung(solid):
    """Schnell: hat der Körper eine Biegeachse (gleichachsige Zylinder mit mindestens drei Radien)?"""
    return any(len({round(r, 3) for r, _ in fl}) >= 3 for _, fl in _zylindergruppen(solid))


def biegungen(solid):
    """Biegungen: [dict(o, a, e1, e2, R, s, rand, phi0, phi1, theta)] – o Punkt auf der Achse (mitten in der Breite der
    Außenwand), a Achsrichtung, e1/e2 Basis senkrecht dazu, Winkel phi um a ab e1."""
    out = []
    for ax, fl in _zylindergruppen(solid):
        radien = sorted({round(r, 3) for r, _ in fl}, reverse=True)
        if len(radien) < 3:
            continue
        R = radien[0]
        wand = R - radien[1]
        rand = R - radien[-1]
        if wand <= 0.3 or rand < wand + 0.5:       # Rand der Seitenwände tiefer als die Wand (sonst Rundrohr)
            continue
        a = _v(ax.Direction())
        ax3 = gp_Ax3(ax.Location(), ax.Direction())
        e1, e2 = _v(ax3.XDirection()), _v(ax3.YDirection())
        o0 = _v(ax.Location())
        phis, hoehen = [], []
        for r, f in fl:
            if abs(r - R) > 1e-3:
                continue
            for vx in g._liste(f, TopAbs_VERTEX):
                q = _sub(_v(BRep_Tool.Pnt_s(TopoDS.Vertex(vx))), o0)
                phis.append(math.atan2(_dot(q, e2), _dot(q, e1)))
                hoehen.append(_dot(q, a))
        if len(phis) < 2:
            continue
        # zusammenhängender Bereich (über ±180° hinweg): die größte Lücke zwischen den sortierten Winkeln liegt außerhalb
        ph = sorted(phis)
        luecken = [(ph[(i + 1) % len(ph)] - ph[i]) % (2 * math.pi) for i in range(len(ph))]
        i = max(range(len(ph)), key=lambda j: luecken[j])
        phi0 = ph[(i + 1) % len(ph)]
        theta = 2 * math.pi - luecken[i]
        if math.degrees(theta) < WINKEL_MIN or theta > math.pi:
            continue
        o = _add(o0, a, (min(hoehen) + max(hoehen)) / 2)
        # voller Querschnitt gebogen (Plan B3, ohne Kerbe): die beiden innersten Radien sind die Innenwand (Abstand
        # = Wand); gestreckt wird dann auf der Mittellinie (R − Tiefe/2) wie beim Biegerohr
        voll = len(radien) >= 4 and abs((radien[-2] - radien[-1]) - wand) < 0.05
        faser = R - rand / 2 if voll else R - wand / 2
        out.append(dict(o=o, a=a, e1=e1, e2=e2, R=R, s=wand, rand=rand, phi0=phi0, phi1=phi0 + theta, theta=theta,
                        voll=voll, faser=faser))
    return out


def _radial(b, phi):
    return _add(_add((0, 0, 0), b["e1"], math.cos(phi)), b["e2"], math.sin(phi))


def _tang(b, phi):
    """Richtung steigendes phi."""
    return _add(_add((0, 0, 0), b["e1"], -math.sin(phi)), b["e2"], math.cos(phi))


def _tangente(b, ende):
    """Punkt auf der Außenseite am Anfang (0) bzw. Ende (1) der Biegung und Richtung der Tangente weg vom Bogen."""
    phi = b["phi0"] if ende == 0 else b["phi1"]
    p = _add(b["o"], _radial(b, phi), b["R"])
    t = _tang(b, phi)
    return p, (tuple(-x for x in t) if ende == 0 else t)


def _kette(bg):
    """Biegungen in Reihenfolge entlang des Rohrs: [(Biegung, umgedreht)], umgedreht = von phi1 nach phi0 durchlaufen.
    Zwei Biegungen sind über ein gerades Stück verbunden, wenn ihre Tangenten dort gegenläufig parallel sind und die
    andere Biegung vorn liegt (die nächste davon). None, wenn sich keine eindeutige Kette ergibt."""
    if len(bg) == 1:
        return [(bg[0], False)]
    nb = {}
    for i, a in enumerate(bg):
        for ea in (0, 1):
            pa, ta = _tangente(a, ea)
            best = None
            for j, b in enumerate(bg):
                if i == j:
                    continue
                for eb in (0, 1):
                    pb, tb = _tangente(b, eb)
                    if _dot(ta, tb) > -1 + PARALLEL:
                        continue
                    d = _dot(_sub(pb, pa), ta)
                    if d < -1e-6:
                        continue
                    if best is None or d < best[0]:
                        best = (d, j, eb)
            if best is not None:
                nb[(i, ea)] = best[1:]
    # nur gegenseitige Nachbarn zählen
    nb = {k: v for k, v in nb.items() if nb.get(v) == k}
    start = [i for i in range(len(bg)) if sum((i, e) in nb for e in (0, 1)) == 1]
    if len(start) != 2:
        return None
    i = start[0]
    e_frei = 0 if (i, 0) not in nb else 1
    out, gesehen = [], set()
    while True:
        gesehen.add(i)
        aus = 1 - e_frei
        out.append((bg[i], e_frei == 1))     # von e_frei nach aus
        if (i, aus) not in nb:
            break
        i, e_frei = nb[(i, aus)]
        if i in gesehen:
            return None
    return out if len(out) == len(bg) else None


# ------------------------------------------------------------------ Körper
def _bool(art, a, b):
    op = {"common": BRepAlgoAPI_Common, "cut": BRepAlgoAPI_Cut, "fuse": BRepAlgoAPI_Fuse}[art](a, b)
    op.SetFuzzyValue(g.FUZZY)
    op.Build()
    return op.Shape() if op.IsDone() else None


def _anwenden(shape, tr):
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def _schwerpunkt(k):
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(k, p)
    return _v(p.CentreOfMass())


def _verbund(ks):
    if len(ks) == 1:
        return ks[0]
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    c = TopoDS_Compound()
    bb = BRep_Builder()
    bb.MakeCompound(c)
    for k in ks:
        bb.Add(c, k)
    return c


def _prisma_polygon(pts, z0, z1):
    """Prisma über einem Polygon (x, y) in der XY-Ebene von z0 bis z1 (lokal)."""
    poly = BRepBuilderAPI_MakePolygon()
    for x, y in pts:
        poly.Add(gp_Pnt(x, y, z0))
    poly.Close()
    f = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
    return BRepPrimAPI_MakePrism(f, gp_Vec(0, 0, z1 - z0)).Shape()


def _keil(b, phi_a, phi_b, gross=GROSS):
    """Keil um die Biegeachse zwischen phi_a und phi_b, außerhalb des Randes (Radius ab R − rand − EPS)."""
    n = max(2, int(abs(phi_b - phi_a) / math.radians(5)) + 1)
    pts = [(0.0, 0.0)] + [(gross * math.cos(phi_a + (phi_b - phi_a) * k / n),
                           gross * math.sin(phi_a + (phi_b - phi_a) * k / n)) for k in range(n + 1)]
    keil = _prisma_polygon(pts, -gross, gross)
    tr = gp_Trsf()
    tr.SetTransformation(gp_Ax3(_pnt(b["o"]), gp_Dir(*b["a"]), gp_Dir(*b["e1"])), gp_Ax3())
    keil = _anwenden(keil, tr)
    unten = _add(b["o"], b["a"], -gross)
    innen = BRepPrimAPI_MakeCylinder(gp_Ax2(_pnt(unten), gp_Dir(*b["a"])), b["R"] - b["rand"] - EPS,
                                     2 * gross).Shape()
    return _bool("cut", keil, innen)


def _stueck_nr(kette, q):
    """Nummer des Stücks (0 = vor der ersten Biegung), in dem der Punkt q liegt: vor Biegung j heißt auf der Seite
    der Winkelhalbierenden, auf der der Anfang der Biegung liegt."""
    for j, (b, um) in enumerate(kette):
        n = _tang(b, (b["phi0"] + b["phi1"]) / 2)
        p_in, _ = _tangente(b, 1 if um else 0)
        if _dot(_sub(p_in, b["o"]), n) * _dot(_sub(q, b["o"]), n) > 0:
            return j
    return len(kette)


def _drehung(b, winkel):
    tr = gp_Trsf()
    tr.SetRotation(gp_Ax1(_pnt(b["o"]), gp_Dir(*b["a"])), winkel)
    return tr


def _schieben(v):
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(*v))
    return tr


def _gerade(stueck, b, ende, laenge, richtung):
    """Gerades Stück für den Biegestreifen: Querschnitt des geraden Stücks vor der Biegung kurz vor dem Bogenanfang
    (dort sind alle Kanten Geraden und Kreise; ein Schnitt durch den Bogen selbst gäbe Freiformkurven, mit denen das
    Zusammensetzen sehr langsam wird), nur der Teil über dem Rand des Streifens, auf den Bogenanfang geschoben und
    laenge lang in richtung."""
    p, _ = _tangente(b, ende)
    vor = _add(p, richtung, -VOR)
    sec = BRepAlgoAPI_Section(stueck, gp_Pln(_pnt(vor), gp_Dir(*richtung)), False)
    sec.Build()
    kanten = g.TopTools_HSequenceOfShape()
    for e in g._liste(sec.Shape(), TopAbs_EDGE):
        kanten.Append(e)
    if kanten.Length() == 0:
        return None
    wires = ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(kanten, 1e-4, False)
    ws = [TopoDS.Wire(wires.Value(i)) for i in range(1, wires.Length() + 1)]
    ws = [(abs(g._flaeche(BRepBuilderAPI_MakeFace(w, True).Face())), w) for w in ws]
    ws.sort(key=lambda x: -x[0])
    if not ws:
        return None
    flaeche = BRepBuilderAPI_MakeFace(ws[0][1], True).Face()
    for _, w in ws[1:]:         # Innenkontur (Rohr) abziehen
        flaeche = _bool("cut", flaeche, BRepBuilderAPI_MakeFace(w, True).Face())
        if flaeche is None:
            return None
    unten = _add(b["o"], b["a"], -GROSS)
    innen = BRepPrimAPI_MakeCylinder(gp_Ax2(_pnt(unten), gp_Dir(*b["a"])), b["R"] - b["rand"] - EPS,
                                     2 * GROSS).Shape()
    flaeche = _bool("cut", flaeche, innen)
    if flaeche is None:
        return None
    flaeche = _anwenden(flaeche, _schieben(tuple(x * VOR for x in richtung)))
    form = None
    for f in g._liste(flaeche, TopAbs_FACE):
        pr = BRepPrimAPI_MakePrism(f, gp_Vec(*(x * laenge for x in richtung))).Shape()
        form = pr if form is None else _bool("fuse", form, pr)
    return form


def abwickeln(solid):
    """Gerades Rohr aus dem gebogenen Körper (Lage: Stück vor der ersten Biegung bleibt wie in der Datei) und die
    Biegungen [dict(winkel, radius, laenge, rand)], oder None."""
    bg = biegungen(solid)
    if not bg:
        return None
    kette = _kette(bg)
    if kette is None:
        return None
    # Biegestreifen abtrennen (Hilfskörper nur so groß wie nötig: große Keile machen die Booleschen Operationen langsam)
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    bb = Bnd_Box()
    BRepBndLib.Add_s(solid, bb, False)
    diag = math.sqrt(bb.SquareExtent())
    rest = solid
    for b, _ in kette:
        gross = min(GROSS, 2 * diag + 2 * b["R"])
        k = _keil(b, b["phi0"], b["phi1"], gross)
        if k is None:
            return None
        rest = _bool("cut", rest, k)        # der Streifen selbst wird durch ein gerades Stück ersetzt (_gerade)
        if rest is None:
            return None
    # Stücke: die übrigen Körper (an jeder Biegung sind die Wände bis auf den Streifen durchtrennt, die Schnittkanten
    # stoßen nur aneinander), je Körper nach seinem Schwerpunkt dem Stück zwischen zwei Biegungen zugeordnet – so
    # bleiben verzahnte Schnittkanten (Puzzle) ganz bei ihrem Stück
    stuecke = [[] for _ in range(len(kette) + 1)]
    for k in g._liste(rest, TopAbs_SOLID):
        stuecke[_stueck_nr(kette, _schwerpunkt(k))].append(k)
    if any(not x for x in stuecke):
        return None
    stuecke = [_verbund(x) for x in stuecke]
    # Lage im geraden Rohr: Stück 0 bleibt, jedes weitere wird um seine Biegung zurückgedreht und um die gestreckte
    # Länge verschoben; Trafo kumulativ (alles in Dateikoordinaten der jeweiligen Biegung)
    gesamt = gp_Trsf()
    teile = [stuecke[0]]
    info = []
    for j, (b, um) in enumerate(kette):
        e_in = 1 if um else 0
        _, t_in = _tangente(b, e_in)
        laenge = b["faser"] * b["theta"]
        richtung = tuple(-x for x in t_in)       # Laufrichtung des Rohrs am Anfang der Biegung
        ersatz = _gerade(stuecke[j], b, e_in, laenge, richtung)
        if ersatz is None:
            return None
        teile.append(_anwenden(ersatz, gesamt))
        dreh = b["theta"] if um else -b["theta"]
        schritt = _schieben(tuple(x * laenge for x in richtung)).Multiplied(_drehung(b, dreh))
        gesamt = gesamt.Multiplied(schritt)
        teile.append(_anwenden(stuecke[j + 1], gesamt))
        info.append(dict(winkel=round(math.degrees(b["theta"]), 2), radius=round(b["R"], 2),
                         laenge=round(laenge, 2), rand=round(b["rand"], 2), voll=b["voll"]))
    form = teile[0]
    for x in teile[1:]:
        form = _bool("fuse", form, x)
        if form is None:
            return None
    k = g._liste(form, TopAbs_SOLID)
    if len(k) != 1:
        return None
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    u = ShapeUpgrade_UnifySameDomain(k[0], True, True, True)
    u.Build()
    return u.Shape(), info


def messen(solid, datei="", koerper=1, netz=False):
    """Eingeschnittenes, gebogenes Quadrat-/Rechteckrohr: gemessenes gerades Rohr (Teil) oder None."""
    if not vorpruefung(solid):
        return None
    erg = abwickeln(solid)
    if erg is None:
        return None
    gerade, info = erg
    t = g._profil_messen(gerade, datei, koerper, netz)
    if t.profilform not in ("Quadratrohr", "Rechteckrohr") or t.laenge <= 0:
        return None
    t.bauteiltyp = "Profil"
    t.sicherheit["laenge"] = "wahrscheinlich"
    faser = ("Mittellinie" if all(x["voll"] for x in info) else "neutraler Faser der Außenwand"
             if not any(x["voll"] for x in info) else "Mittellinie bzw. neutraler Faser der Außenwand")
    t.hinweise.insert(0, f"{HINWEIS}: {len(info)} Biegung{'en' if len(info) > 1 else ''} (" +
                      ", ".join(f"{x['winkel']:g}° R{x['radius']:g}" + (" voller Querschnitt" if x["voll"] else "")
                                for x in info) +
                      f"), gestreckte Länge {t.laenge:.1f} mm auf {faser} – gelasert wird das gerade Rohr, Biegen als "
                      "Zusatzarbeit prüfen")
    return t
