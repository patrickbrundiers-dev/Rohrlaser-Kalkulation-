"""Fenster „Verlauf“ (Patrick 01.11.2026, Paket D): wer hat wann was geändert – je Angebot (Angebotsliste → Vorgang →
Verlauf …) oder für Stammdaten und Einstellungen (Datei → Kollegen im gemeinsamen Ordner → Verlauf Stammdaten …).
Ein geändertes Feld lässt sich auf den alten Wert zurücksetzen (verlauf.darf_zurueckholen sagt, wer das darf)."""
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import aenderungsverlauf as verlauf

SPALTEN = ("Zeit", "Wer", "Was", "Feld", "Vorher", "Nachher")


def zeit_text(utc):
    t = verlauf._lokal(utc)
    return f"{t[8:10]}.{t[5:7]}.{t[:4]} {t[11:16]}" if len(t) >= 16 else str(utc or "")


def was_text(e):
    """Spalte „Was“: Angebot/Position oder die Stammdatenzeile."""
    if e.get("tabelle") == verlauf.ANGEBOT:
        z = e.get("ziel") or ""
        if z.startswith(verlauf.POS):
            if e.get("art") != verlauf.GEAENDERT:
                return f"Position {verlauf.ART_TEXT[e['art']]}"
            return "Position"
        if z == verlauf.STAFFELN:
            return "Staffeln geändert"
        return "Angebot neu" if e.get("art") == verlauf.NEU else "Angebotskopf"
    zusatz = "" if e.get("art") == verlauf.GEAENDERT else f" ({verlauf.ART_TEXT[e['art']]})"
    return f"{e.get('bezug') or e.get('tabelle')}{zusatz}"


class VerlaufDialog(QDialog):
    def __init__(self, fenster, angebot_id=None):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.angebot_uid, self.eintraege = None, []
        if angebot_id is not None:
            r = self.db.con.execute("SELECT uid, nummer FROM angebote WHERE id=?", (angebot_id,)).fetchone()
            self.angebot_uid = r[0] if r else ""
            self.setWindowTitle(f"Verlauf Angebot {r[1] if r else ''}")
        else:
            self.setWindowTitle("Verlauf Stammdaten und Einstellungen")
        self.resize(1000, 520)
        lay = QVBoxLayout(self)
        kopf = QLabel("Wer hat wann was geändert (letzte 12 Monate, alle Arbeitsplätze im gemeinsamen Ordner). "
                      "Ein geändertes Feld markieren und „Alten Wert zurückholen“ setzt den Wert von „Vorher“ wieder.")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Kürzel, Feld, Kunde, Wert …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.laden)
        lay.addWidget(self.suche)
        self.liste = QTableWidget(0, len(SPALTEN))
        self.liste.setHorizontalHeaderLabels(SPALTEN)
        self.liste.verticalHeader().setVisible(False)
        self.liste.setAlternatingRowColors(True)
        self.liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        k = self.liste.horizontalHeader()
        for sp in range(4):
            k.setSectionResizeMode(sp, QHeaderView.ResizeToContents)
        k.setSectionResizeMode(4, QHeaderView.Stretch)
        k.setSectionResizeMode(5, QHeaderView.Stretch)
        self.liste.itemSelectionChanged.connect(self._knoepfe)
        lay.addWidget(self.liste, 1)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        lay.addWidget(self.hinweis)
        zeile = QHBoxLayout()
        self.zurueck = QPushButton("Alten Wert zurückholen")
        self.zurueck.clicked.connect(self._zurueckholen)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        zeile.addWidget(self.zurueck)
        zeile.addStretch(1)
        zeile.addWidget(zu)
        lay.addLayout(zeile)
        self.laden()

    def laden(self):
        text = self.suche.text().strip()
        if self.angebot_uid is not None:
            self.eintraege = verlauf.eintraege(self.db.con, verlauf.ANGEBOT, self.angebot_uid or "-", text=text)
        else:
            self.eintraege = verlauf.eintraege(self.db.con, ohne_angebote=True, text=text)
        self.liste.setRowCount(0)
        for e in self.eintraege:
            z = self.liste.rowCount()
            self.liste.insertRow(z)
            werte = (zeit_text(e["zeit"]), e["wer"] or "", was_text(e),
                     verlauf.feld_titel(e) if e.get("feld") else "",
                     verlauf.wert_text(e["alt"]) if e.get("art") == verlauf.GEAENDERT else "",
                     verlauf.wert_text(e["neu"]) if e.get("art") == verlauf.GEAENDERT else "")
            if e.get("ziel", "").startswith(verlauf.POS) and e.get("art") != verlauf.GEAENDERT:
                werte = werte[:3] + ("", verlauf.wert_text(e["alt"]), verlauf.wert_text(e["neu"]))
            for sp, t in enumerate(werte):
                it = QTableWidgetItem(t)
                if sp in (4, 5):
                    it.setToolTip(verlauf.wert_text(e["alt" if sp == 4 else "neu"], 2000))
                self.liste.setItem(z, sp, it)
        if not self.eintraege:
            self.hinweis.setText("Noch keine Änderungen vermerkt. Der Verlauf beginnt mit dem ersten Abgleich nach "
                                 "dem Update." if not text else "Nichts gefunden.")
        else:
            self.hinweis.setText(f"{len(self.eintraege)} Einträge.")
        self._knoepfe()

    def _gewaehlt(self):
        r = self.liste.currentRow()
        return self.eintraege[r] if 0 <= r < len(self.eintraege) and self.liste.selectedItems() else None

    def _knoepfe(self):
        e = self._gewaehlt()
        ja, grund = verlauf.darf_zurueckholen(self.db, e) if e else (False, "Erst eine Zeile wählen.")
        self.zurueck.setEnabled(ja)
        self.zurueck.setToolTip(grund or "Den Wert aus „Vorher“ wieder eintragen")

    def _zurueckholen(self):
        e = self._gewaehlt()
        if e is None:
            return
        if not self.f.stumm and QMessageBox.question(
                self, "Alten Wert zurückholen",
                f"{verlauf.feld_titel(e)} wieder auf „{verlauf.wert_text(e['alt'])}“ setzen?") != QMessageBox.Yes:
            return
        try:
            verlauf.zurueckholen(self.db, e)
        except PermissionError as fehler:
            QMessageBox.warning(self, "Alten Wert zurückholen", str(fehler))
            return
        self.f.meldung(f"{verlauf.feld_titel(e)} zurückgeholt: „{verlauf.wert_text(e['alt'])}“. Der nächste Abgleich "
                       "gibt es an die Kollegen weiter.")
        self._neu_laden()
        self.laden()

    def _neu_laden(self):
        f = self.f
        if hasattr(f, "alles_neu_laden"):
            f.alles_neu_laden()


def zeigen(fenster, angebot_id=None):
    d = VerlaufDialog(fenster, angebot_id)
    if not fenster.stumm:
        d.exec()
    return d
