"""Hilfetexte über Tabellen und Seiten: kurz oder als Tooltip (Einstellung 'ansicht_hilfe').

aufklappbar (Vorgabe): nur der erste Satz steht da, 'ⓘ mehr' zeigt den ganzen Text. Ob ein Hinweis offen ist, merkt
sich das Programm je Seite (Einstellung 'ansicht_hilfe_offen', über alle Angebote und Neustarts).
nur Tooltip: statt des Textes steht nur 'ⓘ Hilfe', der ganze Text erscheint beim Zeigen mit der Maus.
"""
import re
import weakref

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

HILFE_EINSTELLUNG = "ansicht_hilfe"
OFFEN_EINSTELLUNG = "ansicht_hilfe_offen"     # {Schlüssel: True} der aufgeklappten Hinweise
HILFE_ARTEN = ("aufklappbar", "nur Tooltip")
GRAU = "#595959"
# Satzende: Punkt/Doppelpunkt nach mindestens zwei Buchstaben oder Ziffern, danach ein Großbuchstabe;
# Abkürzungen wie 'bzw.', 'z. B.', 'inkl.' beenden keinen Satz
_SATZENDE = re.compile(r"(?<=[\wäöüß)\]]{2})[.!]\s+(?=[A-ZÄÖÜ0-9'„])")
_ABKUERZUNGEN = ("bzw", "inkl", "ggf", "evtl", "usw", "ca", "Nr", "zzgl", "max", "min", "vgl", "Stk")

_alle = weakref.WeakSet()


def kurztext(text):
    """Erster Satz des Hinweises (ohne Abkürzungen als Satzende); ganzer Text, wenn es nur ein Satz ist."""
    text = " ".join((text or "").split())
    for m in _SATZENDE.finditer(text):
        wort = re.findall(r"[\wäöüß]+$", text[:m.start()])
        if wort and wort[0] in _ABKUERZUNGEN:
            continue
        return text[:m.start() + 1]
    return text


def art(db):
    a = db.einstellung(HILFE_EINSTELLUNG) if db is not None else None
    return "nur Tooltip" if a == "nur Tooltip" else "aufklappbar"


def alle_aktualisieren():
    """Nach dem Ändern der Einstellung alle sichtbaren Hinweise neu darstellen."""
    for h in list(_alle):
        h.aktualisieren()


class Hinweis(QWidget):
    """Hilfetext einer Seite; schluessel: unter diesem Namen wird 'aufgeklappt' gemerkt (leer = nicht gemerkt)."""

    def __init__(self, text, db=None, schluessel=None, parent=None):
        super().__init__(parent)
        self.db, self.schluessel = db, schluessel
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.PlainText)
        self.label.setStyleSheet(f"color: {GRAU};")
        self.knopf = QToolButton()
        self.knopf.setAutoRaise(True)
        self.knopf.setCursor(Qt.PointingHandCursor)
        self.knopf.setStyleSheet("QToolButton { color: #1F4E78; border: none; padding: 0 2px; }")
        self.knopf.clicked.connect(lambda: self.aufklappen(not self.offen, merken=True))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.label)
        lay.addWidget(self.knopf, 0, Qt.AlignTop)
        lay.addStretch(0)
        self.offen = False
        self.setText(text)
        _alle.add(self)

    def setText(self, text):
        self.text = " ".join((text or "").split())
        self.kurz = kurztext(self.text)
        self.aktualisieren()

    def _gemerkt(self):
        if self.db is None or not self.schluessel:
            return self.offen
        return bool((self.db.einstellung(OFFEN_EINSTELLUNG) or {}).get(self.schluessel))

    def aktualisieren(self):
        self.tooltip = art(self.db) == "nur Tooltip"
        self.offen = self._gemerkt()
        self._zeigen()

    def aufklappen(self, offen, merken=False):
        self.offen = bool(offen)
        if merken and self.db is not None and self.schluessel:
            alle = dict(self.db.einstellung(OFFEN_EINSTELLUNG) or {})
            if offen:
                alle[self.schluessel] = True
            else:
                alle.pop(self.schluessel, None)
            self.db.einstellung_setzen(OFFEN_EINSTELLUNG, alle)
        self._zeigen()

    def _zeigen(self):
        if not self.text:
            self.hide()
        elif self.isHidden() and self.parentWidget() is not None:     # nie als eigenes Fenster zeigen
            self.show()
        lang = self.kurz != self.text
        if self.tooltip:
            self.label.setVisible(False)
            self.knopf.setText("ⓘ Hilfe")
            self.knopf.setToolTip(self.text)
            self.knopf.setVisible(True)
            self.layout().setAlignment(self.knopf, Qt.AlignLeft)
            self.layout().setStretch(0, 0)
            self.layout().setStretch(2, 1)
            return
        self.label.setVisible(True)
        self.layout().setAlignment(self.knopf, Qt.AlignTop)
        ganz = self.offen or not lang
        # eingeklappt: eine Zeile direkt mit 'ⓘ mehr' dahinter, bei Platzmangel abgeschnitten (Tooltip zeigt alles);
        # aufgeklappt: Umbruch über die ganze Breite
        self.label.setWordWrap(ganz)
        self.label.setMinimumWidth(0 if ganz else 1)
        lay = self.layout()
        lay.setStretch(0, 1 if ganz else 0)
        lay.setStretch(2, 0 if ganz else 1)
        self.label.setText(self.text if ganz else self.kurz)
        self.label.setToolTip("" if ganz else self.text)
        self.knopf.setVisible(lang)
        self.knopf.setText("ⓘ weniger" if self.offen else "ⓘ mehr")
        self.knopf.setToolTip("Hilfetext einklappen" if self.offen else "Ganzen Hilfetext zeigen")
