"""Fenster „Schneiddaten aus Nachkalkulation kalibrieren“ (kalibrierung.py, D1 MACH-005, D3 MACH-004): Vorschläge je
Wandstufe und je Wandbereich mit Faktor, Fällen, Bandbreite und den neuen Vorschüben; übernommen wird nur mit dem
Knopf „Übernehmen“ (Quelle Nachkalkulation, Historie unter Kennwerte, dort zurücknehmbar)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import VERSION, kalibrierung as kb, stil
from .eingabe import RechenSpinGanz
from .stil import GELB_FLAECHE, TEXT_GRAU

SPALTEN = ("Art", "Maschine", "Werkstoff", "Wand", "Gas", "Faktor Ist ÷ Soll", "Bandbreite", "Fälle", "Vorschub groß "
           "alt → neu [mm/min]", "Status")


def _z(w, n=2):
    return "" if w is None else f"{w:.{n}f}".replace(".", ",")


class KalibrierDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db, self.geaendert = db, False
        self.setWindowTitle("Schneiddaten aus Nachkalkulation kalibrieren")
        self.resize(1100, 520)
        lay = QVBoxLayout(self)
        info = QLabel("Je Schneiddaten-Zeile (Wandstufe) und je Wandbereich: Faktor = Median der Laufzeit Ist ÷ Soll "
                      "aus der Nachkalkulation, Ausreißer zählen nicht; Bandbreite = 10. bis 90. Perzentil. Faktor "
                      "1,10 = in der Fertigung 10 % länger, die Vorschübe werden ÷ 1,10 kleiner. Geändert wird nur "
                      "mit „Übernehmen“; die Zeile bekommt die Quelle „Nachkalkulation“, die Freigabe steht unter "
                      "Kennwerte und lässt sich dort zurücknehmen.")
        info.setWordWrap(True)
        lay.addWidget(info)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Mindestens Fälle:"))
        self.mindest = RechenSpinGanz()
        self.mindest.setRange(1, 100)
        self.mindest.setValue(kb.MINDESTENS)
        self.mindest.valueChanged.connect(self.neu_laden)
        zeile.addWidget(self.mindest)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.tab = QTableWidget(0, len(SPALTEN))
        self.tab.setHorizontalHeaderLabels(SPALTEN)
        self.tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tab.verticalHeader().setVisible(False)
        self.tab.horizontalHeader().setStretchLastSection(True)
        self.tab.itemSelectionChanged.connect(self._gewaehlt)
        lay.addWidget(self.tab, 1)
        zeile = QHBoxLayout()
        self.uebernehmen_knopf = QPushButton("Übernehmen")
        self.uebernehmen_knopf.setToolTip("Vorschübe der gewählten Zeile(n) ÷ Faktor, Quelle Nachkalkulation")
        self.uebernehmen_knopf.clicked.connect(lambda: self.uebernehmen())
        zeile.addWidget(self.uebernehmen_knopf)
        self.meldung = QLabel()
        zeile.addWidget(self.meldung, 1)
        lay.addLayout(zeile)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.neu_laden()

    def neu_laden(self):
        self.vorschlaege = kb.vorschlaege(self.db, self.mindest.value())
        self.tab.setRowCount(len(self.vorschlaege))
        for r, v in enumerate(self.vorschlaege):
            s = list(v["schluessel"])
            wand = f"≤ {_z(s[2], 1)} mm" if v["quelle"] == kb.QUELLE_TEIL else s[2]
            gas = s[3] if v["quelle"] == kb.QUELLE_TEIL else "alle"
            b = v.get("band")
            vor = "; ".join(f"{_z(a, 0)} → {_z(n, 0)}" for _, _, a, n in v["zeilen"][:4] if a is not None)
            werte = (v["art"], s[0], s[1], wand, gas, _z(v["faktor"], 3),
                     f"{_z(b[0], 2)}–{_z(b[1], 2)}" if b else "", str(v["n"]), vor, v["status"])
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                if c in (5, 6, 7):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if v["status"] != "ok":
                    it.setForeground(QBrush(stil.farbe(TEXT_GRAU)))
                elif v["faktor"] and abs(v["faktor"] - 1) >= 0.1:
                    it.setBackground(QBrush(stil.farbe(GELB_FLAECHE)))
                self.tab.setItem(r, c, it)
        self.tab.resizeColumnsToContents()
        self.meldung.setText("" if self.vorschlaege else "Noch keine Laufzeiten je Teil in der Nachkalkulation erfasst.")
        self._gewaehlt()

    def _gewaehlt(self):
        r = self.tab.currentRow()
        self.uebernehmen_knopf.setEnabled(0 <= r < len(self.vorschlaege) and self.vorschlaege[r]["status"] == "ok")

    def uebernehmen(self, zeile=None):
        """Gewählten Vorschlag übernehmen (zeile für Tests). Ergebnis: ID der Historie oder None."""
        r = self.tab.currentRow() if zeile is None else zeile
        if not 0 <= r < len(self.vorschlaege):
            self.meldung.setText("Bitte einen Vorschlag wählen.")
            return None
        try:
            hid = kb.uebernehmen(self.db, self.vorschlaege[r], VERSION)
        except ValueError as e:
            self.meldung.setText(str(e))
            return None
        self.geaendert = True
        self.neu_laden()
        self.meldung.setText("Übernommen – Vorschübe geändert, Quelle Nachkalkulation (zurücknehmen unter Kennwerte).")
        return hid
