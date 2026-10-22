"""Schnellanlage von Zukaufartikeln aus dem Angebot (z. B. 20 Bleche für einen Rahmen): Bezeichnung, Kategorie,
Lieferant, EK je Stück, Aufschlag und Menge je Teil bzw. je Satz in einem kurzen Formular.

Der Artikel wird wie im Reiter Zukaufartikel gespeichert (Einheit Stück, Preiseinheit 1, ein Lieferant) und kann
dort später ergänzt werden. Bei Kategorie Blechteile (oder 'Blech' in der Bezeichnung) ist der Lieferant
zukauf.BLECH_LIEFERANT vorbelegt. Ein leerer Aufschlag nimmt die Regel der Kategorie bzw. den Standard."""
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout)

from . import zukauf
from .stammdaten import zahl_aus_text

HERKUNFT = "Schnellanlage"


def _zahl(text, titel, leer_erlaubt=True):
    t = (text or "").strip()
    if not t:
        if leer_erlaubt:
            return None
        raise ValueError(f"Bitte {titel} eingeben.")
    try:
        w = zahl_aus_text(t)
    except ValueError:
        raise ValueError(f"{titel}: '{t}' ist keine Zahl.")
    if w < 0:
        raise ValueError(f"{titel} darf nicht negativ sein.")
    return w


def artikel_werte(bezeichnung, artikelnr, kategorie, lieferant, ek, aufschlag):
    """(Artikel, [Einkauf]) für db.zukauf_speichern; aufschlag None = Regel der Kategorie."""
    werte = dict(artikelnr=artikelnr or None, bezeichnung=bezeichnung, kategorie=kategorie or None, einheit="Stück",
                 status="aktiv", herkunft=HERKUNFT,
                 aufschlag_quelle=zukauf.KATEGORIE if aufschlag is None else zukauf.INDIVIDUELL,
                 aufschlag_methode=None if aufschlag is None else zukauf.PROZENT, aufschlag_wert=aufschlag)
    return werte, [dict(lieferant=lieferant, bevorzugt="ja", preiseinheit=1, preise=[dict(ab=1, preis=ek)])]


class SchnellDialog(QDialog):
    """Neue Zukaufartikel nacheinander anlegen. ergebnis: [{artikel_id, bezeichnung, artikelnr, menge, je}] der
    angelegten Artikel. ganz: Menge nur ganzzahlig (eigene Positionen im Angebot); hinweis: Text unter dem Formular,
    der sagt, worauf sich die Menge bezieht; ohne_je: nur Stückzahl, ohne Wahl je Teil/je Satz; blech: Kategorie
    Blechteile vorbelegt."""

    def __init__(self, parent, db, satz=False, ganz=False, hinweis="", ohne_je=False, blech=True):
        super().__init__(parent)
        self.db, self.ganz = db, ganz
        self.ergebnis = []
        self._lief_von_hand = False
        self.setWindowTitle("Neuer Zukaufartikel")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.bezeichnung = QLineEdit()
        self.bezeichnung.setPlaceholderText("z. B. Blech Lasche 80x40x5")
        self.artikelnr = QLineEdit()
        self.artikelnr.setPlaceholderText("optional")
        self.kategorie = QComboBox()
        kat = [n for n, z in db.zukauf_kategorien().items() if (z.get("aktiv") or "ja") == "ja"]
        self.kategorie.addItems([""] + kat)
        if blech and "Blechteile" in kat:
            self.kategorie.setCurrentText("Blechteile")
        self.lieferant = QComboBox()
        self.lieferant.setEditable(True)
        self.lieferant.addItems(sorted(z["name"] for z in db.zeilen("zukauf_lieferanten") if z.get("name")))
        self.lieferant.lineEdit().textEdited.connect(self._lief_gesetzt)
        self.ek = QLineEdit()
        self.ek.setPlaceholderText("€ je Stück")
        self.aufschlag = QLineEdit()
        self.aufschlag.setPlaceholderText("leer = Aufschlag der Kategorie bzw. Standard")
        self.menge = QLineEdit("1")
        self.je = QComboBox()
        self.je.addItem("je Teil", zukauf.JE_TEIL)
        self.je.addItem("je Satz", zukauf.JE_SATZ)
        self.je.setCurrentIndex(1 if satz else 0)
        self.je.setToolTip("je Satz: die Menge gilt je Satz (z. B. 20 Bleche je Rahmen); Sätze = Stückzahl / "
                           "Stück je Satz der Position")
        menge = QHBoxLayout()
        menge.addWidget(self.menge, 1)
        menge.addWidget(self.je)
        form.addRow("Bezeichnung *", self.bezeichnung)
        form.addRow("Artikelnummer", self.artikelnr)
        form.addRow("Kategorie", self.kategorie)
        form.addRow("Lieferant *", self.lieferant)
        form.addRow("EK je Stück [€] *", self.ek)
        form.addRow("Aufschlag [%]", self.aufschlag)
        form.addRow("Stückzahl" if ohne_je else "Menge", menge)
        self.je.setVisible(not ohne_je)
        lay.addLayout(form)
        if hinweis:
            h = QLabel(hinweis)
            h.setWordWrap(True)
            h.setStyleSheet("color: #5F6B7A;")
            lay.addWidget(h)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: #8C1D18;")
        lay.addWidget(self.info)
        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        self.weiter_knopf = QPushButton("Speichern + nächster")
        self.weiter_knopf.clicked.connect(self.weiter)
        self.ok_knopf = QPushButton("Speichern + schließen")
        self.ok_knopf.setObjectName("primaer")
        self.ok_knopf.setDefault(True)
        self.ok_knopf.clicked.connect(self.fertig)
        ab = QPushButton("Schließen")
        ab.clicked.connect(self._schliessen)
        for b in (self.weiter_knopf, self.ok_knopf, ab):
            knoepfe.addWidget(b)
        lay.addLayout(knoepfe)
        self.kategorie.currentTextChanged.connect(lambda _: self._vorgabe())
        self.bezeichnung.textChanged.connect(lambda _: self._vorgabe())
        self._vorgabe()
        self.resize(460, self.sizeHint().height())

    def _lief_gesetzt(self, text):
        self._lief_von_hand = bool(text.strip())

    def _vorgabe(self):
        """Lieferant nach Kategorie bzw. Bezeichnung vorschlagen, solange er nicht von Hand eingetragen wurde."""
        if not self._lief_von_hand:
            self.lieferant.setCurrentText(zukauf.lieferant_vorgabe(self.kategorie.currentText(),
                                                                   self.bezeichnung.text()))

    def speichern(self):
        """Artikel aus den Eingaben anlegen; Ergebnis ID oder None (Meldung im Dialog)."""
        try:
            bez = self.bezeichnung.text().strip()
            if not bez:
                raise ValueError("Bitte eine Bezeichnung eingeben.")
            lief = self.lieferant.currentText().strip()
            if not lief:
                raise ValueError("Bitte einen Lieferanten eingeben.")
            ek = _zahl(self.ek.text(), "EK je Stück", False)
            if ek <= 0:
                raise ValueError("EK je Stück muss größer als 0 € sein.")
            auf = _zahl(self.aufschlag.text(), "Aufschlag")
            menge = _zahl(self.menge.text(), "Menge", False)
            if menge <= 0:
                raise ValueError("Menge muss größer als 0 sein.")
            if self.ganz and menge != int(menge):
                raise ValueError("Menge muss eine ganze Zahl sein (Stück).")
            werte, bezuege = artikel_werte(bez, self.artikelnr.text().strip(), self.kategorie.currentText(), lief, ek,
                                           auf)
            aid = self.db.zukauf_speichern(None, werte, bezuege, "Schnellanlage im Angebot")
        except ValueError as e:
            self.info.setStyleSheet("color: #8C1D18;")
            self.info.setText(str(e))
            return None
        self.ergebnis.append(dict(artikel_id=aid, bezeichnung=werte["bezeichnung"], artikelnr=werte["artikelnr"],
                                  menge=menge, je=self.je.currentData()))
        return aid

    def weiter(self):
        """Speichern und Formular für den nächsten Artikel leeren (Kategorie, Lieferant, Aufschlag, je bleiben)."""
        if self.speichern() is None:
            return False
        self.info.setStyleSheet("color: #2E6B30;")
        self.info.setText(f"{self.bezeichnung.text().strip()} gespeichert ({len(self.ergebnis)} Artikel angelegt).")
        for f in (self.bezeichnung, self.artikelnr, self.ek):
            f.clear()
        self.menge.setText("1")
        self.bezeichnung.setFocus()
        return True

    def fertig(self):
        """Speichern und schließen; leeres Formular nach 'Speichern + nächster' schließt nur."""
        if not self.bezeichnung.text().strip() and not self.ek.text().strip() and self.ergebnis:
            self.accept()
            return True
        if self.speichern() is None:
            return False
        self.accept()
        return True

    def _schliessen(self):
        (self.accept if self.ergebnis else self.reject)()
