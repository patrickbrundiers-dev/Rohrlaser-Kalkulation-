"""Ansichtswürfel (Plan 3D-Editor A3, wie in CAD/CAM-Programmen): kleiner Würfel in der Ecke der 3D-Ansicht, der
sich mit dem Modell dreht. Klick auf eine Fläche, Kante oder Ecke = Blick genau darauf; der Knopf ⌂ darüber = schräge
Ausgangsansicht.

Bezug wie in der Skizze: Rohrachse z (Ende A bei z = 0, Ende B hinten), oben = +y, vorne (90°, von Ende A gesehen
rechts) = −x. Die Blickrichtung (gier, nick) rechnet blick_auf() aus der Flächennormale so, dass ansicht3d._drehung die
Normale genau zum Betrachter dreht.
"""
import itertools
import math

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from . import stil
from .ansicht3d import NICK_MAX, _drehung, blick_auf  # noqa: F401 (blick_auf für Aufrufer)

GROESSE = 96
# Flächen: (Name, Normale im Modell)
FLAECHEN = (("A", (0, 0, -1)), ("B", (0, 0, 1)), ("oben", (0, 1, 0)), ("unten", (0, -1, 0)),
            ("vorne", (-1, 0, 0)), ("hinten", (1, 0, 0)))


def flaechen_bild(gier, nick, groesse=GROESSE):
    """Sichtbare Flächen als [(Name, Normale, [4 Bildpunkte], Tiefe)], hinten zuerst."""
    m = _drehung(gier, nick)
    s, mitte = groesse * 0.28, groesse / 2

    def bild(v):
        x, y, z = v
        return (mitte + (m[0][0] * x + m[0][1] * y + m[0][2] * z) * s,
                mitte - (m[1][0] * x + m[1][1] * y + m[1][2] * z) * s,
                m[2][0] * x + m[2][1] * y + m[2][2] * z)
    out = []
    for name, n in FLAECHEN:
        tiefe = m[2][0] * n[0] + m[2][1] * n[1] + m[2][2] * n[2]
        if tiefe <= 1e-3:
            continue
        achse = next(i for i in range(3) if n[i])
        andere = [i for i in range(3) if i != achse]
        ecken = []
        for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p = [0, 0, 0]
            p[achse], p[andere[0]], p[andere[1]] = n[achse], u, v
            ecken.append(bild(p))
        out.append((name, n, [(x, y) for x, y, _ in ecken], tiefe))
    out.sort(key=lambda f: f[3])
    return out, bild


def treffer(gier, nick, x, y, groesse=GROESSE):
    """Normale (Fläche, Kante oder Ecke) unter dem Punkt (x, y) oder None. Ecken und Kanten fangen 7 px."""
    flaechen, bild = flaechen_bild(gier, nick, groesse)
    for sx, sy, sz in itertools.product((-1, 1), repeat=3):
        px, py, t = bild((sx, sy, sz))
        if t > 0 and math.hypot(px - x, py - y) <= 7:
            return (sx, sy, sz)
    for (a, b) in itertools.combinations(list(itertools.product((-1, 1), repeat=3)), 2):
        if sum(1 for i in range(3) if a[i] != b[i]) != 1:
            continue
        pa, pb = bild(a), bild(b)
        if pa[2] + pb[2] <= 0:
            continue
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        lg = dx * dx + dy * dy
        t = 0.0 if lg < 1e-9 else max(0.0, min(1.0, ((x - pa[0]) * dx + (y - pa[1]) * dy) / lg))
        if 0.15 < t < 0.85 and math.hypot(pa[0] + t * dx - x, pa[1] + t * dy - y) <= 5:
            return tuple(a[i] if a[i] == b[i] else 0 for i in range(3))
    for name, n, ecken, _ in reversed(flaechen):
        if QPolygonF([QPointF(*e) for e in ecken]).containsPoint(QPointF(x, y), Qt.OddEvenFill):
            return n
    return None


class Ansichtswuerfel(QWidget):
    """Würfel als Kind der 3D-Ansicht (oben rechts). Signal blick(gier, nick); Ausgangsansicht über ausgang."""
    blick = Signal(float, float)
    ausgang = Signal()

    def __init__(self, ansicht):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.setFixedSize(GROESSE, GROESSE + 18)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Klick auf Fläche, Kante oder Ecke: Blick darauf · ⌂ Ausgangsansicht")
        self._ueber = None
        self.blick.connect(lambda g, n: ansicht.ansicht(g, n))
        self.ausgang.connect(ansicht.zuruecksetzen)
        if hasattr(ansicht, "gedreht"):
            ansicht.gedreht.connect(self.update)

    def anordnen(self):
        self.move(self.ansicht.width() - self.width() - 6, 6)
        self.raise_()

    def _lage(self):
        return getattr(self.ansicht, "gier", 0.0), getattr(self.ansicht, "nick", 0.0)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        gier, nick = self._lage()
        schrift = QFont(self.font())
        schrift.setPointSizeF(7.5)
        schrift.setBold(True)
        p.setFont(schrift)
        p.setPen(QPen(stil.farbe(stil.TEXT_GRAU)))
        p.drawText(QRectF(0, 0, GROESSE, 16), Qt.AlignRight | Qt.AlignVCenter, "⌂ ")
        p.translate(0, 18)
        flaechen, _ = flaechen_bild(gier, nick)
        for name, n, ecken, tiefe in flaechen:
            hell = 0.55 + 0.45 * tiefe
            farbe = QColor(stil.farbe("#DDEBF7"))
            if self._ueber == n:
                farbe = QColor(stil.farbe("#9CC3E6"))
            farbe = farbe.darker(int(100 + (1 - hell) * 40))
            p.setBrush(farbe)
            p.setPen(QPen(stil.farbe(stil.AKZENT), 1))
            p.drawPolygon(QPolygonF([QPointF(*e) for e in ecken]))
            if tiefe > 0.35:
                mx = sum(e[0] for e in ecken) / 4
                my = sum(e[1] for e in ecken) / 4
                p.setPen(QPen(stil.farbe(stil.AKZENT_DUNKEL)))
                p.drawText(QRectF(mx - 22, my - 8, 44, 16), Qt.AlignCenter, name)
        p.end()

    def _wuerfel_punkt(self, e):
        return e.position().x(), e.position().y() - 18

    def mouseMoveEvent(self, e):
        x, y = self._wuerfel_punkt(e)
        n = treffer(*self._lage(), x, y) if y >= 0 else None
        if n != self._ueber:
            self._ueber = n
            self.update()

    def leaveEvent(self, _):
        self._ueber = None
        self.update()

    def mousePressEvent(self, e):
        x, y = self._wuerfel_punkt(e)
        if y < 0:
            self.ausgang.emit()
            return
        n = treffer(*self._lage(), x, y)
        if n is not None:
            self.blick.emit(*blick_auf(n))


class _Groesse(QObject):
    """Würfel bei jeder Größenänderung der 3D-Ansicht in die Ecke setzen."""

    def __init__(self, wuerfel):
        super().__init__(wuerfel)
        self.wuerfel = wuerfel

    def eventFilter(self, obj, ereignis):
        if ereignis.type() in (QEvent.Resize, QEvent.Show):
            self.wuerfel.anordnen()
        return False


def an_ecke(wuerfel):
    """Würfel oben rechts in seiner Ansicht halten."""
    wuerfel.ansicht.installEventFilter(_Groesse(wuerfel))
    wuerfel.anordnen()
