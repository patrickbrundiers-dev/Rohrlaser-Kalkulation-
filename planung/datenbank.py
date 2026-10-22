"""Planungsdatenbank (SQLite im WAL-Modus auf dem Server-Rechner).

Nur der Planungsserver öffnet die Datei, und alle Zugriffe laufen nacheinander über eine Sperre: es gibt genau einen
Schreiber, deshalb ist SQLite hier sicher (die Arbeitsplätze greifen nie direkt auf die Datei zu).

Tabellen: maschinen, schichten, ausnahmen, stillstaende (Maschinenkalender), auftraege, belegungen (ein Auftrag auf
einer Maschine ab einem Beginn mit einer Dauer; das Ende wird immer aus dem aktuellen Kalender gerechnet und nicht
gespeichert), aenderungen (Historie, wird nur ergänzt), benutzer, einstellungen.

Konflikte: Aufträge, Belegungen und Maschinen tragen eine Versionsnummer. Gespeichert wird nur, wenn die Version
noch die gelesene ist; sonst KonfliktFehler mit dem aktuellen Stand und der letzten Änderung (wer, wann). Jede
Änderung an den Belegungen einer Maschine erhöht deren Version, so erkennt eine Vorschau, dass ein anderer
Benutzer auf derselben Maschine geplant hat.
"""
import datetime
import hashlib
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from . import kalender

SCHEMA_VERSION = 1
MASCHINEN = (("T03", "Trumpf CO₂-Laser"), ("T11", "Trumpf Faserlaser"), ("LT7", "Adige Faserlaser"))
ROLLEN = ("lesen", "planen", "verwalten")
STATUS = ("offen", "in Arbeit", "fertig", "storniert")
MASCHINEN_STATUS = ("verfügbar", "eingeschränkt", "außer Betrieb")
AUSNAHME_ARTEN = ("frei", "zusatz")
STILLSTAND_ARTEN = ("Wartung", "Störung", "Umbau", "Sonstiges")
SICHERUNGEN_BEHALTEN = 30
# Vorgabe, bis Patrick die Schwelle festlegt (Bericht, offene Frage 7); in den Einstellungen änderbar
EINSTELLUNGEN = {"termin_schwelle_tage": "2"}

AUFTRAG_FELDER = ("auftragsnummer", "angebot_nummer", "kunde", "bezeichnung", "profil", "werkstoff", "stueck",
                  "maschinenzeit_min", "ruestzeit_min", "zeitquelle", "liefertermin", "prioritaet", "status",
                  "maschinen_erlaubt", "bemerkung")
ZEITQUELLEN = ("manuell", "Kalkulation", "Excel-Import")

SCHEMA = """
CREATE TABLE IF NOT EXISTS einstellungen (name TEXT PRIMARY KEY, wert TEXT);
CREATE TABLE IF NOT EXISTS maschinen (id TEXT PRIMARY KEY, bezeichnung TEXT, status TEXT NOT NULL DEFAULT 'verfügbar',
    bemerkung TEXT, version INTEGER NOT NULL DEFAULT 1, geaendert_von TEXT, geaendert_am TEXT);
CREATE TABLE IF NOT EXISTS schichten (id INTEGER PRIMARY KEY, maschine TEXT NOT NULL REFERENCES maschinen(id),
    wochentag INTEGER NOT NULL CHECK (wochentag BETWEEN 0 AND 6), beginn TEXT NOT NULL, ende TEXT NOT NULL,
    gueltig_ab TEXT, gueltig_bis TEXT);
CREATE TABLE IF NOT EXISTS ausnahmen (id INTEGER PRIMARY KEY, datum TEXT NOT NULL, maschine TEXT REFERENCES maschinen(id),
    art TEXT NOT NULL CHECK (art IN ('frei', 'zusatz')), beginn TEXT, ende TEXT, bezeichnung TEXT);
CREATE TABLE IF NOT EXISTS stillstaende (id INTEGER PRIMARY KEY, maschine TEXT NOT NULL REFERENCES maschinen(id),
    beginn TEXT NOT NULL, ende TEXT NOT NULL, art TEXT, geplant INTEGER NOT NULL DEFAULT 1, bemerkung TEXT);
CREATE TABLE IF NOT EXISTS auftraege (id INTEGER PRIMARY KEY, auftragsnummer TEXT NOT NULL UNIQUE, angebot_nummer TEXT,
    kunde TEXT, bezeichnung TEXT, profil TEXT, werkstoff TEXT, stueck REAL, maschinenzeit_min REAL, ruestzeit_min REAL,
    zeitquelle TEXT, liefertermin TEXT, prioritaet INTEGER, status TEXT NOT NULL DEFAULT 'offen',
    maschinen_erlaubt TEXT, bemerkung TEXT, version INTEGER NOT NULL DEFAULT 1,
    angelegt_von TEXT, angelegt_am TEXT, geaendert_von TEXT, geaendert_am TEXT);
CREATE TABLE IF NOT EXISTS belegungen (id INTEGER PRIMARY KEY,
    auftrag_id INTEGER NOT NULL UNIQUE REFERENCES auftraege(id) ON DELETE CASCADE,
    maschine TEXT NOT NULL REFERENCES maschinen(id), beginn TEXT NOT NULL, dauer_min REAL, fixiert INTEGER NOT NULL DEFAULT 0,
    ist_beginn TEXT, ist_ende TEXT, version INTEGER NOT NULL DEFAULT 1, geaendert_von TEXT, geaendert_am TEXT);
CREATE TABLE IF NOT EXISTS aenderungen (id INTEGER PRIMARY KEY, zeit TEXT NOT NULL, benutzer TEXT, objekt TEXT NOT NULL,
    objekt_id TEXT, aktion TEXT NOT NULL, alt TEXT, neu TEXT, grund TEXT);
CREATE INDEX IF NOT EXISTS aenderungen_objekt ON aenderungen (objekt, objekt_id);
CREATE TABLE IF NOT EXISTS benutzer (name TEXT PRIMARY KEY, anzeige TEXT, rolle TEXT NOT NULL, salz TEXT NOT NULL,
    hash TEXT NOT NULL, aktiv INTEGER NOT NULL DEFAULT 1);
"""


class Fehler(ValueError):
    """Eingabe oder Planung unzulässig; der Text ist für den Benutzer."""


class KonfliktFehler(Fehler):
    """Ein anderer Benutzer hat inzwischen gespeichert. aktuell = aktueller Stand, letzte = letzte Änderung."""

    def __init__(self, text, aktuell=None, letzte=None):
        super().__init__(text)
        self.aktuell, self.letzte = aktuell, letzte


def jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _zahl(v, name, ganz=False, mindest=None):
    if v is None or v == "":
        return None
    try:
        z = float(str(v).replace(",", "."))
    except ValueError:
        raise Fehler(f"{name}: '{v}' ist keine Zahl") from None
    if mindest is not None and z < mindest:
        raise Fehler(f"{name}: mindestens {mindest:g}")
    return int(z) if ganz else z


def passwort_hash(passwort, salz):
    return hashlib.scrypt(passwort.encode("utf-8"), salt=bytes.fromhex(salz), n=2 ** 14, r=8, p=1).hex()


class Planungsdatenbank:
    def __init__(self, pfad):
        self.pfad = Path(pfad)
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.pfad, check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.sperre = threading.RLock()
        with self.sperre:
            self.con.execute("PRAGMA journal_mode=WAL")
            self.con.execute("PRAGMA foreign_keys=ON")
            self.con.execute("PRAGMA busy_timeout=5000")
            version = self.con.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise Fehler(f"Die Planungsdatei hat Schema {version}, dieses Programm kennt nur {SCHEMA_VERSION}. "
                             "Bitte das Programm aktualisieren.")
            self.con.executescript(SCHEMA)
            for mid, name in MASCHINEN:
                self.con.execute("INSERT OR IGNORE INTO maschinen (id, bezeichnung) VALUES (?, ?)", (mid, name))
            for n, w in EINSTELLUNGEN.items():
                self.con.execute("INSERT OR IGNORE INTO einstellungen VALUES (?, ?)", (n, w))
            self.con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def schliessen(self):
        with self.sperre:
            self.con.close()

    @contextmanager
    def transaktion(self):
        """Alles oder nichts: BEGIN IMMEDIATE … COMMIT, bei einer Ausnahme ROLLBACK."""
        with self.sperre:
            self.con.execute("BEGIN IMMEDIATE")
            try:
                yield self.con
            except BaseException:
                self.con.execute("ROLLBACK")
                raise
            self.con.execute("COMMIT")

    def _alle(self, sql, *args):
        with self.sperre:
            return [dict(z) for z in self.con.execute(sql, args)]

    def _eine(self, sql, *args):
        with self.sperre:
            z = self.con.execute(sql, args).fetchone()
            return dict(z) if z else None

    # ------------------------------------------------------------------ Historie
    def _historie(self, con, benutzer, objekt, objekt_id, aktion, alt=None, neu=None, grund=None):
        con.execute("INSERT INTO aenderungen (zeit, benutzer, objekt, objekt_id, aktion, alt, neu, grund) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (jetzt(), benutzer, objekt, str(objekt_id), aktion,
                     json.dumps(alt, ensure_ascii=False) if alt is not None else None,
                     json.dumps(neu, ensure_ascii=False) if neu is not None else None, grund or None))

    def historie(self, objekt=None, objekt_id=None, anzahl=200):
        sql, args = "SELECT * FROM aenderungen", []
        if objekt:
            sql += " WHERE objekt = ?" + (" AND objekt_id = ?" if objekt_id is not None else "")
            args = [objekt] + ([str(objekt_id)] if objekt_id is not None else [])
        zeilen = self._alle(sql + " ORDER BY id DESC LIMIT ?", *args, anzahl)
        for z in zeilen:
            z["alt"] = json.loads(z["alt"]) if z["alt"] else None
            z["neu"] = json.loads(z["neu"]) if z["neu"] else None
        return zeilen

    def letzte_aenderung(self, objekt, objekt_id):
        return self._eine("SELECT zeit, benutzer, aktion, grund FROM aenderungen WHERE objekt = ? AND objekt_id = ? "
                          "ORDER BY id DESC LIMIT 1", objekt, str(objekt_id))

    # ------------------------------------------------------------------ Einstellungen
    def einstellungen(self):
        return {z["name"]: z["wert"] for z in self._alle("SELECT * FROM einstellungen")}

    def einstellung_setzen(self, name, wert, benutzer):
        if name not in EINSTELLUNGEN:
            raise Fehler(f"Unbekannte Einstellung: {name}")
        if name == "termin_schwelle_tage":
            wert = str(_zahl(wert, "Schwelle Terminrisiko", ganz=True, mindest=0))
        with self.transaktion() as con:
            alt = self.einstellungen().get(name)
            con.execute("INSERT OR REPLACE INTO einstellungen VALUES (?, ?)", (name, wert))
            self._historie(con, benutzer, "einstellung", name, "geändert", alt, wert)

    # ------------------------------------------------------------------ Benutzer
    def benutzer_anzahl(self):
        return self._eine("SELECT COUNT(*) AS n FROM benutzer")["n"]

    def benutzer_liste(self):
        return self._alle("SELECT name, anzeige, rolle, aktiv FROM benutzer ORDER BY name")

    def benutzer_anlegen(self, name, passwort, rolle, anzeige=None, von=None):
        name = (name or "").strip().lower()
        if not name or len(passwort or "") < 8 or rolle not in ROLLEN:
            raise Fehler("Name, Passwort (mindestens 8 Zeichen) und Rolle (lesen, planen, verwalten) angeben")
        salz = secrets.token_hex(16)
        with self.transaktion() as con:
            if con.execute("SELECT 1 FROM benutzer WHERE name = ?", (name,)).fetchone():
                raise Fehler(f"Benutzer {name} gibt es schon")
            con.execute("INSERT INTO benutzer (name, anzeige, rolle, salz, hash) VALUES (?, ?, ?, ?, ?)",
                        (name, anzeige or name, rolle, salz, passwort_hash(passwort, salz)))
            self._historie(con, von or name, "benutzer", name, "angelegt", None, dict(rolle=rolle))

    def benutzer_aendern(self, name, von, rolle=None, aktiv=None, passwort=None):
        with self.transaktion() as con:
            alt = con.execute("SELECT name, rolle, aktiv FROM benutzer WHERE name = ?", (name,)).fetchone()
            if not alt:
                raise Fehler(f"Benutzer {name} gibt es nicht")
            alt = dict(alt)
            if rolle is not None:
                if rolle not in ROLLEN:
                    raise Fehler("Rolle muss lesen, planen oder verwalten sein")
                con.execute("UPDATE benutzer SET rolle = ? WHERE name = ?", (rolle, name))
            if aktiv is not None:
                con.execute("UPDATE benutzer SET aktiv = ? WHERE name = ?", (1 if aktiv else 0, name))
            if passwort:
                if len(passwort) < 8:
                    raise Fehler("Passwort: mindestens 8 Zeichen")
                salz = secrets.token_hex(16)
                con.execute("UPDATE benutzer SET salz = ?, hash = ? WHERE name = ?",
                            (salz, passwort_hash(passwort, salz), name))
            if (con.execute("SELECT COUNT(*) FROM benutzer WHERE rolle = 'verwalten' AND aktiv = 1").fetchone()[0]
                    == 0):
                raise Fehler("Mindestens ein aktiver Benutzer muss die Rolle 'verwalten' behalten")
            self._historie(con, von, "benutzer", name, "geändert", alt,
                           dict(rolle=rolle, aktiv=aktiv, passwort="neu" if passwort else None))

    def anmelden(self, name, passwort):
        """Benutzer-dict (name, anzeige, rolle) oder None."""
        z = self._eine("SELECT * FROM benutzer WHERE name = ? AND aktiv = 1", (name or "").strip().lower())
        if not z or not secrets.compare_digest(passwort_hash(passwort or "", z["salz"]), z["hash"]):
            return None
        return dict(name=z["name"], anzeige=z["anzeige"], rolle=z["rolle"])

    # ------------------------------------------------------------------ Maschinen und Kalender
    def maschinen(self):
        return self._alle("SELECT * FROM maschinen ORDER BY CASE id WHEN 'T03' THEN 1 WHEN 'T11' THEN 2 "
                          "WHEN 'LT7' THEN 3 ELSE 4 END, id")

    def maschine_aendern(self, mid, daten, version, benutzer):
        with self.transaktion() as con:
            alt = self._maschine_pruefen(con, mid, version)
            status = daten.get("status", alt["status"])
            if status not in MASCHINEN_STATUS:
                raise Fehler(f"Status muss {', '.join(MASCHINEN_STATUS)} sein")
            neu = dict(bezeichnung=daten.get("bezeichnung", alt["bezeichnung"]), status=status,
                       bemerkung=daten.get("bemerkung", alt["bemerkung"]))
            con.execute("UPDATE maschinen SET bezeichnung = ?, status = ?, bemerkung = ?, version = version + 1, "
                        "geaendert_von = ?, geaendert_am = ? WHERE id = ?",
                        (neu["bezeichnung"], neu["status"], neu["bemerkung"], benutzer, jetzt(), mid))
            self._historie(con, benutzer, "maschine", mid, "geändert",
                           {k: alt[k] for k in neu}, neu)

    def _maschine_pruefen(self, con, mid, version=None):
        m = con.execute("SELECT * FROM maschinen WHERE id = ?", (mid,)).fetchone()
        if not m:
            raise Fehler(f"Unbekannte Maschine: {mid}")
        m = dict(m)
        if version is not None and int(version) != m["version"]:
            raise KonfliktFehler(f"Die Planung von {mid} wurde inzwischen von {m['geaendert_von'] or 'jemand anderem'} "
                                 f"geändert ({m['geaendert_am']}). Bitte neu laden und erneut prüfen.",
                                 m, dict(benutzer=m["geaendert_von"], zeit=m["geaendert_am"]))
        return m

    def _maschine_hochzaehlen(self, con, mid, benutzer):
        con.execute("UPDATE maschinen SET version = version + 1, geaendert_von = ?, geaendert_am = ? WHERE id = ?",
                    (benutzer, jetzt(), mid))

    def kalender(self):
        """{schichten, ausnahmen, stillstaende} für kalender.verfuegbare_fenster."""
        return dict(schichten=self._alle("SELECT * FROM schichten ORDER BY maschine, wochentag, beginn"),
                    ausnahmen=self._alle("SELECT * FROM ausnahmen ORDER BY datum"),
                    stillstaende=self._alle("SELECT * FROM stillstaende ORDER BY beginn"))

    def schichten_setzen(self, mid, schichten, benutzer):
        """Ersetzt das Schichtmodell der Maschine: [{wochentag, beginn, ende, gueltig_ab?, gueltig_bis?}]."""
        neu = []
        for s in schichten:
            try:
                wt = int(s["wochentag"])
                kalender.uhrzeit(s["beginn"])
                kalender.uhrzeit(s["ende"])
                for f in ("gueltig_ab", "gueltig_bis"):
                    kalender.datum(s.get(f))
            except (KeyError, ValueError, TypeError):
                raise Fehler(f"Ungültige Schicht: {s}") from None
            if not 0 <= wt <= 6 or s["beginn"] == s["ende"]:
                raise Fehler(f"Ungültige Schicht: {s}")
            neu.append((mid, wt, s["beginn"], s["ende"], s.get("gueltig_ab") or None, s.get("gueltig_bis") or None))
        with self.transaktion() as con:
            self._maschine_pruefen(con, mid)
            alt = [dict(z) for z in con.execute("SELECT wochentag, beginn, ende, gueltig_ab, gueltig_bis FROM schichten "
                                                "WHERE maschine = ? ORDER BY wochentag, beginn", (mid,))]
            con.execute("DELETE FROM schichten WHERE maschine = ?", (mid,))
            con.executemany("INSERT INTO schichten (maschine, wochentag, beginn, ende, gueltig_ab, gueltig_bis) "
                            "VALUES (?, ?, ?, ?, ?, ?)", neu)
            self._maschine_hochzaehlen(con, mid, benutzer)
            self._historie(con, benutzer, "schichten", mid, "ersetzt", alt, schichten)

    def ausnahme_anlegen(self, daten, benutzer):
        art = daten.get("art")
        if art not in AUSNAHME_ARTEN:
            raise Fehler("Art muss 'frei' (Feiertag, Betriebsruhe) oder 'zusatz' (Zusatzschicht) sein")
        try:
            tag = kalender.datum(daten.get("datum"))
            if art == "zusatz":
                kalender.uhrzeit(daten["beginn"])
                kalender.uhrzeit(daten["ende"])
        except (KeyError, ValueError, TypeError):
            raise Fehler("Datum (und bei Zusatzschicht Beginn und Ende) angeben") from None
        if tag is None:
            raise Fehler("Datum angeben")
        mid = daten.get("maschine") or None
        with self.transaktion() as con:
            if mid:
                self._maschine_pruefen(con, mid)
            cur = con.execute("INSERT INTO ausnahmen (datum, maschine, art, beginn, ende, bezeichnung) "
                              "VALUES (?, ?, ?, ?, ?, ?)",
                              (tag.isoformat(), mid, art, daten.get("beginn") if art == "zusatz" else None,
                               daten.get("ende") if art == "zusatz" else None, daten.get("bezeichnung")))
            for m in ([mid] if mid else [m[0] for m in con.execute("SELECT id FROM maschinen")]):
                self._maschine_hochzaehlen(con, m, benutzer)
            self._historie(con, benutzer, "ausnahme", cur.lastrowid, "angelegt", None, daten)
            return cur.lastrowid

    def feiertage_eintragen(self, jahr, benutzer):
        """Bundesweite Feiertage des Jahres als 'frei' für alle Maschinen; vorhandene Tage bleiben unverändert."""
        vorhanden = {z["datum"] for z in self._alle("SELECT datum FROM ausnahmen WHERE art = 'frei' AND maschine IS NULL")}
        n = 0
        for tag, name in kalender.bundesweite_feiertage(int(jahr)):
            if tag.isoformat() not in vorhanden:
                self.ausnahme_anlegen(dict(datum=tag.isoformat(), art="frei", bezeichnung=name), benutzer)
                n += 1
        return n

    def ausnahme_loeschen(self, aid, benutzer):
        with self.transaktion() as con:
            alt = con.execute("SELECT * FROM ausnahmen WHERE id = ?", (aid,)).fetchone()
            if not alt:
                raise Fehler("Ausnahme nicht gefunden")
            con.execute("DELETE FROM ausnahmen WHERE id = ?", (aid,))
            for m in ([alt["maschine"]] if alt["maschine"] else [m[0] for m in con.execute("SELECT id FROM maschinen")]):
                self._maschine_hochzaehlen(con, m, benutzer)
            self._historie(con, benutzer, "ausnahme", aid, "gelöscht", dict(alt))

    def stillstand_anlegen(self, daten, benutzer):
        mid = daten.get("maschine")
        try:
            b, e = kalender.zeit(daten["beginn"]), kalender.zeit(daten["ende"])
        except (KeyError, ValueError, TypeError):
            raise Fehler("Beginn und Ende des Stillstands angeben (Datum und Uhrzeit)") from None
        if not b or not e or e <= b:
            raise Fehler("Das Ende des Stillstands muss nach dem Beginn liegen")
        with self.transaktion() as con:
            self._maschine_pruefen(con, mid)
            cur = con.execute("INSERT INTO stillstaende (maschine, beginn, ende, art, geplant, bemerkung) "
                              "VALUES (?, ?, ?, ?, ?, ?)",
                              (mid, kalender.zeit_text(b), kalender.zeit_text(e), daten.get("art") or "Wartung",
                               0 if daten.get("geplant") in (False, 0, "0", "nein") else 1, daten.get("bemerkung")))
            self._maschine_hochzaehlen(con, mid, benutzer)
            self._historie(con, benutzer, "stillstand", cur.lastrowid, "angelegt", None, daten)
            return cur.lastrowid

    def stillstand_loeschen(self, sid, benutzer):
        with self.transaktion() as con:
            alt = con.execute("SELECT * FROM stillstaende WHERE id = ?", (sid,)).fetchone()
            if not alt:
                raise Fehler("Stillstand nicht gefunden")
            con.execute("DELETE FROM stillstaende WHERE id = ?", (sid,))
            self._maschine_hochzaehlen(con, alt["maschine"], benutzer)
            self._historie(con, benutzer, "stillstand", sid, "gelöscht", dict(alt))

    # ------------------------------------------------------------------ Aufträge
    def auftraege(self):
        return self._alle("SELECT a.*, b.id AS belegung_id FROM auftraege a LEFT JOIN belegungen b "
                          "ON b.auftrag_id = a.id ORDER BY a.liefertermin IS NULL, a.liefertermin, a.auftragsnummer")

    def auftrag(self, aid):
        return self._eine("SELECT * FROM auftraege WHERE id = ?", aid)

    def _auftrag_werte(self, daten, alt=None):
        w = dict(alt or {})
        for f in AUFTRAG_FELDER:
            if f in daten:
                w[f] = daten[f] if daten[f] != "" else None
        w["auftragsnummer"] = (w.get("auftragsnummer") or "").strip()
        if not w["auftragsnummer"]:
            raise Fehler("Auftragsnummer angeben")
        w["stueck"] = _zahl(w.get("stueck"), "Stückzahl", mindest=0)
        w["maschinenzeit_min"] = _zahl(w.get("maschinenzeit_min"), "Maschinenzeit", mindest=0)
        w["ruestzeit_min"] = _zahl(w.get("ruestzeit_min"), "Rüstzeit", mindest=0)
        w["prioritaet"] = _zahl(w.get("prioritaet"), "Priorität", ganz=True)
        w["status"] = w.get("status") or "offen"
        if w["status"] not in STATUS:
            raise Fehler(f"Status muss {', '.join(STATUS)} sein")
        w["zeitquelle"] = w.get("zeitquelle") or "manuell"
        if w["zeitquelle"] not in ZEITQUELLEN:
            raise Fehler(f"Zeitquelle muss {', '.join(ZEITQUELLEN)} sein")
        if w.get("liefertermin"):
            try:
                w["liefertermin"] = kalender.datum(w["liefertermin"]).isoformat()
            except ValueError:
                raise Fehler(f"Liefertermin '{w['liefertermin']}' ist kein gültiges Datum") from None
        erlaubt = [m.strip().upper() for m in str(w.get("maschinen_erlaubt") or "").replace(";", ",").split(",")
                   if m.strip()]
        bekannt = {m["id"] for m in self.maschinen()}
        if set(erlaubt) - bekannt:
            raise Fehler(f"Unbekannte Maschine in 'Maschinen erlaubt': {', '.join(sorted(set(erlaubt) - bekannt))}")
        w["maschinen_erlaubt"] = ",".join(erlaubt) or None
        return w

    def auftrag_speichern(self, daten, benutzer, version=None, aid=None):
        """Neuer Auftrag (aid None) oder Änderung mit Versionsprüfung. Ergebnis: id."""
        with self.transaktion() as con:
            if aid is None:
                w = self._auftrag_werte(daten)
                if con.execute("SELECT 1 FROM auftraege WHERE auftragsnummer = ?", (w["auftragsnummer"],)).fetchone():
                    raise Fehler(f"Auftrag {w['auftragsnummer']} gibt es schon")
                felder = AUFTRAG_FELDER + ("angelegt_von", "angelegt_am", "geaendert_von", "geaendert_am")
                t = jetzt()
                werte = [w.get(f) for f in AUFTRAG_FELDER] + [benutzer, t, benutzer, t]
                cur = con.execute(f"INSERT INTO auftraege ({', '.join(felder)}) VALUES ({', '.join('?' * len(felder))})",
                                  werte)
                self._historie(con, benutzer, "auftrag", cur.lastrowid, "angelegt", None,
                               {f: w.get(f) for f in AUFTRAG_FELDER})
                return cur.lastrowid
            alt = con.execute("SELECT * FROM auftraege WHERE id = ?", (aid,)).fetchone()
            if not alt:
                raise Fehler("Auftrag nicht gefunden")
            alt = dict(alt)
            if version is None or int(version) != alt["version"]:
                raise KonfliktFehler(f"Auftrag {alt['auftragsnummer']} wurde inzwischen von "
                                     f"{alt['geaendert_von'] or 'jemand anderem'} geändert ({alt['geaendert_am']}).",
                                     alt, self.letzte_aenderung("auftrag", aid))
            w = self._auftrag_werte(daten, {f: alt[f] for f in AUFTRAG_FELDER})
            if w["auftragsnummer"] != alt["auftragsnummer"] and con.execute(
                    "SELECT 1 FROM auftraege WHERE auftragsnummer = ? AND id != ?", (w["auftragsnummer"], aid)).fetchone():
                raise Fehler(f"Auftrag {w['auftragsnummer']} gibt es schon")
            geaendert = {f: w[f] for f in AUFTRAG_FELDER if w[f] != alt[f]}
            if not geaendert:
                return aid
            con.execute(f"UPDATE auftraege SET {', '.join(f + ' = ?' for f in geaendert)}, version = version + 1, "
                        "geaendert_von = ?, geaendert_am = ? WHERE id = ?",
                        [*geaendert.values(), benutzer, jetzt(), aid])
            b = con.execute("SELECT maschine FROM belegungen WHERE auftrag_id = ?", (aid,)).fetchone()
            if b:              # Dauer oder Termin der Belegung ändern sich mit
                self._maschine_hochzaehlen(con, b[0], benutzer)
            self._historie(con, benutzer, "auftrag", aid, "geändert", {f: alt[f] for f in geaendert}, geaendert,
                           daten.get("grund"))
            return aid

    def auftrag_loeschen(self, aid, version, benutzer):
        with self.transaktion() as con:
            alt = con.execute("SELECT * FROM auftraege WHERE id = ?", (aid,)).fetchone()
            if not alt:
                raise Fehler("Auftrag nicht gefunden")
            if int(version) != alt["version"]:
                raise KonfliktFehler(f"Auftrag {alt['auftragsnummer']} wurde inzwischen geändert.", dict(alt),
                                     self.letzte_aenderung("auftrag", aid))
            b = con.execute("SELECT maschine FROM belegungen WHERE auftrag_id = ?", (aid,)).fetchone()
            con.execute("DELETE FROM auftraege WHERE id = ?", (aid,))
            if b:
                self._maschine_hochzaehlen(con, b[0], benutzer)
            self._historie(con, benutzer, "auftrag", aid, "gelöscht", dict(alt))

    # ------------------------------------------------------------------ Belegungen
    def belegungen(self):
        return self._alle("SELECT b.*, a.auftragsnummer, a.kunde, a.bezeichnung, a.liefertermin, a.prioritaet, "
                          "a.status, a.maschinenzeit_min, a.ruestzeit_min, a.zeitquelle, a.maschinen_erlaubt "
                          "FROM belegungen b JOIN auftraege a ON a.id = b.auftrag_id ORDER BY b.maschine, b.beginn")

    def belegungen_schreiben(self, schritte, maschinen_versionen, benutzer, grund=None):
        """Mehrere Belegungsänderungen in einer Transaktion (Plantafel: verschieben samt Nachrücken).
        schritte: [{aktion: 'neu' | 'ändern' | 'entfernen', id?, version?, auftrag_id?, maschine, beginn, dauer_min?,
        fixiert?, ist_beginn?, ist_ende?}]; maschinen_versionen: {Maschine: Version beim Lesen} für jede betroffene
        Maschine. Weicht eine Version ab, wird nichts gespeichert (KonfliktFehler)."""
        with self.transaktion() as con:
            betroffen = set(maschinen_versionen)
            for s in schritte:
                betroffen.add(s.get("maschine"))
                if s.get("id"):
                    z = con.execute("SELECT maschine FROM belegungen WHERE id = ?", (s["id"],)).fetchone()
                    if z:
                        betroffen.add(z[0])
            betroffen.discard(None)
            for m in betroffen:
                if m not in maschinen_versionen:
                    raise Fehler(f"Version der Maschine {m} fehlt")
                self._maschine_pruefen(con, m, maschinen_versionen[m])
            for s in schritte:
                self._schritt(con, s, benutzer, grund)
            for m in betroffen:
                self._maschine_hochzaehlen(con, m, benutzer)

    def _schritt(self, con, s, benutzer, grund):
        aktion = s.get("aktion")
        if aktion == "neu":
            a = con.execute("SELECT id, auftragsnummer FROM auftraege WHERE id = ?", (s.get("auftrag_id"),)).fetchone()
            if not a:
                raise Fehler("Auftrag nicht gefunden")
            if con.execute("SELECT 1 FROM belegungen WHERE auftrag_id = ?", (a[0],)).fetchone():
                raise KonfliktFehler(f"Auftrag {a[1]} wurde inzwischen schon eingeplant.")
            w = self._belegung_werte(con, s)
            cur = con.execute("INSERT INTO belegungen (auftrag_id, maschine, beginn, dauer_min, fixiert, ist_beginn, "
                              "ist_ende, geaendert_von, geaendert_am) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (a[0], w["maschine"], w["beginn"], w["dauer_min"], w["fixiert"], w["ist_beginn"],
                               w["ist_ende"], benutzer, jetzt()))
            self._historie(con, benutzer, "belegung", cur.lastrowid, "eingeplant", None,
                           dict(w, auftrag=a[1]), grund)
            return
        alt = con.execute("SELECT b.*, a.auftragsnummer FROM belegungen b JOIN auftraege a ON a.id = b.auftrag_id "
                          "WHERE b.id = ?", (s.get("id"),)).fetchone()
        if not alt:
            raise KonfliktFehler("Die Belegung gibt es nicht mehr (inzwischen entfernt).")
        alt = dict(alt)
        if s.get("version") is None or int(s["version"]) != alt["version"]:
            raise KonfliktFehler(f"Die Belegung von Auftrag {alt['auftragsnummer']} wurde inzwischen von "
                                 f"{alt['geaendert_von'] or 'jemand anderem'} geändert ({alt['geaendert_am']}).",
                                 alt, self.letzte_aenderung("belegung", alt["id"]))
        if aktion == "entfernen":
            con.execute("DELETE FROM belegungen WHERE id = ?", (alt["id"],))
            self._historie(con, benutzer, "belegung", alt["id"], "ausgeplant", alt, None, grund)
            return
        if aktion != "ändern":
            raise Fehler(f"Unbekannte Aktion: {aktion}")
        w = self._belegung_werte(con, dict({k: alt[k] for k in ("maschine", "beginn", "dauer_min", "fixiert",
                                                                 "ist_beginn", "ist_ende")}, **s))
        geaendert = {k: v for k, v in w.items() if v != alt[k]}
        if not geaendert:
            return
        con.execute(f"UPDATE belegungen SET {', '.join(k + ' = ?' for k in geaendert)}, version = version + 1, "
                    "geaendert_von = ?, geaendert_am = ? WHERE id = ?", [*geaendert.values(), benutzer, jetzt(), alt["id"]])
        self._historie(con, benutzer, "belegung", alt["id"], "geändert", {k: alt[k] for k in geaendert},
                       dict(geaendert, auftrag=alt["auftragsnummer"]), grund)

    def _belegung_werte(self, con, s):
        if not con.execute("SELECT 1 FROM maschinen WHERE id = ?", (s.get("maschine"),)).fetchone():
            raise Fehler(f"Unbekannte Maschine: {s.get('maschine')}")
        try:
            beginn = kalender.zeit(s.get("beginn"))
            ist = [kalender.zeit(s.get(f)) for f in ("ist_beginn", "ist_ende")]
        except ValueError:
            raise Fehler("Ungültige Zeitangabe") from None
        if not beginn:
            raise Fehler("Beginn angeben")
        if ist[0] and ist[1] and ist[1] < ist[0]:
            raise Fehler("Ist-Ende liegt vor dem Ist-Beginn")
        return dict(maschine=s["maschine"], beginn=kalender.zeit_text(beginn),
                    dauer_min=_zahl(s.get("dauer_min"), "Dauer", mindest=0),
                    fixiert=1 if s.get("fixiert") in (True, 1, "1", "ja") else 0,
                    ist_beginn=kalender.zeit_text(ist[0]), ist_ende=kalender.zeit_text(ist[1]))

    # ------------------------------------------------------------------ Sicherung
    def sicherung(self, ordner=None, behalten=SICHERUNGEN_BEHALTEN):
        """Geprüfte Kopie (sqlite-Backup, integrity_check) nach Sicherung/ neben der Datendatei; es bleiben die
        letzten `behalten`. Ergebnis: Pfad."""
        ordner = Path(ordner) if ordner else self.pfad.parent / "Sicherung"
        ordner.mkdir(parents=True, exist_ok=True)
        name = f"{self.pfad.stem}_{datetime.datetime.now():%Y-%m-%d_%H%M%S}"
        ziel, n = ordner / f"{name}.db", 1
        while ziel.exists():
            ziel = ordner / f"{name}_{n}.db"
            n += 1
        kopie = sqlite3.connect(ziel)
        try:
            with self.sperre:
                self.con.backup(kopie)
            if kopie.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise OSError(f"Sicherung {ziel} ist beschädigt")
        except BaseException:
            kopie.close()
            ziel.unlink(missing_ok=True)
            raise
        kopie.close()
        alle = sorted(ordner.glob(f"{self.pfad.stem}_*.db"), key=lambda p: (p.stat().st_mtime_ns, p.name))
        for p in alle[:max(0, len(alle) - behalten)]:
            p.unlink(missing_ok=True)
        return ziel

    def sicherung_heute(self, ordner=None):
        ordner = Path(ordner) if ordner else self.pfad.parent / "Sicherung"
        if any(ordner.glob(f"{self.pfad.stem}_{datetime.date.today():%Y-%m-%d}_*.db")):
            return None
        return self.sicherung(ordner)
