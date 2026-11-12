"""Reiter „Optimierung“ im Angebot (Plan X6, optimierungsvorschlaege.py): alle Vorschläge einheitlich mit Ist,
Variante, Zeit-, Material- und Kostenersparnis, Voraussetzung und Nachweis; „Als neue Fassung übernehmen“."""
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import empfindlichkeit as ef, optimierungsvorschlaege as ov


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
        # CALC-029: Empfindlichkeit je Annahme (±10 %)
        self.ef_knopf = QPushButton("Empfindlichkeit rechnen (±10 %)")
        self.ef_knopf.setToolTip("Angebot je Annahme mit −10 % und +10 % neu rechnen: Vorschub, Materialpreis, "
                                 "Stundensatz, Rüstzeit, Zeit der Zusatzarbeiten; zeigt die größten Hebel in €")
        self.ef_knopf.clicked.connect(lambda: self.empfindlichkeit_laden())
        self.ef_tabelle = QTableWidget(0, 4)
        self.ef_tabelle.setHorizontalHeaderLabels(["Position", "Annahme", "Preis bei +10 %", "Preis bei −10 %"])
        self.ef_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ef_tabelle.verticalHeader().setVisible(False)
        self.ef_tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ef_tabelle.horizontalHeader().setStretchLastSection(True)
        self.ef_tabelle.setVisible(False)
        self.ef_info = QLabel("")
        self.ef_info.setWordWrap(True)
        kn = QHBoxLayout()
        kn.addWidget(self.rechnen_knopf)
        kn.addWidget(self.uebernehmen_knopf)
        kn.addWidget(self.ef_knopf)
        kn.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addLayout(kn)
        lay.addWidget(self.leer)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(self.ef_info)
        lay.addWidget(self.ef_tabelle, 1)
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

    def empfindlichkeit_laden(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = self.seite.empfindlichkeit()
        finally:
            QApplication.restoreOverrideCursor()
        t = self.ef_tabelle
        t.setRowCount(0)
        if not r:
            self.ef_info.setText("Erst optimieren, dann die Empfindlichkeit rechnen.")
            t.setVisible(False)
            return r
        z = ov.rechnen.zahl

        def zeile(pos, x):
            n = t.rowCount()
            t.insertRow(n)
            for c, w in enumerate((pos, x["hebel"] + ("" if x["linear"] else " (nicht linear)"),
                                   f"{'+' if x['plus'] >= 0 else ''}{z(x['plus'])} €",
                                   f"{'+' if x['minus'] >= 0 else ''}{z(x['minus'])} €")):
                t.setItem(n, c, QTableWidgetItem(w))
        for x in r["angebot"]:
            zeile("Angebot", x)
        for p in r["positionen"]:
            for x in p["hebel"]:
                zeile(f"Pos. {p['pos']}", x)
        top = r["angebot"][:3]
        self.ef_info.setText(f"Netto {z(r['basis'])} €. Größte Hebel: "
                             + "; ".join(f"{x['hebel']} {ef.text(x)}" for x in top)
                             + ". Je Position die drei größten. Das Angebot bleibt unverändert.")
        t.setVisible(True)
        return r

    def markiert(self):
        r = self.tabelle.currentRow()
        return self.vorschlaege[r] if 0 <= r < len(self.vorschlaege) and self.tabelle.selectedItems() else None

    def _knoepfe(self):
        v = self.markiert()
        self.uebernehmen_knopf.setEnabled(bool(v and v.get("aktion") and not self.seite.db.nur_lesen))

    def uebernehmen(self, v=None):
        v = v or self.markiert()
        return self.seite.vorschlag_uebernehmen(v) if v else None
