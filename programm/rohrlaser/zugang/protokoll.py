"""Sicherheitsprotokoll des Zugangssystems (Paket A; ab Paket B zusätzlich in der Tabelle zg_protokoll).

Ein Eintrag je Zeile (JSON): Zeit (UTC), Aktion, Benutzer, Installation, Arbeitsplatz, Objekt, Ergebnis, Details.
Geheimnisse kommen nie hinein: bereinigen() ersetzt jeden Wert, dessen Schlüssel nach Passwort, PIN, Token, Tresor,
Geheimnis, Seed, Code oder Signatur aussieht, durch „***“, und kürzt lange Texte. Die Datei wird nur angehängt;
ab GROESSE_MAX wird sie in .1 umbenannt (eine Vorgängerdatei bleibt). Ohne Qt.
"""
import datetime
import json
import os
import re
import threading
from pathlib import Path

DATEI = "sicherheit.jsonl"
GROESSE_MAX = 5 * 1024 * 1024
TEXT_MAX = 500

# Aktionen (Abschnitt 9 des Auftrags)
(ANMELDUNG_OK, ANMELDUNG_FEHLER, ABMELDUNG, BENUTZERWECHSEL, SITZUNG_ABGELAUFEN, GESPERRT, PASSWORT_GEAENDERT,
 PASSWORT_RESET, BENUTZER_ANGELEGT, BENUTZER_GEAENDERT, ROLLE_GEAENDERT, RECHT_GEAENDERT, LIZENZ_AKTIVIERT,
 LIZENZ_DEAKTIVIERT, ARBEITSPLATZ_REGISTRIERT, ENTWICKLER_ZUGRIFF, KONFIGURATION_GEAENDERT, ZUGRIFF_VERWEIGERT,
 MIGRATION) = (
    "anmeldung_ok", "anmeldung_fehler", "abmeldung", "benutzerwechsel", "sitzung_abgelaufen", "gesperrt",
    "passwort_geaendert", "passwort_reset", "benutzer_angelegt", "benutzer_geaendert", "rolle_geaendert",
    "recht_geaendert", "lizenz_aktiviert", "lizenz_deaktiviert", "arbeitsplatz_registriert", "entwickler_zugriff",
    "konfiguration_geaendert", "zugriff_verweigert", "migration")

_GEHEIM = re.compile(r"pass|pin|token|tresor|geheim|secret|seed|code|signatur|schluessel_privat|hash", re.I)
_sperre = threading.Lock()


def bereinigen(wert, tiefe=0):
    """Kopie ohne Geheimnisse (rekursiv), lange Texte gekürzt."""
    if tiefe > 5:
        return "…"
    if isinstance(wert, dict):
        return {str(k): ("***" if _GEHEIM.search(str(k)) else bereinigen(v, tiefe + 1)) for k, v in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [bereinigen(v, tiefe + 1) for v in list(wert)[:50]]
    if isinstance(wert, str):
        return wert if len(wert) <= TEXT_MAX else wert[:TEXT_MAX] + "…"
    if wert is None or isinstance(wert, (int, float, bool)):
        return wert
    return bereinigen(str(wert), tiefe + 1)


class Protokoll:
    """Sicherheitsprotokoll in ordner/DATEI. senke: optionale Funktion(eintrag) für die Datenbank (Paket B)."""

    def __init__(self, ordner, installation="", arbeitsplatz="", senke=None, uhr=None):
        self.ordner = Path(ordner) if ordner else None
        self.installation = installation
        self.arbeitsplatz = arbeitsplatz
        self.senke = senke
        self.uhr = uhr or (lambda: datetime.datetime.now(datetime.timezone.utc))

    @property
    def pfad(self):
        return self.ordner / DATEI if self.ordner else None

    def schreiben(self, aktion, benutzer="", objekt="", ergebnis="ok", **details):
        e = dict(zeit=self.uhr().isoformat(timespec="seconds"), aktion=str(aktion), benutzer=str(benutzer or ""),
                 installation=self.installation, arbeitsplatz=self.arbeitsplatz, objekt=str(objekt or ""),
                 ergebnis=str(ergebnis), details=bereinigen(details))
        if self.pfad:
            with _sperre:
                try:
                    self.ordner.mkdir(parents=True, exist_ok=True)
                    if self.pfad.exists() and self.pfad.stat().st_size > GROESSE_MAX:
                        os.replace(self.pfad, self.pfad.with_suffix(".jsonl.1"))
                    with open(self.pfad, "a", encoding="utf-8") as f:
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
                except OSError:
                    pass        # ein volles Laufwerk darf die Anmeldung nicht verhindern
        if self.senke:
            try:
                self.senke(e)
            except Exception:  # noqa: BLE001 – Protokoll darf nie den Ablauf abbrechen
                pass
        return e

    def lesen(self, letzte=500, aktion=None, benutzer=None):
        """Die letzten Einträge, neueste zuletzt; optional gefiltert."""
        if not self.pfad or not self.pfad.exists():
            return []
        aus = []
        for z in self.pfad.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(z)
            except ValueError:
                continue
            if (aktion is None or e.get("aktion") == aktion) and (benutzer is None or e.get("benutzer") == benutzer):
                aus.append(e)
        return aus[-letzte:]
