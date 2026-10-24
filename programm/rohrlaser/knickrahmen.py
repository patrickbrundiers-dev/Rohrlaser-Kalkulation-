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
bleibt dann ein kleiner Keilspalt. Die V-Zeilen tragen dann d3, die Eingaben das Häkchen 3D (dreid.bearbeitungen)."""
import math

FORMEN = ("Quadratrohr", "Rechteckrohr")
ZUSATZ_KNICKEN, KNICKEN_PREIS = "Knicken", 2.00      # € je Knick (Beispielpreis)
K_FAKTOR = 0.5          # neutrale Faser in Wandmitte (entspricht k = 1,0 in der Schreibweise von DIN 6935)
STEG_RICHTUNG = {"oben": 0, "vorne": 90, "unten": 180, "hinten": 270}     # Stegwand = längste Seite der Gehrung
STEG_VORGABE = "unten"
HERKUNFT_HAND = "manuell"


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


def v_masse(b, h, s, beta, freistich=0.0):
    """dict(w = Breite an der Innenwand, laenge = Schnittlänge, huelle, tiefe = Tiefe des V (h − s))."""
    beta = _beta(beta)
    t = h - s
    halb = math.radians(beta / 2)
    w = 2 * t * math.tan(halb)
    d = max(0.0, _z(freistich))
    return dict(w=w, laenge=2 * b + 4 * t / math.cos(halb) + 2 * math.pi * d, huelle=max(w + d, b + 2 * t + d),
                tiefe=t)


def v_umriss(b, h, s, beta, freistich=0.0, n=12):
    """Umriss des V-Ausschnitts auf der Abwicklung [[dx längs, ds am Umfang]] um die Mitte der Stegwand (Spalte
    Seite): Innenwand gegenüber (ds = b + h), die Spitzen auf den Seitenwänden an der Innenseite der Stegwand."""
    m = v_masse(b, h, s, beta)
    w, t, c = m["w"], m["tiefe"], b + h
    r = max(0.0, _z(freistich)) / 2

    def spitze(ds):         # Freistich: Kreis um die Spitze (Linienzug läuft einmal herum)
        if not r:
            return [(0.0, ds)]
        return [(r * math.sin(2 * math.pi * i / n), ds + r * math.cos(2 * math.pi * i / n) * (1 if ds > c else -1))
                for i in range(n + 1)]
    pts = [(-w / 2, c + b / 2)] + spitze(c + b / 2 + t) + [(w / 2, c + b / 2), (w / 2, c - b / 2)] \
        + spitze(c - b / 2 - t) + [(-w / 2, c - b / 2)]
    return [[round(x, 2), round(y, 2)] for x, y in pts]


def zeile_ergaenzen(e, profil):
    """Konturzeile V-Ausschnitt mit Querschnitt (qs = [b, h, s]) und Umriss für das Profil; ValueError ohne passendes
    Profil."""
    b, h, s = querschnitt(profil, e.get("seite"))
    return dict(e, qs=[b, h, s], umriss=v_umriss(b, h, s, e.get("beta"), e.get("freistich")))


def kontur(e):
    """(Schnittlänge je Stück, Hüllmaß) einer Konturzeile V-Ausschnitt (mit qs, zeile_ergaenzen)."""
    qs = e.get("qs")
    if not qs or len(qs) != 3:
        raise ValueError("V-Ausschnitt: nur bei Quadrat- und Rechteckrohr.")
    m = v_masse(*map(float, qs), e.get("beta"), e.get("freistich"))
    return m["laenge"], m["huelle"]


def ausgleich(beta, s, k=K_FAKTOR):
    """Ausgleichswert v je Knick [mm] (Abzug von den Außenmaßen, DIN 6935, Innenradius 0)."""
    from .blech import ausgleich as v
    return v(_beta(beta), 0.0, s, k)


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
    knicke, pos, enden, stoss = [], 0.0, None, None
    vs = [ausgleich(be, s, kf) for be in betas]
    for i, (a_, be, v) in enumerate(zip(schenkel, betas, vs), start=1):
        netto = v - zug
        pos += a_
        m = v_masse(b, h, s, be, fs)
        knicke.append(dict(nr=i, x=round(pos - netto / 2, 2), beta=be, w=m["w"], laenge=m["laenge"]))
        pos -= netto
    laenge = pos + schenkel[-1]
    for i in range(1, n):       # Mitte des V muss im Rohr liegen, V dürfen sich nicht überschneiden
        if knicke[i]["x"] - knicke[i]["w"] / 2 < knicke[i - 1]["x"] + knicke[i - 1]["w"] / 2:
            raise ValueError(f"Knickrahmen: Schenkel {i + 1} ist kürzer als die V-Ausschnitte an seinen Enden.")
    rand = 0.0                  # Gehrung am Stoß: die Innenwand endet um h · tan(Gehrung) früher
    if k.get("geschlossen"):
        stoss = 360.0 - sum(betas)
        if not 0 < stoss < 180:
            raise ValueError(f"Knickrahmen: Die Knickwinkel ({'+'.join(f'{x:g}' for x in betas)}°) schließen keinen "
                             "Rahmen (Summe muss zwischen 180° und 360° liegen).")
        enden = dict(winkel=round(stoss / 2, 2), richtung=STEG_RICHTUNG.get(steg, 180))
        rand = h * math.tan(math.radians(stoss / 2))
    if knicke[0]["x"] - knicke[0]["w"] / 2 < rand - 1e-6:
        raise ValueError("Knickrahmen: Schenkel 1 ist kürzer als der V-Ausschnitt an seinem Ende.")
    if knicke[-1]["x"] + knicke[-1]["w"] / 2 > laenge - rand + 1e-6:
        raise ValueError(f"Knickrahmen: Schenkel {n + 1} ist kürzer als der V-Ausschnitt an seinem Ende.")
    return dict(laenge=laenge, v=vs[0] if len(set(round(x, 6) for x in vs)) == 1 else None, vs=vs, knicke=knicke,
                enden=enden, stoss=stoss, schenkel=schenkel, b=b, h=h, s=s, steg=steg, z=zug, k=kf, freistich=fs,
                schraeg=bool(k.get("schraeg")))


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
    ist = sorted(((round(_z(z.get("x")), 1), round(_z(z.get("beta")), 2), z.get("seite") or "oben",
                   round(_z(z.get("freistich")), 2)) for z in (eingaben or {}).get("konturen") or ()
                  for _ in range(int(_z(z.get("anzahl")) or 0)) if z.get("art") == "V-Ausschnitt"))
    soll = sorted(((round(_z(z["x"]), 1), round(_z(z["beta"]), 2), z.get("seite") or "oben",
                    round(_z(z.get("freistich")), 2)) for z in konturen(r)))
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
