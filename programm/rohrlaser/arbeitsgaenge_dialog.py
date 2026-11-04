"""Fenster „Arbeitsgänge vorschlagen“ (arbeitsgaenge.py): Arbeitsgänge je Position mit Status, Vorschläge der
Arbeitsgang-Regeln annehmen oder ablehnen; automatische Zusatzarbeiten (Regel mit Zuordnung automatisch) abwählen
(Ablehnen) oder fest übernehmen (Annehmen).

Seit 04.11.2026 (Patrick: Zusatzarbeiten bei allen Teilen bestätigen oder ablehnen): zuerst nur die offenen Punkte
(Vorschläge, automatische, abgelehnte, zu prüfende), nach Arbeitsgang sortiert; „Alle Arbeitsgänge zeigen“ blendet die
gerechneten dazu. Mehrere Zeilen markierbar, die Knöpfe wirken auf alle markierten; „Alle … annehmen/ablehnen“ wirkt
auf jede Position mit demselben Vorschlag."""
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import arbeitsgaenge as ag, stil
from .rechnen import zahl

FARBE = {ag.VORSCHLAG: "#FFF6DB", ag.ABGELEHNT: "#F2F2F2", ag.ZU_PRUEFEN: "#FDECEA", ag.AUTOMATISCH: "#FFF6DB"}
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
        self.tabelle.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.alle_zeigen = QCheckBox("Alle Arbeitsgänge zeigen (auch die gerechneten)")
        self.alle_zeigen.toggled.connect(lambda _: self.laden())
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
        self.alle_ja_knopf = QPushButton()
        self.alle_nein_knopf = QPushButton()
        self.alle_ja_knopf.clicked.connect(lambda: self.alle_gleichen(True))
        self.alle_nein_knopf.clicked.connect(lambda: self.alle_gleichen(False))
        self.annehmen_knopf.clicked.connect(lambda: self.ausfuehren("annehmen"))
        self.ablehnen_knopf.clicked.connect(lambda: self.ausfuehren("ablehnen"))
        self.zurueck_knopf.clicked.connect(lambda: self.ausfuehren("zurueck"))
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        for b in (self.annehmen_knopf, self.ablehnen_knopf, self.zurueck_knopf, self.alle_ja_knopf,
                  self.alle_nein_knopf):
            kn.addWidget(b)
        kn.addStretch(1)
        kn.addWidget(zu)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(self.alle_zeigen)
        lay.addWidget(self.tabelle, 1)
        lay.addLayout(kn)
        self.laden()

    def laden(self):
        alle = self.seite.arbeitsgaenge_zeilen()
        self.alle_zeilen = alle
        if self.alle_zeigen.isChecked():
            self.zeilen = alle
        else:               # nur offene Punkte, gleiche Arbeitsgänge untereinander
            offen = [z for z in alle if z["status"] != ag.IM_ANGEBOT]
            reihe = {}
            for z in offen:
                reihe.setdefault(z["arbeitsgang"], len(reihe))
            self.zeilen = sorted(offen, key=lambda z: reihe[z["arbeitsgang"]])
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
                    it.setBackground(QBrush(stil.farbe(FARBE[z["status"]])))
                t.setItem(r, c, it)
        s = ag.summen(alle)
        n_v = sum(1 for z in alle if z["status"] == ag.VORSCHLAG)
        self.info.setText(
            "Gerechnet werden Arbeitsgänge „im Angebot“ und „automatisch“ (Gewinde, Zusatzarbeiten je Teil: "
            + (", ".join(f"{k} {zahl(v)} €" for k, v in s[ag.IM_ANGEBOT].items()) or "keine") + "). "
            + (f"{n_v} Vorschlag/Vorschläge der Arbeitsgang-Regeln, voraussichtlich je Teil "
               + ", ".join(f"{k} {zahl(v)} €" for k, v in s[ag.VORSCHLAG].items())
               + " – erst nach „Annehmen“ im Preis." if n_v else "Keine offenen Vorschläge."))
        self._knoepfe()

    def markiert(self):
        r = self.tabelle.currentRow()
        return self.zeilen[r] if 0 <= r < len(self.zeilen) and self.tabelle.selectedItems() else None

    def alle_markierten(self):
        """Markierte Zeilen (mehrere möglich); ohne Markierung die aktuelle."""
        rs = sorted({i.row() for i in self.tabelle.selectedIndexes()})
        return [self.zeilen[r] for r in rs if r < len(self.zeilen)]

    def gleiche(self, z=None):
        """Offene Vorschläge desselben Arbeitsgangs wie z (bzw. die markierte Zeile) in allen Positionen."""
        z = z or self.markiert()
        if not z or z["status"] != ag.VORSCHLAG:
            return []
        return [x for x in self.alle_zeilen if x["arbeitsgang"] == z["arbeitsgang"] and x["status"] == ag.VORSCHLAG]

    def _knoepfe(self):
        z = self.markiert()
        st = {x["status"] for x in self.alle_markierten()} or ({z["status"]} if z else set())
        schreibbar = not self.seite.db.nur_lesen
        self.annehmen_knopf.setEnabled(schreibbar and bool(st & {ag.VORSCHLAG, ag.ABGELEHNT, ag.AUTOMATISCH}))
        self.ablehnen_knopf.setEnabled(schreibbar and bool(st & {ag.VORSCHLAG, ag.AUTOMATISCH}))
        self.ablehnen_knopf.setText("Abwählen" if st == {ag.AUTOMATISCH} else "Ablehnen")
        self.zurueck_knopf.setEnabled(schreibbar and ag.ABGELEHNT in st)
        g = self.gleiche(z)
        for b, text in ((self.alle_ja_knopf, "annehmen"), (self.alle_nein_knopf, "ablehnen")):
            b.setVisible(len(g) > 1)
            b.setEnabled(schreibbar)
            if g:
                b.setText(f"Alle {len(g)} „{z['arbeitsgang']}“ {text}")

    def waehlen(self, position_id, arbeitsgang):
        """Zeile markieren (Tests)."""
        r = next(i for i, z in enumerate(self.zeilen)
                 if z["position_id"] == position_id and z["arbeitsgang"] == arbeitsgang)
        self.tabelle.selectRow(r)
        self.tabelle.setCurrentCell(r, 0)
        return self.zeilen[r]

    def _eine(self, z, was):
        name = z.get("name") or z["arbeitsgang"]       # erkannte mit RAL-Farbe: „Pulverbeschichten RAL 7016“
        if was == "annehmen":
            if z["status"] not in (ag.VORSCHLAG, ag.ABGELEHNT, ag.AUTOMATISCH):
                return False
            return self.seite.arbeitsgang_annehmen(z["position_id"], name)
        if was == "ablehnen" and z["status"] not in (ag.VORSCHLAG, ag.AUTOMATISCH) or \
                was == "zurueck" and z["status"] != ag.ABGELEHNT:
            return False
        return self.seite.arbeitsgang_ablehnen(z["position_id"], name, zurueck=was == "zurueck")

    def ausfuehren(self, was, zeilen=None):
        """Annehmen/Ablehnen/Zurücknehmen für die markierten Zeilen (bzw. zeilen). Ergebnis: True, wenn mindestens
        eine Zeile geändert wurde."""
        zeilen = zeilen if zeilen is not None else (self.alle_markierten() or
                                                    ([self.markiert()] if self.markiert() else []))
        ok = False
        for z in zeilen:
            ok = self._eine(z, was) or ok
        self.laden()
        return ok

    def alle_gleichen(self, ja, z=None):
        """Denselben Vorschlag in allen Positionen annehmen (ja) bzw. ablehnen. Ergebnis: Anzahl."""
        g = self.gleiche(z)
        if not g:
            return 0
        self.ausfuehren("annehmen" if ja else "ablehnen", g)
        return len(g)
