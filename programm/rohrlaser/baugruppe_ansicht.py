"""3D-Ansicht einer Schweißbaugruppe wie im Rohr-Editor (Patrick 24.10.2026, Plan B1–B3, Freigabe „1a 2a 3a“).

B1 Bedienung: Leiste über der Ansicht wie im Menüband des Teile-Editors (Blick mit Menü, Ansichtswürfel,
   Darstellung, Nur Gewähltes, Nähte ein/aus, Messen, Winkel, Maße löschen).
B2 Rohre aus den Eingaben des Teile-Editors (rohr3d) in der Einbaulage der STEP-Datei: so gerechnet, wie gezeigt,
   mit den Schlitzen und Nasen der Steckverbindungen (auch noch nicht übernommene aus dem Editor). Ohne Eingaben,
   bei Biegerohr, Knickrahmen oder Anbauteilen bleibt das gemessene STEP-Netz.
B3 Schweißnähte als Raupe: Kehlnaht als Dreieck mit dem a-Maß (Schenkel a·√2 entlang der beiden Flächen),
   Stumpf- und Ecknaht flach mit der Dicke als Breite. Lage und Richtung aus den Flächen der Teile an der Naht
   (Normalen der Flächen um den Nahtpunkt; Berührflächen der beiden Teile heben sich auf). Nähte ohne Verlauf
   bekommen ihn aus dem Stoß (bg['stoesse']): Schnittkante des Steckerendes auf der Aufnahme.

Gleiche Netzform wie ansicht3d (p, t, l); Koordinaten der Baugruppe = Dateilage der STEP-Datei.
"""
import bisect
import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMenu, QSlider, QToolButton, QVBoxLayout, QWidget

from . import rohr3d, schneidweg, steckverbindung as stv
from .ansicht3d import DARSTELLUNGEN, MESS_WINKEL, Ansicht3D, Ansicht3DMitKnoepfen
from .ansicht3d_leiste import blick_menue
from .schneidweg import V_AUSSCHNITT

ZELLE = 10.0            # Raster für die Suche der Flächen an der Naht [mm]
NAH = 0.6               # Flächen bis so viel weiter weg als die nächste zählen zur Naht [mm]
BERUEHRT = 3.0          # ein Teil gehört zur Naht, wenn seine Fläche so nah ist [mm]
GLEICH = 0.9            # cos: Normalen mit kleinerem Winkel gelten als dieselbe Fläche
RAUPE_VORGABE = 3.0     # Größe der Raupe ohne a-Maß/Dicke [mm] (nur Bild, nicht gerechnet)
FLAECHE_FREI = 3.0      # Berührflächen: die größere bleibt frei, wenn sie so viel größer ist
ECKE = 30.0             # Richtungswechsel des Nahtverlaufs über so viel Grad: Raupe in Stücke teilen
ABSTAND_LINIE = 2.0     # Punkte der Naht für die Flächensuche höchstens so weit auseinander [mm]


# ------------------------------------------------------------------ Vektoren
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b, f=1.0):
    return (a[0] + f * b[0], a[1] + f * b[1], a[2] + f * b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _einheit(a):
    lg = math.sqrt(_dot(a, a))
    return (a[0] / lg, a[1] / lg, a[2] / lg) if lg > 1e-12 else None


def abstand_dreieck(q, a, b, c):
    """Abstand Punkt q zum Dreieck a, b, c (nächster Punkt nach Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, aq = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)], [q[k] - a[k] for k in range(3)]
    d1, d2 = _dot(ab, aq), _dot(ac, aq)
    if d1 <= 0 and d2 <= 0:
        return math.dist(q, a)
    bq = [q[k] - b[k] for k in range(3)]
    d3, d4 = _dot(ab, bq), _dot(ac, bq)
    if d3 >= 0 and d4 <= d3:
        return math.dist(q, b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return math.dist(q, [a[k] + v * ab[k] for k in range(3)])
    cq = [q[k] - c[k] for k in range(3)]
    d5, d6 = _dot(ab, cq), _dot(ac, cq)
    if d6 >= 0 and d5 <= d6:
        return math.dist(q, c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return math.dist(q, [a[k] + w * ac[k] for k in range(3)])
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return math.dist(q, [b[k] + w * (c[k] - b[k]) for k in range(3)])
    n = 1.0 / (va + vb + vc)
    v, w = vb * n, vc * n
    return math.dist(q, [a[k] + ab[k] * v + ac[k] * w for k in range(3)])


def _lage_achsen(lage):
    """(Ursprung, X, Y, Z) einer Einbaulage [Ende A, Rohrachse, X-Richtung]."""
    o, z, x = tuple(lage[0:3]), tuple(lage[3:6]), tuple(lage[6:9])
    return o, x, _kreuz(z, x), z


def in_lage(p, lage):
    """Punkt (x, y, z) im Rohrsystem -> Dateilage."""
    o, x, y, z = _lage_achsen(lage)
    return tuple(o[k] + p[0] * x[k] + p[1] * y[k] + p[2] * z[k] for k in range(3))


# ------------------------------------------------------------------ B2 Rohre aus den Eingaben
def eingaben_stecken(positionen, verbindungen, profil_von):
    """Eingaben und Länge der Rohre mit den Steckverbindungen, wie sie im Editor stehen (noch nicht in die Teile
    geschrieben): je Position erst die Schlitze und Nasen aller früheren Verbindungen weg, dann die aktuellen dazu
    (wie AngebotSeite.stecken_anwenden, nur im Speicher). positionen {Positions-ID: Position}, verbindungen:
    gespeicherte Verbindungen, profil_von(Positions-ID) -> Profil. Ergebnis {Positions-ID: (Eingaben, Länge)}."""
    out = {}
    for pid, q in positionen.items():
        profil = profil_von(pid) or {}
        try:
            e = schneidweg.aus_position(schneidweg.lesen(q.get("technik")), q, profil)[0]
        except (ValueError, TypeError, KeyError):
            continue
        laenge = q.get("laenge") if isinstance(q.get("laenge"), (int, float)) else None
        for vid in stv.rollen(q.get("technik")):
            e, weniger = stv.entfernen(e, vid)
            if laenge is not None:
                laenge -= weniger
        out[pid] = [e, laenge]
    for v in verbindungen or ():
        a, s_ = (v.get("aufnahme") or {}).get("id"), (v.get("stecker") or {}).get("id")
        if a not in out or s_ not in out:
            continue
        try:
            out[a][0], out[s_][0], plus = stv.anwenden(v, out[a][0], out[s_][0], profil_von(a) or {},
                                                       profil_von(s_) or {}, (out[a][1], out[s_][1]))
        except ValueError:
            continue
        if out[s_][1] is not None:
            out[s_][1] += plus
    return {pid: (e, lg) for pid, (e, lg) in out.items()}


def eigenes_modell(e, netz_step):
    """True, wenn das Rohr aus den Eingaben gezeichnet werden kann (sonst bleibt das STEP-Netz): kein Biegerohr,
    kein Knickrahmen (V-Ausschnitte), keine Anbauteile im STEP-Netz."""
    if not e or e.get("biegerohr"):
        return False
    if any((z or {}).get("art") == V_AUSSCHNITT for z in e.get("konturen") or ()):
        return False
    return "AN" not in ((netz_step or {}).get("t") or {})


def nasen_winkel(v, lage_auf, lage_st, form_s):
    """Winkel der ersten Nase am Stecker (von Ende A gesehen, 0° oben, 90° vorne) aus der Einbaulage: 'quer' = die
    Nasen liegen hintereinander längs der Aufnahme (Wand des Steckers quer zu ihrer Achse), 'längs' um 90° gedreht.
    Quadrat-/Rechteckrohr auf die nächste Wand gerundet. None ohne Lage."""
    if not lage_auf or not lage_st or len(lage_auf) != 9 or len(lage_st) != 9:
        return None
    _, x_s, y_s, _ = _lage_achsen(lage_st)
    z_a = tuple(lage_auf[3:6])
    lx, ly = _dot(z_a, x_s), _dot(z_a, y_s)
    if math.hypot(lx, ly) < 1e-6:
        return None
    w = math.degrees(math.atan2(-lx, ly))           # Rohrsystem X = −u, Y = v (rohr3d)
    if v.get("waende") == stv.WAENDE[1]:
        w += 90.0
    if int(stv._z(v.get("anzahl"))) == 1 and stv._z(v.get("nase_seite")) < 0:
        w += 180.0              # eine Nase auf der Gegenseite (steckverbindung.nasen_wahl)
    if form_s != "Rundrohr":
        w = round(w / 90.0) * 90.0
    return round(w % 360.0, 3)


def rohr_netz(e, profil, laenge, nasen_w=None):
    """Netz des Rohrs aus den Eingaben, verschoben auf das Ende A der STEP-Messung (Nasen an Ende A ragen über 0
    hinaus). None, wenn es nicht geht."""
    try:
        n = rohr3d.netz(e, profil, laenge, nasen_winkel=nasen_w)
    except (ValueError, TypeError, ZeroDivisionError, KeyError):
        return None
    if not n:
        return None
    nb = stv.nasen((e or {}).get("a"))
    plus_a = float(nb.get("laenge_plus") or 0) if nb else 0.0
    if plus_a:
        p = n["p"]
        for i in range(2, len(p), 3):
            p[i] = round(p[i] - plus_a, 3)
        for art, zuege in (n.get("l") or {}).items():
            for zug in zuege:
                for i in range(2, len(zug), 3):
                    zug[i] = round(zug[i] - plus_a, 3)
        from .schnittkoerper import verschieben
        verschieben(n.get("wk"), -plus_a)
    return n


# ------------------------------------------------------------------ B3 Nähte als Raupe
class Flaechen:
    """Dreiecke des Baugruppen-Netzes in einem Raster (ZELLE), um die Flächen an einer Naht schnell zu finden."""

    def __init__(self, netz, ohne=("SN", "SV", "SH")):
        p = netz.get("p") or []
        self.dreiecke, self.raster, self.huellen, self.raupen = [], {}, [], {}
        for art, idx in (netz.get("t") or {}).items():
            if art in ohne:
                continue
            for i in range(0, len(idx) - 2, 3):
                a, b, c = (tuple(p[3 * idx[i + j]:3 * idx[i + j] + 3]) for j in range(3))
                kreuz = _kreuz(_sub(b, a), _sub(c, a))
                n = _einheit(kreuz)
                if n is None:
                    continue
                nr = len(self.dreiecke)
                self.dreiecke.append((a, b, c, n, math.sqrt(_dot(kreuz, kreuz)) / 2))
                mn, mx = [min(a[k], b[k], c[k]) for k in range(3)], [max(a[k], b[k], c[k]) for k in range(3)]
                self.huellen.append((mn[0], mn[1], mn[2], mx[0], mx[1], mx[2]))
                lo = [math.floor(mn[k] / ZELLE) for k in range(3)]
                hi = [math.floor(mx[k] / ZELLE) for k in range(3)]
                for x in range(lo[0], hi[0] + 1):
                    for y in range(lo[1], hi[1] + 1):
                        for z in range(lo[2], hi[2] + 1):
                            self.raster.setdefault((x, y, z), []).append(nr)

    def an(self, q, weite=BERUEHRT):
        """Flächen nahe q: [(Abstand, Normale, Fläche des Dreiecks)]."""
        c = [math.floor(q[k] / ZELLE) for k in range(3)]
        r = max(1, math.ceil(weite / ZELLE))
        gesehen, out = set(), []
        qx, qy, qz = q
        for x in range(c[0] - r, c[0] + r + 1):
            for y in range(c[1] - r, c[1] + r + 1):
                for z in range(c[2] - r, c[2] + r + 1):
                    for nr in self.raster.get((x, y, z), ()):
                        if nr in gesehen:
                            continue
                        gesehen.add(nr)
                        h = self.huellen[nr]            # Hüllquader + weite: weiter weg kann das Dreieck nicht sein
                        if qx < h[0] - weite or qx > h[3] + weite or qy < h[1] - weite or qy > h[4] + weite or \
                                qz < h[2] - weite or qz > h[5] + weite:
                            continue
                        a, b, c_, n, fl = self.dreiecke[nr]
                        d = abstand_dreieck(q, a, b, c_)
                        if d <= weite:
                            out.append((d, n, fl))
        return out


_FLAECHEN_MERKER = {}       # {(Schlüssel, Punktzahl, Prüfsumme der Punkte): Flaechen} über Editor-Fenster hinweg
FLAECHEN_MERKEN = 4


def flaechen_merken(netz, schluessel=None):
    """Flaechen des Netzes, gemerkt (mit den Raupen darin): das nächste Öffnen derselben Baugruppe sucht die Flächen
    an den Nähten nicht neu. Schlüssel = Inhalt der Punkte (plus schluessel des Aufrufers)."""
    p = netz.get("p") or []
    k = (schluessel, len(p), hash(tuple(p)))
    f = _FLAECHEN_MERKER.pop(k, None) or Flaechen(netz)
    _FLAECHEN_MERKER[k] = f
    while len(_FLAECHEN_MERKER) > FLAECHEN_MERKEN:
        _FLAECHEN_MERKER.pop(next(iter(_FLAECHEN_MERKER)))
    return f


def flaechen_an_naht(flaechen, q):
    """Freie Flächen der Teile am Nahtpunkt q: Liste von Normalen (gleiche Flächen zusammengefasst). Liegen zwei
    Flächen gegeneinander (Normalen entgegen), berühren sich die Teile dort: ist eine viel größer (die Platte neben
    dem Rohr ist frei), fällt nur die kleinere weg (die Stirn des Rohrs), sonst beide (Stumpfstoß)."""
    nah = flaechen.an(q)
    if not nah:
        return []
    dmin = min(d for d, _, _ in nah)
    gruppen = []                # [Normale, Fläche]
    for d, n, fl in sorted(nah, key=lambda x: x[0]):
        if d > dmin + NAH:
            break
        g = next((g for g in gruppen if _dot(n, g[0]) > GLEICH), None)
        if g is None:
            gruppen.append([n, fl])
        else:
            g[1] += fl
    weg = set()
    for i, (n, fl) in enumerate(gruppen):
        for j in range(i + 1, len(gruppen)):
            if _dot(n, gruppen[j][0]) < -GLEICH:
                klein, gross = sorted((fl, gruppen[j][1]))
                if gross > FLAECHE_FREI * klein:
                    weg.add(i if fl < gruppen[j][1] else j)
                else:                       # Stoß gleich großer Flächen (Stumpfnaht): beide berühren sich
                    weg.update((i, j))
    return [g[0] for i, g in enumerate(gruppen) if i not in weg]


def querschnitt_raupe(nahtart, groesse, normalen, t):
    """Querschnitt der Raupe am Nahtpunkt (Punkte relativ zum Nahtpunkt) aus den freien Flächen (normalen) und der
    Richtung t der Naht. Kehlnaht: Dreieck mit Schenkeln a·√2 entlang der beiden Flächen; sonst flach (Breite =
    groesse, Höhe ein Viertel). None ohne passende Flächen."""
    ns = []
    for n in normalen:
        if abs(_dot(n, t)) > 0.5:                       # Fläche quer zur Naht (Ecke des Linienzugs): zählt nicht
            continue
        m = _einheit(_add(n, t, -_dot(n, t)))           # quer zur Naht
        if m is not None:
            ns.append(m)
    if not ns:
        return None
    b = (0.0, 0.0, 0.0)
    for n in ns:
        b = _add(b, n)
    b = _einheit(b)
    if b is None:
        return None
    s = _einheit(_kreuz(t, b))
    if s is None:
        return None
    if nahtart == "Kehlnaht":
        z = groesse * math.sqrt(2.0)
        if len(ns) == 2 and _dot(ns[0], ns[1]) < 0.95:
            d1 = _einheit(_add(ns[1], ns[0], -_dot(ns[1], ns[0])))     # entlang Fläche 1, weg von Fläche 2
            d2 = _einheit(_add(ns[0], ns[1], -_dot(ns[0], ns[1])))
            if d1 is not None and d2 is not None:
                return [(0.0, 0.0, 0.0), tuple(z * c for c in d1), tuple(z * c for c in d2)]
        h = math.sqrt(0.5)
        return [(0.0, 0.0, 0.0), tuple(z * h * (b[k] + s[k]) for k in range(3)),
                tuple(z * h * (b[k] - s[k]) for k in range(3))]
    w = max(groesse, 2.0)
    return [tuple(-w / 2 * c for c in s), tuple(w / 2 * c for c in s), tuple(min(w / 4, 2.0) * c for c in b)]


def _punkte(zug):
    pts = []
    for i in range(0, len(zug) - 2, 3):
        q = (float(zug[i]), float(zug[i + 1]), float(zug[i + 2]))
        if not pts or math.dist(pts[-1], q) > 1e-6:
            pts.append(q)
    return pts


def _verdichten(pts, schritt=ABSTAND_LINIE):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:], strict=False):
        n = max(1, math.ceil(math.dist(a, b) / schritt))
        out += [tuple(a[k] + (b[k] - a[k]) * i / n for k in range(3)) for i in range(1, n + 1)]
    return out


def _abschnitte(pts, knick=ECKE):
    """Linienzug an Ecken (Richtungswechsel über knick Grad) teilen; der Eckpunkt gehört zu beiden Stücken."""
    out, stueck = [], [pts[0]]
    for i in range(1, len(pts)):
        stueck.append(pts[i])
        if i < len(pts) - 1:
            a, b = _einheit(_sub(pts[i], pts[i - 1])), _einheit(_sub(pts[i + 1], pts[i]))
            if a and b and _dot(a, b) < math.cos(math.radians(knick)):
                out.append(stueck)
                stueck = [pts[i]]
    out.append(stueck)
    return [s_ for s_ in out if len(s_) > 1]


def raupe(zug, nahtart, groesse, flaechen):
    """Raupe entlang eines Linienzugs (flach [x, y, z, …] in Dateilage): (Punkte, Dreiecke als Punktnummern) oder
    None, wenn an keinem Punkt Flächen der Teile liegen. An Ecken des Zugs beginnt ein neues Stück. Je Flaechen
    gemerkt (Klick im Baum, Nur Gewähltes: dieselben Raupen ohne neue Flächensuche); Ergebnis nur lesen."""
    merker = getattr(flaechen, "raupen", None)
    if merker is None:
        return _raupe(zug, nahtart, groesse, flaechen)
    schluessel = (tuple(zug), nahtart, groesse)
    if schluessel not in merker:
        merker[schluessel] = _raupe(zug, nahtart, groesse, flaechen)
    return merker[schluessel]


def _raupe(zug, nahtart, groesse, flaechen):
    pts = _punkte(zug)
    if len(pts) < 2:
        return None
    punkte, dreiecke = [], []
    for stueck in _abschnitte(pts):
        r = _raupe_stueck(_verdichten(stueck), nahtart, groesse, flaechen)
        if r:
            basis = len(punkte) // 3
            punkte.extend(r[0])
            dreiecke.extend(basis + i for i in r[1])
    return (punkte, dreiecke) if dreiecke else None


def _raupe_stueck(pts, nahtart, groesse, flaechen):
    n = len(pts)
    quer = []
    for i, q in enumerate(pts):
        t = _einheit(_sub(pts[min(i + 1, n - 1)], pts[max(i - 1, 0)]))
        quer.append(querschnitt_raupe(nahtart, groesse, flaechen_an_naht(flaechen, q), t) if t else None)
    if not any(quer):
        return None
    def richtung(qs):
        return _einheit(tuple(sum(v[k] for v in qs) for k in range(3))) if qs else None
    for i in range(n):              # Ausreißer (fremde Flächen, Ecken, Schlitze am Punkt): Querschnitt des Nachbarn
        nb = [quer[j] for j in (i - 2, i - 1, i + 1, i + 2) if 0 <= j < n and quer[j]]
        r, rn = richtung(quer[i]), [richtung(q) for q in nb]
        rn = [x for x in rn if x]
        if r and len(rn) >= 2 and all(_dot(a, b) > 0.95 for a in rn for b in rn) and _dot(r, rn[0]) < 0.85:
            quer[i] = nb[0]
    for i in range(n):              # Lücken mit dem Querschnitt des Nachbarn füllen
        if quer[i] is None:
            quer[i] = next((quer[j] for j in sorted(range(n), key=lambda j: abs(j - i)) if quer[j]), None)
    punkte, dreiecke = [], []

    def dreieck(a, b, c, soll):
        if _dot(_kreuz(_sub(b, a), _sub(c, a)), soll) < 0:
            b, c = c, b
        for v in (a, b, c):
            dreiecke.append(len(punkte) // 3)
            punkte.extend(round(x, 3) for x in v)

    ringe = [[_add(q, d) for d in qs] for q, qs in zip(pts, quer, strict=False)]
    # nur die freien Seiten: Kehlnaht die Nahtoberfläche (die Schenkel liegen an den Teilen), sonst beide Flanken
    sichtbar = [1] if nahtart == "Kehlnaht" else [1, 2]
    for r0, r1 in zip(ringe, ringe[1:], strict=False):
        mitte = tuple(sum(v[k] for v in r0 + r1) / 6 for k in range(3))
        for k in sichtbar:
            a, b = r0[k], r0[(k + 1) % 3]
            c, d = r1[(k + 1) % 3], r1[k]
            soll = _sub(tuple((a[j] + b[j] + c[j] + d[j]) / 4 for j in range(3)), mitte)
            dreieck(a, b, c, soll)
            dreieck(a, c, d, soll)
    for ring, nach in ((ringe[0], _sub(pts[0], pts[1])), (ringe[-1], _sub(pts[-1], pts[-2]))):
        dreieck(ring[0], ring[1], ring[2], nach)
    return punkte, dreiecke


def naehte_einsetzen(netz, naehte, flaechen=None):
    """Nähte in das Netz der Baugruppe: naehte = [(Art SN/SV/SH, Linienzüge, Nahtart, Größe [mm] oder None)].
    Raupen als Dreiecke der Art (von nahem), dazu der Linienzug (immer sichtbar, von weitem). Ändert netz.
    Ergebnis: Anzahl Raupen."""
    if flaechen is None:
        flaechen = Flaechen(netz)
    p, t = netz["p"], netz.setdefault("t", {})
    linien, n = {a: list(z) for a, z in (netz.get("l") or {}).items()}, 0     # z. B. Längsnähte NL bleiben
    for art, zuege, nahtart, groesse in naehte:
        for zug in zuege or ():
            linien.setdefault(art, []).append(zug)       # Linie bleibt: von weitem und verdeckt sichtbar
            r = raupe(zug, nahtart, groesse or RAUPE_VORGABE, flaechen)
            if r is None:
                continue
            basis = len(p) // 3
            p.extend(r[0])
            t.setdefault(art, []).extend(basis + i for i in r[1])
            n += 1
    netz["l"] = linien
    netz["ln"] = {a: [(0.0, 0.0, 0.0)] * len(z) for a, z in linien.items()}    # Linien immer sichtbar
    return n


def verlauf_aus_stoss(naht, stoesse, koerper_netz):
    """Nahtverlauf einer Nahtgruppe ohne Verlauf aus den Stößen der STEP-Messung (3a): je Stoß zwischen zwei Körpern
    der Nahtgruppe die Schnittkante des Steckerendes (längster Linienzug Anfangs- bzw. Endschnitt) in Dateilage.
    koerper_netz {Körpernummer: (Netz, Lage)}. Ergebnis: Linienzüge (leer = nicht ableitbar)."""
    koerper = {str(k) for k in naht.get("koerper") or ()}
    out = []
    for s_ in stoesse or ():
        if not isinstance(s_, dict) or str(s_.get("stecker")) not in koerper or \
                str(s_.get("aufnahme")) not in koerper or s_.get("ende") not in ("a", "b"):
            continue
        netz, lage = koerper_netz.get(str(s_.get("stecker"))) or (None, None)
        zuege = ((netz or {}).get("l") or {}).get("EA" if s_["ende"] == "a" else "EB") or []
        if not zuege or not lage:
            continue
        zug = max(zuege, key=lambda z: sum(math.dist(a, b) for a, b in zip(_punkte(z), _punkte(z)[1:], strict=False)))
        out.append([round(c, 3) for q in _punkte(zug) for c in in_lage(q, lage)])
    return out


# ------------------------------------------------------------------ Satz in 3D: Teile und Längsnaht
def teil_kennung(netz, bereiche, kennungen):
    """Kennung je Dreieck (netz 'ti') aus den Bereichen von ansicht3d.baugruppe: kennungen[Nummer im Netz-Liste],
    damit ein Klick auf eine Fläche sein Teil findet. Ändert netz."""
    grenzen = sorted((von, bis, kennungen[nr]) for nr, von, bis, _ in bereiche)
    starts = [g[0] for g in grenzen]

    def von(i):
        k = bisect.bisect_right(starts, i) - 1
        return grenzen[k][2] if k >= 0 and i < grenzen[k][1] else None
    netz["ti"] = {art: [von(idx[n]) for n in range(0, len(idx) - 2, 3)] for art, idx in netz["t"].items()}
    return netz


def _spannen(netz):
    """(halbe Breite X, halbe Höhe Y, z von, z bis) eines Netzes im Rohrsystem."""
    p = netz.get("p") or [0, 0, 0]
    xs, ys, zs = p[0::3], p[1::3], p[2::3]
    return (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2, min(zs), max(zs)


def _hochkant(netz, form):
    """True, wenn die Breitseite eines Rechteckrohrs im Rohrsystem senkrecht steht (Bezug der Naht: Breitseite oben,
    naht.py)."""
    bx, by, _, _ = _spannen(netz)
    return form == "Rechteckrohr" and by > bx + 0.5


def laengsnaht_winkel(punkt, lage, netz, form):
    """Nahtwinkel (naht.py: von Ende A gesehen 0° oben, 90° rechts, im Bezug Breitseite oben) für einen Klick auf die
    Fläche eines Rohrs: Quadrat-/Rechteckrohr die Mitte der angeklickten Wand, Rundrohr auf 1° gerundet. None ohne
    Lage oder auf der Achse."""
    if not lage or len(lage) != 9:
        return None
    o, x, y, _ = _lage_achsen(lage)
    d = _sub(punkt, o)
    lx, ly = _dot(d, x), _dot(d, y)
    if math.hypot(lx, ly) < 1e-6:
        return None
    if form in ("Quadratrohr", "Rechteckrohr"):
        bx, by, _, _ = _spannen(netz)
        lx, ly = lx / max(bx, 1e-6), ly / max(by, 1e-6)        # Wand: größter Anteil am halben Querschnitt
        lx, ly = (lx, 0.0) if abs(lx) >= abs(ly) else (0.0, ly)
    w = math.degrees(math.atan2(-lx, ly))
    if _hochkant(netz, form):
        w -= 90.0
    return round(w % 360.0, 0 if form != "Rundrohr" else 1) % 360.0


def laengsnaht_linie(lage, netz, winkel, form):
    """Längsnaht (Winkel wie laengsnaht_winkel) als Linie über die ganze Länge des Rohrs in der Dateilage, knapp
    außen auf der Wand (wie die Linie NL des Rohr-Editors). [x, y, z, x, y, z] oder None."""
    if winkel is None or not lage or len(lage) != 9 or not netz.get("p"):
        return None
    bx, by, z0, z1 = _spannen(netz)
    w = math.radians(float(winkel) + (90.0 if _hochkant(netz, form) else 0.0))
    ux, uy = -math.sin(w), math.cos(w)
    if form == "Rundrohr":
        f = max(bx, by)
    else:
        f = min(bx / abs(ux) if abs(ux) > 1e-9 else 1e18, by / abs(uy) if abs(uy) > 1e-9 else 1e18)
    f += 0.4
    return [round(c, 3) for z in (z0, z1) for c in in_lage((ux * f, uy * f, z), lage)]


# ------------------------------------------------------------------ B1 Bedienung
class BaugruppenAnsicht(QWidget):
    """3D-Ansicht der Baugruppe mit Leiste wie im Teile-Editor. Wie Ansicht3DMitKnoepfen: .ansicht, .info,
    setzen(netz, titel, info). geaendert() ruft der Besitzer nach „Nur Gewähltes“ und „Nähte“ neu auf (zeichnet
    die Baugruppe neu); vor_messen() vor dem Messen (z. B. Naht zeichnen aus)."""

    def __init__(self, geaendert=None, vor_messen=None, parent=None):
        super().__init__(parent)
        self.geaendert, self.vor_messen = geaendert, vor_messen
        self.d3 = Ansicht3DMitKnoepfen()
        for b in self.d3.knoepfe.findChildren(QWidget):          # Blickrichtung übernimmt die Leiste
            if b.parent() is self.d3.knoepfe and b is not self.d3.modi:
                b.hide()
        self.ansicht, self.info = self.d3.ansicht, self.d3.info
        self.ansicht.flaeche_vor_kante = True     # Klick auf eine Kante wählt das Teil dahinter (Auswahl im 3D)
        self.nur_gewaehlt, self.naehte = False, True
        leiste = QWidget()
        self._leiste = ll = QHBoxLayout(leiste)
        ll.setContentsMargins(0, 0, 0, 0)
        knopf = self.knopf
        blick = blick_menue(QMenu(self), self.ansicht)        # dasselbe Menü wie in allen 3D-Fenstern (3E-11)
        self.blick_knopf = knopf("Blick", "Isometrie; Pfeil: Vorn, Hinten, Oben, Unten, Ende A, Ende B, Auf Auswahl, "
                                 "um 90° drehen, Perspektivisch (oder den Ansichtswürfel anklicken)",
                                 wenn=lambda: self.ansicht.ansicht(*Ansicht3D.GRUND))
        self.blick_knopf.setMenu(blick)
        self.blick_knopf.setPopupMode(QToolButton.MenuButtonPopup)
        self.darstellung = QComboBox()
        self.darstellung.addItems(DARSTELLUNGEN)
        self.darstellung.setToolTip("Schattiert = Flächen, Mit Kanten = dazu die Körperkanten, Durchsichtig = Röntgen "
                                    "(verdeckte Teile und Nähte sichtbar)")
        self.darstellung.currentTextChanged.connect(lambda t: self.ansicht.darstellung_setzen(t))
        ll.addWidget(self.darstellung)
        self.nur_knopf = knopf("Nur Gewähltes", "Nur die gewählten Teile (blau) zeigen, die anderen ausblenden",
                               True, lambda an: self._umschalten("nur_gewaehlt", an))
        self.naehte_knopf = knopf("Nähte", "Schweißnähte als Raupe zeigen (schwarz, Vorschläge magenta, gewählte rot)",
                                  True, lambda an: self._umschalten("naehte", an))
        self.naehte_knopf.blockSignals(True)        # Vorgabe an, ohne geaendert() (zeichnet der Besitzer selbst)
        self.naehte_knopf.setChecked(True)
        self.naehte_knopf.blockSignals(False)
        self.messen_knopf = knopf("Messen", "Zwei Punkte am Modell anklicken (fängt Kreismitte, Kantenmitte, Ecke "
                                  "oder Fläche): Ergebnis mit Kernwerten in der Mess-Tafel; das Maß bleibt stehen", True, lambda an: self._messen(an))
        self.winkel_knopf = knopf("Winkel", "Drei Punkte anklicken, der mittlere ist der Scheitel: Winkel in Grad",
                                  True, lambda an: self._messen(an, MESS_WINKEL))
        knopf("Maße löschen", "Alle stehenden Maße entfernen", wenn=lambda: self._masse_loeschen())
        self.mass = QLabel()
        ll.addWidget(self.mass, 1)
        self._lay = lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(leiste)
        lay.addWidget(self.d3, 1)
        self.montage = None             # Leiste Montagefolge (montage_leiste), sonst None
        self.wuerfel = self.d3.wuerfel
        self.ansicht.gemessen.connect(lambda _: self._mass_zeigen())

    def knopf(self, text, tipp, umschalter=False, wenn=None):
        """Knopf der Leiste (vor der Maßanzeige); der Besitzer ergänzt so eigene Werkzeuge (Satz in 3D)."""
        k = QToolButton()
        k.setText(text)
        k.setToolTip(tipp)
        k.setCheckable(umschalter)
        k.setAutoRaise(False)
        if wenn is not None:
            (k.toggled if umschalter else k.clicked).connect(wenn)
        mass = getattr(self, "mass", None)
        self._leiste.insertWidget(self._leiste.indexOf(mass) if mass is not None else self._leiste.count(), k)
        return k

    def montage_leiste(self):
        """Knopf „Montage“ und darunter die Leiste Montagefolge (A6): Schieber Schritt (1 … alle) und Explosion
        (0 … 100 %). Der Besitzer liest montage_zustand() und setzt mit montage_schritte(n) die Zahl der Schritte."""
        self.montage_knopf = self.knopf(
            "Montage", "Montagefolge der Steckverbindungen: Schritt für Schritt aufbauen und Explosionsansicht (jedes "
            "Teil rückt gegen seine Steckrichtung heraus)", True, lambda an: self._montage_an(an))
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel("Schritt"))
        self.montage_schritt = QSlider(Qt.Horizontal)
        self.montage_schritt.setRange(1, 1)
        self.montage_schritt.setMaximumWidth(220)
        self.montage_schritt.setToolTip("Bis zu diesem Schritt aufgebaut, der aktuelle Schritt blau; ganz rechts = alles")
        h.addWidget(self.montage_schritt)
        h.addWidget(QLabel("Explosion"))
        self.montage_explosion = QSlider(Qt.Horizontal)
        self.montage_explosion.setRange(0, 100)
        self.montage_explosion.setMaximumWidth(160)
        self.montage_explosion.setToolTip("0 = zusammengesteckt, 100 % = jedes Teil um die halbe größte Teillänge "
                                          "gegen seine Steckrichtung herausgerückt")
        h.addWidget(self.montage_explosion)
        self.montage_text = QLabel()
        self.montage_text.setWordWrap(True)
        h.addWidget(self.montage_text, 1)
        for sch in (self.montage_schritt, self.montage_explosion):
            sch.valueChanged.connect(lambda _: self.geaendert() if self.geaendert is not None else None)
        w.hide()
        self._lay.insertWidget(1, w)
        self.montage = w
        return w

    def _montage_an(self, an):
        if self.montage is not None:
            self.montage.setVisible(bool(an))
        if self.geaendert is not None:
            self.geaendert()

    def montage_zustand(self):
        """(Schritt, Explosion 0 … 1) bei eingeschalteter Montage, sonst None; Schritt = Maximum heißt alles."""
        if self.montage is None or not self.montage_knopf.isChecked():
            return None
        return self.montage_schritt.value(), self.montage_explosion.value() / 100.0

    def montage_schritte(self, n):
        """Zahl der Schritte setzen (ohne neu zu zeichnen); neu eingeschaltet steht der Schieber auf alles."""
        sch = self.montage_schritt
        n = max(int(n), 1)
        if sch.maximum() != n:
            alle = sch.value() >= sch.maximum()
            sch.blockSignals(True)
            sch.setMaximum(n)
            if alle:
                sch.setValue(n)
            sch.blockSignals(False)

    def setzen(self, netz, titel="", info=""):
        """Netz zeigen; die Blickrichtung bleibt, wenn schon eins da war (Auswahl im Baum, Nähte ein/aus)."""
        a = self.ansicht
        alt = a.netz is not None
        blick = (a.gier, a.nick, a.zoom, a.versatz)
        masse = list(a.masse_fest)
        messen = (a.messen, a.mess_max, a.mess_art)
        self.d3.setzen(netz, titel, info)
        if alt and a.netz is not None:
            a.gier, a.nick, a.zoom, a.versatz = blick
            a.masse_fest = masse
            if messen[0]:
                a.messen, a.mess_max, a.mess_art = messen
            a.update()

    def _umschalten(self, attr, an):
        setattr(self, attr, bool(an))
        if self.geaendert is not None:
            self.geaendert()

    def messen_aus(self):
        for k in (self.messen_knopf, self.winkel_knopf):
            k.blockSignals(True)
            k.setChecked(False)
            k.blockSignals(False)
        self.mass.setText("")

    def _messen(self, an, art=None):
        andere = self.winkel_knopf if art is None else self.messen_knopf
        if an and andere.isChecked():
            andere.blockSignals(True)
            andere.setChecked(False)
            andere.blockSignals(False)
        if an and self.vor_messen is not None:
            self.vor_messen()
        self.ansicht.messen_setzen(an, art=art)
        self.mass.setText(("Drei Punkte anklicken, der mittlere ist der Scheitel" if art == MESS_WINKEL
                           else "Zwei Punkte anklicken") if an else "")

    def _mass_zeigen(self):
        a = self.ansicht
        if a.messen and a.mess_max and (self.messen_knopf.isChecked() or self.winkel_knopf.isChecked()):
            self.mass.setText(a.mess_text() or "")

    def _masse_loeschen(self):
        self.ansicht.masse_loeschen()
        self.mass.setText("")
