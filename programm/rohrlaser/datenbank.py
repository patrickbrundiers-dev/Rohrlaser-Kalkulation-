"""Datenbank des Programms: eine SQLite-Datei mit Stammdaten und Einstellungen.

Aufträge kommen in Schritt 2 dazu. Das Schema entsteht aus stammdaten.TABELLEN; die Schemaversion
steht in PRAGMA user_version, damit spätere Versionen alte Dateien erweitern können.
"""
import datetime
import json
import sqlite3
from pathlib import Path

from .stammdaten import TABELLEN, TABELLE, EINSTELLUNGEN, EINSTELLUNG, VERWEISE, Kontext, beispieldaten

SCHEMA_VERSION = 1
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
            self.con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

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
        k = Kontext()
        k.profile = {z["profil_id"]: z for z in self.zeilen("profile") if z["profil_id"]}
        k.werkstoffe = {z["werkstoff_id"]: z for z in self.zeilen("werkstoffe") if z["werkstoff_id"]}
        k.maschinen = {z["maschinen_id"]: z for z in self.zeilen("maschinen") if z["maschinen_id"]}
        k.profilformen = tuple(s.strip() for s in self.einstellung("profilformen").splitlines() if s.strip())
        return k

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
