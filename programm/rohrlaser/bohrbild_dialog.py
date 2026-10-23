"""Dialog 'Bohrungen prüfen': Gewinde-Vorschläge, Senkungen, Fließlochbohrungen und Bohrungen kleiner als
0,7 × Wandstärke (Bohren) einer Position bestätigen oder ablehnen (Doppelklick auf Status, Gewinde oder Bohrungen der
Position). Bestätigte Senkungen, Flowdrill und Bohren werden als Zusatzarbeit vorgeschlagen. Rechnet nichts selbst:
bohrbild.py."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import hilfe
from . import bohrbild, rechnen
from .stammdaten import zahl_als_text

KEIN_GEWINDE = "kein Gewinde"


class BohrbildDialog(QDialog):
    """Je Zeile: Art, Ø, Anzahl je Teil, Gewinde (Auswahl), was der Laser macht bzw. Senk-Ø gravieren, und
    Bestätigen/Ablehnen. Unten weitere Gewinde von Hand und die Auswirkung. Ergebnis: self.ergebnis = (Liste, Text
    der Gewinde von Hand)."""
    SPALTEN = ("Art", "Ø [mm]", "Anzahl je Teil", "Gewinde", "Gewinde [€/Stk]", "Arbeit [€/Stk]", "Laser", "Prüfung")
    G_PREIS, A_PREIS, LASER_SP, PRUEF = 4, 5, 6, 7

    def __init__(self, parent, p, gewinde, wand=None, laser=None, katalog=None, saetze=None, gewinde_preise=None):
        """gewinde = [(Gewinde, Kernloch)] der Stammdaten, wand = Wandstärke (Bohren < 0,7 × Wand), laser = Vorgabe
        der Markierung, katalog = Zeilen der Zusatzarbeiten (None: Zusatzarbeiten nicht anzeigen), gewinde_preise =
        {Gewinde: € je Stück} der Einstellungen. Preise je Zeile: leer = Einstellungen (grau), sonst nur diese
        Position."""
        super().__init__(parent)
        self.p = p
        self.katalog, self.saetze = katalog, saetze
        self.stamm_gewinde = gewinde_preise or {}
        self.stamm_arbeit = {z.get("name"): rechnen.zusatz_preis(z, saetze)["preis"] for z in katalog or ()
                             if z.get("name")}
        self.liste = [dict(z) for z in bohrbild.aus_position(p, gewinde, wand, laser or bohrbild.GRAVUR)]
        gewinde_namen = [g for g, _ in gewinde]
        self.ergebnis = None
        titel = " ".join(str(x) for x in (p.get("pos"), p.get("artikel")) if x)
        self.setWindowTitle(f"Bohrungen prüfen – Pos. {titel}")
        self.resize(1150, 380)
        lay = QVBoxLayout(self)
        info = hilfe.Hinweis("Je Zeile „Bestätigen“ oder „Ablehnen“. Gewinde werden erst nach dem Bestätigen "
                      "gerechnet. Senkung: der Laser schneidet die Bohrung, auf Wunsch wird der Senk-Ø graviert. "
                      "Flowdrill: der Laser markiert nur (Gravur oder Loch Ø0,5); abgelehnt = normale Bohrung. "
                      "Bohren: Bohrung kleiner als 0,7 × Wandstärke, der Laser markiert nur, danach aufbohren; "
                      "abgelehnt = der Laser schneidet sie. Bestätigte Senkungen, Flowdrill und Bohren kommen als "
                      "Zusatzarbeit Senken, Flowdrill bzw. Bohren mit der Anzahl je Teil in die Position.",
                             schluessel="bohrbild")             # erster Satz, Rest hinter „mehr“ (L7)
        lay.addWidget(info)
        self.tabelle = QTableWidget(len(self.liste), len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.gruppen, self.gewinde, self.laser, self.preise = [], [], [], []
        for r, z in enumerate(self.liste):
            art = {"Bohrung": "Bohrung (Kernloch)", "Fließloch": "Flowdrill",
                   bohrbild.BOHREN: "Bohren (< 0,7 × Wand)"}.get(z["art"], z["art"])
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
                gw.currentTextChanged.connect(lambda _=None, r=r: self._gewinde_platzhalter(r))
                self.tabelle.setCellWidget(r, 3, gw)
            self.gewinde.append(gw)
            ls = None
            if z["art"] == "Senkung":
                ls = QCheckBox(f"Senk-Ø {bohrbild.dez(z.get('D'))} gravieren")
                ls.setChecked(bool(z.get("gravur")))
                ls.toggled.connect(self._auswirkung)
            elif z["art"] in ("Fließloch", bohrbild.BOHREN):
                ls = QComboBox()
                ls.addItems(bohrbild.LASER)
                ls.setCurrentText(z.get("laser") or bohrbild.GRAVUR)
                ls.currentTextChanged.connect(self._auswirkung)
            if ls is not None:
                self.tabelle.setCellWidget(r, self.LASER_SP, ls)
            else:
                self.tabelle.setItem(r, self.LASER_SP, QTableWidgetItem("schneidet die Bohrung"))
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
            self.tabelle.setCellWidget(r, self.PRUEF, knoepfe)
            gp = ap = None
            if gw is not None:
                gp = self._preisfeld(z.get("gewinde_preis"))
                self.tabelle.setCellWidget(r, self.G_PREIS, gp)
            if z["art"] in bohrbild.ZUSATZ_ARBEIT:
                ap = self._preisfeld(z.get("preis"), self.stamm_arbeit.get(bohrbild.ZUSATZ_ARBEIT[z["art"]]),
                                     bohrbild.ZUSATZ_ARBEIT[z["art"]])
                self.tabelle.setCellWidget(r, self.A_PREIS, ap)
            self.preise.append((gp, ap))
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setStretchLastSection(True)
        self.tabelle.verticalHeader().setDefaultSectionSize(34)
        lay.addWidget(self.tabelle, 1)
        if not self.liste:
            lay.addWidget(QLabel("Diese Position hat keine Gewinde-Vorschläge, Senkungen, Fließlochbohrungen oder "
                                 "Bohrungen kleiner als 0,7 × Wandstärke."))
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
        for r in range(len(self.liste)):
            self._gewinde_platzhalter(r)
        self._auswirkung()

    def _preisfeld(self, wert, stamm=None, name=None):
        """Eingabe € je Stück: leer = Preis der Einstellungen (als graue Vorgabe), sonst nur für diese Position."""
        f = QLineEdit(zahl_als_text(wert, 2, tausender=False) if isinstance(wert, (int, float)) else "")
        f.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setFixedWidth(90)
        if name:
            f.setPlaceholderText(zahl_als_text(stamm, 2) if stamm is not None else "fehlt")
            f.setToolTip(f"€ je Stück für {name}; leer = Einstellungen › Zusatzarbeiten")
        f.textChanged.connect(self._auswirkung)
        return f

    def _gewinde_platzhalter(self, r):
        gp, gw = self.preise[r][0] if r < len(self.preise) else None, self.gewinde[r]
        if gp is None:
            return
        g = None if gw.currentText() == KEIN_GEWINDE else gw.currentText()
        stamm = self.stamm_gewinde.get(g) if g else None
        gp.setEnabled(bool(g))
        gp.setPlaceholderText(zahl_als_text(stamm, 2) if stamm is not None else ("fehlt" if g else ""))
        gp.setToolTip(f"€ je Gewinde {g}; leer = Einstellungen › Gewinde" if g else "")

    @staticmethod
    def _preis(feld):
        if feld is None or not feld.text().strip():
            return None
        try:
            w = float(feld.text().strip().replace(".", "").replace(",", ".") if "," in feld.text()
                      else feld.text().strip())
        except ValueError:
            return None
        return w if w >= 0 else None

    def werte(self):
        """Bohrbild nach der Wahl im Dialog."""
        out = []
        for z, gruppe, gw, ls, (gp, ap) in zip(self.liste, self.gruppen, self.gewinde, self.laser, self.preise):
            z = dict(z)
            if gp is not None:
                z["gewinde_preis"] = self._preis(gp)
            if ap is not None:
                z["preis"] = self._preis(ap)
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

    def setzen(self, nr, status=None, gewinde=None, laser=None, gravur=None, preis=None, gewinde_preis=None):
        """Zeile nr ohne Maus setzen (Tests, Bildschirmfotos); preis/gewinde_preis als Text, '' = Einstellungen."""
        if preis is not None:
            self.preise[nr][1].setText(preis)
        if gewinde_preis is not None:
            self.preise[nr][0].setText(gewinde_preis)
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
        felder = bohrbild.anwenden(self.p, neu, self.hand.text(), self.katalog, self.saetze)
        teile = []
        for name, titel, einheit, stellen in (("schneidweg", "Schneidweg", " mm", 1), ("gravur", "Gravur", " mm", 1),
                                              ("einstiche", "Einstiche", "", 0)):
            if name in felder:
                alt, wert = self.p.get(name) or 0, felder[name] or 0
                teile.append(f"{titel} {zahl_als_text(alt, stellen)} → {zahl_als_text(wert, stellen)}{einheit}")
        g_preise = dict(self.stamm_gewinde, **bohrbild.gewinde_preise(neu))
        g_tab = [dict(gewinde=g, preis=w) for g, w in g_preise.items()]
        g_eur = rechnen.gewinde_preis(felder.get("gewinde"), g_tab) if felder.get("gewinde") else 0
        teile.append("Gewinde: " + (f"{felder['gewinde']} = {zahl_als_text(g_eur, 2)} €" if felder.get("gewinde")
                                    else "keine"))
        if self.katalog is not None:
            a_preise = dict(self.stamm_arbeit, **bohrbild.arbeit_preise(neu))
            arbeiten = bohrbild.arbeiten(neu)
            teile.append("Zusatzarbeiten: " + (", ".join(
                f"{n}× {name} à {zahl_als_text(a_preise.get(name) or 0, 2)} €" for name, n in arbeiten.items())
                or "keine"))
            if felder.get("_fehlt"):
                teile.append(f"<span style='color:#B42318'>{', '.join(felder['_fehlt'])} fehlt in den Stammdaten "
                             "Zusatzarbeiten</span>")
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
