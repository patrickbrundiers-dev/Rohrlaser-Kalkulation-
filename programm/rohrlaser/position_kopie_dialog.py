"""Fenster „Positionen aus anderem Angebot übernehmen“ (Patrick 30.10.2026, position_kopie.py): links die Angebote
(Suche nach Nummer, Kunde, Artikel oder Bezeichnung; auch Angebote der Kollegen und festgeschriebene, sie werden nur
gelesen), rechts ihre Positionen wie in der Positionsliste (Baugruppe mit eingerückten Teilen, Satz zusammen).
Mehrere Positionen lassen sich markieren (Strg/Umschalt), die erste Zeile einer Baugruppe bzw. eines Satzes nimmt
die ganze Gruppe mit. Nach „Übernehmen“: self.quelle (Angebots-ID), self.zeilen (Indizes der Positionen),
self.staffeln (Staffeln mitkopieren)."""
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import position_kopie, reihenfolge, satzgruppen
from .angebot import ist_baugruppe

ANGEBOT_SPALTEN = ("Nummer", "Kunde", "Datum", "Pos.")
POS_SPALTEN = ("Pos.", "Artikel", "Bezeichnung", "Profil / Art", "Länge", "Stück", "Gruppe")


def _z(w):
    if isinstance(w, float) and w.is_integer():
        w = int(w)
    return "" if w is None else str(w)


def zeilen_text(positionen):
    """Zeilen der Positionstabelle in der Reihenfolge der Positionsliste: [(Index, [Spaltentexte])]."""
    out = []
    for gruppe, ix in reihenfolge.bloecke(positionen):
        for k, i in enumerate(ix):
            p = positionen[i]
            art = "Schweißbaugruppe" if ist_baugruppe(p) else (p.get("profil_id") or
                                                               ("Zukaufteil" if p.get("zukauf") else ""))
            if gruppe and gruppe[0] == "bg":
                grp = "Baugruppe mit Teilen" if k == 0 else "  └ Teil der Baugruppe"
            elif gruppe:
                grp = f"Satz {satzgruppen.name(p)}" + (" (ganzer Satz)" if k == 0 else "")
            else:
                grp = ""
            einr = "    " if gruppe and gruppe[0] == "bg" and k else ""
            out.append((i, [_z(p.get("pos")), einr + _z(p.get("artikel")), _z(p.get("bezeichnung")), art,
                            _z(p.get("laenge")), _z(p.get("stueck")), grp]))
    return out


class UebernehmenDialog(QDialog):
    def __init__(self, parent, db, angebot_id):
        super().__init__(parent)
        self.db, self.ziel = db, angebot_id
        self.quelle, self.zeilen, self.staffeln = None, [], True
        self.positionen, self._ix = [], []
        self.setWindowTitle("Positionen aus anderem Angebot übernehmen")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Angebot wählen, dann die Positionen markieren (Strg/Umschalt für mehrere). Die erste "
                             "Zeile einer Schweißbaugruppe bzw. eines Satzes übernimmt die ganze Gruppe. Das andere "
                             "Angebot bleibt unverändert, die Kopien kommen ans Ende und werden neu kalkuliert."))
        lay.itemAt(0).widget().setWordWrap(True)
        teiler = QSplitter(Qt.Horizontal)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Nummer, Kunde, Artikel, Bezeichnung …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.angebote_laden)
        ll.addWidget(self.suche)
        self.angebote = QTableWidget(0, len(ANGEBOT_SPALTEN))
        self.angebote.setHorizontalHeaderLabels(ANGEBOT_SPALTEN)
        self.angebote.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.angebote.setSelectionMode(QAbstractItemView.SingleSelection)
        self.angebote.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.angebote.verticalHeader().hide()
        self.angebote.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.angebote.itemSelectionChanged.connect(self._angebot_gewaehlt)
        ll.addWidget(self.angebote)
        teiler.addWidget(links)
        self.pos = QTableWidget(0, len(POS_SPALTEN))
        self.pos.setHorizontalHeaderLabels(POS_SPALTEN)
        self.pos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pos.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.pos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pos.verticalHeader().hide()
        self.pos.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.pos.itemSelectionChanged.connect(self._anzeigen)
        teiler.addWidget(self.pos)
        teiler.setSizes([380, 620])
        lay.addWidget(teiler, 1)
        unten = QHBoxLayout()
        self.staffel_haken = QCheckBox("Staffeln der Positionen mitkopieren")
        self.staffel_haken.setChecked(True)
        unten.addWidget(self.staffel_haken)
        unten.addStretch(1)
        self.info = QLabel("")
        unten.addWidget(self.info)
        lay.addLayout(unten)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        self.knoepfe.accepted.connect(self._ok)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        self.resize(1050, 560)
        self._liste = []
        self.angebote_laden()

    def angebote_laden(self, *_):
        self._liste = [a for a in self.db.angebote(self.suche.text().strip()) if a["id"] != self.ziel
                       and a.get("positionen")]
        self.angebote.setRowCount(len(self._liste))
        for r, a in enumerate(self._liste):
            kunde = a.get("kunde") or a.get("kundennr") or ""
            if a.get("fremd"):
                kunde += f"  ({a['fremd']})"
            for c, t in enumerate((a.get("nummer") or str(a["id"]), kunde, a.get("datum") or "",
                                   _z(a.get("positionen")))):
                self.angebote.setItem(r, c, QTableWidgetItem(t))
        self.angebote.resizeColumnToContents(0)
        if self._liste:
            self.angebote.selectRow(0)
        else:
            self._angebot_gewaehlt()

    def angebot_waehlen(self, angebot_id):
        r = next((k for k, a in enumerate(self._liste) if a["id"] == angebot_id), None)
        if r is not None:
            self.angebote.selectRow(r)
        return r is not None

    def _angebot_gewaehlt(self):
        r = self.angebote.currentRow()
        self.quelle = self._liste[r]["id"] if 0 <= r < len(self._liste) and self.angebote.selectedItems() else None
        self.positionen = self.db.positionen(self.quelle) if self.quelle else []
        zeilen = zeilen_text(self.positionen)
        self._ix = [i for i, _ in zeilen]
        self.pos.setRowCount(len(zeilen))
        for r, (_, texte) in enumerate(zeilen):
            for c, t in enumerate(texte):
                self.pos.setItem(r, c, QTableWidgetItem(t))
        self.pos.resizeColumnsToContents()
        self.pos.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._anzeigen()

    def markieren(self, indizes):
        """Positionen (Indizes im gewählten Angebot) markieren."""
        self.pos.clearSelection()
        modus = self.pos.selectionModel()
        for r, i in enumerate(self._ix):
            if i in indizes:
                modus.select(self.pos.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def gewaehlt(self):
        return sorted({self._ix[i.row()] for i in self.pos.selectionModel().selectedRows() if i.row() < len(self._ix)})

    def _anzeigen(self):
        e = position_kopie.einheiten(self.positionen, self.gewaehlt())
        n = sum(len(ix) for _, ix in e)
        self.info.setText(f"{n} Position(en) werden übernommen" if n else "Keine Position markiert")
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(bool(n))

    def _ok(self):
        self.zeilen = self.gewaehlt()
        self.staffeln = self.staffel_haken.isChecked()
        if self.quelle and self.zeilen:
            self.accept()
