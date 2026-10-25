"""Fenster „Rahmen-Assistent“ (Plan „Baugruppen automatisch“ A8): Profil, Werkstoff, Form, Ecken und Außenmaße
eingeben, die Vorschau nennt die Rohre; nach OK steht in self.ergebnis dict(erg = rahmen.bauen(...), profil_id,
werkstoff_id, saetze, name)."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QVBoxLayout)

from . import rahmen
from .eingabe import RechenSpin, RechenSpinGanz


def _zahl(von, bis, wert, schritt=10.0):
    f = RechenSpin()
    f.setRange(von, bis)
    f.setDecimals(1)
    f.setSingleStep(schritt)
    f.setSuffix(" mm")
    f.setValue(wert)
    return f


class RahmenDialog(QDialog):
    def __init__(self, parent, profile, werkstoffe, werkstoff=None):
        super().__init__(parent)
        self.setWindowTitle("Rahmen-Assistent")
        self.profile = {pid: p for pid, p in (profile or {}).items() if (p or {}).get("form") in rahmen.PROFILE}
        self.ergebnis = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Rechteckrahmen oder Quader aus Rohr ohne STEP-Datei: die Rohre werden Positionen eines "
                             "Satzes, mit Einbaulage und Stößen wie aus dem STEP-Import (Satz in 3D, Steckverbindungen, "
                             "Vorschläge, Montagefolge)."))
        lay.itemAt(0).widget().setWordWrap(True)
        form = QFormLayout()
        self.profil = QComboBox()
        self.profil.addItems(sorted(self.profile, key=str.lower))
        self.werkstoff = QComboBox()
        self.werkstoff.addItems([""] + sorted(werkstoffe or (), key=str.lower))
        if werkstoff in (werkstoffe or ()):
            self.werkstoff.setCurrentText(werkstoff)
        self.form = QComboBox()
        self.form.addItems(rahmen.FORMEN)
        self.ecken = QComboBox()
        self.ecken.addItems(rahmen.ECKEN)
        self.b, self.h, self.t = _zahl(10, 20000, 1000), _zahl(10, 20000, 600), _zahl(10, 20000, 400)
        self.hochkant = QCheckBox("Rechteckrohr hochkant (Maß a in der Rahmenebene)")
        self.saetze = RechenSpinGanz()
        self.saetze.setRange(1, 100000)
        self.name = QLineEdit()
        self.name.setPlaceholderText("leer = Rahmen B×H")
        for t, w in (("Profil", self.profil), ("Werkstoff", self.werkstoff), ("Form", self.form),
                     ("Ecken", self.ecken), ("Breite B (außen)", self.b), ("Höhe H (außen)", self.h),
                     ("Tiefe T (außen, Quader)", self.t), ("", self.hochkant), ("Sätze", self.saetze),
                     ("Name des Satzes", self.name)):
            form.addRow(t, w)
        lay.addLayout(form)
        self.vorschau = QLabel()
        self.vorschau.setWordWrap(True)
        lay.addWidget(self.vorschau)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.accepted.connect(self._ok)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        for w in (self.profil, self.form, self.ecken):
            w.currentTextChanged.connect(lambda _: self.neu())
        for w in (self.b, self.h, self.t):
            w.valueChanged.connect(lambda _: self.neu())
        self.hochkant.toggled.connect(lambda _: self.neu())
        self.setMinimumWidth(460)
        self.neu()

    def satz_name(self):
        return self.name.text().strip() or f"Rahmen {self.b.value():g}×{self.h.value():g}" + (
            f"×{self.t.value():g}" if self.form.currentText() == rahmen.QUADER else "")

    def berechnen(self):
        """rahmen.bauen mit den Eingaben; (Ergebnis, Fehlertext)."""
        p = self.profile.get(self.profil.currentText())
        if not p:
            return None, "Keine Quadrat-, Rechteck- oder Rundrohre in den Profilen."
        try:
            return rahmen.bauen(p, self.form.currentText(), self.b.value(), self.h.value(), self.t.value(),
                                self.ecken.currentText(), self.hochkant.isChecked()), None
        except ValueError as f:
            return None, str(f).replace("Rahmen-Assistent: ", "")

    def neu(self):
        p = self.profile.get(self.profil.currentText()) or {}
        self.hochkant.setEnabled(p.get("form") == "Rechteckrohr")
        self.t.setEnabled(self.form.currentText() == rahmen.QUADER)
        erg, fehler = self.berechnen()
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(erg is not None)
        if fehler:
            self.vorschau.setText(f"<span style='color:#C62828'>{fehler}</span>")
            return
        self.vorschau.setText("<b>Rohre je Satz:</b><br>" + "<br>".join(rahmen.text(erg)) + (
            "<br>Steckverbindungen an allen Stößen (Satz in 3D öffnet danach)." if erg["stecken"] else ""))

    def _ok(self):
        erg, fehler = self.berechnen()
        if erg is None:
            return
        self.ergebnis = dict(erg=erg, profil_id=self.profil.currentText(),
                             werkstoff_id=self.werkstoff.currentText() or None, saetze=self.saetze.value(),
                             name=self.satz_name())
        self.accept()
