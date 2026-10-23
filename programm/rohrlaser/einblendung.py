"""Ruhige Meldungen (Plan B7, Layout-Plan L14): Hinweise und Erfolg erscheinen als Einblendung unten rechts im
Fenster und verschwinden von selbst; der Meldungsverlauf in der Statusleiste zeigt die letzten noch einmal.

Rückfragen vor dem Löschen, Fehler mit Datenverlust und Entscheidungen bleiben Dialoge.
"""
import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QToolButton

from . import stil

VERLAUF = 20            # so viele Meldungen merkt der Verlauf
DAUER_MS = 4500         # so lange bleibt eine Einblendung (Fehler doppelt so lange)


class Einblendung(QFrame):
    """Kleine Karte unten rechts über dem Fensterinhalt; Klick schließt sie."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.setObjectName("einblendung")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.symbol = QLabel()
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setMaximumWidth(420)
        lay.addWidget(self.symbol, 0, Qt.AlignTop)
        lay.addWidget(self.text, 1)
        self.uhr = QTimer(self)
        self.uhr.setSingleShot(True)
        self.uhr.timeout.connect(self.hide)
        self.hide()

    def zeigen(self, text, fehler=False):
        stufe = "FEHLER" if fehler else "OK"
        self.setStyleSheet(
            f"QFrame#einblendung {{ background: {'#FDECEA' if fehler else '#FFFFFF'}; border: 1px solid "
            f"{'#F3B8B2' if fehler else '#C5CCD6'}; border-radius: 6px; }} QLabel {{ color: "
            f"{'#8C1D18' if fehler else '#1F2937'}; background: transparent; border: none; }}")
        self.symbol.setPixmap(stil.status_symbol(stufe, 16).pixmap(16, 16))
        self.text.setText(text)
        self.adjustSize()
        self.platzieren()
        self.show()
        self.raise_()
        self.uhr.start(DAUER_MS * (2 if fehler else 1))

    def platzieren(self):
        p = self.parentWidget()
        if p is None:
            return
        unten = p.statusBar().height() if hasattr(p, "statusBar") else 0
        self.move(max(8, p.width() - self.width() - 16), max(8, p.height() - unten - self.height() - 12))

    def mousePressEvent(self, _e):
        self.hide()


class Verlauf(QToolButton):
    """Statusleiste: die letzten Meldungen mit Uhrzeit (Klick öffnet die Liste)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.eintraege = []         # [(Zeit, Text, Fehler)], neueste zuerst
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setToolTip("Letzte Meldungen")
        self.setPopupMode(QToolButton.InstantPopup)
        self.menue = QMenu(self)
        self.setMenu(self.menue)
        self.aktualisieren()

    def merken(self, text, fehler=False):
        self.eintraege.insert(0, (datetime.datetime.now(), str(text), bool(fehler)))
        del self.eintraege[VERLAUF:]
        self.aktualisieren()

    def aktualisieren(self):
        self.setText(f"Meldungen ({len(self.eintraege)})")
        self.menue.clear()
        if not self.eintraege:
            self.menue.addAction("Noch keine Meldungen").setEnabled(False)
        for zeit, text, fehler in self.eintraege:
            a = self.menue.addAction(f"{zeit:%H:%M}  {text}")
            a.setIcon(stil.status_symbol("FEHLER" if fehler else "OK"))
