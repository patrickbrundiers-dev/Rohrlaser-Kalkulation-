"""Planungsserver starten: python -m planung [--port 8765] [--daten ORDNER] [--host 0.0.0.0]

Portabel: Die Daten liegen im Ordner 'Planungsdaten' neben dem Programm (bzw. neben diesem Paket in der
Entwicklung), Sicherungen in 'Planungsdaten/Sicherung' (beim Start und danach einmal je Tag). Keine Installation,
keine Admin-Rechte; damit andere PCs den Server erreichen, muss die Windows-Firewall den Port zulassen.
"""
import argparse
import socket
import sys
import threading
import time
from pathlib import Path

from . import NAME, VERSION
from .datenbank import Planungsdatenbank
from .server import starten


def daten_ordner():
    basis = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return basis / "Planungsdaten"


def selbsttest():
    """Für den Build: Datenbank in einem leeren Ordner anlegen, Server starten, Seite und Status abrufen."""
    import json
    import tempfile
    import urllib.request
    with tempfile.TemporaryDirectory() as t:
        db = Planungsdatenbank(Path(t) / "planung.db")
        srv = starten(db, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        basis = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            seite = urllib.request.urlopen(basis + "/", timeout=10).read().decode("utf-8")
            status = json.loads(urllib.request.urlopen(basis + "/api/status", timeout=10).read())
            assert "Maschinenplanung" in seite and "app.js" in seite, "Oberfläche fehlt"
            assert status["version"] == VERSION and status["eingerichtet"] is False, status
            assert urllib.request.urlopen(basis + "/app.js", timeout=10).status == 200
            assert [m["id"] for m in db.maschinen()] == ["T03", "T11", "LT7"]
        finally:
            srv.shutdown()
            srv.server_close()
            db.schliessen()
    print(f"Selbsttest OK ({NAME} {VERSION})")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="planung", description=NAME)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = von anderen PCs erreichbar, 127.0.0.1 = nur hier")
    p.add_argument("--daten", type=Path, default=None, help="Ordner der Planungsdaten")
    p.add_argument("--selbsttest", action="store_true", help="Server kurz in einem leeren Ordner starten und prüfen")
    a = p.parse_args(argv)
    if a.selbsttest:
        return selbsttest()
    ordner = a.daten or daten_ordner()
    db = Planungsdatenbank(ordner / "planung.db")
    db.sicherung_heute()

    def taeglich():
        while True:
            time.sleep(3600)
            try:
                db.sicherung_heute()
            except OSError as e:
                print(f"Sicherung fehlgeschlagen: {e}", flush=True)

    threading.Thread(target=taeglich, daemon=True).start()
    try:
        srv = starten(db, a.host, a.port)
    except OSError as e:
        print(f"Port {a.port} ist belegt oder nicht erlaubt: {e}")
        return 1
    print(f"{NAME} {VERSION}\nDaten: {ordner}\nIm Browser öffnen: http://{socket.gethostname()}:{a.port}/ "
          f"(auf diesem Rechner: http://localhost:{a.port}/)\nBeenden: Strg+C", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        db.schliessen()
    return 0


if __name__ == "__main__":
    sys.exit(main())
