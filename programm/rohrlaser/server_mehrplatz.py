"""Mehrbenutzerbetrieb am zentralen Server (Serverversion S2, Patrick 26.11.2026). Ohne Qt.

- Anwesenheit (Tabelle server_anwesenheit): jeder Arbeitsplatz meldet alle PULS_S Sekunden, wer dort angemeldet ist,
  welche Angebote er bearbeitet und welche Stammdatenzeilen er gerade geändert hat. Wer länger als ONLINE_S nichts
  gemeldet hat, gilt als weg. Dieselben Angaben wie die Lebenszeichen im gemeinsamen Ordner (teilen.lebenszeichen),
  damit „Kollegen“, „● geöffnet“ und die weiche Sperre für Stammdaten unverändert weiterlaufen.
- Bearbeitungsreservierung (Tabelle server_sperren): ein Angebot bearbeitet immer nur ein Arbeitsplatz. Wer es
  öffnet, reserviert es; die anderen sehen es nur an (wie ein Angebot eines Kollegen im Ordnerbetrieb). Die
  Reservierung lebt vom Puls: stürzt ein Arbeitsplatz ab oder ist das Netz weg, wird sie nach FRISCH_S Sekunden frei.
  Übernehmen geht mit Rückfrage; der bisherige Platz merkt es beim nächsten Puls und schaltet auf Ansehen.
- Live-Aktualisierung: Trigger melden jede Änderung an einem Angebot und jede Reservierung über LISTEN/NOTIFY (Kanal
  KANAL); der Zuhoerer (eigener Thread, eigene Verbindung) sammelt die Meldungen, die Oberfläche holt sie ab.
- Benutzerverwaltung: die Programm-Benutzer (rollen.py) sind im Serverbetrieb die Logins am Server. Angelegt,
  geändert und gesperrt wird über die Serverfunktion rl_benutzer_pflegen (SECURITY DEFINER, nur Verwalter), damit
  kein Login selbst Rollen anlegen darf.
- Protokoll (Tabelle server_protokoll): Anmelden, Abmelden, Übernahmen und Benutzeränderungen mit Kürzel und Platz.
"""
import contextlib
import json
import queue
import threading

from . import db_verbindung
from . import server_betrieb as sb

ANWESEND = "server_anwesenheit"
SPERREN = "server_sperren"
PROTOKOLL = "server_protokoll"
KANAL = "rl_aenderung"
FUNKTION_LIVE = "rl_live_melden"
FUNKTION_BENUTZER = "rl_benutzer_pflegen"
PULS_S = 15             # so oft meldet sich ein Arbeitsplatz (Anwesenheit, Reservierungen verlängern)
ONLINE_S = 60           # so lange gilt ein Arbeitsplatz nach seinem letzten Puls als da
FRISCH_S = 90           # so lange hält eine Reservierung ohne Puls (Absturz, Netz weg)
ANGEBOT = "angebot:"    # Objekt einer Reservierung: angebot:<id>

# Arten im Protokoll
P_ANMELDEN, P_ABMELDEN, P_UEBERNOMMEN, P_BENUTZER = "anmelden", "abmelden", "uebernommen", "benutzer"


def aktiv(db):
    return getattr(db, "server", None) is not None


def _s(db):
    return db.server


# ------------------------------------------------------------------------------------------------ Einrichten
_LIVE_SQL = f"""
CREATE OR REPLACE FUNCTION {FUNKTION_LIVE}() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF TG_TABLE_NAME = 'angebot_aenderungen' THEN
    IF NEW.angebot_id > 0 THEN
      PERFORM pg_notify('{KANAL}', 'a|' || NEW.angebot_id || '|' || pg_backend_pid());
    END IF;
  ELSIF TG_OP = 'DELETE' THEN
    PERFORM pg_notify('{KANAL}', 'r|' || OLD.objekt || '|' || pg_backend_pid());
  ELSE
    PERFORM pg_notify('{KANAL}', 'r|' || NEW.objekt || '|' || pg_backend_pid());
  END IF;
  RETURN NULL;
END $f$"""

# Benutzer pflegen als Serverfunktion (läuft mit den Rechten des Server-Verwalters, der sie beim Einrichten
# anlegt). Nur Mitglieder von rohrlaser_verwalter dürfen sie ausführen; sie fasst nur Logins rl_… an.
_BENUTZER_SQL = f"""
CREATE OR REPLACE FUNCTION public.{FUNKTION_BENUTZER}(p_kuerzel text, p_passwort text, p_recht text, p_name text,
                                                    p_aktiv boolean, p_entfernen boolean DEFAULT false)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
DECLARE
  login text := '{sb.LOGIN_PRAEFIX}' || lower(p_kuerzel);
  verwalter_rest integer;
BEGIN
  IF NOT pg_has_role(session_user, '{sb.ROLLE_VERWALTER}', 'MEMBER') THEN
    RAISE EXCEPTION 'Nur ein Verwalter darf Benutzer am Server anlegen oder ändern.' USING ERRCODE = '42501';
  END IF;
  IF p_kuerzel IS NULL OR p_kuerzel !~ '^[A-Za-z0-9]{{1,5}}$' THEN
    RAISE EXCEPTION 'Ungültiges Kürzel: %', p_kuerzel USING ERRCODE = '22023';
  END IF;
  IF p_recht NOT IN ('{sb.RECHT_BEARBEITEN}', '{sb.RECHT_LESEN}', '{sb.RECHT_VERWALTER}') THEN
    RAISE EXCEPTION 'Unbekanntes Recht: %', p_recht USING ERRCODE = '22023';
  END IF;
  IF login = session_user AND (p_entfernen OR NOT p_aktiv OR p_recht <> '{sb.RECHT_VERWALTER}') THEN
    RAISE EXCEPTION 'Den eigenen Zugang kann man nicht sperren, entfernen oder herabstufen.' USING ERRCODE = '22023';
  END IF;
  IF p_entfernen OR NOT p_aktiv OR p_recht <> '{sb.RECHT_VERWALTER}' THEN
    SELECT count(*) INTO verwalter_rest FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
      JOIN pg_roles u ON u.oid = m.member
      WHERE g.rolname = '{sb.ROLLE_VERWALTER}' AND u.rolcanlogin AND u.rolname <> login;
    IF verwalter_rest = 0 AND pg_has_role(login, '{sb.ROLLE_VERWALTER}', 'MEMBER') THEN
      RAISE EXCEPTION 'Es muss mindestens ein aktiver Verwalter bleiben.' USING ERRCODE = '22023';
    END IF;
  END IF;
  IF p_entfernen THEN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = login) THEN
      EXECUTE format('DROP ROLE %I', login);
    END IF;
    RETURN login;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = login) THEN
    IF p_passwort IS NULL THEN
      RAISE EXCEPTION 'Für einen neuen Benutzer am Server bitte ein Passwort vergeben.' USING ERRCODE = '22023';
    END IF;
    EXECUTE format('CREATE ROLE %I NOLOGIN NOINHERIT', login);
  END IF;
  IF p_passwort IS NOT NULL THEN
    IF length(p_passwort) < 8 THEN
      RAISE EXCEPTION 'Das Passwort braucht mindestens 8 Zeichen.' USING ERRCODE = '22023';
    END IF;
    EXECUTE format('ALTER ROLE %I PASSWORD %L', login, p_passwort);
  END IF;
  EXECUTE format('ALTER ROLE %I %s', login, CASE WHEN p_aktiv THEN 'LOGIN' ELSE 'NOLOGIN' END);
  IF p_recht IN ('{sb.RECHT_BEARBEITEN}', '{sb.RECHT_VERWALTER}') THEN
    EXECUTE format('GRANT %I TO %I', '{sb.ROLLE_APP}', login);
    EXECUTE format('REVOKE %I FROM %I', '{sb.ROLLE_LESEN}', login);
  ELSE
    EXECUTE format('GRANT %I TO %I', '{sb.ROLLE_LESEN}', login);
    EXECUTE format('REVOKE %I FROM %I', '{sb.ROLLE_APP}', login);
  END IF;
  IF p_recht = '{sb.RECHT_VERWALTER}' THEN
    EXECUTE format('GRANT %I TO %I', '{sb.ROLLE_VERWALTER}', login);
  ELSE
    EXECUTE format('REVOKE %I FROM %I', '{sb.ROLLE_VERWALTER}', login);
  END IF;
  IF p_name IS NOT NULL THEN
    EXECUTE format('COMMENT ON ROLE %I IS %L', login, p_name);
  END IF;
  RETURN login;
END $f$"""


def verwalter_einrichten(con):
    """Serverfunktion zum Pflegen der Benutzer (als Server-Verwalter/Superuser; beim Einrichten und Starten)."""
    con.execute(_BENUTZER_SQL)
    con.execute(f"REVOKE ALL ON FUNCTION public.{FUNKTION_BENUTZER}(text, text, text, text, boolean, boolean) "
                "FROM PUBLIC")
    con.execute(f'GRANT EXECUTE ON FUNCTION public.{FUNKTION_BENUTZER}(text, text, text, text, boolean, boolean) '
                f'TO "{sb.ROLLE_VERWALTER}"')


def einrichten(con):
    """Tabellen, Live-Trigger und Rechte (als rohrlaser_app nach der Datenpflege; mehrfach aufrufbar)."""
    con.execute(f"CREATE TABLE IF NOT EXISTS {ANWESEND} (kuerzel TEXT NOT NULL, platz TEXT NOT NULL, name TEXT, "
                "version TEXT, seit TIMESTAMPTZ, zeit TIMESTAMPTZ, offen TEXT, zeilen TEXT, ende BOOLEAN, "
                "PRIMARY KEY (kuerzel, platz))")
    con.execute(f"CREATE TABLE IF NOT EXISTS {SPERREN} (objekt TEXT PRIMARY KEY, kuerzel TEXT NOT NULL, "
                "platz TEXT NOT NULL, titel TEXT, seit TIMESTAMPTZ, zeit TIMESTAMPTZ)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {PROTOKOLL} (id BIGSERIAL PRIMARY KEY, zeit TIMESTAMPTZ DEFAULT now(), "
                "kuerzel TEXT, platz TEXT, art TEXT, objekt TEXT, text TEXT)")
    con.execute(_LIVE_SQL)
    for name, tabelle, art in (("rl_live_angebot", "angebot_aenderungen", "INSERT OR UPDATE"),
                               ("rl_live_sperre", SPERREN, "INSERT OR DELETE")):
        con.execute(f"DROP TRIGGER IF EXISTS {name} ON {tabelle}")
        con.execute(f"CREATE TRIGGER {name} AFTER {art} ON {tabelle} FOR EACH ROW EXECUTE FUNCTION {FUNKTION_LIVE}()")
    # Verlängern (nur zeit) meldet nichts, nur ein Wechsel des Inhabers
    con.execute(f"DROP TRIGGER IF EXISTS rl_live_sperre_wechsel ON {SPERREN}")
    con.execute(f"CREATE TRIGGER rl_live_sperre_wechsel AFTER UPDATE ON {SPERREN} FOR EACH ROW WHEN "
                "(OLD.kuerzel IS DISTINCT FROM NEW.kuerzel OR OLD.platz IS DISTINCT FROM NEW.platz) "
                f"EXECUTE FUNCTION {FUNKTION_LIVE}()")
    # Leser (nur Ansehen) melden sich trotzdem an (Anwesenheit, Protokoll)
    con.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {ANWESEND} TO "{sb.ROLLE_LESEN}"')
    con.execute(f'GRANT INSERT ON {PROTOKOLL} TO "{sb.ROLLE_LESEN}"')
    con.execute(f'GRANT USAGE ON SEQUENCE {PROTOKOLL}_id_seq TO "{sb.ROLLE_LESEN}"')


# ------------------------------------------------------------------------------------------------ Protokoll
def protokollieren(db, art, text="", objekt=""):
    s = _s(db)
    with contextlib.suppress(db_verbindung.DbFehler), db.con:
        db.con.execute(f"INSERT INTO {PROTOKOLL} (kuerzel, platz, art, objekt, text) VALUES (?, ?, ?, ?, ?)",
                       (s.kuerzel, s.platz, art, objekt or "", text or ""))


def protokoll(db, grenze=500):
    """Neueste Einträge zuerst: [dict(zeit, kuerzel, platz, art, objekt, text)]."""
    zeilen = db.con.execute(f"SELECT to_char(zeit AT TIME ZONE current_setting('TimeZone'), 'YYYY-MM-DD HH24:MI:SS'),"
                            f" kuerzel, platz, art, objekt, text FROM {PROTOKOLL} ORDER BY id DESC LIMIT ?",
                            (int(grenze),)).fetchall()
    return [dict(zip(("zeit", "kuerzel", "platz", "art", "objekt", "text"), z)) for z in zeilen]


# ------------------------------------------------------------------------------------------------ Anwesenheit
def puls(db, offen=None, zeilen=None, ende=False):
    """Eigene Anwesenheit melden und die eigenen Reservierungen verlängern. offen: {Nummer: seit} der hier
    bearbeiteten Angebote; zeilen: {"Tabelle|Kennung": Zeit} gerade geänderter Stammdatenzeilen; ende: Programm
    wird beendet (gleich „nicht mehr da“, alle Reservierungen frei). Ergebnis: Objekte der Reservierungen, die
    dieser Platz noch hält (eine fehlende hat ein Kollege übernommen)."""
    from . import VERSION
    s = _s(db)
    if db.con.in_transaction:           # nie mitten in eine laufende Änderung schreiben
        return None
    with db.con:
        db.con.execute(
            f"INSERT INTO {ANWESEND} (kuerzel, platz, name, version, seit, zeit, offen, zeilen, ende) "
            "VALUES (?, ?, ?, ?, now(), now(), ?, ?, ?) ON CONFLICT (kuerzel, platz) DO UPDATE SET "
            f"name = excluded.name, version = excluded.version, zeit = now(), offen = excluded.offen, "
            f"zeilen = excluded.zeilen, ende = excluded.ende, "
            f"seit = CASE WHEN {ANWESEND}.ende THEN now() ELSE {ANWESEND}.seit END",
            (s.kuerzel, s.platz, db.einstellung("benutzer_name") or "", VERSION,
             json.dumps(dict(offen or {}), ensure_ascii=False), json.dumps(dict(zeilen or {}), ensure_ascii=False),
             bool(ende)))
        if s.nur_lesen:
            return set()
        if ende:
            db.con.execute(f"DELETE FROM {SPERREN} WHERE kuerzel=? AND platz=?", (s.kuerzel, s.platz))
            return set()
        db.con.execute(f"UPDATE {SPERREN} SET zeit = now() WHERE kuerzel=? AND platz=?", (s.kuerzel, s.platz))
        return {r[0] for r in db.con.execute(f"SELECT objekt FROM {SPERREN} WHERE kuerzel=? AND platz=?",
                                             (s.kuerzel, s.platz))}


def anwesende(db):
    """{Kürzel: dict(name, rechner, version, zeit, offen, zeilen, ende, vor_s, online, plaetze)} wie
    teilen.lebenszeichen. Ist ein Kürzel an mehreren Plätzen angemeldet, zählt der frischeste Platz (offen und
    zeilen aller Plätze zusammen)."""
    zeilen = db.con.execute(
        f"SELECT kuerzel, platz, name, version, to_char(zeit AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS+00:00'), "
        f"offen, zeilen, ende, EXTRACT(EPOCH FROM now() - zeit) FROM {ANWESEND} ORDER BY zeit").fetchall()
    out = {}
    for k, platz, name, version, zeit, offen, zl, ende, vor in zeilen:
        vor = float(vor or 0)
        online = not ende and vor <= ONLINE_S
        d = out.get(k)
        e = dict(name=name or "", rechner=platz, version=version or "", zeit=zeit, ende=bool(ende), vor_s=vor,
                 online=online, offen=_json(offen), zeilen=_json(zl), plaetze=[platz] if online else [])
        if d is not None:           # früherer (älterer) Platz desselben Kürzels: Angaben zusammenlegen
            if d["online"]:
                e["offen"] = {**d["offen"], **e["offen"]} if online else d["offen"]
                e["zeilen"] = {**d["zeilen"], **e["zeilen"]} if online else d["zeilen"]
                e["plaetze"] = d["plaetze"] + e["plaetze"]
                if not online:
                    e.update(online=True, vor_s=d["vor_s"], rechner=d["rechner"], ende=False)
        out[k] = e
    return out


def _json(text):
    try:
        w = json.loads(text or "{}")
    except ValueError:
        return {}
    return w if isinstance(w, dict) else {}


def server_zeit_versatz(db):
    """Sekunden, um die die Serveruhr der eigenen Uhr voraus ist (für Zeiten in der Anwesenheit)."""
    import time
    r = db.con.execute("SELECT EXTRACT(EPOCH FROM now())").fetchone()
    return float(r[0]) - time.time()


# ------------------------------------------------------------------------------------------------ Reservierung
def objekt_angebot(angebot_id):
    return f"{ANGEBOT}{int(angebot_id)}"


def reservieren(db, objekt, titel=""):
    """Objekt (z. B. angebot:17) für diesen Arbeitsplatz reservieren. Ergebnis: None = reserviert (auch schon vorher),
    sonst der Inhaber dict(kuerzel, platz, seit, vor_s, titel). Eine Reservierung ohne Puls seit FRISCH_S Sekunden
    gilt als frei."""
    s = _s(db)
    if s.nur_lesen:
        return None
    with db.con:
        r = db.con.execute(
            f"INSERT INTO {SPERREN} (objekt, kuerzel, platz, titel, seit, zeit) VALUES (?, ?, ?, ?, now(), now()) "
            "ON CONFLICT (objekt) DO UPDATE SET kuerzel = excluded.kuerzel, platz = excluded.platz, "
            f"titel = excluded.titel, zeit = now(), seit = CASE WHEN {SPERREN}.kuerzel = excluded.kuerzel AND "
            f"{SPERREN}.platz = excluded.platz THEN {SPERREN}.seit ELSE now() END "
            f"WHERE ({SPERREN}.kuerzel = excluded.kuerzel AND {SPERREN}.platz = excluded.platz) "
            f"OR {SPERREN}.zeit < now() - make_interval(secs => ?) RETURNING kuerzel",
            (objekt, s.kuerzel, s.platz, str(titel or ""), FRISCH_S)).fetchone()
    if r is not None:
        return None
    return inhaber(db, objekt)


def inhaber(db, objekt):
    """Wer hält die Reservierung (frisch)? dict(kuerzel, platz, seit, vor_s, titel, ich) oder None."""
    r = db.con.execute(
        f"SELECT kuerzel, platz, to_char(seit, 'YYYY-MM-DD HH24:MI'), EXTRACT(EPOCH FROM now() - zeit), titel "
        f"FROM {SPERREN} WHERE objekt=? AND zeit >= now() - make_interval(secs => ?)", (objekt, FRISCH_S)).fetchone()
    if r is None:
        return None
    s = _s(db)
    return dict(kuerzel=r[0], platz=r[1], seit=r[2], vor_s=float(r[3] or 0), titel=r[4] or "",
                ich=r[0] == s.kuerzel and r[1] == s.platz)


def freigeben(db, objekt):
    """Eigene Reservierung aufheben (Angebot geschlossen)."""
    s = _s(db)
    if s.nur_lesen:
        return
    with contextlib.suppress(db_verbindung.DbFehler), db.con:
        db.con.execute(f"DELETE FROM {SPERREN} WHERE objekt=? AND kuerzel=? AND platz=?", (objekt, s.kuerzel, s.platz))


def uebernehmen(db, objekt, titel=""):
    """Reservierung eines Kollegen übernehmen (nach Rückfrage in der Oberfläche). Ergebnis: bisheriger Inhaber oder
    None. Der bisherige Platz verliert sie mit seinem nächsten Puls und zeigt das Angebot dann nur noch an."""
    s = _s(db)
    if s.nur_lesen:
        raise db_verbindung.NurLesen("Lesemodus – Übernehmen ist gesperrt.")
    vorher = inhaber(db, objekt)
    with db.con:
        db.con.execute(
            f"INSERT INTO {SPERREN} (objekt, kuerzel, platz, titel, seit, zeit) VALUES (?, ?, ?, ?, now(), now()) "
            "ON CONFLICT (objekt) DO UPDATE SET kuerzel = excluded.kuerzel, platz = excluded.platz, "
            "titel = excluded.titel, seit = now(), zeit = now()", (objekt, s.kuerzel, s.platz, str(titel or "")))
    if vorher and not vorher["ich"]:
        protokollieren(db, P_UEBERNOMMEN, f"{titel or objekt} von {vorher['kuerzel']} ({vorher['platz']}) übernommen",
                       objekt)
    return vorher if vorher and not vorher["ich"] else None


def reservierungen(db, ohne_eigene=True):
    """{Objekt: dict(kuerzel, platz, seit, titel)} aller frischen Reservierungen (ohne die dieses Platzes)."""
    s = _s(db)
    out = {}
    for objekt, k, platz, seit, titel in db.con.execute(
            f"SELECT objekt, kuerzel, platz, to_char(seit, 'YYYY-MM-DD HH24:MI'), titel FROM {SPERREN} "
            "WHERE zeit >= now() - make_interval(secs => ?)", (FRISCH_S,)):
        if ohne_eigene and k == s.kuerzel and platz == s.platz:
            continue
        out[objekt] = dict(kuerzel=k, platz=platz, seit=seit, titel=titel or "")
    return out


def angebote_in_bearbeitung(db):
    """{Angebots-ID: dict(kuerzel, platz, seit, titel)} der Angebote, die Kollegen gerade bearbeiten."""
    out = {}
    for objekt, d in reservierungen(db).items():
        if objekt.startswith(ANGEBOT):
            with contextlib.suppress(ValueError):
                out[int(objekt[len(ANGEBOT):])] = d
    return out


# ------------------------------------------------------------------------------------------------ Live (NOTIFY)
class Zuhoerer(threading.Thread):
    """Eigene Verbindung mit LISTEN auf KANAL; jede Meldung landet als (art, kennung) in meldungen. Meldungen der
    eigenen Hauptverbindung (gleiche Prozessnummer am Server) zählen nicht. Bricht die Verbindung ab, wird nach einer
    Pause neu verbunden (danach meldet er ('neu', '') – alles neu laden, was dazwischen kam, fehlt)."""

    def __init__(self, db):
        super().__init__(name="Server-Zuhoerer", daemon=True)
        v = db.con.v
        self._zugang, self._passwort = dict(v.zugang), v._passwort
        self._zugang.pop("rolle", None)         # LISTEN braucht keine Rechte an Tabellen
        self.meldungen = queue.SimpleQueue()
        self._stop = threading.Event()
        self.eigene_pid = None
        self.verbunden = threading.Event()
        self._db = db
        self.fehler = ""

    def eigene_pid_lesen(self):
        with contextlib.suppress(Exception):
            self.eigene_pid = str(self._db.con.execute("SELECT pg_backend_pid()").fetchone()[0])
        return self.eigene_pid

    def stoppen(self):
        self._stop.set()

    def run(self):
        pause = 1.0
        erstes = True
        while not self._stop.is_set():
            v = None
            try:
                v = db_verbindung.PostgresVerbindung(self._zugang, self._passwort, zeitlimit_ms=0)
                v.con.execute(f"LISTEN {KANAL}")
                self.verbunden.set()
                if not erstes:
                    self.meldungen.put(("neu", ""))
                erstes, pause = False, 1.0
                while not self._stop.is_set():
                    for n in v.con.notifies(timeout=1.0):
                        art, _, rest = n.payload.partition("|")
                        kennung, _, pid = rest.rpartition("|")
                        if pid != self.eigene_pid:
                            self.meldungen.put((art, kennung))
            except Exception as e:      # noqa: BLE001 - Netz weg, Server neu gestartet: gleich wieder versuchen
                self.fehler = str(e)
                self.verbunden.clear()
                self._stop.wait(pause)
                pause = min(pause * 2, 30.0)
            finally:
                if v is not None:
                    with contextlib.suppress(Exception):
                        v.schliessen()

    def abholen(self):
        """Alle bisher eingegangenen Meldungen: dict(angebote={ids}, sperren={objekte}, neu=bool)."""
        out = dict(angebote=set(), sperren=set(), neu=False)
        while True:
            try:
                art, kennung = self.meldungen.get_nowait()
            except queue.Empty:
                return out
            if art == "a":
                with contextlib.suppress(ValueError):
                    out["angebote"].add(int(kennung))
            elif art == "r":
                out["sperren"].add(kennung)
            elif art == "neu":
                out["neu"] = True


# ------------------------------------------------------------------------------------------------ Benutzer
@contextlib.contextmanager
def _als_verwalter(db):
    """Rohe Verbindung kurz als rohrlaser_verwalter (für die Serverfunktion), danach wieder als Programmrolle."""
    s = _s(db)
    if not s.verwalter:
        raise sb.ServerFehler("Benutzer am Server anlegen oder ändern darf nur ein Verwalter (Administrator).")
    if db.con.in_transaction:
        db.con.commit()
    roh = db.con.v.con
    roh.execute(f'SET ROLE "{sb.ROLLE_VERWALTER}"')
    try:
        yield roh
    finally:
        roh.execute(f'SET ROLE "{s.rolle}"')


def _pflegen(db, kuerzel, passwort=None, recht=sb.RECHT_BEARBEITEN, name=None, aktiv_=True, entfernen=False):
    import psycopg
    try:
        with _als_verwalter(db) as roh:
            roh.execute(f"SELECT public.{FUNKTION_BENUTZER}(%s, %s, %s, %s, %s, %s)",
                        (str(kuerzel), passwort, recht, name, bool(aktiv_), bool(entfernen)))
    except psycopg.Error as e:
        text = (getattr(getattr(e, "diag", None), "message_primary", None) or str(e)).splitlines()[0]
        raise sb.ServerFehler(text) from e


def recht_aus_rollen(db, kuerzel, rollen_=None):
    """Recht am Server aus den Programmrollen: Administrator → Verwalter; eine Rolle mit „bearbeiten“ irgendwo →
    bearbeiten; sonst nur lesen. Ohne Rollen: bearbeiten, solange niemand Rollen hat (wie im Programm)."""
    from . import rollen
    if rollen_ is None:
        rollen_ = (rollen.benutzer(db).get(kuerzel) or {}).get("rollen") or []
    if rollen.ADMIN in rollen_:
        return sb.RECHT_VERWALTER
    if not rollen_:
        return sb.RECHT_BEARBEITEN if not rollen.aktiv(db) else sb.RECHT_LESEN
    rechte = rollen.rechte(db)
    if any(rollen._RANG.get(st, 0) >= rollen._RANG[rollen.BEARBEITEN]
           for r in rollen_ for st in (rechte.get(r) or {}).values()):
        return sb.RECHT_BEARBEITEN
    return sb.RECHT_LESEN


def benutzer_server(db, kuerzel, name=None, rollen_=None, aktiv_=True, passwort=None):
    """Programm-Benutzer am Server anlegen/ändern (Login, Recht, Name, gesperrt, Passwort). Ergebnis: Fehlertext
    oder ''."""
    try:
        recht = recht_aus_rollen(db, kuerzel, rollen_)
        _pflegen(db, kuerzel, passwort, recht, name, aktiv_)
    except sb.ServerFehler as e:
        return str(e)
    teile = [f"{kuerzel}: {recht}"]
    if not aktiv_:
        teile.append("gesperrt")
    if passwort:
        teile.append("Passwort neu")
    protokollieren(db, P_BENUTZER, ", ".join(teile), kuerzel)
    return ""


def benutzer_entfernen(db, kuerzel):
    try:
        _pflegen(db, kuerzel, None, sb.RECHT_LESEN, None, False, entfernen=True)
    except sb.ServerFehler as e:
        return str(e)
    protokollieren(db, P_BENUTZER, f"{kuerzel} entfernt", kuerzel)
    return ""


def benutzer_liste(db):
    """Logins am Server wie server_betrieb.benutzer_liste (über die Programmverbindung)."""
    return sb.benutzer_liste(db.con.v.con)
