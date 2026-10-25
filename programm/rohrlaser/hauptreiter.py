"""Hauptreiter mit eigener Zeile für geöffnete Angebote (Layout-Plan L13).

Oben stehen immer dieselben Reiter (Start · Angebote · Kunden · Frachtkosten · Zukaufartikel · Einstellungen).
Geöffnete Angebote reihen sich nicht mehr dahinter ein, sondern stehen in einer zweiten Zeile unter „Angebote“:
[Angebotsliste | A-2026-0041 × | A-2026-0040 × …]. Die Zeile erscheint, solange „Angebote“ gewählt ist und
mindestens ein Angebot offen ist; ein Klick auf „Angebote“ kehrt zum zuletzt gezeigten Angebot zurück.

Nach außen verhält sich der Reiter wie ein QTabWidget mit allen Seiten in einer Liste (zuerst die festen, dann die
Angebote): count, tabText, setTabText, widget, indexOf, currentIndex, currentWidget, setCurrentIndex,
setCurrentWidget, addTab, removeTab, setTabVisible, isTabVisible, currentChanged, tabCloseRequested.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QTabBar, QVBoxLayout, QWidget

LISTE = "Angebotsliste"


class HauptReiter(QWidget):
    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fest, self.offen, self.texte = [], [], {}
        self.versteckt = set()          # ids ausgeblendeter fester Seiten (z. B. Versand per Einstellung)
        self.gruppe = None              # Seite, unter der die offenen Angebote stehen (Angebotsliste)
        self._letzte = None             # zuletzt gezeigte Seite der Gruppe
        self._sync = False
        self.oben = QTabBar()
        self.oben.setDrawBase(False)
        self.oben.setExpanding(False)
        self.unten = QTabBar()
        self.unten.setObjectName("angebotszeile")
        self.unten.setDocumentMode(True)
        self.unten.setExpanding(False)
        self.unten.setTabsClosable(True)
        self.unten.setMovable(False)
        self.unten.setVisible(False)
        self.stapel = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.oben)
        lay.addWidget(self.unten)
        lay.addWidget(self.stapel, 1)
        self.oben.currentChanged.connect(self._oben_gewaehlt)
        self.unten.currentChanged.connect(self._unten_gewaehlt)
        self.unten.tabCloseRequested.connect(lambda j: j > 0 and self.tabCloseRequested.emit(len(self.fest) + j - 1))

    # -------------------------------------------------- Aufbau
    def addTab(self, seite, text):
        """Feste Seiten, solange keine Gruppe gesetzt ist; danach (bzw. mit gruppe_setzen) Angebote."""
        self.texte[id(seite)] = text
        self.stapel.addWidget(seite)
        if self.gruppe is None or seite in self.fest:
            self.fest.append(seite)
            self._sync = True
            self.oben.addTab(text)
            self._sync = False
            if len(self.fest) == 1:
                self._zeigen(seite)
        else:
            self.offen.append(seite)
            self._sync = True
            self.unten.addTab(text)
            self._sync = False
            self._zeile()
        return self.indexOf(seite)

    def gruppe_setzen(self, seite):
        """Ab jetzt hinzugefügte Seiten sind Angebote und stehen in der Zeile unter dieser (festen) Seite."""
        self.gruppe = seite
        self._sync = True
        self.unten.addTab(LISTE)
        self.unten.setTabButton(0, QTabBar.RightSide, None)     # die Liste lässt sich nicht schließen
        self.unten.setTabButton(0, QTabBar.LeftSide, None)
        self._sync = False

    def removeTab(self, i):
        seite = self.widget(i)
        if seite is None or seite in self.fest:
            return
        j = self.offen.index(seite)
        aktuell = self.currentWidget() is seite
        self.offen.pop(j)
        self.texte.pop(id(seite), None)
        if self._letzte is seite:
            self._letzte = None
        self._sync = True
        self.unten.removeTab(j + 1)
        self._sync = False
        self.stapel.removeWidget(seite)
        if aktuell:                 # wie QTabWidget: das Nachbarangebot, sonst die Liste
            self._zeigen(self.offen[min(j, len(self.offen) - 1)] if self.offen else self.gruppe)
        self._zeile()

    # -------------------------------------------------- wie QTabWidget
    def _alle(self):
        return self.fest + self.offen

    def count(self):
        return len(self.fest) + len(self.offen)

    def widget(self, i):
        alle = self._alle()
        return alle[i] if 0 <= i < len(alle) else None

    def indexOf(self, seite):
        return next((i for i, s in enumerate(self._alle()) if s is seite), -1)

    def tabText(self, i):
        s = self.widget(i)
        return self.texte.get(id(s), "") if s is not None else ""

    def setTabText(self, i, text):
        s = self.widget(i)
        if s is None:
            return
        self.texte[id(s)] = text
        if s in self.fest:
            self.oben.setTabText(self.fest.index(s), text)
        else:
            self.unten.setTabText(self.offen.index(s) + 1, text)

    def currentWidget(self):
        return self.stapel.currentWidget()

    def currentIndex(self):
        return self.indexOf(self.currentWidget())

    def setCurrentIndex(self, i):
        s = self.widget(i)
        if s is not None:
            self._zeigen(s)

    def setCurrentWidget(self, seite):
        if self.indexOf(seite) >= 0:
            self._zeigen(seite)

    def setTabVisible(self, i, an):
        """Feste Seite ein-/ausblenden; ist die ausgeblendete gerade gewählt, wird die erste Seite gezeigt."""
        s = self.widget(i)
        if s is None or s not in self.fest:
            return
        (self.versteckt.discard if an else self.versteckt.add)(id(s))
        self.oben.setTabVisible(self.fest.index(s), bool(an))
        if not an and self.currentWidget() is s:
            self._zeigen(self.fest[0])

    def isTabVisible(self, i):
        s = self.widget(i)
        return s is not None and id(s) not in self.versteckt

    def eintrag_rect(self, text):
        """(Leiste, Rechteck) eines Reiters nach seinem Text (für die Bilder der Anleitung)."""
        for leiste in (self.oben, self.unten):
            for i in range(leiste.count()):
                if leiste.tabText(i) == text:
                    return leiste, leiste.tabRect(i)
        raise KeyError(text)

    # -------------------------------------------------- Anzeige
    def _in_gruppe(self, seite):
        return seite is self.gruppe or seite in self.offen

    def _zeigen(self, seite):
        alt = self.stapel.currentWidget()
        self.stapel.setCurrentWidget(seite)
        if self._in_gruppe(seite):
            self._letzte = seite
        self._sync = True
        ziel = self.gruppe if self._in_gruppe(seite) else seite
        if ziel in self.fest:
            self.oben.setCurrentIndex(self.fest.index(ziel))
        if seite in self.offen:
            self.unten.setCurrentIndex(self.offen.index(seite) + 1)
        elif seite is self.gruppe and self.unten.count():
            self.unten.setCurrentIndex(0)
        self._sync = False
        self._zeile()
        if seite is not alt:
            self.currentChanged.emit(self.indexOf(seite))

    def _zeile(self):
        self.unten.setVisible(bool(self.offen) and self._in_gruppe(self.stapel.currentWidget()))

    def _oben_gewaehlt(self, i):
        if self._sync or not 0 <= i < len(self.fest):
            return
        s = self.fest[i]
        if s is self.gruppe and self._letzte is not None and self.indexOf(self._letzte) >= 0:
            s = self._letzte
        self._zeigen(s)

    def _unten_gewaehlt(self, j):
        if self._sync or j < 0:
            return
        self._zeigen(self.gruppe if j == 0 else self.offen[j - 1])
