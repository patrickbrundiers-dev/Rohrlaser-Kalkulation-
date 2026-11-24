"""Abwicklung als eigenes Fenster im Teile-Editor (Patrick 25.10.2026): Knopf „Abwicklung“ oben rechts im Menüband
öffnet sie groß in einem Fenster, Esc schließt nur dieses Fenster, der Editor bleibt offen.

Rohr: Skizze im Modus Abwicklung (Umfang aufgerollt, Konturen ausgeschnitten), Blech: Zuschnitt mit Biegelinien.
Die Abwicklung folgt jeder Eingabe; Klick wählt die Kontur, Ziehen verschiebt sie wie in der Skizze des Editors.
Seit 0.9.427 zeigt das Rohr die echte Außenhaut (Eckradien, abwicklung.Mantel) und lässt sich als DXF (Layer
AUSSENKONTUR, INNENKONTUR, KANTE, RADIUS, GRAVUR, BESCHRIFTUNG) und als PDF speichern.
"""
from PySide6.QtCore import QMarginsF, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from . import einblendung, skizze_widget


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
        unten = QHBoxLayout()
        hinweis = QLabel("Esc schließt dieses Fenster, der Editor bleibt offen.")
        hinweis.setStyleSheet("color: #5F6B7A;")
        unten.addWidget(hinweis, 1)
        self.gegenprobe = QLabel("")
        self.gegenprobe.setWordWrap(True)
        self.gegenprobe.hide()
        lay.addWidget(self.gegenprobe)
        if rahmen.art == "rohr":
            self.mit_mass = QCheckBox("Maße in der DXF")
            self.mit_mass.setChecked(True)
            self.mit_mass.setToolTip("Seitenbreiten, Umfang und je Kontur Kurztext mit Lage (x längs, t am Umfang) auf "
                                     "dem Layer BESCHRIFTUNG")
            k_dxf = QPushButton("DXF speichern …")
            k_dxf.setToolTip("Abwicklung der Außenhaut als DXF R12: Umriss, Konturen, Kanten, Radiuslinien, "
                             "Gravuren und Beschriftung je auf eigenem Layer")
            k_dxf.clicked.connect(lambda: self.dxf_speichern())
            k_pdf = QPushButton("PDF speichern …")
            k_pdf.setToolTip("Abwicklung wie gezeigt als PDF (A4 quer, Vektor)")
            k_pdf.clicked.connect(lambda: self.pdf_speichern())
            self.original = QCheckBox("Original (Import) zeigen")
            self.original.setToolTip("Konturen wie aus STEP/DXF importiert gestrichelt grau über die bearbeitete "
                                     "Abwicklung legen (Vergleich Original gegen bearbeitet)")
            self.original.toggled.connect(lambda _a: self.auffrischen())
            for w in (self.original, self.mit_mass, k_dxf, k_pdf):
                unten.addWidget(w)
        lay.addLayout(unten)
        g = d.geometry()
        self.resize(max(700, int(g.width() * 0.8)), max(420, int(g.height() * 0.6)))

    def auffrischen(self):
        """Stand der Skizze des Editors übernehmen (Eingaben, Ergebnis, Profil, Länge, Markierung)."""
        quelle, b = self.r.d.skizze, self.bild
        if self.r.art == "rohr":
            neu_profil = b.profil is not quelle.profil
            b.profil, b.qs, b.laenge = quelle.profil, quelle.qs, quelle.laenge
            b.naht, b.grenze = quelle.naht, quelle.grenze
            b.pruefen = list(getattr(quelle, "pruefen", None) or [])
            b.markiert = quelle.markiert
            u = self.r.ursprung_import() if hasattr(self.r, "ursprung_import") else None
            self.original.setEnabled(u is not None)
            b.original = u if u is not None and self.original.isChecked() else None
            b.zeigen(quelle.eingaben, quelle.ergebnis)
            if neu_profil:
                b.einpassen()
            self._gegenprobe()
        else:
            b.markiert = quelle.markiert
            b.setzen(quelle.eingaben, quelle.zuschnitt)

    def _gegenprobe(self):
        """P6.1: Konturlänge der Rechnung gegen die Abwicklung (nur Hinweis, rechnet nichts neu)."""
        from . import abwicklung, rechnen
        b = self.bild
        try:
            abw = abwicklung.gegenprobe(b.qs, b.eingaben, b.L, b.ergebnis)
        except (ValueError, TypeError, ZeroDivisionError, KeyError, IndexError):
            abw = []
        if not abw:
            self.gegenprobe.hide()
            return
        teile = [f"Zeile {g['zeile'] + 1} {g['text']}: Rechnung {rechnen.zahl(g['rechnung'], 1)} mm, Abwicklung "
                 f"{rechnen.zahl(g['abwicklung'], 1)} mm ({'+' if g['prozent'] > 0 else ''}"
                 f"{rechnen.zahl(g['prozent'], 1)} %)" for g in abw]
        self.gegenprobe.setText("Gegenprobe Konturlänge (nur Hinweis, Preis unverändert): " + "; ".join(teile))
        self.gegenprobe.setStyleSheet("color: #7F6000;")
        self.gegenprobe.show()

    def _name(self):
        p = getattr(self.r.d, "p", None) or {}
        return (f"Pos {p.get('pos') or ''} {p.get('artikel') or ''}".strip() or "Teil") + " Abwicklung"

    def dxf_speichern(self, pfad=None):
        """Rohrabwicklung als DXF (abwicklung.dxf_speichern). Ergebnis: Pfad oder None."""
        from . import abwicklung
        b = self.bild
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "DXF speichern", self._name() + ".dxf", "DXF-Datei (*.dxf)")
            if not pfad:
                return None
        try:
            abwicklung.dxf_speichern(pfad, b.qs, b.eingaben, b.L, self.mit_mass.isChecked())
        except (OSError, ValueError) as x:
            einblendung.melden(self, f"DXF nicht gespeichert: {x}")
            return None
        einblendung.melden(self, f"DXF gespeichert: {pfad}")
        return pfad

    def pdf_speichern(self, pfad=None):
        """Abwicklung wie gezeigt als PDF (A4 quer, ohne Bedienhinweise). Ergebnis: Pfad oder None."""
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "PDF speichern", self._name() + ".pdf", "PDF-Datei (*.pdf)")
            if not pfad:
                return None
        b = self.bild
        w = QPdfWriter(pfad)
        w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape, QMarginsF(10, 10, 10, 10)))
        w.setResolution(150)
        w.setTitle(self._name())
        g = QPainter()
        if not g.begin(w):
            einblendung.melden(self, f"PDF nicht gespeichert: {pfad}")
            return None
        k = skizze_widget.Skizze(b.profil, b.laenge)       # eigene Kopie, das Fenster bleibt unverändert
        k.qs, k.naht, k.grenze, k.modus, k.druck = b.qs, b.naht, b.grenze, skizze_widget.ABWICKLUNG, True
        k.zeigen(b.eingaben, b.ergebnis)
        try:
            r = g.viewport()
            k.resize(r.width(), r.height() - 40)
            k.render(g, QPoint())
            g.drawText(QRectF(0, r.height() - 36, r.width(), 32), Qt.AlignLeft | Qt.AlignVCenter, self._name())
        finally:
            g.end()
            k.deleteLater()
        return pfad

    def showEvent(self, e):
        super().showEvent(e)
        self.auffrischen()

    def closeEvent(self, e):
        super().closeEvent(e)
        self.geschlossen.emit()

    def done(self, r):              # Esc (reject) schließt nur dieses Fenster
        super().done(r)
        self.geschlossen.emit()
