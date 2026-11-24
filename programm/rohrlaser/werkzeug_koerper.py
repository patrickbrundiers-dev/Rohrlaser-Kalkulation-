"""Werkzeug aus einem importierten Körper (Paket K3, ArTube „Tool aus Importiertem“): ein anderes Teil derselben
STEP-Datei schneidet das Rohr. Wo seine Oberfläche die Außenhaut des Rohrs durchdringt, entsteht eine Sonderkontur
genau an dieser Stelle (kanten_kontur.rohr), z. B. die Aussparung für ein durchgestecktes Rohr oder eine Lasche.

Rechnung: Dreiecke des Werkzeugs aus seiner Einbaulage in das System des Rohrs (Modell (-u, v, x), Lage aus der
STEP-Messung), dann je Dreieck die Strecke, auf der es die Außenhaut schneidet (vorzeichenbehafteter Abstand zum
Außenumriss, Nullstelle je Kante mit Halbierung genau auf 0,001 mm). Die Strecken werden zu geschlossenen Zügen
verbunden; jeder Zug wird eine Kontur. Züge über ein Ende hinaus sind keine Innenkontur (Gegenrohr bzw. Enden
verwenden).
"""
import math

GENAU = 0.001           # mm: Schnittpunkt auf der Außenhaut so genau
FANG = 0.01             # mm: Endpunkte gelten als gleich
VERSCHMELZEN = 0.02      # mm: so nahe Schnittpunkte sind derselbe Punkt
MIN_ABSTAND = 0.25      # mm: Punkte des Zugs mindestens so weit auseinander (Bögen bleiben auf 0,01 mm rund)
FEIN = 1.5              # mm: Dreiecke nahe am Rohr vorher bis zu dieser Kantenlänge teilen


# ------------------------------------------------------------------ Lagen
def _achsen(lage):
    o, z, x = lage[0:3], lage[3:6], lage[6:9]
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    return o, x, y, z


def in_datei(p, lage):
    """Punkt im System des Teils -> STEP-Datei (wie ansicht3d._in_lage, ohne Runden)."""
    o, x, y, z = _achsen(lage)
    return tuple(o[i] + p[0] * x[i] + p[1] * y[i] + p[2] * z[i] for i in range(3))


def aus_datei(p, lage):
    """Punkt der STEP-Datei -> System des Teils (Umkehrung von in_datei; Achsen senkrecht und Länge 1)."""
    o, x, y, z = _achsen(lage)
    d = [p[i] - o[i] for i in range(3)]
    return tuple(sum(d[i] * a[i] for i in range(3)) for a in (x, y, z))


def dreiecke(netz, lagen):
    """Dreiecke des Netzes in der Datei, für jede Einbaulage: [((x, y, z), …×3)]."""
    p = netz.get("p") or []
    out = []
    for lage in lagen:
        pk = [in_datei(p[i:i + 3], lage) for i in range(0, len(p) - 2, 3)]
        for idx in (netz.get("t") or {}).values():
            for i in range(0, len(idx) - 2, 3):
                out.append((pk[idx[i]], pk[idx[i + 1]], pk[idx[i + 2]]))
    return out


def lagen(netz):
    """Alle Einbaulagen eines Netzes (gleiche Teile: 'lagen', sonst 'lage')."""
    ll = [lg for lg in (netz.get("lagen") or []) if lg and len(lg) >= 9]
    if not ll and netz.get("lage") and len(netz["lage"]) >= 9:
        ll = [netz["lage"]]
    return ll


# ------------------------------------------------------------------ Außenhaut
def abstand(qs, u, v):
    """Vorzeichenbehafteter Abstand des Punkts (u, v) zum Außenumriss [mm], < 0 = im Rohr (Material oder hohl)."""
    if qs.r:
        return math.hypot(u, v) - qs.r
    r = float(getattr(qs, "radius", 0.0) or 0.0)
    qx, qy = abs(u) - (qs.B / 2 - r), abs(v) - (qs.H / 2 - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _f(qs, p):
    return abstand(qs, -p[0], p[1])


def _nullstelle(qs, a, b, fa):
    for _ in range(40):
        m = tuple((a[i] + b[i]) / 2 for i in range(3))
        fm = _f(qs, m)
        if abs(fm) <= GENAU or math.dist(a, b) <= GENAU:
            return m
        if (fm < 0) == (fa < 0):
            a, fa = m, fm
        else:
            b = m
    return tuple((a[i] + b[i]) / 2 for i in range(3))


def _nahe(qs, laenge, t):
    """Kann das Dreieck die Außenhaut berühren (umschließender Quader gegen den des Rohrs)?"""
    g = (qs.r or max(qs.B, qs.H) / 2) + 1.0
    lo = [min(q[i] for q in t) for i in range(3)]
    hi = [max(q[i] for q in t) for i in range(3)]
    return hi[0] >= -g and lo[0] <= g and hi[1] >= -g and lo[1] <= g and hi[2] >= -1.0 and lo[2] <= laenge + 1.0


def _fein(t, h):
    """Dreieck so lange an der längsten Kante teilen, bis keine Kante länger als h ist."""
    stapel, out = [t], []
    while stapel:
        a, b, c = stapel.pop()
        ls = (math.dist(a, b), math.dist(b, c), math.dist(c, a))
        k = max(range(3), key=lambda i: ls[i])
        if ls[k] <= h or len(out) > 200000:
            out.append((a, b, c))
            continue
        e = ((a, b, c), (b, c, a), (c, a, b))[k]
        m = tuple((e[0][i] + e[1][i]) / 2 for i in range(3))
        stapel += [(e[0], m, e[2]), (m, e[1], e[2])]
    return out


def strecken(qs, tri_rohr, laenge=None, h=FEIN):
    """Strecken [(a, b)] im System des Rohrs, auf denen die Dreiecke die Außenhaut schneiden. Große Dreiecke nahe
    am Rohr werden vorher fein geteilt (h), damit kein Durchgang zwischen zwei Ecken verloren geht."""
    if laenge is not None:
        tri_rohr = [f for t in tri_rohr if _nahe(qs, laenge, t) for f in _fein(t, h)]
    out = []
    for t in tri_rohr:
        f = [_f(qs, q) for q in t]
        pk = []
        for i in range(3):
            j = (i + 1) % 3
            if (f[i] < 0) != (f[j] < 0):
                pk.append(_nullstelle(qs, t[i], t[j], f[i]))
        if len(pk) == 2 and math.dist(*pk) > 1e-6:
            out.append((pk[0], pk[1]))
    return out


def zuege(strecken_, fang=FANG):
    """Strecken zu Gruppen verbundener Strecken (je Gruppe eine Kontur)."""
    def schl(p):
        return tuple(round(c / fang) for c in p)
    eltern = {}

    def wurzel(k):
        while eltern.setdefault(k, k) != k:
            eltern[k] = eltern[eltern[k]]
            k = eltern[k]
        return k
    for a, b in strecken_:
        ra, rb = wurzel(schl(a)), wurzel(schl(b))
        if ra != rb:
            eltern[ra] = rb
    gruppen = {}
    for a, b in strecken_:
        gruppen.setdefault(wurzel(schl(a)), []).append((a, b))
    return sorted(gruppen.values(), key=len, reverse=True)


def ringe(gruppe, fang=VERSCHMELZEN, abstand=MIN_ABSTAND):
    """Strecken einer Gruppe -> geschlossene Punktzüge: nahe Punkte verschmolzen (feine Dreiecke liefern viele sehr
    kurze Strecken), doppelte Strecken weg, dann verkettet und auf Punkte im Abstand >= abstand ausgeduennt."""
    def schl(p):
        return tuple(round(c / fang) for c in p)
    vertreter = {}
    kanten = set()
    for a, b in gruppe:
        ka, kb = schl(a), schl(b)
        vertreter.setdefault(ka, a)
        vertreter.setdefault(kb, b)
        if ka != kb:
            kanten.add(frozenset((ka, kb)))
    nach = {}
    for k in kanten:
        a, b = tuple(k)
        nach.setdefault(a, []).append(b)
        nach.setdefault(b, []).append(a)
    out = []
    frei = set(kanten)
    while frei:
        k0 = next(iter(frei))
        a, b = tuple(k0)
        frei.discard(k0)
        zug = [a, b]
        while True:
            weiter = [c for c in nach.get(zug[-1], ()) if frozenset((zug[-1], c)) in frei]
            if not weiter:
                break
            c = weiter[0]
            frei.discard(frozenset((zug[-1], c)))
            if c == zug[0]:
                break
            zug.append(c)
        if len(zug) >= 3:
            pk = [vertreter[k] for k in zug]
            duenn = [pk[0]]
            for q in pk[1:]:
                if math.dist(q, duenn[-1]) >= abstand:
                    duenn.append(q)
            out.append(duenn)
    return out


# ------------------------------------------------------------------ Ergebnis
def konturen(qs_kontur, qs_haut, laenge, netz_rohr, netz_werkzeug):
    """(Konturzeilen, Hinweise): Sonderkonturen (bzw. Bohrungen) dort, wo das Werkzeug die Außenhaut des Rohrs
    schneidet. qs_kontur: Querschnitt des Editors (für die Konturzeile), qs_haut: mit Außenradius (Modell).
    ValueError, wenn die Lagen fehlen oder sich nichts schneidet."""
    from . import auswahl3d, kanten_kontur
    lr, lw = lagen(netz_rohr), lagen(netz_werkzeug)
    if not lr or not lw:
        raise ValueError("Werkzeug: Rohr und Körper brauchen ihre Einbaulage aus derselben STEP-Datei "
                         "(STEP neu einlesen).")
    tri_datei = dreiecke(netz_werkzeug, lw)
    hinweise = []
    for lage in lr:                         # gleiche Rohre: das erste, das der Körper trifft
        tri = [tuple(aus_datei(q, lage) for q in t) for t in tri_datei]
        gruppen = zuege(strecken(qs_haut, tri, float(laenge)))
        if not gruppen:
            continue
        out = []
        for g in gruppen:
            xs = [p[2] for s in g for p in s]
            if min(xs) < 0.05 or max(xs) > float(laenge) - 0.05:
                hinweise.append("Ein Schnitt des Körpers reicht über das Rohrende: dafür das Ende bearbeiten "
                                "(Gegenrohr), keine Innenkontur.")
                continue
            for ring in ringe(g):
                if len(ring) < 3:
                    continue
                kanten = [dict(art=auswahl3d.KANTE, a=ring[i], b=ring[(i + 1) % len(ring)]) for i in range(len(ring))]
                try:
                    z = kanten_kontur.rohr(qs_kontur, kanten)
                    if z.get("art") != "Bohrung":
                        z["text"] = "aus Körper"
                    out.append(z)
                except ValueError as x:
                    hinweise.append(str(x))
        if out or hinweise:
            return out, hinweise
    raise ValueError("Werkzeug: Der Körper berührt die Außenhaut des Rohrs nicht.")


def kandidaten(positionen, p, netz_rohr, netz_von):
    """Andere Positionen derselben STEP-Datei: [(Text, Netz)]. netz_von(position) -> Netz oder None."""
    mutter = (netz_rohr or {}).get("mutter")
    out = []
    for q in positionen or ():
        if q is p or q.get("id") == p.get("id"):
            continue
        n = netz_von(q)
        if n and n.get("mutter") == mutter and lagen(n):
            out.append((f"Pos {q.get('pos') or ''} {q.get('artikel') or q.get('bezeichnung') or ''}".strip(), n))
    return out


TITEL = "Werkzeug aus Körper"
TIPP = ("Ein anderes Teil derselben STEP-Datei (z. B. ein durchgestecktes Rohr oder eine Lasche) schneidet dieses "
        "Rohr: wo es die Außenhaut durchdringt, entsteht eine Sonderkontur genau an der Stelle")


def aus_koerper(rahmen, wahl=None):
    """Rohr-Editor: Körper wählen (wahl = Text des Eintrags für Tests) und die Konturen anhängen. Ergebnis: Zahl
    der neuen Konturzeilen oder None (Grund gemeldet)."""
    from . import einblendung, rohr3d
    from .ansicht3d import entpacken
    d = rahmen.d
    db = getattr(d, "db", None)
    netz_rohr = d._mutter_netz() if hasattr(d, "_mutter_netz") else None
    if not netz_rohr:
        einblendung.melden(d, "Werkzeug aus Körper: Das Rohr stammt nicht aus einem STEP-Import mit Einbaulage.")
        return None

    def netz_von(q):
        return entpacken(db.netz(q["id"])) if q.get("id") and db is not None else None
    liste = kandidaten(getattr(d, "positionen", None) or getattr(d.parent(), "positionen", None), d.p, netz_rohr,
                       netz_von)
    if not liste:
        einblendung.melden(d, "Werkzeug aus Körper: In diesem Angebot gibt es kein anderes Teil derselben STEP-Datei.")
        return None
    if wahl is None:
        from PySide6.QtWidgets import QInputDialog
        wahl, ok = QInputDialog.getItem(d, TITEL, "Welches Teil schneidet dieses Rohr?", [t for t, _ in liste], 0,
                                        False)
        if not ok:
            return None
    netz_w = next((n for t, n in liste if t == wahl), None)
    if netz_w is None:
        return None
    e = d.eingaben()
    laenge = d.k_laenge.value() if getattr(d, "neu", False) and hasattr(d, "k_laenge") else d.p.get("laenge")
    from . import skizze as sk
    try:
        neu, hinweise = konturen(d.qs, sk.Querschnitt(rohr3d.mit_radius(d.profil, e)), laenge, netz_rohr, netz_w)
    except ValueError as x:
        einblendung.melden(d, str(x))
        return None
    if not neu:
        einblendung.melden(d, " ".join(hinweise) or "Werkzeug: keine Kontur entstanden.")
        return None
    for z in neu:
        d.zeile_neu(z)
    d.rechnen()
    rahmen.aktualisieren()
    rahmen.waehlen(f"kontur:{d.tabelle.rowCount() - 1}")
    einblendung.melden(d, f"{wahl}: {len(neu)} Kontur{'en' if len(neu) > 1 else ''} angelegt." +
                       (" " + " ".join(hinweise) if hinweise else ""))
    return len(neu)
