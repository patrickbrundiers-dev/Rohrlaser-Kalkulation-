"""Fenster „Maße“ (Messplan 19.11.2026, M2): alle stehenden Maße einer 3D-Ansicht als Liste – umbenennen,
ein-/ausblenden, löschen, kopieren, als CSV oder als PDF-Messprotokoll speichern. Gilt in jedem 3D-Fenster
(Rechtsklick → Maße, Knopf „Maße …“ in der Mess-Tafel). Ändert nur die Anzeige der Maße, nie das Teil."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import einblendung, mess_protokoll

SPALTEN = ("Nr.", "Name", "Art", "Wert", "Messung", "Sichtbar")


class MessListe(QDialog):
    def __init__(self, ansicht, parent=None):
        super().__init__(parent or ansicht.window())
        self.ansicht = ansicht
        self.setWindowTitle("Maße")
        self.resize(820, 420)
        lay = QVBoxLayout(self)
        self.hinweis = QLabel("Stehende Maße dieser 3D-Ansicht. Name doppelklicken zum Umbenennen, Haken blendet ein "
                              "oder aus. Messen ändert nichts am Teil.")
        self.hinweis.setWordWrap(True)
        lay.addWidget(self.hinweis)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setVisible(False)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(4, QHeaderView.Stretch)
        lay.addWidget(self.tabelle, 1)
        knoepfe = QHBoxLayout()
        self.knoepfe = {}
        for name, text, tipp, fn in (
                ("loeschen", "Löschen", "Markierte Maße entfernen", self.loeschen),
                ("kopieren", "Alle kopieren", "Alle Maße als Text in die Zwischenablage", self.kopieren),
                ("csv", "CSV speichern …", "Alle Maße als Tabelle (Excel, Trennzeichen ;)", self.csv),
                ("pdf", "Messprotokoll (PDF) …", "Bild der Ansicht und alle Maße als PDF", self.pdf)):
            k = QPushButton(text)
            k.setToolTip(tipp)
            k.clicked.connect(fn)
            knoepfe.addWidget(k)
            self.knoepfe[name] = k
        knoepfe.addStretch(1)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        knoepfe.addWidget(zu)
        lay.addLayout(knoepfe)
        self._laden = False
        self.tabelle.itemChanged.connect(self._geaendert)
        self.laden()

    def laden(self):
        self._laden = True
        masse = self.ansicht.masse_liste()
        zeilen = mess_protokoll.zeilen(masse)
        self.tabelle.setRowCount(len(masse))
        for r, (m, z) in enumerate(zip(masse, zeilen)):
            for c, text in enumerate((z[0], z[1], z[2], z[3], z[4])):
                it = QTableWidgetItem(text)
                if c != 1:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c == 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(r, c, it)
            it = QTableWidgetItem("")
            it.setFlags((it.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            it.setCheckState(Qt.Checked if m.sichtbar else Qt.Unchecked)
            self.tabelle.setItem(r, 5, it)
        for k in ("loeschen", "kopieren", "csv"):
            self.knoepfe[k].setEnabled(bool(masse))
        self._laden = False

    def _geaendert(self, it):
        if self._laden:
            return
        r, c = it.row(), it.column()
        if c == 1:
            self.ansicht.mass_aendern(r, name=it.text().strip())
        elif c == 5:
            self.ansicht.mass_aendern(r, sichtbar=it.checkState() == Qt.Checked)

    def loeschen(self):
        zeilen = sorted({i.row() for i in self.tabelle.selectedIndexes()})
        if not zeilen:
            einblendung.melden(self, "Erst Maße in der Liste markieren.")
            return
        self.ansicht.mass_entfernen(zeilen)
        self.laden()

    def kopieren(self):
        self.ansicht.masse_kopieren()
        einblendung.melden(self, "Maße in die Zwischenablage kopiert.")

    def _kopf(self):
        titel = getattr(self.ansicht, "titel", "") or ""
        return [("Teil", titel)] if titel else []

    def csv(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Maße als CSV speichern", "Masse.csv", "CSV (*.csv)")
        if pfad:
            self.ansicht.masse_csv(pfad, self._kopf())
            einblendung.melden(self, f"Gespeichert: {pfad}")
        return pfad

    def pdf(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Messprotokoll speichern", "Messprotokoll.pdf", "PDF (*.pdf)")
        if pfad:
            self.ansicht.masse_pdf(pfad, angaben=self._kopf())
            einblendung.melden(self, f"Gespeichert: {pfad}")
        return pfad
