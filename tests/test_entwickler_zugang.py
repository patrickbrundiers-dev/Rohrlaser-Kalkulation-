"""Entwickler-Zugang: fester Login mit vollem Zugriff auf jeder Installation (Patrick 27.11.2026).

- Prüfwert aus dem Passwort (scrypt, festes Salz), Passwort nicht rückrechenbar; ohne hinterlegten Prüfwert aus;
- passt() nur beim richtigen Passwort; admin_schutz.ist_admin/ist_haupt wahr nach anmelden();
- anmelden() hebt den Lesemodus auf und schreibt ins Protokoll;
- fenster.Einstellungen.oeffnen und lizenz.LizenzStelle.hauptadmin_anmelden erkennen das Passwort;
- Werkzeug-Befehl entwickler-schluessel gibt nur den öffentlichen Prüfwert aus, nie das Passwort.
Aufruf: python tests/test_entwickler_zugang.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "werkzeuge"))

from rohrlaser import admin_schutz, entwickler  # noqa: E402


def ok(text):
    print("OK     " + text)


PW = "Entwickler-Geheim-2026!"
entwickler.KDF = dict(n=2 ** 10, r=8, p=1)      # im Test schnell
VERIF = entwickler.verifizierer(PW)
assert entwickler._b64_ok(VERIF), "Prüfwert ist ein 32-Byte-Ed25519-Schlüssel"
assert VERIF != PW and PW not in VERIF, "Passwort steckt nicht im Prüfwert"
assert entwickler.verifizierer(PW) == VERIF, "gleiches Passwort, gleicher Prüfwert (festes Salz)"
assert entwickler.verifizierer(PW + "x") != VERIF

# ohne hinterlegten Prüfwert: aus
entwickler.VERIFIZIERER = ""
entwickler.setzen(False)
assert not entwickler.aktiv() and not entwickler.passt(PW) and not entwickler.passt("")
ok("ohne hinterlegten Prüfwert ist der Entwickler-Zugang aus (passt() immer False)")

entwickler.VERIFIZIERER = VERIF
assert entwickler.aktiv()
assert entwickler.passt(PW) and not entwickler.passt("falsch") and not entwickler.passt("")
ok("passt() nur beim richtigen Passwort; Prüfwert ohne Passwort nutzlos")


class FalscheDb:
    def __init__(self):
        self.nur_lesen = "keine Lizenz"
        self.aufgehoben = False

    def einstellung(self, _n):
        return "x"      # Admin-Passwort gesetzt -> Schutz aktiv

    def lesemodus(self, grund):
        self.nur_lesen = grund
        self.aufgehoben = grund == ""


db = FalscheDb()
entwickler.setzen(False)
admin_schutz.SITZUNG = admin_schutz.Sitzung()
assert not admin_schutz.ist_admin(db) and not admin_schutz.ist_haupt(db), "vorher gesperrt"
protokoll = []
import rohrlaser.protokoll as P  # noqa: E402
P.warnung = lambda t, *a, **k: protokoll.append(t)
assert entwickler.anmelden(PW, db, wo="Test")
assert entwickler.frei() and admin_schutz.ist_admin(db) and admin_schutz.ist_haupt(db)
assert db.aufgehoben and db.nur_lesen == "", "Lesemodus aufgehoben"
assert any("Entwickler-Zugang" in t for t in protokoll), "ins Protokoll geschrieben"
assert not entwickler.anmelden("falsch", db), "falsches Passwort meldet nicht an"
ok("anmelden(): voller Zugriff (ist_admin/ist_haupt), Lesemodus aufgehoben, Protokolleintrag")

# lizenz.LizenzStelle.hauptadmin_anmelden erkennt das Passwort auch ohne Hauptadmin-Lizenz
from rohrlaser import lizenz  # noqa: E402

entwickler.setzen(False)


class Stelle:
    db = None
    hauptadmin_ok = admin_ok = False

    def pruefen(self, heute=None):
        self.geprueft = True


s = Stelle()
erg = lizenz.LizenzStelle.hauptadmin_anmelden(s, PW)
assert erg.ok and s.hauptadmin_ok and s.admin_ok and entwickler.frei(), "Start-Login mit Entwickler-Passwort"
ok("lizenz.LizenzStelle.hauptadmin_anmelden: Entwickler-Passwort schaltet beim Start frei")

# Werkzeug-Befehl: nur der öffentliche Prüfwert, nie das Passwort
import io  # noqa: E402
import contextlib  # noqa: E402

import lizenz_werkzeug as W  # noqa: E402

W.getpass.getpass = lambda *a, **k: PW
W.lizenzordner = lambda *a, **k: str(WURZEL)
aus = io.StringIO()
with contextlib.redirect_stdout(aus):
    W.main(["entwickler-schluessel"])
text = aus.getvalue()
assert "VERIFIZIERER" in text and VERIF in text and PW not in text, "nur Prüfwert, nicht das Passwort"
ok("Werkzeug entwickler-schluessel: gibt nur den öffentlichen Prüfwert aus")

print("alle Prüfungen bestanden")
