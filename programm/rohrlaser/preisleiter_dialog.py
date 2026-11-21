"""Fenster „Preisleiter“ (Master-Prompt Angebotserstellung, Patrick 21.11.2026, Punkt 4): Preisstufen des Angebots
von der Preisuntergrenze bis zum Angebotspreis mit Gewinn, Aufschlag und Marge (preisleiter.py), dazu „Auf
Mindestmarge setzen“ und „Auf Zielmarge setzen“ (stellt den Gewinn des Angebots über die volle Kalkulation ein)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QFont
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from . import preisleiter as pl
from . import stil
from .stammdaten import zahl_als_text

ROT = stil.farbe_fest(stil.ROT)
GRAU = stil.farbe_fest(stil.TEXT_GRAU)
AMPEL = {pl.GUT: stil.GRUEN, pl.KNAPP: stil.ORANGE, pl.KRITISCH: stil.ROT}


def _geld(x):
    return "–" if x is None else f"{zahl_als_text(round(x, 2), 2)} €"


def _prozent(x):
    return "–" if x is None else f"{zahl_als_text(100 * x, 1)} %"


class PreisleiterDialog(QDialog):
    """seite = Angebotsseite (_rechnung, einst, db, id, auf_marge_setzen)."""

    def __init__(self, seite, parent=None):
        super().__init__(parent if parent is not None else seite)
        self.s = seite
        self.setWindowTitle(f"Preisleiter – Angebot {seite.kopf.get('nummer') or ''}")
        self.resize(900, 360)
        lay = QVBoxLayout(self)
        self.ampel = QLabel()
        self.ampel.setTextFormat(Qt.RichText)
        self.ampel.setWordWrap(True)
        lay.addWidget(self.ampel)
        self.tabelle = QTableWidget(0, len(pl.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(pl.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.tabelle, 1)
        info = QLabel(pl.umrechnung_text())
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        lay.addWidget(info)
        kn = QHBoxLayout()
        self.mindest_knopf = QPushButton("Auf Mindestmarge setzen")
        self.mindest_knopf.setToolTip("Gewinn des Angebots so einstellen, dass die Marge die Mindestmarge erreicht")
        self.mindest_knopf.clicked.connect(lambda: self.setzen(pl.ART_MINDEST))
        self.ziel_knopf = QPushButton("Auf Zielmarge setzen")
        self.ziel_knopf.setToolTip("Gewinn des Angebots so einstellen, dass die Marge die Zielmarge erreicht")
        self.ziel_knopf.clicked.connect(lambda: self.setzen(pl.ART_ZIEL))
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        kn.addWidget(self.mindest_knopf)
        kn.addWidget(self.ziel_knopf)
        kn.addStretch(1)
        kn.addWidget(zu)
        lay.addLayout(kn)
        self.laden()

    def laden(self):
        _, summen = self.s._rechnung()
        ziel_kunde = (self.s.db.zusatz(self.s.id, "zielpreis") or {}).get("gesamt") if self.s.id else None
        self.zeilen = pl.zeilen(summen, self.s.einst, ziel_kunde)
        t = self.tabelle
        t.setRowCount(len(self.zeilen))
        fett = QFont()
        fett.setBold(True)
        for r, z in enumerate(self.zeilen):
            werte = (z["titel"], _geld(z["netto"]), _geld(z["gewinn"]), _prozent(z["aufschlag"]), _prozent(z["marge"]),
                     "" if z["art"] == pl.ART_ANGEBOT else _geld(z["unterschied"]))
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if z["art"] == pl.ART_ANGEBOT:
                    it.setFont(fett)
                if c == 2 and z["gewinn"] is not None and z["gewinn"] < -0.005:
                    it.setForeground(QBrush(ROT))
                if z["art"] in (pl.ART_KURZ, pl.ART_LANG) and c:
                    it.setForeground(QBrush(GRAU))
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        b = pl.bewertung(summen, self.s.einst, self.s.unsicher_anteil() if hasattr(self.s, "unsicher_anteil") else None)
        if b:
            farbe = stil.umsetzen(AMPEL[b["stufe"]])
            self.ampel.setText(f"<span style='color:{farbe}'>●</span> <b>{b['text']}</b>"
                               + "".join(f"<br>• {g}" for g in b["gruende"]))
        arten = {z["art"] for z in self.zeilen}
        lesen = bool(self.s.db.nur_lesen or (self.s.fremd() if hasattr(self.s, "fremd") else False))
        self.mindest_knopf.setEnabled(pl.ART_MINDEST in arten and not lesen)
        self.ziel_knopf.setEnabled(pl.ART_ZIEL in arten and not lesen)
        self.mindest_knopf.setVisible(pl.ART_MINDEST in arten)
        self.ziel_knopf.setVisible(pl.ART_ZIEL in arten)

    def setzen(self, art):
        """Gewinn des Angebots auf die Marge der Stufe art einstellen; Ergebnis: neuer Gewinn (Anteil) oder None."""
        z = next((z for z in self.zeilen if z["art"] == art), None)
        if not z or z.get("satz") is None:
            return None
        g = self.s.auf_marge_setzen(z["satz"])
        self.laden()
        return g
