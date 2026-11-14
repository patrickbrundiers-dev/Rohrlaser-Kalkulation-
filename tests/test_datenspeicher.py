"""Datenspeicher je PC (Plan Datenbank-Modernisierung, Phase 3c): SQLite-Datendatei → eingebettetes PostgreSQL und
zurück.

Prüft: geprüfte Sicherung vor dem Umstellen, alle Zeilen übernommen und verglichen, Merkdatei am alten Ort,
Rückfall-Datei unverändert, Datenbank(pfad) öffnet danach PostgreSQL, Änderungen landen dort, Sicherung bleibt eine
SQLite-Datei, Zurückstellen schreibt alles (auch Neues) in eine SQLite-Datendatei, Fehlerfall (schon Daten im
PostgreSQL-Ordner) ändert nichts, nur der Hauptadmin darf umstellen (Menü Datei). Ohne PostgreSQL-Programme oder als
root (initdb verweigert root) wird nur die Erkennung der Merkdatei geprüft.

Aufruf: python tests/test_datenspeicher.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

import beispiel_angebot  # noqa: E402
from rohrlaser import datenspeicher, db_verbindung, pg_lokal  # noqa: E402
from rohrlaser.datenbank import Datenbank, datei_pruefen  # noqa: E402


def ok(text):
    print("OK     " + text)


tmp = Path(tempfile.mkdtemp())
pfad = tmp / "Daten" / "rohrlaser.db"
db = Datenbank(pfad)
a = beispiel_angebot.anlegen(db, dict(nummer="2026-00001", kunde="Umzug GmbH"))
db.con.commit()
assert datenspeicher.art(pfad) == datenspeicher.SQLITE and datenspeicher.merkdatei_lesen(pfad) is None
assert datenspeicher.art(tmp / "gibt_es_nicht.db") == datenspeicher.SQLITE
ok("Normale Datendatei und fehlende Datei gelten als SQLite")

try:
    bin_ordner = pg_lokal.programme()
    import psycopg  # noqa: F401
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise pg_lokal.PgFehlt("als root (initdb verweigert root)")
except (pg_lokal.PgFehlt, ImportError) as e:
    print(f"PostgreSQL-Teil übersprungen: {e}")
    db.schliessen()
    sys.exit(0)

vorher = {t: db.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("angebote", "positionen", "preise")}
inhalt_vorher = pfad.read_bytes()
erg = datenspeicher.umstellen(db, bin_ordner)
assert datei_pruefen(erg["sicherung"])["anzahl"]["angebote"] == vorher["angebote"]
assert "vor_PostgreSQL" in Path(erg["sicherung"]).name
assert erg["rueckfall"].read_bytes() == inhalt_vorher, "Rückfall-Datei = Datendatei vor dem Umstellen"
assert datenspeicher.art(pfad) == datenspeicher.POSTGRES and pfad.stat().st_size < 64 * 1024
assert erg["angebote"] == vorher["angebote"] and erg["tabellen"] > 30
assert (tmp / "Daten" / "pg" / "PG_VERSION").is_file()
ok(f"Umgestellt: geprüfte Sicherung, {erg['tabellen']} Tabellen verglichen, Rückfall-Datei unverändert, Merkdatei")

db = Datenbank(pfad)
assert not db_verbindung.ist_sqlite(db.con)
assert {t: db.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in vorher} == vorher
assert db.angebot(a)["kunde"] == "Umzug GmbH"
db.angebot_aendern(a, "kunde", "Neu in PostgreSQL")
b = beispiel_angebot.anlegen(db, dict(nummer="2026-00002", kunde="Zweiter"))
db.con.commit()
s = db.sicherung(zusatz="test")
assert datei_pruefen(s)["anzahl"]["angebote"] == vorher["angebote"] + 1, "Sicherung ist eine SQLite-Datendatei"
assert "PostgreSQL auf diesem PC" in datenspeicher.status(db)
ok("Datenbank(pfad) öffnet PostgreSQL, Änderungen und Sicherung gehen")

# zweites Umstellen geht nicht, Fehler ändert nichts
try:
    datenspeicher.umstellen(db)
    raise AssertionError("doppelt umgestellt")
except datenspeicher.UmstellFehler:
    pass
ok("Schon PostgreSQL: Umstellen abgewiesen")

erg2 = datenspeicher.zurueck(db)
assert datenspeicher.art(pfad) == datenspeicher.SQLITE
con = sqlite3.connect(pfad)
assert con.execute("SELECT kunde FROM angebote WHERE id=?", (a,)).fetchone()[0] == "Neu in PostgreSQL"
assert con.execute("SELECT COUNT(*) FROM angebote").fetchone()[0] == vorher["angebote"] + 1 == erg2["angebote"]
con.close()
assert "vor_SQLite" in Path(erg2["sicherung"]).name
assert list(pfad.parent.glob("rohrlaser_PostgreSQL_bis_*.merk"))
db = Datenbank(pfad)
assert db_verbindung.ist_sqlite(db.con) and db.angebot(b)["kunde"] == "Zweiter"
ok("Zurück auf SQLite: alles (auch Neues) in der Datendatei, Sicherung vorher, Merkdatei aufgehoben")

# PostgreSQL-Ordner hat schon Daten: nicht umstellen, Datendatei bleibt
anzahl = db.con.execute("SELECT COUNT(*) FROM angebote").fetchone()[0]
try:
    datenspeicher.umstellen(db, bin_ordner)
    raise AssertionError("über vorhandene Daten umgestellt")
except datenspeicher.UmstellFehler as e:
    assert "schon Daten" in str(e), e
db = Datenbank(pfad)
assert db_verbindung.ist_sqlite(db.con) and datenspeicher.art(pfad) == datenspeicher.SQLITE
assert db.con.execute("SELECT COUNT(*) FROM angebote").fetchone()[0] == anzahl
ok("PostgreSQL-Ordner mit Daten: abgewiesen, Datendatei unverändert")

# Menü Datei: nur Hauptadmin
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import admin_schutz  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, tmp, stumm=True)
assert "Datenspeicher (SQLite / PostgreSQL) …" in fenster.datei_aktionen
alt = admin_schutz.ist_haupt
admin_schutz.ist_haupt = lambda *_a, **_k: False
assert fenster.datenspeicher_wechseln(bestaetigt=True) is None and db_verbindung.ist_sqlite(db.con)
admin_schutz.ist_haupt = lambda *_a, **_k: True       # als Hauptadmin freigeschaltet
# Ordner mit Daten weg, dann über das Menü umstellen: dasselbe db-Objekt arbeitet danach mit PostgreSQL
datenspeicher.alle_stoppen()
(tmp / "Daten" / "pg").rename(tmp / "Daten" / "pg_alt")
(tmp / "Daten" / pg_lokal.ZUGANG).unlink()
os.environ["ROHRLASER_PG_BIN"] = str(bin_ordner)
erg3 = fenster.datenspeicher_wechseln(bestaetigt=True)
assert erg3 and not db_verbindung.ist_sqlite(db.con) and fenster.db is db
assert db.angebot(b)["kunde"] == "Zweiter"
assert fenster.datenspeicher_wechseln(bestaetigt=True) and db_verbindung.ist_sqlite(db.con)
admin_schutz.ist_haupt = alt
ok("Menü Datei → Datenspeicher: nur Hauptadmin, Wechsel hin und zurück ohne Neustart")
fenster.close()
db.schliessen()
datenspeicher.alle_stoppen()
print("Alles in Ordnung.")
