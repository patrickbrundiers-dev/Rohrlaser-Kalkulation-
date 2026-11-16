"""Virenprüfung der Anhänge mit dem Windows-Virenschutz (Anfragenverwaltung Paket 3, Freigabe Patrick 13.11.2026).

Microsoft Defender bringt das Befehlszeilenwerkzeug MpCmdRun.exe mit: „-Scan -ScanType 3 -File <Pfad>“ prüft eine
Datei oder einen Ordner samt Unterordnern. Rückgabewert 0 = nichts gefunden, 2 = Bedrohung gefunden, anderes =
Prüfung nicht möglich. „-DisableRemediation“: der Defender lässt die Datei liegen, das Programm sperrt sie selbst
(nichts wird gelöscht). Ohne Defender (anderer Virenschutz, kein Windows) bleibt eine Datei „nicht geprüft“.

Fehlalarm behoben (Patrick 16.11.2026 „alles wird als Virus erkannt“): MpCmdRun.exe gibt 2 auch zurück, wenn die
Prüfung selbst scheitert (z. B. Netzlaufwerk, OneDrive-Ordner, fehlende Rechte: „CmdTool: Failed with hr = …“).
Ein Fund zählt darum nur noch, wenn die Ausgabe eine Bedrohung nennt („found N threats“ mit N > 0, Liste der
Bedrohungen bzw. „Threat : Name“); alles andere bleibt „nicht geprüft“. Außerdem ist die Prüfung durch das Programm
seitdem nur noch auf Wunsch an (Einstellung EIN, Vorgabe aus): der Echtzeitschutz des Windows-Virenschutzes prüft
die Dateien ohnehin, sobald das Programm sie auspackt oder öffnet."""
import os
import re
import subprocess
import sys
from pathlib import Path

SAUBER, FUND, UNGEPRUEFT = "sauber", "fund", "ungeprueft"
TEXT = {SAUBER: "vom Virenschutz geprüft", FUND: "Virus gefunden: gesperrt", UNGEPRUEFT: "nicht geprüft"}
EIN = "anfrage_virenpruefung"           # Einstellung „ja“: Anhänge zusätzlich mit MpCmdRun.exe prüfen (Vorgabe nein)
FREIGEGEBEN = "freigegeben"             # Ergebnis im Verlauf: Sperre aufgehoben (Fehlalarm), Datei wieder nutzbar
_GEFUNDEN = re.compile(r"found\s+([0-9]+)\s+threat", re.I)
_LISTE = re.compile(r"LIST OF DETECTED THREATS|^\s*Threat\s*:\s*(\S.*)$", re.I | re.M)


def an(db):
    """True, wenn das Programm die Anhänge selbst mit dem Windows-Virenschutz prüfen soll (Einstellung, Vorgabe aus)."""
    try:
        return (db.einstellung(EIN) or "nein") == "ja"
    except Exception:                   # noqa: BLE001 – Einstellung nicht lesbar: nicht prüfen
        return False


def bedrohung(ausgabe):
    """Name der gemeldeten Bedrohung aus der Ausgabe von MpCmdRun.exe, "?" bei einer Bedrohung ohne Namen, sonst None
    (keine Bedrohung genannt: kein Fund, auch wenn der Rückgabewert 2 ist)."""
    t = ausgabe or ""
    n = [int(x) for x in _GEFUNDEN.findall(t)]
    treffer = [m.group(1) for m in _LISTE.finditer(t)]
    if any(n) or treffer:
        return next((x.strip() for x in treffer if x), "?")
    return None


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
    if r.returncode == 0:
        return SAUBER
    if r.returncode == 2 and bedrohung(f"{getattr(r, 'stdout', '') or ''}\n{getattr(r, 'stderr', '') or ''}"):
        return FUND
    return UNGEPRUEFT                   # Prüfung gescheitert (auch Rückgabewert 2 ohne genannte Bedrohung)


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
