"""docs/KALKULATION_FORMELN.md (Plan X8): Formelteil aktuell, Parameter-Tabellen erzeugbar. Neue Felder anderer
Änderungen lassen den Test grün (die Tabellen werden beim nächsten Erzeugen ergänzt), damit kein paralleler Zweig
an der Doku scheitert.

Aufruf: python tests/test_formeln_doku.py   (bei Abweichung: python docs/erzeuge_formeln.py)
"""
import importlib.util
from pathlib import Path

HIER = Path(__file__).parent
spec = importlib.util.spec_from_file_location("erzeuge_formeln", HIER.parent / "docs" / "erzeuge_formeln.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ist = m.ZIEL.read_text(encoding="utf-8")
assert ist.startswith(m.FORMELN.strip()), "Formelteil veraltet: python docs/erzeuge_formeln.py ausführen"
neu = m.inhalt()
assert neu.startswith(m.FORMELN.strip()) and "## Parameter: Stammdaten" in neu
for wort in ("Laserzeit netto", "Herstell", "Rüstzeit je Los", "Qualität", "Qualitätsstufen", "zuschlag_fertigung"):
    assert wort in ist, wort
print("OK: Formel-Dokumentation aktuell")
