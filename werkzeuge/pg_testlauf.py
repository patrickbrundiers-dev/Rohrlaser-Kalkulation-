"""Testskripte gegen PostgreSQL laufen lassen (Plan Datenbank-Modernisierung, Phase 3b Teil 2).

Startet einen eingebetteten PostgreSQL-Server in einem Zeitordner, setzt ROHRLASER_PG_TEST und ruft die genannten
Testskripte (Vorgabe: alle aus tests/alle.py) einzeln auf. Jede Datendatei eines Tests wird dabei eine eigene
PostgreSQL-Datenbank. Ergebnis: Liste grün/rot mit der ersten Fehlerzeile, optional als JSON.

Aufruf (nicht als root, initdb verweigert root):
  python werkzeuge/pg_testlauf.py [--json DATEI] [-j N] [test_a.py test_b.py …]
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parent
sys.path.insert(0, str(WURZEL / "programm"))
from rohrlaser import db_verbindung, pg_lokal  # noqa: E402


def alle_tests():
    sys.path.insert(0, str(WURZEL / "tests"))
    import alle
    return [t if isinstance(t, str) else t[0] for t in alle.TESTS]


def letzte_fehlerzeile(text):
    zeilen = [z.strip() for z in text.strip().splitlines() if z.strip()]
    for z in reversed(zeilen):
        if "Error" in z or "Fehler" in z or z.startswith("AssertionError"):
            return z[:300]
    return zeilen[-1][:300] if zeilen else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tests", nargs="*")
    ap.add_argument("--json")
    ap.add_argument("-j", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--zeit", type=int, default=900)
    a = ap.parse_args()
    tests = a.tests or alle_tests()
    tmp = Path(tempfile.mkdtemp(prefix="pg_testlauf_"))
    server = pg_lokal.LokalerServer(tmp / "Daten", pg_lokal.programme())
    server.starten()
    try:
        zugang = dict(server.zugang(), passwort=server.passwort())
        datei = tmp / "zugang.json"
        datei.write_text(json.dumps(zugang), encoding="utf-8")
        umg = dict(os.environ, **{db_verbindung.PG_TEST: str(datei)}, QT_QPA_PLATFORM="offscreen")

        def lauf(t):
            start = time.time()
            try:
                p = subprocess.run([sys.executable, str(WURZEL / "tests" / t)], cwd=WURZEL / "tests", env=umg,
                                   capture_output=True, text=True, timeout=a.zeit)
                ok, text = p.returncode == 0, p.stdout + p.stderr
            except subprocess.TimeoutExpired:
                ok, text = False, "Zeitlimit"
            return dict(test=t, ok=ok, s=round(time.time() - start, 1), fehler="" if ok else letzte_fehlerzeile(text))

        with concurrent.futures.ThreadPoolExecutor(a.j) as ex:
            ergebnisse = list(ex.map(lauf, tests))
    finally:
        server.stoppen()
    for e in ergebnisse:
        print(("OK    " if e["ok"] else "ROT   ") + f"{e['test']:45s} {e['fehler']}")
    gruen = sum(e["ok"] for e in ergebnisse)
    print(f"{gruen} von {len(ergebnisse)} Tests grün gegen PostgreSQL")
    if a.json:
        Path(a.json).write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if gruen == len(ergebnisse) else 1


if __name__ == "__main__":
    sys.exit(main())
