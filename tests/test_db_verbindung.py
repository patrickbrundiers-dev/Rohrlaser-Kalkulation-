"""Verbindungsschicht SQLite/PostgreSQL (Plan Datenbank-Modernisierung 12.11.2026, Phase 3a).

Prüft dieselben Abläufe auf beiden Datenbanken: Übersetzung des SQL, Zeilen wie sqlite3.Row, neue IDs, Transaktion
alles-oder-nichts (auch verschachtelt), doppelte Schlüssel, ersetzen(), optimistische Sperre mit version (zwei
Arbeitsplätze ändern dieselbe Zeile), Lesemodus, Spalten/Tabellen/Schemaversion, Pool, paralleles Speichern aus
mehreren Threads ohne verlorene Werte. PostgreSQL läuft als eingebetteter Server (pg_lokal) in einem Testordner;
ohne PostgreSQL-Programme oder als root (initdb verweigert das) wird nur SQLite geprüft und das gemeldet.

Aufruf: python tests/test_db_verbindung.py
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import db_verbindung as dv  # noqa: E402
from rohrlaser import pg_lokal  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    if not bedingung:
        fehler.append(text)
        print("FEHLER:", text)


# ------------------------------------------------------------------ Übersetzung (ohne Datenbank)
P = dv.nach_postgres
pruefe(P("SELECT * FROM a WHERE x=? AND y=?") == "SELECT * FROM a WHERE x=%s AND y=%s", "Platzhalter")
pruefe(P("SELECT '?', \"a?\" FROM t WHERE z=?") == "SELECT '?', \"a?\" FROM t WHERE z=%s", "? in Texten bleibt")
pruefe(P("SELECT * FROM t WHERE n LIKE ?") == "SELECT * FROM t WHERE n LIKE %s", "LIKE")
pruefe(P("SELECT * FROM t WHERE n LIKE '%x%'") == "SELECT * FROM t WHERE n LIKE '%x%'", "% in Text bleibt")
pruefe(P("SELECT 5 % 3") == "SELECT 5 %% 3", "% als Operator wird %%")
pruefe(P("INSERT OR IGNORE INTO t (a) VALUES (?)") == "INSERT INTO t (a) VALUES (%s) ON CONFLICT DO NOTHING",
       "INSERT OR IGNORE")
pruefe(P("insert or ignore into t (a) values (?) returning id")
       == "INSERT INTO t (a) values (%s) ON CONFLICT DO NOTHING returning id", "INSERT OR IGNORE mit RETURNING")
pruefe(P("SELECT 1 FROM t WHERE a IS NOT ?") == "SELECT 1 FROM t WHERE a IS DISTINCT FROM %s", "IS NOT ?")
pruefe(P("SELECT 1 FROM t WHERE a IS ?") == "SELECT 1 FROM t WHERE a IS NOT DISTINCT FROM %s", "IS ?")
pruefe(P("SELECT 1 -- Kommentar mit ?\nFROM t") == "SELECT 1 -- Kommentar mit ?\nFROM t", "Kommentar bleibt")
pruefe(P("SELECT 'it''s ?' FROM t") == "SELECT 'it''s ?' FROM t", "verdoppeltes Hochkomma")
for falsch in ("PRAGMA table_info(t)", "INSERT OR REPLACE INTO t VALUES (1)", "REPLACE INTO t VALUES (1)",
               "SELECT name FROM sqlite_master"):
    try:
        P(falsch)
        pruefe(False, f"nicht übersetzbar erkannt: {falsch}")
    except dv.NichtUebersetzbar:
        pass
pruefe(P("SELECT 'sqlite_master' FROM t") == "SELECT 'sqlite_master' FROM t", "sqlite_master nur als Text erlaubt")
for name in ("a;b", "x y", "", '"t"'):
    try:
        dv._name(name)
        pruefe(False, f"ungültiger Name angenommen: {name!r}")
    except ValueError:
        pass


# ------------------------------------------------------------------ gleiche Abläufe auf beiden Datenbanken
TABELLE = ("CREATE TABLE angebote (id INTEGER PRIMARY KEY{auto}, nummer TEXT UNIQUE NOT NULL, kunde TEXT, "
           "betrag REAL, version INTEGER NOT NULL DEFAULT 1)")


def ablauf(name, fabrik, auto):
    print(f"--- {name}")
    v = fabrik()
    v.execute(TABELLE.format(auto=auto))
    v.execute("CREATE TABLE zaehler (id INTEGER PRIMARY KEY, n INTEGER NOT NULL)")
    v.execute("INSERT INTO zaehler (id, n) VALUES (1, 0)")

    i1 = v.einfuegen("INSERT INTO angebote (nummer, kunde, betrag) VALUES (?, ?, ?)", ("2026-00001", "Müller", 12.5))
    i2 = v.einfuegen("INSERT INTO angebote (nummer, kunde, betrag) VALUES (?, ?, ?)", ("2026-00002", "Meier", 7.0))
    pruefe(i1 and i2 and i2 > i1, f"{name}: neue IDs {i1}, {i2}")
    z = v.execute("SELECT id, nummer, kunde FROM angebote WHERE id=?", (i1,)).fetchone()
    pruefe(z["kunde"] == "Müller" and z[1] == "2026-00001" and dict(z)["id"] == i1, f"{name}: Zeile wie sqlite3.Row")
    pruefe(len(v.execute("SELECT * FROM angebote WHERE kunde LIKE ?", ("%ll%",)).fetchall()) == 1, f"{name}: LIKE")
    pruefe(v.execute("SELECT COUNT(*) FROM angebote WHERE kunde IS NOT ?", (None,)).fetchone()[0] == 2,
           f"{name}: IS NOT ?")

    try:
        v.execute("INSERT INTO angebote (nummer) VALUES (?)", ("2026-00001",))
        pruefe(False, f"{name}: doppelte Nummer angenommen")
    except dv.Doppelt:
        pass
    v.execute("INSERT OR IGNORE INTO angebote (nummer) VALUES (?)", ("2026-00001",))
    pruefe(v.execute("SELECT COUNT(*) FROM angebote").fetchone()[0] == 2, f"{name}: INSERT OR IGNORE")

    # Transaktion: alles oder nichts, verschachtelt
    try:
        with v.transaktion():
            v.execute("UPDATE angebote SET betrag=99 WHERE id=?", (i1,))
            raise RuntimeError("Abbruch mitten in der Transaktion")
    except RuntimeError:
        pass
    pruefe(v.execute("SELECT betrag FROM angebote WHERE id=?", (i1,)).fetchone()[0] == 12.5, f"{name}: Rollback")
    with v.transaktion():
        v.execute("UPDATE angebote SET betrag=20 WHERE id=?", (i1,))
        try:
            with v.transaktion():
                v.execute("UPDATE angebote SET betrag=30 WHERE id=?", (i2,))
                raise RuntimeError("innen")
        except RuntimeError:
            pass
    pruefe(v.execute("SELECT betrag FROM angebote WHERE id=?", (i1,)).fetchone()[0] == 20, f"{name}: außen bestätigt")
    pruefe(v.execute("SELECT betrag FROM angebote WHERE id=?", (i2,)).fetchone()[0] == 7, f"{name}: innen verworfen")
    pruefe(not v.in_transaktion, f"{name}: Transaktion geschlossen")

    v.ersetzen("zaehler", {"id": 1, "n": 5}, ["id"])
    v.ersetzen("zaehler", {"id": 2, "n": 1}, ["id"])
    pruefe([tuple(r) for r in v.execute("SELECT id, n FROM zaehler ORDER BY id")] == [(1, 5), (2, 1)], f"{name}: ersetzen")

    # zwei Arbeitsplätze ändern dieselbe Zeile: der zweite bekommt Konflikt statt still zu überschreiben
    w = fabrik()
    ver_a = v.execute("SELECT version FROM angebote WHERE id=?", (i1,)).fetchone()[0]
    ver_b = w.execute("SELECT version FROM angebote WHERE id=?", (i1,)).fetchone()[0]
    neu = v.aendern_mit_version("angebote", i1, {"kunde": "Müller GmbH"}, ver_a)
    try:
        w.aendern_mit_version("angebote", i1, {"kunde": "Müller KG"}, ver_b)
        pruefe(False, f"{name}: Konflikt nicht erkannt")
    except dv.Konflikt:
        pass
    pruefe(neu == ver_a + 1 and w.execute("SELECT kunde FROM angebote WHERE id=?", (i1,)).fetchone()[0] == "Müller GmbH",
           f"{name}: erste Änderung bleibt")

    # Aufbau
    pruefe({"angebote", "zaehler"} <= set(v.tabellen()), f"{name}: tabellen() {v.tabellen()}")
    pruefe(v.spalten("angebote") == ["id", "nummer", "kunde", "betrag", "version"], f"{name}: spalten()")
    v.schema_version_setzen(83)
    pruefe(v.schema_version() == 83, f"{name}: Schemaversion")

    # Lesemodus: von der Datenbank selbst gesperrt, auch für direktes SQL
    v.nur_lesen(True)
    for versuch in (lambda: v.execute("UPDATE angebote SET betrag=1"), lambda: v.transaktion().__enter__()):
        try:
            versuch()
            pruefe(False, f"{name}: Lesemodus lässt Ändern zu")
        except dv.NurLesen:
            pass
    pruefe(v.execute("SELECT COUNT(*) FROM angebote").fetchone()[0] == 2, f"{name}: Lesen im Lesemodus")
    v.nur_lesen(False)
    v.execute("UPDATE angebote SET betrag=betrag WHERE id=?", (i1,))

    # paralleles Speichern: 8 Threads × 40 Erhöhungen in Transaktionen, kein Wert darf verloren gehen
    pool = dv.VerbindungsPool(fabrik, groesse=4)
    v.execute("UPDATE zaehler SET n=0 WHERE id=1")

    def arbeiten():
        for _ in range(40):
            for _versuch in range(50):
                try:
                    with pool.holen() as c, c.transaktion():
                        n = c.execute("SELECT n FROM zaehler WHERE id=1 FOR UPDATE" if c.art == "postgres"
                                      else "SELECT n FROM zaehler WHERE id=1").fetchone()[0]
                        c.execute("UPDATE zaehler SET n=? WHERE id=1", (n + 1,))
                    break
                except (dv.Konflikt, dv.VerbindungWeg):
                    continue

    threads = [threading.Thread(target=arbeiten) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    n = v.execute("SELECT n FROM zaehler WHERE id=1").fetchone()[0]
    pruefe(n == 320, f"{name}: paralleles Speichern {n} statt 320")
    pruefe(pool.offen <= 4, f"{name}: Pool hält höchstens 4 Verbindungen ({pool.offen})")
    pool.schliessen()
    w.schliessen()
    v.schliessen()


tmp = Path(tempfile.mkdtemp())
ablauf("SQLite", lambda: dv.oeffnen({"art": "sqlite", "pfad": tmp / "test.sqlite"}), "")

# Lese-Verbindung auf eine Datei (Migration liest die Quelle nur so)
lesen = dv.SqliteVerbindung(tmp / "test.sqlite", nur_lesen=True)
try:
    lesen.execute("DELETE FROM angebote")
    pruefe(False, "SQLite nur lesend geöffnet, trotzdem gelöscht")
except dv.NurLesen:
    pass
lesen.schliessen()

try:
    bin_ordner = pg_lokal.programme()
    import psycopg  # noqa: F401
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise pg_lokal.PgFehlt("als root (initdb verweigert root)")
except (pg_lokal.PgFehlt, ImportError) as e:
    print(f"PostgreSQL-Teil übersprungen: {e}")
else:
    server = pg_lokal.LokalerServer(tmp / "Daten", bin_ordner)
    server.starten()
    try:
        pruefe(server.laeuft(), "eingebetteter Server läuft")
        zugang = server.zugang()
        ablauf("PostgreSQL", lambda: dv.oeffnen(zugang, passwort=server.passwort), " GENERATED BY DEFAULT AS IDENTITY")
        # falsches Passwort: verständliche Meldung statt Absturz
        try:
            dv.oeffnen(zugang, passwort="falsch")
            pruefe(False, "falsches Passwort angenommen")
        except dv.VerbindungWeg as e:
            pruefe("Datenbank" in str(e), "Meldung bei falschem Passwort")
        # Verbindung bricht ab: Lesen verbindet neu, Schreiben in einer Transaktion meldet VerbindungWeg
        v = dv.oeffnen(zugang, passwort=server.passwort)
        v.execute("CREATE TABLE abbruch (id INTEGER PRIMARY KEY, n INTEGER)")
        v.execute("INSERT INTO abbruch VALUES (1, 1)")
        w = dv.oeffnen(zugang, passwort=server.passwort)
        pid = v.execute("SELECT pg_backend_pid()").fetchone()[0]
        w.execute("SELECT pg_terminate_backend(?)", (pid,))
        pruefe(v.execute("SELECT n FROM abbruch WHERE id=1").fetchone()[0] == 1, "Lesen nach Verbindungsabbruch")
        pid = v.execute("SELECT pg_backend_pid()").fetchone()[0]
        try:
            with v.transaktion():
                v.execute("UPDATE abbruch SET n=2 WHERE id=1")
                w.execute("SELECT pg_terminate_backend(?)", (pid,))
                v.execute("UPDATE abbruch SET n=3 WHERE id=1")
            pruefe(False, "Abbruch in der Transaktion nicht gemeldet")
        except dv.VerbindungWeg:
            pass
        pruefe(w.execute("SELECT n FROM abbruch WHERE id=1").fetchone()[0] == 1, "abgebrochene Transaktion verworfen")
        pruefe(v.execute("SELECT n FROM abbruch WHERE id=1").fetchone()[0] == 1, "danach wieder verbunden")
        v.schliessen()
        w.schliessen()
        # Neustart behält die Daten (Einzelplatz: Programm beenden und wieder starten)
        server.stoppen()
        pruefe(not server.laeuft(), "Server gestoppt")
        server.starten()
        v = dv.oeffnen(server.zugang(), passwort=server.passwort)
        pruefe(v.execute("SELECT COUNT(*) FROM angebote").fetchone()[0] == 2, "Daten nach Neustart")
        v.schliessen()
    finally:
        server.stoppen()

if fehler:
    print(f"{len(fehler)} Fehler")
    sys.exit(1)
print("Verbindungsschicht: alles in Ordnung")
