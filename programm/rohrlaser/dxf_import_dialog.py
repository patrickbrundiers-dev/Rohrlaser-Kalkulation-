"""Fenster 'DXF importieren' (Schritt 3E-9, Rechnung in dxf_import.py): alle Bleche der DXF mit Vorschau und Haken,
je Teil Bezeichnung, Werkstoff, Dicke, Stückzahl und bei Biegelinien die Biegewinkel (Kantteil). Werkstoff und Dicke
sind vorgeschlagen aus Dateiname und Texten der DXF, sonst wie beim letzten Import. Maßstab aus Bemaßung oder
Schriftfeld, änderbar (liest die Datei neu)."""
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QSpinBox, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import blech, dxf, dxf_import as di, schneidweg as sw, vorschau
from .blech_dialog import BlechSkizze

MASSSTAB_TEXTE = ("1:1", "1:2", "1:2,5", "1:4", "1:5", "1:10", "1:20", "2:1", "5:1", "10:1")


def massstab_text(f):
    """Faktor Zeichnung -> echt als '1:2' bzw. '2:1'."""
    if f >= 1:
        return f"1:{f:g}".replace(".", ",")
    return f"{1 / f:g}:1".replace(".", ",")


def massstab_wert(text):
    try:
        a, b = (float(x.strip().replace(",", ".")) for x in str(text).split(":"))
        return b / a if a > 0 and b > 0 else None
    except ValueError:
        return None


class DxfImportDialog(QDialog):
    """text: DXF-Text (sonst aus pfad gelesen); vorgabe: dict(werkstoff, dicke) z. B. aus dem Blech-Editor;
    mehrere=False: nur ein Teil wählbar (Blech-Editor). Nach OK: ergebnisse() = [(Eingaben, Kopf)]. Fehler beim
    Lesen: self.fehler (Text), dann nicht anzeigen."""

    def __init__(self, parent, db, pfad=None, text=None, vorgabe=None, mehrere=True):
        super().__init__(parent)
        self.db, self.mehrere = db, mehrere
        self.dateiname = Path(pfad).name if pfad else "DXF"
        self.fehler = None
        self.werkstoffe = {z["blech_werkstoff_id"]: z for z in db.zeilen("blech_werkstoffe")
                           if z.get("blech_werkstoff_id")} if db else {}
        self.einst = db.blech_einstellungen() if db else {}
        try:
            self.text = text if text is not None else di.datei_lesen(pfad)
            self.erg = di.importieren(self.text, self.dateiname, self._namen())
        except (OSError, ValueError) as x:
            self.fehler = str(x)
            return
        vorgabe = vorgabe or {}
        gefunden = (di.werkstoff_aus([self.dateiname], self.werkstoffe)      # Dateiname vor Texten der Zeichnung
                    or di.werkstoff_aus(self.erg["texte"], self.werkstoffe))
        self.werkstoff_vorschlag = (gefunden or vorgabe.get("werkstoff")
                                    or (db.einstellung("dxf_import_werkstoff") if db else None))
        if self.werkstoff_vorschlag not in self.werkstoffe:
            self.werkstoff_vorschlag = next(iter(sorted(self.werkstoffe)), None)
        self.dicke_vorschlag = (self.erg["dicke"] or vorgabe.get("dicke")
                                or (db.einstellung("dxf_import_dicke") if db else None) or 3.0)
        self.quelle = ("aus Dateiname/DXF" if gefunden or self.erg["dicke"]
                       else "wie zuletzt")
        self.setWindowTitle(f"DXF importieren – {self.dateiname}")
        lay = QVBoxLayout(self)
        kopf = QHBoxLayout()
        self.info = QLabel()
        self.info.setWordWrap(True)
        kopf.addWidget(self.info, 1)
        kopf.addWidget(QLabel("Maßstab"))
        self.massstab = QComboBox()
        self.massstab.setEditable(True)
        self.massstab.addItems(list(MASSSTAB_TEXTE))
        self.massstab.setCurrentText(massstab_text(self.erg["massstab"]))
        self.massstab.setToolTip("Maßstab der Zeichnung (1:2 = gezeichnet halb so groß): Vorschlag aus Bemaßung "
                                 "oder Schriftfeld; ändern liest die Datei neu")
        self.massstab.currentTextChanged.connect(self.massstab_aendern)
        kopf.addWidget(self.massstab)
        lay.addLayout(kopf)
        teiler = QSplitter(Qt.Horizontal)
        lay.addWidget(teiler, 1)
        self.liste = QListWidget()
        self.liste.setIconSize(QSize(120, 60))
        self.liste.currentRowChanged.connect(self.zeigen)
        self.liste.itemChanged.connect(lambda _: self._ok_text())
        teiler.addWidget(self.liste)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(6, 0, 0, 0)
        self.skizze = BlechSkizze()
        rl.addWidget(self.skizze, 1)
        self.zusammen = QLabel()
        self.zusammen.setWordWrap(True)
        rl.addWidget(self.zusammen)
        raster = QGridLayout()
        self.bezeichnung = QLineEdit()
        self.werkstoff = QComboBox()
        for kat in ("Stahl", "Edelstahl", "Aluminium"):
            for n in sorted(x for x, z in self.werkstoffe.items() if z.get("kategorie") == kat):
                self.werkstoff.addItem(n)
        for n in sorted(x for x in self.werkstoffe if self.werkstoff.findText(x) < 0):
            self.werkstoff.addItem(n)
        self.dicke = QDoubleSpinBox()
        self.dicke.setRange(0.1, 100)
        self.dicke.setDecimals(2)
        self.dicke.setSingleStep(0.5)
        self.dicke.setSuffix(" mm")
        self.stueck = QSpinBox()
        self.stueck.setRange(1, 10 ** 7)
        self.kant = QCheckBox("Als Kantteil (Biegelinien aus der DXF)")
        felder = ((0, 0, 2, "Bezeichnung", self.bezeichnung), (0, 2, 1, "Stückzahl", self.stueck),
                  (2, 0, 1, "Blech-Werkstoff", self.werkstoff), (2, 1, 1, "Dicke", self.dicke))
        for r, c, n, titel, w in felder:
            raster.addWidget(QLabel(f"<span style='color:#595959'>{titel}</span>"), r, c, 1, n)
            raster.addWidget(w, r + 1, c, 1, n)
        self.quelle_text = QLabel()
        self.quelle_text.setStyleSheet("color: #595959")
        raster.addWidget(self.quelle_text, 3, 2)
        rl.addLayout(raster)
        rl.addWidget(self.kant)
        self.winkel = QTableWidget(0, 2)
        self.winkel.setHorizontalHeaderLabels(["Biegelinie y [mm]", "Biegewinkel [°] (+ hoch, − runter)"])
        self.winkel.horizontalHeader().setStretchLastSection(True)
        self.winkel.setMaximumHeight(130)
        rl.addWidget(self.winkel)
        self.warnungen = QLabel()
        self.warnungen.setWordWrap(True)
        self.warnungen.setStyleSheet("color: #B26A00")
        rl.addWidget(self.warnungen)
        teiler.addWidget(rechts)
        teiler.setSizes([300, 700])
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.accepted.connect(self.accept)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        for w in (self.bezeichnung,):
            w.textEdited.connect(self._merken)
        self.werkstoff.currentTextChanged.connect(self._merken)
        self.dicke.valueChanged.connect(self._merken)
        self.stueck.valueChanged.connect(self._merken)
        self.kant.toggled.connect(self._merken)
        self.winkel.itemChanged.connect(self._merken)
        self._aktuell = None
        self.resize(1100, 720)
        self._teile_setzen()

    def _namen(self):
        return dxf.layer_namen(self.db.einstellung("blech_dxf_layer") if self.db else None)

    # -------------------------------------------------------------- Teile
    def _teile_setzen(self):
        self.zustand = []
        for t in self.erg["teile"]:
            self.zustand.append(dict(name=t["name"], werkstoff=self.werkstoff_vorschlag, dicke=self.dicke_vorschlag,
                                     stueck=1, kant=bool(t["biegelinien"]),
                                     winkel=[b["winkel"] for b in t["e"].get("biegelinien_dxf") or ()]))
        self.liste.blockSignals(True)
        self.liste.clear()
        for t in self.erg["teile"]:
            it = QListWidgetItem(t["name"] + (f"\n({t['grund']})" if t["grund"] else ""))
            pm = vorschau.blech_bild(dict(t["e"], dicke=self.dicke_vorschlag), 120, 60)
            it.setIcon(QIcon(pm) if pm is not None else QIcon())
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            aktiv = t["aktiv"] and (self.mehrere or not any(self.liste.item(i).checkState() == Qt.Checked
                                                            for i in range(self.liste.count())))
            it.setCheckState(Qt.Checked if aktiv else Qt.Unchecked)
            self.liste.addItem(it)
        self.liste.blockSignals(False)
        teile = len(self.erg["teile"])
        quelle = self.erg.get("massstab_quelle")
        self.info.setText(f"<b>{teile} Teil{'e' if teile != 1 else ''}</b> in {self.dateiname}"
                          + (f" · Maßstab aus {quelle}" if quelle else "")
                          + "".join(f"<br><span style='color:#595959'>{w}</span>" for w in self.erg["warnungen"]))
        self._aktuell = None
        if teile:
            self.liste.setCurrentRow(0)
            self.zeigen(0)
        self._ok_text()

    def massstab_aendern(self, text):
        f = massstab_wert(text)
        if not f or abs(f - self.erg["massstab"]) < 1e-9:
            return
        try:
            self.erg = di.importieren(self.text, self.dateiname, self._namen(), massstab=f)
        except ValueError:
            return
        self._teile_setzen()

    def zeigen(self, r):
        if not 0 <= r < len(self.erg["teile"]):
            return
        self._aktuell = None
        t, z = self.erg["teile"][r], self.zustand[r]
        widgets = (self.bezeichnung, self.werkstoff, self.dicke, self.stueck, self.kant, self.winkel)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.bezeichnung.setText(z["name"])
            if z["werkstoff"]:
                self.werkstoff.setCurrentText(z["werkstoff"])
            self.dicke.setValue(sw._z(z["dicke"]))
            self.stueck.setValue(int(z["stueck"]))
            self.kant.setChecked(z["kant"])
            self.kant.setVisible(bool(t["biegelinien"]))
            self.winkel.setVisible(bool(t["biegelinien"]))
            self.winkel.setRowCount(0)
            for (y, _a), w in zip(t["biegelinien"], z["winkel"]):
                i = self.winkel.rowCount()
                self.winkel.insertRow(i)
                it = QTableWidgetItem(f"{y:g}".replace(".", ","))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.winkel.setItem(i, 0, it)
                self.winkel.setItem(i, 1, QTableWidgetItem(f"{w:g}"))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.quelle_text.setText(f"Werkstoff/Dicke: {self.quelle}")
        self.zusammen.setText(t["zusammenfassung"])
        self.warnungen.setText("<br>".join(t["warnungen"]))
        self._aktuell = r
        self._vorschau()

    def _merken(self, *_):
        r = self._aktuell
        if r is None:
            return
        z = self.zustand[r]
        winkel = []
        for i in range(self.winkel.rowCount()):
            it = self.winkel.item(i, 1)
            try:
                winkel.append(float((it.text() if it else "").replace(",", ".")))
            except ValueError:
                winkel.append(z["winkel"][i] if i < len(z["winkel"]) else 90.0)
        z.update(name=self.bezeichnung.text().strip(), werkstoff=self.werkstoff.currentText() or None,
                 dicke=self.dicke.value(), stueck=self.stueck.value(), kant=self.kant.isChecked(), winkel=winkel)
        self._vorschau()

    def _vorschau(self):
        r = self._aktuell
        if r is None:
            return
        e = self.eingaben(r)
        try:
            zs = blech.zuschnitt(e, blech.k_fuer(self.werkstoffe.get(e.get("werkstoff")), e.get("dicke"), self.einst))
        except ValueError as x:
            self.skizze.setzen({}, None)
            self.warnungen.setText("<br>".join(self.erg["teile"][r]["warnungen"] + [str(x)]))
            return
        self.skizze.setzen(e, zs)

    def _ok_text(self):
        n = len(self.gewaehlt())
        ok = self.knoepfe.button(QDialogButtonBox.Ok)
        ok.setEnabled(n > 0 and (self.mehrere or n == 1))
        ok.setText("Übernehmen" if not self.mehrere else f"{n} Teil{'e' if n != 1 else ''} übernehmen")
        if not self.mehrere and n > 1:
            ok.setToolTip("Im Blech-Editor genau ein Teil anhaken")

    def gewaehlt(self):
        return [i for i in range(self.liste.count()) if self.liste.item(i).checkState() == Qt.Checked]

    def eingaben(self, r):
        """Blech-Eingaben des Teils r mit Werkstoff, Dicke, Stückzahl; Kantteil aus den Biegelinien."""
        t, z = self.erg["teile"][r], self.zustand[r]
        e = dict(t["e"], werkstoff=z["werkstoff"], dicke=z["dicke"], stueck=z["stueck"])
        if z["kant"] and e.get("biegelinien_dxf"):
            e = di.als_kantteil(e, z["winkel"], z["dicke"],
                                blech.k_fuer(self.werkstoffe.get(z["werkstoff"]), z["dicke"], self.einst))
        e.pop("biegelinien_dxf", None)
        return e

    def ergebnisse(self):
        """[(Eingaben, Kopf dict(bezeichnung, stueck))] der angehakten Teile."""
        return [(self.eingaben(r), dict(bezeichnung=self.zustand[r]["name"] or None, stueck=self.zustand[r]["stueck"]))
                for r in self.gewaehlt()]

    def accept(self):
        if self._aktuell is not None:
            z = self.zustand[self._aktuell]
            if self.db is not None and not getattr(self.db, "nur_lesen", False):
                self.db.einstellung_setzen("dxf_import_werkstoff", z["werkstoff"])
                self.db.einstellung_setzen("dxf_import_dicke", z["dicke"])
        super().accept()
