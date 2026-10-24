"""Online-Update zuverlässig (Patrick 24.10.2026, F1a F2a): gesperrte Dateien erkennen, abwarten, Wiederholen/
Abbrechen, zurückstellen; erst nach dem Beenden austauschen; Neustart wartet auf die Datensperre; Anleitung wird
aus einer Kopie im Datenordner geöffnet (der PDF-Betrachter sperrt sonst die Datei im Programmordner, WinError 32).

Unter Linux lässt sich eine Windows-Sperre nicht erzeugen: update._ersetzen wird dafür ersetzt.
Aufruf: python tests/test_update_sperre.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from rohrlaser import __main__ as start, orte, update, update_fenster  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster, anleitung_kopie  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp(prefix="update_sperre_"))
echt_ersetzen = os.replace
gesperrt = set()        # Dateinamen, die "ein anderes Programm" gerade festhält


def ersetzen(von, nach):
    if Path(von).name in gesperrt:
        e = PermissionError(13, "Der Prozess kann nicht auf die Datei zugreifen", str(von))
        e.winerror = 32
        raise e
    return echt_ersetzen(von, nach)


update._ersetzen = ersetzen


def programm(ordner, inhalt):
    ordner = Path(ordner)
    for rel in ("Rohrlaser-Angebotskalkulation.exe", "_internal/a.dll", "Bedienungsanleitung.pdf",
                "STEP-Import/STEP-Import.exe"):
        (ordner / rel).parent.mkdir(parents=True, exist_ok=True)
        (ordner / rel).write_bytes(inhalt + rel.encode())
    return ordner


def inhalt(ordner):
    return {p.relative_to(ordner).as_posix(): p.read_bytes() for p in Path(ordner).rglob("*")
            if p.is_file() and not p.relative_to(ordner).as_posix().startswith(update.ARBEITSORDNER + "/")}


neu = programm(tmp / "neu", b"v2:")
liste = update.erstellen(neu, tmp / "pakete", 2)
quelle = str(tmp / "pakete" / update.DATEILISTE)
alt = programm(tmp / "alt", b"v1:")
update.erstellen(alt, tmp / "pakete_alt", 1)
shutil.copyfile(tmp / "pakete_alt" / update.DATEILISTE, alt / update.DATEILISTE)
online = update.online_liste(quelle)
plan = update.planen(alt, online, update.lokale_liste(alt))
assert len(plan["neu"]) == 4, plan
vorher = inhalt(alt)

# 1) Vorabprüfung: nur die gesperrte Datei, nichts verändert, keine .probe-Reste
gesperrt.add("Bedienungsanleitung.pdf")
assert update.gesperrte_dateien(alt, plan) == ["Bedienungsanleitung.pdf"]
assert inhalt(alt) == vorher and not list(alt.rglob("*.probe"))
ok("Vorabprüfung findet die gesperrte Anleitung, ändert nichts")

# 2) Warten: Sperre geht nach 3 s weg -> frei; bleibt sie, nach der Frist die gesperrten Dateien
uhr = [0.0]
meldungen = []


def schlafen(s):
    uhr[0] += s
    if uhr[0] >= 3:
        gesperrt.discard("Bedienungsanleitung.pdf")


assert update.warten_bis_frei(alt, plan, melden=lambda g, r: meldungen.append((g, r)), schlafen=schlafen,
                              uhr=lambda: uhr[0]) == []
assert meldungen and meldungen[0][0] == ["Bedienungsanleitung.pdf"], meldungen
gesperrt.add("Bedienungsanleitung.pdf")
uhr[0] = 0.0
assert update.warten_bis_frei(alt, plan, sekunden=5, schlafen=lambda s: uhr.__setitem__(0, uhr[0] + s),
                              uhr=lambda: uhr[0]) == ["Bedienungsanleitung.pdf"]
ok("Warten bis frei: Sperre weg -> weiter, Sperre bleibt -> Liste nach der Frist")

# 3) Gründe verständlich
assert "PDF-Programm" in update.sperr_grund("Bedienungsanleitung.pdf")
assert update.nur_anleitungen(["Bedienungsanleitung.pdf", "Kurzanleitung.pdf"])
assert not update.nur_anleitungen(["Bedienungsanleitung.pdf", "_internal/a.dll"]) and not update.nur_anleitungen([])
assert "STEP-Import" in update.sperr_grund("STEP-Import/STEP-Import.exe")
assert "Virenscanner" in update.sperr_grund("_internal/a.dll")
assert "Bedienungsanleitung.pdf" in update.sperr_text(["Bedienungsanleitung.pdf"])
ok("Meldung nennt Datei und wahrscheinlichen Grund")

# 4) Sperre erst beim Austausch (nach der Prüfung): DateiGesperrt, alles zurückgestellt, Download bleibt
neu_ordner = update.laden(alt, quelle, online, plan)
update.KURZ_WARTEN_S = 0.3
try:
    update.einspielen(alt, online, plan, neu_ordner)
    raise AssertionError("Fehler erwartet")
except update.DateiGesperrt as e:
    assert e.dateien == ["Bedienungsanleitung.pdf"], e.dateien
assert inhalt(alt) == vorher and neu_ordner.exists()
ok("Sperre beim Austausch: zurückgestellt, Download bleibt für einen neuen Versuch")

# 5) nach_beenden: erst Wiederholen (Programmdatei noch gesperrt), dann ist sie weg -> ok, Neustart mit
#    --nach-update ok
app = QApplication.instance() or QApplication([])
update.SPERR_WARTEN_S = 0
fragen = []


def warnung(*a, **k):
    fragen.append(a[2])
    if len(fragen) == 1:
        gesperrt.clear()            # Benutzer schließt das andere Programm und klickt Wiederholen
        return QMessageBox.Retry
    return QMessageBox.Cancel


QMessageBox.warning = staticmethod(warnung)
gesperrt.add("a.dll")
neustart = []
ausstehend = dict(online=online, plan=plan, neu_ordner=neu_ordner)
assert update_fenster.nach_beenden(alt, ausstehend, starten=lambda exe, arg: neustart.append(arg)) == "ok"
assert len(fragen) == 1 and "_internal/a.dll" in fragen[0] and "Virenscanner" in fragen[0], fragen
assert neustart == [["--nach-update", "ok"]]
assert inhalt(alt) == inhalt(neu) | {update.DATEILISTE: inhalt(alt)[update.DATEILISTE]}
assert update.lokale_liste(alt)["stand"] == 2
ok("Nach dem Beenden: Wiederholen nach dem Schließen, dann ausgetauscht und neu gestartet")

# 5b) Nur die Anleitung bleibt gesperrt (Patrick 24.10.: Anleitung war gar nicht offen): ohne Rückfrage
#     aktualisieren, die Anleitung tauscht der nächste Start
alt3 = programm(tmp / "alt3", b"v1:")
shutil.copyfile(tmp / "pakete_alt" / update.DATEILISTE, alt3 / update.DATEILISTE)
plan3 = update.planen(alt3, online, update.lokale_liste(alt3))
aus3 = dict(online=online, plan=plan3, neu_ordner=update.laden(alt3, quelle, online, plan3))
fragen.clear()
neustart.clear()
gesperrt.add("Bedienungsanleitung.pdf")
assert update_fenster.nach_beenden(alt3, aus3, starten=lambda exe, arg: neustart.append(arg)) == "ok"
assert not fragen and neustart == [["--nach-update", "ok"]], fragen
assert (alt3 / "Bedienungsanleitung.pdf").read_bytes() == b"v1:Bedienungsanleitung.pdf"
assert (alt3 / "Rohrlaser-Angebotskalkulation.exe").read_bytes() == b"v2:Rohrlaser-Angebotskalkulation.exe"
assert update.lokale_liste(alt3)["stand"] == 2
update.aufraeumen(alt3)                                       # Start, Anleitung noch gesperrt: bleibt liegen
assert update.nachholen(alt3) == ["Bedienungsanleitung.pdf"]
update.aufraeumen(alt3)
gesperrt.clear()
assert update.nachholen(alt3) == []                           # nächster Start: jetzt getauscht
assert (alt3 / "Bedienungsanleitung.pdf").read_bytes() == b"v2:Bedienungsanleitung.pdf"
update.aufraeumen(alt3)
assert not (alt3 / update.ARBEITSORDNER).exists()
assert update.wer_sperrt(alt3 / "Bedienungsanleitung.pdf") == []          # außerhalb von Windows: keine Angabe
ok("Nur die Anleitung gesperrt: Programm trotzdem aktualisiert, Anleitung beim nächsten Start nachgeholt")

# 6) Abbrechen: alte Version bleibt, Download verworfen, Neustart mit --nach-update abgebrochen
alt2 = programm(tmp / "alt2", b"v1:")
shutil.copyfile(tmp / "pakete_alt" / update.DATEILISTE, alt2 / update.DATEILISTE)
vorher2 = inhalt(alt2)
plan2 = update.planen(alt2, online, update.lokale_liste(alt2))
fragen.clear()
fragen.append("schon gefragt")      # warnung antwortet ab jetzt Abbrechen
gesperrt.add("a.dll")
neustart.clear()
aus2 = dict(online=online, plan=plan2, neu_ordner=update.laden(alt2, quelle, online, plan2))
assert update_fenster.nach_beenden(alt2, aus2, starten=lambda exe, arg: neustart.append(arg)) == "abgebrochen"
assert neustart == [["--nach-update", "abgebrochen"]] and inhalt(alt2) == vorher2
assert not (alt2 / update.ARBEITSORDNER / "neu").exists()
gesperrt.clear()
ok("Abbrechen: nichts geändert, Download verworfen, alte Version startet wieder")

# 7) Programm beenden vor dem Austausch: Beenden abgelehnt -> kein Update, nichts geändert
db = Datenbank(tmp / "Daten" / "rohrlaser.db")
f = Hauptfenster(db, alt2, stumm=True)
f.show()
f.close = lambda: False
assert f.updater.beenden() is False
del f.close
f.show()
assert f.updater.beenden() is True and not f.isVisible()
ok("Beenden für das Update: abgelehnt -> nichts, sonst Fenster zu")

# 8) Anleitung aus einer Kopie im Datenordner; geöffnete (gesperrte) Kopie bleibt, Original nie geöffnet
pdf = alt2 / "Bedienungsanleitung.pdf"
kopie = anleitung_kopie(pdf, tmp / "Daten" / "Anleitung")
assert kopie == tmp / "Daten" / "Anleitung" / pdf.name and kopie.read_bytes() == pdf.read_bytes()
assert anleitung_kopie(pdf, tmp / "Daten" / "Anleitung") == kopie            # unverändert: keine neue Kopie
pdf.write_bytes(b"neuer Stand der Anleitung")
os.chmod(kopie.parent, 0o500)                                                  # Kopie lässt sich nicht erneuern
try:
    assert anleitung_kopie(pdf, tmp / "Daten" / "Anleitung") == kopie
finally:
    os.chmod(kopie.parent, 0o700)
assert anleitung_kopie(pdf, tmp / "Daten" / "Anleitung").read_bytes() == b"neuer Stand der Anleitung"
geoeffnet = []
f.datei_oeffnen = geoeffnet.append
f.programmordner = alt2
assert f.anleitung_oeffnen() == db.pfad.parent / "Anleitung" / "Bedienungsanleitung.pdf"
assert geoeffnet and geoeffnet[0].parent != alt2
ok("Anleitung öffnet eine Kopie im Datenordner, nie die Datei im Programmordner")
db.schliessen()

# 9) Neustart nach dem Update wartet auf die Datensperre der alten Version
s1 = orte.Sperre(tmp / "Daten")
try:
    start.sperre_holen(orte, tmp / "Daten", warten_s=0)
    raise AssertionError("Gesperrt erwartet")
except orte.Gesperrt:
    pass
runden = []


def frei_nach_2(s):
    runden.append(s)
    if len(runden) == 2:
        s1.freigeben()


s2 = start.sperre_holen(orte, tmp / "Daten", warten_s=30, schlafen=frei_nach_2)
assert len(runden) == 2
s2.freigeben()
assert set(start.NACH_UPDATE_TEXT) == {"ok", "abgebrochen", "fehler"}
ok("Neustart wartet, bis die alte Version die Datensperre freigibt")

update._ersetzen = echt_ersetzen
shutil.rmtree(tmp, ignore_errors=True)
print("OK: Online-Update zuverlässig (Sperren, Warten, Wiederholen, Zurückstellen, Neustart)")
