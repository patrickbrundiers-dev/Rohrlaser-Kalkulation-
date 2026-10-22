"""Profilwahl nach Profilform und kleines Fenster 'Neues Profil' (Form, Abmessungen, Wandstärke): Profil-ID wie beim
STEP-Import (z. B. 'QR 40x40x3', 'RE 60x40x3', 'RR 48,3x2,6'), Querschnitt, Hüllkreis und Metergewicht rechnet das
Programm aus den Maßen. Genutzt im Schneidweg-Rechner (neue Position)."""
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
                               QVBoxLayout)

from . import normprofile
from .stammdaten import MIT_B, PROFILFORMEN, TRAEGER, flaeche_berechnet, huellkreis, zahl_als_text

ALLE = "alle Profilformen"
KUERZEL = {"Rundrohr": "RR", "Quadratrohr": "QR", "Rechteckrohr": "RE", "U-Profil": "U", "C-Profil": "C",
           "L-Profil": "L", "Flachstahl": "FL", "I-/H-Träger": "I", "T-Profil": "T"}
DICHTE_STAHL = 7.85     # g/cm³ für die Anzeige des Metergewichts


def _mm(x):
    return f"{x:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def profil_id(form, a, b=None, wand=None):
    """Profil-ID nach der Schreibweise des STEP-Imports; '' ohne Maße."""
    if not form or not a:
        return ""
    if form in ("I-/H-Träger", "T-Profil", "U-Profil") and b:      # Normprofil: 'IPE 200', 'HEB 160', 'UPN 100'
        norm = normprofile.name_aus_massen(form, a, b, wand)
        if norm:
            return norm
    k = KUERZEL.get(form, "P")
    if form == "Rundrohr":
        return f"{k} {_mm(a)}x{_mm(wand or 0)}"
    if form == "Quadratrohr":
        return f"{k} {_mm(a)}x{_mm(a)}x{_mm(wand or 0)}"
    if form == "Flachstahl":
        return f"{k} {_mm(a)}x{_mm(wand or 0)}"
    if form in MIT_B and b:
        return f"{k} {_mm(a)}x{_mm(b)}x{_mm(wand or 0)}"
    return f"{k} {_mm(a)}x{_mm(wand or 0)}"


def profile_der_form(profile, form):
    """Profil-IDs einer Form (ALLE oder leer: alle), sortiert."""
    return sorted((pid for pid, p in profile.items() if form in (None, "", ALLE) or p.get("form") == form),
                  key=str.lower)


class ProfilNeuDialog(QDialog):
    """Neues Profil aus Form und Maßen. werte() = Zeile für die Tabelle profile (ohne Materialpreis: der fehlt danach
    und steht als Hinweis in der Position)."""

    def __init__(self, parent, profile, form=None, formen=PROFILFORMEN):
        super().__init__(parent)
        self.profile = profile
        self.setWindowTitle("Neues Profil")
        lay = QVBoxLayout(self)
        hinweis = QLabel("Profil fehlt in den Stammdaten? Form und Maße eingeben; Querschnitt und Gewicht rechnet das "
                         "Programm. Den Materialpreis danach unter Einstellungen → Werkstoffe/Materialpreise oder als "
                         "Meterpreis im Angebot eintragen.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color:#5F6B7A")
        lay.addWidget(hinweis)
        f = QFormLayout()
        self.form = QComboBox()
        self.form.addItems([x for x in formen if x != "Sonderprofil"])
        if form in formen:
            self.form.setCurrentText(form)
        self.a, self.b, self.wand = (self._spin(1, 1000), self._spin(0, 1000), self._spin(0.1, 100))
        self.a.setValue(40)
        self.b.setValue(0)
        self.b.setSpecialValueText("–")
        self.wand.setValue(3)
        self.pid = QLineEdit()
        self.pid.setPlaceholderText("wird aus den Maßen vorgeschlagen")
        self.info = QLabel()
        self.a_text, self.b_text, self.w_text = QLabel(), QLabel(), QLabel()
        f.addRow("Profilform", self.form)
        f.addRow(self.a_text, self.a)
        f.addRow(self.b_text, self.b)
        f.addRow(self.w_text, self.wand)
        f.addRow("Profil-ID", self.pid)
        f.addRow("", self.info)
        lay.addLayout(f)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Profil anlegen")
        self.knoepfe.accepted.connect(self.accept)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        self._von_hand = False
        self.pid.textEdited.connect(lambda _: setattr(self, "_von_hand", True))
        for w in (self.a, self.b, self.wand):
            w.valueChanged.connect(self.pruefen)
        self.form.currentTextChanged.connect(self.pruefen)
        self.pid.textChanged.connect(self._info)
        self.pruefen()

    @staticmethod
    def _spin(von, bis):
        s = QDoubleSpinBox()
        s.setRange(von, bis)
        s.setDecimals(2)
        s.setSuffix(" mm")
        return s

    def werte(self):
        form = self.form.currentText()
        b = self.b.value() if form in MIT_B and self.b.value() > 0 else None
        a = self.a.value()
        return dict(profil_id=self.pid.text().strip(), form=form, a=a, b=b, wand=self.wand.value(),
                    bemerkung="im Schneidweg-Rechner angelegt")

    def pruefen(self, *_):
        form = self.form.currentText()
        texte = {"Rundrohr": ("Durchmesser", None, "Wandstärke"), "Quadratrohr": ("Kante", None, "Wandstärke"),
                 "Rechteckrohr": ("Breite (A)", "Höhe (B)", "Wandstärke"),
                 "Flachstahl": ("Breite", None, "Dicke")}.get(form)
        if texte is None:
            texte = ("Höhe (A)", "Flanschbreite (B)", "Stegdicke") if form in TRAEGER else \
                ("Abmessung A", "Abmessung B", "Wandstärke")
        self.a_text.setText(texte[0])
        self.b_text.setText(texte[1] or "Abmessung B")
        self.w_text.setText(texte[2])
        self.b.setEnabled(form in MIT_B)
        w = self.werte()
        if not self._von_hand:
            self.pid.setText(profil_id(form, w["a"], w["b"], w["wand"]))
        self._info()

    def fehler(self):
        w = self.werte()
        if not w["profil_id"]:
            return "Profil-ID fehlt."
        if w["profil_id"] in self.profile:
            return f"Profil {w['profil_id']} gibt es schon – oben auswählen."
        if w["form"] in MIT_B and not w["b"]:
            return "Abmessung B eingeben."
        if w["form"] in ("Rundrohr", "Quadratrohr", "Rechteckrohr") and 2 * w["wand"] >= min(w["a"], w["b"] or w["a"]):
            return "Wandstärke zu groß für die Abmessung."
        return ""

    def _info(self, *_):
        w = self.werte()
        fl, hk = flaeche_berechnet(w), huellkreis(w)
        teile = [f"Querschnitt {zahl_als_text(fl, 1)} mm² ≈ {zahl_als_text(fl * DICHTE_STAHL / 1000, 2)} kg/m Stahl"
                 if fl else "Querschnitt: bei dieser Form unter Einstellungen → Profile 'Fläche manuell' eintragen"]
        if hk:
            teile.append(f"Hüllkreis Ø {zahl_als_text(hk, 1)} mm")
        f = self.fehler()
        self.info.setText(" · ".join(teile) + (f"<br><span style='color:#B42318'>{f}</span>" if f else ""))
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(not f)
