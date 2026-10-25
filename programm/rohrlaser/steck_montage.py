"""Steckbarkeit einer Baugruppe prüfen (Plan „Baugruppen automatisch“ A5, Patrick 25.10.2026 „Alle a“).

Jede Steckverbindung verlangt eine Fügerichtung: der Stecker schiebt sich mit seinem Ende längs der eigenen Achse in
die Schlitze der Aufnahme (Ende A in Richtung −Z des Rohrs, Ende E in Richtung +Z), die Aufnahme kommt umgekehrt
auf schon liegende Stecker. Ein Teil lässt sich nur dazustecken, wenn alle seine Verbindungen zu schon liegenden
Teilen dieselbe Richtung verlangen. Gesucht ist eine Reihenfolge (je Gruppe zusammenhängender Teile), in der jedes
Teil so dazukommt; gibt es keine, ist die Baugruppe so nicht steckbar (Warnung, z. B. ein Stecker mit Nasen an beiden
Enden zwischen zwei schon liegenden Aufnahmen).

Dazu örtliche Prüfungen je Rohr: Schlitz überschneidet eine andere Kontur, feste Längsnaht liegt auf einem Schlitz
oder einer Nase. Die Reihenfolge nutzt später die Montagefolge (A6) und das Montageblatt (A7)."""
import math

from . import skizze as sk
from . import steckverbindung as stv

GRAD = 5.0                      # Richtungen gleich bis zu diesem Winkel [°]


def _einheit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v) if n > 1e-12 else None


def _gleich(a, b):
    return sum(x * y for x, y in zip(a, b)) >= math.cos(math.radians(GRAD))


def kanten(koerper, stoesse, verbindungen):
    """Steckstöße zwischen Körpern: [(Körper Aufnahme, Körper Stecker, Fügerichtung des Steckers)] für jeden Stoß
    der STEP-Messung, zu dem es eine Verbindung (Aufnahme-ID, Stecker-ID, Ende) gibt. koerper {Körper: (Positions-ID,
    Einbaulage [Ende A, Rohrachse, X])}."""
    paare = {(str(a), str(s_), e) for a, s_, e in verbindungen}
    out = []
    for st in stoesse or ():
        if not isinstance(st, dict) or st.get("ende") not in ("a", "b"):
            continue
        ka, ks = str(st.get("aufnahme")), str(st.get("stecker"))
        if ka not in koerper or ks not in koerper or ka == ks:
            continue
        if (str(koerper[ka][0]), str(koerper[ks][0]), st["ende"]) not in paare:
            continue
        lage = koerper[ks][1]
        z = _einheit(lage[3:6]) if lage and len(lage) == 9 else None
        if z is None:
            continue
        d = tuple(-c for c in z) if st["ende"] == "a" else z
        out.append((ka, ks, d))
    return out


def _richtungen(k, gesetzt, kanten_):
    """Verlangte Fügerichtungen des Körpers k zu den schon gesetzten Körpern."""
    out = []
    for ka, ks, d in kanten_:
        if ks == k and ka in gesetzt:
            out.append((d, ka))
        elif ka == k and ks in gesetzt:
            out.append((tuple(-c for c in d), ks))
    return out


SUCHE = 20000                   # Schritte der Suche je Gruppe (danach das beste bis dahin)


def _versuch(start, knoten, kanten_, budget):
    """Tiefensuche nach einer Steckfolge ab start: (Schritte, nicht gesetzte Körper) der längsten gefundenen Folge.
    Ein Teil, das zu früh zwischen zwei liegende Teile käme, wird später versucht (Zurückgehen)."""
    best = [[(start, None)], knoten - {start}]
    gesehen = set()

    def tief(gesetzt, schritte):
        if budget[0] <= 0 or not best[1]:
            return
        budget[0] -= 1
        if len(knoten - gesetzt) < len(best[1]):
            best[0], best[1] = list(schritte), knoten - gesetzt
            if not best[1]:
                return
        schluessel = frozenset(gesetzt)
        if schluessel in gesehen:
            return
        gesehen.add(schluessel)
        for k in sorted(knoten - gesetzt, key=_sort):
            r = _richtungen(k, gesetzt, kanten_)
            if r and all(_gleich(r[0][0], d) for d, _ in r):
                tief(gesetzt | {k}, schritte + [(k, r[0][0])])
                if not best[1]:
                    return
    tief(frozenset({start}), [(start, None)])
    return best[0], best[1]


def _sort(k):
    return (len(k), k)


def _gruppen(kanten_):
    nachbar = {}
    for ka, ks, _ in kanten_:
        nachbar.setdefault(ka, set()).add(ks)
        nachbar.setdefault(ks, set()).add(ka)
    rest, out = set(nachbar), []
    while rest:
        k = min(rest, key=_sort)
        teil, offen = set(), [k]
        while offen:
            x = offen.pop()
            if x not in teil:
                teil.add(x)
                offen.extend(nachbar[x] - teil)
        rest -= teil
        out.append(teil)
    return out


def reihenfolge(kanten_):
    """Steckfolge: dict(ok, schritte = [(Körper, Fügerichtung oder None für das erste Teil der Gruppe)],
    offen = [Körper, die so nicht dazukommen], gruppen = Anzahl). Je Gruppe wird jedes Teil als Anfang probiert."""
    schritte, offen = [], []
    gruppen = _gruppen(kanten_)
    for knoten in gruppen:
        best, budget = None, [SUCHE]
        for start in sorted(knoten, key=_sort):
            s_, rest = _versuch(start, knoten, kanten_, budget)
            if best is None or len(rest) < len(best[1]):
                best = (s_, rest)
            if not rest:
                break
        schritte += best[0]
        offen += sorted(best[1], key=_sort)
    return dict(ok=not offen, schritte=schritte, offen=offen, gruppen=len(gruppen))


def konflikt(k, schritte, kanten_):
    """Text, warum Körper k nicht dazukommt (verschiedene Richtungen zu welchen Teilen)."""
    gesetzt = {x for x, _ in schritte}
    r = _richtungen(k, gesetzt, kanten_)
    if not r:
        return "hängt nur an Teilen, die selbst nicht gesteckt werden können"
    return "müsste zugleich in verschiedene Richtungen geschoben werden (zu Körper " + \
        ", ".join(sorted({x for _, x in r}, key=_sort)) + ")"


# ------------------------------------------------------------------ örtliche Prüfungen je Rohr
def _rechteck(qs, k):
    """(x0, x1, s0, s1) einer Kontur aus sk.lagen."""
    ein = k["eingabe"]
    pts = sk.umriss_kontur(ein) or [(0.0, 0.0)]
    m = sk.s_lage(qs, ein)
    return (k["x"] + min(p[0] for p in pts), k["x"] + max(p[0] for p in pts),
            m + min(p[1] for p in pts), m + max(p[1] for p in pts))


def _schneiden(a, b, umfang):
    if not (a[0] < b[1] and b[0] < a[1]):
        return False
    ma, mb = (a[2] + a[3]) / 2, (b[2] + b[3]) / 2
    ds = (ma - mb + umfang / 2) % umfang - umfang / 2
    return abs(ds) < (a[3] - a[2]) / 2 + (b[3] - b[2]) / 2


def schlitz_ueberschneidungen(profil, e, laenge):
    """Schlitze einer Steckverbindung, die eine andere Kontur (auch Schlitze anderer Verbindungen) überschneiden:
    [Text]."""
    if (profil or {}).get("form") not in stv.FORMEN or not laenge:
        return []
    qs = sk.Querschnitt(profil)
    liste = [(k, _rechteck(qs, k)) for k in sk.lagen((e or {}).get("konturen") or (), laenge, qs)]
    out = []
    for i, (k, r) in enumerate(liste):
        q = str(k["eingabe"].get("quelle") or "")
        if not q.startswith(stv.HERKUNFT + " "):
            continue
        for j, (k2, r2) in enumerate(liste):
            q2 = str(k2["eingabe"].get("quelle") or "")
            if j == i or q2 == q or (q2.startswith(stv.HERKUNFT + " ") and j < i):
                continue
            if _schneiden(r, r2, qs.umfang):
                out.append(f"Schlitz bei x {k['x']:.0f} mm überschneidet {sk.kurz(k2['eingabe'])} bei x "
                           f"{k2['x']:.0f} mm")
                break
    return out


def naht_auf_schlitz(profil, e, laenge, winkel):
    """True, wenn die feste Längsnaht (Winkel) auf einem Schlitz oder einer Nase liegt."""
    from . import baugruppe_vorschlaege as bv
    if winkel is None or (profil or {}).get("form") not in stv.FORMEN:
        return False
    qs = sk.Querschnitt(profil)
    s = sk.naht_s(qs, winkel)
    if s is None:
        return False
    ee = dict(e or {}, konturen=[z for z in (e or {}).get("konturen") or ()
                                 if str(z.get("quelle") or "").startswith(stv.HERKUNFT + " ")])
    return not bv._frei(s, bv.belegt(qs, ee, laenge), qs.umfang)
