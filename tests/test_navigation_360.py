"""Freie 360°-Drehung in allen 3D-Fenstern (Patrick 19.11.2026, navigation3d).

R1 Mehrere volle Umdrehungen waagrecht und senkrecht (langsam und schnell): kein Anschlag, kein Rücksprung,
   zurück genau in der Ausgangslage, Matrix bleibt orthonormal
R2 Matrix <-> Winkel: jede Lage (auch genau von oben/unten) wird exakt wieder dieselbe Matrix
R3 Ansicht3D: Maus senkrecht ziehen kippt über Kopf (vorher bei ±89° Schluss), Strg/Alt-Tasten, Blickachse
R4 Einstellungen: Tempo, Richtung umkehren, Drehteller, Vorgaben ohne Datenbank
R5 Exakte Winkeleingabe um Modell- und Bildschirmachsen; 360° = Ausgangslage
R6 Nur die Kamera dreht: Netz und Modellpunkte bleiben unverändert; Nachlauf nur mit Einstellung

Aufruf: python tests/test_navigation_360.py
"""
import copy
import math
import os
import random
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, ansicht3d_leiste, navigation3d as nav, rohr3d, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def gleich(m1, m2, tol=1e-9):
    return all(abs(m1[r][c] - m2[r][c]) < tol for r in range(3) for c in range(3))


def orthonormal(m, tol=1e-9):
    t = nav.mal(m, tuple(tuple(m[c][r] for c in range(3)) for r in range(3)))
    return gleich(t, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), tol)


# ------------------------------------------------------------------ R1 volle Umdrehungen
start = (-0.45, 0.45, 0.0)
m0 = nav.matrix(*start)
k = nav.DREH_GRUND
for richtung in ((1, 0), (0, 1), (1, 1)):
    for schritt in (1.0, 37.0):                     # langsam (1 px) und schnell (37 px je Ereignis)
        g, n, r = start
        px = 3 * 2 * math.pi / k                    # drei volle Umdrehungen in Pixel
        schritte = int(round(px / schritt))
        d = px / schritte
        ueber_kopf = False
        for _ in range(schritte):
            g, n, r = nav.ziehen(g, n, r, d * richtung[0], d * richtung[1])
            ueber_kopf |= nav.matrix(g, n, r)[1][1] < -0.99      # Modell-Y zeigt nach unten: über Kopf
        m = nav.matrix(g, n, r)
        if richtung == (1, 1):
            assert orthonormal(m, 1e-7), m
        else:
            assert gleich(m, m0, 1e-6) and orthonormal(m, 1e-9), (richtung, schritt, m)
        if richtung == (0, 1):
            assert ueber_kopf, "senkrecht nicht über Kopf gedreht"
ok("R1 3 volle Umdrehungen waagrecht/senkrecht, langsam und schnell: über Kopf, zurück genau in die Ausgangslage")

# ------------------------------------------------------------------ R2 Matrix <-> Winkel
random.seed(7)
faelle = [(random.uniform(-4, 4), random.uniform(-4, 4), random.uniform(-4, 4)) for _ in range(300)]
faelle += [(0.3, math.pi / 2, 0.2), (1.1, -math.pi / 2, -0.4), (0, math.pi, 0), (2.0, -math.pi, 1.0)]
for w in faelle:
    m = nav.matrix(*w)
    assert gleich(nav.matrix(*nav.zerlegen(m)), m, 1e-9), w
ok("R2 300 zufällige Lagen und genau von oben/unten: Winkel zerlegt ergeben exakt dieselbe Matrix")

# ------------------------------------------------------------------ R3 Ansicht3D mit Maus und Tasten
ansicht3d.renderer_setzen("Software")
QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
netz = rohr3d.netz(dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100)]), QR, 500)
roh = copy.deepcopy(netz)
a = ansicht3d.Ansicht3D()
a.resize(600, 400)
a.setzen(netz)
a.show()
app.processEvents()
punkte = list(a.modell.p) if hasattr(a.modell, "p") else None


def maus(art, x, y, knopf=Qt.LeftButton):
    return QMouseEvent(art, QPointF(x, y), QPointF(x, y), knopf, knopf if art != QEvent.MouseButtonRelease
                       else Qt.NoButton, Qt.NoModifier)


a.blick("Vorn")
a.mousePressEvent(maus(QEvent.MouseButtonPress, 5, 5))      # neben dem Modell: Drehen um die Mitte
y = 5
gesehen = []
for _ in range(262):                                           # 262 × 1 px × 0,012 ≈ 180°
    y += 1
    a.mouseMoveEvent(maus(QEvent.MouseMove, 5, y))
    gesehen.append(ansicht3d._drehung(a.gier, a.nick, a.roll)[1][1])
a.mouseReleaseEvent(maus(QEvent.MouseButtonRelease, 5, y))
assert min(gesehen) < -0.99, min(gesehen)                     # über Kopf: Modell-Y zeigt nach unten
assert all(abs(x2 - x1) < 0.05 for x1, x2 in zip(gesehen, gesehen[1:])), "Sprung beim Kippen"
a.blick("Vorn")
for _ in range(4):
    a.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.ControlModifier))
assert gleich(ansicht3d._drehung(a.gier, a.nick, a.roll), ansicht3d._drehung(*ansicht3d.blick_auf((-1, 0, 0))), 1e-9)
for _ in range(24):                                             # 24 × 15° um die Blickachse
    a.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_PageUp, Qt.AltModifier))
assert gleich(ansicht3d._drehung(a.gier, a.nick, a.roll), ansicht3d._drehung(*ansicht3d.blick_auf((-1, 0, 0))), 1e-9)
a.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_PageUp, Qt.ControlModifier))
assert abs(abs(a.roll) - math.pi / 2) < 1e-9, a.roll
a.blick(ansicht3d.ISOMETRIE)
assert a.roll == 0 and (a.gier, a.nick) == ansicht3d.Ansicht3D.GRUND
ok("R3 Maus: 180° senkrecht über Kopf ohne Sprung; Strg+↑ ×4 = 360°, Alt+Bild↑ ×24 = 360°, Strg+Bild↑ = Blickachse")

# ------------------------------------------------------------------ R4 Einstellungen
assert nav.werte_lesen(None) == nav.VORGABEN
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
for n, v in (("nav_dreh_tempo", 2.0), ("nav_umkehren_h", "ja"), ("nav_drehart", nav.DREHTELLER),
             ("nav_zoom_tempo", 99)):
    db.einstellung_setzen(n, v)
w = nav.werte_lesen(db)
assert w["nav_dreh_tempo"] == 2.0 and w["nav_zoom_tempo"] == 5.0 and w["nav_umkehren_h"] == "ja"
g, n, r = nav.ziehen(0.0, 0.0, 0.0, 10, 0, w)
assert abs(g + 10 * 2 * k) < 1e-12 and n == 0 and r == 0                     # Drehteller, umgekehrt, doppelt
g, n, r = nav.ziehen(0.0, 1.5, 0.0, 0, 20, w)
assert abs(n - (1.5 + 20 * 2 * k)) < 1e-12                                  # Drehteller kippt ohne Grenze
from rohrlaser import teilen  # noqa: E402
assert set(nav.NAMEN) <= teilen.LOKAL                                       # nur dieser Arbeitsplatz
from rohrlaser.stammdaten import EINSTELLUNG  # noqa: E402
assert set(nav.NAMEN) <= set(EINSTELLUNG) and EINSTELLUNG["nav_drehart"].vorgabe == nav.FREI
ok("R4 Einstellungen: Tempo, Umkehren, Drehteller (kippt ohne Grenze), Grenzen 0,1–5, je Arbeitsplatz")

# ------------------------------------------------------------------ R5 exakte Winkeleingabe
a.blick("Vorn")
m_vorn = ansicht3d._drehung(a.gier, a.nick, a.roll)
for achse in "XYZxyz":
    for _ in range(4):
        assert ansicht3d_leiste.drehen_fragen(a, achse, 90)
    assert gleich(ansicht3d._drehung(a.gier, a.nick, a.roll), m_vorn, 1e-9), achse
a.drehen_um("Z", 90)                                       # um die Rohrachse: Rohrachse bleibt, wo sie ist
m = ansicht3d._drehung(a.gier, a.nick, a.roll)
assert all(abs(m[i][2] - m_vorn[i][2]) < 1e-9 for i in range(3))
a.drehen_um("Z", -90)
a.drehen_um("y", 400)
a.drehen_um("y", -40)
assert gleich(ansicht3d._drehung(a.gier, a.nick, a.roll), m_vorn, 1e-9)
ok("R5 Winkeleingabe: 4 × 90° um jede Modell- und Bildschirmachse = Ausgangslage, Z hält die Rohrachse")

# ------------------------------------------------------------------ R6 Geometrie bleibt, Nachlauf
assert netz == roh
if punkte is not None:
    assert list(a.modell.p) == punkte
assert not a._nachlauf.isActive()
db.einstellung_setzen("nav_drehart", nav.FREI)
db.einstellung_setzen("nav_traegheit", "ja")
alt_speicher = ansicht3d._speicher
ansicht3d._speicher = db
a.mousePressEvent(maus(QEvent.MouseButtonPress, 5, 5))
a.mouseMoveEvent(maus(QEvent.MouseMove, 30, 5))
a.mouseReleaseEvent(maus(QEvent.MouseButtonRelease, 30, 5))
assert a._nachlauf.isActive()
g0 = a.gier, a.nick, a.roll
a._nachlaufen()
assert (a.gier, a.nick, a.roll) != g0
a.mousePressEvent(maus(QEvent.MouseButtonPress, 30, 5))       # neuer Druck stoppt den Nachlauf
assert not a._nachlauf.isActive()
a.mouseReleaseEvent(maus(QEvent.MouseButtonRelease, 30, 5))
ansicht3d._speicher = alt_speicher
assert netz == roh
ok("R6 Netz und Modellpunkte unverändert; Nachlauf nur mit Einstellung, neuer Druck stoppt ihn")
print("Alle Prüfungen bestanden.")
