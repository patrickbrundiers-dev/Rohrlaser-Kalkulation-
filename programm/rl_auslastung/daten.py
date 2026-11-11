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

from . import zusatz as Z

OFFEN, LAEUFT, FERTIG = "offen", "läuft", "fertig"
STATUS = (OFFEN, LAEUFT, FERTIG)
VORGABEN = {
    "samstag_stunden": "0", "nutzungsgrad": "100", "bundesland": "Nordrhein-Westfalen", "vorlauf_tage": "2",
    "rolle_vorgabe": "lesen", "arbeitsgaenge": "0", "stopp_fragen": "1",
    "einfrieren_tage": "2", "rest_prozent": "15", "rest_min": "30", "prio_tage": "3", "warn_stopp_min": "30",
    "warn_material_tage": "2",
    "stoppgruende": "Störung; Material fehlt; Rüsten; Pause; anderer Auftrag",
    "betriebsruhe": "", "laufzeit_form": "hm", "ohne_einheit": "min", "schwelle_tage": "2", "design": "Hell",
    "wochen": "8",
    "schichten": ('[{"name": "Früh", "beginn": "06:00", "ende": "14:00", "pause": 30}, '
                  '{"name": "Spät", "beginn": "14:00", "ende": "22:00", "pause": 30}, '
                  '{"name": "Nacht", "beginn": "22:00", "ende": "06:00", "pause": 30}]'),
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
    # 7: „Material da ab“ (Erweiterungsplan E8): vor diesem Tag wird der Auftrag nicht eingelastet.
    """
    ALTER TABLE auftraege ADD COLUMN material_ab TEXT;
    """,
    # 8: Schichtsystem (Patrick 11.11.2026): Schichten mit Beginn, Ende und Pause stehen als JSON in der Einstellung
    # schichten; je Maschine die Schichten von Montag bis Freitag (Namen mit Komma). Mit Schichten ergibt sich
    # stunden_tag aus deren Summe, ohne bleibt die Zahl von Hand.
    """
    ALTER TABLE maschinen ADD COLUMN schichten TEXT NOT NULL DEFAULT '';
    """,
    # 9: Wochenwechsel der Schichten (Patrick 11.11.2026): maschinen.schichten kann mehrere Wochen enthalten, mit „|“
    # getrennt („Früh|Spät“ = eine Woche Früh, die nächste Spät, dann wieder von vorn); schicht_start = Montag der
    # Woche, in der die Folge mit ihrer ersten Woche beginnt. stunden_tag ist dann die kleinste Woche der Folge.
    """
    ALTER TABLE maschinen ADD COLUMN schicht_start TEXT;
    """,
    # 10: Schichtkalender mit Ausnahmen (Patrick 11.11.2026, V1): eigene Schichten am Samstag je Maschine
    # (schichten_sa, Namen mit Komma; leer = die Samstagsstunden für alle) und Ausnahmen für einzelne Tage oder
    # Zeiträume (Sonderschicht, Kurzarbeit, Brückentag): maschine '' = alle, schichten '' = frei.
    """
    ALTER TABLE maschinen ADD COLUMN schichten_sa TEXT NOT NULL DEFAULT '';
    CREATE TABLE ausnahmen (id INTEGER PRIMARY KEY, maschine TEXT NOT NULL DEFAULT '', von TEXT NOT NULL,
        bis TEXT NOT NULL, schichten TEXT NOT NULL DEFAULT '', grund TEXT NOT NULL DEFAULT '');
    """,
    # 11: Planung genauer (Patrick 11.11.2026, Plan Paket A). A1 Rüstzeit: feste Zeit je Maschine (ruest_min), je
    # Auftrag änderbar (auftraege.ruest_min, NULL = Vorgabe der Maschine); gleiches Material (Text) direkt
    # hintereinander spart das Rüsten. A3 Eignung: größter Durchmesser und größte Rohrlänge je Maschine (0 = keine
    # Grenze) gegen Durchmesser und Rohrlänge des Auftrags (0 = unbekannt). A5 Teillieferungen: mehrere
    # Liefertermine mit Mengen; die Laufzeit teilt sich nach den Mengen, jede Lieferung hat ihren eigenen Termin.
    # Uhrzeit der Fertigmeldung (Patrick 11.11.2026): fertig_um = 'HH:MM' neben dem Tag fertig_am, NULL = unbekannt.
    """
    ALTER TABLE maschinen ADD COLUMN ruest_min INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE maschinen ADD COLUMN max_durchmesser REAL NOT NULL DEFAULT 0;
    ALTER TABLE maschinen ADD COLUMN max_laenge REAL NOT NULL DEFAULT 0;
    ALTER TABLE auftraege ADD COLUMN ruest_min INTEGER;
    ALTER TABLE auftraege ADD COLUMN material TEXT NOT NULL DEFAULT '';
    ALTER TABLE auftraege ADD COLUMN durchmesser REAL NOT NULL DEFAULT 0;
    ALTER TABLE auftraege ADD COLUMN laenge REAL NOT NULL DEFAULT 0;
    CREATE TABLE lieferungen (id INTEGER PRIMARY KEY, auftrag_id INTEGER NOT NULL, termin TEXT NOT NULL,
        menge REAL NOT NULL DEFAULT 0);
    CREATE INDEX lieferungen_auftrag ON lieferungen (auftrag_id, termin, id);
    ALTER TABLE auftraege ADD COLUMN fertig_um TEXT;
    ALTER TABLE gaenge ADD COLUMN fertig_um TEXT;
    """,
    # 12: Planen mit Erfahrungswert (Patrick 11.11.2026, Plan 2.2 N3): je Maschine schaltbar; die kalkulierte Zeit
    # wird um die gemessene Abweichung aus Soll und Ist korrigiert (rechnung.erfahrung).
    """
    ALTER TABLE maschinen ADD COLUMN erfahrung INTEGER NOT NULL DEFAULT 0;
    """,
    # 13: Zusatzschritte mit Zeit aus Anzahl (Patrick 11.11.2026, Plan 2.6): Stückzahl je Auftrag, Positionen je
    # Arbeitsgang (JSON [{schritt, art, anzahl}]), Tabelle der Richtzeiten mit Schätzwerten; Fremdarbeit wird nur
    # montags und mittwochs abgeholt und angeliefert (Einstellung fremd_tage, änderbar).
    """
    ALTER TABLE auftraege ADD COLUMN stueckzahl INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE gaenge ADD COLUMN zusatz TEXT NOT NULL DEFAULT '';
    CREATE TABLE richtzeiten (id INTEGER PRIMARY KEY, schritt TEXT NOT NULL, art TEXT NOT NULL DEFAULT '',
        je_s REAL NOT NULL DEFAULT 0, ruest_min REAL NOT NULL DEFAULT 0, handling_s REAL NOT NULL DEFAULT 0,
        platz TEXT NOT NULL DEFAULT '', tage INTEGER NOT NULL DEFAULT 0, stichwort TEXT NOT NULL DEFAULT '',
        geschaetzt INTEGER NOT NULL DEFAULT 1, reihenfolge INTEGER NOT NULL DEFAULT 0, UNIQUE (schritt, art));
    INSERT OR IGNORE INTO einstellungen (schluessel, wert) VALUES ('fremd_tage', '0,2');
    """ + "".join(
        "INSERT INTO richtzeiten (schritt, art, je_s, ruest_min, handling_s, platz, tage, stichwort, reihenfolge) "
        f"VALUES ('{z[0]}', '{z[1]}', {z[2]}, {z[3]}, {z[4]}, '{z[5]}', {z[6]}, '{z[7]}', {i});\n"
        for i, z in enumerate(Z.STANDARD)),
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


def uhrzeit(text):
    """'6', '6:00', '06.30', '14 Uhr' -> Minuten seit Mitternacht; sonst Fehler."""
    m = re.fullmatch(r"\s*(\d{1,2})(?:[:.](\d{2}))?\s*(?:Uhr)?\s*", str(text or ""))
    if not m or int(m.group(1)) > 24 or int(m.group(2) or 0) > 59 or (int(m.group(1)) == 24 and int(m.group(2) or 0)):
        raise Fehler(f"„{text}“ ist keine Uhrzeit. Beispiel: 06:00")
    return (int(m.group(1)) % 24) * 60 + int(m.group(2) or 0)


def uhr_text(minuten):
    minuten = int(round(minuten)) % 1440
    return f"{minuten // 60:02d}:{minuten % 60:02d}"


FOLGE_MAX = 4                  # so viele Wochen kann der Wochenwechsel einer Maschine haben


def schichtfolge(maschine):
    """Schichten einer Maschine (Zeile aus maschinen) je Woche der Folge: [[Namen der Woche 1], [Woche 2] …];
    [] = ohne Schichten, eine Woche = jede Woche gleich."""
    text = (maschine or {}).get("schichten") or ""
    return [w for w in ([n for n in teil.split(",") if n] for teil in text.split("|")) if w]


def schichten_woche(maschine, montag=None):
    """Namen der Schichten der Maschine in der Woche ab montag (None = erste Woche der Folge)."""
    folge = schichtfolge(maschine)
    if not folge:
        return []
    if len(folge) == 1 or montag is None:
        return folge[0]
    start = _tag_iso(maschine.get("schicht_start")) or montag
    return folge[((montag - start).days // 7) % len(folge)]


def _tag_iso(text):
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def _schicht(name, beginn, ende, pause=0):
    """Geprüfte Schicht: dauer = Stunden von Beginn bis Ende (über Mitternacht möglich, gleich = 24 h), stunden =
    Arbeitszeit ohne Pause."""
    name = str(name or "").strip()
    if not name or "," in name or "|" in name:
        raise Fehler("Die Schicht braucht einen Namen (ohne Komma und ohne „|“).")
    b, e = uhrzeit(beginn), uhrzeit(ende)
    try:
        pause = int(pause or 0)
    except (TypeError, ValueError):
        raise Fehler("Pause: bitte Minuten als ganze Zahl eingeben.") from None
    dauer = (e - b) % 1440 or 1440
    if not 0 <= pause < dauer:
        raise Fehler(f"Schicht „{name}“: Die Pause muss kürzer sein als die Schicht.")
    return dict(name=name, beginn=uhr_text(b), ende=uhr_text(e), pause=pause, dauer=dauer / 60,
                stunden=(dauer - pause) / 60)


def _zahl(wert, name, hoechstens=None, ganz=False):
    """Zahl >= 0 aus Text mit Komma oder Punkt; leer = 0."""
    t = str(wert if wert is not None else "").strip().replace(",", ".")
    try:
        z = float(t) if t else 0.0
    except ValueError:
        raise Fehler(f"{name}: bitte eine Zahl eingeben.") from None
    if z < 0 or (hoechstens is not None and z > hoechstens):
        raise Fehler(f"{name}: bitte eine Zahl von 0 bis {hoechstens:g} eingeben." if hoechstens is not None
                     else f"{name}: bitte eine Zahl ab 0 eingeben.")
    return int(round(z)) if ganz else z


def mm_text(wert):
    """1200.0 -> '1200', 60.3 -> '60,3'."""
    return f"{float(wert or 0):g}".replace(".", ",")


def passt_nicht(maschine, durchmesser, laenge):
    """A3 Eignung: Text, warum das Rohr nicht auf die Maschine passt, oder ''. maschine: Zeile aus maschinen() oder
    dict(name, max_durchmesser, max_laenge); 0 = keine Grenze, Durchmesser oder Länge 0 = unbekannt (passt)."""
    if not maschine:
        return ""
    for wert, grenze, was in ((durchmesser, maschine.get("max_durchmesser"), "Durchmesser"),
                              (laenge, maschine.get("max_laenge"), "Rohrlänge")):
        if wert and grenze and float(wert) > float(grenze) + 1e-9:
            return (f"{was} {mm_text(wert)} mm passt nicht auf {maschine['name']} "
                    f"(höchstens {mm_text(grenze)} mm).")
    return ""


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _zeigen(feld, wert):
    """Wert für den Änderungsverlauf."""
    if feld == "Kalkulierte Laufzeit":
        m = int(wert or 0)
        return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"
    if feld in ("Liefertermin", "Material da ab") and wert:
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
        self.nur_ansehen = ""                     # Plan 2.4: Grund, wenn dieser Platz keine gültige Lizenz hat
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

    # ------------------------------------------------------------------ Schichten
    def schichten(self):
        """Schichten in ihrer Reihenfolge: [dict(name, beginn 'HH:MM', ende 'HH:MM', pause in Minuten, stunden
        = Arbeitszeit ohne Pause)]."""
        try:
            roh = json.loads(self.einstellung("schichten") or "[]")
            return [_schicht(z["name"], z["beginn"], z["ende"], z.get("pause", 0)) for z in roh]
        except (ValueError, TypeError, KeyError, Fehler):
            return []

    def schichten_setzen(self, liste):
        """Schichten speichern. Maschinen, die Schichten fahren, bekommen ihre Stunden je Tag neu; eine entfernte
        Schicht fällt bei ihnen weg (bleibt keine, behalten sie ihre Stunden je Tag)."""
        neu, namen = [], set()
        for z in liste:
            sch = _schicht(z.get("name"), z.get("beginn"), z.get("ende"), z.get("pause", 0))
            if sch["name"].lower() in namen:
                raise Fehler(f"Die Schicht „{sch['name']}“ gibt es doppelt.")
            namen.add(sch["name"].lower())
            neu.append(sch)
        with self.con:
            self.con.execute("BEGIN")
            self.einstellung_setzen("schichten", json.dumps(
                [dict(name=x["name"], beginn=x["beginn"], ende=x["ende"], pause=x["pause"]) for x in neu]))
            netto = {x["name"]: x["stunden"] for x in neu}
            for a in self.ausnahmen():                      # entfernte Schicht: fällt weg; bleibt keine, die Ausnahme
                bleibt = [n for n in a["namen"] if n in netto]
                if a["namen"] and not bleibt:
                    self.con.execute("DELETE FROM ausnahmen WHERE id = ?", (a["id"],))
                elif bleibt != a["namen"]:
                    self.con.execute("UPDATE ausnahmen SET schichten = ? WHERE id = ?", (",".join(bleibt), a["id"]))
            for m in self.maschinen():
                sa = [n for n in (m.get("schichten_sa") or "").split(",") if n]
                if sa and any(n not in netto for n in sa):
                    self.con.execute("UPDATE maschinen SET schichten_sa = ? WHERE name = ?",
                                     (",".join(n for n in sa if n in netto), m["name"]))
                folge = schichtfolge(m)
                if not folge:
                    continue
                bleibt = [w for w in ([n for n in woche if n in netto] for woche in folge) if w]
                stunden = (min(min(24.0, sum(netto[n] for n in w)) for w in bleibt) if bleibt
                           else m["stunden_tag"])
                self.con.execute("UPDATE maschinen SET schichten = ?, stunden_tag = ? WHERE name = ?",
                                 ("|".join(",".join(w) for w in bleibt), stunden, m["name"]))

    def schicht_umbenennen(self, alt, neu):
        """Neuer Name bei Maschinen (Wochen, Samstag) und Ausnahmen; die Schichtliste selbst setzt schichten_setzen."""
        def tausch(text, trenner=","):
            return trenner.join(neu if n == alt else n for n in text.split(trenner))
        for m in self.maschinen():
            self.con.execute("UPDATE maschinen SET schichten = ?, schichten_sa = ? WHERE name = ?", (
                "|".join(tausch(w) for w in (m["schichten"] or "").split("|")), tausch(m.get("schichten_sa") or ""),
                m["name"]))
        for z in self.con.execute("SELECT id, schichten FROM ausnahmen").fetchall():
            self.con.execute("UPDATE ausnahmen SET schichten = ? WHERE id = ?", (tausch(z["schichten"]), z["id"]))

    def schichten_der(self, maschine, montag=None):
        """Schichten einer Maschine von Montag bis Freitag in der Woche ab montag (Vorgabe: erste Woche der Folge),
        in der Reihenfolge der Schichtliste ([] = ohne Schichten, Stunden je Tag von Hand)."""
        m = next((x for x in self.maschinen() if x["name"] == maschine), None)
        namen = schichten_woche(m, montag) if m else []
        return [x for x in self.schichten() if x["name"] in namen]

    def maschine_speichern(self, name, stunden_tag=8.0, aktiv=True, alt=None, sperrtage=None, uebergang=None,
                           ausweich=None, schichten=None, schicht_start=None, samstag=None, ruest=None,
                           max_durchmesser=None, max_laenge=None, erfahrung=None):
        """Legt an oder ändert (alt = bisheriger Name). Umbenennen zieht die Aufträge mit. sperrtage: Text wie
        '24.11.2026-25.11.2026; 02.12.2026' (Wartung, Ausfall); None lässt sie, wie sie sind. uebergang: Arbeitstage
        zwischen dem Arbeitsgang davor und dem Beginn an diesem Arbeitsplatz (Transport, Abkühlen); None lässt sie.
        ausweich: kann Aufträge anderer Maschinen übernehmen (Vorschlag Ausweichmaschine); None lässt es.
        schichten: Namen der Schichten von Montag bis Freitag; mit Schichten ergeben sich die Stunden je Tag aus
        ihrer Summe, [] = ohne Schichten (Stunden je Tag von Hand); None lässt sie. Wochenwechsel: eine Liste je
        Woche ([["Früh"], ["Spät"]]), die Folge wiederholt sich ab schicht_start (Datum, gilt dessen Montag;
        Vorgabe: der bisherige Beginn, sonst diese Woche). stunden_tag ist dann die kleinste Woche.
        samstag: Namen der Schichten am Samstag ([] = die Samstagsstunden für alle Maschinen); None lässt sie.
        ruest: feste Rüstzeit je Auftrag in Minuten (A1); max_durchmesser, max_laenge: größtes Rohr in mm, 0 = keine
        Grenze (A3); None lässt sie."""
        name = str(name or "").strip()
        if ruest is not None:
            ruest = _zahl(ruest, "Rüstzeit", 24 * 60, ganz=True)
        if max_durchmesser is not None:
            max_durchmesser = _zahl(max_durchmesser, "Größter Durchmesser")
        if max_laenge is not None:
            max_laenge = _zahl(max_laenge, "Größte Rohrlänge")
        if not name:
            raise Fehler("Die Maschine braucht einen Namen.")
        if samstag is not None:
            samstag = self._schichtnamen(samstag)
        if schichten is not None:
            bekannt = {x["name"]: x for x in self.schichten()}
            fehlt = [n for w in schichten for n in ([w] if isinstance(w, str) else w) if n not in bekannt]
            if fehlt:
                raise Fehler(f"Die Schicht „{fehlt[0]}“ gibt es nicht (Einstellungen → Schichten).")
            folge = [list(w) for w in schichten] if schichten and not isinstance(schichten[0], str) \
                else ([list(schichten)] if schichten else [])
            if len(folge) > FOLGE_MAX:
                raise Fehler(f"Der Wochenwechsel geht über höchstens {FOLGE_MAX} Wochen.")
            folge = [[n for n in bekannt if n in woche] for woche in folge]
            if len(folge) > 1 and not all(folge):
                raise Fehler("Wochenwechsel: In jeder Woche muss mindestens eine Schicht angehakt sein.")
            folge = [w for w in folge if w]
            for woche in folge:
                if sum(bekannt[n]["dauer"] for n in woche) > 24 + 1e-9:
                    raise Fehler("Die gewählten Schichten ergeben zusammen mehr als 24 Stunden am Tag.")
            if folge:
                stunden_tag = min(sum(bekannt[n]["stunden"] for n in woche) for woche in folge)
            schichten = folge
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
                    self.con.execute("UPDATE ausnahmen SET maschine = ? WHERE maschine = ?", (name, alt))
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
            for spalte, wert in (("ruest_min", ruest), ("max_durchmesser", max_durchmesser),
                                 ("max_laenge", max_laenge),
                                 ("erfahrung", None if erfahrung is None else int(bool(erfahrung)))):
                if wert is not None:
                    self.con.execute(f"UPDATE maschinen SET {spalte} = ? WHERE name = ?", (wert, name))
            if samstag is not None:
                self.con.execute("UPDATE maschinen SET schichten_sa = ? WHERE name = ?", (",".join(samstag), name))
            if schichten is not None:
                self.con.execute("UPDATE maschinen SET schichten = ? WHERE name = ?",
                                 ("|".join(",".join(w) for w in schichten), name))
                if len(schichten) > 1:
                    alt_start = self.con.execute("SELECT schicht_start FROM maschinen WHERE name = ?",
                                                 (name,)).fetchone()[0]
                    start = schicht_start or _tag_iso(alt_start) or datetime.date.today()
                    start -= datetime.timedelta(days=start.weekday())
                    self.con.execute("UPDATE maschinen SET schicht_start = ? WHERE name = ?", (start.isoformat(), name))

    def maschine_loeschen(self, name):
        n = self.con.execute(
            "SELECT COUNT(*) FROM auftraege a WHERE a.geloescht_am IS NULL AND (a.maschine = ? OR EXISTS "
            "(SELECT 1 FROM gaenge g WHERE g.auftrag_id = a.id AND g.platz = ?))", (name, name)).fetchone()[0]
        if n:
            raise Fehler(f"Auf „{name}“ liegen noch {n} Aufträge. Die Maschine lässt sich stattdessen auf „nicht "
                         "aktiv“ stellen.")
        with self.con:
            self.con.execute("BEGIN")
            self.con.execute("DELETE FROM maschinen WHERE name = ?", (name,))
            self.con.execute("DELETE FROM ausnahmen WHERE maschine = ?", (name,))

    def _schichtnamen(self, namen):
        """Geprüfte Schichtnamen in der Reihenfolge der Schichtliste; zusammen höchstens 24 Stunden."""
        bekannt = {x["name"]: x for x in self.schichten()}
        fehlt = [n for n in namen if n not in bekannt]
        if fehlt:
            raise Fehler(f"Die Schicht „{fehlt[0]}“ gibt es nicht (Einstellungen → Schichten).")
        liste = [n for n in bekannt if n in namen]
        if sum(bekannt[n]["dauer"] for n in liste) > 24 + 1e-9:
            raise Fehler("Die gewählten Schichten ergeben zusammen mehr als 24 Stunden am Tag.")
        return liste

    # ------------------------------------------------------------------ Ausnahmen im Schichtkalender
    def ausnahmen(self):
        """Ausnahmen nach Datum: [dict(id, maschine ('' = alle), von, bis (Datum), namen (Schichten, [] = frei),
        grund)]. Ein einzelner Tag gilt immer außer am Sonntag, auch am Samstag und am Feiertag; ein Zeitraum gilt
        für Montag bis Freitag ohne Feiertage."""
        out = []
        for z in self.con.execute("SELECT * FROM ausnahmen ORDER BY von, bis, maschine, id"):
            von, bis = _tag_iso(z["von"]), _tag_iso(z["bis"])
            if von and bis:
                out.append(dict(id=z["id"], maschine=z["maschine"], von=von, bis=bis, grund=z["grund"],
                                namen=[n for n in z["schichten"].split(",") if n]))
        return out

    def ausnahme_speichern(self, maschine, von, bis=None, schichten=(), grund="", id=None):
        """Ausnahme anlegen oder ändern (id). maschine '' oder None = alle Maschinen; von/bis: Datum oder Text
        (TT.MM.JJJJ); schichten: Namen, leer = an diesen Tagen wird nicht gearbeitet."""
        maschine = str(maschine or "").strip()
        if maschine and maschine not in {m["name"] for m in self.maschinen()}:
            raise Fehler(f"Die Maschine „{maschine}“ gibt es nicht.")
        tage = []
        for wert in (von, bis if bis not in (None, "") else von):
            if not isinstance(wert, datetime.date):
                treffer = wochen.betriebsruhe(str(wert or ""))
                if len(treffer) != 1:
                    raise Fehler(f"Ausnahme: „{wert}“ ist kein Datum. Beispiel: 24.11.2026")
                wert = next(iter(treffer))
            tage.append(wert)
        von, bis = tage
        if bis < von:
            raise Fehler("Ausnahme: „bis“ liegt vor „von“.")
        if (bis - von).days > 366:
            raise Fehler("Eine Ausnahme geht über höchstens ein Jahr.")
        if von == bis and von.weekday() == 6:
            raise Fehler("Am Sonntag wird nicht eingelastet, eine Ausnahme dort hat keine Wirkung.")
        namen = self._schichtnamen(list(schichten or ()))
        werte = (maschine, von.isoformat(), bis.isoformat(), ",".join(namen), str(grund or "").strip())
        with self.con:
            if id:
                self.con.execute("UPDATE ausnahmen SET maschine = ?, von = ?, bis = ?, schichten = ?, grund = ? "
                                 "WHERE id = ?", werte + (id,))
                return id
            return self.con.execute("INSERT INTO ausnahmen (maschine, von, bis, schichten, grund) "
                                    "VALUES (?, ?, ?, ?, ?)", werte).lastrowid

    def ausnahme_entfernen(self, id):
        with self.con:
            self.con.execute("DELETE FROM ausnahmen WHERE id = ?", (id,))

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
        lief = {}
        if liste:
            for z in self.con.execute("SELECT id, auftrag_id, termin, menge FROM lieferungen ORDER BY termin, id"):
                lief.setdefault(z["auftrag_id"], []).append(dict(id=z["id"], termin=z["termin"], menge=z["menge"]))
        for a in liste:
            a["zusatz"] = werte.get(a["id"], {})
            a["gaenge"] = gaenge.get(a["id"], [])
            a["lieferungen"] = lief.get(a["id"], [])
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

    def materialien(self):
        """Alle bisher eingegebenen Materialien (für die Vorschlagsliste im Auftrag)."""
        return [z[0] for z in self.con.execute(
            "SELECT DISTINCT material FROM auftraege WHERE material <> '' AND geloescht_am IS NULL "
            "ORDER BY material COLLATE NOCASE")]

    def auftrag_speichern(self, a):
        """Legt an (ohne id) oder ändert. a: nummer, maschine, kalk_min, liefertermin, kunde, bemerkung, zusatz={Feld:
        Wert}. Ergebnis: id.

        Mit a["gaenge"] = [dict(name, platz, kalk_min, tage, gleichzeitig[, id])] wird der Auftrag mehrteilig
        (Arbeitsgänge oder Teile auf mehreren Maschinen); Maschine und Laufzeit ergeben sich dann aus den Zeilen. Eine
        leere Liste macht ihn wieder einteilig. Fehlt der Schlüssel, bleiben vorhandene Arbeitsgänge, wie sie sind.

        Paket A, jeweils nur mit dem Schlüssel (fehlt er, bleibt der Wert): ruest_min (None oder '' = Vorgabe der
        Maschine), material (Text; gleiches Material hintereinander spart das Rüsten), durchmesser und laenge in mm
        (0 = unbekannt; passt das Rohr nicht auf die Maschine, gibt es einen Fehler), lieferungen = [dict(termin,
        menge)] (Teillieferungen, nur ohne Arbeitsgänge; der Liefertermin ist dann der letzte davon)."""
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
        mehr = {}
        if "ruest_min" in a:
            mehr["ruest_min"] = (None if a["ruest_min"] in (None, "") else
                                 _zahl(a["ruest_min"], "Rüstzeit", 24 * 60, ganz=True))
        if "material" in a:
            mehr["material"] = " ".join(str(a["material"] or "").split())
        if "durchmesser" in a:
            mehr["durchmesser"] = _zahl(a["durchmesser"], "Durchmesser")
        if "laenge" in a:
            mehr["laenge"] = _zahl(a["laenge"], "Rohrlänge")
        if "stueckzahl" in a:                     # Plan 2.6: für die Zeit der Zusatzschritte
            mehr["stueckzahl"] = max(1, _zahl(a["stueckzahl"] or 1, "Stückzahl", 10 ** 7, ganz=True))
        lieferungen = None
        if "lieferungen" in a:
            lieferungen = []
            for x in a["lieferungen"] or ():
                tag = _tag(x.get("termin"))
                if not tag:
                    raise Fehler("Teillieferung: bitte einen Termin eingeben.")
                menge = _zahl(x.get("menge"), "Teillieferung, Menge")
                if menge <= 0:
                    raise Fehler("Teillieferung: bitte eine Menge über 0 eingeben.")
                lieferungen.append((tag, menge))
            lieferungen.sort()
            if len(lieferungen) == 1:
                raise Fehler("Teillieferungen: bitte mindestens zwei Termine eingeben oder die Zeile entfernen "
                             "(ein einzelner Termin ist der Liefertermin).")
            if lieferungen and mehrteilig:
                raise Fehler("Teillieferungen gibt es nur bei Aufträgen ohne Arbeitsgänge.")
            if lieferungen:
                termin = lieferungen[-1][0]
        elif mehrteilig and "gaenge" in a and a.get("id") and self.con.execute(
                "SELECT 1 FROM lieferungen WHERE auftrag_id = ?", (a["id"],)).fetchone():
            raise Fehler("Teillieferungen gibt es nur bei Aufträgen ohne Arbeitsgänge.")
        if not mehrteilig and ("durchmesser" in mehr or "laenge" in mehr or "maschine" in a):
            alt_a = (self.con.execute("SELECT durchmesser, laenge FROM auftraege WHERE id = ?",
                                      (a["id"],)).fetchone() if a.get("id") else None) or (0, 0)
            grund = passt_nicht(next((m for m in self.maschinen() if m["name"] == maschine), None),
                                mehr.get("durchmesser", alt_a[0]), mehr.get("laenge", alt_a[1]))
            if grund:
                raise Fehler(grund)
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
            if "material_ab" in a:                # E8: Schlüssel fehlt = bleibt, wie es ist
                material = _tag(a["material_ab"])
                alt_m = self.con.execute("SELECT material_ab FROM auftraege WHERE id = ?", (aid,)).fetchone()[0]
                if (alt_m or None) != material:
                    self.con.execute("UPDATE auftraege SET material_ab = ? WHERE id = ?", (material, aid))
                    self._verlauf(aid, f"Material da ab: {_zeigen('Material da ab', material) if material else 'sofort'}")
            if mehr:
                alt_w = self.con.execute(f"SELECT {', '.join(mehr)} FROM auftraege WHERE id = ?", (aid,)).fetchone()
                namen = dict(ruest_min="Rüstzeit", material="Material", durchmesser="Durchmesser", laenge="Rohrlänge",
                             stueckzahl="Stückzahl")
                einheit = dict(ruest_min=" min", material="", durchmesser=" mm", laenge=" mm", stueckzahl=" Stück")
                anders = []
                for (spalte, neu), war in zip(mehr.items(), alt_w):
                    if (war or None) != (neu or None) or (spalte == "ruest_min" and war != neu):
                        self.con.execute(f"UPDATE auftraege SET {spalte} = ? WHERE id = ?", (neu, aid))
                        zeigen = ("wie Maschine" if spalte == "ruest_min" and neu is None else
                                  "leer" if neu in ("", 0, 0.0) and spalte != "ruest_min" else
                                  (mm_text(neu) if spalte != "material" else neu) + einheit[spalte])
                        anders.append(f"{namen[spalte]}: {zeigen}")
                if anders and a.get("id"):
                    self._verlauf(aid, "geändert (" + "; ".join(anders) + ")")
            if lieferungen is not None:
                war = [(z[0], z[1]) for z in self.con.execute(
                    "SELECT termin, menge FROM lieferungen WHERE auftrag_id = ? ORDER BY termin, id", (aid,))]
                if war != lieferungen:
                    self.con.execute("DELETE FROM lieferungen WHERE auftrag_id = ?", (aid,))
                    self.con.executemany("INSERT INTO lieferungen (auftrag_id, termin, menge) VALUES (?, ?, ?)",
                                         [(aid, t, m) for t, m in lieferungen])
                    self._verlauf(aid, "Teillieferungen: " + ("; ".join(
                        f"{_zeigen('Liefertermin', t)} {mm_text(m)} Stück" for t, m in lieferungen) or "keine"))
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
                    self.con.execute("DELETE FROM lieferungen WHERE auftrag_id = ?", (i,))
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

    def _maschine_wechseln(self, a, g, maschine, pruefen=True):
        """pruefen: passt das Rohr auf die Maschine (A3)? Beim Rückgängigmachen aus."""
        if not maschine or maschine == (g["platz"] if g else a["maschine"]):
            return
        ziel = next((m for m in self.maschinen() if m["name"] == maschine), None)
        if ziel is None:
            raise Fehler(f"Die Maschine „{maschine}“ gibt es nicht.")
        grund = passt_nicht(ziel, a.get("durchmesser"), a.get("laenge")) if pruefen else ""
        if grund:
            raise Fehler(f"Auftrag {a['nummer']}: {grund}")
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

    def optimierung_uebernehmen(self, schritte):
        """Vorschlag der automatischen Optimierung speichern: schritte = [dict(id, art 'maschine'|'vorziehen'|
        'termin'|'reihenfolge', nach, vorrang)] in ihrer Reihenfolge; 'reihenfolge' (Ziel wenig Rüsten) setzt die
        Reihenfolge mehrerer Aufträge fest: vorrang = {Auftrag-ID: Vorrang}. Ergebnis: der Stand davor für
        „Rückgängig“ (optimierung_zurueck)."""
        davor = []
        for s in schritte:
            if s["art"] == "reihenfolge":
                with self.con:
                    self.con.execute("BEGIN")
                    for i, v in (s.get("vorrang") or {}).items():
                        a = self.auftrag(i)
                        if a is None or a["status"] != OFFEN or a["gaenge"]:
                            continue
                        if not any(d["id"] == i for d in davor):
                            davor.append(dict(id=i, maschine=a["maschine"], vorrang=int(a["vorrang"] or 0)))
                        self.con.execute("UPDATE auftraege SET vorrang = ?, geaendert = ? WHERE id = ?",
                                         (int(v), _jetzt(), i))
                    self._verlauf(s["id"], "automatische Optimierung übernommen (hinter gleiches Material gestellt)")
                continue
            a = self.auftrag(s["id"])
            if a is None or a["status"] == FERTIG or a["gaenge"]:
                continue
            if not any(d["id"] == a["id"] for d in davor):
                davor.append(dict(id=a["id"], maschine=a["maschine"], vorrang=int(a["vorrang"] or 0)))
            if s["art"] == "maschine":
                self.maschine_wechseln(a["id"], s["nach"])
            else:
                self.vorrang_setzen(a["id"], 1 if s["art"] == "vorziehen" else 0)
            self._verlauf(a["id"], "automatische Optimierung übernommen")
        return davor

    def optimierung_zurueck(self, davor):
        """Rückgängig für optimierung_uebernehmen(): Maschine und Reihenfolge wie davor."""
        with self.con:
            self.con.execute("BEGIN")
            for d in davor:
                a = self.auftrag(d["id"])
                if a is None or a["status"] == FERTIG:
                    continue
                self._maschine_wechseln(a, None, d["maschine"], pruefen=False)
                self.con.execute("UPDATE auftraege SET vorrang = ?, geaendert = ? WHERE id = ?",
                                 (d["vorrang"], _jetzt(), d["id"]))
                self._verlauf(d["id"], "automatische Optimierung rückgängig gemacht")

    def zuruecksetzen(self, davor):
        """Rückgängig für festlegen(): Platz und Maschine wie davor."""
        a = self.auftrag(davor["id"])
        if a is None:
            return
        g = next((x for x in a["gaenge"] if x["id"] == davor.get("gang_id")), None)
        with self.con:
            self.con.execute("BEGIN")
            self._maschine_wechseln(a, g, davor["maschine"], pruefen=False)
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

    def offene_stopps(self):
        """V3: Unterbrechungen mit Grund, die noch andauern, bei Aufträgen und Arbeitsgängen, die nicht fertig sind.
        [dict(auftrag_id, gang_id, maschine, wann, grund, nummer, kunde)], älteste zuerst."""
        return [dict(z) for z in self.con.execute(
            "SELECT s.auftrag_id, s.gang_id, s.maschine, s.wann, s.grund, a.nummer, a.kunde FROM stopps s "
            "JOIN auftraege a ON a.id = s.auftrag_id LEFT JOIN gaenge g ON g.id = s.gang_id "
            "WHERE s.weiter_am IS NULL AND a.status <> ? AND (s.gang_id IS NULL OR COALESCE(g.status, '') <> ?) "
            "ORDER BY s.wann, s.id", (FERTIG, FERTIG))]

    def wartet_auf_material(self, a, heute=None):
        """Tag, ab dem das Material da ist, solange der Auftrag darauf wartet (noch nicht begonnen, Tag in der
        Zukunft); sonst None."""
        try:
            tag = datetime.date.fromisoformat(a.get("material_ab") or "")
        except ValueError:
            return None
        if tag <= (heute or datetime.date.today()) or a["status"] == FERTIG or not self.funktion("material_ab"):
            return None
        teile = a["gaenge"] or [a]
        if any(t["start_am"] or t["gelaufen_min"] or t["status"] == FERTIG for t in teile):
            return None                           # schon begonnen: das Material ist offenbar da
        return tag

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

    def fertig_melden(self, auftrag_id, ist_min, fertig_am=None, gang_id=None, fertig_um=None):
        """Fertigmeldung mit der tatsächlichen Laufzeit in Minuten. Bei einem mehrteiligen Auftrag wird der
        Arbeitsgang gang_id gemeldet (Vorgabe: der nächste, der an der Reihe ist); mit dem letzten ist der Auftrag
        fertig. Fremdarbeit braucht keine Laufzeit. fertig_um: Uhrzeit der Fertigmeldung ('14:30'), None = unbekannt."""
        um = uhr_text(uhrzeit(fertig_um)) if fertig_um not in (None, "") else None
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
            self.con.execute("UPDATE gaenge SET status = ?, ist_min = ?, fertig_am = ?, fertig_um = ?, start_am = NULL "
                             "WHERE id = ?", (FERTIG, max(0, ist), tag, um, g["id"]))
            self._abgleichen(auftrag_id)
            self._verlauf(auftrag_id, f"{g['name']}: fertig gemeldet" + (
                f" (tatsächlich {_zeigen('Kalkulierte Laufzeit', ist)})" if g["platz"] != FREMD else ""))
            return
        self.con.execute("UPDATE auftraege SET status = ?, ist_min = ?, fertig_am = ?, fertig_um = ?, start_am = NULL, "
                         "vorrang = 0, fest_ab = NULL, "
                         "geaendert = ? WHERE id = ?", (FERTIG, ist, tag, um, _jetzt(), auftrag_id))
        self._verlauf(auftrag_id, f"fertig gemeldet (tatsächlich {_zeigen('Kalkulierte Laufzeit', ist)})")

    def wieder_oeffnen(self, auftrag_id):
        """Fertigmeldung zurücknehmen; die tatsächliche Laufzeit bleibt als gelaufene Zeit stehen."""
        a = self.auftrag(auftrag_id)
        if a and a["gaenge"]:                     # mehrteilig: der zuletzt gemeldete Arbeitsgang ist wieder offen
            fertige = [g for g in a["gaenge"] if g["status"] == FERTIG]
            if fertige and not any(g["status"] != FERTIG and (g["start_am"] or g["gelaufen_min"])
                                   for g in a["gaenge"] if g["stufe"] > fertige[-1]["stufe"]):
                g = fertige[-1]
                self.con.execute("UPDATE gaenge SET status = ?, gelaufen_min = ?, ist_min = NULL, fertig_am = NULL, fertig_um = NULL "
                                 "WHERE id = ?", (OFFEN, int(g["ist_min"] or 0), g["id"]))
                self._abgleichen(auftrag_id)
                self._verlauf(auftrag_id, f"{g['name']}: wieder geöffnet")
            return
        if a and a["status"] == FERTIG:
            self.con.execute("UPDATE auftraege SET status = ?, gelaufen_min = ?, ist_min = NULL, fertig_am = NULL, fertig_um = NULL, "
                             "geaendert = ? WHERE id = ?", (OFFEN, int(a["ist_min"] or 0), _jetzt(), auftrag_id))
            self._verlauf(auftrag_id, "wieder geöffnet")

    # ------------------------------------------------------------------ Arbeitsgänge und Teile auf mehreren Maschinen
    def funktion(self, name):
        """E5/M1/M2 (Plan 2.3): Zusatzfunktion an? Gespeichert als Einstellung funktion_<name> = 1 oder 0. Ohne
        Einstellung: Material und Rüsten nur an, wenn schon Material, Rüstzeit oder Rohrmaße eingetragen sind;
        Material da ab nur, wenn ein Auftrag es nutzt; alles andere an. Daten bleiben beim Ausschalten erhalten."""
        wert = self.einstellung(f"funktion_{name}")
        if wert in ("0", "1"):
            return wert == "1"
        if name == "material":
            return bool(self.con.execute(
                "SELECT 1 FROM auftraege WHERE COALESCE(material, '') <> '' OR ruest_min IS NOT NULL "
                "OR COALESCE(durchmesser, 0) > 0 OR COALESCE(laenge, 0) > 0 LIMIT 1").fetchone() or self.con.execute(
                "SELECT 1 FROM maschinen WHERE COALESCE(ruest_min, 0) > 0 OR COALESCE(max_durchmesser, 0) > 0 "
                "OR COALESCE(max_laenge, 0) > 0 LIMIT 1").fetchone())
        if name == "material_ab":
            return bool(self.con.execute(
                "SELECT 1 FROM auftraege WHERE COALESCE(material_ab, '') <> '' LIMIT 1").fetchone())
        if name == "zusatzschritte":              # Plan 2.6: in neuen Datenbanken aus
            return bool(self.con.execute("SELECT 1 FROM gaenge WHERE zusatz <> '' LIMIT 1").fetchone())
        return True

    def funktion_setzen(self, name, an):
        self.einstellung_setzen(f"funktion_{name}", "1" if an else "0")

    # ------------------------------------------------------------------ Zusatzschritte (Plan 2.6)
    def richtzeiten(self):
        """Tabelle der Richtzeiten: [dict(id, schritt, art, je_s, ruest_min, handling_s, platz, tage, stichwort,
        geschaetzt, reihenfolge)]; platz '' = Fremdarbeit (dann zählt nur tage)."""
        return [dict(z) for z in self.con.execute("SELECT * FROM richtzeiten ORDER BY reihenfolge, id")]

    def richtzeit_speichern(self, r, id=None):
        """Zeile anlegen (ohne id) oder ändern. Eine geänderte Zeit je Stück gilt als eigener Wert (keine Schätzung
        mehr), außer r['geschaetzt'] sagt es anders. Ergebnis: id."""
        schritt = " ".join(str(r.get("schritt") or "").split())
        art = " ".join(str(r.get("art") or "").split())
        if not schritt:
            raise Fehler("Der Zusatzschritt braucht einen Namen (z. B. Gewinde schneiden).")
        platz = str(r.get("platz") or "").strip()
        platz = FREMD if platz.lower() == FREMD_TEXT.lower() else platz
        je = _zahl(r.get("je_s") or 0, "Zeit je Stück", 24 * 3600)
        ruest = _zahl(r.get("ruest_min") or 0, "Rüsten", 24 * 60)
        handling = _zahl(r.get("handling_s") or 0, "Handling je Teil", 24 * 3600)
        tage = _zahl(r.get("tage") or 0, "Arbeitstage", 365, ganz=True)
        if platz == FREMD and not tage:
            raise Fehler(f"{schritt}: Fremdarbeit braucht eine Dauer in Arbeitstagen (z. B. 5).")
        if platz != FREMD and je <= 0:
            raise Fehler(f"{schritt} {art}: Bitte eine Zeit je Stück über 0 eingeben.".replace("  ", " "))
        doppelt = self.con.execute("SELECT id FROM richtzeiten WHERE schritt = ? AND art = ?", (schritt, art)).fetchone()
        if doppelt and doppelt[0] != id:
            raise Fehler(f"„{schritt} {art}“ steht schon in der Tabelle.".replace(" “", "“"))
        alt = self.con.execute("SELECT * FROM richtzeiten WHERE id = ?", (id,)).fetchone() if id else None
        geschaetzt = r.get("geschaetzt")
        if geschaetzt is None:
            geschaetzt = int(alt["geschaetzt"]) if alt and abs(float(alt["je_s"]) - je) < 1e-9 else 0
        werte = (schritt, art, je, ruest, handling, platz, int(tage), " ".join(str(r.get("stichwort") or "").split()),
                 int(bool(geschaetzt)))
        if alt:
            self.con.execute("UPDATE richtzeiten SET schritt = ?, art = ?, je_s = ?, ruest_min = ?, handling_s = ?, "
                             "platz = ?, tage = ?, stichwort = ?, geschaetzt = ? WHERE id = ?", werte + (id,))
            return id
        n = self.con.execute("SELECT COALESCE(MAX(reihenfolge), 0) + 1 FROM richtzeiten").fetchone()[0]
        return self.con.execute("INSERT INTO richtzeiten (schritt, art, je_s, ruest_min, handling_s, platz, tage, "
                                "stichwort, geschaetzt, reihenfolge) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                werte + (n,)).lastrowid

    def richtzeit_loeschen(self, id):
        self.con.execute("DELETE FROM richtzeiten WHERE id = ?", (id,))

    def zusatz_gemeldet(self):
        """Fertig gemeldete Zusatzschritte für die Vorschläge (Z3): [dict(zusatz, ist_min, stueck)]."""
        return [dict(zusatz=z[0], ist_min=z[1], stueck=z[2]) for z in self.con.execute(
            "SELECT g.zusatz, g.ist_min, a.stueckzahl FROM gaenge g JOIN auftraege a ON a.id = g.auftrag_id "
            "WHERE g.status = ? AND g.zusatz <> '' AND COALESCE(g.ist_min, 0) > 0 AND a.geloescht_am IS NULL",
            (FERTIG,))]

    def zusatz_vorschlaege(self):
        return Z.vorschlaege(self.zusatz_gemeldet(), self.richtzeiten())

    def fremd_tage(self):
        """Wochentage, an denen Fremdarbeit abgeholt und angeliefert wird (0 = Montag); leere Menge = jeder Tag."""
        return Z.tage_lesen(self.einstellung("fremd_tage", ""))

    # V10 (Plan 2.7): Kundenpriorität A/B/C. B ist der Normalfall; A-Kunden werden so eingeplant, als läge ihr
    # Liefertermin prio_tage Kalendertage früher, C-Kunden so viele Tage später. Gespeichert als JSON {Kunde: Stufe}.
    def kunden(self):
        """Alle Kunden der Aufträge (ohne leere), alphabetisch."""
        return [z[0] for z in self.con.execute(
            "SELECT DISTINCT kunde FROM auftraege WHERE TRIM(kunde) <> '' ORDER BY kunde COLLATE NOCASE")]

    def prioritaeten(self):
        """{Kunde (klein geschrieben): 'A' oder 'C'}; Kunden mit B stehen nicht darin."""
        try:
            roh = json.loads(self.einstellung("kunden_prio", "") or "{}")
        except ValueError:
            roh = {}
        return {str(k).strip().casefold(): v for k, v in roh.items() if v in ("A", "C") and str(k).strip()}

    def prioritaet(self, kunde):
        return self.prioritaeten().get(str(kunde or "").strip().casefold(), "B")

    def prioritaet_setzen(self, kunde, stufe):
        kunde = str(kunde or "").strip()
        if not kunde:
            return
        try:
            roh = json.loads(self.einstellung("kunden_prio", "") or "{}")
        except ValueError:
            roh = {}
        roh = {k: v for k, v in roh.items() if str(k).strip().casefold() != kunde.casefold()}
        if stufe in ("A", "C"):
            roh[kunde] = stufe
        self.einstellung_setzen("kunden_prio", json.dumps(roh, ensure_ascii=False, sort_keys=True))

    def zusatz_einschalten(self, an=True):
        """Funktion Zusatzschritte schalten. An: auch Arbeitsgänge an, fehlende Arbeitsplätze aus der Tabelle
        anlegen (8 h je Tag, nicht als Ausweichmaschine). Ergebnis: Namen der neu angelegten Arbeitsplätze."""
        self.funktion_setzen("zusatzschritte", an)
        if not an:
            return []
        self.einstellung_setzen("arbeitsgaenge", "1")
        da = {m["name"] for m in self.maschinen()}
        neu = []
        for r in self.richtzeiten():
            if r["platz"] and r["platz"] not in da:
                self.maschine_speichern(r["platz"], 8.0, ausweich=False)
                da.add(r["platz"])
                neu.append(r["platz"])
        return neu

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
            g["zusatz"] = Z.positionen(g.get("zusatz"))
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
                            gleichzeitig=int(bool(g.get("gleichzeitig")) and bool(out)),
                            zusatz=json.dumps(Z.positionen(g.get("zusatz")), ensure_ascii=False)
                            if Z.positionen(g.get("zusatz")) else ""))
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
            werte = (pos, g["name"], g["platz"], g["kalk_min"], g["tage"], g["gleichzeitig"], g.get("zusatz") or "")
            if g.get("id") in alt:
                self.con.execute("UPDATE gaenge SET pos = ?, name = ?, platz = ?, kalk_min = ?, tage = ?, "
                                 "gleichzeitig = ?, zusatz = ? WHERE id = ?", werte + (g["id"],))
            else:
                self.con.execute("INSERT INTO gaenge (pos, name, platz, kalk_min, tage, gleichzeitig, zusatz, "
                                 "auftrag_id, gelaufen_min) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            fertig_am, fertig_um = max((g["fertig_am"] or "", g["fertig_um"] or "") for g in gaenge)
            fertig_am, fertig_um = fertig_am or None, fertig_um or None
        else:
            begonnen = fertig or any(g["start_am"] or g["gelaufen_min"] for g in gaenge)
            status, ist, fertig_am, fertig_um = (LAEUFT if begonnen else OFFEN), None, None, None
        self.con.execute(
            "UPDATE auftraege SET maschine = ?, kalk_min = ?, status = ?, ist_min = ?, fertig_am = ?, fertig_um = ?, "
            "gelaufen_min = ?, "
            "start_am = NULL, vorrang = CASE WHEN ? = 'fertig' THEN 0 ELSE vorrang END, geaendert = ? WHERE id = ?",
            (_plaetze_text(gaenge), sum(g["kalk_min"] for g in gaenge), status, ist, fertig_am, fertig_um,
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
        if name is None and self.nur_ansehen:     # ohne gültige Lizenz: nur ansehen (Plan 2.4)
            return LESEN
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
