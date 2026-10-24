"""3D-Ansicht des Blech-Editors: das Teil aus den Eingaben des Editors gefaltet (Patrick 23.10.2026).

Kein CAD, nur zur Anschauung: Die Abwicklung (Außenkontur des Zuschnitts) wird in Dreiecke zerlegt und an jeder
Biegung um ihre Biegelinie geklappt, im Bereich der Biegung als Bogen (Bogenlänge ba, Radius ba / φ). Oben und
unten je eine Haut im Abstand der Blechdicke, dazu die Seitenflächen am Rand. Innenkonturen und Biegelinien sind
Linien auf der Haut (Farben wie im Editor und in der 3D-Ansicht des STEP-Imports), die Flächen bleiben geschlossen.

Biegungen: Kantteil aus den Schenkeln (blech.biegungen, parallel zur Kantlänge), mehrachsig gekantete Zuschnitte
aus den Biegelinien der STEP-Messung (eingaben['biegelinien']). Die Grundfläche ist die Seite mit dem Schwerpunkt
der Abwicklung (Kantteil: Schenkel 1). + Biegewinkel = nach oben (zum Betrachter der Abwicklung).

Ergebnis: Netz wie ansicht3d ({p, t, l, ln}); ln = Normale je Linienzug, damit Linien auf der Rückseite verdeckt
sind."""
import math

from . import blech, schneidweg as sw

_z = sw._z
BOGEN_SCHRITT = 15.0        # Grad je Teilstück eines Biegebogens


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
    teile = [list(t) for t in _ohrschnitt(kontur)]
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
    # Seitenflächen: Rand an den Biegezonen geteilt
    rand = []
    for i, a in enumerate(kontur):
        b = kontur[(i + 1) % len(kontur)]
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
        for p1, p2 in zip(stuecke, stuecke[1:]):
            rand.append((p1, p2))
    for p1, p2 in rand:
        o1, u1 = haut(p1, 1)[0], haut(p1, -1)[0]
        o2, u2 = haut(p2, 1)[0], haut(p2, -1)[0]
        m = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        lg = math.hypot(dx, dy) or 1
        aussen = (m[0] + dy / lg * 0.05, m[1] - dx / lg * 0.05)       # rechts der Kante = außen (ccw)
        va, vb = gefaltet(m)[0], gefaltet(aussen)[0]
        soll = tuple(vb[i] - va[i] for i in range(3))
        dreieck(o1, o2, u2, soll)
        dreieck(o1, u2, u1, soll)
    # Linien: Innenkonturen (K) oben und unten, Biegelinien (B) oben; je Linie das Merkmal des Teile-Editors (li)
    kennung = {}
    zeile = {id(z): i for i, z in enumerate(e.get("konturen") or [])}
    for z, zug in konturzuege(e, zs):
        for seite in ((1,) if z.get("art") == sw.TEXT_GRAVUR else (1, -1)):    # Gravur nur oben
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
    return dict(p=punkte, t={"BL": dreiecke}, ti={"BL": ["teil"] * (len(dreiecke) // 3)},
                l={a: [[round(c, 3) for c in zug] for zug in z] for a, z in linien.items()}, ln=normalen,
                li=kennung, flach=True)


def konturzuege(e, zs):
    """Innenkonturen als Linienzüge [(Kontur, [(x, y)])] in der Abwicklung (Lage wie in der Skizze)."""
    lg, br = zs["laenge"], zs["breite"]
    konturen = [z for z in e.get("konturen") or [] if z.get("art")]
    frei = [z for z in konturen if z.get("x") is None or z.get("y") is None]
    out = []
    for z in konturen:
        if z in frei:
            i = frei.index(z)
            cx, cy = lg * (i + 1) / (len(frei) + 1), br / 2
        else:
            cx, cy = _z(z["x"]), _z(z["y"])
        art = z.get("art")
        if art in (sw.BOHRUNG, sw.SENKUNG):
            r = _z(z.get("d")) / 2
            zug = [(cx + r * math.cos(i * math.pi / 12), cy + r * math.sin(i * math.pi / 12)) for i in range(25)]
        elif art == sw.LANGLOCH:
            l_, b_ = _z(z.get("l")), _z(z.get("b"))
            r = b_ / 2
            quer = bool(z.get("quer"))
            h = max(l_ / 2 - r, 0)
            zug = []
            for mx, w0 in ((h, -90), (-h, 90)):
                zug += [(mx + r * math.cos(math.radians(w0 + 15 * i)), r * math.sin(math.radians(w0 + 15 * i)))
                        for i in range(13)]
            zug.append(zug[0])
            zug = [((y, x) if quer else (x, y)) for x, y in zug]
            zug = [(cx + x, cy + y) for x, y in zug]
        elif art == sw.RECHTECK:
            b_, h_ = _z(z.get("b")) / 2, _z(z.get("h")) / 2
            zug = [(cx - b_, cy - h_), (cx + b_, cy - h_), (cx + b_, cy + h_), (cx - b_, cy + h_), (cx - b_, cy - h_)]
        elif art == sw.POLYGON:
            try:
                pk = sw.punkte(z.get("punkte"))
            except ValueError:
                continue
            if len(pk) < 3:
                continue
            mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
            zug = [(cx + x - mx, cy + y - my) for x, y in pk] + [(cx + pk[0][0] - mx, cy + pk[0][1] - my)]
        elif art == sw.TEXT_GRAVUR:      # je Strich ein Linienzug
            from . import gravur_text
            out += [(z, zug) for zug in gravur_text.gedreht(gravur_text.linien(z.get("text"), _z(z.get("hoehe"))),
                                                           z.get("winkel"), cx, cy)]
            continue
        else:
            zug = [(cx - 4, cy - 4), (cx + 4, cy - 4), (cx + 4, cy + 4), (cx - 4, cy + 4), (cx - 4, cy - 4)]
        out.append((z, zug))
    return out
