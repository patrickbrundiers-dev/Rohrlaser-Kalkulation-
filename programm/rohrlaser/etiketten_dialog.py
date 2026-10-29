"""Etiketten mit QR-Code drucken und Rückmeldung per Scan (etiketten.py, Plan 29.10.2026 2a)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import ausgabe, etiketten, stil, tastatur
from .angebot import aktiv as position_aktiv


class EtikettenDialog(QDialog):
    """Format, Anzahl je Position (oder je Stück), erstes freies Feld auf dem Bogen, Rahmen."""

    def __init__(self, parent, db, kopf, positionen):
        super().__init__(parent)
        self.db, self.kopf, self.positionen = db, kopf, positionen
        self.setWindowTitle(f"Etiketten mit QR-Code – {kopf.get('nummer') or ''}".strip(" –"))
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        n = sum(1 for p in positionen if position_aktiv(p))
        text = (f"{n} Positionen. Je Etikett ein QR-Code für die Rückmeldung per Scan (Reiter Fertigung → "
                "Scannen …).")
        if kopf.get("vorgang") != "Beauftragt":
            text += " Hinweis: Scannen geht erst, wenn das Angebot beauftragt ist."
        info = QLabel(text)
        info.setWordWrap(True)
        form.addRow(info)
        self.format = QComboBox()
        self.format.addItems(list(etiketten.FORMATE))
        self.format.setCurrentText(db.einstellung("etikett_format") or etiketten.FORMAT_VORGABE)
        self.format.currentTextChanged.connect(self._format)
        form.addRow("Format", self.format)
        self.anzahl = QSpinBox()
        self.anzahl.setRange(1, 999)
        form.addRow("Etiketten je Position", self.anzahl)
        self.je_stueck = QCheckBox("je Stück ein Etikett (Anzahl = Stückzahl der Position)")
        self.je_stueck.toggled.connect(lambda an: self.anzahl.setEnabled(not an))
        form.addRow("", self.je_stueck)
        self.start = QSpinBox()
        self.start.setRange(1, 200)
        self.start.setToolTip("Angebrochener Etikettenbogen: Felder davor bleiben frei (gezählt zeilenweise von "
                              "links oben)")
        form.addRow("Erstes freies Feld auf dem Bogen", self.start)
        self.rahmen = QCheckBox("Rahmen um jedes Etikett (zum Ausschneiden auf Normalpapier)")
        form.addRow("", self.rahmen)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("PDF erstellen")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)
        self._format(self.format.currentText())

    def _format(self, name):
        seite = (etiketten.FORMATE.get(name) or (None,))[0]
        self.start.setEnabled(seite is not None)

    def liste(self):
        return etiketten.etiketten(self.kopf, self.positionen, self.anzahl.value(), self.je_stueck.isChecked())

    def schreiben(self, pfad):
        return etiketten.etiketten_pdf(pfad, self.liste(), self.format.currentText(), self.rahmen.isChecked(),
                                       self.start.value() - 1)


def drucken(fenster, angebot_id, parent=None, dialog=None):
    """Etiketten eines Angebots: Dialog, dann PDF im Ordner des Angebots. dialog: fertiger Dialog (Selbsttest).
    Ergebnis: Pfad oder None."""
    db = fenster.db
    kopf = db.angebot(angebot_id) or {}
    positionen = db.positionen(angebot_id)
    if not any(position_aktiv(p) for p in positionen):
        fenster.meldung("Das Angebot hat keine Positionen.", fehler=True)
        return None
    d = dialog or EtikettenDialog(parent or fenster, db, kopf, positionen)
    if dialog is None and not d.exec():
        return None
    try:
        pfad = fenster.angebot_ordner(kopf) / (ausgabe.dateiname(kopf, "Etiketten") + ".pdf")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            n = d.schreiben(pfad)
        finally:
            QApplication.restoreOverrideCursor()
    except OSError as e:
        QMessageBox.warning(parent or fenster, "Etiketten", f"Die Datei konnte nicht gespeichert werden:\n{e}")
        return None
    if d.format.currentText() != db.einstellung("etikett_format") and not db.nur_lesen:
        db.einstellung_setzen("etikett_format", d.format.currentText())      # nächstes Mal dasselbe Format
    fenster.meldung(f"{n} Etiketten gespeichert: {pfad}")
    fenster.datei_oeffnen(pfad)
    return pfad


class ScanDialog(QDialog):
    """Rückmeldung per Handscanner: Arbeitsschritt wählen, Etiketten scannen (der Scanner tippt den Code und Enter).
    Bleibt offen, bis man ihn schließt; jede Rückmeldung steht unten in der Liste."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.ergebnisse = []
        self.setWindowTitle("Rückmeldung per Scan")
        self.resize(760, 480)
        self.schritt = QComboBox()
        self.schritt.addItems(etiketten.schritte(self.db))
        self.menge = QDoubleSpinBox()
        self.menge.setRange(0, 1_000_000)
        self.menge.setDecimals(0)
        self.menge.setSpecialValueText("ganze Position")
        self.menge.setToolTip("Leer (0) = die ganze Stückzahl der Position; sonst diese Menge (Teilmenge)")
        self.feld = QLineEdit()
        self.feld.setPlaceholderText("Etikett scannen (oder Code eintippen und Enter)")
        self.feld.returnPressed.connect(self.scannen)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Arbeitsschritt"))
        oben.addWidget(self.schritt)
        oben.addWidget(QLabel("Menge"))
        oben.addWidget(self.menge)
        oben.addStretch(1)
        self.meldung = QLabel("Bereit. Der Scanner tippt den Code ins Feld und bestätigt selbst.")
        self.meldung.setWordWrap(True)
        self.meldung.setTextFormat(Qt.RichText)
        self.liste = QTableWidget(0, 4)
        self.liste.setHorizontalHeaderLabels(("Zeit", "Schritt", "Ergebnis", "Code"))
        self.liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.liste.verticalHeader().hide()
        self.liste.horizontalHeader().setStretchLastSection(False)
        knoepfe = QDialogButtonBox()
        schliessen = QPushButton("Schließen")
        knoepfe.addButton(schliessen, QDialogButtonBox.RejectRole)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.feld)
        lay.addWidget(self.meldung)
        lay.addWidget(self.liste, 1)
        lay.addWidget(knoepfe)
        tastatur.enter_sperren(self)       # Enter des Scanners bestätigt nur das Feld, schließt nie das Fenster
        self.feld.setFocus()

    def scannen(self, text=None):
        """Einen Scan verarbeiten. Ergebnis: dict aus etiketten.rueckmelden oder None (Fehler steht in der Meldung)."""
        text = self.feld.text() if text is None else text
        self.feld.clear()
        if not str(text).strip():
            return None
        import datetime
        zeit = datetime.datetime.now().strftime("%H:%M:%S")
        from .datenbank import Lesemodus
        from .fertigung import FertigungFehler
        try:
            r = etiketten.rueckmelden(self.db, text, self.schritt.currentText(), self.menge.value() or None)
        except (etiketten.ScanFehler, FertigungFehler, Lesemodus) as e:
            QApplication.beep()
            self.meldung.setText(f"<span style='color:#B42318'><b>Nicht übernommen:</b> {e}</span>")
            self._zeile(zeit, str(e), text, fehler=True)
            return None
        self.meldung.setText(f"<span style='color:#1D7A46'><b>OK</b></span> {r['text']}")
        self._zeile(zeit, r["text"], text)
        self.menge.setValue(0)          # Teilmenge gilt nur für einen Scan
        self.ergebnisse.append(r)
        if hasattr(self.f, "fertigung"):
            self.f.fertigung.neu_laden()
        return r

    def _zeile(self, zeit, text, code, fehler=False):
        self.liste.insertRow(0)
        for c, t in enumerate((zeit, self.schritt.currentText(), text, str(code).strip())):
            it = QTableWidgetItem(t)
            if fehler:
                it.setForeground(QBrush(stil.farbe("#B42318")))
            self.liste.setItem(0, c, it)
        self.liste.resizeColumnsToContents()
