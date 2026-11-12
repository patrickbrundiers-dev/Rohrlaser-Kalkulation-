"""Fenster „Aus Scan/Bild nachzeichnen“ für den Rohr- und Blech-Editor (Plan Paket K2, Rechnung in nachzeichnen).

Bild oder PDF wählen, Breite des Teils in mm eingeben (Vorgabe aus der Auflösung), Art und Schwelle stellen; die
Vorschau zeigt das Bild mit dem nachgezeichneten Umriss (blau) und den Löchern (rot). Übernehmen:
- Blech: Außenkontur und Löcher ersetzen das Teil (wie DXF importieren) oder kommen als Innenkonturen dazu.
- Rohr: Löcher (und auf Wunsch der Umriss) als Innenkonturen auf der Wand oben, mittig in der Rohrlänge.
"""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout)

from . import einblendung, nachzeichnen as nz

TITEL = "Aus Scan/Bild"
TIPP = ("Kontur aus einem Scan, Foto oder Raster-PDF nachzeichnen: Umriss und Löcher werden erkannt, Bögen werden "
        "echte Bögen, Bohrungen und Langlöcher wie beim DXF-Import erkannt. Den Maßstab gibt die Breite des Teils in "
        "mm; genau auf etwa ein Pixel, also bitte prüfen")
ZIEL_ERSETZEN, ZIEL_INNEN = "Außenkontur und Löcher (Teil ersetzen)", "Nur als Innenkonturen dazu"


class NachzeichnenDialog(QDialog):
    def __init__(self, parent, rohr=False, pfad=None):
        super().__init__(parent)
        self.setWindowTitle("Kontur aus Scan oder Bild nachzeichnen")
        self.rohr = rohr
        self.bild = self.erg = None
        self.mm_bild = None
        lay = QVBoxLayout(self)
        oben = QHBoxLayout()
        self.datei_knopf = QPushButton("Bild oder PDF wählen …")
        self.datei_knopf.clicked.connect(lambda: self.datei_waehlen())
        self.datei = QLabel("–")
        oben.addWidget(self.datei_knopf)
        oben.addWidget(self.datei, 1)
        lay.addLayout(oben)
        self.vorschau = QLabel()
        self.vorschau.setMinimumSize(640, 420)
        self.vorschau.setAlignment(Qt.AlignCenter)
        self.vorschau.setStyleSheet("QLabel { background: white; border: 1px solid #c8c8c8; }")
        lay.addWidget(self.vorschau, 1)
        form = QFormLayout()
        self.seite = QSpinBox()
        self.seite.setRange(1, 1)
        self.seite.valueChanged.connect(lambda _: self.laden())
        form.addRow("PDF-Seite", self.seite)
        self.art = QComboBox()
        self.art.addItems(nz.ARTEN)
        self.art.setToolTip("Linienzeichnung: Umriss und Löcher sind Striche (Mitte des Strichs zählt). Fläche: das "
                            "Teil ist dunkel gefüllt, z. B. ein Schattenriss")
        self.art.currentIndexChanged.connect(lambda _: self.rechnen())
        form.addRow("Art", self.art)
        self.schwelle = QSpinBox()
        self.schwelle.setRange(0, 255)
        self.schwelle.setSpecialValueText("automatisch")
        self.schwelle.setToolTip("Grauwert, bis zu dem ein Pixel als Strich zählt (0 = automatisch)")
        self.schwelle.valueChanged.connect(lambda _: self.rechnen())
        form.addRow("Schwelle", self.schwelle)
        self.breite = QDoubleSpinBox()
        self.breite.setRange(0, 100000)
        self.breite.setDecimals(2)
        self.breite.setSuffix(" mm")
        self.breite.setToolTip("Breite des Umrisses in mm (Maßstab); vorgeschlagen aus der Auflösung des Bildes")
        self.breite.valueChanged.connect(lambda _: self.text_setzen())
        form.addRow("Breite des Teils", self.breite)
        self.ziel = QComboBox()
        if rohr:
            self.umriss = QCheckBox("Umriss auch als Kontur (z. B. ein gezeichneter Ausschnitt)")
            form.addRow("", self.umriss)
        else:
            self.ziel.addItems((ZIEL_ERSETZEN, ZIEL_INNEN))
            form.addRow("Übernehmen als", self.ziel)
        lay.addLayout(form)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        self.ok_knopf = knoepfe.button(QDialogButtonBox.Ok)
        self.ok_knopf.setEnabled(False)
        lay.addWidget(knoepfe)
        self.pfad = None
        if pfad:
            self.datei_setzen(pfad)

    # -------------------------------------------------------------- Laden und Rechnen
    def datei_waehlen(self):
        pfad, _ = QFileDialog.getOpenFileName(self, "Scan oder Bild wählen", "", nz.BILD_FILTER)
        if pfad:
            self.datei_setzen(pfad)

    def datei_setzen(self, pfad):
        self.pfad = str(pfad)
        self.datei.setText(self.pfad)
        self.seite.blockSignals(True)
        self.seite.setValue(1)
        self.seite.blockSignals(False)
        self.laden(neu=True)

    def laden(self, neu=False):
        if not self.pfad:
            return
        try:
            self.bild, self.mm_bild, n = nz.laden(self.pfad, self.seite.value() - 1)
        except Exception as x:          # beschädigte Datei, unbekanntes Format
            self.bild, self.erg = None, None
            self.info.setText(f"Bild nicht lesbar: {x}")
            self.ok_knopf.setEnabled(False)
            return
        self.seite.blockSignals(True)
        self.seite.setRange(1, max(1, n))
        self.seite.blockSignals(False)
        self.rechnen(breite_vorschlagen=neu)

    def rechnen(self, breite_vorschlagen=False):
        if self.bild is None:
            return
        art = self.art.currentText()
        try:
            self.erg = nz.nachzeichnen(self.bild, self.schwelle.value() or None, art)
        except ValueError as x:
            self.erg = None
            self.info.setText(str(x))
            self.ok_knopf.setEnabled(False)
            self.zeichnen()
            return
        if breite_vorschlagen or not self.breite.value():
            if self.mm_bild:
                self.breite.blockSignals(True)
                self.breite.setValue(round(nz.breite_px(self.erg) * self.erg["faktor"] * self.mm_bild, 1))
                self.breite.blockSignals(False)
        self.zeichnen()
        self.text_setzen()

    def text_setzen(self):
        if not self.erg:
            return
        if not self.breite.value():
            self.info.setText("Breite des Teils in mm eingeben (das Bild nennt keine Auflösung).")
            self.ok_knopf.setEnabled(False)
            return
        mm = nz.mm_je_pixel(self.erg, self.breite.value())
        n = len(self.erg["zuege"]) - 1
        strich = f", Strich {self.erg['strich']} Pixel" if self.erg.get("strich") else ""
        loch = "1 Loch" if n == 1 else f"{n} Löcher"
        genau = f"{mm:.2f}".replace(".", ",")
        self.info.setText(f"{self.erg['art']}: Umriss und {loch}{strich}. Ein Pixel = {genau} mm, so genau ist das "
                          "Ergebnis: bitte die Maße prüfen.")
        self.ok_knopf.setEnabled(True)

    def zeichnen(self):
        if self.bild is None:
            self.vorschau.clear()
            return
        k, _ = nz.verkleinert(self.bild)
        img = QImage(k.tobytes(), k.width, k.height, k.width, QImage.Format_Grayscale8).copy()
        pm = QPixmap.fromImage(img.convertToFormat(QImage.Format_RGB32))
        if self.erg:
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            for i, zug in enumerate(self.erg["zuege"]):
                farbe = "#2E75B6" if i == 0 else "#C00000"   # auf dem Scan (immer hell): Umriss blau, Löcher rot
                p.setPen(QPen(QColor(farbe), max(2.0, k.width / 500)))  # fest: auf dem hellen Scan
                p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in nz._glatt(zug)]))
            p.end()
        self.vorschau.setPixmap(pm.scaled(self.vorschau.width() - 4, self.vorschau.height() - 4, Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))

    # -------------------------------------------------------------- Ergebnis
    def ergebnis(self):
        """(Blech-Eingaben aus dem Bild, Zusammenfassung) oder ValueError."""
        if not self.erg:
            raise ValueError("Kein Umriss erkannt.")
        return nz.teil(self.erg, nz.mm_je_pixel(self.erg, self.breite.value()),
                       name=str(self.pfad or "Scan").rsplit("/", 1)[-1])


def uebernehmen(rahmen, e_bild, ersetzen=True, mit_umriss=False):
    """Ergebnis ins Teil: Blech ersetzen bzw. Innenkonturen anhängen, Rohr Innenkonturen anhängen. Ergebnis: Zahl
    der neuen Konturzeilen."""
    d = rahmen.d
    e = d.eingaben()
    if rahmen.art == "rohr":
        laenge = d.k_laenge.value() if getattr(d, "neu", False) and hasattr(d, "k_laenge") else d.p.get("laenge")
        neu = nz.rohr_konturen(e_bild, laenge, mit_umriss or not e_bild.get("konturen"))
        d.eingaben_setzen(dict(e, konturen=list(e.get("konturen") or []) + neu))
    elif ersetzen:
        neu = list(e_bild.get("konturen") or [])
        felder = {k: v for k, v in e_bild.items() if k in ("form", "punkte", "laenge", "breite", "eckradius")}
        d.eingaben_setzen(dict(e, art=e_bild.get("art") or e.get("art"), konturen=neu, **felder))
    else:
        neu = list(e_bild.get("konturen") or [])
        d.eingaben_setzen(dict(e, konturen=list(e.get("konturen") or []) + neu))
    d.rechnen()
    rahmen.aktualisieren()
    return len(neu)


def aus_bild(rahmen, pfad=None):
    """Knopf „Aus Scan/Bild“: Fenster öffnen und übernehmen. Ergebnis: Zahl der neuen Konturen oder None."""
    dlg = NachzeichnenDialog(rahmen.d, rohr=rahmen.art == "rohr", pfad=pfad)
    dlg.resize(900, 760)
    if dlg.exec() != QDialog.Accepted:
        return None
    try:
        e_bild, zus = dlg.ergebnis()
    except ValueError as x:
        einblendung.melden(rahmen.d, str(x))
        return None
    n = uebernehmen(rahmen, e_bild, ersetzen=dlg.ziel.currentText() != ZIEL_INNEN,
                    mit_umriss=bool(getattr(dlg, "umriss", None) and dlg.umriss.isChecked()))
    einblendung.melden(rahmen.d, f"Aus dem Bild übernommen: {zus}. Bitte Maße prüfen.")
    return n
