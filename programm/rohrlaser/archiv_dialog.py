"""Datei → „Alte Angebote archivieren …“ und „Archiv durchsuchen …“ (archiv.py, Vorschlag 5b 28.10.2026).

Archivieren: Anzahl je Jahr zeigen, nach Rückfrage erst eine geschützte Sicherung (vor_Archiv), dann verschieben.
Archiv durchsuchen: Suche über alle Archivdateien, gewähltes Angebot zurückholen (es öffnet sich danach)."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import archiv

SPALTEN = ("Jahr", "Nummer", "Datum", "Kunde", "Vorgang", "Positionen", "Netto €")


def archivieren(fenster, heute=None, rueckfrage=True):
    """Ablauf aus dem Datei-Menü. Ergebnis: {Jahr: Anzahl} oder None (nichts zu tun / abgebrochen)."""
    db = fenster.db
    kandidaten = archiv.kandidaten(db, heute, offen=set(fenster.offen))
    if not kandidaten:
        text = (f"Keine Angebote älter als {archiv.jahre_einstellung(db)} Jahre (Einstellungen → Ablage → Archiv). "
                "Geöffnete Angebote, Lageraufträge, Reservierungen und Angebote der Kollegen bleiben immer.")
        fenster.meldung("Nichts zu archivieren.")
        if rueckfrage and not fenster.stumm:
            QMessageBox.information(fenster, "Alte Angebote archivieren", text)
        return None
    n = sum(len(v) for v in kandidaten.values())
    if rueckfrage and not fenster.stumm:
        liste = "\n".join(f"   {j}: {len(v)} Angebote" for j, v in kandidaten.items())
        if QMessageBox.question(
                fenster, "Alte Angebote archivieren",
                f"{n} Angebote bis einschließlich {archiv.bis_jahr(db, heute)} ins Archiv verschieben?\n\n{liste}\n\n"
                "Vorher wird eine Sicherung erstellt. Archivierte Angebote stehen nicht mehr in der Angebotsliste, "
                "in den Wiederholteilen und in der Nachkalkulation; Datei → Archiv durchsuchen findet sie und holt "
                "sie bei Bedarf zurück.") != QMessageBox.Yes:
            return None
    _, fehler = db.sicherungen(zusatz="vor_Archiv")
    if fehler:
        fenster.meldung(fehler, fehler=True)
    ergebnis = archiv.archivieren(db, kandidaten)
    fenster.angebote.neu_laden()
    fenster.meldung(archiv.bericht(ergebnis))
    return ergebnis


class ArchivDialog(QDialog):
    """Archiv durchsuchen und Angebote zurückholen."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f = fenster
        self.zurueckgeholt = None
        self.setWindowTitle("Archiv durchsuchen")
        self.resize(900, 520)
        anzahl = archiv.anzahl(fenster.db)
        self.hinweis = QLabel(("Archiv: " + ", ".join(f"{j}: {k}" for j, k in anzahl.items()) + " Angebote. "
                               if anzahl else "Noch nichts archiviert. ") +
                              "Suche nach Nummer, Kunde, Kundennummer, Bemerkung, Artikel oder Bezeichnung; "
                              "Doppelklick oder „Zurückholen“ legt das Angebot wieder in die Angebotsliste.")
        self.hinweis.setWordWrap(True)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen …")
        self.suche.setClearButtonEnabled(True)
        self._zeitgeber = QTimer(self, singleShot=True, interval=300)
        self._zeitgeber.timeout.connect(self.laden)
        self.suche.textChanged.connect(lambda *_: self._zeitgeber.start())
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.verticalHeader().hide()
        self.tabelle.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabelle.doubleClicked.connect(lambda *_: self.zurueckholen())
        knoepfe = QDialogButtonBox()
        self.ok = knoepfe.addButton("Zurückholen", QDialogButtonBox.AcceptRole)
        knoepfe.addButton("Schließen", QDialogButtonBox.RejectRole)
        self.ok.clicked.connect(self.zurueckholen)
        knoepfe.rejected.connect(self.reject)
        self.ok.setEnabled(not fenster.db.nur_lesen)
        lay = QVBoxLayout(self)
        lay.addWidget(self.hinweis)
        lay.addWidget(self.suche)
        lay.addWidget(self.tabelle)
        lay.addWidget(knoepfe)
        self.zeilen = []
        self.laden()

    def laden(self):
        self.zeilen = archiv.suchen(self.f.db, self.suche.text().strip())
        self.tabelle.setRowCount(len(self.zeilen))
        for i, z in enumerate(self.zeilen):
            werte = (z["jahr"], z["nummer"], z["datum"], z["kunde"] or "", z["vorgang"], z["positionen"],
                     f"{z['vk_netto'] or 0:,.2f}".replace(",", " ").replace(".", ",").replace(" ", "."))
            for j, w in enumerate(werte):
                item = QTableWidgetItem(str(w))
                if j in (5, 6):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(i, j, item)
        self.tabelle.resizeColumnsToContents()
        if self.zeilen:
            self.tabelle.selectRow(0)

    def zurueckholen(self):
        i = self.tabelle.currentRow()
        if self.f.db.nur_lesen or not 0 <= i < len(self.zeilen):
            return None
        z = self.zeilen[i]
        try:
            neu = archiv.zurueckholen(self.f.db, z["jahr"], z["id"])
        except ValueError as e:
            if not self.f.stumm:
                QMessageBox.warning(self, "Archiv", str(e))
            self.f.meldung(str(e), fehler=True)
            return None
        self.zurueckgeholt = neu
        self.f.angebote.neu_laden()
        self.f.meldung(f"Angebot {z['nummer']} aus dem Archiv {z['jahr']} zurückgeholt.")
        self.accept()
        return neu
