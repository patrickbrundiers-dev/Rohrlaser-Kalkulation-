"""Kanten zu einer Kontur verbinden und Konturen skalieren (CAD-Entwicklungsplan Paket 6, Abschnitte 4.2 und 4.4;
Patrick 12.11.2026 „Alle, Reihenfolge 5, 6, K, 7“).

Kanten aus der 3D-Auswahl (auswahl3d: Gerade a–b, Kreis bzw. Bogen mit Punkten) werden an gemeinsamen Endpunkten
(FANG mm) zu einem Linienzug verkettet. Geprüft wird: genau ein zusammenhängender Zug ohne Abzweig, geschlossen
(Ende = Anfang, sonst Lücke mit Lage und Breite), keine Selbstüberschneidung in der Abwicklung. Ergebnis ist eine
Konturzeile wie aus dem STEP- bzw. DXF-Import:
- Rohr: Sonderkontur mit echtem Umriss [[dx längs, dq am Umfang]] um ihre Mitte (x, Seite, q), auch über mehrere
  Flächen; ein einzelner Kreis auf einer Fläche wird eine Bohrung. Modellpunkte wie rohr3d: (−u, v, x).
- Blech: Polygon (Punkte um ihre Mitte, Lage x/y in der Abwicklung); der Punkt im 3D wird über blech3d.falten in die
  Abwicklung zurückgerechnet (auch über Biegungen); ein einzelner Kreis wird eine Bohrung.
Die Punkte bleiben, wie sie im Modell liegen: nichts wird verschoben oder geglättet."""
import math

from . import schneidweg as sw

FANG = 0.1              # mm: Endpunkte so nah gelten als derselbe Punkt
AUF_FLAECHE = 0.6       # mm: so weit darf ein Punkt neben der Außenhaut liegen (Netzgenauigkeit)


def _zahl(x, n=2):
    return round(float(x), n) + 0.0


# ------------------------------------------------------------------------------------------- Kanten verketten
def stuecke(kanten):
    """Kanten-Elemente der 3D-Auswahl als Linienzüge [[(x, y, z), …]]; ganze Kreise geschlossen."""
    out = []
    for k in kanten:
        if k.get("kreis"):
            pk = [tuple(map(float, q)) for q in (k["kreis"].get("punkte") or ())]
            if len(pk) >= 2:
                out.append(pk)
        elif k.get("a") is not None and k.get("b") is not None:
            out.append([tuple(map(float, k["a"])), tuple(map(float, k["b"]))])
    return out


def verketten(zuege, fang=FANG):
    """Linienzüge an gemeinsamen Endpunkten zu einem Zug verbinden: (Punkte, geschlossen). ValueError mit Grund
    (keine Kanten, Abzweig, mehrere getrennte Züge)."""
    zuege = [list(z) for z in zuege if len(z) >= 2]
    if not zuege:
        raise ValueError("Kanten zu Kontur: Erst im 3D die Kanten wählen (Auswahl „Kante“, Strg+Klick für mehrere).")
    if len(zuege) == 1:
        z = zuege[0]
        return z, math.dist(z[0], z[-1]) <= fang and len(z) > 2

    def gleich(p, q):
        return math.dist(p, q) <= fang
    # Abzweig: ein Endpunkt, an dem mehr als zwei Kantenenden liegen
    enden = [z[0] for z in zuege] + [z[-1] for z in zuege]
    for p in enden:
        if sum(1 for q in enden if gleich(p, q)) > 2:
            raise ValueError("Kanten zu Kontur: An einem Punkt treffen mehr als zwei Kanten zusammen "
                             f"({', '.join(f'{c:.1f}' for c in p)}). Bitte nur die Kanten einer Kontur wählen.")
    rest = zuege[1:]
    zug = list(zuege[0])
    while rest:
        for i, z in enumerate(rest):
            if gleich(zug[-1], z[0]):
                zug += z[1:]
            elif gleich(zug[-1], z[-1]):
                zug += z[-2::-1]
            elif gleich(zug[0], z[-1]):
                zug = z[:-1] + zug
            elif gleich(zug[0], z[0]):
                zug = z[:0:-1] + zug
            else:
                continue
            rest.pop(i)
            break
        else:
            raise ValueError(f"Kanten zu Kontur: Die gewählten Kanten bilden {1 + _zuege_zahl(rest, fang)} getrennte "
                             "Züge. Bitte die fehlenden Kanten dazwischen mitwählen.")
    geschlossen = gleich(zug[0], zug[-1])
    if geschlossen:
        zug[-1] = zug[0]
    return zug, geschlossen


def _zuege_zahl(rest, fang):
    """Wie viele getrennte Züge die übrigen Kanten noch bilden (für die Meldung)."""
    n, offen = 0, [list(z) for z in rest]
    while offen:
        n += 1
        zug = offen.pop(0)
        weiter = True
        while weiter:
            weiter = False
            for i, z in enumerate(offen):
                if any(math.dist(p, q) <= fang for p in (zug[0], zug[-1]) for q in (z[0], z[-1])):
                    zug = zug + z
                    offen.pop(i)
                    weiter = True
                    break
    return n


def luecke(zug):
    """Offener Zug: (Mitte der Lücke, Breite) zwischen Ende und Anfang."""
    a, b = zug[-1], zug[0]
    return tuple((a[i] + b[i]) / 2 for i in range(3)), math.dist(a, b)


def _schneiden(a, b, c, d):
    def kreuz(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2, d3, d4 = kreuz(c, d, a), kreuz(c, d, b), kreuz(a, b, c), kreuz(a, b, d)
    return ((d1 > 1e-9 and d2 < -1e-9) or (d1 < -1e-9 and d2 > 1e-9)) and \
        ((d3 > 1e-9 and d4 < -1e-9) or (d3 < -1e-9 and d4 > 1e-9))


def selbstschnitt(pk):
    """Erste Selbstüberschneidung eines geschlossenen 2D-Zugs als Punkt oder None."""
    n = len(pk)
    seg = [(pk[i], pk[(i + 1) % n]) for i in range(n) if math.dist(pk[i], pk[(i + 1) % n]) > 1e-9]
    m = len(seg)
    for i in range(m):
        a, b = seg[i]
        x0, x1 = min(a[0], b[0]), max(a[0], b[0])
        y0, y1 = min(a[1], b[1]), max(a[1], b[1])
        for j in range(i + 2, m):
            if i == 0 and j == m - 1:
                continue
            c, d = seg[j]
            if max(c[0], d[0]) < x0 or min(c[0], d[0]) > x1 or max(c[1], d[1]) < y0 or min(c[1], d[1]) > y1:
                continue
            if _schneiden(a, b, c, d):
                return ((a[0] + b[0] + c[0] + d[0]) / 4, (a[1] + b[1] + c[1] + d[1]) / 4)
    return None


def _ohne_doppelte(pk):
    out = []
    for p in pk:
        if not out or math.dist(p, out[-1]) > 1e-6:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= 1e-6:
        out.pop()
    return out


def _gerade_weg(pk, tol=0.005):
    """Punkte auf einer Geraden zwischen ihren Nachbarn weglassen (Abweichung unter tol mm): die Form bleibt gleich."""
    out = list(pk)
    i = 0
    while len(out) > 3 and i < len(out):
        a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
        lg = math.dist(a, c)
        if lg > 1e-9 and abs((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / lg < tol and \
                min(a[0], c[0]) - tol <= b[0] <= max(a[0], c[0]) + tol and \
                min(a[1], c[1]) - tol <= b[1] <= max(a[1], c[1]) + tol:
            out.pop(i)
        else:
            i += 1
    return out


def _umfang(pk):
    return sum(math.dist(pk[i], pk[(i + 1) % len(pk)]) for i in range(len(pk)))


def _kreis_allein(kanten):
    """Genau ein ganzer Kreis gewählt: sein Ø, sonst None."""
    if len(kanten) == 1 and kanten[0].get("kreis") and not kanten[0]["kreis"].get("bogen"):
        return float(kanten[0]["kreis"]["d"])
    return None


def _offen(zug, geschlossen):
    """Offener Zug: ValueError mit Lage und Breite der Lücke (Koordinaten des Modells)."""
    if not geschlossen:
        m, b = luecke(zug)
        raise ValueError(f"Kanten zu Kontur: Die Kontur ist offen, Lücke {b:.2f} mm bei "
                         f"{', '.join(f'{c:.1f}' for c in m)}. Bitte die Kanten bis zum Anfang mitwählen.")


def _pruefen(zug, geschlossen, nach_2d, name):
    """Gemeinsame Prüfung ohne Selbstüberschneidung; Ergebnis: Punkte in 2D ohne Wiederholung."""
    pk = _gerade_weg(_ohne_doppelte([nach_2d(p) for p in zug]))
    if len(pk) < 3:
        raise ValueError("Kanten zu Kontur: Zu wenige Punkte für eine Kontur.")
    x = selbstschnitt(pk)
    if x is not None:
        raise ValueError(f"Kanten zu Kontur: Die Kontur überschneidet sich selbst ({name} {x[0]:.1f} / {x[1]:.1f}). "
                         "Bitte die Kanten prüfen.")
    return pk


# ------------------------------------------------------------------------------------------- Rohr
def _rohr_s(qs, u, v):
    """Stelle s der Abwicklung und Abstand zur Außenhaut für einen Punkt (u, v) des Querschnitts."""
    if qs.r:
        w = math.degrees(math.atan2(u, v))
        return ((w + 45) % 360) / 360 * qs.umfang, abs(math.hypot(u, v) - qs.r)
    beste, s0 = None, 0.0
    for f in qs.flaechen:
        q = (u - f.mitte[0]) * f.dir[0] + (v - f.mitte[1]) * f.dir[1]
        qk = max(-f.breite / 2, min(f.breite / 2, q))
        p = f.punkt(qk)
        d = math.hypot(u - p[0], v - p[1])
        if beste is None or d < beste[1]:
            beste = (s0 + qk + f.breite / 2, d)
        s0 += f.breite
    return beste


def rohr(qs, kanten, fang=FANG):
    """Konturzeile (Sonderkontur bzw. Bohrung) aus gewählten Kanten am Rohr-Modell. ValueError mit Grund."""
    zug, zu = verketten(stuecke(kanten), fang)
    _offen(zug, zu)
    U = qs.umfang
    toleranz = max(AUF_FLAECHE, 0.45 * (getattr(qs, "radius", 0.0) or 0.0))
    roh = []
    for p in zug:
        u, v, x = -p[0], p[1], p[2]
        s, d = _rohr_s(qs, u, v)
        if d > toleranz:
            raise ValueError(f"Kanten zu Kontur: Die Kante bei {p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f} liegt nicht auf der "
                             "Außenhaut des Rohrs (Innenwand oder Schnittfläche am Ende).")
        roh.append((s, x))
    # über die Naht stetig: s relativ zum ersten Punkt in (−U/2, U/2]
    s_erst = roh[0][0]
    sx = []
    s_alt = s_erst
    for s, x in roh:
        s = s + U * round((s_alt - s) / U)
        sx.append((s, x))
        s_alt = s
    smin, smax = min(s for s, _ in sx), max(s for s, _ in sx)
    if smax - smin > U - 1.0:
        raise ValueError("Kanten zu Kontur: Die Kontur läuft ganz um das Rohr (z. B. eine Schnittkante am Ende); "
                         "dafür bitte die Enden bearbeiten.")
    xmin, xmax = min(x for _, x in sx), max(x for _, x in sx)
    sc, xc = (smin + smax) / 2, (xmin + xmax) / 2
    pk = _pruefen([(x, s, 0.0) for s, x in sx], zu, lambda q: (q[0] - xc, q[1] - sc), "längs/quer")
    z = dict(anzahl=1, x=_zahl(xc, 1))
    sm = sc % U
    if qs.r:
        z["seite"] = _zahl((sm / U * 360 - 45) % 360, 1)
    else:
        s0 = 0.0
        for f in qs.flaechen:
            if sm <= s0 + f.breite or f is qs.flaechen[-1]:
                z["seite"] = f.name
                q = sm - (s0 + f.breite / 2)
                if abs(q) > 0.05:
                    z["q"] = _zahl(q, 1)
                break
            s0 += f.breite
    d = _kreis_allein(kanten)
    if d is not None and (smax - smin) <= d + 0.5 and abs((xmax - xmin) - d) <= 0.5:
        z.update(art=sw.BOHRUNG, d=_zahl(d, 2))
        return z
    z.update(art=sw.SONDERKONTUR, umriss=[[_zahl(dx), _zahl(dq)] for dx, dq in pk],
             laenge=_zahl(_umfang(pk), 1), huelle=_zahl(max(xmax - xmin, smax - smin), 1),
             text="aus Kanten")
    return z


# ------------------------------------------------------------------------------------------- Blech
def _blech_flach(e, zs):
    """Funktion Abwicklung (x, y) -> (Punkt der Mittelfläche, Normale) in Ansichtsachsen (blech3d._ansicht)."""
    from . import blech3d
    kontur = blech3d.aussenkontur(e, zs)
    bg = blech3d.biegungen(e, zs, kontur)

    def f(p):
        v, n = blech3d.falten(p, bg)
        return blech3d._ansicht(v), blech3d._ansicht(n)
    return f, kontur, bool(bg)


def blech_abwicklung(e, zs, punkte):
    """3D-Punkte (Ansicht des Blech-Editors) -> Punkte der Abwicklung [(x, y)]. ValueError, wenn ein Punkt nicht auf
    dem Blech liegt."""
    f, kontur, gebogen = _blech_flach(e, zs)
    s = max(float(e.get("dicke") or 0) or 0.1, 0.1)
    if not gebogen:          # flach: Ansicht (y, z, x) -> Abwicklung (x, y) direkt
        out = []
        for p in punkte:
            if abs(abs(p[1]) - s / 2) > AUF_FLAECHE and abs(p[1]) > s / 2 + AUF_FLAECHE:
                raise ValueError(f"Kanten zu Kontur: Punkt {p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f} liegt nicht auf dem "
                                 "Blech.")
            out.append((p[2], p[0]))
        return out
    xs, ys = [q[0] for q in kontur], [q[1] for q in kontur]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    schritt = max(1.0, math.sqrt((x1 - x0) * (y1 - y0) / 4000.0))
    raster = []
    y = y0
    while y <= y1 + 1e-9:
        x = x0
        while x <= x1 + 1e-9:
            raster.append(((x, y), f((x, y))[0]))
            x += schritt
        y += schritt
    out = []
    for p in punkte:
        (x, y), _ = min(raster, key=lambda r: (r[1][0] - p[0]) ** 2 + (r[1][1] - p[1]) ** 2 + (r[1][2] - p[2]) ** 2)
        h = 0.0
        for _ in range(12):      # Gauß-Newton auf (x, y, h): Mittelfläche + h × Normale = p
            m, n = f((x, y))
            r = [m[i] + h * n[i] - p[i] for i in range(3)]
            if math.sqrt(sum(c * c for c in r)) < 1e-4:
                break
            eps = 1e-3
            mx, _ = f((x + eps, y))
            my, _ = f((x, y + eps))
            J = [[(mx[i] - m[i]) / eps, (my[i] - m[i]) / eps, n[i]] for i in range(3)]
            try:
                dx, dy, dh = _loesen(J, [-c for c in r])
            except ZeroDivisionError:
                break
            x, y, h = x + dx, y + dy, h + dh
        m, n = f((x, y))
        rest = math.dist([m[i] + h * n[i] for i in range(3)], p)
        if rest > AUF_FLAECHE or abs(h) > s / 2 + AUF_FLAECHE:
            raise ValueError(f"Kanten zu Kontur: Punkt {p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f} liegt nicht auf dem Blech.")
        out.append((x, y))
    return out


def _loesen(a, b):
    """3×3-Gleichungssystem (Cramer)."""
    def det(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    d = det(a)
    if abs(d) < 1e-12:
        raise ZeroDivisionError
    out = []
    for k in range(3):
        m = [row[:] for row in a]
        for i in range(3):
            m[i][k] = b[i]
        out.append(det(m) / d)
    return out


def blech(e, zs, kanten, fang=FANG):
    """Konturzeile (Polygon bzw. Bohrung) aus gewählten Kanten am Blech-Modell. ValueError mit Grund."""
    zug, zu = verketten(stuecke(kanten), fang)
    _offen(zug, zu)
    flach = blech_abwicklung(e, zs, zug)
    pk = _pruefen([(x, y, 0.0) for x, y in flach], zu, lambda q: (q[0], q[1]), "x/y")
    d = _kreis_allein(kanten)
    mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
    if d is not None:
        return dict(art=sw.BOHRUNG, anzahl=1, d=_zahl(d), x=_zahl(mx), y=_zahl(my))
    return dict(art=sw.POLYGON, anzahl=1, x=_zahl(mx), y=_zahl(my),
                punkte="; ".join(f"{_zahl(x - mx):g},{_zahl(y - my):g}" for x, y in pk))


# ------------------------------------------------------------------------------------------- Skalieren
MASSE = ("d", "D", "l", "b", "h", "r", "laenge", "huelle", "eckradius", "hoehe")


def skalieren(z, faktor):
    """Konturzeile um den Faktor vergrößern bzw. verkleinern (um ihre Mitte; Lage, Seite und Tiefe bleiben). Maße,
    Polygonpunkte und echter Umriss werden gestreckt. ValueError bei Faktor <= 0 oder einer Art ohne Maße."""
    f = float(faktor)
    if not f > 0:
        raise ValueError("Skalieren: Der Faktor muss größer als 0 sein.")
    art = z.get("art")
    if art in (sw.V_AUSSCHNITT,) or z.get("knickrahmen"):
        raise ValueError(f"Skalieren: {art} hat seine Maße aus dem Profil und lässt sich nicht skalieren.")
    neu = dict(z)
    geaendert = False
    for k in MASSE:
        if k in z and z[k] not in (None, ""):
            try:
                neu[k] = _zahl(float(z[k]) * f, 3)
                geaendert = True
            except (TypeError, ValueError):
                pass
    for k in ("punkte", "eckpunkte"):
        if z.get(k):
            roh = sw.punkte_roh(z[k])
            neu[k] = "; ".join(f"{_zahl(x * f, 3):g},{_zahl(y * f, 3):g}" + (f",{b:g}" if b else "")
                               for x, y, b in roh)       # Bulge bleibt: Bogen bleibt Bogen
            geaendert = True
    if z.get("umriss"):
        neu["umriss"] = [[_zahl(float(a) * f, 3), _zahl(float(b) * f, 3)] for a, b in z["umriss"]]
        geaendert = True
    if not geaendert:
        raise ValueError(f"Skalieren: {art or 'Diese Zeile'} hat keine Maße zum Skalieren.")
    return neu
