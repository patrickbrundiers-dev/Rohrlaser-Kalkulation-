"""Erzeugt Beispielteile offen gezeichneter Rechteckrohre (tests/step_offen) für die Bedienungsanleitung: RE 60x40x3
als gekantetes Blech mit einer offenen Seite (U offen mit Gehrung und Bohrungen, U mit ausgeschnittenen Seitenwänden
wie Patricks Beispiel) – gefertigt aus dem Rohr mit je einem Steg 2 mm an den Enden – und ein Rohr mit 2-mm-Spalt
(wird ganz geschlossen). Die Prüfung der Erkennung steht in tests/test_offenes_rohr.py (dort werden die Teile selbst
erzeugt).

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
    u = profil([(-30, -20), (30, -20), (30, 20), (27, 20), (27, -17), (-27, -17), (-27, 20), (-30, 20)], L,
               {(-30, -20): 6, (30, -20): 6, (27, -17): 3, (-27, -17): 3})
    u1 = bohrung_quer(bohrung_quer(u, 10, 120, (1, 0, 0)), 13, 280, (0, 1, 0))
    schreibe(gehrung(u1, L, 45), "OR1_U_offen_RE60x40x3", ZIEL)
    laschen = bohrung_quer(cut(u, box(-31, -14, 230, 62, 40, 110)), 18, 110, (1, 0, 0))
    schreibe(laschen, "OR2_U_Laschen_RE60x40x3", ZIEL)
    spalt = cut(kastenrohr(60, 40, 3, L, 6), box(-1, 15, -1, 2, 6, L + 2))
    schreibe(spalt, "OR3_Spalt2_RE60x40x3", ZIEL)

if __name__ == "__main__":
    main()
