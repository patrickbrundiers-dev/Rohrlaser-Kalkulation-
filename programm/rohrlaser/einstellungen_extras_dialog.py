"""Oberfläche zur Einstellungsverwaltung (19.11.2026): Änderungsverlauf und Seite „Favoriten“ der Einstellungen.
Die Logik steht in einstellungen_extras.py."""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLabel, QLineEdit, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import einstellungen_extras as X
from .einstellungen_nav import passt

SPALTEN = ("Zeit", "Wer", "Einstellung", "Vorher", "Nachher")


class VerlaufDialog(QDialog):
    """Änderungsverlauf der Einstellungen dieses Arbeitsplatzes, neueste oben, mit Suche."""

    def __init__(self, db, parent=None, name=None):
        super().__init__(parent)
        self.setWindowTitle("Änderungsverlauf der Einstellungen")
        self.resize(900, 520)
        self.eintraege = list(reversed(X.verlauf(db, name)))
        lay = QVBoxLayout(self)
        info = QLabel(f"{len(self.eintraege)} Änderung(en) an diesem Arbeitsplatz (die letzten {X.VERLAUF_MAX}). "
                      "Änderungen der Kollegen stehen im Änderungsverlauf des gemeinsamen Ordners.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen (Einstellung, Wert, Kürzel) …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.filtern)
        lay.addWidget(self.suche)
        self.tabelle = QTableWidget(len(self.eintraege), len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.verticalHeader().hide()
        self.tabelle.setEditTriggers(QTableWidget.NoEditTriggers)
        for i, x in enumerate(self.eintraege):
            for j, k in enumerate(("zeit", "wer", "titel", "alt", "neu")):
                text = str(x.get(k) or "")
                self.tabelle.setItem(i, j, QTableWidgetItem(text.replace("T", " ") if k == "zeit" else text))
        self.tabelle.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabelle.resizeColumnsToContents()
        lay.addWidget(self.tabelle, 1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def filtern(self, text):
        for i, x in enumerate(self.eintraege):
            alles = " ".join(str(x.get(k) or "") for k in ("zeit", "wer", "titel", "alt", "neu"))
            self.tabelle.setRowHidden(i, bool(text.strip()) and not passt(alles, text))

    def sichtbar(self):
        return sum(1 for i in range(self.tabelle.rowCount()) if not self.tabelle.isRowHidden(i))


class FavoritenSeite(QWidget):
    """Seite „Favoriten“ ganz oben in den Einstellungen: die mit ☆ markierten Einstellungen auf einer Seite (je
    Arbeitsplatz). Baut ihr Formular neu, wenn sich die Favoriten ändern; leer zeigt sie einen Hinweis."""
    schluessel = "e_favoriten"
    titel = "★ Favoriten"

    def __init__(self, db, meldung):
        super().__init__()
        self.db, self.meldung = db, meldung
        self.gesperrte = frozenset()
        self.formular = None
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self.leer = QLabel("Noch keine Favoriten. Auf jeder Einstellungsseite steht neben jedem Wert ein ☆: "
                           "ein Klick merkt die Einstellung hier, so sind häufig geänderte Werte mit einem Klick "
                           "erreichbar. Die Favoriten gelten nur für Sie (diesen Arbeitsplatz).")
        self.leer.setWordWrap(True)
        self.leer.setStyleSheet("color: #5F6B7A; padding: 12px;")
        self._lay.addWidget(self.leer)
        self._namen = None
        self.neu_bauen()

    @property
    def liste(self):
        return self.formular.liste if self.formular is not None else []

    @property
    def felder(self):
        return self.formular.felder if self.formular is not None else {}

    def neu_bauen(self):
        from .einstellungen_ordnung import Abschnitt, Seite
        from .fenster import EinstellungenSeite
        namen = X.favoriten(self.db)
        if namen == self._namen and self.formular is not None:
            self.formular.neu_laden()
            return
        self._namen = list(namen)
        if self.formular is not None:
            self._lay.removeWidget(self.formular)
            self.formular.deleteLater()
            self.formular = None
        self.leer.setVisible(not namen)
        if namen:
            seite = Seite(self.schluessel, self.titel, "Ihre Favoriten aus allen Einstellungsseiten. ☆ nimmt einen "
                          "Wert wieder heraus.", (Abschnitt("Favoriten", tuple(namen)),))
            self.formular = EinstellungenSeite(self.db, self.meldung, seite=seite)
            self.formular.schutz_setzen(self.gesperrte)
            self._lay.addWidget(self.formular, 1)

    def neu_laden(self):
        self.neu_bauen()

    def filtern(self, suche):
        if self.formular is not None:
            self.formular.filtern(suche)

    def schutz_setzen(self, namen):
        self.gesperrte = frozenset(namen)
        if self.formular is not None:
            self.formular.schutz_setzen(self.gesperrte)

    def admin_setzen(self, an):
        if self.formular is not None:
            self.formular.admin_setzen(an)
