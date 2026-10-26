"""Stangen von Hand vorgeben (Patrick 26.10.2026: „Für die Verschachtelung eine Option: manuell Stangenlänge und die
Stückzahl zu der Länge, mehrere Längen eintragbar“): je Abmessung eine Liste Länge [mm] × Stück, z. B. 3 × 6.000 und
2 × 4.500. Die Optimierung plant dann nur mit diesen Stangen (optimierung.vorrat_planen); was nicht mehr passt,
steht unter „nicht eingeplant“. Leere Liste = wieder beliebig viele Stangen der Lieferlänge.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import hilfe, optimierung as opt
from .stammdaten import zahl_als_text, zahl_aus_text

MIN_LAENGE = 500


def _z(w):
    return zahl_als_text(w, 0)


class VorgabeDialog(QDialog):
    """Vorgegebene Stangen einer Abmessung. vorrat = [(Länge, Anzahl)] bisher, max_laenge = max. Stangenlänge der
    Maschine (None = ohne Grenze), titel = Abmessung für die Überschrift. Nach 'Übernehmen': self.vorrat =
    [[Länge, Anzahl], …] (längste zuerst, [] = keine Vorgabe)."""

    def __init__(self, parent, titel, vorrat=None, max_laenge=None, standard=None):
        super().__init__(parent)
        self.max_laenge, self.vorrat = max_laenge, None
        self.setWindowTitle(f"Stangen vorgeben – {titel}")
        self.resize(460, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(hilfe.Hinweis(
            "Welche Stangen für diese Abmessung da sind: je Zeile eine Länge und wie viele Stangen dieser Länge. Die "
            "Optimierung nutzt dann genau diese Stangen (möglichst wenig Stangenlänge) statt beliebig vieler Stangen "
            "der Lieferlänge. Teile, die nicht mehr auf die Stangen passen, stehen unter 'nicht eingeplant'. Alle "
            "Zeilen leer = keine Vorgabe.", schluessel="stangen_vorgabe"))
        self.tabelle = QTableWidget(0, 2)
        self.tabelle.setHorizontalHeaderLabels(["Länge [mm]", "Stück"])
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.setColumnWidth(0, 160)
        for laenge, n in vorrat or ():
            self.zeile_neu(laenge, n)
        if not vorrat:
            self.zeile_neu(standard, None)
        lay.addWidget(self.tabelle, 1)
        reihe = QHBoxLayout()
        for text, f in (("Zeile hinzufügen", lambda: self.zeile_neu()), ("Zeile entfernen", self.zeile_weg),
                        ("Vorgabe aufheben", self.leeren)):
            k = QPushButton(text)
            k.clicked.connect(f)
            reihe.addWidget(k)
        reihe.addStretch(1)
        lay.addLayout(reihe)
        self.summe = QLabel()
        lay.addWidget(self.summe)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #C00000;")
        self.fehler.setWordWrap(True)
        lay.addWidget(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.annehmen)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.tabelle.itemChanged.connect(lambda _: self._summe())
        self._summe()

    def zeile_neu(self, laenge=None, anzahl=None):
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        for c, w in enumerate((laenge, anzahl)):
            it = QTableWidgetItem("" if w is None else _z(w))
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabelle.setItem(r, c, it)
        self.tabelle.setCurrentCell(r, 0)
        return r

    def zeile_weg(self):
        r = self.tabelle.currentRow()
        if r >= 0:
            self.tabelle.removeRow(r)
        self._summe()

    def leeren(self):
        self.tabelle.setRowCount(0)
        self._summe()

    def setzen(self, zeilen):
        """Zeilen [(Länge-Text, Stück-Text)] eintragen (Tests, Bildschirmfotos)."""
        self.leeren()
        for laenge, n in zeilen:
            r = self.zeile_neu()
            self.tabelle.item(r, 0).setText(str(laenge))
            self.tabelle.item(r, 1).setText(str(n))

    def werte(self):
        """[[Länge, Anzahl], …] (längste zuerst, gleiche Längen zusammengefasst); ValueError bei ungültiger Zeile."""
        out = []
        for r in range(self.tabelle.rowCount()):
            texte = [(self.tabelle.item(r, c).text() if self.tabelle.item(r, c) else "").strip() for c in (0, 1)]
            if not any(texte):
                continue
            try:
                laenge, n = (zahl_aus_text(t) for t in texte)
            except ValueError:
                raise ValueError(f"Zeile {r + 1}: Länge und Stückzahl als Zahl eintragen.") from None
            if not MIN_LAENGE <= laenge <= (self.max_laenge or 20000):
                raise ValueError(f"Zeile {r + 1}: Länge zwischen {_z(MIN_LAENGE)} und {_z(self.max_laenge or 20000)} "
                                 "mm eintragen" + (" (max. Stangenlänge der Maschine)." if self.max_laenge else "."))
            if n < 1 or n != int(n):
                raise ValueError(f"Zeile {r + 1}: Stückzahl als ganze Zahl ab 1 eintragen.")
            out.append([int(round(laenge)), int(n)])
        return [list(x) for x in opt.vorrat_lesen(out)]

    def _summe(self):
        try:
            v = self.werte()
        except ValueError:
            self.summe.setText("")
            return
        self.summe.setText(f"{sum(n for _, n in v)} Stangen, {zahl_als_text(sum(l * n for l, n in v) / 1000, 1)} m"
                           if v else "Keine Vorgabe: beliebig viele Stangen der Lieferlänge.")

    def annehmen(self):
        try:
            self.vorrat = self.werte()
        except ValueError as e:
            self.fehler.setText(str(e))
            return
        self.accept()
