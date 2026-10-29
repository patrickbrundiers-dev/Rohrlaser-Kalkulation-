"""Häkchen „Muster“ für alle Editoren (Rohr-, Blech- und Baugruppen-Editor; Patrick 28.10.2026, Plan „Musterteile im
Angebot“): ein Musterteil wird voll gerechnet, steht aber ohne eigenen Preis im Angebot, seine Kosten gehen mit
Gewinn auf die Serie (rechnen._muster_umlegen)."""
from PySide6.QtWidgets import QCheckBox

from . import funktionen
from .angebot import ist_muster

TEXT = "Muster"
HILFE = ("Musterteil: wird voll gerechnet (eigener Lauf, Material nach Länge, eigenes Rüsten, Programmierung), "
         "steht aber mit 0 € im Angebot. Die Kosten mit Gewinn gehen auf die Serienpositionen bzw. als "
         "„Musterkosten einmalig“ in eine eigene Zeile (Angebotskopf).")


def wert(an):
    """Spaltenwert der Position: 'ja' oder None (Serienteil)."""
    return "ja" if an else None


class MusterHaken(QCheckBox):
    """Häkchen mit dem Stand der Position p; geaendert() liefert {'muster': …} nur, wenn es umgeschaltet wurde."""

    def __init__(self, p=None, parent=None):
        super().__init__(TEXT, parent)
        self.setToolTip(HILFE)
        self.start = ist_muster(p)
        self.setChecked(self.start)
        if not self.start and not funktionen.an("funktion_muster"):      # Funktion Musterteile ausgeschaltet
            self.hide()

    def wert(self):
        return wert(self.isChecked())

    def geaendert(self):
        return {} if self.isChecked() == self.start else {"muster": self.wert()}
