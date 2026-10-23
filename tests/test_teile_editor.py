"""Teile-Editor für Rohr und Blech (Plan S6, Abschnitt 6):
- T1 Merkmale und Herkunft (STEP / manuell / Vorgabe) aus den Eingaben, ohne Oberfläche; Befunde nennen die
  Konturzeilen (auch mit Gravurzeilen davor).
- T2 Rohr: Rahmen um den Schneidweg-Rechner (Baum, Prüfmeldungen, Knöpfe); STEP-Kontur geändert -> „manuell (STEP
  geändert)“, auf STEP-Wert zurücksetzen; Rückgängig/Wiederholen samt STEP-Merkern; Ende zurücksetzen.
- T3 Prüfmeldung anklicken: Merkmal im Baum, beide Konturen eines Stegs markiert, Skizze und 3D-Bereich.
- T4 3D: Klick auf eine Kontur wählt die Zeile (Rohr längs der Achse, Blech über die Kennung der Linie); Messen
  Punkt–Punkt.
- T5 Blech: Herkunft aus dem STEP-Import (bleibt beim Speichern), zurücksetzen, Rückgängig, Skizze markiert.
- T6 Gleiche Rechnung: Ergebnis des Editors = schneidweg.rechnen bzw. blech.rechnen für dieselben Eingaben.

Aufruf: python tests/test_teile_editor.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import blech, dfm, schneidweg as sw, teile_editor as te  # noqa: E402


def ok(t):
    print("OK    ", t)


QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")

# ------------------------------------------------------------------ T1 Merkmale ohne Oberfläche
e = dict(a=dict(winkel=45, achse="über Höhe"), b=dict(winkel=0),
         konturen=[dict(art=sw.BOHRUNG, anzahl=2, d=8, x=100), dict(art=sw.GRAVUR, laenge=30)], gravur=12)
m = te.merkmale_rohr(e, 500, step_enden={"a": True}, step_zeilen={0: False}, naht_text=("keine Vorgabe", te.VORGABE))
nach = {x.id: x for x in m}
assert nach["ende:a"].herkunft == te.STEP and nach["ende:a"].text == "Ende A: Gehrung 45° über Höhe"
assert nach["ende:b"].herkunft == te.VORGABE and nach["ende:b"].text == "Ende B: gerade"
assert nach["kontur:0"].herkunft == te.GEAENDERT and nach["kontur:0"].text == "1. Bohrung Ø d 8 × 2 bei x = 100"
assert nach["kontur:1"].gruppe == "Gravur" and nach["gravur"].text == "weitere Gravur 12 mm je Teil"
assert nach["teil"].text == "Länge 500 mm" and nach["naht"].herkunft == te.VORGABE
kant = dict(art=blech.KANTTEIL, form=blech.RECHTECK, dicke=2, kantlaenge=300, werkstoff="S235JR",
            schenkel=[dict(laenge=50, winkel=90, radius=None), dict(laenge=50, winkel=0, radius=None)],
            konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=20, y=20)])
mb = {x.id: x for x in te.merkmale_blech(kant, step=json.loads(json.dumps(kant)))}
assert [mb[i].herkunft for i in ("teil", "biegung:0", "kontur:0")] == [te.STEP] * 3
assert mb["biegung:0"].text == "B1: 90° nach Schenkel 50 mm" and "biegung:1" not in mb
geaendert = dict(kant, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=12, x=20, y=20)])
assert te.merkmale_blech(geaendert, step=kant)[-1].herkunft == te.GEAENDERT
assert te.merkmale_blech(kant, start=kant)[0].herkunft == te.VORGABE
assert te.merkmale_blech(geaendert, start=kant)[-1].herkunft == te.MANUELL
# Befunde mit Zeilen: Gravur vor den Konturen verschiebt die Zählung nicht
steg = [dict(art=sw.GRAVUR, laenge=20), dict(art=sw.BOHRUNG, anzahl=1, d=10, x=200, seite="oben"),
        dict(art=sw.BOHRUNG, anzahl=1, d=10, x=211, seite="oben")]
p_steg = dict(laenge=500, technik=json.dumps(dict(quelle=sw.QUELLE, konturen=steg)))
(b,) = [x for x in dfm.rohr(p_steg, QR) if x.regel == dfm.STEG]
assert b.zeilen == (1, 2) and "zwischen Kontur 2 und 3" in b.text and te.ziele(b) == ["kontur:1", "kontur:2"], b
klein = dfm.blech(dict(kant, art=blech.ZUSCHNITT, laenge=200, breite=100, dicke=3,
                       konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=20, x=50, y=50),
                                 dict(art=sw.BOHRUNG, anzahl=1, d=2, x=150, y=50)]),
                  blech.zuschnitt(dict(art=blech.ZUSCHNITT, laenge=200, breite=100, dicke=3)), kantbarkeit=False)
assert [(x.regel, x.zeilen) for x in klein] == [(dfm.BOHRUNG_KLEIN, (1,))], klein
ok("T1 Merkmale mit Herkunft STEP/manuell/Vorgabe; Befunde nennen ihre Konturzeilen (Gravur davor zählt richtig)")

# ------------------------------------------------------------------ T2 Rohr: Rahmen, Herkunft, Rückgängig
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
kopf = dict(maschine="T11", stange=6000)
technik = dict(quelle=sw.QUELLE, a=dict(winkel=30, achse="über Höhe", gemessen=70.5), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben", gemessen=31.4),
                         dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="oben")])
p = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, technik=json.dumps(technik))
d = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], kopf, k, db.tabellen(), db)
ed = d.editor
assert isinstance(ed, te.EditorRahmen) and ed.senkrecht.parent() is d
gruppen = [ed.baum.topLevelItem(i).text(0) for i in range(ed.baum.topLevelItemCount())]
assert gruppen == ["Teil", "Enden", "Innenkonturen", "Schweißnaht"], gruppen
her = {x.id: x.herkunft for x in ed.merkmale}
assert her["ende:a"] == te.STEP and her["ende:b"] == te.VORGABE and her["kontur:0"] == te.STEP
assert her["kontur:1"] == te.MANUELL
assert not ed.verlauf.canUndo()
# STEP-Bohrung von Hand größer: geändert, zurücksetzen
d.tabelle.item(0, 2).setText("12")
ed.aktualisieren()
assert {x.id: x.herkunft for x in ed.merkmale}["kontur:0"] == te.GEAENDERT
assert d.eingaben()["konturen"][0].get("gemessen") is None
ed.waehlen("kontur:0")
assert ed.zurueck_knopf.isEnabled() and d.tabelle.currentRow() == 0
assert ed.zuruecksetzen()
ed.aktualisieren()
assert {x.id: x.herkunft for x in ed.merkmale}["kontur:0"] == te.STEP
assert d.eingaben()["konturen"][0]["gemessen"] == 31.4 and d.eingaben()["konturen"][0]["d"] == 10
# Rückgängig: zurück zu Ø 12 (geändert), noch einmal: Ø 10 wie gemessen; Wiederholen
ed.verlauf.undo()
assert d.eingaben()["konturen"][0]["d"] == 12 and {x.id: x.herkunft for x in ed.merkmale}["kontur:0"] == te.GEAENDERT
ed.verlauf.undo()
assert d.eingaben()["konturen"][0] == dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, gemessen=31.4), \
    d.eingaben()["konturen"][0]
assert not ed.verlauf.canUndo()
ed.verlauf.redo()
assert d.eingaben()["konturen"][0]["d"] == 12
ed.verlauf.redo()
assert d.eingaben()["konturen"][0]["gemessen"] == 31.4
# Ende A geändert: Schnittlänge gerechnet statt gemessen, zurücksetzen holt die Messung
d.winkel["a"].setValue(40)
ed.aktualisieren()
assert {x.id: x.herkunft for x in ed.merkmale}["ende:a"] == te.GEAENDERT and "gemessen" not in d.eingaben()["a"]
assert ed.zuruecksetzen("ende:a")
assert d.eingaben()["a"]["gemessen"] == 70.5 and d.winkel["a"].value() == 30
n = ed.verlauf.count()
ed.aktualisieren()
assert ed.verlauf.count() == n + 1 and ed.verlauf.canUndo()
ok("T2 Rohr: Baum mit Herkunft, STEP-Werte geändert/zurückgesetzt, Rückgängig/Wiederholen mit gemessenen Werten")

# ------------------------------------------------------------------ T3 Prüfmeldung anklicken
d3 = SchneidwegDialog(None, dict(p, technik=json.dumps(dict(quelle=sw.QUELLE, konturen=steg))),
                      k.profile["QR 40x40x3"], kopf, k, db.tabellen(), db)
ed3 = d3.editor
texte = [ed3.meldungen.item(i).text() for i in range(ed3.meldungen.count())]
nr = next(i for i, t in enumerate(texte) if "Steg zu schmal" in t)
assert texte[nr].startswith("WARNUNG: Steg zu schmal"), texte
ed3.meldungen.setCurrentRow(nr)
assert ed3.gewaehlt == "kontur:1" and ed3.baum.currentItem().data(0, 0x0100) == "kontur:1"
assert sorted({i.row() for i in d3.tabelle.selectedIndexes()}) == [1, 2]
assert d3.skizze.markiert == 1 and d3.ansicht3d.ansicht.markiert_z is None     # ohne STEP-Netz kein 3D-Bereich
assert "Prüfmeldungen</b> (" in ed3.meldung_titel.text()
ok("T3 Prüfmeldung anklicken: Merkmal im Baum, beide Konturen des Stegs markiert")

# ------------------------------------------------------------------ T4 3D: Auswahl und Messen
# Rohr: einfaches Netz (Achse Z ab 0) mit zwei Konturlinien bei z = 100 und z = 300, Anfangsschnitt bei 0
L = 500.0
punkte = [20, 20, 0, -20, 20, 0, -20, 20, L, 20, 20, L]
netz = dict(p=punkte, t={"A": [0, 1, 2, 0, 2, 3]},
            l={"K": [[-5, 20, 100, 5, 20, 100], [-15, 20, 300, 15, 20, 300]], "EA": [[20, 20, 0, -20, 20, 0]]})
d.ansicht3d.setzen(netz, "Test")
a = d.ansicht3d.ansicht
a.resize(800, 400)
bild = a.bildpunkt()
x, y, _ = bild((0, 20, 300))
treffer = a.klicken(x, y)
assert treffer and abs(treffer["punkt"][2] - 300) < 1 and d.editor.gewaehlt == "kontur:1", (treffer, d.editor.gewaehlt)
assert a.markiert_z and a.markiert_z[0] < 300 < a.markiert_z[1] and a.markiert_z[1] - a.markiert_z[0] < 50
x, y, _ = bild((0, 20, 100))
a.klicken(x, y)
assert d.editor.gewaehlt == "kontur:0" and d.tabelle.currentRow() == 0
x, y, _ = bild((20, 20, 0))
a.klicken(x, y)
assert d.editor.gewaehlt == "ende:a", d.editor.gewaehlt
# Messen: Ecke zu Ecke
d.editor.messen_knopf.setChecked(True)
assert a.messen and d.bilder.currentWidget() is d.ansicht3d
a.resize(800, 400)
bild = a.bildpunkt()
for q in ((20, 20, 0), (20, 20, L)):
    x, y, _ = bild(q)
    a.klicken(x + 3, y - 2)
assert abs(a.abstand() - L) < 1e-6 and "Abstand 500" in d.editor.mass.text(), d.editor.mass.text()
d.editor.messen_knopf.setChecked(False)
assert not a.messen and a.abstand() is None
a.grab()                # zeichnet Markierung und Hinweis ohne Fehler
ok("T4 3D: Klick wählt Kontur bzw. Ende (Bereich längs der Achse hervorgehoben), Messen Punkt–Punkt 500 mm")

# ------------------------------------------------------------------ T5 Blech aus dem STEP-Import
werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
roh = dict(kant, werkstoff=werkstoff, step=True)
bd = BlechDialog(None, db, roh, neu=False)
be = bd.editor
assert isinstance(be, te.EditorRahmen) and bd.step_werte and "stueck" not in bd.step_werte
assert bd.eingaben()["step"] == bd.step_werte
assert {x.id: x.herkunft for x in be.merkmale} == {"teil": te.STEP, "biegung:0": te.STEP, "kontur:0": te.STEP}
bd.tabelle.item(0, 2).setText("14")
be.aktualisieren()
assert {x.id: x.herkunft for x in be.merkmale}["kontur:0"] == te.GEAENDERT
# gespeichert und wieder geöffnet: die Herkunft bleibt
bd2 = BlechDialog(None, db, json.loads(json.dumps(bd.eingaben())), neu=False)
assert {x.id: x.herkunft for x in bd2.editor.merkmale}["kontur:0"] == te.GEAENDERT
be.waehlen("kontur:0")
assert bd.skizze.markiert == "kontur:0" and bd.ansicht3d.ansicht.markiert == {"kontur:0"}
assert be.zurueck_knopf.isEnabled() and be.zuruecksetzen()
be.aktualisieren()
assert bd.eingaben()["konturen"][0]["d"] == 10 and {x.id: x.herkunft for x in be.merkmale}["kontur:0"] == te.STEP
be.verlauf.undo()
assert bd.eingaben()["konturen"][0]["d"] == 14
be.waehlen("biegung:0")
assert bd.schenkel.currentRow() == 0 and bd.skizze.markiert == "biegung:0"
# 3D: Klick auf eine Konturlinie des gefalteten Teils wählt die Zeile
a = bd.ansicht3d.ansicht
a.resize(700, 400)
nr = next(i for i, kn in enumerate(a.modell.linien_id) if kn == "kontur:0")
pa, pb = a.bildpunkt()(a.modell.linien[nr][0]), a.bildpunkt()(a.modell.linien[nr][1])
be.waehlen("teil")
a.klicken((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
assert be.gewaehlt == "kontur:0"
bd.skizze.grab()
# neues Blech: Grundwerte = Vorgabe, geändert = manuell
neu = BlechDialog(None, db)
assert neu.editor.merkmale[0].herkunft == te.VORGABE and not neu.editor.zurueck_knopf.isEnabled()
neu.laenge.setValue(250)
neu.editor.aktualisieren()
assert neu.editor.merkmale[0].herkunft == te.MANUELL and "step" not in neu.eingaben()
ok("T5 Blech: Herkunft aus dem STEP-Import bleibt gespeichert, zurücksetzen, Rückgängig, Skizze/3D markiert")

# ------------------------------------------------------------------ T6 gleiche Rechnung wie die Module
r = sw.rechnen(d.eingaben(), d.profil, d.grenzen, d.gewinde, d.maschine)
assert r["felder"] == d.ergebnis["felder"] and r["schritte"] == d.ergebnis["schritte"]
rb = blech.rechnen(bd.eingaben(), bd.werkstoffe, bd.laserdaten, bd.einst)
assert rb["richtpreis"] == bd.ergebnis["richtpreis"] and rb["kosten"] == bd.ergebnis["kosten"]
assert blech.rechnen({k_: v for k_, v in bd.eingaben().items() if k_ != "step"}, bd.werkstoffe, bd.laserdaten,
                     bd.einst)["richtpreis"] == rb["richtpreis"]
db.schliessen()
ok("T6 Editor rechnet wie schneidweg.rechnen bzw. blech.rechnen (keine zweite Rechnung)")
print("Alle Tests Teile-Editor bestanden.")
