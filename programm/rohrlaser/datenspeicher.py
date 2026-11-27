"""Datenspeicher je Arbeitsplatz: eingebettetes PostgreSQL, die einzige Datenbank des Programms (Phase 3c, Patrick
13.11.2026 „lokal speichern und abgleichen“; seit 19.11.2026 „SQLite vollständig entfernen“, je PC eigenes PostgreSQL,
Abgleich über den gemeinsamen Ordner bleibt). Ohne Qt.

bereitstellen(pfad) ist der einzige Weg zu den Daten:
- Merkdatei am Pfad: PostgreSQL öffnen (Server bei Bedarf starten).
- keine Datei: neue Installation, PostgreSQL direkt anlegen (Ordner Daten/pg, nur 127.0.0.1) und Merkdatei schreiben.
- alte SQLite-Datendatei (vor dem Update): automatisch umstellen, Ablauf von umstellen():
  1. Schema wie gewohnt erweitern, geprüfte Sicherung (…_vor_PostgreSQL), ohne sie geht nichts weiter;
  2. Server anlegen und starten;
  3. Tabellen anlegen und alle Zeilen übernehmen (db_kopie.sqlite_nach_pg); danach jede Tabelle Zeile für Zeile
     vergleichen, Fremdschlüssel prüfen und die letzten Angebote in beiden Datenbanken neu kalkulieren und
     vergleichen; bei einem Unterschied wird nicht umgestellt (UmstellFehler, Bericht im Ordner Sicherung);
  4. die SQLite-Datendatei kommt unverändert als Archiv nach Sicherung/Migration (nicht mehr im Betrieb); an ihrer
     Stelle steht eine kleine Merkdatei (Tabelle datenspeicher), damit Pfade, Sperre, Sicherung und Abgleich bleiben.
Ein Rückweg auf SQLite und ein SQLite-Betrieb bei Störungen sind bewusst nicht vorgesehen. SQLite-Dateien gibt es
nur noch als Dateiformat: Merkdatei, Sicherungen, Austauschdateien im gemeinsamen Ordner, Archiv.
"""
import atexit
import contextlib
import datetime
import hashlib
import sqlite3
import time
from pathlib import Path

from . import db_verbindung

TABELLE = "datenspeicher"
SQLITE, POSTGRES, SERVER = "sqlite", "postgres", "server"
TITEL = {SQLITE: "SQLite-Datendatei", POSTGRES: "PostgreSQL auf diesem PC", SERVER: "Zentraler Server"}
ARCHIV = "Migration"    # Unterordner von Sicherung: die alte SQLite-Datendatei nach dem Umstellen (nur Archiv)

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


def ist_sqlite_datei(pfad):
    """Echte SQLite-Datei mit Inhalt (keine Merkdatei, kein leerer Platzhalter des Prüflaufs)."""
    try:
        with open(pfad, "rb") as f:
            kopf = f.read(16)
    except OSError:
        return False
    return kopf == b"SQLite format 3\x00" and merkdatei_lesen(pfad) is None


def pg_test_umstellen(pfad):
    """Prüflauf gegen PostgreSQL (db_verbindung.pg_test_an): liegt am Pfad eine echte SQLite-Datendatei (ein Test hat
    einen alten Stand gebaut), geht sie wie beim Update nach PostgreSQL: auf SQLite das Schema erweitern, in die
    Datenbank des Pfads auf dem Prüfserver übernehmen; danach steht am Pfad der leere Platzhalter des Prüflaufs."""
    from . import db_kopie
    from .datenbank import Datenbank
    pfad = Path(pfad)
    Datenbank(pfad, verbindung=db_verbindung.SqliteVerbindung(pfad, fremdschluessel=False)).schliessen()
    z, passwort = db_verbindung.pg_test_zugang()
    name = db_verbindung.pg_test_name(pfad)
    v = db_verbindung.PostgresVerbindung(z, passwort)
    try:
        v._roh(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        v._roh(f'CREATE DATABASE "{name}"')
    finally:
        v.schliessen()
    ziel = Datenbank(pfad, verbindung=db_verbindung.PostgresVerbindung(dict(z, datenbank=name), passwort))
    try:
        quelle = sqlite3.connect(f"{pfad.resolve().as_uri()}?mode=ro", uri=True)
        try:
            db_kopie.sqlite_nach_pg(quelle, ziel.con)
        finally:
            quelle.close()
        ziel._anlegen()
    finally:
        ziel.schliessen()
    for rest in (pfad.with_name(pfad.name + "-wal"), pfad.with_name(pfad.name + "-shm")):
        rest.unlink(missing_ok=True)
    pfad.write_bytes(b"")


def art(pfad):
    m = merkdatei_lesen(pfad)
    if m and m.get("art") in (POSTGRES, SERVER):
        return m["art"]
    return SQLITE


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
def server(pfad, bin_ordner=None, unterordner=None):
    """Eingebetteter Server zum Datenordner der Datendatei pfad (gestartet). unterordner: eigener Server in diesem
    Ordner daneben (Rohrlaser Auslastung: Auslastung_PG, getrennt vom PostgreSQL der Kalkulation)."""
    from . import pg_lokal
    ordner = Path(pfad).resolve().parent
    if unterordner:
        ordner = ordner / unterordner
    s = _server.get(ordner)
    if s is None:
        s = pg_lokal.LokalerServer(ordner, bin_ordner)
        _server[ordner] = s
        if not _server.get("_atexit"):
            _server["_atexit"] = True
            atexit.register(alle_stoppen)
        s.starten()
        try:                    # Schritt 2 (19.11.2026): Programm nie als Superuser; ältere Datenordner umstellen
            if s.rollen_pruefen():
                from . import protokoll
                protokoll.info(f"PostgreSQL in {ordner}: Programmkonto ohne Superuser-Rechte, Verwalter angelegt, "
                               "Verbindungsprotokoll an")
        except Exception:       # noqa: BLE001 - Daten bleiben erreichbar; Statusanzeige zeigt die Rechte
            from . import protokoll
            protokoll.warnung(f"PostgreSQL in {ordner}: Rechte des Programmkontos nicht umgestellt")
    s.starten()
    if s.reparaturen:           # Windows-Update-Sicherheit 26.11.2026: Selbstheilung beim Start ins Protokoll
        from . import protokoll
        for r in s.reparaturen:
            protokoll.info(f"PostgreSQL in {ordner}: {r}")
        s.reparaturen.clear()
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
    return _mit_wiederbeleben(db_verbindung.PostgresVerbindung(s.zugang(), s.passwort()), pfad)


def _mit_wiederbeleben(v, pfad):
    """Schritt 5: bricht die Verbindung ab, weil der Server dieses PCs nicht mehr läuft, startet ihn die Verbindung
    neu (server() startet bei Bedarf) und nimmt den neuen Zugang (anderer Port)."""
    v.wiederbeleben = lambda p=Path(pfad): server(p).zugang()
    return v


def bereitstellen(pfad, bin_ordner=None):
    """PostgresVerbindung zu den Daten am Pfad der Datendatei; legt PostgreSQL neu an oder stellt eine alte
    SQLite-Datendatei automatisch um (siehe oben). UmstellFehler, wenn das nicht geht (die Daten bleiben dann, wie
    sie sind)."""
    pfad = Path(pfad)
    m = merkdatei_lesen(pfad)
    if m and m.get("art") == SERVER:        # Serverbetrieb (Serverversion S1): zentrale Datenbank, angemeldet
        from . import server_betrieb
        return server_betrieb.oeffnen(pfad, m)
    if art(pfad) == POSTGRES:
        try:
            return oeffnen(pfad)
        except Exception as e:
            raise UmstellFehler(f"PostgreSQL lässt sich auf diesem PC nicht starten: {e}") from e
    if ist_sqlite_datei(pfad):
        from .datenbank import Datenbank
        quelle = Datenbank(pfad, verbindung=db_verbindung.SqliteVerbindung(pfad, fremdschluessel=False))
        try:
            umstellen(quelle, bin_ordner)
        finally:
            with contextlib.suppress(Exception):     # umstellen() schließt sie schon
                quelle.schliessen()
        return oeffnen(pfad)
    return neu_anlegen(pfad, bin_ordner)


def neu_anlegen(pfad, bin_ordner=None):
    """Neue Installation: PostgreSQL im Datenordner anlegen und die Merkdatei schreiben. Liegen im Ordner Daten/pg
    schon Daten (Merkdatei verloren), werden sie geöffnet, nicht überschrieben."""
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    try:
        s = server(pfad, bin_ordner)
    except Exception as e:
        raise UmstellFehler(f"PostgreSQL lässt sich auf diesem PC nicht anlegen: {e}") from e
    merk = _merkdatei_schreiben(pfad, dict(art=POSTGRES, seit=datetime.datetime.now().isoformat(timespec="seconds"),
                                           ordner="pg"))
    merk.replace(pfad)
    return _mit_wiederbeleben(db_verbindung.PostgresVerbindung(s.zugang(), s.passwort()), pfad)


def kalkulationen(db, ids=None, anzahl=20):
    """{Angebots-ID: Summen der Kalkulation, gerundet} der letzten `anzahl` gerechneten Angebote (oder der genannten);
    zum Vergleich vor und nach dem Umstellen (keine Kalkulation darf sich ändern)."""
    from . import rechnen
    if ids is None:
        ids = [r[0] for r in db.con.execute("SELECT id FROM angebote WHERE ergebnis IS NOT NULL "
                                            "ORDER BY id DESC LIMIT ?", (anzahl,)).fetchall()]
    out = {}
    if not ids:
        return out
    k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
    for aid in ids:
        try:
            kopf, pos = db.angebot(aid), db.positionen(aid)
            e = rechnen.einstellungen_angebot(kopf, einst)
            _zeilen, summen = rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)
            out[aid] = _gerundet(summen)
        except Exception as ex:     # noqa: BLE001 – derselbe Fehler auf beiden Seiten ist kein Unterschied
            out[aid] = f"Fehler {type(ex).__name__}: {ex}"[:200]
    return out


def _gerundet(w):
    if isinstance(w, bool) or w is None or isinstance(w, str):
        return w
    if isinstance(w, (int, float)):
        return round(float(w), 6)
    if isinstance(w, dict):
        return {str(k): _gerundet(v) for k, v in sorted(w.items(), key=lambda kv: str(kv[0]))}
    if isinstance(w, (list, tuple)):
        return [_gerundet(v) for v in w]
    return type(w).__name__


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
    arten = db_kopie._pg_arten(pg_con.v if hasattr(pg_con, "v") else pg_con)
    for t in sorted(hier - dort):
        if sqlite_con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]:
            unterschiede.append(f"Tabelle {t} fehlt")
    for t in sorted(hier & dort):
        a = [r[1] for r in sqlite_con.execute(f'PRAGMA table_info("{t}")')]
        b = set(db_verbindung.spalten(pg_con, t))
        spalten = [s for s in a if s in b]
        liste = ", ".join(f'"{s}"' for s in spalten)
        art = [arten.get((t, s_)) for s_ in spalten]
        # SQLite-Seite so, wie sie nach PostgreSQL übernommen wird (Text in Zahlenspalten usw., db_kopie.wert_fuer_pg)
        za = [tuple(db_kopie.wert_fuer_pg(w, a_)[0] for w, a_ in zip(z, art))
              for z in sqlite_con.execute(f'SELECT {liste} FROM "{t}"')]
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
    kalk_alt = kalkulationen(db)
    db.schliessen()
    angepasst, verwaist = [], []
    try:
        ziel = Datenbank(pfad, verbindung=oeffnen(pfad))       # Tabellen wie im Programm anlegen
        try:
            quelle = sqlite3.connect(f"{pfad.resolve().as_uri()}?mode=ro", uri=True)
            try:
                db_kopie.sqlite_nach_pg(quelle, ziel.con, bericht=angepasst)
                unterschiede = vergleichen(quelle, ziel.con)
                verwaist = verwaiste(ziel.con)
                angebote = quelle.execute("SELECT COUNT(*) FROM angebote").fetchone()[0]
                tabellen = len(set(db_verbindung.tabellen(ziel.con)) - db_kopie.EIGENE)
                zeilen = {t: n for t, n in _anzahlen(quelle)}
            finally:
                quelle.close()
            kalk_neu = kalkulationen(ziel, list(kalk_alt))
            unterschiede += [f"Kalkulation Angebot {aid} weicht ab" for aid in kalk_alt
                             if kalk_alt[aid] != kalk_neu.get(aid)]
        finally:
            ziel.schliessen()
    except UmstellFehler:
        _pg_leeren(pfad)
        raise
    except Exception as e:      # noqa: BLE001 – nichts umgestellt, die Datendatei bleibt
        _pg_leeren(pfad)
        bericht = bericht_schreiben(pfad, dict(ok=False, fehler=str(e), angepasst=angepasst))
        raise UmstellFehler(f"Übernehmen nach PostgreSQL misslungen: {e}. Es wurde nicht umgestellt (Bericht: "
                            f"{bericht.name}).") from e
    if unterschiede:
        _pg_leeren(pfad)
        bericht = bericht_schreiben(pfad, dict(ok=False, unterschiede=unterschiede, angepasst=angepasst))
        raise UmstellFehler("Nach dem Übernehmen stimmen die Daten nicht überein (" + "; ".join(unterschiede[:5])
                            + f"). Es wurde nicht umgestellt (Bericht: {bericht.name}).")
    bericht = bericht_schreiben(pfad, dict(ok=True, zeilen=zeilen, angepasst=angepasst, verwaist=verwaist))
    archiv = _frei(pfad.parent / "Sicherung" / ARCHIV / f"{pfad.stem}_SQLite_{heute:%Y-%m-%d}.db")
    archiv.parent.mkdir(parents=True, exist_ok=True)
    merk = _merkdatei_schreiben(pfad, dict(art=POSTGRES, seit=datetime.datetime.now().isoformat(timespec="seconds"),
                                           archiv=str(archiv.relative_to(pfad.parent)), ordner="pg"))
    pfad.replace(archiv)
    merk.replace(pfad)
    for rest in (pfad.with_name(pfad.name + "-wal"), pfad.with_name(pfad.name + "-shm")):
        rest.unlink(missing_ok=True)
    return dict(sicherung=sicherung, archiv=archiv, tabellen=tabellen, angebote=angebote, bericht=bericht,
                angepasst=len(angepasst), verwaist=sum(n for _, n in verwaist), kalkulationen=len(kalk_alt))


def _anzahlen(quelle):
    from . import db_kopie
    out = []
    for (t,) in quelle.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                               "ORDER BY name"):
        if t not in db_kopie.EIGENE:
            out.append((t, quelle.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]))
    return out


def verwaiste(pg_con):
    """[(Text, Anzahl)] Zeilen, deren Fremdschlüssel ins Leere zeigt (in SQLite möglich, weil Fremdschlüssel dort
    lange aus waren). Sie werden übernommen wie sie sind und im Bericht genannt."""
    v = pg_con.v if hasattr(pg_con, "v") else pg_con
    out = []
    for kind, spalte, eltern, eltern_spalte in v.execute(
            "SELECT k.relname, a.attname, e.relname, ea.attname FROM pg_constraint c "
            "JOIN pg_class k ON k.oid = c.conrelid JOIN pg_class e ON e.oid = c.confrelid "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
            "JOIN pg_attribute ea ON ea.attrelid = c.confrelid AND ea.attnum = c.confkey[1] "
            "WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 1").fetchall():
        n = v.execute(f'SELECT COUNT(*) FROM "{kind}" k WHERE k."{spalte}" IS NOT NULL AND NOT EXISTS '
                      f'(SELECT 1 FROM "{eltern}" e WHERE e."{eltern_spalte}" = k."{spalte}")').fetchone()[0]
        if n:
            out.append((f"{kind}.{spalte} → {eltern}", n))
    return out


def bericht_schreiben(pfad, inhalt, heute=None):
    """Bericht der Umstellung als Textdatei im Ordner Sicherung (für den Hauptadmin und den Support)."""
    jetzt = datetime.datetime.now()
    ziel = _frei(Path(pfad).parent / "Sicherung" / f"Umstellung_PostgreSQL_{jetzt:%Y-%m-%d_%H%M%S}.txt")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    z = [f"Umstellung der Datendatei {Path(pfad).name} nach PostgreSQL am {jetzt:%d.%m.%Y %H:%M}",
         "Ergebnis: " + ("umgestellt" if inhalt.get("ok") else "NICHT umgestellt, die Datendatei bleibt"), ""]
    if inhalt.get("fehler"):
        z += ["Fehler: " + inhalt["fehler"], ""]
    if inhalt.get("unterschiede"):
        z += ["Unterschiede nach dem Übernehmen:"] + [f"  {u}" for u in inhalt["unterschiede"]] + [""]
    if inhalt.get("zeilen"):
        z += ["Übernommene Zeilen je Tabelle (alle verglichen):"]
        z += [f"  {t}: {n}" for t, n in sorted(inhalt["zeilen"].items()) if n]
        z.append("")
    ang = inhalt.get("angepasst") or []
    z.append(f"Angepasste Werte: {len(ang)}" + (" (Text in Zahlenfeldern usw.; der alte Wert steht hier und in der "
                                                  "Rückfall-Datei)" if ang else ""))
    z += [f"  {a['tabelle']} Zeile {a['zeile']}, {a['spalte']}: {a['alt']!r} → {a['neu']!r}" for a in ang[:2000]]
    if len(ang) > 2000:
        z.append(f"  … und {len(ang) - 2000} weitere")
    ver = inhalt.get("verwaist") or []
    z += ["", f"Verwaiste Zeilen (Verweis ins Leere, unverändert übernommen): {sum(n for _, n in ver)}"]
    z += [f"  {t}: {n}" for t, n in ver]
    ziel.write_text("\n".join(z) + "\n", encoding="utf-8")
    return ziel


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
    """Text für Dialoge: wo die Daten liegen."""
    m = merkdatei_lesen(db.pfad) or {}
    if getattr(db, "server", None) is not None:
        zeilen = status_zeilen(db)
        with contextlib.suppress(Exception):            # S3: wo die gemeinsamen Dateien liegen
            from . import teilen
            zeilen = [teilen.ablage_zustand(db)[2]] + list(zeilen)
        with contextlib.suppress(Exception):            # S4: wer rechnet lange Rechnungen
            from . import server_rechnen
            zeilen.insert(1, server_rechnen.status_text(db))
        with contextlib.suppress(Exception):            # S6: letzte Serversicherung und Rücksicherungsprobe
            from . import server_sicherung
            zeilen.insert(2, server_sicherung.status_text(db))
        return f"{TITEL[SERVER]}: {db.server.text()}" + ("\n\n" + "\n".join(zeilen) if zeilen else "")
    archiv = f"; alte SQLite-Datendatei archiviert: {m['archiv']}" if m.get("archiv") else ""
    konto = ""
    with contextlib.suppress(Exception):        # Prüflauf oder Server nicht erreichbar: ohne Angabe zum Konto
        zeile = db.con.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()
        konto = (f"; Programmkonto {zeile[0]}" + (" – ACHTUNG: mit Superuser-Rechten" if zeile[1] else
                                                  " ohne Superuser-Rechte"))
    kopf = (f"{TITEL[POSTGRES]} (Ordner {Path(db.pfad).parent / m.get('ordner', 'pg')}, seit "
            f"{m.get('seit', '–')[:16].replace('T', ' ')}){konto}{archiv}")
    zeilen = status_zeilen(db)
    return kopf + ("\n\n" + "\n".join(zeilen) if zeilen else "")


def status_werte(db):
    """Schritt 5 (Datenbank-Auftrag 19.11.2026): Zahlen für die Statusanzeige. Fehlt etwas (Server nicht erreichbar,
    Prüflauf), bleibt es leer."""
    from . import verbindung_waechter
    w = dict(verbindung=verbindung_waechter.zustand_text(db))
    abfragen = dict(
        version="SELECT current_setting('server_version')",
        groesse="SELECT pg_size_pretty(pg_database_size(current_database()))",
        verbindungen="SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()",
        wartende_sperren="SELECT count(*) FROM pg_locks WHERE NOT granted",
        lange_abfragen="SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'active' "
                       "AND now() - query_start > interval '5 seconds' AND pid <> pg_backend_pid()")
    for name, sql in abfragen.items():
        with contextlib.suppress(Exception):
            w[name] = db.con.execute(sql).fetchone()[0]
    v = getattr(db.con, "v", None)
    w["langsam"] = list(getattr(v, "langsam", ()) or ())[-5:]
    with contextlib.suppress(Exception):
        w["sicherung"] = letzte_sicherung(db)
    with contextlib.suppress(Exception):
        from . import pruef_wiederherstellung
        w["probe"] = pruef_wiederherstellung.text(db)
    return w


def letzte_sicherung(db):
    """(Zeit, Name, mit Abbild, mit Dokumenten) der neuesten Sicherung in allen Sicherungsordnern oder None."""
    from . import dokumente_sicherung, pg_abbild
    neueste = None
    for ordner in db.sicherungsordner():
        for p in Path(ordner).glob("*.db"):
            t = p.stat().st_mtime
            if neueste is None or t > neueste[0]:
                neueste = (t, p)
    if neueste is None:
        return None
    t, p = neueste
    return (datetime.datetime.fromtimestamp(t), p.name, pg_abbild.pfad(p).is_file(),
            dokumente_sicherung.listenpfad(p).is_file())


def status_zeilen(db):
    w = status_werte(db)
    z = [w["verbindung"]]
    if w.get("version"):
        z.append(f"PostgreSQL {w['version']}, Datenbank {w.get('groesse', '–')}, {w.get('verbindungen', '–')} "
                 f"Verbindungen, wartende Sperren {w.get('wartende_sperren', '–')}, laufende Abfragen über 5 s "
                 f"{w.get('lange_abfragen', '–')}")
    if w["langsam"]:
        z.append("Langsame Abfragen (ab 1 s): " + "; ".join(
            f"{time.strftime('%H:%M:%S', time.localtime(t))} {d:.1f} s {sql[:60]}" for t, d, sql in w["langsam"]))
    else:
        z.append("Langsame Abfragen (ab 1 s): keine")
    s = w.get("sicherung")
    if s:
        alter = (datetime.datetime.now() - s[0]).days
        z.append(f"Letzte Sicherung: {s[0]:%d.%m.%Y %H:%M} ({s[1]}; "
                 + " + ".join(t for t, da in (("Datendatei", True), ("PostgreSQL-Abbild", s[2]),
                                              ("Angebotsdokumente", s[3])) if da)
                 + ")" + (f" – ACHTUNG: {alter} Tage alt" if alter >= SICHERUNG_WARNEN_TAGE else ""))
    else:
        z.append("Letzte Sicherung: keine gefunden")
    if w.get("probe"):
        z.append(w["probe"])
    return z


SICHERUNG_WARNEN_TAGE = 3
