"""Seitenleiste der Hauptnavigation (UI-Modernisierung 12.11.2026, Paket U2).

Ersetzt die Zeile mit den festen Hauptreitern: links eine schmale dunkle Leiste mit Symbolen, gegliedert nach
Arbeitsbereichen (Arbeiten · Auftrag · Pflege, Einstellungen unten). Breit zeigt sie Symbol und Text, schmal nur das
Symbol mit Tooltip. Die Breite wählt man unten mit « / » oder im Menü Ansicht; „automatisch“ (Vorgabe) ist sie ab
AUTO_BREIT_AB Pixel Fensterbreite breit, darunter schmal.

Nach außen verhält sich die Leiste wie die QTabBar, die sie in hauptreiter.HauptReiter ersetzt: addTab, count,
tabText, setTabText, setTabVisible, isTabVisible, currentIndex, setCurrentIndex, tabRect, Signal currentChanged.
"""
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenuBar, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

AUTO_BREIT_AB = 1600            # Fensterbreite in px, ab der die Leiste im Modus „automatisch“ Text zeigt
BREIT, SCHMAL = 176, 48
MODI = ("automatisch", "breit", "schmal")
EINSTELLUNG = "navigation_breite"

# Arbeitsbereiche in dieser Reihenfolge; Seiten ohne Eintrag kommen unter „Pflege“, Einstellungen steht ganz unten
GRUPPEN = ("Arbeiten", "Auftrag", "Pflege")
GRUPPE = {"Start": "Arbeiten", "Anfragen": "Arbeiten", "Angebote": "Arbeiten", "Kunden": "Arbeiten",
          "Aufträge": "Auftrag", "Produktion": "Auftrag", "Versand": "Auftrag", "Fertigung": "Auftrag", "Lager": "Auftrag",
          "Zukaufartikel": "Pflege", "Frachtkosten": "Pflege", "Einstellungen": None}
SYMBOL = {"Start": "start", "Anfragen": "mail", "Angebote": "angebote", "Kunden": "kunden", "Aufträge": "auftraege", "Produktion": "produktion", "Versand": "versand", "Fertigung": "fertigung",
          "Lager": "lager", "Zukaufartikel": "zukauf", "Frachtkosten": "fracht", "Einstellungen": "einstellungen"}
TIPP = {"Start": "Übersicht: Kennzahlen, zuletzt bearbeitete Angebote, Datensicherung",
        "Anfragen": "Kundenanfragen: Neu, In Bearbeitung, Erledigt; übernehmen, zuweisen, kalkulieren",
        "Angebote": "Angebotsliste und geöffnete Angebote",
        "Kunden": "Kundenstamm; Doppelklick zeigt die Angebote des Kunden",
        "Aufträge": "Auftragsverwaltung: alle Aufträge mit Status, Termin, Wert und Historie",
        "Produktion": "Arbeitsgänge in der Werkstatt: beginnen, Teilmengen, abschließen, Probleme melden",
        "Versand": "Beauftragte Angebote: Palettenschein, Lieferdatum, Stand",
        "Fertigung": "Freigabe und Status beauftragter Angebote",
        "Lager": "Materialbestand und Reststücke",
        "Zukaufartikel": "Zukaufartikel, Kategorien und Lieferanten",
        "Frachtkosten": "Frachtkosten nach PLZ rechnen",
        "Einstellungen": "Stammdaten, Vorgaben und Einstellungen"}
TEXT_FARBE = "#C8D2DE"          # Symbole auf der dunklen Leiste; gewählt weiß


def _symbol(name):
    """QIcon mit hellem Symbol, gewählt (checked) weiß; leer ohne Symbol oder ohne QtSvg."""
    from . import symbole
    if name not in symbole.PFADE:
        return QIcon()
    icon = QIcon()
    for farbe, zustand in ((TEXT_FARBE, QIcon.Off), (symbole.WEISS, QIcon.On)):
        quelle = symbole.symbol(name, farbe)
        for groesse in (QSize(18, 18), QSize(36, 36)):
            pix = quelle.pixmap(groesse)
            if not pix.isNull():
                icon.addPixmap(pix, QIcon.Normal, zustand)
    return icon


class Seitenleiste(QFrame):
    currentChanged = Signal(int)
    modus_geaendert = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("seitenleiste")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.knoepfe, self.texte, self.versteckt = [], [], set()
        self.gruppe_der = []            # je Knopf: Gruppenname oder None (unten)
        self._aktuell = -1
        self.modus = "automatisch"
        self.breit = True
        self._wahl = QButtonGroup(self)
        self._wahl.setExclusive(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 6)
        lay.setSpacing(1)
        self._lay = lay
        self.titel = {}
        self._ende = {}                 # Gruppe -> Index im Layout hinter ihrem letzten Knopf
        for g in GRUPPEN:
            t = QLabel(g.upper())
            t.setObjectName("navgruppe")
            lay.addWidget(t)
            self.titel[g] = t
        lay.addStretch(1)
        self.umschalter = QToolButton()
        self.umschalter.setObjectName("navumschalter")
        self.umschalter.setAutoRaise(True)
        self.umschalter.clicked.connect(self._umschalten)
        lay.addWidget(self.umschalter)
        self._breite_anwenden()

    # -------------------------------------------------- wie QTabBar
    def addTab(self, text):
        i = len(self.knoepfe)
        k = QToolButton()
        k.setObjectName("navknopf")
        k.setCheckable(True)
        k.setAutoRaise(True)
        k.setCursor(Qt.PointingHandCursor)
        k.setIcon(_symbol(SYMBOL.get(text, "")))
        k.setIconSize(QSize(18, 18))
        k.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        k.clicked.connect(lambda _=False, k=k: self._geklickt(k))
        self._wahl.addButton(k)
        self.knoepfe.append(k)
        self.texte.append(text)
        gruppe = GRUPPE.get(text, "Pflege")
        self.gruppe_der.append(gruppe)
        if gruppe is None:              # unten: vor dem Umschalter
            self._lay.insertWidget(self._lay.indexOf(self.umschalter), k)
        else:
            nach = self.titel[gruppe]
            letzte = [kk for kk, g in zip(self.knoepfe[:-1], self.gruppe_der[:-1]) if g == gruppe]
            ziel = letzte[-1] if letzte else nach
            self._lay.insertWidget(self._lay.indexOf(ziel) + 1, k)
        self._text_setzen(i)
        self._titel_zeigen()
        if self._aktuell < 0:
            self.setCurrentIndex(i)
        return i

    def count(self):
        return len(self.knoepfe)

    def tabText(self, i):
        return self.texte[i] if 0 <= i < len(self.texte) else ""

    def setTabText(self, i, text):
        if 0 <= i < len(self.texte):
            self.texte[i] = text
            self._text_setzen(i)

    def setTabVisible(self, i, an):
        if not 0 <= i < len(self.knoepfe):
            return
        (self.versteckt.discard if an else self.versteckt.add)(i)
        self.knoepfe[i].setVisible(bool(an))
        self._titel_zeigen()

    def isTabVisible(self, i):
        return 0 <= i < len(self.knoepfe) and i not in self.versteckt

    def currentIndex(self):
        return self._aktuell

    def setCurrentIndex(self, i):
        if not 0 <= i < len(self.knoepfe):
            return
        self.knoepfe[i].setChecked(True)
        if i != self._aktuell:
            self._aktuell = i
            self.currentChanged.emit(i)

    def tabRect(self, i):
        return self.knoepfe[i].geometry() if 0 <= i < len(self.knoepfe) else self.rect()

    # -------------------------------------------------- Breite
    def modus_setzen(self, modus, fensterbreite=None):
        """'automatisch', 'breit' oder 'schmal'; automatisch richtet sich nach der Fensterbreite."""
        self.modus = modus if modus in MODI else "automatisch"
        self._breite_anwenden()
        self.fenster_breite(fensterbreite or (self.window().width() if self.window() is not self else 0))

    def sizeHint(self):
        return QSize(BREIT if self.breit else SCHMAL, super().sizeHint().height())

    def fenster_breite(self, breite):
        """Vom Hauptfenster bei jeder Größenänderung aufgerufen (nur im Modus „automatisch“ wirksam)."""
        breit = self.modus == "breit" or self.modus == "automatisch" and breite >= AUTO_BREIT_AB
        if breit != self.breit:
            self.breit = breit
            self._breite_anwenden()

    def _umschalten(self):
        self.modus = "schmal" if self.breit else "breit"
        self.breit = not self.breit
        self._breite_anwenden()
        self.modus_geaendert.emit(self.modus)

    def _breite_anwenden(self):
        # automatisch: Mindestbreite schmal, damit die Leiste die Mindestbreite des Fensters nicht erhöht (1366 px)
        breite = BREIT if self.breit else SCHMAL
        self.setMinimumWidth(SCHMAL if self.modus == "automatisch" else breite)
        self.setMaximumWidth(breite)
        stil = Qt.ToolButtonTextBesideIcon if self.breit else Qt.ToolButtonIconOnly
        for i, k in enumerate(self.knoepfe):
            k.setToolButtonStyle(stil)
            self._text_setzen(i)
        self._titel_zeigen()
        self.umschalter.setText("«  Leiste schmal" if self.breit else "»")
        self.umschalter.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.umschalter.setToolTip("Seitenleiste nur mit Symbolen zeigen" if self.breit
                                   else "Seitenleiste mit Beschriftung zeigen")

    def _text_setzen(self, i):
        k, text = self.knoepfe[i], self.texte[i]
        k.setText(f" {text}" if self.breit else text)
        tipp = TIPP.get(text, "")
        k.setToolTip(f"{text}: {tipp}" if tipp and not self.breit else tipp or text)

    def _titel_zeigen(self):
        for g, t in self.titel.items():
            sichtbar = any(gg == g and i not in self.versteckt for i, gg in enumerate(self.gruppe_der))
            t.setVisible(self.breit and sichtbar)

    def _geklickt(self, k):
        self.setCurrentIndex(self.knoepfe.index(k))


class MenueEcke(QWidget):
    """Rechter Teil der Menüzeile (U2): geöffnete Angebote links, Suche rechts. Füllt den ganzen Platz neben den
    Menüs, damit Menü, Angebote und Suche eine Zeile teilen statt drei Zeilen zu belegen."""

    def __init__(self, menueleiste, zeile, suchknopf):
        super().__init__()
        self.setObjectName("menueecke")
        self.leiste, self.zeile, self.suchknopf = menueleiste, zeile, suchknopf
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 4, 0)
        lay.setSpacing(8)
        lay.addWidget(zeile, 1)
        zeile.setMinimumHeight(28)              # Platz für das × der Reiter
        lay.addStretch(0)                       # ohne offene Angebote steht die Suche trotzdem rechts
        lay.addWidget(suchknopf, 0, Qt.AlignVCenter)
        suchknopf.setMaximumWidth(300)          # ohne offene Angebote nicht über die ganze Zeile

        self._rechnet = False

    def hoehe(self):
        """Gleichbleibende Höhe, auch solange die Reiter der Angebote ausgeblendet sind (sonst springt die Zeile)."""
        return max(self.zeile.sizeHint().height(), self.suchknopf.sizeHint().height())

    def sizeHint(self):
        h = self.minimumSizeHint()
        if self._rechnet:               # actionGeometry ordnet die Menüleiste neu und fragt dabei wieder hier an
            return h
        self._rechnet = True
        try:
            rechts = max((self.leiste.actionGeometry(a).right() for a in self.leiste.actions() if a.isVisible()),
                         default=0)
        finally:
            self._rechnet = False
        frei = self.leiste.width() - rechts - 6
        return QSize(max(h.width(), frei), self.hoehe())

    def minimumSizeHint(self):
        return QSize(super().minimumSizeHint().width(), self.hoehe())


class Menueleiste(QMenuBar):
    """Menüleiste, die so hoch ist wie ihre Ecke (Reiter der offenen Angebote): QMainWindow nimmt sonst nur die Höhe
    der Menüpunkte, und die Reiter samt × würden gestaucht."""

    def _ecke_hoehe(self):
        e = self.cornerWidget(Qt.TopRightCorner)
        return e.hoehe() if hasattr(e, "hoehe") else 0

    def event(self, e):
        # Stylesheet/Theme ändert die Höhe der Reiter: Layout des Hauptfensters neu fragen (es merkt sich die Höhe)
        if e.type() in (QEvent.Show, QEvent.StyleChange, QEvent.PolishRequest, QEvent.LayoutRequest):
            QTimer.singleShot(0, self, self.updateGeometry)
        return super().event(e)

    def heightForWidth(self, breite):
        return max(super().heightForWidth(breite), self._ecke_hoehe())

    def sizeHint(self):
        h = super().sizeHint()
        return QSize(h.width(), max(h.height(), self._ecke_hoehe()))

    def minimumSizeHint(self):
        h = super().minimumSizeHint()
        return QSize(h.width(), max(h.height(), self._ecke_hoehe()))
