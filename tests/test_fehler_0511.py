"""Fehler-Durchgang 05.11.2026 (Prüffenster STEP-Import):
- Regel des Kunden mit anderer Profilform im Prüffenster zurückgestellt (gemessenes Profil gewählt): die gemessene
  Form gilt wieder, die Position wird genau wie ohne Regel übernommen (vorher blieb die Form der Regel stehen, das
  Profil galt als „fehlt in Stammdaten“ und die Enden wurden neu gerechnet, Schneidweg kürzer als im STEP),
- Haken „Nur zu prüfende“: ist nichts mehr zu prüfen, geht der Filter aus (vorher blieb er unsichtbar an und die
  Liste war leer).
Aufruf: python tests/test_fehler_0511.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import step_messen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import step, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

stil.anwenden(app, "hell")
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
roh = [dict(zip(step_messen.SPALTEN, z)) for z in step_messen.zeilen(HIER / "step_anbau" / "A01_RE60x40x3_ohne_Anbau.step",
                                                                      Path(tempfile.mkdtemp(dir=tmp)))]
gemessen = step.profil_vorschlag(roh[0], k.profile)
assert gemessen == "RE 60x40x3", gemessen
quadrat = next(p for p, z in k.profile.items() if z.get("form") == "Quadratrohr")
anders = next(p for p, z in k.profile.items() if z.get("form") == "Rechteckrohr" and p != gemessen)
regeln = {gemessen: quadrat}


def ok(text):
    print("OK    ", text)


def position(mw):
    erg = step.uebernehmen([dict(m) for m in mw], [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
    p = erg["positionen"][0]
    return {f: p.get(f) for f in ("profil_id", "konturen", "schneidweg", "hinweise")}, erg["bericht"]


ohne = [dict(m, _uebernehmen=True) for m in roh]
soll, soll_bericht = position(ohne)

# --- Regel mit anderer Form, im Prüffenster zurückgestellt
mw = [dict(m) for m in roh]
assert step.profile_gelernt_anwenden(mw, regeln, k.profile) == 1 and mw[0]["profilform"] == "Quadratrohr"
d = StepPruefDialog(None, mw, k, "S235-10219", 1)
z = d.zeilen[0]
assert z.pr.currentText() == quadrat and z.ampel == "gelb"
z.pr.setCurrentText(gemessen)
d.werte_schreiben()
m = mw[0]
assert m["profilform"] == "Rechteckrohr" and "_form_gemessen" not in m and "_profil_regel" not in m, m
assert step.ampel(m)[0] == "gruen", step.ampel(m)
assert step.profile_gelernt_merken(regeln, mw, k.profile) == {}
ist, bericht = position(mw)
assert ist == soll and bericht == soll_bericht, (ist, soll, bericht)
d.close()
ok("Regel mit anderer Form zurückgestellt: gemessene Form, Position wie ohne Regel (Enden wie im STEP)")

# --- Regel beibehalten: Form der Regel bleibt
mw = [dict(m) for m in roh]
step.profile_gelernt_anwenden(mw, regeln, k.profile)
d = StepPruefDialog(None, mw, k, "S235-10219", 1)
d.werte_schreiben()
assert mw[0]["profilform"] == "Quadratrohr" and mw[0]["_profil"] == quadrat and mw[0]["_profil_regel"] == gemessen
assert step.profile_gelernt_merken(regeln, mw, k.profile) == regeln
d.close()
# anderes Profil der gemessenen Form gewählt: Regel verlassen, gemessene Form, neue Regel gemessen → gewählt
mw = [dict(m) for m in roh]
step.profile_gelernt_anwenden(mw, regeln, k.profile)
d = StepPruefDialog(None, mw, k, "S235-10219", 1)
d.zeilen[0].pr.setCurrentText(anders)
d.werte_schreiben()
assert mw[0]["profilform"] == "Rechteckrohr" and mw[0]["_profil"] == anders and "_profil_regel" not in mw[0]
assert step.profile_gelernt_merken(regeln, mw, k.profile) == {gemessen: anders}
d.close()
# Rücknahme bei Kundenwechsel nach Zurückstellen: nichts mehr zurückzunehmen
step.profile_gelernt_zuruecknehmen(mw)
assert mw[0]["_profil"] == anders and mw[0]["profilform"] == "Rechteckrohr"
ok("Regel beibehalten: Form der Regel bleibt; anderes Profil gewählt: Regel verlassen, gemessene Form")

# --- Filter „Nur zu prüfende“ geht aus, wenn nichts mehr zu prüfen ist
mw = [dict(m) for m in roh]
step.profile_gelernt_anwenden(mw, regeln, k.profile)
d = StepPruefDialog(None, mw, k, "S235-10219", 1)
d.show()
app.processEvents()
assert d.zeilen[0].ampel == "gelb" and d.nur_pruefen.isVisible()
d.nur_pruefen.setChecked(True)
assert not d.zeilen[0].it.isHidden()
d.form_setzen(d.zeilen[0].liste[0], "Rechteckrohr")
app.processEvents()
z = d.zeilen[0]
assert z.ampel == "gruen", z.ampel
assert not d.nur_pruefen.isVisible() and not d.nur_pruefen.isChecked() and not z.it.isHidden()
d.close()
ok("„Nur zu prüfende“: nichts mehr gelb/rot → Filter aus, alle Teile sichtbar")
print("Alle Prüfungen Fehler-Durchgang 05.11. bestanden.")
