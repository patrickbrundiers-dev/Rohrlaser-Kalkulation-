"""Normteil-Vorab-Erkennung, Stufe 1 (Master-Prompt Patrick 21.11.2026 „Intelligente Normteil- und
Zukaufteil-Erkennung“): Normteile laut Bauteilname werden nur als Zukaufteil gemessen, ohne Rohr-/Blechmessung.

- N1 Niet „DIN 7337 4x8“ (Kopf Ø8 × 1,5, Schaft Ø4 × 8): Drehteil (Grund: Norm im Bauteilnamen, kein gelber Hinweis), Netz bleibt; Programm: sicheres
  Zukaufteil; Scheibe „DIN 125“ bleibt Blech wie bisher (voll gemessen, nur runde Drehteile kurz)
- N2 nur Begriff („Scheibe“), Halbzeug-Norm (EN 10219), unbekannte Norm, kein Name: voll gemessen wie bisher
- N3 größer als zukaufteile.KLEIN_BIS (Gewindestange DIN 975 × 1000): voll gemessen
- N4 --normteile-voll (step_geometrie.einstellen normteile_voll): voll gemessen
- N5 Programm: --normteile-voll, wenn die eingebaute Erkennung (step_zukauf_begriffe) aus ist

Aufruf: python tests/test_normteil_vorab.py
"""
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]

from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_geometrie as g  # noqa: E402
from rohrlaser import step_einstellungen, zukaufteile  # noqa: E402


def zyl(r, z0, h):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), r, h).Shape()


SCHEIBE = et.cut(zyl(12, 0, 2.5), zyl(6.5, -1, 5))
NIET = g.boolesch("plus", zyl(4, 0, 1.5), zyl(2, 1.5, 8)).Shape()
STANGE = zyl(6, 0, 1000)


def messen(solid, name):
    info = dict(einheit="mm", meldungen=[], bauteile={1: (name, "", "")}, struktur=None)
    return g.koerper_messen(g.Gelesen("T", [("Volumenkörper", solid)], info, {}), 1, netz=True)


def voll(t):
    return not (t.art_grund or "").endswith("im Bauteilnamen")


# N1
g.einstellen(None)
t = messen(NIET, "Nýt trhací DIN7337_4x8-4")
assert t.bauteiltyp == "Drehteil" and not voll(t), (t.bauteiltyp, t.art_grund)
assert not t.hinweise, t.hinweise
assert t.netz, "Normteil bleibt in der 3D-Ansicht (Netz)"
assert abs(t.abm_a - 8) < 0.01 and t.art_regel == "Normteil", (t.abm_a, t.art_regel)
m = dict(bauteil=t.bauteil, profilform=t.profilform, laenge=t.laenge, abm_a=t.abm_a, abm_b=t.abm_b)
info = zukaufteile.einordnen(m)
assert info and info["vertrauen"] == zukaufteile.SICHER and info["kategorie"] == zukaufteile.NIET, info
t = messen(SCHEIBE, "COP-DIN125-M12-")
assert voll(t) and t.bauteiltyp == "Blech", (t.bauteiltyp, t.hinweise)
print("OK: N1 DIN 7337 nur als Zukaufteil gemessen (Drehteil, Netz, sicher), Scheibe bleibt Blech")

# N2
for name in ("Niet 4x8", "Rohr EN 10219 40x2", "DIN 99999", "", "Halter DIN 2395"):
    assert voll(messen(NIET, name)), name
print("OK: N2 Begriff, Halbzeug-Norm, unbekannte Norm, ohne Name: voll gemessen")

# N3
t = messen(STANGE, "DIN 975 M12x1000")
assert voll(t), t.hinweise
print("OK: N3 größer als 150 mm: voll gemessen")

# N4
g.einstellen({"normteile_voll": True})
assert voll(messen(NIET, "DIN 7337 4x8"))
g.einstellen(None)
assert not voll(messen(NIET, "DIN 7337 4x8"))
print("OK: N4 Einstellung voll messen")


# N5
class DB:
    def __init__(self, **w):
        self.w = w

    def einstellung(self, n):
        from rohrlaser.stammdaten import EINSTELLUNG
        return self.w.get(n, EINSTELLUNG[n].vorgabe if n in EINSTELLUNG else None)


assert "--normteile-voll" not in step_einstellungen.mess_argumente(DB(step_cache="nein"))
assert "--normteile-voll" in step_einstellungen.mess_argumente(DB(step_cache="nein", step_zukauf_begriffe="nein"))
print("OK: N5 Aufrufargumente")
print("Alle Tests bestanden.")
