"""Seite „Auslastung“ (Plan Maschinenauslastung, Patrick 10.11.2026, Schritte 2 bis 4): Reiter Fertigung → Auslastung und
Datei → Maschinenauslastung.

Oben je Maschine die Wochenbalken (WochenBalken): grauer Rahmen = Kapazität der Woche, gefüllt = Laserzeit der
Aufträge (grün, ab 80 % gelb, über 100 % rot), schraffiert = verschickte Angebote gewichtet mit der Trefferquote,
links grau die gemessenen Stunden vergangener Wochen (Scans „Laser Start/Ende“). Zwei Sichten: „eingelastet“
(einlastung.py: Überlast rutscht in die Folgewoche) und „Terminwoche“ (auslastung.py: Laserzeit in der Woche des
Liefertermins minus Vorlauf). Darunter die Plantafel (lesend): je Maschine die Aufträge als Balken auf der Zeitachse
mit Liefertermin-Marke und Rahmen bei Terminrisiko; Doppelklick öffnet das Angebot. Rechts die Aufträge der gewählten
Woche bzw. die Aufträge mit Terminrisiko. Was-wäre-wenn ändert nur die Anzeige, nie die Daten."""
import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
                               QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import auslastung, einlastung, stil
from .auslastung_grafik import BALKEN, RISIKO_TEXT, Plantafel, WochenBalken, _datum, _h, spalten_daten, stufe  # noqa: F401

FARBEN = {"gruen": "#E3F4E8", "gelb": "#FFF2CC", "rot": "#F8D7DA", "grau": "#F2F2F2"}      # Zellen der Zahlentabelle
SICHT_EIN, SICHT_TERMIN = "eingelastet (Überlast rutscht weiter)", "Terminwoche (Liefertermin minus Vorlauf)"
IST_WOCHEN = 4
MERKER = {}                    # Laserzeit je Angebot über mehrere Aufrufe (auslastung.berechnen, merker)
DETAIL_SPALTEN = ("Angebot", "Kunde", "Art", "Liefertermin", "Stunden", "geschnitten", "Gewicht", "Laser fertig",
                  "Puffer [AT]", "Terminrisiko")


class AuslastungAnsicht(QWidget):
    """Die ganze Seite; fenster = Hauptfenster (db, angebot_oeffnen)."""
    geoeffnet = Signal(object)

    def __init__(self, fenster, heute=None, parent=None):
        super().__init__(parent)
        self.f, self.heute = fenster, heute
        self.daten = self.ein = self.gem = self.ein_ohne = None
        self.szenario = einlastung.Szenario()
        self.auswahl = None                       # (Maschine, Spaltenschlüssel)
        self.auftrag = None                       # gewählte Angebots-ID
        self.wochen = QSpinBox()
        self.wochen.setRange(2, 26)
        self.wochen.setValue(8)
        self.wochen.setSuffix(" Wochen")
        self.wochen.valueChanged.connect(lambda _w: self.laden())
        self.sicht = QComboBox()
        self.sicht.addItems((SICHT_EIN, SICHT_TERMIN))
        self.sicht.setToolTip("eingelastet: Aufträge laufen ab heute nacheinander durch die freien Stunden, Überlast "
                              "rutscht in die Folgewoche.\nTerminwoche: die ganze Laserzeit steht in der Woche des "
                              "Liefertermins minus Vorlauf.")
        self.sicht.currentIndexChanged.connect(lambda _i: self.zeigen())
        self.offene = QCheckBox("verschickte Angebote gewichtet mit der Trefferquote")
        self.offene.setToolTip("Verschickte Angebote zählen mit Maschinenzeit × Trefferquote der letzten 12 Monate "
                               "(Datei → Angebots-Auswertung); Termin aus ihrer Lieferzeit ab heute.")
        self.offene.toggled.connect(lambda _a: self.laden())
        self.zoom = QComboBox()
        self.zoom.addItems(("Plantafel: alles", "Plantafel: Woche", "Plantafel: Monat"))
        self.zoom.currentIndexChanged.connect(lambda _i: self._zoom())
        neu = QPushButton("Aktualisieren")
        neu.clicked.connect(lambda: (MERKER.clear(), self.laden()))
        self.pdf_knopf = QPushButton("PDF …")
        self.pdf_knopf.setToolTip("Diese Seite als PDF für die Werkstattbesprechung")
        self.pdf_knopf.clicked.connect(lambda: self.pdf())
        oben = QHBoxLayout()
        for w in (QLabel("Zeitraum"), self.wochen, self.sicht, self.offene):
            oben.addWidget(w)
        oben.addStretch(1)
        self.uebergabe_knopf = QPushButton("Übergabe …")
        self.uebergabe_knopf.setToolTip("Schreibt die beauftragten Aufträge mit Maschine, Laserzeit und Liefertermin "
                                        "in eine CSV-Datei für das eigene Programm „Rohrlaser Auslastung“ (dort: "
                                        "CSV einlesen …). An den Daten der Kalkulation ändert sich nichts.")
        self.uebergabe_knopf.clicked.connect(lambda: self.uebergabe())
        for w in (self.zoom, neu, self.uebergabe_knopf, self.pdf_knopf):
            oben.addWidget(w)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.RichText)
        self.balken = WochenBalken()
        self.balken.gewaehlt.connect(self._woche_gewaehlt)
        self.tabelle = QTableWidget()
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.currentCellChanged.connect(lambda r, c, *_: self._zelle(r, c))
        self.oben_reiter = QTabWidget()
        rollen = QScrollArea()
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QScrollArea.NoFrame)
        rollen.setWidget(self.balken)
        self.oben_reiter.addTab(rollen, "Wochenbalken")
        self.oben_reiter.addTab(self.tabelle, "Zahlen (Terminwoche)")
        self.tafel = Plantafel()
        self.tafel.gewaehlt.connect(self._auftrag_gewaehlt)
        self.tafel.oeffnen.connect(self._oeffnen_id)
        self.tafel_rollen = QScrollArea()
        self.tafel_rollen.setWidgetResizable(True)
        self.tafel_rollen.setFrameShape(QScrollArea.NoFrame)
        self.tafel_rollen.setWidget(self.tafel)
        self.legende = QLabel()
        self.legende.setTextFormat(Qt.RichText)
        self.legende.setWordWrap(True)
        self.details_titel = QLabel()
        self.details_titel.setWordWrap(True)
        self.details = QTableWidget(0, len(DETAIL_SPALTEN))
        self.details.setHorizontalHeaderLabels(DETAIL_SPALTEN)
        self.details.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.details.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.details.verticalHeader().hide()
        self.details.doubleClicked.connect(self._oeffnen)
        self.details.itemSelectionChanged.connect(self._detail_gewaehlt)
        self.alle_knopf = QPushButton("Terminrisiko zeigen")
        self.alle_knopf.setToolTip("Alle Aufträge, deren Liefertermin knapp oder nicht zu halten ist")
        self.alle_knopf.clicked.connect(lambda: self._woche_gewaehlt(None, None))
        # Was-wäre-wenn (Schritt 4): ändert nur die Anzeige
        self.ww_maschine = QComboBox()
        self.ww_maschine_knopf = QPushButton("Auftrag testweise auf diese Maschine")
        self.ww_maschine_knopf.setToolTip("Den markierten Auftrag probeweise auf der gewählten Maschine einlasten "
                                          "(mit deren Laserzeit). Nichts wird gespeichert.")
        self.ww_maschine_knopf.clicked.connect(lambda: self.ww_verlegen())
        self.ww_stunden = QDoubleSpinBox()
        self.ww_stunden.setRange(0, 200)
        self.ww_stunden.setDecimals(1)
        self.ww_stunden.setSuffix(" h")
        self.ww_stunden.setValue(8.0)
        self.ww_zusatz_knopf = QPushButton("Zusatzstunden in gewählter Woche")
        self.ww_zusatz_knopf.setToolTip("So viele Stunden zusätzlich (Überstunden, Zusatzschicht) für die oben "
                                        "angeklickte Maschine und Woche annehmen. Nichts wird gespeichert.")
        self.ww_zusatz_knopf.clicked.connect(lambda: self.ww_zusatz())
        self.ww_samstag = QCheckBox("Samstag mit")
        self.ww_samstag_h = QDoubleSpinBox()
        self.ww_samstag_h.setRange(0, 24)
        self.ww_samstag_h.setDecimals(1)
        self.ww_samstag_h.setSuffix(" h")
        self.ww_samstag_h.setValue(6.0)
        self.ww_samstag.toggled.connect(lambda _a: self.ww_samstag_setzen())
        self.ww_samstag_h.valueChanged.connect(lambda _w: self.ww_samstag_setzen())
        self.ww_zurueck = QPushButton("Zurücksetzen")
        self.ww_zurueck.clicked.connect(lambda: self.ww_leeren())
        ww = QHBoxLayout()
        ww.addWidget(QLabel("<b>Was wäre, wenn …</b>"))
        for w in (self.ww_maschine, self.ww_maschine_knopf, self.ww_stunden, self.ww_zusatz_knopf, self.ww_samstag,
                  self.ww_samstag_h, self.ww_zurueck):
            ww.addWidget(w)
        ww.addStretch(1)
        self.ww_banner = QLabel()
        self.ww_banner.setWordWrap(True)
        self.ww_banner.setTextFormat(Qt.RichText)
        self.ww_banner.hide()
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.oben_reiter, 3)
        ll.addWidget(self.legende)
        ll.addWidget(self.tafel_rollen, 2)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        kopf = QHBoxLayout()
        kopf.addWidget(self.details_titel, 1)
        kopf.addWidget(self.alle_knopf)
        rl.addLayout(kopf)
        rl.addWidget(self.details, 1)
        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.addWidget(links)
        self.teiler.addWidget(rechts)
        self.teiler.setStretchFactor(0, 3)
        self.teiler.setStretchFactor(1, 2)
        self.teiler.setSizes([780, 520])
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.info)
        lay.addWidget(self.ww_banner)
        lay.addWidget(self.teiler, 1)
        lay.addLayout(ww)
        self.geladen = False

    # ---- Daten ----
    def sicht_ein(self):
        return self.sicht.currentIndex() == 0

    def laden(self):
        """Auslastung neu aus der Datendatei rechnen (dauert bei vielen Aufträgen einen Moment)."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.daten = auslastung.berechnen(self.f.db, self.heute, self.wochen.value(), self.offene.isChecked(),
                                              merker=MERKER)
            self.gem = einlastung.gemessen(self.f.db, self.daten["heute"], IST_WOCHEN, self.daten)
        finally:
            QApplication.restoreOverrideCursor()
        self.geladen = True
        self.ein_ohne = einlastung.rechnen(self.daten)
        self.ww_maschine.blockSignals(True)
        self.ww_maschine.clear()
        self.ww_maschine.addItems([m for m in self.daten["maschinen"] if m != "?"])
        self.ww_maschine.blockSignals(False)
        ids = {a["id"] for a in self.ein_ohne["auftraege"]}
        self.szenario.maschine = {i: v for i, v in self.szenario.maschine.items() if i in ids}
        self.zeigen()

    def zeigen(self):
        """Anzeige aus den geladenen Daten und dem Szenario aufbauen."""
        if self.daten is None:
            return
        d = self.daten
        self.ein = einlastung.rechnen(d, None if self.szenario.leer() else self.szenario)
        zeilen = spalten_daten(d, self.ein, self.gem if self.gem and self.gem["laeufe"] else None, self.sicht_ein())
        self.balken.setzen(zeilen, self.auswahl)
        self.tafel.setzen(d, self.ein, self.wochen.value(), self.auftrag)
        self._tabelle_fuellen()
        self._info()
        self._details()

    def _zoom(self):
        i = self.zoom.currentIndex()
        sicht = max(300, self.tafel_rollen.viewport().width() - Plantafel.LINKS - 8)
        self.tafel.zoom(None if i == 0 else sicht / (7 if i == 1 else 31))

    def _info(self):
        d, e = self.daten, self.ein
        voll = [(m, titel) for m in d["maschinen"] for s, titel, mo in d["spalten"]
                if mo and (auslastung.quote(d["bedarf"].get((m, s), 0), d["kapazitaet"].get((m, s))) or 0) > 1]
        r = e["risiko"]
        if self.sicht_ein():
            text = ("Eingelastet: Die Aufträge laufen ab heute nacheinander (nach Liefertermin) durch die freien "
                    "Stunden des Schichtkalenders; was nicht in eine Woche passt, rutscht in die nächste.")
        else:
            text = ("Bedarf / Kapazität je Maschine und Woche: Laserzeit der beauftragten Aufträge in der Woche des "
                    "Liefertermins minus Vorlauf, Kapazität aus dem Schichtkalender (Einstellungen → Lager und "
                    "Fertigung, Maschinen).")
        if d["gewicht"] is not None:
            text += f" Verschickte Angebote zählen mit {d['gewicht'] * 100:.0f} %."
        rot = stil.umsetzen(stil.ROT)
        if r[einlastung.UEBER] or r[einlastung.KNAPP]:
            text += (f" <b style='color:{rot}'>Terminrisiko: {r[einlastung.UEBER]} nicht zu halten, "
                     f"{r[einlastung.KNAPP]} knapp.</b>")
        elif r[einlastung.OK]:
            text += " <b>Alle Liefertermine sind zu halten.</b>"
        if voll and not self.sicht_ein():
            text += f" <b style='color:{rot}'>Überlastet: " + ", ".join(f"{m} {w}" for m, w in voll) + ".</b>"
        if d["fehlt"]:
            text += f" Ohne Rechnung: {', '.join(f'{n} ({g})' for n, g in d['fehlt'])}."
        if self.gem is not None and not self.gem["laeufe"]:
            text += (" Gemessene Auslastung erscheint, sobald Aufträge mit „Laser Start“ und „Laser Ende“ gescannt "
                     "sind.")
        self.info.setText(text)
        self.legende.setText(
            f"<span style='color:{BALKEN['gruen']}'>■</span> Aufträge (ab 80 % <span style='color:{BALKEN['gelb']}'>■"
            f"</span>, über 100 % <span style='color:{BALKEN['rot']}'>■</span>) &nbsp; "
            f"<span style='color:{BALKEN['angebot']}'>▨</span> Angebote gewichtet &nbsp; "
            f"<span style='color:{BALKEN['ist']}'>■</span> gemessen &nbsp; ▢ Kapazität &nbsp; "
            "Plantafel: ▲ Liefertermin, roter Rahmen = Termin nicht zu halten, oranger Rahmen = knapp, "
            "Doppelklick öffnet das Angebot.")
        if self.szenario.leer():
            self.ww_banner.hide()
        else:
            v, n = self.ein_ohne["risiko"], r
            self.ww_banner.setText(
                f"<b>Was-wäre-wenn (nichts wird gespeichert):</b> {self.szenario.text()}. Terminrisiko vorher "
                f"{v[einlastung.UEBER]} nicht zu halten / {v[einlastung.KNAPP]} knapp, jetzt "
                f"<b>{n[einlastung.UEBER]} nicht zu halten / {n[einlastung.KNAPP]} knapp</b>.")
            self.ww_banner.setStyleSheet(f"background: {stil.umsetzen(stil.GELB_FLAECHE)}; color: "
                                         f"{stil.umsetzen(stil.GELB_TEXT)}; padding: 4px; border-radius: 3px;")
            self.ww_banner.show()

    def _tabelle_fuellen(self):
        d, t = self.daten, self.tabelle
        t.blockSignals(True)
        t.clear()
        t.setRowCount(len(d["maschinen"]))
        t.setColumnCount(len(d["spalten"]))
        t.setHorizontalHeaderLabels([titel + (f"\n{m.strftime('%d.%m.')}" if m else "") for _, titel, m in d["spalten"]])
        t.setVerticalHeaderLabels(d["maschinen"])
        for r, m in enumerate(d["maschinen"]):
            for c, (s, _, mo) in enumerate(d["spalten"]):
                b = d["bedarf"].get((m, s), 0.0)
                k = d["kapazitaet"].get((m, s)) if mo else None
                q = auslastung.quote(b, k) if k is not None else None
                if mo:
                    text = f"{_h(b)} / {_h(k)} h" + (f"\n{q * 100:.0f} %" if q is not None else "\nkeine Schicht")
                else:
                    text = f"{_h(b)} h" if b else ""
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignCenter)
                farbe = None
                if q is not None and b:
                    farbe = stufe(q)
                elif mo and k == 0 and b:
                    farbe = "rot"
                elif s == auslastung.UEBERFAELLIG and b:
                    farbe = "rot"
                elif not mo and b:
                    farbe = "grau"
                if farbe:
                    it.setBackground(QBrush(stil.farbe(FARBEN[farbe])))
                n = len(d["auftraege"].get((m, s), ()))
                gesperrt = auslastung.gesperrt_text(d.get("ruhe"), (d.get("sperre") or {}).get(m), mo) if mo else ""
                if gesperrt:                    # Betriebsruhe/Sperrtage (F7): Zelle grau, Tage im Text
                    it.setText(text + "\n" + gesperrt.split(" ")[0])
                    if not farbe:
                        it.setBackground(QBrush(stil.farbe(FARBEN["grau"])))
                it.setToolTip("; ".join(x for x in (f"{n} Auftrag/Aufträge" if n else "", gesperrt) if x))
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.resizeRowsToContents()
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.blockSignals(False)

    # ---- Auswahl und Details ----
    def _woche_gewaehlt(self, m, key):
        self.auswahl = (m, key) if m is not None else None
        self.balken.auswahl = self.auswahl
        self.balken.update()
        self._details()

    def _zelle(self, r, c):
        d = self.daten
        if not d or r < 0 or c < 0 or r >= len(d["maschinen"]) or c >= len(d["spalten"]):
            return
        self.auswahl = (d["maschinen"][r], d["spalten"][c][0])
        self._details(termin_sicht=True)

    def _auftrag_gewaehlt(self, angebot_id):
        self.auftrag = angebot_id
        for i in range(self.details.rowCount()):
            if self.details.item(i, 0).data(Qt.UserRole) == angebot_id:
                self.details.blockSignals(True)
                self.details.selectRow(i)
                self.details.blockSignals(False)

    def _detail_gewaehlt(self):
        it = self.details.item(self.details.currentRow(), 0) if self.details.selectedItems() else None
        self.auftrag = it.data(Qt.UserRole) if it is not None else self.auftrag
        self.tafel.auswahl = self.auftrag
        self.tafel.update()

    def auftraege_der_auswahl(self, termin_sicht=None):
        """(Titel, [Auftrag mit Feld 'h_woche']) zur Auswahl: Woche einer Maschine oder alle mit Terminrisiko."""
        d, e = self.daten, self.ein
        nach_id = {a["id"]: a for a in e["auftraege"]}
        if self.auswahl is None:
            liste = [dict(a, h_woche=a["h"]) for a in einlastung.kritische(e)]
            return (f"Terminrisiko: {len(liste)} Auftrag/Aufträge knapp oder nicht zu halten"
                    if liste else "Kein Auftrag mit Terminrisiko. Balken anklicken: die Aufträge dieser Woche."), liste
        m, key = self.auswahl
        titel = next((t for s, t, _ in d["spalten"] if s == key), "")
        if isinstance(key, tuple):                # gemessene Woche
            return f"{m}, KW {key[1].isocalendar()[1]} (gemessen): Summe der Scans „Laser Start/Ende“", []
        termin = (not self.sicht_ein()) if termin_sicht is None else termin_sicht
        if termin or not isinstance(key, datetime.date):
            roh = d["auftraege"].get((m, key), ())
            if not termin and key == auslastung.SPAETER:
                letzter = max(x for _, _, x in d["spalten"] if x is not None)
                roh = [a for a in e["auftraege"] if a["maschine"] == m
                       and (a["fertig"] is None or auslastung.montag(a["fertig"]) > letzter)]
            liste = [dict(nach_id.get(a["id"], a), h_woche=a["h"]) for a in roh]
        else:
            liste = []
            for a in e["auftraege"]:
                h = sum(bis - von for tag, von, bis in a["stuecke"] if auslastung.montag(tag) == key)
                if a["maschine"] == m and h > 1e-9:
                    liste.append(dict(a, h_woche=h))
        liste.sort(key=lambda a: (str(a.get("termin") or "9999"), str(a.get("nummer"))))
        n = f"{len(liste)} Auftrag" if len(liste) == 1 else f"{len(liste)} Aufträge"
        return f"{m}, {titel}: {n}, {_h(sum(a['h_woche'] for a in liste))} h", liste

    def _details(self, termin_sicht=None):
        self.details.blockSignals(True)
        self.details.setRowCount(0)
        if self.daten is None:
            self.details.blockSignals(False)
            return
        titel, liste = self.auftraege_der_auswahl(termin_sicht)
        self.details_titel.setText(titel)
        for a in liste:
            i = self.details.rowCount()
            self.details.insertRow(i)
            werte = (a["nummer"] or "", a["kunde"] or "", a["art"], _datum(a["termin"]), _h(a["h_woche"]),
                     f"{a['geschnitten'] * 100:.0f} %" if a.get("geschnitten") else "",
                     f"{a['gewicht'] * 100:.0f} %" if a.get("gewicht", 1) < 1 else "",
                     _datum(a.get("fertig")), "" if a.get("puffer") is None else str(a["puffer"]),
                     RISIKO_TEXT.get(a.get("risiko"), ""))
            for k, w in enumerate(werte):
                it = QTableWidgetItem(w)
                it.setData(Qt.UserRole, a["id"])
                if k in (4, 5, 6, 8):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if k == 9 and a.get("risiko") in (einlastung.UEBER, einlastung.KNAPP) \
                        and a["art"] == einlastung.AUFTRAG:
                    it.setBackground(QBrush(stil.farbe(FARBEN["rot" if a["risiko"] == einlastung.UEBER else "gelb"])))
                self.details.setItem(i, k, it)
        for k in (5, 6):                # geschnitten, Gewicht: nur zeigen, wenn eine Zeile etwas dazu hat
            self.details.setColumnHidden(k, not any(self.details.item(i, k).text()
                                                    for i in range(self.details.rowCount())))
        self.details.resizeColumnsToContents()
        kopf = self.details.horizontalHeader()
        kopf.setSectionResizeMode(1, QHeaderView.Stretch)
        # Spalte Kunde nie schmaler als ihr Titel (Layout-Rundgang 11.11.2026: „Kunde“ war bei 1366 px abgeschnitten)
        kopf.setMinimumSectionSize(min(kopf.minimumSectionSize(), 40))
        if kopf.sectionSize(1) < kopf.fontMetrics().horizontalAdvance("Kunde") + 28:
            kopf.setSectionResizeMode(1, QHeaderView.Interactive)
            self.details.setColumnWidth(1, kopf.fontMetrics().horizontalAdvance("Kunde") + 28)
        self.details.blockSignals(False)

    def _oeffnen(self, index):
        it = self.details.item(index.row(), 0)
        if it is not None:
            self._oeffnen_id(it.data(Qt.UserRole))

    def _oeffnen_id(self, angebot_id):
        self.f.angebot_oeffnen(angebot_id)
        self.geoeffnet.emit(angebot_id)

    # ---- Was-wäre-wenn ----
    def ww_verlegen(self, angebot_id=None, maschine=None):
        angebot_id = angebot_id or self.auftrag
        maschine = maschine or self.ww_maschine.currentText()
        a = next((x for x in (self.ein_ohne or {}).get("auftraege", ()) if x["id"] == angebot_id), None)
        if a is None or not maschine:
            self.ww_banner.setText("Was-wäre-wenn: erst einen Auftrag markieren (Plantafel oder Liste rechts).")
            self.ww_banner.setStyleSheet("")
            self.ww_banner.show()
            return False
        if maschine == a["ursprung"]:
            self.szenario.maschine.pop(angebot_id, None)
        else:
            h = einlastung.andere_maschine(self.f.db, angebot_id, maschine)
            self.szenario.maschine[angebot_id] = (maschine, None if h is None else h * a.get("gewicht", 1.0))
        self.zeigen()
        return True

    def ww_zusatz(self, maschine=None, montag=None, stunden=None):
        if maschine is None and self.auswahl and isinstance(self.auswahl[1], datetime.date):
            maschine, montag = self.auswahl
        if maschine is None or montag is None:
            self.ww_banner.setText("Was-wäre-wenn: erst oben den Balken einer Woche anklicken.")
            self.ww_banner.setStyleSheet("")
            self.ww_banner.show()
            return False
        h = self.ww_stunden.value() if stunden is None else stunden
        if h > 0:
            self.szenario.zusatz[(maschine, montag)] = h
        else:
            self.szenario.zusatz.pop((maschine, montag), None)
        self.zeigen()
        return True

    def ww_samstag_setzen(self):
        self.szenario.samstag = self.ww_samstag_h.value() if self.ww_samstag.isChecked() else None
        self.zeigen()

    def ww_leeren(self):
        self.szenario = einlastung.Szenario()
        self.ww_samstag.blockSignals(True)
        self.ww_samstag.setChecked(False)
        self.ww_samstag.blockSignals(False)
        self.zeigen()

    # ---- PDF ----
    def uebergabe(self, pfad=None):
        """Übergabedatei für das eigene Programm Rohrlaser Auslastung (Patrick 11.11.2026): die beauftragten Aufträge
        mit Maschine, restlicher Laserzeit (Stunden:Minuten) und Liefertermin als CSV. Ergebnis: Pfad oder None."""
        if self.daten is None:
            self.laden()
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Übergabe an Rohrlaser Auslastung", "Auslastung-Uebergabe.csv",
                                                  "CSV (*.csv)")
            if not pfad:
                return None
        import csv
        liste = sorted((a for a in einlastung.auftragsliste(self.daten) if a["art"] == einlastung.AUFTRAG),
                       key=lambda a: (str(a.get("termin") or "9999"), str(a.get("nummer") or "")))
        with open(pfad, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(("Auftragsnummer", "Kunde", "Maschine", "Kalkulierte Laufzeit", "Liefertermin"))
            for a in liste:
                minuten = max(1, int(float(a.get("h") or 0.0) * 60 + 0.5))
                w.writerow((a.get("nummer") or a["id"], a.get("kunde") or "", a["maschine"],
                            f"{minuten // 60}:{minuten % 60:02d}", _datum(a.get("termin"))))
        return pfad

    def pdf(self, pfad=None):
        """Seite als PDF (A4 quer): Wochenbalken, Plantafel und die Aufträge mit Terminrisiko."""
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Auslastung als PDF", "Maschinenauslastung.pdf", "PDF (*.pdf)")
            if not pfad:
                return None
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter
        w = QPdfWriter(str(pfad))
        w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape, QMarginsF(12, 12, 12, 12)))
        w.setResolution(96)
        w.setTitle("Maschinenauslastung")
        with stil.druckfarben():
            p = QPainter(w)
            seite = w.pageLayout().paintRectPixels(96)
            breite = seite.width()
            f = self.font()
            f.setPointSizeF(13)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#1F2937"))          # fest: PDF, immer dunkle Schrift auf Weiß
            heute = self.daten["heute"]
            p.drawText(QRectF(0, 0, breite, 24), Qt.AlignLeft | Qt.AlignVCenter,
                       f"Maschinenauslastung, Stand {heute.strftime('%d.%m.%Y')} – "
                       + ("eingelastet" if self.sicht_ein() else "Terminwoche")
                       + ("" if self.szenario.leer() else " – WAS-WÄRE-WENN: " + self.szenario.text()))
            f.setPointSizeF(8.5)
            f.setBold(False)
            p.setFont(f)
            y = 30
            for widget in (self.balken, self.tafel):
                alt = widget.size()
                fest = widget.minimumWidth()
                widget.setMinimumWidth(0)
                widget.resize(breite, widget.sizeHint().height())
                widget.render(p, QPointF(0, y).toPoint())
                y += widget.height() + 14
                widget.setMinimumWidth(fest)
                widget.resize(alt)
            auswahl, self.auswahl = self.auswahl, None
            titel, liste = self.auftraege_der_auswahl()
            self.auswahl = auswahl
            p.drawText(QRectF(0, y, breite, 16), Qt.AlignLeft | Qt.AlignVCenter, titel)
            y += 18
            spalten = ((0, 90, "nummer"), (95, 260, "kunde"), (360, 70, "maschine"), (435, 90, "termin"),
                       (530, 90, "fertig"), (625, 70, "puffer"), (700, 120, "risiko"))
            kopf = ("Angebot", "Kunde", "Maschine", "Liefertermin", "Laser fertig", "Puffer [AT]", "Terminrisiko")
            for (x, b, _), t in zip(spalten, kopf):
                p.drawText(QRectF(x, y, b, 14), Qt.AlignLeft | Qt.AlignVCenter, t)
            y += 15
            for a in liste:
                if y > seite.height() - 16:
                    break
                for x, b, feld in spalten:
                    wert = a.get(feld)
                    wert = (_datum(wert) if feld in ("termin", "fertig") else RISIKO_TEXT.get(wert, "") if feld == "risiko"
                            else "" if wert is None else str(wert))
                    p.drawText(QRectF(x, y, b, 14), Qt.AlignLeft | Qt.AlignVCenter,
                               QFontMetrics(f).elidedText(wert, Qt.ElideRight, b))
                y += 14
            p.end()
        return pfad


class AuslastungKachel(QWidget):
    """Startseite, Karte „Heute“: je Maschine die eingelastete Auslastung dieser und der nächsten Woche mit kleinem
    Verlauf über acht Wochen und die Zahl der Aufträge mit Terminrisiko. Klick öffnet die Seite Auslastung."""
    geklickt = Signal()
    ZEILE, WOCHEN = 22, 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zeilen, self.risiko = [], None       # [(Maschine, [(Quote oder None, Montag)])]
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("Eingelastete Laserzeit der Aufträge gegen die Kapazität, diese und die nächsten Wochen. "
                        "Klick öffnet die Seite Auslastung.")

    def laden(self, db, heute=None):
        """Aus der Datendatei rechnen; True, wenn es etwas zu zeigen gibt (mindestens ein Auftrag)."""
        aus = auslastung.berechnen(db, heute, self.WOCHEN, merker=MERKER)
        ein = einlastung.rechnen(aus)
        self.setzen(aus, ein)
        return bool(ein["auftraege"])

    def setzen(self, aus, ein):
        self.zeilen = []
        for m in ein["maschinen"]:
            werte = []
            for _, _, mo in aus["spalten"]:
                if mo is not None:
                    a, _b, kap = einlastung.wochenwerte(aus, ein, m, mo)
                    werte.append((a / kap if kap else (None if not a else 9.9), mo))
            self.zeilen.append((m, werte))
        self.risiko = ein["risiko"]
        self.updateGeometry()
        self.update()

    def text(self):
        """Dasselbe als Text (Tests, Vorlesen)."""
        teile = []
        for m, werte in self.zeilen:
            w = [f"{q * 100:.0f} %" if q is not None else "–" for q, _ in werte[:2]]
            teile.append(f"{m} {' / '.join(w)}")
        r = self.risiko or {}
        if r.get(einlastung.UEBER) or r.get(einlastung.KNAPP):
            teile.append(f"Terminrisiko {r.get(einlastung.UEBER, 0)} nicht zu halten, {r.get(einlastung.KNAPP, 0)} knapp")
        return "; ".join(teile)

    def sizeHint(self):
        return QSize(300, 20 + self.ZEILE * max(1, len(self.zeilen)) + (18 if self._risiko_text() else 0))

    def _risiko_text(self):
        r = self.risiko or {}
        if r.get(einlastung.UEBER) or r.get(einlastung.KNAPP):
            return f"Terminrisiko: {r.get(einlastung.UEBER, 0)} nicht zu halten, {r.get(einlastung.KNAPP, 0)} knapp"
        return ""

    def mouseReleaseEvent(self, _):
        self.geklickt.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        text, grau = stil.farbe(stil.TEXT), stil.farbe(stil.TEXT_GRAU)
        fett = self.font()
        fett.setBold(True)
        p.setFont(fett)
        p.setPen(text)
        p.drawText(QRectF(0, 0, self.width(), 18), Qt.AlignLeft | Qt.AlignVCenter, "Auslastung (eingelastet)")
        p.setFont(self.font())
        p.setPen(grau)
        p.drawText(QRectF(0, 0, self.width(), 18), Qt.AlignRight | Qt.AlignVCenter, "diese / nächste Woche")
        y = 20
        for m, werte in self.zeilen:
            p.setPen(text)
            p.drawText(QRectF(0, y, 46, self.ZEILE), Qt.AlignLeft | Qt.AlignVCenter, m)
            x, bb = 50, 12
            for q, _mo in werte:                      # Verlauf: ein kleiner Balken je Woche
                p.setPen(Qt.NoPen)
                p.setBrush(stil.farbe(stil.LINIE))
                p.drawRect(QRectF(x, y + 3, bb, self.ZEILE - 7))
                if q:
                    h = (self.ZEILE - 7) * min(1.0, q)
                    p.setBrush(QColor(BALKEN[stufe(q)]))
                    p.drawRect(QRectF(x, y + self.ZEILE - 4 - h, bb, h))
                x += bb + 3
            w = [f"{q * 100:.0f} %" if q is not None and q < 9 else "–" if q is None else "keine Schicht"
                 for q, _ in werte[:2]]
            rot = any((q or 0) > 1 for q, _ in werte[:2])
            p.setPen(QColor(BALKEN["rot"]) if rot else text)
            p.drawText(QRectF(x + 6, y, self.width() - x - 6, self.ZEILE), Qt.AlignLeft | Qt.AlignVCenter,
                       " / ".join(w) + ("  überlastet" if rot else ""))
            y += self.ZEILE
        r = self._risiko_text()
        if r:
            p.setPen(QColor(BALKEN["rot"]))
            p.drawText(QRectF(0, y, self.width(), 18), Qt.AlignLeft | Qt.AlignVCenter, "! " + r)
        p.end()


def frei_satz(db, maschine, bis, heute=None):
    """Ein Satz für „Termin prüfen …“: freie Laserstunden der Maschine bis zum Termin (eingelastet). '' ohne Maschine
    oder Termin."""
    if not maschine or bis is None:
        return ""
    aus = auslastung.berechnen(db, heute, merker=MERKER)
    if maschine not in aus["maschinen"]:
        return ""
    ein = einlastung.rechnen(aus)
    return (f" Freie Laserzeit auf {maschine} bis {bis.strftime('%d.%m.%Y')}: "
            f"{_h(einlastung.frei_bis(aus, ein, maschine, bis))} h (Aufträge eingelastet).")
