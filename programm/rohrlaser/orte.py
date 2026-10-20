"""Wo das Programm seine Daten ablegt: portabel (neben dem Programm) oder installiert (im Benutzerprofil).

Beide Auslieferungen enthalten dieselben Programmdateien; der einzige Unterschied ist die Datei Portabel.ini im
ZIP. Liegt sie neben der .exe, ist das Programm portabel und die Daten liegen im Ordner 'Daten' daneben (oder
im Ordner aus 'daten = …' in der Portabel.ini, relativ zum Programmordner). Ohne Portabel.ini gilt:
- es gibt schon einen Ordner 'Daten' neben dem Programm: portabel (ZIP vor Version 0.4.0, per Update aktualisiert)
- Entwicklung (python -m rohrlaser): portabel, Daten in programm/Daten
- sonst installiert: Daten in %LOCALAPPDATA%\\Rohrlaser Angebotskalkulation\\Daten (nicht unter Dokumente, weil
  OneDrive diesen Ordner oft synchronisiert und eine offene SQLite-Datei das schlecht verträgt), PDF/CSV-Ablage in
  Dokumente\\Rohrlaser Angebote.

Sperre: Solange das Programm läuft, hält es eine Sperre auf der Datei 'rohrlaser.db.sperre' im Datenordner
(Betriebssystem-Sperre, verschwindet auch bei einem Absturz). Ein zweites Programm (z. B. die portable und die
installierte Version oder ein zweiter Rechner auf einem Netzlaufwerk) öffnet dieselbe Datendatei dann nicht.

Ohne Qt, damit Build und Tests es ohne Oberfläche benutzen können.
"""
import configparser
import datetime
import getpass
import json
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from . import VERSION

PORTABEL = "Portabel.ini"
DATEN = "Daten"
ABLAGE_PORTABEL = "Angebote"
ORDNER_INSTALLIERT = "Rohrlaser Angebotskalkulation"
ABLAGE_INSTALLIERT = "Rohrlaser Angebote"
DATENDATEI = "rohrlaser.db"
SPERRE = DATENDATEI + ".sperre"
_SPERR_STELLE = 1 << 20         # Windows: gesperrt wird ein Byte hinter dem Inhalt, der Inhalt bleibt lesbar


@dataclass
class Orte:
    programm: Path
    daten: Path          # Ordner mit rohrlaser.db und Sicherung
    ablage: Path         # Vorgabe für PDF/CSV, wenn in den Einstellungen kein Ablageordner steht
    portabel: bool
    grund: str           # warum diese Orte (für 'Über …' und Fehlermeldungen)

    @property
    def datei(self):
        return self.daten / DATENDATEI

    @property
    def art(self):
        return "portabel" if self.portabel else "installiert"


def ini_lesen(pfad):
    """Portabel.ini: Zeilen 'schluessel = wert', Kommentare mit # oder ;. Ergebnis: dict (Schlüssel klein)."""
    p = configparser.ConfigParser(interpolation=None)
    try:
        p.read_string("[portabel]\n" + Path(pfad).read_text(encoding="utf-8-sig"))
    except (OSError, configparser.Error):
        return {}
    return {k.lower(): v.strip() for k, v in p["portabel"].items()}


def lokaler_ordner(umgebung=None):
    umgebung = os.environ if umgebung is None else umgebung
    basis = umgebung.get("LOCALAPPDATA")
    return Path(basis) if basis else Path.home() / "AppData" / "Local"


def ermitteln(programmordner, daten=None, frozen=None, umgebung=None, dokumente=None):
    """Orte für den Programmordner. daten: Startparameter --daten (geht vor). dokumente: Ordner 'Dokumente' des
    Benutzers (aus Qt, beachtet umgeleitete Ordner), sonst ~/Documents."""
    programm = Path(programmordner)
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    ini = programm / PORTABEL
    if ini.is_file():
        werte = ini_lesen(ini)
        d = programm / (werte.get("daten") or DATEN)
        a = programm / werte["ablage"] if werte.get("ablage") else programm / ABLAGE_PORTABEL
        orte = Orte(programm, d, a, True, f"{PORTABEL} im Programmordner")
    elif (programm / DATEN).is_dir():
        orte = Orte(programm, programm / DATEN, programm / ABLAGE_PORTABEL, True,
                    "Ordner Daten neben dem Programm")
    elif not frozen:
        orte = Orte(programm, programm / DATEN, programm / ABLAGE_PORTABEL, True, "Entwicklung")
    else:
        dok = Path(dokumente) if dokumente else Path.home() / "Documents"
        orte = Orte(programm, lokaler_ordner(umgebung) / ORDNER_INSTALLIERT / DATEN, dok / ABLAGE_INSTALLIERT,
                    False, "installiert (Benutzerprofil)")
    if daten:
        orte.daten = Path(daten)
        orte.grund = "Startparameter --daten"
    return orte


# ------------------------------------------------------------------ Sperre
class Gesperrt(Exception):
    """Die Datendatei ist von einem anderen Programm geöffnet. info: Inhalt der Sperrdatei (dict, ggf. leer)."""

    def __init__(self, pfad, info):
        self.pfad, self.info = Path(pfad), info
        wer = ", ".join(f"{k} {v}" for k, v in (("Rechner", info.get("rechner")), ("Benutzer", info.get("benutzer")),
                                                 ("Version", info.get("version")), ("seit", info.get("seit"))) if v)
        super().__init__(f"Die Datendatei in {self.pfad.parent} ist schon in einem anderen Programm geöffnet"
                         + (f" ({wer})." if wer else "."))


def _sperren(f):
    f.seek(_SPERR_STELLE)
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl      # flock, nicht lockf: lockf-Sperren fallen beim Schließen jeder anderen Kopie der Datei
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _freigeben(f):
    try:
        f.seek(_SPERR_STELLE)
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def sperr_info(ordner):
    try:
        return json.loads((Path(ordner) / SPERRE).read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return {}


class Sperre:
    """Sperre auf den Datenordner, solange das Objekt lebt (freigeben() beim Beenden)."""

    def __init__(self, ordner):
        self.pfad = Path(ordner) / SPERRE
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.pfad, "a+b")
        try:
            _sperren(self.f)
        except OSError:
            self.f.close()
            self.f = None
            raise Gesperrt(self.pfad, sperr_info(ordner)) from None
        info = dict(rechner=socket.gethostname(), benutzer=_benutzer(), pid=os.getpid(), version=VERSION,
                    seit=datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))
        self.f.seek(0)
        self.f.truncate()
        self.f.write(json.dumps(info, ensure_ascii=False).encode("utf-8"))
        self.f.flush()

    def freigeben(self):
        if self.f is None:
            return
        _freigeben(self.f)
        self.f.close()
        self.f = None
        try:
            self.pfad.unlink()
        except OSError:         # ein anderes Programm hat sie gerade übernommen: bleibt
            pass


def _benutzer():
    try:
        return getpass.getuser()
    except Exception:
        return ""
