"""Rechenfelder (Plan 3D-Editor B5): in Maßfeldern darf gerechnet werden wie im Taschenrechner.

Erlaubt sind Zahlen mit Komma oder Punkt, + − × ÷ (auch * / x), Klammern und die Größen des Teils als Namen,
z. B. L (Teilelänge), B, H, D (Profilmaße), S (Wand): „L/2“, „1960 − 150“, „(L − 2×25)/3“. Nur diese Rechenarten,
keine Funktionen – ausgewertet über den Python-Syntaxbaum, nie mit eval.

Muster: „3x25“ bzw. „3 × 25“ in einem Musterfeld heißt 3 Stück im Abstand 25 (muster()).
"""
import ast
import operator
import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit

from . import stil

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_MUSTER = re.compile(r"^\s*(\d+)\s*[x×*]\s*([0-9]+(?:[.,][0-9]+)?)\s*$", re.IGNORECASE)


def _vorbereiten(text):
    t = str(text or "").strip().replace("−", "-").replace("×", "*").replace("÷", "/").replace(":", "/")
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)              # Dezimalkomma
    t = re.sub(r"(?<=[\d)\s])[xX](?=[\s\d(])", "*", t)  # 2x3 = 2 × 3 (x zwischen Zahlen)
    return t


def auswerten(text, groessen=None):
    """Wert eines Rechenausdrucks; leer = None. Fehler: ValueError mit verständlichem Text."""
    t = _vorbereiten(text)
    if not t:
        return None
    namen = {str(k).upper(): float(v) for k, v in (groessen or {}).items() if v not in (None, "")}
    try:
        baum = ast.parse(t, mode="eval")
    except SyntaxError:
        raise ValueError(f"„{text}“ ist keine Zahl und keine Rechnung.") from None

    def wert(k):
        if isinstance(k, ast.Expression):
            return wert(k.body)
        if isinstance(k, ast.Constant) and isinstance(k.value, (int, float)) and not isinstance(k.value, bool):
            return float(k.value)
        if isinstance(k, ast.UnaryOp) and isinstance(k.op, (ast.UAdd, ast.USub)):
            v = wert(k.operand)
            return -v if isinstance(k.op, ast.USub) else v
        if isinstance(k, ast.BinOp) and type(k.op) in _OPS:
            a, b = wert(k.left), wert(k.right)
            if isinstance(k.op, ast.Div) and b == 0:
                raise ValueError("Division durch 0.")
            return _OPS[type(k.op)](a, b)
        if isinstance(k, ast.Name):
            if k.id.upper() in namen:
                return namen[k.id.upper()]
            bekannt = ", ".join(sorted(namen)) or "keine"
            raise ValueError(f"Unbekannte Größe „{k.id}“ (bekannt: {bekannt}).")
        raise ValueError(f"„{text}“: nur Zahlen, + − × ÷ und Klammern.")
    return wert(baum)


def muster(text):
    """'3x25' → (3, 25.0); sonst None."""
    m = _MUSTER.match(str(text or ""))
    if not m:
        return None
    return int(m.group(1)), float(m.group(2).replace(",", "."))


def zahl_text(v, stellen=2):
    """Zahl mit Komma ohne Nullen am Ende (12,5 statt 12,50)."""
    if v is None:
        return ""
    t = f"{float(v):.{stellen}f}".rstrip("0").rstrip(".")
    return (t if t != "-0" else "0").replace(".", ",")


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
