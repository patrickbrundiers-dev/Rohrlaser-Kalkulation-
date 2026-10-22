"""Fälle aus Patricks Baugruppe 00_Rahmengestell (22.10.2026):

- Nicht übernehmbare STEP-Teile: auch nicht messbare Körper bekommen ein Dreiecksnetz in Dateilage (Art 'N'), damit
  der Prüfdialog zeigt, welches Teil fehlt und wo es in der Baugruppe sitzt; die Zeile zeigt den Grund mit Hüllmaß über
  die ganze Breite, Anklicken hebt das Teil in der 3D-Baugruppe hervor. (Die beiden Rohre, die dort nicht messbar
  waren, prüft tests/test_step_regression.py als R06.)
- Flache Teile: Vorgabe Blech (Einstellung flach_als, Messung mit --flachstahl-bis 0), Flachstahl bleibt als andere Art
  wählbar; R07 = FL 80x8 mit Senkungen, früher weder Blech noch wählbar (Volumenprüfung ohne Senkungen).

Aufruf: python tests/test_step_rahmengestell.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import step_messen  # noqa: E402
from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())


def messen(datei, name, *zusatz):
    netze = tmp / f"netze_{name}"
    step_messen.main(["--ausgabe", str(tmp / f"{name}.txt"), "--netze", str(netze), *zusatz, str(datei)])
    return step.lade_netze(step.lies_messwerte(tmp / f"{name}.txt"), netze)


# 1) Messung: offener Flächenkörper (nicht messbar) bekommt ein Rohnetz in Dateilage
mw = messen(HIER / "step_referenz" / "REF14_Flaechenmodell_mit_loser_Flaeche.step", "ref14")
offen = next(m for m in mw if m["pruefstatus"] == "nicht messbar")
netz = json.loads((tmp / "netze_ref14" / offen["netz"]).read_text(encoding="utf-8"))
assert list(netz["t"]) == ["N"] and netz["lage"] == [0, 0, 0, 0, 0, 1, 1, 0, 0] and len(netz["p"]) >= 9, netz.keys()
print("OK     nicht messbarer Körper: Dreiecksnetz in Dateilage (Art N)")

# 2) Prüfdialog: Baugruppe mit einem nicht übernehmbaren Teil
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
from rohrlaser.ansicht3d import entpacken  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog, grund  # noqa: E402
mw = messen(HIER / "step_satz" / "T08_Gestell_Baugruppe.step", "t08")
assert len(mw) == 4 and all(m.get("_netz") for m in mw)
m = mw[-1]                              # als nicht messbar ausgeben (wie früher Körper 13 der Rahmengestell-Datei)
m.update(profilform="", pruefstatus="nicht messbar", profil_id_vorschlag="",
         hinweise="Kein Profilquerschnitt gefunden (Querschnitt nicht über die Länge gleich?)")
assert "Hüllmaß" in grund(m) and grund(m).startswith("Kein Profilquerschnitt"), grund(m)
d = StepPruefDialog(None, mw, k, "S235-10219", 1)
datei = m["datei"]
fg = d.fehler_gruppen[datei]
assert fg.text(0).startswith("Nicht übernehmbar – 1 Teil") and "magenta" in fg.text(0), fg.text(0)
it = fg.child(0)
assert it.isFirstColumnSpanned() and "Kein Profilquerschnitt" in it.text(0) and "Hüllmaß" in it.text(0), it.text(0)
assert not it.icon(0).isNull()
# Baugruppe: alle 4 Teile, das nicht übernehmbare magenta
d._zeigen(d.baugruppen[datei])
n = d.ansicht.ansicht.netz
assert "N" in n["t"] and "magenta: 1 nicht übernehmbares Teil" in d.ansicht.info.text(), d.ansicht.info.text()
alle = len(n["p"])
# Zeile anklicken: Teil blau hervorgehoben, Grund oben in der Info
d._zeigen(it)
n = d.ansicht.ansicht.netz
assert len(n["p"]) == alle and set(n["t"]) == {"S", "X"}, list(n["t"])
assert "Nicht übernehmbar: Kein Profilquerschnitt" in d.ansicht.info.text()
assert len(n["t"]["S"]) == sum(len(i) for a, i in entpacken(m["_netz"])["t"].items() if a != "I")
d._zeigen(fg)                                                       # Gruppe: alle nicht übernehmbaren Teile
assert "S" in d.ansicht.ansicht.netz["t"]
d.ansicht.ansicht.grab()
# Einzeldatei mit nicht messbarem Teil: Rohnetz allein mit Legende
d2 = StepPruefDialog(None, [dict(m, datei="einzeln.step", artikel="einzeln")], k, "S235-10219", 1)
d2._zeigen(d2.fehler_gruppen["einzeln.step"].child(0))
assert d2.ansicht.ansicht.modell is not None and "Nicht übernehmbar" in d2.ansicht.info.text()
print("OK     Prüfdialog: Grund in der Zeile, Teil in der 3D-Baugruppe magenta bzw. gewählt blau")

# 3) Flache Teile: Vorgabe Blech, Flachstahl wählbar
from types import SimpleNamespace  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.stammdaten import FLACH_ALS  # noqa: E402
assert db.einstellung("flach_als") == FLACH_ALS[0] == "Blech"
assert AngebotSeite.flach_bis(SimpleNamespace(db=db)) == 0                # Messung: ebene flache Teile immer Blech
db.einstellung_setzen("flach_als", FLACH_ALS[1])
assert AngebotSeite.flach_bis(SimpleNamespace(db=db)) == 150
db.einstellung_setzen("flach_als", FLACH_ALS[0])
r07 = HIER / "step_regression" / "R07_FL80x8_L100_Senkungen.step"
for bis, art, andere in (("0", "Blech", "Flachstahl"), ("150", "Blech", "Flachstahl")):   # L 100 < 3 × 80: Blech
    m = messen(r07, f"r07_{bis}", "--flachstahl-bis", bis)[0]
    alt = step.alternative(m)
    assert m["profilform"] == art and alt and alt["profilform"] == andere, (bis, m["profilform"], alt)
    assert step.blech(m)["bohrungen"] == {"11.0": 4}, step.blech(m)
b09 = HIER / "step_bleche" / "B09_FL100x10_L800.step"
assert messen(b09, "b09_150", "--flachstahl-bis", "150")[0]["profilform"] == "Flachstahl"   # alte Abgrenzung
m = messen(b09, "b09_0", "--flachstahl-bis", "0")[0]
assert m["profilform"] == "Blech" and step.alternative(m)["profilform"] == "Flachstahl", m["profilform"]
d3 = StepPruefDialog(None, [m], k, "S235-10219", 1, zukauf_liste=[])
from PySide6.QtWidgets import QComboBox  # noqa: E402
art = d3.baum.itemWidget(d3.zeilen[0].it, d3.SP_ART)
assert isinstance(art, QComboBox) and art.count() == 2 and "Flachstahl" in art.itemText(1), art
art.setCurrentIndex(1)                                              # auf Flachstahl umstellen
assert d3.messwerte[0]["profilform"] == "Flachstahl" and not step.blech(d3.messwerte[0])
print("OK     flache Teile: Vorgabe Blech, Flachstahl im Prüfdialog wählbar, Senkungen stören die Blecherkennung nicht")
db.schliessen()
shutil.rmtree(tmp, ignore_errors=True)
