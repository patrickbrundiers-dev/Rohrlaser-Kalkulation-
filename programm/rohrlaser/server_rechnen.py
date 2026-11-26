"""Rechenaufträge am zentralen Server (Serverversion S4, Patrick 26.11.2026). Ohne Qt.

Lange Rechnungen (STEP-Messung großer oder vieler Dateien, Vormessung neuer Anfragen) kann im Serverbetrieb der
Server-Rechner übernehmen. Gerechnet wird mit demselben Messprogramm (STEP-Import.exe) und denselben Einstellungen;
das Ergebnis landet im gemeinsamen Zwischenspeicher der Messung in der Ablage am Server (<Ablage>/STEP-Cache).
Danach misst der Arbeitsplatz wie immer selbst, findet jede Datei im Zwischenspeicher und ist in Sekunden fertig.
So bleibt das Ergebnis bitgleich: der Schlüssel des Zwischenspeichers enthält Dateiinhalt, Programmversion und alle
wirksamen Einstellungen, ein Rechner mit anderer Version erzeugt nur andere Einträge.

- Auftragstabelle server_rechenauftraege: Dateien (Pfade relativ zur Ablage), Messargumente, Zustand
  (neu → laeuft → fertig/fehler; abbrechen → abgebrochen), Fortschritt, Text, wer und welcher Rechner. Gleiche
  offene Aufträge (Schlüssel aus Dateien und Argumenten) werden nicht doppelt angelegt: 25 Plätze, die dieselbe
  Anfrage vormessen, warten auf einen Auftrag.
- Rechner (Befehl „--server rechnen“ auf dem Server-Rechner): holt Aufträge seiner Programmversion
  (FOR UPDATE SKIP LOCKED, auch mehrere Rechner gleichzeitig), meldet Fortschritt und Lebenszeichen
  (server_rechner), bricht auf Wunsch ab. Neue Aufträge weckt LISTEN/NOTIFY (Kanal KANAL).
- Arbeitsplatz: Einstellung rechnen_ort („automatisch“: nur lange Rechnungen an den Server; „am Server“; „an diesem
  Arbeitsplatz“). Ist kein Rechner da, der Server ausgelastet (Auftrag startet nicht in WARTEN_START_S) oder geht
  etwas schief, rechnet der Platz selbst – mit demselben Ergebnis.
"""
import contextlib
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

AUFTRAEGE = "server_rechenauftraege"
RECHNER = "server_rechner"
KANAL = "rl_rechnen"
NEU, LAEUFT, FERTIG, FEHLER, ABBRECHEN, ABGEBROCHEN = "neu", "laeuft", "fertig", "fehler", "abbrechen", "abgebrochen"
OFFEN = (NEU, LAEUFT, ABBRECHEN)
LEBENSZEICHEN_S = 15        # so oft meldet sich ein Rechner
DA_S = 45                   # so lange gilt ein Rechner nach seinem letzten Lebenszeichen als da
WARTEN_START_S = 30         # startet ein Auftrag so lange nicht (Server ausgelastet), rechnet der Platz selbst
ZEITLIMIT_S = 3600          # ein Auftrag höchstens so lange
CACHE = "STEP-Cache"        # Unterordner der Ablage: gemeinsamer Zwischenspeicher der Messung
EINGANG = "_Rechnen"        # Unterordner der Ablage: Dateien von außerhalb der Ablage für einen Auftrag
CACHE_MB_MIN = 5000         # gemeinsamer Zwischenspeicher mindestens so groß (alle Plätze teilen ihn)
STEP_ENDUNGEN = {".step", ".stp", ".stpz", ".p21", ".iges", ".igs"}     # ohne Begleitdateien (TUBX/ARTUBE: lokal)
ORT = "rechnen_ort"
ORT_WAHL = ("automatisch", "am Server", "an diesem Arbeitsplatz")       # [0] = Vorgabe
AUTO_MB = 5.0               # automatisch: an den Server ab dieser Gesamtgröße [MB] …
AUTO_DATEIEN = 10           # … oder ab so vielen Dateien
_FORTSCHRITT = re.compile(r"^\[(\d+)/(\d+)\]")
# Ein-/Ausgabe der Messung: setzt jeder Rechner selbst (eigene Pfade); alles andere ist die Rechnung
_EA = {"--liste": 1, "--ausgabe": 1, "--netze": 1, "--json": 1, "--zwischenstand": 1, "--virtuell": 1}


# ------------------------------------------------------------------------------------------------ Einrichten
def einrichten(con):
    """Tabellen, Trigger und Rechte (als rohrlaser_app nach der Datenpflege; mehrfach aufrufbar)."""
    from . import server_betrieb as sb
    con.execute(f"CREATE TABLE IF NOT EXISTS {AUFTRAEGE} (id BIGSERIAL PRIMARY KEY, art TEXT NOT NULL, "
                "schluessel TEXT NOT NULL, dateien TEXT NOT NULL, args TEXT NOT NULL, netze BOOLEAN, version TEXT, "
                "zustand TEXT NOT NULL, fortschritt INTEGER DEFAULT 0, gesamt INTEGER DEFAULT 0, text TEXT, "
                "meldung TEXT, kuerzel TEXT, platz TEXT, rechner TEXT, angelegt TIMESTAMPTZ DEFAULT now(), "
                "begonnen TIMESTAMPTZ, fertig TIMESTAMPTZ, zeit TIMESTAMPTZ DEFAULT now())")
    con.execute(f"CREATE INDEX IF NOT EXISTS {AUFTRAEGE}_offen ON {AUFTRAEGE} (zustand, id)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {RECHNER} (name TEXT PRIMARY KEY, version TEXT, prozesse INTEGER, "
                "seit TIMESTAMPTZ, zeit TIMESTAMPTZ, auftrag BIGINT)")
    con.execute("CREATE OR REPLACE FUNCTION rl_rechnen_melden() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN "
                f"PERFORM pg_notify('{KANAL}', NEW.zustand || '|' || NEW.id); RETURN NULL; END $f$")
    con.execute(f"DROP TRIGGER IF EXISTS rl_rechnen_neu ON {AUFTRAEGE}")
    con.execute(f"CREATE TRIGGER rl_rechnen_neu AFTER INSERT OR UPDATE OF zustand ON {AUFTRAEGE} FOR EACH ROW "
                "EXECUTE FUNCTION rl_rechnen_melden()")
    # auch wer nur ansehen darf, misst für die 3D-Vorschau und Vormessung (schreibt nur Aufträge, keine Daten)
    con.execute(f'GRANT SELECT, INSERT, UPDATE ON {AUFTRAEGE} TO "{sb.ROLLE_LESEN}"')
    con.execute(f'GRANT USAGE ON SEQUENCE {AUFTRAEGE}_id_seq TO "{sb.ROLLE_LESEN}"')


# ------------------------------------------------------------------------------------------------ Arbeitsplatz
def ort(db):
    w = db.einstellung(ORT) or ORT_WAHL[0]
    return w if w in ORT_WAHL else ORT_WAHL[0]


def verbindung(db):
    """Eigene psycopg-Verbindung des angemeldeten Mitarbeiters (Rolle wie die Hauptverbindung; für Hintergrund-
    Threads und damit Warten die Hauptverbindung nicht blockiert). Ergebnis: db_verbindung.PostgresVerbindung."""
    from . import db_verbindung
    v = db.con.v
    return db_verbindung.PostgresVerbindung(dict(v.zugang), v._passwort, zeitlimit_ms=0)


def zugang(db):
    """Was ein Hintergrund-Thread braucht, um selbst zu verbinden und Dateien abzulegen (ohne Datenbank-Objekt) oder
    None (kein Serverbetrieb, keine erreichbare Ablage)."""
    from . import VERSION, teilen
    if not teilen.server(db):
        return None
    p, ok, _ = teilen.ablage_zustand(db)
    if not ok:
        return None
    v = db.con.v
    return dict(zugang=dict(v.zugang), passwort=v._passwort, ablage=str(p), version=VERSION,
                kuerzel=db.server.kuerzel, platz=db.server.platz, ort=ort(db))


def cache_ordner(db):
    """Gemeinsamer Zwischenspeicher der Messung im Serverbetrieb (<Ablage>/STEP-Cache) oder None."""
    from . import teilen
    if not teilen.server(db):
        return None
    p, ok, _ = teilen.ablage_zustand(db)
    return Path(p) / CACHE if ok else None


def _pg(z):
    from . import db_verbindung
    return db_verbindung.PostgresVerbindung(z["zugang"], z["passwort"], zeitlimit_ms=0)


def rechner_da(con, version):
    """Anzahl der Rechner dieser Programmversion, die sich in den letzten DA_S Sekunden gemeldet haben."""
    return int(con.execute(f"SELECT count(*) FROM {RECHNER} WHERE version = %s AND zeit > now() - "
                           f"interval '{DA_S} seconds'", (version,)).fetchone()[0])


def rechenargumente(args):
    """Messargumente ohne Ein- und Ausgabe (Liste, Ausgabe, Netze, JSON, Zwischenstand): die eigentliche Rechnung."""
    out, i, args = [], 0, list(args)
    while i < len(args):
        if args[i] in _EA:
            i += 1 + _EA[args[i]]
            continue
        out.append(args[i])
        i += 1
    return out


def _datei_hash(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ablegen(ablage, dateien):
    """Dateien für einen Auftrag erreichbar machen: was schon in der Ablage liegt, bleibt dort; anderes kommt nach
    <Ablage>/_Rechnen/<Prüfsumme>/<Name> (nur einmal je Inhalt). Ergebnis: [Pfad relativ zur Ablage] oder None,
    wenn eine Datei nicht passt (Begleitdateien, nicht lesbar)."""
    ablage = Path(ablage)
    try:
        basis = ablage.resolve()
    except OSError:
        return None
    out = []
    for d in map(Path, dateien):
        if d.suffix.lower() not in STEP_ENDUNGEN:
            return None
        try:
            echt = d.resolve()
            out.append(echt.relative_to(basis).as_posix())
            continue
        except ValueError:
            pass
        except OSError:
            return None
        try:
            ziel = ablage / EINGANG / _datei_hash(d)[:24] / d.name
            if not ziel.is_file():
                ziel.parent.mkdir(parents=True, exist_ok=True)
                tmp = ziel.with_name(ziel.name + ".neu")
                shutil.copyfile(d, tmp)
                os.replace(tmp, ziel)
            out.append(ziel.relative_to(ablage).as_posix())
        except OSError:
            return None
    return out


def auftrag_schluessel(dateien_rel, args, netze, version, ablage):
    """Gleiche Rechnung = gleicher Schlüssel (Inhalt der Dateien, nicht nur der Name)."""
    h = hashlib.sha256(json.dumps([sorted(dateien_rel), args, bool(netze), version]).encode("utf-8"))
    for r in sorted(dateien_rel):
        with contextlib.suppress(OSError):
            st = (Path(ablage) / r).stat()
            h.update(f"{r}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8"))
    return h.hexdigest()


def einreichen(con, dateien_rel, args, netze, version, kuerzel="", platz="", art="step", ablage="."):
    """Auftrag anlegen oder einen gleichen offenen Auftrag mitbenutzen. Ergebnis: id."""
    args = rechenargumente(args)
    schl = auftrag_schluessel(dateien_rel, args, netze, version, ablage)
    with con.con.transaction():
        con.con.execute("SELECT pg_advisory_xact_lock(73102)")
        r = con.con.execute(f"SELECT id FROM {AUFTRAEGE} WHERE schluessel = %s AND zustand IN ('{NEU}', '{LAEUFT}') "
                            "ORDER BY id LIMIT 1", (schl,)).fetchone()
        if r:
            return int(r[0])
        return int(con.con.execute(
            f"INSERT INTO {AUFTRAEGE} (art, schluessel, dateien, args, netze, version, zustand, gesamt, kuerzel, platz) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (art, schl, json.dumps(dateien_rel, ensure_ascii=False), json.dumps(args, ensure_ascii=False),
             bool(netze), version, NEU, len(dateien_rel), kuerzel, platz)).fetchone()[0])


def zustand(con, auftrag):
    r = con.con.execute(f"SELECT zustand, fortschritt, gesamt, text, meldung, rechner FROM {AUFTRAEGE} WHERE id = %s",
                        (auftrag,)).fetchone()
    if r is None:
        return None
    return dict(zip(("zustand", "fortschritt", "gesamt", "text", "meldung", "rechner"), r))


def abbrechen(con, auftrag):
    """Abbruch wünschen: ein wartender Auftrag ist sofort abgebrochen, ein laufender beim nächsten Blick des Rechners."""
    con.con.execute(f"UPDATE {AUFTRAEGE} SET zustand = CASE WHEN zustand = '{NEU}' THEN '{ABGEBROCHEN}' ELSE "
                    f"'{ABBRECHEN}' END, zeit = now() WHERE id = %s AND zustand IN ('{NEU}', '{LAEUFT}')", (auftrag,))


def entscheiden(z, dateien):
    """Rechnet der Server? (True/False, Grund) nach Einstellung, Rechner und Größe."""
    if z is None:
        return False, "kein Serverbetrieb oder Ablage am Server nicht erreichbar"
    if z["ort"] == ORT_WAHL[2]:
        return False, "Einstellung: an diesem Arbeitsplatz rechnen"
    if any(Path(d).suffix.lower() not in STEP_ENDUNGEN for d in dateien):
        return False, "Dateiart mit Begleitdatei"
    if z["ort"] == ORT_WAHL[0]:
        try:
            mb = sum(Path(d).stat().st_size for d in dateien) / 1e6
        except OSError:
            return False, "Datei nicht lesbar"
        if mb < AUTO_MB and len(dateien) < AUTO_DATEIEN:
            return False, "kurze Rechnung"
    return True, ""


def am_server_rechnen(z, dateien, args, netze, melden=None, abbruch=None, warten_start_s=WARTEN_START_S,
                      zeitlimit_s=ZEITLIMIT_S, entscheiden_=True):
    """Dateien am Server vorrechnen lassen und warten (Hintergrund-Thread oder Fortschrittsanzeige). z: zugang(db).
    melden(fertig, gesamt, text); abbruch() -> True bricht ab. Ergebnis: (Erfolg, Grund) – Erfolg heißt: die
    Messung liegt im gemeinsamen Zwischenspeicher, der Platz misst danach sofort. Sonst rechnet der Platz selbst."""
    if entscheiden_:
        ja, grund = entscheiden(z, dateien)
        if not ja:
            return False, grund
    if "--cache" not in list(args)[:-1]:
        return False, "Zwischenspeicher der Messung ist ausgeschaltet"
    con = None
    try:
        con = _pg(z)
        if not rechner_da(con.con, z["version"]):
            return False, "kein Rechner am Server (Befehl „--server rechnen“) mit dieser Programmversion"
        rel = ablegen(z["ablage"], dateien)
        if rel is None:
            return False, "Dateien nicht in die Ablage am Server kopierbar"
        auftrag = einreichen(con, rel, args, netze, z["version"], z.get("kuerzel", ""), z.get("platz", ""),
                             ablage=z["ablage"])
        start = time.monotonic()
        while True:
            d = zustand(con, auftrag)
            if d is None:
                return False, "Auftrag verschwunden"
            if d["zustand"] == FERTIG:
                return True, f"am Server gerechnet ({d.get('rechner') or ''})"
            if d["zustand"] in (FEHLER, ABGEBROCHEN):
                return False, f"am Server: {d.get('meldung') or d['zustand']}"
            if melden is not None:
                melden(int(d["fortschritt"] or 0), int(d["gesamt"] or len(rel)),
                       d.get("text") or ("wartet auf den Rechner am Server …" if d["zustand"] == NEU else ""))
            if abbruch is not None and abbruch():
                abbrechen(con, auftrag)
                return False, "abgebrochen"
            vor = time.monotonic() - start
            if d["zustand"] == NEU and vor > warten_start_s:
                abbrechen(con, auftrag)
                return False, "Server ausgelastet"
            if vor > zeitlimit_s:
                abbrechen(con, auftrag)
                return False, "Zeitlimit am Server"
            time.sleep(0.25)
    except Exception as e:      # noqa: BLE001 - jeder Fehler am Server: der Platz rechnet selbst
        return False, f"Server: {e}"
    finally:
        if con is not None:
            with contextlib.suppress(Exception):
                con.schliessen()


def status_text(db):
    """Eine Zeile für Datei → Datenbank: Rechner am Server, wartende Aufträge, Einstellung dieses Platzes."""
    from . import VERSION
    da = db.con.execute(f"SELECT count(*) FROM {RECHNER} WHERE version = ? AND zeit > now() - interval '{DA_S} seconds'",
                        (VERSION,)).fetchone()[0]
    wartend = db.con.execute(f"SELECT count(*) FROM {AUFTRAEGE} WHERE zustand IN ('{NEU}', '{LAEUFT}')").fetchone()[0]
    wer = f"{da} Rechner bereit" if da else "kein Rechner bereit (am Server „--server rechnen“ starten)"
    return f"Rechnen am Server: {wer}, {wartend} Auftrag/Aufträge offen; dieser Platz: {ort(db)}"


# ------------------------------------------------------------------------------------------------ Rechner (Server)
def _cache_tauschen(args, cache):
    out = list(args)
    if "--cache" in out[:-1]:
        out[out.index("--cache") + 1] = str(cache)
    if "--cache-mb" in out[:-1]:
        i = out.index("--cache-mb") + 1
        with contextlib.suppress(ValueError):
            out[i] = f"{max(float(out[i]), CACHE_MB_MIN):g}"
    return out


class Rechner:
    """Rechnet Aufträge am Server-Rechner. verbinden() -> psycopg-Verbindung (autocommit, Rolle rohrlaser_app);
    ablage: Ablage-Ordner auf diesem Rechner; befehl: Messprogramm (step.messprogramm)."""

    def __init__(self, verbinden, ablage, befehl, version, name=None, prozesse=0, ausgabe=print):
        self.verbinden = verbinden
        self.ablage = Path(ablage)
        self.befehl = list(befehl)
        self.version = version
        self.name = name or f"{socket.gethostname()}-{os.getpid()}"
        self.prozesse = int(prozesse)
        self.ausgabe = ausgabe
        self.con = None
        self._zuletzt = 0.0

    def _verbindung(self):
        if self.con is None or self.con.closed:
            self.con = self.verbinden()
            self.con.execute(f"LISTEN {KANAL}")
        return self.con

    def lebenszeichen(self, auftrag=None, sofort=False):
        if not sofort and time.monotonic() - self._zuletzt < LEBENSZEICHEN_S:
            return
        self._verbindung().execute(
            f"INSERT INTO {RECHNER} (name, version, prozesse, seit, zeit, auftrag) VALUES (%s, %s, %s, now(), now(), "
            f"%s) ON CONFLICT (name) DO UPDATE SET version = excluded.version, prozesse = excluded.prozesse, "
            "zeit = now(), auftrag = excluded.auftrag", (self.name, self.version, self.prozesse, auftrag))
        self._zuletzt = time.monotonic()

    def abmelden(self):
        with contextlib.suppress(Exception):
            self._verbindung().execute(f"DELETE FROM {RECHNER} WHERE name = %s", (self.name,))

    def holen(self):
        """Nächsten Auftrag dieser Version übernehmen: dict oder None."""
        c = self._verbindung()
        with c.transaction():
            r = c.execute(f"UPDATE {AUFTRAEGE} SET zustand = '{LAEUFT}', begonnen = now(), zeit = now(), rechner = %s "
                          f"WHERE id = (SELECT id FROM {AUFTRAEGE} WHERE zustand = '{NEU}' AND version = %s "
                          "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id, dateien, args, netze",
                          (self.name, self.version)).fetchone()
        if r is None:
            return None
        return dict(id=int(r[0]), dateien=json.loads(r[1]), args=json.loads(r[2]), netze=bool(r[3]))

    def _setzen(self, auftrag, **werte):
        teile = ", ".join(f"{k} = %s" for k in werte)
        self._verbindung().execute(f"UPDATE {AUFTRAEGE} SET {teile}, zeit = now() WHERE id = %s",
                                   (*werte.values(), auftrag))

    def _abbruch_gewuenscht(self, auftrag):
        r = self._verbindung().execute(f"SELECT zustand FROM {AUFTRAEGE} WHERE id = %s", (auftrag,)).fetchone()
        return r is None or r[0] == ABBRECHEN

    def rechnen(self, a):
        """Einen Auftrag rechnen (Messprogramm als eigener Prozess). Ergebnis: Endzustand."""
        self.lebenszeichen(a["id"], sofort=True)
        dateien = [self.ablage / r for r in a["dateien"]]
        fehlt = [str(d) for d in dateien if not d.is_file()]
        if fehlt:
            self._setzen(a["id"], zustand=FEHLER, fertig=_jetzt_sql(), meldung="Datei fehlt am Server: " + fehlt[0])
            return FEHLER
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            liste_, ausgabe = tmp / "liste.txt", tmp / "messwerte.txt"
            liste_.write_text("\n".join(map(str, dateien)), encoding="utf-8")
            befehl = self.befehl + ["--liste", str(liste_), "--ausgabe", str(ausgabe)] \
                + (["--netze", str(tmp / "netze")] if a["netze"] else []) \
                + _cache_tauschen(a["args"], self.ablage / CACHE)
            if self.prozesse and "--prozesse" in befehl[:-1]:
                befehl[befehl.index("--prozesse") + 1] = str(self.prozesse)
            umgebung = dict(os.environ, PYTHONIOENCODING="utf-8")
            proz = subprocess.Popen(befehl, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    encoding="utf-8", errors="replace", env=umgebung,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            stand, fehler_text = dict(fertig=0, gesamt=len(dateien), text=""), []

            def lesen():
                for z in proz.stdout:
                    m = _FORTSCHRITT.match(z)
                    if m:
                        stand.update(fertig=int(m.group(1)), gesamt=int(m.group(2)), text=z.strip())

            def fehler_lesen():
                for z in proz.stderr:
                    if z.strip():
                        fehler_text.append(z.strip())
                        del fehler_text[:-5]
            leser = [threading.Thread(target=f, daemon=True) for f in (lesen, fehler_lesen)]
            for t in leser:
                t.start()
            start, gemeldet, ende = time.monotonic(), None, None
            while proz.poll() is None:
                time.sleep(0.5)
                if (stand["fertig"], stand["text"]) != gemeldet:
                    gemeldet = (stand["fertig"], stand["text"])
                    self._setzen(a["id"], fortschritt=stand["fertig"], gesamt=stand["gesamt"], text=stand["text"])
                self.lebenszeichen(a["id"])
                if self._abbruch_gewuenscht(a["id"]):
                    ende = ABGEBROCHEN
                elif time.monotonic() - start > ZEITLIMIT_S:
                    ende = FEHLER
                    fehler_text.append(f"Zeitlimit {ZEITLIMIT_S} s")
                if ende:
                    proz.kill()
                    break
            proz.wait()
            for t in leser:
                t.join(5)
            if ende is None:
                ende = FERTIG if proz.returncode == 0 and ausgabe.is_file() else FEHLER
            if ende == FERTIG:
                meldung = f"{stand['gesamt']} Datei(en) in {time.monotonic() - start:.0f} s"
            elif ende == ABGEBROCHEN:
                meldung = "auf Wunsch abgebrochen"
            else:
                meldung = "; ".join(fehler_text[-2:]) or f"Messprogramm beendet mit {proz.returncode}"
            self._setzen(a["id"], zustand=ende, fortschritt=stand["fertig"], fertig=_jetzt_sql(), meldung=meldung)
        self.lebenszeichen(None, sofort=True)
        self.ausgabe(f"Auftrag {a['id']}: {ende} – {meldung}")
        return ende

    def einmal(self):
        """Alle wartenden Aufträge rechnen. Ergebnis: Anzahl."""
        n = 0
        self.lebenszeichen(sofort=True)
        while True:
            a = self.holen()
            if a is None:
                return n
            self.rechnen(a)
            n += 1

    def laufen(self, stop=None):
        """Dauerbetrieb bis stop gesetzt ist: rechnen, sonst auf neue Aufträge warten (NOTIFY, spätestens alle 5 s
        nachsehen); nach einem Verbindungsabbruch neu verbinden."""
        stop = stop or threading.Event()
        pause = 1.0
        while not stop.is_set():
            try:
                self.einmal()
                for _ in self._verbindung().notifies(timeout=5.0, stop_after=1):
                    pass
                pause = 1.0
            except Exception as e:      # noqa: BLE001 - Netz/Server weg: warten, neu verbinden
                self.ausgabe(f"Rechner: {e} – neuer Versuch in {pause:.0f} s")
                with contextlib.suppress(Exception):
                    if self.con is not None:
                        self.con.close()
                self.con = None
                stop.wait(pause)
                pause = min(pause * 2, 30.0)
        self.abmelden()


def _jetzt_sql():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc)
