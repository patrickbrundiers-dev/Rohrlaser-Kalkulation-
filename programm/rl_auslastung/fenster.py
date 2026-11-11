"""Fenster des Programms Rohrlaser Auslastung: Reiter Aufträge, Auslastung, Soll und Ist, Einstellungen."""
import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QMarginsF, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)
from rohrlaser import einlastung, feiertage, stil
from rohrlaser.auslastung_grafik import RISIKO_TEXT, Plantafel, WochenBalken, spalten_daten

from . import NAME, VERSION, austausch, laufzeit, ort, rechnung
from . import daten as D

FILTER = ("offene Aufträge", "fertige Aufträge", "alle Aufträge")
ZEITRAUM = ("alle", "letzte 30 Tage", "letzte 90 Tage", "dieses Jahr", "letztes Jahr")
FORM_TEXT = {"hm": "1 h 30 min", "uhr": "1:30 h", "dez": "1,50 h (Dezimalstunden)", "min": "90 min (nur Minuten)"}
OHNE_TEXT = {"min": "Minuten (90 = 90 Minuten)", "h": "Stunden (2 = 2 Stunden)"}
RISIKO_FARBE = {einlastung.UEBER: stil.ROT_FLAECHE, einlastung.KNAPP: stil.GELB_FLAECHE}


def _tag(iso):
    try:
        return datetime.date.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return ""


def _zelle(text, rechts=False, daten=None, sortier=None):
    z = _Zelle("" if text is None else str(text))
    z.setFlags(z.flags() & ~Qt.ItemIsEditable)
    if rechts:
        z.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if daten is not None:
        z.setData(Qt.UserRole, daten)
    z.sortier = sortier
    return z


class _Zelle(QTableWidgetItem):
    """Zelle, die nach ihrem Wert sortiert (Laufzeit, Datum) statt nach dem angezeigten Text."""
    sortier = None

    def __lt__(self, other):
        a, b = self.sortier, getattr(other, "sortier", None)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)


class LaufzeitFeld(QWidget):
    """Eingabe einer Laufzeit in freier Schreibweise mit Rückmeldung, wie sie verstanden wurde."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.eingabe = QLineEdit()
        self.eingabe.setPlaceholderText(laufzeit.BEISPIELE)
        self.eingabe.setToolTip("Schreibweisen: 1 Stunde 30 Minuten, 1 Std 30 Min, 1 h 30 min, 1h30, 1:30, 90 Minuten, "
                                "90 min, 1,5 h.\nEine ganze Zahl ohne Einheit gilt als "
                                + ("Stunden" if db.einstellung("ohne_einheit") == "h" else "Minuten")
                                + ", eine Kommazahl als Stunden (Einstellungen).")
        self.echo = QLabel("")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self.eingabe)
        lay.addWidget(self.echo)
        self.eingabe.textChanged.connect(self.pruefen)

    def setzen(self, minuten):
        self.eingabe.setText(laufzeit.text(minuten, self.db.einstellung("laufzeit_form")) if minuten else "")

    def minuten(self):
        """Ganze Minuten oder None (leer); laufzeit.Fehler bei unlesbarer Eingabe."""
        return laufzeit.lesen(self.eingabe.text(), self.db.einstellung("ohne_einheit"))

    def pruefen(self, *_):
        try:
            n = self.minuten()
        except laufzeit.Fehler as e:
            self.echo.setText(str(e))
            self.echo.setStyleSheet(f"color: {stil.umsetzen(stil.ROT)};")
            self.echo.setWordWrap(True)
            return False
        self.echo.setText("= " + laufzeit.lang(n) if n is not None else "")
        self.echo.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        return True


class AuftragDialog(QDialog):
    """Auftrag anlegen oder ändern."""

    def __init__(self, db, auftrag=None, parent=None):
        super().__init__(parent)
        self.db, self.auftrag = db, dict(auftrag or {})
        self.setWindowTitle("Auftrag ändern" if self.auftrag.get("id") else "Neuer Auftrag")
        self.nummer = QLineEdit(self.auftrag.get("nummer") or "")
        self.kunde = QLineEdit(self.auftrag.get("kunde") or "")
        self.maschine = QComboBox()
        namen = [m["name"] for m in db.maschinen(nur_aktive=True)]
        if self.auftrag.get("maschine") and self.auftrag["maschine"] not in namen:
            namen.append(self.auftrag["maschine"])
        self.maschine.addItems(namen)
        if self.auftrag.get("maschine"):
            self.maschine.setCurrentText(self.auftrag["maschine"])
        self.kalk = LaufzeitFeld(db)
        self.kalk.setzen(self.auftrag.get("kalk_min"))
        self.mit_termin = QCheckBox("Liefertermin")
        self.termin = QDateEdit()
        self.termin.setCalendarPopup(True)
        self.termin.setDisplayFormat("dd.MM.yyyy")
        try:
            t = datetime.date.fromisoformat(self.auftrag.get("liefertermin") or "")
            self.termin.setDate(QDate(t.year, t.month, t.day))
            self.mit_termin.setChecked(True)
        except ValueError:
            self.termin.setDate(QDate.currentDate().addDays(14))
            self.mit_termin.setChecked(not self.auftrag.get("id"))
        self.mit_termin.toggled.connect(self.termin.setEnabled)
        self.termin.setEnabled(self.mit_termin.isChecked())
        zeile = QHBoxLayout()
        zeile.addWidget(self.mit_termin)
        zeile.addWidget(self.termin, 1)
        self.bemerkung = QLineEdit(self.auftrag.get("bemerkung") or "")
        self.zusatz = {}
        form = QFormLayout()
        form.addRow("Auftragsnummer", self.nummer)
        form.addRow("Kunde", self.kunde)
        form.addRow("Maschine", self.maschine)
        form.addRow("Kalkulierte Laufzeit", self.kalk)
        form.addRow("", zeile)
        form.addRow("Bemerkung", self.bemerkung)
        for f in db.zusatzfelder():
            self.zusatz[f["name"]] = QLineEdit((self.auftrag.get("zusatz") or {}).get(f["name"], ""))
            form.addRow(f["name"], self.zusatz[f["name"]])
        self.fehler = QLabel("")
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(f"color: {stil.umsetzen(stil.ROT)};")
        knoepfe = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Save).setText("Speichern")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.speichern)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.fehler)
        lay.addWidget(knoepfe)
        self.setMinimumWidth(460)

    def werte(self):
        d = self.termin.date()
        return dict(id=self.auftrag.get("id"), nummer=self.nummer.text(), kunde=self.kunde.text(),
                    maschine=self.maschine.currentText(), kalk_min=self.kalk.minuten() or 0,
                    liefertermin=datetime.date(d.year(), d.month(), d.day()) if self.mit_termin.isChecked() else None,
                    bemerkung=self.bemerkung.text(), zusatz={n: e.text() for n, e in self.zusatz.items()})

    def speichern(self):
        try:
            self.auftrag["id"] = self.db.auftrag_speichern(self.werte())
        except (D.Fehler, laufzeit.Fehler) as e:
            self.fehler.setText(str(e))
            return False
        self.accept()
        return True


class FertigDialog(QDialog):
    """Fertigmeldung: tatsächliche Laufzeit und Fertig-Datum."""

    def __init__(self, db, auftrag, parent=None, jetzt=None):
        super().__init__(parent)
        self.db, self.auftrag = db, auftrag
        self.setWindowTitle(f"Auftrag {auftrag['nummer']} fertig melden")
        form_ = db.einstellung("laufzeit_form")
        self.ist = LaufzeitFeld(db)
        gelaufen = db.gelaufen(auftrag, jetzt)
        self.ist.setzen(auftrag.get("ist_min") or gelaufen or None)
        self.am = QDateEdit(QDate.currentDate())
        self.am.setCalendarPopup(True)
        self.am.setDisplayFormat("dd.MM.yyyy")
        form = QFormLayout()
        form.addRow("Kalkulierte Laufzeit", QLabel(laufzeit.text(auftrag["kalk_min"], form_)))
        if gelaufen:
            form.addRow("Gestoppt mit Start/Stopp", QLabel(laufzeit.text(gelaufen, form_)))
        form.addRow("Tatsächliche Laufzeit", self.ist)
        form.addRow("Fertig am", self.am)
        self.fehler = QLabel("")
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(f"color: {stil.umsetzen(stil.ROT)};")
        knoepfe = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Save).setText("Fertig melden")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.speichern)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.fehler)
        lay.addWidget(knoepfe)
        self.setMinimumWidth(420)

    def speichern(self):
        try:
            d = self.am.date()
            self.db.fertig_melden(self.auftrag["id"], self.ist.minuten() or 0, datetime.date(d.year(), d.month(), d.day()))
        except (D.Fehler, laufzeit.Fehler) as e:
            self.fehler.setText(str(e))
            return False
        self.accept()
        return True


class Hauptfenster(QMainWindow):
    def __init__(self, db, heute=None):
        super().__init__()
        self.db, self.heute_fest = db, heute
        self.aus = self.ein = self.gem = None
        self.woche = None                         # im Wochenbalken gewählte (Maschine, Montag)
        self.setWindowTitle(f"{NAME} {VERSION}")
        self.resize(1320, 820)
        self.reiter = QTabWidget()
        self.setCentralWidget(self.reiter)
        self.reiter.addTab(self._seite_auftraege(), "Aufträge")
        self.reiter.addTab(self._seite_auslastung(), "Auslastung")
        self.reiter.addTab(self._seite_soll_ist(), "Soll und Ist")
        self.reiter.addTab(self._seite_einstellungen(), "Einstellungen")
        self.reiter.currentChanged.connect(lambda _i: self.laden())
        self.statusBar().showMessage(f"Datenbank: {db.pfad}")
        self.stand = db.stand()
        self.uhr = QTimer(self)                   # anderer Platz hat gespeichert, oder eine Start/Stopp-Uhr läuft
        self.uhr.timeout.connect(self.takt)
        self.uhr.start(5000)
        self.laden()

    def heute(self):
        return self.heute_fest or datetime.date.today()

    def form(self):
        return self.db.einstellung("laufzeit_form")

    def lz(self, minuten):
        return laufzeit.text(minuten, self.form())

    def meldung(self, text):
        QMessageBox.warning(self, NAME, text)

    def takt(self):
        neu = self.db.stand()
        if neu != self.stand or any(a["start_am"] for a in self.db.auftraege(D.LAEUFT)):
            self.stand = neu
            if not QApplicationModal():
                self.laden()

    # ------------------------------------------------------------------ Aufträge
    def _seite_auftraege(self):
        w = QWidget()
        self.filter = QComboBox()
        self.filter.addItems(FILTER)
        self.filter.currentIndexChanged.connect(lambda _i: self.auftraege_zeigen())
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Auftragsnummer, Kunde, Maschine, Bemerkung")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(lambda _t: self.auftraege_zeigen())
        self.k_neu = QPushButton("Neuer Auftrag …")
        self.k_neu.setObjectName("primaer")
        self.k_aendern = QPushButton("Ändern …")
        self.k_start = QPushButton("Start")
        self.k_stopp = QPushButton("Stopp")
        self.k_fertig = QPushButton("Fertig melden …")
        self.k_oeffnen = QPushButton("Wieder öffnen")
        self.k_loeschen = QPushButton("Löschen")
        self.k_csv_ein = QPushButton("CSV einlesen …")
        self.k_csv_aus = QPushButton("CSV speichern …")
        self.k_start.setToolTip("Startet die Uhr für den gewählten Auftrag. Stopp hält sie an; die gestoppte Zeit wird "
                                "bei der Fertigmeldung als tatsächliche Laufzeit vorgeschlagen.")
        self.k_csv_ein.setToolTip("Aufträge aus einer CSV-Datei übernehmen, auch die Übergabedatei aus der Kalkulation. "
                                  "Vorhandene Auftragsnummern werden aktualisiert, fertige bleiben unverändert.")
        for k, f in ((self.k_neu, self.neu), (self.k_aendern, self.aendern), (self.k_start, self.starten),
                     (self.k_stopp, self.stoppen), (self.k_fertig, self.fertig_melden),
                     (self.k_oeffnen, self.wieder_oeffnen), (self.k_loeschen, self.loeschen),
                     (self.k_csv_ein, self.csv_einlesen), (self.k_csv_aus, self.csv_speichern)):
            k.clicked.connect(lambda _=False, f=f: f())
        oben = QHBoxLayout()
        oben.addWidget(self.filter)
        oben.addWidget(self.suche, 1)
        knoepfe = QHBoxLayout()
        for k in (self.k_neu, self.k_aendern, self.k_start, self.k_stopp, self.k_fertig, self.k_oeffnen, self.k_loeschen):
            knoepfe.addWidget(k)
        knoepfe.addStretch(1)
        knoepfe.addWidget(self.k_csv_ein)
        knoepfe.addWidget(self.k_csv_aus)
        self.liste = QTableWidget()
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste.setAlternatingRowColors(True)
        self.liste.verticalHeader().setVisible(False)
        self.liste.setSortingEnabled(True)
        self.liste.itemSelectionChanged.connect(self.knoepfe_setzen)
        self.liste.itemDoubleClicked.connect(lambda _i: self.aendern())
        self.summe = QLabel("")
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addLayout(knoepfe)
        lay.addWidget(self.liste, 1)
        lay.addWidget(self.summe)
        return w

    def gewaehlt(self):
        """Der in der Liste gewählte Auftrag (frisch aus der Datenbank) oder None."""
        r = self.liste.currentRow()
        z = self.liste.item(r, 0) if r >= 0 else None
        return self.db.auftrag(z.data(Qt.UserRole)) if z is not None else None

    def waehlen(self, auftrag_id):
        for r in range(self.liste.rowCount()):
            if self.liste.item(r, 0).data(Qt.UserRole) == auftrag_id:
                self.liste.selectRow(r)
                return True
        return False

    def auftraege_zeigen(self):
        alt = self.gewaehlt()
        status = {0: (D.OFFEN, D.LAEUFT), 1: (D.FERTIG,), 2: None}[self.filter.currentIndex()]
        such = self.suche.text().strip().lower()
        plan = {a["id"]: a for a in (self.ein or {}).get("auftraege", ())}
        felder = [f["name"] for f in self.db.zusatzfelder()]
        kopf = ["Auftragsnummer", "Kunde", "Maschine", "Kalkulierte Laufzeit", "Liefertermin", "Status",
                "Laser fertig (Plan)", "Terminrisiko", "Tatsächliche Laufzeit", "Abweichung", "Fertig am",
                "Bemerkung"] + felder
        self.liste.setSortingEnabled(False)
        self.liste.setColumnCount(len(kopf))
        self.liste.setHorizontalHeaderLabels(kopf)
        zeilen = []
        for a in self.db.auftraege(status):
            if such and such not in " ".join([a["nummer"], a["kunde"], a["maschine"], a["bemerkung"]]
                                             + list(a["zusatz"].values())).lower():
                continue
            zeilen.append(a)
        self.liste.setRowCount(len(zeilen))
        offen_min = 0
        for r, a in enumerate(zeilen):
            p = plan.get(a["id"], {})
            diff, prozent = rechnung.abweichung(a["kalk_min"], a["ist_min"])
            status_text = a["status"]
            if a["status"] != D.FERTIG:
                gelaufen = self.db.gelaufen(a)
                offen_min += max(0, a["kalk_min"] - gelaufen)
                if gelaufen:
                    status_text += f" ({self.lz(gelaufen)}" + (", Uhr läuft)" if a["start_am"] else ")")
            abw = "" if diff is None else f"{'+' if diff > 0 else ''}{self.lz(diff)}" + (
                f" ({prozent:+.0f} %)".replace(".", ",") if prozent is not None else "")
            risiko = RISIKO_TEXT.get(p.get("risiko"), "") if a["status"] != D.FERTIG else ""
            werte = [
                _zelle(a["nummer"], daten=a["id"]), _zelle(a["kunde"]), _zelle(a["maschine"]),
                _zelle(self.lz(a["kalk_min"]), True, sortier=a["kalk_min"]),
                _zelle(_tag(a["liefertermin"]), sortier=a["liefertermin"] or "9999"), _zelle(status_text),
                _zelle(_tag(p.get("fertig")), sortier=str(p.get("fertig") or "9999")), _zelle(risiko),
                _zelle(self.lz(a["ist_min"]), True, sortier=a["ist_min"] or 0),
                _zelle(abw, True, sortier=diff if diff is not None else 0),
                _zelle(_tag(a["fertig_am"]), sortier=a["fertig_am"] or ""), _zelle(a["bemerkung"]),
            ] + [_zelle(a["zusatz"].get(n, "")) for n in felder]
            for c, z in enumerate(werte):
                self.liste.setItem(r, c, z)
            farbe = RISIKO_FARBE.get(p.get("risiko")) if a["status"] != D.FERTIG else None
            if farbe:
                werte[7].setBackground(stil.farbe(farbe))
                werte[7].setForeground(stil.farbe(stil.TEXT))
        for c in (6, 7):                          # Plan nur bei offenen, Ist nur bei fertigen Aufträgen
            self.liste.setColumnHidden(c, self.filter.currentIndex() == 1)
        for c in (8, 9, 10):
            self.liste.setColumnHidden(c, self.filter.currentIndex() == 0)
        self.liste.setSortingEnabled(True)
        self.liste.resizeColumnsToContents()
        self.liste.horizontalHeader().setSectionResizeMode(11, QHeaderView.Stretch)
        self.summe.setText(f"{len(zeilen)} Aufträge" + (f", noch {self.lz(offen_min)} offene Laufzeit"
                                                        if offen_min else ""))
        if alt is None or not self.waehlen(alt["id"]):
            self.liste.clearSelection()
            self.liste.setCurrentCell(-1, -1)
        self.knoepfe_setzen()

    def knoepfe_setzen(self):
        a = self.gewaehlt()
        offen = a is not None and a["status"] != D.FERTIG
        self.k_aendern.setEnabled(a is not None)
        self.k_start.setEnabled(offen and not a["start_am"])
        self.k_stopp.setEnabled(offen and bool(a["start_am"]))
        self.k_fertig.setEnabled(offen)
        self.k_oeffnen.setEnabled(a is not None and a["status"] == D.FERTIG)
        self.k_loeschen.setEnabled(a is not None)

    def neu(self, zeigen=True):
        d = AuftragDialog(self.db, parent=self)
        if zeigen and d.exec() == QDialog.Accepted:
            self.laden()
            self.waehlen(d.auftrag["id"])
        return d

    def aendern(self, auftrag_id=None, zeigen=True):
        a = self.db.auftrag(auftrag_id) if auftrag_id is not None else self.gewaehlt()
        if a is None:
            return None
        d = AuftragDialog(self.db, a, self)
        if zeigen and d.exec() == QDialog.Accepted:
            self.laden()
        return d

    def starten(self):
        a = self.gewaehlt()
        if a:
            try:
                self.db.starten(a["id"])
            except D.Fehler as e:
                self.meldung(str(e))
            self.laden()

    def stoppen(self):
        a = self.gewaehlt()
        if a:
            self.db.stoppen(a["id"])
            self.laden()

    def fertig_melden(self, zeigen=True):
        a = self.gewaehlt()
        if a is None or a["status"] == D.FERTIG:
            return None
        if a["start_am"]:
            self.db.stoppen(a["id"])
            a = self.db.auftrag(a["id"])
        d = FertigDialog(self.db, a, self)
        if zeigen and d.exec() == QDialog.Accepted:
            self.laden()
        return d

    def wieder_oeffnen(self):
        a = self.gewaehlt()
        if a:
            self.db.wieder_oeffnen(a["id"])
            self.laden()

    def loeschen(self, fragen=True):
        a = self.gewaehlt()
        if a is None:
            return
        if fragen and QMessageBox.question(
                self, NAME, f"Auftrag {a['nummer']} wirklich löschen? Das lässt sich nicht rückgängig machen.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.db.auftrag_loeschen(a["id"])
        self.laden()

    def csv_einlesen(self, pfad=None, fragen=True):
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "Aufträge aus CSV einlesen", "", "CSV (*.csv *.txt);;Alle (*)")
            if not pfad:
                return None
        try:
            ergebnis = austausch.lesen(self.db, pfad)
        except OSError as e:
            self.meldung(f"Die Datei lässt sich nicht lesen: {e}")
            return None
        text = austausch.zusammenfassung(ergebnis)
        if not ergebnis["neu"] and not ergebnis["geaendert"]:
            if fragen:
                QMessageBox.information(self, NAME, "Nichts zu übernehmen.\n\n" + text)
            return ergebnis
        if fragen and QMessageBox.question(self, NAME, text + "\n\nJetzt übernehmen?", QMessageBox.Yes | QMessageBox.No,
                                           QMessageBox.Yes) != QMessageBox.Yes:
            return None
        self.db.sichern("vor-CSV")
        austausch.uebernehmen(self.db, ergebnis)
        self.laden()
        return ergebnis

    def csv_speichern(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Auftragsliste als CSV", "Auftraege.csv", "CSV (*.csv)")
            if not pfad:
                return None
        ids = [self.liste.item(r, 0).data(Qt.UserRole) for r in range(self.liste.rowCount())]
        return austausch.schreiben(self.db, pfad, [self.db.auftrag(i) for i in ids])

    # ------------------------------------------------------------------ Auslastung
    def _seite_auslastung(self):
        w = QWidget()
        self.wochen = QSpinBox()
        self.wochen.setRange(2, 26)
        self.wochen.setValue(int(self.db.zahl("wochen", 8)))
        self.wochen.setSuffix(" Wochen")
        self.wochen.valueChanged.connect(self._wochen_geaendert)
        self.k_pdf = QPushButton("PDF …")
        self.k_pdf.clicked.connect(lambda _=False: self.pdf())
        self.k_risiko = QPushButton("Terminrisiko zeigen")
        self.k_risiko.clicked.connect(lambda _=False: self.woche_waehlen(None, None))
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.balken = WochenBalken()
        self.balken.gewaehlt.connect(self.woche_waehlen)
        self.tafel = Plantafel()
        self.tafel.gewaehlt.connect(self.tafel_gewaehlt)
        self.tafel.oeffnen.connect(lambda i: self.aendern(i))
        legende = QLabel("Wochenbalken: Rahmen = Kapazität, gefüllt = eingelastete Aufträge (ab 80 % gelb, über 100 % "
                         "rot), grau links = tatsächliche Stunden aus den Fertigmeldungen. Plantafel: Dreieck = "
                         "Liefertermin, roter Rahmen = Termin nicht zu halten, oranger Rahmen = knapp, Doppelklick "
                         "öffnet den Auftrag.")
        legende.setWordWrap(True)
        legende.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.balken)
        ll.addWidget(legende)
        ll.addWidget(self.tafel)
        ll.addStretch(1)
        rollen = QScrollArea()
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QFrame.NoFrame)
        rollen.setWidget(links)
        self.details_titel = QLabel("")
        self.details_titel.setWordWrap(True)
        self.details = QTableWidget()
        self.details.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.details.setSelectionMode(QAbstractItemView.SingleSelection)
        self.details.verticalHeader().setVisible(False)
        self.details.itemDoubleClicked.connect(
            lambda z: self.aendern(self.details.item(z.row(), 0).data(Qt.UserRole)))
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        kopf = QHBoxLayout()
        kopf.addWidget(self.details_titel, 1)
        kopf.addWidget(self.k_risiko)
        rl.addLayout(kopf)
        rl.addWidget(self.details, 1)
        teiler = QSplitter(Qt.Horizontal)
        teiler.addWidget(rollen)
        teiler.addWidget(rechts)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 2)
        teiler.setSizes([800, 560])
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Zeitraum"))
        oben.addWidget(self.wochen)
        oben.addStretch(1)
        oben.addWidget(self.k_pdf)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addWidget(self.info)
        lay.addWidget(teiler, 1)
        return w

    def _wochen_geaendert(self, n):
        self.db.einstellung_setzen("wochen", n)
        self.stand = self.db.stand()
        self.laden()

    def woche_waehlen(self, maschine, key):
        self.woche = (maschine, key) if maschine is not None and isinstance(key, datetime.date) else None
        if self.woche is None:
            self.balken.auswahl = None
            self.balken.update()
        self.details_zeigen()

    def tafel_gewaehlt(self, auftrag_id):
        for r in range(self.details.rowCount()):
            if self.details.item(r, 0).data(Qt.UserRole) == auftrag_id:
                self.details.selectRow(r)
                return

    def auftraege_der_auswahl(self):
        """(Titel, Aufträge) für die Tabelle rechts: gewählte Woche oder die Aufträge mit Terminrisiko."""
        if self.woche:
            m, mo = self.woche
            ende = mo + datetime.timedelta(days=6)
            liste = [a for a in self.ein["auftraege"] if a["maschine"] == m
                     and any(mo <= tag <= ende for tag, _v, _b in a["stuecke"])]
            return f"{m}, KW {mo.isocalendar()[1]}: {len(liste)} Aufträge auf dem Laser", liste
        liste = einlastung.kritische(self.ein)
        return (f"Terminrisiko: {len(liste)} Aufträge knapp oder nicht zu halten" if liste
                else "Kein Auftrag mit Terminrisiko"), liste

    def details_zeigen(self):
        if self.ein is None:
            return
        titel, liste = self.auftraege_der_auswahl()
        self.details_titel.setText(titel)
        kopf = ("Auftragsnummer", "Kunde", "Maschine", "Liefertermin", "Restlaufzeit", "Laser fertig", "Puffer [AT]",
                "Terminrisiko")
        self.details.setColumnCount(len(kopf))
        self.details.setHorizontalHeaderLabels(kopf)
        self.details.setRowCount(len(liste))
        for r, a in enumerate(liste):
            werte = [_zelle(a["nummer"], daten=a["id"]), _zelle(a["kunde"]), _zelle(a["maschine"]),
                     _zelle(_tag(a.get("termin"))), _zelle(self.lz(int(a["h"] * 60 + 0.5)), True),
                     _zelle(_tag(a.get("fertig")) or "später"), _zelle(a["puffer"], True),
                     _zelle(RISIKO_TEXT.get(a["risiko"], ""))]
            for c, z in enumerate(werte):
                self.details.setItem(r, c, z)
            if a["risiko"] in RISIKO_FARBE:
                werte[7].setBackground(stil.farbe(RISIKO_FARBE[a["risiko"]]))
                werte[7].setForeground(stil.farbe(stil.TEXT))
        self.details.resizeColumnsToContents()
        self.details.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    def auslastung_zeigen(self):
        self.balken.setzen(spalten_daten(self.aus, self.ein, self.gem, True), self.woche)
        self.tafel.setzen(self.aus, self.ein, self.wochen.value())
        r = self.ein["risiko"]
        text = ("Die offenen Aufträge laufen ab heute nacheinander, sortiert nach Liefertermin, durch die freien "
                "Stunden jeder Maschine. Was nicht in eine Woche passt, rutscht in die nächste.")
        if r[einlastung.UEBER] or r[einlastung.KNAPP]:
            text += (f" <b style='color:{stil.umsetzen(stil.ROT)}'>Terminrisiko: {r[einlastung.UEBER]} nicht zu "
                     f"halten, {r[einlastung.KNAPP]} knapp.</b>")
        self.info.setText(text)
        self.details_zeigen()

    def pdf(self, pfad=None):
        """Auslastung als PDF (A4 quer): Wochenbalken, Plantafel und die Aufträge mit Terminrisiko."""
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Auslastung als PDF", "Maschinenauslastung.pdf", "PDF (*.pdf)")
            if not pfad:
                return None
        w, seite, p = _pdf_beginnen(pfad, "Maschinenauslastung")
        with stil.druckfarben():
            f = self.font()
            y = _pdf_titel(p, f, seite, f"Maschinenauslastung, Stand {self.heute().strftime('%d.%m.%Y')}")
            for widget in (self.balken, self.tafel):
                alt, fest = widget.size(), widget.minimumWidth()
                widget.setMinimumWidth(0)
                widget.resize(seite.width(), widget.sizeHint().height())
                widget.render(p, QPointF(0, y).toPoint())
                y += widget.height() + 14
                widget.setMinimumWidth(fest)
                widget.resize(alt)
            liste = einlastung.kritische(self.ein)
            zeilen = [[a["nummer"], a["kunde"], a["maschine"], _tag(a.get("termin")), _tag(a.get("fertig")) or "später",
                       "" if a["puffer"] is None else str(a["puffer"]), RISIKO_TEXT.get(a["risiko"], "")] for a in liste]
            p.drawText(QRectF(0, y, seite.width(), 16), Qt.AlignLeft | Qt.AlignVCenter,
                       f"Aufträge mit Terminrisiko: {len(liste)}")
            _pdf_tabelle(p, f, seite, y + 18, ("Auftragsnummer", "Kunde", "Maschine", "Liefertermin", "Laser fertig",
                                               "Puffer [AT]", "Terminrisiko"), zeilen, (110, 250, 80, 90, 90, 80, 120))
            p.end()
        del w
        return pfad

    # ------------------------------------------------------------------ Soll und Ist
    def _seite_soll_ist(self):
        w = QWidget()
        self.zeitraum = QComboBox()
        self.zeitraum.addItems(ZEITRAUM)
        self.zeitraum.currentIndexChanged.connect(lambda _i: self.soll_ist_zeigen())
        self.k_si_csv = QPushButton("Liste als CSV …")
        self.k_si_pdf = QPushButton("Liste als PDF …")
        self.k_si_csv.clicked.connect(lambda _=False: self.soll_ist_csv())
        self.k_si_pdf.clicked.connect(lambda _=False: self.soll_ist_pdf())
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Fertig gemeldet"))
        oben.addWidget(self.zeitraum)
        oben.addStretch(1)
        oben.addWidget(self.k_si_csv)
        oben.addWidget(self.k_si_pdf)
        self.si_info = QLabel("")
        self.si_info.setWordWrap(True)
        self.si_maschinen = QTableWidget()
        self.si_liste = QTableWidget()
        for t in (self.si_maschinen, self.si_liste):
            t.verticalHeader().setVisible(False)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.setAlternatingRowColors(True)
        self.si_liste.setSortingEnabled(True)
        self.si_maschinen.setMaximumHeight(190)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addWidget(self.si_info)
        lay.addWidget(QLabel("<b>Je Maschine</b>"))
        lay.addWidget(self.si_maschinen)
        lay.addWidget(QLabel("<b>Je Auftrag</b>"))
        lay.addWidget(self.si_liste, 1)
        return w

    def zeitraum_grenzen(self):
        h, i = self.heute(), self.zeitraum.currentIndex()
        if i == 1:
            return h - datetime.timedelta(days=30), h
        if i == 2:
            return h - datetime.timedelta(days=90), h
        if i == 3:
            return datetime.date(h.year, 1, 1), h
        if i == 4:
            return datetime.date(h.year - 1, 1, 1), datetime.date(h.year - 1, 12, 31)
        return None, None

    def _abw(self, diff, prozent):
        if diff is None:
            return ""
        return f"{'+' if diff > 0 else ''}{self.lz(diff)}" + (
            f" ({prozent:+.0f} %)".replace(".", ",") if prozent is not None else "")

    def soll_ist_daten(self):
        """(Kopf und Zeilen je Maschine, Kopf und Zeilen je Auftrag) als Texte, für Anzeige, CSV und PDF."""
        si = rechnung.soll_ist(self.db, *self.zeitraum_grenzen())
        k1 = ("Maschine", "Aufträge", "Kalkuliert", "Tatsächlich", "Abweichung")
        z1 = [[s["maschine"], str(s["anzahl"]), self.lz(s["kalk_min"]), self.lz(s["ist_min"]),
               self._abw(s["diff_min"], s["diff_prozent"])] for s in si["maschinen"] + [si["gesamt"]]]
        k2 = ("Auftragsnummer", "Kunde", "Maschine", "Liefertermin", "Fertig am", "Kalkulierte Laufzeit",
              "Tatsächliche Laufzeit", "Abweichung")
        z2 = [[a["nummer"], a["kunde"], a["maschine"], _tag(a["liefertermin"]), _tag(a["fertig_am"]),
               self.lz(a["kalk_min"]), self.lz(a["ist_min"]), self._abw(a["diff_min"], a["diff_prozent"])]
              for a in si["zeilen"]]
        return si, (k1, z1), (k2, z2)

    def soll_ist_zeigen(self):
        si, (k1, z1), (k2, z2) = self.soll_ist_daten()
        g = si["gesamt"]
        if g["anzahl"]:
            p = g["diff_prozent"]
            self.si_info.setText(
                f"{g['anzahl']} fertige Aufträge: kalkuliert {self.lz(g['kalk_min'])}, tatsächlich "
                f"{self.lz(g['ist_min'])}. " + ("" if p is None else (
                    f"Die Aufträge liefen im Schnitt {abs(p):.0f} % {'länger' if p > 0 else 'kürzer'} als kalkuliert."
                    if abs(p) >= 0.5 else "Kalkulation und tatsächliche Laufzeit stimmen überein.")))
        else:
            self.si_info.setText("In diesem Zeitraum ist noch kein Auftrag fertig gemeldet. Die tatsächliche Laufzeit "
                                 "wird bei „Fertig melden“ im Reiter Aufträge eingetragen.")
        self.si_liste.setSortingEnabled(False)
        for tabelle, kopf, zeilen, rechts in ((self.si_maschinen, k1, z1, (1, 2, 3, 4)),
                                             (self.si_liste, k2, z2, (5, 6, 7))):
            tabelle.setColumnCount(len(kopf))
            tabelle.setHorizontalHeaderLabels(kopf)
            tabelle.setRowCount(len(zeilen))
            for r, z in enumerate(zeilen):
                for c, t in enumerate(z):
                    tabelle.setItem(r, c, _zelle(t, c in rechts))
            tabelle.resizeColumnsToContents()
        for r, a in enumerate(si["zeilen"]):           # sortieren nach Wert, Abweichung ab 10 % farbig
            for c, wert in ((3, a["liefertermin"] or ""), (4, a["fertig_am"] or ""), (5, a["kalk_min"]),
                            (6, a["ist_min"] or 0), (7, a["diff_min"] or 0)):
                self.si_liste.item(r, c).sortier = wert
            p = a["diff_prozent"]
            if p is not None and abs(p) >= 10:
                z = self.si_liste.item(r, 7)
                z.setBackground(stil.farbe(stil.GELB_FLAECHE if p > 0 else stil.GRUEN_FLAECHE))
                z.setForeground(stil.farbe(stil.TEXT))
        self.si_liste.setSortingEnabled(True)

    def soll_ist_csv(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Soll und Ist als CSV", "Soll-Ist.csv", "CSV (*.csv)")
            if not pfad:
                return None
        import csv
        _si, (k1, z1), (k2, z2) = self.soll_ist_daten()
        with open(pfad, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(k2)
            w.writerows(z2)
            w.writerow([])
            w.writerow(k1)
            w.writerows(z1)
        return pfad

    def soll_ist_pdf(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Soll und Ist als PDF", "Soll-Ist.pdf", "PDF (*.pdf)")
            if not pfad:
                return None
        _si, (k1, z1), (k2, z2) = self.soll_ist_daten()
        w, seite, p = _pdf_beginnen(pfad, "Soll und Ist")
        f = self.font()
        y = _pdf_titel(p, f, seite, f"Kalkulierte und tatsächliche Laufzeit, {self.zeitraum.currentText()}, Stand "
                                    f"{self.heute().strftime('%d.%m.%Y')}")
        y = _pdf_tabelle(p, f, seite, y, k1, z1, (140, 80, 130, 130, 200)) + 16
        _pdf_tabelle(p, f, seite, y, k2, z2, (120, 220, 80, 90, 90, 130, 130, 170), w)
        p.end()
        return pfad

    # ------------------------------------------------------------------ Einstellungen
    def _seite_einstellungen(self):
        w = QWidget()
        self.e_maschinen = QTableWidget()
        self.e_maschinen.setColumnCount(3)
        self.e_maschinen.setHorizontalHeaderLabels(("Maschine", "Stunden je Tag", "aktiv"))
        self.e_maschinen.verticalHeader().setVisible(False)
        self.e_maschinen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.e_maschinen.setMaximumHeight(200)
        self.k_m_neu = QPushButton("Maschine hinzufügen …")
        self.k_m_aendern = QPushButton("Maschine ändern …")
        self.k_m_weg = QPushButton("Maschine entfernen")
        self.k_m_neu.clicked.connect(lambda _=False: self.maschine_bearbeiten(neu=True))
        self.k_m_aendern.clicked.connect(lambda _=False: self.maschine_bearbeiten())
        self.k_m_weg.clicked.connect(lambda _=False: self.maschine_entfernen())
        g1 = QGroupBox("Maschinen")
        l1 = QVBoxLayout(g1)
        l1.addWidget(self.e_maschinen)
        z = QHBoxLayout()
        for k in (self.k_m_neu, self.k_m_aendern, self.k_m_weg):
            z.addWidget(k)
        z.addStretch(1)
        l1.addLayout(z)

        self.e_samstag = QDoubleSpinBox()
        self.e_samstag.setRange(0, 24)
        self.e_samstag.setDecimals(1)
        self.e_samstag.setSuffix(" h")
        self.e_nutzung = QSpinBox()
        self.e_nutzung.setRange(10, 100)
        self.e_nutzung.setSuffix(" %")
        self.e_nutzung.setToolTip("Anteil der Arbeitszeit, der wirklich für Aufträge nutzbar ist (Rüsten, Störungen).")
        self.e_vorlauf = QSpinBox()
        self.e_vorlauf.setRange(0, 30)
        self.e_vorlauf.setSuffix(" Arbeitstage")
        self.e_vorlauf.setToolTip("So viele Arbeitstage liegen zwischen „Laser fertig“ und dem Liefertermin "
                                  "(Nacharbeit, Verpacken, Versand).")
        self.e_schwelle = QSpinBox()
        self.e_schwelle.setRange(0, 20)
        self.e_schwelle.setSuffix(" Arbeitstage")
        self.e_land = QComboBox()
        self.e_land.addItems(feiertage.AUSWAHL)
        self.e_ruhe = QLineEdit()
        self.e_ruhe.setPlaceholderText("z. B. 24.12.2026-31.12.2026; 02.10.2026")
        g2 = QGroupBox("Arbeitszeit und Termine")
        f2 = QFormLayout(g2)
        f2.addRow("Samstag", self.e_samstag)
        f2.addRow("Nutzungsgrad", self.e_nutzung)
        f2.addRow("Feiertage", self.e_land)
        f2.addRow("Betriebsruhe", self.e_ruhe)
        f2.addRow("Vorlauf bis zum Liefertermin", self.e_vorlauf)
        f2.addRow("Termin „knapp“ unter", self.e_schwelle)

        self.e_form = QComboBox()
        for k, t in FORM_TEXT.items():
            self.e_form.addItem(t, k)
        self.e_ohne = QComboBox()
        for k, t in OHNE_TEXT.items():
            self.e_ohne.addItem(t, k)
        self.e_design = QComboBox()
        self.e_design.addItems(stil.THEMES)
        g3 = QGroupBox("Laufzeit und Ansicht")
        f3 = QFormLayout(g3)
        f3.addRow("Laufzeit anzeigen als", self.e_form)
        f3.addRow("Ganze Zahl ohne Einheit bedeutet", self.e_ohne)
        hinweis = QLabel("Bei der Eingabe gehen immer alle Schreibweisen: " + laufzeit.BEISPIELE.replace("z. B. ", "")
                         + ".")
        hinweis.setWordWrap(True)
        f3.addRow("", hinweis)
        f3.addRow("Design", self.e_design)

        self.e_felder = QTableWidget()
        self.e_felder.setColumnCount(1)
        self.e_felder.setHorizontalHeaderLabels(("Zusatzfeld",))
        self.e_felder.horizontalHeader().setStretchLastSection(True)
        self.e_felder.verticalHeader().setVisible(False)
        self.e_felder.setMaximumHeight(160)
        self.k_f_neu = QPushButton("Feld hinzufügen …")
        self.k_f_um = QPushButton("Feld umbenennen …")
        self.k_f_weg = QPushButton("Feld entfernen")
        self.k_f_neu.clicked.connect(lambda _=False: self.feld_bearbeiten(neu=True))
        self.k_f_um.clicked.connect(lambda _=False: self.feld_bearbeiten())
        self.k_f_weg.clicked.connect(lambda _=False: self.feld_entfernen())
        g4 = QGroupBox("Zusatzfelder je Auftrag (für eigene Angaben, z. B. Material, Stückzahl, Bearbeiter)")
        l4 = QVBoxLayout(g4)
        l4.addWidget(self.e_felder)
        z = QHBoxLayout()
        for k in (self.k_f_neu, self.k_f_um, self.k_f_weg):
            z.addWidget(k)
        z.addStretch(1)
        l4.addLayout(z)

        self.e_pfad = QLabel("")
        self.e_pfad.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.e_pfad.setWordWrap(True)
        self.k_db = QPushButton("Datenbank an anderem Ort …")
        self.k_db.setToolTip("Für mehrere Plätze: Datenbank in einen gemeinsamen Ordner legen und an jedem Platz hier "
                             "auswählen. Gibt es am gewählten Ort noch keine, wird die jetzige dorthin kopiert.")
        self.k_sichern = QPushButton("Jetzt sichern")
        self.k_db.clicked.connect(lambda _=False: self.datenbank_waehlen())
        self.k_sichern.clicked.connect(lambda _=False: self.jetzt_sichern())
        g5 = QGroupBox("Datenbank")
        l5 = QVBoxLayout(g5)
        l5.addWidget(self.e_pfad)
        z = QHBoxLayout()
        z.addWidget(self.k_db)
        z.addWidget(self.k_sichern)
        z.addStretch(1)
        l5.addLayout(z)

        self.k_speichern = QPushButton("Einstellungen speichern")
        self.k_speichern.setObjectName("primaer")
        self.k_speichern.clicked.connect(lambda _=False: self.einstellungen_speichern())
        innen = QWidget()
        lay = QVBoxLayout(innen)
        for g in (g1, g2, g3, g4, g5):
            lay.addWidget(g)
        z = QHBoxLayout()
        z.addWidget(self.k_speichern)
        z.addStretch(1)
        lay.addLayout(z)
        lay.addStretch(1)
        rollen = QScrollArea()
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QFrame.NoFrame)
        rollen.setWidget(innen)
        aussen = QVBoxLayout(w)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(rollen)
        return w

    def einstellungen_zeigen(self):
        ms = self.db.maschinen()
        self.e_maschinen.setRowCount(len(ms))
        for r, m in enumerate(ms):
            self.e_maschinen.setItem(r, 0, _zelle(m["name"]))
            self.e_maschinen.setItem(r, 1, _zelle(f"{m['stunden_tag']:g}".replace(".", ","), True))
            self.e_maschinen.setItem(r, 2, _zelle("ja" if m["aktiv"] else "nein"))
        self.e_maschinen.resizeColumnsToContents()
        self.e_samstag.setValue(self.db.zahl("samstag_stunden"))
        self.e_nutzung.setValue(int(self.db.zahl("nutzungsgrad", 100)))
        self.e_vorlauf.setValue(int(self.db.zahl("vorlauf_tage")))
        self.e_schwelle.setValue(int(self.db.zahl("schwelle_tage", 2)))
        self.e_land.setCurrentText(self.db.einstellung("bundesland"))
        self.e_ruhe.setText(self.db.einstellung("betriebsruhe"))
        self.e_form.setCurrentIndex(max(0, self.e_form.findData(self.db.einstellung("laufzeit_form"))))
        self.e_ohne.setCurrentIndex(max(0, self.e_ohne.findData(self.db.einstellung("ohne_einheit"))))
        self.e_design.setCurrentText(self.db.einstellung("design"))
        felder = self.db.zusatzfelder()
        self.e_felder.setRowCount(len(felder))
        for r, f in enumerate(felder):
            self.e_felder.setItem(r, 0, _zelle(f["name"]))
        self.e_pfad.setText(str(self.db.pfad))

    def einstellungen_speichern(self):
        design_alt = self.db.einstellung("design")
        for k, v in (("samstag_stunden", self.e_samstag.value()), ("nutzungsgrad", self.e_nutzung.value()),
                     ("vorlauf_tage", self.e_vorlauf.value()), ("schwelle_tage", self.e_schwelle.value()),
                     ("bundesland", self.e_land.currentText()), ("betriebsruhe", self.e_ruhe.text().strip()),
                     ("laufzeit_form", self.e_form.currentData()), ("ohne_einheit", self.e_ohne.currentData()),
                     ("design", self.e_design.currentText())):
            self.db.einstellung_setzen(k, v)
        if self.e_design.currentText() != design_alt:
            from PySide6.QtWidgets import QApplication
            stil.ansicht_wechseln(QApplication.instance(), self, self.e_design.currentText())
        self.statusBar().showMessage("Einstellungen gespeichert.", 4000)
        self.laden()

    def _maschine_gewaehlt(self):
        r = self.e_maschinen.currentRow()
        return self.db.maschinen()[r] if 0 <= r < self.e_maschinen.rowCount() else None

    def maschine_bearbeiten(self, neu=False, werte=None):
        """Dialog Maschine; werte=(Name, Stunden, aktiv) überspringt den Dialog (Tests)."""
        m = None if neu else self._maschine_gewaehlt()
        if not neu and m is None:
            return False
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Maschine hinzufügen" if neu else "Maschine ändern")
            name = QLineEdit(m["name"] if m else "")
            stunden = QDoubleSpinBox()
            stunden.setRange(0, 24)
            stunden.setDecimals(1)
            stunden.setSuffix(" h")
            stunden.setValue(m["stunden_tag"] if m else 8.0)
            aktiv = QCheckBox("aktiv (wird eingelastet und angezeigt)")
            aktiv.setChecked(bool(m["aktiv"]) if m else True)
            form = QFormLayout(d)
            form.addRow("Name", name)
            form.addRow("Stunden je Tag (Montag bis Freitag)", stunden)
            form.addRow("", aktiv)
            kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            kn.button(QDialogButtonBox.Cancel).setText("Abbrechen")
            kn.accepted.connect(d.accept)
            kn.rejected.connect(d.reject)
            form.addRow(kn)
            if d.exec() != QDialog.Accepted:
                return False
            werte = (name.text(), stunden.value(), aktiv.isChecked())
        try:
            self.db.maschine_speichern(werte[0], werte[1], werte[2], alt=m["name"] if m else None)
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def maschine_entfernen(self):
        m = self._maschine_gewaehlt()
        if m is None:
            return False
        try:
            self.db.maschine_loeschen(m["name"])
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def _feld_gewaehlt(self):
        r = self.e_felder.currentRow()
        return self.e_felder.item(r, 0).text() if r >= 0 and self.e_felder.item(r, 0) else None

    def feld_bearbeiten(self, neu=False, name=None):
        alt = None if neu else self._feld_gewaehlt()
        if not neu and alt is None:
            return False
        if name is None:
            name, ok = QInputDialog.getText(self, "Zusatzfeld", "Name des Feldes", text=alt or "")
            if not ok:
                return False
        try:
            self.db.zusatzfeld_speichern(name, alt=alt)
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def feld_entfernen(self, fragen=True):
        name = self._feld_gewaehlt()
        if name is None:
            return False
        n = self.db.zusatz_gefuellt(name)
        if n and fragen and QMessageBox.question(
                self, NAME, f"Das Feld „{name}“ ist bei {n} Aufträgen ausgefüllt. Feld und Inhalte löschen?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        self.db.zusatzfeld_loeschen(name)
        self.laden()
        return True

    def jetzt_sichern(self):
        ziel = self.db.sichern(datetime.datetime.now().strftime("%H%M%S"))
        self.statusBar().showMessage(f"Gesichert: {ziel}", 8000)
        return ziel

    def datenbank_waehlen(self, pfad=None):
        """Datenbank an einem anderen Ort öffnen (gemeinsamer Ordner). Gibt es dort keine, wird die jetzige kopiert."""
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Ort der Datenbank", str(self.db.pfad), "Datenbank (*.db)",
                                                  options=QFileDialog.DontConfirmOverwrite)
            if not pfad:
                return False
        pfad = Path(pfad)
        if pfad.resolve() == self.db.pfad.resolve():
            return False
        if not pfad.exists():
            import shutil
            pfad.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.db.pfad, pfad)
        try:
            neu = D.Daten(pfad)
        except (D.Fehler, OSError, Exception) as e:      # noqa: BLE001 – auch keine SQLite-Datei
            self.meldung(f"Die Datenbank lässt sich nicht öffnen: {e}")
            return False
        self.db.schliessen()
        self.db = neu
        ort.datenbank_merken(pfad)
        self.stand = self.db.stand()
        self.statusBar().showMessage(f"Datenbank: {pfad}")
        self.laden()
        return True

    # ------------------------------------------------------------------ alles
    def laden(self):
        """Neu rechnen und den sichtbaren Reiter füllen."""
        self.aus, self.ein = rechnung.einlasten(self.db, self.heute(), self.wochen.value())
        self.gem = rechnung.gemessen(self.db, self.aus, self.heute())
        if self.woche and self.woche[0] not in self.ein["maschinen"]:
            self.woche = None
        i = self.reiter.currentIndex()
        if i == 0:
            self.auftraege_zeigen()
        elif i == 1:
            self.auslastung_zeigen()
        elif i == 2:
            self.soll_ist_zeigen()
        else:
            self.einstellungen_zeigen()
        self.stand = self.db.stand()


def QApplicationModal():
    """Ist gerade ein Dialog offen? Dann nicht unter ihm neu laden."""
    from PySide6.QtWidgets import QApplication
    return QApplication.activeModalWidget() is not None


def _pdf_beginnen(pfad, titel):
    w = QPdfWriter(str(pfad))
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape, QMarginsF(12, 12, 12, 12)))
    w.setResolution(96)
    w.setTitle(titel)
    return w, w.pageLayout().paintRectPixels(96), QPainter(w)


def _pdf_titel(p, f, seite, text):
    f = type(f)(f)
    f.setPointSizeF(13)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#1F2937"))                   # fest: PDF, immer dunkle Schrift auf Weiß
    p.drawText(QRectF(0, 0, seite.width(), 24), Qt.AlignLeft | Qt.AlignVCenter, text)
    f.setPointSizeF(8.5)
    f.setBold(False)
    p.setFont(f)
    return 30


def _pdf_tabelle(p, f, seite, y, kopf, zeilen, breiten, writer=None):
    """Einfache Tabelle; mit writer läuft sie über mehrere Seiten. Ergebnis: y nach der letzten Zeile."""
    fm = QFontMetrics(p.font())

    def zeile(texte, y, fett=False):
        x = 0
        schrift = p.font()
        schrift.setBold(fett)
        p.setFont(schrift)
        for t, b in zip(texte, breiten):
            p.drawText(QRectF(x, y, b - 6, 14), Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(str(t), Qt.ElideRight, b - 6))
            x += b
    zeile(kopf, y, True)
    y += 16
    for z in zeilen:
        if y > seite.height() - 16:
            if writer is None:
                break
            writer.newPage()
            y = 0
            zeile(kopf, y, True)
            y += 16
        zeile(z, y)
        y += 14
    return y
