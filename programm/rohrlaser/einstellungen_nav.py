"""Einstellungen mit Navigation links und Suche (Layout-Plan L11) statt einer Reiterzeile mit 20 Unterreitern.

Links stehen die Seiten nach Themen gruppiert (Kalkulation, Material, Maschinen, Blech, Schweißen, STEP-Import),
oben ein Suchfeld: es filtert nach Seitentitel, Spalten der Tabellen und Titeln der Vorgaben; auf der Seite
Vorgaben blendet es zusätzlich die nicht passenden Einstellungen aus.

Nach außen verhält sich die Navigation wie ein QTabWidget (count, tabText, widget, indexOf, currentWidget,
setCurrentWidget, setCurrentIndex, currentChanged), damit Aufrufer und Tests unverändert bleiben.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

# Thema -> Seiten (Name der Stammdatentabelle bzw. Schlüssel der eigenen Seiten); Unbekanntes landet unter WEITERE
GRUPPEN = (
    ("Kalkulation", ("vorgaben", "zeitvorgaben", "zusatzarbeiten")),
    ("Material", ("profile", "werkstoffe", "oberflaechen", "preise", "lieferlaengen")),
    ("Maschinen", ("maschinen", "schneiddaten", "gewinde", "pruefregeln")),
    ("Blech", ("blech_werkstoffe", "blechlaser", "blech_kfaktoren")),
    ("Schweißen", ("schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren")),
    ("Kunden", ("kundenvorgaben",)),
    ("STEP-Import", ("importprofile",)),
)
WEITERE = "Weitere"
SEITE = Qt.UserRole


def schluessel(seite):
    """Name einer Seite für GRUPPEN: Stammdatentabelle (t.name) oder eigenes Attribut schluessel."""
    return getattr(seite, "schluessel", None) or getattr(getattr(seite, "t", None), "name", None) or ""


def suchtexte(seite, titel):
    """Wonach die Suche eine Seite findet: Titel, Spalten der Tabelle, Titel und Gruppen der Vorgaben."""
    texte = [titel]
    t = getattr(seite, "t", None)
    if t is not None:
        texte += [f.titel for f in getattr(t, "felder", ())]
    for e in getattr(seite, "liste", ()):          # EinstellungenSeite: alle Einstellungen
        texte += [e.titel, e.gruppe]
    for unter in getattr(seite, "teilseiten", ()):  # z. B. Stundensätze + Arbeitsschritte
        texte += suchtexte(unter, "")
    return [x for x in texte if x]


def passt(text, suche):
    return all(w in text.lower() for w in suche.lower().split())


class NavigationsReiter(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.seiten, self.titel, self.items = [], [], []
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen (z. B. Gewinn, Schneiddaten, Firmenlogo)")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.filtern)
        self.suche.returnPressed.connect(self._ersten_treffer)
        self.baum = QTreeWidget()
        self.baum.setHeaderHidden(True)
        self.baum.setRootIsDecorated(False)
        self.baum.setIndentation(14)
        self.baum.setMinimumWidth(100)
        self.baum.setMaximumWidth(220)
        self.baum.currentItemChanged.connect(self._gewaehlt)
        self.stapel = QStackedWidget()
        links = self.links = QVBoxLayout()
        links.setContentsMargins(0, 0, 0, 0)
        links.addWidget(self.suche)
        links.addWidget(self.baum, 1)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(links)
        lay.addWidget(self.stapel, 1)
        self.gruppen = {}
        fett = QFont()
        fett.setBold(True)
        for name, _ in GRUPPEN + ((WEITERE, ()),):
            g = QTreeWidgetItem([name])
            g.setFlags(Qt.ItemIsEnabled)
            g.setFont(0, fett)
            self.baum.addTopLevelItem(g)
            g.setExpanded(True)
            g.setHidden(True)
            self.gruppen[name] = g

    # -------------------------------------------------- wie QTabWidget
    def addTab(self, seite, titel):
        k = schluessel(seite)
        gruppe = next((n for n, namen in GRUPPEN if k in namen), WEITERE)
        g = self.gruppen[gruppe]
        item = QTreeWidgetItem([titel])
        item.setData(0, SEITE, len(self.seiten))
        # Reihenfolge innerhalb der Gruppe wie in GRUPPEN
        reihe = dict(GRUPPEN).get(gruppe, ())
        pos = reihe.index(k) if k in reihe else len(reihe)
        stelle = sum(1 for j in range(g.childCount())
                     if self._reihe(g.child(j), reihe) <= pos)
        g.insertChild(stelle, item)
        g.setHidden(False)
        self.seiten.append(seite)
        self.titel.append(titel)
        self.items.append(item)
        self.stapel.addWidget(seite)
        if len(self.seiten) == 1:
            self.baum.setCurrentItem(item)
        return len(self.seiten) - 1

    def _reihe(self, item, reihe):
        k = schluessel(self.seiten[item.data(0, SEITE)])
        return reihe.index(k) if k in reihe else len(reihe)

    def count(self):
        return len(self.seiten)

    def tabText(self, i):
        return self.titel[i]

    def widget(self, i):
        return self.seiten[i] if 0 <= i < len(self.seiten) else None

    def indexOf(self, seite):
        return next((i for i, s in enumerate(self.seiten) if s is seite), -1)

    def currentIndex(self):
        return self.indexOf(self.stapel.currentWidget())

    def currentWidget(self):
        return self.stapel.currentWidget()

    def setCurrentIndex(self, i):
        if 0 <= i < len(self.items):
            self.items[i].setHidden(False)
            self.items[i].parent().setHidden(False)
            self.baum.setCurrentItem(self.items[i])

    def setCurrentWidget(self, seite):
        self.setCurrentIndex(self.indexOf(seite))

    def eintrag_rect(self, titel):
        """(Widget, Rechteck) des Eintrags in der Navigation (für die Bilder der Anleitung)."""
        i = self.titel.index(titel)
        return self.baum.viewport(), self.baum.visualItemRect(self.items[i])

    # -------------------------------------------------- Auswahl und Suche
    def _gewaehlt(self, item, _alt=None):
        if item is None or item.data(0, SEITE) is None:
            return
        i = item.data(0, SEITE)
        if self.stapel.currentIndex() != i:
            self.stapel.setCurrentIndex(i)
            self.currentChanged.emit(i)

    def treffer(self, suche):
        """Indizes der Seiten, die zur Suche passen (leer = alle)."""
        return [i for i, (s, t) in enumerate(zip(self.seiten, self.titel))
                if not suche.strip() or any(passt(x, suche) for x in suchtexte(s, t))]

    def filtern(self, suche):
        gefunden = set(self.treffer(suche))
        for i, item in enumerate(self.items):
            item.setHidden(i not in gefunden)
        for g in self.gruppen.values():
            g.setHidden(all(g.child(j).isHidden() for j in range(g.childCount())))
        for s in self.seiten:                     # Vorgaben: nur passende Einstellungen zeigen
            if hasattr(s, "filtern"):
                s.filtern(suche)
        aktuell = self.baum.currentItem()
        if gefunden and (aktuell is None or aktuell.isHidden()):
            self.setCurrentIndex(min(gefunden))

    def _ersten_treffer(self):
        t = self.treffer(self.suche.text())
        if t:
            self.setCurrentIndex(t[0])
