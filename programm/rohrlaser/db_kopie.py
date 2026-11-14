"""Daten zwischen SQLite-Datei und PostgreSQL kopieren (Plan Datenbank-Modernisierung, Phase 3b Teil 2 / Phase 5).

pg_nach_sqlite: der ganze Inhalt der PostgreSQL-Datenbank in eine SQLite-Datei – Sicherung, Export und der Weg
zurück (Rückfall auf SQLite). Die Datei hat dieselben Tabellen, Spalten, Primärschlüssel und die Schema-Version;
Indizes, Trigger und eindeutige Schlüssel legt das Programm beim Öffnen wie bei jeder älteren Datei selbst an.

sqlite_nach_pg: Inhalt einer SQLite-Datei (Sicherung, Datendatei, Export) in die geöffnete PostgreSQL-Datenbank –
Wiederherstellen und später die Umstellung. Alle Tabellen, die es in beiden gibt, werden ersetzt (gemeinsame
Spalten), in einer Transaktion; Trigger und Fremdschlüssel ruhen dabei wie beim Kopieren einer SQLite-Datei.
Leere Texte in Zahlenspalten werden NULL (PostgreSQL kennt dort kein ''), Zähler der Kennungen werden nachgezogen.
"""
from . import db_verbindung

EIGENE = {"stammdaten_stand", "angebot_aenderungen", "schema_stand"}     # Zähler der Verbindung, keine Daten
_ZAHL = {"bigint", "integer", "smallint", "double precision", "real", "numeric"}


def _pg_schluessel(v):
    """{Tabelle: [Spalten des Primärschlüssels]} der PostgreSQL-Datenbank."""
    out = {}
    for t, s in v.execute(
            "SELECT tc.table_name, kcu.column_name FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name "
            "AND kcu.table_schema = tc.table_schema WHERE tc.constraint_type = 'PRIMARY KEY' "
            "AND tc.table_schema = current_schema() ORDER BY tc.table_name, kcu.ordinal_position"):
        out.setdefault(t, []).append(s)
    return out


def _pg_arten(v):
    """{(Tabelle, Spalte): Datentyp} der PostgreSQL-Datenbank."""
    return {(t, s): a for t, s, a in v.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema()")}


def pg_nach_sqlite(con, ziel):
    """Alles aus der PostgreSQL-Hülle con in die sqlite3.Connection ziel (leer oder wird ersetzt)."""
    v = con.v
    schluessel = _pg_schluessel(v)
    arten = _pg_arten(v)
    tabellen = [t for t in v.tabellen() if t not in EIGENE]
    for t in tabellen:
        spalten = v.spalten(t)
        pk = schluessel.get(t, [])
        defs = []
        for s in spalten:
            art = arten.get((t, s), "text")
            if pk == [s] and s == "id" and art in _ZAHL:
                defs.append('"id" INTEGER PRIMARY KEY')         # wie in der Datendatei: id = rowid
                continue
            sql_art = ("INTEGER" if art in ("bigint", "integer", "smallint") else "REAL" if art in _ZAHL
                       else "BLOB" if art == "bytea" else "TEXT")
            defs.append(f'"{s}" {sql_art}')
        if len(pk) > 1 or (pk and not (pk == ["id"] and arten.get((t, "id")) in _ZAHL)):
            defs.append("PRIMARY KEY (" + ", ".join(f'"{s}"' for s in pk) + ")")
        ziel.execute(f'DROP TABLE IF EXISTS "{t}"')
        ziel.execute(f'CREATE TABLE "{t}" ({", ".join(defs)})')
        liste = ", ".join(f'"{s}"' for s in spalten)
        zeilen = [tuple(bytes(w) if isinstance(w, memoryview) else w for w in z)
                  for z in v.execute(f'SELECT {liste} FROM "{t}"')]
        if zeilen:
            ziel.executemany(f'INSERT INTO "{t}" ({liste}) VALUES ({", ".join("?" * len(spalten))})', zeilen)
    ziel.execute(f"PRAGMA user_version={int(v.schema_version())}")
    ziel.commit()


def sqlite_nach_pg(quelle, con):
    """Inhalt der sqlite3.Connection quelle in die PostgreSQL-Hülle con (Tabellen in beiden: ersetzt)."""
    v = con.v
    arten = _pg_arten(v)
    ziel_tabellen = set(v.tabellen()) - EIGENE
    quell_tabellen = [r[0] for r in quelle.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                    "AND name NOT LIKE 'sqlite_%'")]
    if con.in_transaction:
        con.commit()
    with v.transaktion():
        v._roh("SET LOCAL session_replication_role = replica")     # Trigger und Fremdschlüssel ruhen
        for t in quell_tabellen:
            if t not in ziel_tabellen:
                continue
            ziel_spalten = set(v.spalten(t))
            spalten = [r[1] for r in quelle.execute(f'PRAGMA table_info("{t}")') if r[1] in ziel_spalten]
            v.execute(f'DELETE FROM "{t}"')
            if not spalten:
                continue
            zahl = [arten.get((t, s)) in _ZAHL for s in spalten]
            roh = [arten.get((t, s)) == "bytea" for s in spalten]
            liste = ", ".join(f'"{s}"' for s in spalten)
            zeilen = []
            for z in quelle.execute(f'SELECT {liste} FROM "{t}"'):
                zeilen.append(tuple(None if (zl and w == "") else (w.encode("utf-8") if (r and isinstance(w, str))
                                                                    else w)
                                    for w, zl, r in zip(z, zahl, roh)))
            if zeilen:
                v.executemany(f'INSERT INTO "{t}" ({liste}) VALUES ({", ".join("?" * len(spalten))})', zeilen)
        # Zähler der selbst hochzählenden Kennungen hinter die größte übernommene setzen
        for t, s in v.execute("SELECT table_name, column_name FROM information_schema.columns "
                              "WHERE table_schema = current_schema() AND is_identity = 'YES'").fetchall():
            if t in quell_tabellen:
                v.execute(f"SELECT setval(pg_get_serial_sequence('\"{t}\"', '{s}'), "
                          f'COALESCE((SELECT MAX("{s}") FROM "{t}"), 0) + 1, false)')
    db_verbindung.schema_version_setzen(con, quelle.execute("PRAGMA user_version").fetchone()[0])
