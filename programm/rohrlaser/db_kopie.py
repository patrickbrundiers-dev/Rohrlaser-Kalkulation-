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

EIGENE = {"stammdaten_stand", "angebot_aenderungen", "schema_stand", "zeilen_version"}     # Zähler der Verbindung, keine Daten
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


def _sqlite_art(art):
    return ("INTEGER" if art in ("bigint", "integer", "smallint") else "REAL" if art in _ZAHL
            else "BLOB" if art == "bytea" else "TEXT")


def sqlite_tabelle(con, t, ziel, ersetzen=False, schluessel=None, arten=None):
    """Tabelle t der PostgreSQL-Hülle con in der sqlite3.Connection ziel anlegen (gleiche Spalten und Primärschlüssel;
    id = rowid wie in der Datendatei). Gibt es sie schon, kommen nur fehlende Spalten dazu (ersetzen: neu anlegen).
    Ergebnis: Spalten von t."""
    v = con.v
    schluessel = _pg_schluessel(v) if schluessel is None else schluessel
    arten = _pg_arten(v) if arten is None else arten
    spalten = v.spalten(t)
    if ersetzen:
        ziel.execute(f'DROP TABLE IF EXISTS "{t}"')
    da = [r[1] for r in ziel.execute(f'PRAGMA table_info("{t}")')]
    if da:
        for s in spalten:
            if s not in da:
                ziel.execute(f'ALTER TABLE "{t}" ADD COLUMN "{s}" {_sqlite_art(arten.get((t, s), "text"))}')
        return spalten
    pk = schluessel.get(t, [])
    defs = []
    for s in spalten:
        art = arten.get((t, s), "text")
        if pk == [s] and s == "id" and art in _ZAHL:
            defs.append('"id" INTEGER PRIMARY KEY')         # wie in der Datendatei: id = rowid
        else:
            defs.append(f'"{s}" {_sqlite_art(art)}')
    if len(pk) > 1 or (pk and not (pk == ["id"] and arten.get((t, "id")) in _ZAHL)):
        defs.append("PRIMARY KEY (" + ", ".join(f'"{s}"' for s in pk) + ")")
    ziel.execute(f'CREATE TABLE "{t}" ({", ".join(defs)})')
    return spalten


def zeilen_nach_sqlite(con, t, ziel, bedingung="TRUE", werte=()):
    """Zeilen von t (PostgreSQL) mit bedingung in die gleichnamige Tabelle der sqlite3.Connection ziel (gemeinsame
    Spalten). Ergebnis: Anzahl."""
    hier = con.v.spalten(t)
    dort = {r[1] for r in ziel.execute(f'PRAGMA table_info("{t}")')}
    spalten = [s for s in hier if s in dort]
    liste = ", ".join(f'"{s}"' for s in spalten)
    zeilen = [tuple(bytes(w) if isinstance(w, memoryview) else w for w in z)
              for z in con.v.execute(f'SELECT {liste} FROM "{t}" WHERE {bedingung}', werte)]
    if zeilen:
        ziel.executemany(f'INSERT INTO "{t}" ({liste}) VALUES ({", ".join("?" * len(spalten))})', zeilen)
    return len(zeilen)


def pg_nach_sqlite(con, ziel):
    """Alles aus der PostgreSQL-Hülle con in die sqlite3.Connection ziel (leer oder wird ersetzt)."""
    v = con.v
    schluessel, arten = _pg_schluessel(v), _pg_arten(v)
    for t in [t for t in v.tabellen() if t not in EIGENE]:
        sqlite_tabelle(con, t, ziel, ersetzen=True, schluessel=schluessel, arten=arten)
        zeilen_nach_sqlite(con, t, ziel)
    ziel.execute(f"PRAGMA user_version={int(v.schema_version())}")
    ziel.commit()


_GANZ = {"bigint", "integer", "smallint"}


def wert_fuer_pg(w, art):
    """(Wert für eine PostgreSQL-Spalte der Art art, geändert?). SQLite nimmt in Zahlenspalten jeden Text an,
    PostgreSQL nicht: '' wird NULL (wie bisher, keine Änderung im Sinn des Berichts), Zahlen als Text (auch mit Komma)
    werden Zahlen, sonstiger Text NULL; Kommazahlen in Ganzzahl-Spalten werden gerundet. Text in Byte-Spalten wird
    UTF-8."""
    if w is None:
        return None, False
    if art in _ZAHL:
        if isinstance(w, bool):
            return int(w), False
        if isinstance(w, (bytes, bytearray, memoryview)):
            return None, True
        if isinstance(w, str):
            t = w.strip()
            if t == "":
                return None, False
            try:
                z = float(t.replace(",", ".")) if ("," in t and "." not in t) else float(t)
            except ValueError:
                return None, True
            if z != z or z in (float("inf"), float("-inf")):
                return None, True
            if art in _GANZ:
                return int(round(z)), True
            return z, True
        if art in _GANZ and isinstance(w, float):
            if w != w or w in (float("inf"), float("-inf")):
                return None, True
            return (int(round(w)), int(round(w)) != w)
        return w, False
    if art == "bytea" and isinstance(w, str):
        return w.encode("utf-8"), False
    if isinstance(w, (bytes, bytearray, memoryview)) and art in ("text", "character varying"):
        try:
            return bytes(w).decode("utf-8"), True
        except UnicodeDecodeError:
            return bytes(w).hex(), True
    return w, False


def sqlite_nach_pg(quelle, con, bericht=None):
    """Inhalt der sqlite3.Connection quelle in die PostgreSQL-Hülle con (Tabellen in beiden: ersetzt).
    bericht: Liste, in die jede angepasste Zelle als dict(tabelle, zeile, spalte, alt, neu) kommt (Phase 5)."""
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
            art = [arten.get((t, s)) for s in spalten]
            liste = ", ".join(f'"{s}"' for s in spalten)
            zeilen = []
            for z in quelle.execute(f'SELECT rowid, {liste} FROM "{t}"'):
                neu = []
                for w, a, s in zip(z[1:], art, spalten):
                    x, geaendert = wert_fuer_pg(w, a)
                    if geaendert and bericht is not None:
                        bericht.append(dict(tabelle=t, zeile=z[0], spalte=s, alt=w, neu=x))
                    neu.append(x)
                zeilen.append(tuple(neu))
            if zeilen:
                v.executemany(f'INSERT INTO "{t}" ({liste}) VALUES ({", ".join("?" * len(spalten))})', zeilen)
        # Zähler der selbst hochzählenden Kennungen hinter die größte übernommene setzen
        for t, s in v.execute("SELECT table_name, column_name FROM information_schema.columns "
                              "WHERE table_schema = current_schema() AND is_identity = 'YES'").fetchall():
            if t in quell_tabellen:
                v.execute(f"SELECT setval(pg_get_serial_sequence('\"{t}\"', '{s}'), "
                          f'COALESCE((SELECT MAX("{s}") FROM "{t}"), 0) + 1, false)')
    db_verbindung.schema_version_setzen(con, quelle.execute("PRAGMA user_version").fetchone()[0])
