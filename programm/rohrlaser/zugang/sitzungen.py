"""Sitzungen (Paket A): wer ist angemeldet, seit wann, mit welchen Rechten; Inaktivität und Benutzerwechsel.

Jede Anmeldung erzeugt eine Sitzung mit zufälligem Token (secrets, 256 Bit). Nach Inaktivität (Vorgabe 30 Minuten,
Entwickler 15 Minuten, E4a) wird die Sitzung gesperrt: Daten bleiben offen, weiter geht es nur mit erneuter
Passworteingabe. Abmelden und Benutzerwechsel beenden die Sitzung; ein beendetes Token gilt nie wieder (auch nicht,
wenn es jemand kopiert hat). Ohne Qt; die Uhr ist austauschbar (Tests).
"""
import secrets
import threading
import time
from dataclasses import dataclass, field

MINUTEN_STANDARD = 30
MINUTEN_ENTWICKLER = 15


class SitzungFehler(PermissionError):
    """Keine gültige Sitzung (nie angemeldet, abgemeldet, abgelaufen oder gesperrt)."""


@dataclass
class Sitzung:
    token: str
    benutzer: str                       # Benutzer-ID bzw. Ausweis-Nummer beim Entwickler
    kuerzel: str
    name: str
    rollen: tuple
    rechte: frozenset
    entwickler: bool
    installation: str
    arbeitsplatz: str
    beginn: float
    letzte: float
    minuten: int
    gesperrt: bool = False
    beendet: bool = False
    zusatz: dict = field(default_factory=dict)

    @property
    def aktiv(self):
        return not self.beendet and not self.gesperrt


class Sitzungen:
    """Sitzungsverwaltung eines Programms (eine aktuelle Sitzung je Programmfenster)."""

    def __init__(self, uhr=time.monotonic):
        self.uhr = uhr
        self.aktuell = None
        self._beendet = set()
        self._lock = threading.Lock()

    def anlegen(self, benutzer, kuerzel="", name="", rollen=(), rechte=(), entwickler=False, installation="",
                arbeitsplatz="", minuten=None, **zusatz):
        with self._lock:
            if self.aktuell and not self.aktuell.beendet:
                self._beenden(self.aktuell)
            jetzt = self.uhr()
            m = int(minuten or (MINUTEN_ENTWICKLER if entwickler else MINUTEN_STANDARD))
            self.aktuell = Sitzung(secrets.token_hex(32), str(benutzer), kuerzel, name, tuple(rollen),
                                   frozenset(rechte), bool(entwickler), str(installation), str(arbeitsplatz), jetzt,
                                   jetzt, max(1, m), zusatz=dict(zusatz))
            return self.aktuell

    def _beenden(self, s):
        s.beendet = True
        self._beendet.add(s.token)

    def beenden(self):
        with self._lock:
            s = self.aktuell
            if s and not s.beendet:
                self._beenden(s)
            self.aktuell = None
            return s

    def eingabe(self):
        s = self.aktuell
        if s and s.aktiv:
            s.letzte = self.uhr()

    def ablauf_pruefen(self):
        """True, wenn die Sitzung gerade wegen Inaktivität gesperrt wurde."""
        s = self.aktuell
        if s and s.aktiv and self.uhr() - s.letzte >= s.minuten * 60:
            s.gesperrt = True
            return True
        return False

    def entsperren(self):
        """Nach erneuter erfolgreicher Prüfung desselben Benutzers (pruefstelle)."""
        s = self.aktuell
        if s and not s.beendet:
            s.gesperrt = False
            s.letzte = self.uhr()

    def pruefen(self, token=None):
        """Aktuelle Sitzung, wenn sie gilt; sonst SitzungFehler. token: das Token, das der Aufrufer kennt (z. B. aus
        einem Hintergrundauftrag) – ein fremdes oder beendetes Token wird abgelehnt."""
        s = self.aktuell
        if token is not None and (token in self._beendet or s is None or token != s.token):
            raise SitzungFehler("Die Sitzung ist nicht mehr gültig. Bitte neu anmelden.")
        if s is None or s.beendet:
            raise SitzungFehler("Nicht angemeldet.")
        self.ablauf_pruefen()
        if s.gesperrt:
            raise SitzungFehler("Die Sitzung ist wegen Inaktivität gesperrt. Bitte Passwort eingeben.")
        return s
