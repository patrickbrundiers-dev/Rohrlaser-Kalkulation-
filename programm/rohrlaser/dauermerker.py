"""Merker über den Programmstart hinaus (Großes System-Update, Patrick 19.11.2026: „Berechnungen intelligent
wiederverwenden“).

Die Merker in rechenmerker.py gelten nur, solange das Programm läuft. Nach jedem Start rechnete das Programm darum
beim ersten Öffnen eines Angebots dieselben reinen Rechnungen neu, vor allem die Schneidfolge je Teil und Maschine
(dynamik.folge, 2-opt über alle Konturen): beim Angebot mit 33 STEP-Teilen gut die Hälfte der Zeit beim Öffnen.

Hier liegen solche Ergebnisse in einer kleinen SQLite-Datei neben der Datendatei (Ordner Rechenmerker). Regeln:
- Nur Rechnungen, deren Ergebnis allein von ihren Eingaben abhängt. Der Schlüssel ist eine Prüfsumme (SHA-256) über
  alle Eingaben und die Programmversion; nach einem Update rechnet das Programm also einmal neu.
- Abgelegt wird Unveränderliches als JSON; der Aufrufer prüft, ob das Ergebnis zu den Eingaben passt (sonst gilt es
  als nicht gemerkt und wird neu gerechnet).
- Jeder Fehler der Datei (gesperrt, beschädigt, kein Platz) schaltet den Merker für diesen Programmlauf ab und wird
  einmal protokolliert; gerechnet wird dann wie ohne Merker. Eine beschädigte Datei wird beim nächsten Start ersetzt.
- Höchstens GROESSE Einträge; beim Einrichten fallen die ältesten heraus.

Ohne Qt, ohne Datendatei. Sicher für mehrere Threads (eine Sperre).
"""
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from . import VERSION

ORDNER = "Rechenmerker"
DATEI = "rechenmerker.db"
GROESSE = 50_000

_sperre = threading.Lock()
_con = None
_pfad = None
_aus = False
zaehler = {"treffer": 0, "neu": 0}


def einrichten(ordner):
    """Merker im Ordner ordner (Daten/Rechenmerker) benutzen; None schaltet ihn aus."""
    global _pfad, _aus
    with _sperre:
        _schliessen()
        _aus = ordner is None
        _pfad = None if ordner is None else Path(ordner) / DATEI


def _schliessen():
    global _con
    if _con is not None:
        try:
            _con.close()
        except sqlite3.Error:
            pass
    _con = None


def _verbindung():
    """Offene Verbindung oder None (aus, nicht eingerichtet, Fehler). Unter der Sperre aufrufen."""
    global _con, _aus
    if _aus or _pfad is None:
        return None
    if _con is not None:
        return _con
    for versuch in range(2):
        try:
            _pfad.parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(_pfad, timeout=1.0, check_same_thread=False, isolation_level=None)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=OFF")       # nur ein Zwischenspeicher: lieber schnell als dauerhaft
            con.execute("CREATE TABLE IF NOT EXISTS merker (bereich TEXT NOT NULL, schluessel BLOB NOT NULL, "
                        "wert TEXT NOT NULL, zeit REAL NOT NULL, PRIMARY KEY (bereich, schluessel))")
            con.execute("CREATE INDEX IF NOT EXISTS merker_zeit ON merker (zeit)")
            n = con.execute("SELECT COUNT(*) FROM merker").fetchone()[0]
            if n > GROESSE:
                con.execute("DELETE FROM merker WHERE rowid IN (SELECT rowid FROM merker ORDER BY zeit LIMIT ?)",
                            (n - GROESSE,))
            _con = con
            return con
        except sqlite3.DatabaseError:
            if versuch == 0 and _beschaedigt_ersetzen():
                continue
            _abschalten("Rechenmerker: Datei nicht nutzbar, es wird ohne gerechnet")
            return None
        except OSError:
            _abschalten("Rechenmerker: Ordner nicht nutzbar, es wird ohne gerechnet")
            return None
    return None


def _beschaedigt_ersetzen():
    """Beschädigte Merker-Datei (nur ein Zwischenspeicher) wegräumen. True = weg."""
    try:
        for p in (_pfad, _pfad.with_name(DATEI + "-wal"), _pfad.with_name(DATEI + "-shm")):
            if p.exists():
                p.unlink()
        return True
    except OSError:
        return False


def _abschalten(text):
    global _aus
    _aus = True
    _schliessen()
    from . import protokoll
    protokoll.warnung(text)


def schluessel(*eingaben):
    """Prüfsumme über alle Eingaben (JSON, sortiert) und die Programmversion."""
    text = json.dumps([VERSION, eingaben], sort_keys=True, default=repr, ensure_ascii=False, allow_nan=True)
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).digest()


def holen(bereich, s):
    """Gemerkter Wert (aus JSON) oder None."""
    with _sperre:
        con = _verbindung()
        if con is None:
            return None
        try:
            r = con.execute("SELECT wert FROM merker WHERE bereich=? AND schluessel=?", (bereich, s)).fetchone()
        except sqlite3.Error:
            _abschalten("Rechenmerker: Lesen gescheitert, es wird ohne gerechnet")
            return None
    if r is None:
        zaehler["neu"] += 1
        return None
    try:
        wert = json.loads(r[0])
    except ValueError:
        return None
    zaehler["treffer"] += 1
    return wert


def ablegen(bereich, s, wert):
    """Wert (JSON-fähig) merken; Fehler schalten den Merker ab."""
    try:
        text = json.dumps(wert, allow_nan=True)
    except (TypeError, ValueError):
        return
    with _sperre:
        con = _verbindung()
        if con is None:
            return
        try:
            con.execute("INSERT INTO merker (bereich, schluessel, wert, zeit) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT (bereich, schluessel) DO UPDATE SET wert=excluded.wert, zeit=excluded.zeit",
                        (bereich, s, text, time.time()))
        except sqlite3.Error:
            _abschalten("Rechenmerker: Schreiben gescheitert, es wird ohne gerechnet")


def stand():
    """dict(treffer, neu, eintraege, aus) für die Diagnose."""
    with _sperre:
        con = _verbindung() if not _aus else None
        try:
            n = con.execute("SELECT COUNT(*) FROM merker").fetchone()[0] if con is not None else 0
        except sqlite3.Error:
            n = 0
    return dict(zaehler, eintraege=n, aus=_aus or _pfad is None)
