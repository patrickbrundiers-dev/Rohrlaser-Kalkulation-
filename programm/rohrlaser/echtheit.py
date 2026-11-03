"""Eigene Programmdateien beim Start prüfen (Patrick 30.10.2026, Härtung „c“): Wer ein übersetztes Modul (z. B. die
Lizenzprüfung) gegen ein eigenes tauscht, soll nicht unbemerkt weiterarbeiten.

Grundlage ist die Dateiliste Update.json im Programmordner (Prüfsumme jeder Datei, update.py). Liegt die Signatur
Update.json.sig daneben, gilt die Liste nur mit gültiger Signatur des Update-Schlüssels (update_schluessel.py);
ältere Installationen haben noch keine Signatur, dann wird gegen die unsignierte Liste geprüft, bis das nächste
Update beide ablegt. Geprüft werden nur die eigenen Dateien (übersetzte Module rohrlaser.*/step_* und die beiden
Programme), nicht Qt, Python und die übrigen Bibliotheken – das hält den Start schnell.

Ergebnis von pruefen(): None = nicht prüfbar (Entwicklung ohne .exe, keine Dateiliste), '' = unverändert, sonst der
Befund als kurzer Text. lizenz.ermitteln macht daraus den Lesemodus (ab Stufe 2), nie eine Sperre der Daten.

Ohne Qt.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath

from . import update

PROGRAMME = ("Rohrlaser-Angebotskalkulation.exe", "STEP-Import/STEP-Import.exe")
MODUL_ENDUNGEN = (".pyd", ".so")
FREMD_ENDUNGEN = (".py", ".pyc", ".pyd", ".so")   # zusätzliche Dateien in _internal/rohrlaser: verdächtig
ORDNER_EIGEN = "_internal/rohrlaser"


def eigen(rel):
    """True für eigene Programmdateien der Dateiliste (Pfad mit /)."""
    p = PurePosixPath(rel)
    if rel in PROGRAMME:
        return True
    if p.suffix.lower() not in MODUL_ENDUNGEN:
        return False
    return "rohrlaser" in p.parts[:-1] or p.name.startswith("step_")


def _sha256(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _kurz(rel):
    return PurePosixPath(rel).name.split(".")[0]


def pruefen(ordner, schluessel=None):
    """Eigene Dateien im Programmordner gegen die Dateiliste prüfen. schluessel: öffentliche Update-Schlüssel
    (Vorgabe update_schluessel.py). Ergebnis siehe Modultext."""
    ordner = Path(ordner)
    try:
        daten = (ordner / update.DATEILISTE).read_bytes()
    except OSError:
        return None
    sig = ordner / update.SIGNATUR
    if sig.is_file():
        schluessel = update.update_schluessel() if schluessel is None else schluessel
        try:
            update.signatur_pruefen(daten, sig.read_bytes(), schluessel)
        except (update.UpdateFehler, OSError):
            return "Dateiliste Update.json verändert"
    try:
        dateien = json.loads(daten)["dateien"]
        eigene = {rel: d["sha256"] for rel, d in dateien.items() if eigen(rel)}
    except (ValueError, KeyError, TypeError, AttributeError):
        return "Dateiliste Update.json unlesbar"
    if not eigene:
        return "Dateiliste Update.json ohne eigene Programmdateien"
    befunde = []
    for rel, soll in sorted(eigene.items()):
        try:
            ist = _sha256(ordner / rel)
        except OSError:
            befunde.append(f"{_kurz(rel)} fehlt")
            continue
        if ist != str(soll).lower():
            befunde.append(f"{_kurz(rel)} geändert")
    gelistet = {rel.casefold() for rel in dateien}
    eigen_ordner = ordner / ORDNER_EIGEN
    if eigen_ordner.is_dir():
        for p in sorted(eigen_ordner.rglob("*")):
            rel = p.relative_to(ordner).as_posix()
            if p.is_file() and p.suffix.lower() in FREMD_ENDUNGEN and rel.casefold() not in gelistet:
                befunde.append(f"{p.name} fremd")
    if not befunde:
        return ""
    return ", ".join(befunde[:3]) + (f" und {len(befunde) - 3} weitere" if len(befunde) > 3 else "")
