"""Zeitwächter (Optimierungsplan 04.11.2026, A3): langsame Schritte im Betrieb festhalten.

Patrick 04.11.2026: „gefühlt bei jedem Schritt langsam“. Testangebote zeigen nicht alles (STEP, Editoren, große echte
Angebote, Windows-Laptop). Der Zeitwächter merkt im laufenden Programm jede Stelle, an der die Oberfläche länger als
GRENZE_S nicht reagiert hat, und schreibt sie in Daten/Protokoll/tempo.log (höchstens 3 × 512 KB). Die Datei kommt
ins Support-Paket.

So funktioniert es, ohne das Programm selbst zu bremsen:
- ein Takt (QTimer, alle TAKT_MS) auf dem Oberflächen-Ablauf merkt sich die Uhrzeit. Kommt der nächste Takt deutlich
  später als geplant, war die Oberfläche so lange blockiert;
- ein Ereignisfilter merkt sich nur die letzte Bedienung (Klick, Taste, Doppelklick, Ziehen & Ablegen), damit der
  Eintrag sagt, was davor getan wurde;
- ein Hilfsfaden schaut während einer Blockade alle TAKT_MS nach, in welcher Programmfunktion der Oberflächen-Ablauf
  gerade steckt (nur im Quelltext-Betrieb sichtbar; im übersetzten Programm stehen dort nur Ort und Bedienung).

Speicher (Optimierungsplan E3, erst messen): jeder Eintrag nennt den Arbeitsspeicher des Programms, und alle
SPEICHER_TAKT_S schaut der Wächter nach; wächst er über den bisher höchsten Stand um SPEICHER_SCHRITT_MB, steht eine
Zeile „Speicher N MB | Ort: …“ im Protokoll. auswerten() nennt den höchsten Stand mit Ort.

Ein Eintrag: Zeit, Dauer, Ort (Reiter › Unterreiter, beim Angebot Positionen und Teile), letzte Bedienung, häufigste
Funktionen. auswerten() fasst die Datei für Menschen zusammen (Support, Tests).
"""
import collections
import logging
import logging.handlers
import re
import sys
import threading
import time
from pathlib import Path

DATEI = "tempo.log"
GRENZE_S = 0.5          # ab dieser Blockade gilt ein Schritt als langsam
TAKT_MS = 100
MAX_FUNKTIONEN = 3
SPEICHER_TAKT_S = 30      # so oft den Arbeitsspeicher ansehen
SPEICHER_SCHRITT_MB = 100   # neuer Höchststand um so viel: eine Zeile ins Protokoll

_log = logging.getLogger("rohrlaser.tempo")
_log.propagate = False


def _bedienung_text(ereignis, ziel):
    """Kurzer Text zur Bedienung, z. B. 'Klick „Optimieren“' oder 'Taste Enter in Positionen'."""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QAbstractButton
    art = {QEvent.MouseButtonRelease: "Klick", QEvent.MouseButtonDblClick: "Doppelklick",
           QEvent.KeyPress: "Taste", QEvent.Drop: "Ablegen"}.get(ereignis.type(), "Bedienung")
    if ereignis.type() == QEvent.KeyPress:
        from PySide6.QtGui import QKeySequence
        taste = QKeySequence(ereignis.keyCombination()).toString() or str(ereignis.key())
        return f"{art} {taste} in {type(ziel).__name__}"
    w = ziel
    knopf = None
    for _ in range(4):              # Klick auf das Symbol eines Knopfes: Knopf darüber
        if w is None:
            break
        if isinstance(w, QAbstractButton):
            knopf = w
            break
        w = w.parent() if hasattr(w, "parent") else None
    if knopf is not None and knopf.text():
        return f"{art} „{knopf.text().replace('&', '').strip()}“"
    return f"{art} in {type(ziel).__name__}"


class Waechter:
    """Zeitwächter für ein Hauptfenster. ordner = Protokollordner; kontext() = Text zum Ort (Hauptfenster.tempo_ort).
    starten() einmal nach dem Anlegen des Fensters; stoppen() beim Beenden (oder Test)."""

    def __init__(self, ordner, kontext=None, grenze_s=GRENZE_S, takt_ms=TAKT_MS, schreiben=None):
        self.ordner = Path(ordner) if ordner else None
        self.kontext = kontext
        self.grenze_s = grenze_s
        self.takt_s = takt_ms / 1000
        self.letzte_bedienung = ""
        self.eintraege = []                 # zuletzt geschriebene Einträge (höchstens 50, für Tests/Anzeige)
        self._schreiben = schreiben         # Test: Funktion(text) statt Datei
        self._zuletzt = time.perf_counter()
        self._proben = collections.Counter()
        self._sperre = threading.Lock()
        self._laeuft = False
        self._haupt_id = threading.get_ident()
        self._timer = None
        self._filter = None
        self._faden = None
        self.speicher_hoch = 0          # höchster protokollierter Arbeitsspeicher [MB]
        self._speicher_zuletzt = 0.0

    # ---------------------------------------------------------------- Einrichten
    def starten(self):
        from PySide6.QtCore import QObject, QTimer
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None or self._laeuft:
            return False
        if self.ordner is not None and self._schreiben is None:
            try:
                self.ordner.mkdir(parents=True, exist_ok=True)
                h = logging.handlers.RotatingFileHandler(self.ordner / DATEI, maxBytes=512_000, backupCount=2,
                                                         encoding="utf-8")
                h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
                _log.handlers = [h]
                _log.setLevel(logging.INFO)
            except OSError:
                self.ordner = None
        waechter = self

        class Filter(QObject):
            def eventFilter(self, ziel, ereignis):      # noqa: N802 – Qt-Name
                if ereignis.type() in _BEDIENUNG:
                    try:
                        waechter.letzte_bedienung = _bedienung_text(ereignis, ziel)
                    except Exception:                   # noqa: BLE001 – der Wächter darf nie stören
                        pass
                return False

        _bedienung_einrichten()
        self._filter = Filter()
        app.installEventFilter(self._filter)
        self._haupt_id = threading.get_ident()
        self._zuletzt = time.perf_counter()
        self._timer = QTimer()
        self._timer.setInterval(int(self.takt_s * 1000))
        self._timer.timeout.connect(self.takt)
        self._timer.start()
        self._laeuft = True
        self._faden = threading.Thread(target=self._beobachten, name="Zeitwächter", daemon=True)
        self._faden.start()
        return True

    def stoppen(self):
        from PySide6.QtWidgets import QApplication
        self._laeuft = False
        if self._timer is not None:
            self._timer.stop()
        app = QApplication.instance()
        if app is not None and self._filter is not None:
            app.removeEventFilter(self._filter)
        for h in list(_log.handlers):
            h.close()
        _log.handlers = []

    # ---------------------------------------------------------------- Messen
    def takt(self, jetzt=None):
        """Takt auf dem Oberflächen-Ablauf: Blockade seit dem letzten Takt erkennen und eintragen."""
        jetzt = time.perf_counter() if jetzt is None else jetzt
        blockiert = jetzt - self._zuletzt - self.takt_s
        self._zuletzt = jetzt
        with self._sperre:
            proben, self._proben = self._proben, collections.Counter()
        if blockiert >= self.grenze_s:
            self.eintragen(blockiert, proben)
            self._zuletzt = time.perf_counter()     # Schreiben selbst zählt nicht mit
        if jetzt - self._speicher_zuletzt >= SPEICHER_TAKT_S:
            self._speicher_zuletzt = jetzt
            self.speicher_pruefen()

    def speicher_pruefen(self, mb=None):
        """Neuen Höchststand des Arbeitsspeichers (ab SPEICHER_SCHRITT_MB mehr) mit Ort ins Protokoll. Ergebnis: Text
        des Eintrags oder None."""
        mb = speicher_mb() if mb is None else mb
        if not mb or mb < self.speicher_hoch + SPEICHER_SCHRITT_MB:
            return None
        self.speicher_hoch = mb
        text = f"Speicher {mb:.0f} MB" + (f" | Ort: {self._ort()}" if self._ort() else "")
        self.eintraege = (self.eintraege + [text])[-50:]
        if self._schreiben is not None:
            self._schreiben(text)
        else:
            _log.info(text)
        return text

    def _ort(self):
        if self.kontext is None:
            return ""
        try:
            return self.kontext() or ""
        except Exception:                               # noqa: BLE001
            return ""

    def _beobachten(self):
        """Hilfsfaden: während einer Blockade die Funktionen des Oberflächen-Ablaufs zählen."""
        while self._laeuft:
            time.sleep(self.takt_s)
            if time.perf_counter() - self._zuletzt < self.grenze_s:
                continue
            rahmen = sys._current_frames().get(self._haupt_id)
            name = _eigene_funktionen(rahmen)
            if name:
                with self._sperre:
                    self._proben[name] += 1

    def eintragen(self, dauer, proben=None):
        ort = self._ort()
        teile = [f"{dauer:.1f} s"]
        if ort:
            teile.append(f"Ort: {ort}")
        if self.letzte_bedienung:
            teile.append(f"zuletzt: {self.letzte_bedienung}")
        if proben:
            teile.append("in: " + "; ".join(f"{n} ({z})" for n, z in proben.most_common(MAX_FUNKTIONEN)))
        mb = speicher_mb()
        if mb:
            teile.append(f"Speicher: {mb:.0f} MB")
        text = " | ".join(teile)
        self.eintraege = (self.eintraege + [text])[-50:]
        if self._schreiben is not None:
            self._schreiben(text)
        else:
            _log.info(text)
        return text


def speicher_mb():
    """Arbeitsspeicher dieses Programms (Working Set bzw. RSS) in MB, None = nicht lesbar. Ohne Zusatzpaket: unter
    Windows GetProcessMemoryInfo, sonst /proc/self/status."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class Zaehler(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            z = Zaehler()
            z.cb = ctypes.sizeof(z)
            proc = ctypes.windll.kernel32.GetCurrentProcess()
            if not ctypes.windll.psapi.GetProcessMemoryInfo(proc, ctypes.byref(z), z.cb):
                return None
            return z.WorkingSetSize / 1048576
        with open("/proc/self/status", encoding="ascii") as f:
            for z in f:
                if z.startswith("VmRSS:"):
                    return int(z.split()[1]) / 1024
    except Exception:                                   # noqa: BLE001 – der Wächter darf nie stören
        return None
    return None


_BEDIENUNG = ()


def _bedienung_einrichten():
    global _BEDIENUNG
    from PySide6.QtCore import QEvent
    _BEDIENUNG = (QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick, QEvent.KeyPress, QEvent.Drop)


def _eigene_funktionen(rahmen, tiefe=3):
    """Die innersten tiefe Funktionen aus dem Programm (rohrlaser/…) als 'modul.funktion < modul.funktion …'."""
    namen = []
    while rahmen is not None and len(namen) < tiefe:
        datei = rahmen.f_code.co_filename.replace("\\", "/")
        if "/rohrlaser/" in datei and not datei.endswith("/tempo.py"):
            namen.append(f"{Path(datei).stem}.{rahmen.f_code.co_name}")
        rahmen = rahmen.f_back
    return " < ".join(namen)


# ------------------------------------------------------------------------------------------- Auswertung
_ZEILE = re.compile(r"^(\S+ \S+) (\d+(?:\.\d+)?) s(?: \| (.*))?$")
_SPEICHER = re.compile(r"^(\S+ \S+) Speicher (\d+) MB(?: \| Ort: (.*))?$")


def dateien(ordner):
    ordner = Path(ordner)
    return [p for p in (ordner / DATEI, ordner / f"{DATEI}.1", ordner / f"{DATEI}.2") if p.exists()]


def lesen(ordner):
    """Einträge aus tempo.log (+ Vorgänger): Liste dict(zeit, dauer, ort, bedienung, funktionen), älteste zuerst."""
    out = []
    for p in reversed(dateien(ordner)):
        for z in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = _ZEILE.match(z.strip())
            if not m:
                continue
            e = dict(zeit=m.group(1), dauer=float(m.group(2)), ort="", bedienung="", funktionen="", speicher="")
            for teil in (m.group(3) or "").split(" | "):
                for schl, feld in (("Ort: ", "ort"), ("zuletzt: ", "bedienung"), ("in: ", "funktionen"),
                                   ("Speicher: ", "speicher")):
                    if teil.startswith(schl):
                        e[feld] = teil[len(schl):]
            out.append(e)
    return out


def speicher_hoechststand(ordner):
    """Höchster protokollierter Arbeitsspeicher: (MB, Zeit, Ort) oder None."""
    hoch = None
    for p in reversed(dateien(ordner)):
        for z in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = _SPEICHER.match(z.strip())
            if m and (hoch is None or int(m.group(2)) > hoch[0]):
                hoch = (int(m.group(2)), m.group(1), m.group(3) or "")
    return hoch


def auswerten(ordner, anzahl=10):
    """Zusammenfassung für das Support-Paket: Anzahl, Summe und die langsamsten Stellen je Ort + Bedienung, dazu der
    höchste Arbeitsspeicher (E3)."""
    eintraege = lesen(ordner)
    hoch = speicher_hoechststand(ordner)
    speicher = (f"\n\nArbeitsspeicher höchstens {hoch[0]} MB ({hoch[1]}" + (f", {hoch[2]}" if hoch[2] else "") + ")."
                if hoch else "")
    if not eintraege:
        return "Keine langsamen Schritte (über %.1f s) protokolliert." % GRENZE_S + speicher
    gruppen = collections.defaultdict(list)
    for e in eintraege:
        ort = re.sub(r"\(\d[\d.]* Pos\., \d[\d.]* Teile\)", "", e["ort"]).strip()
        gruppen[(ort, e["bedienung"])].append(e["dauer"])
    zeilen = [f"{len(eintraege)} langsame Schritte, zusammen {sum(e['dauer'] for e in eintraege):.0f} s "
              f"(seit {eintraege[0]['zeit']}).", "", "Häufigste Stellen (Anzahl, längste, Summe):"]
    for (ort, bed), d in sorted(gruppen.items(), key=lambda kv: -sum(kv[1]))[:anzahl]:
        zeilen.append(f"  {len(d)} × bis {max(d):.1f} s, Summe {sum(d):.0f} s – {ort or '?'}"
                      + (f" – {bed}" if bed else ""))
    return "\n".join(zeilen) + speicher
