"""Datei → „Maschinenauslastung …“ und Reiter Fertigung → „Auslastung …“ (auslastung.py, Plan 29.10.2026 2b).

Oben je Maschine und Woche Bedarf / Kapazität in Stunden mit Auslastung in % (ab 80 % gelb, über 100 % rot), darunter
die Aufträge der gewählten Zelle; Doppelklick öffnet das Angebot."""
import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QHeaderView, QLabel, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import auslastung, stil

FARBEN = {"gruen": "#E3F4E8", "gelb": "#FFF1C2", "rot": "#F8D4D0", "grau": "#F2F2F2"}


def _h(x):
    return f"{x:.1f}".replace(".", ",")


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return ""


class AuslastungDialog(QDialog):
    def __init__(self, fenster, heute=None):
        super().__init__(fenster)
        self.f, self.heute = fenster, heute
        self.daten = None
        self.setWindowTitle("Maschinenauslastung je Woche")
        self.resize(1100, 620)
        self.wochen = QSpinBox()
        self.wochen.setRange(2, 26)
        self.wochen.setValue(8)
        self.wochen.setSuffix(" Wochen")
        self.wochen.valueChanged.connect(lambda _w: self.laden())
        self.offene = QCheckBox("verschickte Angebote gewichtet mit der Trefferquote")
        self.offene.setToolTip("Verschickte Angebote zählen mit Maschinenzeit × Trefferquote der letzten 12 Monate "
                               "(Datei → Angebots-Auswertung); Termin aus ihrer Lieferzeit ab heute.")
        self.offene.toggled.connect(lambda _a: self.laden())
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Zeitraum"))
        oben.addWidget(self.wochen)
        oben.addWidget(self.offene)
        oben.addStretch(1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.RichText)
        self.tabelle = QTableWidget()
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.currentCellChanged.connect(lambda r, c, *_: self._details(r, c))
        self.details_titel = QLabel("Zelle wählen: die Aufträge dieser Woche und Maschine.")
        self.details = QTableWidget(0, 7)
        self.details.setHorizontalHeaderLabels(("Angebot", "Kunde", "Art", "Liefertermin", "Stunden", "geschnitten",
                                                "Gewicht"))
        self.details.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.details.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.details.verticalHeader().hide()
        self.details.doubleClicked.connect(self._oeffnen)
        knoepfe = QDialogButtonBox()
        knoepfe.addButton("Schließen", QDialogButtonBox.RejectRole)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.info)
        lay.addWidget(self.tabelle, 3)
        lay.addWidget(self.details_titel)
        lay.addWidget(self.details, 2)
        lay.addWidget(knoepfe)
        self.laden()

    def laden(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.daten = auslastung.berechnen(self.f.db, self.heute, self.wochen.value(), self.offene.isChecked())
        finally:
            QApplication.restoreOverrideCursor()
        d = self.daten
        t = self.tabelle
        t.clear()
        t.setRowCount(len(d["maschinen"]))
        t.setColumnCount(len(d["spalten"]))
        t.setHorizontalHeaderLabels([titel + (f"\n{m.strftime('%d.%m.')}" if m else "") for _, titel, m in d["spalten"]])
        t.setVerticalHeaderLabels(d["maschinen"])
        for r, m in enumerate(d["maschinen"]):
            for c, (s, _, mo) in enumerate(d["spalten"]):
                b = d["bedarf"].get((m, s), 0.0)
                k = d["kapazitaet"].get((m, s)) if mo else None
                q = auslastung.quote(b, k) if k is not None else None
                if mo:
                    text = f"{_h(b)} / {_h(k)} h" + (f"\n{q * 100:.0f} %" if q is not None else "\nkeine Schicht")
                else:
                    text = f"{_h(b)} h" if b else ""
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignCenter)
                farbe = None
                if q is not None and b:
                    farbe = "rot" if q > auslastung.ROT else "gelb" if q >= auslastung.GELB else "gruen"
                elif mo and k == 0 and b:
                    farbe = "rot"
                elif s == auslastung.UEBERFAELLIG and b:
                    farbe = "rot"
                elif not mo and b:
                    farbe = "grau"
                if farbe:
                    it.setBackground(QBrush(stil.farbe(FARBEN[farbe])))
                n = len(d["auftraege"].get((m, s), ()))
                it.setToolTip(f"{n} Auftrag/Aufträge" if n else "")
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.resizeRowsToContents()
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        voll = [(m, titel) for m in d["maschinen"] for s, titel, mo in d["spalten"]
                if mo and (auslastung.quote(d["bedarf"].get((m, s), 0), d["kapazitaet"].get((m, s))) or 0) > 1]
        text = ("Bedarf / Kapazität je Maschine und Woche: Laserzeit der beauftragten Aufträge in der Woche des "
                "Liefertermins minus Vorlauf, Kapazität aus dem Schichtkalender (Einstellungen → Lager und "
                "Fertigung, Maschinen).")
        if d["gewicht"] is not None:
            text += f" Verschickte Angebote zählen mit {d['gewicht'] * 100:.0f} %."
        if voll:
            text += " <b style='color:#B42318'>Überlastet: " + ", ".join(f"{m} {w}" for m, w in voll) + ".</b>"
        if d["fehlt"]:
            text += f" Ohne Rechnung: {', '.join(f'{n} ({g})' for n, g in d['fehlt'])}."
        self.info.setText(text)
        self._details(-1, -1)

    def _details(self, r, c):
        self.details.setRowCount(0)
        d = self.daten
        if not d or r < 0 or c < 0 or r >= len(d["maschinen"]) or c >= len(d["spalten"]):
            return
        m, (s, titel, _) = d["maschinen"][r], d["spalten"][c]
        liste = sorted(d["auftraege"].get((m, s), ()), key=lambda a: (str(a["termin"] or ""), str(a["nummer"])))
        n = f"{len(liste)} Auftrag" if len(liste) == 1 else f"{len(liste)} Aufträge"
        self.details_titel.setText(f"{m}, {titel}: {n}, {_h(sum(a['h'] for a in liste))} h")
        for a in liste:
            i = self.details.rowCount()
            self.details.insertRow(i)
            werte = (a["nummer"] or "", a["kunde"] or "", a["art"], _datum(a["termin"]), _h(a["h"]),
                     f"{a['geschnitten'] * 100:.0f} %" if a["geschnitten"] else "",
                     f"{a['gewicht'] * 100:.0f} %" if a["gewicht"] < 1 else "")
            for k, w in enumerate(werte):
                it = QTableWidgetItem(w)
                it.setData(Qt.UserRole, a["id"])
                if k >= 4:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.details.setItem(i, k, it)
        self.details.resizeColumnsToContents()
        self.details.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    def _oeffnen(self, index):
        it = self.details.item(index.row(), 0)
        if it is not None:
            self.f.angebot_oeffnen(it.data(Qt.UserRole))
            self.accept()
