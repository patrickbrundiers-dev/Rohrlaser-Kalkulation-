"""Bauteilbibliothek (Großes UI- und Funktionsupdate 19.11.2026, Punkt 4.4): die Positionsvorlagen als Bibliothek mit
Suche, Kategorien, Favoriten, 3D-Vorschau, Kopieren und Löschen. Im Angebot setzt „Einsetzen“ (bzw. Doppelklick)
die gewählte Vorlage als neue Position ein. Logik in positionsvorlagen.py."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import positionsvorlagen as PV

ALLE = "Alle Kategorien"
SPALTEN = ("★", "Name", "Kategorie", "Inhalt", "Angelegt")


class BibliothekDialog(QDialog):
    """einsetzen=True: Knopf „Als Position einsetzen“ (Ergebnis: gewaehlt = ID, accept)."""

    def __init__(self, db, parent=None, k=None, einsetzen=True):
        super().__init__(parent)
        self.db, self.k = db, k if k is not None else db.kontext()
        self.gewaehlt = None
        self.stumm = bool(getattr(getattr(parent, "f", None), "stumm", False))
        self.setWindowTitle("Bauteilbibliothek")
        self.resize(1180, 680)
        lay = QVBoxLayout(self)
        oben = QHBoxLayout()
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Name, Profil, Werkstoff, Artikel, Kategorie …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(lambda _: self.laden())
        oben.addWidget(self.suche, 1)
        self.kategorie = QComboBox()
        self.kategorie.currentTextChanged.connect(lambda _: self.laden())
        oben.addWidget(self.kategorie)
        self.nur_fav = QCheckBox("Nur Favoriten")
        self.nur_fav.toggled.connect(lambda _: self.laden())
        oben.addWidget(self.nur_fav)
        lay.addLayout(oben)
        teiler = QSplitter(Qt.Horizontal)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.verticalHeader().hide()
        self.tabelle.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabelle.setSelectionMode(QTableWidget.SingleSelection)
        self.tabelle.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabelle.itemSelectionChanged.connect(self._gewaehlt)
        self.tabelle.cellDoubleClicked.connect(lambda r, c: self._favorit_umschalten() if c == 0 else
                                               (self.einsetzen() if einsetzen else None))
        teiler.addWidget(self.tabelle)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        from .ansicht3d import Ansicht3DMitKnoepfen
        self.vorschau = Ansicht3DMitKnoepfen()
        self.vorschau.setMinimumSize(360, 260)
        rl.addWidget(self.vorschau, 1)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rl.addWidget(self.info)
        teiler.addWidget(rechts)
        teiler.setSizes([640, 520])
        lay.addWidget(teiler, 1)
        unten = QHBoxLayout()
        self.knoepfe = {}
        for name, text, tun in (("favorit", "☆ Favorit", self._favorit_umschalten),
                                ("kategorie", "Kategorie …", self._kategorie),
                                ("kopieren", "Kopieren …", self._kopieren),
                                ("loeschen", "Löschen …", self._loeschen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, tun=tun: tun())
            unten.addWidget(b)
            self.knoepfe[name] = b
        unten.addStretch(1)
        self.anzahl = QLabel("")
        unten.addWidget(self.anzahl)
        if einsetzen:
            b = QPushButton("Als Position einsetzen")
            b.setDefault(True)
            b.clicked.connect(self.einsetzen)
            unten.addWidget(b)
            self.knoepfe["einsetzen"] = b
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.reject)
        unten.addWidget(zu)
        lay.addLayout(unten)
        self.kategorien_laden()
        self.laden()

    # ------------------------------------------------------------ Daten
    def vorlagen(self):
        return self.db.zeilen(PV.TABELLE)

    def kategorien_laden(self):
        alt = self.kategorie.currentText()
        self.kategorie.blockSignals(True)
        self.kategorie.clear()
        self.kategorie.addItems([ALLE] + PV.kategorien(self.vorlagen()) + [PV.OHNE_KATEGORIE])
        if alt and self.kategorie.findText(alt) >= 0:
            self.kategorie.setCurrentText(alt)
        self.kategorie.blockSignals(False)

    def laden(self, waehlen=None):
        kat = self.kategorie.currentText()
        self.liste = PV.suchen(self.vorlagen(), self.suche.text(), None if kat in ("", ALLE) else kat,
                               self.nur_fav.isChecked())
        waehlen = waehlen if waehlen is not None else self.aktuell_id()
        self.tabelle.blockSignals(True)
        self.tabelle.setRowCount(len(self.liste))
        for i, v in enumerate(self.liste):
            for j, text in enumerate(("★" if PV.ist_favorit(v) else "", v.get("name") or "",
                                      v.get("kategorie") or "", v.get("inhalt") or "",
                                      str(v.get("angelegt") or "").replace("T", " "))):
                it = QTableWidgetItem(text)
                if j == 0:
                    it.setTextAlignment(Qt.AlignCenter)
                    it.setToolTip("Doppelklick: Favorit an/aus")
                self.tabelle.setItem(i, j, it)
        self.tabelle.resizeColumnToContents(0)
        self.tabelle.resizeColumnToContents(1)
        self.tabelle.resizeColumnToContents(2)
        self.tabelle.blockSignals(False)
        zeile = next((i for i, v in enumerate(self.liste) if v["id"] == waehlen), 0 if self.liste else -1)
        if zeile >= 0:
            self.tabelle.selectRow(zeile)
        self.anzahl.setText(f"{len(self.liste)} von {len(self.vorlagen())} Bauteilen")
        self._gewaehlt()

    def aktuell(self):
        r = self.tabelle.currentRow()
        sel = self.tabelle.selectionModel().selectedRows() if self.tabelle.selectionModel() else []
        if sel:
            r = sel[0].row()
        return self.liste[r] if 0 <= r < len(getattr(self, "liste", ())) else None

    def aktuell_id(self):
        v = self.aktuell() if hasattr(self, "liste") else None
        return v["id"] if v else None

    def _gewaehlt(self):
        v = self.aktuell()
        for name, b in self.knoepfe.items():
            b.setEnabled(v is not None)
        if v is None:
            self.vorschau.setzen(None, "")
            self.info.setText("Keine Bauteile gefunden. Im Angebot an einer Position „Position als Vorlage "
                              "speichern …“ legt ein Bauteil in der Bibliothek ab.")
            return
        self.knoepfe["favorit"].setText("★ Favorit" if PV.ist_favorit(v) else "☆ Favorit")
        netz = PV.vorschau_netz(v, self.k)
        self.vorschau.setzen(netz, v.get("name") or "")
        d = PV.werte(v) or {}
        zeilen = [f"<b>{v.get('name')}</b>", v.get("inhalt") or ""]
        for feld, titel in (("artikel", "Artikel"), ("bezeichnung", "Bezeichnung"), ("oberflaeche", "Oberfläche")):
            if d.get(feld):
                zeilen.append(f"{titel}: {d[feld]}")
        if v.get("bemerkung"):
            zeilen.append(f"Bemerkung: {v['bemerkung']}")
        if netz is None:
            zeilen.append("<i>Keine 3D-Vorschau (keine Eingaben des Editors oder Profil unbekannt).</i>")
        self.info.setText("<br>".join(z for z in zeilen if z))

    # ------------------------------------------------------------ Aktionen
    def _favorit_umschalten(self):
        v = self.aktuell()
        if v is None:
            return None
        an = not PV.ist_favorit(v)
        PV.favorit_setzen(self.db, v["id"], an)
        self.laden(v["id"])
        return an

    def _kategorie(self, kategorie=None):
        v = self.aktuell()
        if v is None:
            return
        if kategorie is None:
            if self.stumm:
                return
            kategorie, ok = QInputDialog.getItem(self, "Kategorie", "Kategorie (neu eintippen oder wählen):",
                                                 PV.kategorien(self.vorlagen()) or [""], 0, True)
            if not ok:
                return
        PV.kategorie_setzen(self.db, v["id"], kategorie)
        self.kategorien_laden()
        self.laden(v["id"])

    def _kopieren(self, name=None):
        v = self.aktuell()
        if v is None:
            return None
        if name is None:
            if self.stumm:
                return None
            name, ok = QInputDialog.getText(self, "Bauteil kopieren", "Name der Kopie:", text=f"{v['name']} (Kopie)")
            if not ok:
                return None
        try:
            i = PV.kopieren(self.db, v["id"], name)
        except ValueError as e:
            if not self.stumm:
                QMessageBox.warning(self, "Bauteil kopieren", str(e))
            return None
        self.laden(i)
        return i

    def _loeschen(self, frage=True):
        v = self.aktuell()
        if v is None:
            return False
        if frage and (self.stumm or QMessageBox.question(self, "Bauteil löschen", f"„{v['name']}“ aus der Bibliothek "
                                                         "löschen? Angebote mit diesem Teil bleiben unverändert.")
                      != QMessageBox.Yes):
            return False
        self.db.loeschen(PV.TABELLE, [v["id"]])
        self.kategorien_laden()
        self.laden()
        return True

    def einsetzen(self):
        v = self.aktuell()
        if v is None:
            return
        self.gewaehlt = v["id"]
        self.accept()
