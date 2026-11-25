"""Prüfsatz Sonderkonturen aus der STEP (Patrick 25.11.2026 „Sonderkonturen müssen auch erkannt werden“): Ausschnitte in
der Wand, die keine Bohrung, kein gerades Langloch und kein gerades Rechteck sind – schräges Langloch, gedrehtes
Rechteck mit Eckradius, Dreieck, Sechseck, gedrehtes Quadrat, Kreuz, Schlüsselloch – an Quadrat-, Rechteck- und
Rundrohr. SOLL je Datei: Form, wie sie form_erkennung liefern soll (Typ und Text bis zur Lage, die je nach Blickrichtung
als w oder 180° − w erscheint), Freiform = keine Grundform.

Der Ausschnitt geht senkrecht durch die obere Wand (Strahl senkrecht zur Fläche wie beim 2D-Schneiden); am Rundrohr
nur schmale Formen in Achsrichtung, damit die Abwicklung die Form behält.

Aufruf: python tests/erzeuge_sonderkonturen.py [ZIEL]   (Vorgabe tests/step_sonderkontur)
"""
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism  # noqa: E402
from OCP.GC import GC_MakeArcOfCircle, GC_MakeSegment  # noqa: E402
from OCP.gp import gp_Pnt, gp_Vec  # noqa: E402

import erzeuge_testteile as et  # noqa: E402

ZIEL = Path(sys.argv[1]) if len(sys.argv) > 1 else HIER / "step_sonderkontur"
L = 400.0
Z0 = 200.0


def _p(z, x):
    return gp_Pnt(x, 0, Z0 + z)


def ausschnitt(shape, stuecke):
    """Wand oben (y > 0) mit dem Umriss aus stuecke schneiden: [('G', (z, x), (z, x)) | ('B', p0, pm, p1)], (z längs
    ab Z0, x quer)."""
    w = BRepBuilderAPI_MakeWire()
    for st in stuecke:
        if st[0] == "G":
            kurve = GC_MakeSegment(_p(*st[1]), _p(*st[2])).Value()
        else:
            kurve = GC_MakeArcOfCircle(_p(*st[1]), _p(*st[2]), _p(*st[3])).Value()
        w.Add(BRepBuilderAPI_MakeEdge(kurve).Edge())
    face = BRepBuilderAPI_MakeFace(w.Wire()).Face()
    werkzeug = BRepPrimAPI_MakePrism(face, gp_Vec(0, 100, 0)).Shape()
    return et.cut(shape, werkzeug)


def _dreh(p, w):
    c, s = math.cos(math.radians(w)), math.sin(math.radians(w))
    return p[0] * c - p[1] * s, p[0] * s + p[1] * c


def vieleck(ecken):
    return [("G", ecken[i], ecken[(i + 1) % len(ecken)]) for i in range(len(ecken))]


def langloch(lg, br, w):
    r, h = br / 2, lg / 2 - br / 2
    d = lambda x, y: _dreh((x, y), w)       # noqa: E731
    return [("G", d(-h, -r), d(h, -r)), ("B", d(h, -r), d(h + r, 0), d(h, r)), ("G", d(h, r), d(-h, r)),
            ("B", d(-h, r), d(-h - r, 0), d(-h, -r))]


def rechteck_r(lg, br, r, w):
    hx, hy = lg / 2 - r, br / 2 - r
    d = lambda x, y: _dreh((x, y), w)       # noqa: E731
    q = r / math.sqrt(2)
    return [("G", d(-hx, -hy - r), d(hx, -hy - r)), ("B", d(hx, -hy - r), d(hx + q, -hy - q), d(hx + r, -hy)),
            ("G", d(hx + r, -hy), d(hx + r, hy)), ("B", d(hx + r, hy), d(hx + q, hy + q), d(hx, hy + r)),
            ("G", d(hx, hy + r), d(-hx, hy + r)), ("B", d(-hx, hy + r), d(-hx - q, hy + q), d(-hx - r, hy)),
            ("G", d(-hx - r, hy), d(-hx - r, -hy)), ("B", d(-hx - r, -hy), d(-hx - q, -hy - q), d(-hx, -hy - r))]


def regelmaessig(n, umkreis, w=0.0):
    return vieleck([_dreh((umkreis * math.cos(2 * math.pi * i / n), umkreis * math.sin(2 * math.pi * i / n)), w)
                    for i in range(n)])


def kreuz(a, b):
    """Kreuz: Arme a lang (von der Mitte), b breit."""
    h = b / 2
    return vieleck([(h, -h), (a, -h), (a, h), (h, h), (h, a), (-h, a), (-h, h), (-a, h), (-a, -h), (-h, -h),
                    (-h, -a), (h, -a)])


def schluesselloch(r, b, lg):
    """Kreis r mit Schlitz b breit, lg lang (in +z)."""
    h = b / 2
    x0 = math.sqrt(r * r - h * h)
    return [("G", (x0, -h), (lg, -h)), ("G", (lg, -h), (lg, h)), ("G", (lg, h), (x0, h)),
            ("B", (x0, h), (-r, 0), (x0, -h))]


def teile():
    """{Name: (Form, Soll (typ, Textanfang))}"""
    out = {}
    arten = [("Langloch30", langloch(40, 12, 30), ("Langloch", "Langloch 40 × 12")),
             ("RechteckR3_45", rechteck_r(30, 16, 3, 45), ("Rechteck", "Rechteck 30 × 16 R3")),
             ("Dreieck", regelmaessig(3, 12, 90), ("Dreieck", "Dreieck 20,8 × 20,8 × 20,8")),
             ("Sechseck", regelmaessig(6, 10), ("Vieleck", "Sechseck SW 17,3")),
             ("Quadrat20", regelmaessig(4, 10, 20), ("Rechteck", "Quadrat 14,1")),
             ("Kreuz", kreuz(12, 6), ("Freiform", "Freiform: 12 Geraden")),
             ("Schluesselloch", schluesselloch(7, 5, 16), ("Freiform", "Freiform: 3 Geraden, 1 Bogen (R7)"))]
    for name, rohr in (("QR60", et.kastenrohr(60, 60, 3, L, 6)), ("RE80x40", et.kastenrohr(80, 40, 3, L, 6))):
        for art, st, soll in arten:
            out[f"SK_{name}_{art}"] = (ausschnitt(rohr, st), soll)
    rr = et.rundrohr(60.3, 3, L)
    out["SK_RR60_Langloch0"] = (ausschnitt(rr, langloch(40, 8, 0)), ("Langloch", "Langloch 40 × 8"))
    return out


def main():
    ZIEL.mkdir(parents=True, exist_ok=True)
    t = teile()
    for n, (s, _) in t.items():
        et.schreibe(s, n, ZIEL)
    print(len(t), "Dateien in", ZIEL)


if __name__ == "__main__":
    main()
