"""Fehlerprotokoll: unerwartete Fehler nie still verschlucken.

Das ausgelieferte Programm hat keine Konsole. Ein Fehler, den der Programmcode nicht abfängt (z. B. in einer
Knopf-Aktion), landet deshalb in der Datei Daten/Protokoll/fehler.log (höchstens 3 × 1 MB) und wird mit einer
Meldung angezeigt; die Details lassen sich kopieren und weitergeben. Das Programm läuft danach weiter.

Harte Abstürze (das Programm schließt sich ohne Meldung, z. B. ein Fehler in Qt oder im Grafiktreiber) schreibt
faulthandler seit 16.11.2026 nach Daten/Protokoll/absturz.log: welche Programmstelle zuletzt lief.

Seit der Systemprüfung 17.11.2026 (LOG-01, ERR-01): jede Zeile nennt Modul und Funktion, beim Start steht eine
Kopfzeile mit Version, Kürzel und Datenspeicher; Zugangsdaten (Passwort, Token, Schlüssel) werden vor dem Schreiben
durch *** ersetzt. warnung() protokolliert einen bewusst abgefangenen Fehler mit Stacktrace (WARNING, ohne Meldung),
höchstens WARNUNG_JE_STELLE-mal je Programmstelle und Programmlauf.
"""
import faulthandler
import logging
import logging.handlers
import re
import sys
import threading
import traceback
from pathlib import Path

DATEI = "fehler.log"
ABSTURZ = "absturz.log"
_absturz_datei = None   # offen halten, solange das Programm läuft (faulthandler schreibt beim Absturz hinein)
_log = logging.getLogger("rohrlaser")
_zeigen = None          # Funktion(text, details) für die Meldung, None = keine Meldung (Tests, ohne Oberfläche)
_in_meldung = False
SUPPORT = None          # Funktion() für den Knopf „Support-Paket“ in der Meldung (Hauptfenster.support_paket), None = ohne
FORMAT = "%(asctime)s %(levelname)s %(module)s.%(funcName)s | %(message)s"
WARNUNG_JE_STELLE = 3
_warnungen = {}         # (Datei, Zeile) -> Anzahl in diesem Programmlauf
fehler_anzahl = 0       # unerwartete Fehler in diesem Programmlauf (Diagnose)

# Zugangsdaten nie ins Protokoll (LOG-01): Schlüssel=Wert bzw. "Schlüssel": "Wert" und Bearer-Token
_GEHEIM = re.compile(r"(?i)\b(password|passwort|passwd|pwd|kennwort|token|secret|geheim|api[_-]?key|seed|tresor"
                     r"|notfallcode)(\"?\s*[:=]\s*\"?)([^\s\"',;&}]+)")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+")


def bereinigen(text):
    """Zugangsdaten in text durch *** ersetzen (Passwort=…, "token": "…", Bearer …)."""
    return _BEARER.sub(r"\1***", _GEHEIM.sub(r"\1\2***", str(text)))


class _Format(logging.Formatter):
    def format(self, record):
        return bereinigen(super().format(record))


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
        h.setFormatter(_Format(FORMAT))
        _log.handlers = [h]
        _log.setLevel(logging.INFO)
    except OSError:
        pfad = None
    absturz_einrichten(ordner)
    sys.excepthook = _haken
    threading.excepthook = lambda a: _haken(a.exc_type, a.exc_value, a.exc_traceback)
    return pfad


def absturz_einrichten(ordner):
    """Harte Abstürze nach ordner/absturz.log (angehängt, höchstens 1 MB, dann neu). Ergebnis: Pfad oder None."""
    global _absturz_datei
    try:
        pfad = Path(ordner) / ABSTURZ
        modus = "w" if pfad.exists() and pfad.stat().st_size > 1_000_000 else "a"
        datei = open(pfad, modus, encoding="utf-8")      # noqa: SIM115 – bleibt bis zum Programmende offen
        faulthandler.enable(datei, all_threads=True)
    except (OSError, ValueError, RuntimeError):
        return None
    if _absturz_datei is not None:
        try:
            _absturz_datei.close()
        except OSError:
            pass
    _absturz_datei = datei
    return pfad


def info(text):
    """Eintrag ins Protokoll (z. B. Programmstart mit Version)."""
    _log.info(text, stacklevel=2)


def kopfzeile(version, kuerzel="", speicher=""):
    """Eine Zeile je Programmstart: Version, Kürzel des Platzes, Datenspeicher (SQLite/PostgreSQL)."""
    _log.info("Start Version %s, Kürzel %s, Datenspeicher %s", version, kuerzel or "-", speicher or "-",
              stacklevel=2)


def warnung(text):
    """Bewusst abgefangener Fehler (except-Zweig, Verhalten bleibt): WARNING mit Stacktrace ins Protokoll, keine
    Meldung. Je Programmstelle höchstens WARNUNG_JE_STELLE Einträge je Programmlauf (kein Volllaufen in Schleifen)."""
    # Im übersetzten Programm (Cython) hat der Aufrufer oft keinen Python-Rahmen, z. B. aus closeEvent heraus, das
    # Qt direkt aufruft: sys._getframe(1) gab dort "call stack is not deep enough" und brach das Beenden ab
    # (Supportpaket 20.11.2026). Dann zählt der Text als Stelle.
    try:
        f = sys._getframe(1)
        stelle = (f.f_code.co_filename, f.f_lineno)
    except ValueError:
        stelle = ("", str(text)[:80])
    n = _warnungen.get(stelle, 0) + 1
    _warnungen[stelle] = n
    if n > WARNUNG_JE_STELLE:
        return
    zusatz = " (weitere an dieser Stelle werden nicht mehr protokolliert)" if n == WARNUNG_JE_STELLE else ""
    _log.warning("%s%s", text, zusatz, exc_info=sys.exc_info()[0] is not None, stacklevel=2)


def ist_lesemodus(wert):
    """Abgewiesener Schreibversuch im Lesemodus (Lizenz): Ausnahme Lesemodus, NurLesen (Datenschicht, SQLite und
    PostgreSQL) oder SQLite 'readonly database'."""
    import sqlite3
    if type(wert).__name__ in ("Lesemodus", "NurLesen"):     # NurLesen: Datenschicht (db_verbindung), auch PostgreSQL
        return True
    return isinstance(wert, sqlite3.OperationalError) and "readonly" in str(wert)


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
    global _in_meldung, fehler_anzahl
    if issubclass(art, KeyboardInterrupt):
        sys.__excepthook__(art, wert, tb)
        return
    if ist_lesemodus(wert):
        _lesemodus_melden(wert)
        return
    fehler_anzahl += 1
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
    except Exception:                   # noqa: BLE001 – die Meldung selbst darf nie einen zweiten Fehler auslösen
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
    knopf = m.addButton("Support-Paket …", QMessageBox.ActionRole) if SUPPORT is not None else None
    m.addButton(QMessageBox.Ok)
    m.exec()
    if knopf is not None and m.clickedButton() is knopf:
        SUPPORT()


def fehler_seit(ordner, seit):
    """Fehler im Protokoll (fehler.log und die rotierten Vorgänger) ab seit (datetime): [(Zeitpunkt, erste Zeile der
    Details)], ältester zuerst. Startseite: „N Fehler seit gestern“ (Optimierungsplan E1). Unlesbare Dateien zählen
    nicht."""
    import datetime
    muster = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)[,.]\d+ (ERROR|CRITICAL) (?:\S+ \| )?(.*)$")
    out = []
    ordner = Path(ordner)
    for name in (f"{DATEI}.2", f"{DATEI}.1", DATEI):
        try:
            zeilen = (ordner / name).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, z in enumerate(zeilen):
            m = muster.match(z)
            if not m:
                continue
            try:
                zeit = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if zeit < seit:
                continue
            text = m.group(3).strip()
            details = []
            for x in zeilen[i + 1:i + 200]:
                if re.match(r"^\d{4}-\d\d-\d\d \d\d:", x):
                    break           # nächster Eintrag
                if x.strip():
                    details.append(x.strip())
            # letzte Zeile des Tracebacks sagt am meisten (z. B. „ZeroDivisionError: division by zero“)
            if details and text == "Unerwarteter Fehler":
                text = details[-1]
            out.append((zeit, text[:200]))
    return out
