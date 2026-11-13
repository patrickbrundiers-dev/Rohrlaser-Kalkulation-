"""Seite „Auswertung“ der Aufträge (Plan Auftragsworkflow 13.11.2026, Paket 7). Zahlen aus auftrag_auswertung.py.

Oben der Zeitraum und Kacheln mit Durchlaufzeit, Termintreue, Ausschussquote, Produktivität (Soll ÷ Ist) und den
Kosten (kalkuliert gegen tatsächlich); darunter Reiter mit verspäteten Aufträgen, Zeit je Arbeitsgang und Kosten je
Auftrag. Doppelklick auf einen Auftrag zeigt ihn auf der Seite Aufträge. Recht: Bereich Auswertungen sehen.
"""
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from . import auftrag_auswertung as aw
from .auftrag_qs_seite import _datum, _tabelle, _zelle
from .kacheln import KachelZeile
from .stil import TEXT_GRAU

KACHELN = (
    ("abgeschlossen", "Fertige Aufträge", "Aufträge, die im Zeitraum fertiggestellt bzw. ausgeliefert wurden"),
    ("durchlauf", "Durchlaufzeit", "Mittlere Tage von der Übernahme bis zur Auslieferung (sonst bis Fertiggestellt)"),
    ("termintreue", "Termintreue", "Anteil der fertigen Aufträge mit Liefertermin, die bis zum Termin geliefert wurden"),
    ("ausschuss", "Ausschussquote", "Ausschuss ÷ (gut + Ausschuss) aus den Rückmeldungen im Zeitraum"),
    ("produktivitaet", "Produktivität", "Soll-Zeit ÷ Ist-Zeit der fertigen Arbeitsgänge im Zeitraum; über 100 % = "
                                        "schneller als geplant"),
    ("kosten", "Kosten Ist ÷ Kalkulation", "Tatsächliche (aus Ist-Zeiten und Ausschuss hochgerechnete) gegen "
                                           "kalkulierte Kosten der fertigen Aufträge"),
)
SPAET_SPALTEN = ("Auftrag", "Kunde", "Liefertermin", "Tage zu spät", "Status")
AG_SPALTEN = ("Arbeitsgang", "Rückmeldungen", "Gut", "Ausschuss", "Soll [h]", "Ist [h]", "Abweichung")
KOSTEN_SPALTEN = ("Auftrag", "Kunde", "Material €", "Fertigung kalk. €", "Fertigung Ist €", "Ausschuss €",
                  "Kalkuliert €", "Tatsächlich €", "Abweichung")
ROT, GRUEN = "#B42318", "#1E6B34"


def _euro(x):
    from .ausgabe import euro_text
    return euro_text(x)


def _prozent(x, vorzeichen=False):
    if x is None:
        return "–"
    return (f"{x * 100:+.0f} %" if vorzeichen else f"{x * 100:.0f} %").replace("-", "−")


def _farbe(verhaeltnis, besser_hoch):
    """Grün, wenn besser als geplant, rot ab 10 % schlechter, sonst neutral."""
    if verhaeltnis is None:
        return ""
    gut = verhaeltnis >= 1 if besser_hoch else verhaeltnis <= 1
    schlecht = verhaeltnis < 0.9 if besser_hoch else verhaeltnis > 1.1
    return f"color: {GRUEN};" if gut else f"color: {ROT};" if schlecht else ""


def _h(minuten):
    return f"{minuten / 60:.1f}".replace(".", ",")


class AuswertungSeite(QWidget):
    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.werte = {}
        lay = QVBoxLayout(self)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("<b>Auswertung der Aufträge</b>"))
        oben.addSpacing(16)
        oben.addWidget(QLabel("Zeitraum"))
        self.zeitraum = QComboBox()
        for k, t in aw.ZEITRAEUME:
            self.zeitraum.addItem(t, k)
        self.zeitraum.setCurrentIndex(1)
        self.zeitraum.currentIndexChanged.connect(lambda _: self.neu_laden())
        oben.addWidget(self.zeitraum)
        oben.addStretch(1)
        lay.addLayout(oben)
        self.kacheln = KachelZeile(KACHELN)
        self.kacheln.geklickt.connect(self._kachel)
        lay.addWidget(self.kacheln)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet(f"color: {TEXT_GRAU};")
        lay.addWidget(self.hinweis)
        self.reiter = QTabWidget()
        self.spaet = _tabelle(SPAET_SPALTEN)
        self.gaenge = _tabelle(AG_SPALTEN, dehnen=0)
        self.kosten = _tabelle(KOSTEN_SPALTEN)
        for t in (self.spaet, self.kosten):
            t.doubleClicked.connect(lambda i, t=t: self._oeffnen(t, i.row()))
        self.reiter.addTab(self.spaet, "Verspätete Aufträge")
        self.reiter.addTab(self.gaenge, "Zeit je Arbeitsgang")
        self.reiter.addTab(self.kosten, "Kosten je Auftrag")
        lay.addWidget(self.reiter, 1)

    def showEvent(self, e):
        super().showEvent(e)
        self.neu_laden()

    def zeitraum_setzen(self, schluessel):
        self.zeitraum.setCurrentIndex(max(0, self.zeitraum.findData(schluessel)))
        self.neu_laden()

    def neu_laden(self):
        von, bis = aw.zeitraum(self.zeitraum.currentData())
        w = self.werte = aw.auswertung(self.db, von, bis)
        k = self.kacheln.kacheln
        k["abgeschlossen"].setzen(str(w["abgeschlossen"]), f"{len(w['verspaetet'])} verspätet" if w["verspaetet"]
                                  else "keine verspätet")
        d = w["durchlauf_tage"]
        k["durchlauf"].setzen(f"{d:.1f} Tage".replace(".", ",") if d is not None else "–")
        k["termintreue"].setzen(_prozent(w["termintreue"]), "pünktlich geliefert" if w["termintreue"] is not None
                                else "noch keine mit Termin")
        k["ausschuss"].setzen(_prozent(w["ausschussquote"]) if w["ausschussquote"] is None
                              else f"{w['ausschussquote'] * 100:.1f} %".replace(".", ","),
                              f"{w['ausschuss']:g} von {w['gut'] + w['ausschuss']:g} Teilen" if w["gut"] + w["ausschuss"]
                              else "")
        p = w["produktivitaet"]
        k["produktivitaet"].setzen(_prozent(p), f"Soll {_h(w['soll_min'])} h, Ist {_h(w['ist_min'])} h" if p else "")
        k["produktivitaet"].wert.setStyleSheet(_farbe(p, besser_hoch=True))
        q = w["ist_summe"] / w["kalk_summe"] if w["kalk_summe"] > 0 else None
        k["kosten"].setzen(_prozent(q), f"{_euro(w['ist_summe'])} € von {_euro(w['kalk_summe'])} €" if q else "")
        k["kosten"].wert.setStyleSheet(_farbe(q, besser_hoch=False))
        self.hinweis.setText("Noch keine Rückmeldungen oder fertigen Aufträge im Zeitraum." if not (
            w["abgeschlossen"] or w["arbeitsgaenge"] or w["verspaetet"]) else
            "Tatsächliche Kosten: Material wie kalkuliert, Fertigung mit Ist-Zeit ÷ Soll-Zeit hochgerechnet, dazu der "
            "Ausschuss mit den Selbstkosten je Teil.")
        self._spaet(w["verspaetet"])
        self._gaenge(w["arbeitsgaenge"])
        self._kosten(w["kosten"])

    def _spaet(self, liste):
        t = self.spaet
        t.setRowCount(len(liste))
        for r, v in enumerate(liste):
            _zelle(t, r, 0, v["nummer"], daten=v["uid"])
            _zelle(t, r, 1, v["kunde"])
            _zelle(t, r, 2, _datum(v["liefertermin"]))
            _zelle(t, r, 3, v["tage"], rechts=True, farbe=ROT if v["offen"] else None)
            _zelle(t, r, 4, v["status"] + (" (offen)" if v["offen"] else ""))

    def _gaenge(self, liste):
        t = self.gaenge
        t.setRowCount(len(liste))
        for r, g in enumerate(liste):
            _zelle(t, r, 0, g["name"])
            _zelle(t, r, 1, g["anzahl"], rechts=True)
            _zelle(t, r, 2, f"{g['gut']:g}", rechts=True)
            _zelle(t, r, 3, f"{g['ausschuss']:g}", rechts=True, farbe=ROT if g["ausschuss"] else None)
            _zelle(t, r, 4, _h(g["soll"]) if g["soll"] else "–", rechts=True)
            _zelle(t, r, 5, _h(g["ist"]) if g["ist"] else "–", rechts=True)
            a = g["abweichung"]
            _zelle(t, r, 6, _prozent(a, True), rechts=True,
                   farbe=None if a is None or abs(a) < 0.1 else (ROT if a > 0 else GRUEN))

    def _kosten(self, liste):
        t = self.kosten
        t.setRowCount(len(liste))
        for r, c in enumerate(liste):
            _zelle(t, r, 0, c["nummer"], daten=c["uid"])
            _zelle(t, r, 1, c["kunde"])
            for i, f in enumerate(("material", "fertigung_kalk", "fertigung_ist", "ausschuss", "kalk", "ist"), 2):
                _zelle(t, r, i, _euro(c[f]), rechts=True)
            a = c["abweichung"]
            _zelle(t, r, 8, _prozent(a, True) + ("" if c["mit_zeiten"] else " (ohne Ist-Zeiten)"), rechts=True,
                   farbe=None if a is None or abs(a) < 0.05 else (ROT if a > 0 else GRUEN))

    def _kachel(self, schluessel):
        self.reiter.setCurrentIndex({"produktivitaet": 1, "kosten": 2}.get(schluessel, 0))

    def _oeffnen(self, t, r):
        it = t.item(r, 0)
        uid = it.data(256) if it is not None else None
        if uid:
            self.f.auftrag_zeigen(uid)
