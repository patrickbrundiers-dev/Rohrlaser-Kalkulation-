"""Suche ohne Groß- und Kleinschreibung (Patrick 20.11.2026: „Bei der Suche groß und Kleinschreibung ignorieren“).

In SQLite unterschied LIKE A–Z nicht, in PostgreSQL schon: Seit dem Umzug fand „müller“ den Kunden „Müller“ nicht
mehr. Die Suchen schreiben jetzt suchtext(spalte) LIKE suchtext(?); geprüft werden:
- die Regel selbst (A–Z, Umlaute, ẞ, Akzente) und die Übersetzung nach PostgreSQL,
- dieselbe Funktion in SQLite (Archivdateien, Austausch),
- die Angebotssuche (Nummer, Kunde, Kundennummer, Artikel, Bezeichnung) in der echten Datenbank,
- der Änderungsverlauf und die Python-Filter (Positionsvorlagen, Aufträge, Materialanfragen, Einstellungen).

Aufruf: python tests/test_suche_gross_klein.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import db_verbindung as dv  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


def regel():
    assert dv.suchtext("Müller STAHLBAU GmbH") == "müller stahlbau gmbh"
    assert dv.suchtext("ÄÖÜ ẞ") == "äöü ß"
    assert dv.suchtext("ÉCOLE Ñandú") == "école ñandú"
    assert dv.suchtext(None) is None and dv.suchtext(42) == "42"
    assert len(dv.SUCH_GROSS) == len(dv.SUCH_KLEIN)
    sql = dv.nach_postgres("SELECT id FROM angebote WHERE suchtext(kunde) LIKE suchtext(?)")
    assert sql.count("translate(lower(") == 2 and "%s" in sql and "suchtext" not in sql, sql
    ok("Regel: A–Z, Umlaute, ẞ und Akzente klein; PostgreSQL bekommt translate(lower(…))")


def sqlite_funktion():
    con = sqlite3.connect(":memory:")
    dv.suchtext_anmelden(con)
    con.execute("CREATE TABLE t (name TEXT)")
    con.executemany("INSERT INTO t VALUES (?)", [("Müller",), ("ÖLMÜHLE Süd",), ("Schulz",)])
    n = lambda s: [r[0] for r in con.execute("SELECT name FROM t WHERE suchtext(name) LIKE suchtext(?)",  # noqa: E731
                                             (f"%{s}%",))]
    assert n("MÜLLER") == ["Müller"] and n("ölmühle") == ["ÖLMÜHLE Süd"] and n("SCHULZ") == ["Schulz"]
    ok("SQLite (Archiv, Austausch): suchtext() findet „MÜLLER“, „ölmühle“, „SCHULZ“")


def angebote():
    po = Path(tempfile.mkdtemp())
    (po / "Daten").mkdir()
    db = Datenbank(po / "Daten" / "rohrlaser.db")
    a = db.angebot_neu(dict(nummer="A-2026-0815", kunde="Müller Stahlbau ÖSTERREICH", kundennr="K10417"))
    db.position_neu(a, dict(pos=10, artikel="GL-100a", bezeichnung="Handlauf Edelstahl", profil_id="", werkstoff_id="",
                            laenge=1000, stueck=1))
    db.angebot_neu(dict(nummer="A-2026-0816", kunde="Schulz", kundennr="K2"))
    for such in ("müller", "MÜLLER", "stahlBAU", "österreich", "a-2026-0815", "k10417", "gl-100A", "HANDLAUF",
                 "edelSTAHL"):
        treffer = [z["nummer"] for z in db.angebote(such)]
        assert treffer == ["A-2026-0815"], (such, treffer)
    assert [z["nummer"] for z in db.angebote("schulz")] == ["A-2026-0816"]
    assert db.angebote("meier") == []
    ok(f"Angebotssuche ({dv.ist_sqlite(db.con) and 'SQLite' or 'PostgreSQL'}): Kunde, Nummer, Kundennummer, "
       "Artikel und Bezeichnung in jeder Schreibweise")
    from rohrlaser import aenderungsverlauf
    db.con.execute("SELECT 1")
    gefunden = aenderungsverlauf.eintraege(db.con, text="MÜLLER")
    ok(f"Änderungsverlauf: Suche läuft ohne Groß-/Kleinschreibung ({len(gefunden)} Einträge zu „MÜLLER“)")


def python_filter():
    from rohrlaser import auftraege, einstellungen_nav, materialanfragen, positionsvorlagen
    assert einstellungen_nav.passt("Angebot Gültigkeit", "GÜLTIGKEIT")
    assert positionsvorlagen.suchen([dict(name="Handlauf Müller", inhalt="", kategorie="")], "MÜLLER")
    assert materialanfragen.filtern([dict(kunde="Österreich")], suche="ÖSTERREICH")
    z = dict(nummer="AB-1", kunde="Müller", kundennr="", projekt="", bestellnr="", angebote=[], artikel=["GL-100a"],
             liefertermin=None, verantwortlich="")
    assert auftraege.filtern([z], suche="MÜLLER") and auftraege.filtern([z], suche="gl-100A")
    ok("Python-Filter (Einstellungen, Positionsvorlagen, Materialanfragen, Aufträge) ohne Groß-/Kleinschreibung")


if __name__ == "__main__":
    regel()
    sqlite_funktion()
    angebote()
    python_filter()
    print("Alle Prüfungen bestanden.")
