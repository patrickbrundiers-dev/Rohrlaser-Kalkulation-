"""Erzeugt die STEP-Testteile für Profilwechsel und 3D-Enden (tests/step_profilwechsel): Rechteckrohr mit zweiachsigem
Schrägschnitt, Quadratrohr mit Spitze aus zwei Ebenen (3D-Ende), Rundrohr mit Ausklinkung auf ein Rundrohr Ø 60
(Zylinder quer zur Achse).

Aufruf: python tests/erzeuge_profilwechsel_teile.py   (braucht OpenCascade, wie tests/erzeuge_testteile.py)
"""
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

from erzeuge_testteile import cut, gehrung, kastenrohr, rundrohr, schraeg_ende, schreibe  # noqa: E402

ZIEL = HIER / "step_profilwechsel"

if __name__ == "__main__":
    schreibe(schraeg_ende(kastenrohr(60, 40, 3, 900, 0), 800, 20, 10), "PW01_RE60x40x3_schraeg20-10_L800", ZIEL)
    # Spitze: zwei Gehrungen 30° gegeneinander (Ende B = Minimum der beiden Ebenen)
    qr = kastenrohr(40, 40, 3, 800, 0)
    schreibe(gehrung(gehrung(qr, 600, 30), 600, -30), "PW02_QR40x3_Spitze30_L600", ZIEL)
    # Ausklinkung: Rundrohr Ø 42,4 rechtwinklig auf Rundrohr Ø 60 (Zylinder um X durch z = 530)
    rr = rundrohr(42.4, 2, 600)
    rr = cut(rr, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(-100, 0, 530), gp_Dir(1, 0, 0)), 30, 200).Shape())
    rr = cut(rr, BRepPrimAPI_MakeBox(gp_Pnt(-100, -100, 530), 200, 200, 200).Shape())
    schreibe(rr, "PW03_RR42-4x2_Ausklinkung60_L530", ZIEL)
    print("Testteile in", ZIEL)
