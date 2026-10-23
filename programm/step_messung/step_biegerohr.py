"""Biegerohre (Plan S9, Abschnitt 5.4): gebogene Rundrohre aus Zylindern (Geraden) und Torusflächen (Bögen).

Erkennung: mindestens ein Torus, dessen kleiner Radius dem Außenradius der Zylinder entspricht, und ein Biegeradius
größer als der Rohrradius (eine Ausrundung an einer Schweißnaht hat einen kleineren Querschnittsradius). Die
Mittellinie entsteht aus den Achsen der Außenzylinder (Geraden) und den Mittenkreisen der Tori (Bögen), verkettet über
gemeinsame Endpunkte. Gemessen wird auf der Mittellinie (Faktor neutrale Faser 1,0); das Programm rechnet die
gestreckte Länge mit seinem Faktor um (biegerohr.gestreckt).

Ergebnis: Teil wie ein gerades Rundrohr mit der Länge der Mittellinie, Konturen mit z = Lage auf der Mittellinie
ab Ende A (also am gestreckten Rohr) und Winkel um die Rohrachse (0° = Innenseite der ersten Biegung, mitgeführt
ohne Verdrehung), dazu t.biegerohr = {mittellinie, elemente, lra, xyz}. Prüfstatus immer „prüfen“."""
import math

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Torus
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt

import step_geometrie as g

TOL_R = 0.02            # mm: gleicher Radius
TOL_KETTE = 0.5         # mm: Endpunkte zweier Elemente gelten als verbunden
HINWEIS = "Biegerohr"


# ------------------------------------------------------------------ Vektoren (Tupel)
def _add(a, b, k=1.0):
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _betrag(a):
    return math.sqrt(_dot(a, a))


def _einheit(a):
    n = _betrag(a) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def _drehen(v, achse, w):
    """v um die Einheitsachse achse um w (Bogenmaß) drehen (Rodrigues)."""
    c, s = math.cos(w), math.sin(w)
    kv = _kreuz(achse, v)
    d = _dot(achse, v) * (1 - c)
    return tuple(v[i] * c + kv[i] * s + achse[i] * d for i in range(3))


def _t(p):
    return (p.X(), p.Y(), p.Z())


# ------------------------------------------------------------------ Flächen
def _flaechen(solid):
    """Alle Flächen mit Art: ('Z', Radius, Achspunkt, Richtung, v0, v1) bzw. ('T', kleiner R, Mitte, Achse, X, Y,
    Biegeradius, u0, u1) bzw. None."""
    faces = g.TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(solid, TopAbs_FACE, faces)
    daten = {}
    for i in range(1, faces.Extent() + 1):
        f = TopoDS.Face(faces.FindKey(i))
        z = g._zylinder(f)
        u0, u1, v0, v1 = BRepTools.UVBounds_s(f)
        if z is not None:
            ax = z.Axis()
            daten[i] = ("Z", z.Radius(), _t(ax.Location()), _t(ax.Direction()), v0, v1)
            continue
        sf = BRepAdaptor_Surface(f)
        if sf.GetType() == GeomAbs_Torus:
            tor = sf.Torus()
            p = tor.Position()
            daten[i] = ("T", tor.MinorRadius(), _t(p.Location()), _t(p.Direction()), _t(p.XDirection()),
                        _t(p.YDirection()), tor.MajorRadius(), u0, u1)
    return faces, daten


def ist_biegerohr(daten):
    """Außenradius, wenn die Flächen ein Biegerohr ergeben, sonst None: der größte Querschnittsradius der Tori ist
    der größte Radius überhaupt (Außenmantel) und mindestens ein solcher Torus hat einen größeren Biegeradius."""
    tori = [d for d in daten.values() if d[0] == "T"]
    if not tori:
        return None
    ra = max(d[1] for d in tori)
    if any(d[0] == "Z" and d[1] > ra + TOL_R for d in daten.values()):
        return None         # größerer Zylinder: der Torus ist eine Ausrundung, kein Rohrbogen
    if not any(abs(d[1] - ra) < TOL_R and d[6] > ra + TOL_R for d in tori):
        return None
    return ra


def _gleich_linie(a, b):
    """Zwei Zylinderachsen (Punkt, Richtung) auf derselben Geraden?"""
    if abs(abs(_dot(a[1], b[1])) - 1) > 1e-6:
        return False
    w = _sub(b[0], a[0])
    return _betrag(_kreuz(w, a[1])) < 0.05


def _intervalle(liste, tol=0.1):
    """Vereinigung von Intervallen [(a, b)] -> zusammenhängende [(a, b)]."""
    out = []
    for a, b in sorted(liste):
        if out and a <= out[-1][1] + tol:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _ring_intervalle(iv, tol=1e-3):
    """Winkelbereiche [(u0, u1)] eines Torus vereinigen, auch über die Naht bei 0 = 2π (ein Bogen aus zwei
    Flächen beiderseits der Naht ist ein Bogen)."""
    voll = 2 * math.pi
    out = _intervalle([(a % voll, a % voll + (b - a)) for a, b in iv], tol)
    if len(out) > 1 and out[0][0] < tol and out[-1][1] > voll - tol:
        out = [(out[-1][0], out[0][1] + voll)] + out[1:-1]
        out = _intervalle(out, tol)
    return out


def _elemente(daten, ra):
    """Geraden und Bögen der Mittellinie (unverkettet): dict(art, a, b (Endpunkte), …)."""
    linien = []     # [(Punkt, Richtung), [(v0, v1)]]
    boegen = []     # [(Mitte, Achse, X, Y, R), [(u0, u1)]]
    for d in daten.values():
        if abs(d[1] - ra) >= TOL_R:
            continue
        if d[0] == "Z":
            _, _, p, r, v0, v1 = d
            for ln in linien:
                if _gleich_linie(ln[0], (p, r)):
                    k = _dot(_sub(p, ln[0][0]), ln[0][1])
                    s = 1 if _dot(r, ln[0][1]) > 0 else -1
                    ln[1].append(tuple(sorted((k + s * v0, k + s * v1))))
                    break
            else:
                linien.append([(p, r), [(v0, v1)]])
        elif d[6] > ra + TOL_R:
            _, _, c, n, x, y, rb, u0, u1 = d
            for bg in boegen:
                c2, n2, x2, y2, r2 = bg[0]
                if _betrag(_sub(c, c2)) < 0.05 and abs(r2 - rb) < TOL_R and abs(abs(_dot(n, n2)) - 1) < 1e-6:
                    # u im System des ersten Torus: Winkel von X2 nach X (um n2)
                    w = math.atan2(_dot(_kreuz(x2, x), n2), _dot(x2, x))
                    s = 1 if _dot(n, n2) > 0 else -1
                    a_, b_ = sorted((w + s * u0, w + s * u1))
                    bg[1].append((a_, b_))
                    break
            else:
                boegen.append([(c, n, x, y, rb), [(u0, u1)]])
    out = []
    for (p, r), iv in linien:
        for a, b in _intervalle(iv):
            out.append(dict(art="gerade", a=_add(p, r, a), b=_add(p, r, b), laenge=b - a))
    for (c, n, x, y, rb), iv in boegen:
        for a, b in _ring_intervalle(iv):
            if b - a > 2 * math.pi - 1e-3:
                return None             # geschlossener Ring, kein Rohrbogen
            pa = _add(c, _add(tuple(rb * math.cos(a) * v for v in x), tuple(rb * math.sin(a) * v for v in y)))
            pb = _add(c, _add(tuple(rb * math.cos(b) * v for v in x), tuple(rb * math.sin(b) * v for v in y)))
            out.append(dict(art="bogen", a=pa, b=pb, mitte=c, achse=n, x=x, y=y, radius=rb, u0=a, u1=b,
                            winkel=math.degrees(b - a), laenge=rb * (b - a)))
    return out


def _kette(elemente):
    """Elemente zur Mittellinie verketten (Ende A = freies Ende); je Element 'umgekehrt' (b -> a durchlaufen).
    None, wenn sich keine eindeutige Kette ergibt."""
    def frei(e, p):
        return not any(f is not e and min(_betrag(_sub(p, f["a"])), _betrag(_sub(p, f["b"]))) < TOL_KETTE
                       for f in elemente)
    start = [(e, "a") for e in elemente if frei(e, e["a"])] + [(e, "b") for e in elemente if frei(e, e["b"])]
    if len(start) != 2:
        return None
    # Ende A: das freie Ende einer Geraden mit kleinerer Koordinate (stabil), sonst das erste
    start.sort(key=lambda t: (t[0]["art"] != "gerade", tuple(round(v, 3) for v in t[0][t[1]])))
    e, seite = start[0]
    kette, rest = [], [f for f in elemente if f is not e]
    while True:
        kette.append(dict(e, umgekehrt=seite == "b"))
        ende = e["a"] if seite == "b" else e["b"]
        weiter = [(f, s) for f in rest for s in ("a", "b") if _betrag(_sub(ende, f[s])) < TOL_KETTE]
        if not weiter:
            break
        if len(weiter) > 1:
            return None
        e, seite = weiter[0]
        rest.remove(e)
    return kette if not rest else None


# ------------------------------------------------------------------ Mittellinie
class Mittellinie:
    """Verkettete Mittellinie mit Bogenlänge s ab Ende A, Tangente und mitgeführtem Bezug (Winkel 0°)."""

    def __init__(self, kette):
        self.teile = []
        s = 0.0
        for e in kette:
            p0, p1 = (e["b"], e["a"]) if e["umgekehrt"] else (e["a"], e["b"])
            d = dict(e, p0=p0, p1=p1, s0=s, s1=s + e["laenge"])
            if e["art"] == "gerade":
                d["t"] = _einheit(_sub(p1, p0)) if e["laenge"] > 1e-9 else None
            else:
                n = e["achse"] if not e["umgekehrt"] else tuple(-v for v in e["achse"])
                d["n"] = n          # Drehachse in Laufrichtung (rechte Hand)
                d["t0"] = _einheit(_kreuz(n, _sub(p0, e["mitte"])))
                d["t1"] = _einheit(_kreuz(n, _sub(p1, e["mitte"])))
            self.teile.append(d)
            s = d["s1"]
        self.laenge = s
        for i, d in enumerate(self.teile):      # Geraden der Länge 0 übernehmen die Tangente des Nachbarn
            if d["art"] == "gerade" and d["t"] is None:
                nb = self.teile[i + 1] if i + 1 < len(self.teile) else self.teile[i - 1]
                d["t"] = nb.get("t0") or nb.get("t")
        erste = self.tangente_anfang()
        bogen = next((d for d in self.teile if d["art"] == "bogen"), None)
        x0 = _sub(bogen["mitte"], bogen["p0"]) if bogen else (1.0, 0.0, 0.0)
        x0 = _sub(x0, tuple(_dot(x0, erste) * v for v in erste))
        if _betrag(x0) < 1e-9:
            x0 = _kreuz(erste, (0.0, 0.0, 1.0)) if abs(erste[2]) < 0.9 else _kreuz(erste, (1.0, 0.0, 0.0))
        self.x0 = _einheit(x0)
        x = self.x0
        for d in self.teile:            # Bezug ohne Verdrehung mitführen
            d["x0"] = x
            if d["art"] == "bogen":
                x = _drehen(x, d["n"], math.radians(d["winkel"]))
            d["x1"] = x

    def auf_gerade(self, p, r):
        """Liegt die Achse (Punkt p, Richtung r) auf einer Geraden der Mittellinie?"""
        return any(d["art"] == "gerade" and abs(abs(_dot(r, d["t"])) - 1) < 1e-6 and
                   _betrag(_kreuz(_sub(p, d["p0"]), d["t"])) < 0.05 for d in self.teile)

    def tangente_anfang(self):
        d = self.teile[0]
        return d["t"] if d["art"] == "gerade" else d["t0"]

    def tangente_ende(self):
        d = self.teile[-1]
        return d["t"] if d["art"] == "gerade" else d["t1"]

    def projektion(self, p):
        """Nächster Punkt der Mittellinie: (s, Abstand, Winkel um die Achse in Grad, Teil)."""
        best = None
        for d in self.teile:
            if d["art"] == "gerade":
                k = max(0.0, min(d["laenge"], _dot(_sub(p, d["p0"]), d["t"])))
                q, t, x = _add(d["p0"], d["t"], k), d["t"], d["x0"]
                s = d["s0"] + k
            else:
                c, n = d["mitte"], d["n"]
                r0 = _einheit(_sub(d["p0"], c))
                v = _sub(p, c)
                v = _sub(v, tuple(_dot(v, n) * a for a in n))
                w = math.atan2(_dot(_kreuz(r0, v), n), _dot(r0, v)) if _betrag(v) > 1e-9 else 0.0
                phi = math.radians(d["winkel"])
                if w < 0 or w > phi:
                    w = 0.0 if (w < 0 and w > -(2 * math.pi - phi) / 2) or w > phi + (2 * math.pi - phi) / 2 \
                        else phi
                rw = _drehen(r0, n, w)
                q = _add(c, rw, d["radius"])
                t = _kreuz(n, rw)
                x = _drehen(d["x0"], n, w)
                s = d["s0"] + d["radius"] * w
            r = _sub(p, q)
            ab = _betrag(r)
            if best is None or ab < best[1] - 1e-9:
                y = _kreuz(t, x)
                winkel = math.degrees(math.atan2(_dot(r, y), _dot(r, x))) % 360 if ab > 1e-9 else 0.0
                best = (s, ab, winkel, d)
        return best

    def lra(self):
        """Biegedaten: [{gerade (vor der Biegung), drehung, winkel, radius}] und die Gerade nach der letzten
        Biegung als letzte Zeile (drehung/winkel 0)."""
        out, gerade, n_alt = [], 0.0, None
        for d in self.teile:
            if d["art"] == "gerade":
                gerade += d["laenge"]
                continue
            n = d["n"]
            dreh = 0.0
            if n_alt is not None:
                t = d["t0"]
                dreh = math.degrees(math.atan2(_dot(t, _kreuz(n_alt, n)), _dot(n_alt, n)))
            out.append(dict(gerade=round(gerade, 2), drehung=round(dreh, 2) + 0.0, winkel=round(d["winkel"], 2),
                            radius=round(d["radius"], 2)))
            gerade, n_alt = 0.0, n
        out.append(dict(gerade=round(gerade, 2), drehung=0.0, winkel=0.0, radius=None))
        return out

    def xyz(self):
        """Eckpunkte des Polygonzugs aus den verlängerten Geraden (Schnittpunkte der Tangenten), Anfang und Ende."""
        pts = [self.teile[0]["p0"]]
        for d in self.teile:
            if d["art"] == "bogen":
                h = d["radius"] * math.tan(math.radians(d["winkel"]) / 2)
                pts.append(_add(d["p0"], d["t0"], h))
        pts.append(self.teile[-1]["p1"])
        return pts


# ------------------------------------------------------------------ Messung
def messen(solid, datei="", koerper=1, netz=False):
    """Teil (step_geometrie.Teil) für ein Biegerohr oder None (kein Biegerohr bzw. nicht verkettbar)."""
    faces, daten = _flaechen(solid)
    ra = ist_biegerohr(daten)
    if ra is None:
        return None
    elemente = _elemente(daten, ra)
    if not elemente or not any(e["art"] == "bogen" for e in elemente):
        return None
    kette = _kette(elemente)
    if kette is None:
        return None
    ml = Mittellinie(kette)
    # Innenradius: Zylinder bzw. Tori gleicher Achse mit kleinerem Radius (häufigster Wert)
    innen_r = {}
    for d in daten.values():
        if d[1] < ra - TOL_R and (d[0] == "T" and d[6] > ra or d[0] == "Z"):
            if d[0] == "Z" and not ml.auf_gerade(d[2], d[3]):
                continue        # Zylinder außerhalb der Mittellinie: Bohrung o. ä.
            if d[0] == "T" and not any(b["art"] == "bogen" and _betrag(_sub(d[2], b["mitte"])) < 0.05
                                       for b in ml.teile):
                continue
            innen_r[round(d[1], 3)] = innen_r.get(round(d[1], 3), 0) + 1
    ri = max(innen_r, key=lambda r: (innen_r[r], r)) if innen_r else 0.0
    t = g.Teil(datei=datei, koerper=koerper)
    t.profilform = "Rundrohr" if ri > 0 else "Rundstahl"
    t.bauteiltyp = "Profil"
    t.abm_a = round(2 * ra, 3)
    t.wandstaerke = round(ra - ri, 3) if ri > 0 else 0.0
    t.innen_a = round(2 * ri, 3) if ri > 0 else 0.0
    t.flaeche = math.pi * (ra * ra - ri * ri)
    t.laenge = ml.laenge
    t.achse_global = ml.tangente_anfang()
    t.ende_a_global = ml.teile[0]["p0"]
    t.x_global = ml.x0
    t.kammern = 1 if ri > 0 else 0
    t.kontur_umfang = 2 * math.pi * ra
    _konturen(t, solid, faces, daten, ra, ri, ml)
    boegen = [d for d in ml.teile if d["art"] == "bogen"]
    lra = ml.lra()
    ax = gp_Ax3(gp_Pnt(*ml.teile[0]["p0"]), gp_Dir(*ml.tangente_anfang()), gp_Dir(*ml.x0))
    lokal = _lokal(ax)
    t.biegerohr = dict(
        mittellinie=round(ml.laenge, 2), aussen_d=round(2 * ra, 3),
        elemente=[dict(art=d["art"], s0=round(d["s0"], 2), s1=round(d["s1"], 2), laenge=round(d["laenge"], 2),
                       **(dict(radius=round(d["radius"], 2), winkel=round(d["winkel"], 2)) if d["art"] == "bogen"
                          else {})) for d in ml.teile],
        lra=lra, xyz=[[round(v, 2) + 0.0 for v in lokal(p)] for p in ml.xyz()])
    t.hinweise.append(f"{HINWEIS}: {len(boegen)} Biegung(en), Länge auf der Mittellinie {ml.laenge:.1f} mm "
                      "(gestreckt), Biegedaten und Konturen prüfen")
    t.sicherheit.update(profil="sicher", laenge="wahrscheinlich", wandstaerke="sicher" if ri > 0 else "unsicher",
                        achse="sicher", biegerohr="wahrscheinlich")
    if netz:
        try:
            lok = g._transformiere(solid, ax)
            fl = g.TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(lok, TopAbs_FACE, fl)
            t.netz = g.dreiecksnetz(lok, fl, {i: "A" for i in range(1, fl.Extent() + 1)}, [], 0.0, t.abm_a)
        except Exception:  # 3D-Ansicht darf die Messung nie verhindern
            t.netz = None
    return t


def _lokal(ax):
    o, x, y, z = _t(ax.Location()), _t(ax.XDirection()), _t(ax.YDirection()), _t(ax.Direction())
    return lambda p: (_dot(_sub(p, o), x), _dot(_sub(p, o), y), _dot(_sub(p, o), z))


def _konturen(t, solid, faces, daten, ra, ri, ml):
    """Enden und Innenkonturen: Schnittflächen (weder Außen- noch Innenmantel) mit ihren Kanten auf dem Außenmantel;
    ein Konturzug um die Mittellinie ist ein Ende, einer auf der Wand eine Innenkontur."""
    from rohrlaser import dreid

    def art(i):
        d = daten.get(i)
        if d and abs(d[1] - ra) < TOL_R and (d[0] == "Z" or d[6] > ra):
            return "A"
        if d and ri > 0 and abs(d[1] - ri) < TOL_R and (d[0] == "T" and d[6] > ra or d[0] == "Z"):
            return "I"
        return "S"
    arten = {i: art(i) for i in range(1, faces.Extent() + 1)}
    # Innenmantel-Zylinder, die nicht auf der Mittellinie liegen (Bohrung Ø = Innen-Ø), sind Schnittflächen
    for i, a_ in arten.items():
        d = daten.get(i)
        if a_ != "S" and d and d[0] == "Z" and not ml.auf_gerade(d[2], d[3]):
            arten[i] = "S"
    kf = g.TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(solid, TopAbs_EDGE, TopAbs_FACE, kf)
    vmap = g.TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(solid, TopAbs_VERTEX, vmap)
    eltern = {}

    def finde(x):
        while eltern.setdefault(x, x) != x:
            eltern[x] = eltern[eltern[x]]
            x = eltern[x]
        return x
    info = []
    for i in range(1, kf.Extent() + 1):
        fi = {faces.FindIndex(f) for f in kf.FindFromIndex(i)}
        info.append((kf.FindKey(i), fi))
        s_ = [f for f in fi if arten.get(f) == "S"]
        for f in s_:
            eltern[finde(f)] = finde(s_[0])
    merkmale = {}
    for f, a_ in arten.items():
        if a_ == "S":
            merkmale.setdefault(finde(f), dict(faces=[], kanten=[], durch=False))["faces"].append(f)
    for e, fi in info:
        a_ = {arten.get(f) for f in fi}
        for f in fi:
            if arten.get(f) == "S":
                m = merkmale[finde(f)]
                if "A" in a_:
                    m["kanten"].append(e)
                if "I" in a_ or ri <= 0:
                    m["durch"] = True

    def zuege(kanten):
        ve = {}

        def fv(x):
            while ve.setdefault(x, x) != x:
                ve[x] = ve[ve[x]]
                x = ve[x]
            return x
        for e in kanten:
            vs = [vmap.FindIndex(v) for v in g._liste(e, TopAbs_VERTEX)]
            for v in vs:
                ve[fv(v)] = fv(vs[0])
        out = {}
        for e in kanten:
            out.setdefault(fv(vmap.FindIndex(g._liste(e, TopAbs_VERTEX)[0])), []).append(e)
        return list(out.values())

    enden, liste = [], []
    for m in merkmale.values():
        for zug in zuege(m["kanten"]):
            pts = list({tuple(round(v, 4) for v in _t(p)): None for p in g._punkte_kanten(zug)})  # ohne Doppelte
            if not pts:
                continue
            lg = sum(g._kantenlaenge(e) for e in zug)
            mitte = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
            pr = [ml.projektion(p) for p in pts]
            q = ml.projektion(mitte)
            if q[1] < ra / 2:           # Zug um die Mittellinie: Ende
                enden.append((q[0], lg, pr))
                continue
            s_min, s_max = min(p[0] for p in pr), max(p[0] for p in pr)
            # Mitte: Lage auf der Mittellinie und Winkel des Konturmittelpunkts auf dem Mantel
            winkel = q[2]
            d = dict(durchgehend=m["durch"], z=round(q[0], 2), winkel=round(winkel, 1) % 360, u=round(
                math.radians(winkel) * ra, 2), seite=None, s_von=round(s_min, 2), s_bis=round(s_max, 2))
            zyl = [daten.get(f) for f in m["faces"]]
            rund = zyl and all(z_ and z_[0] == "Z" for z_ in zyl) and \
                max(z_[1] for z_ in zyl) - min(z_[1] for z_ in zyl) < TOL_R
            if not m["durch"]:
                t.gravur += lg
                t.gravur_konturen += 1
                d.update(art="Gravur", schnittlaenge=round(lg, 2), huellmass=round(s_max - s_min, 2))
            elif rund:
                dm = round(2 * zyl[0][1], 2)
                schnitt = dreid.bohrung_2d_rundrohr(dm, 2 * ra, ra - ri) if ri > 0 else None
                schnitt = schnitt or lg
                t.bohrungen[dm] = t.bohrungen.get(dm, 0) + 1
                d.update(art="Bohrung", durchmesser=dm, schnittlaenge=round(schnitt, 2), huellmass=dm)
                lg = schnitt
            else:
                hm = max(s_max - s_min, max(_betrag(_sub(a, b)) for a in pts[::4] for b in pts[::4]))
                d.update(art="Sonderkontur", schnittlaenge=round(lg, 2), huellmass=round(hm, 2),
                         laenge=round(s_max - s_min, 2))
            if m["durch"]:
                t.innen += lg
                t.innen_konturen += 1
                t.konturen += 1
                t.innen_liste.append((d["huellmass"], lg))
            bz = [b for b in ml.teile if b["art"] == "bogen" and s_max > b["s0"] + 0.01 and s_min < b["s1"] - 0.01]
            if bz:
                d["biegezone"] = True
            liste.append(d)
    enden.sort(key=lambda e: e[0])
    kopf = []
    for name, ende, z in (("Ende A", enden[0] if enden else None, 0.0),
                          ("Ende B", enden[-1] if len(enden) > 1 else None, ml.laenge)):
        if ende is None:
            e = dict(form="nicht erkannt", gehrung=None, um_x=None, um_y=None, richtung=None, schnittlaenge=0.0)
        else:
            _, lg, pr = ende
            gerade = max(p[0] for p in pr) - min(p[0] for p in pr) < 0.02
            e = dict(form="gerade" if gerade else "komplex", gehrung=0.0 if gerade else None,
                     um_x=0.0 if gerade else None, um_y=0.0 if gerade else None, richtung=None,
                     schnittlaenge=round(lg, 2), huellmass=round(2 * ra, 2))
            setattr(t, "ende_a" if name == "Ende A" else "ende_b", lg)
            setattr(t, "ende_a_gerade" if name == "Ende A" else "ende_b_gerade", gerade)
            setattr(t, "ende_a_huelle" if name == "Ende A" else "ende_b_huelle", 2 * ra)
            t.konturen += 1
            if not gerade:
                t.hinweise.append(f"{name}: kein gerader Schnitt, prüfen")
        kopf.append(dict(art=name, durchgehend=True, z=round(z, 2), winkel=None, u=None, seite=None, **e))
    if len(enden) > 2:
        t.hinweise.append(f"{len(enden) - 2} weitere Schnitte um die Rohrachse, prüfen")
    t.konturen_liste = kopf + sorted(liste, key=lambda d: (d["z"], d["winkel"]))
    t.schneidweg = t.ende_a + t.ende_b + t.innen
    t.sicherheit["konturen"] = "wahrscheinlich"
    n_zone = sum(1 for d in liste if d.get("biegezone"))
    if n_zone:
        t.hinweise.append(f"{n_zone} Kontur(en) in der Biegezone")
