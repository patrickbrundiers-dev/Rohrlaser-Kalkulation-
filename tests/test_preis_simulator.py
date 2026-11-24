"""Prüft den Preis-Simulator (Plan 29.10.2026, neue Idee 3):

- P1 leeres Szenario: vorher = nachher, Verkaufspreis wie im Angebotsfenster
- P2 Material +10 % für Edelstahl: nur Edelstahl-Angebote werden teurer, Materialkosten genau +10 %; Stahl bleibt
- P3 Maschinenstundensatz +20 €/h: Laserkosten steigen im Verhältnis des Stundensatzes
- P4 Marge bei gleichem Preis sinkt, Summen stimmen mit den Zeilen überein
- P5 Auswahl: nur Entwurf/Verschickt (Beauftragt nur auf Wunsch), nicht optimierte Angebote mit Grund
- P6 nichts wird gespeichert; festgeschriebene Preise (preisbasis) bleiben Grundlage
- P7 Dialog: Szenario eingeben, rechnen, Tabelle und Summenzeile; Margen nur mit Admin-Rechten

Aufruf: python tests/test_preis_simulator.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import preis_simulator as ps  # noqa: E402
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


def nah(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)


def angebot_mit(werkstoff, kunde, optimieren=True):
    a = db.angebot_neu(dict(kunde=kunde, skonto=0, stange=6000))
    db.position_neu(a, dict(pos=10, artikel="Teil", profil_id="RR 42,4x2,0", werkstoff_id=werkstoff, laenge=1000,
                            stueck=10, schneidweg=300, einstiche=2))
    if optimieren:
        s = f.angebot_oeffnen(a)
        s.optimieren()
        s.neu_laden()
        vk = s._rechnung()[1]["verkauf"]
        f.angebot_schliessen(a)
        return a, vk
    return a, None


a_es, vk_es = angebot_mit("1.4301", "Edel GmbH")
a_st, vk_st = angebot_mit("S235-10219", "Stahl KG")
a_leer, _ = angebot_mit("S235-10219", "Ohne Plan", optimieren=False)
a_auftrag, _ = angebot_mit("1.4301", "Auftrag AG")
db.vorgang_setzen(a_auftrag, "Beauftragt")

# P1 leeres Szenario
assert ps.leer({}) and ps.leer({"material": {"Edelstahl": 0}}) and not ps.leer({"maschine": 5})
r = ps.angebot(db, a_es, {})
assert nah(r["vorher"]["verkauf"], vk_es, 0.005), (r, vk_es)
assert r["vorher"] == r["nachher"]
ok("P1 leeres Szenario = unverändert, Verkaufspreis wie im Angebotsfenster")

# P2 Material Edelstahl +10 %
sz = {"material": {"Edelstahl": 10}}
r_es, r_st = ps.angebot(db, a_es, sz), ps.angebot(db, a_st, sz)
assert nah(r_es["nachher"]["material"], r_es["vorher"]["material"] * 1.10, 1e-6), r_es
assert r_es["nachher"]["verkauf"] > r_es["vorher"]["verkauf"]
assert r_st["vorher"] == r_st["nachher"], "Stahl bleibt"
ok("P2 Material Edelstahl +10 %, Stahl unverändert")

# P3 Maschinenstundensatz +20 €/h
k = db.kontext()
m = db.angebot(a_es)["maschine"]
satz = rechnen.zeitbasis(db.angebot(a_es), k, db.tabellen())["maschine"]["stundensatz"]
r3 = ps.angebot(db, a_es, {"maschine": 20})
assert nah(r3["nachher"]["laser"], r3["vorher"]["laser"] * (satz + 20) / satz, 1e-6), (r3, satz)
assert r3["nachher"]["material"] == r3["vorher"]["material"]
ok(f"P3 Maschine {m} {satz} → {satz + 20} €/h: Laserkosten im Verhältnis")

# P4 Margen und Summen
zeilen, summen = ps.simulieren(db, {"material": {"Edelstahl": 10}, "maschine": 20})
gerechnet = [z for z in zeilen if "vorher" in z]
z_es = next(z for z in zeilen if z["id"] == a_es)
assert z_es["marge_gleich"] < z_es["marge_vorher"], z_es
assert nah(summen["verkauf_vorher"], sum(z["vorher"]["verkauf"] for z in gerechnet))
assert nah(summen["diff"], sum(z["diff"] for z in gerechnet))
assert summen["angebote"] == 2 and summen["ohne"] == 1, summen
ok("P4 Marge bei gleichem Preis sinkt, Summen = Zeilen")

# P5 Auswahl
ids = {z["id"] for z in zeilen}
assert ids == {a_es, a_st, a_leer}, ids
assert next(z for z in zeilen if z["id"] == a_leer)["fehlt"] == "nicht optimiert"
z2, _ = ps.simulieren(db, {}, ps.MIT_BEAUFTRAGT)
assert a_auftrag in {z["id"] for z in z2}
assert ps.szenario_text({"material": {"Edelstahl": 8}, "maschine": 10}) == "Edelstahl +8 %, Maschine +10 €/h"
assert ps.szenario_text({}) == "keine Änderung"
ok("P5 offene Angebote, Beauftragte auf Wunsch, ohne Schnittplan mit Grund")

# P6 nichts gespeichert, Preisbasis gilt
vor = (db.angebot(a_es), db.positionen(a_es), db.tabellen()["preise"])
z6, _ = ps.simulieren(db, {"material": {"Edelstahl": 50}, "maschine": 50, "saetze": 20, "zukauf": 10})
assert not any(str(z.get("fehlt", "")).startswith("Fehler") for z in z6), z6
assert (db.angebot(a_es), db.positionen(a_es), db.tabellen()["preise"]) == vor
a_fest = db.angebot(a_es)
pb = rechnen.preisbasis_aus(a_fest, db.positionen(a_es), db.kontext(), db.tabellen())
pb["preise"] = [dict(z, preis=z["preis"] * 2) if z.get("basis") else z for z in pb["preise"]]
with db.con:
    db.con.execute("UPDATE angebote SET preisbasis=? WHERE id=?", (json.dumps(pb), a_es))
r6 = ps.angebot(db, a_es, {})
assert r6["vorher"]["material"] > r["vorher"]["material"] * 1.5, "festgeschriebene (doppelte) Preise gelten"
with db.con:
    db.con.execute("UPDATE angebote SET preisbasis=NULL WHERE id=?", (a_es,))
ok("P6 nichts gespeichert, festgeschriebene Preise gelten")

# P7 Dialog
from rohrlaser.preis_simulator_dialog import PreisSimulatorDialog  # noqa: E402
d = PreisSimulatorDialog(f, admin=False)
d.material["Edelstahl"].setValue(10)
d.maschine.setValue(20)
d.rechnen()
assert d.tabelle.rowCount() == 4, d.tabelle.rowCount()          # 3 Angebote + Summe
kopf = [d.tabelle.horizontalHeaderItem(c).text() for c in range(d.tabelle.columnCount())]
assert not any("Marge" in t for t in kopf), kopf
assert "Edelstahl +10 %" in d.ergebnis_text.text() and "Maschine +20 €/h" in d.ergebnis_text.text()
summe = d.tabelle.item(3, 0).text()
assert summe.startswith("Summe"), summe
d2 = PreisSimulatorDialog(f, admin=True)
d2.material["Edelstahl"].setValue(10)
d2.beauftragt.setChecked(True)
d2.rechnen()
kopf2 = [d2.tabelle.horizontalHeaderItem(c).text() for c in range(d2.tabelle.columnCount())]
assert any("Marge" in t for t in kopf2) and d2.tabelle.rowCount() == 5, (kopf2, d2.tabelle.rowCount())
assert "Preis-Simulator …" in f.datei_aktionen
ok("P7 Dialog mit Summenzeile, Margen nur mit Admin-Rechten, Menü Datei")
# P8 Zukaufteile: Staffelpreise im Preisstand × Faktor, Bezugskosten bleiben
e = dict(artikel_id=1, menge=2, stand=dict(bezug=dict(preise=[dict(ab=1, preis=10.0), dict(ab=100, preis=8.0)],
                                                     versand=5.0)))
e2 = ps._zukauf_teurer(e, 1.1)
assert [x["preis"] for x in e2["stand"]["bezug"]["preise"]] == [11.0, 8.8] and e2["stand"]["bezug"]["versand"] == 5.0
assert e["stand"]["bezug"]["preise"][0]["preis"] == 10.0 and ps._zukauf_teurer(dict(menge=1), 1.1) == dict(menge=1)
ok("P8 Zukauf-Staffelpreise × Faktor, Original unverändert")
print("Alle Preis-Simulator-Tests bestanden.")
