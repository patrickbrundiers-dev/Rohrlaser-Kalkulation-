"""Hinweis in leeren Tabellen (Prüfung 29.10.2026, O6): Statt nur Spaltenköpfen steht mittig ein grauer Satz, z. B.
„Noch keine beauftragten Angebote“. Der Hinweis wird nur gezeichnet, die Tabelle selbst bleibt unverändert."""
from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QPainter


class _Zeichner(QObject):
    def __init__(self, tabelle, text):
        super().__init__(tabelle)
        self.tabelle, self.text = tabelle, text
        tabelle.viewport().installEventFilter(self)

    def eventFilter(self, obj, ereignis):
        if ereignis.type() == QEvent.Paint and self.text and self.tabelle.model().rowCount() == 0:
            p = QPainter(obj)
            p.setPen(obj.palette().placeholderText().color())
            p.drawText(QRect(16, 0, obj.width() - 32, min(obj.height(), 120)), Qt.AlignCenter | Qt.TextWordWrap,
                       self.text)
            p.end()
            return True
        return False


def setzen(tabelle, text):
    """Hinweistext für die leere Tabelle (QTableWidget/QTableView/QTreeView) setzen oder ändern."""
    z = tabelle.findChild(_Zeichner)
    if z is None:
        _Zeichner(tabelle, text)
    else:
        z.text = text
        tabelle.viewport().update()


def text(tabelle):
    z = tabelle.findChild(_Zeichner)
    return z.text if z is not None else ""
