"""3D-Viewer als Arbeitswerkzeug, Teil 3 (Plan Patrick 18.11.2026, Paket V4 Bearbeiten).

- R1 Rückgängig/Wiederholen in „Satz in 3D“: Alle Stöße stecken, Steckverbindung entfernen, Längsnaht per Klick –
  jeder Schritt einzeln zurück und wieder vor, Tabellen und 3D folgen; Strg+Z/Strg+Y.
- R2 Schweißbaugruppe: Unterbaugruppe, Stecken und Zurücksetzen je ein Schritt (gleicher Stand wie Zurücksetzen).
- E1 Eckpunkte prüfen: zu wenige, doppelte, ohne Fläche, sich schneidende Kanten; Bögen bleiben.
- E2 Polygon am Rohr: Punkt ziehen (Lage wird nachgeführt, unveränderte Punkte bleiben am Rohr), einfügen, löschen,
  Schnittlänge aus der Rechnung neu; Rückgängig im Editor.
- E3 Sonderkontur aus STEP: Umriss geändert -> Schnittlänge = Umfang, Merkmal „von Hand geändert“.

Aufruf: python tests/test_3d_viewer_bearbeiten.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402
import step_messen  # noqa: E402
from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser import teile_editor as te  # noqa: E402
from rohrlaser.satz3d import saetze  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


datei = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
tmp = Path(tempfile.mkdtemp())
step_messen.main(["--ausgabe", str(tmp / "m.txt"), "--json", str(tmp / "m.json"), "--netze", str(tmp / "netze"),
                  str(datei)])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(tmp / "m.txt"), tmp / "netze"), tmp / "m.json")
for x in mw:
    x.update(_saetze=1, _stueck=1, _uebernehmen=True)
db = Datenbank(tmp / "satz.db")
k = db.kontext()
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True, zukauf_liste=[])
satz = step.satzname(datei)
db.profile_anlegen(erg["profile"])
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db.position_neu(a, q)
    if netz:
        db.netz_speichern(pid, netz)
db.satz_daten_speichern(a, satz, erg["satz_daten"][satz])
f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(a)
assert saetze(seite.positionen) == [satz]
gesehen = {}


def bedienen(d):
    v = d.verlauf
    gesehen["start"] = (v.count(), d.zurueck_knopf.isEnabled(), d.vor_knopf.isEnabled())
    n0 = len(d.bg["steckverbindungen"])
    d.steck_alle(melden=False)
    n1 = len(d.bg["steckverbindungen"])
    gesehen["gesteckt"] = (n0, n1, v.count(), d.zurueck_knopf.isEnabled())
    d.steck_tab.clearSelection()
    d.steck_tab.selectRow(0)
    d.steck_entfernen()
    n2 = len(d.bg["steckverbindungen"])
    gesehen["entfernt"] = (n2, v.count())
    v.undo()
    gesehen["undo1"] = (len(d.bg["steckverbindungen"]), d.steck_tab.rowCount(), v.count())
    v.undo()
    gesehen["undo2"] = (len(d.bg["steckverbindungen"]), d.steck_tab.rowCount(), d.vor_knopf.isEnabled())
    v.redo()
    gesehen["redo"] = (len(d.bg["steckverbindungen"]), d.steck_tab.rowCount())
    # Strg+Z im Fenster
    d.show()
    d.activateWindow()
    d.ansicht3d.ansicht.setFocus()
    app.processEvents()
    gesehen["band"] = d.zurueck_knopf.parentWidget() is not None and "Bearbeiten" in d.rahmen.gruppen and \
        d.zurueck_knopf.isVisibleTo(d)
    QTest.keyClick(d.ansicht3d.ansicht, Qt.Key_Z, Qt.ControlModifier)
    gesehen["strg_z"] = len(d.bg["steckverbindungen"])
    QTest.keyClick(d.ansicht3d.ansicht, Qt.Key_Y, Qt.ControlModifier)
    gesehen["strg_y"] = len(d.bg["steckverbindungen"])
    # neuer Schritt nach Rückgängig verwirft das Wiederholen
    v.undo()
    d.steck_alle(melden=False)
    gesehen["neu_nach_undo"] = (v.canRedo(), len(d.bg["steckverbindungen"]))
    # Längsnaht per Klick als eigener Schritt
    d.__dict__.setdefault("laengsnaehte", {})[d.teile[0]["_id"]] = 90.0
    d.aktualisieren()
    gesehen["naht"] = (dict(d.laengsnaehte), v.undoText())
    v.undo()
    gesehen["naht_undo"] = dict(d.__dict__.get("laengsnaehte") or {})
    d.reject()
    return False


i = next(r for r, p in enumerate(seite.positionen) if p.get("satz") == satz)
seite.satz_3d(i, dialog=bedienen)
assert gesehen["start"] == (0, False, False), gesehen["start"]
n0, n1, cnt, an = gesehen["gesteckt"]
assert n0 == 0 and n1 >= 2 and cnt == 1 and an, gesehen["gesteckt"]
assert gesehen["entfernt"] == (n1 - 1, 2), gesehen["entfernt"]
assert gesehen["undo1"] == (n1, n1, 2), gesehen["undo1"]
assert gesehen["undo2"] == (0, 0, True), gesehen["undo2"]
assert gesehen["redo"] == (n1, n1), gesehen["redo"]
assert gesehen["band"], gesehen
assert gesehen["strg_z"] == 0 and gesehen["strg_y"] == n1, gesehen
assert gesehen["neu_nach_undo"] == (False, n1), gesehen["neu_nach_undo"]
assert gesehen["naht"][0] and gesehen["naht"][1] == "Längsnaht", gesehen["naht"]
assert gesehen["naht_undo"] == {}, gesehen["naht_undo"]
ok(f"R1 Satz in 3D: Stecken ({n1}), Entfernen, Längsnaht je ein Schritt zurück und vor, Strg+Z/Strg+Y, Tabellen folgen")

# ------------------------------------------------------------------ R2 Schweißbaugruppe
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402

t2 = tmp / "bg"
t2.mkdir()
step_messen.main(["--ausgabe", str(t2 / "m.txt"), "--json", str(t2 / "m.json"), "--netze", str(t2 / "netze"),
                  str(datei)])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(t2 / "m.txt"), t2 / "netze"), t2 / "m.json")
for x in mw:
    x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True)
db2 = Datenbank(t2 / "b.db")
erg = step.uebernehmen(mw, [], db2.kontext(), db2.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                       zukauf_liste=[])
db2.profile_anlegen(erg["profile"])
a2 = db2.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db2.position_neu(a2, q)
    if netz:
        db2.netz_speichern(pid, netz)
positionen = db2.positionen(a2)
bgp = next(q for q in positionen if q.get("art") == BAUGRUPPE)
d = BaugruppeDialog(None, bgp, positionen, db2.tabellen(), {"Schweißen": 75.0}, db=db2, netze=db2.netze(a2),
                    profile=db2.kontext().profile)
assert d.verlauf.count() == 0 and "Bearbeiten" in d.rahmen.gruppen
knoten0 = len(d.bg["knoten"])
d.knoten_neu("Hand")
assert len(d.bg["knoten"]) == knoten0 + 1 and d.verlauf.count() == 1, (d.verlauf.count(), d.verlauf.undoText())
neu, _ = d.steck_alle(melden=False)
assert neu >= 1 and d.verlauf.count() == 2 and d.verlauf.undoText() in ("Steckverbindungen", "Teilen")
d.verlauf.undo()
assert not d.bg["steckverbindungen"] and len(d.bg["knoten"]) == knoten0 + 1
d.verlauf.undo()
assert len(d.bg["knoten"]) == knoten0 and d.steck_tab.rowCount() == 0
d.verlauf.redo()
d.verlauf.redo()
assert len(d.bg["steckverbindungen"]) == neu and len(d.bg["knoten"]) == knoten0 + 1
# Zurücksetzen ist auch ein Schritt: Strg+Z (verlauf_zurueck) holt den Stand davor
d.ursprung("oeffnen")
assert not d.bg["steckverbindungen"] and len(d.bg["knoten"]) == knoten0
assert d.verlauf_zurueck() and len(d.bg["steckverbindungen"]) == neu
werte = d.werte()                     # OK-Ergebnis wie bisher lesbar
assert werte["stecken"]["dazu"], werte["stecken"]
d.reject()
ok(f"R2 Schweißbaugruppe: Unterbaugruppe, Stecken ({neu}) und Zurücksetzen je ein Schritt, zurück und vor")

# ------------------------------------------------------------------ E1 Eckpunkte prüfen
import json  # noqa: E402
import math  # noqa: E402

from rohrlaser import eckpunkte_dialog as ed, schneidweg as sw  # noqa: E402

Q = [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0), (40.0, 20.0, 0.0), (0.0, 20.0, 0.0)]
assert ed.pruefen(Q) == ""
assert "Mindestens 3" in ed.pruefen(Q[:2])
assert "aufeinander" in ed.pruefen(Q[:2] + [(40.0, 0.004, 0.0)] + Q[2:])
assert "keine Fläche" in ed.pruefen([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 0.0, 0.0)])
assert "schneiden sich" in ed.pruefen([Q[0], Q[2], Q[1], (0.0, 30.0, 0.0)])         # Schleife (Achter)
assert ed.pruefen([Q[0], Q[1], (40.0, 20.0, 0.4142), Q[3]]) == ""
assert ed.text([(0.0, 0.0, 0.0), (40.5, 0.0, 0.4142)]) == "0,0; 40.5,0,0.4142"
assert sw.punkte_roh(ed.text(Q)) == Q
ok("E1 Eckpunkte geprüft: zu wenige, doppelt, ohne Fläche, Kanten schneiden sich; Bögen bleiben im Text")

# ------------------------------------------------------------------ E2 Polygon am Rohr
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

db3 = Datenbank(tmp / "e.db")
k3 = db3.kontext()
qr = k3.profile["QR 40x40x3"]
poly = dict(art=sw.POLYGON, anzahl=1, punkte="0,0; 20,0; 20,10; 0,10", x=200, seite="oben")
p3 = dict(id=1, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=1,
          technik=json.dumps(dict(quelle=sw.QUELLE, a=dict(winkel=0), b=dict(winkel=0), konturen=[poly])))
d = SchneidwegDialog(None, p3, qr, dict(maschine="T11", stange=6000), k3, db3.tabellen(), db3)
r_ed = d.editor
lg0 = next(x for x in d.ergebnis["schritte"] if x.get("eingabe", {}).get("art") == sw.POLYGON)["laenge"]
assert abs(lg0 - 60.0) < 1e-6
schritte0 = r_ed.verlauf.count()


def ziehen(dlg):
    f = dlg.form
    f.resize(400, 300)
    a = f.bild(20.0, 10.0)                                        # Ecke 3 nach x 30 ziehen
    QTest.mousePress(f, Qt.LeftButton, Qt.NoModifier, a.toPoint())
    ziel = f.bild(30.0, 10.0)
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent
    f.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, ziel, ziel, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    f.mouseReleaseEvent(None)
    assert abs(dlg.pk[2][0] - 30) < 0.2 and abs(dlg.pk[2][1] - 10) < 0.2, dlg.pk
    dlg.tab.item(2, 0).setText("30")                             # genau eingeben
    dlg.tab.item(2, 1).setText("10")
    dlg.tab.selectRow(0)
    dlg.einfuegen()                                              # Punkt zwischen 1 und 2 (10, 0)
    assert len(dlg.pk) == 5 and dlg.pk[1][:2] == (10.0, 0.0)
    dlg.tab.selectRow(1)
    dlg.loeschen()
    assert len(dlg.pk) == 4
    # ungültig: Kanten kreuzen -> OK aus
    dlg.tab.item(3, 0).setText("40")
    dlg.tab.item(3, 1).setText("5")
    gesperrt = not dlg.knoepfe.button(QDialogButtonBox.Ok).isEnabled() and "schneiden sich" in dlg.info.text()
    dlg.tab.item(3, 0).setText("0")
    dlg.tab.item(3, 1).setText("10")
    assert gesperrt and dlg.knoepfe.button(QDialogButtonBox.Ok).isEnabled(), (gesperrt, dlg.pk, dlg.info.text())
    dlg._ok()
    return True


assert r_ed.eckpunkte(0, bedienen=ziehen)
e_neu = d.eingaben()["konturen"][0]
assert sw.punkte(e_neu["punkte"]) == [(0, 0), (20, 0), (30, 10), (0, 10)], e_neu["punkte"]
# Mitte des Hüllrechtecks wanderte um 5 mm längs: Lage nachgeführt, Punkt 1 (0,0) bleibt am Rohr
assert abs(e_neu["x"] - 205) < 1e-6, e_neu
lg1 = next(x for x in d.ergebnis["schritte"] if x.get("eingabe", {}).get("art") == sw.POLYGON)["laenge"]
assert abs(lg1 - (20 + math.hypot(10, 10) + 30 + 10)) < 1e-6, lg1
# Rückgängig-Schritt nach kurzer Ruhe: seit 0.9.400 wartet der Editor je nach Rechendauer bis VERZOEGERUNG_MAX
QTest.qWaitFor(lambda: r_ed.verlauf.count() == schritte0 + 1, te.VERZOEGERUNG_MAX + 2000)
assert r_ed.verlauf.count() == schritte0 + 1, (r_ed.verlauf.count(), schritte0)
r_ed.verlauf.undo()
assert d.eingaben()["konturen"][0]["punkte"] == poly["punkte"].replace(" ", "") or \
    sw.punkte(d.eingaben()["konturen"][0]["punkte"]) == sw.punkte(poly["punkte"])
assert abs(d.eingaben()["konturen"][0]["x"] - 200) < 1e-6
r_ed.verlauf.redo()
ok(f"E2 Polygon: Ecke gezogen und genau eingegeben, Punkt eingefügt/gelöscht, Kreuzung gesperrt; Lage +5 mm "
   f"nachgeführt, Rückgängig, Schnittlänge {lg0:g} -> {lg1:.2f} mm aus der Rechnung")

# ------------------------------------------------------------------ E3 Sonderkontur aus dem STEP
umriss = [[-10, -5], [10, -5], [10, 5], [-10, 5]]
sonder = dict(art=sw.SONDERKONTUR, anzahl=1, laenge=60.0, huelle=20.0, umriss=umriss, x=300, seite="oben",
              gemessen=60.0)
p4 = dict(p3, technik=json.dumps(dict(quelle=sw.QUELLE, a=dict(winkel=0), b=dict(winkel=0), konturen=[sonder])),
          step_merkmale="1 Sonderkontur")
d = SchneidwegDialog(None, p4, qr, dict(maschine="T11", stange=6000), k3, db3.tabellen(), db3)
assert d.editor.hand_geaendert() == []


def umriss_aendern(dlg):
    assert not dlg.polygon and dlg.tab.columnCount() == 2 and "Schnittlänge bisher 60" in dlg.info.text()
    dlg.tab.item(1, 0).setText("20")
    dlg.tab.item(2, 0).setText("20")
    dlg._ok()
    return True


assert d.editor.eckpunkte(0, bedienen=umriss_aendern)
e4 = d.eingaben()["konturen"][0]
assert e4["umriss"][1] == [20.0, -5.0] and abs(e4["laenge"] - 80) < 1e-6 and abs(e4["huelle"] - 30) < 1e-6, e4
assert "gemessen" not in e4 or e4.get("laenge") == 80          # gemessene STEP-Länge gilt nicht mehr
d.editor.aktualisieren()
hand = d.editor.hand_geaendert()
assert hand and "Sonderkontur" in hand[0], hand
assert d.editor.eckpunkte(0, bedienen=lambda dlg: False) is False   # Abbrechen ändert nichts
assert d.eingaben()["konturen"][0]["umriss"] == e4["umriss"]
ok("E3 Sonderkontur: Umriss geändert, Schnittlänge 60 -> 80 mm aus den Punkten, Merkmal von Hand geändert")
print("Alle Tests bestanden.")
