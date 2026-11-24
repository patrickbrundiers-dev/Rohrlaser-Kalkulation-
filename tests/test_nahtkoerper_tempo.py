"""Schweißnaht-Körper schneller zuordnen (STEP-Import mit KI, Phase 2b, Patrick 21.11.2026 „Alles einbauen nach
Empfehlungen“): Pizza-Ofen 816 s → 186 s (Abschluss 773 s → 139 s), Ergebnis bitgleich; vorher lief der Abschluss im
Programm (Zeitlimit 600 s) ab und 155 Nahtkörper kamen als „Drehteil“.

- T1 Stützpunkte liegen auf dem Körper (Abstand 0) – Grundlage dafür, dass „sicher nah“ nie falsch ist
- T2 sicher_nah: Punkt 5 mm neben der Fläche ja, 20 mm daneben nein
- T3 Gleiches Ergebnis mit und ohne Schnelltest: Rundrohr mit Bund und Naht (E4) und Knotenblech-Gegenprobe
- T4 Jeder Nachbar wird je Nahtkandidat einmal geprüft (nicht je Paar), Stützpunkte einmal je Körper

Aufruf: python tests/test_nahtkoerper_tempo.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_nahtkoerper as nk  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402
from test_step_wie_modell import box  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def zyl(r, z0, h):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), r, h).Shape()


def messen(shape, name):
    et.schreibe(shape, name, TMP)
    return [(t.profilform, t.bauteiltyp, tuple(t.hinweise or ())) for t in analysiere_datei(TMP / f"{name}.step")]


# T1
rr = et.rundrohr(40, 2, 35)
st = nk._Stuetz(rr)
punkte = [p for zelle in st.zellen.values() for p in zelle]
assert len(punkte) >= 40, len(punkte)
for p in punkte[::7]:
    d = nk._abstand(BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex(), rr)
    assert d is not None and d < 1e-6, (p, d)
print("OK: T1 Stützpunkte liegen auf dem Körper")

# T2
platte = box(0, 0, 0, 200, 200, 5)
sp = nk._Stuetz(platte)
assert sp.sicher_nah(gp_Pnt(3, 3, 10)) and not sp.sicher_nah(gp_Pnt(3, 3, 25))
assert not sp.sicher_nah(gp_Pnt(100, 100, 10))     # Flächenmitte: kein Stützpunkt nah, dort rechnet zuordnen exakt
print("OK: T2 sicher nah nur bis NAHT_SCHENKEL")

# T3 + T4
bund = et.cut(zyl(35, -8, 8), zyl(18, -9, 10))
naht = et.cut(BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 24, 20, 4).Shape(), zyl(20, -1, 6))
r1 = et.kastenrohr(40, 40, 2, 300, 4)
r2 = et.verschiebe(et.kastenrohr(40, 40, 2, 300, 4), 100, 0, 0)
FAELLE = {"RR_Bund_Naht": et.baugruppe(rr, bund, naht), "Knotenblech": et.baugruppe(r1, r2, box(20, -3, 50, 60, 6, 120))}
zaehler = {"abstand": 0, "stuetz": 0}
abstand, stuetz_init = nk._abstand, nk._Stuetz.__init__


def abstand_zaehlen(a, b):
    zaehler["abstand"] += 1
    return abstand(a, b)


def stuetz_zaehlen(self, k):
    zaehler["stuetz"] += 1
    stuetz_init(self, k)


nk._abstand, nk._Stuetz.__init__ = abstand_zaehlen, stuetz_zaehlen
schnell = {n: messen(s, n) for n, s in FAELLE.items()}
n_schnell = zaehler["abstand"]
assert 0 < zaehler["stuetz"] <= 4, zaehler                # einmal je Nachbarkörper
nk._Stuetz.sicher_nah = lambda self, p: False             # ohne Schnelltest: jeder Punkt exakt wie bisher
zaehler["abstand"] = 0
exakt = {n: messen(s, n) for n, s in FAELLE.items()}
assert schnell == exakt, (schnell, exakt)
assert any(p == "Schweißnaht (Körper)" for p, _, _ in schnell["RR_Bund_Naht"]), schnell["RR_Bund_Naht"]
assert all(p != "Schweißnaht (Körper)" for p, _, _ in schnell["Knotenblech"]), schnell["Knotenblech"]
assert n_schnell < zaehler["abstand"], (n_schnell, zaehler["abstand"])
print(f"OK: T3/T4 gleiches Ergebnis mit und ohne Schnelltest; exakte Abstände {zaehler['abstand']} → {n_schnell}")
print("Alle Tests bestanden.")
