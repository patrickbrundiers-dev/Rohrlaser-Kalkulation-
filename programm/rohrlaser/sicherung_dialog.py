"""Dialog „Sicherung wiederherstellen“: alle Sicherungen aus Daten/Sicherung und dem zweiten Sicherungsordner mit
Zeit, Art, Inhalt und Schema; neueste oben. Gewählt wird eine Datei, ersetzt wird in Hauptfenster.daten_ersetzen."""
import datetime
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import stil
from .datenbank import SCHEMA_VERSION, _geschuetzt, datei_info

SPALTEN = ("Zeit", "Art", "Angebote", "Positionen", "Schema", "Ordner")
ARTEN = {"update": "vor Update", "Schema": "vor Schema-Umstellung", "Wiederherstellung": "vor Wiederherstellung",
         "Import": "vor Import", "Uebernahme": "vor Übernahme"}


def art_text(pfad):
    g = _geschuetzt(pfad)
    if g:
        return ARTEN.get(g, "vor " + g)
    return "beim Beenden" if Path(pfad).stem.endswith("_beenden") else "täglich / von Hand"


def sicherungen_lesen(ordner_liste):
    """[{pfad, zeit, art, schema, anzahl, fehler}] neueste zuerst; Beschreibung aus <name>.json, sonst aus der Datei."""
    zeilen = []
    for ordner in ordner_liste:
        for p in Path(ordner).glob("*.db"):
            z = dict(pfad=p, zeit=datetime.datetime.fromtimestamp(p.stat().st_mtime), art=art_text(p), fehler="")
            try:
                beschreibung = p.with_suffix(".json")
                info = (json.loads(beschreibung.read_text(encoding="utf-8")) if beschreibung.is_file()
                        else datei_info(p))
                z.update(schema=info.get("schema"), anzahl=info.get("anzahl") or {})
            except Exception as e:     # beschädigte oder fremde Datei: anzeigen, aber nicht wählbar
                z.update(schema=None, anzahl={}, fehler=str(e))
            zeilen.append(z)
    return sorted(zeilen, key=lambda z: z["zeit"], reverse=True)


class WiederherstellenDialog(QDialog):
    def __init__(self, fenster):
        super().__init__(fenster)
        self.f = fenster
        self.gewaehlt = None
        self.setWindowTitle("Sicherung wiederherstellen")
        self.resize(900, 480)
        hinweis = QLabel("Sicherung wählen. Der jetzige Stand wird vorher gesichert (Art „vor Wiederherstellung“) "
                         "und lässt sich damit wieder zurückholen. Sicherungen einer neueren Programmversion "
                         f"(Schema über {SCHEMA_VERSION}) lassen sich erst nach einem Update einlesen.")
        hinweis.setWordWrap(True)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.verticalHeader().hide()
        self.tabelle.horizontalHeader().setSectionResizeMode(len(SPALTEN) - 1, QHeaderView.Stretch)
        self.tabelle.doubleClicked.connect(lambda *_: self._ok())
        knoepfe = QDialogButtonBox()
        self.ok = knoepfe.addButton("Wiederherstellen", QDialogButtonBox.AcceptRole)
        andere = QPushButton("Andere Datei …")
        knoepfe.addButton(andere, QDialogButtonBox.ActionRole)
        knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        self.ok.clicked.connect(self._ok)
        andere.clicked.connect(self._andere)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(hinweis)
        lay.addWidget(self.tabelle)
        lay.addWidget(knoepfe)
        self.zeilen = sicherungen_lesen(fenster.db.sicherungsordner())
        self._fuellen()

    def _fuellen(self):
        self.tabelle.setRowCount(len(self.zeilen))
        for i, z in enumerate(self.zeilen):
            werte = (z["zeit"].strftime("%d.%m.%Y %H:%M"), z["art"],
                     z["anzahl"].get("angebote", "") if not z["fehler"] else "unlesbar",
                     z["anzahl"].get("positionen", ""), z["schema"] if z["schema"] is not None else "",
                     str(z["pfad"].parent))
            for j, w in enumerate(werte):
                item = QTableWidgetItem(str(w))
                if j in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if z["fehler"] or (z["schema"] or 0) > SCHEMA_VERSION:
                    item.setForeground(stil.farbe(stil.TEXT_GRAU))
                    item.setToolTip(z["fehler"] or "Sicherung einer neueren Programmversion")
                self.tabelle.setItem(i, j, item)
        self.tabelle.resizeColumnsToContents()
        if self.zeilen:
            self.tabelle.selectRow(0)
        self.ok.setEnabled(bool(self.zeilen))

    def _ok(self):
        i = self.tabelle.currentRow()
        if 0 <= i < len(self.zeilen):
            self.gewaehlt = self.zeilen[i]["pfad"]
            self.accept()

    def _andere(self):
        datei, _ = QFileDialog.getOpenFileName(self, "Sicherung wiederherstellen", str(self.f.db.pfad.parent),
                                               "Sicherung, Export oder Datendatei (*.db *.zip)")
        if datei:
            self.gewaehlt = Path(datei)
            self.accept()
