"""Angebote: Übersicht, Angebotsbearbeitung (Kopf, Positionen), STEP-Import, Optimierung, Ergebnisse."""
import datetime
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QSize, QDate, QEventLoop, QModelIndex, QPointF, QProcess, QRectF, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QPainter, QPen, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFrame,
    QFormLayout, QMenu, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressDialog, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QStyledItemDelegate, QTableView,
    QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget)

from . import fracht_angebot, ausgabe, export, materialanfrage, naht, pdf, rechnen, schneidweg, step, tastatur, \
    zukauf, zukauf_ek
from .nachkalk_seite import NachkalkulationSeite
from .staffel_seite import StaffelSeite
from .zusatz_dialog import ZusatzDialog
from .schneidweg_dialog import SchneidwegDialog, gewinde_liste
from .naht_dialog import NahtDialog
from .zukauf_dialog import ZukaufDialog, datum_text
from .zukauf_schnell import SchnellDialog
from .zeiten_seite import ZeitenSeite
from .angebot import EIGENMATERIAL, POSITIONEN, STEP_FELDER, ZUKAUFTEIL, aktiv as position_aktiv, ist_zukaufteil
from .angebot_oben import KALK_NAMEN, KALK_OFFEN_EINSTELLUNG, KopfBereich, UebersichtBereich, _kundennr
from .sichtbarkeit import sichtbar, spalte_sichtbar
from .angebot_spalten import AUSW_SPALTEN, FEHLER_SPALTEN, KALK_SPALTEN, STANGEN_SPALTEN, TEIL_SPALTEN
from .leiste import UmbruchLeiste
from .fenster import FARBE_BERECHNET, FARBE_EINGABE, FARBE_STATUS, Auswahl, Sortierung
from .spaltenbreite import AutoGroesse
from .verlauf import Verlauf
from .stammdaten import wert_aus_text, wert_als_text, zahl_als_text

FARBE_TEILE = ["#4E79A7", "#F28E2B", "#59A14F", "#B07AA1", "#76B7B2", "#EDC948", "#FF9DA7", "#9C755F",
               "#E15759", "#BAB0AC"]


def preis_aenderung(vorher, nachher):
    """Kurztext zur Preisänderung, z. B. 'Verkaufspreis netto 1.234,00 € → 1.290,50 €.'"""
    if vorher is None or nachher is None:
        return ""
    if abs(vorher - nachher) < 0.005:
        return f"Verkaufspreis netto unverändert {zahl_als_text(vorher, 2)} €."
    return f"Verkaufspreis netto {zahl_als_text(vorher, 2)} € → {zahl_als_text(nachher, 2)} €."


def _z(w, stellen=2):
    return zahl_als_text(w, stellen) if isinstance(w, (int, float)) and not isinstance(w, bool) else ("" if w is None else str(w))


def _farbe_status(text):
    return FARBE_STATUS.get(str(text).split(":")[0])


def _tabelle(modell, sortieren=True):
    v = QTableView()
    if sortieren and not isinstance(modell, Sortierung):
        proxy = Sortierung(v)
        proxy.setSourceModel(modell)
        modell = proxy
    v.setModel(modell)
    v.setSelectionBehavior(QAbstractItemView.SelectRows)
    v.setSortingEnabled(sortieren)
    v.sortByColumn(-1, Qt.AscendingOrder)   # zuerst in der gelieferten Reihenfolge (Pos. aufsteigend)
    kopf = v.horizontalHeader()
    kopf.setDefaultAlignment(Qt.AlignCenter | Qt.TextWordWrap)
    kopf.setMinimumHeight(48)
    v.verticalHeader().setDefaultSectionSize(22)
    AutoGroesse(v)                  # Breite und Höhe passend zum Inhalt (spaltenbreite.py)
    return v


class Liste(QAbstractTableModel):
    """Nur-Lese-Tabelle aus dicts. spalten: [(Titel, Schlüssel oder Funktion(zeile), Nachkommastellen, Breite)]."""

    def __init__(self, spalten, zeilen=(), max_stellen=None):
        super().__init__()
        self.spalten, self.zeilen = spalten, list(zeilen)
        self.max_stellen = max_stellen      # Anzeige höchstens so viele Nachkommastellen, Tooltip genau

    def setzen(self, zeilen):
        self.beginResetModel()
        self.zeilen = list(zeilen)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.zeilen)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.spalten)

    def headerData(self, abschnitt, richtung, rolle=Qt.DisplayRole):
        if rolle == Qt.DisplayRole:
            return self.spalten[abschnitt][0] if richtung == Qt.Horizontal else str(abschnitt + 1)
        return None

    def wert(self, r, c):
        schl = self.spalten[c][1]
        z = self.zeilen[r]
        return schl(z) if callable(schl) else z.get(schl)

    def data(self, index, rolle=Qt.DisplayRole):
        if not index.isValid():
            return None
        w = self.wert(index.row(), index.column())
        stellen = self.spalten[index.column()][2]
        if rolle in (Qt.DisplayRole, Qt.ToolTipRole):
            if isinstance(w, datetime.datetime):
                return w.strftime("%d.%m.%Y %H:%M")
            if stellen is not None and self.max_stellen is not None and rolle == Qt.DisplayRole:
                stellen = min(stellen, self.max_stellen)
            return _z(w, stellen) if stellen is not None else ("" if w is None else str(w))
        if rolle == Qt.UserRole:
            return w
        if rolle == Qt.TextAlignmentRole and isinstance(w, (int, float)) and not isinstance(w, bool):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.BackgroundRole and isinstance(w, str):
            f = _farbe_status(w) or ({"ÜBERBELEGT": FARBE_STATUS["FEHLER"]}.get(w))
            if f is not None:
                return QBrush(f)
        return None


def leere_ausblenden(ansicht, liste, immer=()):
    """Spalten ohne Wert in allen Zeilen (0, leer) ausblenden wie in der Positionsliste (sichtbarkeit.py); Spalten
    mit Schlüssel in immer bleiben. Ergebnis: Anzahl ausgeblendeter Spalten."""
    n = 0
    for c, sp in enumerate(liste.spalten):
        zeigen = (not liste.zeilen or sp[1] in immer
                  or spalte_sichtbar([liste.wert(r, c) for r in range(len(liste.zeilen))]))
        ansicht.setColumnHidden(c, not zeigen)
        n += not zeigen
    return n


def gleiche_ausblenden(ansicht, liste, schluessel):
    """Spalten (Schlüssel aus schluessel), die in allen Zeilen denselben Wert haben, ausblenden; Ergebnis: Text
    'Titel Wert' je ausgeblendeter Spalte für eine Zeile über der Tabelle (Gleiches steht nur einmal da)."""
    teile = []
    for c, sp in enumerate(liste.spalten):
        if sp[1] not in schluessel:
            continue
        werte = {liste.data(liste.index(r, c)) for r in range(len(liste.zeilen))}
        gleich = len(liste.zeilen) > 1 and len(werte) == 1
        ansicht.setColumnHidden(c, gleich)
        if gleich:
            titel, einheit = sp[0], ""
            if "[" in titel:
                titel, einheit = titel.split("[", 1)
                einheit = " " + einheit.rstrip("]")
            teile.append(f"{titel.strip()} <b>{werte.pop()}{einheit}</b>")
    return teile


def _breiten(ansicht, spalten):
    for i, s in enumerate(spalten):
        ansicht.setColumnWidth(i, s[3] if len(s) > 3 else 90)


# ------------------------------------------------------------------ Übersicht der Angebote
class AngeboteSeite(QWidget):
    oeffnen = Signal(int)
    KUERZEL = {"neu": "neu", "loeschen": ("loeschen", "ansicht")}     # Tastenkürzel, siehe tastatur.py

    SPALTEN = [("Angebotsnummer", "nummer", None, 120), ("Kunde", "kunde", None, 200), ("Kundennr.", "kundennr", None, 90),
               ("Datum", lambda z: _datum(z.get("datum")), None, 85), ("Maschine", "maschine", None, 70),
               ("Positionen", "positionen", 0, 70), ("Teile", "teile", 0, 70),
               ("Optimiert am", lambda z: _zeit(z.get("optimiert_am")), None, 120),
               ("Geändert am", lambda z: _zeit(z.get("geaendert")), None, 120),
               ("Nachkalkuliert", lambda z: "ja" if z.get("nachkalkuliert") else "", None, 85)]

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.modell = Liste(self.SPALTEN)
        self.filter = Sortierung()
        self.filter.setSourceModel(self.modell)
        self.ansicht = _tabelle(self.filter)
        self.ansicht.setEditTriggers(QAbstractItemView.NoEditTriggers)
        _breiten(self.ansicht, self.SPALTEN)
        self.ansicht.doubleClicked.connect(lambda i: self.oeffnen.emit(self._id(i)))
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen nach Angebot, Kunde, Artikel …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.neu_laden)
        tastatur.suche_esc(self.suche)
        for taste in (Qt.Key_Return, Qt.Key_Enter):         # Eingabe öffnet das markierte Angebot
            k = QShortcut(QKeySequence(taste), self.ansicht, self.oeffnen_gewaehlt)
            k.setContext(Qt.WidgetShortcut)
        leiste = QHBoxLayout()
        for text, ziel in (("Neues Angebot", self.neu), ("Öffnen", self.oeffnen_gewaehlt), ("Kopieren", self.kopieren),
                           ("Löschen", self.loeschen), ("Ablage öffnen", self.f.ablage_oeffnen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            leiste.addWidget(b)
        leiste.addSpacing(20)
        leiste.addWidget(self.suche, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(leiste)
        lay.addWidget(self.ansicht, 1)
        self.neu_laden()

    def neu_laden(self, *_):
        self.modell.setzen(self.db.angebote(self.suche.text().strip()))

    def _id(self, index):
        return self.modell.zeilen[self.filter.mapToSource(index).row()]["id"]

    def _gewaehlt(self):
        i = self.ansicht.currentIndex()
        if not i.isValid():
            self.f.meldung("Bitte zuerst ein Angebot wählen.", fehler=True)
            return None
        return self._id(i)

    def neu(self):
        i = self.db.angebot_neu()
        self.neu_laden()
        self.oeffnen.emit(i)

    def oeffnen_gewaehlt(self):
        i = self._gewaehlt()
        if i:
            self.oeffnen.emit(i)

    def kopieren(self, kundennr=None):
        """Angebot kopieren; im Dialog lässt sich ein anderer Kunde wählen (kundennr setzt ihn ohne Dialog)."""
        i = self._gewaehlt()
        if not i:
            return None
        if kundennr is None and not self.f.stumm:
            kundennr = self._kunde_fuer_kopie(self.db.angebot(i))
            if kundennr is False:
                return None
        neu = self.db.angebot_kopieren(i, kundennr)
        self.neu_laden()
        self.oeffnen.emit(neu)
        return neu

    def _kunde_fuer_kopie(self, a):
        """Dialog: Kunde der Kopie. Ergebnis: Kundennummer ('' = ohne Kunde) oder False (abgebrochen)."""
        d = QDialog(self)
        d.setWindowTitle(f"Angebot {a['nummer']} kopieren")
        form = QFormLayout(d)
        kunde = QComboBox()
        kunde.setEditable(True)
        kunde.setInsertPolicy(QComboBox.NoInsert)
        for kd in self.db.zeilen("kunden"):
            if kd.get("kundennr"):
                kunde.addItem(f"{kd['kundennr']} – {kd.get('name') or ''}", kd["kundennr"])
        i = kunde.findData(a.get("kundennr"))
        kunde.setCurrentIndex(i)
        if i < 0:
            kunde.setEditText(a.get("kundennr") or "")
        text = QLabel("Die Kopie bekommt eine neue Nummer und das heutige Datum. Für einen anderen Kunden "
                      "kommen Name und Zahlungsbedingungen aus dem Kundenstamm.")
        text.setWordWrap(True)
        d.setMinimumWidth(460)
        form.addRow(text)
        form.addRow("Kunde", kunde)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(d.accept)
        knoepfe.rejected.connect(d.reject)
        form.addRow(knoepfe)
        if d.exec() != QDialog.Accepted:
            return False
        return _kundennr(kunde.currentText())

    def loeschen(self):
        i = self._gewaehlt()
        if not i:
            return
        a = self.db.angebot(i)
        if QMessageBox.question(self, "Angebot löschen", f"Angebot {a['nummer']} mit allen Positionen löschen?\n\n"
                                "Die tägliche Datensicherung enthält es weiterhin.") == QMessageBox.Yes:
            self.f.angebot_schliessen(i)
            self.db.angebot_loeschen(i)
            self.neu_laden()


def _datum(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y") if iso else ""
    except ValueError:
        return iso


def _zeit(iso):
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M") if iso else ""
    except ValueError:
        return iso


# ------------------------------------------------------------------ Positionen
BERECHNET = [("Profilform", "profilform", None), ("Querschnitt [mm²]", "querschnitt", 1), ("Wandstärke [mm]", "wand", 2),
             ("Metergewicht [kg/m]", "kg_m", 3), ("Gewicht je Teil [kg]", "gewicht", 3),
             ("Länge gesamt [mm]", "laenge_gesamt", 0), ("Stangenlänge wirksam [mm]", "stange", 0),
             ("Endbeschnitt wirksam [mm]", "end", 0), ("Greiferrest wirksam [mm]", "greif", 0),
             ("Nutzlänge Stange [mm]", "nutz", 0), ("Preis hinterlegt", "preis_hinterlegt", None),
             ("Vorschub groß [mm/min]", "vorschub", 0), ("Schneidgas", "gas", None), ("Gewicht Position [kg]", "gewicht_position", 2),
             ("Eingeplant [Stk]", "eingeplant", 0), ("Nicht eingeplant [Stk]", "nicht_eingeplant", 0)]
SICHTBAR = ["pos", "art", "artikel", "bezeichnung", "profil_id", "werkstoff_id", "oberflaeche", "laenge", "stueck", "schneidweg",
            "einstiche", "zeit_manuell", "stange", "satz", "je_satz", "preis_m", "material_herkunft", "gewinde", "zusatz", "zukauf",
            "naht_vorgabe", "gewicht_teil"]
# Optionale Spalten: erscheinen, sobald eine Position einen Wert hat, oder über 'Weitere Spalten'
OPTIONALE_SPALTEN = ("art", "oberflaeche", "stange", "satz", "je_satz", "material_herkunft", "gewinde", "zusatz",
                     "zukauf", "naht_vorgabe", "gewicht_teil")
EIGENE = ("zusatz", "zukauf", "naht")        # Spalten mit eigenem Dialog (Doppelklick)
SPALTEN_EINSTELLUNG = "ansicht_positionsspalten"     # gemerkte Wahl {Spalte: True/False}; fehlt = automatisch
ABWEICHUNG_MM = 0.25    # STEP-Teilwerte sind auf 0,1 mm gerundet: kleinere Unterschiede sind keine Änderung


def schneidweg_abweichung(p):
    """Eingetragener Schneidweg − (Anfangs- + Endschnitt + Innenkonturen aus STEP) [mm]; None ohne STEP-Werte
    oder wenn beide gleich sind (der Schneidweg wurde nicht von Hand geändert)."""
    teile = [p.get(n) for n in ("a_schnitt", "b_schnitt", "innen")]
    if any(not isinstance(t, (int, float)) for t in teile) or not isinstance(p.get("schneidweg"), (int, float)):
        return None
    d = p["schneidweg"] - sum(teile)
    return d if abs(d) > ABWEICHUNG_MM else None


class PositionenModell(QAbstractTableModel):
    geaendert = Signal()

    def __init__(self, seite):
        super().__init__()
        self.s = seite
        felder = {f.name: f for f in POSITIONEN.felder}
        self.spalten = ([(felder[n].art if felder[n].art in EIGENE else "feld", felder[n]) for n in SICHTBAR]
                        + [("status", None)]
                        + [("berechnet", b) for b in BERECHNET]
                        + [("feld", f) for f in POSITIONEN.felder if f.name in STEP_FELDER]
                        + [("abweichung", None)])
        self.daten, self.werte, self.status = [], [], []
        self.mit_netz, self.bilder = set(), {}

    def vorschau(self, r):
        """Kleines 3D-Bild der Position (nur aus dem STEP-Import), einmal je Position gezeichnet."""
        pid = self.daten[r].get("id")
        if pid not in self.mit_netz:
            return None
        if pid not in self.bilder:
            from .ansicht3d import entpacken, vorschaubild
            try:
                self.bilder[pid] = vorschaubild(entpacken(self.s.db.netz(pid)), 64, 18)
            except Exception:       # beschädigte Daten: ohne Bild weiter
                self.bilder[pid] = None
        return self.bilder[pid]

    def rechnen(self):
        s = self.s
        self.beginResetModel()
        self.daten = s.positionen
        self.mit_netz = s.db.netz_ids(s.id)
        self.bilder = {pid: b for pid, b in self.bilder.items() if pid in self.mit_netz}
        erg = s.ergebnis
        eingeplant = rechnen.eingeplant_je_position(erg) if erg and erg["stangen"] else None
        self.werte, self.status, self.zeiten, self.meterpreise = [], [], [], []
        for i, p in enumerate(self.daten):
            w = rechnen.position_werte(p, s.kopf, s.k, s.tabellen)
            self.meterpreise.append(rechnen.meterpreis(p, s.kopf, self.daten, s.k, s.tabellen))  # (berechnet, wirksam, fehlt)
            self.zeiten.append(rechnen.schneidzeit(p, s.kopf, w.get("wand_schneiden"), s.tabellen, s.k)[2])   # berechnet [s]
            ein = eingeplant.get(rechnen.schluessel(p, i), 0) if eingeplant is not None else None
            w["eingeplant"] = ein if p.get("profil_id") and not ist_zukaufteil(p) else None
            if ist_zukaufteil(p):
                ein = None              # Zukaufteile werden nicht eingeplant
            w["nicht_eingeplant"] = (p["stueck"] - ein) if ein is not None and p.get("stueck") is not None else None
            self.werte.append(w)
            self.status.append(rechnen.status(p, w, s.kopf, s.k, ein))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.daten)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.spalten)

    @property
    def k(self):
        return self.s.k

    def headerData(self, abschnitt, richtung, rolle=Qt.DisplayRole):
        if rolle != Qt.DisplayRole:
            return None
        if richtung == Qt.Vertical:
            return str(abschnitt + 1)
        art, x = self.spalten[abschnitt]
        return x.titel if art in ("feld",) + EIGENE else {"status": "Status",
                                                          "abweichung": "Abweichung Schneidweg zu STEP [mm]"}.get(art) or x[0]

    def name(self, c):
        """Name einer Spalte (Feldname, 'status', 'abweichung' oder 'berechnet:' + Schlüssel)."""
        art, x = self.spalten[c]
        return x.name if art in ("feld",) + EIGENE else ("berechnet:" + x[1] if art == "berechnet" else art)

    def roh(self, r, c):
        art, x = self.spalten[c]
        if art == "feld":
            return self.daten[r].get(x.name)
        if art == "status":
            return self.status[r]
        if art == "zusatz":
            return rechnen.zusatz_text(self.daten[r])
        if art == "zukauf":
            return zukauf.zukauf_text(self.daten[r])
        if art == "naht":
            return naht.text(self.daten[r], self.k.profile.get(self.daten[r].get("profil_id")))
        if art == "abweichung":
            return schneidweg_abweichung(self.daten[r])
        w = self.werte[r].get(x[1])
        return {True: "ja", False: "nein"}.get(w, w) if isinstance(w, bool) else w

    def data(self, index, rolle=Qt.DisplayRole):
        if not index.isValid():
            return None
        art, x = self.spalten[index.column()]
        w = self.roh(index.row(), index.column())
        if art == "feld" and x.name == "zeit_manuell":      # Schneidzeit: berechnet, von Hand überschreibbar
            berechnet = self.zeiten[index.row()]
            if rolle == Qt.DisplayRole and w is None:
                return _z(berechnet, 1) if berechnet is not None else ""
            if rolle == Qt.ToolTipRole:
                return (f"Berechnet: {_z(berechnet, 1)} s je Teil (ohne Einsparung gemeinsamer Schnitte). "
                        if berechnet is not None else "Keine Schneiddaten: Zeit von Hand eintragen. ") + \
                    ("Von Hand eingetragen; leeren = wieder berechnet." if w is not None
                     else "Doppelklick zum Anpassen.")
            if rolle == Qt.EditRole and w is None:
                return _z(berechnet, 1) if berechnet is not None else ""
            if rolle == Qt.ForegroundRole:
                return QBrush(QColor("#000000" if w is not None else "#7F7F7F"))
            if rolle == Qt.FontRole and w is not None:
                f = QFont()
                f.setBold(True)
                return f
        if art == "feld" and x.name == "preis_m":           # Meterpreis: berechnet, von Hand überschreibbar
            berechnet, wirksam, fehlt = self.meterpreise[index.row()]
            eigen = rechnen._n(w) > 0
            # Preis von Hand einer anderen Position derselben Stangengruppe gilt für alle Stangen der Gruppe
            fremd = not eigen and wirksam is not None and berechnet is not None and abs(wirksam - berechnet) > 0.005
            anzeige = wirksam if fremd else berechnet
            if rolle in (Qt.DisplayRole, Qt.EditRole) and not eigen:
                return _z(anzeige, 2) if anzeige is not None else ""
            if rolle == Qt.ToolTipRole:
                if ist_zukaufteil(self.daten[index.row()]):
                    return "Zukaufteil: kein Materialpreis je m."
                t = (f"Berechnet: {_z(berechnet, 2)} €/m (Lieferlänge, Preise bzw. Tonnenpreis, mit Aufpreis der "
                     "Oberfläche). " if berechnet is not None else "Kein berechneter Meterpreis: Preis von Hand "
                                                                    "eintragen. ")
                if fehlt and berechnet is not None:
                    t += f"Achtung: {fehlt}. "
                if eigen:
                    return t + ("Von Hand eingetragen, gilt für alle Positionen mit gleichem Profil, Werkstoff, "
                                "Oberfläche und Stangenlänge; leeren = wieder berechnet.")
                if fremd:
                    return t + (f"Es gilt {_z(wirksam, 2)} €/m, von Hand bei einer anderen Position mit gleichem "
                                "Profil, Werkstoff, Oberfläche und Stangenlänge eingetragen.")
                return t + "Doppelklick zum Anpassen (günstiger oder teurer)."
            if rolle == Qt.ForegroundRole:
                return QBrush(QColor("#000000" if eigen else "#7F7F7F"))
            if rolle == Qt.FontRole and (eigen or fremd):
                f = QFont()
                f.setBold(eigen)
                f.setItalic(fremd)
                return f
        if rolle in (Qt.DisplayRole, Qt.ToolTipRole):
            if art == "feld":
                return wert_als_text(x, w)
            if art == "berechnet":
                return _z(w, x[2]) if x[2] is not None else ("" if w is None else str(w))
            if art == "abweichung":
                if rolle == Qt.ToolTipRole:
                    return ("Schneidweg von Hand geändert: eingetragen minus Summe aus Anfangsschnitt, Endschnitt und "
                            "Innenkonturen laut STEP." if w is not None else "Schneidweg wie aus STEP gemessen.")
                return _z(w, 1) if w is not None else ""
            if art == "zusatz" and rolle == Qt.ToolTipRole:
                return (w + "\n" if w else "") + "Doppelklick: Gewinde und Zusatzarbeiten wählen"
            if art == "zukauf" and rolle == Qt.ToolTipRole:
                return (w + "\n" if w else "") + "Doppelklick: Zukaufteile wählen"
            if art == "naht" and rolle == Qt.ToolTipRole:
                return (w + "\n" if w else "Keine Vorgabe: frei drehbar\n") + \
                    "Doppelklick: Schweißnaht am Querschnitt wählen (Blick von Ende A, 0° oben, 90° rechts)"
            return w
        if rolle == Qt.EditRole and art == "feld":
            return wert_als_text(x, w, bearbeiten=True)
        if rolle == Qt.DecorationRole and art == "feld" and x.name == "artikel":
            return self.vorschau(index.row())
        if rolle == Qt.UserRole:
            return w
        if rolle == Qt.TextAlignmentRole and (art == "berechnet" and x[2] is not None or art == "abweichung"
                                              or art == "feld" and x.art in ("zahl", "ganz")):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.BackgroundRole:
            if art == "status":
                return QBrush(_farbe_status(w) or (QColor("#FFF2CC") if str(w).startswith("HINWEIS") else FARBE_BERECHNET))
            if art == "abweichung" and w is not None:
                return QBrush(QColor("#FFF2CC"))
            return QBrush(FARBE_EINGABE if art in ("feld",) + EIGENE else FARBE_BERECHNET)
        if rolle == Qt.ForegroundRole and art == "status":
            return QBrush(QColor({"FEHLER": "#8C1D18", "WARNUNG": "#6B4A00"}.get(str(w).split(":")[0], "#1F2937")))
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
        p = self.daten[index.row()]
        try:
            wert = wert_aus_text(f, text)
        except ValueError as e:
            self.s.f.meldung(str(e), fehler=True)
            return False
        if wert == p.get(f.name):
            return False
        if f.name == "zeit_manuell" and p.get(f.name) is None and wert is not None \
                and self.zeiten[index.row()] is not None and abs(wert - round(self.zeiten[index.row()], 1)) < 0.05:
            return False                # berechnete Zeit unverändert bestätigt: bleibt berechnet
        if f.name == "preis_m":
            if wert is not None and wert <= 0:
                wert = None             # 0 = kein Preis von Hand
            berechnet = self.meterpreise[index.row()][0]
            if wert is not None and rechnen._n(p.get(f.name)) <= 0 and berechnet is not None \
                    and abs(wert - round(berechnet, 2)) < 0.005:
                return False            # berechneter Meterpreis unverändert bestätigt: bleibt berechnet
            if wert == p.get(f.name):
                return False
        self.s.db.position_aendern(p["id"], f.name, wert)
        if f.name in ("konturen", "kontur_grenzen"):     # Konturliste geändert: beim Neuladen neu einteilen
            self.s.db.position_aendern(p["id"], "kontur_grenzen", None)
        self.s.f.meldung(f"{f.titel} gespeichert.")
        self.geaendert.emit()
        return True


# ------------------------------------------------------------------ Stangenbild
class Stangenbild(QWidget):
    """Je Stangenmuster ein maßstäblicher Balken: Endbeschnitt grau, Teile farbig mit Pos. und Länge,
    dicke Linie = Schnitt, Rest hellgrau, Greiferrest rot."""
    ZEILE = 74

    def __init__(self):
        super().__init__()
        self.muster, self.farben = [], {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, ergebnis):
        self.muster = rechnen.stangenmuster(ergebnis)
        refs = []
        for s, _ in self.muster:
            for t in s["teile"]:
                if t["ref"] not in refs:
                    refs.append(t["ref"])
        self.farben = {r: QColor(FARBE_TEILE[i % len(FARBE_TEILE)]) for i, r in enumerate(refs)}
        self.setMinimumHeight(max(60, 20 + self.ZEILE * len(self.muster)))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        if not self.muster:
            p.drawText(self.rect(), Qt.AlignCenter, "Noch nicht optimiert.")
            return
        x0, breite = 10, max(200, self.width() - 20)
        klein = QFont(self.font())
        klein.setPointSizeF(max(7.0, klein.pointSizeF() - 1.5))
        fett = QFont(self.font())
        fett.setBold(True)
        for n, (s, nummern) in enumerate(self.muster):
            y = 10 + n * self.ZEILE
            p.setPen(QColor("#202020"))
            p.setFont(fett)
            anz = len(nummern)
            nr_text = ", ".join(map(str, nummern)) if anz <= 6 else f"{nummern[0]}–{nummern[-1]}"
            kopf = (f"{anz} × Stange {nr_text}: {s['profil']}  {rechnen.material_text(s['werkstoff'], s.get('oberflaeche'))}  {_z(s['stange'], 0)} mm")
            if any(t.get("ansicht") == "von oben" for t in s["teile"]):
                kopf += "  (Ansicht von oben)"
            p.drawText(x0, y + 12, kopf)
            summe = sum(t["laenge"] for t in s["teile"])
            rest = s["stange"] - s["end"] - summe - s["verlust"]
            p.setFont(klein)
            p.drawText(x0 + breite - 330, y, 330, 16, Qt.AlignRight | Qt.AlignVCenter,
                       f"{len(s['teile'])} Teile · Rest {_z(rest, 1)} mm · Ausnutzung {_z(100 * summe / s['stange'], 1)} %")
            m = breite / s["stange"]
            yb, hb = y + 20, 34

            def rechteck(von, bis, farbe, rand=QColor("#7F7F7F")):
                r = QRectF(x0 + von * m, yb, max(1.0, (bis - von) * m), hb)
                p.fillRect(r, farbe)
                p.setPen(QPen(rand, 1))
                p.drawRect(r)
                return r
            rechteck(0, s["stange"], QColor("#EDEDED"))                         # Rest
            rechteck(0, s["end"], QColor("#A6A6A6"))                             # Endbeschnitt
            rechteck(s["stange"] - s["greif"], s["stange"], QColor("#E06666"))   # Greiferrest
            for t in s["teile"]:
                if t.get("kante_a") or t.get("kante_b"):        # schräge Enden: Umriss mit Schnittkanten
                    ol, or_, ur, ul = rechnen.umriss(t)
                    form = QPolygonF([QPointF(x0 + ol * m, yb), QPointF(x0 + or_ * m, yb),
                                      QPointF(x0 + ur * m, yb + hb), QPointF(x0 + ul * m, yb + hb)])
                    p.setPen(QPen(QColor("#202020"), 2))
                    p.setBrush(self.farben.get(t["ref"], QColor("#4E79A7")))
                    p.drawPolygon(form)
                    p.setBrush(Qt.NoBrush)
                    r = QRectF(x0 + max(ol, ul) * m, yb, max(1.0, (min(or_, ur) - max(ol, ul)) * m), hb)
                else:
                    r = rechteck(t["von"], t["bis"], self.farben.get(t["ref"], QColor("#4E79A7")))
                    p.setPen(QPen(QColor("#202020"), 2))
                    p.drawLine(r.topLeft(), r.bottomLeft())
                    p.drawLine(r.topRight(), r.bottomRight())
                text = f"{t['pos'] if t['pos'] is not None else t['artikel']}\n{_z(t['laenge'], 1)}"
                if r.width() > 28:
                    p.setPen(QColor("white"))
                    p.drawText(r, Qt.AlignCenter, text if r.width() > 46 else str(t["pos"] or ""))
        p.end()


def laengen_html(erg, kopf, positionen, k, tabellen, einst):
    """Vergleich der Lieferlängen je Gruppe als HTML: Kennzahlen je Variante, Empfehlung mit Begründung und Links
    zum Übernehmen (laenge:<Gruppe>:<Länge>, 0 = Stangenlänge des Angebots)."""
    if not erg:
        return "<i>Noch nicht optimiert.</i>"
    if not erg.get("laengen"):
        return ("Für die Profile dieses Angebots gibt es keine weitere Lieferlänge: verglichen wird, was unter "
                "Einstellungen → Lieferlängen steht, und ohne Eintrag Profile über dem Hüllkreis-Ø aus den "
                "Einstellungen (Vorgabe 70 mm) mit 12 m. Kleinere Profile ohne Eintrag werden nie mit 12 m geplant.")
    zeilen = [("Benötigte Stangen", lambda v: _z(v["lieferstangen"], 0)),
              ("Beladungen der Maschine (Stangen)", lambda v: _z(v["werkstuecke"], 0)),
              ("Zuschnitte beim Lieferanten", lambda v: _z(v["zuschnitte"], 0) if v["zuschnitt"] else "–"),
              ("Stangenlängen nach Zuschnitt [mm]", lambda v: ", ".join(_z(l, 0) for l in v["werkstueck_laengen"]) or "–"),
              ("Materiallänge [m]", lambda v: _z(v["material_mm"] / 1000, 1)),
              ("Materialkosten [€]", lambda v: _z(v["material"])),
              ("Stangenwechsel / je Beladung [€]", lambda v: _z(v["werkstueck_kosten"])),
              ("Zuschnittkosten [€]", lambda v: _z(v["zuschnitt_kosten"]) if v["zuschnitt"] else "–"),
              ("Reststückwert [€]", lambda v: "nicht angerechnet"),
              ("<b>Gesamtkosten [€]</b>", lambda v: f"<b>{_z(v['gesamt'])}</b>"),
              ("Verschnitt [mm]", lambda v: _z(v["verschnitt_mm"], 0)),
              ("Verschnitt [%]", lambda v: _z(100 * v["verschnitt_anteil"], 1)),
              ("Angaben fehlen", lambda v: ", ".join(v["fehlt"]) or "–")]
    farbe = {rechnen.LAENGE_ALTERNATIVE: "#1E7B34", rechnen.LAENGE_NUR_ALTERNATIVE: "#1E7B34",
             rechnen.LAENGE_ANGABEN_FEHLEN: "#B45F06"}
    teile = []
    for i, vg in enumerate(erg["laengen"]):
        b = rechnen.laengen_bewerten(vg, kopf, positionen, k, tabellen, einst)
        geplant = vg.get("gewaehlt") or vg["stange"]
        kopfz = "".join(f"<th align='right'>{rechnen.m_text(v['laenge'])}-m-Variante"
                        + (" (geplant)" if v["laenge"] == geplant else "") + "</th>" for v in b["varianten"])
        if not vg["basis_lieferbar"]:
            kopfz = f"<th align='right'>{rechnen.m_text(vg['stange'])} m: nicht lieferbar</th>" + kopfz
        html = [f"<p><b>{vg['profil']} · {rechnen.material_text(vg['werkstoff'], vg.get('oberflaeche'))}</b> "
                f"(Stangenlänge des Angebots {_z(vg['stange'], 0)} mm, max. Beladelänge "
                f"{_z(vg.get('max_werkstueck'), 0) if vg.get('max_werkstueck') else '–'} mm)"
                + ("<br><i>12 m ohne Eintrag in Lieferlängen angenommen (Hüllkreis-Ø über der Grenze in den "
                   "Einstellungen), Preis wie unter Preise.</i>" if vg.get("automatisch") else "") + "</p>",
                "<table border='1' cellspacing='0' cellpadding='3'><tr><th align='left'>Kennzahl</th>" + kopfz + "</tr>"]
        for n, (titel, f) in enumerate(zeilen):
            # nicht ausführbare Variante: Grund in der ersten Zeile, sonst leer
            wert = lambda v: f(v) if not v["fehler"] else ("nicht ausführbar: " + v["fehler"] if n == 0 else "")
            zellen = "".join(f"<td align='right'>{wert(v)}</td>" for v in b["varianten"])
            if not vg["basis_lieferbar"]:
                zellen = "<td></td>" + zellen
            html.append(f"<tr><td>{titel}</td>{zellen}</tr>")
        html.append("</table>")
        html.append(f"<p><span style='color:{farbe.get(b['empfehlung'], '#202020')}'><b>{b['titel']}</b></span><br>"
                    f"{b['begruendung']}</p>")
        links = [f"<a href='laenge:{i}:{v['laenge']}'>{rechnen.m_text(v['laenge'])}-m-Stangen übernehmen</a>"
                 for v in b["varianten"] if v["laenge"] != geplant and v["laenge"] != vg["stange"] and not v["fehler"]]
        if geplant != vg["stange"] and vg["basis_lieferbar"]:
            links.append(f"<a href='laenge:{i}:0'>wieder {rechnen.m_text(vg['stange'])}-m-Stangen verwenden</a>")
        if links:
            html.append("<p>Geplant: " + f"{rechnen.m_text(geplant)} m. " + " · ".join(links) + "</p>")
        teile.append("".join(html))
    return "<hr>".join(teile)


def laengen_sinnvoll(erg, kopf, positionen, k, tabellen, einst):
    """Kurztext, wenn der Vergleich der Lieferlängen eine sinnvolle Lösung zeigt (eine andere Länge ist empfohlen
    oder nur sie ist lieferbar) oder schon eine andere Länge geplant ist; sonst None (Knopf ausgeblendet)."""
    texte = []
    for vg in (erg or {}).get("laengen") or []:
        b = rechnen.laengen_bewerten(vg, kopf, positionen, k, tabellen, einst)
        if vg.get("gewaehlt") and vg["gewaehlt"] != vg["stange"]:
            texte.append(f"{vg['profil']}: {rechnen.m_text(vg['gewaehlt'])} m geplant")
        elif b["empfehlung"] in (rechnen.LAENGE_ALTERNATIVE, rechnen.LAENGE_NUR_ALTERNATIVE):
            texte.append(f"{vg['profil']}: {b['titel']}")
    return " · ".join(texte) or None


class LaengenDialog(QDialog):
    """Vergleich der Lieferlängen (6 m gegen 12 m) groß in einem eigenen Fenster; Links übernehmen eine Länge."""

    def __init__(self, seite):
        super().__init__(seite)
        self.setWindowTitle("Lieferlängen: 6 m gegen 12 m")
        self.resize(1250, 820)
        lay = QVBoxLayout(self)
        self.ansicht = QTextBrowser()
        self.ansicht.setOpenLinks(False)
        self.ansicht.zoomIn(4)          # groß: bessere Übersicht als im Reiter
        self.ansicht.anchorClicked.connect(lambda url: seite.laenge_waehlen(url.toString()))
        lay.addWidget(self.ansicht, 1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)


# ------------------------------------------------------------------ Angebot
def _d(w):
    return float(w) if w is not None else None


def zukauf_zeilen(gruppen):
    """Zeilen der Tabelle Zukaufteile aus summen['zukauf'] (zukauf.rechnen): eine Zeile je Artikel und Preisstand."""
    out = []
    for g in gruppen:
        st, b = g["stand"], g["bestellung"]
        out.append(dict(artikel=st.get("artikelnr"), bezeichnung=st.get("bezeichnung"),
                        einheit=zukauf.EINHEIT_KURZ.get(st.get("einheit"), st.get("einheit")),
                        lieferant=b.get("lieferant"), positionen=g["positionen"], verbrauch=_d(b["verbrauch"]),
                        bestellt=_d(b["bestellt"]), mehrmenge=_d(b["mehrmenge"]) or None,
                        staffel=f"ab {zahl_als_text(float(b['staffel']['ab']), 0)}" if b.get("staffel") else None,
                        ek=_d(b["ek"]), einkauf=_d(b["einkauf"]), bezug=_d(b["bezug"]), einstand=_d(g["einstand"]),
                        regel=g["regel"], aufschlag=_d(g["aufschlag"]), vk=_d(g["vk"]),
                        db_pct=_d(g["aufschlag"] / g["vk"] * 100) if g["vk"] else None,
                        stand=datum_text(st.get("datum")),
                        hinweis=("FEHLER: " + g["fehler"]) if g["fehler"]
                        else ("WARNUNG: " + g["warnung"]) if g["warnung"] else ""))
    return out


def zukauf_info(summen):
    n = len(summen["zukauf"])
    if not n:
        return ("Keine Zukaufteile. Zukaufteile einer Position: Position markieren, dann 'Zukaufteile …' "
                "(oder Doppelklick in die Spalte Zukaufteile).")
    e, a = summen["zukauf_einstand"], summen["zukauf_aufschlag"]
    return (f"{n} Artikel · Einstand {_z(e)} € · Aufschlag {_z(a)} € · Verkauf {_z(e + a)} € (netto, ohne Skonto). "
            "Gleiche Artikel aller Positionen werden zusammen bestellt; gerechnet wird mit dem Preisstand, der in "
            "den Positionen gespeichert ist.")


ZUKAUF_SPALTEN = [("Artikelnr.", "artikel", None, 90), ("Bezeichnung", "bezeichnung", None, 180),
                  ("Einheit", "einheit", None, 50), ("Lieferant", "lieferant", None, 120),
                  ("Positionen", "positionen", 0, 70), ("Verbrauch", "verbrauch", 2, 75),
                  ("Bestellmenge", "bestellt", 2, 95), ("Mehrmenge", "mehrmenge", 2, 75),
                  ("Preisstaffel", "staffel", None, 75), ("EK je Einheit [€]", "ek", 4, 85),
                  ("Einkauf [€]", "einkauf", 2, 80), ("Bezugskosten [€]", "bezug", 2, 95),
                  ("Einstand [€]", "einstand", 2, 80), ("Aufschlagsregel", "regel", None, 170),
                  ("Aufschlag [€]", "aufschlag", 2, 80), ("Verkauf netto [€]", "vk", 2, 85),
                  ("Deckungsbeitrag [% vom VK]", "db_pct", 1, 110), ("Preisstand", "stand", None, 80),
                  ("Hinweis", "hinweis", None, 220)]
PROT_SPALTEN = [(t, (lambda i: lambda z: z[i] if i < len(z) else None)(i), None, 90) for i, t in enumerate(step.PROTOKOLL)]


KALK_IMMER = {"pos", "artikel", "stueck", "material_teil", "herstell_teil", "preis_teil", "preis_position"}
PLAN_GLEICH = {"profil", "werkstoff", "oberflaeche", "stange", "end", "greif"}   # einmal über dem Schnittplan
UEBERSICHT_MIN, UEBERSICHT_BREIT = 320, 400      # Breite der Übersicht rechts (1366 px bzw. ab 1700 px)


class AngebotSeite(QWidget):
    # Tastenkürzel (siehe tastatur.py); Entf nur in der Positionsliste
    KUERZEL = {"neu": "position_neu", "loeschen": ("positionen_loeschen", "pos_ansicht"),
               "rueckgaengig": "rueckgaengig", "wiederholen": "wiederholen", "einfuegen": "_einfuegen",
               "ausschneiden": "_ausschneiden", "optimieren": "optimieren", "drucken": "angebot_pdf",
               "importieren": "step_importieren"}

    def __init__(self, fenster, angebot_id):
        super().__init__()
        self.setAcceptDrops(True)       # STEP-Dateien und Ordner per Drag & Drop importieren
        self.f, self.db, self.id = fenster, fenster.db, angebot_id
        self.verlauf = Verlauf(self.db, angebot_id)     # Rückgängig/Wiederholen
        self._laden = False
        self.kopf, self.positionen, self.ergebnis = {}, [], None

        # Kopf und Kalkulationseinstellungen (links), Übersicht (rechts): siehe angebot_oben.py
        self.kopf_bereich = KopfBereich(self)
        self.felder = self.kopf_bereich.felder
        self.maschinenwerte = self.kopf_bereich.maschinenwerte
        self.uebersicht_bereich = UebersichtBereich()
        self.stand = self.uebersicht_bereich.stand
        self.uebersicht = self.uebersicht_bereich.uebersicht
        self.uebersicht_bereich.preise_knopf.clicked.connect(lambda _=False: self.preise_aktualisieren())
        oben_rahmen = QScrollArea()          # kleine Fenster: Kopf und Kalkulation scrollen
        oben_rahmen.setWidgetResizable(True)
        oben_rahmen.setFrameShape(QFrame.NoFrame)
        oben_rahmen.setWidget(self.kopf_bereich)
        # Übersicht als rechte Spalte über die ganze Höhe: Preise immer im Blick, die Reiter bekommen mehr Höhe
        self.uebersicht_rahmen = QScrollArea()
        self.uebersicht_rahmen.setWidgetResizable(True)
        self.uebersicht_rahmen.setFrameShape(QFrame.NoFrame)
        self.uebersicht_rahmen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.uebersicht_rahmen.setWidget(self.uebersicht_bereich)
        self.uebersicht_rahmen.setMinimumWidth(UEBERSICHT_MIN)

        # Aktionen: Hauptaktionen hervorgehoben, dann Bearbeiten, rechts Ausgabe und Weitere Aktionen
        self.leiste = UmbruchLeiste()     # bei schmalem Fenster rückt die Ausgabe in eine zweite Zeile
        leiste = self.leiste.links_layout
        for text, ziel in (("Neue Position", self.position_neu), ("STEP importieren …", lambda: self.step_importieren()),
                           ("Optimieren", self.optimieren), ("3D-Ansicht …", lambda: self.ansicht_3d())):
            b = QPushButton(text)
            b.setObjectName("primaer")
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            leiste.addWidget(b)
        leiste.addSpacing(12)
        for text, ziel in (("Zusatzarbeiten …", lambda: self.zusatzarbeiten()), ("Zukaufteile …", None),
                           ("Positionen löschen", self.positionen_loeschen)):
            b = QPushButton(text)
            if ziel is None:        # Auswahlmenü statt eines weiteren Knopfs: die Leiste wird nicht breiter
                menue = QMenu(b)
                menue.addAction("Zukaufteile bearbeiten …", lambda: self.zukaufteile())
                menue.addAction("Neuer Zukaufartikel …", lambda: self.zukauf_schnell())
                menue.addAction("EK eintragen …", lambda: self.zukauf_ek())
                b.setMenu(menue)
                b.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0px; }")
                self.zukauf_knopf = b
            else:
                b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            leiste.addWidget(b)
        leiste = self.leiste.rechts_layout
        leiste.addWidget(QLabel("Ausgabe:"))
        for text, ziel in (("Angebot (PDF)", self.angebot_pdf), ("Werkstattpapiere (PDF)", self.werkstatt_pdf),
                           ("Kalkulation (PDF)", self.kalkulation_pdf)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            leiste.addWidget(b)
        self.weitere = QPushButton("Weitere Aktionen")
        menue = QMenu(self.weitere)
        for text, ziel in (("Material per Outlook anfragen …", lambda: self.material_anfragen()),
                           ("Schneidweg berechnen …", lambda: self.schneidweg_berechnen()),
                           ("Schweißnaht …", lambda: self.schweissnaht()),
                           ("CSV-Export", self.csv_export), ("Ablage öffnen", self.f.ablage_oeffnen)):
            menue.addAction(text, lambda ziel=ziel: ziel())
        self.weitere.setMenu(menue)
        leiste.addWidget(self.weitere)

        # Positionen und Ergebnisse
        self.pos_modell = PositionenModell(self)
        self.pos_modell.geaendert.connect(self.neu_laden)
        self.pos_ansicht = _tabelle(self.pos_modell, sortieren=False)
        self.pos_ansicht.setItemDelegate(Auswahl(self.pos_modell, self.pos_ansicht))
        self.pos_ansicht.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                         | QAbstractItemView.AnyKeyPressed)
        self.pos_ansicht.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.pos_ansicht.setIconSize(QSize(64, 18))     # 3D-Vorschau in der Spalte Artikelnummer
        self.pos_ansicht.horizontalHeader().setStretchLastSection(True)
        for i, (art, x) in enumerate(self.pos_modell.spalten):
            self.pos_ansicht.setColumnWidth(i, x.breite if art in ("feld",) + EIGENE else (240 if art == "status" else 85))
        # Rechtsklick auf eine Position: Bearbeiten-Aktionen ohne weitere Knöpfe in der Leiste
        self.pos_ansicht.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pos_menue = QMenu(self.pos_ansicht)
        for text, ziel in (("Schneidweg berechnen …", lambda: self.schneidweg_berechnen()),
                           ("Schweißnaht …", lambda: self.schweissnaht()),
                           ("Zusatzarbeiten …", lambda: self.zusatzarbeiten()),
                           ("Zukaufteile bearbeiten …", lambda: self.zukaufteile()),
                           ("Positionen löschen", self.positionen_loeschen)):
            self.pos_menue.addAction(text, lambda ziel=ziel: ziel())
        self.pos_ansicht.customContextMenuRequested.connect(
            lambda punkt: self.pos_menue.exec(self.pos_ansicht.viewport().mapToGlobal(punkt)))
        self.pos_ansicht.doubleClicked.connect(
            lambda i: {"zusatz": self.zusatzarbeiten, "zukauf": self.zukaufteile,
                       "naht": self.schweissnaht}.get(
                self.pos_modell.spalten[i.column()][0], lambda _: None)([i.row()]))

        self.kalk = Liste(KALK_SPALTEN, max_stellen=2)
        self.stangen = Liste(STANGEN_SPALTEN)
        self.teile = Liste(TEIL_SPALTEN)
        self.ausw = Liste(AUSW_SPALTEN)
        self.fehler = Liste(FEHLER_SPALTEN)
        self.prot = Liste(PROT_SPALTEN)
        self.zukauf = Liste(ZUKAUF_SPALTEN)
        kalk_ansicht = self.kalk_ansicht = _tabelle(self.kalk)
        _breiten(kalk_ansicht, KALK_SPALTEN)
        self.summen = QLabel()
        self.summen.setWordWrap(True)
        self.summen.setObjectName("summenzeile")
        self.kalk_info = QLabel()
        self.kalk_info.setStyleSheet("color: #5F6B7A;")
        kalk_seite = QWidget()
        kl = QVBoxLayout(kalk_seite)
        kl.addWidget(self.summen)
        kl.addWidget(self.kalk_info)
        kl.addWidget(kalk_ansicht, 1)
        self.stangen_ansicht = _tabelle(self.stangen, sortieren=False)
        _breiten(self.stangen_ansicht, STANGEN_SPALTEN)
        self.stangen_ansicht.selectionModel().currentRowChanged.connect(self._stange_gewaehlt)
        teile_ansicht = self.teile_ansicht = _tabelle(self.teile, sortieren=False)
        _breiten(teile_ansicht, TEIL_SPALTEN)
        plan = QSplitter(Qt.Vertical)
        plan_oben = QWidget()
        po = QVBoxLayout(plan_oben)
        po.setContentsMargins(0, 4, 0, 0)
        self.plan_info = QLabel()           # was für alle Stangen gleich ist, steht nur hier einmal
        self.plan_info.setWordWrap(True)
        po.addWidget(self.plan_info)
        po.addWidget(self.stangen_ansicht, 1)
        plan_unten = QWidget()
        pu = QVBoxLayout(plan_unten)
        pu.setContentsMargins(0, 4, 0, 0)
        self.teile_titel = QLabel()
        pu.addWidget(self.teile_titel)
        pu.addWidget(teile_ansicht, 1)
        plan.addWidget(plan_oben)
        plan.addWidget(plan_unten)
        self.bild = Stangenbild()
        bild_rahmen = QScrollArea()
        bild_rahmen.setWidgetResizable(True)
        bild_rahmen.setWidget(self.bild)
        ausw_seite = QWidget()
        al = QVBoxLayout(ausw_seite)
        ausw_ansicht = _tabelle(self.ausw)
        _breiten(ausw_ansicht, AUSW_SPALTEN)
        fehler_ansicht = _tabelle(self.fehler)
        _breiten(fehler_ansicht, FEHLER_SPALTEN)
        al.addWidget(ausw_ansicht, 2)
        self.fehler_titel = QLabel()
        self.fehler_titel.setWordWrap(True)
        al.addWidget(self.fehler_titel)
        self.fehler_ansicht = fehler_ansicht
        al.addWidget(fehler_ansicht, 1)
        # Lieferlängen: Knopf nur bei einer sinnvollen Lösung, der Vergleich selbst groß im eigenen Fenster
        self.laengen_dialog = LaengenDialog(self)
        self.laengen_ansicht = self.laengen_dialog.ansicht
        lz = QHBoxLayout()
        self.laengen_knopf = QPushButton("12-m-Lösung ansehen …")
        self.laengen_knopf.setToolTip("Lieferlängen: 6 m gegen 12 m – Vergleich je Gruppe in einem großen Fenster")
        self.laengen_knopf.clicked.connect(self.laengen_zeigen)
        self.laengen_hinweis = QLabel()
        self.laengen_hinweis.setWordWrap(True)
        lz.addWidget(self.laengen_knopf)
        lz.addWidget(self.laengen_hinweis, 1)
        al.addLayout(lz)
        self.laengen_knopf.setVisible(False)
        self.laengen_hinweis.setVisible(False)
        zk_seite = QWidget()            # Zukaufteile: Bestellung je Artikel und Preisstand (ganzes Angebot)
        zl = QVBoxLayout(zk_seite)
        self.zukauf_info = QLabel()
        self.zukauf_info.setWordWrap(True)
        zl.addWidget(self.zukauf_info)
        self.zukauf_ansicht = _tabelle(self.zukauf)
        _breiten(self.zukauf_ansicht, ZUKAUF_SPALTEN)
        zl.addWidget(self.zukauf_ansicht, 1)
        prot_ansicht = _tabelle(self.prot)
        _breiten(prot_ansicht, PROT_SPALTEN)
        # Staffeln: Mengenstufen mit Werten je Stufe (Eingabe) und Kosten je Stufe (Ergebnis), siehe staffel_seite.py
        st_seite = StaffelSeite(self)
        self.staffel_modell, self.staffel_ansicht, self.staffel_info = st_seite.modell, st_seite.ansicht, st_seite.info

        self.reiter = QTabWidget()
        self.pos_seite = QWidget()            # Positionsliste mit Spaltenauswahl darüber
        self.pos_leiste = QHBoxLayout()
        self.pos_leiste.setContentsMargins(0, 0, 0, 0)
        pl = QVBoxLayout(self.pos_seite)
        pl.setContentsMargins(0, 4, 0, 0)
        pl.setSpacing(4)
        pl.addLayout(self.pos_leiste)
        pl.addWidget(self.pos_ansicht, 1)
        self.reiter.addTab(self.pos_seite, "Positionen")
        self.reiter.addTab(kalk_seite, "Kalkulation")
        self.zeiten_seite = ZeitenSeite(self)
        self.reiter.addTab(self.zeiten_seite, "Zeiten && Arbeitskosten")
        self.reiter.addTab(zk_seite, "Zukaufteile")
        self.reiter.addTab(plan, "Schnittplan")
        self.reiter.addTab(bild_rahmen, "Stangenbild")
        self.reiter.addTab(ausw_seite, "Auswertung")
        self.reiter.addTab(st_seite, "Staffeln")
        self.nachkalk = NachkalkulationSeite(self)
        self.reiter.addTab(self.nachkalk, "Nachkalkulation")
        self.reiter.addTab(prot_ansicht, "STEP-Protokoll")
        self.st_seite = st_seite

        # Spaltenauswahl der Positionsliste (Zeile über der Liste, Reiter behalten die volle Breite)
        el = self.pos_leiste
        self.pos_info = QLabel()
        self.pos_info.setStyleSheet("color: #5F6B7A;")
        self.spalten_knopf = QPushButton("Weitere Spalten")
        self.spalten_knopf.setToolTip("Optionale Spalten der Positionsliste ein- oder ausblenden. Spalten mit Werten "
                                      "erscheinen automatisch.")
        self.spalten_menue = QMenu(self.spalten_knopf)
        self.spalten_menue.aboutToShow.connect(self._spalten_menue_fuellen)
        self.spalten_knopf.setMenu(self.spalten_menue)
        self.zeige_step = QCheckBox("STEP-Werte (aus CAD)")
        self.zeige_step.setToolTip("Aus dem importierten CAD-Modell (STEP) gemessene Werte: Anfangs- und Endschnitt, "
                                   "Innenkonturen, Gravur, Bohrungen, Konturgrößen.")
        self.zeige_berechnet = QCheckBox("Berechnete Werte (Programm)")
        self.zeige_berechnet.setToolTip("Vom Programm ermittelte Werte: Profilform, Gewicht, wirksame Stangenlänge, "
                                        "Vorschub, eingeplante Teile usw.")
        el.addWidget(self.pos_info, 1)
        for w in (self.spalten_knopf, self.zeige_step, self.zeige_berechnet):
            el.addWidget(w)
        for c in (self.zeige_berechnet, self.zeige_step):
            c.toggled.connect(self._spalten_zeigen)

        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(self.leiste)
        ul.addWidget(self.reiter, 1)
        self.teiler = QSplitter(Qt.Vertical)
        self.teiler.addWidget(oben_rahmen)
        self.teiler.addWidget(unten)
        self.teiler.setStretchFactor(0, 0)
        self.teiler.setStretchFactor(1, 1)
        self.teiler.setChildrenCollapsible(False)
        self.spalten = QSplitter(Qt.Horizontal)       # links Kopf und Reiter, rechts die Übersicht
        self.spalten.addWidget(self.teiler)
        self.spalten.addWidget(self.uebersicht_rahmen)
        self.spalten.setStretchFactor(0, 1)
        self.spalten.setStretchFactor(1, 0)
        self.spalten.setChildrenCollapsible(False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 4)
        lay.addWidget(self.spalten, 1)
        self.spalten_wahl = self.db.einstellung(SPALTEN_EINSTELLUNG) or {}
        self.neu_laden()

    # -------------------------------------------------------------- Laden und Rechnen
    def titel(self):
        return f"Angebot {self.kopf.get('nummer') or ''}"

    def neu_laden(self, *_):
        a = self.db.angebot(self.id)
        if a is None:
            return
        if self.db.fracht_auto_nachfuehren(self.id):      # Haken 'Fracht automatisch berechnen': nach jeder Änderung
            a = self.db.angebot(self.id)
        self.kopf = a
        self.ergebnis = a["ergebnis"]
        self.positionen = self.db.positionen(self.id)
        # festgeschriebene Materialpreise und Schneiddaten gehen den aktuellen Stammdaten vor
        self.k_aktuell, self.tabellen_aktuell = self.db.kontext(), self.db.tabellen()
        self.k, self.tabellen = rechnen.preisbasis_anwenden(a, self.k_aktuell, self.tabellen_aktuell)
        self._konturen_einteilen()
        self.einst = rechnen.einstellungen_angebot(a, self.db.einstellungen())     # mit Werten des Angebots
        self.stufen = self.db.staffeln(self.id)
        self._kopf_anzeigen()
        self.pos_modell.rechnen()
        self._spalten_zeigen()
        self._ergebnisse_anzeigen()
        self.f.reiter_titel(self)
        self.verlauf.merken()

    def _konturen_einteilen(self):
        """Konturklassen neu einteilen, wenn die Regel (Grenzen und Faktoren der Maschine, Wandstärke des Profils) nicht
        die ist, mit der die Konturliste der Position eingeteilt wurde (andere Maschine oder anderes Profil gewählt,
        Grenzen in den Stammdaten geändert)."""
        m = rechnen.maschine(self.kopf, self.k)
        if m is None:
            return
        neu = [(p, z) for p in self.positionen
               if (z := rechnen.konturklassen_neu(p, m, rechnen.wand_position(p, self.k)))]
        for p, z in neu:
            for feld, wert in z.items():
                self.db.position_aendern(p["id"], feld, wert)
        if neu:
            self.positionen = self.db.positionen(self.id)
            self.f.meldung(f"Konturklassen von {len(neu)} Position(en) mit den Grenzen der Maschine "
                           f"{self.kopf.get('maschine')} ({neu[0][1]['kontur_grenzen']}) neu eingeteilt.")

    def _kopf_anzeigen(self):
        self._laden = True
        try:
            self.kopf_bereich.anzeigen()
            self.kopf_bereich.kopf_aufklappen(not self.kopf_bereich.kopf_ausgefuellt(), automatisch=True)
        finally:
            self._laden = False

    def resizeEvent(self, ereignis):
        super().resizeEvent(ereignis)
        self.kopf_bereich.breite_anpassen(ereignis.size().width())

    def showEvent(self, ereignis):
        super().showEvent(ereignis)
        if not getattr(self, "_teiler_gesetzt", False):
            self._teiler_gesetzt = True
            b = self.spalten.width()
            rechts = UEBERSICHT_BREIT if b >= 1700 else UEBERSICHT_MIN
            self.spalten.setSizes([max(b - rechts, 400), rechts])
            if self.teiler.height() < 700 and self.db.einstellung(KALK_OFFEN_EINSTELLUNG) is None:   # kleiner Bildschirm
                self.kopf_bereich.kalkulation_aufklappen(False)
            self._oben_anpassen_jetzt()

    def oben_anpassen(self):
        """Oberen Teil (Kopf, Kalkulation, Fracht) so hoch wie nötig, höchstens gut die Hälfte; nach dem Auf- oder
        Zuklappen des Angebotskopfs."""
        if getattr(self, "_teiler_gesetzt", False):
            QTimer.singleShot(0, self._oben_anpassen_jetzt)      # erst nach dem Layout des Auf- oder Zuklappens

    def _oben_anpassen_jetzt(self):
        h = self.teiler.height()
        self.kopf_bereich.adjustSize()
        oben = min(self.kopf_bereich.sizeHint().height() + 6, int(h * 0.55))
        self.teiler.setSizes([oben, max(h - oben, 200)])

    def _kopf_speichern(self, fd, wert):
        if self._laden or wert == self.kopf.get(fd.name):
            return
        vorher = self._verkauf() if fd.name in KALK_NAMEN else None
        try:
            self.db.angebot_aendern(self.id, fd.name, wert)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            self._kopf_anzeigen()
            return
        meldung = f"{fd.titel} gespeichert."
        a = self.db.angebot(self.id) or {}
        if fd.name.startswith("lieferzeit") and a.get("lieferzeit_art") == "Lieferdatum" and a.get("lieferzeit_wert") \
                and a["lieferzeit_wert"] < (a.get("datum") or ""):
            meldung += " Achtung: Das Lieferdatum liegt vor dem Angebotsdatum."
        self.neu_laden()
        if vorher is not None:          # Kalkulationswert: was sich am Preis ändert, in der Statuszeile
            meldung += f" {preis_aenderung(vorher, self._verkauf())}"
        self.f.meldung(meldung)

    def _verkauf(self):
        """Verkaufspreis netto des Angebots mit den gespeicherten Werten (None ohne Positionen)."""
        if not any(position_aktiv(p) for p in self.positionen):
            return None
        return self._rechnung()[1]["verkauf"]

    def material_fuer_alle(self, herkunft):
        """Material (Eigenmaterial / Kunde beigestellt) für alle Rohrlaserteil-Positionen setzen."""
        n = 0
        for p in self.positionen:
            if not ist_zukaufteil(p) and (p.get("material_herkunft") or EIGENMATERIAL) != herkunft:
                self.db.position_aendern(p["id"], "material_herkunft", herkunft)
                n += 1
        self.neu_laden()
        self.f.meldung(f"Material „{herkunft}“ für {n} Position(en) gesetzt." if n else
                       f"Alle Positionen haben schon „{herkunft}“.")
        return n

    def kalkulation_zuruecksetzen(self):
        """Kalkulationswerte, Stundensätze und Zeitvorgaben des Angebots auf die Einstellungen setzen; die Rückfrage
        nennt, was sich ändert."""
        kalk, zeiten = self.kopf_bereich.abweichungen()
        if not kalk and not zeiten:
            self.f.meldung("Alle Kalkulationswerte, Stundensätze und Zeitvorgaben entsprechen den Einstellungen.")
            return False
        liste = [f"{f.titel.split('[')[0].strip()}: {zahl_als_text(w, f.stellen)} → {zahl_als_text(std, f.stellen)}"
                 for f, w, std in kalk] + zeiten
        if not self.f.stumm and QMessageBox.question(
                self, "Kalkulation", "Diese Werte des Angebots auf die Einstellungen bzw. Stammdaten setzen?\n\n"
                + "\n".join(liste) + "\n\nVon Hand eingetragene Werte an den Positionen (Meterpreis, Schneidzeit, "
                "Zukaufteile) bleiben.") != QMessageBox.Yes:
            return False
        vorher = self._verkauf()
        self.db.kalkulation_zuruecksetzen(self.id)
        self.neu_laden()
        self.f.meldung(f"{len(liste)} Werte aus den Einstellungen übernommen. {preis_aenderung(vorher, self._verkauf())}")
        return True

    def fracht_berechnen(self):
        """Dialog 'Fracht berechnen' (fracht_seite.FrachtDialog); im stummen Betrieb (Tests) nur anlegen."""
        from .fracht_seite import FrachtDialog
        d = FrachtDialog(self)
        if not self.f.stumm:
            d.exec()
        return d

    def fracht_auto_setzen(self, an):
        """Haken 'Fracht automatisch berechnen': an = Ziel-PLZ (leer: aus dem Kunden) und Tarifkopie festhalten."""
        if self._laden or an == fracht_angebot.auto(self.kopf):
            return
        if an:
            if not self.kopf.get("fracht_plz"):
                plz, land = fracht_angebot.ziel_aus_kunde(self.db.kunde(self.kopf.get("kundennr")))
                self.db.angebot_aendern(self.id, "fracht_plz", plz or None)
                self.db.angebot_aendern(self.id, "fracht_land", land)
            self.db.angebot_aendern(self.id, "fracht_auto", "ja")
            self._fracht_auto_rechnen()
        else:
            self.db.angebot_aendern(self.id, "fracht_auto", None)
            self.f.meldung("Fracht wird nicht mehr automatisch berechnet (letzter Betrag bleibt).")
        self.neu_laden()

    def fracht_ziel_setzen(self, plz, land):
        """Ziel-PLZ und Land der automatischen Fracht ändern (neue Zone und Tarifkopie)."""
        plz = "".join(str(plz or "").split()).upper() or None
        land = (land or "").strip().upper() or "DE"
        if self._laden or (plz == self.kopf.get("fracht_plz") and land == (self.kopf.get("fracht_land") or "DE")):
            return
        self.db.angebot_aendern(self.id, "fracht_plz", plz)
        self.db.angebot_aendern(self.id, "fracht_land", land)
        if fracht_angebot.auto(self.kopf):
            self._fracht_auto_rechnen()
        self.neu_laden()

    def _fracht_auto_rechnen(self):
        d = self.db.fracht_auto_aktualisieren(self.id)
        if d.get("fehler"):
            self.f.meldung("Fracht nicht berechnet: " + d["fehler"], fehler=True)
        else:
            self.f.meldung(f"Fracht automatisch berechnet: {d.get('text')}.")

    def kunde_waehlen(self, kundennr):
        """Kundennummer übernehmen; steht der Kunde im Kundenstamm, auch Name und Zahlungsbedingungen."""
        kundennr = (kundennr or "").strip() or None
        if self._laden or kundennr == self.kopf.get("kundennr"):
            return
        k = self.db.kunde_uebernehmen(self.id, kundennr)
        self.f.meldung(f"Kunde {k['name']} übernommen (Name und Zahlungsbedingungen)." if k
                       else "Kundennummer gespeichert (nicht im Kundenstamm).")
        if k and fracht_angebot.auto(self.kopf):     # automatische Fracht: Ziel des neuen Kunden
            plz, land = fracht_angebot.ziel_aus_kunde(k)
            if plz:
                self.db.angebot_aendern(self.id, "fracht_plz", plz)
                self.db.angebot_aendern(self.id, "fracht_land", land)
            self._fracht_auto_rechnen()
        self.neu_laden()

    def stand_optimierung(self):
        if not self.ergebnis:
            return "noch nicht optimiert"
        aktuell = rechnen.eingabe_kennung(self.kopf, self.positionen, self.k, self.tabellen, self.einst) \
            == self.ergebnis.get("kennung")
        return "aktuell" if aktuell else "VERALTET – Angebot oder Stammdaten geändert, bitte neu optimieren"

    def _ergebnisse_anzeigen(self):
        self.uebersicht_bereich.stand_setzen(self.stand_optimierung())
        self.uebersicht_bereich.preisstand_setzen(
            self.kopf.get("preisbasis"), rechnen.preisbasis_abweichung(self.kopf, self.k_aktuell, self.tabellen_aktuell))
        erg = self.ergebnis
        zeilen, summen = rechnen.kalkulation(self.kopf, self.positionen, erg, self.k, self.tabellen, self.einst)
        self.kalk.setzen([z for z in zeilen if z])
        stat = self.pos_modell.status
        teile = sum(p.get("stueck") or 0 for p in self.positionen)
        gewicht = sum(w["gewicht_position"] or 0 for w in self.pos_modell.werte)
        self.uebersicht_bereich.kennzahlen_setzen(dict(
            positionen=str(sum(1 for s in stat if s)), stueck=f"{_z(teile, 0)} Stk",
            gewicht=f"{_z(gewicht)} kg"))
        self.uebersicht_bereich.meldungen_setzen(
            [(p.get("pos"), st) for p, st in zip(self.positionen, stat) if st.startswith(("FEHLER", "WARNUNG", "HINWEIS"))])
        kosten = rechnen.kostenarten(summen, self.einst)
        self.uebersicht_bereich.kosten_setzen(kosten)
        self.uebersicht_bereich.zeiten_setzen(rechnen.zeit_summen(summen["zeiten"]))
        self.zeiten_seite.setzen(summen)
        self.zukauf.setzen(zukauf_zeilen(summen["zukauf"]))
        self.zukauf_info.setText(zukauf_info(summen))
        self.summen.setText(" · ".join(f"<b>{t} {_z(w)} €</b>" if fett else f"{t} {_z(w)} €"
                                       for t, w, fett in kosten if fett or sichtbar(w)))
        n = leere_ausblenden(self.kalk_ansicht, self.kalk, KALK_IMMER)
        self.kalk_info.setText(f"{len(self.kalk.zeilen)} Positionen · Beträge auf 2 Stellen (genauer Wert im "
                               f"Tooltip)" + (f" · {n} Spalten ohne Werte ausgeblendet" if n else ""))
        if erg:
            sw = rechnen.stangen_werte(erg, self.kopf, self.positionen, self.k, self.tabellen)
            # Schnittplan wie geladen: zugeschnittene Lieferstangen als ihre Werkstücke
            self.stangen.setzen([dict(s, **w) for s, w in rechnen.anzeige_stangen(erg, sw)])
            ausw = rechnen.auswertung_zeilen(erg, sw)
            self.ausw.setzen(ausw)
            self.fehler.setzen(erg["fehler"])
        else:
            self.stangen.setzen([])
            self.ausw.setzen([])
            self.fehler.setzen([])
        gleich = gleiche_ausblenden(self.stangen_ansicht, self.stangen, PLAN_GLEICH)
        self.plan_info.setText(f"{len(self.stangen.zeilen)} Stangen" + (" · für alle gleich: " + " · ".join(gleich)
                                                                          if gleich else "")
                               if self.stangen.zeilen else "Noch nicht optimiert.")
        self.fehler_titel.setText(
            "" if not erg else "<span style='color:#1E6B34'><b>✓ Alle Teile eingeplant.</b></span>"
            if not erg["fehler"] else f"<span style='color:#B42318'><b>Nicht eingeplante Teile "
                                      f"({len(erg['fehler'])})</b></span>")
        self.fehler_ansicht.setVisible(bool(erg and erg["fehler"]))
        self.teile.setzen([])
        self.laengen_ansicht.setHtml(laengen_html(erg, self.kopf, self.positionen, self.k, self.tabellen, self.einst))
        hinweis = laengen_sinnvoll(erg, self.kopf, self.positionen, self.k, self.tabellen, self.einst)
        self.laengen_knopf.setVisible(bool(hinweis))
        self.laengen_hinweis.setVisible(bool(hinweis))
        self.laengen_hinweis.setText(f"<b>Lieferlängen:</b> {hinweis}" if hinweis else "")
        self.bild.setzen(dict(erg, stangen=rechnen.anzeige_stangen(erg)) if erg else erg)
        self.prot.setzen(self.db.protokoll(self.id))
        self.st_seite.setzen()
        self.nachkalk.neu_laden()
        if self.stangen.zeilen:          # Teile der ersten Stange gleich zeigen, nicht erst nach einem Klick
            zeile = max(self.stangen_ansicht.currentIndex().row(), 0)
            self.stangen_ansicht.selectRow(min(zeile, len(self.stangen.zeilen) - 1))
            self._stange_gewaehlt(self.stangen_ansicht.currentIndex())

    def _stange_gewaehlt(self, aktuell, _=None):
        if not aktuell.isValid() or not self.ergebnis:
            self.teile.setzen([])
            self.teile_titel.setText("")
            return
        zeile = self.stangen_ansicht.model().mapToSource(aktuell).row() if hasattr(
            self.stangen_ansicht.model(), "mapToSource") else aktuell.row()
        s = rechnen.anzeige_stangen(self.ergebnis)[zeile]     # in der Liste ist 'teile' die Anzahl
        self.teile.setzen([dict(t, platz=i) for i, t in enumerate(s["teile"], start=1)])
        leere_ausblenden(self.teile_ansicht, self.teile, {"platz", "pos", "artikel", "laenge", "von", "bis"})
        self.teile_titel.setText(f"<b>Teile auf Stange {s.get('nr') or zeile + 1}</b> (Stange oben wählen)")

    def _spalten_zeigen(self):
        """Sichtbare Spalten der Positionsliste: Standardspalten immer, optionale Spalten mit Werten oder nach Wahl
        unter 'Weitere Spalten', STEP-Werte und berechnete Werte über die Häkchen."""
        m = self.pos_modell
        neu = set()
        for i, (art, x) in enumerate(m.spalten):
            name = m.name(i)
            if art == "berechnet":
                zeigen = self.zeige_berechnet.isChecked()
            elif art == "feld" and x.name in STEP_FELDER:
                zeigen = self.zeige_step.isChecked()
            elif art == "abweichung":
                zeigen = self.zeige_step.isChecked() or self._spalte_hat_werte(i)
            elif name in OPTIONALE_SPALTEN:
                zeigen = self.spalten_wahl.get(name, self._spalte_hat_werte(i))
            else:
                zeigen = True
            if zeigen and self.pos_ansicht.isColumnHidden(i):
                neu.add(i)
            self.pos_ansicht.setColumnHidden(i, not zeigen)
        if neu and self.pos_ansicht.auto_groesse.eingepasst:     # neu gezeigte Spalten einpassen (sonst beim Füllen)
            self.pos_ansicht.auto_groesse.einpassen(neu)
        aus = sum(1 for i, (art, _) in enumerate(m.spalten) if m.name(i) in OPTIONALE_SPALTEN
                  and self.pos_ansicht.isColumnHidden(i))
        n = sum(1 for p in self.positionen if position_aktiv(p) or p.get("artikel"))
        self.pos_info.setText(f"{n} {'Position' if n == 1 else 'Positionen'}"
                              + (f" · {aus} optionale Spalten ausgeblendet (Weitere Spalten)" if aus else ""))

    def _spalte_hat_werte(self, c):
        return spalte_sichtbar([self.pos_modell.roh(r, c) for r in range(self.pos_modell.rowCount())])

    def _spalten_menue_fuellen(self):
        m, menue = self.pos_modell, self.spalten_menue
        menue.clear()
        for i, (art, x) in enumerate(m.spalten):
            name = m.name(i)
            if name not in OPTIONALE_SPALTEN:
                continue
            a = menue.addAction(x.titel + ("" if self._spalte_hat_werte(i) else "  (leer)"))
            a.setCheckable(True)
            a.setChecked(not self.pos_ansicht.isColumnHidden(i))
            a.toggled.connect(lambda an, name=name: self.spalte_waehlen(name, an))
        menue.addSeparator()
        menue.addAction("Automatisch: Spalten mit Werten zeigen", lambda: self.spalte_waehlen(None, None))

    def spalte_waehlen(self, name, zeigen):
        """Optionale Spalte fest ein- (True) oder ausblenden (False); name=None: alle wieder automatisch."""
        if name is None:
            self.spalten_wahl = {}
        else:
            self.spalten_wahl[name] = zeigen
        self.db.einstellung_setzen(SPALTEN_EINSTELLUNG, self.spalten_wahl)
        self._spalten_zeigen()

    # -------------------------------------------------------------- Bearbeiten
    def position_neu(self):
        vorher = [p["pos"] for p in self.positionen if isinstance(p.get("pos"), (int, float))]
        self.db.position_neu(self.id, {"pos": int(max(vorher, default=0)) + 10})
        self.neu_laden()
        r = len(self.positionen) - 1
        i = self.pos_modell.index(r, 1)
        self.reiter.setCurrentIndex(0)
        self.pos_ansicht.scrollTo(i)
        self.pos_ansicht.setCurrentIndex(i)
        self.pos_ansicht.edit(i)

    def zusatzarbeiten(self, zeilen=None, werte=None):
        """Gewinde und Zusatzarbeiten der markierten Positionen wählen (Dialog). werte = (Gewinde, JSON) setzt
        sie ohne Dialog (Tests, Bildschirmfotos). Ergebnis: True = gespeichert."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.f.meldung("Bitte zuerst die Position(en) markieren.", fehler=True)
            return False
        if werte is None:
            d = ZusatzDialog(self, self.positionen[zeilen[0]], len(zeilen), self.k, self.tabellen,
                            self.db.zusatz_haeufigkeit())
            if d.exec() != QDialog.Accepted:
                return False
            werte = d.ergebnis
        gewinde, zusatz = werte
        for r in zeilen:
            p = self.positionen[r]
            self.db.position_aendern(p["id"], "gewinde", gewinde)
            self.db.position_aendern(p["id"], "zusatz", zusatz)
        self.f.meldung(f"Zusatzarbeiten für {len(zeilen)} Position(en) gespeichert.")
        self.neu_laden()
        return True

    def schneidweg_berechnen(self, zeile=None, eingaben=None, dialog=None, ueberschreiben=None):
        """Schneidweg-Rechner für die markierte Position (Dialog): Enden, Konturen und Gravur eingeben, Werte in die
        Position übernehmen. eingaben = dict setzt sie ohne Dialog, dialog(d) bedient den Dialog statt exec,
        ueberschreiben = True/False beantwortet die Rückfrage bei STEP-Werten (Tests). Ergebnis: True = gespeichert."""
        if zeile is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
            if len(zeilen) != 1:
                self.f.meldung("Bitte genau eine Position markieren.", fehler=True)
                return False
            zeile = zeilen[0]
        p = self.positionen[zeile]
        profil = self.k.profile.get(p.get("profil_id"))
        if ist_zukaufteil(p) or not profil:
            self.f.meldung("Schneidweg-Rechner: Die Position braucht ein Profil aus den Stammdaten (kein Zukaufteil).",
                           fehler=True)
            return False
        if eingaben is None:
            d = SchneidwegDialog(self, p, profil, self.kopf, self.k, self.tabellen, self.db, self.positionen)
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                return False
            eingaben = d.eingaben()
        grenzen = rechnen.kontur_regel(rechnen.maschine(self.kopf, self.k), rechnen.wand_schneiden(profil))
        erg = schneidweg.rechnen(eingaben, profil, grenzen, gewinde_liste(self.tabellen))
        if erg["fehler"]:
            self.f.meldung("Schneidweg-Rechner: " + " ".join(erg["fehler"]), fehler=True)
            return False
        step_werte = p.get("a_schnitt") is not None and schneidweg.lesen(p.get("technik")).get("quelle") != \
            schneidweg.QUELLE
        if step_werte:
            if ueberschreiben is None:
                ueberschreiben = self.f.stumm or QMessageBox.question(
                    self, "Schneidweg", "Die Position hat Werte aus dem STEP-Import (Schneidweg, Enden, Konturen). "
                    "Durch die Werte des Schneidweg-Rechners ersetzen?") == QMessageBox.Yes
            if not ueberschreiben:
                return False
        for name, wert in dict(erg["felder"], technik=schneidweg.speichern(eingaben)).items():
            self.db.position_aendern(p["id"], name, wert)
        self.f.meldung(f"Pos. {p.get('pos') or ''}: Schneidweg {rechnen.zahl(erg['schneidweg'], 1)} mm, "
                       f"{erg['einstiche']} Einstiche aus dem Schneidweg-Rechner übernommen.")
        self.neu_laden()
        return True

    def schweissnaht(self, zeilen=None, werte=None, dialog=None):
        """Schweißnaht der markierten Positionen wählen (Dialog mit Querschnitt). werte = dict der Nahtfelder setzt
        sie ohne Dialog; dialog(d) bedient den Dialog statt exec (Tests, Bildschirmfotos). Ergebnis: True = gespeichert."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        zeilen = [z for z in zeilen if not ist_zukaufteil(self.positionen[z])]
        if not zeilen:
            self.f.meldung("Bitte zuerst die Rohrlaserteil-Position(en) markieren.", fehler=True)
            return False
        p = self.positionen[zeilen[0]]
        if werte is None:
            d = NahtDialog(self, p, self.k.profile.get(p.get("profil_id")), len(zeilen))
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                return False
            werte = d.werte()
        for z in zeilen:
            for name, wert in werte.items():
                self.db.position_aendern(self.positionen[z]["id"], name, wert)
        self.f.meldung(f"Schweißnaht für {len(zeilen)} Position(en) gespeichert.")
        self.neu_laden()
        return True

    def zukaufteile(self, zeilen=None, werte=None, dialog=None):
        """Zukaufteile der markierten Positionen wählen (Dialog). werte = JSON (oder None) setzt sie ohne Dialog;
        dialog(d) bedient den Dialog statt exec (Tests, Bildschirmfotos). Ergebnis: True = gespeichert."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.f.meldung("Bitte zuerst die Position(en) markieren.", fehler=True)
            return False
        if werte is None:
            d = ZukaufDialog(self, self.db, self.positionen[zeilen[0]], len(zeilen))
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                return False
            werte = d.ergebnis
        for r in zeilen:
            self.db.position_aendern(self.positionen[r]["id"], "zukauf", werte)
        self.f.meldung(f"Zukaufteile für {len(zeilen)} Position(en) gespeichert.")
        self.neu_laden()
        return True

    def zukauf_schnell(self, zeilen=None, dialog=None):
        """Neue Zukaufartikel schnell anlegen (z. B. Bleche): jeder wird eine eigene Position der Art Zukaufteil.
        Die Menge bezieht sich auf die erste markierte Position: 'je Satz' = gleicher Satz mit Menge als Stück je
        Satz, 'je Teil' = Menge × Stückzahl der markierten Position; ohne Markierung ist sie die Stückzahl.
        dialog(d) bedient den Dialog statt exec (Tests). Ergebnis: Anzahl neuer Positionen."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        bezug = self.positionen[zeilen[0]] if zeilen else None
        satz = str((bezug or {}).get("satz") or "").strip()
        if bezug is None:
            hinweis = "Jeder Artikel wird eine eigene Position (Zukaufteil) mit dieser Stückzahl."
        else:
            hinweis = (f"Jeder Artikel wird eine eigene Position (Zukaufteil). Bezug Pos. {bezug.get('pos') or ''}: "
                       + (f"je Satz = Stück je Satz {satz}, " if satz else "")
                       + "je Teil = Menge × Stückzahl dieser Position.")
        d = SchnellDialog(self, self.db, bool(satz), ganz=True, hinweis=hinweis, ohne_je=bezug is None)
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or not d.ergebnis:
            return 0
        nr = int(max((p["pos"] for p in self.positionen if isinstance(p.get("pos"), (int, float))), default=0))
        for x in d.ergebnis:
            nr += 10
            menge = int(x["menge"])
            p = dict(pos=nr, art=ZUKAUFTEIL, artikel=x["artikelnr"] or x["bezeichnung"], bezeichnung=x["bezeichnung"],
                     zukauf=json.dumps([dict(artikel_id=x["artikel_id"], menge=1, stand=self.db.zukauf_stand(
                         x["artikel_id"]))], ensure_ascii=False))
            if bezug is None:
                p["stueck"] = menge
            elif x["je"] == zukauf.JE_SATZ and satz:
                saetze = zukauf.bezugsmenge(dict(je=zukauf.JE_SATZ), bezug)
                p.update(satz=bezug.get("satz"), je_satz=menge, stueck=round(saetze * menge) or None)
            else:
                s = bezug.get("stueck")
                p["stueck"] = round(s * menge) if isinstance(s, (int, float)) and s > 0 else None
            self.db.position_neu(self.id, p)
        self.f.meldung(f"{len(d.ergebnis)} Zukaufartikel angelegt, je als eigene Position (Zukaufteil).")
        self.neu_laden()
        return len(d.ergebnis)

    def zukauf_ek(self, zeilen=None, preise=None, dialog=None):
        """Einkaufspreise der Zukaufteile im Angebot eintragen (z. B. Bleche aus dem STEP-Import ohne EK): markierte
        Positionen, ohne Markierung alle Zukaufteile ohne EK. Der Preis wird im Artikel beim Lieferanten des
        Preisstands (sonst zukauf.BLECH_LIEFERANT) als Staffelzeile 'ab Stückzahl der Position' gespeichert und die
        Position bekommt den neuen Preisstand. preise = [Preis je Zeile oder None] statt Dialog; dialog(d) bedient den
        Dialog statt exec (Tests). Ergebnis: Anzahl eingetragener Preise."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        liste = zukauf_ek.zeilen([(r, self.positionen[r]) for r in (zeilen or range(len(self.positionen)))],
                                 nur_fehlend=not zeilen)
        if not liste:
            self.f.meldung("Keine Zukaufteile ohne EK gefunden." if not zeilen
                           else "Die markierten Positionen haben keine Zukaufteile.", fehler=True)
            return 0
        if preise is None:
            d = zukauf_ek.EkDialog(self, liste)
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                return 0
            paare = d.ergebnis
        else:
            paare = [(z, w) for z, w in zip(liste, preise) if w]
        nummer = self.kopf.get("nummer") or ""
        geaendert = {}
        for z, preis in paare:
            menge = float(z["menge"])
            menge = int(menge) if menge.is_integer() else menge
            lief = z["lieferant"] or zukauf.BLECH_LIEFERANT["Blechteile"]
            self.db.zukauf_ek_eintragen(z["artikel_id"], preis, lief, ab=menge,
                                        bemerkung=f"EK aus Angebot {nummer} (ab {menge} St)".replace("  ", " "))
            p = self.positionen[z["zeile"]]
            liste_p = geaendert.setdefault(z["zeile"], zukauf.json_liste(p.get("zukauf")))
            liste_p[z["nr"]]["stand"] = self.db.zukauf_stand(z["artikel_id"], lief)
        for r, liste_p in geaendert.items():
            self.db.position_aendern(self.positionen[r]["id"], "zukauf", json.dumps(liste_p, ensure_ascii=False))
        self.f.meldung(f"EK für {len(paare)} Zukaufteil(e) eingetragen und im Artikel gespeichert.")
        self.neu_laden()
        return len(paare)

    # -------------------------------------------------------------- Rückgängig, Einfügen (Tastenkürzel)
    def rueckgaengig(self):
        return self._verlauf_schritt(self.verlauf.rueckgaengig, "Rückgängig", "Nichts mehr rückgängig zu machen.")

    def wiederholen(self):
        return self._verlauf_schritt(self.verlauf.wiederholen, "Wiederholt", "Nichts zu wiederholen.")

    def _verlauf_schritt(self, schritt, wort, nichts):
        was = schritt()
        if was is None:
            self.f.meldung(nichts, fehler=True)
            return None
        aktuell = self.pos_ansicht.currentIndex()
        self.pos_modell.bilder.clear()
        self.neu_laden()
        if aktuell.isValid() and aktuell.row() < self.pos_modell.rowCount():
            self.pos_ansicht.setCurrentIndex(self.pos_modell.index(aktuell.row(), aktuell.column()))
        self.f.meldung(f"{wort}: {was}")
        return was

    def _gesammelt(self, aendern):
        """Mehrere Zellen ändern, einmal neu rechnen, ein Schritt für Rückgängig."""
        self.verlauf.pause += 1
        self.pos_modell.blockSignals(True)
        try:
            n = aendern(self.pos_ansicht)
        finally:
            self.pos_modell.blockSignals(False)
            self.verlauf.pause -= 1
        if n:
            self.neu_laden()
        self.f.meldung(f"{n} Zelle(n) geändert." if n else "Keine bearbeitbare Zelle.", fehler=not n)
        return n

    def _einfuegen(self, text=None):
        if QApplication.focusWidget() is not self.pos_ansicht and text is None:
            return False                        # andere Tabelle: allgemeines Einfügen im Hauptfenster
        return self._gesammelt(lambda v: tastatur.einfuegen(v, text))

    def _ausschneiden(self):
        if QApplication.focusWidget() is not self.pos_ansicht:
            return False
        tastatur.kopieren(self.pos_ansicht)
        return self._gesammelt(tastatur.leeren)

    def positionen_loeschen(self):
        zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.f.meldung("Bitte zuerst die Positionen markieren, die gelöscht werden sollen.", fehler=True)
            return
        if self.f.stumm or QMessageBox.question(self, "Löschen", f"{len(zeilen)} Position(en) löschen?") == QMessageBox.Yes:
            self.db.positionen_loeschen([self.positionen[r]["id"] for r in zeilen])
            self.neu_laden()

    def optimieren(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            erg = rechnen.optimieren(self.kopf, self.positionen, self.k, self.tabellen, self.einst)
        except ValueError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Optimieren", str(e))
            return False
        except AssertionError as e:   # Kontrolle der Optimierung angeschlagen: nie ein falsches Ergebnis speichern
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Optimieren", f"Die Kontrolle der Optimierung hat angeschlagen: {e}")
            return False
        QApplication.restoreOverrideCursor()
        if erg["neue_profile"]:
            self.db.profile_anlegen(erg["neue_profile"])
            erg["kennung"] = rechnen.eingabe_kennung(self.kopf, self.positionen, self.db.kontext(), self.tabellen,
                                                     self.einst)
        self.db.ergebnis_speichern(self.id, erg)
        self.neu_laden()
        n_teile = sum(len(s["teile"]) for s in erg["stangen"])
        text = f"{len(erg['stangen'])} Stangen, {n_teile} Teile eingeplant"
        if erg["fehler"]:
            text += f", {sum(f['anzahl'] for f in erg['fehler'])} Teile nicht eingeplant (siehe Auswertung)"
        if erg["neue_profile"]:
            text += f", {len(erg['neue_profile'])} Profil(e) aus dem Namen angelegt"
        self.f.meldung(text + ".")
        return True

    def laengen_zeigen(self):
        """Vergleich der Lieferlängen im großen Fenster öffnen."""
        self.laengen_dialog.show()
        self.laengen_dialog.raise_()
        self.laengen_dialog.activateWindow()

    def laenge_waehlen(self, link):
        """Link 'laenge:<Gruppe>:<Länge>' aus dem Vergleich der Lieferlängen: Länge für die Gruppe übernehmen (0 = wieder
        die Stangenlänge des Angebots), speichern und neu optimieren."""
        try:
            _, i, laenge = link.split(":")
            vg = self.ergebnis["laengen"][int(i)]
            laenge = int(laenge)
        except (ValueError, IndexError, KeyError, TypeError):
            return False
        wahl = dict(self.kopf.get("laengenwahl") or {})
        if laenge:
            wahl[vg["schluessel"]] = laenge
        else:
            wahl.pop(vg["schluessel"], None)
        self.db.laengenwahl_speichern(self.id, wahl)
        self.neu_laden()
        ok = self.optimieren()
        if ok:
            self.f.meldung(f"{vg['profil']} / {vg['werkstoff']}: " + (
                f"{rechnen.m_text(laenge)}-m-Stangen übernommen, Schnittplan neu optimiert." if laenge else
                f"wieder mit {rechnen.m_text(vg['stange'])}-m-Stangen geplant, Schnittplan neu optimiert."))
        return ok

    # -------------------------------------------------------------- Staffeln (staffel_seite.py)
    def staffel_neu(self):
        self.st_seite.neu()

    def staffeln_aus_angebot(self):
        return self.st_seite.aus_angebot()

    def staffeln_loeschen(self):
        self.st_seite.loeschen()

    def _staffel_stand(self):
        self.st_seite.stand()

    def staffelpreise_rechnen(self):
        """Alle Stufen neu rechnen und speichern. Ergebnis: bepreiste Zeilen oder None (abgebrochen)."""
        return self.st_seite.rechnen()

    def staffelpreise_aktuell(self):
        """Staffelpreise fürs Angebot; veraltete werden vorher neu gerechnet. None = abgebrochen."""
        return self.st_seite.aktuell()

    # -------------------------------------------------------------- Ausgabe (PDF, CSV)
    def _vor_ausgabe(self):
        """Bei veralteter Optimierung fragen, bei nicht berechneter automatischer Fracht warnen. True = weiter."""
        if fracht_angebot.auto(self.kopf):
            _, summen = self._rechnung()
            if summen.get("fracht_fehler"):
                if self.f.stumm:
                    self.f.meldung(summen["fracht_fehler"] + " – Angebot ohne Fracht.", fehler=True)
                elif QMessageBox.question(self, "Fracht", f"{summen['fracht_fehler']}.\n\nDas Angebot enthält dann "
                                          "keine Fracht. Trotzdem weiter?") != QMessageBox.Yes:
                    return False
        if self.stand_optimierung() == "aktuell":
            return True
        if self.f.stumm:
            return self.optimieren()
        a = QMessageBox.question(self, "Optimierung veraltet",
                                 "Der Schnittplan passt nicht mehr zum Angebot (oder es wurde noch nicht optimiert).\n\n"
                                 "Jetzt neu optimieren?\nJa = optimieren, Nein = mit dem bisherigen Stand weiter",
                                 QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if a == QMessageBox.Cancel:
            return False
        return self.optimieren() if a == QMessageBox.Yes else True

    def _ziel(self, zusatz, endung, mit_kunde=False):
        try:
            return self.f.ablage() / (ausgabe.dateiname(self.kopf, zusatz, mit_kunde) + endung)
        except OSError as e:
            QMessageBox.warning(self, "Ablage", f"Der Ablageordner lässt sich nicht anlegen:\n{e}")
            return None

    def _schreiben(self, art, pfad, schreiben):
        """Datei schreiben und öffnen. Ergebnis: Pfad oder None."""
        if pfad is None:
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            schreiben(pfad)
        except PermissionError:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, art, f"Die Datei konnte nicht gespeichert werden:\n{pfad}\n\n"
                                "Ist sie noch in einem anderen Programm geöffnet?")
            return None
        QApplication.restoreOverrideCursor()
        self.f.meldung(f"{art} gespeichert: {pfad}")
        self.f.datei_oeffnen(pfad)
        return pfad

    def _rechnung(self):
        zeilen, summen = rechnen.kalkulation(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen, self.einst)
        return zeilen, summen

    def angebot_daten(self):
        """Inhalt des Angebots mit aktuellen Staffelpreisen (None = abgebrochen)."""
        sp = self.staffelpreise_aktuell()
        if sp is None:
            return None
        zeilen, _ = self._rechnung()
        ang = ausgabe.angebot(self.kopf, self.positionen, zeilen, self.k, self.einst, sp, ergebnis=self.ergebnis)
        ang["anschrift"] = ausgabe.anschrift(self.db.kunde(self.kopf.get("kundennr")))
        return ang

    def angebot_pdf(self):
        if not self._vor_ausgabe():
            return None
        if not any(position_aktiv(p) for p in self.positionen):
            QMessageBox.warning(self, "Angebot", "Das Angebot hat keine Positionen.")
            return None
        ang = self.angebot_daten()
        if ang is None:
            return None
        if ang["hinweise"] and not self.f.stumm and QMessageBox.question(
                self, "Angebot", f"{ang['hinweise']} Position(en) haben einen Hinweis in der Kalkulation, z. B. kein "
                "Preis oder nicht eingeplant.\n\nAngebot trotzdem erstellen?") != QMessageBox.Yes:
            self.reiter.setCurrentIndex(1)
            return None
        pfad = self._schreiben("Angebot", self._ziel("Angebot", ".pdf"),
                               lambda p: pdf.angebot_pdf(p, self.kopf, ang, self.einst))
        if pfad is not None:
            self.preise_festschreiben()
        return pfad

    def preise_festschreiben(self):
        """Materialpreise und Schneiddaten, mit denen das Angebot gerade rechnet, im Angebot speichern (nach dem
        Angebots-PDF). Schon festgeschriebene Werte bleiben, neue Profile, Werkstoffe und Oberflächen kommen dazu."""
        pb = rechnen.preisbasis_aus(self.kopf, self.positionen, self.k, self.tabellen)
        alt = self.kopf.get("preisbasis")
        if isinstance(alt, dict) and rechnen.preisbasis_gleich(alt, pb):
            return
        self.db.preisbasis_speichern(self.id, pb)
        self.neu_laden()

    def preise_aktualisieren(self):
        """Festgeschriebene Preise auf die aktuellen Stammdaten setzen (nach Rückfrage)."""
        abw = rechnen.preisbasis_abweichung(self.kopf, self.k_aktuell, self.tabellen_aktuell)
        if not self.f.stumm and QMessageBox.question(
                self, "Aktuelle Preise übernehmen",
                "Materialpreise und Schneiddaten dieses Angebots auf die aktuellen Stammdaten setzen?\n\n"
                + "\n".join(abw[:15]) + ("\n…" if len(abw) > 15 else "")
                + "\n\nDer Preis des Angebots ändert sich dadurch. Ein bereits verschicktes Angebots-PDF bleibt "
                "unverändert; erst das nächste Angebots-PDF schreibt die neuen Preise wieder fest.") != QMessageBox.Yes:
            return False
        self.db.preisbasis_speichern(self.id, None)
        self.f.meldung("Aktuelle Materialpreise und Schneiddaten übernommen.")
        self.neu_laden()
        return True

    def werkstatt_pdf(self):
        if not self._vor_ausgabe():
            return None
        if not self.ergebnis or not self.ergebnis["stangen"]:
            QMessageBox.warning(self, "Werkstattpapiere", "Der Schnittplan ist leer. Bitte zuerst optimieren.")
            return None
        wp = ausgabe.werkstatt(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen)
        aktuell = self.stand_optimierung() == "aktuell"
        return self._schreiben("Werkstattpapiere", self._ziel("Werkstattpapiere", ".pdf"),
                               lambda p: pdf.werkstatt_pdf(p, self.kopf, wp, aktuell, self.einst))

    def kalkulation_pdf(self):
        if not self._vor_ausgabe():
            return None
        zeilen, summen = self._rechnung()
        aktuell = self.stand_optimierung() == "aktuell"
        return self._schreiben("Kalkulation", self._ziel("Kalkulation", ".pdf"),
                               lambda p: pdf.kalkulation_pdf(p, self.kopf, zeilen, summen, self.einst, aktuell))

    def csv_export(self):
        if not self._vor_ausgabe():
            return None
        zeilen, summen = self._rechnung()
        return self._schreiben("CSV-Export", self._ziel("Kalkulation", ".csv", mit_kunde=True),
                               lambda p: export.angebot_csv(p, self.kopf, zeilen, summen, self.einst))

    # -------------------------------------------------------------- Materialanfrage
    def material_anfragen(self, dialog=None, ausfuehren=None):
        """Materialanfrage an den Lieferanten (Dialog): Bedarf aus der Optimierung, Lieferant und Text prüfen, dann 'In Outlook öffnen' (gesendet wird nur in Outlook) oder 'Als E-Mail-Datei speichern'.
        dialog(d) bedient den Dialog statt exec, ausfuehren ersetzt den Outlook-Aufruf (Tests)."""
        from .materialanfrage_dialog import AnfrageDialog
        if not self.ergebnis or not self.ergebnis.get("stangen"):
            self.f.meldung("Materialanfrage: bitte zuerst optimieren (der Stangenbedarf kommt aus der Optimierung).",
                           fehler=True)
            return None
        werte = rechnen.stangen_werte(self.ergebnis, self.kopf, self.positionen, self.k, self.tabellen)
        zeilen = materialanfrage.bedarf(self.positionen, self.ergebnis, self.k, self.tabellen, werte)
        if not zeilen:
            self.f.meldung("Materialanfrage: kein Eigenmaterial im Angebot (Kundenmaterial wird nicht angefragt).",
                           fehler=True)
            return None
        d = AnfrageDialog(self, self.kopf, zeilen, self.k, self.einst,
                          materialanfrage.lieferanten(self.db.zeilen("zukauf_lieferanten")),
                          self._ziel("Materialanfrage", ".eml"), self.f.datei_oeffnen, ausfuehren)
        (dialog(d) if dialog else d.exec())
        if d.meldung:
            self.f.meldung(d.meldung)
        return d

    # -------------------------------------------------------------- STEP-Import
    def _gezogene_dateien(self, ereignis):
        urls = ereignis.mimeData().urls() if ereignis.mimeData().hasUrls() else []
        return step.step_dateien([u.toLocalFile() for u in urls if u.isLocalFile()])

    def dragEnterEvent(self, ereignis):
        if self._gezogene_dateien(ereignis):
            ereignis.acceptProposedAction()

    def dropEvent(self, ereignis):
        dateien = self._gezogene_dateien(ereignis)
        if dateien:
            ereignis.acceptProposedAction()
            self.step_importieren([str(d) for d in dateien])

    def step_importieren(self, dateien=None, werkstoff=None, stueck=None, als_satz=None):
        """STEP-Dateien messen und übernehmen. als_satz: Mehrteilige Dateien als Satz anlegen (None = wie im
        Prüfdialog im Feld „Sätze“ eingetragen, ohne Rückfragen ja)."""
        if werkstoff is None:       # Vorgabe für Rohre und Profile (Einstellung), Bleche bleiben offen
            werkstoff = self.db.einstellung("step_werkstoff") or None
            werkstoff = werkstoff if werkstoff in self.k.werkstoffe else None
        befehl = step.messprogramm(self.f.programmordner)
        if befehl is None:
            QMessageBox.warning(self, "STEP-Import", "STEP-Import.exe wurde nicht gefunden.\n\nDer Ordner 'STEP-Import' "
                                f"muss im Programmordner liegen:\n{self.f.programmordner}")
            return None
        if not dateien:
            dateien, _ = QFileDialog.getOpenFileNames(self, "STEP-Dateien wählen", str(Path.home()),
                                                      "STEP-Dateien (*.step *.stp *.STEP *.STP)")
            if not dateien:
                return None
        with tempfile.TemporaryDirectory() as tmp:
            liste, ausgabe = Path(tmp) / "liste.txt", Path(tmp) / "messwerte.txt"
            liste.write_text("\n".join(str(d) for d in dateien), encoding="utf-8")
            netze, ergebnis = Path(tmp) / "netze", Path(tmp) / "messung.json"
            if not self._messen(befehl + ["--liste", str(liste), "--ausgabe", str(ausgabe), "--netze", str(netze),
                                          "--json", str(ergebnis), "--flachstahl-bis",
                                          str(self.db.einstellung("flachstahl_bis") or 150)], len(dateien)):
                return None
            if not ausgabe.exists():
                QMessageBox.warning(self, "STEP-Import", "Die Messung hat keine Messwerte geschrieben.")
                return None
            messwerte = step.lade_netze(step.lies_messwerte(ausgabe), netze)
            json_ablage = self._messung_ablegen(ergebnis)
        zukauf_liste = self.db.zukauf_artikel_liste()     # Bleche werden Zukaufteile (Dubletten aus dieser Liste)
        if not self.f.stumm:        # Rohre und Bleche prüfen: je Teil übernehmen, Profil bzw. Zukaufartikel, Werkstoff
            from .step_dialog import StepPruefDialog
            # Stückzahl der Einzelteile im Dialog: 1 vorbelegt (Sätze zählt das Feld „Sätze“, Vorgabe 1 Satz)
            if StepPruefDialog(self, messwerte, self.k, werkstoff, 1 if stueck is None else stueck,
                               zukauf_liste).exec() != QDialog.Accepted:
                self.f.meldung("STEP-Import abgebrochen.")
                return None
        fehlend, doppelt = step.vorpruefung(messwerte, self.positionen, self.k)
        neue_profile = erneut = False
        if fehlend:
            neue_profile = self.f.stumm or QMessageBox.question(
                self, "STEP-Import", "Diese Profile fehlen in den Stammdaten:\n" + "\n".join(fehlend)
                + "\n\nSollen sie aus den Messwerten angelegt werden? (Bitte danach prüfen.)") == QMessageBox.Yes
        if doppelt and not self.f.stumm:
            erneut = QMessageBox.question(self, "STEP-Import", f"{doppelt} Artikel stehen schon im Angebot.\n\n"
                                          "Trotzdem noch einmal eintragen?") == QMessageBox.Yes
        mehr = step.mehrteilig(messwerte, mit_blechen=True)
        if als_satz is None:        # Prüfdialog: Feld „Sätze“ je Datei (leer = Einzelpositionen); ohne Dialog als Satz
            als_satz = self.f.stumm and not any("_saetze" in m for m in messwerte)
        m = rechnen.maschine(self.kopf, self.k)
        erg = step.uebernehmen(messwerte, self.positionen, self.k, self.tabellen["gewinde"], m, werkstoff, stueck,
                               neue_profile, erneut, saetze=list(mehr) if als_satz else (), zukauf_liste=zukauf_liste)
        self.db.profile_anlegen(erg["profile"])
        neue_ids = {schl: self.db.zukauf_speichern(None, werte, bezuege, bemerkung="aus STEP-Import angelegt")
                    for schl, (werte, bezuege) in erg["zukauf_neu"].items()}
        if neue_ids:
            erg["bericht"].append(f"{len(neue_ids)} Zukaufartikel (Blech) neu angelegt, EK fehlt: bitte unter "
                                  "Zukaufartikel mit 'EK eintragen …' nachtragen.")
        for p in erg["positionen"]:
            verweis = p.pop("_zukauf", None)
            if verweis:
                aid = verweis.get("artikel_id") or neue_ids.get(verweis.get("neu"))
                p["zukauf"] = json.dumps([dict(artikel_id=aid, menge=1, stand=self.db.zukauf_stand(aid))],
                                         ensure_ascii=False)
            netz = p.pop("_netz", None)
            pid = self.db.position_neu(self.id, p)
            if netz:
                self.db.netz_speichern(pid, netz)
        self.db.protokoll_anhaengen(self.id, erg["protokoll"])
        self.neu_laden()
        if json_ablage:
            erg["bericht"].append(f"Messergebnis (JSON): {json_ablage}")
        text = f"{len(erg['positionen'])} Position(en) in das Angebot übernommen."
        self.f.meldung(text)
        if not self.f.stumm:
            box = QMessageBox(QMessageBox.Information, "STEP-Import", text, parent=self)
            box.setDetailedText("\n".join(erg["bericht"]))
            box.exec()
        return erg

    def _messung_ablegen(self, ergebnis):
        """Messergebnis im JSON-Format (versioniert, siehe step_messung/step_ergebnis.py) in die Ablage kopieren:
        '<Angebot> STEP-Messung <Datum Uhrzeit>.json'. Im Selbsttest (stumm) nicht. Ergebnis: Pfad oder None."""
        if self.f.stumm or not ergebnis.exists():
            return None
        ziel = self._ziel(f"STEP-Messung {datetime.datetime.now():%Y-%m-%d %H%M%S}", ".json")
        if ziel is None:
            return None
        try:
            ziel.write_bytes(ergebnis.read_bytes())
        except OSError as e:
            self.f.meldung(f"Messergebnis (JSON) nicht gespeichert: {e}")
            return None
        return ziel

    def ansicht_3d(self, zeile=None):
        """3D-Ansicht der Positionen (Teile aus dem STEP-Import); zeigt zuerst die markierte Position."""
        from .step_dialog import Positionen3DDialog
        netze = self.db.netze(self.id)
        if not netze:
            QMessageBox.information(self, "3D-Ansicht", "In diesem Angebot gibt es keine Teile mit 3D-Daten.\n\n"
                                    "3D-Daten entstehen beim STEP-Import.")
            return None
        if zeile is None:
            i = self.pos_ansicht.currentIndex()
            zeile = i.row() if i.isValid() else next(r for r, p in enumerate(self.positionen) if p["id"] in netze)
        d = Positionen3DDialog(self, self.positionen, netze, zeile)
        if not self.f.stumm:
            d.exec()
        return d

    def _messen(self, befehl, anzahl):
        """Messung als eigener Prozess mit Fortschrittsanzeige. True = Messung beendet."""
        proz = QProcess(self)
        fortschritt = QProgressDialog("STEP-Dateien werden gemessen …", "Abbrechen", 0, anzahl, self)
        fortschritt.setWindowModality(Qt.WindowModal)
        fortschritt.setMinimumDuration(300)
        schleife = QEventLoop()

        def ausgabe():
            for z in bytes(proz.readAllStandardOutput()).decode("utf-8", "replace").splitlines():
                if z.startswith("[") and "/" in z:
                    try:
                        fortschritt.setValue(int(z[1:z.index("/")]) - 1)
                        fortschritt.setLabelText(z)
                    except ValueError:
                        pass
        proz.readyReadStandardOutput.connect(ausgabe)
        proz.finished.connect(schleife.quit)
        proz.errorOccurred.connect(lambda _: schleife.quit())
        abgebrochen = []
        fortschritt.canceled.connect(lambda: (abgebrochen.append(1), proz.kill()) if proz.state() != QProcess.NotRunning else None)
        umgebung = proz.processEnvironment()
        umgebung.insert("PYTHONIOENCODING", "utf-8")
        proz.setProcessEnvironment(umgebung)
        proz.start(befehl[0], befehl[1:])
        if proz.state() != QProcess.NotRunning or proz.waitForStarted(5000):
            schleife.exec()
        fortschritt.close()     # close() meldet auch 'canceled', darum zählt nur ein Abbruch bei laufender Messung
        if abgebrochen:
            return False
        if proz.exitStatus() != QProcess.NormalExit or proz.exitCode() not in (0, 1):
            fehler = bytes(proz.readAllStandardError()).decode("utf-8", "replace")[-800:]
            QMessageBox.warning(self, "STEP-Import", f"Die Messung ist fehlgeschlagen (Rückgabewert {proz.exitCode()})."
                                + (f"\n\n{fehler}" if fehler else ""))
            return False
        return True
