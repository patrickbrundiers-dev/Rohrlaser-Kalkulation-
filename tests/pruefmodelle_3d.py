"""Prüfmodelle der 3D-Kantendarstellung (Auftrag „Kantenvisualisierung und technische Prüfbarkeit“, Patrick
20.11.2026, Punkt 9): acht Netze aus dem Rohr-Rechner (rohr3d), ohne STEP-Messung, damit die Prüfung überall läuft.

1 Rechteckrohr mit Bohrungen und Ausschnitten   2 zwei sich kreuzende Rohre   3 Rohr mit innenliegendem Durchbruch
4 Schweißbaugruppe (Rahmen mit Strebe)           5 Profile mit unterschiedlichen Wandstärken
6 Gehrung und Schrägschnitt                      7 verschachtelte Rohre (Rohr im Rohr)   8 große Baugruppe

Mehrteilige Modelle tragen je Dreieck die Kennung teil:<Nr> (wie Baugruppe und Satz in 3D) und 'teile'."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import rohr3d, schneidweg as sw  # noqa: E402

RE = dict(form="Rechteckrohr", a=60, b=40, wand=2, r=3)
QR = dict(form="Quadratrohr", a=40, b=40, wand=3, r=4)
QR2 = dict(form="Quadratrohr", a=30, b=30, wand=2, r=3)
RR = dict(form="Rundrohr", a=42.4, wand=2)
RR_DICK = dict(form="Rundrohr", a=48.3, wand=5)
RE_DUENN = dict(form="Rechteckrohr", a=80, b=40, wand=1.5, r=2)


def rohr(profil, laenge, konturen=(), a=None, b=None):
    e = sw.v_ergaenzen(dict(a=dict(a or {}), b=dict(b or {}), laenge=laenge, konturen=list(konturen)), profil)
    return rohr3d.netz(e, profil, laenge)


def _lage(netz, o=(0, 0, 0), z=(0, 0, 1), x=(1, 0, 0)):
    """Netz vom Rohrsystem (Achse z) in die Lage o + Achsen x, y = z × x, z."""
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    p = netz["p"]
    q = []
    for i in range(0, len(p) - 2, 3):
        u, v, w = p[i], p[i + 1], p[i + 2]
        q += [o[k] + u * x[k] + v * y[k] + w * z[k] for k in range(3)]
    out = dict(netz, p=q)
    if netz.get("l"):
        out["l"] = {art: [_zug(z_, o, x, y, z) for z_ in zuege] for art, zuege in netz["l"].items()}
    out.pop("wk", None)         # Schnittkörper bleiben beim Rohr-Editor
    out.pop("ln", None)
    return out


def _zug(zug, o, x, y, z):
    out = []
    for i in range(0, len(zug) - 2, 3):
        u, v, w = zug[i], zug[i + 1], zug[i + 2]
        out += [o[k] + u * x[k] + v * y[k] + w * z[k] for k in range(3)]
    return out


def baugruppe(teile):
    """[(Netz in Lage)] -> ein Netz mit Kennung teil:<Nr> je Dreieck (wie BaugruppenAnsicht)."""
    p, t, ti, linien = [], {}, {}, {}
    for nr, n in enumerate(teile):
        basis = len(p) // 3
        p += n["p"]
        for art, idx in (n.get("t") or {}).items():
            t.setdefault(art, []).extend(i + basis for i in idx)
            ti.setdefault(art, []).extend([f"teil:{nr}"] * (len(idx) // 3))
        for art, zuege in (n.get("l") or {}).items():
            linien.setdefault(art, []).extend(zuege)
    return dict(p=p, t=t, ti=ti, l=linien, teile=[f"teil:{i}" for i in range(len(teile))])


def m1_rechteckrohr():
    return rohr(RE, 600, [dict(art=sw.BOHRUNG, anzahl=3, d=10, x=80, abstand=60),
                          dict(art=sw.LANGLOCH, anzahl=1, l=40, b=12, x=340, seite="vorne"),
                          dict(art=sw.RECHTECK, anzahl=1, l=50, b=24, x=480, r=3)])


def m2_kreuzende_rohre():
    a = _lage(rohr(QR, 500, [dict(art=sw.DURCHBRUCH, anzahl=1, x=250, d=42.4, beide="ja")]))
    b = _lage(rohr(RR, 400), o=(0, -200, 250), z=(0, 1, 0), x=(1, 0, 0))
    return baugruppe([a, b])


def m3_durchbruch():
    return rohr(QR, 500, [dict(art=sw.BOHRUNG, anzahl=1, d=24, x=180, seite="vorne"),
                          dict(art=sw.BOHRUNG, anzahl=1, d=16, x=180, seite="hinten"),
                          dict(art=sw.RECHTECK, anzahl=1, l=60, b=20, x=340, seite="oben")])


def m4_schweissbaugruppe():
    h, s = 400.0, 600.0
    teile = [_lage(rohr(QR, s, a=dict(winkel=45), b=dict(winkel=45))),
             _lage(rohr(QR, s, a=dict(winkel=45), b=dict(winkel=45)), o=(0, h, 0)),
             _lage(rohr(QR, h, a=dict(winkel=45), b=dict(winkel=45)), o=(0, 0, 0), z=(0, 1, 0), x=(1, 0, 0)),
             _lage(rohr(QR, h, [dict(art=sw.BOHRUNG, anzahl=2, d=8, x=100, abstand=200)],
                        a=dict(winkel=45), b=dict(winkel=45)), o=(0, 0, s), z=(0, 1, 0), x=(1, 0, 0)),
             _lage(rohr(QR2, math.hypot(h, s) - 60), o=(0, 25, 35), z=(0, h / math.hypot(h, s), s / math.hypot(h, s)),
                   x=(1, 0, 0))]
    return baugruppe(teile)


def m5_wandstaerken():
    teile = [_lage(rohr(RR_DICK, 400)), _lage(rohr(RE_DUENN, 400), o=(90, 0, 0)), _lage(rohr(QR, 400), o=(170, 0, 0)),
             _lage(rohr(RR, 400, [dict(art=sw.BOHRUNG, anzahl=2, d=8, x=100, abstand=200)]), o=(240, 0, 0))]
    return baugruppe(teile)


def m6_gehrung():
    return rohr(RE, 500, a=dict(winkel=45), b=dict(winkel=30))


def m7_verschachtelt():
    aussen = _lage(rohr(QR, 400, [dict(art=sw.BOHRUNG, anzahl=1, d=8, x=60, seite="oben")]))
    innen = _lage(rohr(dict(form="Quadratrohr", a=34, b=34, wand=2, r=2), 500,
                       [dict(art=sw.BOHRUNG, anzahl=1, d=8, x=160, seite="oben")]), o=(0, 0, -100))
    return baugruppe([aussen, innen])


def m8_grosse_baugruppe(n=48):
    teile = []
    for i in range(n):
        r, c = divmod(i, 8)
        teile.append(_lage(rohr(QR if i % 2 else RE, 800, [dict(art=sw.BOHRUNG, anzahl=6, d=10, x=60, abstand=120)]),
                           o=(c * 90.0, r * 90.0, 0)))
    return baugruppe(teile)


MODELLE = [("1 Rechteckrohr mit Bohrungen und Ausschnitten", m1_rechteckrohr),
           ("2 Zwei sich kreuzende Rohre", m2_kreuzende_rohre),
           ("3 Rohr mit innenliegendem Durchbruch", m3_durchbruch),
           ("4 Schweißbaugruppe", m4_schweissbaugruppe),
           ("5 Unterschiedliche Wandstärken", m5_wandstaerken),
           ("6 Gehrung und Schrägschnitt", m6_gehrung),
           ("7 Verschachtelte Rohre", m7_verschachtelt),
           ("8 Große Baugruppe (48 Rohre)", m8_grosse_baugruppe)]
