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
import shutil
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QEvent, QModelIndex, QSortFilterProxyModel, QTimer, QUrl, Signal
from PySide6.QtCore import QBuffer, QByteArray, QPoint
from PySide6.QtGui import QAction, QBrush, QDesktopServices, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QApplication, QSpinBox, QSplitter, QStyle, QStyledItemDelegate, QStyleOptionButton, QStyleOptionViewItem, QTableView, QTabWidget, QVBoxLayout, QWidget)

from . import stil
from . import NAME, URHEBER, VERSION, angebotsordner, ausgabe, funktionen, hilfe, lizenzbedingungen, pdf, schneiddaten_standard, tabellen_eingabe, tastatur, teilen, update
from .angebot import kuerzel_sauber
from .spaltenbreite import AutoGroesse
from . import einstellungen_nav
from .einstellungen_nav import NavigationsReiter
from .hauptreiter import HauptReiter
from .stil import AKZENT, STIL  # noqa: F401 – Stilwerte zentral in stil.py
from .stammdaten import TABELLEN, EINSTELLUNG, EINSTELLUNGEN, Feld, Kontext, pruefen, wert_aus_text, wert_als_text, werkstoff_info, zahl_als_text
from .eingabe import RechenSpin, RechenSpinGanz, Schalter, Segment, segment_passt

ANLEITUNG = "Bedienungsanleitung.pdf"
ANLEITUNG_KOPIE = "Anleitung"     # Unterordner im Datenordner (anleitung_kopie)
KURZANLEITUNG = "Kurzanleitung.pdf"
FARBE_EINGABE = stil.farbe_fest("#FFFCF0")   # Eingabefelder (dezent gelb, Layout-Plan L3)
FARBE_BERECHNET = stil.farbe_fest("#EDEDED")
FARBE_ABWEICHUNG = stil.farbe_fest("#FCE4D6")    # Schneiddaten: Wert weicht vom mitgelieferten Standard ab
# Prüfstatus: nur Auffälliges ist farbig (FEHLER rot, WARNUNG gelb), OK bleibt neutral grau
FARBE_STATUS = {"FEHLER": stil.farbe_fest("#F8CBAD"), "WARNUNG": stil.farbe_fest("#FFD966"), "OK": FARBE_BERECHNET}



def anleitung_kopie(pfad, ordner):
    """Kopie der Anleitung im Datenordner (Unterordner Anleitung), damit der PDF-Betrachter nie die Datei im
    Programmordner festhält: die ließe sich sonst beim Online-Update nicht austauschen (WinError 32). Die Kopie wird
    erneuert, wenn sie fehlt oder sich Größe bzw. Zeitstempel unterscheiden. Ist die alte Kopie gerade geöffnet,
    bleibt sie; ganz ohne Kopie das Original."""
    ziel = Path(ordner) / Path(pfad).name
    try:
        q = Path(pfad).stat()
        if ziel.is_file():
            z = ziel.stat()
            if z.st_size == q.st_size and int(z.st_mtime) == int(q.st_mtime):
                return ziel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        tmp = ziel.with_name(ziel.name + ".neu")
        shutil.copy2(pfad, tmp)
        os.replace(tmp, ziel)
        return ziel
    except OSError:
        return ziel if ziel.is_file() else Path(pfad)

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
        if self.t.name == "schneiddaten" and not hasattr(self, "standard"):
            self.standard = schneiddaten_standard.standard_je_schluessel()
        self.endResetModel()

    def standard_wert(self, zeile, spalte):
        """Schneiddaten: (True, Standardwert), wenn die Zelle vom mitgelieferten Richtwert abweicht, sonst None."""
        if self.t.name != "schneiddaten":
            return None
        art, f = self.spalten[spalte]
        if art != "feld" or f.name not in schneiddaten_standard.WERTE:
            return None
        std = self.standard.get(schneiddaten_standard.schluessel(self.daten[zeile]))
        if std is None or schneiddaten_standard.gleich(self.daten[zeile].get(f.name), std.get(f.name)):
            return None
        return True, std.get(f.name)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.daten)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.spalten)

    def headerData(self, abschnitt, richtung, rolle=Qt.ItemDataRole.DisplayRole):
        if rolle != Qt.ItemDataRole.DisplayRole:
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

    def data(self, index, rolle=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        art, s = self.spalten[index.column()]
        w = self.roh(index.row(), index.column())
        if rolle == Qt.ItemDataRole.ToolTipRole and (abw := self.standard_wert(index.row(), index.column())):
            return f"{wert_als_text(s, w) or 'leer'} – Standard: {wert_als_text(s, abw[1]) or 'leer'}"
        if rolle in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if art == "feld":
                return wert_als_text(s, w)
            if art == "berechnet":
                return zahl_als_text(w, s[2]) if w is not None else ""
            return w
        if rolle == Qt.ItemDataRole.EditRole and art == "feld":
            return wert_als_text(s, w, bearbeiten=True)
        if rolle == Qt.ItemDataRole.UserRole:
            return w
        if rolle == Qt.ItemDataRole.TextAlignmentRole:
            if art == "berechnet" or (art == "feld" and s.art in ("zahl", "ganz")):
                return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.ItemDataRole.BackgroundRole:
            if art == "pruefung":
                return QBrush(FARBE_STATUS.get(str(w).split(":")[0], FARBE_BERECHNET))
            if self.standard_wert(index.row(), index.column()):
                return QBrush(FARBE_ABWEICHUNG)
            return QBrush(FARBE_EINGABE if art == "feld" else FARBE_BERECHNET)
        return None

    admin_gesperrt = False      # Admin-Schutz (admin_schutz_fenster.sperren): ansehen ja, ändern nein

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.spalten[index.column()][0] == "feld" and not self.admin_gesperrt:
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index, text, rolle=Qt.ItemDataRole.EditRole):
        if rolle != Qt.ItemDataRole.EditRole or not index.isValid() or self.admin_gesperrt:
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
        a, b = links.data(Qt.ItemDataRole.UserRole), rechts.data(Qt.ItemDataRole.UserRole)
        if a is None or b is None:
            return a is not None and b is None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return str(a).lower() < str(b).lower()


# Plan Bedienung B7: Funktion(quelle) -> zuletzt benutzte Werte (neueste zuerst); setzt das Hauptfenster
# (Datenbank.zuletzt_benutzt), im stummen Betrieb (Tests) bleibt sie leer
zuletzt_quelle = None
ZULETZT_ANZAHL = 5
ZULETZT_TITEL = "— Zuletzt benutzt —"


def ueberschrift(cb, titel):
    """Nicht wählbare, fette Zwischenzeile in einer Auswahlliste."""
    cb.addItem(titel)
    it = cb.model().item(cb.count() - 1)
    it.setEnabled(False)
    f = it.font()
    f.setBold(True)
    it.setFont(f)


def zuletzt_einfuegen(cb, quelle, erlaubt):
    """Die zuletzt benutzten Werte (nur solche aus erlaubt) als eigene Gruppe oben in die Liste (B7)."""
    if zuletzt_quelle is None:
        return []
    try:
        werte = [w for w in zuletzt_quelle(quelle) if w in erlaubt][:ZULETZT_ANZAHL]
    except Exception:       # noqa: BLE001 – Datendatei geschlossen o. Ä.: ohne Gruppe
        return []
    if werte:
        ueberschrift(cb, ZULETZT_TITEL)
        cb.addItems(werte)
    return werte


def liste_fuellen(cb, k, quelle, erster=""):
    """Auswahlliste füllen; Werkstoffe und Oberflächen mit Überschriften je Kategorie (nicht wählbar), oben die
    zuletzt benutzten (B7). erster: Eintrag vor der Liste (None = keiner)."""
    if erster is not None:
        cb.addItem(erster)
    gruppen = list(k.gruppiert(quelle))
    if quelle in ("profil", "werkstoff", "oberflaeche"):
        zuletzt = zuletzt_einfuegen(cb, quelle, {w for _, werte in gruppen for w in werte})
        if zuletzt and gruppen and not gruppen[0][0]:
            gruppen[0] = ("Alle", gruppen[0][1])     # Trennung der Gruppe „zuletzt“ von der vollen Liste
    for titel, werte in gruppen:
        if titel:
            ueberschrift(cb, f"— {titel} —")
        cb.addItems(werte)
        if quelle == "werkstoff":      # Norm, Rohrlaser-Eigenschaften und Laser-Hinweis als Tooltip (24.10.2026)
            for i in range(cb.count() - len(werte), cb.count()):
                info = werkstoff_info(k.werkstoffe.get(cb.itemText(i)))
                if info:
                    cb.setItemData(i, info, Qt.ItemDataRole.ToolTipRole)


class Auswahl(QStyledItemDelegate):
    """Auswahlliste für Felder mit fester Liste (Profilform, Preisbasis, Profil-ID, …)."""

    def __init__(self, modell, parent):
        super().__init__(parent)
        self.modell = modell

    def _feld(self, index):
        quelle = self.modell.mapToSource(index) if hasattr(self.modell, "mapToSource") else index
        art, f = quelle.model().spalten[quelle.column()]
        return f if art == "feld" else None

    def _janein(self, index):
        """Spalte ja/nein: Häkchen in der Zelle statt Auswahlliste (Plan Eingabefelder E1)."""
        f = self._feld(index) if index.isValid() else None
        return f is not None and f.art == "auswahl" and f.auswahl == "janein"

    def _haken_rechteck(self, option):
        st = option.widget.style() if option.widget else QApplication.style()
        o = QStyleOptionButton()
        r = st.subElementRect(QStyle.SE_CheckBoxIndicator, o, option.widget)
        r.moveCenter(option.rect.center())
        return r

    def paint(self, painter, option, index):
        if not self._janein(index):
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        wert = str(index.data(Qt.ItemDataRole.EditRole) or "").strip().lower()
        opt.text = ""
        st = opt.widget.style() if opt.widget else QApplication.style()
        st.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        haken = QStyleOptionButton()
        haken.rect = self._haken_rechteck(option)
        haken.state = QStyle.State_Enabled | (QStyle.State_On if wert == "ja" else
                                              QStyle.State_NoChange if wert not in ("ja", "nein") else QStyle.State_Off)
        if not (index.flags() & Qt.ItemIsEditable):
            haken.state &= ~QStyle.State_Enabled
        st.drawPrimitive(QStyle.PE_IndicatorCheckBox, haken, painter, opt.widget)

    def editorEvent(self, ereignis, modell, option, index):
        if not self._janein(index) or not (index.flags() & Qt.ItemIsEditable):
            return super().editorEvent(ereignis, modell, option, index)
        t = ereignis.type()
        if t == QEvent.MouseButtonDblClick:
            return True                     # kein Editor, das Umschalten macht der Klick
        if t == QEvent.MouseButtonRelease and ereignis.button() == Qt.LeftButton:
            if not self._haken_rechteck(option).adjusted(-6, -6, 6, 6).contains(ereignis.position().toPoint()):
                return False                # Klick neben das Häkchen: nur auswählen
            return self._umschalten(modell, index)
        if t == QEvent.KeyPress:
            taste = ereignis.key()
            if taste in (Qt.Key_Space, Qt.Key_Select):
                return self._umschalten(modell, index)
            if taste in (Qt.Key_J, Qt.Key_N):
                return modell.setData(index, "ja" if taste == Qt.Key_J else "nein", Qt.ItemDataRole.EditRole)
        return False

    @staticmethod
    def _umschalten(modell, index):
        alt = str(index.data(Qt.ItemDataRole.EditRole) or "").strip().lower()
        modell.setData(index, "nein" if alt == "ja" else "ja", Qt.ItemDataRole.EditRole)
        return True

    def createEditor(self, parent, option, index):
        if self._janein(index):
            return None
        quelle = self.modell.mapToSource(index) if hasattr(self.modell, "mapToSource") else index
        art, f = quelle.model().spalten[quelle.column()]
        if art == "feld" and f.art == "auswahl":
            cb = QComboBox(parent)
            cb.setEditable(f.auswahl not in ("preisbasis", "profilform", "zusatzart", "janein", "satzart", "materialherkunft",
                                              "zeugnis"))
            liste_fuellen(cb, quelle.model().k, f.auswahl)
            if f.auswahl == "profil":           # „40x3“ findet „QR 40x40x3“ (Plan Arbeitsabläufe W5)
                tabellen_eingabe.profil_vervollstaendigen(cb)
            elif cb.isEditable():               # Tippen findet auch Teilwörter, z. B. „4301“ (B7)
                tabellen_eingabe.teilwort(cb)
            return cb
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            editor.setCurrentText(index.data(Qt.ItemDataRole.EditRole) or "")
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, modell, index):
        if isinstance(editor, QComboBox):
            text = editor.currentText()
            if editor.property("profil_namen") is not None:
                text = tabellen_eingabe.profil_aufloesen(text, editor.property("profil_namen"))
            modell.setData(index, text, Qt.ItemDataRole.EditRole)
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
            standard.setToolTip("Schneiddaten aller Maschinen, einer Maschine oder nur der markierten Zeilen auf "
                                "die mitgelieferten Richtwerte zurücksetzen: mit Vorschau und Rückfrage, vorher "
                                "Datensicherung. Orange Zellen weichen vom Standard ab.")
            standard.clicked.connect(lambda: self.schneiddaten_zuruecksetzen())
            leiste.addWidget(standard)
        if tabelle.name == "maschinen":
            satz = QPushButton("Stundensatz ermitteln …")
            satz.setToolTip("Maschinenstundensatz der markierten Maschine aus Anschaffung, Nutzungsdauer, Raum, "
                            "Instandhaltung, Wartung, Strom, Verschleiß und Bediener ermitteln; Übernehmen stellt "
                            "die Maschine auf „ermittelt“ (Schneidgas kommt dann je Teil dazu)")
            satz.clicked.connect(lambda: self.stundensatz_ermitteln())
            leiste.addWidget(satz)
        if tabelle.name in ("schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren", "schweiss_regeln"):
            richt = QPushButton("Richtwerte laden")
            richt.setToolTip("Fehlende Schweißverfahren, Kennwerte, Faktoren und Regeln der Vorkalkulation als "
                             "Richtwerte eintragen; vorhandene Zeilen bleiben unverändert")
            richt.clicked.connect(lambda: self.schweiss_richtwerte())
            leiste.addWidget(richt)
        if tabelle.name == "schweiss_kennwerte":
            lernen = QPushButton("Kennwerte aus Nachkalkulation …")
            lernen.setToolTip("Vorschläge Ist ÷ Soll aus nachkalkulierten Schweißbaugruppen prüfen, mit Begründung "
                              "freigeben oder frühere Freigaben zurücknehmen")
            lernen.clicked.connect(lambda: self.kennwerte_lernen())
            leiste.addWidget(lernen)
            self.lernen_knopf = lernen
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

    def funktionen_anwenden(self):
        """Funktionen ein/aus: „Kennwerte aus Nachkalkulation …“ (Nachkalkulation) und die Spalten Teuerungszuschlag
        der Werkstoffe (Teuerung; eingetragene Zuschläge bleiben sichtbar)."""
        if getattr(self, "lernen_knopf", None) is not None:
            self.lernen_knopf.setVisible(funktionen.an("funktion_nachkalkulation"))
        if self.t.name == "werkstoffe":
            an = funktionen.an("funktion_teuerung") or any(z.get("teuerung_wert") for z in self.modell.daten)
            for i, (art, f) in enumerate(self.modell.spalten):
                if art == "feld" and f.name.startswith("teuerung_"):
                    self.ansicht.setColumnHidden(i, not an)

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
        from .admin_schutz_fenster import gesperrt_melden
        if gesperrt_melden(self):
            return
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
        from .admin_schutz_fenster import gesperrt_melden
        if gesperrt_melden(self):
            return
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
                    f"Kennwerte, {len(fehlt['schweiss_faktoren'])} Faktoren und {len(fehlt['schweiss_regeln'])} "
                    "Regeln der Vorkalkulation fehlen und werden als Richtwerte "
                    "eingetragen (Status Richtwert). Vorhandene Zeilen bleiben unverändert.\n\nRichtwerte sind aus "
                    "dem Nahtquerschnitt hergeleitet, keine Erfahrungswerte der eigenen Fertigung: bitte prüfen und "
                    "danach auf 'geprüft' stellen.\n\nJetzt eintragen?")
            bestaetigt = QMessageBox.question(self, "Richtwerte laden", text, QMessageBox.Yes | QMessageBox.No,
                                              QMessageBox.Yes) == QMessageBox.Yes
        if not bestaetigt:
            return 0
        for name in ("schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren", "schweiss_regeln"):  # Verfahren zuerst
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

    def stundensatz_ermitteln(self, werte=None, zeile=None):
        """Dialog „Stundensatz ermitteln …“ für die markierte Maschine (sonst die erste); werte = {Feld: Wert} ohne
        Dialog (Tests). Speichert die Werte, satz_art = ermittelt und den Satz; Ergebnis die Werte oder None."""
        from . import stundensatz_dialog
        if zeile is None:
            reihen = sorted({self.filter.mapToSource(i).row() for i in self.ansicht.selectionModel().selectedIndexes()})
            if not reihen and not self.modell.daten:
                return None
            zeile = self.modell.daten[reihen[0] if reihen else 0]
        if werte is None:
            werte = stundensatz_dialog.dialog_zeigen(self, zeile, self.db.einstellungen())
            if werte is None:
                return None
        for n, w in werte.items():
            self.db.aendern("maschinen", zeile["id"], n, w)
        self.neu_laden()
        self.meldung(f"Stundensatz {zeile.get('maschinen_id')}: {zahl_als_text(werte['stundensatz'], 2)} €/h "
                     "ermittelt (gilt für neue Angebote).")
        return werte

    def schneiddaten_zuruecksetzen(self, wahl=None):
        """Schneiddaten auf die mitgelieferten Standardwerte zurücksetzen (schneiddaten_standard.StandardDialog: alle
        Maschinen mit Richtwerten, eine Maschine oder die markierten Zeilen, mit Vorschau und Rückfrage; vorher
        Datensicherung). wahl = dict(maschinen, ids, eigene_behalten) ohne Dialog (Tests). Ergebnis wie
        Datenbank.schneiddaten_standard_setzen oder None."""
        if wahl is None:
            markiert = [self.modell.daten[r]["id"] for r in
                        sorted({self.filter.mapToSource(i).row() for i in self.ansicht.selectionModel().selectedIndexes()})]
            wahl = schneiddaten_standard.dialog_zeigen(self, self.modell.daten, markiert)
            if wahl is None:
                return None
        try:
            r = self.db.schneiddaten_standard_setzen(**wahl)
        except OSError as e:
            self.meldung(f"Zurücksetzen abgebrochen, Datensicherung nicht möglich: {e}", fehler=True)
            return None
        self.neu_laden()
        self.meldung(f"Schneiddaten auf Standard zurückgesetzt: {r['geaendert']} Zeile(n) geändert, {r['weg']} "
                     f"entfernt, {r['neu']} ergänzt" + (f"; Sicherung {Path(r['pfad']).name}." if r["pfad"] else "."))
        return r


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
        self.weg.clicked.connect(lambda: self.geaendert.emit(""))
        lay.addWidget(self.feld, 1)
        lay.addWidget(self.weg)

    frei = False            # nur mit Admin-Rechten änderbar (Freigabe 25.10.2026, freigeben())

    def anzeigen(self, gesetzt):
        self.gesetzt = bool(gesetzt)
        self.feld.clear()
        self.feld.setPlaceholderText("gesetzt – zum Ändern neues Passwort eingeben" if gesetzt else "ohne Passwort")
        self.weg.setEnabled(self.frei and self.gesetzt)

    def freigeben(self, an):
        """Setzen, Ändern und Entfernen nur mit Admin-Rechten (Admin-Lizenz und Admin-Passwort in dieser Sitzung)."""
        self.frei = bool(an)
        self.feld.setEnabled(self.frei)
        self.weg.setEnabled(self.frei and getattr(self, "gesetzt", False))
        tipp = "" if self.frei else "Ändern nur mit Admin-Rechten (Admin-Lizenz, Hilfe → Lizenz …)"
        self.feld.setToolTip(tipp)
        if tipp:
            self.weg.setToolTip(tipp)
        else:
            self.weg.setToolTip("Einstellungen ohne Passwort öffnen (ohne Admin-Lizenz-Passwort auch keine "
                                "Admin-Abfrage beim Start)")

    def _neu(self):
        text = self.feld.text()
        self.feld.clear()
        if text and self.frei:
            self.geaendert.emit(text)


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
    """Einstellungen als Formular; gruppen = nur diese Gruppen, ohne = diese Gruppen nicht (je Gruppe eine Karte),
    oder seite = eine Seite aus einstellungen_ordnung.SEITEN (je Abschnitt eine Karte, Expertenabschnitte eingeklappt).
    Ab ZWEI_SPALTEN px Breite stehen die Karten in zwei Spalten (auf die kürzere Spalte verteilt)."""
    ZWEI_SPALTEN = 1150
    BREITE_ZAHL, BREITE_TEXT, BREITE_TITEL = 160, 380, 300

    admin = False           # Admin-Rechte: nur dann ist das Passwort der Einstellungen änderbar (admin_setzen)
    gesperrte = frozenset()     # Admin-Schutz: diese Einstellungen grau (schutz_setzen)
    schluessel = "vorgaben"     # Navigation der Einstellungen (einstellungen_nav.GRUPPEN)

    def __init__(self, db, meldung, gruppen=None, ohne=(), seite=None):
        from . import einstellungen_ordnung as ordnung
        super().__init__()
        self.db, self.meldung = db, meldung
        self.seite = seite
        if seite is not None:       # Plan „Einstellungen aufräumen“: eine Seite je Thema, Karten = Abschnitte
            self.schluessel, self.titel = seite.schluessel, seite.titel
            abschnitte = [(a.titel, [EINSTELLUNG[n] for n in a.namen], a.experte) for a in seite.abschnitte]
        else:
            abschnitte = []
            for e in EINSTELLUNGEN:
                if (gruppen is None or e.gruppe in gruppen) and e.gruppe not in ohne:
                    if not abschnitte or abschnitte[-1][0] != e.gruppe:
                        abschnitte.append((e.gruppe, [], False))
                    abschnitte[-1][1].append(e)
        self.liste = [e for _, liste, _ in abschnitte for e in liste]
        self.setWidgetResizable(True)
        innen = QWidget()
        aussen = QVBoxLayout(innen)
        if seite is not None and seite.hinweis:
            self.hinweis = QLabel(seite.hinweis)
            self.hinweis.setWordWrap(True)
            self.hinweis.setStyleSheet("color: #5F6B7A;")
            aussen.addWidget(self.hinweis)
        lay = QHBoxLayout()
        aussen.addLayout(lay, 1)
        self.spalten = [QVBoxLayout(), QVBoxLayout()]
        for sp in self.spalten:
            sp.setSpacing(10)
            lay.addLayout(sp, 1)
        self.felder = {}
        self.wert_schalter = {}     # Name -> Schalter vor einem Wert mit „0 = aus“ (einstellungen_ordnung.WERT_SCHALTER)
        self.boxen = []
        self.zeilen = []            # (Einstellung, Formular, Zeile, Karte) für die Suche (filtern)
        lokal = ordnung.lokal() if seite is not None and seite.schluessel != "e_arbeitsplatz" else ()
        for titel_karte, liste, experte in abschnitte:
            box = QGroupBox(f"{titel_karte} (Experte)" if experte else titel_karte)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.boxen.append(box)
            for e in liste:
                w = feld = self._eingabe(e)
                self.felder[e.name] = feld
                text = self._kurztitel(e, feld, ordnung.kurztitel(e) if seite is not None else e.titel)
                if seite is not None and e.name in ordnung.WERT_SCHALTER:     # Schalter vor dem Wert
                    w = self._mit_schalter(e, feld)
                if e.name in lokal:
                    text += " · nur dieser Arbeitsplatz"
                titel = QLabel(text)
                titel.setToolTip(e.titel)
                f = funktionen.FUNKTION.get(e.name)
                if f is not None:           # Seite Funktionen: was beim Ausschalten verschwindet
                    titel.setText(f"{text}<br><span style='color:#5F6B7A'>{f.text}</span>")
                    titel.setToolTip(f.text)
                titel.setWordWrap(True)
                titel.setFixedWidth(self.BREITE_TITEL)
                self.zeilen.append((e, form, form.rowCount(), box))
                form.addRow(titel, w)
            if experte:             # eingeklappt; Haken in der Kartenüberschrift klappt auf
                box.setCheckable(True)
                box.setChecked(False)
                box.setToolTip("Selten geänderte Werte: Haken setzen zum Aufklappen")
                box.toggled.connect(lambda an, box=box: self._experte(box, an))
                self._experte(box, False)
        if "step_cache" in self.felder:
            knopf = QPushButton("Zwischenspeicher leeren")
            knopf.setToolTip("Gemerkte Messungen löschen: der nächste STEP-Import misst alle Dateien neu")
            knopf.clicked.connect(self._step_cache_leeren)
            knopf.setMaximumWidth(self.BREITE_ZAHL + 60)
            next(form for e, form, _, _ in self.zeilen if e.name == "step_cache").addRow("", knopf)
        self.zweispaltig = None
        self._anordnen(False)
        self.setWidget(innen)
        self.neu_laden()

    def _mit_schalter(self, e, feld):
        """Schalter an/aus vor dem Wert (Plan Funktionen Schritt 3): aus speichert 0 bzw. leer und merkt sich den
        Wert, an holt ihn zurück. Das Feld bleibt in felder, der Schalter steht in wert_schalter."""
        rahmen = QWidget()
        lay = QHBoxLayout(rahmen)
        lay.setContentsMargins(0, 0, 0, 0)
        sw = Schalter(text_an="an", text_aus="aus")
        sw.setToolTip("Aus: der Wert wird nicht verwendet, bleibt aber gemerkt und kommt beim Einschalten zurück")
        lay.addWidget(sw)
        lay.addWidget(feld, 1)
        self.wert_schalter[e.name] = sw
        sw.toggled.connect(lambda an, e=e: self._wert_schalten(e, an))
        return rahmen

    def _wert_schalten(self, e, an):
        from .einstellungen_ordnung import WERT_GEMERKT, WERT_SCHALTER
        if getattr(self, "_laden", False):
            return
        gemerkt = dict(self.db.einstellung(WERT_GEMERKT) or {})
        if an:
            wert = gemerkt.get(e.name) or WERT_SCHALTER[e.name]
        else:
            alt = self.db.einstellung(e.name)
            if alt:
                gemerkt[e.name] = alt
                self.db.einstellung_setzen(WERT_GEMERKT, gemerkt)
            wert = "" if e.art == "text" else 0
        self._speichern(e, wert)
        self.neu_laden()

    def _experte(self, box, an):
        """Expertenabschnitt auf- oder zuklappen (zu: nur die Überschrift mit Haken)."""
        box.setFlat(not an)
        for e, form, zeile, b in self.zeilen:
            if b is box:
                form.setRowVisible(zeile, an)

    def filtern(self, suche):
        """Suche der Einstellungen: nur passende Einstellungen und Karten zeigen (leer = alle). Ein Treffer in einem
        eingeklappten Expertenabschnitt klappt ihn auf."""
        from .einstellungen_ordnung import kurztitel
        from .einstellungen_nav import passt
        sichtbar = {}
        for e, form, zeile, box in self.zeilen:
            ja = not suche.strip() or passt(f"{e.titel} {kurztitel(e)} {e.gruppe} {box.title()}", suche)
            if ja and suche.strip() and box.isCheckable() and not box.isChecked():
                box.setChecked(True)
            form.setRowVisible(zeile, ja and (not box.isCheckable() or box.isChecked()))
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
            w = RechenSpin()
            w.setRange(e.von * 100, e.bis * 100)
            w.setDecimals(1)
            w.setSuffix(" %")
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, round(w.value() / 100, 6)))
        elif e.art == "zahl":
            w = RechenSpin()
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
            w = RechenSpinGanz()
            w.setRange(int(e.von), int(e.bis))
            w.setGroupSeparatorShown(True)
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, w.value()))
        elif e.art == "mehrzeilig":
            w = MehrzeiligEingabe()
            w.setFixedHeight(80)
            w.fertig.connect(lambda e=e, w=w: self._speichern(e, w.toPlainText().strip()))
        elif e.art == "auswahl":
            # Plan Eingabefelder E1/E2: ja/nein als Schalter, wenige kurze Möglichkeiten als Knopfreihe, feste
            # Listen nur mit ihren Werten; Listen aus den Stammdaten (Maschine, Werkstoff …) mit Teilwortsuche
            fest = Kontext().auswahl(e.auswahl)
            if e.auswahl == "janein":
                w = Schalter()
            elif segment_passt(fest):
                w = Segment(fest)
            else:
                w = QComboBox()
                w.setEditable(not fest)
            w.currentTextChanged.connect(lambda text, e=e: self._speichern(e, text.strip()))
        elif e.art == "passwort":
            w = PasswortEingabe()
            w.freigeben(self.admin)
            w.geaendert.connect(lambda text, e=e, w=w: (self._speichern(e, text), w.anzeigen(text)))
        elif e.art == "bild":
            w = LogoEingabe()
            w.geaendert.connect(lambda daten, e=e: self._speichern(e, daten))
        elif e.art == "ordner":
            w = OrdnerEingabe({"teilen_ordner": "Gemeinsamen Ordner wählen",
                               "ablageordner": "Ablageordner wählen",
                               "csv_ordner": "Ordner für den CSV-Export wählen",
                               "anfrage_ordner": "Anfrage-Ordner wählen"}.get(e.name, "Standardordner wählen"))
            if e.name == "teilen_ordner":
                w.pfad.setPlaceholderText("nicht teilen")
            if e.name == "ablageordner":
                w.pfad.setPlaceholderText("Vorgabe: Ordner 'Angebote' neben dem Programm")
            w.setMaximumWidth(self.BREITE_TEXT + 160)
            w.geaendert.connect(lambda pfad, e=e: self._speichern(e, pfad))
        else:
            w = QLineEdit()
            w.editingFinished.connect(lambda e=e, w=w: self._speichern(e, w.text().strip()))
        if e.art in ("anteil", "zahl", "zahl_leer", "ganz"):
            w.setMaximumWidth(self.BREITE_ZAHL)
        elif e.art == "auswahl" and not isinstance(w, Schalter):
            w.setMaximumWidth(self.BREITE_TEXT)
        elif e.art == "text":
            w.setMaximumWidth(self.BREITE_TEXT)
        elif e.art == "passwort":
            w.setMaximumWidth(self.BREITE_TEXT + 100)
        elif e.art == "mehrzeilig":
            w.setMaximumWidth(self.BREITE_TEXT + 160)
        return w

    def admin_setzen(self, an):
        """Admin-Rechte an/aus (Hauptfenster.lizenz_anwenden): Passwortfelder nur mit Admin-Rechten änderbar."""
        self.admin = bool(an)
        for w in self.felder.values():
            if isinstance(w, PasswortEingabe):
                w.freigeben(self.admin)

    EINHEIT = re.compile(r"\s*\[([^\]]{1,12})\]")
    SONDER = re.compile(r"\s*\((0|leer) = ([^);]+)\)")

    def _kurztitel(self, e, w, titel=None):
        """Vorgaben-Formular (Layout-Plan L12): Einheit als Suffix rechts im Feld statt im Titel, Sonderfall
        („0 = aus“, „leer = keiner“) als grauer Text im Feld. Der volle Titel bleibt Tooltip."""
        titel = e.titel if titel is None else titel
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
        if e.name in step_einstellungen.EINSTELLUNGEN or e.name in step_einstellungen.WEITERE:
            step_einstellungen.anwenden(self.db)
        if e.name in ("ansicht_thema", "ansicht_schrift", "ansicht_dichte"):
            haupt = self.window()
            if hasattr(haupt, "ansicht_anwenden"):
                haupt.ansicht_anwenden()            # sofort wirksam (Dunkelmodus verbessern, 24.10.2026)
            self.meldung(f"{e.titel} gespeichert und angewendet.")
            return
        if e.name == "versand_aktiv":
            haupt = self.window()
            if hasattr(haupt, "versand_anwenden"):
                haupt.versand_anwenden()
        if e.name in ("fertigung_aktiv", "fertigung_status"):
            haupt = self.window()
            if hasattr(haupt, "fertigung_anwenden"):
                haupt.fertigung_anwenden()
        if e.name in ("lager_aktiv", "reste_aktiv"):
            haupt = self.window()
            if hasattr(haupt, "lager_anwenden"):
                haupt.lager_anwenden()
        if e.name in funktionen.FUNKTION:          # Funktionen ein/aus: Reiter, Menüs, Seiten, offene Angebote
            haupt = self.window()
            if hasattr(haupt, "funktionen_anwenden"):
                haupt.funktionen_anwenden()
        if e.name == "ansicht_3d":
            from . import ansicht3d
            ansicht3d.renderer_setzen(wert)
        if e.name in self.wert_schalter and not getattr(self, "_laden", False):
            self.wert_schalter[e.name].blockSignals(True)       # 0 bzw. leer von Hand: Schalter folgt
            self.wert_schalter[e.name].setChecked(bool(wert))
            self.wert_schalter[e.name].blockSignals(False)
            self.felder[e.name].setEnabled(bool(wert))
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
                werte = k.auswahl(e.auswahl)
                if isinstance(w, QComboBox):
                    w.clear()
                    w.addItems(werte)
                    if w.isEditable():
                        tabellen_eingabe.teilwort(w)    # Tippen findet Teilwörter (B7)
                    elif v and v not in werte:
                        w.addItem(v)         # alter Wert, den es in der Liste nicht mehr gibt: sichtbar lassen
                else:
                    w.addItems(werte)
                w.setCurrentText(v or "")
            elif e.art in ("bild", "ordner"):
                w.anzeigen(v or "")
            elif e.art == "passwort":
                w.anzeigen(bool(v))
            else:
                w.setText(v or "")
        if self.wert_schalter:
            from .einstellungen_ordnung import WERT_GEMERKT
            gemerkt = self.db.einstellung(WERT_GEMERKT) or {}
            for name, sw in self.wert_schalter.items():
                e, w, v = EINSTELLUNG[name], self.felder[name], self.db.einstellung(name)
                an = bool(v)
                sw.setChecked(an)
                w.setEnabled(an)
                g = gemerkt.get(name)
                if not an and g:            # aus: den gemerkten Wert grau zeigen (nicht gespeichert)
                    if e.art == "anteil":
                        w.setValue(g * 100)
                    elif e.art == "ganz":
                        w.setValue(int(g))
                    elif e.art == "zahl":
                        w.setValue(g)
                    else:
                        w.setText(str(g))
        self._laden = False
        self._schutz_anwenden()

    def schutz_setzen(self, namen):
        """Admin-Schutz: Einstellungen namen sind gesperrt (grau, nicht änderbar), alle anderen frei."""
        self.gesperrte = frozenset(namen)
        self._schutz_anwenden()

    def _schutz_anwenden(self):
        for name, w in self.felder.items():
            zu = name in self.gesperrte
            sw = self.wert_schalter.get(name)
            if sw is not None:
                sw.setEnabled(not zu)
                w.setEnabled(not zu and sw.isChecked())
            else:
                w.setEnabled(not zu)


class EinstellungenSammlung:
    """Alle Seiten der Einstellungen zusammen (bis 0.9.196 eine Seite „Vorgaben“): Felder aller Seiten, Laden, Suche
    und Admin-Rechte gemeinsam. Steht eine Einstellung auf zwei Seiten, zählt in felder die erste."""

    def __init__(self, seiten):
        self.seiten = list(seiten)
        self.felder, self.liste = {}, []
        for s in self.seiten:
            for e in s.liste:
                if e.name not in self.felder:
                    self.felder[e.name] = s.felder[e.name]
                    self.liste.append(e)

    @property
    def boxen(self):
        return [b for s in self.seiten for b in s.boxen]

    def seite_von(self, name):
        """Erste Seite, auf der die Einstellung steht (oder None)."""
        return next((s for s in self.seiten if name in s.felder), None)

    def neu_laden(self):
        for s in self.seiten:
            s.neu_laden()

    def filtern(self, suche):
        for s in self.seiten:
            s.filtern(suche)

    def admin_setzen(self, an):
        for s in self.seiten:
            s.admin_setzen(an)

    def findChildren(self, typ):
        return [w for s in self.seiten for w in s.findChildren(typ)]

    def setEnabled(self, an):
        for s in self.seiten:
            s.setEnabled(an)

    def setToolTip(self, text):
        for s in self.seiten:
            s.setToolTip(text)


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
    """Reiter Einstellungen: Unterreiter Vorgaben und Stammdaten (ohne Kunden), frei zugänglich. Seiten mit Admin-
    Schutz (admin_schutz.py, Plan 30.10.2026) ändert nur der Admin: oben die Schlossleiste mit Admin-Passwort und
    „Als Admin freischalten …“. Freigeschaltet bleibt es bis 'Admin sperren', Programmende oder 15 Minuten ohne
    Eingabe. Bis 0.9.207 war der ganze Reiter mit einem Passwort gesperrt (Frage 5a: entfällt)."""

    def __init__(self, db, vorgaben, seiten):
        from . import admin_schutz
        from .admin_schutz_fenster import SchlossLeiste
        super().__init__()
        self.db = db
        self.sitzung = admin_schutz.Sitzung()
        admin_schutz.SITZUNG = self.sitzung
        self.pruefer = db.passwort_pruefen      # Hauptfenster: Lizenz (Admin-Lizenz, Notfallcode)
        self.passwort_in_lizenz = False         # Admin-Passwort steht in der Admin-Lizenz (Lizenz-Werkzeug)
        self.nach_schutz = None                 # Rückruf nach jeder Änderung des Schutzes (Frachtkosten)
        self.vorgaben = vorgaben
        self.leiste = SchlossLeiste(self)
        self.passwort, self.fehler = self.leiste.passwort, self.leiste.fehler
        self.unter = NavigationsReiter()     # Navigation links mit Suche (Layout-Plan L11)
        for s in (vorgaben.seiten if isinstance(vorgaben, EinstellungenSammlung) else [vorgaben]):
            self.unter.addTab(s, getattr(s, "titel", None) or "Vorgaben")
        for s in seiten:
            self.unter.addTab(s, getattr(s, "titel", None) or s.t.titel)
        self.grundtitel = [self.unter.tabText(i) for i in range(self.unter.count())]
        self.unter.currentChanged.connect(lambda _: self.neu_laden())
        self.sperren_knopf = self.leiste.sperren
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.leiste)
        lay.addWidget(self.unter, 1)
        self.schutz_anwenden()

    admin = False           # Admin-Lizenz: Kennzahlen, Auswertung (Hauptfenster.lizenz_anwenden)

    @property
    def offen(self):
        """Als Admin freigeschaltet (oder kein Admin-Passwort gesetzt)."""
        return not self.gesperrt()

    @offen.setter
    def offen(self, an):
        if an:
            self.sitzung.freischalten()
        else:
            self.sitzung.sperren()

    def gesperrt(self):
        """True, wenn die geschützten Seiten gerade gesperrt sind (Admin-Passwort gesetzt, nicht freigeschaltet)."""
        from . import admin_schutz
        return not admin_schutz.ist_admin(self.db, self.sitzung)

    def bereich_gesperrt(self, schluessel):
        """True, wenn der Bereich (Seite oder Tabelle, admin_schutz.bereiche) für diesen Platz gerade gesperrt ist."""
        from . import admin_schutz
        return self.gesperrt() and schluessel in admin_schutz.geschuetzt_liste(self.db)

    def oeffnen(self, passwort=None):
        """Als Admin freischalten mit dem Passwort aus der Schlossleiste (oder dem übergebenen): Admin-Passwort der
        Admin-Lizenz, das Passwort der Einstellungen oder ein Notfallcode. Ergebnis: freigeschaltet ja/nein."""
        text = self.passwort.text() if passwort is None or isinstance(passwort, bool) else passwort
        self.passwort.clear()
        if not self.pruefer(text):
            self.fehler.setText("Passwort falsch.")
            return False
        self.sitzung.freischalten()
        self.fehler.clear()
        self.neu_laden()
        return True

    def sperren(self):
        self.sitzung.sperren()
        self.schutz_anwenden()

    def schutz_anwenden(self):
        """Schutz auf alle Seiten: geschützte Einstellungen grau, geschützte Tabellen nicht änderbar, Schloss vor den
        geschützten Seiten in der Navigation, Schlossleiste passend zur gewählten Seite."""
        from . import admin_schutz
        from .admin_schutz_fenster import SCHLOSS, sperren
        from .einstellungen_nav import schluessel
        aktiv = admin_schutz.aktiv(self.db)
        zu = self.gesperrt()
        schutz = admin_schutz.geschuetzt_liste(self.db)
        namen = admin_schutz.einstellungen_geschuetzt(self.db) if zu else set()
        for i in range(self.unter.count()):
            seite = self.unter.widget(i)
            k = getattr(seite, "schutz_bereich", None) or schluessel(seite)
            gesch = k in schutz
            self.unter.setTabText(i, f"{self.grundtitel[i]} {SCHLOSS}" if aktiv and gesch else self.grundtitel[i])
            if hasattr(seite, "schutz_setzen") and isinstance(seite, EinstellungenSeite):
                seite.schutz_setzen(namen)
            elif hasattr(seite, "schutz_setzen"):
                seite.schutz_setzen(zu)
            else:
                sperren(seite, zu and gesch)
        admin = aktiv and not zu
        if isinstance(self.vorgaben, EinstellungenSammlung):
            self.vorgaben.admin_setzen(not zu and not self.passwort_in_lizenz)
        w = self.unter.currentWidget()
        aktuell = (getattr(w, "schutz_bereich", None) or schluessel(w)) if w is not None else ""
        self.leiste.anzeigen(aktiv, admin, zu and aktuell in schutz)
        if self.nach_schutz:
            self.nach_schutz()

    def zeigen(self, seite):
        """Unterreiter auswählen (z. B. Vorgaben oder eine Stammdatenseite)."""
        self.unter.setCurrentWidget(seite)

    def neu_laden(self):
        w = self.unter.currentWidget()
        if hasattr(w, "neu_laden"):
            w.neu_laden()
        self.schutz_anwenden()


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
            lambda it: fenster.angebot_oeffnen(it.data(Qt.ItemDataRole.UserRole)))
        hl.addWidget(self.wiedervorlage)
        self.wv_knoepfe = QWidget()          # Plan A9: für das markierte Angebot
        wk = QHBoxLayout(self.wv_knoepfe)
        wk.setContentsMargins(0, 0, 0, 0)
        for text, ziel in (("Öffnen", fenster.angebot_oeffnen), ("Nachfassen vermerken …", self.nachfassen),
                           ("Wiedervorlage …", self.wiedervorlage_setzen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: self._wv_aktion(ziel))
            wk.addWidget(b)
        wk.addStretch(1)
        hl.addWidget(self.wv_knoepfe)
        # Notizen der Kollegen (gemeinsamer Ordner, Patrick 28.10.2026)
        self.notiz_titel = QLabel()
        hl.addWidget(self.notiz_titel)
        self.notizen = QListWidget()
        self.notizen.setToolTip("Notizen der Kollegen; Doppelklick öffnet das Angebot, „Erledigt“ nimmt die Notiz "
                                "aus der Liste")
        self.notizen.setMaximumHeight(120)
        self.notizen.itemActivated.connect(lambda it: self._notiz_oeffnen(it))
        hl.addWidget(self.notizen)
        self.notiz_knoepfe = QWidget()
        nk = QHBoxLayout(self.notiz_knoepfe)
        nk.setContentsMargins(0, 0, 0, 0)
        for text, ziel in (("Erledigt", self.notiz_erledigt), ("Antworten …", self.notiz_antworten)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            nk.addWidget(b)
        nk.addStretch(1)
        hl.addWidget(self.notiz_knoepfe)
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

        # Neue Anfragen aus dem Anfrage-Ordner (Plan W6a), über den Angeboten; nur mit Einstellung sichtbar
        from .anfragen_karte import AnfragenKarte
        self.anfragen = AnfragenKarte(fenster)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)
        ll.addWidget(self.anfragen.karte)
        ll.addWidget(angebote, 1)

        raster = QGridLayout()
        raster.setSpacing(10)
        raster.addWidget(links, 0, 0, 3, 1)
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
        from .angebot_fenster import step_drop, step_neu_pfade
        pfade = step_neu_pfade(ereignis)
        if pfade:
            step_drop(self.f, ereignis, self, lambda: self.f.angebote.neu_aus_step(pfade))

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
        self.anfragen.neu_laden()
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
            it.setData(Qt.ItemDataRole.UserRole, z["id"])
            if rest < 0:
                it.setForeground(QBrush(stil.farbe("#B42318")))
            self.wiedervorlage.addItem(it)
        n = len(self.wiedervorlagen)
        self.wv_titel.setText(f"<b>Wiedervorlage</b> ({n})" if n else
                              "<b>Wiedervorlage:</b> nichts fällig")
        nachfassen = funktionen.an("funktion_nachfassen")     # Funktion ausgeschaltet: keine Wiedervorlage
        self.wv_titel.setVisible(nachfassen)
        self.wiedervorlage.setVisible(bool(n) and nachfassen)
        self.wv_knoepfe.setVisible(bool(n) and nachfassen)
        self.notizen_laden()
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

    def notizen_laden(self):
        """Offene Notizen der Kollegen: fällige zuerst, mit Wiedervorlage in der Zukunft grau."""
        offen = sorted(teilen.notizen(self.f.db, offen_nur=True), key=lambda n: not n["faellig_jetzt"])
        self.notizen.clear()
        for n in offen:
            wann = ""
            if n.get("faellig"):
                wann = f" · Wiedervorlage {datetime.date.fromisoformat(n['faellig']):%d.%m.%Y}"
            it = QListWidgetItem(f"{n['von']}: {n['notiz']}" + (f"  (Angebot {n['nummer']})" if n.get("nummer") else "")
                                 + wann)
            it.setData(Qt.ItemDataRole.UserRole, n["id"])
            if not n["faellig_jetzt"]:
                it.setForeground(self.notizen.palette().placeholderText())
            self.notizen.addItem(it)
        faellig = sum(1 for n in offen if n["faellig_jetzt"])
        self.notiz_titel.setText(f"<b>Notizen von Kollegen</b> ({faellig})" if offen else "")
        for w in (self.notiz_titel, self.notizen, self.notiz_knoepfe):
            w.setVisible(bool(offen))

    def _notiz(self, it=None):
        it = it or self.notizen.currentItem() or (self.notizen.item(0) if self.notizen.count() else None)
        nid = it.data(Qt.ItemDataRole.UserRole) if it else None
        return next((n for n in teilen.notizen(self.f.db) if n["id"] == nid), None)

    def _notiz_oeffnen(self, it):
        n = self._notiz(it)
        a = next((z for z in self.f.db.angebote() if n and z.get("nummer") == n.get("nummer")), None)
        if a:
            self.f.angebot_oeffnen(a["id"])

    def notiz_erledigt(self):
        n = self._notiz()
        if n:
            teilen.notiz_erledigt(self.f.db, n["id"])
            self.notizen_laden()

    def notiz_antworten(self):
        from . import teilen_fenster
        n = self._notiz()
        if not n:
            return False
        a = next((z for z in self.f.db.angebote() if z.get("nummer") == n.get("nummer")), None)
        return teilen_fenster.notiz_senden(self.f, a["id"] if a else None, vorschlag=n["von"])

    def _wv_aktion(self, ziel):
        it = self.wiedervorlage.currentItem() or (self.wiedervorlage.item(0) if self.wiedervorlage.count() else None)
        if it is None:
            return None
        return ziel(it.data(Qt.ItemDataRole.UserRole))

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
        self.step_drop_laeuft = False   # STEP-Import nach Drag & Drop läuft (angebot_fenster.step_drop)
        self.offen = {}             # Angebots-ID -> AngebotSeite
        try:                        # frühere Zeichnungsablage einmalig aufräumen (seit 0.6.28 entfernt)
            db.zeichnungen_entfernen(self.ablage_lokal())
        except OSError:
            pass
        from . import step_einstellungen
        step_einstellungen.anwenden(db)     # Toleranzen des STEP-Imports aus den Einstellungen
        from . import ansicht3d
        ansicht3d.renderer_setzen(db.einstellung("ansicht_3d"))     # OpenGL oder QPainter
        ansicht3d.speicher_setzen(db)       # Perspektive je Benutzer merken (3E-11)
        from . import spaltenbreite
        spaltenbreite.speicher_setzen(db)        # von Hand gezogene Spaltenbreiten merken (Layout-Plan L15)
        from .update_fenster import Updater
        self.updater = Updater(self, os.environ.get("RL_UPDATE_QUELLE") or update.ADRESSE)
        self.setWindowTitle(f"{NAME} {update.stand_text(self.updater.lokal)}")
        stil.fenster_stil(self)                # Theme und Dichte aus stil.anwenden (beim Start)
        self.resize(1400, 800)
        self.reiter = HauptReiter()     # feste Reiter oben, geöffnete Angebote in eigener Zeile (Layout-Plan L13)
        self.reiter.tabCloseRequested.connect(self._reiter_schliessen)
        self.start = StartSeite(self)
        self.reiter.addTab(self.start, "Start")
        self.angebote = AngeboteSeite(self)
        self.angebote.oeffnen.connect(self.angebot_oeffnen)
        self.reiter.addTab(self.angebote, "Angebote")
        # Versand: beauftragte Angebote mit Palettenschein, Lieferdatum und Stand (Plan Palettenbegleitschein P3)
        from .versand_seite import VersandSeite
        self.versand = VersandSeite(self)
        self.reiter.addTab(self.versand, "Versand")
        self.reiter.setTabVisible(self.reiter.indexOf(self.versand), self.versand_an())
        # Fertigung: Freigabe und Status beauftragter Angebote (Wettbewerbsvergleich P1-6), Einstellung 'fertigung_aktiv'
        from .fertigung_seite import FertigungSeite
        self.fertigung = FertigungSeite(self)
        self.reiter.addTab(self.fertigung, "Fertigung")
        self.reiter.setTabVisible(self.reiter.indexOf(self.fertigung), self.fertigung_an())
        # Lager: Materialbestand und Reststücke (Wettbewerbsvergleich P0-1), nur mit Einstellung 'lager_aktiv'
        from .lager_seite import LagerSeite
        self.lager = LagerSeite(self)
        self.reiter.addTab(self.lager, "Lager")
        self.reiter.setTabVisible(self.reiter.indexOf(self.lager), self.lager_an())
        self.seiten = [StammdatenSeite(db, t, self.meldung) for t in TABELLEN]
        for s in self.seiten:           # Kunden als eigener Reiter, die übrigen Stammdaten unter Einstellungen
            if s.t.name == "kunden":
                self.reiter.addTab(s, s.t.titel)
                self.kunden = s
                s.doppelklick_setzen(lambda z: self.kunden_angebote(z.get("kundennr"), z.get("name")),
                                     "Doppelklick: Angebote dieses Kunden zeigen · Tippen oder F2: Wert ändern")
        # Einstellungen nach Themen (Plan „Einstellungen aufräumen“, 29.10.2026): je Seite der Ordnung ein Formular
        from .einstellungen_ordnung import SEITEN as EINSTELLUNGS_SEITEN
        funktionen.db_setzen(db)
        self.einstellungen = EinstellungenSammlung(EinstellungenSeite(db, self.meldung, seite=s)
                                                   for s in EINSTELLUNGS_SEITEN)
        seite = {s.t.name: s for s in self.seiten}
        self.zeitvorgaben = ZeitvorgabenSeite(seite["stundensaetze"], seite["arbeitsschritte"])
        # Zusatzarbeiten: eigene Verwaltung (Übersicht, Formular, Preisvorschau) statt der Stammdatentabelle
        from .zusatz_verwaltung import ZusatzVerwaltung
        self.zusatz = ZusatzVerwaltung(db, self.meldung)
        unter = [self.zusatz if s.t.name == "zusatzarbeiten" else s for s in self.seiten
                 if s.t.name not in ("kunden", "stundensaetze", "arbeitsschritte")]
        # Admin-Schutz (Plan 30.10.2026): Seite mit den Häkchen je Bereich
        from .admin_schutz_fenster import AdminSchutzSeite, EingabeWaechter
        self.admin_seite = AdminSchutzSeite(db, self.meldung, lambda: self.bereich.schutz_anwenden())
        # Frachtkosten: Rechner als eigener Reiter, die Pflegeseiten unter Einstellungen → Fracht (0.9.211)
        from .fracht_seite import FrachtBereich
        self.fracht = FrachtBereich(self)
        self.bereich = EinstellungenBereich(db, self.einstellungen, unter + [self.zeitvorgaben, self.admin_seite]
                                            + self.fracht.pflege)
        if self.lizenz is not None:
            self.bereich.pruefer = self.lizenz.passwort_gilt
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
        self.funktionen_anwenden()          # ausgeschaltete Funktionen gleich beim Start ausblenden
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
        self.fenster_merker = None
        if not stumm:
            self.updater.beim_start()
            global zuletzt_quelle                       # zuletzt benutzte Werte oben in Auswahllisten (B7)
            zuletzt_quelle = db.zuletzt_benutzt
            from . import fenster_platz     # Fenster passen auf den Bildschirm, offenes Fenster bleibt vorne (E3/E6)
            self.fenster_platz = fenster_platz.einrichten(self)
            self.eingabe_waechter = EingabeWaechter(self.bereich.sitzung)  # Admin sperrt nach 15 min ohne Eingabe
            QApplication.instance().installEventFilter(self.eingabe_waechter)
            self.admin_uhr = QTimer(self)
            self.admin_uhr.setInterval(30_000)
            self.admin_uhr.timeout.connect(self.admin_ablauf)
            self.admin_uhr.start()
            from .fenster_merken import FensterMerker     # Größe, Lage, Teiler der Dialoge (Plan Bedienung B4)
            self.fenster_merker = FensterMerker(db, self)
            QApplication.instance().installEventFilter(self.fenster_merker)

    def starten(self):
        """Programmstart: Fenster maximiert (mit Taskleiste) und gleich im Reiter Angebote; danach Benutzer (beim
        ersten Start) und Angebote der anderen Mitarbeiter holen."""
        self.reiter.setCurrentWidget(self.angebote)
        self.showMaximized()
        self.lose_dateien_verschieben()
        if not self.stumm:
            from . import fenster_merken            # zuletzt offene Angebote wieder öffnen (B4, Freigabe F2a)
            fenster_merken.sitzung_wiederherstellen(self)
            QTimer.singleShot(200, self._start_teilen)
            QTimer.singleShot(800, self._start_systempruefung)
            z = self.lizenz.zustand if self.lizenz else None
            if z is not None and z.start_hinweis and (z.hinweis or z.grund):
                QTimer.singleShot(400, lambda: QMessageBox.warning(self, "Lizenz", f"{z.hinweis or z.grund}\n\n"
                                                                                  "Mehr unter Hilfe → Lizenz …"))

    def sicherung_beobachten(self, lauf):
        """Tägliche Sicherung im Hintergrund (Datenbank.sicherung_heute): bei Fehler eine Meldung."""
        if not lauf.fertig():
            QTimer.singleShot(1000, lambda: self.sicherung_beobachten(lauf))
        elif lauf.fehler is not None:
            self.meldung(f"Die tägliche Sicherung ist fehlgeschlagen: {lauf.fehler}", fehler=True)

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
        # Zusammenarbeit (Patrick 28.10.2026): alle paar Minuten von selbst abgleichen (Einstellung teilen_takt)
        self.teilen_takt = QTimer(self)
        self.teilen_takt.timeout.connect(self._teilen_takt)
        self._teilen_takt(starten=True)

    def _teilen_takt(self, starten=False):
        from . import teilen_fenster
        try:
            ms = teilen_fenster.takt_ms(self.db)
            if not starten and ms:
                teilen_fenster.auto_abgleich(self)
        except sqlite3.ProgrammingError:        # Fenster schon geschlossen (Tests)
            self.teilen_takt.stop()
            return
        self.teilen_takt.start(ms or 60_000)    # aus: jede Minute nachsehen, ob es eingeschaltet wurde

    def benutzer_bearbeiten(self):
        from . import teilen_fenster
        return teilen_fenster.benutzer_bearbeiten(self)

    def abgleichen(self):
        """Knopf Abgleichen: Angebote und Stammdaten mit dem gemeinsamen Ordner abgleichen."""
        from . import teilen_fenster
        erg = teilen_fenster.abgleichen(self)
        self.funktionen_anwenden()          # Funktionen ein/aus gelten für alle Plätze und kommen mit dem Abgleich
        return erg

    def konflikte_zeigen(self):
        """Datei → Abgleich-Konflikte: Stammdaten, die hier und bei einem Kollegen verschieden geändert wurden."""
        from . import teilen_fenster
        return teilen_fenster.konflikte_zeigen(self)

    def _menue(self):
        datei = self.menuBar().addMenu("&Datei")
        self.datei_aktionen = {}
        for text, ziel, taste in (("Neues Angebot aus STEP …", lambda: self.angebote.neu_aus_step(), None),
                                  ("Neue Fassung des Angebots", self.neue_fassung, None),
                                  (None, None, None),
                                  ("Benutzer und gemeinsamer Ordner …", self.benutzer_bearbeiten, None),
                                  ("Mit den Kollegen abgleichen", self.abgleichen, "Ctrl+Shift+A"),
                                  ("Abgleich-Konflikte …", self.konflikte_zeigen, None),
                                  (None, None, None),
                                  ("Datensicherung erstellen", self.sicherung_erstellen, None),
                                  ("Sicherung wiederherstellen …", self.wiederherstellen_dialog, None),
                                  (None, None, None),
                                  ("Alte Angebote archivieren …", self.archivieren, None),
                                  ("Archiv durchsuchen …", self.archiv_dialog, None),
                                  (None, None, None),
                                  ("Angebots-Auswertung …", self.angebots_auswertung, None),
                                  ("Preis-Simulator …", self.preis_simulator, None),
                                  ("Maschinenauslastung …", self.maschinenauslastung, None),
                                  ("Reklamationen …", self.reklamationen, None),
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
                                   ("hoch", "Position nach oben", ["Alt+Up"]),
                                   ("runter", "Position nach unten", ["Alt+Down"]),
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
        a = QAction("Systemprüfung …", self)
        a.triggered.connect(lambda: self.systempruefung_zeigen())
        hilfe.addAction(a)
        a = QAction("Lizenz …", self)
        a.triggered.connect(lambda: self.lizenz_zeigen())
        hilfe.addAction(a)
        a = QAction("Lizenzbedingungen …", self)
        a.triggered.connect(self.lizenzbedingungen_zeigen)
        hilfe.addAction(a)
        a = QAction("Nach Updates suchen …", self)
        a.triggered.connect(lambda: self.updater.suchen())
        hilfe.addAction(a)
        a = QAction("Über …", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, NAME, f"<b>{NAME}</b> {update.stand_text(self.updater.lokal)}<br>Angebotskalkulation und Materialoptimierung für Rohrlaserteile.<br>"
                        f"{URHEBER}<br>"
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

    def lizenzbedingungen_zeigen(self):
        """Hilfe → Lizenzbedingungen …: derselbe Text wie im Setup (rohrlaser/Lizenzbedingungen.txt)."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser
        d = QDialog(self)
        d.setWindowTitle("Lizenzbedingungen")
        d.resize(760, 640)
        text = QTextBrowser()
        text.setPlainText(lizenzbedingungen())
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        lay.addWidget(text)
        lay.addWidget(knoepfe)
        if not self.stumm:
            d.exec()
        return d

    def systempruefung_zeigen(self, zeilen=None):
        """Hilfe → Systemprüfung …: dieser Rechner gegen die Systemvoraussetzungen (systempruefung.py)."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser
        from . import systempruefung
        if zeilen is None:
            zeilen = systempruefung.pruefen(self.db.pfad.parent)
        d = QDialog(self)
        d.setWindowTitle("Systemprüfung")
        d.resize(980, 380)
        text = QTextBrowser()
        text.setHtml(systempruefung.html(zeilen))
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        zu_wenig = systempruefung.unter_minimum(zeilen)
        info = QLabel(("<b style='color:#B42318'>Unter dem Minimum: " + ", ".join(z[0] for z in zu_wenig) +
                       ".</b> Das Programm läuft, große Angebote, STEP-Dateien und 3D-Ansichten können aber sehr "
                       "langsam werden.") if zu_wenig else
                      "Dieser Rechner erfüllt die Mindestvoraussetzungen. „Empfohlen“ gilt für große STEP-Dateien "
                      "(1.000 Bohrungen und mehr) und große Baugruppen.")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addWidget(text)
        lay.addWidget(knoepfe)
        self.systempruefung_ergebnis = zeilen
        if not self.stumm:
            d.exec()
        return d

    def _start_systempruefung(self):
        """7a: einmal nach Installation bzw. Update prüfen und nur warnen, wenn etwas unter dem Minimum liegt."""
        from . import systempruefung
        try:
            if not systempruefung.start_pruefung_noetig(self.db, VERSION):
                return None
            zeilen = systempruefung.pruefen(self.db.pfad.parent)
        except sqlite3.ProgrammingError:        # Fenster schon geschlossen (Tests)
            return None
        systempruefung.start_gepruft(self.db, VERSION)
        if systempruefung.unter_minimum(zeilen):
            return self.systempruefung_zeigen(zeilen)
        return None

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
                           "optimieren", "importieren", "drucken", "staffeln", "stueck", "hoch", "runter")
    SCHREIBENDE_DATEI = ("Benutzer und gemeinsamer Ordner …", "Mit den Kollegen abgleichen", "Abgleich-Konflikte …",
                         "Alte Angebote archivieren …")

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
        lizenz_pw = (z.inhalt or {}).get("admin_passwort") if z.stufe == "admin" else ""
        self.bereich.passwort_in_lizenz = bool(lizenz_pw)
        if z.admin and lizenz_pw and self.db.einstellung("passwort") != lizenz_pw and not self.db.nur_lesen:
            self.db.einstellung_setzen("passwort", lizenz_pw)   # nur der Hash: gilt so an allen Plätzen (Frage 3a)
        if z.admin and not self.bereich.sitzung.jemals:
            self.bereich.offen = True           # Admin-Passwort beim Start eingegeben
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

    def admin_ablauf(self):
        """Uhr alle 30 s: nach admin_schutz.MINUTEN ohne Eingabe die geschützten Seiten wieder sperren."""
        if self.bereich.sitzung.ablauf_pruefen():
            self.bereich.schutz_anwenden()
            self.meldung("Admin gesperrt (15 Minuten ohne Eingabe).")

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
        self.angebote.suchen(such)
        return self.angebote.filter.rowCount()

    def meldung(self, text, fehler=False, aktion=None, bericht=None):
        """Ruhige Meldung in Statusleiste, Verlauf und Einblendung. aktion = (Knopftext, Funktion), z. B. Rückgängig;
        bericht = (Titel, Einzelheiten): Knopf „Bericht“ (wenn keine andere Aktion) und Eintrag im Verlauf."""
        self.statusBar().setStyleSheet("color: #B42318;" if fehler else "")
        self.statusBar().showMessage(text, 8000)
        self.letzte_aktion = aktion                 # Tests: die angebotene Aktion
        if getattr(self, "verlauf", None) is None:  # noch beim Aufbau des Fensters
            return
        self.verlauf.merken(text, fehler, bericht)
        if aktion is None and bericht:
            from .einblendung import bericht_zeigen
            aktion = ("Bericht …", lambda: bericht_zeigen(self, bericht[0], text, bericht[1]))
        if not self.stumm:                          # Selbsttest und Bildschirmfotos ohne Einblendung
            self.einblendung.zeigen(text, fehler, aktion)

    def einblendung_grenze(self):
        """Linker Rand der Übersicht des sichtbaren Angebots (Fensterkoordinaten) oder None: Einblendungen stehen
        links davon, damit sie Preise und Zeiten nicht verdecken (Prüfung 29.10.2026, O2)."""
        for s in self.offen.values():
            r = getattr(s, "uebersicht_rahmen", None)
            if s.isVisible() and r is not None and r.isVisible():
                return r.mapTo(self, QPoint(0, 0)).x()
        return None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "einblendung", None) is not None and self.einblendung.isVisible():
            self.einblendung.platzieren()

    def zeigen(self, seite):
        """Reiter oder Unterreiter der Einstellungen anzeigen (gesperrt: erst die Passwortabfrage). Die Sammlung
        der Einstellungen zeigt ihre erste Seite (Funktionen)."""
        if seite is self.einstellungen:
            seite = self.einstellungen.seiten[0]
        if seite in (self.zeitvorgaben.saetze, self.zeitvorgaben.schritte):
            seite = self.zeitvorgaben
        if getattr(seite, "t", None) is not None and seite.t.name == "zusatzarbeiten":
            seite = self.zusatz
        if self.bereich.unter.indexOf(seite) >= 0:
            self.bereich.zeigen(seite)
            seite = self.bereich
        self.reiter.setCurrentWidget(seite)

    def einstellung_zeigen(self, name):
        """Seite der Einstellungen mit dieser Einstellung zeigen (Befehlspalette, Hinweise)."""
        seite = self.einstellungen.seite_von(name)
        if seite is not None:
            self.zeigen(seite)
        return seite

    def funktionen_anwenden(self):
        """Funktionen ein/aus (funktionen.py) sofort anwenden: Hauptreiter, Menü Datei, Seiten der Einstellungen,
        Startseite und offene Angebote."""
        for f in funktionen.FUNKTIONEN:
            if f.reiter and hasattr(self, f.reiter):
                self.reiter.setTabVisible(self.reiter.indexOf(getattr(self, f.reiter)), funktionen.an(f.name))
        for text, a in getattr(self, "datei_aktionen", {}).items():
            a.setVisible(funktionen.datei_an(text))
        nav = self.bereich.unter
        for i in range(nav.count()):
            nav.verbergen(i, not funktionen.seite_an(einstellungen_nav.schluessel(nav.widget(i))))
        for s in self.seiten:
            if hasattr(s, "funktionen_anwenden"):
                s.funktionen_anwenden()
        self.start.neu_laden()
        for seite in list(getattr(self, "offen", {}).values()):
            if hasattr(seite, "funktionen_anwenden"):
                seite.funktionen_anwenden()

    def reiter_gewechselt(self, _):
        w = self.reiter.currentWidget()
        if hasattr(w, "neu_laden") and w is not getattr(self, "_frisch", None):
            w.neu_laden()

    def versand_an(self):
        """Reiter Versand und Palettenschein eingeschaltet (Einstellung 'versand_aktiv', Vorgabe ja)?"""
        return self.db.einstellung("versand_aktiv") != "nein"

    def versand_anwenden(self):
        """Reiter Versand nach der Einstellung ein- oder ausblenden (Menüeinträge prüfen beim Öffnen selbst)."""
        self.reiter.setTabVisible(self.reiter.indexOf(self.versand), self.versand_an())
        if self.versand_an():
            self.versand.neu_laden()

    def fertigung_an(self):
        """Reiter Fertigung eingeschaltet (Einstellung 'fertigung_aktiv', Vorgabe ja)?"""
        return self.db.einstellung("fertigung_aktiv") != "nein"

    def fertigung_anwenden(self):
        self.reiter.setTabVisible(self.reiter.indexOf(self.fertigung), self.fertigung_an())
        if self.fertigung_an():
            self.fertigung.neu_laden()

    def fertigung_zeigen(self, angebot_id):
        """Reiter Fertigung mit dem Auftrag markiert; nur beauftragte Angebote (sonst Hinweis). Ergebnis: True."""
        if not self.fertigung_an():
            return False
        self.fertigung.neu_laden()
        if not any(z["id"] == angebot_id for z in self.fertigung.zeilen):
            self.meldung("Fertigungsstatus: erst nach „Beauftragt“ (Vorgang ▾).", fehler=True)
            return False
        self.reiter.setCurrentWidget(self.fertigung)
        self.fertigung.waehlen(angebot_id)
        return True

    def lager_an(self):
        """Reiter Lager und „Material aus Lager …“ eingeschaltet (Einstellung 'lager_aktiv', Vorgabe nein)?"""
        return self.db.einstellung("lager_aktiv") == "ja"

    def lager_anwenden(self):
        self.reiter.setTabVisible(self.reiter.indexOf(self.lager), self.lager_an())
        if self.lager_an():
            self.lager.neu_laden()

    def palettenschein(self, angebot_id):
        """Fenster „Palettenbegleitschein“ eines Angebots (nur beauftragte; sonst Hinweis)."""
        if not self.versand_an():
            return None
        a = self.db.angebot(angebot_id) or {}
        if a.get("vorgang") != "Beauftragt":
            self.meldung(f"Angebot {a.get('nummer') or ''}: Palettenschein erst nach „Beauftragt“ (Vorgang ▾).",
                         fehler=True)
            return None
        from . import palettenschein_dialog
        return palettenschein_dialog.oeffnen(self, angebot_id)

    def nachfassen_geaendert(self, angebot_id):
        """Nach Nachfassen/Wiedervorlage (Plan A9): Startseite, Angebotsliste und Versandverlauf im Angebot neu."""
        self.start.neu_laden()
        self.angebote.neu_laden()
        seite = self.offen.get(angebot_id)
        if seite is not None:
            seite.kopf["versand"] = (self.db.angebot(angebot_id) or {}).get("versand") or []
            seite._ergebnisse_anzeigen()

    def ansicht_anwenden(self):
        """Theme, Schriftgröße und Dichte aus den Einstellungen sofort übernehmen (ohne Neustart)."""
        from PySide6.QtWidgets import QApplication
        stil.ansicht_wechseln(QApplication.instance(), self, self.db.einstellung("ansicht_thema"),
                              self.db.einstellung("ansicht_schrift"), self.db.einstellung("ansicht_dichte"))

    def alles_neu_laden(self):
        self.start.neu_laden()
        self.angebote.neu_laden()
        self.versand.neu_laden()
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
        Ordner anleitung. Geöffnet wird eine Kopie im Datenordner (anleitung_kopie). Ergebnis: geöffnete Datei."""
        for pfad in (self.programmordner / datei, self.programmordner.parent / "anleitung" / datei):
            if pfad.is_file():
                pfad = anleitung_kopie(pfad, self.db.pfad.parent / ANLEITUNG_KOPIE)
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
            if teilen_fenster.abgleichen(self, lesen=False, leise=True, beenden=True) is None and QMessageBox.warning(
                    self, "Abgleichen", "Die eigenen Angebote ließen sich nicht in den gemeinsamen Ordner legen "
                    "(siehe Statuszeile). Die Kollegen sehen den Stand nach dem nächsten Abgleich.\n\n"
                    "Trotzdem beenden?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                ereignis.ignore()
                return
        if not self.stumm:
            from . import fenster_merken
            fenster_merken.sitzung_merken(self)     # offene Angebote für den nächsten Start (B4)
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

    def archivieren(self):
        """Datei → Alte Angebote archivieren (archiv_dialog.py, Vorschlag 5b)."""
        from . import archiv_dialog
        return archiv_dialog.archivieren(self)

    def archiv_dialog(self):
        from .archiv_dialog import ArchivDialog
        d = ArchivDialog(self)
        if d.exec() and d.zurueckgeholt:
            self.angebot_oeffnen(d.zurueckgeholt)

    def angebots_auswertung(self):
        """Datei → Angebots-Auswertung: Trefferquote je Kunde, Kategorie, Preisklasse, Absagegründe (nur Admin, wie
        die Kennzahlen der Startseite)."""
        if not (getattr(self, "bereich", None) and self.bereich.admin):
            self.meldung("Die Angebots-Auswertung zeigt Kennzahlen und braucht Admin-Rechte "
                         "(Hilfe → Lizenz → Admin freischalten …).", fehler=True)
            return None
        from .absage_dialog import AuswertungDialog
        d = AuswertungDialog(self)
        if not self.stumm:
            d.exec()
        return d

    def preis_simulator(self):
        """Datei → Preis-Simulator: Was-wäre-wenn für die offenen Angebote (nichts wird gespeichert)."""
        from .preis_simulator_dialog import PreisSimulatorDialog
        d = PreisSimulatorDialog(self)
        d.rechnen()
        d.exec()

    def maschinenauslastung(self):
        """Datei → Maschinenauslastung: Bedarf und Kapazität je Maschine und Woche (auslastung.py). Ergebnis: der
        Dialog (im Selbsttest ohne exec)."""
        from .auslastung_dialog import AuslastungDialog
        d = AuslastungDialog(self)
        if not self.stumm:
            d.exec()
        return d

    def reklamationen(self):
        """Datei → Reklamationen: offene bzw. alle Reklamationen und Quote je Fehlerart, Kunde, Werkstoff
        (reklamation.py). Ergebnis: der Dialog (im Selbsttest ohne exec)."""
        from .reklamation_dialog import ReklamationenDialog
        d = ReklamationenDialog(self)
        if not self.stumm:
            d.exec()
        return d

    def wiederherstellen_dialog(self):
        from .sicherung_dialog import WiederherstellenDialog
        d = WiederherstellenDialog(self)
        if d.exec() and d.gewaehlt:
            self.daten_ersetzen(d.gewaehlt)

    def daten_exportieren(self):
        from PySide6.QtWidgets import QFileDialog
        vorschlag = self.ablage_lokal() / f"Rohrlaser-Daten {datetime.date.today():%Y-%m-%d}.zip"
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
        datei, _ = QFileDialog.getOpenFileName(self, "Daten importieren", str(self.ablage_lokal()),
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
        """Ordner für PDF und CSV-Export: mit gemeinsamem Ordner dessen Unterordner „Angebote“ (Einstellung
        teilen_ablage, Patrick 28.10.2026), sonst die eigene Ablage (ablage_lokal)."""
        gemeinsam = teilen.unterordner(self.db, teilen.ANGEBOTE, "teilen_ablage", anlegen=True)
        return gemeinsam if gemeinsam is not None else self.ablage_lokal()

    def ablage_lokal(self):
        """Ablage dieses Arbeitsplatzes (Einstellung 'Ablageordner', sonst portabel 'Angebote' neben dem Programm,
        installiert Dokumente\\Rohrlaser Angebote)."""
        vorgabe = self.orte.ablage if self.orte else self.programmordner / ausgabe.ABLAGE
        return ausgabe.ablageordner(self.db.einstellung("ablageordner"), vorgabe)

    def ablage_oeffnen(self):
        try:
            self.datei_oeffnen(self.ablage())
        except OSError as e:
            QMessageBox.warning(self, "Ablage", f"Der Ablageordner lässt sich nicht öffnen:\n{e}")

    def angebot_ordner(self, kopf):
        """Ordner des Angebots in der Ablage ('2026-00042 Kunde', Fassungen 'Fassung 2' darin), wird angelegt.
        Vorher werden Ordner vorläufiger Nummern auf die endgültige umbenannt. OSError: nicht anlegbar."""
        ablage = self.ablage()
        lokal = self.ablage_lokal()
        grund = angebotsordner.teile(kopf)[0]
        if ablage != lokal and not angebotsordner.finden(ablage, grund) and angebotsordner.finden(lokal, grund):
            ablage = lokal          # Ordner aus der Zeit vor dem gemeinsamen Ordner bleibt, wo er ist
        angebotsordner.umnummerieren_offen(self.db, ablage)
        return angebotsordner.ordner(ablage, kopf)

    def angebot_ordner_oeffnen(self, kopf):
        """Knopf „Ordner öffnen“: Ordner des Angebots im Explorer (ohne Angebot: die ganze Ablage)."""
        if not kopf:
            return self.ablage_oeffnen()
        try:
            ordner = self.angebot_ordner(kopf)
        except OSError as e:
            QMessageBox.warning(self, "Ablage", f"Der Ordner des Angebots lässt sich nicht anlegen:\n{e}")
            return None
        self.datei_oeffnen(ordner)
        return ordner

    def lose_dateien_verschieben(self):
        """Einmalig je Ablage: Dateien aus der Zeit vor den Angebotsordnern in den Ordner ihres Angebots."""
        try:
            n = angebotsordner.lose_verschieben_einmal(self.db, self.ablage_lokal())
        except (OSError, sqlite3.Error):
            return 0
        if n:
            self.meldung(f"{n} Datei(en) der Ablage in die Ordner ihrer Angebote verschoben.")
        return n

    def datei_oeffnen(self, pfad):
        """Datei oder Ordner mit dem zugehörigen Programm öffnen (im Selbsttest nicht)."""
        if self.stumm:
            return
        if sys.platform == "win32":
            os.startfile(str(pfad))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pfad)))
