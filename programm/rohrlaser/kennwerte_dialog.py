"""Fenster 'Kennwerte aus der Nachkalkulation' (Einstellungen, kennwerte.py): Vorschläge Ist ÷ Soll je Quelle und
Schlüssel prüfen, mit Begründung freigeben, frühere Freigaben zurücknehmen."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import VERSION, kennwerte
from .stil import GELB_FLAECHE, TEXT_GRAU

SPALTEN = ("Quelle", "Schlüssel", "Faktor Ist ÷ Soll", "Fälle", "Streuung", "Ausreißer", "Status")
H_SPALTEN = ("Freigegeben am", "Quelle", "Schlüssel", "Faktor", "Fälle", "Begründung", "Version", "Zurückgenommen")


def _z(w, stellen=2):
    return "" if w is None else f"{w:.{stellen}f}".replace(".", ",")


class KennwerteDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Kennwerte aus der Nachkalkulation")
        self.resize(980, 620)
        lay = QVBoxLayout(self)
        info = QLabel("Vorschläge aus nachkalkulierten Angeboten: Faktor = Median von Ist ÷ Soll, Ausreißer (mehr als "
                      "3 × mittlere Abweichung) zählen nicht. Faktor 1,10 = in der Fertigung 10 % länger als "
                      "kalkuliert. Geändert wird nur nach Freigabe mit Begründung; jede Freigabe lässt sich "
                      "zurücknehmen.")
        info.setWordWrap(True)
        lay.addWidget(info)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Mindestens Fälle:"))
        self.mindest = QSpinBox()
        self.mindest.setRange(1, 100)
        self.mindest.setValue(5)
        self.mindest.valueChanged.connect(self.neu_laden)
        zeile.addWidget(self.mindest)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.tab = self._tabelle(SPALTEN)
        lay.addWidget(self.tab, 3)
        zeile = QHBoxLayout()
        self.begruendung = QLineEdit()
        self.begruendung.setPlaceholderText("Begründung der Freigabe (Pflicht), z. B. 'Nachkalkulation Q3 geprüft'")
        zeile.addWidget(self.begruendung, 1)
        self.frei = QPushButton("Gewählten Vorschlag freigeben")
        self.frei.clicked.connect(lambda: self.freigeben())
        zeile.addWidget(self.frei)
        lay.addLayout(zeile)
        lay.addWidget(QLabel("Bisherige Freigaben"))
        self.hist = self._tabelle(H_SPALTEN)
        lay.addWidget(self.hist, 2)
        zeile = QHBoxLayout()
        self.zurueck = QPushButton("Gewählte Freigabe zurücknehmen")
        self.zurueck.setToolTip("Alte Werte wiederherstellen; Werte, die seitdem von Hand geändert wurden, bleiben")
        self.zurueck.clicked.connect(lambda: self.zuruecknehmen())
        zeile.addWidget(self.zurueck)
        zeile.addStretch(1)
        self.meldung = QLabel()
        zeile.addWidget(self.meldung)
        lay.addLayout(zeile)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.geaendert = False
        self.neu_laden()

    def _tabelle(self, spalten):
        t = QTableWidget(0, len(spalten))
        t.setHorizontalHeaderLabels(spalten)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        return t

    def neu_laden(self):
        self.vorschlaege = kennwerte.vorschlaege(self.db, self.mindest.value())
        self.tab.setRowCount(len(self.vorschlaege))
        for r, v in enumerate(self.vorschlaege):
            aus = ", ".join(str(f.get("angebot") or "?") for f in v["ausreisser"])
            werte = (v["titel"], " / ".join(str(s) for s in v["schluessel"]), _z(v["faktor"], 3), str(v["n"]),
                     _z(v["streuung"], 3), aus, v["status"])
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c in (2, 3, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if v["status"] != "ok":
                    it.setForeground(QBrush(QColor(TEXT_GRAU)))
                elif v["faktor"] and abs(v["faktor"] - 1) >= 0.1:
                    it.setBackground(QBrush(QColor(GELB_FLAECHE)))
                self.tab.setItem(r, c, it)
        self.historie = kennwerte.historie(self.db)
        self.hist.setRowCount(len(self.historie))
        for r, h in enumerate(self.historie):
            werte = (h.get("datum") or "", h.get("quelle") or "", (h.get("schluessel") or "").strip("[]"),
                     _z(h.get("faktor"), 3), str(h.get("n") or ""), h.get("begruendung") or "", h.get("version") or "",
                     h.get("zurueck") or "")
            for c, w in enumerate(werte):
                self.hist.setItem(r, c, QTableWidgetItem(w))
        self.tab.resizeColumnsToContents()
        self.hist.resizeColumnsToContents()

    def freigeben(self, zeile=None, begruendung=None):
        """Vorschlag freigeben (zeile/begruendung für Tests). Ergebnis: ID der Historie oder None."""
        zeile = self.tab.currentRow() if zeile is None else zeile
        if begruendung is not None:
            self.begruendung.setText(begruendung)
        if not 0 <= zeile < len(self.vorschlaege):
            self.meldung.setText("Bitte einen Vorschlag wählen.")
            return None
        try:
            hid = kennwerte.freigeben(self.db, self.vorschlaege[zeile], self.begruendung.text(), VERSION)
        except ValueError as e:
            self.meldung.setText(str(e))
            return None
        self.geaendert = True
        self.begruendung.clear()
        self.neu_laden()
        self.meldung.setText("Freigegeben – die Kennwerte sind geändert.")
        return hid

    def zuruecknehmen(self, zeile=None):
        zeile = self.hist.currentRow() if zeile is None else zeile
        if not 0 <= zeile < len(self.historie):
            self.meldung.setText("Bitte eine Freigabe wählen.")
            return 0
        n = kennwerte.zuruecknehmen(self.db, self.historie[zeile]["id"])
        self.geaendert = self.geaendert or n > 0
        self.neu_laden()
        self.meldung.setText(f"Zurückgenommen: {n} Wert(e) wiederhergestellt.")
        return n
