"""Prüfreihe: berechnete Schnitte im 3D-Modell des Editors auf Fehler prüfen (Patrick 16.11.2026: „Berechnete Schnitte
im 3d editor im model auf Fehler prüfen“).

Das 3D-Modell (rohr3d.netz, wie im Teile-Editor) wird mit einer unabhängig konstruierten Geometrie verglichen:
M1 Konturen (Bohrung, Langloch, Rechteck mit Eckradius, quer versetzt, gedreht, quer, Muster) auf allen vier Seiten von
   Quadrat- und Rechteckrohr (Breitseite oben und hochkant), Bohrungen rundum am Rundrohr, Gehrungen in 3D in jede
   Richtung und um beide Achsen: Werkzeuge mit OpenCascade vom Rohr abgezogen, Kanten auf der Außenfläche gegen die
   Linien des Modells (beide Richtungen, Toleranz 0,35 mm bei 0,5 mm Abtastung; die Konturlinien liegen
   rohr3d.ABSTAND über der Wand).
M2 Gehrung in 2D (ohne 3D-Häkchen): Strahl senkrecht zur Oberfläche, kein Material ragt über die Gehrungsfläche;
   jeder Punkt der Schnittkante liegt bei max(Lage außen, Lage innen) – 320 Fälle, Toleranz 0,1 mm.
M3 Schnittlängen (schneidweg.rechnen) gegen die Länge der Schnittlinien im Modell (1 % bzw. 0,5 mm). Bewusst anders
   und nicht geprüft: Gehrung in 2D rechnet die Länge an der Außenkante der Ebene (wie bisher), die 2D-Bohrung am
   Rundrohr ist außen breiter (Strahl zur Rohrmitte).
M4 Längste Seite im Editor gewählt: „gekippt über“ stellt sich passend ein (vorher rechnete die Schnittlänge beim
   Rechteckrohr über die andere Seite, bis 15 % daneben, nur als Fehler gemeldet).

Aufruf: python tests/test_modell_schnitte.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np  # noqa: E402
import erzeuge_testteile as et  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Curve  # noqa: E402
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon,  # noqa: E402
                                BRepBuilderAPI_Transform)
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeHalfSpace, BRepPrimAPI_MakePrism  # noqa: E402
from OCP.GCPnts import GCPnts_UniformAbscissa  # noqa: E402
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec  # noqa: E402
from OCP.TopAbs import TopAbs_EDGE  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402
from rohrlaser import rohr3d, schneidweg as sw, skizze as sk  # noqa: E402


def ok(t):
    print("OK    ", t)


PROFILE = {
    "QR 40x40x3": dict(form="Quadratrohr", a=40, b=None, wand=3, profil_id="QR 40x40x3"),
    "RE 60x40x3": dict(form="Rechteckrohr", a=60, b=40, wand=3, profil_id="RE 60x40x3"),
    "RE 40x60x3 (hoch)": dict(form="Rechteckrohr", a=40, b=60, wand=3, profil_id="RE 40x60x3"),
    "RR 48,3x2,6": dict(form="Rundrohr", a=48.3, b=None, wand=2.6, profil_id="RR 48,3x2,6"),
}
SEITEN_N = {"oben": (0, 1), "vorne": (1, 0), "unten": (0, -1), "hinten": (-1, 0)}


def xyz(x, u, v):
    return (-u, v, x)


def outline(art, z):
    """2D-Umriss (längs, quer) um die Mitte."""
    n = 96
    if art == sw.BOHRUNG:
        r = z["d"] / 2
        return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    if art == sw.LANGLOCH:
        l, b = z["l"], z["b"]
        r = b / 2
        h = l / 2 - r
        pk = [(h + r * math.cos(a), r * math.sin(a)) for a in np.linspace(-math.pi / 2, math.pi / 2, n // 2)]
        pk += [(-h + r * math.cos(a), r * math.sin(a)) for a in np.linspace(math.pi / 2, 3 * math.pi / 2, n // 2)]
        return pk
    if art == sw.RECHTECK:
        b, h, r = z["b"], z["h"], z.get("r") or 0
        if r <= 0:
            return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]
        pk = []
        for cx, cy, a0 in ((b / 2 - r, -h / 2 + r, -90), (b / 2 - r, h / 2 - r, 0), (-b / 2 + r, h / 2 - r, 90),
                           (-b / 2 + r, -h / 2 + r, 180)):
            pk += [(cx + r * math.cos(math.radians(a0 + t)), cy + r * math.sin(math.radians(a0 + t)))
                   for t in np.linspace(0, 90, 12)]
        return pk
    raise ValueError(art)


def werkzeug_flach(qs, z, x0):
    """Prisma durch die eine Wand der Fläche z['seite'] (Kastenrohr)."""
    seite = z.get("seite") or "oben"
    n = SEITEN_N[seite]
    t = (n[1], -n[0])           # quer in der Fläche (u, v), + zur nächsten Fläche (oben→vorne→unten→hinten)
    halb = qs.B / 2 if n[0] else qs.H / 2
    q = z.get("q") or 0.0
    cu, cv = n[0] * halb + t[0] * q, n[1] * halb + t[1] * q
    w = math.radians(z.get("drehung") or 0)
    poly = BRepBuilderAPI_MakePolygon()
    for a, b in outline(z["art"], z):
        a, b = a * math.cos(w) - b * math.sin(w), a * math.sin(w) + b * math.cos(w)
        u, v = cu + t[0] * b + n[0] * 2, cv + t[1] * b + n[1] * 2
        poly.Add(gp_Pnt(*xyz(x0 + a, u, v)))
    poly.Close()
    f = BRepBuilderAPI_MakeFace(poly.Wire()).Face()
    d = qs.wand + 2.5
    return BRepPrimAPI_MakePrism(f, gp_Vec(*xyz(0, -n[0] * d, -n[1] * d))).Shape()


def werkzeug_rund(qs, z, x0):
    phi = math.radians(z.get("seite") or 0)
    nu, nv = math.sin(phi), math.cos(phi)
    if z["art"] != sw.BOHRUNG:
        raise ValueError("RR nur Bohrung")
    p = xyz(x0, nu * (qs.r + 2), nv * (qs.r + 2))
    d = xyz(0, -nu, -nv)
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p), gp_Dir(*d)), z["d"] / 2, qs.wand + 2.5).Shape()


def ende_halbraum(qs, e, s, L):
    w = abs(e.get("winkel") or 0)
    if not w:
        return None
    th = math.radians(sk._richtung(qs, e))
    sn, cs = math.sin(th), math.cos(th)
    ext = max(u * sn + v * cs for u, v in umriss_aussen(qs)) + 1e-3      # nicht genau tangential (OCC)
    tw = math.tan(math.radians(w))
    # x(u,v) = (ext - (u s + v c)) tw ab der Spitze
    if s == "a":
        p0 = xyz(0, ext * sn, ext * cs)
        nrm = xyz(1, tw * sn, tw * cs)          # Richtung, in der x - (ext-lage)tw wächst
        innen = gp_Pnt(*xyz(-200, 0, 0))
    else:
        p0 = xyz(L, ext * sn, ext * cs)
        nrm = xyz(-1, tw * sn, tw * cs)
        innen = gp_Pnt(*xyz(L + 200, 0, 0))
    f = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(*p0), gp_Dir(*nrm)), -500, 500, -500, 500).Face()
    return BRepPrimAPI_MakeHalfSpace(f, innen).Solid()


def umriss_aussen(qs):
    if qs.r:
        return [(qs.r * math.sin(a), qs.r * math.cos(a)) for a in np.linspace(0, 2 * math.pi, 3600)]
    r = qs.radius
    u1, v1 = qs.B / 2, qs.H / 2
    pk = []
    for cu, cv, a0 in ((u1 - r, v1 - r, 0), (u1 - r, -v1 + r, 90), (-u1 + r, -v1 + r, 180), (-u1 + r, v1 - r, 270)):
        pk += [(cu + r * math.sin(math.radians(a0 + t)), cv + r * math.cos(math.radians(a0 + t))) for t in np.linspace(0, 90, 400)]
    return pk


def aussen_abstand(qs, u, v):
    """Abstand eines Punkts (u, v) zur Außenkontur (0 = auf der Oberfläche)."""
    if qs.r:
        return abs(math.hypot(u, v) - qs.r)
    r = qs.radius
    du, dv = abs(u) - (qs.B / 2 - r), abs(v) - (qs.H / 2 - r)
    if du > 0 and dv > 0:
        return abs(math.hypot(du, dv) - r)
    return min(abs(abs(u) - qs.B / 2), abs(abs(v) - qs.H / 2))


def referenz(profil, e, L):
    qs = sk.Querschnitt(rohr3d.mit_radius(profil, e))
    if qs.r:
        s = et.rundrohr(qs.B, qs.wand, L)
        tr = gp_Trsf()
        tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(7.3))   # Naht weg von 0/45/90°
        s = BRepBuilderAPI_Transform(s, tr, True).Shape()
    else:
        s = et.kastenrohr(qs.B, qs.H, qs.wand, L, qs.radius)
    for z in e.get("konturen") or []:
        n = int(z.get("anzahl") or 1)
        for i in range(n):
            x0 = z["x"] + i * (z.get("abstand") or 0)
            s = et.cut(s, werkzeug_rund(qs, z, x0) if qs.r else werkzeug_flach(qs, z, x0))
    for side in ("a", "b"):
        h = ende_halbraum(qs, e.get(side) or {}, side, L)
        if h is not None:
            s = et.cut(s, h)
    return qs, s


def kanten_punkte(shape, qs, L, schritt=0.5):
    pk = []
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        c = BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current()) if hasattr(TopoDS, "Edge_s") else TopoDS.Edge(ex.Current()))
        ab = GCPnts_UniformAbscissa(c, schritt)
        ps = []
        if ab.IsDone() and ab.NbPoints() > 1:
            ps = [c.Value(ab.Parameter(i)) for i in range(1, ab.NbPoints() + 1)]
        else:
            ps = [c.Value(c.FirstParameter()), c.Value(c.LastParameter())]
        ps = [(p.X(), p.Y(), p.Z()) for p in ps]
        zs = [p[2] for p in ps]
        xy = [(p[0], p[1]) for p in ps]
        laengs = bool(qs.r) and max(math.dist(xy[0], q) for q in xy) < 1e-6 and max(zs) - min(zs) > 0.1  # Naht
        if max(zs) - min(zs) < 0.6 * L and not laengs:          # keine Längskanten des Rohrs
            pk += [p for p in ps if aussen_abstand(qs, -p[0], p[1]) < 0.02]
        ex.Next()
    return np.array(pk)


def segmente(netz, arten):
    seg = []
    for a in arten:
        for z in netz["l"].get(a, []):
            p = [z[i:i + 3] for i in range(0, len(z) - 2, 3)]
            seg += [(p[i], p[i + 1]) for i in range(len(p) - 1)]
    return np.array(seg, dtype=float).reshape(-1, 2, 3)


def abstand(pk, seg):
    if len(seg) == 0 or len(pk) == 0:
        return np.full(len(pk), 99.0)
    a, b = seg[:, 0], seg[:, 1]
    ab = b - a
    lg = (ab * ab).sum(1)
    lg[lg < 1e-12] = 1e-12
    out = np.empty(len(pk))
    for i in range(0, len(pk), 200):
        p = pk[i:i + 200, None, :]
        t = np.clip(((p - a) * ab).sum(2) / lg, 0, 1)
        q = a + t[..., None] * ab
        out[i:i + 200] = np.sqrt(((p - q) ** 2).sum(2)).min(1)
    return out


def zu_punkten(p, wolke):
    if len(wolke) == 0 or len(p) == 0:
        return np.full(len(p), 99.0)
    out = np.empty(len(p))
    for i in range(0, len(p), 200):
        out[i:i + 200] = np.sqrt(((p[i:i + 200, None, :] - wolke[None]) ** 2).sum(2)).min(1)
    return out


def abtasten(seg, schritt=0.5):
    pk = []
    for a, b in seg:
        n = max(1, int(np.linalg.norm(b - a) / schritt))
        pk += [a + (b - a) * k / n for k in range(n + 1)]
    return np.array(pk)


def pruefen(name, pid, e, L=500):
    profil = PROFILE[pid]
    e = dict(e, d3=True)
    for s in ("a", "b"):
        e.setdefault(s, {})
        if e[s].get("winkel"):
            e[s] = dict(e[s], d3=True)
    netz = rohr3d.netz(e, profil, L)
    qs, ref = referenz(profil, e, L)
    rp = kanten_punkte(ref, qs, L)
    sk_ = segmente(netz, ("K",))
    se = segmente(netz, ("EA", "EB"))
    mk = abtasten(sk_) if len(sk_) else np.zeros((0, 3))
    me = abtasten(se) if len(se) else np.zeros((0, 3))
    # Modell -> Referenzpunkte (0,5 mm abgetastet, also bis 0,25 mm Rasterfehler)
    d_mk = zu_punkten(mk, rp) - rohr3d.ABSTAND
    d_me = zu_punkten(me, rp)
    # Referenz -> Modell
    d_rk = np.minimum(abstand(rp, sk_) - rohr3d.ABSTAND, abstand(rp, se))
    def w(d):
        return float(np.max(np.abs(d))) if len(d) else 0.0
    erg = dict(name=name, kontur_modell=w(d_mk), ende_modell=w(d_me), referenz=w(d_rk), n_ref=len(rp))
    schlecht = max(erg["kontur_modell"], erg["ende_modell"], erg["referenz"]) > 0.35
    if schlecht and len(rp):
        i = int(np.argmax(np.abs(d_rk))) if len(rp) else 0
        erg["ref_punkt"] = [round(c, 2) for c in rp[i]]
        if len(mk):
            j = int(np.argmax(np.abs(d_mk)))
            erg["modell_punkt"] = [round(c, 2) for c in mk[j]]
    erg["ok"] = not schlecht
    return erg


def normale(qs, u, v):
    if qs.r:
        lg = math.hypot(u, v) or 1
        return u / lg, v / lg
    r = qs.radius
    du, dv = abs(u) - (qs.B / 2 - r), abs(v) - (qs.H / 2 - r)
    if du > 1e-9 and dv > 1e-9:
        lg = math.hypot(du, dv)
        return math.copysign(du / lg, u), math.copysign(dv / lg, v)
    if du > dv:
        return math.copysign(1, u), 0.0
    return 0.0, math.copysign(1, v)


def pruefen_2d(name, pid, e, L=500):
    """Gehrung in 2D (ohne 3D-Häkchen): Strahl senkrecht zur Oberfläche, die ganze Wand unter einem Punkt wird an
    derselben Stelle geschnitten, und kein Material ragt über die Gehrungsfläche: Lage = max(Außen-, Innenpunkt)."""
    profil = PROFILE[pid]
    netz = rohr3d.netz(e, profil, L)
    qs = sk.Querschnitt(rohr3d.mit_radius(profil, e))
    weit, wo = 0.0, None
    for s, art in (("a", "EA"), ("b", "EB")):
        ee = e.get(s) or {}
        w = abs(ee.get("winkel") or 0)
        if not w:
            continue
        th = math.radians(sk._richtung(qs, ee))
        sn, cs = math.sin(th), math.cos(th)
        ext = max(u * sn + v * cs for u, v in umriss_aussen(qs))
        tw = math.tan(math.radians(w))
        for p in abtasten(segmente(netz, (art,)), 0.5):
            u, v = -p[0], p[1]
            if aussen_abstand(qs, u, v) > 0.05:
                continue                      # Innenkante
            nu, nv = normale(qs, u, v)
            ui, vi = u - qs.wand * nu, v - qs.wand * nv
            soll = max((ext - (u * sn + v * cs)) * tw, (ext - (ui * sn + vi * cs)) * tw)
            ist = p[2] if s == "a" else L - p[2]
            if abs(ist - soll) > weit:
                weit, wo = abs(ist - soll), dict(ende=s, u=round(u, 2), v=round(v, 2), ist=round(ist, 3), soll=round(soll, 3))
    return dict(name=name, ende_2d=weit, wo=wo, ok=weit < 0.1)


# ------------------------------------------------------------------ Fälle
B, LL, R = sw.BOHRUNG, sw.LANGLOCH, sw.RECHTECK
KASTEN = ("QR 40x40x3", "RE 60x40x3", "RE 40x60x3 (hoch)")
RR = "RR 48,3x2,6"


def faelle_m1():
    f = []
    for pid in KASTEN:
        for seite in ("oben", "vorne", "unten", "hinten"):
            f.append((f"{pid} Bohrung {seite}", pid, dict(konturen=[dict(art=B, anzahl=1, d=10, x=150, seite=seite)])))
            f.append((f"{pid} Langloch {seite}", pid,
                      dict(konturen=[dict(art=LL, anzahl=1, l=30, b=10, x=250, seite=seite)])))
            f.append((f"{pid} Rechteck r3 {seite}", pid,
                      dict(konturen=[dict(art=R, anzahl=1, b=24, h=12, r=3, x=350, seite=seite)])))
        f.append((f"{pid} Bohrung quer +6 vorne", pid, dict(konturen=[dict(art=B, anzahl=1, d=8, x=150, seite="vorne",
                                                                          q=6)])))
        f.append((f"{pid} Langloch gedreht 30°", pid,
                  dict(konturen=[dict(art=LL, anzahl=1, l=24, b=8, x=250, seite="oben", drehung=30)])))
        f.append((f"{pid} Langloch quer", pid,
                  dict(konturen=[dict(art=LL, anzahl=1, l=20, b=8, x=250, seite="oben", drehung=90)])))
        f.append((f"{pid} Muster 3 Bohrungen", pid,
                  dict(konturen=[dict(art=B, anzahl=3, d=6, x=100, abstand=40, seite="unten")])))
        for achse in sw.ACHSEN:
            for ri in (None, 0, 90, 180, 270):
                f.append((f"{pid} Gehrung A 30° {achse} {ri}", pid,
                          dict(a=dict(winkel=30, achse=achse, richtung=ri), konturen=[])))
        f.append((f"{pid} Gehrung B 45° unten + Bohrung nahe am Ende", pid,
                  dict(b=dict(winkel=45, achse="über Höhe", richtung=180),
                       konturen=[dict(art=B, anzahl=1, d=8, x=440, seite="oben")])))
    for w in (0, 45, 90, 135, 180, 270, 300):
        f.append((f"RR Bohrung {w}°", RR, dict(konturen=[dict(art=B, anzahl=1, d=10, x=200, seite=w)])))
    for ri in (None, 0, 90, 180, 270, 45):
        f.append((f"RR Gehrung A 30° {ri}", RR, dict(a=dict(winkel=30, richtung=ri), konturen=[])))
    f.append(("RR Gehrung B 40° 90", RR, dict(b=dict(winkel=40, richtung=90), konturen=[])))
    return f


def m1():
    schlecht = []
    for name, pid, e in faelle_m1():
        r = pruefen(name, pid, e)
        if not r["ok"]:
            schlecht.append(r)
    assert not schlecht, json.dumps(schlecht, ensure_ascii=False, indent=1)
    ok(f"M1 {len(faelle_m1())} Fälle: Konturen und 3D-Gehrungen im Modell genau wie die konstruierte Geometrie")


def m2():
    n, schlecht = 0, []
    for pid in PROFILE:
        for achse in sw.ACHSEN:
            for ri in (None, 0, 90, 180, 270):
                for w in (15, 30, 45, 60):
                    for s in ("a", "b"):
                        r = pruefen_2d(f"{pid} {s} {w}° {achse} {ri}", pid,
                                       {s: dict(winkel=w, achse=achse, richtung=ri), "konturen": []})
                        n += 1
                        if not r["ok"]:
                            schlecht.append(r)
    assert not schlecht, json.dumps(schlecht[:10], ensure_ascii=False, indent=1)
    ok(f"M2 {n} Fälle: Gehrung in 2D, kein Material über der Gehrungsfläche, Innenkante maßhaltig")


def laengen(netz):
    out = {}
    for art, zuege in netz["l"].items():
        for i, z in enumerate(zuege):
            kn = netz["li"][art][i]
            p = [z[j:j + 3] for j in range(0, len(z) - 2, 3)]
            out[(art, kn)] = out.get((art, kn), 0) + sum(math.dist(p[j], p[j + 1]) for j in range(len(p) - 1))
    return out


def m3(k):
    from rohrlaser import rechnen
    m = rechnen.maschine(dict(maschine="T11", stange=6000), k)
    faelle = []
    for name, pid, e in faelle_m1():
        if pid == RR and e.get("konturen"):
            continue                # 2D-Bohrung am Rundrohr: außen breiter (Strahl zur Rohrmitte), gewollt
        for s in ("a", "b"):
            x = e.get(s) or {}
            if x.get("winkel") and pid != RR:
                x = dict(x, achse=sw.achse_zu_richtung(PROFILE[pid], x["richtung"])) \
                    if x.get("richtung") is not None else x
            e = dict(e, **{s: dict(x, d3=True) if x.get("winkel") else x})
        faelle.append((name, pid, dict(e, d3=True)))
    n, schlecht = 0, []
    for name, pid, e in faelle:
        prof = PROFILE[pid]
        r = sw.rechnen(e, prof, rechnen.kontur_regel(m, rechnen.wand_schneiden(prof)), None, m)
        assert not r["fehler"], (name, r["fehler"])
        lg = laengen(rohr3d.netz(e, prof, 500))
        for st in r["schritte"]:
            if st["text"].startswith("Anfangsschnitt"):
                ist = lg.get(("EA", "ende:a"))
            elif st["text"].startswith("Endschnitt"):
                ist = lg.get(("EB", "ende:b"))
            else:
                i = e["konturen"].index(st["eingabe"])
                ist = lg[("K", f"kontur:{i}")] / max(1, st["anzahl"])
            n += 1
            if ist is None or abs(ist - st["laenge_stueck"]) > max(0.5, 0.01 * st["laenge_stueck"]):
                schlecht.append((name, st["text"], round(st["laenge_stueck"], 2), ist and round(ist, 2)))
    assert not schlecht, schlecht
    ok(f"M3 {n} Schnitte: berechnete Schnittlänge = Länge der Schnittlinie im Modell")


def m4(db, k):
    from PySide6.QtWidgets import QApplication
    from rohrlaser import rechnen
    from rohrlaser.schneidweg_dialog import SchneidwegDialog
    app = QApplication.instance() or QApplication([])  # noqa: F841
    pid = "RE 60x40x3"
    kopf = dict(maschine="T11", stange=6000)
    m = rechnen.maschine(kopf, k)
    p = dict(profil_id=pid, werkstoff_id="S235-10219", laenge=500, stueck=1,
             technik=json.dumps(dict(a=dict(winkel=45, achse="über Höhe"), b={}, konturen=[], quelle=sw.QUELLE)))
    d = SchneidwegDialog(None, p, k.profile[pid], kopf, k, db.tabellen(), db)
    for text, grad in sw.RICHTUNGEN.items():
        if grad is None:
            continue
        d.richtung["a"].setCurrentText(text)
        assert d.achse["a"].currentText() == sw.achse_zu_richtung(d.profil, grad), (text, d.achse["a"].currentText())
        e = d.eingaben()
        r = sw.rechnen(e, d.profil, rechnen.kontur_regel(m, rechnen.wand_schneiden(d.profil)), None, m)
        assert not r["fehler"], (text, r["fehler"])
        e3 = dict(e, d3=True, a=dict(e["a"], d3=True))          # Länge rechnet an der Ebene wie 3D (2D bewusst außen)
        ist = laengen(rohr3d.netz(e3, d.profil, 500))[("EA", "ende:a")]
        assert abs(ist - r["schritte"][0]["laenge_stueck"]) < 0.01 * ist, (text, ist, r["schritte"][0])
    assert d.achse["a"].currentText() == "über Höhe"              # zuletzt 270°: über die lange Seite
    ok("M4 Längste Seite gewählt: „gekippt über“ passt sich an, Schnittlänge über dieselbe Seite wie das Modell")


def main():
    from rohrlaser.datenbank import Datenbank
    db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
    k = db.kontext()
    m1()
    m2()
    m3(k)
    m4(db, k)
    print("OK: berechnete Schnitte im 3D-Modell ohne Fehler")


if __name__ == "__main__":
    main()
