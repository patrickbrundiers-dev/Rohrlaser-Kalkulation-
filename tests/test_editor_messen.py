"""3D-Editor Schritt 3E-5 (Plan kalkulation/3d-editor D1, D2): Messen und Querschnitt.
- M1 Messen: Abstand fängt Ecken und Konturmitten, Winkel aus drei Punkten, Maße bleiben stehen bis gelöscht.
- M2 Querschnitt: Konturen, die an der Stelle x die Wand schneiden (auch Kopien am Umfang), Ring im 3D, Fenster im
  Teile-Editor folgt den Eingaben.

Aufruf: python tests/test_editor_messen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, editor_schnitt, rohr3d, schneidweg as sw, skizze as sk  # noqa: E402


def ok(t):
    print("OK    ", t)


QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
RR = dict(form="Rundrohr", a=48.3, wand=3)
eing = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100),
                                  dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="vorne")])

# ------------------------------------------------------------------ M1 Messen
assert abs(ansicht3d.winkel_bei((1, 0, 0), (0, 0, 0), (0, 1, 0)) - 90) < 1e-9
assert abs(ansicht3d.winkel_bei((1, 0, 0), (0, 0, 0), (1, 1, 0)) - 45) < 1e-9
a = ansicht3d.Ansicht3D()
a.resize(900, 400)
a.setzen(rohr3d.netz(eing, QR, 500))
mo = a.modell
assert len(mo.mitten) == 2
m0 = mo.mitten[0]
assert abs(m0[2] - 100) < 0.5 and abs(m0[0]) < 0.5 and abs(m0[1] - 20.4) < 0.1      # Bohrung oben bei x = 100
bild = a.bildpunkt()
a.messen_setzen(True)
for v in (m0, mo.mitten[1]):
    px, py, _ = bild(v)
    a.klicken(px, py)
# seit 3E-11 fängt Messen die exakte Kreismitte (auf der Wand, nicht 0,4 mm darüber) und die Mitte des Langlochs
soll = [(0.0, 20.0, 100.0), (-20.0, 0.0, 300.0)]
assert all(math.dist(p, q) < 1e-6 for p, q in zip(a.messpunkte, soll)), a.messpunkte
assert abs(a.abstand() - math.dist(*soll)) < 1e-9
assert a.mess_text().startswith("Abstand") and len(a.masse_fest) == 1
# Winkel: drei Ecken
a.messen_setzen(True, art=ansicht3d.MESS_WINKEL)
assert a.mess_max == 3 and a.abstand() is None
ecken = sorted(mo.punkte, key=lambda p: (p[2], -p[1], p[0]))[:1]
a.messpunkte = [(0.0, 20.0, 0.0), (0.0, 20.0, 100.0), (20.0, 20.0, 100.0)]
assert abs(a.winkel() - 90) < 1e-9 and a.mess_text().startswith("Winkel 90")
a.messpunkte = []
for v in ((mo.mitten[0]), (mo.mitten[1]), ecken[0]):
    px, py, _ = bild(v)
    a.klicken(px, py)
assert len(a.messpunkte) == 3 and a.winkel() is not None and len(a.masse_fest) == 2
a.grab()
a.masse_loeschen()
assert a.masse_fest == [] and a.messpunkte == []
ok("M1 Messen: Konturmitten fangen, Abstand, Winkel aus drei Punkten, Maße bleiben stehen, löschen")

# ------------------------------------------------------------------ M2 Querschnitt
qs = sk.Querschnitt(QR)
assert editor_schnitt.stellen(eing, qs, 500, 50) == []
st = editor_schnitt.stellen(eing, qs, 500, 100)
assert len(st) == 1 and st[0][2] == 0 and abs((st[0][1] - st[0][0]) - 10) < 0.2       # Bohrung Ø 10 mitten
assert len(editor_schnitt.stellen(eing, qs, 500, 310)) == 1                            # Langloch 30 lang
assert editor_schnitt.stellen(eing, qs, 500, 316) == []
beide = dict(eing, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, wand="beide")])
assert len(editor_schnitt.stellen(beide, qs, 500, 100)) == 2
qr = sk.Querschnitt(RR)
um = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=12, x=60, wand="umfang", umfang_n=4)])
assert len(editor_schnitt.stellen(um, qr, 200, 60)) == 4
assert editor_schnitt.stellen(dict(a={}, b={}, konturen=[dict(art=sw.GRAVUR, anzahl=1, laenge=20, x=60)]),
                              qr, 200, 60) == []
r = editor_schnitt.ring(qs, 120)
assert r and all(p[2] == 120 for p in r) and r[0] == r[-1]
b = editor_schnitt.SchnittBild()
b.resize(320, 300)
b.setzen(qs, st, 100)
b.grab()
# Fenster im Teile-Editor
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
p = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10,
         technik=json.dumps(dict(eing, quelle=sw.QUELLE)))
d = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed = d.editor
for text in ("Messen", "Winkel", "Maße löschen", "Querschnitt"):
    assert ed.band.knopf(text) is not None, text
ed.band.knopf("Winkel").click()
a3 = d.ansicht3d.ansicht
assert a3.messen and a3.mess_art == ansicht3d.MESS_WINKEL and not ed.messen_knopf.isChecked()
ed.messen_knopf.click()
assert a3.mess_art == ansicht3d.MESS_ABSTAND and not ed.winkel_knopf.isChecked()
ed.messen_knopf.click()
ed.band.knopf("Querschnitt").click()
f = ed.schnitt_fenster
assert f.isVisible() and abs(f.feld.value() - 250) < 1e-6 and a3.schnitt_linie
f.setzen(100)
assert "Zeile 1 Bohrung" in f.text.text() and all(abs(q[2] - 100) < 1e-6 for q in a3.schnitt_linie)
f.schieber.setValue(600)
assert abs(f.feld.value() - 300) < 1e-6 and "Zeile 2 Langloch" in f.text.text()
d.eingaben_setzen(dict(a={}, b={}, konturen=[dict(art=sw.RECHTECK, anzahl=1, b=20, h=10, r=0, x=300)]))
ed.aktualisieren()                                   # wie nach dem Zeitgeber
assert "Zeile 1 Rechteck" in f.text.text(), f.text.text()          # folgt den Eingaben
ed.band.knopf("Querschnitt").click()
assert not f.isVisible() and a3.schnitt_linie == []
ok("M2 Querschnitt: geschnittene Konturen an der Stelle x (Kopien, Rundrohr), Ring im 3D, Fenster folgt den Eingaben")
print("Alle Tests Messen und Querschnitt bestanden.")
