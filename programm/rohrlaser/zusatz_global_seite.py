"""Reiter „Zusatzarbeiten“ im Angebot (Master-Auftrag Zusatzarbeiten flexibel, Patrick 23.11.2026).

Oben die allgemeinen Zusatzarbeiten für das ganze Angebot (zusatz_global.py) mit Bezeichnung, Menge, Einheit,
Preis je Einheit (Verkaufspreis), Gesamt, Beschreibung und den internen Werten Kosten und Zeit je Einheit. Darunter
die Zusatzarbeiten je Position (aus der Kalkulation, nur zur Übersicht; ändern über „Position bearbeiten …“ wie
bisher), eine Warnung bei möglichen Doppelberechnungen, die Darstellung im Kundenangebot und die Summen (Positionen,
Zusatzarbeiten, netto, MwSt, brutto, interne Kosten, Deckungsbeitrag).

Jede Änderung wird sofort im Angebot gespeichert (eine Schreibtransaktion je Änderung, Abgleich über „geändert am“)
und die Kalkulation neu gerechnet."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import rechnen, zusatz_global as zg
from .stammdaten import zahl_als_text, zahl_aus_text
from .stil import GELB_FLAECHE, GELB_TEXT

SPALTEN = (("Bezeichnung", 190), ("Menge", 60), ("Einheit", 90), ("Preis/Einheit [€]", 110), ("Gesamt [€]", 90),
           ("Beschreibung (Kundenangebot)", 200), ("Kosten/Einheit intern [€]", 140),
           ("Zeit/Einheit intern [min]", 140), ("Grundlage bei %", 160))
NAME, MENGE, EINHEIT, PREIS, GESAMT, TEXT, KOSTEN, ZEIT, BASIS = range(len(SPALTEN))
POS_SPALTEN = ("Pos.", "Leistung", "Menge je Teil", "Preis je Einheit [€]", "€ je Teil", "Preisart", "Position [€]")


def _z(w, st=2):
    return zahl_als_text(round(float(w or 0), st), st)


def _zahl(t):
    t = (t or "").strip()
    return zahl_aus_text(t) if t else None


class UebertragenDialog(QDialog):
    """Allgemeine Zusatzarbeit einer oder mehreren Positionen zuordnen: Positionen anhaken, Menge je Teil."""

    def __init__(self, parent, eintrag, positionen):
        super().__init__(parent)
        self.setWindowTitle(f"„{eintrag['name']}“ auf Positionen übertragen")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Positionen wählen. Die Leistung wird dort mit dem Verkaufspreis je Einheit "
                             f"({_z(eintrag.get('preis'))} € je {eintrag.get('einheit')}) und dem Haken "
                             "„Preis = Verkauf“ eingetragen und mit der Stückzahl der Position gerechnet."))
        self.liste = QListWidget()
        for i, p in enumerate(positionen):
            if not p:
                continue
            it = QListWidgetItem(f"Pos. {p.get('pos') or i + 1}  {p.get('artikel') or ''}  {p.get('bezeichnung') or ''}"
                                 f"  ({_z(p.get('stueck'), 0)} Stk)")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            it.setData(Qt.UserRole, i)
            self.liste.addItem(it)
        lay.addWidget(self.liste, 1)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel(f"Menge je Teil [{eintrag.get('einheit')}]:"))
        self.menge = QDoubleSpinBox()
        self.menge.setDecimals(3)
        self.menge.setRange(0, 1e6)
        self.menge.setValue(1.0)
        zeile.addWidget(self.menge)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.entfernen = QCheckBox("Danach aus den allgemeinen Zusatzarbeiten entfernen (nicht doppelt berechnen)")
        self.entfernen.setChecked(True)
        lay.addWidget(self.entfernen)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def gewaehlt(self):
        return [self.liste.item(r).data(Qt.UserRole) for r in range(self.liste.count())
                if self.liste.item(r).checkState() == Qt.Checked]


class ZusatzGlobalSeite(QWidget):
    def __init__(self, seite):
        super().__init__()
        self.s = seite
        self._laden = False
        self.eintraege = []
        lay = QVBoxLayout(self)
        titel = QLabel("<b>Allgemeine Zusatzarbeiten</b> – gelten für das ganze Angebot und stehen im Kundenangebot "
                       "als eigene Zeilen unter den Positionen. Preis je Einheit = Verkaufspreis netto.")
        titel.setWordWrap(True)
        lay.addWidget(titel)
        leiste = QHBoxLayout()
        self.katalog = QComboBox()
        self.katalog.setMinimumWidth(170)
        self.katalog.setToolTip("Zusatzarbeit aus Einstellungen → Zusatzarbeiten (Standardpreis wird vorgeschlagen)")
        self.aus_katalog = QPushButton("＋ Aus Verwaltung")
        self.aus_katalog.clicked.connect(lambda: self.hinzufuegen_katalog(self.katalog.currentText()))
        self.frei = QPushButton("＋ Frei")
        self.frei.setToolTip("Freie Zusatzarbeit mit eigener Bezeichnung und eigenem Preis")
        self.frei.clicked.connect(lambda: self.hinzufuegen("Zusatzarbeit", 1.0, "Stück", 0.0))
        self.pauschal = QPushButton("＋ Pauschale")
        self.pauschal.clicked.connect(lambda: self.hinzufuegen("Verpackung", 1.0, zg.PAUSCHAL, 0.0))
        self.prozent = QPushButton("＋ Zuschlag %")
        self.prozent.clicked.connect(lambda: self.hinzufuegen("Zuschlag", 0.0, zg.PROZENT, 0.0))
        self.aus_katalog.setToolTip("Gewählte Zusatzarbeit der Verwaltung hinzufügen (Standardpreis wird vorgeschlagen)")
        self.entfernen = QPushButton("Entfernen")
        self.entfernen.clicked.connect(lambda: self.entfernen_markierte())
        self.standard = QPushButton("Standardpreis")
        self.standard.setToolTip("Preis, Kosten und Zeit der markierten Einträge neu aus der Verwaltung holen")
        self.standard.clicked.connect(lambda: self.standard_uebernehmen())
        self.uebertragen = QPushButton("Auf Positionen …")
        self.uebertragen.setToolTip("Markierte Zusatzarbeit einer oder mehreren Positionen zuordnen")
        self.uebertragen.clicked.connect(lambda: self.auf_positionen())
        for w in (self.katalog, self.aus_katalog, self.frei, self.pauschal, self.prozent, self.entfernen,
                  self.standard, self.uebertragen):
            leiste.addWidget(w)
        leiste.addStretch(1)
        lay.addLayout(leiste)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels([t for t, _ in SPALTEN])
        for i, (_, b) in enumerate(SPALTEN):
            self.tabelle.setColumnWidth(i, b)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        self.tabelle.itemChanged.connect(self._geaendert)
        lay.addWidget(self.tabelle, 2)
        self.warnung = QLabel()
        self.warnung.setWordWrap(True)
        self.warnung.setStyleSheet(f"background: {GELB_FLAECHE}; color: {GELB_TEXT}; padding: 4px;")
        self.warnung.hide()
        lay.addWidget(self.warnung)
        lay.addWidget(QLabel("<b>Zusatzarbeiten je Position</b> – ändern über die Position (Rechtsklick → "
                             "Zusatzarbeiten …), Haken „Preis = Verkauf“ für feste Einheitspreise."))
        self.pos_tabelle = QTableWidget(0, len(POS_SPALTEN))
        self.pos_tabelle.setHorizontalHeaderLabels(POS_SPALTEN)
        self.pos_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pos_tabelle.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.pos_tabelle.verticalHeader().setDefaultSectionSize(22)
        lay.addWidget(self.pos_tabelle, 2)
        unten = QHBoxLayout()
        unten.addWidget(QLabel("Darstellung im Kundenangebot:"))
        self.darstellung = QComboBox()
        self.darstellung.addItems(zg.DARSTELLUNGEN)
        self.darstellung.setToolTip("zusammengefasst: „inkl. …“ im Positionstext (wie bisher) · detailliert: "
                                    "Aufstellung je Position mit Menge, Einheitspreis und Gesamt · nur Gesamtpreis: "
                                    "keine Zusatzarbeiten im Text, allgemeine als eine Summenzeile. Die interne "
                                    "Kalkulation bleibt immer vollständig.")
        self.darstellung.currentTextChanged.connect(self._darstellung_gewechselt)
        unten.addWidget(self.darstellung)
        unten.addStretch(1)
        lay.addLayout(unten)
        self.summen = QLabel()
        self.summen.setWordWrap(True)
        self.summen.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.summen)

    # ------------------------------------------------------------------ Anzeige
    def _lesen(self):
        return bool(self.s.fremd() or self.s.db.nur_lesen)

    def setzen(self, summen):
        """Nach jedem Rechnen des Angebots: Tabellen, Warnung und Summen füllen."""
        self._laden = True
        try:
            self._katalog_fuellen()
            self.eintraege = zg.liste(self.s.kopf)
            self.tabelle.setRowCount(0)         # keine Zellen-Widgets älterer Zeilen behalten
            basis = rechnen._n(summen.get("verkauf_positionen", summen.get("verkauf")))
            gerechnet = {r.get("id"): r for r in zg.zeilen(self.eintraege, basis)}
            self.tabelle.setRowCount(len(self.eintraege))
            for r, e in enumerate(self.eintraege):
                self._zeile(r, e, gerechnet.get(e.get("id")) or {})
            self.darstellung.setCurrentText(zg.darstellung(self.s.kopf, self.s.einst))
            lesen = self._lesen()
            for w in (self.aus_katalog, self.frei, self.pauschal, self.prozent, self.entfernen, self.standard,
                      self.uebertragen, self.darstellung, self.katalog):
                w.setEnabled(not lesen)
            self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers if lesen else
                                         QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                         | QAbstractItemView.AnyKeyPressed | QAbstractItemView.SelectedClicked)
            self._positionen_fuellen()
            t = zg.ueberschneidung_text(zg.ueberschneidungen(self.s.kopf, self.s.positionen))
            self.warnung.setText("⚠ " + t if t else "")
            self.warnung.setVisible(bool(t))
            self._summen_setzen(summen)
        finally:
            self._laden = False

    def _katalog_fuellen(self):
        alt = self.katalog.currentText()
        namen = sorted(z["name"] for z in self.s.tabellen.get("zusatzarbeiten") or ()
                       if z.get("name") and z.get("aktiv") != "nein" and z.get("art") != "s/Stück")
        if [self.katalog.itemText(i) for i in range(self.katalog.count())] != namen:
            self.katalog.blockSignals(True)
            self.katalog.clear()
            self.katalog.addItems(namen)
            if alt in namen:
                self.katalog.setCurrentText(alt)
            self.katalog.blockSignals(False)

    def _item(self, text, bearbeitbar=True, rechts=False):
        it = QTableWidgetItem(text)
        if not bearbeitbar:
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        if rechts:
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return it

    def _zeile(self, r, e, g):
        prozent = e.get("einheit") == zg.PROZENT
        self.tabelle.setItem(r, NAME, self._item(e.get("name") or ""))
        self.tabelle.setItem(r, MENGE, self._item(zahl_als_text(e.get("menge"), tausender=False), rechts=True))
        cb = QComboBox()
        cb.addItems(zg.EINHEITEN)
        cb.setCurrentText(e.get("einheit") or "Stück")
        cb.setEnabled(not self._lesen())
        cb.currentTextChanged.connect(lambda t, r=r: self._einheit(r, t))
        self.tabelle.setCellWidget(r, EINHEIT, cb)
        self.tabelle.setItem(r, PREIS, self._item("auto" if prozent else zahl_als_text(e.get("preis"), 2, tausender=False),
                                                  not prozent, True))
        self.tabelle.setItem(r, GESAMT, self._item(_z(g.get("gesamt")), False, True))
        self.tabelle.setItem(r, TEXT, self._item(e.get("beschreibung") or ""))
        self.tabelle.setItem(r, KOSTEN, self._item("" if e.get("kosten") is None else
                                                   zahl_als_text(e["kosten"], 2, tausender=False), rechts=True))
        self.tabelle.setItem(r, ZEIT, self._item("" if e.get("zeit_min") is None else
                                                 zahl_als_text(e["zeit_min"], tausender=False), rechts=True))
        if prozent:
            b = QComboBox()
            b.addItems(zg.BASIS)
            b.setCurrentText(e.get("basis") or zg.BASIS[0])
            b.setEnabled(not self._lesen())
            b.currentTextChanged.connect(lambda t, r=r: self._feld(r, "basis", t))
            self.tabelle.setCellWidget(r, BASIS, b)
        else:
            self.tabelle.removeCellWidget(r, BASIS)
            self.tabelle.setItem(r, BASIS, self._item("", False))
        if e.get("stand"):
            st = e["stand"]
            self.tabelle.item(r, NAME).setToolTip(
                f"Aus der Verwaltung „{e.get('katalog')}“ am {st.get('datum')}: Standardpreis {_z(st.get('preis'))} € "
                f"(Kosten {_z(st.get('kosten'))} €). Spätere Änderungen der Verwaltung ändern dieses Angebot nicht.")

    def _positionen_fuellen(self):
        try:
            kz, _ = self.s._rechnung()
        except Exception:           # noqa: BLE001 – Anzeige darf nie scheitern
            kz = []
        zeilen = []
        for p, z in zip(self.s.positionen, kz or ()):
            for e in (z or {}).get("zusatzarbeiten") or ():
                if e.get("art") == "s/Stück":
                    continue
                c = rechnen._n(p.get("stueck"))
                zeilen.append((str(p.get("pos") or ""), e["name"] + (f" {e['text']}" if e.get("text") else ""),
                               f"{rechnen.zahl(e.get('menge'), 3)} {e.get('einheit') or ''}".strip(),
                               _z(e.get("preis")), _z(e.get("teil")),
                               "Verkauf fest" if e.get("vk") else "+ Zuschlag/Gewinn",
                               _z(rechnen._n(e.get("teil")) * c)))
        self.pos_tabelle.setRowCount(len(zeilen))
        for r, werte in enumerate(zeilen):
            for c, w in enumerate(werte):
                self.pos_tabelle.setItem(r, c, self._item(w, False, c in (2, 3, 4, 6)))

    def _summen_setzen(self, summen):
        mwst_satz = rechnen._n((self.s.einst or {}).get("mwst"))
        netto = rechnen._n(summen.get("verkauf"))
        glob = rechnen._n(summen.get("zusatz_global"))
        pos = rechnen._n(summen.get("zusatz")) + rechnen._n(summen.get("zusatz_vk"))
        kosten = rechnen._n(summen.get("zusatz_global_kosten"))
        teile = [f"Positionen {_z(netto - glob)} € (darin Zusatzarbeiten je Position {_z(pos)} €)",
                 f"Allgemeine Zusatzarbeiten {_z(glob)} €",
                 f"<b>Angebot netto {_z(netto)} €</b>",
                 f"MwSt {_z(100 * mwst_satz, 0)} % {_z(netto * mwst_satz)} €",
                 f"brutto {_z(netto * (1 + mwst_satz))} €"]
        if glob:
            teile.append(f"<span style='color:#5F6B7A'>intern: Kosten {_z(kosten)} €, Zeit "
                         f"{_z(summen.get('zusatz_global_zeit_min'), 0)} min, Deckungsbeitrag {_z(glob - kosten)} €</span>")
        self.summen.setText(" · ".join(teile))

    # ------------------------------------------------------------------ Ändern
    def speichern(self, eintraege=None, darstellung=None):
        """Allgemeine Zusatzarbeiten bzw. Darstellung im Angebot speichern und neu rechnen."""
        if self._lesen():
            return False
        if eintraege is not None:
            self.s.db.zusatz_setzen(self.s.id, zg.SCHLUESSEL, eintraege or None)
        if darstellung is not None:
            self.s.db.zusatz_setzen(self.s.id, zg.SCHLUESSEL_DARSTELLUNG,
                                    None if darstellung == zg.ZUSAMMEN else darstellung)
        self.s.neu_laden()
        return True

    def hinzufuegen(self, name, menge, einheit, preis, **w):
        e = zg.neu(name, menge, einheit, preis, **w)
        return self.speichern(zg.liste(self.s.kopf) + [e])

    def hinzufuegen_katalog(self, name):
        z = next((z for z in self.s.tabellen.get("zusatzarbeiten") or () if z.get("name") == name), None)
        if z is None:
            return False
        e = zg.vorschlag(z, self.s.einst, rechnen.stundensaetze(self.s.tabellen))
        return self.speichern(zg.liste(self.s.kopf) + [e])

    def _markiert(self):
        return sorted({i.row() for i in self.tabelle.selectedIndexes()})

    def entfernen_markierte(self, zeilen=None):
        zeilen = self._markiert() if zeilen is None else zeilen
        if not zeilen:
            return False
        liste = zg.liste(self.s.kopf)
        return self.speichern([e for r, e in enumerate(liste) if r not in set(zeilen)])

    def standard_uebernehmen(self, zeilen=None):
        zeilen = self._markiert() if zeilen is None else zeilen
        liste = zg.liste(self.s.kopf)
        katalog = {z.get("name"): z for z in self.s.tabellen.get("zusatzarbeiten") or ()}
        n = 0
        for r in zeilen:
            e = liste[r] if r < len(liste) else None
            z = katalog.get((e or {}).get("katalog") or (e or {}).get("name"))
            if not e or z is None:
                continue
            v = zg.vorschlag(z, self.s.einst, rechnen.stundensaetze(self.s.tabellen))
            e.update(preis=v["preis"], kosten=v["kosten"], zeit_min=v["zeit_min"], katalog=v["katalog"],
                     stand=v["stand"])
            n += 1
        return self.speichern(liste) if n else False

    def _feld(self, r, feld, wert):
        if self._laden:
            return
        liste = zg.liste(self.s.kopf)
        if r >= len(liste):
            return
        liste[r][feld] = wert
        if feld == "einheit" and wert == zg.PROZENT:
            liste[r].setdefault("basis", zg.BASIS[0])
        self.speichern(liste)

    def _einheit(self, r, t):
        self._feld(r, "einheit", t)

    def _geaendert(self, it):
        if self._laden:
            return
        r, c = it.row(), it.column()
        feld = {NAME: "name", MENGE: "menge", PREIS: "preis", TEXT: "beschreibung", KOSTEN: "kosten",
                ZEIT: "zeit_min"}.get(c)
        if feld is None:
            return
        text = it.text()
        try:
            if feld in ("name", "beschreibung"):
                wert = text.strip()
                if feld == "name" and not wert:
                    raise ValueError("Die Bezeichnung darf nicht leer sein.")
            else:
                wert = _zahl(text)
                if wert is not None and wert < 0:
                    raise ValueError("Negative Werte sind nicht zulässig.")
                if feld in ("menge", "preis") and wert is None:
                    wert = 0.0
        except ValueError as ex:
            self.s.f.meldung(f"Zusatzarbeiten: {ex}", fehler=True)
            self.s.neu_laden()
            return
        self._feld(r, feld, wert)

    def _darstellung_gewechselt(self, t):
        if not self._laden:
            self.speichern(darstellung=t)

    def auf_positionen(self, zeile=None, positionen=None, menge_je_teil=None, entfernen=True):
        """Markierte allgemeine Zusatzarbeit auf Positionen übertragen (Dialog bzw. Werte für Tests)."""
        if self._lesen():
            return False
        liste = zg.liste(self.s.kopf)
        zeile = (self._markiert() or [None])[0] if zeile is None else zeile
        if zeile is None or zeile >= len(liste):
            self.s.f.meldung("Bitte zuerst eine allgemeine Zusatzarbeit markieren.", fehler=True)
            return False
        e = liste[zeile]
        if e.get("einheit") == zg.PROZENT:
            self.s.f.meldung("Ein prozentualer Zuschlag gilt für das ganze Angebot.", fehler=True)
            return False
        if positionen is None:
            d = UebertragenDialog(self, e, self.s.positionen)
            if d.exec() != QDialog.Accepted:
                return False
            positionen, menge_je_teil, entfernen = d.gewaehlt(), d.menge.value(), d.entfernen.isChecked()
        katalog = next((z for z in self.s.tabellen.get("zusatzarbeiten") or ()
                        if z.get("name") == (e.get("katalog") or e.get("name"))), None)
        neu = zg.an_position(e, katalog, menge_je_teil)
        import json
        for i in positionen:
            p = self.s.positionen[i]
            alt = [x for x in rechnen.zusatz_liste(p) if x.get("name") != neu["name"]]
            self.s.db.position_aendern(p["id"], "zusatz", json.dumps(alt + [dict(neu)], ensure_ascii=False))
        if entfernen:
            self.s.db.zusatz_setzen(self.s.id, zg.SCHLUESSEL, [x for r, x in enumerate(liste) if r != zeile] or None)
        self.s.f.meldung(f"„{e['name']}“ auf {len(positionen)} Position(en) übertragen.")
        self.s.neu_laden()
        return True
