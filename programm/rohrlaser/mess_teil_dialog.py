"""Fenster „Teil messen“ (Messplan 19.11.2026, M3): Rohr-, Kontur- und Fertigungsmessung des gezeigten Teils in
jedem 3D-Fenster (Knopf „Teil messen“ in der Leiste, Rechtsklick → Teil messen). Zeigt nur Werte, ändert nie das
Teil; die Kalkulation rechnet unverändert."""
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from . import einblendung, mess_teil


class TeilMessung(QDialog):
    def __init__(self, ansicht, parent=None):
        super().__init__(parent or ansicht.window())
        self.ansicht = ansicht
        self.setWindowTitle("Teil messen")
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        self.hinweis = QLabel("Gemessen am 3D-Modell: Rohr, Konturen und Fertigung. Werte mit „≈“ sind am Netz "
                              "gewölbter Flächen genähert. Nur Prüfung – Schneidweg und Preis rechnen unverändert.")
        self.hinweis.setWordWrap(True)
        lay.addWidget(self.hinweis)
        self.baum = QTreeWidget()
        self.baum.setHeaderHidden(True)
        self.baum.setWordWrap(True)
        lay.addWidget(self.baum, 1)
        knoepfe = QHBoxLayout()
        self.knoepfe = {}
        for name, text, fn in (("kopieren", "Kopieren", self.kopieren), ("pdf", "Messprotokoll (PDF) …", self.pdf)):
            k = QPushButton(text)
            k.clicked.connect(fn)
            knoepfe.addWidget(k)
            self.knoepfe[name] = k
        knoepfe.addStretch(1)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        knoepfe.addWidget(zu)
        lay.addLayout(knoepfe)
        self.gruppen = []
        self.laden()

    def laden(self):
        self.gruppen = self.ansicht.teil_messung() or []
        self.baum.clear()
        for titel, zeilen in self.gruppen:
            kopf = QTreeWidgetItem([titel])
            f = kopf.font(0)
            f.setBold(True)
            kopf.setFont(0, f)
            for z in zeilen:
                QTreeWidgetItem(kopf, [z])
            self.baum.addTopLevelItem(kopf)
            kopf.setExpanded(True)
        for k in self.knoepfe.values():
            k.setEnabled(bool(self.gruppen))

    def text(self):
        return mess_teil.klartext(self.gruppen)

    def kopieren(self):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.text())
        einblendung.melden(self, "Teilmessung in die Zwischenablage kopiert.")

    def pdf(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Messprotokoll speichern", "Teilmessung.pdf", "PDF (*.pdf)")
        if pfad:
            from . import mess_protokoll
            titel = getattr(self.ansicht, "titel", "") or ""
            mess_protokoll.pdf_gruppen(pfad, self.gruppen, titel="Messprotokoll Teil",
                                       angaben=[("Teil", titel)] if titel else (),
                                       bild_png=self.ansicht.bild_png())
            einblendung.melden(self, f"Gespeichert: {pfad}")
        return pfad
