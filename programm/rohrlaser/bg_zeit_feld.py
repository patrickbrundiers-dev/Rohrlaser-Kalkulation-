"""Feld „Kalkulation: Zeit“ im Fenster Schweißbaugruppe (Konzept 12.11.2026, Paket 1 und 3): automatische Zeit,
Zeit von Hand und Abweichung für Stückzeit je Baugruppe und Rüstzeit je Auftrag, je Bereich aufklappbar, dazu
Komplexitätsfaktor mit Gründen, Stundensatz und Notiz der Vorgabe. Jeder Wert lässt sich mit ↺ auf automatisch
zurücksetzen, „Alles automatisch“ setzt alles zurück. Eingabe direkt im Feld (55, 1,5 h, 1:20, 1 h 20 min);
geändert wird beim Verlassen des Felds bzw. mit Enter, das Fenster rechnet sofort neu.

Das Feld kennt nur die Daten; was gespeichert wird, entscheidet der Dialog (Signal geaendert(dict)):
dict(stueck_min, ruest_min, bereiche, satz_id, grund, komplex_faktor, komplex_gruende) – None = automatisch.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from . import bg_vorgabe as bv
from . import stil

_ZURUECK = "↺"


def _zahl_text(w, stellen=2):
    return f"{round(w, stellen):g}".replace(".", ",")


class ZeitFeld(QFrame):
    geaendert = Signal(dict)

    def __init__(self, saetze=None, nur_lesen=False, parent=None):
        super().__init__(parent)
        self.saetze = saetze or {}
        self.nur_lesen = nur_lesen
        self.z = None
        self.setObjectName("zeit_feld")
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        lay.addWidget(QLabel("<b>Kalkulation: Zeit</b>"))
        self.status = QLabel()
        self.status.setObjectName("zeit_status")
        lay.addWidget(self.status)
        g = QGridLayout()
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(1)
        g.setColumnStretch(1, 1)
        grau = f"color: {stil.umsetzen(stil.TEXT_GRAU)};"
        self.felder, self.auto_l, self.abw_l, self.zurueck = {}, {}, {}, {}
        for i, (n, t, tipp) in enumerate((
                ("stueck_min", "Stückzeit je BG", "Zeit für eine Baugruppe ohne Rüsten (Nahtgruppen und laufende "
                 "Arbeitsgänge, ohne Fremdleistung). Von Hand: ersetzt die Summe, die Kosten folgen anteilig."),
                ("ruest_min", "Rüstzeit je Auftrag", "Einmal je Auftrag (alle Lose): Rüstzeiten der Arbeitsgänge. "
                 "Von Hand: ersetzt die Summe, unabhängig von der Stückzeit."))):
            r = i * 2
            k = QLabel(t)
            k.setToolTip(tipp)
            g.addWidget(k, r, 0)
            f = QLineEdit()
            f.setObjectName(f"zeit_{n}")
            f.setPlaceholderText("automatisch")
            f.setToolTip(tipp + "\nEingabe z. B. 55, 55 min, 1,5 h, 1:20 oder 1 h 20 min; leer = automatisch.")
            f.setMinimumWidth(80)
            f.setReadOnly(nur_lesen)
            f.editingFinished.connect(self._melden)
            self.felder[n] = f
            g.addWidget(f, r, 1)
            b = QToolButton()
            b.setText(_ZURUECK)
            b.setToolTip("Zurück auf die automatische Berechnung")
            b.setEnabled(not nur_lesen)
            b.clicked.connect(lambda _=False, n=n: self._zuruecksetzen(n))
            self.zurueck[n] = b
            g.addWidget(b, r, 2)
            zeile = QHBoxLayout()
            zeile.setContentsMargins(0, 0, 0, 2)
            self.auto_l[n] = QLabel()
            self.auto_l[n].setStyleSheet(grau)
            self.abw_l[n] = QLabel()
            zeile.setSpacing(8)
            self.abw_l[n].setStyleSheet(f"color: {stil.umsetzen(stil.ORANGE)}; font-weight: bold;")
            zeile.addWidget(self.auto_l[n])
            zeile.addWidget(self.abw_l[n])
            zeile.addStretch(1)
            g.addLayout(zeile, r + 1, 0, 1, 3)
        lay.addLayout(g)
        self.gesamt = QLabel()
        self.gesamt.setWordWrap(True)
        lay.addWidget(self.gesamt)
        # Je Bereich (aufklappbar)
        self.bereich_knopf = QToolButton()
        self.bereich_knopf.setText("▸ Je Bereich")
        self.bereich_knopf.setCheckable(True)
        self.bereich_knopf.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.bereich_knopf.setAutoRaise(True)
        self.bereich_knopf.toggled.connect(self._bereich_auf)
        lay.addWidget(self.bereich_knopf)
        self.bereich_w = QWidget()
        bg_ = QGridLayout(self.bereich_w)
        bg_.setContentsMargins(10, 0, 0, 0)
        bg_.setHorizontalSpacing(6)
        bg_.setVerticalSpacing(2)
        for c, t in enumerate(("Bereich", "automatisch", "von Hand")):
            k = QLabel(t)
            k.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
            bg_.addWidget(k, 0, c)
        self.b_ruest, self.b_auto, self.b_feld = {}, {}, {}
        for r, b in enumerate(bv.BEREICHE, 1):
            self.b_ruest[b] = QLabel(b)
            bg_.addWidget(self.b_ruest[b], r, 0)
            self.b_auto[b] = QLabel()
            bg_.addWidget(self.b_auto[b], r, 1)
            f = QLineEdit()
            f.setObjectName(f"zeit_bereich_{b}")
            f.setPlaceholderText("automatisch")
            f.setMinimumWidth(70)
            f.setReadOnly(nur_lesen)
            f.setToolTip(f"Stückzeit {b} von Hand (min je Baugruppe); gilt nur ohne Stückzeit von Hand gesamt")
            f.editingFinished.connect(self._melden)
            self.b_feld[b] = f
            bg_.addWidget(f, r, 2)
        self.bereich_w.setVisible(False)
        lay.addWidget(self.bereich_w)
        # Komplexitätsfaktor (aufklappbar mit Gründen)
        kz = QHBoxLayout()
        kz.addWidget(QLabel("Komplexität ×"))
        self.komplex = QLineEdit()
        self.komplex.setObjectName("zeit_komplex")
        self.komplex.setPlaceholderText("1,0")
        self.komplex.setMaximumWidth(60)
        self.komplex.setReadOnly(nur_lesen)
        self.komplex.setToolTip("Faktor auf die automatische Stückzeit der eigenen Leistungen (nicht auf Rüsten und "
                                "nicht auf eine Zeit von Hand). 1,0 = wie berechnet. Kein Vorschlag ohne Ist-Daten.")
        self.komplex.editingFinished.connect(self._melden)
        kz.addWidget(self.komplex)
        self.gruende_knopf = QToolButton()
        self.gruende_knopf.setText("▸ Gründe")
        self.gruende_knopf.setCheckable(True)
        self.gruende_knopf.setAutoRaise(True)
        self.gruende_knopf.toggled.connect(self._gruende_auf)
        kz.addWidget(self.gruende_knopf)
        kz.addStretch(1)
        lay.addLayout(kz)
        self.gruende_w = QWidget()
        gl = QVBoxLayout(self.gruende_w)
        gl.setContentsMargins(10, 0, 0, 0)
        gl.setSpacing(0)
        self.gruende = {}
        for t in bv.KOMPLEX_GRUENDE:
            c = QCheckBox(t)
            c.setEnabled(not nur_lesen)
            c.toggled.connect(self._melden)
            self.gruende[t] = c
            gl.addWidget(c)
        self.gruende_w.setVisible(False)
        lay.addWidget(self.gruende_w)
        # Stundensatz und Notiz der Vorgabe (nur mit Vorgabe sichtbar)
        self.hand_w = QWidget()
        hl = QGridLayout(self.hand_w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(QLabel("Stundensatz"), 0, 0)
        self.satz = QComboBox()
        self.satz.setObjectName("zeit_satz")
        self.satz.setToolTip("Gilt nur für Zeit von Hand ohne automatische Grundlage (z. B. Schnellkalkulation); "
                             "sonst bleibt die Mischung der Stundensätze der berechneten Zeilen")
        self.satz.addItem("wie berechnet", None)
        for s, v in sorted(self.saetze.items()):
            self.satz.addItem(f"{s} ({_zahl_text(v)} €/h)" if isinstance(v, (int, float)) else str(s), s)
        self.satz.setEnabled(not nur_lesen)
        self.satz.activated.connect(self._melden)
        hl.addWidget(self.satz, 0, 1)
        hl.addWidget(QLabel("Notiz"), 1, 0)
        self.grund = QLineEdit()
        self.grund.setObjectName("zeit_grund")
        self.grund.setPlaceholderText("z. B. Erfahrung Auftrag 2026-114")
        self.grund.setReadOnly(nur_lesen)
        self.grund.editingFinished.connect(self._melden)
        hl.addWidget(self.grund, 1, 1)
        lay.addWidget(self.hand_w)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        lay.addWidget(self.hinweis)
        self.alles = QPushButton("Alles automatisch")
        self.alles.setObjectName("zeit_alles_auto")
        self.alles.setToolTip("Alle Zeiten von Hand und den Komplexitätsfaktor entfernen")
        self.alles.setEnabled(not nur_lesen)
        self.alles.clicked.connect(self.alles_automatisch)
        lay.addWidget(self.alles)
        self._fehler = None

    # -------------------------------------------------------------- Anzeige
    def _bereich_auf(self, an):
        self.bereich_w.setVisible(an)
        self.bereich_knopf.setText(("▾" if an else "▸") + " Je Bereich")

    def _gruende_auf(self, an):
        self.gruende_w.setVisible(an)
        self.gruende_knopf.setText(("▾" if an else "▸") + " Gründe")

    @staticmethod
    def _setzen_still(f, text):
        if f.hasFocus() and f.isModified():
            return
        f.blockSignals(True)
        f.setText(text)
        f.setModified(False)
        f.blockSignals(False)

    def setzen(self, bg, z):
        """Anzeige aus der Baugruppe (Vorgabe, Komplexität) und dem Ergebnis zeiten von baugruppe.rechnen."""
        self.z = z
        if not z:
            return
        v = bv.vorgabe(bg)
        kf, gruende = bv.komplex(bg)
        auto_s = z["auto_komplex_min"]
        for n, auto in (("stueck_min", auto_s), ("ruest_min", z["auto_ruest_min"])):
            self.auto_l[n].setText(f"automatisch {bv.zeit_text(auto)}")
            self._setzen_still(self.felder[n], bv.zeit_text(v[n]) if v[n] is not None else "")
            self.abw_l[n].setText(bv.abweichung_text(v[n] - auto) if v[n] is not None else "")
            self._hand_stil(self.felder[n], v[n] is not None)
            self.zurueck[n].setVisible(v[n] is not None)
        n = z.get("anzahl") or 0
        auto_g = z["auto_ruest_min"] + auto_s * n
        t = f"Gesamt bei {n:g} Stk.: <b>{bv.zeit_text(z['gesamt_min'])}</b>"
        if z["hand"]:
            t += (f" <span style='color:{stil.umsetzen(stil.TEXT_GRAU)}'>(automatisch {bv.zeit_text(auto_g)}, "
                  f"{bv.abweichung_text(z['gesamt_min'] - auto_g)})</span>")
        self.gesamt.setText(t)
        ber = {x["bereich"]: x for x in z["bereiche"]}
        for b in bv.BEREICHE:
            x = ber.get(b)
            self.b_ruest[b].setToolTip(f"Rüsten {b}: {bv.zeit_text(x['ruest'])} je Auftrag" if x and x["ruest"]
                                       else "")
            self.b_auto[b].setText(bv.zeit_text(x["auto_stueck"] * z["komplex"]) if x else "")
            self._setzen_still(self.b_feld[b], bv.zeit_text(v["bereiche"][b]) if b in v["bereiche"] else "")
            self._hand_stil(self.b_feld[b], b in v["bereiche"])
            self.b_feld[b].setEnabled(v["stueck_min"] is None)
        if v["bereiche"] and not self.bereich_knopf.isChecked():
            self.bereich_knopf.setChecked(True)
        self._setzen_still(self.komplex, _zahl_text(kf) if abs(kf - 1) > 1e-9 else "")
        self._hand_stil(self.komplex, abs(kf - 1) > 1e-9)
        for t, c in self.gruende.items():
            c.blockSignals(True)
            c.setChecked(t in gruende)
            c.blockSignals(False)
        i = self.satz.findData(v["satz_id"])
        self.satz.setCurrentIndex(max(0, i))
        self._setzen_still(self.grund, v["grund"])
        self.hand_w.setVisible(z["hand"])
        if z["hand"]:
            self.status.setText(f"<span style='color:{stil.umsetzen(stil.ORANGE)}'>● von Hand vorgegeben</span>")
        elif abs(kf - 1) > 1e-9:
            self.status.setText(f"<span style='color:{stil.umsetzen(stil.ORANGE)}'>● automatisch × Komplexität</span>")
        else:
            self.status.setText(f"<span style='color:{stil.umsetzen(stil.GRUEN)}'>● automatisch berechnet</span>")
        hinweise = []
        damals = v["auto_damals"]
        if z["hand"] and damals and abs((damals.get("stueck_min") or 0) - z["auto_stueck_min"]) > 0.05:
            hinweise.append(f"Die automatische Stückzeit hat sich seit der Vorgabe geändert: "
                            f"{bv.zeit_text(damals.get('stueck_min'))} → {bv.zeit_text(z['auto_stueck_min'])}.")
        if v["am"] and z["hand"]:
            hinweise.append(f"Vorgabe vom {v['am']}.")
        if self._fehler:
            hinweise.insert(0, f"<span style='color:{stil.umsetzen(stil.ROT)}'>{self._fehler}</span>")
        self.hinweis.setText(" ".join(hinweise))
        self.hinweis.setVisible(bool(hinweise))
        self.alles.setVisible(z["hand"] or abs(kf - 1) > 1e-9)

    @staticmethod
    def _hand_stil(f, hand):
        f.setStyleSheet(f"background: {stil.umsetzen(stil.GELB_FLAECHE)}; font-weight: bold;" if hand else "")

    # -------------------------------------------------------------- Eingaben
    def werte(self):
        """Eingaben als dict (siehe Modulkopf); bv.Fehler bei unlesbarer Zeit oder Faktor."""
        out = {n: bv.zeit_lesen(f.text()) for n, f in self.felder.items()}
        out["bereiche"] = {}
        for b, f in self.b_feld.items():
            w = bv.zeit_lesen(f.text())
            if w is not None:
                out["bereiche"][b] = w
        t = self.komplex.text().strip().replace(",", ".").lstrip("×x*")
        try:
            kf = float(t) if t else 1.0
        except ValueError:
            raise bv.Fehler(f"Komplexitätsfaktor „{self.komplex.text()}“ ist keine Zahl (z. B. 1,2)") from None
        if kf <= 0 or kf > 10:
            raise bv.Fehler("Komplexitätsfaktor zwischen 0,1 und 10")
        out.update(satz_id=self.satz.currentData(), grund=self.grund.text().strip(), komplex_faktor=kf,
                   komplex_gruende=[t for t, c in self.gruende.items() if c.isChecked()])
        return out

    def _melden(self, *_):
        try:
            w = self.werte()
        except bv.Fehler as e:
            self._fehler = str(e)
            if self.z:
                self.hinweis.setText(f"<span style='color:{stil.umsetzen(stil.ROT)}'>{e}</span>")
                self.hinweis.setVisible(True)
            return
        self._fehler = None
        for f in list(self.felder.values()) + list(self.b_feld.values()) + [self.komplex, self.grund]:
            f.setModified(False)
        self.geaendert.emit(w)

    def _zuruecksetzen(self, n):
        self.felder[n].setText("")
        self._melden()

    def alles_automatisch(self):
        for f in list(self.felder.values()) + list(self.b_feld.values()) + [self.komplex, self.grund]:
            f.setText("")
        for c in self.gruende.values():
            c.blockSignals(True)
            c.setChecked(False)
            c.blockSignals(False)
        self.satz.setCurrentIndex(0)
        self._melden()
