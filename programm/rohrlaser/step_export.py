"""STEP-Export (Plan 3D-Editor 3E-8, Patrick 24.10.2026): im Rohr- und Blech-Editor erstellte Teile als STEP mit
echtem Volumenkörper speichern, mit Gehrungen, Ausklinkungen, Konturen, Nasen und Gravuren.

Hier entsteht nur der Bauplan (JSON, ohne OpenCascade). Gebaut und geschrieben wird er wie die Messung in einem
eigenen Prozess (STEP-Import.exe --export, step_messung/step_schreiben.py):

- Rohr: Querschnitt exakt (Kreis, Quadrat-/Rechteckrohr mit echtem Außenradius, Profile als Umriss), entlang der
  Rohrachse Z (Koordinaten wie die 3D-Ansicht: X = −u, Y = oben, Z ab Ende A). Ein ebenes Ende (gerade, Gehrung,
  3D-Schnitt) ist ein Halbraum, ein gekrümmtes Ende (Sattel, Gegenrohr, Schnitt senkrecht zum Mantel) ein Netz
  entlang derselben Schnittkante wie im 3D (rohr3d.netz). Bohrungen sind echte Zylinder, alle anderen Konturen
  Werkzeuge je Fläche des Umrisses (eben, damit sie über Kanten und Rundungen der Wand folgen).
- Nasen einer Steckverbindung bleiben stehen: das Werkzeug des Endes spart sie aus.
- Gravuren (Text-Gravur, Artikelnummer, Gravur mit Umriss) als Rille GRAVUR_TIEFE tief und GRAVUR_BREITE breit,
  mindestens GRAVUR_ABSTAND von Enden, Außenkontur und Konturen (Patrick 24.10.2026, sonst gekürzt mit Hinweis).
- Blech: eben (auch aus dem DXF-Import), Außenkontur und Innenkonturen mit echten Bögen.
"""
import json
import math
import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

from . import blech, blech3d, gravur_text, optimierung as opt, rohr3d, schneidweg as sw, skizze as sk
from .blech3d import _flaeche2, _ohrschnitt
from .schneidweg import BOHRUNG, GRAVUREN, SENKUNG, TEXT_GRAVUR, _z

GRAVUR_TIEFE = 0.1          # mm, mindestens (Patrick 24.10.2026)
GRAVUR_BREITE = 0.2         # mm, Breite der Rille
GRAVUR_ABSTAND = 0.5        # mm zu Enden, Außenkontur und Konturen (wie blech.GRAVUR_ABSTAND)
GRAVUR_UEBER = 0.3          # Rille beginnt so weit über der Oberfläche [mm]
GRAVUR_SCHRITT = 1.0        # Gravur in Stücke höchstens so lang prüfen und legen [mm] (Rundrohr: folgt der Wand)
UEBER = 1.0                 # Werkzeuge ragen so weit über die Wand [mm]
FERN = 10.0                 # Werkzeug eines Endes reicht so weit über das Teil hinaus [mm]
EBEN_TOL = 1e-3             # Ende gilt als eben bis zu dieser Abweichung [mm]
STREIFEN_UEBER = 0.02       # Werkzeuge benachbarter Flächen überlappen so viel [mm]
BULGE_90 = math.tan(math.radians(22.5))
ZEITLIMIT = 300             # Sekunden für das Schreiben


# ------------------------------------------------------------------ kleine Vektorrechnung
def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _add(a, b, f=1.0):
    return tuple(a[i] + b[i] * f for i in range(3))


def _norm(a):
    lg = math.sqrt(sum(c * c for c in a)) or 1.0
    return tuple(c / lg for c in a)


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _r(v, n=6):
    return [round(float(c), n) for c in v]


class Netz:
    """Geschlossenes Dreiecksnetz eines Werkzeugs (Punkte, Dreiecke) für den Bauplan."""

    def __init__(self):
        self.p, self.t = [], []

    def punkt(self, v):
        self.p.extend(_r(v))
        return len(self.p) // 3 - 1

    def viereck(self, a, b, c, d):
        self.t += [a, b, c, a, c, d]

    def werkzeug(self, **mehr):
        return dict(art="netz", p=self.p, t=self.t, **mehr)


def _ccw(pk):
    return list(pk) if _flaeche2(pk) > 0 else list(pk)[::-1]


def _ohne_doppelte(pk, tol=1e-7):
    out = []
    for p in pk:
        if not out or math.dist(p, out[-1]) > tol:
            out.append(p)
    while len(out) > 1 and math.dist(out[0], out[-1]) <= tol:
        out.pop()
    return out


def prisma_netz(pk2, oben, unten):
    """Werkzeug zwischen zwei Ringen: pk2 = Polygon in 2D (für die Deckel), oben/unten = je Punkt 3D. Deckel aus dem
    Ohrenschnitt von pk2, Seiten je Kante."""
    n = Netz()
    io = [n.punkt(p) for p in oben]
    iu = [n.punkt(p) for p in unten]
    index = {(round(p[0], 9), round(p[1], 9)): i for i, p in enumerate(pk2)}
    for a, b, c in _ohrschnitt(pk2):
        ia, ib, ic = (index[(round(q[0], 9), round(q[1], 9))] for q in (a, b, c))
        n.t += [io[ia], io[ib], io[ic], iu[ia], iu[ic], iu[ib]]
    k = len(pk2)
    for i in range(k):
        j = (i + 1) % k
        n.viereck(io[i], iu[i], iu[j], io[j])
    return n


# ------------------------------------------------------------------ Querschnitt
def rund_rechteck(b, h, r, cx=0.0, cy=0.0, w=0.0):
    """Rechteck b × h (Mitte cx, cy, um w Grad gedreht) mit Eckradius r als Eckpunkte mit Bulge, gegen den
    Uhrzeigersinn."""
    x, y = b / 2, h / 2
    r = max(0.0, min(r, x, y))
    if r < 1e-6:
        pk = [(-x, -y, 0.0), (x, -y, 0.0), (x, y, 0.0), (-x, y, 0.0)]
    else:
        pk = [(-x + r, -y, 0.0), (x - r, -y, BULGE_90), (x, -y + r, 0.0), (x, y - r, BULGE_90),
              (x - r, y, 0.0), (-x + r, y, BULGE_90), (-x, y - r, 0.0), (-x, -y + r, BULGE_90)]
    return _gedreht(pk, w, cx, cy)


def _gedreht(pk, w, cx=0.0, cy=0.0):
    c, s = math.cos(math.radians(w)), math.sin(math.radians(w))
    return [[round(cx + x * c - y * s, 6), round(cy + x * s + y * c, 6), round(b, 9)] for x, y, b in pk]


def querschnitt(qs):
    """(außen, innen) des Rohrs in XY (X = −u, Y = v) als Kontur des Bauplans; innen None bei Vollprofil."""
    if qs.r:
        innen = {"kreis": [0.0, 0.0, round(qs.r - qs.wand, 6)]} if 0 < qs.wand < qs.r else None
        return {"kreis": [0.0, 0.0, round(qs.r, 6)]}, innen
    hohl = len(qs.umriss) > 1
    if qs.radius and qs.form in opt.RADIUS_FORMEN:
        t = qs.wand
        innen = {"punkte": rund_rechteck(qs.B - 2 * t, qs.H - 2 * t, max(0.0, qs.radius - t))} if hohl else None
        return {"punkte": rund_rechteck(qs.B, qs.H, qs.radius)}, innen

    def kontur(pk):
        return {"punkte": [[round(-u, 6), round(v, 6), 0.0] for u, v in pk]}
    return kontur(qs.umriss[0]), (kontur(qs.umriss[1]) if hohl else None)


# ------------------------------------------------------------------ Enden
def _ebene(punkte):
    """Ebene z = a x + b y + c durch die Punkte (kleinste Quadrate) -> (a, b, c, größte Abweichung) oder None."""
    n = len(punkte)
    if n < 3:
        return None
    sx = sum(p[0] for p in punkte)
    sy = sum(p[1] for p in punkte)
    sz = sum(p[2] for p in punkte)
    sxx = sum(p[0] * p[0] for p in punkte)
    syy = sum(p[1] * p[1] for p in punkte)
    sxy = sum(p[0] * p[1] for p in punkte)
    sxz = sum(p[0] * p[2] for p in punkte)
    syz = sum(p[1] * p[2] for p in punkte)
    m = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]]
    rs = [sxz, syz, sz]

    def det(q):
        return (q[0][0] * (q[1][1] * q[2][2] - q[1][2] * q[2][1]) - q[0][1] * (q[1][0] * q[2][2] - q[1][2] * q[2][0])
                + q[0][2] * (q[1][0] * q[2][1] - q[1][1] * q[2][0]))
    d = det(m)
    if abs(d) < 1e-12:
        return None
    loes = []
    for k in range(3):
        q = [row[:] for row in m]
        for i in range(3):
            q[i][k] = rs[i]
        loes.append(det(q) / d)
    a, b, c = loes
    return a, b, c, max(abs(p[2] - (a * p[0] + b * p[1] + c)) for p in punkte)


def _ende_werkzeug(ring_o, ring_i, s, L, meldungen):
    """Werkzeug, das alles hinter der Schnittkante eines Endes wegnimmt; None, wenn nichts weg muss."""
    soll = 0.0 if s == "a" else L
    alle = ring_o + (ring_i or [])
    if all(abs(p[2] - soll) < 1e-6 for p in alle):
        return None
    eb = _ebene(alle)
    if eb and eb[3] < EBEN_TOL:
        a, b, c, _ = eb
        n = _norm((a, b, -1.0) if s == "a" else (-a, -b, 1.0))
        return dict(art="ebene", p=[0.0, 0.0, round(c, 6)], n=_r(n, 9), name=f"Ende {s.upper()}")
    if not ring_i:
        a, b, c, abw = eb
        meldungen.append(f"Ende {s.upper()}: Schnitt als Ebene angenähert (Abweichung bis {abw:.2f} mm)")
        n = _norm((a, b, -1.0) if s == "a" else (-a, -b, 1.0))
        return dict(art="ebene", p=[0.0, 0.0, round(c, 6)], n=_r(n, 9), name=f"Ende {s.upper()}")
    fern = min(0.0, min(p[2] for p in alle)) - FERN if s == "a" else max(L, max(p[2] for p in alle)) + FERN
    n = Netz()
    k = len(ring_o)
    for o, q in zip(ring_o, ring_i):
        d = _norm(_sub(o, q))
        o2, q2 = _add(o, d, UEBER), _add(q, d, -UEBER)
        for p in (o2, q2, (q2[0], q2[1], fern), (o2[0], o2[1], fern)):
            n.punkt(p)
    for i in range(k):
        j = (i + 1) % k
        for m in range(4):
            n.viereck(4 * i + m, 4 * i + (m + 1) % 4, 4 * j + (m + 1) % 4, 4 * j + m)
    return n.werkzeug(name=f"Ende {s.upper()}")


def _ringe(bau, s, versatz=0.0):
    z = bau["za"] if s == "a" else bau["zb"]
    xyz = rohr3d._xyz
    ring_o = [xyz(z(u, v) + versatz, u, v) for u, v in bau["aussen"]]
    ring_i = [xyz(z(u, v) + versatz, u, v) for u, v in bau["innen"]] if bau["innen"] else None
    return ring_o, ring_i


def ende_werkzeuge(bau, s, meldungen):
    """Werkzeug(e) des Endes s ('a'/'b'); Nasen einer Steckverbindung bleiben stehen."""
    L = bau["L"]
    werkzeug = _ende_werkzeug(*_ringe(bau, s), s, L, meldungen)
    nasen = bau["nasen"].get(s)
    if not nasen or not bau["innen"]:
        return [werkzeug] if werkzeug else []
    # Nasen: der Schnitt liegt um die Flanke weiter innen, die Nasen reichen bis zum Teilende (Spitze)
    plus = bau["plus"][s]
    spitze = _ende_werkzeug(*_ringe(bau, s, -plus if s == "a" else plus), s, L, meldungen)
    lg, winkel, h = nasen
    qs, aussen, innen, cum, T, ort = bau["qs"], bau["aussen"], bau["innen"], bau["cum"], bau["T"], bau["ort"]
    sektoren = []
    for w in winkel:
        pt = sk.naht_punkt(qs, w)
        if pt is None:
            continue
        tc = rohr3d._t_von(aussen, cum, *pt)
        ts = sorted([tc - h] + [c + T * k for k in (-1, 0, 1) for c in cum[:-1] if tc - h < c + T * k < tc + h]
                    + [tc + h])
        rand_o, rand_i = [], []
        for t in ts:
            _, u, v = ort(t, 0.0, aussen)
            _, ui, vi = ort(t, 0.0, innen)
            d = _norm((-(u - ui), v - vi, 0.0))
            rand_o.append(_add((-u, v, 0.0), d, 2 * UEBER))
            rand_i.append(_add((-ui, vi, 0.0), d, -2 * UEBER))
        poly = [[round(p[0], 6), round(p[1], 6), 0.0] for p in rand_o + rand_i[::-1]]
        sektor = dict(art="prisma", punkte=poly, z0=-2 * FERN - lg, z1=L + 2 * FERN + lg, name=f"Nase {w:g}°")
        if spitze:
            sektor["ohne"] = [spitze]
        sektoren.append(sektor)
    if werkzeug is None:            # Schnitt gerade am Teilende: nur über den Nasen hinaus nichts weg
        return []
    if sektoren:
        werkzeug["ohne"] = sektoren
    return [werkzeug]


# ------------------------------------------------------------------ Konturen
def _streifen(poly, t0, t1):
    """Polygon [(t, x)] auf den Streifen t0 ≤ t ≤ t1 beschneiden (Sutherland-Hodgman)."""
    def schneiden(pk, grenze, innen):
        out = []
        for i, a in enumerate(pk):
            b = pk[(i + 1) % len(pk)]
            ia, ib = innen(a), innen(b)
            if ia:
                out.append(a)
            if ia != ib and abs(b[0] - a[0]) > 1e-12:
                f = (grenze - a[0]) / (b[0] - a[0])
                out.append((grenze, a[1] + f * (b[1] - a[1])))
        return out
    pk = schneiden(list(poly), t0, lambda p: p[0] >= t0)
    if pk:
        pk = schneiden(pk, t1, lambda p: p[0] <= t1)
    return _ohne_doppelte(pk)


FLACH_ARTEN = (sw.LANGLOCH, sw.RECHTECK, sw.SCHLITZ)


def _flach_kontur(ein):
    """Kontur (dx längs, dq quer) mit echten Bögen wie skizze.umriss_kontur, oder None (Fase, Umriss, andere Art)."""
    art = ein.get("art")
    if art not in FLACH_ARTEN or ein.get("umriss") or _z(ein.get("fase")) or ein.get("_dx") or ein.get("_dq"):
        return None
    if art == sw.LANGLOCH:
        lg, b = _z(ein.get("l")), _z(ein.get("b"))
        if b <= 0 or lg < b:
            return None
        h, r = (lg - b) / 2, b / 2
        pk = [(-h, -r, 0.0), (h, -r, 1.0), (h, r, 0.0), (-h, r, 1.0)] if h > 1e-6 else None
        if pk is None:
            return {"kreis": [0.0, 0.0, round(r, 6)]}
    else:
        b, h = (_z(ein.get("b")), _z(ein.get("h"))) if art == sw.RECHTECK else (_z(ein.get("l")), _z(ein.get("b")))
        if b <= 0 or h <= 0:
            return None
        pk = [tuple(p) for p in rund_rechteck(b, h, _z(ein.get("r")) if art == sw.RECHTECK else 0.0)]
    w = (90.0 if ein.get("quer") else 0.0) + _z(ein.get("drehung"))
    pk = _gedreht(pk, w)
    if ein.get("spiegeln"):
        pk = [[x, -q, -b] for x, q, b in pk]
    return {"punkte": pk}


def flach_werkzeuge(bau, e):
    """Langloch, Rechteck und Schlitz ganz auf einer ebenen Wand (Quadrat-, Rechteckrohr, Profile): exakt mit
    Bögen, senkrecht durch die Wand. -> (Werkzeuge, Zeilen, die so erledigt sind)."""
    qs, L = bau["qs"], bau["L"]
    if qs.r or not qs.flaechen:
        return [], set()
    tief = (qs.wand if bau["innen"] else qs.H if qs.form == "Flachstahl" else qs.wand or qs.H) + 2 * UEBER
    je_zeile = {}
    for d in sk.lagen(e.get("konturen") or [], L, qs):
        je_zeile.setdefault(d["zeile"], []).append(d)
    out, fertig = [], set()
    for zeile, liste in je_zeile.items():
        stuecke = []
        for d in liste:
            ein = d["eingabe"]
            kontur = _flach_kontur(ein)
            f = qs.flaeche(ein.get("seite")) if kontur else None
            pk = sk.umriss_kontur(ein) if f else None
            if not pk:
                break
            q = _z(ein.get("q"))
            rand = f.breite / 2 - (qs.radius if qs.form in opt.RADIUS_FORMEN else 0.0) - 0.01
            if max(abs(q + dq) for _, dq in pk) > rand:
                break                   # reicht in die Rundung oder über die Kante: Werkzeug je Fläche
            (u0, v0), (u1, v1) = f.punkt(q), f.punkt(q + 1.0)
            n3 = _norm(rohr3d._xyz(0, *f.n))
            y3 = _norm(rohr3d._xyz(0, u1 - u0, v1 - v0))
            x3 = (0.0, 0.0, 1.0)
            o = _add(rohr3d._xyz(d["x"], u0, v0), n3, UEBER)
            if _dot(_kreuz(n3, x3), y3) < 0 and kontur.get("punkte"):     # quer in der Ebene andersherum
                kontur = {"punkte": [[x, -q, -b] for x, q, b in kontur["punkte"]]}
            stuecke.append(dict(art="flach", kontur=kontur, o=_r(o), x=_r(x3, 9), n=_r(n3, 9), h=round(tief, 6),
                                name=f"Kontur {zeile + 1}"))
        else:
            out += stuecke
            fertig.add(zeile)
    return out, fertig


def loch_werkzeuge(bau, e, ohne=()):
    """Werkzeuge der ausgeschnittenen Konturen außer Bohrungen (die sind Zylinder): je Fläche des Umrisses ein Stück,
    radial durch die Wand (wie die 3D-Ansicht)."""
    aussen, innen, cum, T = bau["aussen"], bau["innen"], bau["cum"], bau["T"]
    zeilen = e.get("konturen") or []
    out, vorher = [], None
    for q, zeile in bau["loch_zeile"]:
        if vorher and vorher[1] == zeile and abs(abs(q[0][0] - vorher[0][0][0]) - T) < 1e-6 \
                and abs(q[0][1] - vorher[0][0][1]) < 1e-9:
            continue                    # dieselbe Kontur um den Umfang verschoben (Naht): schon dabei
        vorher = (q, zeile)
        if zeile in ohne or (zeilen[zeile] if zeile < len(zeilen) else {}).get("art") in (BOHRUNG, SENKUNG):
            continue
        q = _ccw(_ohne_doppelte(q))
        if len(q) < 3:
            continue
        t_min, t_max = min(p[0] for p in q), max(p[0] for p in q)
        for i in range(len(aussen)):
            for k in (-1, 0, 1):
                t0, t1 = cum[i] + k * T, cum[i + 1] + k * T
                if t_max <= t0 or t_min >= t1 or t1 - t0 < 1e-9:
                    continue
                stueck = _streifen(q, t0 - STREIFEN_UEBER, t1 + STREIFEN_UEBER)
                if len(stueck) < 3 or abs(_flaeche2(stueck)) < 1e-8:
                    continue
                (u0, v0), (u1, v1) = aussen[i], aussen[(i + 1) % len(aussen)]
                (p0, r0), (p1, r1) = innen[i], innen[(i + 1) % len(innen)]
                oben, unten = [], []
                for t, x in stueck:
                    f = (t - t0) / (t1 - t0)
                    o = rohr3d._xyz(x, u0 + f * (u1 - u0), v0 + f * (v1 - v0))
                    i_ = rohr3d._xyz(x, p0 + f * (p1 - p0), r0 + f * (r1 - r0))
                    d = _norm(_sub(o, i_))
                    oben.append(_add(o, d, UEBER))
                    unten.append(_add(i_, d, -UEBER))
                out.append(prisma_netz(_ccw(stueck), *((oben, unten) if _flaeche2(stueck) > 0 else
                                                       (oben[::-1], unten[::-1]))).werkzeug(
                    name=f"Kontur {zeile + 1}"))
    return out


def vollprofil_werkzeuge(bau, e, ohne=()):
    """Profile ohne Innenwand (Flachstahl, Winkel, U …): Konturen außer Bohrungen senkrecht zur Fläche durch die
    Wand."""
    qs, L = bau["qs"], bau["L"]
    tief = (qs.H if qs.form == "Flachstahl" else 2 * qs.r if qs.r else qs.wand or qs.H) + UEBER
    out = []
    for d in sk.lagen(e.get("konturen") or [], L, qs):
        ein = d["eingabe"]
        if ein.get("art") not in rohr3d.LOCH_ARTEN or ein.get("art") in (BOHRUNG, SENKUNG) or d["zeile"] in ohne:
            continue
        pk2 = sk.umriss_kontur(ein)
        try:
            pts, n_mitte = sk.platzieren(qs, d)
        except (ValueError, TypeError, ZeroDivisionError):
            continue
        if not pk2 or len(pts) != len(pk2) or len(pk2) < 3:
            continue
        n3 = _norm(rohr3d._xyz(0, *n_mitte))
        p3 = [rohr3d._xyz(*p) for p in pts]
        paare = [(a, p) for i, (a, p) in enumerate(zip(pk2, p3)) if math.dist(a, pk2[i - 1]) > 1e-7]
        pk2 = [a for a, _ in paare]
        oben = [_add(p, n3, UEBER) for _, p in paare]
        unten = [_add(p, n3, -tief) for _, p in paare]
        if _flaeche2(pk2) < 0:
            pk2, oben, unten = pk2[::-1], oben[::-1], unten[::-1]
        out.append(prisma_netz(pk2, oben, unten).werkzeug(name=f"Kontur {d['zeile'] + 1}"))
    return out


def bohrungen(bau, e):
    """Bohrungen und Senkungen als echte Zylinder senkrecht zur Wand (Mitte und Ø wie beim Messen)."""
    qs, L = bau["qs"], bau["L"]
    geo = rohr3d.geometrie(e, qs, L)
    tief = (qs.wand if bau["innen"] else qs.H if qs.form == "Flachstahl" else 2 * qs.r if qs.r else qs.wand or qs.H)
    out = []
    for k in geo["kreise"]:
        if geo["merkmale"].get(k["id"], {}).get("art") not in (BOHRUNG, SENKUNG):
            continue
        n = _norm(k["n"])
        out.append(dict(art="zylinder", p=_r(_add(k["m"], n, UEBER)), achse=_r([-c for c in n], 9),
                        r=round(k["d"] / 2, 6), h=round(tief + 2 * UEBER, 6), name=f"Bohrung Ø {k['d']:g}"))
    return out


# ------------------------------------------------------------------ Gravur
def _abstand_strecke(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy or 1.0)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _frei(p, polygone, aussen=None, abstand=GRAVUR_ABSTAND + GRAVUR_BREITE / 2):
    """Punkt p (2D) außerhalb der Polygone und innerhalb aussen, überall mit dem Abstand."""
    if aussen is not None:
        if not rohr3d._innen(p, aussen):
            return False
        if any(_abstand_strecke(p, a, aussen[i - 1]) < abstand for i, a in enumerate(aussen)):
            return False
    for pk in polygone:
        if rohr3d._innen(p, pk) or any(_abstand_strecke(p, a, pk[i - 1]) < abstand for i, a in enumerate(pk)):
            return False
    return True


def _fein(zug):
    """Linienzug [(Punkt, Normale)] so unterteilen, dass kein Stück länger als GRAVUR_SCHRITT ist."""
    out = zug[:1]
    for (a, na), (b, nb) in zip(zug, zug[1:]):
        k = max(1, math.ceil(math.dist(a, b) / GRAVUR_SCHRITT))
        for i in range(1, k + 1):
            f = i / k
            out.append((_add(a, _sub(b, a), f), _norm(_add(na, _sub(nb, na), f))))
    return out


def rillen(zuege, frei):
    """Gravurrillen (Quader) aus Linienzügen [[(Punkt 3D, Normale)]]; frei(Punkt, Normale) prüft den Abstand.
    Gerade Stücke werden zusammengefasst. -> (Werkzeuge, Anzahl gekürzter Stellen)."""
    out, gekuerzt = [], 0
    b = GRAVUR_BREITE
    for zug in zuege:
        lauf = []
        teile = []
        for p, n in _fein(zug):
            if frei(p, n):
                lauf.append((p, n))
            else:
                gekuerzt += 1
                if len(lauf) > 1:
                    teile.append(lauf)
                lauf = []
        if len(lauf) > 1:
            teile.append(lauf)
        for lauf in teile:
            stuecke = []                # zusammengefasst: (Anfang, Ende, Normale)
            for (a, na), (c, nc) in zip(lauf, lauf[1:]):
                if math.dist(a, c) < 1e-6:
                    continue
                n = _norm(_add(na, nc))
                if stuecke:
                    a0, c0, n0 = stuecke[-1]
                    r0, r1 = _norm(_sub(c0, a0)), _norm(_sub(c, a))
                    if _dot(r0, r1) > math.cos(math.radians(0.5)) and _dot(n0, n) > math.cos(math.radians(0.5)):
                        stuecke[-1] = (a0, c, n0)
                        continue
                stuecke.append((a, c, n))
            for a, c, n in stuecke:
                x = _norm(_sub(c, a))
                z = _norm(_sub(n, tuple(x[i] * _dot(n, x) for i in range(3))))
                y = _kreuz(z, x)
                ecke = _add(_add(_add(a, x, -b / 2), y, -b / 2), z, -GRAVUR_TIEFE)
                out.append(dict(art="quader", p=_r(ecke), x=_r(x, 9), z=_r(z, 9), l=round(math.dist(a, c) + b, 6),
                                b=b, h=round(GRAVUR_TIEFE + GRAVUR_UEBER, 6)))
    return out, gekuerzt


def _rohr_gravur_zuege(qs, e, L):
    """Gravuren auf der Außenwand als Linienzüge [[(Punkt, Normale)]] in Koordinaten der 3D-Ansicht."""
    out = []
    for d in sk.lagen(e.get("konturen") or [], L, qs):
        ein = d["eingabe"]
        art = ein.get("art")
        if art not in GRAVUREN:
            continue
        if art == TEXT_GRAVUR and not ein.get("umriss"):
            striche = gravur_text.gedreht(gravur_text.linien(ein.get("text"), _z(ein.get("hoehe"))), ein.get("winkel"))
            zuege = [[(x, -y) for x, y in s] for s in striche]          # von außen lesbar wie im 3D
            geschlossen = False
        elif ein.get("umriss"):
            zuege, geschlossen = [None], True
        else:
            continue                    # Gravur ohne Umriss: nur Länge, keine Lage
        for zug in zuege:
            try:
                pts, n_mitte = sk.platzieren(qs, d, zug)
                ns = sk.normalen(qs, d) if zug is None else None
            except (ValueError, TypeError, ZeroDivisionError):
                continue
            linie = []
            for i, (x, u, v) in enumerate(pts):
                if qs.r:
                    r = math.hypot(u, v) or 1.0
                    n = (u / r, v / r)
                else:
                    n = ns[i] if ns and i < len(ns) else n_mitte
                linie.append((rohr3d._xyz(x, u, v), _norm(rohr3d._xyz(0, *n))))
            if geschlossen and len(linie) > 2:
                linie.append(linie[0])
            if len(linie) > 1:
                out.append(linie)
    return out


def artikel_gravur(qs, e, L, artikel, h):
    """Zeile Text-Gravur für die Artikelnummer (positionen.bg_gravur) auf der ersten Seite, längs, dort mit dem
    größten Abstand zu Enden und Konturen dieser Seite; None, wenn kein Platz ist."""
    if not artikel or h <= 0:
        return None
    seite = qs.seiten()[0]
    breite = gravur_text.masse(artikel, h)[0]
    belegt = []
    for d in sk.lagen(e.get("konturen") or [], L, qs):
        ein = d["eingabe"]
        if (ein.get("seite") or seite) != seite and ein.get("art") not in (sw.AUSKLINKUNG,):
            continue
        pk = sk.umriss_kontur(ein) or [(0.0, 0.0)]
        belegt.append((d["x"] + min(p[0] for p in pk), d["x"] + max(p[0] for p in pk)))
    platz = gravur_text.lage_laengs(L, belegt, breite + 2 * GRAVUR_ABSTAND)
    if not platz:
        return None
    return {"art": TEXT_GRAVUR, "text": artikel, "hoehe": h, "x": round(platz[0], 3), "seite": seite, "q": 0,
            "winkel": 0, "anzahl": 1}


# ------------------------------------------------------------------ Teile
def rohr_teil(e, profil, laenge, name="Teil", naht_winkel=None, grenze=None, nasen_winkel=None, artikel=None,
              gravur_h=0.0):
    """Bauplan eines Rohrs aus den Eingaben des Rohr-Editors (wie rohr3d.netz). ValueError ohne Länge/Profil."""
    e = dict(e or {})
    meldungen = []
    if artikel and _z(gravur_h) > 0:
        qs0 = sk.Querschnitt(sw.mit_radius(profil, e))
        z = artikel_gravur(qs0, e, _z(laenge), str(artikel), _z(gravur_h))
        if z:
            e["konturen"] = list(e.get("konturen") or []) + [z]
        else:
            meldungen.append("Artikelnummer-Gravur: kein Platz mit 0,5 mm Abstand, nicht graviert")
    bau = {}
    if not rohr3d.netz(e, profil, laenge, naht_winkel, grenze, nasen_winkel, bau=bau):
        raise ValueError("Rohr: Länge oder Querschnitt fehlt.")
    qs, L = bau["qs"], bau["L"]
    aussen_k, innen_k = querschnitt(qs)
    werkzeuge = ende_werkzeuge(bau, "a", meldungen) + ende_werkzeuge(bau, "b", meldungen)
    werkzeuge += bohrungen(bau, e)
    flach, fertig = flach_werkzeuge(bau, e)
    werkzeuge += flach + (loch_werkzeuge(bau, e, fertig) if bau["innen"] else vollprofil_werkzeuge(bau, e, fertig))
    loecher = [q for q, _ in bau["loch_zeile"]]
    abstand = GRAVUR_ABSTAND + GRAVUR_BREITE / 2

    def frei(p, n):
        x, u, v = p[2], -p[0], p[1]
        if x - bau["za"](u, v) < abstand or bau["zb"](u, v) - x < abstand:
            return False
        if not loecher:
            return True
        t = rohr3d._t_von(bau["aussen"], bau["cum"], u, v)
        return _frei((t, x), loecher)
    gravur, gekuerzt = rillen(_rohr_gravur_zuege(qs, e, L), frei)
    if gekuerzt:
        meldungen.append(f"Gravur an {gekuerzt} Stellen gekürzt (mindestens 0,5 mm Abstand zu Enden und Konturen)")
    return dict(name=str(name or "Teil"), koerper=dict(art="rohr", laenge=round(L, 6), aussen=aussen_k,
                                                       innen=innen_k),
                werkzeuge=werkzeuge, rillen=gravur, meldungen=meldungen)


def _blech_loch(z, cx, cy):
    """Innenkontur eines Blechs als Kontur des Bauplans mit echten Bögen oder None (Gravur, unbekannt)."""
    art = z.get("art")
    w = blech.drehung(z)
    if art in (BOHRUNG, SENKUNG):
        d = _z(z.get("d"))
        return {"kreis": [round(cx, 6), round(cy, 6), round(d / 2, 6)]} if d > 0 else None
    if art == sw.LANGLOCH:
        lg, b = _z(z.get("l")), _z(z.get("b"))
        if b <= 0 or lg < b:
            return None
        if lg - b < 1e-6:
            return {"kreis": [round(cx, 6), round(cy, 6), round(b / 2, 6)]}
        h, r = (lg - b) / 2, b / 2
        pk = [(-h, -r, 0.0), (h, -r, 1.0), (h, r, 0.0), (-h, r, 1.0)]
        return {"punkte": _gedreht(pk, w + (90 if z.get("quer") else 0), cx, cy)}
    if art == sw.RECHTECK:
        b, h = _z(z.get("b")), _z(z.get("h"))
        if b <= 0 or h <= 0:
            return None
        return {"punkte": rund_rechteck(b, h, _z(z.get("r")), cx, cy, w)}
    if art == sw.POLYGON:
        try:
            roh, pk = sw.punkte_roh(z.get("punkte")), sw.punkte(z.get("punkte"))
        except ValueError:
            return None
        if len(roh) < 3 or len(pk) < 3:
            return None
        mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
        return {"punkte": _gedreht([(x - mx, y - my, b) for x, y, b in roh], w, cx, cy)}
    return None


def blech_teil(e, zs, name="Teil"):
    """Bauplan eines ebenen Blechs aus den Eingaben des Blech-Editors und dem Zuschnitt (blech.zuschnitt).
    ValueError bei gekanteten Blechen (noch nicht) oder ohne Maße."""
    if not zs:
        raise ValueError("Blech: Maße fehlen.")
    if zs.get("biegungen") or e.get("biegelinien") or e.get("art") == blech.KANTTEIL:
        raise ValueError("Gekantete Bleche kann der STEP-Export noch nicht, nur ebene Bleche.")
    s = _z(e.get("dicke"))
    if s <= 0:
        raise ValueError("Blech: Dicke fehlt.")
    meldungen = []
    if zs.get("punkte"):
        minx = min(float(x) for x, _ in zs["punkte"])
        miny = min(float(y) for _, y in zs["punkte"])
        try:
            roh = sw.punkte_roh(e.get("punkte")) if e.get("form") == blech.POLYGON else []
        except ValueError:
            roh = []
        if len(roh) < 3:
            roh = [(float(x), float(y), 0.0) for x, y in zs["punkte"]]
        aussen_k = {"punkte": [[round(x - minx, 6), round(y - miny, 6), round(b, 9)] for x, y, b in roh]}
    else:
        lg, br = zs["laenge"], zs["breite"]
        aussen_k = {"punkte": rund_rechteck(lg, br, _z(e.get("eckradius")), lg / 2, br / 2)}
    loecher, belegt = [], []
    for z, cx, cy in blech3d.kontur_mitten(e, zs):
        if z.get("art") in GRAVUREN:
            continue
        k = _blech_loch(z, cx, cy)
        if k:
            loecher.append(k)
        elif z.get("art") not in (sw.FLOWDRILL, sw.SONSTIGE):
            meldungen.append(f"Kontur {z.get('art')}: nicht im STEP (nur ebene Innenkonturen)")
    for z, zug in blech3d.konturzuege(e, zs):
        if z.get("art") not in GRAVUREN and len(zug) >= 3:
            belegt.append(_ohne_doppelte(zug))
    aussen = blech3d.aussenkontur(e, zs)
    zuege = []
    for z, zug in blech3d.konturzuege(e, zs):
        if z.get("art") in GRAVUREN and (z.get("art") == TEXT_GRAVUR or z.get("linien")):
            zuege.append([((x, y, s), (0.0, 0.0, 1.0)) for x, y in zug])
    gravur, gekuerzt = rillen(zuege, lambda p, n: _frei(p[:2], belegt, aussen))
    if gekuerzt:
        meldungen.append(f"Gravur an {gekuerzt} Stellen gekürzt (mindestens 0,5 mm Abstand zu Rand und Konturen)")
    return dict(name=str(name or "Teil"), koerper=dict(art="platte", dicke=s, aussen=aussen_k, loecher=loecher),
                werkzeuge=[], rillen=gravur, meldungen=meldungen)


def teilname(p):
    """Name des Teils in der STEP-Datei: Artikelnummer, sonst Pos."""
    return str(p.get("artikel") or "").strip() or f"Pos {p.get('pos') or ''}".strip()


# ------------------------------------------------------------------ Schreiben
def befehl(programmordner):
    """Befehl für den STEP-Export (Liste für subprocess, ohne Dateien) oder None, wenn er nicht verfügbar ist."""
    exe = Path(programmordner or ".") / "STEP-Import" / "STEP-Import.exe"
    if exe.is_file():
        return [str(exe)]
    if not getattr(sys, "frozen", False):
        skript = Path(__file__).resolve().parents[1] / "step_messung" / "step_schreiben.py"
        if skript.is_file() and find_spec("OCP") is not None:
            return [sys.executable, str(skript)]
    return None


def schreiben(teile, ziel, programmordner=None, name=None, zeitlimit=ZEITLIMIT):
    """Teile (Baupläne) als STEP-Datei ziel schreiben -> Ergebnis dict(ok, teile, fehler, meldungen).
    Die Meldungen der Baupläne (gekürzte Gravur, …) stehen mit im Ergebnis."""
    b = befehl(programmordner)
    if b is None:
        return dict(ok=False, fehler="Der STEP-Export braucht STEP-Import.exe im Programmordner.", teile=[],
                    meldungen=[])
    meldungen = [m for t in teile for m in t.get("meldungen") or ()]
    with tempfile.TemporaryDirectory() as tmp:
        plan, erg = Path(tmp) / "bauplan.json", Path(tmp) / "ergebnis.json"
        plan.write_text(json.dumps(dict(name=name, teile=teile)), encoding="utf-8")
        if b[0].lower().endswith(".exe"):
            cmd = b + ["--export", str(plan), "--step", str(ziel), "--ergebnis", str(erg)]
        else:
            cmd = b + [str(plan), str(ziel), str(erg)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=zeitlimit,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            return dict(ok=False, fehler=f"STEP-Export nach {zeitlimit} s abgebrochen.", teile=[], meldungen=meldungen)
        except OSError as ex:
            return dict(ok=False, fehler=f"STEP-Export nicht gestartet: {ex}", teile=[], meldungen=meldungen)
        try:
            ergebnis = json.loads(erg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ergebnis = dict(ok=False, fehler="STEP-Export ohne Ergebnis beendet.", teile=[])
    ergebnis["meldungen"] = meldungen + [m for t in ergebnis.get("teile") or () for m in t.get("meldungen") or ()]
    return ergebnis


def ergebnis_text(erg, ziel=None):
    """Kurzer Text für die Meldung nach dem Export."""
    if not erg.get("teile") or erg.get("fehler"):
        return f"STEP nicht geschrieben: {erg.get('fehler') or 'unbekannter Fehler'}"
    t = erg["teile"][0]
    text = f"STEP gespeichert{f': {Path(ziel).name}' if ziel else ''} (Volumen {t['volumen'] / 1000:.1f} cm³, " \
           f"{t['flaechen']} Flächen)"
    if not erg.get("ok"):
        text += "\nAchtung: Die Prüfung des Volumenkörpers meldet Fehler, bitte im CAD kontrollieren."
    if erg.get("meldungen"):
        text += "\n" + "\n".join(f"• {m}" for m in erg["meldungen"])
    return text


# ------------------------------------------------------------------ Bedienung (Rohr- und Blech-Editor)
def programmordner_von(widget):
    """Programmordner (dort liegt STEP-Import.exe) über die Fenster des Programms, sonst wie beim Start."""
    w = widget
    while w is not None:
        for kandidat in (w, getattr(w, "f", None)):
            if kandidat is not None and getattr(kandidat, "programmordner", None):
                return kandidat.programmordner
        w = w.parent() if hasattr(w, "parent") else None
    from .__main__ import programmordner
    return programmordner()


def vorschlag(widget, name):
    """Vorschlag für den Dateinamen: im Ordner des Angebots (wie Zeichnung als PDF), sonst nur der Name."""
    seite = widget.parent() if hasattr(widget, "parent") else None
    if hasattr(seite, "_ziel"):
        pfad = seite._ziel(name, ".step")
        if pfad is not None:
            return str(pfad)
    return "".join(c if c.isalnum() or c in " -_,." else "_" for c in name).strip() + ".step"


def speichern_dialog(widget, bauplan, name, pfad=None):
    """Ziel wählen (Dateidialog mit Vorschlag), Bauplan als STEP schreiben und das Ergebnis melden. Ergebnis: Pfad
    oder None. widget.step_ergebnis = Ergebnis des Exports (für Tests)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    if pfad is None:
        pfad, _ = QFileDialog.getSaveFileName(widget, "STEP speichern", vorschlag(widget, name),
                                              "STEP-Datei (*.step *.stp)")
        if not pfad:
            return None
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        erg = schreiben([bauplan], pfad, programmordner_von(widget), name=bauplan.get("name"))
    finally:
        QApplication.restoreOverrideCursor()
    widget.step_ergebnis = erg
    gut = bool(erg.get("teile")) and not erg.get("fehler")
    if not getattr(widget, "stumm", False):
        (QMessageBox.information if gut else QMessageBox.warning)(widget, "STEP speichern", ergebnis_text(erg, pfad))
    return pfad if gut else None
