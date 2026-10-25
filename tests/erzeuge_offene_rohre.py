"""Erzeugt Beispielteile mit Spalt gezeichneter Rechteckrohre (tests/step_offen) für die Bedienungsanleitung: RE 60x40x3
mit einem Spalt über die ganze Länge (2 mm oben mit Gehrung, 1,5 mm seitlich) und als Gegenbeispiel ein U offen, das
offen bleibt (nur Spalte bis 2 mm werden geschlossen). Die Prüfung der Erkennung steht in tests/test_offenes_rohr.py
(dort werden die Teile selbst erzeugt).

Aufruf: python tests/erzeuge_offene_rohre.py   (braucht OpenCascade, wie tests/erzeuge_testteile.py)
"""
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402

from erzeuge_testteile import bohrung_quer, cut, gehrung, kastenrohr, profil, schreibe  # noqa: E402

ZIEL = Path(sys.argv[1]) if len(sys.argv) > 1 else HIER / "step_offen"
L = 400


def box(x0, y0, z0, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), dx, dy, dz).Shape()


def main():
    ZIEL.mkdir(exist_ok=True)
    rohr = kastenrohr(60, 40, 3, L, 6)
    spalt = cut(rohr, box(-1, 15, -1, 2, 6, L + 2))
    spalt = bohrung_quer(bohrung_quer(spalt, 10, 120, (1, 0, 0)), 13, 280, (0, 1, 0))
    schreibe(gehrung(spalt, L, 45), "OR1_Spalt2_RE60x40x3", ZIEL)
    seite = cut(rohr, box(26, -0.75, -1, 5, 1.5, L + 2))
    schreibe(bohrung_quer(seite, 8.5, 200, (0, 1, 0)), "OR2_Spalt_seitlich_RE60x40x3", ZIEL)
    u = profil([(-30, -20), (30, -20), (30, 20), (27, 20), (27, -17), (-27, -17), (-27, 20), (-30, 20)], L,
               {(-30, -20): 6, (30, -20): 6, (27, -17): 3, (-27, -17): 3})
    schreibe(u, "OR3_U_offen_bleibt", ZIEL)

if __name__ == "__main__":
    main()
