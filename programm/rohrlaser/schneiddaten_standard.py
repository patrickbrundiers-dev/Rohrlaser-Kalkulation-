"""Schneiddaten auf Standard zurücksetzen (Patrick 29.10.2026): Vergleich der Tabelle mit den mitgelieferten
Richtwerten (stammdaten.beispiel_schneiddaten) und der Dialog mit Vorschau.

Umfang: alle Maschinen mit Richtwerten (stammdaten.LASER), eine Maschine oder nur die markierten Zeilen. Eine Zeile
gehört zum Standard, wenn Maschine, Kategorie, Gas und 'Wandstärke bis' einer Richtwertzeile gleichen und die
Werkstoff-ID leer ist; ihre Werte werden auf den Standard gesetzt. Eigene Zeilen (werkstoffgenau oder ohne passende
Richtwertzeile) werden beim Zurücksetzen einer Maschine entfernt, außer 'eigene Zeilen behalten'; fehlende
Standardzeilen kommen dazu. Bei 'nur markierte Zeilen' wird nichts entfernt und nichts ergänzt."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QLabel, QMessageBox, QRadioButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from . import stil
from .stammdaten import LASER
# Vergleich ohne Qt (Audit 26.11.2026, A-01): hier weitergeführt
from .schneiddaten_werte import (TITEL, WERTE, _leer, abweichungen, gleich, schluessel, standard_je_schluessel,  # noqa: F401
                                 standard_zeilen, vergleich, vorschau_zeilen, wert_text, zeile_text, zusammenfassung)


class StandardDialog(QDialog):
    """Umfang wählen, Vorschau prüfen, dann 'Zurücksetzen …' (mit letzter Rückfrage, Vorwahl Nein). Ergebnis in
    self.wahl = dict(maschinen, ids, eigene_behalten) oder None."""
    SPALTEN = ("Zeile", "Was", "Jetzt", "Standard")

    def __init__(self, eltern, aktuell, markiert=(), stumm=False):
        super().__init__(eltern)
        self.aktuell, self.markiert, self.stumm = aktuell, list(markiert), stumm
        self.wahl = None
        self.setWindowTitle("Schneiddaten auf Standard zurücksetzen")
        self.resize(760, 520)
        oben = QLabel("Die mitgelieferten Richtwerte (Rohr-Schnitttabellen, keine Herstellerwerte) gibt es für "
                      f"{', '.join(f'{m} ({laser})' for m, laser in LASER.items())}. Vorher wird automatisch eine "
                      "Datensicherung angelegt (zurückholen mit „Sicherung wiederherstellen …“).")
        oben.setWordWrap(True)
        self.alle = QRadioButton(f"Alle Maschinen ({', '.join(LASER)})")
        self.eine = QRadioButton("Eine Maschine")
        self.maschine = QComboBox()
        self.maschine.addItems([f"{m} ({laser}-Laser)" for m, laser in LASER.items()])
        self.nur_markiert = QRadioButton(f"Nur die markierten Zeilen ({len(self.markiert)})")
        self.nur_markiert.setEnabled(bool(self.markiert))
        self.gruppe = QButtonGroup(self)
        for b in (self.alle, self.eine, self.nur_markiert):
            self.gruppe.addButton(b)
        (self.nur_markiert if self.markiert else self.alle).setChecked(True)
        self.behalten = QCheckBox("Eigene Zeilen behalten")
        self.behalten.setToolTip("Zeilen je Werkstoff und andere eigene Zeilen bleiben, nur die Standardzeilen werden "
                                 "zurückgesetzt")
        eine = QHBoxLayout()
        eine.addWidget(self.eine)
        eine.addWidget(self.maschine)
        eine.addStretch(1)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.tabelle = QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabelle.verticalHeader().hide()
        self.tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        knoepfe = QDialogButtonBox()
        self.ok = knoepfe.addButton("Zurücksetzen …", QDialogButtonBox.AcceptRole)
        knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        self.ok.clicked.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(oben)
        lay.addWidget(self.alle)
        lay.addLayout(eine)
        lay.addWidget(self.nur_markiert)
        lay.addWidget(self.behalten)
        lay.addWidget(self.text)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(knoepfe)
        for b in (self.alle, self.eine, self.nur_markiert):
            b.toggled.connect(self._zeigen)
        self.maschine.currentIndexChanged.connect(lambda *_: (self.eine.setChecked(True), self._zeigen()))
        self.behalten.toggled.connect(self._zeigen)
        self._zeigen()

    def umfang(self):
        """dict(maschinen, ids, eigene_behalten) der aktuellen Wahl."""
        if self.nur_markiert.isChecked():
            return dict(maschinen=None, ids=self.markiert, eigene_behalten=True)
        maschinen = list(LASER) if self.alle.isChecked() else [list(LASER)[self.maschine.currentIndex()]]
        return dict(maschinen=maschinen, ids=None, eigene_behalten=self.behalten.isChecked())

    def _zeigen(self, *_):
        u = self.umfang()
        self.behalten.setEnabled(u["ids"] is None)
        self.v = vergleich(self.aktuell, **u)
        self.text.setText(zusammenfassung(self.v))
        zeilen = vorschau_zeilen(self.v)
        self.tabelle.setRowCount(len(zeilen))
        for i, werte in enumerate(zeilen):
            for j, w in enumerate(werte):
                item = QTableWidgetItem(w)
                if j == 3:
                    item.setBackground(stil.farbe_fest("#FCE4D6" if w == "wird entfernt" else "#E2F0D9"))
                self.tabelle.setItem(i, j, item)
        self.tabelle.resizeColumnsToContents()
        self.tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ok.setEnabled(bool(self.v["aendern"] or self.v["entfernen"] or self.v["ergaenzen"]))

    def bestaetigung_text(self):
        v = self.v
        return (f"Schneiddaten von {', '.join(v['maschinen']) or '–'} auf Standard zurücksetzen?\n\n"
                + zusammenfassung(v) + "\n\nVorher wird eine Datensicherung angelegt. Angebote mit "
                "festgeschriebenen Preisen rechnen mit ihren gespeicherten Schneiddaten weiter.")

    def _ok(self):
        if not self.stumm and QMessageBox.question(
                self, "Schneiddaten zurücksetzen", self.bestaetigung_text(),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.wahl = self.umfang()
        self.accept()


def dialog_zeigen(eltern, aktuell, markiert=()):
    """Dialog öffnen; Ergebnis die Wahl (dict) oder None."""
    d = StandardDialog(eltern, aktuell, markiert)
    d.setAttribute(Qt.WA_DeleteOnClose, False)
    return d.wahl if d.exec() == QDialog.Accepted else None
