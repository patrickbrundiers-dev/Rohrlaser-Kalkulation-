"""Mausrad ändert keine Werte: Über Zahlenfeldern, Datumsfeldern, Auswahllisten und Schiebereglern rollt das Rad
immer die Seite, Tabelle oder Liste darunter, statt den Wert zu verstellen (Patrick 22.10.2026: "Beim Scrollen
nicht versehentlich Werte ändern"). Gilt für alle Fenster und Dialoge, auch für Editoren in Tabellenzellen.
Zoom in Skizzen und 3D-Ansicht und Bildlaufleisten bleiben unverändert; aufgeklappte Auswahllisten rollen wie gewohnt.
"""
from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox, QScrollBar

GESPERRT = (QAbstractSpinBox, QComboBox, QAbstractSlider)


def gesperrt(obj):
    return isinstance(obj, GESPERRT) and not isinstance(obj, QScrollBar)


class Mausrad(QObject):
    def eventFilter(self, obj, ereignis):
        art = ereignis.type()
        if art == QEvent.Wheel and gesperrt(obj):
            weiterreichen(obj, ereignis)
            return True                             # das Feld selbst bekommt das Rad nie
        if art == QEvent.Polish and gesperrt(obj) and obj.focusPolicy() == Qt.WheelFocus:
            obj.setFocusPolicy(Qt.StrongFocus)      # das Rad holt auch keinen Eingabefokus mehr
        return False


def weiterreichen(feld, ereignis):
    """Rad an die Eltern weiterreichen, bis eines es verarbeitet (Seite, Tabelle, Liste) – wie Qt es mit einem
    ignorierten Rad täte. Von Hand, weil Qt nicht vom Benutzer stammende Ereignisse nicht weiterreicht."""
    w = feld
    pos = ereignis.position()
    while not w.isWindow() and w.parentWidget() is not None:
        pos = QPointF(w.mapToParent(pos))
        w = w.parentWidget()
        if gesperrt(w):
            continue
        neu = QWheelEvent(pos, ereignis.globalPosition(), ereignis.pixelDelta(), ereignis.angleDelta(),
                          ereignis.buttons(), ereignis.modifiers(), ereignis.phase(), ereignis.inverted(),
                          ereignis.source())
        neu.setAccepted(False)
        QApplication.sendEvent(w, neu)
        if neu.isAccepted():
            break
    ereignis.accept()


def einrichten(app):
    """Einmal nach dem Anlegen der QApplication aufrufen."""
    app._mausrad = Mausrad(app)
    app.installEventFilter(app._mausrad)
    return app._mausrad
