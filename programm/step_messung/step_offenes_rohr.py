"""Offene Rohre aus dem Rohr lasern (Patrick 25.10.2026, Freigabe „Alle a“, danach „Nur vielleicht 2 mm die Fläche
schließen nicht komplett“ und „Je ein Steg 2 mm an beiden Enden“): Kunden zeichnen Quadrat- oder Rechteckrohre oft
als gekantetes Blech mit einer offenen Seite (U offen, C mit Längsschlitz, U mit einer Lasche). Gefertigt wird das
Teil auf dem Rohrlaser aus dem geschlossenen Rohr: Von der offenen Seite bleibt an Ende A und Ende B je ein Steg
STEG (2 mm) stehen, damit das Teil ein Rohr bleibt, dazwischen wird die Wand als Fenster ausgeschnitten (Innenkontur
im Schneidweg). Ein schmaler Spalt bis SPALT_MAX (2 mm) wird ganz geschlossen (ein Fenster wäre dort sinnlos).

Erkennung: gleich dicke Wände, Querschnitt mit einer Kontur in einem Hüllrechteck, drei Seiten mit Material belegt,
eine Seite über die ganze Länge offen (an allen Messlagen dieselbe Lücke). Öffnungen, die nicht über die ganze
Länge gehen, sind Ausschnitte und bleiben (Frage 3 a); Laschen und Schlitzränder bleiben stehen, das Fenster liegt
genau über der Lücke (Frage 4 a). Wand bzw. Stege füllen je Lücke den Bereich zwischen den Rändern (Blechdicke,
Hüllrechteck außen); die Enden folgen den Nachbarwänden (Frage 2 a): Verlauf der gegenüberliegenden Wand, quer dazu die Steigung der
Seitenwände, damit wird ein gerades Ende gerade und eine Gehrung eine Gehrung.

Der Körper mit Stegen wird wie jedes Rohr gemessen (Querschnitt aus dem geschlossenen Rohr, Konturen der vorhandenen
Wände bleiben, das Fenster ist eine Innenkontur). Ergebnis: Teil als Quadrat-/Rechteckrohr mit offene_seite (Seite,
Lücken, Länge, Steg) in t.geschlossen der offenen Messung; deren Netz zeigt die Stege bzw. den geschlossenen Spalt als
Art „EO“ (im Programm rot „EW“, sobald das Teil als Rohr gilt). Ob das Rohr vorgeschlagen wird, entscheidet das Programm (nur, wenn es das
Rohr in den Stammdaten gibt, Frage 1 a, step.offene_rohre_vorbelegen)."""
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_SOLID
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Trsf

import math

import step_geometrie as g

HINWEIS = "Offenes Rohr"
KANDIDATEN = ("U-Profil", "C-Profil", "offenes Sonderprofil", "Blech gekantet")
ROHRE = ("Quadratrohr", "Rechteckrohr")
LAGEN = 9               # Messlagen über die Länge (10 … 90 %)
SCHRITT = 0.25          # mm, Abtastung entlang einer Seite
LUECKE_INNEN = 0.5      # mm, kleinste Lücke mitten in einer Seite (Schlitz)
TOL_WAND = 0.15         # mm, Wandstärke des geschlossenen Rohrs gegen die Blechdicke
TOL_HUELLE = 0.2        # mm, Hüllrechteck an allen Lagen gleich
SPALT_MAX = 2.0         # mm, breitester Spalt, der ganz geschlossen wird (sonst Stege und Fenster)
STEG = 2.0              # mm, Steg über der offenen Seite an Ende A und Ende B (Patrick 25.10.2026)
SPALT_TOL = 0.05        # mm, Messtoleranz auf SPALT_MAX


def _dicke(t):
    if t.bauteiltyp == "Blech gekantet":
        return float((t.blech or {}).get("dicke") or 0.0)
    if t.normprofil or t.sicherheit.get("wandstaerke") == "unsicher" or \
            any(h.startswith("Wandstärken verschieden") for h in t.hinweise):
        return 0.0              # Walzprofil (UPN) oder ungleich dicke Wände: kein gekantetes Rohr
    return t.wandstaerke


def _luecken(strecken, seite, x0, y0, x1, y1, d):
    """Lücken der Seite auf der Mittellinie der Wand (d/2 innen): Liste (von, bis) entlang der Seite."""
    if seite in ("unten", "oben"):
        a, b = x0, x1
        v = y0 + d / 2 if seite == "unten" else y1 - d / 2
        punkt = lambda u: (u, v)    # noqa: E731
    else:
        a, b = y0, y1
        v = x0 + d / 2 if seite == "links" else x1 - d / 2
        punkt = lambda u: (v, u)    # noqa: E731
    n = max(2, int((b - a) / SCHRITT))
    def frei(u):
        return not g._im_material(*punkt(u), strecken)

    def kante(u_frei, u_voll):
        for _ in range(14):         # Rand der Lücke auf etwa 0,02 µm genau (Halbierung)
            m = (u_frei + u_voll) / 2
            u_frei, u_voll = (m, u_voll) if frei(m) else (u_frei, m)
        return (u_frei + u_voll) / 2
    out, start, vorher = [], None, None
    for k in range(n + 1):
        u = a + 0.01 + (b - a - 0.02) * k / n       # nicht genau auf der Hülle (Punkt auf dem Rand: unbestimmt)
        f = frei(u)
        if f and start is None:
            start = a if vorher is None else kante(u, vorher)
        elif not f and start is not None:
            out.append((start, kante(vorher, u)))
            start = None
        vorher = u
    if start is not None:
        out.append((start, b))
    return out, a, b


def _offen(luecken, a, b, d):
    """Lücken, die die Seite öffnen: mitten in der Seite ab LUECKE_INNEN, am Rand (Ecke) erst ab der Größe, die eine
    Biegerundung nicht erreicht (4 × Dicke, mindestens 15 % der Seite)."""
    rand = max(4 * d, 0.15 * (b - a))
    return [(u0, u1) for u0, u1 in luecken
            if (u1 - u0 >= rand) or (u0 > a + SCHRITT and u1 < b - SCHRITT and u1 - u0 >= LUECKE_INNEN)]


def erkennen(solid, d):
    """Offene Seite des Körpers: dict(ax3, seite, luecken [(von, bis)], huelle (x0, y0, x1, y1), z (zmin, zmax)) im
    lokalen System (Z = Achse) oder None."""
    ax3, _ = g._lage(solid)
    lok = g._transformiere(solid, ax3)
    zmin, zmax = g._z_bereich(lok)
    if zmax - zmin < 3 * d:
        return None
    lagen = []
    for k in range(LAGEN):
        z = zmin + (zmax - zmin) * (0.1 + 0.8 * k / (LAGEN - 1)) + 0.0137
        ws = g._schnitt(lok, z)
        if len(ws) != 1:          # Schnitt durch einen Ausschnitt (zerfallen) oder ein Hohlprofil
            continue
        st = g._strecken(ws[0][1])
        xs, ys = [s[0] for s in st] + [s[2] for s in st], [s[1] for s in st] + [s[3] for s in st]
        lagen.append((st, (min(xs), min(ys), max(xs), max(ys))))
    if not lagen:
        return None
    # Hüllrechteck: das größte; Lagen mit kleinerem Querschnitt (Seitenwand dort ausgeschnitten, wie Patricks Beispiel
    # mit Laschen) zählen nicht, solange sie darin liegen; ein größerer oder versetzter Querschnitt: kein gerades Rohr
    huelle = max((h for _, h in lagen), key=lambda h: (h[2] - h[0]) * (h[3] - h[1]))
    offen_je_lage = []
    for st, h in lagen:
        if h[0] < huelle[0] - TOL_HUELLE or h[1] < huelle[1] - TOL_HUELLE or h[2] > huelle[2] + TOL_HUELLE or \
                h[3] > huelle[3] + TOL_HUELLE:
            return None
        if max(abs(p - q) for p, q in zip(h, huelle)) > TOL_HUELLE:
            continue
        offen = {}
        for seite in ("links", "rechts", "unten", "oben"):
            lu, a, b = _luecken(st, seite, *h, d)
            o = _offen(lu, a, b, d)
            if o:
                offen[seite] = o
        offen_je_lage.append(offen)
    if len(offen_je_lage) < 3 or huelle is None:
        return None
    x0, y0, x1, y1 = huelle
    if min(x1 - x0, y1 - y0) < 3 * d:
        return None                 # flaches Teil, kein Rohr
    # über die ganze Länge offen: an jeder Lage; genau eine solche Seite (sonst L-Profil o. ä.)
    immer = [s for s in ("links", "rechts", "unten", "oben") if all(s in o for o in offen_je_lage)]
    if len(immer) != 1:
        return None
    seite = immer[0]
    # Lücken der Seite: Vereinigung über die Lagen (Laschen, die nur an einer Lage fehlen, sind Ausschnitte; die
    # Lücke selbst ist an allen Lagen gleich)
    luecken = []
    for u0, u1 in sorted(x for o in offen_je_lage for x in o[seite]):
        if luecken and u0 <= luecken[-1][1] + SCHRITT:
            luecken[-1] = (luecken[-1][0], max(luecken[-1][1], u1))
        else:
            luecken.append((u0, u1))
    return dict(ax3=ax3, lok=lok, seite=seite, luecken=luecken, huelle=huelle, z=(zmin, zmax))


def _z_grenzen(lok, x, y):
    """Material entlang der Linie (x, y) parallel zur Achse: (kleinstes z, größtes z) oder None."""
    s = IntCurvesFace_ShapeIntersector()
    s.Load(lok, 1e-6)
    s.Perform(gp_Lin(gp_Pnt(x, y, -1e6), gp_Dir(0, 0, 1)), -1e7, 1e7)
    if not s.IsDone() or s.NbPnt() < 2:
        return None
    zs = [s.Pnt(i).Z() for i in range(1, s.NbPnt() + 1)]
    return min(zs), max(zs)


def _profil_z(lok, uv_zu_xyz, us, v):
    """Enden (z Ende A, z Ende B) des Materials entlang Linien parallel zur Achse an den Stellen u (bei v); Lücken
    (Bohrung, Rundung) linear aus den Nachbarn ergänzt. None, wenn keine Stelle Material hat."""
    werte = []
    for u in us:
        x, y, _ = uv_zu_xyz(u, v, 0.0)
        werte.append(_z_grenzen(lok, x, y))
    da = [i for i, w in enumerate(werte) if w is not None]
    if not da:
        return None
    out = []
    for i, w in enumerate(werte):
        if w is None:
            li = max((k for k in da if k < i), default=None)
            re = min((k for k in da if k > i), default=None)
            if li is None or re is None:      # am Rand: aus den zwei nächsten Stellen verlängert
                k1, k2 = (da[-2:] if re is None else da[:2]) if len(da) > 1 else (da[0], da[0])
                s = 0.0 if k1 == k2 else (us[i] - us[k1]) / (us[k2] - us[k1])
                w = tuple(werte[k1][k] + (werte[k2][k] - werte[k1][k]) * s for k in range(2))
            else:
                s = (i - li) / (re - li)
                w = tuple(werte[li][k] * (1 - s) + werte[re][k] * s for k in range(2))
        out.append(w)
    return out


def _seite_z(lok, uv_zu_xyz, u, v, mitte):
    """Enden (z A, z B) der Seitenwand bei u in der Höhe v. Liegt dort kein Material (Rundung an der Ecke), aus den
    zwei nächsten Stellen Richtung mitte linear verlängert. None, wenn nicht messbar."""
    schritt = math.copysign(0.5, mitte - v)
    treffer = []
    w = v
    while (mitte - w) * schritt > 0 and len(treffer) < 2:
        zg = _profil_z(lok, uv_zu_xyz, [u], w)
        if zg:
            if w == v:
                return zg[0]
            treffer.append((w, zg[0]))
            w += 4 * schritt          # zweite Stelle mit Abstand (Steigung)
            continue
        w += schritt
    if len(treffer) < 2:
        return treffer[0][1] if treffer else None
    (wa, za), (wb, zb) = treffer
    return tuple(za[k] + (zb[k] - za[k]) * (v - wa) / (wb - wa) for k in range(2))


def _knicke(pts):
    """Polygonzug [(u, z)] aus gleichmäßigen Stellen: liegt ein Knick (Schnitt nur über einen Teil der Breite)
    zwischen zwei Stellen, wird der Schnittpunkt der beiden Nachbargeraden eingefügt (sonst eine kleine Fase)."""
    out = list(pts[:2])
    for i in range(2, len(pts) - 1):      # Knick zwischen pts[i-1] und pts[i]
        (ua, za), (ub, zb), (uc, zc), (ud, zd) = pts[i - 2], pts[i - 1], pts[i], pts[i + 1]
        m1, m2 = (zb - za) / (ub - ua), (zd - zc) / (ud - uc)
        mitte = (zc - zb) / (uc - ub)
        if abs(m1 - m2) > 1e-3 and abs(mitte - m1) > 1e-3 and abs(mitte - m2) > 1e-3:
            u = (zc - zb + m1 * ub - m2 * uc) / (m1 - m2)
            if ub < u < uc:
                out.append((u, zb + m1 * (u - ub)))
        out.append(pts[i])
    return out + [pts[-1]] if len(pts) > 3 else list(pts)


def wand(e, d, ueberlapp=True, fenster=0.0):
    """Ergänzte Wand je Lücke als Körper im lokalen System: (Körper, Lückenbereiche, quer, Schichten = je Körper die
    Endlinien (Ende A, Ende B) außen und innen); ueberlapp: die Wand reicht um die Blechdicke in die Ränder (zum
    Verschmelzen), sonst genau die Lücke (3D-Ansicht).
    Enden (Frage 2 a): Verlauf der gegenüberliegenden Wand (z je u), quer dazu die Steigung der Seitenwände (z je v,
    zwischen linker und rechter Seitenwand gemittelt). Ein gerades Ende bleibt gerade, eine Gehrung oder ein Schnitt
    nur über einen Teil der Breite wird übernommen.
    fenster > 0: statt der Wand das Fenster zwischen den Stegen (je fenster mm an Ende A und B), genau über der Lücke
    und nach außen und innen etwas über die Wand hinaus (zum Ausschneiden aus dem geschlossenen Rohr)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    x0, y0, x1, y1 = e["huelle"]
    seite, lok = e["seite"], e["lok"]
    quer = seite in ("unten", "oben")
    if quer:
        v_aussen, v_gegen = (y0, y1) if seite == "unten" else (y1, y0)
        a, b = x0, x1
        uv_zu_xyz = lambda u, v, z: (u, v, z)       # noqa: E731
    else:
        v_aussen, v_gegen = (x0, x1) if seite == "links" else (x1, x0)
        a, b = y0, y1
        uv_zu_xyz = lambda u, v, z: (v, u, z)       # noqa: E731
    innen = 1.0 if v_gegen > v_aussen else -1.0
    v_innen = v_aussen + innen * d
    v_lo, v_hi = min(v_aussen, v_innen), max(v_aussen, v_innen)
    v_gm = v_gegen - innen * d / 2                   # Mitte der gegenüberliegenden Wand
    # Versatz der Enden quer zur Wand: Seitenwand links/rechts in Höhe der neuen Wand gegen die Höhe der
    # gegenüberliegenden Wand (gerades Ende: 0, Gehrung quer: Steigung, Schnitt nur über einen Teil: der Knick)
    mitte = (v_aussen + v_gegen) / 2
    versatz = {}
    for u_s in (a + d / 2, b - d / 2):
        z_g = _seite_z(lok, uv_zu_xyz, u_s, v_gm, mitte)
        for v in (v_lo, v_hi):
            z_v = _seite_z(lok, uv_zu_xyz, u_s, min(max(v, v_lo + 0.05), v_hi - 0.05), mitte)
            versatz[u_s, v] = (0.0, 0.0) if z_g is None or z_v is None else (z_v[0] - z_g[0], z_v[1] - z_g[1])
    teile, felder, schichten = [], [], []
    for u0, u1 in e["luecken"]:
        w0, w1 = (max(a, u0 - d), min(b, u1 + d)) if ueberlapp and not fenster else (u0, u1)   # überlappt: verschmolzen
        n = max(8, min(240, int((w1 - w0) / 0.5)))
        us = [w0 + (w1 - w0) * k / n for k in range(n + 1)]
        gegen = _profil_z(lok, uv_zu_xyz, us, v_gm)
        if gegen is None:
            return None
        enden = [_knicke([(u, z[k]) for u, z in zip(us, gegen)]) for k in (0, 1)]
        drahte, schicht = [], []
        for v in (v_lo, v_hi):
            va, vb = versatz[a + d / 2, v], versatz[b - d / 2, v]
            vf = v if not fenster else v - innen * 1.0 if v == v_aussen else v + innen * 0.5   # Fenster: über die Wand
            unten = [uv_zu_xyz(u, vf, z + fenster + va[0] * (1 - (u - a) / (b - a)) + vb[0] * (u - a) / (b - a))
                     for u, z in enden[0]]
            oben = [uv_zu_xyz(u, vf, z - fenster + va[1] * (1 - (u - a) / (b - a)) + vb[1] * (u - a) / (b - a))
                    for u, z in enden[1]]
            schicht.append((unten, oben))
            poly = BRepBuilderAPI_MakePolygon()
            for q in unten + oben[::-1]:
                poly.Add(gp_Pnt(*q))
            poly.Close()
            drahte.append(poly.Wire())
        ts = BRepOffsetAPI_ThruSections(True, True)
        for w in drahte:
            ts.AddWire(w)
        ts.Build()
        if not ts.IsDone():
            return None
        teile.append(ts.Shape())
        felder.append((u0, u1))
        schichten.append(schicht)
    return teile, felder, quer, schichten


def _vereinen(solid, teile, ax3):
    """Körper ∪ ergänzte Wände (in Dateilage); None, wenn nicht genau ein Körper entsteht."""
    tr = gp_Trsf()
    tr.SetTransformation(ax3)
    zurueck = tr.Inverted()
    form = solid
    for k in teile:
        f = BRepAlgoAPI_Fuse(form, BRepBuilderAPI_Transform(k, zurueck, True).Shape())
        f.SetFuzzyValue(g.FUZZY)
        f.Build()
        if not f.IsDone():
            return None
        form = f.Shape()
    koerper = g._liste(form, TopAbs_SOLID)
    if len(koerper) != 1:
        return None
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    u = ShapeUpgrade_UnifySameDomain(koerper[0], True, True, True)
    u.Build()
    return u.Shape()


def _ausschneiden(form, teile, ax3):
    """Fenster (Körper im lokalen System) aus dem geschlossenen Rohr (Dateilage) schneiden; None bei Fehler. Ohne
    Vereinheitlichen der Flächen: die Fensterränder liegen in der Ebene der Seitenwände innen und sollen eigene
    Schnittflächen bleiben."""
    tr = gp_Trsf()
    tr.SetTransformation(ax3)
    zurueck = tr.Inverted()
    for k in teile:
        c = BRepAlgoAPI_Cut(form, BRepBuilderAPI_Transform(k, zurueck, True).Shape())
        c.SetFuzzyValue(g.FUZZY)
        c.Build()
        if not c.IsDone():
            return None
        form = c.Shape()
    return form if len(g._liste(form, TopAbs_SOLID)) == 1 else None


def _gitter(schicht, quer, laenge):
    """Dreiecke der Wand aus ihren Endlinien: Raster über u (Stützstellen beider Enden) und z (etwa alle 20 mm),
    damit die Dreiecke klein und gleichmäßig sind (die 3D-Ansicht ohne OpenGL sortiert nach Tiefe). Ergebnis:
    Punkte [(x, y, z)] und Dreiecke [(i, j, k)], nach außen gedreht."""
    k_u = 0 if quer else 1

    def an(linie, u):
        for p, q in zip(linie, linie[1:]):
            if p[k_u] - 1e-9 <= u <= q[k_u] + 1e-9:
                s = 0.0 if q[k_u] == p[k_u] else (u - p[k_u]) / (q[k_u] - p[k_u])
                return [p[m] + (q[m] - p[m]) * s for m in range(3)]
        return list(linie[0] if u < linie[0][k_u] else linie[-1])
    us = sorted({round(p[k_u], 6) for unten, oben in schicht for p in unten + oben})
    n = max(1, int(laenge / 20.0))
    punkte, gitter = [], []
    for unten, oben in schicht:          # außen, innen: Gitter je Schicht
        g_ = []
        for u in us:
            a, b = an(unten, u), an(oben, u)
            g_.append([len(punkte) + j for j in range(n + 1)])
            punkte += [[a[m] + (b[m] - a[m]) * j / n for m in range(3)] for j in range(n + 1)]
        gitter.append(g_)
    dreiecke = []

    def viereck(a, b, c, d_):
        dreiecke.extend([(a, b, c), (a, c, d_)])
    for g_ in gitter:                                       # Wandflächen
        for i in range(len(us) - 1):
            for j in range(n):
                viereck(g_[i][j], g_[i + 1][j], g_[i + 1][j + 1], g_[i][j + 1])
    g0, g1 = gitter
    for i in range(len(us) - 1):                            # Enden A und B
        viereck(g0[i][0], g0[i + 1][0], g1[i + 1][0], g1[i][0])
        viereck(g0[i][n], g0[i + 1][n], g1[i + 1][n], g1[i][n])
    # die Ränder an den Lückenkanten fehlen mit Absicht: dort liegt die Wand des Teils (gleiche Ebene)
    mitte = [sum(p[m] for p in punkte) / len(punkte) for m in range(3)]
    out = []
    for a, b, c in dreiecke:                                # nach außen drehen (Wand ist flach und konvex)
        pa, pb, pc = punkte[a], punkte[b], punkte[c]
        u_ = [pb[m] - pa[m] for m in range(3)]
        v_ = [pc[m] - pa[m] for m in range(3)]
        nv = (u_[1] * v_[2] - u_[2] * v_[1], u_[2] * v_[0] - u_[0] * v_[2], u_[0] * v_[1] - u_[1] * v_[0])
        if sum(abs(x) for x in nv) < 1e-12:
            continue
        sp = [(pa[m] + pb[m] + pc[m]) / 3 - mitte[m] for m in range(3)]
        out.append((a, b, c) if sum(nv[m] * sp[m] for m in range(3)) >= 0 else (a, c, b))
    return punkte, out


def _verfeinern(netz, max_kante=25.0):
    """Lange Dreiecke des Netzes an der längsten Kante teilen, bis keine Kante länger als max_kante ist (gemeinsame
    Kantenmitten, das Netz bleibt geschlossen). Die 3D-Ansicht ohne OpenGL sortiert Dreiecke nach der Tiefe ihrer
    Mitte; lange Dreiecke der Seitenwände lägen sonst teils vor der ergänzten Wand."""
    p = netz["p"]
    mitten = {}

    def mitte(a, b):
        k = (min(a, b), max(a, b))
        if k not in mitten:
            mitten[k] = len(p) // 3
            p.extend(round((p[3 * a + m] + p[3 * b + m]) / 2, 2) for m in range(3))
        return mitten[k]

    def laenge2(a, b):
        return sum((p[3 * a + m] - p[3 * b + m]) ** 2 for m in range(3))
    grenze = max_kante * max_kante
    for art, idx in netz["t"].items():
        offen = [tuple(idx[j:j + 3]) for j in range(0, len(idx), 3)]
        fertig = []
        while offen:
            a, b, c = offen.pop()
            kanten = [(laenge2(a, b), 0), (laenge2(b, c), 1), (laenge2(c, a), 2)]
            l2, k = max(kanten)
            if l2 <= grenze or len(fertig) + len(offen) > 20000:
                fertig.append((a, b, c))
                continue
            x, y, z = ((a, b, c), (b, c, a), (c, a, b))[k]          # längste Kante x–y
            q = mitte(x, y)
            offen += [(x, q, z), (q, y, z)]
        netz["t"][art] = [i for tri in fertig for i in tri]


def _stege(schicht, steg):
    """Endlinien der Stege an Ende A und B aus den Endlinien der Wand (je Schicht außen/innen um steg nach innen)."""
    def verschoben(linie, dz):
        return [(p[0], p[1], p[2] + dz) for p in linie]
    return ([(unten, verschoben(unten, steg)) for unten, _ in schicht],
            [(verschoben(oben, -steg), oben) for _, oben in schicht])


def _netz_wand(t, e, d, steg=0.0):
    """Die ergänzte Wand (genau die Lücken; mit steg nur die Stege an den Enden) als Dreiecke der Art EO im Netz der
    offenen Messung (System wie das Netz: Ende A, Achse, X-Richtung der Messung)."""
    w = wand(e, d, ueberlapp=False)
    if not w or t.netz is None or not t.achse_global:
        return
    zu_datei, zu_netz = gp_Trsf(), gp_Trsf()
    zu_datei.SetTransformation(e["ax3"])
    zu_netz.SetTransformation(g._rohr_ax3(t))
    tr = zu_netz.Multiplied(zu_datei.Inverted())
    schichten = [(s_, e["z"][1] - e["z"][0]) for s_ in w[3]] if not steg else \
        [(s_, steg) for schicht in w[3] for s_ in _stege(schicht, steg)]
    for schicht, laenge in schichten:
        punkte, dreiecke = _gitter(schicht, w[2], laenge)
        p = []
        for x, y, z in punkte:
            q = gp_Pnt(x, y, z).Transformed(tr)
            p += [round(q.X(), 2), round(q.Y(), 2), round(q.Z(), 2)]
        g._netz_anhaengen(t.netz, dict(p=p, t={"EO": [i for tri in dreiecke for i in tri]}, l={}))
    _verfeinern(t.netz, max(10.0, (e["z"][1] - e["z"][0]) / 20))


def schliessen(solid, t, datei="", koerper=1, netz=False):
    """Offen gezeichnetes Rohr: t.geschlossen = Messung als Quadrat-/Rechteckrohr mit Stegen an den Enden und Fenster
    (Spalt bis SPALT_MAX: ganz geschlossen), im Netz von t die Stege bzw. die Wand als Art EO. False, wenn t nicht
    offen bzw. nicht schließbar ist."""
    if t is None or t.biegerohr or t.knick_schenkel or t.trennung or \
            (t.profilform if t.bauteiltyp != "Blech gekantet" else "Blech gekantet") not in KANDIDATEN:
        return False
    if t.bauteiltyp == "Blech gekantet" and ((t.blech or {}).get("abwicklung") or {}).get("mehrachsig"):
        return False
    d = _dicke(t)
    if d <= 0:
        return False
    e = erkennen(solid, d)
    if e is None:
        return False
    w = wand(e, d)
    if w is None:
        return False
    teile, felder, quer = w[:3]
    voll = _vereinen(solid, teile, e["ax3"])
    if voll is None:
        return False
    breite, laenge = sum(u1 - u0 for u0, u1 in felder), e["z"][1] - e["z"][0]
    steg = 0.0 if all(u1 - u0 <= SPALT_MAX + SPALT_TOL for u0, u1 in felder) or laenge < 4 * STEG else STEG
    zu = voll
    if steg:
        f = wand(e, d, fenster=steg)
        zu = _ausschneiden(voll, f[0], e["ax3"]) if f else None
        if zu is None:
            return False
    r = g._profil_messen(zu, datei, koerper, False, quer=voll if steg else None)
    if r.profilform not in ROHRE or abs(r.wandstaerke - d) > TOL_WAND:
        return False
    r.bauteiltyp = "Profil"
    ecke = e["huelle"][0] if quer else e["huelle"][1]
    r.offene_seite = dict(seite=e["seite"], luecken=[[round(u0 - ecke, 2), round(u1 - ecke, 2)] for u0, u1 in felder],
                          breite=round(breite, 2), laenge=round(laenge, 2), vorher=t.profilform, steg=steg or None)
    r.sicherheit["offene_seite"] = "stege" if steg else "ergänzt"
    if steg:
        r.hinweise.append(f"{HINWEIS}: aus dem Rohr gelasert, offene Seite ({breite:.1f} mm breit) bis auf je einen "
                          f"Steg {steg:g} mm an Ende A und B ausgeschnitten (vorher {t.profilform}) – Profil prüfen")
    else:
        r.hinweise.append(f"{HINWEIS}: Spalt {breite:.1f} mm über {laenge:.1f} mm Länge geschlossen (vorher "
                          f"{t.profilform}) – Profil prüfen")
    t.geschlossen = r
    if netz:
        try:
            _netz_wand(t, e, d, steg)
        except Exception:  # ohne Anzeige der Stege bzw. der Wand bleibt alles andere gültig
            pass
    return True
