"""Fenster „Als Satz zusammenfassen“ (umwandeln.py, Patrick 06.11.2026, F1a): Name und Anzahl Sätze für die markierten
Einzelteile, darunter je Position Stückzahl und Stück je Satz. Die Stückzahlen bleiben; OK nur, wenn jede Stückzahl
ganz auf die Anzahl Sätze aufgeht."""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from . import umwandeln
from .baugruppe_dialog import FEHLER_FARBE


class SatzBildenDialog(QDialog):
    def __init__(self, parent, positionen, zeilen):
        super().__init__(parent)
        self.positionen, self.zeilen = positionen, sorted(set(zeilen))
        self.name, self.saetze = None, None
        self.setWindowTitle("Als Satz zusammenfassen")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        info = QLabel("Die markierten Einzelteile werden ein Satz. Die Stückzahlen bleiben, Stück je Satz = "
                      "Stückzahl ÷ Anzahl Sätze. Zurück mit Rechtsklick → „Satz auflösen“.")
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        self.name_feld = QLineEdit(umwandeln.satz_name_vorschlag(positionen))
        self.saetze_feld = QSpinBox()
        self.saetze_feld.setRange(1, 1000000)
        self.saetze_feld.setValue(umwandeln.saetze_vorschlag(positionen, self.zeilen))
        self.saetze_feld.setToolTip("Vorschlag: größter gemeinsamer Teiler der Stückzahlen")
        form.addRow("Name des Satzes", self.name_feld)
        form.addRow("Anzahl Sätze", self.saetze_feld)
        lay.addLayout(form)
        self.tabelle = QTableWidget(len(self.zeilen), 4)
        self.tabelle.setHorizontalHeaderLabels(["Pos.", "Artikel", "Stückzahl", "Stück je Satz"])
        self.tabelle.verticalHeader().hide()
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tabelle)
        self.fehler = QLabel()
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(f"color: {FEHLER_FARBE}")
        lay.addWidget(self.fehler)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.accepted.connect(self._ok)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        self.name_feld.textChanged.connect(self._auffrischen)
        self.saetze_feld.valueChanged.connect(self._auffrischen)
        self._auffrischen()

    def _auffrischen(self):
        n = self.saetze_feld.value()
        for r, z in enumerate(self.zeilen):
            p = self.positionen[z]
            st = p.get("stueck")
            je = (f"{int(st) // n}" if isinstance(st, (int, float)) and st >= 1 and int(st) % n == 0 and st == int(st)
                  else "geht nicht auf")
            for c, t in enumerate((p.get("pos"), p.get("artikel") or p.get("bezeichnung"), st, je)):
                self.tabelle.setItem(r, c, QTableWidgetItem("" if t is None else str(t)))
        f = umwandeln.satz_bilden_pruefen(self.positionen, self.zeilen, self.name_feld.text(), n)
        self.fehler.setText(f or "")
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(not f)
        return f

    def _ok(self):
        if self._auffrischen():
            return
        self.name, self.saetze = self.name_feld.text().strip(), self.saetze_feld.value()
        self.accept()


def knoepfe_einbauen(d, knoepfe, eintraege, aktiv=True):
    """Knöpfe zum Umwandeln in einem Editor (Satz in 3D, Satz bearbeiten, Schweißbaugruppe; Regel „Schritte in alle
    Editoren“): eintraege [(Text, Ziel, Tooltip)]. Ein Klick speichert wie OK und merkt d.umwandeln = Ziel; das
    Angebot wandelt danach um (AngebotSeite._nach_editor_umwandeln). Ergebnis: {Ziel: Knopf}."""
    from PySide6.QtWidgets import QPushButton
    d.umwandeln = None
    out = {}

    def klick(ziel):
        d.umwandeln = ziel
        getattr(d, "_ok", d.accept)()
        if d.result() != QDialog.Accepted:      # Eingaben unvollständig: Editor bleibt offen, nichts umwandeln
            d.umwandeln = None
    for text, ziel, tipp in eintraege:
        b = QPushButton(text)
        b.setToolTip(tipp)
        b.setEnabled(aktiv)
        b.clicked.connect(lambda _=False, z=ziel: klick(z))
        knoepfe.addButton(b, QDialogButtonBox.ActionRole)
        out[ziel] = b
    return out
