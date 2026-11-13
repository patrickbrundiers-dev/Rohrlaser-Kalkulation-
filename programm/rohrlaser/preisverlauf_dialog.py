"""Fenster „Preisverlauf“ (MAT-008) und „EK-Verlauf“ (PART-013), Roadmap Kalkulation Phase 2 Paket 2b: Stufenkurve
der Preisstände, Liste mit Datum und Durchschnitt bzw. Änderung über 3/6/12 Monate. Nur Anzeige."""
import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHeaderView, QLabel,
                               QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import preisverlauf as pv
from .stammdaten import zahl_als_text as zahl


class Kurve(QWidget):
    """Stufenkurve [(date, Preis)]: jeder Preis gilt bis zum nächsten Stand, die letzte Stufe bis heute."""

    def __init__(self, punkte=(), einheit="", parent=None):
        super().__init__(parent)
        self.punkte, self.einheit = list(punkte), einheit
        self.setMinimumSize(520, 190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, punkte, einheit=""):
        self.punkte, self.einheit = list(punkte), einheit
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        text = pal.color(pal.ColorRole.WindowText)
        gitter = QColor(text)
        gitter.setAlpha(40)
        r = QRectF(self.rect()).adjusted(64, 12, -16, -28)
        if not self.punkte:
            p.setPen(text)
            p.drawText(self.rect(), Qt.AlignCenter, "Noch kein Preisstand")
            return
        heute = max(datetime.date.today(), self.punkte[-1][0])
        start = self.punkte[0][0]
        if (heute - start).days < 30:
            start = heute - datetime.timedelta(days=30)
        werte = [w for _, w in self.punkte]
        lo, hi = min(werte), max(werte)
        if hi - lo < 1e-9:
            lo, hi = lo * 0.9, hi * 1.1 if hi else 1.0
        rand = (hi - lo) * 0.1
        lo, hi = lo - rand, hi + rand
        tage = max((heute - start).days, 1)

        def x(d):
            return r.left() + (d - start).days / tage * r.width()

        def y(w):
            return r.bottom() - (w - lo) / (hi - lo) * r.height()
        p.setPen(QPen(gitter, 1))
        for i in range(5):
            w = lo + (hi - lo) * i / 4
            p.drawLine(QPointF(r.left(), y(w)), QPointF(r.right(), y(w)))
            p.setPen(text)
            p.drawText(QRectF(0, y(w) - 8, r.left() - 6, 16), Qt.AlignRight | Qt.AlignVCenter, zahl(w, 2))
            p.setPen(QPen(gitter, 1))
        p.setPen(text)
        p.drawText(QRectF(r.left(), r.bottom() + 6, 100, 16), Qt.AlignLeft, start.strftime("%d.%m.%Y"))
        p.drawText(QRectF(r.right() - 100, r.bottom() + 6, 100, 16), Qt.AlignRight, heute.strftime("%d.%m.%Y"))
        weg = QPainterPath()
        for i, (d, w) in enumerate(self.punkte):
            bis = self.punkte[i + 1][0] if i + 1 < len(self.punkte) else heute
            if i == 0:
                weg.moveTo(x(max(d, start)), y(w))
            else:
                weg.lineTo(x(d), y(w))
            weg.lineTo(x(bis), y(w))
        akzent = pal.color(pal.ColorRole.Highlight)
        p.setPen(QPen(akzent, 2))
        p.drawPath(weg)
        p.setBrush(akzent)
        for d, w in self.punkte:
            p.drawEllipse(QPointF(x(d), y(w)), 3, 3)
        if self.einheit:
            p.setPen(text)
            p.drawText(QRectF(r.left(), 0, r.width(), 12), Qt.AlignLeft, self.einheit)


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(list(spalten))
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(len(spalten) - 1, QHeaderView.Stretch)
    t.setMinimumHeight(160)
    return t


def _fuellen(t, zeilen):
    t.setRowCount(len(zeilen))
    for r, z in enumerate(zeilen):
        for c, w in enumerate(z):
            t.setItem(r, c, QTableWidgetItem("" if w is None else str(w)))


def _datum(t):
    try:
        return datetime.date.fromisoformat(str(t)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(t or "")


def kennzahl_text(punkte, einheit):
    teile = []
    for kz in pv.kennzahlen(punkte):
        if kz["mittel"] is None:
            continue
        aend = (f", {'+' if kz['aenderung_pct'] >= 0 else '−'}{zahl(abs(kz['aenderung_pct']), 1)} % zu damals"
                if kz["aenderung_pct"] is not None else "")
        teile.append(f"{kz['monate']} Monate: Ø {zahl(kz['mittel'], 2)} {einheit}{aend}")
    return " · ".join(teile) or "Noch zu wenig Verlauf für Durchschnitte."


class PreisverlaufDialog(QDialog):
    """MAT-008: Auswahl Werkstoff/Abmessung (alle Schlüssel im Verlauf), Kurve, Liste, Durchschnitte."""

    def __init__(self, db, parent=None, auswahl=None):
        super().__init__(parent)
        self.setWindowTitle("Preisverlauf")
        self.db = db
        alle = db.preisverlauf()
        schl = {}
        for e in alle:
            schl.setdefault((e["art"], e["profil_id"], e["werkstoff_id"], e["laenge"]), e)
        self.schluessel = sorted(schl, key=lambda s: (str(s[1] or ""), str(s[2] or ""), s[0], s[3] or 0))
        self.alle = alle
        lay = QVBoxLayout(self)
        hinweis = QLabel("Jeder Stand der Materialpreise mit Datum („Gültig ab“, sonst Tag der Änderung). Gerechnet "
                         "wird weiter mit der aktuellen Zeile; festgeschriebene Angebote behalten ihre Preise.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        self.wahl = QComboBox()
        for s in self.schluessel:
            self.wahl.addItem(pv.bezeichnung(schl[s]), s)
        lay.addWidget(self.wahl)
        self.kurve = Kurve()
        lay.addWidget(self.kurve)
        self.kennzahlen = QLabel()
        self.kennzahlen.setWordWrap(True)
        lay.addWidget(self.kennzahlen)
        self.tabelle = _tabelle(("Gültig ab", "Preisbasis", "Preis", "Lieferant", "Eingetragen"))
        lay.addWidget(self.tabelle)
        k = QDialogButtonBox(QDialogButtonBox.Close)
        k.rejected.connect(self.reject)
        lay.addWidget(k)
        self.wahl.currentIndexChanged.connect(self.anzeigen)
        if auswahl in self.schluessel:          # findData vergleicht Tupel nicht zuverlässig
            self.wahl.setCurrentIndex(self.schluessel.index(auswahl))
        self.anzeigen()
        self.resize(760, 560)

    def anzeigen(self, *_):
        i = self.wahl.currentIndex()
        s = self.schluessel[i] if 0 <= i < len(self.schluessel) else None
        eintr = [e for e in self.alle if (e["art"], e["profil_id"], e["werkstoff_id"], e["laenge"]) == s] if s else []
        punkte = pv.reihe(eintr)
        einheit = (eintr[-1].get("basis") or "") if eintr else ""
        self.kurve.setzen(punkte, einheit)
        self.kennzahlen.setText(kennzahl_text(punkte, einheit) if punkte else "")
        _fuellen(self.tabelle, [(_datum(e["datum"]), e.get("basis"), zahl(e["preis"], 2), e.get("lieferant"),
                                 _datum(e.get("zeit"))) for e in reversed(eintr)])


class EkVerlaufDialog(QDialog):
    """PART-013: EK der ersten Staffel je Artikel und Lieferant aus dem Protokoll der Preisänderungen."""

    def __init__(self, db, parent=None, artikel_id=None, grenze=0.0):
        super().__init__(parent)
        self.setWindowTitle("EK-Verlauf")
        self.verlauf = pv.ek_verlauf(db.zukauf_historie())
        self.grenze = grenze
        lay = QVBoxLayout(self)
        hinweis = QLabel("Einkaufspreis der ersten Staffel je Lieferant aus den Preisänderungen"
                         + (f"; Sprünge über {zahl(grenze, 0)} % sind markiert." if grenze else
                            "; Hinweis bei Preissprung: Einstellung „Zukauf: Hinweis bei EK-Preissprung über [%]“."))
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        self.wahl = QComboBox()
        for (aid, lief), r in sorted(self.verlauf.items(), key=lambda x: (x[1][-1]["artikel"], x[0][1])):
            self.wahl.addItem(r[-1]["artikel"] + (f" – {lief}" if lief else ""), (aid, lief))
        lay.addWidget(self.wahl)
        self.kurve = Kurve()
        lay.addWidget(self.kurve)
        self.kennzahlen = QLabel()
        self.kennzahlen.setWordWrap(True)
        lay.addWidget(self.kennzahlen)
        self.tabelle = _tabelle(("Datum", "Alt", "Neu", "Änderung", "Bemerkung"))
        lay.addWidget(self.tabelle)
        k = QDialogButtonBox(QDialogButtonBox.Close)
        k.rejected.connect(self.reject)
        lay.addWidget(k)
        self.wahl.currentIndexChanged.connect(self.anzeigen)
        if artikel_id is not None:
            for i in range(self.wahl.count()):
                if self.wahl.itemData(i)[0] == artikel_id:
                    self.wahl.setCurrentIndex(i)
                    break
        self.anzeigen()
        self.resize(760, 560)

    def anzeigen(self, *_):
        r = self.verlauf.get(self.wahl.currentData()) or []
        punkte = sorted({d: e["preis"] for e in r for d in [pv._datum(e["datum"])] if d}.items())
        self.kurve.setzen(punkte, "€ (erste Staffel)")
        self.kennzahlen.setText(kennzahl_text(punkte, "€") if punkte else "")
        zeilen = []
        for e in reversed(r):
            pct = (e["preis"] / e["alt"] - 1) * 100 if e.get("alt") else None
            sprung = pct is not None and self.grenze and abs(pct) > self.grenze
            zeilen.append((_datum(e["datum"]), zahl(e["alt"], 2) if e.get("alt") else "", zahl(e["preis"], 2),
                           ("" if pct is None else f"{'+' if pct >= 0 else '−'}{zahl(abs(pct), 1)} %")
                           + (" ⚠ Preissprung" if sprung else ""), e.get("bemerkung")))
        _fuellen(self.tabelle, zeilen)
