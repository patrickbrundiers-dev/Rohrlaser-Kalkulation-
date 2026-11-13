"""Zeile, die umbricht (Plan Schweißbaugruppe Teil 2, 13.11.2026, L6): Knopfzeilen unter den Tabellen brechen in eine
zweite Zeile um, statt dem Fenster eine Mindestbreite aufzuzwingen (sonst waagerechter Rollbalken auf dem Laptop)."""
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlussLayout(QLayout):
    def __init__(self, parent=None, abstand=6):
        super().__init__(parent)
        self._dinge = []
        self._abstand = abstand
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._dinge.append(item)

    def addStretch(self, _=0):          # wie QHBoxLayout aufrufbar; eine umbrechende Zeile braucht keine Feder
        pass

    def count(self):
        return len(self._dinge)

    def itemAt(self, i):
        return self._dinge[i] if 0 <= i < len(self._dinge) else None

    def takeAt(self, i):
        return self._dinge.pop(i) if 0 <= i < len(self._dinge) else None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, breite):
        return self._legen(QRect(0, 0, breite, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._legen(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        g = QSize()
        for it in self._dinge:
            g = g.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return g + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _legen(self, rect, nur_messen):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, hoehe = r.x(), r.y(), 0
        for it in self._dinge:
            w = it.widget()
            if w is not None and w.isHidden():
                continue
            g = it.sizeHint()
            if x + g.width() > r.right() + 1 and hoehe > 0:
                x, y, hoehe = r.x(), y + hoehe + self._abstand, 0
            if not nur_messen:
                it.setGeometry(QRect(QPoint(x, y), g))
            x += g.width() + self._abstand
            hoehe = max(hoehe, g.height())
        return y + hoehe - rect.y() + m.bottom()
