"""Eingaben intuitiver (Plan Eingabefelder E1–E4, Patrick 25.10.2026).

- Schalter: Schiebeschalter An/Aus statt Auswahlliste „ja/nein“ (Einstellungen).
- Segment: Knopfreihe statt Auswahlliste bei wenigen, kurzen Möglichkeiten (z. B. Hell | Dunkel | …).
- RechenSpin / RechenSpinGanz: Zahlenfelder, in denen gerechnet werden darf („6000/4“, „1250 − 2×3“, wie im
  Teile-Editor), der alte Wert beim Hineinklicken markiert ist und eine ungültige Rechnung rot umrandet wird.

Schalter und Segment verhalten sich nach außen wie eine QComboBox (currentText, setCurrentText, currentTextChanged,
count, itemText, clear, addItems, isEditable), damit Laden, Speichern und Aufrufer unverändert bleiben. Gespeichert
wird weiter der Text („ja“/„nein“ bzw. der gewählte Eintrag).
"""
import re

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QValidator
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QButtonGroup, QDoubleSpinBox, QHBoxLayout,
                               QPushButton, QSpinBox, QWidget)

from . import stil

JA, NEIN = "ja", "nein"
JANEIN = (JA, NEIN)
SEGMENT_MAX = 4             # höchstens so viele Möglichkeiten als Knopfreihe
SEGMENT_ZEICHEN = 46        # … und zusammen höchstens so viele Zeichen, sonst bleibt die Auswahlliste


def segment_passt(werte):
    """Knopfreihe statt Auswahlliste? Nur bei 2–4 kurzen Möglichkeiten."""
    werte = [str(w) for w in werte]
    return 2 <= len(werte) <= SEGMENT_MAX and sum(len(w) for w in werte) <= SEGMENT_ZEICHEN


class _WieAuswahl:
    """Gemeinsame Auswahllisten-Schnittstelle für Schalter und Segment."""

    def isEditable(self):
        return False

    def count(self):
        return len(self.werte())

    def itemText(self, i):
        w = self.werte()
        return w[i] if 0 <= i < len(w) else ""

    def findText(self, text):
        w = self.werte()
        return w.index(text) if text in w else -1

    def currentIndex(self):
        return self.findText(self.currentText())

    def setCurrentIndex(self, i):
        self.setCurrentText(self.itemText(i))


class Schalter(_WieAuswahl, QAbstractButton):
    """Schiebeschalter An/Aus. Text daneben: „Ja“/„Nein“ (oder text_an/text_aus). Leertaste und Klick schalten um."""
    currentTextChanged = Signal(str)

    def __init__(self, parent=None, text_an="Ja", text_aus="Nein"):
        super().__init__(parent)
        self.text_an, self.text_aus = text_an, text_aus
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.toggled.connect(lambda an: self.currentTextChanged.emit(JA if an else NEIN))
        self.setMaximumWidth(self.sizeHint().width())

    # wie eine Auswahlliste ja/nein
    def werte(self):
        return list(JANEIN)

    def clear(self):
        pass

    def addItems(self, _werte):
        pass

    def currentText(self):
        return JA if self.isChecked() else NEIN

    def setCurrentText(self, text):
        self.setChecked(str(text or "").strip().lower() == JA)

    def _masse(self):
        h = max(18, self.fontMetrics().height() + 2)
        return h, int(h * 1.8)

    def sizeHint(self):
        h, b = self._masse()
        fm = self.fontMetrics()
        text = max(fm.horizontalAdvance(self.text_an), fm.horizontalAdvance(self.text_aus))
        return QSize(b + 8 + text + 4, h + 4)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h, b = self._masse()
        y = (self.height() - h) / 2
        bahn = QRectF(1, y, b, h)
        pal = self.palette()
        an = self.isChecked()
        farbe = pal.color(QPalette.Highlight) if an else pal.color(QPalette.Mid)
        if not self.isEnabled():
            farbe.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(farbe)
        p.drawRoundedRect(bahn, h / 2, h / 2)
        if self.hasFocus():
            stift = QColor(pal.color(QPalette.Highlight))
            stift.setAlpha(160)
            p.setPen(stift)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(bahn.adjusted(-1, -1, 1, 1), h / 2 + 1, h / 2 + 1)
            p.setPen(Qt.NoPen)
        rand = 2.5
        d = h - 2 * rand
        x = bahn.right() - rand - d if an else bahn.left() + rand
        p.setBrush(pal.color(QPalette.Base))
        p.drawEllipse(QRectF(x, y + rand, d, d))
        p.setPen(pal.color(QPalette.WindowText if self.isEnabled() else QPalette.PlaceholderText))
        p.drawText(QRectF(b + 8, 0, self.width() - b - 8, self.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   self.text_an if an else self.text_aus)
        p.end()


class Segment(_WieAuswahl, QWidget):
    """Knopfreihe mit genau einer gewählten Möglichkeit; Pfeiltasten links/rechts wechseln."""
    currentTextChanged = Signal(str)
    activated = Signal(int)

    def __init__(self, werte=(), parent=None):
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self.gruppe = QButtonGroup(self)
        self.gruppe.setExclusive(True)
        self.gruppe.idClicked.connect(self._geklickt)
        self.knoepfe = []
        self._aktuell = ""
        self.setFocusPolicy(Qt.TabFocus)
        self.setStyleSheet(
            "QPushButton[segment=\"true\"] { padding: 3px 10px; border: 1px solid palette(mid); border-radius: 0;"
            " background: palette(base); color: palette(text); }"
            "QPushButton[segment=\"true\"]:hover { background: palette(alternate-base); }"
            "QPushButton[segment=\"true\"]:checked { background: palette(highlight);"
            " color: palette(highlighted-text); border-color: palette(highlight); }"
            "QPushButton[segment=\"true\"][erster=\"true\"] { border-top-left-radius: 4px;"
            " border-bottom-left-radius: 4px; }"
            "QPushButton[segment=\"true\"][letzter=\"true\"] { border-top-right-radius: 4px;"
            " border-bottom-right-radius: 4px; }")
        self.addItems(werte)

    def werte(self):
        return [k.text() for k in self.knoepfe]

    def clear(self):
        for k in self.knoepfe:
            self.gruppe.removeButton(k)
            k.deleteLater()
        self.knoepfe = []
        self._aktuell = ""

    def addItems(self, werte):
        werte = [str(w) for w in werte]
        if werte == self.werte():
            return
        alt = self._aktuell
        self.clear()
        for i, w in enumerate(werte):
            k = QPushButton(w)
            k.setCheckable(True)
            k.setAutoDefault(False)
            k.setFocusPolicy(Qt.StrongFocus)
            k.setCursor(Qt.PointingHandCursor)
            k.setProperty("segment", True)
            k.setProperty("erster", i == 0)
            k.setProperty("letzter", i == len(werte) - 1)
            self.gruppe.addButton(k, i)
            self._lay.addWidget(k)
            self.knoepfe.append(k)
        if alt in werte:
            self._waehlen(alt)

    def currentText(self):
        return self._aktuell

    def _waehlen(self, text):
        self.gruppe.setExclusive(False)
        for k in self.knoepfe:
            k.setChecked(k.text() == text)
        self.gruppe.setExclusive(True)
        self._aktuell = text if text in self.werte() else ""

    def setCurrentText(self, text):
        text = str(text or "")
        alt = self._aktuell
        self._waehlen(text)
        if self._aktuell != alt:
            self.currentTextChanged.emit(self._aktuell)

    def _geklickt(self, i):
        self.setCurrentText(self.knoepfe[i].text())
        self.activated.emit(i)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Left, Qt.Key_Right) and self.knoepfe:
            i = self.currentIndex()
            i = max(0, min(len(self.knoepfe) - 1, (0 if i < 0 else i) + (1 if e.key() == Qt.Key_Right else -1)))
            self._geklickt(i)
            self.knoepfe[i].setFocus()
            return
        super().keyPressEvent(e)


# ------------------------------------------------------------------ Zahlenfelder mit Rechnen (E4)
_RECHNUNG = re.compile(r"[\d\s.,+\-−*/×÷:()xX]+")


class _Rechnen:
    """Rechnen im Zahlenfeld: eine Rechnung ist während der Eingabe „unfertig“ (Intermediate) und wird bei Enter
    oder beim Verlassen des Felds ausgerechnet. Unauswertbare Rechnung: rot umrandet, Erklärung als Tooltip."""

    def _rechnen_einrichten(self):
        self._tooltip = None
        self.lineEdit().textEdited.connect(self._pruefen)
        self.setButtonSymbols(self.buttonSymbols())

    def _kern(self, text):
        t = str(text)
        if self.prefix() and t.startswith(self.prefix()):
            t = t[len(self.prefix()):]
        if self.suffix() and t.endswith(self.suffix()):
            t = t[:-len(self.suffix())]
        elif self.suffix().strip() and t.rstrip().endswith(self.suffix().strip()):
            t = t.rstrip()[:-len(self.suffix().strip())]
        return t.strip()

    def _ist_rechnung(self, kern):
        """Rechnung (auch unfertig während der Eingabe, z. B. „6000/“): Zahlen und mindestens ein Rechenzeichen."""
        return bool(kern) and _RECHNUNG.fullmatch(kern) is not None and re.search(r"[\d(]", kern) is not None \
            and re.search(r"(?<=[\d)\s])[+\-−*/×÷:xX]|[()]", kern) is not None

    def _ergebnis(self, kern):
        from .rechenfeld import auswerten
        if "," in kern:     # deutsche Schreibweise im Feld: Punkt = Tausender („6.000,5/4“)
            kern = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", kern)
        elif re.search(r"\d\.\d{3}(?!\d)", kern) and self.groupSeparatorShown():
            kern = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", kern)
        try:
            w = auswerten(kern)
        except ValueError:
            return None
        if w is None:
            return None
        return max(self.minimum(), min(self.maximum(), w))

    def _pruefen(self, text):
        kern = self._kern(text)
        schlecht = self._ist_rechnung(kern) and self._ergebnis(kern) is None \
            and not re.search(r"[+\-−*/×÷:xX(]\s*$", kern)      # gerade ein Rechenzeichen getippt: noch nicht rot
        if schlecht and self._tooltip is None:
            self._tooltip = self.toolTip()
            self.setStyleSheet(stil.ROTER_RAHMEN)
            self.setToolTip("Rechnung unvollständig: erlaubt sind Zahlen, + − × ÷ und Klammern, z. B. 6000/4")
        elif not schlecht and self._tooltip is not None:
            self.setStyleSheet("")
            self.setToolTip(self._tooltip)
            self._tooltip = None

    def focusInEvent(self, e):
        super().focusInEvent(e)
        if e.reason() in (Qt.MouseFocusReason, Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason):
            QTimer.singleShot(0, self.selectAll)        # alten Wert gleich überschreiben

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._pruefen(self.lineEdit().text())


class RechenSpin(_Rechnen, QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rechnen_einrichten()

    def validate(self, text, pos):
        erg = super().validate(text, pos)
        if erg[0] != QValidator.Acceptable and self._ist_rechnung(self._kern(text)):
            return QValidator.Intermediate, text, pos
        return erg

    def valueFromText(self, text):
        kern = self._kern(text)
        if self._ist_rechnung(kern):
            w = self._ergebnis(kern)
            if w is not None:
                return w
        return super().valueFromText(text)

    def fixup(self, text):
        kern = self._kern(text)
        if self._ist_rechnung(kern):
            w = self._ergebnis(kern)
            if w is not None:
                return self.prefix() + self.textFromValue(w) + self.suffix()
        return super().fixup(text)


class RechenSpinGanz(_Rechnen, QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rechnen_einrichten()

    def validate(self, text, pos):
        erg = super().validate(text, pos)
        if erg[0] != QValidator.Acceptable and self._ist_rechnung(self._kern(text)):
            return QValidator.Intermediate, text, pos
        return erg

    def valueFromText(self, text):
        kern = self._kern(text)
        if self._ist_rechnung(kern):
            w = self._ergebnis(kern)
            if w is not None:
                return int(round(w))
        return super().valueFromText(text)

    def fixup(self, text):
        kern = self._kern(text)
        if self._ist_rechnung(kern):
            w = self._ergebnis(kern)
            if w is not None:
                return self.prefix() + self.textFromValue(int(round(w))) + self.suffix()
        return super().fixup(text)


def ist_zahlenfeld(w):
    return isinstance(w, QAbstractSpinBox)
