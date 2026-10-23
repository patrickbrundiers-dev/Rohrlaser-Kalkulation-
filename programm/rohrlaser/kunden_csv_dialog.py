"""Reiter Kunden: CSV-Export und CSV-Import mit Vorschau (kunden_csv). Vor dem Import legt die Datenbank eine
Sicherung '_vor_Kundenimport' an."""
from pathlib import Path

from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHeaderView, QLabel, QVBoxLayout

from . import kunden_csv, stil
from .zukauf_preise import _fuellen, _tabelle

FARBE = {kunden_csv.NEU: "#E2F0D9", kunden_csv.AENDERN: "#FFF2CC", kunden_csv.UEBERSPRUNGEN: "#EDEDED",
         kunden_csv.FEHLER: "#F8D7DA"}


class KundenImportDialog(QDialog):
    """Vorschau: je Zeile Aktion (neu, ändern, unverändert, übersprungen, Fehler) mit Änderungen bzw. Fehlern.
    'Vorhandene Kunden nicht ändern' rechnet die Vorschau neu. Übernommen wird erst mit 'Importieren'."""
    SPALTEN = ("Zeile", "Aktion", "Kundennummer", "Kundenname", "Änderungen / Fehler")

    def __init__(self, parent, rechnen, datei=""):
        super().__init__(parent)
        self.rechnen = rechnen          # nur_neue -> Ergebnis von kunden_csv.vorschau
        self.setWindowTitle(f"Kunden importieren: {Path(datei).name}" if datei else "Kunden importieren")
        self.resize(1000, 520)
        self.zusammenfassung = QLabel()
        self.zusammenfassung.setWordWrap(True)
        self.nur_neue = QCheckBox("Vorhandene Kunden nicht ändern (nur neue anlegen)")
        self.nur_neue.setToolTip("Kunden, deren Kundennummer es schon gibt, bleiben wie sie sind")
        self.nur_neue.toggled.connect(lambda _: self.anzeigen())
        self.tabelle = _tabelle(self.SPALTEN, (50, 95, 110, 220))
        self.tabelle.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.importieren_knopf = knoepfe.addButton("Importieren", QDialogButtonBox.AcceptRole)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.zusammenfassung)
        lay.addWidget(self.nur_neue)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(knoepfe)
        self.anzeigen()

    def anzeigen(self):
        self.ergebnis = self.rechnen(self.nur_neue.isChecked())
        zeilen = self.ergebnis["zeilen"]
        zahl = {a: sum(1 for z in zeilen if z["aktion"] == a) for a in
                (kunden_csv.NEU, kunden_csv.AENDERN, kunden_csv.GLEICH, kunden_csv.UEBERSPRUNGEN, kunden_csv.FEHLER)}
        self.zusammenfassung.setText(
            "; ".join(self.ergebnis["fehler"]) if self.ergebnis["fehler"] else
            f"{zahl[kunden_csv.NEU]} neu · {zahl[kunden_csv.AENDERN]} ändern · {zahl[kunden_csv.GLEICH]} unverändert"
            + (f" · {zahl[kunden_csv.UEBERSPRUNGEN]} übersprungen" if zahl[kunden_csv.UEBERSPRUNGEN] else "")
            + (f" · <b style='color:#B42318'>{zahl[kunden_csv.FEHLER]} mit Fehler (werden nicht übernommen)</b>"
               if zahl[kunden_csv.FEHLER] else "")
            + ". Erst <b>Importieren</b> übernimmt die Daten, vorher legt das Programm eine Datensicherung an.")
        _fuellen(self.tabelle, [(z["nr"], z["aktion"], z.get("kundennr"), z.get("name"),
                                 "; ".join(z["fehler"] or z["aenderung"] + z["hinweis"])) for z in zeilen], rechts=(0,))
        for r, z in enumerate(zeilen):
            if z["aktion"] in FARBE:
                for c in range(len(self.SPALTEN)):
                    self.tabelle.item(r, c).setBackground(QBrush(stil.farbe(FARBE[z["aktion"]])))
        self.importieren_knopf.setEnabled(zahl[kunden_csv.NEU] + zahl[kunden_csv.AENDERN] > 0)


def _ordner(seite):
    f = seite.window()
    return f.ablage() if hasattr(f, "ablage") else Path.home()


def csv_exportieren(seite, db, pfad=None):
    """Alle Kunden als CSV speichern (Dateiauswahl, wenn pfad fehlt). Ergebnis: Pfad oder None."""
    if pfad is None:
        pfad, _ = QFileDialog.getSaveFileName(seite, "Kunden exportieren", str(Path(_ordner(seite)) / "Kunden.csv"),
                                              "CSV (*.csv)")
        if not pfad:
            return None
    Path(pfad).write_text(kunden_csv.exportieren(db.zeilen("kunden")), encoding="utf-8")
    return pfad


def csv_importieren(seite, db, pfad=None, bestaetigt=None, nur_neue=False):
    """CSV lesen, Vorschau zeigen, nach Bestätigung übernehmen. bestaetigt/nur_neue ohne Dialog (Tests).
    Ergebnis: (Vorschau, (neu, geändert, Sicherung) oder None)."""
    if pfad is None:
        pfad, _ = QFileDialog.getOpenFileName(seite, "Kunden importieren", str(_ordner(seite)), "CSV (*.csv *.txt)")
        if not pfad:
            return None, None
    roh, vorhandene, kontext = Path(pfad).read_bytes(), db.zeilen("kunden"), db.kontext()

    def rechnen(nur):
        return kunden_csv.vorschau(roh, vorhandene, kontext, nur_neue=nur)
    if bestaetigt is None:
        d = KundenImportDialog(seite, rechnen, pfad)
        bestaetigt = d.exec() == QDialog.Accepted
        ergebnis = d.ergebnis
    else:
        ergebnis = rechnen(nur_neue)
    if not bestaetigt:
        return ergebnis, None
    return ergebnis, db.kunden_importieren(ergebnis["zeilen"])
