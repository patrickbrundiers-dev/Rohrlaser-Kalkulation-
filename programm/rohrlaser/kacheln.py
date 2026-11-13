"""Kennzahl-Kacheln der Startseite (UI-Modernisierung U5, Patrick 12.11.2026).

Eine Zeile mit wenigen großen Zahlen über der Startseite: Entwürfe, verschickte (offene) Angebote, Aufträge und
Trefferquote der letzten 90 Tage, fällige Wiedervorlagen. Für alle Benutzer; Marge und Umsatzdetails bleiben in der
Kennzahlenzeile „nur Admin“. Ein Klick auf eine Kachel öffnet die passende Liste. Die Werte kommen aus cockpit.py
(dieselben Summen wie Angebotsliste und Pipeline).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .stil import TEXT_GRAU

# (Schlüssel, Titel, Tooltip)
KACHELN = (
    ("Entwurf", "Entwürfe", "Eigene Angebote im Entwurf (Klick: Angebotsliste mit diesem Filter)"),
    ("Verschickt", "Verschickt, offen", "Eigene verschickte Angebote ohne Entscheidung (Klick: Angebotsliste)"),
    ("Beauftragt", "Aufträge (90 Tage)", "Beauftragte eigene Angebote mit Datum in den letzten 90 Tagen "
                                         "(Klick: Angebotsliste Beauftragt)"),
    ("quote", "Trefferquote (90 Tage)", "Beauftragt ÷ (beauftragt + abgelehnt), eigene Angebote der letzten 90 Tage"),
    ("wiedervorlage", "Wiedervorlage fällig", "Angebote zum Nachfassen (Liste rechts unter Heute)"),
)


class Kachel(QFrame):
    geklickt = Signal(str)

    def __init__(self, schluessel, titel, tipp):
        super().__init__()
        self.schluessel = schluessel
        self.setObjectName("karte")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tipp)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 8)
        lay.setSpacing(0)
        self.titel = QLabel(titel)
        self.titel.setStyleSheet(f"color: {TEXT_GRAU};")
        self.wert = QLabel("–")
        f = QFont(self.wert.font())
        f.setPointSizeF(f.pointSizeF() * 1.8)
        f.setBold(True)
        self.wert.setFont(f)
        self.unter = QLabel("")
        self.unter.setStyleSheet(f"color: {TEXT_GRAU};")
        for w in (self.titel, self.wert, self.unter):
            lay.addWidget(w)

    def setzen(self, wert, unter=""):
        self.wert.setText(wert)
        self.unter.setText(unter or " ")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.geklickt.emit(self.schluessel)
        super().mouseReleaseEvent(e)


class KachelZeile(QWidget):
    geklickt = Signal(str)

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.kacheln = {}
        for schluessel, titel, tipp in KACHELN:
            k = Kachel(schluessel, titel, tipp)
            k.geklickt.connect(self.geklickt)
            lay.addWidget(k)
            self.kacheln[schluessel] = k

    def setzen(self, pipeline, kennzahlen, wiedervorlagen, euro_text):
        """pipeline = cockpit.pipeline, kennzahlen = cockpit.kennzahlen, wiedervorlagen = Anzahl fälliger."""
        p = {v: (n, summe) for v, n, summe in pipeline}
        for v in ("Entwurf", "Verschickt"):
            n, summe = p.get(v, (0, 0))
            self.kacheln[v].setzen(str(n), f"{euro_text(summe)} € netto" if summe else "")
        k = kennzahlen
        self.kacheln["Beauftragt"].setzen(str(k["beauftragt"]),
                                          f"{euro_text(k['auftragswert'])} € netto" if k["auftragswert"] else "")
        q = k["trefferquote"]
        self.kacheln["quote"].setzen(f"{q * 100:.0f} %" if q is not None else "–",
                                     "noch keine Entscheidung" if q is None else "")
        self.kacheln["wiedervorlage"].setzen(str(wiedervorlagen), "heute nachfassen" if wiedervorlagen else "nichts fällig")
