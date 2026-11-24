"""Knickrahmen (Plan K1): Rahmen aus einem einzigen Quadrat- oder Rechteckrohr. Der Laser schneidet an jeder Ecke einen
V-Ausschnitt durch drei Wände, nur die Stegwand bleibt stehen; daran wird das Rohr nach dem Lasern geknickt.

Maße (Rohr b × h, h = Maß in der Rahmenebene = quer zur Stegwand, Wand s, Knickwinkel β = Umlenkung am Knick):
  Breite des V an der Innenwand   w = 2 · (h − s) · tan(β/2)
  Schnittlänge je Knick           L = 2 · b + 4 · (h − s) / cos(β/2)  (+ 2 · π · d mit Freistich Ø d an den Spitzen)
  Ausgleich je Knick              v = Ausgleichswert nach DIN 6935 für die Stegwand (Blech der Dicke s, Innenradius 0,
                                      K-Faktor k = Lage der neutralen Faser, 0,5 = Wandmitte; blech.ausgleich)
  gestreckte Länge                L = Σ Außenmaße der Schenkel − n · (v − z)   (z = Knickzugabe je Knick)
  Lage von Knick i (Mitte des V)  x_i = Σ_{j≤i} A_j − (i − 1) · (v − z) − (v − z) / 2
Die Spitzen des V liegen auf der Innenseite der Stegwand; ein V-Ausschnitt ist ein geschlossener Konturzug (1
Einstich). Geschlossener Rahmen: Anfang und Ende stoßen an einer Ecke zusammen, beide Enden bekommen die halbe
Gehrung des Stoßes (Rechteck 45°), längste Seite = Stegwand außen.

Die Konturzeile 'V-Ausschnitt' im Schneidweg-Rechner hat die Maße beta (Knickwinkel) und freistich (Ø), Lage x und
Seite = Stegwand. Der Block 'knickrahmen' in positionen.technik hält die Schenkel:
  {schenkel: [Außenmaße], beta: [Knickwinkel je Knick], geschlossen, steg, freistich, z, k, schraeg, herkunft}
schraeg (Patrick 24.10.2026, Vorgabe aus): die Innenwand gegenüber der Stegwand wird um β/2 geschwenkt geschnitten
(3D), damit die Stirnflächen nach dem Knicken voll aufeinanderliegen; gerade (2D) lässt sich auch knicken, innen
bleibt dann ein kleiner Keilspalt. Die V-Zeilen tragen dann d3, die Eingaben das Häkchen 3D (dreid.bearbeitungen).

Schließungen am Scheitel (Plan Paket 7 nach ArTube 2.2 „Biegeschnitte“; Felder je V-Zeile und im Block, ohne
erfundene Vorgabewerte):
  spitz                 die Flanken treffen sich an der Innenseite der Stegwand (auf Wunsch mit Freistich = Öse)
  abgeschrägt           gerades Stück der Länge Grat g zwischen den Flanken (Abstand der Seiten nach dem Knicken)
  Radius symmetrisch    Deckel am Scheitel: gerades Stück der Länge D = β · (R − s/2) + Korrektur (Bogen der
                        Wandmitte bei Außenradius R; Korrektur < 0 verschiebt die Ebene nach innen); der Ausgleich
                        rechnet mit Innenradius R − s
  Radius asymmetrisch   wie symmetrisch, eine Flanke gerade (quer zur Achse), die andere um β geneigt (β < 90°)
Verankerung (Breite × Höhe): Nase an der linken Flanke (in den Ausschnitt), Aussparung gleicher Größe an der rechten;
nach dem Knicken greift die Nase in die Aussparung. Die Schnittlänge ist dann der Umfang des Umrisses."""
import math

FORMEN = ("Quadratrohr", "Rechteckrohr")
ZUSATZ_KNICKEN, KNICKEN_PREIS = "Knicken", 2.00      # € je Knick (Beispielpreis)
K_FAKTOR = 0.5          # neutrale Faser in Wandmitte (entspricht k = 1,0 in der Schreibweise von DIN 6935)
STEG_RICHTUNG = {"oben": 0, "vorne": 90, "unten": 180, "hinten": 270}     # Stegwand = längste Seite der Gehrung
STEG_VORGABE = "unten"
HERKUNFT_HAND = "manuell"
SPITZ, ABGESCHRAEGT, RADIUS_SYM, RADIUS_ASYM = "spitz", "abgeschrägt", "Radius symmetrisch", "Radius asymmetrisch"
SCHLIESSUNGEN = (SPITZ, ABGESCHRAEGT, RADIUS_SYM, RADIUS_ASYM)
SCHLIESS_FELDER = ("schliessung", "grat", "radius", "korrektur", "anker_b", "anker_h")


def _z(x):
    try:
        return float(x) if x not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def lesen(e):
    """Block 'knickrahmen' aus den Eingaben des Rechners (dict) oder None."""
    k = (e or {}).get("knickrahmen") if isinstance(e, dict) else None
    return k if isinstance(k, dict) and len(k.get("schenkel") or ()) >= 2 else None


def querschnitt(profil, steg=None):
    """(b, h, s) für die Stegwand steg: b = Breite der Stegwand, h = Maß quer dazu (in der Rahmenebene), s = Wand.
    Breitseite oben und unten wie in der Skizze. ValueError, wenn das Profil kein Quadrat-/Rechteckrohr ist."""
    form = (profil or {}).get("form")
    if form not in FORMEN:
        raise ValueError(f"V-Ausschnitt und Knickrahmen nur bei Quadrat- und Rechteckrohr (Profil: {form or '?'}).")
    a, b, s = _z(profil.get("a")), _z(profil.get("b")) or _z(profil.get("a")), _z(profil.get("wand"))
    if a <= 0 or s <= 0 or 2 * s >= min(a, b):
        raise ValueError("V-Ausschnitt: Profilmaße und Wandstärke fehlen oder passen nicht.")
    breit, schmal = max(a, b), min(a, b)
    return (breit, schmal, s) if (steg or STEG_VORGABE) in ("oben", "unten") else (schmal, breit, s)


def _beta(beta):
    b = _z(beta)
    if not 0 < b < 180:
        raise ValueError("V-Ausschnitt: Knickwinkel β zwischen 0° und 180° eingeben (Rechteck-Rahmen 90°).")
    return b


def schliessung(e):
    """Schließung und Verankerung aus einer V-Zeile bzw. dem Block: dict(art, grat, radius, korrektur, anker_b,
    anker_h); ValueError bei fehlenden Werten (es gibt keine Vorgaben)."""
    e = e or {}
    art = e.get("schliessung") or SPITZ
    if art not in SCHLIESSUNGEN:
        raise ValueError(f"V-Ausschnitt: unbekannte Schließung „{art}“.")
    sl = dict(art=art, grat=_z(e.get("grat")), radius=_z(e.get("radius")), korrektur=_z(e.get("korrektur")),
              anker_b=_z(e.get("anker_b")), anker_h=_z(e.get("anker_h")))
    if art == ABGESCHRAEGT and sl["grat"] <= 0:
        raise ValueError("V-Ausschnitt abgeschrägt: Grat (Länge des geraden Stücks) eingeben.")
    if art in (RADIUS_SYM, RADIUS_ASYM) and sl["radius"] <= 0:
        raise ValueError("V-Ausschnitt mit Radius: Außenradius eingeben.")
    if (sl["anker_b"] > 0) != (sl["anker_h"] > 0) or sl["anker_b"] < 0 or sl["anker_h"] < 0:
        raise ValueError("Verankerung: Breite und Höhe der Nase eingeben (beide 0 = ohne).")
    return sl


def schliessung_text(e):
    """Zusatz für Maße und Skizze: ', abgeschrägt Grat 2', ', Radius symmetrisch R 6', ', Verankerung 8 × 3'."""
    from .rechnen import zahl
    art = (e or {}).get("schliessung") or SPITZ
    t = ""
    if art == ABGESCHRAEGT:
        t = f", abgeschrägt Grat {zahl(_z(e.get('grat')), 2)}"
    elif art in (RADIUS_SYM, RADIUS_ASYM):
        t = f", {art} R {zahl(_z(e.get('radius')), 2)}" + (
            f" Korrektur {zahl(_z(e.get('korrektur')), 2)}" if _z(e.get("korrektur")) else "")
    if _z((e or {}).get("anker_b")) > 0:
        t += f", Verankerung {zahl(_z(e.get('anker_b')), 2)} × {zahl(_z(e.get('anker_h')), 2)}"
    return t


def deckel(beta, s, sl):
    """Länge des geraden Stücks am Scheitel [mm]: Grat bzw. Deckel β · (R − s/2) + Korrektur; 0 bei spitz."""
    if sl["art"] == ABGESCHRAEGT:
        return sl["grat"]
    if sl["art"] in (RADIUS_SYM, RADIUS_ASYM):
        if sl["radius"] < s:
            raise ValueError("V-Ausschnitt mit Radius: Außenradius mindestens so groß wie die Wandstärke.")
        d = math.radians(_beta(beta)) * (sl["radius"] - s / 2) + sl["korrektur"]
        if d <= 0:
            raise ValueError("V-Ausschnitt mit Radius: Korrektur zu stark negativ (Deckel ≤ 0).")
        return d
    return 0.0


def _halb_v(t, beta, s, sl):
    """Halber V (eine Seitenwand) als Linienzug [(dx, Tiefe)] von der offenen Seite links über den Scheitel nach
    rechts; Tiefe 0 = Kante zur Gegenwand, t = Innenseite der Stegwand."""
    beta = _beta(beta)
    d = deckel(beta, s, sl)
    if sl["art"] == RADIUS_ASYM:
        pts = [(-d / 2, 0.0), (-d / 2, t)] + [(d / 2 + x, t + y) for x, y in _asym_rechts(t, beta)]
    else:
        q = t * math.tan(math.radians(beta / 2))
        pts = [(-d / 2 - q, 0.0)] + ([(-d / 2, t), (d / 2, t)] if d > 0 else [(0.0, t)]) + [(d / 2 + q, 0.0)]
    if sl["anker_b"] > 0:
        pts = _anker(pts, sl["anker_b"], sl["anker_h"])
    return pts


def _asym_rechts(t, beta):
    """Asymmetrisch: die linke Seite bleibt gerade (Schnitt quer), rechts wird weggeschnitten, was die linke
    Seitenwand nach dem Knicken um β überdeckt. Weg vom Scheitel (0, 0) bis zur Kante zur Gegenwand (y = −t), relativ
    zum Scheitel (x längs, y = Tiefe − t). Bis 90° eine geneigte Flanke, darüber mit zusätzlicher Kante entlang der
    Stegwand."""
    w = math.radians(beta)
    c, s_ = math.cos(w), math.sin(w)

    def zurueck(p):                 # Punkt in die Lage vor dem Knicken (Drehung um −β)
        return (c * p[0] + s_ * p[1], -s_ * p[0] + c * p[1])
    poly = [(0.0, 0.0), (4 * t + 1, 0.0), (4 * t + 1, -t), (0.0, -t)]
    for test in (lambda q: zurueck(q)[0] <= 1e-9, lambda q: zurueck(q)[1] >= -t - 1e-9,
                 lambda q: zurueck(q)[1] <= 1e-9):
        neu = []
        for i, p in enumerate(poly):
            q = poly[i - 1]
            if test(p):
                if not test(q):
                    neu.append(_schnitt_seg(q, p, test))
                neu.append(p)
            elif test(q):
                neu.append(_schnitt_seg(q, p, test))
        poly = neu
    poly = [p for i, p in enumerate(poly) if math.dist(p, poly[i - 1]) > 1e-7]
    i0 = min(range(len(poly)), key=lambda i: math.hypot(*poly[i]))
    poly = poly[i0:] + poly[:i0]
    if abs(poly[1][0]) < 1e-6:              # nächste Ecke liegt auf der geraden Seite: andersherum laufen
        poly = [poly[0]] + poly[:0:-1]
    weg = [poly[0]]
    for p in poly[1:]:
        weg.append(p)
        if p[1] <= -t + 1e-6:
            break
    return [(round(x, 6), round(y, 6)) for x, y in weg]


def _schnitt_seg(a, b, test, n=60):
    """Grenzpunkt auf der Strecke a–b zwischen erfüllt und nicht erfüllt (Halbierung)."""
    lo, hi = (a, b) if test(a) else (b, a)
    for _ in range(n):
        m = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
        if test(m):
            lo = m
        else:
            hi = m
    return lo


def _anker(pts, ab, ah):
    """Nase an der ersten Flanke (in den Ausschnitt), Aussparung an der letzten (ins Material), je in der Mitte."""
    def flanke(a, b, nase):
        lg = math.dist(a, b)
        if ab >= 0.8 * lg:
            raise ValueError(f"Verankerung: Breite {ab:g} mm passt nicht auf die Flanke ({lg:.1f} mm).")
        u = ((b[0] - a[0]) / lg, (b[1] - a[1]) / lg)
        n = (u[1], -u[0]) if nase else (-u[1], u[0])        # beide zeigen nach +dx (rechts)
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        p1 = (m[0] - u[0] * ab / 2, m[1] - u[1] * ab / 2)
        p2 = (m[0] + u[0] * ab / 2, m[1] + u[1] * ab / 2)
        return [p1, (p1[0] + n[0] * ah, p1[1] + n[1] * ah), (p2[0] + n[0] * ah, p2[1] + n[1] * ah), p2]
    links = flanke(pts[0], pts[1], True)
    # Spalt neben der Nase: rechte Flanke in derselben Tiefe
    (ax, ay), (bx, by) = pts[-2], pts[-1]
    for qx, qy in links:
        if abs(ay - by) > 1e-9:
            f = min(1.0, max(0.0, (qy - by) / (ay - by)))
            rechts_x = bx + (ax - bx) * f
        else:
            rechts_x = min(ax, bx)
        if qx >= rechts_x - 0.1 or qy < 0:
            raise ValueError(f"Verankerung: Nase {ah:g} mm zu hoch, sie stößt an die andere Flanke.")
    return [pts[0]] + links + pts[1:-1] + flanke(pts[-2], pts[-1], False) + [pts[-1]]


def _sonder(e):
    """Hat die Zeile eine Schließung außer spitz oder eine Verankerung?"""
    return (e or {}).get("schliessung") not in (None, "", SPITZ) or _z((e or {}).get("anker_b")) > 0


def v_masse(b, h, s, beta, freistich=0.0, sl=None):
    """dict(w = Breite an der Innenwand, laenge = Schnittlänge, huelle, tiefe = Tiefe des V (h − s))."""
    beta = _beta(beta)
    t = h - s
    halb = math.radians(beta / 2)
    w = 2 * t * math.tan(halb)
    d = max(0.0, _z(freistich))
    if sl and _sonder(sl if "art" not in sl else dict(schliessung=sl["art"], anker_b=sl["anker_b"])):
        sl = sl if "art" in sl else schliessung(sl)
        um = v_umriss(b, h, s, beta, 0.0, sl=sl)
        xs = [p[0] for p in um]
        lg = sum(math.dist(um[i], um[(i + 1) % len(um)]) for i in range(len(um)))
        w = max(xs) - min(xs)
        return dict(w=w, laenge=lg, huelle=max(w, b + 2 * t), tiefe=t, mitte=(max(xs) + min(xs)) / 2)
    return dict(w=w, laenge=2 * b + 4 * t / math.cos(halb) + 2 * math.pi * d, huelle=max(w + d, b + 2 * t + d),
                tiefe=t)


def v_umriss(b, h, s, beta, freistich=0.0, n=12, sl=None):
    """Umriss des V-Ausschnitts auf der Abwicklung [[dx längs, ds am Umfang]] um die Mitte der Stegwand (Spalte
    Seite): Innenwand gegenüber (ds = b + h), die Spitzen auf den Seitenwänden an der Innenseite der Stegwand.
    Freistich: Kreis um jede Spitze; der Umriss läuft die Flanken bis an den Kreis und außen um ihn herum (ein
    einfacher Linienzug, sonst zählte der Kreis innerhalb des V doppelt und bliebe als Material stehen).
    sl = Schließung (schliessung): abgeschrägt, Radius oder Verankerung ersetzen die Spitze (_halb_v)."""
    if sl and (sl.get("art") or SPITZ) != SPITZ or sl and sl.get("anker_b"):
        t, c = h - s, b + h
        oben, unten = c + b / 2, c - b / 2
        halb = _halb_v(t, beta, s, sl)
        pts = [(x, oben + d) for x, d in halb] + [(x, unten - d) for x, d in reversed(halb)]
        return [[round(x, 2), round(y, 2)] for x, y in pts]
    m = v_masse(b, h, s, beta)
    w, t, c = m["w"], m["tiefe"], b + h
    r = max(0.0, _z(freistich)) / 2

    def spitze(ds, links, rechts):
        """Spitze bei (0, ds) zwischen den Flanken zu den Punkten links und rechts (der offenen Seite des V)."""
        if not r:
            return [(0.0, ds)]
        r_ = min(r, 0.95 * math.hypot(links[0], links[1] - ds), 0.95 * math.hypot(rechts[0], rechts[1] - ds))
        a1 = math.atan2(links[1] - ds, links[0])
        a2 = math.atan2(rechts[1] - ds, rechts[0])
        weg = (a2 - a1) % (2 * math.pi)          # gegen den Uhrzeiger von links nach rechts
        if weg < math.pi:                           # außen herum = der lange Bogen
            weg -= 2 * math.pi
        k = max(n, 4)
        return [(r_ * math.cos(a1 + weg * i / k), ds + r_ * math.sin(a1 + weg * i / k)) for i in range(k + 1)]
    oben, unten = c + b / 2, c - b / 2
    pts = [(-w / 2, oben)] + spitze(oben + t, (-w / 2, oben), (w / 2, oben)) + [(w / 2, oben), (w / 2, unten)] \
        + spitze(unten - t, (w / 2, unten), (-w / 2, unten)) + [(-w / 2, unten)]
    return [[round(x, 2), round(y, 2)] for x, y in pts]


def zeile_ergaenzen(e, profil):
    """Konturzeile V-Ausschnitt mit Querschnitt (qs = [b, h, s]) und Umriss für das Profil; ValueError ohne passendes
    Profil."""
    b, h, s = querschnitt(profil, e.get("seite"))
    sl = schliessung(e) if _sonder(e) else None
    return dict(e, qs=[b, h, s], umriss=v_umriss(b, h, s, e.get("beta"), e.get("freistich"), sl=sl))


def kontur(e):
    """(Schnittlänge je Stück, Hüllmaß) einer Konturzeile V-Ausschnitt (mit qs, zeile_ergaenzen)."""
    qs = e.get("qs")
    if not qs or len(qs) != 3:
        raise ValueError("V-Ausschnitt: nur bei Quadrat- und Rechteckrohr.")
    m = v_masse(*map(float, qs), e.get("beta"), e.get("freistich"), sl=schliessung(e) if _sonder(e) else None)
    return m["laenge"], m["huelle"]


def ausgleich(beta, s, k=K_FAKTOR, sl=None):
    """Ausgleichswert v je Knick [mm] (Abzug von den Außenmaßen, DIN 6935, Innenradius 0; mit Schließung Radius
    Innenradius R − s)."""
    from .blech import ausgleich as v
    ri = max(0.0, sl["radius"] - s) if sl and sl["art"] in (RADIUS_SYM, RADIUS_ASYM) else 0.0
    return v(_beta(beta), ri, s, k)


def _liste(werte, n, name):
    if isinstance(werte, (list, tuple)):
        out = [_z(x) for x in werte]
    else:
        out = [_z(werte)] * n
    if len(out) == 1 and n > 1:
        out *= n
    if len(out) != n:
        raise ValueError(f"Knickrahmen: {n} {name} erwartet, {len(out)} eingegeben.")
    return out


def rahmen(k, profil):
    """Knickrahmen aus dem Block k (lesen) für das Profil: dict(laenge, v, knicke=[dict(nr, x, beta, w, laenge)],
    enden = dict(winkel, richtung) oder None (offen), stoss = Stoßwinkel oder None, schenkel, b, h, s).
    ValueError bei unmöglichen Eingaben."""
    schenkel = [_z(x) for x in k.get("schenkel") or ()]
    if len(schenkel) < 2 or min(schenkel) <= 0:
        raise ValueError("Knickrahmen: mindestens zwei Schenkel mit Außenmaß > 0 eingeben.")
    n = len(schenkel) - 1
    steg = k.get("steg") or STEG_VORGABE
    b, h, s = querschnitt(profil, steg)
    betas = [_beta(x) for x in _liste(k.get("beta") if k.get("beta") not in (None, "", []) else 90.0, n,
                                      "Knickwinkel")]
    zug, kf, fs = _z(k.get("z")), _z(k.get("k")) or K_FAKTOR, _z(k.get("freistich"))
    sl = schliessung(k)
    if sl["art"] != SPITZ:
        fs = 0.0                # Freistich (Öse) nur bei spitzem Scheitel
    knicke, pos, enden, stoss = [], 0.0, None, None
    vs = [ausgleich(be, s, kf, sl) for be in betas]
    for i, (a_, be, v) in enumerate(zip(schenkel, betas, vs), start=1):
        netto = v - zug
        pos += a_
        m = v_masse(b, h, s, be, fs, sl=sl if _sonder(k) else None)
        x = round(pos - netto / 2, 2)
        mi = m.get("mitte", 0.0)
        knicke.append(dict(nr=i, x=x, beta=be, w=m["w"], laenge=m["laenge"], links=x + mi - m["w"] / 2,
                           rechts=x + mi + m["w"] / 2))
        pos -= netto
    laenge = pos + schenkel[-1]
    for i in range(1, n):       # Mitte des V muss im Rohr liegen, V dürfen sich nicht überschneiden
        if knicke[i]["links"] < knicke[i - 1]["rechts"]:
            raise ValueError(f"Knickrahmen: Schenkel {i + 1} ist kürzer als die V-Ausschnitte an seinen Enden.")
    rand = 0.0                  # Gehrung am Stoß: die Innenwand endet um h · tan(Gehrung) früher
    if k.get("geschlossen"):
        stoss = 360.0 - sum(betas)
        if not 0 < stoss < 180:
            raise ValueError(f"Knickrahmen: Die Knickwinkel ({'+'.join(f'{x:g}' for x in betas)}°) schließen keinen "
                             "Rahmen (Summe muss zwischen 180° und 360° liegen).")
        enden = dict(winkel=round(stoss / 2, 2), richtung=STEG_RICHTUNG.get(steg, 180))
        rand = h * math.tan(math.radians(stoss / 2))
    if knicke[0]["links"] < rand - 1e-6:
        raise ValueError("Knickrahmen: Schenkel 1 ist kürzer als der V-Ausschnitt an seinem Ende.")
    if knicke[-1]["rechts"] > laenge - rand + 1e-6:
        raise ValueError(f"Knickrahmen: Schenkel {n + 1} ist kürzer als der V-Ausschnitt an seinem Ende.")
    return dict(laenge=laenge, v=vs[0] if len(set(round(x, 6) for x in vs)) == 1 else None, vs=vs, knicke=knicke,
                enden=enden, stoss=stoss, schenkel=schenkel, b=b, h=h, s=s, steg=steg, z=zug, k=kf, freistich=fs,
                schraeg=bool(k.get("schraeg")), schliessung={x: k.get(x) for x in SCHLIESS_FELDER if k.get(x)})


def konturen(r, k=None):
    """Konturzeilen V-Ausschnitt des Rahmens (r = rahmen) für den Schneidweg-Rechner."""
    out = []
    for kn in r["knicke"]:
        z = dict(art="V-Ausschnitt", anzahl=1, beta=kn["beta"], x=kn["x"], knick=kn["nr"])
        if r["steg"] != "oben":
            z["seite"] = r["steg"]
        if r["freistich"]:
            z["freistich"] = r["freistich"]
        if r.get("schraeg"):
            z["d3"] = True
        z.update(r.get("schliessung") or {})
        out.append(z)
    return out


def anwenden(eingaben, k, profil):
    """Eingaben des Rechners mit Knickrahmen k: V-Ausschnitte aus dem Rahmen (vorhandene V-Ausschnitte fallen weg),
    beim geschlossenen Rahmen die Gehrung beider Enden. Ohne k (None) fallen Block und V-Ausschnitte weg. War der
    Rahmen vorher geschlossen und ist es nicht mehr, werden die Enden wieder gerade. Ergebnis (neue Eingaben,
    rahmen oder None)."""
    from . import schneidweg as sw
    alt = lesen(eingaben)
    neu = {x: y for x, y in eingaben.items() if x != "knickrahmen"}
    neu["konturen"] = [z for z in eingaben.get("konturen") or () if z.get("art") != sw.V_AUSSCHNITT]
    r = rahmen(k, profil) if k else None
    if alt and alt.get("geschlossen") and not (r and r["enden"]):
        neu["a"], neu["b"] = {}, {}         # Gehrung des Stoßes kam vom Rahmen
    if alt and alt.get("schraeg") and not (r and r["schraeg"]) and not any(
            (neu.get(s) or {}).get("d3") for s in ("a", "b")) and not any(z.get("d3") for z in neu["konturen"]):
        neu.pop("d3", None)                 # 3D kam nur von der schrägen Innenwand
    if r and r["schraeg"]:
        neu["d3"] = True
    if not k:
        return neu, None
    neu["konturen"] += konturen(r)
    if r["enden"]:
        richtung = r["enden"]["richtung"]
        for seite in ("a", "b"):
            neu[seite] = dict(winkel=r["enden"]["winkel"], achse=sw.achse_zu_richtung(profil, richtung),
                              richtung=richtung)
    neu["knickrahmen"] = dict(k, schenkel=r["schenkel"], steg=r["steg"], herkunft=k.get("herkunft") or HERKUNFT_HAND)
    return neu, r


def passt(eingaben, r):
    """Stimmen die V-Ausschnitte der Eingaben noch mit dem Rahmen r überein (Zahl, Lage, Knickwinkel, Stegwand,
    Freistich)? False, wenn sie von Hand geändert wurden."""
    def sl(z):
        return tuple(str(z.get(x) or "") for x in SCHLIESS_FELDER)
    ist = sorted(((round(_z(z.get("x")), 1), round(_z(z.get("beta")), 2), z.get("seite") or "oben",
                   round(_z(z.get("freistich")), 2), sl(z)) for z in (eingaben or {}).get("konturen") or ()
                  for _ in range(int(_z(z.get("anzahl")) or 0)) if z.get("art") == "V-Ausschnitt"))
    soll = sorted(((round(_z(z["x"]), 1), round(_z(z["beta"]), 2), z.get("seite") or "oben",
                    round(_z(z.get("freistich")), 2), sl(z)) for z in konturen(r)))
    return ist == soll


def nachfuehren(eingaben, profil):
    """Block 'knickrahmen' passend zu den V-Ausschnitten der Eingaben, wenn diese von Hand geändert wurden (verschoben
    im Teile-Editor, Knickwinkel, Stegwand oder Freistich in der Tabelle): Schenkel aus der Lage der Knicke, die
    gestreckte Länge bleibt (der letzte Schenkel gleicht aus). Ergebnis neuer Block oder None (passt schon, kein
    Rahmen oder nicht nachführbar: andere Zahl der Knicke, Muster, verschiedene Stegwände, unmöglicher Rahmen)."""
    k = lesen(eingaben)
    if not k:
        return None
    try:
        r = rahmen(k, profil)
    except ValueError:
        return None
    if passt(eingaben, r):
        return None
    zeilen = [z for z in eingaben.get("konturen") or () if z.get("art") == "V-Ausschnitt"]
    if len(zeilen) != len(r["knicke"]) or any(int(_z(z.get("anzahl")) or 0) != 1 or z.get("x") is None
                                              for z in zeilen):
        return None
    zeilen.sort(key=lambda z: _z(z["x"]))
    stege = {z.get("seite") or "oben" for z in zeilen}
    freistiche = {round(_z(z.get("freistich")), 3) for z in zeilen}
    if len(stege) != 1 or len(freistiche) != 1:
        return None
    steg = stege.pop()
    try:
        s = querschnitt(profil, steg)[2]
        betas = [_beta(z.get("beta")) for z in zeilen]
    except ValueError:
        return None
    netto = [ausgleich(be, s, r["k"]) - r["z"] for be in betas]
    xs = [_z(z["x"]) for z in zeilen]
    schenkel = [xs[0] + netto[0] / 2]
    schenkel += [xs[i] - xs[i - 1] + netto[i - 1] / 2 + netto[i] / 2 for i in range(1, len(xs))]
    schenkel.append(r["laenge"] - xs[-1] + netto[-1] / 2)
    neu = dict(k, schenkel=[round(a, 2) for a in schenkel], beta=betas if len(set(betas)) > 1 else betas[0],
               steg=steg, freistich=freistiche.pop() or 0.0)
    try:
        rahmen(neu, profil)
    except ValueError:
        return None
    return neu


def anzahl(eingaben):
    """Zahl der V-Ausschnitte (Knicke) je Teil in den Eingaben."""
    return sum(int(_z(z.get("anzahl")) or 0) for z in (eingaben or {}).get("konturen") or ()
               if z.get("art") == "V-Ausschnitt")


def _zahl(x, n=1):
    t = f"{round(float(x), n):.{n}f}".replace(".", ",")
    while "," in t and t.endswith("0"):
        t = t[:-1]
    return t.rstrip(",")


def kurz(r):
    """z. B. 'geschlossen, 3 Knicke, gestreckt 1592,7 mm (Ausgleich 2,43 mm je Knick)'."""
    n = len(r["knicke"])
    v = f"{_zahl(r['v'], 2)} mm je Knick" if r["v"] is not None else "je Knick verschieden"
    return (f"{'geschlossen' if r['enden'] else 'offen'}, {n} Knick{'e' if n != 1 else ''}, gestreckt "
            f"{_zahl(r['laenge'])} mm (Ausgleich {v}" + (f", Zugabe {_zahl(r['z'], 2)} mm" if r["z"] else "") + ")"
            + (", Innenwand schräg (3D)" if r.get("schraeg") else ""))


def zusatz_eintragen(zusatz_json, n, katalog, quelle):
    """Spalte Zusatzarbeiten (JSON) mit 'Knicken' × n (Menge = Zahl der Knicke je Teil); n = 0 nimmt einen Eintrag
    dieser Quelle wieder heraus. Ergebnis (JSON oder None, fehlt = Knicken nicht in den Stammdaten)."""
    import json
    from . import rechnen
    liste = rechnen.zusatz_liste(dict(zusatz=zusatz_json))
    kat = {z.get("name"): z for z in katalog or ()}
    out, da = [], False
    for e in liste:
        if e.get("name") == ZUSATZ_KNICKEN:
            if n:
                out.append(dict(e, menge=n))
                da = True
            elif e.get("quelle") != quelle:
                out.append(e)
        else:
            out.append(e)
    fehlt = False
    if n and not da:
        if ZUSATZ_KNICKEN in kat:
            out.append(dict(name=ZUSATZ_KNICKEN, menge=n, preis=None, text=None, quelle=quelle,
                            stand=rechnen.zusatz_stand(kat[ZUSATZ_KNICKEN])))
        else:
            fehlt = True
    return (json.dumps(out, ensure_ascii=False) if out else None), fehlt
