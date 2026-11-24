"""Fehlalarm der Virenprüfung (Patrick 16.11.2026: „beim msg auslesen … alles wird als Virus erkannt“).

Bis 0.9.348 galt jeder Rückgabewert 2 von MpCmdRun.exe als Fund; der Defender gibt 2 aber auch zurück, wenn die
Prüfung scheitert (Netzlaufwerk, OneDrive, Rechte). Seitdem: eigene Prüfung nur auf Wunsch (Vorgabe aus), Fund nur
mit genannter Bedrohung, alte Sperren werden einmal aufgehoben, eine Sperre lässt sich von Hand aufheben.
Nur erfundene Testmails, der Defender ist nachgebaut.

Aufruf: python tests/test_virus_fehlalarm.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import virenpruefung as vp  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


EXE = Path("C:/Programme/Windows Defender/MpCmdRun.exe")
aufrufe = []


def gescheitert(befehl):
    """Defender, dessen Prüfung scheitert: Rückgabewert 2, aber keine Bedrohung (so meldete 0.9.348 alles als Virus)."""
    aufrufe.append(befehl)
    return SimpleNamespace(returncode=2, stdout="CmdTool: Failed with hr = 0x80508023. Check MpCmdRun.log", stderr="")


tmp = Path(tempfile.mkdtemp())
JETZT = datetime.datetime.now().replace(microsecond=0)
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")


def mail(name, betreff):
    m = tmp / f"{name}.eml"
    m.write_bytes(mail_testdateien.eml(betreff, "Bitte anbieten.", "Max Muster", "max@muster-metall.example",
                                       JETZT - datetime.timedelta(hours=2),
                                       [("teil.step", b"ISO-10303-21; Teil"), ("zeichnung.pdf", b"%PDF sauber")]))
    return m


# ------------------------------------------------------------------ V1 gescheiterte Prüfung ist kein Fund
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")
a, _ = abl.anlegen(dict(quelle="ordner", betreff="Anfrage Konsole", absender="max@muster-metall.example"),
                   [mail("konsole", "Anfrage Konsole")], "k1")
assert not abl.viren_pruefen(a, exe=EXE, ausfuehren=gescheitert) and aufrufe
a = abl.neu_lesen(a)
assert not a.virus() and len(a.ungeprueft()) == 3
ok("V1 Rückgabewert 2 ohne genannte Bedrohung: nichts gesperrt, Dateien bleiben „nicht geprüft“")

# ------------------------------------------------------------------ V2 alte Sperren (Fehlalarm) werden aufgehoben
alt, _ = abl.anlegen(dict(quelle="ordner", betreff="Anfrage Halter", absender="max@muster-metall.example"),
                     [mail("halter", "Anfrage Halter")], "h1")
alt = abl.neu_lesen(alt)
namen = [d.get("datei", d["name"]) for d in alt.dateien()]
for d in alt.dateien():                 # so hinterließ 0.9.348 die Akte: alles umbenannt, Ereignis ohne „sicher“
    d["pfad"].replace(d["pfad"].with_name(d["pfad"].name + ".gesperrt"))
abl.ereignis(alt, ak.VIREN, dateien={n: vp.FUND for n in namen})
alt = abl.neu_lesen(alt)
assert alt.virus() and sorted(alt.fehlalarme()) == sorted(namen)
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
seite.viren_exe, seite.viren_ausfuehren = EXE, gescheitert
seite._ablage = None
seite.ablage = lambda: abl
aufrufe.clear()
seite.neu_laden()
alt = abl.neu_lesen(alt)
assert not alt.virus() and not alt.fehlalarme() and all(d["pfad"].is_file() for d in alt.dateien())
assert all(d["viren"] == vp.FREIGEGEBEN and not d.get("gesperrt") for d in alt.dateien())
assert any("Sperre aufgehoben" in ak.verlauf_text(e) and "Fehlalarm" in ak.verlauf_text(e) for e in alt.verlauf)
assert not aufrufe, "eigene Prüfung ist aus (Vorgabe): kein Aufruf von MpCmdRun"
seite.waehlen(alt.nr)
text = seite.inhalt.toPlainText()
assert "Virus gefunden" not in text and "Sperre aufgehoben" in text and "wird auf Viren geprüft" not in text, text
assert ak.arbeitskopie(alt) is not None                # Kalkulieren wieder möglich
ok("V2 Sperren der alten Prüfung beim Öffnen der Seite aufgehoben (Datei zurück, Verlauf), Kalkulieren wieder frei")

# ------------------------------------------------------------------ V3 echter Fund bleibt, Sperre von Hand aufheben
db.einstellung_setzen(vp.EIN, "ja")
fund = SimpleNamespace(returncode=2, stderr="", stdout="Scanning x found 1 threats.\n<====LIST OF DETECTED THREATS====>"
                       "\nThreat                  : Virus:DOS/Test_Kennung\n")
b, _ = abl.anlegen(dict(quelle="ordner", betreff="Anfrage Winkel", absender="max@muster-metall.example"),
                   [mail("winkel", "Anfrage Winkel")], "w1")
abl.viren_pruefen(b, exe=EXE, ausfuehren=lambda befehl: fund)
seite.neu_laden()
b = abl.neu_lesen(b)
assert b.virus() and not b.fehlalarme()                # sicherer Fund: wird nicht von selbst aufgehoben
seite.waehlen(b.nr)
assert "Sperre aufheben" in seite.inhalt.toPlainText()
ziel = next(d for d in b.dateien() if d["name"] == "zeichnung.pdf")
assert seite.sperre_aufheben(ziel.get("datei", ziel["name"]), fragen=False)
b = abl.neu_lesen(b)
z = next(d for d in b.dateien() if d["name"] == "zeichnung.pdf")
assert z["viren"] == vp.FREIGEGEBEN and z["pfad"].is_file() and b.virus()      # die übrigen bleiben gesperrt
assert any("von PB als Fehlalarm freigegeben" in ak.verlauf_text(e) for e in b.verlauf)
ok("V3 Fund mit genannter Bedrohung bleibt gesperrt; „Sperre aufheben …“ gibt eine Datei frei, mit Verlauf")

# ------------------------------------------------------------------ V4 Einstellung im Fenster Outlook
from rohrlaser.anfragen_seite import OutlookDialog  # noqa: E402
dlg = OutlookDialog(seite)
assert dlg.viren.isChecked()
dlg.viren.setChecked(False)
assert not vp.an(db) and seite._viren_exe() is None
dlg.reject()
ok("V4 Fenster „Outlook …“: eigene Virenprüfung ein- und ausschaltbar (Vorgabe aus)")
print("Alle Tests bestanden.")
