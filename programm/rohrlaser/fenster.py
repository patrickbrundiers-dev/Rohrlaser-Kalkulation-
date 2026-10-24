"""Hauptfenster: Start, Angebote (Übersicht und je offenes Angebot ein Reiter), Kunden, Frachtkosten,
Zukaufartikel und Einstellungen.

Der Reiter Einstellungen ist mit einem Passwort geschützt (Einstellung 'passwort') und enthält als Unterreiter die
allgemeinen Vorgaben und alle Stammdaten außer den Kunden. Im Reiter Frachtkosten ist der Rechner frei, die
Pflegebereiche öffnen mit demselben Passwort.

Lizenz (lizenz.py): Hauptfenster(…, lizenz=LizenzStelle) zeigt Hinweise in der Statusleiste, Hilfe → Lizenz …, und
schaltet im Lesemodus die ändernden Aktionen ab; mit der Admin-Lizenz (Admin-Passwort beim Start) öffnen die Einstellungen ohne Passwort. Ohne
lizenz (Tests, Entwicklung) voller Zugriff ohne Hinweise."""
import datetime
import os
import re
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QTimer, QUrl, Signal
from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QAction, QBrush, QDesktopServices, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QStackedWidget, QStyledItemDelegate, QTableView, QTabWidget, QVBoxLayout, QWidget)

from . import stil
from . import NAME, VERSION, ausgabe, hilfe, pdf, tastatur, teilen, update
from .angebot import kuerzel_sauber
from .spaltenbreite import AutoGroesse
from .einstellungen_nav import NavigationsReiter
from .hauptreiter import HauptReiter
from .stil import AKZENT, STIL  # noqa: F401 – Stilwerte zentral in stil.py
from .stammdaten import LASER, TABELLEN, EINSTELLUNGEN, Feld, pruefen, wert_aus_text, wert_als_text, zahl_als_text

ANLEITUNG = "Bedienungsanleitung.pdf"
KURZANLEITUNG = "Kurzanleitung.pdf"
FARBE_EINGABE = stil.farbe_fest("#FFFCF0")   # Eingabefelder (dezent gelb, Layout-Plan L3)
FARBE_BERECHNET = stil.farbe_fest("#EDEDED")
# Prüfstatus: nur Auffälliges ist farbig (FEHLER rot, WARNUNG gelb), OK bleibt neutral grau
FARBE_STATUS = {"FEHLER": stil.farbe_fest("#F8CBAD"), "WARNUNG": stil.farbe_fest("#FFD966"), "OK": FARBE_BERECHNET}


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
    Zeilen mit genau diesem Wert (z. B. Preisstaffeln eines Tarifs). nur_auffaellig = Spalte der Prüfung: nur Zeilen
    mit FEHLER oder WARNUNG."""
    fest = None
    nur_auffaellig = None

    def filterAcceptsRow(self, zeile, eltern):
        if self.fest is not None:
            spalte, wert = self.fest
            if self.sourceModel().roh(zeile, spalte) != wert:
                return False
        if self.nur_auffaellig is not None:
            if not str(self.sourceModel().roh(zeile, self.nur_auffaellig) or "").startswith(("FEHLER", "WARNUNG")):
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
            cb.setEditable(f.auswahl not in ("preisbasis", "profilform", "zusatzart", "janein", "materialherkunft",
                                              "zeugnis"))
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

        self.hinweis = hilfe.Hinweis(tabelle.hinweis, db, f"tabelle:{tabelle.name}")
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
        self.pruefspalte = next((i for i, (art, _) in enumerate(self.modell.spalten) if art == "pruefung"), None)
        self.nur_fehler = QCheckBox("Nur Fehler und Warnungen")
        self.nur_fehler.setToolTip("Nur Zeilen zeigen, deren Prüfung FEHLER oder WARNUNG meldet")
        self.nur_fehler.toggled.connect(self.fehler_filtern)
        self.nur_fehler.setVisible(self.pruefspalte is not None)
        leiste = QHBoxLayout()
        for w in (neu, weg):
            leiste.addWidget(w)
        if tabelle.name == "schneiddaten":
            standard = QPushButton("Auf Standard zurücksetzen …")
            standard.setToolTip("Schneiddaten einer Maschine oder aller Maschinen durch die mitgelieferten "
                                "Richtwerte ersetzen")
            standard.clicked.connect(self.schneiddaten_zuruecksetzen)
            leiste.addWidget(standard)
        if tabelle.name in ("schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren"):
            richt = QPushButton("Richtwerte laden")
            richt.setToolTip("Fehlende Schweißverfahren, Kennwerte und Faktoren als Richtwerte eintragen; vorhandene "
                             "Zeilen bleiben unverändert")
            richt.clicked.connect(lambda: self.schweiss_richtwerte())
            leiste.addWidget(richt)
        if tabelle.name == "schweiss_kennwerte":
            lernen = QPushButton("Kennwerte aus Nachkalkulation …")
            lernen.setToolTip("Vorschläge Ist ÷ Soll aus nachkalkulierten Schweißbaugruppen prüfen, mit Begründung "
                              "freigeben oder frühere Freigaben zurücknehmen")
            lernen.clicked.connect(lambda: self.kennwerte_lernen())
            leiste.addWidget(lernen)
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
        if tabelle.name == "profile":
            rp = QPushButton("RP-Profile aus MegaCAD laden …")
            rp.setToolTip("RP-Profile (Rohre mit Anschlag) aus MegaCAD-Makros (.mac) einlesen: Profil-ID 'RP ' + "
                          "Dateiname, Maße, Fläche und Schnittlänge aus der Kontur. Die mitgelieferte Bibliothek "
                          "RP-ROHRE ist schon eingetragen.")
            rp.clicked.connect(self.rp_laden)
            quer = QPushButton("RP-Querschnitt …")
            quer.setToolTip("Querschnitt und Kennwerte des gewählten RP-Profils zeigen")
            quer.clicked.connect(self.rp_querschnitt)
            leiste.addWidget(rp)
            leiste.addWidget(quer)
        leiste.addSpacing(20)
        leiste.addWidget(self.suche, 1)
        leiste.addWidget(self.nur_fehler)
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
        lay.addWidget(self.hinweis)
        lay.addLayout(leiste)
        lay.addWidget(self.ansicht, 1)
        self.modell.modelReset.connect(self.zaehlen)
        self.zaehlen()

    def doppelklick_setzen(self, aktion, tooltip):
        """Doppelklick auf eine Zeile ruft aktion(Zeile als dict) auf statt die Zelle zu bearbeiten (Tippen und F2
        bearbeiten weiter)."""
        self.ansicht.setEditTriggers(QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)
        self.ansicht.setToolTip(tooltip)
        self.ansicht.doubleClicked.connect(
            lambda i: aktion(self.modell.daten[self.filter.mapToSource(i).row()]) if i.isValid() else None)

    def zaehlen(self):
        if self.filter.fest is not None:
            spalte, wert = self.filter.fest
            zeilen = [r for r in range(len(self.modell.daten)) if self.modell.roh(r, spalte) == wert]
        else:
            zeilen = range(len(self.modell.daten))
        status = [str(self.modell.roh(r, self.pruefspalte)) if self.pruefspalte is not None else "" for r in zeilen]
        fehler = sum(1 for t in status if t.startswith("FEHLER"))
        warnung = sum(1 for t in status if t.startswith("WARNUNG"))
        teile = [f"{fehler} mit FEHLER"] * bool(fehler) + [f"{warnung} mit WARNUNG"] * bool(warnung)
        self.anzahl.setText(f"{len(status)} Zeilen" + "".join(", " + t for t in teile))

    def fehler_filtern(self, an):
        """Nur Zeilen mit FEHLER oder WARNUNG zeigen (an) oder wieder alle."""
        self.filter.nur_auffaellig = self.pruefspalte if an else None
        self.filter.invalidateFilter()

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

    def rp_laden(self, pfade=None):
        """MegaCAD-Makros als RP-Profile einlesen (rp_dialog.makros_laden). Ergebnis: (neu, geändert, Meldungen)."""
        from .rp_dialog import makros_laden
        erg = makros_laden(self, self.db, pfade)
        if erg is None:
            return None
        neu, geaendert, meldungen = erg
        if neu or geaendert:
            f = self.window()
            f.alles_neu_laden() if hasattr(f, "alles_neu_laden") else self.neu_laden()
        text = f"RP-Profile: {neu} neu, {geaendert} geändert"
        if meldungen:
            text += f", {len(meldungen)} nicht übernommen ({'; '.join(meldungen[:3])}{' …' * (len(meldungen) > 3)})"
        self.meldung(text + ".", fehler=bool(meldungen) and not (neu or geaendert))
        return erg

    def rp_querschnitt(self, stumm=False):
        """Querschnitt des gewählten RP-Profils zeigen (rp_dialog.querschnitt_zeigen)."""
        from .rp_dialog import querschnitt_zeigen
        z = self.ausgewaehlt()
        return querschnitt_zeigen(self, (z or {}).get("profil_id", ""), stumm)

    def schweiss_richtwerte(self, bestaetigt=None):
        """Fehlende Richtwerte der Schweiß-Stammdaten eintragen (baugruppe.richtwerte_fehlend); vorhandene Zeilen
        bleiben, wie sie sind. bestaetigt: Antwort auf die Rückfrage (Tests). Ergebnis: Anzahl neuer Zeilen."""
        from . import baugruppe
        fehlt = baugruppe.richtwerte_fehlend(self.db.tabellen())
        n = sum(len(z) for z in fehlt.values())
        if not n:
            self.meldung("Alle Richtwerte sind schon eingetragen; vorhandene Zeilen werden nicht geändert.")
            return 0
        if bestaetigt is None:
            text = (f"{len(fehlt['schweissverfahren'])} Schweißverfahren, {len(fehlt['schweiss_kennwerte'])} "
                    f"Kennwerte und {len(fehlt['schweiss_faktoren'])} Faktoren fehlen und werden als Richtwerte "
                    "eingetragen (Status Richtwert). Vorhandene Zeilen bleiben unverändert.\n\nRichtwerte sind aus "
                    "dem Nahtquerschnitt hergeleitet, keine Erfahrungswerte der eigenen Fertigung: bitte prüfen und "
                    "danach auf 'geprüft' stellen.\n\nJetzt eintragen?")
            bestaetigt = QMessageBox.question(self, "Richtwerte laden", text, QMessageBox.Yes | QMessageBox.No,
                                              QMessageBox.Yes) == QMessageBox.Yes
        if not bestaetigt:
            return 0
        for name in ("schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren"):    # Verfahren zuerst (Verweis)
            for z in fehlt[name]:
                self.db.neu(name, z)
        f = self.window()
        f.alles_neu_laden() if hasattr(f, "alles_neu_laden") else self.neu_laden()
        self.meldung(f"Richtwerte geladen: {n} Zeile(n) neu, vorhandene unverändert.")
        return n

    def kennwerte_lernen(self, dialog=None):
        """Fenster Kennwerte aus der Nachkalkulation (kennwerte_dialog); dialog(d) statt exec (Tests)."""
        from .kennwerte_dialog import KennwerteDialog
        d = KennwerteDialog(self, self.db)
        dialog(d) if dialog else d.exec()
        if d.geaendert:
            f = self.window()
            f.alles_neu_laden() if hasattr(f, "alles_neu_laden") else self.neu_laden()
        return d

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


class PasswortEingabe(QWidget):
    """Einstellung 'passwort': gespeichert ist nur der Hash (passwort.py), das Feld bleibt deshalb leer. Ein neu
    eingegebenes Passwort ersetzt das alte, 'Entfernen' = ohne Passwort. geaendert(text) mit dem neuen Passwort oder ''."""
    geaendert = Signal(str)

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.feld = QLineEdit()
        self.feld.setEchoMode(QLineEdit.Password)
        self.feld.editingFinished.connect(self._neu)
        self.weg = QPushButton("Entfernen")
        self.weg.setToolTip("Einstellungen ohne Passwort öffnen (auch keine Admin-Abfrage beim Start)")
        self.weg.clicked.connect(lambda: self.geaendert.emit(""))
        lay.addWidget(self.feld, 1)
        lay.addWidget(self.weg)

    def _neu(self):
        text = self.feld.text()
        self.feld.clear()
        if text:
            self.geaendert.emit(text)

    def anzeigen(self, gesetzt):
        self.feld.clear()
        self.feld.setPlaceholderText("gesetzt – zum Ändern neues Passwort eingeben" if gesetzt else "ohne Passwort")
        self.weg.setEnabled(bool(gesetzt))


class OrdnerEingabe(QWidget):
    """Einstellung 'ordner': Pfad, 'Ordner wählen …' und 'Leeren'. geaendert(pfad) mit dem Ordner oder ''."""
    geaendert = Signal(str)

    def __init__(self, titel):
        super().__init__()
        self.titel = titel
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.pfad = QLineEdit()
        self.pfad.setPlaceholderText("zuletzt benutzter Ordner")
        self.pfad.editingFinished.connect(lambda: self.geaendert.emit(self.pfad.text().strip()))
        waehlen, weg = QPushButton("Ordner wählen …"), QPushButton("Leeren")
        waehlen.clicked.connect(self._waehlen)
        weg.clicked.connect(lambda: self._setzen(""))
        lay.addWidget(self.pfad, 1)
        lay.addWidget(waehlen)
        lay.addWidget(weg)

    def anzeigen(self, pfad):
        self.pfad.setText(pfad or "")

    def _waehlen(self):
        from PySide6.QtWidgets import QFileDialog
        pfad = QFileDialog.getExistingDirectory(self, self.titel, self.pfad.text().strip())
        if pfad:
            self._setzen(str(Path(pfad)))

    def _setzen(self, pfad):
        self.anzeigen(pfad)
        self.geaendert.emit(pfad)


class EinstellungenSeite(QScrollArea):
    """Einstellungen als Formular; gruppen = nur diese Gruppen, ohne = diese Gruppen nicht. Jede Gruppe ist eine
    Karte; ab ZWEI_SPALTEN px Breite stehen die Karten in zwei Spalten (auf die kürzere Spalte verteilt)."""
    ZWEI_SPALTEN = 1150
    BREITE_ZAHL, BREITE_TEXT, BREITE_TITEL = 160, 380, 300

    def __init__(self, db, meldung, gruppen=None, ohne=()):
        super().__init__()
        self.db, self.meldung = db, meldung
        self.liste = [e for e in EINSTELLUNGEN if (gruppen is None or e.gruppe in gruppen) and e.gruppe not in ohne]
        self.setWidgetResizable(True)
        innen = QWidget()
        lay = QHBoxLayout(innen)
        self.spalten = [QVBoxLayout(), QVBoxLayout()]
        for sp in self.spalten:
            sp.setSpacing(10)
            lay.addLayout(sp, 1)
        self.felder = {}
        gruppen = {}
        self.boxen = []
        self.zeilen = []            # (Einstellung, Formular, Zeile, Karte) für die Suche (filtern)
        for e in self.liste:
            if e.gruppe not in gruppen:
                box = QGroupBox(e.gruppe)
                gruppen[e.gruppe] = QFormLayout(box)
                gruppen[e.gruppe].setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.boxen.append(box)
            w = self._eingabe(e)
            self.felder[e.name] = w
            titel = QLabel(self._kurztitel(e, w))
            titel.setToolTip(e.titel)
            titel.setWordWrap(True)
            titel.setFixedWidth(self.BREITE_TITEL)
            form = gruppen[e.gruppe]
            self.zeilen.append((e, form, form.rowCount(), form.parentWidget()))
            gruppen[e.gruppe].addRow(titel, w)
        if "STEP-Import" in gruppen:
            knopf = QPushButton("Zwischenspeicher leeren")
            knopf.setToolTip("Gemerkte Messungen löschen: der nächste STEP-Import misst alle Dateien neu")
            knopf.clicked.connect(self._step_cache_leeren)
            knopf.setMaximumWidth(self.BREITE_ZAHL + 60)
            gruppen["STEP-Import"].addRow("", knopf)
        self.zweispaltig = None
        self._anordnen(False)
        self.setWidget(innen)
        self.neu_laden()

    schluessel = "vorgaben"     # Navigation der Einstellungen (einstellungen_nav.GRUPPEN)

    def filtern(self, suche):
        """Suche der Einstellungen: nur passende Einstellungen und Karten zeigen (leer = alle)."""
        from .einstellungen_nav import passt
        sichtbar = {}
        for e, form, zeile, box in self.zeilen:
            ja = not suche.strip() or passt(f"{e.titel} {e.gruppe}", suche)
            form.setRowVisible(zeile, ja)
            sichtbar[id(box)] = sichtbar.get(id(box), False) or ja
        for box in self.boxen:
            box.setVisible(sichtbar.get(id(box), True))

    def _anordnen(self, zwei):
        """Karten auf eine oder zwei Spalten verteilen (Reihenfolge bleibt, je Karte in die kürzere Spalte)."""
        if zwei == self.zweispaltig:
            return
        self.zweispaltig = zwei
        for sp in self.spalten:
            while sp.count():
                sp.takeAt(0)
        hoehe = [0, 0]
        for box in self.boxen:
            i = hoehe.index(min(hoehe)) if zwei else 0
            self.spalten[i].addWidget(box)
            hoehe[i] += box.sizeHint().height()
        for sp in self.spalten:
            sp.addStretch(1)

    def resizeEvent(self, e):
        self._anordnen(self.viewport().width() >= self.ZWEI_SPALTEN)
        super().resizeEvent(e)

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
            w.setEditable(e.auswahl != "hilfeart")
            w.currentTextChanged.connect(lambda text, e=e: self._speichern(e, text.strip()))
        elif e.art == "passwort":
            w = PasswortEingabe()
            w.geaendert.connect(lambda text, e=e, w=w: (self._speichern(e, text), w.anzeigen(text)))
        elif e.art == "bild":
            w = LogoEingabe()
            w.geaendert.connect(lambda daten, e=e: self._speichern(e, daten))
        elif e.art == "ordner":
            w = OrdnerEingabe("Gemeinsamen Ordner wählen" if e.name == "teilen_ordner" else "Standardordner wählen")
            if e.name == "teilen_ordner":
                w.pfad.setPlaceholderText("nicht teilen")
            w.setMaximumWidth(self.BREITE_TEXT + 160)
            w.geaendert.connect(lambda pfad, e=e: self._speichern(e, pfad))
        else:
            w = QLineEdit()
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, w.text().strip()))
        if e.art in ("anteil", "zahl", "zahl_leer", "ganz"):
            w.setMaximumWidth(self.BREITE_ZAHL)
        elif e.art in ("text", "auswahl"):
            w.setMaximumWidth(self.BREITE_TEXT)
        elif e.art == "passwort":
            w.setMaximumWidth(self.BREITE_TEXT + 100)
        elif e.art == "mehrzeilig":
            w.setMaximumWidth(self.BREITE_TEXT + 160)
        return w

    EINHEIT = re.compile(r"\s*\[([^\]]{1,12})\]")
    SONDER = re.compile(r"\s*\((0|leer) = ([^);]+)\)")

    def _kurztitel(self, e, w):
        """Vorgaben-Formular (Layout-Plan L12): Einheit als Suffix rechts im Feld statt im Titel, Sonderfall
        („0 = aus“, „leer = keiner“) als grauer Text im Feld. Der volle Titel bleibt Tooltip."""
        titel = e.titel
        if isinstance(w, (QSpinBox, QDoubleSpinBox)) and e.art in ("zahl", "ganz"):
            m = self.EINHEIT.search(titel)
            if m:
                w.setSuffix(" " + m.group(1))
                titel = titel[:m.start()] + titel[m.end():]
            m = self.SONDER.search(titel)
            if m and m.group(1) == "0" and w.minimum() == 0:
                w.setSpecialValueText(m.group(2).strip())
                titel = titel[:m.start()] + titel[m.end():]
        elif e.art in ("text", "zahl_leer", "ordner"):
            m = self.SONDER.search(titel)
            feld = getattr(w, "pfad", w)
            if m and m.group(1) == "leer" and isinstance(feld, QLineEdit):
                if e.art != "ordner" or not feld.placeholderText():
                    feld.setPlaceholderText(m.group(2).strip())
                titel = titel[:m.start()] + titel[m.end():]
        return titel.strip()

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

    def _step_cache_leeren(self):
        from . import step_einstellungen
        n = step_einstellungen.cache_leeren(self.db)
        self.meldung(f"Zwischenspeicher des STEP-Imports geleert ({n} Messungen).")

    def _speichern(self, e, wert):
        if e.name == "benutzer_kuerzel":
            wert = kuerzel_sauber(wert)
        if getattr(self, "_laden", False) or self.db.einstellung(e.name) == wert:
            return
        self.db.einstellung_setzen(e.name, wert)
        if e.name == "benutzer_kuerzel":
            teilen.bearbeiter_nachtragen(self.db)
        if e.name == hilfe.HILFE_EINSTELLUNG:
            hilfe.alle_aktualisieren()
        from . import step_einstellungen
        if e.name in step_einstellungen.EINSTELLUNGEN:
            step_einstellungen.anwenden(self.db)
        if e.name in ("ansicht_thema", "ansicht_schrift", "ansicht_dichte"):
            self.meldung(f"{e.titel} gespeichert, gilt ab dem nächsten Start.")
            return
        if e.name == "ansicht_3d":
            from . import ansicht3d
            ansicht3d.renderer_setzen(wert)
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
            elif e.art in ("bild", "ordner"):
                w.anzeigen(v or "")
            elif e.art == "passwort":
                w.anzeigen(bool(v))
            else:
                w.setText(v or "")
        self._laden = False


class ZeitvorgabenSeite(QWidget):
    """Unterreiter 'Stundensätze und Zeitvorgaben': Stundensätze oben, Arbeitsschritte darunter."""
    titel = "Stundensätze und Zeitvorgaben"
    schluessel = "zeitvorgaben"

    def __init__(self, saetze, schritte):
        super().__init__()
        self.saetze, self.schritte = saetze, schritte
        self.teilseiten = (saetze, schritte)        # für die Suche der Einstellungen
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
        self.fehler.setStyleSheet("color: #B42318;")
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
        self.unter = NavigationsReiter()     # Navigation links mit Suche (Layout-Plan L11)
        self.unter.addTab(vorgaben, "Vorgaben")
        for s in seiten:
            self.unter.addTab(s, getattr(s, "titel", None) or s.t.titel)
        self.unter.currentChanged.connect(lambda _: self.neu_laden())
        sperren = QPushButton("Einstellungen sperren")
        sperren.clicked.connect(self.sperren)
        sperren.setMinimumWidth(90)                 # schmale Fenster (1024 px): Navigation darf schmaler werden
        self.unter.links.addWidget(sperren)         # unter der Navigation: oben bleibt keine Leerzeile
        li = QVBoxLayout(inhalt)
        li.setContentsMargins(0, 0, 0, 0)
        li.addWidget(self.unter, 1)
        self.stapel.addWidget(sperre)
        self.stapel.addWidget(inhalt)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stapel)
        self.offen = False
        self.sperren()

    admin = False           # Admin-Lizenz: ohne Passwort (Hauptfenster.lizenz_anwenden)

    def gesperrt(self):
        return not self.offen and not self.admin and bool(self.db.einstellung("passwort"))

    def oeffnen(self, passwort=None):
        """Mit dem Passwort aus dem Eingabefeld (oder dem übergebenen) öffnen. Ergebnis: geöffnet ja/nein."""
        text = self.passwort.text() if passwort is None or isinstance(passwort, bool) else passwort
        self.passwort.clear()
        if not self.db.passwort_pruefen(text):
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
    """Startseite als Übersicht: Angebote (neu, zuletzt bearbeitet), Stand der Stammdaten, Datensicherung."""
    ZULETZT = 8         # so viele zuletzt geänderte Angebote

    def __init__(self, fenster):
        from .angebot_fenster import AngeboteListe, _tabelle, _zeit, angebot_status
        from .angebot_oben import Aufklapper, karte
        super().__init__()
        self.f = fenster
        titel = QLabel(f"<h2 style='color:{AKZENT}'>{NAME}</h2>")
        version = QLabel(f"Version {update.stand_text(fenster.updater.lokal)}")
        version.setStyleSheet("color: #5F6B7A;")

        # Angebote: neu anlegen, Liste öffnen, zuletzt bearbeitete mit Doppelklick öffnen
        angebote, al = karte("Angebote")
        zeile = QHBoxLayout()
        for text, ziel, primaer in (("Neues Angebot", lambda: fenster.angebote.neu(), True),
                                    ("Aus STEP …", lambda: fenster.angebote.neu_aus_step(), False),
                                    ("Alle Angebote", lambda: fenster.reiter.setCurrentWidget(fenster.angebote), False)):
            b = QPushButton(text)
            if primaer:
                b.setObjectName("primaer")
            if text == "Aus STEP …":
                b.setToolTip("Neues Angebot aus STEP-Dateien (oder STEP-Dateien hierher ziehen)")
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            zeile.addWidget(b)
        zeile.addStretch(1)
        al.addLayout(zeile)
        al.addWidget(QLabel("<b>Zuletzt bearbeitet</b> (Doppelklick öffnet)"))
        self.zuletzt = AngeboteListe([("Angebot", "nummer", None, 110), ("Kunde", "kunde", None, 180),
                                      ("Status", angebot_status, None, 110),
                                      ("Verkaufspreis netto [€]", "vk_netto", 2, 110),
                                      ("Geändert am", lambda z: _zeit(z.get("geaendert")), None, 120)])
        self.zuletzt_ansicht = _tabelle(self.zuletzt, sortieren=False)
        self.zuletzt_ansicht.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.zuletzt_ansicht.horizontalHeader().setStretchLastSection(True)
        self.zuletzt_ansicht.doubleClicked.connect(
            lambda i: fenster.angebot_oeffnen(self.zuletzt.zeilen[i.row()]["id"]))
        al.addWidget(self.zuletzt_ansicht, 1)
        self.keine = QLabel("Noch keine Angebote. <b>Neues Angebot</b> legt das erste an, oder STEP-Dateien "
                            "hierher ziehen.")
        self.keine.setWordWrap(True)
        self.keine.setStyleSheet("color: #5F6B7A;")
        al.addWidget(self.keine)
        al.addStretch(0)                    # ohne Angebote: Knöpfe und Hinweis oben statt verteilt (L8)
        self.angebote_layout = al

        # Cockpit (Layout-Plan L21): Pipeline je Vorgang, Wiedervorlagen, Kennzahlen nur für Admin
        heute, hl = karte("Heute")
        self.pipeline = QLabel()
        self.pipeline.setTextFormat(Qt.RichText)
        self.pipeline.setToolTip("Klick auf einen Vorgang zeigt die Angebotsliste mit diesem Filter")
        self.pipeline.linkActivated.connect(self.vorgang_zeigen)
        hl.addWidget(self.pipeline)
        self.wv_titel = QLabel()
        self.wv_titel.setWordWrap(True)
        hl.addWidget(self.wv_titel)
        self.wiedervorlage = QListWidget()
        self.wiedervorlage.setToolTip("Angebote zum Nachfassen: verschickt und seit einigen Tagen ohne Antwort, "
                                      "Gültigkeit endet bald, oder Wiedervorlage erreicht (Doppelklick öffnet)")
        self.wiedervorlage.itemActivated.connect(
            lambda it: fenster.angebot_oeffnen(it.data(Qt.UserRole)))
        hl.addWidget(self.wiedervorlage)
        self.wv_knoepfe = QWidget()          # Plan A9: für das markierte Angebot
        wk = QHBoxLayout(self.wv_knoepfe)
        wk.setContentsMargins(0, 0, 0, 0)
        for text, ziel in (("Öffnen", fenster.angebot_oeffnen), ("Nachfassen …", self.nachfassen),
                           ("Wiedervorlage …", self.wiedervorlage_setzen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: self._wv_aktion(ziel))
            wk.addWidget(b)
        wk.addStretch(1)
        hl.addWidget(self.wv_knoepfe)
        self.kennzahlen = QLabel()
        self.kennzahlen.setTextFormat(Qt.RichText)
        self.kennzahlen.setWordWrap(True)
        hl.addWidget(self.kennzahlen)
        hl.addStretch(1)

        # Stammdaten: Herkunft, Stand, Anzahl je Tabelle
        stamm, sl = karte("Stammdaten")
        self.stamm = QLabel()
        self.stamm.setWordWrap(True)
        self.stamm.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sl.addWidget(self.stamm)
        self.stamm_tabellen = QLabel()       # Anzahl je Tabelle nur bei Bedarf (L8)
        self.stamm_tabellen.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.stamm_aufklapper = Aufklapper("Tabellen", self.stamm_tabellen)
        sl.addWidget(self.stamm_aufklapper)
        b = QPushButton("Einstellungen öffnen")
        b.clicked.connect(lambda: fenster.reiter.setCurrentWidget(fenster.bereich))
        zeile = QHBoxLayout()
        zeile.addWidget(b)
        zeile.addStretch(1)
        sl.addLayout(zeile)
        sl.addStretch(1)

        # Datensicherung und Datendatei
        sicherung, dl = karte("Daten und Sicherung")
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dl.addWidget(self.info)
        knoepfe = QHBoxLayout()
        for text, ziel in (("Datensicherung erstellen", fenster.sicherung_erstellen),
                           ("Sicherung wiederherstellen …", fenster.wiederherstellen_dialog),
                           ("Datenordner öffnen", fenster.datenordner_oeffnen)):
            b = QPushButton(text)
            b.clicked.connect(ziel)
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        dl.addLayout(knoepfe)

        raster = QGridLayout()
        raster.setSpacing(10)
        raster.addWidget(angebote, 0, 0, 3, 1)
        raster.addWidget(heute, 0, 1)
        raster.addWidget(stamm, 1, 1)
        raster.addWidget(sicherung, 2, 1)
        raster.setColumnStretch(0, 3)
        raster.setColumnStretch(1, 2)
        raster.setRowStretch(0, 1)          # Heute: die Wiedervorlage bekommt den Platz
        lay = QVBoxLayout(self)
        kopf = QHBoxLayout()
        kopf.addWidget(titel)
        kopf.addSpacing(12)
        kopf.addWidget(version, 0, Qt.AlignBottom)
        kopf.addStretch(1)
        lay.addLayout(kopf)
        lay.addLayout(raster, 1)
        self.setAcceptDrops(True)
        self.neu_laden()

    # STEP-Dateien oder Ordner auf die Startseite ziehen: neues Angebot (Plan Arbeitsabläufe W11)
    def dragEnterEvent(self, ereignis):
        from .angebot_fenster import step_neu_pfade
        if step_neu_pfade(ereignis):
            ereignis.acceptProposedAction()

    def dropEvent(self, ereignis):
        from .angebot_fenster import step_neu_pfade
        pfade = step_neu_pfade(ereignis)
        if pfade:
            ereignis.acceptProposedAction()
            self.f.angebote.neu_aus_step(pfade)

    def neu_laden(self):
        db = self.f.db
        herkunft = db.einstellung("stammdaten_herkunft") or "–"
        stand = db.einstellung("stammdaten_stand") or ""
        if stand:
            stand = datetime.datetime.fromisoformat(stand).strftime("%d.%m.%Y %H:%M")
        warnung = ""
        if herkunft == "Beispieldaten":
            warnung = ("<p style='color:#B42318'><b>Die Stammdaten sind Beispielwerte.</b> Bitte im Reiter "
                       "Einstellungen durch die eigenen Werte ersetzen.</p>")
        tabellen = [(t.titel, db.anzahl(t.name)) for t in TABELLEN]
        haelfte = (len(tabellen) + 1) // 2           # zwei Spalten: kurze Liste statt einer langen
        zeilen = "".join(
            "<tr>" + "".join(f"<td>{t}</td><td align='right' style='padding-right:18px'><b>{n}</b></td>"
                             for t, n in tabellen[i::haelfte]) + "</tr>" for i in range(haelfte))
        self.stamm.setText(f"<p>{herkunft} (Stand {stand})</p>{warnung}")
        self.stamm_tabellen.setText(f"<table cellpadding='2'>{zeilen}</table>")
        self.stamm_aufklapper.setze_titel(f"{len(tabellen)} Tabellen, {sum(n for _, n in tabellen)} Einträge")
        self.info.setText(f"Datendatei: {db.pfad}{self.f.datenort_text()}<br><span style='color:#5F6B7A'>Täglich "
                          f"wird automatisch gesichert; vor großen Änderungen zusätzlich eine Sicherung erstellen.</span>")
        alle = db.angebote()
        self.cockpit_laden(alle)
        zuletzt = sorted(alle, key=lambda z: z.get("geaendert") or "", reverse=True)[:self.ZULETZT]
        self.zuletzt.setzen(zuletzt)
        self.zuletzt_ansicht.setVisible(bool(zuletzt))
        self.keine.setVisible(not zuletzt)
        self.angebote_layout.setStretch(self.angebote_layout.count() - 1, 0 if zuletzt else 1)

    def cockpit_laden(self, alle):
        from . import cockpit
        from .ausgabe import euro_text
        self.pipeline_werte = cockpit.pipeline(alle)
        teile = [f"<a href='{v}'>{v}</a>: <b>{n}</b>" + (f" · {euro_text(summe)} €" if summe else "")
                 for v, n, summe in self.pipeline_werte]
        self.pipeline.setText("<b>Eigene Angebote</b><br>" + "<br>".join(teile))
        self.wiedervorlagen = cockpit.wiedervorlagen(alle, self.f.db.einstellung("gueltigkeit"),
                                                     nachfassen=self.f.db.einstellung("nachfassen_tage"))
        self.wiedervorlage.clear()
        for w in self.wiedervorlagen:
            z, rest = w.z, w.rest
            wann = (f"seit {-rest} Tagen fällig" if rest < -1 else "seit gestern fällig" if rest == -1
                    else "heute fällig" if rest == 0 else f"in {rest} Tagen" if rest > 1 else "morgen")
            it = QListWidgetItem(f"{z.get('nummer') or ''}  {z.get('kunde') or ''}  –  {', '.join(w.gruende)} "
                                 f"({wann})")
            it.setData(Qt.UserRole, z["id"])
            if rest < 0:
                it.setForeground(QBrush(stil.farbe("#B42318")))
            self.wiedervorlage.addItem(it)
        n = len(self.wiedervorlagen)
        self.wv_titel.setText(f"<b>Wiedervorlage</b> ({n})" if n else
                              "<b>Wiedervorlage:</b> nichts fällig")
        self.wiedervorlage.setVisible(bool(n))
        self.wv_knoepfe.setVisible(bool(n))
        admin = bool(getattr(self.f, "bereich", None) and self.f.bereich.admin)
        self.kennzahlen.setVisible(admin)
        if admin:
            k = cockpit.kennzahlen(alle)
            quote = f"{k['trefferquote'] * 100:.0f} %" if k["trefferquote"] is not None else "–"
            schnitt = f"{euro_text(k['durchschnitt'])} €" if k["durchschnitt"] is not None else "–"
            self.kennzahlen.setText(
                f"<b>Letzte {k['zeitraum']} Tage</b> (nur Admin): {k['angebote']} Angebote, "
                f"{euro_text(k['summe'])} € angeboten, Ø {schnitt}; {k['beauftragt']} beauftragt "
                f"({euro_text(k['auftragswert'])} €), Trefferquote {quote}")

    def _wv_aktion(self, ziel):
        it = self.wiedervorlage.currentItem() or (self.wiedervorlage.item(0) if self.wiedervorlage.count() else None)
        if it is None:
            return None
        return ziel(it.data(Qt.UserRole))

    def nachfassen(self, angebot_id):
        from .nachfassen_dialog import nachfassen_dialog
        return nachfassen_dialog(self.f, angebot_id, self)

    def wiedervorlage_setzen(self, angebot_id):
        from .nachfassen_dialog import wiedervorlage_dialog
        return wiedervorlage_dialog(self.f, angebot_id, self)

    def vorgang_zeigen(self, v):
        """Angebotsliste mit dem Filter des Vorgangs (nur eigene Angebote wie in der Pipeline)."""
        from .angebot_fenster import MEINE
        a = self.f.angebote
        a.suche.clear()
        if a.wer_filter.findText(MEINE) >= 0:
            a.wer_filter.setCurrentText(MEINE)
        a.vorgang_filter.setCurrentText(v)
        self.f.reiter.setCurrentWidget(a)


class Hauptfenster(QMainWindow):
    def __init__(self, db, programmordner=None, stumm=False, orte=None, lizenz=None):
        from .angebot_fenster import AngeboteSeite
        super().__init__()
        self.db = db
        self.lizenz = lizenz        # lizenz.LizenzStelle oder None (voller Zugriff, keine Hinweise)
        hilfe.einrichten(db)
        self.programmordner = Path(programmordner or Path(__file__).resolve().parent.parent)
        self.orte = orte            # orte.Orte (Datenort portabel/installiert, Vorgabe der Ablage) oder None
        self.stumm = stumm          # Selbsttest: keine Rückfragen und Meldungsfenster
        self.offen = {}             # Angebots-ID -> AngebotSeite
        try:                        # frühere Zeichnungsablage einmalig aufräumen (seit 0.6.28 entfernt)
            db.zeichnungen_entfernen(self.ablage())
        except OSError:
            pass
        from . import step_einstellungen
        step_einstellungen.anwenden(db)     # Toleranzen des STEP-Imports aus den Einstellungen
        from . import ansicht3d
        ansicht3d.renderer_setzen(db.einstellung("ansicht_3d"))     # OpenGL oder QPainter
        from . import spaltenbreite
        spaltenbreite.speicher_setzen(db)        # von Hand gezogene Spaltenbreiten merken (Layout-Plan L15)
        from .update_fenster import Updater
        self.updater = Updater(self, os.environ.get("RL_UPDATE_QUELLE") or update.ADRESSE)
        self.setWindowTitle(f"{NAME} {update.stand_text(self.updater.lokal)}")
        self.setStyleSheet(stil.aktuell())     # Theme und Dichte aus stil.anwenden (beim Start)
        self.resize(1400, 800)
        self.reiter = HauptReiter()     # feste Reiter oben, geöffnete Angebote in eigener Zeile (Layout-Plan L13)
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
                self.kunden = s
                s.doppelklick_setzen(lambda z: self.kunden_angebote(z.get("kundennr"), z.get("name")),
                                     "Doppelklick: Angebote dieses Kunden zeigen · Tippen oder F2: Wert ändern")
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
        self.reiter.gruppe_setzen(self.angebote)     # ab hier: geöffnete Angebote in der Zeile unter „Angebote“
        self.reiter.currentChanged.connect(self.reiter_gewechselt)
        self.setCentralWidget(self.reiter)
        self._menue()
        self.lizenz_hinweis = QLabel()
        self.lizenz_hinweis.setTextFormat(Qt.PlainText)
        self.lizenz_hinweis.hide()
        self.statusBar().addPermanentWidget(self.lizenz_hinweis)
        from .einblendung import Einblendung, Verlauf
        self.einblendung = Einblendung(self)        # ruhige Meldungen unten rechts (Layout-Plan L14)
        self.verlauf = Verlauf()
        self.statusBar().addPermanentWidget(self.verlauf)
        self.statusBar().showMessage("Bereit")
        from . import symbole
        symbole.versehen(self)          # Symbole an Hauptaktionen und Menüpunkten (Layout-Plan L19)
        self.lizenz_anwenden()
        if not stumm:
            self.updater.beim_start()

    def starten(self):
        """Programmstart: Fenster maximiert (mit Taskleiste) und gleich im Reiter Angebote; danach Benutzer (beim
        ersten Start) und Angebote der anderen Mitarbeiter holen."""
        self.reiter.setCurrentWidget(self.angebote)
        self.showMaximized()
        if not self.stumm:
            QTimer.singleShot(200, self._start_teilen)
            z = self.lizenz.zustand if self.lizenz else None
            if z is not None and z.start_hinweis and (z.hinweis or z.grund):
                QTimer.singleShot(400, lambda: QMessageBox.warning(self, "Lizenz", f"{z.hinweis or z.grund}\n\n"
                                                                                  "Mehr unter Hilfe → Lizenz …"))

    def _start_teilen(self):
        from . import teilen_fenster
        try:
            ohne_kuerzel = not teilen.kuerzel(self.db)
        except sqlite3.ProgrammingError:        # Fenster schon geschlossen (Tests)
            return
        if self.db.nur_lesen:                   # Lesemodus: kein Benutzer anlegen, kein Abgleich (beides schreibt)
            return
        if ohne_kuerzel:
            teilen_fenster.benutzer_bearbeiten(self, erststart=True)
        elif teilen.aktiv(self.db):
            teilen_fenster.abgleichen(self, schreiben=False, leise=True)

    def benutzer_bearbeiten(self):
        from . import teilen_fenster
        return teilen_fenster.benutzer_bearbeiten(self)

    def abgleichen(self):
        """Knopf Abgleichen: Angebote und Stammdaten mit dem gemeinsamen Ordner abgleichen."""
        from . import teilen_fenster
        return teilen_fenster.abgleichen(self)

    def _menue(self):
        datei = self.menuBar().addMenu("&Datei")
        self.datei_aktionen = {}
        for text, ziel, taste in (("Neues Angebot aus STEP …", lambda: self.angebote.neu_aus_step(), None),
                                  ("Neue Fassung des Angebots", self.neue_fassung, None),
                                  (None, None, None),
                                  ("Benutzer und gemeinsamer Ordner …", self.benutzer_bearbeiten, None),
                                  ("Mit den Kollegen abgleichen", self.abgleichen, "Ctrl+Shift+A"),
                                  (None, None, None),
                                  ("Datensicherung erstellen", self.sicherung_erstellen, None),
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
            self.datei_aktionen[text] = a
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
                                   ("werkstatt", "Werkstattpapiere (PDF)", ["Ctrl+Shift+P"]),
                                   ("kalkulation", "Kalkulation (PDF)", ["Ctrl+Shift+K"]),
                                   ("staffeln", "Staffelpreise rechnen", ["F8"]),
                                   ("stueck", "Stückzahl ändern …", ["Ctrl+Shift+S"]),
                                   ("material", "Materialanfrage (E-Mail) …", ["Ctrl+Shift+M"]),
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
        ansicht.addSeparator()
        a = QAction("Suchen und ausführen …", self)       # Befehlspalette (Layout-Plan L20)
        a.setShortcut(QKeySequence("Ctrl+K"))
        a.triggered.connect(lambda: self.befehlspalette())
        ansicht.addAction(a)
        hilfe = self.menuBar().addMenu("&Hilfe")
        a = QAction("Bedienungsanleitung (PDF)", self)
        a.setShortcut(QKeySequence.HelpContents)
        a.triggered.connect(lambda: self.anleitung_oeffnen())
        hilfe.addAction(a)
        a = QAction("Kurzanleitung (PDF)", self)
        a.triggered.connect(lambda: self.anleitung_oeffnen(KURZANLEITUNG))
        hilfe.addAction(a)
        a = QAction("Was ist neu …", self)
        a.triggered.connect(self.neuerungen_zeigen)
        hilfe.addAction(a)
        a = QAction("Tastenkürzel …", self)
        a.triggered.connect(self.kuerzel_zeigen)
        hilfe.addAction(a)
        a = QAction("Lizenz …", self)
        a.triggered.connect(lambda: self.lizenz_zeigen())
        hilfe.addAction(a)
        a = QAction("Nach Updates suchen …", self)
        a.triggered.connect(lambda: self.updater.suchen())
        hilfe.addAction(a)
        a = QAction("Über …", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, NAME, f"<b>{NAME}</b> {update.stand_text(self.updater.lokal)}<br>Angebotskalkulation und Materialoptimierung für Rohrlaserteile.<br>"
                        f"Daten: {self.db.pfad}{self.datenort_text()}"
                        + (f"<br>{self.lizenz.text()}<br>Rechner-ID: {self.lizenz.rechner}" if self.lizenz else "")))
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
                if isinstance(w, (QTabWidget, NavigationsReiter)):
                    ziel = getattr(w, "gruppe_von", None) or w     # Unterreiter-Gruppe: Reiter des Angebots
                    break
                w = w.parentWidget()
            if ziel is None:            # Fokus außerhalb: erster Unterreiter der sichtbaren Seite
                seite = self.reiter.currentWidget()
                ziel = next((t for t in seite.findChildren(NavigationsReiter) + seite.findChildren(QTabWidget)
                             if t.isVisible()), None)
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

    def neuerungen_zeigen(self):
        """Hilfe → Was ist neu …: alle Versionen ausführlich (die Bedienungsanleitung zeigt nur die letzten)."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser
        from .neuerungen import als_html
        d = QDialog(self)
        d.setWindowTitle("Was ist neu")
        d.resize(900, 640)
        text = QTextBrowser()
        text.setHtml(als_html())
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel(f"Änderungen je Programmversion, neueste zuerst. Installiert ist {VERSION}."))
        lay.addWidget(text)
        lay.addWidget(knoepfe)
        if not self.stumm:
            d.exec()
        return d

    def angebot_oeffnen(self, angebot_id):
        from .angebot_fenster import AngebotSeite
        seite = self.offen.get(angebot_id)
        neu = seite is None
        if neu:
            seite = AngebotSeite(self, angebot_id)      # lädt das Angebot selbst
            from . import symbole
            symbole.versehen(seite)
            self.offen[angebot_id] = seite
            self.lesemodus_anwenden(seite)
            self.reiter.addTab(seite, seite.titel())
        self._frisch = seite if neu else None           # gerade geladen: beim Reiterwechsel nicht noch einmal
        try:
            self.reiter.setCurrentWidget(seite)
        finally:
            self._frisch = None
        return seite

    # -------------------------------------------------------------- Lizenz
    SCHREIBENDE_KUERZEL = ("rueckgaengig", "wiederholen", "ausschneiden", "einfuegen", "loeschen", "neu", "speichern",
                           "optimieren", "importieren", "drucken", "staffeln", "stueck")
    SCHREIBENDE_DATEI = ("Benutzer und gemeinsamer Ordner …", "Mit den Kollegen abgleichen")

    def lizenz_anwenden(self):
        """Lizenzzustand auf die Oberfläche: Hinweis in der Statusleiste, Fenstertitel, Admin-Rechte (Einstellungen
        ohne Passwort), Aufdruck TESTVERSION, im Lesemodus ändernde Aktionen aus."""
        z = self.lizenz.zustand if self.lizenz else None
        if z is None:
            return
        farbe = "rot" if z.nur_lesen else z.farbe
        self.lizenz_hinweis.setText(z.hinweis if not z.nur_lesen else f"Lesemodus: {z.nur_lesen}")
        self.lizenz_hinweis.setToolTip("Hilfe → Lizenz …")
        self.lizenz_hinweis.setStyleSheet({"gelb": "background: #FFF4D6; color: #7A5B00; padding: 1px 8px;",
                                           "rot": "background: #FDECEA; color: #B42318; padding: 1px 8px;"}
                                          .get(farbe, ""))
        self.lizenz_hinweis.setVisible(bool(self.lizenz_hinweis.text()) and not z.admin)
        self.bereich.admin = z.admin
        if z.admin and not self.bereich.offen:
            self.bereich.offen = True
            self.bereich.neu_laden()
        pdf.AUFDRUCK = "TESTVERSION" if z.test else ""
        titel = f"{NAME} {update.stand_text(self.updater.lokal)}"
        self.setWindowTitle(titel + (" – Lesemodus" if z.nur_lesen else " – TESTVERSION" if z.test else ""))
        if z.nur_lesen:
            self.lesemodus_anwenden()
            self._lesemodus_aktiv = True
        elif getattr(self, "_lesemodus_aktiv", False) and not self.stumm:     # neue Lizenz geladen
            QMessageBox.information(self, "Lizenz", "Ändern ist wieder möglich. Bitte das Programm einmal neu starten, "
                                                    "damit alle Knöpfe wieder frei sind.")

    def lesemodus_anwenden(self, seite=None):
        """Im Lesemodus: ändernde Menüpunkte und Knöpfe aus (ansehen, exportieren, sichern geht weiter)."""
        if not self.db.nur_lesen:
            return
        from .lizenz_dialog import LESEMODUS_TIPP, lesemodus_anwenden
        if seite is not None:
            lesemodus_anwenden(seite)
            return
        for name in self.SCHREIBENDE_KUERZEL:
            self.kuerzel_aktionen[name].setEnabled(False)
        for text in self.SCHREIBENDE_DATEI:
            self.datei_aktionen[text].setEnabled(False)
        for w in [self.angebote, self.kunden, self.fracht, self.zukauf, self.bereich, *self.offen.values()]:
            lesemodus_anwenden(w)
        self.einstellungen.setEnabled(False)
        self.einstellungen.setToolTip(LESEMODUS_TIPP)

    def lizenz_zusatz(self, zusatz):
        """Vom Update-Check: neue Sperrliste übernehmen und Zeit abgleichen, dann den Zustand neu anzeigen."""
        if self.lizenz is None or not zusatz:
            return
        vorher = self.lizenz.zustand.stufe if self.lizenz.zustand else None
        try:
            if zusatz.get("sperrliste"):
                self.lizenz.sperrliste(zusatz["sperrliste"].decode("utf-8", "replace"))
            if zusatz.get("datum"):
                self.lizenz.zeit_abgleich(zusatz["datum"])
        except (OSError, ValueError):
            return
        if self.lizenz.zustand and self.lizenz.zustand.stufe != vorher:
            self.lizenz_anwenden()

    def lizenz_zeigen(self):
        from . import lizenz as lz
        from .lizenz_dialog import LizenzDialog
        if self.lizenz is None:         # Entwicklung/Tests: Zustand ohne Speichern anzeigen
            self.lizenz = lz.LizenzStelle(lz.ordner(self.db.pfad.parent), None)
        d = LizenzDialog(self, self.lizenz, stumm=self.stumm)
        if not self.stumm:
            d.exec()
        return d

    def neue_fassung(self):
        """Datei → Neue Fassung des Angebots (W10): für das offene Angebot, sonst für das in der Liste gewählte."""
        from .angebot_fenster import AngebotSeite
        seite = self.reiter.currentWidget()
        return self.angebote.neue_fassung(seite.id if isinstance(seite, AngebotSeite) else None)

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

    def befehlspalette(self):
        """Strg+K: Angebote, Kunden, Profile, Einstellungen und Befehle suchen und ausführen."""
        from .befehlspalette import Befehlspalette
        d = Befehlspalette(self)
        if not self.stumm:
            d.exec()
        return d

    def kunde_zeigen(self, kundennr, name=None):
        """Reiter Kunden mit diesem Kunden (gesucht nach Kundennummer, sonst Name) zeigen. Ergebnis: Treffer."""
        such = str(kundennr or name or "").strip()
        if not such:
            self.meldung("Im Angebot ist noch kein Kunde eingetragen.", fehler=True)
            return 0
        self.reiter.setCurrentWidget(self.kunden)
        self.kunden.suche.setText(such)
        n = self.kunden.filter.rowCount()
        if n:
            self.kunden.ansicht.selectRow(0)
        else:
            self.meldung(f"„{such}“ steht nicht im Kundenstamm.", fehler=True)
        return n

    def kunden_angebote(self, kundennr, name=None):
        """Reiter Angebote, gefiltert auf den Kunden (Kundennummer, sonst Name). Ergebnis: Anzahl Angebote."""
        such = str(kundennr or name or "").strip()
        if not such:
            return 0
        self.reiter.setCurrentWidget(self.angebote)
        self.angebote.suche.setText(such)
        return self.angebote.filter.rowCount()

    def meldung(self, text, fehler=False):
        self.statusBar().setStyleSheet("color: #B42318;" if fehler else "")
        self.statusBar().showMessage(text, 8000)
        if getattr(self, "verlauf", None) is None:  # noch beim Aufbau des Fensters
            return
        self.verlauf.merken(text, fehler)
        if not self.stumm:                          # Selbsttest und Bildschirmfotos ohne Einblendung
            self.einblendung.zeigen(text, fehler)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "einblendung", None) is not None and self.einblendung.isVisible():
            self.einblendung.platzieren()

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
        if hasattr(w, "neu_laden") and w is not getattr(self, "_frisch", None):
            w.neu_laden()

    def nachfassen_geaendert(self, angebot_id):
        """Nach Nachfassen/Wiedervorlage (Plan A9): Startseite, Angebotsliste und Versandverlauf im Angebot neu."""
        self.start.neu_laden()
        self.angebote.neu_laden()
        seite = self.offen.get(angebot_id)
        if seite is not None:
            seite.kopf["versand"] = (self.db.angebot(angebot_id) or {}).get("versand") or []
            seite._ergebnisse_anzeigen()

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

    def anleitung_oeffnen(self, datei=ANLEITUNG):
        """Bedienungsanleitung.pdf bzw. Kurzanleitung.pdf neben dem Programm (liegt im ZIP), beim Entwickeln aus dem
        Ordner anleitung."""
        for pfad in (self.programmordner / datei, self.programmordner.parent / "anleitung" / datei):
            if pfad.is_file():
                self.datei_oeffnen(pfad)
                return pfad
        QMessageBox.warning(self, Path(datei).stem, f"{datei} wurde nicht gefunden.\n\n"
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
        """Beim Beenden die eigenen Angebote in den gemeinsamen Ordner legen und eine Sicherung (eine je Tag, wird
        überschrieben), auch in den zweiten Sicherungsordner."""
        if not self.stumm and not self.db.nur_lesen and teilen.aktiv(self.db):
            from . import teilen_fenster
            if teilen_fenster.abgleichen(self, lesen=False, leise=True) is None and QMessageBox.warning(
                    self, "Abgleichen", "Die eigenen Angebote ließen sich nicht in den gemeinsamen Ordner legen "
                    "(siehe Statuszeile). Die Kollegen sehen den Stand nach dem nächsten Abgleich.\n\n"
                    "Trotzdem beenden?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                ereignis.ignore()
                return
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
