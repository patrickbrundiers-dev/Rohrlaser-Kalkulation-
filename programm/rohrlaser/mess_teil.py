"""Rohr-, Kontur- und Fertigungsmessung am 3D-Modell (Messplan 19.11.2026, Phase M3). Ohne Qt, ohne Fenster.

Misst ein Rohr- oder Profilteil so, wie es im 3D steht (aus dem STEP oder aus den Eingaben des Editors):
- Rohr: Länge, Außen- und Innenmaß, Wand, Breite/Höhe, Eckradien, Querschnitt, Umfang, Profilform (Rund, Quadrat,
  Rechteck, Oval, offenes Profil, Sonderprofil), Volumen und Masse (nur bei geschlossenem Körper; sonst aus
  Querschnitt × Länge und als genähert gekennzeichnet). Der Querschnitt kommt aus einem Schnitt quer zur Rohrachse
  an der Stelle mit der meisten Wand (Bohrungen und Ausschnitte fallen so heraus).
- Konturen: je Innenkontur und Gravur Länge, offen/geschlossen, Kreis-Ø, Geraden und Bögen mit R, Winkel zwischen
  Geraden, Fläche, Größe längs × um den Umfang, Lage (längs, Umfangswinkel, Seite), doppelte Konturen.
- Fertigung: Lochabstände, kleinster Abstand Kontur–Kontur (Reststeg) und Kontur–Ende gegen die Prüfregeln (dfm
  „Steg zu schmal“, „Kontur zu nah am Rand“, „Großer Ausschnitt“, „Teil stark geschwächt“).

Die Werte sind eine Prüfung neben der Kalkulation: Schneidweg, Laserzeit und Preis rechnen unverändert. Abstände,
Winkel und Flächen kommen aus dem Messkern (mess_kern, ein Rechenweg). Was nur am Netz gewölbter Flächen gemessen
ist, trägt exakt=False und wird mit „≈“ gezeigt. Messen ändert nie etwas am Teil.

Rohrachse ist z (Ende A bei z = zmin), wie in allen Rohrnetzen des Programms (rohr3d, STEP-Messung)."""
import math

from . import mess_kern as mk
from .mess_kern import eintrag_text, zahl

MATERIAL = ("A", "I", "EA", "EB", "K", "G", "N", "EW", "ES")   # Arten, die zum Teil gehören (ohne Anbau, Hilfen)
KONTUR_ARTEN = (("K", "Innenkontur"), ("G", "Gravur"))
ENDEN = ("EA", "EB")
SCHNITTE = 9                     # Querschnitte zwischen 10 % und 90 % der Länge, der mit der meisten Wand zählt
ZEILEN_MAX = 12                  # je Liste (Lochabstände, Konturen) höchstens so viele Zeilen, der Rest als Anzahl
STAHL = 7.85                     # kg/dm³, wenn der Werkstoff unbekannt ist (so angeschrieben)
DOPPELT_TOL = 0.02               # mm: zwei Konturen gleich, wenn Mitte und Länge so genau übereinstimmen


# ---------------------------------------------------------------- Querschnitt
def _schnitt(dreiecke, z):
    """Strecken des Schnitts der Dreiecke mit der Ebene z (in x/y)."""
    out = []
    for a, b, c in dreiecke:
        pk = []
        for p, q in ((a, b), (b, c), (c, a)):
            dp, dq = p[2] - z, q[2] - z
            if (dp < 0) != (dq < 0) and dp != dq:
                t = dp / (dp - dq)
                pk.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        if len(pk) == 2 and math.dist(pk[0], pk[1]) > 1e-9:
            out.append((pk[0], pk[1]))
    return out


def _schleifen(strecken, tol=1e-4):
    """Strecken zu geschlossenen Linienzügen verbinden: Liste [[(x, y), …]]."""
    def k(p):
        return (round(p[0] / tol), round(p[1] / tol))
    nachbarn = {}
    for i, (p, q) in enumerate(strecken):
        nachbarn.setdefault(k(p), []).append((i, 1))
        nachbarn.setdefault(k(q), []).append((i, 0))
    frei = set(range(len(strecken)))
    out = []
    while frei:
        i = frei.pop()
        zug = [strecken[i][0], strecken[i][1]]
        start = k(zug[0])
        while True:
            ende = k(zug[-1])
            if ende == start and len(zug) > 3:
                break
            weiter = next(((j, s) for j, s in nachbarn.get(ende, ()) if j in frei), None)
            if weiter is None:
                break
            j, s = weiter
            frei.discard(j)
            zug.append(strecken[j][s])
        if len(zug) >= 4:
            out.append(zug[:-1] if k(zug[0]) == k(zug[-1]) else zug)
    return out


def _flaeche2(zug):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(zug, zug[1:] + zug[:1]))) / 2


def _umfang2(zug):
    return sum(math.dist(a, b) for a, b in zip(zug, zug[1:] + zug[:1]))


def _innen2(p, zug):
    x, y = p
    drin = False
    for (x1, y1), (x2, y2) in zip(zug, zug[1:] + zug[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            drin = not drin
    return drin


def _abstand_punkt_zug(p, zug):
    best = float("inf")
    for a, b in zip(zug, zug[1:] + zug[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        lg = dx * dx + dy * dy
        t = 0.0 if lg < 1e-18 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lg))
        best = min(best, math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy))
    return best


def material_dreiecke(modell):
    """Dreiecke des Teils (Punkte) aus einem ansicht3d.Modell, ohne Anbauteile, Schnittkörper und Hilfen."""
    p = modell.punkte
    return [(p[i], p[j], p[k]) for i, j, k, art, _ in modell.dreiecke if art in MATERIAL]


def querschnitt(dreiecke):
    """Querschnitt quer zur Rohrachse z an der Stelle mit der meisten Wand: dict(z, aussen, innen, zmin, zmax) oder
    None (kein geschlossener Schnitt). aussen: größter Linienzug, innen: Linienzüge darin."""
    if not dreiecke:
        return None
    zs = [q[2] for t in dreiecke for q in t]
    zmin, zmax = min(zs), max(zs)
    laenge = zmax - zmin
    if laenge <= 1e-6:
        return None
    beste = None
    for n in range(SCHNITTE):
        z = zmin + laenge * (0.1 + 0.8 * n / max(SCHNITTE - 1, 1)) + 1e-7 * laenge
        nahe = [t for t in dreiecke if min(q[2] for q in t) <= z <= max(q[2] for q in t)]
        zuege = _schleifen(_schnitt(nahe, z))
        if not zuege:
            continue
        zuege.sort(key=_flaeche2, reverse=True)
        aussen = zuege[0]
        innen = [zg for zg in zuege[1:] if _innen2(zg[0], aussen)]
        wand = _flaeche2(aussen) - sum(_flaeche2(zg) for zg in innen)
        rang = (round(wand, 3), -abs(z - (zmin + zmax) / 2))
        if beste is None or rang > beste[0]:
            beste = (rang, dict(z=z, aussen=aussen, innen=innen, zmin=zmin, zmax=zmax))
    return beste[1] if beste else None


def _eckradius(b, h, flaeche):
    """Eckradius eines Rechtecks mit gerundeten Ecken aus der Flächenlücke: b·h − A = (4 − π)·R²."""
    luecke = b * h - flaeche
    return math.sqrt(luecke / (4 - math.pi)) if luecke > 1e-6 else 0.0


def _rund(zug, mitte):
    d = [math.dist(p, mitte) for p in zug]
    return max(d) - min(d) <= max(0.05, 0.01 * max(d)), 2 * max(d)


def rohr_werte(dreiecke, volumen=None, dichte=None):
    """Rohrmessung: dict mit form, laenge, breite, hoehe, (d_aussen, d_innen), wand, r_aussen, r_innen, querschnitt,
    umfang, umfang_innen, gewicht, kg_m, exakt (je Wert in genau) oder None (kein Rohrquerschnitt)."""
    q = querschnitt(dreiecke)
    if q is None:
        return None
    aussen, innen = q["aussen"], q["innen"]
    xs, ys = [p[0] for p in aussen], [p[1] for p in aussen]
    b, h = max(xs) - min(xs), max(ys) - min(ys)
    a_aussen = _flaeche2(aussen)
    mitte = ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)
    w = dict(laenge=q["zmax"] - q["zmin"], breite=b, hoehe=h, umfang=_umfang2(aussen), z_schnitt=q["z"],
             genau=dict(laenge=True, breite=True, hoehe=True), aussen=aussen, innen=innen, mitte=mitte)
    ist_rund, d_a = _rund(aussen, mitte)
    a_innen = sum(_flaeche2(zg) for zg in innen)
    w["querschnitt"] = a_aussen - a_innen
    if innen:
        haupt = max(innen, key=_flaeche2)
        xi, yi = [p[0] for p in haupt], [p[1] for p in haupt]
        w["breite_innen"], w["hoehe_innen"] = max(xi) - min(xi), max(yi) - min(yi)
        w["umfang_innen"] = _umfang2(haupt)
        wand = min(min(_abstand_punkt_zug(p, aussen) for p in haupt), min(_abstand_punkt_zug(p, haupt) for p in aussen))
        w["wand"] = wand
        w["genau"]["wand"] = True
        innen_rund, d_i = _rund(haupt, mitte)
        if ist_rund and innen_rund:
            w.update(form="Rundrohr", d_aussen=d_a, d_innen=d_i, wand=(d_a - d_i) / 2)
            # Netzpunkte liegen auf der Fläche, aber auf 0,01 mm gerundet: genähert
            w["genau"].update(d_aussen=False, d_innen=False, wand=False, querschnitt=False, umfang=False)
            w["querschnitt_soll"] = math.pi / 4 * (d_a * d_a - d_i * d_i)
            w["umfang_soll"] = math.pi * d_a
        else:
            r_a = _eckradius(b, h, a_aussen)
            r_i = _eckradius(w["breite_innen"], w["hoehe_innen"], _flaeche2(haupt))
            oval = abs(a_aussen - math.pi / 4 * b * h) <= 0.02 * a_aussen and min(b, h) > 0 and abs(b - h) > 0.01
            if oval:
                w["form"] = "Ovalrohr"
            elif r_a <= 0.5 * min(b, h) + 1e-6 and a_aussen >= 0.95 * (b * h - (4 - math.pi) * (min(b, h) / 2) ** 2):
                w["form"] = "Quadratrohr" if abs(b - h) < 0.01 else "Rechteckrohr"
                w["r_aussen"], w["r_innen"] = r_a, r_i
                eckig = r_a < 0.05 and r_i < 0.05
                w["genau"].update(r_aussen=False, r_innen=False, querschnitt=eckig, umfang=eckig, wand=eckig)
            else:
                w["form"] = "Sonderprofil"
                w["genau"].update(querschnitt=True, umfang=True)
    else:
        w["form"] = "offenes Profil (U, L, T, Flach …)"
        w["wand"] = 2 * w["querschnitt"] / w["umfang"] if w["umfang"] > 0 else None     # dünne Wand: A ≈ s · U / 2
        w["genau"].update(wand=False, querschnitt=True, umfang=True)
    w["genau"].setdefault("querschnitt", False)
    w["genau"].setdefault("umfang", False)
    dichte_ = dichte if isinstance(dichte, (int, float)) and dichte > 0 else None
    w["dichte"], w["dichte_angenommen"] = dichte_ or STAHL, dichte_ is None
    w["kg_m"] = w["querschnitt"] * w["dichte"] / 1000
    if volumen is not None and volumen > 0:
        w["volumen"] = volumen
        w["gewicht"] = volumen * w["dichte"] * 1e-6
        w["gewicht_aus"] = "Volumen"
    else:
        w["gewicht"] = w["kg_m"] * w["laenge"] / 1000
        w["gewicht_aus"] = "Querschnitt × Länge"
    return w


def rohr_zeilen(w):
    """Texte der Rohrmessung."""
    if w is None:
        return ["Kein Rohrquerschnitt gefunden (Teil ist kein gerades Rohr/Profil entlang der Achse)."]
    g = w["genau"]

    def e(name, wert, einheit="mm", schl=None):
        return eintrag_text((name, wert, einheit, g.get(schl, True) if schl else True))
    z = [f"Profilform (gemessen): {w['form']}", e("Länge", w["laenge"], schl="laenge")]
    if w["form"] == "Rundrohr":
        z += [e("Außen-Ø", w["d_aussen"], schl="d_aussen"), e("Innen-Ø", w["d_innen"], schl="d_innen")]
    else:
        z.append(f"Breite × Höhe {zahl(w['breite'])} × {zahl(w['hoehe'])} mm")
        if "breite_innen" in w:
            z.append(f"Innen {zahl(w['breite_innen'])} × {zahl(w['hoehe_innen'])} mm")
    if w.get("wand") is not None:
        z.append(e("Wand", w["wand"], schl="wand"))
    if "r_aussen" in w and max(w["r_aussen"], w["r_innen"]) >= 0.05:
        z.append(eintrag_text(("Eckradius außen", w["r_aussen"], "mm", False)) + " · " +
                 eintrag_text(("innen", w["r_innen"], "mm", False)))
    z.append(e("Querschnitt", w["querschnitt"], "mm²", "querschnitt"))
    if "querschnitt_soll" in w:
        z.append(f"Querschnitt aus Ø (exakt) {zahl(w['querschnitt_soll'])} mm² · Umfang {zahl(w['umfang_soll'])} mm")
    z.append(e("Umfang außen", w["umfang"], schl="umfang"))
    dichte = f"{zahl(w['dichte'], 2)} kg/dm³" + (" (Stahl angenommen, Werkstoff unbekannt)" if w["dichte_angenommen"]
                                                  else "")
    z.append(eintrag_text(("Metergewicht", w["kg_m"], "kg/m", g.get("querschnitt", False))) + f" bei {dichte}")
    z.append(eintrag_text(("Masse", w["gewicht"], "kg", w["gewicht_aus"] == "Volumen" and g.get("querschnitt", False)))
             + f" (aus {w['gewicht_aus']})")
    return z


# ---------------------------------------------------------------- Konturen
def _zug_punkte(zug):
    return [(zug[i], zug[i + 1], zug[i + 2]) for i in range(0, len(zug) - 2, 3)]


def _verketten(zuege, tol=0.02):
    """Linienzüge mit gemeinsamen Endpunkten zu Konturen verbinden (die STEP-Messung liefert je Kante einen Zug)."""
    def k(q):
        return tuple(round(c / tol) for c in q)
    offen = [list(z) for z in zuege if len(z) >= 2]
    fertig = []
    while offen:
        zug = offen.pop()
        weiter = True
        while weiter and k(zug[0]) != k(zug[-1]):
            weiter = False
            for i, z in enumerate(offen):
                if k(z[0]) == k(zug[-1]):
                    zug += z[1:]
                elif k(z[-1]) == k(zug[-1]):
                    zug += z[-2::-1]
                elif k(z[-1]) == k(zug[0]):
                    zug = z + zug[1:]
                elif k(z[0]) == k(zug[0]):
                    zug = z[::-1] + zug[1:]
                else:
                    continue
                offen.pop(i)
                weiter = True
                break
        fertig.append(zug)
    return fertig


def linienzuege(netz):
    """Konturen aus dem Netz: [(Art, Name, Punkte)] für Innenkonturen und Gravuren (Kanten zu Konturen verbunden),
    dazu die Endschnitte."""
    out, enden = [], []
    for art, zuege in ((netz or {}).get("l") or {}).items():
        pks = [_zug_punkte(z) for z in zuege]
        if art in ENDEN:
            enden += [pk for pk in pks if len(pk) >= 2]
            continue
        name = dict(KONTUR_ARTEN).get(art)
        if name:
            out += [(art, name, pk) for pk in _verketten(pks)]
    return out, enden


def _durch_die_wand(konturen, wand):
    """Dieselbe Kontur auf beiden Seiten der Wand gezeichnet (offene Profile, Bleche): Paare (außen, innen) mit
    gleicher Länge und Mitten höchstens 1,5 × Wand auseinander. Die innere fällt aus der Liste."""
    weg = set()
    if not wand:
        return weg
    for i, a in enumerate(konturen):
        for j in range(i + 1, len(konturen)):
            b = konturen[j]
            if i in weg or j in weg or a["art"] != b["art"] or a["geschlossen"] != b["geschlossen"]:
                continue
            if abs(a["laenge"] - b["laenge"]) <= 0.02 * max(a["laenge"], 1.0) + 0.05 and \
                    0.0 < math.dist(a["mitte"], b["mitte"]) <= 1.5 * wand + 0.1:
                weg.add(j)
    return weg


def _segmente(pk, gerade=0.5, ecke=30.0):
    """Linienzug in Geraden und Bögen teilen (genähert, Netz-Linienzug): [['gerade', Länge, a, b, Richtung] |
    ['bogen', Länge, R, Winkel]]. Knick unter gerade° = gerade weiter, ab ecke° = Ecke, dazwischen Bogen."""
    rs = [mk.norm(mk.sub(b, a)) for a, b in zip(pk, pk[1:])]
    keep = [i for i, r in enumerate(rs) if r is not None]
    if not keep:
        return []
    rs = [rs[i] for i in keep]
    lg = [math.dist(pk[i], pk[i + 1]) for i in keep]
    a_ = [pk[i] for i in keep]
    b_ = [pk[i + 1] for i in keep]
    n = len(rs)
    t = [mk.winkel_zwischen(rs[k], rs[k + 1]) for k in range(n - 1)]        # Knick nach Segment k
    bogen = [False] * n

    def b_knoten(k):
        return 0 <= k < n - 1 and gerade <= t[k] < ecke
    for k in range(n):
        links, rechts = b_knoten(k - 1), b_knoten(k)
        if links and rechts:
            bogen[k] = True
    # Randsegmente eines Bogens: dazu, wenn so kurz wie die Bogenschritte
    innen = [lg[k] for k in range(n) if bogen[k]]
    schritt = sorted(innen)[len(innen) // 2] if innen else None
    for k in range(n):
        if not bogen[k] and schritt and (b_knoten(k - 1) or b_knoten(k)) and lg[k] <= 1.5 * schritt:
            nb = (k > 0 and bogen[k - 1]) or (k + 1 < n and bogen[k + 1])
            if nb:
                bogen[k] = True
    teile, k = [], 0
    while k < n:
        j = k
        if bogen[k]:
            while j + 1 < n and bogen[j + 1] and t[j] < ecke:
                j += 1
            dreh = sum(t[k:j])
            laenge = sum(lg[k:j + 1])
            teile.append(["bogen", laenge, laenge / math.radians(dreh) if dreh > 0 else None, dreh])
        else:
            while j + 1 < n and not bogen[j + 1] and t[j] < gerade:
                j += 1
            teile.append(["gerade", sum(lg[k:j + 1]), a_[k], b_[j], rs[k]])
        k = j + 1
    return teile


def _gleicher_kreis(k, mitte):
    """Kreis der Geometrie gehört zur Kontur: Mitten fallen quer zur Kreisachse zusammen (die Konturlinie liegt zur
    Sichtbarkeit etwas über der Fläche, also entlang der Achse versetzt)."""
    d = mk.sub(mitte, k["m"])
    n = mk.norm(k["n"]) or (0.0, 0.0, 1.0)
    laengs = mk.dot(d, n)
    quer = mk.betrag(mk.sub(d, mk.mal(n, laengs)))
    return quer < max(0.05, 0.02 * k["d"]) and abs(laengs) < max(1.0, 0.2 * k["d"])


def kontur_werte(pk, kreise=()):
    """Eine Kontur: dict(laenge, geschlossen, kreis_d, geraden, boegen, ecken, flaeche, eben, mitte, huelle)."""
    geschlossen = len(pk) > 3 and math.dist(pk[0], pk[-1]) < 0.05
    ring = pk[:-1] if geschlossen and math.dist(pk[0], pk[-1]) < 1e-9 else pk
    mitte = tuple(sum(q[i] for q in ring) / len(ring) for i in range(3))
    w = dict(laenge=sum(math.dist(a, b) for a, b in zip(pk, pk[1:])), geschlossen=geschlossen, mitte=mitte,
             huelle=mk.huelle(pk))
    k = next((k for k in kreise if _gleicher_kreis(k, mitte)), None)
    if k is not None and geschlossen:
        w["kreis_d"] = k["d"]
    teile = _segmente(pk + ([pk[0]] if geschlossen and pk[0] != pk[-1] else []))
    if geschlossen and len(teile) == 1 and teile[0][0] == "bogen":     # ganz herum: Kreis
        teile[0][3] = 360.0
        teile[0][2] = teile[0][1] / (2 * math.pi)
        if k is None:
            w["kreis_d_netz"] = 2 * teile[0][2]
    w["geraden"] = [t for t in teile if t[0] == "gerade"]
    w["boegen"] = [t for t in teile if t[0] == "bogen"]
    ecken = []
    for t1, t2 in zip(teile, teile[1:] + (teile[:1] if geschlossen else [])):
        if t1[0] == t2[0] == "gerade":
            ecken.append(mk.winkel_zwischen(t1[4], t2[4]))
    w["ecken"] = ecken
    if geschlossen:
        s = [0.0, 0.0, 0.0]          # Newell: Fläche der Kontur in ihrer mittleren Ebene
        for a, b in zip(ring, ring[1:] + ring[:1]):
            s[0] += (a[1] - b[1]) * (a[2] + b[2])
            s[1] += (a[2] - b[2]) * (a[0] + b[0])
            s[2] += (a[0] - b[0]) * (a[1] + b[1])
        n = mk.norm(tuple(s))
        w["flaeche"] = mk.betrag(tuple(s)) / 2
        w["eben"] = n is not None and max(abs(mk.dot(mk.sub(q, mitte), n)) for q in ring) < 0.02
    return w


def _zug_abstand(a, b):
    """Kleinster Abstand zweier Linienzüge (Messkern, mit Vorauswahl über die Hüllquader)."""
    ha, hb = mk.huelle(a), mk.huelle(b)
    best = (float("inf"), None, None)
    for p1, q1 in zip(a, a[1:]):
        for p2, q2 in zip(b, b[1:]):
            lo1 = [min(p1[i], q1[i]) for i in range(3)]
            hi1 = [max(p1[i], q1[i]) for i in range(3)]
            lo2 = [min(p2[i], q2[i]) for i in range(3)]
            hi2 = [max(p2[i], q2[i]) for i in range(3)]
            luecke = math.sqrt(sum(max(lo1[i] - hi2[i], lo2[i] - hi1[i], 0.0) ** 2 for i in range(3)))
            if luecke >= best[0]:
                continue
            d, x, y = mk.strecke_strecke(p1, q1, p2, q2)
            if d < best[0]:
                best = (d, x, y)
    del ha, hb
    return best


def _umfang_lage(p, w_rohr):
    """Lage eines Punkts um den Umfang: (Bogenlänge auf der Außenkontur ab +y gegen den Uhrzeigersinn, Winkel °)."""
    mx, my = w_rohr["mitte"]
    winkel = math.degrees(math.atan2(-(p[0] - mx), p[1] - my)) % 360       # 0° oben (+y), 90° bei −x
    return winkel


def _seite(p, w_rohr):
    if w_rohr is None:
        return ""
    mx, my = w_rohr["mitte"]
    dx, dy = p[0] - mx, p[1] - my
    if w_rohr["form"] == "Rundrohr":
        return f"{zahl(_umfang_lage(p, w_rohr), 1)}° um den Umfang"
    bx, hy = w_rohr["breite"] / 2 or 1.0, w_rohr["hoehe"] / 2 or 1.0
    if abs(dx) / bx > abs(dy) / hy:
        return "Seite −x (vorn)" if dx < 0 else "Seite +x (hinten)"
    return "oben (+y)" if dy > 0 else "unten (−y)"


def _s_auf_zug(p, zug, kum):
    """Bogenlängen-Lage des nächsten Punkts auf dem geschlossenen Linienzug zug (x/y) [mm]."""
    best = (float("inf"), 0.0)
    for nr, (a, b) in enumerate(zip(zug, zug[1:] + zug[:1])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        lg = dx * dx + dy * dy
        t = 0.0 if lg < 1e-18 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lg))
        d = math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
        if d < best[0]:
            best = (d, kum[nr] + t * math.sqrt(lg))
    return best[1]


def _breite_umfang(pk, w_rohr):
    """Ausdehnung einer Kontur um den Umfang (abgewickelt auf der Außenkontur des Querschnitts) [mm], genähert."""
    if w_rohr is None or w_rohr["umfang"] <= 0:
        return None
    zug = w_rohr["aussen"]
    kum = [0.0]
    for a, b in zip(zug, zug[1:] + zug[:1]):
        kum.append(kum[-1] + math.dist(a, b))
    u = kum[-1]
    ss = sorted(_s_auf_zug(q, zug, kum) for q in pk)
    if len(ss) < 2:
        return 0.0
    luecken = [(ss[(i + 1) % len(ss)] - ss[i]) % u for i in range(len(ss))]
    return u - max(luecken)


def messen(modell, netz, kreise=(), volumen=None, dichte=None, regeln=None):
    """Teilmessung: dict(rohr, konturen, doppelt, loecher, stege, rand, befunde). regeln: dfm.regeln() (Grenzwerte);
    kreise: Kreise der Geometrie (messen3d.Geometrie.kreise) für Ø der Bohrungen."""
    from . import dfm
    regeln = regeln if regeln is not None else dfm.regeln()
    rohr = rohr_werte(material_dreiecke(modell), volumen, dichte) if modell is not None else None
    zuege, enden = linienzuege(netz)
    konturen = []
    hohl = rohr is not None and bool(rohr.get("innen"))
    for art, name, pk in zuege:
        w = kontur_werte(pk, kreise)
        w.update(art=art, name=name, punkte=pk, seite=_seite(w["mitte"], rohr),
                 breite_umfang=_breite_umfang(pk, rohr) if hohl else None)
        w["laenge_laengs"] = w["huelle"][1][2] - w["huelle"][0][2]
        konturen.append(w)
    weg = _durch_die_wand(konturen, rohr.get("wand") if rohr else None)
    beide_seiten = len(weg)
    konturen = [k for i, k in enumerate(konturen) if i not in weg]
    # doppelte Konturen (deckungsgleich: gleiche Mitte, gleiche Länge)
    doppelt = [(i, j) for i in range(len(konturen)) for j in range(i + 1, len(konturen))
               if math.dist(konturen[i]["mitte"], konturen[j]["mitte"]) < DOPPELT_TOL
               and abs(konturen[i]["laenge"] - konturen[j]["laenge"]) < DOPPELT_TOL]
    schnitte = [i for i, k in enumerate(konturen) if k["art"] == "K"]
    # Lochabstände: je Bohrung der nächste Nachbar (Mitte–Mitte)
    loecher = []
    bohr = [i for i in schnitte if "kreis_d" in konturen[i]]
    for i in bohr:
        nb = min(((math.dist(konturen[i]["mitte"], konturen[j]["mitte"]), j) for j in bohr if j != i), default=None)
        if nb is not None and not any(set(x[:2]) == {i, nb[1]} for x in loecher):
            loecher.append((i, nb[1], nb[0]))
    loecher.sort(key=lambda x: x[2])
    # Reststege Kontur–Kontur und Kontur–Ende
    stege = []
    for x, i in enumerate(schnitte):
        for j in schnitte[x + 1:]:
            if (i, j) in doppelt:
                continue
            d, p1, p2 = _zug_abstand(konturen[i]["punkte"], konturen[j]["punkte"])
            stege.append((i, j, d, p1, p2))
    stege.sort(key=lambda x: x[2])
    rand = []
    for i in schnitte:
        best = min((_zug_abstand(konturen[i]["punkte"], e) for e in enden), key=lambda r: r[0], default=None)
        if best is not None:
            rand.append((i, best[0], best[1], best[2]))
    rand.sort(key=lambda x: x[1])
    befunde = []
    wand = rohr.get("wand") if rohr else None
    if wand:
        if dfm.STEG in regeln and stege:
            g, stufe = regeln[dfm.STEG]
            zu = [s for s in stege if s[2] < g * wand - 1e-9]
            if zu:
                befunde.append((stufe, f"{len(zu)} Reststeg(e) unter {zahl(g, 1)} × Wand ({zahl(g * wand)} mm), "
                                       f"kleinster {zahl(zu[0][2])} mm (Prüfregel „{dfm.STEG}“)"))
        if dfm.RAND in regeln and rand:
            g, stufe = regeln[dfm.RAND]
            zu = [r for r in rand if r[1] < g * wand - 1e-9]
            if zu:
                befunde.append((stufe, f"{len(zu)} Kontur(en) näher als {zahl(g, 1)} × Wand ({zahl(g * wand)} mm) "
                                       f"am Ende, kleinster Abstand {zahl(zu[0][1])} mm (Prüfregel „{dfm.RAND}“)"))
    if rohr and dfm.GROSSER_AUSSCHNITT in regeln:
        g, stufe = regeln[dfm.GROSSER_AUSSCHNITT]
        gross = [konturen[i] for i in schnitte if (konturen[i]["breite_umfang"] or 0) > g * rohr["umfang"]]
        if gross:
            befunde.append((stufe, f"{len(gross)} Ausschnitt(e) breiter als {zahl(g, 2)} × Umfang (Prüfregel "
                                   f"„{dfm.GROSSER_AUSSCHNITT}“)"))
    if rohr and dfm.GESCHWAECHT in regeln:
        g, stufe = regeln[dfm.GESCHWAECHT]
        weg = sum(konturen[i].get("flaeche") or 0 for i in schnitte)
        mantel = rohr["umfang"] * rohr["laenge"]
        if mantel > 0 and weg > g * mantel:
            befunde.append((stufe, f"≈ {zahl(100 * weg / mantel, 1)} % der Mantelfläche ausgeschnitten (über "
                                   f"{zahl(100 * g, 0)} %, Prüfregel „{dfm.GESCHWAECHT}“)"))
    if doppelt:
        befunde.append((dfm.REGELN[dfm.DOPPELT][1], f"{len(doppelt)} doppelte Kontur(en) deckungsgleich (würden "
                                                    "zweimal geschnitten)"))
    return dict(rohr=rohr, konturen=konturen, doppelt=doppelt, loecher=loecher, stege=stege, rand=rand,
                befunde=befunde, beide_seiten=beide_seiten)


def _kontur_text(nr, k):
    teile = [f"{nr}. {k['name']}"]
    if "kreis_d" in k:
        teile.append(f"{'Bohrung' if k['art'] == 'K' else 'Kreis'} Ø {zahl(k['kreis_d'])} mm")
    elif "kreis_d_netz" in k:
        teile.append(f"Kreis ≈ Ø {zahl(k['kreis_d_netz'], 2)} mm")
    teile.append(eintrag_text(("Länge", k["laenge"], "mm", False)))
    teile.append("geschlossen" if k["geschlossen"] else "offen")
    if "kreis_d" not in k and "kreis_d_netz" not in k:
        g, b = len(k["geraden"]), len(k["boegen"])
        if g or b:
            seg = f"{g} {'Gerade' if g == 1 else 'Geraden'}, {b} {'Bogen' if b == 1 else 'Bögen'}"
            radien = sorted({round(x[2], 1) for x in k["boegen"] if x[2]})
            if radien:
                seg += " (≈ R " + ", ".join(zahl(r, 1) for r in radien[:4]) + " mm)"
            teile.append(seg)
        if k["ecken"]:
            teile.append("Ecken " + ", ".join(f"{zahl(e, 1)}°" for e in k["ecken"][:6]))
    if k.get("flaeche"):
        teile.append(eintrag_text(("Fläche", k["flaeche"], "mm²", bool(k.get("eben")))))
    groesse = f"Größe längs {zahl(k['laenge_laengs'], 1)} mm"
    if k.get("breite_umfang") is not None:
        groesse += f" × um den Umfang ≈ {zahl(k['breite_umfang'], 1)} mm"
    lage = f"bei längs {zahl(k['mitte'][2], 1)} mm" + (f", {k['seite']}" if k.get("seite") else "")
    return [" · ".join(teile), f"    {groesse} · {lage}"]       # zwei Zeilen: Form, dann Größe und Lage


def gruppen(m):
    """Ergebnis von messen() als Gruppen [(Titel, [Zeilen])] für Fenster, Kopieren und PDF."""
    out = [("Rohr", rohr_zeilen(m["rohr"]))]
    k = m["konturen"]
    z = []
    n_k = sum(1 for x in k if x["art"] == "K")
    n_g = len(k) - n_k
    n_b = sum(1 for x in k if x["art"] == "K" and "kreis_d" in x)
    z.append(f"{n_k} Innenkontur(en), davon {n_b} Bohrung(en); {n_g} Gravur(en)")
    for nr, x in enumerate(k[:ZEILEN_MAX], 1):
        z += _kontur_text(nr, x)
    if len(k) > ZEILEN_MAX:
        z.append(f"… und {len(k) - ZEILEN_MAX} weitere")
    for i, j in m["doppelt"]:
        z.append(f"Doppelt: Kontur {i + 1} und {j + 1} liegen deckungsgleich")
    if m.get("beide_seiten"):
        z.append(f"{m['beide_seiten']} Kontur(en) auch auf der Gegenseite der Wand gezeichnet: einmal gezählt")
    out.append(("Konturen", z))
    f = []
    for i, j, d in m["loecher"][:ZEILEN_MAX]:
        ki, kj = k[i], k[j]
        f.append(f"Lochabstand {i + 1}–{j + 1}: Mitte–Mitte {zahl(d)} mm · ≈ Steg "
                 f"{zahl(d - ki['kreis_d'] / 2 - kj['kreis_d'] / 2)} mm")
    if m["stege"]:
        i, j, d, _, _ = m["stege"][0]
        f.append(eintrag_text(("Kleinster Reststeg Kontur–Kontur", d, "mm", False)) + f" (Kontur {i + 1}–{j + 1})")
    if m["rand"]:
        i, d, _, _ = m["rand"][0]
        f.append(eintrag_text(("Kleinster Abstand Kontur–Ende", d, "mm", False)) + f" (Kontur {i + 1})")
    for stufe, text in m["befunde"]:
        f.append(f"{stufe}: {text}")
    if not m["befunde"]:
        f.append("Prüfregeln: keine Auffälligkeit (Steg, Rand, großer Ausschnitt, geschwächt, doppelt)")
    f.append("Nur Prüfung neben der Kalkulation – Schneidweg und Preis rechnen unverändert.")
    out.append(("Fertigung", f))
    return out


def klartext(gr):
    return "\n".join(f"{titel}\n" + "\n".join(f"  {z}" for z in zeilen) for titel, zeilen in gr)
