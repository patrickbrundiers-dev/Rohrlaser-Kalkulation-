"""Fenster „Schneiddaten aus Nachkalkulation kalibrieren“ (kalibrierung.py, D1 MACH-005, D3 MACH-004): Vorschläge je
Wandstufe und je Wandbereich mit Faktor, Fällen, Bandbreite und den neuen Vorschüben; übernommen wird nur mit dem
Knopf „Übernehmen“ (Quelle Nachkalkulation, Historie unter Kennwerte, dort zurücknehmbar)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import VERSION, kalibrierung as kb, rechnen, stil
from .eingabe import RechenSpinGanz
from .stil import GELB_FLAECHE, TEXT_GRAU

SPALTEN = ("Art", "Maschine", "Werkstoff", "Wand", "Gas", "Faktor Ist ÷ Soll", "Bandbreite", "Fälle", "Vorschub groß "
           "alt → neu [mm/min]", "Status")
B_SPALTEN = (("Maschine – Werkstoff", "Teile", "Soll [h]", "Ist [h]", "Abweichung vorher → nachher")
             + tuple(f"{t} (Anteil)" for t in rechnen.BAUSTEIN_TEXT.values()) + ("Status",))


def _z(w, n=2):
    return "" if w is None else f"{w:.{n}f}".replace(".", ",")


class KalibrierDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db, self.geaendert = db, False
        self.setWindowTitle("Schneiddaten aus Nachkalkulation kalibrieren")
        self.resize(1200, 760)
        lay = QVBoxLayout(self)
        info = QLabel("Je Schneiddaten-Zeile (Wandstufe) und je Wandbereich: Faktor = Median der Laufzeit Ist ÷ Soll "
                      "aus der Nachkalkulation, Ausreißer zählen nicht; Bandbreite = 10. bis 90. Perzentil. Faktor "
                      "1,10 = in der Fertigung 10 % länger, die Vorschübe werden ÷ 1,10 kleiner. Geändert wird nur "
                      "mit „Übernehmen“; die Zeile bekommt die Quelle „Nachkalkulation“, die Freigabe steht unter "
                      "Kennwerte und lässt sich dort zurücknehmen.")
        info.setWordWrap(True)
        lay.addWidget(info)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Mindestens Fälle:"))
        self.mindest = RechenSpinGanz()
        self.mindest.setRange(1, 100)
        self.mindest.setValue(kb.MINDESTENS)
        self.mindest.valueChanged.connect(self.neu_laden)
        zeile.addWidget(self.mindest)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.tab = QTableWidget(0, len(SPALTEN))
        self.tab.setHorizontalHeaderLabels(SPALTEN)
        self.tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tab.verticalHeader().setVisible(False)
        self.tab.horizontalHeader().setStretchLastSection(True)
        self.tab.itemSelectionChanged.connect(self._gewaehlt)
        lay.addWidget(self.tab, 1)
        zeile = QHBoxLayout()
        self.uebernehmen_knopf = QPushButton("Übernehmen")
        self.uebernehmen_knopf.setToolTip("Vorschübe der gewählten Zeile(n) ÷ Faktor, Quelle Nachkalkulation")
        self.uebernehmen_knopf.clicked.connect(lambda: self.uebernehmen())
        zeile.addWidget(self.uebernehmen_knopf)
        self.meldung = QLabel()
        zeile.addWidget(self.meldung, 1)
        lay.addLayout(zeile)
        # Phase 4 E7: Laserzeit je Baustein (Schneiden, Einstechen, Ecken, Verfahren, Nebenzeit) je Maschine
        info2 = QLabel(f"Laserzeit je Baustein: je Maschine ein Faktor für Schneiden, Einstechen, Ecken und Radien, "
                       f"Verfahren und Drehen sowie Nebenzeit und Messen, angepasst an die Ist-Laufzeiten je Teil "
                       f"(kleinste Quadrate, nur positive Faktoren, ab {kb.MINDESTENS_BAUSTEINE} Teilen je Maschine). "
                       f"Bausteine unter 2 % der Zeit bleiben. Vorschau: alter → neuer Faktor; geändert wird nur mit "
                       f"„Faktoren übernehmen“ (Maschinenfelder, zurücknehmen unter Kennwerte).")
        info2.setWordWrap(True)
        lay.addWidget(info2)
        self.btab = QTableWidget(0, len(B_SPALTEN))
        self.btab.setHorizontalHeaderLabels(B_SPALTEN)
        self.btab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.btab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.btab.setSelectionMode(QAbstractItemView.SingleSelection)
        self.btab.verticalHeader().setVisible(False)
        self.btab.horizontalHeader().setStretchLastSection(True)
        self.btab.itemSelectionChanged.connect(self._b_gewaehlt)
        lay.addWidget(self.btab, 1)
        zeile = QHBoxLayout()
        self.b_knopf = QPushButton("Faktoren übernehmen")
        self.b_knopf.setToolTip("Faktoren je Baustein in die gewählte Maschine schreiben")
        self.b_knopf.clicked.connect(lambda: self.uebernehmen_bausteine())
        zeile.addWidget(self.b_knopf)
        self.b_meldung = QLabel()
        zeile.addWidget(self.b_meldung, 1)
        lay.addLayout(zeile)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.neu_laden()

    def neu_laden(self):
        self.vorschlaege = kb.vorschlaege(self.db, self.mindest.value())
        self.tab.setRowCount(len(self.vorschlaege))
        for r, v in enumerate(self.vorschlaege):
            s = list(v["schluessel"])
            wand = f"≤ {_z(s[2], 1)} mm" if v["quelle"] == kb.QUELLE_TEIL else s[2]
            gas = s[3] if v["quelle"] == kb.QUELLE_TEIL else "alle"
            b = v.get("band")
            vor = "; ".join(f"{_z(a, 0)} → {_z(n, 0)}" for _, _, a, n in v["zeilen"][:4] if a is not None)
            werte = (v["art"], s[0], s[1], wand, gas, _z(v["faktor"], 3),
                     f"{_z(b[0], 2)}–{_z(b[1], 2)}" if b else "", str(v["n"]), vor, v["status"])
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                if c in (5, 6, 7):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if v["status"] != "ok":
                    it.setForeground(QBrush(stil.farbe(TEXT_GRAU)))
                elif v["faktor"] and abs(v["faktor"] - 1) >= 0.1:
                    it.setBackground(QBrush(stil.farbe(GELB_FLAECHE)))
                self.tab.setItem(r, c, it)
        self.tab.resizeColumnsToContents()
        self.meldung.setText("" if self.vorschlaege else "Noch keine Laufzeiten je Teil in der Nachkalkulation erfasst.")
        self._gewaehlt()
        self.b_laden()

    def b_laden(self):
        self.bausteine = kb.vorschlaege_bausteine(self.db)
        self.btab.setRowCount(len(self.bausteine))
        for r, v in enumerate(self.bausteine):
            werte = [v["maschine"] + (f" – {v['kategorie']}" if v.get("kategorie") else " – allgemein (Stahl)"),
                     str(v["n"]), _z(v["soll_h"], 2), _z(v["ist_h"], 2),
                     f"{_z(100 * v['vorher'], 0)} % → {_z(100 * v['nachher'], 0)} %" if v["nachher"] is not None
                     else (f"{_z(100 * v['vorher'], 0)} %" if v["vorher"] is not None else "")]
            for b in rechnen.BAUSTEINE:
                pfeil = f"{_z(v['alt'][b], 2)} → {_z(v['neu'][b], 2)}" if b in v["frei"] else _z(v["alt"][b], 2)
                werte.append(f"{pfeil} ({_z(100 * v['anteil'][b], 0)} %)")
            werte.append(v["status"])
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                if 0 < c < len(werte) - 1:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if v["status"] != "ok":
                    it.setForeground(QBrush(stil.farbe(TEXT_GRAU)))
                self.btab.setItem(r, c, it)
        self.btab.resizeColumnsToContents()
        self.b_meldung.setText("" if self.bausteine else "Noch keine Laufzeiten je Teil mit Bausteinen erfasst (ab "
                               "16.11.2026 gespeicherte Nachkalkulationen).")
        self._b_gewaehlt()

    def _b_gewaehlt(self):
        r = self.btab.currentRow()
        self.b_knopf.setEnabled(0 <= r < len(self.bausteine) and self.bausteine[r]["status"] == "ok")

    def uebernehmen_bausteine(self, zeile=None):
        """Faktoren je Baustein der gewählten Maschine übernehmen (zeile für Tests). Ergebnis: ID der Historie."""
        r = self.btab.currentRow() if zeile is None else zeile
        if not 0 <= r < len(self.bausteine):
            self.b_meldung.setText("Bitte eine Maschine wählen.")
            return None
        try:
            hid = kb.uebernehmen_bausteine(self.db, self.bausteine[r], VERSION)
        except ValueError as e:
            self.b_meldung.setText(str(e))
            return None
        self.geaendert = True
        self.b_laden()
        self.b_meldung.setText("Übernommen – Faktoren je Baustein in der Maschine (zurücknehmen unter Kennwerte).")
        return hid

    def _gewaehlt(self):
        r = self.tab.currentRow()
        self.uebernehmen_knopf.setEnabled(0 <= r < len(self.vorschlaege) and self.vorschlaege[r]["status"] == "ok")

    def uebernehmen(self, zeile=None):
        """Gewählten Vorschlag übernehmen (zeile für Tests). Ergebnis: ID der Historie oder None."""
        r = self.tab.currentRow() if zeile is None else zeile
        if not 0 <= r < len(self.vorschlaege):
            self.meldung.setText("Bitte einen Vorschlag wählen.")
            return None
        try:
            hid = kb.uebernehmen(self.db, self.vorschlaege[r], VERSION)
        except ValueError as e:
            self.meldung.setText(str(e))
            return None
        self.geaendert = True
        self.neu_laden()
        self.meldung.setText("Übernommen – Vorschübe geändert, Quelle Nachkalkulation (zurücknehmen unter Kennwerte).")
        return hid
