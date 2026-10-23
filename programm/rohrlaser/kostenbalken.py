"""Kostenbalken (Verbesserung D2): waagerechter, gestapelter Balken mit Legende, z. B. Kosten einer Schweißbaugruppe
nach Schweißen, Arbeitsgängen, Einmalkosten und Fremdleistung. Allgemein gehalten, damit andere Ansichten ihn
wiederverwenden (z. B. Kostenwasserfall): setzen([(Bezeichnung, Betrag, Farbe oder None)]); ohne Farbe kommen die
Farben der Reihe nach aus stil.BALKEN_FARBEN. Beträge ≤ 0 erscheinen nur in der Legende."""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from .stammdaten import zahl_als_text
from .stil import BALKEN_FARBEN, LINIE, TEXT, TEXT_GRAU

BALKEN_HOEHE = 14
ZEILE = 18


def _euro(w):
    return zahl_als_text(round(w or 0.0, 2), 2) + " €"


def abschnitte(teile):
    """[(Bezeichnung, Betrag, Farbe)] mit Farbe aus BALKEN_FARBEN, wo keine angegeben ist."""
    return [(t, float(w or 0.0), f or BALKEN_FARBEN[i % len(BALKEN_FARBEN)]) for i, (t, w, *rest) in enumerate(teile)
            for f in [rest[0] if rest else None]]


class Kostenbalken(QWidget):
    """Balken über die volle Breite, darunter die Legende (Farbe, Bezeichnung, Betrag, Anteil) in Zeilen."""

    def __init__(self, titel="", parent=None):
        super().__init__(parent)
        self.titel, self.teile = titel, []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, teile, titel=None):
        self.teile = abschnitte(teile)
        if titel is not None:
            self.titel = titel
        summe = self.summe()
        self.setToolTip("\n".join(f"{t}: {_euro(w)}" + (f" ({w / summe * 100:.0f} %)" if summe > 0 else "")
                                  for t, w, _ in self.teile))
        self.updateGeometry()
        self.update()

    def summe(self):
        return sum(w for _, w, _ in self.teile if w > 0)

    def _oben(self):
        return ZEILE if self.titel else 0

    def sizeHint(self):
        return QSize(260, self._oben() + BALKEN_HOEHE + 6 + ZEILE * len(self.teile))

    def minimumSizeHint(self):
        return QSize(120, self.sizeHint().height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        breite, y, summe = self.width(), self._oben(), self.summe()
        if self.titel:
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(0, 0, breite, ZEILE), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(self.font()).elidedText(f"{self.titel}  {_euro(summe)}", Qt.ElideRight, breite))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(LINIE))
        p.drawRoundedRect(QRectF(0, y, breite, BALKEN_HOEHE), 3, 3)
        x = 0.0
        for _, w, farbe in self.teile:
            if w <= 0 or summe <= 0:
                continue
            b = breite * w / summe
            p.setBrush(QColor(farbe))
            p.drawRect(QRectF(x, y, max(b, 1.0), BALKEN_HOEHE))
            x += b
        y += BALKEN_HOEHE + 6
        for t, w, farbe in self.teile:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(farbe))
            p.drawRect(QRectF(0, y + 4, 10, 10))
            p.setPen(QColor(TEXT if w > 0 else TEXT_GRAU))
            anteil = f"  {w / summe * 100:.0f} %" if summe > 0 and w > 0 else ""
            p.drawText(QRectF(16, y, breite - 16, ZEILE), Qt.AlignLeft | Qt.AlignVCenter, t)
            p.drawText(QRectF(16, y, breite - 16, ZEILE), Qt.AlignRight | Qt.AlignVCenter, _euro(w) + anteil)
            y += ZEILE
