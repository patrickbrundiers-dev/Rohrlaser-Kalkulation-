"""Merker im __dict__ eines Fensters dürfen nicht wie eine Methode heißen (Support-Paket 06.11.2026).

teilen_fenster.puls legte fenster.__dict__["_teilen_puls"] an; so hieß auch der Timer-Slot des Hauptfensters.
PySide sucht den Slot beim Aufruf über den Namen und fand das dict: alle 15 s „'dict' object is not callable“.
Prüft alle Module: kein Name aus obj.__dict__.setdefault("…") ist zugleich eine Methode einer Klasse.

Aufruf: python tests/test_merker_namen.py
"""
import ast
from pathlib import Path

QUELLE = Path(__file__).parent.parent / "programm" / "rohrlaser"

merker, methoden = {}, {}
for datei in sorted(QUELLE.rglob("*.py")):
    baum = ast.parse(datei.read_text(encoding="utf-8"), str(datei))
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.ClassDef):
            for f in knoten.body:
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methoden.setdefault(f.name, []).append(f"{datei.name}:{knoten.name}")
        elif (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
              and knoten.func.attr == "setdefault" and isinstance(knoten.func.value, ast.Attribute)
              and knoten.func.value.attr == "__dict__" and knoten.args
              and isinstance(knoten.args[0], ast.Constant) and isinstance(knoten.args[0].value, str)):
            merker.setdefault(knoten.args[0].value, []).append(f"{datei.name}:{knoten.lineno}")

assert len(merker) >= 10, merker
gleich = {n: (merker[n], methoden[n]) for n in merker if n in methoden}
assert not gleich, f"Merker heißt wie eine Methode (überdeckt sie): {gleich}"
assert "_teilen_puls_merk" in merker and "_teilen_puls" in methoden
print("OK     Kein Merker im __dict__ heißt wie eine Methode", f"({len(merker)} Merker geprüft)")
