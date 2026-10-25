"""Gemeinsame Bedienung aller 3D-Fenster (Plan 3D-Ansicht 3E-11, M1, Patrick 24.10.2026 „alle a“): Blickrichtungen
(Isometrie, sechs Seiten, Auf Auswahl, um 90° drehen), Perspektive, Darstellung und Messen sehen in jedem 3D-Fenster
gleich aus – Rohr- und Blech-Editor (Menüband, gleiches Menü „Blick“), STEP-Prüfdialog, Teilebaum, Schweißbaugruppe,
Schneidweg-Rechner (Leiste unter dem Bild, Ansicht3DMitKnoepfen).
"""
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QMenu, QPushButton, QToolButton, QWidget

from .ansicht3d import BLICKE, DARSTELLUNGEN, ISOMETRIE, MESS_ABSTAND, MESS_WINKEL

AUF_AUSWAHL = "Auf Auswahl"
PERSPEKTIVISCH = "Perspektivisch"
SCHNITTKOERPER = "Schnittkörper"
SCHNITTKOERPER_TIPP = ("Jede Kontur als halb durchsichtiger Körper, so tief wie sie schneidet (eine Wand, beide Wände, "
                       "Gravurtiefe); Maus darüber zeigt die Tiefe, Farbe je Konturart")
DREHEN = (("90° nach links drehen", "Strg+←", (-1, 0)), ("90° nach rechts drehen", "Strg+→", (1, 0)),
          ("90° nach oben kippen", "Strg+↑", (0, 1)), ("90° nach unten kippen", "Strg+↓", (0, -1)))


def blick_menue(menue, ansicht, vorher=None):
    """Menü „Blick“ füllen: Isometrie, Vorn, Hinten, Oben, Unten, Ende A, Ende B, Auf Auswahl, um 90° drehen und
    Perspektivisch (Haken). ansicht: Ansicht3D oder Funktion, die sie liefert (Teile-Editor); vorher: wird vor
    jedem Blick aufgerufen (z. B. 3D einblenden)."""
    def a3():
        a = ansicht() if callable(ansicht) else ansicht
        if a is not None and vorher is not None:
            vorher()
        return a

    def blick(name):
        a = a3()
        if a is not None:
            a.blick(name)
    for name in (ISOMETRIE,) + tuple(n for n, _ in BLICKE):
        menue.addAction(name, lambda n=name: blick(n))
    menue.addSeparator()
    x = menue.addAction(AUF_AUSWAHL, lambda: (a3() or _Leer).auf_auswahl())
    x.setToolTip("Senkrecht auf das gewählte Merkmal schauen und es groß in die Mitte holen")
    dm = menue.addMenu("Um 90° drehen")
    for text, taste, (g, n) in DREHEN:
        dm.addAction(f"{text}\t{taste}", lambda g=g, n=n: (a3() or _Leer).drehen(g, n))
    menue.addSeparator()
    p = QAction(PERSPEKTIVISCH, menue, checkable=True)
    p.setToolTip("Perspektivisch zeigt die Tiefe besser; orthogonal (ohne Haken) bleiben Maße vergleichbar")
    p.triggered.connect(lambda an: (a3() or _Leer).perspektive_setzen(an))
    menue.addAction(p)
    k = QAction(SCHNITTKOERPER, menue, checkable=True)
    k.setToolTip(SCHNITTKOERPER_TIPP)
    k.triggered.connect(lambda an: (a3() or _Leer).koerper_setzen(an))
    menue.addAction(k)

    def vor_dem_zeigen():
        a = ansicht() if callable(ansicht) else ansicht
        p.setChecked(bool(a is not None and a.perspektive))
        k.setChecked(bool(a is not None and a.koerper_an))
    menue.aboutToShow.connect(vor_dem_zeigen)
    return menue


class _Leer:
    """Ersatz, wenn (noch) keine 3D-Ansicht da ist: alles tut nichts."""
    @staticmethod
    def auf_auswahl():
        return False

    @staticmethod
    def drehen(*_):
        pass

    @staticmethod
    def perspektive_setzen(*_):
        pass

    @staticmethod
    def koerper_setzen(*_):
        pass


class Leiste3D(QWidget):
    """Leiste unter einer 3D-Ansicht: Blick (Menü), Darstellung, Perspektive, Schnittkörper, Messen, Winkel, Maße
    löschen."""

    def __init__(self, ansicht, parent=None):
        super().__init__(parent)
        self.ansicht = ansicht
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.blick_knopf = QToolButton()
        self.blick_knopf.setText("Blick")
        self.blick_knopf.setToolTip("Klick: Isometrie; Pfeil: Vorn, Hinten, Oben, Unten, Ende A, Ende B, Auf Auswahl, "
                                    "um 90° drehen (Strg + Pfeiltasten), Perspektivisch")
        self.blick_knopf.setPopupMode(QToolButton.MenuButtonPopup)
        self.blick_menue = blick_menue(QMenu(self.blick_knopf), ansicht)
        self.blick_knopf.setMenu(self.blick_menue)
        self.blick_knopf.clicked.connect(lambda: ansicht.blick(ISOMETRIE))
        lay.addWidget(self.blick_knopf)
        self.darstellung = QComboBox()
        self.darstellung.addItems(DARSTELLUNGEN)
        self.darstellung.setToolTip("Schattiert, Mit Kanten, Durchsichtig (Röntgen), Drahtgitter (nur Kanten), "
                                    "Verdeckt gestrichelt (verdeckte Kanten gestrichelt)")
        self.darstellung.currentTextChanged.connect(lambda t: ansicht.darstellung_setzen(t))
        lay.addWidget(self.darstellung)
        self.perspektive = QPushButton(PERSPEKTIVISCH)
        self.perspektive.setCheckable(True)
        self.perspektive.setToolTip(self.blick_menue.actions()[-1].toolTip())
        self.perspektive.toggled.connect(lambda an: ansicht.perspektive_setzen(an))
        lay.addWidget(self.perspektive)
        self.koerper = QPushButton(SCHNITTKOERPER)
        self.koerper.setCheckable(True)
        self.koerper.setToolTip(SCHNITTKOERPER_TIPP)
        self.koerper.toggled.connect(lambda an: ansicht.koerper_setzen(an))
        lay.addWidget(self.koerper)
        self.messen = QPushButton("Messen")
        self.messen.setCheckable(True)
        self.messen.setToolTip("Zwei Punkte anklicken: fängt Kreismitte, Kantenmitte, Ecke oder Fläche; Ergebnis mit "
                               "Kernwerten in der Mess-Tafel (kopierbar)")
        self.messen.toggled.connect(lambda an: self._messen(an, MESS_ABSTAND))
        self.winkel = QPushButton("Winkel")
        self.winkel.setCheckable(True)
        self.winkel.setToolTip("Drei Punkte anklicken, der mittlere ist der Scheitel")
        self.winkel.toggled.connect(lambda an: self._messen(an, MESS_WINKEL))
        loeschen = QPushButton("Maße löschen")
        loeschen.clicked.connect(ansicht.masse_loeschen)
        for b in (self.messen, self.winkel, loeschen):
            lay.addWidget(b)
        lay.addStretch(1)
        ansicht.messen_geaendert.connect(self.stand)
        ansicht.gedreht.connect(self.stand)
        self.stand()

    def _messen(self, an, art):
        a = self.ansicht
        if an:
            a.messen_setzen(True, art=art)
        elif a.messen and a.mess_max and a.mess_art == art:
            a.messen_setzen(False)
        self.stand()

    def stand(self):
        """Knöpfe nach der Ansicht stellen (auch wenn ein Fenster selbst umschaltet, z. B. Naht zeichnen)."""
        a = self.ansicht
        for knopf, an in ((self.messen, a.messen and a.mess_max == 2 and a.mess_art == MESS_ABSTAND),
                          (self.winkel, a.messen and a.mess_art == MESS_WINKEL),
                          (self.perspektive, a.perspektive), (self.koerper, a.koerper_an)):
            knopf.blockSignals(True)
            knopf.setChecked(bool(an))
            knopf.blockSignals(False)
        self.darstellung.blockSignals(True)
        self.darstellung.setCurrentText(a.darstellung)
        self.darstellung.blockSignals(False)
