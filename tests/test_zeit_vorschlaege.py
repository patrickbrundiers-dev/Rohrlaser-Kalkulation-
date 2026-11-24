"""Zeitvorschläge für alle Arbeitsgänge (Plan Angebotskalkulation 16.11.2026, Paket K2): Fälle aus der
Nachkalkulation (Zeit je Arbeitsgang aus den Rückmeldungen), Vorschlag ab 3 Aufträgen im Fenster Kennwerte, Freigabe
ändert passende eigene Zusatzarbeiten und Verpackung, Rohrlaser/Schweißen/Bohren nur Vorschlag, Zurücknehmen.

Aufruf: python tests/test_zeit_vorschlaege.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import kennwerte, zeit_vorschlaege as zv  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.kennwerte_dialog import KennwerteDialog  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "r.db")
entgraten = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == "Entgraten")
bohren = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == "Bohren")
pal = db.neu("verpackung", dict(name="Europalette", preis=12.0, max_kg=1000, max_laenge=1200, zeit_bund=2.0))

# drei Aufträge: Entgraten 20 % länger, 25 %, 15 %; Rohrlaser 10 % länger; Verpackung einmal (zu wenig)
for i, (fe, fl) in enumerate(((1.2, 1.1), (1.25, 1.1), (1.15, 1.1))):
    a = db.angebot_neu(dict(kunde="Becker GmbH", kundennr="10023"))
    ag = dict(entgraten=dict(name="Entgraten", soll_s=600.0, ist_s=600.0 * fe, teile=40, faelle=1),
              laser=dict(name="Rohrlaser", soll_s=1200.0, ist_s=1200.0 * fl, teile=40, faelle=1))
    if i == 0:
        ag["verpack"] = dict(name="Verpackung", soll_s=100.0, ist_s=150.0, teile=40, faelle=1)
    db.nachkalkulation_speichern(a, dict(am=f"2026-11-1{i}", arbeitsgaenge=ag, soll=dict(zeilen=[], laufzeit=[])))

f = zv.faelle(db)
assert len(f) == 7 and {x["schluessel"] for x in f} == {("Entgraten",), ("Rohrlaser",), ("Verpackung",)}, f
v = {x["schluessel"][0]: x for x in kennwerte.vorschlaege(db) if x["quelle"] == zv.QUELLE}
assert v["Entgraten"]["status"] == "ok" and abs(v["Entgraten"]["faktor"] - 1.2) < 1e-6 and v["Entgraten"]["n"] == 3
assert v["Verpackung"]["status"] != "ok"
assert zv.betroffen_text(db, "entgraten") == "Entgraten (Preis bzw. Zeit je Stück)"
assert "nur Vorschlag" in zv.betroffen_text(db, "laser") and "nur Vorschlag" in zv.betroffen_text(db, "bohren")
ok("Fälle je Arbeitsgang, Vorschlag ab 3 Aufträgen, Wirkung vorab lesbar")

d = KennwerteDialog(None, db)
zeile = next(r for r, x in enumerate(d.vorschlaege) if x["quelle"] == zv.QUELLE and x["schluessel"] == ("Rohrlaser",))
assert d.freigeben(zeile, "Test") is None and "nur Vorschlag" in d.meldung.text()
zeile = next(r for r, x in enumerate(d.vorschlaege) if x["quelle"] == zv.QUELLE and x["schluessel"] == ("Entgraten",))
assert "Entgraten" in d.tab.item(zeile, 0).toolTip()
hid = d.freigeben(zeile, "Rückmeldungen Nov. geprüft")
assert hid
neu = next(z for z in db.zeilen("zusatzarbeiten") if z["id"] == entgraten["id"])
assert abs(neu["preis"] - round(entgraten["preis"] * 1.2, 2)) < 1e-9, neu
assert next(z for z in db.zeilen("zusatzarbeiten") if z["id"] == bohren["id"])["preis"] == bohren["preis"]
ok("Freigabe ändert nur die passende eigene Zusatzarbeit; Rohrlaser nur Vorschlag; Bohren bleibt (nur €/Stück)")

r = next(i for i, h in enumerate(d.historie) if h["id"] == hid)
assert d.zuruecknehmen(r) == 1
assert next(z for z in db.zeilen("zusatzarbeiten") if z["id"] == entgraten["id"])["preis"] == entgraten["preis"]
# Verpackung mit 3 Fällen: Bündeln je Stück × Faktor
for i in range(2):
    a = db.angebot_neu(dict(kunde="Becker GmbH"))
    db.nachkalkulation_speichern(a, dict(am="2026-11-15", soll=dict(zeilen=[], laufzeit=[]), arbeitsgaenge=dict(
        verpack=dict(name="Verpackung", soll_s=100.0, ist_s=150.0, teile=40, faelle=1))))
v = next(x for x in kennwerte.vorschlaege(db) if x["quelle"] == zv.QUELLE and x["schluessel"] == ("Verpackung",))
assert v["status"] == "ok" and abs(v["faktor"] - 1.5) < 1e-6
kennwerte.freigeben(db, v, "Test", "0")
assert next(z for z in db.zeilen("verpackung") if z["id"] == pal)["zeit_bund"] == 3.0
ok("Zurücknehmen stellt den alten Wert her; Verpackung ändert Bündeln je Stück")
print("test_zeit_vorschlaege OK")
