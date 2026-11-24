"""Diagnose der Update-Umgebung (Auftrag Patrick 19.11.2026, Punkt 9): prüft vor einem Update, was es braucht,
und erklärt jeden Befund so, dass die IT damit arbeiten kann. Exportierbarer Bericht ohne Passwörter oder
Zugangsdaten (Proxy-Adressen ohne Benutzer, keine Lizenzschlüssel, keine Datenbank-Kennwörter).

Geprüft wird (jede Prüfung einzeln, ein Fehler bricht die anderen nicht ab):
- Programm: installierter Stand, Update-Schlüssel eingebaut, Schreibrecht im Programmordner, freier Speicherplatz.
- Update-Ordner: eingestellt bzw. Vorgabe, erreichbar, Dateiliste vorhanden und gültig signiert, Freigabe.
- Netz (nur wenn das Internet eine Quelle ist): Proxy (Windows, PAC-Skript, fest), DNS-Auflösung der Update-Adressen,
  TCP-Verbindung Port 443 (bzw. zum Proxy), TLS mit Zertifikatsprüfung und Aussteller (eigenes Firmenzertifikat =
  TLS-Prüfung durch den Proxy), Abruf der Dateiliste (Sperrseite, HTTP-Status).
- Datenbank: Verbindung (SELECT 1) und Schemaversion.

Ohne Qt. Netzwerkzugriffe lassen sich für Tests ersetzen (aufloesen, verbinden, tls).
"""
import datetime
import os
import shutil
import socket
import ssl
import urllib.parse
from pathlib import Path

from . import NAME, VERSION, update, update_netz, update_quellen

OK, WARNUNG, FEHLER, INFO = "ok", "warnung", "fehler", "info"
ZEICHEN = {OK: "OK", WARNUNG: "WARNUNG", FEHLER: "FEHLER", INFO: "INFO"}
# Update-Adressen: die Dateiliste liegt auf github.com, GitHub leitet den Download auf release-assets weiter
ZIELE = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")
PLATZ_MIN = 600 << 20
ZEITLIMIT = 8


def _befund(gruppe, name, stufe, text, tipp=""):
    return dict(gruppe=gruppe, name=name, stufe=stufe, text=text, tipp=tipp)


def _aufloesen(host):
    return sorted({a[4][0] for a in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})


def _verbinden(host, port):
    with socket.create_connection((host, port), timeout=ZEITLIMIT):
        return True


def _tls(host):
    """TLS-Verbindung mit Prüfung (direkt, ohne Proxy): Aussteller des Zertifikats."""
    k = update_netz.kontext()
    with socket.create_connection((host, 443), timeout=ZEITLIMIT) as roh, k.wrap_socket(roh, server_hostname=host) as s:
        z = s.getpeercert()
    aussteller = dict(x[0] for x in z.get("issuer", ()))
    return aussteller.get("organizationName") or aussteller.get("commonName") or "unbekannt"


def _abruf(adresse):
    with update._oeffnen(adresse, timeout=ZEITLIMIT) as r:
        return getattr(r, "status", 200), r.headers.get_content_type(), r.read(4096)


def pruefen(programmordner, db=None, quellen=None, aufloesen=_aufloesen, verbinden=_verbinden, tls=_tls,
            abruf=_abruf, platz=None):
    """Alle Prüfungen. Ergebnis: Liste von Befunden dict(gruppe, name, stufe, text, tipp)."""
    b = []
    ordner = Path(programmordner) if programmordner else None
    lokal = update.lokale_liste(ordner) if ordner else None
    b.append(_befund("Programm", "Installierter Stand", INFO, f"{NAME} {update.stand_text(lokal)}"
                     + ("" if lokal else " (ohne Dateiliste: Entwicklung oder sehr alte Version)")))
    b.append(_befund("Programm", "Update-Schlüssel", OK if update.update_schluessel() else FEHLER,
                     "Prüfschlüssel für signierte Updates eingebaut" if update.update_schluessel() else
                     "Kein Prüfschlüssel eingebaut: signierte Updates lassen sich nicht prüfen.",
                     "" if update.update_schluessel() else "Setup bzw. ZIP der aktuellen Version einmal neu einspielen."))
    if ordner:
        try:
            update.schreibrecht_pruefen(ordner)
            b.append(_befund("Programm", "Schreibrecht Programmordner", OK, str(ordner)))
        except update.UpdateFehler as e:
            b.append(_befund("Programm", "Schreibrecht Programmordner", FEHLER, str(e),
                             "Portable Version in einen eigenen Ordner mit Schreibrechten legen (nicht C:\\Programme). "
                             "Das Setup installiert ohnehin ins Benutzerprofil, ohne Administratorrechte."))
        try:
            frei = shutil.disk_usage(ordner).free if platz is None else platz
            b.append(_befund("Programm", "Freier Speicherplatz", OK if frei >= PLATZ_MIN else WARNUNG,
                             f"{frei / 1e9:.1f} GB frei".replace(".", ","),
                             "" if frei >= PLATZ_MIN else "Für ein großes Update werden bis zu 0,6 GB gebraucht."))
        except OSError as e:
            b.append(_befund("Programm", "Freier Speicherplatz", WARNUNG, f"nicht lesbar: {e}"))
    quellen = update_quellen.quellen(db) if quellen is None else quellen
    e = update_quellen.einstellungen(db)
    b.append(_befund("Quellen", "Einstellung", INFO, dict(update_quellen.MODI)[e["quelle"]] + "; Reihenfolge: "
                     + (", ".join(q.text() for q in quellen) or "keine")))
    for q in quellen:
        if q.art == "ordner":
            b.extend(_ordner(q))
    if any(q.art == "internet" for q in quellen):
        b.extend(_netz(next(q for q in quellen if q.art == "internet"), aufloesen, verbinden, tls, abruf))
    if db is not None:
        b.extend(_datenbank(db))
    return b


def _ordner(q):
    b = []
    try:
        da = Path(q.ort).is_dir()
    except OSError:
        da = False
    if not da:
        return [_befund("Update-Ordner", q.ort, WARNUNG, "nicht erreichbar oder nicht vorhanden",
                        "Pfad prüfen (Netzlaufwerk verbunden? UNC-Pfad \\\\Server\\Freigabe besser als Laufwerksbuchstabe). "
                        "Der Admin legt das Update dort ab: Update-Center → Verteilen.")]
    try:
        liste = q.liste()
        f = q.freigabe()
        b.append(_befund("Update-Ordner", q.ort, OK, f"{update.stand_text(liste)}, Signatur gültig"
                         + (", Pflicht-Update" if f.get("pflicht") else "")
                         + (", nur aus dem Ordner" if f.get("nur_ordner") else "")))
    except update.UpdateFehler as e:
        b.append(_befund("Update-Ordner", q.ort, FEHLER if "signiert" in str(e) else WARNUNG, str(e),
                         "Update im Ordner neu bereitstellen (Update-Center → Verteilen)."))
    return b


def _netz(q, aufloesen, verbinden, tls, abruf):
    b = []
    pac = update_netz.pac_adresse()
    prox = update_netz.proxies().get("https") or ""
    b.append(_befund("Netz", "Proxy", INFO, update_netz.text()))
    if pac and update_netz.einstellung()["proxy"] == update_netz.SYSTEM:
        b.append(_befund("Netz", "PAC-Skript", WARNUNG, f"Windows nutzt ein Proxy-Skript ({update_netz.ohne_zugang(pac)}); "
                         "das Programm kann es nicht auswerten.",
                         "Proxy im Update-Center fest eintragen (Rechner:Port) oder die Update-Adressen direkt freigeben."))
    proxy_host = urllib.parse.urlsplit(prox).hostname if prox else None
    proxy_port = urllib.parse.urlsplit(prox).port or 8080 if prox else None
    for host in ZIELE[:2]:
        try:
            ips = aufloesen(host)
            b.append(_befund("Netz", f"DNS {host}", OK, ", ".join(ips[:3])))
        except OSError as e:
            b.append(_befund("Netz", f"DNS {host}", WARNUNG if prox else FEHLER, f"nicht auflösbar ({e})",
                             "Mit Proxy löst der Proxy die Namen auf (dann unkritisch). Sonst DNS-Sperre: Domain "
                             "freigeben lassen oder Update-Ordner nutzen."))
    ziel = (proxy_host, proxy_port) if proxy_host else (ZIELE[0], 443)
    try:
        verbinden(*ziel)
        b.append(_befund("Netz", f"Verbindung {ziel[0]}:{ziel[1]}", OK, "TCP-Verbindung möglich"))
    except OSError as e:
        b.append(_befund("Netz", f"Verbindung {ziel[0]}:{ziel[1]}", FEHLER, f"keine Verbindung ({e})",
                         "Firewall bzw. Windows Defender Firewall lässt die ausgehende Verbindung nicht zu: Port 443 "
                         "(HTTPS) zu den Update-Adressen freigeben, oder Update-Ordner bzw. Update-Datei nutzen."))
    if not proxy_host:
        try:
            aussteller = tls(ZIELE[0])
            b.append(_befund("Netz", "Zertifikat", OK, f"gültig, ausgestellt von {aussteller}"))
        except ssl.SSLCertVerificationError as e:
            b.append(_befund("Netz", "Zertifikat", FEHLER, f"nicht vertrauenswürdig ({getattr(e, 'verify_message', None) or e})",
                             "Meist prüft ein Proxy/Firewall die Verbindung mit einem eigenen Firmenzertifikat: Dessen "
                             "Stammzertifikat per Gruppenrichtlinie in den Windows-Zertifikatsspeicher verteilen oder "
                             "im Update-Center als Datei eintragen. Alternativ die Update-Adressen von der TLS-Prüfung "
                             "ausnehmen."))
        except (OSError, ssl.SSLError) as e:
            b.append(_befund("Netz", "Zertifikat", WARNUNG, f"TLS-Verbindung nicht möglich ({e})"))
    try:
        status, typ, _ = abruf(q.adresse())
        if typ == "text/html":
            b.append(_befund("Netz", "Abruf Dateiliste", FEHLER, "statt der Datei kam eine Webseite (Sperrseite eines "
                             "Webfilters)", "Download von github.com und *.githubusercontent.com freigeben lassen."))
        else:
            b.append(_befund("Netz", "Abruf Dateiliste", OK, f"HTTP {status}, Datei kommt an"))
    except update.UpdateFehler as e:
        b.append(_befund("Netz", "Abruf Dateiliste", FEHLER, str(e)))
    except Exception as e:      # noqa: BLE001 – HTTP 403/407, Zeitüberschreitung usw.
        code = getattr(e, "code", None)
        tipp = {407: "Der Proxy verlangt eine Anmeldung: die Update-Adressen ohne Anmeldung freigeben lassen oder "
                     "Update-Ordner/Update-Datei nutzen (Passwörter speichert das Programm nicht).",
                403: "Gesperrt durch Proxy oder Webfilter: Freigabe der Update-Adressen beantragen."}.get(code, (
                    "Netzwerk oder Firewall verhindert den Abruf: IT-Freigabeliste an die IT geben oder Update-Ordner "
                    "nutzen."))
        b.append(_befund("Netz", "Abruf Dateiliste", FEHLER, update_netz.ohne_zugang(str(e)), tipp))
    return b


def _datenbank(db):
    try:
        try:        # Wächter aus dem Datenbank-Umbau (Schritt 5): baut eine abgebrochene Verbindung neu auf
            from . import verbindung_waechter
        except ImportError:
            verbindung_waechter = None
        if verbindung_waechter is not None and hasattr(verbindung_waechter, "erreichbar"):
            if not verbindung_waechter.erreichbar(db):
                raise ConnectionError(getattr(verbindung_waechter, "zustand_text", lambda _d: "nicht erreichbar")(db))
        else:
            db.con.execute("SELECT 1").fetchone()
        from .datenbank import SCHEMA_VERSION
        return [_befund("Datenbank", "Verbindung", OK, f"erreichbar, Schema {SCHEMA_VERSION}")]
    except Exception as e:      # noqa: BLE001
        return [_befund("Datenbank", "Verbindung", FEHLER, f"nicht erreichbar ({type(e).__name__})",
                        "Vor einem Update muss die Datenbank laufen (Sicherung vor dem Update).")]


def zusammenfassung(befunde):
    """'ok', 'warnung' oder 'fehler' (schlechteste Stufe)."""
    stufen = {x["stufe"] for x in befunde}
    return FEHLER if FEHLER in stufen else WARNUNG if WARNUNG in stufen else OK


def bericht(befunde, jetzt=None):
    """Text für die IT (Datei update_diagnose.txt). Enthält keine Passwörter oder Zugangsdaten."""
    jetzt = jetzt or datetime.datetime.now()
    zeilen = [f"Diagnose Update-Umgebung – {NAME} {VERSION}", f"Erstellt: {jetzt:%d.%m.%Y %H:%M}",
              f"Rechner: {os.environ.get('COMPUTERNAME') or socket.gethostname()}",
              f"Gesamt: {ZEICHEN[zusammenfassung(befunde)]}", ""]
    gruppe = None
    for x in befunde:
        if x["gruppe"] != gruppe:
            gruppe = x["gruppe"]
            zeilen += ["", f"== {gruppe} =="]
        zeilen.append(f"[{ZEICHEN[x['stufe']]:7}] {x['name']}: {update_netz.ohne_zugang(x['text'])}")
        if x.get("tipp"):
            zeilen.append(f"          → {x['tipp']}")
    zeilen += ["", "Benötigte Freigaben für das Online-Update (alles andere ist für Updates nicht nötig):",
               "  https://github.com (Port 443, TCP, HTTPS) – Dateiliste",
               "  https://release-assets.githubusercontent.com und https://objects.githubusercontent.com "
               "(Port 443) – Pakete (Weiterleitung von github.com)",
               "Ohne Internet: Update-Ordner im Firmennetz (SMB, Port 445, nur intern) oder Update-Datei (.rlupdate)."]
    return "\n".join(zeilen) + "\n"
