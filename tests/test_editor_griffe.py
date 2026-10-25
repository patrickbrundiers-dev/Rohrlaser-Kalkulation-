"""3D-Editor 3E-3: am Modell bearbeiten (Plan kalkulation/3d-editor, Bausteine A4, B4, B6, C1, C2, C4, G1, G3):
- G1 Fangen und Hilfsrechnungen: Raster, Teilmitte, Flächenmitte, Winkel der Schnittebene, Spiegeln, Gegenseite.
- G2 Griffe: Pfeil längs ziehen (Raster, Live-Maß, ein Rückgängig-Schritt), quer auf die Nachbarfläche, Alt = frei,
  Schnittebene ziehen = Gehrungswinkel.
- G3 Maße am Modell: ab A, bis B, zur Nachbarkontur; Eingabe am Maß (Rechnung L/2).
- G4 Pfeiltasten (Umschalt ×10), Ende ±1°; Rundrohr in Winkelschritten.
- G5 Kontextmenü (Kontur, Ende, Darstellung), Spiegeln, Gegenseite.
- G6 Darstellungsarten (Schattiert, Mit Kanten, Durchsichtig, nur Gewähltes) zeichnen und werden gemerkt; Körperkanten.

Aufruf: python tests/test_editor_griffe.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, editor_griffe as eg, rohr3d, schneidweg as sw, skizze as sk  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ G1 Fangen und Hilfsrechnungen
assert eg.fangen(123.4, 5) == 125 and eg.fangen(123.4, 5, an=False) == 123.4
assert eg.fangen(248.1, 5, (249.0,)) == 249.0 and eg.fangen(246.0, 5, (249.0,)) == 245.0
assert eg.winkel_fangen(44.0) == 45 and eg.winkel_fangen(41.6) == 42 and eg.winkel_fangen(95) == 79.9
assert eg.winkel_fangen(41.66, an=False) == 41.7
QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3", r_aussen=0)
qs = sk.Querschnitt(QR)
(u, v), n, t = eg.mitte_uv(qs, dict(seite="vorne"))
assert (round(u, 3), round(v, 3)) == (20, 0) and n == qs.flaeche("vorne").n
assert eg.quer_neu(qs, dict(seite="vorne"), 30, 5) == dict(seite="unten", q=-10.0)      # über die Kante
assert eg.quer_neu(qs, dict(seite="vorne"), 2, 5) == dict(seite="vorne", q=None)       # fängt Flächenmitte
rund = sk.Querschnitt(dict(form="Rundrohr", a=40, wand=2))
assert eg.quer_neu(rund, dict(seite=0), rund.r * 0.8, 15) == dict(seite=45.0, q=None)
assert eg.x_neu(dict(anzahl=3), None, 120, 500) == dict(x=120, abstand=125.0)          # verteilt → Muster
assert eg.gespiegelt(dict(anzahl=2, x=100, abstand=50), [dict(x=100), dict(x=150)], 500) == dict(x=350)
assert eg.gegenseite(qs, dict(seite="vorne", q=5)) == dict(seite="hinten", q=5)
assert eg.gegenseite(rund, dict(seite=270)) == dict(seite=90, q=None)
ecken = eg.ebene_ecken(qs, dict(winkel=45, achse="über Höhe"), 500, "a")
assert max(e[0] for e in ecken) - min(e[0] for e in ecken) > 40          # Ebene schräg
from rohrlaser import steckverbindung as stv  # noqa: E402
qr = dict(profil_id="QR 40x40x2", form="Quadratrohr", a=40, b=40, wand=2, r_aussen=0)
_, mit_nasen, plus = stv.anwenden(stv.neu(dict(id=1), dict(id=2), qr, {}, ende="b", x=200, seite="oben"),
                                  dict(a={}, b={}, konturen=[]), dict(a={}, b={}, konturen=[]), qr, qr)
assert plus > 0 and eg.nasen_plus(mit_nasen["b"]) == plus
assert {round(e[0], 3) for e in eg.ebene_ecken(qs, mit_nasen["b"], 500, "b")} == {500 - plus}   # Schnitt, nicht Spitze
assert eg.ebene_griff(qs, dict(sattel=50)) is None and eg.ebene_griff(qs, dict(achse=sw.ACHSE_ZWEI)) is None
ok("G1 Fangen (Raster, Marken, Winkel), Mitte/Richtung quer, über die Kante, Muster, Spiegeln, Gegenseite, Ebene")

# ------------------------------------------------------------------ G2 Griffe
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
eing = dict(a=dict(winkel=45, achse="über Höhe"), b={},
            konturen=[dict(art=sw.BOHRUNG, anzahl=2, d=10, x=100, abstand=50),
                      dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="vorne"),
                      dict(art=sw.BOHRUNG, anzahl=1, d=8, x=180)])
p = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10,
         technik=json.dumps(dict(eing, quelle=sw.QUELLE)))
d = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed, a = d.editor, d.ansicht3d.ansicht
w = ed.werkzeug
assert a.werkzeug is w and w.aktiv() and a.hasMouseTracking()
d.resize(1600, 1000)
d.show()
app.processEvents()
ed.modus_setzen("3D")
app.processEvents()
ed.waehlen("kontur:1")
a.grab()
assert {g["art"] for g in w._griffe} == {"ende", "laengs", "quer"}, [g["art"] for g in w._griffe]
assert "Pfeile ziehen" in w.hinweis()
schritte = ed.verlauf.count()
g = next(x for x in w._griffe if x["art"] == "laengs")
assert w.treffer(g["b"]) is not None and w.treffer(QPointF(-50, -50)) is None
assert w.druck(g["b"], Qt.LeftButton) and ed._still
w.ziehen(g["b"] + g["richtung"] * 23.0)                     # 23 mm → Raster 5: 325
assert d.eingaben()["konturen"][1]["x"] == 325 and "ab Ende A 325 mm" in w.live, w.live
w.ziehen(g["b"] + g["richtung"] * 23.0, Qt.AltModifier)     # Alt: frei
assert d.eingaben()["konturen"][1]["x"] == 323
w.loslassen()
assert not ed._still and ed.verlauf.count() == schritte + 1 and ed.gewaehlt == "kontur:1" and not w.live
ed.verlauf.undo()
assert d.eingaben()["konturen"][1]["x"] == 300
ed.verlauf.redo()
ed.waehlen("kontur:1")
a.grab()
g = next(x for x in w._griffe if x["art"] == "quer")
w.druck(g["b"], Qt.LeftButton)
w.ziehen(g["b"] + g["richtung"] * 30)
w.loslassen()
assert d.eingaben()["konturen"][1]["seite"] == "unten" and d.eingaben()["konturen"][1]["q"] == -10
ed.waehlen("ende:a")
a.grab()
g = next(x for x in w._griffe if x["art"] == "ende" and x["seite"] == "a")
w.druck(g["punkt"], Qt.LeftButton)
w.ziehen(g["punkt"] - g["richtung"] * 10)                   # Spitze 40 → 30 mm hinter der Kante: atan(30/40)
assert "37" in w.live
w.loslassen()
assert d.winkel["a"].value() == 37
ok("G2 Griffe: längs mit Raster und Alt, Live-Maß, ein Rückgängig-Schritt; quer auf die Nachbarfläche; Ebene = Gehrung")

# ------------------------------------------------------------------ G3 Maße am Modell
ed.waehlen("kontur:2")
a.grab()
arten = {m["art"]: m for m in w._mass_felder}
assert set(arten) == {"a", "b", "nachbar"} and arten["a"]["wert"] == 180 and arten["b"]["wert"] == 320
assert arten["nachbar"]["wert"] == 30                       # zur zweiten Bohrung bei 150
assert w.doppelklick(arten["b"]["rect"].center()) and w._feld is not None
w._feld.setText("L/2")
w._feld.uebernehmen()
assert d.eingaben()["konturen"][2]["x"] == 250
a.grab()
nb = next(m for m in w._mass_felder if m["art"] == "nachbar")
assert nb["bezug"] == 150 and w.mass_setzen(nb, 2, 20) and d.eingaben()["konturen"][2]["x"] == 170
ok("G3 Maße am Modell: ab A, bis B, zur Nachbarkontur; Doppelklick öffnet das Feld, Rechnung L/2")

# ------------------------------------------------------------------ G4 Pfeiltasten
ed.waehlen("kontur:2")
x0 = d.eingaben()["konturen"][2]["x"]
assert w.taste(QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))
assert d.eingaben()["konturen"][2]["x"] == x0 - 5
assert w.taste(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.ShiftModifier))
assert d.eingaben()["konturen"][2]["x"] == x0 + 45
assert w.taste(QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier)) and d.eingaben()["konturen"][2]["q"] == 5
assert not w.taste(QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier))
ed.waehlen("ende:b")
assert w.taste(QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.ShiftModifier)) and d.winkel["b"].value() == 10
ok("G4 Pfeiltasten: Rasterschritt, Umschalt ×10, quer; Ende ±1°/10°")

# ------------------------------------------------------------------ G5 Kontextmenü
texte = [x.text().split("\t")[0] for x in ed.kontextmenue("kontur:0", (10, 10)).actions()]
for t_ in ("Duplizieren", "Spiegeln zur Teilmitte", "Auf die Gegenseite", "Entfernen", "Messen von hier",
           "Darstellung", "Ausgangsansicht"):
    assert t_ in texte, (t_, texte)
m = ed.kontextmenue("ende:b")
next(x for x in m.actions() if x.text().startswith("Gehrung 45")).trigger()
assert d.winkel["b"].value() == 45
assert ed.spiegeln(0) and d.eingaben()["konturen"][0]["x"] == 350
assert ed.gegenseite(0) and d.eingaben()["konturen"][0]["seite"] == "unten"
m = ed.kontextmenue("kontur:0")
next(x for x in m.actions() if x.text().startswith("Duplizieren")).trigger()
assert d.tabelle.rowCount() == 4 and ed.gewaehlt == "kontur:3"
ed.waehlen("kontur:1")
a.grab()
nr = next(i for i, kn in enumerate(a.modell.linien_id) if kn == "kontur:1")
px, py, _ = a.bildpunkt()(a.modell.linien[nr][0])
ed.messen_ab((px + 3, py))                                  # fängt den Punkt der Kontur
assert a.messen and len(a.messpunkte) == 1
ed.messen_knopf.setChecked(False)
ok("G5 Kontextmenü: Kontur und Ende, Spiegeln, Gegenseite, Duplizieren, Messen von hier")

# ------------------------------------------------------------------ G6 Darstellungsarten
for dar in ansicht3d.DARSTELLUNGEN:
    ed.darstellung_setzen(dar)
    assert a.darstellung == dar and ed.darstellung_wahl.currentText() == dar
    a.grab()
assert db.einstellung("editor_darstellung") == ansicht3d.DURCHSICHTIG
ed.darstellung_setzen(nur_gewaehlt=True)
assert a.blass() and ed.nur_gewaehlt_knopf.isChecked() and db.einstellung("editor_nur_gewaehlt") is True
a.grab()
ed.anzeige_setzen("masse", False)
ed.anzeige_setzen("raster", 2.5)
assert db.einstellung("editor_masse") is False and db.einstellung("editor_raster") == 2.5
ed.waehlen("kontur:1")
a.grab()
assert not w._mass_felder
# gemerkt: neuer Editor übernimmt Darstellung und Raster
d2 = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
assert d2.ansicht3d.ansicht.darstellung == ansicht3d.DURCHSICHTIG and d2.editor.werkzeug.raster == 2.5
assert d2.editor.werkzeug.masse is False and d2.editor.raster_feld.value() == 2.5
# Körperkanten: Stirnflächen und Gehrung sind Kanten, die glatte Rundung nicht
mo = ansicht3d.Modell(rohr3d.netz(eing, dict(QR, r_aussen=None), 500))
kanten = mo.kanten()
assert kanten and len(kanten) < len(mo.dreiecke) and mo.kanten() is kanten
ok("G6 Darstellungsarten zeichnen, nur Gewähltes blass, je Benutzer gemerkt; Körperkanten einmal je Modell")
# Editor öffnet immer maximiert (Patrick 24.10.2026)
from PySide6.QtCore import QTimer  # noqa: E402
from rohrlaser import teile_editor  # noqa: E402

zustand = {}
QTimer.singleShot(0, lambda: (zustand.update(max=bool(d2.windowState() & Qt.WindowMaximized)), d2.reject()))
teile_editor.ausfuehren(d2)
assert zustand["max"] and d2.windowFlags() & Qt.WindowMaximizeButtonHint
ok("G7 Teile-Editor öffnet maximiert")
print("OK: 3D-Editor am Modell bearbeiten (3E-3)")
