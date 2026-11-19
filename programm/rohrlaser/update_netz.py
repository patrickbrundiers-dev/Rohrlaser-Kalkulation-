"""Netzwerk für das Update (Auftrag Patrick 19.11.2026 „Updates auch hinter Firewall und offline“): Proxy und
zusätzliches Firmenzertifikat, ausdrücklich eingestellt und vom Administrator kontrollierbar.

Grundsatz: keine Umgehung von Firewall, Proxy oder Zertifikatsprüfung. Das Programm benutzt nur

- den Proxy aus den Windows-Interneteinstellungen bzw. HTTPS_PROXY (wie bisher, Einstellung „system“),
- keinen Proxy („aus“, z. B. wenn die IT die Update-Adressen direkt freigibt), oder
- einen fest eingetragenen Proxy „host:port“ (z. B. weil Windows den Proxy nur über ein PAC-Skript kennt, das urllib
  nicht auswertet).

Zertifikate: Python prüft unter Windows gegen den Zertifikatsspeicher von Windows (ssl.create_default_context lädt
ROOT und CA). Ein Firmen-Proxy mit TLS-Prüfung (Deep Packet Inspection) funktioniert deshalb, sobald die IT ihr
Stammzertifikat dort verteilt hat (Gruppenrichtlinie). Liegt es nur als Datei vor, kann es zusätzlich eingetragen
werden (PEM/CRT). Die Prüfung selbst wird nie abgeschaltet.

Proxy-Anmeldung: Benutzer und Passwort werden nie gespeichert. NTLM/Kerberos beherrscht urllib nicht; dann
entweder die zwei Update-Adressen ohne Anmeldung freigeben lassen oder das Update über den Netzwerkordner bzw. eine
im Browser geladene Update-Datei einspielen (update_verteilen.py).

Ohne Qt, ohne Datenbank.
"""
import re
import ssl
import urllib.request
from pathlib import Path

SYSTEM, AUS = "system", "aus"
_einstellung = dict(proxy=SYSTEM, zertifikat="")
_cache = {}


class NetzFehler(ValueError):
    pass


def proxy_pruefen(wert):
    """'system', 'aus' oder 'host:port' (optional mit http://) -> bereinigter Wert; sonst NetzFehler.
    Zugangsdaten in der Adresse werden abgelehnt (nie speichern)."""
    w = str(wert or "").strip()
    if not w or w.lower() in (SYSTEM, "windows"):
        return SYSTEM
    if w.lower() in (AUS, "kein", "keiner", "direkt"):
        return AUS
    if "@" in w:
        raise NetzFehler("Benutzer und Passwort gehören nicht in die Proxy-Adresse (werden nie gespeichert).")
    w = re.sub(r"^https?://", "", w).rstrip("/")
    if not re.fullmatch(r"[A-Za-z0-9.\-]+:\d{1,5}", w) or not 0 < int(w.rsplit(":", 1)[1]) < 65536:
        raise NetzFehler(f"Proxy bitte als Rechner:Port angeben, z. B. proxy.firma.local:8080 (nicht „{wert}“).")
    return w


def setzen(proxy=SYSTEM, zertifikat=""):
    """Einstellungen für alle folgenden Abrufe (update._oeffnen). Ungültige Werte -> NetzFehler, alles bleibt."""
    p = proxy_pruefen(proxy)
    z = str(zertifikat or "").strip()
    if z and not Path(z).is_file():
        raise NetzFehler(f"Zertifikatsdatei nicht gefunden: {z}")
    _einstellung.update(proxy=p, zertifikat=z)
    _cache.clear()


def einstellung():
    return dict(_einstellung)


def kontext():
    """TLS-Kontext: immer mit Prüfung von Zertifikat und Rechnernamen; Windows-Zertifikatsspeicher plus die
    eingetragene Firmenzertifikatsdatei."""
    k = ssl.create_default_context()
    z = _einstellung["zertifikat"]
    if z:
        try:
            k.load_verify_locations(cafile=z)
        except (OSError, ssl.SSLError) as e:
            raise NetzFehler(f"Zertifikatsdatei {z} lässt sich nicht lesen: {e}") from e
    return k


def proxies():
    """{'https': 'http://host:port'} bzw. {} ohne Proxy; 'system' = Windows-Interneteinstellungen bzw. HTTPS_PROXY."""
    p = _einstellung["proxy"]
    if p == AUS:
        return {}
    if p == SYSTEM:
        try:
            return {k: v for k, v in urllib.request.getproxies().items() if k in ("http", "https")}
        except Exception:       # noqa: BLE001 – Registry nicht lesbar
            return {}
    return {"https": f"http://{p}", "http": f"http://{p}"}


def oeffner():
    """urllib-Opener mit Proxy und TLS-Kontext (zwischengespeichert, bis setzen() etwas ändert)."""
    if "o" not in _cache:
        _cache["o"] = urllib.request.build_opener(urllib.request.ProxyHandler(proxies()),
                                                  urllib.request.HTTPSHandler(context=kontext()))
    return _cache["o"]


def ohne_zugang(adresse):
    """Adresse ohne Benutzer/Passwort (für Protokoll und Diagnosebericht)."""
    return re.sub(r"//[^/@]*@", "//", str(adresse or ""))


def text():
    """Für Protokoll und Anzeige: welcher Proxy gilt, ohne Zugangsdaten."""
    p = _einstellung["proxy"]
    gilt = ohne_zugang(proxies().get("https") or "") or "kein Proxy"
    if p == SYSTEM:
        return f"{gilt} (Windows-Einstellung)"
    return f"{gilt} (fest eingetragen)" if p != AUS else "kein Proxy (abgeschaltet)"


def pac_adresse():
    """Adresse eines PAC-Skripts aus den Windows-Interneteinstellungen (AutoConfigURL) oder ''. urllib wertet PAC
    nicht aus: dann den Proxy fest eintragen (Diagnose weist darauf hin)."""
    try:
        import winreg
    except ImportError:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as k:
            return str(winreg.QueryValueEx(k, "AutoConfigURL")[0] or "")
    except OSError:
        return ""
