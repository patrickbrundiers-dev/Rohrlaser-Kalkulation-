"""Normteile in der 3D-Ansicht der Baugruppe (Master-Prompt Patrick 21.11.2026 „Intelligente Normteil- und
Zukaufteil-Erkennung“, Punkt Visualisierung): Normteile bleiben sichtbar, mit eigener Farbe und Filter.

- A1 ansicht3d.baugruppe: Normteile als Art NT (eigene Farbe, Legende), gewählte bleiben blau, übrige Teilfarben
- A2 Filter: alle / ohne Zukaufteile / nur Zukaufteile / nur unsichere Vorschläge (step_dialog.zk_sichtbar)

Aufruf: python tests/test_normteil_ansicht.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent.parent / "programm"))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from rohrlaser import ansicht3d, step_dialog  # noqa: E402

LAGE = [0, 0, 0, 0, 0, 1, 1, 0, 0]


def netz(x):
    return {"p": [x, 0, 0, x + 1, 0, 0, x, 1, 0], "t": {"A": [0, 1, 2]}, "lage": LAGE}


# A1
n, ohne = ansicht3d.baugruppe([netz(0), netz(5), netz(10)], normteile={1, 2})
assert ohne == 0 and set(n["t"]) == {"F0", "NT"}, n["t"]
assert len(n["t"]["NT"]) == 6, n["t"]
assert "NT" in ansicht3d.FARBE and "NT" in ansicht3d.REIHE
n, _ = ansicht3d.baugruppe([netz(0), netz(5)], hervor={1}, normteile={1})
assert set(n["t"]) == {"X", "S"}, n["t"]          # gewählt: blau, auch wenn Normteil
n, _ = ansicht3d.baugruppe([netz(0), netz(5)])
assert "NT" not in n["t"], n["t"]                   # ohne Angabe wie bisher
print("OK: A1 Normteile eigene Farbe (NT), gewählte blau, sonst wie bisher")

# A2
fertigung, normteil = {}, {"_normteil": "Schraube"}
vorschlag = {"_zukaufteil": {"vertrauen": "Vorschlag", "kategorie": "Scheibe"}}
sicht = {f: [step_dialog.zk_sichtbar(m, f) for m in (fertigung, normteil, vorschlag)] for f in range(4)}
assert sicht == {0: [True, True, True], 1: [True, False, True], 2: [False, True, False], 3: [False, False, True]}, sicht
assert len(step_dialog.ZK_FILTER) == 4
print("OK: A2 Filter alle / ohne Zukaufteile / nur Zukaufteile / nur Vorschläge")
print("Alle Tests bestanden.")
