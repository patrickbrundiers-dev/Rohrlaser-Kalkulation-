"""Prüft die 3D-Schnittbearbeitung im Rohr-Editor (Schneidweg-Rechner, Plan kalkulation/3d-schnitt, Patrick
22.10.2026):
- E1 Häkchen „3D-Schnittbearbeitung aktivieren“, „Gehrung in 3D“ je Ende, Spalten 3D/Neigung längs/quer je Kontur;
  Eingaben werden gespeichert und beim erneuten Öffnen wieder gezeigt
- E2 Bohrung in 3D: Schnittlänge als Ellipse, Hüllmaß d/cos γ; ohne Häkchen am Bauteil wie 2D
- E3 Begrenzung: Neigung 60° wird auf 45° begrenzt, Hinweis und WARNUNG nicht maßhaltig; ungültige Eingabe = Fehler
- E4 Maschine ohne 3D: Hinweis rot, Status FEHLER; Schneidzeit mit 3D höher als ohne

Aufruf: python tests/test_3d_editor.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import dreid, rechnen, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schneidweg_dialog import D3_SPALTE, NL_SPALTE, NQ_SPALTE, SchneidwegDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.05):
    return abs(a - b) <= tol


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
mid = next(z["id"] for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
db.aendern("maschinen", mid, "d3", "ja")
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(a, dict(pos=10, artikel="R3D", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                        stueck=10))
s = fenster.angebot_oeffnen(a)
p = s.positionen[0]
QR = s.k.profile["QR 40x40x3"]

# ------------------------------------------------------------------ E1 Bedienung und Speichern
d = SchneidwegDialog(s, p, QR, s.kopf, s.k, s.tabellen)
assert not d.d3.isChecked() and not d.ende_3d["b"].isEnabled()
d.winkel["b"].setValue(30)
d.zeile_neu(dict(art="Bohrung", anzahl=1, d=10, x=500, seite=0))
r = d.tabelle.rowCount() - 1
d.d3.setChecked(True)
assert d.ende_3d["b"].isEnabled() and not d.ende_3d["a"].isEnabled()     # Ende A ohne Gehrung
d.ende_3d["b"].setChecked(True)
d.tabelle.item(r, D3_SPALTE).setCheckState(Qt.Checked)
d.tabelle.cellWidget(r, NL_SPALTE).setCurrentText("+30°")
d.tabelle.cellWidget(r, NQ_SPALTE).setCurrentText("−45°")
e = d.eingaben()
assert e["d3"] is True and e["b"]["d3"] is True and not e["a"].get("d3")
k = e["konturen"][-1]
assert k["d3"] is True and k["neigung_l"] == 30 and k["neigung_q"] == -45, k
assert "T11" in d.d3_info.text() and "Greifmaß 300" in d.d3_info.text()
d2 = SchneidwegDialog(s, dict(p, technik=sw.speichern(e)), QR, s.kopf, s.k, s.tabellen)
assert d2.d3.isChecked() and d2.ende_3d["b"].isChecked()
assert d2.tabelle.item(r, D3_SPALTE).checkState() == Qt.Checked
assert d2.tabelle.cellWidget(r, NL_SPALTE).currentText() == "+30°"
assert d2.tabelle.cellWidget(r, NQ_SPALTE).currentText() == "−45°"
assert d2.eingaben() == e
ok("E1 Häkchen Bauteil/Ende/Kontur und Neigungen gespeichert und wieder geöffnet")

# ------------------------------------------------------------------ E2 Bohrung in 3D
m = rechnen.maschine(s.kopf, s.k)
grenzen = rechnen.kontur_regel(m, rechnen.wand_schneiden(QR))
e1 = dict(d3=True, a={}, b={}, konturen=[dict(art="Bohrung", anzahl=1, d=10, d3=True, neigung_l=30)])
erg = sw.rechnen(e1, QR, grenzen, None, m)
schritt = erg["schritte"][-1]
assert nah(schritt["laenge_stueck"], dreid.ellipse(5, 5 / math.cos(math.radians(30))), 0.01), schritt
assert nah(schritt["huelle"], 10 / math.cos(math.radians(30)), 0.01) and "3D" in schritt["text"]
erg0 = sw.rechnen(dict(e1, d3=False), QR, grenzen, None, m)
assert nah(erg0["schritte"][-1]["laenge_stueck"], math.pi * 10, 0.01) and "3D" not in erg0["schritte"][-1]["text"]
ok("E2 Bohrung 30° längs: Ellipse und Hüllmaß d/cos; ohne Häkchen am Bauteil wie 2D")

# ------------------------------------------------------------------ E3 Begrenzung und Fehler
e3 = dict(e1, konturen=[dict(e1["konturen"][0], neigung_l=60)])
erg = sw.rechnen(e3, QR, grenzen, None, m)
assert erg["hinweise_3d"] and any("45" in h for h in erg["hinweise"]), erg["hinweise"]
assert nah(erg["schritte"][-1]["huelle"], 10 / math.cos(math.radians(45)), 0.01)
assert dreid.pruefen(dict(p, technik=sw.speichern(e3)), m).startswith("WARNUNG: 3D-Winkel begrenzt")
d.tabelle.cellWidget(r, NL_SPALTE).setCurrentText("+60°")
d.rechnen()
assert "begrenzt" in d.summe.text() and d.ok_knopf.isEnabled()
erg = sw.rechnen(dict(e1, konturen=[dict(e1["konturen"][0], neigung_l="abc")]), QR, grenzen, None, m)
assert any("3D" in f for f in erg["fehler"]), erg["fehler"]
ok("E3 Neigung 60° auf 45° begrenzt (Hinweis, WARNUNG), ungültige Neigung = Fehler")

# ------------------------------------------------------------------ E4 Maschine ohne 3D, Zeit
d.tabelle.cellWidget(r, NL_SPALTE).setCurrentText("+30°")
d.rechnen()
mit = d.schneidzeit()
d.d3.setChecked(False)
ohne = d.schneidzeit()
assert mit is not None and ohne is not None and mit > ohne, (mit, ohne)
db.aendern("maschinen", mid, "d3", "nein")
s.neu_laden()
d4 = SchneidwegDialog(s, dict(p, technik=sw.speichern(e)), QR, s.kopf, s.k, s.tabellen)
assert "kann keine 3D" in d4.d3_info.text() and "B42318" in d4.d3_info.text()
assert "FEHLER" in d4.summe.text()
ok("E4 Schneidzeit mit 3D höher; Maschine ohne 3D: Hinweis rot und FEHLER")
print("Alle Tests Rohr-Editor 3D bestanden.")

# ------------------------------------------------------------------ E5 Skizze
from rohrlaser import skizze as sk  # noqa: E402

b = dict(art="Bohrung", d=10, d3=True, neigung_l=30)
pts = sk.umriss_kontur(b)
breite = max(x for x, _ in pts) - min(x for x, _ in pts)
assert nah(breite, 10 / math.cos(math.radians(30)), 0.05) and "3D" in sk.kurz(b)
assert "3D" not in sk.kurz(dict(b, d3=False))
from rohrlaser.schneidweg_dialog import ohne_3d  # noqa: E402
assert "d3" not in ohne_3d(dict(konturen=[b]))["konturen"][0] and ohne_3d(dict(d3=True, konturen=[b]))["konturen"][0]["d3"]
ok("E5 Skizze: schräge Bohrung als Ellipse mit „3D“, ohne Häkchen am Bauteil rund")
print("Skizze 3D bestanden.")
