"""Diagnose für Administratoren (Stabilitäts-Auftrag Patrick 18.11.2026, Paket C): wie oft, wie lange und wie oft
unnötig gerechnet wurde, Datenbankzugriffe, Fehler, Speicher – seit dem Programmstart.

Erfasst wird ohne spürbare Bremse:
- Rechnungen (messen): Anzahl, Gesamt- und längste Dauer je Rechnung (Kalkulation, Optimieren, Maschinenvergleich
  …); Läufe über LANGSAM_S zählen als langsam.
- Unnötige Mehrfachberechnungen (doppelt): dieselbe Rechnung mit genau denselben Eingaben (Prüfsumme über den
  Inhalt) noch einmal – das zeigt Stellen, an denen ein Merker fehlt.
- Vermiedene Doppelrechnungen: Treffer der Merker (rechenmerker, rechnen.merker).
- Datenbank: Anzahl Anweisungen und Gesamtdauer (db_verbindung).
- Fehler: unerwartete Fehler und Warnungen des Protokolls in diesem Lauf, Arbeitsspeicher jetzt.

bericht() liefert den Text für das Fenster Hauptadmin → Diagnose: Rechenzähler … und die Datei diagnose.txt im
Support-Paket. Ohne Qt, ohne Datenbank.
"""
import collections
import contextlib
import hashlib
import threading
import time

LANGSAM_S = 1.0             # länger: zählt als langsamer Lauf
LETZTE = 64                 # so viele Eingabe-Prüfsummen je Rechnung merkt sich die Erkennung „doppelt“

_sperre = threading.Lock()
_start = time.time()
_rechnungen = {}            # Name -> [Anzahl, Summe s, längste s, langsam, doppelt]
_letzte = {}                # Name -> deque der letzten Prüfsummen
_db = [0, 0.0]              # Anweisungen, Summe s
_merker_intern = collections.Counter()      # rechnen.merker: (Art, "treffer"|"neu") -> Anzahl


def _eintrag(name):
    e = _rechnungen.get(name)
    if e is None:
        e = _rechnungen[name] = [0, 0.0, 0.0, 0, 0]
    return e


def zaehlen(name, dauer):
    with _sperre:
        e = _eintrag(name)
        e[0] += 1
        e[1] += dauer
        e[2] = max(e[2], dauer)
        if dauer > LANGSAM_S:
            e[3] += 1


@contextlib.contextmanager
def messen(name, eingaben=None):
    """Dauer einer Rechnung zählen. eingaben (optional): Werte, aus deren Darstellung eine Prüfsumme gebildet wird;
    gleiche Prüfsumme wie bei einem der letzten Läufe = unnötige Mehrfachberechnung."""
    if eingaben is not None:
        doppelt_pruefen(name, eingaben)
    t = time.perf_counter()
    try:
        yield
    finally:
        zaehlen(name, time.perf_counter() - t)


def doppelt_pruefen(name, eingaben):
    """True, wenn dieselbe Rechnung mit denselben Eingaben schon einmal lief (zählt sie)."""
    try:
        text = repr(eingaben)
    except Exception:           # noqa: BLE001 – ohne Darstellung keine Prüfung
        return False
    if " at 0x" in text:        # Objekte ohne Inhalts-Darstellung: Prüfsumme wäre zufällig
        return False
    summe = hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=16).digest()
    with _sperre:
        reihe = _letzte.get(name)
        if reihe is None:
            reihe = _letzte[name] = collections.deque(maxlen=LETZTE)
        if summe in reihe:
            _eintrag(name)[4] += 1
            return True
        reihe.append(summe)
    return False


def db_zugriff(dauer):
    with _sperre:
        _db[0] += 1
        _db[1] += dauer


def merker_zaehlen(art, treffer):
    with _sperre:
        _merker_intern[(art, "treffer" if treffer else "neu")] += 1


def stand():
    """Alle Zähler als dict (für Tests und den Bericht)."""
    from . import rechenmerker
    with _sperre:
        rech = {n: dict(anzahl=e[0], summe_s=e[1], max_s=e[2], langsam=e[3], doppelt=e[4])
                for n, e in _rechnungen.items()}
        db = dict(anweisungen=_db[0], summe_s=_db[1])
        intern = dict(_merker_intern)
    arten = sorted({a for a, _ in intern})
    merker = rechenmerker.stand() + [dict(name=f"Rechenlauf: {a}", eintraege=None, groesse=None,
                                          treffer=intern.get((a, "treffer"), 0), neu=intern.get((a, "neu"), 0),
                                          dauer_s=None) for a in arten]
    try:
        from . import protokoll
        warnungen = sum(protokoll._warnungen.values())
        fehler = protokoll.fehler_anzahl
    except Exception:           # noqa: BLE001
        warnungen = fehler = None
    try:
        from . import tempo
        speicher = tempo.speicher_mb()
    except Exception:           # noqa: BLE001
        speicher = None
    return dict(seit_s=time.time() - _start, rechnungen=rech, merker=merker, db=db, fehler=fehler,
                warnungen=warnungen, speicher_mb=speicher)


def zuruecksetzen():
    """Zähler auf null (Fenster „Zähler zurücksetzen“); Merker-Inhalte bleiben, nur ihre Zähler beginnen neu."""
    global _start
    from . import rechenmerker
    with _sperre:
        _rechnungen.clear()
        _letzte.clear()
        _db[0], _db[1] = 0, 0.0
        _merker_intern.clear()
        _start = time.time()
    for m in rechenmerker.alle().values():
        m.treffer = m.neu = 0
        m.dauer_s = 0.0


def _z(w, stellen=0):
    if w is None:
        return "–"
    t = f"{w:,.{stellen}f}"
    return t.replace(",", "X").replace(".", ",").replace("X", ".")


def bericht(s=None):
    """Lesbarer Bericht (Text, feste Spaltenbreite)."""
    s = s or stand()
    h, rest = divmod(int(s["seit_s"]), 3600)
    zeilen = [f"Diagnose seit {h} h {rest // 60} min (Programmstart oder Zähler zurückgesetzt)", ""]
    zeilen.append("Rechnungen                         Anzahl   gesamt s   längste s  langsam  doppelt")
    for n, e in sorted(s["rechnungen"].items(), key=lambda x: -x[1]["summe_s"]):
        zeilen.append(f"{n[:34]:34} {_z(e['anzahl']):>6} {_z(e['summe_s'], 1):>10} {_z(e['max_s'], 2):>11} "
                      f"{_z(e['langsam']):>8} {_z(e['doppelt']):>8}")
    if not s["rechnungen"]:
        zeilen.append("(noch nichts gerechnet)")
    zeilen += ["", "„doppelt“ = gleiche Rechnung mit genau denselben Eingaben noch einmal (unnötig);",
               f"„langsam“ = länger als {_z(LANGSAM_S, 1)} s.", ""]
    zeilen.append("Merker (vermiedene Doppelrechnungen)            Treffer      neu   Quote  Einträge")
    for m in s["merker"]:
        alle = (m["treffer"] or 0) + (m["neu"] or 0)
        quote = f"{100 * m['treffer'] / alle:.0f} %" if alle else "–"
        eintr = f"{_z(m['eintraege'])}/{_z(m['groesse'])}" if m["eintraege"] is not None else "–"
        zeilen.append(f"{m['name'][:46]:46} {_z(m['treffer']):>8} {_z(m['neu']):>8} {quote:>7} {eintr:>9}")
    db = s["db"]
    zeilen += ["", f"Datenbank: {_z(db['anweisungen'])} Anweisungen, zusammen {_z(db['summe_s'], 1)} s",
               f"Fehler in diesem Lauf: {_z(s['fehler'])} unerwartete, {_z(s['warnungen'])} Warnungen im Protokoll",
               f"Arbeitsspeicher jetzt: {_z(s['speicher_mb'])} MB"]
    return "\n".join(zeilen) + "\n"
