"""Aufträge: Übersicht, Auftragsbearbeitung (Kopf, Positionen), STEP-Import, Optimierung, Ergebnisse."""
import datetime
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QDate, QEventLoop, QModelIndex, QProcess, QRectF, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressDialog, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableView, QTabWidget,
    QVBoxLayout, QWidget)

from . import ausgabe, export, pdf, rechnen, staffeln, step
from .zusatz_dialog import ZusatzDialog
from .auftrag import KOPF, POSITIONEN, STEP_FELDER
from .auftrag_spalten import AUSW_SPALTEN, FEHLER_SPALTEN, KALK_SPALTEN, STANGEN_SPALTEN, TEIL_SPALTEN
from .fenster import FARBE_BERECHNET, FARBE_EINGABE, FARBE_STATUS, Auswahl, Sortierung
from .mappe_import import lies_auftrag, lies_staffeln
from .stammdaten import wert_aus_text, wert_als_text, zahl_als_text

FARBE_TEILE = ["#4E79A7", "#F28E2B", "#59A14F", "#B07AA1", "#76B7B2", "#EDC948", "#FF9DA7", "#9C755F",
               "#E15759", "#BAB0AC"]


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
    return v


class Liste(QAbstractTableModel):
    """Nur-Lese-Tabelle aus dicts. spalten: [(Titel, Schlüssel oder Funktion(zeile), Nachkommastellen, Breite)]."""

    def __init__(self, spalten, zeilen=()):
        super().__init__()
        self.spalten, self.zeilen = spalten, list(zeilen)

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


def _breiten(ansicht, spalten):
    for i, s in enumerate(spalten):
        ansicht.setColumnWidth(i, s[3] if len(s) > 3 else 90)


# ------------------------------------------------------------------ Übersicht der Aufträge
class AuftraegeSeite(QWidget):
    oeffnen = Signal(int)

    SPALTEN = [("Auftragsnummer", "nummer", None, 120), ("Kunde", "kunde", None, 200), ("Kundennr.", "kundennr", None, 90),
               ("Datum", lambda z: _datum(z.get("datum")), None, 85), ("Maschine", "maschine", None, 70),
               ("Positionen", "positionen", 0, 70), ("Teile", "teile", 0, 70),
               ("Optimiert am", lambda z: _zeit(z.get("optimiert_am")), None, 120),
               ("Geändert am", lambda z: _zeit(z.get("geaendert")), None, 120)]

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
        self.suche.setPlaceholderText("Suchen nach Auftrag, Kunde, Artikel …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.neu_laden)
        leiste = QHBoxLayout()
        for text, ziel in (("Neuer Auftrag", self.neu), ("Öffnen", self.oeffnen_gewaehlt), ("Kopieren", self.kopieren),
                           ("Löschen", self.loeschen), ("Auftrag aus Excel-Mappe übernehmen …", self.aus_mappe),
                           ("Ablage öffnen", self.f.ablage_oeffnen)):
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
        self.modell.setzen(self.db.auftraege(self.suche.text().strip()))

    def _id(self, index):
        return self.modell.zeilen[self.filter.mapToSource(index).row()]["id"]

    def _gewaehlt(self):
        i = self.ansicht.currentIndex()
        if not i.isValid():
            self.f.meldung("Bitte zuerst einen Auftrag wählen.", fehler=True)
            return None
        return self._id(i)

    def neu(self):
        i = self.db.auftrag_neu()
        self.neu_laden()
        self.oeffnen.emit(i)

    def oeffnen_gewaehlt(self):
        i = self._gewaehlt()
        if i:
            self.oeffnen.emit(i)

    def kopieren(self):
        i = self._gewaehlt()
        if i:
            neu = self.db.auftrag_kopieren(i)
            self.neu_laden()
            self.oeffnen.emit(neu)

    def loeschen(self):
        i = self._gewaehlt()
        if not i:
            return
        a = self.db.auftrag(i)
        if QMessageBox.question(self, "Auftrag löschen", f"Auftrag {a['nummer']} mit allen Positionen löschen?\n\n"
                                "Die tägliche Datensicherung enthält ihn weiterhin.") == QMessageBox.Yes:
            self.f.auftrag_schliessen(i)
            self.db.auftrag_loeschen(i)
            self.neu_laden()

    def aus_mappe(self, pfad=None):
        if not pfad:
            pfad, _ = QFileDialog.getOpenFileName(self, "Auftragsmappe wählen", str(Path.home()),
                                                  "Excel-Mappe (*.xlsm *.xlsx)")
            if not pfad:
                return None
        try:
            kopf, positionen, hinweise = lies_auftrag(pfad)
        except Exception as e:   # fremde oder beschädigte Datei: Meldung statt Absturz
            QMessageBox.warning(self, "Übernahme nicht möglich", str(e))
            return None
        kopf = {f.name: kopf.get(f.name) for f in KOPF if kopf.get(f.name) is not None}
        nummer = kopf.get("nummer")
        if nummer and any(a["nummer"] == nummer for a in self.db.auftraege()):
            kopf.pop("nummer")
            hinweise.insert(0, f"Auftragsnummer {nummer} gibt es schon, der Auftrag bekommt eine neue Nummer.")
        i = self.db.auftrag_neu(kopf)
        for p in positionen:
            self.db.position_neu(i, p)
        try:
            for st in lies_staffeln(pfad):
                self.db.staffel_neu(i, st)
        except Exception as e:   # Staffeln sind Beiwerk: Auftrag trotzdem übernehmen
            hinweise.append(f"Staffeln nicht übernommen: {e}")
        self.neu_laden()
        a = self.db.auftrag(i)
        text = f"Auftrag {a['nummer']} mit {len(positionen)} Positionen übernommen."
        if hinweise:
            text += "\n\n" + "\n".join(hinweise[:15])
        self.f.meldung(text.splitlines()[0])
        if hinweise and not self.f.stumm:
            QMessageBox.information(self, "Auftrag übernommen", text)
        self.oeffnen.emit(i)
        return i


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
             ("Vorschub groß [mm/min]", "vorschub", 0), ("Gewicht Position [kg]", "gewicht_position", 2),
             ("Eingeplant [Stk]", "eingeplant", 0), ("Nicht eingeplant [Stk]", "nicht_eingeplant", 0)]
SICHTBAR = ["pos", "artikel", "bezeichnung", "profil_id", "werkstoff_id", "laenge", "stueck", "schneidweg",
            "einstiche", "zeit_manuell", "stange", "satz", "je_satz", "preis_m", "gewinde", "zusatz"]


class PositionenModell(QAbstractTableModel):
    geaendert = Signal()

    def __init__(self, seite):
        super().__init__()
        self.s = seite
        felder = {f.name: f for f in POSITIONEN.felder}
        self.spalten = ([("zusatz" if felder[n].art == "zusatz" else "feld", felder[n]) for n in SICHTBAR]
                        + [("status", None)]
                        + [("berechnet", b) for b in BERECHNET]
                        + [("feld", f) for f in POSITIONEN.felder if f.name in STEP_FELDER])
        self.daten, self.werte, self.status = [], [], []

    def rechnen(self):
        s = self.s
        self.beginResetModel()
        self.daten = s.positionen
        erg = s.ergebnis
        eingeplant = rechnen.eingeplant_je_position(erg) if erg and erg["stangen"] else None
        self.werte, self.status = [], []
        for i, p in enumerate(self.daten):
            w = rechnen.position_werte(p, s.kopf, s.k, s.tabellen)
            ein = eingeplant.get(rechnen.schluessel(p, i), 0) if eingeplant is not None else None
            w["eingeplant"] = ein if p.get("profil_id") else None
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
        return x.titel if art in ("feld", "zusatz") else ("Status" if art == "status" else x[0])

    def roh(self, r, c):
        art, x = self.spalten[c]
        if art == "feld":
            return self.daten[r].get(x.name)
        if art == "status":
            return self.status[r]
        if art == "zusatz":
            return rechnen.zusatz_text(self.daten[r])
        w = self.werte[r].get(x[1])
        return {True: "ja", False: "nein"}.get(w, w) if isinstance(w, bool) else w

    def data(self, index, rolle=Qt.DisplayRole):
        if not index.isValid():
            return None
        art, x = self.spalten[index.column()]
        w = self.roh(index.row(), index.column())
        if rolle in (Qt.DisplayRole, Qt.ToolTipRole):
            if art == "feld":
                return wert_als_text(x, w)
            if art == "berechnet":
                return _z(w, x[2]) if x[2] is not None else ("" if w is None else str(w))
            if art == "zusatz" and rolle == Qt.ToolTipRole:
                return (w + "\n" if w else "") + "Doppelklick: Gewinde und Zusatzarbeiten wählen"
            return w
        if rolle == Qt.EditRole and art == "feld":
            return wert_als_text(x, w, bearbeiten=True)
        if rolle == Qt.UserRole:
            return w
        if rolle == Qt.TextAlignmentRole and (art == "berechnet" and x[2] is not None
                                              or art == "feld" and x.art in ("zahl", "ganz")):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.BackgroundRole:
            if art == "status":
                return QBrush(_farbe_status(w) or (QColor("#FFF2CC") if str(w).startswith("HINWEIS") else FARBE_BERECHNET))
            return QBrush(FARBE_EINGABE if art in ("feld", "zusatz") else FARBE_BERECHNET)
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
        self.s.db.position_aendern(p["id"], f.name, wert)
        self.s.f.meldung(f"{f.titel} gespeichert.")
        self.geaendert.emit()
        return True


# ------------------------------------------------------------------ Staffeln
STAFFEL_TITEL = ("Satz oder Pos.", "Menge [Sätze bzw. Stück]", "Bemerkung", "Prüfung")
STAFFELPREIS_SPALTEN = [("Satz oder Pos.", "schluessel", None, 100), ("Bezeichnung", "bezeichnung", None, 180),
                        ("Einheit", "einheit", None, 55), ("Menge", "menge", 0, 60), ("Teile gesamt [Stk]", "teile", 0, 70),
                        ("Stangen", "stangen", 0, 60), ("Material [€]", "material", 2, 80),
                        ("Laser + Gewinde [€]", "laser", 2, 80), ("Rüsten + Stangenwechsel [€]", "ruesten", 2, 95),
                        ("Herstellkosten [€]", "herstell", 2, 90), ("Herstellkosten je Einheit [€]", "herstell_einheit", 3, 95),
                        ("Verkaufspreis je Einheit [€]", "preis_einheit", 2, 95),
                        ("Verkaufspreis gesamt [€]", "preis_gesamt", 2, 95), ("Hinweis", "hinweis", None, 260)]


class StaffelnModell(QAbstractTableModel):
    """Mengenstufen eines Auftrags (wie Blatt 'Staffeln'): Schlüssel, Menge, Bemerkung, Prüfung."""
    geaendert = Signal()
    FELDER = ("schluessel", "menge", "bemerkung")

    def __init__(self, seite):
        super().__init__()
        self.s, self.daten = seite, []

    def setzen(self, daten):
        self.beginResetModel()
        self.daten = daten
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.daten)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, abschnitt, richtung, rolle=Qt.DisplayRole):
        if rolle == Qt.DisplayRole:
            return STAFFEL_TITEL[abschnitt] if richtung == Qt.Horizontal else str(abschnitt + 1)
        return None

    def data(self, index, rolle=Qt.DisplayRole):
        if not index.isValid():
            return None
        z, c = self.daten[index.row()], index.column()
        w = staffeln.pruefen(z, self.s.positionen) if c == 3 else z.get(self.FELDER[c])
        if rolle in (Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole):
            return _z(w, 0) if c == 1 and rolle != Qt.EditRole else ("" if w is None else str(w))
        if rolle == Qt.TextAlignmentRole and c == 1:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.BackgroundRole:
            if c == 3:
                return QBrush(FARBE_STATUS["FEHLER"] if str(w).startswith("FEHLER") else FARBE_BERECHNET)
            return QBrush(FARBE_EINGABE)
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return f | Qt.ItemIsEditable if index.column() < 3 else f

    def setData(self, index, text, rolle=Qt.EditRole):
        if rolle != Qt.EditRole or not index.isValid() or index.column() > 2:
            return False
        feld = self.FELDER[index.column()]
        t = str(text).strip()
        wert = t or None
        if feld == "menge" and t:
            try:
                wert = int(t.replace(".", ""))
                if wert < 1:
                    raise ValueError
            except ValueError:
                self.s.f.meldung("Menge: bitte eine ganze Zahl ab 1 eingeben (Sätze bzw. Stück).", fehler=True)
                return False
        z = self.daten[index.row()]
        if wert == z.get(feld):
            return False
        self.s.db.staffel_aendern(z["id"], feld, wert)
        z[feld] = wert
        self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), 3))
        self.geaendert.emit()
        return True


# ------------------------------------------------------------------ Stangenbild
class Stangenbild(QWidget):
    """Je Stangenmuster ein maßstäblicher Balken: Endbeschnitt grau, Teile farbig mit Pos. und Länge,
    dicke Linie = Schnitt, Rest hellgrau, Greiferrest rot (wie Blatt 'Stangenbild' der Mappe)."""
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
            kopf = (f"{anz} × Stange {nr_text}: {s['profil']}  {s['werkstoff']}  {_z(s['stange'], 0)} mm")
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
                r = rechteck(t["von"], t["bis"], self.farben.get(t["ref"], QColor("#4E79A7")))
                p.setPen(QPen(QColor("#202020"), 2))
                p.drawLine(r.topLeft(), r.bottomLeft())
                p.drawLine(r.topRight(), r.bottomRight())
                text = f"{t['pos'] if t['pos'] is not None else t['artikel']}\n{_z(t['laenge'], 1)}"
                if r.width() > 28:
                    p.setPen(QColor("white"))
                    p.drawText(r, Qt.AlignCenter, text if r.width() > 46 else str(t["pos"] or ""))
        p.end()


# ------------------------------------------------------------------ Auftrag
PROT_SPALTEN = [(t, (lambda i: lambda z: z[i] if i < len(z) else None)(i), None, 90) for i, t in enumerate(step.PROTOKOLL)]


class AuftragSeite(QWidget):
    def __init__(self, fenster, auftrag_id):
        super().__init__()
        self.f, self.db, self.id = fenster, fenster.db, auftrag_id
        self._laden = False
        self.kopf, self.positionen, self.ergebnis = {}, [], None

        # Kopf
        self.felder = {}
        kopf_box = QGroupBox("Auftragskopf")
        g = QGridLayout(kopf_box)
        for i, fd in enumerate(KOPF):
            if fd.art == "datum":
                w = QDateEdit()
                w.setCalendarPopup(True)
                w.setDisplayFormat("dd.MM.yyyy")
                w.editingFinished.connect(lambda fd=fd, w=w: self._kopf_speichern(fd, w.date().toString("yyyy-MM-dd")))
            elif fd.art == "auswahl":
                w = QComboBox()
                w.currentTextChanged.connect(lambda t, fd=fd: self._kopf_speichern(fd, t or None))
            elif fd.art == "ganz":
                w = QSpinBox()
                w.setRange(int(fd.von), int(fd.bis))
                w.setGroupSeparatorShown(True)
                w.setSingleStep(100)
                w.editingFinished.connect(lambda fd=fd, w=w: self._kopf_speichern(fd, w.value()))
            elif fd.art == "zahl":
                w = QDoubleSpinBox()
                w.setRange(fd.von, fd.bis)
                w.setDecimals(fd.stellen or 2)
                w.setGroupSeparatorShown(True)
                w.editingFinished.connect(lambda fd=fd, w=w: self._kopf_speichern(fd, round(w.value(), 2) or None))
            else:
                w = QLineEdit()
                w.editingFinished.connect(lambda fd=fd, w=w: self._kopf_speichern(fd, w.text().strip() or None))
            self.felder[fd.name] = w
            g.addWidget(QLabel(fd.titel), i % 4, 2 * (i // 4))
            g.addWidget(w, i % 4, 2 * (i // 4) + 1)
        self.maschinenwerte = QLabel()
        self.maschinenwerte.setStyleSheet("color: #595959;")
        g.addWidget(self.maschinenwerte, 4, 0, 1, 4)
        self.uebersicht = QLabel()
        self.uebersicht.setTextInteractionFlags(Qt.TextSelectableByMouse)
        summen_box = QGroupBox("Übersicht")
        sl = QVBoxLayout(summen_box)
        self.stand = QLabel()
        self.stand.setAlignment(Qt.AlignCenter)
        self.stand.setMinimumHeight(26)
        sl.addWidget(self.stand)
        sl.addWidget(self.uebersicht)
        oben = QHBoxLayout()
        oben.addWidget(kopf_box, 3)
        oben.addWidget(summen_box, 2)

        # Knöpfe
        leiste = QHBoxLayout()
        knoepfe = (("Neue Position", self.position_neu), ("Positionen löschen", self.positionen_loeschen),
                   ("Zusatzarbeiten …", lambda: self.zusatzarbeiten()),
                   ("STEP importieren …", lambda: self.step_importieren()), ("Optimieren", self.optimieren))
        for text, ziel in knoepfe:
            b = QPushButton(text)
            b.clicked.connect(ziel)
            if text == "Optimieren":
                b.setStyleSheet("font-weight: bold;")
            leiste.addWidget(b)
        leiste.addSpacing(20)
        self.zeige_berechnet = QCheckBox("Berechnete Werte")
        self.zeige_step = QCheckBox("STEP-Werte")
        for c in (self.zeige_berechnet, self.zeige_step):
            c.toggled.connect(self._spalten_zeigen)
            leiste.addWidget(c)
        leiste.addStretch(1)
        ausgabe_leiste = QHBoxLayout()
        ausgabe_leiste.addWidget(QLabel("Ausgabe:"))
        for text, ziel in (("Angebot (PDF)", self.angebot_pdf), ("Werkstattpapiere (PDF)", self.werkstatt_pdf),
                           ("Kalkulation (PDF)", self.kalkulation_pdf), ("Excel-Export", self.excel_export),
                           ("Ablage öffnen", self.f.ablage_oeffnen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            ausgabe_leiste.addWidget(b)
        ausgabe_leiste.addStretch(1)

        # Positionen und Ergebnisse
        self.pos_modell = PositionenModell(self)
        self.pos_modell.geaendert.connect(self.neu_laden)
        self.pos_ansicht = _tabelle(self.pos_modell, sortieren=False)
        self.pos_ansicht.setItemDelegate(Auswahl(self.pos_modell, self.pos_ansicht))
        self.pos_ansicht.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                         | QAbstractItemView.AnyKeyPressed)
        self.pos_ansicht.setSelectionBehavior(QAbstractItemView.SelectItems)
        for i, (art, x) in enumerate(self.pos_modell.spalten):
            self.pos_ansicht.setColumnWidth(i, x.breite if art in ("feld", "zusatz") else (240 if art == "status" else 85))
        self.pos_ansicht.doubleClicked.connect(
            lambda i: self.zusatzarbeiten([i.row()]) if self.pos_modell.spalten[i.column()][0] == "zusatz" else None)

        self.kalk = Liste(KALK_SPALTEN)
        self.stangen = Liste(STANGEN_SPALTEN)
        self.teile = Liste(TEIL_SPALTEN)
        self.ausw = Liste(AUSW_SPALTEN)
        self.fehler = Liste(FEHLER_SPALTEN)
        self.prot = Liste(PROT_SPALTEN)
        kalk_ansicht = _tabelle(self.kalk)
        _breiten(kalk_ansicht, KALK_SPALTEN)
        self.summen = QLabel()
        kalk_seite = QWidget()
        kl = QVBoxLayout(kalk_seite)
        kl.addWidget(self.summen)
        kl.addWidget(kalk_ansicht, 1)
        self.stangen_ansicht = _tabelle(self.stangen, sortieren=False)
        _breiten(self.stangen_ansicht, STANGEN_SPALTEN)
        self.stangen_ansicht.selectionModel().currentRowChanged.connect(self._stange_gewaehlt)
        teile_ansicht = _tabelle(self.teile, sortieren=False)
        _breiten(teile_ansicht, TEIL_SPALTEN)
        plan = QSplitter(Qt.Vertical)
        plan.addWidget(self.stangen_ansicht)
        plan.addWidget(teile_ansicht)
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
        al.addWidget(QLabel("<b>Nicht eingeplante Teile</b>"))
        al.addWidget(fehler_ansicht, 1)
        prot_ansicht = _tabelle(self.prot)
        _breiten(prot_ansicht, PROT_SPALTEN)
        # Staffeln: Mengenstufen (Eingabe) und Staffelpreise (Ergebnis)
        self.staffel_modell = StaffelnModell(self)
        self.staffel_modell.geaendert.connect(self._staffel_stand)
        self.staffel_ansicht = _tabelle(self.staffel_modell, sortieren=False)
        self.staffel_ansicht.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                             | QAbstractItemView.AnyKeyPressed)
        for i, b in enumerate((120, 110, 220, 260)):
            self.staffel_ansicht.setColumnWidth(i, b)
        self.staffelpreise = Liste(STAFFELPREIS_SPALTEN)
        sp_ansicht = _tabelle(self.staffelpreise, sortieren=False)
        _breiten(sp_ansicht, STAFFELPREIS_SPALTEN)
        self.staffel_info = QLabel()
        st_seite = QWidget()
        stl = QVBoxLayout(st_seite)
        st_leiste = QHBoxLayout()
        for text, ziel in (("Neue Stufe", self.staffel_neu), ("Stufen löschen", self.staffeln_loeschen),
                           ("Staffelpreise rechnen", self.staffelpreise_rechnen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            st_leiste.addWidget(b)
        st_leiste.addSpacing(20)
        hinweis = QLabel("Je Zeile eine Mengenstufe: Satzbezeichnung (Spalte Satz) oder Positionsnummer. Jede Stufe wird "
                         "als eigener Auftrag neu gerechnet; die Preise stehen im Angebot unter den Positionen.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #595959;")
        st_leiste.addWidget(hinweis, 1)
        stl.addLayout(st_leiste)
        st_split = QSplitter(Qt.Vertical)
        st_split.addWidget(self.staffel_ansicht)
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(self.staffel_info)
        ul.addWidget(sp_ansicht, 1)
        st_split.addWidget(unten)
        stl.addWidget(st_split, 1)

        self.reiter = QTabWidget()
        self.reiter.addTab(self.pos_ansicht, "Positionen")
        self.reiter.addTab(kalk_seite, "Kalkulation")
        self.reiter.addTab(plan, "Schnittplan")
        self.reiter.addTab(bild_rahmen, "Stangenbild")
        self.reiter.addTab(ausw_seite, "Auswertung")
        self.reiter.addTab(st_seite, "Staffeln")
        self.reiter.addTab(prot_ansicht, "STEP-Protokoll")

        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addLayout(leiste)
        lay.addLayout(ausgabe_leiste)
        lay.addWidget(self.reiter, 1)
        self._spalten_zeigen()
        self.neu_laden()

    # -------------------------------------------------------------- Laden und Rechnen
    def titel(self):
        return f"Auftrag {self.kopf.get('nummer') or ''}"

    def neu_laden(self, *_):
        a = self.db.auftrag(self.id)
        if a is None:
            return
        self.kopf = a
        self.ergebnis = a["ergebnis"]
        self.positionen = self.db.positionen(self.id)
        self.k = self.db.kontext()
        self.tabellen = self.db.tabellen()
        self.einst = self.db.einstellungen()
        self.stufen = self.db.staffeln(self.id)
        self._kopf_anzeigen()
        self.pos_modell.rechnen()
        self._ergebnisse_anzeigen()
        self.f.reiter_titel(self)

    def _kopf_anzeigen(self):
        self._laden = True
        for fd in KOPF:
            w, v = self.felder[fd.name], self.kopf.get(fd.name)
            if isinstance(w, QDateEdit):
                w.setDate(QDate.fromString(v, "yyyy-MM-dd") if v else QDate.currentDate())
            elif isinstance(w, QComboBox):
                w.clear()
                w.addItems(self.k.auswahl("maschine"))
                if v and v not in self.k.maschinen:
                    w.addItem(v)
                w.setCurrentText(v or "")
            elif isinstance(w, QSpinBox):
                w.setValue(int(v or 0))
            elif isinstance(w, QDoubleSpinBox):
                w.setValue(v or 0)
            else:
                w.setText(v or "")
        m = rechnen.maschine(self.kopf, self.k)
        if m:
            self.maschinenwerte.setText(
                f"Maschine: Endbeschnitt {_z(m.get('endbeschnitt'), 0)} mm · Greiferrest {_z(m.get('greiferrest'), 0)} mm · "
                f"Schnittverlust {_z(m.get('schnittverlust'), 1)} mm · max. Stange {_z(m.get('max_stange'), 0)} mm · "
                f"Stundensatz {_z(m.get('stundensatz'), 2)} €/h"
                + (f" · max. Hüllkreis-Ø {_z(m['max_huellkreis'], 1)} mm" if m.get("max_huellkreis") else "")
                + (f" · max. Metergewicht {_z(m['max_kg_m'], 1)} kg/m" if m.get("max_kg_m") else ""))
        else:
            self.maschinenwerte.setText("<span style='color:#C00000'>Maschine fehlt oder ist unbekannt.</span>")
        self._laden = False

    def _kopf_speichern(self, fd, wert):
        if self._laden or wert == self.kopf.get(fd.name):
            return
        try:
            self.db.auftrag_aendern(self.id, fd.name, wert)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            self._kopf_anzeigen()
            return
        self.f.meldung(f"{fd.titel} gespeichert.")
        self.neu_laden()

    def stand_optimierung(self):
        if not self.ergebnis:
            return "noch nicht optimiert"
        aktuell = rechnen.eingabe_kennung(self.kopf, self.positionen, self.k) == self.ergebnis.get("kennung")
        return "aktuell" if aktuell else "VERALTET – Auftrag oder Stammdaten geändert, bitte neu optimieren"

    def _ergebnisse_anzeigen(self):
        st = self.stand_optimierung()
        farbe = {"aktuell": "#C6EFCE", "noch nicht optimiert": "#FFEB9C"}.get(st, "#F8CBAD")
        self.stand.setText(f"Stand Optimierung: {st}")
        self.stand.setStyleSheet(f"background: {farbe}; font-weight: bold; padding: 3px;")
        erg = self.ergebnis
        zeilen, summen = rechnen.kalkulation(self.kopf, self.positionen, erg, self.k, self.tabellen, self.einst)
        self.kalk.setzen([z for z in zeilen if z])
        stat = self.pos_modell.status
        teile = sum(p.get("stueck") or 0 for p in self.positionen)
        laenge = sum(w["laenge_gesamt"] or 0 for w in self.pos_modell.werte) / 1000
        gewicht = sum(w["gewicht_position"] or 0 for w in self.pos_modell.werte)
        self.uebersicht.setText(
            f"<table cellpadding='1'>"
            f"<tr><td>Positionen</td><td align='right'>{sum(1 for s in stat if s)}</td>"
            f"<td width='20'></td><td>Material</td><td align='right'>{_z(summen['material'])} €</td></tr>"
            f"<tr><td>davon FEHLER</td><td align='right'>{sum(1 for s in stat if s.startswith('FEHLER'))}</td>"
            f"<td></td><td>Laser + Gewinde</td><td align='right'>{_z(summen['laser'])} €</td></tr>"
            f"<tr><td>davon WARNUNG/HINWEIS</td><td align='right'>"
            f"{sum(1 for s in stat if s.startswith(('WARNUNG', 'HINWEIS')))}</td>"
            f"<td></td><td>Rüsten + Stangenwechsel</td><td align='right'>{_z(summen['ruesten'])} €</td></tr>"
            f"<tr><td>Teile gesamt</td><td align='right'>{_z(teile, 0)} Stk</td>"
            f"<td></td><td>Zusatzarbeiten</td><td align='right'>{_z(summen['zusatz'])} €</td></tr>"
            f"<tr><td></td><td></td><td></td><td>Herstellkosten</td><td align='right'>{_z(summen['herstell'])} €</td></tr>"
            f"<tr><td></td><td></td><td></td><td>Pauschalen + Aufschlag + Fracht</td><td align='right'>"
            f"{_z(summen['pauschalen'] + summen['auftragsaufschlag'] + summen['fracht'])} €</td></tr>"
            f"<tr><td>Teilelänge / Gewicht</td><td align='right'>{_z(laenge)} m / {_z(gewicht)} kg</td>"
            f"<td></td><td><b>Verkaufspreis</b></td><td align='right'><b>{_z(summen['verkauf'])} €</b></td></tr>"
            f"<tr><td>Stangen</td><td align='right'>{summen['stangen']}</td><td></td><td></td><td></td></tr></table>")
        self.summen.setText(
            f"Material {_z(summen['material'])} € · Laser + Gewinde {_z(summen['laser'])} € · Rüsten + Stangenwechsel "
            f"{_z(summen['ruesten'])} € ({_z(summen['ruestzeit'], 0)} min Rüsten + {summen['abmessungen']} Abmessung(en) × "
            f"{_z(summen['ruestzeit_abmessung'], 0)} min, {summen['stangen']} Stangen × "
            f"{_z(summen['stangenwechsel'], 0)} s) · Zusatzarbeiten {_z(summen['zusatz'])} € · "
            f"Herstellkosten {_z(summen['herstell'])} € · "
            f"Pauschale {summen['abmessungen']} × {_z(self.einst.get('pauschale_abmessung') or 0)} € · "
            f"Auftragsaufschlag {_z(summen['auftragsaufschlag'])} € · Fracht {_z(summen['fracht'])} € · "
            f"<b>Verkaufspreis {_z(summen['verkauf'])} €</b> · Zuschläge Material {_z(100 * self.einst['zuschlag_material'], 1)} %, "
            f"Fertigung {_z(100 * self.einst['zuschlag_fertigung'], 1)} %, "
            f"Fremdleistung {_z(100 * (self.einst.get('zuschlag_fremdleistung') or 0), 1)} %, "
            f"Gewinn {_z(100 * self.einst['gewinn'], 1)} %")
        if erg:
            sw = rechnen.stangen_werte(erg, self.kopf, self.positionen, self.k, self.tabellen)
            self.stangen.setzen([dict(s, **w) for s, w in zip(erg["stangen"], sw)])
            ausw = rechnen.auswertung_zeilen(erg, sw)
            self.ausw.setzen(ausw)
            self.fehler.setzen(erg["fehler"] or [dict(grund="keine")])
        else:
            self.stangen.setzen([])
            self.ausw.setzen([])
            self.fehler.setzen([])
        self.teile.setzen([])
        self.bild.setzen(erg)
        self.prot.setzen(self.db.protokoll(self.id))
        self.staffel_modell.setzen(self.stufen)
        self._staffel_stand()

    def _stange_gewaehlt(self, aktuell, _=None):
        if not aktuell.isValid() or not self.ergebnis:
            self.teile.setzen([])
            return
        s = self.ergebnis["stangen"][aktuell.row()]     # in der Liste ist 'teile' die Anzahl
        self.teile.setzen([dict(t, platz=i) for i, t in enumerate(s["teile"], start=1)])

    def _spalten_zeigen(self):
        for i, (art, x) in enumerate(self.pos_modell.spalten):
            if art == "berechnet":
                self.pos_ansicht.setColumnHidden(i, not self.zeige_berechnet.isChecked())
            elif art == "feld" and x.name in STEP_FELDER:
                self.pos_ansicht.setColumnHidden(i, not self.zeige_step.isChecked())

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
            d = ZusatzDialog(self, self.positionen[zeilen[0]], len(zeilen), self.k, self.tabellen)
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
            erg = rechnen.optimieren(self.kopf, self.positionen, self.k)
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
            erg["kennung"] = rechnen.eingabe_kennung(self.kopf, self.positionen, self.db.kontext())
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

    # -------------------------------------------------------------- Staffeln
    def staffel_neu(self):
        self.db.staffel_neu(self.id)
        self.neu_laden()
        i = self.staffel_modell.index(len(self.stufen) - 1, 0)
        self.reiter.setCurrentIndex(self.reiter.count() - 2)
        self.staffel_ansicht.setCurrentIndex(i)
        self.staffel_ansicht.edit(i)

    def staffeln_loeschen(self):
        zeilen = sorted({i.row() for i in self.staffel_ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.f.meldung("Bitte zuerst die Stufen markieren, die gelöscht werden sollen.", fehler=True)
            return
        self.db.staffeln_loeschen([self.stufen[r]["id"] for r in zeilen])
        self.neu_laden()

    def _staffel_kennung(self):
        return staffeln.kennung(self.kopf, self.positionen, self.stufen, self.k, self.tabellen, self.einst)

    def _staffel_stand(self):
        sp = self.kopf.get("staffelpreise")
        self.staffelpreise.setzen(sp["zeilen"] if sp else [])
        if not staffeln.gueltige(self.stufen):
            text, farbe = "Keine Mengenstufen eingetragen.", "#595959"
        elif not sp:
            text, farbe = "Staffelpreise noch nicht gerechnet.", "#9C5700"
        elif sp.get("kennung") != self._staffel_kennung():
            text, farbe = ("VERALTET – Auftrag, Stufen oder Stammdaten geändert. Das Angebot rechnet sie neu.", "#C00000")
        else:
            text, farbe = f"Staffelpreise aktuell (gerechnet {_zeit(sp.get('am'))}).", "#375623"
        self.staffel_info.setText(f"<b style='color:{farbe}'>{text}</b>")

    def staffelpreise_rechnen(self):
        """Alle Stufen neu rechnen und speichern. Ergebnis: Zeilen oder None (abgebrochen)."""
        stufen = staffeln.gueltige(self.stufen)
        if not stufen:
            self.f.meldung("Keine Mengenstufe eingetragen (Reiter Staffeln).", fehler=True)
            self.staffelpreise_speichern([])
            return []
        fortschritt = QProgressDialog("Staffelpreise werden gerechnet …", "Abbrechen", 0, len(stufen), self)
        fortschritt.setWindowModality(Qt.WindowModal)
        fortschritt.setMinimumDuration(500)

        def weiter(i, n):
            fortschritt.setValue(i)
            QApplication.processEvents()
            return not fortschritt.wasCanceled()
        try:
            zeilen = staffeln.rechnen_alle(self.kopf, self.positionen, stufen, self.k, self.tabellen, self.einst, weiter)
        except (ValueError, AssertionError) as e:
            fortschritt.close()
            QMessageBox.warning(self, "Staffelpreise", f"Staffelpreise abgebrochen:\n{e}")
            return None
        abgebrochen = fortschritt.wasCanceled()
        fortschritt.close()
        if abgebrochen:
            self.f.meldung("Staffelpreise abgebrochen.", fehler=True)
            return None
        self.staffelpreise_speichern(zeilen)
        self.f.meldung(f"{len(zeilen)} Mengenstufe(n) gerechnet.")
        return zeilen

    def staffelpreise_speichern(self, zeilen):
        sp = dict(zeilen=zeilen, kennung=self._staffel_kennung(),
                  am=datetime.datetime.now().isoformat(timespec="seconds")) if zeilen else None
        self.db.staffelpreise_speichern(self.id, sp)
        self.kopf["staffelpreise"] = sp
        self._staffel_stand()

    def staffelpreise_aktuell(self):
        """Staffelpreise fürs Angebot; veraltete werden vorher neu gerechnet. None = abgebrochen."""
        if not staffeln.gueltige(self.stufen):
            return []
        sp = self.kopf.get("staffelpreise")
        if sp and sp.get("kennung") == self._staffel_kennung():
            return sp["zeilen"]
        return self.staffelpreise_rechnen()

    # -------------------------------------------------------------- Ausgabe (PDF, Excel)
    def _vor_ausgabe(self):
        """Wie VorAusgabeOptimieren der Mappe: bei veralteter Optimierung fragen. True = weiter."""
        if self.stand_optimierung() == "aktuell":
            return True
        if self.f.stumm:
            return self.optimieren()
        a = QMessageBox.question(self, "Optimierung veraltet",
                                 "Der Schnittplan passt nicht mehr zum Auftrag (oder es wurde noch nicht optimiert).\n\n"
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
        return ausgabe.angebot(self.kopf, self.positionen, zeilen, self.k, self.einst, sp)

    def angebot_pdf(self):
        if not self._vor_ausgabe():
            return None
        if not any(p.get("profil_id") for p in self.positionen):
            QMessageBox.warning(self, "Angebot", "Der Auftrag hat keine Positionen.")
            return None
        ang = self.angebot_daten()
        if ang is None:
            return None
        if ang["hinweise"] and not self.f.stumm and QMessageBox.question(
                self, "Angebot", f"{ang['hinweise']} Position(en) haben einen Hinweis in der Kalkulation, z. B. kein "
                "Preis oder nicht eingeplant.\n\nAngebot trotzdem erstellen?") != QMessageBox.Yes:
            self.reiter.setCurrentIndex(1)
            return None
        return self._schreiben("Angebot", self._ziel("Angebot", ".pdf"),
                               lambda p: pdf.angebot_pdf(p, self.kopf, ang, self.einst))

    def werkstatt_pdf(self):
        if not self._vor_ausgabe():
            return None
        if not self.ergebnis or not self.ergebnis["stangen"]:
            QMessageBox.warning(self, "Werkstattpapiere", "Der Schnittplan ist leer. Bitte zuerst optimieren.")
            return None
        wp = ausgabe.werkstatt(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen)
        aktuell = self.stand_optimierung() == "aktuell"
        return self._schreiben("Werkstattpapiere", self._ziel("Werkstattpapiere", ".pdf"),
                               lambda p: pdf.werkstatt_pdf(p, self.kopf, wp, aktuell))

    def kalkulation_pdf(self):
        if not self._vor_ausgabe():
            return None
        zeilen, summen = self._rechnung()
        aktuell = self.stand_optimierung() == "aktuell"
        return self._schreiben("Kalkulation", self._ziel("Kalkulation", ".pdf"),
                               lambda p: pdf.kalkulation_pdf(p, self.kopf, zeilen, summen, self.einst, aktuell))

    def excel_export(self):
        ang = self.angebot_daten()
        if ang is None:
            return None
        zeilen, summen = self._rechnung()
        sw = rechnen.stangen_werte(self.ergebnis, self.kopf, self.positionen, self.k, self.tabellen) if self.ergebnis else []
        sp = (self.kopf.get("staffelpreise") or {}).get("zeilen", [])
        return self._schreiben("Excel-Export", self._ziel("", ".xlsx", mit_kunde=True),
                               lambda p: export.auftrag_xlsx(p, self.kopf, self.positionen, self.pos_modell.status, zeilen,
                                                             summen, self.ergebnis, sw, sp, ang))

    # -------------------------------------------------------------- STEP-Import
    def step_importieren(self, dateien=None, werkstoff=None, stueck=None):
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
            auswahl = self._step_dialog()
            if auswahl is None:
                return None
            werkstoff, stueck = auswahl
        with tempfile.TemporaryDirectory() as tmp:
            liste, ausgabe = Path(tmp) / "liste.txt", Path(tmp) / "messwerte.txt"
            liste.write_text("\n".join(str(d) for d in dateien), encoding="utf-8")
            if not self._messen(befehl + ["--liste", str(liste), "--ausgabe", str(ausgabe)], len(dateien)):
                return None
            if not ausgabe.exists():
                QMessageBox.warning(self, "STEP-Import", "Die Messung hat keine Messwerte geschrieben.")
                return None
            messwerte = step.lies_messwerte(ausgabe)
        fehlend, doppelt = step.vorpruefung(messwerte, self.positionen, self.k)
        neue_profile = erneut = False
        if fehlend:
            neue_profile = self.f.stumm or QMessageBox.question(
                self, "STEP-Import", "Diese Profile fehlen in den Stammdaten:\n" + "\n".join(fehlend)
                + "\n\nSollen sie aus den Messwerten angelegt werden? (Bitte danach prüfen.)") == QMessageBox.Yes
        if doppelt and not self.f.stumm:
            erneut = QMessageBox.question(self, "STEP-Import", f"{doppelt} Artikel stehen schon im Auftrag.\n\n"
                                          "Trotzdem noch einmal eintragen?") == QMessageBox.Yes
        m = rechnen.maschine(self.kopf, self.k)
        erg = step.uebernehmen(messwerte, self.positionen, self.k, self.tabellen["gewinde"], m, werkstoff, stueck,
                               neue_profile, erneut)
        self.db.profile_anlegen(erg["profile"])
        for p in erg["positionen"]:
            self.db.position_neu(self.id, p)
        self.db.protokoll_anhaengen(self.id, erg["protokoll"])
        self.neu_laden()
        text = f"{len(erg['positionen'])} Position(en) in den Auftrag übernommen."
        self.f.meldung(text)
        if not self.f.stumm:
            box = QMessageBox(QMessageBox.Information, "STEP-Import", text, parent=self)
            box.setDetailedText("\n".join(erg["bericht"]))
            box.exec()
        return erg

    def _step_dialog(self):
        d = QDialog(self)
        d.setWindowTitle("STEP-Import")
        form = QFormLayout(d)
        wst = QComboBox()
        wst.addItems([""] + self.k.auswahl("werkstoff"))
        stk = QSpinBox()
        stk.setRange(0, 100000)
        stk.setSpecialValueText("leer lassen")
        form.addRow(QLabel("Werte für alle importierten Teile (leer = später eintragen):"))
        form.addRow("Werkstoff-ID", wst)
        form.addRow("Stückzahl", stk)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(d.accept)
        knoepfe.rejected.connect(d.reject)
        form.addRow(knoepfe)
        if d.exec() != QDialog.Accepted:
            return None
        return wst.currentText() or None, stk.value() or None

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
