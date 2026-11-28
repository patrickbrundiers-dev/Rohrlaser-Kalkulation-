"""Zugangssystem Paket C (zugang_anmeldung.py, zugang_fenster.py, Hauptfenster): Anmeldefenster, Entwickler-Ausweis
vom Stick und hinterlegt, Einmalcode, Sperre nach Inaktivität, Benutzer wechseln. Fälle C1–C16.

Deckt aus dem Auftrag (Abschnitt 10) Test 2 (Login bei jedem Start, letzter Benutzer nur als Kürzel, kein
automatisches Anmelden, Benutzer wechseln), Test 4 (Entwickler an fremder Installation nur mit Stick, hinterlegt)
und die Anmeldeteile von Test 7 (gleiche Meldung für falschen Benutzer und falsches Passwort, Einmalcode nur einmal,
Sperrbildschirm). Aufruf: python tests/test_zugang_anmeldung.py (mit PostgreSQL)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ROHRLASER_ARBEITSPLATZ"] = "PRUEFPLATZ"
tmp = Path(tempfile.mkdtemp(prefix="zugang_an_"))
os.environ["APPDATA"] = str(tmp / "profil")         # zweiter Ort der Entwickler-Sperre

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import admin_schutz, lizenz, rollen as R  # noqa: E402
from rohrlaser import zugang_authentifizierung as A  # noqa: E402
from rohrlaser import zugang_ausweis as AW  # noqa: E402
from rohrlaser import zugang_daten as D  # noqa: E402
from rohrlaser import zugang_pruefstelle as PS  # noqa: E402
from rohrlaser import zugang_fenster as ZF  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.zugang_anmeldung import LETZTER, Anmeldung  # noqa: E402

app = QApplication.instance() or QApplication([])
fehler = []
PW, PIN, EPW = "Max-Passwort-2026", "482915", "Entwickler-Passwort-2026!"
HEUTE = datetime.date.today()
SCHNELL = dict(n=2 ** 14)
privat = Ed25519PrivateKey.generate()
SCH = {"K9": lizenz.oeffentlich_text(privat)}


def fall(name, f):
    try:
        f()
        print("ok", name)
    except Exception as e:          # noqa: BLE001
        import traceback
        traceback.print_exc()
        fehler.append(f"{name}: {e!r}")


class Stelle:
    """Lizenzstelle für den Test: eigener Lizenzordner, Test-Schlüssel K9."""
    def __init__(self, ordner):
        self.ordner = Path(ordner)
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.schluessel = SCH
        self.hauptadmin_ok = self.admin_ok = False
        self.hauptadmin_seed = None

    def _spaetestes(self):
        return None


class Uhr:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


po = tmp / "daten"
db = Datenbank(po / "rohrlaser.db")
stelle = Stelle(po / "Lizenz")
stick = tmp / "stick"
stick.mkdir()
uhr = Uhr()
an = Anmeldung(db, stelle, uhr=uhr, stick_wurzeln=[stick])
an.ps.sitzungen.uhr = uhr


def c1():
    assert not an.pflicht() and an.auswahl() == []
    assert not R.benutzer_setzen(db, "MM", "Max Muster", [R.KALKULATION])
    assert not an.pflicht(), "ohne Passwort/PIN noch keine Pflicht"
    assert not R.zugang_setzen(db, "MM", passwort=PW)
    assert not R.benutzer_setzen(db, "WS", "Werner Säge", [R.WERKSTATT])
    assert not R.zugang_setzen(db, "WS", pin=PIN)
    db.einstellung_setzen(R.PFLICHT, "nein")
    assert an.pflicht(), "E5a: Pflicht, sobald es Benutzer mit Passwort oder PIN gibt (Schalter hebt sie nicht auf)"
    assert [k for k, _ in an.auswahl()] == ["MM", "WS"]


fall("C1 Anmeldepflicht sobald ein Konto Passwort oder PIN hat; Auswahl nach Name", c1)


def c2():
    e = an.anmelden("mm", PW)
    assert e.ok, e.text
    assert an.letzter() == "MM" and db.einstellung(LETZTER) == "MM"
    assert R.SITZUNG is None or R.SITZUNG.kuerzel == "MM"
    assert PS.AKTUELL is an.ps and PS.darf("angebot.bearbeiten") and not PS.darf("benutzer.verwalten")
    an.abmelden()
    assert not an.angemeldet() and not PS.darf("angebot.sehen")
    e = an.anmelden("WS", PIN)
    assert e.ok and an.sitzung.kuerzel == "WS"
    an.abmelden()


fall("C2 Passwort und PIN; letzter Benutzer nur als Kürzel gemerkt; Rechte gelten über die Prüfstelle", c2)


def c3():
    falsch = an.anmelden("MM", "falsch-falsch")
    unbekannt = an.anmelden("NIEMAND", "falsch-falsch")
    assert not falsch.ok and not unbekannt.ok and falsch.text == unbekannt.text == PS.FALSCH
    assert D.stand(db, "MM")["fehl"] == 1
    for _ in range(D.FEHL_FREI - 1):
        an.anmelden("MM", "falsch-falsch")
    assert "warten" in an.anmelden("MM", PW).text, "Sperre auch für das richtige Passwort"
    an2 = Anmeldung(db, stelle, uhr=uhr)
    assert "warten" in an2.anmelden("MM", PW).text, "Sperre gilt nach Neustart weiter"
    uhr.t += 7200
    assert an2.anmelden("MM", PW).ok
    an2.abmelden()


fall("C3 falscher Benutzer und falsches Passwort: gleiche Meldung; Sperre übersteht Neustart", c3)


def c4():
    g = A.totp_geheimnis_neu()
    assert not D.konto_speichern(db, "MM", totp=g)
    e = an.anmelden("MM", PW)
    assert not e.ok and e.zweiter_faktor_fehlt
    code = A.totp_code(g, uhr.t)
    e = an.anmelden("MM", PW, code)
    assert e.ok, e.text
    an.abmelden()
    e = an.anmelden("MM", PW, code)
    assert not e.ok and "schon benutzt" in e.text, e.text
    uhr.t += 60
    e = an.anmelden("MM", PW, A.totp_code(g, uhr.t))
    assert e.ok
    an.abmelden()
    assert not D.konto_speichern(db, "MM", totp="")


fall("C4 Einmalcode: wird verlangt, gilt, kein zweites Mal", c4)


AUSWEIS = AW.erstellen("Patrick", EPW, privat, "K9", "EW-2026-0001", HEUTE + datetime.timedelta(days=700),
                       heute=HEUTE, kdf=SCHNELL)


def c5():
    e = an.entwickler_anmelden(EPW)
    assert not e.ok and "Kein Entwickler-Ausweis" in e.text, "ohne Stick und ohne Hinterlegung kein Zugang"
    lizenz._schreiben(stick / "NexTube" / AW.DATEI, __import__("json").dumps(AUSWEIS))
    assert not an.entwickler_anmelden("falsch-falsch-falsch").ok
    e = an.entwickler_anmelden(EPW, heute=HEUTE)
    assert e.ok, e.text
    s = an.sitzung
    assert s.entwickler and "entwickler.dashboard" in s.rechte and "benutzer.verwalten" in s.rechte
    assert PS.darf("lizenz.verwalten") and PS.darf("entwickler.dashboard")
    if admin_schutz.SITZUNG is not None:
        assert admin_schutz.SITZUNG.haupt
    assert "Patrick" in an.text() and "Entwickler" in an.text()
    an.abmelden()
    assert not PS.darf("angebot.sehen")


fall("C5 Entwickler mit Ausweis vom Stick: voller Zugriff, ohne Rechner-ID und ohne Platzlizenz", c5)


def c6():
    (stick / "NexTube" / AW.DATEI).unlink()
    assert not an.entwickler_anmelden(EPW, heute=HEUTE).ok
    lizenz._schreiben(stick / AW.DATEI, __import__("json").dumps(AUSWEIS))
    assert an.entwickler_anmelden(EPW, heute=HEUTE).ok
    g = A.totp_geheimnis_neu()
    assert not an.ausweis_hinterlegen(g)
    an.abmelden()
    (stick / AW.DATEI).unlink()
    daten, von_stick, totp, wo = an.ausweis_finden()
    assert daten is not None and not von_stick and totp == g and "hinterlegt" in wo
    e = an.entwickler_anmelden(EPW, heute=HEUTE)
    assert not e.ok and e.zweiter_faktor_fehlt
    e = an.entwickler_anmelden(EPW, A.totp_code(g, uhr.t), heute=HEUTE)
    assert e.ok, e.text
    assert an.ausweis_hinterlegen() == "Der Ausweis ist hier schon hinterlegt."
    an.abmelden()
    assert "Hinterlegen geht nur" in an.ausweis_hinterlegen()


fall("C6 hinterlegter Ausweis: nur nach Anmeldung vom Stick, danach ohne Stick mit Einmalcode", c6)


def c7():
    assert an.anmelden("WS", PIN).ok
    s = an.sitzung
    uhr.t += s.minuten * 60 + 1
    assert an.ablauf_pruefen() and an.gesperrt()
    assert not PS.darf("produktion.bearbeiten"), "gesperrte Sitzung: keine Rechte"
    assert an.entsperren("000000") == PS.FALSCH
    assert an.entsperren(PIN) == "" and not an.gesperrt() and PS.darf("produktion.bearbeiten")
    assert an.sperren() and an.gesperrt()
    assert an.entsperren(PIN) == ""
    an.abmelden()
    assert not an.sperren()


fall("C7 Sperre nach Inaktivität und von Hand; entsperren nur mit eigenem Geheimnis", c7)


def c8():
    an.anmelden("MM", PW)
    d = ZF.AnmeldeDialog(None, an)
    assert d.auswahl.currentData() == "MM", "zuletzt angemeldeter Benutzer vorgewählt"
    assert d.geheim.text() == "" and not d.code.isVisibleTo(d), "kein Passwort vorbelegt, Einmalcode erst bei Bedarf"
    d.geheim.setText("falsch-falsch")
    d.pruefen()
    assert d.result() != QDialog.Accepted and d.fehler.text() == PS.FALSCH and d.geheim.text() == ""
    d.geheim.setText(PW)
    d.pruefen()
    assert d.result() == QDialog.Accepted and d.ergebnis.ok
    an.abmelden()
    d2 = ZF.AnmeldeDialog(None, an, beim_start=True)
    from PySide6.QtWidgets import QDialogButtonBox
    k = d2.findChild(QDialogButtonBox)
    assert k.button(QDialogButtonBox.Cancel).text() == "Beenden"
    d2.entwickler_umschalten()
    assert not d2.auswahl.isEnabled() and "hinterlegt" in d2.hinweis.text() and d2.code.isVisibleTo(d2)
    d2.entwickler_umschalten()
    assert d2.auswahl.isEnabled()


fall("C8 Anmeldefenster: letzter Benutzer vorgewählt, Fehler ohne Hinweis, Beenden beim Start, Entwickler-Modus", c8)


def c9():
    an.anmelden("WS", PIN)
    an.sperren()
    d = ZF.SperrDialog(None, an)
    d.reject()
    assert "Gesperrt" in d.fehler.text() and d.result() != QDialog.Accepted
    d.geheim.setText("111111")
    d.pruefen()
    assert d.result() != QDialog.Accepted and an.gesperrt()
    d.geheim.setText(PIN)
    d.pruefen()
    assert d.result() == QDialog.Accepted and not an.gesperrt()
    an.abmelden()


fall("C9 Sperrbildschirm: Esc entsperrt nicht, nur das richtige Geheimnis", c9)


def c10():
    class F(QObject):
        n = 0

        def sitzung_gesperrt(self):
            F.n += 1
    f = F()
    an.anmelden("WS", PIN)
    w = ZF.Waechter(f, an, takt_ms=10 ** 7)
    assert not w.pruefen() and F.n == 0
    uhr.t += an.sitzung.minuten * 60 + 1
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import Qt
    w.eventFilter(None, QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier))     # Eingabe hält die Sitzung
    assert not w.pruefen() and F.n == 0
    uhr.t += an.sitzung.minuten * 60 + 1
    assert w.pruefen() and F.n == 1 and an.gesperrt()
    w.beenden()
    an.abmelden()


fall("C10 Wächter: Eingabe hält die Sitzung offen, Ablauf ruft den Sperrbildschirm", c10)


def c11():
    class Stur(QDialog):
        def closeEvent(self, e):
            e.ignore()
    haupt = QDialog()
    a, b = QDialog(), Stur()
    a.setWindowTitle("Editor")
    a.show()
    assert ZF.offene_fenster_schliessen(haupt) and not a.isVisible()
    b.setWindowTitle("Editor mit Ungespeichertem")
    b.show()
    assert not ZF.offene_fenster_schliessen(haupt) and b.isVisible()
    b.hide()


fall("C11 vor dem Wechsel: offene Fenster schließen, ein Fenster mit Abbrechen verhindert den Wechsel", c11)


def c12():
    f = Hauptfenster(db, po, stumm=True)
    try:
        f._anmeldung = an
        assert f.anmeldung_beim_start(), "stumm: keine Abfrage"
        assert not f.benutzer_anmelden("MM", "falsch-falsch")
        assert f.benutzer_anmelden("MM", PW)
        assert R.angemeldet(db) == "MM" and "Max Muster" in f.benutzer_info.text()
        assert f.benutzer_wechseln(frage=False)
        assert not an.angemeldet() and R.SITZUNG.kuerzel == ""
        assert D.sitzungen_lesen(db)[-1]["grund"] == "beendet"
        assert f.benutzer_anmelden("WS", PIN) and R.angemeldet(db) == "WS"
        an.abmelden()
        uhr.t += 90                                 # neuer Einmalcode-Schritt
        e = an.entwickler_anmelden(EPW, A.totp_code(an.ausweis_finden()[2], uhr.t), heute=HEUTE)
        assert e.ok, e.text
        f.rechte_anwenden()
        assert "Entwickler" in f.benutzer_info.text() and admin_schutz.ist_admin(db)
    finally:
        f.close()
    assert not an.angemeldet(), "Programm zu: Sitzung beendet"


fall("C12 Hauptfenster: anmelden, Benutzer wechseln, Entwickler in der Statuszeile, Sitzung endet beim Schließen", c12)


def c13():
    texte = []
    for t in D.TABELLEN:
        texte += [" ".join(str(x) for x in z) for z in db.con.execute(f"SELECT * FROM {t}")]
    texte += [str(db.einstellung(LETZTER))]
    alles = "\n".join(texte)
    assert PW not in alles and PIN not in alles and EPW not in alles
    prot = (po / "Sicherheit" / "sicherheit.jsonl").read_text("utf-8")
    assert PW not in prot and PIN not in prot and EPW not in prot and "entwickler_zugriff" in prot


fall("C13 keine Passwörter, PINs oder Ausweis-Passwörter in Tabellen, Einstellungen und Protokolldatei", c13)


def c14():
    import ast
    quellen = [WURZEL / "programm" / "rohrlaser" / n for n in
               ("zugang_anmeldung.py", "zugang_fenster.py", "zugang_ausweis.py", "zugang_pruefstelle.py",
                "zugang_authentifizierung.py", "zugang_daten.py", "lizenz.py", "admin_schutz.py")]
    for q in quellen:
        baum = ast.parse(q.read_text("utf-8"))
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Assign) and isinstance(knoten.value, ast.Constant) and isinstance(
                    knoten.value.value, str):
                for z in knoten.targets:
                    name = getattr(z, "id", "") or getattr(z, "attr", "")
                    assert not (("PASSWORT" in name.upper() or "VERIFIZ" in name.upper() or "MASTER" in name.upper())
                                and len(knoten.value.value) >= 8), f"{q.name}: fester Wert {name}"
    assert not (WURZEL / "programm" / "rohrlaser" / "entwickler.py").exists(), "alter Zugang mit festem Prüfwert weg"


fall("C14 kein fest eingebautes Passwort oder Prüfwert im Programm; alter Entwicklerzugang entfernt", c14)


def c15():
    assert not D.konto_speichern(db, "WS", status="gesperrt")
    assert "WS" not in [k for k, _ in an.auswahl()]
    e = an.anmelden("WS", PIN)
    assert not e.ok and "gesperrt" in e.text
    assert not D.konto_speichern(db, "WS", status="aktiv")


fall("C15 gesperrtes Konto: nicht in der Auswahl, Anmeldung abgelehnt", c15)


def c16():
    an.anmelden("MM", PW)
    s = an.sitzung
    token = s.token
    an.abmelden(wechsel=True)
    try:
        an.ps.sitzungen.pruefen(token)
        raise AssertionError("beendetes Token gilt noch")
    except PermissionError:
        pass


fall("C16 nach dem Wechsel gilt das alte Sitzungs-Token nicht mehr", c16)

db.schliessen()
if fehler:
    print("FEHLER:", *fehler, sep="\n  ")
    sys.exit(1)
print("OK: Zugangssystem Paket C (Anmeldung, Entwickler-Ausweis, Sperre, Benutzer wechseln)")
