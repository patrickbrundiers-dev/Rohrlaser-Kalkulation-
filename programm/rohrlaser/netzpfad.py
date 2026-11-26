"""Netzlaufwerke nach einem Windows-Neustart (Auftrag Patrick 26.11.2026, Windows-Update-Sicherheit).

Ein verbundenes Netzlaufwerk (z. B. Z: → \\\\server\\freigabe) ist nach dem Neustart oft erst „getrennt“: Windows
stellt die Verbindung erst her, wenn jemand im Explorer darauf klickt, oder gar nicht, solange das Netz noch fehlt.
Der gemeinsame Ordner Z:\\Rohrlaser galt dann als „nicht erreichbar“, obwohl \\\\server\\freigabe\\Rohrlaser längst
erreichbar war.

merken(pfad): solange der Ordner über den Laufwerksbuchstaben erreichbar ist, wird der UNC-Pfad dahinter
(WNetGetConnectionW) im Benutzerprofil gemerkt (netzlaufwerke.json). ersatz(pfad): ist der Laufwerksbuchstabe nicht
erreichbar, liefert es den gemerkten UNC-Pfad, wenn der erreichbar ist. Es wird nichts verbunden und nichts an der
Einstellung geändert; derselbe Ordner wird nur auf dem zweiten Weg angesprochen.

Ohne Qt. Unter anderen Systemen als Windows tut es nichts.
"""
import json
import os
import sys
import time
from pathlib import Path, PureWindowsPath

from . import orte

DATEI = "netzlaufwerke.json"
_gemerkt_laufwerke = set()      # in diesem Lauf schon nachgesehen (WNetGetConnection nur einmal je Laufwerk)
NICHT_DA_S = 60                 # UNC-Weg auch nicht erreichbar: so lange nicht noch einmal versuchen (Netz ganz weg
_nicht_da = {}                  # dauert jeder Versuch sonst die SMB-Wartezeit doppelt); Pfad -> Zeitpunkt


def laufwerk(pfad):
    """'Z:' bei einem Pfad mit Laufwerksbuchstaben, sonst None (UNC, relativ, andere Systeme)."""
    d = PureWindowsPath(str(pfad)).drive
    return d.upper() if len(d) == 2 and d[1] == ":" else None


def unc_von_laufwerk(buchstabe):
    """UNC-Pfad hinter einem verbundenen Laufwerk ('\\\\server\\freigabe') oder None."""
    if sys.platform != "win32" or not buchstabe:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        mpr = ctypes.WinDLL("mpr")
        laenge = wintypes.DWORD(1024)
        puffer = ctypes.create_unicode_buffer(laenge.value)
        # 0 = NO_ERROR; ERROR_CONNECTION_UNAVAIL (1201) liefert den gemerkten Pfad einer getrennten Verbindung auch
        r = mpr.WNetGetConnectionW(buchstabe, puffer, ctypes.byref(laenge))
        return puffer.value if r in (0, 1201) and puffer.value.startswith("\\\\") else None
    except (OSError, AttributeError):
        return None


def _datei(umgebung=None):
    return orte.lokaler_ordner(umgebung) / orte.ORDNER_INSTALLIERT / DATEI


def _lesen(umgebung=None):
    try:
        d = json.loads(_datei(umgebung).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def merken(pfad, umgebung=None, abfrage=unc_von_laufwerk):
    """Laufwerk des (erreichbaren) Pfads mit seinem UNC-Pfad merken. Ergebnis: UNC-Pfad oder None."""
    lw = laufwerk(pfad)
    if lw is None or lw in _gemerkt_laufwerke:
        return None
    _gemerkt_laufwerke.add(lw)
    unc = abfrage(lw)
    if not unc:
        return None
    karte = _lesen(umgebung)
    if karte.get(lw) != unc:
        karte[lw] = unc
        try:
            ziel = _datei(umgebung)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            tmp = ziel.with_name(ziel.name + ".neu")
            tmp.write_text(json.dumps(karte, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, ziel)
        except OSError:
            pass
    return unc


def ersatz(pfad, umgebung=None, abfrage=unc_von_laufwerk, ist_ordner=os.path.isdir):
    """Pfad auf dem UNC-Weg, wenn der Laufwerksbuchstabe nicht erreichbar ist, der UNC-Pfad aber schon; sonst
    None. Erst die Windows-Angabe zum Laufwerk (auch bei getrennter Verbindung), dann die gemerkte."""
    lw = laufwerk(pfad)
    if lw is None:
        return None
    schluessel = os.path.normcase(str(pfad))
    if time.monotonic() - _nicht_da.get(schluessel, -NICHT_DA_S) < NICHT_DA_S:
        return None
    rest = str(PureWindowsPath(str(pfad)))[len(lw):].lstrip("\\/")
    for unc in dict.fromkeys((abfrage(lw), _lesen(umgebung).get(lw))):
        if not unc:
            continue
        kandidat = str(PureWindowsPath(unc) / rest) if rest else unc
        if ist_ordner(kandidat):
            _nicht_da.pop(schluessel, None)
            return Path(kandidat)
    _nicht_da[schluessel] = time.monotonic()
    return None
