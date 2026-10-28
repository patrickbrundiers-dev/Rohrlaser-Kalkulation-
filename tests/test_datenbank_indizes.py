"""Indizes für viele Angebote (Prüfung „Datenbank bei vielen Angeboten“, 28.10.2026): Staffeln, Mengenstufen und
STEP-Protokoll werden je Angebot über einen Index gesucht, nicht über die ganze Tabelle. Auch eine ältere Datei ohne
diese Indizes bekommt sie beim Öffnen (ohne Schema-Wechsel); Löschen eines Angebots räumt weiter alles ab.

Aufruf: python tests/test_datenbank_indizes.py
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import beispiel_angebot  # noqa: E402

from rohrlaser.datenbank import Datenbank  # noqa: E402

TABELLEN = ("staffeln", "staffel_stufen", "step_protokoll")


def plan(con, tabelle):
    return " ".join(str(r[-1]) for r in con.execute(f"EXPLAIN QUERY PLAN SELECT * FROM {tabelle} WHERE angebot_id=?",
                                                    (1,)))


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
for t in TABELLEN:
    assert f"{t}_angebot" in plan(db.con, t), plan(db.con, t)
print("OK     neue Datei: Staffeln, Mengenstufen, STEP-Protokoll über Index je Angebot")

a = beispiel_angebot.anlegen(db)
db.staffel_stufe_neu(a)
db.protokoll_anhaengen(a, ["Zeile 1", "Zeile 2"])
db.schliessen()
con = sqlite3.connect(tmp / "rohrlaser.db")          # Stand vor dieser Version: ohne die Indizes
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
db.schliessen()
print("Alle Index-Prüfungen bestanden.")
