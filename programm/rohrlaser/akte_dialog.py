"""Fenster „Angebotsdokument erstellen“ (Patrick 18.11.2026, Angebotsakte): Dokument wählen (Kundenangebot, interne
Kalkulation, komplettes Dokument), Seiten an- und abwählen, Prüfliste sehen, Vorschau ein/aus."""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QLabel,
                               QListWidget, QListWidgetItem, QRadioButton, QVBoxLayout)

from . import angebotsakte as akte_

FARBEN = {akte_.OK: "#1E6B34", akte_.HINWEIS: "#5B6773", akte_.WARNUNG: "#B86E00", akte_.FEHLER: "#B42318"}
ZEICHEN = {akte_.OK: "✓", akte_.HINWEIS: "i", akte_.WARNUNG: "!", akte_.FEHLER: "✕"}


class AkteDialog(QDialog):
    """Ergebnis nach exec: art ('kunde'/'intern'/'gesamt'), seiten [Nummern], vorschau (bool)."""

    def __init__(self, parent, akte, stand_text="", vorschau=True, art="gesamt"):
        super().__init__(parent)
        self.setWindowTitle(f"Angebotsdokument erstellen – Angebot {akte.get('nummer') or ''}")
        self.akte = akte
        lay = QVBoxLayout(self)
        if stand_text:
            hinweis = QLabel(stand_text)
            hinweis.setWordWrap(True)
            lay.addWidget(hinweis)
        gruppe = QGroupBox("Dokument")
        g = QVBoxLayout(gruppe)
        self.arten = QButtonGroup(self)
        self.knoepfe = {}
        for schluessel, text, tipp in (
                ("kunde", "Kundenangebot erstellen", "Seiten 1–2: Angebot und technische Bauteilübersicht, ohne "
                                                     "interne Werte. Zum Versand an den Kunden."),
                ("intern", "Interne Kalkulation erstellen", "Seiten 3–7: Schnittschema, Material, Fertigung, Zukauf, "
                                                            "Gesamtkalkulation. Nur für die interne Ablage."),
                ("gesamt", "Komplettes Angebots- und Kalkulationsdokument erstellen",
                 "Alle Seiten; dazu werden Kundenangebot und interne Kalkulation getrennt in der Akte abgelegt.")):
            k = QRadioButton(text)
            k.setToolTip(tipp)
            self.arten.addButton(k)
            self.knoepfe[schluessel] = k
            g.addWidget(k)
            k.toggled.connect(self._seiten_stellen)
        lay.addWidget(gruppe)
        seiten = QGroupBox("Seiten")
        gl = QGridLayout(seiten)
        self.haken = {}
        mit_zukauf = akte_.zukauf_vorhanden(akte)
        for i, (nr, _, titel, art_) in enumerate(akte_.SEITEN):
            h = QCheckBox(f"{nr}  {titel}" + ("  (Kunde)" if art_ == akte_.KUNDE else "  (intern)"))
            h.setChecked(nr != 6 or mit_zukauf)
            if nr == 6 and not mit_zukauf:
                h.setToolTip("Entfällt: das Angebot hat keine Zukaufteile und keine Fremdleistungen.")
            self.haken[nr] = h
            gl.addWidget(h, i % 4, i // 4)
        lay.addWidget(seiten)
        lay.addWidget(QLabel("Prüfung"))
        self.liste = QListWidget()
        self.liste.setMinimumHeight(140)
        for stufe, text in akte.get("pruefung") or ():
            e = QListWidgetItem(f"{ZEICHEN.get(stufe, 'i')}  {text}")
            e.setForeground(QColor(FARBEN.get(stufe, "#5B6773")))
            self.liste.addItem(e)
        lay.addWidget(self.liste, 1)
        self.vorschau = QCheckBox("Vorschau vor dem Speichern zeigen")
        self.vorschau.setChecked(vorschau)
        lay.addWidget(self.vorschau)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = knoepfe.button(QDialogButtonBox.Ok)
        self.ok.setText("Erstellen")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.knoepfe[art if art in self.knoepfe else "gesamt"].setChecked(True)
        for h in self.haken.values():
            h.toggled.connect(self._ok_stellen)
        self._seiten_stellen()
        self.resize(620, 560)

    @property
    def art(self):
        return next((a for a, k in self.knoepfe.items() if k.isChecked()), "gesamt")

    @property
    def seiten(self):
        erlaubt = akte_.ARTEN[self.art][1]
        return [n for n, h in self.haken.items() if h.isChecked() and h.isEnabled() and n in erlaubt]

    def _seiten_stellen(self, *_):
        erlaubt = akte_.ARTEN[self.art][1]
        mit_zukauf = akte_.zukauf_vorhanden(self.akte)
        for n, h in self.haken.items():
            h.setEnabled(n in erlaubt and (n != 6 or mit_zukauf))
        self._ok_stellen()

    def _ok_stellen(self, *_):
        self.ok.setEnabled(bool(self.seiten))


def stand_text(eintrag, stand):
    """Zeile über der Auswahl: letzte Version der Akte und ob sie zur Kalkulation passt."""
    if not eintrag:
        return "Für dieses Angebot gibt es noch keine Angebotsakte."
    zeit = str(eintrag.get("gespeichert") or eintrag.get("erstellt") or "")
    from .akte_pdf import datum
    t = f"Letzte Akte: Version {eintrag.get('version')} vom {datum(zeit)} {zeit[11:16]}"
    if stand == "veraltet":
        return t + " – die Kalkulation hat sich seitdem geändert, bitte neu erzeugen."
    return t + " – passt zur aktuellen Kalkulation."

