"""Seite „Aufträge“ (Auftragsverwaltung) und Fenster „Angebot in Auftrag übernehmen“ (Plan Auftragsworkflow,
Patrick 13.11.2026, Paket 1). Daten und Regeln in auftraege.py.

Links die Auftragsliste mit Filter nach Status und Suche (Auftrags-, Angebots-, Artikelnummer, Kunde, Projekt,
Bestellnummer), rechts der gewählte Auftrag: Kopf, Positionen mit den übernommenen Zeiten, Kosten und Preisen, die
übernommenen Angebote mit Zeichnungen und CAD-Dateien und die Historie (wer hat wann was geändert, alt → neu).
"""
import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QSplitter, QTabBar, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import auftraege as au, auftrag_av as av, leerhinweis
from .auftrag_av_seite import AMPEL_FARBE, AvReiter
from .klartext import fehler_text

SPALTEN = ("Auftrag", "Status", "Fertig", "Kunde", "Liefertermin", "Auftragswert", "Projekt", "Pos.",
           "Auftragsdatum", "Zuständig", "Angebote")
POS_SPALTEN = ("Pos.", "Artikel", "Bezeichnung", "Werkstoff", "Abmessung", "Länge", "Menge", "Laser [min]",
               "Schweißen [min]", "Fertigung [min]", "Material €", "Fertigung €", "Preis €", "Zeichnungen",
               "Liefertermin", "Bemerkung")
HIST_SPALTEN = ("Zeit", "Benutzer", "Ereignis", "Feld", "Vorher", "Neu", "Bemerkung")
FARBE = {au.VERZOEGERT: "#FDECEA", au.ABGESCHLOSSEN: "#ECEEF1", au.AUSGELIEFERT: "#ECEEF1",
         au.MATERIAL_FEHLT: "#FFF6DB", au.FERTIG: "#E3F4E8"}
FILTER = au.FILTER


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y") if iso else ""
    except ValueError:
        return str(iso)


def _zeit(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso)).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return str(iso or "")


def _eur(x):
    return f"{float(x or 0):,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _zahl(x, stellen=1):
    try:
        return f"{float(x):.{stellen}f}".replace(".", ",") if x not in (None, "") else ""
    except (TypeError, ValueError):
        return str(x)


def _menge(x):
    try:
        return f"{float(x):g}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def _tabelle(spalten, strecken=1):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    kopf = t.horizontalHeader()
    kopf.setSectionResizeMode(QHeaderView.ResizeToContents)    # Spaltenköpfe nie abgeschnitten (Layout-Rundgang)
    kopf.setStretchLastSection(True)
    return t


def _zelle(t, r, c, text, rechts=False, farbe=None):
    it = QTableWidgetItem("" if text is None else str(text))
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if farbe:
        it.setBackground(QColor(farbe))
    t.setItem(r, c, it)
    return it


def positionen_fuellen(t, positionen):
    t.setRowCount(len(positionen))
    for r, p in enumerate(positionen):
        werte = [p.get("_nr") or p.get("nr") or p.get("angebot_pos"), p.get("artikel"), p.get("bezeichnung"),
                 p.get("werkstoff"), p.get("profil"), _zahl(p.get("laenge")), _menge(p.get("menge")),
                 _zahl(p.get("laser_min")), _zahl(p.get("schweissen_min")), _zahl(p.get("fertigung_min")),
                 _eur(p.get("material")), _eur(p.get("fertigung")), _eur(p.get("preis")),
                 len(p.get("zeichnungen") or ()) or "", _datum(p.get("liefertermin")), p.get("bemerkung") or ""]
        hand = p.get("_hand") or {}
        for c, w in enumerate(werte):
            gelb = "#FFF6DB" if (c == 6 and hand.get("menge")) or (c == 14 and hand.get("liefertermin")) else None
            _zelle(t, r, c, w, rechts=c in (5, 6, 7, 8, 9, 10, 11, 12), farbe=gelb)


# ------------------------------------------------------------------ Übernahme
class UebernahmeDialog(QDialog):
    """Auftragszusammenfassung vor der Übernahme; „Auftrag anlegen“ geht nur einmal (kein Doppelauftrag)."""

    def __init__(self, eltern, db, angebot_ids, ordner_von=None):
        super().__init__(eltern)
        self.db, self.ids, self.ordner_von = db, list(angebot_ids), ordner_von
        self.ergebnis = None
        self.z = au.zusammenfassung(db, self.ids, ordner_von)
        nummern = ", ".join(s["angebot"]["nummer"] or "?" for s in self.z["angebote"])
        self.setWindowTitle(f"Angebot in Auftrag übernehmen – {nummern}")
        k = self.z["kopf"]
        kopf = QGridLayout()            # zwei Spalten: wenig Höhe, die Positionen bekommen den Platz
        self.felder = {}
        kunde = QLabel(f"<b>{k.get('kunde') or ''}</b> {('(' + k['kundennr'] + ')') if k.get('kundennr') else ''}")
        kopf.addWidget(QLabel("Kunde:"), 0, 0)
        kopf.addWidget(kunde, 0, 1)
        for n, (f, titel) in enumerate((("projekt", "Projekt"), ("ansprechpartner", "Ansprechpartner"),
                                        ("bestellnr", "Bestellnummer des Kunden"),
                                        ("liefertermin", "Liefertermin (JJJJ-MM-TT)"), ("verantwortlich", "Zuständig"))):
            e = QLineEdit(str(k.get(f) or (au.benutzer(db)[0] if f == "verantwortlich" else "")))
            self.felder[f] = e
            zeile, spalte = divmod(n + 1, 2)
            kopf.addWidget(QLabel(titel + ":"), zeile, 2 * spalte)
            kopf.addWidget(e, zeile, 2 * spalte + 1)
        self.anforderungen = QPlainTextEdit(str(k.get("anforderungen") or ""))
        self.anforderungen.setMaximumHeight(48)
        kopf.addWidget(QLabel("Besondere Anforderungen:"), 3, 0)
        kopf.addWidget(self.anforderungen, 3, 1, 1, 3)
        kopf.setColumnStretch(1, 1)
        kopf.setColumnStretch(3, 1)
        self.ziel = QComboBox()
        self.ziel.addItem("Neuer Auftrag (Nummer wird vergeben)", None)
        for z in au.liste(db, status="Offen"):
            if z["kundennr"] == (k.get("kundennr") or "") and z["kunde"] == (k.get("kunde") or ""):
                self.ziel.addItem(f"Zu Auftrag {z['nummer']} hinzufügen ({z['positionen']} Pos.)", z["uid"])
        kopf.addWidget(QLabel("Auftrag:"), 4, 0)
        kopf.addWidget(self.ziel, 4, 1, 1, 3)
        self.tabelle = _tabelle(POS_SPALTEN, 2)
        positionen_fuellen(self.tabelle, [dict(p, _nr=p.get("angebot_pos")) for p in self.z["positionen"]])
        s = self.z["summen"]
        self.summe = QLabel(
            f"<b>{len(self.z['positionen'])} Positionen</b> aus {len(self.z['angebote'])} Angebot(en) · "
            f"Auftragswert {_eur(s['preis'])} € (Angebot netto {_eur(s['netto'])} €) · Material {_eur(s['material'])} €"
            f" · Fertigung {_eur(s['fertigung'])} € · Laserzeit {_zahl(s['laser_min'] / 60, 2)} h · Fertigungszeit "
            f"{_zahl(s['fertigung_min'] / 60, 2)} h · {s['dateien']} Zeichnungen/CAD-Dateien")
        self.summe.setWordWrap(True)
        self.hinweise = QLabel("<br>".join("⚠ " + h for h in self.z["hinweise"]))
        self.hinweise.setWordWrap(True)
        self.hinweise.setVisible(bool(self.z["hinweise"]))
        self.hinweise.setStyleSheet("background:#FFF6DB; padding:6px; border-radius:4px;")
        info = QLabel("Der Stand der Angebote wird eingefroren: die Kalkulation bleibt unverändert, Ergänzungen "
                      "macht man im Auftrag (mit Historie).")
        info.setWordWrap(True)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Auftrag anlegen")
        self.knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        self.knoepfe.accepted.connect(self.anlegen)
        self.knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(kopf)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(self.summe)
        lay.addWidget(self.hinweise)
        lay.addWidget(info)
        lay.addWidget(self.knoepfe)
        self.resize(1200, 640)

    def kopf(self):
        d = {f: e.text().strip() for f, e in self.felder.items()}
        d["anforderungen"] = self.anforderungen.toPlainText().strip()
        return d

    def anlegen(self):
        ok = self.knoepfe.button(QDialogButtonBox.Ok)
        if not ok.isEnabled():          # zweiter Klick, solange der erste läuft
            return None
        ok.setEnabled(False)
        try:
            self.ergebnis = au.uebernehmen(self.db, self.ids, self.kopf(), ordner_von=self.ordner_von,
                                           auftrag=self.ziel.currentData())
        except (au.AuftragFehler, OSError) as e:
            ok.setEnabled(True)
            QMessageBox.warning(self, "Auftrag", fehler_text(e) if isinstance(e, OSError) else str(e))
            return None
        self.accept()
        return self.ergebnis


# ------------------------------------------------------------------ Auftrag bearbeiten
class KopfDialog(QDialog):
    def __init__(self, eltern, a, kollegen=()):
        super().__init__(eltern)
        self.setWindowTitle(f"Auftrag {a['nummer']} bearbeiten")
        form = QFormLayout()
        self.felder = {}
        for f, titel in au.KOPF:
            if f == "verantwortlich":       # Zuständig: Kollegen zur Auswahl, freie Eingabe bleibt möglich
                e = QComboBox()
                e.setEditable(True)
                e.addItems(sorted(set(kollegen) | {str(a["kopf"].get(f) or "")}))
                e.setCurrentText(str(a["kopf"].get(f) or ""))
                e.text = e.currentText
            else:
                e = QLineEdit(str(a["kopf"].get(f) or ""))
            self.felder[f] = e
            form.addRow(titel + ":", e)
        self.grund = QLineEdit()
        self.grund.setPlaceholderText("Grund der Änderung (steht in der Historie)")
        form.addRow("Bemerkung:", self.grund)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(k)

    def werte(self):
        return {f: e.text().strip() for f, e in self.felder.items()}


class PositionDialog(QDialog):
    """Position nur im Auftrag ergänzen."""

    def __init__(self, eltern):
        super().__init__(eltern)
        self.setWindowTitle("Position im Auftrag ergänzen")
        form = QFormLayout()
        self.e = {}
        for f, titel, vorgabe in (("artikel", "Artikel", ""), ("bezeichnung", "Bezeichnung", ""),
                                  ("menge", "Menge", "1"), ("preis_teil", "Preis je Stück €", "0"),
                                  ("bemerkung", "Bemerkung", ""), ("grund", "Grund (Historie)", "")):
            self.e[f] = QLineEdit(vorgabe)
            form.addRow(titel + ":", self.e[f])
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Ok).setText("Ergänzen")
        k.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(k)

    def werte(self):
        return {f: e.text().strip() for f, e in self.e.items()}


class VergleichDialog(QDialog):
    """Änderung des Angebots seit der Übernahme zeigen und übernehmen."""

    def __init__(self, eltern, nummer, zeilen):
        super().__init__(eltern)
        self.setWindowTitle(f"Änderung aus Angebot {nummer} übernehmen")
        t = _tabelle(("Artikel", "Was", "Im Auftrag", "Im Angebot jetzt"), 0)
        t.setRowCount(len(zeilen))
        for r, z in enumerate(zeilen):
            for c, n in enumerate(("artikel", "was", "alt", "neu")):
                _zelle(t, r, c, z.get(n))
        self.grund = QLineEdit()
        self.grund.setPlaceholderText("Grund (z. B. Nachtrag des Kunden vom …)")
        hinweis = QLabel("Von Hand im Auftrag geänderte Mengen, Termine und Bemerkungen bleiben erhalten."
                         if zeilen else "Die Positionen sind gleich; geändert hat sich nur Kopf oder Technik.")
        hinweis.setWordWrap(True)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Ok).setText("In Auftrag übernehmen")
        k.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(t, 1)
        lay.addWidget(hinweis)
        lay.addWidget(self.grund)
        lay.addWidget(k)
        self.resize(760, 420)


# ------------------------------------------------------------------ Seite
class AuftraegeSeite(QWidget):
    titel = "Aufträge"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.zeilen = []
        self._migriert = False
        # Status als Reiterzeile mit Anzahl (ein Klick, wenig Platz); Termin und Zuständig als Auswahl daneben
        self.status_leiste = QTabBar()
        self.status_leiste.setExpanding(False)
        self.status_leiste.setUsesScrollButtons(True)
        self.status_leiste.setDrawBase(False)
        self.status_leiste.setToolTip("Aufträge nach Status zeigen; „Verzögert“ = Liefertermin überschritten")
        for x in FILTER:
            self.status_leiste.addTab(x)
        self.status_leiste.currentChanged.connect(self.neu_laden)
        self.termin = QComboBox()
        self.termin.setToolTip("Nach Liefertermin filtern")
        for x in au.TERMINE:
            self.termin.addItem(x, x)
        self.termin.currentIndexChanged.connect(self.neu_laden)
        self.wer = QComboBox()
        self.wer.setToolTip("Nach zuständigem Mitarbeiter filtern")
        self.wer.addItem("Alle Mitarbeiter", "")
        self.wer.currentIndexChanged.connect(self.neu_laden)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen nach Auftrag, Kunde, Projekt, Bestellnummer, Angebot, Artikelnummer …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.neu_laden)
        oben = QHBoxLayout()
        oben.addWidget(self.suche, 1)
        oben.addWidget(self.termin)
        oben.addWidget(self.wer)
        knoepfe = QHBoxLayout()
        self.knopf = {}
        for name, text, ziel, tip in (
                ("uebernehmen", "Angebot übernehmen …", self.angebot_uebernehmen,
                 "Beauftragte Angebote ohne Auftrag in einen Auftrag übernehmen"),
                ("bearbeiten", "Bearbeiten …", self.bearbeiten, "Auftragsdaten ändern (mit Historie)"),
                ("status", "Status …", self.status_aendern, "Status von Hand setzen (zurück nur mit Grund)"),
                ("aenderung", "Änderung übernehmen …", self.aenderung_uebernehmen,
                 "Das Angebot wurde nach der Übernahme geändert: Unterschiede zeigen und in den Auftrag übernehmen"),
                ("position", "Position ergänzen …", self.position_ergaenzen,
                 "Eine Position nur im Auftrag ergänzen (z. B. Zukaufteil, Muster, Nacharbeit), mit Historie"),
                ("loesen", "Angebot lösen …", self.angebot_loesen,
                 "Ein irrtümlich zugeordnetes Angebot wieder aus dem Auftrag nehmen (nur vor der Produktion)"),
                ("angebot", "Angebot öffnen", self.angebot_oeffnen, "Erstes Angebot des Auftrags öffnen")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            if name == "uebernehmen":
                b.setObjectName("primaer")
            self.knopf[name] = b
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        self.tabelle = _tabelle(SPALTEN, 1)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.itemSelectionChanged.connect(self.detail_zeigen)
        self.tabelle.doubleClicked.connect(lambda _: self.bearbeiten())
        leerhinweis.setzen(self.tabelle, "Keine Aufträge für diese Auswahl. Ein beauftragtes Angebot wird mit "
                                         "„Angebot übernehmen …“ zum Auftrag.")
        # Detail: Kopf, Positionen, Angebote und Dateien, Historie
        self.kopf_text = QLabel()
        self.kopf_text.setWordWrap(True)
        self.kopf_text.setTextFormat(Qt.RichText)
        self.warnung = QLabel()
        self.warnung.setWordWrap(True)
        self.warnung.setStyleSheet("background:#FFF6DB; padding:6px; border-radius:4px;")
        self.warnung.setVisible(False)
        self.reiter = QTabWidget()
        self.pos = _tabelle(POS_SPALTEN, 2)
        self.pos.doubleClicked.connect(self.position_aendern)
        self.pos.setToolTip("Doppelklick auf Menge, Liefertermin oder Bemerkung: im Auftrag ändern (mit Historie)")
        self.angebote = _tabelle(("Angebot", "Übernommen", "Netto €", "Prüfsumme", "Zeichnungen / CAD-Dateien"), 4)
        self.hist = _tabelle(HIST_SPALTEN, 2)
        self.av = AvReiter(self)
        self.reiter.addTab(self.pos, "Positionen")
        self.reiter.addTab(self.av, "Arbeitsvorbereitung")
        self.reiter.addTab(self.angebote, "Angebote und Dateien")
        self.reiter.addTab(self.hist, "Historie")
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.kopf_text)
        rl.addWidget(self.warnung)
        rl.addWidget(self.reiter, 1)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.tabelle, 1)
        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.addWidget(links)
        self.teiler.addWidget(rechts)
        self.teiler.setStretchFactor(0, 1)
        self.teiler.setStretchFactor(1, 1)
        self.info = QLabel()
        lay = QVBoxLayout(self)
        lay.addWidget(self.status_leiste)
        lay.addLayout(oben)
        lay.addLayout(knoepfe)
        lay.addWidget(self.teiler, 1)
        lay.addWidget(self.info)
        self.neu_laden()

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_veraltet", False):
            self.neu_laden()

    def _ordner_von(self, i):
        try:
            return self.f.angebot_ordner(self.db.angebot(i))
        except (OSError, TypeError, KeyError, AttributeError):
            return None

    def migrieren(self):
        """Bestehende beauftragte Angebote einmal als Aufträge übernehmen (F5a)."""
        if self._migriert:
            return 0
        self._migriert = True
        try:
            n = au.migrieren(self.db, self._ordner_von)
        except Exception as e:          # die Liste muss trotzdem erscheinen
            self.f.meldung(f"Bestehende Aufträge ließen sich nicht übernehmen: {fehler_text(e)}", fehler=True)
            return 0
        if n:
            self.f.meldung(f"{n} bestehende beauftragte Angebote als Aufträge übernommen (Seite Aufträge).")
        return n

    # ------------------------------------------------ Liste
    def neu_laden(self, *_):
        if not self.f.stumm and not self.isVisible():
            self._veraltet = True
            return
        self._veraltet = False
        self.migrieren()
        gewaehlt = self.gewaehlt()
        alle = au.alle_zeilen(self.db)
        self._leiste_fuellen(alle)
        self.zeilen = au.filtern(alle, self.suche.text(), self.status_filter(), self.termin.currentData(),
                                 self.wer.currentData())
        self.tabelle.blockSignals(True)
        self.tabelle.setRowCount(len(self.zeilen))
        for r, z in enumerate(self.zeilen):
            status = z["status"] + (" · verzögert" if z["verzoegert"] else "") + (" · ⚠ Angebot geändert"
                                                                                  if z["geaendert_angebot"] else "")
            farbe = FARBE.get(au.VERZOEGERT if z["verzoegert"] else z["status"])
            fertig = "–" if z["fortschritt"] is None else f"{z['fortschritt'] * 100:.0f} %"
            werte = [z["nummer"], status, fertig, z["kunde"], _datum(z["liefertermin"]), _eur(z["wert"]),
                     z["projekt"], z["positionen"], _datum(z["auftragsdatum"]), z["verantwortlich"],
                     ", ".join(z["angebote"])]
            for c, w in enumerate(werte):
                _zelle(self.tabelle, r, c, w, rechts=c in (2, 5, 7), farbe=farbe)
        self.tabelle.blockSignals(False)
        r = next((r for r, z in enumerate(self.zeilen) if z["uid"] == gewaehlt), 0 if self.zeilen else -1)
        if r >= 0:
            self.tabelle.selectRow(r)
        self.detail_zeigen()
        offen = sum(1 for z in alle if z["status"] in au.OFFEN)
        frei = len(self._ohne_auftrag())
        wert = sum(z["wert"] for z in self.zeilen)
        self.info.setText(f"{len(self.zeilen)} Aufträge gezeigt (Wert {_eur(wert)} €) · {offen} offen"
                          + (f" · {frei} beauftragte Angebote noch ohne Auftrag" if frei else ""))

    def status_filter(self):
        i = self.status_leiste.currentIndex()
        return FILTER[i] if 0 <= i < len(FILTER) else "Offen"

    def filter_setzen(self, status="Alle", termin=None, wer=None):
        """Filter von außen setzen (Auftrag zeigen, Tests)."""
        for w, wert in ((self.termin, termin), (self.wer, wer)):
            if wert is not None:
                w.blockSignals(True)
                w.setCurrentIndex(max(0, w.findData(wert)))
                w.blockSignals(False)
        self.status_leiste.blockSignals(True)
        self.status_leiste.setCurrentIndex(FILTER.index(status) if status in FILTER else 0)
        self.status_leiste.blockSignals(False)
        self.neu_laden()

    def _leiste_fuellen(self, alle):
        n = au.anzahl_je_filter(alle)
        for i, f in enumerate(FILTER):
            self.status_leiste.setTabText(i, f"{f} ({n[f]})")
            self.status_leiste.setTabTextColor(i, QColor("#B42318") if f == au.VERZOEGERT and n[f] else QColor())
        namen = sorted({z["verantwortlich"] for z in alle if z["verantwortlich"]} | set(self._kollegen()))
        jetzt = [self.wer.itemData(i) for i in range(1, self.wer.count())]
        if namen != jetzt:
            alt = self.wer.currentData()
            self.wer.blockSignals(True)
            while self.wer.count() > 1:
                self.wer.removeItem(1)
            for k in namen:
                self.wer.addItem(k, k)
            self.wer.setCurrentIndex(max(0, self.wer.findData(alt)))
            self.wer.blockSignals(False)

    def _kollegen(self):
        try:
            from . import teilen
            return [k for k in teilen.mitarbeiter(self.db) if k]
        except Exception:
            return []

    def gewaehlt(self):
        r = self.tabelle.currentRow() if hasattr(self, "tabelle") else -1
        return self.zeilen[r]["uid"] if 0 <= r < len(self.zeilen) else None

    def waehlen(self, uid):
        for r, z in enumerate(self.zeilen):
            if z["uid"] == uid:
                self.tabelle.selectRow(r)
                return True
        return False

    def detail_zeigen(self):
        uid = self.gewaehlt()
        a = au.auftrag(self.db, uid) if uid else None
        for n in ("bearbeiten", "status", "angebot", "position", "loesen"):
            self.knopf[n].setEnabled(a is not None)
        if a is None:
            self.kopf_text.setText("")
            self.warnung.setVisible(False)
            self.knopf["aenderung"].setVisible(False)
            for t in (self.pos, self.angebote, self.hist):
                t.setRowCount(0)
            self.av.zeigen(None)
            return
        k = a["kopf"]
        zeilen = [f"<b style='font-size:14pt'>Auftrag {a['nummer']}</b> · {a['status']}",
                  f"<b>{k.get('kunde') or ''}</b> {k.get('kundennr') or ''}"
                  + (f" · Ansprechpartner {k['ansprechpartner']}" if k.get("ansprechpartner") else "")
                  + (f" · Projekt {k['projekt']}" if k.get("projekt") else ""),
                  f"Auftragsdatum {_datum(k.get('auftragsdatum'))} · Liefertermin {_datum(k.get('liefertermin'))}"
                  + (f" · Bestellung {k['bestellnr']}" if k.get("bestellnr") else "")
                  + f" · Wert {_eur(a['wert'])} € · Zuständig {k.get('verantwortlich') or '–'}"]
        if k.get("anforderungen"):
            zeilen.append(f"<i>Anforderungen:</i> {k['anforderungen']}")
        g, av_text = av.zusammenfassung(self.db, a)
        zeilen[0] += f" · <span style='color:{AMPEL_FARBE[g]}'>●</span> {av_text}"
        self.kopf_text.setText("<br>".join(zeilen))
        geaendert = au.angebot_geaendert(self.db, a)
        falsch = au.pruefen(self.db, uid)
        texte = []
        if geaendert:
            texte.append(f"⚠ Angebot {', '.join(geaendert)} wurde nach der Übernahme geändert. Der Auftrag rechnet "
                         "weiter mit dem übernommenen Stand; „Änderung übernehmen …“ zeigt die Unterschiede.")
        if falsch:
            texte.append(f"⚠ {len(falsch)} Einträge der Historie passen nicht mehr zu ihrer Prüfsumme (nachträglich "
                         "in der Datei geändert).")
        self.warnung.setText("<br>".join(texte))
        self.warnung.setVisible(bool(texte))
        self.knopf["aenderung"].setVisible(bool(geaendert))
        positionen_fuellen(self.pos, a["positionen"])
        self.av.zeigen(a)
        self.angebote.setRowCount(len(a["angebote"]))
        for r, x in enumerate(a["angebote"]):
            st = x["stand"]
            dateien = st.get("dateien") or ()
            _zelle(self.angebote, r, 0, x["nummer"])
            _zelle(self.angebote, r, 1, _zeit(x["am"]))
            _zelle(self.angebote, r, 2, _eur(st.get("netto")), rechts=True)
            _zelle(self.angebote, r, 3, x["kennung"])
            _zelle(self.angebote, r, 4, ", ".join(d["name"] for d in dateien) or "keine")
        hist = au.historie(self.db, uid)
        self.hist.setRowCount(len(hist))
        for r, h in enumerate(reversed(hist)):          # neueste oben
            for c, n in enumerate(("am", "wer", "ereignis", "feld", "alt", "neu", "bemerkung")):
                _zelle(self.hist, r, c, _zeit(h[n]) if n == "am" else h[n])

    # ------------------------------------------------ Aktionen
    def _ohne_auftrag(self):
        return [r[0] for r in self.db.con.execute(
            "SELECT id FROM angebote WHERE vorgang='Beauftragt' AND fremd IS NULL AND (uid IS NULL OR uid NOT IN "
            "(SELECT angebot FROM auftrag_angebote)) ORDER BY datum DESC, id DESC")]

    def angebot_uebernehmen(self, angebot_ids=None, dialog=None):
        """Übernahme mit Zusammenfassung. Ohne IDs: Auswahl der beauftragten Angebote ohne Auftrag.
        dialog(UebernahmeDialog) -> bool ersetzt exec (Tests). Ergebnis: uid des Auftrags oder None."""
        if self.db.nur_lesen:
            self.f.meldung(f"Lesemodus – {self.db.nur_lesen}.", fehler=True)
            return None
        if not angebot_ids:
            frei = self._ohne_auftrag()
            if not frei:
                self.f.meldung("Alle beauftragten Angebote sind schon in einem Auftrag.")
                return None
            texte = [f"{a['nummer']} – {a.get('kunde') or ''}" for a in (self.db.angebot(i) for i in frei)]
            if self.f.stumm and dialog is None:
                angebot_ids = frei[:1]
            else:
                t, ok = QInputDialog.getItem(self, "Angebot in Auftrag übernehmen", "Beauftragtes Angebot:", texte,
                                             0, False)
                if not ok:
                    return None
                angebot_ids = [frei[texte.index(t)]]
        return uebernehmen_mit_dialog(self.f, angebot_ids, dialog, self)

    def bearbeiten(self, werte=None, grund=None):
        uid = self.gewaehlt()
        a = au.auftrag(self.db, uid) if uid else None
        if a is None:
            return 0
        if werte is None:
            d = KopfDialog(self, a, self._kollegen())
            if d.exec() != QDialog.Accepted:
                return 0
            werte, grund = d.werte(), d.grund.text()
        n = 0
        try:
            for f, w in werte.items():
                n += au.aendern(self.db, uid, f, w, grund or "")
        except au.AuftragFehler as e:
            self.f.meldung(str(e), fehler=True)
        self.neu_laden()
        if n:
            self.f.meldung(f"Auftrag {a['nummer']}: {n} Feld(er) geändert (Historie).")
        return n

    def position_aendern(self, index=None, wert=None, grund=""):
        uid = self.gewaehlt()
        a = au.auftrag(self.db, uid) if uid else None
        if a is None or index is None or not 0 <= index.row() < len(a["positionen"]):
            return False
        feld = {6: "menge", 14: "liefertermin", 15: "bemerkung"}.get(index.column())
        if feld is None:
            self.f.meldung("Im Auftrag lassen sich Menge, Liefertermin und Bemerkung einer Position ändern "
                           "(Doppelklick auf die Zelle).")
            return False
        p = a["positionen"][index.row()]
        if wert is None:
            titel = dict(au.POSITION_AENDERBAR)[feld]
            alt = _menge(p.get(feld)) if feld == "menge" else str(p.get(feld) or "")
            wert, ok = QInputDialog.getText(self, f"Pos. {p.get('_nr')} {p.get('artikel') or ''}",
                                            f"{titel}{' (JJJJ-MM-TT)' if feld == 'liefertermin' else ''}:", text=alt)
            if not ok:
                return False
            grund, _ = QInputDialog.getText(self, "Grund", "Grund der Änderung (Historie):")
        try:
            geaendert = au.aendern(self.db, uid, feld, wert, grund, position=p["uid"])
        except au.AuftragFehler as e:
            self.f.meldung(str(e), fehler=True)
            return False
        self.neu_laden()
        return geaendert

    def status_aendern(self, status=None, grund=""):
        uid = self.gewaehlt()
        a = au.auftrag(self.db, uid) if uid else None
        if a is None:
            return False
        if status is None:
            status, ok = QInputDialog.getItem(self, f"Auftrag {a['nummer']}", "Status:", list(au.STATUS_LISTE),
                                              au.STATUS_LISTE.index(a["status"] or au.NEU), False)
            if not ok:
                return False
            grund, _ = QInputDialog.getText(self, "Grund", "Bemerkung (Pflicht, wenn der Status zurückgeht):")
        try:
            r = au.status_setzen(self.db, uid, status, grund)
        except au.AuftragFehler as e:
            self.f.meldung(str(e), fehler=True)
            return False
        self.neu_laden()
        return r

    def aenderung_uebernehmen(self, bestaetigen=None):
        uid = self.gewaehlt()
        a = au.auftrag(self.db, uid) if uid else None
        if a is None:
            return False
        geaendert = set(au.angebot_geaendert(self.db, a))
        n = 0
        for x in a["angebote"]:
            if x["nummer"] not in geaendert:
                continue
            i = au.angebot_id(self.db, x["uid"])
            zeilen = au.vergleich(self.db, uid, x["uid"], self._ordner_von(i))
            grund = ""
            if bestaetigen is None:
                d = VergleichDialog(self, x["nummer"], zeilen)
                if d.exec() != QDialog.Accepted:
                    continue
                grund = d.grund.text()
            elif not bestaetigen(x["nummer"], zeilen):
                continue
            au.aktualisieren(self.db, uid, x["uid"], grund, self._ordner_von(i))
            n += 1
        self.neu_laden()
        return n

    def position_ergaenzen(self, werte=None):
        """Position nur im Auftrag ergänzen. werte: dict(artikel, bezeichnung, menge, preis_teil, bemerkung, grund)
        ersetzt das Fenster (Tests)."""
        uid = self.gewaehlt()
        if uid is None:
            return None
        if werte is None:
            d = PositionDialog(self)
            if d.exec() != QDialog.Accepted:
                return None
            werte = d.werte()
        try:
            p = au.position_hinzufuegen(self.db, uid, **werte)
        except au.AuftragFehler as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.neu_laden()
        return p

    def angebot_loesen(self, angebot_uid=None, grund=None):
        uid = self.gewaehlt()
        a = au.auftrag(self.db, uid) if uid else None
        if a is None or not a["angebote"]:
            return False
        if angebot_uid is None:
            texte = [x["nummer"] for x in a["angebote"]]
            t, ok = QInputDialog.getItem(self, f"Auftrag {a['nummer']}", "Angebot aus dem Auftrag lösen:", texte, 0,
                                         False)
            if not ok:
                return False
            angebot_uid = a["angebote"][texte.index(t)]["uid"]
            grund, ok = QInputDialog.getText(self, "Grund", "Grund (steht in der Historie):")
            if not ok:
                return False
        try:
            au.angebot_entfernen(self.db, uid, angebot_uid, grund)
        except au.AuftragFehler as e:
            self.f.meldung(str(e), fehler=True)
            return False
        self.neu_laden()
        return True

    def angebot_oeffnen(self):
        uid = self.gewaehlt()
        a = au.auftrag(self.db, uid) if uid else None
        for x in (a or {}).get("angebote") or ():
            i = au.angebot_id(self.db, x["uid"])
            if i:
                self.f.angebot_oeffnen(i)
                return i
        if a:
            self.f.meldung("Das Angebot dieses Auftrags gibt es auf diesem Arbeitsplatz nicht (mehr); der "
                           "übernommene Stand steht im Auftrag.")
        return None


def uebernehmen_mit_dialog(fenster, angebot_ids, dialog=None, eltern=None):
    """Zusammenfassung zeigen und übernehmen. dialog(d) -> bool ersetzt exec (Tests). Ergebnis: uid oder None."""
    db = fenster.db
    vorh = next((au.von_angebot(db, i) for i in angebot_ids if au.von_angebot(db, i)), None)
    if vorh:
        fenster.meldung(f"Das Angebot ist schon im Auftrag {au.nummer(db, vorh)}.")
        fenster.auftrag_zeigen(vorh)
        return vorh

    def ordner_von(i):
        try:
            return fenster.angebot_ordner(db.angebot(i))
        except (OSError, TypeError, KeyError, AttributeError):
            return None
    try:
        d = UebernahmeDialog(eltern or fenster, db, angebot_ids, ordner_von)
    except au.AuftragFehler as e:
        fenster.meldung(str(e), fehler=True)
        return None
    if dialog is not None:
        if not dialog(d):
            return None
        uid = d.ergebnis or d.anlegen()
    else:
        if d.exec() != QDialog.Accepted:
            return None
        uid = d.ergebnis
    if uid:
        fenster.meldung(f"Auftrag {au.nummer(db, uid)} angelegt (Seite Aufträge).")
        fenster.auftrag_zeigen(uid)
    return uid
