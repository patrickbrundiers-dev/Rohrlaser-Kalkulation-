"""Ansichtsbereich des Teile-Editors (Plan 3D-Editor A2/A3): 3D-Modell und Skizze bzw. Abwicklung in der Mitte,
wahlweise nur 3D, nur Skizze oder beides untereinander (das Rohr ist lang, untereinander bleibt es breit). Die
Auswahl ist in beiden gleich (der Teile-Editor markiert in beiden). Im 3D oben rechts der Ansichtswürfel.

Ersetzt die Reiter Skizze/3D des Schneidweg-Rechners und die gestapelten Bilder des Blech-Editors.
"""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from .ansichtswuerfel import Ansichtswuerfel

D3, SKIZZE, BEIDES = "3D", "Skizze", "Beides"
MODI = (D3, SKIZZE, BEIDES)


class _Groesse(QObject):
    """Würfel bei jeder Größenänderung der 3D-Ansicht in die Ecke setzen."""

    def __init__(self, wuerfel):
        super().__init__(wuerfel)
        self.wuerfel = wuerfel

    def eventFilter(self, obj, ereignis):
        if ereignis.type() in (QEvent.Resize, QEvent.Show):
            self.wuerfel.anordnen()
        return False


class Ansichtsbereich(QWidget):
    """skizze: Skizzen-Widget (Rohr: Skizze, Blech: BlechSkizze); ansicht3d: ansicht3d.Ansicht3DMitKnoepfen (die
    Knöpfe für feste Blickrichtungen übernimmt das Menüband, die Vorschau-Knöpfe für Anbauteile bleiben)."""

    def __init__(self, skizze, ansicht3d, modus=BEIDES, parent=None):
        super().__init__(parent)
        self.skizze, self.ansicht3d = skizze, ansicht3d
        for b in ansicht3d.knoepfe.findChildren(QWidget):
            if b.parent() is ansicht3d.knoepfe and b is not ansicht3d.modi:
                b.hide()
        ansicht3d.ansicht.setMinimumSize(240, 140)
        skizze.setMinimumHeight(120)
        self.teiler = QSplitter(Qt.Vertical)
        self.teiler.setChildrenCollapsible(False)
        self.teiler.addWidget(ansicht3d)
        self.teiler.addWidget(skizze)
        self.teiler.setStretchFactor(0, 3)
        self.teiler.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.teiler)
        self.wuerfel = Ansichtswuerfel(ansicht3d.ansicht)
        ansicht3d.ansicht.installEventFilter(_Groesse(self.wuerfel))
        self.modus = None
        self.modus_setzen(modus)

    def modus_setzen(self, modus):
        if modus not in MODI:
            modus = BEIDES
        self.modus = modus
        self.ansicht3d.setVisible(modus != SKIZZE)
        self.skizze.setVisible(modus != D3)
        self.wuerfel.anordnen()

    # Verträglich mit dem früheren QTabWidget (Reiter Skizze/3D)
    def currentWidget(self):
        return self.skizze if self.modus == SKIZZE else self.ansicht3d

    def setCurrentWidget(self, w):
        if w is self.ansicht3d and self.modus == SKIZZE:
            self.modus_setzen(D3)
        elif w is self.skizze and self.modus == D3:
            self.modus_setzen(SKIZZE)
