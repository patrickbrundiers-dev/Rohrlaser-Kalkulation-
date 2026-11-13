"""Fenster „Kundenwert“ (kundenwert.py, OFFER-012): je Kunde und Jahr Angebote, Aufträge, Quote, Umsatz und
Deckungsbeitrag aus der Nachkalkulation. Nur Anzeige."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import kundenwert

SPALTEN = ("Kunde", "Kd.-Nr.", "Jahr", "Angebote", "Aufträge", "Auftragsquote", "Umsatz netto",
           "DB Ist (Nachkalk.)", "DB Soll (Nachkalk.)", "DB-Quote Ist", "nachkalkuliert")


def _e(w):
    return "" if w is None else f"{w:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _p(w):
    return "" if w is None else f"{100 * w:.1f} %".replace(".", ",")


class KundenwertDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Kundenwert")
        self.resize(1150, 560)
        lay = QVBoxLayout(self)
        info = QLabel("Je Kunde und Jahr: Umsatz = Verkaufspreis netto der beauftragten Angebote; Deckungsbeitrag "
                      "(Erlös − Einzelkosten) nur aus der Nachkalkulation, mit der Zahl der nachkalkulierten "
                      "Aufträge – ohne Nachkalkulation bleibt er leer statt geschätzt.")
        info.setWordWrap(True)
        lay.addWidget(info)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Jahr:"))
        self.jahr = QComboBox()
        self.jahr.addItem("alle", None)
        for j in kundenwert.jahre(db):
            self.jahr.addItem(j, j)
        if self.jahr.count() > 1:
            self.jahr.setCurrentIndex(1)
        self.jahr.currentIndexChanged.connect(self.neu_laden)
        zeile.addWidget(self.jahr)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.tab = QTableWidget(0, len(SPALTEN))
        self.tab.setHorizontalHeaderLabels(SPALTEN)
        self.tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.verticalHeader().setVisible(False)
        self.tab.setSortingEnabled(False)
        lay.addWidget(self.tab, 1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.neu_laden()

    def neu_laden(self):
        self.zeilen = kundenwert.zeilen(self.db, self.jahr.currentData())
        self.tab.setRowCount(len(self.zeilen))
        for r, z in enumerate(self.zeilen):
            werte = (z["kunde"], z["kundennr"], z["jahr"], str(z["angebote"]), str(z["auftraege"]), _p(z["quote"]),
                     _e(z["umsatz"]), _e(z["db_ist"]), _e(z["db_soll"]), _p(z["db_quote"]),
                     f"{z['nachkalkuliert']} von {z['auftraege']}")
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c >= 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tab.setItem(r, c, it)
        self.tab.resizeColumnsToContents()
