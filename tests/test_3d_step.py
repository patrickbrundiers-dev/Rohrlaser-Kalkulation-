"""Prüft die 3D-Schnittbearbeitung im STEP-Import (Plan kalkulation/3d-schnitt, Patrick 22.10.2026, Tests 8/9):
- T1 Messung: schräge Bohrungen mit Neigung längs (+ Richtung Ende B) und quer (+ Richtung steigender
  Umfangswinkel), gerade Bohrungen ohne Neigung (STEP-JSON 1.5)
- T2 Übernahme mit Häkchen 3D: Gehrung am Ende B und schräge Bohrungen in 3D (positionen.technik), 60° wird auf 45°
  begrenzt (WARNUNG nicht maßhaltig); ohne Häkchen 2D und Hinweis „3D prüfen“
- T3 Prüfdialog: Häkchen „3D-Schnittbearbeitung aktivieren“ mit Anzahl gefundener Gehrungen/schräger Bohrungen

Teile werden mit OpenCascade erzeugt (tests/erzeuge_testteile.py) und mit step_messung gemessen.
Aufruf: python tests/test_3d_step.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402

from rohrlaser import dreid, rechnen, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.1):
    return a is not None and abs(a - b) <= tol


tmp = Path(os.environ.get("TESTTMP") or tempfile.mkdtemp())
s30 = math.sin(math.radians(30))
c30 = math.cos(math.radians(30))
r = et.rundrohr(42.4, 2, 600)
R = 21.2                                                                     # oben, 30° quer zur Seite +X:
r = et.cut(r, et.zylinder((-30 * s30, R - 30 * c30, 150), (s30, c30, 0), 8, 45))  # Achse durch (0, R) neben der Mitte
r = et.cut(r, et.zylinder((0, 0, 300), (1, 0, 0), 8, 40))                     # gerade, auf der Seite +X
r = et.cut(r, et.zylinder((0, 0, 450), (0, 0.5, -math.sin(math.radians(60))), 8, 60))   # oben, 60° Richtung A
et.schreibe(r, "D01_RR42-4x2_schraeg", tmp)

# ------------------------------------------------------------------ T1 Messung
(t,) = analysiere_datei(tmp / "D01_RR42-4x2_schraeg.step")
b = sorted((d for d in t.konturen_liste if d.get("art") == "Bohrung"), key=lambda d: d["z"])
assert len(b) == 3, b
quer, gerade, steil = b
assert gerade.get("neigung_l") is None and nah(gerade["schraeg"], 0, 0.05)
seite = gerade["winkel"]
assert nah(seite, 90, 0.5) or nah(seite, 270, 0.5), seite
vz = 1 if nah(seite, 90, 0.5) else -1                  # Seite +X ist 90°: Neigung zur Seite +X ist quer +
# Rundrohr: die Normale wird in der Mitte der (gekrümmten) Austrittsellipse genommen, daher ±1,5°
assert nah(quer["neigung_l"], 0) and nah(quer["neigung_q"], 30 * vz, 1.5), quer
assert nah(steil["neigung_l"], -60) and nah(steil["neigung_q"], 0), steil
k03 = [d for d in analysiere_datei(HIER / "step_konturen" / "K03_RR42-4x2_Konturen.step")[0].konturen_liste
       if d.get("art") == "Bohrung" and d.get("neigung_l") is not None]
assert len(k03) == 1 and nah(k03[0]["neigung_l"], 30) and nah(k03[0]["neigung_q"], 0), k03
ok(f"T1 Neigung gemessen: quer {quer['neigung_q']:+g}° (Seite +X = {seite:g}°), längs −60°, K03 längs +30° "
   "Richtung Ende B, gerade Bohrung ohne Neigung")

# ------------------------------------------------------------------ T2 Übernahme
step_messen.main(["--ausgabe", str(tmp / "m.txt"), str(tmp / "D01_RR42-4x2_schraeg.step"),
                  str(HIER / "step_konturen" / "K01_RE60x40x3_Konturen.step")])
mw = step.lies_messwerte(tmp / "m.txt")
assert [step.kandidaten_3d(m) for m in mw] == [(0, 2), (1, 0)], [step.kandidaten_3d(m) for m in mw]
db = Datenbank(tmp / "rohrlaser.db")
mid = next(z["id"] for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
db.aendern("maschinen", mid, "d3", "ja")
k, gew = db.kontext(), db.zeilen("gewinde")
kopf = dict(maschine="T11", stange=6000)


def importieren(mit_3d):
    werte = [dict(m, _d3=mit_3d) for m in mw]
    return step.uebernehmen(werte, [], k, gew, None, "S235-10219", 5, neue_profile=True)


erg = importieren(True)
rohr, kasten = erg["positionen"]
tr, tk = json.loads(rohr["technik"]), json.loads(kasten["technik"])
assert tr["d3"] is True and tk["d3"] is True and tk["b"].get("d3") is True and not tk["a"].get("d3"), tk
bo = sorted((x for x in tr["konturen"] if x.get("d3")), key=lambda x: x["x"])
assert len(bo) == 2 and nah(bo[0]["neigung_q"], 30 * vz, 1.5) and nah(bo[1]["neigung_l"], -60), bo
k = db.kontext()
m = rechnen.maschine(kopf, k)
assert dreid.pruefen(rohr, m) == "WARNUNG: 3D-Winkel begrenzt, Kontur nicht maßhaltig"
assert not dreid.pruefen(kasten, m)
bearb = dreid.bearbeitungen(kasten, m)
assert [x["art"] for x in bearb] == [dreid.ENDE_B] and nah(bearb[0]["winkel"], 30), bearb
st = rechnen.status(rohr, rechnen.position_werte(rohr, kopf, k, db.tabellen()), kopf, k)
assert "3D" in st and not st.startswith("FEHLER"), st
ok("T2 mit 3D: Gehrung Ende B 30° und schräge Bohrungen in 3D, 60° → 45° mit WARNUNG")
erg = importieren(False)
rohr, kasten = erg["positionen"]
assert "d3" not in json.loads(rohr["technik"]) and not dreid.aktiv(kasten)
assert "3D prüfen: 2 schräge Bohrungen" in erg["bericht"][0] and "3D prüfen" not in erg["bericht"][1], erg["bericht"]
ok("T2 ohne 3D: alles 2D, Teil mit schrägen Bohrungen mit Hinweis „3D prüfen“")

# ------------------------------------------------------------------ T3 Prüfdialog
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
werte = [dict(m) for m in mw]
d = StepPruefDialog(None, werte, k, "S235-10219", 1)
assert not d.d3.isChecked() and "1 Gehrung an Enden, 2 schräge Bohrungen" in d.d3_info.text(), d.d3_info.text()
d.d3.setChecked(True)
d.werte_schreiben()
assert all(m["_d3"] is True for m in werte)
assert StepPruefDialog(None, werte, k, "S235-10219", 1).d3.isChecked()
ok("T3 Prüfdialog: Häkchen 3D mit gefundenen Kandidaten, Wahl geht an die Übernahme")
print("Alle 3D-STEP-Tests bestanden.")
