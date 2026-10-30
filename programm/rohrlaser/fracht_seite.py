"""Frachtkosten: Rechner (Reiter Frachtkosten) und sechs Pflegeseiten (Einstellungen → Fracht, seit 0.9.211).

Reiter Frachtkosten: Fracht kalkulieren (frei). Einstellungen → Fracht: Frachtzonen und Postleitzahlen,
Tarifverwaltung, Paletten und Ladehilfsmittel, Zuschläge, Dienstleister und Kundentarife, Historie und Einstellungen;
die ändert nur der Admin, solange der Bereich Frachtkosten Admin-Schutz hat (admin_schutz.py).

Ab 1024 × 700 Pixel ohne waagrechtes Scrollen bedienbar: im schmalen Fenster rutscht das Ergebnis des Rechners unter
die Eingabe.
"""
import datetime
import html
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget)

from . import fracht, hilfe
from .angebot import aktiv as position_aktiv
from .angebot_oben import Aufklapper
from .fenster import EinstellungenSeite, StammdatenSeite
from .fracht_daten import (DIENSTLEISTER, DIESELPREISE, DIESELSTAFFEL, LAENDER, LHT, LIEFERBEDINGUNGEN, PLZ, PREISE,
                           TARIFE, WAEHRUNGEN, ZONEN, ZUSCHLAEGE, liste, plz_csv, plz_csv_lesen)
from .stammdaten import zahl_als_text, zahl_aus_text
from .eingabe import RechenSpin, RechenSpinGanz

SCHMAL = 1100          # darunter steht das Ergebnis unter der Eingabe
FARBE = {"ok": "#1E6B34", "warnung": "#7A5A00", "fehler": "#B42318", "auswahl": "#7A5A00"}
STATUS_TEXT = {"ok": "berechnet", "warnung": "berechnet, mit Warnung", "fehler": "nicht berechnet",
               "auswahl": "Tarif wählen"}


def _e(t):
    return html.escape(str(t if t is not None else ""))


def ergebnis_html(erg):
    """Aufgeschlüsselte Kostenübersicht eines Ergebnisses (fracht.rechnen/nachrechnen) als HTML."""
    st = erg.get("status") or "fehler"
    teile = [f"<p style='color:{FARBE.get(st, '#000')}'><b>{_e(STATUS_TEXT.get(st, st))}</b>"
             + (f" – Gesamtfrachtkosten <b>{fracht.euro(erg['gesamt'])}</b>" if erg.get("gesamt") is not None else "")
             + "</p>"]
    t = erg.get("tarif") or {}
    info = []
    if t.get("tarif_id"):
        info.append(("Frachtführer / Tarif", f"{t.get('dienstleister') or '–'} / {t['tarif_id']} "
                     f"{t.get('bezeichnung') or ''}" + (f", Version {t['version']}" if t.get("version") else "")
                     + f" ({t.get('modell') or ''}, {t.get('tarifart') or ''})"))
    if erg.get("tarif_grund"):
        info.append(("Tarifauswahl", erg["tarif_grund"]))
    ze = erg.get("zone_empfang") or {}
    if ze.get("text"):
        info.append(("Frachtzone", ze["text"]))
    zv = erg.get("zone_versand") or {}
    if zv.get("text"):
        info.append(("Versandzone", zv["text"]))
    g = erg.get("gewicht") or {}
    if g:
        info.append(("Gewicht", f"Netto {zahl_als_text(g['netto'], 1)} kg + Verpackung "
                     f"{zahl_als_text(g['verpackung'], 1)} kg = Brutto {zahl_als_text(g['brutto'], 1)} kg "
                     f"({_e(g.get('quelle'))})"))
        info.append(("Frachtpflichtiges Gewicht", f"{zahl_als_text(g['frachtpflichtig'], 1)} kg: "
                     f"{_e(g.get('erklaerung'))}"))
    lw = erg.get("lht") or {}
    if lw.get("anzahl"):
        je = ", ".join(f"{x['anzahl']} × {x['bezeichnung']}" for x in lw["je"])
        extra = [f"{zahl_als_text(lw['stellplaetze'], 2)} Stellplätze"]
        if lw.get("volumen") is not None:
            extra.append(f"{zahl_als_text(lw['volumen'], 3)} m³")
        if lw.get("lademeter") is not None:
            extra.append(f"{zahl_als_text(lw['lademeter'], 2)} Lademeter")
        info.append(("Ladehilfsmittel", f"{lw['anzahl']} Stück ({je}); " + ", ".join(extra)))
    if erg.get("staffeln"):
        info.append(("Preisstaffel", "; ".join(erg["staffeln"])))
    if info:
        teile.append("<table cellspacing='0' cellpadding='2'>" + "".join(
            f"<tr><td valign='top' style='color:#5F6B7A; padding-right:8px'>{_e(a)}</td><td>{_e(b)}</td></tr>"
            for a, b in info) + "</table>")
    if erg.get("zeilen"):
        zeilen = "".join(f"<tr><td>{_e(z['text'])}</td><td align='right'>{fracht.euro(z['betrag'])}</td>"
                         f"<td style='color:#5F6B7A'>{_e(z['erklaerung'])}</td></tr>" for z in erg["zeilen"])
        summe = (f"<tr><td><b>Gesamtfrachtkosten</b></td><td align='right'><b>{fracht.euro(erg['gesamt'])}</b></td>"
                 "<td></td></tr>" if erg.get("gesamt") is not None else "")
        teile.append("<table cellspacing='0' cellpadding='3' style='margin-top:6px'><tr style='background:#F1F3F6'>"
                     "<th align='left'>Position</th><th align='right'>Betrag</th><th align='left'>Rechnung</th></tr>"
                     + zeilen + summe + "</table>")
    for titel, schl, farbe in (("Fehler und fehlende Tarifdaten", "fehler", "#B42318"),
                               ("Warnungen", "warnungen", "#7A5A00"), ("Hinweise", "hinweise", "#3A4656"),
                               ("Nicht angewendete Zuschläge", "nicht_angewendet", "#5F6B7A")):
        if erg.get(schl):
            teile.append(f"<p style='margin-bottom:0; color:{farbe}'><b>{titel}</b></p><ul style='margin-top:0'>"
                         + "".join(f"<li>{_e(x)}</li>" for x in erg[schl]) + "</ul>")
    if erg.get("weitere_tarife"):
        teile.append("<p style='margin-bottom:0'><b>Weitere passende Tarife</b></p><ul style='margin-top:0'>" + "".join(
            f"<li>{_e(w['tarif_id'])} {_e(w.get('bezeichnung') or '')}: "
            + (fracht.euro(w["gesamt"]) if w.get("gesamt") is not None else "nicht berechenbar – "
               + _e("; ".join(w.get("fehler") or [])))
            + "</li>" for w in erg["weitere_tarife"]) + "</ul>")
    teile.append("<p style='color:#5F6B7A; font-size:small'>Alle Werte stammen aus den gepflegten Frachtdaten; "
                 "Tarife mit BEISPIEL sind keine echten Preise.</p>")
    return "".join(teile)


def _zahl(text):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return zahl_aus_text(t)
    except ValueError:
        return None


def _box(titel, w):
    box = QGroupBox(titel)
    bl = QVBoxLayout(box)
    bl.setContentsMargins(4, 4, 4, 4)
    bl.addWidget(w)
    return box


# ------------------------------------------------------------------ 1 Fracht kalkulieren
class RechnerSeite(QWidget):
    titel = "Fracht kalkulieren"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.daten = {}
        self.ergebnis = None
        self.ware = None            # (Positionen, Werte) eines Angebots für den Packvorschlag
        self._laden = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.rechnen)

        # Versanddaten
        v = QGroupBox("Versanddaten")
        fv = QFormLayout(v)
        self.abs_plz, self.abs_land = QLineEdit(), QLineEdit()
        self.land, self.plz = QLineEdit("DE"), QLineEdit()
        for w in (self.abs_land, self.land):
            w.setMaxLength(2)
            w.setMaximumWidth(50)
        self.zone = QLabel()
        self.zone.setWordWrap(True)
        self.versandart, self.kunde, self.dienstleister, self.tarif, self.lieferbedingung = (
            QComboBox() for _ in range(5))
        for cb in (self.versandart, self.kunde):
            cb.setEditable(True)
        self.datum = QDateEdit(QDate.currentDate())
        self.datum.setDisplayFormat("dd.MM.yyyy")
        self.datum.setCalendarPopup(True)
        self.bezeichnung = QLineEdit()
        self.bezeichnung.setPlaceholderText("optional, z. B. Angebotsnummer")
        zeile = QHBoxLayout()
        zeile.addWidget(self.abs_plz, 1)
        zeile.addWidget(QLabel("Land"))
        zeile.addWidget(self.abs_land)
        fv.addRow("Absender-PLZ", zeile)
        zeile = QHBoxLayout()
        zeile.addWidget(self.plz, 1)
        zeile.addWidget(QLabel("Land"))
        zeile.addWidget(self.land)
        fv.addRow("Empfänger-PLZ", zeile)
        fv.addRow("", self.zone)
        fv.addRow("Versandart", self.versandart)
        fv.addRow("Kunde (optional)", self.kunde)
        fv.addRow("Frachtführer (optional)", self.dienstleister)
        fv.addRow("Tarif", self.tarif)
        fv.addRow("Lieferbedingung", self.lieferbedingung)
        fv.addRow("Datum", self.datum)
        fv.addRow("Bezeichnung", self.bezeichnung)

        # Gewicht
        g = QGroupBox("Gewicht")
        fg = QFormLayout(g)
        self.netto = RechenSpin()
        self.netto.setRange(0, 1000000)
        self.netto.setDecimals(1)
        self.netto.setSuffix(" kg")
        self.netto.setGroupSeparatorShown(True)
        self.brutto = QLabel()
        fg.addRow("Nettogewicht der Ware", self.netto)
        fg.addRow("Gesamtbruttogewicht", self.brutto)
        self.ware_text = QLabel()
        self.ware_text.setWordWrap(True)
        self.laden_knopf = QPushButton("Aus Angebot laden …")
        self.laden_knopf.setToolTip("Positionen eines Angebots übernehmen: Gewicht, längstes Teil und Packvorschlag "
                                    "nach Maßen und Stückzahl (günstigster Ladungsträger)")
        self.laden_knopf.clicked.connect(lambda: self.aus_angebot_laden())
        zeile = QHBoxLayout()
        zeile.addWidget(self.laden_knopf)
        zeile.addWidget(self.ware_text, 1)
        fg.addRow("Ware", zeile)

        # Ladehilfsmittel
        lh = QGroupBox("Ladehilfsmittel")
        ll = QVBoxLayout(lh)
        self.lht_tabelle = QTableWidget(0, 3)
        self.lht_tabelle.setHorizontalHeaderLabels(["Ladehilfsmittel", "Anzahl", "Brutto je Stück [kg]"])
        self.lht_tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2):
            self.lht_tabelle.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.lht_tabelle.verticalHeader().setVisible(False)
        self.lht_tabelle.setMinimumHeight(110)
        knoepfe = QHBoxLayout()
        for text, ziel in (("+ Ladungsträger", self.lht_neu), ("Ladungsträger entfernen", self.lht_weg),
                           ("Packvorschlag", self.packvorschlag)):
            b = QPushButton(text)
            b.clicked.connect(ziel)
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        self.lht_summe = QLabel()
        self.lht_summe.setWordWrap(True)
        ll.addWidget(self.lht_tabelle)
        ll.addLayout(knoepfe)
        ll.addWidget(self.lht_summe)

        # Packliste (nur mit Ware aus einem Angebot): Vergleich der Ladungsträger und Skizze je Palette
        from .palette_skizze import PacklisteAnsicht
        self.packliste_box = QGroupBox("Packliste")
        pl = QVBoxLayout(self.packliste_box)
        self.vergleich = QLabel()
        self.vergleich.setWordWrap(True)
        self.vergleich.setTextFormat(Qt.RichText)
        self.packliste_ansicht = PacklisteAnsicht()
        pl.addWidget(self.vergleich)
        pl.addWidget(self.packliste_ansicht)
        self.packliste_box.hide()
        self.packliste = None
        self.vergleich_liste = []

        # Zusatzleistungen (Zuschläge mit Bedingung 'nur wenn gewählt')
        self.leistungen_box = QGroupBox("Zusatzleistungen")
        self.leistungen_lay = QFormLayout(self.leistungen_box)
        self.leistungen = {}

        # Erweiterte Einstellungen
        er = QWidget()
        fe = QFormLayout(er)
        fe.setContentsMargins(0, 0, 0, 0)
        self.verpackung = QLineEdit()
        self.verpackung.setPlaceholderText("leer = Eigengewicht der Ladungsträger")
        self.frachtpflichtig = QLineEdit()
        self.frachtpflichtig.setPlaceholderText("leer = nach Tarif")
        self.km = QLineEdit()
        self.km.setPlaceholderText("leer = Entfernung der Zone")
        self.max_laenge = QLineEdit()
        self.max_laenge.setPlaceholderText("für Langgut- und Überlängenzuschlag")
        fe.addRow("Verpackungsgewicht [kg]", self.verpackung)
        fe.addRow("Frachtpflichtiges Gewicht [kg]", self.frachtpflichtig)
        fe.addRow("Entfernung [km]", self.km)
        fe.addRow("Längstes Teil [mm]", self.max_laenge)
        self.erweitert = Aufklapper("Erweiterte Einstellungen", er)

        links = QWidget()
        lv = QVBoxLayout(links)
        for w in (v, g, lh, self.packliste_box, self.leistungen_box, self.erweitert):
            lv.addWidget(w)
        lv.addStretch(1)
        self.links = QScrollArea()
        self.links.setWidgetResizable(True)
        self.links.setWidget(links)
        self.links.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.links.setMinimumWidth(420)

        # Ergebnis
        self.anzeige = QTextBrowser()
        self.anzeige.setOpenExternalLinks(False)
        self.speichern_knopf = QPushButton("In Historie speichern")
        self.speichern_knopf.setObjectName("primaer")
        self.speichern_knopf.clicked.connect(self.speichern)
        rechts = QWidget()
        rv = QVBoxLayout(rechts)
        rv.setContentsMargins(0, 0, 0, 0)
        t = QLabel("Ergebnis")
        t.setObjectName("kartentitel")
        rv.addWidget(t)
        rv.addWidget(self.anzeige, 1)
        z = QHBoxLayout()
        z.addStretch(1)
        z.addWidget(self.speichern_knopf)
        rv.addLayout(z)

        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.addWidget(self.links)
        self.teiler.addWidget(rechts)
        self.teiler.setStretchFactor(0, 1)
        self.teiler.setStretchFactor(1, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.teiler)

        for w in (self.abs_plz, self.abs_land, self.land, self.plz, self.verpackung, self.frachtpflichtig, self.km,
                  self.max_laenge):
            w.textChanged.connect(self.geaendert)
        for cb in (self.versandart, self.dienstleister, self.tarif, self.lieferbedingung):
            cb.currentTextChanged.connect(self.geaendert)
        self.kunde.currentTextChanged.connect(self.kunde_gewaehlt)
        self.netto.valueChanged.connect(self.geaendert)
        self.datum.dateChanged.connect(self.geaendert)
        self.neu_laden()

    def resizeEvent(self, ereignis):
        super().resizeEvent(ereignis)
        richtung = Qt.Vertical if self.width() < SCHMAL else Qt.Horizontal
        if self.teiler.orientation() != richtung:
            self.teiler.setOrientation(richtung)
            self.links.setMinimumWidth(0 if richtung == Qt.Vertical else 420)
            gesamt = self.height() if richtung == Qt.Vertical else self.width()
            self.teiler.setSizes([gesamt // 2, gesamt - gesamt // 2])

    # ---------------------------------------------------------- Daten
    def neu_laden(self):
        self._laden = True
        self.daten = self.db.fracht_daten()
        self.kunden = {k["kundennr"]: k for k in self.db.zeilen("kunden") if k.get("kundennr")}
        if not self.abs_plz.text() and not self.abs_land.text():
            self.abs_plz.setText(self.db.einstellung("absender_plz") or "")
            self.abs_land.setText(self.db.einstellung("absender_land") or "DE")
        arten = []
        for d in self.daten["dienstleister"]:
            arten += [a for a in liste(d.get("versandarten")) if a not in arten]
        arten += [t["versandart"] for t in self.daten["tarife"] if t.get("versandart") and t["versandart"] not in arten]
        self._fuellen(self.versandart, [""] + arten)
        self._fuellen(self.kunde, [""] + [f"{k} – {v.get('name') or ''}" for k, v in sorted(self.kunden.items())])
        self._fuellen(self.dienstleister, [""] + sorted(d["dienstleister_id"] for d in self.daten["dienstleister"]
                                                         if d.get("dienstleister_id") and fracht.aktiv(d)))
        self._fuellen(self.tarif, ["automatisch"] + sorted(t["tarif_id"] for t in self.daten["tarife"]
                                                           if t.get("tarif_id") and fracht.aktiv(t)))
        self._fuellen(self.lieferbedingung, [""] + list(LIEFERBEDINGUNGEN))
        lhts = [z["lht_id"] for z in self.daten["lht"] if z.get("lht_id") and fracht.aktiv(z)]
        for r in range(self.lht_tabelle.rowCount()):
            cb = self.lht_tabelle.cellWidget(r, 0)
            self._fuellen(cb, lhts)
        self._leistungen_bauen()
        self._laden = False
        self.rechnen()

    @staticmethod
    def _fuellen(cb, werte):
        alt = cb.currentText()
        cb.blockSignals(True)
        cb.clear()
        cb.addItems(werte)
        if alt in werte or cb.isEditable():
            cb.setCurrentText(alt)
        cb.blockSignals(False)

    def _leistungen_bauen(self):
        alt = {i: (c.isChecked(), s.value() if s else None) for i, (c, s) in self.leistungen.items()}
        while self.leistungen_lay.rowCount():
            self.leistungen_lay.removeRow(0)
        self.leistungen = {}
        for z in self.daten["zuschlaege"]:
            if not z.get("zuschlag_id") or not fracht.aktiv(z) or z.get("bedingung") != "nur wenn gewählt":
                continue
            c = QCheckBox(z.get("bezeichnung") or z["zuschlag_id"])
            c.setChecked(alt.get(z["zuschlag_id"], (False, None))[0])
            c.toggled.connect(self.geaendert)
            s = None
            if z.get("berechnung") == "€ je Stunde":
                s = RechenSpin()
                s.setRange(0, 1000)
                s.setDecimals(2)
                s.setSuffix(" h")
                s.setValue(alt.get(z["zuschlag_id"], (False, 1.0))[1] or 1.0)
                s.valueChanged.connect(self.geaendert)
                zeile = QHBoxLayout()
                zeile.addWidget(c, 1)
                zeile.addWidget(s)
                self.leistungen_lay.addRow(zeile)
            else:
                self.leistungen_lay.addRow(c)
            self.leistungen[z["zuschlag_id"]] = (c, s)
        self.leistungen_box.setVisible(bool(self.leistungen))

    # ---------------------------------------------------------- Eingaben
    def kunde_gewaehlt(self, text):
        if self._laden:
            return
        k = self.kunden.get(text.split(" – ")[0].strip())
        if k:
            plz = k.get("liefer_plz") or k.get("plz") or fracht.plz_aus_text(k.get("plz_ort"))
            land = k.get("liefer_land") if k.get("liefer_plz") else k.get("land")
            self._laden = True
            self.plz.setText(plz or "")
            self.land.setText(land or "DE")
            if k.get("lieferbedingung"):
                self.lieferbedingung.setCurrentText(k["lieferbedingung"])
            self._laden = False
        self.geaendert()

    def lht_neu(self, lht_id=None, anzahl=1, gewicht=None):
        r = self.lht_tabelle.rowCount()
        self.lht_tabelle.insertRow(r)
        cb = QComboBox()
        self._fuellen(cb, [z["lht_id"] for z in self.daten.get("lht", []) if z.get("lht_id") and fracht.aktiv(z)])
        if lht_id:
            cb.setCurrentText(lht_id)
        cb.currentTextChanged.connect(self.geaendert)
        sp = RechenSpinGanz()
        sp.setRange(0, 10000)
        sp.setValue(int(anzahl or 0))
        sp.valueChanged.connect(self.geaendert)
        gw = QLineEdit("" if gewicht is None else zahl_als_text(gewicht))
        gw.setPlaceholderText("optional")
        gw.textChanged.connect(self.geaendert)
        self.lht_tabelle.setCellWidget(r, 0, cb)
        self.lht_tabelle.setCellWidget(r, 1, sp)
        self.lht_tabelle.setCellWidget(r, 2, gw)
        self.geaendert()

    def lht_weg(self):
        r = self.lht_tabelle.currentRow()
        if r < 0:
            r = self.lht_tabelle.rowCount() - 1
        if r >= 0:
            self.lht_tabelle.removeRow(r)
            self.geaendert()

    def _packliste_zeigen(self):
        from . import paletten
        if self.packliste is None:
            self.packliste_box.hide()
            return
        zeilen = []
        for i, x in enumerate(self.vergleich_liste):
            preis = fracht.euro(x["gesamt"]) if x["gesamt"] is not None else "kein Tarif"
            lht = ", ".join(f"{t['anzahl']} × {t['lht_id']}" for t in x["lht"]) or "–"
            t = f"{'Paket ' if x.get('paket') else ''}{html.escape(x['bezeichnung'])}: {html.escape(lht)} – {preis}"
            zeilen.append(f"<b>✓ {t} (günstigste, übernommen)</b>" if i == 0 else t)
        kopf = f"{paletten.kurz(self.packliste)}"
        self.vergleich.setText(f"<b>{html.escape(kopf)}</b>" + (
            "<br>Verglichen (Standard-Ladungsträger, lange Teile auf Langgut; Paket je Kartongröße, wenn alles "
            "hineinpasst):<br>" + "<br>".join(zeilen)
            if zeilen else ""))
        self.packliste_ansicht.setzen(self.packliste)
        self.packliste_box.show()

    def lht_eintraege(self):
        out = []
        for r in range(self.lht_tabelle.rowCount()):
            out.append(dict(lht_id=self.lht_tabelle.cellWidget(r, 0).currentText(),
                            anzahl=self.lht_tabelle.cellWidget(r, 1).value(),
                            gewicht=_zahl(self.lht_tabelle.cellWidget(r, 2).text())))
        return out

    def aus_angebot_laden(self, angebot_id=None):
        """Ware eines Angebots übernehmen (Patrick 29.10.2026, 1b): Positionen und Werte für den Packvorschlag,
        Nettogewicht, längstes Teil, Kunde und Bezeichnung; danach Packvorschlag. Ohne angebot_id Auswahl der
        zuletzt geänderten Angebote. Ergebnis: True, wenn geladen."""
        from . import fracht_angebot, rechnen
        if angebot_id is None:
            alle = sorted(self.db.angebote(), key=lambda a: a.get("geaendert") or "", reverse=True)[:300]
            if not alle:
                self.f.meldung("Keine Angebote vorhanden.", fehler=True)
                return False
            texte = [f"{a.get('nummer') or a['id']} – {a.get('kunde') or a.get('kundennr') or ''} "
                     f"({a.get('positionen') or 0} Pos., {zahl_als_text(a.get('teile') or 0, 0)} Teile)" for a in alle]
            text, ok = QInputDialog.getItem(self, "Aus Angebot laden", "Angebot (zuletzt geänderte zuerst):", texte,
                                            0, True)
            if not ok or text not in texte:
                return False
            angebot_id = alle[texte.index(text)]["id"]
        kopf = self.db.angebot(angebot_id)
        if kopf is None:
            return False
        pos = self.db.positionen(angebot_id)
        k, tab = self.db.kontext(), self.db.tabellen()
        werte = [rechnen.position_werte(p, kopf, k, tab) if position_aktiv(p) else None for p in pos]
        netto, laenge, fehlt = fracht_angebot.ware(pos, werte)
        self._laden = True
        nr = kopf.get("kundennr")
        if nr and nr in self.kunden:
            self.kunde.setCurrentText(f"{nr} – {self.kunden[nr].get('name') or ''}")
            self._laden = False
            self.kunde_gewaehlt(self.kunde.currentText())
            self._laden = True
        self.bezeichnung.setText(f"Angebot {kopf.get('nummer') or ''}")
        self.netto.setValue(netto)
        self.max_laenge.setText(zahl_als_text(laenge, 0) if laenge else "")
        self._laden = False
        self.ware = (pos, werte)
        teile = sum(int(p.get("stueck") or 0) for p, w in zip(pos, werte) if w is not None)
        self.ware_text.setText(f"Angebot {kopf.get('nummer') or ''}: {zahl_als_text(teile, 0)} Teile, "
                               f"{zahl_als_text(netto, 1)} kg" + (f"; <span style='color:#B42318'>Gewicht fehlt bei "
                                                                  f"Pos. {', '.join(fehlt)}</span>" if fehlt else ""))
        self.packvorschlag()
        return True

    def _preis_mit(self, lht, paket=False):
        """Fracht (€ oder None) der aktuellen Eingaben mit diesen Ladungsträgern; paket: als Paketversand (Versandart
        Paket, Tarif und Dienstleister automatisch), sonst ohne die Versandart Paket."""
        from .fracht_richtwerte import PAKET
        s = self.sendung()
        s["lht"] = lht
        if paket:
            s.update(versandart=PAKET, tarif_id=None, dienstleister=None)
        elif s.get("versandart") == PAKET:
            s.update(versandart=None, tarif_id=None, dienstleister=None)
        return fracht.rechnen(self.daten, s).get("gesamt")

    def _preis_paket(self, lht):
        return self._preis_mit(lht, paket=True)

    def packvorschlag(self):
        """Ladungsträger vorschlagen (ersetzt die Liste): aus einem Angebot (ware = (Positionen, Werte), gesetzt vom
        Dialog 'Fracht berechnen …' oder 'Aus Angebot laden …') nach Gewicht und Packraum (paletten.py) mit dem
        günstigsten Standard-Ladungsträger (paletten.guenstigste, lange Teile auf Langgut), dazu Packliste und
        Skizze; sonst aus Nettogewicht und längstem Teil."""
        std, lg = self.db.einstellung("fracht_lht_standard"), self.db.einstellung("fracht_lht_langgut")
        if self.ware is not None:
            from . import fracht_angebot, paletten
            einst = {n: self.db.einstellung(n) for n in fracht_angebot.PALETTEN_EINST}
            self.vergleich_liste = paletten.guenstigste(*self.ware, self.daten.get("lht", []), std, lg, einst,
                                                        self._preis_mit, self._preis_paket)
            if self.vergleich_liste:
                from .fracht_richtwerte import PAKET
                beste = self.vergleich_liste[0]
                vorschlag, hinweise, self.packliste = beste["lht"], beste["hinweise"], beste["packliste"]
                if beste.get("paket") or self.versandart.currentText() == PAKET:     # Paket oder Palette
                    self._laden = True
                    self.versandart.setCurrentText(PAKET if beste.get("paket") else "")
                    self.tarif.setCurrentText("automatisch")
                    self.dienstleister.setCurrentText("")
                    self._laden = False
            else:
                vorschlag, hinweise = paletten.ladung(*self.ware, self.daten.get("lht", []), std, lg, einst)
                self.packliste = paletten.packen(*self.ware, self.daten.get("lht", []), std, lg, einst)
            self._packliste_zeigen()
        else:
            vorschlag, hinweise = fracht.packvorschlag(
                [(self.netto.value(), _zahl(self.max_laenge.text()) or 0)], self.daten.get("lht", []), std, lg)
        self.lht_tabelle.setRowCount(0)
        for e in vorschlag:
            self.lht_neu(e["lht_id"], e["anzahl"])
        if hinweise:
            self.f.meldung("; ".join(hinweise), fehler=not vorschlag)
        self.geaendert()
        return vorschlag

    def sendung(self):
        kunde = self.kunde.currentText().split(" – ")[0].strip()
        leist = {i: (s.value() if s else 1) for i, (c, s) in self.leistungen.items() if c.isChecked()}
        return dict(datum=self.datum.date().toString("yyyy-MM-dd"), land=self.land.text().strip().upper() or "DE",
                    plz=self.plz.text().strip(), absender_plz=self.abs_plz.text().strip(),
                    absender_land=self.abs_land.text().strip().upper() or "DE",
                    versandart=self.versandart.currentText().strip() or None, kundennr=kunde or None,
                    dienstleister=self.dienstleister.currentText() or None,
                    tarif_id=None if self.tarif.currentText() in ("", "automatisch") else self.tarif.currentText(),
                    lieferbedingung=self.lieferbedingung.currentText() or None, netto=self.netto.value(),
                    verpackung=_zahl(self.verpackung.text()), frachtpflichtig=_zahl(self.frachtpflichtig.text()),
                    km=_zahl(self.km.text()), max_laenge=_zahl(self.max_laenge.text()), lht=self.lht_eintraege(),
                    leistungen=leist)

    def setzen(self, s):
        """Eingaben aus einer gespeicherten Sendung übernehmen (Frachtberechnung eines Angebots)."""
        self._laden = True
        for w, n in ((self.abs_plz, "absender_plz"), (self.abs_land, "absender_land"), (self.plz, "plz"),
                     (self.land, "land")):
            if s.get(n):
                w.setText(str(s[n]))
        nr = s.get("kundennr")
        k = self.kunden.get(nr)
        self.kunde.setCurrentText(f"{nr} – {k.get('name') or ''}" if k else (nr or ""))
        self.versandart.setCurrentText(s.get("versandart") or "")
        self.dienstleister.setCurrentText(s.get("dienstleister") or "")
        self.tarif.setCurrentText(s.get("tarif_id") or "automatisch")
        self.lieferbedingung.setCurrentText(s.get("lieferbedingung") or "")
        if s.get("datum"):
            self.datum.setDate(QDate.fromString(s["datum"], "yyyy-MM-dd"))
        for w, n in ((self.verpackung, "verpackung"), (self.frachtpflichtig, "frachtpflichtig"), (self.km, "km")):
            w.setText("" if s.get(n) is None else zahl_als_text(s[n]))
        for i, (c, sp) in self.leistungen.items():
            c.setChecked(i in (s.get("leistungen") or {}))
            if sp and i in (s.get("leistungen") or {}):
                sp.setValue(s["leistungen"][i] or 1)
        self.lht_tabelle.setRowCount(0)
        for e in s.get("lht") or ():
            self.lht_neu(e.get("lht_id"), e.get("anzahl"), e.get("gewicht"))
        self._laden = False
        self.rechnen()

    def geaendert(self, *_):
        if not self._laden:
            self.timer.start()

    def rechnen(self):
        s = self.sendung()
        self.ergebnis = fracht.rechnen(self.daten, s)
        e = self.ergebnis
        ze = e["zone_empfang"]
        farbe = {"ok": "#1E6B34", "standard": "#7A5A00"}.get(ze["status"], "#B42318")
        self.zone.setText(f"<span style='color:{farbe}'>{_e(ze['text'] or 'PLZ eingeben')}</span>")
        lw = e.get("lht") or fracht.lht_werte(s["lht"], self.daten.get("lht", []))
        g = e.get("gewicht") or fracht.gewicht(s, lw)
        self.brutto.setText(f"{zahl_als_text(g['brutto'], 1)} kg (Verpackung {zahl_als_text(g['verpackung'], 1)} kg)")
        teile = [f"{lw['anzahl']} Ladungsträger", f"{zahl_als_text(lw['stellplaetze'], 2)} Stellplätze",
                 f"Eigengewicht {zahl_als_text(lw['eigengewicht'], 1)} kg"]
        if lw.get("volumen") is not None:
            teile.append(f"{zahl_als_text(lw['volumen'], 3)} m³")
        self.lht_summe.setText(", ".join(teile) if lw["anzahl"] else "keine Ladungsträger (Gewichtstarif reicht "
                                                                    "auch ohne)")
        self.anzeige.setHtml(ergebnis_html(e))
        self.speichern_knopf.setEnabled(e.get("gesamt") is not None)
        return e

    def speichern(self):
        e = self.rechnen()
        if e.get("gesamt") is None:
            self.f.meldung("Nicht berechnet – nichts gespeichert.", fehler=True)
            return None
        nr = self.db.fracht_kalkulation_speichern(e, self.bezeichnung.text().strip())
        self.f.meldung(f"Frachtkalkulation gespeichert ({fracht.euro(e['gesamt'])}).")
        return nr


class FrachtDialog(QDialog):
    """Fracht eines Angebots berechnen: Rechner mit Gewicht, längstem Teil und Kunde aus dem Angebot vorbelegt;
    'Ins Angebot übernehmen' speichert Betrag, Eingaben und Tarif-Snapshot im Angebot (Frachtart berechnet)."""

    def __init__(self, seite):
        super().__init__(seite)
        from . import fracht_angebot, rechnen
        self.s = seite
        self.setWindowTitle(f"Fracht berechnen – Angebot {seite.kopf.get('nummer') or ''}")
        self.rechner = RechnerSeite(seite.f)
        self.rechner.speichern_knopf.hide()          # gespeichert wird mit der Übernahme ins Angebot
        werte = [rechnen.position_werte(p, seite.kopf, seite.k, seite.tabellen) if position_aktiv(p) else None
                 for p in seite.positionen]
        netto, laenge, fehlt = fracht_angebot.ware(seite.positionen, werte)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        text = f"Aus dem Angebot: Nettogewicht {zahl_als_text(netto, 1)} kg, längstes Teil {zahl_als_text(laenge, 0)} mm."
        if fehlt:
            text += f" <span style='color:#B42318'>Gewicht fehlt bei Pos. {', '.join(fehlt)}.</span>"
        self.hinweis.setText(text)
        r = self.rechner
        alt = fracht_angebot.daten(seite.kopf)
        if alt and alt.get("sendung"):
            r.setzen(alt["sendung"])
        else:
            nr = seite.kopf.get("kundennr")
            k = r.kunden.get(nr)
            if k:
                r.kunde.setCurrentText(f"{nr} – {k.get('name') or ''}")
            if seite.kopf.get("datum"):
                r.datum.setDate(QDate.fromString(seite.kopf["datum"], "yyyy-MM-dd"))
        r.bezeichnung.setText(f"Angebot {seite.kopf.get('nummer') or ''}")
        r.netto.setValue(netto)
        r.max_laenge.setText(zahl_als_text(laenge, 0) if laenge else "")
        r.ware = (seite.positionen, werte)          # Packvorschlag nach Gewicht und Packraum (paletten.py)
        r.laden_knopf.hide()                        # die Ware kommt aus diesem Angebot
        r.ware_text.setText("aus diesem Angebot")
        if not (alt and alt.get("sendung", {}).get("lht")):
            r.packvorschlag()
        r.rechnen()
        knoepfe = QDialogButtonBox()
        self.uebernehmen_knopf = knoepfe.addButton("Ins Angebot übernehmen", QDialogButtonBox.AcceptRole)
        self.uebernehmen_knopf.setObjectName("primaer")
        knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        knoepfe.accepted.connect(self.uebernehmen)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.hinweis)
        lay.addWidget(r, 1)
        lay.addWidget(knoepfe)
        self.resize(1150, 760)

    def uebernehmen(self):
        """Ergebnis ins Angebot schreiben. Ergebnis: True, wenn übernommen."""
        import json

        from . import fracht_angebot
        e = self.rechner.rechnen()
        if e.get("gesamt") is None:
            self.s.f.meldung("Fracht nicht berechnet – nichts übernommen: " + "; ".join(e.get("fehler") or []),
                             fehler=True)
            return False
        db = self.s.db
        snap = e.get("snapshot")
        text = fracht.zusammenfassung(e)
        if e.get("gewicht"):
            text += f", {zahl_als_text(e['gewicht']['brutto'], 1)} kg brutto"
        lht = ", ".join(f"{x['anzahl']} × {x['lht_id']}" for x in (e.get("lht") or {}).get("je", []))
        if lht:
            text += f", {lht}"
        if snap is None:          # Lieferbedingung ohne Fracht: 0 € ohne Tarif
            daten = dict(sendung=e["eingaben"], snapshot=None, gesamt=0.0, text=text)
        else:
            daten = dict(sendung=e["eingaben"], snapshot=snap, gesamt=e["gesamt"], text=text,
                         lht_standard=db.einstellung("fracht_lht_standard"),
                         lht_langgut=db.einstellung("fracht_lht_langgut"),
                         paletten={n: db.einstellung(n) for n in fracht_angebot.PALETTEN_EINST})
        db.angebot_aendern(self.s.id, "fracht_sendung", json.dumps(daten, ensure_ascii=False, default=str))
        db.angebot_aendern(self.s.id, "fracht", e["gesamt"])
        db.angebot_aendern(self.s.id, "fracht_modus", "berechnet" if snap is not None else "keine Fracht")
        if self.s.kopf.get("fracht_auto"):        # von Hand übernommen: Automatik aus, sonst würde sie überschreiben
            db.angebot_aendern(self.s.id, "fracht_auto", None)
        db.fracht_kalkulation_speichern(e, self.rechner.bezeichnung.text().strip(), self.s.id)
        self.s.f.meldung(f"Fracht {fracht.euro(e['gesamt'])} ins Angebot übernommen.")
        self.accept()
        self.s.neu_laden()
        return True


# ------------------------------------------------------------------ 2 Zonen und PLZ
class ZonenSeite(QWidget):
    titel = "Frachtzonen und Postleitzahlen"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        m = fenster.meldung
        self.zonen, self.plz, self.laender = (StammdatenSeite(self.db, t, m) for t in (ZONEN, PLZ, LAENDER))
        self.test_land, self.test_plz = QLineEdit("DE"), QLineEdit()
        self.test_land.setMaxLength(2)
        self.test_land.setMaximumWidth(50)
        self.test_plz.setPlaceholderText("PLZ testen")
        self.test_plz.setMaximumWidth(120)
        self.test_ergebnis = QLabel()
        self.test_ergebnis.setWordWrap(True)
        for w in (self.test_land, self.test_plz):
            w.textChanged.connect(self.testen)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("PLZ testen:"))
        oben.addWidget(self.test_land)
        oben.addWidget(self.test_plz)
        oben.addWidget(self.test_ergebnis, 1)
        for text, ziel in (("CSV exportieren", self.csv_exportieren), ("CSV importieren", self.csv_importieren),
                           ("Auf Standard zurücksetzen …", self.zuruecksetzen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, z=ziel: z())
            oben.addWidget(b)
            if ziel == self.zuruecksetzen:
                b.setToolTip("Frachtzonen und PLZ-Zuordnungen durch die Standardzonen (Richtwerte nach Entfernung "
                             "vom Versandort) ersetzen; vorher wird eine Datensicherung angelegt")
                self.standard_knopf = b
        self.oben = QTabWidget()
        self.oben.addTab(self.zonen, "Frachtzonen")
        self.oben.addTab(self.laender, "Länder")
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(self.oben)
        teiler.addWidget(_box("PLZ-Zuordnungen", self.plz))
        teiler.setSizes([300, 360])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(oben)
        lay.addWidget(teiler, 1)

    def neu_laden(self):
        for s in (self.zonen, self.plz, self.laender):
            s.neu_laden()
        self.testen()

    def testen(self, *_):
        if not self.test_plz.text().strip():
            self.test_ergebnis.setText("")
            return None
        z = fracht.zone_finden(self.db.fracht_daten(), self.test_land.text() or "DE", self.test_plz.text())
        farbe = {"ok": "#1E6B34", "standard": "#7A5A00"}.get(z["status"], "#B42318")
        self.test_ergebnis.setText(f"<span style='color:{farbe}'>{_e(z['text'])}</span>")
        return z

    def zuruecksetzen(self):
        """Frachtzonen und PLZ-Zuordnungen nach Sicherheitsabfrage auf Standard zurücksetzen
        (Datenbank.fracht_zonen_zuruecksetzen, vorher Datensicherung). Ergebnis: (entfernt, eingefügt) oder None."""
        plz = (self.db.einstellung("absender_plz") or "").strip()
        if not plz and not self.f.stumm:
            plz, ok = QInputDialog.getText(self, "Frachtzonen zurücksetzen", "Absender-PLZ (Versandort):")
            if not ok:
                return None
        fremd = self.db.fracht_zonen_fremd()
        text = (f"Alle {len(self.db.zeilen('fracht_zonen'))} Frachtzonen und {len(self.db.zeilen('fracht_plz'))} "
                "PLZ-Zuordnungen werden gelöscht, auch eigene, und durch die Standardzonen ersetzt (Palette bis "
                f"50 / 100 / 200 / 450 / 650 / über 650 km ab PLZ {plz.strip()} und Inseln). Die Preise des Richtwert-Tarifs "
                "werden passend neu geschrieben.\n\n"
                + (f"{fremd} Preiszeile(n) anderer Tarife verweisen auf Zonen, die es danach nicht mehr gibt; "
                   "diese Preise gelten dann nicht mehr.\n\n" if fremd else "")
                + "Angebote mit gespeicherter Frachtberechnung behalten ihre Tarifkopie. Vorher wird eine "
                "Datensicherung angelegt (zurückholen mit „Sicherung wiederherstellen …“ auf der Startseite).\n\nWirklich zurücksetzen?")
        if not self.f.stumm and QMessageBox.question(self, "Frachtzonen auf Standard zurücksetzen", text,
                                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return None
        try:
            weg, neu, pfad = self.db.fracht_zonen_zuruecksetzen(plz)
        except (ValueError, OSError) as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.f.fracht.neu_laden_alle()
        self.f.meldung(f"Frachtzonen auf Standard zurückgesetzt: {weg} Zeile(n) entfernt, {neu} eingefügt; "
                       f"Sicherung {Path(pfad).name}.")
        return weg, neu

    def csv_exportieren(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "PLZ-Zuordnungen exportieren",
                                                  str(self.f.ablage() / "PLZ-Zuordnungen.csv"), "CSV (*.csv)")
            if not pfad:
                return None
        Path(pfad).write_text(plz_csv(self.db.zeilen("fracht_plz")), encoding="utf-8", newline="")
        self.f.meldung(f"PLZ-Zuordnungen exportiert: {pfad}")
        return pfad

    def csv_importieren(self, pfad=None):
        """CSV einlesen; fehlerhafte Zeilen werden gemeldet und nicht übernommen. Ergebnis: (neu, ersetzt, fehler)."""
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "PLZ-Zuordnungen importieren", str(self.f.ablage()),
                                                  "CSV (*.csv *.txt)")
            if not pfad:
                return None
        roh = Path(pfad).read_bytes()
        try:
            text = roh.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = roh.decode("cp1252")
        daten = self.db.fracht_daten()
        zeilen, fehler = plz_csv_lesen(text, {z["zone_id"] for z in daten["zonen"] if z.get("zone_id")},
                                       {z["land"] for z in daten["laender"] if z.get("land")})
        neu, ersetzt = self.db.plz_importieren(zeilen)
        self.neu_laden()
        text = f"{neu} PLZ-Zuordnungen neu, {ersetzt} ersetzt" + (f", {len(fehler)} Zeilen mit Fehler" if fehler else "")
        self.f.meldung(text, fehler=bool(fehler))
        if fehler and not self.f.stumm:
            QMessageBox.warning(self, "CSV importieren", text + ":\n\n" + "\n".join(fehler[:30])
                                + ("\n…" if len(fehler) > 30 else ""))
        return neu, ersetzt, fehler


# ------------------------------------------------------------------ 3 Tarife
class TarifSeite(QWidget):
    titel = "Tarifverwaltung"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.tarife = StammdatenSeite(self.db, TARIFE, fenster.meldung)
        self.preise = StammdatenSeite(self.db, PREISE, fenster.meldung)
        self.alle = QCheckBox("Preise aller Tarife zeigen")
        self.alle.toggled.connect(self.auswahl)
        version = QPushButton("Neue Version …")
        version.clicked.connect(lambda: self.neue_version())
        self.preis_titel = QLabel()
        self.preis_titel.setObjectName("kartentitel")
        oben = QHBoxLayout()
        oben.addStretch(1)
        oben.addWidget(version)
        mitte = QHBoxLayout()
        mitte.addWidget(self.preis_titel, 1)
        mitte.addWidget(self.alle)
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addLayout(mitte)
        ul.addWidget(self.preise, 1)
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(_box("Tarife", self.tarife))
        teiler.addWidget(_box("Preisstaffeln", unten))
        teiler.setSizes([280, 420])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(oben)
        lay.addWidget(teiler, 1)
        self.tarife.ansicht.selectionModel().currentRowChanged.connect(lambda *_: self.auswahl())
        self.auswahl()

    def neu_laden(self):
        self.tarife.neu_laden()
        self.preise.neu_laden()
        self.auswahl()

    def auswahl(self, *_):
        t = self.tarife.ausgewaehlt()
        tid = t.get("tarif_id") if t else None
        if self.alle.isChecked() or not tid:
            self.preise.nur("tarif_id", None)
            self.preis_titel.setText("Preisstaffeln aller Tarife" if self.alle.isChecked() or not tid else "")
        else:
            self.preise.nur("tarif_id", tid)
            self.preis_titel.setText(f"Preisstaffeln von Tarif {tid} ({t.get('modell') or 'Tarifmodell fehlt'})")

    def neue_version(self, ab=None):
        t = self.tarife.ausgewaehlt()
        if not t or not t.get("tarif_id"):
            self.f.meldung("Bitte zuerst einen Tarif markieren.", fehler=True)
            return None
        if ab is None:
            if self.f.stumm:
                return None
            vorschlag = datetime.date.today().strftime("%d.%m.%Y")
            text, ok = QInputDialog.getText(self, "Neue Version", f"Tarif {t['tarif_id']} kopieren. Gültig ab "
                                            "(TT.MM.JJJJ):", text=vorschlag)
            if not ok:
                return None
            try:
                ab = datetime.datetime.strptime(text.strip(), "%d.%m.%Y").date().isoformat()
            except ValueError:
                self.f.meldung("Datum als TT.MM.JJJJ eingeben.", fehler=True)
                return None
        try:
            neu = self.db.fracht_tarif_neue_version(t["tarif_id"], ab)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.neu_laden()
        self.f.meldung(f"Neue Version {neu} angelegt; {t['tarif_id']} gilt bis zum Vortag.")
        return neu


# ------------------------------------------------------------------ 5 Zuschläge
class ZuschlagSeite(QWidget):
    titel = "Zuschläge"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        m = fenster.meldung
        self.zuschlaege, self.diesel, self.staffel, self.waehrungen = (
            StammdatenSeite(self.db, t, m) for t in (ZUSCHLAEGE, DIESELPREISE, DIESELSTAFFEL, WAEHRUNGEN))
        self.unter = QTabWidget()
        for s in (self.diesel, self.staffel, self.waehrungen):
            self.unter.addTab(s, s.t.titel)
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(_box("Zuschläge", self.zuschlaege))
        teiler.addWidget(self.unter)
        teiler.setSizes([380, 300])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(teiler)

    def neu_laden(self):
        for s in (self.zuschlaege, self.diesel, self.staffel, self.waehrungen):
            s.neu_laden()


# ------------------------------------------------------------------ 6 Dienstleister und Kundentarife
class DienstleisterSeite(QWidget):
    titel = "Dienstleister und Kundentarife"

    def __init__(self, fenster, tarif_seite):
        super().__init__()
        self.f, self.db, self.tarif_seite = fenster, fenster.db, tarif_seite
        self.dienstleister = StammdatenSeite(self.db, DIENSTLEISTER, fenster.meldung)
        self.kundentarife = QTableWidget(0, 6)
        self.kundentarife.setHorizontalHeaderLabels(["Kunde", "Name", "Tarif", "Tarifart", "Gültig", "Dienstleister"])
        self.kundentarife.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.kundentarife.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.kundentarife.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.kundentarife.verticalHeader().setVisible(False)
        self.kundentarife.doubleClicked.connect(self.tarif_zeigen)
        neu = QPushButton("Kundentarif anlegen")
        neu.clicked.connect(lambda: self.kundentarif_anlegen())
        hinweis = hilfe.Hinweis("Kundentarife, Rahmenverträge und Sondertarife sind Tarife mit Tarifart und (bei "
                                "Kundentarifen) Kundennummer. Sie gehen bei der automatischen Auswahl vor dem "
                                "Standardtarif. Doppelklick öffnet den Tarif in der Tarifverwaltung.",
                                schluessel="fracht_dienstleister")
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(hinweis)
        z = QHBoxLayout()
        z.addWidget(neu)
        z.addStretch(1)
        ul.addLayout(z)
        ul.addWidget(self.kundentarife, 1)
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(_box("Dienstleister", self.dienstleister))
        teiler.addWidget(_box("Kundentarife und Verträge", unten))
        teiler.setSizes([300, 380])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(teiler)

    def neu_laden(self):
        self.dienstleister.neu_laden()
        kunden = {k["kundennr"]: k for k in self.db.zeilen("kunden") if k.get("kundennr")}
        zeilen = [t for t in self.db.zeilen("fracht_tarife")
                  if t.get("kundennr") or t.get("tarifart") in ("Kundentarif", "Rahmenvertrag", "Sondertarif",
                                                                 "interner Verrechnungstarif")]
        zeilen.sort(key=lambda t: (t.get("kundennr") or "~", t.get("tarif_id") or ""))
        self.kundentarife.setRowCount(len(zeilen))
        for r, t in enumerate(zeilen):
            gueltig = " – ".join(x for x in (fracht._datum(t.get("gueltig_ab")) if t.get("gueltig_ab") else "ab sofort",
                                             fracht._datum(t.get("gueltig_bis")) if t.get("gueltig_bis") else "offen"))
            werte = (t.get("kundennr") or "alle Kunden", (kunden.get(t.get("kundennr")) or {}).get("name") or "",
                     t.get("tarif_id"), t.get("tarifart") or "Standardtarif", gueltig, t.get("dienstleister") or "")
            for c, w in enumerate(werte):
                self.kundentarife.setItem(r, c, QTableWidgetItem(str(w or "")))

    def tarif_zeigen(self, *_):
        r = self.kundentarife.currentRow()
        if r < 0:
            return
        tid = self.kundentarife.item(r, 2).text()
        self.f.fracht.zeigen(self.tarif_seite)
        self.tarif_seite.tarife.suche.setText(tid)

    def kundentarif_anlegen(self):
        n, i = "KUNDE-NEU", 2
        vorhanden = {t["tarif_id"] for t in self.db.zeilen("fracht_tarife") if t.get("tarif_id")}
        while n in vorhanden:
            n, i = f"KUNDE-NEU-{i}", i + 1
        self.db.neu("fracht_tarife", dict(tarif_id=n, tarifart="Kundentarif", modell="Gewichtstarif", aktiv="ja"))
        self.f.fracht.zeigen(self.tarif_seite)
        self.tarif_seite.tarife.suche.setText(n)
        self.f.meldung(f"Kundentarif {n} angelegt: Tarif-ID, Kundennummer und Preise eintragen.")
        return n


# ------------------------------------------------------------------ 7 Historie und Einstellungen
class HistorieSeite(QWidget):
    titel = "Historie und Einstellungen"
    SPALTEN = ("Datum", "Bezeichnung", "Empfänger", "Zone", "Tarif", "Frachtpfl. Gewicht", "Gesamt")

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.tabelle = QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.doubleClicked.connect(lambda *_: self.anzeigen())
        anzeigen = QPushButton("Kalkulation anzeigen")
        anzeigen.clicked.connect(lambda: self.anzeigen())
        hinweis = hilfe.Hinweis("Jede gespeicherte Kalkulation enthält alle verwendeten Tarif-, Zonen- und "
                                "Zuschlagswerte. Spätere Änderungen an den Frachtdaten ändern sie nicht.",
                                schluessel="fracht_historie")
        oben = QWidget()
        ol = QVBoxLayout(oben)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.addWidget(hinweis)
        z = QHBoxLayout()
        z.addWidget(anzeigen)
        z.addStretch(1)
        ol.addLayout(z)
        ol.addWidget(self.tabelle, 1)
        self.einstellungen = EinstellungenSeite(self.db, fenster.meldung, gruppen=("Frachtkosten",))
        beispiele = QPushButton("Beispieldaten laden")
        beispiele.clicked.connect(lambda: self.beispiele())
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(self.einstellungen, 1)
        z = QHBoxLayout()
        z.addWidget(beispiele)
        erkl = QLabel("fügt Beispiel-Zonen, -Tarife, -Ladehilfsmittel und -Zuschläge hinzu (BEISPIEL, keine "
                      "echten Preise); vorhandene Einträge bleiben")
        erkl.setWordWrap(True)
        z.addWidget(erkl, 1)
        ul.addLayout(z)
        richtwerte = QPushButton("Richtwerte laden")
        richtwerte.clicked.connect(lambda: self.richtwerte())
        z = QHBoxLayout()
        z.addWidget(richtwerte)
        erkl = QLabel("ersetzt alle BEISPIEL-Werte durch Richtwerte für den Palettenversand in Deutschland (Recherche "
                      "10/2026, Marktpreise + 10 % Puffer, Zonen nach Entfernung von der Absender-PLZ); eigene "
                      "Einträge bleiben")
        erkl.setWordWrap(True)
        z.addWidget(erkl, 1)
        ul.addLayout(z)
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(_box("Historie", oben))
        teiler.addWidget(_box("Einstellungen", unten))
        teiler.setSizes([400, 260])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(teiler)
        self.eintraege = []

    def neu_laden(self):
        self.einstellungen.neu_laden()
        self.eintraege = self.db.fracht_kalkulationen()
        self.tabelle.setRowCount(len(self.eintraege))
        for r, h in enumerate(self.eintraege):
            e, ein = h["ergebnis"], h["eingaben"]
            datum = datetime.datetime.fromisoformat(h["datum"]).strftime("%d.%m.%Y %H:%M") if h.get("datum") else ""
            zone = ((e.get("zone_empfang") or {}).get("zone") or {}).get("zone_id") or ""
            werte = (datum, h.get("bezeichnung") or "", f"{ein.get('land') or ''} {ein.get('plz') or ''}".strip(), zone,
                     (e.get("tarif") or {}).get("tarif_id") or "",
                     zahl_als_text((e.get("gewicht") or {}).get("frachtpflichtig"), 1) + " kg"
                     if (e.get("gewicht") or {}).get("frachtpflichtig") is not None else "",
                     fracht.euro(h["gesamt"]) if h.get("gesamt") is not None else "")
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                if c >= 5:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(r, c, it)

    def anzeigen(self, zeile=None):
        r = self.tabelle.currentRow() if zeile is None else zeile
        if r < 0 or r >= len(self.eintraege):
            self.f.meldung("Bitte zuerst eine Kalkulation markieren.", fehler=True)
            return None
        h = self.eintraege[r]
        text = ergebnis_html(h["ergebnis"])
        if self.f.stumm:
            return text
        d = QDialog(self)
        d.setWindowTitle(f"Frachtkalkulation vom {self.tabelle.item(r, 0).text()}")
        d.resize(760, 620)
        b = QTextBrowser()
        b.setHtml(text)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        lay.addWidget(b)
        lay.addWidget(knoepfe)
        d.exec()
        return text

    def richtwerte(self):
        plz = (self.db.einstellung("absender_plz") or "").strip()
        if not plz and not self.f.stumm:
            plz, ok = QInputDialog.getText(self, "Richtwerte laden", "Absender-PLZ (Versandort):")
            if not ok:
                return None
        if not self.f.stumm and QMessageBox.question(
                self, "Richtwerte laden", "Alle Frachtdaten mit BEISPIEL in der Bemerkung werden durch Richtwerte für "
                "den Palettenversand ersetzt (Zonen nach Entfernung von PLZ " + plz.strip() + "). Eigene Einträge "
                "bleiben. Angebote mit gespeicherter Frachtberechnung behalten ihre Tarifkopie.\n\nFortfahren?"
                ) != QMessageBox.Yes:
            return None
        try:
            weg, neu = self.db.fracht_richtwerte_laden(plz)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.f.fracht.neu_laden_alle()
        self.f.meldung(f"Richtwerte Palettenversand geladen: {neu} Zeilen eingefügt, {weg} Beispielzeilen ersetzt.")
        return weg, neu

    def beispiele(self):
        n = self.db.fracht_beispiele_laden()
        self.f.fracht.neu_laden_alle()
        self.f.meldung(f"{n} Beispielzeilen hinzugefügt (BEISPIEL, keine echten Preise).")
        return n


# ------------------------------------------------------------------ Reiter
class FrachtBereich(QWidget):
    """Hauptreiter Frachtkosten: nur der Rechner (Fracht kalkulieren). Die sechs Pflegeseiten (Zonen, Tarife, Paletten,
    Zuschläge, Dienstleister, Historie und Einstellungen) stehen seit 0.9.211 unter Einstellungen → Fracht
    (Patrick 30.10.2026); Knopf „Frachtdaten pflegen …“ springt dorthin. Admin-Schutz: Bereich admin_schutz.FRACHT."""

    def __init__(self, fenster):
        from .admin_schutz import FRACHT
        super().__init__()
        self.f = fenster
        self.rechner = RechnerSeite(fenster)
        self.zonen = ZonenSeite(fenster)
        self.tarife = TarifSeite(fenster)
        self.lht = StammdatenSeite(fenster.db, LHT, fenster.meldung)
        self.lht.titel = "Paletten und Ladehilfsmittel"
        self.zuschlaege = ZuschlagSeite(fenster)
        self.dienstleister = DienstleisterSeite(fenster, self.tarife)
        self.historie = HistorieSeite(fenster)
        self.pflege = [self.zonen, self.tarife, self.lht, self.zuschlaege, self.dienstleister, self.historie]
        for s, k in zip(self.pflege, ("zonen", "tarife", "lht", "zuschlaege", "dienstleister", "historie")):
            s.schluessel = f"fracht_{k}"        # Navigation der Einstellungen (einstellungen_nav.GRUPPEN, Fracht)
            s.schutz_bereich = FRACHT           # alle sechs zusammen unter dem Admin-Schutz der Frachtkosten
        oben = QHBoxLayout()
        oben.setContentsMargins(8, 4, 8, 0)
        hinweis = QLabel("Zonen, Tarife, Paletten, Zuschläge, Dienstleister und Historie stehen unter "
                         "Einstellungen → Fracht.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #5F6B7A;")
        self.pflegen_knopf = QPushButton("Frachtdaten pflegen …")
        self.pflegen_knopf.setToolTip("Einstellungen → Fracht öffnen (Frachtzonen und Postleitzahlen)")
        self.pflegen_knopf.clicked.connect(lambda: self.zeigen(self.zonen))
        oben.addWidget(hinweis, 1)
        oben.addWidget(self.pflegen_knopf)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(oben)
        lay.addWidget(self.rechner, 1)

    def zeigen(self, seite):
        """Rechner im Reiter Frachtkosten, eine Pflegeseite unter Einstellungen → Fracht."""
        if seite is self.rechner or seite is self:
            self.f.reiter.setCurrentWidget(self)
            self.rechner.neu_laden()
            return
        self.f.reiter.setCurrentWidget(self.f.bereich)
        self.f.bereich.zeigen(seite)

    def neu_laden(self):
        self.rechner.neu_laden()

    def neu_laden_alle(self):
        self.rechner.neu_laden()
        for s in self.pflege:
            if hasattr(s, "neu_laden"):
                s.neu_laden()
