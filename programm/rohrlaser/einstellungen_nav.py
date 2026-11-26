"""Einstellungen mit Navigation links und Suche (Layout-Plan L11) statt einer Reiterzeile mit 20 Unterreitern.

Links stehen die Seiten nach Themen gruppiert (Kalkulation, Material, Maschinen, Blech, Schweißen, STEP-Import),
oben ein Suchfeld: es filtert nach Seitentitel, Spalten der Tabellen und Titeln der Vorgaben; auf der Seite
Vorgaben blendet es zusätzlich die nicht passenden Einstellungen aus.

Nach außen verhält sich die Navigation wie ein QTabWidget (count, tabText, widget, indexOf, currentWidget,
setCurrentWidget, setCurrentIndex, currentChanged), damit Aufrufer und Tests unverändert bleiben.
"""
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

# Thema -> Seiten (Name der Stammdatentabelle bzw. Schlüssel der eigenen Seiten); Unbekanntes landet unter WEITERE
# Seiten der Einstellungen (einstellungen_ordnung.SEITEN, Schlüssel e_…) stehen beim Thema (Plan „Einstellungen
# aufräumen“, 29.10.2026)
GRUPPEN = (
    ("Allgemein", ("e_favoriten", "e_funktionen", "e_firma", "e_admin", "e_plaetze", "e_arbeitsplatz", "e_bedienmodus", "e_navigation", "e_kanten3d", "e_ablage")),
    ("Kalkulation", ("e_zuschlaege", "e_gewinn_gestaffelt", "e_kosten", "vorgaben", "zeitvorgaben", "zusatzarbeiten", "arbeitsgang_regeln")),
    ("Angebot", ("e_neue_angebote", "e_pdf_texte", "e_automatik", "e_angebot_mail", "e_materialanfrage", "e_mail_vorlagen")),
    ("Material", ("profile", "werkstoffe", "oberflaechen", "preise", "material_lieferanten", "materialstamm", "e_erp_preise", "lieferlaengen", "material_index", "e_lieferlaengen", "e_verschachtelung", "e_listen")),
    ("Maschinen", ("maschinen", "schneiddaten", "gewinde", "pruefregeln")),
    ("Blech", ("e_blech", "blech_werkstoffe", "blechlaser", "blech_kfaktoren")),
    ("Dreh- und Frästeile", ("e_drehfraes", "e_drehfraes_grenzen", "drehfraes_werkstoffe")),
    ("Schweißen und Konstruktion", ("e_schweissen", "e_knick_steck", "schweissverfahren", "schweiss_kennwerte",
                                    "schweiss_faktoren", "schweiss_regeln")),
    ("Kunden", ("kundenvorgaben",)),
    ("Import", ("e_step", "e_step_messung", "e_step_ablauf", "e_dxf", "importprofile")),
    ("Fertigung und Versand", ("e_lager", "e_fertigung", "e_auslastung", "e_versand")),
    ("Fracht", ("fracht_zonen", "fracht_tarife", "fracht_lht", "fracht_zuschlaege", "fracht_dienstleister",
                "fracht_historie")),
)
WEITERE = "Weitere"
EBENE_KURZ = {"grund": "Grund", "erweitert": "Erweitert", "experte": "Experte"}     # Knopfreihe im Seitenkopf
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
        if hasattr(e, "titel"):                     # andere Seiten haben eine liste aus dicts (Arbeitsplätze)
            texte += [e.titel, getattr(e, "gruppe", "")]
    for unter in getattr(seite, "teilseiten", ()):  # z. B. Stundensätze + Arbeitsschritte
        texte += suchtexte(unter, "")
    return [x for x in texte if x]


def passt(text, suche):
    return all(w in text.lower() for w in suche.lower().split())


class SeitenStapel(QStackedWidget):
    """Stapel, dessen Mindestbreite nur die sichtbare Seite bestimmt (QStackedWidget nimmt sonst die breiteste aller
    Seiten): mit der Seitenleiste links bleibt das Fenster auch bei 1024 px bedienbar. Genutzt in den Einstellungen
    und im Hauptfenster (UI-Modernisierung U2). Verdeckte Seiten bekommen waagrecht die Größenregel „Ignored“, so
    zählt der Stapel ihre Mindestbreite nicht; die sichtbare Seite behält ihre eigene Regel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._regel = {}
        self.widgetAdded.connect(self._regeln)
        self.widgetAdded.connect(lambda i: self.widget(i).installEventFilter(self))
        self.currentChanged.connect(self._regeln)

    def _regeln(self, _=None):
        aktuell = self.currentWidget()
        for i in range(self.count()):
            w = self.widget(i)
            if id(w) not in self._regel:
                self._regel[id(w)] = w.sizePolicy().horizontalPolicy()
            regel = w.sizePolicy()
            soll = self._regel[id(w)] if w is aktuell else QSizePolicy.Ignored
            if regel.horizontalPolicy() != soll:
                regel.setHorizontalPolicy(soll)
                w.setSizePolicy(regel)
        self.updateGeometry()

    def eventFilter(self, objekt, e):
        # die sichtbare Seite hat ihre Mindestgröße geändert (z. B. Formular daneben geschlossen): Qt meldet das nicht
        # über den Stapel hinaus, also selbst weitergeben
        if e.type() == QEvent.LayoutRequest and objekt is self.currentWidget():
            self.updateGeometry()
        return False


class NurSichtbareSeite(QObject):
    """Dieselbe Regel wie SeitenStapel für einen fertigen Stapel, z. B. den inneren Stapel eines QTabWidget: nur die
    sichtbare Reiterseite bestimmt die Mindestbreite. Sonst drückt die breiteste Seite (etwa die Kalkulation) die
    mittlere Spalte des Angebots so breit, dass links die Teileliste zu schmal wird (UI-Modernisierung U3)."""

    def __init__(self, reiter):
        stapel = reiter.findChild(QStackedWidget, "qt_tabwidget_stackedwidget") if not isinstance(reiter, QStackedWidget) else reiter
        super().__init__(stapel)
        self.stapel, self.reiter, self._regel = stapel, reiter, {}
        stapel.widgetAdded.connect(lambda _: self.regeln())
        stapel.widgetRemoved.connect(lambda _: self.regeln())
        stapel.currentChanged.connect(lambda _: self.regeln())
        self.regeln()

    def regeln(self):
        aktuell = self.stapel.currentWidget()
        for i in range(self.stapel.count()):
            w = self.stapel.widget(i)
            if id(w) not in self._regel:
                self._regel[id(w)] = w.sizePolicy().horizontalPolicy()
                w.installEventFilter(self)
            regel = w.sizePolicy()
            soll = self._regel[id(w)] if w is aktuell else QSizePolicy.Ignored
            if regel.horizontalPolicy() != soll:
                regel.setHorizontalPolicy(soll)
                w.setSizePolicy(regel)
        self.stapel.updateGeometry()
        self.reiter.updateGeometry()

    def eventFilter(self, objekt, e):
        if e.type() == QEvent.LayoutRequest and objekt is self.stapel.currentWidget():
            self.stapel.updateGeometry()
            self.reiter.updateGeometry()
        return False


class NavigationsReiter(QWidget):
    """Ebenen (Patrick 26.11.2026): oben die Wahl Grundeinstellungen / Erweitert / Expertenbereich; die Navigation
    zeigt nur Seiten bis zu dieser Ebene, die Seiten nur ihre Abschnitte bis zu dieser Ebene. Die Suche findet immer
    alle Seiten und Einstellungen. Wer eine höher eingeordnete Seite aufruft (Befehlspalette, Hinweis, Knopf), bekommt
    die Ebene dafür umgestellt."""
    currentChanged = Signal(int)
    ebene_geaendert = Signal(str)

    def __init__(self, parent=None):
        from . import einstellungen_ordnung as ordnung
        super().__init__(parent)
        self.seiten, self.titel, self.items = [], [], []
        self.ebene = ordnung.EXPERTE        # ohne Wahl alles (Tests, eigene Fenster); EinstellungenBereich setzt sie
        self.ebene_merken = None            # Rückruf: gewählte Ebene speichern (je Benutzer/Arbeitsplatz)
        self.ebene_wahl = QComboBox()
        for e in ordnung.EBENEN:
            self.ebene_wahl.addItem(ordnung.EBENE_TITEL[e], e)
            self.ebene_wahl.setItemData(self.ebene_wahl.count() - 1, ordnung.EBENE_TEXT[e], Qt.ToolTipRole)
        self.ebene_wahl.setCurrentIndex(self.ebene_wahl.findData(self.ebene))
        self.ebene_wahl.setToolTip("Welche Einstellungen zu sehen sind. Ausgeblendete Einstellungen gelten weiter mit "
                                   "ihrem Wert; die Suche findet immer alle.")
        self.ebene_wahl.currentIndexChanged.connect(lambda _: self.ebene_setzen(self.ebene_wahl.currentData()))
        # UI Next Level Phase 4: Ebene als Knopfreihe Grund · Erweitert · Experte im Seitenkopf (EinstellungenBereich);
        # das Wahlfeld bleibt verborgen als Schnittstelle (Tests, ältere Aufrufer)
        from .eingabe import Segment
        self.ebene_segment = Segment([EBENE_KURZ[e] for e in ordnung.EBENEN])
        self.ebene_segment.setToolTip("\n".join(f"{EBENE_KURZ[e]}: {ordnung.EBENE_TEXT[e]}" for e in ordnung.EBENEN)
                                      + "\nAusgeblendete Einstellungen gelten weiter; die Suche findet immer alle.")
        self.ebene_segment.setCurrentText(EBENE_KURZ[self.ebene])
        self.ebene_segment.activated.connect(lambda i: self.ebene_setzen(ordnung.EBENEN[i]))
        self.ebene_wahl.setVisible(False)
        self.ebene_info = QLabel()
        self.ebene_info.setWordWrap(True)
        self.ebene_info.setStyleSheet("color: #5F6B7A; font-size: 11px;")
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Einstellung suchen …")
        self.suche.setToolTip("Seiten und Felder der Einstellungen durchsuchen, z. B. Gewinn, Schneiddaten, Firmenlogo")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.filtern)
        self.suche.returnPressed.connect(self._ersten_treffer)
        self.baum = QTreeWidget()
        self.baum.setObjectName("einstnav")
        self.baum.setHeaderHidden(True)
        self.baum.setRootIsDecorated(False)
        self.baum.setIndentation(14)
        self.baum.setMinimumWidth(100)
        self.baum.setMaximumWidth(220)
        self.baum.currentItemChanged.connect(self._gewaehlt)
        self.stapel = SeitenStapel()
        links = self.links = QVBoxLayout()
        links.setContentsMargins(0, 0, 0, 0)
        links.addWidget(self.ebene_wahl)
        links.addWidget(self.suche)
        links.addWidget(self.baum, 1)
        links.addWidget(self.ebene_info)
        # Titel der gewählten Seite über dem Inhalt (Phase 4)
        self.seiten_titel = QLabel()
        self.seiten_titel.setObjectName("abschnitt_gross")
        rechts = self.rechts = QVBoxLayout()
        rechts.setContentsMargins(0, 0, 0, 0)
        rechts.setSpacing(4)
        rechts.addWidget(self.seiten_titel)
        rechts.addWidget(self.stapel, 1)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(links)
        lay.addLayout(rechts, 1)
        self.gruppen = {}
        self.verborgen = set()      # Indizes ausgeschalteter Seiten (Funktionen ein/aus): nie in Navigation/Suche
        fett = QFont()
        fett.setBold(True)
        fett.setCapitalization(QFont.AllUppercase)      # Gruppen klein in Großbuchstaben (Anzeige), Text bleibt
        fett.setPointSizeF(max(7.0, (fett.pointSizeF() if fett.pointSizeF() > 0 else 9.0) * 0.85))
        fett.setLetterSpacing(QFont.PercentageSpacing, 106)
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

    def setTabText(self, i, titel):
        """Titel einer Seite ändern (z. B. Schloss vor geschützten Seiten); die Suche nutzt den neuen Titel."""
        self.titel[i] = titel
        self.items[i].setText(0, titel)

    def widget(self, i):
        return self.seiten[i] if 0 <= i < len(self.seiten) else None

    def indexOf(self, seite):
        return next((i for i, s in enumerate(self.seiten) if s is seite), -1)

    def currentIndex(self):
        return self.indexOf(self.stapel.currentWidget())

    def currentWidget(self):
        return self.stapel.currentWidget()

    def verbergen(self, i, ja):
        """Seite i aus- oder wieder einblenden (Funktion ausgeschaltet); die Gruppe verschwindet mit ihrer letzten
        Seite. War sie gewählt, wird die erste sichtbare Seite gewählt."""
        if ja:
            self.verborgen.add(i)
        else:
            self.verborgen.discard(i)
        self.filtern(self.suche.text())
        if ja and self.currentIndex() == i:
            frei = [j for j in range(len(self.items)) if j not in self.verborgen and self.ebene_zeigt(j)]
            if frei:
                self.setCurrentIndex(frei[0])

    # -------------------------------------------------- Ebenen
    def seite_ebene(self, i):
        from . import einstellungen_ordnung as ordnung
        return ordnung.seite_ebene(schluessel(self.seiten[i]))

    def ebene_zeigt(self, i):
        from . import einstellungen_ordnung as ordnung
        return ordnung.zeigen(self.seite_ebene(i), self.ebene)

    def ebene_setzen(self, ebene, merken=True):
        """Ebene der Anzeige umstellen (Navigation, Abschnitte der Seiten, Wahlfeld)."""
        from . import einstellungen_ordnung as ordnung
        if ebene not in ordnung.EBENEN:
            return
        neu = ebene != self.ebene
        self.ebene = ebene
        if self.ebene_segment.currentText() != EBENE_KURZ[ebene]:
            self.ebene_segment.blockSignals(True)
            self.ebene_segment.setCurrentText(EBENE_KURZ[ebene])
            self.ebene_segment.blockSignals(False)
        if self.ebene_wahl.currentData() != ebene:
            self.ebene_wahl.blockSignals(True)
            self.ebene_wahl.setCurrentIndex(self.ebene_wahl.findData(ebene))
            self.ebene_wahl.blockSignals(False)
        for s in self.seiten:
            if hasattr(s, "ebene_setzen"):
                s.ebene_setzen(ebene)
        self.filtern(self.suche.text())
        mehr = sum(1 for i in range(len(self.seiten)) if i not in self.verborgen and not self.ebene_zeigt(i))
        self.ebene_info.setText(f"{mehr} weitere Seite{'n' if mehr != 1 else ''} unter „Erweitert“ bzw. "
                                "„Experte“; die Suche findet sie." if mehr else "")
        if neu:
            if merken and self.ebene_merken:
                self.ebene_merken(ebene)
            self.ebene_geaendert.emit(ebene)

    def mindestens(self, ebene):
        """Ebene mindestens auf ebene stellen (eine höher eingeordnete Seite/Einstellung wird gezeigt)."""
        from . import einstellungen_ordnung as ordnung
        if ebene and not ordnung.zeigen(ebene, self.ebene):
            self.ebene_setzen(ebene)

    def setCurrentIndex(self, i):
        if 0 <= i < len(self.items) and i not in self.verborgen and not self.ebene_zeigt(i) \
                and not self.suche.text().strip():
            self.mindestens(self.seite_ebene(i))
        if 0 <= i < len(self.items) and i not in self.verborgen:
            self.items[i].setHidden(False)
            self.items[i].parent().setHidden(False)
            self.baum.setCurrentItem(self.items[i])

    def setCurrentWidget(self, seite):
        self.setCurrentIndex(self.indexOf(seite))

    def eintrag_rect(self, titel):
        """(Widget, Rechteck) des Eintrags in der Navigation (für die Bilder der Anleitung)."""
        i = next(j for j, t in enumerate(self.titel) if t == titel or t.removesuffix(" 🔒") == titel)
        return self.baum.viewport(), self.baum.visualItemRect(self.items[i])

    def titel_herausnehmen(self):
        """Seitentitel aus der rechten Spalte nehmen (der Bereich zeigt ihn im Seitenkopf, spart eine Zeile Höhe:
        das maximierte Fenster passt so auch auf 1280 × 680, test_fenster_maximiert)."""
        self.rechts.removeWidget(self.seiten_titel)
        return self.seiten_titel

    # -------------------------------------------------- Auswahl und Suche
    def _gewaehlt(self, item, _alt=None):
        if item is None or item.data(0, SEITE) is None:
            return
        i = item.data(0, SEITE)
        self.seiten_titel.setText(self.titel[i].removesuffix(" 🔒"))
        if self.stapel.currentIndex() != i:
            self.stapel.setCurrentIndex(i)
            self.currentChanged.emit(i)

    def treffer(self, suche):
        """Indizes der Seiten, die zur Suche passen (leer = alle)."""
        return [i for i, (s, t) in enumerate(zip(self.seiten, self.titel)) if i not in self.verborgen
                and ((not suche.strip() and self.ebene_zeigt(i))
                     or (suche.strip() and any(passt(x, suche) for x in suchtexte(s, t))))]

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
