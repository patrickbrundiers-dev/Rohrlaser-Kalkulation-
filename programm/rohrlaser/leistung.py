"""Leistungsmessung je Verarbeitungsschritt (Master-Auftrag Patrick 24.11.2026 „Rechenkern, Importlogik und
Geometrieverarbeitung 2.0“, Punkt 12: automatisches Performance-Monitoring).

Für jeden wichtigen Schritt (STEP-Import und seine Teilschritte, Optimieren, Kalkulation, Staffeln,
Maschinenvergleich, Nesting, PDF …) hält das Modul seit dem Programmstart fest:
- Anzahl, Startzeit des ersten und Endzeit des letzten Laufs, Gesamtdauer,
- die Dauer der letzten FENSTER Läufe, daraus Median und hohe Perzentile (90 %, 95 %, 99 %) und den längsten Lauf –
  ein einzelner schneller Lauf verfälscht so nichts,
- CPU-Zeit des rechnenden Fadens (time.thread_time) und daraus die CPU-Auslastung des Schritts,
- Arbeitsspeicher des Programms nach dem Schritt (höchster Stand) und den größten Zuwachs während eines Laufs,
- Zählwerte je Schritt (verarbeitete Objekte, Körper, Konturen, Positionen, Teile …) als Summe,
- Fehler (Ausnahme im Schritt) und Warnungen.

Nichts davon ändert eine Rechnung: gemessen wird nur um die Schritte herum. Kosten je Lauf wenige Mikrosekunden
(Uhr, CPU-Uhr, bei ram=True zweimal /proc bzw. GetProcessMemoryInfo); für Schritte, die tausendfach je Sekunde laufen,
ist das Modul nicht gedacht.

Die Werte stehen im Diagnose-Bericht (Hauptadmin → Diagnose, Abschnitt „Leistung je Verarbeitungsschritt“, auch als
diagnose.txt im Support-Paket) – das ist die Entwickleransicht. Ohne Qt, ohne Datenbank, fadensicher.

Benutzung:
    with leistung.schritt("Kalkulation", positionen=len(pos)) as s:
        ...
        s.zaehlen(teile=n)
    leistung.erfassen("STEP: Körper messen", 12.3, koerper=48)      # Dauer von außen (z. B. Unterprozess)
"""
import collections
import contextlib
import threading
import time

FENSTER = 256               # so viele letzte Dauern je Schritt für Median und Perzentile
PERZENTILE = (50, 90, 95, 99)

_sperre = threading.Lock()
_schritte = {}              # Name -> _Eintrag
_start = time.time()


class _Eintrag:
    __slots__ = ("anzahl", "summe_s", "max_s", "dauern", "cpu_s", "cpu_n", "ram_mb", "ram_plus_mb", "zahlen",
                 "fehler", "warnungen", "letzte_warnung", "erster_start", "letztes_ende")

    def __init__(self):
        self.anzahl = 0
        self.summe_s = 0.0
        self.max_s = 0.0
        self.dauern = collections.deque(maxlen=FENSTER)
        self.cpu_s = 0.0
        self.cpu_n = 0              # Läufe mit CPU-Zeit (für die Auslastung nur diese zählen)
        self.ram_mb = None
        self.ram_plus_mb = None
        self.zahlen = collections.Counter()
        self.fehler = 0
        self.warnungen = 0
        self.letzte_warnung = ""
        self.erster_start = None
        self.letztes_ende = None


def perzentil(werte, p):
    """p-Perzentil (0–100) nach dem Rang-Verfahren mit linearer Zwischenrechnung (wie numpy „linear“, Excel
    QUANTIL.INKL): 50 = Median. Leere Liste: None."""
    w = sorted(werte)
    if not w:
        return None
    if len(w) == 1:
        return w[0]
    r = (len(w) - 1) * p / 100.0
    i = int(r)
    if i >= len(w) - 1:
        return w[-1]
    return w[i] + (w[i + 1] - w[i]) * (r - i)


def kennzahlen(werte):
    """Median, Perzentile, kleinster/größter Wert und Mittel einer Liste von Dauern (Benchmarks, Bericht)."""
    w = list(werte)
    if not w:
        return dict(n=0)
    out = dict(n=len(w), min=min(w), max=max(w), mittel=sum(w) / len(w))
    for p in PERZENTILE:
        out["median" if p == 50 else f"p{p}"] = perzentil(w, p)
    return out


def _ram():
    try:
        from . import tempo
        return tempo.speicher_mb()
    except Exception:           # noqa: BLE001 – Messung darf nie stören
        return None


def erfassen(name, dauer_s, cpu_s=None, ram_mb=None, ram_plus_mb=None, fehler=False, start=None, warnung=None,
             **zahlen):
    """Einen Lauf von name eintragen (Dauer in s; CPU-Zeit, Speicher und Zählwerte, soweit bekannt)."""
    try:
        dauer_s = float(dauer_s)
    except (TypeError, ValueError):
        return
    if dauer_s != dauer_s or dauer_s < 0:     # NaN oder negativ: kein Messwert
        return
    jetzt = time.time()
    with _sperre:
        e = _schritte.get(name)
        if e is None:
            e = _schritte[name] = _Eintrag()
        e.anzahl += 1
        e.summe_s += dauer_s
        e.max_s = max(e.max_s, dauer_s)
        e.dauern.append(dauer_s)
        if cpu_s is not None:
            e.cpu_s += cpu_s
            e.cpu_n += 1
        if ram_mb is not None:
            e.ram_mb = ram_mb if e.ram_mb is None else max(e.ram_mb, ram_mb)
        if ram_plus_mb is not None:
            e.ram_plus_mb = ram_plus_mb if e.ram_plus_mb is None else max(e.ram_plus_mb, ram_plus_mb)
        for k, v in zahlen.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                e.zahlen[k] += v
        if fehler:
            e.fehler += 1
        if warnung:
            e.warnungen += 1
            e.letzte_warnung = str(warnung)[:200]
        beginn = start if start is not None else jetzt - dauer_s
        if e.erster_start is None or beginn < e.erster_start:
            e.erster_start = beginn
        e.letztes_ende = jetzt


class Lauf:
    """Ein laufender Schritt (aus schritt()): Zählwerte und Warnungen während des Laufs."""
    __slots__ = ("name", "zahlen", "warnung")

    def __init__(self, name, zahlen):
        self.name = name
        self.zahlen = dict(zahlen)
        self.warnung = None

    def zaehlen(self, **zahlen):
        for k, v in zahlen.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                self.zahlen[k] = self.zahlen.get(k, 0) + v

    def warnen(self, text):
        self.warnung = text


@contextlib.contextmanager
def schritt(name, ram=True, **zahlen):
    """Dauer, CPU-Zeit, Speicher und Zählwerte eines Schritts messen. Eine Ausnahme zählt als Fehler und wird
    weitergereicht (die Messung ändert keinen Ablauf)."""
    lauf = Lauf(name, zahlen)
    ram0 = _ram() if ram else None
    start, t0, c0 = time.time(), time.perf_counter(), time.thread_time()
    fehler = False
    try:
        yield lauf
    except BaseException:
        fehler = True
        raise
    finally:
        dauer, cpu = time.perf_counter() - t0, time.thread_time() - c0
        ram1 = _ram() if ram else None
        plus = ram1 - ram0 if ram0 is not None and ram1 is not None else None
        erfassen(name, dauer, cpu_s=cpu, ram_mb=ram1, ram_plus_mb=plus, fehler=fehler, start=start,
                 warnung=lauf.warnung, **lauf.zahlen)


# Teilschritte der STEP-Messung aus ihrer Zeile „ZEITEN {json}“ (step_messen._zeiten_melden)
STEP_SCHRITTE = (("lesen_s", "STEP: Datei lesen"), ("uebertragen_s", "STEP: umwandeln und heilen"),
                 ("naehen_s", "STEP: Flächen nähen"), ("struktur_s", "STEP: Baugruppenstruktur"),
                 ("kopien_s", "STEP: gleiche Körper suchen"), ("messen_s", "STEP: Körper messen"),
                 ("abschluss_s", "STEP: Baugruppe auswerten"))


def step_zeiten(zeiten, dauer_s=None, dateien=None, mb=None):
    """Die Zeiten einer STEP-Messung eintragen: Gesamtdauer (aus Sicht des Programms, mit Start des Messprozesses)
    und die Teilschritte je Datei. zeiten = dict der ZEITEN-Zeile (kann leer sein)."""
    z = zeiten if isinstance(zeiten, dict) else {}
    if dauer_s is not None:
        erfassen("STEP-Import gesamt", dauer_s, dateien=dateien or 0, mb=mb or 0,
                 koerper=z.get("koerper_n") or 0)
    for name, d in (z.get("dateien") or {}).items():
        if not isinstance(d, dict):
            continue
        sch = d.get("schritte") or {}
        for feld, text in STEP_SCHRITTE:
            v = sch.get(feld)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                zahl = dict(koerper=sch.get("gemessen") or 0) if feld == "messen_s" else {}
                erfassen(text, v, **zahl)
        if isinstance(d.get("abschluss"), (int, float)) and "abschluss_s" not in sch:
            erfassen("STEP: Baugruppe auswerten", d["abschluss"])
    if isinstance(z.get("koerper_s"), (int, float)) and z.get("koerper_n"):
        erfassen("STEP: Körper verteilt gemessen", z["koerper_s"], koerper=z["koerper_n"])


def stand():
    """Alle Schritte als dict {Name: Kennzahlen} (für Tests, Bericht und Benchmarks)."""
    with _sperre:
        roh = {n: (e.anzahl, e.summe_s, e.max_s, list(e.dauern), e.cpu_s, e.cpu_n, e.ram_mb, e.ram_plus_mb,
                   dict(e.zahlen), e.fehler, e.warnungen, e.letzte_warnung, e.erster_start, e.letztes_ende)
               for n, e in _schritte.items()}
    out = {}
    for n, (anz, summe, mx, dauern, cpu, cpu_n, ram, plus, zahlen, fehler, warn, lw, t0, t1) in roh.items():
        k = kennzahlen(dauern)
        # Auslastung nur über die Läufe mit CPU-Zeit (von außen eingetragene Unterprozess-Zeiten haben keine)
        cpu_dauer = sum(dauern[-cpu_n:]) if cpu_n and cpu_n <= len(dauern) else summe
        out[n] = dict(anzahl=anz, summe_s=summe, max_s=mx, median_s=k.get("median"), p90_s=k.get("p90"),
                      p95_s=k.get("p95"), p99_s=k.get("p99"), cpu_s=cpu if cpu_n else None,
                      cpu_auslastung=(cpu / cpu_dauer if cpu_n and cpu_dauer > 0 else None), ram_mb=ram,
                      ram_plus_mb=plus, zahlen=zahlen, fehler=fehler, warnungen=warn, letzte_warnung=lw,
                      erster_start=t0, letztes_ende=t1)
    return out


def zuruecksetzen():
    global _start
    with _sperre:
        _schritte.clear()
        _start = time.time()


def _z(w, stellen=0):
    if w is None:
        return "–"
    t = f"{w:,.{stellen}f}"
    return t.replace(",", "X").replace(".", ",").replace("X", ".")


def _dauer(s):
    if s is None:
        return "–"
    if s < 1:
        return _z(1000 * s, 0) + " ms"
    return _z(s, 2 if s < 10 else 1) + " s"


def bericht_zeilen(s=None):
    """Abschnitt „Leistung je Verarbeitungsschritt“ für den Diagnose-Bericht (feste Spaltenbreite)."""
    s = stand() if s is None else s
    zeilen = ["Leistung je Verarbeitungsschritt     Anzahl   Median     95 %      max  gesamt s  CPU    RAM MB  +RAM"]
    if not s:
        return zeilen + ["(noch nichts gemessen)"]
    for n, e in sorted(s.items(), key=lambda x: -x[1]["summe_s"]):
        cpu = f"{100 * e['cpu_auslastung']:.0f} %" if e["cpu_auslastung"] is not None else "–"
        zeilen.append(f"{n[:34]:34} {_z(e['anzahl']):>6} {_dauer(e['median_s']):>8} {_dauer(e['p95_s']):>8} "
                      f"{_dauer(e['max_s']):>8} {_z(e['summe_s'], 1):>9} {cpu:>5} {_z(e['ram_mb']):>7} "
                      f"{_z(e['ram_plus_mb']):>5}")
        extra = [f"{k} {_z(v, 1 if v != int(v) else 0)}" for k, v in sorted(e["zahlen"].items()) if v]
        if e["fehler"]:
            extra.append(f"Fehler {_z(e['fehler'])}")
        if e["warnungen"]:
            extra.append(f"Warnungen {_z(e['warnungen'])}" + (f" ({e['letzte_warnung']})" if e["letzte_warnung"]
                                                              else ""))
        if extra:
            zeilen.append("    " + " · ".join(extra))
    zeilen += [f"„Median“/„95 %“ über die letzten {FENSTER} Läufe; CPU = Rechenzeit des Fadens ÷ Dauer (unter 100 % =",
               "Warten auf Datei, Datenbank oder Unterprozess); +RAM = größter Zuwachs in einem Lauf."]
    return zeilen


def gemessen(name, **zahlen):
    """Dekorator: jeder Aufruf der Funktion ist ein Lauf von name."""
    import functools

    def deko(fn):
        @functools.wraps(fn)
        def huelle(*a, **kw):
            with schritt(name, **zahlen):
                return fn(*a, **kw)
        return huelle
    return deko
