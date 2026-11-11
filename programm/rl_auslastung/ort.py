"""Wo die Datenbank liegt. Vorgabe: Ordner „Daten“ neben dem Programm (als ZIP entpackt) bzw. im Benutzerordner
(aus dem Quelltext gestartet). Ein anderer Ort – z. B. ein gemeinsamer Ordner für mehrere Plätze – steht in der Datei
Auslastung.ini neben dem Programm (Zeile „datenbank = Pfad“); die Umgebungsvariable RLA_DATENBANK geht vor."""
import os
import sys
from pathlib import Path

INI, DATEI = "Auslastung.ini", "Auslastung.db"


def basis():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.home() / "Rohrlaser-Auslastung"


def ini_lesen(ordner=None):
    werte = {}
    try:
        for zeile in ((ordner or basis()) / INI).read_text(encoding="utf-8-sig").splitlines():
            if "=" in zeile and not zeile.lstrip().startswith(("#", ";")):
                k, _, v = zeile.partition("=")
                werte[k.strip().lower()] = v.strip()
    except OSError:
        pass
    return werte


def datenbank(ordner=None):
    """Pfad der Datenbankdatei."""
    if os.environ.get("RLA_DATENBANK"):
        return Path(os.environ["RLA_DATENBANK"])
    ordner = ordner or basis()
    pfad = ini_lesen(ordner).get("datenbank")
    if pfad:
        p = Path(pfad)
        return p if p.is_absolute() else ordner / p
    return ordner / "Daten" / DATEI


def datenbank_merken(pfad, ordner=None):
    """Anderen Ort in die Auslastung.ini schreiben (gilt ab sofort und beim nächsten Start)."""
    ordner = ordner or basis()
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / INI).write_text("# Rohrlaser Auslastung: Ort der Datenbank (auch ein gemeinsamer Ordner im Netz)\n"
                              f"datenbank = {pfad}\n", encoding="utf-8")
