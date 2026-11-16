"""Fenster „Gemeinsamen Ordner prüfen“ (Datei-Menü, Patrick 31.10.2026, Paket A): Befunde aus ordner_pruefung als
Liste mit Symbol, Ergebnis und „Was tun“; eigene Konfliktkopien aufräumen, Ordner öffnen, Bericht kopieren."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import ordner_pruefung, stil, teilen

FARBE = {ordner_pruefung.OK: stil.GRUEN, ordner_pruefung.HINWEIS: stil.ORANGE, ordner_pruefung.FEHLER: stil.ROT}


class OrdnerPruefenDialog(QDialog):
    def __init__(self, fenster):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.befunde = []
        self.setWindowTitle("Gemeinsamen Ordner prüfen")
        self.resize(900, 480)
        lay = QVBoxLayout(self)
        self.kopf = QLabel()
        self.kopf.setWordWrap(True)
        self.kopf.setTextFormat(Qt.PlainText)
        lay.addWidget(self.kopf)
        self.liste = QTableWidget(0, 3)
        self.liste.setHorizontalHeaderLabels(["Prüfung", "Ergebnis", "Was tun"])
        self.liste.verticalHeader().setVisible(False)
        self.liste.setWordWrap(True)
        self.liste.setAlternatingRowColors(True)
        self.liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        kopf = self.liste.horizontalHeader()
        kopf.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(1, QHeaderView.Stretch)
        kopf.setSectionResizeMode(2, QHeaderView.Stretch)
        lay.addWidget(self.liste, 1)
        zeile = QHBoxLayout()
        self.neu = QPushButton("Erneut prüfen")
        self.neu.clicked.connect(self.pruefen)
        self.aufraeumen = QPushButton("Eigene aufräumen")
        self.aufraeumen.setToolTip("Eigene Konfliktkopien in den lokalen Ordner Daten/Teilen/Konfliktkopien legen und "
                                   "liegengebliebene Zwischendateien (*.neu) löschen")
        self.aufraeumen.clicked.connect(self._aufraeumen)
        self.oeffnen = QPushButton("Ordner öffnen")
        self.oeffnen.clicked.connect(self._oeffnen)
        self.kopieren = QPushButton("Bericht kopieren")
        self.kopieren.clicked.connect(self._kopieren)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        for b in (self.neu, self.aufraeumen, self.oeffnen, self.kopieren):
            zeile.addWidget(b)
        zeile.addStretch(1)
        zeile.addWidget(zu)
        lay.addLayout(zeile)
        self.pruefen()

    def pruefen(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.befunde = ordner_pruefung.pruefen(self.db)
        finally:
            QApplication.restoreOverrideCursor()
        self.liste.setRowCount(0)
        for b in self.befunde:
            z = self.liste.rowCount()
            self.liste.insertRow(z)
            for sp, text in enumerate((f"{ordner_pruefung.SYMBOL[b['stufe']]}  {b['titel']}", b["text"], b["tun"])):
                it = QTableWidgetItem(text)
                it.setToolTip(b["text"] + (f"\n→ {b['tun']}" if b["tun"] else ""))
                if sp == 0:
                    it.setForeground(stil.farbe(FARBE[b["stufe"]]))
                self.liste.setItem(z, sp, it)
        self.liste.resizeRowsToContents()
        fehler = sum(1 for b in self.befunde if b["stufe"] == ordner_pruefung.FEHLER)
        hinweise = sum(1 for b in self.befunde if b["stufe"] == ordner_pruefung.HINWEIS)
        if fehler or hinweise:
            self.kopf.setText(f"{fehler} Fehler, {hinweise} Hinweise. Die Spalte „Was tun“ sagt, wie es weitergeht.")
        else:
            self.kopf.setText("Alles in Ordnung: der gemeinsame Ordner arbeitet wie er soll.")
        self.aufraeumen.setEnabled(self._eigenes())
        self.oeffnen.setEnabled(teilen.ordner(self.db) is not None)

    def _eigenes(self):
        """Gibt es eigene Konfliktkopien oder liegengebliebene eigene Zwischendateien?"""
        w, k = teilen.weg(self.db), teilen.kuerzel(self.db)
        if w is None or not k or not w.erreichbar():
            return False
        try:
            return any(c["eigene"] for c in teilen.konfliktkopien(self.db)) or bool(w.reste(k))
        except OSError:
            return False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.liste.resizeRowsToContents()

    def _aufraeumen(self):
        n = teilen.kopien_aufraeumen(self.db)
        self.f.meldung(f"Gemeinsamer Ordner: {n} eigene Konfliktkopien bzw. Zwischendateien aufgeräumt." if n else
                       "Gemeinsamer Ordner: nichts Eigenes zum Aufräumen (fremde räumt der Kollege selbst auf).")
        self.pruefen()

    def _oeffnen(self):
        o = teilen.ordner(self.db)
        if o is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(o)))

    def _kopieren(self):
        QApplication.clipboard().setText(f"Gemeinsamer Ordner: {teilen.ordner(self.db)}\n"
                                         + ordner_pruefung.bericht_text(self.befunde))
        self.f.meldung("Prüfbericht kopiert.")


def zeigen(fenster):
    d = OrdnerPruefenDialog(fenster)
    if not fenster.stumm:
        d.exec()
    return d
