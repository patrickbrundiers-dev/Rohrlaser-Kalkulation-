"""Normteile ohne Preis gesammelt nachtragen (Vorschlag M6, Patrick 07.11.2026): Unterreiter der Zukaufartikel mit allen
Normteilen (Kategorie Normteile bzw. Artikeltyp Normteil) ohne Einkaufspreis. Der EK wird direkt in der Zeile
eingetragen; „Speichern“ schreibt alle eingetragenen Preise auf einmal (db.zukauf_ek_eintragen, Protokoll der
Preisänderungen wie sonst). Der Angebots-Check nennt Normteile ohne Preis eines Angebots und springt hierher.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import zukauf

TITEL = "Normteile ohne Preis"


def ist_normteil(a):
    from .step import NORMTEIL_KATEGORIE, NORMTEIL_TYP
    return a.get("kategorie") == NORMTEIL_KATEGORIE or a.get("artikeltyp") == NORMTEIL_TYP


def ohne_preis(db):
    """Normteil-Artikel (nicht archiviert) ohne Einkaufspreis, nach Bezeichnung."""
    return sorted((a for a in db.zukauf_artikel_liste() if ist_normteil(a) and a.get("status") != "archiviert"
                   and zukauf.ek_fehlt(a)), key=lambda a: (a.get("bezeichnung") or "").casefold())


def ids_ohne_preis(db):
    return {a["id"] for a in ohne_preis(db)}


class NormteilPreisSeite(QWidget):
    """Liste der Normteile ohne EK mit Eingabefeld je Zeile und „Speichern“."""
    titel = TITEL
    SPALTEN = ("Bezeichnung", "Artikelnummer", "Lieferant", "EK je Stück [€]", "Herkunft")

    def __init__(self, db, meldung):
        super().__init__()
        self.db, self.meldung = db, meldung
        self.artikel = []
        lay = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.tabelle = QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.verticalHeader().setDefaultSectionSize(28)
        for c, b in enumerate((260, 130, 150, 130)):
            self.tabelle.setColumnWidth(c, b)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tabelle, 1)
        unten = QHBoxLayout()
        unten.addStretch(1)
        self.speichern_knopf = QPushButton("Preise speichern")
        self.speichern_knopf.setToolTip("Alle eingetragenen Einkaufspreise speichern (Zeilen mit 0 € bleiben offen)")
        self.speichern_knopf.clicked.connect(lambda: self.speichern())
        unten.addWidget(self.speichern_knopf)
        lay.addLayout(unten)
        self.neu_laden()

    def neu_laden(self):
        self.artikel = ohne_preis(self.db)
        t = self.tabelle
        t.setRowCount(len(self.artikel))
        for r, a in enumerate(self.artikel):
            b = (a.get("bezuege") or [{}])[0]
            for c, w in enumerate((a.get("bezeichnung"), a.get("artikelnr"), b.get("lieferant"), None,
                                   a.get("herkunft"))):
                if c == 3:
                    continue
                it = QTableWidgetItem("" if w is None else str(w))
                it.setData(Qt.UserRole, a["id"])
                t.setItem(r, c, it)
            feld = QDoubleSpinBox()
            feld.setDecimals(zukauf.STELLEN_EINHEIT)
            feld.setRange(0, 1_000_000)
            feld.setSuffix(" €")
            feld.setSpecialValueText("–")
            t.setCellWidget(r, 3, feld)
        n = len(self.artikel)
        self.info.setText(
            f"{n} Normteil{'e' if n != 1 else ''} ohne Einkaufspreis. EK je Stück eintragen und „Preise speichern“: "
            "der Preis gilt dann in allen Angeboten (beim nächsten Import und beim Aktualisieren der Zukaufpreise)."
            if n else "Alle Normteile haben einen Einkaufspreis.")
        self.speichern_knopf.setEnabled(bool(n))
        if getattr(self, "nach_laden", None):
            self.nach_laden()

    def preis_setzen(self, zeile, preis):
        """Für Tests und Tastatur: EK der Zeile eintragen (noch nicht gespeichert)."""
        self.tabelle.cellWidget(zeile, 3).setValue(preis)

    def speichern(self):
        """Alle Zeilen mit EK über 0 € speichern. Ergebnis: Anzahl gespeicherter Preise."""
        n, fehler = 0, []
        for r, a in enumerate(self.artikel):
            preis = self.tabelle.cellWidget(r, 3).value()
            if preis <= 0:
                continue
            try:
                self.db.zukauf_ek_eintragen(a["id"], preis, bemerkung="Normteile ohne Preis")
                n += 1
            except ValueError as e:
                fehler.append(f"{a.get('bezeichnung')}: {e}")
        self.neu_laden()
        if n or fehler:
            self.meldung(f"{n} Normteil-Preis{'e' if n != 1 else ''} gespeichert."
                         + (" Nicht gespeichert: " + "; ".join(fehler) if fehler else ""), bool(fehler))
        return n
