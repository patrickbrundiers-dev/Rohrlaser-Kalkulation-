"""Prüft das automatische Optimieren (Plan „Arbeitsabläufe effizienter“ W1, Schritt AB2): Entwürfe bis zur Grenze
der Einstellung optimieren kurz nach einer Änderung selbst; verschickte, fremde, große Angebote und Angebote im
Lesemodus nicht; ein Fehler erscheint nur in der Statuszeile und wird mit denselben Eingaben nicht wiederholt.

Aufruf: python tests/test_auto_optimieren.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def warten(bedingung, sekunden=10):
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.02)
    return False


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
assert db.einstellung("auto_optimieren_bis") == 100
a = beispiel_angebot.anlegen(db)
s = fenster.angebot_oeffnen(a)

# Neues Angebot (Entwurf, nicht optimiert): optimiert sich nach der Pause selbst
assert s.stand_optimierung() != "aktuell" and s.auto_optimieren_moeglich()
assert s._auto_timer.isActive()
assert warten(lambda: s.stand_optimierung() == "aktuell"), s.stand_optimierung()
assert not s._auto_timer.isActive()
ok("Neues Angebot: nach der Pause automatisch optimiert, Schnittplan aktuell")

# Änderung: wieder veraltet, Zeitgeber läuft, danach aktuell
db.position_aendern(s.positionen[0]["id"], "stueck", (s.positionen[0]["stueck"] or 1) + 1)
s.neu_laden()
assert s.stand_optimierung() != "aktuell" and s._auto_timer.isActive()
assert warten(lambda: s.stand_optimierung() == "aktuell")
ok("Stückzahl geändert: automatisch neu optimiert")

# Gleiches Ergebnis wie von Hand
auto = s.ergebnis
assert s.optimieren()
assert [len(x["teile"]) for x in s.ergebnis["stangen"]] == [len(x["teile"]) for x in auto["stangen"]]
ok("Automatisch optimiert = von Hand optimiert (gleiche Stangen und Teile)")

# Grenze 0 = aus; Grenze kleiner als Positionen = aus
for grenze in (0, 1):
    db.einstellung_setzen("auto_optimieren_bis", grenze)
    db.position_aendern(s.positionen[0]["id"], "stueck", s.positionen[0]["stueck"] + 1)
    s.neu_laden()
    assert not s.auto_optimieren_moeglich() and not s._auto_timer.isActive(), grenze
db.einstellung_setzen("auto_optimieren_bis", 100)
s.neu_laden()
assert s.auto_optimieren_moeglich()
ok("Einstellung 0 = aus, mehr Positionen als die Grenze = aus")

# Verschickte Angebote behalten ihren Schnittplan
db.vorgang_setzen(a, "Verschickt")
s.neu_laden()
assert not s.auto_optimieren_moeglich() and not s._auto_timer.isActive()
db.vorgang_setzen(a, "Entwurf")
s.neu_laden()
assert s.auto_optimieren_moeglich()
ok("Verschickt: kein automatisches Optimieren, Entwurf wieder ja")

# Fehler: nur Statuszeile, mit denselben Eingaben kein zweiter Versuch
vorher = s._optimierung_rechnen


def fehler(*_):
    raise ValueError("Testfehler")


s._optimierung_rechnen = fehler
assert s.auto_optimieren() is False
assert not s.auto_optimieren_moeglich()
s._optimierung_rechnen = vorher
db.position_aendern(s.positionen[0]["id"], "stueck", s.positionen[0]["stueck"] + 1)
s.neu_laden()
assert s.auto_optimieren_moeglich() and s.auto_optimieren() and s.stand_optimierung() == "aktuell"
ok("Fehler beim automatischen Optimieren: kein Meldungsfenster, erst nach neuer Änderung wieder versucht")

# Lesemodus
db.position_aendern(s.positionen[0]["id"], "stueck", s.positionen[0]["stueck"] + 1)
db.nur_lesen = "Test Lesemodus"
s.neu_laden()
assert not s.auto_optimieren_moeglich()
db.nur_lesen = None
ok("Lesemodus: kein automatisches Optimieren")

print("Alle Prüfungen bestanden.")
