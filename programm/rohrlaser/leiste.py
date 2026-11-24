"""Knopfleiste, die bei schmalem Fenster in zwei Zeilen umbricht.

Links stehen die Arbeitsknöpfe, rechts die Ausgabe. Reicht die Breite nicht für beide nebeneinander (z. B. 1366 px
mit Seitenrand), rückt der rechte Teil rechtsbündig in eine zweite Zeile. So bestimmt nicht die Summe aller Knöpfe
die Mindestbreite des Fensters, sondern nur der breitere der beiden Teile. Ist sogar der linke Teil allein zu breit
(schmales Fenster mit Seitenleiste, größere Schrift), rücken seine letzten Knöpfe vorn in die zweite Zeile, statt
abgeschnitten zu werden (UI-Modernisierung U2).
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QWidget

from .fluss import FlussLayout


class UmbruchLeiste(QWidget):
    ABSTAND = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.links, self.rechts = QWidget(), QWidget()
        self.links_layout, self.rechts_layout = QHBoxLayout(self.links), QHBoxLayout(self.rechts)
        for lay in (self.links_layout, self.rechts_layout):
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
        # zweite Zeile links: Knöpfe, die oben nicht mehr passen; bricht selbst weiter um (20.11.2026: sonst zwang die
        # volle linke Knopfreihe dem maximierten Fenster ihre Breite auf)
        self.ueberlauf = QWidget()
        self.ueberlauf_layout = FlussLayout(self.ueberlauf)
        self._verschoben = []
        self.unten = QWidget()
        self._unten_layout = QHBoxLayout(self.unten)
        self._unten_layout.setContentsMargins(0, 0, 0, 0)
        self._unten_layout.setSpacing(self.ABSTAND)
        self._unten_layout.addWidget(self.ueberlauf, 1)
        self._gitter = QGridLayout(self)
        self._gitter.setContentsMargins(0, 0, 0, 0)
        self._gitter.setHorizontalSpacing(self.ABSTAND)
        self._gitter.setVerticalSpacing(4)
        self.zweizeilig = None
        self._anordnen(False)

    def _bedarf(self):
        return self.links.sizeHint().width() + self.ABSTAND + self.rechts.sizeHint().width()

    def _anordnen(self, zweizeilig):
        if zweizeilig == self.zweizeilig:
            return
        self.zweizeilig = zweizeilig
        self._gitter.removeWidget(self.links)
        self._gitter.removeWidget(self.rechts)
        self._gitter.removeWidget(self.unten)
        self._gitter.addWidget(self.links, 0, 0, Qt.AlignLeft)
        if zweizeilig:
            self._unten_layout.addWidget(self.rechts)
            self._gitter.addWidget(self.unten, 1, 0)
            self.unten.show()
            self._gitter.setColumnStretch(1, 0)
        else:
            self._gitter.addWidget(self.rechts, 0, 1, Qt.AlignRight)
            self.unten.hide()
            self._gitter.setColumnStretch(1, 1)
        self.updateGeometry()

    def _zurueck(self):
        """Verschobene Knöpfe wieder ans Ende des linken Teils."""
        for w in self._verschoben:
            sichtbar = not w.isHidden()     # Umhängen blendet aus; ein ausgeblendeter Knopf zählt nicht zur Breite
            self.ueberlauf_layout.removeWidget(w)
            self.links_layout.addWidget(w)
            w.setVisible(sichtbar)
        self._verschoben = []
        self.links_layout.invalidate()

    def _umbrechen(self, breite):
        """Letzte Knöpfe des linken Teils in die zweite Zeile, bis der linke Teil in die Breite passt."""
        while self.links.sizeHint().width() > breite:
            i = self.links_layout.count() - 1
            while i >= 0 and self.links_layout.itemAt(i).widget() is None:
                i -= 1
            if i <= 0:
                break
            w = self.links_layout.itemAt(i).widget()
            sichtbar = not w.isHidden()
            self.links_layout.removeWidget(w)
            self.ueberlauf_layout.insertWidget(0, w)
            w.setVisible(sichtbar)
            self._verschoben.insert(0, w)
            self.links_layout.invalidate()
        self.ueberlauf.setVisible(bool(self._verschoben))

    def _einpassen(self, breite):
        self._zurueck()
        self._anordnen(breite < self._bedarf())
        if self.zweizeilig:
            self._umbrechen(breite)

    def minimumSizeHint(self):
        """Breitester Knopf links neben dem rechten Teil: mehr braucht die Leiste nicht, der Rest bricht um."""
        knoepfe = [w.minimumSizeHint().width() for w in self.links.findChildren(QWidget) + self.ueberlauf.findChildren(QWidget)
                   if w.parentWidget() in (self.links, self.ueberlauf) and not w.isHidden()]
        breite = max(knoepfe, default=0) + self.ABSTAND + self.rechts.minimumSizeHint().width()
        return QSize(breite, super().minimumSizeHint().height())

    def resizeEvent(self, e):
        self._einpassen(e.size().width())
        super().resizeEvent(e)

    def showEvent(self, e):
        self._einpassen(self.width())
        super().showEvent(e)
