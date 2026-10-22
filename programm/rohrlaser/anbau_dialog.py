"""Dialog 'Anbauteile prüfen': aufgeschweißte Bolzen, Muttern, Laschen, Bleche und Kopfplatten eines Rohrteils aus
dem STEP-Import prüfen (Doppelklick auf die Spalte Anbauteile im STEP-Prüfdialog). Rechnet nichts selbst: anbau.py."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import anbau
from .stammdaten import zahl_als_text

OHNE_TRENNUNG = "ohne Trennung"


class AnbauDialog(QDialog):
    """Je Zeile: Nr., Art (Auswahl), Lage, Aufstand, Höhe, Bearbeitung (Auswahl), Gravur [mm] (änderbar),
    Erkennung und Bestätigen/Ausschließen. ohne_trennung: Kurztext der Messung ohne Trennung (Profil, Länge) oder
    None; dann fehlt der Knopf 'Ist kein Anbauteil'. Ergebnis: self.ergebnis = neue Liste bzw. OHNE_TRENNUNG
    (die Messung ohne Trennung soll gelten) oder None (abgebrochen)."""
    SPALTEN = ("Nr.", "Art", "Lage", "Aufstand [mm]", "Höhe [mm]", "Bearbeitung", "Gravur [mm]", "Erkennung",
               "Prüfung")

    def __init__(self, parent, liste, titel, gravur, ohne_trennung=None):
        """gravur = Gravur des Teils [mm] (für die Auswirkung)."""
        super().__init__(parent)
        self.liste = anbau.lesen(liste)
        self.alt = anbau.lesen(liste)
        self.gravur = float(gravur or 0)
        self.ergebnis = None
        self.setWindowTitle(f"Anbauteile prüfen – {titel}")
        self.resize(1050, 380)
        lay = QVBoxLayout(self)
        info = QLabel("Anbauteile werden nicht gelasert; das Rohr ist ohne sie gemessen. Der Laser graviert nur "
                      "ihre Lage: <b>Umriss</b> der Aufstandsfläche, <b>Positionsmarke</b> (Kreuz 2 × 10 mm), "
                      "<b>Punktmarke</b> (Kreuz 2 × 2 mm) oder <b>keine</b>. Je Zeile <b>Bestätigen</b> oder "
                      "<b>Ausschließen</b> (keine Gravur). Unsicher erkannte Anbauteile (Erkennung „prüfen“) bitte "
                      "immer entscheiden.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.tabelle = QTableWidget(len(self.liste), len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.arten, self.bearbeitung, self.laengen, self.gruppen = [], [], [], []
        for r, a in enumerate(self.liste):
            quelle = f" ({a['quelle']})" if str(a.get("quelle") or "").startswith("Körper") else ""
            for c, text in ((0, str(a.get("nr") or r + 1)), (2, anbau.lage_text(a) + quelle),
                            (3, anbau.aufstand_text(a)), (4, anbau.dez(a.get("hoehe"))),
                            (7, "sicher" if not anbau.unsicher(a) else "prüfen")):
                it = QTableWidgetItem(text)
                if c in (0, 4):
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if c == 7 and anbau.unsicher(a):
                    it.setBackground(Qt.yellow)
                if a.get("hinweis"):
                    it.setToolTip(a["hinweis"])
                self.tabelle.setItem(r, c, it)
            art = QComboBox()
            art.addItems(list(dict.fromkeys(list(anbau.ARTEN) + [a.get("art") or "Sonstiges"])))
            art.setCurrentText(a.get("art") or "Sonstiges")
            art.currentTextChanged.connect(lambda t, r=r: self._art(r, t))
            self.tabelle.setCellWidget(r, 1, art)
            self.arten.append(art)
            be = QComboBox()
            be.addItems(anbau.bearbeitungen(a))
            be.setCurrentText(a.get("bearbeitung") or anbau.vorgabe(a, a.get("art")))
            be.currentTextChanged.connect(lambda t, r=r: self._bearbeitung(r, t))
            self.tabelle.setCellWidget(r, 5, be)
            self.bearbeitung.append(be)
            lg = QDoubleSpinBox()
            lg.setRange(0, 100000)
            lg.setDecimals(2)
            lg.setValue(float(a.get("gravur_laenge") or 0))
            lg.setToolTip("Gravurlänge; aus der Bearbeitung vorbelegt, von Hand änderbar")
            lg.valueChanged.connect(self._auswirkung)
            self.tabelle.setCellWidget(r, 6, lg)
            self.laengen.append(lg)
            knoepfe = QWidget()
            kl = QHBoxLayout(knoepfe)
            kl.setContentsMargins(2, 0, 2, 0)
            gruppe = QButtonGroup(knoepfe)
            for text, status, farbe in (("✓ Bestätigen", anbau.BESTAETIGT, "#C6EFCE"),
                                        ("✗ Ausschließen", anbau.AUSGESCHLOSSEN, "#FFC7CE")):
                b = QPushButton(text)
                b.setCheckable(True)
                b.setProperty("status", status)
                b.setStyleSheet(f"QPushButton:checked {{ background: {farbe}; font-weight: bold; }}")
                b.setChecked(a.get("status") == status)
                gruppe.addButton(b)
                kl.addWidget(b)
            gruppe.buttonClicked.connect(self._auswirkung)
            self.gruppen.append(gruppe)
            self.tabelle.setCellWidget(r, 8, knoepfe)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setStretchLastSection(True)
        self.tabelle.verticalHeader().setDefaultSectionSize(34)
        lay.addWidget(self.tabelle, 1)
        if not self.liste:
            lay.addWidget(QLabel("Dieses Teil hat keine Anbauteile aus dem STEP-Import."))
        zeile = QHBoxLayout()
        alle = QPushButton("Alle bestätigen")
        alle.clicked.connect(self.alle_bestaetigen)
        alle.setEnabled(bool(self.liste))
        zeile.addWidget(alle)
        zeile.addStretch(1)
        self.ohne = QPushButton("Ist kein Anbauteil: Messung ohne Trennung verwenden")
        self.ohne.setToolTip(f"Das Teil gilt so, wie es ohne Abtrennen gemessen wurde: {ohne_trennung}"
                             if ohne_trennung else "Ohne Trennung ist das Teil nicht messbar.")
        self.ohne.setEnabled(bool(ohne_trennung))
        self.ohne.clicked.connect(self.ohne_trennung)
        zeile.addWidget(self.ohne)
        lay.addLayout(zeile)
        self.auswirkung = QLabel()
        self.auswirkung.setWordWrap(True)
        lay.addWidget(self.auswirkung)
        bb = QDialogButtonBox()
        bb.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        bb.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._auswirkung()

    def _art(self, r, art):
        """Andere Art: Bearbeitung und Gravurlänge auf die Vorgabe der Art."""
        self.bearbeitung[r].setCurrentText(anbau.vorgabe(self.liste[r], art))
        self._bearbeitung(r, self.bearbeitung[r].currentText())

    def _bearbeitung(self, r, bearbeitung):
        self.laengen[r].setValue(anbau.laenge(self.liste[r], bearbeitung))
        self._auswirkung()

    def werte(self):
        """Anbauteile nach der Wahl im Dialog."""
        out = []
        for a, art, be, lg, gruppe in zip(self.liste, self.arten, self.bearbeitung, self.laengen, self.gruppen):
            a = dict(a)
            b = gruppe.checkedButton()
            a.update(art=art.currentText(), bearbeitung=be.currentText(), gravur_laenge=round(lg.value(), 2),
                     status=b.property("status") if b else anbau.OFFEN)
            out.append(a)
        return out

    def setzen(self, nr, status=None, art=None, bearbeitung=None, laenge=None):
        """Zeile nr ohne Maus setzen (Tests, Bildschirmfotos)."""
        if art is not None:
            self.arten[nr].setCurrentText(art)
        if bearbeitung is not None:
            self.bearbeitung[nr].setCurrentText(bearbeitung)
        if laenge is not None:
            self.laengen[nr].setValue(laenge)
        if status is not None:
            for b in self.gruppen[nr].buttons():
                b.setChecked(b.property("status") == status)
        self._auswirkung()

    def alle_bestaetigen(self):
        for nr in range(len(self.liste)):
            self.setzen(nr, anbau.BESTAETIGT)

    def _auswirkung(self, *_):
        neu = self.werte()
        g = anbau.anwenden({"gravur": self.gravur, "gravur_anbau": anbau.gravur(self.alt)}, self.alt, neu)
        teile = [f"Gravur {zahl_als_text(self.gravur, 1)} → {zahl_als_text(g['gravur'], 1)} mm "
                 f"(davon Anbauteile {zahl_als_text(g['gravur_anbau'], 1)} mm)"]
        offen = anbau.offen(neu)
        if offen:
            teile.append(f"<span style='color:#7A5A00'>{offen} unsicher erkannte{'s' if offen == 1 else ''} "
                         f"Anbauteil{'e' if offen != 1 else ''} noch offen</span>")
        self.auswirkung.setText("Auswirkung je Teil: " + " · ".join(teile))

    def ohne_trennung(self):
        self.ergebnis = OHNE_TRENNUNG
        super().accept()

    def accept(self):
        self.ergebnis = self.werte()
        super().accept()
