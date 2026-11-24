"""Prüfangebote (Plan Angebotskalkulation 16.11.2026, Paket K4): markieren nur als Admin, Referenz mit Preis- und
Zeitbasis, nach einem Update einmal neu rechnen, Meldung ab 2 %, Kostenarten mit der größten Änderung, neue
Referenz, Angebot bleibt unverändert.

Aufruf: python tests/test_pruefangebote.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import VERSION, pruefangebote as pa  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
ids = []
for n in range(2):
    a = db.angebot_neu(dict(kunde="Becker GmbH", kundennr="10023", stange=6000, maschine="T03"))
    db.position_neu(a, dict(pos=1, artikel=f"R-{n}", bezeichnung="Teil", profil_id="RR 42,4x2,0",
                            werkstoff_id="S235-10219", laenge=1000 + 100 * n, stueck=40, schneidweg=300, einstiche=2,
                            zusatz='[{"name": "Entgraten"}]'))
    s = f.angebot_oeffnen(a)
    s.optimieren()
    s.neu_laden()
    f.angebot_schliessen(a)
    ids.append(a)
ohne = db.angebot_neu(dict(kunde="Becker GmbH"))

# nur Admin sieht den Menüpunkt
f.angebote.neu_laden()
f.angebote.ansicht.selectRow(0)
db.einstellung_setzen("passwort", "x")                      # Admin-Schutz an, nicht freigeschaltet
f.bereich.sitzung.sperren()
assert not any("Prüfangebot" in x.text() for x in f.angebote.kontextmenue(zeigen=False).actions())
f.bereich.sitzung.freischalten()
vorher = [db.angebot(i) for i in ids]
assert f.angebote.pruefangebot_umschalten(ids + [ohne]) == 2 and "optimieren" in f.letzte_meldung
assert sorted(pa.ids(db)) == sorted(ids)
f.angebote.ansicht.selectRow(0)
menue = f.angebote.kontextmenue(zeigen=False)
assert any(x.text() in ("Prüfangebot aufheben", "Als Prüfangebot markieren") for x in menue.actions())
ref = db.zusatz(ids[0], pa.SCHLUESSEL)
assert ref["verkauf"] > 0 and ref["version"] == VERSION and ref["preisbasis"] and ref["zeitbasis"], ref
ok("Markieren nur als Admin, Referenz mit Preis und Basis; ohne Schnittplan abgelehnt")

liste = pa.pruefen(db)
assert len(liste) == 2 and all(r["abweichung"] == 0 and not r["bausteine"] for r in liste), liste
# „Update“: Einstellung der letzten Prüfung ist eine andere Version -> einmal rechnen
db.einstellung_setzen(pa.VERSION_EINST, "0.9.1")
assert f._start_pruefangebote() == [] and "unverändert" in f.letzte_meldung
assert f._start_pruefangebote() is None                     # nur einmal je Version
ok("Nach einem Update einmal neu gerechnet: alle unverändert")

# „Programm-Update“ mit geändertem Rechenweg simulieren: Zusatzarbeiten doppelt -> Abweichung mit Kostenart
from rohrlaser import rechnen  # noqa: E402
orig = rechnen.zusatz_werte


def doppelt(*a, **kw):
    return [dict(z, betrag=2 * (z.get("betrag") or 0)) for z in orig(*a, **kw)]


rechnen.zusatz_werte = doppelt
db.einstellung_setzen(pa.VERSION_EINST, "0.9.2")
auff = f._start_pruefangebote()
assert len(auff) == 2 and "weichen" in f.letzte_meldung and f.letzte_aktion[0] == "Anzeigen", f.letzte_meldung
r = auff[0]
assert r["prozent"] > 0.02 and r["bausteine"][0][0] == "Zusatzarbeiten", r
d = f.pruefangebote_zeigen(zeigen=False)
assert d.tabelle.rowCount() == 2 and "Zusatzarbeiten" in d.tabelle.item(0, 7).text()
assert [db.angebot(i) for i in ids] == [dict(x, zusatz=db.angebot(x["id"])["zusatz"], geaendert=db.angebot(x["id"])["geaendert"]) for x in vorher]
ok("Abweichung ab 2 % gemeldet, größte Änderung Zusatzarbeiten, Angebot unverändert")

assert pa.neue_referenz(db, [ids[0]], VERSION) == 1
liste = {r["id"]: r for r in pa.pruefen(db)}
assert liste[ids[0]]["abweichung"] == 0 and liste[ids[1]]["prozent"] > 0.02
f.angebote.pruefangebot_umschalten([ids[1]], False)
assert pa.ids(db) == [ids[0]]
ok("Neue Referenz übernehmen; Prüfangebot aufheben")
print("test_pruefangebote OK")
