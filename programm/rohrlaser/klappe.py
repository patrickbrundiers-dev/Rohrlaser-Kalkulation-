"""Zuklappbarer Abschnitt (Plan Schweißbaugruppe Teil 2, 13.11.2026, L5): Kopfzeile mit Pfeil, Titel und Kurzwert,
darunter der Inhalt. Der Zustand wird je Name in der eigenen Datendatei gemerkt (Einstellung klappen, nicht im
gemeinsamen Ordner); ohne Datenbank gilt er für die Sitzung."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QToolButton, QVBoxLayout, QWidget

EINSTELLUNG = "klappen"         # {Name: True/False}
_SITZUNG = {}


def gemerkt(db, name, vorgabe):
    if name in _SITZUNG:
        return _SITZUNG[name]
    try:
        d = db.einstellung(EINSTELLUNG) if db is not None else None
    except Exception:           # noqa: BLE001 – Datendatei geschlossen: Vorgabe
        d = None
    return bool(d[name]) if isinstance(d, dict) and name in d else vorgabe


def merken(db, name, offen):
    _SITZUNG[name] = bool(offen)
    if db is None:
        return
    try:
        d = db.einstellung(EINSTELLUNG)
        d = dict(d) if isinstance(d, dict) else {}
        d[name] = bool(offen)
        db.einstellung_setzen(EINSTELLUNG, d)
    except Exception:           # noqa: BLE001 – nur lesend geöffnet o. Ä.: Zustand gilt für die Sitzung
        pass


class Klappe(QWidget):
    """Abschnitt mit Kopfzeile; offen = Inhalt sichtbar. kurz_setzen zeigt einen Kurzwert in der Kopfzeile, solange
    der Abschnitt zu ist (z. B. die Zeit), damit das Wichtigste ohne Aufklappen lesbar bleibt."""
    geklappt = Signal(bool)

    def __init__(self, titel, inhalt, name, db=None, offen=False, parent=None):
        super().__init__(parent)
        self.titel, self.inhalt, self.name, self.db = titel, inhalt, name, db
        self._kurz = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.kopf = QToolButton()
        self.kopf.setObjectName(f"klappe_{name}")
        self.kopf.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.kopf.setCheckable(True)
        self.kopf.setAutoRaise(True)
        self.kopf.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.kopf.setStyleSheet("QToolButton { text-align: left; font-weight: bold; border: none; padding: 2px 0; }")
        self.kopf.setToolTip("Klick klappt den Abschnitt auf oder zu (wird gemerkt)")
        self.kopf.toggled.connect(self._klappen)
        lay.addWidget(self.kopf)
        lay.addWidget(inhalt)
        an = gemerkt(db, name, offen)
        self.kopf.blockSignals(True)
        self.kopf.setChecked(an)
        self.kopf.blockSignals(False)
        self._zeigen(an)

    def offen(self):
        return self.kopf.isChecked()

    def oeffnen(self, an=True):
        self.kopf.setChecked(bool(an))

    def kurz_setzen(self, text):
        self._kurz = str(text or "")
        self._zeigen(self.offen())

    def _zeigen(self, an):
        self.kopf.setArrowType(Qt.DownArrow if an else Qt.RightArrow)
        self.kopf.setText(self.titel + (f"   {self._kurz}" if self._kurz and not an else ""))
        self.inhalt.setVisible(an)

    def _klappen(self, an):
        self._zeigen(an)
        merken(self.db, self.name, an)
        self.geklappt.emit(an)
