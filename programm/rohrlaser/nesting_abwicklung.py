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
                konturen=konturen, index=t.get("index"))


def stange(s, positionen, profil_von, merker=None):
    """Exakte Abwicklung der Stange s: dict(laenge, umfang (echte Außenhaut), umfang_scharf, streifen [(Name, t0,
    t1)], kanten [(t, Art)] (Seitenkanten, Radiusübergänge), naht (t der Schweißnaht oder None), bereiche [(art, von,
    bis)] (end, teil, schnitt, rest, greif aus dem Schnittplan), teile [teil_auf_stange], fehlt [Pos.], profil, qs)
    oder None ohne Querschnitt. merker: dict für gleiche Teile über mehrere Stangen (Form je Position und Länge)."""
    from .stangen_ansicht import bereiche
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
    return dict(laenge=float(s["stange"]), end=float(s.get("end") or 0), greif=float(s.get("greif") or 0),
                umfang=m.umfang, umfang_scharf=qs.umfang, streifen=m.streifen(), kanten=m.radius_linien(),
                naht=m.t(naht) if naht is not None else None, form=getattr(qs, "form", ""),
                bereiche=[(a, v, b) for a, v, b, _ in bereiche(s)], teile=teile, fehlt=fehlt, profil=profil0,
                radius=m.r, rest=s.get("rest") or "")


def kennzahlen(d, s):
    """Kennzahlen einer Stange aus dem Schnittplan: Teile, Verbrauch, Schnittfugen, Verschnitt, Rest, Ausnutzung."""
    from .stangen_ansicht import bereiche
    b = d["bereiche"] if d else [(a, v, bis) for a, v, bis, _ in bereiche(s)]

    def summe(art):
        return sum(bis - v for a, v, bis in b if a == art)
    teile = summe("teil")
    laenge = float(s["stange"])
    return dict(teile=len(s["teile"]), teile_mm=teile, schnitt_mm=summe("schnitt"), end_mm=summe("end"),
                rest_mm=summe("rest"), greif_mm=summe("greif"), ausnutzung=teile / laenge if laenge else 0.0,
                laenge=laenge)


def koordinaten(d):
    """Tabelle der technischen Ansicht: [dict(teil, art, text, x, x_bis, t, winkel, seite)] je Schnitt und Kontur,
    x ab Materialanfang [mm], t am Umfang [mm] ab Abwicklungsbeginn, Winkel [°]."""
    out = []
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


def netz_stange(s, positionen, profil_von, netz_von=None, merker=None):
    """3D-Netz der Stange: (Netz oder None, [dict(nr, ref, quelle 'STEP' | 'Eingaben' | '', hinweis)] je Teil).
    netz_von(Position) = gespeichertes STEP-Netz (Bytes oder dict) oder None. Farben: je Position eine Teilfarbe
    (Reihenfolge wie im Stangenbild), Rest/Verschnitt als eigene Art."""
    from . import rohr3d
    from .ansicht3d import baugruppe, entpacken
    from .stangen_ansicht import bereiche
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
            farben.append(farbe_je.setdefault(t.get("ref"), len(farbe_je)))
            netze.append(n)
        info.append(dict(nr=len(info) + 1, ref=t.get("ref"), quelle=quelle, hinweis=hinweis))
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
    return netz, info
