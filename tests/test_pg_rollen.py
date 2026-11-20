"""Rollen und Sicherheit der eingebetteten PostgreSQL-Datenbank (Datenbank-Auftrag 19.11.2026, Schritt 2).

Prüft mit echtem Server je Datenordner (ohne Prüflauf-Server):
- neue Installation: das Programm arbeitet als rohrlaser OHNE Superuser-Rechte (nur CREATEDB für die Probe der
  Wiederherstellung), Eigentümer der Datenbank; Wartung über eigenen Verwalter rohrlaser_admin;
- das Programmkonto darf keine Servereinstellungen ändern, keine Rollen anlegen, keine fremden Dateien lesen;
- keine Passwörter im Quellcode: zufällig je Installation, nur in Daten/pg_zugang.json (Windows: verschlüsselt,
  sonst nur für den eigenen Benutzer lesbar);
- Verbindungsprotokoll im Server-Log (log_connections/log_disconnections) mit Benutzer und Programm;
- ältere Datenordner (rohrlaser war Superuser): beim Start einmal umgestellt (rohrlaser wird Verwalter, das
  Programm meldet sich als rohrlaser_app an und besitzt alle Tabellen), Daten unverändert, danach
  nichts mehr zu tun; ein abgebrochener Umbau (neues Passwort schon gemerkt) wird beim nächsten Start beendet.
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme übersprungen.

Aufruf: python tests/test_pg_rollen.py
"""
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)      # hier geht es um den echten Server je Datenordner
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import datenspeicher, db_verbindung, pg_lokal, zugangsschutz  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK     " + text)


if hasattr(os, "getuid") and os.getuid() == 0:
    print("übersprungen: initdb läuft nicht als root")
    sys.exit(0)
try:
    pg_lokal.programme()
except pg_lokal.PgFehlt:
    print("übersprungen: keine PostgreSQL-Programme")
    sys.exit(0)

import psycopg  # noqa: E402

tmp = Path(tempfile.mkdtemp())
try:
    # ------------------------------------------------------------------ neue Installation
    pfad = tmp / "neu" / "Daten" / "rohrlaser.db"
    db = Datenbank(pfad)
    aid = db.angebot_neu(dict(kunde="Rollen GmbH"))
    s = datenspeicher.server(pfad)
    r = s.rechte()
    assert r == dict(rolsuper=False, rolcreatedb=True, rolcreaterole=False, rolreplication=False,
                     rolbypassrls=False), r
    assert db.con.execute("SELECT current_user").fetchone()[0] == pg_lokal.BENUTZER
    eigner = db.con.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()")
    assert eigner.fetchone()[0] == pg_lokal.BENUTZER
    with db.con:                                # Einzelrecht für Datenübernahme und Wiederherstellung (db_kopie)
        db.con.execute("SET LOCAL session_replication_role = replica")
    ok("neue Installation: Programm als rohrlaser_app ohne Superuser (nur CREATEDB und session_replication_role), "
       "Eigentümer der Datenbank")

    z = s.zugang()
    assert z["benutzer"] == pg_lokal.BENUTZER
    with psycopg.connect(host=z["host"], port=z["port"], user=pg_lokal.BENUTZER, password=s.passwort(),
                         dbname=pg_lokal.DATENBANK, autocommit=True) as con:
        for verboten in ("ALTER SYSTEM SET work_mem = '8MB'", "CREATE ROLE fremd LOGIN",
                         "SELECT pg_read_file('postgresql.conf')", "COPY angebote TO '/tmp/x.csv'"):
            try:
                con.execute(verboten)
                raise AssertionError(f"Programmkonto darf das nicht: {verboten}")
            except psycopg.errors.InsufficientPrivilege:
                pass
    with psycopg.connect(host=z["host"], port=z["port"], user=pg_lokal.VERWALTER, password=s.verwalter_passwort(),
                         dbname="postgres", autocommit=True) as con:
        assert con.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]
        werte = dict(con.execute("SELECT name, setting FROM pg_settings WHERE name IN ('log_connections', "
                                 "'log_disconnections')").fetchall())
        assert werte == dict(log_connections="on", log_disconnections="on"), werte
    ok("Programmkonto: keine Servereinstellungen, keine Rollen, keine Dateien; Verwalter getrennt; Verbindungen "
       "werden protokolliert")

    roh = json.loads((pfad.parent / pg_lokal.ZUGANG).read_text(encoding="utf-8"))
    assert set(roh) >= {"passwort", "admin_passwort"} and roh["passwort"] != roh["admin_passwort"]
    assert all(zugangsschutz.geschuetzt(roh[k]) for k in ("passwort", "admin_passwort"))
    if zugangsschutz.verfuegbar():
        assert s.passwort() not in json.dumps(roh), "Windows: Passwort nie im Klartext in der Datei"
    else:
        assert (pfad.parent / pg_lokal.ZUGANG).stat().st_mode & 0o077 == 0, "nur für den eigenen Benutzer lesbar"
    quellen = "".join(p.read_text(encoding="utf-8") for p in (HIER.parent / "programm" / "rohrlaser").glob("*.py"))
    assert s.passwort() not in quellen and s.verwalter_passwort() not in quellen
    ok("Passwörter zufällig je Installation, nur in der Zugangsdatei (geschützt), nie im Quellcode")

    db.schliessen()
    datenspeicher.alle_stoppen()
    log = (pfad.parent / "pg_server.log").read_text(encoding="utf-8", errors="replace")
    assert "connection authorized: user=rohrlaser_app database=rohrlaser" in log, log[-2000:]
    assert "Rohrlaser-Kalkulation" in log and "disconnection:" in log
    ok("Server-Log: jede Verbindung mit Benutzer, Datenbank und Programm, Abmeldungen mit Dauer")

    # ------------------------------------------------------------------ älterer Datenordner (rohrlaser war Superuser)
    alt = tmp / "alt" / "Daten" / "rohrlaser.db"
    alt.parent.mkdir(parents=True)
    server = pg_lokal.LokalerServer(alt.parent)
    pw = secrets.token_urlsafe(24)
    pw_datei = tmp / "pw.txt"
    pw_datei.write_text(pw, encoding="utf-8")
    r = pg_lokal._lauf([str(server.bin / pg_lokal._exe("initdb")), "-D", str(server.pg), "-U", pg_lokal.ALT_BENUTZER,
                        "--pwfile", str(pw_datei), "-A", "scram-sha-256", "-E", "UTF8", "--locale=C"])
    assert r.returncode == 0, r.stderr
    with open(server.pg / "postgresql.conf", "a", encoding="utf-8") as f:      # wie pg_lokal bis 0.9.407
        f.write("\nlisten_addresses = '127.0.0.1'\nunix_socket_directories = ''\nmax_connections = 30\n")
    (alt.parent / pg_lokal.ZUGANG).write_text(json.dumps(dict(passwort=pw, port=None)), encoding="utf-8")
    server.starten()
    with server._verbinden(pg_lokal.ALT_BENUTZER, pw) as con:
        con.execute(f'CREATE DATABASE "{pg_lokal.DATENBANK}"')
    d = Datenbank(alt, verbindung=db_verbindung.PostgresVerbindung(server.zugang(), pw))   # Stand 0.9.407
    a_alt = d.angebot_neu(dict(kunde="Vorher GmbH"))
    d.schliessen()
    server.stoppen()
    datenspeicher._merkdatei_schreiben(alt, dict(art=datenspeicher.POSTGRES, seit="2026-11-19T12:00:00",
                                                 ordner="pg")).replace(alt)

    zd = json.loads((alt.parent / pg_lokal.ZUGANG).read_text(encoding="utf-8"))
    zd["neu_passwort"] = gemerkt = secrets.token_urlsafe(24)     # wie nach einem Abbruch mitten im Umbau
    (alt.parent / pg_lokal.ZUGANG).write_text(json.dumps(zd), encoding="utf-8")
    d = Datenbank(alt)                           # nächster Start: umgestellt
    s2 = datenspeicher.server(alt)
    assert not s2.rechte()["rolsuper"] and s2.verwalter_passwort() == pw, "alter Superuser wird Verwalter"
    assert s2.zugang()["benutzer"] == pg_lokal.BENUTZER and s2.passwort() == gemerkt != pw
    assert d.con.execute("SELECT current_user").fetchone()[0] == pg_lokal.BENUTZER
    fremd = d.con.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner <> ?",
                          (pg_lokal.BENUTZER,)).fetchone()[0]
    assert fremd == 0, "alle Tabellen gehören dem Programmkonto"
    assert d.angebot(a_alt)["kunde"] == "Vorher GmbH"
    d.angebot_aendern(a_alt, "kunde", "Nachher GmbH")
    assert d.angebot(a_alt)["kunde"] == "Nachher GmbH"
    assert s2.rollen_pruefen() is False, "zweiter Lauf: nichts mehr zu tun"
    roh = json.loads((alt.parent / pg_lokal.ZUGANG).read_text(encoding="utf-8"))
    assert all(zugangsschutz.geschuetzt(roh[k]) for k in ("passwort", "admin_passwort"))
    d.schliessen()
    datenspeicher.alle_stoppen()
    ok("älterer Datenordner: rohrlaser wird Verwalter, Programm als rohrlaser_app (besitzt alle Tabellen), Daten "
       "unverändert, abgebrochener Umbau beendet, Zugangsdatei geschützt; zweiter Start ändert nichts")
finally:
    datenspeicher.alle_stoppen()
print("OK: Rollen und Sicherheit der Datenbank")
