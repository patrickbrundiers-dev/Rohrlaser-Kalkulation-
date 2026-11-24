"""Zugangsdaten der Lieferanten sicher ablegen (Online-Preise, Patrick 18.11.2026).

Benutzer und Passwort eines Lieferanten (z. B. OCI-Benutzer) liegen nie in der Datenbank, nie in einer Sicherung und
nie im gemeinsamen Ordner, sondern in der Windows-Anmeldeinformationsverwaltung des angemeldeten Windows-Benutzers
(advapi32 CredWriteW/CredReadW/CredDeleteW, Ziel „Rohrlaser Onlinepreise: <Lieferant>“). Jeder PC trägt sie selbst
ein. Außerhalb von Windows (Tests, Entwicklung) bleiben sie nur bis zum Programmende im Speicher. Ohne Qt."""
import ctypes
import sys

PRAEFIX = "Rohrlaser Onlinepreise: "
_SPEICHER = {}          # außerhalb von Windows: {Ziel: (Benutzer, Passwort)}


def windows():
    return sys.platform == "win32"


def _ziel(lieferant):
    return PRAEFIX + str(lieferant or "").strip()


if sys.platform == "win32":                       # pragma: no cover - nur unter Windows
    from ctypes import wintypes

    class _CRED(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    _adv = ctypes.WinDLL("advapi32", use_last_error=True)
    _adv.CredWriteW.argtypes = [ctypes.POINTER(_CRED), wintypes.DWORD]
    _adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CRED))]
    _adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _adv.CredFree.argtypes = [ctypes.c_void_p]
    _GENERIC, _LOCAL_MACHINE = 1, 2


def speichern(lieferant, benutzer, passwort):
    """Zugang ablegen (ersetzt einen vorhandenen). Ergebnis True, wenn dauerhaft gespeichert (Windows)."""
    ziel = _ziel(lieferant)
    if not windows():
        _SPEICHER[ziel] = (benutzer or "", passwort or "")
        return False
    blob = (passwort or "").encode("utf-16-le")      # pragma: no cover
    c = _CRED()
    c.Type, c.TargetName, c.UserName, c.Persist = _GENERIC, ziel, benutzer or "", _LOCAL_MACHINE
    c.CredentialBlobSize = len(blob)
    c.CredentialBlob = ctypes.cast(ctypes.create_string_buffer(blob, len(blob)), ctypes.POINTER(ctypes.c_char))
    if not _adv.CredWriteW(ctypes.byref(c), 0):
        raise OSError(ctypes.get_last_error(), "Zugangsdaten konnten nicht gespeichert werden")
    return True


def lesen(lieferant):
    """(Benutzer, Passwort) oder None."""
    ziel = _ziel(lieferant)
    if not windows():
        return _SPEICHER.get(ziel)
    p = ctypes.POINTER(_CRED)()                     # pragma: no cover
    if not _adv.CredReadW(ziel, _GENERIC, 0, ctypes.byref(p)):
        return None
    try:
        c = p.contents
        pw = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-16-le") if c.CredentialBlobSize else ""
        return c.UserName or "", pw
    finally:
        _adv.CredFree(p)


def loeschen(lieferant):
    ziel = _ziel(lieferant)
    if not windows():
        return _SPEICHER.pop(ziel, None) is not None
    return bool(_adv.CredDeleteW(ziel, _GENERIC, 0))       # pragma: no cover


def vorhanden(lieferant):
    return lesen(lieferant) is not None
