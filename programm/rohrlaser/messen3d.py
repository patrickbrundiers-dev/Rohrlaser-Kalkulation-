"""Messen mit exakten Kernwerten in allen 3D-Ansichten (Plan 3D-Ansicht 3E-11, M4, Patrick 24.10.2026 „alle a“).

Das Dreiecksnetz allein misst ungenau (ein Kreis ist ein Vieleck: Ø 8 wird 7,98). Deshalb kennt die Messung die
echte Geometrie:
- Kreise mit Mitte, Achse und Ø: aus den Eingaben (Netz 'geo', rohr3d/blech3d) oder, ohne Eingaben (STEP-Netz), aus
  dem Linienzug der Kontur eingepasst (Ausgleichskreis in seiner Ebene, nur wenn alle Punkte darauf liegen);
- Kanten (Geraden): Körperkanten und gerade Stücke der Konturen, zu ganzen Kanten zusammengesetzt;
- Ecken: Enden der Kanten;
- Flächen: Ebenen (Modell.ebenen) und der Mantel eines Rundrohrs (Achse = Rohrachse z).
Fangen in dieser Reihenfolge: Kreismitte (auch Konturmitte), Kantenmitte, Ecke, Punkt auf einer Linie, Fläche.

Koordinaten wie die Netze: z = längs (Rohrachse bzw. Kantlänge), x = quer (vorne = −x), y = hoch. Baugruppen liegen
in den Koordinaten der STEP-Datei (Netz 'global'): dann x, y, z.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout

KREISMITTE, KONTURMITTE, KANTENMITTE, ECKE, PUNKT, FLAECHE = ("Kreismitte", "Konturmitte", "Kantenmitte", "Ecke",
                                                             "Punkt", "Fläche")
FANG_PX = 14            # so nah [px] muss der Mauszeiger an einem Fangpunkt sein
LINIE_PX = 7            # Punkt auf einer Linie
PARALLEL = 0.5          # Grad: darunter gelten Kanten, Flächen und Achsen als parallel
NAMEN_ROHR = ("quer", "hoch", "längs")
NAMEN_GLOBAL = ("x", "y", "z")
MERKMAL_WERTE = (("d", "Ø"), ("D", "Senk-Ø"), ("l", "Länge"), ("lang", "Länge"), ("b", "Breite"), ("h", "Höhe"),
                 ("r", "Eckradius"), ("t", "Tiefe"), ("winkel", "Winkel"), ("x", "Lage x"), ("y", "Lage y"), ("q", "quer"))


def zahl(w, stellen=3):
    """Zahl mit fester Stellenzahl (Mess-Tafel: drei Nachkommastellen, „8,000“), ohne „-0,000“."""
    t = f"{w:.{stellen}f}"
    if t.lstrip("-").strip("0.") == "":
        t = t.lstrip("-")
    return t.replace(".", ",")


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    lg = math.sqrt(_dot(a, a))
    return (a[0] / lg, a[1] / lg, a[2] / lg) if lg > 1e-12 else None


def winkel_zwischen(a, b, gerichtet=False):
    """Winkel [°] zwischen zwei Richtungen (ungerichtet: 0..90°, z. B. Kanten und Achsen)."""
    c = _dot(a, b) / (math.sqrt(_dot(a, a) * _dot(b, b)) or 1.0)
    c = max(-1.0, min(1.0, c if gerichtet else abs(c)))
    return math.degrees(math.acos(c))


# ---------------------------------------------------------------- Kreis aus Punkten
def kreis_einpassen(pk):
    """Ausgleichskreis durch einen geschlossenen Linienzug (Ende beim Anfang): dict(m, n, d, abw) oder None
    (kein Kreis). abw = größte Abweichung eines Punkts vom Kreis [mm]."""
    if len(pk) < 6:
        return None
    schritt = max(math.dist(a, b) for a, b in zip(pk, pk[1:]))
    bogen = math.dist(pk[0], pk[-1]) > 2 * schritt          # offen: Bogen (z. B. Ende eines Langlochs)
    if not bogen and len(pk) < 9:
        return None
    ring = pk[:-1] if math.dist(pk[0], pk[-1]) < 1e-6 else list(pk)
    s = [0.0, 0.0, 0.0]                 # Normale nach Newell (auch für leicht gewölbte Ringe stabil)
    for a, b in zip(ring, ring[1:] + ring[:1]):         # offener Bogen: über die Sehne geschlossen
        s[0] += (a[1] - b[1]) * (a[2] + b[2])
        s[1] += (a[2] - b[2]) * (a[0] + b[0])
        s[2] += (a[0] - b[0]) * (a[1] + b[1])
    n = _norm(s)
    if n is None:
        return None
    c = tuple(sum(q[i] for q in ring) / len(ring) for i in range(3))
    e1 = _norm(_kreuz(n, (1.0, 0.0, 0.0)) if abs(n[0]) < 0.9 else _kreuz(n, (0.0, 1.0, 0.0)))
    e2 = _kreuz(n, e1)
    uv = [(_dot(_sub(q, c), e1), _dot(_sub(q, c), e2)) for q in ring]
    # Kasa: x² + y² + D x + E y + F = 0 (Normalgleichungen 3 × 3)
    m = [[0.0] * 4 for _ in range(3)]
    for x, y in uv:
        z = x * x + y * y
        zeile = (x, y, 1.0)
        for i in range(3):
            for j in range(3):
                m[i][j] += zeile[i] * zeile[j]
            m[i][3] -= zeile[i] * z
    try:
        for i in range(3):              # Gauß mit Pivot
            p = max(range(i, 3), key=lambda r: abs(m[r][i]))
            m[i], m[p] = m[p], m[i]
            if abs(m[i][i]) < 1e-12:
                return None
            for r in range(3):
                if r != i:
                    f = m[r][i] / m[i][i]
                    m[r] = [m[r][k] - f * m[i][k] for k in range(4)]
        dd, ee, ff = (m[i][3] / m[i][i] for i in range(3))
    except ZeroDivisionError:
        return None
    mx, my = -dd / 2, -ee / 2
    r2 = mx * mx + my * my - ff
    if r2 <= 1e-12:
        return None
    r = math.sqrt(r2)
    abw = max(abs(math.hypot(x - mx, y - my) - r) for x, y in uv)
    tiefe = max(abs(_dot(_sub(q, c), n)) for q in ring)
    if abw > min(0.05, max(0.02, 0.004 * r)) or tiefe > max(0.05, 0.02 * r):
        return None
    if bogen and sum(math.dist(a, b) for a, b in zip(pk, pk[1:])) / r < math.radians(60):
        return None                     # zu kurzer Bogen: Mitte unsicher
    mitte = tuple(c[i] + e1[i] * mx + e2[i] * my for i in range(3))
    return dict(m=mitte, n=n, d=2 * r, abw=abw, bogen=bogen)


def stellen_fuer(abw):
    """Nachkommastellen, die eine eingepasste Größe hergibt (Netze sind auf 0,001 bzw. 0,01 mm gerundet)."""
    return 3 if abw < 0.0015 else 2 if abw < 0.015 else 1


# ---------------------------------------------------------------- Geometrie eines Modells
class Geometrie:
    """Fangbare Elemente eines ansicht3d.Modell (einmal je Modell gerechnet, Modell.geometrie())."""

    def __init__(self, modell, netz=None):
        netz = netz or {}
        geo = netz.get("geo") or {}
        self.modell = modell
        self.namen = NAMEN_GLOBAL if netz.get("global") else NAMEN_ROHR
        self.merkmale = geo.get("merkmale") or {}
        self.rohr = geo.get("rohr") or {}
        self.kreise = [dict(m=tuple(k["m"]), n=tuple(k["n"]), d=float(k["d"]), id=k.get("id"), stellen=3)
                       for k in geo.get("kreise") or ()]
        self.mitten = [dict(p=tuple(k["p"]), n=tuple(k.get("n") or (0, 1, 0)), id=k.get("id"))
                       for k in geo.get("mitten") or ()]
        exakt = {k["id"] for k in self.kreise} | {k["id"] for k in self.mitten}
        # Genauigkeit der Netzpunkte: STEP-Netze sind auf 0,01 mm gerundet, dann höchstens zwei Stellen
        p = netz.get("p") or []
        self.raster = 3 if any(abs(c * 100 - round(c * 100)) > 1e-6 for c in p[:3000]) else 2
        segmente = []               # [(a, b, Linienzug-Nr.)] für Kanten
        for art, zuege in (netz.get("l") or {}).items():
            kennung = (netz.get("li") or {}).get(art) or []
            for nr, zug in enumerate(zuege):
                pk = [tuple(zug[i:i + 3]) for i in range(0, len(zug) - 2, 3)]
                kid = kennung[nr] if nr < len(kennung) else None
                if art in ("K", "G", "EA", "EB") and kid not in exakt and len(pk) >= 6:
                    k = kreis_einpassen(pk)
                    if k is not None:
                        d = self._rohr_d(k["d"])         # Rohrende: Ø genau aus dem Profil
                        self.kreise.append(dict(m=k["m"], n=k["n"], d=d, id=kid, bogen=k["bogen"],
                                                stellen=3 if d != k["d"] else min(self.raster,
                                                                                 stellen_fuer(k["abw"]))))
                        if not k["bogen"]:
                            continue
                if art in ("K", "G", "EA", "EB", "B", "HK"):
                    segmente += [(a, b) for a, b in zip(pk, pk[1:]) if math.dist(a, b) > 1e-6]
        segmente += [(a, b) for a, b, _ in modell.kanten()]
        self.geraden = _geraden(segmente)
        ecken = {}
        for g in self.geraden:
            for q in (g["a"], g["b"]):
                ecken.setdefault(tuple(round(c, 3) for c in q), q)
        self.ecken = list(ecken.values())

    def _rohr_d(self, d):
        """Eingepasster Ø: am Rohr (Außen- bzw. Innen-Ø) den genauen Wert aus dem Profil."""
        soll = self.rohr.get("d")
        if soll:
            for w in (soll, soll - 2 * (self.rohr.get("t") or 0)):
                if abs(d - w) < 0.01:
                    return float(w)
        return d

    # ------------------------------------------------------------ Flächen
    def flaeche(self, dreieck_nr, punkt):
        """Fläche zum getroffenen Dreieck: dict(typ ebene|zylinder|flaeche, …)."""
        mo = self.modell
        nummer, ebenen = mo.ebenen()
        i, j, k, _, n = mo.dreiecke[dreieck_nr]
        z = None if self.namen == NAMEN_GLOBAL else self._zylinder(mo.punkte[i], mo.punkte[j], mo.punkte[k], n)
        if z is not None:
            return z
        if dreieck_nr < len(nummer):
            e = ebenen[nummer[dreieck_nr]]
            if len(e["dreiecke"]) >= 2 or e["flaeche"] > 25:
                return dict(typ="ebene", n=tuple(e["n"]), d=e["d"], p=punkt, flaeche=e["flaeche"])
        return dict(typ="flaeche", n=n, p=punkt)

    def _zylinder(self, a, b, c, n):
        """Mantel um die Rohrachse (z): Normale radial, alle Ecken gleich weit von der Achse."""
        if abs(n[2]) > 1e-3:
            return None
        rs = [math.hypot(q[0], q[1]) for q in (a, b, c)]
        r = sum(rs) / 3
        if r < 1e-6 or max(rs) - min(rs) > max(0.01, 1e-4 * r):
            return None
        mx, my = (a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3
        lg = math.hypot(mx, my) or 1.0
        if abs(abs(n[0] * mx / lg + n[1] * my / lg) - 1.0) > 0.02:
            return None
        return dict(typ="zylinder", p=(0.0, 0.0, 0.0), r=(0.0, 0.0, 1.0), d=self._rohr_d(2 * r), stellen=3)

    # ------------------------------------------------------------ Fangen
    def fangen(self, bild, x, y, flaeche_treffer=None, mit_flaeche=True):
        """Fangpunkt beim Pixel (x, y): dict(art, punkt, element) oder None. bild: Modellpunkt -> (x, y, Tiefe);
        flaeche_treffer(bild, x, y) -> (Dreieck-Nr., Punkt) oder None."""
        def naechster(kandidaten, radius=FANG_PX):
            beste = None
            for p, el in kandidaten:
                px, py, t = bild(p)
                d = math.hypot(px - x, py - y)
                if d <= radius and (beste is None or d - t * 1e-3 < beste[0]):
                    beste = (d - t * 1e-3, p, el)
            return beste
        b = naechster((k["m"], dict(k, typ="kreis")) for k in self.kreise)
        if b is not None:
            return dict(art=KREISMITTE, punkt=b[1], element=b[2])
        b = naechster((k["p"], dict(k, typ="mitte")) for k in self.mitten)
        if b is not None:
            return dict(art=KONTURMITTE, punkt=b[1], element=b[2])
        b = naechster((g["mitte"], dict(g, typ="gerade")) for g in self.geraden)
        if b is not None:
            return dict(art=KANTENMITTE, punkt=b[1], element=b[2])
        b = naechster((q, None) for q in self.ecken)
        if b is not None:
            return dict(art=ECKE, punkt=b[1], element=None)
        beste = None                    # Punkt auf einer Linie (Kontur oder Kante)
        for g in self.geraden:
            pa, pb = bild(g["a"]), bild(g["b"])
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            lg = dx * dx + dy * dy
            t = 0.0 if lg < 1e-9 else max(0.0, min(1.0, ((x - pa[0]) * dx + (y - pa[1]) * dy) / lg))
            d = math.hypot(pa[0] + t * dx - x, pa[1] + t * dy - y)
            if d <= LINIE_PX and (beste is None or d < beste[0]):
                beste = (d, tuple(g["a"][i] + t * (g["b"][i] - g["a"][i]) for i in range(3)), g)
        if beste is not None:
            return dict(art=PUNKT, punkt=beste[1], element=dict(beste[2], typ="gerade"))
        if mit_flaeche and flaeche_treffer is not None:
            tr = flaeche_treffer(bild, x, y)
            if tr is not None:
                nr, p = tr
                return dict(art=FLAECHE, punkt=p, element=self.flaeche(nr, p))
        return None

    # ------------------------------------------------------------ Texte
    def lage(self, p):
        """„längs 100,000 · quer 0,000 · hoch 20,000“ (Rohrnetz) bzw. „x … · y … · z …“."""
        q, h, l_ = self.namen
        if self.namen == NAMEN_GLOBAL:
            return f"x {zahl(p[0])} · y {zahl(p[1])} · z {zahl(p[2])}"
        return f"{l_} {zahl(p[2])} · {q} {zahl(-p[0])} · {h} {zahl(p[1])}"

    def richtung(self, n):
        """Richtung als Text: Achse, wenn sie mit einer Hauptachse zusammenfällt, sonst Winkel."""
        q, h, l_ = self.namen
        for i, name in ((2, l_), (0, q), (1, h)):
            if abs(abs(n[i]) - 1.0) < 1e-6:
                return name
        return f"{l_} {zahl(winkel_zwischen(n, (0, 0, 1)), 1)}° · {h} {zahl(winkel_zwischen(n, (0, 1, 0)), 1)}°"

    def merkmal_text(self, kid):
        m = self.merkmale.get(kid) if kid else None
        if not m:
            return ""
        teile = [str(m.get("art") or "")]
        for k, name in MERKMAL_WERTE:
            v = m.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v:
                teile.append(f"{name} {zahl(v)}" + ("°" if k == "winkel" else ""))
        if m.get("seite"):
            teile.append(f"Seite {m['seite']}")
        return " · ".join(t for t in teile if t)

    def kernwerte(self, t):
        """Kernwerte eines Fangpunkts als Zeilen (Mess-Tafel, erster Klick)."""
        el = t.get("element") or {}
        typ = el.get("typ")
        zeilen = []
        if typ == "kreis":
            st = el.get("stellen", 3)
            groesse = f"Bogen R {zahl(el['d'] / 2, st)} mm" if el.get("bogen") else f"Kreis Ø {zahl(el['d'], st)} mm"
            zeilen.append(groesse + ("" if st == 3 else " (aus dem Netz eingepasst)"))
            zeilen.append(f"Mitte: {self.lage(el['m'])}")
            zeilen.append(f"Achse: {self.richtung(el['n'])}")
        elif typ == "mitte":
            zeilen.append(f"Konturmitte: {self.lage(el['p'])}")
        elif typ == "gerade":
            zeilen.append(f"Kante Länge {zahl(math.dist(el['a'], el['b']))} mm, Richtung {self.richtung(el['r'])}")
            zeilen.append(f"von {self.lage(el['a'])}")
            zeilen.append(f"bis {self.lage(el['b'])}")
            if t["art"] == PUNKT:
                zeilen.append(f"Punkt: {self.lage(t['punkt'])}")
        elif typ == "ebene":
            zeilen.append(f"Ebene Fläche, Normale {self.richtung(el['n'])}, {zahl(el['flaeche'], 1)} mm²")
            zeilen.append(f"Punkt: {self.lage(t['punkt'])}")
        elif typ == "zylinder":
            zeilen.append(f"Rohrmantel Ø {zahl(el['d'])} mm, Achse {self.richtung(el['r'])}")
            zeilen.append(f"Punkt: {self.lage(t['punkt'])}")
        else:
            zeilen.append(f"{t['art']}: {self.lage(t['punkt'])}")
        text = self.merkmal_text(el.get("id"))
        if text:
            zeilen.append(text)
        return zeilen

    def vergleich(self, t1, t2):
        """Ergebnis zweier Fangpunkte: (Hauptwert als Text, Zeilen)."""
        a, b = t1["punkt"], t2["punkt"]
        # Punkt auf einer Linie: nur der Punkt zählt (die Kante dazu steht in den Kernwerten)
        e1 = (t1.get("element") or {}) if t1["art"] != PUNKT else {}
        e2 = (t2.get("element") or {}) if t2["art"] != PUNKT else {}
        typ1, typ2 = e1.get("typ"), e2.get("typ")
        art = {KREISMITTE: "Mitte", KONTURMITTE: "Mitte", KANTENMITTE: "Kantenmitte", ECKE: "Ecke", PUNKT: "Punkt",
               FLAECHE: "Fläche"}
        q, h, l_ = self.namen
        d = _sub(b, a)
        haupt = f"Abstand {zahl(math.dist(a, b))} mm"
        zeilen = [f"{art[t1['art']]} – {art[t2['art']]}: {haupt}"]
        if self.namen == NAMEN_GLOBAL:
            zeilen.append(f"Δx {zahl(abs(d[0]))} · Δy {zahl(abs(d[1]))} · Δz {zahl(abs(d[2]))}")
        else:
            zeilen.append(f"Δ {l_} {zahl(abs(d[2]))} · Δ {q} {zahl(abs(d[0]))} · Δ {h} {zahl(abs(d[1]))}")
        flaeche = {"ebene"}
        richtung1, richtung2 = _richtung(e1), _richtung(e2)
        if typ1 in flaeche and typ2 in flaeche:
            w = winkel_zwischen(e1["n"], e2["n"])
            if w < PARALLEL:
                haupt = f"Abstand Fläche–Fläche {zahl(abs(_dot(_sub(b, a), e1['n'])))} mm"
            else:
                haupt = f"Winkel Fläche–Fläche {zahl(w)}°"
            zeilen.insert(0, haupt)
        elif typ1 in flaeche or typ2 in flaeche:
            e, p, andere = (e1, b, e2) if typ1 in flaeche else (e2, a, e1)
            if andere.get("typ") == "gerade":
                w = 90 - winkel_zwischen(e["n"], andere["r"])
                if w < PARALLEL:
                    haupt = f"Abstand Kante–Fläche {zahl(abs(_dot(_sub(p, e['p']), e['n'])))} mm"
                else:
                    haupt = f"Winkel Kante–Fläche {zahl(w)}°"
            else:
                haupt = f"Abstand Punkt–Fläche (senkrecht) {zahl(abs(_dot(_sub(p, e['p']), e['n'])))} mm"
            zeilen.insert(0, haupt)
        elif richtung1 is not None and richtung2 is not None:
            namen = {"gerade": "Kante", "kreis": "Achse", "zylinder": "Achse"}
            n1, n2 = namen.get(typ1, "Achse"), namen.get(typ2, "Achse")
            w = winkel_zwischen(richtung1, richtung2)
            o1, o2 = _ort(e1, a), _ort(e2, b)
            if w < PARALLEL:
                text = f"Abstand {n1}–{n2} {zahl(_abstand_linie(o2, o1, richtung1))} mm (parallel)"
                extra = []
            else:
                text = f"Winkel {n1}–{n2} {zahl(w)}°"
                extra = [f"kürzester Abstand {zahl(_abstand_windschief(o1, richtung1, o2, richtung2))} mm"]
            if typ1 == typ2 == "gerade":            # zwei Kanten: Abstand bzw. Winkel der Kanten ist das Ergebnis
                haupt = text
                zeilen = [haupt] + zeilen + extra
            else:                                   # Mitten: Abstand der Mitten, Achsen dazu
                zeilen += [text] + extra
        elif typ1 == "gerade" or typ2 == "gerade":       # Kante (Kantenmitte) und Punkt: senkrechter Abstand
            e, p = (e1, b) if typ1 == "gerade" else (e2, a)
            zeilen.append(f"Abstand Punkt–Kante (senkrecht) {zahl(_abstand_linie(p, e['a'], e['r']))} mm")
        return haupt, zeilen


def _richtung(e):
    typ = e.get("typ")
    if typ == "gerade":
        return e["r"]
    if typ == "kreis":
        return e["n"]
    if typ == "zylinder":
        return e["r"]
    return None


def _ort(e, punkt):
    typ = e.get("typ")
    if typ == "gerade":
        return e["a"]
    if typ == "kreis":
        return e["m"]
    if typ == "zylinder":
        return e["p"]
    return punkt


def _abstand_linie(p, o, r):
    """Abstand des Punkts p von der Geraden o + t r."""
    v = _sub(p, o)
    k = _kreuz(v, r)
    return math.sqrt(_dot(k, k)) / (math.sqrt(_dot(r, r)) or 1.0)


def _abstand_windschief(o1, r1, o2, r2):
    n = _kreuz(r1, r2)
    lg = math.sqrt(_dot(n, n))
    if lg < 1e-12:
        return _abstand_linie(o2, o1, r1)
    return abs(_dot(_sub(o2, o1), n)) / lg


# ---------------------------------------------------------------- Kanten zusammensetzen
def _geraden(segmente):
    """Liniensegmente [(a, b)] zu ganzen geraden Kanten zusammensetzen: [dict(a, b, r, mitte)]. Kurze Stücke, die an
    beiden Enden fast stetig in gleich kurze Stücke übergehen (Vieleck eines Kreises), fallen weg."""
    gruppen = {}
    for a, b in segmente:
        r = _norm(_sub(b, a))
        if r is None:
            continue
        k = next(i for i in range(3) if abs(r[i]) > 1e-9)
        if r[k] < 0:
            r = (-r[0], -r[1], -r[2])
        fuss = _sub(a, tuple(_dot(a, r) * c for c in r))
        key = (round(r[0], 3), round(r[1], 3), round(r[2], 3), round(fuss[0], 2), round(fuss[1], 2), round(fuss[2], 2))
        t0, t1 = sorted((_dot(a, r), _dot(b, r)))
        gruppen.setdefault(key, (r, fuss, []))[2].append((t0, t1))
    stuecke = []
    for r, fuss, iv in gruppen.values():
        iv.sort()
        s0, s1 = iv[0]
        for t0, t1 in iv[1:]:
            if t0 <= s1 + 1e-3:
                s1 = max(s1, t1)
            else:
                stuecke.append((r, fuss, s0, s1))
                s0, s1 = t0, t1
        stuecke.append((r, fuss, s0, s1))
    enden = {}
    out = []
    for r, fuss, t0, t1 in stuecke:
        if t1 - t0 < 0.2:
            continue
        a = tuple(fuss[i] + r[i] * t0 for i in range(3))
        b = tuple(fuss[i] + r[i] * t1 for i in range(3))
        g = dict(a=a, b=b, r=r, mitte=tuple((a[i] + b[i]) / 2 for i in range(3)), laenge=t1 - t0)
        out.append(g)
        for q in (a, b):
            enden.setdefault(tuple(round(c, 2) for c in q), []).append(g)

    def glatt(g, q):
        """Geht g am Ende q fast stetig in ein höchstens gleich langes Stück über?"""
        for h in enden.get(tuple(round(c, 2) for c in q), ()):
            if h is g:
                continue
            w = winkel_zwischen(g["r"], h["r"])
            if PARALLEL <= w < 25 and h["laenge"] * 3 > g["laenge"]:
                return True
        return False
    return [g for g in out if not (glatt(g, g["a"]) and glatt(g, g["b"]))]


# ---------------------------------------------------------------- Anzeige
def _kreis_punkte(k, n=48):
    nn = _norm(k["n"]) or (0.0, 0.0, 1.0)
    e1 = _norm(_kreuz(nn, (1.0, 0.0, 0.0)) if abs(nn[0]) < 0.9 else _kreuz(nn, (0.0, 1.0, 0.0)))
    e2 = _kreuz(nn, e1)
    r = k["d"] / 2
    return [tuple(k["m"][i] + r * (math.cos(w) * e1[i] + math.sin(w) * e2[i]) for i in range(3))
            for w in (2 * math.pi * j / n for j in range(n + 1))]


def fang_zeichnen(p, bild, t, farbe, beschriften=False):
    """Fangpunkt hervorheben: Kreis als Ring mit Mitte, Kante dick, sonst ein Punkt; beschriften: Art (und Ø)."""
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing, True)
    el = t.get("element") or {}
    p.setPen(QPen(farbe, 2.5))
    p.setBrush(Qt.NoBrush)
    if el.get("typ") == "kreis":
        pk = [bild(q) for q in _kreis_punkte(el)]
        for a, b in zip(pk, pk[1:]):
            p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
    elif el.get("typ") == "gerade":
        a, b = bild(el["a"]), bild(el["b"])
        p.setPen(QPen(farbe, 4.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
    q = bild(t["punkt"])
    c = QPointF(q[0], q[1])
    p.setPen(QPen(farbe, 2.0))
    p.setBrush(QBrush(QColor(255, 255, 255)))
    if t["art"] in (KREISMITTE, KONTURMITTE):
        p.drawLine(c + QPointF(-7, 0), c + QPointF(7, 0))
        p.drawLine(c + QPointF(0, -7), c + QPointF(0, 7))
    elif t["art"] == ECKE:
        p.drawRect(QRectF(q[0] - 4, q[1] - 4, 8, 8))
    elif t["art"] == KANTENMITTE:
        p.drawPolygon([c + QPointF(0, -6), c + QPointF(6, 4), c + QPointF(-6, 4)])
    else:
        p.drawEllipse(c, 4, 4)
    if beschriften:
        text = t["art"] + (f" Ø {zahl(el['d'], el.get('stellen', 3))}" if el.get("typ") == "kreis" else "")
        r = QRectF(q[0] + 10, q[1] + 8, p.fontMetrics().horizontalAdvance(text) + 10, 18)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 225)))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(QPen(farbe))
        p.drawText(r, Qt.AlignCenter, text)
    p.restore()


class MessTafel(QFrame):
    """Mess-Tafel unten links in der 3D-Ansicht: Kernwerte bzw. Ergebnis mit drei Nachkommastellen, Knopf
    „Kopieren“ (Text in die Zwischenablage). Unsichtbar, solange nichts gemessen ist."""

    def __init__(self, ansicht):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.setObjectName("messtafel")
        self.setStyleSheet("#messtafel {background: rgba(255, 255, 255, 235); border: 1px solid #B42318; "
                           "border-radius: 4px;} QLabel {color: #202020;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 4, 4)
        self.text = QLabel()
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.text, 1)
        knoepfe = QVBoxLayout()
        self.kopieren = QToolButton()
        self.kopieren.setText("Kopieren")
        self.kopieren.setToolTip("Messergebnis als Text in die Zwischenablage")
        self.kopieren.clicked.connect(self.in_zwischenablage)
        zu = QToolButton()
        zu.setText("×")
        zu.setToolTip("Mess-Tafel schließen")
        zu.clicked.connect(lambda: self.zeigen([]))
        knoepfe.addWidget(zu, 0, Qt.AlignRight)
        knoepfe.addWidget(self.kopieren)
        lay.addLayout(knoepfe)
        self.zeilen = []
        self.hide()

    def zeigen(self, zeilen):
        self.zeilen = [z for z in zeilen if z]
        self.text.setText("\n".join(self.zeilen))
        self.setVisible(bool(self.zeilen))
        self.anordnen()

    def klartext(self):
        return "\n".join(self.zeilen)

    def in_zwischenablage(self):
        QGuiApplication.clipboard().setText(self.klartext())

    def anordnen(self):
        if self.isHidden():
            return
        self.adjustSize()
        a = self.ansicht
        self.setFixedWidth(min(self.sizeHint().width(), max(160, a.width() - 20)))
        self.adjustSize()
        self.move(10, max(4, a.height() - self.height() - 28))
        self.raise_()
