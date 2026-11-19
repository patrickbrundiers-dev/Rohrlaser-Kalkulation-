"""Feld „Kalkulation: Zeit“ im Fenster Schweißbaugruppe (Konzept 12.11.2026, Paket 1 und 3): automatische Zeit,
Zeit von Hand und Abweichung für Stückzeit je Baugruppe und Rüstzeit je Auftrag, je Bereich aufklappbar, dazu
Komplexitätsfaktor mit Gründen, Stundensatz und Notiz der Vorgabe. Jeder Wert lässt sich mit ↺ auf automatisch
zurücksetzen, „Alles automatisch“ setzt alles zurück. Eingabe direkt im Feld (55, 1,5 h, 1:20, 1 h 20 min);
geändert wird beim Verlassen des Felds bzw. mit Enter, das Fenster rechnet sofort neu.

Das Feld kennt nur die Daten; was gespeichert wird, entscheidet der Dialog (Signal geaendert(dict)):
dict(gesamt_min, stueck_min, ruest_min, bereiche, satz_id, grund, frei, komplex_faktor, komplex_gruende) – None =
automatisch.

Editor 2.0 (19.11.2026): oben die Gesamtzeit je Baugruppe von Hand (ein Wert für die ganze Bearbeitung, geht vor
allem anderen), darunter der Zeitvorschlag aus vergleichbaren Baugruppen (nur mit Knopf übernommen), der Hinweis,
wenn sich die Baugruppe seit der Vorgabe geändert hat, das Protokoll und die Auswertung.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from . import bg_vorgabe as bv
from . import stil
from .stammdaten import zahl_als_text, zahl_aus_text

_ZURUECK = "↺"


def _zahl_text(w, stellen=2):
    return f"{round(w, stellen):g}".replace(".", ",")


class ZeitFeld(QFrame):
    geaendert = Signal(dict)
    vorschlag_nehmen = Signal()         # Lernvorschlag als Gesamtzeit übernehmen
    vergleichbare = Signal()            # vergleichbare Baugruppen zeigen
    auswertung = Signal()               # Auswertung der Zeiten von Hand
    bestaetigt = Signal()               # Zeit von Hand gilt nach einer Änderung der Baugruppe weiter
    protokoll = Signal()                # Protokoll der Änderungen zeigen

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
        self.titel = QLabel("<b>Kalkulation: Zeit</b>")
        lay.addWidget(self.titel)
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
                ("gesamt_min", "<b>Gesamtzeit je Baugruppe</b>", "Die ganze Bearbeitungszeit einer Baugruppe mit einem "
                 "Wert von Hand: Stückzeit und Rüstanteil zusammen, ohne Fremdleistung. Sie geht vor allem anderen "
                 "(Stückzeit, Rüstzeit, Bereiche) und wird nicht zur berechneten Zeit dazugezählt: die berechneten "
                 "Zeiten werden anteilig auf genau diesen Wert gebracht und bleiben als Grundlage sichtbar."),
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
        self.felder["gesamt_min"].setPlaceholderText("automatisch (z. B. 240 oder 4 h)")
        # Hinweis nach einer Änderung der Baugruppe: die Zeit von Hand bleibt, der Benutzer prüft sie
        self.pruef_w = QFrame()
        self.pruef_w.setObjectName("zeit_pruefen")
        self.pruef_w.setStyleSheet(f"#zeit_pruefen {{ border: 1px solid {stil.umsetzen(stil.ORANGE)}; "
                                   "border-radius: 4px; }")
        pl = QVBoxLayout(self.pruef_w)
        pl.setContentsMargins(6, 4, 6, 4)
        self.pruef_l = QLabel()
        self.pruef_l.setWordWrap(True)
        pl.addWidget(self.pruef_l)
        self.pruef_k = QPushButton("Zeit geprüft, gilt weiter")
        self.pruef_k.setObjectName("zeit_bestaetigen")
        self.pruef_k.setToolTip("Die Zeit von Hand bleibt, der heutige Stand der Baugruppe wird als Grundlage gemerkt")
        self.pruef_k.setEnabled(not nur_lesen)
        self.pruef_k.clicked.connect(self.bestaetigt.emit)
        pl.addWidget(self.pruef_k)
        self.pruef_w.setVisible(False)
        lay.addWidget(self.pruef_w)
        # Zeitvorschlag aus vergleichbaren Baugruppen (bg_zeitlernen): nur Anzeige, übernommen wird mit dem Knopf
        self.vorschlag_w = QFrame()
        self.vorschlag_w.setObjectName("zeit_vorschlag")
        self.vorschlag_w.setStyleSheet(f"#zeit_vorschlag {{ border: 1px solid {stil.umsetzen(stil.TEXT_GRAU)}; "
                                       "border-radius: 4px; }")
        vl = QVBoxLayout(self.vorschlag_w)
        vl.setContentsMargins(6, 4, 6, 4)
        self.vorschlag_l = QLabel()
        self.vorschlag_l.setObjectName("zeit_vorschlag_text")
        self.vorschlag_l.setWordWrap(True)
        vl.addWidget(self.vorschlag_l)
        vz = QHBoxLayout()
        self.vorschlag_k = QPushButton("Vorschlag übernehmen")
        self.vorschlag_k.setObjectName("zeit_vorschlag_nehmen")
        self.vorschlag_k.setToolTip("Trägt den Vorschlag als Gesamtzeit je Baugruppe von Hand ein (wird protokolliert)")
        self.vorschlag_k.setEnabled(not nur_lesen)
        self.vorschlag_k.clicked.connect(self.vorschlag_nehmen.emit)
        vz.addWidget(self.vorschlag_k)
        self.vergleich_k = QPushButton("Vergleichbare …")
        self.vergleich_k.setObjectName("zeit_vergleichbare")
        self.vergleich_k.setToolTip("Die vergleichbaren Baugruppen mit automatischer Zeit, Zeit von Hand und Ähnlichkeit")
        self.vergleich_k.clicked.connect(self.vergleichbare.emit)
        vz.addWidget(self.vergleich_k)
        vz.addStretch(1)
        vl.addLayout(vz)
        self.vorschlag_w.setVisible(False)
        lay.addWidget(self.vorschlag_w)
        self._vorschlag = None
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
        # Schnellkalkulation (Paket 3): Material und Zukauf pauschal, nur für Baugruppen ohne Einzelteile sichtbar
        self.ohne_teile = False
        self.schnell_w = QWidget()
        sl = QGridLayout(self.schnell_w)
        sl.setContentsMargins(0, 2, 0, 0)
        sl.addWidget(QLabel("<b>Schnellkalkulation</b> (ohne Einzelteile)"), 0, 0, 1, 2)
        self.schnell = {}
        for r, (n, t) in enumerate((("material_eur", "Material je BG [€]"), ("zukauf_eur", "Zukauf je BG [€]")), 1):
            sl.addWidget(QLabel(t), r, 0)
            f = QLineEdit()
            f.setObjectName(f"schnell_{n}")
            f.setPlaceholderText("0")
            f.setReadOnly(nur_lesen)
            f.setToolTip("Pauschal je Baugruppe, wenn keine Einzelteile erfasst sind. Material mit Gewinn, Zukauf wie "
                         "Zukaufteile. Die Zeit oben bei Stückzeit/Rüstzeit von Hand eintragen, Stundensatz darunter.")
            f.editingFinished.connect(self._melden)
            self.schnell[n] = f
            sl.addWidget(f, r, 1)
        lay.addWidget(self.schnell_w)
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
        # Erfahrung (Paket 4): letzte Ist-Zeit derselben oder einer ähnlichen Baugruppe aus der Nachkalkulation
        self.erfahrung = QLabel()
        self.erfahrung.setObjectName("zeit_erfahrung")
        self.erfahrung.setWordWrap(True)
        self.erfahrung.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        self.erfahrung.setVisible(False)
        lay.addWidget(self.erfahrung)
        self.frei = QCheckBox("Für Zeitvorschläge freigeben")
        self.frei.setObjectName("zeit_frei")
        self.frei.setToolTip("Freigegeben: diese Zeit von Hand zählt bei den Vorschlägen für vergleichbare Baugruppen "
                             "mit. Ohne Haken wird sie gespeichert und protokolliert, aber nicht zum Lernen verwendet.")
        self.frei.setChecked(True)
        self.frei.setEnabled(not nur_lesen)
        self.frei.toggled.connect(self._melden)
        lay.addWidget(self.frei)
        uz = QHBoxLayout()
        self.protokoll_k = QPushButton("Protokoll …")
        self.protokoll_k.setObjectName("zeit_protokoll")
        self.protokoll_k.setToolTip("Alle Änderungen der Zeit von Hand an dieser Baugruppe: alt, neu, wer, wann, Grund")
        self.protokoll_k.clicked.connect(self.protokoll.emit)
        uz.addWidget(self.protokoll_k)
        self.auswertung_k = QPushButton("Auswertung …")
        self.auswertung_k.setObjectName("zeit_auswertung")
        self.auswertung_k.setToolTip("Zeiten von Hand aller Schweißbaugruppen: Abweichungen, Arten, Material, Verlauf")
        self.auswertung_k.clicked.connect(self.auswertung.emit)
        uz.addWidget(self.auswertung_k)
        uz.addStretch(1)
        lay.addLayout(uz)
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
        hg = v["gesamt_min"] is not None
        for n, auto in (("gesamt_min", z["auto_je_bg_min"]), ("stueck_min", auto_s), ("ruest_min", z["auto_ruest_min"])):
            self.auto_l[n].setText(f"automatisch {bv.zeit_text(auto)}"
                                   + (" (mit Rüstanteil)" if n == "gesamt_min" and z["auto_ruest_min"] else ""))
            self._setzen_still(self.felder[n], bv.zeit_text(v[n]) if v[n] is not None else "")
            t = bv.abweichung_text(v[n] - auto) if v[n] is not None else ""
            if t and auto > 1e-9:
                pz = (v[n] / auto - 1) * 100
                t += f" ({'+' if pz >= 0 else '−'}{abs(pz):.0f} %)"
            if n != "gesamt_min" and hg and v[n] is not None:
                t = "ruht (Gesamtzeit geht vor)"
            self.abw_l[n].setText(t)
            self._hand_stil(self.felder[n], v[n] is not None and (n == "gesamt_min" or not hg))
            self.zurueck[n].setVisible(v[n] is not None)
            if n != "gesamt_min":
                self.felder[n].setEnabled(not hg)
        n = z.get("anzahl") or 0
        auto_g = z["auto_ruest_min"] + auto_s * n
        t = f"Gesamt bei {n:g} Stk.: <b>{bv.zeit_text(z['gesamt_min'])}</b>"
        if z["hand"]:
            t += (f" <span style='color:{stil.umsetzen(stil.TEXT_GRAU)}'>(automatisch {bv.zeit_text(auto_g)}, "
                  f"{bv.abweichung_text(z['gesamt_min'] - auto_g)})</span>")
        self.gesamt.setText(t)
        ber = {x["bereich"]: x for x in z["bereiche"]}
        liste = bv.bereiche_liste(bg)
        for b in bv.BEREICHE:
            for w_ in (self.b_ruest[b], self.b_auto[b], self.b_feld[b]):
                w_.setVisible(b in liste)
        for b in bv.BEREICHE:
            x = ber.get(b)
            self.b_ruest[b].setToolTip(f"Rüsten {b}: {bv.zeit_text(x['ruest'])} je Auftrag" if x and x["ruest"]
                                       else "")
            self.b_auto[b].setText(bv.zeit_text(x["auto_stueck"] * z["komplex"]) if x else "–")
            self._setzen_still(self.b_feld[b], bv.zeit_text(v["bereiche"][b]) if b in v["bereiche"] else "")
            self._hand_stil(self.b_feld[b], b in v["bereiche"])
            self.b_feld[b].setEnabled(v["stueck_min"] is None and not hg)
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
        sc = bv.schnell(bg)
        for n, f in self.schnell.items():
            self._setzen_still(f, zahl_als_text(sc[n], 2) if sc[n] else "")
        self.schnell_w.setVisible(self.ohne_teile or any(sc.values()))
        self.hand_w.setVisible(z["hand"] or self.schnell_w.isVisibleTo(self))
        self.frei.blockSignals(True)
        self.frei.setChecked(v["frei"])
        self.frei.blockSignals(False)
        self.frei.setVisible(bool(z["hand"]))
        self.protokoll_k.setVisible(bool(bv.protokoll(bg)))
        if hg:
            self.status.setText(f"<span style='color:{stil.umsetzen(stil.ORANGE)}'>● Gesamtzeit von Hand: "
                                f"<b>{bv.zeit_text(z['je_bg_min'])}</b> je Baugruppe statt berechnet "
                                f"{bv.zeit_text(z['auto_je_bg_min'])}</span>")
        elif z["hand"]:
            self.status.setText(f"<span style='color:{stil.umsetzen(stil.ORANGE)}'>● von Hand vorgegeben</span>")
        elif abs(kf - 1) > 1e-9:
            self.status.setText(f"<span style='color:{stil.umsetzen(stil.ORANGE)}'>● automatisch × Komplexität</span>")
        else:
            self.status.setText(f"<span style='color:{stil.umsetzen(stil.GRUEN)}'>● automatisch berechnet</span>")
        hinweise = []
        damals = v["auto_damals"]
        if z["hand"] and not hg and damals and abs((damals.get("stueck_min") or 0) - z["auto_stueck_min"]) > 0.05:
            hinweise.append(f"Die automatische Stückzeit hat sich seit der Vorgabe geändert: "
                            f"{bv.zeit_text(damals.get('stueck_min'))} → {bv.zeit_text(z['auto_stueck_min'])}.")
        if v["am"] and z["hand"]:
            hinweise.append(f"Vorgabe vom {v['am']}" + (f" ({v['von']})" if v["von"] else "") + ".")
        if self._fehler:
            hinweise.insert(0, f"<span style='color:{stil.umsetzen(stil.ROT)}'>{self._fehler}</span>")
        self.hinweis.setText(" ".join(hinweise))
        self.hinweis.setVisible(bool(hinweise))
        self.alles.setVisible(z["hand"] or abs(kf - 1) > 1e-9 or any(sc.values()))

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
        for n, f in self.schnell.items():
            t = f.text().replace("€", "").strip()
            try:
                out[n] = zahl_aus_text(t) if t else None
            except ValueError:
                raise bv.Fehler(f"„{f.text()}“ ist kein Betrag") from None
            if out[n] is not None and out[n] < 0:
                raise bv.Fehler("Betrag darf nicht negativ sein")
        out.update(satz_id=self.satz.currentData(), grund=self.grund.text().strip(), komplex_faktor=kf,
                   frei=self.frei.isChecked(),
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
        for f in list(self.felder.values()) + list(self.b_feld.values()) + [self.komplex, self.grund] \
                + list(self.schnell.values()):
            f.setModified(False)
        self.geaendert.emit(w)

    def _zuruecksetzen(self, n):
        self.felder[n].setText("")
        self._melden()

    def vorschlag_setzen(self, vs, uebernommen=False):
        """Zeitvorschlag aus vergleichbaren Baugruppen (bg_zeitlernen.vorschlag) zeigen; None blendet ihn aus."""
        self._vorschlag = vs
        self.vorschlag_w.setVisible(bool(vs))
        if not vs:
            return
        auto = (self.z or {}).get("auto_je_bg_min") or 0.0
        self.vorschlag_l.setText(
            f"<b>Zeitvorschlag aus vergleichbaren Baugruppen: {bv.zeit_text(vs['min'])}</b> je Baugruppe"
            f"<br>Automatisch berechnet: {bv.zeit_text(auto)} · vergleichbare Datensätze: {vs['n']}"
            + (" · <i>übernommen</i>" if uebernommen else ""))
        self.vorschlag_l.setToolTip(vs["text"])
        self.vorschlag_k.setEnabled(not self.nur_lesen and not uebernommen)

    def pruef_setzen(self, gruende):
        """Hinweis, dass die Zeit von Hand geprüft werden sollte (bg_vorgabe.pruefen); leer blendet ihn aus."""
        self.pruef_w.setVisible(bool(gruende))
        if gruende:
            self.pruef_l.setText(f"<span style='color:{stil.umsetzen(stil.ORANGE)}'><b>Zeit von Hand prüfen:</b></span> "
                                 "die Baugruppe hat sich seit der Vorgabe geändert (" + "; ".join(gruende)
                                 + "). Die Zeit von Hand bleibt, bis sie geändert oder bestätigt wird.")

    def erfahrung_setzen(self, text):
        self.erfahrung.setText(text or "")
        self.erfahrung.setVisible(bool(text))

    def alles_automatisch(self):
        for f in list(self.felder.values()) + list(self.b_feld.values()) + [self.komplex, self.grund] \
                + list(self.schnell.values()):
            f.setText("")
        for c in self.gruende.values():
            c.blockSignals(True)
            c.setChecked(False)
            c.blockSignals(False)
        self.satz.setCurrentIndex(0)
        self._melden()
