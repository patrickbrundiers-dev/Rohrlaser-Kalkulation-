"""3D-Maus in jeder Belegung (Patrick 25.11.2026: „Drehen im 3D prüfen, mein Mausrad hat heute nicht funktioniert bzw.
das Verschieben ging nicht“).

Befund: Auf Patricks Arbeitsplatz stand die Mausbelegung „wie Inventor“. Dort tat die rechte Taste nichts, der Hinweis
unten im 3D sagte aber „rechte verschieben“. Jetzt:

M1 In jeder Belegung: links ziehen dreht, rechts ziehen verschiebt; die Belegung legt nur die mittlere Taste fest
M2 Echte Ereignisse über das Fenster (wie unter Windows: Qt sucht das Widget unter der Maus): Rad zoomt, links dreht,
   rechts und Mitte verschieben bzw. drehen nach der Belegung, in Ansicht3D und Ansicht3DMitKnoepfen
M3 Hinweis unten im 3D nennt die Tasten der eingestellten Belegung (nie „rechte verschieben“, wenn rechts nichts tut)
M4 Mausrad: auch waagrecht (Alt) und in Pixeln (Touchpad) zoomen; Rad 0 ändert nichts
M5 Rechtsklick ohne Ziehen bleibt das Kontextmenü des Editors (kein Verschieben)

Aufruf: python tests/test_maus_3d.py
"""
import os
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, mausrad, navigation3d as nav, rohr3d, schneidweg as sw  # noqa: E402

mausrad.einrichten(app)
ansicht3d.renderer_setzen("Software")


def ok(t):
    print("OK    ", t)


class Speicher:
    """Einstellungen wie die Datenbank (nur einstellung), ohne PostgreSQL."""

    def __init__(self):
        self.werte = {}

    def einstellung(self, name):
        return self.werte.get(name)


speicher = Speicher()
ansicht3d.speicher_setzen(speicher)
BELEGUNGEN = list(nav.MAUSBELEGUNGEN)

# ------------------------------------------------------------------ M1 Belegungen
for b in BELEGUNGEN:
    w = {"nav_maus": b}
    assert nav.aktion("links", set(), w) == "drehen", b
    assert nav.aktion("rechts", set(), w) == "schieben", b
    assert nav.aktion("rechts", {"umschalt"}, w) == "schieben", b
    assert nav.aktion("mitte", set(), w) in ("drehen", "schieben"), b
inv, solidworks, creo = BELEGUNGEN[1:4]
assert nav.aktion("mitte", {"umschalt"}, {"nav_maus": inv}) == "drehen"
assert nav.aktion("mitte", set(), {"nav_maus": inv}) == "schieben"
assert nav.aktion("mitte", set(), {"nav_maus": solidworks}) == "drehen"
assert nav.aktion("mitte", {"strg"}, {"nav_maus": solidworks}) == "schieben"
assert nav.aktion("mitte", {"umschalt"}, {"nav_maus": creo}) == "schieben"
assert nav.aktion(None, set(), {}) is None
ok("M1 jede Belegung: links dreht, rechts verschiebt; Mitte nach Programm/Inventor/SolidWorks/Creo")

# ------------------------------------------------------------------ M2 echte Ereignisse über das Fenster
QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
netz = rohr3d.netz(dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100)]), QR, 500)


def fenster_mit(art):
    top = QWidget()
    lay = QVBoxLayout(top)
    if art == "knoepfe":
        mk = ansicht3d.Ansicht3DMitKnoepfen()
        lay.addWidget(mk)
        mk.setzen(netz, "Test")
        a = mk.ansicht
    else:
        a = ansicht3d.Ansicht3D()
        lay.addWidget(a)
        a.setzen(netz)
    top.resize(900, 600)
    top.show()
    for _ in range(5):
        app.processEvents()
    return top, a


def rad(win, pt, wy=120, wx=0, py=0, mod=Qt.NoModifier):
    ev = QWheelEvent(QPointF(pt), QPointF(win.mapToGlobal(pt)), QPoint(0, py), QPoint(wx, wy), Qt.NoButton, mod,
                     Qt.NoScrollPhase, False)
    QApplication.sendEvent(win, ev)
    app.processEvents()


def ziehen(win, pt, knopf, mod=Qt.NoModifier):
    QTest.mousePress(win, knopf, mod, pt)
    for i in range(1, 6):
        QTest.mouseMove(win, pt + QPoint(8 * i, 5 * i))
        app.processEvents()
    QTest.mouseRelease(win, knopf, mod, pt + QPoint(40, 25))
    app.processEvents()


def wirkung(a, vorher):
    zoom, versatz, lage = vorher
    if (a.gier, a.nick, a.roll) != lage:
        return "drehen"
    if a.versatz != versatz:
        return "schieben"
    return "zoom" if a.zoom != zoom else None


def stand(a):
    return a.zoom, a.versatz, (a.gier, a.nick, a.roll)


ERWARTET = {  # Belegung: {(Taste, Zusatz): Wirkung}
    BELEGUNGEN[0]: {(Qt.MiddleButton, Qt.NoModifier): "schieben"},
    inv: {(Qt.MiddleButton, Qt.NoModifier): "schieben", (Qt.MiddleButton, Qt.ShiftModifier): "drehen"},
    solidworks: {(Qt.MiddleButton, Qt.NoModifier): "drehen", (Qt.MiddleButton, Qt.ControlModifier): "schieben"},
    creo: {(Qt.MiddleButton, Qt.NoModifier): "drehen", (Qt.MiddleButton, Qt.ShiftModifier): "schieben"},
}
gesehen = 0
for art in ("ansicht", "knoepfe"):
    top, a = fenster_mit(art)
    win = top.windowHandle()
    for b in BELEGUNGEN:
        speicher.werte["nav_maus"] = b
        a.zuruecksetzen()
        pt = a.mapTo(top, QPoint(a.width() // 2, a.height() // 2))
        assert top.childAt(pt) is a, (art, top.childAt(pt))      # nichts liegt über dem 3D
        v = stand(a)
        rad(win, pt)
        assert wirkung(a, v) == "zoom" and a.zoom > v[0], (art, b)
        v = stand(a)
        rad(win, pt, wy=-120)
        assert a.zoom < v[0], (art, b)
        faelle = {(Qt.LeftButton, Qt.NoModifier): "drehen", (Qt.RightButton, Qt.NoModifier): "schieben",
                  **ERWARTET[b]}
        for (knopf, mod), soll in faelle.items():
            v = stand(a)
            ziehen(win, pt, knopf, mod)
            ist = wirkung(a, v)
            assert ist == soll, (art, b, knopf, mod, ist, soll)
            assert a._maus is None, "Taste hängt nach dem Loslassen"
            gesehen += 1
    top.close()
ok(f"M2 echte Fensterereignisse in Ansicht3D und Ansicht3DMitKnoepfen, alle {len(BELEGUNGEN)} Belegungen: Rad zoomt "
   f"(beide Richtungen), {gesehen} Zieh-Fälle drehen/verschieben wie erwartet")

# ------------------------------------------------------------------ M3 Hinweis nach der Belegung
for b in BELEGUNGEN:
    h = nav.hinweis({"nav_maus": b})
    assert h.startswith("Drehen") and "links" in h and "Verschieben: rechts" in h and "Mausrad zoomen" in h, h
assert "Umschalt+Rad gedrückt" in nav.hinweis({"nav_maus": inv}).split("·")[0]
assert "Strg+Rad gedrückt" in nav.hinweis({"nav_maus": solidworks}).split("·")[1]
assert nav.hinweis({}) == "Drehen: links ziehen · Verschieben: rechts oder Rad gedrückt ziehen · Mausrad zoomen"
speicher.werte["nav_maus"] = inv
from PySide6.QtGui import QImage, QPainter  # noqa: E402
a = ansicht3d.Ansicht3D()
a.resize(1600, 400)
a.setzen(netz)
texte = []
bild = QImage(1600, 400, QImage.Format_ARGB32)
p = QPainter(bild)
orig = p.drawText


def merken(*args):
    texte.append(str(args[-1]))
    return orig(*args)


p.drawText = merken
a._beschriften(p)
p.end()
unten = [t for t in texte if "Mausrad zoomen" in t]
assert unten and "Umschalt+Rad gedrückt" in unten[0] and "rechte verschieben" not in unten[0], texte
ok("M3 Hinweis unten im 3D nennt die Tasten der Belegung (Inventor: Umschalt+Rad gedrückt drehen, rechts/Rad gedrückt verschieben)")

# ------------------------------------------------------------------ M4 Mausrad waagrecht / Pixel
assert nav.rad_schritte(120) == 120 and nav.rad_schritte(0, -120) == -120 and nav.rad_schritte(0, 0, 15) == 120
assert nav.rad_schritte(0, 0, 0) == 0
top, a = fenster_mit("ansicht")
win = top.windowHandle()
pt = a.mapTo(top, QPoint(a.width() // 2, a.height() // 2))
for kw in (dict(wy=0, wx=120), dict(wy=0, py=20)):
    z = a.zoom
    rad(win, pt, **kw)
    assert a.zoom > z, kw
z = a.zoom
rad(win, pt, wy=0)
assert a.zoom == z
top.close()
ok("M4 Mausrad waagrecht (Alt) und Touchpad-Pixel zoomen, Rad 0 ändert nichts")

# ------------------------------------------------------------------ M5 Rechtsklick ohne Ziehen = Menü
speicher.werte["nav_maus"] = BELEGUNGEN[0]


class Werkzeug:
    def __init__(self):
        self.menue = 0

    def druck(self, *_):
        return False

    def kontext(self, *_):
        self.menue += 1

    def schweben(self, *_):
        pass

    def hinweis(self):
        return None

    def zeichnen(self, *_):
        pass


top, a = fenster_mit("ansicht")
a.werkzeug = Werkzeug()
win = top.windowHandle()
pt = a.mapTo(top, QPoint(a.width() // 2, a.height() // 2))
v = stand(a)
QTest.mouseClick(win, Qt.RightButton, Qt.NoModifier, pt)
app.processEvents()
assert a.werkzeug.menue == 1 and a.versatz == v[1]
ziehen(win, pt, Qt.RightButton)
assert a.werkzeug.menue == 1 and a.versatz != v[1]
top.close()
ok("M5 Rechtsklick ohne Ziehen öffnet das Menü, rechts ziehen verschiebt")
print("Alle Prüfungen bestanden.")
