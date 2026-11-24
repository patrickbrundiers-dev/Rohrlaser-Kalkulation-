"""Datei → „Preis-Simulator …“ (preis_simulator.py, Plan 29.10.2026 neue Idee 3).

Oben das Szenario (Material je Kategorie in %, Maschinenstundensatz in €/h, weitere Stundensätze und Zukaufteile in
%), darunter je offenes Angebot Verkaufspreis vorher/nachher und die Differenz, mit Admin-Rechten auch die Margen
(Plan „Margen nur Admin“). Nichts wird gespeichert; Doppelklick öffnet das Angebot."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import preis_simulator as ps
from . import stil
from .ausgabe import euro_text
from .stammdaten import KATEGORIEN

SPALTEN = ("Nummer", "Kunde", "Vorgang", "Verkauf\nvorher [€]", "Verkauf\nnachher [€]", "Differenz\n[€]")
SPALTEN_ADMIN = ("Marge\nvorher", "Marge bei\ngleichem Preis", "Marge mit\nneuem Preis")


def _prozent(w):
    return "" if w is None else f"{w * 100:.1f} %".replace(".", ",")


def _feld(von, bis, schritt, einheit):
    f = QDoubleSpinBox()
    f.setRange(von, bis)
    f.setDecimals(1)
    f.setSingleStep(schritt)
    f.setSuffix(f" {einheit}")
    f.setAccelerated(True)
    return f


class PreisSimulatorDialog(QDialog):
    """Was-wäre-wenn für offene Angebote."""

    def __init__(self, fenster, admin=None):
        super().__init__(fenster)
        self.f = fenster
        self.admin = bool(getattr(getattr(fenster, "bereich", None), "admin", False)) if admin is None else admin
        self.zeilen, self.summen = [], {}
        self.setWindowTitle("Preis-Simulator")
        self.resize(1000, 600)
        hinweis = QLabel("Was wäre, wenn Material oder Stundensätze teurer werden? Gerechnet werden die offenen "
                         "Angebote (Entwurf und Verschickt) mit ihren festgeschriebenen Preisen und dem gespeicherten "
                         "Schnittplan, einmal wie sie sind und einmal mit den Änderungen unten. Es wird nichts "
                         "gespeichert.")
        hinweis.setWordWrap(True)
        self.material = {}
        form_m = QFormLayout()
        for kat in KATEGORIEN:
            self.material[kat] = _feld(-50, 200, 1, "%")
            form_m.addRow(f"Material {kat}", self.material[kat])
        form_s = QFormLayout()
        self.maschine = _feld(-100, 500, 5, "€/h")
        self.saetze = _feld(-50, 200, 1, "%")
        self.zukauf = _feld(-50, 200, 1, "%")
        form_s.addRow("Stundensatz Maschine", self.maschine)
        form_s.addRow("weitere Stundensätze", self.saetze)
        form_s.addRow("Zukaufteile (Einkauf)", self.zukauf)
        self.beauftragt = QCheckBox("auch beauftragte Angebote")
        self.beauftragt.setToolTip("Beauftragte Angebote zeigen, wie viel Marge eine Preiserhöhung bei schon "
                                   "zugesagten Preisen kostet.")
        form_s.addRow("", self.beauftragt)
        oben = QHBoxLayout()
        for form in (form_m, form_s):
            w = QWidget()
            w.setLayout(form)
            oben.addWidget(w)
        oben.addStretch(1)
        self.knopf = QPushButton("Rechnen")
        self.knopf.setDefault(True)
        self.knopf.clicked.connect(self.rechnen)
        zuruecksetzen = QPushButton("Zurücksetzen")
        zuruecksetzen.clicked.connect(self.zuruecksetzen)
        knoepfe_oben = QVBoxLayout()
        knoepfe_oben.addWidget(self.knopf)
        knoepfe_oben.addWidget(zuruecksetzen)
        knoepfe_oben.addStretch(1)
        oben.addLayout(knoepfe_oben)
        self.ergebnis_text = QLabel("Änderungen eintragen und „Rechnen“ wählen.")
        self.ergebnis_text.setWordWrap(True)
        self.ergebnis_text.setTextFormat(Qt.RichText)
        spalten = SPALTEN + (SPALTEN_ADMIN if self.admin else ())
        self.tabelle = QTableWidget(0, len(spalten))
        self.tabelle.setHorizontalHeaderLabels(spalten)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.verticalHeader().hide()
        self.tabelle.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabelle.doubleClicked.connect(self._oeffnen)
        unten = QDialogButtonBox()
        unten.addButton("Schließen", QDialogButtonBox.RejectRole)
        unten.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(hinweis)
        lay.addLayout(oben)
        lay.addWidget(self.ergebnis_text)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(unten)

    def szenario(self):
        return dict(material={k: f.value() for k, f in self.material.items() if f.value()},
                    maschine=self.maschine.value(), saetze=self.saetze.value(), zukauf=self.zukauf.value())

    def zuruecksetzen(self):
        for f in (*self.material.values(), self.maschine, self.saetze, self.zukauf):
            f.setValue(0)
        self.rechnen()

    def rechnen(self):
        sz = self.szenario()
        vorgaenge = ps.MIT_BEAUFTRAGT if self.beauftragt.isChecked() else ps.OFFEN
        self.setCursor(Qt.WaitCursor)
        try:
            self.zeilen, self.summen = ps.simulieren(self.f.db, sz, vorgaenge)
        finally:
            self.unsetCursor()
        self._zeigen(sz)

    def _zeigen(self, sz):
        s = self.summen
        text = (f"<b>{ps.szenario_text(sz)}</b>: {s['angebote']} Angebote, Verkaufspreis "
                f"{euro_text(s['verkauf_vorher'])} € → {euro_text(s['verkauf_nachher'])} € "
                f"({'+' if s['diff'] >= 0 else ''}{euro_text(s['diff'])} €)")
        if self.admin and s.get("marge_vorher") is not None:
            text += (f"; Marge {_prozent(s['marge_vorher'])}, bei gleichem Preis {_prozent(s['marge_gleich'])}, "
                     f"mit neuem Preis {_prozent(s['marge_neu'])}")
        if s.get("ohne"):
            text += f". {s['ohne']} Angebot(e) ohne Rechnung (z. B. nicht optimiert)"
        self.ergebnis_text.setText(text)
        self.tabelle.setRowCount(0)
        rot = QBrush(stil.farbe("#B42318"))
        for r in self.zeilen:
            werte = [r.get("nummer") or "", r.get("kunde") or "", r.get("vorgang") or ""]
            if "vorher" in r:
                werte += [euro_text(r["vorher"]["verkauf"]), euro_text(r["nachher"]["verkauf"]),
                          ("+" if r["diff"] > 0 else "") + euro_text(r["diff"])]
                if self.admin:
                    werte += [_prozent(r["marge_vorher"]), _prozent(r["marge_gleich"]), _prozent(r["marge_neu"])]
            else:
                werte += [r.get("fehlt") or "", "", ""] + (["", "", ""] if self.admin else [])
            self._zeile(werte, r["id"], rot if r.get("diff", 0) > 0.005 else None)
        summe = ["Summe", f"{s['angebote']} Angebote", "", euro_text(s["verkauf_vorher"]),
                 euro_text(s["verkauf_nachher"]), ("+" if s["diff"] > 0 else "") + euro_text(s["diff"])]
        if self.admin:
            summe += [_prozent(s["marge_vorher"]), _prozent(s["marge_gleich"]), _prozent(s["marge_neu"])]
        self._zeile(summe, None, None, fett=True)
        self.tabelle.resizeColumnsToContents()
        self.tabelle.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    def _zeile(self, werte, angebot_id, farbe, fett=False):
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        for c, w in enumerate(werte):
            it = QTableWidgetItem(str(w))
            it.setData(Qt.UserRole, angebot_id)
            if c >= 3:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if farbe is not None and c == 5:
                it.setForeground(farbe)
            if fett:
                font = QFont(it.font())
                font.setBold(True)
                it.setFont(font)
            self.tabelle.setItem(r, c, it)

    def _oeffnen(self, index):
        it = self.tabelle.item(index.row(), 0)
        a = it.data(Qt.UserRole) if it else None
        if a is not None:
            self.f.angebot_oeffnen(a)
            self.accept()
