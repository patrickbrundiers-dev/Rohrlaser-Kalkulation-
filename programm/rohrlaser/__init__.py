"""Rohrlaser Angebotskalkulation als eigenständiges Windows-Programm."""
import importlib.machinery
import importlib.util
from pathlib import Path

VERSION = "0.9.227"
NAME = "Rohrlaser Angebotskalkulation"
URHEBER = "© 2026 Patrick Brundiers. Alle Rechte vorbehalten."
_HIER = Path(__file__).resolve().parent
# übersetzt ausgeliefert (programm/kompilieren.py): Qt-Slots brauchen dann eine Python-Hülle (qt_slots.py)
UEBERSETZT = any((_HIER / ("qt_slots" + e)).is_file() for e in importlib.machinery.EXTENSION_SUFFIXES)


def lizenzbedingungen():
    """Text der Lizenzbedingungen (Lizenzbedingungen.txt neben diesem Paket, dieselbe Datei zeigt das Setup)."""
    return (_HIER / "Lizenzbedingungen.txt").read_text(encoding="utf-8-sig")


if UEBERSETZT and importlib.util.find_spec("PySide6") is not None:
    from . import qt_slots
    qt_slots.einschalten()
