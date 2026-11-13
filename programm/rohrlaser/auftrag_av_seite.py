"""Reiter „Arbeitsvorbereitung“ der Seite Aufträge (Plan Auftragsworkflow, Paket 3). Regeln in auftrag_av.py.

Oben die Prüfliste mit Ampel (Zeichnungen, Material, Zukauf, Fertigungsinformationen, Arbeitsgänge) und die Knöpfe
Material, Als geklärt bestätigen und Produktionsbereit melden. Darunter die Arbeitsgänge der gewählten Position:
an-/abwählen (Häkchen), verschieben, ergänzen, entfernen, Maschine, Mitarbeiter, Sollzeit, Sollmenge, geplanter Start
und Ende, Bemerkung. Jede Eingabe wird sofort gespeichert (Ereignis mit Historie).
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import auftraege as au, auftrag_av as av

AMPEL_FARBE = {av.GRUEN: "#1E8E3E", av.GELB: "#B7791F", av.ROT: "#B42318"}
AMPEL_GRUND = {av.GRUEN: "#E3F4E8", av.GELB: "#FFF6DB", av.ROT: "#FDECEA"}
PRUEF_SPALTEN = ("Ampel", "Prüfpunkt", "Stand", "Bestätigt")
AG_SPALTEN = ("Aktiv", "Arbeitsgang", "Maschine", "Mitarbeiter", "Sollzeit [min]", "Sollmenge", "Start geplant",
              "Ende geplant", "Bemerkung")
AG_FELD = (None, "name", "maschine", "mitarbeiter", "sollzeit", "sollmenge", "start", "ende", "bemerkung")


def _zahl(x):
    try:
        return f"{float(x):g}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.verticalHeader().setVisible(False)
    kopf = t.horizontalHeader()
    kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
    kopf.setStretchLastSection(True)
    return t


class AvReiter(QWidget):
    def __init__(self, seite):
        super().__init__()
        self.seite, self.db = seite, seite.db
        self.a = None
        self.liste, self.vorschlag = [], False
        self.gesamt = QLabel()
        self.gesamt.setTextFormat(Qt.RichText)
        self.pruef = _tabelle(PRUEF_SPALTEN)
        self.pruef.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pruef.setMaximumHeight(190)
        self.pruef.doubleClicked.connect(lambda _: self.bestaetigen())
        self.pruef.setToolTip("Doppelklick: Punkt als geklärt bestätigen (bzw. Material setzen)")
        pk = QHBoxLayout()
        self.knopf = {}
        for name, text, ziel, tip in (
                ("material", "Material …", self.material_setzen,
                 "Material verfügbar, bestellt oder fehlt (fehlt setzt den Status „Material fehlt“)"),
                ("klaeren", "Als geklärt bestätigen …", self.bestaetigen,
                 "Gewählten Prüfpunkt von Hand als geklärt bestätigen (bei Lücken mit Bemerkung)"),
                ("frei", "Produktionsbereit melden …", self.freigeben,
                 "Auftrag für die Produktion freigeben; nicht alles grün = Sonderfreigabe mit Grund")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            if name == "frei":
                b.setObjectName("primaer")
            self.knopf[name] = b
            pk.addWidget(b)
        pk.addStretch(1)
        self.position = QComboBox()
        self.position.setToolTip("Position, deren Arbeitsgänge unten stehen")
        self.position.currentIndexChanged.connect(self._position_zeigen)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.ag = _tabelle(AG_SPALTEN)
        self.ag.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                | QAbstractItemView.AnyKeyPressed)
        self.ag.itemChanged.connect(self._geaendert)
        leiste = QHBoxLayout()
        leiste.addWidget(QLabel("Arbeitsgänge der Position"))
        leiste.addWidget(self.position, 1)
        ak = QHBoxLayout()
        for name, text, ziel, tip in (
                ("hoch", "▲ Nach oben", lambda: self.verschieben(-1), "Gewählten Arbeitsgang früher"),
                ("runter", "▼ Nach unten", lambda: self.verschieben(1), "Gewählten Arbeitsgang später"),
                ("neu", "Schritt hinzufügen …", self.hinzufuegen, "Weiteren Arbeitsgang einfügen"),
                ("weg", "Schritt entfernen", self.entfernen, "Gewählten Arbeitsgang aus der Position nehmen"),
                ("vorschlag", "Vorschläge übernehmen", self.vorschlaege_uebernehmen,
                 "Für alle Positionen ohne festgelegte Arbeitsgänge den Vorschlag aus der Kalkulation festlegen"),
                ("alle", "Auswahl für alle Positionen", self.fuer_alle,
                 "An-/Abwahl und Reihenfolge dieser Position auf alle anderen Positionen übertragen")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            self.knopf[name] = b
            ak.addWidget(b)
        ak.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.gesamt)
        lay.addWidget(self.pruef)
        lay.addLayout(pk)
        lay.addLayout(leiste)
        lay.addWidget(self.hinweis)
        lay.addWidget(self.ag, 1)
        lay.addLayout(ak)

    # ------------------------------------------------ Anzeige
    def zeigen(self, a):
        self.a = a
        for b in self.knopf.values():
            b.setEnabled(a is not None)
        if a is None:
            self.gesamt.setText("")
            self.pruef.setRowCount(0)
            self.position.blockSignals(True)
            self.position.clear()
            self.position.blockSignals(False)
            self.ag.setRowCount(0)
            return
        liste = av.pruefliste(self.db, a)
        g = av.ampel(liste)
        fr = a["kopf"].get("_freigabe") or {}
        text = (f"<span style='color:{AMPEL_FARBE[g]}; font-size:14pt'>●</span> <b>Arbeitsvorbereitung</b> · "
                f"{sum(1 for x in liste if x['ampel'] == av.GRUEN)} von {len(liste)} Punkten grün")
        if fr:
            text += (f" · freigegeben von {fr.get('wer') or '?'}"
                     + (f" (Sonderfreigabe: {fr.get('grund')})" if fr.get("sonder") else ""))
        self.gesamt.setText(text)
        self.pruef.setRowCount(len(liste))
        for r, x in enumerate(liste):
            h = x["hand"]
            werte = ("●", x["titel"], x["text"],
                     f"{h.get('wert')} · {h.get('wer') or ''}".strip(" ·") if h.get("wert") not in (None, av.ZURUECK)
                     else "")
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                it.setBackground(QColor(AMPEL_GRUND[x["ampel"]]))
                if c == 0:
                    it.setForeground(QColor(AMPEL_FARBE[x["ampel"]]))
                    it.setTextAlignment(Qt.AlignCenter)
                it.setData(Qt.UserRole, x["punkt"])
                self.pruef.setItem(r, c, it)
        frei = a["status"] in (au.NEU, au.AV, au.MATERIAL_FEHLT)
        self.knopf["frei"].setEnabled(frei)
        alt = self.position.currentData()
        self.position.blockSignals(True)
        self.position.clear()
        for p in a["positionen"]:
            fest = "" if p.get("arbeitsgaenge") else " (Vorschlag)"
            self.position.addItem(f"Pos. {p['nr']} {p.get('artikel') or ''} {p.get('bezeichnung') or ''}".strip()
                                  + fest, p["uid"])
        self.position.setCurrentIndex(max(0, self.position.findData(alt)))
        self.position.blockSignals(False)
        self._position_zeigen()

    def _pos(self):
        if self.a is None:
            return None
        u = self.position.currentData()
        return next((p for p in self.a["positionen"] if p["uid"] == u), None)

    def _position_zeigen(self, *_):
        p = self._pos()
        self.ag.blockSignals(True)
        if p is None:
            self.liste, self.vorschlag = [], False
            self.ag.setRowCount(0)
            self.ag.blockSignals(False)
            return
        self.liste, self.vorschlag = av.arbeitsgaenge(self.db, self.a, p)
        self.hinweis.setText("Vorschlag aus der Kalkulation, noch nicht festgelegt. Die erste Änderung oder "
                             "„Vorschläge übernehmen“ legt ihn fest." if self.vorschlag else
                             "Häkchen = Arbeitsgang wird gemacht. Doppelklick auf eine Zelle zum Ändern; "
                             "alles wird sofort gespeichert.")
        self.hinweis.setStyleSheet("background:#FFF6DB; padding:4px; border-radius:4px;" if self.vorschlag else "")
        self.ag.setRowCount(len(self.liste))
        for r, x in enumerate(self.liste):
            haken = QTableWidgetItem()
            haken.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            haken.setCheckState(Qt.Checked if x.get("aktiv") else Qt.Unchecked)
            self.ag.setItem(r, 0, haken)
            for c, f in enumerate(AG_FELD[1:], start=1):
                w = x.get(f)
                it = QTableWidgetItem(_zahl(w) if f in ("sollzeit", "sollmenge") else str(w or ""))
                if f in ("sollzeit", "sollmenge"):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if not x.get("aktiv"):
                    it.setForeground(QColor("#8A94A3"))
                self.ag.setItem(r, c, it)
        self.ag.blockSignals(False)

    # ------------------------------------------------ Speichern
    def _aus_tabelle(self):
        out = []
        for r, x in enumerate(self.liste):
            z = dict(x)
            z["aktiv"] = self.ag.item(r, 0).checkState() == Qt.Checked
            for c, f in enumerate(AG_FELD[1:], start=1):
                it = self.ag.item(r, c)
                z[f] = it.text() if it else ""
            out.append(z)
        return out

    def _speichern(self, liste, bemerkung=""):
        p = self._pos()
        if p is None:
            return False
        uid = self.a["uid"]
        try:
            r = av.setzen(self.db, uid, p["uid"], liste, bemerkung)
        except au.AuftragFehler as e:
            self.seite.f.meldung(str(e), fehler=True)
            self._position_zeigen()
            return False
        self.seite.neu_laden()
        return r

    def _geaendert(self, *_):
        return self._speichern(self._aus_tabelle())

    def aktiv_setzen(self, zeile, an=True):
        it = self.ag.item(zeile, 0)
        if it is None:
            return False
        liste = self._aus_tabelle()
        liste[zeile]["aktiv"] = bool(an)
        return self._speichern(liste)

    def feld_setzen(self, zeile, feld, wert):
        liste = self._aus_tabelle()
        if not 0 <= zeile < len(liste):
            return False
        liste[zeile][feld] = wert
        return self._speichern(liste)

    def verschieben(self, schritt, zeile=None):
        zeile = self.ag.currentRow() if zeile is None else zeile
        liste = self._aus_tabelle()
        ziel = zeile + schritt
        if not (0 <= zeile < len(liste) and 0 <= ziel < len(liste)):
            return False
        liste[zeile], liste[ziel] = liste[ziel], liste[zeile]
        r = self._speichern(liste)
        self.ag.selectRow(ziel)
        return r

    def hinzufuegen(self, name=None):
        p = self._pos()
        if p is None:
            return False
        if name is None:
            vorh = {x["name"] for x in self.liste}
            angebot = [s for s in av.schritte(self.db) if s not in vorh]
            name, ok = QInputDialog.getItem(self, "Schritt hinzufügen", "Arbeitsgang (aus der Vorlage oder eigener "
                                            "Name):", angebot or [""], 0, True)
            if not ok or not str(name).strip():
                return False
        liste = self._aus_tabelle()
        hinter = self.ag.currentRow()
        neu = dict(name=str(name).strip(), aktiv=True, sollmenge=p.get("menge"), sollzeit=0)
        liste.insert(hinter + 1 if 0 <= hinter < len(liste) else len(liste), neu)
        return self._speichern(liste, f"Schritt {neu['name']} ergänzt")

    def entfernen(self, zeile=None):
        zeile = self.ag.currentRow() if zeile is None else zeile
        liste = self._aus_tabelle()
        if not 0 <= zeile < len(liste):
            return False
        weg = liste.pop(zeile)
        return self._speichern(liste, f"Schritt {weg['name']} entfernt")

    def vorschlaege_uebernehmen(self):
        if self.a is None:
            return 0
        try:
            n = av.alle_uebernehmen(self.db, self.a["uid"])
        except au.AuftragFehler as e:
            self.seite.f.meldung(str(e), fehler=True)
            return 0
        self.seite.f.meldung(f"Arbeitsgänge für {n} Positionen aus der Kalkulation festgelegt.")
        self.seite.neu_laden()
        return n

    def fuer_alle(self):
        p = self._pos()
        if p is None:
            return 0
        try:
            if self.vorschlag:
                av.setzen(self.db, self.a["uid"], p["uid"], self._aus_tabelle())
            n = av.fuer_alle(self.db, self.a["uid"], p["uid"])
        except au.AuftragFehler as e:
            self.seite.f.meldung(str(e), fehler=True)
            return 0
        self.seite.f.meldung(f"Auswahl der Arbeitsgänge auf {n} weitere Positionen übertragen.")
        self.seite.neu_laden()
        return n

    # ------------------------------------------------ Prüfliste
    def _punkt(self):
        r = self.pruef.currentRow()
        it = self.pruef.item(r, 0) if r >= 0 else None
        return it.data(Qt.UserRole) if it else None

    def material_setzen(self, wert=None, bemerkung=None):
        if self.a is None:
            return False
        if wert is None:
            wert, ok = QInputDialog.getItem(self, "Material", "Material für den Auftrag:",
                                            list(av.MATERIAL_WERTE) + [av.ZURUECK], 0, False)
            if not ok:
                return False
            bemerkung, _ = QInputDialog.getText(self, "Material", "Bemerkung (z. B. Lieferant, Liefertermin):")
        return self._bestaetigen("material", wert, bemerkung or "")

    def bestaetigen(self, punkt=None, bemerkung=None, wert=av.OK):
        if self.a is None:
            return False
        punkt = punkt or self._punkt()
        if not punkt:
            self.seite.f.meldung("Bitte zuerst einen Prüfpunkt wählen.", fehler=True)
            return False
        if punkt == "material":
            return self.material_setzen()
        if punkt == "arbeitsgaenge":
            self.seite.f.meldung("Arbeitsgänge werden grün, wenn jede Position festgelegte Arbeitsgänge hat "
                                 "(„Vorschläge übernehmen“).", fehler=True)
            return False
        if bemerkung is None:
            bemerkung, ok = QInputDialog.getText(self, av.PUNKT_TITEL[punkt], "Als geklärt bestätigen. Bemerkung "
                                                 "(Pflicht, wenn das Programm Lücken sieht):")
            if not ok:
                return False
        return self._bestaetigen(punkt, wert, bemerkung)

    def _bestaetigen(self, punkt, wert, bemerkung):
        try:
            r = av.bestaetigen(self.db, self.a["uid"], punkt, wert, bemerkung)
        except au.AuftragFehler as e:
            self.seite.f.meldung(str(e), fehler=True)
            return False
        self.seite.neu_laden()
        return r

    def freigeben(self, grund=None):
        if self.a is None:
            return False
        offen = [x for x in av.pruefliste(self.db, self.a) if x["ampel"] != av.GRUEN]
        if grund is None:
            if offen:
                grund, ok = QInputDialog.getText(
                    self, "Sonderfreigabe", "Noch nicht grün:\n" + "\n".join(f"• {x['titel']}: {x['text']}"
                                                                            for x in offen)
                    + "\n\nTrotzdem produktionsbereit melden? Grund (steht in der Historie):")
                if not ok or not grund.strip():
                    return False
            else:
                grund = ""
        try:
            sonder = av.freigeben(self.db, self.a["uid"], grund)
        except au.AuftragFehler as e:
            self.seite.f.meldung(str(e), fehler=True)
            return False
        self.seite.f.meldung(f"Auftrag {self.a['nummer']} ist produktionsbereit"
                             + (" (Sonderfreigabe)." if sonder else "."))
        self.seite.neu_laden()
        return True
