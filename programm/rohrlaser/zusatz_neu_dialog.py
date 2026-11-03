"""Kurzformular „Neue Zusatzarbeit“ aus dem Angebot (Plan „Zusatzarbeiten besser erkennen“, Patrick 03.11.2026, 3c 5a).

Sechs Felder statt rund zwanzig: Name, wie abgerechnet wird (in Klartext), Preis, Fremdleistung, Kategorie,
Erkennungswörter; unter „Mehr“ Mindestbetrag je Angebot und Text im Angebot. Alles Weitere (Zeit × Stundensatz,
Material, Zuschläge) bleibt in Einstellungen → Zusatzarbeiten. „Aus Vorlage“ füllt das Formular mit einer typischen
Zusatzarbeit (stammdaten.ZUSATZ_VORLAGEN, Beispielpreise). Die Vorschau rechnet an der markierten Position.

Wer darf (3c): jeder legt sie an, sie gilt dann nur in diesem Angebot (Eintrag mit Preisstand in den Positionen,
Herkunft „nur in diesem Angebot“). Ist der Platz als Admin freigeschaltet (oder kein Admin-Schutz eingerichtet),
übernimmt der Haken „Auch in die Einstellungen übernehmen“ sie gleich in die Stammdaten; sonst übernimmt ein Admin sie
später unter Einstellungen → Zusatzarbeiten → „Aus Angeboten übernehmen“.
"""
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton, QVBoxLayout, QWidget)

from . import rechnen
from .stammdaten import (ZUSATZ_KATEGORIEN, ZUSATZ_VORLAGEN, ZUSATZARBEITEN, zahl_als_text, zahl_aus_text,
                         zusatz_vorlage)
from .stil import GELB_FLAECHE, GELB_TEXT

# Abrechnung in Klartext (Knopf -> Abrechnung der Stammdaten)
ARTEN = (("je Stück", "€/Stück"), ("je kg", "€/kg"), ("je m² Außenfläche", "€/m²"), ("je m Länge", "€/m"),
         ("nach Zeit (€/h)", "€/h"), ("einmal je Angebot", "€/Angebot"))
EINHEIT_PREIS = {"€/Stück": "€ je Stück", "€/kg": "€ je kg", "€/m²": "€ je m²", "€/m": "€ je m",
                 "€/h": "€ je Stunde (Sekunden je Teil im Angebot)", "€/Angebot": "€ je Angebot"}


def zeile_aus(werte):
    """Stammdatenzeile (alle Felder) aus den Werten des Kurzformulars."""
    z = {f.name: None for f in ZUSATZARBEITEN.felder}
    z.update({n: werte.get(n) for n in ("name", "art", "fremd", "kategorie", "erkennung", "mindest", "angebotstext",
                                        "bemerkung")})
    z["aktiv"] = "ja"
    if werte.get("art") == "€/h":           # Stundensatz eigener, Sekunden je Teil im Angebot
        z.update(satz=werte.get("preis"), zeit_einheit="s")
    else:
        z["preis"] = werte.get("preis")
    return z


class ZusatzNeuDialog(QDialog):
    """p: markierte Position (Vorschau, darf leer sein); gesperrt: Admin-Schutz aktiv und nicht freigeschaltet."""

    def __init__(self, parent, db, p, k, tabellen, positionen=(), gesperrt=True):
        super().__init__(parent)
        self.db, self.p, self.k, self.tabellen = db, p or {}, k, tabellen
        self.vorhanden = {str(z.get("name") or "").lower() for z in tabellen.get("zusatzarbeiten") or ()}
        from .zusatz_dialog import angebot_eigene
        self.vorhanden |= {n.lower() for n in angebot_eigene(positionen, tabellen)}
        self.ergebnis = None
        self.setWindowTitle("Neue Zusatzarbeit")
        self.resize(640, 420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("z. B. Eloxieren E6/EV1")
        form.addRow("Name *", self.name)
        self.art_knoepfe = QButtonGroup(self)
        self.art_knoepfe.setExclusive(True)
        zeile = QHBoxLayout()
        for i, (text, art) in enumerate(ARTEN):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("art", art)
            self.art_knoepfe.addButton(b, i)
            zeile.addWidget(b)
        zeile.addStretch(1)
        self.art_knoepfe.button(0).setChecked(True)
        self.art_knoepfe.buttonClicked.connect(lambda _: self.aktualisieren())
        form.addRow("Wie wird abgerechnet?", zeile)
        self.preis = QLineEdit()
        self.preis.setPlaceholderText("0,00")
        self.preis.setMaximumWidth(110)
        self.preis.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.preis_einheit = QLabel()
        zeile = QHBoxLayout()
        zeile.addWidget(self.preis)
        zeile.addWidget(self.preis_einheit)
        zeile.addStretch(1)
        form.addRow("Preis *", zeile)
        self.fremd = QCheckBox("Fremdleistung (z. B. Verzinkerei, Eloxal): Zuschlag Fremdleistung statt Fertigung")
        form.addRow("", self.fremd)
        self.kategorie = QComboBox()
        self.kategorie.setEditable(True)
        self.kategorie.addItems([""] + list(ZUSATZ_KATEGORIEN))
        form.addRow("Kategorie", self.kategorie)
        self.erkennung = QLineEdit()
        self.erkennung.setPlaceholderText("Wörter mit ; getrennt, z. B. eloxiert; E6; anodisiert")
        self.erkennung.setToolTip("Steht eines dieser Wörter in Bezeichnung, Artikelnummer, STEP-Name, Anfrage-Mail "
                                  "oder Zeichnung, schlägt das Programm die Zusatzarbeit gelb vor")
        form.addRow("Erkennungswörter", self.erkennung)
        lay.addLayout(form)
        self.mehr = QToolButton()
        self.mehr.setText("Mehr ▸")
        self.mehr.setCheckable(True)
        self.mehr.toggled.connect(self._mehr)
        lay.addWidget(self.mehr)
        self.mehr_box = QWidget()
        f2 = QFormLayout(self.mehr_box)
        f2.setContentsMargins(0, 0, 0, 0)
        self.mindest = QLineEdit()
        self.mindest.setPlaceholderText("0,00")
        self.mindest.setMaximumWidth(110)
        f2.addRow("Mindestbetrag je Angebot [€]", self.mindest)
        self.angebotstext = QLineEdit()
        self.angebotstext.setPlaceholderText("leer = Name")
        f2.addRow("Text im Angebot", self.angebotstext)
        f2.addRow(QLabel("Zeit × Stundensatz, Material und Zuschläge: Einstellungen → Zusatzarbeiten."))
        self.mehr_box.hide()
        lay.addWidget(self.mehr_box)
        self.vorschau = QLabel()
        self.vorschau.setWordWrap(True)
        self.vorschau.setStyleSheet(f"background: {GELB_FLAECHE}; color: {GELB_TEXT}; padding: 6px;")
        lay.addWidget(self.vorschau)
        self.stammdaten = QCheckBox("Auch in die Einstellungen übernehmen (für alle Angebote)")
        self.stammdaten.setEnabled(not gesperrt)
        self.stammdaten.setChecked(not gesperrt)
        self.stammdaten.setToolTip("Nur als Admin. Ohne Haken gilt die Zusatzarbeit nur in diesem Angebot; ein Admin "
                                   "übernimmt sie später unter Einstellungen → Zusatzarbeiten → „Aus Angeboten "
                                   "übernehmen“." if gesperrt else "Legt die Zusatzarbeit in den Stammdaten an")
        lay.addWidget(self.stammdaten)
        if gesperrt:
            lay.addWidget(QLabel("<span style='color:#5F6B7A'>Gilt nur in diesem Angebot (Einstellungen ändert nur der "
                                 "Admin).</span>"))
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #B42318;")
        lay.addWidget(self.fehler)
        unten = QHBoxLayout()
        self.vorlage = QComboBox()
        self.vorlage.addItem("Aus Vorlage …", None)
        for v in ZUSATZ_VORLAGEN:
            self.vorlage.addItem(f"{v[0]} ({v[1]}, {zahl_als_text(v[2], 2)} €)", v[0])
        self.vorlage.setToolTip("Typische Zusatzarbeit mit Beispielpreis einsetzen (bitte Preis prüfen)")
        self.vorlage.currentIndexChanged.connect(lambda _: self.vorlage_nehmen(self.vorlage.currentData()))
        unten.addWidget(self.vorlage)
        unten.addStretch(1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Anlegen und wählen")
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        unten.addWidget(knoepfe)
        lay.addLayout(unten)
        for w in (self.name, self.preis, self.mindest):
            w.textChanged.connect(lambda _=None: self.aktualisieren())
        self.fremd.toggled.connect(lambda _: self.aktualisieren())
        self.aktualisieren()

    def _mehr(self, an):
        self.mehr_box.setVisible(an)
        self.mehr.setText("Mehr ▾" if an else "Mehr ▸")

    def art(self):
        b = self.art_knoepfe.checkedButton()
        return b.property("art") if b else "€/Stück"

    def art_setzen(self, art):
        for b in self.art_knoepfe.buttons():
            b.setChecked(b.property("art") == art)
        self.aktualisieren()

    def vorlage_nehmen(self, name):
        """Formular mit der Vorlage name füllen (Beispielpreis)."""
        v = zusatz_vorlage(name) if name else None
        if not v:
            return False
        self.name.setText(v["name"])
        self.art_setzen(v["art"])
        self.preis.setText(zahl_als_text(v["preis"], 2, tausender=False))
        self.fremd.setChecked(v["fremd"] == "ja")
        self.kategorie.setCurrentText(v["kategorie"] or "")
        self.erkennung.setText(v["erkennung"] or "")
        self.angebotstext.setText(v["angebotstext"] or "")
        self.aktualisieren()
        return True

    @staticmethod
    def _zahl(text):
        t = text.strip()
        return zahl_aus_text(t) if t else None

    def werte(self):
        """Werte des Formulars; ValueError mit verständlicher Meldung."""
        from .zusatz_regeln import nur_stueck
        name = self.name.text().strip()
        if not name:
            raise ValueError("Bitte einen Namen eingeben.")
        if name.lower() in self.vorhanden:
            raise ValueError(f"Eine Zusatzarbeit „{name}“ gibt es schon – bitte in der Liste anhaken.")
        art = self.art()
        if nur_stueck(name) and art != "€/Stück":
            raise ValueError(f"{name} rechnet nur € je Stück.")
        try:
            preis = self._zahl(self.preis.text())
            mindest = self._zahl(self.mindest.text())
        except ValueError:
            raise ValueError("Preis und Mindestbetrag bitte als Zahl eingeben (z. B. 14,50).")
        if not preis or preis < 0:
            raise ValueError("Bitte einen Preis größer 0 eingeben.")
        if mindest is not None and mindest < 0:
            raise ValueError("Der Mindestbetrag darf nicht negativ sein.")
        return dict(name=name, art=art, preis=preis, mindest=mindest, fremd="ja" if self.fremd.isChecked() else "nein",
                    kategorie=self.kategorie.currentText().strip() or None,
                    erkennung=self.erkennung.text().strip() or None,
                    angebotstext=self.angebotstext.text().strip() or None,
                    bemerkung="im Angebot angelegt (Kurzformular)")

    def aktualisieren(self):
        """Einheit des Preises und Vorschau an der markierten Position."""
        art = self.art()
        self.preis_einheit.setText(EINHEIT_PREIS.get(art, "€"))
        try:
            w = self.werte()
        except ValueError as e:
            self.vorschau.setText(f"Vorschau: {e}")
            return None
        z = zeile_aus(w)
        if not self.p or self.k is None:
            self.vorschau.setText("Keine Position markiert: die Zusatzarbeit wird nur angelegt.")
            return z
        e = dict(name=w["name"], menge=None, preis=None, text=None,
                 stand=rechnen.zusatz_stand(z, rechnen.stundensaetze(self.tabellen)))
        probe = dict(self.p, zusatz=json.dumps([e], ensure_ascii=False), arbeitsgaenge=None)
        werte = rechnen.zusatz_werte(probe, self.k, dict(self.tabellen, arbeitsgang_regeln=[]))
        if not werte:
            self.vorschau.setText("")
            return z
        x = werte[0]
        zuschlag = "Fremdleistung" if w["fremd"] == "ja" else "Fertigung"
        pos = f"Pos. {self.p.get('pos')}" if self.p.get("pos") else "der Position"
        if art == "€/h":
            text = (f"So rechnet sie an {pos}: Sekunden je Teil im Angebot eintragen, ÷ 3600 × "
                    f"{rechnen.zahl(x['preis'])} €/h")
        elif art == "€/Angebot":
            text = f"So rechnet sie: einmal {rechnen.zahl(x['pauschal'])} € je Angebot, auf die Teile umgelegt"
        else:
            text = (f"So rechnet sie an {pos}: {rechnen.zahl(x['menge'], 3)} {x['einheit']} × "
                    f"{rechnen.zahl(x['preis'])} € = <b>{rechnen.zahl(x['betrag'])} € je Teil</b>")
        self.vorschau.setText(text + f" (+ Zuschlag {zuschlag} und Gewinn)")
        return z

    def _ok(self):
        try:
            w = self.werte()
        except ValueError as e:
            self.fehler.setText(str(e))
            return
        self.ergebnis = (w["name"], zeile_aus(w), self.stammdaten.isEnabled() and self.stammdaten.isChecked())
        self.accept()
