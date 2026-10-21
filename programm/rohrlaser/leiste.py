"""Knopfleiste, die bei schmalem Fenster in zwei Zeilen umbricht.

Links stehen die Arbeitsknöpfe, rechts die Ausgabe. Reicht die Breite nicht für beide nebeneinander (z. B. 1366 px
mit Seitenrand), rückt der rechte Teil rechtsbündig in eine zweite Zeile. So bestimmt nicht die Summe aller Knöpfe
die Mindestbreite des Fensters, sondern nur der breitere der beiden Teile.
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QWidget


class UmbruchLeiste(QWidget):
    ABSTAND = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.links, self.rechts = QWidget(), QWidget()
        self.links_layout, self.rechts_layout = QHBoxLayout(self.links), QHBoxLayout(self.rechts)
        for lay in (self.links_layout, self.rechts_layout):
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
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
        self._gitter.addWidget(self.links, 0, 0, Qt.AlignLeft)
        if zweizeilig:
            self._gitter.addWidget(self.rechts, 1, 0, Qt.AlignRight)
            self._gitter.setColumnStretch(1, 0)
        else:
            self._gitter.addWidget(self.rechts, 0, 1, Qt.AlignRight)
            self._gitter.setColumnStretch(1, 1)
        self.updateGeometry()

    def minimumSizeHint(self):
        breite = max(self.links.minimumSizeHint().width(), self.rechts.minimumSizeHint().width())
        return QSize(breite, super().minimumSizeHint().height())

    def resizeEvent(self, e):
        self._anordnen(e.size().width() < self._bedarf())
        super().resizeEvent(e)

    def showEvent(self, e):
        self._anordnen(self.width() < self._bedarf())
        super().showEvent(e)
