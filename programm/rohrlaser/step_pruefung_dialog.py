"""Fenster „STEP-Merkmale prüfen“ (step_pruefung.py): Status je Merkmal, Rohdaten der Messung und Korrekturen."""
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout)

from . import step_pruefung

FARBE = {step_pruefung.SICHER: "#E3F4E8", step_pruefung.PRUEFEN: "#FFF6DB", step_pruefung.NICHT: "#FDECEA"}


def _tabelle(titel, zeilen):
    t = QTableWidget(len(zeilen), len(titel))
    t.setHorizontalHeaderLabels(titel)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    for r, z in enumerate(zeilen):
        for c, w in enumerate(z):
            t.setItem(r, c, QTableWidgetItem("" if w is None else str(w)))
    return t


class MerkmaleDialog(QDialog):
    def __init__(self, parent, p):
        super().__init__(parent)
        d = step_pruefung.lesen(p.get("step_merkmale")) or {}
        self.daten = d
        self.bestaetigt = False
        self.setWindowTitle(f"STEP-Merkmale – Pos. {p.get('pos') or ''} {p.get('artikel') or ''}")
        self.resize(900, 460)
        m = d.get("merkmale") or []
        self.merkmale = _tabelle(("Merkmal", "Wert", "Status", "Grund / Annahme"),
                                 [(x["merkmal"], x["wert"], x["status"], x["grund"]) for x in m])
        for r, x in enumerate(m):
            self.merkmale.item(r, 2).setBackground(QBrush(QColor(FARBE.get(x["status"], "#FFFFFF"))))
        self.korrekturen = _tabelle(("Zeitpunkt", "Feld", "gemessen bzw. vorher", "von Hand"),
                                    [(k["am"], k["feld"], k["alt"], k["neu"]) for k in d.get("korrekturen") or ()])
        self.roh = _tabelle(("Messwert", "Wert"), sorted((d.get("roh") or {}).items()))
        reiter = QTabWidget()
        reiter.addTab(self.merkmale, "Merkmale")
        reiter.addTab(self.korrekturen, f"Korrekturen ({len(d.get('korrekturen') or ())})")
        reiter.addTab(self.roh, "Rohdaten der Messung")
        g = d.get("geprueft")
        self.info = QLabel(f"Datei {d.get('datei') or ''}, importiert {d.get('am') or ''}. "
                           f"Stand: {step_pruefung.kurztext(m)}."
                           + (f" Von Hand geprüft am {g['am']} {g.get('wer') or ''}." if g else ""))
        self.info.setWordWrap(True)
        kn = QHBoxLayout()
        self.pruefen_knopf = QPushButton("Alle Merkmale geprüft")
        self.pruefen_knopf.setToolTip("Bestätigt, dass die offenen Merkmale geprüft sind (Angebots-Check zählt sie "
                                      "dann nicht mehr). Messwerte und Korrekturen bleiben.")
        self.pruefen_knopf.clicked.connect(self.bestaetigen)
        self.pruefen_knopf.setEnabled(not g)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.reject)
        kn.addWidget(self.pruefen_knopf)
        kn.addStretch(1)
        kn.addWidget(zu)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(reiter, 1)
        lay.addLayout(kn)

    def bestaetigen(self):
        self.bestaetigt = True
        self.accept()
