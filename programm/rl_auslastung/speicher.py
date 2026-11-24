"""Datenspeicher der Auslastung: SQLite-Datei (Standard, auch im gemeinsamen Ordner für mehrere Plätze) oder
eingebettetes PostgreSQL auf diesem PC (Plan Datenbank-Modernisierung, nach Phase 9; Patrick 14.11.2026).

Wie in der Kalkulation (rohrlaser.datenspeicher): Umstellen nur durch den Hauptadmin, vorher eine geprüfte
Sicherung, danach jede Tabelle Zeile für Zeile verglichen; die SQLite-Datei bleibt als
Auslastung_SQLite_bis_<Datum>.db liegen, an ihrer Stelle steht eine kleine Merkdatei. Der Server liegt im Ordner
Auslastung_PG neben der Datei (getrennt vom PostgreSQL der Kalkulation) und nimmt nur Verbindungen von diesem PC an.

PostgreSQL kann nicht in einem Netzordner von mehreren PCs geöffnet werden. Deshalb:
- liegt die Datenbank im Netz (\\\\Server\\… oder ein Netzlaufwerk), wird nicht umgestellt; mehrere Plätze teilen
  sich weiter die SQLite-Datei im gemeinsamen Ordner;
- die Merkdatei nennt den PC; ein anderer PC, der sie öffnet, bekommt eine klare Meldung statt eines zweiten Servers
  auf denselben Daten.
"""
import datetime
import os
import platform
import sqlite3
from pathlib import Path

from rohrlaser import datenspeicher as DS
from rohrlaser import db_verbindung as dv

ORDNER = "Auslastung_PG"
SQLITE, POSTGRES = DS.SQLITE, DS.POSTGRES
# PostgreSQL statt der zwei SQLite-Trigger aus Schritt 18: eindeutiger Index über die bereinigte Nummer. Der Name
# steht in der Fehlermeldung, wie bei SQLite „Auftragsnummer doppelt“.
NUMMER_INDEX = 'CREATE UNIQUE INDEX "Auftragsnummer doppelt" ON auftraege ((lower(trim(nummer))))'


class SpeicherFehler(RuntimeError):
    """Umstellen, Zurückstellen oder Öffnen nicht möglich; die Daten sind unverändert."""


def rechner():
    return (os.environ.get("COMPUTERNAME") or platform.node() or "").strip().lower()


def art(pfad):
    return DS.art(pfad)


# ------------------------------------------------------------------------------------------------ Öffnen
def verbindung(pfad, neu):
    """KompatVerbindung (sofort gültig wie sqlite3 mit isolation_level=None) zur Datenbank der Auslastung."""
    pfad = Path(pfad)
    if dv.pg_test_an():                         # Prüflauf aller Tests gegen PostgreSQL, nie im Programm
        v, _neu = dv.pg_test_oeffnen(pfad)
        return dv.KompatVerbindung(v, sofort=True)
    if not neu:
        m = DS.merkdatei_lesen(pfad)
        if m and m.get("art") == POSTGRES:
            wo = (m.get("rechner") or "").strip().lower()
            if wo and wo != rechner():
                raise SpeicherFehler(
                    f"Die Datenbank {pfad} liegt in PostgreSQL auf dem PC „{m.get('rechner')}“ und lässt sich nur dort "
                    "öffnen. Für mehrere Plätze bitte dort unter Einstellungen → Datenspeicher zurück auf die "
                    "SQLite-Datei stellen und diese in den gemeinsamen Ordner legen.")
            s = DS.server(pfad, unterordner=m.get("ordner") or ORDNER)
            return dv.KompatVerbindung(dv.PostgresVerbindung(s.zugang(), s.passwort()), sofort=True)
    return dv.KompatVerbindung(dv.SqliteVerbindung(pfad, warten=15, fremdschluessel=False), sofort=True)


def _anweisungen(skript):
    """SQL-Skript in einzelne Anweisungen (Texte in Anführungszeichen dürfen ; enthalten)."""
    out, teil = [], ""
    for zeile in skript.splitlines(keepends=True):
        for zeichen in zeile:
            teil += zeichen
            if zeichen == ";" and sqlite3.complete_statement(teil):
                if teil.strip(" \n\t;"):
                    out.append(teil.strip())
                teil = ""
    if teil.strip():
        out.append(teil.strip())
    return out


def schritt(con, skript, nummer):
    """Einen Schritt des Aufbaus ausführen und den Stand setzen (alles oder nichts)."""
    if dv.ist_sqlite(con):
        con.roh.executescript("BEGIN;" + skript + f"PRAGMA user_version = {int(nummer)};COMMIT;")
        return
    con.beginnen()
    try:
        for a in _anweisungen(skript):
            if a.upper().startswith("CREATE TRIGGER"):
                if "auftrag_nummer_neu" in a:
                    con.execute(NUMMER_INDEX)
                continue                         # auftrag_nummer_aendern: deckt derselbe Index ab
            con.execute(a)
        dv.schema_version_setzen(con, nummer)
        con.commit()
    except BaseException:
        con.rollback()
        raise


def sichern_pg(con, ziel):
    """Sicherung aus PostgreSQL als normale SQLite-Datei (lässt sich wie jede Auslastung.db öffnen)."""
    tmp = Path(ziel).with_name(Path(ziel).name + ".neu")
    tmp.unlink(missing_ok=True)
    z = sqlite3.connect(tmp)
    try:
        con.backup(z)
    finally:
        z.close()
    tmp.replace(ziel)
    return ziel


# ------------------------------------------------------------------------------------------------ Ort prüfen
def im_netz(pfad):
    """True, wenn die Datei in einem Netzordner liegt (dort teilen sich mehrere Plätze die SQLite-Datei)."""
    if str(pfad).startswith(("\\\\", "//")):
        return True
    p = str(Path(pfad).absolute())
    if p.startswith(("\\\\", "//")):
        return True
    if os.name == "nt" and len(p) > 1 and p[1] == ":":
        try:
            import ctypes
            return ctypes.windll.kernel32.GetDriveTypeW(p[:2] + "\\") == 4      # DRIVE_REMOTE
        except (AttributeError, OSError):
            return False
    return False


def umstellen_moeglich(db):
    """Leerer Text, wenn dieser Platz umstellen darf, sonst der Grund."""
    if db.postgres:
        return "Die Daten liegen schon in PostgreSQL auf diesem PC."
    if im_netz(db.pfad):
        return ("Die Datenbank liegt in einem Netzordner und wird von mehreren Plätzen gemeinsam genutzt. PostgreSQL "
                "gibt es nur je PC; im gemeinsamen Ordner bleibt die SQLite-Datei.")
    return ""


# ------------------------------------------------------------------------------------------------ Umstellen
def umstellen(db, bin_ordner=None, heute=None):
    """SQLite-Datei von db (offen) nach PostgreSQL auf diesem PC. Danach ist db geschlossen; das Fenster öffnet die
    Datenbank neu (daten.Daten(pfad)). Ergebnis: dict(sicherung, rueckfall, tabellen, auftraege, bericht, angepasst,
    verwaist). SpeicherFehler, wenn etwas nicht stimmt (dann bleibt alles wie vorher)."""
    from rohrlaser import db_kopie

    from . import daten
    grund = umstellen_moeglich(db)
    if grund:
        raise SpeicherFehler(grund)
    pfad = Path(db.pfad)
    heute = heute or datetime.date.today()
    try:
        sicherung = db.sichern(f"vor_PostgreSQL_{datetime.datetime.now():%H%M%S}")
        _pruefen(sicherung)
    except Exception as e:
        raise SpeicherFehler(f"Die Sicherung vor dem Umstellen ist nicht gelungen: {e}") from e
    try:
        s = DS.server(pfad, bin_ordner, unterordner=ORDNER)
    except Exception as e:
        raise SpeicherFehler(f"PostgreSQL lässt sich auf diesem PC nicht starten: {e}") from e
    pg = dv.PostgresVerbindung(s.zugang(), s.passwort())
    try:
        if any(t not in db_kopie.EIGENE for t in pg.tabellen()):
            raise SpeicherFehler(f"Im Ordner {s.daten} liegen schon Daten. Bitte den Ordner umbenennen und noch "
                                 "einmal umstellen.")
    finally:
        pg.schliessen()
    wer = db.wer
    db.schliessen()
    angepasst, verwaist = [], []
    try:
        con = dv.KompatVerbindung(dv.PostgresVerbindung(s.zugang(), s.passwort()), sofort=True)
        try:
            for nr in range(dv.schema_version(con), daten.SCHEMA):     # Tabellen wie im Programm anlegen
                schritt(con, daten.SCHRITTE[nr], nr + 1)
            quelle = sqlite3.connect(f"{pfad.resolve().as_uri()}?mode=ro", uri=True)
            try:
                db_kopie.sqlite_nach_pg(quelle, con, bericht=angepasst)
                unterschiede = DS.vergleichen(quelle, con)
                verwaist = DS.verwaiste(con)
                auftraege = quelle.execute("SELECT COUNT(*) FROM auftraege").fetchone()[0]
                tabellen = len(set(dv.tabellen(con)) - db_kopie.EIGENE)
                zeilen = dict(DS._anzahlen(quelle))
            finally:
                quelle.close()
        finally:
            con.close()
    except SpeicherFehler:
        _leeren(s)
        raise
    except Exception as e:      # noqa: BLE001 – nichts umgestellt, die Datei bleibt
        _leeren(s)
        bericht = DS.bericht_schreiben(pfad, dict(ok=False, fehler=str(e), angepasst=angepasst))
        raise SpeicherFehler(f"Übernehmen nach PostgreSQL misslungen: {e}. Es wurde nicht umgestellt (Bericht: "
                             f"{bericht.name}).") from e
    if unterschiede:
        _leeren(s)
        bericht = DS.bericht_schreiben(pfad, dict(ok=False, unterschiede=unterschiede, angepasst=angepasst))
        raise SpeicherFehler("Nach dem Übernehmen stimmen die Daten nicht überein (" + "; ".join(unterschiede[:5])
                             + f"). Es wurde nicht umgestellt (Bericht: {bericht.name}).")
    bericht = DS.bericht_schreiben(pfad, dict(ok=True, zeilen=zeilen, angepasst=angepasst, verwaist=verwaist))
    rueckfall = DS._frei(pfad.with_name(f"{pfad.stem}_SQLite_bis_{heute:%Y-%m-%d}.db"))
    merk = DS._merkdatei_schreiben(pfad, dict(art=POSTGRES, seit=datetime.datetime.now().isoformat(timespec="seconds"),
                                              rueckfall=rueckfall.name, ordner=ORDNER, rechner=rechner(), wer=wer))
    for nebendatei in (pfad.with_name(pfad.name + "-wal"), pfad.with_name(pfad.name + "-shm")):
        nebendatei.unlink(missing_ok=True)
    pfad.replace(rueckfall)
    merk.replace(pfad)
    return dict(sicherung=sicherung, rueckfall=rueckfall, tabellen=tabellen, auftraege=auftraege, bericht=bericht,
                angepasst=len(angepasst), verwaist=sum(n for _, n in verwaist))


def zurueck(db, heute=None):
    """PostgreSQL-Daten von db (offen) wieder in eine SQLite-Datei am alten Ort. Danach ist db geschlossen.
    Ergebnis: dict(sicherung, datei, auftraege)."""
    if not db.postgres:
        raise SpeicherFehler("Die Daten liegen schon in der SQLite-Datei.")
    pfad = Path(db.pfad)
    heute = heute or datetime.date.today()
    try:
        sicherung = db.sichern(f"vor_SQLite_{datetime.datetime.now():%H%M%S}")
        _pruefen(sicherung)
    except Exception as e:
        raise SpeicherFehler(f"Die Sicherung vor dem Zurückstellen ist nicht gelungen: {e}") from e
    neu = pfad.with_name(pfad.name + ".neu")
    neu.unlink(missing_ok=True)
    z = sqlite3.connect(neu)
    try:
        db.con.backup(z)
        z.execute(f"PRAGMA user_version = {int(dv.schema_version(db.con))}")
        z.commit()
        unterschiede = DS.vergleichen(z, db.con)
        auftraege = z.execute("SELECT COUNT(*) FROM auftraege").fetchone()[0]
    finally:
        z.close()
    if unterschiede:
        neu.unlink(missing_ok=True)
        raise SpeicherFehler("Die SQLite-Datei stimmt nicht mit PostgreSQL überein (" + "; ".join(unterschiede[:5])
                             + "). Es wurde nicht zurückgestellt.")
    _pruefen(neu)
    db.schliessen()
    merk_alt = DS._frei(pfad.with_name(f"{pfad.stem}_PostgreSQL_bis_{heute:%Y-%m-%d}.merk"))
    pfad.replace(merk_alt)
    neu.replace(pfad)
    return dict(sicherung=sicherung, datei=pfad, auftraege=auftraege)


def _pruefen(datei):
    """Sicherung/neue Datei lässt sich lesen und ist in sich in Ordnung."""
    c = sqlite3.connect(f"{Path(datei).resolve().as_uri()}?mode=ro", uri=True)
    try:
        if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SpeicherFehler(f"{Path(datei).name} ist beschädigt.")
        c.execute("SELECT COUNT(*) FROM auftraege").fetchone()
    finally:
        c.close()


def _leeren(s):
    try:
        v = dv.PostgresVerbindung(s.zugang(), s.passwort())
        try:
            v._roh("DROP SCHEMA public CASCADE")
            v._roh("CREATE SCHEMA public")
        finally:
            v.schliessen()
    except Exception:       # noqa: BLE001
        pass


def status(db):
    """Text für die Einstellungen: wo die Daten liegen."""
    if not db.postgres:
        return f"{DS.TITEL[SQLITE]}: {db.pfad}"
    m = DS.merkdatei_lesen(db.pfad) or {}
    return (f"{DS.TITEL[POSTGRES]} (Ordner {Path(db.pfad).parent / m.get('ordner', ORDNER)}, seit "
            f"{m.get('seit', '–')[:16].replace('T', ' ')}); Rückfall-Datei {m.get('rueckfall', '–')}")
