"""Durchdringung Rohr an Rohr (Plan 3D-Editor G2): Schnittkurve, wenn ein Rohr schräg und mit Versatz auf ein
Gegenrohr gesetzt wird (Ende) oder ein Gegenrohr durch die Wand des Rohrs geht (Durchbruch).

Beide Rohre sind gerade Prismen mit Rund- oder Rechteckquerschnitt (Rechteck mit Eckradius außen). Lage:
- Rohrachse = z, das Rohr kommt von z < 0 und endet am Gegenrohr.
- Die Achse des Gegenrohrs liegt in der x-z-Ebene unter dem Winkel alpha zur Rohrachse (90° = rechtwinklig) und ist
  um den Versatz e in y verschoben (y steht senkrecht auf beiden Achsen).
- Querschnittsmaße je Rohr: quer = Maß in y (bei beiden Rohren dieselbe Richtung), tief = das andere Maß.

Die Schnittkurve ist eine Kurve auf beiden Außenflächen zugleich; ihre Länge ist deshalb für „Ende“ (Schnitt am Rohr)
und „Durchbruch“ (Loch im Gegenrohr) dieselbe Rechnung mit vertauschten Rollen. Ein rechtwinkliger Rundrohr-Stoß ohne
Versatz ergibt genau schneidweg.sattel(d, D).
"""
import math

RUND, RECHTECK = "rund", "rechteck"
SCHRITTE = 720


class Querschnitt:
    """Außenquerschnitt: rund (Ø d) oder rechteckig (quer × tief, Eckradius r außen)."""
    __slots__ = ("form", "quer", "tief", "r")

    def __init__(self, form, quer, tief=None, r=0.0):
        self.form = RUND if form in (RUND, "Rundrohr") else RECHTECK
        self.quer = float(quer)
        self.tief = float(tief if tief not in (None, "") else quer)
        self.r = self.quer / 2 if self.form == RUND else max(0.0, min(float(r or 0), self.quer / 2, self.tief / 2))
        if self.quer <= 0 or self.tief <= 0:
            raise ValueError("Durchdringung: Querschnitt braucht Maße größer 0.")
        if self.form == RUND:
            self.tief = self.quer

    def umriss(self, schritte=SCHRITTE):
        """Punkte (tief-Richtung x, quer-Richtung y) des Umrisses, gleichmäßig über den Umfang."""
        if self.form == RUND:
            r = self.quer / 2
            return [(r * math.cos(2 * math.pi * i / schritte), r * math.sin(2 * math.pi * i / schritte))
                    for i in range(schritte)]
        a, b, r = self.tief / 2 - self.r, self.quer / 2 - self.r, self.r
        gerade = 4 * (a + b)
        bogen = 2 * math.pi * r
        umfang = gerade + bogen
        punkte = []
        # Ecken (Mittelpunkte) gegen den Uhrzeigersinn, je Ecke: Kante davor, Viertelbogen
        ecken = ((a, b, 0.0), (-a, b, math.pi / 2), (-a, -b, math.pi), (a, -b, 1.5 * math.pi))
        abschnitte = []
        for i, (cx, cy, w0) in enumerate(ecken):
            nx, ny, _ = ecken[(i + 1) % 4]
            abschnitte.append(("bogen", cx, cy, w0, math.pi / 2 * r))
            abschnitte.append(("kante", cx + r * math.cos(w0 + math.pi / 2), cy + r * math.sin(w0 + math.pi / 2),
                               nx + r * math.cos(w0 + math.pi / 2), ny + r * math.sin(w0 + math.pi / 2),
                               math.dist((cx, cy), (nx, ny))))
        for i in range(schritte):
            s = umfang * i / schritte
            for ab in abschnitte:
                lg = ab[-1]
                if s <= lg or ab is abschnitte[-1]:
                    t = s / lg if lg > 1e-12 else 0.0
                    if ab[0] == "bogen":
                        _, cx, cy, w0, _ = ab
                        w = w0 + t * math.pi / 2
                        punkte.append((cx + r * math.cos(w), cy + r * math.sin(w)))
                    else:
                        _, x0, y0, x1, y1, _ = ab
                        punkte.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
                    break
                s -= lg
        return punkte

    def halbe_tiefe(self, quer):
        """Halbe Ausdehnung in tief-Richtung an der Stelle quer (Abstand von der Mitte in quer-Richtung) oder None,
        wenn die Stelle außerhalb liegt."""
        q = abs(quer)
        if q > self.quer / 2 + 1e-9:
            return None
        if self.form == RUND:
            r = self.quer / 2
            return math.sqrt(max(r * r - q * q, 0.0))
        gerade = self.quer / 2 - self.r
        if q <= gerade:
            return self.tief / 2
        d = q - gerade
        return self.tief / 2 - self.r + math.sqrt(max(self.r * self.r - d * d, 0.0))


def kurve(rohr, gegen, alpha=90.0, versatz=0.0, schritte=SCHRITTE):
    """Schnittkurve am Ende des Rohrs: Punkte (x, y, z) im Rohr-System (z = Abstand vom Kreuzungspunkt der Achsen,
    negativ = zum Rohr hin). alpha in Grad (Winkel zwischen den Achsen, 90 = rechtwinklig)."""
    a = math.radians(float(alpha))
    sa, ca = math.sin(a), math.cos(a)
    if sa < math.sin(math.radians(10)):
        raise ValueError("Durchdringung: Winkel zwischen den Rohren mindestens 10°.")
    punkte = []
    for x, y in rohr.umriss(schritte):
        h = gegen.halbe_tiefe(y - versatz)
        if h is None:
            raise ValueError("Durchdringung: Rohr ragt seitlich über das Gegenrohr hinaus (Gegenrohr zu klein oder "
                             "Versatz zu groß).")
        # Abstand quer zur Gegenrohrachse in der x-z-Ebene: x cos α − z sin α = h (Seite zum Rohr hin)
        punkte.append((x, y, (x * ca - h) / sa))
    return punkte


def _laenge(punkte):
    return sum(math.dist(punkte[i - 1], punkte[i]) for i in range(len(punkte)))


def ende(rohr, gegen, alpha=90.0, versatz=0.0):
    """Ende des Rohrs auf dem Gegenrohr: dict(laenge Schnittlänge [mm], tiefe = Länge des Ausschnitts längs
    (längste minus kürzeste Stelle) [mm], kurve)."""
    k = kurve(rohr, gegen, alpha, versatz)
    zs = [p[2] for p in k]
    return dict(laenge=_laenge(k), tiefe=max(zs) - min(zs), kurve=k)


def durchbruch(rohr, gegen, alpha=90.0, versatz=0.0, durchgehend=False):
    """Loch im Rohr, durch das ein Gegenrohr geht bzw. auf dem es endet: dict(laenge Schnittlänge [mm] (beide
    Wände bei durchgehend), einstiche, huelle = größte Ausdehnung des Lochs [mm], kurve)."""
    k = kurve(gegen, rohr, alpha, versatz)
    n = 2 if durchgehend else 1
    # Ausdehnung des Lochs auf dem Rohr: längs (Achse des Rohrs) aus der Projektion der Kurve
    a = math.radians(float(alpha))
    # die Kurve liegt im System des Gegenrohrs, die Rohrachse darin in Richtung (sin α, 0, cos α)
    laengs = [p[0] * math.sin(a) + p[2] * math.cos(a) for p in k]
    quer = [p[1] for p in k]
    huelle = max(max(laengs) - min(laengs), max(quer) - min(quer))
    return dict(laenge=_laenge(k) * n, einstiche=n, huelle=huelle, kurve=k)


# ---------------------------------------------------------------------- im Rohr-Editor (3E-7)
# Gegenrohr am Ende (Eingabe des Endes 'gegen'): dict(d = Ø bzw. Breite quer, t = Tiefe (leer/0 = rund), r =
# Eckradius, winkel = Abweichung der Achsen von rechtwinklig [°] (+ = länger zur Seite +x), versatz [mm] quer,
# lage = WAAGERECHT (Achse des Gegenrohrs liegt quer in u, Sattel in der Seitenansicht) oder SENKRECHT (Achse in v),
# drehung = nur Rundrohr: Achse des Gegenrohrs um die Rohrachse gedreht [°, von u zu v], z. B. aus dem STEP-Import
# (Rohranschluss in beliebiger Lage am Umfang, Patrick 30.10.2026)).
WAAGERECHT, SENKRECHT = "waagerecht", "senkrecht"
LAGEN = (WAAGERECHT, SENKRECHT)
GESCHLOSSEN = ("Rundrohr", "Quadratrohr", "Rechteckrohr")


def _f(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def gegen_lesen(e):
    """Gegenrohr eines Endes als dict oder None; die alte Eingabe sattel (Ø, rechtwinklig auf Rundrohr) zählt als
    rundes Gegenrohr waagerecht ohne Versatz."""
    e = e or {}
    g = e.get("gegen")
    if isinstance(g, dict) and _f(g.get("d")) > 0:
        return g
    if _f(e.get("sattel")) > 0:
        return dict(d=_f(e["sattel"]))
    return None


def querschnitt_gegen(g):
    t = _f(g.get("t"))
    return Querschnitt(RECHTECK if t else RUND, _f(g.get("d")), t or None, _f(g.get("r")))


def querschnitt_rohr(qs, lage=WAAGERECHT):
    """Querschnitt des Rohrs (skizze.Querschnitt) im System der Durchdringung: x = Richtung der Achse des
    Gegenrohrs (waagerecht u, senkrecht v), y = quer dazu."""
    if qs.r:
        return Querschnitt(RUND, 2 * qs.r)
    if lage == SENKRECHT:
        return Querschnitt(RECHTECK, qs.B, qs.H, qs.radius)
    return Querschnitt(RECHTECK, qs.H, qs.B, qs.radius)


def _alpha(g):
    w = _f(g.get("winkel"))
    if abs(w) > 80:
        raise ValueError("Gegenrohr: Winkel höchstens 80° (0 = rechtwinklig).")
    return 90.0 - w


def _xy(u, v, lage):
    return (v, u) if lage == SENKRECHT else (u, v)


def drehung(qs, g):
    """Drehung der Gegenrohrachse um die Rohrachse [rad]; nur beim Rundrohr (sonst 0)."""
    return math.radians(_f(g.get("drehung"))) if qs.r else 0.0


def _ins_gegen(u, v, d):
    """Punkt (u, v) des Querschnitts in das um d gedrehte System der Gegenrohrachse."""
    if not d:
        return u, v
    c, s = math.cos(d), math.sin(d)
    return u * c + v * s, -u * s + v * c


def _aus_gegen(u, v, d):
    if not d:
        return u, v
    c, s = math.cos(d), math.sin(d)
    return u * c - v * s, u * s + v * c


def ende_gegen(qs, g):
    """Ende auf dem Gegenrohr g: dict(laenge, tiefe, kurve) wie ende(); ValueError bei unmöglichen Maßen."""
    if qs.form not in GESCHLOSSEN:
        raise ValueError("Gegenrohr nur bei Rund-, Quadrat- und Rechteckrohr.")
    return ende(querschnitt_rohr(qs, g.get("lage")), querschnitt_gegen(g), _alpha(g), _f(g.get("versatz")))


_SPITZE = {}


def schnitt_x(qs, g, u, v):
    """Wie skizze.schnitt_x für ein Ende auf dem Gegenrohr g: Abstand der Schnittkante an (u, v) hinter der Spitze
    [mm, ≥ 0]. Die Spitze (längste Stelle) kommt aus dem Außenumriss; Punkte quer außerhalb des Gegenrohrs bekommen
    die Kante am Rand."""
    lage = g.get("lage")
    gq = querschnitt_gegen(g)
    a = math.radians(_alpha(g))
    sa, ca = math.sin(a), math.cos(a)
    e = _f(g.get("versatz"))

    def z(x, y):
        h = gq.halbe_tiefe(max(-gq.quer / 2, min(gq.quer / 2, y - e)))
        return (x * ca - (h or 0.0)) / sa
    schl = (qs.form, qs.B, qs.H, qs.r, qs.radius, tuple(sorted((k, str(v_)) for k, v_ in g.items())))
    if schl not in _SPITZE:
        r = querschnitt_rohr(qs, lage)
        _SPITZE[schl] = max(z(x, y) for x, y in r.umriss(360))
        if len(_SPITZE) > 200:
            _SPITZE.pop(next(iter(_SPITZE)))
    return max(0.0, _SPITZE[schl] - z(*_xy(*_ins_gegen(u, v, drehung(qs, g)), lage)))


def gegen_koerper(qs, g, L, seite, laenge=None, n=48):
    """Hilfskörper Gegenrohr für die 3D-Ansicht: Linienzüge [(x längs ab Ende A, u, v)] – zwei Umrissringe und
    Längslinien, Achse durch den Kreuzungspunkt an der Spitze des Endes."""
    lage = g.get("lage")
    gq = querschnitt_gegen(g)
    a = math.radians(_alpha(g))
    e = _f(g.get("versatz"))
    r = querschnitt_rohr(qs, lage)
    lg = laenge or max(3 * max(gq.quer, gq.tief), 2.5 * max(r.quer, r.tief))
    # Kreuzungspunkt der Achsen liegt im System des Rohrs bei z = 0, die Spitze des Endes bei z_max
    sa, ca = math.sin(a), math.cos(a)
    z_max = max((x * ca - (gq.halbe_tiefe(max(-gq.quer / 2, min(gq.quer / 2, y - e))) or 0.0)) / sa
                for x, y in r.umriss(120))
    achse = (sa, ca)                    # Richtung der Gegenrohrachse in (x, z)
    quer_n = (ca, -sa)                  # tief-Richtung des Gegenrohrs in (x, z)
    ringe = []
    for t in (-lg / 2, lg / 2):
        ring = []
        for gx, gy in gq.umriss(n):     # gx = tief, gy = quer (y)
            x = t * achse[0] + gx * quer_n[0]
            zz = t * achse[1] + gx * quer_n[1]
            ring.append((x, gy + e, zz))
        ringe.append(ring + ring[:1])
    zuege = list(ringe)
    for i in range(0, n, max(1, n // 8)):
        zuege.append([ringe[0][i], ringe[1][i]])
    out = []
    dr = drehung(qs, g)
    for zug in zuege:
        pts = []
        for x, y, zz in zug:
            u, v = _aus_gegen(*_xy(x, y, lage), dr)      # (x, y) ↔ (u, v) ist symmetrisch
            x_teil = z_max - zz         # < 0 = hinter der Spitze, außerhalb des Teils
            pts.append((x_teil if seite == "a" else L - x_teil, u, v))
        out.append(pts)
    return out


def durchbruch_umriss(qs, seite, g, versatz=0.0, schritte=180):
    """Loch für ein Gegenrohr g (d quer, t längs zum Rohr, winkel) durch die Wand 'seite' des Rohrs: dict(laenge,
    huelle, umriss [[dx längs, dq am Umfang]] um den Kreuzungspunkt der Achsen). versatz = Lage der Gegenrohrachse
    quer zur Mitte der Fläche (Rundrohr: zur Rohrachse) [mm]."""
    if qs.form not in GESCHLOSSEN:
        raise ValueError("Durchbruch nur bei Rund-, Quadrat- und Rechteckrohr.")
    gq = querschnitt_gegen(g)
    if qs.r:
        rohr = Querschnitt(RUND, 2 * qs.r)
    else:
        f = qs.flaeche(seite) or qs.flaechen[0]
        senkrecht = abs(f.n[1]) > 0.5          # oben/unten: Fläche quer = B, Tiefe = H
        rohr = Querschnitt(RECHTECK, qs.B if senkrecht else qs.H, qs.H if senkrecht else qs.B, qs.radius)
    alpha = _alpha(g)
    b = durchbruch(rohr, gq, alpha, -versatz)
    a = math.radians(alpha)
    k = b["kurve"]
    schritt = max(1, len(k) // schritte)
    umriss = []
    for x, y, z in k[::schritt]:
        dx = -(x * math.sin(a) + z * math.cos(a))      # + Winkel = Gegenrohr außen zu Ende B geneigt
        if qs.r:
            R = qs.r
            dq = R * (math.asin(max(-1.0, min(1.0, (y + versatz) / R))) - math.asin(max(-1.0, min(1.0, versatz / R))))
        else:
            dq = y
        umriss.append([round(dx, 3), round(dq, 3)])
    return dict(laenge=b["laenge"], huelle=b["huelle"], umriss=umriss)
