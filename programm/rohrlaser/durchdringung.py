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
