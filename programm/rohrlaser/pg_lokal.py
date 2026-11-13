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
BENUTZER = "rohrlaser"
DATENBANK = "rohrlaser"


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
    return subprocess.run(befehl, capture_output=True, text=True, **kw)


class LokalerServer:
    """Eingebetteter Server in daten_ordner/pg. starten() ist idempotent; zugang() liefert die Einstellung für
    db_verbindung.oeffnen()."""

    def __init__(self, daten_ordner, bin_ordner=None):
        self.daten = Path(daten_ordner)
        self.pg = self.daten / "pg"
        self.bin = Path(bin_ordner) if bin_ordner else programme()
        self._zugang_datei = self.daten / ZUGANG

    # -------- Zugang
    def _zugang_lesen(self):
        try:
            return json.loads(self._zugang_datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _zugang_schreiben(self, d):
        self.daten.mkdir(parents=True, exist_ok=True)
        tmp = self._zugang_datei.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(tmp, 0o600)
        os.replace(tmp, self._zugang_datei)

    def zugang(self):
        d = self._zugang_lesen() or {}
        return dict(art="postgres", host="127.0.0.1", port=d.get("port"), datenbank=DATENBANK, benutzer=BENUTZER,
                    sslmode="disable", anwendung="Rohrlaser-Kalkulation (Einzelplatz)")

    def passwort(self):
        return (self._zugang_lesen() or {}).get("passwort")

    # -------- Lebenszyklus
    @property
    def angelegt(self):
        return (self.pg / "PG_VERSION").exists()

    def anlegen(self):
        """Neuen Datenordner anlegen (nur wenn noch keiner da ist), Benutzer und Datenbank rohrlaser."""
        if self.angelegt:
            return
        self.daten.mkdir(parents=True, exist_ok=True)
        passwort = secrets.token_urlsafe(24)
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pw", encoding="utf-8") as f:
            f.write(passwort)
            pw_datei = f.name
        try:
            r = _lauf([str(self.bin / _exe("initdb")), "-D", str(self.pg), "-U", BENUTZER, "--pwfile", pw_datei,
                       "-A", "scram-sha-256", "-E", "UTF8", "--locale=C", "--no-instructions"])
        finally:
            os.unlink(pw_datei)
        if r.returncode != 0:
            raise RuntimeError(f"Datenordner für PostgreSQL ließ sich nicht anlegen: {r.stderr.strip()[:500]}")
        with open(self.pg / "postgresql.conf", "a", encoding="utf-8") as f:
            f.write("\n# Rohrlaser-Kalkulation Einzelplatz\nlisten_addresses = '127.0.0.1'\n"
                    "unix_socket_directories = ''\nmax_connections = 30\nshared_buffers = 128MB\n"
                    "fsync = on\nsynchronous_commit = on\nfull_page_writes = on\n")
        self._zugang_schreiben(dict(passwort=passwort, port=None))
        self.starten()
        import psycopg
        with psycopg.connect(host="127.0.0.1", port=self.zugang()["port"], user=BENUTZER, password=passwort,
                             dbname="postgres", autocommit=True) as con:
            con.execute(f'CREATE DATABASE "{DATENBANK}" ENCODING \'UTF8\' TEMPLATE template0')

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
        d["port"] = _freier_port()
        self._zugang_schreiben(d)
        log = self.daten / "pg_server.log"
        r = _lauf([str(self.bin / _exe("pg_ctl")), "start", "-w", "-t", str(int(warten_s)), "-D", str(self.pg),
                   "-l", str(log), "-o", f"-p {d['port']}"])
        if r.returncode != 0:
            raise RuntimeError("Eingebettete Datenbank startet nicht: "
                               + (r.stderr.strip() or _ende(log))[:800])
        ende = time.monotonic() + warten_s
        while time.monotonic() < ende:          # bereit, sobald der Port Verbindungen annimmt
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", d["port"]), timeout=1):
                return
            time.sleep(0.1)
        raise RuntimeError("Eingebettete Datenbank antwortet nicht.")

    def stoppen(self, art="fast"):
        if self.laeuft():
            _lauf([str(self.bin / _exe("pg_ctl")), "stop", "-w", "-m", art, "-D", str(self.pg)])


def _ende(pfad, zeichen=800):
    try:
        return Path(pfad).read_text(encoding="utf-8", errors="replace")[-zeichen:]
    except OSError:
        return ""
