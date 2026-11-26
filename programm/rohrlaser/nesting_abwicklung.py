"""Abwicklung je Materialstange auf CAD/CAM-Niveau und 3D der echten Teile auf der Stange (Patrick 24.11.2026,
Master-Auftrag „Stangenabwicklung und realistische 3D-Darstellung“). Nur Rechnen, ohne Oberfläche.

Quelle ist ausschließlich das Nesting-Ergebnis im Format des Schnittplans (nesting_vergleich.anzeige_stangen bzw.
ergebnis['stangen']): je Teil von/bis/Länge/Drehung, dazu Endbeschnitt, Schnittfugen, Rest und Greiferrest
(stangen_ansicht.bereiche). Diese Datei rechnet keine eigenen Lagen; sie legt nur die Geometrie jedes Teils an seinen
Platz:

- Abwicklung: die exakte Außenhaut aus abwicklung.py (Mantel: echte Länge t am Umfang mit Eckradien, Seiten,
  Radiusübergänge; Schnittkanten der Enden und Konturen genau wie im 3D und im Schnittkörper). Das Teil liegt bei x =
  von … bis; seine Drehung um die Rohrachse verschiebt die Abwicklung um Drehung/360 × Umfang (bei diesen Drehungen
  bildet der Querschnitt sich auf sich selbst ab: Rundrohr jeder Winkel, Quadratrohr 90°, Rechteckrohr 180°).
- 3D: je Teil das gespeicherte STEP-Netz der Position (Rohrachse z ab Ende A) oder, ohne STEP bzw. wenn das Netz nicht
  zur Teillänge passt, das Netz aus den Eingaben (rohr3d.netz, wie im Teile-Editor). Lage = um von entlang z
  verschoben und um die Drehung um z gedreht (+Drehung = +Umfangsrichtung, wie in der Abwicklung). Endbeschnitt,
  Rest und Greiferrest als gerades Rohrstück. Nichts wird gestreckt oder angepasst: ein unpassendes STEP-Netz wird
  nicht gezeigt, der Grund steht am Teil.
"""
import math

from . import abwicklung as aw, rechnen, schneidweg as sw, skizze as sk, stangen_abwicklung as sa, wenden

PUNKTE = 96                 # Stützstellen der Schnittkanten über den Umfang
NETZ_TOLERANZ = 1.0         # mm: so weit darf die Länge des STEP-Netzes von der Teillänge abweichen (+0,5 %)


def _linie_bei(linie, t, umfang):
    """x-Wert der Schnittkante [(x, t)] (t aufsteigend 0 … Umfang) an der Stelle t (periodisch, linear)."""
    if not linie:
        return 0.0
    t = t % umfang if umfang else t
    pts = sorted(linie, key=lambda p: p[1])
    if t <= pts[0][1]:
        return pts[0][0]
    for (x0, t0), (x1, t1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return x0 + (x1 - x0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0.0)
    return pts[-1][0]


def drehung_t(mantel, drehung):
    """Verschiebung der Abwicklung durch die Drehung [°] auf der echten Außenhaut [mm, 0 … Umfang)."""
    return ((drehung or 0) % 360) / 360 * mantel.umfang


def winkel_von_t(mantel, t):
    """Umfangswinkel [°] der Stelle t (0° = Abwicklungsbeginn oben hinten, im Uhrzeigersinn von Ende A gesehen
    wie die Abwicklung: oben, vorne, unten, hinten)."""
    return (t % mantel.umfang) / mantel.umfang * 360.0 if mantel.umfang else 0.0


def seite_von_t(mantel, t):
    """Name der Rohrseite (Streifen) an der Stelle t, z. B. 'oben'."""
    t = t % mantel.umfang if mantel.umfang else t
    for name, t0, t1 in mantel.streifen():
        if t0 - 1e-9 <= t <= t1 + 1e-9:
            return name
    return ""


def teil_form(qs, e, L, mantel=None):
    """Lage des Teils ohne Platz auf der Stange (für gleiche Teile einmal gerechnet): dict(a, b, konturen) mit
    a/b = Schnittkanten [(x, t)] ab Teilanfang und konturen = [dict(kennung, art, gravur, punkte [(x, t)], zeile,
    text)] aus abwicklung.linien (exakte Außenhaut)."""
    m = mantel or aw.Mantel(qs)
    li = aw.linien(qs, e, L, m)
    a = next((x["punkte"] for x in li if x["kennung"] == "ende:a"), [(0.0, 0.0), (0.0, m.umfang)])
    b = next((x["punkte"] for x in li if x["kennung"] == "ende:b"), [(L, 0.0), (L, m.umfang)])
    konturen = []
    for x in li:
        if not x["kennung"].startswith("kontur:"):
            continue
        z = x.get("zeile")
        ein = ((e or {}).get("konturen") or [])[z] if z is not None and z < len((e or {}).get("konturen") or []) else {}
        konturen.append(dict(kennung=x["kennung"], art=x["art"], gravur=x["art"] in sw.GRAVUREN,
                             geschlossen=x["geschlossen"], punkte=x["punkte"], zeile=z,
                             text=sk.kurz(ein) if ein else str(x["art"])))
    return dict(a=a, b=b, konturen=konturen)


def gewendet_form(form, L, mantel):
    """Form eines gewendeten Teils (wenden.py: um die senkrechte Achse gewendet, Ende B vorn): x -> L − x und am Umfang
    gespiegelt um die Mitte der Seite oben (vorne <-> hinten); Ende A und B tauschen."""
    U = mantel.umfang
    oben = next(((t0 + t1) / 2 for n, t0, t1 in mantel.streifen() if n == "oben"), 0.0)

    def sp(pts):
        return [(L - x, (2 * oben - q) % U if U else q) for x, q in pts]
    return dict(a=sp(form["b"]), b=sp(form["a"]),
                konturen=[dict(k, punkte=[(L - x, 2 * oben - q) for x, q in k["punkte"]]) for k in form["konturen"]])


def teil_auf_stange(m, t, form):
    """Ein Teil an seinem Platz: dict(ref, pos, artikel, von, bis, laenge, drehung, dt, umriss [(x, t)] geschlossen
    über den ganzen Umfang, konturen [dict(..., punkte [(x, t)] auf der Stange)]), alles aus dem Nesting-Ergebnis."""
    U, von = m.umfang, float(t["von"])
    dt = drehung_t(m, t.get("drehung"))
    stellen = sorted({U * i / PUNKTE for i in range(PUNKTE + 1)}
                     | {(q + dt) % U for _, q in form["a"]} | {(q + dt) % U for _, q in form["b"]})
    # auf der Stange an der Stelle t liegt die Stelle t − dt des Teils
    oben = [(von + _linie_bei(form["a"], s - dt, U), s) for s in stellen]
    unten = [(von + _linie_bei(form["b"], s - dt, U), s) for s in reversed(stellen)]
    konturen = []
    for k in form["konturen"]:
        pts = [(von + x, q + dt) for x, q in k["punkte"]]
        mitte = (min(q for _, q in pts) + max(q for _, q in pts)) / 2
        if mitte >= U:
            pts = [(x, q - U) for x, q in pts]
        mx = (min(x for x, _ in pts) + max(x for x, _ in pts)) / 2
        mt = ((min(q for _, q in pts) + max(q for _, q in pts)) / 2) % U
        konturen.append(dict(k, punkte=pts, x=mx, t=mt, winkel=winkel_von_t(m, mt), seite=seite_von_t(m, mt)))
    return dict(ref=t.get("ref"), pos=t.get("pos"), artikel=t.get("artikel"), von=von, bis=float(t["bis"]),
                laenge=float(t["laenge"]), drehung=float(t.get("drehung") or 0), dt=dt, umriss=oben + unten,
                kante_a=oben, kante_b=list(reversed(unten)),
                konturen=konturen, index=t.get("index"))


def stange(s, positionen, profil_von, merker=None):
    """Exakte Abwicklung der Stange s: dict(laenge, umfang (echte Außenhaut), umfang_scharf, streifen [(Name, t0,
    t1)], kanten [(t, Art)] (Seitenkanten, Radiusübergänge), naht (t der Schweißnaht oder None), bereiche [(art, von,
    bis)] (end, teil, schnitt, rest, greif aus dem Schnittplan), teile [teil_auf_stange], fehlt [Pos.], profil, qs)
    oder None ohne Querschnitt. merker: dict für gleiche Teile über mehrere Stangen (Form je Position und Länge)."""
    from .stangen_bereiche import bereiche
    qs = m = profil0 = None
    teile, fehlt = [], []
    for t in s.get("teile") or ():
        p = sa.position_zum_teil(t, positionen)
        profil = profil_von(p) if p else None
        try:
            if qs is None and profil:
                qs = sk.Querschnitt(profil)
                m = aw.Mantel(qs)
                profil0 = profil
            if qs is None or qs.umfang <= 0:
                raise ValueError
            schl = ("exakt", id(p), repr(profil), t["laenge"])
            if merker is not None and schl in merker and merker[schl][0] is p:
                form = merker[schl][1]
            else:
                e = sw.aus_position(sw.lesen(p.get("technik")), p, profil)[0]
                form = teil_form(qs, e, t["laenge"], m)
                if wenden.gewendet(p):
                    form = gewendet_form(form, float(t["laenge"]), m)
                if merker is not None:
                    merker[schl] = (p, form)
            teile.append(dict(teil_auf_stange(m, t, form), gewendet=wenden.gewendet(p),
                              bezeichnung=p.get("bezeichnung") or "", position_id=p.get("id"),
                              step=bool(p.get("step_merkmale")) or "step" in str(p.get("geometrie") or "").lower()))
        except (ValueError, KeyError, TypeError, ZeroDivisionError, AttributeError, IndexError):
            fehlt.append(t.get("pos") if t.get("pos") is not None else t.get("artikel"))
    if qs is None or qs.umfang <= 0:
        return None
    lage = rechnen.stange_zeichen(s)[0]
    naht = sk.naht_s(qs, lage) if lage is not None else None
    zwischen = zwischenflaechen(teile, m.umfang, float(s.get("end") or 0),
                                _rest_anfang(s, bereiche(s)))
    return dict(zwischen=zwischen, laenge=float(s["stange"]), end=float(s.get("end") or 0),
                greif=float(s.get("greif") or 0),
                umfang=m.umfang, umfang_scharf=qs.umfang, streifen=m.streifen(), kanten=m.radius_linien(),
                naht=m.t(naht) if naht is not None else None, form=getattr(qs, "form", ""),
                bereiche=[(a, v, b) for a, v, b, _ in bereiche(s)], teile=teile, fehlt=fehlt, profil=profil0,
                radius=m.r, rest=s.get("rest") or "")


def _rest_anfang(s, b):
    """x, ab dem nach dem letzten Teil (und seinem Schnitt) Rest bzw. Greiferrest beginnt."""
    teile_ende = max((bis for a, v, bis, _ in b if a in ("teil", "schnitt")), default=float(s.get("end") or 0))
    return teile_ende


def _flaeche(poly):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))) / 2


def zwischenflaechen(teile, umfang, anfang, ende):
    """Verschnitt zwischen den Teilen (Patrick 24.11.2026): die Mantelfläche zwischen der Schnittkante B eines Teils
    und der Schnittkante A des nächsten (bei Gehrungen/Schrägschnitten die Dreiecke, sonst die Schnittfuge), dazu vor
    dem ersten Teil bis zum Endbeschnitt und nach dem letzten bis zum Rest. Ergebnis: [dict(von_teil, bis_teil,
    poly [(x, t)], flaeche [mm²], mm = Fläche / Umfang (gleichwertige Länge), x0, x1)], nur Flächen > 0,5 mm²."""
    out = []
    if not teile or umfang <= 0:
        return out
    seq = sorted(range(len(teile)), key=lambda i: teile[i]["von"])
    kanten = [([(anfang, 0.0), (anfang, umfang)], None)]
    for i in seq:
        kanten.append((teile[i]["kante_a"], i))
        kanten.append((teile[i]["kante_b"], i))
    kanten.append(([(ende, 0.0), (ende, umfang)], None))
    for k in range(0, len(kanten), 2):
        (links, li), (rechts, ri) = kanten[k], kanten[k + 1]
        poly = list(links) + list(reversed(rechts))
        f = _flaeche(poly)
        if f <= 0.5:
            continue
        xs = [x for x, _ in poly]
        out.append(dict(von_teil=li, bis_teil=ri, poly=poly, flaeche=f, mm=f / umfang, x0=min(xs), x1=max(xs),
                        links=list(links), rechts=list(rechts)))
    return out


def zwischen_netz(qs, mantel, zwischen, punkte=PUNKTE):
    """3D-Netz der Verschnittflächen zwischen den Teilen (Patrick 24.11.2026 „In 3D auch“): je Fläche das Stück
    Rohrwand zwischen den beiden Schnittkanten, außen auf der echten Außenhaut (Eckradien), innen um die Wanddicke
    nach innen, mit den Schnittflächen an beiden Kanten. Koordinaten wie die Teile auf der Stange (z längs ab
    Materialanfang, Y oben, X = −u, d. h. vorne = −X). Ergebnis dict(p, t={'VS': Dreiecke}) oder None."""
    U = mantel.umfang
    wand = float(getattr(qs, "wand", 0) or getattr(qs, "dicke", 0) or 0) or 1.0
    pk, tri = [], []

    def ort(t):
        u, v = qs.s_zu_uv(mantel.s(t % U))[0]
        n = qs.s_zu_uv(mantel.s(t % U))[1]
        ru, rv, rn = sk.rund_ort(qs, u, v)
        nu, nv = rn if rn is not None else n
        return (-ru, rv), (-(ru - wand * nu), rv - wand * nv)

    def punkt(x, uv):
        pk.extend((uv[0], uv[1], x))
        return len(pk) // 3 - 1
    for z in zwischen:
        # beide Schnittkanten einzeln (am Stangenanfang/-ende hat die gerade Kante nur 2 Punkte, die Gehrung viele)
        links, rechts = z["links"], z["rechts"]
        stellen = sorted({U * i / punkte for i in range(punkte + 1)} | {q for _, q in links} | {q for _, q in rechts})
        reihe = []
        for t in stellen:
            xa, xb = _linie_bei(links, t, U), _linie_bei(rechts, t, U)
            if xb < xa:
                xa = xb = (xa + xb) / 2
            aus, inn = ort(t)
            reihe.append((punkt(xa, aus), punkt(xb, aus), punkt(xa, inn), punkt(xb, inn), xb - xa > 1e-6))
        for (a0, b0, c0, d0, f0), (a1, b1, c1, d1, f1) in zip(reihe, reihe[1:]):
            if not (f0 or f1):
                continue
            tri += [a0, b0, b1, a0, b1, a1,         # außen
                    c0, d1, d0, c0, c1, d1,         # innen
                    a0, a1, c1, a0, c1, c0,         # Schnittfläche links
                    b0, d0, d1, b0, d1, b1]         # Schnittfläche rechts
    if not tri:
        return None
    return dict(p=pk, t={"VS": tri})


def kennzahlen(d, s):
    """Kennzahlen einer Stange aus dem Schnittplan: Teile, Verbrauch, Schnittfugen, Verschnitt, Rest, Ausnutzung."""
    from .stangen_bereiche import bereiche
    b = d["bereiche"] if d else [(a, v, bis) for a, v, bis, _ in bereiche(s)]

    def summe(art):
        return sum(bis - v for a, v, bis in b if a == art)
    teile = summe("teil")
    laenge = float(s["stange"])
    zw = d.get("zwischen") if d else None
    return dict(zwischen_mm=sum(z["mm"] for z in zw) if zw is not None else None,
                zwischen_flaeche=sum(z["flaeche"] for z in zw) if zw is not None else None,
                teile=len(s["teile"]), teile_mm=teile, schnitt_mm=summe("schnitt"), end_mm=summe("end"),
                rest_mm=summe("rest"), greif_mm=summe("greif"), ausnutzung=teile / laenge if laenge else 0.0,
                laenge=laenge)


def koordinaten(d):
    """Tabelle der technischen Ansicht: [dict(teil, art, text, x, x_bis, t, winkel, seite)] je Schnitt und Kontur,
    x ab Materialanfang [mm], t am Umfang [mm] ab Abwicklungsbeginn, Winkel [°]."""
    out = []
    if d.get("end", 0) > 0.05:      # 1. Schnitt: Besäumschnitt am Stangenanfang (Endbeschnitt)
        out.append(dict(teil="Stange", art="1. Schnitt (Besäumen)", text=f"Endbeschnitt {rechnen.zahl(d['end'], 1)} mm",
                        x=d["end"], x_bis=None, t=None, winkel=None, seite=""))
    for n, t in enumerate(d["teile"], 1):
        name = f"{n}: Pos. {t['pos']}" if t.get("pos") is not None else f"{n}: {t.get('artikel') or ''}"
        out.append(dict(teil=name, art="Schnitt Anfang", text="", x=t["von"], x_bis=None, t=None, winkel=None,
                        seite=""))
        for k in t["konturen"]:
            xs = [x for x, _ in k["punkte"]]
            out.append(dict(teil=name, art="Gravur" if k["gravur"] else "Kontur", text=k["text"], x=min(xs),
                            x_bis=max(xs), t=k["t"], winkel=k["winkel"], seite=k["seite"]))
        out.append(dict(teil=name, art="Schnitt Ende", text="", x=t["bis"], x_bis=None, t=None, winkel=None,
                        seite=""))
    return out


# ------------------------------------------------------------------------------------------------ 3D
def lage_auf_stange(von, drehung, laenge=0.0, gewendet=False):
    """Einbaulage (ansicht3d: Ursprung, z-Achse, x-Achse) eines Teils bei x = von mit Drehung [°] um die Achse;
    gewendet (Ende B vorn): danach um die senkrechte Achse gedreht (x -> −x, z -> L − z)."""
    w = math.radians(drehung or 0.0)
    c, s = math.cos(w), math.sin(w)
    if gewendet:
        return [0.0, 0.0, float(von) + float(laenge), 0.0, 0.0, -1.0, -c, s, 0.0]
    return [0.0, 0.0, float(von), 0.0, 0.0, 1.0, c, s, 0.0]


def netz_passt(netz, laenge, profil=None):
    """(True, '') wenn das STEP-Netz in Rohrlage liegt (z von 0 bis zur Teillänge), sonst (False, Grund)."""
    p = (netz or {}).get("p") or []
    if len(p) < 9:
        return False, "kein 3D-Netz"
    zs = p[2::3]
    z0, z1 = min(zs), max(zs)
    tol = NETZ_TOLERANZ + 0.005 * laenge
    if abs(z0) > tol or abs(z1 - laenge) > tol:
        return False, (f"STEP-Netz {rechnen.zahl(z1 - z0, 1)} mm statt {rechnen.zahl(laenge, 1)} mm bzw. nicht in "
                       "Rohrlage: Teil aus den Eingaben gezeigt")
    return True, ""


def _gerade(profil, laenge):
    from . import rohr3d
    try:
        return rohr3d.netz({"a": {}, "b": {}, "konturen": []}, profil, laenge)
    except (ValueError, TypeError, KeyError, ZeroDivisionError, AttributeError):
        return None


def _farbnummer(farbe_ref, ref, farbe_je):
    """Nummer der Teilfarbe (ansicht3d.TEILFARBEN) wie in der Abwicklung, sonst je Position der Reihe nach."""
    from .netz_daten import TEILFARBEN
    f = (farbe_ref or {}).get(ref)
    if f:
        f = str(f).upper()
        for n, x in enumerate(TEILFARBEN):
            if x.upper() == f:
                return n
    return farbe_je.setdefault(ref, len(farbe_je))


def _hoehe(profil):
    """Halbe Außenhöhe des Profils [mm] (für Schilder und Einpassen im 3D)."""
    try:
        q = sk.Querschnitt(profil)
        return max(float(q.H), float(q.B)) / 2
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError):
        return 20.0


def netz_stange(s, positionen, profil_von, netz_von=None, merker=None, farbe_ref=None):
    """3D-Netz der Stange: (Netz oder None, [dict(nr, ref, quelle 'STEP' | 'Eingaben' | '', hinweis)] je Teil).
    netz_von(Position) = gespeichertes STEP-Netz (Bytes oder dict) oder None. Farben: je Position eine Teilfarbe
    (Reihenfolge wie im Stangenbild), Rest/Verschnitt als eigene Art. farbe_ref = {Bezug: Farbe} aus der Abwicklung:
    dieselbe Farbe im 3D (Teilfarben ansicht3d.TEILFARBEN; info je Teil zusätzlich mitte = Punkt über dem Teil)."""
    from . import rohr3d
    from .netz_daten import baugruppe, entpacken
    from .stangen_bereiche import bereiche
    merker = merker if merker is not None else {}
    netze, farben, info, reste = [], [], [], []
    farbe_je = {}
    profil0 = None
    for t in s.get("teile") or ():
        p = sa.position_zum_teil(t, positionen)
        profil = profil_von(p) if p else None
        profil0 = profil0 or profil
        quelle, hinweis, n = "", "", None
        if p is not None and profil:
            roh = None
            if netz_von is not None:
                schl = ("step", p.get("id"))
                if schl not in merker:
                    try:
                        roh = netz_von(p)
                        merker[schl] = roh if isinstance(roh, dict) or roh is None else entpacken(bytes(roh))
                    except Exception:       # noqa: BLE001 – kaputtes Netz: aus den Eingaben zeigen
                        merker[schl] = None
                roh = merker[schl]
            if roh:
                ok, hinweis = netz_passt(roh, float(t["laenge"]), profil)
                if ok:
                    n, quelle = {k: v for k, v in roh.items() if k not in ("lage", "lagen")}, "STEP"
            if n is None:
                schl = ("eingaben", id(p), repr(profil), t["laenge"])
                if schl not in merker:
                    try:
                        e = sw.aus_position(sw.lesen(p.get("technik")), p, profil)[0]
                        merker[schl] = rohr3d.netz(e, profil, float(t["laenge"]))
                    except (ValueError, TypeError, KeyError, ZeroDivisionError, AttributeError, IndexError):
                        merker[schl] = None
                n = merker[schl]
                quelle = "Eingaben" if n else ""
                if not n:
                    hinweis = hinweis or "kein 3D-Modell"
        if n:
            n = dict(n, lage=lage_auf_stange(t["von"], t.get("drehung"), t["laenge"], wenden.gewendet(p)))
            farben.append(_farbnummer(farbe_ref, t.get("ref"), farbe_je))
            netze.append(n)
        hoehe = _hoehe(profil)
        info.append(dict(nr=len(info) + 1, ref=t.get("ref"), quelle=quelle, hinweis=hinweis, pos=t.get("pos"),
                         mitte=(0.0, hoehe, (float(t["von"]) + float(t["bis"])) / 2),
                         ecken=[(sx * hoehe, sy * hoehe, float(z)) for z in (t["von"], t["bis"]) for sx in (-1, 1)
                                for sy in (-1, 1)]))
    if profil0:
        for art, von, bis, _ in bereiche(s):
            if art in ("end", "rest", "greif") and bis - von > 0.5:
                n = _gerade(profil0, bis - von)
                if n:
                    reste.append(len(netze))
                    netze.append(dict(n, lage=lage_auf_stange(von, 0)))
                    farben.append(0)
    if not netze:
        return None, info
    netz, _ = baugruppe(netze, farben=farben, normteile=tuple(reste))
    if netz and "NT" in netz.get("t", {}):
        netz["t"]["RS"] = netz["t"].pop("NT")         # Reststücke/Endbeschnitt/Greiferrest eigene Farbe
    if netz and profil0:                            # Verschnitt zwischen den Teilen als eigene Art (rot)
        try:
            d = stange(s, positionen, profil_von, merker)
            qs = sk.Querschnitt(profil0)
            vs = zwischen_netz(qs, aw.Mantel(qs), d["zwischen"]) if d and d.get("zwischen") else None
        except (ValueError, TypeError, KeyError, ZeroDivisionError, AttributeError, IndexError):
            vs = None
        if vs:
            basis = len(netz["p"]) // 3
            netz["p"] = list(netz["p"]) + vs["p"]
            netz["t"]["VS"] = [basis + i for i in vs["t"]["VS"]]
    return netz, info


# ------------------------------------------------------------------------------------------------ DXF der Stange
def dxf_elemente(d):
    """Elemente für dxf.schreiben (Layer wie die Rohrabwicklung, abwicklung.ROHR_LAYER): x längs ab Materialanfang,
    y = Umfang − t. Je Teil der Umriss (außen), Konturen (innen) bzw. Gravuren, Seitenkanten/Radiusübergänge,
    Stangenrand und Bereichsgrenzen, Beschriftung (Pos., Länge, Bereiche, Kopfzeile)."""
    from . import dxf
    U, L = d["umfang"], d["laenge"]

    def p(x, t):
        return (round(x, 4), round(U - t, 4))

    def zug(layer, pts, zu=False):
        z = list(pts) + (list(pts[:1]) if zu else [])
        return [("LINE", layer, p(*a), p(*b)) for a, b in zip(z, z[1:]) if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1e-6]
    elem = zug(dxf.TEXT, [(0, 0), (L, 0), (L, U), (0, U)], True)
    for art, von, bis in d["bereiche"]:
        if art != "teil":
            elem += zug(dxf.TEXT, [(von, 0), (von, U)]) + zug(dxf.TEXT, [(bis, 0), (bis, U)])
            elem.append(("TEXT", dxf.TEXT, p(von, -4), 3.0,
                         f"{ {'end': 'Endbeschnitt', 'rest': 'Rest', 'greif': 'Greiferrest', 'schnitt': 'Fuge'}.get(art, art)} "
                         f"{rechnen.zahl(bis - von, 1)}"))
            if art == "end" and bis > 0.05:
                elem.append(("TEXT", dxf.TEXT, p(bis, -9), 3.0, f"1. Schnitt Besäumen x {rechnen.zahl(bis, 1)}"))
    for t_, art in d["kanten"]:
        if t_ > 1e-6:
            elem += zug(dxf.HOCH if art == "kante" else dxf.RUNTER, [(0, t_), (L, t_)])
    for n, t in enumerate(d["teile"], 1):
        elem += zug(dxf.AUSSEN, t["umriss"], True)
        for k in t["konturen"]:
            for stueck in sa.kontur_teile(k["punkte"], U):
                stueck = [(x, min(max(q, 0.0), U)) for x, q in stueck]
                elem += zug(dxf.GRAVUR if k["gravur"] else dxf.INNEN, stueck, k["geschlossen"] and not k["gravur"])
        elem.append(("TEXT", dxf.TEXT, p((t["von"] + t["bis"]) / 2 - 20, U / 2), 4.0,
                     f"{n}: Pos. {t.get('pos')} {rechnen.zahl(t['laenge'], 1)}"))
    elem.append(("TEXT", dxf.TEXT, p(0, U + 10), 4.0,
                 f"Stange {rechnen.zahl(L, 0)} mm, Umfang Außenhaut {rechnen.zahl(U, 1)} mm, {len(d['teile'])} Teile"))
    return elem
