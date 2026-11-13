"""Zentrale Datenbank-Verbindungsschicht für SQLite und PostgreSQL (Plan Datenbank-Modernisierung, Patrick 12.11.2026
„Alle Empfehlungen“, Phase 3a).

Bisher sprechen datenbank.py und rund 37 weitere Module direkt mit sqlite3 (db.con). Diese Schicht ist der eine Ort,
an dem künftig eine Verbindung entsteht und SQL ausgeführt wird. Sie bedient SQLite (heute, Migration, Archiv,
Rückfall) und PostgreSQL (Einzelplatz eingebettet und Datenbank-PC im Netzwerk) mit denselben Aufrufen:

- execute / executemany / einfuegen (liefert die neue ID, SQLite über lastrowid, PostgreSQL über RETURNING id)
- transaktion(): alles oder nichts; verschachtelt über SAVEPOINT. Außerhalb einer Transaktion gilt jede Anweisung
  sofort (autocommit), damit nie eine Lese-Transaktion offen bleibt und andere Arbeitsplätze aufhält.
- spalten(), tabellen(), schema_version(): ersetzen PRAGMA table_info / sqlite_master / user_version
- nur_lesen(): Lesemodus der Lizenz, von der Datenbank selbst durchgesetzt (SQLite query_only, PostgreSQL
  default_transaction_read_only)
- einheitliche Fehler: Doppelt, Konflikt, VerbindungWeg, KeineBerechtigung, NurLesen, NichtUebersetzbar

SQL wird im SQLite-Dialekt geschrieben, wie im ganzen Programm; nach_postgres() übersetzt die wenigen Unterschiede
zentral (Platzhalter ?, INSERT OR IGNORE, IS ? / IS NOT ?). Was sich nicht sicher übersetzen lässt (PRAGMA,
INSERT OR REPLACE ohne Konfliktspalten), löst NichtUebersetzbar aus, statt still etwas anderes zu tun.

Zugangsdaten stehen nie im Code: Adresse, Port, Datenbank und Benutzer kommen aus den Einstellungen, das Passwort
über eine Funktion (später Windows-Anmeldeinformationsverwaltung, beim eingebetteten Server aus pg_lokal).
"""
import contextlib
import functools
import os
import queue
import re
import sqlite3
import threading
from pathlib import Path

ANWENDUNG = "Rohrlaser-Kalkulation"
ABFRAGE_ZEITLIMIT_MS = 30_000      # PostgreSQL statement_timeout: keine Abfrage hält den Arbeitsplatz länger fest
SQLITE_WARTEN_S = 30               # SQLite busy_timeout: so lange auf eine Schreibsperre warten


# ------------------------------------------------------------------------------------------------ Fehler
class DbFehler(sqlite3.DatabaseError):
    """Oberklasse aller Datenbankfehler dieser Schicht; Text ist für den Benutzer gedacht. Erbt für den Übergang von den
    sqlite3-Fehlern, damit bestehendes except sqlite3.… weiter greift, auch wenn später PostgreSQL dahinter steht."""


class Doppelt(DbFehler, sqlite3.IntegrityError):
    """Eindeutiger Schlüssel verletzt (z. B. Angebotsnummer gibt es schon)."""


class Integritaet(DbFehler, sqlite3.IntegrityError):
    """Andere Regel der Datenbank verletzt (Fremdschlüssel, NOT NULL, CHECK)."""


class Konflikt(DbFehler):
    """Die Zeile wurde inzwischen von jemand anderem geändert oder gelöscht (Spalte version passt nicht)."""


class VerbindungWeg(DbFehler, sqlite3.OperationalError):
    """Keine Verbindung zur Datenbank (Datenbank-PC aus, Netzwerk weg, Datei gesperrt)."""


class KeineBerechtigung(DbFehler):
    """Die Rolle des Benutzers erlaubt diese Änderung nicht."""


class NurLesen(DbFehler, sqlite3.OperationalError):
    """Lesemodus: Ändern ist gesperrt."""


class Betriebsfehler(DbFehler, sqlite3.OperationalError):
    """Fehler beim Ausführen (z. B. Tabelle oder Spalte fehlt, SQL fehlerhaft)."""


class Bedienfehler(DbFehler, sqlite3.ProgrammingError):
    """Falsche Benutzung, z. B. Verbindung schon geschlossen."""


class NichtUebersetzbar(DbFehler):
    """SQL lässt sich nicht sicher nach PostgreSQL übersetzen; die Stelle muss die Schicht anders nutzen."""


# ------------------------------------------------------------------------------------------------ Zeilen
class Zeile(tuple):
    """Ergebniszeile wie sqlite3.Row: Zugriff über Index und Spaltenname, dict(zeile) liefert alle Spalten."""
    __slots__ = ()
    _index = {}

    def __getitem__(self, schluessel):
        if isinstance(schluessel, str):
            try:
                return tuple.__getitem__(self, self._index[schluessel])
            except KeyError:
                raise IndexError(f"Spalte {schluessel!r} gibt es nicht") from None
        return tuple.__getitem__(self, schluessel)

    def keys(self):
        return list(self._index)


def _zeilen_klasse(namen):
    """Eigene Zeilenklasse je Spaltenliste (einmal je Abfrage, nicht je Zeile)."""
    return type("Zeile", (Zeile,), {"__slots__": (), "_index": {n: i for i, n in enumerate(namen)}})


# ------------------------------------------------------------------------------------------------ Übersetzung
_TEIL = re.compile(r"""('(?:[^']|'')*')|("(?:[^"]|"")*")|(--[^\n]*)|(\?)|(%)|([^'"?%-]+|-)""", re.S)
_OR_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", re.I)
_OR_REPLACE = re.compile(r"^\s*(INSERT\s+OR\s+REPLACE|REPLACE)\s+INTO\b", re.I)
_RETURNING = re.compile(r"\bRETURNING\b", re.I)
_IS_NOT_PARAM = re.compile(r"\bIS\s+NOT\s+%s", re.I)
_IS_PARAM = re.compile(r"\bIS\s+%s", re.I)
_PRAGMA = re.compile(r"^\s*PRAGMA\b", re.I)
_SQLITE_MASTER = re.compile(r"\bsqlite_(master|schema|sequence)\b", re.I)


@functools.lru_cache(maxsize=4096)
def nach_postgres(sql):
    """SQL im SQLite-Dialekt des Programms nach PostgreSQL. Texte in Anführungszeichen und Kommentare bleiben
    unverändert; ? wird %s, ein wörtliches % wird %%. Ergebnis wird je SQL-Text gemerkt."""
    if _PRAGMA.match(sql):
        raise NichtUebersetzbar(f"PRAGMA gibt es nur in SQLite – bitte spalten()/schema_version()/nur_lesen() nutzen: "
                                f"{sql.strip()[:80]}")
    if _OR_REPLACE.match(sql):
        raise NichtUebersetzbar("INSERT OR REPLACE braucht in PostgreSQL die Konfliktspalten – bitte "
                                f"ersetzen(tabelle, werte, schluessel) nutzen: {sql.strip()[:80]}")
    teile = []
    for text, name, kommentar, frage, prozent, rest in _TEIL.findall(sql):
        if frage:
            teile.append("%s")
        elif prozent:
            teile.append("%%")
        else:
            teile.append(text or name or kommentar or rest)
    neu = "".join(teile)
    if _SQLITE_MASTER.search(_ohne_texte(neu)):
        raise NichtUebersetzbar(f"sqlite_master gibt es nur in SQLite – bitte tabellen() nutzen: {sql.strip()[:80]}")
    neu = _IS_NOT_PARAM.sub("IS DISTINCT FROM %s", neu)
    neu = _IS_PARAM.sub("IS NOT DISTINCT FROM %s", neu)
    if _OR_IGNORE.match(neu):
        neu = _OR_IGNORE.sub("INSERT INTO", neu, count=1)
        m = _RETURNING.search(_ohne_texte(neu))
        if m:
            neu = neu[:m.start()].rstrip() + " ON CONFLICT DO NOTHING " + neu[m.start():]
        else:
            neu = neu.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return neu


def _ohne_texte(sql):
    """Gleich langer Text, in dem Inhalte von '…' und "…" durch Leerzeichen ersetzt sind (für Suchen im SQL)."""
    return re.sub(r"""'(?:[^']|'')*'|"(?:[^"]|"")*\"""", lambda m: " " * len(m.group(0)), sql)


def _name(text):
    """Tabellen- oder Spaltenname sicher in Anführungszeichen (nur Buchstaben, Ziffern, _)."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text or ""):
        raise ValueError(f"Ungültiger Name: {text!r}")
    return f'"{text}"'


# ------------------------------------------------------------------------------------------------ Ergebnis
class Ergebnis:
    """Ergebnis einer Anweisung: fetchone/fetchall/Iteration, rowcount; Zeilen wie sqlite3.Row."""

    def __init__(self, zeilen, rowcount, lastrowid=None, description=None):
        self._zeilen = zeilen
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.description = description

    def __iter__(self):
        return iter(self._zeilen)

    def fetchone(self):
        return self._zeilen[0] if self._zeilen else None

    def fetchall(self):
        return list(self._zeilen)


# ------------------------------------------------------------------------------------------------ Basis
class Verbindung:
    """Gemeinsame Oberfläche beider Datenbanken. Nicht zwischen Threads teilen: je Thread eine eigene Verbindung
    (VerbindungsPool)."""
    art = ""

    def __init__(self):
        self._tiefe = 0
        self._lesen = False

    # -------- Anweisungen
    def execute(self, sql, werte=()):
        raise NotImplementedError

    def executemany(self, sql, liste):
        raise NotImplementedError

    def einfuegen(self, sql, werte=()):
        """INSERT ausführen und die neue ID zurückgeben (Spalte id)."""
        raise NotImplementedError

    def ersetzen(self, tabelle, werte, schluessel):
        """Zeile einfügen oder bei gleichem Schlüssel überschreiben (Ersatz für INSERT OR REPLACE).
        werte: dict Spalte -> Wert; schluessel: Spalten des eindeutigen Schlüssels."""
        spalten = list(werte)
        if not spalten or not set(schluessel) <= set(spalten):
            raise ValueError("ersetzen: Schlüsselspalten müssen in den Werten stehen")
        rest = [s for s in spalten if s not in schluessel]
        aktion = ("DO UPDATE SET " + ", ".join(f"{_name(s)}=excluded.{_name(s)}" for s in rest)) if rest else "DO NOTHING"
        sql = (f"INSERT INTO {_name(tabelle)} ({', '.join(_name(s) for s in spalten)}) "
               f"VALUES ({', '.join('?' * len(spalten))}) ON CONFLICT ({', '.join(_name(s) for s in schluessel)}) {aktion}")
        return self.execute(sql, [werte[s] for s in spalten])

    def aendern_mit_version(self, tabelle, zeilen_id, werte, version):
        """Optimistische Sperre: Felder nur ändern, wenn die Zeile noch die gelesene version hat; version + 1.
        Passt sie nicht, hat jemand anders inzwischen geändert -> Konflikt. Gibt die neue version zurück."""
        if not werte:
            return version
        setze = ", ".join(f"{_name(s)}=?" for s in werte)
        e = self.execute(f"UPDATE {_name(tabelle)} SET {setze}, version=version+1 WHERE id=? AND version=?",
                         [*werte.values(), zeilen_id, version])
        if e.rowcount != 1:
            raise Konflikt(f"{tabelle} {zeilen_id}: inzwischen von einem anderen Arbeitsplatz geändert oder gelöscht.")
        return version + 1

    # -------- Transaktionen
    @contextlib.contextmanager
    def transaktion(self):
        """Alles oder nichts. Verschachtelt: innere Blöcke als SAVEPOINT (Fehler innen verwirft nur den inneren)."""
        if self._lesen:
            raise NurLesen("Lesemodus – Ändern ist gesperrt.")
        tiefe = self._tiefe
        self._beginnen(tiefe)
        self._tiefe += 1
        try:
            yield self
        except BaseException:
            self._tiefe -= 1
            self._zurueck(tiefe)
            raise
        else:
            self._tiefe -= 1
            self._bestaetigen(tiefe)

    @property
    def in_transaktion(self):
        return self._tiefe > 0

    def _beginnen(self, tiefe):
        self._roh(f"SAVEPOINT sp{tiefe}" if tiefe else self._BEGIN)

    def _bestaetigen(self, tiefe):
        self._roh(f"RELEASE SAVEPOINT sp{tiefe}" if tiefe else "COMMIT")

    def _zurueck(self, tiefe):
        try:
            if tiefe:
                self._roh(f"ROLLBACK TO SAVEPOINT sp{tiefe}")
                self._roh(f"RELEASE SAVEPOINT sp{tiefe}")
            else:
                self._roh("ROLLBACK")
        except DbFehler:
            pass          # Verbindung weg: der Server verwirft die offene Transaktion selbst

    _BEGIN = "BEGIN"

    def _roh(self, sql):
        raise NotImplementedError

    # -------- Aufbau der Datenbank
    def tabellen(self):
        raise NotImplementedError

    def spalten(self, tabelle):
        raise NotImplementedError

    def schema_version(self):
        raise NotImplementedError

    def schema_version_setzen(self, nummer):
        raise NotImplementedError

    def nur_lesen(self, an):
        raise NotImplementedError

    def aenderungsstand(self):
        """Wert, der sich ändert, sobald eine andere Verbindung in die Datenbank geschrieben hat (eigene Änderungen
        dürfen ihn auch ändern; Aufrufer verwerfen dann nur einmal zu viel einen Zwischenspeicher)."""
        raise NotImplementedError

    def schliessen(self):
        raise NotImplementedError


# ------------------------------------------------------------------------------------------------ SQLite
class SqliteVerbindung(Verbindung):
    art = "sqlite"
    _BEGIN = "BEGIN IMMEDIATE"      # Schreibsperre gleich am Anfang: kein Abbruch mitten in der Transaktion

    def __init__(self, pfad, nur_lesen=False, warten=SQLITE_WARTEN_S, fremdschluessel=True):
        super().__init__()
        self.pfad = Path(pfad)
        try:
            if nur_lesen:
                self.con = sqlite3.connect(f"{self.pfad.resolve().as_uri()}?mode=ro", uri=True, timeout=warten,
                                           isolation_level=None, check_same_thread=False)
            else:
                self.con = sqlite3.connect(self.pfad, timeout=warten, isolation_level=None, check_same_thread=False)
        except sqlite3.Error as e:
            raise VerbindungWeg(f"Datendatei {self.pfad} lässt sich nicht öffnen: {e}") from e
        self.con.row_factory = sqlite3.Row
        self._roh(f"PRAGMA busy_timeout={int(warten * 1000)}")
        if fremdschluessel:
            self._roh("PRAGMA foreign_keys=ON")
        if nur_lesen:
            self.nur_lesen(True)

    def _ausfuehren(self, art, sql, werte):
        try:
            cur = getattr(self.con, art)(sql, werte)
            zeilen = cur.fetchall() if cur.description else []
            return Ergebnis(zeilen, cur.rowcount, cur.lastrowid, cur.description)
        except sqlite3.IntegrityError as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise Doppelt(str(e)) from e
            raise Integritaet(str(e)) from e
        except sqlite3.OperationalError as e:
            text = str(e)
            if "readonly" in text or "read-only" in text or "query_only" in text:
                raise NurLesen("Lesemodus – Ändern ist gesperrt.") from e
            if "locked" in text or "unable to open" in text or "disk I/O" in text:
                raise VerbindungWeg(text) from e
            raise Betriebsfehler(text) from e
        except sqlite3.ProgrammingError as e:
            raise Bedienfehler(str(e)) from e
        except sqlite3.Error as e:
            raise DbFehler(str(e)) from e

    def execute(self, sql, werte=()):
        return self._ausfuehren("execute", sql, werte)

    def executemany(self, sql, liste):
        return self._ausfuehren("executemany", sql, liste)

    def einfuegen(self, sql, werte=()):
        return self.execute(sql, werte).lastrowid

    def _roh(self, sql):
        self._ausfuehren("execute", sql, ())

    def tabellen(self):
        return [r[0] for r in self.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                           "AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    def spalten(self, tabelle):
        return [r[1] for r in self.execute(f"PRAGMA table_info({_name(tabelle)})")]

    def schema_version(self):
        return self.execute("PRAGMA user_version").fetchone()[0]

    def schema_version_setzen(self, nummer):
        self._roh(f"PRAGMA user_version={int(nummer)}")

    def nur_lesen(self, an):
        self._lesen = bool(an)
        self._roh(f"PRAGMA query_only={'ON' if an else 'OFF'}")

    def aenderungsstand(self):
        return self.execute("PRAGMA data_version").fetchone()[0]

    def schliessen(self):
        self.con.close()


# ------------------------------------------------------------------------------------------------ PostgreSQL
class PostgresVerbindung(Verbindung):
    """Verbindung zu PostgreSQL (psycopg 3). zugang: dict mit host, port, datenbank, benutzer, sslmode (Vorgabe
    prefer; im Netzwerk require) und optional sslrootcert; passwort: Funktion ohne Argumente oder Text."""
    art = "postgres"

    def __init__(self, zugang, passwort=None, nur_lesen=False, zeitlimit_ms=ABFRAGE_ZEITLIMIT_MS):
        super().__init__()
        try:
            import psycopg
        except ImportError as e:      # pragma: no cover - im Paket immer dabei
            raise VerbindungWeg("PostgreSQL-Treiber (psycopg) fehlt in dieser Installation.") from e
        self._psycopg = psycopg
        self.zugang = dict(zugang)
        self._passwort = passwort
        self._zeitlimit_ms = int(zeitlimit_ms)
        self._lesen_start = bool(nur_lesen)
        self.con = None
        self._verbinden()

    def _verbinden(self):
        z = self.zugang
        pw = self._passwort() if callable(self._passwort) else self._passwort
        werte = dict(host=z.get("host", "127.0.0.1"), port=int(z.get("port", 5432)), dbname=z.get("datenbank", "rohrlaser"),
                     user=z.get("benutzer"), password=pw, sslmode=z.get("sslmode", "prefer"),
                     application_name=z.get("anwendung", ANWENDUNG), connect_timeout=int(z.get("verbinden_s", 5)),
                     options=f"-c statement_timeout={self._zeitlimit_ms}")
        if z.get("sslrootcert"):
            werte["sslrootcert"] = z["sslrootcert"]
        try:
            self.con = self._psycopg.connect(autocommit=True, **{k: v for k, v in werte.items() if v is not None})
        except self._psycopg.OperationalError as e:
            raise VerbindungWeg(f"Keine Verbindung zur Datenbank auf {werte['host']}:{werte['port']} – "
                                f"läuft der Datenbank-PC? ({_kurz(e)})") from e
        self._tiefe = 0
        if self._lesen_start or self._lesen:
            self.nur_lesen(True)

    def _fehler(self, e):
        pg = self._psycopg
        code = getattr(getattr(e, "diag", None), "sqlstate", None) or ""
        if isinstance(e, pg.errors.UniqueViolation):
            return Doppelt(_kurz(e))
        if isinstance(e, pg.errors.ReadOnlySqlTransaction):
            return NurLesen("Lesemodus – Ändern ist gesperrt.")
        if isinstance(e, pg.errors.InsufficientPrivilege):
            return KeineBerechtigung(f"Keine Berechtigung für diese Änderung ({_kurz(e)}).")
        if isinstance(e, (pg.errors.SerializationFailure, pg.errors.DeadlockDetected)):
            return Konflikt(f"Gleichzeitige Änderung, bitte erneut versuchen ({_kurz(e)}).")
        if isinstance(e, pg.OperationalError) or code.startswith("08") or (self.con is not None and self.con.closed):
            return VerbindungWeg(f"Verbindung zur Datenbank unterbrochen ({_kurz(e)}).")
        return DbFehler(_kurz(e))

    def _ausfuehren(self, sql, werte, viele=False, lesen_wiederholen=True):
        if self.con is None or self.con.closed:
            if self._tiefe:
                raise VerbindungWeg("Verbindung während einer Änderung unterbrochen – nichts davon wurde gespeichert.")
            self._verbinden()
        pg_sql = nach_postgres(sql)
        try:
            with self.con.cursor() as cur:
                if viele:
                    cur.executemany(pg_sql, list(werte))
                    return Ergebnis([], cur.rowcount)
                cur.execute(pg_sql, tuple(werte) if werte is not None else None)
                zeilen, beschreibung = [], None
                if cur.description:
                    namen = [d.name for d in cur.description]
                    klasse = _zeilen_klasse(namen)
                    zeilen = [klasse(r) for r in cur.fetchall()]
                    beschreibung = tuple((n, None, None, None, None, None, None) for n in namen)
                return Ergebnis(zeilen, cur.rowcount, description=beschreibung)
        except self._psycopg.Error as e:
            fehler = self._fehler(e)
            # Nur reines Lesen außerhalb einer Transaktion wird nach Neuaufbau einmal wiederholt: Schreiben könnte
            # schon angekommen sein (Antwort verloren), das darf nicht doppelt passieren.
            if (isinstance(fehler, VerbindungWeg) and lesen_wiederholen and not self._tiefe and not viele
                    and _nur_lesen_sql(sql)):
                try:
                    self._verbinden()
                except VerbindungWeg:
                    raise fehler from e
                return self._ausfuehren(sql, werte, viele, lesen_wiederholen=False)
            raise fehler from e

    def execute(self, sql, werte=()):
        return self._ausfuehren(sql, werte)

    def executemany(self, sql, liste):
        return self._ausfuehren(sql, liste, viele=True)

    def einfuegen(self, sql, werte=()):
        if _RETURNING.search(_ohne_texte(sql)):
            raise ValueError("einfuegen: RETURNING setzt die Schicht selbst")
        z = self.execute(sql.rstrip().rstrip(";") + " RETURNING id", werte).fetchone()
        return z[0] if z else None

    def _roh(self, sql):
        self._ausfuehren(sql, None)

    def tabellen(self):
        return [r[0] for r in self.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() "
            "AND table_type = 'BASE TABLE' ORDER BY table_name")]

    def spalten(self, tabelle):
        return [r[0] for r in self.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND table_name = ? ORDER BY ordinal_position", (tabelle,))]

    def schema_version(self):
        self._roh("CREATE TABLE IF NOT EXISTS schema_stand (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)")
        r = self.execute("SELECT version FROM schema_stand WHERE id = 1").fetchone()
        return r[0] if r else 0

    def schema_version_setzen(self, nummer):
        self.schema_version()
        self.ersetzen("schema_stand", {"id": 1, "version": int(nummer)}, ["id"])

    def nur_lesen(self, an):
        self._lesen = bool(an)
        self._roh(f"SET default_transaction_read_only = {'on' if an else 'off'}")

    def aenderungsstand(self):
        # nächste zu vergebende Transaktionsnummer: wächst nur, wenn irgendwo eine schreibende Transaktion begann
        return int(self.execute("SELECT pg_snapshot_xmax(pg_current_snapshot())::text").fetchone()[0])

    def schliessen(self):
        if self.con is not None and not self.con.closed:
            self.con.close()


def _nur_lesen_sql(sql):
    return bool(re.match(r"^\s*(SELECT|WITH)\b", sql, re.I)) and not re.search(
        r"\b(INSERT|UPDATE|DELETE)\b", _ohne_texte(sql), re.I)


def _kurz(e):
    return str(e).strip().splitlines()[0][:300] if str(e).strip() else type(e).__name__


# ------------------------------------------------------------------------------------------------ Aufbau
def oeffnen(einstellung, passwort=None, nur_lesen=False):
    """Verbindung nach Einstellung: {"art": "sqlite", "pfad": …} oder {"art": "postgres", "host": …, "port": …,
    "datenbank": …, "benutzer": …, "sslmode": …}."""
    art = (einstellung or {}).get("art", "sqlite")
    if art == "sqlite":
        return SqliteVerbindung(einstellung["pfad"], nur_lesen=nur_lesen)
    if art == "postgres":
        return PostgresVerbindung(einstellung, passwort=passwort, nur_lesen=nur_lesen)
    raise ValueError(f"Unbekannte Datenbankart: {art!r}")


class VerbindungsPool:
    """Wenige offene Verbindungen für Hintergrundarbeiten (Sicherung, Prüfung, Suche), statt je Aufgabe neu zu
    verbinden. holen() gibt eine Verbindung für die Dauer des with-Blocks; kaputte Verbindungen werden ersetzt."""

    def __init__(self, fabrik, groesse=4, warten_s=30):
        self._fabrik = fabrik
        self._frei = queue.LifoQueue()
        self._anzahl = 0
        self._groesse = int(groesse)
        self._warten = warten_s
        self._sperre = threading.Lock()
        self._zu = False

    @contextlib.contextmanager
    def holen(self):
        if self._zu:
            raise VerbindungWeg("Datenbank wird gerade geschlossen.")
        v = self._nehmen()
        kaputt = False
        try:
            yield v
        except VerbindungWeg:
            kaputt = True
            raise
        finally:
            if v.in_transaktion:
                kaputt = True       # nicht abgeschlossene Transaktion: lieber neu verbinden
            if kaputt or self._zu:
                with contextlib.suppress(Exception):
                    v.schliessen()
                with self._sperre:
                    self._anzahl -= 1
            else:
                self._frei.put(v)

    def _nehmen(self):
        try:
            return self._frei.get_nowait()
        except queue.Empty:
            pass
        with self._sperre:
            neu = self._anzahl < self._groesse
            if neu:
                self._anzahl += 1
        if neu:
            try:
                return self._fabrik()
            except BaseException:
                with self._sperre:
                    self._anzahl -= 1
                raise
        try:
            return self._frei.get(timeout=self._warten)
        except queue.Empty:
            raise VerbindungWeg("Alle Datenbankverbindungen sind belegt.") from None

    @property
    def offen(self):
        return self._anzahl

    def schliessen(self):
        self._zu = True
        while True:
            try:
                v = self._frei.get_nowait()
            except queue.Empty:
                break
            with contextlib.suppress(Exception):
                v.schliessen()
            with self._sperre:
                self._anzahl -= 1


# ------------------------------------------------------------------------------------------------ Übergang
_AENDERT = re.compile(r"^\s*(INSERT|UPDATE|DELETE|REPLACE)\b", re.I)


# Bestandsaufnahme für PostgreSQL (Phase 3b): mit ROHRLASER_PG_PRUEFEN=<Datei> merkt sich jede SQLite-Hülle die
# Anweisungen, die nach_postgres() nicht übersetzen kann, und hängt sie beim Beenden als JSON-Zeilen an die Datei an.
_PG_PRUEFEN = os.environ.get("ROHRLASER_PG_PRUEFEN", "")
_PG_OFFEN = {}


def _pg_pruefen(sql):
    try:
        nach_postgres(sql)
    except NichtUebersetzbar as e:
        if sql not in _PG_OFFEN:
            import traceback
            stelle = next((f"{Path(f.filename).name}:{f.lineno}" for f in reversed(traceback.extract_stack()[:-3])
                           if Path(f.filename).name not in ("db_verbindung.py",)), "?")
            _PG_OFFEN[sql] = (stelle, str(e).split(":")[0])


def _pg_offen_schreiben():
    if _PG_OFFEN:
        import json
        with open(_PG_PRUEFEN, "a", encoding="utf-8") as f:
            for sql, (stelle, grund) in _PG_OFFEN.items():
                f.write(json.dumps({"stelle": stelle, "grund": grund, "sql": " ".join(sql.split())[:300]},
                                   ensure_ascii=False) + "\n")


if _PG_PRUEFEN:
    import atexit
    atexit.register(_pg_offen_schreiben)


class KompatVerbindung:
    """Hülle mit der Oberfläche von sqlite3.Connection über einer Verbindung dieser Schicht (Phase 3a Teil 2).

    Das Programm ruft an rund 450 Stellen db.con.execute(…), commit(), with db.con: … usw. auf. Diese Hülle lässt
    alle diese Aufrufe unverändert, führt sie aber über die Schicht aus: gleiche Fehler, später PostgreSQL. Verhalten
    wie das sqlite3-Modul (Python 3.12, isolation_level ""): vor INSERT/UPDATE/DELETE/REPLACE beginnt ohne offene
    Transaktion eine neue, commit()/rollback() beenden sie, with … bestätigt am Ende oder verwirft bei einem Fehler.
    SELECT, DDL und PRAGMA außerhalb einer Transaktion gelten sofort. Ergebnisse sind schon vollständig gelesen, ein
    weiterer Aufruf während einer Schleife über ein Ergebnis ist also unschädlich.

    Für Dinge, die es nur bei einer SQLite-Datei gibt (backup, Verbindung für ATTACH), steht roh bereit; das wird
    beim Wechsel auf PostgreSQL eigens ersetzt (Sicherung Phase 7)."""

    def __init__(self, verbindung):
        self.v = verbindung
        self._offen = False
        self._aenderungen = 0

    @property
    def art(self):
        return self.v.art

    @property
    def roh(self):
        """Die sqlite3.Connection darunter (nur SQLite), sonst None."""
        return self.v.con if self.v.art == "sqlite" else None

    def _vorher(self, sql):
        if _PG_PRUEFEN and self.v.art == "sqlite":
            _pg_pruefen(sql)
        aendert = bool(_AENDERT.match(sql))
        if aendert and not self.in_transaction:
            self.v._roh("BEGIN")
            self._offen = True
        return aendert

    def execute(self, sql, werte=()):
        aendert = self._vorher(sql)
        e = self.v.execute(sql, werte)
        if aendert and e.rowcount and e.rowcount > 0:
            self._aenderungen += e.rowcount
        return e

    def executemany(self, sql, liste):
        aendert = self._vorher(sql)
        e = self.v.executemany(sql, liste)
        if aendert and e.rowcount and e.rowcount > 0:
            self._aenderungen += e.rowcount
        return e

    @property
    def in_transaction(self):
        if self.v.art == "sqlite":
            return self.v.con.in_transaction
        return self._offen

    @property
    def total_changes(self):
        if self.v.art == "sqlite":
            return self.v.con.total_changes
        return self._aenderungen

    def commit(self):
        if self.in_transaction:
            self.v._roh("COMMIT")
        self._offen = False

    def rollback(self):
        if self.in_transaction:
            self.v._roh("ROLLBACK")
        self._offen = False

    def __enter__(self):
        return self

    def __exit__(self, art, wert, spur):
        if art is None:
            self.commit()
        else:
            self.rollback()
        return False

    def backup(self, ziel, **kw):
        if self.roh is None:
            raise NichtUebersetzbar("backup() gibt es nur bei einer SQLite-Datei (Sicherung über pg_dump, Phase 7).")
        return self.roh.backup(ziel, **kw)

    def close(self):
        self.v.schliessen()

    @property
    def row_factory(self):
        return sqlite3.Row

    @row_factory.setter
    def row_factory(self, wert):
        if wert is not sqlite3.Row:
            raise ValueError("Die Verbindungsschicht liefert immer Zeilen wie sqlite3.Row.")


# ------------------------------------------------------------------------------------------------ neutrale Helfer
# Statt INSERT OR REPLACE (nur SQLite): Einfügen oder bei gleichem Schlüssel ändern, gilt in SQLite und PostgreSQL.
EINSTELLUNG_SETZEN = ("INSERT INTO einstellungen (name, wert) VALUES (?, ?) "
                      "ON CONFLICT (name) DO UPDATE SET wert=excluded.wert")
NETZ_SETZEN = ("INSERT INTO netze (position_id, daten) VALUES (?, ?) "
               "ON CONFLICT (position_id) DO UPDATE SET daten=excluded.daten")

# Phase 3b: Fragen nach dem Aufbau der Datenbank, die das Programm bisher mit PRAGMA oder sqlite_master stellte.
# Sie nehmen eine KompatVerbindung (Hauptdatenbank, SQLite oder PostgreSQL) oder eine einfache sqlite3.Connection
# (Austauschdateien im gemeinsamen Ordner, Archiv, Sicherungen: die bleiben SQLite-Dateien).
def _schicht(con):
    return con.v if isinstance(con, KompatVerbindung) else None


def spalten(con, tabelle):
    """Spaltennamen einer Tabelle in Reihenfolge ([] wenn es sie nicht gibt)."""
    v = _schicht(con)
    if v is not None:
        return v.spalten(tabelle)
    return [r[1] for r in con.execute(f"PRAGMA table_info({_name(tabelle)})")]


def tabellen(con):
    """Namen aller Tabellen (ohne interne)."""
    v = _schicht(con)
    if v is not None:
        return v.tabellen()
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                      "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def schema_version(con):
    v = _schicht(con)
    if v is not None:
        return v.schema_version()
    return con.execute("PRAGMA user_version").fetchone()[0]


def schema_version_setzen(con, nummer):
    v = _schicht(con)
    if v is not None:
        return v.schema_version_setzen(nummer)
    con.execute(f"PRAGMA user_version={int(nummer)}")


def nur_lesen(con, an):
    """Lesemodus ein/aus: die Datenbank selbst nimmt dann keine Änderung mehr an."""
    v = _schicht(con)
    if v is not None:
        return v.nur_lesen(an)
    con.execute(f"PRAGMA query_only={'ON' if an else 'OFF'}")


def aenderungsstand(con):
    """Ändert sich, sobald eine andere Verbindung geschrieben hat (SQLite: PRAGMA data_version)."""
    v = _schicht(con)
    if v is not None:
        return v.aenderungsstand()
    return con.execute("PRAGMA data_version").fetchone()[0]


def ist_sqlite(con):
    v = _schicht(con)
    return v is None or v.art == "sqlite"
