"""Schrift und Markierungen als eigene Körper (Patrick 29.10.2026: „wenn größere Gravuren auf dem Teil sind, dauert
es sehr lange und er erkennt falsch“).

Viele CAD-Modelle legen eine Gravur nicht als Vertiefung in das Rohr, sondern als eigenen dünnen Körper (Schrift
0,1 mm aufgesetzt, je Buchstabe ein Körper) oder als lose Flächen auf die Rohrwand. Bisher wurde jeder Buchstabe
als Blech gemessen (mit Flachstahl-Zweitmessung, je Buchstabe Hunderte Querschnitte: 24 Zeichen 4–5 Minuten), als
Anbauteil ohne Innenkonturen (Ø in „0“, „A“, „B“ fehlte) bzw. als „Flächenmodell offen“ ganz ohne Gravur gemeldet.

Jetzt gilt: ein eigener Körper (Volumen höchstens GRAVUR_DICKE dick oder lose Flächen), der ganz auf dem Mantel eines
gemessenen Rohrs liegt (jeder Punkt höchstens GRAVUR_ABSTAND von der Außenkontur, innerhalb der Rohrlänge), ist eine
Gravur dieses Rohrs. Seine Konturen (Rand der Fläche, die auf der Rohrwand liegt, mit allen Innenkonturen) kommen als
Zeilen „Gravur“ mit Lage und Umriss wie eine eingeprägte Gravur in die Konturliste des Rohrs, genau dort, wo sie in der
STEP liegen. Der Körper selbst wird kein Teil (Profilform GRAVURKOERPER, wie ein Verbundkern nur gemeldet) und zählt
nicht für Anbauteile, Nahtkandidaten und Erreichbarkeit.
"""
import math

import step_geometrie as g
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX, TopAbs_WIRE
from step_geometrie import TopTools_IndexedMapOfShape  # OCP-Version wie dort

GRAVURKOERPER = "Gravurkörper"
GRAVUR_DICKE = g.GRAVUR_DICKE  # mm: so dünne eigene Volumenkörper können Schrift/Markierung sein
GRAVUR_ABSTAND = 1.0        # mm: jeder Punkt des Körpers so nah an der Außenkontur des Rohrs
TOL_AUF = 0.05              # mm: Spielraum an den Rohrenden
NORMALE_COS = 0.7           # Fläche zeigt zur Rohrwand: Normale höchstens ~45° gegen die Wandnormale


def duenn(t, art):
    """True, wenn der Körper (Teil t, Körperart art) eine Gravur sein kann: lose Flächen oder ein ebenes Blech
    (bzw. Flachstahl) höchstens GRAVUR_DICKE dick."""
    if art == "Flächenmodell offen":
        return True
    if t.profilform == "Flachstahl":        # schmaler Strich („1“, „-“) misst sich als Flachstahl
        return 0 < min(t.abm_a, t.abm_b or t.abm_a) <= GRAVUR_DICKE + 1e-6
    bl = t.blech if isinstance(t.blech, dict) else None
    return t.bauteiltyp == "Blech" and bl is not None and 0 < (bl.get("dicke") or 0) <= GRAVUR_DICKE + 1e-6


def _wand_normale(x, y, s_a, cx, cy):
    """Normale der Rohrwand nach außen (x, y) an der nächsten Stelle der Außenkontur s_a (Mitte cx, cy)."""
    x1, y1, x2, y2 = min(s_a, key=lambda st: g._abst_strecke(x, y, st))
    lg = math.hypot(x2 - x1, y2 - y1) or 1.0
    nx, ny = (y2 - y1) / lg, -(x2 - x1) / lg
    if nx * ((x1 + x2) / 2 - cx) + ny * ((y1 + y2) / 2 - cy) < 0:
        nx, ny = -nx, -ny
    return nx, ny


def _boden(lok, r, lg, offen):
    """Flächen des Körpers (im Rohrsystem lok), deren Rand die Gravur ist: bei Volumenkörpern die Seite zur Rohrwand
    (Normale zeigt ins Rohr, bei aufgesetzter Schrift die Unterseite), bei losen Flächen alle, die parallel zur Wand
    liegen. None, wenn der Körper nicht ganz auf dem Mantel liegt (jeder Punkt höchstens GRAVUR_ABSTAND von der
    Außenkontur, innerhalb der Rohrlänge)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    s_a, abw = r["s_aussen"], r["abw"]
    out = []
    for f in g._liste(lok, TopAbs_FACE):
        pts = g._flaechen_punkte(f)
        if not pts or any(not -TOL_AUF <= p.Z() <= lg + TOL_AUF or
                          g._abstand_zug(p.X(), p.Y(), s_a) > GRAVUR_ABSTAND for p in pts):
            return None
        pr = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, pr)
        c = pr.CentreOfMass()
        n = g._normale(f, c)
        if n is None:
            continue
        wx, wy = _wand_normale(c.X(), c.Y(), s_a, abw.cx, abw.cy)
        dot = n[0] * wx + n[1] * wy
        if dot < -NORMALE_COS or offen and dot > NORMALE_COS:
            out.append(f)
    return out or None


def _zuege(flaechen):
    """Rand der Flächen (Kanten, die nur zu einer der Flächen gehören, alle Drähte: außen und innen) als
    geschlossene Züge (über gemeinsame Eckpunkte)."""
    karte, zahl = TopTools_IndexedMapOfShape(), {}
    for f in flaechen:
        for w in g._liste(f, TopAbs_WIRE):
            for e in g._liste(w, TopAbs_EDGE):
                i = karte.Add(e)
                zahl[i] = zahl.get(i, 0) + 1
    rand = [karte.FindKey(i) for i, n in zahl.items() if n == 1]
    vmap = TopTools_IndexedMapOfShape()
    for e in rand:
        for v in g._liste(e, TopAbs_VERTEX):
            vmap.Add(v)
    eltern = {}

    def fv(x):
        while eltern.setdefault(x, x) != x:
            eltern[x] = eltern[eltern[x]]
            x = eltern[x]
        return x
    for e in rand:
        vs = [vmap.FindIndex(v) for v in g._liste(e, TopAbs_VERTEX)]
        for v in vs:
            eltern[fv(v)] = fv(vs[0])
    out = {}
    for e in rand:
        vs = g._liste(e, TopAbs_VERTEX)
        if vs:
            out.setdefault(fv(vmap.FindIndex(vs[0])), []).append(e)
    return list(out.values())


def _eintrag(zug, r, kasten, quelle):
    """Zeile 'Gravur' der Konturliste für einen Zug (Rohrsystem, z ab Ende A) wie bei eingeprägter Gravur."""
    abw = r["abw"]
    pts = g._punkte_kanten(zug)
    if len(pts) < 3:
        return None
    uv = g._u_entrollen([(abw.u(p.X(), p.Y()), p.Z()) for p in pts], abw.umfang)
    form, (uc, vc), _ = g._form_2d(uv)
    winkel, px, py = abw.punkt(uc)
    seite = None
    if kasten:
        dx, dy = px - abw.cx, py - abw.cy
        seite = f"{round(winkel / 90) % 4 * 90}°" if abs(abs(dx) - r["hx"]) < 0.05 or abs(abs(dy) - r["hy"]) < 0.05 \
            else "Ecke"
    u = uc % abw.umfang
    d = dict(art="Gravur", durchgehend=False, z=round(vc, 2), winkel=round(winkel % 360, 1) % 360,
             u=round(0.0 if abw.umfang - u < 0.005 else u, 2), seite=seite, laenge=round(form[1], 2),
             breite=round(form[2], 2), schnittlaenge=round(sum(g._kantenlaenge(e) for e in zug), 2),
             quelle=quelle, hinweis="Schrift/Markierung als eigener Körper: Gravur, nicht im Schneidweg")
    if form[0] == "Kreis":
        d.update(breite=round(form[1], 2), durchmesser=round(form[1], 2))
    um = g._umriss_uv(zug, abw, 0.0, d["u"])
    if um:
        d["umriss"] = um
    return d


def zuordnen(teile, koerper, netz=False, rahmen=None):
    """Gravurkörper der Datei den Rohren zuordnen (siehe oben). rahmen(t): Abwicklung eines Rohrs, dessen _rahmen
    fehlt (wie bei _beruehrende_anbauteile). Ergebnis: Menge der Indizes (in teile), die Gravurkörper geworden
    sind."""
    rohre = [(t, k) for t, (art, k) in zip(teile, koerper) if g._ist_rohr(t) and t.laenge > 0]
    kandidaten = [(i, t, k, art == "Flächenmodell offen") for i, (t, (art, k)) in enumerate(zip(teile, koerper))
                  if not g._ist_rohr(t) and duenn(t, art)]
    if not rohre or not kandidaten:
        return set()
    boxen = []
    for _, k in rohre:
        b = Bnd_Box()
        BRepBndLib.Add_s(k, b, False)
        b.Enlarge(GRAVUR_ABSTAND)
        boxen.append(b)
    fertig, neu = set(), {}
    for i, u, k, offen in kandidaten:
        kb = Bnd_Box()
        BRepBndLib.Add_s(k, kb, False)
        for (t, _), rb in zip(rohre, boxen):
            if rb.IsOut(kb):
                continue
            r = getattr(t, "_rahmen", None) or (rahmen(t) if rahmen else None)
            if r is None or not t.ende_a_global:
                continue
            lok = g._transformiere(k, g._rohr_ax3(t))
            boden = _boden(lok, r, t.laenge, offen)
            if not boden:
                continue
            quelle = f"Körper {u.koerper}"
            zeilen = [d for d in (_eintrag(z, r, r["kasten"], quelle) for z in _zuege(boden)) if d]
            if not zeilen:
                continue
            laenge = sum(d["schnittlaenge"] for d in zeilen)
            t.gravur += laenge
            t.gravur_konturen += len(zeilen)
            neu.setdefault(id(t), (t, []))[1].extend(zeilen)
            if netz and t.netz is not None:
                g._netz_anhaengen(t.netz, dict(p=[], t={}, l={"G": [g._linienzug(e) for z in _zuege(boden)
                                                                     for e in z]}))
            u.profilform, u.bauteiltyp = GRAVURKOERPER, ""
            u.alternative = None
            u.hinweise = [f"Schrift/Markierung auf Körper {t.koerper}, dort als Gravur"]
            fertig.add(i)
            break
    for t, zeilen in neu.values():     # ohne Hinweis am Rohr: wie eingeprägte Gravur kein Grund zum Prüfen
        kopf = [d for d in t.konturen_liste if d.get("art") in ("Ende A", "Ende B")]
        rest = [d for d in t.konturen_liste if d.get("art") not in ("Ende A", "Ende B")] + zeilen
        t.konturen_liste = kopf + sorted(rest, key=lambda d: (d["z"] is None, d["z"] or 0, d["winkel"] or 0))
    return fertig


def ohne(teile, koerper, weg):
    """teile und koerper ohne die Indizes in weg (für Anbauteile, Verbund, Nahtkandidaten)."""
    return [t for i, t in enumerate(teile) if i not in weg], [k for i, k in enumerate(koerper) if i not in weg]

