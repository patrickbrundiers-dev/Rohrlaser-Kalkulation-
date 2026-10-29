"""Prüft Reklamationen je Auftrag und Position (Plan 29.10.2026 Schritt 2c):

- R1 erfassen, ändern, erledigen, löschen; nur beauftragte Angebote; Position muss zum Angebot gehören; Menge Pflicht
- R2 Nachkalkulation: Kostenart „Reklamationen“ (Soll 0) mit der Summe der Kosten, senkt den Deckungsbeitrag; ohne
  Reklamation keine Zeile (alte Nachkalkulationen unverändert); gespeichert für die Auswertung
- R3 Auswertung: Quote je Fehlerart, Kunde, Werkstoff (reklamierte ÷ gelieferte Stück)
- R4 Oberfläche: Ausgaben-Menü im Angebot, Dialog erfassen, Datei → Reklamationen (Liste offen/alle, Auswertung)
- R5 Löschen des Angebots löscht seine Reklamationen; Einstellung Fehlerarten

Aufruf: python tests/test_reklamation.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import reklamation as rk  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)

a = db.angebot_neu(dict(kunde="Gestellbau Weber KG", skonto=0, stange=6000))
db.position_neu(a, dict(pos=10, artikel="GR-100", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                        stueck=100, schneidweg=300, einstiche=2))
db.position_neu(a, dict(pos=20, artikel="ES-1", profil_id="RR 42,4x2,0", werkstoff_id="1.4301", laenge=500,
                        stueck=50, schneidweg=200, einstiche=1))
p10, p20 = (p["id"] for p in db.positionen(a))
b = db.angebot_neu(dict(kunde="Edelstahlbau Nord GmbH", skonto=0, stange=6000))
db.position_neu(b, dict(pos=10, artikel="X", profil_id="RR 42,4x2,0", werkstoff_id="1.4301", laenge=800, stueck=200))

# R1
try:
    rk.speichern(db, a, dict(position_id=p10, menge=2))
    raise AssertionError("nicht beauftragt")
except rk.ReklamationFehler as e:
    assert "beauftragt" in str(e)
db.vorgang_setzen(a, "Beauftragt")
db.vorgang_setzen(b, "Beauftragt")
for falsch in (dict(position_id=db.positionen(b)[0]["id"], menge=1), dict(position_id=p10, menge=0)):
    try:
        rk.speichern(db, a, falsch)
        raise AssertionError(falsch)
    except rk.ReklamationFehler:
        pass
r1 = rk.speichern(db, a, dict(position_id=p10, menge=5, fehlerart="Grat oder Schlacke", ursache="intern: Fertigung",
                              massnahme="Nacharbeit", kosten=48.5), wer="PB")
r2 = rk.speichern(db, a, dict(position_id=None, fehlerart="Transportschaden", massnahme="Gutschrift", kosten=120))
z = {x["id"]: x for x in rk.liste(db, a)}
assert z[r1]["pos"] == "10" and z[r1]["artikel"] == "GR-100" and z[r1]["status"] == rk.OFFEN and z[r1]["wer"] == "PB"
assert z[r2]["pos"] is None and z[r2]["datum"] == datetime.date.today().isoformat()
rk.speichern(db, a, dict(z[r1], kosten=60.0, status=rk.ERLEDIGT), r1)
z = {x["id"]: x for x in rk.liste(db, a)}
assert z[r1]["kosten"] == 60.0 and z[r1]["erledigt_am"] == datetime.date.today().isoformat()
assert [x["id"] for x in rk.liste(db, nur_offen=True)] == [r2]
rk.erledigen(db, r2)
assert rk.liste(db, nur_offen=True) == [] and rk.kosten(db, a) == 180.0 and rk.kosten(db, b) is None
r3 = rk.speichern(db, b, dict(position_id=db.positionen(b)[0]["id"], menge=10, fehlerart="Grat oder Schlacke"))
rk.loeschen(db, r3)
assert rk.kosten(db, b) is None
ok("R1 erfassen, ändern, erledigen, löschen; Prüfungen")

# R2 Nachkalkulation
s = f.angebot_oeffnen(a)
s.optimieren()
s.neu_laden()
nk = s._nachkalk
nk.neu_laden()
v = nk._rechnen()
zeile = next(x for x in v["zeilen"] if x.get("feld") == "reklamation")
assert zeile["soll"] == 0 and zeile["ist"] == 180.0 and zeile["erfasst"] == "ja"
db_ohne = v["db"]["soll"]
assert abs(v["db"]["ist"] - (db_ohne - 180.0)) < 0.01, v["db"]
nk.setzen(werte={"laser_h": 0.5})
gespeichert = db.angebot(a)["nachkalkulation"]
assert gespeichert["reklamation"] == 180.0
assert any(x[1] == "reklamation" and x[6] == 180.0 for x in gespeichert["soll"]["zeilen"])
s2 = f.angebot_oeffnen(b)
s2._nachkalk.neu_laden()
assert not any(x.get("feld") == "reklamation" for x in s2._nachkalk._rechnen()["zeilen"])
ok("R2 Nachkalkulation mit Kostenart Reklamationen, gespeichert; ohne Reklamation keine Zeile")

# R3 Auswertung
rk.speichern(db, b, dict(position_id=db.positionen(b)[0]["id"], menge=4, fehlerart="Maß außerhalb der Toleranz",
                         kosten=30))
aw = rk.auswertung(db)
g = aw["gesamt"]
assert g["anzahl"] == 3 and g["menge"] == 9 and g["geliefert"] == 350 and abs(g["quote"] - 9 / 350) < 1e-9, g
k = {x["name"]: x for x in aw["kunde"]}
assert abs(k["Edelstahlbau Nord GmbH"]["quote"] - 4 / 200) < 1e-9 and k["Gestellbau Weber KG"]["kosten"] == 180
w = {x["name"]: x for x in aw["werkstoff"]}
assert w["S235-10219"]["menge"] == 5 and abs(w["S235-10219"]["quote"] - 5 / 100) < 1e-9 and "ganzer Auftrag" in w
assert aw["fehlerart"][0]["name"] == "Transportschaden", aw["fehlerart"]
ok("R3 Quote je Fehlerart, Kunde, Werkstoff")

# R4 Oberfläche
texte = [x.text() for x in s.weitere.menu().actions()]
assert "Reklamation erfassen …" in texte, texte
from rohrlaser.reklamation_dialog import ReklamationDialog, ReklamationenDialog  # noqa: E402
d = ReklamationDialog(s, db, a)
assert d.position.count() == 3 and d.position.currentData() == p10
d.position.setCurrentIndex(2)
d.menge.setValue(3)
d.fehlerart.setCurrentText("Kontur fehlt oder falsch")
d.kosten.setValue(25)
d._ok()
i = s.reklamation_erfassen(dialog=d)
assert i is not None and rk.kosten(db, a) == 205.0
assert db.angebot(a)["nachkalkulation"]["reklamation"] == 205.0, "gespeicherte Nachkalkulation aktualisiert"
d2 = ReklamationDialog(s, db, a)
d2._ok()                                                   # Menge 0 -> Fehler, nichts gespeichert
assert d2.werte is None and rk.kosten(db, a) == 205.0
rd = f.reklamationen()
assert isinstance(rd, ReklamationenDialog) and rd.tabelle.rowCount() == 2, rd.tabelle.rowCount()   # offene
rd.filter.setCurrentIndex(1)
assert rd.tabelle.rowCount() == 4 and "Quote" in rd.kopf.text()
assert rd.auswertungen["fehlerart"].rowCount() == 4
rd.tabelle.selectRow(0)
alt = rd.markiert()
d3 = ReklamationDialog(rd, db, alt["angebot_id"], alt)
assert d3.menge.value() == (alt["menge"] or 0)
d3.status.setCurrentText(rk.ERLEDIGT)
d3._ok()
rd.bearbeiten(dialog=d3)
assert next(x for x in rk.liste(db) if x["id"] == alt["id"])["status"] == rk.ERLEDIGT
assert "Reklamationen …" in f.datei_aktionen
ok("R4 Menü, Dialog erfassen/bearbeiten, Datei → Reklamationen mit Liste und Auswertung")

# R5
f.angebot_schliessen(b)
db.angebot_loeschen(b)
assert all(x["angebot_id"] != b for x in rk.liste(db))
db.einstellung_setzen("reklamation_fehlerarten", "Grat\n\nGrat\nMaß")
assert rk.fehlerarten(db) == ["Grat", "Maß"]
ok("R5 Löschen mit dem Angebot, Fehlerarten aus der Einstellung")
print("Alle Reklamations-Tests bestanden.")
