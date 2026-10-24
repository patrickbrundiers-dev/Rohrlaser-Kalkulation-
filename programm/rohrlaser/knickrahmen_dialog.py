"""Dialog „Knickrahmen“ im Schneidweg-Rechner (Plan K1): Schenkel des Rahmens, Knickwinkel, Stegwand, Freistich,
Knickzugabe und K-Faktor eingeben; die Vorschau zeigt gestreckte Länge und Lage der Knicke (knickrahmen.rahmen)."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from . import knickrahmen as kn, rechnen, skizze as sk


def _liste(text):
    """'500; 300; 500; 300' -> [500.0, 300.0, 500.0, 300.0] (Semikolon oder Leerzeichen, Komma als Dezimalzeichen)."""
    out = []
    for teil in str(text or "").replace(";", " ").split():
        out.append(float(teil.replace(",", ".")))
    return out


class KnickrahmenDialog(QDialog):
    """k: vorhandener Block (knickrahmen.lesen) oder None; vorgaben: dict(z, freistich, k) aus den Einstellungen.
    Nach OK: block() = neuer Block, entfernen = True, wenn der Knickrahmen wegfallen soll."""

    def __init__(self, parent, profil, k=None, vorgaben=None):
        super().__init__(parent)
        self.setWindowTitle("Knickrahmen")
        self.profil, self.entfernen = profil, False
        v = dict(vorgaben or {})
        k = k or {}
        self.qs = sk.Querschnitt(profil)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Rahmen aus einem Rohr: an jeder Ecke ein V-Ausschnitt, nur die Stegwand bleibt stehen. "
                             "Schenkel = Außenmaße entlang der Stegwand in Reihenfolge ab Ende A."))
        form = QFormLayout()
        self.schenkel = QLineEdit("; ".join(rechnen.zahl(x, 1) for x in k.get("schenkel") or ()))
        self.schenkel.setPlaceholderText("z. B. 500; 300; 500; 300")
        self.schenkel.setToolTip("Außenmaße der Schenkel in mm, getrennt mit Semikolon; geschlossener Rahmen: alle "
                                 "Seiten, der Stoß liegt an der Ecke zwischen letztem und erstem Schenkel")
        beta = k.get("beta")
        self.beta = QLineEdit("; ".join(rechnen.zahl(x, 1) for x in beta) if isinstance(beta, list)
                              else rechnen.zahl(beta or 90.0, 1))
        self.beta.setToolTip("Knickwinkel β = Umlenkung am Knick (Rechteck 90°, Dreieck 120°); eine Zahl für alle "
                             "Knicke oder je Knick, getrennt mit Semikolon")
        self.geschlossen = QCheckBox("geschlossen (Anfang und Ende stoßen an einer Ecke zusammen)")
        self.geschlossen.setChecked(bool(k.get("geschlossen", True)))
        self.steg = QComboBox()
        self.steg.addItems(sk.seiten_anzeige(self.qs))
        self.steg.setCurrentText(sk.seite_anzeige(self.qs, k.get("steg") or kn.STEG_VORGABE))
        self.steg.setToolTip("Wand, die am Knick stehen bleibt (außen an der Ecke), von Ende A gesehen")
        self.freistich = self._spin(k.get("freistich", v.get("freistich")), 0, 20, " mm", "ohne")
        self.freistich.setToolTip("Bohrung an den Spitzen des V gegen Einreißen beim Knicken (0 = ohne)")
        self.z = self._spin(k.get("z", v.get("z")), -20, 20, " mm")
        self.z.setToolTip("Knickzugabe je Knick für die Korrektur nach eigener Erfahrung (+ = Rohr länger)")
        self.k = self._spin(k.get("k", v.get("k")) or kn.K_FAKTOR, 0.1, 1, "", stellen=2)
        self.k.setToolTip("Lage der neutralen Faser in der Stegwand (0,5 = Wandmitte) für den Ausgleichswert nach "
                          "DIN 6935")
        for titel, w in (("Schenkel [mm]", self.schenkel), ("Knickwinkel β [°]", self.beta), ("", self.geschlossen),
                         ("Stegwand", self.steg), ("Freistich-Ø", self.freistich), ("Knickzugabe je Knick", self.z),
                         ("K-Faktor", self.k)):
            form.addRow(titel, w)
        lay.addLayout(form)
        self.vorschau = QLabel()
        self.vorschau.setWordWrap(True)
        lay.addWidget(self.vorschau)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("V-Ausschnitte erzeugen")
        self.ok_knopf = knoepfe.button(QDialogButtonBox.Ok)
        weg = QPushButton("Knickrahmen entfernen")
        weg.setToolTip("Schenkel und alle V-Ausschnitte entfernen (die Teilelänge bleibt)")
        weg.setEnabled(bool(k.get("schenkel")))
        weg.clicked.connect(self._entfernen)
        knoepfe.addButton(weg, QDialogButtonBox.ResetRole)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        for w in (self.schenkel, self.beta):
            w.textChanged.connect(self.zeigen)
        self.geschlossen.toggled.connect(self.zeigen)
        self.steg.currentTextChanged.connect(self.zeigen)
        for w in (self.freistich, self.z, self.k):
            w.valueChanged.connect(self.zeigen)
        self.zeigen()

    def _spin(self, wert, von, bis, suffix, leer=None, stellen=1):
        s = QDoubleSpinBox()
        s.setRange(von, bis)
        s.setDecimals(stellen)
        s.setSuffix(suffix)
        if leer:
            s.setSpecialValueText(leer)
        s.setValue(kn._z(wert))
        return s

    def block(self):
        """Block 'knickrahmen' aus den Feldern; ValueError bei unlesbaren Zahlen."""
        try:
            schenkel, beta = _liste(self.schenkel.text()), _liste(self.beta.text())
        except ValueError:
            raise ValueError("Knickrahmen: Schenkel und Knickwinkel als Zahlen eingeben.")
        return dict(schenkel=schenkel, beta=beta[0] if len(beta) == 1 else beta,
                    geschlossen=self.geschlossen.isChecked(), steg=sk.seite_name(self.qs, self.steg.currentText()),
                    freistich=self.freistich.value() or None, z=self.z.value() or None, k=self.k.value(),
                    herkunft=kn.HERKUNFT_HAND)

    def zeigen(self, *_):
        try:
            r = kn.rahmen(self.block(), self.profil)
        except ValueError as f:
            self.vorschau.setText(f"<span style='color:#B42318'>{f}</span>")
            self.ok_knopf.setEnabled(False)
            return
        lagen = ", ".join(f"K{x['nr']} bei {rechnen.zahl(x['x'], 1)}" for x in r["knicke"])
        self.vorschau.setText(f"<b>{kn.kurz(r)}</b><br>Knicke (Mitte V ab Ende A): {lagen} mm<br>V-Ausschnitt: Breite "
                              f"{rechnen.zahl(r['knicke'][0]['w'], 1)} mm, Schnittlänge "
                              f"{rechnen.zahl(r['knicke'][0]['laenge'], 1)} mm je Knick"
                              + (f"<br>Enden: Gehrung {rechnen.zahl(r['enden']['winkel'], 1)}° (Stoß)"
                                 if r["enden"] else ""))
        self.ok_knopf.setEnabled(True)

    def _entfernen(self):
        self.entfernen = True
        self.accept()
