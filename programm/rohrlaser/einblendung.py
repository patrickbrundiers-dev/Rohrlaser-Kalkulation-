"""Ruhige Meldungen (Plan B7, Layout-Plan L14): Hinweise und Erfolg erscheinen als Einblendung unten rechts im
Fenster und verschwinden von selbst; der Meldungsverlauf in der Statusleiste zeigt die letzten noch einmal.

Entscheidungen und Fehler mit Datenverlust bleiben Dialoge. Löschen im Angebot fragt nicht mehr, die Einblendung
bietet dafür „Rückgängig“ an (Plan Bedienung B2); lange Berichte stehen hinter einem Knopf „Bericht“ (B1) und bleiben
im Verlauf abrufbar.
"""
import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QToolButton

from . import stil

VERLAUF = 20            # so viele Meldungen merkt der Verlauf
DAUER_MS = 4500         # so lange bleibt eine Einblendung (Fehler doppelt so lange)
DAUER_AKTION_MS = 9000  # mit Knopf (Rückgängig, Bericht) länger, damit Zeit zum Klicken bleibt


def bericht_zeigen(parent, titel, text, details):
    """Bericht einer Meldung (z. B. STEP-Import) als Fenster mit aufklappbaren Einzelheiten."""
    box = QMessageBox(QMessageBox.Information, titel, text, parent=parent)
    box.setDetailedText(details)
    box.exec()


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
        self.knopf = QPushButton()      # Rückgängig, Bericht … (nur mit aktion)
        self.knopf.setCursor(Qt.PointingHandCursor)
        self.knopf.clicked.connect(self._aktion_ausfuehren)
        self.knopf.hide()
        self.aktion = None
        lay.addWidget(self.symbol, 0, Qt.AlignTop)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.knopf, 0, Qt.AlignVCenter)
        self.uhr = QTimer(self)
        self.uhr.setSingleShot(True)
        self.uhr.timeout.connect(self.hide)
        self.hide()

    def zeigen(self, text, fehler=False, aktion=None):
        """aktion = (Knopftext, Funktion): Knopf in der Einblendung, ein Klick führt sie aus und schließt."""
        stufe = "FEHLER" if fehler else "OK"
        self.setStyleSheet(
            f"QFrame#einblendung {{ background: {'#FDECEA' if fehler else '#FFFFFF'}; border: 1px solid "
            f"{'#F3B8B2' if fehler else '#C5CCD6'}; border-radius: 6px; }} QLabel {{ color: "
            f"{'#8C1D18' if fehler else '#1F2937'}; background: transparent; border: none; }}")
        self.symbol.setPixmap(stil.status_symbol(stufe, 16).pixmap(16, 16))
        self.text.setText(text)
        self.aktion = aktion[1] if aktion else None
        self.knopf.setText(aktion[0] if aktion else "")
        self.knopf.setVisible(bool(aktion))
        self.adjustSize()
        self.platzieren()
        self.show()
        self.raise_()
        self.uhr.start(DAUER_AKTION_MS if aktion else DAUER_MS * (2 if fehler else 1))

    def _aktion_ausfuehren(self):
        ziel, self.aktion = self.aktion, None
        self.hide()
        if ziel is not None:
            ziel()

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
        self.eintraege = []         # [(Zeit, Text, Fehler, Bericht)], neueste zuerst; Bericht = (Titel, Details)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setToolTip("Letzte Meldungen")
        self.setPopupMode(QToolButton.InstantPopup)
        self.menue = QMenu(self)
        self.setMenu(self.menue)
        self.aktualisieren()

    def merken(self, text, fehler=False, bericht=None):
        self.eintraege.insert(0, (datetime.datetime.now(), str(text), bool(fehler), bericht))
        del self.eintraege[VERLAUF:]
        self.aktualisieren()

    def aktualisieren(self):
        self.setText(f"Meldungen ({len(self.eintraege)})")
        self.menue.clear()
        if not self.eintraege:
            self.menue.addAction("Noch keine Meldungen").setEnabled(False)
        for zeit, text, fehler, bericht in self.eintraege:
            a = self.menue.addAction(f"{zeit:%H:%M}  {text}" + ("  (Bericht …)" if bericht else ""))
            a.setIcon(stil.status_symbol("FEHLER" if fehler else "OK"))
            if bericht:
                a.triggered.connect(lambda _=False, t=text, b=bericht: bericht_zeigen(self.window(), b[0], t, b[1]))


def melden(widget, text, fehler=False, aktion=None, bericht=None):
    """Ruhige Meldung aus einem beliebigen Fenster (Plan Bedienung B2): im Hauptfenster über dessen meldung (mit
    Verlauf), in einem Editor oder Dialog als Einblendung unten rechts in diesem Fenster (sonst läge sie verdeckt
    hinter dem Dialog). Ersetzt reine Hinweisfenster, die nur ein OK verlangen."""
    fenster = widget.window() if widget is not None else None
    if fenster is None:
        return
    haupt = fenster if hasattr(fenster, "verlauf") and hasattr(fenster, "meldung") else None
    if haupt is not None:
        haupt.meldung(text, fehler, aktion=aktion, bericht=bericht)
        return
    # Dialog: Hauptfenster (Eltern-Kette) führt den Verlauf, die Einblendung erscheint im Dialog
    p = fenster.parentWidget()
    while p is not None and not (hasattr(p, "verlauf") and hasattr(p, "meldung")):
        p = p.parentWidget()
    stumm = bool(getattr(p, "stumm", False))
    if p is not None and getattr(p, "verlauf", None) is not None:
        p.verlauf.merken(text, fehler, bericht)
        p.letzte_aktion = aktion
    fenster.letzte_meldung = text           # Tests: zuletzt gemeldeter Text des Dialogs
    if stumm:
        return
    if aktion is None and bericht:
        aktion = ("Bericht …", lambda: bericht_zeigen(fenster, bericht[0], text, bericht[1]))
    karte = getattr(fenster, "_einblendung", None)
    if karte is None:
        karte = fenster._einblendung = Einblendung(fenster)
    karte.zeigen(text, fehler, aktion)
