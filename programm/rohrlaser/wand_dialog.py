"""Wandstärke ändern (Patrick 31.10.2026: „Eine einfache Option einbauen um Wandstärke an Rohren zu ändern“, Plan 5a):
Rechtsklick auf Positionen bzw. im Material-Fenster auf eine Abmessung -> „Wandstärke ändern …“. Zur Wahl stehen die
Profile der Stammdaten mit gleicher Form und gleichem Außenmaß; eine andere Wandstärke lässt sich eintippen, das Profil
wird dann wie bei „Abmessung neu anlegen“ in den Stammdaten angelegt (ohne Materialpreis). Konturen und Schnitte der
Positionen bleiben, Gewicht, Schneiddaten und Preis rechnen mit der neuen Wandstärke.

Normprofile (UPN, IPE …) und RP-Profile haben feste Maße: dort gibt es keine andere Wandstärke.
"""
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QRadioButton,
                               QVBoxLayout)

from . import hilfe, normprofile, profil_neu, rp_profile
from .stammdaten import zahl_aus_text

TOL = 0.05      # mm: gleiches Außenmaß


def _z(w):
    return f"{float(w):.2f}".rstrip("0").rstrip(".").replace(".", ",")


def aenderbar(pid, profil):
    """'' = Wandstärke änderbar, sonst der Grund (Normprofil, RP-Profil, Profil fehlt)."""
    if not profil:
        return f"Profil {pid} fehlt in den Stammdaten."
    if normprofile.daten(pid) is not None:
        return f"{pid} ist ein Normprofil mit festen Maßen: bitte ein anderes Normprofil wählen."
    if profil.get("form") == rp_profile.FORM:
        return f"{pid} ist ein RP-Profil mit fester Kontur."
    if profil.get("a") is None:
        return f"{pid} hat kein Außenmaß in den Stammdaten."
    return ""


def gleiche_aussenmasse(profil, profile):
    """Profile der Stammdaten mit gleicher Form und gleichem Außenmaß wie profil, nach Wandstärke sortiert:
    [(Wandstärke, Profil-ID)]. Normprofile und Profile ohne Wandstärke zählen nicht."""
    out = []
    for pid, p in (profile or {}).items():
        if p.get("form") != profil.get("form") or not isinstance(p.get("wand"), (int, float)):
            continue
        if normprofile.daten(pid) is not None:
            continue
        if abs(float(p.get("a") or 0) - float(profil.get("a") or 0)) > TOL:
            continue
        if abs(float(p.get("b") or 0) - float(profil.get("b") or 0)) > TOL:
            continue
        out.append((float(p["wand"]), pid))
    return sorted(out)


def ziel_profil(profil, wand, profile):
    """Profil mit gleicher Form und gleichem Außenmaß und der Wandstärke wand: (Profil-ID, None), wenn es in den
    Stammdaten steht, sonst (neue Profil-ID, Zeile zum Anlegen) – die übrigen Werte (Endbeschnitt, Greiferrest,
    Außenradius, Lieferlängen vergleichen) wie das bisherige Profil, Fläche und Wandstärke max. leer (berechnet)."""
    for w, pid in gleiche_aussenmasse(profil, profile):
        if abs(w - wand) < 1e-6:
            return pid, None
    pid = profil_neu.profil_id(profil.get("form"), profil.get("a"), profil.get("b"), wand)
    zeile = {k: v for k, v in profil.items() if k not in ("id", "uid", "flaeche_manuell", "wand_max", "naht_stange")}
    zeile.update(profil_id=pid, wand=wand, bemerkung=f"Wandstärke geändert aus {profil.get('profil_id') or ''}".strip())
    return pid, zeile


class WandDialog(QDialog):
    """Fenster „Wandstärke ändern“: neue Wandstärke (Liste der Stammdaten oder eintippen) und für welche Positionen.
    Nach OK: self.wand (mm), self.alle (alle Positionen der Abmessung im Angebot)."""

    def __init__(self, parent, profil, profile, markiert, abmessung):
        super().__init__(parent)
        self.profil, self.wand, self.alle = profil, None, False
        self.setWindowTitle("Wandstärke ändern")
        lay = QVBoxLayout(self)
        lay.addWidget(hilfe.Hinweis(
            "Andere Wandstärke bei gleichem Außenmaß: Konturen und Schnitte der Positionen bleiben, Gewicht, "
            "Schneiddaten und Preis rechnen neu. Eine Wandstärke, die es in den Stammdaten noch nicht gibt, legt das "
            "Programm dort als neue Abmessung an (Materialpreis bitte nachtragen).", schluessel="wand_aendern"))
        form = QFormLayout()
        form.addRow("Abmessung:", QLabel(f"<b>{profil.get('profil_id')}</b>  ({profil.get('form')}, Wandstärke "
                                         f"{_z(profil.get('wand') or 0)} mm)"))
        self.auswahl = QComboBox()
        self.auswahl.setEditable(True)
        self.liste = gleiche_aussenmasse(profil, profile)
        for w, pid in self.liste:
            self.auswahl.addItem(f"{_z(w)} mm  –  {pid}", w)
        self.auswahl.setCurrentText("")
        self.auswahl.lineEdit().setPlaceholderText("Wandstärke [mm] wählen oder eintippen")
        self.auswahl.setToolTip("Wandstärken dieser Abmessung aus den Stammdaten; eine andere Zahl eintippen")
        form.addRow("Neue Wandstärke:", self.auswahl)
        self.nur = QRadioButton(f"nur markierte Positionen ({markiert})")
        self.alle_knopf = QRadioButton(f"alle Positionen dieser Abmessung im Angebot ({abmessung})")
        (self.nur if markiert else self.alle_knopf).setChecked(True)
        self.nur.setEnabled(bool(markiert))
        form.addRow("Ändern für:", self.nur)
        form.addRow("", self.alle_knopf)
        lay.addLayout(form)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #C00000;")
        lay.addWidget(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Ändern")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.annehmen)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def lesen(self):
        """Wandstärke aus der Eingabe [mm]; ValueError bei ungültiger Eingabe."""
        t = self.auswahl.currentText().strip()
        i = self.auswahl.findText(t)
        if i >= 0 and self.auswahl.itemData(i) is not None:
            return float(self.auswahl.itemData(i))
        try:
            w = zahl_aus_text(t.replace("mm", "").strip())
        except ValueError:
            raise ValueError(f"„{t}“ ist keine Wandstärke.") from None
        a = [float(self.profil.get(x)) for x in ("a", "b") if isinstance(self.profil.get(x), (int, float))]
        if not 0 < w < (min(a) / 2 if a else 500):
            raise ValueError("Wandstärke größer 0 und kleiner als das halbe Außenmaß eintragen.")
        return round(w, 2)

    def annehmen(self):
        try:
            w = self.lesen()
        except ValueError as e:
            self.fehler.setText(str(e))
            return
        if abs(w - float(self.profil.get("wand") or 0)) < 1e-6:
            self.fehler.setText("Das ist schon die Wandstärke der Abmessung.")
            return
        self.wand, self.alle = w, self.alle_knopf.isChecked()
        self.accept()
