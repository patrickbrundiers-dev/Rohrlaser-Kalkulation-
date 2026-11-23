"""Nesting-Arbeitsplatz (Patrick 23.11.2026, Master-Auftrag Verschachtelung): je Abmessung die Strategien A … E
gegen den bisherigen Plan, maßstäbliches Bild aller Stangen untereinander und Belegung von Hand.

- Oben: Abmessung wählen, Empfehlung mit Begründung.
- Tabelle: bisher und A … E mit Stangen je Länge, eingekaufter Länge, Einkauf und kalkulatorischen Kosten,
  Teilelänge, Schnittverlusten, verwertbarem Rest, Verschnitt, Ausnutzung, € je Teil, Beladungen, Belegungen,
  Einkauf gegenüber bisher und Rechenzeit (nesting_vergleich.SPALTEN).
- Bild (NestingBild): je Stange ein Balken in Länge der Stange; Endbeschnitt grau, Teile in der Farbe ihrer Position,
  Schnitte als dunkle Linien, verwertbarer Rest grün, nicht verwertbarer Verschnitt rot schraffiert, Greiferrest
  dunkelgrau. Klick auf ein Teil wählt es, Klick auf eine andere Stange setzt es dorthin (geprüft, eine
  überbelegte Stange ist nicht möglich), Klick rechts neben die Stangen legt es auf eine neue Stange. Die Kennzahlen
  rechnen sofort neu; „Rückgängig“ nimmt den letzten Schritt zurück.
- Je Position: Materialkosten (nach Teilelänge verteilt) des gewählten Plans.
- Übernehmen: „Strategie übernehmen“ (je Abmessung gespeichert, rechnet bei jeder Mengenänderung neu),
  „Belegung von Hand übernehmen“ (diese Stangen bleiben fest, neue Teile plant Strategie B dazu), „Wie bisher“.
Der Dialog ändert das Angebot nicht selbst: das Ergebnis steht in self.wahl ({Abmessung: Strategie}) und
self.hand ({Abmessung: Stangen}); die Angebotsseite speichert und optimiert neu.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import nesting as ne, nesting_vergleich as nv, optimierung as opt, rechnen, stil


def segmente(g, laenge, folge, min_rest=0.0, min_nutz=ne.REST_MIN_NUTZ):
    """Teile einer Stange für das Bild: [(art, von, bis, Teil oder None)] mit art 'end' | 'teil' | 'schnitt' |
    'rest' (verwertbar) | 'abfall' | 'greif'. Positionen in mm ab Stangenanfang, wie verbrauch rechnet."""
    h = opt.replace(g, stange=laenge, teile=[])
    out = [("end", 0.0, g.endbeschnitt, None)]
    pos, vorher = g.endbeschnitt, None
    for t, r in folge:
        if vorher is not None:
            tr = opt.trennung_teile(h, vorher[0], vorher[1], t, r)
            if tr > 0:
                out.append(("schnitt", pos, pos + tr, None))
            pos += tr
        out.append(("teil", pos, pos + t.laenge, t))
        pos += t.laenge
        vorher = (t, r)
    out.append(("schnitt", pos, pos + g.kerf, None))
    pos += g.kerf
    hinten = opt.hinten(h, folge)
    rest = laenge - pos
    art = "rest" if ne.verwertbar(g, rest, min_rest, min_nutz) else "abfall"
    if rest - hinten > 0:
        out.append((art, pos, laenge - hinten, None))
    out.append(("greif" if art == "abfall" else art, max(pos, laenge - hinten), laenge, None))
    return out


class NestingBild(QWidget):
    """Maßstäbliches Bild der Stangen eines Plans. Signale: teil_gewaehlt(Stange, Teil), ziel(Stange; -1 = neue
    Stange)."""
    ZEILE, LINKS, RECHTS, OBEN = 26, 70, 90, 6
    teil_gewaehlt = Signal(int, int)
    ziel = Signal(int)

    def __init__(self):
        super().__init__()
        self.g, self.stangen, self.auswahl = None, [], None
        self.min_rest, self.min_nutz = 0.0, ne.REST_MIN_NUTZ
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setToolTip("Klick auf ein Teil: wählen · Klick auf eine andere Stange: Teil dorthin · Klick rechts neben "
                        "die Stangen: Teil auf eine neue Stange")

    def setzen(self, g, stangen, min_rest=0.0, min_nutz=ne.REST_MIN_NUTZ):
        self.g, self.stangen, self.auswahl = g, list(stangen), None
        self.min_rest, self.min_nutz = min_rest, min_nutz
        self.setMinimumHeight(self.OBEN * 2 + self.ZEILE * max(len(self.stangen), 1))
        self.update()

    def _skala(self):
        lang = max((laenge for laenge, _, _ in self.stangen), default=1)
        return max(self.width() - self.LINKS - self.RECHTS, 50) / lang

    def _farbe(self, t):
        return QColor(stil.TEIL_FARBEN[(t.zeile - rechnen.ZEILE0) % len(stil.TEIL_FARBEN)])

    def paintEvent(self, _):
        if self.g is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        sk = self._skala()
        text = QColor(stil.farbe("#222222"))
        for i, (laenge, folge, rest) in enumerate(self.stangen):
            y = self.OBEN + i * self.ZEILE
            hoehe = self.ZEILE - 8
            p.setPen(QPen(text))
            p.drawText(QRectF(0, y, self.LINKS - 6, hoehe), Qt.AlignRight | Qt.AlignVCenter,
                       f"{i + 1}" + (f" {rest}" if rest else ""))
            n_teil = 0
            for art, von, bis, t in segmente(self.g, laenge, folge, self.min_rest, self.min_nutz):
                r = QRectF(self.LINKS + von * sk, y, max((bis - von) * sk, 1), hoehe)
                if art == "teil":
                    gew = self.auswahl == (i, n_teil)
                    p.fillRect(r, QColor("#FF7F0E") if gew else self._farbe(t))
                    p.setPen(QPen(QColor("#ffffff")))
                    if r.width() > 34:
                        p.drawText(r, Qt.AlignCenter, rechnen.zahl(t.laenge, 0))
                    n_teil += 1
                elif art == "schnitt":
                    p.fillRect(QRectF(r.x(), r.y(), max(r.width(), 1.5), r.height()), QColor("#222222"))
                elif art == "rest":
                    p.fillRect(r, QColor("#B9E4C0"))
                elif art == "abfall":
                    p.fillRect(r, QBrush(QColor("#E15759"), Qt.BDiagPattern))
                elif art == "greif":
                    p.fillRect(r, QColor("#7F7F7F"))
                else:
                    p.fillRect(r, QColor("#BBBBBB"))
            p.setPen(QPen(text))
            p.drawRect(QRectF(self.LINKS, y, laenge * sk, hoehe))
            p.drawText(QRectF(self.LINKS + laenge * sk + 4, y, self.RECHTS - 6, hoehe), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{rechnen.m_text(laenge)} m")
        p.end()

    def treffer(self, punkt):
        """(Stange, Teil oder None) unter dem Punkt; Stange -1 = rechts neben den Stangen (neue Stange)."""
        if self.g is None:
            return None, None
        i = int((punkt.y() - self.OBEN) // self.ZEILE)
        if not (0 <= i < len(self.stangen)):
            return None, None
        sk = self._skala()
        x = (punkt.x() - self.LINKS) / sk
        laenge, folge, _ = self.stangen[i]
        if x > laenge + (self.RECHTS * 0.5) / sk:
            return -1, None
        n = 0
        for art, von, bis, _ in segmente(self.g, laenge, folge):
            if art == "teil":
                if von <= x <= bis:
                    return i, n
                n += 1
        return i, None

    def mousePressEvent(self, e):
        i, n = self.treffer(QPointF(e.position()))
        if i is None:
            return
        if self.auswahl is not None and (n is None or i != self.auswahl[0]):
            self.ziel.emit(i)
            return
        if n is not None:
            self.auswahl = (i, n)
            self.teil_gewaehlt.emit(i, n)
            self.update()


class NestingDialog(QDialog):
    """vergleich: Ergebnis von nesting_vergleich.vergleich; positionen: Positionen des Angebots (Bezug je Teil)."""

    def __init__(self, vergleich, positionen, parent=None, nur_lesen=False):
        super().__init__(parent)
        self.setWindowTitle("Nesting-Arbeitsplatz")
        self.resize(1280, 820)
        self.vergleich, self.positionen = vergleich, positionen
        self.wahl, self.hand = {}, {}           # Ergebnis: {Abmessung: Strategie}, {Abmessung: Stangen}
        self.hand_stangen, self.verlauf = None, []
        self.abm = QComboBox()
        for v in vergleich:
            self.abm.addItem(v["titel"])
        self.abm.currentIndexChanged.connect(lambda _: self.gruppe_zeigen())
        self.empf = QLabel("")
        self.empf.setWordWrap(True)
        self.tabelle = QTableWidget(0, len(nv.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels([t for _, t in nv.SPALTEN])
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.itemSelectionChanged.connect(self.zeile_gewaehlt)
        self.bild = NestingBild()
        self.bild.teil_gewaehlt.connect(self.teil_gewaehlt)
        self.bild.ziel.connect(self.ziel_gewaehlt)
        rahmen = QScrollArea()
        rahmen.setWidgetResizable(True)
        rahmen.setWidget(self.bild)
        self.hinweis = QLabel("")
        self.hinweis.setWordWrap(True)
        self.kennzahlen = QLabel("")
        self.kennzahlen.setWordWrap(True)
        self.ki = QLabel("")
        self.ki.setWordWrap(True)
        self.pos_tabelle = QTableWidget(0, 3)
        self.pos_tabelle.setHorizontalHeaderLabels(["Position", "Teilelänge [m]", "Material [€]"])
        self.pos_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pos_tabelle.verticalHeader().setVisible(False)
        self.pos_tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.pos_tabelle.setMaximumWidth(330)
        self.k_strategie = QPushButton("Strategie übernehmen")
        self.k_strategie.setObjectName("primaer")
        self.k_strategie.clicked.connect(lambda: self.strategie_uebernehmen())
        self.k_hand = QPushButton("Belegung von Hand übernehmen")
        self.k_hand.clicked.connect(lambda: self.hand_uebernehmen())
        self.k_bisher = QPushButton("Wie bisher rechnen")
        self.k_bisher.clicked.connect(lambda: self.bisher_uebernehmen())
        self.k_zurueck = QPushButton("Rückgängig")
        self.k_zurueck.clicked.connect(lambda: self.rueckgaengig())
        self.k_ok = QPushButton("Übernehmen und neu optimieren")
        self.k_ok.clicked.connect(self.accept)
        k_zu = QPushButton("Schließen")
        k_zu.clicked.connect(self.reject)
        for k in (self.k_strategie, self.k_hand, self.k_bisher):
            k.setEnabled(not nur_lesen)
        self.k_ok.setEnabled(False)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Abmessung:"))
        oben.addWidget(self.abm, 1)
        unten = QHBoxLayout()
        for k in (self.k_strategie, self.k_hand, self.k_zurueck, self.k_bisher):
            unten.addWidget(k)
        unten.addStretch(1)
        unten.addWidget(self.k_ok)
        unten.addWidget(k_zu)
        mitte = QWidget()
        ml = QHBoxLayout(mitte)
        ml.setContentsMargins(0, 0, 0, 0)
        links = QVBoxLayout()
        links.addWidget(rahmen, 1)
        links.addWidget(self.kennzahlen)
        links.addWidget(self.hinweis)
        ml.addLayout(links, 1)
        ml.addWidget(self.pos_tabelle)
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(self.tabelle)
        teiler.addWidget(mitte)
        teiler.setSizes([260, 520])
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.empf)
        lay.addWidget(self.ki)
        lay.addWidget(teiler, 1)
        lay.addLayout(unten)
        if vergleich:
            self.gruppe_zeigen()
        else:
            self.empf.setText("Keine Abmessung zum Verschachteln (Kundenmaterial, Muster und von Hand vorgegebene "
                              "Stangen rechnen wie bisher).")

    # -------------------------------------------------------------- Anzeige
    def aktuell(self):
        i = self.abm.currentIndex()
        return self.vergleich[i] if 0 <= i < len(self.vergleich) else None

    def gruppe_zeigen(self):
        v = self.aktuell()
        if v is None:
            return
        self.hand_stangen, self.verlauf = None, []
        s, text = v["empfehlung"]
        gew = self.wahl.get(v["schluessel"], v["gewaehlt"]) or "bisher"
        self.empf.setText(f"<b>Empfehlung:</b> {text}<br>Gewählt für diese Abmessung: <b>{gew}</b>")
        from . import nesting_hinweise
        hw = nesting_hinweise.hinweise(v)
        self.ki.setText(("<b>Hinweise (lokal, nur Vorschläge):</b> " + " · ".join(hw)) if hw else "")
        t = self.tabelle
        t.blockSignals(True)
        t.setRowCount(0)
        for z in v["zeilen"]:
            r = t.rowCount()
            t.insertRow(r)
            for c, (schl, _) in enumerate(nv.SPALTEN):
                it = QTableWidgetItem(nv.text(z, schl))
                if z["strategie"] == s:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                t.setItem(r, c, it)
        t.blockSignals(False)
        ziel = next((r for r, z in enumerate(v["zeilen"]) if z["strategie"] == s), 0)
        t.selectRow(ziel)
        self.zeile_gewaehlt()

    def strategie_der_zeile(self):
        v = self.aktuell()
        r = self.tabelle.currentRow()
        return v["zeilen"][r]["strategie"] if v and 0 <= r < len(v["zeilen"]) else None

    def plan_der_zeile(self):
        v = self.aktuell()
        s = self.strategie_der_zeile()
        return v["plaene"].get(s) if v and s else None

    def zeile_gewaehlt(self):
        v, p = self.aktuell(), self.plan_der_zeile()
        if v is None:
            return
        self.hand_stangen, self.verlauf = None, []
        zs = v["zuschnitt"].get(self.strategie_der_zeile())
        self.hinweis.setText("Mit Zuschnitt beim Lieferanten (ganze Lieferstange bezahlt) ist diese Strategie "
                             "günstiger; das Bild zeigt die Stangen ohne Zuschnitt. Übernehmen plant wie in der Zeile."
                             if zs else "")
        self._bild(p.stangen if p else [])
        self.k_hand.setEnabled(False)

    def _bild(self, stangen):
        v = self.aktuell()
        d = v["daten"]
        self.bild.setzen(v["gruppe"], stangen, d["min_rest"], d["min_nutz"])
        g = v["gruppe"]
        if not stangen:
            self.kennzahlen.setText("")
            self.pos_tabelle.setRowCount(0)
            return
        w = ne.kennzahlen(g, stangen, [], ne._laengen_fuer(g, d["laengen"]) or [ne.Laenge(g.stange)], d["reste"],
                          d["je_beladung"], d["min_rest"], d["min_nutz"])
        z = rechnen.zahl
        self.kennzahlen.setText(
            f"{w['stangen']} Stangen ({ne.laengen_text(w['je_laenge'])}), eingekauft {z(w['gekauft_mm'] / 1000)} m, "
            f"Einkauf {z(w['einkauf']) if w['einkauf'] is not None else 'Preis fehlt'} €, Teile "
            f"{z(w['teile_mm'] / 1000)} m, Schnitt {z(w['schnitt_mm'], 0)} mm, verwertbarer Rest "
            f"{z(w['rest_verwertbar_mm'], 0)} mm, Verschnitt {z(w['verschnitt_mm'], 0)} mm, Ausnutzung "
            f"{z(100 * w['ausnutzung'], 1)} %. Bilanz: Teile + Schnitt + Rest + Verschnitt = "
            f"{z(w['gesamt_mm'], 0)} mm (geprüft).")
        pt = self.pos_tabelle
        pt.setRowCount(0)
        for zeile, mm in w["mm_position"].items():
            r = pt.rowCount()
            pt.insertRow(r)
            p = self.positionen[zeile - rechnen.ZEILE0]
            eur = w["eur_position"].get(zeile)
            for c, txt in enumerate((f"Pos. {p.get('pos')}", z(mm / 1000), z(eur) if eur is not None else "—")):
                pt.setItem(r, c, QTableWidgetItem(txt))

    # -------------------------------------------------------------- Belegung von Hand
    def teil_gewaehlt(self, i, n):
        laenge, folge, _ = self.bild.stangen[i]
        t = folge[n][0]
        p = self.positionen[t.zeile - rechnen.ZEILE0]
        self.hinweis.setText(f"Gewählt: Pos. {p.get('pos')} {p.get('artikel') or ''}, {rechnen.zahl(t.laenge, 1)} mm "
                             f"auf Stange {i + 1}. Jetzt auf eine andere Stange klicken (rechts daneben = neue Stange).")

    def ziel_gewaehlt(self, nach):
        v = self.aktuell()
        if v is None or self.bild.auswahl is None:
            return
        von, n = self.bild.auswahl
        neu, fehler = nv.verschieben(v["gruppe"], self.bild.stangen, von, n, None if nach < 0 else nach, v["daten"])
        if fehler:
            self.hinweis.setText(fehler)
            self.bild.auswahl = None
            self.bild.update()
            return
        self.verlauf.append(self.bild.stangen)
        self.hand_stangen = neu
        self._bild(neu)
        self.hinweis.setText("Teil umgesetzt und geprüft (keine Stange überbelegt). „Belegung von Hand übernehmen“ "
                             "speichert diese Stangen für die Abmessung.")
        self.k_hand.setEnabled(self.k_strategie.isEnabled())

    def rueckgaengig(self):
        if not self.verlauf:
            return
        alt = self.verlauf.pop()
        self.hand_stangen = alt if self.verlauf else None
        self._bild(alt)
        self.k_hand.setEnabled(bool(self.verlauf) and self.k_strategie.isEnabled())

    # -------------------------------------------------------------- Übernehmen
    def _gemerkt(self, text):
        self.k_ok.setEnabled(True)
        self.hinweis.setText(text + " Mit „Übernehmen und neu optimieren“ gilt es im Angebot.")
        self.gruppe_zeigen()

    def strategie_uebernehmen(self):
        v, s = self.aktuell(), self.strategie_der_zeile()
        if v is None or s is None:
            return None
        self.wahl[v["schluessel"]] = "bisher" if s == nv.BISHER else s
        self.hand[v["schluessel"]] = None
        self._gemerkt(f"{v['titel']}: Strategie {self.wahl[v['schluessel']]} vorgemerkt.")
        return s

    def hand_uebernehmen(self):
        v = self.aktuell()
        if v is None or not self.hand_stangen:
            return None
        self.hand[v["schluessel"]] = nv.hand_aus_plan(ne.Plan("Hand", self.hand_stangen), self.positionen)
        self._gemerkt(f"{v['titel']}: Belegung von Hand ({len(self.hand_stangen)} Stangen) vorgemerkt.")
        return self.hand[v["schluessel"]]

    def bisher_uebernehmen(self):
        v = self.aktuell()
        if v is None:
            return None
        self.wahl[v["schluessel"]] = "bisher"
        self.hand[v["schluessel"]] = None
        self._gemerkt(f"{v['titel']}: wieder wie bisher.")
        return True
