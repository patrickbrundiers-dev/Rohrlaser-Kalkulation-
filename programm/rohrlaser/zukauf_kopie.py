"""Zukaufartikel aus einem anderen Angebot kopieren (Master-Auftrag Patrick 23.11.2026, Punkt 5): auch ohne zentrale
Zukaufartikelverwaltung lassen sich bereits verwendete Artikel wiederverwenden. Die Kopie ist vollständig unabhängig:
tiefe Kopie des Eintrags mit eigenem Preisstand, ohne zentrale Verwaltung auch ohne Verweis auf den Artikelstamm.
Spätere Änderungen im Ursprungsangebot ändern die Kopie nicht (und umgekehrt); das Ursprungsangebot wird nur gelesen.

eintraege() und kopie() ohne Qt; KopieDialog ist das Fenster im Dialog „Zukaufteile …“."""
import copy

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QLineEdit,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import zukauf
from .stammdaten import zahl_als_text

ANGEBOT_SPALTEN = ("Nummer", "Kunde", "Datum")
ARTIKEL_SPALTEN = ("Pos.", "Bezeichnung", "Menge", "Einheit", "EK [€/Einh.]", "Lieferant")


def eintraege(db, angebot_id):
    """Alle Zukaufartikel eines Angebots in Positionsreihenfolge: [dict(pos, artikel (der Position), eintrag)]."""
    out = []
    for p in db.positionen(angebot_id) or ():
        for e in zukauf.eintraege(p):
            out.append(dict(pos=p.get("pos"), artikel=p.get("artikel") or p.get("bezeichnung") or "", eintrag=e))
    return out


def kopie(e, herkunft=None, stamm=False):
    """Unabhängige Kopie eines Eintrags. stamm (zentrale Verwaltung an): Stammartikel behalten ihren Verweis (dann
    geht „Aus Stammdaten aktualisieren“), sonst wird die Kopie ein freier Eintrag mit gleichem Preisstand."""
    if stamm and e.get("artikel_id") is not None:
        k = copy.deepcopy(e)
        k.setdefault("stand", {})
        if herkunft:
            k["stand"]["kopiert_aus"] = herkunft
        return k
    return zukauf.unabhaengig(e, herkunft)


def _z(w):
    if isinstance(w, float) and w.is_integer():
        w = int(w)
    return "" if w is None else str(w)


class KopieDialog(QDialog):
    """Links die Angebote (Suche), rechts deren Zukaufartikel (mehrere markieren). Nach OK: quelle (Angebots-ID),
    auswahl (Indizes in eintraege())."""

    def __init__(self, parent, db, ziel=None):
        super().__init__(parent)
        self.db, self.ziel = db, ziel
        self.quelle, self.auswahl, self._liste, self._eintraege = None, [], [], []
        self.setWindowTitle("Zukaufartikel aus anderem Angebot kopieren")
        lay = QVBoxLayout(self)
        t = QLabel("Angebot wählen und die Zukaufartikel markieren (Strg/Umschalt für mehrere). Die Kopien sind "
                   "unabhängig: Bezeichnung, Menge und Preise lassen sich hier frei ändern, das andere Angebot bleibt "
                   "unverändert.")
        t.setWordWrap(True)
        lay.addWidget(t)
        teiler = QSplitter(Qt.Horizontal)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Nummer, Kunde, Artikel …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.angebote_laden)
        ll.addWidget(self.suche)
        self.angebote = self._tabelle(ANGEBOT_SPALTEN, 1, QAbstractItemView.SingleSelection)
        self.angebote.itemSelectionChanged.connect(self._angebot_gewaehlt)
        ll.addWidget(self.angebote)
        teiler.addWidget(links)
        self.artikel = self._tabelle(ARTIKEL_SPALTEN, 1, QAbstractItemView.ExtendedSelection)
        self.artikel.itemSelectionChanged.connect(self._anzeigen)
        teiler.addWidget(self.artikel)
        teiler.setSizes([340, 600])
        lay.addWidget(teiler, 1)
        self.info = QLabel("")
        lay.addWidget(self.info)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Kopieren")
        self.knoepfe.accepted.connect(self._ok)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        self.resize(980, 520)
        self.angebote_laden()

    @staticmethod
    def _tabelle(spalten, dehnen, modus):
        t = QTableWidget(0, len(spalten))
        t.setHorizontalHeaderLabels(spalten)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(modus)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().hide()
        t.horizontalHeader().setSectionResizeMode(dehnen, QHeaderView.Stretch)
        return t

    def angebote_laden(self, *_):
        self._liste = [a for a in self.db.angebote(self.suche.text().strip()) if a["id"] != self.ziel
                       and a.get("positionen")]
        self.angebote.setRowCount(len(self._liste))
        for r, a in enumerate(self._liste):
            for c, t in enumerate((a.get("nummer") or str(a["id"]), a.get("kunde") or a.get("kundennr") or "",
                                   a.get("datum") or "")):
                self.angebote.setItem(r, c, QTableWidgetItem(t))
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
        self._eintraege = eintraege(self.db, self.quelle) if self.quelle else []
        self.artikel.setRowCount(len(self._eintraege))
        for r, x in enumerate(self._eintraege):
            st = x["eintrag"].get("stand") or {}
            ek = zukauf.ek_einheit(st)
            for c, t in enumerate((_z(x["pos"]), st.get("bezeichnung") or st.get("artikelnr") or "?",
                                   _z(x["eintrag"].get("menge")), st.get("einheit") or "Stück",
                                   zahl_als_text(float(ek), 2) if ek is not None else "",
                                   (st.get("bezug") or {}).get("lieferant") or "")):
                self.artikel.setItem(r, c, QTableWidgetItem(t))
        self._anzeigen()

    def markieren(self, indizes):
        """Zukaufartikel (Indizes in eintraege()) markieren."""
        self.artikel.clearSelection()
        modell = self.artikel.selectionModel()
        for i in indizes:
            if i < self.artikel.rowCount():
                modell.select(self.artikel.model().index(i, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def gewaehlt(self):
        return sorted({i.row() for i in self.artikel.selectionModel().selectedRows()})

    def _anzeigen(self):
        n = len(self.gewaehlt())
        self.info.setText(f"{n} Zukaufartikel werden kopiert" if n else
                          ("Keine Zukaufartikel markiert" if self._eintraege else "Dieses Angebot hat keine "
                                                                                    "Zukaufartikel"))
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(bool(n))

    def _ok(self):
        self.auswahl = self.gewaehlt()
        if self.quelle is not None and self.auswahl:
            self.accept()
