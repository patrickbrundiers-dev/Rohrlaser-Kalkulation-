"""Reiter 'Nachkalkulation' im Angebot: Ist-Werte nach dem Auftrag erfassen und mit der Kalkulation vergleichen."""
import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from . import nachkalkulation as nk
from .spaltenbreite import AutoGroesse
from .stammdaten import zahl_als_text, zahl_aus_text

VERGLEICH_SPALTEN = [("Kostenart", "text", None, 230), ("Einheit", "einheit", None, 60),
                     ("Menge Soll", "soll_menge", 2, 85), ("Menge Ist", "ist_menge", 2, 85),
                     ("Soll [€]", "soll", 2, 90), ("Ist [€]", "ist", 2, 90), ("Abweichung [€]", "abweichung", 2, 95),
                     ("Abweichung [%]", "prozent", 1, 90), ("Ist erfasst", "erfasst", None, 70)]
GRUPPEN_TITEL = ("Profil-ID", "Werkstoff-ID", "Stangenlänge [mm]", "Stangen Soll", "Stangen Ist",
                 "EK-Meterpreis Soll [€/m]", "EK-Meterpreis Ist [€/m]")
EINGABE = {4: ("stangen", True), 6: ("meterpreis", False)}   # editierbare Spalten: (Schlüssel in ist, ganze Zahl)


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
        knoepfe = QHBoxLayout()
        for text, ziel in (("Ist-Werte löschen", self.loeschen), ("Nachkalkulation (PDF)", self.pdf)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            knoepfe.addWidget(b)
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
        self._laden = True
        if not s.ergebnis or not s.ergebnis.get("stangen"):
            self.stand.setText("<b style='color:#9C5700'>Noch nicht optimiert: die Nachkalkulation vergleicht mit dem "
                               "Schnittplan und der Kalkulation. Bitte zuerst optimieren.</b>")
        elif s.stand_optimierung() != "aktuell":
            self.stand.setText("<b style='color:#C00000'>Optimierung VERALTET: das Soll passt nicht mehr zum Angebot. "
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
                    it.setBackground(QBrush(QColor("#F2F2F2")))
                else:
                    it.setBackground(QBrush(QColor("#FFF9E5")))
                if c >= 2:
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.gruppen.setItem(r, c, it)
        for name, _, stellen in nk.FELDER:
            w = self.ist.get(name)
            self.felder[name].setText(_z(w, stellen) if w is not None else "")
        self.bemerkung.setText(self.ist.get("bemerkung") or "")
        self._platzhalter(v)
        self._laden = False

    def _rechnen(self):
        s = self.s
        v = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, self.ist)
        self.vergleich.setzen(v["zeilen"] + [v["summe"], v["erloes"], v["db"]])
        db = v["db"]
        farbe = "#375623" if db["abweichung"] >= 0 else "#C00000"
        self.ergebnis.setText(
            f"Deckungsbeitrag Soll {_z(db['soll'])} € · Ist <b style='color:{farbe}'>{_z(db['ist'])} €</b> "
            f"(Abweichung {_z(db['abweichung'])} €). Einzelkosten Ist {_z(v['summe']['ist'])} € gegen Soll "
            f"{_z(v['summe']['soll'])} €. Herstellkosten laut Kalkulation (mit Zuschlägen) {_z(v['herstell'])} €.")
        return v

    def _platzhalter(self, v):
        soll = {"laser_h": (v["zeilen"][1]["soll_menge"], 2), "ruest_min": (v["zeilen"][2]["soll_menge"], 0),
                "zusatz": (v["zeilen"][3]["soll"], 2), "zukauf": (v["zeilen"][4]["soll"], 2), "sonstiges": (0, 2), "erloes": (v["erloes"]["soll"], 2)}
        for name, (w, st) in soll.items():
            self.felder[name].setPlaceholderText(f"leer = Soll {_z(w, st)}")

    # -------------------------------------------------------------- Speichern
    def _speichern(self):
        self.ist["am"] = datetime.datetime.now().isoformat(timespec="seconds")
        if not nk.erfasst(self.ist) and not self.ist.get("bemerkung"):
            self.ist = {}
        self.s.db.nachkalkulation_speichern(self.s.id, self.ist or None)
        self.s.kopf["nachkalkulation"] = self.ist or None
        self.s.f.meldung("Nachkalkulation gespeichert.")
        self.s.verlauf.merken()
        self._platzhalter(self._rechnen())

    def setzen(self, werte=None, stangen=None, meterpreis=None):
        """Ist-Werte ohne Oberfläche setzen (Tests, Bildschirmfotos): werte {Feld: Zahl}, stangen {Gruppe: Anzahl},
        meterpreis {Gruppe: €/m}."""
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

    def loeschen(self):
        if not self.ist:
            return
        if self.s.f.stumm or QMessageBox.question(self, "Nachkalkulation", "Alle Ist-Werte dieses Angebots löschen?") \
                == QMessageBox.Yes:
            self.ist = {}
            self.s.db.nachkalkulation_speichern(self.s.id, None)
            self.s.kopf["nachkalkulation"] = None
            self.neu_laden()

    def pdf(self):
        from . import pdf
        s = self.s
        if not s.ergebnis or not s.ergebnis.get("stangen"):
            QMessageBox.warning(self, "Nachkalkulation", "Bitte zuerst optimieren.")
            return None
        v = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, self.ist)
        aktuell = s.stand_optimierung() == "aktuell"
        return s._schreiben("Nachkalkulation", s._ziel("Nachkalkulation", ".pdf"),
                            lambda p: pdf.nachkalkulation_pdf(p, s.kopf, v, self.ist, aktuell, s.einst))
