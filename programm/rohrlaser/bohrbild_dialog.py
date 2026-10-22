"""Dialog 'Bohrungen prüfen': Gewinde-Vorschläge, Senkungen und Fließlochbohrungen einer Position bestätigen oder
ablehnen (Doppelklick auf Status, Gewinde oder Bohrungen der Position). Rechnet nichts selbst: bohrbild.py."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import bohrbild
from .stammdaten import zahl_als_text

KEIN_GEWINDE = "kein Gewinde"


class BohrbildDialog(QDialog):
    """Je Zeile: Art, Ø, Anzahl je Teil, Gewinde (Auswahl), was der Laser macht bzw. Senk-Ø gravieren, und
    Bestätigen/Ablehnen. Unten weitere Gewinde von Hand und die Auswirkung. Ergebnis: self.ergebnis = (Liste, Text
    der Gewinde von Hand)."""
    SPALTEN = ("Art", "Ø [mm]", "Anzahl je Teil", "Gewinde", "Laser", "Prüfung")

    def __init__(self, parent, p, gewinde):
        """gewinde = [(Gewinde, Kernloch)] der Stammdaten."""
        super().__init__(parent)
        self.p = p
        self.liste = [dict(z) for z in bohrbild.aus_position(p, gewinde)]
        gewinde_namen = [g for g, _ in gewinde]
        self.ergebnis = None
        titel = " ".join(str(x) for x in (p.get("pos"), p.get("artikel")) if x)
        self.setWindowTitle(f"Bohrungen prüfen – Pos. {titel}")
        self.resize(900, 360)
        lay = QVBoxLayout(self)
        info = QLabel("Je Zeile <b>Bestätigen</b> oder <b>Ablehnen</b>. Gewinde werden erst nach dem Bestätigen "
                      "gerechnet. Senkung: der Laser schneidet die Bohrung, auf Wunsch wird der Senk-Ø graviert. "
                      "Flowdrill: der Laser markiert nur (Gravur oder Loch Ø0,5); abgelehnt = normale Bohrung.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.tabelle = QTableWidget(len(self.liste), len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.gruppen, self.gewinde, self.laser = [], [], []
        for r, z in enumerate(self.liste):
            art = {"Bohrung": "Bohrung (Kernloch)", "Fließloch": "Flowdrill"}.get(z["art"], z["art"])
            masse = bohrbild.dez(z.get("d")) + (f" / {bohrbild.dez(z.get('D'))}" if z.get("D") else "")
            for c, text in ((0, art), (1, masse), (2, str(z.get("anzahl") or ""))):
                it = QTableWidgetItem(text)
                if c:
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.tabelle.setItem(r, c, it)
            gw = None
            if z["art"] in ("Bohrung", "Fließloch"):
                gw = QComboBox()
                gw.addItem(KEIN_GEWINDE)
                gw.addItems(sorted(set(gewinde_namen) | ({z["gewinde"]} if z.get("gewinde") else set()),
                                   key=_gewinde_sortierung))
                gw.setCurrentText(z.get("gewinde") or KEIN_GEWINDE)
                gw.currentTextChanged.connect(self._auswirkung)
                self.tabelle.setCellWidget(r, 3, gw)
            self.gewinde.append(gw)
            ls = None
            if z["art"] == "Senkung":
                ls = QCheckBox(f"Senk-Ø {bohrbild.dez(z.get('D'))} gravieren")
                ls.setChecked(bool(z.get("gravur")))
                ls.toggled.connect(self._auswirkung)
            elif z["art"] == "Fließloch":
                ls = QComboBox()
                ls.addItems(bohrbild.LASER)
                ls.setCurrentText(z.get("laser") or bohrbild.GRAVUR)
                ls.currentTextChanged.connect(self._auswirkung)
            if ls is not None:
                self.tabelle.setCellWidget(r, 4, ls)
            else:
                self.tabelle.setItem(r, 4, QTableWidgetItem("schneidet die Bohrung"))
            self.laser.append(ls)
            knoepfe = QWidget()
            kl = QHBoxLayout(knoepfe)
            kl.setContentsMargins(2, 0, 2, 0)
            gruppe = QButtonGroup(knoepfe)
            for text, status, farbe in (("✓ Bestätigen", bohrbild.BESTAETIGT, "#C6EFCE"),
                                        ("✗ Ablehnen", bohrbild.ABGELEHNT, "#FFC7CE")):
                b = QPushButton(text)
                b.setCheckable(True)
                b.setProperty("status", status)
                b.setStyleSheet(f"QPushButton:checked {{ background: {farbe}; font-weight: bold; }}")
                b.setChecked(z.get("status") == status)
                gruppe.addButton(b)
                kl.addWidget(b)
            gruppe.buttonClicked.connect(self._auswirkung)
            self.gruppen.append(gruppe)
            self.tabelle.setCellWidget(r, 5, knoepfe)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setStretchLastSection(True)
        self.tabelle.verticalHeader().setDefaultSectionSize(34)
        lay.addWidget(self.tabelle, 1)
        if not self.liste:
            lay.addWidget(QLabel("Diese Position hat keine Gewinde-Vorschläge, Senkungen oder Fließlochbohrungen aus "
                                 "dem STEP-Import."))
        zeile = QHBoxLayout()
        alle = QPushButton("Alle bestätigen")
        alle.clicked.connect(self.alle_bestaetigen)
        alle.setEnabled(bool(self.liste))
        zeile.addWidget(alle)
        zeile.addSpacing(16)
        zeile.addWidget(QLabel("Weitere Gewinde von Hand:"))
        self.hand = QLineEdit(bohrbild.hand_gewinde(p, self.liste))
        self.hand.setPlaceholderText("z. B. 2xM10; 1xM12")
        self.hand.textChanged.connect(self._auswirkung)
        zeile.addWidget(self.hand, 1)
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

    def werte(self):
        """Bohrbild nach der Wahl im Dialog."""
        out = []
        for z, gruppe, gw, ls in zip(self.liste, self.gruppen, self.gewinde, self.laser):
            z = dict(z)
            b = gruppe.checkedButton()
            z["status"] = b.property("status") if b else bohrbild.OFFEN
            if gw is not None:
                z["gewinde"] = None if gw.currentText() == KEIN_GEWINDE else gw.currentText()
            if isinstance(ls, QCheckBox):
                z["gravur"] = ls.isChecked()
            elif isinstance(ls, QComboBox):
                z["laser"] = ls.currentText()
            out.append(z)
        return out

    def setzen(self, nr, status=None, gewinde=None, laser=None, gravur=None):
        """Zeile nr ohne Maus setzen (Tests, Bildschirmfotos)."""
        if status is not None:
            for b in self.gruppen[nr].buttons():
                b.setChecked(b.property("status") == status)
        if gewinde is not None:
            self.gewinde[nr].setCurrentText(gewinde)
        if laser is not None:
            self.laser[nr].setCurrentText(laser)
        if gravur is not None:
            self.laser[nr].setChecked(gravur)
        self._auswirkung()

    def alle_bestaetigen(self):
        for nr in range(len(self.liste)):
            self.setzen(nr, bohrbild.BESTAETIGT)

    def _auswirkung(self, *_):
        neu = self.werte()
        felder = bohrbild.anwenden(self.p, neu, self.hand.text())
        teile = []
        for name, titel, einheit, stellen in (("schneidweg", "Schneidweg", " mm", 1), ("gravur", "Gravur", " mm", 1),
                                              ("einstiche", "Einstiche", "", 0)):
            if name in felder:
                alt, wert = self.p.get(name) or 0, felder[name] or 0
                teile.append(f"{titel} {zahl_als_text(alt, stellen)} → {zahl_als_text(wert, stellen)}{einheit}")
        teile.append("Gewinde: " + (felder.get("gewinde") or "keine"))
        offen = bohrbild.offen(neu)
        if offen:
            teile.append(f"<span style='color:#7A5A00'>{offen} Zeile{'n' if offen != 1 else ''} noch offen</span>")
        self.auswirkung.setText("Auswirkung je Teil: " + " · ".join(teile))

    def accept(self):
        self.ergebnis = (self.werte(), self.hand.text())
        super().accept()


def _gewinde_sortierung(g):
    try:
        return (0, float(str(g).upper().lstrip("M").replace(",", ".")))
    except ValueError:
        return (1, str(g))
