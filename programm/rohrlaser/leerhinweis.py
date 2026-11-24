"""Hinweis in leeren Tabellen (Prüfung 29.10.2026, O6): Statt nur Spaltenköpfen steht mittig ein grauer Satz, z. B.
„Noch keine beauftragten Angebote“. Der Hinweis wird nur gezeichnet, die Tabelle selbst bleibt unverändert.

Generalüberholung 24.11.2026 (Phase 4, „hochwertige Tabellen“): bisher hatten nur Seiten mit setzen() einen Hinweis,
alle anderen leeren Tabellen (Anfragen, Auswertung, Kunden-Unterlisten …) zeigten eine weiße Fläche. Jetzt bekommt
jede Tabelle/Baumansicht beim ersten Polieren (Ereignisfilter in stil.py) den allgemeinen Hinweis STANDARD; setzen()
ersetzt ihn wie bisher durch einen eigenen Text, setzen(tabelle, "") schaltet ihn ab."""
from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QPainter

STANDARD = "Keine Einträge"


class _Zeichner(QObject):
    def __init__(self, tabelle, text):
        super().__init__(tabelle)
        self.tabelle, self.text = tabelle, text
        tabelle.viewport().installEventFilter(self)

    def eventFilter(self, obj, ereignis):
        if (ereignis.type() == QEvent.Paint and self.text and self.tabelle.model() is not None
                and self.tabelle.model().rowCount() == 0):
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


def automatisch(ansicht):
    """Allgemeinen Hinweis an eine Tabelle/Baumansicht hängen, wenn sie noch keinen hat (stil.py beim Polieren).
    Auswahllisten (Popup-Fenster) bleiben ohne. Poliert wird oft schon vor dem Einsetzen ins Layout (Eltern noch None),
    darum zählt nur der Fenstertyp."""
    from PySide6.QtWidgets import QTableView, QTreeView
    if not isinstance(ansicht, (QTableView, QTreeView)) or ansicht.findChild(_Zeichner) is not None:
        return
    if ansicht.window().windowType() == Qt.Popup:
        return
    _Zeichner(ansicht, STANDARD)
