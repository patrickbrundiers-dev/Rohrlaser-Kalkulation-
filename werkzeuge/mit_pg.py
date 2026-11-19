"""Befehl mit einem eingebetteten PostgreSQL-Prüfserver ausführen (SQLite entfernen, Patrick 19.11.2026).

Startet einen PostgreSQL-Server in einem Zeitordner, setzt ROHRLASER_PG_TEST (jede Datendatei eines Tests wird eine
eigene Datenbank auf diesem Server, db_verbindung.pg_test_oeffnen) und führt den Befehl aus. Danach wird der Server
gestoppt und der Ordner gelöscht. Für CI-Schritte, die Datenbanken anlegen (Testsuite, Abnahme, Anleitung).

Aufruf (nicht als root, initdb verweigert root):
  python werkzeuge/mit_pg.py -- python tests/alle.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import db_verbindung, pg_lokal  # noqa: E402


def main(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    if not argv:
        print(__doc__)
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="mit_pg_"))
    server = pg_lokal.LokalerServer(tmp / "Daten", pg_lokal.programme())
    server.anlegen()
    server.stoppen()
    with open(server.pg / "postgresql.conf", "a", encoding="utf-8") as f:     # viele Tests parallel
        f.write("\n# Prüfserver\nmax_connections = 400\nfsync = off\nsynchronous_commit = off\n")
    server.starten()
    try:
        datei = tmp / "zugang.json"
        datei.write_text(json.dumps(dict(server.zugang(), passwort=server.passwort())), encoding="utf-8")
        umg = dict(os.environ, **{db_verbindung.PG_TEST: str(datei)})
        return subprocess.run(argv, env=umg).returncode
    finally:
        server.stoppen()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
