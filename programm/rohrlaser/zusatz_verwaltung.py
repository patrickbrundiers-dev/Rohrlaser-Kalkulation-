"""Unterreiter 'Zusatzarbeiten' der Einstellungen: Übersicht mit Suche, Filter und Sortierung, Aktionen je Eintrag
(Bearbeiten, Duplizieren, Aktivieren/Deaktivieren, Löschen) und ein Formular für Anlegen, Bearbeiten und Kopieren
mit Preisvorschau.

Die Vorschau rechnet mit rechnen.zusatz_preis, also genau wie das Angebot. Der Verkaufspreis in der Vorschau nimmt
Zuschlag Fertigung bzw. Fremdleistung und Gewinn aus den Einstellungen; im Angebot gelten dessen Werte bzw. die der
Staffel. Der Materialzuschlag des Angebots gilt nur für das Stangenmaterial, nie für Zusatzarbeiten.
"""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
                               QWidget)

from . import hilfe, rechnen, tastatur
from .stammdaten import (TABELLE, ZEITEINHEITEN, ZUSATZ_EINHEIT, ZUSATZ_KATEGORIEN, ZUSATZART_TEXT, ZUSATZARTEN,
                         ZUSCHLAG_ARTEN, ZUSCHLAG_BASIS, zahl_als_text, zahl_aus_text)

TITEL = "Zusatzarbeiten"
BREIT = 1280        # ab dieser Breite steht das Formular neben der Tabelle, darunter in einem eigenen Fenster
EIGENER_SATZ = "eigener Stundensatz"
from .stil import ROT, ROTER_RAHMEN, TEXT_GRAU as GRAU  # noqa: E402
FELD = {f.name: f for f in TABELLE["zusatzarbeiten"].felder}
# Reihenfolge der Abrechnung in der Auswahl (häufigste zuerst)
ARTEN = ("€/Stück", "€/Angebot", "€/kg", "€/m²", "€/m", "s/Stück")
assert set(ARTEN) == set(ZUSATZARTEN)


def euro(w):
    return f"{zahl_als_text(w, 2)} €" if isinstance(w, (int, float)) else ""


def prozent(w):
    return f"{zahl_als_text(round(w, 4))} %" if isinstance(w, (int, float)) else ""


def _n(w):
    return w if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0


def aktiv(z):
    """Leer zählt als aktiv (Einträge aus Dateien vor Schema 15)."""
    return z.get("aktiv") != "nein"


def art_text(art):
    return f"{art} ({ZUSATZART_TEXT[art]})" if art in ZUSATZART_TEXT else (art or "")


def zeit_text(z):
    if z.get("art") == "s/Stück":
        return f"{zahl_als_text(_n(z.get('preis')))} s Laser" if z.get("preis") is not None else ""
    if not _n(z.get("zeit")):
        return ""
    return f"{zahl_als_text(z['zeit'])} {z.get('zeit_einheit') or 'min'}"


def satz_text(z, saetze):
    if z.get("art") == "s/Stück" or not _n(z.get("zeit")):
        return ""
    if z.get("satz_id"):
        return f"{z['satz_id']} ({euro(saetze.get(z['satz_id']))}/h)" if saetze.get(z["satz_id"]) is not None \
            else f"{z['satz_id']} (unbekannt)"
    return f"{euro(z.get('satz'))}/h" if z.get("satz") is not None else ""


def material_zuschlag_text(z):
    w = _n(z.get("zuschlag_material"))
    if not w:
        return ""
    return euro(w) if z.get("zuschlag_material_art") == "€" else prozent(w)


def weitere_text(z):
    w = _n(z.get("zuschlag_weitere"))
    return f"{prozent(w)} auf {z.get('zuschlag_weitere_basis') or 'Arbeit und Material'}" if w else ""


def vorgaben(db):
    """Zuschläge und Gewinn aus den Einstellungen (Anteile) für den Verkaufspreis in der Vorschau."""
    return {n: _n(db.einstellung(n)) for n in ("zuschlag_fertigung", "zuschlag_fremdleistung", "gewinn")}


def verkauf(z, preis, vg):
    """Verkaufspreis je Einheit mit den Vorgaben: (Preis × (1 + Zuschlag Fertigung bzw. Fremdleistung)) × (1 + Gewinn)."""
    zs = vg["zuschlag_fremdleistung"] if z.get("fremd") == "ja" else vg["zuschlag_fertigung"]
    return preis * (1 + zs) * (1 + vg["gewinn"])


def kopie_name(name, vorhanden):
    """'Name (Kopie)', bei Bedarf 'Name (Kopie 2)', 'Name (Kopie 3)' … (frei in vorhanden)."""
    vorhanden = {v.lower() for v in vorhanden}
    kandidat, i = f"{name} (Kopie)", 2
    while kandidat.lower() in vorhanden:
        kandidat, i = f"{name} (Kopie {i})", i + 1
    return kandidat


def grundlage_text(z):
    """Berechnungsgrundlage im Angebot in einem Satz."""
    art = z.get("art")
    if art == "s/Stück":
        return ("Die Zeit je Stück kommt zur Laserzeit und wird mit dem Stundensatz für Laser schneiden bewertet; "
                "danach Zuschlag Fertigung und Gewinn wie die übrige Laserzeit.")
    menge = {"€/kg": "× Teilegewicht [kg]", "€/m²": "× Außenfläche [m²]", "€/m": "× Teilelänge [m]",
             "€/Stück": "× Stückzahl"}.get(art)
    t = (f"Im Angebot: Preis je Einheit {menge} der Position" if menge else
         "Im Angebot: Preis einmal je Angebot, umgelegt auf die Teile der Positionen mit dieser Zusatzarbeit")
    if _n(z.get("mindest")):
        t += f", mindestens {euro(z['mindest'])} je Angebot"
    t += (", dann Zuschlag " + ("Fremdleistung" if z.get("fremd") == "ja" else "Fertigung")
          + " und Gewinn des Angebots bzw. der Staffel, Skonto und Rundung wie im übrigen Angebot. Der Preisstand "
          "wird beim Hinzufügen in der Position gespeichert; spätere Änderungen hier ändern alte Angebote nicht.")
    return t


def rechenzeilen(z, saetze, vg):
    """Zeilen der Preisvorschau: [(Text, Betrag, fett)]; Nullwerte entfallen außer Selbstkosten und Verkaufspreis."""
    if z.get("art") == "s/Stück":
        return [("Maschinenzeit je Stück", f"{zahl_als_text(_n(z.get('preis')))} s", True)]
    pr = rechnen.zusatz_preis(z, saetze)
    out = []
    if pr["fest"]:
        out.append(("Festpreis", euro(pr["fest"]), False))
    if pr["arbeit"] or pr["zeit_s"]:
        out.append((f"Arbeitskosten: {zeit_text(z)} × {euro(pr['satz'])}/h", euro(pr["arbeit"]), False))
    if pr["material"]:
        out.append(("Materialkosten", euro(pr["material"]), False))
    if pr["zuschlag_material"]:
        out.append((f"Materialzuschlag {material_zuschlag_text(z)}", euro(pr["zuschlag_material"]), False))
        out.append(("Material inklusive Zuschlag", euro(pr["material_inkl"]), False))
    if pr["weitere"]:
        out.append((f"Weiterer Zuschlag {weitere_text(z)}", euro(pr["weitere"]), False))
    einheit = ZUSATZ_EINHEIT.get(z.get("art"), "Einheit")
    out.append((f"Selbstkosten je {einheit}", euro(pr["preis"]), True))
    fremd = z.get("fremd") == "ja"
    zs = vg["zuschlag_fremdleistung"] if fremd else vg["zuschlag_fertigung"]
    if zs:
        out.append((f"Zuschlag {'Fremdleistung' if fremd else 'Fertigung'} {prozent(zs * 100)} (Vorgabe)",
                    euro(pr["preis"] * zs), False))
    if vg["gewinn"]:
        out.append((f"Gewinn {prozent(vg['gewinn'] * 100)} (Vorgabe)", euro(pr["preis"] * (1 + zs) * vg["gewinn"]), False))
    out.append((f"Verkaufspreis je {einheit} (mit Vorgaben)", euro(verkauf(z, pr["preis"], vg)), True))
    return out


# ------------------------------------------------------------------ Formular
class ZusatzFormular(QWidget):
    """Ein Formular für Anlegen, Bearbeiten und Duplizieren. laden() füllt es, Speichern schreibt erst dann in die
    Datenbank (gespeichert(ID)), Abbrechen verwirft alles (abgebrochen)."""
    gespeichert = Signal(int)
    abgebrochen = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.zeilen_id = None
        self.geaendert = False
        self._laedt = False
        self.saetze = {}
        self.vg = vorgaben(db)

        self.titel = QLabel()
        self.titel.setObjectName("kartentitel")
        # Bereich 1: allgemeine Angaben
        self.name = QLineEdit()
        self.name.setPlaceholderText("z. B. Entgraten von Hand")
        self.kategorie = QComboBox()
        self.kategorie.setEditable(True)
        self.kategorie.lineEdit().setPlaceholderText("z. B. Oberfläche")
        self.beschreibung = QLineEdit()
        self.beschreibung.setPlaceholderText("kurze Beschreibung")
        self.art = QComboBox()
        for a in ARTEN:
            self.art.addItem(art_text(a), a)
        self.aktiv = QCheckBox("aktiv (im Angebot auswählbar)")
        # Bereich 2: Arbeitszeit und Kosten
        self.preis = self._zahl("0,00")
        self.preis_einheit = QLabel("€")
        self.zeit = self._zahl("0")
        self.zeit_einheit = QComboBox()
        self.zeit_einheit.addItems(list(ZEITEINHEITEN))
        self.satz_id = QComboBox()
        self.satz = self._zahl("0,00")
        self.arbeit = QLabel()
        self.arbeit.setStyleSheet(f"color: {GRAU};")
        # Bereich 3: Material und Zuschläge
        self.material = self._zahl("0,00")
        self.zuschlag_material = self._zahl("0")
        self.zuschlag_material_art = QComboBox()
        self.zuschlag_material_art.addItems(list(ZUSCHLAG_ARTEN))
        self.material_inkl = QLabel()
        self.material_inkl.setStyleSheet(f"color: {GRAU};")
        # weitere Optionen
        self.zuschlag_weitere = self._zahl("0")
        self.zuschlag_weitere_basis = QComboBox()
        self.zuschlag_weitere_basis.addItems(list(ZUSCHLAG_BASIS))
        self.zuschlag_weitere_basis.setCurrentText("Arbeit und Material")
        self.mindest = self._zahl("0,00")
        self.fremd = QCheckBox("Fremdleistung (Zuschlag Fremdleistung statt Fertigung)")
        self.angebotstext = QLineEdit()
        self.angebotstext.setPlaceholderText("leer = Name")
        # Ergebnis
        self.ergebnis = QWidget()
        self.ergebnis_gitter = QGridLayout(self.ergebnis)
        self.ergebnis_gitter.setContentsMargins(0, 0, 0, 0)
        self.ergebnis_gitter.setColumnStretch(2, 1)
        self.ergebnis_zeilen = []
        self.grundlage = QLabel()
        self.grundlage.setWordWrap(True)
        self.grundlage.setStyleSheet(f"color: {GRAU};")
        self.fehler = QLabel()
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(f"color: {ROT}; font-weight: bold;")
        self.speichern_knopf = QPushButton("Speichern")
        self.speichern_knopf.setObjectName("primaer")
        self.speichern_knopf.clicked.connect(self.speichern)
        self.abbrechen_knopf = QPushButton("Abbrechen")
        self.abbrechen_knopf.clicked.connect(self.abbrechen)

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.titel)
        f1 = self._bereich(lay, "Allgemeine Angaben")
        f1.addRow("Name *", self.name)
        f1.addRow("Kategorie", self.kategorie)
        f1.addRow("Beschreibung", self.beschreibung)
        f1.addRow("Abrechnung *", self.art)
        f1.addRow("", self.aktiv)
        self.f2 = self._bereich(lay, "Arbeitszeit und Kosten")
        self.preis_titel = QLabel("Festpreis je Einheit")
        self.f2.addRow(self.preis_titel, self._zeile(self.preis, self.preis_einheit))
        self.f2.addRow("Zeitaufwand je Einheit", self._zeile(self.zeit, self.zeit_einheit))
        self.f2.addRow("Stundensatz", self._zeile(self.satz_id, self.satz, QLabel("€/h")))
        self.f2.addRow("Arbeitskosten", self.arbeit)
        self.box3 = QWidget()
        f3 = self._bereich(lay, "Material und Zuschläge", self.box3)
        f3.addRow("Materialkosten je Einheit", self._zeile(self.material, QLabel("€")))
        f3.addRow("Materialzuschlag", self._zeile(self.zuschlag_material, self.zuschlag_material_art))
        f3.addRow("Material inklusive Zuschlag", self.material_inkl)
        self.mehr = QToolButton()
        self.mehr.setObjectName("aufklapper")
        self.mehr.setCheckable(True)
        self.mehr.toggled.connect(self._mehr_zeigen)
        lay.addWidget(self.mehr)
        self.box_mehr = QWidget()
        f4 = self._bereich(lay, "Weitere Optionen", self.box_mehr)
        self.zeile_weitere = self._zeile(self.zuschlag_weitere, QLabel("% auf"), self.zuschlag_weitere_basis)
        f4.addRow("Weiterer Zuschlag", self.zeile_weitere)
        f4.addRow("Mindestbetrag je Angebot", self._zeile(self.mindest, QLabel("€")))
        f4.addRow("", self.fremd)
        f4.addRow("Text im Angebot", self.angebotstext)
        f5 = self._bereich(lay, "Ergebnis")
        f5.addRow(self.ergebnis)
        f5.addRow(self.grundlage)
        lay.addStretch(1)
        rollen = QScrollArea()
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QFrame.NoFrame)
        rollen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rollen.setWidget(inhalt)
        knoepfe = QHBoxLayout()
        knoepfe.addWidget(self.speichern_knopf)
        knoepfe.addWidget(self.abbrechen_knopf)
        knoepfe.addStretch(1)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(rollen, 1)
        aussen.addWidget(self.fehler)
        aussen.addLayout(knoepfe)
        self.setMinimumWidth(420)

        for w in (self.name, self.beschreibung, self.preis, self.zeit, self.satz, self.material,
                  self.zuschlag_material, self.zuschlag_weitere, self.mindest, self.angebotstext):
            w.textEdited.connect(self._geaendert)
        self.kategorie.editTextChanged.connect(self._geaendert)
        for w in (self.art, self.zeit_einheit, self.satz_id, self.zuschlag_material_art, self.zuschlag_weitere_basis):
            w.currentIndexChanged.connect(self._geaendert)
        for w in (self.aktiv, self.fremd):
            w.toggled.connect(self._geaendert)
        for w, stellen in ((self.preis, 2), (self.satz, 2), (self.material, 2), (self.mindest, 2),
                           (self.zuschlag_material, None), (self.zuschlag_weitere, None), (self.zeit, None)):
            w.editingFinished.connect(lambda w=w, s=stellen: self._formatieren(w, s))
        self._mehr_zeigen(False)

    # -------------------------------------------------------------- Aufbau
    def _zahl(self, platzhalter):
        e = QLineEdit()
        e.setPlaceholderText(platzhalter)
        e.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        e.setMaximumWidth(110)
        return e

    @staticmethod
    def _zeile(*widgets):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            h.addWidget(x)
        h.addStretch(1)
        return w

    @staticmethod
    def _bereich(lay, titel, behaelter=None):
        behaelter = behaelter or QWidget()
        v = QVBoxLayout(behaelter)
        v.setContentsMargins(0, 6, 0, 0)
        t = QLabel(titel)
        t.setObjectName("gruppentitel")
        v.addWidget(t)
        f = QFormLayout()
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        v.addLayout(f)
        lay.addWidget(behaelter)
        return f

    def _mehr_zeigen(self, offen):
        self.box_mehr.setVisible(offen)
        self.mehr.setText(("▾ " if offen else "▸ ") + "Weitere Optionen")
        self.mehr.setToolTip("Weiterer Zuschlag, Mindestbetrag je Angebot, Fremdleistung, Text im Angebot")

    def _formatieren(self, w, stellen):
        try:
            v = zahl_aus_text(w.text()) if w.text().strip() else None    # Bereich prüft werte()
        except ValueError:
            return
        if v is not None:
            w.setText(zahl_als_text(v, stellen, tausender=False) if stellen else zahl_als_text(v, None, False))

    # -------------------------------------------------------------- Laden
    def laden(self, z=None, zeilen_id=None, titel="Neue Zusatzarbeit"):
        """Formular füllen: z = Stammdatenzeile (None = neu mit Standardwerten), zeilen_id = None legt beim
        Speichern neu an (Neu, Duplizieren)."""
        z = dict(z or {})
        self._laedt = True
        self.zeilen_id = zeilen_id
        self.titel.setText(titel)
        self.saetze = rechnen.stundensaetze(self.db.tabellen())
        self.vg = vorgaben(self.db)
        vorhandene = sorted({x.get("kategorie") for x in self.db.zeilen("zusatzarbeiten") if x.get("kategorie")}
                            - set(ZUSATZ_KATEGORIEN))
        self.kategorie.clear()
        self.kategorie.addItems([""] + list(ZUSATZ_KATEGORIEN) + vorhandene)
        self.kategorie.setCurrentText(z.get("kategorie") or "")
        self.satz_id.clear()
        self.satz_id.addItem(EIGENER_SATZ, None)
        for sid, w in sorted(self.saetze.items()):
            self.satz_id.addItem(f"{sid} ({euro(w)}/h)", sid)
        if z.get("satz_id") and z["satz_id"] not in self.saetze:
            self.satz_id.addItem(f"{z['satz_id']} (unbekannt)", z["satz_id"])
        i = self.satz_id.findData(z.get("satz_id")) if z.get("satz_id") else 0
        self.satz_id.setCurrentIndex(max(i, 0))
        self.name.setText(z.get("name") or "")
        self.beschreibung.setText(z.get("bemerkung") or "")
        self.art.setCurrentIndex(max(self.art.findData(z.get("art") or "€/Stück"), 0))
        self.aktiv.setChecked(aktiv(z))
        for n, stellen in (("preis", 2), ("satz", 2), ("material", 2), ("mindest", 2), ("zeit", None),
                           ("zuschlag_material", None), ("zuschlag_weitere", None)):
            w = z.get(n)
            getattr(self, n).setText(zahl_als_text(w, stellen if n != "preis" or z.get("art") != "s/Stück" else None,
                                                   tausender=False) if isinstance(w, (int, float)) else "")
        self.zeit_einheit.setCurrentText(z.get("zeit_einheit") or "min")
        self.zuschlag_material_art.setCurrentText(z.get("zuschlag_material_art") or "%")
        self.zuschlag_weitere_basis.setCurrentText(z.get("zuschlag_weitere_basis") or "Arbeit und Material")
        self.fremd.setChecked(z.get("fremd") == "ja")
        self.angebotstext.setText(z.get("angebotstext") or "")
        self.mehr.setChecked(bool(_n(z.get("zuschlag_weitere")) or _n(z.get("mindest")) or z.get("fremd") == "ja"
                                  or z.get("angebotstext")))
        self._mehr_zeigen(self.mehr.isChecked())
        self._laedt = False
        self.geaendert = False
        self.aktualisieren()
        self.name.setFocus()

    def _geaendert(self, *_):
        if self._laedt:
            return
        self.geaendert = True
        self.aktualisieren()

    # -------------------------------------------------------------- Werte und Vorschau
    def _felder(self):
        """{Feld: Wert} aus den Eingaben und {Feld: Meldung} für ungültige Eingaben."""
        werte, fehler = {}, {}
        werte["name"] = self.name.text().strip() or None
        werte["kategorie"] = self.kategorie.currentText().strip() or None
        werte["bemerkung"] = self.beschreibung.text().strip() or None
        werte["art"] = self.art.currentData()
        werte["aktiv"] = "ja" if self.aktiv.isChecked() else "nein"
        werte["fremd"] = "ja" if self.fremd.isChecked() else "nein"
        werte["angebotstext"] = self.angebotstext.text().strip() or None
        werte["zeit_einheit"] = self.zeit_einheit.currentText()
        werte["satz_id"] = self.satz_id.currentData()
        werte["zuschlag_material_art"] = self.zuschlag_material_art.currentText()
        werte["zuschlag_weitere_basis"] = self.zuschlag_weitere_basis.currentText()
        titel = {"preis": self.preis_titel.text(), "zeit": "Zeitaufwand", "satz": "Stundensatz",
                 "material": "Materialkosten", "zuschlag_material": "Materialzuschlag",
                 "zuschlag_weitere": "Weiterer Zuschlag", "mindest": "Mindestbetrag"}
        for n, t in titel.items():
            text = getattr(self, n).text().strip()
            try:
                w = zahl_aus_text(text) if text else None
            except ValueError:
                fehler[n] = f"{t}: '{text}' ist keine Zahl."
                continue
            if w is not None and w < 0:
                fehler[n] = f"{t}: negative Werte sind nicht zulässig."
            elif w is not None and FELD[n].bis is not None and w > FELD[n].bis:
                fehler[n] = f"{t}: höchstens {zahl_als_text(FELD[n].bis)}."
            else:
                werte[n] = w
        if werte["satz_id"]:
            werte["satz"] = None
        if werte["art"] == "s/Stück":           # nur die Zeit je Stück zählt
            for n in ("zeit", "satz_id", "satz", "material", "zuschlag_material", "zuschlag_weitere"):
                werte[n] = None
                fehler.pop(n, None)
        return werte, fehler

    def aktualisieren(self):
        """Sichtbarkeit, rote Felder und Preisvorschau nach jeder Eingabe."""
        s_stueck = self.art.currentData() == "s/Stück"
        self.preis_titel.setText("Maschinenzeit je Stück" if s_stueck else "Festpreis je Einheit")
        self.preis_einheit.setText("s" if s_stueck else "€")
        for i in range(1, self.f2.rowCount()):
            self.f2.setRowVisible(i, not s_stueck)
        self.box3.setVisible(not s_stueck)
        self.zeile_weitere.setEnabled(not s_stueck)
        eigen = self.satz_id.currentData() is None
        self.satz.setEnabled(eigen)
        werte, fehler = self._felder()
        for n in ("preis", "zeit", "satz", "material", "zuschlag_material", "zuschlag_weitere", "mindest"):
            getattr(self, n).setStyleSheet(ROTER_RAHMEN if n in fehler else "")
        if not eigen:
            self.satz.setText(zahl_als_text(self.saetze.get(werte["satz_id"]), 2, tausender=False)
                              if self.saetze.get(werte["satz_id"]) is not None else "")
        pr = rechnen.zusatz_preis(werte, self.saetze)
        self.arbeit.setText(f"{zeit_text(werte) or '0 min'} × {euro(pr['satz'] or 0)}/h = {euro(pr['arbeit'])}")
        self.material_inkl.setText(euro(pr["material_inkl"]))
        self.ergebnis_zeilen = rechenzeilen(werte, self.saetze, self.vg)
        while self.ergebnis_gitter.count():
            self.ergebnis_gitter.takeAt(0).widget().deleteLater()
        for r, (t, b, fett) in enumerate(self.ergebnis_zeilen):
            for c, text in enumerate((t, b)):
                lab = QLabel(text)
                if fett:
                    lab.setStyleSheet("font-weight: bold;")
                if c:
                    lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.ergebnis_gitter.addWidget(lab, r, c)
        self.grundlage.setText(grundlage_text(werte))
        self.fehler.setText("\n".join(fehler.values()))
        return werte, fehler

    def werte(self):
        """Alle Felder der Stammdatenzeile. ValueError mit verständlicher Meldung bei ungültiger Eingabe."""
        werte, fehler = self.aktualisieren()
        if fehler:
            raise ValueError(next(iter(fehler.values())))
        if not werte["name"]:
            raise ValueError("Bitte einen Namen eingeben.")
        andere = {x["name"].lower() for x in self.db.zeilen("zusatzarbeiten")
                  if x.get("name") and x["id"] != self.zeilen_id}
        if werte["name"].lower() in andere:
            raise ValueError(f"Eine Zusatzarbeit '{werte['name']}' gibt es schon. Bitte einen anderen Namen wählen.")
        if werte["art"] == "s/Stück":
            if not _n(werte.get("preis")):
                raise ValueError("Bitte die Maschinenzeit je Stück in Sekunden eingeben.")
        elif not any(_n(werte.get(n)) for n in ("preis", "zeit", "material")):
            raise ValueError("Bitte einen Festpreis, einen Zeitaufwand oder Materialkosten eingeben.")
        if _n(werte.get("zeit")) and not werte.get("satz_id") and werte.get("satz") is None:
            raise ValueError("Bitte einen Stundensatz wählen oder eingeben.")
        return {n: werte.get(n) for n in FELD}

    # -------------------------------------------------------------- Knöpfe
    def speichern(self):
        try:
            werte = self.werte()
            i = self.db.zusatz_speichern(self.zeilen_id, werte)
        except ValueError as e:
            self.fehler.setText(str(e))
            return False
        self.zeilen_id = i
        self.geaendert = False
        self.gespeichert.emit(i)
        return True

    def abbrechen(self):
        self.geaendert = False
        self.abgebrochen.emit()


# ------------------------------------------------------------------ Übersicht
# (Titel, Schlüssel, immer sichtbar)
SPALTEN = (("Name", "name", True), ("Kategorie", "kategorie", True), ("Abrechnung", "art", True),
           ("Beschreibung", "bemerkung", False), ("Zeitaufwand", "zeit", False), ("Stundensatz", "satz", False),
           ("Arbeitskosten", "arbeit", False), ("Material", "material", False),
           ("Materialzuschlag", "zuschlag_material", False), ("Weitere Zuschläge", "weitere", False),
           ("Mindestbetrag", "mindest", False), ("Preis je Einheit", "preis", True),
           ("Verkaufspreis (Vorgaben)", "verkauf", True), ("Status", "status", True))
SORTIERUNG = ("Name", "Preis", "Zeitaufwand", "Kategorie")
# bei schmalem Fenster zuerst weggelassen (stehen im Detailbereich)
WEGLASSEN = ("zuschlag_material", "weitere", "arbeit", "satz", "mindest", "material", "bemerkung", "zeit", "kategorie")


class ZusatzVerwaltung(QWidget):
    titel = TITEL
    KUERZEL = {"neu": "neu", "loeschen": ("loeschen", "tabelle")}     # Tastenkürzel, siehe tastatur.py

    def __init__(self, db, meldung):
        super().__init__()
        self.db, self.meldung = db, meldung
        self.daten = []
        self.sichtbar = []
        self.dialog = None

        neu = QPushButton("+ Zusatzarbeit hinzufügen")
        neu.setObjectName("primaer")
        neu.clicked.connect(self.neu)
        self.neu_knopf = neu
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen (Name, Kategorie, Beschreibung) …")
        self.suche.setClearButtonEnabled(True)
        tastatur.suche_esc(self.suche)
        self.suche.textChanged.connect(self.anzeigen)
        self.kat_filter = QComboBox()
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Alle", "Aktive", "Inaktive"])
        self.sortierung = QComboBox()
        self.sortierung.addItems(list(SORTIERUNG))
        for cb in (self.kat_filter, self.status_filter, self.sortierung):
            cb.currentIndexChanged.connect(self.anzeigen)
        self.anzahl = QLabel()
        self.anzahl.setStyleSheet(f"color: {GRAU};")
        leiste = QGridLayout()
        leiste.addWidget(neu, 0, 0)
        leiste.addWidget(self.suche, 0, 1, 1, 3)
        for i, (t, w) in enumerate((("Kategorie", self.kat_filter), ("Status", self.status_filter),
                                    ("Sortieren nach", self.sortierung))):
            box = QHBoxLayout()
            box.addWidget(QLabel(t))
            box.addWidget(w, 1)
            leiste.addLayout(box, 1, i + 1)
        leiste.addWidget(self.anzahl, 1, 0)
        leiste.setColumnStretch(1, 1)
        leiste.setColumnStretch(2, 1)
        leiste.setColumnStretch(3, 1)

        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels([s[0] for s in SPALTEN])
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        self.tabelle.setWordWrap(False)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(3, QHeaderView.Stretch)      # Beschreibung nimmt den Rest (gekürzt mit …)
        kopf.setStretchLastSection(False)
        kopf.setMinimumSectionSize(40)
        self.tabelle.setTextElideMode(Qt.ElideRight)
        kopf.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.tabelle.itemSelectionChanged.connect(self._auswahl)
        self.tabelle.itemDoubleClicked.connect(lambda _: self.bearbeiten())
        self.tabelle.viewport().installEventFilter(self)
        self.tabelle.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabelle.customContextMenuRequested.connect(self._kontextmenue)

        self.k_bearbeiten = QPushButton("Bearbeiten")
        self.k_duplizieren = QPushButton("Duplizieren")
        self.k_aktiv = QPushButton("Deaktivieren")
        self.k_loeschen = QPushButton("Löschen")
        aktionen = QHBoxLayout()
        for k, f in ((self.k_bearbeiten, self.bearbeiten), (self.k_duplizieren, self.duplizieren),
                     (self.k_aktiv, self.aktiv_umschalten), (self.k_loeschen, self.loeschen)):
            k.clicked.connect(lambda _=False, f=f: f())
            aktionen.addWidget(k)
        aktionen.addStretch(1)
        self.detail = QLabel()
        self.detail.setTextFormat(Qt.RichText)
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        detail_rahmen = QFrame()
        detail_rahmen.setObjectName("karte")
        dl = QVBoxLayout(detail_rahmen)
        dl.addWidget(self.detail)

        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.tabelle, 1)
        ll.addLayout(aktionen)
        ll.addWidget(detail_rahmen)
        self.formular = ZusatzFormular(db)
        self.formular.gespeichert.connect(self._gespeichert)
        self.formular.abgebrochen.connect(self._formular_zu)
        self.rechts = QFrame()
        self.rechts.setObjectName("karte")
        rl = QVBoxLayout(self.rechts)
        rl.addWidget(self.formular)
        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.addWidget(links)
        self.teiler.addWidget(self.rechts)
        self.teiler.setStretchFactor(0, 3)
        self.teiler.setStretchFactor(1, 2)
        self.teiler.setChildrenCollapsible(False)
        self.rechts.hide()

        hinweis = hilfe.Hinweis("Zusatzarbeiten für 'Zusatzarbeiten …' im Angebot. Preis je Einheit = Festpreis + "
                                "Zeitaufwand × Stundensatz + Material mit Zuschlag + weiterer Zuschlag; im Angebot "
                                "kommen Zuschlag Fertigung bzw. Fremdleistung und Gewinn dazu. Leere oder nicht "
                                "verwendete Spalten sind ausgeblendet.",
                                schluessel="zusatzarbeiten")
        lay = QVBoxLayout(self)
        lay.addWidget(hinweis)
        lay.addLayout(leiste)
        lay.addWidget(self.teiler, 1)
        self.neu_laden()

    # -------------------------------------------------------------- Daten
    def neu_laden(self):
        self.saetze = rechnen.stundensaetze(self.db.tabellen())
        self.vg = vorgaben(self.db)
        self.daten = self.db.zeilen("zusatzarbeiten")
        for z in self.daten:
            pr = rechnen.zusatz_preis(z, self.saetze)
            z["_preis"] = pr
        kat = self.kat_filter.currentText()
        self.kat_filter.blockSignals(True)
        self.kat_filter.clear()
        kategorien = sorted({z.get("kategorie") or "" for z in self.daten}, key=lambda k: (k == "", k.lower()))
        self.kat_filter.addItems(["Alle"] + [k or "ohne Kategorie" for k in kategorien])
        self.kat_filter.setCurrentText(kat if kat else "Alle")
        self.kat_filter.blockSignals(False)
        self.anzeigen()

    def zeile(self, zeilen_id):
        return next((z for z in self.daten if z["id"] == zeilen_id), None)

    def gefiltert(self):
        """Einträge nach Suche, Kategorie und Status, sortiert."""
        such = self.suche.text().strip().lower()
        kat = self.kat_filter.currentText()
        status = self.status_filter.currentText()
        out = []
        for z in self.daten:
            if such and not any(such in str(z.get(n) or "").lower() for n in ("name", "kategorie", "bemerkung",
                                                                                "angebotstext")):
                continue
            if kat not in ("", "Alle") and (z.get("kategorie") or "ohne Kategorie") != kat:
                continue
            if status == "Aktive" and not aktiv(z) or status == "Inaktive" and aktiv(z):
                continue
            out.append(z)
        art = self.sortierung.currentText()
        name = lambda z: (z.get("name") or "").lower()
        if art == "Preis":
            out.sort(key=lambda z: (z.get("art") == "s/Stück", -z["_preis"]["preis"], name(z)))
        elif art == "Zeitaufwand":
            out.sort(key=lambda z: (-(_n(z.get("preis")) if z.get("art") == "s/Stück" else z["_preis"]["zeit_s"]),
                                    name(z)))
        elif art == "Kategorie":
            out.sort(key=lambda z: ((z.get("kategorie") or "~").lower(), name(z)))
        else:
            out.sort(key=name)
        return out

    def zellen(self, z):
        """Anzeigetexte je Spalte und ob der Wert leer bzw. 0 ist."""
        pr = z["_preis"]
        s_stueck = z.get("art") == "s/Stück"
        werte = dict(name=z.get("name") or "", kategorie=z.get("kategorie") or "", art=art_text(z.get("art")),
                     bemerkung=z.get("bemerkung") or "", zeit=zeit_text(z), satz=satz_text(z, self.saetze),
                     arbeit=euro(pr["arbeit"]) if pr["arbeit"] else "",
                     material=euro(pr["material"]) if pr["material"] else "",
                     zuschlag_material=material_zuschlag_text(z), weitere=weitere_text(z),
                     mindest=euro(z.get("mindest")) if _n(z.get("mindest")) else "",
                     preis=f"{zahl_als_text(pr['preis'])} s" if s_stueck else euro(pr["preis"]),
                     verkauf="Laserzeit" if s_stueck else euro(verkauf(z, pr["preis"], self.vg)),
                     status="aktiv" if aktiv(z) else "inaktiv")
        return werte

    def anzeigen(self, *_):
        gewaehlt = self.gewaehlt()
        self.sichtbar = self.gefiltert()
        zellen = [self.zellen(z) for z in self.sichtbar]
        self.tabelle.setRowCount(len(self.sichtbar))
        for r, (z, w) in enumerate(zip(self.sichtbar, zellen)):
            for c, (_, n, _) in enumerate(SPALTEN):
                it = QTableWidgetItem(w[n])
                it.setData(Qt.UserRole, z["id"])
                if n in ("zeit", "satz", "arbeit", "material", "zuschlag_material", "mindest", "preis", "verkauf"):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if n in ("preis", "verkauf"):
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                if not aktiv(z):
                    it.setForeground(Qt.gray)
                if n == "art":
                    it.setToolTip(grundlage_text(z))
                self.tabelle.setItem(r, c, it)
        self.zellen_text = zellen
        self._einpassen()
        n_alle = len(self.daten)
        inaktiv = sum(1 for z in self.daten if not aktiv(z))
        self.anzahl.setText(f"{len(self.sichtbar)} von {n_alle} Einträgen" + (f", {inaktiv} inaktiv" if inaktiv else ""))
        self.auswaehlen(gewaehlt)
        self._auswahl()

    def _einpassen(self):
        """Nullwert-Regel: leere optionale Spalten ausblenden. Ist das Fenster zu schmal, fallen weitere
        Detailspalten weg (sie stehen im Detailbereich), damit die Tabelle nicht waagrecht rollt."""
        zellen = getattr(self, "zellen_text", [])
        for c, (_, n, immer) in enumerate(SPALTEN):
            self.tabelle.setColumnHidden(c, not immer and not any(w[n] for w in zellen))
        platz = self.tabelle.viewport().width()
        if platz <= 0:
            return
        kopf = self.tabelle.horizontalHeader()

        def bedarf():
            return sum(max(kopf.sectionSizeHint(c), self.tabelle.sizeHintForColumn(c)) if n != "bemerkung" else 60
                       for c, (_, n, _) in enumerate(SPALTEN) if not self.tabelle.isColumnHidden(c))
        for n in WEGLASSEN:
            if bedarf() + 12 <= platz:      # Reserve für Rahmen und Abstände der Kopfzeile
                break
            self.tabelle.setColumnHidden(next(c for c, x in enumerate(SPALTEN) if x[1] == n), True)

    def eventFilter(self, objekt, ereignis):
        # Tabelle ändert ihre Breite (Fenster, Formular daneben, Teiler verschoben): Spalten neu einpassen
        if objekt is self.tabelle.viewport() and ereignis.type() == QEvent.Resize:
            self._einpassen()
        return super().eventFilter(objekt, ereignis)

    def spalte_sichtbar(self, titel):
        c = next(i for i, s in enumerate(SPALTEN) if s[0] == titel)
        return not self.tabelle.isColumnHidden(c)

    def gewaehlt(self):
        r = self.tabelle.currentRow()
        if r < 0 or r >= len(self.sichtbar) or not self.tabelle.selectionModel().hasSelection():
            return None
        return self.sichtbar[r]["id"]

    def auswaehlen(self, zeilen_id):
        for r, z in enumerate(self.sichtbar):
            if z["id"] == zeilen_id:
                self.tabelle.selectRow(r)
                return True
        self.tabelle.clearSelection()
        return False

    def _auswahl(self):
        z = self.zeile(self.gewaehlt())
        for k in (self.k_bearbeiten, self.k_duplizieren, self.k_aktiv, self.k_loeschen):
            k.setEnabled(z is not None)
        self.k_aktiv.setText("Aktivieren" if z and not aktiv(z) else "Deaktivieren")
        if not z:
            self.detail.setText(f"<span style='color:{GRAU}'>Eintrag markieren: hier steht die vollständige "
                                "Berechnung.</span>")
            return
        zeilen = rechenzeilen(z, self.saetze, self.vg)
        tab = "".join(f"<tr><td style='padding-right:16px'>{t}</td><td align='right'>"
                      f"{'<b>' if f else ''}{b}{'</b>' if f else ''}</td></tr>" for t, b, f in zeilen)
        extra = [f"Abrechnung {art_text(z.get('art'))}"]
        if z.get("bemerkung"):
            extra.append(z["bemerkung"])
        if z.get("angebotstext"):
            extra.append(f"Text im Angebot: {z['angebotstext']}")
        if z.get("fremd") == "ja":
            extra.append("Fremdleistung")
        v = self.db.zusatz_verwendung(z.get("name"))
        if v["positionen"]:
            extra.append(f"verwendet in {v['positionen']} Position(en), {len(v['angebote'])} Angebot(en)")
        self.detail.setText(f"<b>{z.get('name') or ''}</b> &nbsp; <span style='color:{GRAU}'>"
                            f"{' · '.join(extra)}</span><table>{tab}</table>"
                            f"<span style='color:{GRAU}'>{grundlage_text(z)}</span>")

    def _kontextmenue(self, pos):
        if self.tabelle.itemAt(pos) is None:
            return
        self.tabelle.selectRow(self.tabelle.itemAt(pos).row())
        m = QMenu(self)
        for t, f in (("Bearbeiten", self.bearbeiten), ("Duplizieren", self.duplizieren),
                     (self.k_aktiv.text(), self.aktiv_umschalten), ("Löschen", self.loeschen)):
            m.addAction(t, f)
        m.exec(self.tabelle.viewport().mapToGlobal(pos))

    # -------------------------------------------------------------- Formular öffnen
    def schmal(self):
        return self.width() < BREIT

    def _frage(self, titel, text, knoepfe, standard):
        """Rückfrage mit eigenen Knöpfen; Ergebnis: Text des gewählten Knopfs (Abbrechen bei Schließen)."""
        box = QMessageBox(QMessageBox.Question, titel, text, parent=self)
        k = {t: box.addButton(t, QMessageBox.RejectRole if t == "Abbrechen" else QMessageBox.AcceptRole)
             for t in knoepfe}
        box.setDefaultButton(k[standard])
        box.exec()
        return next((t for t, b in k.items() if b is box.clickedButton()), "Abbrechen")

    def formular_offen(self):
        return self.rechts.isVisible() or (self.dialog is not None and self.dialog.isVisible())

    def aktives_formular(self):
        return self.dialog.formular if self.dialog is not None and self.dialog.isVisible() else self.formular

    def _verwerfen_ok(self):
        if self.formular_offen() and self.aktives_formular().geaendert:
            return self._frage("Ungespeicherte Änderungen", "Die Änderungen im Formular sind noch nicht gespeichert. "
                               "Verwerfen?", ("Verwerfen", "Abbrechen"), "Abbrechen") == "Verwerfen"
        return True

    def _oeffnen(self, z, zeilen_id, titel):
        if not self._verwerfen_ok():
            return None
        self._formular_zu()
        if self.schmal():
            self.dialog = QDialog(self)
            self.dialog.setWindowTitle(titel)
            self.dialog.resize(560, 720)
            self.dialog.formular = ZusatzFormular(self.db, self.dialog)
            QVBoxLayout(self.dialog).addWidget(self.dialog.formular)
            self.dialog.formular.gespeichert.connect(self._gespeichert)
            self.dialog.formular.abgebrochen.connect(self._formular_zu)
            self.dialog.rejected.connect(self._formular_zu)
            self.dialog.formular.laden(z, zeilen_id, titel)
            self.dialog.setModal(True)
            self.dialog.show()
            return self.dialog.formular
        self.formular.laden(z, zeilen_id, titel)
        self.rechts.show()
        w = self.teiler.width()
        self.teiler.setSizes([w - 520, 520])
        return self.formular

    def _formular_zu(self):
        self.rechts.hide()
        if self.dialog is not None:
            d, self.dialog = self.dialog, None
            d.blockSignals(True)
            d.close()
            d.deleteLater()

    def _gespeichert(self, zeilen_id):
        self._formular_zu()
        self.neu_laden()
        if not self.auswaehlen(zeilen_id):        # durch Filter verdeckt: Filter zurücksetzen
            self.suche.clear()
            self.kat_filter.setCurrentIndex(0)
            self.status_filter.setCurrentIndex(0)
            self.auswaehlen(zeilen_id)
        z = self.zeile(zeilen_id)
        self.meldung(f"Zusatzarbeit '{z.get('name') if z else ''}' gespeichert.")

    # -------------------------------------------------------------- Aktionen
    def neu(self):
        return self._oeffnen(None, None, "Neue Zusatzarbeit")

    def bearbeiten(self, zeilen_id=None):
        z = self.zeile(zeilen_id or self.gewaehlt())
        if not z:
            self.meldung("Bitte zuerst eine Zusatzarbeit markieren.", fehler=True)
            return None
        return self._oeffnen(z, z["id"], f"Zusatzarbeit bearbeiten: {z.get('name')}")

    def duplizieren(self, zeilen_id=None):
        z = self.zeile(zeilen_id or self.gewaehlt())
        if not z:
            self.meldung("Bitte zuerst eine Zusatzarbeit markieren.", fehler=True)
            return None
        kopie = {n: z.get(n) for n in FELD}
        kopie["name"] = kopie_name(z.get("name") or "", [x.get("name") or "" for x in self.daten])
        return self._oeffnen(kopie, None, f"Kopie von {z.get('name')} (wird erst mit Speichern angelegt)")

    def aktiv_umschalten(self, zeilen_id=None):
        z = self.zeile(zeilen_id or self.gewaehlt())
        if not z:
            return
        self.db.aendern("zusatzarbeiten", z["id"], "aktiv", "ja" if not aktiv(z) else "nein")
        self.neu_laden()
        self.auswaehlen(z["id"])
        self.meldung(f"Zusatzarbeit '{z['name']}' {'deaktiviert' if aktiv(z) else 'aktiviert'}.")

    def loeschen(self, zeilen_id=None):
        """Sicherheitsabfrage; wird die Zusatzarbeit in Angeboten verwendet, wird Deaktivieren empfohlen.
        Ergebnis: 'gelöscht', 'deaktiviert' oder None."""
        z = self.zeile(zeilen_id or self.gewaehlt())
        if not z:
            self.meldung("Bitte zuerst eine Zusatzarbeit markieren.", fehler=True)
            return None
        v = self.db.zusatz_verwendung(z["name"])
        if not v["positionen"]:
            if self._frage("Löschen", f"Zusatzarbeit '{z['name']}' löschen?", ("Löschen", "Abbrechen"),
                           "Abbrechen") != "Löschen":
                return None
        else:
            nummern = ", ".join(v["angebote"][:8]) + (" …" if len(v["angebote"]) > 8 else "")
            text = (f"Die Zusatzarbeit '{z['name']}' wird in {v['positionen']} Position(en) verwendet "
                    f"(Angebote {nummern}).\n\nEmpfohlen: Deaktivieren. Sie ist dann im Angebot nicht mehr "
                    "auswählbar, bestehende Angebote bleiben unverändert.")
            if v["ohne_stand"]:
                text += (f"\n\nBeim Löschen verlieren {v['ohne_stand']} ältere Position(en) ohne gespeicherten "
                         "Preisstand diese Zusatzarbeit (Status 'Zusatzarbeit unbekannt'). Positionen mit "
                         "Preisstand rechnen unverändert weiter.")
            else:
                text += "\n\nAlle Positionen haben einen gespeicherten Preisstand und rechnen auch nach dem Löschen weiter."
            wahl = self._frage("Zusatzarbeit wird verwendet", text, ("Deaktivieren", "Trotzdem löschen", "Abbrechen"),
                               "Deaktivieren")
            if wahl == "Deaktivieren":
                if aktiv(z):
                    self.aktiv_umschalten(z["id"])
                return "deaktiviert"
            if wahl != "Trotzdem löschen":
                return None
        self.db.loeschen("zusatzarbeiten", [z["id"]])
        self.neu_laden()
        self.meldung(f"Zusatzarbeit '{z['name']}' gelöscht.")
        return "gelöscht"
