"""Eigene Datenbank des Programms Rohrlaser Auslastung (SQLite, eine Datei). Ohne Qt.

Tabellen: einstellungen, maschinen, auftraege, zusatzfelder, zusatzwerte. Laufzeiten stehen in ganzen Minuten, Tage als
ISO-Text. Die Datei kann in einem gemeinsamen Ordner liegen: jeder Zugriff ist eine kurze Transaktion, stand() ändert
sich, sobald ein anderer Platz geschrieben hat (das Fenster lädt dann neu).

Platz für Erweiterungen: SCHRITTE ist die Liste der Schemastände; ein neues Feld kommt als neuer Schritt dazu und wird
beim Öffnen einer älteren Datei nachgezogen, die Daten bleiben erhalten. Eigene Felder des Benutzers liegen in
zusatzfelder / zusatzwerte und brauchen keinen neuen Schritt."""
import datetime
import getpass
import json
import os
import re
import shutil
import sqlite3
from pathlib import Path

from rohrlaser import wochen

OFFEN, LAEUFT, FERTIG = "offen", "läuft", "fertig"
STATUS = (OFFEN, LAEUFT, FERTIG)
VORGABEN = {
    "samstag_stunden": "0", "nutzungsgrad": "100", "bundesland": "Nordrhein-Westfalen", "vorlauf_tage": "2",
    "rolle_vorgabe": "lesen", "arbeitsgaenge": "0", "stopp_fragen": "1",
    "stoppgruende": "Störung; Material fehlt; Rüsten; Pause; anderer Auftrag",
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
    # 3: Benutzerrechte und Änderungsverlauf (Patrick 11.11.2026, Plan B1a bis B4a)
    """
    CREATE TABLE benutzer (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, rolle TEXT NOT NULL DEFAULT 'lesen');
    CREATE TABLE verlauf (id INTEGER PRIMARY KEY, auftrag_id INTEGER NOT NULL, wann TEXT NOT NULL,
        wer TEXT NOT NULL DEFAULT '', was TEXT NOT NULL DEFAULT '');
    CREATE INDEX verlauf_auftrag ON verlauf (auftrag_id, id);
    """,
    # 4: Arbeitsgänge und Auftrag auf mehreren Maschinen (Patrick 11.11.2026, Plan A1a bis A4a). Ein Auftrag mit
    # Zeilen in gaenge ist mehrteilig: die Zeilen sind maßgeblich, Maschine, Laufzeit und Status des Auftrags werden
    # daraus zusammengefasst. platz leer = Fremdarbeit (nur Dauer in Arbeitstagen, keine Kapazität).
    """
    ALTER TABLE maschinen ADD COLUMN uebergang_tage INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE gaenge (id INTEGER PRIMARY KEY, auftrag_id INTEGER NOT NULL, pos INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL DEFAULT '', platz TEXT NOT NULL DEFAULT '', kalk_min INTEGER NOT NULL DEFAULT 0,
        tage INTEGER NOT NULL DEFAULT 0, gleichzeitig INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'offen',
        ist_min INTEGER, fertig_am TEXT, gelaufen_min INTEGER NOT NULL DEFAULT 0, start_am TEXT);
    CREATE INDEX gaenge_auftrag ON gaenge (auftrag_id, pos);
    CREATE TABLE vorlagen (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, gaenge TEXT NOT NULL DEFAULT '[]');
    """,
    # 5: Planen wie an einer Plantafel (Patrick 11.11.2026, Erweiterungsplan E1 bis E3): fester Platz eines Auftrags
    # (fest_ab = Tag, vor dem er nicht beginnt; er wird vor allen anderen eingelastet), Ausweichmaschinen.
    # Zusatzstunden je Maschine und Woche stehen als JSON in der Einstellung zusatzstunden.
    """
    ALTER TABLE auftraege ADD COLUMN fest_ab TEXT;
    ALTER TABLE maschinen ADD COLUMN ausweich INTEGER NOT NULL DEFAULT 1;
    """,
    # 6: Grund bei Stopp (Erweiterungsplan E6): jede Unterbrechung mit Grund; weiter_am kommt beim nächsten Start.
    """
    CREATE TABLE stopps (id INTEGER PRIMARY KEY, auftrag_id INTEGER NOT NULL, gang_id INTEGER, maschine TEXT NOT NULL
        DEFAULT '', wann TEXT NOT NULL, weiter_am TEXT, wer TEXT NOT NULL DEFAULT '', grund TEXT NOT NULL DEFAULT '');
    CREATE INDEX stopps_auftrag ON stopps (auftrag_id, id);
    """,
)
FREMD = ""                     # Arbeitsplatz eines Arbeitsgangs außer Haus
FREMD_TEXT = "Fremdarbeit"
SCHEMA = len(SCHRITTE)
# Benutzerrechte: vier feste Rollen. Rechte: einstellungen (Einstellungen, Benutzer), auftraege (anlegen, ändern,
# löschen, Reihenfolge, CSV einlesen, Papierkorb), melden (Start, Stopp, fertig melden, wieder öffnen). Ansehen,
# Terminauskunft und Drucken darf jeder. Die Rechte gelten im Programm; wer die Datei mit einem anderen Werkzeug
# öffnet, umgeht sie (Schutz gegen Versehen, nicht gegen Absicht).
VERWALTUNG, PLANUNG, WERKSTATT, LESEN = "verwaltung", "planung", "werkstatt", "lesen"
ROLLEN = ((VERWALTUNG, "Verwaltung"), (PLANUNG, "Planung"), (WERKSTATT, "Werkstatt"), (LESEN, "Nur lesen"))
RECHTE = {VERWALTUNG: {"einstellungen", "auftraege", "melden"}, PLANUNG: {"auftraege", "melden"},
          WERKSTATT: {"melden"}, LESEN: set()}
ROLLE_TEXT = dict(ROLLEN)


def anmeldename():
    """Windows-Anmeldename des Platzes (klein geschrieben); RLA_BENUTZER überschreibt ihn (Tests, Sonderfälle)."""
    name = os.environ.get("RLA_BENUTZER")
    if not name:
        try:
            name = getpass.getuser()
        except Exception:                         # kein Benutzer ermittelbar (sehr eingeschränkte Umgebung)
            name = ""
    return str(name or "").strip().lower()
PAPIERKORB_TAGE = 30
SICHERUNGEN = 10


class Fehler(ValueError):
    """Eingabe abgelehnt; der Text ist für den Benutzer."""


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _zeigen(feld, wert):
    """Wert für den Änderungsverlauf."""
    if feld == "Kalkulierte Laufzeit":
        m = int(wert or 0)
        return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"
    if feld == "Liefertermin" and wert:
        try:
            return datetime.date.fromisoformat(str(wert)).strftime("%d.%m.%Y")
        except ValueError:
            return str(wert)
    return str(wert) if wert not in (None, "") else "leer"


def _plaetze_text(gaenge):
    """Arbeitsplätze eines mehrteiligen Auftrags als ein Text: nacheinander mit →, gleichzeitig mit +."""
    stufen = []
    for g in gaenge:
        platz = g["platz"] or FREMD_TEXT
        if g.get("gleichzeitig") and stufen:
            if platz not in stufen[-1]:
                stufen[-1].append(platz)
        else:
            stufen.append([platz])
    return " → ".join(" + ".join(s) for s in stufen)


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
    def __init__(self, pfad, wer=None):
        self.pfad = Path(pfad)
        self.wer = anmeldename() if wer is None else str(wer).strip().lower()
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

    def maschine_speichern(self, name, stunden_tag=8.0, aktiv=True, alt=None, sperrtage=None, uebergang=None,
                           ausweich=None):
        """Legt an oder ändert (alt = bisheriger Name). Umbenennen zieht die Aufträge mit. sperrtage: Text wie
        '24.11.2026-25.11.2026; 02.12.2026' (Wartung, Ausfall); None lässt sie, wie sie sind. uebergang: Arbeitstage
        zwischen dem Arbeitsgang davor und dem Beginn an diesem Arbeitsplatz (Transport, Abkühlen); None lässt sie.
        ausweich: kann Aufträge anderer Maschinen übernehmen (Vorschlag Ausweichmaschine); None lässt es."""
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
        if name.lower() == FREMD_TEXT.lower() or " + " in name or " → " in name:
            raise Fehler(f"„{name}“ geht nicht als Name (Fremdarbeit, „ + “ und „ → “ sind vergeben).")
        if uebergang is not None:
            try:
                uebergang = int(uebergang)
            except (TypeError, ValueError):
                raise Fehler("Übergangszeit: bitte ganze Arbeitstage eingeben.") from None
            if not 0 <= uebergang <= 60:
                raise Fehler("Die Übergangszeit muss zwischen 0 und 60 Arbeitstagen liegen.")
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
                    betroffen = [z[0] for z in self.con.execute(
                        "SELECT DISTINCT auftrag_id FROM gaenge WHERE platz = ?", (alt,))]
                    self.con.execute("UPDATE gaenge SET platz = ? WHERE platz = ?", (name, alt))
                    for aid in betroffen:
                        self._abgleichen(aid)
            else:
                n = self.con.execute("SELECT COALESCE(MAX(reihenfolge), 0) + 1 FROM maschinen").fetchone()[0]
                self.con.execute("INSERT INTO maschinen (name, stunden_tag, aktiv, reihenfolge, sperrtage) "
                                 "VALUES (?, ?, ?, ?, ?)", (name, stunden, int(bool(aktiv)), n,
                                                           str(sperrtage or "").strip()))
            if uebergang is not None:
                self.con.execute("UPDATE maschinen SET uebergang_tage = ? WHERE name = ?", (uebergang, name))
            if ausweich is not None:
                self.con.execute("UPDATE maschinen SET ausweich = ? WHERE name = ?", (int(bool(ausweich)), name))

    def maschine_loeschen(self, name):
        n = self.con.execute(
            "SELECT COUNT(*) FROM auftraege a WHERE a.geloescht_am IS NULL AND (a.maschine = ? OR EXISTS "
            "(SELECT 1 FROM gaenge g WHERE g.auftrag_id = a.id AND g.platz = ?))", (name, name)).fetchone()[0]
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
        gaenge = self.alle_gaenge() if liste else {}
        for a in liste:
            a["zusatz"] = werte.get(a["id"], {})
            a["gaenge"] = gaenge.get(a["id"], [])
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
        Wert}. Ergebnis: id.

        Mit a["gaenge"] = [dict(name, platz, kalk_min, tage, gleichzeitig[, id])] wird der Auftrag mehrteilig
        (Arbeitsgänge oder Teile auf mehreren Maschinen); Maschine und Laufzeit ergeben sich dann aus den Zeilen. Eine
        leere Liste macht ihn wieder einteilig. Fehlt der Schlüssel, bleiben vorhandene Arbeitsgänge, wie sie sind."""
        nummer = str(a.get("nummer") or "").strip()
        if not nummer:
            raise Fehler("Bitte eine Auftragsnummer eingeben.")
        vorher = self.gaenge(a["id"]) if a.get("id") else []
        gaenge = self._gaenge_pruefen(a["gaenge"]) if "gaenge" in a else None
        mehrteilig = bool(gaenge) if gaenge is not None else bool(vorher)
        if mehrteilig:
            maschine, kalk = _plaetze_text(gaenge or vorher), sum(g["kalk_min"] for g in (gaenge or vorher))
        else:
            maschine = str(a.get("maschine") or "").strip()
            if not maschine or " + " in maschine or " → " in maschine:
                raise Fehler("Bitte eine Maschine wählen." if not maschine else
                             "Mehrere Maschinen oder Arbeitsgänge bitte im Auftrag als eigene Zeilen anlegen.")
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
            da = {m["name"] for m in self.maschinen()}
            for platz in ([g["platz"] for g in (gaenge or vorher)] if mehrteilig else [maschine]):
                if platz != FREMD and platz not in da:
                    n = self.con.execute("SELECT COALESCE(MAX(reihenfolge), 0) + 1 FROM maschinen").fetchone()[0]
                    self.con.execute("INSERT INTO maschinen (name, reihenfolge) VALUES (?, ?)", (platz, n))
                    da.add(platz)
            werte = (nummer, str(a.get("kunde") or "").strip(), maschine, kalk, termin,
                     str(a.get("bemerkung") or "").strip(), _jetzt())
            if a.get("id"):
                alt = self.con.execute("SELECT nummer, kunde, maschine, kalk_min, liefertermin, bemerkung FROM "
                                       "auftraege WHERE id = ?", (a["id"],)).fetchone()
                self.con.execute("UPDATE auftraege SET nummer = ?, kunde = ?, maschine = ?, kalk_min = ?, "
                                 "liefertermin = ?, bemerkung = ?, geaendert = ? WHERE id = ?", werte + (a["id"],))
                aid = a["id"]
                namen = ("Auftragsnummer", "Kunde", "Maschine", "Kalkulierte Laufzeit", "Liefertermin", "Bemerkung")
                anders = [f"{n}: {_zeigen(n, v)} → {_zeigen(n, w)}" for n, v, w in zip(namen, alt or (), werte)
                          if (v or "") != (w or "")]
                if anders:
                    self._verlauf(aid, "geändert (" + "; ".join(anders) + ")")
            else:
                aid = self.con.execute(
                    "INSERT INTO auftraege (nummer, kunde, maschine, kalk_min, liefertermin, bemerkung, geaendert, "
                    "angelegt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", werte + (_jetzt(),)).lastrowid
                self._verlauf(aid, f"angelegt ({maschine}, {_zeigen('Kalkulierte Laufzeit', kalk)})")
            if gaenge is not None:
                self._gaenge_schreiben(aid, gaenge, vorher)
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
        self.con.execute("UPDATE gaenge SET start_am = NULL WHERE auftrag_id = ? AND platz <> ''", (auftrag_id,))
        self._verlauf(auftrag_id, "in den Papierkorb gelegt")

    def papierkorb(self):
        """Gelöschte Aufträge, zuletzt gelöschte zuerst."""
        return self._mit_zusatz(self.con.execute(
            "SELECT * FROM auftraege WHERE geloescht_am IS NOT NULL ORDER BY geloescht_am DESC, nummer"))

    def im_papierkorb(self, nummer):
        return self.con.execute("SELECT 1 FROM auftraege WHERE nummer = ? AND geloescht_am IS NOT NULL",
                                (str(nummer).strip(),)).fetchone() is not None

    def zurueckholen(self, auftrag_id):
        self.con.execute("UPDATE auftraege SET geloescht_am = NULL, geaendert = ? WHERE id = ?", (_jetzt(), auftrag_id))
        self._verlauf(auftrag_id, "aus dem Papierkorb zurückgeholt")

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
                    self.con.execute("DELETE FROM verlauf WHERE auftrag_id = ?", (i,))
                    self.con.execute("DELETE FROM gaenge WHERE auftrag_id = ?", (i,))
                    self.con.execute("DELETE FROM stopps WHERE auftrag_id = ?", (i,))
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
                "SELECT vorrang FROM auftraege WHERE status <> ? AND geloescht_am IS NULL AND id <> ?",
                (FERTIG, auftrag_id))] + [0]
            neu = max(werte) + 1 if richtung > 0 else min(werte) - 1
        self.con.execute("UPDATE auftraege SET vorrang = ?, geaendert = ? WHERE id = ?", (neu, _jetzt(), auftrag_id))
        self._verlauf(auftrag_id, "Reihenfolge: " + ("wieder nach Liefertermin" if not neu else
                                                     "vorgezogen" if neu > 0 else "zurückgestellt"))

    def festlegen(self, auftrag_id, tag, maschine=None, gang_id=None):
        """Fester Platz (E1): Der Auftrag beginnt nicht vor tag und wird vor allen anderen eingelastet, die sich
        weiter nach Liefertermin ordnen. maschine: zugleich auf diese Maschine legen (bei einem mehrteiligen Auftrag
        die Zeile gang_id). Ergebnis: der Stand davor für „Rückgängig“ (für zuruecksetzen)."""
        a = self.auftrag(auftrag_id)
        if a is None or a["status"] == FERTIG:
            raise Fehler("Ein fertiger Auftrag lässt sich nicht verschieben.")
        tag = _tag(tag)
        g = next((x for x in a["gaenge"] if x["id"] == gang_id), None)
        davor = dict(id=auftrag_id, fest_ab=a["fest_ab"], maschine=g["platz"] if g else a["maschine"], gang_id=gang_id)
        with self.con:
            self.con.execute("BEGIN")
            self._maschine_wechseln(a, g, maschine)
            self.con.execute("UPDATE auftraege SET fest_ab = ?, geaendert = ? WHERE id = ?", (tag, _jetzt(), auftrag_id))
            wo = maschine or davor["maschine"]
            self._verlauf(auftrag_id, f"in der Plantafel verschoben: fest ab {_zeigen('Liefertermin', tag)}"
                          + (f" auf {wo}" if wo != davor["maschine"] else ""))
        return davor

    def _maschine_wechseln(self, a, g, maschine):
        if not maschine or maschine == (g["platz"] if g else a["maschine"]):
            return
        if maschine not in {m["name"] for m in self.maschinen()}:
            raise Fehler(f"Die Maschine „{maschine}“ gibt es nicht.")
        if g is not None:
            if g["status"] == FERTIG or g["platz"] == FREMD:
                raise Fehler("Diese Zeile lässt sich nicht auf eine andere Maschine legen.")
            self.con.execute("UPDATE gaenge SET platz = ? WHERE id = ?", (maschine, g["id"]))
            self._abgleichen(a["id"])
        elif a["gaenge"]:
            raise Fehler("Bei einem Auftrag mit mehreren Zeilen bitte die einzelne Zeile verschieben.")
        else:
            self.con.execute("UPDATE auftraege SET maschine = ? WHERE id = ?", (maschine, a["id"]))

    def maschine_wechseln(self, auftrag_id, maschine):
        """Auftrag auf eine andere Maschine legen (Vorschlag Ausweichmaschine, Was-wäre-wenn übernehmen)."""
        a = self.auftrag(auftrag_id)
        if a is None or a["status"] == FERTIG or maschine == a["maschine"]:
            return
        with self.con:
            self.con.execute("BEGIN")
            self._maschine_wechseln(a, None, maschine)
            self.con.execute("UPDATE auftraege SET geaendert = ? WHERE id = ?", (_jetzt(), auftrag_id))
            self._verlauf(auftrag_id, f"geändert (Maschine: {a['maschine']} → {maschine})")

    def zuruecksetzen(self, davor):
        """Rückgängig für festlegen(): Platz und Maschine wie davor."""
        a = self.auftrag(davor["id"])
        if a is None:
            return
        g = next((x for x in a["gaenge"] if x["id"] == davor.get("gang_id")), None)
        with self.con:
            self.con.execute("BEGIN")
            self._maschine_wechseln(a, g, davor["maschine"])
            self.con.execute("UPDATE auftraege SET fest_ab = ?, geaendert = ? WHERE id = ?",
                             (davor["fest_ab"], _jetzt(), davor["id"]))
            self._verlauf(davor["id"], "Verschieben rückgängig gemacht")

    def loesen(self, auftrag_id):
        """Festen Platz lösen: Der Auftrag ordnet sich wieder nach Liefertermin ein."""
        a = self.auftrag(auftrag_id)
        if a and a["fest_ab"]:
            self.con.execute("UPDATE auftraege SET fest_ab = NULL, geaendert = ? WHERE id = ?", (_jetzt(), auftrag_id))
            self._verlauf(auftrag_id, "fester Platz gelöst")

    def zusatzstunden(self, ab=None):
        """Zusatzstunden je Maschine und Woche: {(Maschine, Montag): Stunden}; ab = nur Wochen ab diesem Montag."""
        try:
            roh = json.loads(self.einstellung("zusatzstunden") or "[]")
        except ValueError:
            roh = []
        out = {}
        for z in roh:
            try:
                montag, h = datetime.date.fromisoformat(z[1]), float(z[2])
            except (TypeError, ValueError, IndexError):
                continue
            if h > 0 and (ab is None or montag >= ab):
                out[(str(z[0]), montag)] = h
        return out

    def zusatzstunden_setzen(self, werte):
        self.einstellung_setzen("zusatzstunden", json.dumps(
            [[m, mo.isoformat(), float(h)] for (m, mo), h in sorted(werte.items()) if h and float(h) > 0]))

    def starten(self, auftrag_id, jetzt=None, gang_id=None):
        """Start-Knopf: die Uhr läuft, Status „läuft“. Bei einem mehrteiligen Auftrag startet der Arbeitsgang gang_id
        (Vorgabe: der nächste, der an der Reihe ist)."""
        a = self.auftrag(auftrag_id)
        if a is None or a["status"] == FERTIG:
            raise Fehler("Ein fertiger Auftrag lässt sich nicht starten.")
        jetzt = jetzt or datetime.datetime.now()
        if a["gaenge"]:
            g = self._gang(a, gang_id, lambda x: not x["start_am"])
            if not g["start_am"]:
                self._weiter(auftrag_id, g["id"], jetzt)
                self.con.execute("UPDATE gaenge SET start_am = ? WHERE id = ?",
                                 (jetzt.isoformat(timespec="seconds"), g["id"]))
                self._abgleichen(auftrag_id)
                self._verlauf(auftrag_id, f"{g['name']}: gestartet")
            return
        if a["start_am"]:
            return
        self._weiter(auftrag_id, None, jetzt)
        self.con.execute("UPDATE auftraege SET status = ?, start_am = ?, geaendert = ? WHERE id = ?",
                         (LAEUFT, jetzt.isoformat(timespec="seconds"), _jetzt(), auftrag_id))
        self._verlauf(auftrag_id, "gestartet")

    def stoppen(self, auftrag_id, jetzt=None, gang_id=None, grund=None):
        """Stopp-Knopf: die Zeit seit dem Start kommt zur gelaufenen Zeit dazu. Ergebnis: gelaufene Minuten.
        grund: Grund der Unterbrechung (E6); mit Grund wird die Unterbrechung für die Auswertung aufgezeichnet."""
        a = self.auftrag(auftrag_id)
        if a is None:
            return 0
        if a["gaenge"]:
            laufend = [g for g in a["gaenge"] if g["start_am"] and (gang_id is None or g["id"] == gang_id)]
            n = 0
            for g in laufend:
                n = self.gelaufen(g, jetzt) if g["platz"] != FREMD else 0
                self.con.execute("UPDATE gaenge SET gelaufen_min = ?, start_am = NULL WHERE id = ?", (n, g["id"]))
                self._verlauf(auftrag_id, f"{g['name']}: gestoppt"
                              + (f" (gelaufen {_zeigen('Kalkulierte Laufzeit', n)})" if g["platz"] != FREMD else "")
                              + (f", Grund: {grund}" if grund else ""))
                if g["platz"] != FREMD:
                    self._stopp(auftrag_id, g["id"], g["platz"], jetzt, grund)
            if laufend:
                self._abgleichen(auftrag_id)
            return n
        gelaufen = self.gelaufen(a, jetzt)
        self.con.execute("UPDATE auftraege SET gelaufen_min = ?, start_am = NULL, geaendert = ? WHERE id = ?",
                         (gelaufen, _jetzt(), auftrag_id))
        if a["start_am"]:
            self._verlauf(auftrag_id, f"gestoppt (gelaufen {_zeigen('Kalkulierte Laufzeit', gelaufen)})"
                          + (f", Grund: {grund}" if grund else ""))
            self._stopp(auftrag_id, None, a["maschine"], jetzt, grund)
        return gelaufen

    def _stopp(self, auftrag_id, gang_id, maschine, jetzt, grund):
        if grund:
            self.con.execute("INSERT INTO stopps (auftrag_id, gang_id, maschine, wann, wer, grund) VALUES "
                             "(?, ?, ?, ?, ?, ?)", (auftrag_id, gang_id, maschine, (jetzt or datetime.datetime.now())
                                                    .isoformat(timespec="seconds"), self.wer, str(grund).strip()))

    def _weiter(self, auftrag_id, gang_id, jetzt):
        """Beim Start: die offene Unterbrechung dieser Zeile ist zu Ende."""
        self.con.execute("UPDATE stopps SET weiter_am = ? WHERE auftrag_id = ? AND gang_id IS ? AND weiter_am IS NULL",
                         (jetzt.isoformat(timespec="seconds"), auftrag_id, gang_id))

    def offener_stopp(self, auftrag_id, gang_id=None):
        """Grund der Unterbrechung, die gerade andauert ('' = keine oder ohne Grund gestoppt)."""
        z = self.con.execute("SELECT grund FROM stopps WHERE auftrag_id = ? AND gang_id IS ? AND weiter_am IS NULL "
                             "ORDER BY id DESC LIMIT 1", (auftrag_id, gang_id)).fetchone()
        return z["grund"] if z else ""

    def stoppgruende(self):
        return [g.strip() for g in re.split(r"[;\n]+", self.einstellung("stoppgruende") or "") if g.strip()]

    def stopps(self, von=None, bis=None):
        """Aufgezeichnete Unterbrechungen im Zeitraum (nach Tag des Stopps), neueste zuerst."""
        out = []
        for z in self.con.execute("SELECT s.*, a.nummer FROM stopps s JOIN auftraege a ON a.id = s.auftrag_id "
                                  "ORDER BY s.id DESC"):
            tag = datetime.date.fromisoformat(z["wann"][:10])
            if (von and tag < von) or (bis and tag > bis):
                continue
            out.append(dict(z))
        return out

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

    def fertig_melden(self, auftrag_id, ist_min, fertig_am=None, gang_id=None):
        """Fertigmeldung mit der tatsächlichen Laufzeit in Minuten. Bei einem mehrteiligen Auftrag wird der
        Arbeitsgang gang_id gemeldet (Vorgabe: der nächste, der an der Reihe ist); mit dem letzten ist der Auftrag
        fertig. Fremdarbeit braucht keine Laufzeit."""
        a = self.auftrag(auftrag_id)
        g = self._gang(a, gang_id) if a and a["gaenge"] else None
        try:
            ist = int(ist_min or 0) if g is not None and g["platz"] == FREMD else int(ist_min)
        except (TypeError, ValueError):
            raise Fehler("Bitte die tatsächliche Laufzeit eingeben.") from None
        if ist <= 0 and not (g is not None and g["platz"] == FREMD):
            raise Fehler("Bitte eine tatsächliche Laufzeit über 0 eingeben.")
        tag = _tag(fertig_am) or datetime.date.today().isoformat()
        if g is not None:
            self.con.execute("UPDATE gaenge SET status = ?, ist_min = ?, fertig_am = ?, start_am = NULL WHERE id = ?",
                             (FERTIG, max(0, ist), tag, g["id"]))
            self._abgleichen(auftrag_id)
            self._verlauf(auftrag_id, f"{g['name']}: fertig gemeldet" + (
                f" (tatsächlich {_zeigen('Kalkulierte Laufzeit', ist)})" if g["platz"] != FREMD else ""))
            return
        self.con.execute("UPDATE auftraege SET status = ?, ist_min = ?, fertig_am = ?, start_am = NULL, vorrang = 0, "
                         "fest_ab = NULL, "
                         "geaendert = ? WHERE id = ?", (FERTIG, ist, tag, _jetzt(), auftrag_id))
        self._verlauf(auftrag_id, f"fertig gemeldet (tatsächlich {_zeigen('Kalkulierte Laufzeit', ist)})")

    def wieder_oeffnen(self, auftrag_id):
        """Fertigmeldung zurücknehmen; die tatsächliche Laufzeit bleibt als gelaufene Zeit stehen."""
        a = self.auftrag(auftrag_id)
        if a and a["gaenge"]:                     # mehrteilig: der zuletzt gemeldete Arbeitsgang ist wieder offen
            fertige = [g for g in a["gaenge"] if g["status"] == FERTIG]
            if fertige and not any(g["status"] != FERTIG and (g["start_am"] or g["gelaufen_min"])
                                   for g in a["gaenge"] if g["stufe"] > fertige[-1]["stufe"]):
                g = fertige[-1]
                self.con.execute("UPDATE gaenge SET status = ?, gelaufen_min = ?, ist_min = NULL, fertig_am = NULL "
                                 "WHERE id = ?", (OFFEN, int(g["ist_min"] or 0), g["id"]))
                self._abgleichen(auftrag_id)
                self._verlauf(auftrag_id, f"{g['name']}: wieder geöffnet")
            return
        if a and a["status"] == FERTIG:
            self.con.execute("UPDATE auftraege SET status = ?, gelaufen_min = ?, ist_min = NULL, fertig_am = NULL, "
                             "geaendert = ? WHERE id = ?", (OFFEN, int(a["ist_min"] or 0), _jetzt(), auftrag_id))
            self._verlauf(auftrag_id, "wieder geöffnet")

    # ------------------------------------------------------------------ Arbeitsgänge und Teile auf mehreren Maschinen
    def mit_gaengen(self):
        """Schalter in den Einstellungen: mehrere Arbeitsgänge je Auftrag verwenden (Vorgabe aus)."""
        return self.einstellung("arbeitsgaenge") == "1"

    def alle_gaenge(self):
        """{Auftrag-ID: [Arbeitsgang …]} in der Reihenfolge des Auftrags; jeder mit stufe (Zeilen, die gleichzeitig
        laufen, teilen eine Stufe)."""
        out = {}
        for z in self.con.execute("SELECT * FROM gaenge ORDER BY auftrag_id, pos, id"):
            liste = out.setdefault(z["auftrag_id"], [])
            g = dict(z)
            g["stufe"] = liste[-1]["stufe"] + (0 if g["gleichzeitig"] else 1) if liste else 0
            liste.append(g)
        return out

    def gaenge(self, auftrag_id):
        return self.alle_gaenge().get(auftrag_id, [])

    @staticmethod
    def bereit(gaenge):
        """Die Arbeitsgänge, die jetzt an der Reihe sind: die offenen der ersten Stufe, die nicht ganz fertig ist
        (streng nacheinander, Plan A2a)."""
        offen = [g for g in gaenge if g["status"] != FERTIG]
        return [g for g in offen if g["stufe"] == offen[0]["stufe"]] if offen else []

    def _gang(self, a, gang_id=None, lieber=None):
        """Arbeitsgang für Start oder Fertigmeldung; Fehler, wenn er noch nicht an der Reihe ist."""
        bereit = self.bereit(a["gaenge"])
        if not bereit:
            raise Fehler("Alle Arbeitsgänge dieses Auftrags sind schon fertig gemeldet.")
        if gang_id is None:
            return next((g for g in bereit if lieber and lieber(g)), bereit[0])
        g = next((g for g in a["gaenge"] if g["id"] == gang_id), None)
        if g is None or g["status"] == FERTIG:
            raise Fehler("Dieser Arbeitsgang ist schon fertig gemeldet.")
        if g not in bereit:
            raise Fehler(f"„{g['name']}“ ist noch nicht an der Reihe. Zuerst fertig melden: "
                         + ", ".join(x["name"] for x in bereit) + ".")
        return g

    def _gaenge_pruefen(self, liste):
        out = []
        for nr, g in enumerate(liste or (), start=1):
            platz = str(g.get("platz") or "").strip()
            if platz.lower() == FREMD_TEXT.lower():
                platz = FREMD
            try:
                kalk, tage = int(g.get("kalk_min") or 0), int(g.get("tage") or 0)
            except (TypeError, ValueError):
                raise Fehler(f"Zeile {nr}: Laufzeit oder Dauer ist nicht lesbar.") from None
            if platz == FREMD:
                if not 0 < tage <= 365:
                    raise Fehler(f"Zeile {nr}: Fremdarbeit braucht eine Dauer in Arbeitstagen (1 bis 365).")
                kalk = 0
            else:
                if kalk <= 0:
                    raise Fehler(f"Zeile {nr}: Bitte eine Laufzeit über 0 eingeben.")
                tage = 0
            name = str(g.get("name") or "").strip() or (FREMD_TEXT if platz == FREMD else platz)
            out.append(dict(id=g.get("id"), name=name, platz=platz, kalk_min=kalk, tage=tage,
                            gleichzeitig=int(bool(g.get("gleichzeitig")) and bool(out))))
        if len({g["name"] for g in out}) < len(out):
            raise Fehler("Zwei Zeilen heißen gleich. Bitte unterschiedliche Namen vergeben (z. B. Laser 1, Laser 2).")
        return out

    def _gaenge_schreiben(self, auftrag_id, gaenge, vorher):
        """Arbeitsgänge eines Auftrags ersetzen; Zeilen mit bekannter id behalten Status und gestoppte Zeit."""
        alt = {g["id"]: g for g in vorher}
        bleiben = {g["id"] for g in gaenge if g.get("id") in alt}
        for gid in set(alt) - bleiben:
            self.con.execute("DELETE FROM gaenge WHERE id = ?", (gid,))
        a = self.con.execute("SELECT gelaufen_min FROM auftraege WHERE id = ?", (auftrag_id,)).fetchone()
        mitnehmen = int(a[0] or 0) if a and not vorher else 0   # einteilig -> mehrteilig: gestoppte Zeit zum ersten
        for pos, g in enumerate(gaenge):
            werte = (pos, g["name"], g["platz"], g["kalk_min"], g["tage"], g["gleichzeitig"])
            if g.get("id") in alt:
                self.con.execute("UPDATE gaenge SET pos = ?, name = ?, platz = ?, kalk_min = ?, tage = ?, "
                                 "gleichzeitig = ? WHERE id = ?", werte + (g["id"],))
            else:
                self.con.execute("INSERT INTO gaenge (pos, name, platz, kalk_min, tage, gleichzeitig, auftrag_id, "
                                 "gelaufen_min) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                 werte + (auftrag_id, mitnehmen if pos == 0 and g["platz"] != FREMD else 0))
        if vorher and not gaenge:                 # mehrteilig -> einteilig: gestoppte Zeit bleibt beim Auftrag
            self.con.execute("UPDATE auftraege SET gelaufen_min = ? WHERE id = ?",
                             (sum(int(g["ist_min"] or g["gelaufen_min"] or 0) for g in vorher), auftrag_id))
            return
        if gaenge:
            self.con.execute("UPDATE auftraege SET start_am = NULL WHERE id = ?", (auftrag_id,))
            self._abgleichen(auftrag_id)
            neu, war = _plaetze_text(gaenge), _plaetze_text(vorher) if vorher else None
            if neu != war or [g["kalk_min"] for g in gaenge] != [g["kalk_min"] for g in vorher]:
                self._verlauf(auftrag_id, "Arbeitsgänge: " + "; ".join(
                    f"{g['name']} ({g['platz']}, {_zeigen('Kalkulierte Laufzeit', g['kalk_min'])})"
                    if g["platz"] != FREMD else f"{g['name']} (Fremdarbeit, {g['tage']} Arbeitstage)"
                    for g in gaenge))

    def _abgleichen(self, auftrag_id):
        """Maschine, Laufzeit, Status und tatsächliche Laufzeit des Auftrags aus seinen Arbeitsgängen zusammenfassen."""
        gaenge = self.gaenge(auftrag_id)
        if not gaenge:
            return
        fertig = [g for g in gaenge if g["status"] == FERTIG]
        if len(fertig) == len(gaenge):
            status, ist = FERTIG, sum(int(g["ist_min"] or 0) for g in gaenge)
            fertig_am = max(g["fertig_am"] or "" for g in gaenge) or None
        else:
            begonnen = fertig or any(g["start_am"] or g["gelaufen_min"] for g in gaenge)
            status, ist, fertig_am = (LAEUFT if begonnen else OFFEN), None, None
        self.con.execute(
            "UPDATE auftraege SET maschine = ?, kalk_min = ?, status = ?, ist_min = ?, fertig_am = ?, gelaufen_min = ?, "
            "start_am = NULL, vorrang = CASE WHEN ? = 'fertig' THEN 0 ELSE vorrang END, geaendert = ? WHERE id = ?",
            (_plaetze_text(gaenge), sum(g["kalk_min"] for g in gaenge), status, ist, fertig_am,
             sum(int((g["ist_min"] if g["status"] == FERTIG else g["gelaufen_min"]) or 0) for g in gaenge),
             status, _jetzt(), auftrag_id))

    def uhr_laeuft(self):
        """Läuft irgendwo eine Start/Stopp-Uhr? (Das Fenster zählt dann mit.)"""
        return bool(self.con.execute(
            "SELECT 1 FROM auftraege WHERE start_am IS NOT NULL AND geloescht_am IS NULL UNION ALL "
            "SELECT 1 FROM gaenge WHERE start_am IS NOT NULL AND platz <> '' LIMIT 1").fetchone())

    def vorlagen(self):
        """Vorlagen für Arbeitsgänge (Plan A1a): [dict(id, name, gaenge=[dict(name, platz, kalk_min, tage,
        gleichzeitig)])]."""
        out = []
        for z in self.con.execute("SELECT * FROM vorlagen ORDER BY name"):
            try:
                gaenge = json.loads(z["gaenge"])
            except ValueError:
                gaenge = []
            out.append(dict(id=z["id"], name=z["name"], gaenge=gaenge))
        return out

    def vorlage_speichern(self, name, gaenge, alt=None):
        """Vorlage anlegen oder ändern (alt = bisheriger Name). Laufzeiten dürfen leer sein; sie werden im Auftrag
        eingetragen."""
        name = str(name or "").strip()
        if not name:
            raise Fehler("Die Vorlage braucht einen Namen.")
        liste = []
        for g in gaenge or ():
            platz = str(g.get("platz") or "").strip()
            platz = FREMD if platz.lower() == FREMD_TEXT.lower() else platz
            liste.append(dict(name=str(g.get("name") or "").strip() or platz or FREMD_TEXT, platz=platz,
                              kalk_min=max(0, int(g.get("kalk_min") or 0)), tage=max(0, int(g.get("tage") or 0)),
                              gleichzeitig=int(bool(g.get("gleichzeitig")) and bool(liste))))
        if not liste:
            raise Fehler("Die Vorlage braucht mindestens einen Arbeitsgang.")
        da = {v["name"] for v in self.vorlagen()}
        if name in da and name != alt:
            raise Fehler(f"Die Vorlage „{name}“ gibt es schon.")
        text = json.dumps(liste, ensure_ascii=False)
        if alt in da:
            self.con.execute("UPDATE vorlagen SET name = ?, gaenge = ? WHERE name = ?", (name, text, alt))
        else:
            self.con.execute("INSERT INTO vorlagen (name, gaenge) VALUES (?, ?)", (name, text))

    def vorlage_loeschen(self, name):
        self.con.execute("DELETE FROM vorlagen WHERE name = ?", (name,))

    # ------------------------------------------------------------------ Benutzerrechte und Änderungsverlauf
    def benutzer(self):
        return [dict(z) for z in self.con.execute("SELECT * FROM benutzer ORDER BY name")]

    def rolle(self, name=None):
        """Rolle eines Anmeldenamens (Vorgabe: dieser Platz). Solange kein Benutzer eingetragen ist, sind die Rechte
        aus und jeder ist Verwaltung; wer nicht eingetragen ist, bekommt sonst die Vorgabe-Rolle."""
        name = self.wer if name is None else str(name).strip().lower()
        liste = {b["name"]: b["rolle"] for b in self.benutzer()}
        if not liste:
            return VERWALTUNG
        rolle = liste.get(name) or self.einstellung("rolle_vorgabe")
        return rolle if rolle in RECHTE else LESEN

    def darf(self, recht, name=None):
        return recht in RECHTE[self.rolle(name)]

    def rechte_an(self):
        return bool(self.con.execute("SELECT 1 FROM benutzer LIMIT 1").fetchone())

    def benutzer_speichern(self, name, rolle, alt=None):
        """Legt an oder ändert (alt = bisheriger Anmeldename). Mindestens ein Benutzer muss Verwaltung bleiben."""
        name = str(name or "").strip().lower()
        if not name:
            raise Fehler("Bitte den Anmeldenamen eingeben (so, wie er bei der Windows-Anmeldung heißt).")
        if rolle not in RECHTE:
            raise Fehler("Bitte eine Rolle wählen.")
        alt = str(alt).strip().lower() if alt else None
        liste = {b["name"]: b["rolle"] for b in self.benutzer()}
        if name in liste and name != alt:
            raise Fehler(f"Den Benutzer „{name}“ gibt es schon.")
        danach = {n: r for n, r in liste.items() if n != alt}
        danach[name] = rolle
        self._verwaltung_bleibt(danach)
        if alt in liste:
            self.con.execute("UPDATE benutzer SET name = ?, rolle = ? WHERE name = ?", (name, rolle, alt))
        else:
            self.con.execute("INSERT INTO benutzer (name, rolle) VALUES (?, ?)", (name, rolle))

    def benutzer_loeschen(self, name):
        name = str(name or "").strip().lower()
        danach = {b["name"]: b["rolle"] for b in self.benutzer() if b["name"] != name}
        self._verwaltung_bleibt(danach)
        self.con.execute("DELETE FROM benutzer WHERE name = ?", (name,))

    @staticmethod
    def _verwaltung_bleibt(liste):
        if liste and VERWALTUNG not in liste.values():
            raise Fehler("Mindestens ein Benutzer braucht die Rolle Verwaltung, sonst kommt niemand mehr an die "
                         "Einstellungen. Zuerst einen Benutzer mit der Rolle Verwaltung eintragen.")

    def _verlauf(self, auftrag_id, was):
        self.con.execute("INSERT INTO verlauf (auftrag_id, wann, wer, was) VALUES (?, ?, ?, ?)",
                         (auftrag_id, _jetzt(), self.wer, was))

    def verlauf(self, auftrag_id):
        """Änderungsverlauf eines Auftrags, neueste zuerst: [dict(wann, wer, was)]."""
        return [dict(z) for z in self.con.execute(
            "SELECT wann, wer, was FROM verlauf WHERE auftrag_id = ? ORDER BY id DESC", (auftrag_id,))]
