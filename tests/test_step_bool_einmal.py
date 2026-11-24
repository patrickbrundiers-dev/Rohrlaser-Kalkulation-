"""STEP-Import Tempo (Patrick 21.11.2026 „Ist der STEP-Import jetzt besser und schneller geworden?“): jede Boolesche
Operation der Messung wird genau einmal gerechnet.

BRepAlgoAPI_Fuse(a, b) (ebenso Cut, Common) rechnet schon im Konstruktor; ein SetFuzzyValue + Build() danach rechnete
alles ein zweites Mal (U-Profil 80×40×4 mit Konturen: 18,9 s statt 11,4 s). Geprüft wird:
- step_geometrie.boolesch rechnet und, plus, minus richtig (Volumen zweier Quader, mit und ohne Toleranz),
- kein Modul der Messung baut eine Boolesche Operation mit Argumenten im Konstruktor und ruft danach Build(),
- das offene U-Profil K07 ergibt mit boolesch dieselbe Messung wie mit dem doppelten Rechnen (alter Ablauf
  nachgebaut).
Aufruf: python tests/test_step_bool_einmal.py
"""
import json
import re
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
MESSUNG = HIER.parent / "programm" / "step_messung"
sys.path.insert(0, str(MESSUNG))

import step_geometrie as g  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("ok    " if bedingung else "FEHLER ") + text)
    if not bedingung:
        fehler.append(text)


# 1. Ergebnis
a = BRepPrimAPI_MakeBox(10, 10, 10).Shape()
b = BRepPrimAPI_MakeBox(5, 5, 20).Shape()
for art, soll in (("und", 250.0), ("plus", 1250.0), ("minus", 750.0)):
    for fuzzy in (g.FUZZY, 0):
        op = g.boolesch(art, a, b, fuzzy=fuzzy)
        pruefe(op.IsDone() and abs(g._volumen(op.Shape()) - soll) < 1e-6,
               f"boolesch {art} (Toleranz {fuzzy}): Volumen {soll:g}")

# 2. kein doppeltes Rechnen im Quelltext: Konstruktor mit Argumenten und danach .Build() auf derselben Variablen
muster = re.compile(r"^\s*(\w+)\s*=\s*(?:BRepAlgoAPI_(?:Fuse|Cut|Common)|\{[^}]*BRepAlgoAPI[^}]*\}\[\w+\])\((?!\))")
for datei in sorted(MESSUNG.glob("*.py")):
    zeilen = datei.read_text(encoding="utf-8").splitlines()
    for i, z in enumerate(zeilen):
        m = muster.match(z)
        if m and any(re.match(rf"^\s*{m.group(1)}\.Build\(\)", n) for n in zeilen[i + 1:i + 6]):
            pruefe(False, f"{datei.name}:{i + 1}: Boolesche Operation doppelt gerechnet ({z.strip()[:60]})")
pruefe(True, "Quelltext der Messung: keine Boolesche Operation doppelt gerechnet")

# 3. gleiche Messung wie mit dem alten, doppelten Ablauf
import step_messen  # noqa: E402

K07 = HIER / "step_konturen" / "K07_U80x40x4_Lage.step"
neu = json.dumps(step_messen.messen(K07, None)[1], sort_keys=True, default=str)
_einmal = g.boolesch


def _doppelt(art, a, b, fuzzy=g.FUZZY):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    op = {"und": BRepAlgoAPI_Common, "plus": BRepAlgoAPI_Fuse, "minus": BRepAlgoAPI_Cut}[art](a, b)
    if fuzzy:
        op.SetFuzzyValue(fuzzy)
    op.Build()
    return op


g.boolesch = _doppelt
try:
    alt = json.dumps(step_messen.messen(K07, None)[1], sort_keys=True, default=str)
finally:
    g.boolesch = _einmal
pruefe(alt == neu, "K07 U80x40x4 (offenes Profil): Messung gleich wie mit doppeltem Rechnen")
pruefe("Offenes Rohr" in neu, "K07: offenes Rohr wurde geschlossen (der geänderte Ablauf lief wirklich)")

if fehler:
    print(f"\n{len(fehler)} Fehler")
    sys.exit(1)
print("\nalle Prüfungen ok")
