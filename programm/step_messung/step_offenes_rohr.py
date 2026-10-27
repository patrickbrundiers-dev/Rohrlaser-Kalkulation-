"""Offene Rohre aus dem Rohr lasern (Patrick 25.10.2026, Freigabe „Alle a“, danach „Nur vielleicht 2 mm die Fläche
schließen nicht komplett“, „Je ein Steg 2 mm an beiden Enden“, „die Rohre auch Außenradius etc haben … an der
importierten Datei nichts ändern, errechnen welches nächstgrößere Rohr es ist“): Kunden zeichnen Quadrat- oder
Rechteckrohre oft als gekantetes Blech mit einer offenen Seite (U offen, C mit Längsschlitz, U mit einer Lasche) und
Rundrohre als Halbschale. Gefertigt wird das Teil auf dem Rohrlaser aus dem geschlossenen Rohr: an Ende A und Ende B
bleibt je ein Ring STEG (2 mm) des ganzen Rohrs stehen (Querschnitt des nächstgrößeren Normrohrs, step_normrohre, mit
Außenradius nach EN 10219), dazwischen wird die offene Seite als Fenster ausgeschnitten (Innenkontur im Schneidweg).
Ein schmaler Spalt bis SPALT_MAX (2 mm) wird ganz geschlossen (ein Fenster wäre dort sinnlos). Die Datei selbst bleibt
unverändert.

Erkennung (Kastenrohr): gleich dicke Wände, Querschnitt mit einer Kontur in einem Hüllrechteck, drei Seiten mit
Material belegt, eine Seite über die ganze Länge offen (an allen Messlagen mit vollem Querschnitt dieselbe Lücke;
Lagen, an denen die Seitenwände ausgeschnitten sind, zählen nicht). Öffnungen, die nicht über die ganze Länge gehen,
sind Ausschnitte und bleiben (Frage 3 a); Laschen und Schlitzränder bleiben stehen, das Fenster liegt genau über der
Lücke (Frage 4 a). Die Enden der Ringe und der Wand folgen den Nachbarwänden (Frage 2 a): Verlauf der
gegenüberliegenden Wand, quer dazu die Steigung der Seitenwände, damit wird ein gerades Ende gerade und eine Gehrung
eine Gehrung.

Der Körper mit Ringen wird wie jedes Rohr gemessen (Querschnitt aus dem geschlossenen Rohr, Konturen der vorhandenen
Wände bleiben, das Fenster ist eine Innenkontur). Ergebnis: Teil als Quadrat-/Rechteck-/Rundrohr mit offene_seite
(Seite, Lücken, Länge, Steg) in t.geschlossen der offenen Messung; deren Netz zeigt die Ringe bzw. den geschlossenen
Spalt als Art „EO“ (im Programm rot „EW“, sobald das Teil als Rohr gilt). Ob das Rohr vorgeschlagen wird, entscheidet
das Programm (nur, wenn es das Rohr in den Stammdaten gibt, Frage 1 a, step.offene_rohre_vorbelegen)."""
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_SOLID
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Trsf

import math

import step_geometrie as g
import step_normrohre

HINWEIS = "Offenes Rohr"
KANDIDATEN = ("U-Profil", "C-Profil", "offenes Sonderprofil", "Blech gekantet")
ROHRE = ("Quadratrohr", "Rechteckrohr")
LAGEN = 9               # Messlagen über die Länge (10 … 90 %)
SCHRITT = 0.25          # mm, Abtastung entlang einer Seite
LUECKE_INNEN = 0.5      # mm, kleinste Lücke mitten in einer Seite (Schlitz)
TOL_WAND = 0.15         # mm, Wandstärke des geschlossenen Rohrs gegen die Blechdicke
TOL_HUELLE = 0.2        # mm, Hüllrechteck an allen Lagen gleich
SPALT_MAX = 2.0         # mm, breitester Spalt, der ganz geschlossen wird (sonst Stege und Fenster)
STEG = 2.0              # mm, Steg über der offenen Seite an Ende A und Ende B (Patrick 25.10.2026)
SPALT_TOL = 0.05        # mm, Messtoleranz auf SPALT_MAX


def _dicke(t):
    if t.bauteiltyp == "Blech gekantet":
        return float((t.blech or {}).get("dicke") or 0.0)
    if t.normprofil or t.sicherheit.get("wandstaerke") == "unsicher" or \
            any(h.startswith("Wandstärken verschieden") for h in t.hinweise):
        return 0.0              # Walzprofil (UPN) oder ungleich dicke Wände: kein gekantetes Rohr
    return t.wandstaerke


def _luecken(strecken, seite, x0, y0, x1, y1, d):
    """Lücken der Seite auf der Mittellinie der Wand (d/2 innen): Liste (von, bis) entlang der Seite."""
    if seite in ("unten", "oben"):
        a, b = x0, x1
        v = y0 + d / 2 if seite == "unten" else y1 - d / 2
        punkt = lambda u: (u, v)    # noqa: E731
    else:
        a, b = y0, y1
        v = x0 + d / 2 if seite == "links" else x1 - d / 2
        punkt = lambda u: (v, u)    # noqa: E731
    n = max(2, int((b - a) / SCHRITT))
    def frei(u):
        return not g._im_material(*punkt(u), strecken)

    def kante(u_frei, u_voll):
        for _ in range(14):         # Rand der Lücke auf etwa 0,02 µm genau (Halbierung)
            m = (u_frei + u_voll) / 2
            u_frei, u_voll = (m, u_voll) if frei(m) else (u_frei, m)
        return (u_frei + u_voll) / 2
    out, start, vorher = [], None, None
    for k in range(n + 1):
        u = a + 0.01 + (b - a - 0.02) * k / n       # nicht genau auf der Hülle (Punkt auf dem Rand: unbestimmt)
        f = frei(u)
        if f and start is None:
            start = a if vorher is None else kante(u, vorher)
        elif not f and start is not None:
            out.append((start, kante(vorher, u)))
            start = None
        vorher = u
    if start is not None:
        out.append((start, b))
    return out, a, b


def _offen(luecken, a, b, d):
    """Lücken, die die Seite öffnen: mitten in der Seite ab LUECKE_INNEN, am Rand (Ecke) erst ab der Größe, die eine
    Biegerundung nicht erreicht (4 × Dicke, mindestens 15 % der Seite)."""
    rand = max(4 * d, 0.15 * (b - a))
    return [(u0, u1) for u0, u1 in luecken
            if (u1 - u0 >= rand) or (u0 > a + SCHRITT and u1 < b - SCHRITT and u1 - u0 >= LUECKE_INNEN)]


def erkennen(solid, d):
    """Offene Seite des Körpers: dict(ax3, seite, luecken [(von, bis)], huelle (x0, y0, x1, y1), z (zmin, zmax)) im
    lokalen System (Z = Achse) oder None."""
    ax3, _ = g._lage(solid)
    lok = g._transformiere(solid, ax3)
    zmin, zmax = g._z_bereich(lok)
    if zmax - zmin < 3 * d:
        return None
    lagen = []
    for k in range(LAGEN):
        z = zmin + (zmax - zmin) * (0.1 + 0.8 * k / (LAGEN - 1)) + 0.0137
        ws = g._schnitt(lok, z)
        if len(ws) != 1:          # Schnitt durch einen Ausschnitt (zerfallen) oder ein Hohlprofil
            continue
        st = g._strecken(ws[0][1])
        xs, ys = [s[0] for s in st] + [s[2] for s in st], [s[1] for s in st] + [s[3] for s in st]
        lagen.append((st, (min(xs), min(ys), max(xs), max(ys))))
    if not lagen:
        return None
    # Hüllrechteck: das größte; Lagen mit kleinerem Querschnitt (Seitenwand dort ausgeschnitten, wie Patricks Beispiel
    # mit Laschen) zählen nicht, solange sie darin liegen; ein größerer oder versetzter Querschnitt: kein gerades Rohr
    huelle = max((h for _, h in lagen), key=lambda h: (h[2] - h[0]) * (h[3] - h[1]))
    offen_je_lage = []
    for st, h in lagen:
        if h[0] < huelle[0] - TOL_HUELLE or h[1] < huelle[1] - TOL_HUELLE or h[2] > huelle[2] + TOL_HUELLE or \
                h[3] > huelle[3] + TOL_HUELLE:
            return None
        if max(abs(p - q) for p, q in zip(h, huelle)) > TOL_HUELLE:
            continue
        offen = {}
        for seite in ("links", "rechts", "unten", "oben"):
            lu, a, b = _luecken(st, seite, *h, d)
            o = _offen(lu, a, b, d)
            if o:
                offen[seite] = o
        offen_je_lage.append(offen)
    if len(offen_je_lage) < 3 or huelle is None:
        return None
    x0, y0, x1, y1 = huelle
    if min(x1 - x0, y1 - y0) < 3 * d:
        return None                 # flaches Teil, kein Rohr
    # über die ganze Länge offen: an jeder Lage; genau eine solche Seite (sonst L-Profil o. ä.)
    immer = [s for s in ("links", "rechts", "unten", "oben") if all(s in o for o in offen_je_lage)]
    if len(immer) != 1:
        return None
    seite = immer[0]
    # Lücken der Seite: Vereinigung über die Lagen (Laschen, die nur an einer Lage fehlen, sind Ausschnitte; die
    # Lücke selbst ist an allen Lagen gleich)
    luecken = []
    for u0, u1 in sorted(x for o in offen_je_lage for x in o[seite]):
        if luecken and u0 <= luecken[-1][1] + SCHRITT:
            luecken[-1] = (luecken[-1][0], max(luecken[-1][1], u1))
        else:
            luecken.append((u0, u1))
    return dict(ax3=ax3, lok=lok, seite=seite, luecken=luecken, huelle=huelle, z=(zmin, zmax))


def _z_grenzen(lok, x, y):
    """Material entlang der Linie (x, y) parallel zur Achse: (kleinstes z, größtes z) oder None."""
    s = IntCurvesFace_ShapeIntersector()
    s.Load(lok, 1e-6)
    s.Perform(gp_Lin(gp_Pnt(x, y, -1e6), gp_Dir(0, 0, 1)), -1e7, 1e7)
    if not s.IsDone() or s.NbPnt() < 2:
        return None
    zs = [s.Pnt(i).Z() for i in range(1, s.NbPnt() + 1)]
    return min(zs), max(zs)


def _profil_z(lok, uv_zu_xyz, us, v):
    """Enden (z Ende A, z Ende B) des Materials entlang Linien parallel zur Achse an den Stellen u (bei v); Lücken
    (Bohrung, Rundung) linear aus den Nachbarn ergänzt. None, wenn keine Stelle Material hat."""
    werte = []
    for u in us:
        x, y, _ = uv_zu_xyz(u, v, 0.0)
        werte.append(_z_grenzen(lok, x, y))
    da = [i for i, w in enumerate(werte) if w is not None]
    if not da:
        return None
    out = []
    for i, w in enumerate(werte):
        if w is None:
            li = max((k for k in da if k < i), default=None)
            re = min((k for k in da if k > i), default=None)
            if li is None or re is None:      # am Rand: aus den zwei nächsten Stellen verlängert
                k1, k2 = (da[-2:] if re is None else da[:2]) if len(da) > 1 else (da[0], da[0])
                s = 0.0 if k1 == k2 else (us[i] - us[k1]) / (us[k2] - us[k1])
                w = tuple(werte[k1][k] + (werte[k2][k] - werte[k1][k]) * s for k in range(2))
            else:
                s = (i - li) / (re - li)
                w = tuple(werte[li][k] * (1 - s) + werte[re][k] * s for k in range(2))
        out.append(w)
    return out


def _seite_z(lok, uv_zu_xyz, u, v, mitte):
    """Enden (z A, z B) der Seitenwand bei u in der Höhe v. Liegt dort kein Material (Rundung an der Ecke), aus den
    zwei nächsten Stellen Richtung mitte linear verlängert. None, wenn nicht messbar."""
    schritt = math.copysign(0.5, mitte - v)
    treffer = []
    w = v
    while (mitte - w) * schritt > 0 and len(treffer) < 2:
        zg = _profil_z(lok, uv_zu_xyz, [u], w)
        if zg:
            if w == v:
                return zg[0]
            treffer.append((w, zg[0]))
            w += 4 * schritt          # zweite Stelle mit Abstand (Steigung)
            continue
        w += schritt
    if len(treffer) < 2:
        return treffer[0][1] if treffer else None
    (wa, za), (wb, zb) = treffer
    return tuple(za[k] + (zb[k] - za[k]) * (v - wa) / (wb - wa) for k in range(2))


def _knicke(pts):
    """Polygonzug [(u, z)] aus gleichmäßigen Stellen: liegt ein Knick (Schnitt nur über einen Teil der Breite)
    zwischen zwei Stellen, wird der Schnittpunkt der beiden Nachbargeraden eingefügt (sonst eine kleine Fase)."""
    out = list(pts[:2])
    for i in range(2, len(pts) - 1):      # Knick zwischen pts[i-1] und pts[i]
        (ua, za), (ub, zb), (uc, zc), (ud, zd) = pts[i - 2], pts[i - 1], pts[i], pts[i + 1]
        m1, m2 = (zb - za) / (ub - ua), (zd - zc) / (ud - uc)
        mitte = (zc - zb) / (uc - ub)
        if abs(m1 - m2) > 1e-3 and abs(mitte - m1) > 1e-3 and abs(mitte - m2) > 1e-3:
            u = (zc - zb + m1 * ub - m2 * uc) / (m1 - m2)
            if ub < u < uc:
                out.append((u, zb + m1 * (u - ub)))
        out.append(pts[i])
    return out + [pts[-1]] if len(pts) > 3 else list(pts)


def _rahmen(e, d):
    """Lage der offenen Seite im lokalen System: (lok, quer, uv_zu_xyz, a, b (Seite von, bis), v_aussen, innen
    (Richtung nach innen, ±1), v_lo, v_hi (Wandschicht), v_gm (Mitte der gegenüberliegenden Wand), versatz)."""
    x0, y0, x1, y1 = e["huelle"]
    seite, lok = e["seite"], e["lok"]
    quer = seite in ("unten", "oben")
    if quer:
        v_aussen, v_gegen = (y0, y1) if seite == "unten" else (y1, y0)
        a, b = x0, x1
        uv_zu_xyz = lambda u, v, z: (u, v, z)       # noqa: E731
    else:
        v_aussen, v_gegen = (x0, x1) if seite == "links" else (x1, x0)
        a, b = y0, y1
        uv_zu_xyz = lambda u, v, z: (v, u, z)       # noqa: E731
    innen = 1.0 if v_gegen > v_aussen else -1.0
    v_innen = v_aussen + innen * d
    v_lo, v_hi = min(v_aussen, v_innen), max(v_aussen, v_innen)
    v_gm = v_gegen - innen * d / 2                   # Mitte der gegenüberliegenden Wand
    # Versatz der Enden quer zur Wand: Seitenwand links/rechts in Höhe der neuen Wand gegen die Höhe der
    # gegenüberliegenden Wand (gerades Ende: 0, Gehrung quer: Steigung, Schnitt nur über einen Teil: der Knick)
    mitte = (v_aussen + v_gegen) / 2
    versatz = {}
    for u_s in (a + d / 2, b - d / 2):
        z_g = _seite_z(lok, uv_zu_xyz, u_s, v_gm, mitte)
        for v in (v_lo, v_hi):
            z_v = _seite_z(lok, uv_zu_xyz, u_s, min(max(v, v_lo + 0.05), v_hi - 0.05), mitte)
            versatz[u_s, v] = (0.0, 0.0) if z_g is None or z_v is None else (z_v[0] - z_g[0], z_v[1] - z_g[1])
    return lok, quer, uv_zu_xyz, a, b, v_aussen, innen, v_lo, v_hi, v_gm, versatz


def ring(e, d, steg, anzeige=False):
    """Je ein Ring des ganzen Rohrquerschnitts (Patrick 25.10.2026: „die Rohre auch Außenradius etc haben … nicht nur
    einen Steg dazwischen“) an Ende A und B, steg mm breit, als Körper im lokalen System, und die Außenhaut des Rohrs
    über die ganze Länge (für die Messung des Querschnitts); None bei Fehler.
    Querschnitt: Rohr in der Hülle des Teils bzw. das nächstgrößere Normrohr darum (Patrick: „errechnen welches
    nächstgrößere Rohr es ist und dann darauf die Stege anpassen“), Außenradius nach EN 10219 (2 × Wand bis 6 mm, 2,5 × bis 10 mm, darüber
    3 × Wand; wie optimierung.aussenradius), innen Außenradius − Wand. Der Ring folgt den Enden wie die Wand (wand):
    Verlauf der gegenüberliegenden Wand, quer dazu die Steigung der Seitenwände, über die ganze Hülle verlängert."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    lok, quer, uv_zu_xyz, a, b, v_aussen, innen, v_lo, v_hi, v_gm, versatz = _rahmen(e, d)
    if "rohr_masse" in e:           # schon bestimmt (Anzeige nach der Messung)
        x0, y0, x1, y1 = e["rohr_masse"]
        ra = e["ra"]
    else:
        x0, y0, x1, y1 = e["huelle"]
        # nächstgrößeres Normrohr (step_normrohre) als Profil; gemessen wird in der Hülle des Teils (die Wände liegen
        # auf dem Rohr, bis ABWEICHUNG Unterschied; die Enden rechnet das Programm für das Profil nach). Datei
        # unverändert
        norm = step_normrohre.naechstes_kasten(x1 - x0, y1 - y0)
        if norm:
            na, nb = (norm[1], norm[2]) if x1 - x0 >= y1 - y0 else (norm[2], norm[1])
            if max(na - (x1 - x0), nb - (y1 - y0)) > step_normrohre.ABWEICHUNG:
                norm = None     # Teil deutlich kleiner als das Normrohr: Sondermaß = Hülle (Wände passen sonst nicht)
        e["norm"] = norm
        # Radius aus der STEP (Patrick 25.10.2026: „den Radius aus der STEP übernehmen, nicht dass verschiedene Radien
        # am Rohr sind“), an allen vier Ecken gleich; ohne Biegeradius in der Zeichnung nach EN 10219
        ra = eckradius(lok, d) or (2 * d if d <= 6 else 2.5 * d if d <= 10 else 3 * d)
        ra = min(ra, min(x1 - x0, y1 - y0) / 2)
        # nichts fällt weg (Patrick: „ab dem Punkt, wo das Rohr aufhört, weg zum nächstmöglichen Radiusanfang beim
        # nächstmöglichen größeren Rohr“): ragt das Teil über das Rohr (scharf gezeichnete Schenkelenden an den
        # Rohrecken), wird das Rohr quer zur offenen Seite so weit größer, bis der Radius erst nach den Enden beginnt
        if _ueberstand(lok, (x0, y0, x1, y1), ra, e) > 0.5:
            groesser = _groesseres_rohr(lok, e, (x0, y0, x1, y1), ra, d)
            if groesser:
                (x0, y0, x1, y1), e["norm"] = groesser
                e["vergroessert"] = True
        e["ra"], e["rohr_masse"] = ra, (x0, y0, x1, y1)
    profil = _rundrechteck(x0, y0, x1, y1, ra, e["z"][0] - 1, e["z"][1] - e["z"][0] + 2)
    if not anzeige and profil is not None:
        # was dann noch aus dem Rohr ragt (kein größeres Rohr gefunden), als Fläche je mm
        e["ueberstand"] = _ueberstand(lok, (x0, y0, x1, y1), ra, e)
        # das ganze Rohr über die Länge (Messung des Querschnitts, wenn das Rohr größer ist als das Teil)
        e["rohr"] = _bool("minus", profil, _rundrechteck(x0 + d, y0 + d, x1 - d, y1 - d, max(ra - d, 0.0),
                                                         e["z"][0] - 2, e["z"][1] - e["z"][0] + 4))
    # innen Radius außen − Wand; für die Messung an den zwei Ecken der offenen Seite scharf wie die ergänzte Wand
    # (sonst ragte der Ring dort in das Fenster und verbände dessen Schnitt mit den Enden; Unterschied im Schneidweg
    # unter 1 mm), für die Anzeige und im größeren Rohr (Querschnitt = ganzes Rohr) wie das Rohr an allen Ecken gleich
    ri = max(ra - d, 0.0)
    offen = () if anzeige or e.get("vergroessert") else {"unten": (0, 3), "rechts": (0, 1), "oben": (1, 2), "links": (2, 3)}[e["seite"]]
    profil = _bool("minus", profil, _rundrechteck(x0 + d, y0 + d, x1 - d, y1 - d,
                                                  tuple(0.0 if k in offen else ri for k in range(4)), e["z"][0] - 2,
                                                  e["z"][1] - e["z"][0] + 4)) if profil else None
    if profil is None:
        return None
    w0, w1 = a - 1.0, b + 1.0
    n = max(8, min(240, int((w1 - w0) / 0.5)))
    us = [w0 + (w1 - w0) * k / n for k in range(n + 1)]
    gegen = _profil_z(lok, uv_zu_xyz, us, v_gm)
    if gegen is None:
        return None
    v_weit = v_aussen + innen * (abs(x1 - x0 if not quer else y1 - y0) + 1.0)   # über die gegenüberliegende Wand
    ringe = []
    for k, richtung in ((0, 1.0), (1, -1.0)):
        ende = _knicke([(u, z[k]) for u, z in zip(us, gegen)])
        drahte = []
        for v in (v_aussen - innen * (1.0 + _wachs(e, x0, y0, x1, y1)), v_weit):
            # Versatz quer zur Wand: in der Wandschicht gemessen, linear über die Hülle verlängert
            def vs(u_s):
                lo, hi = versatz[u_s, v_lo][k], versatz[u_s, v_hi][k]
                return lo + (hi - lo) * (v - v_lo) / (v_hi - v_lo)
            va, vb = vs(a + d / 2), vs(b - d / 2)
            linie = [(u, z + va * (1 - (u - a) / (b - a)) + vb * (u - a) / (b - a)) for u, z in ende]
            poly = BRepBuilderAPI_MakePolygon()
            for u, z in linie + [(u, z + richtung * steg) for u, z in linie[::-1]]:
                poly.Add(gp_Pnt(*uv_zu_xyz(u, v, z)))
            poly.Close()
            drahte.append(poly.Wire())
        ts = BRepOffsetAPI_ThruSections(True, True)
        for w in drahte:
            ts.AddWire(w)
        ts.Build()
        if not ts.IsDone():
            return None
        r = _bool("und", profil, ts.Shape())
        if r is None:
            return None
        ringe.append(r)
    # für die Messung des Querschnitts nur eine dünne Außenhaut des Rohrs über die ganze Länge: sie bringt ein größeres
    # Normrohr in die Hülle, lässt die Innenkontur aber wie gezeichnet (sonst zählten die Innenwände als Schnitt)
    haut = _bool("minus", _rundrechteck(x0, y0, x1, y1, ra, e["z"][0] - 1, e["z"][1] - e["z"][0] + 2),
                 _rundrechteck(x0 + d / 2, y0 + d / 2, x1 - d / 2, y1 - d / 2, max(ra - d / 2, 0.0), e["z"][0] - 2,
                               e["z"][1] - e["z"][0] + 4))
    return (ringe, haut) if haut is not None else None


def _ueberstand(lok, masse, ra, e, d=None):
    """Was vom Teil (lokales System) über das Rohr mit den Außenmaßen masse (x0, y0, x1, y1) und Radius ra ragt
    (mit Wand d: was nicht in der Rohrwand liegt): Fläche im Querschnitt [mm²] (Volumen ÷ Länge); das Stück selbst in
    e['rest']."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    x0, y0, x1, y1 = masse
    aussen = _rundrechteck(x0, y0, x1, y1, ra, e["z"][0] - 1, e["z"][1] - e["z"][0] + 2)
    if aussen is not None and d:
        aussen = _bool("minus", aussen, _rundrechteck(x0 + d, y0 + d, x1 - d, y1 - d, max(ra - d, 0.0),
                                                      e["z"][0] - 2, e["z"][1] - e["z"][0] + 4))
    rest = _bool("minus", lok, aussen) if aussen is not None else None
    e["rest"] = rest
    if rest is None:
        return 0.0
    gp = GProp_GProps()
    BRepGProp.VolumeProperties_s(rest, gp)
    return gp.Mass() / max(e["z"][1] - e["z"][0], 1.0)


def _wachs(e, x0, y0, x1, y1):
    """Um so viel ist das Rohr quer zur offenen Seite größer als die Hülle des Teils (0 = nicht vergrößert)."""
    hx0, hy0, hx1, hy1 = e["huelle"]
    return max(0.0, (y1 - y0) - (hy1 - hy0)) if e["seite"] in ("oben", "unten") else max(0.0, (x1 - x0) - (hx1 - hx0))


def _groesseres_rohr(lok, e, masse, ra, d):
    """Nächstgrößeres Rohr, in dessen Wänden das Teil ganz liegt: Breite der offenen Seite bleibt (die Seitenwände
    bleiben auf dem Rohr), das Maß quer dazu wächst auf der offenen Seite – erst die Normreihe, sonst Sondermaß (Hülle
    + Radius). Liegt dann etwas nicht in der Wand (z. B. eine Lasche der offenen Seite), gibt es kein solches Rohr.
    Ergebnis ((x0, y0, x1, y1), Norm (Form, A, B) oder None) oder None."""
    x0, y0, x1, y1 = masse
    quer = e["seite"] in ("oben", "unten")
    fest, alt = (x1 - x0, y1 - y0) if quer else (y1 - y0, x1 - x0)
    passt = lambda f_: fest - step_normrohre.TOL <= f_ <= fest + step_normrohre.ABWEICHUNG     # noqa: E731
    kandidaten = sorted({(s_, ("Quadratrohr", s_, s_)) for s_ in step_normrohre.QUADRAT
                         if passt(s_) and s_ > alt + 0.05} |
                        {(h, ("Rechteckrohr", a_, b_)) for a_, b_ in step_normrohre.RECHTECK
                         for f_, h in ((a_, b_), (b_, a_)) if passt(f_) and h > alt + 0.05})
    sonder = math.ceil(alt + ra)
    for h, norm in [k for k in kandidaten if k[0] <= sonder + 20] + [(sonder, None)]:
        neu = {"oben": (x0, y0, x1, y0 + h), "unten": (x0, y1 - h, x1, y1), "rechts": (x0, y0, x0 + h, y1),
               "links": (x1 - h, y0, x1, y1)}[e["seite"]]
        if _ueberstand(lok, neu, ra, e) <= 0.5:
            return (neu, norm) if _ueberstand(lok, neu, ra, e, d) <= 0.5 else None
    return None


def eckradius(lok, d):
    """Außenradius der Rohrecken aus der Zeichnung: größter Zylinder längs der Achse (z), zu dem es den Innenradius
    (außen − Wand) gibt; sonst der größte Radius über der Wand; None ohne Biegeradius (scharf gezeichnet)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    radien = set()
    for f in g._liste(lok, TopAbs_FACE):
        s = BRepAdaptor_Surface(TopoDS.Face(f))
        if s.GetType() == GeomAbs_Cylinder and abs(abs(s.Cylinder().Axis().Direction().Z()) - 1) < 1e-4:
            radien.add(round(s.Cylinder().Radius(), 3))
    paare = [r for r in radien if r > d and any(abs(r - d - q) < 0.1 for q in radien)]
    if paare:
        return max(paare)
    ueber = [r for r in radien if r > d * 0.5]
    return max(ueber) if ueber else None


def _rundrechteck(x0, y0, x1, y1, r, z, h):
    """Prisma über dem Rechteck mit Eckradius r (Zahl oder je Ecke rechts unten, rechts oben, links oben, links unten),
    von z über die Höhe h (lokales System)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.gp import gp_Vec
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return None
    rs = [max(0.0, min(r_, (x1 - x0) / 2 - 1e-6, (y1 - y0) / 2 - 1e-6))
          for r_ in (r if isinstance(r, (tuple, list)) else (r,) * 4)]
    ecken = ((x1, y0, -1, 1, -90), (x1, y1, -1, -1, 0), (x0, y1, 1, -1, 90), (x0, y0, 1, 1, 180))
    stuecke = []        # je Ecke Anfang, (Mitte), Ende des Bogens bzw. nur der Eckpunkt
    for (x, y, sx, sy, w0), r_ in zip(ecken, rs):
        if r_ < 1e-6:
            stuecke.append([gp_Pnt(x, y, z)])
        else:
            mx, my = x + sx * r_, y + sy * r_
            stuecke.append([gp_Pnt(mx + r_ * math.cos(math.radians(t_)), my + r_ * math.sin(math.radians(t_)), z)
                            for t_ in (w0, w0 + 45, w0 + 90)])
    w = BRepBuilderAPI_MakeWire()
    for i, p in enumerate(stuecke):
        if len(p) == 3:
            w.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(*p).Value()).Edge())
        w.Add(BRepBuilderAPI_MakeEdge(p[-1], stuecke[(i + 1) % 4][0]).Edge())
    f = BRepBuilderAPI_MakeFace(w.Wire()).Face()
    return BRepPrimAPI_MakePrism(f, gp_Vec(0, 0, h)).Shape()


def wand(e, d, ueberlapp=True, fenster=0.0):
    """Ergänzte Wand je Lücke als Körper im lokalen System: (Körper, Lückenbereiche, quer, Schichten = je Körper die
    Endlinien (Ende A, Ende B) außen und innen); ueberlapp: die Wand reicht um die Blechdicke in die Ränder (zum
    Verschmelzen), sonst genau die Lücke (3D-Ansicht).
    Enden (Frage 2 a): Verlauf der gegenüberliegenden Wand (z je u), quer dazu die Steigung der Seitenwände (z je v,
    zwischen linker und rechter Seitenwand gemittelt). Ein gerades Ende bleibt gerade, eine Gehrung oder ein Schnitt
    nur über einen Teil der Breite wird übernommen.
    fenster > 0: statt der Wand das Fenster zwischen den Stegen (je fenster mm an Ende A und B), genau über der Lücke
    und nach außen und innen etwas über die Wand hinaus (zum Ausschneiden aus dem geschlossenen Rohr)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    lok, quer, uv_zu_xyz, a, b, v_aussen, innen, v_lo, v_hi, v_gm, versatz = _rahmen(e, d)
    teile, felder, schichten = [], [], []
    for u0, u1 in e["luecken"]:
        w0, w1 = (max(a, u0 - d), min(b, u1 + d)) if ueberlapp and not fenster else (u0, u1)   # überlappt: verschmolzen
        n = max(8, min(240, int((w1 - w0) / 0.5)))
        us = [w0 + (w1 - w0) * k / n for k in range(n + 1)]
        gegen = _profil_z(lok, uv_zu_xyz, us, v_gm)
        if gegen is None:
            return None
        enden = [_knicke([(u, z[k]) for u, z in zip(us, gegen)]) for k in (0, 1)]
        drahte, schicht = [], []
        for v in (v_lo, v_hi):
            va, vb = versatz[a + d / 2, v], versatz[b - d / 2, v]
            vf = v if not fenster else v - innen * 1.0 if v == v_aussen else v + innen * 0.5   # Fenster: über die Wand
            unten = [uv_zu_xyz(u, vf, z + fenster + va[0] * (1 - (u - a) / (b - a)) + vb[0] * (u - a) / (b - a))
                     for u, z in enden[0]]
            oben = [uv_zu_xyz(u, vf, z - fenster + va[1] * (1 - (u - a) / (b - a)) + vb[1] * (u - a) / (b - a))
                    for u, z in enden[1]]
            schicht.append((unten, oben))
            poly = BRepBuilderAPI_MakePolygon()
            for q in unten + oben[::-1]:
                poly.Add(gp_Pnt(*q))
            poly.Close()
            drahte.append(poly.Wire())
        ts = BRepOffsetAPI_ThruSections(True, True)
        for w in drahte:
            ts.AddWire(w)
        ts.Build()
        if not ts.IsDone():
            return None
        teile.append(ts.Shape())
        felder.append((u0, u1))
        schichten.append(schicht)
    return teile, felder, quer, schichten


def _vereinen(solid, teile, ax3, einheitlich=True):
    """Körper ∪ ergänzte Wände (in Dateilage); None, wenn nicht genau ein Körper entsteht."""
    tr = gp_Trsf()
    tr.SetTransformation(ax3)
    zurueck = tr.Inverted()
    form = solid
    for k in teile:
        f = BRepAlgoAPI_Fuse(form, BRepBuilderAPI_Transform(k, zurueck, True).Shape())
        f.SetFuzzyValue(g.FUZZY)
        f.Build()
        if not f.IsDone():
            return None
        form = f.Shape()
    koerper = g._liste(form, TopAbs_SOLID)
    if len(koerper) != 1:
        return None
    if not einheitlich:
        return koerper[0]
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    try:
        u = ShapeUpgrade_UnifySameDomain(koerper[0], True, True, True)
        u.Build()
        return u.Shape()
    except Exception:       # OpenCascade kann nicht vereinheitlichen: Körper wie verschmolzen
        return koerper[0]


def _ausschneiden(form, teile, ax3):
    """Fenster (Körper im lokalen System) aus dem geschlossenen Rohr (Dateilage) schneiden; None bei Fehler. Ohne
    Vereinheitlichen der Flächen: die Fensterränder liegen in der Ebene der Seitenwände innen und sollen eigene
    Schnittflächen bleiben."""
    tr = gp_Trsf()
    tr.SetTransformation(ax3)
    zurueck = tr.Inverted()
    for k in teile:
        c = BRepAlgoAPI_Cut(form, BRepBuilderAPI_Transform(k, zurueck, True).Shape())
        c.SetFuzzyValue(g.FUZZY)
        c.Build()
        if not c.IsDone():
            return None
        form = c.Shape()
    return form if len(g._liste(form, TopAbs_SOLID)) == 1 else None


def _gitter(schicht, quer, laenge):
    """Dreiecke der Wand aus ihren Endlinien: Raster über u (Stützstellen beider Enden) und z (etwa alle 20 mm),
    damit die Dreiecke klein und gleichmäßig sind (die 3D-Ansicht ohne OpenGL sortiert nach Tiefe). Ergebnis:
    Punkte [(x, y, z)] und Dreiecke [(i, j, k)], nach außen gedreht."""
    k_u = 0 if quer else 1

    def an(linie, u):
        for p, q in zip(linie, linie[1:]):
            if p[k_u] - 1e-9 <= u <= q[k_u] + 1e-9:
                s = 0.0 if q[k_u] == p[k_u] else (u - p[k_u]) / (q[k_u] - p[k_u])
                return [p[m] + (q[m] - p[m]) * s for m in range(3)]
        return list(linie[0] if u < linie[0][k_u] else linie[-1])
    us = sorted({round(p[k_u], 6) for unten, oben in schicht for p in unten + oben})
    n = max(1, int(laenge / 20.0))
    punkte, gitter = [], []
    for unten, oben in schicht:          # außen, innen: Gitter je Schicht
        g_ = []
        for u in us:
            a, b = an(unten, u), an(oben, u)
            g_.append([len(punkte) + j for j in range(n + 1)])
            punkte += [[a[m] + (b[m] - a[m]) * j / n for m in range(3)] for j in range(n + 1)]
        gitter.append(g_)
    dreiecke = []

    def viereck(a, b, c, d_):
        dreiecke.extend([(a, b, c), (a, c, d_)])
    for g_ in gitter:                                       # Wandflächen
        for i in range(len(us) - 1):
            for j in range(n):
                viereck(g_[i][j], g_[i + 1][j], g_[i + 1][j + 1], g_[i][j + 1])
    g0, g1 = gitter
    for i in range(len(us) - 1):                            # Enden A und B
        viereck(g0[i][0], g0[i + 1][0], g1[i + 1][0], g1[i][0])
        viereck(g0[i][n], g0[i + 1][n], g1[i + 1][n], g1[i][n])
    # die Ränder an den Lückenkanten fehlen mit Absicht: dort liegt die Wand des Teils (gleiche Ebene)
    mitte = [sum(p[m] for p in punkte) / len(punkte) for m in range(3)]
    out = []
    for a, b, c in dreiecke:                                # nach außen drehen (Wand ist flach und konvex)
        pa, pb, pc = punkte[a], punkte[b], punkte[c]
        u_ = [pb[m] - pa[m] for m in range(3)]
        v_ = [pc[m] - pa[m] for m in range(3)]
        nv = (u_[1] * v_[2] - u_[2] * v_[1], u_[2] * v_[0] - u_[0] * v_[2], u_[0] * v_[1] - u_[1] * v_[0])
        if sum(abs(x) for x in nv) < 1e-12:
            continue
        sp = [(pa[m] + pb[m] + pc[m]) / 3 - mitte[m] for m in range(3)]
        out.append((a, b, c) if sum(nv[m] * sp[m] for m in range(3)) >= 0 else (a, c, b))
    return punkte, out


def _verfeinern(netz, max_kante=25.0):
    """Lange Dreiecke des Netzes an der längsten Kante teilen, bis keine Kante länger als max_kante ist (gemeinsame
    Kantenmitten, das Netz bleibt geschlossen). Die 3D-Ansicht ohne OpenGL sortiert Dreiecke nach der Tiefe ihrer
    Mitte; lange Dreiecke der Seitenwände lägen sonst teils vor der ergänzten Wand."""
    p = netz["p"]
    mitten = {}

    def mitte(a, b):
        k = (min(a, b), max(a, b))
        if k not in mitten:
            mitten[k] = len(p) // 3
            p.extend(round((p[3 * a + m] + p[3 * b + m]) / 2, 2) for m in range(3))
        return mitten[k]

    def laenge2(a, b):
        return sum((p[3 * a + m] - p[3 * b + m]) ** 2 for m in range(3))
    grenze = max_kante * max_kante
    for art, idx in netz["t"].items():
        offen = [tuple(idx[j:j + 3]) for j in range(0, len(idx), 3)]
        fertig = []
        while offen:
            a, b, c = offen.pop()
            kanten = [(laenge2(a, b), 0), (laenge2(b, c), 1), (laenge2(c, a), 2)]
            l2, k = max(kanten)
            if l2 <= grenze or len(fertig) + len(offen) > 20000:
                fertig.append((a, b, c))
                continue
            x, y, z = ((a, b, c), (b, c, a), (c, a, b))[k]          # längste Kante x–y
            q = mitte(x, y)
            offen += [(x, q, z), (q, y, z)]
        netz["t"][art] = [i for tri in fertig for i in tri]


def _stege(schicht, steg):
    """Endlinien der Stege an Ende A und B aus den Endlinien der Wand (je Schicht außen/innen um steg nach innen)."""
    def verschoben(linie, dz):
        return [(p[0], p[1], p[2] + dz) for p in linie]
    return ([(unten, verschoben(unten, steg)) for unten, _ in schicht],
            [(verschoben(oben, -steg), oben) for _, oben in schicht])


def _netz_wand(t, e, d, steg=0.0):
    """Die ergänzte Wand (genau die Lücken; mit steg nur die Stege an den Enden) als Dreiecke der Art EO im Netz der
    offenen Messung (System wie das Netz: Ende A, Achse, X-Richtung der Messung)."""
    w = wand(e, d, ueberlapp=False)
    if not w or t.netz is None or not t.achse_global:
        return
    zu_datei, zu_netz = gp_Trsf(), gp_Trsf()
    zu_datei.SetTransformation(e["ax3"])
    zu_netz.SetTransformation(g._rohr_ax3(t))
    tr = zu_netz.Multiplied(zu_datei.Inverted())
    schichten = [(s_, e["z"][1] - e["z"][0]) for s_ in w[3]] if not steg else \
        [(s_, steg) for schicht in w[3] for s_ in _stege(schicht, steg)]
    for schicht, laenge in schichten:
        punkte, dreiecke = _gitter(schicht, w[2], laenge)
        p = []
        for x, y, z in punkte:
            q = gp_Pnt(x, y, z).Transformed(tr)
            p += [round(q.X(), 2), round(q.Y(), 2), round(q.Z(), 2)]
        g._netz_anhaengen(t.netz, dict(p=p, t={"EO": [i for tri in dreiecke for i in tri]}, l={}))
    _verfeinern(t.netz, max(10.0, (e["z"][1] - e["z"][0]) / 20))


def schliessen(solid, t, datei="", koerper=1, netz=False):
    """Offen gezeichnetes Rohr: t.geschlossen = Messung als Quadrat-/Rechteckrohr mit Stegen an den Enden und Fenster
    (Spalt bis SPALT_MAX: ganz geschlossen), im Netz von t die Stege bzw. die Wand als Art EO. False, wenn t nicht
    offen bzw. nicht schließbar ist."""
    if t is None or t.biegerohr or t.knick_schenkel or t.trennung or \
            (t.profilform if t.bauteiltyp != "Blech gekantet" else "Blech gekantet") not in KANDIDATEN:
        return False
    if t.bauteiltyp == "Blech gekantet" and ((t.blech or {}).get("abwicklung") or {}).get("mehrachsig"):
        return False
    return _kasten_schliessen(solid, t, datei, koerper, netz) or _rund_schliessen(solid, t, datei, koerper, netz)


def _kasten_schliessen(solid, t, datei, koerper, netz):
    """Quadrat-/Rechteckrohr (siehe schliessen)."""
    d = _dicke(t)
    if d <= 0:
        return False
    e = erkennen(solid, d)
    if e is None:
        return False
    w = wand(e, d)
    if w is None:
        return False
    teile, felder, quer = w[:3]
    voll = _vereinen(solid, teile, e["ax3"])
    if voll is None:
        return False
    breite, laenge = sum(u1 - u0 for u0, u1 in felder), e["z"][1] - e["z"][0]
    steg = 0.0 if all(u1 - u0 <= SPALT_MAX + SPALT_TOL for u0, u1 in felder) or laenge < 4 * STEG else STEG
    zu, ringe, ringe_step = voll, None, False
    if steg:
        # Ringe des ganzen Rohrquerschnitts an den Enden, dazwischen über der Lücke das Fenster ausgeschnitten
        rg = ring(e, d, steg)
        ringe = rg[0] if rg else None
        f = wand(e, d, fenster=steg)
        quer_k = _vereinen(voll, [rg[1]], e["ax3"], False) if rg else None
        # Regel (Patrick 25.10.2026): das Teil liegt immer im Querschnitt des ganzen Rohrs – was darüber ragt (z. B.
        # scharf gezeichnete Schenkelenden an den Rohrecken), fällt weg (Anzeige UW, Hinweis). Gemessen wird wie
        # gezeichnet: abgeschnitten wäre die Schnittfläche des Fensters an den Schenkeln nicht mehr von der Innenwand
        # zu unterscheiden; der Schneidweg ändert sich dadurch um weniger als 1 mm je Ecke
        if e.get("vergroessert") and ringe and e.get("rohr") is not None:
            # größeres Rohr: das Teil liegt darin, gefertigt wird Teil + Ringe; die Schnitte des Fensters laufen an den
            # Schenkelenden (eigene Flächen), der Querschnitt ist das ganze Rohr
            zu = _vereinen(solid, ringe, e["ax3"], False)
            quer_k = _vereinen(solid, [e["rohr"]], e["ax3"], False)
        elif ringe and _ringe_im_teil(e, d):
            zu, ringe_step = solid, True    # Ringe stehen schon in der STEP: Fenster genau wie gezeichnet
        else:
            mit_ringen = _vereinen(_vereinen(solid, teile, e["ax3"]), ringe, e["ax3"], False) if ringe and f else None
            zu = _ausschneiden(mit_ringen, f[0], e["ax3"]) if mit_ringen is not None else None
        if zu is None or quer_k is None:
            return False
    r = g._profil_messen(zu, datei, koerper, False, quer=quer_k if steg else None)
    if r.profilform not in ROHRE or abs(r.wandstaerke - d) > TOL_WAND:
        return False
    r.bauteiltyp = "Profil"
    ecke = e["huelle"][0] if quer else e["huelle"][1]
    r.offene_seite = dict(seite=e["seite"], luecken=[[round(u0 - ecke, 2), round(u1 - ecke, 2)] for u0, u1 in felder],
                          breite=round(breite, 2), laenge=round(laenge, 2), vorher=t.profilform, steg=steg or None)
    r.sicherheit["offene_seite"] = "stege" if steg else "ergänzt"
    if ringe_step:
        r.offene_seite["ringe_step"] = True
        r.hinweise.append(f"{HINWEIS}: Enden in der STEP geschlossen, Ausschnitt ({breite:.1f} mm breit) als "
                          f"Innenkontur wie gezeichnet (vorher {t.profilform}) – Profil prüfen")
    elif steg:
        r.hinweise.append(f"{HINWEIS}: aus dem Rohr gelasert, offene Seite ({breite:.1f} mm breit) bis auf je einen "
                          f"Ring {steg:g} mm an Ende A und B ausgeschnitten (vorher {t.profilform}) – Profil prüfen")
    else:
        r.hinweise.append(f"{HINWEIS}: Spalt {breite:.1f} mm über {laenge:.1f} mm Länge geschlossen (vorher "
                          f"{t.profilform}) – Profil prüfen")
    if steg:
        r.offene_seite["radius"] = round(e["ra"], 2)
    if steg and e.get("vergroessert"):
        x0, y0, x1, y1 = e["rohr_masse"]
        r.offene_seite["vergroessert"] = round(_wachs(e, x0, y0, x1, y1), 2)
        r.hinweise.append(f"{HINWEIS}: Rohr {max(x1 - x0, y1 - y0):g} × {min(x1 - x0, y1 - y0):g} mm, quer zur offenen "
                          f"Seite {_wachs(e, x0, y0, x1, y1):g} mm größer als das Teil, damit nichts wegfällt (der "
                          f"Radius R{e['ra']:g} beginnt erst nach den Schenkelenden)")
    if steg and e.get("ueberstand", 0.0) > 0.5:
        r.offene_seite["ueberstand"] = round(e["ueberstand"], 1)
        r.hinweise.append(f"{HINWEIS}: Teil ragt über den Querschnitt des Rohrs (ca. {e['ueberstand']:.1f} mm², z. B. "
                          f"scharfe Schenkelenden an den Rohrecken) – fällt weg, die Ecken bekommen den Rohrradius "
                          f"R{e['ra']:g}")
    if steg and e.get("norm"):
        _, na, nb = e["norm"]
        r.abm_a, r.abm_b = float(na), float(nb)
        r.offene_seite["normrohr"] = True
    elif steg:
        r.offene_seite["normrohr"] = False
        r.hinweise.append(f"{HINWEIS}: kein Normrohr passt (Hülle {r.abm_a:g} × {r.abm_b:g} mm), Sondermaß prüfen")
    r.volumen = g._volumen(zu)          # so gelasert (Gewicht); gezeichnet: t.volumen
    g.virtuell_ablegen(zu, koerper)
    t.geschlossen = r
    if netz and not ringe_step:         # Ringe aus der STEP: nichts ergänzt, nichts zusätzlich zu zeigen
        try:
            if ringe:       # sichtbar nur, was zum Teil dazukommt
                # der ganze Ring, auf der Wand (Patrick: „der Steg muss auf die Rohrwandung gesetzt werden“)
                zeigen = ring(e, d, steg, anzeige=True)
                _netz_koerper(t, _bool("plus", *(zeigen[0] if zeigen else ringe)), e["ax3"], 0.05)
                if e.get("ueberstand", 0.0) > 0.5 and e.get("rest") is not None:
                    _netz_koerper(t, e["rest"], e["ax3"], 0.2, art="UO")     # fällt weg: über dem Rohr
            else:
                _netz_wand(t, e, d)
        except Exception:  # ohne Anzeige der Stege bzw. der Wand bleibt alles andere gültig
            pass
    return True


def _ringe_im_teil(e, d):
    """True, wenn ein Ring RING_PRUEF breit an beiden Enden ganz im Teil liegt: das Rohr ist an den Enden schon
    geschlossen gezeichnet (Patrick 27.10.2026), es wird kein Ring ergänzt."""
    rg = ring(e, d, RING_PRUEF)
    if not rg or not rg[0]:
        return False
    for k in rg[0]:
        rest = _bool("minus", k, e["lok"])
        if rest is None or g._volumen(rest) >= RING_REST * g._volumen(k):
            return False
    return True


# ---- Rundrohr: Halbschale und offenes Rundrohr (Patrick 25.10.2026: „Funktioniert das dann auch mit Rundrohr? Dass
# er die Halbschale zu einem geschlossenen Rohr macht?“) – Mantel aus zwei gleichachsigen Zylindern, über die ganze
# Länge ein Stück des Umfangs offen. Gefertigt aus dem Rundrohr mit je einem Ring-Steg STEG an Ende A und B, das offene
# Stück dazwischen als Fenster; ein Spalt bis SPALT_MAX (Bogen außen) wird ganz geschlossen. Die Enden müssen eben
# sein (gerade oder Gehrung): der Steg läuft in der Ebene des Endes weiter.

GRAD = 0.25             # Grad, Abtastung des Umfangs
ENDE_TOL = 0.05         # mm, Endfläche erreicht zmin bzw. zmax
RING_PRUEF = 0.3        # mm, Ring an den Enden, der ganz im Teil liegen muss (Enden geschlossen gezeichnet)
RING_REST = 0.01        # Anteil des Prüfrings, der außerhalb des Teils liegen darf (Rundung der Booleschen Operation)
LUFT = 5.0          # mm am Außendurchmesser zwischen zwei Schalen aus einem Rohrumfang (Patrick 25.10.2026)


def _zylinder(solid):
    """Mantel: (Achse gp_Ax1, R außen, r innen) aus den Zylinderflächen des Körpers (die größte Fläche gibt die
    Achse; außen und innen gleichachsig) oder None."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    zyl = []
    for f in g._liste(solid, TopAbs_FACE):
        s = BRepAdaptor_Surface(TopoDS.Face(f))
        if s.GetType() == GeomAbs_Cylinder:
            zyl.append((_flaeche(f), s.Cylinder()))
    if len(zyl) < 2:
        return None
    zyl.sort(key=lambda x: -x[0])
    achse = zyl[0][1].Axis()
    radien = set()
    for _, c in zyl:
        a = c.Axis()
        if a.Direction().IsParallel(achse.Direction(), 1e-4) and \
                gp_Lin(achse).Distance(a.Location()) < 0.01:
            radien.add(round(c.Radius(), 4))
    if len(radien) != 2:
        return None
    r, R = sorted(radien)
    return achse, R, r


def _flaeche(f):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(f, p)
    return p.Mass()


def _rund_erkennen(solid):
    """Offenes Rundrohr: dict(ax3, lok, R, r, luecke (Winkel von, bis in Grad, im lokalen System), z) oder None."""
    from OCP.gp import gp_Ax3
    z_ = _zylinder(solid)
    if z_ is None:
        return None
    achse, R, r = z_
    ax3 = gp_Ax3(achse.Location(), achse.Direction())
    lok = g._transformiere(solid, ax3)
    zmin, zmax = g._z_bereich(lok)
    if zmax - zmin < 3 * (R - r):
        return None
    lagen = []
    for k in range(LAGEN):
        z = zmin + (zmax - zmin) * (0.1 + 0.8 * k / (LAGEN - 1)) + 0.0137
        ws = g._schnitt(lok, z)
        if len(ws) == 1:
            st = g._strecken(ws[0][1], 0.1)
            if max(math.hypot(x, y) for s_ in st for x, y in (s_[:2], s_[2:])) > R + 0.05:
                return None         # Material außerhalb des Mantels: kein Rohrstück (z. B. Biegung eines U)
            lagen.append(st)
    if len(lagen) < 3:
        return None
    rm = (R + r) / 2

    def frei(w):           # an allen Lagen kein Material auf dem Mittelkreis der Wand
        x, y = rm * math.cos(math.radians(w)), rm * math.sin(math.radians(w))
        return not any(g._im_material(x, y, st) for st in lagen)
    n = int(360 / GRAD)
    f = [frei(k * GRAD) for k in range(n)]
    if all(f) or not any(f):
        return None
    start = f.index(False)          # bei Material beginnen: die Lücke liegt am Stück zwischen 0 und 360
    luecken, von = [], None
    for k in range(start, start + n + 1):
        if f[k % n] and von is None:
            von = k
        elif not f[k % n] and von is not None:
            luecken.append((von, k))
            von = None
    luecken = [(a, b) for a, b in luecken if (b - a) * GRAD * math.pi / 180 * R >= LUECKE_INNEN]
    if len(luecken) != 1:
        return None                 # mehrere Schlitze: kein offenes Rohr

    def kante(w_frei, w_voll):
        for _ in range(20):
            m = (w_frei + w_voll) / 2
            w_frei, w_voll = (m, w_voll) if frei(m) else (w_frei, m)
        return (w_frei + w_voll) / 2
    a, b = luecken[0]
    w0, w1 = kante(a * GRAD, (a - 1) * GRAD), kante((b - 1) * GRAD, b * GRAD)
    return dict(ax3=ax3, lok=lok, R=R, r=r, luecke=(w0, w1), z=(zmin, zmax))


def _enden_eben(lok, zmin, zmax):
    """Ebene je Ende (gp_Pln) aus den Endflächen des Körpers (Normale mit Anteil längs der Achse, nahe zmin bzw.
    zmax); None, wenn ein Ende nicht in einer Ebene liegt. Querflächen, die das Ende nicht erreichen (Ränder eines
    Fensters kurz vor dem geschlossenen Ring, Patrick 27.10.2026), zählen nicht als Ende."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    enden = {0: [], 1: []}
    mitte = (zmin + zmax) / 2
    for f in g._liste(lok, TopAbs_FACE):
        s = BRepAdaptor_Surface(TopoDS.Face(f))
        if s.GetType() != GeomAbs_Plane:
            continue
        pl = s.Plane()
        if abs(pl.Axis().Direction().Z()) < 0.2:
            continue                # Längsfläche (Rand der Lücke)
        bb = Bnd_Box()
        BRepBndLib.Add_s(f, bb, False)
        k = 0 if (bb.CornerMin().Z() + bb.CornerMax().Z()) / 2 < mitte else 1
        if (bb.CornerMin().Z() - zmin if k == 0 else zmax - bb.CornerMax().Z()) > ENDE_TOL:
            continue                # Querfläche im Teil (Fensterrand), nicht am Ende
        enden[k].append(pl)
    out = []
    for k in (0, 1):
        if not enden[k]:
            return None
        p0 = enden[k][0]
        for p in enden[k][1:]:
            if not p.Axis().Direction().IsParallel(p0.Axis().Direction(), 1e-4) or \
                    p0.Distance(p.Location()) > 0.01:
                return None
        out.append(p0)
    return out


def _enden_zu(e):
    """True, wenn das offene Rundrohr an beiden Enden schon ganz geschlossen gezeichnet ist (je ein Ring mindestens
    RING_PRUEF breit, Patrick 27.10.2026: Rohr mit großem Ausschnitt, „wird nicht als Rundrohr erkannt“). Dann wird
    kein Ring ergänzt: der Ausschnitt bleibt genau wie in der STEP."""
    ringe = _rund_stuecke(e, RING_PRUEF, ganz=True)
    if ringe is None:
        return False
    rest = _bool("minus", ringe, e["lok"])
    return rest is not None and g._volumen(rest) < RING_REST * g._volumen(ringe)


def _halbraum(pl, verschiebung, ref):
    """Halbraum der Ebene pl (längs der Achse um verschiebung versetzt) auf der Seite des Punkts ref."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
    from OCP.gp import gp_Pln, gp_Vec
    q = gp_Pln(pl.Position())
    q.Translate(gp_Vec(0, 0, verschiebung))
    return BRepPrimAPI_MakeHalfSpace(BRepBuilderAPI_MakeFace(q).Face(), gp_Pnt(*ref)).Solid()


def _bool(art, a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    op = {"und": BRepAlgoAPI_Common, "plus": BRepAlgoAPI_Fuse, "minus": BRepAlgoAPI_Cut}[art](a, b)
    op.SetFuzzyValue(g.FUZZY)
    op.Build()
    return op.Shape() if op.IsDone() else None


def _rund_stuecke(e, steg, ganz=False):
    """Fehlendes Stück des Mantels (steg = 0) bzw. die zwei Ring-Stege an den Enden, im lokalen System; None, wenn
    die Enden nicht eben sind. ganz: der ganze Mantel statt nur über der Lücke (Ringe des ganzen Rohrs, Patrick
    25.10.2026: „die Rohre auch Außenradius etc haben … nicht nur einen Steg dazwischen“), mit den Radien der Zeichnung."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
    from OCP.gp import gp_Ax2, gp_Vec
    R, r, (zmin, zmax) = e["R"], e["r"], e["z"]
    L = zmax - zmin
    ebenen = _enden_eben(e["lok"], zmin, zmax)
    if ebenen is None:
        return None
    z0 = zmin - 2 * L - 4 * R
    h = 5 * L + 8 * R
    mantel = _bool("minus", BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), R, h).Shape(),
                   BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0 - 1), gp_Dir(0, 0, 1)), r, h + 2).Shape())
    w0, w1 = e["luecke"]
    # etwas in die Ränder: ist die Lücke nicht radial begrenzt (Schnitt in einer Ebene), bliebe sonst ein Spalt
    rand = math.degrees((R - r) / r) * 2 + 0.5 if steg is not None else 0.0
    w0, w1 = w0 - rand, w1 + rand
    poly = BRepBuilderAPI_MakePolygon()
    poly.Add(gp_Pnt(0, 0, z0))
    n = max(2, int((w1 - w0) / 5) + 1)
    for k in range(n + 1):
        w = math.radians(w0 + (w1 - w0) * k / n)
        poly.Add(gp_Pnt(3 * R * math.cos(w), 3 * R * math.sin(w), z0))     # Sehnen weit außerhalb des Mantels
    poly.Close()
    keil = BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(poly.Wire()).Face(), gp_Vec(0, 0, h)).Shape()
    stueck = mantel if ganz else _bool("und", mantel, keil)
    innen = (0.0, 0.0, (zmin + zmax) / 2)
    for pl in ebenen:
        stueck = stueck and _bool("und", stueck, _halbraum(pl, 0.0, innen))
    if not steg or stueck is None:
        return stueck
    (pa, pb) = ebenen
    stege = []
    for pl, d_, ref in ((pa, steg, (0, 0, z0)), (pb, -steg, (0, 0, z0 + h))):
        s = _bool("und", stueck, _halbraum(pl, d_, ref))
        if s is None:
            return None
        stege.append(s)
    return _bool("plus", stege[0], stege[1])


def _netz_koerper(t, koerper, ax3, abheben=0.0, art="EO"):
    """Körper (lokales System ax3) als Dreiecke der Art art (Vorgabe EO) ins Netz der offenen Messung t. abheben (mm): jede Fläche
    so weit nach außen versetzt gezeichnet, damit ein Ring, der auf der Wand des Teils sitzt, vor der Wand liegt
    (gleiche Fläche: die 3D-Ansicht zeigte sonst mal die eine, mal die andere)."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    if t.netz is None or not t.achse_global:
        return
    zu_datei, zu_netz = gp_Trsf(), gp_Trsf()
    zu_datei.SetTransformation(ax3)
    zu_netz.SetTransformation(g._rohr_ax3(t))
    tr = zu_netz.Multiplied(zu_datei.Inverted())
    BRepMesh_IncrementalMesh(koerper, 0.05, False, 0.3, True)
    p, idx = [], []
    for f in g._liste(koerper, TopAbs_FACE):
        ort = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(TopoDS.Face(f), ort)
        if tri is None:
            continue
        basis = len(p) // 3
        m = tr.Multiplied(ort.Transformation())
        q = [tri.Node(j).Transformed(m) for j in range(1, tri.NbNodes() + 1)]
        umgedreht = f.Orientation() == 1           # TopAbs_REVERSED: Dreiecke nach außen drehen
        dreiecke = []
        for j in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(j).Get()
            dreiecke.append((a - 1, c - 1, b - 1) if umgedreht else (a - 1, b - 1, c - 1))
        versatz = [[0.0, 0.0, 0.0] for _ in q]
        if abheben:
            for a, b, c in dreiecke:            # Normale je Knoten (Mittel der Dreiecke), nach außen
                u_ = [q[b].Coord(k + 1) - q[a].Coord(k + 1) for k in range(3)]
                v_ = [q[c].Coord(k + 1) - q[a].Coord(k + 1) for k in range(3)]
                n = (u_[1] * v_[2] - u_[2] * v_[1], u_[2] * v_[0] - u_[0] * v_[2], u_[0] * v_[1] - u_[1] * v_[0])
                for i in (a, b, c):
                    for k in range(3):
                        versatz[i][k] += n[k]
            for v in versatz:
                betrag = math.sqrt(sum(c * c for c in v)) or 1.0
                v[:] = [c / betrag * abheben for c in v]
        for pt, v in zip(q, versatz):
            p += [round(pt.X() + v[0], 2), round(pt.Y() + v[1], 2), round(pt.Z() + v[2], 2)]
        idx += [basis + i for tri_ in dreiecke for i in tri_]
    g._netz_anhaengen(t.netz, dict(p=p, t={art: idx}, l={}))
    _verfeinern(t.netz, max(10.0, t.laenge / 20))


def _schalen(e, m):
    """Mehrere Schalen aus einem Rohrumfang (Patrick 25.10.2026, „Rundrohr alle a“): Schalen je Umfang =
    ⌊360° ÷ (Schalenwinkel + Luft)⌋ mit mindestens LUFT mm am Außendurchmesser zwischen zwei Schalen. Jede Schale wird
    dann ganz freigeschnitten (zwei Längskanten, die Bögen an den Enden, ihre Bohrungen; keine Ringe). Ergebnis
    dict(je_umfang, schale_grad, luft, schale_schnitt [mm]); je_umfang 1 = nur eine Schale je Rohr (mit Ringen)."""
    R, rm = e["R"], (e["R"] + e["r"]) / 2
    w0, w1 = e["luecke"]
    grad = 360.0 - (w1 - w0)
    luft = math.degrees(LUFT / R)
    je = max(1, int(360.0 // (grad + luft)))
    kanten = 0.0
    for w in (w0 - 0.5, w1 + 0.5):          # knapp im Material neben der Lücke
        zg = _z_grenzen(e["lok"], rm * math.cos(math.radians(w)), rm * math.sin(math.radians(w)))
        kanten += (zg[1] - zg[0]) if zg else e["z"][1] - e["z"][0]
    fenster = max((lg for _, lg in m.innen_liste), default=0.0)
    schnitt = kanten + (m.ende_a + m.ende_b) * grad / 360.0 + max(m.innen - fenster, 0.0)
    return dict(je_umfang=je, schale_grad=round(grad, 2), luft=LUFT, schale_schnitt=round(schnitt, 1))


def _rund_schliessen(solid, t, datei, koerper, netz):
    """Halbschale bzw. offenes Rundrohr als Rundrohr: t.geschlossen mit Ring-Stegen an den Enden und Fenster (Spalt bis
    SPALT_MAX: ganz geschlossen). False, wenn nicht erkannt."""
    e = _rund_erkennen(solid)
    if e is None:
        return False
    R, r = e["R"], e["r"]
    w0, w1 = e["luecke"]
    laenge = e["z"][1] - e["z"][0]
    breite = math.radians(w1 - w0) * R                       # Bogen außen
    # Spalt: lichte Weite (Sehne auf dem Mittelkreis, an dem die Lücke gesucht ist), nicht der Bogen außen
    weite = 2 * (R + r) / 2 * math.sin(math.radians(w1 - w0) / 2)
    steg = 0.0 if weite <= SPALT_MAX + SPALT_TOL or laenge < 4 * STEG else STEG
    norm = step_normrohre.naechstes_rund(2 * R)
    if not (norm and norm / 2 - R <= step_normrohre.ABWEICHUNG / 2 and steg):
        norm = None         # gemessen wird im Durchmesser des Teils, das Normrohr gilt als Profil
    voll_stueck = _rund_stuecke(e, 0.0)
    if voll_stueck is None:
        return False
    voll = _vereinen(solid, [voll_stueck], e["ax3"])
    stuecke, zu = None, voll
    ringe_step = bool(steg) and _enden_zu(e)
    if steg:
        stuecke, rohr = _rund_stuecke(e, steg, ganz=True), _rund_stuecke(e, 0.0, ganz=True)
        if ringe_step:          # Ringe stehen schon in der STEP: nichts ergänzen, Fenster genau wie gezeichnet
            stuecke, zu = None, solid
        else:
            zu = _vereinen(solid, [stuecke], e["ax3"]) if stuecke is not None else None
        voll = _vereinen(voll, [rohr], e["ax3"], False) if rohr is not None and voll is not None else None
    if voll is None or zu is None:
        return False
    m = g._profil_messen(zu, datei, koerper, False, quer=voll if steg else None)
    if m.profilform != "Rundrohr" or abs(m.wandstaerke - (R - r)) > TOL_WAND:
        return False
    if norm:
        m.abm_a = float(norm)
    m.bauteiltyp = "Profil"
    m.offene_seite = dict(seite="Umfang", luecken=[[round(w0, 2), round(w1, 2)]], breite=round(breite, 2),
                          laenge=round(laenge, 2), vorher=t.profilform, steg=steg or None)
    m.sicherheit["offene_seite"] = "stege" if steg else "ergänzt"
    if ringe_step:
        m.offene_seite["ringe_step"] = True
        m.hinweise.append(f"{HINWEIS}: Rundrohr, Enden in der STEP geschlossen, Ausschnitt ({w1 - w0:.0f}°, "
                          f"{breite:.1f} mm) als Innenkontur wie gezeichnet (vorher {t.profilform}) – Profil prüfen")
    elif steg:
        m.offene_seite.update(_schalen(e, m))
    if steg and not ringe_step:
        m.hinweise.append(f"{HINWEIS}: aus dem Rundrohr gelasert, offener Umfang ({w1 - w0:.0f}°, {breite:.1f} mm) bis "
                          f"auf je einen Ring {steg:g} mm an Ende A und B ausgeschnitten (vorher {t.profilform}) – "
                          "Profil prüfen")
        if m.offene_seite["je_umfang"] > 1:
            m.hinweise.append(f"{HINWEIS}: {m.offene_seite['je_umfang']} Schalen je Rohrumfang möglich "
                              f"({m.offene_seite['schale_grad']:g}°, {LUFT:g} mm Luft), je Schale ganz freigeschnitten "
                              f"{m.offene_seite['schale_schnitt']:g} mm")
    elif not steg:
        m.hinweise.append(f"{HINWEIS}: Spalt {breite:.1f} mm über {laenge:.1f} mm Länge geschlossen (vorher "
                          f"{t.profilform}) – Profil prüfen")
    m.volumen = g._volumen(zu)
    g.virtuell_ablegen(zu, koerper)
    t.geschlossen = m
    if netz and not ringe_step:     # nichts ergänzt: nichts zusätzlich zu zeigen
        try:
            # sichtbar nur das, was zum Teil kommt (ohne die Überlappung in die Ränder)
            if steg:        # der ganze Ring, auf der Wand
                _netz_koerper(t, stuecke, e["ax3"], 0.05)
            else:
                _netz_koerper(t, _bool("minus", voll_stueck, e["lok"]), e["ax3"])
        except Exception:  # ohne Anzeige bleibt alles andere gültig
            pass
    return True
