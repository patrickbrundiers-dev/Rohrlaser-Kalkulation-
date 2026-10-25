"""Knickrahmen aus einem Körper (Plan K1-3, Fall A): ein geknickter Rahmen aus Quadrat- oder Rechteckrohr, der als
ein Volumenkörper in der STEP-Datei steht (Ecken mit durchgehender Stegwand, die übrigen Wände stoßen mit Gehrung
aneinander, ohne Spalt).

Erkennung: Der Körper ist eben (Normale = Hauptträgheitsachse mit dem größten Moment), der Schnitt in halber Höhe
zeigt die Wände. Seine konvexe Hülle gibt die Außenkontur: lange, mit Material belegte Seiten sind die Schenkel
(Außenmaß A = Abstand der Eckpunkte), eine lange unbelegte Seite ist die Lücke eines offenen Rahmens. Je Schenkel
prüft ein Strahl von außen nach innen das Hohlprofil (Wand s, Maß h in der Rahmenebene), ein Strahl quer zur Ebene
die Wand oben und unten (Maß b quer zur Ebene). Dann wird der Körper an den Winkelhalbierenden der Ecken in gerade
Rohrstücke mit Gehrung geteilt und jedes Stück wie ein Einzelrohr gemessen (Bohrungen, Ausschnitte, Enden, Lage).
Das Programm verbindet die Stücke wie Einzelrohre zum Knickrahmen (rohrlaser/knickverbindung.py).

Ergebnis: Teil wie ein Rohr des Profils (Länge = Summe der Schenkel außen) mit t.knick_schenkel = gemessene Stücke
in Reihenfolge, Netz = der Körper in Dateilage. Prüfstatus immer „prüfen“."""
import math

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GProp import GProp_GProps
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.gp import gp_Ax3, gp_Dir, gp_Lin, gp_Pnt, gp_Trsf, gp_Vec

import step_geometrie as g

HINWEIS = "Knickrahmen aus einem Körper"
TOL = 0.15              # mm: gleiche Wand, gleiches Maß
TOL_WINKEL = 1.5        # Grad: gleiche Knickwinkel
BELEGT = 0.7            # Anteil einer Hüllseite mit Material: Schenkel
DICKE_MIN = 5.0         # mm: kleinste Profilhöhe quer zur Ebene
SNAP_GRAD = 2.0         # Grad: so weit darf die Trägheitsachse von der Wandnormale abweichen


def _ebene(solid):
    """System mit Z = Normale der Rahmenebene, Ursprung im Schwerpunkt. Grob die Hauptträgheitsachse mit dem größten
    Moment; sind Bohrungen oder Ausschnitte nicht symmetrisch zur Mittelebene verteilt, kippt sie leicht (Bruchteile
    eines Grads, bei 1 m Schenkel schon Zehntel mm). Deshalb genau: die Normale der flächengrößten ebenen Wand, die
    höchstens SNAP_GRAD von der Achse abweicht (Ober- oder Unterwand des Rahmens)."""
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, p)
    m = p.MatrixOfInertia()
    werte, vek = g._eigen3([[m.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)])
    k = max(range(3), key=lambda i: werte[i])
    n = gp_Dir(vek[0][k], vek[1][k], vek[2][k])
    best, gross = None, 0.0
    for f in g._liste(solid, TopAbs_FACE):
        pl = g._ebene(f)
        if pl is None:
            continue
        d = pl.Axis().Direction()
        if abs(d.Dot(n)) < math.cos(math.radians(SNAP_GRAD)):
            continue
        a = g._flaeche(f)
        if a > gross:
            best, gross = (d if d.Dot(n) > 0 else d.Reversed()), a
    return gp_Ax3(p.CentreOfMass(), best or n)


def _huelle(pts):
    """Konvexe Hülle (gegen den Uhrzeigersinn)."""
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def kreuz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    unten, oben = [], []
    for p in pts:
        while len(unten) >= 2 and kreuz(unten[-2], unten[-1], p) <= 1e-9:
            unten.pop()
        unten.append(p)
    for p in reversed(pts):
        while len(oben) >= 2 and kreuz(oben[-2], oben[-1], p) <= 1e-9:
            oben.pop()
        oben.append(p)
    return unten[:-1] + oben[:-1]


def _seiten(huelle, tol_grad=0.5):
    """Seiten der Hülle, fast gerade weiterlaufende zusammengefasst: Liste (Anfang, Ende)."""
    seiten = [(huelle[i], huelle[(i + 1) % len(huelle)]) for i in range(len(huelle))]
    out = []
    for a, b in seiten:
        if out:
            pa, pb = out[-1]
            w1 = math.atan2(pb[1] - pa[1], pb[0] - pa[0])
            w2 = math.atan2(b[1] - a[1], b[0] - a[0])
            if abs(math.degrees((w2 - w1 + math.pi) % (2 * math.pi) - math.pi)) < tol_grad:
                out[-1] = (pa, b)
                continue
        out.append((a, b))
    if len(out) > 2:        # erste und letzte Seite können ebenso zusammengehören
        (pa, pb), (a, b) = out[-1], out[0]
        w1 = math.atan2(pb[1] - pa[1], pb[0] - pa[0])
        w2 = math.atan2(b[1] - a[1], b[0] - a[0])
        if abs(math.degrees((w2 - w1 + math.pi) % (2 * math.pi) - math.pi)) < tol_grad:
            out[0] = (pa, b)
            out.pop()
    return out


def _laenge(s):
    return math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1])


def _richtung(s):
    lg = _laenge(s) or 1.0
    return ((s[1][0] - s[0][0]) / lg, (s[1][1] - s[0][1]) / lg)


def _belegt(s, strecken, n=40):
    """Anteil der Seite, an dem Material liegt (Schnittkonturen höchstens 0,05 mm entfernt)."""
    treffer = 0
    for k in range(n):
        u = (k + 0.5) / n
        x, y = s[0][0] + u * (s[1][0] - s[0][0]), s[0][1] + u * (s[1][1] - s[0][1])
        treffer += g._nah_zug(x, y, strecken, 0.05)
    return treffer / n


def _schnittpunkt(s1, s2):
    (x1, y1), (x2, y2) = s1
    (x3, y3), (x4, y4) = s2
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-12:
        return None
    a, b = x1 * y2 - y1 * x2, x3 * y4 - y3 * x4
    return ((a * (x3 - x4) - (x1 - x2) * b) / d, (a * (y3 - y4) - (y1 - y2) * b) / d)


def _wand_innen(s, strecken):
    """Strahl von der Außenseite s nach innen an drei Stellen: (Wand s, Maß h) des Hohlprofils oder None."""
    dx, dy = _richtung(s)
    nx, ny = -dy, dx        # Hülle gegen den Uhrzeigersinn: innen = links
    werte = []
    for u in (0.5, 0.35, 0.65, 0.25, 0.75):
        x, y = s[0][0] + u * (s[1][0] - s[0][0]) - nx, s[0][1] + u * (s[1][1] - s[0][1]) - ny
        d = sorted(v - 1.0 for v in g._strahl_alle(x, y, nx, ny, strecken))
        if len(d) >= 4 and abs(d[0]) < 0.05 and d[1] > 0.2 and d[2] - d[1] > d[1]:
            werte.append((round(d[1], 2), round(d[3], 2)))
    if not werte:
        return None
    return max(set(werte), key=werte.count)


def _wand_quer(lok, x, y, zmin, zmax):
    """Strahl quer zur Rahmenebene durch (x, y): Wand oben/unten oder None."""
    sx = IntCurvesFace_ShapeIntersector()
    sx.Load(lok, 1e-6)
    sx.Perform(gp_Lin(gp_Pnt(x, y, zmin - 1.0), gp_Dir(0, 0, 1)), -1e9, 1e9)
    if not sx.IsDone():
        return None
    z = sorted(sx.Pnt(i).Z() for i in range(1, sx.NbPnt() + 1))
    if len(z) != 4 or abs(z[0] - zmin) > 0.05 or abs(z[3] - zmax) > 0.05:
        return None
    s1, s2 = z[1] - z[0], z[3] - z[2]
    return (s1 + s2) / 2 if abs(s1 - s2) <= TOL else None


def erkennen(solid):
    """Knickrahmen im Körper: dict(ax3, zmin, zmax, schenkel=[dict(a, e, d, n, laenge)], geschlossen, beta,
    s, h, b) oder None. a, e = Anfang und Ende der Außenseite in der Ebene (lokal), d = Richtung, n = nach innen."""
    ax3 = _ebene(solid)
    lok = g._transformiere(solid, ax3)
    zmin, zmax = g._z_bereich(lok)
    b = zmax - zmin
    if b < DICKE_MIN:
        return None
    ws = g._schnitt(lok, (zmin + zmax) / 2)
    if len(ws) < 2:
        return None
    strecken = [s for w in ws for s in g._strecken(w[1], 2.0)]
    pts = [(round(x, 6), round(y, 6)) for s in strecken for x, y in ((s[0], s[1]), (s[2], s[3]))]
    huelle = _huelle(pts)
    if len(huelle) < 3:
        return None
    seiten = _seiten(huelle)
    if max(_laenge(s) for s in seiten) < 3 * b:
        return None      # gerades Rohr o. ä.: die Hülle ist nicht viel größer als das Profil
    belegt = [_belegt(s, strecken) >= BELEGT for s in seiten]
    lang = [s for s, j in zip(seiten, belegt) if j]
    if not lang:
        return None
    s, h = _wand_innen(max(lang, key=_laenge), strecken) or (None, None)
    if not s or h < 2.5 * s or h > _laenge(max(lang, key=_laenge)) / 2:
        return None
    grenze = 1.5 * max(h, b)
    art = ["S" if j and _laenge(x) >= grenze else "L" if _laenge(x) >= grenze else "k" for x, j in zip(seiten, belegt)]
    if art.count("L") > 1 or art.count("S") < 2:
        return None
    geschlossen = "L" not in art
    if not geschlossen:         # Reihenfolge ab der Lücke
        i = art.index("L")
        seiten, art = seiten[i + 1:] + seiten[:i], art[i + 1:] + art[:i]
    elif art[0] != "S":
        i = art.index("S")
        seiten, art = seiten[i:] + seiten[:i], art[i:] + art[:i]
    while art and art[0] == "k":    # kurze Seiten am Anfang/Ende eines offenen Rahmens: Enden der Schenkel
        seiten, art = seiten[1:], art[1:]
    while art and art[-1] == "k":
        seiten, art = seiten[:-1], art[:-1]
    sch = [x for x, a_ in zip(seiten, art) if a_ == "S"]
    if len(sch) < (3 if geschlossen else 2):
        return None
    ecken = []
    for i in range(len(sch) if geschlossen else len(sch) - 1):
        p = _schnittpunkt(sch[i], sch[(i + 1) % len(sch)])
        if p is None:
            return None
        ecken.append(p)
    out, betas = [], []
    for i, x in enumerate(sch):
        a = ecken[i - 1] if (geschlossen or i > 0) else x[0]
        e = ecken[i] if (geschlossen or i < len(sch) - 1) else x[1]
        d = _richtung((a, e))
        w = _wand_innen(x, strecken)
        if w is None or abs(w[0] - s) > TOL or abs(w[1] - h) > TOL:
            return None
        n = (-d[1], d[0])
        mx, my = (a[0] + e[0]) / 2 + n[0] * h / 2, (a[1] + e[1]) / 2 + n[1] * h / 2
        sq = _wand_quer(lok, mx, my, zmin, zmax)
        if sq is None:      # Bohrung o. ä. in der Mitte: daneben versuchen
            mx, my = mx + d[0] * h, my + d[1] * h
            sq = _wand_quer(lok, mx, my, zmin, zmax)
        if sq is None or abs(sq - s) > TOL:
            return None
        out.append(dict(a=a, e=e, d=d, n=n, laenge=math.hypot(e[0] - a[0], e[1] - a[1])))
    for i in range(len(out) if geschlossen else len(out) - 1):
        d1, d2 = out[i]["d"], out[(i + 1) % len(out)]["d"]
        betas.append(math.degrees(math.acos(max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1])))))
    if max(betas) - min(betas) > TOL_WINKEL or min(betas) < 5 or max(betas) > 175:
        return None
    return dict(ax3=ax3, zmin=zmin, zmax=zmax, schenkel=out, geschlossen=geschlossen,
                beta=round(sum(betas) / len(betas), 1), s=s, h=h, b=b)


def _halbierende(d1, d2):
    """Richtung der Winkelhalbierenden an der Ecke (von außen nach innen) zwischen Schenkel d1 und d2."""
    x, y = d2[0] - d1[0], d2[1] - d1[1]
    lg = math.hypot(x, y) or 1.0
    return (x / lg, y / lg)


def _stueck(solid, r, i):
    """Körper an den Winkelhalbierenden der Ecken von Schenkel i geteilt: das gerade Rohrstück mit Gehrung (in
    Dateilage) oder None."""
    sch = r["schenkel"]
    t = sch[i]
    d, n = t["d"], t["n"]
    tief = r["h"] + 1.0
    rand = 1.0

    def ecke(p, u):
        """Punkte der Schnittlinie durch p in Richtung u: außen (rand vor der Außenseite) und innen (tief)."""
        k = u[0] * n[0] + u[1] * n[1]
        return ((p[0] - u[0] * rand / k, p[1] - u[1] * rand / k), (p[0] + u[0] * tief / k, p[1] + u[1] * tief / k))

    def frei(p, richtung):
        q = (p[0] + richtung * d[0] * tief, p[1] + richtung * d[1] * tief)
        return ((q[0] - n[0] * rand, q[1] - n[1] * rand), (q[0] + n[0] * tief, q[1] + n[1] * tief))
    nr = len(sch)
    if r["geschlossen"] or i > 0:
        a_aus, a_in = ecke(t["a"], _halbierende(sch[(i - 1) % nr]["d"], d))
    else:
        a_aus, a_in = frei(t["a"], -1)
    if r["geschlossen"] or i < nr - 1:
        e_aus, e_in = ecke(t["e"], _halbierende(d, sch[(i + 1) % nr]["d"]))
    else:
        e_aus, e_in = frei(t["e"], 1)
    poly = BRepBuilderAPI_MakePolygon()
    z0 = r["zmin"] - 1.0
    for x, y in (a_aus, e_aus, e_in, a_in):
        poly.Add(gp_Pnt(x, y, z0))
    poly.Close()
    prisma = BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(poly.Wire()).Face(),
                                   gp_Vec(0, 0, r["zmax"] - r["zmin"] + 2.0)).Shape()
    tr = gp_Trsf()
    tr.SetTransformation(r["ax3"])
    prisma = BRepBuilderAPI_Transform(prisma, tr.Inverted(), True).Shape()
    teil = g._boolesch("common", solid, prisma)
    if teil is None:
        return None
    koerper = g._liste(teil, TopAbs_SOLID)
    return max(koerper, key=g._volumen) if koerper else None


def _ecken_gehrung(t, r, i):
    """Enden des Stücks i an einer Ecke sind Gehrungen mit β/2, längste Stelle außen. Ist die Außenkante der Ecke
    gerundet (Knick mit Radius statt scharfer Kante), hält die Messung das Ende für eine Fase oder „komplex“; dann
    wird es aus der bekannten Eckgeometrie gesetzt, sonst passt die Knickverbindung die Stücke nicht zusammen."""
    sch, nr = r["schenkel"], len(r["schenkel"])
    if not (t.ende_a_global and t.achse_global and t.x_global):
        return
    ax_r = r["ax3"]
    z = gp_Vec(*t.achse_global)
    x = gp_Vec(*t.x_global)
    y = z.Crossed(x)
    n = sch[i]["n"]
    aussen = gp_Vec(-n[0], -n[1], 0.0)     # lokal in der Rahmenebene → global
    tr = gp_Trsf()
    tr.SetTransformation(ax_r)
    aussen = aussen.Transformed(tr.Inverted())
    ref = g._bezug(gp_Ax3(gp_Pnt(*t.ende_a_global), gp_Dir(z), gp_Dir(x)), t.profilform)
    richtung = round((math.degrees(math.atan2(-aussen.Dot(x), aussen.Dot(y))) - ref) % 360, 1) % 360
    a_glob = g._global(ax_r, sch[i]["a"][0], sch[i]["a"][1], 0.0)
    e_glob = g._global(ax_r, sch[i]["e"][0], sch[i]["e"][1], 0.0)
    # Ende A des Stücks liegt am Schenkelanfang a, wenn die Achse von a nach e zeigt
    a_am_anfang = z.Dot(gp_Vec(a_glob, e_glob)) > 0
    ecke = {"A" if a_am_anfang else "B": r["geschlossen"] or i > 0,
            "B" if a_am_anfang else "A": r["geschlossen"] or i < nr - 1}
    halb = round(r["beta"] / 2, 2)
    for d in t.konturen_liste:
        e = d.get("art", "")[-1:] if d.get("art") in ("Ende A", "Ende B") else None
        if not e or not ecke[e] or (d.get("form") == "Gehrung" and abs((d.get("gehrung") or 0) - halb) < 1.0):
            continue
        d.update(form="Gehrung", gehrung=halb, um_x=halb, um_y=0.0, richtung=richtung)
        for k in ("fase", "hinweis", "umriss"):
            d.pop(k, None)
        t.hinweise = [h for h in t.hinweise if not (h.startswith(f"Ende {e}:") and g.FASE_HINWEIS in h)]
        setattr(t, "ende_a_gerade" if e == "A" else "ende_b_gerade", False)


def messen(solid, datei="", koerper=1, netz=False):
    """Knickrahmen aus einem Körper messen: Teil mit knick_schenkel oder None (kein Knickrahmen)."""
    r = erkennen(solid)
    if r is None:
        return None
    stuecke = []
    for i in range(len(r["schenkel"])):
        k = _stueck(solid, r, i)
        if k is None:
            return None
        t = g._profil_messen(k, datei, koerper, False)
        if t.profilform not in ("Quadratrohr", "Rechteckrohr"):
            return None
        t.__dict__.pop("_rahmen", None)
        _ecken_gehrung(t, r, i)
        stuecke.append(t)
    t0 = stuecke[0]
    if any(t.profilform != t0.profilform or abs(t.wandstaerke - t0.wandstaerke) > TOL
           or abs(max(t.abm_a, t.abm_b) - max(t0.abm_a, t0.abm_b)) > TOL
           or abs(min(t.abm_a, t.abm_b) - min(t0.abm_a, t0.abm_b)) > TOL for t in stuecke[1:]):
        return None
    out = g.Teil(datei=datei, koerper=koerper)
    for n in ("profilform", "abm_a", "abm_b", "wandstaerke", "flaeche", "innen_a", "innen_b", "kammern",
              "kontur_umfang"):
        setattr(out, n, getattr(t0, n))
    out.bauteiltyp = "Profil"
    out.laenge = round(sum(x["laenge"] for x in r["schenkel"]), 3)
    for n in ("schneidweg", "innen", "gravur"):
        setattr(out, n, sum(getattr(t, n) for t in stuecke))
    for n in ("konturen", "innen_konturen", "gravur_konturen"):
        setattr(out, n, sum(getattr(t, n) for t in stuecke))
    for t in stuecke:
        for n in ("bohrungen", "senkungen", "fliessloecher"):
            for k, v in getattr(t, n).items():
                getattr(out, n)[k] = getattr(out, n).get(k, 0) + v
        out.innen_liste += t.innen_liste
    knicke = len(r["schenkel"]) - (0 if r["geschlossen"] else 1)
    out.hinweise.append(f"{HINWEIS}: {len(r['schenkel'])} Schenkel "
                        + " / ".join(f"{x['laenge']:.1f}".replace(".", ",") for x in r["schenkel"])
                        + f" mm, {knicke} Ecken mit {r['beta']:.1f}°".replace(".", ",")
                        + (", geschlossen" if r["geschlossen"] else ", offen") + " – bitte prüfen")
    out.knick_schenkel = stuecke
    if netz:
        out.netz = _netz(solid, r)
    return out


def _netz(solid, r):
    """3D-Ansicht des gefalteten Rahmens in Dateilage: ebene Flächen als Außenwand, die übrigen (Bohrungen,
    Ausschnitte) als Innenkontur."""
    from OCP.TopExp import TopExp
    try:
        faces = g.TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(solid, TopAbs_FACE, faces)
        arten = {i: "A" if g._ebene(faces.FindKey(i)) is not None else "K" for i in range(1, faces.Extent() + 1)}
        groesse = sum(x["laenge"] for x in r["schenkel"]) / 4
        n = g.dreiecksnetz(solid, faces, arten, [], 0.0, max(10.0, groesse / 20))
        n["lage"] = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]
        return n
    except Exception:  # 3D-Ansicht darf die Messung nie verhindern
        return None
