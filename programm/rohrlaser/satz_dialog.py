"""Fenster „Satz bearbeiten“ (Patrick 31.10.2026): Anzahl Sätze mit − / + und Stück je Satz je Position; die
Stückzahlen rechnen sich live mit (Sätze × Stück je Satz). Aufruf per Doppelklick auf die Spalte Satz oder Rechtsklick
„Satz bearbeiten …“; die Rechnung steht in satz_menge.py. Nach OK: self.saetze und self.je {Positions-ID: Stück je
Satz}; AngebotSeite.satz_bearbeiten schreibt sie als einen Schritt für Rückgängig."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import satz_menge, tastatur
from .eingabe import RechenSpinGanz
from .mengen_dialog import STUECK_MAX

SPALTEN = ("Pos.", "Artikel", "Bezeichnung", "Stück je Satz", "Stückzahl", "bisher")
JE_SPALTE, STUECK_SPALTE = 3, 4


def _t(x):
    if x is None:
        return ""
    return str(int(x)) if isinstance(x, (int, float)) and abs(x - round(x)) < 1e-9 else str(x).replace(".", ",")


class SatzDialog(QDialog):
    def __init__(self, parent, satz, positionen, nur_lesen=False):
        super().__init__(parent)
        self.satz, self.nur_lesen = satz, nur_lesen
        self.setWindowTitle(f"Satz bearbeiten: {satz}" + (" (nur ansehen)" if nur_lesen else ""))
        self.resize(760, 420)
        self.teile = [positionen[i] for i in satz_menge.satz_positionen(positionen, satz)]
        self.saetze, self.je = None, {}
        alt = satz_menge.anzahl(positionen, satz)
        self.alt = int(round(alt)) if alt else 1

        lay = QVBoxLayout(self)
        kopf = QHBoxLayout()
        kopf.addWidget(QLabel(f"<b>Satz {satz}</b> · {len(self.teile)} Position(en)    Anzahl Sätze:"))
        self.minus, self.plus = QPushButton("−"), QPushButton("+")
        self.anzahl = RechenSpinGanz()
        self.anzahl.setRange(1, STUECK_MAX)
        self.anzahl.setValue(self.alt)
        self.anzahl.setSuffix(" Sätze")
        for k in (self.minus, self.plus):
            k.setFixedWidth(34)
        self.minus.clicked.connect(lambda: self.anzahl.setValue(self.anzahl.value() - 1))
        self.plus.clicked.connect(lambda: self.anzahl.setValue(self.anzahl.value() + 1))
        for w in (self.minus, self.anzahl, self.plus):
            kopf.addWidget(w)
            w.setEnabled(not nur_lesen)
        kopf.addStretch(1)
        lay.addLayout(kopf)
        verschieden = sorted({round(p["stueck"] / satz_menge.je_satz(p), 2) for p in self.teile
                              if isinstance(p.get("stueck"), (int, float)) and p["stueck"] > 0})
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        if len(verschieden) > 1:
            self.hinweis.setText("Die Positionen ergeben bisher unterschiedlich viele Sätze ("
                                 + " / ".join(_t(x) for x in verschieden) + "). Mit OK haben alle die Anzahl oben.")
            self.hinweis.setStyleSheet("color: #B54708;")
        lay.addWidget(self.hinweis)

        self.tab = QTableWidget(len(self.teile), len(SPALTEN))
        self.tab.setHorizontalHeaderLabels(SPALTEN)
        self.tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab.setSelectionMode(QAbstractItemView.NoSelection)
        self.tab.verticalHeader().hide()
        self.tab.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.spins = []
        for r, p in enumerate(self.teile):
            for c, text in ((0, _t(p.get("pos"))), (1, p.get("artikel") or ""), (2, p.get("bezeichnung") or ""),
                            (5, _t(p.get("stueck")))):
                it = QTableWidgetItem(str(text))
                if c in (0, 5):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tab.setItem(r, c, it)
            sp = RechenSpinGanz()
            sp.setRange(1, STUECK_MAX)
            sp.setValue(satz_menge.je_satz(p))
            sp.setEnabled(not nur_lesen)
            sp.valueChanged.connect(self.auffrischen)
            self.tab.setCellWidget(r, JE_SPALTE, sp)
            self.spins.append(sp)
            it = QTableWidgetItem()
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tab.setItem(r, STUECK_SPALTE, it)
        lay.addWidget(self.tab, 1)
        self.summe = QLabel()
        lay.addWidget(self.summe)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        knoepfe.button(QDialogButtonBox.Ok).setEnabled(not nur_lesen)
        lay.addWidget(knoepfe)
        self.anzahl.valueChanged.connect(self.auffrischen)
        tastatur.enter_sperren(self)
        self.auffrischen()

    def stueckzahlen(self):
        """Neue Stückzahl je Zeile (Sätze × Stück je Satz)."""
        return [self.anzahl.value() * sp.value() for sp in self.spins]

    def auffrischen(self, *_):
        neu = self.stueckzahlen()
        for r, st in enumerate(neu):
            it = self.tab.item(r, STUECK_SPALTE)
            it.setText(_t(st))
            f = it.font()
            f.setBold(st != self.teile[r].get("stueck"))
            it.setFont(f)
        bisher = sum(p.get("stueck") or 0 for p in self.teile)
        self.summe.setText(f"Teile gesamt: <b>{sum(neu)}</b> (bisher {_t(bisher)}). Geänderte Stückzahlen fett. "
                           "Angelegte Staffelstufen behalten ihre Mengen und werden neu gerechnet.")

    def _ok(self):
        if self.nur_lesen:
            return
        self.saetze = self.anzahl.value()
        self.je = {p["id"]: sp.value() for p, sp in zip(self.teile, self.spins)}
        self.accept()
