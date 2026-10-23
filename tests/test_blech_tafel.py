"""Tafelausnutzung im Blech-Richtpreis (Plan S4, Abschnitt 5.5):
- T1 Tafelformate aus der Einstellung lesen (×, x, *, Komma, unlesbare Einträge fehlen).
- T2 Tafelbedarf: Raster mit gedrehtem Reststreifen, volle Tafeln ganz, die letzte mit der belegten Fläche samt Rand,
  kleinstes Format gewinnt, zu große Teile passen auf keine Tafel.
- T3 Richtpreis: Material je Stück sinkt mit der Losgröße, 'pauschaler Verschnitt' rechnet wie bisher, Teil größer
  als jede Tafel: pauschal mit Hinweis; Blech-Editor zeigt
  den Tafelbedarf.

Aufruf: python tests/test_blech_tafel.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import blech  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ T1 Formate
assert blech.tafelformate("3000 × 1500; 2500x1250; 1250*2500; 2000,5 X 1000; Rest; 0 × 100") == [
    (3000, 1500), (2500, 1250), (2500, 1250), (2000.5, 1000)]
assert blech.tafelformate("") == [] and blech.tafelformate(None) == []
from rohrlaser.stammdaten import EINSTELLUNGEN  # noqa: E402
vorgaben = {x.name: x.vorgabe for x in EINSTELLUNGEN}
for n in ("blech_material", "blech_tafeln", "blech_tafel_rand", "blech_tafel_steg"):
    assert vorgaben[n] == blech.EINSTELLUNGEN[n], n
TAFELN = blech.tafelformate(vorgaben["blech_tafeln"])
assert TAFELN == [(3000, 1500), (2500, 1250)]
ok("T1 Tafelformate aus der Einstellung (Vorgabe 3000 × 1500 und 2500 × 1250)")

# ------------------------------------------------------------------ T2 Tafelbedarf
t = blech.tafelbedarf(200, 100, 1, TAFELN)
assert t["format"] == (3000, 1500) and t["voll"] == 0 and t["rest"] == (220, 120) and t["flaeche"] == 220 * 120
# Raster 14 × 14 = 196 (Teilung 205 × 105 auf 2985 × 1485), mit gedrehtem Reststreifen mehr; Obergrenze Fläche
je = t["je_tafel"]
assert 196 < je <= int(2985 * 1485 / (205 * 105)) and je == 203, je
voll = blech.tafelbedarf(200, 100, 2 * je, TAFELN)
assert voll["voll"] == 2 and voll["rest"] is None and voll["flaeche"] == 2 * 3000 * 1500 and voll["tafeln"] == 2
zehn = blech.tafelbedarf(200, 100, 10, TAFELN)
assert zehn["rest"] == (425, 540)                                       # 2 × 5 gedreht: kleinste belegte Fläche
# gleicher Bedarf auf beiden Formaten: das erste bleibt
klein = blech.tafelbedarf(1200, 1200, 2, TAFELN)
assert klein["je_tafel"] == 2 and klein["format"] == (3000, 1500) and klein["rest"] == (2425, 1220)
gross = blech.tafelbedarf(2400, 1200, 1, TAFELN)
assert gross["format"] == (3000, 1500) and gross["rest"] == (2420, 1220)
assert blech.tafelbedarf(2400, 1200, 1, [(2500, 1250)])["rest"] == (2420, 1220)
assert blech.tafelbedarf(3100, 100, 3, TAFELN) is None and blech.tafelbedarf(100, 100, 3, []) is None
# Ausnutzung steigt mit der Losgröße
a = [blech.tafelbedarf(200, 100, n, TAFELN)["ausnutzung"] for n in (1, 10, 100)]
assert a[0] < a[1] < a[2] < 1, a
ok("T2 Tafelbedarf: Raster mit Reststreifen, letzte Tafel nur belegte Fläche, Ausnutzung steigt mit dem Los")

# ------------------------------------------------------------------ T3 Richtpreis, Staffel, Editor
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
werkstoffe = {z["blech_werkstoff_id"]: z for z in db.zeilen("blech_werkstoffe")}
laser = db.zeilen("blechlaser")
einst = db.blech_einstellungen()
assert einst["blech_material"] == blech.MATERIAL_AUS[0]
e = dict(werkstoff="S235JR", dicke=3, art=blech.ZUSCHNITT, laenge=200, breite=100, konturen=[])


def material(stueck, **w):
    erg = blech.rechnen(dict(e, stueck=stueck), werkstoffe, laser, dict(einst, **w))
    return erg, erg["kosten"]["Material"]


e1, m1 = material(1)
e100, m100 = material(100)
assert e1["tafel"]["rest"] == (220, 120) and abs(e1["gewicht_tafel"] - 220 * 120 * 3 * 7.85 / 1e6) < 1e-9
assert m100 < m1 and e100["richtpreis"] < e1["richtpreis"]
p, mp = material(100, blech_material=blech.MATERIAL_AUS[1])
assert p["tafel"] is None and abs(p["gewicht_tafel"] - 20000 * 1.15 * 3 * 7.85 / 1e6) < 1e-9
riesig = blech.rechnen(dict(e, laenge=4000), werkstoffe, laser, einst)
assert riesig["tafel"] is None and any(h.startswith("Tafel: Zuschnitt passt auf kein") for h in riesig["hinweise"])
assert abs(riesig["gewicht_tafel"] - 400000 * 1.15 * 3 * 7.85 / 1e6) < 1e-9
eigene = blech.rechnen(dict(e, laenge=4000, stueck=1), werkstoffe, laser,
                       dict(einst, blech_tafeln="6000 × 2000", blech_tafel_rand=0, blech_tafel_steg=0))
assert eigene["tafel"]["rest"] == (4000, 100)
ok("T3 Richtpreis: Material aus dem Tafelbedarf, pauschal wie bisher, zu große Teile mit Hinweis")

d = BlechDialog(None, db, dict(e, stueck=100))
assert "Tafel 3000 × 1500: 203 Stück je Tafel" in d.summe.text() and "für 100 Stück" in d.summe.text(), \
    d.summe.text()
db.schliessen()
ok("T3 Blech-Editor zeigt Format, Stück je Tafel, Tafelbedarf und Ausnutzung")
