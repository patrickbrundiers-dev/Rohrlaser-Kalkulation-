"""Ansichten einer DXF-Zeichnung erkennen (Plan DXF-Import verbessern, Patrick 25.10.2026 „a a a a a a“; gemeinsam
mit dem Rohr-Import 3E-12).

- gruppen: Linien und Kreise, die sich berühren oder fast berühren, bilden eine Ansicht (Hüllrechteck je Gruppe).
- Isometrie: viele Kanten unter 30° und 150° (beide Richtungen), keine Abwicklung.
- Rohr: ein Querschnitt mit gleichmäßiger Wand (Außen- und Innenkontur, Wand auf allen Seiten gleich) und eine
  weitere Ansicht, deren schmale Seite so breit ist wie der Querschnitt -> Rohrzeichnung, kein Blech.
- Seitenansicht eines Blechs: schmaler Streifen, eine Seite so lang wie eine Seite einer anderen Ansicht, die andere
  Seite = Blechdicke.

Nur Rechnung ohne Oberfläche; Eingaben sind Strecken [(p, q)] und Kreise [(Mitte, Radius)] in mm.
"""
import math

ISO_WINKEL = (30.0, 150.0)  # Richtungen der Kanten einer Isometrie [°] (gegen die Waagerechte)
ISO_TOL = 4.0               # so genau [°]
ISO_ANTEIL = 0.3            # mindestens so viel der Linienlänge in diesen Richtungen, je Richtung ein Drittel davon
MASS_TOL = 0.02             # Seiten gelten als gleich lang bei 2 % Abweichung (mindestens 0,2 mm)
DICKE_MAX = 30.0            # Seitenansicht eines Blechs: schmale Seite höchstens so dick [mm]


class Ansicht:
    """Gruppe von Linien und Kreisen: bb = (x0, y0, x1, y1), strecken/kreise = Indizes der Eingabe, iso."""

    def __init__(self, bb, strecken, kreise, iso):
        self.bb, self.strecken, self.kreise, self.iso = bb, strecken, kreise, iso
        self.seitenansicht = None            # Dicke [mm], wenn Seitenansicht eines Blechs

    @property
    def breite(self):
        return self.bb[2] - self.bb[0]

    @property
    def hoehe(self):
        return self.bb[3] - self.bb[1]

    @property
    def kurz(self):
        return min(self.breite, self.hoehe)

    @property
    def lang(self):
        return max(self.breite, self.hoehe)

    def enthaelt(self, p, tol=0.5):
        return self.bb[0] - tol <= p[0] <= self.bb[2] + tol and self.bb[1] - tol <= p[1] <= self.bb[3] + tol


def gleich(a, b):
    return abs(a - b) <= max(0.2, MASS_TOL * max(abs(a), abs(b)))


def _bb_strecke(p, q):
    return min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1])


def _bb_kreis(c, r):
    return c[0] - r, c[1] - r, c[0] + r, c[1] + r


def _nah(a, b, d):
    return a[0] - d <= b[2] and b[0] - d <= a[2] and a[1] - d <= b[3] and b[1] - d <= a[3]


def gruppen(strecken, kreise, abstand=None):
    """[Ansicht] aus Strecken [(p, q)] und Kreisen [(c, r)]; zwei Elemente gehören zusammen, wenn ihre Hüllrechtecke
    höchstens abstand auseinander liegen (Vorgabe 1 % der Zeichnung, mindestens 1 mm)."""
    boxen = [_bb_strecke(p, q) for p, q in strecken] + [_bb_kreis(c, r) for c, r in kreise]
    if not boxen:
        return []
    x0, y0 = min(b[0] for b in boxen), min(b[1] for b in boxen)
    x1, y1 = max(b[2] for b in boxen), max(b[3] for b in boxen)
    d = abstand if abstand is not None else max(1.0, 0.01 * math.hypot(x1 - x0, y1 - y0))
    zelle = max(10 * d, 1e-6)
    eltern = list(range(len(boxen)))

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i

    raster = {}
    for i, b in enumerate(boxen):
        cx0, cy0 = int((b[0] - d - x0) // zelle), int((b[1] - d - y0) // zelle)
        cx1, cy1 = int((b[2] + d - x0) // zelle), int((b[3] + d - y0) // zelle)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                liste = raster.setdefault((cx, cy), [])
                for j in liste:
                    if wurzel(i) != wurzel(j) and _nah(b, boxen[j], d):
                        eltern[wurzel(i)] = wurzel(j)
                liste.append(i)
    gruppe = {}
    for i in range(len(boxen)):
        gruppe.setdefault(wurzel(i), []).append(i)
    n = len(strecken)
    out = []
    for idx in gruppe.values():
        bb = (min(boxen[i][0] for i in idx), min(boxen[i][1] for i in idx),
              max(boxen[i][2] for i in idx), max(boxen[i][3] for i in idx))
        st = [i for i in idx if i < n]
        out.append(Ansicht(bb, st, [i - n for i in idx if i >= n], ist_isometrie([strecken[i] for i in st])))
    return sorted(out, key=lambda a: (-a.bb[3], a.bb[0]))


def ist_isometrie(strecken):
    """Viele Kanten unter 30° und 150° (beide Richtungen kommen vor) -> isometrische Ansicht."""
    gesamt = 0.0
    je = [0.0, 0.0]
    for p, q in strecken:
        lg = math.dist(p, q)
        if lg < 1e-9:
            continue
        gesamt += lg
        w = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])) % 180
        for i, soll in enumerate(ISO_WINKEL):
            if abs(w - soll) <= ISO_TOL:
                je[i] += lg
    if gesamt <= 0:
        return False
    schraeg = je[0] + je[1]
    return schraeg >= ISO_ANTEIL * gesamt and min(je) >= schraeg / 6


def seitenansichten(ansichten):
    """Markiert Seitenansichten von Blechen (Ansicht.seitenansicht = Dicke): schmale Seite höchstens DICKE_MAX und
    höchstens ein Zehntel der langen, lange Seite gleich einer Seite einer größeren Ansicht."""
    for a in ansichten:
        if a.iso or a.kurz <= 0 or a.kurz > DICKE_MAX or a.kurz > 0.1 * a.lang:
            continue
        if any(b is not a and not b.iso and b.kurz > 3 * a.kurz and (gleich(a.lang, b.breite) or gleich(a.lang, b.hoehe))
               for b in ansichten):
            a.seitenansicht = round(a.kurz, 2)
    return ansichten


def rohr_querschnitt(aussen, innen):
    """Querschnitt eines Rohrs aus Außen- und Innenkontur (je dict(bb, rund)) -> dict(form, a, b, wand) oder None.
    Wand auf allen vier Seiten gleich, Innenkontur mittig, Wand höchstens ein Viertel der kleineren Seite."""
    ax0, ay0, ax1, ay1 = aussen["bb"]
    ix0, iy0, ix1, iy1 = innen["bb"]
    waende = (ix0 - ax0, ax1 - ix1, iy0 - ay0, ay1 - iy1)
    t = sum(waende) / 4
    a, b = ax1 - ax0, ay1 - ay0
    if t <= 0 or t > 0.25 * min(a, b) or any(abs(w - t) > max(0.05, 0.03 * t) for w in waende):
        return None
    if aussen.get("rund") and innen.get("rund"):
        return dict(form="Rundrohr", a=round(a, 2), b=round(a, 2), wand=round(t, 2))
    if gleich(a, b):
        return dict(form="Quadratrohr", a=round((a + b) / 2, 2), b=round((a + b) / 2, 2), wand=round(t, 2))
    return dict(form="Rechteckrohr", a=round(max(a, b), 2), b=round(min(a, b), 2), wand=round(t, 2))


def rohr_erkennen(querschnitte, ansichten):
    """Rohrzeichnung? querschnitte: [(Ansicht, dict aus rohr_querschnitt)]. Rohr, wenn eine andere Ansicht (keine
    Isometrie) so breit ist wie der Querschnitt und länger. -> dict(form, a, b, wand, laenge, text) oder None."""
    for ans, qs in querschnitte:
        seiten = (qs["a"], qs["b"])
        laengen = [b.lang for b in ansichten if b is not ans and not b.iso and b.lang > b.kurz * 1.2
                   and any(gleich(b.kurz, s) for s in seiten)]
        if laengen:
            laenge = round(max(laengen), 2)
            kurz = {"Rundrohr": "RR", "Quadratrohr": "QR", "Rechteckrohr": "RE"}[qs["form"]]
            mass = f"{_z(qs['a'])}" if qs["form"] == "Rundrohr" else f"{_z(qs['a'])} × {_z(qs['b'])}"
            return dict(qs, laenge=laenge, text=f"{kurz} {mass} × {_z(qs['wand'])}, Länge {_z(laenge)} mm")
    return None


def _z(v):
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")
