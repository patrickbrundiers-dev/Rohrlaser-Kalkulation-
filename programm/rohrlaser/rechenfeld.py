"""Rechenfelder (Plan 3D-Editor B5): in Maßfeldern darf gerechnet werden wie im Taschenrechner.

Erlaubt sind Zahlen mit Komma oder Punkt, + − × ÷ (auch * / x), Klammern und die Größen des Teils als Namen,
z. B. L (Teilelänge), B, H, D (Profilmaße), S (Wand): „L/2“, „1960 − 150“, „(L − 2×25)/3“. Nur diese Rechenarten,
keine Funktionen – ausgewertet über den Python-Syntaxbaum, nie mit eval.

Muster: „3x25“ bzw. „3 × 25“ in einem Musterfeld heißt 3 Stück im Abstand 25 (muster()).
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit

from . import stil
# reine Rechnung ohne Qt (Audit 26.11.2026, A-01): hier weitergeführt
from .rechenformel import _MUSTER, _OPS, _vorbereiten, auswerten, muster, zahl_text  # noqa: F401


class RechenFeld(QLineEdit):
    """Eingabefeld für ein Maß: nimmt Rechnungen an, zeigt nach Enter/Verlassen das Ergebnis (die Rechnung steht im
    Tooltip). wert_geaendert(float oder None) nur bei gültiger Eingabe; ungültig: roter Rahmen + Fehler im Tooltip."""
    wert_geaendert = Signal(object)

    def __init__(self, wert=None, groessen=None, einheit="mm", parent=None):
        super().__init__(parent)
        self.groessen, self.einheit = dict(groessen or {}), einheit
        self._wert, self.fehler = wert, None
        self.setText(zahl_text(wert))
        self.setPlaceholderText(einheit)
        self.editingFinished.connect(self.uebernehmen)

    def wert(self):
        return self._wert

    def wert_setzen(self, v):
        """Wert von außen setzen (ohne Signal)."""
        self._wert, self.fehler = v, None
        self.setText(zahl_text(v))
        self.setStyleSheet("")

    def uebernehmen(self):
        text = self.text()
        try:
            v = auswerten(text, self.groessen)
        except ValueError as f:
            self.fehler = str(f)
            self.setStyleSheet(f"QLineEdit {{ {stil.ROTER_RAHMEN} }}")
            self.setToolTip(self.fehler)
            return
        self.fehler = None
        self.setStyleSheet("")
        rechnung = _vorbereiten(text)
        self.setToolTip(f"Eingabe: {text}" if v is not None and rechnung != _vorbereiten(zahl_text(v)) else "")
        self.setText(zahl_text(v))
        if v != self._wert:
            self._wert = v
            self.wert_geaendert.emit(v)
