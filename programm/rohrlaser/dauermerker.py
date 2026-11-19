"""Merker über den Programmstart hinaus, je Angebot eine eigene Datei (Großes System-Update und Angebots-Cache,
Patrick 19.11.2026: „Berechnungen intelligent wiederverwenden“, „jedes Angebot erhält einen eigenen persistenten
Cache“).

Die Merker in rechenmerker.py gelten nur, solange das Programm läuft. Hier liegen reine Rechenergebnisse in kleinen
SQLite-Dateien neben der Datendatei, lokal auf jedem PC (Ordner Daten/Rechenmerker):

    Rechenmerker/
        rechenmerker.db          Ergebnisse, die nicht zu einem Angebot gehören (Schneidfolge, Endabfall eines Teils:
                                 dasselbe Rohr in zwei Angeboten rechnet nur einmal)
        Angebote/A<id>.db        je Angebot: Kalkulation, Schnittzeiten je Position (Bereiche), mit Kopfdaten
                                 (Angebots-ID und -Nummer, Programmversion, Cache-Schema, angelegt, zuletzt benutzt)

Regeln:
- Nur Rechnungen, deren Ergebnis allein von ihren Eingaben abhängt. Der Schlüssel ist eine Prüfsumme (SHA-256) über
  alle Eingaben (Position, Kopf, gelesene Stammdaten …), die Programmversion und das Cache-Schema. Ändert sich eine
  Eingabe, passt der Schlüssel nicht mehr, und nur diese Rechnung läuft neu; nach einem Update rechnet das Programm
  einmal alles neu (die alte Version räumt das Aufräumen weg). Ein veraltetes Ergebnis kann so nie in die
  Kalkulation kommen.
- Die Datenbank bleibt maßgeblich: im Merker steht nur, was sich jederzeit aus ihr neu rechnen lässt. Löschen der
  Dateien schadet nie.
- Werte werden typgenau abgelegt (Tupel, Zahlen-Schlüssel, -0.0 bleiben, was sie waren); was sich nicht genau
  ablegen lässt, wird nicht gemerkt. Große Werte werden komprimiert (zlib).
- Geschrieben wird im Hintergrund (eigener Faden, gesammelt in einer Transaktion); leeren() wartet, bis alles
  geschrieben ist (beim Schließen eines Angebots und am Programmende). Lesen sieht noch nicht geschriebene Werte.
- Jeder Fehler einer Datei (gesperrt, beschädigt, kein Platz) wird einmal protokolliert; gerechnet wird dann wie
  ohne Merker. Eine beschädigte Datei wird ersetzt, ein unlesbarer Eintrag gelöscht.
- Mehrere Benutzer: jeder PC hat seine eigenen Dateien (kein gemeinsames Schreiben über das Netz); zwei
  Programme auf einem PC teilen sie sicher (SQLite WAL, Sperre mit Wartezeit, Schreiben je Eintrag atomar).
- Zähler je Bereich (Treffer, neu gerechnet, eingesparte Rechenzeit, Ladezeit) zeigt die Diagnose.

Ohne Qt, ohne Datendatei. Sicher für mehrere Threads (eine Sperre).
"""
import atexit
import decimal
import hashlib
import json
import queue
import sqlite3
import threading
import time
import zlib
from pathlib import Path

from . import VERSION

ORDNER = "Rechenmerker"
DATEI = "rechenmerker.db"
ANGEBOTE = "Angebote"
SCHEMA = 2                      # Aufbau der Dateien und der Ablage; höher = alte Einträge gelten nicht mehr
GROESSE = 50_000                # Einträge höchstens in rechenmerker.db
GROESSE_ANGEBOT = 20_000        # Einträge höchstens je Angebot
GESAMT_MB = 1024                # alle Angebotsdateien zusammen höchstens (die am längsten unbenutzten fallen weg)
UNBENUTZT_TAGE = 180            # Angebotsdatei so lange nicht benutzt: weg (rechnet beim nächsten Öffnen neu)
KOMPRIMIEREN_AB = 2048          # Zeichen JSON; darüber zlib
OFFEN_HOECHSTENS = 12           # so viele Angebotsdateien gleichzeitig offen
BEREICH_HOECHSTENS = {"Kalkulation": 40}    # große Einträge: je Datei nur die neuesten (Staffeln, Maschinen …)

_sperre = threading.RLock()
_wurzel = None                  # Ordner Rechenmerker oder None
_aus = False
_dateien = {}                   # Schlüssel (None = allgemein, sonst Angebots-ID) -> _Datei
_kaputt = set()                 # Dateien, die in diesem Lauf nicht nutzbar sind
zaehler = {"treffer": 0, "neu": 0}
_bereiche = {}                  # Bereich -> dict(treffer, neu, gespart_s, rechnen_s, laden_s, nicht_ablegbar)

_offen = {}                     # (datei, bereich, schluessel) -> (art, text, dauer) noch nicht geschrieben
_warteschlange = queue.Queue()
_schreiber = None


# ------------------------------------------------------------------------------------------------ Ablage typgenau
class NichtAblegbar(ValueError):
    """Wert lässt sich nicht genau als JSON ablegen (Objekt, Menge, numpy …): wird nicht gemerkt."""


_T, _D, _M = "\x00t", "\x00d", "\x00m"
_EINFACH = (str, int, float, bool, type(None))


def kodieren(x):
    """Wert -> JSON-fähig, umkehrbar: Tupel und dict mit Nicht-Text-Schlüsseln markiert."""
    t = type(x)
    if t in _EINFACH:
        return x
    if t is list:
        return [kodieren(v) for v in x]
    if t is tuple:
        return {_T: [kodieren(v) for v in x]}
    if t is dict:
        if all(type(k) is str for k in x) and _T not in x and _D not in x and _M not in x:
            return {k: kodieren(v) for k, v in x.items()}
        return {_D: [[kodieren(k), kodieren(v)] for k, v in x.items()]}
    if t is decimal.Decimal:            # Zukauf-Mengen: genau als Text
        return {_M: str(x)}
    raise NichtAblegbar(t.__name__)


def dekodieren(x):
    t = type(x)
    if t is list:
        return [dekodieren(v) for v in x]
    if t is dict:
        if len(x) == 1:
            if _T in x:
                return tuple(dekodieren(v) for v in x[_T])
            if _D in x:
                return {dekodieren(k): dekodieren(v) for k, v in x[_D]}
            if _M in x:
                return decimal.Decimal(x[_M])
        return {k: dekodieren(v) for k, v in x.items()}
    return x


def _packen(wert):
    text = json.dumps(kodieren(wert), allow_nan=True, ensure_ascii=False, separators=(",", ":"))
    if len(text) > KOMPRIMIEREN_AB:
        return 1, zlib.compress(text.encode("utf-8", "surrogatepass"), 6)
    return 0, text


def _auspacken(art, daten):
    if art == 1:
        daten = zlib.decompress(daten).decode("utf-8", "surrogatepass")
    return dekodieren(json.loads(daten))


# ------------------------------------------------------------------------------------------------ Dateien
class _Datei:
    def __init__(self, pfad, angebot=None):
        self.pfad, self.angebot, self.con = Path(pfad), angebot, None
        self.benutzt_gemerkt = False

    def oeffnen(self):
        """Verbindung (einmal ersetzt, wenn beschädigt) oder None. Unter der Sperre."""
        if self.con is not None:
            return self.con
        if self.pfad in _kaputt:
            return None
        for versuch in range(2):
            con = None
            try:
                self.pfad.parent.mkdir(parents=True, exist_ok=True)
                con = sqlite3.connect(self.pfad, timeout=2.0, check_same_thread=False, isolation_level=None)
                con.execute("PRAGMA journal_mode=WAL")
                con.execute("PRAGMA synchronous=NORMAL")    # WAL: übersteht Programmabsturz; nur ein Zwischenspeicher
                self._einrichten(con)
                self.con = con
                return con
            except sqlite3.DatabaseError:
                if con is not None:
                    con.close()         # schließt auch eine unbrauchbare Verbindung ohne Fehler
                if versuch == 0 and _beschaedigt_ersetzen(self.pfad):
                    continue
                _datei_fehler(self.pfad, "Datei nicht nutzbar")
                return None
            except OSError:
                _datei_fehler(self.pfad, "Ordner nicht nutzbar")
                return None
        return None

    def _einrichten(self, con):
        con.execute("CREATE TABLE IF NOT EXISTS kopf (name TEXT PRIMARY KEY, wert TEXT)")
        schema = con.execute("SELECT wert FROM kopf WHERE name='schema'").fetchone()
        if schema is None or schema[0] != str(SCHEMA):
            con.execute("DROP TABLE IF EXISTS merker")      # anderer Aufbau (ältere Version): neu anfangen
        con.execute("CREATE TABLE IF NOT EXISTS merker (bereich TEXT NOT NULL, schluessel BLOB NOT NULL, "
                    "art INTEGER NOT NULL DEFAULT 0, wert BLOB NOT NULL, version TEXT NOT NULL DEFAULT '', "
                    "dauer REAL NOT NULL DEFAULT 0, zeit REAL NOT NULL, PRIMARY KEY (bereich, schluessel))")
        con.execute("CREATE INDEX IF NOT EXISTS merker_zeit ON merker (zeit)")
        jetzt = repr(time.time())
        kopf = {"schema": str(SCHEMA), "programm": VERSION}
        if self.angebot is not None:
            kopf["angebot_id"] = str(self.angebot)
        con.execute("BEGIN")
        for n, w in kopf.items():
            con.execute("INSERT INTO kopf (name, wert) VALUES (?, ?) ON CONFLICT (name) DO UPDATE SET wert=excluded.wert",
                        (n, w))
        con.execute("INSERT OR IGNORE INTO kopf (name, wert) VALUES ('angelegt', ?)", (jetzt,))
        con.execute("COMMIT")
        grenze = GROESSE if self.angebot is None else GROESSE_ANGEBOT
        n = con.execute("SELECT COUNT(*) FROM merker").fetchone()[0]
        if n > grenze:
            con.execute("DELETE FROM merker WHERE rowid IN (SELECT rowid FROM merker ORDER BY zeit LIMIT ?)",
                        (n - grenze,))

    def benutzt(self, con, nummer=None):
        """Zuletzt benutzt (und Angebotsnummer) einmal je Programmlauf festhalten."""
        if self.benutzt_gemerkt and nummer is None:
            return
        self.benutzt_gemerkt = True
        werte = [("benutzt", repr(time.time()))] + ([("nummer", str(nummer))] if nummer else [])
        for n, w in werte:
            con.execute("INSERT INTO kopf (name, wert) VALUES (?, ?) ON CONFLICT (name) DO UPDATE SET wert=excluded.wert",
                        (n, w))

    def schliessen(self):
        if self.con is not None:
            try:
                self.con.close()
            except sqlite3.Error:
                pass
        self.con = None


def _beschaedigt_ersetzen(pfad):
    """Beschädigte Merker-Datei (nur ein Zwischenspeicher) wegräumen. True = weg."""
    try:
        for p in (pfad, pfad.with_name(pfad.name + "-wal"), pfad.with_name(pfad.name + "-shm")):
            if p.exists():
                p.unlink()
        return True
    except OSError:
        return False


def _datei_fehler(pfad, text):
    """Datei für diesen Lauf aus; die allgemeine Datei schaltet den ganzen Merker aus."""
    global _aus
    _kaputt.add(Path(pfad))
    if _wurzel is not None and Path(pfad) == _wurzel / DATEI:
        _aus = True
    from . import protokoll
    protokoll.warnung(f"Rechenmerker: {text} ({Path(pfad).name}), es wird ohne gerechnet")


def _datei(angebot):
    """_Datei für das Angebot (None = allgemein) oder None (aus). Unter der Sperre."""
    if _aus or _wurzel is None:
        return None
    d = _dateien.get(angebot)
    if d is None:
        pfad = _wurzel / DATEI if angebot is None else _wurzel / ANGEBOTE / f"A{int(angebot)}.db"
        d = _dateien[angebot] = _Datei(pfad, angebot)
        offen = [k for k, x in _dateien.items() if k is not None and x.con is not None and k != angebot]
        for k in offen[:max(0, len(offen) - OFFEN_HOECHSTENS + 1)]:
            _dateien.pop(k).schliessen()
    return d


def _angebot_id(angebot):
    try:
        return None if angebot is None else int(angebot)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ Einrichten
def einrichten(ordner):
    """Merker im Ordner ordner (Daten/Rechenmerker) benutzen; None schaltet ihn aus."""
    global _wurzel, _aus
    leeren()
    with _sperre:
        _schliessen()
        _kaputt.clear()
        _aus = ordner is None
        _wurzel = None if ordner is None else Path(ordner)


def _schliessen():
    for d in _dateien.values():
        d.schliessen()
    _dateien.clear()


def ordner():
    return _wurzel


def schluessel(*eingaben):
    """Prüfsumme über alle Eingaben (JSON, sortiert), die Programmversion und das Cache-Schema."""
    text = json.dumps([VERSION, SCHEMA, eingaben], sort_keys=True, default=repr, ensure_ascii=False, allow_nan=True)
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).digest()


def pruefsumme(text):
    """SHA-256 eines (großen) Texts, z. B. repr der Stammdaten, als kurzer Text für einen Schlüssel."""
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _bereich(b):
    z = _bereiche.get(b)
    if z is None:
        z = _bereiche[b] = dict(treffer=0, neu=0, gespart_s=0.0, rechnen_s=0.0, laden_s=0.0, nicht_ablegbar=0)
    return z


# ------------------------------------------------------------------------------------------------ Lesen, Ablegen
def holen(bereich, s, angebot=None):
    """Gemerkter Wert (eigene Kopie) oder None."""
    t0 = time.perf_counter()
    angebot = _angebot_id(angebot)
    with _sperre:
        d = _datei(angebot)
        if d is None:
            return None
        offen = _offen.get((d.pfad, bereich, s))
        if offen is not None:
            r = offen
        else:
            con = d.oeffnen()
            if con is None:
                return None
            try:
                r = con.execute("SELECT art, wert, dauer FROM merker WHERE bereich=? AND schluessel=?",
                                (bereich, s)).fetchone()
                if angebot is not None and not d.benutzt_gemerkt:
                    d.benutzt(con)
            except sqlite3.Error:
                _datei_fehler(d.pfad, "Lesen gescheitert")
                d.schliessen()
                return None
    z = _bereich(bereich)
    if r is None:
        zaehler["neu"] += 1
        z["neu"] += 1
        return None
    try:
        wert = _auspacken(r[0], r[1])
    except (ValueError, TypeError, zlib.error, UnicodeDecodeError):
        _eintrag_loeschen(d, bereich, s)            # unlesbar: weg, neu rechnen
        zaehler["neu"] += 1
        z["neu"] += 1
        return None
    zaehler["treffer"] += 1
    z["treffer"] += 1
    z["gespart_s"] += r[2] or 0.0
    z["laden_s"] += time.perf_counter() - t0
    return wert


def _eintrag_loeschen(d, bereich, s):
    with _sperre:
        con = d.oeffnen()
        if con is not None:
            try:
                con.execute("DELETE FROM merker WHERE bereich=? AND schluessel=?", (bereich, s))
            except sqlite3.Error:
                _datei_fehler(d.pfad, "Löschen gescheitert")


def ablegen(bereich, s, wert, angebot=None, dauer_s=0.0):
    """Wert merken (im Hintergrund geschrieben); nicht genau ablegbare Werte werden nicht gemerkt."""
    try:
        art, daten = _packen(wert)
    except (NichtAblegbar, TypeError, ValueError, RecursionError):
        _bereich(bereich)["nicht_ablegbar"] += 1
        return
    angebot = _angebot_id(angebot)
    with _sperre:
        d = _datei(angebot)
        if d is None:
            return
        _bereich(bereich)["rechnen_s"] += dauer_s or 0.0
        _offen[(d.pfad, bereich, s)] = (art, daten, float(dauer_s or 0.0))
        _schreiber_starten()
    _warteschlange.put((angebot, d.pfad, bereich, s))


def gemerkt(bereich, s, rechne, angebot=None, pruefen=None):
    """Wert aus dem Merker, sonst rechne() (wird gemerkt). pruefen(wert) False = gemerkter Wert passt nicht."""
    wert = holen(bereich, s, angebot)
    if wert is not None and (pruefen is None or pruefen(wert)):
        return wert
    t0 = time.perf_counter()
    wert = rechne()
    ablegen(bereich, s, wert, angebot, time.perf_counter() - t0)
    return wert


# ------------------------------------------------------------------------------------------------ Hintergrund
def _schreiber_starten():
    global _schreiber
    if _schreiber is None or not _schreiber.is_alive():
        _schreiber = threading.Thread(target=_schreiben, name="Rechenmerker schreiben", daemon=True)
        _schreiber.start()


def _schreiben():
    while True:
        posten = [_warteschlange.get()]
        while len(posten) < 500:
            try:
                posten.append(_warteschlange.get_nowait())
            except queue.Empty:
                break
        try:
            _posten_schreiben(posten)
        finally:
            for _ in posten:
                _warteschlange.task_done()


def _posten_schreiben(posten):
    je_datei = {}
    for angebot, pfad, bereich, s in posten:
        je_datei.setdefault((angebot, pfad), []).append((bereich, s))
    for (angebot, pfad), liste in je_datei.items():
        with _sperre:
            d = _dateien.get(angebot)
            werte = [(b, s, _offen.get((pfad, b, s))) for b, s in liste]
            werte = [(b, s, w) for b, s, w in werte if w is not None]
            if d is None or d.pfad != pfad or not werte:
                for b, s, _ in werte:
                    _offen.pop((pfad, b, s), None)
                continue
            con = d.oeffnen()
            try:
                if con is not None:
                    jetzt = time.time()
                    con.execute("BEGIN")
                    con.executemany("INSERT INTO merker (bereich, schluessel, art, wert, version, dauer, zeit) "
                                    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (bereich, schluessel) DO UPDATE SET "
                                    "art=excluded.art, wert=excluded.wert, version=excluded.version, "
                                    "dauer=excluded.dauer, zeit=excluded.zeit",
                                    [(b, s, w[0], w[1], VERSION, w[2], jetzt) for b, s, w in werte])
                    for b in {b for b, _, _ in werte} & set(BEREICH_HOECHSTENS):
                        con.execute("DELETE FROM merker WHERE bereich=? AND rowid NOT IN (SELECT rowid FROM merker "
                                    "WHERE bereich=? ORDER BY zeit DESC, rowid DESC LIMIT ?)",
                                    (b, b, BEREICH_HOECHSTENS[b]))
                    if angebot is not None:
                        d.benutzt(con)
                    con.execute("COMMIT")
            except sqlite3.Error:
                try:
                    con.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                _datei_fehler(d.pfad, "Schreiben gescheitert")
                d.schliessen()
            finally:
                for b, s, w in werte:
                    if _offen.get((pfad, b, s)) is w:
                        _offen.pop((pfad, b, s), None)


def leeren(warten_s=15.0):
    """Warten, bis alles Abgelegte geschrieben ist (Angebot schließen, Programmende). True = fertig."""
    if _schreiber is None or not _schreiber.is_alive():
        return not _warteschlange.unfinished_tasks
    ende = time.monotonic() + warten_s
    while _warteschlange.unfinished_tasks and time.monotonic() < ende:
        time.sleep(0.01)
    return not _warteschlange.unfinished_tasks


atexit.register(leeren)


def angebot_benutzt(angebot, nummer=None):
    """Beim Öffnen eines Angebots: Nummer in den Kopf der Datei (für die Verwaltung)."""
    angebot = _angebot_id(angebot)
    if angebot is None:
        return
    with _sperre:
        d = _datei(angebot)
        con = d.oeffnen() if d is not None else None
        if con is not None:
            try:
                d.benutzt(con, nummer)
            except sqlite3.Error:
                _datei_fehler(d.pfad, "Schreiben gescheitert")


# ------------------------------------------------------------------------------------------------ Diagnose
def stand():
    """dict(treffer, neu, eintraege, aus, bereiche) für die Diagnose (eintraege: allgemeine Datei)."""
    with _sperre:
        d = _datei(None)
        con = d.oeffnen() if d is not None else None
        try:
            n = con.execute("SELECT COUNT(*) FROM merker").fetchone()[0] if con is not None else 0
        except sqlite3.Error:
            n = 0
        bereiche = {b: dict(z) for b, z in _bereiche.items()}
    return dict(zaehler, eintraege=n, aus=_aus or _wurzel is None, bereiche=bereiche)


def zaehler_zuruecksetzen():
    with _sperre:
        zaehler.update(treffer=0, neu=0)
        _bereiche.clear()


# ------------------------------------------------------------------------------------------------ Verwaltung
def _alle_pfade():
    if _wurzel is None:
        return []
    pfade = [_wurzel / DATEI] if (_wurzel / DATEI).exists() else []
    try:
        pfade += sorted((_wurzel / ANGEBOTE).glob("A*.db"))
    except OSError:
        pass
    return pfade


def _groesse(pfad):
    g = 0
    for p in (pfad, pfad.with_name(pfad.name + "-wal")):
        try:
            g += p.stat().st_size
        except OSError:
            pass
    return g


def uebersicht():
    """Je Datei: dict(pfad, angebot_id, nummer, groesse, eintraege, bereiche {Bereich: Anzahl}, programm, schema,
    angelegt, benutzt, geaendert, veraltet (Einträge anderer Version), fehler)."""
    leeren()
    out = []
    for pfad in _alle_pfade():
        z = dict(pfad=pfad, angebot_id=None, nummer=None, groesse=_groesse(pfad), eintraege=0, bereiche={},
                 programm=None, schema=None, angelegt=None, benutzt=None, geaendert=None, veraltet=0, fehler=None)
        try:
            z["geaendert"] = max(p.stat().st_mtime for p in (pfad, pfad.with_name(pfad.name + "-wal")) if p.exists())
        except (OSError, ValueError):
            pass
        try:
            with _sperre:
                d = _datei(_aus_pfad(pfad))
                con = d.oeffnen() if d is not None else None
                if con is None:
                    raise sqlite3.DatabaseError("nicht nutzbar")
                kopf = dict(con.execute("SELECT name, wert FROM kopf"))
                z["bereiche"] = dict(con.execute("SELECT bereich, COUNT(*) FROM merker GROUP BY bereich"))
                z["veraltet"] = con.execute("SELECT COUNT(*) FROM merker WHERE version<>?", (VERSION,)).fetchone()[0]
        except sqlite3.Error as e:
            z["fehler"] = str(e)
            kopf = {}
        z["eintraege"] = sum(z["bereiche"].values())
        z["angebot_id"] = int(kopf["angebot_id"]) if kopf.get("angebot_id", "").isdigit() else None
        z["nummer"], z["programm"], z["schema"] = kopf.get("nummer"), kopf.get("programm"), kopf.get("schema")
        for n in ("angelegt", "benutzt"):
            try:
                z[n] = float(kopf[n]) if n in kopf else None
            except ValueError:
                z[n] = None
        out.append(z)
    return out


def _aus_pfad(pfad):
    """Angebots-ID aus dem Dateinamen (A<id>.db) oder None für die allgemeine Datei."""
    name = Path(pfad).stem
    return int(name[1:]) if name.startswith("A") and name[1:].isdigit() else None


def pruefen(pfad=None):
    """Dateien prüfen (SQLite-Prüfung, jeder Eintrag lesbar, doppelte Inhalte). Unlesbare Einträge werden gelöscht,
    eine beschädigte Datei ersetzt. Ergebnis je Datei: dict(pfad, ok, eintraege, unlesbar, doppelt, ersetzt)."""
    leeren()
    out = []
    for p in ([Path(pfad)] if pfad else _alle_pfade()):
        e = dict(pfad=p, ok=True, eintraege=0, unlesbar=0, doppelt=0, ersetzt=False)
        with _sperre:
            d = _datei(_aus_pfad(p))
            con = d.oeffnen() if d is not None else None
            try:
                if con is None:
                    raise sqlite3.DatabaseError("nicht nutzbar")
                if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("quick_check")
                schlecht = []
                for b, s, art, wert in con.execute("SELECT bereich, schluessel, art, wert FROM merker"):
                    e["eintraege"] += 1
                    try:
                        _auspacken(art, wert)
                    except (ValueError, TypeError, zlib.error, UnicodeDecodeError):
                        schlecht.append((b, s))
                for b, s in schlecht:
                    con.execute("DELETE FROM merker WHERE bereich=? AND schluessel=?", (b, s))
                e["unlesbar"] = len(schlecht)
                e["doppelt"] = con.execute("SELECT COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) AS n FROM merker "
                                           "GROUP BY bereich, art, wert HAVING n > 1)").fetchone()[0]
            except sqlite3.DatabaseError:
                e["ok"] = False
                if d is not None:
                    d.schliessen()
                _kaputt.discard(p)
                e["ersetzt"] = _beschaedigt_ersetzen(p)
                if p == (_wurzel / DATEI if _wurzel else None):
                    global _aus
                    _aus = False
        out.append(e)
    return out


def loeschen(angebot="alle"):
    """Merker eines Angebots (ID), der allgemeinen Datei (None) oder alle ("alle") löschen. Rechnet beim nächsten
    Bedarf neu. Ergebnis: Anzahl gelöschter Dateien."""
    leeren()
    with _sperre:
        pfade = _alle_pfade() if angebot == "alle" else [
            p for p in _alle_pfade() if _aus_pfad(p) == _angebot_id(angebot) and (angebot is not None or
                                                                                   p.name == DATEI)]
        n = 0
        for p in pfade:
            d = _dateien.pop(_aus_pfad(p), None)
            if d is not None:
                d.schliessen()
            if _beschaedigt_ersetzen(p):
                n += 1
            _kaputt.discard(p)
        for k in [k for k in _offen if k[0] in pfade]:
            _offen.pop(k, None)
        return n


def exportieren(ziel, angebot="alle"):
    """Merker-Dateien (Sicherungskopie über SQLite) und eine Übersicht als ZIP nach ziel. Ergebnis: Pfad."""
    import tempfile
    import zipfile
    leeren()
    ziel = Path(ziel)
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
        for e in uebersicht():
            if angebot != "alle" and e["angebot_id"] != _angebot_id(angebot):
                continue
            kopie = Path(tmp) / e["pfad"].name
            with _sperre:
                d = _datei(_aus_pfad(e["pfad"]))
                con = d.oeffnen() if d is not None else None
                if con is None:
                    continue
                ziel_con = sqlite3.connect(kopie)
                try:
                    con.backup(ziel_con)
                finally:
                    ziel_con.close()
            z.write(kopie, ("" if e["angebot_id"] is None else ANGEBOTE + "/") + e["pfad"].name)
        z.writestr("uebersicht.json", json.dumps([dict(e, pfad=e["pfad"].name) for e in uebersicht()],
                                                 ensure_ascii=False, indent=1, default=str))
    return ziel


def aufraeumen(angebote=None, jetzt=None):
    """Nur nachweislich nicht mehr Benötigtes weg: Einträge anderer Programmversionen, Dateien zu Angeboten, die es
    nicht mehr gibt (angebote = Menge der vorhandenen IDs; None = nicht prüfen), seit UNBENUTZT_TAGE unbenutzte
    Dateien und über GESAMT_MB die am längsten unbenutzten. Ergebnis: dict(eintraege, dateien)."""
    leeren()
    jetzt = jetzt or time.time()
    weg = dict(eintraege=0, dateien=0)
    liste = uebersicht()
    for e in liste:
        aid = _aus_pfad(e["pfad"])
        alt = (e["benutzt"] or e["angelegt"] or e["geaendert"] or jetzt) < jetzt - UNBENUTZT_TAGE * 86400
        if aid is not None and ((angebote is not None and aid not in angebote) or alt):
            weg["dateien"] += loeschen(aid)
            e["weg"] = True
            continue
        if e["veraltet"]:
            with _sperre:
                d = _datei(aid)
                con = d.oeffnen() if d is not None else None
                try:
                    if con is not None:
                        weg["eintraege"] += con.execute("DELETE FROM merker WHERE version<>?", (VERSION,)).rowcount
                except sqlite3.Error:
                    _datei_fehler(e["pfad"], "Aufräumen gescheitert")
    rest = sorted((e for e in liste if not e.get("weg") and _aus_pfad(e["pfad"]) is not None),
                  key=lambda e: e["benutzt"] or e["angelegt"] or 0)
    summe = sum(e["groesse"] for e in rest)
    while rest and summe > GESAMT_MB * 1024 * 1024:
        e = rest.pop(0)
        summe -= e["groesse"]
        weg["dateien"] += loeschen(_aus_pfad(e["pfad"]))
    return weg


def kennzahlen():
    """Nutzen des Caches seit dem Programmstart (bzw. Zähler zurücksetzen) und Größe auf der Platte:
    dict(gesamt, treffer, neu, quote, gespart_s, rechnen_s, laden_s, nicht_ablegbar, dateien, groesse)."""
    st = stand()
    b = st["bereiche"].values()
    treffer = sum(z["treffer"] for z in b)
    neu = sum(z["neu"] for z in b)
    pfade = _alle_pfade()
    return dict(gesamt=treffer + neu, treffer=treffer, neu=neu,
                quote=(treffer / (treffer + neu)) if treffer + neu else None,
                gespart_s=sum(z["gespart_s"] for z in b), rechnen_s=sum(z["rechnen_s"] for z in b),
                laden_s=sum(z["laden_s"] for z in b), nicht_ablegbar=sum(z["nicht_ablegbar"] for z in b),
                dateien=len(pfade), groesse=sum(_groesse(p) for p in pfade), aus=st["aus"])
