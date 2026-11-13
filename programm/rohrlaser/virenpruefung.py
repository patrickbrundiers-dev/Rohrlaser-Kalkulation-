"""Virenprüfung der Anhänge mit dem Windows-Virenschutz (Anfragenverwaltung Paket 3, Freigabe Patrick 13.11.2026).

Microsoft Defender bringt das Befehlszeilenwerkzeug MpCmdRun.exe mit: „-Scan -ScanType 3 -File <Pfad>“ prüft eine
Datei oder einen Ordner samt Unterordnern. Rückgabewert 0 = nichts gefunden, 2 = Bedrohung gefunden, anderes =
Prüfung nicht möglich. „-DisableRemediation“: der Defender lässt die Datei liegen, das Programm sperrt sie selbst
(nichts wird gelöscht). Ohne Defender (anderer Virenschutz, kein Windows) bleibt eine Datei „nicht geprüft“."""
import os
import subprocess
import sys
from pathlib import Path

SAUBER, FUND, UNGEPRUEFT = "sauber", "fund", "ungeprueft"
TEXT = {SAUBER: "vom Virenschutz geprüft", FUND: "Virus gefunden: gesperrt", UNGEPRUEFT: "nicht geprüft"}


def programm():
    """Pfad zu MpCmdRun.exe (neueste Plattform-Version zuerst) oder None."""
    if sys.platform != "win32":
        return None
    kandidaten = []
    daten = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows Defender" / "Platform"
    try:
        kandidaten += sorted(daten.glob("*/MpCmdRun.exe"), reverse=True)
    except OSError:
        pass
    kandidaten.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Windows Defender" / "MpCmdRun.exe")
    return next((p for p in kandidaten if p.is_file()), None)


def _lauf(exe, pfad, ausfuehren=None):
    befehl = [str(exe), "-Scan", "-ScanType", "3", "-File", str(pfad), "-DisableRemediation"]
    try:
        if ausfuehren:
            r = ausfuehren(befehl)
        else:
            r = subprocess.run(befehl, capture_output=True, text=True, timeout=300,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return UNGEPRUEFT
    return {0: SAUBER, 2: FUND}.get(r.returncode, UNGEPRUEFT)


def pruefen(pfade, exe=None, ausfuehren=None):
    """{Pfad: SAUBER|FUND|UNGEPRUEFT}. Erst alle zusammen (gemeinsamer Ordner bzw. eine Datei); nur bei einem Fund
    jede Datei einzeln, damit nur die betroffene gesperrt wird. ausfuehren(befehl) ersetzt subprocess.run (Tests)."""
    pfade = [Path(p) for p in pfade if Path(p).is_file()]
    if not pfade:
        return {}
    exe = exe or programm()
    if exe is None:
        return {p: UNGEPRUEFT for p in pfade}
    if len(pfade) == 1:
        return {pfade[0]: _lauf(exe, pfade[0], ausfuehren)}
    basis = Path(os.path.commonpath([str(p.parent) for p in pfade]))
    alle = _lauf(exe, basis, ausfuehren)
    if alle != FUND:
        return {p: alle for p in pfade}
    return {p: _lauf(exe, p, ausfuehren) for p in pfade}
