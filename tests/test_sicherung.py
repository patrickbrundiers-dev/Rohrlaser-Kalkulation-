"""Datenort (portabel/installiert), Sperre, geprüfte und geschützte Sicherungen, Wiederherstellen, Export/Import.

Aufruf: python tests/test_sicherung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path.insert(0, str(PROGRAMM))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import orte, update  # noqa: E402
from rohrlaser.datenbank import (SCHEMA_VERSION, Datenbank, SicherungFehler, datei_info,  # noqa: E402
                                 datei_uebernehmen)

tmp = Path(tempfile.mkdtemp())

# 1) Orte: Portabel.ini, alter ZIP-Stand mit Ordner Daten, Entwicklung, installiert, --daten
p = tmp / "zip"
p.mkdir()
(p / orte.PORTABEL).write_text("# portabel\n", encoding="utf-8")
o = orte.ermitteln(p, frozen=True)
assert o.portabel and o.daten == p / "Daten" and o.ablage == p / "Angebote" and o.datei == p / "Daten" / "rohrlaser.db"
(p / orte.PORTABEL).write_text("daten = ..\\Netz\\Daten\nablage = Ablage\n".replace("\\", "/"), encoding="utf-8")
o = orte.ermitteln(p, frozen=True)
assert o.daten == p / ".." / "Netz" / "Daten" and o.ablage == p / "Ablage", o
alt = tmp / "alt"
(alt / "Daten").mkdir(parents=True)
o = orte.ermitteln(alt, frozen=True)
assert o.portabel and o.daten == alt / "Daten" and "Daten" in o.grund
inst = tmp / "Programs" / "Rohrlaser Angebotskalkulation"
inst.mkdir(parents=True)
o = orte.ermitteln(inst, frozen=True, umgebung={"LOCALAPPDATA": str(tmp / "Local")}, dokumente=tmp / "Doks")
assert not o.portabel and o.art == "installiert"
assert o.daten == tmp / "Local" / "Rohrlaser Angebotskalkulation" / "Daten" and o.ablage == tmp / "Doks" / "Rohrlaser Angebote"
assert orte.ermitteln(inst, frozen=False).portabel                       # Entwicklung
o = orte.ermitteln(inst, daten=tmp / "anders", frozen=True, umgebung={"LOCALAPPDATA": str(tmp / "Local")})
assert o.daten == tmp / "anders" and o.grund == "Startparameter --daten"
# Portabel.ini gehört nie zum Update (installiert darf sie nie entstehen, portabel nie verschwinden)
assert not update.sicherer_pfad(orte.PORTABEL) and orte.PORTABEL not in update.programmdateien(p)

# 2) Sperre: ein zweites Programm (eigener Prozess) kommt nicht an die Datendatei, nach dem Freigeben schon
d = tmp / "sperre"
s = orte.Sperre(d)
info = orte.sperr_info(d)
assert info["pid"] == os.getpid() and info["version"]
code = ("import sys; sys.path.insert(0, sys.argv[1]); from rohrlaser import orte\n"
        "try:\n    orte.Sperre(sys.argv[2]).freigeben(); print('frei')\n"
        "except orte.Gesperrt as e:\n    print('gesperrt', e.info.get('pid'))\n")
aus = subprocess.run([sys.executable, "-c", code, str(PROGRAMM), str(d)], capture_output=True, text=True).stdout
assert aus.strip() == f"gesperrt {os.getpid()}", aus
s.freigeben()
assert not (d / orte.SPERRE).exists()
aus = subprocess.run([sys.executable, "-c", code, str(PROGRAMM), str(d)], capture_output=True, text=True).stdout
assert aus.strip() == "frei", aus

# 3) Sicherung: geprüft, mit Beschreibung; geschützte Sicherungen überleben das Aufräumen
db = Datenbank(tmp / "a" / "rohrlaser.db")
aid = db.angebot_neu(dict(kunde="Sicherungstest"))
db.position_neu(aid, dict(pos=10, artikel="S-1", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                          stueck=5))
vor = db.sicherung(zusatz="vor_update")
beschreibung = json.loads(vor.with_suffix(".json").read_text(encoding="utf-8"))
assert beschreibung["schema"] == SCHEMA_VERSION and beschreibung["anzahl"]["angebote"] == 1
assert beschreibung["anzahl"]["positionen"] == 1 and beschreibung["art"] == "vor_update" and len(beschreibung["sha256"]) == 64
schema_alt = vor.with_name(vor.name.replace("vor_update", "vor_Schema_14"))
shutil.copyfile(vor, schema_alt)
for _ in range(35):                     # mehr laufende Sicherungen, als behalten werden
    db.sicherung()
ordner = vor.parent
laufend = [x for x in ordner.glob("*.db") if "_vor_" not in x.name]
assert len(laufend) == 30, len(laufend)
assert vor.exists() and schema_alt.exists(), "geschützte Sicherung beim Aufräumen gelöscht"
assert len(list(ordner.glob("*.json"))) == 31          # Beschreibungen gelöschter Sicherungen sind auch weg
for _ in range(12):                     # von jeder geschützten Art bleiben die letzten 10
    db.sicherung(zusatz="vor_update")
assert len([x for x in ordner.glob("*_vor_update*.db")]) == 10 and schema_alt.exists()
assert db.anzahl("angebote") == 1, "Aufräumen darf nie Daten löschen"

# 4) Wiederherstellen: Stand zurück, vorher Sicherung des jetzigen Stands; neuere und defekte Dateien abgelehnt
stand = db.sicherung()
db.angebot_loeschen(aid) if hasattr(db, "angebot_loeschen") else db.con.execute("DELETE FROM angebote")
db.einstellung_setzen("ablageordner", "geändert")
assert db.anzahl("angebote") == 0
info, vorher = db.wiederherstellen(stand)
assert db.anzahl("angebote") == 1 and db.anzahl("positionen") == 1 and db.einstellung("ablageordner") != "geändert"
assert datei_info(vorher)["anzahl"]["angebote"] == 0 and "_vor_Wiederherstellung" in vorher.name
neuer = tmp / "neuer.db"
shutil.copyfile(stand, neuer)
c = sqlite3.connect(neuer)
c.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
c.commit()
c.close()
for falsch, text in ((neuer, "neueren Programmversion"), (tmp / "kaputt.db", "keine lesbare"),
                     (tmp / "fremd.db", "keine Datendatei")):
    if falsch.name == "kaputt.db":
        falsch.write_bytes(b"SQLite format 3\x00" + b"\x01" * 3000)
    if falsch.name == "fremd.db":
        sqlite3.connect(falsch).execute("CREATE TABLE x (a)").connection.close()
    try:
        db.wiederherstellen(falsch)
        raise AssertionError(f"{falsch.name} hätte abgelehnt werden müssen")
    except SicherungFehler as e:
        assert text in str(e), e
assert db.anzahl("angebote") == 1, "abgelehnte Wiederherstellung darf nichts ändern"

# 5) Export/Import: vollständig, Prüfsumme; beschädigtes Export abgelehnt
export = tmp / "Export" / "Rohrlaser-Daten.zip"
info = db.exportieren(export)
with zipfile.ZipFile(export) as z:
    assert sorted(z.namelist()) == ["info.json", "rohrlaser.db"]
    assert json.loads(z.read("info.json"))["anzahl"]["angebote"] == 1
db2 = Datenbank(tmp / "b" / "rohrlaser.db")            # zweite Variante (z. B. installiert) mit Beispieldaten
assert db2.anzahl("angebote") == 0
db2.wiederherstellen(export, zusatz="vor_Import")
assert db2.anzahl("angebote") == 1 and db2.angebot(db2.angebote()[0]["id"])["kunde"] == "Sicherungstest"
assert any(x.name.endswith("_vor_Import.db") for x in (tmp / "b" / "Sicherung").glob("*.db"))
kaputt = tmp / "kaputt.zip"
with zipfile.ZipFile(export) as z, zipfile.ZipFile(kaputt, "w") as k:
    k.writestr("info.json", z.read("info.json"))
    k.writestr("rohrlaser.db", z.read("rohrlaser.db")[:-4096] + b"\x00" * 4096)
try:
    db2.wiederherstellen(kaputt)
    raise AssertionError("beschädigter Export hätte abgelehnt werden müssen")
except SicherungFehler as e:
    assert any(t in str(e) for t in ("Prüfsumme", "beschädigt", "keine lesbare")), e
db2.schliessen()

# 6) Übernahme ohne offene Datenbank (erster Start): Ziel neu bzw. alte Datei nach Sicherung verschoben
ziel = tmp / "c" / "Daten" / "rohrlaser.db"
datei_uebernehmen(export, ziel)
assert datei_info(ziel)["anzahl"]["angebote"] == 1
ziel.write_bytes(b"defekt")
datei_uebernehmen(stand, ziel)
assert datei_info(ziel)["anzahl"]["angebote"] == 1
assert [x.read_bytes() for x in (ziel.parent / "Sicherung").glob("*_vor_Uebernahme.db")] == [b"defekt"]

# 7) Programm: Menü und Start-Knopf, Ersetzen schließt offene Angebote, Dialog listet die Sicherungen
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.__main__ import info as info_schreiben  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.sicherung_dialog import WiederherstellenDialog, art_text  # noqa: E402

app = QApplication.instance() or QApplication([])
o = orte.ermitteln(inst, frozen=True, umgebung={"LOCALAPPDATA": str(tmp / "Local")}, dokumente=tmp / "Doks")
f = Hauptfenster(db, inst, stumm=True, orte=o)
assert f.ablage() == tmp / "Doks" / "Rohrlaser Angebote"
menue = [a.text() for a in f.menuBar().actions()[0].menu().actions()]
for text in ("Sicherung wiederherstellen …", "Daten exportieren …", "Daten importieren …"):
    assert text in menue, menue
f.angebot_oeffnen(db.angebote()[0]["id"])
db.con.execute("DELETE FROM positionen")
db.con.commit()
assert f.daten_ersetzen(stand)["anzahl"]["positionen"] == 1 and not f.offen and db.anzahl("positionen") == 1
assert f.daten_ersetzen(db.pfad) is None                 # die eigene Datei nicht
assert f.export_schreiben(tmp / "Export" / "zwei.zip")["anzahl"]["angebote"] == 1
dlg = WiederherstellenDialog(f)
arten = {z["art"] for z in dlg.zeilen}
assert {"vor Update", "vor Schema-Umstellung", "vor Wiederherstellung", "täglich / von Hand"} <= arten, arten
assert dlg.tabelle.rowCount() == len(dlg.zeilen) > 40 and dlg.zeilen[0]["zeit"] >= dlg.zeilen[-1]["zeit"]
assert art_text("rohrlaser_2026-10-20_beenden.db") == "beim Beenden"
dlg.close()
f.close()
db.schliessen()

# 8) --info legt die Datendatei am ermittelten Ort an und meldet portabel/installiert
erg = tmp / "info.json"
assert info_schreiben(o, erg) == 0
werte = json.loads(erg.read_text(encoding="utf-8"))
assert werte["portabel"] is False and Path(werte["daten"]) == o.daten and werte["schema"] == SCHEMA_VERSION
assert (o.daten / "rohrlaser.db").exists() and not (o.daten / orte.SPERRE).exists()

print("OK: Datenort, Sperre, geprüfte und geschützte Sicherungen, Wiederherstellen, Export/Import, Übernahme")
