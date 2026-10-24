"""Rohrlaser Angebotskalkulation als eigenständiges Windows-Programm."""
from pathlib import Path

VERSION = "0.9.94"
NAME = "Rohrlaser Angebotskalkulation"
URHEBER = "© 2026 Patrick Brundiers. Alle Rechte vorbehalten."


def lizenzbedingungen():
    """Text der Lizenzbedingungen (Lizenzbedingungen.txt neben diesem Paket, dieselbe Datei zeigt das Setup)."""
    return (Path(__file__).resolve().parent / "Lizenzbedingungen.txt").read_text(encoding="utf-8-sig")
