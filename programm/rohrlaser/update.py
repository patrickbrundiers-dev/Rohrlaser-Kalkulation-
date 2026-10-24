"""Online-Update: nur geänderte Programmdateien herunterladen und austauschen.

Der Build (programm/update_paket.py) schreibt eine Dateiliste Update.json mit Prüfsumme (SHA256) und Größe jeder
Programmdatei und packt die Dateien in Pakete: große Dateien (ab 1 MB) einzeln, kleine Dateien je Ordner
gebündelt. Jedes Paket ist ein ZIP, dessen Einträge nach der Prüfsumme ihres Inhalts heißen; der Paketname hängt
nur vom Inhalt ab. Unveränderte Pakete behalten so ihren Namen und werden beim Veröffentlichen nicht neu
hochgeladen, und das Programm lädt nur die Pakete, in denen eine geänderte Datei steckt.

Austausch im laufenden Programm: Windows erlaubt, eine laufende .exe und geladene DLLs umzubenennen, aber nicht zu
überschreiben. Die alten Dateien wandern deshalb nach _update/alt, die neuen an ihren Platz; beim nächsten Start
wird _update gelöscht. Geht unterwegs etwas schief, kommt jede alte Datei an ihren Platz zurück.
Seit 0.9.50 tauscht das Programm erst aus, nachdem es sich geordnet beendet hat (update_fenster.nach_beenden).
Vorher prüft gesperrte_dateien jede betroffene Datei (Umbenennen hin und zurück); hält ein anderes Programm eine
Datei fest (z. B. die Anleitung im PDF-Betrachter, der Virenscanner), wartet warten_bis_frei bis zu SPERR_WARTEN_S.
Nur Dateien aus der Dateiliste werden angefasst, Daten, Angebote und andere eigene Dateien nie.

Ohne Qt, damit der Build dieselbe Paketbildung benutzt (programm/update_paket.py).
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import time
import urllib.request
import zipfile
import zlib
from pathlib import Path

from . import NAME, VERSION

DATEILISTE = "Update.json"
SPERRLISTE = "Sperrliste.json"      # Lizenz: signierte Sperrliste, neben Update.json im Release update-dateien
ARBEITSORDNER = "_update"           # im Programmordner: Download, Zwischenstand und alte Dateien
# Dateiliste und Pakete liegen im Release "update-dateien" des öffentlichen Repositorys Rohrlaser-Updates: das
# Programm-Repository ist privat, seine Release-Dateien lassen sich ohne Anmeldung nicht laden (404).
# Die Pakete liegen unter "adresse" aus der Dateiliste (bei diesem Build derselbe Ordner).
UPDATE_REPO = "patrickbrundiers-dev/Rohrlaser-Updates"
ADRESSE = f"https://github.com/{UPDATE_REPO}/releases/download/update-dateien/" + DATEILISTE
GROSS = 1 << 20                     # ab 1 MB eigenes Paket
PAKET_MAX = 8 << 20                 # kleine Dateien eines Ordners (3 Ebenen) bis etwa 8 MB je Paket
# nie in der Dateiliste, nie angefasst; Portabel.ini liegt nur im ZIP (installiert fehlt sie, siehe orte.py)
NIE = (DATEILISTE, ARBEITSORDNER, "Daten", "Angebote", "Portabel.ini")
STUECK = 1 << 16
SPERR_WARTEN_S = 30                 # so lange auf eine gesperrte Datei warten, bevor das Programm nachfragt
KURZ_WARTEN_S = 5                   # beim Austausch selbst: kurze Sperren (Virenscanner) abwarten
_ersetzen = os.replace              # Tests setzen hier eine Sperre ein


class UpdateFehler(Exception):
    pass


class Abbruch(UpdateFehler):
    pass


class DateiGesperrt(UpdateFehler):
    """Eine Programmdatei lässt sich nicht austauschen, weil ein anderes Programm sie festhält. dateien: rel. Pfade."""

    def __init__(self, dateien, text=""):
        self.dateien = list(dateien)
        super().__init__(text or sperr_text(self.dateien))


def ist_sperre(e):
    """OSError durch eine von einem anderen Prozess benutzte Datei (Windows: Fehler 5, 32, 33)."""
    return isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32, 33)


def sperr_grund(rel):
    """Wahrscheinlicher Grund, warum die Datei rel festgehalten wird (für die Meldung)."""
    p = str(rel).replace("\\", "/").lower()
    if p.endswith(".pdf"):
        return "wahrscheinlich im PDF-Programm geöffnet – bitte dort schließen"
    if p.startswith("step-import/"):
        return "der STEP-Import läuft noch – bitte im Task-Manager „STEP-Import“ beenden"
    return ("von einem anderen Programm benutzt (Virenscanner, Explorer-Vorschau oder ein zweites "
            f"{NAME}-Fenster) – bitte schließen")


def sperr_text(dateien):
    zeilen = [f"• {rel}: {sperr_grund(rel)}" for rel in list(dateien)[:8]]
    if len(dateien) > 8:
        zeilen.append(f"• … und {len(dateien) - 8} weitere")
    return "Diese Programmdateien sind noch geöffnet und lassen sich nicht austauschen:\n" + "\n".join(zeilen)


def pruefsumme(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for teil in iter(lambda: f.read(1 << 20), b""):
            h.update(teil)
    return h.hexdigest()


def _zip_eintrag(name):
    """Eintrag mit festem Datum: gleicher Inhalt ergibt Byte für Byte dasselbe Paket."""
    z = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
    z.compress_type = zipfile.ZIP_DEFLATED
    z.external_attr = 0o644 << 16
    return z


# ------------------------------------------------------------------ Build: Dateiliste und Pakete erzeugen
def programmdateien(ordner):
    """{relativer Pfad mit '/': Path} aller Programmdateien (ohne Dateiliste, Daten, Ablage, Update-Ordner)."""
    ordner = Path(ordner)
    dateien = {}
    for p in sorted(ordner.rglob("*")):
        rel = p.relative_to(ordner).as_posix()
        if p.is_file() and rel.split("/")[0] not in NIE:
            dateien[rel] = p
    return dateien


def pakete_bilden(dateien):
    """dateien: {rel: (sha256, groesse)} -> {rel: Paketname}. Nur vom Inhalt abhängig, stabil von Build zu Build."""
    zuordnung, gruppen = {}, {}
    for rel, (sha, groesse) in dateien.items():
        if groesse >= GROSS:
            zuordnung[rel] = f"d-{sha[:40]}.zip"
        else:
            gruppen.setdefault("/".join(rel.split("/")[:-1][:3]), []).append(rel)   # höchstens 3 Ordnerebenen
    for ordner, namen in gruppen.items():
        k = max(1, -(-sum(dateien[r][1] for r in namen) // PAKET_MAX))
        teile = {}
        for rel in namen:       # große Ordner nach Dateiname (CRC) aufteilen: eine geänderte Datei ändert nur ihr Teilpaket
            teile.setdefault(zlib.crc32(rel.rpartition("/")[2].encode()) % k, []).append(rel)
        for teil in teile.values():
            kennung = hashlib.sha256("\n".join(sorted({dateien[r][0] for r in teil})).encode()).hexdigest()
            for rel in teil:
                zuordnung[rel] = f"p-{kennung[:40]}.zip"
    return zuordnung


def erstellen(programm, ziel, stand, commit="", aenderung="", adresse="", datum=None):
    """Dateiliste und Pakete für den Programmordner `programm` nach `ziel` schreiben. Ergebnis: Dateiliste (dict)."""
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    pfade = programmdateien(programm)
    info = {rel: (pruefsumme(p), p.stat().st_size) for rel, p in pfade.items()}
    zuordnung = pakete_bilden(info)
    inhalt = {}
    for rel, paket in zuordnung.items():
        inhalt.setdefault(paket, {})[info[rel][0]] = pfade[rel]
    pakete = {}
    for paket, eintraege in sorted(inhalt.items()):
        datei = ziel / paket
        with zipfile.ZipFile(datei, "w") as z:
            for sha in sorted(eintraege):
                z.writestr(_zip_eintrag(sha), eintraege[sha].read_bytes(), compresslevel=6)
        pakete[paket] = dict(groesse=datei.stat().st_size)
    liste = dict(format=1, programm=NAME, version=VERSION, stand=int(stand), commit=commit,
                 datum=datum or datetime.date.today().isoformat(), aenderung=aenderung, adresse=adresse,
                 dateien={rel: dict(sha256=info[rel][0], groesse=info[rel][1], paket=zuordnung[rel])
                          for rel in sorted(info)},
                 pakete=pakete)
    (ziel / DATEILISTE).write_text(json.dumps(liste, indent=1, ensure_ascii=False), encoding="utf-8")
    return liste


# ------------------------------------------------------------------ Programm: prüfen, laden, austauschen
def lokale_liste(ordner):
    """Dateiliste des installierten Stands oder None (z. B. beim Entwickeln)."""
    try:
        return json.loads((Path(ordner) / DATEILISTE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def stand_text(liste):
    if not liste:
        return VERSION
    datum = liste.get("datum") or ""
    try:
        datum = datetime.date.fromisoformat(datum).strftime("%d.%m.%Y")
    except ValueError:
        pass
    return f"{liste.get('version') or VERSION} (Stand {liste.get('stand')}{' vom ' + datum if datum else ''})"


def _ist_url(quelle):
    return str(quelle).startswith(("http://", "https://"))


def _oeffnen(quelle, timeout=30):
    if _ist_url(quelle):
        anfrage = urllib.request.Request(quelle, headers={"User-Agent": f"{NAME} {VERSION}"})
        return urllib.request.urlopen(anfrage, timeout=timeout)
    return open(quelle, "rb")


def holen(quelle, ziel=None, fortschritt=None, timeout=30):
    """Datei von einer Adresse (http/https) oder einem Pfad lesen; mit ziel dorthin schreiben, sonst Bytes zurück.
    fortschritt(bytes) wird je Stück aufgerufen und kann mit Abbruch abbrechen."""
    try:
        with _oeffnen(quelle, timeout) as r:
            if ziel is None:
                return r.read()
            with open(ziel, "wb") as f:
                for teil in iter(lambda: r.read(STUECK), b""):
                    f.write(teil)
                    if fortschritt:
                        fortschritt(len(teil))
    except Abbruch:
        raise
    except Exception as e:      # Netzwerk-, HTTP- und Dateifehler einheitlich melden
        raise UpdateFehler(f"{quelle} lässt sich nicht laden: {e}") from e
    return ziel


def online_liste(quelle=ADRESSE, timeout=15):
    try:
        liste = json.loads(holen(quelle, timeout=timeout))
    except ValueError as e:
        raise UpdateFehler(f"Die Dateiliste {quelle} ist beschädigt: {e}") from e
    if liste.get("format") != 1 or not liste.get("dateien"):
        raise UpdateFehler(f"Die Dateiliste {quelle} hat ein unbekanntes Format.")
    for rel, d in liste["dateien"].items():
        if not sicherer_pfad(rel) or not re.fullmatch(r"[dp]-[0-9a-f]{40}\.zip", str(d.get("paket"))):
            raise UpdateFehler(f"Die Dateiliste {quelle} enthält einen ungültigen Eintrag: {rel}")
    return liste


def lizenz_zusatz(quelle=ADRESSE, timeout=10):
    """Für die Lizenz beim Update-Check: Sperrliste (Bytes oder None) neben der Dateiliste und das Datum des Servers
    (HTTP-Kopf Date, als datetime.date oder None). Fehler zählen nicht: ohne Netz bleibt alles, wie es ist."""
    adresse = str(quelle).replace("\\", "/").rsplit("/", 1)[0] + "/" + SPERRLISTE
    if not _ist_url(quelle):
        adresse = str(Path(quelle).parent / SPERRLISTE)
    daten, datum = None, None
    try:
        with _oeffnen(adresse, timeout) as r:
            daten = r.read(1 << 20)
            kopf = r.headers.get("Date") if hasattr(r, "headers") else None
            if kopf:
                import email.utils
                datum = email.utils.parsedate_to_datetime(kopf).date()
    except Exception:       # noqa: BLE001 – keine Sperrliste veröffentlicht (404), kein Netz, kaputter Kopf
        pass
    return dict(sperrliste=daten, datum=datum)


def sicherer_pfad(rel):
    """Nur Pfade innerhalb des Programmordners, nie Daten, Angebote oder der Update-Ordner."""
    teile = str(rel).split("/")
    return (bool(rel) and "\\" not in rel and ":" not in rel and not rel.startswith("/")
            and all(t not in ("", ".", "..") for t in teile) and teile[0] not in NIE)


def neuer(online, lokal):
    """Gibt es online einen neueren Stand als installiert?"""
    return int(online.get("stand") or 0) > int((lokal or {}).get("stand") or 0)


def paket_adresse(quelle, online, paket):
    """Pakete liegen unter "adresse" der Dateiliste; kommt die Liste aus einem Ordner, im selben Ordner."""
    if not _ist_url(quelle):
        return str(Path(quelle).parent / paket)
    basis = online.get("adresse") or quelle.rpartition("/")[0] + "/"
    return basis.rstrip("/") + "/" + paket


def planen(ordner, online, lokal=None, alle=False, fortschritt=None):
    """Welche Dateien fehlen oder sind anders (Prüfsumme der Datei auf der Platte), welche Pakete braucht es,
    welche Dateien des alten Stands fallen weg. alle=True tauscht jede Datei aus (Test)."""
    ordner = Path(ordner)
    dateien = online["dateien"]
    neu = []
    for i, (rel, d) in enumerate(dateien.items()):
        if fortschritt:
            fortschritt(i, len(dateien))
        p = ordner / rel
        if alle or not p.is_file() or p.stat().st_size != d["groesse"] or pruefsumme(p) != d["sha256"]:
            neu.append(rel)
    alt = set((lokal or {}).get("dateien") or ())
    weg = sorted(rel for rel in alt - set(dateien) if (ordner / rel).is_file())
    pakete = sorted({dateien[rel]["paket"] for rel in neu})
    groesse = sum((online.get("pakete") or {}).get(p, {}).get("groesse", 0) for p in pakete)
    return dict(neu=neu, weg=weg, pakete=pakete, groesse=groesse)


def laden(ordner, quelle, online, plan, fortschritt=None):
    """Pakete laden und die gebrauchten Dateien nach _update/neu/<sha256> auspacken (geprüft)."""
    arbeit = Path(ordner) / ARBEITSORDNER
    neu_ordner = arbeit / "neu"
    shutil.rmtree(neu_ordner, ignore_errors=True)
    (arbeit / "pakete").mkdir(parents=True, exist_ok=True)
    neu_ordner.mkdir(parents=True, exist_ok=True)
    gebraucht = {}
    for rel in plan["neu"]:
        d = online["dateien"][rel]
        gebraucht.setdefault(d["paket"], set()).add(d["sha256"])
    for paket in plan["pakete"]:
        datei = holen(paket_adresse(quelle, online, paket), arbeit / "pakete" / paket, fortschritt)
        try:
            with zipfile.ZipFile(datei) as z:
                for sha in gebraucht[paket]:
                    ziel = neu_ordner / sha
                    with z.open(sha) as quelle_datei, open(ziel, "wb") as f:
                        shutil.copyfileobj(quelle_datei, f, 1 << 20)
                    if pruefsumme(ziel) != sha:
                        raise UpdateFehler(f"Prüfsumme falsch in {paket}")
        except (zipfile.BadZipFile, KeyError) as e:
            raise UpdateFehler(f"Paket {paket} ist beschädigt: {e}") from e
        datei.unlink()
    return neu_ordner


def gesperrte_dateien(ordner, plan):
    """Vorabprüfung: rel. Pfade der betroffenen Dateien, die sich jetzt nicht wegschieben lassen (jede wird probehalber
    umbenannt und gleich zurück; dabei wird nichts ausgetauscht)."""
    ordner = Path(ordner)
    out = []
    for rel in list(plan["neu"]) + list(plan["weg"]):
        ziel = ordner / rel
        if not ziel.is_file():
            continue
        probe = ziel.with_name(ziel.name + ".probe")
        try:
            _ersetzen(ziel, probe)
        except OSError:
            out.append(rel)
            continue
        _zurueck(probe, ziel)
    return out


def _zurueck(von, nach, sekunden=None, schlafen=time.sleep):
    """Umbenennen, bei einer kurzen Sperre (Virenscanner prüft die Datei gerade) einige Sekunden wiederholen."""
    ende = time.monotonic() + (KURZ_WARTEN_S if sekunden is None else sekunden)
    while True:
        try:
            return _ersetzen(von, nach)
        except OSError as e:
            if not ist_sperre(e) or time.monotonic() >= ende:
                raise
            schlafen(0.25)


def warten_bis_frei(ordner, plan, sekunden=None, melden=None, schlafen=time.sleep, uhr=time.monotonic):
    """Bis zu sekunden warten, bis keine betroffene Datei mehr gesperrt ist. melden(gesperrt, rest_s) nach jeder
    Runde (Anzeige). Ergebnis: rel. Pfade, die dann noch gesperrt sind ([] = alles frei)."""
    ende = uhr() + (SPERR_WARTEN_S if sekunden is None else sekunden)
    while True:
        gesperrt = gesperrte_dateien(ordner, plan)
        rest = ende - uhr()
        if not gesperrt or rest <= 0:
            return gesperrt
        if melden:
            melden(gesperrt, rest)
        schlafen(1)


def einspielen(ordner, online, plan, neu_ordner):
    """Alte Dateien nach _update/alt verschieben, neue an ihren Platz, zuletzt die Dateiliste.
    Bei einem Fehler alles zurück und UpdateFehler bzw. DateiGesperrt (der Programmordner ist dann wie vorher, der
    Download in _update/neu bleibt für einen neuen Versuch)."""
    ordner = Path(ordner)
    alt = ordner / ARBEITSORDNER / f"alt-{datetime.datetime.now():%Y%m%d-%H%M%S-%f}"
    getan = []          # [Ziel, gesicherte alte Datei oder None, neue Datei angelegt]

    def wegschieben(ziel):
        if not ziel.exists():
            return None
        b = alt / ziel.relative_to(ordner)
        b.parent.mkdir(parents=True, exist_ok=True)
        _zurueck(ziel, b)           # klappt auch bei laufender .exe und geladenen DLLs
        return b

    try:
        for rel in plan["neu"]:
            ziel = ordner / rel
            getan.append([ziel, wegschieben(ziel), True])
            ziel.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(neu_ordner / online["dateien"][rel]["sha256"], ziel)
        for rel in plan["weg"]:
            ziel = ordner / rel
            getan.append([ziel, wegschieben(ziel), False])
        tmp = ordner / (DATEILISTE + ".neu")
        tmp.write_text(json.dumps(online, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, ordner / DATEILISTE)
    except OSError as e:
        fehler = []
        for ziel, b, angelegt in reversed(getan):
            try:
                if angelegt and ziel.exists():
                    ziel.unlink()
                if b is not None:
                    _zurueck(b, ziel)
            except OSError as e2:
                fehler.append(f"{ziel}: {e2}")
        datei = getattr(e, "filename", "") or ""
        text = f"Die Datei {datei} lässt sich nicht austauschen: {e}"
        if fehler:
            text += "\n\nNicht zurückgestellt (aus " + str(alt) + " von Hand zurückkopieren):\n" + "\n".join(fehler)
            raise UpdateFehler(text) from e
        if ist_sperre(e) and datei:
            try:
                rel = Path(datei).resolve().relative_to(ordner.resolve()).as_posix()
            except ValueError:
                rel = Path(datei).name
            raise DateiGesperrt([rel]) from e
        raise UpdateFehler(text) from e
    shutil.rmtree(neu_ordner, ignore_errors=True)
    return alt


def verwerfen(ordner):
    """Nach Abbruch oder Fehler: Download und Zwischenstand löschen (alte Dateien unter _update/alt-* bleiben)."""
    for name in ("neu", "pakete"):
        shutil.rmtree(Path(ordner) / ARBEITSORDNER / name, ignore_errors=True)


def aufraeumen(ordner):
    """Beim Start: Reste eines Updates löschen (alte Dateien sind jetzt frei). Fehler stören nicht."""
    shutil.rmtree(Path(ordner) / ARBEITSORDNER, ignore_errors=True)
    (Path(ordner) / (DATEILISTE + ".neu")).unlink(missing_ok=True)


def neuere_liste(quelle, online):
    """Fehlt beim Laden ein Paket, hat meist ein neuerer Build die Dateiliste ersetzt und die alten Pakete gelöscht,
    nachdem das Programm die Liste geholt hatte. Dann die aktuelle Liste holen: Ergebnis die neue Dateiliste, wenn
    sie einen anderen Stand hat, sonst None (der Fehler ist dann ein anderer)."""
    try:
        frisch = online_liste(quelle)
    except UpdateFehler:
        return None
    return frisch if frisch.get("stand") != online.get("stand") else None


def aktualisieren(ordner, quelle=ADRESSE, alle=False, fortschritt=None, online=None):
    """Prüfen, laden, einspielen in einem Zug (ohne Rückfragen). Ergebnis: (Dateiliste, Plan) bzw. Plan None,
    wenn nichts zu tun ist. Ist die Dateiliste inzwischen überholt (Paket fehlt), einmal mit der neuen."""
    online = online or online_liste(quelle)
    lokal = lokale_liste(ordner)
    for versuch in range(2):
        plan = planen(ordner, online, lokal, alle=alle)
        if not plan["neu"] and not plan["weg"]:
            return online, None
        try:
            neu_ordner = laden(ordner, quelle, online, plan, fortschritt)
            break
        except UpdateFehler:
            verwerfen(ordner)
            frisch = neuere_liste(quelle, online) if versuch == 0 else None
            if frisch is None:
                raise
            online = frisch
    einspielen(ordner, online, plan, neu_ordner)
    return online, plan
