"""Dialog „Fräsen nach Bearbeitung …“ (Patrick 03.11.2026): Bearbeitungen eingeben (Planfläche, Bohrungen, Gewinde,
Passbohrungen, Senkungen, Taschen), Zeiten, Ampel und Preis je Stück sehen (fraesen_nach.rechnen)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from . import drehfraes_preis as dp, fraesen_nach as fn
from .drehfraes_dialog import AMPEL_FARBE, _eur, _min, werkstoff_liste

EINGABE = ("Bearbeitung", "Anzahl", "Länge", "Breite", "Tiefe/Aufmaß", "Ø")
FELD = {2: "l", 3: "b", 4: "t", 5: "d"}


def _zahl(text):
    try:
        return float(str(text).replace(",", ".")) if str(text).strip() else None
    except ValueError:
        return None


class FraesenNachDialog(QDialog):
    def __init__(self, eltern, e, einst, titel="", nur_lesen=False):
        super().__init__(eltern)
        self.e = dict(e)
        self.einst = einst
        self.ergebnis = {}
        self._laedt = True
        self.setWindowTitle("Fräsen nach Bearbeitung")
        self.resize(980, 720)
        lay = QVBoxLayout(self)
        kopf = QLabel(f"<b>{titel}</b><br>Bearbeitungen nach dem Lasern bzw. Schweißen eintragen; gerechnet mit den "
                      "Schnittwerten und Sätzen unter Einstellungen → Dreh-/Frästeil-Richtpreis.")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        form = QFormLayout()
        self.werkstoff = QLineEdit(self.e.get("werkstoff") or "")
        werkstoff_liste(self.werkstoff, einst)
        self.stueck = QSpinBox()
        self.stueck.setRange(1, 1000000)
        self.stueck.setValue(int(float(self.e.get("stueck") or 1)))
        self.gewicht = QDoubleSpinBox()
        self.gewicht.setRange(0, 100000)
        self.gewicht.setDecimals(1)
        self.gewicht.setSuffix(" kg")
        self.gewicht.setValue(float(self.e.get("gewicht") or 0))
        groesse = QHBoxLayout()
        self.masse = []
        for n in ("laenge", "breite", "hoehe"):
            s = QDoubleSpinBox()
            s.setRange(0, 100000)
            s.setDecimals(0)
            s.setSuffix(" mm")
            s.setValue(float(self.e.get(n) or 0))
            self.masse.append(s)
            groesse.addWidget(s)
        self.aufspannungen = QSpinBox()
        self.aufspannungen.setRange(1, 20)
        self.aufspannungen.setValue(int(self.e.get("aufspannungen") or 1))
        self.ausrichten = QCheckBox("Schweißteil ausrichten/antasten (+2 min je Aufspannung)")
        self.ausrichten.setChecked(str(self.e.get("ausrichten") or "ja").startswith("j"))
        self.fremd = QCheckBox("beim Lohnfertiger (Fremdleistung, mit Aufschlag des Lieferanten)")
        self.fremd.setChecked(str(self.e.get("fremd") or "nein").startswith("j"))
        self.zusatz = QDoubleSpinBox()
        self.zusatz.setRange(0, 100000)
        self.zusatz.setDecimals(2)
        self.zusatz.setSuffix(" €/Stück")
        self.zusatz.setValue(float(self.e.get("zusatz_eur") or 0))
        form.addRow("Werkstoff", self.werkstoff)
        form.addRow("Stückzahl (Rüsten verteilt sich darauf)", self.stueck)
        form.addRow("Gewicht je Stück", self.gewicht)
        form.addRow("Größe L × B × H (Verfahrweg)", groesse)
        form.addRow("Aufspannungen", self.aufspannungen)
        form.addRow("", self.ausrichten)
        form.addRow("", self.fremd)
        form.addRow("Zusätze (z. B. feste €/Gewinde)", self.zusatz)
        lay.addLayout(form)
        self.eingabe = QTableWidget(0, len(EINGABE))
        self.eingabe.setHorizontalHeaderLabels(EINGABE)
        self.eingabe.verticalHeader().setVisible(False)
        self.eingabe.setColumnWidth(0, 200)
        leiste = QHBoxLayout()
        self.plus = QPushButton("+ Bearbeitung")
        self.minus = QPushButton("Bearbeitung entfernen")
        leiste.addWidget(self.plus)
        leiste.addWidget(self.minus)
        leiste.addStretch(1)
        lay.addLayout(leiste)
        lay.addWidget(self.eingabe, 1)
        self.befunde = QLabel()
        self.befunde.setWordWrap(True)
        self.befunde.setTextFormat(Qt.RichText)
        lay.addWidget(self.befunde)
        self.tabelle = QTableWidget(0, 4)
        self.tabelle.setHorizontalHeaderLabels(("Arbeitsgang", "Minuten je Stück", "Kosten €", "Rechnung"))
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabelle.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabelle.setColumnWidth(0, 220)
        lay.addWidget(self.tabelle, 1)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        self.summe.setTextFormat(Qt.RichText)
        lay.addWidget(self.summe)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Als Zusatzarbeit übernehmen")
        knoepfe.button(QDialogButtonBox.Ok).setEnabled(not nur_lesen)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        for b in self.e.get("bearbeitungen") or [dict(art=fn.PLAN, anzahl=1)]:
            self.zeile_neu(b)
        self.plus.clicked.connect(lambda: self.zeile_neu(dict(art=fn.BOHRUNG, anzahl=1)))
        self.minus.clicked.connect(self._entfernen)
        for s in [self.stueck, self.gewicht, self.zusatz, self.aufspannungen] + self.masse:
            s.valueChanged.connect(self.neu_rechnen)
        for c in (self.ausrichten, self.fremd):
            c.toggled.connect(self.neu_rechnen)
        self.werkstoff.editingFinished.connect(self.neu_rechnen)
        self.eingabe.itemChanged.connect(lambda _: self.neu_rechnen())
        self._laedt = False
        self.neu_rechnen()

    def zeile_neu(self, b):
        alt = self._laedt
        self._laedt = True
        r = self.eingabe.rowCount()
        self.eingabe.insertRow(r)
        cb = QComboBox()
        cb.addItems(fn.ARTEN)
        cb.setCurrentText(b.get("art") or fn.PLAN)
        cb.currentTextChanged.connect(self.neu_rechnen)
        self.eingabe.setCellWidget(r, 0, cb)
        self.eingabe.setItem(r, 1, QTableWidgetItem(_min(float(b.get("anzahl") or 1)).rstrip("0").rstrip(",")))
        for c, n in FELD.items():
            v = b.get(n)
            self.eingabe.setItem(r, c, QTableWidgetItem("" if v in (None, "") else dp._fmm(float(v))))
        self._laedt = alt
        self.neu_rechnen()

    def _entfernen(self):
        r = self.eingabe.currentRow()
        if r >= 0:
            self.eingabe.removeRow(r)
            self.neu_rechnen()

    def eingaben(self):
        bearb = []
        for r in range(self.eingabe.rowCount()):
            b = dict(art=self.eingabe.cellWidget(r, 0).currentText(),
                     anzahl=_zahl((self.eingabe.item(r, 1) or QTableWidgetItem("1")).text()) or 1)
            for c, n in FELD.items():
                it = self.eingabe.item(r, c)
                v = _zahl(it.text()) if it else None
                if v is not None and n in fn.MASSE[b["art"]]:
                    b[n] = v
            bearb.append(b)
        return dict(self.e, werkstoff=self.werkstoff.text().strip() or None, stueck=self.stueck.value(),
                    gewicht=self.gewicht.value() or None, laenge=self.masse[0].value() or None,
                    breite=self.masse[1].value() or None, hoehe=self.masse[2].value() or None,
                    aufspannungen=self.aufspannungen.value(), ausrichten="ja" if self.ausrichten.isChecked() else "nein",
                    fremd="ja" if self.fremd.isChecked() else "nein", zusatz_eur=self.zusatz.value(),
                    bearbeitungen=bearb)

    def neu_rechnen(self):
        if self._laedt:
            return
        erg = fn.rechnen(self.eingaben(), self.einst)
        self.ergebnis = erg
        self.tabelle.setRowCount(len(erg["arbeitsgaenge"]))
        for r, g in enumerate(erg["arbeitsgaenge"]):
            for c, w in enumerate((g["name"], _min(g["minuten"]), _eur(g["kosten"]), g["info"])):
                it = QTableWidgetItem(w)
                if c in (1, 2):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(r, c, it)
        ampel = erg.get("ampel") or dp.GRUEN
        self.befunde.setText(f"<b style='color:{AMPEL_FARBE[ampel]}'>Machbarkeit: {dp.AMPEL_TEXT[ampel]}</b>"
                             + "".join(f"<br><span style='color:{AMPEL_FARBE[x['stufe']]}'>●</span> {x['text']}"
                                       for x in erg.get("machbarkeit") or ()))
        if erg["fehler"]:
            self.summe.setText("<b>Kein Preis:</b> " + "; ".join(erg["fehler"]))
            return
        self.summe.setText(
            f"Bearbeitung {_min(erg['minuten'])} min je Stück = {_eur(erg['maschine'])}; Rüsten und Programmieren "
            f"{_min(erg['ruesten_min'])} min je Auftrag = {_eur(erg['ruesten_auftrag'])}, je Stück "
            f"{_eur(erg['ruesten'])}; Zusätze {_eur(erg['zusatz'])}"
            + (f"; Aufschlag Lohnfertiger {_eur(erg['aufschlag'])}" if erg.get("fremd") else "")
            + f"<br><b>Fräsen nach Bearbeitung: {_eur(erg['preis'])} je Stück</b> ({dp._gruppe_text(erg)})")
