"""Schnittstelle beim Beauftragen (Plan PROfirst-/LogiTRACE-Handbücher 12.11.2026, G5; Vorgabe aus).

Ist in den Einstellungen (Automatik und Prüfung → Schnittstelle beim Beauftragen) ein Programm oder Skript
eingetragen, schreibt das Programm beim Vorgang „Beauftragt“ den Fertigungsauftrag als JSON (fertigung.export, wie
„Export (JSON/CSV)“ im Reiter Fertigung) in den Angebotsordner und startet das Programm mit dem Pfad dieser Datei als
Parameter, z. B. für die Übergabe an ein PPS oder ERP. Das Programm wartet nicht darauf; ein Fehler beim Start wird
gemeldet und hält den Auftrag nicht auf. Leer = aus."""
import json
import shlex
import subprocess
from pathlib import Path

EINSTELLUNG = "auftrag_skript"


def befehl(db):
    """Eingetragenes Programm (mit eigenen Parametern) als Liste oder [] = aus."""
    t = str(db.einstellung(EINSTELLUNG) or "").strip()
    if not t:
        return []
    try:
        return shlex.split(t, posix=False)
    except ValueError:
        return [t]


def datei_schreiben(db, angebot_id, ordner):
    """Fertigungsauftrag als JSON in ordner; Ergebnis: Pfad."""
    from . import ausgabe, fertigung
    a = db.angebot(angebot_id) or {}
    daten = fertigung.export(db, angebot_id, a.get("ergebnis"))
    ziel = Path(ordner) / (ausgabe.dateiname(a, "Auftrag") + ".json")
    ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    return ziel


def starten(db, angebot_id, ordner, popen=None):
    """Datei schreiben und Programm starten. Ergebnis: (Pfad der Datei oder None, Meldung oder '')."""
    cmd = befehl(db)
    if not cmd:
        return None, ""
    try:
        ziel = datei_schreiben(db, angebot_id, ordner)
        (popen or subprocess.Popen)([c.strip('"') for c in cmd] + [str(ziel)])
    except Exception as e:          # Schnittstelle hält den Auftrag nie auf
        return None, f"Schnittstelle beim Beauftragen: Start nicht möglich ({e})."
    return ziel, f"Schnittstelle beim Beauftragen: {Path(cmd[0].strip(chr(34))).name} mit {ziel.name} gestartet."
