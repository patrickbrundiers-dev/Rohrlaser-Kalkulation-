"""Abwicklung gekanteter Bleche (Kantteile) aus dem STEP-Körper (Patrick 23.10.2026: Kantteile kamen im Blech-Editor
ohne Schenkel, Bohrungen und Schneidweg an).

Vorgehen:
1. Haut: Ebene Flächen, hinter denen im Abstand der Blechdicke wieder Material-Oberfläche liegt, und die Zylinder der
   Biegezonen (koaxiale Paare r / r + s) bilden die beiden Häute des Blechs; Stirn- und Lochflächen gehören nicht dazu.
   Ein Kantteil hat genau zwei zusammenhängende Häute (ein T-Stoß oder ein Vollkörper nicht).
2. Schenkel = zusammenhängende ebene Flächen einer Haut in derselben Ebene; Biegungen = Zylinder der Haut (mit
   Innenradius) oder scharfe Kanten zwischen zwei Schenkeln (scharfkantig gezeichnet, Innenradius = Blechdicke
   angenommen).
3. Ausgehend vom größten Schenkel (bei einer Kette: vom ersten) wird jeder Schenkel um seine Biegung in die Ebene des
   Vorgängers gedreht und um die Biegezugabe der neutralen Faser verschoben: BA = φ·(r + k·s), bei scharfen Kanten
   BA − 2·r·tan(φ/2) gegenüber der Innenkante. Zwischen den Schenkeln liegt ein Streifen der Breite BA.
4. Alle Flächen zusammen ergeben den Zuschnitt (Außenkontur, Innenkonturen = Bohrungen und Ausschnitte der Schenkel).

Mit parallelen Biegekanten und einer Kette von Schenkeln (Winkel, U, Z, Hut, C) stehen dazu die Schenkel mit
Außenmaß, Biegewinkel (+ zur Außenseite der Haut, also nach oben in der Abwicklung) und Innenradius da, wie im
Blech-Editor (rohrlaser.blech). Sonst (Schale, Kasten) nur Zuschnitt, Biegelinien und Zahl der Kantungen.

Zuschnitt-System: x längs der Biegekanten (Kantlänge), y quer dazu ab dem Anfang von Schenkel 1 (Kette); mehrachsig
das kleinste umschreibende Rechteck (x längs) wie bei ebenen Blechen."""
import math

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.GProp import GProp_GProps
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_ON, TopAbs_OUT, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
try:  # OCP >= 7.8
    from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
except ImportError:
    from OCP.TopTools import TopTools_ListOfShape
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

import step_geometrie as g

K_FAKTOR = 0.33          # wie rohrlaser.blech.K_FAKTOR
TOL = 0.02               # mm: Lage von Ebenen und Radien
PARALLEL = 1e-4          # 1 − |cos| für parallele Richtungen


def _punkte_in(face, n=5):
    """Punkte mitten in der Fläche (Schwerpunkte der n größten Dreiecke des Netzes), größtes zuerst."""
    ort = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(TopoDS.Face(face), ort)
    if tri is None:
        return []
    tr = ort.Transformation()
    out = []
    for j in range(1, tri.NbTriangles() + 1):
        p = [tri.Node(i).Transformed(tr) for i in tri.Triangle(j).Get()]
        a = gp_Vec(p[0], p[1]).Crossed(gp_Vec(p[0], p[2])).Magnitude()
        out.append((a, gp_Pnt(sum(q.X() for q in p) / 3, sum(q.Y() for q in p) / 3, sum(q.Z() for q in p) / 3)))
    out.sort(key=lambda x: -x[0])
    return [p for _, p in out[:n]]


def _vereinheitlichen(solid):
    """Angrenzende Flächen derselben Ebene bzw. desselben Zylinders zusammenfassen (aus Booleschen Operationen
    zerstückelte Flächen), damit jede Haut-Fläche ganz geprüft wird."""
    try:
        u = ShapeUpgrade_UnifySameDomain(solid, True, True, False)
        u.Build()
        sol = g._liste(u.Shape(), g.TopAbs_SOLID)
        return sol[0] if len(sol) == 1 else solid
    except Exception:  # noqa: BLE001 – dann eben mit den Flächen, wie sie sind
        return solid


def _normale(face, p):
    n = g._normale(face, p)
    return gp_Vec(*n) if n else None


class _Flaeche:
    def __init__(self, i, face):
        self.i, self.face = i, face
        self.flaeche = g._flaeche(face)
        self.art = None              # 'E' Ebene, 'Z' Zylinder der Haut
        self.p = self.n = None       # Punkt in der Fläche, Normale nach außen
        self.achse = self.radius = None


def _zylinderdaten(face):
    sf = BRepAdaptor_Surface(TopoDS.Face(face))
    if sf.GetType() != GeomAbs_Cylinder:
        return None
    c = sf.Cylinder()
    return c.Axis(), c.Radius()


def _koaxial(a1, a2):
    return abs(abs(a1.Direction().Dot(a2.Direction())) - 1) < PARALLEL and \
        gp_Vec(a1.Location(), a2.Location()).Crossed(g._vec(a1.Direction())).Magnitude() < TOL


def _loesen(n1, h1, n2, h2, d, hd):
    """Punkt x mit n1·x = h1, n2·x = h2, d·x = hd (Cramer)."""
    m = [[n1.X(), n1.Y(), n1.Z()], [n2.X(), n2.Y(), n2.Z()], [d.X(), d.Y(), d.Z()]]
    r = [h1, h2, hd]

    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    dt = det(m)
    if abs(dt) < 1e-12:
        return None
    out = []
    for k in range(3):
        mk = [row[:] for row in m]
        for i in range(3):
            mk[i][k] = r[i]
        out.append(det(mk) / dt)
    return gp_Pnt(*out)


def _pv(p):
    return gp_Vec(p.X(), p.Y(), p.Z())


def abwickeln(solid, dicke, k=K_FAKTOR):
    """Abwicklung eines Kantteils. Ergebnis dict (siehe abwicklung_daten) oder dict(fehler=Grund)."""
    s = dicke
    solid = _vereinheitlichen(solid)
    BRepMesh_IncrementalMesh(solid, max(s, 0.5), False, 0.5, True)
    try:
        return _abwickeln(solid, s, k)
    finally:
        BRepTools.Clean_s(solid)


def _abwickeln(solid, s, k):
    faces = g.TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(solid, TopAbs_FACE, faces)
    fl = [_Flaeche(i, faces.FindKey(i)) for i in range(1, faces.Extent() + 1)]
    klass = BRepClass3d_SolidClassifier(solid)
    # 1. Häute: Ebenen mit Gegenfläche im Abstand s, Zylinder mit koaxialem Partner (Radius ± s)
    zyl = [(f, z) for f in fl for z in (_zylinderdaten(f.face),) if z]
    for f in fl:
        if g._ebene(f.face) is not None:
            for p in _punkte_in(f.face):        # einige Punkte: Teile der Fläche liegen evtl. vor einer Ecke
                n = _normale(f.face, p)
                if n is None:
                    break
                q = gp_Pnt(_pv(p).Subtracted(n.Multiplied(s)).XYZ())
                klass.Perform(q, 1e-3)
                if klass.State() == TopAbs_ON:
                    f.art, f.p, f.n = "E", p, n
                    break
    for f, (ax, r) in zyl:
        for f2, (ax2, r2) in zyl:
            if f2 is not f and abs(abs(r - r2) - s) < TOL and _koaxial(ax, ax2):
                f.art, f.achse, f.radius = "Z", ax, r
                f.r_innen = min(r, r2)
                break
    haut = {f.i: f for f in fl if f.art}
    if not haut:
        return dict(fehler="keine Blechhaut gefunden")
    kf = g.TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(solid, TopAbs_EDGE, TopAbs_FACE, kf)
    nachbarn = {i: {} for i in haut}          # Fläche -> {Nachbarfläche: [Kanten]}
    for j in range(1, kf.Extent() + 1):
        ids = sorted({faces.FindIndex(x) for x in kf.FindFromIndex(j)})
        if len(ids) == 2 and ids[0] in haut and ids[1] in haut:
            e = kf.FindKey(j)
            nachbarn[ids[0]].setdefault(ids[1], []).append(e)
            nachbarn[ids[1]].setdefault(ids[0], []).append(e)
    komp, gesehen = [], set()
    for i in haut:
        if i in gesehen:
            continue
        stapel, c = [i], []
        gesehen.add(i)
        while stapel:
            x = stapel.pop()
            c.append(x)
            for y in nachbarn[x]:
                if y not in gesehen:
                    gesehen.add(y)
                    stapel.append(y)
        komp.append(c)
    komp.sort(key=lambda c: -sum(haut[i].flaeche for i in c))
    if len(komp) != 2:
        return dict(fehler=f"{len(komp)} statt 2 Blechhäute (kein Kantteil)")
    S = set(komp[0])
    # 2. Schenkel: zusammenhängende ebene Flächen der Haut in einer Ebene
    eben = [i for i in S if haut[i].art == "E"]
    schenkel_von, schenkel = {}, []
    for i in eben:
        if i in schenkel_von:
            continue
        stapel, c = [i], []
        schenkel_von[i] = len(schenkel)
        while stapel:
            x = stapel.pop()
            c.append(x)
            for y in nachbarn[x]:
                if y in schenkel_von or haut[y].art != "E":
                    continue
                if abs(haut[y].n.Dot(haut[x].n) - 1) < PARALLEL and \
                        abs(gp_Vec(haut[x].p, haut[y].p).Dot(haut[x].n)) < TOL:
                    schenkel_von[y] = len(schenkel)
                    stapel.append(y)
        schenkel.append(c)
    if len(schenkel) < 2:
        return dict(fehler="weniger als zwei Schenkel")
    # Biegungen: koaxiale Zylinder der Haut (zusammenhängend) oder scharfe Kanten zwischen zwei Schenkeln
    biegungen = []
    zyl_s = [i for i in S if haut[i].art == "Z"]
    frei = set(zyl_s)
    while frei:
        i = frei.pop()
        gruppe, stapel = [i], [i]
        while stapel:
            x = stapel.pop()
            for y in list(nachbarn[x]):
                if y in frei and abs(haut[y].radius - haut[i].radius) < TOL and _koaxial(haut[y].achse, haut[i].achse):
                    frei.discard(y)
                    gruppe.append(y)
                    stapel.append(y)
        an = sorted({schenkel_von[y] for x in gruppe for y in nachbarn[x] if y in schenkel_von})
        if len(an) != 2:
            return dict(fehler=f"Biegezone mit {len(an)} Schenkeln")
        biegungen.append(dict(art="Z", flaechen=gruppe, schenkel=an, achse=haut[i].achse,
                              r=haut[i].r_innen, r_haut=haut[i].radius))
    paare = {}
    for i in eben:
        for j, kanten in nachbarn[i].items():
            if j in schenkel_von and schenkel_von[j] != schenkel_von[i] and i < j:
                paare.setdefault(tuple(sorted((schenkel_von[i], schenkel_von[j]))), []).append((i, j, kanten))
    for (a, b), liste in paare.items():
        if any(set(x["schenkel"]) == {a, b} for x in biegungen):
            continue
        biegungen.append(dict(art="K", schenkel=[a, b], kanten=[(i, j, e) for i, j, ks in liste for e in ks]))
    # Graph prüfen und Baum ab der Wurzel
    grad = [0] * len(schenkel)
    for x in biegungen:
        for a in x["schenkel"]:
            grad[a] += 1
    fl_sch = [sum(haut[i].flaeche for i in c) for c in schenkel]
    d0 = None
    parallel = True
    for x in biegungen:
        d = _richtung(x, haut)
        x["d"] = d
        if d0 is None:
            d0 = d
        elif abs(abs(d.Dot(d0)) - 1) > 1e-3:
            parallel = False
    kette = parallel and max(grad) <= 2 and len(biegungen) == len(schenkel) - 1
    if kette:
        enden = [i for i, x in enumerate(grad) if x == 1]
        wurzel = min(enden, key=lambda i: (-fl_sch[i], i)) if enden else 0
    else:
        wurzel = max(range(len(schenkel)), key=lambda i: fl_sch[i])
    T = {wurzel: gp_Trsf()}
    ordnung, stapel, kreis = [wurzel], [wurzel], False
    bieg_baum = []
    while stapel:
        a = stapel.pop(0)
        for x in biegungen:
            if a not in x["schenkel"]:
                continue
            b = x["schenkel"][1] if x["schenkel"][0] == a else x["schenkel"][0]
            if b in T:
                if x not in bieg_baum:
                    kreis = True
                continue
            m = _biegung(x, a, b, schenkel, haut, s, k)
            if m is None:
                return dict(fehler="Biegung nicht auswertbar")
            T[b] = T[a].Multiplied(m["trsf"])
            x.update(m, von=a, nach=b)
            bieg_baum.append(x)
            ordnung.append(b)
            stapel.append(b)
    if len(T) != len(schenkel):
        return dict(fehler="Schenkel nicht verbunden")
    # 3. Flächen in die Ebene der Wurzel legen und vereinigen
    teile = []
    for nr, c in enumerate(schenkel):
        for i in c:
            teile.append(BRepBuilderAPI_Transform(haut[i].face, T[nr], True).Shape())
    for x in bieg_baum:
        st = _streifen(x, T[x["von"]])
        if st is not None:
            teile.append(st)
    w = haut[schenkel[wurzel][0]]
    teile = [_ausrichten(x, w.n) for x in teile]
    flaeche = _vereinigen(teile)
    if flaeche is None:
        return dict(fehler="Zuschnitt nicht bildbar")
    erg = _daten(flaeche, w, schenkel, wurzel, bieg_baum, ordnung, kette, kreis, s, d0, T, haut, solid, k)
    erg["mehrachsig"] = not parallel        # geschlossener Ring paralleler Kanten (Rohr) ist nicht mehrachsig
    erg["rohr"] = kreis and parallel        # geschlossener Ring paralleler Kanten: ein Rohr, kein Kantteil
    return erg


def _richtung(x, haut):
    if x["art"] == "Z":
        return g._vec(x["achse"].Direction()).Normalized()
    i, j, _ = x["kanten"][0]
    d = haut[i].n.Crossed(haut[j].n)
    return d.Normalized()


def _mitte(schenkel_flaechen, haut):
    sx = sy = sz = a = 0.0
    for i in schenkel_flaechen:
        p, f = haut[i].p, haut[i].flaeche
        sx, sy, sz, a = sx + p.X() * f, sy + p.Y() * f, sz + p.Z() * f, a + f
    return gp_Pnt(sx / a, sy / a, sz / a)


def _biegung(x, a, b, schenkel, haut, s, k):
    """Drehung + Verschiebung, die Schenkel b in die Ebene von Schenkel a legt (Originallage), dazu Winkel, Radius,
    Biegezugabe und die Lage der Tangente auf Schenkel a."""
    fa, fb = haut[schenkel[a][0]], haut[schenkel[b][0]]
    na, nb = fa.n, fb.n
    phi = math.acos(max(-1.0, min(1.0, na.Dot(nb))))
    if phi < math.radians(0.5):
        return None
    d = x["d"]
    ma, mb = _mitte(schenkel[a], haut), _mitte(schenkel[b], haut)
    if x["art"] == "Z":
        drehpunkt = x["achse"].Location()
        r = x["r"]
        ba = phi * (r + k * s)
        g_ = ba
        scharf = False
    else:
        # scharfe Kante: Innenkante = Schnitt der Innenebenen; innen ist die Seite, zu der Schenkel b abbiegt
        e = x["kanten"][0][2]
        pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in g._liste(e, TopAbs_VERTEX)]
        m = pts[0] if pts else fa.p
        innen = na.Dot(gp_Vec(m, mb)) > 0          # b liegt auf der Außenseite der Haut -> Haut innen
        ha, hb = _pv(fa.p).Dot(na), _pv(fb.p).Dot(nb)
        if not innen:
            ha, hb = ha - s, hb - s
        drehpunkt = _loesen(na, ha, nb, hb, d, _pv(m).Dot(d))
        if drehpunkt is None:
            return None
        r = s                       # scharfkantig gezeichnet: Innenradius = Blechdicke angenommen
        ba = phi * (r + k * s)
        g_ = ba - 2 * r * math.tan(phi / 2)
        scharf = True
    ax = gp_Ax1(drehpunkt, gp_Dir(d.X(), d.Y(), d.Z()))
    # Richtung t: in der Ebene von a, quer zu d, vom Schenkel a zur Biegung
    v = gp_Vec(ma, drehpunkt)
    t = v.Subtracted(g._vec(ax.Direction()).Multiplied(v.Dot(g._vec(ax.Direction()))))
    t = t.Subtracted(na.Multiplied(t.Dot(na)))
    if t.Magnitude() < 1e-9:
        return None
    t.Normalize()
    best = None
    for w in (phi, -phi):
        rot = gp_Trsf()
        rot.SetRotation(ax, w)
        n2 = nb.Transformed(rot)
        p2 = mb.Transformed(rot)
        guete = n2.Dot(na) + (1 if gp_Vec(drehpunkt, p2).Dot(t) > 0 else -1)
        if best is None or guete > best[0]:
            best = (guete, rot)
    tr = gp_Trsf()
    tr.SetTranslation(t.Multiplied(g_))
    m_ = tr.Multiplied(best[1])
    # Tangente auf Schenkel a (Haut-Ebene): Lot des Drehpunkts auf die Ebene, bei scharfen Kanten um r·tan(φ/2)
    # zurück; Ausdehnung längs d aus den Kanten bzw. Flächen der Biegung
    lot = _pv(drehpunkt).Subtracted(na.Multiplied(gp_Vec(fa.p, drehpunkt).Dot(na)))
    tangente = lot.Subtracted(t.Multiplied(r * math.tan(phi / 2))) if scharf else lot
    werte = []
    for i in (x.get("flaechen") or []):
        werte += [_pv(BRep_Tool.Pnt_s(TopoDS.Vertex(v))).Dot(d) for v in g._liste(haut[i].face, TopAbs_VERTEX)]
    for _, _, e in (x.get("kanten") or []):
        werte += [_pv(BRep_Tool.Pnt_s(TopoDS.Vertex(v))).Dot(d) for v in g._liste(e, TopAbs_VERTEX)]
    if not werte:
        return None
    vorzeichen = 1 if na.Dot(gp_Vec(drehpunkt, mb)) > 0 else -1     # + = b biegt zur Außenseite der Haut
    return dict(trsf=m_, winkel=round(math.degrees(phi), 2) * vorzeichen, phi=phi, radius=None if scharf else r,
                r_rechnen=r, ba=ba, t=t, tangente=tangente, d_von=min(werte), d_bis=max(werte), scharf=scharf,
                setback=(r + s) * (math.tan(phi / 2) if phi <= math.pi / 2 + 1e-9 else 1.0))


def _streifen(x, ta):
    """Biegestreifen (Breite BA ab der Tangente auf Schenkel a) als ebene Fläche in der Abwicklung."""
    d = x["d"]
    base = x["tangente"].Subtracted(d.Multiplied(x["tangente"].Dot(d)))
    p1 = base.Added(d.Multiplied(x["d_von"]))
    p2 = base.Added(d.Multiplied(x["d_bis"]))
    breite = x["ba"]
    if breite <= 1e-6 or x["d_bis"] - x["d_von"] < 1e-6:
        return None
    p3, p4 = p2.Added(x["t"].Multiplied(breite)), p1.Added(x["t"].Multiplied(breite))
    poly = BRepBuilderAPI_MakePolygon()
    for p in (p1, p2, p3, p4):
        poly.Add(gp_Pnt(p.XYZ()))
    poly.Close()
    f = BRepBuilderAPI_MakeFace(poly.Wire(), True)
    if not f.IsDone():
        return None
    x["streifen"] = [gp_Pnt(p.XYZ()).Transformed(ta) for p in (p1, p2, p3, p4)]
    return BRepBuilderAPI_Transform(f.Face(), ta, True).Shape()


def _ausrichten(f, n):
    """Fläche so wenden, dass ihre Normale nach außen wie n zeigt (sonst vereinigt OpenCascade sie nicht)."""
    f = TopoDS.Face(f)
    p = _punkt_flaeche(f)
    m = _normale(f, p) if p else None
    return TopoDS.Face(f.Reversed()) if m is not None and m.Dot(n) < 0 else f


def _punkt_flaeche(f):
    pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in g._liste(f, TopAbs_VERTEX)]
    if not pts:
        return None
    return gp_Pnt(sum(p.X() for p in pts) / len(pts), sum(p.Y() for p in pts) / len(pts),
                  sum(p.Z() for p in pts) / len(pts))


def _vereinigen(teile):
    if len(teile) == 1:
        return TopoDS.Face(teile[0])
    a, t = TopTools_ListOfShape(), TopTools_ListOfShape()
    a.Append(teile[0])
    for x in teile[1:]:
        t.Append(x)
    fu = BRepAlgoAPI_Fuse()
    fu.SetArguments(a)
    fu.SetTools(t)
    fu.SetFuzzyValue(1e-3)
    fu.Build()
    if not fu.IsDone():
        return None
    u = ShapeUpgrade_UnifySameDomain(fu.Shape(), True, True, False)
    u.Build()
    fl = g._liste(u.Shape(), TopAbs_FACE)
    if not fl:
        return None
    return TopoDS.Face(max(fl, key=g._flaeche)), len(fl)


def _daten(erg, w, schenkel, wurzel, bieg_baum, ordnung, kette, kreis, s, d0, T, haut, solid, k):
    face, n_flaechen = erg if isinstance(erg, tuple) else (erg, 1)
    o, n = w.p, w.n
    # Achsen des Zuschnitts: Kette x = Biegekante, y = quer (vom freien Ende von Schenkel 1 weg); sonst beliebig,
    # danach kleinstes umschreibendes Rechteck
    if d0 is not None:
        ex = d0.Subtracted(n.Multiplied(d0.Dot(n))).Normalized()
    else:
        ex = gp_Vec(1, 0, 0) if abs(n.X()) < 0.9 else gp_Vec(0, 1, 0)
        ex = ex.Subtracted(n.Multiplied(ex.Dot(n))).Normalized()
    ey = n.Crossed(ex)
    if kette and bieg_baum and bieg_baum[0]["t"].Dot(ey) < 0:
        ey = ey.Reversed()
    if ex.Crossed(ey).Dot(n) < 0:      # rechtshändig mit der Normalen zum Betrachter (Außenseite der Haut oben)
        ex = ex.Reversed()

    def xy(p):
        v = gp_Vec(o, p)
        return v.Dot(ex), v.Dot(ey)
    aussen = BRepTools.OuterWire_s(face)
    pa = [xy(p) for p in g._draht_punkte(aussen)]
    drehung = 0.0
    if not kette:
        drehung = g._min_rechteck(pa)
    c, s_ = math.cos(drehung), math.sin(drehung)

    def rot(x, y):
        return x * c + y * s_, -x * s_ + y * c
    pa = [rot(x, y) for x, y in pa]
    x0, y0 = min(x for x, _ in pa), min(y for _, y in pa)

    def zu(p):
        x, y = rot(*xy(p))
        return x - x0, y - y0
    pa = [(x - x0, y - y0) for x, y in pa]
    laenge, breite = max(x for x, _ in pa), max(y for _, y in pa)
    if not kette and breite > laenge:
        laenge, breite = breite, laenge
        pa = [(y, laenge - x) for x, y in pa]
        zu_alt = zu

        def zu(p):
            x, y = zu_alt(p)
            return y, laenge - x
    innen = [TopoDS.Wire(d) for d in g._liste(face, TopAbs_WIRE) if not d.IsSame(aussen)]
    konturen_lage, bohrungen, innen_liste, innen_laenge = [], {}, [], 0.0
    for dr in innen:
        lg = g._draht_laenge(dr)
        innen_laenge += lg
        dm = g._wire_kreis(dr)
        if dm is not None:
            bohrungen[dm] = bohrungen.get(dm, 0) + 1
        try:
            kk = g._blech_kontur([zu(p) for p in g._draht_punkte(dr)])
        except (ValueError, ZeroDivisionError, IndexError):
            continue
        kk["schnittlaenge"] = round(lg, 2)
        konturen_lage.append(kk)
        hm = max(kk.get("durchmesser") or 0, kk.get("laenge") or 0, kk.get("breite") or 0,
                 *(max(abs(a), abs(b)) * 2 for a, b in kk.get("punkte") or ()))
        innen_liste.append((round(hm, 2), round(lg, 2)))
    flaeche_netto = g._flaeche(face)
    mf = BRepBuilderAPI_MakeFace(aussen, True)
    flaeche_aussen = g._flaeche(mf.Face()) if mf.IsDone() else laenge * breite
    rechteckig = abs(flaeche_aussen - laenge * breite) <= 0.002 * laenge * breite
    aussen_punkte = None if rechteckig else [[round(x, 2), round(y, 2)] for x, y in g._vereinfachen(pa)]
    biegelinien = []
    for x in bieg_baum:
        if not x.get("streifen"):
            continue
        a, b, cc, dd = (zu(p) for p in x["streifen"])
        mitte = [((a[0] + dd[0]) / 2, (a[1] + dd[1]) / 2), ((b[0] + cc[0]) / 2, (b[1] + cc[1]) / 2)]
        biegelinien.append(dict(punkte=[[round(u, 2), round(v, 2)] for u, v in mitte], winkel=x["winkel"],
                                radius=None if x["radius"] is None else round(x["radius"], 2),
                                scharf=x["scharf"], ba=round(x["ba"], 3),
                                von=[[round(u, 2), round(v, 2)] for u, v in (a, b)],
                                bis=[[round(u, 2), round(v, 2)] for u, v in (cc, dd)]))
    hinweise = []
    sch_liste = None
    if kette:
        sch_liste = _schenkel_kette(bieg_baum, ordnung, zu, breite, s)
    if kreis:
        hinweise.append("geschlossene Kanten (Ecken verbunden): Ecken im Zuschnitt prüfen")
    if n_flaechen > 1:
        hinweise.append("Zuschnitt nicht zusammenhängend, prüfen")
    if any(x["scharf"] for x in bieg_baum):
        hinweise.append(f"scharfkantig gezeichnet: Innenradius {s:g} mm (= Blechdicke) angenommen")
    vol = g._volumen(solid)
    if vol > 0 and abs(flaeche_netto * s - vol) > 0.1 * vol:
        hinweise.append("Zuschnittfläche passt nicht zum Volumen, Abwicklung prüfen")
    return dict(kantlaenge=round(laenge, 2) if kette else None, laenge=laenge, breite=breite,
                flaeche_netto=flaeche_netto, flaeche_aussen=flaeche_aussen, umfang_aussen=g._draht_laenge(aussen),
                umfang_innen=innen_laenge, innen=len(innen), bohrungen=dict(sorted(bohrungen.items())),
                innen_liste=innen_liste, konturen_lage=konturen_lage, aussen_punkte=aussen_punkte,
                rechteckig=rechteckig, biegelinien=biegelinien, kantungen=len(bieg_baum), schenkel=sch_liste,
                mehrachsig=not kette, scharf=any(x["scharf"] for x in bieg_baum), k_faktor=k, hinweise=hinweise)


def _schenkel_kette(bieg_baum, ordnung, zu, breite, s):
    """Schenkel einer Kette mit Außenmaß (Blech-Editor): flache Länge zwischen den Biegestreifen + Rücksprung
    (r + s)·tan(φ/2) (über 90°: r + s) je Biegung, Winkel mit Vorzeichen, Innenradius (None = Blechdicke)."""
    streifen = []
    for x in bieg_baum:
        if not x.get("streifen"):
            return None
        ys = [zu(p)[1] for p in x["streifen"]]
        streifen.append((min(ys), max(ys), x))
    streifen.sort(key=lambda z: z[0])
    out, pos = [], 0.0
    for i, (y_von, y_bis, x) in enumerate(streifen):
        flach = y_von - pos
        lg = flach + x["setback"] + (streifen[i - 1][2]["setback"] if i else 0.0)
        out.append(dict(laenge=round(lg, 2), winkel=x["winkel"], radius=x["radius"] if x["radius"] is None
                        else round(x["radius"], 2)))
        pos = y_bis
    lg = breite - pos + (streifen[-1][2]["setback"] if streifen else 0.0)
    out.append(dict(laenge=round(lg, 2), winkel=0.0, radius=None))
    return out
