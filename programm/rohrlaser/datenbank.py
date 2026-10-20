"""Datenbank des Programms: eine SQLite-Datei mit Stammdaten, Einstellungen und Angeboten.

Das Schema entsteht aus stammdaten.TABELLEN und angebot.KOPF/POSITIONEN; die Schemaversion steht in
PRAGMA user_version, damit spätere Versionen alte Dateien erweitern können (1 = nur Stammdaten,
2 = mit Aufträgen, 3 = mit Staffeln und Staffelpreisen, 4 = Maschinengrenzen Hüllkreis/Metergewicht und
Frachtkosten im Kopf, 5 = Zusatzarbeiten, Preis je Gewinde, Schneidzeit manuell, 6 = Aufträge heißen Angebote,
7 = Kunden und Zahlungsbedingungen mit Skonto im Kopf,
8 = Nachkalkulation je Angebot, 9 = 3D-Netze der STEP-Teile je Position, 10 = Kalkulationswerte je Angebot,
11 = Werkstoff-Kategorien, Oberflächen, Schneiddaten je Kategorie und Schneidgas, 14 = Werte je Staffel:
Menge bis, Materialzuschlag, Gewinn, Nebenkosten usw.).
Vor dem Erweitern einer Datei älterer Version legt das Programm eine Sicherung an (Daten/Sicherung, Zusatz
'vor_Schema_<neu>'); mit ihr und der alten Programmversion lässt sich jede Umstellung rückgängig machen.
Fehlende Spalten älterer Dateien werden beim Öffnen ergänzt; Dateien vor Schema 5 bekommen die
Beispiel-Zusatzarbeiten, Dateien vor Schema 6 werden von Auftrag auf Angebot umbenannt, Dateien vor Schema 11
bekommen Kategorien, die neuen Beispiel-Werkstoffe und -Oberflächen und Schneiddaten je Kategorie.
"""
import datetime
import json
import sqlite3
from pathlib import Path

from .angebot import KALK_PROZENT, KALKULATION, KOPF, POSITIONEN, ZAHLUNG, naechste_nummer
from .staffeln import STUFE_FELDER
from .stammdaten import (TABELLEN, TABELLE, EINSTELLUNGEN, EINSTELLUNG, VERWEISE, beispiel_zusatzarbeiten,
                         beispiel_arbeitsschritte, beispiel_stundensaetze,
                         beispieldaten, kategorie_raten, kontext_aus, OFFENE_PROFILE)

SCHEMA_VERSION = 14     # 14: Werte je Staffel (Materialzuschlag, Gewinn, Nebenkosten …), leer = Wert des Angebots
# Schema 6: alte Namen (Schema 2–5) -> neue Namen
UMBENANNT_TABELLEN = (("auftraege", "angebote"),)
UMBENANNT_SPALTEN = (("positionen", "auftrag_id", "angebot_id"), ("step_protokoll", "auftrag_id", "angebot_id"),
                     ("staffeln", "auftrag_id", "angebot_id"))
UMBENANNT_EINSTELLUNGEN = (("letzte_auftragsnummer", "letzte_angebotsnummer"), ("auftragsaufschlag", "angebotsaufschlag"))
ALTE_INDIZES = ("auftraege_nummer", "positionen_auftrag")
SQL_ART = {"zahl": "REAL", "ganz": "INTEGER"}
SICHERUNGEN_BEHALTEN = 30


class Datenbank:
    def __init__(self, pfad):
        self.pfad = Path(pfad)
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        neu = not self.pfad.exists()
        self.con = sqlite3.connect(self.pfad)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=DELETE")
        self._anlegen()
        if neu:
            self.stammdaten_ersetzen(beispieldaten(), {}, "Beispieldaten")

    def schliessen(self):
        self.con.close()

    # -------------------------------------------------------------- Schema
    def _anlegen(self):
        version = self.con.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"Die Datendatei {self.pfad} stammt von einer neueren Programmversion "
                               f"(Schema {version}). Bitte das Programm aktualisieren.")
        if 0 < version < SCHEMA_VERSION:    # Rückfall: Stand vor der Umstellung sichern
            self.sicherung(zusatz=f"vor_Schema_{SCHEMA_VERSION}")
        with self.con:
            if 0 < version < 6:
                self._umbenennen()
            if 0 < version < 11:          # Schlüssel der Schneiddaten mit Kategorie und Schneidgas
                self.con.execute('DROP INDEX IF EXISTS "schneiddaten_schluessel"')
            for t in TABELLEN:
                spalten = ", ".join(f'"{f.name}" {SQL_ART.get(f.art, "TEXT")}' for f in t.felder)
                self.con.execute(f'CREATE TABLE IF NOT EXISTS "{t.name}" (id INTEGER PRIMARY KEY, {spalten})')
            self.con.execute("CREATE TABLE IF NOT EXISTS einstellungen (name TEXT PRIMARY KEY, wert TEXT)")
            kopf = ", ".join(f'"{f.name}" {SQL_ART.get(f.art, "TEXT")}' for f in KOPF)
            self.con.execute(f"CREATE TABLE IF NOT EXISTS angebote (id INTEGER PRIMARY KEY, {kopf}, angelegt TEXT, "
                             "geaendert TEXT, ergebnis TEXT, optimiert_am TEXT)")
            self.con.execute("CREATE UNIQUE INDEX IF NOT EXISTS angebote_nummer ON angebote (nummer)")
            spalten = ", ".join(f'"{f.name}" {SQL_ART.get(f.art, "TEXT")}' for f in POSITIONEN.felder)
            self.con.execute("CREATE TABLE IF NOT EXISTS positionen (id INTEGER PRIMARY KEY, angebot_id INTEGER "
                             f"NOT NULL REFERENCES angebote(id) ON DELETE CASCADE, nr INTEGER, {spalten})")
            self.con.execute("CREATE INDEX IF NOT EXISTS positionen_angebot ON positionen (angebot_id, nr)")
            self.con.execute("CREATE TABLE IF NOT EXISTS step_protokoll (id INTEGER PRIMARY KEY, angebot_id INTEGER "
                             "NOT NULL REFERENCES angebote(id) ON DELETE CASCADE, zeile TEXT)")
            self.con.execute("CREATE TABLE IF NOT EXISTS netze (position_id INTEGER PRIMARY KEY REFERENCES "
                             "positionen(id) ON DELETE CASCADE, daten BLOB)")
            self.con.execute("CREATE TABLE IF NOT EXISTS staffeln (id INTEGER PRIMARY KEY, angebot_id INTEGER "
                             "NOT NULL REFERENCES angebote(id) ON DELETE CASCADE, nr INTEGER, schluessel TEXT, "
                             "menge INTEGER, bemerkung TEXT)")
            spalten_a = {r[1] for r in self.con.execute("PRAGMA table_info(angebote)")}
            if "staffelpreise" not in spalten_a:      # Datei aus Schema 2
                self.con.execute("ALTER TABLE angebote ADD COLUMN staffelpreise TEXT")
            if "nachkalkulation" not in spalten_a:    # Datei vor Schema 8
                self.con.execute("ALTER TABLE angebote ADD COLUMN nachkalkulation TEXT")
            if "zeitbasis" not in spalten_a:          # Datei vor Schema 13 (alte Angebote: ohne Snapshot)
                self.con.execute("ALTER TABLE angebote ADD COLUMN zeitbasis TEXT")
            for tabelle, felder in [(t.name, t.felder) for t in TABELLEN] + [("angebote", KOPF),
                                                                            ("positionen", POSITIONEN.felder),
                                                                            ("staffeln", STUFE_FELDER)]:
                vorhanden = {r[1] for r in self.con.execute(f'PRAGMA table_info("{tabelle}")')}
                for f in felder:                       # neue Felder späterer Versionen
                    if f.name not in vorhanden:
                        self.con.execute(f'ALTER TABLE "{tabelle}" ADD COLUMN "{f.name}" {SQL_ART.get(f.art, "TEXT")}')
            for t in TABELLEN:                         # nach den neuen Spalten: Schlüssel können sie enthalten
                # leere Felder im Schlüssel (Schneiddaten: Werkstoff-ID oder Kategorie) zählen als gleich
                schl = ", ".join(f'"{s}"' if t.feld(s).pflicht else f"""COALESCE("{s}", '')""" for s in t.schluessel)
                self.con.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{t.name}_schluessel" ON "{t.name}" ({schl})')
            if 0 < version < 5 and not self.anzahl("zusatzarbeiten"):
                namen = [f.name for f in TABELLE["zusatzarbeiten"].felder]
                self.con.executemany(f'INSERT INTO zusatzarbeiten ({", ".join(namen)}) VALUES ({", ".join("?" * len(namen))})',
                                     [[z[n] for n in namen] for z in beispiel_zusatzarbeiten()])
            if 0 < version < 11:
                self._werkstoffe_ergaenzen()
            if 0 < version < 12:
                self._profilformen_ergaenzen()
            if 0 < version < 13:
                if not self.anzahl("stundensaetze"):
                    self._einfuegen("stundensaetze", beispiel_stundensaetze())
                if not self.anzahl("arbeitsschritte"):
                    self._einfuegen("arbeitsschritte", beispiel_arbeitsschritte())
            self.con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.con.execute("PRAGMA foreign_keys=ON")

    def _einfuegen(self, tabelle, zeilen):
        namen = [f.name for f in TABELLE[tabelle].felder]
        self.con.executemany(f'INSERT INTO "{tabelle}" ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                             f'VALUES ({", ".join("?" * len(namen))})', [[z.get(n) for n in namen] for z in zeilen])

    def _profilformen_ergaenzen(self):
        """Dateien vor Schema 12: U-, C-, L-Profil und Flachstahl in die Auswahlliste Profilformen (vor
        'Sonderprofil'), sofern sie dort fehlen; eigene Einträge bleiben."""
        formen = [s.strip() for s in (self.einstellung("profilformen") or "").splitlines() if s.strip()]
        neu = [f for f in OFFENE_PROFILE if f not in formen]
        if neu:
            i = formen.index("Sonderprofil") if "Sonderprofil" in formen else len(formen)
            self._einstellung_schreiben("profilformen", "\n".join(formen[:i] + neu + formen[i:]))

    def _werkstoffe_ergaenzen(self):
        """Dateien vor Schema 11: Kategorie der vorhandenen Werkstoffe raten, fehlende Beispiel-Werkstoffe und
        Oberflächen ergänzen (vorhandene bleiben unverändert). Schneiddaten: unveränderte Beispieldaten werden
        ersetzt; eigene Werte bleiben und gehen vor, dazu kommen die Beispielwerte je Kategorie."""
        neu = beispieldaten()
        for z in self.zeilen("werkstoffe"):
            if not z.get("kategorie"):
                self.con.execute("UPDATE werkstoffe SET kategorie=? WHERE id=?", (kategorie_raten(z), z["id"]))
        da = {z["werkstoff_id"] for z in self.zeilen("werkstoffe")}
        self._einfuegen("werkstoffe", [z for z in neu["werkstoffe"] if z["werkstoff_id"] not in da])
        if not self.anzahl("oberflaechen"):
            self._einfuegen("oberflaechen", neu["oberflaechen"])
        if self.einstellung("stammdaten_herkunft") == "Beispieldaten":
            self.con.execute("DELETE FROM schneiddaten")
        self._einfuegen("schneiddaten", neu["schneiddaten"])

    def _umbenennen(self):
        """Dateien vor Schema 6: Tabellen, Spalten und Einstellungen von Auftrag auf Angebot umbenennen."""
        tabellen = {r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for alt, neu in UMBENANNT_TABELLEN:
            if alt in tabellen and neu not in tabellen:
                self.con.execute(f'ALTER TABLE "{alt}" RENAME TO "{neu}"')
        for tabelle, alt, neu in UMBENANNT_SPALTEN:
            if tabelle in tabellen and alt in {r[1] for r in self.con.execute(f'PRAGMA table_info("{tabelle}")')}:
                self.con.execute(f'ALTER TABLE "{tabelle}" RENAME COLUMN "{alt}" TO "{neu}"')
        for name in ALTE_INDIZES:
            self.con.execute(f'DROP INDEX IF EXISTS "{name}"')
        for alt, neu in UMBENANNT_EINSTELLUNGEN:
            self.con.execute("UPDATE OR IGNORE einstellungen SET name=? WHERE name=?", (neu, alt))

    # -------------------------------------------------------------- Stammdaten
    def zeilen(self, tabelle):
        return [dict(r) for r in self.con.execute(f'SELECT * FROM "{tabelle}" ORDER BY id')]

    def anzahl(self, tabelle):
        return self.con.execute(f'SELECT COUNT(*) FROM "{tabelle}"').fetchone()[0]

    def _stammdaten_geaendert(self, tabelle):
        """Nach einer Änderung von Hand gelten die Stammdaten nicht mehr als Beispielwerte (Startseite).
        Kunden zählen dabei nicht: sie ändern keine Rechenwerte."""
        if tabelle in TABELLE and tabelle != "kunden":
            self._einstellung_schreiben("stammdaten_herkunft", "eigene Werte")
            self._einstellung_schreiben("stammdaten_stand", self._jetzt())

    def neu(self, tabelle, werte=None):
        werte = {k: v for k, v in (werte or {}).items() if k != "id"}
        with self.con:
            self._stammdaten_geaendert(tabelle)
            if not werte:
                return self.con.execute(f'INSERT INTO "{tabelle}" DEFAULT VALUES').lastrowid
            namen = ", ".join(f'"{k}"' for k in werte)
            return self.con.execute(f'INSERT INTO "{tabelle}" ({namen}) VALUES ({", ".join("?" * len(werte))})',
                                    list(werte.values())).lastrowid

    def aendern(self, tabelle, zeilen_id, feld, wert):
        """Ein Feld ändern. Ist es ein Schlüssel, auf den andere Tabellen verweisen (Profil-ID,
        Werkstoff-ID, Maschinen-ID), werden die Verweise mit umbenannt. Doppelte Schlüssel lösen
        ValueError aus."""
        TABELLE[tabelle].feld(feld)   # unbekanntes Feld -> StopIteration
        alt = self.con.execute(f'SELECT "{feld}" FROM "{tabelle}" WHERE id=?', (zeilen_id,)).fetchone()
        try:
            with self.con:
                self._stammdaten_geaendert(tabelle)
                self.con.execute(f'UPDATE "{tabelle}" SET "{feld}"=? WHERE id=?', (wert, zeilen_id))
                if alt is not None and alt[0] not in (None, "") and wert not in (None, ""):
                    for ziel, zfeld in VERWEISE.get((tabelle, feld), ()):
                        self.con.execute(f'UPDATE "{ziel}" SET "{zfeld}"=? WHERE "{zfeld}"=?', (wert, alt[0]))
        except sqlite3.IntegrityError:
            t = TABELLE[tabelle]
            namen = " + ".join(t.feld(s).titel for s in t.schluessel)
            raise ValueError(f"Diese Kombination ({namen}) gibt es schon." if len(t.schluessel) > 1
                             else f"{namen} '{wert}' gibt es schon.")

    def verweise(self, tabelle, zeilen_id):
        """Anzahl der Zeilen anderer Tabellen, die auf diese Zeile verweisen (Hinweis vor dem Löschen)."""
        n = 0
        for (quelle, feld), ziele in VERWEISE.items():
            if quelle != tabelle:
                continue
            r = self.con.execute(f'SELECT "{feld}" FROM "{tabelle}" WHERE id=?', (zeilen_id,)).fetchone()
            if r and r[0] not in (None, ""):
                for ziel, zfeld in ziele:
                    n += self.con.execute(f'SELECT COUNT(*) FROM "{ziel}" WHERE "{zfeld}"=?', (r[0],)).fetchone()[0]
        return n

    def loeschen(self, tabelle, ids):
        with self.con:
            self._stammdaten_geaendert(tabelle)
            self.con.executemany(f'DELETE FROM "{tabelle}" WHERE id=?', [(i,) for i in ids])

    def stammdaten_ersetzen(self, daten, einstellungen, herkunft):
        """Alle Stammdatentabellen in einem Schritt ersetzen (z. B. Beispieldaten einer neuen Datei).
        daten: {Tabelle: [Zeile, …]}; einstellungen: {Name: Wert}, nur die genannten werden gesetzt."""
        with self.con:
            for t in TABELLEN:
                if t.name not in daten:
                    continue
                self.con.execute(f'DELETE FROM "{t.name}"')
                namen = [f.name for f in t.felder]
                self.con.executemany(
                    f'INSERT INTO "{t.name}" ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                    f'VALUES ({", ".join("?" * len(namen))})',
                    [[z.get(n) for n in namen] for z in daten[t.name]])
            for name, wert in einstellungen.items():
                self._einstellung_schreiben(name, wert)
            self._einstellung_schreiben("stammdaten_herkunft", herkunft)
            self._einstellung_schreiben("stammdaten_stand", datetime.datetime.now().isoformat(timespec="seconds"))

    def kontext(self):
        formen = [s.strip() for s in self.einstellung("profilformen").splitlines() if s.strip()]
        kategorien = [s.strip() for s in (self.einstellung("kategorien") or "").splitlines() if s.strip()]
        return kontext_aus({t: self.zeilen(t) for t in ("profile", "werkstoffe", "maschinen", "oberflaechen",
                                                        "stundensaetze")},
                           formen, kategorien)

    def tabellen(self):
        """Stammdaten, die die Rechnung braucht (Preise, Schneiddaten, Gewinde, Zusatzarbeiten, Stundensätze,
        Arbeitsschritte)."""
        return {t: self.zeilen(t) for t in ("preise", "schneiddaten", "gewinde", "zusatzarbeiten", "stundensaetze",
                                            "arbeitsschritte")}

    def zeitbasis_vorgabe(self, maschinen_id):
        """Snapshot der Stundensätze und Zeitvorgaben für ein Angebot (rechnen.zeitbasis_aus)."""
        from .rechnen import zeitbasis_aus
        return zeitbasis_aus(maschinen_id, self.kontext(), self.tabellen())

    def zeitbasis_speichern(self, angebot_id, zeitbasis):
        """Stundensätze und Zeitvorgaben eines Angebots setzen (None = wieder die aktuellen Stammdaten)."""
        with self.con:
            self.con.execute("UPDATE angebote SET zeitbasis=?, geaendert=? WHERE id=?",
                             (json.dumps(zeitbasis, ensure_ascii=False) if zeitbasis is not None else None,
                              self._jetzt(), angebot_id))

    # -------------------------------------------------------------- Kunden
    def kunde(self, kundennr):
        """Kundenzeile zur Kundennummer oder None."""
        if kundennr in (None, ""):
            return None
        r = self.con.execute("SELECT * FROM kunden WHERE kundennr=?", (kundennr,)).fetchone()
        return dict(r) if r else None

    def zahlungsbedingungen(self, kundennr=None):
        """Skonto [%], Skontofrist und Zahlungsziel für ein neues Angebot: Werte des Kunden, fehlende aus den
        Einstellungen."""
        k = self.kunde(kundennr) or {}
        return {n: k[n] if k.get(n) is not None else self.einstellung(n) for n in ZAHLUNG}

    def kalkulation_vorgaben(self):
        """Kalkulationswerte für ein Angebot aus den Einstellungen (Prozentwerte in %)."""
        out = {}
        for f in KALKULATION:
            w = self.einstellung(f.name)
            if isinstance(w, (int, float)):
                out[f.name] = round(w * 100, 4) if f.name in KALK_PROZENT else w
        return out

    def kalkulation_zuruecksetzen(self, angebot_id):
        """Kalkulationswerte, Stundensätze und Zeitvorgaben des Angebots wieder auf die Einstellungen setzen."""
        for n, w in self.kalkulation_vorgaben().items():
            self.angebot_aendern(angebot_id, n, w)
        self.zeitbasis_speichern(angebot_id, self.zeitbasis_vorgabe(self.angebot(angebot_id).get("maschine")))

    def kunde_uebernehmen(self, angebot_id, kundennr):
        """Kundennummer ins Angebot; steht sie im Kundenstamm, auch Name und Zahlungsbedingungen.
        Ergebnis: Kundenzeile oder None."""
        k = self.kunde(kundennr)
        self.angebot_aendern(angebot_id, "kundennr", kundennr)
        if k:
            self.angebot_aendern(angebot_id, "kunde", k["name"])
            for n, w in self.zahlungsbedingungen(kundennr).items():
                self.angebot_aendern(angebot_id, n, w)
        return k

    # -------------------------------------------------------------- Angebote
    def angebote(self, suche=""):
        """Übersicht: Kopf, Anzahl Positionen und Teile, Zeitpunkt der Optimierung."""
        sql = ("SELECT a.id, a.nummer, a.kundennr, a.kunde, a.datum, a.maschine, a.geaendert, a.optimiert_am, "
               "a.nachkalkulation IS NOT NULL AS nachkalkuliert, "
               "COUNT(p.id) AS positionen, COALESCE(SUM(p.stueck), 0) AS teile FROM angebote a "
               "LEFT JOIN positionen p ON p.angebot_id = a.id")
        werte = []
        if suche:
            sql += (" WHERE a.nummer LIKE ? OR a.kunde LIKE ? OR a.kundennr LIKE ? OR a.bemerkung LIKE ? "
                    "OR a.id IN (SELECT angebot_id FROM positionen WHERE artikel LIKE ? OR bezeichnung LIKE ?)")
            werte = [f"%{suche}%"] * 6
        sql += " GROUP BY a.id ORDER BY a.datum DESC, a.id DESC"
        return [dict(r) for r in self.con.execute(sql, werte)]

    def angebot(self, angebot_id):
        r = self.con.execute("SELECT * FROM angebote WHERE id=?", (angebot_id,)).fetchone()
        if r is None:
            return None
        a = dict(r)
        a["ergebnis"] = json.loads(a["ergebnis"]) if a["ergebnis"] else None
        a["staffelpreise"] = json.loads(a["staffelpreise"]) if a.get("staffelpreise") else None
        a["nachkalkulation"] = json.loads(a["nachkalkulation"]) if a.get("nachkalkulation") else None
        a["zeitbasis"] = json.loads(a["zeitbasis"]) if a.get("zeitbasis") else None
        return a

    def _jetzt(self):
        return datetime.datetime.now().isoformat(timespec="seconds")

    def angebot_neu(self, kopf=None):
        """Neues Angebot mit Vorgaben aus den Einstellungen; die Nummer zählt die letzte hoch."""
        kopf = dict(kopf or {})
        if not kopf.get("nummer"):
            nr = naechste_nummer(self.einstellung("letzte_angebotsnummer"))
            while self.con.execute("SELECT 1 FROM angebote WHERE nummer=?", (nr,)).fetchone():
                nr = naechste_nummer(nr)
            kopf["nummer"] = nr
        kopf.setdefault("datum", datetime.date.today().isoformat())
        kopf.setdefault("maschine", self.einstellung("standard_maschine"))
        kopf.setdefault("stange", self.einstellung("standard_stange"))
        k = self.kunde(kopf.get("kundennr"))
        if k and not kopf.get("kunde"):
            kopf["kunde"] = k["name"]
        for n, w in self.zahlungsbedingungen(kopf.get("kundennr")).items():
            kopf.setdefault(n, w)
        for n, w in self.kalkulation_vorgaben().items():
            kopf.setdefault(n, w)
        namen = [f.name for f in KOPF if f.name in kopf]
        zb = kopf.get("zeitbasis") or self.zeitbasis_vorgabe(kopf.get("maschine"))     # Snapshot beim Anlegen
        try:
            with self.con:
                i = self.con.execute(
                    f'INSERT INTO angebote ({", ".join(namen)}, zeitbasis, angelegt, geaendert) VALUES '
                    f'({", ".join("?" * len(namen))}, ?, ?, ?)',
                    [kopf[n] for n in namen] + [json.dumps(zb, ensure_ascii=False)] + [self._jetzt()] * 2).lastrowid
                self._einstellung_schreiben("letzte_angebotsnummer", kopf["nummer"])
        except sqlite3.IntegrityError:
            raise ValueError(f"Angebotsnummer '{kopf['nummer']}' gibt es schon.")
        return i

    def angebot_aendern(self, angebot_id, feld, wert):
        if feld not in {f.name for f in KOPF}:
            raise KeyError(feld)
        if feld == "nummer" and not wert:
            raise ValueError("Die Angebotsnummer darf nicht leer sein.")
        try:
            with self.con:
                self.con.execute(f'UPDATE angebote SET "{feld}"=?, geaendert=? WHERE id=?',
                                 (wert, self._jetzt(), angebot_id))
                if feld == "maschine":          # andere Maschine: deren Stundensatz, Rüstzeit, Stangenwechsel
                    zb = self.con.execute("SELECT zeitbasis FROM angebote WHERE id=?", (angebot_id,)).fetchone()[0]
                    if zb:
                        zb = json.loads(zb)
                        zb["maschine"] = self.zeitbasis_vorgabe(wert)["maschine"]
                        self.con.execute("UPDATE angebote SET zeitbasis=? WHERE id=?",
                                         (json.dumps(zb, ensure_ascii=False), angebot_id))
        except sqlite3.IntegrityError:
            raise ValueError(f"Angebotsnummer '{wert}' gibt es schon.")

    def angebot_kopieren(self, angebot_id, kundennr=None):
        """Kopie mit neuer Nummer und heutigem Datum. kundennr: anderer Kunde (Name und Zahlungsbedingungen
        aus dem Kundenstamm, sonst bleibt nur die Nummer); None = gleicher Kunde."""
        a = self.angebot(angebot_id)
        kopf = {f.name: a[f.name] for f in KOPF if f.name != "nummer"}
        kopf["datum"] = datetime.date.today().isoformat()
        kopf["zeitbasis"] = a.get("zeitbasis")      # gleiche Stundensätze; ältere Angebote: aktuelle Vorgaben
        if kundennr is not None and kundennr != a.get("kundennr"):
            k = self.kunde(kundennr)
            kopf["kundennr"] = kundennr or None
            kopf["kunde"] = k["name"] if k else None
            kopf.update(self.zahlungsbedingungen(kundennr))
        neu = self.angebot_neu(kopf)
        netze = self.netze(angebot_id)
        for p in self.positionen(angebot_id):
            i = self.position_neu(neu, p)
            if p["id"] in netze:
                self.netz_speichern(i, netze[p["id"]])
        for st in self.staffeln(angebot_id):
            self.staffel_neu(neu, st)
        return neu

    def angebot_loeschen(self, angebot_id):
        with self.con:
            self.con.execute("DELETE FROM angebote WHERE id=?", (angebot_id,))

    def ergebnis_speichern(self, angebot_id, ergebnis):
        with self.con:
            self.con.execute("UPDATE angebote SET ergebnis=?, optimiert_am=? WHERE id=?",
                             (json.dumps(ergebnis, ensure_ascii=False) if ergebnis else None,
                              self._jetzt() if ergebnis else None, angebot_id))

    def staffelpreise_speichern(self, angebot_id, staffelpreise):
        """staffelpreise: {'zeilen': [...], 'kennung': str, 'am': Zeitpunkt} oder None"""
        with self.con:
            self.con.execute("UPDATE angebote SET staffelpreise=? WHERE id=?",
                             (json.dumps(staffelpreise, ensure_ascii=False) if staffelpreise else None, angebot_id))

    def nachkalkulation_speichern(self, angebot_id, ist):
        """Ist-Werte der Nachkalkulation (siehe nachkalkulation.py) oder None."""
        with self.con:
            self.con.execute("UPDATE angebote SET nachkalkulation=? WHERE id=?",
                             (json.dumps(ist, ensure_ascii=False) if ist else None, angebot_id))

    # -------------------------------------------------------------- Staffeln (Mengenstufen)
    def staffeln(self, angebot_id):
        return [dict(r) for r in self.con.execute("SELECT * FROM staffeln WHERE angebot_id=? ORDER BY nr, id",
                                                  (angebot_id,))]

    def staffel_neu(self, angebot_id, werte=None):
        werte = werte or {}
        nr = self.con.execute("SELECT COALESCE(MAX(nr), 0) + 1 FROM staffeln WHERE angebot_id=?",
                              (angebot_id,)).fetchone()[0]
        namen = [f.name for f in STUFE_FELDER]
        with self.con:
            return self.con.execute(f'INSERT INTO staffeln (angebot_id, nr, {", ".join(chr(34) + n + chr(34) for n in namen)}) '
                                    f'VALUES (?, ?, {", ".join("?" * len(namen))})',
                                    [angebot_id, nr] + [werte.get(n) for n in namen]).lastrowid

    def staffel_aendern(self, staffel_id, feld, wert):
        if feld not in {f.name for f in STUFE_FELDER}:
            raise KeyError(feld)
        with self.con:
            self.con.execute(f'UPDATE staffeln SET "{feld}"=? WHERE id=?', (wert, staffel_id))

    def staffeln_loeschen(self, ids):
        with self.con:
            self.con.executemany("DELETE FROM staffeln WHERE id=?", [(i,) for i in ids])

    def positionen(self, angebot_id):
        return [dict(r) for r in self.con.execute("SELECT * FROM positionen WHERE angebot_id=? ORDER BY nr, id",
                                                  (angebot_id,))]

    def position_neu(self, angebot_id, werte=None):
        werte = {f.name: (werte or {}).get(f.name) for f in POSITIONEN.felder if (werte or {}).get(f.name) is not None}
        nr = self.con.execute("SELECT COALESCE(MAX(nr), 0) + 1 FROM positionen WHERE angebot_id=?",
                              (angebot_id,)).fetchone()[0]
        namen = ["angebot_id", "nr"] + list(werte)
        with self.con:
            i = self.con.execute(f'INSERT INTO positionen ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                                 f'VALUES ({", ".join("?" * len(namen))})', [angebot_id, nr] + list(werte.values())).lastrowid
            self.con.execute("UPDATE angebote SET geaendert=? WHERE id=?", (self._jetzt(), angebot_id))
        return i

    def position_aendern(self, position_id, feld, wert):
        POSITIONEN.feld(feld)
        with self.con:
            self.con.execute(f'UPDATE positionen SET "{feld}"=? WHERE id=?', (wert, position_id))
            self.con.execute("UPDATE angebote SET geaendert=? WHERE id=(SELECT angebot_id FROM positionen WHERE id=?)",
                             (self._jetzt(), position_id))

    def positionen_loeschen(self, ids):
        with self.con:
            self.con.executemany("DELETE FROM positionen WHERE id=?", [(i,) for i in ids])

    # -------------------------------------------------------------- 3D-Netze (STEP-Import)
    def netz_speichern(self, position_id, daten):
        """Dreiecksnetz einer Position (zlib-komprimiertes JSON, siehe ansicht3d.packen)."""
        with self.con:
            self.con.execute("INSERT OR REPLACE INTO netze (position_id, daten) VALUES (?, ?)", (position_id, daten))

    def netz(self, position_id):
        r = self.con.execute("SELECT daten FROM netze WHERE position_id=?", (position_id,)).fetchone()
        return bytes(r[0]) if r else None

    def netz_ids(self, angebot_id):
        """Positions-IDs eines Angebots, für die es ein 3D-Netz gibt."""
        return {r[0] for r in self.con.execute("SELECT n.position_id FROM netze n JOIN positionen p ON "
                                                "p.id = n.position_id WHERE p.angebot_id=?", (angebot_id,))}

    def netze(self, angebot_id):
        """{Positions-ID: Netz-Bytes} aller Positionen eines Angebots mit 3D-Daten."""
        return {r[0]: bytes(r[1]) for r in self.con.execute(
            "SELECT n.position_id, n.daten FROM netze n JOIN positionen p ON p.id = n.position_id "
            "WHERE p.angebot_id=?", (angebot_id,))}

    def protokoll(self, angebot_id):
        return [json.loads(r[0]) for r in self.con.execute(
            "SELECT zeile FROM step_protokoll WHERE angebot_id=? ORDER BY id", (angebot_id,))]

    def protokoll_anhaengen(self, angebot_id, zeilen):
        with self.con:
            self.con.executemany("INSERT INTO step_protokoll (angebot_id, zeile) VALUES (?, ?)",
                                 [(angebot_id, json.dumps(z, default=str, ensure_ascii=False)) for z in zeilen])

    def profile_anlegen(self, profile):
        """Profile aus Optimierung (Name) oder STEP-Import anlegen, vorhandene IDs bleiben unverändert."""
        for p in profile:
            if not self.con.execute("SELECT 1 FROM profile WHERE profil_id=?", (p["profil_id"],)).fetchone():
                self.neu("profile", {k: v for k, v in p.items() if k in {f.name for f in TABELLE["profile"].felder}})

    # -------------------------------------------------------------- Einstellungen
    def einstellung(self, name):
        r = self.con.execute("SELECT wert FROM einstellungen WHERE name=?", (name,)).fetchone()
        if r is None:
            e = EINSTELLUNG.get(name)
            return e.vorgabe if e else None
        return json.loads(r[0])

    def einstellung_setzen(self, name, wert):
        with self.con:
            self._einstellung_schreiben(name, wert)

    def _einstellung_schreiben(self, name, wert):
        self.con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES (?, ?)",
                         (name, json.dumps(wert, ensure_ascii=False)))

    def einstellungen(self):
        return {e.name: self.einstellung(e.name) for e in EINSTELLUNGEN}

    # -------------------------------------------------------------- Sicherung
    def sicherung(self, ordner=None, behalten=SICHERUNGEN_BEHALTEN, zusatz=None):
        """Kopie der Datendatei nach Daten/Sicherung (sqlite-Backup, auch bei offener Datei sicher).
        zusatz: fester Namensteil statt der Uhrzeit (eine Datei, die überschrieben wird, z. B. 'beenden').
        Ältere Sicherungen über `behalten` hinaus werden gelöscht. Ergebnis: Pfad der Sicherung."""
        ordner = Path(ordner) if ordner else self.pfad.parent / "Sicherung"
        ordner.mkdir(parents=True, exist_ok=True)
        if zusatz:
            ziel = ordner / f"{self.pfad.stem}_{datetime.date.today():%Y-%m-%d}_{zusatz}.db"
            ziel.unlink(missing_ok=True)
        else:
            ziel = ordner / f"{self.pfad.stem}_{datetime.datetime.now():%Y-%m-%d_%H%M%S}.db"
            n = 1
            while ziel.exists():
                ziel = ordner / f"{self.pfad.stem}_{datetime.datetime.now():%Y-%m-%d_%H%M%S}_{n}.db"
                n += 1
        kopie = sqlite3.connect(ziel)
        with kopie:
            self.con.backup(kopie)
        kopie.close()
        alte = sorted(ordner.glob(f"{self.pfad.stem}_*.db"))
        for p in alte[:max(0, len(alte) - behalten)]:
            p.unlink()
        return ziel

    def sicherung_heute(self, ordner=None):
        """Beim Start: eine Sicherung je Tag."""
        ordner = Path(ordner) if ordner else self.pfad.parent / "Sicherung"
        if any(ordner.glob(f"{self.pfad.stem}_{datetime.date.today():%Y-%m-%d}_*.db")):
            return None
        return self.sicherung(ordner)

    def sicherungen(self, zusatz=None):
        """Sicherung nach Daten/Sicherung und, falls eingestellt, in den zweiten Sicherungsordner.
        Ergebnis: (Pfade, Fehlertext oder None) – ein nicht erreichbarer zweiter Ordner (Netzlaufwerk,
        USB-Stick fehlt) verhindert die erste Sicherung nicht."""
        pfade = [self.sicherung(zusatz=zusatz)]
        ordner2 = (self.einstellung("sicherung_ordner2") or "").strip()
        if not ordner2:
            return pfade, None
        try:
            pfade.append(self.sicherung(ordner2, zusatz=zusatz))
        except OSError as e:
            return pfade, f"Zweiter Sicherungsordner nicht erreichbar ({ordner2}): {e}"
        return pfade, None
