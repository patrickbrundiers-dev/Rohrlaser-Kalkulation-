"""Universelles Konturmodell der Rohrenden und geometrischer Rechenkern für das Verschachteln beliebiger Endkonturen
(Master-Auftrag „3D-Konturbearbeitung universell + intelligente Stangenoptimierung“, Patrick 25.11.2026).

Grundidee (Bericht docs/system-audit/ENDKONTUR_2511.md): JEDES Ende eines Rohrs ist ein Verlauf d(s) auf dem
abgewickelten Mantel – s = Stelle am Umfang (wie skizze.py, Blick von Ende A), d = wie weit die Schnittkante dort hinter
der äußersten Spitze des Teils liegt (≥ 0, an der Spitze 0). Das gilt für den geraden Schnitt (d = 0), die Gehrung
(eben), den Schrägschnitt zweiachsig, die Ausklinkung und das Gegenrohr, das komplexe Ende aus dem STEP-Import
(gemessener Umriss) und für die neuen Endkonturen dieses Moduls. Daraus folgt alles Weitere ohne Sonderfälle:

- Darstellung (Skizze, Abwicklung, 3D, Stangenabwicklung): skizze.schnitt_x/ende_abwicklung lesen den Verlauf,
- Schnittlänge: Länge der Kurve auf dem abgewickelten Mantel (Mantel von Rund- und Kastenrohr ist abwickelbar,
  die Länge ist dort exakt),
- Verschachteln: zwei Nachbarteile rücken zusammen, bis an der engsten Stelle der Abstand der Schnittkanten im Raum
  2 × Schnittverlust + Abstand (+ Sicherheitsabstand) ist – für beliebige Verläufe (verschachtelung_*).

Neue Endkonturen (Eingabe des Endes 'kontur', Schneidweg-Rechner und 3D-Editor): Durchgangsschnitt mit einem
Linienzug in der Seitenansicht. w = Lage quer zum Rohr in Richtung 'richtung' (0° = oben, 90° = vorne/rechts wie die
Gehrungsrichtung; w = u·sin + v·cos), die Kontur gibt d(w) vor. Arten (TYPEN):
  Schräg           d linear von der langen Seite (richtung) bis 'tiefe' auf der Gegenseite (wie Gehrung, aber frei
                   kombinierbar und mit Versatz)
  V-Spitze         Spitze an der Stelle 'versatz' ab Mitte, beide Flanken bis 'tiefe' (versetzt = asymmetrisch)
  V-Kerbe          Kerbe 'breite' × 'tiefe' an der Stelle 'versatz'
  U-Kerbe          Kerbe 'breite' × 'tiefe' mit rundem Grund (Radius = Breite/2)
  U-Zunge          Zunge 'breite' × 'tiefe' mit runder Spitze
  S-Kurve          stetiger S-Bogen von der langen Seite bis 'tiefe'
  Bogen konvex     Kreisbogen 'radius' (oder aus 'tiefe'), Mitte am weitesten vorn
  Bogen konkav     Kreisbogen, Mitte am weitesten hinten (Hohlkehle)
  Stufen           abgestuft: 'stufen' [[Breite ab der langen Seite, Tiefe], …]
  Freiform         'punkte' [[w ab Mitte, d], …] linear
  Freiform Abwicklung  'punkte' [[s am Umfang, d], …] direkt auf dem Mantel (komplexe räumliche Verläufe)
  Kombination      'teile' [Kontur, …]: Schnitte überlagert (an jeder Stelle der tiefste), z. B. Gehrung + V-Kerbe
Alle Konturen sind 2D (Strahl senkrecht zur Oberfläche); der Verlauf wird so verschoben, dass die Spitze bei d = 0
liegt (Teilelänge = Gesamtlänge über alles).

Ohne Qt, ohne Datenbank.
"""
import hashlib
import json
import math

EPS = 1e-9
SCHRAEG, V_SPITZE, V_KERBE, U_KERBE, U_ZUNGE, S_KURVE = ("Schräg", "V-Spitze", "V-Kerbe", "U-Kerbe", "U-Zunge",
                                                          "S-Kurve")
BOGEN_VEX, BOGEN_KAV, STUFEN, FREI, FREI_S, KOMBI = ("Bogen konvex", "Bogen konkav", "Stufen", "Freiform",
                                                     "Freiform Abwicklung", "Kombination")
TYPEN = (SCHRAEG, V_SPITZE, V_KERBE, U_KERBE, U_ZUNGE, S_KURVE, BOGEN_VEX, BOGEN_KAV, STUFEN, FREI, FREI_S, KOMBI)
# Maße je Art (Schlüssel, Titel) für Dialog und Prüfung
MASSE = {SCHRAEG: ("tiefe", "versatz"), V_SPITZE: ("tiefe", "versatz"), V_KERBE: ("tiefe", "breite", "versatz"),
         U_KERBE: ("tiefe", "breite", "versatz"), U_ZUNGE: ("tiefe", "breite", "versatz"),
         S_KURVE: ("tiefe", "versatz"), BOGEN_VEX: ("tiefe", "radius", "versatz"),
         BOGEN_KAV: ("tiefe", "radius", "versatz"), STUFEN: ("stufen",), FREI: ("punkte",), FREI_S: ("punkte",),
         KOMBI: ("teile",)}
TITEL = dict(tiefe="Tiefe t [mm]", breite="Breite b [mm]", versatz="Versatz ab Mitte [mm]", radius="Radius R [mm]",
             stufen="Stufen: Breite × Tiefe; …", punkte="Punkte w, d; …")
SCHRITT = 0.5           # Stützstellen des Verlaufs am Umfang [mm] (höchstens MAX_PUNKTE)
MAX_PUNKTE = 2400


def _z(v):
    try:
        return float(v) if v is not None and not isinstance(v, bool) else 0.0
    except (TypeError, ValueError):
        return 0.0


def lesen(k):
    """Kontur-Eingabe eines Endes (dict) oder None (keine/ungültige)."""
    if not isinstance(k, dict):
        return None
    if k.get("typ") == KOMBI:
        teile = [t for t in (lesen(x) for x in k.get("teile") or ()) if t]
        return dict(k, teile=teile) if teile else None
    return k if k.get("typ") in TYPEN else None


def paare(text):
    """'10; 20 / 5, 3; …' oder [[a, b], …] -> [(a, b)] (Komma oder Leerzeichen zwischen den Zahlen, ; zwischen den
    Paaren; deutsche Kommazahlen mit Leerzeichen getrennt: '10,5 3')."""
    if isinstance(text, (list, tuple)):
        out = []
        for p in text:
            try:
                out.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError, IndexError):
                continue
        return out
    out = []
    for teil in str(text or "").replace("×", " ").replace("x", " ").split(";"):
        t = teil.strip()
        if not t:
            continue
        if " " in t.strip():
            a, _, b = t.strip().partition(" ")
            a, b = a.replace(",", "."), b.strip().replace(",", ".")
        else:
            a, _, b = t.partition(",")
        try:
            out.append((float(a), float(b)))
        except ValueError:
            continue
    return out


def text(k):
    """Kurzer Text der Kontur für Schneidweg, Liste und Tooltip."""
    k = lesen(k)
    if not k:
        return ""
    if k["typ"] == KOMBI:
        return " + ".join(text(t) for t in k["teile"])
    teile = [k["typ"]]
    if _z(k.get("tiefe")):
        teile.append(f"t {_zahl(k['tiefe'])}")
    if _z(k.get("breite")):
        teile.append(f"b {_zahl(k['breite'])}")
    if _z(k.get("radius")):
        teile.append(f"R {_zahl(k['radius'])}")
    if _z(k.get("versatz")):
        teile.append(f"Versatz {_zahl(k['versatz'])}")
    if k["typ"] == STUFEN and 0 < len(paare(k.get("stufen"))) <= 4:
        teile.append("; ".join(f"{_zahl(round(b, 1))} × {_zahl(round(t, 1))}" for b, t in paare(k.get("stufen"))))
    elif k["typ"] in (STUFEN, FREI, FREI_S):
        n = len(paare(k.get("stufen" if k["typ"] == STUFEN else "punkte")))
        teile.append(f"{n} {'Stufen' if k['typ'] == STUFEN else 'Punkte'}")
    if _z(k.get("richtung")):
        teile.append(f"{_zahl(k['richtung'])}°")
    return " ".join(teile)


def _zahl(x):
    return f"{float(x):g}".replace(".", ",")


# ------------------------------------------------------------------ Verlauf d(w) je Art
def _wbereich(qs, richtung):
    """(w_min, w_max) des Außenumrisses in Richtung richtung [°]."""
    s, c = math.sin(math.radians(richtung)), math.cos(math.radians(richtung))
    ws = [u * s + v * c for u, v in qs.umriss[0]] if qs.umriss and qs.umriss[0] else [0.0]
    if qs.r:
        return -qs.r, qs.r
    return min(ws), max(ws)


def _kerbe_u(x, b, t):
    """Tiefe der U-Kerbe (Breite b, Tiefe t, runder Grund) an der Stelle x ab Kerbenmitte."""
    r = b / 2
    if abs(x) >= r or r <= 0:
        return 0.0
    if t >= r:
        return (t - r) + math.sqrt(max(r * r - x * x, 0.0))
    return t * math.sqrt(max(1 - (x / r) ** 2, 0.0))


def _bogen_r(k, halb):
    r = _z(k.get("radius"))
    t = _z(k.get("tiefe"))
    if r <= 0 and t > 0:
        r = (halb * halb + t * t) / (2 * t)
    return max(r, halb + 1e-6) if r > 0 else 0.0


def _roh_w(k, w, wmin, wmax):
    """Verlauf vor dem Verschieben auf Spitze 0 an der Stelle w (Richtung schon eingerechnet)."""
    typ, t = k["typ"], abs(_z(k.get("tiefe")))
    halb = (wmax - wmin) / 2
    m = (wmin + wmax) / 2 + _z(k.get("versatz"))
    m = min(max(m, wmin + 1e-6), wmax - 1e-6)
    if typ == SCHRAEG:
        return t * (wmax - w) / (wmax - wmin) if wmax > wmin else 0.0
    if typ == V_SPITZE:
        return t * (m - w) / (m - wmin) if w < m else t * (w - m) / (wmax - m)
    if typ == V_KERBE:
        b = _z(k.get("breite")) or 2 * halb
        return t * max(0.0, 1 - abs(w - m) / (b / 2)) if b > 0 else 0.0
    if typ == U_KERBE:
        return _kerbe_u(w - m, _z(k.get("breite")) or 2 * halb, t)
    if typ == U_ZUNGE:
        return t - _kerbe_u(w - m, _z(k.get("breite")) or halb, t)
    if typ == S_KURVE:
        x = min(max((w - m) / halb, -1.0), 1.0) if halb > 0 else 0.0
        return t * (1 - math.sin(math.pi / 2 * x)) / 2
    if typ in (BOGEN_VEX, BOGEN_KAV):
        r = _bogen_r(k, halb)
        if r <= 0:
            return 0.0
        x = min(abs(w - m), r)
        d = r - math.sqrt(max(r * r - x * x, 0.0))
        return d if typ == BOGEN_VEX else -d
    if typ == STUFEN:
        # von der langen Seite (w_max) aus: je Stufe Breite × Tiefe; hinter der letzten Stufe deren Tiefe
        pos, d = wmax, 0.0
        for breite, tiefe in paare(k.get("stufen")):
            d = abs(tiefe)
            if w >= pos - breite - 1e-9:
                return d
            pos -= breite
        return d
    if typ == FREI:
        pk = sorted(paare(k.get("punkte")))
        if not pk:
            return 0.0
        x = w - (wmin + wmax) / 2
        if x <= pk[0][0]:
            return pk[0][1]
        for (x0, d0), (x1, d1) in zip(pk, pk[1:]):
            if x <= x1:
                return d0 + (d1 - d0) * ((x - x0) / (x1 - x0) if x1 > x0 else 0.0)
        return pk[-1][1]
    return 0.0


def _knicke_w(k, wmin, wmax):
    """Stellen w, an denen der Verlauf knickt oder springt (dort gehört ein Punkt hin): [(w, Sprung)]."""
    typ = k["typ"]
    halb = (wmax - wmin) / 2
    m = min(max((wmin + wmax) / 2 + _z(k.get("versatz")), wmin + 1e-6), wmax - 1e-6)
    if typ in (V_SPITZE,):
        return [(m, False)]
    if typ in (V_KERBE, U_KERBE, U_ZUNGE):
        b = _z(k.get("breite")) or (halb if typ == U_ZUNGE else 2 * halb)
        return [(m - b / 2, False), (m, False), (m + b / 2, False)]
    if typ in (BOGEN_VEX, BOGEN_KAV):
        r = _bogen_r(k, halb)
        return [(m - r, False), (m + r, False)] if r else []
    if typ == STUFEN:
        out, pos = [], wmax
        for breite, _ in paare(k.get("stufen")):
            pos -= breite
            out.append((pos, True))
        return out
    if typ == FREI:
        return [(x + (wmin + wmax) / 2, False) for x, _ in paare(k.get("punkte"))]
    return []


# ------------------------------------------------------------------ Umriss [[s, d]] aus der Kontur
_UMRISS = {}


def _qs_schluessel(qs):
    return (qs.form, round(qs.umfang, 6), round(qs.B, 6), round(qs.H, 6), round(qs.wand or 0.0, 6),
            round(qs.radius or 0.0, 6))


def umriss(qs, k):
    """Verlauf der Kontur k als Umriss [[s, Abstand vom Ende], …] (wie das komplexe Ende aus dem STEP-Import), Spitze
    bei 0. Gemerkt je Querschnitt und Kontur. None, wenn die Kontur leer oder ungültig ist."""
    k = lesen(k)
    if not k or not qs.umfang:
        return None
    schl = (_qs_schluessel(qs), json.dumps(k, sort_keys=True, default=str))
    if schl in _UMRISS:
        return _UMRISS[schl]
    pk = _rechnen_umriss(qs, k)
    if len(_UMRISS) > 256:
        _UMRISS.clear()
    _UMRISS[schl] = pk
    return pk


def _verlauf_fn(qs, k):
    """Funktion (s, u, v) -> d vor dem Verschieben auf Spitze 0 und die Knickstellen s."""
    if k["typ"] == KOMBI:
        fns = [_verlauf_fn(qs, t) for t in k["teile"]]
        return (lambda s, u, v: max(f(s, u, v) for f, _ in fns)), sorted({x for _, st in fns for x in st})
    if k["typ"] == FREI_S:
        pk = sorted((p[0] % qs.umfang, abs(p[1])) for p in paare(k.get("punkte")))
        if not pk:
            return (lambda s, u, v: 0.0), []
        ss = [p[0] for p in pk]
        ring = [(pk[-1][0] - qs.umfang, pk[-1][1])] + pk + [(pk[0][0] + qs.umfang, pk[0][1])]

        def fs(s, u, v):
            s %= qs.umfang
            for (s0, d0), (s1, d1) in zip(ring, ring[1:]):
                if s0 <= s <= s1:
                    return d0 + (d1 - d0) * ((s - s0) / (s1 - s0) if s1 > s0 else 0.0)
            return pk[-1][1]
        return fs, ss
    from . import skizze as sk
    r = _z(k.get("richtung")) % 360
    sn, cs = math.sin(math.radians(r)), math.cos(math.radians(r))
    wmin, wmax = _wbereich(qs, r)

    def w_von(u, v):            # Lage auf der echten Außenkontur (Eckradius wie STEP und 3D, skizze.rund_ort)
        ur, vr, _ = sk.rund_ort(qs, u, v)
        return ur * sn + vr * cs
    knicke = _knicke_w(k, wmin, wmax)
    stellen = []
    # Stellen s zu den Knicken: auf dem Umriss dort, wo w den Wert erreicht (fein abgetastet, dann linear)
    n = max(360, min(MAX_PUNKTE, int(qs.umfang / SCHRITT)))
    vorher = None
    for i in range(n + 1):
        s = qs.umfang * i / n
        (u, v), _ = qs.s_zu_uv(min(s, qs.umfang - 1e-9))
        w = w_von(u, v)
        if vorher is not None:
            s0, w0 = vorher
            for wk, _sp in knicke:
                if (w0 - wk) * (w - wk) <= 0 and abs(w - w0) > 1e-12:
                    a, b, wa = s0, s, w0             # genau suchen (am Rundrohr ist w nicht linear in s)
                    for _ in range(30):
                        m = (a + b) / 2
                        wm = w_von(*qs.s_zu_uv(min(m, qs.umfang - 1e-9))[0])
                        if (wa - wk) * (wm - wk) <= 0:
                            b = m
                        else:
                            a, wa = m, wm
                    stellen.append((a + b) / 2)
        vorher = (s, w)
    return (lambda s, u, v: _roh_w(k, w_von(u, v), wmin, wmax)), stellen


def _rechnen_umriss(qs, k):
    fn, stellen = _verlauf_fn(qs, k)
    n = max(360, min(MAX_PUNKTE, int(qs.umfang / SCHRITT)))
    ss = {round(qs.umfang * i / n, 6) for i in range(n)}
    for s in stellen:                       # Knicke genau, Sprünge (Stufen) als zwei Punkte dicht nebeneinander
        for ds in (-0.2, -0.1, -0.05, -0.02, -2e-4, 0.0, 2e-4, 0.02, 0.05, 0.1, 0.2):  # steile Stellen fein
            ss.add(round((s + ds) % qs.umfang, 6))
    pk = []
    for s in sorted(ss):
        (u, v), _ = qs.s_zu_uv(min(s, qs.umfang - 1e-9))
        pk.append([s, fn(s, u, v)])
    if not pk:
        return None
    mn = min(d for _, d in pk)
    return [[round(s, 4), round(d - mn, 4)] for s, d in pk]


def tiefe(qs, k):
    """Größte Tiefe des Verlaufs [mm] (Abstand der tiefsten Stelle von der Spitze)."""
    pk = umriss(qs, k)
    return max(d for _, d in pk) if pk else 0.0


def schnittlaenge(qs, k, gerade=None):
    """Länge der Schnittkurve auf dem Außenmantel [mm]: Kurve auf dem abgewickelten Mantel; gerade = gerade
    Schnittlänge des Profils (optimierung.schnittlaenge): das Verhältnis Kurve / Umfang wird darauf angewendet (wie
    schneidweg.ende_3d), damit Eckradien und offene Profile wie beim geraden Schnitt zählen."""
    pk = umriss(qs, k)
    if not pk:
        return gerade or qs.umfang
    ring = pk + [[pk[0][0] + qs.umfang, pk[0][1]]]
    lg = sum(math.hypot(s1 - s0, d1 - d0) for (s0, d0), (s1, d1) in zip(ring, ring[1:]))
    return (gerade or qs.umfang) * lg / qs.umfang if qs.umfang else lg


# ------------------------------------------------------------------ Prüfung: schneidbar?
FEHLER, HINWEIS = "Fehler", "Hinweis"


def pruefen(qs, k, kerf=0.2, laenge=None, wand=None):
    """Prüft die Kontur auf Schneidbarkeit: [(Art, Text, s_von, s_bis)] – Art FEHLER (nicht schneidbar, Kontur so
    nicht fertigen) oder HINWEIS. Geprüft wird
      - Tiefe größer als das Teil (laenge),
      - Schlitze schmaler als die Schnittfuge (der Laser kann sie nicht schneiden),
      - Zungen/Stege schmaler als die Wand bzw. 2 × Schnittfuge (brechen ab, verziehen),
      - Innenecken spitzer als der Strahl (werden mit dem Strahlradius gerundet)."""
    pk = umriss(qs, k)
    if not pk:
        return [(FEHLER, "Kontur unvollständig (Maße fehlen)", 0.0, qs.umfang)]
    out = []
    t = max(d for _, d in pk)
    if laenge and t >= laenge - 1e-6:
        out.append((FEHLER, f"Kontur {_zahl(round(t, 1))} mm tiefer als das Teil ({_zahl(round(laenge, 1))} mm)",
                    0.0, qs.umfang))
    wand = wand if wand is not None else (qs.wand or 0.0)
    schlitz_min = max(kerf, 1e-3)
    steg_min = max(2 * kerf, wand or 0.0, 1.0)
    # in Tiefenstufen: Bereiche, in denen Material fehlt (d ≥ h, Schlitz) bzw. steht (d < h, Zunge)
    U = qs.umfang
    stufen = [t * i / 24 for i in range(1, 24)]
    gesehen = set()
    for h in stufen:
        for art, innen in (("Schlitz", True), ("Zunge", False)):
            for s0, s1 in _bereiche(pk, U, h, innen):
                breite = s1 - s0
                tief = _tiefe_in(pk, U, s0, s1, h, innen)
                grenze = schlitz_min if innen else steg_min
                if breite < grenze - 1e-9 and tief > grenze:
                    key = (art, round(s0, 0))
                    if key in gesehen:
                        continue
                    gesehen.add(key)
                    if innen:
                        out.append((FEHLER, f"Schlitz {_zahl(round(breite, 2))} mm schmaler als die Schnittfuge "
                                            f"({_zahl(kerf)} mm): nicht schneidbar", s0 % U, s1 % U))
                    else:
                        out.append((HINWEIS, f"Zunge/Steg nur {_zahl(round(breite, 2))} mm breit (unter "
                                             f"{_zahl(round(steg_min, 1))} mm): kann sich verziehen oder abbrechen",
                                    s0 % U, s1 % U))
    # Innenecken (Knick nach innen) spitzer als 60°: der Strahl rundet sie mit seinem Radius
    for i in range(len(pk)):
        (s0, d0), (s1, d1), (s2, d2) = pk[i - 1], pk[i], pk[(i + 1) % len(pk)]
        if i == 0:
            s0 -= U
        if i == len(pk) - 1:
            s2 += U
        a = (s0 - s1, d0 - d1)
        b = (s2 - s1, d2 - d1)
        la, lb = math.hypot(*a), math.hypot(*b)
        if la < 1e-3 or lb < 1e-3 or not (d1 > d0 + 1e-6 and d1 > d2 + 1e-6):
            continue
        w = math.degrees(math.acos(max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (la * lb)))))
        if w < 60:
            out.append((HINWEIS, f"spitze Innenecke {_zahl(round(w))}°: wird mit dem Strahlradius gerundet",
                        s1 % U, s1 % U))
    return out


def _tiefe_in(pk, U, s0, s1, h, innen):
    """Länge eines Schlitzes (tiefste Stelle − h) bzw. einer Zunge (h − vorderste Stelle) im Bereich s0 … s1."""
    ds = [d for s, d in pk if s0 - 1e-9 <= s <= s1 + 1e-9 or s0 - 1e-9 <= s + U <= s1 + 1e-9]
    if not ds:
        return 0.0
    return (max(ds) - h) if innen else (h - min(ds))


def _bereiche(pk, U, h, innen):
    """Zusammenhängende Bereiche [(s0, s1)] mit d ≥ h (innen) bzw. d < h, über die Naht hinweg."""
    flag = [(d >= h) == innen for _, d in pk]
    if all(flag):
        return [(0.0, U)] if not innen else []
    if not any(flag):
        return []
    n = len(pk)
    start = next(i for i in range(n) if not flag[i])
    out, i0 = [], None
    for j in range(1, n + 1):
        i = (start + j) % n
        if flag[i] and i0 is None:
            i0 = j
        if (not flag[i] or j == n) and i0 is not None:
            a = pk[(start + i0 - 1) % n][0]
            b = pk[(start + j) % n][0] if not flag[i] else pk[i][0]
            # Ränder linear auf die Höhe h
            s0 = _kreuz(pk, (start + i0 - 1) % n, (start + i0) % n, h, U)
            s1 = _kreuz(pk, (start + j - 1) % n, (start + j) % n, h, U)
            if s1 < s0:
                s1 += U
            out.append((s0 if s0 is not None else a, s1 if s1 is not None else b))
            i0 = None
    return out


def _kreuz(pk, i, j, h, U):
    (s0, d0), (s1, d1) = pk[i], pk[j]
    if s1 < s0:
        s1 += U
    if abs(d1 - d0) < 1e-12:
        return s0
    f = (h - d0) / (d1 - d0)
    return s0 + min(max(f, 0.0), 1.0) * (s1 - s0)


# ------------------------------------------------------------------ Verschachtelung beliebiger Enden
# Geometrie je Querschnitt: Zellen am Umfang (N durch 4 teilbar), je Zelle Mittelpunkt außen und innen (um die Wand
# nach innen) und die Nachbarzellen, die einander im Raum näher als der geforderte Abstand kommen können. Der Verlauf
# eines Endes wird je Zelle sicher (kleinstes d in der Zelle) gespeichert. Alles in Registern mit kurzen Schlüsseln
# (die Packverfahren prüfen dieselben Paare sehr oft; Tupel mit Hunderten Zahlen wären als Schlüssel zu langsam).
_GEO = {}
_PROFIL = {}
_TRENN = {}
TEIL_SCHRITTE = 4           # Stützstellen je Zelle für das sichere kleinste d
ZELLE = 0.5                 # Zellbreite am Umfang [mm] (höchstens 1.440 Zellen)


class Geo:
    __slots__ = ("n", "ds", "aussen", "innen", "ds_innen", "verschiebung", "umfang", "wand", "_nachbarn")

    def __init__(self, qs, n=None):
        self.umfang = qs.umfang
        self.n = n or max(160, min(1440, int(round(qs.umfang / ZELLE / 4)) * 4))
        self.ds = qs.umfang / self.n
        self.wand = qs.wand or 0.0
        self.aussen, self.innen = [], []
        for i in range(self.n):
            (u, v), nrm = qs.s_zu_uv((i + 0.5) * self.ds)
            self.aussen.append((u, v))
            ln = math.hypot(*nrm) or 1.0
            self.innen.append((u - self.wand * nrm[0] / ln, v - self.wand * nrm[1] / ln))
        self.ds_innen = []
        for i in range(self.n):
            a, b = self.innen[i - 1], self.innen[(i + 1) % self.n]
            self.ds_innen.append(max(math.hypot(b[0] - a[0], b[1] - a[1]) / 2, 0.0))
        self.verschiebung = {}
        for r in (0, 90, 180, 270):
            k = _drehung_index(qs, self, r)
            if k is not None:
                self.verschiebung[r] = k
        self._nachbarn = {}

    def lateral(self, i, j):
        """Kleinster Abstand quer (in der Querschnittsebene) zwischen Material der Zellen i und j (sicher: Zellbreite
        abgezogen), außen oder innen – je nachdem, was kleiner ist."""
        if i == j:
            return 0.0
        pa, pb = self.aussen[i], self.aussen[j]
        qa, qb = self.innen[i], self.innen[j]
        da = math.hypot(pa[0] - pb[0], pa[1] - pb[1]) - self.ds
        di = math.hypot(qa[0] - qb[0], qa[1] - qb[1]) - (self.ds_innen[i] + self.ds_innen[j]) / 2 - 1e-9
        return max(0.0, min(da, di) if self.wand > 0 else da)

    def nachbarn(self, abstand):
        """Je Zelle i: [(j, nötiger Längsabstand sqrt(abstand² − quer²))] für alle j mit quer < abstand."""
        key = round(abstand, 6)
        if key in self._nachbarn:
            return self._nachbarn[key]
        out = []
        n = self.n
        for i in range(n):
            liste = [(i, abstand)]
            for richtung in (1, -1):
                weit = 0                    # konvexer Umriss: der Abstand wächst mit dem Versatz; erst nach
                for o in range(1, n // 2 + 1):  # mehreren Zellen in Folge weit genug wird abgebrochen
                    j = (i + richtung * o) % n
                    if richtung == -1 and o == n // 2 and n % 2 == 0:
                        break               # gegenüberliegende Zelle schon mit +1 geprüft
                    q = self.lateral(i, j)
                    if q < abstand:
                        liste.append((j, math.sqrt(abstand * abstand - q * q)))
                        weit = 0
                    else:
                        weit += 1
                        if weit >= 8:
                            break
            out.append(tuple(liste))
        self._nachbarn[key] = tuple(out)
        return self._nachbarn[key]


def _drehung_index(qs, geo, r):
    """Verschiebung in Zellen, um die ein um r [°] gedrehtes Teil (von Ende A gesehen im Uhrzeigersinn, wie
    optimierung.drehungen) seinen Verlauf am Umfang verschiebt; None, wenn der Querschnitt bei dieser Drehung nicht
    auf sich selbst fällt."""
    from .skizze import uv_zu_s
    if r % 360 == 0:
        return 0
    c, s = math.cos(math.radians(r)), math.sin(math.radians(r))
    werte = set()
    for i in range(0, geo.n, max(1, geo.n // 16)):
        u, v = geo.aussen[i]
        ru, rv = u * c + v * s, -u * s + v * c
        sneu = uv_zu_s(qs, ru, rv)
        (pu, pv), _ = qs.s_zu_uv(sneu)
        if math.hypot(pu - ru, pv - rv) > 1e-3 * max(qs.B, qs.H, 1.0):
            return None             # gedrehter Punkt liegt nicht auf dem Umriss: keine Symmetrie
        k = ((sneu - (i + 0.5) * geo.ds) / geo.ds) % geo.n
        if abs(k - round(k)) > 0.02 and abs(k - round(k)) < 0.98:
            return None
        werte.add(int(round(k)) % geo.n)
    return werte.pop() if len(werte) == 1 else None


def geo_schluessel(qs):
    """Schlüssel der Geometrie des Querschnitts im Register (legt sie bei Bedarf an); '' für offene Profile."""
    from .skizze import _offen
    if not qs.umfang or not qs.umriss or _offen(qs):
        return ""
    k = "G" + hashlib.blake2b(repr(_qs_schluessel(qs)).encode(), digest_size=8).hexdigest()
    if k not in _GEO:
        _GEO[k] = Geo(qs)
    return k


def geo(schluessel):
    return _GEO.get(schluessel)


def ende_verlauf_zellen(qs, gk, e, gespiegelt=False, d3=None):
    """Sicherer Verlauf des Endes e (Eingabe des Schneidweg-Rechners) je Zelle der Geometrie gk: kleinstes d der Zelle
    (Material reicht dort höchstens so weit), bei 3D-Schnitten (Gehrung in 3D, gemessener Schwenk) um die Wand × tan
    (Winkel) weiter vorn angenommen (die Innenkante kann vor der Außenkante liegen). gespiegelt: Teil gewendet
    (Enden getauscht, rechts <-> links). None, wenn das Ende sich nicht beschreiben lässt (Nasen einer
    Steckverbindung).
    d3: Teil wird in 3D geschnitten (Eingabe d3 des Schneidweg-Rechners). False = 2D: der Strahl steht senkrecht zur
    Oberfläche, die Innenkante liegt unter der Außenkante – kein Zuschlag für einen gemessenen Schwenk (Patrick
    25.11.2026 „Erkennung weiter verbessern“: V-Spitze 20 mm am Rechteckrohr lag sonst 3 mm zu weit vorn). None =
    wie bisher (Schwenk zählt)."""
    from . import skizze as sk
    g = _GEO.get(gk)
    if g is None or not isinstance(e, dict):
        return None
    if e.get("nasen"):
        return None
    out = []
    zusatz = 0.0
    w = abs(_z(e.get("winkel")))
    # 3D-Ebene: echte Innenkante je Stützstelle (unten); innen_3d = pauschaler Zuschlag als zweite sichere Grenze
    innen_3d = (qs.wand or 0.0) * math.tan(math.radians(min(w, 80))) if _innen_3d(qs, e) else 0.0
    if innen_3d:
        pass
    elif e.get("d3") and w:
        zusatz = (qs.wand or 0.0) * math.tan(math.radians(min(w, 80)))
    elif _z(e.get("schwenk")) >= 0.5 and d3 is not False:
        zusatz = (qs.wand or 0.0) * math.tan(math.radians(min(_z(e.get("schwenk")), 80)))
    for i in range(g.n):
        werte, werte_i = [], []
        for k_ in range(TEIL_SCHRITTE + 1):
            s = (i + k_ / TEIL_SCHRITTE) * g.ds
            (u, v), nrm = qs.s_zu_uv(min(s, qs.umfang - 1e-9))
            if gespiegelt:
                u = -u
            try:
                werte.append(sk.schnitt_x(qs, e, u, v))
                if innen_3d:                # 3D-Schnitt: die Ebene trifft die Innenwand an ihrer eigenen Stelle
                    ln = math.hypot(*nrm) or 1.0
                    ui, vi = u - qs.wand * (-nrm[0] if gespiegelt else nrm[0]) / ln, v - qs.wand * nrm[1] / ln
                    werte_i.append(sk.schnitt_x(qs, e, ui, vi))
            except (ValueError, ZeroDivisionError, TypeError):
                return None
        sprung = max((abs(b - a) for a, b in zip(werte, werte[1:])), default=0.0)
        wert = min(werte) - sprung / 2 - zusatz         # zwischen den Stützstellen höchstens um den halben Sprung
        if werte_i:
            # beides sind sichere Grenzen: die echte Innenkante und der pauschale Zuschlag Wand × tan(Winkel) (an
            # Ecken von Kastenprofilen springt die Innenkante, dort ist der Zuschlag enger); die weitere zählt
            sprung_i = max((abs(b - a) for a, b in zip(werte_i, werte_i[1:])), default=0.0)
            wert = max(min(wert, min(werte_i) - sprung_i / 2), wert - innen_3d)
        out.append(wert)
    um = sk.ende_umriss_von(qs, e)
    if um:                                  # Knicke eines gemessenen bzw. konstruierten Verlaufs genau
        f = sk._ende_umriss_merken(qs, um)
        for st in getattr(f, "stellen", ()) if f else ():
            s = st % qs.umfang
            if gespiegelt:
                (u, v), _ = qs.s_zu_uv(s)
                s = sk.uv_zu_s(qs, -u, v)
            i = int(s / g.ds) % g.n
            out[i] = min(out[i], f(st) - zusatz)
    return out


def _innen_3d(qs, e):
    """True, wenn die Innenkante eines Endes genau aus der Schnittebene folgt: ebener Schnitt (Gehrung bzw. schräg in
    zwei Richtungen) mit 3D-Bearbeitung ('d3') an einem Hohlprofil. Dann liegt die Innenkante dort, wo die Ebene die
    Innenwand trifft (wie in der STEP), statt pauschal Wand × tan(Winkel) vor der Außenkante (Master-Auftrag
    Abwicklungskern 25.11.2026, P4; Patrick 25.11.2026: mit 3D wie in der STEP, ohne 3D 90° an der Innenkante)."""
    w = abs(_z(e.get("winkel")))
    return bool(e.get("d3") and 0 < w < 80 and (qs.wand or 0) > 0 and not e.get("umriss") and not e.get("kontur")
                and not e.get("nasen") and not _gegen(e))


def _gegen(e):
    from . import durchdringung as dd
    try:
        return bool(dd.gegen_lesen(e))
    except Exception:   # noqa: BLE001
        return True


def profil_schluessel(werte):
    """Verlauf je Zelle ins Register, Ergebnis kurzer Schlüssel (gleiche Verläufe = gleicher Schlüssel)."""
    if werte is None:
        return None
    t = tuple(round(x, 4) for x in werte)
    if max(t) - min(t) < 1e-3:
        return None                         # gerade bzw. ohne Verlauf: nichts zu verschachteln
    k = "P" + hashlib.blake2b(repr(t).encode(), digest_size=8).hexdigest()
    _PROFIL.setdefault(k, t)
    return k


def profil(k):
    return _PROFIL.get(k)


def profil_tiefe(k):
    """Größte Überlappung, die ein Ende erlauben kann [mm] (Tiefe des Verlaufs)."""
    p = _PROFIL.get(k)
    return max(p) if p else 0.0


def trennung(gk, abstand, k_b, r1, k_a, r2):
    """Längsabstand zwischen der Spitze von Ende B des ersten Teils (Verlauf k_b, Drehung r1) und der Spitze von
    Ende A des folgenden (k_a, r2), wenn beide so weit zusammenrücken, dass an jeder Stelle der Abstand der
    Schnittkanten im Raum mindestens abstand ist [mm]; negativ = die Teile überlappen sich in der Länge. Material
    von Teil 1 bei z ≤ −d_B, von Teil 2 bei z ≥ x + d_A: x = max über alle nahen Zellpaare (j, i) von
    nötig(i, j) − d_B(j) − d_A(i). None, wenn eine Drehung nicht abbildbar ist."""
    key = (gk, round(abstand, 6), k_b, r1 % 360, k_a, r2 % 360)
    if key in _TRENN:
        return _TRENN[key]
    g = _GEO.get(gk)
    pb, pa = _PROFIL.get(k_b), _PROFIL.get(k_a)
    if g is None or pb is None or pa is None or r1 % 360 not in g.verschiebung or r2 % 360 not in g.verschiebung:
        return None
    n = g.n
    s1, s2 = g.verschiebung[r1 % 360], g.verschiebung[r2 % 360]
    db = [pb[(j - s1) % n] for j in range(n)]
    da = [pa[(i - s2) % n] for i in range(n)]
    x = -math.inf
    for i, liste in enumerate(g.nachbarn(abstand)):
        a = da[i]
        for j, noetig in liste:
            v = noetig - db[j] - a
            if v > x:
                x = v
    if len(_TRENN) > 200000:
        _TRENN.clear()
    _TRENN[key] = x
    return x


def kleinster_abstand(gk, k_b, r1, k_a, r2, x):
    """Unabhängige Gegenprobe (Kollisionsprüfung): kleinster Abstand im Raum zwischen den Schnittkanten zweier
    Nachbarteile im Längsabstand x der Spitzen [mm], über ALLE Zellpaare (nicht nur die nahen), mit dem sicheren
    Querabstand. Negativ bzw. 0 bei Durchdringung (Material von Teil 2 vor dem von Teil 1 an derselben Stelle)."""
    key = ("abstand", gk, k_b, r1 % 360, k_a, r2 % 360, round(x, 6))
    if key in _TRENN:
        return _TRENN[key]
    g = _GEO.get(gk)
    pb, pa = _PROFIL.get(k_b), _PROFIL.get(k_a)
    s1, s2 = g.verschiebung[r1 % 360], g.verschiebung[r2 % 360]
    n = g.n
    best = math.inf
    for i in range(n):
        a = pa[(i - s2) % n]
        for j in range(n):
            dz = x + a + pb[(j - s1) % n]
            q = g.lateral(i, j)
            if dz <= 0 and q <= 0:
                best = min(best, dz)
                continue
            d = math.hypot(max(dz, 0.0), q)
            if d < best:
                best = d
    _TRENN[key] = best
    return best


def merker_leeren():
    _TRENN.clear()
    _UMRISS.clear()


# ------------------------------------------------------------------ Kollisionsprüfung an der echten Geometrie
def kanten_punkte(qs, e, gespiegelt=False, n=720):
    """Punkte der Schnittkante eines Endes außen und innen [(u, v, d)] fein am Umfang (für Gegenproben und Tests)."""
    from . import skizze as sk
    out = []
    for i in range(n):
        s = qs.umfang * (i + 0.5) / n
        (u, v), nrm = qs.s_zu_uv(s)
        d = sk.schnitt_x(qs, e, -u if gespiegelt else u, v)
        out.append((u, v, d))
        if qs.wand:
            ln = math.hypot(*nrm) or 1.0
            ui, vi = u - qs.wand * nrm[0] / ln, v - qs.wand * nrm[1] / ln
            # 3D-Schnitt: Innenkante dort, wo die Ebene die Innenwand trifft; 2D: unter der Außenkante
            di = sk.schnitt_x(qs, e, -ui if gespiegelt else ui, vi) if _innen_3d(qs, e) else d
            out.append((ui, vi, di))
    return out


def echter_abstand(qs, e_b, r1, e_a, r2, x, n=720):
    """Kleinster Abstand im Raum zwischen der Kante von Ende B (Teil 1, Drehung r1) und der von Ende A (Teil 2,
    Drehung r2, Spitze x hinter der Spitze von Teil 1), aus den feinen Kantenpunkten (Gegenprobe für Tests)."""
    def drehen(p, r):
        c, s = math.cos(math.radians(r)), math.sin(math.radians(r))
        u, v, d = p
        return u * c + v * s, -u * s + v * c, d
    kb = [drehen(p, r1) for p in kanten_punkte(qs, e_b, n=n)]
    ka = [drehen(p, r2) for p in kanten_punkte(qs, e_a, n=n)]
    best = math.inf
    for ub, vb, db in kb:
        zb = -db
        for ua, va, da in ka:
            d = math.sqrt((ub - ua) ** 2 + (vb - va) ** 2 + (x + da - zb) ** 2)
            if d < best:
                best = d
    return best


# ------------------------------------------------------------------ Erkennung aus dem gemessenen Umriss (STEP)
ERKENNUNG_TOL = 0.1     # mm: so genau muss die erkannte Kontur den gemessenen Umriss überall treffen (wie Gehrung)
ERKENNUNG_TYPEN = (V_SPITZE, V_KERBE, U_KERBE, U_ZUNGE, BOGEN_VEX, BOGEN_KAV, S_KURVE, SCHRAEG, STUFEN)


def kurven_abstand(pa, pb, umfang, fenster=2.0, beide=False):
    """Größter Abstand zweier geschlossener Verläufe [[s, d]] auf dem abgewickelten Mantel (Hausdorff, in mm):
    wie weit ein Punkt der einen Kurve höchstens von der anderen weg liegt. Sprünge (Stufen) zählen als senkrechte
    Strecke, eine um 0,05 mm versetzte Stufe ist also 0,05 mm daneben, nicht die ganze Stufenhöhe. Ab fenster mm
    Abstand wird nicht weiter gesucht (Ergebnis dann ≥ fenster). beide: (pa -> pb, pb -> pa) getrennt."""
    import bisect

    def ring(p):
        p = sorted((float(s) % umfang, float(d)) for s, d in p)
        return [(s - umfang, d) for s, d in p] + p + [(s + umfang, d) for s, d in p]

    def einseitig(a, b):
        ss = [s for s, _ in b]
        groesst = 0.0
        for s0, d0 in sorted((float(s) % umfang, float(d)) for s, d in a):
            i0 = max(bisect.bisect_right(ss, s0 - fenster) - 1, 0)
            i1 = min(bisect.bisect_left(ss, s0 + fenster), len(b) - 1)
            best = fenster
            for j in range(i0, max(i1, i0 + 1)):
                (s1, d1), (s2, d2) = b[j], b[j + 1]
                ds, dd = s2 - s1, d2 - d1
                lg = ds * ds + dd * dd
                t = min(max(((s0 - s1) * ds + (d0 - d1) * dd) / lg, 0.0), 1.0) if lg > 1e-18 else 0.0
                best = min(best, math.hypot(s1 + t * ds - s0, d1 + t * dd - d0))
            groesst = max(groesst, best)
            if groesst >= fenster:
                break
        return groesst
    # Kein "a if beide else b" mit Tupel/Zahl: Cython (Windows-Build) lehnt gemischte Typen im Bedingungsausdruck ab.
    if not pa or not pb or not umfang:
        if beide:
            return (math.inf, math.inf)
        return math.inf
    x = (einseitig(pa, ring(pb)), einseitig(pb, ring(pa)))
    if beide:
        return x
    return max(x)


def _nelder_mead(f, x0, schritte, n_max=160):
    """Einfaches Nelder-Mead (ohne scipy) für 1–3 Maße."""
    n = len(x0)
    pts = [list(x0)] + [[x0[j] + (schritte[j] if j == i else 0.0) for j in range(n)] for i in range(n)]
    werte = [f(p) for p in pts]
    for _ in range(n_max):
        ordn = sorted(range(n + 1), key=lambda i: werte[i])
        pts, werte = [pts[i] for i in ordn], [werte[i] for i in ordn]
        if werte[-1] - werte[0] < 1e-10:
            break
        mitte = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        refl = [mitte[j] + (mitte[j] - pts[-1][j]) for j in range(n)]
        fr = f(refl)
        if fr < werte[0]:
            exp = [mitte[j] + 2 * (mitte[j] - pts[-1][j]) for j in range(n)]
            fe = f(exp)
            pts[-1], werte[-1] = (exp, fe) if fe < fr else (refl, fr)
        elif fr < werte[-2]:
            pts[-1], werte[-1] = refl, fr
        else:
            kon = [mitte[j] + 0.5 * (pts[-1][j] - mitte[j]) for j in range(n)]
            fk = f(kon)
            if fk < werte[-1]:
                pts[-1], werte[-1] = kon, fk
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    werte[i] = f(pts[i])
    i = min(range(n + 1), key=lambda i: werte[i])
    return pts[i], werte[i]


def _richtungen(qs, proben):
    """Mögliche Schnittrichtungen [°]: Durchgangsschnitt = Verlauf spiegelbildlich zur Achse w (Punkt und sein
    Spiegelbild quer zur Richtung haben dasselbe d). Kastenrohr 0/90°, Rundrohr fein gesucht. Je Richtung r auch
    r + 180° (Schräg, Stufen und versetzte Konturen sind gerichtet)."""
    from . import skizze as sk
    f = proben["f"]

    def fehler(r):
        sn, cs = math.sin(math.radians(r)), math.cos(math.radians(r))
        groesst = 0.0
        for _, u, v, d in proben["p"]:
            q = u * cs - v * sn
            s2 = sk.uv_zu_s(qs, u - 2 * q * cs, v + 2 * q * sn)
            f2 = f(s2)
            steil = max(abs(f(s2 - 0.3) - f2), abs(f(s2 + 0.3) - f2))   # an Sprüngen/Flanken 0,3 mm Lage frei
            groesst = max(groesst, max(abs(f2 - d) - steil, 0.0))
        return groesst
    if qs.r:
        grob = [(fehler(r), r) for r in range(0, 180, 3)]
        kand = []
        for i, (x, r) in enumerate(grob):           # örtliche Minima, fein nachgesucht
            if x <= min(grob[i - 1][0], grob[(i + 1) % len(grob)][0]):
                a, b = r - 3.0, r + 3.0
                for _ in range(30):
                    m1, m2 = a + (b - a) * 0.382, a + (b - a) * 0.618
                    if fehler(m1) < fehler(m2):
                        b = m2
                    else:
                        a = m1
                fein = round((a + b) / 2, 2) % 180
                ganz = round(fein) % 180            # Sprünge (Stufen, U-Kerbe): Fehler springt, glatte Werte zuerst
                kand.append(min((fehler(ganz), ganz), (fehler(fein), fein), (x, float(r))))
        kand = sorted(kand)[:3]
    else:
        kand = [(fehler(r), float(r)) for r in (0, 90)]
    out = []
    for x, r in sorted(kand):
        if x <= 4 * ERKENNUNG_TOL:
            out += [r, (r + 180) % 360]
    return out


def _start_werte(typ, ws, ds, wmin, wmax):
    """Startmaße je Art aus dem Verlauf d(w): (Namen, Werte, Schrittweiten) oder None."""
    halb = (wmax - wmin) / 2
    mitte = (wmin + wmax) / 2
    t = max(ds) - min(ds)
    if t < 0.2:
        return None
    lo = [w for w, d in zip(ws, ds) if d <= min(ds) + 0.05 * t]
    hi = [w for w, d in zip(ws, ds) if d >= max(ds) - 0.05 * t]
    m_lo = (min(lo) + max(lo)) / 2 - mitte
    m_hi = (min(hi) + max(hi)) / 2 - mitte
    if typ == SCHRAEG:
        return ("tiefe",), [t], [t * 0.1]
    if typ in (V_SPITZE, S_KURVE):
        return ("tiefe", "versatz"), [t, m_lo if typ == V_SPITZE else 0.0], [t * 0.1, halb * 0.1]
    if typ == V_KERBE:
        breite = max(w for w, d in zip(ws, ds) if d > min(ds) + 0.5 * t) - min(
            w for w, d in zip(ws, ds) if d > min(ds) + 0.5 * t)
        return ("tiefe", "breite", "versatz"), [t, 2 * max(breite, 0.5), m_hi], [t * 0.1, halb * 0.1, halb * 0.05]
    if typ in (U_KERBE, U_ZUNGE):
        sel = [w for w, d in zip(ws, ds) if (d > min(ds) + 0.02 * t if typ == U_KERBE else d < max(ds) - 0.02 * t)]
        breite = max(sel) - min(sel) if sel else halb
        m = (max(sel) + min(sel)) / 2 - mitte if sel else 0.0
        return ("tiefe", "breite", "versatz"), [t, max(breite, 0.5), m], [t * 0.1, halb * 0.1, halb * 0.05]
    if typ in (BOGEN_VEX, BOGEN_KAV):
        m = m_lo if typ == BOGEN_VEX else m_hi
        x = halb + abs(m)
        r = (x * x + t * t) / (2 * t)
        return ("radius", "versatz"), [r, m], [r * 0.05, halb * 0.05]
    return None


def _stufen_aus(ws, ds, wmin, wmax):
    """Stufen [[Breite, Tiefe]] von der langen Seite (w_max) aus: Höhen d zu Gruppen zusammenfassen (je Gruppe ein
    zusammenhängender Bereich in w), Proben im Sprung selbst (Zwischenhöhe, wenige Punkte) zählen nicht. Grenze
    zwischen zwei Stufen in der Mitte zwischen ihren Bereichen (genau dann _stufen_genau)."""
    gruppen = []                            # [Höhe, [w …]]
    for d, w in sorted(zip(ds, ws)):
        if gruppen and d - gruppen[-1][0] <= 0.3:
            g = gruppen[-1]
            g[1].append(w)
            g[0] = d if len(g[1]) == 1 else g[0]
            g.append(d)
        else:
            gruppen.append([d, [w], d])
    stufen = []
    for g in gruppen:
        hoehen = g[2:]
        if len(g[1]) < 3 or max(g[1]) - min(g[1]) < 0.5:
            continue                        # Proben im Sprung (Messpunkte an der senkrechten Kante)
        stufen.append((max(g[1]), min(g[1]), sum(hoehen) / len(hoehen)))
    stufen.sort(reverse=True)
    if len(stufen) < 2 or len(stufen) > 12:
        return None
    for (o1, u1, _), (o2, u2, _) in zip(stufen, stufen[1:]):
        if o2 > u1 + 1.5:                   # Bereiche überlappen: kein Stufenschnitt in dieser Richtung
            return None
    out, oben = [], wmax
    for i, (o, u, h) in enumerate(stufen):
        unten = (u + stufen[i + 1][0]) / 2 if i + 1 < len(stufen) else wmin
        out.append([oben - unten, h])
        oben = unten
    if any(b_ < 0.2 for b_, _ in out):
        return None
    return out


def _stufen_genau(stufen, f, qs, sn, cs, wmax):
    """Sprungstellen der Stufen auf dem gemessenen Umriss genau suchen (Halbierung an der Stelle, wo der Umriss
    zwischen den Stufenhöhen wechselt)."""
    U = qs.umfang
    n = max(400, int(U / 0.5))
    ss = [U * i / n for i in range(n)]
    from . import skizze as sk
    pkt = [(s,) + sk.rund_ort(qs, *qs.s_zu_uv(s)[0])[:2] for s in ss]
    pos = wmax
    out = []
    for i, (breite, tiefe_) in enumerate(stufen[:-1]):
        grenze = pos - breite
        naechste = stufen[i + 1][1]
        mitte_h = (tiefe_ + naechste) / 2
        best = None
        for (s0, u0, v0), (s1, u1, v1) in zip(pkt, pkt[1:] + pkt[:1]):
            w0, w1 = u0 * sn + v0 * cs, u1 * sn + v1 * cs
            if min(w0, w1) - 1.0 <= grenze <= max(w0, w1) + 1.0 and abs(w1 - w0) > 1e-6:
                a, b = s0, s1 if s1 > s0 else s1 + U
                fa = f(a) - mitte_h
                fb = f(b) - mitte_h
                if fa * fb > 0:
                    continue
                for _ in range(40):
                    m = (a + b) / 2
                    if (f(m) - mitte_h) * fa > 0:
                        a = m
                    else:
                        b = m
                u, v, _ = sk.rund_ort(qs, *qs.s_zu_uv(((a + b) / 2) % U)[0])
                best = u * sn + v * cs
                break
        if best is not None:
            grenze = best
        out.append([pos - grenze, tiefe_])
        pos = grenze
    out.append([stufen[-1][0] + (pos - (pos if not out else pos)), stufen[-1][1]])
    gesamt = sum(b for b, _ in out[:-1])
    out[-1][0] = max(sum(b for b, _ in stufen) - gesamt, 0.2)
    return out


def _runden(k, stellen):
    out = dict(k)
    for sch in ("tiefe", "breite", "versatz", "radius", "richtung"):
        if sch in out:
            out[sch] = round(float(out[sch]), stellen)
            if sch in ("versatz", "richtung") and abs(out[sch]) < 10 ** -stellen:
                out.pop(sch)
    if "stufen" in out:
        out["stufen"] = [[round(b, stellen), round(t, stellen)] for b, t in out["stufen"]]
    return out


def erkennen(qs, umriss_gemessen, tol=ERKENNUNG_TOL, nur_freimachung=False):
    """Konturart eines gemessenen Endes: dict(kontur, abweichung[, freimachung]) oder None. Zuerst die Grundarten
    (_erkennen_grund), sonst Ausklinkung mit runden Freimachungen an den inneren Ecken (Patrick 25.11.2026):
    freimachung = dict(d, lage, anzahl, text), kontur = die Ausklinkung ohne Freimachung (U-Kerbe …).
    nur_freimachung: Ende mit Hinterschnitt (Teile der Freimachung als eigene Sonderkontur): nur so erkennen."""
    er = None if nur_freimachung else _erkennen_grund(qs, umriss_gemessen, tol)
    if er is None:
        try:
            er = _erkennen_freimachung(qs, umriss_gemessen, tol)
        except (ValueError, ZeroDivisionError, TypeError):
            er = None
    return er


def erkannt_text(er):
    """Anzeige einer erkannten Konturart (dict aus erkennen): 'U-Kerbe t 30 b 20, Freimachung 2 × Ø10 mittig' bzw.
    'Ausklinkung 20 × 30, Freimachung 2 × Ø10 mittig'."""
    if not isinstance(er, dict):
        return ""
    k = lesen(er.get("kontur"))
    grund = text(k) if k else str(er.get("text") or "")
    f = er.get("freimachung")
    return grund + (f", {f['text']}" if grund and isinstance(f, dict) and f.get("text") else "")


def _erkennen_freimachung(qs, umriss_gemessen, tol):
    """Ausklinkung mit Freimachungen an den inneren Ecken: jede vertiefte Stelle als geschlossenen Umriss (Abstand je
    Umfangsstelle, am Ende mit d = 0 geschlossen) an form_erkennung.freimachung geben. Ergibt die Ausklinkung ohne
    Freimachung eine Grundart (z. B. U-Kerbe durch zwei Wände), ist das die Kontur; sonst (eine Wand) heißt sie
    „Ausklinkung b × t“ (kontur None, text)."""
    from . import form_erkennung as fe
    U = qs.umfang
    pts = sorted(((float(s) % U, max(float(d), 0.0)) for s, d in umriss_gemessen), key=lambda p: p[0])
    if len(pts) < 4:
        return None
    flach = [i for i, p in enumerate(pts) if p[1] <= tol]
    if not flach:
        return None
    i0 = flach[0]                           # bei einer flachen Stelle beginnen, über den Umfang abwickeln
    ring = [(p[0] + (U if i < i0 else 0.0), p[1]) for i, p in enumerate(pts)]
    ring = ring[i0:] + ring[:i0] + [(ring[i0][0] + U, ring[i0][1])]
    tief = [p[1] > tol for p in ring]
    stellen = []
    i = 1
    while i < len(ring):
        if tief[i] and not tief[i - 1]:
            b = next((j for j in range(i, len(ring)) if not tief[j]), None)
            if b is None:
                return None
            stellen.append((i - 1, b))
            i = b
        i += 1
    if not stellen or len(stellen) > 4:
        return None
    formen = []
    for a, b in stellen:
        poly = ring[a:b + 1]
        poly_p = fe._punkte(poly)
        st = fe.zerlegen(poly, min(tol, fe.ZERLEGEN_TOL), tol)
        f = fe.freimachung(poly_p, st, tol, band=True) if poly_p and st else None
        if not f or abs(f["winkel"]) > 1e-6:
            return None
        s1, s2 = f["mitte"][0] - f["laenge"] / 2, f["mitte"][0] + f["laenge"] / 2
        t1, t2 = f["mitte"][1] - f["breite"] / 2, f["mitte"][1] + f["breite"] / 2
        if abs(t1) > tol or any(e["ecke"] in (0, 1) for e in f["ecken"]):
            return None                     # am Ende beginnend, Freimachung nur am Grund der Ausklinkung
        formen.append((a, b, s1, s2, t2, f))
    d_ = {f["freimachung_d"] for *_, f in formen}
    if len(d_) != 1:
        return None
    grund, vorher = [], 0
    for a, b, s1, s2, t2, f in formen:      # Ausklinkung ohne Freimachung (Wände wie gemessen fast senkrecht)
        grund += ring[vorher:a + 1] + [(s1 - 1e-3, 0.0), (s1 + 1e-3, t2), (s2 - 1e-3, t2), (s2 + 1e-3, 0.0)]
        vorher = b
    grund += ring[vorher:-1]
    er = _erkennen_grund(qs, [[p[0] % U, p[1]] for p in grund], tol)
    lagen = {f["freimachung_lage"] for *_, f in formen}
    n = sum(f["freimachung_anzahl"] for *_, f in formen)
    lage = lagen.pop() if len(lagen) == 1 else "gemischt"
    frei = dict(d=d_.pop(), lage=lage, anzahl=n)
    frei["text"] = f"Freimachung {n} × Ø{fe._zahl(frei['d'])} {lage}"
    abw = max(f["abweichung"] for *_, f in formen)
    if er:
        return dict(kontur=er["kontur"], abweichung=abw, freimachung=frei)
    if len(formen) != 1:
        return None
    _, _, s1, s2, t2, f = formen[0]
    return dict(kontur=None, abweichung=abw, freimachung=frei,
                ausklinkung=dict(breite=round(s2 - s1, 2), tiefe=round(t2, 2), mitte_s=round(((s1 + s2) / 2) % U, 2)),
                text=f"Ausklinkung {fe._zahl(s2 - s1)} × {fe._zahl(t2)}")


def _erkennen_grund(qs, umriss_gemessen, tol=ERKENNUNG_TOL):
    """Konturart eines gemessenen Endes (Umriss [[s, Abstand]] aus dem STEP-Import) erkennen: dict(kontur=…,
    abweichung=mm) oder None. Erkannt gilt nur eine Kontur, deren Verlauf den gemessenen Umriss überall auf tol trifft
    (kurven_abstand, Grundregel 100 % wie die STEP). Der gemessene Umriss bleibt trotzdem maßgebend; die Kontur
    beschreibt ihn nur (Anzeige, Endkontur-Dialog). Gerade, Gehrung und Gegenrohr erkennt step.py vorher."""
    from . import skizze as sk
    if not umriss_gemessen or not qs.umfang or not (qs.r or qs.form in ("Quadratrohr", "Rechteckrohr")):
        return None
    f = sk._ende_umriss(qs, umriss_gemessen)
    if f is None:
        return None
    U = qs.umfang
    n = max(240, min(480, int(U / 1.0)))
    ss = sorted({U * i / n for i in range(n)} | {float(s) % U for s, _ in umriss_gemessen})
    proben = dict(f=f, p=[])
    for s in ss:                            # echte Außenkontur (Eckradius), wie _verlauf_fn
        u, v, _ = sk.rund_ort(qs, *qs.s_zu_uv(min(s, U - 1e-9))[0])
        proben["p"].append((s, u, v, f(s)))
    tiefe_ges = max(p[3] for p in proben["p"]) - min(p[3] for p in proben["p"])
    if tiefe_ges < 0.2:
        return None
    gemessen_pk = [[float(s) % U, max(float(d), 0.0)] for s, d in umriss_gemessen]
    kandidaten = []
    for r in _richtungen(qs, proben):
        sn, cs = math.sin(math.radians(r)), math.cos(math.radians(r))
        wmin, wmax = _wbereich(qs, r)
        ws = [u * sn + v * cs for _, u, v, _ in proben["p"]]
        ds = [p[3] for p in proben["p"]]
        for typ in ERKENNUNG_TYPEN:
            if typ in (V_SPITZE, V_KERBE, U_KERBE, U_ZUNGE, BOGEN_VEX, BOGEN_KAV) and r >= 180:
                continue                    # symmetrische Arten: r + 180° ist dieselbe Kontur mit −Versatz
            if typ == STUFEN:
                st = _stufen_aus(ws, ds, wmin, wmax)
                if not st:
                    continue
                st = _stufen_genau(st, f, qs, sn, cs, wmax)
                k = dict(typ=STUFEN, stufen=st, richtung=r)
                if st[0][1] > st[-1][1] + 1e-6:     # wie im Dialog: von der Seite ohne Tiefe aus
                    k = dict(typ=STUFEN, stufen=[list(x) for x in reversed(st)], richtung=(r + 180) % 360)
                kandidaten.append(k)
                continue
            sw_ = _start_werte(typ, ws, ds, wmin, wmax)
            if not sw_:
                continue
            namen, x0, schr = sw_

            def k_aus(x, typ=typ, namen=namen, r=r):
                k = dict(typ=typ, richtung=r)
                for nm, val in zip(namen, x):
                    k[nm] = val
                return k

            def kosten(x, k_aus=k_aus, wmin=wmin, wmax=wmax):
                k = k_aus(x)
                if any(k.get(nm, 1.0) <= 0 for nm in ("tiefe", "breite", "radius")):
                    return 1e12
                raw = [_roh_w(k, w, wmin, wmax) for w in ws]
                c = min(raw)
                return sum((d - (x_ - c)) ** 2 for d, x_ in zip(ds, raw)) / len(ds)
            x, wert = _nelder_mead(kosten, x0, schr)
            k = k_aus(x)
            if typ in (V_KERBE, U_KERBE, U_ZUNGE) and _z(k.get("breite")) > wmax - wmin + 2 * tol:
                continue                    # breiter als das Rohr: keine Kerbe/Zunge (dann Bogen, Spitze …)
            if wert <= 1.0:                 # grob passend; genau entscheidet der Kurvenabstand unten
                kandidaten.append(k)
                if "tiefe" in namen:        # Sprünge (U-Kerbe/-Zunge) ziehen die Tiefe beim Ausgleich: wie gemessen
                    kandidaten.append(dict(k, tiefe=x0[namen.index("tiefe")]))
            if kosten(x0) <= 1.0:
                kandidaten.append(k_aus(x0))
    beste = None
    symm = (V_SPITZE, V_KERBE, U_KERBE, U_ZUNGE, BOGEN_VEX, BOGEN_KAV)
    for k in kandidaten:
        r = _z(k.get("richtung")) % 360
        if k["typ"] in symm and r >= 180 - 1e-6:            # gleiche Kontur von der anderen Seite
            k = dict(k, richtung=r - 180, versatz=-_z(k.get("versatz")))
        if k["typ"] in (BOGEN_VEX, BOGEN_KAV):
            pk = umriss(qs, k)
            k = dict(k, tiefe=max(d for _, d in pk) if pk else 0.0)
        r = _z(k.get("richtung"))
        richtungen = [r] if not qs.r else sorted({round(r / 5) * 5.0, float(round(r)), round(r, 1), r},
                                                 key=lambda x: (x % 5 != 0, x % 1 != 0, abs(x - r)))
        fertig = False
        for rr in richtungen:
            for stellen in (1, 2):
                rr_, vz = (rr - 180, -1) if k["typ"] in symm and rr % 360 >= 180 - 1e-6 else (rr, 1)
                kk = _runden(dict(k, richtung=rr_ % 360, versatz=vz * _z(k.get("versatz"))), stellen)
                if kk["typ"] in (BOGEN_VEX, BOGEN_KAV) and "radius" in kk:
                    ohne = {x: y for x, y in kk.items() if x != "radius"}      # Radius aus der Tiefe, wenn gleich
                    if abs(_bogen_r(ohne, (lambda a, b: (b - a) / 2)(*_wbereich(qs, _z(kk.get("richtung")))))
                           - kk["radius"]) < 0.05:
                        kk = ohne
                pk = umriss(qs, kk)
                if not pk:
                    continue
                # jeder gemessene Punkt (Kante der STEP) auf tol an der Kontur; umgekehrt darf die Kontur zwischen
                # den Messpunkten etwas mehr abweichen (die Messung verbindet ihre Punkte gerade, an steilen Stellen
                # wie der Wand einer U-Kerbe liegt die Sehne bis 0,2 mm neben der echten Kante), nur keine fehlende
                # Form (3 × tol)
                x, x_rueck = kurven_abstand(gemessen_pk, pk, U, beide=True)
                if x <= tol and x_rueck <= 3 * tol:
                    if beste is None or x < beste[0] - 1e-3:
                        beste = (x, kk)
                    fertig = True
                    break
            if fertig:
                break
    if not beste:
        return None
    return dict(kontur=beste[1], abweichung=round(beste[0], 3))
