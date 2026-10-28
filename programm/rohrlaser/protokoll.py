"""Fehlerprotokoll: unerwartete Fehler nie still verschlucken.

Das ausgelieferte Programm hat keine Konsole. Ein Fehler, den der Programmcode nicht abfängt (z. B. in einer
Knopf-Aktion), landet deshalb in der Datei Daten/Protokoll/fehler.log (höchstens 3 × 1 MB) und wird mit einer
Meldung angezeigt; die Details lassen sich kopieren und weitergeben. Das Programm läuft danach weiter.
"""
import logging
import logging.handlers
import sys
import threading
import traceback
from pathlib import Path

DATEI = "fehler.log"
_log = logging.getLogger("rohrlaser")
_zeigen = None          # Funktion(text, details) für die Meldung, None = keine Meldung (Tests, ohne Oberfläche)
_in_meldung = False


def einrichten(ordner, zeigen=None):
    """Protokoll in ordner/fehler.log schreiben und sys.excepthook sowie threading.excepthook setzen. zeigen(text,
    details) zeigt die Meldung (Vorgabe: Dialog). Ergebnis: Pfad der Protokolldatei oder None, wenn der Ordner nicht
    beschreibbar ist (dann nur die Meldung)."""
    global _zeigen
    _zeigen = zeigen if zeigen is not None else meldung_dialog
    pfad = None
    try:
        Path(ordner).mkdir(parents=True, exist_ok=True)
        pfad = Path(ordner) / DATEI
        h = logging.handlers.RotatingFileHandler(pfad, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _log.handlers = [h]
        _log.setLevel(logging.INFO)
    except OSError:
        pfad = None
    sys.excepthook = _haken
    threading.excepthook = lambda a: _haken(a.exc_type, a.exc_value, a.exc_traceback)
    return pfad


def info(text):
    """Eintrag ins Protokoll (z. B. Programmstart mit Version)."""
    _log.info(text)


def nebenbei(wert, wozu):
    """Fehler in einer Nebensache (Einstellung merken, Vorschaubild, Zusatzinfo): das Programm läuft ohne sie weiter,
    der Fehler kommt aber ins Protokoll statt still zu verschwinden. Lesemodus ist Absicht und wird nicht notiert."""
    if ist_lesemodus(wert):
        return
    _log.info("%s nicht möglich: %s", wozu,
              "".join(traceback.format_exception(type(wert), wert, wert.__traceback__)).rstrip())


def ist_lesemodus(wert):
    """Abgewiesener Schreibversuch im Lesemodus (Lizenz): Ausnahme Lesemodus oder SQLite 'readonly database'."""
    import sqlite3
    return type(wert).__name__ == "Lesemodus" or (isinstance(wert, sqlite3.OperationalError)
                                                   and "readonly" in str(wert))


_lesemodus_zuletzt = 0.0


def _lesemodus_melden(wert):
    """Kein Fehler, sondern Absicht: kurzer Hinweis statt Fehlermeldung, höchstens alle 20 Sekunden ein Fenster."""
    global _lesemodus_zuletzt, _in_meldung
    import time
    _log.info("Lesemodus: Änderung abgewiesen (%s)", wert)
    if _zeigen is None or _in_meldung or time.monotonic() - _lesemodus_zuletzt < 20:
        return
    _lesemodus_zuletzt = time.monotonic()
    from PySide6.QtWidgets import QApplication, QMessageBox
    if QApplication.instance() is None or _zeigen is not meldung_dialog:
        return
    _in_meldung = True
    try:
        text = str(wert) if type(wert).__name__ == "Lesemodus" else (
            "Lesemodus – Ändern ist erst mit gültiger Lizenz möglich (Hilfe → Lizenz …).")
        QMessageBox.information(None, "Lesemodus", text + "\n\nAnsehen, Daten exportieren und Sicherungen gehen weiter.")
    finally:
        _in_meldung = False


def _haken(art, wert, tb):
    global _in_meldung
    if issubclass(art, KeyboardInterrupt):
        sys.__excepthook__(art, wert, tb)
        return
    if ist_lesemodus(wert):
        _lesemodus_melden(wert)
        return
    details = "".join(traceback.format_exception(art, wert, tb))
    _log.error("Unerwarteter Fehler\n%s", details)
    if sys.__stderr__ is not None:
        try:
            sys.__stderr__.write(details)
        except (OSError, ValueError):
            pass
    if _zeigen is None or _in_meldung:
        return
    _in_meldung = True
    try:
        _zeigen(f"{art.__name__}: {wert}", details)
    except Exception:                   # noqa: BLE001, S110 – die Meldung selbst darf nie einen zweiten Fehler auslösen
        pass
    finally:
        _in_meldung = False


def meldung_dialog(text, details):
    from PySide6.QtWidgets import QApplication, QMessageBox
    if QApplication.instance() is None:
        return
    pfad = next((h.baseFilename for h in _log.handlers if hasattr(h, "baseFilename")), None)
    m = QMessageBox(QMessageBox.Warning, "Unerwarteter Fehler",
                    "Bei dieser Aktion ist ein unerwarteter Fehler aufgetreten. Die Aktion wurde nicht vollständig "
                    "ausgeführt. Bereits gespeicherte Daten bleiben erhalten, das Programm läuft weiter.\n\n" + text
                    + (f"\n\nDetails stehen im Protokoll:\n{pfad}" if pfad else ""))
    m.setDetailedText(details)
    m.exec()
