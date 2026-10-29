"""Profilwahl nach Profilform und kleines Fenster 'Neues Profil' (Form, Abmessungen, Wandstärke): Profil-ID wie beim
STEP-Import (z. B. 'QR 40x40x3', 'RE 60x40x3', 'RR 48,3x2,6'), Querschnitt, Hüllkreis und Metergewicht rechnet das
Programm aus den Maßen. Genutzt im Schneidweg-Rechner (neue Position), in der Schnellzeile und in der Profilspalte
des Angebots: eine eingetippte Abmessung, die in den Stammdaten fehlt („RE 70x30x3“), füllt das Fenster vor
(vorschlag, Patrick 28.10.2026)."""
import re

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMenu,
                               QVBoxLayout)

from . import normprofile
from .stammdaten import MIT_B, PROFILFORMEN, TRAEGER, flaeche_berechnet, huellkreis, zahl_als_text
from .eingabe import RechenSpin

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


# Kürzel einer getippten Abmessung -> Profilform (Groß-/Kleinschreibung egal)
FORM_KUERZEL = {"RR": "Rundrohr", "RO": "Rundrohr", "ROHR": "Rundrohr", "Ø": "Rundrohr", "D": "Rundrohr",
                "QR": "Quadratrohr", "VK": "Quadratrohr", "RE": "Rechteckrohr", "RK": "Rechteckrohr",
                "FL": "Flachstahl", "FLA": "Flachstahl", "L": "L-Profil", "U": "U-Profil", "C": "C-Profil"}
_ZAHL = r"\d+(?:[.,]\d+)?"


def vorschlag(text):
    """Profilform und Maße aus einer getippten Abmessung, die in den Stammdaten fehlt: 'RE 70x30x3', 'rr 60,3 x 2,9',
    'QR 50x4' (= QR 50x50x4), 'L 50x5' (gleichschenklig), 'FL 40x5', ohne Kürzel '70x30x3' = Rechteckrohr, '50x50x4'
    = Quadratrohr, '60,3x2,9' = Rundrohr; Normprofile ('IPE 200') wie in den Stammdaten. Ergebnis dict(form, a, b,
    wand, profil_id) oder None (keine Abmessung erkennbar). Das Fenster zeigt den Vorschlag, der Nutzer bestätigt."""
    t = re.sub(r"\s*[x×*]\s*", "x", " ".join(str(text or "").split()), flags=re.IGNORECASE)
    if not t:
        return None
    from .optimierung import profil_aus_name
    n = profil_aus_name(t)
    if n is not None and n["form"] in TRAEGER + ("U-Profil",) and n.get("flaeche_manuell"):    # IPE 200, UPN 100
        kurz, _, rest = t.partition(" ")
        return dict(n, profil_id=f"{kurz.upper()} {rest}".strip())     # 'I 100x55x5x8' behält die Flanschdicke
    m = re.fullmatch(rf"(Ø|[A-Za-zÄÖÜäöü]+)?\.?\s*({_ZAHL}(?:x{_ZAHL})+)", t)
    if not m:
        return None
    kurz = (m.group(1) or "").upper()
    z = [float(x.replace(",", ".")) for x in m.group(2).split("x")]
    form = FORM_KUERZEL.get(kurz) if kurz else \
        {2: "Rundrohr", 3: "Quadratrohr" if z[0] == z[1] else "Rechteckrohr"}.get(len(z))
    if form is None:
        return None
    if form in ("Rundrohr", "Flachstahl") and len(z) == 2:
        a, b, wand = z[0], None, z[1]
    elif form == "Quadratrohr" and len(z) in (2, 3) and (len(z) == 2 or z[0] == z[1]):
        a, b, wand = z[0], None, z[-1]
    elif form == "L-Profil" and len(z) == 2:
        a, b, wand = z[0], z[0], z[1]
    elif form in MIT_B and len(z) == 3:
        a, b, wand = z
    else:
        return None
    if a <= 0 or wand <= 0:
        return None
    return dict(form=form, a=a, b=b, wand=wand, profil_id=profil_id(form, a, b, wand))


def anbieten(parent, text, anlegen, wo=None):
    """Kleines Menü unter dem Eingabefeld, wenn eine getippte Abmessung in den Stammdaten fehlt (Patrick 28.10.2026):
    „Abmessung … neu anlegen …“ ruft anlegen(text) auf (öffnet ProfilNeuDialog), „Nicht anlegen“ schließt es.
    Nicht blockierend (popup); nur bei Text mit Zahl. wo = Bildschirmpunkt (leer = Mauszeiger). Ergebnis: das Menü
    oder None."""
    text = " ".join(str(text or "").split())
    if not re.search(r"\d", text):
        return None
    vor = vorschlag(text)
    m = QMenu(parent)
    m.setToolTipsVisible(True)
    kopf = m.addAction(f"„{text}“ fehlt in den Stammdaten")
    kopf.setEnabled(False)
    neu = m.addAction(f"Abmessung {vor['profil_id'] if vor else text} neu anlegen …")
    neu.setToolTip("Öffnet das Fenster mit Form und Maßen aus der Eingabe; danach steht die Abmessung unter "
                   "Einstellungen → Profile und die Eingabe läuft mit ihr weiter.")
    m.addAction("Nicht anlegen")
    neu.triggered.connect(lambda: anlegen(text))
    m.setDefaultAction(neu)
    m.setActiveAction(neu)
    m.popup(wo if wo is not None else QCursor.pos())
    return m


def profile_der_form(profile, form):
    """Profil-IDs einer Form (ALLE oder leer: alle), sortiert."""
    return sorted((pid for pid, p in profile.items() if form in (None, "", ALLE) or p.get("form") == form),
                  key=str.lower)


class ProfilNeuDialog(QDialog):
    """Neues Profil aus Form und Maßen. werte() = Zeile für die Tabelle profile (ohne Materialpreis: der fehlt danach
    und steht als Hinweis in der Position). eingabe = getippte Abmessung (Schnellzeile, Profilspalte): Form, Maße und
    Profil-ID daraus vorbelegt (vorschlag). Lässt sich der Querschnitt nicht rechnen (C-Profil, Träger ohne
    Normtabelle), fragt das Fenster die Fläche ab."""

    def __init__(self, parent, profile, form=None, formen=PROFILFORMEN, eingabe=None,
                 bemerkung="im Schneidweg-Rechner angelegt"):
        super().__init__(parent)
        self.profile = profile
        self.bemerkung = bemerkung
        vor = vorschlag(eingabe) if eingabe else None
        form = (vor or {}).get("form") or form
        self.setWindowTitle("Neue Abmessung anlegen" if eingabe else "Neues Profil")
        lay = QVBoxLayout(self)
        text = (f"<b>{eingabe}</b> steht nicht in den Stammdaten (Profile). " if eingabe else
                "Profil fehlt in den Stammdaten? ") + \
            ("Form und Maße sind aus der Eingabe übernommen, bitte prüfen. " if vor else "Form und Maße eingeben. ") + \
            ("Querschnitt und Gewicht rechnet das Programm. Den Materialpreis danach unter Einstellungen → "
             "Werkstoffe/Materialpreise oder als Meterpreis im Angebot eintragen.")
        hinweis = QLabel(text)
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
        self.flaeche = RechenSpin()
        self.flaeche.setRange(0, 100000)
        self.flaeche.setDecimals(1)
        self.flaeche.setSuffix(" mm²")
        self.flaeche.setSpecialValueText("aus den Maßen")
        self.flaeche.setToolTip("Querschnittsfläche laut Hersteller (Eckradien, C-Profil, Träger ohne Normtabelle). "
                                "Leer = aus den Maßen gerechnet.")
        if vor:
            self.a.setValue(vor["a"])
            self.b.setValue(vor.get("b") or 0)
            self.wand.setValue(vor["wand"])
            if vor.get("flaeche_manuell"):
                self.flaeche.setValue(vor["flaeche_manuell"])
        self.pid = QLineEdit()
        self.pid.setPlaceholderText("wird aus den Maßen vorgeschlagen")
        self.info = QLabel()
        self.a_text, self.b_text, self.w_text = QLabel(), QLabel(), QLabel()
        f.addRow("Profilform", self.form)
        f.addRow(self.a_text, self.a)
        f.addRow(self.b_text, self.b)
        f.addRow(self.w_text, self.wand)
        f.addRow("Fläche (Hersteller)", self.flaeche)
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
        for w in (self.a, self.b, self.wand, self.flaeche):
            w.valueChanged.connect(self.pruefen)
        self.form.currentTextChanged.connect(self.pruefen)
        self.pid.textChanged.connect(self._info)
        self.pruefen()
        if vor and self.pid.text() != vor["profil_id"]:     # Träger 'I h x b x Steg x Flansch': ID wie eingegeben
            self._von_hand = True
            self.pid.setText(vor["profil_id"])

    @staticmethod
    def _spin(von, bis):
        s = RechenSpin()
        s.setRange(von, bis)
        s.setDecimals(2)
        s.setSuffix(" mm")
        return s

    def werte(self):
        form = self.form.currentText()
        b = self.b.value() if form in MIT_B and self.b.value() > 0 else None
        a = self.a.value()
        w = dict(profil_id=self.pid.text().strip(), form=form, a=a, b=b, wand=self.wand.value(),
                 bemerkung=self.bemerkung)
        if self.flaeche.value() > 0:
            w["flaeche_manuell"] = self.flaeche.value()
        return w

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
        if not w.get("flaeche_manuell") and not flaeche_berechnet(w):
            return "Fläche eintragen (Herstellerwert): ohne sie fehlen Gewicht und Materialkosten."
        return ""

    def _info(self, *_):
        w = self.werte()
        fl, hk = w.get("flaeche_manuell") or flaeche_berechnet(w), huellkreis(w)
        teile = [f"Querschnitt {zahl_als_text(fl, 1)} mm² ≈ {zahl_als_text(fl * DICHTE_STAHL / 1000, 2)} kg/m Stahl"
                 if fl else "Querschnitt lässt sich bei dieser Form nicht rechnen: Fläche oben eintragen"]
        if hk:
            teile.append(f"Hüllkreis Ø {zahl_als_text(hk, 1)} mm")
        f = self.fehler()
        self.info.setText(" · ".join(teile) + (f"<br><span style='color:#B42318'>{f}</span>" if f else ""))
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(not f)
