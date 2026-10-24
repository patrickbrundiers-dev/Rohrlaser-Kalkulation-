"""Fenster „Palettenbegleitschein“ je beauftragtem Angebot (Plan Palettenbegleitschein P2): Auftragsdaten, Palettenanzahl
(automatisch aus der Packliste oder von Hand), Packliste mit Lagenaufbau je Palette, Arbeitsschritte, Status und
Hinweis; Druck als PDF (je Palette ein A4-Querblatt) in den Ordner des Angebots. Jede Änderung wird sofort gespeichert
(wie im Tool v97)."""
import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import ausgabe, feiertage, paletten, palettenschein, pdf
from .stammdaten import zahl_als_text

HINWEIS_TEXT = {"leer": "", "normal": "passt in normaler Schrift", "klein": "wird etwas kleiner gedruckt",
                "sehr klein": "wird deutlich kleiner gedruckt", "zu lang": "zu lang – das Ende wird abgeschnitten"}


def _zelle(text, rechts=False):
    it = QTableWidgetItem("" if text is None else str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it


def dateipfad(fenster, kopf, zusatz="Palettenbegleitschein"):
    return fenster.angebot_ordner(kopf) / (ausgabe.dateiname(kopf, zusatz) + ".pdf")


def scheine_drucken(fenster, angebot_ids, pfad=None, nur=None):
    """Palettenscheine eines oder mehrerer Angebote als ein PDF; nur = Palettennummern (Nachdruck, ein Angebot).
    Vermerkt 'gedruckt am'. Ergebnis: Pfad oder None."""
    db = fenster.db
    alle, stamm = [], palettenschein.stammdaten(db)
    einst = stamm["einst"]
    for i in angebot_ids:
        z = palettenschein.zusammenstellen(db, i, stamm=stamm)
        seiten = palettenschein.seiten(z["kopf"], z["schein"], z["packliste"], z["gruppen"])
        if nur:
            seiten = [s for s in seiten if s.get("nr") in nur] or seiten
        alle += seiten
        if not db.nur_lesen:
            d = db.palettenschein(i)
            d["gedruckt_am"] = datetime.date.today().isoformat()
            db.palettenschein_speichern(i, d)
    if pfad is None:
        try:
            if len(angebot_ids) == 1:
                kopf = db.angebot(angebot_ids[0])
                pfad = dateipfad(fenster, kopf, "Palettenbegleitschein" + (
                    " Nachdruck " + "-".join(str(n) for n in nur) if nur else ""))
            else:
                pfad = fenster.ablage() / f"Palettenscheine {datetime.datetime.now():%Y-%m-%d %H%M}.pdf"
        except OSError as e:
            if not fenster.stumm:
                QMessageBox.warning(fenster, "Palettenschein", f"Der Ordner lässt sich nicht anlegen:\n{e}")
            return None
    try:
        pdf.palettenschein_pdf(pfad, alle, einst, titel=None if len(angebot_ids) == 1 else "Sammeldruck")
    except PermissionError:
        if not fenster.stumm:
            QMessageBox.warning(fenster, "Palettenschein", f"Die Datei konnte nicht gespeichert werden:\n{pfad}\n\n"
                                "Ist sie noch in einem anderen Programm geöffnet?")
        return None
    fenster.meldung(f"Palettenbegleitschein gespeichert: {pfad}")
    fenster.datei_oeffnen(pfad)
    return pfad


class PalettenscheinDialog(QDialog):
    def __init__(self, fenster, angebot_id, parent=None):
        super().__init__(parent or fenster)
        self.f, self.db, self.id = fenster, fenster.db, angebot_id
        self._laden = True
        self.z = palettenschein.zusammenstellen(self.db, angebot_id)
        self.d, kopf = self.z["schein"], self.z["kopf"]
        self.land = self.db.einstellung("versand_bundesland")
        self.setWindowTitle(f"Palettenbegleitschein – Angebot {kopf.get('nummer') or ''}")
        nur_lesen = bool(self.db.nur_lesen or kopf.get("fremd"))

        # ------------------------------------------------ Auftrag
        auftrag = QGroupBox("Auftragsdaten")
        fa = QFormLayout(auftrag)
        fa.addRow("Auftrag", QLabel(f"<b>{kopf.get('nummer') or ''}</b>"))
        fa.addRow("Kunde", QLabel(kopf.get("kunde") or ""))
        self.bestellnr = QLineEdit(kopf.get("auftragsnr") or "")
        self.bestellnr.setPlaceholderText("Auftragsnummer des Kunden")
        self.bestellnr.editingFinished.connect(self._auftrag_speichern)
        fa.addRow("Bestellnummer", self.bestellnr)
        self.mit_termin = QCheckBox()
        self.termin = QDateEdit()
        self.termin.setDisplayFormat("dd.MM.yyyy")
        self.termin.setCalendarPopup(True)
        t = kopf.get("liefertermin")
        self.mit_termin.setChecked(bool(t))
        self.termin.setDate(QDate.fromString(t, "yyyy-MM-dd") if t else QDate.currentDate())
        self.termin.setEnabled(bool(t))
        self.mit_termin.toggled.connect(self.termin.setEnabled)
        self.mit_termin.toggled.connect(self._auftrag_speichern)
        self.termin.dateChanged.connect(self._auftrag_speichern)
        zeile = QHBoxLayout()
        zeile.addWidget(self.mit_termin)
        zeile.addWidget(self.termin, 1)
        for text, n in (("Heute", 0), ("+5 AT", 5), ("+10 AT", 10), ("+15 AT", 15)):
            b = QPushButton(text)
            b.setToolTip("Arbeitstage ab heute, ohne Wochenende und Feiertage des Bundeslands aus den Einstellungen")
            b.clicked.connect(lambda _=False, n=n: self.termin_setzen(n))
            zeile.addWidget(b)
        fa.addRow("Lieferdatum", zeile)
        self.termin_hinweis = QLabel()
        self.termin_hinweis.setStyleSheet("color:#B54708")
        fa.addRow("", self.termin_hinweis)

        # ------------------------------------------------ Paletten
        pal = QGroupBox("Paletten")
        lp = QVBoxLayout(pal)
        self.auto = QRadioButton("Automatisch berechnen (Lagen je Palette, Höhe und Gewicht)")
        self.hand = QRadioButton("Von Hand:")
        self.anzahl = QSpinBox()
        self.anzahl.setRange(1, 999)
        self.unbekannt = QCheckBox("Anzahl noch nicht bekannt")
        self.ergebnis = QLabel()
        self.ergebnis.setWordWrap(True)
        self.ergebnis.setTextFormat(Qt.RichText)
        h = QHBoxLayout()
        h.addWidget(self.hand)
        h.addWidget(self.anzahl)
        h.addWidget(QLabel("Paletten, Stück pro Palette"))
        self.stueck_text = QLineEdit()
        self.stueck_text.setPlaceholderText("z. B. 100 oder 100, 100, 50 oder 3x80, 10 (optional)")
        h.addWidget(self.stueck_text, 1)
        self.verteilen_knopf = QPushButton("Verteilen")
        self.verteilen_knopf.setToolTip("Auftragsstückzahl gleichmäßig auf die Paletten verteilen")
        self.verteilen_knopf.clicked.connect(self.verteilen)
        h.addWidget(self.verteilen_knopf)
        self.stueck_hinweis = QLabel()
        lp.addWidget(self.auto)
        lp.addWidget(self.ergebnis)
        lp.addLayout(h)
        lp.addWidget(self.stueck_hinweis)
        lp.addWidget(self.unbekannt)
        self.packliste = QTableWidget(0, 6)
        self.packliste.setHorizontalHeaderLabels(["Palette", "Ladungsträger", "Stück", "Höhe [mm]", "Brutto [kg]",
                                                  "Aufbau (Lagen je Position)"])
        self.packliste.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.packliste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.packliste.setWordWrap(True)
        lp.addWidget(QLabel("<b>Packliste</b>"))
        lp.addWidget(self.packliste, 1)
        self.teile = QTableWidget(0, 8)
        self.teile.setHorizontalHeaderLabels(["Pos.", "Artikel", "Stück", "Packmaß [mm]", "kg je Stück",
                                              "Ladungsträger", "Stück je Palette", "max. je Palette (von Hand)"])
        self.teile.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.teile.setToolTip("Stück je Palette = volle Palette nach Lagen, Höhe und Gewicht. Von Hand: ersetzt die "
                              "Rechnung dieser Position (0 = automatisch).")
        lp.addWidget(QLabel("<b>Positionen</b>"))
        lp.addWidget(self.teile, 1)

        # ------------------------------------------------ Arbeitsschritte, Status, Hinweis
        rechts = QWidget()
        lr = QVBoxLayout(rechts)
        lr.setContentsMargins(0, 0, 0, 0)
        arb = QGroupBox("Arbeitsschritte – Auswahl für den Ausdruck (abgehakt wird in der Produktion)")
        la = QVBoxLayout(arb)
        knoepfe = QHBoxLayout()
        for text, ziel in (("Vorschlag aus dem Angebot", self.vorschlag), ("Alle", lambda: self.alle(True)),
                           ("Keine", lambda: self.alle(False))):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        la.addLayout(knoepfe)
        raster = QGridLayout()
        self.haken = {}
        gruppen = dict(self.z["gruppen"])
        for k in self.d.get("arbeiten") or ():          # Schritte, die nicht (mehr) in der Liste stehen
            g, _, s = k.partition(palettenschein.TRENNER)
            if s and s not in gruppen.setdefault(g, []):
                gruppen[g] = gruppen[g] + [s]
        for spalte, (g, liste) in enumerate(gruppen.items()):
            box = QGroupBox(g)
            lb = QVBoxLayout(box)
            for s in liste:
                cb = QCheckBox(s)
                cb.toggled.connect(self.speichern)
                self.haken[palettenschein.schluessel(g, s)] = cb
                lb.addWidget(cb)
            lb.addStretch(1)
            raster.addWidget(box, 0, spalte)
        la.addLayout(raster)
        lr.addWidget(arb)
        st = QGroupBox("Auftragsstatus („Versendet“ schließt den Auftrag ab)")
        ls = QVBoxLayout(st)
        self.status = {}
        for s in palettenschein.STATUS:
            cb = QCheckBox(s)
            cb.toggled.connect(lambda an, s=s: self.status_geaendert(s, an))
            self.status[s] = cb
            ls.addWidget(cb)
        lr.addWidget(st)
        hw = QGroupBox("Hinweis")
        lh = QVBoxLayout(hw)
        self.hinweis = QPlainTextEdit()
        self.hinweis.setMaximumHeight(110)
        self.hinweis.textChanged.connect(self.speichern)
        self.hinweis_info = QLabel()
        lh.addWidget(self.hinweis)
        lh.addWidget(self.hinweis_info)
        lr.addWidget(hw)
        lr.addStretch(1)

        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(auftrag)
        ll.addWidget(pal, 1)
        inhalt = QWidget()
        li = QHBoxLayout(inhalt)
        li.addWidget(links, 3)
        li.addWidget(rechts, 2)
        rollen = QScrollArea()
        rollen.setWidgetResizable(True)
        rollen.setWidget(inhalt)

        unten = QDialogButtonBox()
        self.druck_knopf = unten.addButton("Palettenscheine drucken (PDF)", QDialogButtonBox.ActionRole)
        self.druck_knopf.setObjectName("primaer")
        self.druck_knopf.clicked.connect(self.drucken)
        self.nachdruck_nr = QSpinBox()
        self.nachdruck_nr.setRange(1, 999)
        self.nachdruck_nr.setPrefix("Palette ")
        nach = unten.addButton("Nachdruck", QDialogButtonBox.ActionRole)
        nach.setToolTip("Nur den Schein der gewählten Palette noch einmal drucken")
        nach.clicked.connect(lambda: self.drucken(nur=[self.nachdruck_nr.value()]))
        unten.addButton("Schließen", QDialogButtonBox.RejectRole).clicked.connect(self.reject)
        fuss = QHBoxLayout()
        self.stand = QLabel()
        fuss.addWidget(self.stand, 1)
        fuss.addWidget(self.nachdruck_nr)
        fuss.addWidget(unten)
        lay = QVBoxLayout(self)
        lay.addWidget(rollen, 1)
        lay.addLayout(fuss)
        self.resize(1450, 900)

        # Werte setzen
        self.auto.setChecked(bool(self.d.get("paletten_auto")))
        self.hand.setChecked(not self.d.get("paletten_auto"))
        self.anzahl.setValue(self.d.get("paletten") or max(1, self.z["packliste"]["anzahl"]))
        self.unbekannt.setChecked(bool(self.d.get("unbekannt")))
        self.stueck_text.setText(self.d.get("stueck_text") or "")
        for k, cb in self.haken.items():
            cb.setChecked(k in (self.d.get("arbeiten") or ()))
        for s, cb in self.status.items():
            cb.setChecked(s in (self.d.get("status") or ()))
        self.hinweis.setPlainText(self.d.get("hinweis") or "")
        for w in (self.auto, self.hand, self.unbekannt):
            w.toggled.connect(self.speichern)
        self.anzahl.valueChanged.connect(self.speichern)
        self.stueck_text.textChanged.connect(self.speichern)
        if nur_lesen:
            for w in [self.bestellnr, self.mit_termin, self.termin, self.auto, self.hand, self.anzahl,
                      self.unbekannt, self.stueck_text, self.verteilen_knopf, self.hinweis] + \
                    list(self.haken.values()) + list(self.status.values()):
                w.setEnabled(False)
        self._laden = False
        self.anzeigen()

    # ------------------------------------------------ Anzeige
    def anzeigen(self):
        e = self.z["packliste"]
        self._laden = True
        man = self.hand.isChecked()
        for w in (self.anzahl, self.stueck_text, self.verteilen_knopf):
            w.setEnabled(man and not self.unbekannt.isChecked() and not self.db.nur_lesen)
        v = e["vorgaben"]
        text = f"<b>{paletten.kurz(e)}</b> · {zahl_als_text(e['gesamt_stueck'], 0)} Stück"
        if e.get("netto"):
            text += f", {zahl_als_text(e['netto'], 0)} kg netto"
        text += (f"<br><span style='color:#68727E'>Grundlage: max. {zahl_als_text(v['hoehe_gesamt'], 0)} mm hoch inkl. "
                 f"Palette, max. {zahl_als_text(v['max_brutto'], 0) + ' kg brutto' if v['max_brutto'] else 'Nutzlast'}"
                 f", Lagenausnutzung {zahl_als_text(v['fuellgrad'] * 100, 0)} %, Positionen "
                 f"{'gemischt' if v['mischen'] else 'je eigene Paletten'} (Einstellungen › Versand)</span>")
        if e["hinweise"]:
            text += "<br><span style='color:#B54708'>" + "<br>".join(e["hinweise"]) + "</span>"
        self.ergebnis.setText(text)
        self.packliste.setRowCount(len(e["paletten"]))
        for r, p in enumerate(e["paletten"]):
            werte = [p["nr"], p["bezeichnung"], sum(n for _, n in p["inhalt"]),
                     zahl_als_text(p["hoehe"], 0) if p.get("hoehe") else "", zahl_als_text(p["brutto"], 0),
                     "\n".join(p["aufbau"])]
            for c, w in enumerate(werte):
                self.packliste.setItem(r, c, _zelle(w, c in (0, 2, 3, 4)))
        self.packliste.resizeRowsToContents()
        st = e["stuecke"]
        self.teile.setRowCount(len(st))
        for r, s in enumerate(st):
            masse = " × ".join(zahl_als_text(x, 0) for x in s["masse"]) if s["masse"] else "unbekannt"
            werte = [s["pos"], " · ".join(t for t in (s["artikel"], s["bezeichnung"]) if t), s["stueck"], masse,
                     zahl_als_text(s["gewicht"], 2) if s["gewicht"] else "fehlt", s.get("lht_id") or "",
                     s.get("je_palette") or ""]
            for c, w in enumerate(werte):
                it = _zelle(w, c in (0, 2, 4, 6))
                if c == 6 and s.get("plan_text"):
                    it.setToolTip(s["plan_text"])
                self.teile.setItem(r, c, it)
            sb = QSpinBox()
            sb.setRange(0, 100000)
            sb.setSpecialValueText("automatisch")
            sb.setValue(int((self.d.get("max_je") or {}).get(str(s.get("id"))) or 0))
            sb.setEnabled(not self.db.nur_lesen and s.get("id") is not None)
            sb.valueChanged.connect(lambda n, pid=s.get("id"): self.max_je_setzen(pid, n))
            self.teile.setCellWidget(r, 7, sb)
        self.teile.resizeColumnsToContents()
        self.teile.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        n = palettenschein.anzahl(self.d, e)
        self.nachdruck_nr.setMaximum(max(1, n or 1))
        sh = ""
        if man and self.stueck_text.text().strip():
            r = palettenschein.stueck_liste(self.stueck_text.text(), self.anzahl.value())
            if r.get("fehler"):
                sh = "Bitte nur Zahlen eingeben, z. B. 100 oder 100, 100, 50 oder 3x80, 10"
            elif r["summe"] != e["gesamt_stueck"] and (r["einzeln"] or r["anzahl"] == self.anzahl.value()):
                sh = f"Summe {r['summe']} Stück ≠ Auftragsstückzahl {e['gesamt_stueck']}"
            else:
                sh = f"Summe {r['summe']} Stück"
        self.stueck_hinweis.setText(sh)
        stufe = palettenschein.hinweis_stufe(self.hinweis.toPlainText())
        self.hinweis_info.setText(f"{len(self.hinweis.toPlainText())} Zeichen · {HINWEIS_TEXT[stufe]}"
                                  if stufe != "leer" else "")
        datum = self.termin.date().toPython() if self.mit_termin.isChecked() else None
        fh = feiertage.hinweis(datum, self.land)
        self.termin_hinweis.setText(f"Achtung: Lieferdatum fällt auf {fh}" if fh else "")
        self.stand.setText(("Gedruckt am " + datetime.date.fromisoformat(self.d["gedruckt_am"]).strftime("%d.%m.%Y")
                            if self.d.get("gedruckt_am") else "Noch nicht gedruckt") + " · automatisch gespeichert")
        self._laden = False

    # ------------------------------------------------ Ändern
    def _neu_rechnen(self):
        self.z = palettenschein.zusammenstellen(self.db, self.id, self.d)

    def speichern(self, *_):
        if self._laden or self.db.nur_lesen:
            return
        self.d.update(paletten_auto=self.auto.isChecked(), paletten=self.anzahl.value() if self.hand.isChecked()
                      else self.d.get("paletten"), unbekannt=self.unbekannt.isChecked(),
                      stueck_text=self.stueck_text.text().strip(),
                      arbeiten=[k for k, cb in self.haken.items() if cb.isChecked()],
                      hinweis=self.hinweis.toPlainText())
        self.db.palettenschein_speichern(self.id, self.d)
        self.anzeigen()

    def max_je_setzen(self, pid, n):
        if self._laden or self.db.nur_lesen:
            return
        m = dict(self.d.get("max_je") or {})
        if n:
            m[str(pid)] = int(n)
        else:
            m.pop(str(pid), None)
        self.d["max_je"] = m
        self.db.palettenschein_speichern(self.id, self.d)
        self._neu_rechnen()
        self.anzeigen()

    def status_geaendert(self, status, an):
        if self._laden or self.db.nur_lesen:
            return
        palettenschein.status_setzen(self.d, status, an)
        self.db.palettenschein_speichern(self.id, self.d)
        self.anzeigen()

    def _auftrag_speichern(self, *_):
        if self._laden or self.db.nur_lesen:
            return
        termin = self.termin.date().toPython().isoformat() if self.mit_termin.isChecked() else None
        self.db.auftrag_setzen(self.id, self.bestellnr.text(), termin)
        self.anzeigen()

    def termin_setzen(self, arbeitstage):
        heute = datetime.date.today()
        d = feiertage.arbeitstage_spaeter(heute, arbeitstage, self.land) if arbeitstage else heute
        self.mit_termin.setChecked(True)
        self.termin.setDate(QDate(d))

    def vorschlag(self):
        gewaehlt = set(palettenschein.vorschlag_arbeiten(self.z["positionen"], self.db.tabellen(), self.z["gruppen"]))
        self._haken_setzen(lambda k: k in gewaehlt)

    def alle(self, an):
        self._haken_setzen(lambda k: an)

    def _haken_setzen(self, an):
        self._laden = True
        for k, cb in self.haken.items():
            cb.setChecked(an(k))
        self._laden = False
        self.speichern()

    def verteilen(self):
        try:
            text = palettenschein.verteilen(self.z["packliste"]["gesamt_stueck"], self.anzahl.value())
        except ValueError as e:
            if not self.f.stumm:
                QMessageBox.information(self, "Verteilen", str(e) + " Bitte „Stück pro Palette“ von Hand eintragen.")
            return
        self.stueck_text.setText(text)

    def drucken(self, nur=None):
        pfad = scheine_drucken(self.f, [self.id], nur=nur)
        if pfad:
            self.d = self.db.palettenschein(self.id)
            self.z["schein"] = self.d
            self.anzeigen()
        return pfad


def oeffnen(fenster, angebot_id, parent=None):
    """Fenster zeigen (im Selbsttest nicht modal). Ergebnis: Dialog."""
    d = PalettenscheinDialog(fenster, angebot_id, parent)
    if fenster.stumm:
        d.show()
    else:
        d.exec()
    if hasattr(fenster, "versand"):
        fenster.versand.neu_laden()
    return d
