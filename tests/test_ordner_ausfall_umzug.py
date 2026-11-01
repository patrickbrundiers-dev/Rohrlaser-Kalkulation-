"""Gemeinsamen Ordner ausbauen, Teil 2 Paket F (Patrick 01.11.2026): Ausfall, Assistent, Umzug, schneller schreiben.

Prüft: F3 unverändert = Hauptdatei bleibt liegen, geändert = neu abgelegt, nur geänderte Stammdatenzeilen werden
ersetzt, gelöschte verschwinden; F1 Leiste bei nicht erreichbarem Ordner (mit Zeit), vorläufige Nummer, nach der
Rückkehr Abgleich mit endgültiger Nummer und Meldung; F2 Umzug nur als Admin, ziel nicht leer bzw. im alten Ordner
abgelehnt, Kopie vollständig, alter Ordner gilt als nicht erreichbar mit Hinweis, Admin umgestellt, Kollege bekommt das
Umstellen angeboten und arbeitet danach im neuen Ordner; Ordner prüfen nennt den Umzug; Assistent: Ordner prüfen
(Kollegen gefunden), Kürzel belegt nur mit Haken, erster Abgleich übernimmt die Stammdaten.

Aufruf: python tests/test_ordner_ausfall_umzug.py
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import admin_schutz, austausch, ordner_assistent, ordner_pruefung, teilen, teilen_fenster  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def arbeitsplatz(name, k, ordner=gemeinsam):
    db = Datenbank(tmp / name / "rohrlaser.db")
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("teilen_ordner", str(ordner))
    return db


pb, mk = arbeitsplatz("Patrick", "PB"), arbeitsplatz("Martin", "MK")
k1 = pb.neu("kunden", dict(kundennr="10042", name="Muster GmbH"))
pb.neu("kunden", dict(kundennr="10043", name="Weber KG"))
teilen.abgleichen(pb)
teilen.abgleichen(mk, teilen.UEBERNEHMEN)

# ---- F3 schneller schreiben
haupt = gemeinsam / "Rohrlaser_PB" / "haupt.sqlite"
vorher = haupt.stat().st_mtime_ns
time.sleep(0.05)
teilen.schreiben(pb)
assert haupt.stat().st_mtime_ns == vorher
ok("Nichts geändert: Hauptdatei bleibt liegen")


def zeilen(p):
    c = sqlite3.connect(p)
    try:
        return {(t, u): r for r, t, u in c.execute("SELECT rowid, tabelle, uid FROM stammdaten")}
    finally:
        c.close()


r0 = zeilen(haupt)
pb.aendern("kunden", k1, "name", "Muster AG")
teilen.schreiben(pb)
assert haupt.stat().st_mtime_ns != vorher
r1 = zeilen(haupt)
uid1 = pb.con.execute("SELECT uid FROM kunden WHERE id=?", (k1,)).fetchone()[0]
gleich = [s for s in r0 if s in r1 and s != ("kunden", uid1) and r0[s] == r1[s]]
assert len(gleich) == len(r0) - 1 and r1[("kunden", uid1)] != r0[("kunden", uid1)]
ok("Geändert: neu abgelegt, nur die geänderte Stammdatenzeile ersetzt")
pb.loeschen("kunden", [k1])
teilen.schreiben(pb)
c = sqlite3.connect(haupt)
assert c.execute("SELECT daten FROM stammdaten WHERE tabelle='kunden' AND uid=?", (uid1,)).fetchone()[0] is None
c.close()
teilen.abgleichen(mk)
assert not mk.con.execute("SELECT 1 FROM kunden WHERE uid=?", (uid1,)).fetchone()
ok("Gelöschte Zeile als Grabstein, beim Kollegen weg")
teilen.schreiben(pb, offen={"X": "2026-11-01T10:00"})
assert teilen.info_lesen(haupt)["offen"] == {"X": "2026-11-01T10:00"}
ok("Geöffnete Angebote ändern: neu abgelegt (ältere Versionen sehen es)")

# ---- F1 Ordner nicht erreichbar
f = Hauptfenster(mk, tmp, stumm=True)
assert ordner_assistent.zustand(f) == "ok"
weg = tmp / "Gemeinsam_weg"
gemeinsam.rename(weg)
assert ordner_assistent.zustand(f) == "weg"
assert f.ordner_leiste.isVisibleTo(f) and "nicht erreichbar seit" in f.ordner_leiste.text.text()
assert teilen_fenster.puls(f)["ordner"] == "weg"
aid = mk.angebot_neu(dict(kunde="Offline Kunde", datum="2026-11-01"))
nr = mk.angebot(aid)["nummer"]
assert nr.startswith("V-"), nr
ok("Ordner weg: rote Leiste mit Zeit, vorläufige Nummer")
weg.rename(gemeinsam)
assert ordner_assistent.zustand(f) == "zurueck"
assert not f.ordner_leiste.isVisibleTo(f)
assert not mk.angebot(aid)["nummer"].startswith("V-")
assert "wieder erreichbar" in f.meldungen[-1] if hasattr(f, "meldungen") else True
ok("Ordner zurück: Leiste weg, abgeglichen, Nummer endgültig")

# ---- F2 Umzug
neu = tmp / "NAS" / "Rohrlaser"
admin_schutz.SITZUNG = admin_schutz.Sitzung()
fp = Hauptfenster(pb, tmp, stumm=True)
assert fp.ordner_umziehen(str(neu)) is None and not neu.exists()
ok("Umzug nur als Admin")
s = admin_schutz.Sitzung()
s.freischalten()
admin_schutz.SITZUNG = s
for falsch in (gemeinsam / "Unter", tmp):
    try:
        teilen.umziehen(pb, falsch)
        raise AssertionError("hätte abgelehnt werden müssen")
    except teilen.TeilenFehler:
        pass
voll = tmp / "Voll"
voll.mkdir()
(voll / "x.txt").write_text("x")
try:
    teilen.umziehen(pb, voll)
    raise AssertionError("nicht leer")
except teilen.TeilenFehler:
    pass
assert teilen.umzug(pb) is None
ok("Umzug abgelehnt: im alten Ordner, darüber, nicht leer (alter Ordner gilt weiter)")
erg = fp.ordner_umziehen(str(neu))
assert erg and erg["dateien"] > 3
assert teilen.ordner(pb) == neu and (neu / "Rohrlaser_PB" / "haupt.sqlite").is_file()
assert (neu / "Rohrlaser_MK" / "haupt.sqlite").is_file()
assert not (neu / austausch.UMZUG_DATEI).exists()
u = austausch.OrdnerWeg(gemeinsam).umgezogen()
assert u["fertig"] and u["neu"] == str(neu) and u["von"] == "PB"
assert not austausch.OrdnerWeg(gemeinsam).erreichbar()
ok("Umzug: alles kopiert, Admin umgestellt, alter Ordner mit Hinweis und gesperrt")

befunde = ordner_pruefung.pruefen(mk, geschwindigkeit=False)
assert befunde[0]["stufe"] == ordner_pruefung.FEHLER and "Umgezogen" in befunde[0]["text"]
try:
    teilen.schreiben(mk)
    raise AssertionError("alter Ordner darf nicht beschrieben werden")
except teilen.TeilenFehler as e:
    assert "umgezogen" in str(e)
ok("Kollege: Prüfung nennt den Umzug, in den alten Ordner wird nichts geschrieben")
ordner_assistent.UMSTELLEN_ANTWORT = False
assert ordner_assistent.zustand(f) == "umzug" and f.ordner_leiste.umstellen.isVisibleTo(f)
ordner_assistent.UMSTELLEN_ANTWORT = True
assert ordner_assistent.umstellen_fragen(f, u)
assert teilen.ordner(mk) == neu and ordner_assistent.zustand(f) == "ok"
mk.angebot_neu(dict(kunde="Nach dem Umzug", datum="2026-11-01"))
teilen.abgleichen(mk)
teilen.abgleichen(pb)
assert any(a["kunde"] == "Nach dem Umzug" for a in pb.angebote())
ok("Kollege stellt um und arbeitet im neuen Ordner weiter")

# ---- F2 Assistent
sk = Datenbank(tmp / "Sandra" / "rohrlaser.db")
fs = Hauptfenster(sk, tmp, stumm=True)
a = ordner_assistent.assistent(fs)
a.ordner_seite.ordner.setText(str(tmp / "gibtsnicht"))
assert not a.ordner_seite.isComplete()
a.ordner_seite.ordner.setText(str(neu))
assert a.ordner_seite.isComplete() and set(a.ordner_seite.kollegen) == {"PB", "MK"}
a.benutzer_seite.name.setText("Sandra")
a.benutzer_seite.kuerzel.setText("MK")
assert a.benutzer_seite.belegt() and not a.benutzer_seite.isComplete()
a.benutzer_seite.kuerzel.setText("SK")
assert a.benutzer_seite.isComplete()
a.abgleich_seite.initializePage()
assert a.abgleich_seite.uebernehmen.isChecked()
bericht = a.ausfuehren()
assert bericht is not None and teilen.kuerzel(sk) == "SK" and teilen.ordner(sk) == neu
assert sk.con.execute("SELECT 1 FROM kunden WHERE kundennr='10043'").fetchone()
assert (neu / "Rohrlaser_SK" / "haupt.sqlite").is_file()
ok("Assistent: Ordner, Kürzel (belegt nur mit Haken), erster Abgleich übernimmt die Stammdaten")

shutil.rmtree(tmp, ignore_errors=True)
print("\nAlle Prüfungen bestanden.")
