"""Reiter „Optimierung“ im Angebot (Plan X6, optimierungsvorschlaege.py): alle Vorschläge einheitlich mit Ist,
Variante, Zeit-, Material- und Kostenersparnis, Voraussetzung und Nachweis; „Als neue Fassung übernehmen“."""
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import optimierungsvorschlaege as ov


class OptimierungSeite(QWidget):
    """seite: Angebotsseite mit optimierung_vorschlaege() und vorschlag_uebernehmen(v)."""

    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        self.vorschlaege = []
        self.info = QLabel("Vorschläge rechnen: Lieferlängen, Material aus dem Lager, andere Maschine (das ganze Angebot "
                           "wird je Maschine neu optimiert, das dauert etwas) und Schneiddaten prüfen aus den Ist-Zeiten "
                           "der Nachkalkulation. Das Angebot bleibt unverändert; übernommen wird nur als neue Fassung.")
        self.info.setWordWrap(True)
        self.rechnen_knopf = QPushButton("Vorschläge rechnen")
        self.rechnen_knopf.clicked.connect(lambda: self.laden())
        self.uebernehmen_knopf = QPushButton("Als neue Fassung übernehmen")
        self.uebernehmen_knopf.setObjectName("primaer")
        self.uebernehmen_knopf.clicked.connect(lambda: self.uebernehmen())
        self.tabelle = QTableWidget(0, len(ov.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels([t for _, t in ov.SPALTEN])
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.itemSelectionChanged.connect(self._knoepfe)
        self.leer = QLabel("")
        kn = QHBoxLayout()
        kn.addWidget(self.rechnen_knopf)
        kn.addWidget(self.uebernehmen_knopf)
        kn.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addLayout(kn)
        lay.addWidget(self.leer)
        lay.addWidget(self.tabelle, 1)
        self._knoepfe()

    def laden(self, maschinen=True):
        self.vorschlaege = self.seite.optimierung_vorschlaege(maschinen=maschinen)
        t = self.tabelle
        t.setRowCount(0)
        for v in self.vorschlaege:
            r = t.rowCount()
            t.insertRow(r)
            for c, (schl, _) in enumerate(ov.SPALTEN):
                t.setItem(r, c, QTableWidgetItem(ov.text(v, schl)))
        self.leer.setText("" if self.vorschlaege else
                          "Keine Vorschläge mit gerechnetem Vorteil (oder noch nicht optimiert).")
        self._knoepfe()
        return self.vorschlaege

    def markiert(self):
        r = self.tabelle.currentRow()
        return self.vorschlaege[r] if 0 <= r < len(self.vorschlaege) and self.tabelle.selectedItems() else None

    def _knoepfe(self):
        v = self.markiert()
        self.uebernehmen_knopf.setEnabled(bool(v and v.get("aktion") and not self.seite.db.nur_lesen))

    def uebernehmen(self, v=None):
        v = v or self.markiert()
        return self.seite.vorschlag_uebernehmen(v) if v else None
