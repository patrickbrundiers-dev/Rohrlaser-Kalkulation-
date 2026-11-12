"""Fenster „Rohrzug aus Punkten“ (Plan Paket K4, Rechnung in rohrzug.py): Profil, Werkstoff und die XYZ-Punkte der
Mittellinie eingeben (eintippen, aus Excel einfügen oder aus einer Text-/CSV-Datei laden); die Vorschau nennt die
Rohre mit Gehrungen und zeigt sie im 3D. Nach OK steht in self.ergebnis dict(erg = rohrzug.bauen(...), profil_id,
werkstoff_id, saetze, name) wie beim Rahmen-Assistent."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from . import rahmen, rohrzug
from .eingabe import RechenSpinGanz

TITEL = "Rohrzug aus Punkten"
BEISPIEL = "0 0 0\n1000 0 0\n1000 0 800\n0 0 800\n0 0 0"


class RohrzugDialog(QDialog):
    def __init__(self, parent, profile, werkstoffe, werkstoff=None, punkte_text=None):
        super().__init__(parent)
        self.setWindowTitle(TITEL)
        self.profile = {pid: p for pid, p in (profile or {}).items() if (p or {}).get("form") in rahmen.PROFILE}
        self.ergebnis = None
        aussen = QHBoxLayout(self)
        links = QWidget()
        lay = QVBoxLayout(links)
        lay.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(links)
        from .ansicht3d import Ansicht3DMitKnoepfen
        self.ansicht = Ansicht3DMitKnoepfen()
        self.ansicht.setMinimumSize(420, 380)
        aussen.addWidget(self.ansicht, 1)
        hinweis = QLabel("Punkte der Mittellinie in mm, je Zeile x y z (auch aus Excel einfügen). Zwischen zwei "
                         "Punkten liegt ein gerades Rohr, an jedem Knick eine Gehrung. Liegt der letzte Punkt auf "
                         "dem ersten, ist der Zug geschlossen. Die Rohre werden ein Satz mit 3D und danach eine "
                         "Schweißbaugruppe.")
        hinweis.setWordWrap(True)
        hinweis.setMaximumWidth(460)
        lay.addWidget(hinweis)
        form = QFormLayout()
        self.profil = QComboBox()
        self.profil.addItems(sorted(self.profile, key=str.lower))
        self.werkstoff = QComboBox()
        self.werkstoff.addItems([""] + sorted(werkstoffe or (), key=str.lower))
        if werkstoff in (werkstoffe or ()):
            self.werkstoff.setCurrentText(werkstoff)
        self.hochkant = QCheckBox("Rechteckrohr hochkant (anderes Maß in der Knickebene)")
        self.saetze = RechenSpinGanz()
        self.saetze.setRange(1, 100000)
        self.name = QLineEdit()
        self.name.setPlaceholderText("leer = Rohrzug")
        for t, w in (("Profil", self.profil), ("Werkstoff", self.werkstoff), ("", self.hochkant),
                     ("Baugruppen", self.saetze), ("Name", self.name)):
            form.addRow(t, w)
        lay.addLayout(form)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Punkte x y z [mm]"))
        zeile.addStretch(1)
        self.datei_knopf = QPushButton("Aus Datei …")
        self.datei_knopf.setToolTip("Punkte aus einer Text- oder CSV-Datei laden (je Zeile x y z)")
        self.datei_knopf.clicked.connect(lambda: self.datei_laden())
        zeile.addWidget(self.datei_knopf)
        lay.addLayout(zeile)
        self.punkte = QPlainTextEdit(punkte_text if punkte_text is not None else BEISPIEL)
        self.punkte.setMinimumHeight(160)
        lay.addWidget(self.punkte, 1)
        self.vorschau = QLabel()
        self.vorschau.setWordWrap(True)
        self.vorschau.setMaximumWidth(460)
        lay.addWidget(self.vorschau)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.accepted.connect(self._ok)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        self.profil.currentTextChanged.connect(lambda _: self.neu())
        self.hochkant.toggled.connect(lambda _: self.neu())
        self.punkte.textChanged.connect(self.neu)
        self.setMinimumWidth(960)
        self.neu()

    def datei_laden(self, pfad=None):
        if not pfad:
            pfad, _ = QFileDialog.getOpenFileName(self, "Punkte laden", "", "Punkte (*.txt *.csv *.xyz);;Alle (*)")
            if not pfad:
                return False
        with open(pfad, encoding="utf-8-sig", errors="replace") as f:
            self.punkte.setPlainText(f.read())
        return True

    def zug_name(self):
        return self.name.text().strip() or rohrzug.NAME

    def berechnen(self):
        """rohrzug.bauen mit den Eingaben; (Ergebnis, Fehlertext)."""
        p = self.profile.get(self.profil.currentText())
        if not p:
            return None, "Keine Quadrat-, Rechteck- oder Rundrohre in den Profilen."
        try:
            return rohrzug.bauen(p, rohrzug.punkte_lesen(self.punkte.toPlainText()), self.hochkant.isChecked()), None
        except ValueError as f:
            return None, str(f).replace("Rohrzug: ", "")

    def neu(self):
        p = self.profile.get(self.profil.currentText()) or {}
        self.hochkant.setEnabled(p.get("form") == "Rechteckrohr")
        erg, fehler = self.berechnen()
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(erg is not None)
        if fehler:
            self.vorschau.setText(f"<span style='color:#C62828'>{fehler}</span>")
            self.ansicht.setzen(None, "", "")
            return
        z = rohrzug.text(erg)
        self.vorschau.setText(f"<b>{z[0]}</b><br>" + "<br>".join(z[1:]))
        self.ansicht.setzen(rahmen.vorschau(erg, p), self.zug_name(),
                            "Vorschau: Rohre in Einbaulage, gleiche Rohre in gleicher Farbe.")

    def _ok(self):
        erg, _ = self.berechnen()
        if erg is None:
            return
        self.ergebnis = dict(erg=erg, profil_id=self.profil.currentText(),
                             werkstoff_id=self.werkstoff.currentText() or None, saetze=self.saetze.value(),
                             name=self.zug_name())
        self.accept()
