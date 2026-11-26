"""Eingebetteter PostgreSQL-Server für den Einzelplatz (Plan Datenbank-Modernisierung 12.11.2026, F3a).

Am Einzelplatz gibt es keinen Datenbank-PC. Das Programm bringt die PostgreSQL-Programme mit (Ordner pgsql/ neben
dem Programm) und startet den Server selbst als normalen Benutzerprozess: keine Installation, keine Admin-Rechte,
nur auf 127.0.0.1 erreichbar. Der Datenordner liegt in Daten/pg, das Passwort wird beim ersten Start zufällig erzeugt
und in Daten/pg_zugang.json abgelegt (nur dieser Benutzer darf die Datei lesen). Beim Beenden fährt der Server
sauber herunter (pg_ctl stop -m fast: offene Transaktionen werden verworfen, Bestätigtes bleibt erhalten).

Die Programme werden gesucht in: Umgebungsvariable ROHRLASER_PG_BIN, pgsql/bin neben dem Programm, sonst die
üblichen Installationsordner (nur Entwicklung und Tests)."""
import contextlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ZUGANG = "pg_zugang.json"
# Rollen (Datenbank-Auftrag 19.11.2026, Schritt 2): das Programm arbeitet als rohrlaser_app OHNE Superuser-Rechte
# (Eigentümer der Datenbank); der Superuser ist nur für Einrichtung und Wartung da. Neue Datenordner: Superuser
# rohrlaser_admin; ältere (bis 0.9.407): rohrlaser war Superuser des Servers und bleibt es (der erste Benutzer eines
# Servers kann es nicht abgeben) – er wird zum Verwalter, das Programm bekommt rohrlaser_app.
BENUTZER = "rohrlaser_app"
VERWALTER = "rohrlaser_admin"
ALT_BENUTZER = "rohrlaser"
DATENBANK = "rohrlaser"
# Rechte des Programmkontos: CREATEDB braucht die Prüfung der Wiederherstellung (Probe-Datenbank), sonst nichts
PROGRAMM_RECHTE = "LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
# Einzelrecht statt Superuser: Datenübernahme und Wiederherstellung (db_kopie) schalten Trigger und Fremdschlüssel
# während des Kopierens mit session_replication_role ab (ab PostgreSQL 15 einzeln vergebbar)
EINZELRECHTE = ('GRANT SET ON PARAMETER session_replication_role TO "{neu}"',)
# Verbindungsprotokoll im Server-Log (Daten/pg_server.log): wer, von wo, mit welchem Programm
PROTOKOLL = dict(log_connections="on", log_disconnections="on", log_line_prefix="'%m [%p] %u@%d %a %h '")


class PgFehlt(RuntimeError):
    """Die PostgreSQL-Programme wurden nicht gefunden."""


def programme(start=None):
    """Ordner mit initdb, pg_ctl, pg_dump … oder PgFehlt."""
    kandidaten = []
    if os.environ.get("ROHRLASER_PG_BIN"):
        kandidaten.append(Path(os.environ["ROHRLASER_PG_BIN"]))
    basis = Path(start) if start else Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    kandidaten += [basis / "pgsql" / "bin", basis.parent / "pgsql" / "bin"]
    if os.name == "nt":
        kandidaten += sorted(Path(os.environ.get("ProgramFiles", "C:/Program Files")).glob("PostgreSQL/*/bin"), reverse=True)
    else:
        kandidaten += sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True)
        kandidaten += [Path("/usr/local/pgsql/bin"), Path("/usr/bin")]
    for k in kandidaten:
        if (k / _exe("pg_ctl")).exists() and (k / _exe("initdb")).exists():
            return k
    raise PgFehlt("PostgreSQL-Programme nicht gefunden (Ordner pgsql/bin fehlt im Programmordner).")


def _exe(name):
    return f"{name}.exe" if os.name == "nt" else name


def _freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _lauf(befehl, **kw):
    """Hilfsprogramm starten; unter Windows ohne Konsolenfenster."""
    if os.name == "nt":
        kw.setdefault("creationflags", 0x08000000)     # CREATE_NO_WINDOW
    if "stdout" not in kw:
        kw["capture_output"] = True
    kw.setdefault("timeout", 300)
    return subprocess.run(befehl, text=True, **kw)


def _windows_zugriff(ordner):
    """Windows: initdb startet sich als Administrator mit eingeschränktem Konto neu (Gruppe Administratoren nur noch
    „verweigern“). Ordner, die nur Administratoren oder nur dem Ersteller (tempfile.mkdtemp) gehören, kann es dann
    nicht lesen und den Datenordner nicht anlegen („File exists“, „could not change permissions“). Deshalb bekommt der
    angemeldete Benutzer selbst volle Rechte auf den Datenordner (vererbt). Ohne Windows oder bei Fehlern: nichts."""
    if os.name != "nt":
        return
    wer = os.environ.get("USERNAME")
    if not wer:
        return
    try:
        _lauf(["icacls", str(ordner), "/grant", f"{wer}:(OI)(CI)F", "/q"])
    except OSError:
        pass


def _langer_pfad(p):
    """Voller Pfad ohne Windows-Kurznamen (RUNNER~1 → runneradmin); initdb und pg_ctl scheitern sonst."""
    try:
        return p.resolve()
    except OSError:
        return p.absolute()


class LokalerServer:
    """Eingebetteter Server in daten_ordner/pg. starten() ist idempotent; zugang() liefert die Einstellung für
    db_verbindung.oeffnen()."""

    def __init__(self, daten_ordner, bin_ordner=None):
        self.daten = _langer_pfad(Path(daten_ordner))
        self.pg = self.daten / "pg"
        self.bin = Path(bin_ordner) if bin_ordner else programme()
        self._zugang_datei = self.daten / ZUGANG

    # -------- Zugang
    def _zugang_lesen(self):
        """Zugangsdatei mit Passwörtern im Klartext (im Speicher); in der Datei unter Windows verschlüsselt."""
        from . import zugangsschutz
        try:
            d = json.loads(self._zugang_datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        for k in ("passwort", "admin_passwort"):
            if k in d:
                d[k] = zugangsschutz.lesen(d[k])
        return d

    def _zugang_schreiben(self, d):
        from . import zugangsschutz
        self.daten.mkdir(parents=True, exist_ok=True)
        d = dict(d)
        for k in ("passwort", "admin_passwort"):
            if d.get(k) is not None:
                d[k] = zugangsschutz.schuetzen(d[k])
        tmp = self._zugang_datei.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(tmp, 0o600)
        os.replace(tmp, self._zugang_datei)

    def zugang(self):
        d = self._zugang_lesen() or {}
        return dict(art="postgres", host="127.0.0.1", port=d.get("port"), datenbank=DATENBANK,
                    benutzer=d.get("benutzer", ALT_BENUTZER),
                    sslmode="disable", anwendung="Rohrlaser-Kalkulation (Einzelplatz)")

    def passwort(self):
        return (self._zugang_lesen() or {}).get("passwort")

    def verwalter_zugang(self):
        """Zugang des Verwalters (Superuser) – nur für Einrichtung und Wartung, nie für das Programm."""
        d = self._zugang_lesen() or {}
        return dict(self.zugang(), benutzer=d.get("admin_benutzer", ALT_BENUTZER), datenbank="postgres",
                    anwendung="Rohrlaser-Kalkulation (Wartung)")

    def verwalter_passwort(self):
        return (self._zugang_lesen() or {}).get("admin_passwort")

    def _verbinden(self, benutzer, passwort, datenbank="postgres"):
        import psycopg
        return psycopg.connect(host="127.0.0.1", port=self.zugang()["port"], user=benutzer, password=passwort,
                               dbname=datenbank, autocommit=True, application_name="Rohrlaser-Kalkulation (Wartung)")

    # -------- Lebenszyklus
    @property
    def angelegt(self):
        return (self.pg / "PG_VERSION").exists()

    def anlegen(self):
        """Neuen Datenordner anlegen (nur wenn noch keiner da ist): Verwalter rohrlaser_admin (Superuser, nur Wartung),
        Programmkonto rohrlaser ohne Superuser-Rechte als Eigentümer der Datenbank rohrlaser. Beide Passwörter
        zufällig, nur in der Zugangsdatei (unter Windows verschlüsselt)."""
        if self.angelegt:
            return
        self.daten.mkdir(parents=True, exist_ok=True)
        _windows_zugriff(self.daten)
        verwalter = secrets.token_urlsafe(24)
        passwort = secrets.token_urlsafe(24)
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pw", encoding="utf-8") as f:
            f.write(verwalter)
            pw_datei = f.name
        try:
            r = _lauf([str(self.bin / _exe("initdb")), "-D", str(self.pg), "-U", VERWALTER, "--pwfile", pw_datei,
                       "-A", "scram-sha-256", "-E", "UTF8", "--locale=C", "--no-instructions"])
        finally:
            os.unlink(pw_datei)
        if r.returncode != 0:
            raise RuntimeError(f"Datenordner für PostgreSQL ließ sich nicht anlegen: {r.stderr.strip()[:500]}")
        with open(self.pg / "postgresql.conf", "a", encoding="utf-8") as f:
            f.write(self._konfiguration())
        self._nach_initdb()
        self._zugang_schreiben(dict(benutzer=BENUTZER, passwort=passwort, admin_benutzer=VERWALTER,
                                    admin_passwort=verwalter, port=None))
        self.starten()
        with self._verbinden(VERWALTER, verwalter) as con:
            con.execute(_mit_passwort(f'CREATE ROLE "{BENUTZER}" {PROGRAMM_RECHTE} PASSWORD {{}}', passwort))
            con.execute(f'CREATE DATABASE "{DATENBANK}" OWNER "{BENUTZER}" ENCODING \'UTF8\' TEMPLATE template0')
            for g in EINZELRECHTE:
                con.execute(g.replace("{neu}", BENUTZER))
        with self._verbinden(VERWALTER, verwalter, DATENBANK) as con:
            con.execute(f'ALTER SCHEMA public OWNER TO "{BENUTZER}"')

    def _konfiguration(self):
        """Zeilen für postgresql.conf beim Anlegen. Einzelplatz: nur 127.0.0.1, wenige Verbindungen. Der zentrale
        Server (server_betrieb.ZentralerServer) überschreibt das."""
        return ("\n# Rohrlaser-Kalkulation Einzelplatz\nlisten_addresses = '127.0.0.1'\n"
                "unix_socket_directories = ''\nmax_connections = 30\nshared_buffers = 128MB\n"
                "fsync = on\nsynchronous_commit = on\nfull_page_writes = on\n"
                + "".join(f"{k} = {v}\n" for k, v in PROTOKOLL.items()))

    def _nach_initdb(self):
        """Nach initdb, vor dem ersten Start (zentraler Server: Zertifikat, Zugangsregeln). Einzelplatz: nichts."""

    def _port_waehlen(self):
        """Port für den Start. Einzelplatz: jedes Mal ein freier Port (nur 127.0.0.1)."""
        return _freier_port()

    def rollen_pruefen(self):
        """Ältere Datenordner (bis 0.9.407): das Programm meldete sich als rohrlaser an, den Superuser des Servers.
        Einmalig: rohrlaser wird Verwalter (Passwort bleibt), neues Programmkonto rohrlaser_app ohne Superuser-Rechte
        mit eigenem Passwort wird Eigentümer der Datenbank und aller Tabellen, Folgen, Sichten und Funktionen; dazu
        Verbindungsprotokoll an. Erst wenn alles fertig ist, wechselt die Zugangsdatei auf das neue Konto (ein
        Abbruch wird beim nächsten Start einfach wiederholt). Liegt eine Zugangsdatei mit Klartext-Passwort vor (vor
        Schritt 2), wird sie geschützt neu geschrieben. Ergebnis: True, wenn umgestellt wurde."""
        from . import zugangsschutz
        try:
            roh = json.loads(self._zugang_datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            roh = {}
        d = self._zugang_lesen() or {}
        if not all(zugangsschutz.geschuetzt(roh.get(k)) for k in ("passwort", "admin_passwort", "neu_passwort")):
            self._zugang_schreiben(d)
        if d.get("benutzer", ALT_BENUTZER) == BENUTZER:
            return False
        verwalter, verwalter_pw = d.get("benutzer", ALT_BENUTZER), d.get("passwort")
        neu_pw = d.get("neu_passwort") or secrets.token_urlsafe(24)
        if not d.get("neu_passwort"):           # erst merken, dann anlegen: das Passwort geht nie verloren
            d = dict(d, neu_passwort=neu_pw)
            self._zugang_schreiben(d)
        with self._verbinden(verwalter, verwalter_pw) as con:
            da = con.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (BENUTZER,)).fetchone()
            con.execute(_mit_passwort(f'{"ALTER" if da else "CREATE"} ROLE "{BENUTZER}" {PROGRAMM_RECHTE} '
                                      'PASSWORD {}', neu_pw))
            con.execute(f'ALTER DATABASE "{DATENBANK}" OWNER TO "{BENUTZER}"')
            for g in EINZELRECHTE:
                con.execute(g.replace("{neu}", BENUTZER))
            for k, v in PROTOKOLL.items():
                con.execute(f"ALTER SYSTEM SET {k} = {v}")
            con.execute("SELECT pg_reload_conf()")
        with self._verbinden(verwalter, verwalter_pw, DATENBANK) as con:
            con.execute(EIGENTUEMER_WECHSELN.replace("{neu}", BENUTZER))
        self._zugang_schreiben(dict({k: v for k, v in d.items() if k != "neu_passwort"}, benutzer=BENUTZER,
                                    passwort=neu_pw, admin_benutzer=verwalter, admin_passwort=verwalter_pw))
        return True

    def rechte(self):
        """Rechte des Programmkontos (für Statusanzeige und Tests): dict rolsuper, rolcreatedb, rolcreaterole, …"""
        with self._verbinden(self.zugang()["benutzer"], self.passwort(), DATENBANK) as con:
            cur = con.execute("SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                              "FROM pg_roles WHERE rolname = current_user")
            werte = cur.fetchone()
            return dict(zip([c.name for c in cur.description], werte))

    def laeuft(self):
        if not self.angelegt:
            return False
        r = _lauf([str(self.bin / _exe("pg_ctl")), "status", "-D", str(self.pg)])
        return r.returncode == 0

    def starten(self, warten_s=30):
        if not self.angelegt:
            self.anlegen()
            return
        if self.laeuft():
            return
        d = self._zugang_lesen() or {}
        d["port"] = self._port_waehlen()
        self._zugang_schreiben(d)
        log = self.daten / "pg_server.log"
        # Ohne Pipes: der Server erbt sonst unter Windows die Ausgabe-Handles von pg_ctl, und das Warten auf das Ende
        # der Ausgabe hört nie auf (Programm hängt beim Start). Meldungen stehen im Server-Log.
        try:
            r = _lauf([str(self.bin / _exe("pg_ctl")), "start", "-w", "-t", str(int(warten_s)), "-D", str(self.pg),
                       "-l", str(log), "-o", f"-p {d['port']}"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, timeout=warten_s + 30)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Eingebettete Datenbank startet nicht (Zeit abgelaufen): " + _ende(log)) from None
        if r.returncode != 0:
            raise RuntimeError("Eingebettete Datenbank startet nicht: " + _ende(log))
        ende = time.monotonic() + warten_s
        while time.monotonic() < ende:          # bereit, sobald der Port Verbindungen annimmt
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", d["port"]), timeout=1):
                return
            time.sleep(0.1)
        raise RuntimeError("Eingebettete Datenbank antwortet nicht.")

    def stoppen(self, art="fast"):
        if self.laeuft():
            _lauf([str(self.bin / _exe("pg_ctl")), "stop", "-w", "-m", art, "-D", str(self.pg)])


# Alle Objekte im Schema public dem Programmkonto geben (REASSIGN OWNED geht beim ersten Benutzer des Servers nicht).
# Tabellen nehmen ihre Folgen (serial/identity) mit; freie Folgen, Sichten und Funktionen einzeln.
EIGENTUEMER_WECHSELN = """
DO $$
DECLARE r record;
BEGIN
  EXECUTE 'ALTER SCHEMA public OWNER TO "{neu}"';
  FOR r IN SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
             AND NOT (c.relkind = 'S' AND EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid
                                                  AND d.deptype IN ('a', 'i')))
  LOOP
    EXECUTE format(CASE r.relkind WHEN 'v' THEN 'ALTER VIEW public.%I OWNER TO "{neu}"'
                                  WHEN 'm' THEN 'ALTER MATERIALIZED VIEW public.%I OWNER TO "{neu}"'
                                  WHEN 'S' THEN 'ALTER SEQUENCE public.%I OWNER TO "{neu}"'
                                  ELSE 'ALTER TABLE public.%I OWNER TO "{neu}"' END, r.relname);
  END LOOP;
  FOR r IN SELECT p.oid::regprocedure AS f FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = 'public'
  LOOP
    EXECUTE format('ALTER ROUTINE %s OWNER TO "{neu}"', r.f);
  END LOOP;
END $$
"""


def _mit_passwort(befehl, passwort):
    """DDL mit Passwort als SQL-Literal (Rollenbefehle kennen keine Parameter); nie ins Protokoll."""
    from psycopg import sql
    return sql.SQL(befehl).format(sql.Literal(passwort))


def _ende(pfad, zeichen=800):
    try:
        return Path(pfad).read_text(encoding="utf-8", errors="replace")[-zeichen:]
    except OSError:
        return ""
