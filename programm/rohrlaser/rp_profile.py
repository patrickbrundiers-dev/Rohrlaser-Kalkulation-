"""RP-Profile (kaltgeformte Stahlrohre mit Anschlag, Patricks Bibliothek RP-ROHRE) und Querschnitte aus MegaCAD-Makros.

Die Querschnitte kommen als MegaCAD-2D-Makros (.mac): nach dem Kopf folgen Datensätze mit 1 Byte Art (3 = Linie,
5 = Bogen), 7 Byte Attribute (MegaCAD 13; MegaCAD 20: 9 Byte) und den Zahlen als double (little endian): Linie x1, y1, x2, y2; Bogen Mittelpunkt x, y,
Radius, Start- und Endwinkel [rad], gegen den Uhrzeigersinn. Andere Datensätze (Schraffur, Text, Maße) werden
übersprungen.

Auswertung (querschnitt): alle Linien und Bögen als ebener Graph (Bögen fein unterteilt, Schnitt- und
Berührpunkte geteilt), daraus die Flächen. Flächen mit 2 · Fläche / Umfang unter 1,6 × Wand sind
Blech, größere sind Kammern. Liegen zwei Blechlagen ohne Spalt aufeinander (Anschlag aus umgelegtem Blech), steht im
Makro nur eine Linie zwischen ihnen (oft mit losem Ende im Umschlag): beide Seiten der Linie sind Blech, sie zählt
als Doppellage.

Ergebnis je Querschnitt (Maße in mm):
- breite, hoehe: Hüllmaß; wand: Blechdicke aus den Biegungen (Differenz der Radien gleicher Mittelpunkte)
- flaeche [mm²], umfang (Außenkontur, für die Oberfläche), kammern (Anzahl), kammer_flaeche
- doppellage: Länge der aufeinanderliegenden Lagen (Anschläge), doppellagen: deren Anzahl
- schnitt: Länge eines geraden Trennschnitts = Außenkontur ohne Unterseite und Umschlag der Doppellagen (der Laser
  schneidet beide Lagen in einem Zug von oben); offene Profile die Hälfte (jede Wand einmal), davon schnitt_doppel durch die Doppellage (Schneiddaten 2 × Wand,
  Patrick 22.10.2026, Frage F10 a)
- ecken: Biegungen der Außenkontur (Bögen ab 20°, gleicher Mittelpunkt = eine Ecke), für die Eckzeit
- koerper: Anzahl getrennter Blechteile (1 bei einem Profil)

Die Bibliothek (rp_profile.json neben dieser Datei) enthält die ausgewerteten Makros aus RP-ROHRE (Patrick
22.10.2026: "archiv zur berechnung nutzen"); Profil-ID = "RP " + Dateiname, z. B. 'RP 0106-35' (Frage F12 a: Nummer und
Kammerbreite). Zubehör ohne Rohrlaser (400180 … 400330, Schrauben, Zeichnungen) ist nicht dabei (Frage F13 b).
"""
import bisect
import json
import math
import os
import struct

FORM = "RP-Profil"
PRAEFIX = "RP "
LINIE, BOGEN = 3, 5
_ZAHLEN = {LINIE: 4, BOGEN: 5}
SEHNE = 0.002           # mm, größter Abstand Sehne/Bogen beim Unterteilen
FANG = 1e-3             # mm, Punkte näher als das gelten als gleich
LUECKE = 0.05           # mm, Enden der Linien und Bögen näher als das werden zusammengezogen (Zeichenungenauigkeit)
ECKE_AB = math.radians(20)
MATERIAL_BIS = 1.6      # 2·A/U einer Fläche bis 1,6 × Wand: Blech, darüber Kammer

_BIBLIOTHEK = None


# ------------------------------------------------------------------ Makro lesen
def _kette(d, p, attr=7):
    teile = []
    while p + 1 + attr <= len(d) and d[p] in _ZAHLEN:
        n, q = _ZAHLEN[d[p]], p + 1 + attr
        if q + 8 * n > len(d):
            break
        v = struct.unpack("<%dd" % n, d[q:q + 8 * n])
        if not all(math.isfinite(x) and (x == 0 or 1e-300 < abs(x) < 1e5) for x in v) or \
                d[p] == BOGEN and not 1e-4 < v[2] < 1e4:
            break
        teile.append((d[p],) + tuple(v))
        p = q + 8 * n
    return teile


def lies_mac(daten):
    """Linien und Bögen eines MegaCAD-Makros (bytes oder Pfad): Liste von (3, x1, y1, x2, y2) bzw.
    (5, x, y, r, w0, w1). Gesucht wird die längste zusammenhängende Folge solcher Datensätze; die Zeichnung
    steht in diesen Makros am Stück hinter dem Kopf. Leere Liste, wenn keine gefunden wird."""
    if isinstance(daten, (str, os.PathLike)):
        with open(daten, "rb") as f:
            daten = f.read()
    beste = []
    for attr in (7, 9):
        p = 0
        while p < len(daten):
            if daten[p] in _ZAHLEN:
                k = _kette(daten, p, attr)
                if len(k) > len(beste):
                    beste = k
                if len(k) >= 3:
                    p += sum(1 + attr + 8 * _ZAHLEN[e[0]] for e in k)
                    continue
            p += 1
    return beste if len(beste) >= 3 else []


# ------------------------------------------------------------------ Geometrie
def _bogen_winkel(w0, w1):
    while w1 <= w0 + 1e-12:
        w1 += 2 * math.pi
    return w0, w1


def bogen_punkte(e, sehne=SEHNE):
    """Punkte eines Bogens (5, x, y, r, w0, w1) gegen den Uhrzeigersinn."""
    _, cx, cy, r, w0, w1 = e
    w0, w1 = _bogen_winkel(w0, w1)
    schritt = 2 * math.acos(max(-1.0, 1 - sehne / r)) if r > sehne else math.pi / 4
    n = max(2, math.ceil((w1 - w0) / max(schritt, 1e-3)))
    return [(cx + r * math.cos(w0 + (w1 - w0) * i / n), cy + r * math.sin(w0 + (w1 - w0) * i / n))
            for i in range(n + 1)]


def _schluessel(x, y):
    return (round(x / FANG), round(y / FANG))


class _Graph:
    """Ebener Graph aus Strecken; je Strecke die Nummer des Makro-Elements."""

    def __init__(self, elemente):
        zuege = [[(e[1], e[2]), (e[3], e[4])] if e[0] == LINIE else bogen_punkte(e) for e in elemente]
        _enden_fangen(zuege)
        strecken = []
        for i, pts in enumerate(zuege):
            for a, b in zip(pts, pts[1:]):
                if math.hypot(b[0] - a[0], b[1] - a[1]) > FANG / 2:
                    strecken.append((a, b, i))
        strecken = self._teilen(strecken)
        self.punkt = {}
        self.kanten = {}             # (k1, k2) mit k1 < k2 -> Element
        for a, b, i in strecken:
            ka, kb = _schluessel(*a), _schluessel(*b)
            if ka == kb:
                continue
            self.punkt.setdefault(ka, a)
            self.punkt.setdefault(kb, b)
            self.kanten.setdefault((min(ka, kb), max(ka, kb)), i)
        self.nachbarn = {}
        for k1, k2 in self.kanten:
            self.nachbarn.setdefault(k1, set()).add(k2)
            self.nachbarn.setdefault(k2, set()).add(k1)

    @staticmethod
    def _teilen(strecken):
        """Strecken an Schnitt- und Berührpunkten mit anderen Strecken teilen (Raster gegen n²)."""
        zelle = 2.0
        raster = {}
        for j, (a, b, _) in enumerate(strecken):
            for gx in range(math.floor(min(a[0], b[0]) / zelle), math.floor(max(a[0], b[0]) / zelle) + 1):
                for gy in range(math.floor(min(a[1], b[1]) / zelle), math.floor(max(a[1], b[1]) / zelle) + 1):
                    raster.setdefault((gx, gy), []).append(j)
        teil = {j: [] for j in range(len(strecken))}
        gesehen = set()
        for liste in raster.values():
            for x in range(len(liste)):
                for y in range(x + 1, len(liste)):
                    j, k = liste[x], liste[y]
                    if (j, k) in gesehen:
                        continue
                    gesehen.add((j, k))
                    for (s, t) in ((j, k), (k, j)):
                        for u in _beruehrung(strecken[s], strecken[t]):
                            teil[s].append(u)
        aus = []
        for j, (a, b, i) in enumerate(strecken):
            us = sorted(u for u in teil[j] if FANG / 10 < u < 1 - FANG / 10)
            pts = [a] + [(a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1])) for u in us] + [b]
            aus += [(p, q, i) for p, q in zip(pts, pts[1:])]
        return aus

    def zyklen(self):
        """Umläufe (Halbkanten mit der Fläche links): Liste von Punktschlüssel-Folgen."""
        sortiert = {}
        for k, ns in self.nachbarn.items():
            px, py = self.punkt[k]
            sortiert[k] = sorted(ns, key=lambda n: math.atan2(self.punkt[n][1] - py, self.punkt[n][0] - px))
        frei = {(a, b) for a, ns in self.nachbarn.items() for b in ns}
        aus = []
        while frei:
            start = frei.pop()
            zug = [start[0]]
            a, b = start
            while True:
                zug.append(b)
                ns = sortiert[b]
                i = ns.index(a)
                c = ns[i - 1]               # nächste Kante im Uhrzeigersinn ab der Rückkante: Fläche bleibt links
                if (b, c) == start:
                    break
                frei.discard((b, c))
                a, b = b, c
            aus.append(zug[:-1])
        return aus


def _enden_fangen(zuege):
    """Enden, die weniger als LUECKE auseinanderliegen, auf ihren Mittelpunkt setzen (kleine Lücken der Zeichnung)."""
    enden = [(i, j) for i in range(len(zuege)) for j in (0, -1)]
    eltern = list(range(len(enden)))

    def wurzel(x):
        while eltern[x] != x:
            eltern[x] = eltern[eltern[x]]
            x = eltern[x]
        return x
    raster = {}
    for n, (i, j) in enumerate(enden):
        x, y = zuege[i][j]
        gx, gy = math.floor(x / LUECKE), math.floor(y / LUECKE)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for m in raster.get((gx + dx, gy + dy), ()):
                    if math.dist(zuege[enden[m][0]][enden[m][1]], (x, y)) < LUECKE:
                        eltern[wurzel(n)] = wurzel(m)
        raster.setdefault((gx, gy), []).append(n)
    gruppen = {}
    for n in range(len(enden)):
        gruppen.setdefault(wurzel(n), []).append(n)
    for g in gruppen.values():
        if len(g) > 1:
            pts = [zuege[enden[n][0]][enden[n][1]] for n in g]
            mitte = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            for n in g:
                zuege[enden[n][0]][enden[n][1]] = mitte


def _beruehrung(s, t):
    """Parameter u auf s, an denen t die Strecke s schneidet oder mit einem Endpunkt berührt."""
    (ax, ay), (bx, by), _ = s
    (cx, cy), (dx, dy), _ = t
    rx, ry, sx, sy = bx - ax, by - ay, dx - cx, dy - cy
    l2 = rx * rx + ry * ry
    if l2 <= 0:
        return []
    aus = []
    for px, py in ((cx, cy), (dx, dy)):         # Endpunkt von t auf s
        u = ((px - ax) * rx + (py - ay) * ry) / l2
        if 0 < u < 1 and abs((px - ax) * ry - (py - ay) * rx) / math.sqrt(l2) < FANG:
            aus.append(u)
    nenner = rx * sy - ry * sx
    if abs(nenner) > 1e-12:
        u = ((cx - ax) * sy - (cy - ay) * sx) / nenner
        v = ((cx - ax) * ry - (cy - ay) * rx) / nenner
        if 0 < u < 1 and 0 < v < 1:
            aus.append(u)
    return aus


def _flaeche_umfang(pts):
    a = u = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
        u += math.hypot(x2 - x1, y2 - y1)
    return a / 2, u


def _innen(x, y, pts):
    drin = False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            drin = not drin
    return drin


def wandstaerke(elemente):
    """Blechdicke aus den Biegungen: häufigste Differenz der Radien von Bögen mit gleichem Mittelpunkt."""
    je_mitte = {}
    for e in elemente:
        if e[0] == BOGEN:
            je_mitte.setdefault((round(e[1], 2), round(e[2], 2)), set()).add(round(e[3], 3))
    zaehler = {}
    for radien in je_mitte.values():
        r = sorted(radien)
        for a, b in zip(r, r[1:]):
            d = round(b - a, 2)
            if d >= 0.3:
                zaehler[d] = zaehler.get(d, 0) + 1
    return max(zaehler, key=lambda d: (zaehler[d], -d)) if zaehler else None


def querschnitt(elemente, mit_konturen=False):
    """Kennwerte eines Querschnitts aus Linien und Bögen (siehe Modulbeschreibung). Ohne geschlossenen Querschnitt
    ValueError. mit_konturen: zusätzlich 'konturen' = dict(aussen=[(x, y)] gegen den Uhrzeigersinn,
    kammern=[[(x, y)] …]) als Polygone (z. B. für Testteile)."""
    if not elemente:
        raise ValueError("Keine Linien oder Bögen gefunden.")
    g = _Graph(elemente)
    zyklen = []
    for z in g.zyklen():
        pts = [g.punkt[k] for k in z]
        a, u = _flaeche_umfang(pts)
        if abs(a) > 1e-6:
            zyklen.append(dict(schluessel=z, pts=pts, a=a, u=u))
    positiv = [z for z in zyklen if z["a"] > 0]
    if not positiv:
        raise ValueError("Kein geschlossener Querschnitt.")
    positiv.sort(key=lambda z: z["a"])
    aussen = []
    for z in zyklen:
        z["loecher"] = []
    for z in [z for z in zyklen if z["a"] < 0]:
        x, y = z["pts"][0]
        # Testpunkt knapp links der ersten Kante (bei negativen Umläufen liegt das Innere der Hülle rechts)
        (x1, y1), (x2, y2) = z["pts"][0], z["pts"][1]
        lg = math.hypot(x2 - x1, y2 - y1) or 1.0
        tx, ty = (x1 + x2) / 2 - (y2 - y1) / lg * 1e-4, (y1 + y2) / 2 + (x2 - x1) / lg * 1e-4
        traeger = next((p for p in positiv if p["a"] > -z["a"] and _innen(tx, ty, p["pts"])), None)
        if traeger is None:
            aussen.append(z)
        else:
            traeger["loecher"].append(z)
    if not aussen:
        raise ValueError("Keine Außenkontur gefunden.")
    for p in positiv:
        p["netto"] = p["a"] + sum(h["a"] for h in p["loecher"])
        p["rand"] = p["u"] + sum(h["u"] for h in p["loecher"])
        p["dicke"] = 2 * p["netto"] / p["rand"] if p["rand"] else 0.0
    wand = wandstaerke(elemente) or min(p["dicke"] for p in positiv)
    for p in positiv:
        p["blech"] = p["dicke"] < MATERIAL_BIS * wand
    blech = [p for p in positiv if p["blech"]]
    kammern = [p for p in positiv if not p["blech"]]
    if not blech:
        raise ValueError("Keine Blechfläche erkannt.")
    # Halbkante -> Fläche (für die Doppellage: Kante zwischen zwei Blechflächen)
    flaeche_von = {}
    for p in positiv:
        for z in [p] + p["loecher"]:
            ks = z["schluessel"]
            for a, b in zip(ks, ks[1:] + ks[:1]):
                flaeche_von[(a, b)] = p
    doppel, doppel_kanten, umfang, elem_aussen = 0.0, [], 0.0, set()
    richtung = {"aussen": {}, "doppel": {}}     # Länge je Richtung (Grad 0 = waagerecht … 90 = senkrecht)
    for (a, b), i in g.kanten.items():
        p, q = flaeche_von.get((a, b)), flaeche_von.get((b, a))
        blech_p, blech_q = p is not None and p["blech"], q is not None and q["blech"]
        art = "doppel" if blech_p and blech_q else "aussen" if (blech_p and q is None) or (blech_q and p is None) \
            else None
        if art is None:
            continue
        (x1, y1), (x2, y2) = g.punkt[a], g.punkt[b]
        lg = math.hypot(x2 - x1, y2 - y1)
        w = round(math.degrees(math.atan2(abs(y2 - y1), abs(x2 - x1))))
        richtung[art][w] = richtung[art].get(w, 0.0) + lg
        if art == "doppel":
            doppel += lg
            doppel_kanten.append((a, b))
        else:                               # Blech gegen außen
            umfang += lg
            elem_aussen.add(i)
    laeufe = _laeufe(doppel_kanten)
    # Außenkontur: Ecken = Bögen ab 20°, je Mittelpunkt einmal
    ecken = set()
    for i in elem_aussen:
        e = elemente[i]
        if e[0] == BOGEN:
            w0, w1 = _bogen_winkel(e[4], e[5])
            if w1 - w0 >= ECKE_AB - 1e-9:
                ecken.add((round(e[1], 2), round(e[2], 2)))
    xs = [x for z in aussen for x, _ in z["pts"]]
    ys = [y for z in aussen for _, y in z["pts"]]
    schnitt_doppel = doppel + len(laeufe) * math.pi * wand / 2
    schnitt = max(umfang - doppel - len(laeufe) * math.pi * wand, 0.0)
    if not kammern:         # offenes Profil: der Laser schneidet jede Wand nur einmal (wie optimierung.schnittlaenge)
        schnitt /= 2
    aus = dict(breite=round(max(xs) - min(xs), 2), hoehe=round(max(ys) - min(ys), 2), wand=round(wand, 2),
                flaeche=round(sum(p["netto"] for p in blech), 1), umfang=round(umfang, 1),
                kammern=len(kammern), kammer_flaeche=[round(p["netto"], 1) for p in sorted(kammern, key=lambda p: -p["a"])],
                doppellage=round(doppel, 1), doppellagen=len(laeufe), schnitt=round(schnitt, 1),
                schnitt_doppel=round(min(schnitt_doppel, schnitt), 1), ecken=len(ecken), koerper=len(aussen),
                richtung={k: {str(w): round(v, 2) for w, v in sorted(d.items()) if v >= 0.005}
                          for k, d in richtung.items()},
                x0=round(min(xs), 3), y0=round(min(ys), 3))
    if mit_konturen:
        aus["konturen"] = dict(aussen=[list(reversed(z["pts"])) for z in aussen],
                               kammern=[p["pts"] for p in kammern])
    return aus


def pruefen(q):
    """Fehlertext, wenn der Querschnitt kein Rohrlaser-Profil ist (Schraube, Zeichnung, offenes Zubehör), sonst
    None. Offene Profile (ohne Kammer) gehören nicht zu den RP-Rohren (Patrick 22.10.2026, F13 b: 400180 … 400330
    sind Zubehör)."""
    if q["koerper"] != 1:
        return f"{q['koerper']} getrennte Teile statt eines Profils"
    if q["wand"] < 0.5 or q["flaeche"] < 10:
        return f"keine Blechdicke erkennbar (Wand {q['wand']:g} mm, Fläche {q['flaeche']:g} mm²)"
    if not q["kammern"]:
        return "offenes Profil ohne Kammer (Zubehör)"
    return None


def schnitt_gehrung(e, winkel, ueber="x"):
    """Länge eines Trennschnitts unter Gehrung (winkel in Grad gegen den geraden Schnitt): die Kontur wird in der
    gekippten Richtung um 1 / cos(winkel) gestreckt (ueber 'x' = Breite, 'y' = Höhe des Querschnitts). Doppellagen
    und Umschläge wie beim geraden Schnitt abgezogen."""
    t = math.tan(math.radians(abs(winkel or 0.0)))
    return schnitt_schraeg(e, t, 0.0) if ueber == "x" else schnitt_schraeg(e, 0.0, t)


def schnitt_schraeg(e, tx, ty):
    """Länge eines ebenen Trennschnitts z = tx·x + ty·y (zweiachsiger Schrägschnitt, tx, ty = Steigung über Breite
    bzw. Höhe): jedes Konturstück der Richtung w wird um √(1 + (tx·cos w + ty·sin w)²) länger. Doppellagen und
    Umschläge wie beim geraden Schnitt abgezogen (Umschläge mit der mittleren Streckung)."""
    def f(w):
        return math.sqrt(1 + (tx * math.cos(math.radians(int(w))) + ty * math.sin(math.radians(int(w)))) ** 2)

    def lang(d):
        return sum(v * f(w) for w, v in (d or {}).items())
    r = e.get("richtung") or {}
    if not r:
        return e["schnitt"] * math.sqrt(1 + tx * tx + ty * ty)
    mittel = (math.sqrt(1 + tx * tx) + math.sqrt(1 + ty * ty)) / 2
    s = max(lang(r.get("aussen")) - lang(r.get("doppel")) - e["doppellagen"] * math.pi * e["wand"] * mittel, 0.0)
    return s / 2 if not e.get("kammern") else s


def doppel_anteil(e, gemessen=None):
    """Länge des Trennschnitts durch die Doppellage (Anschlag) [mm]: gerade schnitt_doppel, bei einem schrägen Ende
    (gemessen = Schnittlänge des Endes) im Verhältnis gemessen / gerader Schnitt gestreckt."""
    d = float(e.get("schnitt_doppel") or 0)
    if d <= 0 or not gemessen or not e.get("schnitt"):
        return d
    return d * max(1.0, gemessen / e["schnitt"])


def _laeufe(kanten):
    """Zusammenhängende Kantenzüge (je Doppellage einer)."""
    nb = {}
    for a, b in kanten:
        nb.setdefault(a, []).append(b)
        nb.setdefault(b, []).append(a)
    gesehen, n = set(), 0
    for k in nb:
        if k in gesehen:
            continue
        n += 1
        offen = [k]
        while offen:
            x = offen.pop()
            if x in gesehen:
                continue
            gesehen.add(x)
            offen += nb[x]
    return [None] * n


# ------------------------------------------------------------------ Bibliothek
def profil_id(dateiname):
    """'0106-35.mac' -> 'RP 0106-35'."""
    return PRAEFIX + os.path.splitext(os.path.basename(dateiname))[0].strip()


def eintrag(pfad_oder_daten, name):
    """Bibliothekseintrag eines Makros: Kennwerte + Elemente (verschoben, Ecke unten links = 0, 0)."""
    el = lies_mac(pfad_oder_daten)
    q = querschnitt(el)
    x0, y0 = q.pop("x0"), q.pop("y0")
    verschoben = []
    for e in el:
        if e[0] == LINIE:
            verschoben.append([LINIE] + [round(v, 4) for v in (e[1] - x0, e[2] - y0, e[3] - x0, e[4] - y0)])
        else:
            verschoben.append([BOGEN] + [round(v, 4) for v in (e[1] - x0, e[2] - y0)] +
                              [round(v, 6) for v in e[3:]])
    return dict(profil_id=profil_id(name), **q, elemente=verschoben)



def bibliothek():
    """Mitgelieferte RP-Profile: {Profil-ID: Eintrag}."""
    global _BIBLIOTHEK
    if _BIBLIOTHEK is None:
        pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rp_profile.json")
        try:
            with open(pfad, encoding="utf-8") as f:
                _BIBLIOTHEK = {e["profil_id"]: e for e in json.load(f)["profile"]}
        except (OSError, ValueError, KeyError):
            _BIBLIOTHEK = {}
    return _BIBLIOTHEK


_EIGENE = {}


def eigene_setzen(eintraege):
    """Selbst geladene RP-Profile (Einstellung 'rp_eigene' der Datendatei): {Profil-ID: Eintrag}. Sie gehen der
    Bibliothek vor."""
    _EIGENE.clear()
    _EIGENE.update(eintraege or {})


def daten(pid):
    """Eintrag zur Profil-ID ('RP 0106-35'): selbst geladene vor der Bibliothek; None, wenn unbekannt."""
    if not pid:
        return None
    pid = str(pid).strip()
    return _EIGENE.get(pid) or bibliothek().get(pid)


TOL_MASS = 0.3          # mm, Breite/Höhe beim Erkennen (Fingerabdruck)
TOL_ANTEIL = 0.015      # Fläche und Konturlänge beim Erkennen


def erkennen(breite, hoehe, flaeche, umfang, kammern=1, wand=None, eintraege=None):
    """RP-Profile, deren Fingerabdruck zu einem gemessenen Querschnitt passt (STEP-Import): Breite und Höhe (in
    beliebiger Lage), Fläche, Konturlänge (außen + Kammern = 'umfang' der Bibliothek), Zahl der Kammern und
    Blechdicke. eintraege: {Profil-ID: Eintrag}, Vorgabe eigene + Bibliothek. Ergebnis: Profil-IDs, beste zuerst."""
    if eintraege is None:
        eintraege = dict(bibliothek(), **_EIGENE)
    m = sorted((breite, hoehe))
    treffer = []
    for pid, e in eintraege.items():
        if (e.get("kammern") or 0) != kammern or \
                any(abs(x - y) > TOL_MASS for x, y in zip(sorted((e["breite"], e["hoehe"])), m)):
            continue
        if wand and abs(e["wand"] - wand) > 0.15:
            continue
        df, du = abs(e["flaeche"] - flaeche) / e["flaeche"], abs(e["umfang"] - umfang) / e["umfang"]
        if df <= TOL_ANTEIL and du <= TOL_ANTEIL:
            treffer.append((df + du, pid))
    return [pid for _, pid in sorted(treffer)]


def schnitt_aus_messung(e, gemessen, gerade):
    """Schnittlänge eines Endes für ein RP-Profil aus der STEP-Messung: die Messung zählt die Doppellage als zwei
    Wände (Außenkontur + Kammer), der Laser trennt sie mit einem Schnitt. Gerades Ende: Schnittlänge der Kontur,
    sonst die gemessene Länge im Verhältnis Schnittlänge / Konturlänge."""
    if gerade or not gemessen:
        return e["schnitt"]
    return gemessen * e["schnitt"] / e["umfang"] if e.get("umfang") else gemessen


def ausduennen(pts, tol=0.005):
    """Geschlossenen Zug vereinfachen (Douglas-Peucker): Punkte, die weniger als tol von der Sehne abweichen, fallen
    weg."""
    def dp(zug):
        if len(zug) < 3:
            return zug
        (x1, y1), (x2, y2) = zug[0], zug[-1]
        lg = math.hypot(x2 - x1, y2 - y1) or 1e-12
        d = [abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1)) / lg for x, y in zug[1:-1]]
        i = max(range(len(d)), key=d.__getitem__)
        if d[i] <= tol:
            return [zug[0], zug[-1]]
        return dp(zug[:i + 2])[:-1] + dp(zug[i + 1:])
    n = len(pts) // 2
    return dp(pts[:n + 1])[:-1] + dp(pts[n:] + pts[:1])[:-1]


_UMRISS = {}


def umriss(e, tol=0.1):
    """Kontur eines Eintrags für Zeichnungen: [Außenkontur, Kammer …] als Polygone um die Mitte des Hüllrechtecks
    (vereinfacht mit tol), oder [] ohne Elemente."""
    if not e.get("elemente"):
        return []
    schluessel = (e["profil_id"], e["flaeche"], tol)
    if schluessel not in _UMRISS:
        q = querschnitt(e["elemente"], mit_konturen=True)
        mx, my = q["x0"] + q["breite"] / 2, q["y0"] + q["hoehe"] / 2
        _UMRISS[schluessel] = [[(round(x - mx, 4), round(y - my, 4)) for x, y in ausduennen(z, tol)]
                               for z in q["konturen"]["aussen"][:1] + q["konturen"]["kammern"]]
    return _UMRISS[schluessel]


def stammdaten_zeile(e, bemerkung=None):
    """Zeile für die Stammdaten 'Profile': A = Breite, B = Höhe, Wandstärke = Blechdicke, Fläche aus der Kontur."""
    return dict(profil_id=e["profil_id"], form=FORM, a=e["breite"], b=e["hoehe"], wand=e["wand"],
                flaeche_manuell=e["flaeche"],
                bemerkung=bemerkung or ("RP-ROHRE " + e["serie"] if e.get("serie") else "RP-Profil aus MegaCAD-Makro"))


def laden(pfade):
    """MegaCAD-Makros einlesen: (Einträge, Meldungen je übersprungener Datei)."""
    eintraege, meldungen = [], []
    for pfad in pfade:
        name = os.path.basename(pfad)
        try:
            e = eintrag(pfad, name)
        except (OSError, ValueError) as ex:
            meldungen.append(f"{name}: {ex}")
            continue
        fehler = pruefen(e)
        if fehler:
            meldungen.append(f"{name}: {fehler}")
            continue
        eintraege.append(e)
    return eintraege, meldungen


def bibliothek_bauen(ordner, ziel):
    """rp_profile.json aus Patricks Ordner RP-ROHRE (Unterordner Serie-34 … Serie-80, Zubehoer; 'Alle Profile' ist eine
    Kopie und wird nur genutzt, wenn eine Datei in keiner Serie steht)."""
    je_id = {}
    for unter in sorted(os.listdir(ordner)):
        pfad = os.path.join(ordner, unter)
        if not os.path.isdir(pfad):
            continue
        serie = "" if unter.lower() == "alle profile" else unter.replace("Zubehoer", "Zubehör")
        dateien = sorted(os.path.join(pfad, f) for f in os.listdir(pfad) if f.lower().endswith(".mac"))
        for e in laden(dateien)[0]:
            if e["profil_id"] not in je_id or serie and not je_id[e["profil_id"]].get("serie"):
                je_id[e["profil_id"]] = dict(e, serie=serie)
    profile = sorted(je_id.values(), key=lambda e: e["profil_id"])
    with open(ziel, "w", encoding="utf-8") as f:
        json.dump(dict(quelle="RP-ROHRE (MegaCAD-Makros, Patrick 22.10.2026)", profile=profile), f,
                  ensure_ascii=False, separators=(",", ":"))
    return profile


if __name__ == "__main__":       # python -m rohrlaser.rp_profile <Ordner RP-ROHRE> [Ziel]
    import sys
    ziel = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                               "rp_profile.json")
    print(len(bibliothek_bauen(sys.argv[1], ziel)), "RP-Profile ->", ziel)
