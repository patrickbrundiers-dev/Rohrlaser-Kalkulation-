"""Vergleichswerkzeug der STEP-Messung (werkzeuge/step_benchmark.py, Master-Prompt Performance 21.11.2026, Punkt 5):
ungerundete Messwerte bitgleich vergleichen, Toleranz nur auf Wunsch, flüchtige Felder ignorieren; Bericht mit Faktor.

Aufruf: python tests/test_step_benchmark.py
"""
import json
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "werkzeuge"))
import step_benchmark as sb  # noqa: E402

a = {"erzeugt": "gestern", "dateien": [{"laenge": 1250.0000000001, "konturen": [{"z": 10.0}], "art": "Rundrohr"}]}
b = {"erzeugt": "heute", "dateien": [{"laenge": 1250.0, "konturen": [{"z": 10.0}, {"z": 20.0}], "art": "Rundrohr"}]}
u = sb.unterschiede(a, b)
pfade = [p for p, _, _ in u]
assert ".dateien[0].laenge" in pfade and ".dateien[0].konturen[Anzahl]" in pfade, u     # bitgleich: 1e-10 zählt
assert ".erzeugt" not in pfade, u                                                         # Zeitpunkt zählt nicht
assert [p for p, _, _ in sb.unterschiede(a, b, toleranz=1e-9)] == [".dateien[0].konturen[Anzahl]"]
assert sb.unterschiede({"x": True}, {"x": 1}) == [(".x", True, 1)]                         # bool ist keine Zahl
assert sb.unterschiede({"x": "a"}, {}) == [(".x", "a", "—")]
print("OK: Unterschiede ungerundet, Toleranz, flüchtige Felder")

tmp = Path(tempfile.mkdtemp())
for name, daten, dauer in (("alt", a, 10.0), ("neu", dict(a, erzeugt="x"), 4.0)):
    (tmp / name).mkdir()
    (tmp / name / "T1.step.json").write_text(json.dumps(daten))
    (tmp / name / "benchmark.json").write_text(json.dumps({"T1.step": {"dauer_s": dauer, "ram_mb": 300}}))
e = sb.vergleich(tmp / "alt", tmp / "neu", bericht=tmp / "b.md")
assert e["gleich"] == 1 and not e["anders"] and e["faktor"] == 2.5, e
assert "Faktor **2.5**" in (tmp / "b.md").read_text(encoding="utf-8")
(tmp / "neu" / "T1.step.json").write_text(json.dumps(b))
assert sb.main(["vergleich", str(tmp / "alt"), str(tmp / "neu")]) == 1
print("OK: Vergleich zweier Läufe mit Faktor und Bericht; Abweichung -> Rückgabe 1")
print("Alle Tests bestanden.")
