"""Stückzahl mehrerer Positionen auf einmal ändern (Plan Arbeitsabläufe W4): × Faktor oder = fester Wert.

Gilt für die markierten Positionen, ohne Markierung für alle aktiven Positionen des Angebots. Mit Faktor wird
kaufmännisch gerundet (mindestens 1); Positionen ohne Stückzahl bleiben dann leer."""
import math

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QRadioButton

from .stammdaten import zahl_aus_text

STUECK_MAX = 100000         # wie das Feld Stückzahl (angebot.POSITIONEN)


def neue_stueckzahl(alt, faktor=None, wert=None):
    """Neue Stückzahl einer Position oder None (bleibt, wie sie ist)."""
    if wert is not None:
        return min(STUECK_MAX, max(1, int(wert)))
    try:
        alt = float(alt)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(alt) or alt <= 0 or not faktor or not math.isfinite(faktor) or faktor <= 0:
        return None
    return min(STUECK_MAX, max(1, int(alt * faktor + 0.5)))


class StueckDialog(QDialog):
    """Auswahl × Faktor oder = Stückzahl. Nach OK: self.faktor bzw. self.wert (das andere ist None)."""

    def __init__(self, parent, anzahl, alle):
        super().__init__(parent)
        self.setWindowTitle("Stückzahl ändern")
        self.faktor = self.wert = None
        form = QFormLayout(self)
        form.addRow(QLabel(f"<b>{anzahl} Position(en)</b>" + (" (alle, keine markiert)" if alle else " (markiert)")))
        self.mal = QRadioButton("Stückzahl × Faktor")
        self.gleich = QRadioButton("Stückzahl =")
        self.mal.setChecked(True)
        self.faktor_feld, self.wert_feld = QLineEdit("2"), QLineEdit()
        self.faktor_feld.setPlaceholderText("z. B. 2 oder 0,5")
        self.wert_feld.setPlaceholderText("z. B. 50")
        self.faktor_feld.textEdited.connect(lambda _: self.mal.setChecked(True))
        self.wert_feld.textEdited.connect(lambda _: self.gleich.setChecked(True))
        form.addRow(self.mal, self.faktor_feld)
        form.addRow(self.gleich, self.wert_feld)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #B42318;")
        form.addRow(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)
        self.faktor_feld.selectAll()

    def accept(self):
        feld = self.faktor_feld if self.mal.isChecked() else self.wert_feld
        try:
            w = zahl_aus_text(feld.text().strip())
        except ValueError:
            w = None
        if w is None or not math.isfinite(w) or w <= 0 or (self.gleich.isChecked() and w != int(w)):
            self.fehler.setText("Bitte eine Zahl größer 0 eingeben" + (" (ganze Zahl)." if self.gleich.isChecked()
                                                                        else "."))
            return
        self.faktor, self.wert = (w, None) if self.mal.isChecked() else (None, int(w))
        super().accept()
