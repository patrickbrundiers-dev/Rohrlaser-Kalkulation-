"""Datenbank des Programms: eine SQLite-Datei mit Stammdaten, Einstellungen und Aufträgen.

Das Schema entsteht aus stammdaten.TABELLEN und auftrag.KOPF/POSITIONEN; die Schemaversion steht in
PRAGMA user_version, damit spätere Versionen alte Dateien erweitern können (1 = nur Stammdaten,
2 = mit Aufträgen, 3 = mit Staffeln und Staffelpreisen, 4 = Maschinengrenzen Hüllkreis/Metergewicht und
Frachtkosten im Auftragskopf, 5 = Zusatzarbeiten, Preis je Gewinde, Schneidzeit manuell). Fehlende Spalten
älterer Dateien werden beim Öffnen ergänzt; Dateien vor Schema 5 bekommen die Beispiel-Zusatzarbeiten.
"""
import datetime
import json
import sqlite3
from pathlib import Path

from .auftrag import KOPF, POSITIONEN, naechste_nummer
from .stammdaten import (TABELLEN, TABELLE, EINSTELLUNGEN, EINSTELLUNG, VERWEISE, beispiel_zusatzarbeiten,
                         beispieldaten, kontext_aus)

SCHEMA_VERSION = 5
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
        with self.con:
            for t in TABELLEN:
                spalten = ", ".join(f'"{f.name}" {SQL_ART.get(f.art, "TEXT")}' for f in t.felder)
                self.con.execute(f'CREATE TABLE IF NOT EXISTS "{t.name}" (id INTEGER PRIMARY KEY, {spalten})')
                schl = ", ".join(f'"{s}"' for s in t.schluessel)
                self.con.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{t.name}_schluessel" ON "{t.name}" ({schl})')
            self.con.execute("CREATE TABLE IF NOT EXISTS einstellungen (name TEXT PRIMARY KEY, wert TEXT)")
            kopf = ", ".join(f'"{f.name}" {SQL_ART.get(f.art, "TEXT")}' for f in KOPF)
            self.con.execute(f"CREATE TABLE IF NOT EXISTS auftraege (id INTEGER PRIMARY KEY, {kopf}, angelegt TEXT, "
                             "geaendert TEXT, ergebnis TEXT, optimiert_am TEXT)")
            self.con.execute("CREATE UNIQUE INDEX IF NOT EXISTS auftraege_nummer ON auftraege (nummer)")
            spalten = ", ".join(f'"{f.name}" {SQL_ART.get(f.art, "TEXT")}' for f in POSITIONEN.felder)
            self.con.execute("CREATE TABLE IF NOT EXISTS positionen (id INTEGER PRIMARY KEY, auftrag_id INTEGER "
                             f"NOT NULL REFERENCES auftraege(id) ON DELETE CASCADE, nr INTEGER, {spalten})")
            self.con.execute("CREATE INDEX IF NOT EXISTS positionen_auftrag ON positionen (auftrag_id, nr)")
            self.con.execute("CREATE TABLE IF NOT EXISTS step_protokoll (id INTEGER PRIMARY KEY, auftrag_id INTEGER "
                             "NOT NULL REFERENCES auftraege(id) ON DELETE CASCADE, zeile TEXT)")
            self.con.execute("CREATE TABLE IF NOT EXISTS staffeln (id INTEGER PRIMARY KEY, auftrag_id INTEGER "
                             "NOT NULL REFERENCES auftraege(id) ON DELETE CASCADE, nr INTEGER, schluessel TEXT, "
                             "menge INTEGER, bemerkung TEXT)")
            spalten_a = {r[1] for r in self.con.execute("PRAGMA table_info(auftraege)")}
            if "staffelpreise" not in spalten_a:      # Datei aus Schema 2
                self.con.execute("ALTER TABLE auftraege ADD COLUMN staffelpreise TEXT")
            for tabelle, felder in [(t.name, t.felder) for t in TABELLEN] + [("auftraege", KOPF),
                                                                            ("positionen", POSITIONEN.felder)]:
                vorhanden = {r[1] for r in self.con.execute(f'PRAGMA table_info("{tabelle}")')}
                for f in felder:                       # neue Felder späterer Versionen
                    if f.name not in vorhanden:
                        self.con.execute(f'ALTER TABLE "{tabelle}" ADD COLUMN "{f.name}" {SQL_ART.get(f.art, "TEXT")}')
            if 0 < version < 5 and not self.anzahl("zusatzarbeiten"):
                namen = [f.name for f in TABELLE["zusatzarbeiten"].felder]
                self.con.executemany(f'INSERT INTO zusatzarbeiten ({", ".join(namen)}) VALUES ({", ".join("?" * len(namen))})',
                                     [[z[n] for n in namen] for z in beispiel_zusatzarbeiten()])
            self.con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.con.execute("PRAGMA foreign_keys=ON")

    # -------------------------------------------------------------- Stammdaten
    def zeilen(self, tabelle):
        return [dict(r) for r in self.con.execute(f'SELECT * FROM "{tabelle}" ORDER BY id')]

    def anzahl(self, tabelle):
        return self.con.execute(f'SELECT COUNT(*) FROM "{tabelle}"').fetchone()[0]

    def neu(self, tabelle, werte=None):
        werte = {k: v for k, v in (werte or {}).items() if k != "id"}
        with self.con:
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
            self.con.executemany(f'DELETE FROM "{tabelle}" WHERE id=?', [(i,) for i in ids])

    def stammdaten_ersetzen(self, daten, einstellungen, herkunft):
        """Alle Stammdatentabellen in einem Schritt ersetzen (Übernahme aus einer Mappe).
        daten: {Tabelle: [Zeile, …]}; einstellungen: {Name: Wert}, nur die genannten werden gesetzt."""
        with self.con:
            for t in TABELLEN:
                if t.name not in daten:
                    continue
                # Felder, die es nur im Programm gibt (z. B. Preis je Gewinde), bleiben je Schlüssel erhalten
                nur_programm = [f.name for f in t.felder if not f.spalte]
                if nur_programm:
                    alt = {tuple(z.get(s) for s in t.schluessel): z for z in self.zeilen(t.name)}
                    daten = dict(daten)
                    daten[t.name] = [dict(z, **{n: (alt.get(tuple(z.get(s) for s in t.schluessel)) or {}).get(n)
                                                for n in nur_programm if z.get(n) is None})
                                     for z in daten[t.name]]
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
        return kontext_aus({t: self.zeilen(t) for t in ("profile", "werkstoffe", "maschinen")}, formen)

    def tabellen(self):
        """Stammdaten, die die Rechnung braucht (Preise, Schneiddaten, Gewinde, Zusatzarbeiten)."""
        return {t: self.zeilen(t) for t in ("preise", "schneiddaten", "gewinde", "zusatzarbeiten")}

    # -------------------------------------------------------------- Aufträge
    def auftraege(self, suche=""):
        """Übersicht: Kopf, Anzahl Positionen und Teile, Zeitpunkt der Optimierung."""
        sql = ("SELECT a.id, a.nummer, a.kundennr, a.kunde, a.datum, a.maschine, a.geaendert, a.optimiert_am, "
               "COUNT(p.id) AS positionen, COALESCE(SUM(p.stueck), 0) AS teile FROM auftraege a "
               "LEFT JOIN positionen p ON p.auftrag_id = a.id")
        werte = []
        if suche:
            sql += (" WHERE a.nummer LIKE ? OR a.kunde LIKE ? OR a.kundennr LIKE ? OR a.bemerkung LIKE ? "
                    "OR a.id IN (SELECT auftrag_id FROM positionen WHERE artikel LIKE ? OR bezeichnung LIKE ?)")
            werte = [f"%{suche}%"] * 6
        sql += " GROUP BY a.id ORDER BY a.datum DESC, a.id DESC"
        return [dict(r) for r in self.con.execute(sql, werte)]

    def auftrag(self, auftrag_id):
        r = self.con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
        if r is None:
            return None
        a = dict(r)
        a["ergebnis"] = json.loads(a["ergebnis"]) if a["ergebnis"] else None
        a["staffelpreise"] = json.loads(a["staffelpreise"]) if a.get("staffelpreise") else None
        return a

    def _jetzt(self):
        return datetime.datetime.now().isoformat(timespec="seconds")

    def auftrag_neu(self, kopf=None):
        """Neuer Auftrag mit Vorgaben aus den Einstellungen; die Nummer zählt die letzte hoch."""
        kopf = dict(kopf or {})
        if not kopf.get("nummer"):
            nr = naechste_nummer(self.einstellung("letzte_auftragsnummer"))
            while self.con.execute("SELECT 1 FROM auftraege WHERE nummer=?", (nr,)).fetchone():
                nr = naechste_nummer(nr)
            kopf["nummer"] = nr
        kopf.setdefault("datum", datetime.date.today().isoformat())
        kopf.setdefault("maschine", self.einstellung("standard_maschine"))
        kopf.setdefault("stange", self.einstellung("standard_stange"))
        namen = [f.name for f in KOPF if f.name in kopf]
        try:
            with self.con:
                i = self.con.execute(
                    f'INSERT INTO auftraege ({", ".join(namen)}, angelegt, geaendert) VALUES '
                    f'({", ".join("?" * len(namen))}, ?, ?)', [kopf[n] for n in namen] + [self._jetzt()] * 2).lastrowid
                self._einstellung_schreiben("letzte_auftragsnummer", kopf["nummer"])
        except sqlite3.IntegrityError:
            raise ValueError(f"Auftragsnummer '{kopf['nummer']}' gibt es schon.")
        return i

    def auftrag_aendern(self, auftrag_id, feld, wert):
        if feld not in {f.name for f in KOPF}:
            raise KeyError(feld)
        if feld == "nummer" and not wert:
            raise ValueError("Die Auftragsnummer darf nicht leer sein.")
        try:
            with self.con:
                self.con.execute(f'UPDATE auftraege SET "{feld}"=?, geaendert=? WHERE id=?',
                                 (wert, self._jetzt(), auftrag_id))
        except sqlite3.IntegrityError:
            raise ValueError(f"Auftragsnummer '{wert}' gibt es schon.")

    def auftrag_kopieren(self, auftrag_id):
        a = self.auftrag(auftrag_id)
        kopf = {f.name: a[f.name] for f in KOPF if f.name != "nummer"}
        kopf["datum"] = datetime.date.today().isoformat()
        neu = self.auftrag_neu(kopf)
        for p in self.positionen(auftrag_id):
            self.position_neu(neu, p)
        for st in self.staffeln(auftrag_id):
            self.staffel_neu(neu, st)
        return neu

    def auftrag_loeschen(self, auftrag_id):
        with self.con:
            self.con.execute("DELETE FROM auftraege WHERE id=?", (auftrag_id,))

    def ergebnis_speichern(self, auftrag_id, ergebnis):
        with self.con:
            self.con.execute("UPDATE auftraege SET ergebnis=?, optimiert_am=? WHERE id=?",
                             (json.dumps(ergebnis, ensure_ascii=False) if ergebnis else None,
                              self._jetzt() if ergebnis else None, auftrag_id))

    def staffelpreise_speichern(self, auftrag_id, staffelpreise):
        """staffelpreise: {'zeilen': [...], 'kennung': str, 'am': Zeitpunkt} oder None"""
        with self.con:
            self.con.execute("UPDATE auftraege SET staffelpreise=? WHERE id=?",
                             (json.dumps(staffelpreise, ensure_ascii=False) if staffelpreise else None, auftrag_id))

    # -------------------------------------------------------------- Staffeln (Mengenstufen)
    def staffeln(self, auftrag_id):
        return [dict(r) for r in self.con.execute("SELECT * FROM staffeln WHERE auftrag_id=? ORDER BY nr, id",
                                                  (auftrag_id,))]

    def staffel_neu(self, auftrag_id, werte=None):
        werte = werte or {}
        nr = self.con.execute("SELECT COALESCE(MAX(nr), 0) + 1 FROM staffeln WHERE auftrag_id=?",
                              (auftrag_id,)).fetchone()[0]
        with self.con:
            return self.con.execute("INSERT INTO staffeln (auftrag_id, nr, schluessel, menge, bemerkung) VALUES "
                                    "(?, ?, ?, ?, ?)", (auftrag_id, nr, werte.get("schluessel"), werte.get("menge"),
                                                        werte.get("bemerkung"))).lastrowid

    def staffel_aendern(self, staffel_id, feld, wert):
        if feld not in ("schluessel", "menge", "bemerkung"):
            raise KeyError(feld)
        with self.con:
            self.con.execute(f'UPDATE staffeln SET "{feld}"=? WHERE id=?', (wert, staffel_id))

    def staffeln_loeschen(self, ids):
        with self.con:
            self.con.executemany("DELETE FROM staffeln WHERE id=?", [(i,) for i in ids])

    def positionen(self, auftrag_id):
        return [dict(r) for r in self.con.execute("SELECT * FROM positionen WHERE auftrag_id=? ORDER BY nr, id",
                                                  (auftrag_id,))]

    def position_neu(self, auftrag_id, werte=None):
        werte = {f.name: (werte or {}).get(f.name) for f in POSITIONEN.felder if (werte or {}).get(f.name) is not None}
        nr = self.con.execute("SELECT COALESCE(MAX(nr), 0) + 1 FROM positionen WHERE auftrag_id=?",
                              (auftrag_id,)).fetchone()[0]
        namen = ["auftrag_id", "nr"] + list(werte)
        with self.con:
            i = self.con.execute(f'INSERT INTO positionen ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                                 f'VALUES ({", ".join("?" * len(namen))})', [auftrag_id, nr] + list(werte.values())).lastrowid
            self.con.execute("UPDATE auftraege SET geaendert=? WHERE id=?", (self._jetzt(), auftrag_id))
        return i

    def position_aendern(self, position_id, feld, wert):
        POSITIONEN.feld(feld)
        with self.con:
            self.con.execute(f'UPDATE positionen SET "{feld}"=? WHERE id=?', (wert, position_id))
            self.con.execute("UPDATE auftraege SET geaendert=? WHERE id=(SELECT auftrag_id FROM positionen WHERE id=?)",
                             (self._jetzt(), position_id))

    def positionen_loeschen(self, ids):
        with self.con:
            self.con.executemany("DELETE FROM positionen WHERE id=?", [(i,) for i in ids])

    def protokoll(self, auftrag_id):
        return [json.loads(r[0]) for r in self.con.execute(
            "SELECT zeile FROM step_protokoll WHERE auftrag_id=? ORDER BY id", (auftrag_id,))]

    def protokoll_anhaengen(self, auftrag_id, zeilen):
        with self.con:
            self.con.executemany("INSERT INTO step_protokoll (auftrag_id, zeile) VALUES (?, ?)",
                                 [(auftrag_id, json.dumps(z, default=str, ensure_ascii=False)) for z in zeilen])

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
    def sicherung(self, ordner=None, behalten=SICHERUNGEN_BEHALTEN):
        """Kopie der Datendatei nach Daten/Sicherung (sqlite-Backup, auch bei offener Datei sicher).
        Ältere Sicherungen über `behalten` hinaus werden gelöscht. Ergebnis: Pfad der Sicherung."""
        ordner = Path(ordner) if ordner else self.pfad.parent / "Sicherung"
        ordner.mkdir(parents=True, exist_ok=True)
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
