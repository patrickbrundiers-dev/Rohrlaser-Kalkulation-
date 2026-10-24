"""Prüft „Beauftragt“ mit Auftragsnummer und Liefertermin (Plan „Arbeitsabläufe effizienter“ W8, Schritt AB4):
Fenster beim Setzen auf Beauftragt, Vorschlag des Termins aus der Lieferzeit, Abbrechen setzt nichts, Spalten und
Suche in der Angebotsliste; Kopie und neue Fassung übernehmen beides nicht.

Aufruf: python tests/test_auftrag.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QDate, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import auftrag  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import ARBEITSTAGE, KALENDERWOCHE, LIEFERDATUM, NUR_TEXT, WOCHEN  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Vorschlag des Liefertermins
fr = datetime.date(2026, 10, 23)                     # ein Freitag
v = auftrag.termin_vorschlag
assert v(dict(lieferzeit_art=ARBEITSTAGE, lieferzeit_wert="3"), fr) == datetime.date(2026, 10, 28)
assert v(dict(lieferzeit_art=WOCHEN, lieferzeit_wert="2"), fr) == datetime.date(2026, 11, 6)
assert v(dict(lieferzeit_art=KALENDERWOCHE, lieferzeit_wert="46/2026"), fr) == datetime.date(2026, 11, 13)
assert v(dict(lieferzeit_art=LIEFERDATUM, lieferzeit_wert="2026-12-01"), fr) == datetime.date(2026, 12, 1)
assert v(dict(lieferzeit_art=NUR_TEXT), fr) == fr + datetime.timedelta(days=14) == v({}, fr)
assert v(dict(lieferzeit_art=WOCHEN, lieferzeit_wert="2", liefertermin="2027-01-08"), fr) == datetime.date(2027, 1, 8)
ok("Termin-Vorschlag: Arbeitstage, Wochen, Freitag der KW, Lieferdatum, sonst 14 Tage; eingetragener Termin zuerst")

# ------------------------------------------------------------------ Datenbank
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert SCHEMA_VERSION >= 54
a = db.angebot_neu()
assert db.angebot(a)["auftragsnr"] is None and db.angebot(a)["liefertermin"] is None
db.auftrag_setzen(a, " B-4711 ", "2026-11-13")
k = db.angebot(a)
assert (k["auftragsnr"], k["liefertermin"]) == ("B-4711", "2026-11-13")
assert [z["id"] for z in db.angebote("4711")] == [a]
ok("Spalten auftragsnr/liefertermin (Schema 54), Suche findet die Auftragsnummer")

# Datei mit Schema 53 (ohne die Spalten): Sicherung vor_Schema_54, Spalten leer ergänzt, Angebote bleiben
alt = tmp / "alt.db"
d0 = Datenbank(alt)
n0 = len(d0.angebote())
d0.con.execute("ALTER TABLE angebote DROP COLUMN auftragsnr")
d0.con.execute("ALTER TABLE angebote DROP COLUMN liefertermin")
d0.con.execute("PRAGMA user_version = 53")
d0.con.commit()
d0.con.close()
d1 = Datenbank(alt)
assert d1.sicherungen(zusatz="vor_Schema_54") and len(d1.angebote()) == n0
assert all(z["auftragsnr"] is None and z["liefertermin"] is None for z in d1.angebote())
ok("Umstellung von Schema 53: Sicherung vor_Schema_54, neue Spalten leer")

# Kopie und neue Fassung: ohne Auftragsnummer und Termin
for neu in (db.angebot_kopieren(a), db.angebot_fassung(a)):
    assert db.angebot(neu)["auftragsnr"] is None and db.angebot(neu)["liefertermin"] is None
ok("Kopie und neue Fassung übernehmen Auftragsnummer und Termin nicht")

# ------------------------------------------------------------------ Oberfläche
fenster = Hauptfenster(db, tmp, stumm=True)
liste = fenster.angebote
b = db.angebot_neu()
liste.neu_laden()
titel = [s[0] for s in liste.SPALTEN]
assert liste.vorgang_setzen("Beauftragt", b, auftrag=("K-99", "2026-12-04"))
k = db.angebot(b)
assert k["vorgang"] == "Beauftragt" and (k["auftragsnr"], k["liefertermin"]) == ("K-99", "2026-12-04")
assert "Auftrag K-99" in fenster.statusBar().currentMessage() and "04.12.2026" in fenster.statusBar().currentMessage()
r = next(r for r in range(liste.modell.rowCount()) if liste.modell.zeilen[r]["id"] == b)
assert liste.modell.data(liste.modell.index(r, titel.index("Auftragsnr."))) == "K-99"
assert liste.modell.data(liste.modell.index(r, titel.index("Liefertermin"))) == "04.12.2026"
assert not liste.ansicht.isColumnHidden(titel.index("Liefertermin"))
ok("Vorgang Beauftragt mit Auftragsnummer und Termin: gespeichert, Statuszeile, Spalten in der Angebotsliste")

# Fenster: Vorschlag, Häkchen „Liefertermin“, Abbrechen setzt nichts
c = db.angebot_neu(dict(lieferzeit_art=WOCHEN, lieferzeit_wert="3"))
d = auftrag.AuftragDialog(None, db.angebot(c))
assert d.mit_termin.isChecked() and d.termin.date() == QDate(datetime.date.today() + datetime.timedelta(weeks=3))
d.nummer.setText("  ")
d.mit_termin.setChecked(False)
assert d.werte() == (None, None) and not d.termin.isEnabled()
fenster.stumm = False
QTimer.singleShot(0, lambda: next(w for w in app.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()).reject())
assert not liste.vorgang_setzen("Beauftragt", c)
assert (db.angebot(c).get("vorgang") or "Entwurf") == "Entwurf"


def fuellen():
    w = next(w for w in app.topLevelWidgets() if isinstance(w, auftrag.AuftragDialog) and w.isVisible())
    w.nummer.setText("PO 123")
    w.accept()


QTimer.singleShot(0, fuellen)
assert liste.vorgang_setzen("Beauftragt", c)
k = db.angebot(c)
assert k["vorgang"] == "Beauftragt" and k["auftragsnr"] == "PO 123" and k["liefertermin"]
fenster.stumm = True
ok("Fenster: Termin aus der Lieferzeit vorgeschlagen, ohne Termin möglich, Abbrechen = Vorgang bleibt")

# Andere Vorgänge fragen nichts und lassen die Werte stehen; Lesemodus ändert nichts
assert liste.vorgang_setzen("Abgelehnt", c) and db.angebot(c)["auftragsnr"] == "PO 123"
db.nur_lesen = "Test"
try:
    liste.vorgang_setzen("Beauftragt", c, auftrag=("X", None))
except Exception:
    pass
db.nur_lesen = None
assert db.angebot(c)["auftragsnr"] == "PO 123"
ok("Andere Vorgänge ohne Fenster, Werte bleiben; Lesemodus ändert nichts")

print("Alle Prüfungen bestanden.")
