"""Fehlermeldungen in Klartext (Verbesserungsplan 06.11.2026, B3): was passiert ist und was zu tun ist.

fehler_text(e) übersetzt technische Fehler des Betriebssystems, der Datenbank und des Netzwerks (z. B.
„[Errno 13] Permission denied: 'C:/…/Angebot.pdf'“) in einen Satz mit Lösung. Meldungen des Programms selbst
(ValueError, PermissionError mit deutschem Text u. ä.) bleiben unverändert, sie sind schon Klartext.
"""
import errno
import sqlite3
from pathlib import Path

# Windows-Fehlernummern (winerror) für Netzlaufwerke
_NETZ = {53, 64, 67, 121, 1219, 1222, 1231}


def _name(e):
    pfad = getattr(e, "filename", None)
    return Path(str(pfad)).name or str(pfad) if pfad else ""


def _deutsch(text):
    """True, wenn der Text schon eine Meldung des Programms ist (deutsch, kein „[Errno …]“)."""
    t = str(text or "")
    return bool(t) and "[Errno" not in t and "[WinError" not in t and any(
        w in t for w in ("ä", "ö", "ü", "ß", " nicht ", " bitte ", "Bitte ", " der ", " die ", " das ", " ist "))


def fehler_text(e):
    """Fehler e (Exception oder Text) als Klartext mit Lösung."""
    if not isinstance(e, BaseException):
        return str(e or "")
    roh = str(e)
    name = _name(e)
    datei = f"„{name}“" if name else "die Datei"
    if isinstance(e, sqlite3.OperationalError) and "locked" in roh:
        return ("Die Datenbank ist gerade belegt (ein anderer Vorgang schreibt noch). Bitte einen Moment warten und "
                "noch einmal versuchen.")
    if isinstance(e, sqlite3.DatabaseError) and ("malformed" in roh or "not a database" in roh):
        return ("Die Datenbank ist beschädigt. Bitte Datei → Sicherung wiederherstellen … wählen oder das "
                "Support-Paket (Hilfe) an Patrick schicken.")
    if isinstance(e, UnicodeDecodeError):
        return ("Die Datei hat eine unbekannte Zeichenkodierung. Bitte als CSV (UTF-8) oder „CSV (Trennzeichen-"
                "getrennt)“ aus Excel neu speichern.")
    if isinstance(e, (TimeoutError, ConnectionError)):
        return "Keine Verbindung (Netzwerk oder Server antwortet nicht). Bitte Netzwerk prüfen und später noch einmal."
    if isinstance(e, OSError) and not _deutsch(roh):
        winerror = getattr(e, "winerror", None)
        if isinstance(e, PermissionError) or e.errno in (errno.EACCES, errno.EPERM) or winerror in (5, 32, 33):
            return (f"Kein Zugriff auf {datei}: sie ist in einem anderen Programm geöffnet (z. B. PDF-Anzeige oder "
                    "Excel) oder schreibgeschützt. Bitte dort schließen und noch einmal versuchen.")
        if isinstance(e, FileNotFoundError) or e.errno == errno.ENOENT or winerror in (2, 3):
            return (f"{datei[:1].upper() + datei[1:]} bzw. der Ordner ist nicht (mehr) da. Bitte den Pfad prüfen, z. B. "
                    "ob das Netzlaufwerk verbunden ist.")
        if e.errno == errno.ENOSPC or winerror == 112:
            return "Auf dem Laufwerk ist kein Platz mehr. Bitte Platz schaffen und noch einmal versuchen."
        if winerror in _NETZ or e.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH):
            return ("Das Netzlaufwerk bzw. der gemeinsame Ordner ist nicht erreichbar. Bitte Netzwerk und "
                    "Laufwerksverbindung prüfen und noch einmal versuchen.")
        if isinstance(e, FileExistsError):
            return f"{datei[:1].upper() + datei[1:]} gibt es schon. Bitte einen anderen Namen wählen."
    return roh
