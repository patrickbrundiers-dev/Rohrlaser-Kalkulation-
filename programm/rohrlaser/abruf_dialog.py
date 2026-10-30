"""Fenster „Abruf-/Rahmenangebot“ (Patrick 30.10.2026, abruf.py): Jahresmenge und Abrufmenge von–bis, Laufzeit,
Material je Abruf (Materialklausel) oder bevorratet mit Lagerzins. Die Stückzahlen der Positionen bleiben, wie sie
sind; der Hinweis sagt, dass sie dem kleinsten Abruf entsprechen sollen."""
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QVBoxLayout

from . import abruf
from .eingabe import RechenSpin, RechenSpinGanz
from .stammdaten import ABRUF_JE, ABRUF_LAGER, ABRUF_MATERIAL

FELDER = ("abruf_jahr_von", "abruf_jahr_bis", "abruf_von", "abruf_bis", "abruf_laufzeit", "abruf_material",
          "abruf_lagerzins")


def _ganz(von, bis, wert, schritt=100):
    w = RechenSpinGanz()
    w.setRange(von, bis)
    w.setGroupSeparatorShown(True)
    w.setSingleStep(schritt)
    w.setValue(int(wert or 0))
    return w


class AbrufDialog(QDialog):
    """kopf = Angebotskopf, einst = Einstellungen (Vorgaben Laufzeit und Lagerzins), stueck = größte Stückzahl der
    Positionen (Vorschlag für den kleinsten Abruf)."""

    def __init__(self, parent, kopf, einst, stueck=None):
        super().__init__(parent)
        self.setWindowTitle("Abruf-/Rahmenangebot")
        k, e = kopf or {}, einst or {}
        von = k.get("abruf_von") or (int(stueck) if stueck else None)
        self.jahr_von = _ganz(0, 100000000, k.get("abruf_jahr_von") or (von * 10 if von else 0))
        self.jahr_bis = _ganz(0, 100000000, k.get("abruf_jahr_bis") or self.jahr_von.value())
        self.von = _ganz(0, 10000000, von, 10)
        self.bis = _ganz(0, 10000000, k.get("abruf_bis") or von, 10)
        self.laufzeit = _ganz(1, 120, k.get("abruf_laufzeit") or e.get("abruf_laufzeit") or 12, 1)
        self.material = QComboBox()
        self.material.addItems(list(ABRUF_MATERIAL))
        self.material.setCurrentText(k.get("abruf_material") or ABRUF_JE)
        self.zins = RechenSpin()
        self.zins.setRange(0, 100)
        self.zins.setDecimals(1)
        z = k.get("abruf_lagerzins")
        self.zins.setValue(z if isinstance(z, (int, float)) else (e.get("abruf_lagerzins") or 0))
        form = QFormLayout()
        for titel, a, b in (("Jahresmenge [Stk.]", self.jahr_von, self.jahr_bis),
                            ("Abrufmenge [Stk.]", self.von, self.bis)):
            z_ = QHBoxLayout()
            z_.addWidget(QLabel("von"))
            z_.addWidget(a, 1)
            z_.addWidget(QLabel("bis"))
            z_.addWidget(b, 1)
            form.addRow(titel, z_)
        form.addRow("Laufzeit / Preisbindung [Monate]", self.laufzeit)
        form.addRow("Material", self.material)
        form.addRow("Lagerzins [% p. a.]", self.zins)
        self.info = QLabel()
        self.info.setWordWrap(True)
        hinweis = QLabel("Die Stückzahlen der Positionen sind der kleinste Abruf. Rüsten und Fracht zählen je Abruf, "
                         "Programmierung und Musterteile werden auf die kleinste Jahresmenge verteilt. Größere "
                         "Abrufe legt der Knopf „Abrufstufen anlegen“ (Reiter Staffeln) als Stufen an. Bevorratet: "
                         "Lagerzins auf das Material, im Mittel der halbe Jahresbedarf.")
        hinweis.setWordWrap(True)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.info)
        lay.addWidget(hinweis)
        lay.addWidget(knoepfe)
        for w in (self.jahr_von, self.jahr_bis, self.von, self.bis, self.laufzeit, self.zins):
            w.valueChanged.connect(self._info)
        self.material.currentTextChanged.connect(self._info)
        self._info()

    def werte(self):
        """Kopffelder des Abruf-Angebots (abruf = ja); bis kleiner als von wird auf von gesetzt."""
        jv, av = self.jahr_von.value() or None, self.von.value() or None
        return dict(abruf="ja", abruf_jahr_von=jv, abruf_jahr_bis=max(self.jahr_bis.value(), jv or 0) or None,
                    abruf_von=av, abruf_bis=max(self.bis.value(), av or 0) or None,
                    abruf_laufzeit=self.laufzeit.value(),
                    abruf_material=None if self.material.currentText() == ABRUF_JE else ABRUF_LAGER,
                    abruf_lagerzins=self.zins.value())

    def _info(self, *_):
        self.zins.setEnabled(self.material.currentText() == ABRUF_LAGER)
        self.info.setText(abruf.kurz(self.werte()) or "")
