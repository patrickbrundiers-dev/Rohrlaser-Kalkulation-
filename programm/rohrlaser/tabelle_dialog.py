"""Einfaches Tabellen-Fenster für Übersichten (Teilekatalog, Lieferantenangebote, Sammel-Preisprüfung,
Lieferantenbewertung …): Text oben, Tabelle mit Mehrfachauswahl, Knöpfe mit Rückruf auf die markierten Zeilen."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)


class TabellenDialog(QDialog):
    """spalten: Überschriften; zeilen: Listen von Texten; knoepfe: [(Text, Rückruf(markierte Zeilennummern))];
    rechts: Spaltennummern rechtsbündig; farben: {Zeile: QColor/Qt-Farbe} für den Text."""

    def __init__(self, eltern, titel, text, spalten, zeilen, knoepfe=(), rechts=(), farben=None, breite=900):
        super().__init__(eltern)
        self.setWindowTitle(titel)
        self.resize(breite, 420)
        lay = QVBoxLayout(self)
        if text:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lay.addWidget(lbl)
        t = self.tabelle = QTableWidget(len(zeilen), len(spalten))
        t.setHorizontalHeaderLabels(list(spalten))
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, z in enumerate(zeilen):
            for c, w in enumerate(z):
                it = QTableWidgetItem("" if w is None else str(w))
                if c in rechts:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if farben and r in farben:
                    it.setForeground(farben[r])
                t.setItem(r, c, it)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(t)
        leiste = QDialogButtonBox(QDialogButtonBox.Close)
        self.knoepfe = {}
        for text_, rueckruf in knoepfe:
            k = QPushButton(text_)
            leiste.addButton(k, QDialogButtonBox.ActionRole)
            k.clicked.connect(lambda _=False, f=rueckruf: f(self.markiert()))
            self.knoepfe[text_] = k
        leiste.rejected.connect(self.reject)
        lay.addWidget(leiste)

    def markiert(self):
        return sorted({i.row() for i in self.tabelle.selectedIndexes()})
