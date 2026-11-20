"""Schnittansicht und Explosionsansicht (3D-Visualisierungsupdate V6, Patrick 19.11.2026). Ohne Qt.

Beides ändert nur die Anzeige: Aus dem gezeigten Modell (ansicht3d.Modell) entsteht eine Kopie, die geschnitten bzw.
auseinandergezogen ist. Netz, Konturen, Export und Kalkulation bleiben genau gleich, nichts wird gespeichert, was die
Rechnung liest. Weil die Kopie ein ganz normales Modell ist, zeichnen QPainter und OpenGL sie ohne eigenen Weg.

Schnitt: bis zu drei Ebenen (Punkt, Normale). Was auf der Seite der Normalen liegt, fällt weg; Dreiecke, die die
Ebene kreuzen, werden genau an der Ebene abgeschnitten. Die Schnittkanten kommen als Linien der Art „SC“ dazu, daraus
die Wandstärke an der Schnittstelle (kleinster Abstand zwischen zwei Schnittkanten-Zügen, ≈ am Netz).

Explosion: jeder Körper wandert vom Mittelpunkt der Baugruppe weg (Richtung = Lage seines Mittelpunkts, Weg =
Faktor × Abstand). Konturlinien gehen mit dem Körper, in dessen Hülle sie liegen."""
import math

SCHNITT_ART = "SC"
RICHTUNGEN = {"quer (Rohrachse)": "Z", "längs senkrecht": "X", "längs waagrecht": "Y"}
MAX_EBENEN = 3
WAND_ARTEN = ("A", "I", "BL")      # Außenwand, Innenwand, Blech: daraus die Wandstärke
_CACHES = ("sicht_grenzen", "_grob", "_grob_je", "_glatt", "_ebenen", "_kanten", "_glatt_kanten", "_kanten_klassen",
           "_kanten_grenze", "_typen", "durch")


def ebene(modell, achse, anteil, neigung_grad=0.0, umkehren=False):
    """(Punkt, Normale) einer Schnittebene quer zur Modellachse achse ('X', 'Y', 'Z') an der Stelle anteil (0 … 1 der
    Ausdehnung), um neigung_grad gekippt (um die nächste Achse). Weg fällt die Seite der Normalen (umkehren: die
    andere)."""
    i = "XYZ".index(achse)
    p = list(modell.mitte)
    p[i] = modell.min[i] + (modell.max[i] - modell.min[i]) * max(0.0, min(1.0, anteil))
    n = [0.0, 0.0, 0.0]
    n[i] = 1.0
    w = math.radians(neigung_grad)
    j = (i + 1) % 3
    n[i], n[j] = math.cos(w), math.sin(w)
    if umkehren:
        n = [-c for c in n]
    return tuple(p), tuple(n)


def _seite(q, ebene_):
    p, n = ebene_
    return (q[0] - p[0]) * n[0] + (q[1] - p[1]) * n[1] + (q[2] - p[2]) * n[2]


def _zwischen(a, b, da, db):
    t = da / (da - db)
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _polygon_schneiden(poly, ebene_):
    """Sutherland-Hodgman: Teil des Polygons auf der Seite d <= 0; dazu die Schnittstrecke (oder None)."""
    out, schnitt = [], []
    for k in range(len(poly)):
        a, b = poly[k], poly[(k + 1) % len(poly)]
        da, db = _seite(a, ebene_), _seite(b, ebene_)
        if da <= 0:
            out.append(a)
        if (da <= 0) != (db <= 0):
            q = _zwischen(a, b, da, db)
            out.append(q)
            schnitt.append(q)
    return out, (tuple(schnitt[:2]) if len(schnitt) >= 2 else None)


def _kopie(modell):
    from .ansicht3d import Modell
    g = Modell.__new__(Modell)
    g.__dict__.update(modell.__dict__)
    for c in _CACHES:
        g.__dict__.pop(c, None)
    g._grob = None
    return g


def schneiden(modell, ebenen):
    """Geschnittene Kopie des Modells (nur Anzeige) und die Schnittkanten [(a, b, Flächennormale, Ebene, Art)].
    ebenen: [(Punkt, Normale)]."""
    if not ebenen:
        return modell, []
    p = modell.punkte
    neu_p, neu_d, neu_f, neu_id = [], [], [], []
    ff = modell.dreiecke_f if len(getattr(modell, "dreiecke_f", ())) == len(modell.dreiecke) else None
    ids = modell.dreiecke_id if len(getattr(modell, "dreiecke_id", ())) == len(modell.dreiecke) else None
    herkunft = getattr(modell, "herkunft", None)
    neu_h = []
    kanten = []
    for nr, (i, j, k, art, n) in enumerate(modell.dreiecke):
        poly = [p[i], p[j], p[k]]
        for e in ebenen:
            if all(_seite(q, e) <= 0 for q in poly):
                continue
            poly, strecke = _polygon_schneiden(poly, e)
            if strecke is not None:
                kanten.append((strecke[0], strecke[1], n, e, art))
            if len(poly) < 3:
                break
        if len(poly) < 3:
            continue
        basis = len(neu_p)
        neu_p.extend(poly)
        for t in range(1, len(poly) - 1):           # Fächer: das abgeschnittene Polygon ist konvex
            neu_d.append((basis, basis + t, basis + t + 1, art, n))
            if ff is not None:
                neu_f.append(ff[nr])
            if ids is not None:
                neu_id.append(ids[nr])
            neu_h.append(herkunft[nr] if herkunft and nr < len(herkunft) else nr)
    linien, lids = [], []
    alt_ids = getattr(modell, "linien_id", None) or []
    for lnr, (a, b, art, n) in enumerate(modell.linien):
        ok = True
        for e in ebenen:
            da, db = _seite(a, e), _seite(b, e)
            if da > 0 and db > 0:
                ok = False
                break
            if da > 0:
                a = _zwischen(a, b, da, db)
            elif db > 0:
                b = _zwischen(a, b, da, db)
        if ok:
            linien.append((a, b, art, n))
            lids.append(alt_ids[lnr] if lnr < len(alt_ids) else None)
    # Schnittkanten auf der Ebene nur, wo sie nicht von einer anderen Ebene weggeschnitten sind
    sichtbar = [k for k in kanten if all(_seite(((k[0][0] + k[1][0]) / 2, (k[0][1] + k[1][1]) / 2,
                                                  (k[0][2] + k[1][2]) / 2), e) <= 1e-6 for e in ebenen)]
    for a, b, *_ in sichtbar:
        linien.append((a, b, SCHNITT_ART, (0.0, 0.0, 0.0)))
    g = _kopie(modell)
    g.punkte, g.dreiecke = neu_p, neu_d
    g.dreiecke_f = neu_f if ff is not None else []
    g.dreiecke_id = neu_id if ids is not None else []
    g.herkunft = neu_h
    g.linien = linien
    g.linien_id = lids + [None] * (len(linien) - len(lids))
    g.arten = sorted(set(g.arten) | ({SCHNITT_ART} if sichtbar else set()))
    if neu_p:           # Ausdehnung des Rests (Schatten); min/max/mitte bleiben: das Bild springt nicht
        g.sicht_grenzen = (tuple(min(q[c] for q in neu_p) for c in range(3)),
                           tuple(max(q[c] for q in neu_p) for c in range(3)))
    return g, sichtbar


def _strahl(q, d, a, b):
    """Abstand t > 0 von q längs d (Einheitsvektor in der Ebene) bis zur Strecke a–b oder None."""
    # q + t d = a + u (b − a): in der Ebene lösen über die Komponente mit dem größten Kreuzprodukt
    e = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    w = (a[0] - q[0], a[1] - q[1], a[2] - q[2])
    k = (d[1] * e[2] - d[2] * e[1], d[2] * e[0] - d[0] * e[2], d[0] * e[1] - d[1] * e[0])
    kk = k[0] ** 2 + k[1] ** 2 + k[2] ** 2
    if kk < 1e-18:
        return None
    kw = (w[1] * e[2] - w[2] * e[1], w[2] * e[0] - w[0] * e[2], w[0] * e[1] - w[1] * e[0])
    t = (kw[0] * k[0] + kw[1] * k[1] + kw[2] * k[2]) / kk
    kd = (w[1] * d[2] - w[2] * d[1], w[2] * d[0] - w[0] * d[2], w[0] * d[1] - w[1] * d[0])
    u = (kd[0] * k[0] + kd[1] * k[1] + kd[2] * k[2]) / kk
    if t <= 1e-4 or not -1e-6 <= u <= 1 + 1e-6:
        return None
    # Rest senkrecht zur Ebene (Strecke nicht in derselben Ebene): kein Treffer
    hit = (q[0] + d[0] * t - a[0] - e[0] * u, q[1] + d[1] * t - a[1] - e[1] * u, q[2] + d[2] * t - a[2] - e[2] * u)
    return t if hit[0] ** 2 + hit[1] ** 2 + hit[2] ** 2 < 1e-4 else None


def wandstaerke(kanten, proben=160):
    """Wandstärke an der Schnittstelle [mm] ≈ (typisch, kleinste, größte): von der Mitte jeder Schnittkante (Stichprobe)
    in der Schnittebene gegen die Flächennormale ins Material bis zur nächsten Schnittkante, gewichtet mit der Länge der
    Kante (Stirnflächen zählen kaum); typisch = Median, kleinste/größte = 10/90-%-Wert. None ohne Treffer."""
    wand = [k for k in kanten if len(k) < 5 or k[4] in WAND_ARTEN]
    if len(wand) >= 2:          # nur Wände des Teils (keine Hilfskörper wie „über dem Rohr“ oder Ringe)
        kanten = wand
    if len(kanten) < 2:
        return None
    schritt = max(1, len(kanten) // proben)
    werte = []
    for a, b, n, (_, en), *_ in kanten[::schritt]:
        q = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
        s = n[0] * en[0] + n[1] * en[1] + n[2] * en[2]
        d = (-(n[0] - s * en[0]), -(n[1] - s * en[1]), -(n[2] - s * en[2]))
        ld = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
        if ld < 0.3:            # Fläche fast parallel zur Ebene: keine Wand quer dazu
            continue
        d = (d[0] / ld, d[1] / ld, d[2] / ld)
        best = None
        for a2, b2, n2, e2, *_ in kanten:
            if e2 is not None and e2[1] != en:
                continue
            t = _strahl(q, d, a2, b2)
            if t is not None and (best is None or t < best):
                best = t
        if best is not None:
            werte.append((best, math.dist(a, b)))      # Gewicht = Länge der Kante (lange Wände zählen mehr)
    if not werte:
        return None
    werte.sort()
    summe = sum(g for _, g in werte) or 1.0

    def anteil(x):
        lauf = 0.0
        for v, g in werte:
            lauf += g
            if lauf >= x * summe:
                return v
        return werte[-1][0]
    return anteil(0.5), anteil(0.1), anteil(0.9)


def explodieren(modell, koerper_von, faktor):
    """Auseinandergezogene Kopie (nur Anzeige): jeder Körper (koerper_von[Dreieck] = Kennung) wandert um faktor ×
    (seine Mitte − Mitte aller) nach außen. Ein einzelner Körper bleibt stehen."""
    if not faktor or not modell.dreiecke or not koerper_von or len(koerper_von) != len(modell.dreiecke):
        return modell
    p = modell.punkte
    summe, zahl, huelle = {}, {}, {}
    for nr, (i, j, k, _, _) in enumerate(modell.dreiecke):
        kid = koerper_von[nr]
        s = summe.setdefault(kid, [0.0, 0.0, 0.0])
        h = huelle.setdefault(kid, [list(p[i]), list(p[i])])
        for x in (i, j, k):
            for c in range(3):
                s[c] += p[x][c]
                h[0][c] = min(h[0][c], p[x][c])
                h[1][c] = max(h[1][c], p[x][c])
        zahl[kid] = zahl.get(kid, 0) + 3
    if len(summe) < 2:
        return modell
    mitte_k = {kid: tuple(s[c] / zahl[kid] for c in range(3)) for kid, s in summe.items()}
    gesamt = modell.mitte
    weg = {kid: tuple((m[c] - gesamt[c]) * faktor for c in range(3)) for kid, m in mitte_k.items()}
    neu_p, neu_d = [], []
    for nr, (i, j, k, art, n) in enumerate(modell.dreiecke):
        w = weg[koerper_von[nr]]
        basis = len(neu_p)
        for x in (i, j, k):
            neu_p.append((p[x][0] + w[0], p[x][1] + w[1], p[x][2] + w[2]))
        neu_d.append((basis, basis + 1, basis + 2, art, n))

    def koerper_der_linie(a, b):
        q = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
        drin = [(math.prod(h[1][c] - h[0][c] + 1e-3 for c in range(3)), kid) for kid, h in huelle.items()
                if all(h[0][c] - 0.5 <= q[c] <= h[1][c] + 0.5 for c in range(3))]
        return min(drin)[1] if drin else min(mitte_k, key=lambda kid: math.dist(q, mitte_k[kid]))
    linien = []
    for a, b, art, n in modell.linien:
        w = weg[koerper_der_linie(a, b)]
        linien.append(((a[0] + w[0], a[1] + w[1], a[2] + w[2]), (b[0] + w[0], b[1] + w[1], b[2] + w[2]), art, n))
    g = _kopie(modell)
    g.punkte, g.dreiecke, g.linien = neu_p, neu_d, linien
    g.koerper = []          # Schnittkörper der Konturen gehören zum Rohr selbst: in der Explosion weglassen
    xs = [q[0] for q in neu_p]
    ys = [q[1] for q in neu_p]
    zs = [q[2] for q in neu_p]
    g.min, g.max = (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
    g.mitte = tuple((a + b) / 2 for a, b in zip(g.min, g.max))
    g.groesse = max(1e-6, math.dist(g.min, g.max))
    return g
