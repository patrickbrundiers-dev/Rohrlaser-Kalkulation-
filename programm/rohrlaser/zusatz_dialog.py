"""Dialog 'Zusatzarbeiten …' einer oder mehrerer Positionen: Gewinde (Anzahl x Größe) und Zusatzarbeiten
aus den Stammdaten (Verzinken, Pulverbeschichten, Gravur extra …) mit Menge, Preis bzw. Zeit und Text."""
import json

from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget, QVBoxLayout)

from . import rechnen
from .auftrag import POSITIONEN
from .stammdaten import ZUSATZ_EINHEIT, wert_aus_text, zahl_als_text, zahl_aus_text

SPALTEN = ("Zusatzarbeit", "Abrechnung", "Menge je Teil", "Preis [€] bzw. Zeit [s] je Einheit", "Text (z. B. RAL-Farbe)")


def _zahl(text, titel):
    t = text.strip()
    if not t:
        return None
    try:
        return zahl_aus_text(t)
    except ValueError:
        raise ValueError(f"{titel}: '{t}' ist keine Zahl.")


class ZusatzDialog(QDialog):
    """p: erste gewählte Position (für Vorgaben und automatische Mengen), anzahl: gewählte Positionen."""

    def __init__(self, parent, p, anzahl, k, tabellen):
        super().__init__(parent)
        self.p, self.k = p, k
        self.katalog = {z["name"]: z for z in tabellen.get("zusatzarbeiten") or () if z.get("name")}
        self.gewinde_tab = tabellen.get("gewinde") or []
        self.setWindowTitle("Zusatzarbeiten" + (f" für {anzahl} Positionen" if anzahl > 1 else
                                               f" Pos. {p.get('pos') or ''} {p.get('artikel') or ''}"))
        self.resize(900, 380)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.gewinde = QLineEdit(p.get("gewinde") or "")
        self.gewinde.setPlaceholderText("z. B. 4xM6; 2xM8")
        self.gewinde.textChanged.connect(self._gewinde_info)
        self.gewinde_info = QLabel()
        self.gewinde_info.setStyleSheet("color: #595959;")
        form.addRow("Gewinde (geprüft)", self.gewinde)
        form.addRow("", self.gewinde_info)
        lay.addLayout(form)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        kopf = self.tabelle.horizontalHeader()
        for i, b in enumerate((180, 80, 150, 190)):
            self.tabelle.setColumnWidth(i, b)
        kopf.setSectionResizeMode(4, QHeaderView.Stretch)
        lay.addWidget(self.tabelle, 1)
        leiste = QHBoxLayout()
        neu = QPushButton("Zusatzarbeit hinzufügen")
        neu.clicked.connect(lambda: self.zeile_neu())
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(self._entfernen)
        leiste.addWidget(neu)
        leiste.addWidget(weg)
        leiste.addStretch(1)
        lay.addLayout(leiste)
        text = ("Menge und Preis leer lassen = automatisch: Menge aus der Position (Gewicht, Außenfläche, Länge "
                "oder 1 Stück), Preis aus den Stammdaten. Abrechnung s/Stück: Zeit wird zur Schneidzeit addiert.")
        if anzahl > 1:
            text += (f" Gilt für alle {anzahl} markierten Positionen und ersetzt dort Gewinde und Zusatzarbeiten; "
                     "automatische Mengen rechnet jede Position selbst.")
        if not self.katalog:
            text += " In den Stammdaten (Reiter Zusatzarbeiten) ist noch keine Zusatzarbeit angelegt."
        hinweis = QLabel(text)
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #595959;")
        lay.addWidget(hinweis)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #C00000;")
        lay.addWidget(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        for e in rechnen.zusatz_liste(p):
            self.zeile_neu(e)
        self._gewinde_info()
        self.ergebnis = None

    # -------------------------------------------------------------- Zeilen
    def zeile_neu(self, e=None):
        e = e or {}
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        cb = QComboBox()
        namen = list(self.katalog)
        if e.get("name") and e["name"] not in self.katalog:
            namen.append(e["name"])
        cb.addItems(namen)
        if e.get("name"):
            cb.setCurrentText(e["name"])
        self.tabelle.setCellWidget(r, 0, cb)
        self.tabelle.setCellWidget(r, 1, QLabel())
        menge = QLineEdit(zahl_als_text(e.get("menge"), tausender=False) if e.get("menge") is not None else "")
        preis = QLineEdit(zahl_als_text(e.get("preis"), tausender=False) if e.get("preis") is not None else "")
        self.tabelle.setCellWidget(r, 2, menge)
        self.tabelle.setCellWidget(r, 3, preis)
        self.tabelle.setCellWidget(r, 4, QLineEdit(e.get("text") or ""))
        cb.currentTextChanged.connect(lambda _=None, cb=cb: self._vorgaben(cb))
        self._vorgaben(cb)
        return r

    def _zeile_von(self, widget):
        return next(r for r in range(self.tabelle.rowCount()) if self.tabelle.cellWidget(r, 0) is widget)

    def _vorgaben(self, cb):
        """Abrechnung und Vorgabewerte (grau) der gewählten Zusatzarbeit anzeigen."""
        r = self._zeile_von(cb)
        kz = self.katalog.get(cb.currentText())
        art = (kz or {}).get("art")
        self.tabelle.cellWidget(r, 1).setText(art or "unbekannt")
        auto = rechnen.zusatz_menge_auto(art, self.p, self.k) if art else None
        einheit = ZUSATZ_EINHEIT.get(art, "")
        self.tabelle.cellWidget(r, 2).setPlaceholderText(
            f"auto: {rechnen.zahl(auto, 3)} {einheit}" if auto is not None else f"{einheit} je Teil")
        einheit_preis = "s" if art == "s/Stück" else "€"
        self.tabelle.cellWidget(r, 3).setPlaceholderText(
            f"Stammdaten: {rechnen.zahl((kz or {}).get('preis'))} {einheit_preis}" if kz else "")

    def _entfernen(self):
        for r in sorted({i.row() for i in self.tabelle.selectedIndexes()}, reverse=True):
            self.tabelle.removeRow(r)

    def _gewinde_info(self):
        anz = {g: n for g, n in rechnen.gewinde_anzahl(self.gewinde.text(), self.gewinde_tab).items() if n}
        if not anz:
            self.gewinde_info.setText("Gewinde aus den Stammdaten; Festpreis je Gewinde, sonst Zeit × Stundensatz.")
            return
        preise = {g.get("gewinde"): g.get("preis") for g in self.gewinde_tab}
        teile = [f"{n:g} × {g} à {rechnen.zahl(preise[g])} €" if preise.get(g) is not None else f"{n:g} × {g} (Zeit)"
                 for g, n in anz.items()]
        self.gewinde_info.setText("Je Teil: " + ", ".join(teile)
                                  + f" = {rechnen.zahl(rechnen.gewinde_preis(self.gewinde.text(), self.gewinde_tab))} €")

    # -------------------------------------------------------------- Ergebnis
    def werte(self):
        """(Gewinde-Text oder None, Zusatzarbeiten als JSON-Text oder None). ValueError bei falscher Eingabe."""
        gewinde = wert_aus_text(POSITIONEN.feld("gewinde"), self.gewinde.text())
        liste = []
        for r in range(self.tabelle.rowCount()):
            name = self.tabelle.cellWidget(r, 0).currentText().strip()
            if not name:
                continue
            e = dict(name=name, menge=_zahl(self.tabelle.cellWidget(r, 2).text(), f"Zeile {r + 1}: Menge"),
                     preis=_zahl(self.tabelle.cellWidget(r, 3).text(), f"Zeile {r + 1}: Preis bzw. Zeit"),
                     text=self.tabelle.cellWidget(r, 4).text().strip() or None)
            for n in ("menge", "preis"):
                if e[n] is not None and e[n] < 0:
                    raise ValueError(f"Zeile {r + 1}: negative Werte sind nicht zulässig.")
            liste.append(e)
        return gewinde, (json.dumps(liste, ensure_ascii=False) if liste else None)

    def _ok(self):
        try:
            self.ergebnis = self.werte()
        except ValueError as e:
            self.fehler.setText(str(e))
            return
        self.accept()
