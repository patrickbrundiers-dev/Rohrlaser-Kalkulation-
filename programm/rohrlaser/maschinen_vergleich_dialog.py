"""Fenster „Maschinen vergleichen“ (Vorschlag F1, maschinen_vergleich.py): je Maschine Laserzeit, Preis netto,
Abweichung zur Maschine des Angebots und frühester Termin; „Diese Maschine nehmen“ stellt das Angebot um."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import stil
from .stammdaten import zahl_als_text as zahl

SPALTEN = ("Maschine", "Laserzeit [h]", "Preis netto [€]", "Abweichung", "frühester Termin", "Hinweis")


class MaschinenVergleich(QDialog):
    def __init__(self, eltern, liste, maschine, termine=None):
        super().__init__(eltern)
        self.setWindowTitle("Maschinen vergleichen")
        self.resize(860, 320)
        self.liste, self.gewaehlt = liste, None
        jetzt = next((r for r in liste if r["maschine"] == maschine), None)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Das Angebot auf jeder Maschine gerechnet (Stundensatz, Zeitvorgaben und Konturklassen "
                             f"der Maschine, neu optimiert). Aktuell: <b>{maschine or '–'}</b>. Gespeichert wird erst "
                             "mit „Diese Maschine nehmen“."))
        t = self.tabelle = QTableWidget(len(liste), len(SPALTEN))
        t.setHorizontalHeaderLabels(SPALTEN)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, z in enumerate(liste):
            abw = ""
            if jetzt and jetzt["verkauf"] and z["verkauf"] and z is not jetzt:
                p = 100 * (z["verkauf"] / jetzt["verkauf"] - 1)
                abw = f"{'+' if p >= 0 else '−'}{zahl(abs(p), 1)} %"
            werte = (z["maschine"] + (" (aktuell)" if z is jetzt else ""),
                     zahl(z["laser_h"], 2) if z["laser_h"] is not None else "",
                     zahl(z["verkauf"], 2) if z["verkauf"] is not None else "", abw,
                     (termine or {}).get(z["maschine"], ""), z["grund"] or ("" if z["moeglich"] else "nicht möglich"))
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c in (1, 2, 3):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if not z["moeglich"]:
                    it.setForeground(stil.farbe(stil.TEXT_GRAU))
                t.setItem(r, c, it)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(t)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        self.nehmen = QPushButton("Diese Maschine nehmen")
        knoepfe.addButton(self.nehmen, QDialogButtonBox.AcceptRole)
        self.nehmen.clicked.connect(self._nehmen)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        t.itemSelectionChanged.connect(self._auswahl)
        self._auswahl()

    def _zeile(self):
        r = self.tabelle.currentRow()
        return self.liste[r] if 0 <= r < len(self.liste) else None

    def _auswahl(self):
        z = self._zeile()
        self.nehmen.setEnabled(bool(z and z["moeglich"] and "(aktuell)" not in self.tabelle.item(
            self.tabelle.currentRow(), 0).text()))

    def _nehmen(self):
        z = self._zeile()
        if z and z["moeglich"]:
            self.gewaehlt = z["maschine"]
            self.accept()
