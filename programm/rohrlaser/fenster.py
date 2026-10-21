"""Hauptfenster: Start, Angebote (Übersicht und je offenes Angebot ein Reiter), Kunden, Frachtkosten,
Zukaufartikel und Einstellungen.

Der Reiter Einstellungen ist mit einem Passwort geschützt (Einstellung 'passwort') und enthält als Unterreiter die
allgemeinen Vorgaben und alle Stammdaten außer den Kunden. Im Reiter Frachtkosten ist der Rechner frei, die
Pflegebereiche öffnen mit demselben Passwort."""
import datetime
import os
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QUrl, Signal
from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QStackedWidget, QStyledItemDelegate, QTabBar, QTableView, QTabWidget, QVBoxLayout, QWidget)

from . import NAME, ausgabe, tastatur, update
from .spaltenbreite import AutoGroesse
from .stammdaten import LASER, TABELLEN, EINSTELLUNGEN, Feld, pruefen, wert_aus_text, wert_als_text, zahl_als_text

ANLEITUNG = "Bedienungsanleitung.pdf"
FARBE_EINGABE = QColor("#FFF9E0")   # Eingabefelder (gelb)
FARBE_BERECHNET = QColor("#EDEDED")
FARBE_STATUS = {"FEHLER": QColor("#F8CBAD"), "WARNUNG": QColor("#FFD966"), "OK": QColor("#C6EFCE")}
# Einheitliches Aussehen: helle, neutrale Flächen, Karten mit dünnem Rahmen, ruhige Statusfarben
STIL = """
QFrame#karte { background: #FFFFFF; border: 1px solid #D5DBE3; border-radius: 6px; }
QLabel#kartentitel { font-weight: bold; color: #1F2937; }
QLabel#gruppentitel { font-weight: bold; color: #3A4656; padding-bottom: 2px; border-bottom: 1px solid #E3E7EC; }
QFrame#kennzahl { background: #F5F7FA; border: 1px solid #E3E7EC; border-radius: 4px; }
QLabel#kennzahltitel { color: #5F6B7A; }
QLabel#kennzahlwert { font-weight: bold; color: #1F2937; }
QFrame#preis { background: #EEF4FB; border: 1px solid #C9DAEE; border-radius: 4px; }
QLabel#preiswert { font-weight: bold; font-size: 13pt; color: #1F5FA8; }
QLabel#preiswert_klein { font-weight: bold; font-size: 11pt; color: #1F2937; }
QLabel#stand_ok { background: #E3F4E8; color: #1E6B34; border: 1px solid #B7DFC3; border-radius: 4px; font-weight: bold; }
QLabel#stand_offen { background: #FFF6DB; color: #7A5A00; border: 1px solid #F0D98C; border-radius: 4px; font-weight: bold; }
QLabel#stand_veraltet { background: #FDECEA; color: #8C1D18; border: 1px solid #F3B8B2; border-radius: 4px; font-weight: bold; }
QToolButton#kartenknopf { border: none; font-weight: bold; color: #1F2937; padding: 2px 0; }
QToolButton#aufklapper { border: none; text-align: left; color: #3A4656; padding: 2px 0; }
QToolButton#meldung_ok { border: none; color: #1E6B34; font-weight: bold; padding: 2px 0; }
QToolButton#meldung_warnung { border: none; color: #7A5A00; font-weight: bold; padding: 2px 0; }
QToolButton#meldung_fehler { border: none; color: #B42318; font-weight: bold; padding: 2px 0; }
QPushButton { padding: 4px 10px; border: 1px solid #C5CCD6; border-radius: 4px; background: #FFFFFF; }
QPushButton:hover { background: #F1F4F8; }
QPushButton:pressed { background: #E2E8F0; }
QPushButton:disabled { color: #9AA3AF; }
QPushButton#primaer { background: #1F5FA8; color: #FFFFFF; border-color: #1A528F; font-weight: bold; }
QPushButton#primaer:hover { background: #1A528F; }
QPushButton::menu-indicator { subcontrol-position: right center; right: 4px; }
QPushButton[menu="true"] { padding-right: 18px; }
QTableView { gridline-color: #E3E7EC; selection-background-color: #CFE0F5; selection-color: #111827; }
QHeaderView::section { background: #F1F3F6; color: #1F2937; border: none; border-right: 1px solid #DDE2E8;
                       border-bottom: 1px solid #C9D0D8; padding: 3px; font-weight: bold; }
"""


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

    def zeile_neu(self, werte=None):
        self.db.neu(self.t.name, werte)
        self.neu_laden()
        return len(self.daten) - 1

    def zeilen_loeschen(self, zeilen):
        self.db.loeschen(self.t.name, [self.daten[r]["id"] for r in zeilen])
        self.neu_laden()


class Sortierung(QSortFilterProxyModel):
    """Sortiert nach dem gespeicherten Wert (Zahlen als Zahlen), leere Werte zuletzt. fest = (Spalte, Wert): nur
    Zeilen mit genau diesem Wert (z. B. Preisstaffeln eines Tarifs)."""
    fest = None

    def filterAcceptsRow(self, zeile, eltern):
        if self.fest is not None:
            spalte, wert = self.fest
            if self.sourceModel().roh(zeile, spalte) != wert:
                return False
        return super().filterAcceptsRow(zeile, eltern)

    def lessThan(self, links, rechts):
        a, b = links.data(Qt.UserRole), rechts.data(Qt.UserRole)
        if a is None or b is None:
            return a is not None and b is None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return str(a).lower() < str(b).lower()


def liste_fuellen(cb, k, quelle, erster=""):
    """Auswahlliste füllen; Werkstoffe und Oberflächen mit Überschriften je Kategorie (nicht wählbar).
    erster: Eintrag vor der Liste (None = keiner)."""
    if erster is not None:
        cb.addItem(erster)
    for titel, werte in k.gruppiert(quelle):
        if titel:
            cb.addItem(f"— {titel} —")
            it = cb.model().item(cb.count() - 1)
            it.setEnabled(False)
            f = it.font()
            f.setBold(True)
            it.setFont(f)
        cb.addItems(werte)


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
            cb.setEditable(f.auswahl not in ("preisbasis", "profilform", "zusatzart", "janein", "materialherkunft"))
            liste_fuellen(cb, quelle.model().k, f.auswahl)
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
    KUERZEL = {"neu": "zeile_neu", "loeschen": ("zeilen_loeschen", "ansicht")}     # siehe tastatur.py

    def __init__(self, db, tabelle, meldung):
        super().__init__()
        self.t = tabelle
        self.modell = StammdatenModell(db, tabelle, meldung)
        self.filter = Sortierung()
        self.filter.setSourceModel(self.modell)
        self.filter.setFilterKeyColumn(-1)
        self.filter.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.db, self.meldung = db, meldung
        self.vorgabe = {}           # Werte neuer Zeilen (z. B. Tarif bei gefilterten Preisstaffeln)

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
        tastatur.suche_esc(self.suche)
        self.anzahl = QLabel()
        leiste = QHBoxLayout()
        for w in (neu, weg):
            leiste.addWidget(w)
        if tabelle.name == "schneiddaten":
            standard = QPushButton("Auf Standard zurücksetzen …")
            standard.setToolTip("Schneiddaten einer Maschine oder aller Maschinen durch die mitgelieferten "
                                "Richtwerte ersetzen")
            standard.clicked.connect(self.schneiddaten_zuruecksetzen)
            leiste.addWidget(standard)
        if tabelle.name == "kunden":
            export = QPushButton("CSV exportieren")
            export.setToolTip("Alle Kunden als CSV-Datei speichern (Semikolon, für Excel)")
            export.clicked.connect(self.kunden_exportieren)
            einlesen = QPushButton("CSV importieren …")
            einlesen.setToolTip("Kunden aus einer CSV-Datei: zuerst Vorschau mit Prüfung, vorhandene Kundennummern "
                                "werden geändert, vorher Datensicherung")
            einlesen.clicked.connect(self.kunden_importieren)
            leiste.addWidget(export)
            leiste.addWidget(einlesen)
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
        AutoGroesse(self.ansicht)        # Breite und Höhe passend zum Inhalt, Vorgabebreiten bis zum ersten Füllen

        lay = QVBoxLayout(self)
        lay.addWidget(hinweis)
        lay.addLayout(leiste)
        lay.addWidget(self.ansicht, 1)
        self.modell.modelReset.connect(self.zaehlen)
        self.zaehlen()

    def zaehlen(self):
        n = self.filter.rowCount() if self.filter.fest is not None else len(self.modell.daten)
        fehler = sum(1 for r in range(n) if str(self.modell.roh(r, len(self.modell.spalten) - 1)).startswith("FEHLER"))
        self.anzahl.setText(f"{n} Zeilen" + (f", {fehler} mit FEHLER" if fehler else ""))

    def neu_laden(self):
        self.modell.neu_laden()

    def nur(self, feld, wert):
        """Nur Zeilen mit feld = wert zeigen (None = alle); neue Zeilen bekommen den Wert."""
        spalte = next(i for i, (art, f) in enumerate(self.modell.spalten) if art == "feld" and f.name == feld)
        self.filter.fest = None if wert is None else (spalte, wert)
        self.vorgabe = {} if wert is None else {feld: wert}
        self.filter.invalidateFilter()
        self.zaehlen()

    def ausgewaehlt(self):
        """Zeile (dict) der aktuellen Auswahl oder None."""
        idx = self.ansicht.currentIndex()
        if not idx.isValid():
            return None
        return self.modell.daten[self.filter.mapToSource(idx).row()]

    def zeile_neu(self):
        self.suche.clear()
        try:
            r = self.modell.zeile_neu(self.vorgabe or None)
        except sqlite3.IntegrityError:
            self.meldung("Es gibt schon eine leere neue Zeile mit diesem Schlüssel – bitte zuerst ausfüllen.", fehler=True)
            return
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

    def kunden_exportieren(self, pfad=None):
        from .kunden_csv_dialog import csv_exportieren
        try:
            pfad = csv_exportieren(self, self.db, pfad)
        except OSError as e:
            self.meldung(f"CSV-Export: {e}", fehler=True)
            return None
        if pfad:
            self.meldung(f"Kunden exportiert: {pfad}")
        return pfad

    def kunden_importieren(self, pfad=None, bestaetigt=None, nur_neue=False):
        """CSV-Import mit Vorschau (kunden_csv_dialog). Ergebnis: (neu, geändert, Sicherung) oder None."""
        from .kunden_csv_dialog import csv_importieren
        try:
            _, erg = csv_importieren(self, self.db, pfad, bestaetigt, nur_neue)
        except (OSError, ValueError) as e:
            self.meldung(f"CSV-Import: {e}", fehler=True)
            return None
        if erg and erg[2]:
            f = self.window()
            f.alles_neu_laden() if hasattr(f, "alles_neu_laden") else self.neu_laden()
            self.meldung(f"CSV-Import: {erg[0]} Kunden neu, {erg[1]} geändert. Sicherung vorher: {erg[2]}")
        return erg

    def schneiddaten_zuruecksetzen(self):
        """Schneiddaten einer Maschine oder aller Maschinen mit Richtwerten (T03, T11, LT7) nach Sicherheitsabfrage
        auf die mitgelieferten Standardwerte zurücksetzen (Datenbank.schneiddaten_zuruecksetzen)."""
        alle = f"Alle Maschinen ({', '.join(LASER)})"
        wahl, ok = QInputDialog.getItem(
            self, "Schneiddaten auf Standard zurücksetzen",
            "Für welche Maschine sollen die mitgelieferten Standard-Schneiddaten wiederhergestellt werden?",
            [alle] + [f"{m} ({laser}-Laser)" for m, laser in LASER.items()], 0, False)
        if not ok:
            return
        maschinen = list(LASER) if wahl == alle else [wahl.split(" ")[0]]
        n = sum(1 for z in self.modell.daten if z.get("maschinen_id") in maschinen)
        text = (f"Alle {n} Schneiddaten-Zeilen von {', '.join(maschinen)} werden gelöscht, auch eigene Werte und "
                "Zeilen je Werkstoff, und durch die mitgelieferten Standardwerte ersetzt.\n\n"
                "Bereits gerechnete Angebote mit festgeschriebenen Preisen bleiben unverändert. "
                "Das lässt sich nicht rückgängig machen (nur über eine Datensicherung).\n\nWirklich zurücksetzen?")
        if QMessageBox.question(self, "Schneiddaten zurücksetzen", text,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        weg, neu = self.db.schneiddaten_zuruecksetzen(maschinen)
        self.neu_laden()
        self.meldung(f"Schneiddaten {', '.join(maschinen)} auf Standard zurückgesetzt: {weg} Zeile(n) entfernt, "
                     f"{neu} Standardzeile(n) eingefügt.")


class MehrzeiligEingabe(QPlainTextEdit):
    fertig = Signal()

    def focusOutEvent(self, ereignis):
        super().focusOutEvent(ereignis)
        self.fertig.emit()


def logo_aus_datei(pfad, groesste=1200):
    """Bilddatei (PNG, JPG, BMP …) als Base64-PNG für die Einstellung 'logo', auf höchstens `groesste` Pixel
    verkleinert. ValueError, wenn die Datei kein lesbares Bild ist."""
    bild = QImage(str(pfad))
    if bild.isNull():
        raise ValueError(f"{Path(pfad).name} ist kein lesbares Bild (PNG oder JPG wählen).")
    if max(bild.width(), bild.height()) > groesste:
        bild = bild.scaled(groesste, groesste, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    roh = QByteArray()
    puffer = QBuffer(roh)
    puffer.open(QBuffer.WriteOnly)
    bild.save(puffer, "PNG")
    return bytes(roh.toBase64()).decode("ascii")


class LogoEingabe(QWidget):
    """Einstellung 'bild': Vorschau, 'Bild wählen …' und 'Entfernen'. geaendert(daten) mit Base64-PNG oder ''."""
    geaendert = Signal(str)

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.vorschau = QLabel("kein Logo")
        self.vorschau.setFixedSize(160, 60)
        self.vorschau.setAlignment(Qt.AlignCenter)
        self.vorschau.setStyleSheet("border: 1px solid #BFBFBF; background: white;")
        waehlen, weg = QPushButton("Bild wählen …"), QPushButton("Entfernen")
        waehlen.clicked.connect(self._waehlen)
        weg.clicked.connect(lambda: self._setzen(""))
        for w in (self.vorschau, waehlen, weg):
            lay.addWidget(w)
        lay.addStretch(1)

    def anzeigen(self, daten):
        bild = QPixmap()
        if daten and bild.loadFromData(QByteArray.fromBase64(daten.encode("ascii"))):
            self.vorschau.setPixmap(bild.scaled(156, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.vorschau.clear()
            self.vorschau.setText("kein Logo")

    def _waehlen(self):
        from PySide6.QtWidgets import QFileDialog
        pfad, _ = QFileDialog.getOpenFileName(self, "Firmenlogo wählen", "", "Bilder (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not pfad:
            return
        try:
            self._setzen(logo_aus_datei(pfad))
        except ValueError as fehler:
            QMessageBox.warning(self, "Firmenlogo", str(fehler))

    def _setzen(self, daten):
        self.anzeigen(daten)
        self.geaendert.emit(daten)


class EinstellungenSeite(QScrollArea):
    """Einstellungen als Formular; gruppen = nur diese Gruppen, ohne = diese Gruppen nicht."""

    def __init__(self, db, meldung, gruppen=None, ohne=()):
        super().__init__()
        self.db, self.meldung = db, meldung
        self.liste = [e for e in EINSTELLUNGEN if (gruppen is None or e.gruppe in gruppen) and e.gruppe not in ohne]
        self.setWidgetResizable(True)
        innen = QWidget()
        lay = QVBoxLayout(innen)
        self.felder = {}
        gruppen = {}
        for e in self.liste:
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
        elif e.art == "zahl_leer":          # Zahl, die auch leer bleiben darf (leer = keine Vorgabe)
            w = QLineEdit()
            w.setPlaceholderText("leer")
            w.setMaximumWidth(160)
            w.editingFinished.connect(lambda e=e, w=w: self._zahl_leer(e, w))
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
        elif e.art == "passwort":
            w = QLineEdit()
            w.setEchoMode(QLineEdit.PasswordEchoOnEdit)
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, w.text()))
        elif e.art == "bild":
            w = LogoEingabe()
            w.geaendert.connect(lambda daten, e=e: self._speichern(e, daten))
        else:
            w = QLineEdit()
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, w.text().strip()))
        return w

    def _zahl_leer(self, e, w):
        try:
            wert = wert_aus_text(Feld(e.name, e.titel, "zahl", e.von, e.bis), w.text())
        except ValueError as fehler:
            self.meldung(str(fehler), fehler=True)
            v = self.db.einstellung(e.name)
            w.setText(zahl_als_text(v, None, tausender=False) if v is not None else "")
            return
        self._speichern(e, wert)
        w.setText(zahl_als_text(wert, None, tausender=False) if wert is not None else "")

    def _speichern(self, e, wert):
        if getattr(self, "_laden", False) or self.db.einstellung(e.name) == wert:
            return
        self.db.einstellung_setzen(e.name, wert)
        self.meldung(f"{e.titel} gespeichert.")

    def neu_laden(self):
        self._laden = True
        k = self.db.kontext()
        for e in self.liste:
            w, v = self.felder[e.name], self.db.einstellung(e.name)
            if e.art == "anteil":
                w.setValue((v or 0) * 100)
            elif e.art == "zahl":
                w.setValue(v or 0)
            elif e.art == "zahl_leer":
                w.setText(zahl_als_text(v, None, tausender=False) if isinstance(v, (int, float)) else "")
            elif e.art == "ganz":
                w.setValue(int(v or 0))
            elif e.art == "mehrzeilig":
                w.setPlainText(v or "")
            elif e.art == "auswahl":
                w.clear()
                w.addItems(k.auswahl(e.auswahl))
                w.setCurrentText(v or "")
            elif e.art == "bild":
                w.anzeigen(v or "")
            else:
                w.setText(v or "")
        self._laden = False


class ZeitvorgabenSeite(QWidget):
    """Unterreiter 'Stundensätze und Zeitvorgaben': Stundensätze oben, Arbeitsschritte darunter."""
    titel = "Stundensätze und Zeitvorgaben"

    def __init__(self, saetze, schritte):
        super().__init__()
        self.saetze, self.schritte = saetze, schritte
        teiler = QSplitter(Qt.Vertical)
        for s in (saetze, schritte):
            box = QGroupBox(s.t.titel)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(4, 4, 4, 4)
            bl.addWidget(s)
            teiler.addWidget(box)
        teiler.setSizes([260, 420])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(teiler)

    def neu_laden(self):
        self.saetze.neu_laden()
        self.schritte.neu_laden()


class EinstellungenBereich(QWidget):
    """Reiter Einstellungen: erst Passwort, dann Unterreiter Vorgaben und Stammdaten (ohne Kunden).
    Einmal geöffnet bleibt er offen, bis 'Sperren' gedrückt oder das Programm beendet wird."""

    def __init__(self, db, vorgaben, seiten):
        super().__init__()
        self.db = db
        self.stapel = QStackedWidget()
        # Sperre
        sperre = QWidget()
        self.passwort = QLineEdit()
        self.passwort.setEchoMode(QLineEdit.Password)
        self.passwort.setPlaceholderText("Passwort")
        self.passwort.setMaximumWidth(220)
        self.passwort.returnPressed.connect(self.oeffnen)
        oeffnen = QPushButton("Einstellungen öffnen")
        oeffnen.clicked.connect(self.oeffnen)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #C00000;")
        zeile = QHBoxLayout()
        zeile.addWidget(self.passwort)
        zeile.addWidget(oeffnen)
        zeile.addStretch(1)
        ls = QVBoxLayout(sperre)
        text = QLabel("<h3>Einstellungen</h3><p>Vorgaben und Stammdaten (Profile, Werkstoffe, Oberflächen, Preise, "
                      "Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten) sind mit einem Passwort geschützt.</p>")
        text.setWordWrap(True)
        ls.addWidget(text)
        ls.addLayout(zeile)
        ls.addWidget(self.fehler)
        ls.addStretch(1)
        # Inhalt
        inhalt = QWidget()
        self.unter = QTabWidget()
        self.unter.addTab(vorgaben, "Vorgaben")
        for s in seiten:
            self.unter.addTab(s, getattr(s, "titel", None) or s.t.titel)
        self.unter.currentChanged.connect(lambda _: self.neu_laden())
        sperren = QPushButton("Einstellungen sperren")
        sperren.clicked.connect(self.sperren)
        oben = QHBoxLayout()
        oben.addStretch(1)
        oben.addWidget(sperren)
        li = QVBoxLayout(inhalt)
        li.setContentsMargins(0, 0, 0, 0)
        li.addLayout(oben)
        li.addWidget(self.unter, 1)
        self.stapel.addWidget(sperre)
        self.stapel.addWidget(inhalt)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stapel)
        self.offen = False
        self.sperren()

    def gesperrt(self):
        return not self.offen and bool(self.db.einstellung("passwort"))

    def oeffnen(self, passwort=None):
        """Mit dem Passwort aus dem Eingabefeld (oder dem übergebenen) öffnen. Ergebnis: geöffnet ja/nein."""
        text = self.passwort.text() if passwort is None or isinstance(passwort, bool) else passwort
        soll = self.db.einstellung("passwort") or ""
        self.passwort.clear()
        if soll and text != soll:
            self.fehler.setText("Passwort falsch.")
            return False
        self.offen = True
        self.fehler.clear()
        self.stapel.setCurrentIndex(1)
        self.neu_laden()
        return True

    def sperren(self):
        self.offen = False
        self.stapel.setCurrentIndex(1 if not self.gesperrt() else 0)

    def zeigen(self, seite):
        """Unterreiter auswählen (z. B. Vorgaben oder eine Stammdatenseite)."""
        self.unter.setCurrentWidget(seite)

    def neu_laden(self):
        if self.gesperrt():
            self.stapel.setCurrentIndex(0)
            self.passwort.setFocus()
            return
        self.stapel.setCurrentIndex(1)
        w = self.unter.currentWidget()
        if hasattr(w, "neu_laden"):
            w.neu_laden()


class StartSeite(QWidget):
    def __init__(self, fenster):
        super().__init__()
        self.f = fenster
        titel = QLabel(f"<h2>{NAME}</h2><p>Version {update.stand_text(fenster.updater.lokal)}</p>")
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        knoepfe = QHBoxLayout()
        for text, ziel in (("Datensicherung erstellen", fenster.sicherung_erstellen),
                           ("Sicherung wiederherstellen …", fenster.wiederherstellen_dialog),
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
            warnung = ("<p style='color:#C00000'><b>Die Stammdaten sind Beispielwerte.</b> Bitte im Reiter "
                       "Einstellungen durch die eigenen Werte ersetzen.</p>")
        self.info.setText(f"<p>Datendatei: {db.pfad}{self.f.datenort_text()}</p><p>Stammdaten: {herkunft} (Stand {stand})</p>{warnung}"
                          f"<table cellpadding='2'>{zeilen}</table>")


class Hauptfenster(QMainWindow):
    def __init__(self, db, programmordner=None, stumm=False, orte=None):
        from .angebot_fenster import AngeboteSeite
        super().__init__()
        self.db = db
        self.programmordner = Path(programmordner or Path(__file__).resolve().parent.parent)
        self.orte = orte            # orte.Orte (Datenort portabel/installiert, Vorgabe der Ablage) oder None
        self.stumm = stumm          # Selbsttest: keine Rückfragen und Meldungsfenster
        self.offen = {}             # Angebots-ID -> AngebotSeite
        from .update_fenster import Updater
        self.updater = Updater(self, os.environ.get("RL_UPDATE_QUELLE") or update.ADRESSE)
        self.setWindowTitle(f"{NAME} {update.stand_text(self.updater.lokal)}")
        self.setStyleSheet(STIL)
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
        for s in self.seiten:           # Kunden als eigener Reiter, die übrigen Stammdaten unter Einstellungen
            if s.t.name == "kunden":
                self.reiter.addTab(s, s.t.titel)
        self.einstellungen = EinstellungenSeite(db, self.meldung, ohne=("Frachtkosten",))
        seite = {s.t.name: s for s in self.seiten}
        self.zeitvorgaben = ZeitvorgabenSeite(seite["stundensaetze"], seite["arbeitsschritte"])
        # Zusatzarbeiten: eigene Verwaltung (Übersicht, Formular, Preisvorschau) statt der Stammdatentabelle
        from .zusatz_verwaltung import ZusatzVerwaltung
        self.zusatz = ZusatzVerwaltung(db, self.meldung)
        unter = [self.zusatz if s.t.name == "zusatzarbeiten" else s for s in self.seiten
                 if s.t.name not in ("kunden", "stundensaetze", "arbeitsschritte")]
        self.bereich = EinstellungenBereich(db, self.einstellungen, unter + [self.zeitvorgaben])
        from .fracht_seite import FrachtBereich
        self.fracht = FrachtBereich(self)
        self.reiter.addTab(self.fracht, "Frachtkosten")
        # Zukaufartikel: eigener Reiter (Artikel, Kategorien, Lieferanten), tägliche Arbeit ohne Passwort
        from .zukauf_seite import ZukaufBereich
        self.zukauf = ZukaufBereich(db, self.meldung)
        self.reiter.addTab(self.zukauf, self.zukauf.titel)
        self.reiter.addTab(self.bereich, "Einstellungen")
        for i in range(self.reiter.count()):     # feste Reiter ohne Schließen-Knopf
            self.reiter.tabBar().setTabButton(i, QTabBar.RightSide, None)
        self.reiter.currentChanged.connect(self.reiter_gewechselt)
        self.setCentralWidget(self.reiter)
        self._menue()
        self.statusBar().showMessage("Bereit")
        if not stumm:
            self.updater.beim_start()

    def starten(self):
        """Programmstart: Fenster maximiert (mit Taskleiste) und gleich im Reiter Angebote."""
        self.reiter.setCurrentWidget(self.angebote)
        self.showMaximized()

    def _menue(self):
        datei = self.menuBar().addMenu("&Datei")
        for text, ziel, taste in (("Datensicherung erstellen", self.sicherung_erstellen, None),
                                  ("Sicherung wiederherstellen …", self.wiederherstellen_dialog, None),
                                  (None, None, None),
                                  ("Daten exportieren …", self.daten_exportieren, None),
                                  ("Daten importieren …", self.daten_importieren, None),
                                  (None, None, None),
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
        bearbeiten = self.menuBar().addMenu("&Bearbeiten")
        self.kuerzel_aktionen = {}
        for name, text, tasten in (("rueckgaengig", "Rückgängig", [QKeySequence.Undo]),
                                   ("wiederholen", "Wiederholen", ["Ctrl+Y", "Ctrl+Shift+Z"]),
                                   (None, None, None),
                                   ("ausschneiden", "Ausschneiden", [QKeySequence.Cut]),
                                   ("kopieren", "Kopieren", [QKeySequence.Copy]),
                                   ("einfuegen", "Einfügen", [QKeySequence.Paste]),
                                   ("loeschen", "Löschen …", [QKeySequence.Delete]),
                                   (None, None, None),
                                   ("neu", "Neu", [QKeySequence.New]),
                                   ("suchen", "Suchen", [QKeySequence.Find]),
                                   ("speichern", "Eingabe speichern", [QKeySequence.Save]),
                                   ("aktualisieren", "Aktualisieren", ["F5"]),
                                   (None, None, None),
                                   ("optimieren", "Optimieren", ["F9"]),
                                   ("importieren", "STEP importieren …", ["Ctrl+I"]),
                                   ("drucken", "Angebot (PDF)", [QKeySequence.Print]),
                                   ("schliessen", "Angebot schließen", ["Ctrl+W", "Ctrl+F4"])):
            if name is None:
                bearbeiten.addSeparator()
                continue
            a = QAction(text, self)
            a.setShortcuts([QKeySequence(t) for t in tasten])
            a.triggered.connect(lambda _=False, name=name: self.kuerzel(name))
            bearbeiten.addAction(a)
            self.kuerzel_aktionen[name] = a
        ansicht = self.menuBar().addMenu("&Ansicht")
        for text, taste, schritt, innen in (("Nächster Reiter", "Ctrl+Tab", 1, False),
                                            ("Vorheriger Reiter", "Ctrl+Shift+Tab", -1, False),
                                            ("Nächster Unterreiter", "Ctrl+PgDown", 1, True),
                                            ("Vorheriger Unterreiter", "Ctrl+PgUp", -1, True)):
            a = QAction(text, self)
            a.setShortcut(QKeySequence(taste))
            a.triggered.connect(lambda _=False, schritt=schritt, innen=innen: self.reiter_weiter(schritt, innen))
            ansicht.addAction(a)
        hilfe = self.menuBar().addMenu("&Hilfe")
        a = QAction("Bedienungsanleitung (PDF)", self)
        a.setShortcut(QKeySequence.HelpContents)
        a.triggered.connect(self.anleitung_oeffnen)
        hilfe.addAction(a)
        a = QAction("Tastenkürzel …", self)
        a.triggered.connect(self.kuerzel_zeigen)
        hilfe.addAction(a)
        a = QAction("Nach Updates suchen …", self)
        a.triggered.connect(lambda: self.updater.suchen())
        hilfe.addAction(a)
        a = QAction("Über …", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, NAME, f"<b>{NAME}</b> {update.stand_text(self.updater.lokal)}<br>Angebotskalkulation und Materialoptimierung für Rohrlaserteile.<br>"
                        f"Daten: {self.db.pfad}{self.datenort_text()}"))
        hilfe.addAction(a)

    # -------------------------------------------------------------- Tastenkürzel
    def _seite(self):
        """Innerste sichtbare Seite des aktuellen Reiters (Unterreiter von Einstellungen, Zukauf, Fracht)."""
        w = self.reiter.currentWidget()
        while hasattr(getattr(w, "unter", None), "currentWidget") and w.unter.currentWidget() is not None:
            w = w.unter.currentWidget()
        return w

    def kuerzel(self, name):
        """Tastenkürzel ausführen: zuerst die Seite, in der der Fokus steht (von innen nach außen), sonst die
        sichtbare Seite. Ergebnis: True, wenn eine Seite das Kürzel ausgeführt hat."""
        from PySide6.QtWidgets import QApplication
        fokus = QApplication.focusWidget()
        if fokus is not None and not self.isAncestorOf(fokus):
            fokus = None
        if name == "speichern":
            return self._eingabe_abschliessen(fokus)
        if name == "kopieren" and tastatur.ist_tabelle(fokus):
            n = len(tastatur.kopieren(fokus).splitlines())
            self.meldung(f"{n} Zeile(n) kopiert." if n else "Nichts markiert.")
            return bool(n)
        if name == "schliessen":
            seite = self.reiter.currentWidget()
            for aid, s in list(self.offen.items()):
                if s is seite:
                    self.angebot_schliessen(aid)
                    return True
            return False
        kette, w = [], fokus
        while w is not None and w is not self:
            kette.append(w)
            w = w.parentWidget()
        w = self._seite()               # danach die sichtbare Seite (Fokus z. B. auf der Reiterleiste)
        while w is not None and w is not self:
            if w not in kette:
                kette.append(w)
            w = w.parentWidget()
        for w in kette:
            if self._kuerzel_auf(w, name, fokus):
                return True
        if name in ("einfuegen", "ausschneiden") and tastatur.ist_tabelle(fokus):
            if name == "ausschneiden":
                tastatur.kopieren(fokus)
            n = tastatur.einfuegen(fokus) if name == "einfuegen" else tastatur.leeren(fokus)
            self.meldung(f"{n} Zelle(n) geändert." if n else "Keine bearbeitbare Zelle.", fehler=not n)
            return bool(n)
        if name == "aktualisieren":
            for w in kette:
                if hasattr(w, "neu_laden"):
                    w.neu_laden()
                    self.meldung("Aktualisiert.")
                    return True
        if name == "suchen":
            for w in kette:
                if isinstance(getattr(w, "suche", None), QLineEdit):
                    w.suche.setFocus()
                    w.suche.selectAll()
                    return True
        hinweis = {"rueckgaengig": "Rückgängig gibt es im geöffneten Angebot.",
                   "wiederholen": "Wiederholen gibt es im geöffneten Angebot.",
                   "loeschen": "Bitte zuerst in einer Tabelle markieren, was gelöscht werden soll."}
        self.meldung(hinweis.get(name, "Dieses Tastenkürzel gilt hier nicht."), fehler=True)
        return False

    def reiter_weiter(self, schritt, innen=False):
        """Strg+Tab: Hauptreiter wechseln; Strg+Bild↓/↑ (wie Blätter in Excel): Unterreiter der Seite, in der
        der Fokus steht (z. B. Positionen, Kalkulation, Staffeln im Angebot)."""
        from PySide6.QtWidgets import QApplication
        reiter = self.reiter
        if innen:
            w = QApplication.focusWidget()
            if w is None or not self.reiter.currentWidget().isAncestorOf(w):
                w = self._seite()
            ziel = None
            while w is not None and w is not self.reiter:
                if isinstance(w, QTabWidget):
                    ziel = w
                    break
                w = w.parentWidget()
            if ziel is None:            # Fokus außerhalb: erster Unterreiter der sichtbaren Seite
                ziel = next((t for t in self.reiter.currentWidget().findChildren(QTabWidget) if t.isVisible()), None)
            if ziel is None:
                return None
            reiter = ziel
        if reiter.count():
            reiter.setCurrentIndex((reiter.currentIndex() + schritt) % reiter.count())
        return reiter

    def _kuerzel_auf(self, w, name, fokus):
        ziel = getattr(w, "KUERZEL", {}).get(name)
        if ziel is None:
            return False
        if isinstance(ziel, tuple):             # nur, wenn der Fokus in dieser Tabelle steht
            ziel, tabelle = ziel
            if fokus is None or fokus is not getattr(w, tabelle, None):
                return False
        ergebnis = getattr(w, ziel)()
        return ergebnis is not False

    def _eingabe_abschliessen(self, fokus):
        """Strg+S: offene Eingabe übernehmen (Zelle, Textfeld). Gespeichert wird ohnehin jede Eingabe sofort."""
        if fokus is not None:
            ansicht = fokus.parentWidget()
            while ansicht is not None and not tastatur.ist_tabelle(ansicht):
                ansicht = ansicht.parentWidget()
            fokus.clearFocus()          # Zelleneditor und Textfelder speichern beim Verlassen
            (ansicht or fokus).setFocus()
        self.meldung("Gespeichert – das Programm speichert jede Eingabe sofort.")
        return True

    def kuerzel_zeigen(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        d = QDialog(self)
        d.setWindowTitle("Tastenkürzel")
        zeilen = "".join(f"<tr><td><b>{t}</b></td><td>{w}</td><td style='color:#5F6B7A'>{o}</td></tr>"
                         for t, w, o in tastatur.UEBERSICHT)
        text = QLabel(f"<table cellpadding='3'><tr><th align='left'>Taste</th><th align='left'>Wirkung</th>"
                      f"<th align='left'>Wo</th></tr>{zeilen}</table><p>In Textfeldern wirken Strg+Z, Strg+C, "
                      "Strg+V, Strg+X und Entf wie gewohnt im Text.</p>")
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        lay.addWidget(text)
        lay.addWidget(knoepfe)
        if not self.stumm:
            d.exec()
        return d

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

    def zeigen(self, seite):
        """Reiter oder Unterreiter der Einstellungen anzeigen (gesperrt: erst die Passwortabfrage)."""
        if seite in (self.zeitvorgaben.saetze, self.zeitvorgaben.schritte):
            seite = self.zeitvorgaben
        if getattr(seite, "t", None) is not None and seite.t.name == "zusatzarbeiten":
            seite = self.zusatz
        if self.bereich.unter.indexOf(seite) >= 0:
            self.bereich.zeigen(seite)
            seite = self.bereich
        self.reiter.setCurrentWidget(seite)

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
        self.zukauf.neu_laden()
        self.zusatz.neu_laden()
        self.einstellungen.neu_laden()
        self.fracht.neu_laden()

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
        pfade, fehler = self.db.sicherungen()
        if fehler:
            self.meldung(fehler, fehler=True)
            if not self.stumm:
                QMessageBox.warning(self, "Datensicherung", f"Sicherung erstellt: {pfade[0]}\n\n{fehler}")
        else:
            self.meldung("Sicherung erstellt: " + " und ".join(str(p) for p in pfade))
        return pfade

    def closeEvent(self, ereignis):
        """Beim Beenden eine Sicherung (eine je Tag, wird überschrieben), auch in den zweiten Sicherungsordner."""
        if not self.stumm:
            try:
                _, fehler = self.db.sicherungen(zusatz="beenden")
            except OSError as e:
                fehler = str(e)
            if fehler and QMessageBox.warning(
                    self, "Datensicherung", f"Die Sicherung beim Beenden ist nicht vollständig:\n\n{fehler}\n\n"
                    "Trotzdem beenden?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                ereignis.ignore()
                return
        super().closeEvent(ereignis)

    def datenort_text(self):
        """' (portabel)' bzw. ' (installiert)' hinter dem Pfad der Datendatei."""
        return f" ({self.orte.art})" if self.orte else ""

    def wiederherstellen_dialog(self):
        from .sicherung_dialog import WiederherstellenDialog
        d = WiederherstellenDialog(self)
        if d.exec() and d.gewaehlt:
            self.daten_ersetzen(d.gewaehlt)

    def daten_exportieren(self):
        from PySide6.QtWidgets import QFileDialog
        vorschlag = self.ablage() / f"Rohrlaser-Daten {datetime.date.today():%Y-%m-%d}.zip"
        ziel, _ = QFileDialog.getSaveFileName(self, "Daten exportieren", str(vorschlag), "Export-Datei (*.zip)")
        if ziel:
            self.export_schreiben(ziel)

    def export_schreiben(self, ziel):
        try:
            info = self.db.exportieren(ziel)
        except (OSError, RuntimeError) as e:
            self.meldung(f"Export nicht gelungen: {e}", fehler=True)
            if not self.stumm:
                QMessageBox.warning(self, "Daten exportieren", f"Der Export ist nicht gelungen:\n\n{e}")
            return None
        self.meldung(f"Daten exportiert: {ziel} ({info['anzahl'].get('angebote', 0)} Angebote)")
        if not self.stumm:
            QMessageBox.information(self, "Daten exportieren",
                                    f"Alle Daten stehen in\n{ziel}\n\n{info['anzahl'].get('angebote', 0)} Angebote, "
                                    f"{info['anzahl'].get('positionen', 0)} Positionen. Mit „Daten importieren …“ "
                                    "lassen sie sich in der portablen oder installierten Version oder auf einem "
                                    "anderen Rechner einlesen.")
        return info

    def daten_importieren(self):
        from PySide6.QtWidgets import QFileDialog
        datei, _ = QFileDialog.getOpenFileName(self, "Daten importieren", str(self.ablage()),
                                               "Export, Sicherung oder Datendatei (*.zip *.db)")
        if datei:
            self.daten_ersetzen(datei, zusatz="vor_Import")

    def daten_ersetzen(self, quelle, zusatz="vor_Wiederherstellung"):
        """Alle Daten durch eine Sicherung, Datendatei oder Export-Datei ersetzen (vorher Sicherung des jetzigen
        Stands). Offene Angebote werden geschlossen und alles neu geladen. Ergebnis: info oder None."""
        from .datenbank import datei_info
        if Path(quelle).resolve() == self.db.pfad.resolve():
            self.meldung("Das ist die Datendatei, mit der das Programm gerade arbeitet.", fehler=True)
            return None
        if not self.stumm:
            try:
                i = datei_info(quelle) if Path(quelle).suffix.lower() == ".db" else None
            except Exception:
                i = None
            inhalt = (f"\n\nInhalt: {i['anzahl'].get('angebote', 0)} Angebote, letzte Änderung "
                      f"{i.get('letzte_aenderung') or '–'}." if i else "")
            if QMessageBox.question(
                    self, "Daten ersetzen", f"Alle Daten (Stammdaten, Einstellungen, Angebote) durch\n{quelle}\n"
                    f"ersetzen?{inhalt}\n\nDer jetzige Stand wird vorher gesichert (Sicherung …_{zusatz}) und lässt "
                    "sich damit zurückholen.", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return None
        for aid in list(self.offen):
            self.angebot_schliessen(aid)
        try:
            info, vorher = self.db.wiederherstellen(quelle, zusatz=zusatz)
        except (OSError, RuntimeError) as e:
            self.meldung(f"Nicht ersetzt: {e}", fehler=True)
            if not self.stumm:
                QMessageBox.warning(self, "Daten ersetzen", f"Die Daten wurden nicht ersetzt:\n\n{e}")
            return None
        self.alles_neu_laden()
        self.meldung(f"Daten ersetzt aus {Path(quelle).name}; der vorige Stand liegt in {vorher.name}.")
        if not self.stumm:
            QMessageBox.information(self, "Daten ersetzt", f"Die Daten stammen jetzt aus\n{quelle}\n\n"
                                    f"Der vorige Stand ist gesichert:\n{vorher}")
        return info

    def datenordner_oeffnen(self):
        self.datei_oeffnen(self.db.pfad.parent)

    def ablage(self):
        """Ordner für PDF und CSV-Export (Einstellung 'Ablageordner', sonst portabel 'Angebote' neben dem Programm,
        installiert Dokumente\\Rohrlaser Angebote)."""
        vorgabe = self.orte.ablage if self.orte else self.programmordner / ausgabe.ABLAGE
        return ausgabe.ablageordner(self.db.einstellung("ablageordner"), vorgabe)

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
