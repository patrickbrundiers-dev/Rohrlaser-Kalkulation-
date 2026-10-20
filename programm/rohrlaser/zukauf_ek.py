"""Dialog 'EK eintragen …' im Angebot: Einkaufspreise der Zukaufteile (z. B. Bleche aus dem STEP-Import ohne EK)
direkt im Angebot eintragen. Der Preis wird im Zukaufartikel beim Lieferanten des Preisstands als Staffelzeile
'ab Stückzahl' gespeichert (Stückzahl = Verbrauch der Position) und die Position bekommt den neuen Preisstand."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from . import zukauf
from .stammdaten import zahl_als_text, zahl_aus_text

SPALTEN = ("Pos.", "Artikel", "Lieferant", "Stückzahl", "EK bisher", "EK je Stück [€]")
EK = 5


def zeilen(positionen, nur_fehlend=False):
    """[{zeile, nr, pos, artikel_id, bezeichnung, lieferant, menge, ek}] je Zukaufteil der Positionen; menge =
    Verbrauch der Position (Menge × Stückzahl bzw. Sätze), ek = bisheriger EK je Einheit oder None."""
    out = []
    for r, p in positionen:
        for n, e in enumerate(zukauf.json_liste(p.get("zukauf"))):
            if e.get("artikel_id") is None:
                continue
            st = e.get("stand") or {}
            bezug = st.get("bezug") or {}
            menge = (zukauf.dez(e.get("menge")) or 0) * (zukauf.dez(zukauf.bezugsmenge(e, p)) or 0)
            ek = None
            if menge:
                ek, _ = zukauf.ek_je_einheit(bezug, menge)
            if ek is not None and ek <= 0:
                ek = None
            if nur_fehlend and ek is not None:
                continue
            out.append(dict(zeile=r, nr=n, pos=p.get("pos"), artikel_id=e["artikel_id"],
                            bezeichnung=st.get("bezeichnung") or "?", lieferant=bezug.get("lieferant"),
                            menge=menge, ek=ek))
    return out


class EkDialog(QDialog):
    """Tabelle der Zukaufteile; ergebnis: [(Eintrag aus zeilen(), Preis)] der Zeilen mit eingetragenem EK."""

    def __init__(self, parent, liste):
        super().__init__(parent)
        self.liste = liste
        self.ergebnis = []
        self.setWindowTitle("EK eintragen")
        self.resize(820, 320)
        lay = QVBoxLayout(self)
        text = QLabel("Einkaufspreis netto je Stück eintragen. Er wird im Zukaufartikel beim Lieferanten als Preis ab "
                      "dieser Stückzahl gespeichert; das Angebot rechnet sofort damit. Leere Zeilen bleiben unverändert.")
        text.setWordWrap(True)
        lay.addWidget(text)
        self.tabelle = QTableWidget(len(liste), len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setVisible(False)
        for i, b in enumerate((50, 260, 120, 80, 90)):
            self.tabelle.setColumnWidth(i, b)
        self.tabelle.horizontalHeader().setSectionResizeMode(EK, QHeaderView.Stretch)
        for r, z in enumerate(liste):
            werte = (zahl_als_text(z["pos"], 0) if isinstance(z["pos"], (int, float)) else str(z["pos"] or ""),
                     z["bezeichnung"], z["lieferant"] or "",
                     zahl_als_text(float(z["menge"]), 0) if z["menge"] else "",
                     zahl_als_text(float(z["ek"]), 4 if z["ek"] < 1 else 2) + " €" if z["ek"] is not None else "fehlt",
                     "")
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c != EK:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c in (3, 4, 5):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(r, c, it)
        lay.addWidget(self.tabelle, 1)
        self.info = QLabel()
        self.info.setStyleSheet("color: #8C1D18;")
        lay.addWidget(self.info)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        if liste:
            self.tabelle.setCurrentCell(0, EK)

    def setzen(self, zeile, text):
        self.tabelle.item(zeile, EK).setText(text)

    def accept(self):
        out = []
        for r, z in enumerate(self.liste):
            t = self.tabelle.item(r, EK).text().strip().replace("€", "").strip()
            if not t:
                continue
            try:
                w = zahl_aus_text(t)
            except ValueError:
                self.info.setText(f"Zeile {r + 1}: '{t}' ist keine Zahl.")
                return
            if w <= 0:
                self.info.setText(f"Zeile {r + 1}: Der Einkaufspreis muss über 0 € liegen.")
                return
            if not z["menge"]:
                self.info.setText(f"Zeile {r + 1}: Die Position hat keine Stückzahl.")
                return
            out.append((z, w))
        if not out:
            self.info.setText("Bitte mindestens einen Einkaufspreis eintragen.")
            return
        self.ergebnis = out
        super().accept()
