"""Online-Update: nur geänderte Programmdateien herunterladen und austauschen.

Der Build (programm/update_paket.py) schreibt eine Dateiliste Update.json mit Prüfsumme (SHA256) und Größe jeder
Programmdatei und packt die Dateien in Pakete: große Dateien (ab 1 MB) einzeln, kleine Dateien je Ordner
gebündelt. Jedes Paket ist ein ZIP, dessen Einträge nach der Prüfsumme ihres Inhalts heißen; der Paketname hängt
nur vom Inhalt ab. Unveränderte Pakete behalten so ihren Namen und werden beim Veröffentlichen nicht neu
hochgeladen, und das Programm lädt nur die Pakete, in denen eine geänderte Datei steckt.

Austausch im laufenden Programm: Windows erlaubt, eine laufende .exe und geladene DLLs umzubenennen, aber nicht zu
überschreiben. Die alten Dateien wandern deshalb nach _update/alt, die neuen an ihren Platz; beim nächsten Start
wird _update gelöscht. Geht unterwegs etwas schief, kommt jede alte Datei an ihren Platz zurück.
Seit 0.9.53 tauscht das Programm erst aus, nachdem es sich geordnet beendet hat (update_fenster.nach_beenden).
Vorher prüft gesperrte_dateien jede betroffene Datei (Umbenennen hin und zurück); hält ein anderes Programm eine
Datei fest (z. B. die Anleitung im PDF-Betrachter, der Virenscanner), wartet warten_bis_frei bis zu SPERR_WARTEN_S.
Nur Dateien aus der Dateiliste werden angefasst, Daten, Angebote und andere eigene Dateien nie.

Prüfungen gegen eine gefälschte oder kaputte Dateiliste (Audit 24.10.2026, H1): Pfade nach Windows-Regeln
(sicherer_pfad: Groß-/Kleinschreibung, Punkt/Leerzeichen am Ende, reservierte Namen), Prüfsummen nur als Hex,
Pakete nur per https von der erwarteten Adresse, Größengrenzen für Dateiliste, Pakete und Dateien, freier
Speicherplatz vor dem Laden. Absturz mitten im Austausch (H2): vor dem ersten Verschieben steht ein Journal in
_update/journal.json; findet der nächste Start es noch, stellt nach_absturz() die alten Dateien zurück.

Ohne Qt, damit der Build dieselbe Paketbildung benutzt (programm/update_paket.py).
"""
import base64
import datetime
import hashlib
import http.client
import json
import logging
import os
import re
import shutil
import socket
import ssl
import time
import urllib.error
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
# Download der Pakete (Firmennetz 26.10.2026: Abbruch nach ein paar Prozent): Wartezeiten in s zwischen neuen
# Versuchen nach einem Verbindungsabbruch (fortgesetzt an der Abbruchstelle), Zeitlimit je Lesevorgang
WIEDERHOLEN_S = (2, 5, 10, 20, 30)
DOWNLOAD_TIMEOUT_S = 60
SPERR_WARTEN_S = 30                 # so lange auf eine gesperrte Datei warten, bevor das Programm nachfragt
KURZ_WARTEN_S = 5                   # beim Austausch selbst: kurze Sperren (Virenscanner) abwarten
_ersetzen = os.replace              # Tests setzen hier eine Sperre ein
JOURNAL = "journal.json"            # in _update: laufender Austausch (einspielen), nach_absturz() stellt zurück
# Grenzen gegen kaputte oder gefälschte Dateilisten und Pakete
LISTE_MAX = 16 << 20                # Update.json
DATEI_MAX = 1 << 30                 # eine Programmdatei
PAKET_GROESSE_MAX = 1 << 30         # ein Paket
DATEIEN_MAX = 20000                 # Einträge in der Dateiliste
PLATZ_RESERVE = 100 << 20           # so viel soll nach Laden und Entpacken noch frei bleiben
# Pakete nur von hier (bzw. aus dem Ordner der Dateiliste); nur https
ERLAUBTE_ADRESSEN = (f"https://github.com/{UPDATE_REPO}/releases/download/",)
SIGNATUR = DATEILISTE + ".sig"      # neben Update.json: Ed25519-Signatur der exakten Bytes (signatur_pruefen)
SIGNATUR_KONTEXT = b"Rohrlaser-Update.json/1\n"    # vor die Bytes gesetzt: die Signatur gilt nur für Dateilisten
SIGNATUR_MAX = 16 << 10
_SHA = re.compile(r"[0-9a-f]{64}")
_PAKET = re.compile(r"[dp]-[0-9a-f]{40}\.zip")
_RESERVIERT = {"con", "prn", "aux", "nul", "clock$", "conin$", "conout$",
               *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
_VERBOTEN = set('\\:*?"<>|')


_log = logging.getLogger("rohrlaser")    # Protokoll (protokoll.py richtet es ein)


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


NACHHOLEN = "nachholen"              # in _update: Anleitungen, die beim Update gesperrt waren (nachholen())


def wer_sperrt(pfad):
    """Namen der Programme, die die Datei gerade festhalten (Windows-Neustart-Manager), sonst []. Nur für die Meldung
    und das Protokoll; jeder Fehler ergibt []."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class _Prozess(ctypes.Structure):
            _fields_ = [("pid", wintypes.DWORD), ("start", wintypes.FILETIME)]

        class _Info(ctypes.Structure):
            _fields_ = [("prozess", _Prozess), ("name", wintypes.WCHAR * 256), ("dienst", wintypes.WCHAR * 64),
                        ("art", wintypes.DWORD), ("status", wintypes.ULONG), ("sitzung", wintypes.DWORD),
                        ("neustartbar", wintypes.BOOL)]

        rm = ctypes.WinDLL("rstrtmgr")
        sitzung, schluessel = wintypes.DWORD(), ctypes.create_unicode_buffer(64)
        if rm.RmStartSession(ctypes.byref(sitzung), 0, schluessel):
            return []
        try:
            dateien = (wintypes.LPCWSTR * 1)(str(pfad))
            if rm.RmRegisterResources(sitzung, 1, dateien, 0, None, 0, None):
                return []
            noetig, anzahl, grund = wintypes.UINT(0), wintypes.UINT(0), wintypes.DWORD()
            rm.RmGetList(sitzung, ctypes.byref(noetig), ctypes.byref(anzahl), None, ctypes.byref(grund))
            if not noetig.value:
                return []
            infos = (_Info * noetig.value)()
            anzahl = wintypes.UINT(noetig.value)
            if rm.RmGetList(sitzung, ctypes.byref(noetig), ctypes.byref(anzahl), infos, ctypes.byref(grund)):
                return []
            return sorted({i.name or f"Prozess {i.prozess.pid}" for i in infos[:anzahl.value]})
        finally:
            rm.RmEndSession(sitzung)
    except Exception:       # noqa: BLE001 – nur Zusatzinfo
        return []


def nur_anleitungen(dateien):
    """True, wenn alle gesperrten Dateien Anleitungen (PDF) sind: die tauscht das Update später (nachholen)."""
    return bool(dateien) and all(str(r).lower().endswith(".pdf") for r in dateien)


def sperr_grund(rel, ordner=None):
    """Wahrscheinlicher Grund, warum die Datei rel festgehalten wird (für die Meldung); mit ordner auch das
    Programm, das sie festhält (wer_sperrt)."""
    wer = wer_sperrt(Path(ordner) / rel) if ordner is not None else []
    if wer:
        return f"geöffnet in {', '.join(wer)} – bitte dort schließen"
    p = str(rel).replace("\\", "/").lower()
    if p.endswith(".pdf"):
        return "in einem PDF-Programm, der Explorer-Vorschau oder vom Virenscanner geöffnet"
    if p.startswith("step-import/"):
        return "der STEP-Import läuft noch – bitte im Task-Manager „STEP-Import“ beenden"
    return ("von einem anderen Programm benutzt (Virenscanner, Explorer-Vorschau oder ein zweites "
            f"{NAME}-Fenster) – bitte schließen")


def sperr_text(dateien, ordner=None):
    zeilen = [f"• {rel}: {sperr_grund(rel, ordner)}" for rel in list(dateien)[:8]]
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
        pakete[paket] = dict(groesse=datei.stat().st_size, sha256=pruefsumme(datei))
    liste = dict(format=1, programm=NAME, version=VERSION, stand=int(stand), commit=commit,
                 datum=datum or datetime.date.today().isoformat(), aenderung=aenderung, adresse=adresse,
                 dateien={rel: dict(sha256=info[rel][0], groesse=info[rel][1], paket=zuordnung[rel])
                          for rel in sorted(info)},
                 pakete=pakete)
    if not commit:
        del liste["commit"]         # öffentlich: kein Commit des privaten Repositorys (Audit H4)
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
    return str(quelle).startswith(("http://", "https://"))      # http:// lehnt holen() ab


def _oeffnen(quelle, timeout=30, ab=0):
    """Adresse (https) oder Pfad öffnen. ab > 0: nur ab diesem Byte (HTTP Range, zum Fortsetzen eines Downloads).
    urllib nimmt den Proxy aus den Windows-Interneteinstellungen bzw. HTTPS_PROXY (systemproxy())."""
    if _ist_url(quelle):
        kopf = {"User-Agent": f"{NAME} {VERSION}"}
        if ab:
            kopf["Range"] = f"bytes={ab}-"
        return urllib.request.urlopen(urllib.request.Request(quelle, headers=kopf), timeout=timeout)
    return open(quelle, "rb")


def systemproxy():
    """Für das Protokoll: welchen Proxy urllib benutzt (Windows-Interneteinstellungen bzw. HTTPS_PROXY), sonst
    'kein Proxy'. Zugangsdaten in der Adresse werden nicht mitgeschrieben."""
    try:
        p = urllib.request.getproxies().get("https") or ""
    except Exception:       # noqa: BLE001 – Registry nicht lesbar
        p = ""
    return re.sub(r"//[^/@]*@", "//", p) or "kein Proxy"


class Netzfehler(UpdateFehler):
    """Verbindung abgebrochen, Zeitüberschreitung oder Server kurz nicht erreichbar: neuer Versuch lohnt sich."""


def _netzfehler(e):
    """Lohnt nach dieser Ausnahme ein neuer Versuch (Abbruch der Leitung) oder nicht (gesperrt, Datei fehlt,
    Zertifikat, Platte voll)?"""
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (408, 425, 429, 500, 502, 503, 504)
    if isinstance(e, ssl.SSLCertVerificationError):
        return False
    if isinstance(e, urllib.error.URLError):
        return not isinstance(e.reason, ssl.SSLCertVerificationError)
    return isinstance(e, (ConnectionError, TimeoutError, socket.timeout, http.client.HTTPException, ssl.SSLError))


def _fehlertext(quelle, e):
    """Fehlermeldung mit der wahrscheinlichen Ursache (Firmennetz: Proxy, Webfilter, Firewall)."""
    if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 407, 451):
        return (f"{quelle} lässt sich nicht laden: {e}. Der Download wird gesperrt, meist von einem Firmen-Proxy "
                "oder Webfilter. Bitte die IT bitten, github.com und *.githubusercontent.com freizugeben, oder in "
                "einem anderen Netz aktualisieren.")
    if isinstance(e, ssl.SSLCertVerificationError) or (
            isinstance(e, urllib.error.URLError) and isinstance(e.reason, ssl.SSLCertVerificationError)):
        return (f"{quelle} lässt sich nicht laden: {e}. Das Zertifikat der Verbindung ist nicht vertrauenswürdig, "
                "meist prüft ein Firmen-Proxy die verschlüsselte Verbindung mit eigenem Zertifikat. Bitte die IT "
                "fragen oder in einem anderen Netz aktualisieren.")
    return f"{quelle} lässt sich nicht laden: {e}"


def _warten(sekunden, fortschritt, schlafen):
    """Vor einem neuen Versuch warten; fortschritt(0) zwischendurch, damit „Abbrechen“ wirkt."""
    ende = time.monotonic() + sekunden
    while True:
        if fortschritt:
            fortschritt(0)
        rest = ende - time.monotonic()
        if rest <= 0:
            return
        schlafen(min(0.25, rest))


def _einmal(quelle, ziel, fortschritt, timeout, grenze, gemeldet):
    """Ein Versuch, quelle nach ziel zu schreiben; ein vorhandener Anfang von ziel wird fortgesetzt (HTTP Range).
    gemeldet: [Bytes, die fortschritt schon bekommen hat] – nach einem Neubeginn werden sie nicht doppelt gezählt."""
    url = _ist_url(quelle)
    ab = ziel.stat().st_size if url and ziel.is_file() else 0
    if grenze is not None and ab > grenze:
        ziel.unlink()
        ab = 0
    with _oeffnen(quelle, timeout, ab) as r:
        status = getattr(r, "status", 200)
        if url and r.headers.get_content_type() == "text/html":
            raise UpdateFehler(
                f"{quelle} lässt sich nicht laden: statt der Datei kam eine Webseite zurück. Meist ist das die "
                "Sperrseite eines Firmen-Proxys oder Webfilters, der den Download von Programmdateien blockiert. "
                "Bitte die IT bitten, github.com und *.githubusercontent.com freizugeben, oder in einem anderen "
                "Netz aktualisieren.")
        if ab and status == 206 and str(r.headers.get("Content-Range", "")).startswith(f"bytes {ab}-"):
            modus = "ab"
        else:
            ab, modus = 0, "wb"         # Server setzt nicht fort: von vorn
        laenge = r.headers.get("Content-Length") if url else None
        erwartet = ab + int(laenge) if laenge and laenge.isdigit() else None
        n = ab
        with open(ziel, modus) as f:
            for teil in iter(lambda: r.read(STUECK), b""):
                n += len(teil)
                if grenze is not None and n > grenze:
                    raise UpdateFehler(f"{quelle} ist größer als erwartet ({grenze} Byte).")
                f.write(teil)
                if fortschritt and n > gemeldet[0]:
                    fortschritt(n - gemeldet[0])
                    gemeldet[0] = n
    if erwartet is not None and n < erwartet:
        # urllib meldet eine vorzeitig geschlossene Verbindung nicht, die Datei wäre einfach zu kurz
        raise Netzfehler(f"Verbindung nach {n:,} von {erwartet:,} Byte beendet".replace(",", "."))
    return n


def holen(quelle, ziel=None, fortschritt=None, timeout=30, grenze=None, warten=(), melden=None,
          schlafen=time.sleep):
    """Datei von einer Adresse (https) oder einem Pfad lesen; mit ziel dorthin schreiben, sonst Bytes zurück.
    fortschritt(bytes) wird je Stück aufgerufen und kann mit Abbruch abbrechen. grenze: höchstens so viele Bytes,
    sonst UpdateFehler (gegen endlose oder aufgeblähte Downloads).
    warten: Wartezeiten in s für neue Versuche nach einem Abbruch der Verbindung (Netzfehler); ein Download nach ziel
    wird dabei an der Abbruchstelle fortgesetzt. melden(text) zeigt, dass neu versucht wird."""
    if str(quelle).startswith("http://"):
        raise UpdateFehler(f"{quelle}: nur verschlüsselte Verbindungen (https) sind erlaubt.")
    if ziel is None:
        for versuch in range(len(warten) + 1):
            try:
                with _oeffnen(quelle, timeout) as r:
                    daten = r.read() if grenze is None else r.read(grenze + 1)
                if grenze is not None and len(daten) > grenze:
                    raise UpdateFehler(f"{quelle} ist größer als erwartet ({grenze} Byte).")
                return daten
            except (Abbruch, UpdateFehler):
                raise
            except Exception as e:      # Netzwerk-, HTTP- und Dateifehler einheitlich melden
                if versuch >= len(warten) or not _netzfehler(e):
                    raise UpdateFehler(_fehlertext(quelle, e)) from e
                _log.info("Update: %s, neuer Versuch in %s s (%s)", e, warten[versuch], quelle)
                _warten(warten[versuch], None, schlafen)
    ziel = Path(ziel)
    gemeldet = [0]
    for versuch in range(len(warten) + 1):
        try:
            _einmal(quelle, ziel, fortschritt, timeout, grenze, gemeldet)
            return ziel
        except Abbruch:
            raise
        except Netzfehler as e:
            fehler = e
        except UpdateFehler:
            ziel.unlink(missing_ok=True)
            raise
        except Exception as e:      # noqa: BLE001
            if not _netzfehler(e):
                raise UpdateFehler(_fehlertext(quelle, e)) from e
            fehler = e
        if versuch >= len(warten):
            n = ziel.stat().st_size if ziel.is_file() else 0
            raise Netzfehler(
                f"{quelle} lässt sich nicht laden: Die Verbindung wurde {versuch + 1}-mal unterbrochen (zuletzt: "
                f"{fehler}). Häufige Ursache in Firmennetzen: Firewall, Proxy oder Virenscanner brechen Downloads "
                "von Programmdateien ab. Bereits Geladenes bleibt erhalten, „Nach Updates suchen“ setzt fort. "
                "Sonst in einem anderen Netz aktualisieren oder die IT bitten, github.com und "
                f"*.githubusercontent.com freizugeben. ({n:,} Byte geladen, Proxy: {systemproxy()})".replace(",", "."))
        _log.info("Update: Download unterbrochen (%s), Versuch %d von %d in %s s, %s",
                  fehler, versuch + 2, len(warten) + 1, warten[versuch], quelle)
        if melden:
            melden(f"Verbindung unterbrochen, neuer Versuch {versuch + 2} von {len(warten) + 1} …")
        _warten(warten[versuch], fortschritt, schlafen)
    return ziel


def update_schluessel():
    from .update_schluessel import SCHLUESSEL
    return SCHLUESSEL


def daneben(quelle, name):
    """Adresse bzw. Pfad einer Datei im selben Ordner wie die Dateiliste (Signatur, Sperrliste)."""
    if not _ist_url(quelle):
        return str(Path(quelle).parent / name)
    return str(quelle).rsplit("/", 1)[0] + "/" + name


def signatur_erstellen(daten, privat, schluessel_id):
    """Signatur (Inhalt von Update.json.sig) zu den exakten Bytes daten. privat: Ed25519PrivateKey (nur im Build bzw.
    Lizenz-Werkzeug)."""
    sig = privat.sign(SIGNATUR_KONTEXT + bytes(daten))
    return dict(format=1, algorithmus="ed25519", schluessel_id=schluessel_id,
                signatur=base64.b64encode(sig).decode("ascii"))


def signatur_pruefen(daten, signatur, schluessel):
    """Prüft die Signatur (Bytes oder dict aus Update.json.sig) zu den exakten Bytes daten mit einem der fest
    eingebauten öffentlichen Schlüssel. Nur Ed25519, nur bekannte Schlüssel-IDs; sonst UpdateFehler."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        s = json.loads(signatur) if isinstance(signatur, (bytes, str)) else signatur
        if not isinstance(s, dict) or s.get("format") != 1 or s.get("algorithmus") != "ed25519":
            raise ValueError("unbekanntes Format oder Verfahren")
        text = (schluessel or {}).get(s.get("schluessel_id"))
        if not text:
            raise ValueError(f"unbekannter Schlüssel {s.get('schluessel_id')!r}")
        Ed25519PublicKey.from_public_bytes(base64.b64decode(text)).verify(
            base64.b64decode(str(s.get("signatur")), validate=True), SIGNATUR_KONTEXT + bytes(daten))
    except (InvalidSignature, ValueError, TypeError) as e:
        raise UpdateFehler("Die Dateiliste des Updates ist nicht gültig signiert"
                           + (f" ({e})" if str(e) else "") + ". Das Update wird nicht eingespielt, das Programm "
                           "bleibt, wie es ist.") from e


def online_liste(quelle=ADRESSE, timeout=15, schluessel=None):
    """Dateiliste laden und prüfen. Stehen öffentliche Schlüssel in update_schluessel.py (bzw. schluessel), gilt
    sie nur mit gültiger Signatur Update.json.sig – geprüft vor jeder Verwendung ihres Inhalts. Passen Liste und
    Signatur nicht zusammen, wird einmal neu geladen (der Build lädt beide gerade hoch)."""
    schluessel = update_schluessel() if schluessel is None else schluessel
    for versuch in range(2):
        daten = holen(quelle, timeout=timeout, grenze=LISTE_MAX)
        if not schluessel:
            break
        try:
            signatur_pruefen(daten, holen(daneben(quelle, SIGNATUR), timeout=timeout, grenze=SIGNATUR_MAX),
                             schluessel)
            break
        except UpdateFehler:
            if versuch:
                raise
            time.sleep(3 if _ist_url(quelle) else 0)
    try:
        liste = json.loads(daten)
    except ValueError as e:
        raise UpdateFehler(f"Die Dateiliste {quelle} ist beschädigt: {e}") from e
    liste_pruefen(liste, quelle)
    return liste


def _ganzzahl(wert, hoechstens):
    return isinstance(wert, int) and not isinstance(wert, bool) and 0 <= wert <= hoechstens


def liste_pruefen(liste, quelle=""):
    """Aufbau der Dateiliste prüfen, bevor irgendein Wert benutzt wird: Format, Pfade (sicherer_pfad, unter Windows
    ohne Groß-/Kleinschreibung eindeutig), Prüfsummen als Hex, Größen, Paketnamen, jedes Paket mit Größe."""
    if not isinstance(liste, dict) or liste.get("format") != 1 or not isinstance(liste.get("dateien"), dict) \
            or not liste["dateien"] or not isinstance(liste.get("pakete"), dict):
        raise UpdateFehler(f"Die Dateiliste {quelle} hat ein unbekanntes Format.")
    if len(liste["dateien"]) > DATEIEN_MAX or not _ganzzahl(liste.get("stand"), 10 ** 9):
        raise UpdateFehler(f"Die Dateiliste {quelle} ist unplausibel.")
    gesehen = set()
    for rel, d in liste["dateien"].items():
        if not sicherer_pfad(rel) or not isinstance(d, dict) or not _SHA.fullmatch(str(d.get("sha256"))) \
                or not _ganzzahl(d.get("groesse"), DATEI_MAX) or not _PAKET.fullmatch(str(d.get("paket"))) \
                or d["paket"] not in liste["pakete"] or rel.casefold() in gesehen:
            raise UpdateFehler(f"Die Dateiliste {quelle} enthält einen ungültigen Eintrag: {rel}")
        gesehen.add(rel.casefold())
    for name, p in liste["pakete"].items():
        if not _PAKET.fullmatch(str(name)) or not isinstance(p, dict) \
                or not _ganzzahl(p.get("groesse"), PAKET_GROESSE_MAX) \
                or ("sha256" in p and not _SHA.fullmatch(str(p["sha256"]))):
            raise UpdateFehler(f"Die Dateiliste {quelle} enthält ein ungültiges Paket: {name}")
    adresse = liste.get("adresse")
    if adresse and not (isinstance(adresse, str) and adresse.startswith(ERLAUBTE_ADRESSEN)):
        raise UpdateFehler(f"Die Dateiliste {quelle} verweist auf eine unbekannte Adresse: {adresse}")


def lizenz_zusatz(quelle=ADRESSE, timeout=10):
    """Für die Lizenz beim Update-Check: Sperrliste (Bytes oder None) neben der Dateiliste und das Datum des Servers
    (HTTP-Kopf Date, als datetime.date oder None). Fehler zählen nicht: ohne Netz bleibt alles, wie es ist."""
    adresse = daneben(quelle, SPERRLISTE)
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
    """Nur Pfade innerhalb des Programmordners, nie Daten, Angebote oder der Update-Ordner – nach Windows-Regeln:
    ohne Groß-/Kleinschreibung (daten/ = Daten/), ohne Punkt oder Leerzeichen am Ende eines Teils (Windows schneidet
    sie ab: "Daten." = Daten), ohne reservierte Gerätenamen (CON, NUL, COM1 …), Steuer- und Sonderzeichen
    (\\ : * ? " < > |, auch keine Laufwerke, UNC-Pfade oder alternativen Datenströme)."""
    if not isinstance(rel, str) or not rel or len(rel) > 400 or rel.startswith("/"):
        return False
    if any(c in _VERBOTEN or ord(c) < 32 for c in rel):
        return False
    teile = rel.split("/")
    for t in teile:
        if t in ("", ".", "..") or t != t.rstrip(" .") or t.split(".")[0].rstrip(" ").casefold() in _RESERVIERT:
            return False
    return teile[0].casefold() not in {n.casefold() for n in NIE}


def neuer(online, lokal):
    """Gibt es online einen neueren Stand als installiert?"""
    return int(online.get("stand") or 0) > int((lokal or {}).get("stand") or 0)


def paket_adresse(quelle, online, paket):
    """Pakete liegen unter "adresse" der Dateiliste (nur ERLAUBTE_ADRESSEN, https); ohne Angabe bzw. wenn die Liste
    aus einem Ordner kommt, im selben Ordner wie die Liste."""
    if not _PAKET.fullmatch(str(paket)):
        raise UpdateFehler(f"Ungültiger Paketname: {paket}")
    if not _ist_url(quelle):
        return str(Path(quelle).parent / paket)
    basis = online.get("adresse") or quelle.rpartition("/")[0] + "/"
    if not basis.startswith("https://") or (online.get("adresse") and not basis.startswith(ERLAUBTE_ADRESSEN)):
        raise UpdateFehler(f"Pakete nur von {ERLAUBTE_ADRESSEN[0]} (https), nicht von {basis}")
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
    entpackt = sum(dateien[rel]["groesse"] for rel in neu)
    return dict(neu=neu, weg=weg, pakete=pakete, groesse=groesse, entpackt=entpackt)


def platz_pruefen(ordner, plan, frei=None):
    """Genug Platz für Pakete, entpackte Dateien und eine Reserve? Sonst UpdateFehler, bevor etwas geladen wird.
    frei: freie Bytes (Tests), sonst vom Laufwerk."""
    noetig = plan.get("groesse", 0) + plan.get("entpackt", 0) + PLATZ_RESERVE
    if frei is None:
        try:
            frei = shutil.disk_usage(ordner).free
        except OSError:
            return
    if frei < noetig:
        raise UpdateFehler(f"Zu wenig Speicherplatz für das Update: nötig etwa {noetig / 1e6:.0f} MB, frei "
                           f"{frei / 1e6:.0f} MB. Bitte Platz schaffen und noch einmal versuchen.")


def schreibrecht_pruefen(ordner):
    """Darf das Programm im Programmordner schreiben (Download nach _update, Austausch)? Sonst UpdateFehler mit
    Hinweis (portable Version in einem schreibgeschützten Ordner, z. B. C:\\Programme oder Netzlaufwerk)."""
    arbeit = Path(ordner) / ARBEITSORDNER
    probe = arbeit / "schreibprobe.tmp"
    try:
        (arbeit / "pakete").mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"x")
        probe.unlink()
    except OSError as e:
        raise UpdateFehler(f"Im Programmordner {ordner} darf das Programm nicht schreiben ({e}). Das Update braucht "
                           "dort Schreibrechte: die portable Version bitte in einen eigenen Ordner mit Schreibrechten "
                           "kopieren (nicht C:\\Programme, kein schreibgeschützter Netzordner).") from e


def _vorhanden(pfad, sha):
    """Liegt pfad schon fertig und geprüft da (aus einem abgebrochenen Versuch)?"""
    try:
        return pfad.is_file() and pruefsumme(pfad) == sha
    except OSError:
        return False


def laden(ordner, quelle, online, plan, fortschritt=None, melden=None, warten=WIEDERHOLEN_S, schlafen=time.sleep):
    """Pakete laden und die gebrauchten Dateien nach _update/neu/<sha256> auspacken (geprüft).
    Bricht die Verbindung ab, wird bis zu len(warten)-mal neu versucht und an der Abbruchstelle fortgesetzt. Was ein
    früherer, abgebrochener Versuch schon geladen oder entpackt hat (verwerfen(..., download_behalten=True)), wird
    nach Prüfung der Prüfsumme weiterverwendet."""
    arbeit = Path(ordner) / ARBEITSORDNER
    neu_ordner = arbeit / "neu"
    schreibrecht_pruefen(ordner)
    neu_ordner.mkdir(parents=True, exist_ok=True)
    platz_pruefen(ordner, plan)
    gebraucht = {}
    for rel in plan["neu"]:
        d = online["dateien"][rel]
        if not _SHA.fullmatch(str(d["sha256"])):
            raise UpdateFehler(f"Ungültige Prüfsumme in der Dateiliste: {rel}")
        gebraucht.setdefault(d["paket"], {})[d["sha256"]] = d["groesse"]
    for paket in plan["pakete"]:
        info = (online.get("pakete") or {}).get(paket) or {}
        offen = {sha: g for sha, g in gebraucht[paket].items() if not _vorhanden(neu_ordner / sha, sha)}
        if not offen:           # schon beim letzten Versuch entpackt
            if fortschritt:
                fortschritt(info.get("groesse", 0))
            continue
        ziel = arbeit / "pakete" / paket
        for versuch in range(2):
            if ziel.is_file() and ziel.stat().st_size >= info.get("groesse", PAKET_GROESSE_MAX):
                if info.get("sha256") and _vorhanden(ziel, info["sha256"]):     # schon ganz geladen
                    if fortschritt:
                        fortschritt(info["groesse"])
                    datei = ziel
                    break
                ziel.unlink()   # ganz da, aber falsch: neu laden
            datei = holen(paket_adresse(quelle, online, paket), ziel, fortschritt, timeout=DOWNLOAD_TIMEOUT_S,
                          grenze=info.get("groesse", PAKET_GROESSE_MAX), warten=warten if _ist_url(quelle) else (),
                          melden=melden, schlafen=schlafen)
            if not info.get("sha256") or pruefsumme(datei) == info["sha256"]:
                break
            datei.unlink()
            if versuch or not _ist_url(quelle):
                raise UpdateFehler(f"Prüfsumme des Pakets {paket} falsch. Kommt das wiederholt vor, verändert "
                                   "vermutlich ein Proxy oder Virenscanner im Netz den Download.")
            _log.info("Update: Prüfsumme des Pakets %s falsch, wird neu geladen", paket)
        try:
            with zipfile.ZipFile(datei) as z:
                for sha, groesse in offen.items():
                    eintrag = z.getinfo(sha)
                    if eintrag.file_size != groesse or eintrag.is_dir():
                        raise UpdateFehler(f"Paket {paket}: Eintrag hat nicht die erwartete Größe")
                    ziel_datei = neu_ordner / sha
                    try:
                        with z.open(eintrag) as quelle_datei, open(ziel_datei, "wb") as f:
                            kopiert = 0      # nie mehr als angekündigt entpacken (ZIP-Bombe)
                            for teil in iter(lambda: quelle_datei.read(1 << 20), b""):
                                kopiert += len(teil)
                                if kopiert > groesse:
                                    raise UpdateFehler(f"Paket {paket}: Eintrag größer als angekündigt")
                                f.write(teil)
                        if pruefsumme(ziel_datei) != sha:
                            raise UpdateFehler(f"Prüfsumme falsch in {paket}")
                    except BaseException:
                        ziel_datei.unlink(missing_ok=True)
                        raise
        except (zipfile.BadZipFile, KeyError) as e:
            datei.unlink(missing_ok=True)
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

    journal = ordner / ARBEITSORDNER / JOURNAL
    _journal_schreiben(journal, dict(alt=alt.name, neu=list(plan["neu"]), weg=list(plan["weg"]),
                                     vorher={rel: (ordner / rel).exists() for rel in plan["neu"]}))
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
        if not fehler:
            journal.unlink(missing_ok=True)     # vollständig zurückgestellt; sonst versucht es der nächste Start
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
    journal.unlink(missing_ok=True)             # Dateiliste steht: Austausch abgeschlossen
    shutil.rmtree(neu_ordner, ignore_errors=True)
    return alt


def _journal_schreiben(pfad, daten):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_name(pfad.name + ".neu")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, pfad)


def nach_absturz(ordner):
    """Beim Start vor allem anderen: Steht noch ein Journal in _update, wurde ein Austausch unterbrochen (Absturz,
    Stromausfall, Programm beendet). Dann jede schon verschobene alte Datei zurück an ihren Platz und neu angelegte
    Dateien weg; die Dateiliste ist noch die alte. Ergebnis: None (nichts zu tun) oder Liste der Fehler ([] = alles
    zurückgestellt). Bei Fehlern bleibt das Journal für den nächsten Start stehen."""
    ordner = Path(ordner)
    journal = ordner / ARBEITSORDNER / JOURNAL
    if not journal.is_file():
        return None
    try:
        j = json.loads(journal.read_text(encoding="utf-8"))
        alt = ordner / ARBEITSORDNER / Path(str(j["alt"])).name
        neu, weg, vorher = list(j["neu"]), list(j["weg"]), dict(j.get("vorher") or {})
    except (OSError, ValueError, KeyError, TypeError):
        journal.unlink(missing_ok=True)
        return ["Journal unlesbar"]
    fehler = []
    for rel in neu + weg:
        if not sicherer_pfad(rel):
            continue
        ziel, b = ordner / rel, alt / rel
        try:
            if b.is_file():
                _zurueck(b, ziel)                       # alte Datei zurück (ersetzt die neue)
            elif rel in neu and not vorher.get(rel, True) and ziel.is_file():
                ziel.unlink()                           # vorher gab es sie nicht: neue Datei wieder weg
        except OSError as e:
            fehler.append(f"{rel}: {e}")
    if not fehler:
        journal.unlink(missing_ok=True)
    return fehler


def verwerfen(ordner, download_behalten=False):
    """Nach Abbruch oder Fehler: Download und Zwischenstand löschen (alte Dateien unter _update/alt-* bleiben).
    download_behalten: Geladenes bleibt für den nächsten Versuch (laden() prüft es und setzt fort)."""
    for name in () if download_behalten else ("neu", "pakete"):
        shutil.rmtree(Path(ordner) / ARBEITSORDNER / name, ignore_errors=True)


def zurueckstellen(ordner, plan, neu_ordner, online, dateien):
    """Gesperrte Anleitungen aus dem Plan nehmen und ihre neue Fassung nach _update/nachholen legen (nachholen()
    tauscht sie beim nächsten Start). Ergebnis: Plan ohne diese Dateien."""
    ordner = Path(ordner)
    for rel in dateien:
        if rel in plan["neu"]:
            ziel = ordner / ARBEITSORDNER / NACHHOLEN / rel
            ziel.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(neu_ordner) / online["dateien"][rel]["sha256"], ziel)
    return dict(plan, neu=[r for r in plan["neu"] if r not in dateien],
                weg=[r for r in plan["weg"] if r not in dateien])


def nachholen(ordner):
    """Beim Start: zurückgestellte Anleitungen an ihren Platz. Ergebnis: rel. Pfade, die noch gesperrt sind (bleiben
    für den nächsten Start liegen)."""
    ordner = Path(ordner)
    quelle = ordner / ARBEITSORDNER / NACHHOLEN
    offen = []
    for datei in sorted(p for p in quelle.rglob("*") if p.is_file()) if quelle.is_dir() else []:
        rel = datei.relative_to(quelle).as_posix()
        if not sicherer_pfad(rel):
            datei.unlink(missing_ok=True)
            continue
        try:
            _ersetzen(datei, ordner / rel)
        except OSError:
            offen.append(rel)
    return offen


def aufraeumen(ordner):
    """Beim Start: Reste eines Updates löschen (alte Dateien sind jetzt frei). Fehler stören nicht. Noch nicht
    nachgeholte Anleitungen (_update/nachholen) bleiben; steht noch ein Journal (nach_absturz() konnte nicht alles
    zurückstellen), bleibt alles liegen."""
    arbeit = Path(ordner) / ARBEITSORDNER
    if (arbeit / JOURNAL).is_file():
        return
    if (arbeit / NACHHOLEN).is_dir() and any(p.is_file() for p in (arbeit / NACHHOLEN).rglob("*")):
        for p in arbeit.iterdir() if arbeit.is_dir() else []:
            if p.name != NACHHOLEN:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    else:
        shutil.rmtree(arbeit, ignore_errors=True)
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
