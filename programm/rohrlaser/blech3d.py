"""3D-Ansicht des Blech-Editors: das Teil aus den Eingaben des Editors gefaltet (Patrick 23.10.2026).

Kein CAD, nur zur Anschauung: Die Abwicklung (Außenkontur des Zuschnitts) wird in Dreiecke zerlegt und an jeder
Biegung um ihre Biegelinie geklappt, im Bereich der Biegung als Bogen (Bogenlänge ba, Radius ba / φ). Oben und
unten je eine Haut im Abstand der Blechdicke, dazu die Seitenflächen am Rand. Geschlossene Innenkonturen (Bohrung,
Senkung, Langloch, Rechteck, Polygon) sind aus dem Material geschnitten, mit Lochwand durch die Dicke (Patrick
26.10.2026: „Konturen nicht in 3D im Material sichtbar, nur 2D-Linien“); Gravuren, offene Linien und Konturen, die
nicht ganz im Blech liegen oder sich überschneiden, bleiben Linien. Konturen und Biegelinien sind dazu Linien auf der
Haut (Farben wie im Editor und in der 3D-Ansicht des STEP-Imports).

Biegungen: Kantteil aus den Schenkeln (blech.biegungen, parallel zur Kantlänge), mehrachsig gekantete Zuschnitte
aus den Biegelinien der STEP-Messung (eingaben['biegelinien']). Die Grundfläche ist die Seite mit dem Schwerpunkt
der Abwicklung (Kantteil: Schenkel 1). + Biegewinkel = nach oben (zum Betrachter der Abwicklung).

Ergebnis: Netz wie ansicht3d ({p, t, l, ln}); ln = Normale je Linienzug, damit Linien auf der Rückseite verdeckt
sind."""
import bisect
import math

from . import blech, schneidweg as sw

_z = sw._z
BOGEN_SCHRITT = 15.0        # Grad je Teilstück eines Biegebogens
SPALTEN = 8                 # gelochte Haut: so viele senkrechte Teilungen über die Länge (höchstens alle 30 mm)


def _flaeche2(pk):
    return sum(pk[i][0] * pk[(i + 1) % len(pk)][1] - pk[(i + 1) % len(pk)][0] * pk[i][1] for i in range(len(pk)))


def _ohrschnitt(pk):
    """Einfaches Polygon (gegen den Uhrzeigersinn) in Dreiecke [(a, b, c)] zerlegen (Ohrenschneiden)."""
    idx = list(range(len(pk)))
    out, schutz = [], 0
    while len(idx) > 3 and schutz < 10 * len(pk) ** 2:
        schutz += 1
        n = len(idx)
        for k in range(n):
            i, j, m = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = pk[i], pk[j], pk[m]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-9:
                continue                        # nicht konvex
            if any(_im_dreieck(pk[q], a, b, c) for q in idx if q not in (i, j, m)):
                continue
            out.append((a, b, c))
            del idx[k]
            break
        else:
            break                               # kein Ohr gefunden (Polygon schneidet sich): Rest als Fächer
    out += [(pk[idx[0]], pk[idx[q]], pk[idx[q + 1]]) for q in range(1, len(idx) - 1)]
    return out


def _im_polygon(p, pk):
    """Punkt p strikt im Polygon pk (gerade/ungerade)."""
    x, y, drin = p[0], p[1], False
    for i in range(len(pk)):
        (x1, y1), (x2, y2) = pk[i - 1], pk[i]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            drin = not drin
    return drin


def _strecken_schneiden(a, b, c, d):
    def s(u, v, w):
        return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
    return s(a, b, c) * s(a, b, d) < 0 and s(c, d, a) * s(c, d, b) < 0


def loecher(kontur, zuege):
    """Innenkonturen, die aus dem Material geschnitten werden: geschlossene Züge [(x, y)] ganz im Blech, ohne
    Überschneidung mit dem Rand oder einem früheren Loch; gegen den Uhrzeigersinn, ohne doppelten Endpunkt."""
    out, huellen = [], []
    for zug in zuege:
        pk = [tuple(q) for q in zug]
        if len(pk) > 1 and math.dist(pk[0], pk[-1]) < 1e-9:
            pk = pk[:-1]
        if len(pk) < 3 or abs(_flaeche2(pk)) < 1e-6:
            continue
        if _flaeche2(pk) < 0:
            pk.reverse()
        h = (min(x for x, _ in pk), min(y for _, y in pk), max(x for x, _ in pk), max(y for _, y in pk))
        if not all(_im_polygon(q, kontur) for q in pk) or any(_im_polygon(q, pk) for q in kontur) or \
                any(_strecken_schneiden(pk[i - 1], pk[i], kontur[j - 1], kontur[j])
                    for i in range(len(pk)) for j in range(len(kontur))
                    if min(kontur[j - 1][0], kontur[j][0]) <= h[2] and max(kontur[j - 1][0], kontur[j][0]) >= h[0]):
            continue
        frei = True
        for hg, ag in zip(huellen, out):
            if hg[0] > h[2] or hg[2] < h[0] or hg[1] > h[3] or hg[3] < h[1]:
                continue
            if _im_polygon(pk[0], ag) or _im_polygon(ag[0], pk) or any(
                    _strecken_schneiden(pk[i - 1], pk[i], ag[j - 1], ag[j]) for i in range(len(pk))
                    for j in range(len(ag))):
                frei = False
                break
        if frei:
            out.append(pk)
            huellen.append(h)
    return out


def spalten_fuer(kontur):
    """Senkrechte Teilungen für _gelocht: lange, dünne Streifen in Stücke (die Software-Darstellung sortiert nach
    Dreiecksmitten und zeigt lange Splitter falsch)."""
    x0, x1 = min(x for x, _ in kontur), max(x for x, _ in kontur)
    schritt = max(30.0, (x1 - x0) / SPALTEN)
    return [x0 + schritt * k for k in range(1, int((x1 - x0) / schritt) + 1) if x0 + schritt * k < x1 - 1e-6]


def _bei_x(poly, x):
    """Konvexes Polygon an der Senkrechten x teilen; Ecken auf der Linie gehören zu beiden Teilen."""
    links, rechts = [], []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        if a[0] <= x + 1e-9:
            links.append(a)
        if a[0] >= x - 1e-9:
            rechts.append(a)
        if (a[0] < x - 1e-9 < x + 1e-9 < b[0]) or (b[0] < x - 1e-9 < x + 1e-9 < a[0]):
            q = (x, a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0]))
            links.append(q)
            rechts.append(q)
    return [q for q in (links, rechts) if len(q) >= 3 and abs(_flaeche2(q)) > 1e-9]


def _gelocht(kontur, loch, spalten=()):
    """Fläche der Außenkontur ohne die Löcher als konvexe Stücke [(x, y)]: waagerechte Streifen zwischen allen
    Eckhöhen, im Streifen die Trapeze zwischen den Kanten (gerade/ungerade), senkrecht an spalten geteilt. Jedes
    Stück bekommt die Schnittpunkte der Nachbarstreifen auf seiner Ober- und Unterkante (keine T-Stöße, sonst feine
    Risse im Bild)."""
    kanten = []
    for pk in [kontur] + loch:
        for i in range(len(pk)):
            a, b = pk[i - 1], pk[i]
            if abs(a[1] - b[1]) > 1e-12:
                kanten.append((a, b) if a[1] < b[1] else (b, a))
    hoehen = sorted({q[1] for pk in [kontur] + loch for q in pk})
    kanten.sort(key=lambda k: k[0][1])

    def x_bei(k, y):
        (x1, y1), (x2, y2) = k
        return x1 + (y - y1) * (x2 - x1) / (y2 - y1)
    streifen, naechst, aktiv = [], 0, []
    for ya, yb in zip(hoehen, hoehen[1:]):
        if yb - ya < 1e-9:
            continue
        ym = (ya + yb) / 2
        while naechst < len(kanten) and kanten[naechst][0][1] <= ym:
            aktiv.append(kanten[naechst])
            naechst += 1
        aktiv = [k for k in aktiv if k[1][1] > ym]
        reihe = sorted(aktiv, key=lambda k: x_bei(k, ym))
        streifen.append((ya, yb, [(reihe[i], reihe[i + 1]) for i in range(0, len(reihe) - 1, 2)]))
    punkte_auf = {}                 # Höhe -> alle Schnittpunkte der Streifen darüber und darunter
    for ya, yb, paare in streifen:
        for kl, kr in paare:
            for y in (ya, yb):
                xl, xr = x_bei(kl, y), x_bei(kr, y)
                punkte_auf.setdefault(y, set()).update([xl, xr] + [x for x in spalten if xl < x < xr])
    sortiert = {y: sorted(v) for y, v in punkte_auf.items()}
    out = []
    for ya, yb, paare in streifen:
        for kl, kr in paare:
            la, ra, lb, rb = x_bei(kl, ya), x_bei(kr, ya), x_bei(kl, yb), x_bei(kr, yb)
            unten = [x for x in sortiert[ya] if la + 1e-7 < x < ra - 1e-7]
            oben = [x for x in sortiert[yb] if lb + 1e-7 < x < rb - 1e-7][::-1]
            pk = [(la, ya)] + [(x, ya) for x in unten] + [(ra, ya), (rb, yb)] + [(x, yb) for x in oben] + [(lb, yb)]
            rein = [q for i, q in enumerate(pk) if math.dist(q, pk[i - 1]) > 1e-9]
            if len(rein) < 3 or abs(_flaeche2(rein)) <= 1e-9:
                continue
            stuecke = [rein]
            for x in spalten:
                if la + 1e-7 < x < ra - 1e-7 or lb + 1e-7 < x < rb - 1e-7:
                    stuecke = [q for st in stuecke for q in _bei_x(st, x)]
            for st in stuecke:
                n = len(st)
                if all((st[i][0] - st[i - 1][0]) * (st[(i + 1) % n][1] - st[i][1]) -
                       (st[i][1] - st[i - 1][1]) * (st[(i + 1) % n][0] - st[i][0]) > 1e-9 for i in range(n)):
                    out.append(st)          # echte Ecken: Fächer ab der ersten (wie die Teile ohne Löcher)
                    continue
                m = (sum(q[0] for q in st) / len(st), sum(q[1] for q in st) / len(st))
                out += [[m, q, st[(i + 1) % len(st)]] for i, q in enumerate(st)]     # Fächer ab der Mitte
    return out


def _im_dreieck(p, a, b, c):
    def s(u, v, w):
        return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
    return s(a, b, p) > 1e-9 and s(b, c, p) > 1e-9 and s(c, a, p) > 1e-9


def _teilen(poly, o, n, w):
    """Konvexes Polygon an der Geraden dot(p − o, n) = w teilen: [Teile]."""
    vor, nach = [], []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        da = (a[0] - o[0]) * n[0] + (a[1] - o[1]) * n[1] - w
        db = (b[0] - o[0]) * n[0] + (b[1] - o[1]) * n[1] - w
        (vor if da <= 0 else nach).append(a)
        if (da < 0 < db) or (db < 0 < da):
            t = da / (da - db)
            q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            vor.append(q)
            nach.append(q)
    return [x for x in (vor, nach) if len(x) >= 3 and abs(_flaeche2(x)) > 1e-6]


def aussenkontur(e, zs):
    """Außenkontur der Abwicklung [(x, y)] gegen den Uhrzeigersinn, ab (0, 0) wie in der Skizze."""
    if zs.get("punkte"):
        pk = [tuple(map(float, q)) for q in zs["punkte"]]
        minx, miny = min(x for x, _ in pk), min(y for _, y in pk)
        pk = [(x - minx, y - miny) for x, y in pk]
    else:
        lg, br = zs["laenge"], zs["breite"]
        r = min(_z(e.get("eckradius")), lg / 2, br / 2) if e.get("art") != blech.KANTTEIL else 0
        if r > 0.1:
            pk = []
            for cx, cy, w0 in ((lg - r, r, -90), (lg - r, br - r, 0), (r, br - r, 90), (r, r, 180)):
                pk += [(cx + r * math.cos(math.radians(w0 + 15 * i)), cy + r * math.sin(math.radians(w0 + 15 * i)))
                       for i in range(7)]
        else:
            pk = [(0.0, 0.0), (lg, 0.0), (lg, br), (0.0, br)]
    if _flaeche2(pk) < 0:
        pk.reverse()
    return pk


def biegungen(e, zs, kontur):
    """Biegungen für die Faltung: [dict(o (Anfang der Biegezone), d (Richtung der Biegelinie), n (weg von der
    Grundfläche), ba, phi [rad, mit Vorzeichen], t (Bereich längs d), abstand (von der Grundfläche))]."""
    s = _z(e.get("dicke"))
    k = blech.K_FAKTOR
    out = []
    if e.get("art") == blech.KANTTEIL:
        for lage, winkel, r, _ in zs.get("biegungen") or ():
            ba = math.pi * abs(winkel) / 180 * (r + k * s)
            out.append(dict(o=(0.0, lage - ba / 2), d=(1.0, 0.0), n=(0.0, 1.0), ba=ba, phi=math.radians(winkel),
                            t=(-1e9, 1e9), abstand=lage))
        return out
    if not kontur:
        return out
    ax = _flaeche2(kontur) / 2 or 1
    gx = sum((a[0] + b[0]) * (a[0] * b[1] - b[0] * a[1]) for a, b in zip(kontur, kontur[1:] + kontur[:1])) / (6 * ax)
    gy = sum((a[1] + b[1]) * (a[0] * b[1] - b[0] * a[1]) for a, b in zip(kontur, kontur[1:] + kontur[:1])) / (6 * ax)
    verschub = (0.0, 0.0)
    if zs.get("punkte"):
        pk = [tuple(map(float, q)) for q in zs["punkte"]]
        verschub = (min(x for x, _ in pk), min(y for _, y in pk))
    for x in e.get("biegelinien") or ():
        try:
            (x1, y1), (x2, y2) = [(float(a) - verschub[0], float(b) - verschub[1]) for a, b in x["punkte"]]
        except (TypeError, ValueError, KeyError):
            continue
        lg = math.hypot(x2 - x1, y2 - y1)
        winkel = _z(x.get("winkel"))
        if lg < 1e-6 or not winkel:
            continue
        d = ((x2 - x1) / lg, (y2 - y1) / lg)
        n = (-d[1], d[0])
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        if (gx - cx) * n[0] + (gy - cy) * n[1] > 0:
            n = (-n[0], -n[1])
        ba = _z(x.get("ba")) or math.pi * abs(winkel) / 180 * (s + k * s)
        t1, t2 = x1 * d[0] + y1 * d[1], x2 * d[0] + y2 * d[1]
        out.append(dict(o=(cx - n[0] * ba / 2, cy - n[1] * ba / 2), d=d, n=n, ba=ba, phi=math.radians(winkel),
                        t=(min(t1, t2) - 1, max(t1, t2) + 1), abstand=(cx - gx) * n[0] + (cy - gy) * n[1]))
    return out


def _drehen(v, achse, w):
    """v um die Einheitsachse (Richtung) um w [rad] drehen (Rodrigues)."""
    c, s = math.cos(w), math.sin(w)
    kx, ky, kz = achse
    dot = kx * v[0] + ky * v[1] + kz * v[2]
    kreuz = (ky * v[2] - kz * v[1], kz * v[0] - kx * v[2], kx * v[1] - ky * v[0])
    return tuple(v[i] * c + kreuz[i] * s + achse[i] * dot * (1 - c) for i in range(3))


def falten(p, bg):
    """Punkt (x, y) der Abwicklung -> (Punkt 3D, Normale) der gefalteten Mittelfläche."""
    x, y = p
    v, nrm = (x, y, 0.0), (0.0, 0.0, 1.0)
    wirksam = []
    for b in bg:
        w = (x - b["o"][0]) * b["n"][0] + (y - b["o"][1]) * b["n"][1]
        t = x * b["d"][0] + y * b["d"][1]
        if w > 1e-9 and b["t"][0] <= t <= b["t"][1]:
            wirksam.append((b["abstand"], b, min(w, b["ba"])))
    for _, b, s in sorted(wirksam, key=lambda z: -z[0]):        # die äußerste Biegung zuerst
        phi = abs(b["phi"])
        if phi < 1e-9:
            continue
        rho = b["ba"] / phi
        oben = 1.0 if b["phi"] > 0 else -1.0
        a = (b["o"][0], b["o"][1], oben * rho)                  # Biegeachse
        k = (b["n"][1] * oben, -b["n"][0] * oben, 0.0)           # n × oben: n dreht zur Seite 'oben'
        winkel = phi * s / b["ba"]
        q = (v[0] - b["n"][0] * s - a[0], v[1] - b["n"][1] * s - a[1], v[2] - a[2])
        q = _drehen(q, k, winkel)
        v = (q[0] + a[0], q[1] + a[1], q[2] + a[2])
        nrm = _drehen(nrm, k, winkel)
    return v, nrm


def _ansicht(v):
    """Abwicklung (x längs der Kante, y quer, z nach oben) -> Achsen der 3D-Ansicht (Z waagerecht, Y oben)."""
    return v[1], v[2], v[0]


def netz(e, zs):
    """Netz der 3D-Ansicht (ansicht3d) aus Eingaben e und Zuschnitt zs (blech.zuschnitt) oder None."""
    if not zs:
        return None
    s = max(_z(e.get("dicke")), 0.1)
    kontur = aussenkontur(e, zs)
    bg = biegungen(e, zs, kontur)
    arten = (sw.BOHRUNG, sw.SENKUNG) + tuple(blech.DREH_ARTEN)
    loch = loecher(kontur, [zug for z, zug in konturzuege(e, zs) if z.get("art") in arten and not z.get("linien")])
    spalten = spalten_fuer(kontur) if loch else []
    teile = _gelocht(kontur, loch, spalten) if loch else [list(t) for t in _ohrschnitt(kontur)]
    loch_hoehen = sorted({q[1] for pk in [kontur] + loch for q in pk})      # Streifengrenzen von _gelocht
    for b in bg:                            # an jeder Biegezone teilen, im Bogen in Schritten
        n_schritt = max(2, math.ceil(math.degrees(abs(b["phi"])) / BOGEN_SCHRITT))
        for i in range(n_schritt + 1):
            w = b["ba"] * i / n_schritt
            teile = [q for t in teile for q in _teilen(t, b["o"], b["n"], w)]
    punkte, dreiecke, linien, normalen = [], [], {}, {}
    cache = {}

    def gefaltet(q):
        key = (round(q[0], 6), round(q[1], 6))
        if key not in cache:
            cache[key] = falten(q, bg)
        return cache[key]

    def punkt(v):
        punkte.extend(round(c, 3) for c in _ansicht(v))
        return len(punkte) // 3 - 1

    def haut(q, seite):
        v, n = gefaltet(q)
        return tuple(v[i] + n[i] * s / 2 * seite for i in range(3)), n

    def dreieck(a, b, c, soll):
        u = [b[i] - a[i] for i in range(3)]
        w = [c[i] - a[i] for i in range(3)]
        nn = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        if sum(nn[i] * soll[i] for i in range(3)) < 0:
            b, c = c, b
        dreiecke.extend((punkt(a), punkt(b), punkt(c)))

    for t in teile:
        for i in range(1, len(t) - 1):
            for seite in (1, -1):
                (a, na), (b, _), (c, _) = haut(t[0], seite), haut(t[i], seite), haut(t[i + 1], seite)
                dreieck(a, b, c, tuple(x * seite for x in na))
    # Seitenflächen: Rand und Lochwände an den Biegezonen geteilt (Vorderseite nach außen bzw. zur Lochmitte)
    rand = []
    for pk, aussen_rechts in [(kontur, True)] + [(q, False) for q in loch]:
        _rand_stuecke(_an_hoehen(pk, loch_hoehen, spalten) if loch else pk, bg, rand, aussen_rechts)
    for p1, p2, rechts in rand:
        o1, u1 = haut(p1, 1)[0], haut(p1, -1)[0]
        o2, u2 = haut(p2, 1)[0], haut(p2, -1)[0]
        m = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        lg = math.hypot(dx, dy) or 1
        f = 0.05 if rechts else -0.05       # rechts der Kante = außen (ccw), Loch: links = Lochinneres
        aussen = (m[0] + dy / lg * f, m[1] - dx / lg * f)
        va, vb = gefaltet(m)[0], gefaltet(aussen)[0]
        soll = tuple(vb[i] - va[i] for i in range(3))
        dreieck(o1, o2, u2, soll)
        dreieck(o1, u2, u1, soll)
    # Linien: Innenkonturen (K) oben und unten, Biegelinien (B) oben; je Linie das Merkmal des Teile-Editors (li)
    kennung = {}
    zeile = {id(z): i for i, z in enumerate(e.get("konturen") or [])}
    for z, zug in konturzuege(e, zs):
        for seite in ([1] if z.get("art") == sw.TEXT_GRAVUR else [1, -1]):    # Gravur nur oben
            pk = [haut(q, seite * 1.02) for q in zug]
            linien.setdefault("K", []).append([c for v, _ in pk for c in _ansicht(v)])
            normalen.setdefault("K", []).append([round(c * seite, 3) for c in _ansicht(pk[len(pk) // 2][1])])
            kennung.setdefault("K", []).append(f"kontur:{zeile.get(id(z))}")
    for nr, b in enumerate(bg):
        lg = (b["t"][1] - b["t"][0]) if b["t"][1] < 1e8 else zs["laenge"]
        t0 = b["t"][0] if b["t"][0] > -1e8 else 0.0
        m = (b["o"][0] + b["n"][0] * b["ba"] / 2, b["o"][1] + b["n"][1] * b["ba"] / 2)
        tm = m[0] * b["d"][0] + m[1] * b["d"][1]
        zug = [(m[0] + b["d"][0] * (t0 + lg * i / 8 - tm), m[1] + b["d"][1] * (t0 + lg * i / 8 - tm)) for i in range(9)]
        pk = [haut(q, 1.02) for q in zug]
        linien.setdefault("B", []).append([c for v, _ in pk for c in _ansicht(v)])
        normalen.setdefault("B", []).append([round(c, 3) for c in _ansicht(pk[4][1])])
        kennung.setdefault("B", []).append(f"biegung:{nr}")
    # exakte Geometrie für das Messen (Plan 3D-Ansicht 3E-11, M4): Bohrungen mit Mitte, Achse und Ø auf beiden Häuten
    geo = dict(kreise=[], mitten=[], merkmale={}, rohr={})
    for z, cx, cy in kontur_mitten(e, zs):
        kid = f"kontur:{zeile.get(id(z))}"
        for seite in (1, -1):
            v, n = haut((cx, cy), seite)
            m, achse = [round(c, 6) for c in _ansicht(v)], [round(c, 6) for c in _ansicht(n)]
            if z.get("art") in (sw.BOHRUNG, sw.SENKUNG) and _z(z.get("d")) > 0:
                geo["kreise"].append(dict(m=m, n=achse, d=_z(z.get("d")), id=kid))
            elif z.get("art") != sw.TEXT_GRAVUR:
                geo["mitten"].append(dict(p=m, n=achse, id=kid))
        geo["merkmale"][kid] = {k: z[k] for k in ("art", "d", "D", "l", "b", "h", "r", "winkel", "x", "y")
                                if z.get(k) not in (None, "")}
    from . import schnittkoerper
    out = dict(p=punkte, t={"BL": dreiecke}, ti={"BL": ["teil"] * (len(dreiecke) // 3)},
               l={a: [[round(c, 3) for c in zug] for zug in z] for a, z in linien.items()}, ln=normalen,
               li=kennung, flach=True, geo=geo)
    wk = schnittkoerper.blech(e, zs, haut, _ansicht, s)     # Schnittkörper durch die Dicke
    if wk:
        out["wk"] = wk
    return out


def _an_hoehen(pk, hoehen, spalten=()):
    """Geschlossenen Zug an den Streifenhöhen und Spalten von _gelocht teilen (Rand und Lochwand ohne T-Stöße zur
    Haut)."""
    out = []
    for i, a in enumerate(pk):
        b = pk[(i + 1) % len(pk)]
        out.append(a)
        ts = set()
        for k, grenzen in ((1, hoehen), (0, spalten)):
            if abs(b[k] - a[k]) < 1e-12:
                continue
            lo, hi = sorted((a[k], b[k]))
            for g in grenzen[bisect.bisect_right(grenzen, lo + 1e-9):bisect.bisect_left(grenzen, hi - 1e-9)]:
                ts.add((g - a[k]) / (b[k] - a[k]))
        out += [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in sorted(ts)]
    return out

def _rand_stuecke(pk, bg, rand, rechts):
    """Kanten des geschlossenen Zugs pk an den Biegezonen geteilt an rand anhängen: (p1, p2, rechts)."""
    for i, a in enumerate(pk):
        b = pk[(i + 1) % len(pk)]
        ts = {0.0, 1.0}
        for bb in bg:
            n_schritt = max(2, math.ceil(math.degrees(abs(bb["phi"])) / BOGEN_SCHRITT))
            da = (a[0] - bb["o"][0]) * bb["n"][0] + (a[1] - bb["o"][1]) * bb["n"][1]
            db = (b[0] - bb["o"][0]) * bb["n"][0] + (b[1] - bb["o"][1]) * bb["n"][1]
            for j in range(n_schritt + 1):
                w = bb["ba"] * j / n_schritt
                if abs(db - da) > 1e-9 and 0 < (w - da) / (db - da) < 1:
                    ts.add((w - da) / (db - da))
        ts = sorted(ts)
        stuecke = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in ts]
        rand.extend((p1, p2, rechts) for p1, p2 in zip(stuecke, stuecke[1:]))


def kontur_mitten(e, zs):
    """Mitte je Innenkontur in der Abwicklung [(Kontur, cx, cy)] (ohne Lage gleichmäßig verteilt wie die Skizze)."""
    lg, br = zs["laenge"], zs["breite"]
    konturen = [z for z in e.get("konturen") or [] if z.get("art")]
    frei = [z for z in konturen if z.get("x") is None or z.get("y") is None]
    out = []
    for z in konturen:
        if z in frei:
            i = frei.index(z)
            out.append((z, lg * (i + 1) / (len(frei) + 1), br / 2))
        else:
            out.append((z, _z(z["x"]), _z(z["y"])))
    return out


def konturzuege(e, zs):
    """Innenkonturen als Linienzüge [(Kontur, [(x, y)])] in der Abwicklung (Lage wie in der Skizze)."""
    out = []
    for z, cx, cy in kontur_mitten(e, zs):
        art = z.get("art")
        if art in (sw.BOHRUNG, sw.SENKUNG):
            r = _z(z.get("d")) / 2
            zug = [(cx + r * math.cos(i * math.pi / 12), cy + r * math.sin(i * math.pi / 12)) for i in range(25)]
        elif art in blech.DREH_ARTEN:
            zug = [(cx + x, cy + y) for x, y in blech.kontur_umriss(z)]
            if not zug:
                continue
        elif z.get("linien"):            # Gravur bzw. offene Schnittlinie aus dem DXF-Import
            out += [(z, [(cx + float(x), cy + float(y)) for x, y in zug]) for zug in z["linien"]]
            continue
        elif art == sw.TEXT_GRAVUR:      # je Strich ein Linienzug
            from . import gravur_text
            out += [(z, zug) for zug in gravur_text.gedreht(gravur_text.linien(z.get("text"), _z(z.get("hoehe"))),
                                                           z.get("winkel"), cx, cy)]
            continue
        else:
            zug = [(cx - 4, cy - 4), (cx + 4, cy - 4), (cx + 4, cy + 4), (cx - 4, cy + 4), (cx - 4, cy - 4)]
        out.append((z, zug))
    return out
