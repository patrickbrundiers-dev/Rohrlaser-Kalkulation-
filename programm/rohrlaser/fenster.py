"""Hauptfenster: Start, Angebote (Übersicht und je offenes Angebot ein Reiter), Stammdaten und Einstellungen."""
import datetime
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QUrl, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QStyledItemDelegate, QTabBar, QTableView, QTabWidget, QVBoxLayout, QWidget)

from . import NAME, VERSION, ausgabe
from .stammdaten import TABELLEN, EINSTELLUNGEN, pruefen, wert_aus_text, wert_als_text, zahl_als_text

ANLEITUNG = "Bedienungsanleitung.pdf"
FARBE_EINGABE = QColor("#FFF9E0")   # Eingabefelder (gelb)
FARBE_BERECHNET = QColor("#EDEDED")
FARBE_STATUS = {"FEHLER": QColor("#F8CBAD"), "WARNUNG": QColor("#FFD966"), "OK": QColor("#C6EFCE")}


class StammdatenModell(QAbstractTableModel):
    """Eine Stammdatentabelle: Eingabefelder, berechnete Spalten, Prüfung. Jede Änderung wird sofort
    gespeichert."""

    def __init__(self, db, tabelle, meldung):
        super().__init__()
        self.db, self.t, self.meldung = db, tabelle, meldung
        self.spalten = ([("feld", f) for f in tabelle.felder] + [("berechnet", b) for b in tabelle.berechnet]
                        + [("pruefung", None)])
        self.neu_laden()

    def neu_laden(self):
        self.beginResetModel()
        self.daten = self.db.zeilen(self.t.name)
        self.k = self.db.kontext()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.daten)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.spalten)

    def headerData(self, abschnitt, richtung, rolle=Qt.DisplayRole):
        if rolle != Qt.DisplayRole:
            return None
        if richtung == Qt.Vertical:
            return str(abschnitt + 1)
        art, s = self.spalten[abschnitt]
        return s.titel if art == "feld" else (s[0] if art == "berechnet" else "Prüfung")

    def roh(self, zeile, spalte):
        """Wert für Sortierung und Prüfung."""
        z = self.daten[zeile]
        art, s = self.spalten[spalte]
        if art == "feld":
            return z.get(s.name)
        if art == "berechnet":
            return s[1](z, self.k)
        return pruefen(self.t, z, self.k)

    def data(self, index, rolle=Qt.DisplayRole):
        if not index.isValid():
            return None
        art, s = self.spalten[index.column()]
        w = self.roh(index.row(), index.column())
        if rolle in (Qt.DisplayRole, Qt.ToolTipRole):
            if art == "feld":
                return wert_als_text(s, w)
            if art == "berechnet":
                return zahl_als_text(w, s[2]) if w is not None else ""
            return w
        if rolle == Qt.EditRole and art == "feld":
            return wert_als_text(s, w, bearbeiten=True)
        if rolle == Qt.UserRole:
            return w
        if rolle == Qt.TextAlignmentRole:
            if art == "berechnet" or (art == "feld" and s.art in ("zahl", "ganz")):
                return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.BackgroundRole:
            if art == "pruefung":
                return QBrush(FARBE_STATUS.get(str(w).split(":")[0], FARBE_BERECHNET))
            return QBrush(FARBE_EINGABE if art == "feld" else FARBE_BERECHNET)
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.spalten[index.column()][0] == "feld":
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index, text, rolle=Qt.EditRole):
        if rolle != Qt.EditRole or not index.isValid():
            return False
        art, f = self.spalten[index.column()]
        if art != "feld":
            return False
        z = self.daten[index.row()]
        try:
            wert = wert_aus_text(f, text)
            if wert == z.get(f.name):
                return False
            self.db.aendern(self.t.name, z["id"], f.name, wert)
        except ValueError as e:
            self.meldung(str(e), fehler=True)
            return False
        self.neu_laden()   # berechnete Spalten und Prüfung der übrigen Zeilen können sich ändern
        self.meldung(f"{f.titel} gespeichert.")
        return True

    def zeile_neu(self):
        self.db.neu(self.t.name)
        self.neu_laden()
        return len(self.daten) - 1

    def zeilen_loeschen(self, zeilen):
        self.db.loeschen(self.t.name, [self.daten[r]["id"] for r in zeilen])
        self.neu_laden()


class Sortierung(QSortFilterProxyModel):
    """Sortiert nach dem gespeicherten Wert (Zahlen als Zahlen), leere Werte zuletzt."""

    def lessThan(self, links, rechts):
        a, b = links.data(Qt.UserRole), rechts.data(Qt.UserRole)
        if a is None or b is None:
            return a is not None and b is None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return str(a).lower() < str(b).lower()


class Auswahl(QStyledItemDelegate):
    """Auswahlliste für Felder mit fester Liste (Profilform, Preisbasis, Profil-ID, …)."""

    def __init__(self, modell, parent):
        super().__init__(parent)
        self.modell = modell

    def createEditor(self, parent, option, index):
        quelle = self.modell.mapToSource(index) if hasattr(self.modell, "mapToSource") else index
        art, f = quelle.model().spalten[quelle.column()]
        if art == "feld" and f.art == "auswahl":
            cb = QComboBox(parent)
            cb.setEditable(f.auswahl not in ("preisbasis", "profilform", "zusatzart", "janein"))
            cb.addItems([""] + quelle.model().k.auswahl(f.auswahl))
            return cb
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            editor.setCurrentText(index.data(Qt.EditRole) or "")
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, modell, index):
        if isinstance(editor, QComboBox):
            modell.setData(index, editor.currentText(), Qt.EditRole)
        else:
            super().setModelData(editor, modell, index)


class StammdatenSeite(QWidget):
    def __init__(self, db, tabelle, meldung):
        super().__init__()
        self.t = tabelle
        self.modell = StammdatenModell(db, tabelle, meldung)
        self.filter = Sortierung()
        self.filter.setSourceModel(self.modell)
        self.filter.setFilterKeyColumn(-1)
        self.filter.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.db, self.meldung = db, meldung

        hinweis = QLabel(tabelle.hinweis)
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #595959;")
        neu = QPushButton("Neue Zeile")
        neu.clicked.connect(self.zeile_neu)
        weg = QPushButton("Zeilen löschen")
        weg.clicked.connect(self.zeilen_loeschen)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.filter.setFilterFixedString)
        self.anzahl = QLabel()
        leiste = QHBoxLayout()
        for w in (neu, weg):
            leiste.addWidget(w)
        leiste.addSpacing(20)
        leiste.addWidget(self.suche, 1)
        leiste.addWidget(self.anzahl)

        self.ansicht = QTableView()
        self.ansicht.setModel(self.filter)
        self.ansicht.setItemDelegate(Auswahl(self.filter, self.ansicht))
        self.ansicht.setSortingEnabled(True)
        self.ansicht.sortByColumn(-1, Qt.AscendingOrder)
        self.ansicht.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ansicht.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                     | QAbstractItemView.AnyKeyPressed)
        self.ansicht.setAlternatingRowColors(False)
        kopf = self.ansicht.horizontalHeader()
        kopf.setDefaultAlignment(Qt.AlignCenter | Qt.TextWordWrap)
        kopf.setMinimumHeight(48)
        kopf.setSectionResizeMode(QHeaderView.Interactive)
        for i, (art, s) in enumerate(self.modell.spalten):
            self.ansicht.setColumnWidth(i, s.breite if art == "feld" else (110 if art == "berechnet" else 260))
        self.ansicht.verticalHeader().setDefaultSectionSize(24)

        lay = QVBoxLayout(self)
        lay.addWidget(hinweis)
        lay.addLayout(leiste)
        lay.addWidget(self.ansicht, 1)
        self.modell.modelReset.connect(self.zaehlen)
        self.zaehlen()

    def zaehlen(self):
        n = len(self.modell.daten)
        fehler = sum(1 for r in range(n) if str(self.modell.roh(r, len(self.modell.spalten) - 1)).startswith("FEHLER"))
        self.anzahl.setText(f"{n} Zeilen" + (f", {fehler} mit FEHLER" if fehler else ""))

    def neu_laden(self):
        self.modell.neu_laden()

    def zeile_neu(self):
        self.suche.clear()
        r = self.modell.zeile_neu()
        idx = self.filter.mapFromSource(self.modell.index(r, 0))
        self.ansicht.scrollTo(idx)
        self.ansicht.setCurrentIndex(idx)
        self.ansicht.edit(idx)

    def zeilen_loeschen(self):
        zeilen = sorted({self.filter.mapToSource(i).row() for i in self.ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.meldung("Bitte zuerst die Zeilen markieren, die gelöscht werden sollen.", fehler=True)
            return
        verweise = sum(self.db.verweise(self.t.name, self.modell.daten[r]["id"]) for r in zeilen)
        text = f"{len(zeilen)} Zeile(n) aus '{self.t.titel}' löschen?"
        if verweise:
            text += f"\n\n{verweise} Zeile(n) in anderen Tabellen verweisen darauf und zeigen danach FEHLER."
        if QMessageBox.question(self, "Löschen", text) == QMessageBox.Yes:
            self.modell.zeilen_loeschen(zeilen)
            self.meldung(f"{len(zeilen)} Zeile(n) gelöscht.")


class MehrzeiligEingabe(QPlainTextEdit):
    fertig = Signal()

    def focusOutEvent(self, ereignis):
        super().focusOutEvent(ereignis)
        self.fertig.emit()


class EinstellungenSeite(QScrollArea):
    def __init__(self, db, meldung):
        super().__init__()
        self.db, self.meldung = db, meldung
        self.setWidgetResizable(True)
        innen = QWidget()
        lay = QVBoxLayout(innen)
        self.felder = {}
        gruppen = {}
        for e in EINSTELLUNGEN:
            if e.gruppe not in gruppen:
                box = QGroupBox(e.gruppe)
                gruppen[e.gruppe] = QFormLayout(box)
                lay.addWidget(box)
            w = self._eingabe(e)
            self.felder[e.name] = w
            gruppen[e.gruppe].addRow(e.titel, w)
        lay.addStretch(1)
        self.setWidget(innen)
        self.neu_laden()

    def _eingabe(self, e):
        if e.art == "anteil":
            w = QDoubleSpinBox()
            w.setRange(e.von * 100, e.bis * 100)
            w.setDecimals(1)
            w.setSuffix(" %")
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, round(w.value() / 100, 6)))
        elif e.art == "zahl":
            w = QDoubleSpinBox()
            w.setRange(e.von, e.bis)
            w.setDecimals(2)
            w.setGroupSeparatorShown(True)
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, round(w.value(), 2)))
        elif e.art == "ganz":
            w = QSpinBox()
            w.setRange(int(e.von), int(e.bis))
            w.setGroupSeparatorShown(True)
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, w.value()))
        elif e.art == "mehrzeilig":
            w = MehrzeiligEingabe()
            w.setFixedHeight(80)
            w.fertig.connect(lambda e=e, w=w: self._speichern(e, w.toPlainText().strip()))
        elif e.art == "auswahl":
            w = QComboBox()
            w.setEditable(True)
            w.currentTextChanged.connect(lambda text, e=e: self._speichern(e, text.strip()))
        else:
            w = QLineEdit()
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, w.text().strip()))
        return w

    def _speichern(self, e, wert):
        if getattr(self, "_laden", False) or self.db.einstellung(e.name) == wert:
            return
        self.db.einstellung_setzen(e.name, wert)
        self.meldung(f"{e.titel} gespeichert.")

    def neu_laden(self):
        self._laden = True
        k = self.db.kontext()
        for e in EINSTELLUNGEN:
            w, v = self.felder[e.name], self.db.einstellung(e.name)
            if e.art == "anteil":
                w.setValue((v or 0) * 100)
            elif e.art == "zahl":
                w.setValue(v or 0)
            elif e.art == "ganz":
                w.setValue(int(v or 0))
            elif e.art == "mehrzeilig":
                w.setPlainText(v or "")
            elif e.art == "auswahl":
                w.clear()
                w.addItems(k.auswahl(e.auswahl))
                w.setCurrentText(v or "")
            else:
                w.setText(v or "")
        self._laden = False


class StartSeite(QWidget):
    def __init__(self, fenster):
        super().__init__()
        self.f = fenster
        titel = QLabel(f"<h2>{NAME}</h2><p>Version {VERSION}</p>")
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        knoepfe = QHBoxLayout()
        for text, ziel in (("Datensicherung erstellen", fenster.sicherung_erstellen),
                           ("Datenordner öffnen", fenster.datenordner_oeffnen)):
            b = QPushButton(text)
            b.clicked.connect(ziel)
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        hinweis = QLabel("Angebote werden im Reiter 'Angebote' angelegt. "
                         "Im Angebot: Staffelpreise im Reiter 'Staffeln', Angebot, Werkstattpapiere und Kalkulation als PDF sowie "
                         "CSV-Export über die Leiste 'Ausgabe'. Die Dateien landen im Ablageordner (Einstellungen).")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #595959;")
        lay = QVBoxLayout(self)
        lay.addWidget(titel)
        lay.addWidget(self.info)
        lay.addLayout(knoepfe)
        lay.addSpacing(20)
        lay.addWidget(hinweis)
        lay.addStretch(1)
        self.neu_laden()

    def neu_laden(self):
        db = self.f.db
        zeilen = "".join(f"<tr><td>{t.titel}</td><td align='right'>{db.anzahl(t.name)}</td></tr>" for t in TABELLEN)
        herkunft = db.einstellung("stammdaten_herkunft") or "–"
        stand = db.einstellung("stammdaten_stand") or ""
        if stand:
            stand = datetime.datetime.fromisoformat(stand).strftime("%d.%m.%Y %H:%M")
        warnung = ""
        if herkunft == "Beispieldaten":
            warnung = ("<p style='color:#C00000'><b>Die Stammdaten sind Beispielwerte.</b> Bitte in den "
                       "Stammdaten-Reitern durch die eigenen Werte ersetzen.</p>")
        self.info.setText(f"<p>Datendatei: {db.pfad}</p><p>Stammdaten: {herkunft} (Stand {stand})</p>{warnung}"
                          f"<table cellpadding='2'>{zeilen}</table>")


class Hauptfenster(QMainWindow):
    def __init__(self, db, programmordner=None, stumm=False):
        from .angebot_fenster import AngeboteSeite
        super().__init__()
        self.db = db
        self.programmordner = Path(programmordner or Path(__file__).resolve().parent.parent)
        self.stumm = stumm          # Selbsttest: keine Rückfragen und Meldungsfenster
        self.offen = {}             # Angebots-ID -> AngebotSeite
        self.setWindowTitle(f"{NAME} {VERSION}")
        self.resize(1400, 800)
        self.reiter = QTabWidget()
        self.reiter.setTabsClosable(True)
        self.reiter.tabCloseRequested.connect(self._reiter_schliessen)
        self.start = StartSeite(self)
        self.reiter.addTab(self.start, "Start")
        self.angebote = AngeboteSeite(self)
        self.angebote.oeffnen.connect(self.angebot_oeffnen)
        self.reiter.addTab(self.angebote, "Angebote")
        self.seiten = [StammdatenSeite(db, t, self.meldung) for t in TABELLEN]
        for s in self.seiten:
            self.reiter.addTab(s, s.t.titel)
        self.einstellungen = EinstellungenSeite(db, self.meldung)
        self.reiter.addTab(self.einstellungen, "Einstellungen")
        for i in range(self.reiter.count()):     # feste Reiter ohne Schließen-Knopf
            self.reiter.tabBar().setTabButton(i, QTabBar.RightSide, None)
        self.reiter.currentChanged.connect(self.reiter_gewechselt)
        self.setCentralWidget(self.reiter)
        self._menue()
        self.statusBar().showMessage("Bereit")

    def _menue(self):
        datei = self.menuBar().addMenu("&Datei")
        for text, ziel, taste in (("Datensicherung erstellen", self.sicherung_erstellen, None),
                                  ("Datenordner öffnen", self.datenordner_oeffnen, None),
                                  ("Ablageordner öffnen (PDF, CSV)", self.ablage_oeffnen, None),
                                  (None, None, None),
                                  ("Beenden", self.close, QKeySequence.Quit)):
            if text is None:
                datei.addSeparator()
                continue
            a = QAction(text, self)
            a.triggered.connect(ziel)
            if taste:
                a.setShortcut(taste)
            datei.addAction(a)
        hilfe = self.menuBar().addMenu("&Hilfe")
        a = QAction("Bedienungsanleitung (PDF)", self)
        a.setShortcut(QKeySequence.HelpContents)
        a.triggered.connect(self.anleitung_oeffnen)
        hilfe.addAction(a)
        a = QAction("Über …", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, NAME, f"<b>{NAME}</b> {VERSION}<br>Angebotskalkulation und Materialoptimierung für Rohrlaserteile.<br>"
                        f"Daten: {self.db.pfad}"))
        hilfe.addAction(a)

    def angebot_oeffnen(self, angebot_id):
        from .angebot_fenster import AngebotSeite
        seite = self.offen.get(angebot_id)
        if seite is None:
            seite = AngebotSeite(self, angebot_id)
            self.offen[angebot_id] = seite
            self.reiter.addTab(seite, seite.titel())
        self.reiter.setCurrentWidget(seite)
        return seite

    def angebot_schliessen(self, angebot_id):
        seite = self.offen.pop(angebot_id, None)
        if seite is not None:
            self.reiter.removeTab(self.reiter.indexOf(seite))
            seite.deleteLater()

    def _reiter_schliessen(self, i):
        w = self.reiter.widget(i)
        for aid, seite in list(self.offen.items()):
            if seite is w:
                self.angebot_schliessen(aid)

    def reiter_titel(self, seite):
        i = self.reiter.indexOf(seite)
        if i >= 0:
            self.reiter.setTabText(i, seite.titel())

    def meldung(self, text, fehler=False):
        self.statusBar().setStyleSheet("color: #C00000;" if fehler else "")
        self.statusBar().showMessage(text, 8000)

    def reiter_gewechselt(self, _):
        w = self.reiter.currentWidget()
        if hasattr(w, "neu_laden"):
            w.neu_laden()

    def alles_neu_laden(self):
        self.start.neu_laden()
        self.angebote.neu_laden()
        for seite in self.offen.values():
            seite.neu_laden()
        for s in self.seiten:
            s.neu_laden()
        self.einstellungen.neu_laden()

    def anleitung_oeffnen(self):
        """Bedienungsanleitung.pdf neben dem Programm (liegt im ZIP), beim Entwickeln aus dem Ordner anleitung."""
        for pfad in (self.programmordner / ANLEITUNG, self.programmordner.parent / "anleitung" / ANLEITUNG):
            if pfad.is_file():
                self.datei_oeffnen(pfad)
                return pfad
        QMessageBox.warning(self, "Bedienungsanleitung", f"{ANLEITUNG} wurde nicht gefunden.\n\n"
                            f"Sie gehört in den Programmordner:\n{self.programmordner}")
        return None

    def sicherung_erstellen(self):
        ziel = self.db.sicherung()
        self.meldung(f"Sicherung erstellt: {ziel}")

    def datenordner_oeffnen(self):
        self.datei_oeffnen(self.db.pfad.parent)

    def ablage(self):
        """Ordner für PDF und CSV-Export (Einstellung 'Ablageordner', sonst 'Angebote' neben dem Programm)."""
        return ausgabe.ablageordner(self.db.einstellung("ablageordner"), self.programmordner)

    def ablage_oeffnen(self):
        try:
            self.datei_oeffnen(self.ablage())
        except OSError as e:
            QMessageBox.warning(self, "Ablage", f"Der Ablageordner lässt sich nicht öffnen:\n{e}")

    def datei_oeffnen(self, pfad):
        """Datei oder Ordner mit dem zugehörigen Programm öffnen (im Selbsttest nicht)."""
        if self.stumm:
            return
        if sys.platform == "win32":
            os.startfile(str(pfad))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pfad)))
