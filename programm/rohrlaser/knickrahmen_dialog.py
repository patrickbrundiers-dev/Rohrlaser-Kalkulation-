"""Dialog „Knickrahmen“ im Schneidweg-Rechner (Plan K1): Schenkel des Rahmens, Knickwinkel, Stegwand, Freistich,
Knickzugabe und K-Faktor eingeben; die Vorschau zeigt gestreckte Länge und Lage der Knicke (knickrahmen.rahmen)."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from . import knickrahmen as kn, rechnen, skizze as sk
from .eingabe import RechenSpin


def _liste(text):
    """'500; 300; 500; 300' -> [500.0, 300.0, 500.0, 300.0] (Semikolon oder Leerzeichen, Komma als Dezimalzeichen)."""
    out = []
    for teil in str(text or "").replace(";", " ").split():
        out.append(float(teil.replace(",", ".")))
    return out


def _schraeg_haken(k):
    h = QCheckBox("Innenwand schräg (3D, Kopf um β/2 geschwenkt)")
    h.setChecked(bool((k or {}).get("schraeg")))
    h.setToolTip("Die Wand gegenüber der Stegwand schräg schneiden, damit die Stirnflächen nach dem Knicken voll "
                 "aufeinanderliegen (braucht eine Maschine mit 3D). Aus = gerader Schnitt; knicken geht auch, innen "
                 "bleibt ein kleiner Keilspalt.")
    return h


def _spin(wert, von, bis, suffix, leer=None, stellen=1):
    s = RechenSpin()
    s.setRange(von, bis)
    s.setDecimals(stellen)
    s.setSuffix(suffix)
    if leer:
        s.setSpecialValueText(leer)
    s.setValue(kn._z(wert))
    return s


def _vorschau(r):
    lagen = ", ".join(f"K{x['nr']} bei {rechnen.zahl(x['x'], 1)}" for x in r["knicke"])
    return (f"<b>{kn.kurz(r)}</b><br>Knicke (Mitte V ab Ende A): {lagen} mm<br>V-Ausschnitt: Breite "
            f"{rechnen.zahl(r['knicke'][0]['w'], 1)} mm, Schnittlänge {rechnen.zahl(r['knicke'][0]['laenge'], 1)} mm "
            "je Knick" + (f"<br>Enden: Gehrung {rechnen.zahl(r['enden']['winkel'], 1)}° (Stoß)" if r["enden"] else ""))


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
        self.schraeg = _schraeg_haken(k)
        for titel, w in (("Schenkel [mm]", self.schenkel), ("Knickwinkel β [°]", self.beta), ("", self.geschlossen),
                         ("Stegwand", self.steg), ("Freistich-Ø", self.freistich), ("Knickzugabe je Knick", self.z),
                         ("K-Faktor", self.k), ("", self.schraeg)):
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
        self.schraeg.toggled.connect(self.zeigen)
        self.steg.currentTextChanged.connect(self.zeigen)
        for w in (self.freistich, self.z, self.k):
            w.valueChanged.connect(self.zeigen)
        self.zeigen()

    def _spin(self, *a, **kw):
        return _spin(*a, **kw)

    def block(self):
        """Block 'knickrahmen' aus den Feldern; ValueError bei unlesbaren Zahlen."""
        try:
            schenkel, beta = _liste(self.schenkel.text()), _liste(self.beta.text())
        except ValueError:
            raise ValueError("Knickrahmen: Schenkel und Knickwinkel als Zahlen eingeben.")
        return dict(schenkel=schenkel, beta=beta[0] if len(beta) == 1 else beta,
                    geschlossen=self.geschlossen.isChecked(), steg=sk.seite_name(self.qs, self.steg.currentText()),
                    freistich=self.freistich.value() or None, z=self.z.value() or None, k=self.k.value(),
                    schraeg=self.schraeg.isChecked() or None, herkunft=kn.HERKUNFT_HAND)

    def zeigen(self, *_):
        try:
            r = kn.rahmen(self.block(), self.profil)
        except ValueError as f:
            self.vorschau.setText(f"<span style='color:#B42318'>{f}</span>")
            self.ok_knopf.setEnabled(False)
            return
        self.vorschau.setText(_vorschau(r))
        self.ok_knopf.setEnabled(True)

    def _entfernen(self):
        self.entfernen = True
        self.accept()


class KnickverbindungDialog(QDialog):
    """Knickverbindung aus Einzelrohren der STEP-Datei (Plan K1-2): zeigt die erkannte Kette (Schenkel, Knickwinkel,
    Stegwand) und lässt ersten Schenkel bzw. Stoß, Laufrichtung, Freistich, Knickzugabe, K-Faktor und schräge
    Innenwand wählen. Nach OK: kette = Ergebnis von knickverbindung.kette, werte() = Freistich, z, k, schraeg.
    koerper=True: Knickrahmen aus einem Körper bearbeiten (messwerte = seine Rohrstücke, vorgaben mit start)."""

    def __init__(self, parent, messwerte, indizes, vorgaben=None, koerper=False):
        from . import knickverbindung as kv
        super().__init__(parent)
        self.setWindowTitle("Knickrahmen bearbeiten" if koerper else "Knickverbindung erstellen")
        self.messwerte, self.indizes, self.kv = messwerte, list(indizes), kv
        v = dict(vorgaben or {})
        self.kette = kv.kette(messwerte, self.indizes, v.get("start"))      # ValueError: Aufrufer meldet den Grund
        m0 = messwerte[self.kette["teile"][0]["i"]]
        self.profil = dict(form=m0.get("profilform"), a=kn._z(m0.get("abm_a")),
                           b=kn._z(m0.get("abm_b")) or kn._z(m0.get("abm_a")), wand=kn._z(m0.get("wandstaerke")))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Der Körper ist ein Knickrahmen: eine Position mit dem gestreckten Rohr und einem "
                             "V-Ausschnitt je Ecke. Die Schenkel sind an den Ecken getrennt gemessen." if koerper else
                             "Die markierten Rohre stoßen mit Gehrung aneinander und werden ein Knickrahmen: eine "
                             "Position mit dem gestreckten Rohr und einem V-Ausschnitt je Ecke. Die Rohre werden nicht "
                             "mehr einzeln übernommen."))
        form = QFormLayout()
        self.start = QComboBox()
        for i in self.indizes:
            self.start.addItem(str(messwerte[i].get("artikel") or i), i)
        self.start.setCurrentIndex(self.indizes.index(self.kette["teile"][0]["i"]))
        self.start.setToolTip("Erster Schenkel (Ende A des gestreckten Rohrs); beim geschlossenen Rahmen liegt der "
                              "Stoß an seinem Anfang")
        self.umkehren = QCheckBox("Laufrichtung umkehren")
        self.freistich = _spin(v.get("freistich"), 0, 20, " mm", "ohne")
        self.z = _spin(v.get("z"), -20, 20, " mm")
        self.k = _spin(v.get("k") or kn.K_FAKTOR, 0.1, 1, "", stellen=2)
        self.schraeg = _schraeg_haken(None)
        self.schraeg.setChecked(bool(v.get("schraeg")))
        for titel, w in (("Erster Schenkel", self.start), ("", self.umkehren), ("Freistich-Ø", self.freistich),
                         ("Knickzugabe je Knick", self.z), ("K-Faktor", self.k), ("", self.schraeg)):
            form.addRow(titel, w)
        lay.addLayout(form)
        self.vorschau = QLabel()
        self.vorschau.setWordWrap(True)
        lay.addWidget(self.vorschau)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_knopf = knoepfe.button(QDialogButtonBox.Ok)
        self.ok_knopf.setText("Übernehmen" if koerper else "Knickverbindung erstellen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.start.currentIndexChanged.connect(self.zeigen)
        self.umkehren.toggled.connect(self.zeigen)
        self.schraeg.toggled.connect(self.zeigen)
        for w in (self.freistich, self.z, self.k):
            w.valueChanged.connect(self.zeigen)
        self.zeigen()

    def werte(self):
        return dict(freistich=self.freistich.value() or None, z=self.z.value() or None, kf=self.k.value(),
                    schraeg=self.schraeg.isChecked())

    def zeigen(self, *_):
        try:
            self.kette = self.kv.kette(self.messwerte, self.indizes, self.start.currentData(),
                                       self.umkehren.isChecked())
            w = self.werte()
            r = kn.rahmen(dict(self.kette, freistich=w["freistich"], z=w["z"], k=w["kf"], schraeg=w["schraeg"]),
                          self.profil)
        except ValueError as f:
            self.vorschau.setText(f"<span style='color:#B42318'>{f}</span>")
            self.ok_knopf.setEnabled(False)
            return
        reihe = " → ".join(f"{self.messwerte[t['i']].get('artikel')} ({rechnen.zahl(t['laenge'], 1)} mm"
                           + (", umgekehrt" if t["umgekehrt"] else "") + ")" for t in self.kette["teile"])
        self.vorschau.setText(f"Schenkel: {reihe}<br>Stegwand {self.kette['steg']}<br>" + _vorschau(r))
        self.ok_knopf.setEnabled(True)
