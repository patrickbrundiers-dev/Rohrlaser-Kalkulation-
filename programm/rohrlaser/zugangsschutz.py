"""Zugangsdaten verschlüsselt ablegen (Datenbank-Auftrag 19.11.2026, Schritt 2 „Rollen und Sicherheit“).

Die Passwörter der eingebetteten PostgreSQL-Datenbank stehen nie im Quellcode: sie werden beim ersten Start zufällig
erzeugt und in Daten/pg_zugang.json abgelegt. Unter Windows verschlüsselt dieses Modul sie mit der Windows-
Datenschutz-Schnittstelle (DPAPI, Bereich „dieser Rechner“): die Datei taugt auf einem anderen PC nichts, und wer sie
liest, sieht kein Passwort. Andere Systeme (Entwicklung, Prüfläufe) legen den Wert unverändert ab, die Datei ist dort
nur für den eigenen Benutzer lesbar (chmod 600).

schuetzen(text) -> dict für die JSON-Datei; lesen(wert) -> Klartext (auch für alte Dateien mit Klartext-Passwort).
"""
import base64
import sys

ART_DPAPI = "dpapi-rechner"
_ENTROPIE = b"Rohrlaser-Kalkulation pg_zugang"


def _dpapi(daten, verschluesseln):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b):
        puffer = ctypes.create_string_buffer(b, len(b))
        return Blob(len(b), ctypes.cast(puffer, ctypes.POINTER(ctypes.c_char))), puffer

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ein, _p1 = blob(daten)
    entropie, _p2 = blob(_ENTROPIE)
    aus = Blob()
    lokal_rechner = 0x4                     # CRYPTPROTECT_LOCAL_MACHINE: jeder Benutzer dieses PCs, kein anderer PC
    ohne_dialog = 0x1                       # CRYPTPROTECT_UI_FORBIDDEN
    if verschluesseln:
        ok = crypt32.CryptProtectData(ctypes.byref(ein), None, ctypes.byref(entropie), None, None,
                                      lokal_rechner | ohne_dialog, ctypes.byref(aus))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(ein), None, ctypes.byref(entropie), None, None, ohne_dialog,
                                        ctypes.byref(aus))
    if not ok:
        raise OSError(f"Windows-Datenschutz (DPAPI) meldet Fehler {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(aus.pbData, aus.cbData)
    finally:
        kernel32.LocalFree(aus.pbData)


def verfuegbar():
    return sys.platform == "win32"


def schuetzen(text):
    """Wert für die Zugangsdatei: unter Windows verschlüsselt, sonst unverändert."""
    if text is None:
        return None
    if not verfuegbar():
        return text
    roh = _dpapi(str(text).encode("utf-8"), True)
    return {"art": ART_DPAPI, "wert": base64.b64encode(roh).decode("ascii")}


def lesen(wert):
    """Klartext aus einem Wert der Zugangsdatei (verschlüsselt oder, bei älteren Dateien, Klartext)."""
    if wert is None or isinstance(wert, str):
        return wert
    if isinstance(wert, dict) and wert.get("art") == ART_DPAPI:
        return _dpapi(base64.b64decode(wert["wert"]), False).decode("utf-8")
    raise ValueError("unbekannte Art der Zugangsdaten")


def geschuetzt(wert):
    """True, wenn der Wert so abgelegt ist, wie schuetzen() ihn auf diesem System ablegen würde."""
    if wert is None:
        return True
    return isinstance(wert, dict) if verfuegbar() else isinstance(wert, str)
