"""Ergebnisleiste des Teile-Editors (Plan 3D-Editor A6/A7): unten Kennzahl-Kacheln (Rohr: Schneidweg, Einstiche,
Schneidzeit, Konturklassen; Blech: Richtpreis, Zuschnitt, Gewicht, Laserzeit), das Messergebnis und rechts der
Zähler der Prüfmeldungen (Fehler, Warnungen, Hinweise). Ein Klick auf den Zähler klappt die Liste der
Prüfmeldungen auf bzw. zu.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from . import dfm, stil


class Kachel(QFrame):
    def __init__(self, titel):
        super().__init__()
        self.setObjectName("kennzahl")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(0)
        self.titel = QLabel(titel)
        self.titel.setObjectName("kennzahltitel")
        self.wert = QLabel("–")
        self.wert.setObjectName("kennzahlwert")
        lay.addWidget(self.titel)
        lay.addWidget(self.wert)


def zaehler_text(stufen):
    """'✕ 1 Fehler · ! 2 Warnungen · i 3 Hinweise' bzw. '✓ keine Prüfmeldungen'."""
    n = {s: sum(1 for x in stufen if x == s) for s in (dfm.FEHLER, dfm.WARNUNG, dfm.HINWEIS)}
    teile = []
    if n[dfm.FEHLER]:
        teile.append(f"✕ {n[dfm.FEHLER]} Fehler")
    if n[dfm.WARNUNG]:
        teile.append(f"! {n[dfm.WARNUNG]} Warnung{'en' if n[dfm.WARNUNG] != 1 else ''}")
    if n[dfm.HINWEIS]:
        teile.append(f"i {n[dfm.HINWEIS]} Hinweis{'e' if n[dfm.HINWEIS] != 1 else ''}")
    return " · ".join(teile) if teile else "✓ keine Prüfmeldungen"


class Ergebnisleiste(QWidget):
    """kacheln_setzen([(Titel, Wert, Tooltip)]); zaehler_setzen([Stufe …]); Signal aufgeklappt(bool)."""
    aufgeklappt = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 2, 0, 2)
        self.kacheln = []
        self._kachel_lay = QHBoxLayout()
        self._kachel_lay.setSpacing(6)
        self._lay.addLayout(self._kachel_lay)
        self.mass = QLabel()
        self.mass.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        self._lay.addWidget(self.mass, 1)
        self.zaehler = QToolButton()
        self.zaehler.setObjectName("aufklapper")
        self.zaehler.setCheckable(True)
        self.zaehler.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.zaehler.setToolTip("Prüfmeldungen auf- bzw. zuklappen")
        self.zaehler.toggled.connect(self._umgeschaltet)
        self._lay.addWidget(self.zaehler)
        self._stufen = []
        self.zaehler_setzen([])

    def kacheln_setzen(self, werte):
        while len(self.kacheln) < len(werte):
            k = Kachel("")
            self._kachel_lay.addWidget(k)
            self.kacheln.append(k)
        for i, k in enumerate(self.kacheln):
            if i < len(werte):
                titel, wert, tipp = (tuple(werte[i]) + ("",))[:3]
                k.titel.setText(titel)
                k.wert.setText(wert)
                k.setToolTip(tipp)
                k.show()
            else:
                k.hide()

    def zaehler_setzen(self, stufen):
        self._stufen = list(stufen)
        text = zaehler_text(self._stufen)
        self.zaehler.setText(f"{text}  {'▾' if self.zaehler.isChecked() else '▸'}")
        farbe = stil.ROT if dfm.FEHLER in self._stufen else stil.GELB_TEXT if dfm.WARNUNG in self._stufen else \
            stil.GRUEN if not self._stufen else stil.TEXT_GRAU
        self.zaehler.setStyleSheet(f"QToolButton {{ color: {stil.umsetzen(farbe)}; font-weight: bold; border: none; }}")

    def _umgeschaltet(self, an):
        self.zaehler_setzen(self._stufen)
        self.aufgeklappt.emit(an)
