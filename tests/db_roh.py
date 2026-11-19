"""Testhilfe: direkt in die Datenbank einer Datendatei schreiben, wie früher mit sqlite3.connect(pfad).

Seit PostgreSQL die einzige Datenbank ist (SQLite entfernen, Patrick 19.11.2026), liegt hinter dem Pfad einer
Datendatei keine SQLite-Datei mehr, sondern eine PostgreSQL-Datenbank (im Prüflauf eine je Pfad auf dem Prüfserver,
sonst der Server im Datenordner). Tests, die alte Stände nachbauen (Tabelle löschen, Spalte entfernen, Schema-Version
zurücksetzen) oder Werte an der Programmlogik vorbei ändern, nehmen diese Hilfen:

- verbinden(pfad): Verbindung mit execute/executemany/commit/close (Parameter mit ?), für SQLite-Dateien (Sicherung,
  Austauschdatei, Archiv) weiter sqlite3;
- kopieren(quelle, ziel): Datendatei samt Datenbank kopieren (früher shutil.copy);
- tabellen/spalten/schema_version/schema_version_setzen: wie db_verbindung, für beide Arten.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import datenspeicher, db_verbindung  # noqa: E402

tabellen = db_verbindung.tabellen
spalten = db_verbindung.spalten
schema_version = db_verbindung.schema_version
schema_version_setzen = db_verbindung.schema_version_setzen


def ist_pg(pfad):
    return not ist_sqlite_datei(pfad)


ist_sqlite_datei = datenspeicher.ist_sqlite_datei


def sqlite_datenbank(pfad):
    """Neue SQLite-Datendatei wie vor dem Update auf PostgreSQL (aktuelles Schema, Beispieldaten) als offene
    Datenbank. Tests bauen daraus mit sqlite3 alte Stände; Datenbank(pfad) übernimmt sie danach wie beim Update."""
    from rohrlaser.datenbank import Datenbank
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    return Datenbank(pfad, verbindung=db_verbindung.SqliteVerbindung(pfad, fremdschluessel=False))


def _sqlite(con):
    return isinstance(con, sqlite3.Connection) or getattr(con, "art", "sqlite") == "sqlite"


def indizes(con, tabelle=None):
    """Namen der Indizes (einer Tabelle) – SQLite oder PostgreSQL."""
    if _sqlite(con):
        sql, werte = "SELECT name FROM sqlite_master WHERE type='index'", ()
        if tabelle:
            sql, werte = sql + " AND tbl_name=?", (tabelle,)
        return {r[0] for r in con.execute(sql, werte)}
    sql, werte = "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()", ()
    if tabelle:
        sql, werte = sql + " AND tablename = ?", (tabelle,)
    return {r[0] for r in con.execute(sql, werte)}


def plan(con, sql, werte=()):
    """Abfrageplan als Text: genutzte Indizes erscheinen mit Namen, ein Durchsuchen der ganzen Tabelle als SCAN.
    PostgreSQL nimmt bei kleinen Tabellen sonst immer den Seq Scan, deshalb hier enable_seqscan=off."""
    if _sqlite(con):
        return " ".join(str(r[-1]) for r in con.execute("EXPLAIN QUERY PLAN " + sql, werte))
    con.execute("SET enable_seqscan = off")
    try:
        text = " ".join(str(r[0]) for r in con.execute("EXPLAIN " + sql, werte))
    finally:
        con.execute("RESET enable_seqscan")
    return text.replace("Seq Scan", "SCAN")


def typ(con, ausdruck, tabelle, wo, werte=()):
    """Speicherart eines Werts wie SQLite typeof(): blob, text, integer, real, null."""
    if _sqlite(con):
        return con.execute(f"SELECT typeof({ausdruck}) FROM {tabelle} WHERE {wo}", werte).fetchone()[0]
    t, leer = con.execute(f"SELECT pg_typeof({ausdruck})::text, {ausdruck} IS NULL FROM {tabelle} WHERE {wo}",
                          werte).fetchone()
    return "null" if leer else {"bytea": "blob", "bigint": "integer", "integer": "integer",
                                "double precision": "real"}.get(t, "text")


def als_sqlite(db, ziel):
    """Inhalt der offenen Datenbank db als SQLite-Datendatei `ziel` (wie eine Datei vor dem Update). Öffnet ein Test
    sie danach mit Datenbank(ziel), wird sie wie beim Update nach PostgreSQL übernommen."""
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.unlink(missing_ok=True)
    z = sqlite3.connect(ziel)
    try:
        db.con.commit()
        db.con.backup(z)
    finally:
        z.close()
    return ziel


def verbinden(pfad):
    """Verbindung zur Datenbank hinter `pfad` (KompatVerbindung) oder zur SQLite-Datei (sqlite3.Connection)."""
    pfad = Path(pfad)
    if ist_sqlite_datei(pfad):              # Sicherung, Austauschdatei, Archiv: bleiben SQLite-Dateien
        return sqlite3.connect(pfad)
    if db_verbindung.pg_test_an():
        return db_verbindung.KompatVerbindung(db_verbindung.pg_test_oeffnen(pfad)[0])
    if datenspeicher.art(pfad) == datenspeicher.POSTGRES:
        return db_verbindung.KompatVerbindung(datenspeicher.oeffnen(pfad))
    return sqlite3.connect(pfad)


def kopieren(quelle, ziel):
    """Datendatei kopieren (Prüflauf: die Datenbank des Ziels wird eine Kopie der Datenbank der Quelle). Die Quelle
    sollte geschlossen sein; offene Verbindungen zu ihr werden sonst beendet."""
    quelle, ziel = Path(quelle), Path(ziel)
    if ist_sqlite_datei(quelle) or not db_verbindung.pg_test_an():
        if datenspeicher.art(quelle) == datenspeicher.POSTGRES:
            raise RuntimeError("Kopieren einer PostgreSQL-Datendatei nur im Prüflauf")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        return shutil.copy(quelle, ziel)
    z, passwort = db_verbindung.pg_test_zugang()
    a, b = db_verbindung.pg_test_name(quelle), db_verbindung.pg_test_name(ziel)
    v = db_verbindung.PostgresVerbindung(z, passwort)
    try:
        v._roh(f'DROP DATABASE IF EXISTS "{b}" WITH (FORCE)')
        v._roh(f'CREATE DATABASE "{b}"')
    finally:
        v.schliessen()
    # pg_dump statt CREATE DATABASE … TEMPLATE: die Quelle darf dabei offen sein (wie eine Datei beim Kopieren)
    import os
    import subprocess
    from rohrlaser import pg_lokal
    bin_ = pg_lokal.programme()
    umg = dict(os.environ, PGPASSWORD=passwort or "")
    ort = ["-h", str(z.get("host", "127.0.0.1")), "-p", str(z["port"]), "-U", z.get("benutzer", "rohrlaser")]
    dump = subprocess.run([str(bin_ / "pg_dump"), *ort, "-d", a, "-Fc"], env=umg, capture_output=True, check=True)
    subprocess.run([str(bin_ / "pg_restore"), *ort, "-d", b, "--no-owner"], input=dump.stdout, env=umg,
                   capture_output=True, check=True)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    if quelle.exists():
        shutil.copy(quelle, ziel)
    else:
        ziel.write_bytes(b"")
    return ziel
