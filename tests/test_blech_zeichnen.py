"""3D-Editor Schritt 3E-4b (Plan kalkulation/3d-editor C5): Blech zeichnen und Drehwinkel der Blech-Konturen.
- Z1 Rechnung: Ecke abrunden und fasen, Punkt einfügen/löschen, Biegelinie und Außenkante ziehen (Schenkel).
- Z2 Drehwinkel: Langloch, Rechteck und Polygon gedreht in Umriss, Abstand zu den Biegelinien, 3D und DXF
  (Schnittlänge bleibt).
- Z3 Abwicklung mit der Maus: Kontur ziehen, Außenkante ziehen, Außenkontur mit Klicks zeichnen, Ecke abrunden,
  Biegelinie des Kantteils ziehen, Klick wählt das Merkmal im Teile-Editor, Drehwinkel im Eigenschaften-Feld.

Aufruf: python tests/test_blech_zeichnen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import blech, blech3d, blech_zeichnen as bz, dxf, schneidweg as sw  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ Z1 Rechnung
Q = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
r = bz.ecke_runden(Q, 2, 10)
assert len(r) > 5 and r[0] == Q[0] and r[-1] == Q[3]
bogen = r[2:-1]
assert all(abs(math.dist(p, (90, 90)) - 10) < 1e-9 for p in bogen)
assert abs(bogen[0][0] - 100) < 1e-9 and abs(bogen[0][1] - 90) < 1e-9
assert abs(bogen[-1][0] - 90) < 1e-9 and abs(bogen[-1][1] - 100) < 1e-9
assert abs(blech.flaeche_polygon(r) - (10000 - (4 - math.pi) * 100 / 4)) < 2      # Bogen als Sehnen
f = bz.ecke_fasen(Q, 0, 5)
assert f[:2] == [(0.0, 5.0), (5.0, 0.0)] and len(f) == 5
for fn, w in ((bz.ecke_runden, 200), (bz.ecke_fasen, 100)):
    try:
        fn(Q, 1, w)
        raise AssertionError("zu groß")
    except ValueError:
        pass
assert bz.punkt_weg(f, 0) == f[1:] and bz.punkt_einfuegen(Q, 0, (50, 0))[1] == (50, 0)
assert bz.naechste_ecke(Q, (99, 1), 2) == 1 and bz.naechste_ecke(Q, (50, 50), 2) is None
assert bz.naechste_kante(Q, (50, 0.5), 1) == (0, (50.0, 0.0))
assert bz.text([(0, 0), (12.5, 3)]) == "0,0; 12.5,3" and sw.punkte(bz.text(r)) == [(round(x, 3), round(y, 3)) for x, y in r]
sch = [dict(laenge=50, winkel=90), dict(laenge=80, winkel=90), dict(laenge=50, winkel=0)]
assert [x["laenge"] for x in bz.schenkel_ziehen(sch, 0, 10)] == [60, 70, 50]
assert [x["laenge"] for x in bz.schenkel_ziehen(sch, -1, 5)] == [55, 80, 50]
assert [x["laenge"] for x in bz.schenkel_ziehen(sch, 3, 5)] == [50, 80, 55]
try:
    bz.schenkel_ziehen(sch, 0, 90)
    raise AssertionError("zu kurz")
except ValueError:
    pass
assert bz.rechtwinklig((0, 0), (10, 2)) == (10, 0) and bz.fangen(12.4, 5) == 10
ok("Z1 Ecke abrunden/fasen, Punkt einfügen/löschen, Biegelinie und Außenkante ziehen")

# ------------------------------------------------------------------ Z2 Drehwinkel
ll = dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=100, y=50)
u0, u90 = blech.kontur_umriss(ll), blech.kontur_umriss(dict(ll, drehung=90))
ausd = lambda zug, i: max(p[i] for p in zug) - min(p[i] for p in zug)     # noqa: E731
assert abs(ausd(u0, 0) - 30) < 1e-6 and abs(ausd(u0, 1) - 10) < 1e-6
assert abs(ausd(u90, 0) - 10) < 1e-6 and abs(ausd(u90, 1) - 30) < 1e-6
assert abs(blech._halbmass(dict(ll, drehung=90))[0] - 15) < 1e-6 and abs(blech._halbmass(ll)[0] - 5) < 1e-6
assert blech.drehung(dict(art=sw.BOHRUNG, drehung=30)) == 0 and blech.drehung(dict(ll, drehung=-90)) == 270
re = dict(art=sw.RECHTECK, anzahl=1, b=40, h=10, r=2, x=100, y=50, drehung=45)
assert abs(ausd(blech.kontur_umriss(re), 0) - ausd(blech.kontur_umriss(re), 1)) < 1e-6
e = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100, konturen=[dict(ll, drehung=90)])
zs = blech.zuschnitt(e)
zug = blech3d.konturzuege(e, zs)[0][1]
assert abs(ausd(zug, 1) - 30) < 1e-6 and abs(sum(p[0] for p in zug[:-1]) / (len(zug) - 1) - 100) < 1e-6
el0, _ = dxf.elemente(dict(e, konturen=[ll]), zs)
el9, _ = dxf.elemente(e, zs)
assert abs(dxf.schnittlaenge(el0)[dxf.INNEN] - dxf.schnittlaenge(el9)[dxf.INNEN]) < 1e-6
innen = [x for x in el9 if x[1] == dxf.INNEN and x[0] == "LINE"]
assert all(abs(x[2][0] - x[3][0]) < 1e-6 for x in innen)                 # gerade Seiten jetzt senkrecht
assert blech3d.netz(e, zs)
ok("Z2 Drehwinkel: Umriss, Abstand quer, 3D-Konturzug und DXF gedreht, Schnittlänge gleich")

# ------------------------------------------------------------------ Z3 Abwicklung mit der Maus
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
d = BlechDialog(None, db, dict(e, werkstoff=werkstoff, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=50, y=50)]))
d.resize(1366, 728)
d.show()
app.processEvents()
s = d.skizze
s.grab()
ed = d.editor


def pt(x, y):
    q = s.px(x, y)
    return QPoint(round(q.x()), round(q.y()))


def ziehen(von, nach):
    QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, pt(*von))
    QTest.mouseMove(s, pt(*nach))
    QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, pt(*nach))
    app.processEvents()
    s.grab()


assert s.treffer(s.px(50, 50)) == ("kontur", 0)
ziehen((50, 50), (80, 30))
k = d.eingaben()["konturen"][0]
assert abs(k["x"] - 80) <= 1 and abs(k["y"] - 30) <= 1, k
assert ed.gewaehlt == "kontur:0" and ed.eigenschaften.mid == "kontur:0"
assert "Drehwinkel" not in ed.eigenschaften.felder                       # Bohrung: kein Drehwinkel
ziehen((200, 70), (240, 70))                                             # rechte Kante: Länge
assert abs(d.eingaben()["laenge"] - 240) <= 1.5, d.eingaben()["laenge"]
ed.verlauf.undo()
assert abs(d.eingaben()["laenge"] - 200) < 1e-6
# Außenkontur zeichnen
s.grab()
s.zeichnen_starten()
for q in ((0, 0), (150, 0), (150, 60), (60, 100), (0, 100)):
    QTest.mouseClick(s, Qt.LeftButton, Qt.NoModifier, pt(*q))
QTest.mouseClick(s, Qt.LeftButton, Qt.NoModifier, pt(0, 0))              # erster Punkt schließt
app.processEvents()
e2 = d.eingaben()
pk = sw.punkte(e2["punkte"])
assert e2["form"] == blech.POLYGON and len(pk) == 5, e2["punkte"]
assert all(math.dist(a, b) <= 1.5 for a, b in zip(pk, ((0, 0), (150, 0), (150, 60), (60, 100), (0, 100))))
s.grab()
m = s.menue(pt(150, 0))
assert [a.text() for a in m.actions()][:3] == ["Ecke abrunden …", "Ecke fasen …", "Punkt löschen"]
assert s.ecke_aendern(bz.ecke_runden, 1, 10)
assert len(sw.punkte(d.eingaben()["punkte"])) > 6
s.grab()
s.zeichnen_starten()
QTest.mouseClick(s, Qt.LeftButton, Qt.NoModifier, pt(10, 10))
QTest.keyClick(s, Qt.Key_Escape)
assert s._neu is None and d.eingaben()["form"] == blech.POLYGON
# Drehwinkel im Eigenschaften-Feld
d.eingaben_setzen(dict(e, werkstoff=werkstoff, konturen=[dict(ll)]))
ed.aktualisieren()
ed.waehlen("kontur:0")
f = ed.eigenschaften.felder["Drehwinkel"]
f.setText("90")
f.uebernehmen()
assert d.eingaben()["konturen"][0]["drehung"] == 90
s.grab()
# Kantteil: Biegelinie ziehen
kant = dict(art=blech.KANTTEIL, form=blech.RECHTECK, dicke=2, kantlaenge=200, werkstoff=werkstoff,
            schenkel=[dict(laenge=50, winkel=90), dict(laenge=80, winkel=90), dict(laenge=50, winkel=0)], konturen=[])
d.eingaben_setzen(kant)
ed.aktualisieren()
s.grab()
lage = d.ergebnis["zuschnitt"]["biegungen"][0][0]
assert s.treffer(s.px(100, lage)) == ("biegung", 0)
ziehen((100, lage), (100, lage + 10))
sch = d.eingaben()["schenkel"]
assert abs(sch[0]["laenge"] - 60) <= 1 and abs(sch[1]["laenge"] - 70) <= 1, sch
assert ed.gewaehlt == "biegung:0"
br = d.ergebnis["zuschnitt"]["breite"]
ziehen((100, br), (100, br + 5))                                        # obere Kante: letzter Schenkel
assert abs(d.eingaben()["schenkel"][-1]["laenge"] - 55) <= 1
for k_ in ("Zeichnen", "Als Polygon"):
    assert ed.band.knopf(k_) is not None
ok("Z3 Abwicklung: Kontur und Kanten ziehen, Außenkontur zeichnen, Ecke runden, Biegelinie ziehen, Drehwinkel")
print("Alle Tests Blech zeichnen bestanden.")
