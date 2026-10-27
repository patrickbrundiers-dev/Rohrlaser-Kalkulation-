"""Reiter „Fertigung“ (fertigung.py): beauftragte Angebote mit Freigabe und Fertigungsstatus, Verlauf, Durchlaufzeiten,
Materialverbrauch je Charge und Export des Fertigungsauftrags (JSON/CSV). Nur mit Einstellung 'fertigung_aktiv'."""
import json

from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from . import fertigung, lager, stil
from .lager_seite import _fuellen, _tabelle

SPALTEN = (("Angebot", "nummer"), ("Kunde", "kunde"), ("Auftragsnr.", "auftragsnr"), ("Liefertermin", "liefertermin"),
           ("Status", "status"), ("seit", "am"), ("Freigabe-Version", "version"), ("Hinweis", "hinweis"))
VERLAUF = (("Zeitpunkt", "am"), ("Status", "status"), ("Kürzel", "wer"), ("Freigabe-Version", "version"),
           ("Bemerkung", "bemerkung"))
ZEITEN = (("Angebot", "nummer"), ("Status", "status"), ("Stunden", "h"))
CHARGEN = (("Charge", "charge"), ("Kennung", "kennung"), ("Profil-ID", "profil"), ("Werkstoff-ID", "werkstoff"),
           ("Angebot", "nummer"), ("Anzahl", "anzahl"), ("Länge [mm]", "laenge"), ("Zeit", "zeit"))


class FertigungSeite(QWidget):
    def __init__(self, fenster):
        super().__init__()
        self.f = fenster
        self.db = fenster.db
        self.zeilen = []
        self.liste = _tabelle(SPALTEN)
        self.liste.itemSelectionChanged.connect(self._auswahl)
        self.liste.doubleClicked.connect(lambda _i: self.oeffnen())
        self.status = QComboBox()
        self.bemerkung = QLineEdit()
        self.bemerkung.setPlaceholderText("Bemerkung (Pflicht beim Zurücksetzen und bei neuer Freigabe)")
        self.setzen_knopf = QPushButton("Status setzen")
        self.setzen_knopf.clicked.connect(lambda: self.setzen())
        oeffnen = QPushButton("Angebot öffnen")
        oeffnen.clicked.connect(self.oeffnen)
        self.export_knopf = QPushButton("Export (JSON/CSV) …")
        self.export_knopf.clicked.connect(lambda: self.exportieren())
        zeile = QHBoxLayout()
        for w in (QLabel("Neuer Status:"), self.status, self.bemerkung, self.setzen_knopf, oeffnen, self.export_knopf):
            zeile.addWidget(w)
        zeile.setStretch(2, 1)
        self.meldung = QLabel()
        self.meldung.setWordWrap(True)
        self.verlauf = _tabelle(VERLAUF)
        self.zeiten = _tabelle(ZEITEN)
        self.zeiten_info = QLabel()
        self.chargen = _tabelle(CHARGEN)
        self.charge_suche = QLineEdit()
        self.charge_suche.setPlaceholderText("Charge oder Kennung suchen")
        self.charge_suche.textChanged.connect(lambda _t: self._chargen())
        unten = QTabWidget()
        unten.addTab(self.verlauf, "Verlauf")
        z = QWidget()
        lz = QVBoxLayout(z)
        lz.addWidget(self.zeiten_info)
        lz.addWidget(self.zeiten)
        unten.addTab(z, "Durchlaufzeiten")
        c = QWidget()
        lc = QVBoxLayout(c)
        lc.addWidget(self.charge_suche)
        lc.addWidget(self.chargen)
        unten.addTab(c, "Materialverbrauch je Charge")
        self.unten = unten
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Beauftragte Angebote: Freigabe hält den Angebotsstand für die Werkstattpapiere fest; "
                             "jeder Statuswechsel steht im Verlauf."))
        lay.addWidget(self.liste, 2)
        lay.addLayout(zeile)
        lay.addWidget(self.meldung)
        lay.addWidget(unten, 1)

    def neu_laden(self):
        self.status.clear()
        self.status.addItems(fertigung.status_liste(self.db))
        self.zeilen = fertigung.uebersicht(self.db)
        for z in self.zeilen:
            z["hinweis"] = "nach Freigabe geändert – neu freigeben" if z["geaendert"] else ""
        _fuellen(self.liste, SPALTEN, self.zeilen)
        for r, z in enumerate(self.zeilen):
            if z["geaendert"]:
                for c in range(len(SPALTEN)):
                    self.liste.item(r, c).setBackground(QBrush(stil.farbe("#FFF6DB")))
        self._zeiten()
        self._chargen()
        self._auswahl()

    def markiert(self):
        r = self.liste.currentRow()
        return self.zeilen[r] if 0 <= r < len(self.zeilen) and self.liste.selectedItems() else None

    def waehlen(self, angebot_id):
        r = next(i for i, z in enumerate(self.zeilen) if z["id"] == angebot_id)
        self.liste.selectRow(r)
        self.liste.setCurrentCell(r, 0)

    def _auswahl(self):
        z = self.markiert()
        _fuellen(self.verlauf, VERLAUF, list(reversed(fertigung.verlauf(self.db, z["id"]))) if z else [])
        schreibbar = not self.db.nur_lesen
        self.setzen_knopf.setEnabled(bool(z) and schreibbar)
        self.export_knopf.setEnabled(bool(z))

    def setzen(self, status=None, bemerkung=None):
        """Status des markierten Auftrags setzen. Ergebnis: True oder False (Grund in self.meldung)."""
        z = self.markiert()
        if not z:
            return False
        try:
            fertigung.setzen(self.db, z["id"], status or self.status.currentText(),
                             self.bemerkung.text() if bemerkung is None else bemerkung)
        except fertigung.FertigungFehler as ex:
            self.meldung.setText(f"<span style='color:#B42318'>{ex}</span>")
            return False
        self.meldung.setText(f"{z['nummer']}: Status „{status or self.status.currentText()}“ gesetzt.")
        self.bemerkung.clear()
        aid = z["id"]
        self.neu_laden()
        self.waehlen(aid)
        return True

    def oeffnen(self):
        z = self.markiert()
        if z:
            self.f.angebot_oeffnen(z["id"])

    def _zeiten(self):
        d = fertigung.durchlaufzeiten(self.db)
        zeilen = [dict(nummer=a["nummer"], status=s, h=round(h, 2)) for a in d["auftraege"]
                  for s, h in a["je_status"].items()]
        zeilen += [dict(nummer="Mittelwert", status=s, h=round(h, 2)) for s, h in d["mittel"].items()]
        _fuellen(self.zeiten, ZEITEN, zeilen)
        gesamt = [a["gesamt_h"] for a in d["auftraege"] if a["gesamt_h"] is not None]
        self.zeiten_info.setText(
            f"{d['fertig']} von {len(d['auftraege'])} Aufträgen fertig gemeldet"
            + (f", Durchlauf Freigabe bis Fertigmeldung im Mittel {sum(gesamt) / len(gesamt):.1f} h" if gesamt else "")
            + ". Zeit je Status = bis zum nächsten Wechsel; laufende Status zählen noch nicht.")

    def _chargen(self):
        such = self.charge_suche.text().strip().lower()
        zeilen = [z for z in lager.verbrauch_je_charge(self.db)
                  if not such or such in str(z.get("charge") or "").lower() or such in str(z.get("kennung") or "").lower()]
        _fuellen(self.chargen, CHARGEN, zeilen)

    def exportieren(self, pfad=None):
        """Fertigungsauftrag als JSON (und Positionen als CSV daneben) speichern. Ergebnis: Pfad oder None."""
        z = self.markiert()
        if not z:
            return None
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Fertigungsauftrag exportieren",
                                                  f"{z['nummer']} Fertigungsauftrag.json", "JSON (*.json)")
            if not pfad:
                return None
        daten = fertigung.export(self.db, z["id"], (self.db.angebot(z["id"]) or {}).get("ergebnis"))
        from pathlib import Path
        p = Path(pfad)
        p.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
        p.with_suffix(".csv").write_text(fertigung.export_csv(daten), encoding="utf-8-sig")
        self.meldung.setText(f"Export gespeichert: {p.name} und {p.with_suffix('.csv').name}")
        return p
