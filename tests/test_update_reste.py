"""Update-Fehler „_internal/base_library.zip: geöffnet in Rohrlaser Angebotskalkulation“ (Update 0.9.439, Patrick
21.11.2026). Zwei Ursachen, beide abgesichert:

1) Dieser Prozess selbst hält die Datei noch (ZIP-Datei oder offene Datei, egal wer darauf zeigt):
   update.eigene_griffe_freigeben(ordner, dateien) schließt genau diese Dateien.
2) Weitere Prozesse dieses Programms (Hilfsprozesse für Schnittpläne/STEP-Gegenprobe, hängendes zweites Fenster):
   nach_beenden beendet die Hilfsprozesse vorab; hält dann noch ein Prozess dieses Programms eine Datei, fragt es
   „Ja = beenden und weiter“ und beendet nur Prozesse, deren .exe im Programmordner liegt.

Unter Linux gibt es keinen Windows-Neustart-Manager: update.sperrer/prozess_pfad werden ersetzt.
Aufruf: python tests/test_update_reste.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from rohrlaser import update, update_fenster  # noqa: E402

update.update_schluessel = lambda: {}


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp(prefix="update_reste_"))

# 1) eigene Griffe: ZIP-Datei und offene Datei auf Programmdateien werden geschlossen, andere bleiben offen
ordner = tmp / "prog"
(ordner / "_internal").mkdir(parents=True)
with zipfile.ZipFile(ordner / "_internal" / "base_library.zip", "w") as z:
    z.writestr("a.py", "x = 1\n")
(ordner / "_internal" / "a.dll").write_bytes(b"dll")
(tmp / "fremd.txt").write_bytes(b"x")
gehalten = {"zip": zipfile.ZipFile(ordner / "_internal" / "base_library.zip"),     # wie ein Cache, der sie hält
            "datei": open(ordner / "_internal" / "a.dll", "rb"),
            "fremd": open(tmp / "fremd.txt", "rb")}
zu = update.eigene_griffe_freigeben(ordner, ["_internal/base_library.zip", "_internal/a.dll"])
assert zu == 2, zu
assert gehalten["zip"].fp is None and gehalten["datei"].closed and not gehalten["fremd"].closed
gehalten["fremd"].close()
assert update.eigene_griffe_freigeben() == 0 and update.eigene_griffe_freigeben(ordner, []) == 0
ok("Eigene offene ZIP-Datei und Programmdatei geschlossen, fremde Dateien bleiben offen")

# 2) programm_reste: nur andere Prozesse, deren .exe im Programmordner liegt
exe_im_ordner = ordner / "Rohrlaser-Angebotskalkulation.exe"
pfade = {111: exe_im_ordner, 222: Path("C:/Programme/PDF/pdf.exe"), os.getpid(): exe_im_ordner}
finden = {str(ordner / "_internal/base_library.zip"): [(111, "Rohrlaser Angebotskalkulation"),
                                                       (222, "PDF"), (os.getpid(), "Rohrlaser Angebotskalkulation")]}
reste = update.programm_reste(ordner, ["_internal/base_library.zip", "_internal/a.dll"],
                              finden=lambda p: finden.get(str(p), []), pfad=pfade.get)
assert reste == {111: "Rohrlaser Angebotskalkulation"}, reste
assert update._im_ordner(ordner / "_internal" / "x", ordner) and not update._im_ordner(tmp / "fremd.txt", ordner)
assert not update._im_ordner(None, ordner)
ok("Reste: nur andere Prozesse dieses Programms, nie dieser und nie fremde Programme")

# 3) prozesse_beenden: echter Prozess wird beendet, aber nur wenn seine .exe im Programmordner liegt
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
try:
    assert update.prozesse_beenden([p.pid], ordner, pfad=lambda pid: tmp / "anderswo.exe", warten_s=0.5) == []
    assert p.poll() is None, "fremdes Programm darf nicht beendet werden"
    assert update.prozesse_beenden([os.getpid()], ordner, pfad=lambda pid: exe_im_ordner) == []
    assert update.prozesse_beenden([p.pid], ordner, pfad=lambda pid: exe_im_ordner, warten_s=5) == [p.pid]
    p.wait(5)
finally:
    if p.poll() is None:
        p.kill()
ok("Beenden: Prozess dieses Programms beendet, fremde und der eigene Prozess nie")

# 4) Meldung: Hintergrundprozess mit Nummer, eigener Prozess als dieses Update-Fenster
echt_sperrer, echt_pfad = update.sperrer, update.prozess_pfad
update.sperrer = lambda pfad: [(111, "Rohrlaser Angebotskalkulation"), (os.getpid(), "Rohrlaser Angebotskalkulation")]
update.prozess_pfad = lambda pid: exe_im_ordner
grund = update.sperr_grund("_internal/base_library.zip", ordner)
assert "im Hintergrund (Prozess 111)" in grund and "Update-Fenster selbst" in grund and "bitte dort" not in grund, grund
update.sperrer = lambda pfad: [(333, "Acrobat")]
update.prozess_pfad = lambda pid: Path("C:/Acrobat/acrobat.exe")
assert update.sperr_grund("Bedienungsanleitung.pdf", ordner) == "geöffnet in Acrobat – bitte dort schließen"
text = update_fenster.reste_text(["_internal/base_library.zip"], {111: "x", 112: "x"})
assert "2 Prozesse: Nr. 111, Nr. 112" in text and "„Ja“ beendet" in text, text
ok("Meldung nennt Hintergrundprozesse mit Nummer")

# 5) nach_beenden: Hilfsprozess hält base_library.zip -> Rückfrage, „Ja“ beendet ihn, Update läuft durch
app = QApplication.instance() or QApplication([])
update.SPERR_WARTEN_S = 0
update.KURZ_WARTEN_S = 0.1


def programm(o, inhalt):
    for rel in ("Rohrlaser-Angebotskalkulation.exe", "_internal/base_library.zip"):
        (o / rel).parent.mkdir(parents=True, exist_ok=True)
        (o / rel).write_bytes(inhalt + rel.encode())
    return o


neu = programm(tmp / "neu", b"v2:")
update.erstellen(neu, tmp / "pakete", 2)
alt = programm(tmp / "alt", b"v1:")
update.erstellen(alt, tmp / "pakete_alt", 1)
shutil.copyfile(tmp / "pakete_alt" / update.DATEILISTE, alt / update.DATEILISTE)
online = update.online_liste(str(tmp / "pakete" / update.DATEILISTE))
plan = update.planen(alt, online, update.lokale_liste(alt))
neu_ordner = update.laden(alt, str(tmp / "pakete" / update.DATEILISTE), online, plan)

halter = {"laeuft": True}
echt_ersetzen = update._ersetzen


def ersetzen(von, nach):
    if halter["laeuft"] and Path(von).name == "base_library.zip":
        e = PermissionError(13, "benutzt", str(von))
        e.winerror = 32
        raise e
    return echt_ersetzen(von, nach)


update._ersetzen = ersetzen
update.sperrer = lambda pfad: [(4711, "Rohrlaser Angebotskalkulation")] if halter["laeuft"] else []
update.prozess_pfad = lambda pid: alt / "Rohrlaser-Angebotskalkulation.exe"
beendet = []
echt_beenden = update.prozesse_beenden


def beenden(pids, o, **k):
    beendet.extend(pids)
    halter["laeuft"] = False
    return list(pids)


update.prozesse_beenden = beenden
fragen = []


def frage(*a, **k):
    fragen.append(a[2])
    return QMessageBox.Yes


QMessageBox.question = staticmethod(frage)
QMessageBox.warning = staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("keine Warnung erwartet")))
neustart = []
erg = update_fenster.nach_beenden(alt, dict(online=online, plan=plan, neu_ordner=neu_ordner),
                                  starten=lambda exe, arg: neustart.append(arg))
assert erg == "ok", erg
assert len(fragen) == 1 and "Nr. 4711" in fragen[0] and beendet == [4711], (fragen, beendet)
assert (alt / "_internal/base_library.zip").read_bytes() == b"v2:_internal/base_library.zip"
assert neustart == [["--nach-update", "ok"]]
ok("Nach dem Beenden: Rückfrage, Hintergrundprozess beendet, Update eingespielt")

# 6) Abbrechen in der Rückfrage: nichts geändert, alte Version startet
alt2 = programm(tmp / "alt2", b"v1:")
shutil.copyfile(tmp / "pakete_alt" / update.DATEILISTE, alt2 / update.DATEILISTE)
plan2 = update.planen(alt2, online, update.lokale_liste(alt2))
neu2 = update.laden(alt2, str(tmp / "pakete" / update.DATEILISTE), online, plan2)
halter["laeuft"] = True
update.prozess_pfad = lambda pid: alt2 / "Rohrlaser-Angebotskalkulation.exe"
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Cancel)
beendet.clear()
neustart.clear()
assert update_fenster.nach_beenden(alt2, dict(online=online, plan=plan2, neu_ordner=neu2),
                                   starten=lambda exe, arg: neustart.append(arg)) == "abgebrochen"
assert not beendet and neustart == [["--nach-update", "abgebrochen"]]
assert (alt2 / "_internal/base_library.zip").read_bytes() == b"v1:_internal/base_library.zip"
ok("Abbrechen: nichts beendet, nichts geändert")

# 7) Hilfsprozesse (parallel.py) werden vor dem Austausch beendet
import types  # noqa: E402

aufgerufen = []
sys.modules["rohrlaser.parallel"] = types.SimpleNamespace(beenden=lambda: aufgerufen.append(1))
update_fenster.hilfsprozesse_beenden()
assert aufgerufen == [1]
ok("Hilfsprozesse für Schnittpläne/Gegenprobe werden vor dem Austausch beendet")

update.sperrer, update.prozess_pfad, update.prozesse_beenden, update._ersetzen = (echt_sperrer, echt_pfad,
                                                                                  echt_beenden, echt_ersetzen)
shutil.rmtree(tmp, ignore_errors=True)
print("OK: Update beendet Programm-Reste und gibt eigene Dateien frei")
