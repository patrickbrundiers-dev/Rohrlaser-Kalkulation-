"""Update: das laufende Programm gibt eigene offene ZIP-Dateien frei (Windows-Update-Test 19.11.2026).

psycopg fragt beim Laden seine Version über importlib.metadata ab; das hält jeden ZIP-Eintrag von sys.path offen,
im fertigen Programm _internal/base_library.zip. Unter Windows ließ sich die Datei dann beim Update nicht
verschieben („von einem anderen Prozess benutzt“). update.eigene_griffe_freigeben() schließt sie, einspielen() und
warten_bis_frei() rufen es auf. Geprüft über /proc (Linux); sonst übersprungen.

Aufruf: python tests/test_update_eigene_griffe.py
"""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

if not Path("/proc/self/fd").is_dir():
    print("übersprungen: ohne /proc")
    sys.exit(0)

tmp = Path(tempfile.mkdtemp())
archiv = tmp / "base_library.zip"
with zipfile.ZipFile(archiv, "w") as z:
    z.writestr("leer_modul.py", "x = 1\n")
sys.path.insert(0, str(archiv))


def offen():
    treffer = []
    for f in os.listdir("/proc/self/fd"):
        try:
            ziel = os.readlink(f"/proc/self/fd/{f}")
        except OSError:
            continue
        if ziel == str(archiv):
            treffer.append(ziel)
    return treffer


import importlib.metadata  # noqa: E402

importlib.metadata.version("psycopg")           # wie psycopg/version.py beim Laden
assert offen(), "Annahme des Tests: importlib.metadata hält die ZIP-Datei offen"
from rohrlaser import update  # noqa: E402

update.eigene_griffe_freigeben()
assert not offen(), "ZIP-Datei nach eigene_griffe_freigeben noch offen"
importlib.metadata.version("psycopg")
assert offen()
plan = dict(neu={}, weg=[])
update.warten_bis_frei(tmp, plan, sekunden=0)
assert not offen(), "warten_bis_frei gibt eigene Griffe frei"
print("OK     Update gibt eigene offene ZIP-Dateien frei (base_library.zip, importlib.metadata)")
print("OK: Update ohne eigene Sperren")
