"""PostgreSQL-Abbild neben jeder Sicherung (Datenbank-Auftrag 19.11.2026, Schritt 4 „Sicherung“).

Jede Datenbank-Sicherung ist eine SQLite-Datei (lässt sich auf jedem PC lesen, prüfen und einlesen, auch ohne
PostgreSQL). Zusätzlich legt dieses Modul ein Abbild im eigenen Format von PostgreSQL daneben (pg_dump, gepackt):
<Sicherung>.pgdump. Es wird gleich nach dem Schreiben mit pg_restore --list geprüft (lesbar, alle Tabellen mit Daten).

Zurückholen aus einem Abbild: in eine Probe-Datenbank auf demselben Server einspielen (das Programmkonto darf
Datenbanken anlegen, Schritt 2), daraus eine SQLite-Datei schreiben und diese wie jede Sicherung einlesen
(Datenbank.wiederherstellen: geprüft, alter Stand vorher gesichert). So gibt es nur einen Weg zurück.

Ohne Qt. Fehlen pg_dump/pg_restore, bleibt die SQLite-Sicherung (Meldung im Protokoll).
"""
import os
import re
import secrets
import sqlite3
from pathlib import Path

from . import db_verbindung, pg_lokal

ENDUNG = ".pgdump"


class AbbildFehler(OSError):
    pass


def pfad(sicherung):
    return Path(sicherung).with_suffix(ENDUNG)


def _v(con):
    return con.v if hasattr(con, "v") else con


def _umgebung(v):
    pw = v._passwort() if callable(v._passwort) else v._passwort
    umg = dict(os.environ, PGPASSWORD=pw or "", PGAPPNAME="Rohrlaser-Kalkulation (Sicherung)", PGCONNECT_TIMEOUT="10")
    umg.pop("PGSERVICE", None)
    return umg


def _ziel(v, datenbank=None):
    z = v.zugang
    return ["-h", str(z.get("host", "127.0.0.1")), "-p", str(z.get("port", 5432)), "-U", str(z.get("benutzer")),
            "-d", datenbank or z.get("datenbank", "rohrlaser")]


def _programm(name):
    exe = pg_lokal.programme() / pg_lokal._exe(name)
    if not exe.exists():
        raise AbbildFehler(f"{name} fehlt im Programmordner (pgsql/bin)")
    return str(exe)


def tabellen_mit_daten(abbild):
    """Namen der Tabellen mit Daten im Abbild (pg_restore --list); AbbildFehler, wenn nicht lesbar."""
    r = pg_lokal._lauf([_programm("pg_restore"), "--list", str(abbild)])
    if r.returncode != 0:
        raise AbbildFehler(f"PostgreSQL-Abbild {Path(abbild).name} ist nicht lesbar: {r.stderr.strip()[:300]}")
    return {m.group(1) for m in re.finditer(r"TABLE DATA \S+ (\S+) ", r.stdout)}


def erstellen(con, sicherung):
    """Abbild der Datenbank hinter con neben die Sicherung schreiben und prüfen. Ergebnis: Pfad des Abbilds."""
    v = _v(con)
    ziel = pfad(sicherung)
    neu = ziel.with_name(ziel.name + ".neu")
    r = pg_lokal._lauf([_programm("pg_dump"), *_ziel(v), "-Fc", "-Z", "6", "--no-owner", "--no-privileges",
                        "-f", str(neu)], env=_umgebung(v), timeout=1800)
    if r.returncode != 0:
        neu.unlink(missing_ok=True)
        raise AbbildFehler(f"pg_dump: {r.stderr.strip()[:300]}")
    try:
        enthalten = tabellen_mit_daten(neu)
        fehlen = {t for t in v.tabellen() if t not in ("schema_stand",)} - enthalten
        if fehlen:
            raise AbbildFehler(f"PostgreSQL-Abbild unvollständig, es fehlen: {', '.join(sorted(fehlen)[:5])}")
    except BaseException:
        neu.unlink(missing_ok=True)
        raise
    os.replace(neu, ziel)
    return ziel


def nach_sqlite(con, abbild, ziel_datei):
    """Abbild in eine Probe-Datenbank auf dem Server hinter con einspielen und als SQLite-Datei ziel_datei schreiben
    (danach wie jede Sicherung einlesbar). Die Probe-Datenbank wird wieder gelöscht."""
    from . import db_kopie
    v = _v(con)
    name = f"abbild_{secrets.token_hex(4)}"
    v._roh(f'CREATE DATABASE "{name}"')
    try:
        r = pg_lokal._lauf([_programm("pg_restore"), *_ziel(v, name), "--no-owner", "--no-privileges",
                            "--exit-on-error", str(abbild)], env=_umgebung(v), timeout=1800)
        if r.returncode != 0:
            raise AbbildFehler(f"pg_restore: {r.stderr.strip()[:300]}")
        probe = db_verbindung.KompatVerbindung(db_verbindung.PostgresVerbindung(dict(v.zugang, datenbank=name),
                                                                                v._passwort))
        try:
            ziel = sqlite3.connect(ziel_datei)
            try:
                db_kopie.pg_nach_sqlite(probe, ziel)
            finally:
                ziel.close()
        finally:
            probe.close()
    finally:
        v._roh(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    return Path(ziel_datei)
