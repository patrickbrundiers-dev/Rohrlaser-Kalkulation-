"""Datendatei bei vielen Angeboten: Indizes, gepackter Schnittplan, Sicherung im Hintergrund.

Indizes für viele Angebote (Prüfung „Datenbank bei vielen Angeboten“, 28.10.2026): Staffeln, Mengenstufen und
STEP-Protokoll werden je Angebot über einen Index gesucht, nicht über die ganze Tabelle. Auch eine ältere Datei ohne
diese Indizes bekommt sie beim Öffnen (ohne Schema-Wechsel); Löschen eines Angebots räumt weiter alles ab.

Aufruf: python tests/test_datenbank_indizes.py
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import db_roh  # noqa: E402
from rohrlaser import db_verbindung  # noqa: E402
import beispiel_angebot  # noqa: E402

from rohrlaser.datenbank import Datenbank, datei_info  # noqa: E402

TABELLEN = ("staffeln", "staffel_stufen", "step_protokoll")


def plan(con, tabelle):
    return db_roh.plan(con, f"SELECT * FROM {tabelle} WHERE angebot_id=?", (1,))


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
for t in TABELLEN:
    assert f"{t}_angebot" in plan(db.con, t), plan(db.con, t)
print("OK     neue Datei: Staffeln, Mengenstufen, STEP-Protokoll über Index je Angebot")

a = beispiel_angebot.anlegen(db)
db.staffel_stufe_neu(a)
db.protokoll_anhaengen(a, ["Zeile 1", "Zeile 2"])
db.schliessen()
con = db_roh.verbinden(tmp / "rohrlaser.db")          # Stand vor dieser Version: ohne die Indizes
for t in TABELLEN:
    con.execute(f"DROP INDEX {t}_angebot")
    assert "SCAN" in plan(con, t)
con.commit()
con.close()
db = Datenbank(tmp / "rohrlaser.db")
for t in TABELLEN:
    assert f"{t}_angebot" in plan(db.con, t), plan(db.con, t)
assert len(db.staffeln(a)) == len(beispiel_angebot.STAFFELN) and len(db.protokoll(a)) == 2
print("OK     ältere Datei bekommt die Indizes beim Öffnen, Daten unverändert")

db.angebot_loeschen(a)
for t in TABELLEN:
    assert db.con.execute(f"SELECT COUNT(*) FROM {t} WHERE angebot_id=?", (a,)).fetchone()[0] == 0, t
print("OK     Angebot löschen entfernt Staffeln, Mengenstufen und Protokoll")

# Schnittplan gepackt (Schema 67): neu gespeichert gepackt, ältere Datei wird beim Öffnen umgestellt, geteilt als Text
from rohrlaser import teilen  # noqa: E402

erg = dict(stangen=[dict(laenge=6000, teile=[dict(ref="10", laenge=1250.0)] * 4)], auswertung=dict(stangen=1))
b = beispiel_angebot.anlegen(db)
db.ergebnis_speichern(b, erg)
assert db_roh.typ(db.con, "ergebnis", "angebote", "id=?", (b,)) == "blob"
assert db.angebot(b)["ergebnis"] == erg
inhalt, _ = teilen.angebot_inhalt(db.con, b)
assert json.loads(inhalt["kopf"]["ergebnis"]) == erg
db.schliessen()
alt = db_roh.als_sqlite(Datenbank(tmp / "rohrlaser.db"), tmp / "alt67" / "rohrlaser.db")     # alte Stände: SQLite
c = sqlite3.connect(alt)
c.execute("UPDATE angebote SET ergebnis=? WHERE id=?", (json.dumps(erg), b))     # Stand vor Schema 67
db_verbindung.schema_version_setzen(c, 65)
c.commit()
c.close()
db = Datenbank(alt)
assert db_roh.typ(db.con, "ergebnis", "angebote", "id=?", (b,)) == "blob"
assert db.angebot(b)["ergebnis"] == erg
print("OK     Schnittplan gepackt gespeichert, ältere Datei umgestellt, im gemeinsamen Ordner als Text")

# tägliche Sicherung im Hintergrund: eigene Verbindung, das Programm speichert währenddessen weiter
for x in (db.pfad.parent / "Sicherung").glob("*.db"):
    x.unlink()
lauf = db.sicherung_heute(hintergrund=True)
for i in range(20):
    db.angebot_aendern(b, "bemerkung", f"während der Sicherung {i}")
assert lauf.warten(60) and lauf.fehler is None and lauf.pfad.is_file(), lauf.fehler
assert datei_info(lauf.pfad)["anzahl"]["angebote"] == db.anzahl("angebote")
assert db.sicherung_heute(hintergrund=True) is None          # heute schon gesichert
print("OK     tägliche Sicherung im Hintergrund, Speichern geht währenddessen weiter")
db.schliessen()
print("Alle Index-Prüfungen bestanden.")
