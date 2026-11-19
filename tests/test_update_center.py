"""Update-Center im Programm (Hilfe → Update-Center, Auftrag Patrick 19.11.2026): Suche über Update-Ordner und
Internet, Update-Datei einspielen, „Beim Beenden“, Rückmeldung in den Update-Ordner, Einstellungen, Verteilen als
Admin, vorige Version wiederherstellen. Mit eigenen Testschlüsseln und einem nachgebauten Programmordner.

Aufruf: python tests/test_update_center.py
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from rohrlaser import lizenz, update, update_fenster, update_quellen, update_verteilen  # noqa: E402

PRIVAT = Ed25519PrivateKey.generate()
update.update_schluessel = lambda: {"U1": lizenz.oeffentlich_text(PRIVAT)}
os.environ.pop("RL_UPDATE_QUELLE", None)
tmp = Path(tempfile.mkdtemp(prefix="upd_center_"))
app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


def programm(ordner, kennung):
    ordner = Path(ordner)
    for rel, inhalt in {"Rohrlaser-Angebotskalkulation.exe": b"MZ" + kennung + bytes(50_000),
                        "_internal/klein.pyd": b"pyd" + kennung}.items():
        (ordner / rel).parent.mkdir(parents=True, exist_ok=True)
        (ordner / rel).write_bytes(inhalt)
    return ordner


def build(ordner, ziel, stand):
    liste = update.erstellen(ordner, ziel, stand, aenderung=f"Neu in {stand}")
    sig = update.signatur_erstellen((Path(ziel) / update.DATEILISTE).read_bytes(), PRIVAT, "U1")
    (Path(ziel) / update.SIGNATUR).write_text(json.dumps(sig), encoding="ascii")
    return liste


def warten(bedingung, s=20):
    ende = time.monotonic() + s
    while not bedingung() and time.monotonic() < ende:
        app.processEvents()
        time.sleep(0.02)
    assert bedingung(), "Zeitüberschreitung"


inst = programm(tmp / "inst", b"-1")
build(programm(tmp / "q1", b"-1"), tmp / "b1", 1)
for n in (update.DATEILISTE, update.SIGNATUR):
    shutil.copyfile(tmp / "b1" / n, inst / n)
l2 = build(programm(tmp / "q2", b"-2"), tmp / "b2", 2)

from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

db = Datenbank(tmp / "daten" / "rohrlaser.db")
netz = tmp / "netz"
db.einstellung_setzen("update_ordner", str(netz))
f = Hauptfenster(db, inst, stumm=True)
u = f.updater
assert u.feste_quelle is None and [q.art for q in u.quellen()] == ["ordner", "internet"]
meldungen, fragen = [], []
QMessageBox.information = staticmethod(lambda *a, **k: meldungen.append(a[2]))
QMessageBox.warning = staticmethod(lambda *a, **k: meldungen.append("WARNUNG " + a[2]))
QMessageBox.question = staticmethod(lambda *a, **k: fragen.append(a[2]) or QMessageBox.Yes)

# Admin stellt Stand 2 im Update-Ordner bereit (hier aus einem Ordner statt aus dem Internet)
from rohrlaser import update_center  # noqa: E402
c = update_center.UpdateCenter(f)
assert not c.reiter.isTabVisible(c.i_verteilen), "Verteilen nur für Admins"
assert c.bereitstellen(update_quellen.Quelle(str(tmp / "b2" / update.DATEILISTE))) is None, "ohne Admin nichts"
from rohrlaser import admin_schutz  # noqa: E402
admin_schutz.SITZUNG = admin_schutz.Sitzung()
admin_schutz.SITZUNG.freischalten()
c.aktualisieren()
assert c.reiter.isTabVisible(c.i_verteilen)
assert "noch leer" in c.l_ziel.text()
c.bereitstellen(update_quellen.Quelle(str(tmp / "b2" / update.DATEILISTE), "Testserver"))
assert "Stand 2" in c.l_ziel.text()
c.v_hinweis.setText("Bitte heute aktualisieren")
c.v_nur_ordner.setChecked(True)
assert c.freigabe_speichern()["nur_ordner"]
assert [q.art for q in u.quellen()] == ["ordner"], "Freigabe: nur aus dem Ordner"
datei = c.datei_erstellen(str(tmp / "Rohrlaser-Update.rlupdate"))
assert datei and datei.is_file()
ok("Verteilen: bereitstellen, Freigabe (nur Ordner, Hinweis), Update-Datei erstellen")

# Suche aus dem Update-Center (im Hintergrund), Anzeige der Quellen
c.suchen()
warten(lambda: not u._laeuft and u.letzte_suche is not None)
app.processEvents()
assert "Stand 2" in c.l_verfuegbar.text() and "Update verfügbar" in c.l_status.text() and c.k_jetzt.isEnabled()
assert c.t_quellen.rowCount() == 1 and "gültig signiert" in c.t_quellen.item(0, 2).text()
assert any("Hinweis vom Administrator" in str(e[1]) for e in f.verlauf.eintraege), f.verlauf.eintraege
ok("Suche: Update-Ordner gefunden, Stand 2 verfügbar, Hinweis des Admins angezeigt")

# „Beim Beenden“: laden + sichern jetzt, eingespielt erst nach dem normalen Beenden
gezeigt = []
update_fenster.frage = lambda eltern, online, lokal, quelle_text="", freigabe=None: gezeigt.append(
    (quelle_text, freigabe)) or type("Frage", (), dict(exec=lambda s: 0, clickedButton=lambda s: s.beenden,
                                                       jetzt=object(), beenden=object()))()
c.jetzt()
assert gezeigt and "Update-Ordner" in gezeigt[0][0] and gezeigt[0][1]["hinweis"] == "Bitte heute aktualisieren"
assert u.ausstehend and u.beim_beenden, "geladen, Programm läuft weiter"
assert update.lokale_liste(inst)["stand"] == 1, "noch nichts ausgetauscht"
assert any((tmp / "daten" / "Sicherung").glob("*vor_update*")), "vorher gesichert"
neustart = []
assert update_fenster.nach_beenden(inst, u.ausstehend, starten=lambda exe, arg: neustart.append(arg)) == "ok"
assert update.lokale_liste(inst)["stand"] == 2 and neustart == [["--nach-update", "ok"]]
v = update_quellen.verlauf_lesen(u.verlauf_pfad())
assert v[0]["art"] == "eingespielt" and v[0]["ergebnis"] == "ok" and v[1]["art"] == "geladen"
p = update_verteilen.plaetze(netz)
assert len(p) == 1 and p[0]["stand"] == 2 and p[0]["ergebnis"] == "ok", p
u.ausstehend, u.beim_beenden = None, False
ok("Beim Beenden: geladen und gesichert, nach dem Beenden eingespielt, Verlauf und Rückmeldung geschrieben")

# Vorige Version wiederherstellen (aus dem letzten Update)
update.aufraeumen(inst)
u.lokal = update.lokale_liste(inst)
c.aktualisieren()
assert "Stand 1" in c.l_vorige.text() and c.k_zurueck.isEnabled()
u.beenden = lambda: True
assert u.zuruecksetzen() and fragen and "Zurück auf" in fragen[-1]
assert update_fenster.nach_beenden(inst, u.ausstehend, starten=lambda *a: None) == "ok"
assert update.lokale_liste(inst)["stand"] == 1
assert update_quellen.verlauf_lesen(u.verlauf_pfad())[0]["zurueck"] is True
u.ausstehend = None
u.lokal = update.lokale_liste(inst)
ok("Vorige Version: nach Rückfrage zurück auf Stand 1, im Verlauf vermerkt")

# Update-Datei einspielen (z. B. vom USB-Stick); ältere Datei: nichts zu tun
update_fenster.frage = lambda *a, **k: type("Frage", (), dict(exec=lambda s: 0, clickedButton=lambda s: s.jetzt,
                                                               jetzt=object()))()
assert u.datei_einspielen(str(datei)) and u.ausstehend
assert update_fenster.nach_beenden(inst, u.ausstehend, starten=lambda *a: None) == "ok"
assert update.lokale_liste(inst)["stand"] == 2
u.ausstehend = None
u.lokal = update.lokale_liste(inst)
alt = update_verteilen.datei_erstellen(tmp / "b1", tmp / "alt.rlupdate")
assert not u.datei_einspielen(str(alt)) and "nichts zu tun" in meldungen[-1]
boese = tmp / "boese.rlupdate"
boese.write_bytes(b"kein zip")
assert not u.datei_einspielen(str(boese)) and meldungen[-1].startswith("WARNUNG")
ok("Update-Datei: eingespielt; ältere Version abgelehnt (Downgrade), kaputte Datei gemeldet")

# Einstellungen: ungültiger Proxy wird abgelehnt, gültige gespeichert
c.e_proxy.setText("max:geheim@proxy:8080")
assert not c.einstellungen_speichern() and "nie gespeichert" in meldungen[-1]
c.e_proxy.setText("proxy.firma.local:8080")
c.e_quelle.setCurrentIndex(c.e_quelle.findData(update_quellen.INTERNET))
assert c.einstellungen_speichern()
assert db.einstellung("update_proxy") == "proxy.firma.local:8080" and db.einstellung("update_quelle") == "internet"
c.e_proxy.setText("")
c.e_quelle.setCurrentIndex(0)
assert c.einstellungen_speichern() and db.einstellung("update_proxy") == "system"
ok("Einstellungen: Proxy geprüft (keine Passwörter), Quelle gespeichert")

# Diagnose-Bericht speichern (Befunde wie nach einem Lauf)
c._diagnose_fertig([dict(gruppe="Netz", name="Verbindung github.com:443", stufe="fehler", text="abgelehnt",
                         tipp="Port 443 freigeben")])
assert c.t_diag.rowCount() == 1 and c.k_bericht.isEnabled()
pfad = c.bericht_speichern(str(tmp / "diag.txt"))
assert "FEHLER" in Path(pfad).read_text(encoding="utf-8")
ok("Diagnose: Befunde angezeigt, Bericht für die IT gespeichert")

# Menü
namen = [a.text() for m in f.menuBar().findChildren(type(f.menuBar().actions()[0].menu())) for a in m.actions()]
assert "Update-Center …" in namen and "Nach Updates suchen …" in namen
c.close()
f.close()
db.schliessen()
shutil.rmtree(tmp, ignore_errors=True)
print("OK: Update-Center (Verteilen, Suche, Beim Beenden, vorige Version, Update-Datei, Einstellungen, Diagnose)")
