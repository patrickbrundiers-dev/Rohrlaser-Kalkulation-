"""Schnittkörper im 3D (Patrick 25.10.2026, Freigabe „A b b a a“): jede Kontur zusätzlich als halb durchsichtiger
Körper, so tief wie sie schneidet – das Volumen, das der Laser herausnimmt.

Die Körper ragen außen und innen je 2 mm über die Wand (UEBERSTAND, UEBERSTAND_INNEN).

- eine Wand: von der Außenwand durch die Wandstärke (schräge Bohrung entlang ihrer Neigung, Schnitt parallel zur
  Konturachse parallel zur Mitte, sonst senkrecht zur Wand bzw. zur Rohrachse)
- beide Wände (durchgehend): ein Körper durch das ganze Profil bis zur Gegenwand (die Kopie dort bekommt keinen
  eigenen)
- alle Seiten / am Umfang verteilt: je Kopie ein Körper durch ihre Wand
- Gravur mit Umriss: so tief wie angegeben (sonst 0,1 mm)
- Blech: durch die Blechdicke

Farbe je Konturart (ARTEN), die Tiefe steht im Text (Tooltip beim Überfahren). Gezeichnet werden die Körper von
ansicht3d (QPainter und OpenGL), abschaltbar mit „Schnittkörper“ (Vorgabe an, je Benutzer gemerkt).

Netz-Eintrag 'wk': [dict(id = Merkmal 'kontur:3', art = Farbe (ARTEN), o = Ring außen [x, y, z, …], u = Ring innen
(gleich viele Punkte), d = Deckel als Dreiecke [i, j, k, …] über die Nummern im Ring, t = Text, auf = True, wenn
die Fläche dort nicht ausgeschnitten ist (Gravur, Flowdrill, Blech))].
"""
import math

from . import skizze as sk
from .schneidweg import (AUSKLINKUNG, BOHRUNG, DURCHBRUCH, FLOWDRILL, GRAVUR, GRAVUREN, LANGLOCH, LOCHFELD, POLYGON,
                         RECHTECK, SCHLITZ, SENKUNG, SONDERKONTUR, SONSTIGE, V_AUSSCHNITT, _z)

# Farbe je Konturart, in allen 3D-Fenstern gleich (Patrick 25.10.2026): Schlüssel = Art in ansicht3d.ARTEN
# Unbekannte Konturen (Sonderkontur, Sonstige) eigene Farbe "WU", Form wie in der STEP-Datei (aus_step); V-Ausschnitte
# der Knickrahmen eigene Farbe "WV" (Patrick 25.10.2026)
FARBE_ART = {BOHRUNG: "WB", SENKUNG: "WB", FLOWDRILL: "WB", LOCHFELD: "WB", LANGLOCH: "WL", SCHLITZ: "WL",
             RECHTECK: "WR", POLYGON: "WR", DURCHBRUCH: "WR", AUSKLINKUNG: "WA", GRAVUR: "WG", SONDERKONTUR: "WU",
             SONSTIGE: "WU", V_AUSSCHNITT: "WV"}
UNBEKANNT = (SONDERKONTUR, SONSTIGE)
STEP_NAH = 8.0          # STEP-Kontur gehört zur Zeile, wenn ihre Mitte so nah an der Hülle der Zeile liegt [mm]
UEBERSTAND = 2.0        # Körper ragen außen so weit über die Wand hinaus [mm] (Patrick: außen etwas überstehen)
UEBERSTAND_INNEN = 2.0  # innen ebenso (Patrick: je 2 mm)
GRAVUR_TIEFE = 0.1      # Gravur ohne Tiefe [mm]
MAX_KOERPER = 400       # mehr Konturen (Lochfelder, Belastungstest): keine Körper, sonst wird das 3D zäh
SCHRITT = 3.0           # Umriss so dicht [mm] (auf dem Rundrohr folgt der Körper der Krümmung)


def _zahl(w, stellen=1):
    from .rechnen import zahl
    return zahl(w, stellen)


def _deckel(pts):
    """Deckelfläche des Rings (Ohrenschneiden über die Nummern): [i, j, k, …]."""
    n = len(pts)
    if n < 3:
        return []
    flaeche = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    idx = list(range(n)) if flaeche > 0 else list(range(n))[::-1]

    def links(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def drin(p, a, b, c):
        return links(a, b, p) > 1e-9 and links(b, c, p) > 1e-9 and links(c, a, p) > 1e-9
    out, schutz = [], 0
    while len(idx) > 3 and schutz < 4 * n * n:
        schutz += 1
        m = len(idx)
        for k in range(m):
            i, j, l_ = idx[k - 1], idx[k], idx[(k + 1) % m]
            a, b, c = pts[i], pts[j], pts[l_]
            if links(a, b, c) <= 1e-9:
                continue
            if any(drin(pts[q], a, b, c) for q in idx if q not in (i, j, l_)):
                continue
            out += [i, j, l_]
            del idx[k]
            break
        else:
            break                       # kein Ohr (Umriss schneidet sich): Rest als Fächer
    for q in range(1, len(idx) - 1):
        out += [idx[0], idx[q], idx[q + 1]]
    return out


def _ring(pts):
    """Geschlossenen Linienzug ohne doppelten Schlusspunkt."""
    pts = list(pts)
    while len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-9:
        pts.pop()
    return pts


def tiefe_text(ein, qs, d=None, wand=None):
    """Wie tief die Kontur schneidet, als Text: „1 Wand · 3 mm“, „durch 2 Wände · 60 mm“ …"""
    art = ein.get("art")
    t = wand if wand is not None else (qs.wand if qs is not None else 0.0)
    if art in GRAVUREN:
        return f"Gravur {_zahl(_z(ein.get('tiefe')) or GRAVUR_TIEFE, 2)} mm tief"
    w = ein.get("wand") or ""
    if w == "beide" and d is not None:
        text = f"durch 2 Wände · {_zahl(d)} mm"
    elif w == "alle":
        text = f"alle 4 Seiten, je 1 Wand · {_zahl(t)} mm"
    elif w == "umfang":
        text = f"{int(_z(ein.get('umfang_n')))}× am Umfang, je 1 Wand · {_zahl(t)} mm"
    else:
        text = f"1 Wand · {_zahl(t)} mm"
    neig = sk.neigung_3d(ein) if art == BOHRUNG else None
    if neig and (neig[0] or neig[1]):
        text += f" · Neigung längs {_zahl(neig[0])}°, quer {_zahl(neig[1])}°"
    elif ein.get("schnitt") == "parallel" and qs is not None and qs.r:
        text += " · parallel zur Konturachse"
    return text


def rohr(e, qs, L, xyz):
    """Schnittkörper der Konturen eines Rohrs/Profils (Eingaben e, Querschnitt qs, Länge L); xyz(x, u, v) = Punkt im
    Netz (rohr3d._xyz). Liste für netz['wk'] (leer bei zu vielen Konturen)."""
    lagen = sk.lagen(e.get("konturen") or [], L, qs)
    if len(lagen) > MAX_KOERPER:
        return []
    t_wand = qs.wand or 0.0
    if not t_wand and qs.flaechen:      # Vollmaterial / offene Profile ohne Wandangabe: Dicke wie im Querschnitt
        t_wand = min(qs.B, qs.H) / 10
    d3 = e.get("d3") is True
    out = []
    for d in lagen:
        ein = d["eingabe"]
        art = ein.get("art")
        farbe = FARBE_ART.get(art)
        if farbe is None or (art in UNBEKANNT + (GRAVUR,) and not ein.get("umriss")):
            continue
        beide = ein.get("wand") == "beide"
        if beide and d.get("kopie"):
            continue                    # durchgehend: der Körper der Kontur geht schon durch beide Wände
        pts = sk.umriss_kontur(ein)
        if not pts or len(pts) < 3:
            continue
        pts = _ring(pts)
        if qs.r or (ein.get("umriss") and qs.flaechen):
            pts = _ring(sk._dicht(pts + pts[:1], 1.0 if qs.radius and ein.get("umriss") else SCHRITT))
        try:
            orte, n_mitte = sk.platzieren(qs, d, pts)
        except (ValueError, TypeError, ZeroDivisionError, AttributeError):
            continue
        if len(orte) != len(pts):
            continue
        nm = (float(n_mitte[0]), float(n_mitte[1]))
        # Richtung nach innen je Punkt: Rundrohr zur Rohrachse, Fläche senkrecht, über mehrere Flächen je Fläche
        if qs.r:
            richt = [(-u / (math.hypot(u, v) or 1.0), -v / (math.hypot(u, v) or 1.0), 0.0) for _, u, v in orte]
        elif ein.get("umriss") and qs.flaechen:
            richt = []
            for _, dq in pts:
                nu, nv = qs.s_zu_uv(sk.s_lage(qs, ein, dq) % qs.umfang)[1]
                richt.append((-nu, -nv, 0.0))
        else:
            richt = [(-nm[0], -nm[1], 0.0)] * len(orte)
        if qs.radius and not qs.r and not ein.get("wand") == "beide":   # Eckradius: auf dem Bogen wie im STEP
            neu_o, neu_r = [], []
            for (x, u, v), rr in zip(orte, richt):
                u, v, n_ = sk.rund_ort(qs, u, v)
                neu_o.append((x, u, v))
                neu_r.append((-n_[0], -n_[1], 0.0) if n_ else rr)
            orte, richt = neu_o, neu_r
        neig = sk.neigung_3d(ein) if art == BOHRUNG and d3 else None
        tief = t_wand
        if art in GRAVUREN:
            tief = _z(ein.get("tiefe")) or GRAVUR_TIEFE
        if neig and (neig[0] or neig[1]):
            # schräge Bohrung: Achse gekippt (längs + = Richtung Ende B, quer + = im Uhrzeigersinn von Ende A)
            tl, tq = math.tan(math.radians(neig[0])), math.tan(math.radians(neig[1]))
            r = (-nm[0] + tq * nm[1], -nm[1] - tq * nm[0], tl)
            lg = math.sqrt(r[0] ** 2 + r[1] ** 2 + r[2] ** 2)
            richt = [(r[0] / lg, r[1] / lg, r[2] / lg)] * len(orte)
            tief = t_wand * lg          # durch die Wand gemessen entlang der Achse
        elif qs.r and ein.get("schnitt") == "parallel" and d3:
            richt = [(-nm[0], -nm[1], 0.0)] * len(orte)
        durch = None
        if beide:                       # bis zur Gegenwand: Abstand je Punkt zur gespiegelten Wand
            richt = [(-nm[0], -nm[1], 0.0)] * len(orte)
            tiefen = [2 * (u * nm[0] + v * nm[1]) for _, u, v in orte]
            durch = max(tiefen) if tiefen else 0.0
        else:
            tiefen = [tief] * len(orte)
        # über mehrere Wände (Sonderkontur, V-Ausschnitt): ohne Deckel, eine ebene Fläche ginge quer durchs Profil
        deckel = _deckel(pts) if len(set(richt)) == 1 or qs.r else []
        o, u_ = [], []
        for (x, u, v), (ru, rv, rx), tf in zip(orte, richt, tiefen):
            a = (x - rx * UEBERSTAND, u - ru * UEBERSTAND, v - rv * UEBERSTAND)
            b = (x + rx * (tf + UEBERSTAND_INNEN), u + ru * (tf + UEBERSTAND_INNEN), v + rv * (tf + UEBERSTAND_INNEN))
            o += [round(c, 3) for c in xyz(*a)]
            u_ += [round(c, 3) for c in xyz(*b)]
        name = sk.kurz(ein)
        if art == V_AUSSCHNITT:
            name = f"V-Ausschnitt β {_zahl(_z(ein.get('beta')) or 90)}° (Knickrahmen)"
            text = f"{name}\nSeitenwände und Gegenwand, je 1 Wand · {_zahl(t_wand)} mm"
        elif art in UNBEKANNT:
            text = f"{name}\nunbekannte Kontur, Umriss aus den Eingaben · je 1 Wand · {_zahl(t_wand)} mm"
        else:
            text = f"{name}\n{tiefe_text(ein, qs, durch, t_wand)}"
        k = dict(id=f"kontur:{d['zeile']}", art=farbe, o=o, u=u_, d=deckel, t=text)
        if art in GRAVUREN or art == FLOWDRILL:
            k["auf"] = True             # Wand dort nicht ausgeschnitten: Körper liegt auf der Fläche
        out.append(k)
    return out


def blech(e, zs, haut, ansicht, dicke):
    """Schnittkörper der Innenkonturen eines Blechs: durch die Dicke (haut(q, seite) = (Punkt, Normale) der Haut
    oben/unten, ansicht = Achsen der 3D-Ansicht, blech3d). Liste für netz['wk']."""
    from . import blech3d
    zuege = blech3d.konturzuege(e, zs)
    if len(zuege) > MAX_KOERPER:
        return []
    zeile = {id(z): i for i, z in enumerate(e.get("konturen") or [])}
    from . import blech as bl
    arten = (BOHRUNG, SENKUNG) + tuple(bl.DREH_ARTEN)
    s = max(dicke, 0.1)
    seite = 1.0 + 2 * UEBERSTAND / s        # haut: Abstand s/2 × seite von der Mitte; beide Seiten außen
    out = []
    for z, zug in zuege:
        if z.get("art") not in arten or z.get("linien"):
            continue
        pts = _ring(zug)
        if len(pts) < 3:
            continue
        o, u = [], []
        for q in pts:
            o += [round(c, 3) for c in ansicht(haut(q, seite)[0])]
            u += [round(c, 3) for c in ansicht(haut(q, -seite)[0])]
        text = f"{sk.kurz(z)}\ndurch das Blech · {_zahl(s)} mm"
        out.append(dict(id=f"kontur:{zeile.get(id(z))}", art=FARBE_ART.get(z.get("art"), "WR"), o=o, u=u,
                        d=_deckel(pts), t=text, auf=True))      # Blech: Haut bleibt geschlossen
    return out


def verschieben(koerper, dz):
    """Körper längs der Rohrachse verschieben (baugruppe_ansicht.rohr_netz: Nasen an Ende A)."""
    for k in koerper or ():
        for p in [k.get("o") or [], k.get("u") or [], k.get("dr") or []] + list(k.get("li") or ()):
            for i in range(2, len(p), 3):
                p[i] = round(p[i] + dz, 3)


def in_lage(koerper, lage):
    """Körper in die Einbaulage (Ursprung, z-Achse, x-Achse) einer Baugruppe (ansicht3d.baugruppe)."""
    o, z, x = lage[0:3], lage[3:6], lage[6:9]
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])

    def lege(p):
        aus = []
        for i in range(0, len(p) - 2, 3):
            a, b, c = p[i], p[i + 1], p[i + 2]
            aus += [round(o[k] + a * x[k] + b * y[k] + c * z[k], 3) for k in range(3)]
        return aus
    return [dict(k, o=lege(k.get("o") or []), u=lege(k.get("u") or []), dr=lege(k.get("dr") or []),
                 li=[lege(z) for z in k.get("li") or ()]) for k in koerper or ()]



def _gruppen(dreiecke, schl):
    """Dreiecke [(a, b, c)] in zusammenhängende Gruppen (gemeinsame Ecken) teilen: [[Nummern]]."""
    eltern = list(range(len(dreiecke)))

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i
    ecke = {}
    for nr, d in enumerate(dreiecke):
        for q in d:
            k = schl(q)
            if k in ecke:
                a, b = wurzel(nr), wurzel(ecke[k])
                if a != b:
                    eltern[a] = b
            else:
                ecke[k] = nr
    out = {}
    for nr in range(len(dreiecke)):
        out.setdefault(wurzel(nr), []).append(nr)
    return list(out.values())


def aus_step(wk, netz_step, e, qs, L, xyz):
    """Unbekannte Konturen (Sonderkontur, Sonstige) so wie in der STEP-Datei (Patrick 25.10.2026): die Schnittflächen
    der Kontur aus dem Netz des STEP-Imports (Art K, gleiche Lage wie das Modell aus den Eingaben) werden ihr
    Schnittkörper, Farbe "WU". Zugeordnet wird jede zusammenhängende Kontur der STEP-Datei der nächsten Konturzeile;
    nur die der unbekannten Zeilen werden übernommen (ersetzen deren Körper aus dem Umriss). wk: Liste aus rohr(),
    Ergebnis die neue Liste."""
    wk = list(wk or ())
    if not netz_step or not netz_step.get("p"):
        return wk
    zeilen = e.get("konturen") or []
    if not any((z or {}).get("art") in UNBEKANNT for z in zeilen):
        return wk
    p = netz_step["p"]
    idx = (netz_step.get("t") or {}).get("K") or []
    tris = [tuple(tuple(p[3 * i:3 * i + 3]) for i in idx[n:n + 3]) for n in range(0, len(idx) - 2, 3)]
    if not tris:
        return wk
    gruppen = _gruppen(tris, lambda q: (round(q[0], 2), round(q[1], 2), round(q[2], 2)))
    # Mitte und halbe Hülle je Konturzeile (alle Stück und Kopien)
    ziele = []
    for d in sk.lagen(zeilen, L, qs):
        try:
            (orte, _), pts = sk.platzieren(qs, d), sk.umriss_kontur(d["eingabe"]) or [(0.0, 0.0)]
        except (ValueError, TypeError, ZeroDivisionError, AttributeError):
            continue
        m = [sum(xyz(*q)[i] for q in orte) / len(orte) for i in range(3)]
        halb = max((math.hypot(dx, dq) for dx, dq in pts), default=0.0)
        ziele.append((m, halb, d))
    if not ziele:
        return wk
    linien = []
    for zug in (netz_step.get("l") or {}).get("K") or []:
        pk = [tuple(zug[i:i + 3]) for i in range(0, len(zug) - 2, 3)]
        if len(pk) >= 2:
            linien.append((pk, [sum(q[i] for q in pk) / len(pk) for i in range(3)]))
    neu = {}
    for g in gruppen:
        pk = [q for nr in g for q in tris[nr]]
        mitte = [(min(q[i] for q in pk) + max(q[i] for q in pk)) / 2 for i in range(3)]
        m, halb, d = min(ziele, key=lambda z: math.dist(z[0], mitte) - z[1])
        if math.dist(m, mitte) > halb + STEP_NAH or d["eingabe"].get("art") not in UNBEKANNT:
            continue
        k = neu.setdefault(d["zeile"], dict(id=f"kontur:{d['zeile']}", art="WU", o=[], u=[], d=[], dr=[], li=[], auf=True,
                                            t=f"{sk.kurz(d['eingabe'])}\nunbekannte Kontur, Form wie in der "
                                              f"STEP-Datei · Wand {_zahl(qs.wand or 0)} mm"))
        k["dr"] += [round(c, 3) for nr in g for q in tris[nr] for c in q]
        rand = (min(q[0] for q in pk) - 1, max(q[0] for q in pk) + 1, min(q[1] for q in pk) - 1,
                max(q[1] for q in pk) + 1, min(q[2] for q in pk) - 1, max(q[2] for q in pk) + 1)
        for zug, c in linien:
            if rand[0] <= c[0] <= rand[1] and rand[2] <= c[1] <= rand[3] and rand[4] <= c[2] <= rand[5]:
                k["li"].append([round(v, 3) for q in zug for v in q])
    if not neu:
        return wk
    ersetzt = {k["id"] for k in neu.values()}
    return [k for k in wk if k["id"] not in ersetzt] + list(neu.values())
