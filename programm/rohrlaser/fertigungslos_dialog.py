"""Dialog „Fertigungslos …“ im Reiter Fertigung (fertigungslos.py, Plan ArTube-Unterlagen A2): Aufträge ankreuzen,
gemeinsam optimieren, Stangen im Los gegen einzeln vergleichen, Werkstattpapiere des Loses als PDF."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from . import fertigungslos
from .klartext import fehler_text


class FertigungslosDialog(QDialog):
    def __init__(self, parent, db, vorauswahl=()):
        super().__init__(parent)
        self.db = db
        self.los = None
        self.setWindowTitle("Fertigungslos – Aufträge gemeinsam schneiden")
        self.resize(640, 520)
        info = QLabel("Aufträge mit gleicher Maschine ankreuzen. Teile gleicher Abmessung teilen sich dann die "
                      "Stangen. Kundenmaterial und Muster bleiben im eigenen Auftrag. Die Angebotspreise ändern "
                      "sich nicht, das Los liefert nur die Werkstattpapiere.")
        info.setWordWrap(True)
        self.liste = QListWidget()
        for z in fertigungslos.kandidaten(db):
            it = QListWidgetItem(f"{z['nummer']}  {z['kunde']}  ·  Maschine {z['maschine'] or '–'}  ·  {z['status']}")
            it.setData(Qt.UserRole, z["id"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if z["id"] in vorauswahl else Qt.Unchecked)
            self.liste.addItem(it)
        self.liste.itemChanged.connect(lambda _it: self._veraltet())
        self.rechnen_knopf = QPushButton("Gemeinsam optimieren")
        self.rechnen_knopf.clicked.connect(lambda: self.rechnen())
        self.ergebnis = QLabel()
        self.ergebnis.setWordWrap(True)
        self.ergebnis.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.pdf_knopf = QPushButton("Werkstattpapiere (PDF) …")
        self.pdf_knopf.setEnabled(False)
        self.pdf_knopf.clicked.connect(lambda: self.pdf())
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        for w in (info, self.liste, self.rechnen_knopf, self.ergebnis, self.pdf_knopf, knoepfe):
            lay.addWidget(w)
        lay.setStretch(1, 1)

    def gewaehlt(self):
        return [self.liste.item(i).data(Qt.UserRole) for i in range(self.liste.count())
                if self.liste.item(i).checkState() == Qt.Checked]

    def _veraltet(self):
        self.los = None
        self.pdf_knopf.setEnabled(False)
        self.ergebnis.setText("")

    def rechnen(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.los = fertigungslos.zusammenstellen(self.db, self.gewaehlt())
        except fertigungslos.LosFehler as e:
            self.los = None
            self.ergebnis.setText(str(e))
        except ValueError as e:
            self.los = None
            self.ergebnis.setText(f"Optimierung nicht möglich: {fehler_text(e)}")
        finally:
            QApplication.restoreOverrideCursor()
        if self.los:
            zeilen = [f"<b>{fertigungslos.zusammenfassung(self.los)}</b>"]
            zeilen += [f"{a['nummer']} {a['kunde']}: einzeln {a['stangen']} Stangen" for a in self.los["auftraege"]]
            zeilen += self.los["getrennt"] + [f"nicht eingeplant: {t}" for t in self.los["fehler"]]
            zeilen += fertigungslos.reihenfolge_text(fertigungslos.reihenfolge(self.los))      # MACH-008
            self.ergebnis.setText("<br>".join(zeilen))
        self.pdf_knopf.setEnabled(bool(self.los))
        return self.los

    def pdf(self, pfad=None, oeffnen=True):
        if not self.los:
            return None
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Werkstattpapiere des Loses",
                                                  f"{self.los['kopf']['nummer']} Werkstattpapiere.pdf", "PDF (*.pdf)")
            if not pfad:
                return None
        try:
            fertigungslos.pdf_schreiben(pfad, self.los)
        except OSError as e:
            self.ergebnis.setText(f"PDF nicht gespeichert: {fehler_text(e)}")
            return None
        if oeffnen:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pfad)))
        return pfad
