"""3D-Modell eines Rohrs/Profils aus den Eingaben des Schneidweg-Rechners (Plan 3D-Editor A2/G3): damit hat der
Teile-Editor auch ohne STEP-Datei ein drehbares Modell, und jede Eingabe (Gehrung, Ausklinkung, Kontur) ist sofort
im 3D zu sehen – wie in den CAM-Programmen.

Grundlage ist dieselbe Geometrie wie für die Skizze (skizze.py): Querschnitt (Außen- und Innenumriss), Schnittkante
der Enden (skizze.schnitt_x) und Lage der Konturen (skizze.lagen/platzieren). Geschnittene Konturen (Bohrung,
Langloch, Rechteck, Ausklinkung, Polygon, V-Ausschnitt, Sonderkontur mit Umriss …) sind bei geschlossenen Rohren
ausgeschnitten, mit Lochwand durch die Wandstärke (Patrick 24.10.2026); dazu je Kontur ein Linienzug auf der
Außenwand, der ihr Merkmal trägt (li 'kontur:3', 'ende:a'), damit ein Klick im 3D die Zeile wählt. Gravur und
Flowdrill (nur markiert) bleiben Linien.

Ausschneiden: Der Mantel ist abgewickelt ein Rechteck (t = Bogenlänge am Umriss, x = Rohrachse). Je Spalte zwischen
zwei Umrisspunkten wird das Viereck zwischen den Enden in waagerechte Streifen an allen Ecken zerlegt; in jedem
Streifen sind die Ränder gerade, die freien Stücke zwischen den Löchern werden Trapeze (zwei Dreiecke). Innenwand
gleich, Punkt für Punkt auf dem Innenumriss.

Netz wie ansicht3d: Rohrachse = Z ab Ende A, Y = oben, X = −u (vorne = −X, so zeigt die Ansicht „Vorn“ die Seite
vorne/90°).
"""
import bisect
import math

from . import durchdringung as dd, schnittflaeche as sf, skizze as sk, steckverbindung as stv
from .blech3d import _flaeche2, _ohrschnitt
from .schneidweg import (AUSKLINKUNG, BOHRUNG, DURCHBRUCH, FLOWDRILL, GRAVUR, GRAVUREN, LANGLOCH, LOCHFELD, POLYGON,
                         RECHTECK, SCHLITZ, SENKUNG, SONDERKONTUR, TEXT_GRAVUR, V_AUSSCHNITT, _z, mit_radius)

SCHRITT = 4.0           # Kanten des Querschnitts höchstens so lang [mm] (Ausklinkung, Sattel folgen der Kurve)
TEILE_MAX = 24          # je Kante höchstens so viele Stücke
ABSTAND = 0.4           # Linien so weit über der Wand [mm] (verdecken sich nicht mit der Fläche)


def _xyz(x, u, v):
    return (-u, v, x)


def _unterteilen(poly, teile=None, extra=None):
    """Geschlossenes Polygon an den Kanten unterteilen; teile = Anzahl je Kante (für gleiche Teilung innen/außen),
    extra = {Kante: [Anteile 0..1]} zusätzliche Punkte (Knicke eines gemessenen Endes, innen wie außen)."""
    out, anzahl = [], []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        n = teile[i] if teile else max(1, min(TEILE_MAX, math.ceil(math.dist(a, b) / SCHRITT)))
        anzahl.append(n)
        fs = [k / n for k in range(n)]
        if extra and extra.get(i):
            fs = sorted(set(fs) | {f for f in extra[i] if 1e-6 < f < 1 - 1e-6})
        out += [(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f) for f in fs]
    return out, anzahl


def _knick_anteile(qs, poly, enden, extra=()):
    """Knicke der gemessenen Enden (Umriss eines komplexen Endes, Stellen s) als {Kante von poly: [Anteile]}: dort
    braucht der Umriss einen Punkt, sonst schneidet die Schnittkante die Ecke ab. extra: weitere Stellen s (Ränder
    der Mündungen von Ausflügen, dort endet die Schnittkante genau)."""
    out = {}
    stellen = list(extra)
    for es in enden:
        if not es.get("umriss") or _z(es.get("winkel")):
            continue
        um = sk._ende_umriss_merken(qs, es["umriss"])
        stellen += list(getattr(um, "stellen", ()) if um else ())
    for s in stellen:
        (u, v), _ = qs.s_zu_uv(s % qs.umfang)
        u, v, _ = sk.rund_ort(qs, u, v)
        beste = None
        for i, a in enumerate(poly):
            b = poly[(i + 1) % len(poly)]
            du, dv = b[0] - a[0], b[1] - a[1]
            if qs.r:        # Rundrohr: Punkt der Sehne in derselben Richtung von der Mitte (gleiches s wie uv_zu_s)
                det = u * dv - v * du
                if abs(det) > 1e-12:
                    f = (u * a[1] - v * a[0]) / -det
                    if -1e-9 <= f <= 1 + 1e-9 and (a[0] + f * du) * u + (a[1] + f * dv) * v > 0:
                        beste = (0.0, i, min(max(f, 0.0), 1.0))
                        break
                continue
            lg = du * du + dv * dv
            f = 0.0 if lg < 1e-12 else max(0.0, min(1.0, ((u - a[0]) * du + (v - a[1]) * dv) / lg))
            d = (a[0] + f * du - u) ** 2 + (a[1] + f * dv - v) ** 2
            if beste is None or d < beste[0]:
                beste = (d, i, f)
        if beste:
            out.setdefault(beste[1], []).append(beste[2])
    return out


# ausgeschnittene Konturarten (Gravur, Flowdrill, Sonstige und künftige Gravurarten bleiben Linien)
LOCH_ARTEN = (BOHRUNG, SENKUNG, LANGLOCH, RECHTECK, SCHLITZ, AUSKLINKUNG, POLYGON, V_AUSSCHNITT, LOCHFELD, DURCHBRUCH)


def _laengen(poly):
    """Bogenlänge an jedem Punkt des geschlossenen Polygons (letzter Eintrag = Umfang)."""
    cum = [0.0]
    for i, a in enumerate(poly):
        cum.append(cum[-1] + math.dist(a, poly[(i + 1) % len(poly)]))
    return cum


def _t_von(poly, cum, u, v):
    """Bogenlänge des nächsten Punkts auf dem Polygon zu (u, v). Bei vielen Aufrufen für dasselbe Polygon (je
    Lochpunkt einer, Belastungstest 7.000 Bohrungen) sucht ein Raster nur die Kanten in der Nähe: gleiche Kanten
    in gleicher Reihenfolge geprüft wie ohne Raster, daher dasselbe Ergebnis (Performance-Plan P1)."""
    kandidaten = _kanten_raster(poly).nahe(u, v) if len(poly) > RASTER_AB else range(len(poly))
    beste = None
    for i in kandidaten:
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        du, dv = b[0] - a[0], b[1] - a[1]
        lg = du * du + dv * dv
        f = 0.0 if lg < 1e-12 else max(0.0, min(1.0, ((u - a[0]) * du + (v - a[1]) * dv) / lg))
        d = (a[0] + f * du - u) ** 2 + (a[1] + f * dv - v) ** 2
        if beste is None or d < beste[0]:
            beste = (d, cum[i] + f * (cum[i + 1] - cum[i]))
    return beste[1]


RASTER_AB = 24          # Kanten: ab so vielen Kanten sucht _t_von über das Raster
_raster_merker = {}


class _KantenRaster:
    """Kanten eines geschlossenen Polygons in quadratischen Zellen (Kantenlänge der größten Kante). nahe(u, v) =
    Nummern aller Kanten, die näher liegen können als die nächste gefundene, aufsteigend sortiert."""

    def __init__(self, poly):
        n = len(poly)
        self.h = max(max(math.dist(poly[i], poly[(i + 1) % n]) for i in range(n)), 1e-6)
        self.poly, self.zellen = poly, {}
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            for cx in range(self._z(min(a[0], b[0])), self._z(max(a[0], b[0])) + 1):
                for cy in range(self._z(min(a[1], b[1])), self._z(max(a[1], b[1])) + 1):
                    self.zellen.setdefault((cx, cy), []).append(i)
        xs = [k[0] for k in self.zellen]
        ys = [k[1] for k in self.zellen]
        self.rand = (min(xs), max(xs), min(ys), max(ys))

    def _z(self, w):
        return math.floor(w / self.h)

    def _d2(self, i, u, v):
        a, b = self.poly[i], self.poly[(i + 1) % len(self.poly)]
        du, dv = b[0] - a[0], b[1] - a[1]
        lg = du * du + dv * dv
        f = 0.0 if lg < 1e-12 else max(0.0, min(1.0, ((u - a[0]) * du + (v - a[1]) * dv) / lg))
        return (a[0] + f * du - u) ** 2 + (a[1] + f * dv - v) ** 2

    def nahe(self, u, v):
        if not (math.isfinite(u) and math.isfinite(v)):
            return range(len(self.poly))
        cx, cy = self._z(u), self._z(v)
        x0, x1, y0, y1 = self.rand
        weit = max(abs(cx - x0), abs(cx - x1), abs(cy - y0), abs(cy - y1)) + 1
        gefunden, beste = set(), None
        for r in range(weit + 1):
            for x in range(cx - r, cx + r + 1):
                for y in ((cy - r, cy + r) if r and x not in (cx - r, cx + r) else range(cy - r, cy + r + 1)):
                    for i in self.zellen.get((x, y), ()):
                        if i not in gefunden:
                            gefunden.add(i)
                            d = self._d2(i, u, v)
                            beste = d if beste is None or d < beste else beste
            # Kanten in Ring r + 1 und weiter liegen mindestens r · h entfernt: strikt weiter weg als die beste
            if beste is not None and (r * self.h) ** 2 > beste + 1e-6:
                break
        else:
            return range(len(self.poly))
        return sorted(gefunden)


def _kanten_raster(poly):
    r = _raster_merker.get(id(poly))
    if r is None or r.poly is not poly:
        if len(_raster_merker) > 32:
            _raster_merker.clear()
        r = _raster_merker[id(poly)] = _KantenRaster(poly)
    return r


def _innen(pt, poly):
    """Punkt in Polygon (gerade/ungerade Regel)."""
    x, y = pt
    drin = False
    for i, (ax, ay) in enumerate(poly):
        bx, by = poly[i - 1]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            drin = not drin
    return drin


def loecher(e, qs, aussen, cum, L, cum_i=None):
    """Geschnittene Konturen als [(Polygon [(t, x)], Zeile)] in der Abwicklung des Außenumrisses; über die Naht
    (t = 0) reichende zusätzlich um den Umfang verschoben. Mit cum_i (Innenumriss, gleiche Teilung; Rundrohr und
    Eckradius): 2D-Konturen innen mit den gezeichneten Abständen zur Mitte, außen breiter
    (schnittflaeche.innen_massgebend, Patrick 26.10.2026)."""
    out = []
    for d in sk.lagen(e.get("konturen") or [], L, qs):
        poly = loch_poly(d, e, qs, aussen, cum, cum_i)
        if poly:
            out.append((poly, d["zeile"]))
            _naht_kopien(out, poly, d["zeile"], cum[-1])
    return out


def loch_poly(d, e, qs, aussen, cum, cum_i=None):
    """Rand einer geschnittenen Kontur (Lage d aus skizze.lagen) als [(t, x)] in der Abwicklung des Außenumrisses
    oder None (keine ausgeschnittene Kontur). t läuft über die Naht stetig weiter."""
    T = cum[-1]
    ein = d["eingabe"]
    art = ein.get("art")
    if art not in LOCH_ARTEN and not (art == SONDERKONTUR and ein.get("umriss")):
        return None
    pts = sk.umriss_kontur(ein)
    if not pts or len(pts) < 3:
        return None
    try:
        s0 = sk.s_lage(qs, ein)
        if cum_i is not None and sf.innen_2d(ein, e):
            (u, v), _ = qs.s_zu_uv(s0 % qs.umfang)
            tm = _t_von(aussen, cum, u, v)
            return sf.innen_massgebend([(tm + dq, d["x"] + dx) for dx, dq in sk._dicht(pts, 2.0)], cum, cum_i, tm)
        # 3D eben am Eckradius: Kontur auf der Ebene der Wand, parallel zur Normalen auf die Rundung gelegt
        eben = cum_i is not None and not qs.r and qs.radius and sf.eben_3d(ein, e)
        n_m = qs.s_zu_uv(s0 % qs.umfang)[1] if eben else None
        poly, t_alt = [], None
        for dx, dq in sk._dicht(pts, 2.0):
            (u, v), n_p = qs.s_zu_uv((s0 + dq) % qs.umfang)
            if eben and math.dist(n_p, n_m) < 1e-6:
                sv = sf.strahl_bis(aussen, (u + 2 * qs.radius * n_m[0], v + 2 * qs.radius * n_m[1]),
                                   (-n_m[0], -n_m[1]))
                if sv is not None:
                    u, v = u + (2 * qs.radius - sv) * n_m[0], v + (2 * qs.radius - sv) * n_m[1]
            t = _t_von(aussen, cum, u, v)
            if t_alt is not None:           # über die Naht: stetig weiterzählen
                t += T * round((t_alt - t) / T)
            poly.append((t, d["x"] + dx))
            t_alt = t
    except (ValueError, TypeError, ZeroDivisionError, AttributeError):
        return None
    return poly


def _naht_kopien(out, poly, zeile, T):
    """Über die Naht (t = 0) reichende Kontur zusätzlich um den Umfang verschoben."""
    t_min, t_max = min(p[0] for p in poly), max(p[0] for p in poly)
    if t_min < 0:
        out.append(([(t + T, x) for t, x in poly], zeile))
    if t_max > T:
        out.append(([(t - T, x) for t, x in poly], zeile))


def _schnitte(poly, x):
    """Schnitte der Waagerechten x mit den Kanten des Polygons: [(t, Kante (a, b))]."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > x) != (b[1] > x):
            out.append((a[0] + (x - a[1]) * (b[0] - a[0]) / (b[1] - a[1]), (a, b)))
    return sorted(out, key=lambda q: q[0])


def _t_bei(kante, x):
    a, b = kante
    if abs(b[1] - a[1]) < 1e-12:
        return a[0]
    return a[0] + (x - a[1]) * (b[0] - a[0]) / (b[1] - a[1])


def _kreuz(p, q, r, s):
    """Schnittpunkt-x der Strecken p–q und r–s oder None."""
    d = (q[0] - p[0]) * (s[1] - r[1]) - (q[1] - p[1]) * (s[0] - r[0])
    if abs(d) < 1e-12:
        return None
    u = ((r[0] - p[0]) * (s[1] - r[1]) - (r[1] - p[1]) * (s[0] - r[0])) / d
    w = ((r[0] - p[0]) * (q[1] - p[1]) - (r[1] - p[1]) * (q[0] - p[0])) / d
    if -1e-9 <= u <= 1 + 1e-9 and -1e-9 <= w <= 1 + 1e-9:
        return p[1] + u * (q[1] - p[1])
    return None


def zelle_frei(feld, loch_liste):
    """Viereck feld [(t, x)] (Spalte zwischen den Enden) ohne die Löcher als Trapeze [(t_l0, t_r0, x0, t_l1, t_r1, x1)]
    (unten links/rechts, oben links/rechts)."""
    hoehen = {p[1] for p in feld}
    t0, t1 = min(p[0] for p in feld), max(p[0] for p in feld)
    kanten_feld = [(feld[i], feld[(i + 1) % 4]) for i in range(4)]
    for poly in loch_liste:
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            if t0 - 1e-9 <= a[0] <= t1 + 1e-9:
                hoehen.add(a[1])
            for p, q in kanten_feld:
                x = _kreuz(a, b, p, q)
                if x is not None:
                    hoehen.add(x)
    hoehen = sorted(hoehen)
    x_min, x_max = min(p[1] for p in feld), max(p[1] for p in feld)
    out = []
    # Streifen aufsteigend: nur Löcher, die die Höhe des Streifens überdecken, in der Reihenfolge von loch_liste
    # (die übrigen schneiden die Waagerechte nicht; Belastungstest: Hunderte Löcher je Spalte)
    folge = sorted(range(len(loch_liste)), key=lambda k: min(p[1] for p in loch_liste[k]))
    hoch = [max(p[1] for p in poly) for poly in loch_liste]
    tief = [min(p[1] for p in poly) for poly in loch_liste]
    naechst, aktiv = 0, set()
    for xa, xb in zip(hoehen, hoehen[1:], strict=False):
        if xb - xa < 1e-7 or xb <= x_min or xa >= x_max:
            continue
        xm = (xa + xb) / 2
        while naechst < len(folge) and tief[folge[naechst]] <= xm:
            aktiv.add(folge[naechst])
            naechst += 1
        aktiv = {k for k in aktiv if hoch[k] >= xm}
        q = _schnitte(feld, xm)
        if len(q) < 2:
            continue
        frei = [(q[0][0], q[0][1], q[-1][0], q[-1][1])]       # (t links, Kante, t rechts, Kante)
        for nr in sorted(aktiv):
            s = _schnitte(loch_liste[nr], xm)
            for k in range(0, len(s) - 1, 2):
                (la, ka), (ra, kb) = s[k], s[k + 1]
                neu = []
                for fl, kl, fr, kr in frei:
                    if ra <= fl or la >= fr:
                        neu.append((fl, kl, fr, kr))
                        continue
                    if la > fl:
                        neu.append((fl, kl, la, ka))
                    if ra < fr:
                        neu.append((ra, kb, fr, kr))
                frei = neu
        for _, kl, _, kr in frei:
            out.append((_t_bei(kl, xa), _t_bei(kr, xa), xa, _t_bei(kl, xb), _t_bei(kr, xb), xb))
    return out


def nasen_lage(ende, qs, winkel=None):
    """Nasen eines Endes (dict der Eingaben a/b): (Länge über den Schnitt hinaus = Flanke [mm], [Winkel der
    Nasenmitten], halbe Breite am Umfang [mm]) oder None. Winkel von Ende A gesehen wie die Schweißnaht (0° oben,
    90° vorne); Vorgabe 'quer' = erste Nase oben (Wände der Breite a, steckverbindung.querschnitt), 'längs' = vorne,
    die zweite gegenüber, bei 4 Nasen alle Wände. Rundrohr: Nase = Bogenstück über der Sehne bN."""
    n = stv.nasen(ende)
    if not n or _z(n.get("laenge_plus")) <= 0 or _z(n.get("bN")) <= 0:
        return None
    w0 = _z(winkel) if winkel is not None else _z(n.get("winkel")) if n.get("winkel") is not None else \
        (90.0 if n.get("waende") == stv.WAENDE[1] else 0.0)
    anzahl = int(_z(n.get("anzahl")) or 2)
    schritt = {1: (0,), 2: (0, 180), 4: (0, 180, 90, 270)}.get(anzahl, (0, 180))
    if stv.versatz_liste(n):        # Ecke: je Aufnahme eine Nase (steckverbindung.nasen_wahl_ecke)
        schritt = (0,) + tuple(stv.versatz_liste(n))
    b_n = _z(n.get("bN"))
    h = qs.r * math.asin(min(1.0, b_n / (2 * qs.r))) if qs.r else b_n / 2
    return _z(n.get("laenge_plus")), [(w0 + d) % 360 for d in schritt], h


def nasen_stuecke(e, profil, laenge, nasen_winkel=None):
    """Nasen als Körper für den STEP-Export (3E-8): je Nase dict(ende, winkel, aussen, innen) mit aussen/innen =
    [(Punkt am Schnitt, Punkt an der Spitze)] je Stelle am Umfang, Koordinaten wie netz (Z = Rohrachse ab Ende A)."""
    n = netz(e, profil, laenge, nasen_winkel=nasen_winkel)
    return (n or {}).get("nasen") or []


# Fertige Netze merken (Performance-Plan P1): Rohr-Editor, Satz in 3D, Baugruppe und Vorschau bauen dasselbe Rohr
# sonst bei jeder Anzeige neu. Schlüssel = alle Eingaben; zurück kommt eine Kopie (Aufrufer verschieben Punkte).
NETZ_MERKEN_ZAHLEN = 6_000_000      # höchstens so viele Zahlen (Punkte, Indizes) in allen gemerkten Netzen
_netz_merker = {}


def _kopie(o):
    if isinstance(o, dict):
        return {k: _kopie(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_kopie(x) for x in o] if o and isinstance(o[0], (list, dict, tuple)) else o[:]
    if isinstance(o, tuple):
        return tuple(_kopie(x) for x in o)
    return o


def _zahlen(n):
    return len(n.get("p") or ()) + sum(len(t) for t in (n.get("t") or {}).values()) + \
        sum(len(z) for zs in (n.get("l") or {}).values() for z in zs)


def netz_merker_leeren():
    _netz_merker.clear()


def netz(e, profil, laenge, naht_winkel=None, grenze=None, nasen_winkel=None, bau=None):
    """Wie netz_rechnen, gleiche Eingaben liefern das gemerkte Netz (als Kopie). Mit bau (STEP-Export) immer neu."""
    if bau is not None:
        return netz_rechnen(e, profil, laenge, naht_winkel, grenze, nasen_winkel, bau)
    import json
    try:
        schl = json.dumps([e, profil, laenge, naht_winkel, grenze, nasen_winkel], sort_keys=True, default=repr)
    except (TypeError, ValueError):
        return netz_rechnen(e, profil, laenge, naht_winkel, grenze, nasen_winkel)
    if schl in _netz_merker:
        _netz_merker[schl] = _netz_merker.pop(schl)
        return _kopie(_netz_merker[schl])
    n = netz_rechnen(e, profil, laenge, naht_winkel, grenze, nasen_winkel)
    if n is None:
        return None
    _netz_merker[schl] = _kopie(n)
    gesamt = sum(_zahlen(x) for x in _netz_merker.values())
    while len(_netz_merker) > 1 and gesamt > NETZ_MERKEN_ZAHLEN:
        alt = _netz_merker.pop(next(iter(_netz_merker)))
        gesamt -= _zahlen(alt)
    return n


def netz_rechnen(e, profil, laenge, naht_winkel=None, grenze=None, nasen_winkel=None, bau=None):
    """Netz der 3D-Ansicht aus Eingaben e (schneidweg), Profil und Teilelänge [mm]; None ohne Länge/Querschnitt.
    naht_winkel: Lage der Längsschweißnaht (naht.py, von Ende A gesehen 0° oben, 90° rechts) als rote Linie 'NL'
    über die ganze Länge (Patrick 24.10.2026), None = keine feste Naht. grenze: Kopfschwenk der Maschine [°] für
    Enden in 3D (schnittflaeche.py: 2D Strahl senkrecht zum Mantel, 3D bis zur Grenze, darüber gelb 'GB').
    Nasen einer Steckverbindung (Block 'nasen' an Ende a/b) sind als Laschen der Wand über den Schnitt hinaus
    modelliert (nasen_stuecke); nasen_winkel = {Ende: Winkel der ersten Nase} statt der Vorgabe (nasen_lage).
    bau: dict, das die Rechengrößen aufnimmt (STEP-Export step_export.py: Querschnitt, Umrisse, Enden za/zb, Löcher)."""
    L = _z(laenge)
    if L <= 0:
        return None
    qs = sk.Querschnitt(mit_radius(profil, e))
    umriss = qs.umriss_rund(12)             # Quadrat-/Rechteckrohr mit Außenradius (je Ecke 12 Stücke)
    if not umriss or len(umriss[0]) < 3:
        return None
    ea, eb = e.get("a") or {}, e.get("b") or {}
    punkte, dreiecke, linien, normalen, kennung, flaeche_id = [], {}, {}, {}, {}, {}

    def punkt(v):
        punkte.extend(v)            # gerundet wird einmal am Ende (schneller als je Punkt, gleiche Werte)
        return len(punkte) // 3 - 1

    def dreieck(art, a, b, c, soll, merkmal="teil"):
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        w = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        if n[0] ** 2 + n[1] ** 2 + n[2] ** 2 < 1e-12:
            return
        if sum((n[0] * soll[0], n[1] * soll[1], n[2] * soll[2])) < 0:        # sum wie bisher (gleiche Rundung)
            b, c = c, b
        dreiecke.setdefault(art, []).extend((punkt(a), punkt(b), punkt(c)))
        flaeche_id.setdefault(art, []).append(merkmal)       # Klick auf die Fläche wählt das Merkmal

    def linie(art, zug, mitte_n, merkmal):
        linien.setdefault(art, []).append([round(c, 3) for p in zug for c in p])
        normalen.setdefault(art, []).append([round(c, 3) for c in mitte_n])
        kennung.setdefault(art, []).append(merkmal)

    innen_x = {"a": {}, "b": {}}        # Innenkante der Enden je Punkt des Innenumrisses (schnittflaeche.punkt)
    gelb = {"a": set(), "b": set()}     # Stücke des Umrisses über der 3D-Grenze

    # Nasen einer Steckverbindung: das Teil ist um die Flanke länger (Rohlänge), der Schnitt des Endes liegt um so
    # viel weiter innen, die Nasen ragen bis zum Teilende
    nasen = {s_: nasen_lage(es, qs, (nasen_winkel or {}).get(s_)) for s_, es in (("a", ea), ("b", eb))}
    plus = {s_: (n_[0] if n_ else 0.0) for s_, n_ in nasen.items()}

    def za(u, v):
        x = innen_x["a"].get((round(u, 6), round(v, 6)))
        return (sk.schnitt_x(qs, ea, u, v) if x is None else x) + plus["a"]

    def zb(u, v):
        x = innen_x["b"].get((round(u, 6), round(v, 6)))
        return L - (sk.schnitt_x(qs, eb, u, v) if x is None else x) - plus["b"]

    roh_a = list(umriss[0]) if _flaeche2(umriss[0]) > 0 else list(umriss[0])[::-1]     # ccw in (u, v)
    knicke = _knick_anteile(qs, roh_a, (ea, eb), [s_ for k in e.get("konturen") or () if k.get("muendung")
                                                  for s_ in k["muendung"]])
    aussen, teile = _unterteilen(roh_a, extra=knicke)
    innen = None
    if len(umriss) > 1 and len(umriss[1]) == len(umriss[0]):
        roh_i = list(umriss[1]) if _flaeche2(umriss[1]) > 0 else list(umriss[1])[::-1]
        # gleiche Ecke zuerst wie außen (nächster Punkt), damit Stirnfläche innen/außen zusammenpasst
        k = min(range(len(roh_i)), key=lambda i: math.dist(roh_i[i], roh_a[0]))
        innen, _ = _unterteilen(roh_i[k:] + roh_i[:k], teile, knicke)
        g = sf.GRENZE if grenze is None else abs(float(grenze))
        for s_, es in (("a", ea), ("b", eb)):
            d3 = e.get("d3") is True and bool(es.get("d3"))
            werte = [sf.punkt(qs, es, pa, pi, d3, g) for pa, pi in zip(aussen, innen, strict=False)]
            for pi, w in zip(innen, werte, strict=False):
                innen_x[s_][(round(pi[0], 6), round(pi[1], 6))] = w["x_innen"]
            gelb[s_] = {i for i in range(len(werte)) if werte[i]["begrenzt"] or werte[(i + 1) % len(werte)]["begrenzt"]}

    def mantel(poly, art, nach_aussen, auslassen=()):
        n = len(poly)
        for i in range(n):
            if i in auslassen:
                continue
            (u0, v0), (u1, v1) = poly[i], poly[(i + 1) % n]
            du, dv = u1 - u0, v1 - v0
            nu, nv = (dv, -du) if nach_aussen else (-dv, du)        # Polygon ccw: rechts der Kante = außen
            soll = _xyz(0, nu, nv)
            a0, a1 = _xyz(za(u0, v0), u0, v0), _xyz(za(u1, v1), u1, v1)
            b0, b1 = _xyz(zb(u0, v0), u0, v0), _xyz(zb(u1, v1), u1, v1)
            dreieck(art, a0, a1, b1, soll)
            dreieck(art, a0, b1, b0, soll)

    cum = _laengen(aussen)
    T = cum[-1]
    zeilen = e.get("konturen") or []
    # Rundrohr und Eckradius: 2D (Strahl senkrecht zur Oberfläche) mit maßhaltiger Innenkante, außen breiter; 3D
    # (Schnittrichtung parallel) eben durch die Wand (Patrick 26.10.2026, Variante C, schnittflaeche.innen_massgebend)
    rundung = bool(qs.r or qs.radius) and bool(innen) and T > 0
    parallel = {i for i, z in enumerate(zeilen) if sf.eben_3d(z, e)} if rundung else set()
    cum_i = _laengen(innen) if rundung else None
    loch_zeile = loecher(e, qs, aussen, cum, L, cum_i) if innen and T > 0 else []
    loch = [q for q, _ in loch_zeile]
    loch_rahmen = [(min(p[0] for p in q), max(p[0] for p in q), min(p[1] for p in q), max(p[1] for p in q)) for q in loch]

    def ort(t, x, wand):
        """Punkt (t, x) der Abwicklung auf der Außen- bzw. Innenwand (gleiche Spalte, gleicher Anteil)."""
        t = t % T
        i = max(0, min(len(aussen) - 1, bisect.bisect_right(cum, t) - 1))
        f = 0.0 if cum[i + 1] - cum[i] < 1e-12 else (t - cum[i]) / (cum[i + 1] - cum[i])
        (u0, v0), (u1, v1) = wand[i], wand[(i + 1) % len(wand)]
        return x, u0 + f * (u1 - u0), v0 + f * (v1 - v0)

    def innen_parallel(q):
        """Lochrand auf der Innenwand bei Schnitt parallel zur Konturachse (3D, ebene Bearbeitung): jeder Punkt des
        Rands außen geht parallel zur Normalen in der Lochmitte nach innen (statt senkrecht zur Oberfläche).
        Rundrohr und Eckradius. [(t, x)] wie q."""
        tm = sum(p[0] for p in q) / len(q)
        if qs.r:
            _, um, vm = ort(tm, 0.0, aussen)
            lg = math.hypot(um, vm) or 1.0
            nu, nv = um / lg, vm / lg
        else:                           # Normale der Wand an der Lochmitte (auf dem Bogen: Normale des Bogens)
            k = max(0, min(len(aussen) - 1, bisect.bisect_right(cum, tm % T) - 1))
            (u0, v0), (u1, v1) = aussen[k], aussen[(k + 1) % len(aussen)]
            lg = math.hypot(u1 - u0, v1 - v0) or 1.0
            nu, nv = (v1 - v0) / lg, -(u1 - u0) / lg
        ri = math.hypot(*innen[0])
        out = []
        for t, x in q:
            _, u, v = ort(t, x, aussen)
            if qs.r:
                pn = u * nu + v * nv
                disk = pn * pn - (u * u + v * v) + ri * ri
                sv = pn - math.sqrt(disk) if disk >= 0 else None
            else:
                sv = sf.strahl_bis(innen, (u, v), (-nu, -nv))
            if sv is None:
                out.append((t, x))
                continue
            ti = _t_von(innen, cum_i, u - sv * nu, v - sv * nv)
            k = max(0, min(len(innen) - 1, bisect.bisect_right(cum_i, ti) - 1))
            f = 0.0 if cum_i[k + 1] - cum_i[k] < 1e-12 else (ti - cum_i[k]) / (cum_i[k + 1] - cum_i[k])
            ta = cum[k] + f * (cum[k + 1] - cum[k])
            ta += T * round((t - ta) / T)          # über die Naht: neben dem Punkt außen bleiben
            out.append((ta, x))
        return out

    loch_innen = [innen_parallel(q) if z in parallel else q for q, z in loch_zeile]

    def mantel_loch(poly, art, nach_aussen, loch=loch):
        """Wand mit Löchern: jede Spalte in Trapeze ohne die Löcher. Die Kanten zwischen zwei Spalten bekommen die
        Eckpunkte beider Nachbarn (sonst T-Stöße: feine Risse, die als Längslinien über das ganze Rohr laufen)."""
        n = len(poly)
        spalten = []
        # Löcher je Spalte vorab einsortieren (statt je Spalte alle Löcher zu prüfen): Reihenfolge wie in loch
        bereich = [(min(p[0] for p in q), max(p[0] for p in q)) for q in loch]
        je_spalte = [[] for _ in range(n)]
        for k, (lo, hi) in enumerate(bereich):
            von = max(0, bisect.bisect_left(cum, lo) - 1)
            bis = min(n - 1, bisect.bisect_right(cum, hi))
            for i in range(von, bis + 1):
                if lo < cum[i + 1] and hi > cum[i]:
                    je_spalte[i].append(k)
        for i in range(n):
            t0, t1 = cum[i], cum[i + 1]
            hier = [loch[k] for k in je_spalte[i]]
            (u0, v0), (u1, v1) = poly[i], poly[(i + 1) % n]
            feld = [(t0, za(u0, v0)), (t1, za(u1, v1)), (t1, zb(u1, v1)), (t0, zb(u0, v0))]
            zellen = zelle_frei(feld, hier)
            links = {x for tl0, _, x0, tl1, _, x1 in zellen if abs(tl0 - t0) < 1e-9 and abs(tl1 - t0) < 1e-9
                     for x in (x0, x1)}
            rechts = {x for _, tr0, x0, _, tr1, x1 in zellen if abs(tr0 - t1) < 1e-9 and abs(tr1 - t1) < 1e-9
                      for x in (x0, x1)}
            spalten.append((t0, t1, zellen, links, rechts))
        grenze = [sorted(spalten[i][4] | spalten[(i + 1) % n][3]) for i in range(n)]     # rechts von Spalte i

        def zwischen(liste, x0, x1):
            """Einträge der sortierten Liste strikt zwischen x0 + 1e-7 und x1 − 1e-7 (aufsteigend)."""
            return liste[bisect.bisect_right(liste, x0 + 1e-7):bisect.bisect_left(liste, x1 - 1e-7)]
        for i, (t0, t1, zellen, _, _) in enumerate(spalten):
            (u0, v0), (u1, v1) = poly[i], poly[(i + 1) % n]
            du, dv = u1 - u0, v1 - v0
            soll = _xyz(0, *((dv, -du) if nach_aussen else (-dv, du)))

            def p3(t, x, t0=t0, t1=t1, u0=u0, v0=v0, du=du, dv=dv):
                f = 0.0 if t1 - t0 < 1e-12 else (t - t0) / (t1 - t0)
                return _xyz(x, u0 + f * du, v0 + f * dv)
            for tl0, tr0, x0, tl1, tr1, x1 in zellen:
                rechts = zwischen(grenze[i], x0, x1) if abs(tr0 - t1) < 1e-9 and abs(tr1 - t1) < 1e-9 else []
                links = zwischen(grenze[i - 1], x0, x1)[::-1] \
                    if abs(tl0 - t0) < 1e-9 and abs(tl1 - t0) < 1e-9 else []
                if not rechts and not links:
                    a, b, c, d = p3(tl0, x0), p3(tr0, x0), p3(tr1, x1), p3(tl1, x1)
                    dreieck(art, a, b, c, soll)
                    dreieck(art, a, c, d, soll)
                    continue
                zug = [(tl0, x0), (tr0, x0)] + [(t1, x) for x in rechts] + [(tr1, x1), (tl1, x1)] + \
                    [(t0, x) for x in links]
                m = p3(sum(q[0] for q in zug) / len(zug), sum(q[1] for q in zug) / len(zug))
                for q, r in zip(zug, zug[1:] + zug[:1], strict=False):
                    dreieck(art, m, p3(*q), p3(*r), soll)
        return set(range(n))

    gelocht = mantel_loch(aussen, "A", True) if loch else set()
    mantel(aussen, "A", True, gelocht)
    if innen:
        gelocht_i = mantel_loch(innen, "I", False, loch_innen) if loch else set()
        mantel(innen, "I", False, gelocht_i)
    # Lochwände: je Kante des Lochs ein Viereck von außen nach innen, Vorderseite zur Lochmitte
    for (q, zeile), qi in zip(loch_zeile, loch_innen, strict=False):
        dreh = 1 if sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(q, q[1:] + q[:1], strict=False)) > 0 else -1
        for (a, b), (ai, bi) in zip(zip(q, q[1:] + q[:1], strict=False), zip(qi, qi[1:] + qi[:1], strict=False), strict=False):
            tm, xm = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if not 0 <= tm < T:
                continue
            xa, ua, va = ort(tm, xm, aussen)
            if not za(ua, va) - 1e-6 <= xm <= zb(ua, va) + 1e-6:
                continue
            dt, dx = b[0] - a[0], b[1] - a[1]
            nt, nx = (-dx * dreh, dt * dreh)          # links der Kante = Lochinneres bei ccw
            i = max(0, min(len(aussen) - 1, bisect.bisect_right(cum, tm) - 1))
            (u0, v0), (u1, v1) = aussen[i], aussen[(i + 1) % len(aussen)]
            lg = math.hypot(u1 - u0, v1 - v0) or 1.0
            tu, tv = (u1 - u0) / lg, (v1 - v0) / lg
            soll = (-(nt * tu), nt * tv, nx)
            pa, pb = _xyz(*ort(a[0], a[1], aussen)), _xyz(*ort(b[0], b[1], aussen))
            qa, qb = _xyz(*ort(ai[0], ai[1], innen)), _xyz(*ort(bi[0], bi[1], innen))
            dreieck("K", pa, pb, qb, soll, f"kontur:{zeile}")
            dreieck("K", pa, qb, qa, soll, f"kontur:{zeile}")
    # Stirnflächen (Schnittflächen der Enden): Ring zwischen außen und innen bzw. volles Profil
    for art, z, soll in (("EA", za, (0, 0, -1)), ("EB", zb, (0, 0, 1))):
        ende = f"ende:{art[1].lower()}"
        if innen:
            n = len(aussen)
            for i in range(n):
                p0, p1, q0, q1 = aussen[i], aussen[(i + 1) % n], innen[i], innen[(i + 1) % n]
                if loch:        # Ausklinkung / Schlitz am Ende: Stück der Stirnfläche im Loch weglassen
                    tm = (cum[i] + cum[i + 1]) / 2
                    xm = (z(*p0) + z(*p1)) / 2
                    xm += 1e-3 if art == "EA" else -1e-3
                    if any(r[0] <= tm <= r[1] and r[2] <= xm <= r[3] and _innen((tm, xm), q)
                           for q, r in zip(loch, loch_rahmen, strict=False)):
                        continue
                a0, a1 = _xyz(z(*p0), *p0), _xyz(z(*p1), *p1)
                b0, b1 = _xyz(z(*q0), *q0), _xyz(z(*q1), *q1)
                art_i = "GB" if i in gelb[art[1].lower()] else art     # 3D über der Grenze: gelb
                dreieck(art_i, a0, a1, b1, soll, ende)
                dreieck(art_i, a0, b1, b0, soll, ende)
        elif not qs.r:
            for a, b, c in _ohrschnitt(aussen):
                dreieck(art, _xyz(z(*a), *a), _xyz(z(*b), *b), _xyz(z(*c), *c), soll, ende)
        # Schnittkante als Linie (Merkmal Ende)
        muend = [k["muendung"] for k in e.get("konturen") or () if k.get("ende_teil") == art[1] and k.get("muendung")]
        for teil in _ohne_muendung(qs, aussen + aussen[:1], muend):
            linie(art, [_xyz(z(u, v), u, v) for u, v in teil], (0, 1, 0), f"ende:{art[1].lower()}")
        for i in sorted(gelb[art[1].lower()]):         # über der 3D-Grenze: gelb über der Schnittkante
            p0, p1 = aussen[i], aussen[(i + 1) % len(aussen)]
            linie("GB", [_xyz(z(*p0), *p0), _xyz(z(*p1), *p1)], (0, 1, 0), ende)
    # Gegenrohr (Hilfskörper, pink): am Ende und je Durchbruch, als Linien (Plan 3D-Editor G2/G3)
    for s_, es in (("a", ea), ("b", eb)):
        g = dd.gegen_lesen(es)
        if g and (qs.r or es.get("gegen")):
            try:
                for zug in dd.gegen_koerper(qs, g, L, s_):
                    linie("HK", [_xyz(*p) for p in zug], (0, 1, 0), f"ende:{s_}")
            except (ValueError, ZeroDivisionError):
                pass
    for d in sk.lagen(e.get("konturen") or [], L, qs):
        if d["art"] == DURCHBRUCH and not d.get("kopie") and d["eingabe"].get("umriss"):
            for zug in durchbruch_koerper(qs, d):
                linie("HK", [_xyz(*p) for p in zug], (0, 1, 0), f"kontur:{d['zeile']}")
    # Konturen auf der Außenwand
    rund = bool(qs.radius) and not qs.r
    for d in sk.lagen(e.get("konturen") or [], L, qs):
        ein = d["eingabe"]
        if ein.get("art") == TEXT_GRAVUR and not ein.get("umriss"):     # Schrift: je Strich ein Linienzug
            from . import gravur_text
            for strich in gravur_text.gedreht(gravur_text.linien(ein.get("text"), _z(ein.get("hoehe"))),
                                              ein.get("winkel")):
                try:            # quer gespiegelt: von außen lesbar, Leserichtung von Ende A nach B
                    pts, n_mitte = sk.platzieren(qs, d, [(x, -y) for x, y in strich])
                except (ValueError, TypeError, ZeroDivisionError):
                    continue
                zug = []
                for x, u, v in pts:
                    r = math.hypot(u, v) or 1.0
                    nu, nv = (u / r, v / r) if qs.r else n_mitte
                    zug.append(_xyz(x, u + nu * ABSTAND, v + nv * ABSTAND))
                linie("G", zug, _xyz(0, *n_mitte), f"kontur:{d['zeile']}")
            continue
        try:
            geschlossen = not (ein.get("art") == GRAVUR and not ein.get("umriss"))
            if geschlossen and (qs.r or (rund and ein.get("umriss"))):
                # fein, damit die Linie dem Rohr bzw. dem Bogen der Ecke folgt (nicht als Sehne quer durch)
                fein = sk._dicht(sk.umriss_kontur(ein) or [(0.0, 0.0)], 1.0)
                pts, n_mitte = sk.platzieren(qs, d, fein)
                ns = [(u / (math.hypot(u, v) or 1.0), v / (math.hypot(u, v) or 1.0)) for _, u, v in pts] if qs.r \
                    else [qs.s_zu_uv(sk.s_lage(qs, ein, dq) % qs.umfang)[1] for _, dq in fein]
            else:
                pts, n_mitte = sk.platzieren(qs, d)
                ns = sk.normalen(qs, d)
        except (ValueError, TypeError, ZeroDivisionError):
            continue
        if len(pts) < 2:
            continue
        if rund:                # Eckradius: auf der gerundeten Außenkontur wie Netz und STEP
            neu = []
            for (x, u, v), n_ in zip(pts, ns + ns[-1:] * len(pts), strict=False):
                u, v, nr = sk.rund_ort(qs, u, v)
                neu.append(((x, u, v), nr or n_))
            pts, ns = [p_ for p_, _ in neu], [n_ for _, n_ in neu]
        zug = [_xyz(x, u + nu * ABSTAND, v + nv * ABSTAND) for (x, u, v), (nu, nv) in zip(pts, ns + ns[-1:] * len(pts), strict=False)]
        if ein.get("muendung"):         # Ausflug eines Endes: zur Mündung hin offen
            basis = fein if geschlossen and (qs.r or (rund and ein.get("umriss"))) else sk.umriss_kontur(ein)
            i = sk.muendung_ende(ein, basis)
            if i is not None and len(basis or ()) == len(zug):
                zug = zug[:i + 1]
        elif not (ein.get("art") == GRAVUR and not ein.get("umriss")):
            zug.append(zug[0])
        linie("G" if ein.get("art") in GRAVUREN else "K", zug, _xyz(0, *n_mitte), f"kontur:{d['zeile']}")
        if ein.get("art") == SENKUNG and _z(ein.get("D")) > _z(ein.get("d")):
            # Rand der Senkung auf der Außenwand wie in der STEP (geschnitten wird nur die Bohrung Ø d)
            rk = _z(ein.get("D")) / 2
            try:
                pts, n_mitte = sk.platzieren(qs, d, [(rk * math.cos(math.pi * i / 24), rk * math.sin(math.pi * i / 24))
                                                     for i in range(48)])
            except (ValueError, TypeError, ZeroDivisionError):
                continue
            zug = []
            for x, u, v in pts:
                r = math.hypot(u, v) or 1.0
                nu, nv = (u / r, v / r) if qs.r else n_mitte
                if rund:        # über eine gerundete Ecke: auf der Außenkontur wie die Bohrung
                    u, v, nr = sk.rund_ort(qs, u, v)
                    nu, nv = nr or (nu, nv)
                zug.append(_xyz(x, u + nu * ABSTAND, v + nv * ABSTAND))
            linie("K", zug + zug[:1], _xyz(0, *n_mitte), f"kontur:{d['zeile']}")
    # Gravur der Anbauteile (STEP-Import, anbau.gravur_zuege): Lage aus der Messung, im selben Rohrsystem
    for zug in e.get("anbau_gravur") or ():
        if len(zug) >= 2:
            linie("GA", [tuple(p[i] + n[i] * ABSTAND for i in range(3)) for p, n in zug], zug[len(zug) // 2][1],
                  "teil")
    # Nasen der Steckverbindung: Lasche der Wand (Breite am Umfang 2 h) vom Schnitt bis zum Teilende
    stuecke = []
    for s_, z, art in (("a", za, "EA"), ("b", zb, "EB")):
        if not nasen[s_] or not innen or T <= 0:
            continue
        lg, winkel, h = nasen[s_]
        richtung = -1.0 if s_ == "a" else 1.0
        ende = f"ende:{s_}"
        for w in winkel:
            pt = sk.naht_punkt(qs, w)
            if pt is None:
                continue
            tc = _t_von(aussen, cum, *pt)
            ts = [tc - h] + [c + T * k for k in (-1, 0, 1) for c in cum[:-1] if tc - h < c + T * k < tc + h] + [tc + h]
            ts.sort()
            aus, inn = [], []
            for t in ts:
                _, u, v = ort(t, 0.0, aussen)
                _, ui, vi = ort(t, 0.0, innen)
                xa, xi = z(u, v), z(ui, vi)
                aus.append((_xyz(xa, u, v), _xyz(xa + richtung * lg, u, v), (u, v)))
                inn.append((_xyz(xi, ui, vi), _xyz(xi + richtung * lg, ui, vi)))
            for (a0, a1, (u0, v0)), (b0, b1, (u1, v1)), (c0, c1), (d0, d1) in zip(aus, aus[1:], inn, inn[1:], strict=False):
                du, dv = u1 - u0, v1 - v0
                dreieck("A", a0, b0, b1, _xyz(0, dv, -du), ende)
                dreieck("A", a0, b1, a1, _xyz(0, dv, -du), ende)
                dreieck("I", c0, d0, d1, _xyz(0, -dv, du), ende)
                dreieck("I", c0, d1, c1, _xyz(0, -dv, du), ende)
                dreieck(art, a1, b1, d1, (0, 0, richtung), ende)          # Stirn der Nase
                dreieck(art, a1, d1, c1, (0, 0, richtung), ende)
            for (a0, a1, (u0, v0)), (c0, c1), nach in ((aus[0], inn[0], -1), (aus[-1], inn[-1], 1)):
                (ua, va), (ub, vb) = (aus[0][2], aus[1][2]) if nach < 0 else (aus[-2][2], aus[-1][2])
                soll = _xyz(0, nach * (ub - ua), nach * (vb - va))      # Flanke: längs des Umfangs nach außen
                dreieck(art, a0, a1, c1, soll, ende)
                dreieck(art, a0, c1, c0, soll, ende)
            linie(art, [aus[0][0], aus[0][1]] + [p[1] for p in aus[1:]] + [aus[-1][0]], (0, 1, 0), ende)
            stuecke.append(dict(ende=s_, winkel=round(w, 3), aussen=[(p[0], p[1]) for p in aus], innen=inn))
    # Längsschweißnaht: rote Linie auf der Außenwand von Anfangs- bis Endschnitt
    try:
        pt = sk.naht_punkt(qs, naht_winkel)
    except (ValueError, TypeError):
        pt = None
    if pt is not None:
        r = math.hypot(*pt) or 1.0
        u, v = pt[0] + pt[0] / r * ABSTAND, pt[1] + pt[1] / r * ABSTAND
        x0, x1 = za(*pt), zb(*pt)
        schritte = max(1, int(abs(x1 - x0) // 50))
        zug = [_xyz(x0 + (x1 - x0) * i / schritte, u, v) for i in range(schritte + 1)]
        linie("NL", zug, _xyz(0, pt[0] / r, pt[1] / r), "naht")
    if bau is not None:
        bau.update(qs=qs, umriss=umriss, aussen=aussen, innen=innen, cum=cum, T=T, za=za, zb=zb, ort=ort, L=L,
                   loch_zeile=loch_zeile, nasen=nasen, plus=plus)
    punkte[:] = [round(c, 3) for c in punkte]
    out = dict(p=punkte, t=dreiecke, ti=flaeche_id, l=linien, ln=normalen, li=kennung, eingaben=True,
               geo=geometrie(e, qs, L))
    if stuecke:
        out["nasen"] = stuecke
    from . import schnittkoerper
    wk = schnittkoerper.rohr(e, qs, L, _xyz)        # Schnittkörper je Kontur (halb durchsichtig, Tiefe im Tooltip)
    if wk:
        out["wk"] = wk
    return out


def mit_step(netz, netz_step, e, profil, laenge):
    """Schnittkörper unbekannter Konturen in netz (aus netz()) durch ihre Form aus dem STEP-Netz ersetzen
    (schnittkoerper.aus_step); netz wird geändert und zurückgegeben."""
    if not netz or not netz_step or not isinstance(netz_step, dict):
        return netz
    from . import schnittkoerper
    try:
        qs = sk.Querschnitt(mit_radius(profil, e))
        wk = schnittkoerper.aus_step(netz.get("wk"), netz_step, e, qs, _z(laenge), _xyz)
    except (ValueError, TypeError, ZeroDivisionError, KeyError):
        return netz
    if wk:
        netz["wk"] = wk
    return netz


KREIS_ARTEN = (BOHRUNG, SENKUNG, FLOWDRILL)


def merkmal_werte(ein):
    """Eingaben einer Kontur für die Kernwerte beim Messen (messen3d.MERKMAL_WERTE)."""
    out = {k: ein[k] for k in ("art", "d", "D", "l", "lang", "b", "h", "r", "t", "winkel", "x", "q", "seite")
           if ein.get(k) not in (None, "")}
    return out


def geometrie(e, qs, L):
    """Exakte Geometrie für das Messen (Plan 3D-Ansicht 3E-11, M4): Kreise (Mitte auf der Außenwand, Achse = Normale
    der Wand, Ø aus der Eingabe), Mitten der übrigen Konturen, Werte je Merkmal und das Rohr (Ø bzw. B × H, Wand)."""
    geo = dict(kreise=[], mitten=[], merkmale={},
               rohr=dict(d=round(2 * qs.r, 6) if qs.r else None, b=qs.B, h=qs.H, t=qs.wand, laenge=L))
    for d in sk.lagen(e.get("konturen") or [], L, qs):
        ein = d["eingabe"]
        art = ein.get("art")
        kid = f"kontur:{d['zeile']}"
        try:
            pts, n = sk.platzieren(qs, d, [(_z(ein.get("_dx")), _z(ein.get("_dq")))])
        except (ValueError, TypeError, ZeroDivisionError, AttributeError):
            continue
        x, u, v = pts[0]
        if qs.r:
            r = math.hypot(u, v) or 1.0
            n = (u / r, v / r)
        m, achse = [round(c, 6) for c in _xyz(x, u, v)], [round(c, 6) for c in _xyz(0, *n)]
        dm = _z(ein.get("d"))
        if dm > 0 and (art in KREIS_ARTEN or (art == LOCHFELD and not _z(ein.get("lang")))):
            geo["kreise"].append(dict(m=m, n=achse, d=dm, id=kid))
        elif art not in GRAVUREN or ein.get("umriss"):
            geo["mitten"].append(dict(p=m, n=achse, id=kid))
        geo["merkmale"].setdefault(kid, merkmal_werte(ein))
    return geo


def durchbruch_koerper(qs, d, n=40):
    """Gegenrohr eines Durchbruchs als Linien [(x, u, v)]: zwei Umrissringe und Längslinien entlang seiner Achse
    (durch den Kreuzungspunkt bei x, gekippt um den Winkel zur Wand in Richtung Ende B)."""
    e = d["eingabe"]
    gq = dd.querschnitt_gegen(dict(d=e.get("d"), t=e.get("t"), r=e.get("r_gegen")))
    w = math.radians(_z(e.get("winkel")))
    if qs.r:
        phi = math.radians(sk.winkel_aus_text(e.get("seite")) or 0.0)
        nu, nv = math.sin(phi), math.cos(phi)
        versatz = _z(e.get("versatz"))
    else:
        f = qs.flaeche(e.get("seite")) or qs.flaechen[0]
        nu, nv = f.n
        versatz = _z(e.get("q"))
    tu, tv = nv, -nu                    # quer auf der Fläche
    ou, ov = tu * versatz, tv * versatz
    halb = 0.75 * max(qs.B, qs.H, 2 * (qs.r or 0)) + max(gq.quer, gq.tief)
    ringe = []
    for s in (-halb, halb):
        ring = []
        for gx, gy in gq.umriss(n):     # gx = tief (längs zum Rohr), gy = quer
            x = d["x"] + s * math.sin(w) + gx * math.cos(w)
            m = s * math.cos(w) - gx * math.sin(w)
            ring.append((x, ou + m * nu + gy * tu, ov + m * nv + gy * tv))
        ringe.append(ring + ring[:1])
    return ringe + [[ringe[0][i], ringe[1][i]] for i in range(0, n, max(1, n // 8))]


def _ohne_muendung(qs, pts, muend):
    """Schnittkante eines Endes (Punkte (u, v) des Außenumrisses) ohne die Stücke in den Mündungen [s von, s bis]
    der Ausflüge (Schlitz o. ä., der in das Ende läuft): dort ist das Teil offen. Liste der Teilzüge."""
    if not muend:
        return [pts]

    def offen(u, v):
        s = sk.uv_zu_s(qs, u, v)
        return any(0 < (s - a) % qs.umfang < (b - a) % qs.umfang for a, b in muend)
    out, zug = [], []
    for i, p in enumerate(pts):
        if i and offen((p[0] + pts[i - 1][0]) / 2, (p[1] + pts[i - 1][1]) / 2):
            if len(zug) > 1:
                out.append(zug)
            zug = [p]
            continue
        zug.append(p)
    if len(zug) > 1:
        out.append(zug)
    return out
