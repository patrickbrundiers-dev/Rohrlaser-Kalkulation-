"""Einrichtungs-Assistent für den zentralen Server (Server-Setup, Patrick 27.11.2026).

Statt rund zehn Befehlen in der Eingabeaufforderung (IT-Handbuch Kapitel 5) fragt der Assistent die Angaben auf
wenigen Seiten ab und führt die Schritte der Reihe nach aus:

  Voraussetzungen prüfen → Server anlegen (Datenbank, Zertifikate, 1. Administrator, Zugangsdatei) → Firewall-Regel
  → Freigabe der Ablage (SMB + NTFS-Rechte) → Ablage eintragen → zweites Sicherungsziel → Aufgabenplanung
  (Start, Rechner-Dienst, Sicherung mit Nachholen) → erste Sicherung mit Probe → Zustand anzeigen.

Jeder Server-Schritt ruft genau den Befehl aus server_betrieb.main auf, den die IT auch von Hand eingeben würde;
der Assistent ist also nur eine Oberfläche dafür. Ein schon eingerichteter Server bleibt unverändert (einrichten
startet ihn nur), der Assistent darf also erneut laufen, z. B. für ein neues Dienstkonto-Passwort.
Windows-Schritte (Firewall, Freigabe) laufen per PowerShell und nur unter Windows; anderswo werden sie übersprungen.

Aufruf: Rohrlaser-Angebotskalkulation.exe --server-assistent            (Fenster)
        Rohrlaser-Angebotskalkulation.exe --server-assistent ANTWORTEN.json   (ohne Fenster, für Skripte)
Das Protokoll steht danach in <Server-Ordner>/Einrichtung.txt.
"""
import datetime
import json
import os
import re
import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import server_betrieb as sb
from . import server_sicherung as ss

PROTOKOLL = "Einrichtung.txt"
MERKER = "Server-Ordner.txt"       # neben der .exe, liest das Server-Setup (programm/installer/server.iss)
FREIGABE_NAME = "Rohrlaser-Ablage"
GRUPPE_VORGABE = "GG-Rohrlaser-Benutzer"
FIREWALL_REGEL = "Rohrlaser PostgreSQL"
FREI_GB_MIN = 20            # weniger freier Platz auf dem Laufwerk des Server-Ordners: Warnung
KUERZEL = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,7}$")


class AssistentFehler(Exception):
    pass


@dataclass
class Angaben:
    ordner: str = ""                                     # Vorschlag: <Systemlaufwerk>\RohrlaserServer
    firma: str = ""
    admin: str = ""
    admin_name: str = ""
    admin_passwort: str = field(default="", repr=False)
    adressen: list = field(default_factory=list)        # DNS-Name und feste IP des Servers
    port: int = sb.PORT
    firewall: bool = True
    firewall_quelle: str = "LocalSubnet"                 # oder z. B. 192.168.1.0/24
    freigabe: bool = True
    freigabe_name: str = FREIGABE_NAME
    gruppe: str = GRUPPE_VORGABE
    ablage_pfad: str = ""                                # leer: \\<Name>\<Freigabe>
    nas: str = ""                                        # zweites Sicherungsziel, leer = keins
    uhrzeiten: str = ss.UHRZEITEN
    konto: str = ""                                      # leer: angemeldetes Konto
    konto_passwort: str = field(default="", repr=False)
    erste_sicherung: bool = True

    def ohne_geheimnisse(self):
        d = asdict(self)
        d.pop("admin_passwort")
        d.pop("konto_passwort")
        return d


def vorschlag():
    """Angaben mit Vorgaben aus diesem Rechner: Rechnername und IP, Laufwerk D: wenn vorhanden, angemeldetes Konto."""
    a = Angaben()
    name = socket.gethostname()
    adressen = [name]
    try:
        ip = socket.gethostbyname(name)
        if ip and not ip.startswith("127."):
            adressen.append(ip)
    except OSError:
        pass
    a.adressen = adressen
    if os.name == "nt":     # Laufwerk der Daten wählt die IT im Assistenten (IT-Handbuch: eigenes Datenlaufwerk)
        a.ordner = os.environ.get("SystemDrive", "C:") + "\\RohrlaserServer"
    else:
        a.ordner = str(Path.home() / "RohrlaserServer")
    a.konto = ss.konto_vorgabe()
    return a


def ablage_unc(a):
    return a.ablage_pfad.strip() or f"\\\\{(a.adressen or [socket.gethostname()])[0]}\\{a.freigabe_name}"


def pruefen(a):
    """Fehler in den Angaben als Liste von Texten (leer = alles gut)."""
    f = []
    if not a.ordner.strip() or not (Path(a.ordner).is_absolute() or re.match(r"^[A-Za-z]:\\", a.ordner)):
        f.append("Server-Ordner: bitte einen vollständigen Pfad angeben, z. B. D:\\RohrlaserServer.")
    if not KUERZEL.match(a.admin or ""):
        f.append("Administrator: Kürzel mit 1 bis 8 Buchstaben/Ziffern, beginnt mit einem Buchstaben.")
    if len(a.admin_passwort or "") < 8:
        f.append("Administrator: Passwort mit mindestens 8 Zeichen.")
    if not a.firma.strip():
        f.append("Firmenname fehlt (steht in der Zugangsdatei und im Programm).")
    if not a.adressen:
        f.append("Mindestens eine Adresse des Servers angeben (DNS-Name, feste IP).")
    for x in a.adressen:
        if not re.match(r"^[A-Za-z0-9.\-:]+$", x):
            f.append(f"Adresse „{x}“: nur Buchstaben, Ziffern, Punkt, Minus, Doppelpunkt.")
    if not 1 <= int(a.port) <= 65535:
        f.append("Port zwischen 1 und 65535.")
    if a.freigabe and not re.match(r"^[A-Za-z0-9_\-$]{1,80}$", a.freigabe_name or ""):
        f.append("Name der Freigabe: Buchstaben, Ziffern, _ und - (z. B. Rohrlaser-Ablage).")
    if a.nas and not (a.nas.startswith("\\\\") or Path(a.nas).is_absolute()):
        f.append("Zweites Sicherungsziel: vollständiger Pfad, z. B. \\\\NAS\\Backup\\Rohrlaser.")
    try:
        ss._uhrzeiten(a.uhrzeiten)
    except ss.SicherungFehler as e:
        f.append(f"Sicherungszeiten: {e}")
    if os.name == "nt" and not a.konto_passwort:
        f.append("Windows-Passwort des Dienstkontos fehlt (die Aufgaben laufen auch ohne Anmeldung).")
    return f


def ps_text(s):
    """Text als PowerShell-Zeichenkette in einfachen Anführungszeichen."""
    return "'" + str(s).replace("'", "''") + "'"


def ist_admin():
    if os.name != "nt":
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:       # noqa: BLE001
        return False


@dataclass
class Schritt:
    titel: str
    art: str                    # "server" (server_betrieb.main), "windows" (PowerShell), "pruefen"
    befehl: list
    pflicht: bool = True        # misslingt ein Pflichtschritt, hört der Assistent auf


def schritte(a):
    """Die Schritte für die Angaben a, in der Reihenfolge des IT-Handbuchs (Kapitel 3 bis 5)."""
    o = ["--ordner", a.ordner, "--port", str(a.port)]
    ablage = a.ordner.rstrip("\\/") + ("\\" if "\\" in a.ordner else "/") + sb.ABLAGE_ORDNER
    s = [Schritt("Voraussetzungen prüfen", "pruefen", [])]
    s.append(Schritt("Server anlegen (Datenbank, Zertifikate, Administrator, Zugangsdatei)", "server",
                     ["einrichten", *o, "--admin", a.admin, "--name", a.firma, "--adresse", *a.adressen]))
    if a.firewall:
        s.append(Schritt(f"Firewall: TCP {a.port} eingehend aus {a.firewall_quelle}", "windows", [
            f"Get-NetFirewallRule -DisplayName {ps_text(FIREWALL_REGEL)} -ErrorAction SilentlyContinue | "
            "Remove-NetFirewallRule; "
            f"New-NetFirewallRule -DisplayName {ps_text(FIREWALL_REGEL)} -Direction Inbound -Protocol TCP "
            f"-LocalPort {int(a.port)} -RemoteAddress {ps_text(a.firewall_quelle)} -Action Allow "
            "-Profile Domain,Private | Out-Null"], pflicht=False))
    if a.freigabe:
        konto = a.konto or ss.konto_vorgabe()
        s.append(Schritt(f"Freigabe {a.freigabe_name} für {a.gruppe or 'die Mitarbeiter'}", "windows", [
            f"$p = {ps_text(ablage)}; New-Item -ItemType Directory -Force -Path $p | Out-Null; "
            f"if (-not (Get-SmbShare -Name {ps_text(a.freigabe_name)} -ErrorAction SilentlyContinue)) {{ "
            f"New-SmbShare -Name {ps_text(a.freigabe_name)} -Path $p -FullAccess {ps_text(konto)}"
            + (f" -ChangeAccess {ps_text(a.gruppe)}" if a.gruppe else "") + " -CachingMode None | Out-Null }; "
            + (f"icacls $p /grant {ps_text(a.gruppe + ':(OI)(CI)M')} | Out-Null; " if a.gruppe else "")
            + f"icacls $p /grant {ps_text(konto + ':(OI)(CI)F')} | Out-Null; "
            "if ($LASTEXITCODE -ne 0) { throw 'icacls fehlgeschlagen' }"]))
        s.append(Schritt("Ablage für die Arbeitsplätze eintragen", "server", ["ablage", *o, "--pfad", ablage_unc(a)]))
    elif a.ablage_pfad:
        s.append(Schritt("Ablage für die Arbeitsplätze eintragen", "server", ["ablage", *o, "--pfad", a.ablage_pfad]))
    if a.nas:
        s.append(Schritt("Zweites Sicherungsziel eintragen", "server", ["sicherungsziel", *o, "--pfad", a.nas]))
    auf = ["aufgaben", *o, "--uhrzeit", a.uhrzeiten]
    if a.konto:
        auf += ["--konto", a.konto]
    s.append(Schritt("Aufgabenplanung: Start, Rechner-Dienst, Sicherung", "server", auf))
    if a.erste_sicherung:
        s.append(Schritt("Erste Sicherung mit Rücksicherungsprobe", "server", ["sichern", *o, "--anlass",
                                                                               "Einrichtung"]))
    s.append(Schritt("Zustand prüfen", "server", ["status", *o]))
    return s


def voraussetzungen(a):
    """(Fehler, Warnungen) vor dem Einrichten."""
    fehler, warn = list(pruefen(a)), []
    if not ist_admin():
        fehler.append("Bitte als Administrator ausführen (Rechtsklick → Als Administrator ausführen).")
    try:
        basis = Path(a.ordner)
        while not basis.exists() and basis.parent != basis:
            basis = basis.parent
        frei = shutil.disk_usage(basis).free / 1e9
        if frei < FREI_GB_MIN:
            warn.append(f"Nur {frei:.0f} GB frei auf dem Laufwerk des Server-Ordners (empfohlen ab 250 GB).")
    except OSError as e:
        fehler.append(f"Laufwerk des Server-Ordners nicht erreichbar: {e}")
    if not (Path(a.ordner) / "pg").exists():
        with socket.socket() as s:
            try:
                s.bind(("0.0.0.0", int(a.port)))
            except OSError:
                fehler.append(f"Port {a.port} ist schon belegt (läuft hier ein anderes PostgreSQL?).")
    return fehler, warn


def _powershell(befehl):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                        "$ErrorActionPreference = 'Stop'; " + befehl], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise AssistentFehler((r.stderr or r.stdout).strip()[:500] or f"Rückgabewert {r.returncode}")
    return r.stdout.strip()


def ausfuehren(a, melden=print, fortschritt=None, windows=None):
    """Alle Schritte ausführen. melden(text): Zeilen fürs Protokoll; fortschritt(nr, anzahl, titel, zustand) mit
    zustand "läuft", "gut", "Warnung", "übersprungen", "Fehler". windows(befehl): PowerShell (Vorgabe: echt unter
    Windows, sonst übersprungen). Ergebnis: dict(gut, zugang, fingerabdruck, ablage, warnungen, protokoll)."""
    liste = schritte(a)
    zeilen, warnungen = [], []

    def m(t):
        zeilen.append(t)
        melden(t)

    def stand(nr, titel, zustand):
        if fortschritt:
            fortschritt(nr, len(liste), titel, zustand)

    if windows is None and os.name == "nt":
        windows = _powershell
    m(f"Einrichtung des Rohrlaser-Servers, {datetime.datetime.now():%d.%m.%Y %H:%M}")
    m("Angaben: " + json.dumps(a.ohne_geheimnisse(), ensure_ascii=False))

    def eingabe(frage):
        return a.konto_passwort if frage.startswith("Windows-Passwort") else a.admin_passwort
    gut = True
    for nr, sch in enumerate(liste, 1):
        stand(nr, sch.titel, "läuft")
        m(f"\n[{nr}/{len(liste)}] {sch.titel}")
        try:
            if sch.art == "pruefen":
                fehler, warn = voraussetzungen(a)
                for w in warn:
                    m("  Warnung: " + w)
                warnungen += warn
                if fehler:
                    raise AssistentFehler("\n".join(fehler))
            elif sch.art == "windows":
                if windows is None:
                    m("  übersprungen (nur unter Windows)")
                    stand(nr, sch.titel, "übersprungen")
                    continue
                aus = windows(sch.befehl[0])
                if aus:
                    m("  " + aus)
            else:
                code = sb.main(sch.befehl, eingabe=eingabe, ausgabe=lambda t: m("  " + str(t)))
                if code:
                    raise AssistentFehler(f"Befehl {sch.befehl[0]} meldet Rückgabewert {code}")
            stand(nr, sch.titel, "gut")
        except Exception as e:      # noqa: BLE001 - jeder Fehler gehört ins Protokoll
            m(f"  FEHLER: {e}")
            if sch.pflicht:
                stand(nr, sch.titel, "Fehler")
                gut = False
                break
            warnungen.append(f"{sch.titel}: {e}")
            stand(nr, sch.titel, "Warnung")
    erg = dict(gut=gut, warnungen=warnungen, zugang=None, fingerabdruck=None, ablage=ablage_unc(a))
    s = sb.ZentralerServer(a.ordner, port=a.port)
    if gut:
        erg["zugang"] = str(s.daten / sb.ZUGANG_DATEI)
        erg["fingerabdruck"] = sb.fingerabdruck(s.ca_pem())
        merken(a)
        m(f"\nFERTIG. Zugangsdatei für die Arbeitsplätze: {erg['zugang']}\n"
          f"Fingerabdruck des Zertifikats (in der IT-Dokumentation notieren): {erg['fingerabdruck']}")
    else:
        m("\nABGEBROCHEN. Fehler beheben und den Assistenten erneut starten; fertige Schritte bleiben erhalten.")
    try:
        Path(a.ordner).mkdir(parents=True, exist_ok=True)
        p = Path(a.ordner) / PROTOKOLL
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n".join(zeilen) + "\n\n")
        erg["protokoll"] = str(p)
    except OSError:
        erg["protokoll"] = None
    return erg


def merken(a, programmordner=None):
    """Server-Ordner und Port neben die .exe schreiben (Server-Ordner.txt): das Server-Setup stoppt damit vor einem
    Update den Server, damit postgres.exe nicht gesperrt ist. Nur in der fertigen .exe oder mit programmordner."""
    import sys
    if programmordner is None:
        if not getattr(sys, "frozen", False):
            return None
        programmordner = Path(sys.executable).parent
    p = Path(programmordner) / MERKER
    try:
        p.write_text(f"{a.ordner}\n{int(a.port)}\n", encoding="utf-8")
    except OSError:
        return None
    return p


def aus_datei(pfad):
    """Angaben aus einer Antwortdatei (JSON mit den Feldern von Angaben; Passwörter dürfen fehlen)."""
    d = json.loads(Path(pfad).read_text(encoding="utf-8"))
    a = vorschlag()
    for k, v in d.items():
        if not hasattr(a, k):
            raise AssistentFehler(f"Unbekannte Angabe „{k}“ in {pfad}")
        setattr(a, k, v)
    return a


def konsole(argv):
    """Ohne Fenster: --server-assistent ANTWORTEN.json; fehlende Passwörter werden abgefragt."""
    import getpass
    a = aus_datei(argv[0])
    if not a.admin_passwort:
        a.admin_passwort = getpass.getpass(f"Passwort für {a.admin} (mindestens 8 Zeichen): ")
    if os.name == "nt" and not a.konto_passwort:
        a.konto_passwort = getpass.getpass(f"Windows-Passwort von {a.konto or ss.konto_vorgabe()}: ")
    erg = ausfuehren(a, fortschritt=None)
    return 0 if erg["gut"] else 2


def main(argv):
    """Einstieg aus start.py (--server-assistent [ANTWORTEN.json])."""
    if argv:
        return _konsole_windows(argv)
    import sys
    if sys.stdout is None:      # Fensterprogramm ohne Konsole
        sys.stdout = sys.stderr = open(os.devnull, "w")
    from .server_assistent_fenster import starten
    return starten()


def _konsole_windows(argv):
    import sys
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        if not k.AttachConsole(-1):
            k.AllocConsole()
        sys.stdout = sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stdin = open("CONIN$", encoding="utf-8", errors="replace")
    if argv[0] in ("-h", "--help", "--hilfe"):
        print(__doc__)
        return 0
    try:
        return konsole(argv)
    except (AssistentFehler, OSError, ValueError) as e:
        print(f"Fehler: {e}")
        return 2
