"""Programmlauf überwachen: unerwartetes Ende erkennen, Reste aufräumen, riskante Stellen absichern (Auftrag Patrick
26.11.2026 „Systemunabhängigkeit, Windows-Update-Sicherheit und langfristige Stabilität“).

1. Laufmarker (Daten/laeuft.json): beginnen() legt ihn nach dem Holen der Datensperre an, beenden() entfernt ihn
   beim normalen Ende. Liegt er beim nächsten Start noch da, endete der letzte Lauf unerwartet (Windows-Neustart
   für Updates, Stromausfall, Absturz, Task-Manager). Weil die Datensperre nur ein Programm je Datenordner zulässt,
   stammt ein vorhandener Marker immer von einem beendeten Lauf.
2. reste_aufraeumen(): halb geschriebene Dateien eines unterbrochenen Laufs (Zwischendateien *.neu/*.tmp/*.merk im
   Datenordner, Sicherungen ohne Beschreibung .json, pg_dump-Zwischenstände *.pgdump.neu) kommen nach
   Daten/Sicherung/Unvollstaendig/<Zeit>. Nichts wird gelöscht. Eine halbe Sicherung zählt danach nicht mehr als
   „heute schon gesichert“.
3. Riskante Stellen (markieren/entmarken/blockiert): Stellen, an denen ein Fehler im Treiber das ganze Programm
   ohne Meldung beendet (OpenGL nach einem Grafiktreiber-Update), schreiben vorher einen Marker in den Ordner
   Waechter des Benutzerprofils (je PC und Benutzer). Bleibt er stehen, ist das Programm genau dort gestorben;
   die Stelle bleibt für diese Programmversion gesperrt (z. B. 3D mit Software statt OpenGL), bis eine neue
   Programmversion sie einmal neu versucht oder freigeben() sie zurücksetzt.

Ohne Qt. Alle Fehler beim Schreiben der Marker stören den Programmlauf nicht.
"""
import datetime
import getpass
import json
import os
import shutil
import socket
import time
from pathlib import Path

from . import VERSION, orte, zahlen

MARKER = "laeuft.json"
WAECHTER = "Waechter"
UNVOLLSTAENDIG = "Unvollstaendig"
RESTE_ALTER_S = 120                 # nur Dateien, die mindestens so alt sind (nie eine gerade entstehende)
# Zwischendateien des atomaren Schreibens im Datenordner (Name + Endung), siehe orte.merken, pg_lokal, datenspeicher
RESTE_DATEN = ("*.neu", "*.tmp", "*.merk")
_bestaetigt = set()                 # riskante Stellen, die in diesem Lauf schon einmal gut gegangen sind




def _schreiben(pfad, daten):
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_name(pfad.name + ".neu")
    tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, pfad)


def _lesen(pfad):
    try:
        d = json.loads(Path(pfad).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}           # halb geschriebener Marker: der Lauf endete trotzdem unerwartet


def _benutzer():
    try:
        return getpass.getuser()
    except Exception:       # noqa: BLE001 - ohne Benutzernamen weiter
        return ""


# ------------------------------------------------------------------------------------------------ 1. Laufmarker
def beginnen(daten):
    """Laufmarker für diesen Programmlauf anlegen. Ergebnis: Inhalt des alten Markers (dict, mindestens mit
    'datei'), wenn der letzte Lauf unerwartet endete, sonst None."""
    pfad = Path(daten) / MARKER
    vorher = None
    try:
        if pfad.is_file():
            vorher = dict(_lesen(pfad), datei=str(pfad))
    except OSError:
        vorher = None
    try:
        _schreiben(pfad, dict(pid=os.getpid(), version=VERSION, seit=zahlen.jetzt_text(), rechner=socket.gethostname(),
                              benutzer=_benutzer()))
    except OSError:
        pass
    return vorher


def beenden(daten, umgebung=None):
    """Normales Ende (auch Windows-Abmeldung, sobald alles geschlossen ist): Laufmarker entfernen, dazu die Marker
    riskanter Stellen dieses Laufs, die nie zu Ende kamen (z. B. 3D-Ansicht nie gezeichnet): das Programm ist dort
    nicht gestorben."""
    try:
        (Path(daten) / MARKER).unlink(missing_ok=True)
    except OSError:
        pass
    try:
        for m in waechter_ordner(umgebung).glob("*.laeuft.json"):
            if _lesen(m).get("pid") == os.getpid():
                m.unlink(missing_ok=True)
    except OSError:
        pass


def text_unterbrochen(vorher, reste=()):
    """Meldung für den Start nach einem unerwarteten Ende."""
    seit = vorher.get("seit") or "unbekannt"
    version = f", Version {vorher['version']}" if vorher.get("version") else ""
    t = (f"Das Programm wurde zuletzt nicht normal beendet (gestartet {seit.replace('T', ' ')}{version}), z. B. durch "
         "einen Windows-Neustart, einen Stromausfall oder einen Absturz. Gespeicherte Daten sind erhalten; die "
         "Datenbank hat sich beim Start selbst wiederhergestellt.")
    if reste:
        t += (f" {len(reste)} unvollständige Datei(en) aus dem unterbrochenen Lauf liegen jetzt in "
              f"Sicherung\\{UNVOLLSTAENDIG} (nichts gelöscht).")
    return t


# ------------------------------------------------------------------------------------------------ 2. Reste
def _alt_genug(p, jetzt):
    try:
        return jetzt - p.stat().st_mtime >= RESTE_ALTER_S
    except OSError:
        return False


def _zeitpunkt(seit):
    try:
        return datetime.datetime.fromisoformat(str(seit)).timestamp()
    except (TypeError, ValueError):
        return None


def reste_finden(daten, seit=None, jetzt=None):
    """Halb geschriebene Dateien im Datenordner und in Daten/Sicherung aus dem unterbrochenen Lauf (geändert ab
    seit = Startzeit laut Laufmarker; ohne lesbare Startzeit: der letzten 2 Tage). Liste von Pfaden. Ältere
    Sicherungen früherer Programmstände ohne .json bleiben so unberührt."""
    daten = Path(daten)
    jetzt = time.time() if jetzt is None else jetzt
    ab = _zeitpunkt(seit)
    ab = (ab - 60) if ab is not None else jetzt - 2 * 86400
    funde = []
    try:
        for muster in RESTE_DATEN:
            funde += [p for p in daten.glob(muster) if p.is_file()]
        sicherung = daten / "Sicherung"
        if sicherung.is_dir():
            funde += [p for p in sicherung.glob("*.pgdump.neu") if p.is_file()]
            # Sicherung ohne Beschreibung: Datenbank.sicherung schreibt die .json als Letztes
            funde += [p for p in sicherung.glob(f"{Path(orte.DATENDATEI).stem}_*.db")
                      if p.is_file() and not p.with_suffix(".json").is_file()]
    except OSError:
        return []
    return sorted({p for p in funde if _alt_genug(p, jetzt) and _geaendert(p) >= ab})


def _geaendert(p):
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def reste_aufraeumen(daten, seit=None, jetzt=None):
    """Reste nach Daten/Sicherung/Unvollstaendig/<Zeit> verschieben (nur nach einem unerwarteten Ende aufrufen).
    Ergebnis: Liste der neuen Pfade."""
    funde = reste_finden(daten, seit, jetzt)
    if not funde:
        return []
    ziel = Path(daten) / "Sicherung" / UNVOLLSTAENDIG / datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    erg = []
    for p in funde:
        try:
            ziel.mkdir(parents=True, exist_ok=True)
            neu = ziel / p.name
            n = 1
            while neu.exists():
                neu = ziel / f"{p.name}.{n}"
                n += 1
            shutil.move(str(p), str(neu))
            erg.append(neu)
        except OSError:
            continue        # gesperrt (Virenscanner): beim nächsten Start wieder
    return erg


# ------------------------------------------------------------------------------------------------ 3. Riskante Stellen
def waechter_ordner(umgebung=None):
    return orte.lokaler_ordner(umgebung) / orte.ORDNER_INSTALLIERT / WAECHTER


def _marker(name, umgebung=None):
    return waechter_ordner(umgebung) / f"{name}.laeuft.json"


def _sperre(name, umgebung=None):
    return waechter_ordner(umgebung) / f"{name}.gesperrt.json"


def markieren(name, umgebung=None):
    """Vor einer riskanten Stelle. Ist sie in diesem Lauf schon gut gegangen, passiert nichts (keine Dateizugriffe
    bei jedem Bild)."""
    if name in _bestaetigt:
        return
    try:
        _schreiben(_marker(name, umgebung), dict(pid=os.getpid(), version=VERSION, seit=zahlen.jetzt_text()))
    except OSError:
        pass


def entmarken(name, umgebung=None):
    """Nach der riskanten Stelle (gut gegangen oder sauber mit Fehler abgefangen): Marker weg."""
    if name in _bestaetigt:
        return
    _bestaetigt.add(name)
    try:
        _marker(name, umgebung).unlink(missing_ok=True)
    except OSError:
        pass


def blockiert(name, umgebung=None):
    """Ist die Stelle gesperrt? Ergebnis: dict(version, seit, …) der Sperre oder None. Ein Marker eines früheren
    Laufs wird dabei zur Sperre (das Programm ist an dieser Stelle gestorben). Sperren einer anderen
    Programmversion gelten nicht mehr (neue Version: einmal neu versuchen)."""
    try:
        m = _marker(name, umgebung)
        if m.is_file():
            d = _lesen(m)
            if d.get("pid") != os.getpid():
                _schreiben(_sperre(name, umgebung), dict(d, gesperrt=zahlen.jetzt_text()))
                m.unlink(missing_ok=True)
                try:
                    from . import protokoll
                    protokoll.info(f"Programm ist zuletzt an der Stelle „{name}“ gestorben (seit {d.get('seit')}); "
                                   f"gesperrt bis zur nächsten Programmversion")
                except (OSError, RuntimeError, ValueError):     # Protokoll ist kein Muss
                    pass
        s = _sperre(name, umgebung)
        if not s.is_file():
            return None
        d = _lesen(s)
        if d.get("version") != VERSION:
            s.unlink(missing_ok=True)
            return None
        return d
    except OSError:
        return None


def freigeben(name, umgebung=None):
    """Sperre von Hand aufheben (nächster Versuch an der Stelle)."""
    _bestaetigt.discard(name)
    for p in (_marker(name, umgebung), _sperre(name, umgebung)):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
