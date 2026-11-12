"""Reiter „Fertigung“ (fertigung.py): beauftragte Angebote mit Freigabe und Fertigungsstatus, Verlauf, Durchlaufzeiten,
Materialverbrauch je Charge und Export des Fertigungsauftrags (JSON/CSV); Etiketten mit QR-Code und Rückmeldung per
Scan (etiketten.py). Nur mit Einstellung 'fertigung_aktiv'."""
import json

from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import etiketten, fertigung, lager, leerhinweis, stil
from .klartext import fehler_text
from .lager_seite import _fuellen, _tabelle

SPALTEN = (("Angebot", "nummer"), ("Kunde", "kunde"), ("Auftragsnr.", "auftragsnr"), ("ab Werk", "liefertermin"),
           ("frei Haus", "liefertermin_frei_haus"), ("Status", "status"), ("seit", "am"), ("Freigabe-Version", "version"), ("Hinweis", "hinweis"))
VERLAUF = (("Zeitpunkt", "am"), ("Status", "status"), ("Kürzel", "wer"), ("Freigabe-Version", "version"),
           ("Bemerkung", "bemerkung"))
RUECKMELDUNG = (("Pos.", "pos"), ("Artikel", "artikel"), ("Stück", "stueck"))
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
        leerhinweis.setzen(self.liste, "Noch keine beauftragten Angebote. Ein Angebot erscheint hier, sobald es "
                                       "beauftragt ist.")
        self.liste.itemSelectionChanged.connect(self._auswahl)
        self.liste.doubleClicked.connect(lambda _i: self.oeffnen())
        self.status = QComboBox()
        self.status.setSizeAdjustPolicy(QComboBox.AdjustToContents)    # „Freigegeben“ ganz sichtbar (11.11.2026)
        self.bemerkung = QLineEdit()
        self.bemerkung.setPlaceholderText("Bemerkung (Pflicht bei Zurücksetzen und neuer Freigabe)")
        self.setzen_knopf = QPushButton("Status setzen")
        self.setzen_knopf.clicked.connect(lambda: self.setzen())
        oeffnen = QPushButton("Angebot öffnen")
        oeffnen.clicked.connect(self.oeffnen)
        self.export_knopf = QPushButton("Export (JSON/CSV) …")
        self.export_knopf.clicked.connect(lambda: self.exportieren())
        # Etiketten mit QR-Code und Rückmeldung per Scan (Plan 29.10.2026 2a)
        self.etiketten_knopf = QPushButton("Etiketten …")
        self.etiketten_knopf.setToolTip("Etiketten mit QR-Code für die Positionen des markierten Auftrags (PDF)")
        self.etiketten_knopf.clicked.connect(lambda: self.etiketten())
        self.scan_knopf = QPushButton("Scannen …")
        self.scan_knopf.setToolTip("Rückmeldung per Handscanner: Arbeitsschritt wählen und Etiketten scannen")
        self.scan_knopf.clicked.connect(lambda: self.scannen())
        # Fertigungslos (Plan ArTube-Unterlagen A2, 12.11.2026): mehrere Aufträge gemeinsam schneiden
        self.los_knopf = QPushButton("Fertigungslos …")
        self.los_knopf.setToolTip("Mehrere beauftragte Aufträge gemeinsam optimieren: weniger Stangen, ein "
                                  "Schnittplan für die Werkstatt; die Angebotspreise bleiben")
        self.los_knopf.clicked.connect(lambda: self.fertigungslos())
        # Plan PROfirst I1/I2 (12.11.2026): geschnittene Stangen melden, Restplan, Teil in Stangenplänen suchen
        self.stangen_knopf = QPushButton("Stangen melden …")
        self.stangen_knopf.setToolTip("Geschnittene Stangen des markierten Auftrags melden (Nummern wie im Schnittplan, "
                                      "z. B. 1-3, 5): die Teile darauf zählen als geschnitten, offen bleibt der Rest")
        self.stangen_knopf.clicked.connect(lambda: self.stangen_melden())
        self.rest_knopf = QPushButton("Restplan …")
        self.rest_knopf.setToolTip("Werkstattpapiere nur für die noch offenen Mengen (Angebot bleibt unverändert)")
        self.rest_knopf.clicked.connect(lambda: self.restplan())
        suche = QPushButton("Teil suchen …")
        suche.setToolTip("Artikelnummer oder Bezeichnung in allen beauftragten Stangenplänen suchen")
        suche.clicked.connect(lambda: self.teil_suchen())
        auslastung = QPushButton("Auslastung …")       # Wochenauslastung je Maschine (Plan 29.10.2026 2b)
        auslastung.setToolTip("Maschinenzeit der Aufträge je Woche gegen den Schichtkalender: Wochenbalken, Plantafel")
        auslastung.clicked.connect(lambda: self.auslastung_zeigen())
        zeile = QHBoxLayout()
        for w in (QLabel("Neuer Status:"), self.status, self.bemerkung, self.setzen_knopf, oeffnen, self.export_knopf,
                  self.etiketten_knopf, self.scan_knopf, auslastung):
            zeile.addWidget(w)
        zeile.setStretch(2, 1)
        zeile2 = QHBoxLayout()          # Plan PROfirst I1/I2: eigene Zeile, damit die Seite bei 1024 px nicht abschneidet
        for w in (self.stangen_knopf, self.rest_knopf, suche, self.los_knopf):
            zeile2.addWidget(w)
        zeile2.addStretch(1)
        self.meldung = QLabel()
        self.meldung.setWordWrap(True)
        self.verlauf = _tabelle(VERLAUF)
        leerhinweis.setzen(self.verlauf, "Oben ein Angebot wählen: hier steht dann jeder Statuswechsel.")
        self.zeiten = _tabelle(ZEITEN)
        leerhinweis.setzen(self.zeiten, "Noch keine Durchlaufzeiten.")
        self.zeiten_info = QLabel()
        self.chargen = _tabelle(CHARGEN)
        leerhinweis.setzen(self.chargen, "Noch kein Materialverbrauch mit Charge.")
        self.charge_suche = QLineEdit()
        self.charge_suche.setPlaceholderText("Charge oder Kennung suchen")
        self.charge_suche.textChanged.connect(lambda _t: self._chargen())
        unten = QTabWidget()
        unten.addTab(self.verlauf, "Verlauf")
        self.rueckmeldungen = _tabelle(RUECKMELDUNG)
        unten.addTab(self.rueckmeldungen, "Rückmeldungen")
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
        auftraege = QWidget()
        lay = QVBoxLayout(auftraege)
        lay.addWidget(QLabel("Beauftragte Angebote: Freigabe hält den Angebotsstand für die Werkstattpapiere fest; "
                             "jeder Statuswechsel steht im Verlauf."))
        lay.addWidget(self.liste, 2)
        lay.addLayout(zeile)
        lay.addLayout(zeile2)
        lay.addWidget(self.meldung)
        lay.addWidget(unten, 1)
        # Seite Auslastung (Plan Maschinenauslastung 10.11.2026): Wochenbalken und Plantafel, gerechnet beim ersten Öffnen
        from . import funktionen
        from .auslastung_ansicht import AuslastungAnsicht
        self.auslastung = AuslastungAnsicht(fenster)
        self.seiten = QTabWidget()
        self.seiten.addTab(auftraege, "Aufträge")
        from PySide6.QtWidgets import QFrame, QScrollArea
        rollen = QScrollArea()          # schmales Fenster (1024 px): rollen statt das Hauptfenster breiter zu machen
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QFrame.NoFrame)
        rollen.setWidget(self.auslastung)
        self.seiten.addTab(rollen, "Auslastung")
        self.seiten.setTabVisible(1, funktionen.an("funktion_auslastung", self.db))
        self.seiten.currentChanged.connect(lambda i: self.auslastung.laden() if i == 1 else None)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(self.seiten)

    def fertigungslos(self, dialog=None):
        """Dialog Fertigungslos (fertigungslos_dialog); der markierte Auftrag ist vorgewählt."""
        from .fertigungslos_dialog import FertigungslosDialog
        z = self.markiert()
        d = dialog or FertigungslosDialog(self, self.db, vorauswahl=(z["id"],) if z else ())
        if dialog is None:
            d.exec()
        return d

    def auslastung_zeigen(self):
        """Unterseite Auslastung nach vorn (Knopf „Auslastung …“, Kachel der Startseite)."""
        if self.seiten.currentIndex() == 1:
            self.auslastung.laden()
        self.seiten.setCurrentIndex(1)

    def neu_laden(self):
        from . import funktionen
        self.seiten.setTabVisible(1, funktionen.an("funktion_auslastung", self.db))
        if self.seiten.currentIndex() == 1 and self.auslastung.geladen:
            self.auslastung.laden()
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
        self._rueckmeldungen(z)
        schreibbar = not self.db.nur_lesen
        self.setzen_knopf.setEnabled(bool(z) and schreibbar)
        self.export_knopf.setEnabled(bool(z))
        self.etiketten_knopf.setEnabled(bool(z))
        self.scan_knopf.setEnabled(schreibbar)
        self.stangen_knopf.setEnabled(bool(z) and schreibbar)
        self.rest_knopf.setEnabled(bool(z))

    def _rueckmeldungen(self, z):
        """Je Position die gemeldete Menge je Arbeitsschritt ('8 / 10'), vollständige grün."""
        schritte = etiketten.schritte(self.db)
        t = self.rueckmeldungen
        t.setColumnCount(3 + len(schritte) + 1)
        t.setHorizontalHeaderLabels(["Pos.", "Artikel", "Stück", *schritte, "zuletzt"])
        stand = etiketten.stand_je_position(self.db, z["id"]) if z else []
        t.setRowCount(len(stand))
        gruen = QBrush(stil.farbe("#E3F4E8"))
        for r, p in enumerate(stand):
            werte = [p["pos"], p["artikel"] or "", etiketten._z(p["stueck"] or 0)]
            werte += [f"{etiketten._z(p['schritte'].get(s, 0))} / {etiketten._z(p['stueck'] or 0)}"
                      if p["schritte"].get(s) else "" for s in schritte]
            werte.append((p["zuletzt"] or "").replace("T", " "))
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                s = schritte[c - 3] if 3 <= c < 3 + len(schritte) else None
                if s and p["schritte"].get(s, 0) >= (p["stueck"] or 0) > 0:
                    it.setBackground(gruen)
                t.setItem(r, c, it)
        t.resizeColumnsToContents()

    def etiketten(self, dialog=None):
        """Etiketten des markierten Auftrags (etiketten_dialog.drucken). Ergebnis: Pfad oder None."""
        z = self.markiert()
        if not z:
            return None
        from . import etiketten_dialog
        return etiketten_dialog.drucken(self.f, z["id"], self, dialog)

    def scannen(self):
        """Fenster für die Rückmeldung per Scan (bleibt offen; Ergebnis: der Dialog)."""
        from .etiketten_dialog import ScanDialog
        d = ScanDialog(self.f)
        d.finished.connect(lambda _r: self.neu_laden())
        if not self.f.stumm:
            d.show()
        return d

    def setzen(self, status=None, bemerkung=None):
        """Status des markierten Auftrags setzen. Ergebnis: True oder False (Grund in self.meldung)."""
        z = self.markiert()
        if not z:
            return False
        try:
            fertigung.setzen(self.db, z["id"], status or self.status.currentText(),
                             self.bemerkung.text() if bemerkung is None else bemerkung)
        except fertigung.FertigungFehler as ex:
            self.meldung.setText(f"<span style='color:#B42318'>{fehler_text(ex)}</span>")
            return False
        self.meldung.setText(f"{z['nummer']}: Status „{status or self.status.currentText()}“ gesetzt.")
        self.bemerkung.clear()
        aid = z["id"]
        self.neu_laden()
        self.waehlen(aid)
        return True

    def stangen_melden(self, text=None):
        """Plan PROfirst I2: geschnittene Stangen des markierten Auftrags melden. Ergebnis: rueckverfolgung-Ergebnis
        oder None."""
        from . import rueckverfolgung as rv
        z = self.markiert()
        if not z:
            return None
        schon = rv.gemeldet(self.db, z["id"])
        if text is None:
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(self, "Stangen melden", "Geschnittene Stangen (Nummern im Schnittplan, "
                                            "z. B. 1-3, 5)" + (f"\nschon gemeldet: {rv.stangen_text(schon)}"
                                                              if schon else "") + ":")
            if not ok:
                return None
        try:
            erg = rv.stangen_melden(self.db, z["id"], rv.nummern_lesen(text))
        except ValueError as e:
            self.meldung.setText(str(e))
            return None
        offen = sum(o["offen"] for o in rv.offen(self.db, z["id"]))
        self.meldung.setText(erg["text"] + (f" Noch offen: {offen} Teile (Restplan …)." if offen else
                                            " Alle Teile geschnitten."))
        self._rueckmeldungen(z)
        return erg

    def restplan(self, pfad=None):
        """Plan PROfirst I2: Werkstattpapiere nur für die offenen Mengen. Ergebnis: Pfad oder None."""
        from . import ausgabe, pdf, rueckverfolgung as rv
        z = self.markiert()
        if not z:
            return None
        r = rv.restplan(self.db, z["id"])
        if r is None:
            self.meldung.setText("Nichts mehr offen: alle Teile sind geschnitten gemeldet.")
            return None
        kopf, rest, erg = r
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Restplan speichern", f"{z['nummer']} Restplan.pdf",
                                                  "PDF (*.pdf)")
            if not pfad:
                return None
        k, tab = rechnen_kontext(self.db, kopf)
        wp = ausgabe.werkstatt(kopf, rest, erg, k, tab)
        pdf.werkstatt_pdf(pfad, dict(kopf, nummer=f"{kopf.get('nummer') or ''} Rest"), wp, True, self.db.einstellungen())
        self.meldung.setText(f"Restplan gespeichert: {len(erg['stangen'])} Stangen für "
                             f"{sum(p['stueck'] for p in rest)} offene Teile.")
        return pfad

    def teil_suchen(self, text=None, dialog=True):
        """Plan PROfirst I1: Teil in früheren Stangenplänen suchen. Ergebnis: Trefferliste."""
        from . import rueckverfolgung as rv
        if text is None:
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(self, "Teil suchen", "Artikelnummer oder Bezeichnung:")
            if not ok:
                return []
        treffer = rv.suchen(self.db, text)
        if dialog and not self.f.stumm:
            TrefferDialog(self, treffer, text).exec()
        self.meldung.setText(f"{len(treffer)} Treffer für „{text}“ in beauftragten Stangenplänen.")
        return treffer

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
        p.with_suffix(".csv").write_text(fertigung.export_csv(daten), encoding="utf-8-sig", newline="")
        self.meldung.setText(f"Export gespeichert: {p.name} und {p.with_suffix('.csv').name}")
        return p


def rechnen_kontext(db, kopf):
    from . import rechnen
    return rechnen.preisbasis_anwenden(kopf, db.kontext(), db.tabellen())


TREFFER = (("Datum", "datum"), ("Angebot", "nummer"), ("Kunde", "kunde"), ("Pos.", "pos"), ("Artikel", "artikel"),
           ("Bezeichnung", "bezeichnung"), ("Stück", "stueck"), ("Profil", "profil"), ("Stangen", "stangen_text"))


class TrefferDialog(QDialog):
    """Treffer der Teilesuche (I1); Doppelklick öffnet das Angebot."""

    def __init__(self, seite, treffer, text):
        from . import rueckverfolgung as rv
        super().__init__(seite)
        self.setWindowTitle(f"Teil „{text}“ in Stangenplänen")
        self.resize(900, 420)
        self.treffer = [dict(t, stangen_text=rv.stangen_text(t["stangen"])) for t in treffer]
        tab = _tabelle(TREFFER)
        leerhinweis.setzen(tab, "Kein beauftragter Stangenplan mit diesem Teil.")
        _fuellen(tab, TREFFER, self.treffer)
        tab.doubleClicked.connect(lambda i: (seite.f.angebot_oeffnen(self.treffer[i.row()]["angebot_id"]),
                                             self.accept()))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Doppelklick öffnet das Angebot; dort lässt sich der Plan neu einplanen."))
        lay.addWidget(tab)
