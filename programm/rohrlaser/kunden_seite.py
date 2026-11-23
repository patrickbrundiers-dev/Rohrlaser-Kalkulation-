"""Reiter und Menü „Kunden“ (Patrick 23.11.2026, Master-Auftrag Kundenverwaltung). Daten und Regeln in kunden_daten.py.

Aufbau des Reiters: links die Unterbereiche (Kundenübersicht, Neuen Kunden anlegen, Kunden bearbeiten,
Ansprechpartner, Kundenhistorie, Angebote des Kunden, Aufträge des Kunden, Dokumente und Anhänge, Archivierte
Kunden, Tabellenansicht), rechts die Seite dazu:
- Übersicht: Live-Suche, Filter Status und Gruppe, Tabelle oder Karten, Knöpfe Öffnen/Bearbeiten/Duplizieren/
  Archivieren/Export/Import; Doppelklick öffnet das Kundenprofil.
- Kundenprofil mit acht Reitern (Übersicht mit Kennzahlen, Stammdaten mit Adressen, Ansprechpartner, Angebote,
  Aufträge, Dokumente, Historie, Interne Notizen).
- Tabellenansicht: die bisherige Kundentabelle (alle Felder, Tippen/F2, CSV, Datenauskunft, Teilekatalog,
  Kundenwert) unverändert.
Eingabemaske (KundenFormular) mehrstufig in Reitern ohne Scrollen, Dublettenprüfung beim Tippen und vor dem Anlegen.
Kundensuche (KundenSuche) auch im Angebot.
"""
import datetime
from pathlib import Path

from PySide6.QtCore import QModelIndex, QRect, QSize, QSortFilterProxyModel, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QListView, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QPlainTextEdit, QPushButton, QSplitter, QStackedWidget, QStyle, QStyledItemDelegate,
                               QTableView, QTableWidget, QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout,
                               QWidget)

from . import kunden_daten as kd
from . import stil
from .kacheln import KachelZeile

STATUS_FARBE = {kd.AKTIV: ("#1E6B34", "#E3F4E8"), kd.INAKTIV: ("#5F6B7A", "#ECEEF1"),
                kd.GESPERRT: ("#B42318", "#FDECEA")}
SPALTEN = (("kundennr", "Kundennummer"), ("name", "Firmenname"), ("kontakt", "Ansprechpartner"),
           ("ort_anzeige", "Ort"), ("telefon_anzeige", "Telefon"), ("email_anzeige", "E-Mail"),
           ("n_angebote", "Angebote"), ("n_auftraege", "Aufträge"), ("letzter_kontakt", "Letzter Kontakt"),
           ("status", "Status"), ("kundengruppe", "Gruppe"))
ZAHL_SPALTEN = ("n_angebote", "n_auftraege")
BEREICHE = (("uebersicht", "Kundenübersicht", "liste"), ("neu", "Neuen Kunden anlegen", "neu"),
            ("bearbeiten", "Kunden bearbeiten", "einstellungen"), ("personen", "Ansprechpartner", "kunden"),
            ("historie", "Kundenhistorie", "rueckgaengig"), ("angebote", "Angebote des Kunden", "angebote"),
            ("auftraege", "Aufträge des Kunden", "auftraege"), ("dokumente", "Dokumente und Anhänge", "ordner"),
            ("archiv", "Archivierte Kunden", "sichern"), ("tabelle", "Tabellenansicht (alle Felder)", "liste"))
PROFIL_REITER = ("Übersicht", "Stammdaten", "Ansprechpartner", "Angebote", "Aufträge", "Dokumente", "Historie",
                 "Interne Notizen")
REITER_ZU = {"bearbeiten": 1, "personen": 2, "angebote": 3, "auftraege": 4, "dokumente": 5, "historie": 6}
ROLLE = Qt.UserRole + 1
SORT = Qt.UserRole + 2


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y") if iso else ""
    except ValueError:
        return str(iso)


def _eur(x):
    return f"{float(x or 0):,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _symbol(name):
    try:
        from .symbole import symbol
        return symbol(name)
    except Exception:
        from PySide6.QtGui import QIcon
        return QIcon()


def _knopf(text, tipp, aktion, symbol=None):
    k = QPushButton(text)
    k.setToolTip(tipp)
    k.clicked.connect(lambda _=False: aktion())
    if symbol:
        k.setIcon(_symbol(symbol))
    return k


def _titel(text, groesse=1.35):
    t = QLabel(text)
    f = QFont(t.font())
    f.setPointSizeF(f.pointSizeF() * groesse)
    f.setBold(True)
    t.setFont(f)
    return t


def _grau(text=""):
    t = QLabel(text)
    t.setStyleSheet(f"color: {stil.TEXT_GRAU};")
    t.setWordWrap(True)
    return t


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(list(spalten))
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _fuellen(t, zeilen, daten=None):
    t.setRowCount(len(zeilen))
    for r, z in enumerate(zeilen):
        for c, w in enumerate(z):
            it = QTableWidgetItem("" if w is None else str(w))
            if daten is not None and c == 0:
                it.setData(Qt.UserRole, daten[r])
            t.setItem(r, c, it)


def _gewaehlt(t):
    r = t.currentRow()
    it = t.item(r, 0) if r >= 0 else None
    return it.data(Qt.UserRole) if it is not None else None


def status_html(status):
    v, h = STATUS_FARBE.get(status or kd.AKTIV, STATUS_FARBE[kd.AKTIV])
    return (f"<span style='color:{stil.umsetzen(v)}; background:{stil.umsetzen(h)}; padding:1px 6px; "
            f"border-radius:3px;'>&nbsp;{status or kd.AKTIV}&nbsp;</span>")


def fehler_zeigen(eltern, titel, e, stumm=False):
    """Fehler verständlich zeigen (Konflikt mit Kollegen, Lesemodus, Eingabe); im Selbsttest nur zurückgeben."""
    from .datenbank import AenderungsKonflikt
    if isinstance(e, AenderungsKonflikt):
        text = ("Ein Kollege hat dieses Feld inzwischen geändert (Abgleich). Ihre Eingabe ist nicht gespeichert, "
                f"damit nichts überschrieben wird. Gespeichert ist jetzt: „{e.jetzt}“. Bitte den Kunden neu öffnen "
                "und die Änderung erneut eintragen.")
    else:
        text = str(e) or type(e).__name__
    if not stumm:
        QMessageBox.warning(eltern, titel, text)
    return text


# ================================================================== Übersicht
class KundenFilter(QSortFilterProxyModel):
    """Filter der Übersicht über kunden_daten.filtern (Live-Suche, Status, Gruppe)."""

    def __init__(self):
        super().__init__()
        self.suche, self.status, self.gruppe = "", None, None
        self.setSortRole(SORT)

    def setzen(self, suche=None, status=None, gruppe=None):
        if suche is not None:
            self.suche = suche
        self.status, self.gruppe = status, gruppe
        self.invalidateFilter()

    def filterAcceptsRow(self, zeile, eltern):
        z = self.sourceModel().index(zeile, 0, eltern).data(ROLLE)
        return bool(z) and bool(kd.filtern([z], self.suche, self.status, self.gruppe))


class KarteDelegate(QStyledItemDelegate):
    """Kartenansicht: Name groß, Nummer und Ort, Ansprechpartner, Zahlen, Status farbig."""
    GROESSE = QSize(300, 112)

    def sizeHint(self, option, index):
        return self.GROESSE

    def paint(self, p, option, index):
        z = index.data(ROLLE) or {}
        r = option.rect.adjusted(5, 5, -5, -5)
        p.save()
        gewaehlt = bool(option.state & QStyle.State_Selected)
        p.setPen(stil.farbe(stil.AKZENT if gewaehlt else stil.RAHMEN))
        p.setBrush(stil.farbe(stil.BLAU_FLAECHE if gewaehlt else "#FFFFFF"))
        p.drawRoundedRect(r, 6, 6)
        v, h = STATUS_FARBE.get(z.get("status") or kd.AKTIV, STATUS_FARBE[kd.AKTIV])
        p.fillRect(QRect(r.left() + 1, r.top() + 6, 4, r.height() - 12), stil.farbe(v))
        f = QFont(option.font)
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.12)
        p.setFont(f)
        p.setPen(stil.farbe(stil.TEXT))
        innen = r.adjusted(14, 8, -10, -8)
        p.drawText(QRect(innen.left(), innen.top(), innen.width() - 70, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(str(z.get("name") or ""), Qt.ElideRight, innen.width() - 74))
        f2 = QFont(option.font)
        p.setFont(f2)
        p.setPen(stil.farbe(v))
        p.drawText(QRect(innen.right() - 70, innen.top(), 70, 20), Qt.AlignRight | Qt.AlignVCenter,
                   z.get("status") or kd.AKTIV)
        p.setPen(stil.farbe(stil.TEXT_GRAU))
        zeilen = [" · ".join(x for x in (str(z.get("kundennr") or ""), z.get("ort_anzeige") or "",
                                         z.get("kundengruppe") or "") if x),
                  " · ".join(x for x in (z.get("kontakt") or "", z.get("telefon_anzeige") or "") if x) or "–",
                  f"{z.get('n_angebote', 0)} Angebote · {z.get('n_auftraege', 0)} Aufträge"
                  + (f" · zuletzt {_datum(z['letzter_kontakt'])}" if z.get("letzter_kontakt") else "")]
        for i, t in enumerate(zeilen):
            p.drawText(QRect(innen.left(), innen.top() + 24 + i * 19, innen.width(), 18), Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(t, Qt.ElideRight, innen.width()))
        p.restore()


class Uebersicht(QWidget):
    """Kundenübersicht (archiv=False) bzw. archivierte Kunden (archiv=True)."""
    oeffnen = Signal(str)

    def __init__(self, bereich, archiv=False):
        super().__init__()
        self.b, self.db, self.archiv = bereich, bereich.db, archiv
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        kopf = QHBoxLayout()
        kopf.addWidget(_titel("Archivierte Kunden" if archiv else "Kundenübersicht"))
        self.anzahl = _grau()
        kopf.addWidget(self.anzahl)
        kopf.addStretch(1)
        self.als_karten = QToolButton()
        self.als_karten.setText("Karten")
        self.als_karten.setCheckable(True)
        self.als_karten.setToolTip("Zwischen Tabelle und Kartenansicht wechseln")
        self.als_karten.toggled.connect(self._ansicht)
        kopf.addWidget(self.als_karten)
        lay.addLayout(kopf)
        leiste = QHBoxLayout()
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Nummer, Firma, Ort, Ansprechpartner, Telefon, E-Mail, Gruppe …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(lambda t: self._filtern())
        leiste.addWidget(self.suche, 1)
        self.status = QComboBox()
        self.status.addItems(["Alle Status", *kd.STATUS])
        self.status.currentIndexChanged.connect(lambda _: self._filtern())
        self.gruppe = QComboBox()
        self.gruppe.addItem("Alle Gruppen")
        self.gruppe.currentIndexChanged.connect(lambda _: self._filtern())
        leiste.addWidget(self.status)
        leiste.addWidget(self.gruppe)
        lay.addLayout(leiste)
        knoepfe = QHBoxLayout()
        self.knopf = {}
        liste = [("oeffnen", "Öffnen", "Kundenprofil öffnen (auch Doppelklick oder Enter)", self.oeffnen_gewaehlt,
                  "oeffnen")]
        if not archiv:
            liste = [("neu", "Neuer Kunde …", "Neuen Kunden anlegen (mit Dublettenprüfung)",
                      lambda: self.b.neuer_kunde(), "neu")] + liste + [
                ("bearbeiten", "Bearbeiten …", "Stammdaten des gewählten Kunden bearbeiten",
                 lambda: self._mit(self.b.kunde_bearbeiten), "einstellungen"),
                ("duplizieren", "Duplizieren", "Kopie mit neuer Kundennummer (ohne USt-ID und Historie)",
                 lambda: self._mit(self.b.kunde_duplizieren), "kopieren"),
                ("archivieren", "Archivieren", "Kunden ins Archiv (Daten und Angebote bleiben)",
                 lambda: self._mit(self.b.kunde_archivieren), "sichern")]
        else:
            liste.append(("zurueck", "Aus dem Archiv holen", "Kunden wieder in die Übersicht",
                          lambda: self._mit(lambda nr: self.b.kunde_archivieren(nr, an=False)), "wiederherstellen"))
        for name, text, tipp, aktion, sym in liste:
            self.knopf[name] = _knopf(text, tipp, aktion, sym)
            knoepfe.addWidget(self.knopf[name])
        knoepfe.addStretch(1)
        export = QPushButton("Export")
        export.setIcon(_symbol("ausgaben"))
        m = QMenu(export)
        m.addAction("Excel-Datei (.xlsx) …", lambda: self.exportieren("xlsx"))
        m.addAction("CSV-Datei …", lambda: self.exportieren("csv"))
        export.setMenu(m)
        export.setToolTip("Gefilterte Kundenliste als Excel- oder CSV-Datei speichern")
        knoepfe.addWidget(export)
        if not archiv:
            imp = _knopf("Import …", "Kunden aus einer CSV-Datei (Excel: „Speichern unter CSV“), mit Vorschau, "
                                     "Prüfung und Datensicherung vorher", lambda: self.b.tabelle.kunden_importieren(),
                         "oeffnen")
            knoepfe.addWidget(imp)
        lay.addLayout(knoepfe)
        self.modell = QStandardItemModel(0, len(SPALTEN))
        self.modell.setHorizontalHeaderLabels([t for _, t in SPALTEN])
        self.filter = KundenFilter()
        self.filter.setSourceModel(self.modell)
        self.stapel = QStackedWidget()
        self.ansicht = QTableView()
        self.ansicht.setModel(self.filter)
        self.ansicht.setSortingEnabled(True)
        self.ansicht.sortByColumn(1, Qt.AscendingOrder)
        self.ansicht.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ansicht.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ansicht.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ansicht.verticalHeader().setVisible(False)
        self.ansicht.verticalHeader().setDefaultSectionSize(26)
        self.ansicht.horizontalHeader().setStretchLastSection(True)
        self.ansicht.doubleClicked.connect(lambda i: self.oeffnen_gewaehlt())
        self.ansicht.activated.connect(lambda i: self.oeffnen_gewaehlt())
        self.ansicht.setObjectName("kunden_uebersicht" + ("_archiv" if archiv else ""))
        try:
            from .spaltenbreite import AutoGroesse
            AutoGroesse(self.ansicht)
        except Exception:
            pass
        self.karten = QListView()
        self.karten.setModel(self.filter)
        self.karten.setViewMode(QListView.IconMode)
        self.karten.setResizeMode(QListView.Adjust)
        self.karten.setMovement(QListView.Static)
        self.karten.setUniformItemSizes(True)
        self.karten.setSpacing(2)
        self.karten.setItemDelegate(KarteDelegate(self.karten))
        self.karten.doubleClicked.connect(lambda i: self.oeffnen_gewaehlt())
        self.karten.activated.connect(lambda i: self.oeffnen_gewaehlt())
        self.karten.setSelectionModel(self.ansicht.selectionModel())
        self.stapel.addWidget(self.ansicht)
        self.stapel.addWidget(self.karten)
        lay.addWidget(self.stapel, 1)
        self.zeilen = []

    def _ansicht(self, karten):
        self.stapel.setCurrentIndex(1 if karten else 0)
        try:
            self.db.einstellung_setzen("kunden_ansicht", "Karten" if karten else "Tabelle")
        except Exception:
            pass

    def neu_laden(self):
        gewaehlt = self.gewaehlt()
        self.zeilen = kd.uebersicht(self.db, archiv=self.archiv)
        self.modell.setRowCount(0)
        for z in self.zeilen:
            zeile = []
            for n, _ in SPALTEN:
                w = z.get(n)
                text = _datum(w) if n == "letzter_kontakt" else ("" if w is None else str(w))
                it = QStandardItem(text)
                it.setEditable(False)
                it.setData(z, ROLLE)
                it.setData(w if n in ZAHL_SPALTEN else (str(w or "") if n != "letzter_kontakt" else str(w or "")).lower()
                           if not isinstance(w, (int, float)) else w, SORT)
                if n in ZAHL_SPALTEN:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if n == "status":
                    v, h = STATUS_FARBE.get(w or kd.AKTIV, STATUS_FARBE[kd.AKTIV])
                    it.setForeground(stil.farbe(v))
                zeile.append(it)
            self.modell.appendRow(zeile)
        alt = self.gruppe.currentText()
        self.gruppe.blockSignals(True)
        self.gruppe.clear()
        self.gruppe.addItems(["Alle Gruppen", *kd.gruppen(self.db)])
        self.gruppe.setCurrentText(alt if self.gruppe.findText(alt) >= 0 else "Alle Gruppen")
        self.gruppe.blockSignals(False)
        karten = (self.db.einstellung("kunden_ansicht") or "Tabelle") == "Karten"
        if self.als_karten.isChecked() != karten:
            self.als_karten.blockSignals(True)
            self.als_karten.setChecked(karten)
            self.als_karten.blockSignals(False)
            self.stapel.setCurrentIndex(1 if karten else 0)
        self._filtern()
        if gewaehlt:
            self.waehlen(gewaehlt)

    def _filtern(self):
        st = self.status.currentText()
        gr = self.gruppe.currentText()
        self.filter.setzen(self.suche.text(), None if st == "Alle Status" else st,
                           None if gr in ("", "Alle Gruppen") else gr)
        self.anzahl.setText(f"{self.filter.rowCount()} von {len(self.zeilen)} Kunden")

    def gewaehlt(self):
        """Kundennummer der gewählten Zeile/Karte oder None."""
        i = self.ansicht.currentIndex()
        if not i.isValid():
            rows = self.ansicht.selectionModel().selectedRows() if self.ansicht.selectionModel() else []
            i = rows[0] if rows else QModelIndex()
        z = i.data(ROLLE) if i.isValid() else None
        return (z or {}).get("kundennr")

    def waehlen(self, kundennr):
        for r in range(self.filter.rowCount()):
            i = self.filter.index(r, 0)
            if str((i.data(ROLLE) or {}).get("kundennr")) == str(kundennr):
                self.ansicht.selectRow(r)
                self.ansicht.setCurrentIndex(i)
                return True
        return False

    def _mit(self, aktion):
        nr = self.gewaehlt()
        if not nr:
            self.b.meldung("Bitte zuerst einen Kunden wählen.", fehler=True)
            return None
        return aktion(nr)

    def oeffnen_gewaehlt(self):
        return self._mit(lambda nr: self.oeffnen.emit(nr) or nr)

    def exportieren(self, art, pfad=None):
        zeilen = [self.filter.index(r, 0).data(ROLLE) for r in range(self.filter.rowCount())]
        if pfad is None:
            vorschlag = str(Path.home() / f"Kunden_{datetime.date.today().isoformat()}.{art}")
            pfad, _ = QFileDialog.getSaveFileName(self, "Kunden exportieren", vorschlag,
                                                  "Excel (*.xlsx)" if art == "xlsx" else "CSV (*.csv)")
            if not pfad:
                return None
        try:
            (kd.export_xlsx if art == "xlsx" else kd.export_csv)(zeilen, pfad)
        except (OSError, RuntimeError) as e:
            self.b.meldung(f"Export nicht möglich: {e}", fehler=True)
            return None
        self.b.meldung(f"{len(zeilen)} Kunden exportiert: {pfad}")
        return pfad


# ================================================================== Kundenprofil
class Profil(QWidget):
    """Detailansicht eines Kunden mit acht Reitern."""

    def __init__(self, bereich):
        super().__init__()
        self.b, self.db = bereich, bereich.db
        self.kundennr = None
        self.k = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        kopf = QHBoxLayout()
        zurueck = QToolButton()
        zurueck.setText("‹ Übersicht")
        zurueck.setToolTip("Zurück zur Kundenübersicht")
        zurueck.clicked.connect(lambda: self.b.zeigen("uebersicht"))
        kopf.addWidget(zurueck)
        self.name = _titel("", 1.5)
        kopf.addWidget(self.name)
        self.status = QLabel()
        self.status.setTextFormat(Qt.RichText)
        kopf.addWidget(self.status)
        kopf.addStretch(1)
        self.knopf = {}
        for name, text, tipp, aktion, sym in (
                ("bearbeiten", "Bearbeiten …", "Stammdaten, Anschrift, Kaufmännisches und Konditionen ändern",
                 lambda: self.b.kunde_bearbeiten(self.kundennr), "einstellungen"),
                ("angebot", "Neues Angebot", "Neues Angebot für diesen Kunden (Daten, Konditionen, Ansprechpartner "
                                             "und Lieferadresse werden übernommen)",
                 lambda: self.b.neues_angebot(self.kundennr), "angebote"),
                ("mail", "E-Mail …", "E-Mail an den Hauptansprechpartner (sonst an die allgemeine Adresse) im "
                                     "Mailprogramm (Outlook)", lambda: self.mail(), "mail"),
                ("archivieren", "Archivieren", "Kunden ins Archiv bzw. zurückholen",
                 lambda: self.b.kunde_archivieren(self.kundennr, an=self.k.get("archiviert") != "ja"), "sichern")):
            self.knopf[name] = _knopf(text, tipp, aktion, sym)
            kopf.addWidget(self.knopf[name])
        lay.addLayout(kopf)
        self.unter = _grau()
        lay.addWidget(self.unter)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet(f"background: {stil.GELB_FLAECHE}; color: {stil.GELB_TEXT}; padding: 4px 8px;"
                                   " border-radius: 3px;")
        self.hinweis.hide()
        lay.addWidget(self.hinweis)
        self.reiter = QTabWidget()
        lay.addWidget(self.reiter, 1)
        self._uebersicht_bauen()
        self._stammdaten_bauen()
        self._personen_bauen()
        self._angebote_bauen()
        self._auftraege_bauen()
        self._dokumente_bauen()
        self._historie_bauen()
        self._notizen_bauen()

    # ---------------------------------------------------------- Reiter bauen
    def _uebersicht_bauen(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.kacheln = KachelZeile((
            ("umsatz", "Gesamtumsatz", "Verkaufspreis netto aller beauftragten Angebote des Kunden"),
            ("angebote", "Angebote", "Alle Angebote des Kunden ohne ersetzte Fassungen (auch die der Kollegen)"),
            ("auftraege", "Aufträge", "Aufträge des Kunden (Seite Aufträge)"),
            ("quote", "Angebotsquote", "Beauftragt ÷ (beauftragt + abgelehnt)"),
            ("letzter", "Letzter Auftrag", "Datum des letzten Auftrags bzw. der letzten Beauftragung"),
            ("offen", "Offene Angebote", "Verschickt, noch ohne Entscheidung"),
            ("laufend", "Laufende Aufträge", "Aufträge, die noch nicht ausgeliefert sind")))
        self.kacheln.geklickt.connect(self._kachel)
        lay.addWidget(self.kacheln)
        raster = QGridLayout()
        self.info = {}
        for i, (n, t) in enumerate((("anschrift", "Anschrift"), ("kontakt", "Hauptansprechpartner"),
                                    ("konditionen", "Konditionen"), ("weiteres", "Weiteres"))):
            karte = QFrame()
            karte.setObjectName("karte")
            kl = QVBoxLayout(karte)
            kl.addWidget(_titel(t, 1.05))
            lab = QLabel()
            lab.setTextFormat(Qt.RichText)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextBrowserInteraction)
            lab.setOpenExternalLinks(True)
            lab.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            kl.addWidget(lab, 1)
            self.info[n] = lab
            raster.addWidget(karte, i // 2, i % 2)
        lay.addLayout(raster)
        lay.addStretch(1)
        self.reiter.addTab(w, PROFIL_REITER[0])

    def _stammdaten_bauen(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        oben = QHBoxLayout()
        self.stamm = {}
        for n, bereich in (("allgemein", kd.ALLGEMEIN), ("anschrift", kd.ANSCHRIFT + kd.KONTAKT),
                           ("kaufm", kd.KAUFMAENNISCH + kd.VORGABEN)):
            karte = QFrame()
            karte.setObjectName("karte")
            f = QFormLayout(karte)
            f.addRow(_titel({"allgemein": "Allgemein", "anschrift": "Anschrift und Kontakt",
                             "kaufm": "Kaufmännisch und Konditionen"}[n], 1.05))
            for feld, titel in bereich:
                lab = QLabel()
                lab.setWordWrap(True)
                lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
                f.addRow(titel + ":", lab)
                self.stamm[feld] = lab
            oben.addWidget(karte, 1)
        lay.addLayout(oben)
        zeile = QHBoxLayout()
        zeile.addWidget(_titel("Adressen (Rechnung, Lieferung, Standorte)", 1.05))
        zeile.addStretch(1)
        for text, tipp, aktion, sym in (
                ("Adresse hinzufügen …", "Rechnungsadresse, weitere Lieferadresse oder Standort", self.adresse_neu, "neu"),
                ("Bearbeiten …", "Gewählte Adresse ändern", self.adresse_bearbeiten, "einstellungen"),
                ("Entfernen", "Gewählte Adresse löschen", self.adresse_loeschen, "loeschen")):
            zeile.addWidget(_knopf(text, tipp, aktion, sym))
        lay.addLayout(zeile)
        self.adr_tabelle = _tabelle(("Art", "Bezeichnung", "Anschrift", "Standard"))
        self.adr_tabelle.doubleClicked.connect(lambda _: self.adresse_bearbeiten())
        lay.addWidget(self.adr_tabelle, 1)
        self.reiter.addTab(w, PROFIL_REITER[1])

    def _personen_bauen(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        zeile = QHBoxLayout()
        for text, tipp, aktion, sym in (
                ("Neuer Ansprechpartner …", "Ansprechpartner anlegen", self.person_neu, "neu"),
                ("Bearbeiten …", "Gewählten Ansprechpartner ändern", self.person_bearbeiten, "einstellungen"),
                ("Entfernen", "Gewählten Ansprechpartner löschen", self.person_loeschen, "loeschen"),
                ("E-Mail …", "E-Mail an den gewählten Ansprechpartner", self.person_mail, "mail")):
            zeile.addWidget(_knopf(text, tipp, aktion, sym))
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.pers_tabelle = _tabelle(("Name", "Position", "Abteilung", "Telefon", "Mobil", "E-Mail", "Rollen",
                                      "Zuständigkeit", "Aktiv"))
        self.pers_tabelle.doubleClicked.connect(lambda _: self.person_bearbeiten())
        lay.addWidget(self.pers_tabelle, 1)
        self.reiter.addTab(w, PROFIL_REITER[2])

    def _angebote_bauen(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("Neues Angebot", "Neues Angebot für diesen Kunden",
                               lambda: self.b.neues_angebot(self.kundennr), "angebote"))
        zeile.addWidget(_knopf("Öffnen", "Gewähltes Angebot öffnen (auch Doppelklick)", self.angebot_oeffnen, "oeffnen"))
        zeile.addWidget(_knopf("In Angebotsliste zeigen", "Reiter Angebote auf diesen Kunden gefiltert",
                               lambda: self.b.f.kunden_angebote(self.kundennr, self.k.get("name")) if self.b.f else None,
                               "liste"))
        self.ang_summe = _grau()
        zeile.addWidget(self.ang_summe)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.ang_tabelle = _tabelle(("Angebot", "Datum", "Vorgang", "Wert netto €", "Bearbeiter", "Ihre Anfrage",
                                     "Projekt"))
        self.ang_tabelle.doubleClicked.connect(lambda _: self.angebot_oeffnen())
        lay.addWidget(self.ang_tabelle, 1)
        self.reiter.addTab(w, PROFIL_REITER[3])

    def _auftraege_bauen(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("Öffnen", "Gewählten Auftrag auf der Seite Aufträge zeigen (auch Doppelklick)",
                               self.auftrag_oeffnen, "oeffnen"))
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.auf_tabelle = _tabelle(("Auftrag", "Auftragsdatum", "Status", "Liefertermin", "Bestellnr.", "Projekt"))
        self.auf_tabelle.doubleClicked.connect(lambda _: self.auftrag_oeffnen())
        lay.addWidget(self.auf_tabelle, 1)
        self.reiter.addTab(w, PROFIL_REITER[4])

    def _dokumente_bauen(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        zeile = QHBoxLayout()
        for text, tipp, aktion, sym in (
                ("Datei hinzufügen …", "Datei in den Dokumentenordner des Kunden kopieren (Original bleibt)",
                 self.dokument_neu, "neu"),
                ("Öffnen", "Gewählte Datei öffnen", self.dokument_oeffnen, "oeffnen"),
                ("Ordner öffnen", "Dokumentenordner des Kunden im Explorer", self.ordner_oeffnen, "ordner")):
            zeile.addWidget(_knopf(text, tipp, aktion, sym))
        self.dok_ort = _grau()
        zeile.addWidget(self.dok_ort, 1)
        lay.addLayout(zeile)
        self.dok_tabelle = _tabelle(("Datei", "Geändert", "Größe"))
        self.dok_tabelle.doubleClicked.connect(lambda _: self.dokument_oeffnen())
        lay.addWidget(self.dok_tabelle, 1)
        self.reiter.addTab(w, PROFIL_REITER[5])

    def _historie_bauen(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("Kontakt erfassen …", "Telefonat, Besuch, E-Mail … mit Text in die Historie",
                               self.kontakt_neu, "neu"))
        self.hist_alles = QCheckBox("mit Angeboten und Aufträgen")
        self.hist_alles.setChecked(True)
        self.hist_alles.toggled.connect(lambda _: self._historie_fuellen())
        zeile.addWidget(self.hist_alles)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.hist_tabelle = _tabelle(("Zeit", "Wer", "Art", "Feld", "Alt", "Neu", "Text"))
        lay.addWidget(self.hist_tabelle, 1)
        self.reiter.addTab(w, PROFIL_REITER[6])

    def _notizen_bauen(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_grau("Nur intern – erscheint nicht im Angebot. Der Kundenhinweis (Reiter Stammdaten → "
                            "Bearbeiten) steht dagegen groß im Angebotskopf."))
        lay.addWidget(QLabel("Interne Kundennotizen:"))
        self.notizen = QPlainTextEdit()
        lay.addWidget(self.notizen, 2)
        lay.addWidget(QLabel("Individuelle Preisvereinbarungen (sichtbar im Angebotskopf beim Kalkulieren):"))
        self.preisvereinbarung = QPlainTextEdit()
        lay.addWidget(self.preisvereinbarung, 1)
        zeile = QHBoxLayout()
        zeile.addStretch(1)
        self.notiz_speichern = _knopf("Notizen speichern", "Notizen und Preisvereinbarung speichern (mit Historie)",
                                      self.notizen_speichern, "sichern")
        zeile.addWidget(self.notiz_speichern)
        lay.addLayout(zeile)
        self.reiter.addTab(w, PROFIL_REITER[7])

    # ---------------------------------------------------------- Anzeigen
    def zeigen(self, kundennr, reiter=0):
        k = kd.kunde(self.db, kundennr)
        if k is None:
            self.b.meldung(f"Kunde {kundennr} gibt es nicht (mehr).", fehler=True)
            return False
        self.kundennr, self.k = str(kundennr), k
        self.neu_laden()
        self.reiter.setCurrentIndex(reiter)
        return True

    def neu_laden(self):
        if not self.kundennr:
            return
        k = kd.kunde(self.db, self.kundennr)
        if k is None:
            return
        self.k = k
        self.name.setText(" ".join(x for x in (k.get("name"), k.get("firmenzusatz")) if x))
        self.status.setText(status_html(k.get("status")) + (" &nbsp;<b>Archiviert</b>" if k.get("archiviert") == "ja"
                                                            else ""))
        self.unter.setText(" · ".join(x for x in (f"Kunden-Nr. {k['kundennr']}", k.get("kundentyp"), k.get("branche"),
                                                  k.get("kundengruppe"),
                                                  f"angelegt {_datum(k.get('angelegt'))}" if k.get("angelegt") else "")
                                      if x))
        self.knopf["archivieren"].setText("Aus dem Archiv holen" if k.get("archiviert") == "ja" else "Archivieren")
        hw = " · ".join(x for x in (k.get("hinweis"), "Kunde gesperrt" if k.get("status") == kd.GESPERRT else "",
                                    f"Preisvereinbarung: {k['preisvereinbarung']}" if k.get("preisvereinbarung")
                                    else "") if x)
        self.hinweis.setText(hw)
        self.hinweis.setVisible(bool(hw))
        self._uebersicht_fuellen()
        self._stammdaten_fuellen()
        self._personen_fuellen()
        self._angebote_fuellen()
        self._auftraege_fuellen()
        self._dokumente_fuellen()
        self._historie_fuellen()
        self.notizen.setPlainText(k.get("notizen") or "")
        self.preisvereinbarung.setPlainText(k.get("preisvereinbarung") or "")
        self._notiz_alt = dict(notizen=k.get("notizen"), preisvereinbarung=k.get("preisvereinbarung"))

    def _uebersicht_fuellen(self):
        k = self.k
        z = kd.kennzahlen(self.db, self.kundennr)
        self.zahlen = z
        c = self.kacheln.kacheln
        c["umsatz"].setzen(f"{_eur(z['umsatz'])} €", f"{z['beauftragt']} beauftragt")
        c["angebote"].setzen(str(z["angebote"]), f"{z['entwurf']} im Entwurf" if z["entwurf"] else "")
        c["auftraege"].setzen(str(z["auftraege"]))
        c["quote"].setzen(f"{z['quote'] * 100:.0f} %" if z["quote"] is not None else "–",
                          f"{z['beauftragt']} von {z['beauftragt'] + z['abgelehnt']} entschieden"
                          if z["quote"] is not None else "noch keine Entscheidung")
        c["letzter"].setzen(_datum(z["letzter_auftrag"]) or "–")
        c["offen"].setzen(str(z["offen"]), f"{_eur(z['offen_wert'])} € netto" if z["offen_wert"] else "")
        c["laufend"].setzen(str(z["laufend"]))
        e = lambda t: str(t or "").replace("&", "&amp;").replace("<", "&lt;")    # noqa: E731
        an = "<br>".join(e(x) for x in [k.get("name")] + kd.anschrift(k, "") if x)
        web = k.get("website") or ""
        if web:
            url = web if web.startswith("http") else "https://" + web
            an += f"<br><a href='{e(url)}'>{e(web)}</a>"
        self.info["anschrift"].setText(an or "–")
        ps = kd.ansprechpartner(self.db, self.kundennr, nur_aktiv=True)
        p = next((x for x in ps if x.get("haupt") == "ja"), ps[0] if ps else None)
        if p:
            self.info["kontakt"].setText("<br>".join(x for x in (
                f"<b>{e(kd.name_voll(p))}</b>" + (f" – {e(p['position'])}" if p.get("position") else ""),
                f"Tel. {e(p['telefon'])}" if p.get("telefon") else "", f"Mobil {e(p['mobil'])}" if p.get("mobil") else "",
                f"<a href='mailto:{e(p['email'])}'>{e(p['email'])}</a>" if p.get("email") else "",
                f"{len(ps) - 1} weitere Ansprechpartner" if len(ps) > 1 else "") if x))
        else:
            self.info["kontakt"].setText(e(k.get("ansprechpartner")) or "noch kein Ansprechpartner")
        vg = kd.vorgaben(self.db, self.kundennr)
        kond = [f"Zahlungsziel {k['zahlungsziel']} Tage netto" if k.get("zahlungsziel") is not None else "",
                f"Skonto {k['skonto']:g} % in {k.get('skonto_tage') or 0} Tagen" if k.get("skonto") else "",
                e(k.get("zahlungsbedingung")), f"Rabatt {vg['rabatt']:g} %" if vg.get("rabatt") else "",
                f"Mindestauftragswert {_eur(vg['mindestwert'])} €" if vg.get("mindestwert") else "",
                f"Kreditlimit {_eur(k['kreditlimit'])} €" if k.get("kreditlimit") else "",
                e(k.get("lieferbedingung"))]
        self.info["konditionen"].setText("<br>".join(x for x in kond if x) or "wie in den Einstellungen")
        wt = [f"USt-ID {e(k['ust_id'])}" if k.get("ust_id") else "", f"Währung {e(k['waehrung'])}"
              if k.get("waehrung") else "", f"Zuständig {e(k['zustaendig'])}" if k.get("zustaendig") else "",
              f"Letzter Kontakt {_datum(z['letzter_kontakt'])}" if z.get("letzter_kontakt") else "",
              f"Hinweis: {e(k['hinweis'])}" if k.get("hinweis") else ""]
        self.info["weiteres"].setText("<br>".join(x for x in wt if x) or "–")

    def _kachel(self, schl):
        self.reiter.setCurrentIndex({"angebote": 3, "offen": 3, "quote": 3, "umsatz": 3, "auftraege": 4,
                                     "laufend": 4, "letzter": 4}.get(schl, 0))

    def _stammdaten_fuellen(self):
        k, vg = self.k, kd.vorgaben(self.db, self.kundennr)
        for n, lab in self.stamm.items():
            w = vg.get(n) if n in kd.VORGABE_FELDER else k.get(n)
            if isinstance(w, float):
                w = f"{w:g}".replace(".", ",")
            lab.setText("" if w is None else str(w))
        self._adressen = kd.adressen(self.db, self.kundennr)
        _fuellen(self.adr_tabelle, [(a.get("art"), a.get("bezeichnung"), kd.adresse_text(a, k),
                                     "ja" if a.get("standard") == "ja" else "") for a in self._adressen],
                 [a["id"] for a in self._adressen])

    def _personen_fuellen(self):
        self._personen = kd.ansprechpartner(self.db, self.kundennr)
        _fuellen(self.pers_tabelle, [(kd.name_voll(p), p.get("position"), p.get("abteilung"), p.get("telefon"),
                                      p.get("mobil"), p.get("email"), kd.person_rollen_text(p),
                                      p.get("zustaendigkeit"), "nein" if p.get("aktiv") == "nein" else "ja")
                                     for p in self._personen], [p["id"] for p in self._personen])

    def _angebote_fuellen(self):
        a = kd.angebote(self.db, self.kundennr)
        _fuellen(self.ang_tabelle, [(x["nummer"], _datum(x.get("datum")), x.get("vorgang") or "Entwurf",
                                     _eur(x.get("vk_netto")) if x.get("vk_netto") is not None else "",
                                     x.get("bearbeiter") or x.get("fremd") or "", x.get("kundenreferenz"),
                                     x.get("projekt")) for x in a], [x["id"] for x in a])
        z = getattr(self, "zahlen", None) or kd.kennzahlen(self.db, self.kundennr)
        self.ang_summe.setText(f"{len(a)} Angebote · beauftragt {_eur(z['umsatz'])} € netto")

    def _auftraege_fuellen(self):
        a = kd.auftraege(self.db, self.kundennr)
        _fuellen(self.auf_tabelle, [(x["nummer"], _datum(x.get("auftragsdatum") or x.get("angelegt")),
                                     x.get("status"), _datum(x.get("liefertermin")), x.get("bestellnr"),
                                     x.get("projekt")) for x in a], [x["uid"] for x in a])

    def _dokumente_fuellen(self):
        basis = self.b.dokumente_basis()
        self.dok_ort.setText(str(kd.dokumente_ordner(basis, self.kundennr)) if basis else
                             "kein Ablageordner eingerichtet")
        self._dokumente = kd.dokumente(basis, self.kundennr) if basis else []
        _fuellen(self.dok_tabelle, [(d["name"], _datum(d["geaendert"]) + " " + d["geaendert"][11:16],
                                     f"{d['groesse'] / 1024:.0f} KB") for d in self._dokumente],
                 [d["pfad"] for d in self._dokumente])

    def _historie_fuellen(self):
        h = kd.historie(self.db, self.kundennr, mit_vorgaengen=self.hist_alles.isChecked())
        _fuellen(self.hist_tabelle, [(_datum(e.get("zeit")) + " " + str(e.get("zeit") or "")[11:16], e.get("wer"),
                                      e.get("art"), e.get("feld"), e.get("alt"), e.get("neu"), e.get("text"))
                                     for e in h])

    # ---------------------------------------------------------- Aktionen
    def _id(self, t):
        return _gewaehlt(t)

    def person_neu(self, werte=None, stumm=False):
        d = PersonDialog(self, werte or {})
        if not stumm and d.exec() != QDialog.Accepted:
            return None
        try:
            i = kd.person_speichern(self.db, self.kundennr, d.werte())
        except Exception as e:
            fehler_zeigen(self, "Ansprechpartner", e, self.b.stumm)
            return None
        self.b.geaendert(self.kundennr)
        return i

    def person_bearbeiten(self, werte=None, stumm=False):
        pid = self._id(self.pers_tabelle)
        p = next((x for x in getattr(self, "_personen", ()) if x["id"] == pid), None)
        if p is None:
            self.b.meldung("Bitte zuerst einen Ansprechpartner wählen.", fehler=True)
            return None
        d = PersonDialog(self, dict(p, **(werte or {})))
        if not stumm and d.exec() != QDialog.Accepted:
            return None
        try:
            kd.person_speichern(self.db, self.kundennr, d.werte(), pid)
        except Exception as e:
            fehler_zeigen(self, "Ansprechpartner", e, self.b.stumm)
            return None
        self.b.geaendert(self.kundennr)
        return pid

    def person_loeschen(self, bestaetigt=None):
        pid = self._id(self.pers_tabelle)
        if pid is None:
            return False
        if bestaetigt is None and not self.b.stumm:
            bestaetigt = QMessageBox.question(self, "Ansprechpartner", "Gewählten Ansprechpartner entfernen?") == \
                QMessageBox.Yes
        if bestaetigt is False:
            return False
        kd.person_loeschen(self.db, self.kundennr, pid)
        self.b.geaendert(self.kundennr)
        return True

    def _mail_an(self, adresse):
        if not adresse:
            self.b.meldung("Keine E-Mail-Adresse eingetragen.", fehler=True)
            return None
        url = QUrl(f"mailto:{adresse}")
        if not self.b.stumm:
            QDesktopServices.openUrl(url)
        return url.toString()

    def mail(self):
        ps = kd.ansprechpartner(self.db, self.kundennr, nur_aktiv=True)
        p = next((x for x in ps if x.get("haupt") == "ja" and x.get("email")), None) or \
            next((x for x in ps if x.get("email")), None)
        return self._mail_an((p or {}).get("email") or (kd.mails(self.k.get("email")) or [None])[0])

    def person_mail(self):
        pid = self._id(self.pers_tabelle)
        p = next((x for x in getattr(self, "_personen", ()) if x["id"] == pid), None)
        return self._mail_an((p or {}).get("email"))

    def adresse_neu(self, werte=None, stumm=False):
        d = AdresseDialog(self, werte or {"land": "DE"})
        if not stumm and d.exec() != QDialog.Accepted:
            return None
        try:
            i = kd.adresse_speichern(self.db, self.kundennr, d.werte())
        except Exception as e:
            fehler_zeigen(self, "Adresse", e, self.b.stumm)
            return None
        self.b.geaendert(self.kundennr)
        return i

    def adresse_bearbeiten(self, werte=None, stumm=False):
        aid = self._id(self.adr_tabelle)
        a = next((x for x in getattr(self, "_adressen", ()) if x["id"] == aid), None)
        if a is None:
            self.b.meldung("Bitte zuerst eine Adresse wählen.", fehler=True)
            return None
        d = AdresseDialog(self, dict(a, **(werte or {})))
        if not stumm and d.exec() != QDialog.Accepted:
            return None
        try:
            kd.adresse_speichern(self.db, self.kundennr, d.werte(), aid)
        except Exception as e:
            fehler_zeigen(self, "Adresse", e, self.b.stumm)
            return None
        self.b.geaendert(self.kundennr)
        return aid

    def adresse_loeschen(self, bestaetigt=None):
        aid = self._id(self.adr_tabelle)
        if aid is None:
            return False
        if bestaetigt is None and not self.b.stumm:
            bestaetigt = QMessageBox.question(self, "Adresse", "Gewählte Adresse entfernen?") == QMessageBox.Yes
        if bestaetigt is False:
            return False
        kd.adresse_loeschen(self.db, self.kundennr, aid)
        self.b.geaendert(self.kundennr)
        return True

    def angebot_oeffnen(self):
        i = self._id(self.ang_tabelle)
        if i is not None and self.b.f is not None:
            return self.b.f.angebot_oeffnen(i)
        return None

    def auftrag_oeffnen(self):
        uid = self._id(self.auf_tabelle)
        if uid and self.b.f is not None and hasattr(self.b.f, "auftrag_zeigen"):
            return self.b.f.auftrag_zeigen(uid)
        return None

    def dokument_neu(self, pfad=None):
        basis = self.b.dokumente_basis()
        if not basis:
            self.b.meldung("Kein Ablageordner eingerichtet (Einstellungen → Ablage).", fehler=True)
            return None
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "Dokument zum Kunden ablegen", str(Path.home()))
            if not pfad:
                return None
        try:
            ziel = kd.dokument_ablegen(self.db, basis, self.kundennr, pfad)
        except (OSError, kd.KundenFehler) as e:
            fehler_zeigen(self, "Dokument", e, self.b.stumm)
            return None
        self._dokumente_fuellen()
        self._historie_fuellen()
        self.b.meldung(f"Dokument abgelegt: {ziel.name}")
        return ziel

    def dokument_oeffnen(self):
        p = self._id(self.dok_tabelle)
        if p and self.b.f is not None:
            self.b.f.datei_oeffnen(p)
        return p

    def ordner_oeffnen(self):
        basis = self.b.dokumente_basis()
        if not basis or self.b.f is None:
            return None
        o = kd.dokumente_ordner(basis, self.kundennr, anlegen=True)
        self.b.f.datei_oeffnen(o)
        return o

    def kontakt_neu(self, art=None, text=None):
        if art is None or text is None:
            art, ok = QInputDialog.getItem(self, "Kontakt erfassen", "Art:", list(kd.KONTAKT_ARTEN), 0, False)
            if not ok:
                return False
            text, ok = QInputDialog.getMultiLineText(self, "Kontakt erfassen", f"{art} – Inhalt:")
            if not ok:
                return False
        try:
            kd.eintrag(self.db, self.kundennr, kd.H_KONTAKT, f"{art}: {text}")
        except Exception as e:
            fehler_zeigen(self, "Kontakt", e, self.b.stumm)
            return False
        self.b.geaendert(self.kundennr)
        return True

    def notizen_speichern(self):
        neu = dict(notizen=self.notizen.toPlainText().strip() or None,
                   preisvereinbarung=self.preisvereinbarung.toPlainText().strip() or None)
        try:
            basis = dict(self.k, **getattr(self, "_notiz_alt", {}))
            g = kd.speichern(self.db, self.kundennr, dict(basis, **neu), basis)
        except Exception as e:
            fehler_zeigen(self, "Notizen", e, self.b.stumm)
            return None
        self.b.meldung("Notizen gespeichert." if g else "Keine Änderung.")
        self.b.geaendert(self.kundennr)
        return g


# ================================================================== Dialoge
class PersonDialog(QDialog):
    def __init__(self, eltern, p):
        super().__init__(eltern)
        self.setWindowTitle("Ansprechpartner")
        form = QFormLayout(self)
        self.e = {}
        for n in ("anrede", "vorname", "nachname", "position", "abteilung", "telefon", "mobil", "email",
                  "zustaendigkeit", "bemerkung"):
            if n == "anrede":
                w = QComboBox()
                w.setEditable(True)
                w.addItems(["", "Herr", "Frau"])
                w.setCurrentText(str(p.get(n) or ""))
            else:
                w = QLineEdit(str(p.get(n) or ""))
            self.e[n] = w
            form.addRow(kd.ANSPRECHPARTNER.feld(n).titel + ":", w)
        rollen = QHBoxLayout()
        self.r = {}
        for r, t in kd.ROLLEN:
            c = QCheckBox(t)
            c.setChecked(p.get(r) == "ja")
            self.r[r] = c
            rollen.addWidget(c)
        form.addRow("Kennzeichen:", rollen)
        self.aktiv = QCheckBox("aktiv (inaktive erscheinen nicht mehr in der Auswahl im Angebot)")
        self.aktiv.setChecked(p.get("aktiv") != "nein")
        form.addRow("", self.aktiv)
        k = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        form.addRow(k)
        self.setMinimumWidth(460)

    def werte(self):
        w = {n: (e.currentText() if isinstance(e, QComboBox) else e.text()).strip() for n, e in self.e.items()}
        w.update({r: "ja" if c.isChecked() else None for r, c in self.r.items()})
        w["aktiv"] = "ja" if self.aktiv.isChecked() else "nein"
        return w


class AdresseDialog(QDialog):
    def __init__(self, eltern, a):
        super().__init__(eltern)
        self.setWindowTitle("Adresse")
        form = QFormLayout(self)
        self.art = QComboBox()
        self.art.addItems(list(kd.ADRESS_ARTEN))
        self.art.setCurrentText(a.get("art") or kd.LIEFERUNG)
        form.addRow("Art:", self.art)
        self.e = {}
        for n in ("bezeichnung", "name", "zusatz", "strasse", "plz", "ort", "land", "bemerkung"):
            w = QLineEdit(str(a.get(n) or ""))
            self.e[n] = w
            form.addRow(kd.ADRESSEN.feld(n).titel + ":", w)
        self.e["name"].setPlaceholderText("leer = Firmenname des Kunden")
        self.standard = QCheckBox("Standardadresse dieser Art")
        self.standard.setToolTip("Standard-Lieferadresse: Vorschlag im Angebot und Ziel der Frachtzone")
        self.standard.setChecked(a.get("standard") == "ja")
        form.addRow("", self.standard)
        k = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        form.addRow(k)
        self.setMinimumWidth(460)

    def werte(self):
        w = {n: e.text().strip() for n, e in self.e.items()}
        w["art"] = self.art.currentText()
        w["standard"] = "ja" if self.standard.isChecked() else None
        return w


class KundenFormular(QDialog):
    """Eingabemaske neu/bearbeiten: vier Schritte als Reiter (Allgemein und Anschrift · Ansprechpartner ·
    Kaufmännisch und Konditionen · Notizen), je Schritt zwei Spalten, ohne Scrollen. Dubletten erscheinen beim Tippen
    oben (mit „Öffnen“); vor dem Anlegen fragt das Fenster nach."""
    oeffnen_kunde = Signal(str)

    def __init__(self, eltern, db, k=None, vorgaben=None, neu=True, vorschlag=None):
        super().__init__(eltern)
        self.db, self.neu = db, neu
        self.alt = dict(k or {})
        self.vg_alt = dict(vorgaben or {})
        self.setWindowTitle("Neuen Kunden anlegen" if neu else f"Kunde {self.alt.get('kundennr')} bearbeiten")
        lay = QVBoxLayout(self)
        self.dub = QLabel()
        self.dub.setTextFormat(Qt.RichText)
        self.dub.setWordWrap(True)
        self.dub.setStyleSheet(f"background: {stil.GELB_FLAECHE}; color: {stil.GELB_TEXT}; padding: 6px;"
                               " border-radius: 3px;")
        self.dub.linkActivated.connect(lambda nr: self.oeffnen_kunde.emit(nr))
        self.dub.hide()
        lay.addWidget(self.dub)
        self.schritte = QTabWidget()
        lay.addWidget(self.schritte, 1)
        self.e = {}
        w = dict(vorschlag or {}, **{n: v for n, v in self.alt.items() if v not in (None, "")})
        # Schritt 1
        s1 = QWidget()
        g = QHBoxLayout(s1)
        links, rechts = QFormLayout(), QFormLayout()
        for n, t in kd.ALLGEMEIN:
            links.addRow(t + ":", self._feld(n, w.get(n)))
        for n, t in kd.ANSCHRIFT + kd.KONTAKT:
            rechts.addRow(t + ":", self._feld(n, w.get(n)))
        g.addLayout(links, 1)
        g.addSpacing(16)
        g.addLayout(rechts, 1)
        self.schritte.addTab(s1, "Allgemein und Anschrift")
        # Schritt 2 (nur beim Anlegen; danach im Profil)
        self.personen = None
        if neu:
            s2 = QWidget()
            l2 = QVBoxLayout(s2)
            l2.addWidget(_grau("Ansprechpartner für den neuen Kunden (weitere später im Kundenprofil). Der erste mit "
                               "Haken „Haupt“ steht im Angebot als „z. Hd.“."))
            self.personen = QTableWidget(0, 9)
            self.personen.setHorizontalHeaderLabels(["Vorname", "Nachname", "Position", "Telefon", "Mobil", "E-Mail",
                                                     "Haupt", "Einkauf", "Technik"])
            self.personen.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            l2.addWidget(self.personen, 1)
            zl = QHBoxLayout()
            zl.addWidget(_knopf("Zeile hinzufügen", "Weiteren Ansprechpartner eintragen", self.person_zeile, "neu"))
            zl.addStretch(1)
            l2.addLayout(zl)
            for p in (vorschlag or {}).get("ansprechpartner") or [{}]:
                self.person_zeile(p)
            self.schritte.addTab(s2, "Ansprechpartner")
        # Schritt 3
        s3 = QWidget()
        g3 = QHBoxLayout(s3)
        l3, r3 = QFormLayout(), QFormLayout()
        for n, t in kd.KAUFMAENNISCH:
            l3.addRow(t + ":", self._feld(n, w.get(n)))
        for n, t in kd.VORGABEN:
            r3.addRow(t + ":", self._feld(n, self.vg_alt.get(n) if self.vg_alt.get(n) is not None
                                          else (vorschlag or {}).get(n)))
        r3.addRow(_grau("Konditionen gelten für neue Angebote dieses Kunden (leer = Einstellungen); bestehende "
                        "Angebote bleiben unverändert."))
        g3.addLayout(l3, 1)
        g3.addSpacing(16)
        g3.addLayout(r3, 1)
        self.schritte.addTab(s3, "Kaufmännisch und Konditionen")
        # Schritt 4
        s4 = QWidget()
        f4 = QFormLayout(s4)
        for n, t in kd.NOTIZEN:
            f4.addRow(t + ":", self._feld(n, w.get(n), lang=n in ("notizen", "preisvereinbarung")))
        self.schritte.addTab(s4, "Notizen und Hinweise")
        self.fehler = QLabel()
        self.fehler.setStyleSheet(f"color: {stil.ROT};")
        self.fehler.setWordWrap(True)
        lay.addWidget(self.fehler)
        unten = QHBoxLayout()
        self.zurueck = _knopf("‹ Zurück", "Voriger Schritt", lambda: self._schritt(-1))
        self.weiter = _knopf("Weiter ›", "Nächster Schritt", lambda: self._schritt(1))
        unten.addWidget(self.zurueck)
        unten.addWidget(self.weiter)
        unten.addStretch(1)
        self.speichern_knopf = _knopf("Kunde anlegen" if neu else "Speichern", "Alle Eingaben speichern",
                                      self.accept, "sichern")
        self.speichern_knopf.setDefault(True)
        abbrechen = _knopf("Abbrechen", "Ohne Speichern schließen", self.reject)
        unten.addWidget(self.speichern_knopf)
        unten.addWidget(abbrechen)
        lay.addLayout(unten)
        self.schritte.currentChanged.connect(lambda _: self._knoepfe())
        self._knoepfe()
        for n in ("name", "plz", "strasse", "ust_id", "email", "telefon"):
            self.e[n].textChanged.connect(lambda _=None: self.dubletten_pruefen())
        if not neu:
            self.e["kundennr"].setReadOnly(True)
            self.e["kundennr"].setToolTip("Die Kundennummer ändern Sie in der Tabellenansicht (alle Verweise ziehen "
                                          "mit).")
        self.resize(900, 470)
        self.dubletten_pruefen()

    def _feld(self, n, wert, lang=False):
        if n in ("kundentyp", "status", "waehrung", "hinweis_werkstatt", "lieferbedingung"):
            e = QComboBox()
            werte = {"kundentyp": kd.KUNDENTYPEN, "status": kd.STATUS, "waehrung": kd.WAEHRUNGEN,
                     "hinweis_werkstatt": ("", "ja", "nein")}.get(n)
            if n == "lieferbedingung":
                from .fracht_daten import LIEFERBEDINGUNGEN
                werte = ("", *LIEFERBEDINGUNGEN)
            e.addItems([str(x) for x in werte])
            e.setEditable(n in ("waehrung",))
            vorgabe = {"kundentyp": "Firma", "status": kd.AKTIV, "waehrung": "EUR"}.get(n, "")
            e.setCurrentText(str(wert) if wert not in (None, "") else vorgabe)
            e.text = e.currentText
            e.textChanged = e.currentTextChanged
        elif lang:
            e = QPlainTextEdit(str(wert or ""))
            e.setMaximumHeight(110)
            e.text = e.toPlainText
        else:
            if isinstance(wert, float):
                wert = f"{wert:g}".replace(".", ",")
            e = QLineEdit("" if wert is None else str(wert))
        if n == "kundennr" and self.neu:         # Patrick 23.11.2026: Kundennummer immer von Hand
            e.setPlaceholderText(kd.nummer_hinweis(self.db))
        if n == "name":
            e.setPlaceholderText("Pflichtfeld")
        if n == "land" and not (wert or ""):
            e.setText("DE")
        if n == "email":
            e.setPlaceholderText("z. B. info@firma.de")
        self.e[n] = e
        return e

    def person_zeile(self, p=None):
        p = p or {}
        r = self.personen.rowCount()
        self.personen.insertRow(r)
        for c, n in enumerate(("vorname", "nachname", "position", "telefon", "mobil", "email")):
            self.personen.setItem(r, c, QTableWidgetItem(str(p.get(n) or "")))
        for c, n in ((6, "haupt"), (7, "einkauf"), (8, "technik")):
            it = QTableWidgetItem()
            it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setCheckState(Qt.Checked if p.get(n) == "ja" or (n == "haupt" and r == 0 and not p.get(n) == "nein")
                             else Qt.Unchecked)
            self.personen.setItem(r, c, it)

    def personen_werte(self):
        out = []
        if self.personen is None:
            return out
        for r in range(self.personen.rowCount()):
            t = lambda c: (self.personen.item(r, c).text().strip() if self.personen.item(r, c) else "")  # noqa: E731
            p = dict(vorname=t(0), nachname=t(1), position=t(2), telefon=t(3), mobil=t(4), email=t(5))
            for c, n in ((6, "haupt"), (7, "einkauf"), (8, "technik")):
                it = self.personen.item(r, c)
                p[n] = "ja" if it is not None and it.checkState() == Qt.Checked else None
            if p["vorname"] or p["nachname"]:
                if not p["nachname"]:
                    p["nachname"], p["vorname"] = p["vorname"], ""
                out.append(p)
        return out

    def _schritt(self, d):
        self.schritte.setCurrentIndex(max(0, min(self.schritte.count() - 1, self.schritte.currentIndex() + d)))

    def _knoepfe(self):
        i = self.schritte.currentIndex()
        self.zurueck.setEnabled(i > 0)
        self.weiter.setEnabled(i < self.schritte.count() - 1)

    def werte(self):
        return {n: e.text().strip() if isinstance(e.text(), str) else e.text() for n, e in self.e.items()
                if n not in kd.VORGABE_FELDER}

    def vorgaben_werte(self):
        return {n: self.e[n].text().strip() for n in kd.VORGABE_FELDER}

    def dubletten_pruefen(self):
        w = self.werte()
        w["ansprechpartner"] = self.personen_werte()
        d = kd.dubletten(self.db, w, ohne=None if self.neu else self.alt.get("kundennr"))
        self.dubletten = d
        if not d:
            self.dub.hide()
            return d
        e = lambda t: str(t or "").replace("&", "&amp;").replace("<", "&lt;")    # noqa: E731
        zeilen = [f"<a href='{e(k['kundennr'])}'>{e(k['kundennr'])} {e(k.get('name'))}</a> – {e(', '.join(g))}"
                  for k, g, _ in d[:4]]
        self.dub.setText("<b>Mögliche Dublette – gibt es diesen Kunden schon?</b> (Klick öffnet den Kunden)<br>"
                         + "<br>".join(zeilen))
        self.dub.show()
        return d

    def accept(self):
        fehler = kd.pruefen(self.db, self.werte(), None if self.neu else self.alt.get("kundennr"))
        for n in kd.VORGABE_FELDER:
            try:
                kd._wert(n, self.e[n].text())
            except kd.KundenFehler as ex:
                fehler.append(str(ex))
        if fehler:
            self.fehler.setText(" ".join(fehler))
            return
        super().accept()


class KundenSuche(QDialog):
    """Kunden suchen und wählen (Angebot, Anfrage): Live-Suche, Doppelklick/Enter wählt, „Neuer Kunde …“."""

    def __init__(self, eltern, db, suche="", neu=None, titel="Kunde wählen"):
        super().__init__(eltern)
        self.db, self.neu_aktion = db, neu
        self.kundennr = None
        self.setWindowTitle(titel)
        lay = QVBoxLayout(self)
        self.suche = QLineEdit(suche)
        self.suche.setPlaceholderText("Nummer, Firma, Ort, Ansprechpartner, Telefon oder E-Mail …")
        self.suche.setClearButtonEnabled(True)
        lay.addWidget(self.suche)
        self.liste = _tabelle(("Nr.", "Firma", "Ort", "Ansprechpartner", "Telefon", "Status"))
        self.liste.doubleClicked.connect(lambda _: self.accept())
        lay.addWidget(self.liste, 1)
        self.info = _grau()
        lay.addWidget(self.info)
        unten = QHBoxLayout()
        if neu is not None:
            unten.addWidget(_knopf("Neuer Kunde …", "Neuen Kunden anlegen und gleich wählen", self._neu, "neu"))
        unten.addStretch(1)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Ok).setText("Übernehmen")
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        unten.addWidget(k)
        lay.addLayout(unten)
        self.alle = kd.uebersicht(db)
        self.suche.textChanged.connect(lambda _: self.fuellen())
        self.fuellen()
        self.resize(760, 440)

    def fuellen(self):
        z = kd.filtern(self.alle, self.suche.text())
        _fuellen(self.liste, [(x["kundennr"], x.get("name"), x.get("ort_anzeige"), x.get("kontakt"),
                               x.get("telefon_anzeige"), x.get("status")) for x in z[:500]],
                 [x["kundennr"] for x in z[:500]])
        if z:
            self.liste.selectRow(0)
        self.info.setText(f"{len(z)} Treffer" + (" (die ersten 500)" if len(z) > 500 else ""))
        return len(z)

    def _neu(self):
        nr = self.neu_aktion(self.suche.text()) if self.neu_aktion else None
        if nr:
            self.kundennr = nr
            super().accept()

    def accept(self):
        nr = _gewaehlt(self.liste)
        if not nr:
            return
        self.kundennr = nr
        super().accept()


# ================================================================== Bereich (Reiter)
class KundenBereich(QWidget):
    """Reiter Kunden: Unterbereiche links, Seiten rechts. Wie der frühere Reiter (StammdatenSeite) erreichbar über
    suche/filter/ansicht (Übersicht); andere Aufrufe gehen an die Tabellenansicht (tabelle)."""
    titel = "Kunden"

    def __init__(self, f, tabelle, stumm=False):
        super().__init__()
        self.f = f
        self.db = tabelle.db
        self.tabelle = tabelle
        self.stumm = stumm
        self.t = tabelle.t
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        teiler = QSplitter(Qt.Horizontal)
        self.nav = QListWidget()
        self.nav.setObjectName("kunden_navigation")
        self.nav.setMaximumWidth(240)
        self.nav.setMinimumWidth(170)
        for schl, text, sym in BEREICHE:
            it = QListWidgetItem(_symbol(sym), text)
            it.setData(Qt.UserRole, schl)
            self.nav.addItem(it)
        self.nav.itemClicked.connect(lambda it: self.aktion(it.data(Qt.UserRole)))
        teiler.addWidget(self.nav)
        self.stapel = QStackedWidget()
        self.uebersicht = Uebersicht(self)
        self.uebersicht.oeffnen.connect(lambda nr: self.oeffnen(nr))
        self.archiv = Uebersicht(self, archiv=True)
        self.archiv.oeffnen.connect(lambda nr: self.oeffnen(nr))
        self.profil = Profil(self)
        for w in (self.uebersicht, self.profil, self.archiv, self.tabelle):
            self.stapel.addWidget(w)
        teiler.addWidget(self.stapel)
        teiler.setStretchFactor(1, 1)
        teiler.setSizes([190, 1100])
        lay.addWidget(teiler)
        self.nav.setCurrentRow(0)

    # Verträglichkeit mit dem früheren Reiter (Tests, Befehlspalette, kunde_zeigen)
    @property
    def suche(self):
        return self.uebersicht.suche

    @property
    def filter(self):
        return self.uebersicht.filter

    @property
    def ansicht(self):
        return self.uebersicht.ansicht

    def __getattr__(self, name):
        if name in ("tabelle", "uebersicht", "profil", "archiv", "stapel", "nav", "f", "db"):
            raise AttributeError(name)
        return getattr(self.tabelle, name)

    def meldung(self, text, fehler=False):
        if self.f is not None:
            self.f.meldung(text, fehler=fehler)

    def dokumente_basis(self):
        try:
            return self.f.ablage() if self.f is not None else None
        except Exception:
            return None

    def neu_laden(self):
        seite = self.stapel.currentWidget()
        if seite is self.tabelle:
            self.tabelle.neu_laden()
        elif seite is self.profil:
            self.profil.neu_laden()
        elif seite is self.archiv:
            self.archiv.neu_laden()
        else:
            self.uebersicht.neu_laden()

    def _nav(self, schl):
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == schl:
                self.nav.blockSignals(True)
                self.nav.setCurrentRow(i)
                self.nav.blockSignals(False)

    def zeigen(self, seite):
        """uebersicht | archiv | tabelle | profil"""
        w = {"uebersicht": self.uebersicht, "archiv": self.archiv, "tabelle": self.tabelle,
             "profil": self.profil}[seite]
        self.stapel.setCurrentWidget(w)
        if seite != "profil":
            self._nav(seite)
        if self.f is not None and self.f.reiter.currentWidget() is not self:
            self.f.reiter.setCurrentWidget(self)
        w.neu_laden()
        return w

    def gewaehlt(self):
        if self.stapel.currentWidget() is self.profil and self.profil.kundennr:
            return self.profil.kundennr
        if self.stapel.currentWidget() is self.archiv:
            return self.archiv.gewaehlt()
        return self.uebersicht.gewaehlt() or self.profil.kundennr

    def aktion(self, schl):
        """Menüpunkt bzw. Unterbereich ausführen."""
        if schl in ("uebersicht", "archiv", "tabelle"):
            return self.zeigen(schl)
        if schl == "neu":
            self._nav("uebersicht")
            return self.neuer_kunde()
        nr = self.gewaehlt()
        if not nr:
            nr = self.kunde_waehlen()
            if not nr:
                self._nav("uebersicht")
                return None
        if schl == "bearbeiten":
            self.oeffnen(nr, REITER_ZU["bearbeiten"])
            return self.kunde_bearbeiten(nr)
        return self.oeffnen(nr, REITER_ZU.get(schl, 0))

    def kunde_waehlen(self, suche=""):
        if self.stumm:
            return None
        d = KundenSuche(self, self.db, suche, neu=lambda s: self.neuer_kunde(vorschlag={"name": s}))
        return d.kundennr if d.exec() == QDialog.Accepted else None

    def oeffnen(self, kundennr, reiter=0):
        self.stapel.setCurrentWidget(self.profil)
        if self.f is not None and self.f.reiter.currentWidget() is not self:
            self.f.reiter.setCurrentWidget(self)
        if not self.profil.zeigen(kundennr, reiter):
            return None
        self._nav({v: k for k, v in REITER_ZU.items()}.get(reiter, "uebersicht"))
        return self.profil

    def kunde_suchen(self, text):
        """Kunde aus Angebot/Befehlspalette: Übersicht mit Suchtext, bei genau einem Treffer gleich das Profil.
        Ergebnis: Anzahl Treffer."""
        self.zeigen("uebersicht")
        self.uebersicht.suche.setText(str(text or ""))
        n = self.uebersicht.filter.rowCount()
        if n:
            self.uebersicht.ansicht.selectRow(0)
            self.uebersicht.ansicht.setCurrentIndex(self.uebersicht.filter.index(0, 0))
        k = kd.kunde(self.db, text)
        if k is not None or n == 1:
            self.oeffnen(k["kundennr"] if k else self.uebersicht.gewaehlt())
        return n

    def geaendert(self, kundennr=None):
        """Nach einer Änderung: Profil, Übersicht und Tabellenansicht neu, Kollegen beim nächsten Abgleich."""
        if self.profil.kundennr and (kundennr is None or str(kundennr) == self.profil.kundennr):
            self.profil.neu_laden()
        self.uebersicht.neu_laden()
        try:
            self.tabelle.neu_laden()
        except Exception:
            pass
        if self.f is not None and hasattr(self.f, "puls"):
            try:
                self.f.puls()
            except Exception:
                pass

    # ---------------------------------------------------------- Vorgänge
    def neuer_kunde(self, vorschlag=None, stumm=None, werte=None, dubletten_ok=None, oeffnen=True):
        """Eingabemaske „Neuen Kunden anlegen“. stumm (Tests): werte statt Eingabe, dubletten_ok statt Rückfrage.
        Ergebnis: Kundennummer oder None."""
        stumm = self.stumm if stumm is None else stumm
        d = KundenFormular(self, self.db, neu=True, vorschlag=dict(vorschlag or {}, **(werte or {})))
        d.oeffnen_kunde.connect(lambda nr: (d.reject(), self.oeffnen(nr)))
        if not stumm and d.exec() != QDialog.Accepted:
            return None
        w, vg, personen = d.werte(), d.vorgaben_werte(), d.personen_werte()
        dub = kd.dubletten(self.db, dict(w, ansprechpartner=personen))
        if dub and dubletten_ok is None and not stumm:
            k, gruende, _ = dub[0]
            box = QMessageBox(self)
            box.setWindowTitle("Mögliche Dublette")
            box.setIcon(QMessageBox.Warning)
            box.setText(f"Es gibt schon einen ähnlichen Kunden:\n\n{k['kundennr']} {k.get('name') or ''}\n"
                        f"({', '.join(gruende)})" + (f"\n\nund {len(dub) - 1} weitere" if len(dub) > 1 else "")
                        + "\n\nNichts wird automatisch zusammengeführt.")
            vorhanden = box.addButton("Vorhandenen öffnen", QMessageBox.AcceptRole)
            trotzdem = box.addButton("Trotzdem neu anlegen", QMessageBox.DestructiveRole)
            box.addButton("Abbrechen", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is vorhanden:
                self.oeffnen(k["kundennr"])
                return None
            if box.clickedButton() is not trotzdem:
                return None
            dubletten_ok = True
        try:
            nr = kd.anlegen(self.db, w, personen, (), vg, dubletten_ok=bool(dubletten_ok) or not dub)
        except Exception as e:
            fehler_zeigen(self, "Kunde anlegen", e, stumm)
            self.meldung(f"Kunde nicht angelegt: {e}", fehler=True)
            return None
        self.meldung(f"Kunde {nr} {w.get('name') or ''} angelegt.")
        self.geaendert(nr)
        if oeffnen:
            self.oeffnen(nr)
        return nr

    def kunde_bearbeiten(self, kundennr, stumm=None, werte=None, vorgaben=None):
        """Eingabemaske „Kunden bearbeiten“; stumm: werte/vorgaben statt Eingabe. Ergebnis: geänderte Feldtitel."""
        stumm = self.stumm if stumm is None else stumm
        k = kd.kunde(self.db, kundennr)
        if k is None:
            self.meldung(f"Kunde {kundennr} gibt es nicht.", fehler=True)
            return None
        vg = kd.vorgaben(self.db, kundennr)
        d = KundenFormular(self, self.db, k, vg, neu=False)
        d.oeffnen_kunde.connect(lambda nr: (d.reject(), self.oeffnen(nr)))
        for n, w in (werte or {}).items():
            if n in d.e:
                e = d.e[n]
                (e.setCurrentText if isinstance(e, QComboBox) else e.setPlainText if isinstance(e, QPlainTextEdit)
                 else e.setText)("" if w is None else str(w))
        for n, w in (vorgaben or {}).items():
            d.e[n].setText("" if w is None else str(w))
        if not stumm and d.exec() != QDialog.Accepted:
            return None
        alt = {n: k.get(n) for n in d.werte()}
        try:
            g = kd.speichern(self.db, kundennr, d.werte(), alt, d.vorgaben_werte(),
                             {n: vg.get(n) for n in kd.VORGABE_FELDER})
        except Exception as e:
            fehler_zeigen(self, "Kunde speichern", e, stumm)
            self.meldung(f"Nicht gespeichert: {e}", fehler=True)
            return None
        self.meldung(f"Kunde {kundennr}: {', '.join(g)} gespeichert." if g else "Keine Änderung.")
        self.geaendert(kundennr)
        return g

    def kunde_duplizieren(self, kundennr, neue_nr=None):
        """Kopie mit neuer Kundennummer (immer von Hand, Patrick 23.11.2026); stumm: neue_nr."""
        if neue_nr is None:
            if self.stumm:
                return None
            neue_nr, gut = QInputDialog.getText(self, "Kunde duplizieren", f"Kundennummer für die Kopie von "
                                                f"{kundennr}:\n({kd.nummer_hinweis(self.db)})")
            if not gut or not neue_nr.strip():
                return None
        try:
            nr = kd.duplizieren(self.db, kundennr, neue_nr.strip())
        except Exception as e:
            fehler_zeigen(self, "Kunde duplizieren", e, self.stumm)
            return None
        self.meldung(f"Kunde {kundennr} als {nr} kopiert.")
        self.geaendert(nr)
        self.oeffnen(nr)
        return nr

    def kunde_archivieren(self, kundennr, an=True, bestaetigt=None):
        if an and bestaetigt is None and not self.stumm:
            k = kd.kunde(self.db, kundennr) or {}
            bestaetigt = QMessageBox.question(self, "Kunde archivieren",
                                              f"{kundennr} {k.get('name') or ''} ins Archiv?\n\nDaten, Angebote und "
                                              "Aufträge bleiben; der Kunde erscheint nur nicht mehr in der Übersicht "
                                              "und der Kundenauswahl im Angebot.") == QMessageBox.Yes
        if an and bestaetigt is False:
            return False
        try:
            kd.archivieren(self.db, kundennr, an)
        except Exception as e:
            fehler_zeigen(self, "Archivieren", e, self.stumm)
            return False
        self.meldung(f"Kunde {kundennr} {'archiviert' if an else 'aus dem Archiv geholt'}.")
        self.archiv.neu_laden()
        self.geaendert(kundennr)
        return True

    def neues_angebot(self, kundennr):
        """Neues Angebot für den Kunden (Kopf mit Kundendaten, Konditionen, Ansprechpartner, Lieferadresse)."""
        if self.f is None:
            return None
        k = kd.kunde(self.db, kundennr) or {}
        if k.get("status") == kd.GESPERRT and not self.stumm:
            if QMessageBox.question(self, "Kunde gesperrt", f"{kundennr} ist gesperrt. Trotzdem ein Angebot "
                                                            "anlegen?") != QMessageBox.Yes:
                return None
        i = self.db.angebot_neu(dict(kundennr=kundennr))
        kd.angebot_kunde_setzen(self.db, i, kundennr)
        self.f.angebote.neu_laden()
        self.f.angebot_oeffnen(i)
        return i


def menue_einrichten(f, menue):
    """Hauptmenü KUNDEN mit den Unterbereichen."""
    f.kunden_aktionen = {}
    for schl, text, sym in BEREICHE:
        if schl == "tabelle":
            menue.addSeparator()
        a = menue.addAction(_symbol(sym), text + (" …" if schl == "neu" else ""))
        a.triggered.connect(lambda _=False, s=schl: f.kunden.aktion(s))
        f.kunden_aktionen[schl] = a
    return menue
