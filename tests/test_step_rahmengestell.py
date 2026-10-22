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
from rohrlaser.ansicht3d import entpacken  # noqa: E402
v = dict(offen)
assert step.von_hand(v, "Quadratrohr", "QR 40x40x3", {}) and list(entpacken(v["_netz"])["t"]) == ["A"]
assert step.von_hand_zuruecknehmen(v) and list(entpacken(v["_netz"])["t"]) == ["N"] and v["pruefstatus"] == "nicht messbar"
print("OK     nicht messbarer Körper: Dreiecksnetz in Dateilage (Art N), nach Nachtrag Außenwand")

# 2) Prüfdialog: Baugruppe mit einem nicht übernehmbaren Teil
from PySide6.QtCore import Qt  # noqa: E402
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

# 2b) Von Hand nachtragen: Profilform + Profil-ID, Länge aus Hüllmaß; zurücknehmen; Art bei jeder Zeile wählbar
i = it.data(1, 0x0100)
nach = it.child(0)
assert nach.text(0) == "Von Hand nachtragen:" and d.baum.itemWidget(nach, d.SP_WERKSTOFF).text() == "Nachtragen"
form_cb = d.baum.itemWidget(nach, d.SP_ART)
form_cb.setCurrentIndex(form_cb.findData("Quadratrohr"))
pid_cb = d.baum.itemWidget(nach, d.SP_PROFIL)
assert pid_cb.count() and all(d.k.profile[pid_cb.itemText(n)]["form"] == "Quadratrohr" for n in range(pid_cb.count()))
huelle = sorted(float(x) for x in m["huelle"].split("|"))
z = d.von_hand(i, "Quadratrohr", "QR 40x40x3")
mm = d.messwerte[i]
assert z is not None and i in z.liste and z.it.checkState(0) == Qt.Checked and not d.fehler_gruppen
assert mm["profilform"] == "Quadratrohr" and float(mm["laenge"]) == huelle[-1] and mm["pruefstatus"] == "prüfen"
assert step.VON_HAND in z.it.text(d.SP_HINWEIS) and z.pr.currentText() == "QR 40x40x3"
art_cb = d.baum.itemWidget(z.it, d.SP_ART)
assert step.VON_HAND in art_cb.itemText(0) and art_cb.itemData(1) == "zurueck"
d.werte_schreiben()
assert step._rohrteil(mm) and step.gewaehlt(mm) and (mm.get("_profil") or step.profil_vorschlag(mm, d.k.profile)) == "QR 40x40x3"
art_cb.setCurrentIndex(1)                                           # Nachtrag zurücknehmen
assert d.messwerte[i].get("pruefstatus") == "nicht messbar" and d.fehler_gruppen[datei].childCount() == 1
# neue Profil-ID eintippen: Maße aus dem Namen
z = d.von_hand(i, "Rechteckrohr", "RE 50x30x2")
assert (float(d.messwerte[i]["abm_a"]), float(d.messwerte[i]["abm_b"]), float(d.messwerte[i]["wandstaerke"])) == (50, 30, 2)
d.werte_schreiben()
erg = step.uebernehmen(d.messwerte, [], d.k, db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True)
p = next(x for x in erg["positionen"] if x["artikel"] == d.messwerte[i]["artikel"])
assert p["profil_id"] == "RE 50x30x2" and p["laenge"] == round(huelle[-1], 1) and p["a_gerade"] == "ja", p
assert any(x["profil_id"] == "RE 50x30x2" for x in erg["profile"])          # neues Profil aus dem Namen
# andere Profilform bei einem erkannten Rohr: Profil-ID-Liste der Form, Hinweis
z0 = d.zeilen[0]
cb = d.baum.itemWidget(z0.it, d.SP_ART)
gemessen = d.messwerte[z0.liste[0]]["profilform"]
assert cb.findData("form:Rechteckrohr") > 0
cb.setCurrentIndex(cb.findData("form:Rechteckrohr"))
z0 = next(x for x in d.zeilen if x.liste[0] == z0.liste[0])
assert d.messwerte[z0.liste[0]]["profilform"] == "Rechteckrohr" and f"gemessen {gemessen}" in z0.it.text(d.SP_HINWEIS)
print("OK     von Hand nachtragen (Profilform, Profil-ID, Länge aus Hüllmaß), zurücknehmen, Art bei jeder Zeile wählbar")

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
