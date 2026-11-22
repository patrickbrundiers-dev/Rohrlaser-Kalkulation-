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
# Benchmark-Suite (Master-Auftrag 21.11.2026): Schema, Größe, Kennzahlen, Bericht je Schema/Datei
(tmp / "a203.step").write_text("ISO-10303-21;\nHEADER;\nFILE_SCHEMA (( 'CONFIG_CONTROL_DESIGN' ));\nENDSEC;")
(tmp / "a242.stp").write_text("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));")
assert sb.kategorie(tmp / "a203.step")["schema"] == "AP203" and sb.kategorie(tmp / "a242.stp")["schema"] == "AP242"
assert sb.kategorie(tmp / "a203.step")["groesse"] == "bis 1 MB"
mess = {"dateien": [{"baugruppe": True, "koerper": [
    {"nr": 1, "bauteiltyp": "Profil", "profiltyp": "Rundrohr"},
    {"nr": 2, "art_grund": "Norm DIN 933 im Bauteilnamen", "bauteiltyp": "Drehteil"},
    {"nr": 3, "art_grund": "Normteil: Mutter SW 13", "bauteiltyp": "Drehteil"},
    {"nr": 4, "fehler": "nicht messbar"}]}]}
(tmp / "m.json").write_text(json.dumps(mess))
k = sb.kennzahlen(tmp / "m.json", {"1": "Rundrohr", "2": "Drehteil", "4": "Blech"})
assert k == dict(koerper_n=4, fehler_n=1, normteile_n=2, baugruppe=True, erwartet_n=3, treffer_n=2), k
(tmp / "s").mkdir()
(tmp / "s" / "benchmark.json").write_text(json.dumps({"x.step": dict(dauer_s=3.0, ram_mb=300, cpu_auslastung=1.1,
                                                                     schema="AP214", groesse="bis 1 MB", mb=0.2,
                                                                     schritte={"lesen_s": 0.5, "messen_s": 2.0}, **k)}))
text = sb.suite(tmp / "s", tmp / "s.md")
assert "| AP214 | bis 1 MB | 1 | 4 | 2 | 1 | 3.0 | 300 |" in text and "2 von 3 Körpern wie erwartet (66.7 %)" in text, text
assert "| 0.50 |" in text and "| 2.00 |" in text, text
print("OK: Suite mit Schema (AP203/214/242), Größe, Normteilen, Fehlern, Trefferquote, Zeit je Schritt")
print("Alle Tests bestanden.")
