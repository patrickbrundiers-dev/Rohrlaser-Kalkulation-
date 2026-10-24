"""Hauptreiter 'Zukaufartikel': Unterreiter Artikel (Übersicht mit Suche, Filter, Sortierung, Aktionen und Formular
mit Preisvorschau), Kategorien und Lieferanten (Stammdatentabellen).

Die Vorschau rechnet mit zukauf.vorschau, also genau wie das Angebot; die Oberfläche hat keine eigenen Preisformeln.
"""
import json

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
                               QTabWidget, QToolButton, QVBoxLayout, QWidget)

from . import hilfe, stil, tastatur, zukauf
from .stammdaten import Feld, wert_aus_text, wert_als_text, zahl_als_text, zahl_aus_text

TITEL = "Zukaufartikel"
BREIT = 1280        # ab dieser Breite steht das Formular neben der Tabelle, darunter in einem eigenen Fenster
from .stil import GELB_TEXT as GELB, ROT, ROTER_RAHMEN, TEXT_GRAU as GRAU  # noqa: E402
OHNE_KATEGORIE = "ohne Kategorie"
EK_FEHLT = "EK fehlt"
QUELLE_TEXT = {zukauf.KATEGORIE: "Standard der Kategorie", zukauf.INDIVIDUELL: "individuell für diesen Artikel",
               zukauf.STANDARD: "Standard der Anwendung (Einstellungen)"}


def euro(w, stellen=2):
    return f"{zahl_als_text(zukauf.runden(w, stellen), stellen)} €" if w is not None else ""


def euro_einheit(w):
    """Einheitspreis mit bis zu 4 Nachkommastellen, mindestens 2 (0,12 € / 0,0835 €)."""
    if w is None:
        return ""
    r = zukauf.runden(w, zukauf.STELLEN_EINHEIT)
    stellen = next(n for n in range(2, zukauf.STELLEN_EINHEIT + 1) if round(r, n) == r or n == zukauf.STELLEN_EINHEIT)
    return f"{zahl_als_text(round(r, stellen), stellen)} €"


def prozent(w):
    return f"{zahl_als_text(zukauf.runden(w, 2), None)} %" if w is not None else ""


def menge_text(w, einheit=""):
    if w is None:
        return ""
    return f"{zahl_als_text(zukauf.runden(w, 3), None)} {zukauf.EINHEIT_KURZ.get(einheit, einheit)}".strip()


def archiviert(a):
    return a.get("status") == "archiviert"


def _zahl_oder_none(text, titel, fehler, schluessel, groesser_null=False, bis=None):
    t = (text or "").strip()
    if not t:
        return None
    try:
        w = zahl_aus_text(t)
    except ValueError:
        fehler[schluessel] = f"{titel}: '{t}' ist keine Zahl."
        return None
    if w < 0 or (groesser_null and w == 0):
        fehler[schluessel] = f"{titel}: {'muss größer als 0 sein' if groesser_null else 'negative Werte sind nicht zulässig'}."
        return None
    if bis is not None and w >= bis:
        fehler[schluessel] = f"{titel}: muss unter {zahl_als_text(bis)} liegen."
        return None
    return w


def kopie_nummer(nr, vorhanden):
    """Artikelnummer der Kopie: 'Z-1001-K', bei Bedarf 'Z-1001-K2' … ; leer bleibt leer."""
    if not nr:
        return None
    vorhanden = {v.lower() for v in vorhanden if v}
    kandidat, i = f"{nr}-K", 2
    while kandidat.lower() in vorhanden:
        kandidat, i = f"{nr}-K{i}", i + 1
    return kandidat


class Staffeltabelle(QTableWidget):
    """Zwei Spalten 'ab Menge' und Wert (Preis bzw. Aufschlag); leere Zeilen zählen nicht."""
    geaendert = Signal()

    def __init__(self, wert_titel, parent=None, preis=True):
        super().__init__(0, 2, parent)
        self.preis = preis
        self.setHorizontalHeaderLabels(["ab Menge", wert_titel])
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setMaximumHeight(130)
        self.setMinimumHeight(80)
        self.itemChanged.connect(lambda *_: self.geaendert.emit())

    def setzen(self, staffel, wert="preis"):
        self.blockSignals(True)
        self.setRowCount(0)
        for e in zukauf.json_liste(staffel):
            self._zeile(e.get("ab"), e.get(wert))
        self._zeile(None, None)
        self.blockSignals(False)

    def _zeile(self, ab, w):
        r = self.rowCount()
        self.insertRow(r)
        for c, v in enumerate((ab, w)):
            stellen = 2 if c and self.preis and isinstance(v, (int, float)) and round(v, 2) == v else None
            it = QTableWidgetItem(zahl_als_text(v, stellen, tausender=False) if isinstance(v, (int, float)) else "")
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.setItem(r, c, it)

    def lesen(self, wert="preis"):
        """[{ab, wert}] und Meldung bei ungültiger Eingabe ('' wenn alles gültig). Fügt bei Bedarf eine leere
        Zeile am Ende an."""
        out, fehler = [], ""
        for r in range(self.rowCount()):
            texte = [(self.item(r, c).text() if self.item(r, c) else "").strip() for c in range(2)]
            if not any(texte):
                continue
            try:
                ab = zahl_aus_text(texte[0]) if texte[0] else 0
                w = zahl_aus_text(texte[1]) if texte[1] else None
            except ValueError:
                fehler = fehler or f"Staffel Zeile {r + 1}: keine Zahl."
                continue
            out.append({"ab": ab, wert: w})
        letzte = self.rowCount() - 1
        if letzte < 0 or any((self.item(letzte, c).text() if self.item(letzte, c) else "").strip() for c in range(2)):
            self.blockSignals(True)
            self._zeile(None, None)
            self.blockSignals(False)
        return out, fehler


# ------------------------------------------------------------------ Formular
class ZukaufFormular(QWidget):
    """Formular für Anlegen, Bearbeiten und Duplizieren. laden() füllt es; Speichern schreibt erst dann in die
    Datenbank (gespeichert(ID)), Abbrechen verwirft alles (abgebrochen)."""
    gespeichert = Signal(int)
    abgebrochen = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.zeilen_id = None
        self.geaendert = False
        self._laedt = False
        self.bezuege = []          # Einkaufsbedingungen je Lieferant (dicts), self.b_nr = angezeigter Eintrag
        self.b_nr = -1
        self.kategorien = {}
        self.standard = None
        self.vorschau_daten = None

        self.titel = QLabel()
        self.titel.setObjectName("kartentitel")
        # A Stammdaten
        self.artikelnr = QLineEdit()
        self.artikelnr.setPlaceholderText("eindeutig, darf leer bleiben")
        self.bezeichnung = QLineEdit()
        self.bezeichnung.setPlaceholderText("z. B. Sechskantschraube M6x20 8.8 verzinkt")
        self.kategorie = QComboBox()
        self.kategorie.setEditable(True)
        self.einheit = QComboBox()
        self.einheit.setEditable(True)
        self.einheit.addItems(list(zukauf.EINHEITEN))
        self.archiv = QCheckBox("archiviert (im Angebot nicht mehr wählbar)")
        self.beschreibung = QLineEdit()
        self.ean = QLineEdit()
        self.bemerkung = QLineEdit()
        self.angebotstext = QCheckBox("im Angebotstext der Position nennen")
        self.rest_lager = QCheckBox("Mehrmenge geht ins Lager (nur Verbrauch berechnen)")
        # Blechteile: Maße und Werkstoff (vom STEP-Import vorbelegt); Herkunft, STEP-Datei und Kennung nur zur Ansicht
        self.artikeltyp = QComboBox()
        self.artikeltyp.addItem("normaler Zukaufartikel", "")
        for t in zukauf.ZUKAUF_TYPEN:
            self.artikeltyp.addItem(t, t)
        self.b_laenge, self.b_breite, self.b_dicke = self._zahl("Länge"), self._zahl("Breite"), self._zahl("Dicke")
        self.werkstoff = QComboBox()
        self.werkstoff.setEditable(True)
        self.werkstoff.lineEdit().setPlaceholderText("offen (wird nie angenommen)")
        self.blech_info = QLabel()
        self.blech_info.setWordWrap(True)
        self.blech_info.setStyleSheet(f"color: {GRAU};")
        self._blech_extra = {}
        # B Einkauf
        self.lieferanten = QListWidget()
        self.lieferanten.setMaximumHeight(62)
        self.k_lief_neu = QPushButton("+ Lieferant")
        self.k_lief_weg = QPushButton("Entfernen")
        self.k_lief_bev = QPushButton("Als bevorzugt")
        self.lieferant = QComboBox()
        self.lieferant.setEditable(True)
        self.lieferant.lineEdit().setPlaceholderText("Lieferant wählen oder neu eingeben")
        self.lieferanten_artnr = QLineEdit()
        self.preiseinheit = self._zahl("1")
        self.preiseinheit_text = QLabel()
        self.preise = Staffeltabelle("Einkaufspreis netto [€]")
        self.verpackung = self._zahl("0,00")
        self.fracht = self._zahl("0,00")
        self.fracht_einheit = self._zahl("0,00")
        self.weitere = self._zahl("0,00")
        self.mindestmenge = self._zahl("")
        self.vpe = self._zahl("")
        self.lieferzeit = self._zahl("")
        self.mindermenge = self._zahl("0,00")
        self.mindermenge_bis = self._zahl("")
        self.rabatt = self._zahl("0")
        self.gueltig_von = self._zahl("TT.MM.JJJJ")
        self.gueltig_bis = self._zahl("TT.MM.JJJJ")
        # C Aufschlag
        self.quelle = QComboBox()
        for q in zukauf.QUELLEN:
            self.quelle.addItem(QUELLE_TEXT[q], q)
        self.quelle_info = QLabel()
        self.quelle_info.setWordWrap(True)
        self.quelle_info.setStyleSheet(f"color: {GRAU};")
        self.methode = QComboBox()
        for m in zukauf.METHODEN:
            self.methode.addItem(m, m)
        self.wert = self._zahl("0")
        self.wert_einheit = QLabel("%")
        self.auf_staffel = Staffeltabelle("Aufschlag [%]", preis=False)
        self.kombiniert = QCheckBox("zusätzlich zum Kategorieaufschlag (beide Aufschläge addieren)")
        self.methode_info = QLabel()
        self.methode_info.setWordWrap(True)
        self.methode_info.setStyleSheet(f"color: {GRAU};")
        # Vorschau
        self.verbrauch = self._zahl("1")
        self.verbrauch.setText("1")
        self.verbrauch_einheit = QLabel()
        self.ergebnis = QWidget()
        self.ergebnis_gitter = QGridLayout(self.ergebnis)
        self.ergebnis_gitter.setContentsMargins(0, 0, 0, 0)
        self.ergebnis_gitter.setColumnStretch(0, 1)
        self.ergebnis_zeilen = []
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet(f"color: {GRAU};")
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
        self.abschnitte = {}        # Titel -> (Knopf, Inhalt, Kurzfassung); auf-/zugeklappt gemerkt (ZU_EINSTELLUNG)
        fa = self._bereich(lay, "A  Stammdaten", klappbar=True)
        fa.addRow("Artikelnummer", self.artikelnr)
        fa.addRow("Artikelbezeichnung *", self.bezeichnung)
        fa.addRow("Kategorie", self.kategorie)
        fa.addRow("Mengeneinheit", self.einheit)
        fa.addRow("Artikeltyp", self.artikeltyp)
        self.zeile_masse = self._zeile(self.b_laenge, QLabel("×"), self.b_breite, QLabel("×"), self.b_dicke,
                                       QLabel("mm"))
        fa.addRow("Blech L × B × D", self.zeile_masse)
        fa.addRow("Werkstoff", self.werkstoff)
        fa.addRow("", self.blech_info)
        fa.addRow("", self.archiv)
        self.fa = fa
        fb = self._bereich(lay, "B  Einkaufspreis", klappbar=True)
        fb.addRow("Lieferanten", self.lieferanten)
        fb.addRow("", self._zeile(self.k_lief_neu, self.k_lief_weg, self.k_lief_bev))
        fb.addRow("Lieferant", self.lieferant)
        fb.addRow("Preis gilt für", self._zeile(self.preiseinheit, self.preiseinheit_text))
        fb.addRow("Einkaufspreise", self.preise)
        fb.addRow("Verpackung je Bestellung", self._zeile(self.verpackung, QLabel("€")))
        fb.addRow("Eingangsfracht", self._zeile(self.fracht, QLabel("€ je Bestellung +"), self.fracht_einheit,
                                                QLabel("€ je Einheit")))
        fb.addRow("Weitere Bezugskosten", self._zeile(self.weitere, QLabel("€ je Bestellung")))
        fc = self._bereich(lay, "C  Aufschlag", klappbar=True)
        fc.addRow("Aufschlag aus", self.quelle)
        fc.addRow("", self.quelle_info)
        self.zeile_methode = self._zeile(self.methode)
        fc.addRow("Methode", self.zeile_methode)
        self.zeile_wert = self._zeile(self.wert, self.wert_einheit)
        fc.addRow("Aufschlag", self.zeile_wert)
        fc.addRow("Staffel", self.auf_staffel)
        fc.addRow("", self.kombiniert)
        fc.addRow("", self.methode_info)
        self.fc = fc
        self.mehr = QToolButton()
        self.mehr.setObjectName("aufklapper")
        self.mehr.setCheckable(True)
        self.mehr.toggled.connect(self._mehr_zeigen)
        lay.addWidget(self.mehr)
        self.box_mehr = QWidget()
        fm = self._bereich(lay, "Weitere Details", self.box_mehr)
        fm.addRow("Beschreibung", self.beschreibung)
        fm.addRow("EAN / Referenzcode", self.ean)
        fm.addRow("Lieferantenartikelnummer", self.lieferanten_artnr)
        fm.addRow("Mindestbestellmenge", self.mindestmenge)
        fm.addRow("Verpackungseinheit", self.vpe)
        fm.addRow("Lieferzeit", self._zeile(self.lieferzeit, QLabel("Tage")))
        fm.addRow("Mindermengenzuschlag", self._zeile(self.mindermenge, QLabel("€ bei Bestellmenge unter"),
                                                      self.mindermenge_bis))
        fm.addRow("Mengenrabatt", self._zeile(self.rabatt, QLabel("%")))
        fm.addRow("Preis gültig", self._zeile(QLabel("von"), self.gueltig_von, QLabel("bis"), self.gueltig_bis))
        fm.addRow("", self.rest_lager)
        fm.addRow("", self.angebotstext)
        fm.addRow("Bemerkung", self.bemerkung)
        fv = self._bereich(lay, "Preisvorschau", klappbar=True)
        fv.addRow("Verbrauch", self._zeile(self.verbrauch, self.verbrauch_einheit))
        fv.addRow(self.ergebnis)
        fv.addRow(self.hinweis)
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
        self.setMinimumWidth(460)

        for w in (self.artikelnr, self.bezeichnung, self.beschreibung, self.ean, self.bemerkung, self.wert,
                  self.verbrauch, self.b_laenge, self.b_breite, self.b_dicke):
            w.textEdited.connect(self._geaendert)
        for w in self._bezug_eingaben():
            w.textEdited.connect(self._bezug_geaendert)
        self.lieferant.editTextChanged.connect(self._bezug_geaendert)
        self.preise.geaendert.connect(self._bezug_geaendert)
        self.auf_staffel.geaendert.connect(self._geaendert)
        for w in (self.kategorie, self.einheit, self.werkstoff):
            w.editTextChanged.connect(self._geaendert)
        for w in (self.quelle, self.methode, self.artikeltyp):
            w.currentIndexChanged.connect(self._geaendert)
        for w in (self.archiv, self.angebotstext, self.rest_lager, self.kombiniert):
            w.toggled.connect(self._geaendert)
        self.lieferanten.currentRowChanged.connect(self._bezug_zeigen)
        self.k_lief_neu.clicked.connect(self.lieferant_neu)
        self.k_lief_weg.clicked.connect(self.lieferant_entfernen)
        self.k_lief_bev.clicked.connect(self.lieferant_bevorzugt)
        self._mehr_zeigen(False)
        for w in (self.quelle, self.methode):
            w.currentIndexChanged.connect(self._kurz_aktualisieren)
        self.wert.textChanged.connect(self._kurz_aktualisieren)
        self.bezeichnung.textChanged.connect(self._kurz_aktualisieren)
        self.kategorie.editTextChanged.connect(self._kurz_aktualisieren)
        self.lieferant.editTextChanged.connect(self._kurz_aktualisieren)
        zu = self.db.einstellung(self.ZU_EINSTELLUNG)
        for titel in self.abschnitte:
            self.abschnitt_aufklappen(titel, titel not in (self.ZU_VORGABE if zu is None else zu))
        self._kurz_aktualisieren()

    # -------------------------------------------------------------- Aufbau
    ZU_EINSTELLUNG = "ansicht_zukauf_zu"        # Liste der zugeklappten Abschnitte des Formulars (alle Artikel)
    ZU_VORGABE = ("C  Aufschlag",)

    def abschnitt_aufklappen(self, titel, offen, merken=False):
        knopf, inhalt, kurz = self.abschnitte[titel]
        inhalt.setVisible(offen)
        kurz.setVisible(not offen)
        knopf.blockSignals(True)
        knopf.setChecked(offen)
        knopf.blockSignals(False)
        knopf.setText(("▾ " if offen else "▸ ") + titel)
        if merken:
            zu = self.db.einstellung(self.ZU_EINSTELLUNG)
            zu = set(self.ZU_VORGABE if zu is None else zu)
            (zu.discard if offen else zu.add)(titel)
            self.db.einstellung_setzen(self.ZU_EINSTELLUNG, sorted(zu))

    def abschnitt_offen(self, titel):
        return self.abschnitte[titel][1].isVisibleTo(self)

    def _kurz_aktualisieren(self, *_):
        """Kurzfassung zugeklappter Abschnitte (eine Zeile neben dem Titel)."""
        if not getattr(self, "abschnitte", None):
            return
        teile = {"A  Stammdaten": [self.bezeichnung.text().strip() or "ohne Bezeichnung", self.kategorie.currentText()],
                 "B  Einkaufspreis": [self.lieferant.currentText().strip() or "kein Lieferant"],
                 "C  Aufschlag": [self.quelle.currentText()],
                 "Preisvorschau": ["aufklappen für Einstand und Verkaufspreis"]}
        if self.quelle.currentData() == "artikel":
            teile["C  Aufschlag"].append(f"{self.methode.currentText()} {self.wert.text()} {self.wert_einheit.text()}")
        for titel, (_, _, kurz) in self.abschnitte.items():
            kurz.setText(" · ".join(t for t in teile.get(titel, []) if t and t.strip()))
    def _zahl(self, platzhalter):
        e = QLineEdit()
        e.setPlaceholderText(platzhalter)
        e.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        e.setMaximumWidth(100)
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

    def _bereich(self, lay, titel, behaelter=None, klappbar=False):
        """Abschnitt mit Überschrift; klappbar: Überschrift ist ein Knopf, zugeklappt steht daneben eine
        Kurzfassung."""
        behaelter = behaelter or QWidget()
        v = QVBoxLayout(behaelter)
        v.setContentsMargins(0, 6, 0, 0)
        f = QFormLayout()
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        if not klappbar:
            t = QLabel(titel)
            t.setObjectName("gruppentitel")
            v.addWidget(t)
            v.addLayout(f)
        else:
            kopf = QHBoxLayout()
            knopf = QToolButton()
            knopf.setObjectName("kartenknopf")
            knopf.setCheckable(True)
            knopf.setToolButtonStyle(Qt.ToolButtonTextOnly)
            knopf.toggled.connect(lambda offen, t=titel: self.abschnitt_aufklappen(t, offen, merken=True))
            kurz = QLabel()
            kurz.setStyleSheet(f"color: {GRAU};")
            kurz.setMinimumWidth(1)
            kopf.addWidget(knopf, 0, Qt.AlignLeft)
            kopf.addWidget(kurz, 1)
            kopf.addStretch(0)
            v.addLayout(kopf)
            inhalt = QWidget()
            inhalt.setLayout(f)
            f.setContentsMargins(0, 0, 0, 0)
            v.addWidget(inhalt)
            self.abschnitte[titel] = (knopf, inhalt, kurz)
        lay.addWidget(behaelter)
        return f

    def _mehr_zeigen(self, offen):
        self.box_mehr.setVisible(offen)
        self.mehr.setText(("▾ " if offen else "▸ ") + "Weitere Details")
        self.mehr.setToolTip("Beschreibung, EAN, Lieferantenartikelnummer, Mindestmenge, Verpackungseinheit, "
                             "Lieferzeit, Mindermengenzuschlag, Rabatt, Gültigkeit, Lager, Angebotstext")

    # Felder je Lieferant (Name in zukauf.BEZUG -> Eingabe)
    BEZUG_ZAHLEN = ("preiseinheit", "verpackung", "fracht", "fracht_einheit", "weitere", "mindestmenge", "vpe",
                    "lieferzeit", "mindermenge", "mindermenge_bis", "rabatt")

    def _bezug_eingaben(self):
        return [getattr(self, n) for n in self.BEZUG_ZAHLEN + ("gueltig_von", "gueltig_bis")] + [self.lieferanten_artnr]

    # -------------------------------------------------------------- Laden
    def laden(self, a=None, zeilen_id=None, titel="Neuer Zukaufartikel"):
        """Formular füllen: a = Artikel mit 'bezuege' (None = neu), zeilen_id = None legt beim Speichern neu an
        (Neu, Duplizieren)."""
        a = dict(a or {})
        self._laedt = True
        self.zeilen_id = zeilen_id
        self.titel.setText(titel)
        self.kategorien = self.db.zukauf_kategorien()
        self.standard = self.db.einstellung("zukauf_aufschlag")
        self.kategorie.clear()
        self.kategorie.addItems([""] + [n for n, k in self.kategorien.items() if k.get("aktiv") != "nein"])
        self.kategorie.setCurrentText(a.get("kategorie") or "")
        self.lieferant.clear()
        self.lieferant.addItems([""] + sorted(z["name"] for z in self.db.zeilen("zukauf_lieferanten") if z.get("name")))
        for n in ("artikelnr", "bezeichnung", "beschreibung", "ean", "bemerkung"):
            getattr(self, n).setText(a.get(n) or "")
        self.einheit.setCurrentText(a.get("einheit") or "Stück")
        self.artikeltyp.setCurrentIndex(max(self.artikeltyp.findData(a.get("artikeltyp") or ""), 0))
        for n, w in (("laenge", self.b_laenge), ("breite", self.b_breite), ("dicke", self.b_dicke)):
            x = a.get(n)
            w.setText(zahl_als_text(x, None, tausender=False) if isinstance(x, (int, float)) else "")
        self.werkstoff.clear()
        self.werkstoff.addItems([""] + sorted(z["werkstoff_id"] for z in self.db.zeilen("werkstoffe")
                                              if z.get("werkstoff_id")))
        self.werkstoff.setCurrentText(a.get("werkstoff") or "")
        self._blech_extra = {n: a.get(n) for n in ("herkunft", "step_datei", "fingerabdruck")}
        info = [f"angelegt aus {a['herkunft']}" if a.get("herkunft") else "",
                f"STEP-Datei {a['step_datei']}" if a.get("step_datei") else ""]
        self.blech_info.setText(" · ".join(x for x in info if x))
        self.archiv.setChecked(archiviert(a))
        self.angebotstext.setChecked(a.get("angebotstext") == "ja")
        self.rest_lager.setChecked(a.get("rest_lager") == "ja")
        self.quelle.setCurrentIndex(max(self.quelle.findData(a.get("aufschlag_quelle") or zukauf.KATEGORIE), 0))
        self.methode.setCurrentIndex(max(self.methode.findData(a.get("aufschlag_methode") or zukauf.PROZENT), 0))
        w = a.get("aufschlag_wert")
        self.wert.setText(zahl_als_text(w, None, tausender=False) if isinstance(w, (int, float)) else "")
        self.auf_staffel.setzen(a.get("aufschlag_staffel"), "wert")
        self.kombiniert.setChecked(a.get("kombiniert") == "ja")
        self.bezuege = [dict(b, preise=zukauf.json_liste(b.get("preise"))) for b in a.get("bezuege") or ()]
        if not self.bezuege:
            self.bezuege = [dict(preiseinheit=1, bevorzugt="ja", preise=[])]
        self.b_nr = -1
        b0 = zukauf.bezug_waehlen(self.bezuege) or {}
        self.verbrauch.setText(zahl_als_text(float(zukauf.bestellmenge(1, b0.get("mindestmenge"), b0.get("vpe"))),
                                             None, tausender=False))
        self._liste_fuellen(self.bezuege.index(b0) if b0 in self.bezuege else 0)
        mehr = bool(a.get("beschreibung") or a.get("ean") or a.get("bemerkung") or a.get("angebotstext") == "ja"
                    or a.get("rest_lager") == "ja"
                    or any(b.get(n) not in (None, "", 0) for b in self.bezuege
                           for n in ("lieferanten_artnr", "mindestmenge", "vpe", "lieferzeit", "mindermenge", "rabatt",
                                     "gueltig_von", "gueltig_bis")))
        self.mehr.setChecked(mehr)
        self._mehr_zeigen(mehr)
        self._laedt = False
        self.geaendert = False
        self.aktualisieren()
        self.bezeichnung.setFocus()

    def _liste_fuellen(self, auswahl):
        self.lieferanten.blockSignals(True)
        self.lieferanten.clear()
        for b in self.bezuege:
            it = QListWidgetItem(("★ " if b.get("bevorzugt") == "ja" else "   ") + (b.get("lieferant") or "(Lieferant fehlt)"))
            self.lieferanten.addItem(it)
        self.lieferanten.blockSignals(False)
        self.lieferanten.setCurrentRow(auswahl)
        self._bezug_zeigen(auswahl)

    def _bezug_zeigen(self, nr):
        if nr < 0 or nr >= len(self.bezuege):
            return
        if self.b_nr != nr and 0 <= self.b_nr < len(self.bezuege) and not self._laedt:
            self._bezug_lesen()           # Eingaben des bisher angezeigten Lieferanten behalten
        self.b_nr = nr
        b = self.bezuege[nr]
        alt, self._laedt = self._laedt, True
        self.lieferant.setCurrentText(b.get("lieferant") or "")
        self.lieferanten_artnr.setText(b.get("lieferanten_artnr") or "")
        for n in self.BEZUG_ZAHLEN:
            w = b.get(n)
            getattr(self, n).setText(zahl_als_text(w, None, tausender=False) if isinstance(w, (int, float)) else "")
        for n in ("gueltig_von", "gueltig_bis"):
            getattr(self, n).setText(wert_als_text(Feld(n, n, "datum"), b.get(n)) if b.get(n) else "")
        self.preise.setzen(b.get("preise"), "preis")
        self._laedt = alt
        self.k_lief_weg.setEnabled(len(self.bezuege) > 1)
        self.k_lief_bev.setEnabled(b.get("bevorzugt") != "ja")
        if not self._laedt:
            self.aktualisieren()

    def lieferant_neu(self):
        self._bezug_lesen()
        self.bezuege.append(dict(preiseinheit=self.bezuege[self.b_nr].get("preiseinheit") or 1, preise=[]))
        self._liste_fuellen(len(self.bezuege) - 1)
        self._geaendert()
        self.lieferant.setFocus()

    def lieferant_entfernen(self):
        if len(self.bezuege) <= 1:
            return
        weg = self.bezuege.pop(self.b_nr)
        if weg.get("bevorzugt") == "ja":
            self.bezuege[0]["bevorzugt"] = "ja"
        self.b_nr = -1
        self._liste_fuellen(0)
        self._geaendert()

    def lieferant_bevorzugt(self):
        self._bezug_lesen()
        for i, b in enumerate(self.bezuege):
            b["bevorzugt"] = "ja" if i == self.b_nr else "nein"
        self._liste_fuellen(self.b_nr)
        self._geaendert()

    def _geaendert(self, *_):
        if self._laedt:
            return
        self.geaendert = True
        self.aktualisieren()

    def _bezug_geaendert(self, *_):
        if self._laedt:
            return
        self._bezug_lesen()
        it = self.lieferanten.item(self.b_nr)
        if it is not None:
            b = self.bezuege[self.b_nr]
            it.setText(("★ " if b.get("bevorzugt") == "ja" else "   ") + (b.get("lieferant") or "(Lieferant fehlt)"))
        self._geaendert()

    # -------------------------------------------------------------- Werte und Vorschau
    def _bezug_lesen(self):
        """Eingaben des angezeigten Lieferanten in self.bezuege übernehmen; Ergebnis {Feld: Meldung}."""
        fehler = {}
        if not 0 <= self.b_nr < len(self.bezuege):
            return fehler
        b = self.bezuege[self.b_nr]
        b["lieferant"] = self.lieferant.currentText().strip() or None
        b["lieferanten_artnr"] = self.lieferanten_artnr.text().strip() or None
        titel = {f.name: f.titel for f in zukauf.BEZUG.felder}
        for n in self.BEZUG_ZAHLEN:
            b[n] = _zahl_oder_none(getattr(self, n).text(), titel[n], fehler, n, groesser_null=n == "preiseinheit",
                                   bis=100 if n == "rabatt" else None)
            if n == "lieferzeit" and b[n] is not None:
                b[n] = int(b[n])
        for n in ("gueltig_von", "gueltig_bis"):
            try:
                b[n] = wert_aus_text(Feld(n, titel[n], "datum"), getattr(self, n).text())
            except ValueError as e:
                fehler[n] = str(e)
                b[n] = None
        preise, f = self.preise.lesen("preis")
        if f:
            fehler["preise"] = f
        b["preise"] = preise
        return fehler

    def _felder(self):
        """({Feld: Wert} des Artikels, {Feld: Meldung})."""
        fehler = self._bezug_lesen()
        werte = dict(artikelnr=self.artikelnr.text().strip() or None,
                     bezeichnung=self.bezeichnung.text().strip() or None,
                     kategorie=self.kategorie.currentText().strip() or None,
                     einheit=self.einheit.currentText().strip() or "Stück",
                     status="archiviert" if self.archiv.isChecked() else "aktiv",
                     beschreibung=self.beschreibung.text().strip() or None, ean=self.ean.text().strip() or None,
                     bemerkung=self.bemerkung.text().strip() or None,
                     angebotstext="ja" if self.angebotstext.isChecked() else "nein",
                     rest_lager="ja" if self.rest_lager.isChecked() else "nein",
                     aufschlag_quelle=self.quelle.currentData(), aufschlag_methode=None, aufschlag_wert=None,
                     aufschlag_staffel=None, kombiniert="nein", artikeltyp=self.artikeltyp.currentData() or None,
                     werkstoff=self.werkstoff.currentText().strip() or None, **self._blech_extra)
        for n, w in (("laenge", self.b_laenge), ("breite", self.b_breite), ("dicke", self.b_dicke)):
            werte[n] = _zahl_oder_none(w.text(), zukauf.ARTIKEL.feld(n).titel, fehler, n, groesser_null=True) \
                if werte["artikeltyp"] else None
        if werte["aufschlag_quelle"] == zukauf.INDIVIDUELL:
            m = self.methode.currentData()
            werte["aufschlag_methode"] = m
            if m == zukauf.STAFFEL:
                st, f = self.auf_staffel.lesen("wert")
                if f:
                    fehler["auf_staffel"] = f
                werte["aufschlag_staffel"] = json.dumps(st) if st else None
            else:
                werte["aufschlag_wert"] = _zahl_oder_none(self.wert.text(), "Aufschlag", fehler, "wert",
                                                          bis=100 if m == zukauf.MARGE else None)
            werte["kombiniert"] = "ja" if self.kombiniert.isChecked() else "nein"
        return werte, fehler

    def aktualisieren(self):
        """Sichtbarkeit, rote Felder und Preisvorschau nach jeder Eingabe."""
        werte, fehler = self._felder()
        einheit = werte["einheit"]
        kurz = zukauf.EINHEIT_KURZ.get(einheit, einheit)
        self.preiseinheit_text.setText(f"{kurz} (z. B. 100 bei Preis je 100 {kurz})")
        self.verbrauch_einheit.setText(f"{kurz} (Menge für die Vorschau, z. B. Bedarf eines Auftrags)")
        individuell = werte["aufschlag_quelle"] == zukauf.INDIVIDUELL
        m = self.methode.currentData()
        self.fc.setRowVisible(self.zeile_methode, individuell)
        self.fc.setRowVisible(self.zeile_wert, individuell and m != zukauf.STAFFEL)
        self.fc.setRowVisible(self.auf_staffel, individuell and m == zukauf.STAFFEL)
        self.fc.setRowVisible(self.kombiniert, individuell)
        blech = werte["artikeltyp"] == zukauf.BLECH
        for w in (self.zeile_masse, self.werkstoff, self.blech_info):
            self.fa.setRowVisible(w, blech)
        self.wert_einheit.setText("€" if m in (zukauf.JE_EINHEIT, zukauf.JE_BESTELLUNG) else "%")
        kat = self.kategorien.get(werte["kategorie"]) or {}
        r_kat = zukauf.aufschlagsregeln(dict(kategorie=werte["kategorie"]), self.kategorien, None)
        std = f"{zahl_als_text(self.standard, None)} % auf Einstand" if self.standard is not None else "keiner hinterlegt"
        if werte["aufschlag_quelle"] == zukauf.KATEGORIE:
            info = (f"Kategorie {kat.get('name')}: {zukauf.regel_text(r_kat[0]).split(' (')[0]}" if r_kat
                    else f"Die Kategorie hat keinen Aufschlag; es gilt der Standard der Anwendung ({std}).")
        elif werte["aufschlag_quelle"] == zukauf.STANDARD:
            info = f"Standard der Anwendung: {std}."
        else:
            info = ("Ersetzt den Kategorieaufschlag" + (f" ({zukauf.regel_text(r_kat[0]).split(' (')[0]})" if r_kat else "")
                    + ". Spätere Änderungen an der Kategorie ändern diesen Artikel nicht.")
        self.quelle_info.setText(info)
        self.methode_info.setText(zukauf.METHODE_TEXT.get(m, "") + (
            ". Achtung: Aufschlag ist nicht Marge (20 % Aufschlag auf 10,00 € = 12,00 €, 20 % Marge = 12,50 €)."
            if m in (zukauf.PROZENT, zukauf.MARGE, zukauf.STAFFEL) else "") if individuell else "")
        for n, w in (("wert", self.wert), ("preise", self.preise), ("auf_staffel", self.auf_staffel),
                     ("laenge", self.b_laenge), ("breite", self.b_breite), ("dicke", self.b_dicke)) + tuple(
                (n, getattr(self, n)) for n in self.BEZUG_ZAHLEN + ("gueltig_von", "gueltig_bis")):
            w.setStyleSheet(ROTER_RAHMEN if n in fehler else "")
        verbrauch = _zahl_oder_none(self.verbrauch.text(), "Verbrauch", fehler, "verbrauch", groesser_null=True) or 1
        self.verbrauch.setStyleSheet(ROTER_RAHMEN if "verbrauch" in fehler else "")
        b = self.bezuege[self.b_nr] if 0 <= self.b_nr < len(self.bezuege) else None
        meldungen = list(fehler.values())
        try:
            v = zukauf.vorschau(dict(werte, id=self.zeilen_id), b, self.kategorien, self.standard, verbrauch)
        except ValueError as e:
            v = None
            meldungen.append(str(e))
        self.vorschau_daten = v
        self._ergebnis_zeigen(v, einheit, verbrauch)
        if not werte["bezeichnung"] and self.geaendert:
            meldungen.append("Bitte eine Artikelbezeichnung eingeben.")
        self.fehler.setText("\n".join(meldungen))
        return werte, fehler

    def _ergebnis_zeigen(self, v, einheit, verbrauch):
        """Tabelle der Preisvorschau: je Einheit und für den Verbrauch."""
        zeilen = []
        if v is not None and not v["fehler"]:
            bs, je = v["bestellung"], v["je_einheit"]
            kurz = zukauf.EINHEIT_KURZ.get(einheit, einheit)
            st = bs["staffel"]
            ek_text = "Einkaufspreis netto" + (f" (Staffel ab {zahl_als_text(float(st['ab']), None)})" if st else "")
            if bs["mehrmenge"] > 0:
                ek_text += (f", bestellt {menge_text(bs['bestellt'], einheit)}"
                            + (", Mehrmenge ins Lager" if self.rest_lager.isChecked() else ""))
            zeilen.append(("Position", f"je {kurz}", f"für {zahl_als_text(verbrauch, None)} {kurz}", True))
            zeilen.append((ek_text, euro_einheit(bs["ek"]), euro(bs["einkauf"]), False))
            if bs["bezug"]:
                teile = ", ".join(f"{n} {euro(b)}" for n, b in bs["bezug_einzeln"].items() if b)
                zeilen.append((f"Bezugskostenanteil ({teile})", euro_einheit(je["bezug"]), euro(bs["bezug"]), False))
            zeilen.append(("Einstandspreis", euro_einheit(je["einstand"]), euro(v["einstand"]), True))
            zeilen.append((v["regel"], euro_einheit(je["aufschlag"]), euro(v["aufschlag"]), False))
            zeilen.append(("Verkaufspreis netto", euro_einheit(je["vk"]), euro(v["vk"]), True))
            mwst = self.db.einstellung("mwst")
            if isinstance(mwst, (int, float)) and mwst:
                f = zukauf.dez(mwst)
                zeilen.append((f"MwSt. {zahl_als_text(mwst * 100, None)} %", euro_einheit(je["vk"] * f),
                               euro(v["vk"] * f), False))
                zeilen.append(("Bruttopreis", euro_einheit(je["vk"] * (1 + f)), euro(v["vk"] * (1 + f)), False))
            zeilen.append(("Deckungsbeitrag (Verkaufspreis − Einstand)", euro_einheit(je["aufschlag"]),
                           euro(v["aufschlag"]), False))
            if v["aufschlag_pct"] is not None:
                zeilen.append(("Aufschlag auf Einstand / Marge vom Verkaufspreis",
                               f"{prozent(v['aufschlag_pct'])} / {prozent(v['marge_pct'])}", "", False))
        self.ergebnis_zeilen = zeilen
        while self.ergebnis_gitter.count():
            alt = self.ergebnis_gitter.takeAt(0).widget()
            alt.hide()
            alt.deleteLater()
        for r, z in enumerate(zeilen):
            for c, text in enumerate(z[:3]):
                lab = QLabel(text)
                if z[3]:
                    lab.setStyleSheet("font-weight: bold;")
                if c:
                    lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    lab.setWordWrap(True)
                self.ergebnis_gitter.addWidget(lab, r, c)
        hinweise = []
        if v is not None:
            bs = v["bestellung"]
            if v["fehler"]:
                hinweise.append(f"<span style='color:{ROT}; font-weight:bold'>Kein Einkaufspreis: bitte unter "
                                "Einkaufspreise mindestens eine Zeile eintragen.</span>")
            if bs["mehrmenge"] > 0:
                hinweise.append(f"Bestellmenge {menge_text(bs['bestellt'], einheit)} statt Verbrauch "
                                f"{menge_text(bs['verbrauch'], einheit)} (Mindestbestellmenge bzw. Verpackungseinheit); "
                                + ("die Mehrmenge geht ins Lager und wird nicht berechnet." if self.rest_lager.isChecked()
                                   else "die ganze Bestellmenge wird berechnet."))
            for w in (v.get("warnung"),):
                if w:
                    hinweise.append(f"<span style='color:{GELB}'>{w}</span>")
        hinweise.append("Im Angebot kommt der Verkaufspreis nach dem Gewinn dazu (ohne Zuschlag Fertigung, "
                        "Fremdleistung und Gewinn des Angebots); Skonto wird eingerechnet. Der Preisstand wird beim "
                        "Hinzufügen in der Position gespeichert, spätere Änderungen hier ändern alte Angebote nicht.")
        self.hinweis.setText("<br>".join(hinweise))

    def werte(self):
        """(Artikel, Einkaufsbedingungen); ValueError mit verständlicher Meldung bei ungültiger Eingabe."""
        werte, fehler = self.aktualisieren()
        if fehler:
            raise ValueError(next(iter(fehler.values())))
        if not werte["bezeichnung"]:
            raise ValueError("Bitte eine Artikelbezeichnung eingeben.")
        if werte["aufschlag_quelle"] == zukauf.INDIVIDUELL and werte["aufschlag_methode"] != zukauf.STAFFEL \
                and werte["aufschlag_wert"] is None:
            raise ValueError("Bitte einen Aufschlag eingeben oder 'Standard der Kategorie' wählen.")
        return werte, [dict(b) for b in self.bezuege]

    # -------------------------------------------------------------- Knöpfe
    def speichern(self):
        try:
            werte, bezuege = self.werte()
            i = self.db.zukauf_speichern(self.zeilen_id, werte, bezuege)
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
SPALTEN = (("Artikelnr.", "artikelnr", True), ("Bezeichnung", "bezeichnung", True), ("Kategorie", "kategorie", True),
           ("Lieferant", "lieferant", True), ("Einheit", "einheit", True), ("EK je Einheit", "ek", True),
           ("Bezugskosten", "bezug", False), ("Aufschlag", "aufschlag", True), ("VK je Einheit", "vk", True),
           ("Status", "status", True))
SORTIERUNG = ("Kategorie", "Lieferant", "Artikelnummer", "Bezeichnung", "EK je Einheit")
WEGLASSEN = ("bezug", "einheit", "lieferant", "kategorie")


class ArtikelSeite(QWidget):
    """Unterreiter 'Artikel': Übersicht und Formular."""
    titel = "Artikel"
    KUERZEL = {"neu": "neu"}        # Tastenkürzel, siehe tastatur.py

    def __init__(self, db, meldung):
        super().__init__()
        self.db, self.meldung = db, meldung
        self.daten = []
        self.sichtbar = []
        self.dialog = None

        neu = QPushButton("+ Neuer Artikel")
        neu.setObjectName("primaer")
        neu.clicked.connect(self.neu)
        self.neu_knopf = neu
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen (Artikelnummer, Bezeichnung, Lieferantenartikelnummer, EAN) …")
        self.suche.setClearButtonEnabled(True)
        tastatur.suche_esc(self.suche)
        self.suche.textChanged.connect(self.anzeigen)
        self.kat_filter = QComboBox()
        self.lief_filter = QComboBox()
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Aktive", EK_FEHLT, "Archivierte", "Alle"])
        self.status_filter.setToolTip(f"{EK_FEHLT}: aktive Artikel ohne Einkaufspreis über 0 € (z. B. Bleche aus dem "
                                      "STEP-Import), Preis mit 'EK eintragen …' nachtragen")
        self.sortierung = QComboBox()
        self.sortierung.addItems(list(SORTIERUNG))
        for cb in (self.kat_filter, self.lief_filter, self.status_filter, self.sortierung):
            cb.currentIndexChanged.connect(self.anzeigen)
        self.anzahl = QLabel()
        self.anzahl.setStyleSheet(f"color: {GRAU};")
        leiste = QGridLayout()
        leiste.addWidget(neu, 0, 0)
        leiste.addWidget(self.suche, 0, 1, 1, 4)
        for i, (t, w) in enumerate((("Kategorie", self.kat_filter), ("Lieferant", self.lief_filter),
                                    ("Status", self.status_filter), ("Sortieren nach", self.sortierung))):
            box = QHBoxLayout()
            box.addWidget(QLabel(t))
            box.addWidget(w, 1)
            leiste.addLayout(box, 1, i + 1)
        leiste.addWidget(self.anzahl, 1, 0)
        for c in range(1, 5):
            leiste.setColumnStretch(c, 1)

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
        kopf.setSectionResizeMode(1, QHeaderView.Stretch)      # Bezeichnung nimmt den Rest (gekürzt mit …)
        kopf.setStretchLastSection(False)
        kopf.setMinimumSectionSize(40)
        kopf.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.tabelle.setTextElideMode(Qt.ElideRight)
        self.tabelle.itemSelectionChanged.connect(self._auswahl)
        self.tabelle.itemDoubleClicked.connect(lambda _: self.bearbeiten())
        self.tabelle.viewport().installEventFilter(self)
        self.tabelle.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabelle.customContextMenuRequested.connect(self._kontextmenue)

        self.k_bearbeiten = QPushButton("Bearbeiten")
        self.k_duplizieren = QPushButton("Duplizieren")
        self.k_archiv = QPushButton("Archivieren")
        self.k_ek = QPushButton("EK eintragen …")
        self.k_ek.setToolTip("Einkaufspreis je Einheit beim bevorzugten Lieferanten eintragen (z. B. für Bleche aus "
                             "dem STEP-Import, die noch keinen Preis haben)")
        self.k_angebot = QPushButton("In Angebot übernehmen …")
        self.k_angebot.setToolTip("Artikel mit aktuellem Preisstand als Zukaufteil in eine Position eines Angebots "
                                  "übernehmen")
        self.aktionen = QHBoxLayout()
        for k, f in ((self.k_bearbeiten, self.bearbeiten), (self.k_duplizieren, self.duplizieren),
                     (self.k_archiv, self.archiv_umschalten), (self.k_ek, self.ek_eintragen),
                     (self.k_angebot, self.in_angebot)):
            k.clicked.connect(lambda _=False, f=f: f())
            self.aktionen.addWidget(k)
        self.aktionen.addStretch(1)
        from .zukauf_preise import csv_exportieren, csv_importieren
        self.k_export = QPushButton("CSV exportieren")
        self.k_import = QPushButton("CSV importieren …")
        self.k_import.setToolTip("Artikel und Einkaufspreise aus einer CSV-Datei: zuerst Vorschau mit Prüfung, "
                                 "übernommen wird erst nach Bestätigung")
        self.k_export.clicked.connect(lambda: self.csv_export(csv_exportieren))
        self.k_import.clicked.connect(lambda: self.csv_import(csv_importieren))
        self.aktionen.addWidget(self.k_export)
        self.aktionen.addWidget(self.k_import)
        self.detail = QLabel()
        self.detail.setTextFormat(Qt.RichText)
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        detail_rahmen = QFrame()
        detail_rahmen.setObjectName("karte")
        QVBoxLayout(detail_rahmen).addWidget(self.detail)

        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.tabelle, 1)
        ll.addLayout(self.aktionen)
        ll.addWidget(detail_rahmen)
        self.formular = ZukaufFormular(db)
        self.formular.gespeichert.connect(self._gespeichert)
        self.formular.abgebrochen.connect(self._formular_zu)
        self.rechts = QFrame()
        self.rechts.setObjectName("karte")
        QVBoxLayout(self.rechts).addWidget(self.formular)
        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.addWidget(links)
        self.teiler.addWidget(self.rechts)
        self.teiler.setStretchFactor(0, 3)
        self.teiler.setStretchFactor(1, 2)
        self.teiler.setChildrenCollapsible(False)
        self.rechts.hide()

        hinweis = hilfe.Hinweis("Zukaufartikel mit Einkaufspreisen je Lieferant und eigener Aufschlagsregel. "
                                "Verkaufspreis = Einkaufspreis + Bezugskosten (Einstand) + Aufschlag. Die Spalten "
                                "zeigen den Preis für eine Einheit beim bevorzugten Lieferanten und der kleinsten "
                                "Bestellmenge, ohne Bezugskosten je Bestellung (eigene Spalte); Staffeln, Mengen und "
                                "Bezugskosten zusammen zeigt die Vorschau im Formular.",
                                schluessel="zukauf_artikel")
        lay = QVBoxLayout(self)
        lay.addWidget(hinweis)
        lay.addLayout(leiste)
        lay.addWidget(self.teiler, 1)
        self.neu_laden()

    # -------------------------------------------------------------- Daten
    def neu_laden(self):
        self.kategorien = self.db.zukauf_kategorien()
        self.standard = self.db.einstellung("zukauf_aufschlag")
        self.daten = self.db.zukauf_artikel_liste()
        for a in self.daten:
            b = zukauf.bezug_waehlen(a["bezuege"])
            a["_bezug"] = b or {}
            # Preise je Einheit bei der kleinsten Bestellmenge (1, Mindestmenge bzw. Verpackungseinheit)
            a["_menge"] = zukauf.bestellmenge(1, (b or {}).get("mindestmenge"), (b or {}).get("vpe"))
            # Bezugskosten je Bestellung hängen von der Bestellmenge ab: in der Übersicht eigene Spalte, nicht im
            # Preis je Einheit (die Vorschau im Formular rechnet sie für eine Menge mit ein)
            a["_je_bestellung"] = sum(zukauf._d((b or {}).get(n)) for n in ("verpackung", "fracht", "weitere"))
            ohne = dict(b, verpackung=None, fracht=None, weitere=None, mindermenge=None) if b else None
            try:
                a["_vorschau"] = zukauf.vorschau(a, ohne, self.kategorien, self.standard, a["_menge"])
            except ValueError:
                a["_vorschau"] = None
        for cb, werte in ((self.kat_filter, sorted({a.get("kategorie") or OHNE_KATEGORIE for a in self.daten},
                                                   key=lambda k: (k == OHNE_KATEGORIE, k.lower()))),
                          (self.lief_filter, sorted({b.get("lieferant") for a in self.daten for b in a["bezuege"]
                                                     if b.get("lieferant")}, key=str.lower))):
            alt = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(["Alle"] + list(werte))
            cb.setCurrentText(alt if alt in werte else "Alle")
            cb.blockSignals(False)
        self.anzeigen()

    def zeile(self, zeilen_id):
        return next((a for a in self.daten if a["id"] == zeilen_id), None)

    def gefiltert(self):
        such = self.suche.text().strip().lower()
        kat, lief, status = (cb.currentText() for cb in (self.kat_filter, self.lief_filter, self.status_filter))
        out = []
        for a in self.daten:
            texte = [a.get(n) for n in ("artikelnr", "bezeichnung", "beschreibung", "ean")] + \
                    [b.get("lieferanten_artnr") for b in a["bezuege"]]
            if such and not any(such in str(t or "").lower() for t in texte):
                continue
            if kat not in ("", "Alle") and (a.get("kategorie") or OHNE_KATEGORIE) != kat:
                continue
            if lief not in ("", "Alle") and lief not in {b.get("lieferant") for b in a["bezuege"]}:
                continue
            if status in ("Aktive", EK_FEHLT) and archiviert(a) or status == "Archivierte" and not archiviert(a):
                continue
            if status == EK_FEHLT and not zukauf.ek_fehlt(a):
                continue
            out.append(a)
        art = self.sortierung.currentText()
        name = lambda a: (a.get("bezeichnung") or "").lower()
        if art == "Kategorie":
            out.sort(key=lambda a: ((a.get("kategorie") or "~").lower(), name(a)))
        elif art == "Lieferant":
            out.sort(key=lambda a: ((a["_bezug"].get("lieferant") or "~").lower(), name(a)))
        elif art == "Artikelnummer":
            out.sort(key=lambda a: ((a.get("artikelnr") or "~").lower(), name(a)))
        elif art == "EK je Einheit":
            ek = lambda a: a["_vorschau"]["je_einheit"]["ek"] if a["_vorschau"] and not a["_vorschau"]["fehler"] else -1
            out.sort(key=lambda a: (-ek(a), name(a)))
        else:
            out.sort(key=name)
        return out

    def zellen(self, a):
        v = a["_vorschau"]
        ok = v is not None and not v["fehler"]
        quelle = {zukauf.KATEGORIE: "Kat.", zukauf.INDIVIDUELL: "indiv.", zukauf.STANDARD: "Std."}
        auf = ""
        if v is not None and v["regeln"]:
            auf = "; ".join(zukauf.regel_text(r).split(" (")[0] + f" ({quelle.get(r['quelle'], '')})" for r in v["regeln"])
        elif v is not None:
            auf = "kein Aufschlag"
        return dict(artikelnr=a.get("artikelnr") or "", bezeichnung=a.get("bezeichnung") or "",
                    kategorie=a.get("kategorie") or "", lieferant=a["_bezug"].get("lieferant") or "",
                    einheit=zukauf.EINHEIT_KURZ.get(a.get("einheit"), a.get("einheit") or ""),
                    ek=euro_einheit(v["je_einheit"]["ek"]) if ok else (EK_FEHLT if zukauf.ek_fehlt(a) else "kein Preis"),
                    bezug=" + ".join(x for x in (
                        f"{euro(a['_je_bestellung'])} je Best." if a["_je_bestellung"] else "",
                        f"{euro_einheit(v['je_einheit']['bezug'])} je {zukauf.EINHEIT_KURZ.get(a.get('einheit'), 'Einh.')}"
                        if ok and v["je_einheit"]["bezug"] else "") if x),
                    aufschlag=auf, vk=euro_einheit(v["je_einheit"]["vk"]) if ok else "",
                    status="archiviert" if archiviert(a) else ("Preis abgelaufen" if ok and v["warnung"].startswith(
                        "Einkaufspreis abgelaufen") else "aktiv"))

    def anzeigen(self, *_):
        gewaehlt = self.gewaehlt()
        self.sichtbar = self.gefiltert()
        zellen = [self.zellen(a) for a in self.sichtbar]
        self.tabelle.setRowCount(len(self.sichtbar))
        for r, (a, w) in enumerate(zip(self.sichtbar, zellen)):
            for c, (_, n, _) in enumerate(SPALTEN):
                it = QTableWidgetItem(w[n])
                it.setData(Qt.UserRole, a["id"])
                if n in ("ek", "bezug", "vk"):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if n == "vk":
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                if archiviert(a):
                    it.setForeground(stil.farbe(GRAU))
                elif (n == "ek" and w[n] in ("kein Preis", EK_FEHLT)) or (n == "aufschlag" and w[n] == "kein Aufschlag"):
                    it.setForeground(stil.farbe(ROT))
                elif n == "status" and w[n] == "Preis abgelaufen":
                    it.setForeground(stil.farbe(GELB))
                self.tabelle.setItem(r, c, it)
        self.zellen_text = zellen
        self._einpassen()
        arch = sum(1 for a in self.daten if archiviert(a))
        self.anzahl.setText(f"{len(self.sichtbar)} von {len(self.daten)} Artikeln" + (f", {arch} archiviert" if arch else ""))
        self.auswaehlen(gewaehlt)
        self._auswahl()

    def _einpassen(self):
        """Nullwert-Regel: leere optionale Spalten ausblenden; bei schmalem Fenster weitere Spalten weglassen."""
        zellen = getattr(self, "zellen_text", [])
        for c, (_, n, immer) in enumerate(SPALTEN):
            self.tabelle.setColumnHidden(c, not immer and not any(w[n] for w in zellen))
        platz = self.tabelle.viewport().width()
        if platz <= 0:
            return
        kopf = self.tabelle.horizontalHeader()

        def bedarf():
            return sum(max(kopf.sectionSizeHint(c), self.tabelle.sizeHintForColumn(c)) if n != "bezeichnung" else 120
                       for c, (_, n, _) in enumerate(SPALTEN) if not self.tabelle.isColumnHidden(c))
        for n in WEGLASSEN:
            if bedarf() + 12 <= platz:
                break
            self.tabelle.setColumnHidden(next(c for c, x in enumerate(SPALTEN) if x[1] == n), True)

    def eventFilter(self, objekt, ereignis):
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
        for r, a in enumerate(self.sichtbar):
            if a["id"] == zeilen_id:
                self.tabelle.selectRow(r)
                return True
        self.tabelle.clearSelection()
        return False

    def _auswahl(self):
        a = self.zeile(self.gewaehlt())
        for k in (self.k_bearbeiten, self.k_duplizieren, self.k_archiv, self.k_ek):
            k.setEnabled(a is not None)
        self.k_archiv.setText("Wieder aktivieren" if a and archiviert(a) else "Archivieren")
        if not a:
            self.detail.setText(f"<span style='color:{GRAU}'>Artikel markieren: hier stehen Lieferanten, Staffeln "
                                "und die Berechnung für eine Einheit.</span>")
            return
        self.detail.setText(self.detail_text(a))

    def detail_text(self, a):
        v = a["_vorschau"]
        kopf = " ".join(x for x in (a.get("artikelnr"), a.get("bezeichnung")) if x)
        extra = [x for x in (a.get("kategorie"), a.get("beschreibung")) if x]
        if a.get("ean"):
            extra.append(f"EAN {a['ean']}")
        if a.get("artikeltyp") == zukauf.BLECH:
            extra.append(zukauf.blech_bezeichnung(a.get("laenge"), a.get("breite"), a.get("dicke"), a.get("werkstoff"))
                         + (f", aus {a['herkunft']}" if a.get("herkunft") else "")
                         + (f" ({a['step_datei']})" if a.get("step_datei") else ""))
        teile = [f"<b>{kopf}</b> &nbsp; <span style='color:{GRAU}'>{' · '.join(extra)}</span>"]
        for b in a["bezuege"]:
            z = [("★ " if b.get("bevorzugt") == "ja" else "") + (b.get("lieferant") or "ohne Lieferant")]
            if b.get("lieferanten_artnr"):
                z.append(f"Art.-Nr. {b['lieferanten_artnr']}")
            pe = b.get("preiseinheit") or 1
            st = zukauf.staffel_text(b.get("preise"))
            z.append(f"Preise je {zahl_als_text(pe, None)} {zukauf.EINHEIT_KURZ.get(a.get('einheit'), '')}: "
                     + (st.replace(' | ', ', ') + " €" if st else "<span style='color:#B42318'>kein Preis</span>"))
            for n, t in (("mindestmenge", "Mindestmenge"), ("vpe", "VPE"), ("lieferzeit", "Lieferzeit")):
                if b.get(n):
                    z.append(f"{t} {zahl_als_text(b[n], None)}" + (" Tage" if n == "lieferzeit" else ""))
            teile.append(" · ".join(z))
        if v is not None and not v["fehler"]:
            je = v["je_einheit"]
            menge = f" (bei {menge_text(a['_menge'], a.get('einheit'))})" if a["_menge"] != 1 else ""
            bez = f" + Bezug {euro_einheit(je['bezug'])} = Einstand {euro_einheit(je['einstand'])}" if je["bezug"] else ""
            if a["_je_bestellung"]:
                bez += f" (zzgl. Bezugskosten {euro(a['_je_bestellung'])} je Bestellung)"
            teile.append(f"Je Einheit{menge}: Einkauf {euro_einheit(je['ek'])}{bez}; {v['regel']} = "
                         f"{euro_einheit(je['aufschlag'])}; <b>Verkaufspreis {euro_einheit(je['vk'])}</b>")
            if v["warnung"]:
                teile.append(f"<span style='color:{GELB}'>{v['warnung']}</span>")
        if zukauf.ek_fehlt(a) and not archiviert(a):
            teile.append(f"<span style='color:{ROT}; font-weight:bold'>{EK_FEHLT}: Angebote mit diesem Artikel sind "
                         "unvollständig, bis ein Einkaufspreis über 0 € eingetragen ist (EK eintragen …).</span>")
        verw = self.db.zukauf_verwendung(a["id"])
        if verw["positionen"]:
            teile.append(f"verwendet in {verw['positionen']} Position(en), Angebote {', '.join(verw['angebote'][:8])}")
        return "<br>".join(teile)

    def _kontextmenue(self, pos):
        if self.tabelle.itemAt(pos) is None:
            return
        self.tabelle.selectRow(self.tabelle.itemAt(pos).row())
        m = QMenu(self)
        for t, f in (("Bearbeiten", self.bearbeiten), ("Duplizieren", self.duplizieren),
                     (self.k_archiv.text(), self.archiv_umschalten), ("EK eintragen …", self.ek_eintragen),
                     ("In Angebot übernehmen …", self.in_angebot)):
            m.addAction(t, f)
        m.exec(self.tabelle.viewport().mapToGlobal(pos))

    # -------------------------------------------------------------- Formular öffnen
    def schmal(self):
        return self.width() < BREIT

    def _frage(self, titel, text, knoepfe, standard):
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

    def _oeffnen(self, a, zeilen_id, titel):
        if not self._verwerfen_ok():
            return None
        self._formular_zu()
        if self.schmal():
            self.dialog = QDialog(self)
            self.dialog.setWindowTitle(titel)
            self.dialog.resize(600, 740)
            self.dialog.formular = ZukaufFormular(self.db, self.dialog)
            QVBoxLayout(self.dialog).addWidget(self.dialog.formular)
            self.dialog.formular.gespeichert.connect(self._gespeichert)
            self.dialog.formular.abgebrochen.connect(self._formular_zu)
            self.dialog.rejected.connect(self._formular_zu)
            self.dialog.formular.laden(a, zeilen_id, titel)
            self.dialog.setModal(True)
            self.dialog.show()
            return self.dialog.formular
        self.formular.laden(a, zeilen_id, titel)
        self.rechts.show()
        w = self.teiler.width()
        self.teiler.setSizes([w - 560, 560])
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
            for cb in (self.kat_filter, self.lief_filter):
                cb.setCurrentIndex(0)
            self.status_filter.setCurrentText("Alle")
            self.auswaehlen(zeilen_id)
        a = self.zeile(zeilen_id)
        self.meldung(f"Zukaufartikel '{a.get('bezeichnung') if a else ''}' gespeichert.")

    # -------------------------------------------------------------- Aktionen
    def neu(self):
        return self._oeffnen(None, None, "Neuer Zukaufartikel")

    def bearbeiten(self, zeilen_id=None):
        a = self.zeile(zeilen_id or self.gewaehlt())
        if not a:
            self.meldung("Bitte zuerst einen Artikel markieren.", fehler=True)
            return None
        return self._oeffnen(self.db.zukauf_artikel(a["id"]), a["id"], f"Artikel bearbeiten: {a.get('bezeichnung')}")

    def duplizieren(self, zeilen_id=None):
        a = self.zeile(zeilen_id or self.gewaehlt())
        if not a:
            self.meldung("Bitte zuerst einen Artikel markieren.", fehler=True)
            return None
        kopie = self.db.zukauf_artikel(a["id"])
        kopie.pop("id", None)
        kopie["artikelnr"] = kopie_nummer(kopie.get("artikelnr"), [x.get("artikelnr") for x in self.daten])
        kopie["bezeichnung"] = f"{kopie.get('bezeichnung') or ''} (Kopie)"
        kopie["status"] = "aktiv"
        for n in ("herkunft", "step_datei", "fingerabdruck"):     # eine Kopie ist kein Ergebnis des STEP-Imports
            kopie[n] = None
        for b in kopie["bezuege"]:
            b.pop("id", None)
        return self._oeffnen(kopie, None, f"Kopie von {a.get('bezeichnung')} (wird erst mit Speichern angelegt)")

    def ek_eintragen(self, zeilen_id=None, preis=None):
        """Einkaufspreis je Einheit beim bevorzugten Lieferanten eintragen (Abfrage, preis für Tests)."""
        a = self.zeile(zeilen_id or self.gewaehlt())
        if not a:
            self.meldung("Bitte zuerst einen Artikel markieren.", fehler=True)
            return False
        if not self._verwerfen_ok():
            return False
        b = a["_bezug"]
        lief = b.get("lieferant") or zukauf.BLECH_LIEFERANT.get(a.get("kategorie")) or None
        if preis is None:
            from PySide6.QtWidgets import QInputDialog
            alt = (zukauf.staffel_sortiert(b.get("preise")) or [{}])[0].get("preis")
            preis, ok = QInputDialog.getDouble(
                self, "EK eintragen", f"{a.get('bezeichnung')}\nEinkaufspreis netto je "
                f"{zukauf.EINHEIT_KURZ.get(a.get('einheit'), a.get('einheit') or 'Einheit')}"
                + (f" bei {lief}" if lief else "") + " [€]:", float(alt or 0), 0, 1e7, 4)
            if not ok:
                return False
        try:
            self.db.zukauf_ek_eintragen(a["id"], preis, lief)
        except ValueError as e:
            self.meldung(str(e), fehler=True)
            return False
        self._formular_zu()
        self.neu_laden()
        if not self.auswaehlen(a["id"]):
            self.status_filter.setCurrentText("Alle")
            self.auswaehlen(a["id"])
        self.meldung(f"Einkaufspreis für '{a.get('bezeichnung')}' eingetragen: {euro_einheit(zukauf.dez(preis))}.")
        return True

    def archiv_umschalten(self, zeilen_id=None):
        a = self.zeile(zeilen_id or self.gewaehlt())
        if not a:
            return
        neu = "aktiv" if archiviert(a) else "archiviert"
        self.db.zukauf_status(a["id"], neu)
        self.neu_laden()
        if not self.auswaehlen(a["id"]):
            self.status_filter.setCurrentText("Alle")
            self.auswaehlen(a["id"])
        self.meldung(f"Zukaufartikel '{a.get('bezeichnung')}' {'archiviert' if neu == 'archiviert' else 'wieder aktiv'}."
                     + (" Bestehende Angebote rechnen mit ihrem gespeicherten Preisstand weiter." if neu == "archiviert"
                        else ""))


    def csv_export(self, exportieren):
        pfad = exportieren(self, self.db)
        if pfad:
            self.meldung(f"Zukaufartikel exportiert: {pfad}")

    def csv_import(self, importieren):
        try:
            ergebnis, erg = importieren(self, self.db)
        except (OSError, ValueError) as e:
            self.meldung(f"CSV-Import: {e}", fehler=True)
            return
        if erg:
            self.window().alles_neu_laden() if hasattr(self.window(), "alles_neu_laden") else self.neu_laden()
            self.meldung(f"CSV-Import: {erg[0]} Artikel neu, {erg[1]} geändert.")

    def in_angebot(self, zeilen_id=None, ziel=None):
        """Artikel als Zukaufteil in eine Position übernehmen. ziel = (Positions-ID, Menge je Teil) ohne Dialog
        (Tests). Ergebnis: Positions-ID oder None."""
        a = self.zeile(zeilen_id or self.gewaehlt())
        if not a:
            self.meldung("Bitte zuerst einen Artikel markieren.", fehler=True)
            return None
        if archiviert(a):
            self.meldung("Archivierte Artikel lassen sich nicht in Angebote übernehmen.", fehler=True)
            return None
        if ziel is None:
            d = UebernahmeDialog(self, self.db, a)
            if d.exec() != QDialog.Accepted or d.ziel is None:
                return None
            ziel = d.ziel
        pid, menge = ziel
        p = self.db.con.execute("SELECT angebot_id, pos, zukauf FROM positionen WHERE id=?", (pid,)).fetchone()
        liste = zukauf.json_liste(p["zukauf"])
        liste.append(dict(artikel_id=a["id"], menge=menge, aufschlag=None, stand=self.db.zukauf_stand(a["id"])))
        self.db.position_aendern(pid, "zukauf", json.dumps(liste, ensure_ascii=False))
        seite = getattr(self.window(), "offen", {}).get(p["angebot_id"])
        if seite is not None:
            seite.neu_laden()
        nummer = (self.db.angebot(p["angebot_id"]) or {}).get("nummer") or ""
        self.meldung(f"'{a.get('bezeichnung')}' als Zukaufteil in Angebot {nummer}, Pos. {p['pos'] or ''} übernommen.")
        return pid


class UebernahmeDialog(QDialog):
    """Angebot und Position wählen, Menge je Teil eingeben."""

    def __init__(self, parent, db, artikel):
        super().__init__(parent)
        self.db, self.ziel = db, None
        self.setWindowTitle(f"In Angebot übernehmen: {artikel.get('bezeichnung') or ''}")
        self.angebot = QComboBox()
        offen = getattr(parent.window(), "offen", {})
        liste = sorted(db.angebote(), key=lambda x: (x["id"] not in offen, -(x["id"] or 0)))
        for x in liste:
            self.angebot.addItem(" · ".join(t for t in (x.get("nummer"), x.get("kunde")) if t)
                                 + (" (geöffnet)" if x["id"] in offen else ""), x["id"])
        self.position = QComboBox()
        self.menge = QLineEdit("1")
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #8C1D18;")
        form = QFormLayout(self)
        form.addRow("Angebot", self.angebot)
        form.addRow("Position", self.position)
        form.addRow(f"Menge je Teil [{zukauf.EINHEIT_KURZ.get(artikel.get('einheit'), 'St')}]", self.menge)
        form.addRow(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)
        self.angebot.currentIndexChanged.connect(self._positionen)
        self._positionen()

    def _positionen(self, *_):
        self.position.clear()
        aid = self.angebot.currentData()
        for p in self.db.positionen(aid) if aid is not None else ():
            self.position.addItem(" ".join(str(t) for t in (p.get("pos"), p.get("artikel"), p.get("bezeichnung"))
                                           if t not in (None, "")) or "(leer)", p["id"])

    def _ok(self):
        if self.position.currentData() is None:
            self.fehler.setText("Bitte eine Position wählen.")
            return
        try:
            m = zahl_aus_text(self.menge.text())
        except ValueError:
            m = None
        if not m or m <= 0:
            self.fehler.setText("Menge je Teil muss größer als 0 sein.")
            return
        self.ziel = (self.position.currentData(), m)
        self.accept()


class ZukaufBereich(QWidget):
    """Hauptreiter 'Zukaufartikel' mit den Unterreitern Artikel, Kategorien und Lieferanten."""
    titel = TITEL

    def __init__(self, db, meldung):
        from .fenster import StammdatenSeite
        super().__init__()
        self.db = db
        self.artikel = ArtikelSeite(db, meldung)
        self.kategorien = StammdatenSeite(db, zukauf.KATEGORIEN, meldung)
        self.lieferanten = StammdatenSeite(db, zukauf.LIEFERANTEN, meldung)
        from .zukauf_preise import PreisaenderungenSeite
        self.preise = PreisaenderungenSeite(db, meldung)
        self.unter = QTabWidget()
        self.unter.addTab(self.artikel, "Artikel")
        self.unter.addTab(self.kategorien, zukauf.KATEGORIEN.titel)
        self.unter.addTab(self.lieferanten, zukauf.LIEFERANTEN.titel)
        self.unter.addTab(self.preise, self.preise.titel)
        self.unter.currentChanged.connect(self._gewechselt)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.unter)

    def _gewechselt(self, _):
        self.neu_laden()

    def neu_laden(self):
        for s in (self.kategorien, self.lieferanten, self.preise):
            s.neu_laden()
        self.artikel.neu_laden()
