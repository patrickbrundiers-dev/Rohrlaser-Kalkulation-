"""Abwicklung als eigenes Fenster im Teile-Editor (Patrick 25.10.2026): Knopf „Abwicklung“ oben rechts im Menüband
öffnet sie groß in einem Fenster, Esc schließt nur dieses Fenster, der Editor bleibt offen.

Rohr: Skizze im Modus Abwicklung (Umfang aufgerollt, Konturen ausgeschnitten), Blech: Zuschnitt mit Biegelinien.
Die Abwicklung folgt jeder Eingabe; Klick wählt die Kontur, Ziehen verschiebt sie wie in der Skizze des Editors.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from . import skizze_widget


class AbwicklungFenster(QDialog):
    """Nicht modales Fenster mit der Abwicklung des Teils; rahmen ist der EditorRahmen."""
    geschlossen = Signal()

    def __init__(self, rahmen):
        d = rahmen.d
        super().__init__(d)
        self.r = rahmen
        self.setWindowTitle("Abwicklung")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        lay = QVBoxLayout(self)
        if rahmen.art == "rohr":
            self.bild = skizze_widget.Skizze(d.skizze.profil, d.skizze.laenge)
            self.bild.modus = skizze_widget.ABWICKLUNG
            self.bild.gewaehlt.connect(d._auswahl_skizze)
            self.bild.verschoben.connect(d._verschoben)
        else:
            from .blech_dialog import BlechSkizze
            self.bild = BlechSkizze()
            self.bild.gewaehlt.connect(rahmen.waehlen)
            self.bild.geaendert.connect(d.skizze_geaendert)
        self.bild.setToolTip("Abwicklung des Teils: Klick wählt eine Kontur, Ziehen verschiebt sie; Mausrad zoomt, "
                             "Doppelklick passt ein. Esc schließt das Fenster, der Editor bleibt offen.")
        lay.addWidget(self.bild, 1)
        hinweis = QLabel("Esc schließt dieses Fenster, der Editor bleibt offen.")
        hinweis.setStyleSheet("color: #5F6B7A;")
        lay.addWidget(hinweis)
        g = d.geometry()
        self.resize(max(700, int(g.width() * 0.8)), max(420, int(g.height() * 0.6)))

    def auffrischen(self):
        """Stand der Skizze des Editors übernehmen (Eingaben, Ergebnis, Profil, Länge, Markierung)."""
        quelle, b = self.r.d.skizze, self.bild
        if self.r.art == "rohr":
            neu_profil = b.profil is not quelle.profil
            b.profil, b.qs, b.laenge = quelle.profil, quelle.qs, quelle.laenge
            b.naht, b.grenze = quelle.naht, quelle.grenze
            b.markiert = quelle.markiert
            b.zeigen(quelle.eingaben, quelle.ergebnis)
            if neu_profil:
                b.einpassen()
        else:
            b.markiert = quelle.markiert
            b.setzen(quelle.eingaben, quelle.zuschnitt)

    def showEvent(self, e):
        super().showEvent(e)
        self.auffrischen()

    def closeEvent(self, e):
        super().closeEvent(e)
        self.geschlossen.emit()

    def done(self, r):              # Esc (reject) schließt nur dieses Fenster
        super().done(r)
        self.geschlossen.emit()
