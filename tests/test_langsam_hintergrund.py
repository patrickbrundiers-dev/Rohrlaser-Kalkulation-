"""Langsame Teile im Hintergrund (Vorschlag N4, Patrick 07.11.2026): messen nur noch Körper, die schon länger als
--zwischenstand Sekunden laufen, schreibt die Messung einen Zwischenstand ohne sie (Platzhalter „Messung läuft noch“)
und misst weiter. Der Prüfdialog öffnet mit dem Zwischenstand, die langsamen Teile rücken nach; OK wartet auf sie.
Langsam macht einen Körper die Testhilfe STEP_MESSEN_TEST_LANGSAM="Datei:Körper:Sekunden".

Aufruf: python tests/test_langsam_hintergrund.py
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"
GESTELL = HIER / "step_struktur" / "S01_Gestell_verschachtelt.step"
RAHMEN = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
TMP = Path(tempfile.mkdtemp())
LANGSAM = 12

from rohrlaser import step  # noqa: E402


def ok(text):
    print("OK    ", text)


def befehl(name, datei, prozesse):
    return [sys.executable, str(MESSEN), "--ausgabe", str(TMP / f"{name}.txt"), "--json", str(TMP / f"{name}.json"),
            "--netze", str(TMP / f"{name}_n"), "--prozesse", str(prozesse), "--zeitlimit", "120",
            "--zwischenstand", "2", str(datei)]


def umgebung(datei, k, teilen_ab):
    return dict(os.environ, STEP_MESSEN_TEILEN_AB=str(teilen_ab), STEP_MESSEN_TEST_LANGSAM=f"{datei.name}:{k}:{LANGSAM}")


for name, datei, k, prozesse, teilen_ab, kopien in (("verteilt", GESTELL, 1, 3, 2, (1, 4)),
                                                     ("eins", RAHMEN, 3, 1, 99, (3, 4))):
    start = time.monotonic()
    p = subprocess.Popen(befehl(name, datei, prozesse), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         env=umgebung(datei, k, teilen_ab))
    zeit_zwischen = None
    for z in p.stdout:
        if z.strip() == "ZWISCHENSTAND":
            zeit_zwischen = time.monotonic() - start
    p.wait(600)
    gesamt = time.monotonic() - start
    assert zeit_zwischen is not None and gesamt - zeit_zwischen > LANGSAM / 2, (zeit_zwischen, gesamt)
    zw = step.lies_messwerte(TMP / f"{name}.txt.zwischen")
    end = step.lies_messwerte(TMP / f"{name}.txt")
    assert len(zw) == len(end)
    platz = [int(m["koerper"]) for m in zw if step.noch_in_messung(m)]
    assert tuple(platz) == kopien, platz
    assert not any(step.noch_in_messung(m) for m in end)
    for a, b in zip(zw, end):
        if int(a["koerper"]) not in kopien:
            assert (a["profilform"], a["laenge"]) == (b["profilform"], b["laenge"]), (a["koerper"], a, b)
    assert (TMP / f"{name}.json.zwischen").exists()
    ok(f"{datei.stem} ({'verteilt auf 3 Prozesse' if prozesse > 1 else 'ein Prozess'}): Zwischenstand nach "
       f"{zeit_zwischen:.0f} s ohne Körper {', '.join(map(str, kopien))} (Messung läuft noch), endgültig nach "
       f"{gesamt:.0f} s, die übrigen Teile gleich")

# ------------------------------------------------------------------ Prüfdialog mit Nachmessung
from PySide6.QtCore import QProcess  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import nachmessung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
proz = QProcess()
env = proz.processEnvironment()
for k_, v in umgebung(RAHMEN, 3, 99).items():
    env.insert(k_, v)
proz.setProcessEnvironment(env)
b = befehl("dialog", RAHMEN, 1)
proz.start(b[0], b[1:])
zwischen = TMP / "dialog.txt.zwischen"
while not zwischen.exists() and proz.state() != QProcess.NotRunning:
    app.processEvents()
    time.sleep(0.1)
time.sleep(0.3)
assert proz.state() != QProcess.NotRunning, "Messung schon fertig"
nach = nachmessung.Nachmessung(proz, TMP / "nach_ordner", TMP / "dialog.txt", TMP / "dialog_n", TMP / "dialog.json")
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(zwischen), TMP / "dialog_n"),
                             Path(str(TMP / "dialog.json") + ".zwischen"))
for m in mw:
    m["_stueck"] = 7
db = Datenbank(TMP / "a.db")
k = db.kontext()
d = StepPruefDialog(None, mw, k, "S235-10219", 1, nachmessung=nach)
d.show()
app.processEvents()
assert not d.nachmess_info.isHidden() and "2 langsame(s) Teil(e) werden noch gemessen" in d.nachmess_info.text(), \
    d.nachmess_info.text()
ok("Prüfdialog offen, während das langsame Teil noch gemessen wird (Hinweis über der Liste)")
d.accept()          # wartet auf das Ende der Messung und setzt das Teil ein
assert not nach.laeuft() and not any(step.noch_in_messung(m) for m in mw), [m.get("hinweise") for m in mw]
k3 = next(m for m in mw if str(m["koerper"]) == "3")
assert k3["profilform"] == "Quadratrohr" and k3["_stueck"] == 7 and k3.get("_netz"), k3
assert "2 langsame(s) Teil(e) nachgemessen" in d.nachmess_info.text(), d.nachmess_info.text()
ok("OK wartet auf das langsame Teil, es rückt nach (Messwerte, 3D, Stückzahl aus dem Dialog bleibt)")
nach.beenden()
db.con.close()
print("Langsame Teile im Hintergrund: alle Tests bestanden.")
