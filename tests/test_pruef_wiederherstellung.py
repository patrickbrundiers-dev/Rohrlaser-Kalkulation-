"""Probe-Wiederherstellung (Plan Datenbank-Modernisierung, Phase 7).

Prüft: einmal je Woche fällig (und wieder, wenn die letzte misslang), eine gute Sicherung lässt sich probeweise
wiederherstellen (gleiche Anzahlen, Ergebnisdatei), eine beschädigte oder abgeschnittene Sicherung wird erkannt, die
tägliche Sicherung im Hintergrund stößt die Probe an, der Dialog „Sicherung wiederherstellen …“ zeigt das Ergebnis.
Mit PostgreSQL (Datenspeicher je PC) wird die Sicherung zusätzlich in eine Probe-Datenbank eingelesen und verglichen;
das braucht die PostgreSQL-Programme und einen Nicht-root-Benutzer.

Aufruf: python tests/test_pruef_wiederherstellung.py
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

import beispiel_angebot  # noqa: E402
from rohrlaser import datenspeicher, db_verbindung, pg_lokal, pruef_wiederherstellung as pw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK     " + text)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "Daten" / "rohrlaser.db")
beispiel_angebot.anlegen(db, dict(nummer="2026-00001"))
beispiel_angebot.anlegen(db, dict(nummer="2026-00002"))
db.con.commit()

assert pw.faellig(db) and pw.letztes(db) is None and "noch keine" in pw.text(db)
s = db.sicherung(zusatz="probe")
e = pw.pruefen(db, s)
assert e["ok"], e
assert "2 Angebote" in e["text"] and pw.letztes(db)["ok"] and not pw.faellig(db)
assert pw.faellig(db, heute=datetime.date.today() + datetime.timedelta(days=7))
assert not pw.faellig(db, heute=datetime.date.today() + datetime.timedelta(days=6))
assert "lässt sich wiederherstellen" in pw.text(db)
ok(f"Gute Sicherung: {e['text']} ({e['dauer_s']} s), nächste Probe in 7 Tagen")

kaputt = tmp / "kaputt.db"
kaputt.write_bytes(Path(s).read_bytes()[: Path(s).stat().st_size // 3])
e = pw.pruefen(db, kaputt)
assert not e["ok"] and "misslungen" in e["text"], e
assert pw.faellig(db), "nach einer misslungenen Probe gleich wieder fällig"
ok("Abgeschnittene Sicherung erkannt: " + e["text"][:90])

# eine geänderte, aber in sich stimmige Datei ist wiederherstellbar
datei = tmp / "andere.db"
datei.write_bytes(Path(s).read_bytes())
import sqlite3  # noqa: E402
c = sqlite3.connect(datei)
c.execute("PRAGMA foreign_keys=OFF")
c.execute("DELETE FROM positionen WHERE id IN (SELECT id FROM positionen LIMIT 1)")
c.commit()
c.close()
assert pw.pruefen(db, datei)["ok"], "eine in sich stimmige Datei ist wiederherstellbar"
ok("In sich stimmige Datei: wiederherstellbar")

# tägliche Sicherung im Hintergrund stößt die Probe an
pw.ergebnis_datei(db).unlink()
for p in (tmp / "Daten" / "Sicherung").glob("*.db"):
    p.unlink()
lauf = db.sicherung_heute(hintergrund=True)
assert lauf.warten(120) and lauf.fehler is None and lauf.pruefung and lauf.pruefung["ok"], (lauf.fehler,
                                                                                         lauf.pruefung)
assert json.loads(pw.ergebnis_datei(db).read_text(encoding="utf-8"))["ok"]
ok("Tägliche Sicherung im Hintergrund: Probe-Wiederherstellung einmal je Woche")

# Dialog zeigt das Ergebnis
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.sicherung_dialog import WiederherstellenDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, tmp, stumm=True)
d = WiederherstellenDialog(fenster)
assert "lässt sich wiederherstellen" in d.findChild(QLabel, "probe_wiederherstellung").text()
d.close()
fenster.close()
ok("Dialog „Sicherung wiederherstellen …“ zeigt die letzte Probe")
db.schliessen()

# PostgreSQL: Sicherung zusätzlich in eine Probe-Datenbank einlesen
try:
    pg_lokal.programme()
    import psycopg  # noqa: F401
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise pg_lokal.PgFehlt("als root (initdb verweigert root)")
    if db_verbindung.pg_test_an():
        raise pg_lokal.PgFehlt("im Prüflauf gegen PostgreSQL")
except (pg_lokal.PgFehlt, ImportError) as e:
    print(f"PostgreSQL-Teil übersprungen: {e}")
else:
    pfad = tmp / "PG" / "rohrlaser.db"
    db = Datenbank(pfad)
    beispiel_angebot.anlegen(db, dict(nummer="2026-00003"))
    db.con.commit()
    datenspeicher.umstellen(db)
    db = Datenbank(pfad)
    s = db.sicherung(zusatz="probe")
    zweite = db.con.zweite()
    e = pw.pruefen(db, s, pg=zweite)
    zweite.close()
    assert e["ok"] and "PostgreSQL" in e["text"], e
    assert not [r for r in db.con.execute("SELECT datname FROM pg_database WHERE datname LIKE 'pruef_%'")]
    ok("PostgreSQL: Sicherung in Probe-Datenbank eingelesen, jede Tabelle verglichen, Probe-Datenbank gelöscht")
    db.schliessen()
    datenspeicher.alle_stoppen()
print("Alles in Ordnung.")
