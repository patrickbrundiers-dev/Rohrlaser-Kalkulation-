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
    return sum(x * y for x, y in zip(a, b, strict=False)) >= math.cos(math.radians(GRAD))


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


# ------------------------------------------------------------------ Montagefolge und Explosion (A6), Montageblatt (A7)
ACHSEN = (((1, 0, 0), "+X"), ((-1, 0, 0), "−X"), ((0, 1, 0), "+Y"), ((0, -1, 0), "−Y"), ((0, 0, 1), "+Z"),
          ((0, 0, -1), "−Z"))


def richtung_text(d):
    """Fügerichtung als Text: nächste Achse der Datei (+X …), sonst die Richtung gerundet."""
    if d is None:
        return ""
    a, t = max(ACHSEN, key=lambda x: sum(p * q for p, q in zip(x[0], d, strict=False)))
    if sum(p * q for p, q in zip(a, d, strict=False)) >= math.cos(math.radians(GRAD)):
        return t
    return "(" + "; ".join(f"{c:.2f}".replace(".", ",") for c in d) + ")"


def koerper_aus_netzen(netze):
    """{Körper: (Positions-ID, Einbaulage)} und {Körper: (Punkt Ende A, Punkt Ende E)} in Dateilage aus den Netzen
    der Teile {Positions-ID: Netz (entpackt)}."""
    from .baugruppe_ansicht import _spannen, in_lage
    koerper, enden = {}, {}
    for pid, netz in (netze or {}).items():
        if not netz or not netz.get("p"):
            continue
        nummern = netz.get("koerper") or []
        _, _, z0, z1 = _spannen(netz)
        for j, lage in enumerate(netz.get("lagen") or ([netz["lage"]] if netz.get("lage") else [])):
            if j < len(nummern) and lage and len(lage) == 9:
                koerper[str(nummern[j])] = (pid, lage)
                enden[str(nummern[j])] = (in_lage((0.0, 0.0, z0), lage), in_lage((0.0, 0.0, z1), lage))
    return koerper, enden


def explosion(schritte, kanten_, enden, faktor=1.0):
    """Versatz je Körper für die Explosionsansicht: jedes gesteckte Teil rückt gegen seine Fügerichtung aus dem Teil,
    an dem es steckt, um faktor × halbe größte Teillänge, und nimmt den Versatz dieses Teils mit (Unterbaugruppen
    bleiben zusammen). {Körper: (dx, dy, dz)}; Körper ohne Steckverbindung bleiben stehen."""
    lang = max((math.dist(a, b) for a, b in enden.values()), default=0.0)
    weit = faktor * max(lang / 2, 20.0)
    out, gesetzt = {}, set()
    for k, d in schritte:
        basis = (0.0, 0.0, 0.0)
        if d is not None:
            partner = next((p for dd, p in _richtungen(k, gesetzt, kanten_) if _gleich(dd, d)), None)
            basis = out.get(partner, basis)
            basis = tuple(b - c * weit for b, c in zip(basis, d, strict=False))
        out[k] = basis
        gesetzt.add(k)
    return out


def schritt_texte(schritte, kanten_, koerper, name, marken=None):
    """Je Schritt der Steckfolge ein Text: [dict(nr, koerper, teil, text, richtung)]. name {Positions-ID: Text},
    marken {(Körper Aufnahme, Körper Stecker): Marke}."""
    marken = marken or {}
    out, gesetzt = [], set()
    for nr, (k, d) in enumerate(schritte, 1):
        pid = koerper.get(k, (None,))[0]
        if d is None:
            text = "hinlegen (Anfang)"
        else:
            teile = []
            for ka, ks, dd in kanten_:
                if ks == k and ka in gesetzt:
                    p = name.get(koerper[ka][0], "?")
                    teile.append(f"in {p} stecken" + (f" (Marke {marken[(ka, ks)]})" if marken.get((ka, ks)) else ""))
                elif ka == k and ks in gesetzt:
                    p = name.get(koerper[ks][0], "?")
                    teile.append(f"auf {p} aufstecken" + (f" (Marke {marken[(ka, ks)]})" if marken.get((ka, ks))
                                                         else ""))
            text = ", ".join(teile)
        out.append(dict(nr=nr, koerper=k, teil=name.get(pid, "?"), text=text, richtung=richtung_text(d)))
        gesetzt.add(k)
    return out


def montage_folge(positionen, verbindungen, stoesse, netze):
    """Montagefolge einer Baugruppe bzw. eines Satzes ohne Editor (Montageblatt): positionen {Positions-ID:
    Position}, verbindungen = gespeicherte Steckverbindungen (aufnahme/stecker mit id), stoesse aus der STEP-Messung,
    netze {Positions-ID: Netz entpackt}. None ohne Steckstöße, sonst dict(ok, schritte (Texte), offen [Teil], enden,
    versatz, nummer {Körper: Schritt})."""
    koerper, enden = koerper_aus_netzen({pid: n for pid, n in (netze or {}).items() if pid in positionen})
    verb = [((v.get("aufnahme") or {}).get("id"), (v.get("stecker") or {}).get("id"),
             (v.get("stecker") or {}).get("ende") or "a") for v in verbindungen or ()]
    kanten_ = kanten(koerper, stoesse, verb)
    if not kanten_:
        return None
    marke = {(a, s_, e): str(v.get("marke") or "").strip() for (a, s_, e), v in zip(verb, verbindungen or (), strict=False)}
    marken = {}
    for st in stoesse or ():
        if isinstance(st, dict) and str(st.get("aufnahme")) in koerper and str(st.get("stecker")) in koerper:
            ka, ks = str(st["aufnahme"]), str(st["stecker"])
            m = marke.get((koerper[ka][0], koerper[ks][0], st.get("ende")))
            if m:
                marken[(ka, ks)] = m
    erg = reihenfolge(kanten_)
    name = {}
    for pid, q in positionen.items():
        t = " ".join(str(x) for x in (q.get("artikel"), q.get("bezeichnung")) if x)
        name[pid] = f"Pos. {q.get('pos') or ''}" + (f" {t}" if t else "")
    return dict(ok=erg["ok"], schritte=schritt_texte(erg["schritte"], kanten_, koerper, name, marken),
                offen=[name.get(koerper[k][0], k) for k in erg["offen"]], enden=enden,
                versatz=explosion(erg["schritte"], kanten_, enden),
                nummer={k: n for n, (k, _) in enumerate(erg["schritte"], 1)})
