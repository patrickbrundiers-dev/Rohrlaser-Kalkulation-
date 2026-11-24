"""Rohrlaser Auslastung: Datenspeicher je PC (SQLite-Datei → PostgreSQL auf diesem PC und zurück; Patrick 14.11.2026).

Prüft: Umstellen nur für den Hauptadmin (Einstellungen → Datenspeicher), im Netzordner (gemeinsamer Ordner für
mehrere Plätze) nicht; vorher eine geprüfte Sicherung, alle Zeilen übernommen und verglichen, Merkdatei am alten
Ort mit dem Namen des PCs, Rückfall-Datei unverändert; danach öffnet Daten(pfad) PostgreSQL, Änderungen, Takt
(anderer Platz) und Sicherung (als SQLite-Datei) gehen; ein anderer PC bekommt eine klare Meldung; „Datenbank an
anderem Ort“ legt dort eine normale SQLite-Datei an; Zurückstellen schreibt alles (auch Neues) in die SQLite-Datei;
Fehlerfall (schon Daten im PostgreSQL-Ordner) ändert nichts. Ohne PostgreSQL-Programme oder als root (initdb
verweigert root) werden nur die Prüfungen ohne Server gemacht.

Aufruf: python tests/test_auslastung_datenspeicher.py
"""
import datetime
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtWidgets import QApplication  # noqa: E402
from rl_auslastung import daten, speicher  # noqa: E402
from rl_auslastung.fenster import EINSTELLUNGEN, Hauptfenster  # noqa: E402
from rohrlaser import datenspeicher, db_verbindung, pg_lokal  # noqa: E402


def ok(text):
    print("OK     " + text)


if db_verbindung.pg_test_an():            # Prüflauf gegen PostgreSQL: hier geht es um den Weg von SQLite dorthin
    print("Prüflauf gegen PostgreSQL: Test gilt nur für die SQLite-Datei, übersprungen")
    sys.exit(0)
app = QApplication.instance() or QApplication([])
HEUTE = datetime.date(2026, 11, 16)
tmp = Path(tempfile.mkdtemp())
pfad = tmp / "Daten" / "Auslastung.db"
db = daten.Daten(pfad, wer="chef")
a1 = db.auftrag_speichern(dict(nummer="U-1", kunde="Umzug GmbH", maschine="LT7", kalk_min=90,
                               liefertermin=datetime.date(2026, 11, 20), material="RR 40x2"))
db.auftrag_speichern(dict(nummer="U-2", kunde="Ölmühle", maschine="T03", kalk_min=45, bemerkung="Text; mit Semikolon"))
db.fertig_melden(db.auftrag_speichern(dict(nummer="U-3", maschine="T11", kalk_min=30)), 35, datetime.date(2026, 11, 13))
db.maschine_speichern("Säge", 7.5, True)
db.einstellung_setzen("wochen", 6)
assert not db.postgres and speicher.art(pfad) == speicher.SQLITE
assert speicher.umstellen_moeglich(db) == ""
assert speicher.im_netz(Path("//server/freigabe/Auslastung.db")) and speicher.im_netz(Path("\\\\srv\\a\\x.db"))
assert not speicher.im_netz(pfad)
assert speicher._anweisungen("CREATE TABLE a (x TEXT); INSERT INTO a VALUES ('1;2'); ") == [
    "CREATE TABLE a (x TEXT);", "INSERT INTO a VALUES ('1;2');"]

f = Hauptfenster(db, heute=HEUTE, platz=tmp / "platz")
f.show()
app.processEvents()
assert f.datenspeicher_wechseln(fragen=lambda _t: True) is None and not f.db.postgres, "nur Hauptadmin"
f.reiter.setCurrentIndex(EINSTELLUNGEN)
app.processEvents()
assert "SQLite" in f.e_pfad.text() and str(pfad) in f.e_pfad.text()
ok("Ohne Hauptadmin wird nicht umgestellt; Netzordner (gemeinsamer Ordner) wird erkannt; Skript mit ; in Texten")

try:
    bin_ordner = pg_lokal.programme()
    import psycopg  # noqa: F401
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise pg_lokal.PgFehlt("als root (initdb verweigert root)")
except (pg_lokal.PgFehlt, ImportError) as e:
    print(f"PostgreSQL-Teil übersprungen: {e}")
    f.close()
    f.db.schliessen()
    sys.exit(0)

vorher = {t: f.db.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
          for t in ("auftraege", "maschinen", "einstellungen", "richtzeiten", "verlauf")}
inhalt_vorher = pfad.read_bytes()
erg = f.datenspeicher_wechseln(fragen=lambda _t: True, hauptadmin=True)
assert erg and f.db.postgres and speicher.art(pfad) == speicher.POSTGRES and pfad.stat().st_size < 64 * 1024
assert "vor_PostgreSQL" in Path(erg["sicherung"]).name and erg["auftraege"] == 3
assert erg["rueckfall"].read_bytes() == inhalt_vorher, "Rückfall-Datei = Datei vor dem Umstellen"
assert (pfad.parent / speicher.ORDNER / "pg" / "PG_VERSION").exists()
m = datenspeicher.merkdatei_lesen(pfad)
assert m["ordner"] == speicher.ORDNER and m["rechner"] == speicher.rechner() and m["wer"] == "chef"
nachher = {t: f.db.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in vorher}
assert nachher == vorher, (vorher, nachher)
u1 = f.db.auftrag(a1)
assert (u1["kunde"], u1["material"], u1["kalk_min"]) == ("Umzug GmbH", "RR 40x2", 90)
assert f.db.auftrag(nummer="U-2")["bemerkung"] == "Text; mit Semikolon"
assert "Säge" in [x["name"] for x in f.db.maschinen()] and f.db.einstellung("wochen") == "6"
f.reiter.setCurrentIndex(0)
f.reiter.setCurrentIndex(EINSTELLUNGEN)
app.processEvents()
assert "PostgreSQL auf diesem PC" in f.e_pfad.text() and "Rückfall" in f.e_pfad.text()
assert "umgestellt" in erg["bericht"].read_text(encoding="utf-8")
ok(f"Umgestellt: Sicherung geprüft, {sum(vorher.values())} Zeilen übernommen und verglichen, Merkdatei mit PC-Namen, "
   "Rückfall-Datei unverändert")

# Arbeiten mit PostgreSQL: neuer Auftrag, doppelte Nummer, zweiter Platz am selben PC, Takt, Sicherung
a4 = f.db.auftrag_speichern(dict(nummer="U-4", maschine="LT7", kalk_min=60))
try:
    f.db.auftrag_speichern(dict(nummer=" u-4 ", maschine="LT7", kalk_min=5))
    raise AssertionError("doppelte Nummer")
except daten.Fehler as e:
    assert "gibt es schon" in str(e)
try:
    f.db.con.execute("INSERT INTO auftraege (nummer, maschine, kalk_min) VALUES ('U-4 ', 'LT7', 5)")
    raise AssertionError("doppelte Nummer an der Prüfung vorbei")
except sqlite3.IntegrityError as e:
    assert "Auftragsnummer doppelt" in str(e), e
f.db.starten(a4, datetime.datetime(2026, 11, 16, 7, 0))
f.db.stoppen(a4, datetime.datetime(2026, 11, 16, 8, 0), grund="Pause")
assert f.db.auftrag(a4)["gelaufen_min"] == 60
f.reiter.setCurrentIndex(0)
f.laden()
zeilen = f.liste.rowCount()
platz2 = daten.Daten(pfad, wer="halle")
assert platz2.postgres
platz2.auftrag_speichern(dict(nummer="U-5", maschine="T03", kalk_min=20))
platz2.schliessen()
f.takt()
assert f.liste.rowCount() == zeilen + 1, "Takt sieht den anderen Platz"
gesichert = f.jetzt_sichern()
c = sqlite3.connect(gesichert)
assert c.execute("SELECT COUNT(*) FROM auftraege").fetchone()[0] == 5 and c.execute(
    "PRAGMA integrity_check").fetchone()[0] == "ok"
c.close()
probe = daten.Daten(gesichert)                    # die Sicherung ist eine normale Auslastung.db
assert not probe.postgres and probe.auftrag(nummer="U-5")
probe.schliessen()
ok("Mit PostgreSQL: Aufträge, doppelte Nummer abgelehnt, Start/Stopp, zweiter Platz am selben PC mit Takt, "
   "Sicherung als SQLite-Datei")

# anderer PC öffnet die Merkdatei (z. B. über eine Freigabe): klare Meldung, kein zweiter Server
alt_rechner = speicher.rechner
speicher.rechner = lambda: "anderer-pc"
try:
    daten.Daten(pfad)
    raise AssertionError("anderer PC hat geöffnet")
except daten.Fehler as e:
    assert "nur dort" in str(e) and m["rechner"] in str(e).lower()
speicher.rechner = alt_rechner
# gemeinsamer Ordner: „Datenbank an anderem Ort“ legt dort eine SQLite-Datei an
gemeinsam = tmp / "gemeinsam" / "Auslastung.db"
neu_ort = daten.Daten(pfad)
kopie_ziel = tmp / "kopie" / "Auslastung.db"
kopie_ziel.parent.mkdir()
speicher.sichern_pg(neu_ort.con, kopie_ziel)
neu_ort.schliessen()
k = daten.Daten(kopie_ziel)
assert not k.postgres and len(k.auftraege()) == len(f.db.auftraege()) and k.auftrag(nummer="U-5")
k.schliessen()
ok("Anderer PC bekommt eine klare Meldung; Kopie für den gemeinsamen Ordner ist eine SQLite-Datei")

# Zurückstellen: alles (auch Neues) wieder in der SQLite-Datei
erg2 = f.datenspeicher_wechseln(fragen=lambda _t: True, hauptadmin=True)
assert erg2 and not f.db.postgres and speicher.art(pfad) == speicher.SQLITE
assert erg2["auftraege"] == 5 and f.db.auftrag(nummer="U-5") and f.db.auftrag(a4)["gelaufen_min"] == 60
assert db_verbindung.schema_version(f.db.con) == daten.SCHEMA
assert f.db.stopps()[0]["grund"] == "Pause"
assert list(pfad.parent.glob("Auslastung_PostgreSQL_bis_*.merk"))
f.db.auftrag_speichern(dict(nummer="U-6", maschine="LT7", kalk_min=10))
ok("Zurückgestellt: alle Aufträge (auch die neuen) in der SQLite-Datei, Stand des Aufbaus wie vorher")

# Fehlerfall: im PostgreSQL-Ordner liegen schon Daten → nichts geändert
inhalt = pfad.read_bytes()
erg3 = f.datenspeicher_wechseln(fragen=lambda _t: True, hauptadmin=True)
assert erg3 is None and not f.db.postgres and speicher.art(pfad) == speicher.SQLITE
assert pfad.read_bytes() == inhalt and f.db.auftrag(nummer="U-6")
assert "schon Daten" in f.statusBar().currentMessage()
ok("Schon Daten im PostgreSQL-Ordner: es wird nicht umgestellt, die Datei bleibt unverändert")
f.close()
f.db.schliessen()
datenspeicher.alle_stoppen()
print("Alles in Ordnung.")
