"""Datenspeicher je Arbeitsplatz: SQLite-Datendatei (Standard) oder eingebettetes PostgreSQL (Plan
Datenbank-Modernisierung, Phase 3c; Patrick 13.11.2026 „lokal speichern und abgleichen“). Ohne Qt.

Umstellen darf nur der Hauptadmin. Ablauf von umstellen():
1. geprüfte Sicherung der Datendatei (…_vor_PostgreSQL), ohne sie geht nichts weiter;
2. eingebetteten Server im Datenordner anlegen und starten (pg_lokal, Ordner Daten/pg, nur 127.0.0.1);
3. Tabellen anlegen und alle Zeilen übernehmen (db_kopie.sqlite_nach_pg), danach jede Tabelle Zeile für Zeile
   vergleichen; bei einem Unterschied wird nicht umgestellt;
4. die SQLite-Datendatei bleibt unverändert als …_SQLite_bis_<Datum>.db liegen (Rückfall); an ihrer Stelle steht
   eine kleine Merkdatei (eine SQLite-Datei mit der Tabelle datenspeicher). Datenbank(pfad) erkennt sie und öffnet
   das PostgreSQL. Die Merkdatei steht am alten Ort, damit Pfade, Sperre, Sicherung und Abgleich unverändert bleiben.

zurueck() schreibt alles wieder in eine normale SQLite-Datendatei (geprüft und verglichen) und ersetzt die
Merkdatei; der PostgreSQL-Ordner bleibt liegen, bis man ihn selbst löscht.
"""
import atexit
import datetime
import hashlib
import sqlite3
from pathlib import Path

from . import db_verbindung

TABELLE = "datenspeicher"
SQLITE, POSTGRES = "sqlite", "postgres"
TITEL = {SQLITE: "SQLite-Datendatei", POSTGRES: "PostgreSQL auf diesem PC"}

_server = {}            # Datenordner → LokalerServer (von diesem Programm gestartet, beim Beenden gestoppt)


class UmstellFehler(RuntimeError):
    """Umstellen oder Zurückstellen nicht gelungen; die Daten sind unverändert."""


# ------------------------------------------------------------------------------------------------ Merkdatei
def merkdatei_lesen(pfad):
    """Inhalt der Merkdatei als dict, oder None (normale Datendatei oder keine Datei)."""
    pfad = Path(pfad)
    try:
        if not pfad.is_file() or pfad.stat().st_size > 64 * 1024:
            return None
        con = sqlite3.connect(f"{pfad.resolve().as_uri()}?mode=ro", uri=True)
    except (OSError, sqlite3.Error):
        return None
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABELLE,)).fetchone():
            return None
        return dict(con.execute(f"SELECT schluessel, wert FROM {TABELLE}").fetchall())
    except sqlite3.Error:
        return None
    finally:
        con.close()


def art(pfad):
    m = merkdatei_lesen(pfad)
    return POSTGRES if m and m.get("art") == POSTGRES else SQLITE


def _merkdatei_schreiben(pfad, werte):
    tmp = Path(pfad).with_name(Path(pfad).name + ".merk")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        con.execute(f"CREATE TABLE {TABELLE} (schluessel TEXT PRIMARY KEY, wert TEXT)")
        con.executemany(f"INSERT INTO {TABELLE} VALUES (?, ?)", [(k, str(v)) for k, v in werte.items()])
        con.commit()
    finally:
        con.close()
    return tmp


# ------------------------------------------------------------------------------------------------ Server
def server(pfad, bin_ordner=None):
    """Eingebetteter Server zum Datenordner der Datendatei pfad (gestartet)."""
    from . import pg_lokal
    ordner = Path(pfad).resolve().parent
    s = _server.get(ordner)
    if s is None:
        s = pg_lokal.LokalerServer(ordner, bin_ordner)
        _server[ordner] = s
        if not _server.get("_atexit"):
            _server["_atexit"] = True
            atexit.register(alle_stoppen)
    s.starten()
    return s


def alle_stoppen():
    for k, s in list(_server.items()):
        if k != "_atexit":
            try:
                s.stoppen()
            except Exception:       # beim Beenden nie hängen bleiben
                pass
            _server.pop(k, None)


def oeffnen(pfad):
    """PostgresVerbindung für eine Datendatei mit Merkdatei (Server wird bei Bedarf gestartet)."""
    s = server(pfad)
    return db_verbindung.PostgresVerbindung(s.zugang(), s.passwort())


# ------------------------------------------------------------------------------------------------ Vergleich
def _wert(w):
    if w is None or w == "":
        return None
    if isinstance(w, bool):
        return int(w)
    if isinstance(w, (int, float)):
        return round(float(w), 9)
    if isinstance(w, (bytes, bytearray, memoryview)):
        return "b:" + hashlib.sha256(bytes(w)).hexdigest()
    return str(w)


def _abdruck(zeilen):
    h = hashlib.sha256()
    for z in sorted(repr(tuple(_wert(w) for w in z)) for z in zeilen):
        h.update(z.encode("utf-8"))
    return h.hexdigest()


def vergleichen(sqlite_con, pg_con):
    """Unterschiede zwischen einer sqlite3.Connection und einer PostgreSQL-Hülle: Liste von Texten (leer = gleich).
    Verglichen werden Anzahl und Inhalt jeder Programmtabelle über die gemeinsamen Spalten."""
    from . import db_kopie
    unterschiede = []
    hier = {r[0] for r in sqlite_con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE "
                                             "'sqlite_%'")} - db_kopie.EIGENE
    dort = set(db_verbindung.tabellen(pg_con)) - db_kopie.EIGENE
    for t in sorted(hier - dort):
        if sqlite_con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]:
            unterschiede.append(f"Tabelle {t} fehlt")
    for t in sorted(hier & dort):
        a = [r[1] for r in sqlite_con.execute(f'PRAGMA table_info("{t}")')]
        b = set(db_verbindung.spalten(pg_con, t))
        spalten = [s for s in a if s in b]
        liste = ", ".join(f'"{s}"' for s in spalten)
        za = sqlite_con.execute(f'SELECT {liste} FROM "{t}"').fetchall()
        zb = pg_con.execute(f'SELECT {liste} FROM "{t}"').fetchall()
        if len(za) != len(zb):
            unterschiede.append(f"{t}: {len(za)} statt {len(zb)} Zeilen")
        elif _abdruck(za) != _abdruck(zb):
            unterschiede.append(f"{t}: Inhalt weicht ab")
    return unterschiede


# ------------------------------------------------------------------------------------------------ Umstellen
def umstellen(db, bin_ordner=None, heute=None):
    """SQLite-Datendatei von db (offen) nach PostgreSQL. Danach ist db geschlossen; das Programm muss neu starten.
    Ergebnis: dict(sicherung, rueckfall, tabellen, angebote). UmstellFehler, wenn etwas nicht stimmt (dann bleibt
    alles wie vorher)."""
    from . import db_kopie
    from .datenbank import Datenbank, datei_pruefen
    if not db_verbindung.ist_sqlite(db.con):
        raise UmstellFehler("Die Daten liegen schon in PostgreSQL.")
    pfad = Path(db.pfad)
    heute = heute or datetime.date.today()
    if db.con.in_transaction:
        db.con.commit()
    try:
        sicherung = db.sicherung(zusatz="vor_PostgreSQL")
        datei_pruefen(sicherung)
    except Exception as e:
        raise UmstellFehler(f"Die Sicherung vor dem Umstellen ist nicht gelungen: {e}") from e
    try:
        s = server(pfad, bin_ordner)
    except Exception as e:
        raise UmstellFehler(f"PostgreSQL lässt sich auf diesem PC nicht starten: {e}") from e
    pg = db_verbindung.PostgresVerbindung(s.zugang(), s.passwort())
    if any(t not in db_kopie.EIGENE for t in pg.tabellen()):
        pg.schliessen()
        raise UmstellFehler(f"Im PostgreSQL-Ordner {s.pg} liegen schon Daten. Bitte den Ordner umbenennen und noch "
                            "einmal umstellen.")
    pg.schliessen()
    db.schliessen()
    ziel = Datenbank(pfad, verbindung=oeffnen(pfad))       # Tabellen wie im Programm anlegen
    try:
        quelle = sqlite3.connect(f"{pfad.resolve().as_uri()}?mode=ro", uri=True)
        try:
            db_kopie.sqlite_nach_pg(quelle, ziel.con)
            unterschiede = vergleichen(quelle, ziel.con)
            angebote = quelle.execute("SELECT COUNT(*) FROM angebote").fetchone()[0]
            tabellen = len(set(db_verbindung.tabellen(ziel.con)) - db_kopie.EIGENE)
        finally:
            quelle.close()
    finally:
        ziel.schliessen()
    if unterschiede:
        _pg_leeren(pfad)
        raise UmstellFehler("Nach dem Übernehmen stimmen die Daten nicht überein (" + "; ".join(unterschiede[:5])
                            + "). Es wurde nicht umgestellt.")
    rueckfall = _frei(pfad.with_name(f"{pfad.stem}_SQLite_bis_{heute:%Y-%m-%d}.db"))
    merk = _merkdatei_schreiben(pfad, dict(art=POSTGRES, seit=datetime.datetime.now().isoformat(timespec="seconds"),
                                           rueckfall=rueckfall.name, ordner="pg"))
    pfad.replace(rueckfall)
    merk.replace(pfad)
    return dict(sicherung=sicherung, rueckfall=rueckfall, tabellen=tabellen, angebote=angebote)


def zurueck(db, heute=None):
    """PostgreSQL-Daten von db (offen) wieder in eine SQLite-Datendatei am alten Ort. Danach ist db geschlossen;
    das Programm muss neu starten. Ergebnis: dict(sicherung, datei, angebote)."""
    from .datenbank import datei_pruefen
    if db_verbindung.ist_sqlite(db.con):
        raise UmstellFehler("Die Daten liegen schon in einer SQLite-Datendatei.")
    pfad = Path(db.pfad)
    heute = heute or datetime.date.today()
    if db.con.in_transaction:
        db.con.commit()
    try:
        sicherung = db.sicherung(zusatz="vor_SQLite")
        datei_pruefen(sicherung)
    except Exception as e:
        raise UmstellFehler(f"Die Sicherung vor dem Zurückstellen ist nicht gelungen: {e}") from e
    neu = pfad.with_name(pfad.name + ".neu")
    neu.unlink(missing_ok=True)
    ziel = sqlite3.connect(neu)
    try:
        db.con.backup(ziel)
        unterschiede = vergleichen(ziel, db.con)
        angebote = ziel.execute("SELECT COUNT(*) FROM angebote").fetchone()[0]
    finally:
        ziel.close()
    if unterschiede:
        neu.unlink(missing_ok=True)
        raise UmstellFehler("Die SQLite-Datendatei stimmt nicht mit PostgreSQL überein ("
                            + "; ".join(unterschiede[:5]) + "). Es wurde nicht zurückgestellt.")
    datei_pruefen(neu)
    db.schliessen()
    merk_alt = _frei(pfad.with_name(f"{pfad.stem}_PostgreSQL_bis_{heute:%Y-%m-%d}.merk"))
    pfad.replace(merk_alt)
    neu.replace(pfad)
    return dict(sicherung=sicherung, datei=pfad, angebote=angebote)


def _frei(p):
    p = Path(p)
    n = 2
    while p.exists():
        p = p.with_name(f"{p.stem.rsplit('_(', 1)[0]}_({n}){p.suffix}")
        n += 1
    return p


def _pg_leeren(pfad):
    """Nach einem misslungenen Umstellen die halb gefüllte Datenbank wieder leeren."""
    try:
        v = oeffnen(pfad)
        try:
            v._roh("DROP SCHEMA public CASCADE")
            v._roh("CREATE SCHEMA public")
        finally:
            v.schliessen()
    except Exception:
        pass


def status(db):
    """Text für den Dialog: wo die Daten liegen."""
    if db_verbindung.ist_sqlite(db.con):
        return f"{TITEL[SQLITE]}: {db.pfad}"
    m = merkdatei_lesen(db.pfad) or {}
    return (f"{TITEL[POSTGRES]} (Ordner {Path(db.pfad).parent / m.get('ordner', 'pg')}, seit "
            f"{m.get('seit', '–')[:16].replace('T', ' ')}); Rückfall-Datei {m.get('rueckfall', '–')}")
