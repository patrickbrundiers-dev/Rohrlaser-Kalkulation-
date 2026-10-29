"""Zukaufartikel: Unterreiter 'Preisänderungen' (Protokoll, betroffene Angebote mit Vergleich alt/neu, Aktualisieren
je Angebot) und CSV-Import mit Vorschau (zukauf_csv)."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import hilfe, stil, tastatur, zukauf_csv
from .stammdaten import zahl_als_text
from .zukauf_dialog import datum_text

FARBE = {zukauf_csv.NEU: "#E2F0D9", zukauf_csv.AENDERN: "#FFF2CC", zukauf_csv.FEHLER: "#F8D7DA"}


def _tabelle(spalten, breiten=()):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    t.setWordWrap(False)
    t.setTextElideMode(Qt.ElideRight)
    kopf = t.horizontalHeader()
    kopf.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    for i, b in enumerate(breiten):
        t.setColumnWidth(i, b)
    kopf.setStretchLastSection(True)
    return t


def _fuellen(t, zeilen, rechts=()):
    t.setRowCount(len(zeilen))
    for r, zeile in enumerate(zeilen):
        for c, w in enumerate(zeile):
            it = QTableWidgetItem("" if w is None else str(w))
            it.setToolTip(it.text())
            if c in rechts:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(r, c, it)


def _euro(w):
    return "" if w is None else f"{zahl_als_text(w, 2)} €"


class PreisaenderungenSeite(QWidget):
    """Protokoll der Preisänderungen; zum markierten Artikel die Angebote mit älterem Preisstand."""
    titel = "Preisänderungen"
    SPALTEN = ("Datum", "Artikel", "Lieferant", "Was", "Alt", "Neu", "Bemerkung")
    BETROFFEN = ("Angebot", "Kunde", "Positionen", "Preisstand", "Verbrauch", "VK alt", "VK neu", "Differenz")

    def __init__(self, db, meldung):
        super().__init__()
        self.db, self.meldung = db, meldung
        self.daten, self.betroffen = [], []
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen (Artikel, Lieferant, Feld) …")
        self.suche.setClearButtonEnabled(True)
        tastatur.suche_esc(self.suche)
        self.suche.textChanged.connect(self.anzeigen)
        self.artikel_filter = QComboBox()
        self.artikel_filter.currentIndexChanged.connect(self.anzeigen)
        oben = QHBoxLayout()
        oben.addWidget(self.suche, 2)
        oben.addWidget(QLabel("Artikel"))
        oben.addWidget(self.artikel_filter, 1)
        self.tabelle = _tabelle(self.SPALTEN, (125, 220, 140, 150, 160, 160))
        self.tabelle.itemSelectionChanged.connect(self._auswahl)
        self.titel_betroffen = QLabel()
        self.titel_betroffen.setObjectName("kartentitel")
        self.titel_betroffen.setWordWrap(True)
        self.tab_betroffen = _tabelle(self.BETROFFEN, (110, 180, 75, 90, 80, 90, 90))
        self.tab_betroffen.itemDoubleClicked.connect(lambda _: self.angebot_oeffnen())
        self.k_oeffnen = QPushButton("Angebot öffnen")
        self.k_oeffnen.clicked.connect(lambda: self.angebot_oeffnen())
        self.k_aktualisieren = QPushButton("Im Angebot aktualisieren …")
        self.k_aktualisieren.setToolTip("Preisstand dieses Artikels im markierten Angebot auf den aktuellen Stand "
                                        "setzen (nach Rückfrage mit Vergleich alt/neu)")
        self.k_aktualisieren.clicked.connect(lambda: self.aktualisieren())
        knoepfe = QHBoxLayout()
        knoepfe.addWidget(self.k_oeffnen)
        knoepfe.addWidget(self.k_aktualisieren)
        knoepfe.addStretch(1)
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(self.titel_betroffen)
        ul.addWidget(self.tab_betroffen, 1)
        ul.addLayout(knoepfe)
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(self.tabelle)
        teiler.addWidget(unten)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 2)
        teiler.setChildrenCollapsible(False)
        hinweis = hilfe.Hinweis("Jede Änderung an Einkaufspreisen, Bezugskosten und Aufschlag eines Artikels wird "
                                "hier protokolliert. Gespeicherte Angebote rechnen mit ihrem Preisstand weiter; unten"
                                " stehen die Angebote mit älterem Stand des markierten Artikels.",
                                schluessel="zukauf_preise")
        lay = QVBoxLayout(self)
        lay.addWidget(hinweis)
        lay.addLayout(oben)
        lay.addWidget(teiler, 1)
        self.neu_laden()

    def neu_laden(self):
        self.daten = self.db.zukauf_historie()
        gewaehlt = self.artikel_filter.currentData()
        self.artikel_filter.blockSignals(True)
        self.artikel_filter.clear()
        self.artikel_filter.addItem("Alle", None)
        for a in sorted(self.db.zukauf_artikel_liste(), key=lambda a: (a.get("artikelnr") or "", a.get("bezeichnung") or "")):
            self.artikel_filter.addItem(" – ".join(x for x in (a.get("artikelnr"), a.get("bezeichnung")) if x), a["id"])
        i = self.artikel_filter.findData(gewaehlt)
        self.artikel_filter.setCurrentIndex(max(i, 0))
        self.artikel_filter.blockSignals(False)
        self.anzeigen()

    def sichtbar(self):
        t = self.suche.text().strip().lower()
        aid = self.artikel_filter.currentData()
        return [z for z in self.daten if (aid is None or z.get("artikel_id") == aid)
                and (not t or t in " ".join(str(z.get(n) or "") for n in ("artikel", "lieferant", "feld")).lower())]

    def anzeigen(self, *_):
        self.zeilen = self.sichtbar()
        _fuellen(self.tabelle, [(datum_text(z.get("datum")) + (z.get("datum") or "")[10:16].replace("T", " "),
                                 z.get("artikel"), z.get("lieferant"),
                                 z.get("feld"), z.get("alt"), z.get("neu"), z.get("bemerkung")) for z in self.zeilen])
        if self.zeilen:
            self.tabelle.blockSignals(True)
            self.tabelle.selectRow(0)
            self.tabelle.blockSignals(False)
        self._auswahl()

    def _auswahl(self):
        r = self.tabelle.currentRow()
        self._betroffen_zeigen(self.zeilen[r].get("artikel_id") if 0 <= r < len(self.zeilen)
                               else self.artikel_filter.currentData())

    def _betroffen_zeigen(self, artikel_id):
        self.artikel_id = artikel_id
        self.betroffen = self.db.zukauf_betroffen(artikel_id) if artikel_id is not None else []
        a = self.db.zukauf_artikel(artikel_id) if artikel_id is not None else None
        name = " – ".join(x for x in (a.get("artikelnr"), a.get("bezeichnung")) if x) if a else ""
        self.titel_betroffen.setText(
            "Artikel markieren: hier erscheinen die Angebote mit älterem Preisstand." if a is None else
            f"Angebote mit älterem Preisstand von {name}: {len(self.betroffen)}" if self.betroffen else
            f"Kein Angebot mit älterem Preisstand von {name}.")
        _fuellen(self.tab_betroffen, [(b["nummer"], b["kunde"], b["positionen"],
                                       ", ".join(datum_text(d) for d in b["stand"].split(", ")),
                                       zahl_als_text(b["verbrauch"], 2), _euro(b["vk_alt"]), _euro(b["vk_neu"]),
                                       _euro(b["vk_neu"] - b["vk_alt"]) if b["vk_alt"] is not None
                                       and b["vk_neu"] is not None else "kein Einkaufspreis")
                                      for b in self.betroffen], rechts=(2, 4, 5, 6, 7))
        for k in (self.k_oeffnen, self.k_aktualisieren):
            k.setEnabled(bool(self.betroffen))
        if self.betroffen:
            self.tab_betroffen.selectRow(0)

    def _gewaehlt(self):
        r = self.tab_betroffen.currentRow()
        return self.betroffen[r] if 0 <= r < len(self.betroffen) else None

    def angebot_oeffnen(self):
        b = self._gewaehlt()
        f = self.window()
        if b and hasattr(f, "angebot_oeffnen"):
            f.angebot_oeffnen(b["angebot_id"])

    def aktualisieren(self, bestaetigt=None):
        """Preisstand im markierten Angebot aktualisieren. bestaetigt: True/False ohne Rückfrage (Tests).
        Ergebnis: Anzahl geänderter Einträge."""
        b = self._gewaehlt()
        if b is None:
            return 0
        if bestaetigt is None:
            bestaetigt = QMessageBox.question(
                self, "Im Angebot aktualisieren",
                f"Angebot {b['nummer']}: Preisstand vom {datum_text(b['stand'])} durch den aktuellen ersetzen?\n\n"
                f"Zukaufteil netto für {zahl_als_text(b['verbrauch'], 2)} Einheiten: {_euro(b['vk_alt'])} → "
                f"{_euro(b['vk_neu'])}\n\nDas Angebot rechnet danach mit den neuen Preisen.") == QMessageBox.Yes
        if not bestaetigt:
            return 0
        n = self.db.zukauf_angebot_aktualisieren(b["angebot_id"], self.artikel_id)
        seite = getattr(self.window(), "offen", {}).get(b["angebot_id"])
        if seite is not None:
            seite.neu_laden()
        self.meldung(f"Angebot {b['nummer']}: Preisstand in {n} Position(en) aktualisiert.")
        self._betroffen_zeigen(self.artikel_id)
        return n


class CsvImportDialog(QDialog):
    """Vorschau des CSV-Imports: je Zeile Aktion (neu, ändern, unverändert, Fehler) mit Änderungen bzw. Fehlern.
    Übernommen wird erst mit 'Importieren'; Zeilen mit Fehler nie."""
    SPALTEN = ("Zeile", "Aktion", "Artikelnr.", "Bezeichnung", "Lieferant", "Änderungen / Fehler")

    def __init__(self, parent, db, ergebnis, datei=""):
        super().__init__(parent)
        self.db, self.ergebnis = db, ergebnis
        self.setWindowTitle(f"CSV importieren: {Path(datei).name}" if datei else "CSV importieren")
        self.resize(1000, 520)
        zeilen = ergebnis["zeilen"]
        zahl = {a: sum(1 for z in zeilen if z["aktion"] == a) for a in
                (zukauf_csv.NEU, zukauf_csv.AENDERN, zukauf_csv.GLEICH, zukauf_csv.FEHLER)}
        self.zusammenfassung = QLabel(
            "; ".join(ergebnis["fehler"]) if ergebnis["fehler"] else
            f"{zahl[zukauf_csv.NEU]} neu · {zahl[zukauf_csv.AENDERN]} ändern · {zahl[zukauf_csv.GLEICH]} unverändert"
            + (f" · <b style='color:#B42318'>{zahl[zukauf_csv.FEHLER]} mit Fehler (werden nicht übernommen)</b>"
               if zahl[zukauf_csv.FEHLER] else "")
            + ". Erst <b>Importieren</b> übernimmt die Daten; Preisänderungen kommen ins Protokoll.")
        self.zusammenfassung.setWordWrap(True)
        self.tabelle = _tabelle(self.SPALTEN, (50, 85, 100, 200, 140))
        _fuellen(self.tabelle, [(z["nr"], z["aktion"], z.get("artikelnr"), z.get("bezeichnung"), z.get("lieferant"),
                                 "; ".join(z["fehler"] or z["aenderung"] + z["hinweis"])) for z in zeilen], rechts=(0,))
        for r, z in enumerate(zeilen):
            if z["aktion"] in FARBE:
                for c in range(len(self.SPALTEN)):
                    self.tabelle.item(r, c).setBackground(QBrush(stil.farbe(FARBE[z["aktion"]])))
        self.tabelle.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.importieren_knopf = knoepfe.addButton("Importieren", QDialogButtonBox.AcceptRole)
        self.importieren_knopf.setEnabled(zahl[zukauf_csv.NEU] + zahl[zukauf_csv.AENDERN] > 0)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.zusammenfassung)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(knoepfe)


def csv_exportieren(seite, db, pfad=None):
    """Alle Zukaufartikel als CSV speichern (Dateiauswahl, wenn pfad fehlt). Ergebnis: Pfad oder None."""
    f = seite.window()
    if pfad is None:
        ordner = f.ablage() if hasattr(f, "ablage") else Path.home()
        pfad, _ = QFileDialog.getSaveFileName(seite, "Zukaufartikel exportieren", str(Path(ordner) / "Zukaufartikel.csv"),
                                              "CSV (*.csv)")
        if not pfad:
            return None
    Path(pfad).write_text(zukauf_csv.exportieren(db.zukauf_artikel_liste()), encoding="utf-8", newline="")
    return pfad


def csv_importieren(seite, db, pfad=None, bestaetigt=None):
    """CSV lesen, Vorschau zeigen, nach Bestätigung übernehmen. bestaetigt: True/False ohne Dialog (Tests).
    Ergebnis: (Vorschau, (neu, geändert) oder None)."""
    f = seite.window()
    if pfad is None:
        ordner = f.ablage() if hasattr(f, "ablage") else Path.home()
        pfad, _ = QFileDialog.getOpenFileName(seite, "Zukaufartikel importieren", str(ordner), "CSV (*.csv *.txt)")
        if not pfad:
            return None, None
    ergebnis = zukauf_csv.vorschau(Path(pfad).read_bytes(), db.zukauf_artikel_liste(), db.zukauf_kategorien())
    if bestaetigt is None:
        bestaetigt = CsvImportDialog(seite, db, ergebnis, pfad).exec() == QDialog.Accepted
    if not bestaetigt:
        return ergebnis, None
    return ergebnis, db.zukauf_importieren(ergebnis["zeilen"])
