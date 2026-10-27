"""Fenster „Arbeitsgänge vorschlagen“ (arbeitsgaenge.py): Arbeitsgänge je Position mit Status, Vorschläge der
Arbeitsgang-Regeln annehmen oder ablehnen."""
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import arbeitsgaenge as ag
from .rechnen import zahl

FARBE = {ag.VORSCHLAG: "#FFF6DB", ag.ABGELEHNT: "#EEEEEE", ag.ZU_PRUEFEN: "#FDECEA"}
SPALTEN = ("Pos.", "Artikel", "Arbeitsgang", "Menge je Teil", "Zeit je Teil [s]", "€ je Teil", "Kostenart",
           "Status", "Herkunft")


class ArbeitsgaengeDialog(QDialog):
    """seite: Angebotsseite mit arbeitsgang_annehmen/arbeitsgang_ablehnen und arbeitsgaenge_zeilen()."""

    def __init__(self, parent, seite):
        super().__init__(parent)
        self.seite = seite
        self.setWindowTitle("Arbeitsgänge je Position")
        self.resize(1100, 520)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.itemSelectionChanged.connect(self._knoepfe)
        kn = QHBoxLayout()
        self.annehmen_knopf = QPushButton("Annehmen")
        self.annehmen_knopf.setToolTip("Zusatzarbeit mit heutigem Preisstand in die Position übernehmen (wird ab dann "
                                       "gerechnet)")
        self.ablehnen_knopf = QPushButton("Ablehnen")
        self.zurueck_knopf = QPushButton("Ablehnung zurücknehmen")
        self.annehmen_knopf.clicked.connect(lambda: self.ausfuehren("annehmen"))
        self.ablehnen_knopf.clicked.connect(lambda: self.ausfuehren("ablehnen"))
        self.zurueck_knopf.clicked.connect(lambda: self.ausfuehren("zurueck"))
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        for b in (self.annehmen_knopf, self.ablehnen_knopf, self.zurueck_knopf):
            kn.addWidget(b)
        kn.addStretch(1)
        kn.addWidget(zu)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(self.tabelle, 1)
        lay.addLayout(kn)
        self.laden()

    def laden(self):
        self.zeilen = self.seite.arbeitsgaenge_zeilen()
        t = self.tabelle
        t.setRowCount(len(self.zeilen))
        for r, z in enumerate(self.zeilen):
            werte = (z["pos"], z["artikel"], z["arbeitsgang"],
                     f"{zahl(z['menge'])} {z['einheit']}".strip() if z["menge"] is not None else "",
                     zahl(z["zeit"], 0) if z["zeit"] else "",
                     zahl(z["betrag"]) if isinstance(z["betrag"], (int, float)) else "",
                     z["kostenart"], z["status"], z["herkunft"])
            for c, w in enumerate(werte):
                it = QTableWidgetItem("" if w is None else str(w))
                if z["status"] in FARBE:
                    it.setBackground(QBrush(QColor(FARBE[z["status"]])))
                t.setItem(r, c, it)
        s = ag.summen(self.zeilen)
        n_v = sum(1 for z in self.zeilen if z["status"] == ag.VORSCHLAG)
        self.info.setText(
            "Gerechnet werden nur Arbeitsgänge „im Angebot“ (Gewinde, Zusatzarbeiten je Teil: "
            + (", ".join(f"{k} {zahl(v)} €" for k, v in s[ag.IM_ANGEBOT].items()) or "keine") + "). "
            + (f"{n_v} Vorschlag/Vorschläge der Arbeitsgang-Regeln, voraussichtlich je Teil "
               + ", ".join(f"{k} {zahl(v)} €" for k, v in s[ag.VORSCHLAG].items())
               + " – erst nach „Annehmen“ im Preis." if n_v else "Keine offenen Vorschläge."))
        self._knoepfe()

    def markiert(self):
        r = self.tabelle.currentRow()
        return self.zeilen[r] if 0 <= r < len(self.zeilen) and self.tabelle.selectedItems() else None

    def _knoepfe(self):
        z = self.markiert()
        st = z and z["status"]
        schreibbar = not self.seite.db.nur_lesen
        self.annehmen_knopf.setEnabled(schreibbar and st in (ag.VORSCHLAG, ag.ABGELEHNT))
        self.ablehnen_knopf.setEnabled(schreibbar and st == ag.VORSCHLAG)
        self.zurueck_knopf.setEnabled(schreibbar and st == ag.ABGELEHNT)

    def waehlen(self, position_id, arbeitsgang):
        """Zeile markieren (Tests)."""
        r = next(i for i, z in enumerate(self.zeilen)
                 if z["position_id"] == position_id and z["arbeitsgang"] == arbeitsgang)
        self.tabelle.selectRow(r)
        self.tabelle.setCurrentCell(r, 0)
        return self.zeilen[r]

    def ausfuehren(self, was):
        z = self.markiert()
        if not z:
            return False
        if was == "annehmen":
            ok = self.seite.arbeitsgang_annehmen(z["position_id"], z["arbeitsgang"])
        else:
            ok = self.seite.arbeitsgang_ablehnen(z["position_id"], z["arbeitsgang"], zurueck=was == "zurueck")
        self.laden()
        return ok
