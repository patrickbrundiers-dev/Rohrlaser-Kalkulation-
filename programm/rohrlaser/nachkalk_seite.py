"""Reiter 'Nachkalkulation' im Angebot: Ist-Werte nach dem Auftrag erfassen und mit der Kalkulation vergleichen."""
import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from . import baugruppe, reklamation, stil
from . import nachkalkulation as nk
from .spaltenbreite import AutoGroesse
from .stil import GRUEN, GRUEN_FLAECHE, ROT, ROT_FLAECHE
from .stammdaten import zahl_als_text, zahl_aus_text

VERGLEICH_SPALTEN = [("Kostenart", "text", None, 230), ("Einheit", "einheit", None, 60),
                     ("Menge Soll", "soll_menge", 2, 85), ("Menge Ist", "ist_menge", 2, 85),
                     ("Soll [€]", "soll", 2, 90), ("Ist [€]", "ist", 2, 90), ("Abweichung [€]", "abweichung", 2, 95),
                     ("Abweichung [%]", "prozent", 1, 90), ("Ist erfasst", "erfasst", None, 70)]
GRUPPEN_TITEL = ("Profil-ID", "Werkstoff-ID", "Stangenlänge [mm]", "Stangen Soll", "Stangen Ist",
                 "EK-Meterpreis Soll [€/m]", "EK-Meterpreis Ist [€/m]")
TEILE_TITEL = ("Pos.", "Ist [s/Teil]", "Soll [s/Teil]", "Profil-ID", "Schneiddaten")
EINGABE = {4: ("stangen", True), 6: ("meterpreis", False)}   # editierbare Spalten: (Schlüssel in ist, ganze Zahl)
# Schweißbaugruppen: Spalte -> (Feld in ist['baugruppen'][ID] oder None, Titel); Ist-Spalten und Grund editierbar
BG_SPALTEN = [(None, "Baugruppe")] + [x for n, titel, e, _ in nk.BG_FELDER
                                      for x in ((None, f"{titel} Soll [{e}]"), (n, f"{titel} Ist [{e}]"))] + [
    ("grund", "Abweichungsgrund"), (None, "Schweißen Soll [min/m Naht]"), (None, "Schweißen Ist [min/m Naht]")] + [
    x for n, titel, *_ in nk.BG_TEILE for x in ((None, f"{titel} Soll [h]"), (n, f"{titel} Ist [h]"))]


def _z(w, stellen=2):
    return zahl_als_text(w, stellen) if isinstance(w, (int, float)) and not isinstance(w, bool) else ""


class NachkalkulationSeite(QWidget):
    def __init__(self, seite):
        super().__init__()
        from .angebot_fenster import Liste, _breiten, _tabelle
        self.s = seite
        self._laden = False
        self.ist = {}
        self.stand = QLabel()
        self.stand.setWordWrap(True)

        # Ist-Werte
        eingabe = QGroupBox("Ist-Werte nach dem Auftrag (leer = wie kalkuliert)")
        el = QVBoxLayout(eingabe)
        self.gruppen = QTableWidget(0, len(GRUPPEN_TITEL))
        self.gruppen.setHorizontalHeaderLabels(GRUPPEN_TITEL)
        self.gruppen.verticalHeader().setDefaultSectionSize(22)
        for i, b in enumerate((110, 100, 115, 80, 80, 130, 130)):
            self.gruppen.setColumnWidth(i, b)
        self.gruppen.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                     | QAbstractItemView.AnyKeyPressed)
        self.gruppen.itemChanged.connect(self._stangen_geaendert)
        AutoGroesse(self.gruppen)
        text = QLabel("Verbrauchte Stangen und tatsächlicher EK-Meterpreis je Profil, Werkstoff und "
                      "Stangenlänge (Meterpreis leer = kalkulierter Meterpreis):")
        text.setWordWrap(True)          # sonst bestimmt die Zeile die Mindestbreite der ganzen Angebotsseite
        el.addWidget(text)
        el.addWidget(self.gruppen, 1)
        form = QFormLayout()
        self.felder = {}
        for name, titel, _ in nk.FELDER:
            w = QLineEdit()
            w.setClearButtonEnabled(True)
            w.editingFinished.connect(lambda name=name, w=w: self._feld_geaendert(name, w))
            self.felder[name] = w
            form.addRow(titel, w)
        self.bemerkung = QLineEdit()
        self.bemerkung.editingFinished.connect(self._bemerkung_geaendert)
        form.addRow("Bemerkung Nachkalkulation", self.bemerkung)
        el.addLayout(form)
        # Laufzeit je Teil von der Maschine (Vorschlag V3b): daraus lernen die Schneiddaten je Werkstoff und Wandstärke
        tt = QLabel("Laufzeit je Teil laut Maschine [s] (freiwillig): sind alle Teile eingetragen, ergibt sich die "
                    "Ist-Laserzeit daraus; jede Zeile wird ein Fall für die Kennwert-Vorschläge der Schneiddaten "
                    "(Datei → Kennwerte).")
        tt.setWordWrap(True)
        el.addWidget(tt)
        self.teile = QTableWidget(0, len(TEILE_TITEL))
        self.teile.setHorizontalHeaderLabels(TEILE_TITEL)
        self.teile.verticalHeader().setVisible(False)
        self.teile.verticalHeader().setDefaultSectionSize(22)
        self.teile.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                   | QAbstractItemView.AnyKeyPressed)
        self.teile.itemChanged.connect(self._teil_geaendert)
        AutoGroesse(self.teile)
        el.addWidget(self.teile)
        self.bg_rahmen = QGroupBox("Schweißbaugruppen (leer = wie kalkuliert)")
        bl = QVBoxLayout(self.bg_rahmen)
        hinweis = QLabel("Tatsächliche Zeiten und Kosten je Baugruppe für den ganzen Auftrag. Die Schweißzeit je Meter "
                         "Naht hilft, die Schweiß-Kennwerte zu prüfen; sie ändert keine Stammdaten.")
        hinweis.setWordWrap(True)
        bl.addWidget(hinweis)
        self.bg_tabelle = QTableWidget(0, len(BG_SPALTEN))
        self.bg_tabelle.setHorizontalHeaderLabels([t for _, t in BG_SPALTEN])
        self.bg_tabelle.verticalHeader().setDefaultSectionSize(22)
        self.bg_tabelle.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                        | QAbstractItemView.AnyKeyPressed)
        self.bg_tabelle.itemChanged.connect(self._bg_geaendert)
        AutoGroesse(self.bg_tabelle)
        bl.addWidget(self.bg_tabelle)
        el.addWidget(self.bg_rahmen)
        knoepfe = QHBoxLayout()
        for text, ziel in (("Rest wie geplant", self.rest_wie_geplant), ("Ist-Werte löschen", self.loeschen),
                           ("Nachkalkulation (PDF)", self.pdf), ("Auswertung aller Aufträge …", self.auswertung)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            knoepfe.addWidget(b)
            if text == "Rest wie geplant":
                b.setToolTip("Alle noch leeren Ist-Werte auf das Soll setzen; nur Abweichungen von Hand eintragen. "
                             "Eingetragene Werte bleiben.")
        knoepfe.addStretch(1)
        el.addLayout(knoepfe)

        # Vergleich
        self.vergleich = Liste(VERGLEICH_SPALTEN)
        ansicht = self.vergleich_ansicht = _tabelle(self.vergleich, sortieren=False)
        _breiten(ansicht, VERGLEICH_SPALTEN)
        self.ergebnis = QLabel()
        self.ergebnis.setWordWrap(True)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("<b>Soll (Kalkulation) gegen Ist</b> – Einzelkosten ohne Zuschläge und Gewinn"))
        rl.addWidget(ansicht, 1)
        rl.addWidget(self.ergebnis)
        teil = QSplitter(Qt.Horizontal)
        eingabe_rahmen = QScrollArea()      # rollt auf kleinen Bildschirmen, statt den Angebotskopf zu verdrängen
        eingabe_rahmen.setWidgetResizable(True)
        eingabe_rahmen.setFrameShape(QFrame.NoFrame)
        eingabe_rahmen.setWidget(eingabe)
        teil.addWidget(eingabe_rahmen)
        teil.addWidget(rechts)
        teil.setSizes([430, 870])
        lay = QVBoxLayout(self)
        lay.addWidget(self.stand)
        lay.addWidget(teil, 1)

    # -------------------------------------------------------------- Anzeige
    def neu_laden(self):
        s = self.s
        self.ist = dict(s.kopf.get("nachkalkulation") or {})
        rk = reklamation.kosten(s.db, s.id)      # Reklamationskosten immer aktuell (Plan 29.10.2026 2c)
        if rk is None:
            self.ist.pop("reklamation", None)
        else:
            self.ist["reklamation"] = rk
        self._laden = True
        if not s.ergebnis or not s.ergebnis.get("stangen"):
            self.stand.setText("<b style='color:#7A5A00'>Noch nicht optimiert: die Nachkalkulation vergleicht mit dem "
                               "Schnittplan und der Kalkulation. Bitte zuerst optimieren.</b>")
        elif s.stand_optimierung() != "aktuell":
            self.stand.setText("<b style='color:#B42318'>Optimierung VERALTET: das Soll passt nicht mehr zum Angebot. "
                               "Neu optimieren, bevor nachkalkuliert wird.</b>")
        else:
            am = self.ist.get("am")
            self.stand.setText("Nach dem Auftrag die tatsächlichen Werte eintragen (Stangen aus dem Lager, Laserzeit "
                               "der Maschine, Rechnungen für Verzinken usw.). Leere Felder zählen wie kalkuliert."
                               + (f" <i>Zuletzt geändert {datetime.datetime.fromisoformat(am):%d.%m.%Y %H:%M}.</i>"
                                  if am else ""))
        v = self._rechnen()
        self.gruppen.setRowCount(len(v["gruppen"]))
        # bis zu 5 Gruppen ohne Rollen sichtbar (sonst drückt das Formular die Tabelle auf eine Zeile zusammen)
        kopf = self.gruppen.horizontalHeader().sizeHint().height()
        leiste = self.gruppen.horizontalScrollBar().sizeHint().height()
        self.gruppen.setMinimumHeight(kopf + leiste + 4 + 22 * max(2, min(len(v["gruppen"]), 5)))
        for r, g in enumerate(v["gruppen"]):
            for c, w in enumerate((g["profil"], g["werkstoff"], _z(g["stange"], 0), _z(g["soll"], 0),
                                   "" if g["ist"] is None else _z(g["ist"], 0), _z(g["meterpreis"], 2),
                                   "" if g["meterpreis_ist"] is None else _z(g["meterpreis_ist"], 2))):
                it = QTableWidgetItem(w)
                it.setData(Qt.UserRole, g["schluessel"])
                if c == 6:
                    it.setToolTip(f"Leer = kalkulierter Meterpreis {_z(g['meterpreis'], 2)} €/m")
                if c not in EINGABE:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setBackground(QBrush(stil.farbe("#F2F2F2")))
                else:
                    it.setBackground(QBrush(stil.farbe("#FFF9E5")))
                if c >= 2:
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.gruppen.setItem(r, c, it)
        for name, _, stellen in nk.FELDER:
            w = self.ist.get(name)
            self.felder[name].setText(_z(w, stellen) if w is not None else "")
        self.bemerkung.setText(self.ist.get("bemerkung") or "")
        self._teile_zeigen()
        self._bg_zeigen(v)
        self._platzhalter(v)
        self._laden = False

    def _rechnen(self):
        s = self.s
        v = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, self.ist, kalk=s._rechnung())
        self.vergleich.setzen(v["zeilen"] + [v["summe"], v["erloes"], v["db"]])
        db = v["db"]
        farbe = "#1E6B34" if db["abweichung"] >= 0 else "#B42318"
        self.ergebnis.setText(
            f"Deckungsbeitrag Soll {_z(db['soll'])} € · Ist <b style='color:{farbe}'>{_z(db['ist'])} €</b> "
            f"(Abweichung {_z(db['abweichung'])} €). Einzelkosten Ist {_z(v['summe']['ist'])} € gegen Soll "
            f"{_z(v['summe']['soll'])} €. Herstellkosten laut Kalkulation (mit Zuschlägen) {_z(v['herstell'])} €.")
        return v

    def _bg_zeigen(self, v):
        s = self.s
        soll = {b["id"]: b for b in nk.baugruppen_soll(s.positionen, s._rechnung()[0])}
        info = v.get("baugruppen") or []
        self.bg_rahmen.setVisible(bool(info))
        self.bg_tabelle.setRowCount(len(info))
        ist_bg = self.ist.get("baugruppen") or {}
        vorlagen = {}
        for p in s.positionen:
            g = baugruppe.lesen(p.get("baugruppe")) if p.get("baugruppe") else None
            if g and g.get("vorlage"):
                vorlagen[g["id"]] = g["vorlage"]
        for r, b in enumerate(info):
            e, w = ist_bg.get(b["id"]) or {}, soll[b["id"]]["werte"]
            texte, urteil = [b["name"]], {}
            for n, _, einheit, st in nk.BG_FELDER:
                menge, betrag = w[n]
                sw = menge if einheit == "h" else betrag
                texte += [_z(sw, st), "" if e.get(n) is None else _z(e.get(n), st)]
                urteil[len(texte) - 1] = nk.bewertung(sw, e.get(n))
            texte += [b["grund"], _z(b["soll_min_m"], 2), _z(b["ist_min_m"], 2)]
            urteil[len(texte) - 1] = nk.bewertung(b["soll_min_m"], b["ist_min_m"])
            for n, *_ in nk.BG_TEILE:       # davon Rüsten, Positionieren, Verputzen (Lernen der Vorkalkulation)
                sw = (soll[b["id"]].get("teile") or {}).get(n)
                texte += [_z(sw, 2), "" if e.get(n) is None else _z(e.get(n), 2)]
                urteil[len(texte) - 1] = nk.bewertung(sw, e.get(n))
            verlauf = self._verlauf(vorlagen.get(b["id"]))
            for c, (feld, _) in enumerate(BG_SPALTEN):
                it = QTableWidgetItem(texte[c])
                it.setData(Qt.UserRole, b["id"])
                if c == 0 and verlauf:
                    it.setToolTip(verlauf)
                if feld is None:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setBackground(QBrush(stil.farbe("#F2F2F2")))
                else:
                    it.setBackground(QBrush(stil.farbe("#FFF9E5")))
                if c and feld != "grund":
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if urteil.get(c):                   # D5: ab 10 % Abweichung rot (teurer) bzw. grün (günstiger)
                    hoch = urteil[c] == "hoch"
                    it.setForeground(QBrush(stil.farbe(ROT if hoch else GRUEN)))
                    it.setBackground(QBrush(stil.farbe(ROT_FLAECHE if hoch else GRUEN_FLAECHE)))
                    it.setToolTip(f"Ist {'über' if hoch else 'unter'} Soll um mindestens "
                                  f"{nk.ABWEICHUNG_GRENZE:.0%}".replace("%", " %"))
                self.bg_tabelle.setItem(r, c, it)
        self.bg_tabelle.resizeColumnsToContents()

    def _verlauf(self, vorlage):
        """Tooltip: Schweißzeit Ist ÷ Soll der bisherigen Aufträge aus derselben Vorlage (D5), leer ohne Vorlage."""
        if not vorlage:
            return ""
        from . import kennwerte
        zeilen = [f"{v['angebot']} ({str(v['datum'])[:10]}): Ist ÷ Soll {_z(v['faktor'], 2)}"
                  for v in kennwerte.verlauf_vorlage(self.s.db, vorlage) if v["faktor"] is not None]
        return (f"Vorlage {vorlage}: Schweißzeit bisher\n" + "\n".join(zeilen[-10:])) if zeilen else \
            f"Vorlage {vorlage}: noch keine nachkalkulierten Aufträge"

    def _bg_geaendert(self, it):
        feld = BG_SPALTEN[it.column()][0]
        if self._laden or feld is None:
            return
        if feld == "grund":
            wert = it.text().strip() or None
        else:
            try:
                wert = self._zahl(it.text())
            except ValueError as e:
                self.s.f.meldung(str(e), fehler=True)
                self.neu_laden()
                return
        e = self.ist.setdefault("baugruppen", {}).setdefault(it.data(Qt.UserRole), {})
        if e.get(feld) == wert:
            return
        e[feld] = wert
        self._speichern()
        self.neu_laden()

    def setzen_baugruppe(self, bg_id, **werte):
        """Ist-Werte einer Schweißbaugruppe ohne Oberfläche setzen (Tests, Bildschirmfotos)."""
        self.ist.setdefault("baugruppen", {}).setdefault(bg_id, {}).update(werte)
        self._speichern()
        self.neu_laden()

    def _platzhalter(self, v):
        z = {x["text"]: x for x in v["zeilen"]}
        soll = {"laser_h": (v["zeilen"][1]["soll_menge"], 2), "ruest_min": (v["zeilen"][2]["soll_menge"], 0),
                "zusatz": (v["zeilen"][3]["soll"], 2), "zukauf": (v["zeilen"][4]["soll"], 2), "sonstiges": (0, 2),
                "fracht": (z["Fracht"]["soll"], 2), "ausschuss": (0, 2), "ausschuss_stk": (0, 0),
                "erloes": (v["erloes"]["soll"], 2)}
        for name, (w, st) in soll.items():
            self.felder[name].setPlaceholderText(f"leer = Soll {_z(w, st)}")

    # -------------------------------------------------------------- Speichern
    def _speichern(self):
        self.ist["am"] = datetime.datetime.now().isoformat(timespec="seconds")
        if not nk.erfasst(self.ist) and not self.ist.get("bemerkung"):
            self.ist = {}
        elif self.s.ergebnis and self.s.ergebnis.get("stangen"):
            # Soll und Ist festhalten (Auswertung und Kennwert-Vorschläge über alle Aufträge, P0-2)
            s = self.s
            self.ist.pop("soll", None)
            v = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, self.ist, kalk=s._rechnung())
            self.ist["soll"] = nk.soll_stand(v, s.kopf, s.positionen, s.ergebnis, s.k, teile=self._teile_soll())
        self.s.db.nachkalkulation_speichern(self.s.id, self.ist or None)
        self.s.kopf["nachkalkulation"] = self.ist or None
        self.s.f.meldung("Nachkalkulation gespeichert.")
        self.s.verlauf.merken()
        self._platzhalter(self._rechnen())

    def _teile_soll(self):
        s = self.s
        return nk.teile_soll(s.kopf, s.positionen, s._rechnung()[0], s.k, s.tabellen)

    def _teile_zeigen(self):
        je = self.ist.get("laufzeit") or {}
        teile = self._teile_soll()
        self.teile.setRowCount(len(teile))
        for r, t in enumerate(teile):
            m, wer, wand, gas = t["schluessel"]
            sd = f"{str(wer).removeprefix('Kategorie ')} ≤ {_z(wand, 1)} mm{' ' + gas if gas else ''}"
            for c, w in enumerate((str(t["pos"] or ""), _z(je.get(str(t["id"])), 1), _z(t["soll_s"], 1), t["profil"],
                                   sd)):
                it = QTableWidgetItem(w)
                it.setData(Qt.UserRole, t["id"])
                it.setToolTip(f"{t['artikel']} · Schneiddaten {wer}, Wandstärke bis {_z(wand, 1)} mm"
                              + (f", {gas}" if gas else ""))
                if c == 1:
                    it.setBackground(QBrush(stil.farbe("#FFF9E5")))
                else:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setBackground(QBrush(stil.farbe("#F2F2F2")))
                if c in (1, 2):
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.teile.setItem(r, c, it)
        kopf = self.teile.horizontalHeader().sizeHint().height()
        self.teile.setMinimumHeight(kopf + 6 + 22 * max(1, min(len(teile), 5)))
        self.teile.setVisible(bool(teile))

    def _teil_geaendert(self, it):
        if self._laden or it.column() != 1:
            return
        try:
            w = self._zahl(it.text())
        except ValueError as e:
            self.s.f.meldung(str(e), fehler=True)
            self.neu_laden()
            return
        je = dict(self.ist.get("laufzeit") or {})
        schl = str(it.data(Qt.UserRole))
        if w is None:
            je.pop(schl, None)
        else:
            je[schl] = w
        self.ist["laufzeit"] = je
        self._speichern()
        self.neu_laden()

    def setzen(self, werte=None, stangen=None, meterpreis=None, teile=None):
        """Ist-Werte ohne Oberfläche setzen (Tests, Bildschirmfotos): werte {Feld: Zahl}, stangen {Gruppe: Anzahl},
        meterpreis {Gruppe: €/m}, teile {Positions-ID: Laufzeit je Teil [s]}."""
        if teile:
            self.ist.setdefault("laufzeit", {}).update({str(i): v for i, v in teile.items()})
        self.ist.update(werte or {})
        self.ist.setdefault("stangen", {}).update(stangen or {})
        if meterpreis:
            self.ist.setdefault("meterpreis", {}).update(meterpreis)
        self._speichern()
        self.neu_laden()

    def _zahl(self, text, ganz=False):
        t = (text or "").strip()
        if not t:
            return None
        try:
            w = zahl_aus_text(t)
        except ValueError:
            raise ValueError(f"'{t}' ist keine Zahl.")
        if w < 0 or (ganz and w != int(w)):
            raise ValueError("Bitte eine " + ("ganze " if ganz else "") + "Zahl ab 0 eingeben.")
        return int(w) if ganz else w

    def _feld_geaendert(self, name, w):
        if self._laden:
            return
        try:
            wert = self._zahl(w.text())
        except ValueError as e:
            self.s.f.meldung(str(e), fehler=True)
            return
        if wert == self.ist.get(name):
            return
        self.ist[name] = wert
        self._speichern()

    def _bemerkung_geaendert(self):
        if self._laden or (self.bemerkung.text().strip() or None) == self.ist.get("bemerkung"):
            return
        self.ist["bemerkung"] = self.bemerkung.text().strip() or None
        self._speichern()

    def _stangen_geaendert(self, it):
        if self._laden or it.column() not in EINGABE:
            return
        name, ganz = EINGABE[it.column()]
        try:
            wert = self._zahl(it.text(), ganz=ganz)
        except ValueError as e:
            self.s.f.meldung(str(e), fehler=True)
            self.neu_laden()
            return
        st = self.ist.setdefault(name, {})
        if st.get(it.data(Qt.UserRole)) == wert:
            return
        st[it.data(Qt.UserRole)] = wert
        self._speichern()

    def rest_wie_geplant(self):
        """Leere Ist-Werte = Soll (Plan Arbeitsabläufe W9). Ergebnis: Anzahl gesetzter Werte (None = nicht möglich)."""
        s = self.s
        if not s.ergebnis or not s.ergebnis.get("stangen") or s.stand_optimierung() != "aktuell":
            s.f.meldung("Nachkalkulation: bitte zuerst (neu) optimieren, das Soll passt sonst nicht.", fehler=True)
            return None
        v = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, self.ist, kalk=s._rechnung())
        self.ist, n = nk.rest_wie_geplant(v, self.ist)
        if not n:
            s.f.meldung("Alle Ist-Werte sind schon eingetragen.")
            return 0
        self._speichern()
        self.neu_laden()
        s.f.meldung(f"{n} Ist-Wert(e) wie geplant übernommen.")
        return n

    def loeschen(self):
        if not self.ist:
            return
        self.ist = {}           # ohne Rückfrage, mit „Rückgängig“ (Plan Bedienung B2)
        self.s.db.nachkalkulation_speichern(self.s.id, None)
        self.s.kopf["nachkalkulation"] = None
        self.neu_laden()
        self.s.rueckgaengig_anbieten("Alle Ist-Werte der Nachkalkulation gelöscht.")

    def pdf(self):
        from . import pdf
        s = self.s
        if not s.ergebnis or not s.ergebnis.get("stangen"):
            self.s.f.meldung("Nachkalkulation: bitte zuerst optimieren.", fehler=True)
            return None
        v = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, self.ist, kalk=s._rechnung())
        aktuell = s.stand_optimierung() == "aktuell"
        return s._schreiben("Nachkalkulation", s._ziel("Nachkalkulation", ".pdf"),
                            lambda p: pdf.nachkalkulation_pdf(p, s.kopf, v, self.ist, aktuell, s.einst))

    def auswertung(self, dialog=None):
        """Fenster „Auswertung der Nachkalkulation“ über alle Aufträge (nachkalkulation.auswertung)."""
        d = AuswertungDialog(self, self.s.db)
        (dialog(d) if dialog else d.exec())
        return d


AUSWERTUNG_SPALTEN = (("Gruppe", "gruppe", None), ("Kostenart", "kostenart", None), ("Aufträge", "n", 0),
                      ("Soll [€]", "soll", 2), ("Ist [€]", "ist", 2), ("Abweichung [€]", "abweichung", 2),
                      ("Abweichung [%]", "prozent", 1), ("Median Ist ÷ Soll", "median", 3),
                      ("Streuung (MAD)", "streuung", 3))


class AuswertungDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Auswertung der Nachkalkulation")
        self.resize(980, 560)
        self.merkmal = QComboBox()
        for name, titel in nk.MERKMALE.items():
            self.merkmal.addItem(titel, name)
        self.merkmal.currentIndexChanged.connect(self.neu_laden)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Gruppieren nach:"))
        oben.addWidget(self.merkmal)
        oben.addStretch(1)
        self.tabelle = QTableWidget(0, len(AUSWERTUNG_SPALTEN))
        self.tabelle.setHorizontalHeaderLabels([t for t, _, _ in AUSWERTUNG_SPALTEN])
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.verticalHeader().setVisible(False)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(self.info)
        kn = QDialogButtonBox(QDialogButtonBox.Close)
        kn.rejected.connect(self.reject)
        lay.addWidget(kn)
        self.ergebnis = None
        self.neu_laden()

    def neu_laden(self, *_):
        self.ergebnis = e = nk.auswertung(self.db, self.merkmal.currentData())
        self.tabelle.setRowCount(len(e["zeilen"]))
        for r, z in enumerate(e["zeilen"]):
            for c, (_, name, st) in enumerate(AUSWERTUNG_SPALTEN):
                w = z.get(name)
                it = QTableWidgetItem(_z(w, st) if st is not None else str(w or ""))
                if st is not None:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if name == "prozent":
                    b = nk.bewertung(z["soll"], z["ist"])
                    if b:
                        it.setBackground(QBrush(ROT_FLAECHE if b == "hoch" else GRUEN_FLAECHE))
                self.tabelle.setItem(r, c, it)
        self.tabelle.resizeColumnsToContents()
        a = e["ausschuss"]
        self.info.setText(
            f"{e['auftraege']} nachkalkulierte Aufträge ausgewertet; nur erfasste Ist-Werte zählen (leer ist weder "
            "0 € noch „wie geplant“). Median und Streuung zeigen, wie sicher eine Abweichung ist; Richtwerte ändern "
            "sich nur über Einstellungen → Kennwerte aus der Nachkalkulation (mit Freigabe)."
            + (f" {e['ohne_soll']} ältere Nachkalkulation(en) ohne gespeichertes Soll: einmal öffnen und einen "
               "Ist-Wert speichern." if e["ohne_soll"] else "")
            + (f" Ausschuss: {a['stueck']:g} von {a['teile']} Teilen ({_z(100 * a['quote'], 2)} %)." if a["quote"]
               is not None else ""))
