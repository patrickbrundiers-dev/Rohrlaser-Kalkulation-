"""Datenbank ohne SQLite-Sonderbefehle (Plan Datenbank-Modernisierung, Phase 3b Teil 1).

Überschreiben läuft über INSERT … ON CONFLICT … DO UPDATE statt INSERT OR REPLACE. Prüft: Netz und Einstellung
zweimal speichern (Merker-Trigger dürfen dabei nicht an „schon gemerkt“ scheitern, auch nicht mit den alten Triggern
einer früheren Datei), geteilte Einstellungen stehen weiter im Änderungsprotokoll, Lesemodus sperrt weiter.

Aufruf: python tests/test_db_neutral.py
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import beispiel_angebot  # noqa: E402

from rohrlaser import db_verbindung, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
pfad = tmp / "rohrlaser.db"
db = Datenbank(pfad)
a = beispiel_angebot.anlegen(db)
pos = db.con.execute("SELECT id FROM positionen WHERE angebot_id=? ORDER BY id", (a,)).fetchone()[0]
db.schliessen()

# Datei wie vor dieser Version: Merker-Trigger mit INSERT OR IGNORE
con = sqlite3.connect(pfad)
for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'netze_%_teilen'"):
    con.execute(f'DROP TRIGGER "{name}"')
for art, zeile in (("INSERT", "NEW"), ("UPDATE", "NEW"), ("DELETE", "OLD")):
    con.execute(f"CREATE TRIGGER netze_{art.lower()}_teilen AFTER {art} ON netze BEGIN INSERT OR IGNORE INTO "
                f"teilen_geaendert (angebot_id) SELECT angebot_id FROM positionen WHERE id={zeile}.position_id; END")
con.commit()
con.close()

db = Datenbank(pfad)
db.con.execute("DELETE FROM teilen_geaendert")
db.con.commit()
for daten in (b"eins", b"zwei", b"drei"):
    db.netz_speichern(pos, daten)
assert db.netz(pos) == b"drei"
assert [r[0] for r in db.con.execute("SELECT angebot_id FROM teilen_geaendert")] == [a]
print("OK     Netz dreimal speichern: überschrieben, Angebot einmal als geändert gemerkt (auch mit alter Datei)")

name = sorted(teilen.EINSTELLUNGEN_GETEILT)[0]
vorher = teilen.protokoll_stand(db.con)
for wert in ("1", "2"):
    db.con.execute(db_verbindung.EINSTELLUNG_SETZEN, (name, wert))
    db.con.commit()
assert db.con.execute("SELECT wert FROM einstellungen WHERE name=?", (name,)).fetchone()[0] == "2"
neu = [e for e in teilen.protokoll(db.con, vorher) if e["uid"] == name]
assert len(neu) == 2 and all(e["art"] == "neu" for e in neu), neu
print("OK     geteilte Einstellung überschreiben: steht wie bisher als „neu“ im Änderungsprotokoll")

assert "angebote" in db_verbindung.tabellen(db.con) and "uid" in db_verbindung.spalten(db.con, "angebote")
assert db_verbindung.schema_version(db.con) > 0
stand = db.stammdaten_stand()
fremd = sqlite3.connect(pfad)
fremd.execute("UPDATE einstellungen SET wert=wert WHERE name=?", (name,))
fremd.commit()
fremd.close()
assert db.stammdaten_stand() != stand
print("OK     Tabellen, Spalten, Schema-Version, Änderung durch ein anderes Programm erkannt")

db.lesemodus("Test")
try:
    db.con.execute(db_verbindung.EINSTELLUNG_SETZEN, (name, "3"))
    raise AssertionError("Lesemodus nimmt Änderung an")
except sqlite3.OperationalError:
    db.con.rollback()
db.lesemodus("")
db.con.execute(db_verbindung.EINSTELLUNG_SETZEN, (name, "3"))
db.con.commit()
print("OK     Lesemodus sperrt weiter, danach wieder frei")
db.schliessen()
print("Datenbank ohne SQLite-Sonderbefehle: alles in Ordnung")
