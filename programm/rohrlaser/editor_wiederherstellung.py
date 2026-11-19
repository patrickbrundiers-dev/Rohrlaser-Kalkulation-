"""Automatische Wiederherstellung im Teile-Editor (Plan 3D-Editor modernisieren 19.11.2026, A3).

Der Editor (teile_editor.EditorRahmen) hält seinen Stand nur im Speicher. Stürzt das Programm ab oder geht der
Rechner aus, wäre die Arbeit seit dem Öffnen verloren. Deshalb:

- Bei jedem neuen Rückgängig-Schritt schreibt der Editor seinen Stand (EditorRahmen.zustand) als kleine JSON-Datei in
  den Ordner „Wiederherstellung“ neben der lokalen Datenbank (je PC, nie in die Position oder die Datenbank).
- Schließt der Editor normal (Übernehmen oder Abbrechen), wird die Datei gelöscht.
- Bleibt eine Datei liegen (Absturz), bietet der Editor beim nächsten Öffnen derselben Position den Stand an. Erst ein
  Klick auf „Wiederherstellen“ setzt ihn (ein Schritt für Rückgängig); ohne Klick bleibt alles wie gespeichert.

Geschrieben wird atomar (erst .tmp, dann umbenennen): ein Absturz während des Schreibens hinterlässt nie eine halbe
Datei. Unlesbare oder fremde Dateien werden ignoriert und gelöscht.
"""
import datetime
import json
import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from . import stil

ORDNER = "Wiederherstellung"
FASSUNG = 1
MAX_ALTER_TAGE = 14         # ältere Sicherungen werden beim nächsten Öffnen still gelöscht


def ordner(db):
    """Ordner der Sicherungen (neben der lokalen Datenbank) oder None ohne Datenbank."""
    pfad = getattr(db, "pfad", None)
    if pfad is None:
        return None
    return Path(pfad).parent / ORDNER


def schluessel(art, dialog):
    """Name der Sicherung je Editor: Art und Position (Kennung); neue Teile ohne Kennung teilen sich „neu“."""
    p = getattr(dialog, "p", None)
    pid = p.get("id") if isinstance(p, dict) else None
    teil = str(pid) if pid not in (None, "") else "neu"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{art}-{teil}")


def datei(db, schl):
    o = ordner(db)
    return None if o is None else o / f"{schl}.json"


def sichern(db, schl, zustand, titel=""):
    """Stand schreiben (atomar). Ergebnis: True, wenn geschrieben. Fehler (Rechte, voll) brechen nie den Editor ab."""
    pfad = datei(db, schl)
    if pfad is None:
        return False
    inhalt = dict(fassung=FASSUNG, zeit=datetime.datetime.now().isoformat(timespec="seconds"), titel=titel,
                  zustand=zustand)
    try:
        text = json.dumps(inhalt, ensure_ascii=False, default=repr)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = pfad.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, pfad)
        return True
    except (OSError, TypeError, ValueError):
        return False


def lesen(db, schl):
    """Gesicherter Stand {zeit, titel, zustand} oder None (keine, unlesbar, fremde Fassung, zu alt – dann gelöscht)."""
    pfad = datei(db, schl)
    if pfad is None or not pfad.is_file():
        return None
    try:
        inhalt = json.loads(pfad.read_text(encoding="utf-8"))
        if not isinstance(inhalt, dict) or inhalt.get("fassung") != FASSUNG or not isinstance(inhalt.get("zustand"), dict):
            raise ValueError("fremde Fassung")
        zeit = datetime.datetime.fromisoformat(inhalt["zeit"])
        if (datetime.datetime.now() - zeit).days > MAX_ALTER_TAGE:
            raise ValueError("zu alt")
        return inhalt
    except (OSError, ValueError, TypeError, KeyError):
        loeschen(db, schl)
        return None


def loeschen(db, schl):
    pfad = datei(db, schl)
    if pfad is None:
        return
    for p in (pfad, pfad.with_suffix(".tmp")):
        try:
            p.unlink()
        except OSError:
            pass


def zeit_text(inhalt):
    """„heute 14:32“, „gestern 09:05“ oder „17.11. 16:40“."""
    try:
        z = datetime.datetime.fromisoformat(inhalt["zeit"])
    except (KeyError, TypeError, ValueError):
        return "unbekannt"
    heute = datetime.date.today()
    tag = "heute" if z.date() == heute else "gestern" if (heute - z.date()).days == 1 else z.strftime("%d.%m.")
    return f"{tag} {z.strftime('%H:%M')}"


class Leiste(QFrame):
    """Leiste oben im Editor: „Ungespeicherte Änderungen … gefunden“ mit Wiederherstellen und Verwerfen. Bleibt
    sichtbar, bis man sich entscheidet (eine Einblendung wäre nach Sekunden weg)."""
    wiederherstellen = Signal()
    verwerfen = Signal()

    def __init__(self, zeit, neu=False):
        super().__init__()
        self.setObjectName("wiederherstellung")
        self.setStyleSheet(stil.umsetzen("QFrame#wiederherstellung { background: #FFF4E5; border: 1px solid #F5C27A; "
                                         "border-radius: 6px; } QLabel { background: transparent; border: none; }"))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        was = "eines neuen Teils" if neu else "an diesem Teil"
        self.text = QLabel(f"<b>Ungespeicherte Änderungen {was} gefunden</b> (Stand {zeit}). Das Programm wurde "
                           "damals nicht normal beendet. Den Stand wiederherstellen?")
        self.text.setWordWrap(True)
        lay.addWidget(self.text, 1)
        self.ja = QPushButton("Wiederherstellen")
        self.ja.setToolTip("Setzt den gesicherten Stand in den Editor (mit Strg+Z wieder zurück)")
        self.ja.clicked.connect(self.wiederherstellen)
        self.nein = QPushButton("Verwerfen")
        self.nein.setToolTip("Gesicherten Stand nicht verwenden; es gilt der gespeicherte Stand der Position")
        self.nein.clicked.connect(self.verwerfen)
        lay.addWidget(self.ja)
        lay.addWidget(self.nein)
