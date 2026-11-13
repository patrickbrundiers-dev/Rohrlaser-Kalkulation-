"""Mehrere Werte aus einer Liste ankreuzen (Feldart „mehrfach“, z. B. Materialgruppen der Lieferanten, 13.11.2026).

Der Wert steht als Text „Stahl; Edelstahl“ in der Zelle (materialanfragen.gruppen_text). Werte, die es in der Liste
nicht mehr gibt, bleiben angekreuzt stehen, bis man sie abwählt."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from .materialanfragen import gruppen_liste, gruppen_text


class MehrfachDialog(QDialog):
    def __init__(self, parent, titel, werte, gewaehlt):
        super().__init__(parent)
        self.setWindowTitle(titel)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Zutreffendes ankreuzen:"))
        self.liste = QListWidget()
        gewaehlt = gruppen_liste(gewaehlt)
        for w in list(werte) + [g for g in gewaehlt if g not in werte]:
            it = QListWidgetItem(w)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if w in gewaehlt else Qt.Unchecked)
            self.liste.addItem(it)
        lay.addWidget(self.liste)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        lay.addWidget(k)
        self.resize(320, 360)

    def wert(self):
        return gruppen_text(self.liste.item(i).text() for i in range(self.liste.count())
                            if self.liste.item(i).checkState() == Qt.Checked)


def mehrfach_waehlen(parent, titel, werte, gewaehlt, dialog=None):
    """Auswahl als Text oder None (abgebrochen). dialog(d) bedient den Dialog statt exec (Tests)."""
    d = MehrfachDialog(parent, titel, werte, gewaehlt)
    ok = dialog(d) if dialog else d.exec()
    return d.wert() if ok else None
