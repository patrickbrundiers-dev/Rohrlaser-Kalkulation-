"""Zurücksetzen auf den Ursprung in den Editoren (Patrick 03.11.2026, Freigabe 1a 2a 3a 4a):
- U1 schneidweg.ursprung_merken: Importstand unter 'ursprung', ohne sich selbst und ohne Quelle; vorhandener bleibt
  (außer neu=True); Vorlagen und kopierte Konturen tragen ihn nicht weiter (ohne_messung).
- U2 Rohr-Editor: Konturzeile gelöscht, Bohrung und Ende geändert -> „Alles wie aus STEP/DXF importiert“ bringt alles
  zurück (auch die gelöschte Zeile, mit Messwerten), ein Schritt für Rückgängig; „Alles wie beim Öffnen“.
  Gespeichert und wieder geöffnet: der Importstand bleibt. STEP neu einlesen = neuer Ursprung.
- U3 Rohr ohne gemerkten Importstand (alte Position): alle geänderten Merkmale auf STEP-Wert.
- U4 Blech: STEP (step_werte) und DXF (ursprung) zurück, stueck bleibt, Rückgängig.
- U5 Menüband: Knopf „Zurücksetzen“ mit beiden Einträgen; Einträge nur aktiv, wenn es etwas zurückzusetzen gibt.

Aufruf: python tests/test_editor_ursprung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import blech, schneidweg as sw, teile_editor as te  # noqa: E402
from rohrlaser.schneidweg_dialog import ohne_messung  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ U1 ursprung_merken
t = dict(quelle=sw.QUELLE, a=dict(winkel=30, gemessen=70.5), konturen=[dict(art=sw.BOHRUNG, d=10, gemessen=31.4)])
m = json.loads(sw.ursprung_merken(json.dumps(t)))
assert m["ursprung"] == dict(a=t["a"], konturen=t["konturen"]), m
m2 = json.loads(sw.ursprung_merken(json.dumps(dict(m, konturen=[]))))
assert m2["ursprung"]["konturen"] == t["konturen"], "vorhandener Ursprung bleibt"
assert sw.ursprung_merken(dict(m, konturen=[]), neu=True)["ursprung"]["konturen"] == []
assert "ursprung" not in ohne_messung(m)
assert sw.ursprung_merken("kein json") == "kein json"
ok("U1 Importstand gemerkt, vorhandener bleibt, Vorlagen ohne Ursprung")

# ------------------------------------------------------------------ U2 Rohr-Editor
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
kopf = dict(maschine="T11", stange=6000)
QR = k.profile["QR 40x40x3"]
technik = dict(quelle=sw.QUELLE, a=dict(winkel=30, achse="über Höhe", gemessen=70.5), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben", gemessen=31.4),
                         dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="oben", gemessen=82.8)])
p = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10,
         technik=sw.ursprung_merken(json.dumps(technik)))


def oeffnen(pos):
    return SchneidwegDialog(None, pos, QR, kopf, k, db.tabellen(), db)


d = oeffnen(p)
ed = d.editor
start = d.eingaben()
assert start["ursprung"]["konturen"][1]["gemessen"] == 82.8
# Änderungen: Bohrung größer, Ende A anders, Langloch gelöscht
d.tabelle.item(0, 2).setText("12")
ed.aktualisieren()
d.winkel["a"].setValue(40)
ed.aktualisieren()
d.tabelle.selectRow(1)
d._entfernen()
ed.aktualisieren()
assert len(d.eingaben()["konturen"]) == 1 and d.eingaben()["a"]["winkel"] == 40
ed._ursprung_pruefen()
assert all(a.isEnabled() for a in ed.ursprung_aktionen.values())
n = ed.verlauf.count()
assert ed.ursprung(te.IMPORT, fragen=False)
e = d.eingaben()
assert [(z["art"], z.get("d"), z.get("gemessen")) for z in e["konturen"]] == \
    [(sw.BOHRUNG, 10, 31.4), (sw.LANGLOCH, None, 82.8)], e["konturen"]
assert e["a"]["winkel"] == 30 and e["a"]["gemessen"] == 70.5
assert {x.id: x.herkunft for x in ed.merkmale}["kontur:1"] == te.STEP
assert ed.verlauf.count() == n + 1, "ein Schritt für Rückgängig"
ed.verlauf.undo()
assert len(d.eingaben()["konturen"]) == 1 and d.eingaben()["a"]["winkel"] == 40
ed.verlauf.redo()
assert len(d.eingaben()["konturen"]) == 2
# wie beim Öffnen: andere Änderung verwerfen
d.tabelle.item(0, 1).setText("3")
ed.aktualisieren()
assert ed.ursprung(te.OEFFNEN, fragen=False)
assert d.eingaben()["konturen"] == start["konturen"] and d.eingaben()["a"] == start["a"]
assert not ed.ursprung(te.OEFFNEN, fragen=False), "nichts geändert: nichts zu tun"
# gespeichert (ohne Langloch) und wieder geöffnet: Importstand bleibt
d.tabelle.selectRow(1)
d._entfernen()
gespeichert = dict(p, technik=sw.speichern(d.eingaben()))
d2 = oeffnen(gespeichert)
assert len(d2.eingaben()["konturen"]) == 1
assert d2.editor.ursprung(te.IMPORT, fragen=False) and len(d2.eingaben()["konturen"]) == 2
# STEP neu einlesen: neuer Ursprung
d2.eingaben_setzen(dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=6, x=50, gemessen=18.8)]),
                   mit_messung=True)
d2._ursprung_neu()
assert d2.eingaben()["ursprung"]["konturen"][0]["d"] == 6
ok("U2 Rohr: gelöschte Kontur, Bohrung, Ende wie aus STEP zurück (ein Rückgängig-Schritt), wie beim Öffnen, "
   "bleibt gespeichert, STEP neu einlesen = neuer Ursprung")

# ------------------------------------------------------------------ U3 alte Position ohne Importstand
d3 = oeffnen(dict(p, technik=json.dumps(technik)))
e3 = d3.editor
e3._ursprung_pruefen()
assert not e3.ursprung_aktionen[te.IMPORT].isEnabled() and not e3.ursprung_aktionen[te.OEFFNEN].isEnabled()
d3.tabelle.item(0, 2).setText("12")
d3.winkel["a"].setValue(45)
e3.aktualisieren()
e3._ursprung_pruefen()
assert e3.ursprung_aktionen[te.IMPORT].isEnabled() and "STEP-Wert" in e3.ursprung_aktionen[te.IMPORT].text()
assert e3.ursprung(te.IMPORT, fragen=False)
assert d3.eingaben()["konturen"][0]["d"] == 10 and d3.eingaben()["a"]["gemessen"] == 70.5
ok("U3 alte Position: geänderte Merkmale auf STEP-Wert")

# ------------------------------------------------------------------ U4 Blech
werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
kant = dict(art=blech.KANTTEIL, form=blech.RECHTECK, dicke=2, kantlaenge=300, werkstoff=werkstoff, stueck=5,
            schenkel=[dict(laenge=50, winkel=90, radius=None), dict(laenge=50, winkel=0, radius=None)],
            konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=20, y=20)], step=True)
bd = BlechDialog(None, db, kant, neu=False)
be = bd.editor
bd.tabelle.item(0, 2).setText("14")
bd.schenkel.item(0, 1).setText("80")
bd.stueck.setValue(7)
be.aktualisieren()
assert be.ursprung(te.IMPORT, fragen=False)
e = bd.eingaben()
assert e["konturen"][0]["d"] == 10 and e["schenkel"][0]["winkel"] == 90 and e["stueck"] == 7
assert {x.herkunft for x in be.merkmale} == {te.STEP}
be.verlauf.undo()
assert bd.eingaben()["konturen"][0]["d"] == 14
# DXF-Blech (ohne STEP): Ursprung aus der Position
dxf = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100, werkstoff=werkstoff,
           konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=8, x=50, y=50)])
bx = BlechDialog(None, db, dict(dxf, stueck=2, ursprung=dict(dxf)), neu=False)
bx.laenge.setValue(260)
bx.tabelle.setRowCount(0)
bx.rechnen()
bx.editor.aktualisieren()
assert bx.editor.ursprung(te.IMPORT, fragen=False)
assert bx.eingaben()["laenge"] == 200 and len(bx.eingaben()["konturen"]) == 1 and bx.eingaben()["ursprung"]
neu = BlechDialog(None, db)
neu.editor._ursprung_pruefen()
assert not neu.editor.ursprung_aktionen[te.IMPORT].isEnabled() and not neu.editor.ursprung(te.IMPORT, fragen=False)
ok("U4 Blech: wie aus STEP bzw. DXF zurück, Stückzahl bleibt, Rückgängig; neues Blech ohne Ursprung")

# ------------------------------------------------------------------ U5 Menüband
for rahmen in (ed, be):
    kn = rahmen.band.knopf("Zurücksetzen")
    assert kn is rahmen.ursprung_knopf and kn.menu() is not None
    assert [a.text() for a in kn.menu().actions()][0] == "Alles wie beim Öffnen"
ok("U5 Menüband: Knopf Zurücksetzen mit Menü in Rohr- und Blech-Editor")
print("Alle Prüfungen bestanden.")
