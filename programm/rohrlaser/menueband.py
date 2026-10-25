"""Menüband (Plan 3D-Editor A1/F3, Vorbild AlmaCAM Tube): Reiter oben, darunter Gruppen mit großen Symbol-Knöpfen
und kleinem Gruppentitel. Doppelklick auf einen Reiter klappt das Band ein (nur die Reiter bleiben sichtbar), ein
Klick auf einen Reiter klappt es wieder auf – wie in Office.

Aufbau:
    band = Menueband()
    seite = band.reiter("Konstruktion")
    g = seite.gruppe("Konturen")
    g.knopf("Bohrung", "bohrung", slot, tipp="…")              # großer Knopf: Symbol über Text
    g.knopf("Mehr", "mehr", menue=QMenu(...), gross=False)      # kleiner Knopf mit Menü

Symbole: Name aus symbole.PFADE (die Editor-Symbole unten werden dort eingetragen) oder ein QIcon.
"""
from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QStackedWidget, QTabBar, QToolButton,
                               QVBoxLayout, QWidget)

from . import stil, symbole

GROSS, KLEIN = 26, 16
_CACHE = {}
# Editor-Symbole (Raster 24 × 24 wie symbole.PFADE)
EDITOR_PFADE = {
    "rueckgaengig": "<path d='M9 14L4 9l5-5'/><path d='M4 9h10a6 6 0 0 1 0 12h-3'/>",
    "wiederholen": "<path d='M15 14l5-5-5-5'/><path d='M20 9H10a6 6 0 0 0 0 12h3'/>",
    "bohrung": "<circle cx='12' cy='12' r='6'/><path d='M12 3v3M12 18v3M3 12h3M18 12h3'/>",
    "langloch": "<rect x='3' y='8' width='18' height='8' rx='4'/>",
    "rechteck": "<rect x='4' y='6' width='16' height='12' rx='2'/>",
    "ausklinkung": "<path d='M3 6h10v12H3'/><path d='M13 6v12'/><path d='M17 4v16'/>",
    "polygon": "<path d='M5 18l2-11 9-3 4 9-7 6z'/>",
    "sonderkontur": "<path d='M5 15c-2-6 4-11 9-8s6 9 1 11-8 2-10-3z'/>",
    "gravur": "<path d='M3 15l3-6 3 6 3-6 3 6 3-6 3 6'/>",
    "v_ausschnitt": "<path d='M4 4l8 14 8-14'/><path d='M3 20h18'/>",
    "endschnitt": "<path d='M4 8h10l4 8H4z'/><path d='M18 4l-4 16'/>",
    "gegenrohr": "<rect x='3' y='9' width='12' height='6' rx='1'/><circle cx='18' cy='12' r='4'/>",
    "lochfeld": "<circle cx='6' cy='7' r='1.5'/><circle cx='12' cy='7' r='1.5'/><circle cx='18' cy='7' r='1.5'/>"
                "<circle cx='9' cy='13' r='1.5'/><circle cx='15' cy='13' r='1.5'/><circle cx='6' cy='19' r='1.5'/>"
                "<circle cx='12' cy='19' r='1.5'/><circle cx='18' cy='19' r='1.5'/>",
    "text": "<path d='M5 6V4h14v2M12 4v16M9 20h6'/>",
    "fase": "<path d='M4 20V10l6-6h10'/>",
    "muster": "<rect x='3' y='9' width='5' height='6' rx='1'/><rect x='10' y='9' width='5' height='6' rx='1'/>"
              "<rect x='17' y='9' width='4' height='6' rx='1'/>",
    "spiegeln": "<path d='M12 3v18'/><path d='M9 7L4 12l5 5z'/><path d='M15 7l5 5-5 5z'/>",
    "duplizieren": "<rect x='8' y='8' width='12' height='12' rx='2'/><path d='M4 16V5a1 1 0 0 1 1-1h11'/>",
    "messen": "<path d='M3 17L17 3l4 4L7 21z'/><path d='M7 13l2 2M10 10l2 2M13 7l2 2'/>",
    "schnitt": "<path d='M4 4l16 16'/><rect x='4' y='8' width='12' height='12' rx='1' stroke-dasharray='2 2'/>",
    "abwicklung": "<path d='M3 6h18v12H3z'/><path d='M9 6v12M15 6v12'/>",
    "beides": "<rect x='3' y='5' width='8' height='14' rx='1'/><rect x='13' y='5' width='8' height='14' rx='1'/>",
    "wuerfel": "<path d='M12 3l8 4.5v9L12 21l-8-4.5v-9z'/><path d='M12 12l8-4.5M12 12L4 7.5M12 12v9'/>",
    "roentgen": "<path d='M12 3l8 4.5v9L12 21l-8-4.5v-9z' stroke-dasharray='3 2'/>",
    "vorlage": "<path d='M5 4h10l4 4v12H5z'/><path d='M9 12h6M9 16h4'/>",
    "dxf": "<path d='M14 3H6v18h12V7z'/><path d='M8 15l3-4 2 2 3-4'/>",
    "mehr": "<circle cx='5' cy='12' r='1'/><circle cx='12' cy='12' r='1'/><circle cx='19' cy='12' r='1'/>",
}
symbole.PFADE.update({k: v for k, v in EDITOR_PFADE.items() if k not in symbole.PFADE})


def _icon(sym, groesse=GROSS):
    """QIcon eines Symbols, in der Knopfgröße gerendert (symbole.symbol ist für 16 px gedacht)."""
    if isinstance(sym, QIcon):
        return sym
    if not sym or sym not in symbole.PFADE:
        return QIcon()
    schl = (sym, groesse, stil.umsetzen(stil.TEXT))
    if schl not in _CACHE:
        try:
            from PySide6.QtSvg import QSvgRenderer
        except ImportError:
            return QIcon()
        icon = QIcon()
        renderer = QSvgRenderer(QByteArray(symbole.svg(sym, schl[2]).encode()))
        for faktor in (1, 2):
            bild = QPixmap(groesse * faktor, groesse * faktor)
            bild.fill(Qt.transparent)
            p = QPainter(bild)
            renderer.render(p, QRectF(0, 0, bild.width(), bild.height()))
            p.end()
            bild.setDevicePixelRatio(faktor)
            icon.addPixmap(bild)
        _CACHE[schl] = icon
    return _CACHE[schl]


class Gruppe(QFrame):
    """Gruppe im Band: Knöpfe nebeneinander (kleine Knöpfe zu dritt übereinander), Titel darunter."""

    def __init__(self, titel):
        super().__init__()
        self.setObjectName("bandgruppe")
        self.titel = titel
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 0)
        lay.setSpacing(0)
        self._raster = QGridLayout()
        self._raster.setContentsMargins(0, 0, 0, 0)
        self._raster.setHorizontalSpacing(2)
        self._raster.setVerticalSpacing(0)
        lay.addLayout(self._raster, 1)
        t = QLabel(titel)
        t.setObjectName("bandtitel")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        self._spalte, self._zeile = 0, 0
        self.knoepfe = {}

    def knopf(self, text, symbol=None, slot=None, tipp="", menue=None, gross=True, umschalter=False, taste=None):
        b = QToolButton()
        b.setText(text)
        b.setObjectName("bandknopf_gross" if gross else "bandknopf")
        b.setAutoRaise(True)
        b.setIcon(_icon(symbol, GROSS if gross else KLEIN))
        b.setIconSize(QSize(GROSS, GROSS) if gross else QSize(KLEIN, KLEIN))
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon if gross else Qt.ToolButtonTextBesideIcon)
        b.setCheckable(umschalter)
        tipp = tipp or text
        if taste:
            tipp += f" ({taste})"
        b.setToolTip(tipp)
        if menue is not None:
            b.setMenu(menue)
            b.setPopupMode(QToolButton.InstantPopup if slot is None else QToolButton.MenuButtonPopup)
        if slot is not None:
            (b.toggled if umschalter else b.clicked).connect(slot)
        if gross:
            if self._zeile:
                self._spalte, self._zeile = self._spalte + 1, 0
            self._raster.addWidget(b, 0, self._spalte, 3, 1)
            self._spalte += 1
        else:
            self._raster.addWidget(b, self._zeile, self._spalte)
            self._zeile += 1
            if self._zeile == 3:
                self._spalte, self._zeile = self._spalte + 1, 0
        self.knoepfe[text] = b
        return b

    def widget(self, w):
        """Beliebiges Widget (z. B. Auswahlfeld) als eigene Spalte."""
        if self._zeile:
            self._spalte, self._zeile = self._spalte + 1, 0
        self._raster.addWidget(w, 0, self._spalte, 3, 1, Qt.AlignVCenter)
        self._spalte += 1
        return w


class Seite(QWidget):
    def __init__(self):
        super().__init__()
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(2, 2, 2, 2)
        self._lay.setSpacing(0)
        self._lay.addStretch(1)
        self.gruppen = {}

    def gruppe(self, titel):
        g = Gruppe(titel)
        if self.gruppen:
            trenner = QFrame()
            trenner.setFrameShape(QFrame.VLine)
            trenner.setObjectName("bandtrenner")
            self._lay.insertWidget(self._lay.count() - 1, trenner)
        self._lay.insertWidget(self._lay.count() - 1, g)
        self.gruppen[titel] = g
        return g


class Menueband(QWidget):
    """Reiter + Seiten. eingeklappt_geaendert(bool) zum Merken je Benutzer."""
    eingeklappt_geaendert = Signal(bool)
    STIL = """
    QWidget#menueband { background: #FFFFFF; border-bottom: 1px solid #D5DBE3; }
    QToolButton#bandknopf_gross { padding: 2px 4px; min-width: 52px; }
    QToolButton#bandknopf { padding: 1px 4px; text-align: left; }
    QToolButton#bandknopf_gross:hover, QToolButton#bandknopf:hover { background: #EEF4FB; border-radius: 4px; }
    QToolButton#bandknopf_gross:checked, QToolButton#bandknopf:checked { background: #DDEBF7; border-radius: 4px; }
    QLabel#bandtitel { color: #5F6B7A; font-size: 8pt; }
    QFrame#bandtrenner { color: #E3E7EC; }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("menueband")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(stil.umsetzen(self.STIL))
        self.leiste = QTabBar()
        self.leiste.setDrawBase(False)
        self.leiste.setExpanding(False)
        self.stapel = QStackedWidget()
        self.seiten = {}
        self.eingeklappt = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        kopf = QHBoxLayout()           # Reiter links, rechts daneben Knöpfe, die auf jedem Reiter sichtbar sind
        kopf.setContentsMargins(0, 0, 4, 0)
        kopf.addWidget(self.leiste)
        kopf.addStretch(1)
        self._ecke = kopf
        lay.addLayout(kopf)
        lay.addWidget(self.stapel)
        self.leiste.currentChanged.connect(self._gewechselt)
        self.leiste.tabBarDoubleClicked.connect(lambda _: self.einklappen(not self.eingeklappt))
        self.leiste.tabBarClicked.connect(lambda _: self.eingeklappt and self.einklappen(False))

    def ecke(self, w):
        """Widget rechts neben den Reitern (immer sichtbar, auch eingeklappt)."""
        self._ecke.addWidget(w)
        return w

    def reiter(self, name):
        if name not in self.seiten:
            s = Seite()
            self.seiten[name] = s
            self.stapel.addWidget(s)
            self.leiste.addTab(name)
        return self.seiten[name]

    def _gewechselt(self, i):
        if 0 <= i < self.stapel.count():
            self.stapel.setCurrentIndex(i)

    def einklappen(self, an):
        an = bool(an)
        self.stapel.setVisible(not an)
        if an != self.eingeklappt:
            self.eingeklappt = an
            self.eingeklappt_geaendert.emit(an)

    def knopf(self, text):
        """Knopf mit diesem Text auf irgendeiner Seite (für Tests und Tastenkürzel) oder None."""
        for s in self.seiten.values():
            for g in s.gruppen.values():
                if text in g.knoepfe:
                    return g.knoepfe[text]
        return None
