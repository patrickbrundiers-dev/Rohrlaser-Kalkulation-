"""Trigger für SQLite und PostgreSQL (Plan Datenbank-Modernisierung, Phase 3b Teil 2).

Das Programm führt mit Triggern ein Änderungsprotokoll, merkt geänderte Angebote, vergibt feste Kennungen (uid) und
zählt Änderungen für Zwischenspeicher. SQLite schreibt den Rumpf direkt in CREATE TRIGGER, PostgreSQL braucht eine
Funktion in PL/pgSQL und kennt keine TEMP-Trigger. Dieses Modul baut beides aus derselben Beschreibung:

    trigger(con, name, tabelle, "INSERT", ["INSERT INTO x …"], wann="NEW.uid IS NOT NULL")

Im Rumpf gelten NEW/OLD wie in beiden Datenbanken; für Zeit, neue Kennung und Vergleich mit NULL gibt es Helfer
(jetzt_text, neue_kennung, gleich), damit kein Funktionsname nur einer Datenbank im Text steht.
"""
from . import db_verbindung


def _pg(con):
    return not db_verbindung.ist_sqlite(con)


def neue_kennung(con):
    """SQL-Ausdruck: neue zufällige Kennung (32 Zeichen 0-9a-f)."""
    return "replace(gen_random_uuid()::text, '-', '')" if _pg(con) else "lower(hex(randomblob(16)))"


def jetzt_text(con, minus_tage=0):
    """SQL-Ausdruck: Zeitpunkt jetzt (UTC) als Text JJJJ-MM-TTTHH:MM:SS.mmm, wahlweise minus Tage."""
    if _pg(con):
        zeit = "(clock_timestamp() AT TIME ZONE 'UTC')"
        if minus_tage:
            zeit = f"({zeit} - interval '{int(minus_tage)} days')"
        return f"""to_char({zeit}, 'YYYY-MM-DD"T"HH24:MI:SS.MS')"""
    tage = f", '-{int(minus_tage)} days'" if minus_tage else ""
    return f"strftime('%Y-%m-%dT%H:%M:%f', 'now'{tage})"


def gleich(con, a, b):
    """SQL: a gleich b, NULL gleich NULL (SQLite „IS“)."""
    return f"{a} IS NOT DISTINCT FROM {b}" if _pg(con) else f"{a} IS {b}"


def _rumpf_pg(sql):
    return db_verbindung.nach_postgres(sql).replace("%%", "%")


def trigger(con, name, tabelle, art, rumpf, wann=None, temp=False, funktion=None):
    """Trigger name nach art (INSERT/UPDATE/DELETE) auf tabelle neu anlegen (ein vorhandener gleichen Namens wird
    ersetzt). rumpf: Liste von SQL-Anweisungen, je Zeile ausgeführt. temp: nur für diese Verbindung (SQLite); bei
    PostgreSQL gibt es das nicht, dort gilt der Trigger für alle Verbindungen. funktion: Name der PL/pgSQL-Funktion,
    wenn mehrere Trigger denselben Rumpf teilen (sonst eine je Trigger)."""
    if not _pg(con):
        schema = "temp." if temp else ""
        con.execute(f'DROP TRIGGER IF EXISTS {schema}"{name}"')
        ziel = f'main."{tabelle}"' if temp else f'"{tabelle}"'
        bedingung = f"WHEN {wann} " if wann else ""
        con.execute(f'CREATE {"TEMP " if temp else ""}TRIGGER "{name}" AFTER {art} ON {ziel} {bedingung}BEGIN '
                    + " ".join(s.rstrip(";") + ";" for s in rumpf) + " END")
        return
    funktion = funktion or f"{name}_f"
    anweisungen = " ".join(_rumpf_pg(s).rstrip(";") + ";" for s in rumpf)
    if wann:
        anweisungen = f"IF {_rumpf_pg(wann)} THEN {anweisungen} END IF;"
    con.execute(f'CREATE OR REPLACE FUNCTION "{funktion}"() RETURNS trigger LANGUAGE plpgsql AS $rumpf$ '
                f"BEGIN {anweisungen} RETURN NULL; END $rumpf$")
    con.execute(f'DROP TRIGGER IF EXISTS "{name}" ON "{tabelle}"')
    con.execute(f'CREATE TRIGGER "{name}" AFTER {art} ON "{tabelle}" FOR EACH ROW EXECUTE FUNCTION "{funktion}"()')


def kennung_trigger(con, name, tabelle, auch_kopie=False):
    """Beim Einfügen ohne Kennung (uid) eine neue vergeben; auch_kopie: auch wenn die Kennung schon vergeben ist."""
    if not _pg(con):
        bedingung = "NEW.uid IS NULL"
        if auch_kopie:
            bedingung += f' OR EXISTS (SELECT 1 FROM "{tabelle}" WHERE uid = NEW.uid AND rowid <> NEW.rowid)'
        con.execute(f'CREATE TRIGGER IF NOT EXISTS "{name}" AFTER INSERT ON "{tabelle}" WHEN {bedingung} '
                    f'BEGIN UPDATE "{tabelle}" SET uid = {neue_kennung(con)} WHERE rowid = NEW.rowid; END')
        return
    bedingung = "NEW.uid IS NULL"
    if auch_kopie:
        bedingung += f' OR EXISTS (SELECT 1 FROM "{tabelle}" WHERE uid = NEW.uid)'
    funktion = f"{name}_f"
    con.execute(f'CREATE OR REPLACE FUNCTION "{funktion}"() RETURNS trigger LANGUAGE plpgsql AS $rumpf$ '
                f"BEGIN IF {bedingung} THEN NEW.uid := {neue_kennung(con)}; END IF; RETURN NEW; END $rumpf$")
    con.execute(f'DROP TRIGGER IF EXISTS "{name}" ON "{tabelle}"')
    con.execute(f'CREATE TRIGGER "{name}" BEFORE INSERT ON "{tabelle}" FOR EACH ROW EXECUTE FUNCTION "{funktion}"()')


def namen(con, endung):
    """[(Trigger, Tabelle)] aller Trigger, deren Name auf endung endet."""
    if not _pg(con):
        return [(r[0], r[1]) for r in con.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'")
                if r[0].endswith(endung)]
    return [(r[0], r[1]) for r in con.execute(
        "SELECT t.tgname, c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "WHERE NOT t.tgisinternal") if r[0].endswith(endung)]


def loeschen(con, name, tabelle):
    if not _pg(con):
        con.execute(f'DROP TRIGGER IF EXISTS "{name}"')
    else:
        con.execute(f'DROP TRIGGER IF EXISTS "{name}" ON "{tabelle}"')
