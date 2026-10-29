"""Reklamation erfassen (im Angebot) und Datei → „Reklamationen …“ (reklamation.py, Plan 29.10.2026 2c)."""
import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import reklamation as rk
from . import stil
from .angebot import aktiv as position_aktiv
from .ausgabe import euro_text


def _z(x):
    return "" if x is None else (str(int(x)) if float(x).is_integer() else f"{x:.1f}".replace(".", ","))


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return ""


class ReklamationDialog(QDialog):
    """Eine Reklamation: Position (oder ganzer Auftrag), Datum, Menge, Fehlerart, Ursache, Maßnahme, Kosten, Status,
    Bemerkung. Nach OK: self.werte (dict für reklamation.speichern)."""

    def __init__(self, parent, db, angebot_id, alt=None):
        super().__init__(parent)
        self.db, self.angebot_id, self.alt = db, angebot_id, alt or {}
        self.werte = None
        kopf = db.angebot(angebot_id) or {}
        self.setWindowTitle(f"Reklamation – {kopf.get('nummer') or ''}".strip(" –"))
        self.setMinimumWidth(520)
        form = QFormLayout(self)
        info = QLabel(f"Kunde: {kopf.get('kunde') or '–'}. Die Kosten gehen als „Reklamationen“ in die "
                      "Nachkalkulation des Auftrags.")
        info.setWordWrap(True)
        form.addRow(info)
        self.position = QComboBox()
        self.position.addItem(rk.ALLE_POSITIONEN, None)
        for p in db.positionen(angebot_id):
            if position_aktiv(p):
                self.position.addItem(f"Pos. {rk._pos_text(p.get('pos'))}  {p.get('artikel') or ''}  "
                                      f"({_z(p.get('stueck'))} Stk)".replace("  (", " ("), p["id"])
        if self.position.count() > 1:
            self.position.setCurrentIndex(1)
        form.addRow("Position", self.position)
        self.datum = QDateEdit()
        self.datum.setCalendarPopup(True)
        self.datum.setDisplayFormat("dd.MM.yyyy")
        self.datum.setDate(QDate.currentDate())
        form.addRow("Datum", self.datum)
        self.menge = QDoubleSpinBox()
        self.menge.setRange(0, 1_000_000)
        self.menge.setDecimals(0)
        self.menge.setSuffix(" Stk")
        form.addRow("Menge reklamiert", self.menge)
        self.fehlerart = QComboBox()
        self.fehlerart.addItems(rk.fehlerarten(db))
        form.addRow("Fehlerart", self.fehlerart)
        self.ursache = QComboBox()
        self.ursache.addItems(list(rk.URSACHEN))
        form.addRow("Ursache", self.ursache)
        self.massnahme = QComboBox()
        self.massnahme.addItems(list(rk.MASSNAHMEN))
        form.addRow("Maßnahme", self.massnahme)
        self.kosten = QDoubleSpinBox()
        self.kosten.setRange(0, 10_000_000)
        self.kosten.setDecimals(2)
        self.kosten.setGroupSeparatorShown(True)
        self.kosten.setSuffix(" €")
        self.kosten.setToolTip("Eigene Kosten der Reklamation: Nacharbeit, Neuteile (Material und Laserzeit), "
                               "Gutschrift, Fracht")
        form.addRow("Kosten", self.kosten)
        self.status = QComboBox()
        self.status.addItems(list(rk.STATUS))
        form.addRow("Status", self.status)
        self.bemerkung = QLineEdit()
        self.bemerkung.setPlaceholderText("z. B. Prüfbericht, Absprache mit dem Kunden")
        form.addRow("Bemerkung", self.bemerkung)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #B42318")
        self.fehler.setWordWrap(True)
        self.fehler.hide()
        form.addRow(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Speichern")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)
        if self.alt:
            self._laden(self.alt)

    def _laden(self, r):
        i = self.position.findData(r.get("position_id"))
        self.position.setCurrentIndex(max(0, i))
        try:
            self.datum.setDate(QDate.fromString(r.get("datum") or "", "yyyy-MM-dd"))
        except TypeError:
            pass
        self.menge.setValue(r.get("menge") or 0)
        for feld, wert in ((self.fehlerart, r.get("fehlerart")), (self.ursache, r.get("ursache")),
                           (self.massnahme, r.get("massnahme")), (self.status, r.get("status"))):
            if wert and feld.findText(wert) < 0:
                feld.addItem(wert)
            if wert:
                feld.setCurrentText(wert)
        self.kosten.setValue(r.get("kosten") or 0)
        self.bemerkung.setText(r.get("bemerkung") or "")

    def _ok(self):
        self.werte = dict(position_id=self.position.currentData(), datum=self.datum.date().toString("yyyy-MM-dd"),
                          menge=self.menge.value() or None, fehlerart=self.fehlerart.currentText(),
                          ursache=self.ursache.currentText(), massnahme=self.massnahme.currentText(),
                          kosten=self.kosten.value(), status=self.status.currentText(),
                          bemerkung=self.bemerkung.text().strip())
        try:
            self.id = rk.speichern(self.db, self.angebot_id, self.werte, self.alt.get("id"))
        except rk.ReklamationFehler as e:          # im Fenster zeigen, es bleibt offen
            self.fehler.setText(str(e))
            self.fehler.show()
            self.werte = None
            return
        self.accept()


def erfassen(fenster, angebot_id, parent=None, dialog=None, alt=None):
    """Reklamation erfassen bzw. ändern. dialog: fertiger Dialog (Selbsttest, statt exec: _ok()). Ergebnis: id oder
    None."""
    kopf = fenster.db.angebot(angebot_id) or {}
    if kopf.get("vorgang") != "Beauftragt":
        fenster.meldung("Reklamationen nur für beauftragte Angebote (Vorgang „Beauftragt“).", fehler=True)
        return None
    d = dialog or ReklamationDialog(parent or fenster, fenster.db, angebot_id, alt)
    if dialog is None and not d.exec():
        return None
    if d.werte is None:
        return None
    fenster.meldung(f"Reklamation zu {kopf.get('nummer')} gespeichert.")
    return d.id


SPALTEN = ("Datum", "Angebot", "Kunde", "Pos.", "Artikel", "Menge", "Fehlerart", "Ursache", "Maßnahme", "Kosten [€]",
           "Status")
SPALTEN_AUSW = ("", "Reklamationen", "Stück reklamiert", "Kosten [€]", "Stück geliefert", "Quote")


class ReklamationenDialog(QDialog):
    """Alle Reklamationen (offene oder alle) und die Auswertung je Fehlerart, Kunde und Werkstoff."""

    def __init__(self, fenster, heute=None):
        super().__init__(fenster)
        self.f, self.db, self.heute = fenster, fenster.db, heute
        self.zeilen = []
        self.setWindowTitle("Reklamationen")
        self.resize(1100, 600)
        self.filter = QComboBox()
        self.filter.addItems(["offene", "alle"])
        self.filter.currentIndexChanged.connect(lambda _i: self.laden())
        self.kopf = QLabel()
        self.kopf.setWordWrap(True)
        self.kopf.setTextFormat(Qt.RichText)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.verticalHeader().hide()
        self.tabelle.doubleClicked.connect(lambda _i: self.bearbeiten())
        knopf_bearbeiten = QPushButton("Bearbeiten …")
        knopf_bearbeiten.clicked.connect(lambda: self.bearbeiten())
        knopf_erledigt = QPushButton("Erledigt")
        knopf_erledigt.clicked.connect(lambda: self.erledigt())
        knopf_oeffnen = QPushButton("Angebot öffnen")
        knopf_oeffnen.clicked.connect(lambda: self.oeffnen())
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Anzeigen"))
        oben.addWidget(self.filter)
        oben.addStretch(1)
        for k in (knopf_bearbeiten, knopf_erledigt, knopf_oeffnen):
            oben.addWidget(k)
        liste = QWidget()
        ll = QVBoxLayout(liste)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addLayout(oben)
        ll.addWidget(self.tabelle)
        self.reiter = QTabWidget()
        self.reiter.addTab(liste, "Liste")
        self.auswertungen = {}
        for name, titel in (("fehlerart", "Je Fehlerart"), ("kunde", "Je Kunde"), ("werkstoff", "Je Werkstoff")):
            t = QTableWidget(0, len(SPALTEN_AUSW))
            t.setHorizontalHeaderLabels((titel.removeprefix("Je "),) + SPALTEN_AUSW[1:])
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            t.verticalHeader().hide()
            self.auswertungen[name] = t
            self.reiter.addTab(t, titel)
        hinweis = QLabel("Neue Reklamationen im beauftragten Angebot: Ausgaben → Reklamation erfassen …")
        hinweis.setStyleSheet("color: #5f6b7a")
        knoepfe = QDialogButtonBox()
        knoepfe.addButton("Schließen", QDialogButtonBox.RejectRole)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.kopf)
        lay.addWidget(self.reiter, 1)
        lay.addWidget(hinweis)
        lay.addWidget(knoepfe)
        self.laden()

    def laden(self):
        self.zeilen = rk.liste(self.db, nur_offen=self.filter.currentIndex() == 0)
        t = self.tabelle
        t.setRowCount(len(self.zeilen))
        offen = QBrush(stil.farbe("#FFF2CC"))
        for r, z in enumerate(self.zeilen):
            werte = (_datum(z.get("datum")), z.get("nummer") or "", z.get("kunde") or "", z.get("pos") or "",
                     z.get("artikel") or "", _z(z.get("menge")), z.get("fehlerart") or "", z.get("ursache") or "",
                     z.get("massnahme") or "", euro_text(z.get("kosten") or 0), z.get("status") or "")
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c in (5, 9):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if z.get("status") == rk.OFFEN:
                    it.setBackground(offen)
                if z.get("bemerkung"):
                    it.setToolTip(z["bemerkung"])
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        a = rk.auswertung(self.db, self.heute)
        g = a["gesamt"]
        q = f"{g['quote'] * 100:.2f} %".replace(".", ",") if g["quote"] is not None else "–"
        self.kopf.setText(f"<b>{g['offen']} offen</b> · letzte 12 Monate: {g['anzahl']} Reklamationen, "
                          f"{_z(g['menge'])} Stück, Kosten {euro_text(g['kosten'])} € · <b>Quote {q}</b> "
                          f"(reklamierte von {_z(g['geliefert'])} gelieferten Stück in {g['auftraege']} "
                          f"{'Auftrag' if g['auftraege'] == 1 else 'Aufträgen'})")
        for name, t in self.auswertungen.items():
            t.setRowCount(len(a[name]))
            for r, z in enumerate(a[name]):
                werte = (str(z["name"]), str(z["anzahl"]), _z(z["menge"]), euro_text(z["kosten"]),
                         _z(z["geliefert"]), f"{z['quote'] * 100:.2f} %".replace(".", ",") if z["quote"] is not None
                         else "")
                for c, w in enumerate(werte):
                    it = QTableWidgetItem(w)
                    if c:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    t.setItem(r, c, it)
            t.resizeColumnsToContents()
            t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

    def markiert(self):
        r = self.tabelle.currentRow()
        return self.zeilen[r] if 0 <= r < len(self.zeilen) and self.tabelle.selectedItems() else None

    def bearbeiten(self, dialog=None):
        z = self.markiert()
        if not z:
            return None
        i = erfassen(self.f, z["angebot_id"], self, dialog, alt=z)
        self.laden()
        return i

    def erledigt(self):
        z = self.markiert()
        if z:
            rk.erledigen(self.db, z["id"])
            self.laden()

    def oeffnen(self):
        z = self.markiert()
        if z:
            self.f.angebot_oeffnen(z["angebot_id"])
            self.accept()
