"""Einstellungsseite „Darstellung und Bedienoberfläche“ (Patrick 25.11.2026): Einfacher Modus oder
Experten-Pro-Modus wählen. Gilt nur für den angemeldeten Benutzer bzw. diesen Arbeitsplatz (bedienmodus.py), nie
für die Kollegen; die Seite ist nie durch den Admin-Schutz gesperrt (admin_schutz.NIE)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QRadioButton, QVBoxLayout, QWidget

from . import bedienmodus as bm


class BedienmodusSeite(QWidget):
    schluessel = "e_bedienmodus"
    titel = "Darstellung und Bedienoberfläche"

    def __init__(self, fenster):
        super().__init__()
        self.f = fenster
        self.db = fenster.db
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        kopf = QLabel(f"<b style='font-size:13pt'>{self.titel}</b>")
        kopf.setTextFormat(Qt.RichText)
        lay.addWidget(kopf)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet("color: #5F6B7A;")
        lay.addWidget(self.hinweis)
        self.gruppe = QButtonGroup(self)
        self.wahl = {}
        reihe = QHBoxLayout()
        reihe.setSpacing(12)
        for modus, titel, text in bm.MODI:
            karte = QFrame()
            karte.setObjectName("e_modus_karte")
            karte.setStyleSheet("QFrame#e_modus_karte { background: #FFFFFF; border: 1px solid #D5DBE3; "
                                "border-radius: 10px; }")
            v = QVBoxLayout(karte)
            v.setContentsMargins(14, 12, 14, 12)
            knopf = QRadioButton(titel)
            knopf.setStyleSheet("font-size: 11pt; font-weight: 600;")
            self.gruppe.addButton(knopf)
            self.wahl[modus] = knopf
            v.addWidget(knopf)
            beschr = QLabel(text)
            beschr.setWordWrap(True)
            beschr.setStyleSheet("color: #5F6B7A;")
            v.addWidget(beschr)
            v.addStretch(1)
            reihe.addWidget(karte, 1)
        lay.addLayout(reihe)
        unten = QLabel("Beide Oberflächen arbeiten mit denselben Kalkulationen, Daten und Preisen. Ein Wechsel "
                       f"verliert nichts; die geöffnete Kalkulation bleibt offen. Schnell umschalten: unten rechts "
                       f"in der Statusleiste, Menü Ansicht → Einfacher Modus oder {bm_taste()}.")
        unten.setWordWrap(True)
        lay.addWidget(unten)
        lay.addStretch(1)
        for modus, knopf in self.wahl.items():
            knopf.toggled.connect(lambda an, m=modus: self._gewaehlt(m) if an else None)
        self.neu_laden()

    def neu_laden(self):
        k = bm.benutzer(self.db)
        self.hinweis.setText(("Gilt nur für Sie (" + k + ")" if k else "Gilt nur für diesen Arbeitsplatz")
                             + "; andere Mitarbeiter und Arbeitsplätze behalten ihre eigene Wahl. Die Einstellung "
                             "bleibt nach einem Neustart erhalten.")
        aktuell = bm.modus(self.db)
        for modus, knopf in self.wahl.items():
            knopf.blockSignals(True)
            knopf.setChecked(modus == aktuell)
            knopf.blockSignals(False)

    def _gewaehlt(self, modus):
        from . import einfach_seite
        if modus != getattr(self.f, "modus", None):
            einfach_seite.umschalten(self.f, modus)

    def schutz_setzen(self, _gesperrt):
        """Nie gesperrt: jeder Mitarbeiter wählt seine Oberfläche selbst."""
        self.setEnabled(True)


def bm_taste():
    from .einfach_seite import TASTE
    return TASTE.replace("Ctrl", "Strg")
