"""Dialog 'Gegenrohr …' (Plan 3D-Editor G2, Schritt 3E-7): ein Ende des Rohrs auf ein Gegenrohr setzen – rund oder
rechteckig, schräg, mit Versatz, Achse waagerecht oder senkrecht. Das Programm rechnet die Schnittkurve
(durchdringung.py) und zeigt sie sofort; das Gegenrohr erscheint im 3D als pinker Hilfskörper.

Ergebnis (Eingabe des Endes 'gegen'): dict(d, t, r, winkel, versatz, lage) bzw. None (kein Gegenrohr).
"""
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QPushButton, QVBoxLayout)

from . import durchdringung as dd, rechnen, schneidweg as sw, skizze as sk
from .eingabe import RechenSpin

RUND, ECKIG = "rund", "rechteckig"
LAGE_TEXT = {dd.WAAGERECHT: "waagerecht (Achse quer, Sattel von vorne sichtbar)",
             dd.SENKRECHT: "senkrecht (Achse hoch, Sattel von oben sichtbar)"}


def _spin(minimum, maximum, wert, einheit, tipp, stellen=1):
    f = RechenSpin()
    f.setRange(minimum, maximum)
    f.setDecimals(stellen)
    f.setSuffix(f" {einheit}")
    f.setValue(wert)
    f.setToolTip(tipp)
    return f


class GegenrohrDialog(QDialog):
    def __init__(self, profil, gegen=None, titel="Ende", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Gegenrohr – {titel}")
        self.qs = sk.Querschnitt(profil)
        self.entfernt = False
        g = dict(gegen or {})
        lay = QVBoxLayout(self)
        info = QLabel("Das Ende wird so geschnitten, dass es genau auf dem Gegenrohr sitzt. Winkel 0° = rechtwinklig; "
                      "+ = Rohr zur Seite vorne bzw. oben länger. Versatz = Achse des Gegenrohrs quer verschoben.")
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        self.form = QComboBox()
        self.form.addItems((RUND, ECKIG))
        self.form.setCurrentText(ECKIG if sw._z(g.get("t")) else RUND)
        self.d = _spin(1, 5000, sw._z(g.get("d")) or round(max(self.qs.B, self.qs.H) * 1.5, 1), "mm",
                       "Ø bzw. Breite des Gegenrohrs quer zum Rohr")
        self.t = _spin(1, 5000, sw._z(g.get("t")) or max(self.qs.B, self.qs.H), "mm",
                       "Tiefe des rechteckigen Gegenrohrs (in Richtung des Rohrs)")
        self.r = _spin(0, 500, sw._z(g.get("r")), "mm", "Eckradius außen des rechteckigen Gegenrohrs")
        self.winkel = _spin(-80, 80, sw._z(g.get("winkel")), "°", "Abweichung der Achsen von rechtwinklig")
        self.versatz = _spin(-2500, 2500, sw._z(g.get("versatz")), "mm",
                             "Achse des Gegenrohrs quer zur Rohrachse verschoben (0 = mittig)")
        self.lage = QComboBox()
        for k, text in LAGE_TEXT.items():
            self.lage.addItem(text, k)
        self.lage.setCurrentIndex(max(0, self.lage.findData(g.get("lage") or dd.WAAGERECHT)))
        for titel_, f in (("Form", self.form), ("Ø bzw. Breite quer", self.d), ("Tiefe", self.t),
                          ("Eckradius", self.r), ("Winkel", self.winkel), ("Versatz", self.versatz),
                          ("Lage der Achse", self.lage)):
            form.addRow(titel_, f)
        lay.addLayout(form)
        self.ergebnis = QLabel()
        self.ergebnis.setWordWrap(True)
        lay.addWidget(self.ergebnis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        weg = QPushButton("Kein Gegenrohr")
        weg.setToolTip("Gegenrohr an diesem Ende entfernen (gerader Schnitt)")
        weg.setEnabled(bool(gegen))
        weg.clicked.connect(self._entfernen)
        knoepfe.addButton(weg, QDialogButtonBox.ResetRole)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.ok = knoepfe.button(QDialogButtonBox.Ok)
        for f in (self.d, self.t, self.r, self.winkel, self.versatz):
            f.valueChanged.connect(self._rechnen)
        self.form.currentTextChanged.connect(self._rechnen)
        self.lage.currentIndexChanged.connect(self._rechnen)
        self._rechnen()

    def wert(self):
        eckig = self.form.currentText() == ECKIG
        g = dict(d=round(self.d.value(), 3))
        for k, v in (("t", self.t.value() if eckig else 0), ("r", self.r.value() if eckig else 0),
                     ("winkel", self.winkel.value()), ("versatz", self.versatz.value())):
            if v:
                g[k] = round(v, 3)
        if self.lage.currentData() == dd.SENKRECHT:
            g["lage"] = dd.SENKRECHT
        return g

    def _rechnen(self, *_):
        eckig = self.form.currentText() == ECKIG
        self.t.setEnabled(eckig)
        self.r.setEnabled(eckig)
        try:
            e = dd.ende_gegen(self.qs, self.wert())
            self.ergebnis.setText(f"Schnittlänge {rechnen.zahl(e['laenge'], 1)} mm, Ausschnitt "
                                  f"{rechnen.zahl(e['tiefe'], 1)} mm tief (längste bis kürzeste Stelle)")
            self.ok.setEnabled(True)
        except ValueError as f:
            self.ergebnis.setText(f"<span style='color:#B42318'>{f}</span>")
            self.ok.setEnabled(False)

    def _entfernen(self):
        self.entfernt = True
        self.accept()


def fragen(profil, gegen=None, titel="Ende", parent=None):
    """Dialog zeigen: (geändert, Gegenrohr oder None)."""
    dlg = GegenrohrDialog(profil, gegen, titel, parent)
    if dlg.exec() != QDialog.Accepted:
        return False, gegen
    return True, None if dlg.entfernt else dlg.wert()
