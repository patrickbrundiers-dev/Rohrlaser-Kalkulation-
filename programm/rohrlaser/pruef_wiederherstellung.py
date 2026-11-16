"""Prüf-Wiederherstellung (Plan Datenbank-Modernisierung, Phase 7; F8 „wöchentliche Prüf-Wiederherstellung“). Ohne Qt.

Eine Sicherung ist erst etwas wert, wenn sie sich wiederherstellen lässt. Einmal je Woche (nach der täglichen
Sicherung, im Hintergrund) holt das Programm die neueste Sicherung probeweise zurück, genau auf dem Weg, den
„Sicherung wiederherstellen …“ geht, aber in einen Probeort statt über die Daten:

- SQLite-Datendatei: Kopie der Sicherung in einen temporären Ordner, mit dem Programm öffnen (Schema-Umbau wie beim
  echten Zurückholen), Integrität prüfen, Anzahl Angebote/Positionen/Kunden/Preise mit der Beschreibung der Sicherung
  vergleichen.
- PostgreSQL auf diesem PC: zusätzlich in eine eigene Probe-Datenbank auf dem eingebetteten Server einlesen
  (db_kopie.sqlite_nach_pg) und jede Tabelle Zeile für Zeile mit der Sicherung vergleichen; danach wird die
  Probe-Datenbank wieder gelöscht.

Das Ergebnis steht in Sicherung/pruef_wiederherstellung.json (Datum, Sicherung, ok, Text) und erscheint im Dialog
„Sicherung wiederherstellen …“; misslingt die Probe, meldet das Programm es rot.
"""
import datetime
import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

DATEI = "pruef_wiederherstellung.json"
ALLE_TAGE = 7


def ergebnis_datei(db):
    return Path(db.pfad).parent / "Sicherung" / DATEI


def letztes(db):
    """Letztes Ergebnis als dict (datum, sicherung, ok, text, dauer_s) oder None."""
    try:
        return json.loads(ergebnis_datei(db).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def faellig(db, heute=None):
    e = letztes(db)
    if not e or not e.get("datum"):
        return True
    heute = heute or datetime.date.today()
    try:
        return (heute - datetime.date.fromisoformat(e["datum"][:10])).days >= ALLE_TAGE or not e.get("ok")
    except ValueError:
        return True


def pruefen(db, sicherung, pg=None):
    """Sicherung probeweise wiederherstellen. pg: offene PostgreSQL-Hülle der laufenden Datenbank (dann zusätzlich der
    Weg in PostgreSQL) oder None. Ergebnis: dict(ok, text, …), wird auch gespeichert."""
    from . import db_verbindung
    from .datenbank import Datenbank, datei_info, datei_pruefen
    t = time.perf_counter()
    sicherung = Path(sicherung)
    ergebnis = dict(datum=datetime.datetime.now().isoformat(timespec="seconds"), sicherung=sicherung.name, ok=False)
    probe = Path(tempfile.mkdtemp(prefix="rohrlaser_probe_"))
    try:
        erwartet = datei_pruefen(sicherung)["anzahl"]
        kopie = probe / "rohrlaser.db"
        shutil.copy2(sicherung, kopie)
        d = Datenbank(kopie, verbindung=db_verbindung.SqliteVerbindung(kopie, fremdschluessel=False))
        try:
            d.con.commit()
        finally:
            d.schliessen()
        nach = datei_info(kopie)["anzahl"]
        abweichung = [f"{k}: {nach.get(k)} statt {v}" for k, v in erwartet.items() if nach.get(k) != v]
        if abweichung:
            raise RuntimeError("nach dem Öffnen andere Anzahlen (" + "; ".join(abweichung) + ")")
        text = (f"{sicherung.name} lässt sich wiederherstellen: {erwartet.get('angebote', 0)} Angebote, "
                f"{erwartet.get('positionen', 0)} Positionen")
        if pg is not None:
            text += _pg_probe(pg, sicherung)
        ergebnis.update(ok=True, text=text + ".")
    except Exception as e:      # noqa: BLE001 – Ergebnis der Probe, nie ein Absturz
        ergebnis.update(ok=False, text=f"Probe-Wiederherstellung von {sicherung.name} misslungen: {e}")
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    ergebnis["dauer_s"] = round(time.perf_counter() - t, 1)
    try:
        ziel = ergebnis_datei(db)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return ergebnis


def _pg_probe(pg, sicherung):
    """Sicherung in eine eigene Probe-Datenbank auf demselben Server einlesen und vergleichen; danach löschen."""
    from . import datenspeicher, db_kopie, db_verbindung
    from .datenbank import Datenbank
    v = pg.v if hasattr(pg, "v") else pg
    name = f"pruef_{int(time.time())}"
    v._roh(f'CREATE DATABASE "{name}"')
    try:
        probe = db_verbindung.PostgresVerbindung(dict(v.zugang, datenbank=name), v._passwort)
        d = Datenbank(sicherung, verbindung=probe)       # Tabellen wie im Programm (Pfad wird nicht geöffnet)
        try:
            quelle = sqlite3.connect(f"{sicherung.resolve().as_uri()}?mode=ro", uri=True)
            try:
                db_kopie.sqlite_nach_pg(quelle, d.con)
                unterschiede = datenspeicher.vergleichen(quelle, d.con)
            finally:
                quelle.close()
        finally:
            d.schliessen()
    finally:
        v._roh(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    if unterschiede:
        raise RuntimeError("in PostgreSQL eingelesen weicht ab (" + "; ".join(unterschiede[:5]) + ")")
    return "; auch in PostgreSQL eingelesen und jede Tabelle verglichen"


def text(db):
    """Eine Zeile für Dialoge."""
    e = letztes(db)
    if not e:
        return "Probe-Wiederherstellung: noch keine (läuft einmal je Woche nach der täglichen Sicherung)."
    try:
        wann = datetime.datetime.fromisoformat(e.get("datum") or "").strftime("%d.%m.%Y %H:%M")
    except ValueError:
        wann = ""
    return f"Probe-Wiederherstellung {wann}: {e.get('text', '')}"
