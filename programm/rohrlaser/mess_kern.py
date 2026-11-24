"""Gemeinsamer Messkern für alle 3D-Fenster (Plan „CAD- und Messplan“ 19.11.2026, Phase M1). Ohne Qt, ohne Fenster.

Benutzt von messen3d (Messen mit Fangpunkten), auswahl3d (Direktmessung bei Auswahl) und damit von Viewer, Rohr-,
Blech-, Baugruppen- und Satz-Editor sowie STEP-Prüfdialog. Es gibt nur diesen einen Rechenweg für Abstände, Winkel,
Längen, Flächen und Volumen; die Kalkulation (Schneidweg, Laserzeit) rechnet weiter wie bisher. Messen ändert nie
etwas am Teil.

Messelemente (dict, Schlüssel typ):
- punkt     p
- strecke   a, b                    (gerade Kante)
- kreis     m, n, d, bogen, punkte  (Kreis oder Bogen; punkte = Linienzug, beim Bogen nur sein Stück)
- ebene     dreiecke, n, mitte      (ebene Fläche; dreiecke = [(a, b, c)])
- flaeche   dreiecke, mitte         (gewölbte Fläche, nur als Netz bekannt; mit katalog aus der STEP-Messung exakt)
- koerper   dreiecke, eben          (Körper; eben = alle Flächen eben -> Volumen exakt)

Genauigkeit: exakt heißt „aus der exakten Geometrie bzw. aus ebenen Netzflächen, die die Geometrie genau
abbilden“. Was nur auf dem Netz gewölbter Flächen gemessen ist, trägt exakt=False und wird mit „≈“ angezeigt.
Ungültige Geometrie (offener Körper) bekommt kein Volumen, sondern einen Hinweis.

Flächenkatalog (Messplan M3): Flächen von STEP-Teilen tragen katalog = {a: Ebene/Zylinder/Kegel/Kugel/Torus/Freiform,
f: Fläche, r, r2, w} aus der STEP-Messung (OpenCascade). Dann sind Flächeninhalt, Ø und Radien exakt; die Lage einer
Zylinderachse kommt aus den Netzpunkten, die genau auf der Fläche liegen (auf 0,01 mm gerundet)."""
import math

PARALLEL = 0.5              # Grad: darunter gelten Richtungen als parallel
PAARE_MAX = 300000          # Mindestabstand Netz–Netz höchstens über so viele Dreieckspaare (sonst Hinweis)
TOL = 1e-6
KOERPER_MAX = 40000      # Volumen/Schwerpunkt in der Direktmessung bis zu so vielen Dreiecken (≈ 0,5 s)
RAND_ANTEIL = 0.005      # offener Rand bis 0,5 % der Kantenlänge: Volumen noch genähert (Sehnen-Versatz)


def zahl(w, stellen=3):
    """Zahl mit fester Stellenzahl (Mess-Tafel: drei Nachkommastellen, „8,000“), ohne „-0,000“."""
    t = f"{w:.{stellen}f}"
    if t.lstrip("-").strip("0.") == "":
        t = t.lstrip("-")
    return t.replace(".", ",")


# ---------------------------------------------------------------- Vektoren
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mal(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def betrag(a):
    return math.sqrt(dot(a, a))


def norm(a):
    lg = betrag(a)
    return (a[0] / lg, a[1] / lg, a[2] / lg) if lg > 1e-12 else None


def winkel_zwischen(a, b, gerichtet=False):
    """Winkel [°] zwischen zwei Richtungen (ungerichtet: 0..90°, z. B. Kanten und Achsen)."""
    c = dot(a, b) / (math.sqrt(dot(a, a) * dot(b, b)) or 1.0)
    c = max(-1.0, min(1.0, c if gerichtet else abs(c)))
    return math.degrees(math.acos(c))


def drehwinkel(a, b, achse):
    """Gerichteter Winkel [°] von Richtung a nach b um die Achse (rechte Hand: Daumen in Achsrichtung, positiv gegen
    den Uhrzeigersinn beim Blick gegen die Achse), beide in die Ebene senkrecht zur Achse gelegt; −180 … 180."""
    n = norm(achse)
    if n is None:
        return 0.0
    pa = sub(a, mal(n, dot(a, n)))
    pb = sub(b, mal(n, dot(b, n)))
    return math.degrees(math.atan2(dot(kreuz(pa, pb), n), dot(pa, pb)))


def gehrung(n, achse=(0.0, 0.0, 1.0)):
    """Lage einer ebenen Schnittfläche zur Rohrachse (Bezugsebene = Ebene senkrecht zur Achse): dict(gehrung,
    um_hoch, um_quer). gehrung = Winkel der Fläche zur Bezugsebene (0° = gerader Schnitt), um_hoch/um_quer = Drehung
    um die Achse hoch (y) bzw. quer (x) mit Vorzeichen (Drehsinn, rechte Hand)."""
    nz = dot(n, achse)
    m = n if nz >= 0 else mal(n, -1.0)          # Normale zum Ende B hin: gleicher Drehsinn an beiden Enden
    return dict(gehrung=winkel_zwischen(m, achse, gerichtet=True),
                um_hoch=math.degrees(math.atan2(m[0], m[2])), um_quer=-math.degrees(math.atan2(m[1], m[2])))


def winkel_bei(a, b, c):
    """Winkel [°] am Punkt b zwischen den Strecken b→a und b→c (0 bei Nulllänge)."""
    u, w = sub(a, b), sub(c, b)
    lu, lw = betrag(u), betrag(w)
    if lu < 1e-12 or lw < 1e-12:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(u, w) / (lu * lw)))))


def dreieck_flaeche(a, b, c):
    return betrag(kreuz(sub(b, a), sub(c, a))) / 2


# ---------------------------------------------------------------- Punkte, Geraden, Strecken
def naechster_auf_strecke(p, a, b):
    ab = sub(b, a)
    lg = dot(ab, ab)
    t = 0.0 if lg < 1e-18 else max(0.0, min(1.0, dot(sub(p, a), ab) / lg))
    return add(a, mal(ab, t))


def abstand_strecke(p, a, b):
    """Abstand des Punkts p von der Strecke a–b."""
    return math.dist(p, naechster_auf_strecke(p, a, b))


def abstand_linie(p, o, r):
    """Abstand des Punkts p von der Geraden o + t r."""
    return betrag(kreuz(sub(p, o), r)) / (betrag(r) or 1.0)


def abstand_windschief(o1, r1, o2, r2):
    n = kreuz(r1, r2)
    lg = betrag(n)
    if lg < 1e-12:
        return abstand_linie(o2, o1, r1)
    return abs(dot(sub(o2, o1), n)) / lg


def schnittpunkt(o1, r1, o2, r2):
    """Nächste Punkte zweier Geraden (o + t·r): (Punkt auf 1, Punkt auf 2) oder None (parallel)."""
    w = sub(o1, o2)
    a, b, c, d, e = dot(r1, r1), dot(r1, r2), dot(r2, r2), dot(r1, w), dot(r2, w)
    nenner = a * c - b * b
    if abs(nenner) < 1e-12:
        return None
    s, t = (b * e - c * d) / nenner, (a * e - b * d) / nenner
    return add(o1, mal(r1, s)), add(o2, mal(r2, t))


def strecke_strecke(p1, q1, p2, q2):
    """Nächste Punkte zweier Strecken (Ericson 5.1.9): (Abstand, Punkt auf 1, Punkt auf 2)."""
    d1, d2, r = sub(q1, p1), sub(q2, p2), sub(p1, p2)
    a, e, f = dot(d1, d1), dot(d2, d2), dot(d2, r)
    if a <= 1e-18 and e <= 1e-18:
        return math.dist(p1, p2), p1, p2
    if a <= 1e-18:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = dot(d1, r)
        if e <= 1e-18:
            t, s = 0.0, max(0.0, min(1.0, -c / a))
        else:
            b = dot(d1, d2)
            nenner = a * e - b * b
            s = max(0.0, min(1.0, (b * f - c * e) / nenner)) if nenner > 1e-18 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, max(0.0, min(1.0, -c / a))
            elif t > 1.0:
                t, s = 1.0, max(0.0, min(1.0, (b - c) / a))
    c1, c2 = add(p1, mal(d1, s)), add(p2, mal(d2, t))
    return math.dist(c1, c2), c1, c2


def naechster_im_dreieck(p, a, b, c):
    """Nächster Punkt des Dreiecks a, b, c zu p (Ericson 5.1.5)."""
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a
    bp = sub(p, b)
    d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return add(a, mal(ab, d1 / (d1 - d3)))
    cp = sub(p, c)
    d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return add(a, mal(ac, d2 / (d2 - d6)))
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        return add(b, mal(sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6))))
    nenner = 1.0 / (va + vb + vc)
    return add(a, add(mal(ab, vb * nenner), mal(ac, vc * nenner)))


def strahl_dreieck(o, r, a, b, c):
    """Möller–Trumbore: Abstand t vom Ursprung o längs r bis zum Dreieck a, b, c oder None."""
    e1, e2 = sub(b, a), sub(c, a)
    h = kreuz(r, e2)
    det = dot(e1, h)
    if abs(det) < 1e-12:
        return None
    f = 1.0 / det
    s = sub(o, a)
    u = f * dot(s, h)
    if u < -1e-9 or u > 1 + 1e-9:
        return None
    q = kreuz(s, e1)
    v = f * dot(r, q)
    if v < -1e-9 or u + v > 1 + 1e-9:
        return None
    return f * dot(e2, q)


def _strecke_trifft_dreieck(p, q, tri):
    r = sub(q, p)
    lg = betrag(r)
    if lg < 1e-12:
        return None
    t = strahl_dreieck(p, mal(r, 1 / lg), *tri)
    if t is None or t < -1e-9 or t > lg + 1e-9:
        return None
    return add(p, mal(r, t / lg))


def dreieck_dreieck(t1, t2):
    """Kleinster Abstand zweier Dreiecke: (Abstand, Punkt auf 1, Punkt auf 2); 0, wenn sie sich schneiden."""
    for (u, v) in ((t1[0], t1[1]), (t1[1], t1[2]), (t1[2], t1[0])):
        s = _strecke_trifft_dreieck(u, v, t2)
        if s is not None:
            return 0.0, s, s
    for (u, v) in ((t2[0], t2[1]), (t2[1], t2[2]), (t2[2], t2[0])):
        s = _strecke_trifft_dreieck(u, v, t1)
        if s is not None:
            return 0.0, s, s
    beste = None
    for p in t1:
        q = naechster_im_dreieck(p, *t2)
        d = math.dist(p, q)
        if beste is None or d < beste[0]:
            beste = (d, p, q)
    for q in t2:
        p = naechster_im_dreieck(q, *t1)
        d = math.dist(p, q)
        if d < beste[0]:
            beste = (d, p, q)
    for (a1, b1) in ((t1[0], t1[1]), (t1[1], t1[2]), (t1[2], t1[0])):
        for (a2, b2) in ((t2[0], t2[1]), (t2[1], t2[2]), (t2[2], t2[0])):
            d, p, q = strecke_strecke(a1, b1, a2, b2)
            if d < beste[0]:
                beste = (d, p, q)
    return beste


# ---------------------------------------------------------------- Kanten einer Dreiecksmenge
def _randlaenge(dreiecke):
    """Länge des Rands einer Dreiecksmenge: gerichtete Seiten, die sich auf derselben Geraden nicht gegenseitig
    aufheben (verträgt Netze mit T-Stößen, bei denen eine lange Seite an zwei kurze grenzt). Die Dreiecke müssen
    gleich orientiert sein (aussen_orientiert). Ergebnis [mm]; 0 = geschlossen."""
    gruppen = {}
    for tri in dreiecke:
        for u, v in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            r = norm(sub(v, u))
            if r is None:
                continue
            k = next(i for i in range(3) if abs(r[i]) > 1e-9)
            vz = 1
            if r[k] < 0:
                r, vz = (-r[0], -r[1], -r[2]), -1
            fuss = sub(u, mal(r, dot(u, r)))
            key = (round(r[0], 4), round(r[1], 4), round(r[2], 4), round(fuss[0], 3), round(fuss[1], 3),
                   round(fuss[2], 3))
            t0, t1 = sorted((dot(u, r), dot(v, r)))
            gruppen.setdefault(key, []).append((t0, t1, vz))
    summe = 0.0
    for liste in gruppen.values():
        ereignisse = []
        for t0, t1, vz in liste:
            ereignisse += [(t0, vz), (t1, -vz)]
        ereignisse.sort()
        stand, alt = 0, None
        for t, d in ereignisse:
            if alt is not None and stand != 0:
                summe += t - alt
            stand += d
            alt = t
    return summe


def aussen_orientiert(dreiecke, normalen=None):
    """Dreiecke so drehen, dass ihre Umlaufrichtung zur gespeicherten Normale passt (Netze sind nicht immer
    einheitlich orientiert)."""
    if normalen is None:
        return list(dreiecke)
    out = []
    for (a, b, c), n in zip(dreiecke, normalen):
        out.append((a, c, b) if dot(kreuz(sub(b, a), sub(c, a)), n) < 0 else (a, b, c))
    return out


# ---------------------------------------------------------------- Werte eines Elements
def bogenwinkel(m, n, punkte):
    """Überstrichener Winkel [°] eines Bogens (Linienzug punkte um die Mitte m, Achse n)."""
    nn = norm(n) or (0.0, 0.0, 1.0)
    summe = 0.0
    for p, q in zip(punkte, punkte[1:]):
        u, v = sub(p, m), sub(q, m)
        summe += math.atan2(dot(kreuz(u, v), nn), dot(u, v))
    return abs(math.degrees(summe))


def huelle(punkte):
    lo = tuple(min(q[i] for q in punkte) for i in range(3))
    hi = tuple(max(q[i] for q in punkte) for i in range(3))
    return lo, hi


def werte(me):
    """Messwerte eines Elements als dict (Zahlen in mm, mm², mm³, °)."""
    typ = me["typ"]
    if typ == "punkt":
        return dict(typ=typ, p=tuple(me["p"]), exakt=True)
    if typ == "strecke":
        a, b = tuple(me["a"]), tuple(me["b"])
        return dict(typ=typ, laenge=math.dist(a, b), a=a, b=b, r=norm(sub(b, a)) or (0.0, 0.0, 1.0),
                    mitte=mal(add(a, b), 0.5), exakt=True)
    if typ == "kreis":
        d = float(me["d"])
        w = dict(typ=typ, d=d, r=d / 2, m=tuple(me["m"]), n=tuple(me["n"]), bogen=bool(me.get("bogen")),
                 exakt=True)
        if w["bogen"] and me.get("punkte"):
            w["winkel"] = bogenwinkel(w["m"], w["n"], me["punkte"])
            w["laenge"] = math.radians(w["winkel"]) * d / 2
        else:
            w["laenge"] = math.pi * d
        return w
    tris = me.get("dreiecke") or []
    pk = [q for t in tris for q in t]
    inhalt = sum(dreieck_flaeche(*t) for t in tris)
    w = dict(typ=typ, flaeche=inhalt, exakt=typ == "ebene" or (typ == "koerper" and bool(me.get("eben"))))
    if pk:
        w["huelle"] = huelle(pk)
    if typ in ("ebene", "flaeche"):
        normalen = me.get("normalen") or ([me["n"]] * len(tris) if typ == "ebene" else None)
        w["umfang"] = _randlaenge(aussen_orientiert(tris, normalen))
        w["exakt_umfang"] = w["exakt"]
        w["mitte"] = tuple(me.get("mitte") or (0.0, 0.0, 0.0))
        if typ == "ebene":
            w["n"] = tuple(me["n"])
        k = me.get("katalog")
        if k:
            w["katalog"] = dict(k)
            if isinstance(k.get("f"), (int, float)) and k["f"] > 0:
                w["flaeche"], w["exakt"] = float(k["f"]), True
            z = zylinder(me)
            if z:
                w["zylinder"] = z
        return w
    # Körper: Volumen und Schwerpunkt nur bei geschlossenem Netz
    if len(tris) > KOERPER_MAX:
        w["zu_fein"] = len(tris)
        return w
    tris = aussen_orientiert(tris, me.get("normalen"))
    rand = _randlaenge(tris)
    kanten = sum(math.dist(u, v) for t in tris for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))) / 2
    w["geschlossen"] = rand < 1e-3
    w["rand"] = rand
    # Fast geschlossen: nur Sehnen gleicher Kreise passen nicht genau aufeinander (Netz einer Bohrung in Wand und
    # Mantel verschieden fein). Dann Volumen genähert, sonst keins.
    w["fast_geschlossen"] = not w["geschlossen"] and kanten > 0 and rand <= RAND_ANTEIL * kanten
    if w["geschlossen"] or w["fast_geschlossen"]:
        lo, hi = w["huelle"]
        o = mal(add(lo, hi), 0.5)               # Bezug Mitte: kleinster Fehler an offenen Stellen
        v, s = 0.0, [0.0, 0.0, 0.0]
        for a, b, c in tris:
            a, b, c = sub(a, o), sub(b, o), sub(c, o)
            dv = dot(a, kreuz(b, c)) / 6
            v += dv
            for i in range(3):
                s[i] += dv * (a[i] + b[i] + c[i]) / 4
        if v < 0:                      # nach innen orientiert: umdrehen
            v, s = -v, [-c for c in s]
        w["volumen"] = v
        if v > 1e-12:
            w["schwerpunkt"] = tuple(s[i] / v + o[i] for i in range(3))
        if w["fast_geschlossen"]:
            w["exakt"] = False
    return w


def _eigen3(m):
    """Eigenwerte/-vektoren einer symmetrischen 3×3-Matrix (aufsteigend): [(Wert, Vektor)]; Jacobi-Verfahren
    (ohne numpy, das im Windows-Paket fehlt)."""
    a = [[float(m[i][j]) for j in range(3)] for i in range(3)]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(50):
        p, q = max(((0, 1), (0, 2), (1, 2)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) < 1e-14 * (abs(a[0][0]) + abs(a[1][1]) + abs(a[2][2]) + 1e-300):
            break
        th = 0.5 * math.atan2(2 * a[p][q], a[q][q] - a[p][p])
        c, s_ = math.cos(th), math.sin(th)
        for k in range(3):          # Spalten p, q
            akp, akq = a[k][p], a[k][q]
            a[k][p], a[k][q] = c * akp - s_ * akq, s_ * akp + c * akq
        for k in range(3):          # Zeilen p, q
            apk, aqk = a[p][k], a[q][k]
            a[p][k], a[q][k] = c * apk - s_ * aqk, s_ * apk + c * aqk
        for k in range(3):
            vkp, vkq = v[k][p], v[k][q]
            v[k][p], v[k][q] = c * vkp - s_ * vkq, s_ * vkp + c * vkq
    return sorted(((a[i][i], tuple(v[k][i] for k in range(3))) for i in range(3)), key=lambda e: e[0])


def _loesen3(A, b):
    """A x = b für 3×3 (Cramer); ValueError bei singulärer Matrix."""
    def det(M):
        return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
                + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))
    d = det(A)
    if abs(d) < 1e-12 * max(1.0, max(abs(x) for z in A for x in z)) ** 3:
        raise ValueError("singulär")
    out = []
    for j in range(3):
        M = [[b[i] if k == j else A[i][k] for k in range(3)] for i in range(3)]
        out.append(det(M) / d)
    return out


def zylinder_einpassen(tris):
    """Zylinder durch die Punkte einer gewölbten Netzfläche: Achse = Richtung, zu der alle Normalen senkrecht stehen
    (kleinster Eigenwert von Σ n nᵀ), Kreis nach Kåsa in der Ebene senkrecht dazu. dict(r, o, achse, laenge, bogen,
    abw) oder None (kein Zylinder: Punkte weichen mehr als 0,05 mm bzw. 1 % ab)."""
    pk = [q for tr in tris for q in tr]
    if len(pk) < 3:
        return None
    m = [sum(q[i] for q in pk) / len(pk) for i in range(3)]
    nn = [kreuz(sub(b, a), sub(c, a)) for a, b, c in tris]
    mm = [[sum(k[i] * k[j] / (betrag(k) or 1.0) for k in nn) for j in range(3)] for i in range(3)]
    (_, achse), (_, e1), (_, e2) = _eigen3(mm)
    xy = [(sum((q[i] - m[i]) * e1[i] for i in range(3)), sum((q[i] - m[i]) * e2[i] for i in range(3))) for q in pk]
    hoch = [sum((q[i] - m[i]) * achse[i] for i in range(3)) for q in pk]
    sxx = sum(x * x for x, _ in xy)
    syy = sum(y * y for _, y in xy)
    sxy = sum(x * y for x, y in xy)
    sx = sum(x for x, _ in xy)
    sy = sum(y for _, y in xy)
    rz = [-(x * x + y * y) for x, y in xy]
    try:
        A = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, len(xy)]]
        bb = [sum(r * x for r, (x, _) in zip(rz, xy)), sum(r * y for r, (_, y) in zip(rz, xy)), sum(rz)]
        D, E, F = _loesen3(A, bb)
    except ValueError:              # singulär: kein Kreis
        return None
    cx, cy = -D / 2, -E / 2
    r2 = cx * cx + cy * cy - F
    if r2 <= 0:
        return None
    r = math.sqrt(r2)
    abw = max(abs(math.hypot(x - cx, y - cy) - r) for x, y in xy)
    if abw > max(0.05, 0.01 * r):
        return None
    winkel = sorted({round(math.degrees(math.atan2(y - cy, x - cx)) % 360, 6) for x, y in xy})
    schritte = sorted((winkel[(i + 1) % len(winkel)] - winkel[i]) % 360 for i in range(len(winkel)))
    luecke = schritte[-1] if schritte else 360
    # ganz herum: die größte Lücke ist nur ein Netzschritt (Vieleck mit n Ecken: Lücke 360/n), kein offener Bogen
    typisch = schritte[len(schritte) // 2] if len(schritte) > 2 else 0.0
    offen = luecke > 1 and luecke > 2.5 * max(typisch, 1e-9) and len(winkel) > 2
    o = tuple(m[i] + cx * e1[i] + cy * e2[i] for i in range(3))
    return dict(r=r, o=o, achse=tuple(achse), laenge=max(hoch) - min(hoch), bogen=360 - luecke if offen else 360,
                abw=abw)


def zylinder(me):
    """Zylinderfläche mit Katalogeintrag (Art Zylinder, exakter Radius aus der STEP): dict(d, r, o, achse, innen,
    exakt) oder None. Achse und Lage aus den Netzpunkten (zylinder_einpassen; die Punkte liegen genau auf der Fläche),
    innen = Bohrung/Innenwand (Normalen zur Achse hin)."""
    k = me.get("katalog") or {}
    tris = me.get("dreiecke") or []
    if k.get("a") != "Zylinder" or not isinstance(k.get("r"), (int, float)) or not tris:
        return None
    z = zylinder_einpassen(tris)
    if z is None:
        return None
    o, r = z["o"], z["achse"]
    if me.get("mitte"):                      # Bezugspunkt der Achse auf Höhe der Flächenmitte
        o = add(o, mal(r, dot(sub(me["mitte"], o), r)))
    normalen = me.get("normalen") or [norm(kreuz(sub(b, a), sub(c, a))) for a, b, c in tris]
    stimmen = 0
    for (a, b, c), nn in zip(tris, normalen):
        if not nn:
            continue
        q = mal(add(add(a, b), c), 1 / 3)
        radial = sub(q, add(o, mal(r, dot(sub(q, o), r))))
        stimmen += 1 if dot(radial, nn) < 0 else -1
    rad = float(k["r"])
    return dict(d=2 * rad, r=rad, o=o, achse=r, innen=stimmen > 0, exakt=True)


# ---------------------------------------------------------------- Paare
def _richtung(me):
    if me["typ"] == "strecke":
        return norm(sub(me["b"], me["a"]))
    if me["typ"] == "kreis":
        return norm(me["n"])
    return None


def _ort(me):
    if me["typ"] == "punkt":
        return tuple(me["p"])
    if me["typ"] == "strecke":
        return mal(add(me["a"], me["b"]), 0.5)
    if me["typ"] == "kreis":
        return tuple(me["m"])
    return tuple(me.get("mitte") or (0.0, 0.0, 0.0))


def _dreiecke(me):
    """Element als Dreiecke, Strecken und Punkte (für den Mindestabstand)."""
    typ = me["typ"]
    if typ == "punkt":
        return [], [], [tuple(me["p"])]
    if typ == "strecke":
        return [], [(tuple(me["a"]), tuple(me["b"]))], []
    if typ == "kreis":
        pk = me.get("punkte") or ()
        return [], list(zip(pk, pk[1:])), []
    return list(me.get("dreiecke") or ()), [], []


def _bbox(pk):
    return (min(q[0] for q in pk), min(q[1] for q in pk), min(q[2] for q in pk),
            max(q[0] for q in pk), max(q[1] for q in pk), max(q[2] for q in pk))


def _luecke2(b1, b2):
    s = 0.0
    for i in range(3):
        g = max(b1[i] - b2[i + 3], b2[i] - b1[i + 3], 0.0)
        s += g * g
    return s


def mindestabstand(me1, me2):
    """Kleinster Abstand zweier Elemente: dict(wert, p1, p2, exakt) oder dict(wert=None, grund)."""
    t1, s1, p1 = _dreiecke(me1)
    t2, s2, p2 = _dreiecke(me2)
    teile1 = [("t", t) for t in t1] + [("s", s) for s in s1] + [("p", (p,)) for p in p1]
    teile2 = [("t", t) for t in t2] + [("s", s) for s in s2] + [("p", (p,)) for p in p2]
    if not teile1 or not teile2:
        return dict(wert=None, grund="nicht messbar")
    if len(teile1) * len(teile2) > PAARE_MAX:
        return dict(wert=None, grund=f"zu fein für die Direktmessung ({len(teile1)} × {len(teile2)} Netzteile)")
    boxen2 = [(_bbox(g), art, g) for art, g in teile2]
    beste = None
    for art1, g1 in teile1:
        b1 = _bbox(g1)
        for b2, art2, g2 in boxen2:
            if beste is not None and _luecke2(b1, b2) >= beste[0] * beste[0]:
                continue
            r = _paar_teil(art1, g1, art2, g2)
            if beste is None or r[0] < beste[0]:
                beste = r
                if beste[0] <= 0:
                    break
        if beste is not None and beste[0] <= 0:
            break
    exakt = all(me["typ"] in ("punkt", "strecke", "ebene") for me in (me1, me2)) or \
        (me1["typ"] == "koerper" and me2["typ"] == "koerper" and me1.get("eben") and me2.get("eben"))
    return dict(wert=beste[0], p1=beste[1], p2=beste[2], exakt=bool(exakt))


def _paar_teil(art1, g1, art2, g2):
    if art1 == "t" and art2 == "t":
        return dreieck_dreieck(g1, g2)
    if art1 == "t" or art2 == "t":
        tri, other, art, dreh = (g1, g2, art2, False) if art1 == "t" else (g2, g1, art1, True)
        if art == "p":
            q = naechster_im_dreieck(other[0], *tri)
            r = (math.dist(other[0], q), q, other[0])
        else:
            s = _strecke_trifft_dreieck(other[0], other[1], tri)
            if s is not None:
                r = (0.0, s, s)
            else:
                r = None
                for p in other:
                    q = naechster_im_dreieck(p, *tri)
                    d = math.dist(p, q)
                    if r is None or d < r[0]:
                        r = (d, q, p)
                for u, v in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                    d, q, p = strecke_strecke(u, v, other[0], other[1])
                    if d < r[0]:
                        r = (d, q, p)
        return (r[0], r[2], r[1]) if dreh else r
    if art1 == "s" and art2 == "s":
        return strecke_strecke(g1[0], g1[1], g2[0], g2[1])
    if art1 == "s":
        q = naechster_auf_strecke(g2[0], *g1)
        return math.dist(q, g2[0]), q, g2[0]
    if art2 == "s":
        q = naechster_auf_strecke(g1[0], *g2)
        return math.dist(q, g1[0]), g1[0], q
    return math.dist(g1[0], g2[0]), g1[0], g2[0]


def _zyl(me):
    """Zylinderachse einer Fläche mit Katalog (gemerkt am Element) oder None."""
    if me["typ"] != "flaeche" or not me.get("katalog"):
        return None
    if "_zyl" not in me:
        me["_zyl"] = zylinder(me)
    return me["_zyl"]


def _paar_zylinder(a, b, out):
    """Paare mit einer Zylinderfläche aus dem Flächenkatalog (Bohrung, Rohrmantel): über ihre Achse wie bei einem
    Kreis. Hauptwert oder None (keine Zylinderfläche dabei)."""
    za, zb = _zyl(a), _zyl(b)
    if za is None and zb is None:
        return None
    if za is not None and zb is None:            # Zylinder nach hinten (b), der andere vorn
        a, b, za, zb = b, a, zb, za
    o2, r2 = zb["o"], zb["achse"]
    ta = a["typ"]
    if za is not None:
        o1, r1 = za["o"], za["achse"]
        w = winkel_zwischen(r1, r2)
        w = min(w, 180 - w)
        if w < PARALLEL:
            abst = abstand_linie(o2, o1, r1)
            if abst <= abs(za["r"] - zb["r"]) + TOL:     # einer im anderen (Rohr außen/innen, Hülse)
                name = "Wandstärke (radial)" if abst < 1e-2 else "kleinste Wand (radial)"
                out.append((name, abs(za["r"] - zb["r"]) - abst, "mm", True))
                if abst >= 1e-2:
                    out.append(("größte Wand (radial)", abs(za["r"] - zb["r"]) + abst, "mm", True))
            else:
                out.append(("Steg (Mantel zu Mantel)", abst - za["r"] - zb["r"], "mm", True))
            return ("Abstand Achse–Achse (parallel)", abst, "mm", True)
        out.append(("kürzester Abstand der Achsen", abstand_windschief(o1, r1, o2, r2), "mm", True))
        return ("Winkel Achse–Achse", w, "°", True)
    if ta == "punkt":
        return ("Abstand Punkt–Zylinderachse", abstand_linie(tuple(a["p"]), o2, r2), "mm", True)
    if ta in ("strecke", "kreis"):
        ra = _richtung(a)
        o1 = tuple(a["a"]) if ta == "strecke" else tuple(a["m"])
        name = "Kante" if ta == "strecke" else "Achse"
        w = winkel_zwischen(ra, r2)
        w = min(w, 180 - w)
        if w < PARALLEL:
            abst = abstand_linie(o2, o1, ra)
            if ta == "kreis":
                out.append(("Steg (Rand zu Mantel)", abst - a["d"] / 2 - zb["r"], "mm", True))
            return (f"Abstand {name}–Zylinderachse (parallel)", abst, "mm", True)
        out.append(("kürzester Abstand der Geraden", abstand_windschief(o1, ra, o2, r2), "mm", True))
        return (f"Winkel {name}–Zylinderachse", w, "°", True)
    if ta == "ebene":
        w = 90 - winkel_zwischen(a["n"], r2)
        w = abs(w)
        if w < PARALLEL:
            abst = abs(dot(sub(o2, a["mitte"]), a["n"]))
            out.append(("Abstand Fläche–Mantel", abst - zb["r"], "mm", True))
            return ("Abstand Zylinderachse–Fläche", abst, "mm", True)
        return ("Winkel Zylinderachse–Fläche", w, "°", True)
    return None


def _winkelrichtung(me):
    """Richtung für den gerichteten Winkel: Kante bzw. Achse; bei Ebenen die Spur in der Bezugsebene (senkrecht zur
    Normalen und zur Achse z)."""
    if me["typ"] in ("strecke", "kreis"):
        return _richtung(me)
    if me["typ"] == "ebene":
        return norm(me["n"])
    z = _zyl(me) if me["typ"] == "flaeche" else None
    return z["achse"] if z else None


def paar(me1, me2, achsname="z"):
    """Messung zweier Elemente: dict(haupt=(Name, Wert, Einheit, exakt), werte=[(Name, Wert, Einheit, exakt)],
    p1, p2). Hauptwert: bei parallelen Kanten, Ebenen oder Achsen der senkrechte Abstand, sonst der Winkel; zwischen
    Punkten bzw. Mitten der Abstand. Dazu immer der Mindestabstand (wenn messbar)."""
    a, b = (me1, me2) if _rang(me1) <= _rang(me2) else (me2, me1)
    ta, tb = a["typ"], b["typ"]
    oa, ob = _ort(a), _ort(b)
    out = []
    haupt = None
    ra, rb = _richtung(a), _richtung(b)
    if ta in ("punkt", "kreis") and tb in ("punkt", "kreis"):
        n1 = "Mitte" if ta == "kreis" else "Punkt"
        n2 = "Mitte" if tb == "kreis" else "Punkt"
        haupt = (f"Abstand {n1}–{n2}", math.dist(oa, ob), "mm", True)
        if ta == tb == "kreis" and winkel_zwischen(ra, rb) < PARALLEL:
            quer = abstand_linie(ob, oa, ra)
            out.append(("Abstand quer zur Achse", quer, "mm", True))
            steg = quer - a["d"] / 2 - b["d"] / 2
            if abs(dot(sub(ob, oa), ra)) < 1e-3:          # in einer Ebene: Steg zwischen den Rändern
                out.append(("Steg (Rand zu Rand)", steg, "mm", True))
        elif ta == tb == "kreis":
            out.append(("Winkel Achse–Achse", winkel_zwischen(ra, rb), "°", True))
    elif ta == "punkt" and tb == "strecke":
        haupt = ("Abstand Punkt–Kante (senkrecht)", abstand_linie(oa, b["a"], rb), "mm", True)
    elif ta == "punkt" and tb == "ebene":
        haupt = ("Abstand Punkt–Fläche (senkrecht)", abs(dot(sub(oa, b["mitte"]), b["n"])), "mm", True)
    elif ta in ("strecke", "kreis") and tb in ("strecke", "kreis"):
        w = winkel_zwischen(ra, rb)
        n1 = "Kante" if ta == "strecke" else "Achse"
        n2 = "Kante" if tb == "strecke" else "Achse"
        if w < PARALLEL:
            haupt = (f"Abstand {n1}–{n2} (parallel)", abstand_linie(ob if tb != "strecke" else b["a"], a["a"]
                                                                    if ta == "strecke" else oa, ra), "mm", True)
        else:
            haupt = (f"Winkel {n1}–{n2}", w, "°", True)
            o1 = a["a"] if ta == "strecke" else oa
            o2 = b["a"] if tb == "strecke" else ob
            out.append(("kürzester Abstand der Geraden", abstand_windschief(o1, ra, o2, rb), "mm", True))
    elif ta in ("strecke", "kreis") and tb == "ebene":
        w = 90 - winkel_zwischen(b["n"], ra)
        name = "Kante" if ta == "strecke" else "Achse"
        if w < PARALLEL:
            haupt = (f"Abstand {name}–Fläche", abs(dot(sub(oa if ta == "kreis" else a["a"], b["mitte"]), b["n"])),
                     "mm", True)
        else:
            haupt = (f"Winkel {name}–Fläche", w, "°", True)
    elif ta == "ebene" and tb == "ebene":
        w = winkel_zwischen(a["n"], b["n"])
        if w < PARALLEL:
            haupt = ("Abstand Fläche–Fläche (parallel)", abs(dot(sub(ob, oa), a["n"])), "mm", True)
        else:
            haupt = ("Winkel Fläche–Fläche", w, "°", True)
    if haupt is None:
        haupt = _paar_zylinder(a, b, out)
    if haupt is not None and haupt[2] == "°":    # Winkel: dazu gerichtet um die Achse z (Rohrachse), wenn beide quer
        da, db = _winkelrichtung(a), _winkelrichtung(b)
        if da is not None and db is not None and abs(da[2]) < 0.02 and abs(db[2]) < 0.02:
            if b["typ"] != "ebene" and dot(da, db) < 0:     # Kante/Achse ohne Richtung: den spitzen Winkel drehen
                db = mal(db, -1.0)
            out.append((f"Winkel gerichtet um {achsname}", drehwinkel(da, db, (0.0, 0.0, 1.0)), "°", True))
    m = mindestabstand(a, b)
    if m["wert"] is not None:
        out.append(("Mindestabstand", m["wert"], "mm", m["exakt"]))
    elif m["grund"] != "nicht messbar":
        out.append(("Mindestabstand", None, m["grund"], False))
    if haupt is None:                   # gewölbte Flächen, Körper: der Mindestabstand ist das Ergebnis
        if m["wert"] is not None:
            haupt = out.pop()
        else:
            haupt = ("Abstand der Mitten", math.dist(oa, ob), "mm", False)
    d = sub(ob, oa)
    return dict(haupt=haupt, werte=out, delta=(abs(d[0]), abs(d[1]), abs(d[2])),
                p1=m.get("p1"), p2=m.get("p2"))


def _rang(me):
    return ("punkt", "kreis", "strecke", "ebene", "flaeche", "koerper").index(me["typ"])


def summen(liste):
    """Mehrfachauswahl: dict(laenge, flaeche, kanten, flaechen) – Gesamtlänge aller Kanten (gerade, Kreise, Bögen),
    Gesamtfläche aller Flächen; exakt False, sobald etwas nur auf dem Netz gemessen ist."""
    laenge = flaeche = 0.0
    n_k = n_f = 0
    exakt_l = exakt_f = True
    for me in liste:
        w = werte(me)
        if me["typ"] in ("strecke", "kreis"):
            laenge += w["laenge"]
            n_k += 1
        elif me["typ"] in ("ebene", "flaeche"):
            flaeche += w["flaeche"]
            n_f += 1
            exakt_f &= w["exakt"]
    return dict(laenge=laenge, kanten=n_k, flaeche=flaeche, flaechen=n_f, exakt_laenge=exakt_l, exakt_flaeche=exakt_f)


# ---------------------------------------------------------------- Texte (Mess-Tafel, Eigenschaften)
def eintrag_text(e):
    """(Name, Wert, Einheit, exakt) -> „Abstand 12,000 mm“; nur auf dem Netz gemessen: „≈ Abstand 12,000 mm“."""
    name, wert, einheit, exakt = e
    if wert is None:
        return f"{name}: {einheit}"
    stellen = 2 if einheit == "°" else 3
    return f"{'' if exakt else '≈ '}{name} {zahl(wert, stellen)}{'' if einheit == '°' else ' '}{einheit}"


def achsen_winkel(r, rohr=True):
    """Winkel einer Kante zu den Achsen: am Rohr zur Rohrachse (längs = z), sonst zu x, y und z."""
    if rohr:
        return [("Winkel zur Rohrachse", winkel_zwischen(r, (0.0, 0.0, 1.0)), "°", True)]
    return [(f"Winkel zu {n}", winkel_zwischen(r, a), "°", True)
            for n, a in (("x", (1.0, 0.0, 0.0)), ("y", (0.0, 1.0, 0.0)), ("z", (0.0, 0.0, 1.0)))]


def zeilen_element(me, lage=None, rohr=True):
    """Zusätzliche Messzeilen der Direktmessung zu einem Element (die Grundwerte zeigt auswahl3d schon)."""
    w = werte(me)
    typ = w["typ"]
    zeilen = []
    if typ == "strecke":
        zeilen += [eintrag_text(e) for e in achsen_winkel(w["r"], rohr)]
    elif typ == "kreis":
        if w["bogen"] and "winkel" in w:
            zeilen.append(f"Bogen R {zahl(w['r'])} mm · Winkel {zahl(w['winkel'], 2)}° · Bogenlänge "
                          f"{zahl(w['laenge'])} mm")
        else:
            zeilen.append(f"Ø {zahl(w['d'])} mm · R {zahl(w['r'])} mm · Umfang {zahl(w['laenge'])} mm")
    elif typ in ("ebene", "flaeche"):
        if typ == "ebene" and rohr:
            g = gehrung(w["n"])
            if g["gehrung"] < 0.05:
                zeilen.append("Gerader Schnitt: Fläche senkrecht zur Rohrachse (Gehrung 0°)")
            elif g["gehrung"] > 89.95:
                zeilen.append("Fläche längs zur Rohrachse")
            else:
                zeilen.append(eintrag_text(("Gehrung zur Bezugsebene (senkrecht zur Rohrachse)", g["gehrung"], "°",
                                            True)))
                teile = [f"um {nm} {'+' if v > 0 else '−'}{zahl(abs(v), 2)}°"
                         for nm, v in (("hoch", g["um_hoch"]), ("quer", g["um_quer"])) if abs(v) >= 0.005]
                if teile:
                    zeilen.append("Drehsinn: " + " · ".join(teile) + " (rechte Hand, zum Ende B)")
        zeilen += katalog_zeilen(w, lage)
        zeilen.append(eintrag_text(("Flächeninhalt", w["flaeche"], "mm²", w["exakt"])))
        zeilen.append(eintrag_text(("Umfang (alle Ränder)", w["umfang"], "mm", w["exakt_umfang"])))
    elif typ == "koerper":
        if w.get("zu_fein"):
            zeilen.append(f"Volumen: Körper zu fein für die Direktmessung ({w['zu_fein']} Dreiecke)")
        elif "volumen" not in w:
            zeilen.append(f"Kein Volumen: Körper ist offen (Rand {zahl(w.get('rand', 0), 1)} mm), Netz unvollständig")
        else:
            if w.get("fast_geschlossen"):
                zeilen.append(f"Netz an {zahl(w['rand'], 1)} mm Rand nicht ganz geschlossen: Werte genähert")
            zeilen.append(eintrag_text(("Volumen", w["volumen"] / 1000, "cm³", w["exakt"])))
            if lage is not None and w.get("schwerpunkt"):
                zeilen.append(f"{'' if w['exakt'] else '≈ '}Schwerpunkt (Volumen): {lage(w['schwerpunkt'])}")
        if not w["exakt"] and not w.get("zu_fein"):
            zeilen.append("≈ gewölbte Flächen sind im Netz Vielecke: Werte genähert")
    return zeilen


def katalog_zeilen(w, lage=None):
    """Zeilen aus dem Flächenkatalog der STEP-Messung (exakt): Art der Fläche und ihre Maße."""
    k = w.get("katalog")
    if not k:
        return []
    art = k.get("a") or "Freiform"
    z = [f"STEP-Fläche: {art} (Werte exakt aus der STEP)" if art != "Freiform" else
         "STEP-Fläche: Freiform (Fläche exakt, Form nur am Netz)"]
    r = k.get("r")
    if art == "Zylinder" and r:
        zy = w.get("zylinder")
        was = "" if zy is None else " · innen (Bohrung/Innenwand)" if zy["innen"] else " · außen (Mantel)"
        z.append(f"Ø {zahl(2 * r)} mm · R {zahl(r)} mm{was}")
        if zy is not None and lage is not None:
            z.append(f"Achse durch {lage(zy['o'])}")
    elif art == "Kugel" and r:
        z.append(f"Kugel Ø {zahl(2 * r)} mm · R {zahl(r)} mm")
    elif art == "Kegel" and r is not None:
        z.append(f"Kegel: R {zahl(r)} mm am Bezugskreis · halber Öffnungswinkel {zahl(k.get('w') or 0, 2)}° "
                 f"(Senkung {zahl(2 * (k.get('w') or 0), 2)}°)")
    elif art == "Torus" and r:
        z.append(f"Torus: Biegeradius (Mitte) {zahl(r)} mm · Rohr-Ø {zahl(2 * (k.get('r2') or 0))} mm")
    return z


def zeilen_paar(me1, me2, namen=("quer", "hoch", "längs")):
    """Messzeilen zweier gewählter Elemente: Hauptwert, Δ je Achse, weitere Werte, Mindestabstand."""
    r = paar(me1, me2, "die Rohrachse" if namen[2] == "längs" else "z")
    zeilen = [eintrag_text(r["haupt"])]
    d = r["delta"]
    if namen[0] == "x":
        zeilen.append(f"Δx {zahl(d[0])} · Δy {zahl(d[1])} · Δz {zahl(d[2])} (Bezugspunkte)")
    else:
        zeilen.append(f"Δ {namen[2]} {zahl(d[2])} · Δ {namen[0]} {zahl(d[0])} · Δ {namen[1]} {zahl(d[1])} "
                      "(Bezugspunkte)")
    zeilen += [eintrag_text(e) for e in r["werte"]]
    return zeilen


def zeilen_summe(liste):
    s = summen(liste)
    zeilen = []
    if s["kanten"] > 1:
        zeilen.append(eintrag_text((f"Gesamtlänge ({s['kanten']} Kanten)", s["laenge"], "mm", s["exakt_laenge"])))
    if s["flaechen"] > 1:
        zeilen.append(eintrag_text((f"Gesamtfläche ({s['flaechen']} Flächen)", s["flaeche"], "mm²",
                                    s["exakt_flaeche"])))
    return zeilen
