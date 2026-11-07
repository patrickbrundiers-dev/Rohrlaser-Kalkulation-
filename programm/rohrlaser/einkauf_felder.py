"""Zeile „Einkauf je Satz“ bzw. „Einkauf je Baugruppe“ (Patrick 03.11. / 07.11.2026): je Art der Zukaufteile
(Bleche, Vollmaterial, Dreh-/Frästeile) ein Feld mit dem kompletten Einkaufspreis, der nach Gewicht auf die Teile
umgelegt wird (Rechnung in satz_kosten.py). In allen Editoren gleich: Satz bearbeiten, Satz in 3D, Schweißbaugruppe.
Ohne passende Zukaufteile zeigt die Zeile, warum es kein Feld gibt."""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from . import satz_kosten
from .eingabe import RechenSpin

GRAU = "#667085"
OHNE_TEXT = ("keine Bleche, kein Vollmaterial und keine Dreh-/Frästeile als Zukaufteile in diesem {wer} "
             "(Blechteile mit Kategorie Blechteile)")


class EinkaufFelder(QWidget):
    """Felder je vorhandener Art. kosten(): {Art: € oder 0} für alle Felder, geaendert(): nur die geänderten."""

    def __init__(self, positionen, satz=None, bg=None, nur_lesen=False, parent=None):
        super().__init__(parent)
        self.wer = "Baugruppe" if bg else "Satz"
        self.felder = {}
        self.alt = satz_kosten.betraege(positionen, satz, bg)
        arten = satz_kosten.arten(positionen, satz, bg)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(f"Einkauf je {self.wer}:"))
        if not arten:
            leer = bg and not satz_kosten.indizes(positionen, bg=bg)
            hinweis = QLabel("erst nach dem Speichern der Baugruppe (die Teile sind ihr noch nicht zugeordnet)" if leer
                             else OHNE_TEXT.format(wer=self.wer))
            hinweis.setStyleSheet(f"color: {GRAU};")
            hinweis.setWordWrap(True)
            lay.addWidget(hinweis, 1)
            self.hinweis = hinweis
            return
        self.hinweis = None
        for a in arten:
            sp = RechenSpin()
            sp.setRange(0, 9_999_999)
            sp.setDecimals(2)
            sp.setSuffix(" €")
            sp.setSpecialValueText("aus den Artikeln")
            sp.setMinimumWidth(140)
            sp.setValue(self.alt.get(a, 0.0))
            sp.setEnabled(not nur_lesen)
            sp.setToolTip(f"Kompletter Einkaufspreis der {a} je {self.wer}. Wird nach Gewicht (ohne Gewicht nach "
                          f"Stück) auf die {a} umgelegt und ersetzt deren Einkaufspreis aus dem Artikel; danach nur "
                          "der Aufschlag wie jedes Zukaufteil. 0 = wieder der EK aus dem Artikel.")
            lay.addWidget(QLabel(a))
            lay.addWidget(sp)
            self.felder[a] = sp
        lay.addStretch(1)

    def kosten(self):
        return {a: sp.value() for a, sp in self.felder.items()}

    def geaendert(self):
        return {a: w for a, w in self.kosten().items() if round(w, 2) != round(self.alt.get(a, 0.0), 2)}
