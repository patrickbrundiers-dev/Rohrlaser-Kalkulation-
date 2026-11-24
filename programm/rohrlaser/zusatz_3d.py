"""Zusatzarbeit per Rechtsklick im 3D (CAD-009, Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“): Rechtsklick
auf eine Bohrung, Kontur, ein Ende oder eine Fläche im Rohr-, Blech-, Baugruppen- oder Satz-Editor legt eine
Zusatzarbeit aus den Stammdaten an (z. B. Gewinde, Senken, Entgraten, Abkleben).

Die Arbeit wird im Editor gemerkt (Teile-Editor: dialog.zusatz_neu, Baugruppe und Satz: ergebnis["zusatz_neu"] je
Positions-ID) und erst mit OK in die Spalte Zusatzarbeiten der Position geschrieben (anwenden); Abbrechen verwirft
sie. Der Preisstand kommt beim Schreiben aus den Stammdaten (rechnen.zusatz_stand). Vorgabe für die Menge bei
€/Stück: Anzahl der Konturen der Zeile (Bohrbild × 8 = 8), sonst automatisch (leer). Herkunft „3D“ mit dem Merkmal im
Text, damit nachvollziehbar bleibt, woher die Arbeit kommt."""
import json

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox,
                               QVBoxLayout)

QUELLE = "3D"
MENUE = "Zusatzarbeit hier anlegen …"


def menge_vorgabe(merkmal_id, eingaben):
    """Vorgabe für die Menge (Stück je Teil) zum Merkmal: Anzahl der Konturzeile, sonst 1."""
    art, _, nr = str(merkmal_id or "").partition(":")
    if art == "kontur" and nr.isdigit():
        konturen = (eingaben or {}).get("konturen") or []
        if int(nr) < len(konturen):
            n = konturen[int(nr)].get("anzahl")
            if isinstance(n, (int, float)) and n >= 1:
                return int(n)
    return 1


def eintrag(z, menge, merkmal_text):
    """Eintrag für die Spalte Zusatzarbeiten (ohne Preisstand, der kommt mit anwenden): menge nur bei Stück-Arten,
    sonst automatisch (None)."""
    stueck = z.get("art") in ("€/Stück", "s/Stück")
    return dict(name=z.get("name"), menge=(menge if stueck else None), preis=None,
                text=(f"aus 3D: {merkmal_text}" if merkmal_text else "aus 3D"), quelle=QUELLE)


def anwenden(zusatz_json, eintraege, katalog, saetze=None):
    """Spalte Zusatzarbeiten (JSON) um die Einträge aus dem 3D ergänzen; gleiche Arbeit mit gleichem Text ersetzt die
    Menge. Ergebnis: (JSON oder None, [Namen, die in den Stammdaten fehlen])."""
    from . import rechnen
    liste = rechnen.zusatz_liste(dict(zusatz=zusatz_json))
    kat = {z.get("name"): z for z in katalog or ()}
    fehlt = []
    for e in eintraege or ():
        z = kat.get(e.get("name"))
        if z is None:
            fehlt.append(e.get("name"))
            continue
        neu = dict(e, stand=rechnen.zusatz_stand(z, saetze))
        alt = next((i for i, x in enumerate(liste) if x.get("name") == neu["name"] and x.get("text") == neu["text"]),
                   None)
        if alt is None:
            liste.append(neu)
        else:
            liste[alt] = neu
    return (json.dumps(liste, ensure_ascii=False) if liste else None), fehlt


class ZusatzDialog(QDialog):
    """Zusatzarbeit wählen: Arbeit aus den Stammdaten, Menge (bei €/Stück), Merkmal als Herkunft."""

    def __init__(self, parent, katalog, merkmal_text, menge=1):
        super().__init__(parent)
        self.setWindowTitle("Zusatzarbeit anlegen")
        self.katalog = [z for z in katalog or () if z.get("name") and z.get("art") != "€/Angebot"]
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Am Merkmal: <b>{merkmal_text or 'ganzes Teil'}</b>"))
        form = QFormLayout()
        self.arbeit = QComboBox()
        for z in self.katalog:
            self.arbeit.addItem(f"{z['name']} ({z.get('art') or ''})", z["name"])
        form.addRow("Arbeit", self.arbeit)
        self.menge = QSpinBox()
        self.menge.setRange(1, 9999)
        self.menge.setValue(max(1, int(menge or 1)))
        self.menge.setSuffix(" Stk. je Teil")
        form.addRow("Menge", self.menge)
        self.hinweis = QLineEdit(merkmal_text or "")
        self.hinweis.setToolTip("Steht als Herkunft „aus 3D: …“ in der Zusatzarbeit")
        form.addRow("Merkmal", self.hinweis)
        lay.addLayout(form)
        self.leer = QLabel("Keine Zusatzarbeiten in den Stammdaten (Einstellungen › Zusatzarbeiten).")
        self.leer.setVisible(not self.katalog)
        lay.addWidget(self.leer)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setEnabled(bool(self.katalog))
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.arbeit.currentIndexChanged.connect(self._art)
        self._art()

    def _art(self):
        z = self.gewaehlt()
        self.menge.setEnabled(bool(z) and z.get("art") in ("€/Stück", "s/Stück"))

    def gewaehlt(self):
        return self.katalog[self.arbeit.currentIndex()] if self.katalog and self.arbeit.currentIndex() >= 0 else None

    def ergebnis(self):
        z = self.gewaehlt()
        return eintrag(z, self.menge.value(), self.hinweis.text().strip()) if z else None


def fragen(parent, katalog, merkmal_text, menge=1, wahl=None):
    """Dialog zeigen und den Eintrag liefern (None = abgebrochen). wahl = dict(name, menge) bedient ihn ohne exec
    (Tests)."""
    d = ZusatzDialog(parent, katalog, merkmal_text, menge)
    if wahl is not None:
        i = next((i for i, z in enumerate(d.katalog) if z["name"] == wahl.get("name")), -1)
        if i < 0:
            return None
        d.arbeit.setCurrentIndex(i)
        if wahl.get("menge"):
            d.menge.setValue(int(wahl["menge"]))
        return d.ergebnis()
    return d.ergebnis() if d.exec() == QDialog.Accepted else None
