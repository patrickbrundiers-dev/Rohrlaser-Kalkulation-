"""Datei → „Maschinenauslastung …“ (auslastung.py, einlastung.py): dieselbe Seite wie Reiter Fertigung → Auslastung
(auslastung_ansicht.AuslastungAnsicht) als eigenes Fenster, auch wenn der Reiter Fertigung ausgeschaltet ist.

Wochenbalken je Maschine, Plantafel, Aufträge der gewählten Woche und die Zahlentabelle Bedarf / Kapazität (ab 80 %
gelb, über 100 % rot); Doppelklick öffnet das Angebot."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

from .auslastung_ansicht import FARBEN, AuslastungAnsicht  # noqa: F401  (FARBEN: bisherige Adresse)


class AuslastungDialog(QDialog):
    def __init__(self, fenster, heute=None):
        super().__init__(fenster)
        self.f, self.heute = fenster, heute
        self.setWindowTitle("Maschinenauslastung")
        self.resize(1320, 800)
        self.ansicht = AuslastungAnsicht(fenster, heute, self)
        self.ansicht.geoeffnet.connect(lambda _id: self.accept())
        # bisherige Namen (Tests, Anleitungsbilder)
        for name in ("wochen", "offene", "info", "tabelle", "details", "details_titel", "sicht", "balken", "tafel"):
            setattr(self, name, getattr(self.ansicht, name))
        knoepfe = QDialogButtonBox()
        knoepfe.addButton("Schließen", QDialogButtonBox.RejectRole)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.ansicht, 1)
        lay.addWidget(knoepfe)
        self.laden()

    @property
    def daten(self):
        return self.ansicht.daten

    def laden(self):
        self.ansicht.laden()
