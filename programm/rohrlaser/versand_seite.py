"""Reiter „Versand“ (Plan Palettenbegleitschein P3, ersetzt die Auftragsübersicht des Tools v97): alle eigenen
beauftragten Angebote mit Lieferdatum, Paletten und Stand. Filter wie im Tool (aktuell, überfällig, heute, morgen,
diese Woche, in Bearbeitung, verladebereit, versendet, alle, archiviert), Mehrfachauswahl mit Verladebereit,
Versendet, Lieferdatum setzen, Archivieren, Sammeldruck der Palettenscheine und Verladeliste (PDF)."""
import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import feiertage, palettenschein, palettenschein_dialog, pdf, protokoll

SPALTEN = ("Angebot", "Kunde", "Bestellnummer", "Lieferdatum", "Paletten", "Stück", "Stand", "Gedruckt",
           "Versendet am")
FARBE = {"Überfällig": "#FDECEA", "Heute": "#FFF6DB", "Verladebereit": "#E3F4E8", "Versendet": "#ECEEF1"}


def _datum(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y") if iso else ""
    except ValueError:
        return str(iso)


class VersandSeite(QWidget):
    titel = "Versand"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.zeilen = []
        self.filter = QComboBox()
        self.filter.setToolTip("Aufträge nach Lieferdatum und Stand zeigen")
        self.filter.currentIndexChanged.connect(self.neu_laden)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen nach Angebot, Kunde, Bestellnummer …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.neu_laden)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Zeigen:"))
        oben.addWidget(self.filter)
        oben.addWidget(self.suche, 1)
        knoepfe = QHBoxLayout()
        for text, ziel, tip in (
                ("Palettenschein …", self.schein_oeffnen, "Palettenbegleitschein des markierten Auftrags bearbeiten"),
                ("Palettenscheine drucken", self.drucken, "Scheine aller markierten Aufträge in ein PDF"),
                ("Verladeliste", self.verladeliste, "Liste der markierten Aufträge mit Paletten und Gewicht (PDF)"),
                ("✓ Verladebereit", lambda: self.status_alle(palettenschein.VERLADEBEREIT),
                 "Markierte Aufträge: Fertig zur Verladung"),
                ("✓ Versendet", lambda: self.status_alle(palettenschein.VERSENDET),
                 "Markierte Aufträge als versendet abschließen (mit Datum)"),
                ("Lieferdatum …", self.lieferdatum, "Lieferdatum der markierten Aufträge setzen"),
                ("Archivieren", self.archivieren, "Markierte Aufträge aus der Übersicht nehmen (Archiviert: "
                                                   "zurückholen)"),
                ("Angebot öffnen", self.angebot_oeffnen, "Angebot des markierten Auftrags öffnen")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            if text == "Palettenschein …":
                b.setObjectName("primaer")
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabelle.doubleClicked.connect(lambda _: self.schein_oeffnen())
        self.tabelle.verticalHeader().setVisible(False)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addLayout(knoepfe)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(self.info)
        self.neu_laden()

    # ------------------------------------------------ Liste
    def _packliste(self, z, stamm):
        """Anzahl Paletten und Packliste je Auftrag."""
        d = z["schein"]
        if d.get("unbekannt"):
            return None, None
        try:
            alles = palettenschein.zusammenstellen(self.db, z["id"], dict(d), stamm)
        except Exception as e:  # noqa: BLE001 – beschädigtes Angebot: Liste trotzdem zeigen
            protokoll.nebenbei(e, "Palettenschein zusammenstellen")
            return None, None
        return palettenschein.anzahl(d, alles["packliste"]), alles["packliste"]

    def neu_laden(self, *_):
        heute = datetime.date.today()
        alle = self.db.versand_auftraege()
        such = self.suche.text().strip().lower()
        if such:
            alle = [z for z in alle if such in " ".join(str(z.get(n) or "") for n in
                                                        ("nummer", "kunde", "kundennr", "auftragsnr")).lower()]
        zaehler = {f: sum(1 for z in alle if palettenschein.passt(z, z["schein"], f, heute))
                   for f in palettenschein.FILTER}
        alt = self.filter.currentData() or "Aktuell"
        self.filter.blockSignals(True)
        self.filter.clear()
        for f in palettenschein.FILTER:
            self.filter.addItem(f"{f} ({zaehler[f]})", f)
        self.filter.setCurrentIndex(max(0, list(palettenschein.FILTER).index(alt)))
        self.filter.blockSignals(False)
        zeilen = sorted((z for z in alle if palettenschein.passt(z, z["schein"], alt, heute)),
                        key=lambda z: palettenschein.reihenfolge(z, z["schein"], heute))
        self.zeilen = zeilen
        self.tabelle.setRowCount(len(zeilen))
        stamm = palettenschein.stammdaten(self.db) if zeilen else None
        land = self.db.einstellung("versand_bundesland")
        for r, z in enumerate(zeilen):
            d = z["schein"]
            n, pl = self._packliste(z, stamm)
            z["_paletten"], z["_packliste"] = n, pl
            termin = palettenschein._datum(z.get("liefertermin"))
            fh = feiertage.hinweis(termin, land) if termin else ""
            werte = [z.get("nummer"), z.get("kunde"), z.get("auftragsnr"),
                     _datum(z.get("liefertermin")) + (f" ({fh})" if fh else ""),
                     "?" if d.get("unbekannt") else (n or ""), (pl or {}).get("gesamt_stueck") or "",
                     palettenschein.stand(d), _datum(d.get("gedruckt_am")), _datum(d.get("versendet_am"))]
            if palettenschein.ist_versendet(d):
                farbe = FARBE["Versendet"]
            elif palettenschein.ist_verladebereit(d):
                farbe = FARBE["Verladebereit"]
            elif termin and termin < heute:
                farbe = FARBE["Überfällig"]
            elif termin == heute:
                farbe = FARBE["Heute"]
            else:
                farbe = None
            for c, w in enumerate(werte):
                it = QTableWidgetItem("" if w is None else str(w))
                it.setData(Qt.UserRole, z["id"])
                if c in (4, 5):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if farbe and c in (3, 6):
                    it.setBackground(QColor(farbe))
                self.tabelle.setItem(r, c, it)
        self.tabelle.resizeColumnsToContents()
        self.tabelle.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        summe = sum(z.get("_paletten") or 0 for z in zeilen)
        self.info.setText(f"{len(zeilen)} Aufträge · {summe} Paletten. Aufträge erscheinen hier, sobald ein Angebot "
                          "auf „Beauftragt“ steht (Angebote › Vorgang ▾). Doppelklick öffnet den Palettenschein.")

    def gewaehlt(self):
        ids = []
        for i in sorted({ix.row() for ix in self.tabelle.selectedIndexes()}):
            it = self.tabelle.item(i, 0)
            if it is not None:
                ids.append(it.data(Qt.UserRole))
        return ids

    def waehlen(self, ids):
        """Zeilen dieser Angebote markieren (Tests, Rücksprung)."""
        self.tabelle.clearSelection()
        mode = self.tabelle.selectionMode()
        self.tabelle.setSelectionMode(QAbstractItemView.MultiSelection)
        for r in range(self.tabelle.rowCount()):
            if self.tabelle.item(r, 0).data(Qt.UserRole) in ids:
                self.tabelle.selectRow(r)
        self.tabelle.setSelectionMode(mode)

    def _keine(self):
        self.f.meldung("Bitte zuerst einen oder mehrere Aufträge markieren.", fehler=True)

    # ------------------------------------------------ Aktionen
    def schein_oeffnen(self):
        ids = self.gewaehlt()
        if not ids:
            return self._keine()
        return palettenschein_dialog.oeffnen(self.f, ids[0], self)

    def drucken(self):
        ids = self.gewaehlt()
        if not ids:
            return self._keine()
        pfad = palettenschein_dialog.scheine_drucken(self.f, ids)
        self.neu_laden()
        return pfad

    def verladeliste(self, pfad=None):
        ids = self.gewaehlt()
        if not ids:
            return self._keine()
        nach_id = {z["id"]: z for z in self.zeilen}
        zeilen = []
        for i in ids:
            z = nach_id[i]
            pl = z.get("_packliste") or {}
            gewicht = sum(p["brutto"] for p in pl.get("paletten") or ()) if z["schein"].get("paletten_auto") else None
            zeilen.append(dict(auftrag=z.get("nummer"), kunde=z.get("kunde"), bestellnummer=z.get("auftragsnr"),
                               lieferdatum=z.get("liefertermin"), paletten=z.get("_paletten"),
                               stueck=pl.get("gesamt_stueck"), gewicht=gewicht or None,
                               stand=palettenschein.stand(z["schein"])))
        try:
            pfad = pfad or self.f.ablage() / f"Verladeliste {datetime.datetime.now():%Y-%m-%d %H%M}.pdf"
            pdf.verladeliste_pdf(pfad, zeilen, self.db.einstellungen())
        except (OSError, PermissionError) as e:
            if not self.f.stumm:
                QMessageBox.warning(self, "Verladeliste", f"Die Datei konnte nicht gespeichert werden:\n{e}")
            return None
        self.f.meldung(f"Verladeliste gespeichert: {pfad}")
        self.f.datei_oeffnen(pfad)
        return pfad

    def status_alle(self, status):
        ids = self.gewaehlt()
        if not ids:
            return self._keine()
        if self.db.nur_lesen:
            return None
        for i in ids:
            d = self.db.palettenschein(i)
            palettenschein.status_setzen(d, status, True)
            self.db.palettenschein_speichern(i, d)
        self.f.meldung(f"{len(ids)} Auftrag/Aufträge: {status}.")
        self.neu_laden()
        self.waehlen(ids)
        return len(ids)

    def lieferdatum(self, datum=None):
        ids = self.gewaehlt()
        if not ids:
            return self._keine()
        if datum is None:
            dlg = QDialog(self)
            dlg.setWindowTitle("Lieferdatum setzen")
            feld = QDateEdit(QDate.currentDate())
            feld.setCalendarPopup(True)
            feld.setDisplayFormat("dd.MM.yyyy")
            kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            kn.accepted.connect(dlg.accept)
            kn.rejected.connect(dlg.reject)
            lay = QVBoxLayout(dlg)
            lay.addWidget(QLabel(f"Lieferdatum für {len(ids)} markierte Aufträge:"))
            lay.addWidget(feld)
            lay.addWidget(kn)
            if dlg.exec() != QDialog.Accepted:
                return None
            datum = feld.date().toPython()
        for i in ids:
            a = self.db.angebot(i)
            self.db.auftrag_setzen(i, a.get("auftragsnr"), datum.isoformat())
        self.neu_laden()
        self.waehlen(ids)
        return len(ids)

    def archivieren(self):
        ids = self.gewaehlt()
        if not ids:
            return self._keine()
        zurueck = self.filter.currentData() == "Archiviert"
        for i in ids:
            d = self.db.palettenschein(i)
            d["archiviert"] = not zurueck
            self.db.palettenschein_speichern(i, d)
        self.f.meldung(f"{len(ids)} Auftrag/Aufträge {'zurückgeholt' if zurueck else 'archiviert'}.")
        self.neu_laden()
        return len(ids)

    def angebot_oeffnen(self):
        ids = self.gewaehlt()
        if not ids:
            return self._keine()
        return self.f.angebot_oeffnen(ids[0])
