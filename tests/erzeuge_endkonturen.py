"""Prüfsatz Endkonturen aus der STEP (Patrick 25.11.2026 „Erkennung weiter verbessern“): Rohre mit V-Spitze, V-Kerbe,
U-Kerbe, U-Zunge, Bogen konvex/konkav, Stufen und Schräg an Ende B, an Rund-, Quadrat- und Rechteckrohr.

Jede Kontur ist ein Durchgangsschnitt mit einem Linienzug in der Seitenansicht (wie endkontur.py): Material bei
z ≤ L − d(y), der Schnitt geht quer durch das Rohr (in x). SOLL je Datei: Konturart und Maße, wie sie die Erkennung
liefern soll (endkontur.TYPEN), Richtung 0° = oben.

Aufruf: python tests/erzeuge_endkonturen.py [ZIEL]   (Vorgabe tests/step_endkontur)
"""
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism  # noqa: E402
from OCP.gp import gp_Pnt, gp_Vec  # noqa: E402

import erzeuge_testteile as et  # noqa: E402

ZIEL = Path(sys.argv[1]) if len(sys.argv) > 1 else HIER / "step_endkontur"
L = 600.0


def kontur_ende(shape, laenge, d, halb, schritt=0.5):
    """Ende B mit dem Verlauf d(y) (Abstand hinter der Spitze bei der Höhe y) schneiden."""
    rand = halb + 20
    n = int(2 * rand / schritt)
    pts = sorted({-rand + 2 * rand * i / n for i in range(n + 1)}
                 | {y + dy for y in getattr(d, "knicke", ()) for dy in (-0.4, -0.2, -0.1, -0.05, -0.02, -1e-3, 0.0, 1e-3,
                                                                       0.02, 0.05, 0.1, 0.2, 0.4)})
    poly = BRepBuilderAPI_MakePolygon()
    for y in pts:
        poly.Add(gp_Pnt(-300, y, laenge - d(max(-halb, min(halb, y)))))
    poly.Add(gp_Pnt(-300, rand, laenge + 200))
    poly.Add(gp_Pnt(-300, -rand, laenge + 200))
    poly.Close()
    face = BRepBuilderAPI_MakeFace(poly.Wire()).Face()
    werkzeug = BRepPrimAPI_MakePrism(face, gp_Vec(600, 0, 0)).Shape()
    return et.cut(shape, werkzeug)


def _mit(f, *knicke):
    """Verlauf mit den Stellen, an denen er knickt oder springt (dort genau ein Punkt, sonst schräge Wand)."""
    f.knicke = knicke
    return f


def v_spitze(t, h):
    return _mit(lambda y: t * abs(y) / h, 0.0)


def v_kerbe(t, b):
    return _mit(lambda y: t * max(0.0, 1 - abs(y) / (b / 2)), -b / 2, 0.0, b / 2)


def u_kerbe(t, b):
    r = b / 2

    def f(y):
        if abs(y) >= r:
            return 0.0
        tiefe_gerade = t - r
        return tiefe_gerade + math.sqrt(max(r * r - y * y, 0.0)) if tiefe_gerade >= 0 else math.sqrt(r * r - y * y)
    return _mit(f, -r, r)


def u_zunge(t, b):
    k = u_kerbe(t, b)
    return _mit(lambda y: t - k(y), *k.knicke)


def bogen(t, h, konvex=True):
    r = (h * h + t * t) / (2 * t)           # Kreis durch Mitte (0) und Rand (±h, t)

    def f(y):
        x = min(abs(y), h)
        dd = r - math.sqrt(max(r * r - x * x, 0.0))
        return dd if konvex else t - dd
    return _mit(f, 0.0)


def stufen(halb, stufen_):
    """stufen_ [(Breite, Tiefe)] von der langen Seite (y = +halb) aus."""
    def f(y):
        pos = halb
        tiefe = 0.0
        for breite, tiefe in stufen_:
            if y >= pos - breite - 1e-9:
                return tiefe
            pos -= breite
        return tiefe
    grenzen, pos = [], halb
    for breite, _ in stufen_[:-1]:
        pos -= breite
        grenzen.append(pos)
    return _mit(f, *grenzen)


def schraeg(t, halb):
    return lambda y: t * (halb - y) / (2 * halb)


def teile():
    """{Name: (Form, Soll-Kontur oder None)}"""
    out = {}
    for name, rohr, halb in (("QR60", et.kastenrohr(60, 60, 3, L, 6), 30.0),
                             ("RE80x40", et.kastenrohr(80, 40, 3, L, 6), 20.0),
                             ("RR60", et.rundrohr(60.3, 3, L), 30.15)):
        arten = [("VSpitze", v_spitze(20, halb), dict(typ="V-Spitze", tiefe=20)),
                 ("VKerbe", v_kerbe(15, 1.2 * halb), dict(typ="V-Kerbe", tiefe=15, breite=1.2 * halb)),
                 ("UKerbe", u_kerbe(18, halb), dict(typ="U-Kerbe", tiefe=18, breite=halb)),
                 ("UZunge", u_zunge(18, halb), dict(typ="U-Zunge", tiefe=18, breite=halb)),
                 ("BogenVex", bogen(10, halb, True), dict(typ="Bogen konvex", tiefe=10)),
                 ("BogenKav", bogen(10, halb, False), dict(typ="Bogen konkav", tiefe=10)),
                 ("Stufen", stufen(halb, [(halb, 0.0), (halb, 12.0)]),
                  dict(typ="Stufen", stufen=[[halb, 0.0], [halb, 12.0]])),
                 ("Schraeg", schraeg(25, halb), None)]      # Schräg über die volle Höhe = Gehrung (bleibt Gehrung)
        for art, d, soll in arten:
            out[f"EK_{name}_{art}"] = (kontur_ende(rohr, L, d, halb), soll)
    return out


def main():
    ZIEL.mkdir(parents=True, exist_ok=True)
    for n, (s, _) in teile().items():
        et.schreibe(s, n, ZIEL)
    print(len(teile()), "Dateien in", ZIEL)


if __name__ == "__main__":
    main()
