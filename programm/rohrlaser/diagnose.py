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

Erweitert 21.11.2026 (Master-Prompt Rechenkerne und Systemstabilität, Punkte 7 und 9):
- Fehlgeschlagene Berechnungen (fehlgeschlagen): z. B. Kalkulationen mit ungültigem Ergebnis (rechenpruefung).
- Datenbank-Antwortzeiten in Stufen (bis 1 ms, 10 ms, 100 ms, 1 s, darüber) und die längste Anweisung.
- Hintergrundaufgaben (hintergrund.py): was läuft seit wann, fertige Läufe je Aufgabe.
- befunde(): selbständige Erkennung ungewöhnlicher Zustände (lange Rechenzeiten, viele Doppelrechnungen, hoher
  Speicher, langsame Datenbank, Fehler, ausgeschalteter Cache, lange laufende Hintergrundaufgaben, Hänger der
  Oberfläche) mit Stufe, technischer Angabe und konkreter Handlungsempfehlung; stehen oben im Bericht.
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
DB_STUFEN = (0.001, 0.01, 0.1, 1.0)     # Grenzen der Antwortzeit-Stufen in s
_db_stufen = [0] * (len(DB_STUFEN) + 1)
_db_max = [0.0]
_fehlgeschlagen = {}        # Name -> [Anzahl, letzte Texte]
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
        i = 0
        while i < len(DB_STUFEN) and dauer > DB_STUFEN[i]:
            i += 1
        _db_stufen[i] += 1
        if dauer > _db_max[0]:
            _db_max[0] = dauer


def fehlgeschlagen(name, text=""):
    """Fehlgeschlagene bzw. als ungültig erkannte Berechnung zählen (rechenpruefung, Wiederherstellung)."""
    with _sperre:
        e = _fehlgeschlagen.setdefault(name, [0, collections.deque(maxlen=5)])
        e[0] += 1
        if text:
            e[1].append(str(text)[:300])


def merker_zaehlen(art, treffer):
    with _sperre:
        _merker_intern[(art, "treffer" if treffer else "neu")] += 1


def stand():
    """Alle Zähler als dict (für Tests und den Bericht)."""
    from . import rechenmerker
    with _sperre:
        rech = {n: dict(anzahl=e[0], summe_s=e[1], max_s=e[2], langsam=e[3], doppelt=e[4])
                for n, e in _rechnungen.items()}
        db = dict(anweisungen=_db[0], summe_s=_db[1], stufen=list(_db_stufen), max_s=_db_max[0])
        intern = dict(_merker_intern)
        fehl = {n: dict(anzahl=e[0], letzte=list(e[1])) for n, e in _fehlgeschlagen.items()}
    arten = sorted({a for a, _ in intern})
    merker = rechenmerker.stand() + [dict(name=f"Rechenlauf: {a}", eintraege=None, groesse=None,
                                          treffer=intern.get((a, "treffer"), 0), neu=intern.get((a, "neu"), 0),
                                          dauer_s=None) for a in arten]
    from . import dauermerker                   # Merker über den Programmstart hinaus (19.11.2026)
    d = dauermerker.stand()
    merker.append(dict(name="Über Neustart gemerkt" + (" (aus)" if d["aus"] else ""), eintraege=d["eintraege"],
                       groesse=dauermerker.GROESSE, treffer=d["treffer"], neu=d["neu"], dauer_s=None))
    cache = d["bereiche"]
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
    try:
        from . import tempo
        haenger = tempo.haenger_anzahl
    except Exception:           # noqa: BLE001
        haenger = None
    from . import hintergrund
    return dict(seit_s=time.time() - _start, rechnungen=rech, merker=merker, db=db, fehler=fehler,
                warnungen=warnungen, speicher_mb=speicher, cache=cache, fehlgeschlagen=fehl,
                hintergrund=hintergrund.laufend(), hintergrund_fertig=hintergrund.beendet(),
                hintergrund_lang=hintergrund.befunde(), cache_aus=dauermerker.gestoert(), haenger=haenger)


def zuruecksetzen():
    """Zähler auf null (Fenster „Zähler zurücksetzen“); Merker-Inhalte bleiben, nur ihre Zähler beginnen neu."""
    global _start
    from . import rechenmerker
    with _sperre:
        _rechnungen.clear()
        _letzte.clear()
        _db[0], _db[1] = 0, 0.0
        _db_stufen[:] = [0] * len(_db_stufen)
        _db_max[0] = 0.0
        _fehlgeschlagen.clear()
        _merker_intern.clear()
        _start = time.time()
    for m in rechenmerker.alle().values():
        m.treffer = m.neu = 0
        m.dauer_s = 0.0
    from . import dauermerker, hintergrund
    dauermerker.zaehler_zuruecksetzen()
    hintergrund.zuruecksetzen()


def _z(w, stellen=0):
    if w is None:
        return "–"
    t = f"{w:,.{stellen}f}"
    return t.replace(",", "X").replace(".", ",").replace("X", ".")


# Grenzen der selbständigen Erkennung (befunde)
ROT, GELB = "ROT", "GELB"
LANGE_RECHNUNG_S = 15.0     # eine Rechnung länger: auffällig
LANGSAM_ANTEIL = 0.25       # so viele Läufe einer Rechnung über LANGSAM_S: auffällig (ab 8 Läufen)
DOPPELT_ANTEIL = 0.10       # so viele unnötige Mehrfachberechnungen: auffällig (ab 10 Läufen)
SPEICHER_GELB_MB, SPEICHER_ROT_MB = 1500, 3000
DB_MITTEL_MS = 20.0         # mittlere Antwortzeit darüber: langsam
DB_LANGSAM_ANTEIL = 0.01    # Anteil Anweisungen über 100 ms darüber: langsam (ab 200 Anweisungen)

EMPFEHLUNG_RECHNUNG = {
    "Optimieren": "Sehr große Gruppen (viele verschiedene Längen derselben Abmessung) brauchen am längsten. "
                  "Optimieren im Hintergrund abwarten; bleibt es langsam, Support-Paket an den Entwickler senden.",
    "Maschinenvergleich": "Der Vergleich rechnet das Angebot auf allen Maschinen. Er lässt sich unter Einstellungen → "
                          "Angebot abschalten oder auf wenige Maschinen begrenzen.",
    "Kalkulation": "Viele Schweißbaugruppen, Sätze oder Konturen verlängern die Kalkulation. Support-Paket senden, "
                   "damit die Stelle gemessen werden kann.",
    "Staffeln": "Jede Mengenstufe wird optimiert und kalkuliert. Weniger Stufen anlegen oder die Berechnung im "
                "Hintergrund abwarten.",
}


def befunde(s=None):
    """Selbständige Erkennung: [(Stufe ROT|GELB, Befund, Handlungsempfehlung)], ROT zuerst; leer = unauffällig."""
    s = s or stand()
    out = []
    for n, e in (s.get("fehlgeschlagen") or {}).items():
        letzte = e["letzte"][-1] if e["letzte"] else ""
        out.append((ROT, f"{n}: {e['anzahl']} Berechnung(en) mit ungültigem Ergebnis erkannt"
                    + (f" (zuletzt: {letzte})" if letzte else ""),
                    "Das Ergebnis wurde nicht still übernommen (Angebots-Check zeigt FEHLER). Eingaben und Stammdaten "
                    "der genannten Position prüfen; tritt es wiederholt auf, Support-Paket senden."))
    for n, e in sorted(s["rechnungen"].items()):
        rat = EMPFEHLUNG_RECHNUNG.get(n, "Support-Paket senden, damit die Stelle gemessen werden kann.")
        if e["max_s"] > LANGE_RECHNUNG_S:
            out.append((GELB, f"{n}: längster Lauf {_z(e['max_s'], 1)} s (Grenze {_z(LANGE_RECHNUNG_S, 0)} s)", rat))
        elif e["anzahl"] >= 8 and e["langsam"] > LANGSAM_ANTEIL * e["anzahl"]:
            out.append((GELB, f"{n}: {e['langsam']} von {e['anzahl']} Läufen länger als {_z(LANGSAM_S, 1)} s", rat))
        if e["anzahl"] >= 10 and e["doppelt"] > DOPPELT_ANTEIL * e["anzahl"]:
            out.append((GELB, f"{n}: {e['doppelt']} von {e['anzahl']} Läufen mit genau denselben Eingaben "
                        "(unnötige Mehrfachberechnung)",
                        "Hier fehlt ein Merker. Bitte Support-Paket senden (diagnose.txt zeigt die Stelle)."))
    mb = s.get("speicher_mb")
    if mb and mb > SPEICHER_GELB_MB:
        out.append((ROT if mb > SPEICHER_ROT_MB else GELB, f"Arbeitsspeicher {_z(mb)} MB",
                    "Große STEP-Dateien und viele offene Angebote belegen Speicher. Nicht benötigte Angebote und "
                    "3D-Fenster schließen; das Programm bei Gelegenheit neu starten."))
    db = s["db"]
    if db["anweisungen"] >= 200:
        mittel = 1000 * db["summe_s"] / db["anweisungen"]
        lang = sum((db.get("stufen") or [0])[3:])
        if mittel > DB_MITTEL_MS or lang > DB_LANGSAM_ANTEIL * db["anweisungen"]:
            out.append((GELB, f"Datenbank langsam: im Mittel {_z(mittel, 1)} ms je Anweisung, {_z(lang)} über "
                        f"100 ms, längste {_z(1000 * db.get('max_s', 0), 0)} ms",
                        "Liegt der Datenspeicher auf einem Netzlaufwerk oder läuft gerade eine Sicherung? Datenspeicher "
                        "lokal halten (Datei → Datenspeicher); bleibt es langsam, Support-Paket senden."))
    if s.get("fehler"):
        out.append((GELB, f"{s['fehler']} unerwartete Fehler in diesem Lauf",
                    "Details stehen in Daten/Protokoll/fehler.log. Support-Paket senden, wenn sich ein Fehler "
                    "wiederholt."))
    if s.get("cache_aus"):
        out.append((GELB, "Merker über den Neustart ist ausgeschaltet (Fehler beim Lesen oder Schreiben)",
                    "Das Programm rechnet ohne Merker richtig, nur langsamer. Schreibrechte im Ordner "
                    "Daten/Rechenmerker prüfen; nach einem Neustart wird er neu angelegt."))
    for n, seit in s.get("hintergrund_lang") or ():
        out.append((GELB, f"Hintergrundaufgabe „{n}“ läuft seit {_z(seit / 60, 0)} min",
                    "Möglicherweise blockiert. Den Vorgang abbrechen (falls angeboten) oder das Programm nach dem "
                    "Speichern neu starten; tritt es wiederholt auf, Support-Paket senden."))
    if s.get("haenger"):
        out.append((GELB, f"Die Oberfläche hing {s['haenger']}× länger als 10 s",
                    "Ort und Funktion stehen in Daten/Protokoll/tempo.log. Support-Paket senden."))
    out.sort(key=lambda b: b[0] != ROT)
    return out


def bericht(s=None):
    """Lesbarer Bericht (Text, feste Spaltenbreite)."""
    s = s or stand()
    h, rest = divmod(int(s["seit_s"]), 3600)
    zeilen = [f"Diagnose seit {h} h {rest // 60} min (Programmstart oder Zähler zurückgesetzt)", ""]
    bf = befunde(s)
    zeilen.append("Befunde und Empfehlungen")
    if not bf:
        zeilen.append("  keine Auffälligkeiten")
    import textwrap
    for stufe, befund, rat in bf:
        zeilen += textwrap.wrap(f"[{stufe}] {befund}", 104, initial_indent="  ", subsequent_indent="         ")
        zeilen += textwrap.wrap(f"→ {rat}", 104, initial_indent="         ", subsequent_indent="           ")
    zeilen.append("")
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
    zeilen += ["", "Angebots-Cache (über Neustart)          gesamt  aus Cache      neu   Quote  gespart s  Laden s"]
    for b, z in sorted((s.get("cache") or {}).items()):
        alle = z["treffer"] + z["neu"]
        quote = f"{100 * z['treffer'] / alle:.0f} %" if alle else "–"
        zeilen.append(f"{b[:38]:38} {_z(alle):>6} {_z(z['treffer']):>10} {_z(z['neu']):>8} {quote:>7} "
                      f"{_z(z['gespart_s'], 1):>10} {_z(z['laden_s'], 2):>8}")
    if not s.get("cache"):
        zeilen.append("(noch nichts)")
    db = s["db"]
    st = db.get("stufen")
    zeilen += ["", f"Datenbank: {_z(db['anweisungen'])} Anweisungen, zusammen {_z(db['summe_s'], 1)} s"
               + (f", längste {_z(1000 * db.get('max_s', 0), 0)} ms" if db.get("max_s") else "")]
    if st and db["anweisungen"]:
        zeilen.append("  Antwortzeiten: " + " · ".join(f"{t} {_z(n)}" for t, n in zip(
            ("bis 1 ms", "bis 10 ms", "bis 100 ms", "bis 1 s", "länger"), st)))
    zeilen += [f"Fehler in diesem Lauf: {_z(s['fehler'])} unerwartete, {_z(s['warnungen'])} Warnungen im Protokoll",
               f"Arbeitsspeicher jetzt: {_z(s['speicher_mb'])} MB"]
    fehl = s.get("fehlgeschlagen") or {}
    if fehl:
        zeilen += ["", "Fehlgeschlagene bzw. als ungültig erkannte Berechnungen"]
        for n, e in sorted(fehl.items()):
            zeilen.append(f"  {n}: {_z(e['anzahl'])}" + (f" – zuletzt {e['letzte'][-1]}" if e["letzte"] else ""))
    zeilen += ["", "Hintergrundaufgaben (laufend)"]
    lauf = s.get("hintergrund") or []
    for n, seit in lauf:
        zeilen.append(f"  {n[:40]:40} " + (f"seit {_z(seit, 1)} s" if seit is not None else "(ohne Meldung)"))
    if not lauf:
        zeilen.append("  keine")
    fertig = s.get("hintergrund_fertig") or {}
    if fertig:
        zeilen.append("Hintergrundaufgaben (fertig)           Anzahl   gesamt s   längste s")
        for n, e in sorted(fertig.items()):
            zeilen.append(f"  {n[:36]:36} {_z(e['anzahl']):>6} {_z(e['summe_s'], 1):>10} {_z(e['max_s'], 1):>11}")
    return "\n".join(zeilen) + "\n"
