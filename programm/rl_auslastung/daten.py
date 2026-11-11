"""Eigene Datenbank des Programms Rohrlaser Auslastung (SQLite, eine Datei). Ohne Qt.

Tabellen: einstellungen, maschinen, auftraege, zusatzfelder, zusatzwerte. Laufzeiten stehen in ganzen Minuten, Tage als
ISO-Text. Die Datei kann in einem gemeinsamen Ordner liegen: jeder Zugriff ist eine kurze Transaktion, stand() ändert
sich, sobald ein anderer Platz geschrieben hat (das Fenster lädt dann neu).

Platz für Erweiterungen: SCHRITTE ist die Liste der Schemastände; ein neues Feld kommt als neuer Schritt dazu und wird
beim Öffnen einer älteren Datei nachgezogen, die Daten bleiben erhalten. Eigene Felder des Benutzers liegen in
zusatzfelder / zusatzwerte und brauchen keinen neuen Schritt."""
import datetime
import re
import shutil
import sqlite3
from pathlib import Path

from rohrlaser import wochen

OFFEN, LAEUFT, FERTIG = "offen", "läuft", "fertig"
STATUS = (OFFEN, LAEUFT, FERTIG)
VORGABEN = {
    "samstag_stunden": "0", "nutzungsgrad": "100", "bundesland": "Nordrhein-Westfalen", "vorlauf_tage": "2",
    "betriebsruhe": "", "laufzeit_form": "hm", "ohne_einheit": "min", "schwelle_tage": "2", "design": "Hell",
    "wochen": "8",
}
SCHRITTE = (
    # 1: Grundstand
    """
    CREATE TABLE einstellungen (schluessel TEXT PRIMARY KEY, wert TEXT);
    CREATE TABLE maschinen (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, stunden_tag REAL NOT NULL DEFAULT 8,
        aktiv INTEGER NOT NULL DEFAULT 1, reihenfolge INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE auftraege (id INTEGER PRIMARY KEY, nummer TEXT NOT NULL UNIQUE, kunde TEXT NOT NULL DEFAULT '',
        maschine TEXT NOT NULL DEFAULT '', kalk_min INTEGER NOT NULL DEFAULT 0, liefertermin TEXT,
        status TEXT NOT NULL DEFAULT 'offen', ist_min INTEGER, fertig_am TEXT, gelaufen_min INTEGER NOT NULL DEFAULT 0,
        start_am TEXT, bemerkung TEXT NOT NULL DEFAULT '', angelegt TEXT, geaendert TEXT);
    CREATE TABLE zusatzfelder (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, reihenfolge INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE zusatzwerte (auftrag_id INTEGER NOT NULL, feld_id INTEGER NOT NULL, wert TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (auftrag_id, feld_id));
    INSERT INTO maschinen (name, stunden_tag, reihenfolge) VALUES ('LT7', 8, 1), ('T03', 8, 2), ('T11', 8, 3);
    """,
    # 2: Papierkorb, Reihenfolge von Hand, Sperrtage je Maschine (Patrick 11.11.2026, P3 bis P5)
    """
    ALTER TABLE auftraege ADD COLUMN geloescht_am TEXT;
    ALTER TABLE auftraege ADD COLUMN vorrang INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE maschinen ADD COLUMN sperrtage TEXT NOT NULL DEFAULT '';
    """,
)
SCHEMA = len(SCHRITTE)
PAPIERKORB_TAGE = 30
SICHERUNGEN = 10


class Fehler(ValueError):
    """Eingabe abgelehnt; der Text ist für den Benutzer."""


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _tag(wert):
    """Datum, ISO-Text oder 31.12.2026 -> ISO-Text; leer -> None."""
    if wert is None or wert == "":
        return None
    if isinstance(wert, datetime.datetime):
        return wert.date().isoformat()
    if isinstance(wert, datetime.date):
        return wert.isoformat()
    t = str(wert).strip()
    for form in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(t, form).date().isoformat()
        except ValueError:
            continue
    raise Fehler(f"„{wert}“ ist kein Datum (z. B. 27.11.2026).")


class Daten:
    def __init__(self, pfad):
        self.pfad = Path(pfad)
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        neu = not self.pfad.exists()
        self.con = sqlite3.connect(str(self.pfad), timeout=15, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = OFF")
        stand = self.con.execute("PRAGMA user_version").fetchone()[0]
        if stand > SCHEMA:
            self.con.close()
            raise Fehler("Diese Datenbank wurde mit einer neueren Programmversion angelegt. Bitte das Programm "
                         "aktualisieren.")
        if not neu and stand < SCHEMA and stand > 0:
            self.sichern("vor-Umstellung")
        for nr in range(stand, SCHEMA):
            self.con.executescript("BEGIN;" + SCHRITTE[nr] + f"PRAGMA user_version = {nr + 1};COMMIT;")
        self.papierkorb_leeren()

    def schliessen(self):
        self.con.close()

    def stand(self):
        """Ändert sich, sobald eine andere Verbindung (ein anderer Platz) geschrieben hat."""
        return self.con.execute("PRAGMA data_version").fetchone()[0]

    def sichern(self, zusatz=None):
        """Kopie der Datei in den Ordner Sicherung daneben (eine je Tag, die letzten SICHERUNGEN bleiben)."""
        ordner = self.pfad.parent / "Sicherung"
        ordner.mkdir(exist_ok=True)
        name = f"{self.pfad.stem}-{datetime.date.today().isoformat()}{'-' + zusatz if zusatz else ''}{self.pfad.suffix}"
        ziel = ordner / name
        if not ziel.exists():
            self.con.execute("PRAGMA wal_checkpoint")
            shutil.copy2(self.pfad, ziel)
            alte = sorted(ordner.glob(f"{self.pfad.stem}-*{self.pfad.suffix}"))
            for datei in alte[:-SICHERUNGEN]:
                datei.unlink(missing_ok=True)
        return ziel

    # ------------------------------------------------------------------ Einstellungen
    def einstellung(self, schluessel, vorgabe=None):
        z = self.con.execute("SELECT wert FROM einstellungen WHERE schluessel = ?", (schluessel,)).fetchone()
        return z[0] if z is not None else VORGABEN.get(schluessel, vorgabe)

    def zahl(self, schluessel, vorgabe=0.0):
        try:
            return float(str(self.einstellung(schluessel, vorgabe)).replace(",", "."))
        except (TypeError, ValueError):
            return float(vorgabe)

    def einstellung_setzen(self, schluessel, wert):
        self.con.execute("INSERT INTO einstellungen (schluessel, wert) VALUES (?, ?) "
                         "ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert", (schluessel, str(wert)))

    # ------------------------------------------------------------------ Maschinen
    def maschinen(self, nur_aktive=False):
        return [dict(z) for z in self.con.execute(
            "SELECT * FROM maschinen " + ("WHERE aktiv = 1 " if nur_aktive else "") + "ORDER BY reihenfolge, name")]

    def maschine_speichern(self, name, stunden_tag=8.0, aktiv=True, alt=None, sperrtage=None):
        """Legt an oder ändert (alt = bisheriger Name). Umbenennen zieht die Aufträge mit. sperrtage: Text wie
        '24.11.2026-25.11.2026; 02.12.2026' (Wartung, Ausfall); None lässt sie, wie sie sind."""
        name = str(name or "").strip()
        if not name:
            raise Fehler("Die Maschine braucht einen Namen.")
        try:
            stunden = float(str(stunden_tag).replace(",", "."))
        except ValueError:
            raise Fehler("Stunden je Tag: bitte eine Zahl eingeben.") from None
        if not 0 <= stunden <= 24:
            raise Fehler("Stunden je Tag müssen zwischen 0 und 24 liegen.")
        if sperrtage is not None:
            for teil in re.split(r"[;,\n]+", str(sperrtage)):
                if teil.strip() and not wochen.betriebsruhe(teil):
                    raise Fehler(f"Sperrtage: „{teil.strip()}“ ist kein Datum. Beispiel: 24.11.2026-25.11.2026; "
                                 f"02.12.2026")
        da = {m["name"] for m in self.maschinen()}
        if name in da and name != alt:
            raise Fehler(f"Die Maschine „{name}“ gibt es schon.")
        with self.con:
            self.con.execute("BEGIN")
            if alt and alt in da:
                self.con.execute("UPDATE maschinen SET name = ?, stunden_tag = ?, aktiv = ? WHERE name = ?",
                                 (name, stunden, int(bool(aktiv)), alt))
                if sperrtage is not None:
                    self.con.execute("UPDATE maschinen SET sperrtage = ? WHERE name = ?", (str(sperrtage).strip(), name))
                if alt != name:
                    self.con.execute("UPDATE auftraege SET maschine = ? WHERE maschine = ?", (name, alt))
            else:
                n = self.con.execute("SELECT COALESCE(MAX(reihenfolge), 0) + 1 FROM maschinen").fetchone()[0]
                self.con.execute("INSERT INTO maschinen (name, stunden_tag, aktiv, reihenfolge, sperrtage) "
                                 "VALUES (?, ?, ?, ?, ?)", (name, stunden, int(bool(aktiv)), n,
                                                           str(sperrtage or "").strip()))

    def maschine_loeschen(self, name):
        n = self.con.execute("SELECT COUNT(*) FROM auftraege WHERE maschine = ? AND geloescht_am IS NULL",
                             (name,)).fetchone()[0]
        if n:
            raise Fehler(f"Auf „{name}“ liegen noch {n} Aufträge. Die Maschine lässt sich stattdessen auf „nicht "
                         "aktiv“ stellen.")
        self.con.execute("DELETE FROM maschinen WHERE name = ?", (name,))

    # ------------------------------------------------------------------ Zusatzfelder
    def zusatzfelder(self):
        return [dict(z) for z in self.con.execute("SELECT * FROM zusatzfelder ORDER BY reihenfolge, id")]

    def zusatzfeld_speichern(self, name, alt=None):
        name = str(name or "").strip()
        if not name:
            raise Fehler("Das Feld braucht einen Namen.")
        fest = {"auftragsnummer", "kunde", "maschine", "kalkulierte laufzeit", "liefertermin", "status",
                "tatsächliche laufzeit", "fertig am", "bemerkung"}
        da = {f["name"].lower(): f["name"] for f in self.zusatzfelder()}
        if name.lower() in fest or (name.lower() in da and da[name.lower()] != alt):
            raise Fehler(f"Ein Feld „{name}“ gibt es schon.")
        if alt:
            self.con.execute("UPDATE zusatzfelder SET name = ? WHERE name = ?", (name, alt))
        else:
            n = self.con.execute("SELECT COALESCE(MAX(reihenfolge), 0) + 1 FROM zusatzfelder").fetchone()[0]
            self.con.execute("INSERT INTO zusatzfelder (name, reihenfolge) VALUES (?, ?)", (name, n))

    def zusatzfeld_loeschen(self, name):
        z = self.con.execute("SELECT id FROM zusatzfelder WHERE name = ?", (name,)).fetchone()
        if z:
            with self.con:
                self.con.execute("BEGIN")
                self.con.execute("DELETE FROM zusatzwerte WHERE feld_id = ?", (z[0],))
                self.con.execute("DELETE FROM zusatzfelder WHERE id = ?", (z[0],))

    def zusatz_gefuellt(self, name):
        return self.con.execute("SELECT COUNT(*) FROM zusatzwerte w JOIN zusatzfelder f ON f.id = w.feld_id "
                                "WHERE f.name = ? AND w.wert <> ''", (name,)).fetchone()[0]

    # ------------------------------------------------------------------ Aufträge
    def _mit_zusatz(self, zeilen):
        liste = [dict(z) for z in zeilen]
        werte = {}
        for aid, name, wert in self.con.execute(
                "SELECT w.auftrag_id, f.name, w.wert FROM zusatzwerte w JOIN zusatzfelder f ON f.id = w.feld_id"):
            werte.setdefault(aid, {})[name] = wert
        for a in liste:
            a["zusatz"] = werte.get(a["id"], {})
        return liste

    def auftraege(self, status=None):
        """Alle Aufträge (status: None, ein Status oder mehrere), dringendste zuerst."""
        sql, werte = "SELECT * FROM auftraege WHERE geloescht_am IS NULL", ()
        if status:
            status = (status,) if isinstance(status, str) else tuple(status)
            sql += f" AND status IN ({','.join('?' * len(status))})"
            werte = status
        return self._mit_zusatz(self.con.execute(
            sql + " ORDER BY status = 'fertig', liefertermin IS NULL, liefertermin, nummer", werte))

    def auftrag(self, auftrag_id=None, nummer=None):
        if auftrag_id is not None:
            z = self.con.execute("SELECT * FROM auftraege WHERE id = ? AND geloescht_am IS NULL",
                                 (auftrag_id,)).fetchall()
        else:
            z = self.con.execute("SELECT * FROM auftraege WHERE nummer = ? AND geloescht_am IS NULL",
                                 (str(nummer).strip(),)).fetchall()
        return self._mit_zusatz(z)[0] if z else None

    def auftrag_speichern(self, a):
        """Legt an (ohne id) oder ändert. a: nummer, maschine, kalk_min, liefertermin, kunde, bemerkung, zusatz={Feld:
        Wert}. Ergebnis: id."""
        nummer = str(a.get("nummer") or "").strip()
        if not nummer:
            raise Fehler("Bitte eine Auftragsnummer eingeben.")
        maschine = str(a.get("maschine") or "").strip()
        if not maschine:
            raise Fehler("Bitte eine Maschine wählen.")
        try:
            kalk = int(a.get("kalk_min") or 0)
        except (TypeError, ValueError):
            raise Fehler("Die kalkulierte Laufzeit ist nicht lesbar.") from None
        if kalk <= 0:
            raise Fehler("Bitte eine kalkulierte Laufzeit über 0 eingeben.")
        termin = _tag(a.get("liefertermin"))
        doppelt = self.con.execute("SELECT id, geloescht_am FROM auftraege WHERE nummer = ?", (nummer,)).fetchone()
        if doppelt and doppelt[0] != a.get("id"):
            raise Fehler(f"Die Auftragsnummer „{nummer}“ liegt im Papierkorb. Dort zurückholen oder eine andere "
                         "Nummer wählen." if doppelt[1] else f"Die Auftragsnummer „{nummer}“ gibt es schon.")
        with self.con:
            self.con.execute("BEGIN")
            if maschine not in {m["name"] for m in self.maschinen()}:
                n = self.con.execute("SELECT COALESCE(MAX(reihenfolge), 0) + 1 FROM maschinen").fetchone()[0]
                self.con.execute("INSERT INTO maschinen (name, reihenfolge) VALUES (?, ?)", (maschine, n))
            werte = (nummer, str(a.get("kunde") or "").strip(), maschine, kalk, termin,
                     str(a.get("bemerkung") or "").strip(), _jetzt())
            if a.get("id"):
                self.con.execute("UPDATE auftraege SET nummer = ?, kunde = ?, maschine = ?, kalk_min = ?, "
                                 "liefertermin = ?, bemerkung = ?, geaendert = ? WHERE id = ?", werte + (a["id"],))
                aid = a["id"]
            else:
                aid = self.con.execute(
                    "INSERT INTO auftraege (nummer, kunde, maschine, kalk_min, liefertermin, bemerkung, geaendert, "
                    "angelegt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", werte + (_jetzt(),)).lastrowid
            if "zusatz" in a:
                felder = {f["name"]: f["id"] for f in self.zusatzfelder()}
                for name, wert in (a.get("zusatz") or {}).items():
                    if name in felder:
                        self.con.execute("INSERT INTO zusatzwerte (auftrag_id, feld_id, wert) VALUES (?, ?, ?) "
                                         "ON CONFLICT(auftrag_id, feld_id) DO UPDATE SET wert = excluded.wert",
                                         (aid, felder[name], str(wert or "").strip()))
        return aid

    def auftrag_loeschen(self, auftrag_id, jetzt=None):
        """In den Papierkorb legen (P3); nach PAPIERKORB_TAGE Tagen räumt papierkorb_leeren() endgültig auf."""
        jetzt = (jetzt or datetime.datetime.now()).isoformat(timespec="seconds")
        self.con.execute("UPDATE auftraege SET geloescht_am = ?, start_am = NULL WHERE id = ?", (jetzt, auftrag_id))

    def papierkorb(self):
        """Gelöschte Aufträge, zuletzt gelöschte zuerst."""
        return self._mit_zusatz(self.con.execute(
            "SELECT * FROM auftraege WHERE geloescht_am IS NOT NULL ORDER BY geloescht_am DESC, nummer"))

    def im_papierkorb(self, nummer):
        return self.con.execute("SELECT 1 FROM auftraege WHERE nummer = ? AND geloescht_am IS NOT NULL",
                                (str(nummer).strip(),)).fetchone() is not None

    def zurueckholen(self, auftrag_id):
        self.con.execute("UPDATE auftraege SET geloescht_am = NULL, geaendert = ? WHERE id = ?", (_jetzt(), auftrag_id))

    def papierkorb_leeren(self, heute=None, alle=False):
        """Endgültig löschen, was länger als PAPIERKORB_TAGE im Papierkorb liegt (alle=True: alles). Ergebnis: Anzahl."""
        grenze = "9999" if alle else ((heute or datetime.date.today())
                                       - datetime.timedelta(days=PAPIERKORB_TAGE)).isoformat()
        ids = [z[0] for z in self.con.execute(
            "SELECT id FROM auftraege WHERE geloescht_am IS NOT NULL AND geloescht_am < ?", (grenze,))]
        if ids:
            with self.con:
                self.con.execute("BEGIN")
                for i in ids:
                    self.con.execute("DELETE FROM zusatzwerte WHERE auftrag_id = ?", (i,))
                    self.con.execute("DELETE FROM auftraege WHERE id = ?", (i,))
        return len(ids)

    def vorrang_setzen(self, auftrag_id, richtung):
        """Reihenfolge von Hand (P4): richtung +1 = vorziehen (läuft auf seiner Maschine als Nächstes), -1 =
        zurückstellen (läuft dort zuletzt), 0 = wieder nach Liefertermin."""
        a = self.auftrag(auftrag_id)
        if a is None:
            return
        if richtung == 0:
            neu = 0
        else:
            werte = [z[0] for z in self.con.execute(
                "SELECT vorrang FROM auftraege WHERE maschine = ? AND status <> ? AND geloescht_am IS NULL AND id <> ?",
                (a["maschine"], FERTIG, auftrag_id))] + [0]
            neu = max(werte) + 1 if richtung > 0 else min(werte) - 1
        self.con.execute("UPDATE auftraege SET vorrang = ?, geaendert = ? WHERE id = ?", (neu, _jetzt(), auftrag_id))

    def starten(self, auftrag_id, jetzt=None):
        """Start-Knopf: die Uhr läuft, Status „läuft“."""
        a = self.auftrag(auftrag_id)
        if a is None or a["status"] == FERTIG:
            raise Fehler("Ein fertiger Auftrag lässt sich nicht starten.")
        if a["start_am"]:
            return
        jetzt = jetzt or datetime.datetime.now()
        self.con.execute("UPDATE auftraege SET status = ?, start_am = ?, geaendert = ? WHERE id = ?",
                         (LAEUFT, jetzt.isoformat(timespec="seconds"), _jetzt(), auftrag_id))

    def stoppen(self, auftrag_id, jetzt=None):
        """Stopp-Knopf: die Zeit seit dem Start kommt zur gelaufenen Zeit dazu. Ergebnis: gelaufene Minuten."""
        a = self.auftrag(auftrag_id)
        if a is None:
            return 0
        gelaufen = self.gelaufen(a, jetzt)
        self.con.execute("UPDATE auftraege SET gelaufen_min = ?, start_am = NULL, geaendert = ? WHERE id = ?",
                         (gelaufen, _jetzt(), auftrag_id))
        return gelaufen

    @staticmethod
    def gelaufen(a, jetzt=None):
        """Gelaufene Minuten eines Auftrags einschließlich der gerade laufenden Uhr."""
        n = int(a.get("gelaufen_min") or 0)
        if a.get("start_am"):
            jetzt = jetzt or datetime.datetime.now()
            try:
                n += max(0, int((jetzt - datetime.datetime.fromisoformat(a["start_am"])).total_seconds() / 60 + 0.5))
            except (TypeError, ValueError):
                pass
        return n

    def fertig_melden(self, auftrag_id, ist_min, fertig_am=None):
        """Fertigmeldung mit der tatsächlichen Laufzeit in Minuten."""
        try:
            ist = int(ist_min)
        except (TypeError, ValueError):
            raise Fehler("Bitte die tatsächliche Laufzeit eingeben.") from None
        if ist <= 0:
            raise Fehler("Bitte eine tatsächliche Laufzeit über 0 eingeben.")
        tag = _tag(fertig_am) or datetime.date.today().isoformat()
        self.con.execute("UPDATE auftraege SET status = ?, ist_min = ?, fertig_am = ?, start_am = NULL, vorrang = 0, "
                         "geaendert = ? WHERE id = ?", (FERTIG, ist, tag, _jetzt(), auftrag_id))

    def wieder_oeffnen(self, auftrag_id):
        """Fertigmeldung zurücknehmen; die tatsächliche Laufzeit bleibt als gelaufene Zeit stehen."""
        a = self.auftrag(auftrag_id)
        if a and a["status"] == FERTIG:
            self.con.execute("UPDATE auftraege SET status = ?, gelaufen_min = ?, ist_min = NULL, fertig_am = NULL, "
                             "geaendert = ? WHERE id = ?", (OFFEN, int(a["ist_min"] or 0), _jetzt(), auftrag_id))
