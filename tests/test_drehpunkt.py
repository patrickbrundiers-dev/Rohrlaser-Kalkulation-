"""3D-Ansicht: Drehpunkt am Mauszeiger und Zoom zur Mausposition (Patrick 25.10.2026) in allen 3D-Fenstern
(gemeinsame Ansicht3D: Teile-Editor Rohr/Blech, Baugruppe, Satz in 3D, STEP-Prüfdialog).
- Drücken auf dem Modell: der Punkt darunter bleibt beim Drehen an seinem Pixel
- Drücken daneben: Drehen um die Modellmitte wie bisher
- Mausrad: der Punkt unter der Maus bleibt stehen

Aufruf: python tests/test_drehpunkt.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, rohr3d, schneidweg as sw  # noqa: E402

QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
EING = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100)])
ansicht3d.renderer_setzen("Software")


def maus(art, x, y, knopf=Qt.LeftButton):
    return QMouseEvent(art, QPointF(x, y), QPointF(x, y), knopf, knopf if art != QEvent.MouseButtonRelease
                       else Qt.NoButton, Qt.NoModifier)


def ansicht(perspektive):
    a = ansicht3d.Ansicht3D()
    a.resize(900, 420)
    a.setzen(rohr3d.netz(EING, QR, 500))
    a.perspektive_setzen(perspektive, merken=False)
    return a


for persp in (False, True):
    a = ansicht(persp)
    # Punkt auf dem Modell nahe dem rechten Ende suchen
    x0, y0 = next((x, 210.0) for x in range(800, 450, -10) if a.punkt_unter(x, 210.0) is not None)
    punkt = a.punkt_unter(x0, y0)
    px, py, _ = a.bildpunkt()(punkt)
    assert math.hypot(px - x0, py - y0) < 0.5, "Punkt unter der Maus liegt am Pixel"
    a.mousePressEvent(maus(QEvent.MouseButtonPress, x0, y0))
    assert a._drehpunkt is not None
    for n in range(1, 6):
        a.mouseMoveEvent(maus(QEvent.MouseMove, x0 + 25 * n, y0 + 9 * n))
        px, py, _ = a.bildpunkt(a.modell.grob())(punkt)
        assert math.hypot(px - x0, py - y0) < 0.5, (persp, n, px, py, x0, y0)
    assert not a.grab().isNull()                        # Drehpunkt-Markierung zeichnen
    a.mouseReleaseEvent(maus(QEvent.MouseButtonRelease, x0 + 125, y0 + 45))
    assert a._drehpunkt is None
    print("OK     Drehpunkt unter der Maus bleibt stehen", "(perspektivisch)" if persp else "(orthogonal)")

# große Netze: beim Drehen grobe Stufe, nach dem Loslassen das volle Modell mit eigenem Maßstab -> Punkt bleibt
alt = ansicht3d.GROB_DREIECKE
a = ansicht(False)
ansicht3d.GROB_DREIECKE = len(a.modell.dreiecke) // 4
assert a.modell.grob() is not a.modell
x0, y0 = next((x, 210.0) for x in range(800, 450, -10) if a.punkt_unter(x, 210.0) is not None)
punkt = a.punkt_unter(x0, y0)
a.mousePressEvent(maus(QEvent.MouseButtonPress, x0, y0))
a.mouseMoveEvent(maus(QEvent.MouseMove, x0 + 80, y0 + 30))
a.mouseReleaseEvent(maus(QEvent.MouseButtonRelease, x0 + 80, y0 + 30))
px, py, _ = a.bildpunkt()(punkt)
assert math.hypot(px - x0, py - y0) < 0.5, (px, py, x0, y0)
ansicht3d.GROB_DREIECKE = alt
print("OK     nach dem Loslassen (volles Modell) bleibt der Drehpunkt an seinem Pixel")

# daneben: um die Modellmitte (Versatz bleibt)
a = ansicht(False)
assert a.punkt_unter(5, 5) is None
a.mousePressEvent(maus(QEvent.MouseButtonPress, 5, 5))
a.mouseMoveEvent(maus(QEvent.MouseMove, 60, 30))
assert a._drehpunkt is None and a.versatz == (0.0, 0.0) and a.gier != ansicht3d.Ansicht3D.GRUND[0]
a.mouseReleaseEvent(maus(QEvent.MouseButtonRelease, 60, 30))
print("OK     daneben gedrückt: Drehen um die Modellmitte")

# Zoom zur Mausposition
for persp in (False, True):
    a = ansicht(persp)
    x0, y0 = next((x, 210.0) for x in range(800, 450, -10) if a.punkt_unter(x, 210.0) is not None)
    punkt = a.punkt_unter(x0, y0)
    for stufe in (240, 240, -120, 360):
        a.wheelEvent(QWheelEvent(QPointF(x0, y0), QPointF(x0, y0), QPoint(), QPoint(0, stufe), Qt.NoButton,
                                 Qt.NoModifier, Qt.NoScrollPhase, False))
        px, py, _ = a.bildpunkt()(punkt)
        assert math.hypot(px - x0, py - y0) < 0.5, (persp, a.zoom, px, py)
    assert a.zoom > 2
    print("OK     Mausrad zoomt zur Mausposition", "(perspektivisch)" if persp else "(orthogonal)")
print("Alle Tests Drehpunkt bestanden.")
