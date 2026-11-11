"""Online-Update für Rohrlaser Auslastung (ohne Qt).

Das Programm holt eine Dateiliste Update.json mit Prüfsumme jeder Programmdatei aus dem öffentlichen Repository
Rohrlaser-Updates (eigenes Release „auslastung-dateien“, getrennt von der Kalkulation), lädt nur die Pakete mit
geänderten Dateien und tauscht die Dateien aus, nachdem es sich beendet hat. Das Laden, Prüfen und Austauschen
(mit Zurückstellen bei einem Fehler) übernimmt rohrlaser.update unverändert; hier steht nur, was für dieses Programm
anders ist:

- eigene Adresse (ADRESSE, zum Testen die Umgebungsvariable RLA_UPDATE_QUELLE: Adresse oder Pfad einer Update.json),
- die Dateiliste gilt nur mit gültiger Signatur (Update.json.sig, derselbe Update-Schlüssel wie die Kalkulation).
  Vor die signierten Bytes kommt zusätzlich KONTEXT: eine Dateiliste der Kalkulation gilt deshalb hier nie und eine
  Liste dieses Programms nie in der Kalkulation,
- die Dateiliste muss für dieses Programm ausgestellt sein (Feld „programm“).

Der Bau (programm/auslastung_update_paket.py, Workflow Auslastung) benutzt erstellen() und signieren().
"""
import datetime
import json
import os
import sys
import time
from pathlib import Path

from rohrlaser import update

from . import NAME, VERSION

TAG = "auslastung-dateien"
ADRESSE = f"https://github.com/{update.UPDATE_REPO}/releases/download/{TAG}/{update.DATEILISTE}"
KONTEXT = b"Rohrlaser-Auslastung/1\n"
UpdateFehler, Abbruch, DateiGesperrt = update.UpdateFehler, update.Abbruch, update.DateiGesperrt


def quelle():
    return os.environ.get("RLA_UPDATE_QUELLE") or ADRESSE


def programmordner():
    """Ordner des fertigen Programms (neben Rohrlaser-Auslastung.exe) oder None beim Start aus dem Quelltext."""
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None


def lokale_liste(ordner):
    return update.lokale_liste(ordner) if ordner else None


def stand_text(liste):
    """„1.7.0 (Stand 12 vom 11.11.2026)“; ohne Dateiliste nur die Version des laufenden Programms."""
    if not liste:
        return VERSION
    datum = liste.get("datum") or ""
    try:
        datum = datetime.date.fromisoformat(datum).strftime("%d.%m.%Y")
    except ValueError:
        pass
    return f"{liste.get('version') or VERSION} (Stand {liste.get('stand')}{' vom ' + datum if datum else ''})"


def signieren(daten, privat, schluessel_id):
    """Inhalt von Update.json.sig zu den exakten Bytes daten (nur im Bau)."""
    return update.signatur_erstellen(KONTEXT + bytes(daten), privat, schluessel_id)


def signatur_pruefen(daten, signatur, schluessel=None):
    schluessel = update.update_schluessel() if schluessel is None else schluessel
    if not schluessel:
        raise UpdateFehler("Im Programm ist kein Update-Schlüssel hinterlegt, Updates sind nicht möglich.")
    update.signatur_pruefen(KONTEXT + bytes(daten), signatur, schluessel)


def online_liste(adresse=None, timeout=15, schluessel=None):
    """Dateiliste laden; sie gilt nur mit gültiger Signatur und nur für dieses Programm. Passen Liste und Signatur
    nicht zusammen, wird einmal neu geladen (der Bau lädt beide gerade hoch)."""
    adresse = adresse or quelle()
    for versuch in range(2):
        daten = update.holen(adresse, timeout=timeout, grenze=update.LISTE_MAX)
        signatur = update.holen(update.daneben(adresse, update.SIGNATUR), timeout=timeout, grenze=update.SIGNATUR_MAX)
        try:
            signatur_pruefen(daten, signatur, schluessel)
            break
        except UpdateFehler:
            if versuch:
                raise
            time.sleep(3 if str(adresse).startswith("https://") else 0)
    try:
        liste = update.Dateiliste(json.loads(daten))
    except (ValueError, TypeError) as e:
        raise UpdateFehler(f"Die Dateiliste {adresse} ist beschädigt: {e}") from e
    update.liste_pruefen(liste, adresse)
    if liste.get("programm") != NAME:
        raise UpdateFehler(f"Die Dateiliste {adresse} gehört nicht zu {NAME}.")
    liste.roh, liste.signatur = bytes(daten), bytes(signatur)
    return liste


def neuer(online, lokal):
    return update.neuer(online, lokal)


def erstellen(programm, ziel, stand, aenderung="", adresse=""):
    """Bau: Dateiliste und Pakete für den Programmordner schreiben (wie die Kalkulation), mit Namen und Version
    dieses Programms. Ergebnis: Dateiliste (dict)."""
    liste = update.erstellen(programm, ziel, stand, "", aenderung, adresse)
    liste.update(programm=NAME, version=VERSION)
    (Path(ziel) / update.DATEILISTE).write_text(json.dumps(liste, indent=1, ensure_ascii=False), encoding="utf-8")
    return liste


def beim_start(ordner):
    """Vor allem anderen: einen unterbrochenen Austausch zurückstellen, Reste des letzten Updates löschen (die alten
    Dateien sind jetzt frei). Fehler stören den Start nicht."""
    if not ordner:
        return
    try:
        update.nach_absturz(ordner)
        update.aufraeumen(ordner)
    except Exception:       # noqa: BLE001 – Aufräumen darf den Start nie verhindern
        pass


def laden(ordner, online, lokal=None, adresse=None, pruefen=None, geladen=None, melden=None, alle=False):
    """Prüfen, was sich geändert hat, und nur das laden. Ergebnis: dict(online, plan, neu_ordner) für austauschen().
    Hat inzwischen ein neuerer Stand die Dateiliste ersetzt (Paket fehlt), einmal mit der neuen Liste."""
    adresse = adresse or quelle()
    for versuch in range(2):
        plan = update.planen(ordner, online, lokal, alle=alle, fortschritt=pruefen)
        try:
            neu_ordner = update.laden(ordner, adresse, online, plan, geladen, melden=melden)
            return dict(online=online, plan=plan, neu_ordner=neu_ordner)
        except Abbruch:
            raise
        except UpdateFehler:
            update.verwerfen(ordner, download_behalten=True)
            frisch = None
            if versuch == 0:
                try:
                    frisch = online_liste(adresse)
                except UpdateFehler:
                    frisch = None
            if frisch is None or frisch.get("stand") == online.get("stand"):
                raise
            online = frisch


def austauschen(ordner, ausstehend, melden=None):
    """Nach dem Beenden des Programms: warten, bis keine Datei mehr gesperrt ist, dann austauschen. Ergebnis: Liste
    der noch gesperrten Dateien ([] = ausgetauscht). Bei einem Fehler ist alles zurückgestellt (UpdateFehler)."""
    plan = ausstehend["plan"]
    gesperrt = update.warten_bis_frei(ordner, plan, melden=melden)
    if gesperrt:
        return gesperrt
    try:
        update.einspielen(ordner, ausstehend["online"], plan, ausstehend["neu_ordner"])
    except DateiGesperrt as e:
        return list(e.dateien)
    return []


def verwerfen(ordner):
    update.verwerfen(ordner)
