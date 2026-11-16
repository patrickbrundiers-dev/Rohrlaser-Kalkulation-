"""PDF-Vorschau vor dem Speichern (PDF-Design 12.11.2026, F4): Seiten des fertigen PDFs ansehen, dann Speichern,
Drucken oder Abbrechen. Die Seiten zeichnet pypdfium2 (schon im Programm für das Lesen von Anfrage-PDFs), es kommt
keine neue Abhängigkeit dazu."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

SPEICHERN, DRUCKEN, ABBRECHEN = "speichern", "drucken", "abbrechen"


def seiten_bilder(pfad, breite_px=820):
    """Seiten des PDFs als QImage (Breite breite_px); [] wenn die Datei nicht lesbar ist."""
    try:
        import pypdfium2 as pdfium
        d = pdfium.PdfDocument(str(pfad))
    except Exception:       # beschädigte Datei oder pypdfium2 fehlt: ohne Vorschau weiter
        return []
    out = []
    try:
        for seite in d:
            b, _ = seite.get_size()
            bild = seite.render(scale=breite_px / b).to_pil().convert("RGB")
            daten = bild.tobytes("raw", "RGB")
            out.append(QImage(daten, bild.width, bild.height, 3 * bild.width, QImage.Format_RGB888).copy())
    finally:
        d.close()
    return out


class PdfVorschau(QDialog):
    """Fenster mit allen Seiten untereinander; Knöpfe Speichern (Enter), Drucken, Abbrechen (Esc).
    ergebnis: SPEICHERN, DRUCKEN oder ABBRECHEN; nicht_mehr: Häkchen „Vorschau nicht mehr zeigen“."""

    def __init__(self, parent, pfad, titel):
        super().__init__(parent)
        self.setWindowTitle(f"Vorschau: {titel}")
        self.ergebnis, self.pfad = ABBRECHEN, pfad
        self.bilder = seiten_bilder(pfad)
        lay = QVBoxLayout(self)
        flaeche = QWidget()
        spalte = QVBoxLayout(flaeche)
        spalte.setSpacing(14)
        for i, bild in enumerate(self.bilder, start=1):
            lab = QLabel()
            lab.setPixmap(QPixmap.fromImage(bild))
            lab.setStyleSheet("border: 1px solid #C5CCD6; background: white;")
            lab.setToolTip(f"Seite {i} von {len(self.bilder)}")
            spalte.addWidget(lab, 0, Qt.AlignHCenter)
        rollen = QScrollArea()
        rollen.setWidget(flaeche)
        rollen.setWidgetResizable(True)
        rollen.setStyleSheet("QScrollArea { background: #E3E7EC; }")
        lay.addWidget(rollen, 1)
        leiste = QHBoxLayout()
        self.seiten = QLabel(f"{len(self.bilder)} Seite{'n' if len(self.bilder) != 1 else ''}")
        self.nicht_mehr = QCheckBox("Vorschau nicht mehr zeigen")
        self.nicht_mehr.setToolTip("Wieder einschalten: Einstellungen → Texte im PDF → Vorschau vor dem Speichern")
        self.abbrechen = QPushButton("Abbrechen")
        self.drucken = QPushButton("Speichern und drucken …")
        self.speichern = QPushButton("Speichern")
        self.speichern.setDefault(True)
        self.speichern.setProperty("haupt", True)
        for k, e in ((self.abbrechen, ABBRECHEN), (self.drucken, DRUCKEN), (self.speichern, SPEICHERN)):
            k.clicked.connect(lambda _=False, e=e: self._ende(e))
        leiste.addWidget(self.seiten)
        leiste.addSpacing(12)
        leiste.addWidget(self.nicht_mehr)
        leiste.addStretch(1)
        for k in (self.abbrechen, self.drucken, self.speichern):
            leiste.addWidget(k)
        lay.addLayout(leiste)
        QShortcut(QKeySequence.Print, self, activated=lambda: self._ende(DRUCKEN))
        self.resize(900, 900)

    def _ende(self, ergebnis):
        self.ergebnis = ergebnis
        (self.reject if ergebnis == ABBRECHEN else self.accept)()


def drucken(parent, pfad, titel):
    """PDF über den Druckdialog drucken (Seiten mit 200 dpi gezeichnet, jede auf ein Blatt eingepasst).
    True = gedruckt."""
    from PySide6.QtPrintSupport import QPrintDialog, QPrinter
    bilder = seiten_bilder(pfad, 1654)
    if not bilder:
        return False
    drucker = QPrinter(QPrinter.HighResolution)
    drucker.setDocName(titel)
    if QPrintDialog(drucker, parent).exec() != QDialog.Accepted:
        return False
    p = QPainter(drucker)
    try:
        for i, bild in enumerate(bilder):
            if i:
                drucker.newPage()
            ziel = p.viewport()
            groesse = bild.size().scaled(ziel.size(), Qt.KeepAspectRatio)
            p.setViewport(ziel.x(), ziel.y(), groesse.width(), groesse.height())
            p.setWindow(bild.rect())
            p.drawImage(0, 0, bild)
            p.setViewport(ziel)
    finally:
        p.end()
    return True
