"""Fenster rund um die Zeit von Hand der Schweißbaugruppe (Editor 2.0, 19.11.2026): Protokoll der Änderungen,
vergleichbare Baugruppen eines Zeitvorschlags und die Auswertung aller Zeiten von Hand mit Grafik
(bg_zeitlernen.auswertung). Reine Anzeige; in der Auswertung lässt sich ein Datensatz fürs Lernen sperren oder
wieder freigeben."""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                               QLabel, QListWidget, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem,
                               QTabWidget, QToolTip, QVBoxLayout, QWidget)

from . import bg_vorgabe as bv
from . import bg_zeitlernen as zl
from . import stil

FARBE_MEHR, FARBE_WENIGER, FARBE_REIHE = "#C2571A", "#2F6FB3", "#2F6FB3"     # mehr Zeit warm, weniger kühl


def _pct(f):
    w = (f - 1) * 100
    return ("+" if w >= 0 else "−") + f"{abs(w):.0f} %"


def _zelle(text, rechts=False, daten=None):
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if daten is not None:
        it.setData(Qt.UserRole, daten)
    return it


def _tabelle(titel):
    t = QTableWidget(0, len(titel))
    t.setHorizontalHeaderLabels(titel)
    t.verticalHeader().hide()
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


class ProtokollDialog(QDialog):
    def __init__(self, parent, bg):
        super().__init__(parent)
        self.setWindowTitle("Zeit von Hand: Protokoll")
        self.resize(760, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Alle Änderungen der Zeit von Hand an dieser Baugruppe, neueste zuerst. Alte Stände "
                             "bleiben stehen, auch nach „Alles automatisch“."))
        self.liste = QListWidget()
        self.liste.setObjectName("zeit_protokoll_liste")
        self.liste.setWordWrap(True)
        self.liste.addItems(bv.protokoll_text(bg) or ["Noch keine Änderung."])
        lay.addWidget(self.liste)
        k = QDialogButtonBox(QDialogButtonBox.Close)
        k.rejected.connect(self.reject)
        lay.addWidget(k)


class VergleichDialog(QDialog):
    """Die vergleichbaren Baugruppen eines Zeitvorschlags (bg_zeitlernen.vorschlag)."""

    def __init__(self, parent, vs, z=None):
        super().__init__(parent)
        self.setWindowTitle("Vergleichbare Baugruppen")
        self.resize(900, 420)
        lay = QVBoxLayout(self)
        t = QLabel(vs["text"])
        t.setWordWrap(True)
        lay.addWidget(t)
        self.tab = _tabelle(["Angebot", "Baugruppe", "Art", "Ähnlich", "Teile", "Naht [m]", "Gewicht [kg]",
                             "Automatisch", "Von Hand", "Abweichung", "Geändert", "Hinweis"])
        self.tab.setObjectName("zeit_vergleich_tabelle")
        for r in vs["vergleichbare"]:
            i = self.tab.rowCount()
            self.tab.insertRow(i)
            m = r["m"]

            def zahl(n, stellen=1):
                return f"{m[n]:.{stellen}f}".replace(".", ",") if isinstance(m.get(n), (int, float)) else ""
            for c, (text, rechts) in enumerate((
                    (r.get("angebot") or "", False), (r.get("titel") or "", False), (r.get("art") or "", False),
                    (f"{r['aehnlich'] * 100:.0f} %", True), (zahl("teile_n", 0), True), (zahl("naht_m", 2), True),
                    (zahl("gewicht_kg"), True), (bv.zeit_text(r["auto_min"]), True), (bv.zeit_text(r["hand_min"]), True),
                    (_pct(r["faktor"]), True), (str(r.get("geaendert") or "")[:10], False),
                    ("Ausreißer, nicht gezählt" if r["ausreisser"] else "", False))):
                self.tab.setItem(i, c, _zelle(text, rechts))
        lay.addWidget(self.tab)
        k = QDialogButtonBox(QDialogButtonBox.Close)
        k.rejected.connect(self.reject)
        lay.addWidget(k)


# ------------------------------------------------------------------ Grafik
class Diagramm(QWidget):
    """Einfache Diagramme ohne Fremdbibliothek. punkte(): automatisch gegen von Hand mit Gleichheitslinie;
    balken(): mittlere Abweichung je Gruppe um die Nulllinie (mehr warm, weniger kühl); saeulen(): Häufigkeit je
    Klasse; linie(): Verlauf des mittleren Faktors. Werte stehen direkt an den Marken, Maus zeigt Einzelheiten."""
    RAND = (56, 14, 16, 34)         # links, oben, rechts, unten

    def __init__(self, parent=None):
        super().__init__(parent)
        self.art, self.daten, self.titel = None, [], ""
        self._ziele = []            # [(QRectF, Tooltip)]
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        return QSize(520, 300)

    def setzen(self, art, daten, titel=""):
        self.art, self.daten, self.titel = art, list(daten), titel
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position() if hasattr(e, "position") else QPointF(e.pos())
        for r, text in self._ziele:
            if r.contains(pos):
                QToolTip.showText(e.globalPosition().toPoint(), text, self)
                return
        QToolTip.hideText()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._ziele = []
        text, grau, linie = stil.farbe(stil.TEXT), stil.farbe(stil.TEXT_GRAU), stil.farbe(stil.LINIE)
        li, ob, re, un = self.RAND
        f = QRectF(li, ob + (18 if self.titel else 0), self.width() - li - re, self.height() - ob - un
                   - (18 if self.titel else 0))
        if self.titel:
            p.setPen(text)
            p.drawText(QRectF(li, 0, self.width() - li, 18), Qt.AlignLeft | Qt.AlignVCenter, self.titel)
        if not self.daten or f.width() < 40 or f.height() < 40:
            p.setPen(grau)
            p.drawText(self.rect(), Qt.AlignCenter, "Noch keine Daten")
            return
        getattr(self, "_" + self.art)(p, f, text, grau, linie)

    @staticmethod
    def _stufen(hoch, n=4):
        """Runde Achsenschritte bis mindestens hoch."""
        if hoch <= 0:
            return [0, 1]
        roh = hoch / n
        zehner = 10 ** len(str(int(roh))) / 10 if roh >= 1 else 1
        schritt = next(s * zehner for s in (1, 2, 5, 10) if s * zehner >= roh)
        out, w = [0], 0
        while w < hoch:
            w += schritt
            out.append(w)
        return out

    def _punkte(self, p, f, text, grau, linie):
        """daten: [(auto_min, hand_min, Titel, ausreisser)]"""
        hoch = max(max(a, h) for a, h, *_ in self.daten) * 1.05
        st = self._stufen(hoch)
        hoch = st[-1]

        def x(w):
            return f.left() + w / hoch * f.width()

        def y(w):
            return f.bottom() - w / hoch * f.height()
        p.setPen(QPen(linie, 1))
        for w in st:
            p.drawLine(QPointF(f.left(), y(w)), QPointF(f.right(), y(w)))
        p.setPen(grau)
        for w in st:
            p.drawText(QRectF(0, y(w) - 8, f.left() - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{w:g}")
            p.drawText(QRectF(x(w) - 30, f.bottom() + 2, 60, 14), Qt.AlignCenter, f"{w:g}")
        p.drawText(QRectF(f.left(), f.bottom() + 16, f.width(), 14), Qt.AlignCenter,
                   "automatisch berechnet [min je Baugruppe]")
        p.setPen(QPen(grau, 1, Qt.DashLine))
        p.drawLine(QPointF(x(0), y(0)), QPointF(x(hoch), y(hoch)))
        p.setPen(grau)
        p.drawText(QRectF(x(hoch) - 150, y(hoch) + 2, 146, 14), Qt.AlignRight, "gleich wie berechnet")
        for a, h, titel, aus in self.daten:
            c = QPointF(x(a), y(h))
            farbe = QColor(FARBE_MEHR if h >= a else FARBE_WENIGER)
            p.setPen(QPen(self.palette().window().color(), 2))
            p.setBrush(Qt.NoBrush if aus else farbe)
            if aus:
                p.setPen(QPen(farbe, 2))
            p.drawEllipse(c, 5, 5)
            self._ziele.append((QRectF(c.x() - 9, c.y() - 9, 18, 18),
                                f"{titel}\nautomatisch {bv.zeit_text(a)}, von Hand {bv.zeit_text(h)} ({_pct(h / a)})"
                                + ("\nAusreißer" if aus else "")))
        p.setPen(text)
        p.drawText(QRectF(f.left() + 6, f.top(), f.width() - 170, 16), Qt.AlignLeft,
                   "von Hand [min] · oberhalb der Linie = mehr Zeit · Ring = Ausreißer")

    def _balken(self, p, f, text, grau, linie):
        """daten: [(Titel, n, mittlerer Faktor)] – waagerechte Balken um 0 %."""
        werte = [(t, n, (m - 1) * 100) for t, n, m in self.daten[:10]]
        grenze = max(10.0, max(abs(w) for _, _, w in werte)) * 1.25
        breit = 150
        g = QRectF(f.left() + breit - self.RAND[0], f.top(), f.width() - breit + self.RAND[0], f.height())
        null = g.left() + g.width() / 2
        h = min(26.0, g.height() / len(werte))
        p.setPen(QPen(linie, 1))
        p.drawLine(QPointF(null, g.top()), QPointF(null, g.top() + h * len(werte)))
        for i, (t, n, w) in enumerate(werte):
            yy = g.top() + i * h
            p.setPen(text)
            p.drawText(QRectF(4, yy, g.left() - 10, h), Qt.AlignRight | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(str(t), Qt.ElideRight, int(g.left() - 14)))
            laenge = w / grenze * g.width() / 2
            r = QRectF(min(null, null + laenge), yy + 4, abs(laenge), h - 8)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(FARBE_MEHR if w >= 0 else FARBE_WENIGER))
            p.drawRoundedRect(r, 3, 3)
            p.setPen(text)
            marke = f"{'+' if w >= 0 else '−'}{abs(w):.0f} % ({n})"
            if w >= 0:
                p.drawText(QRectF(r.right() + 4, yy, 120, h), Qt.AlignLeft | Qt.AlignVCenter, marke)
            else:
                p.drawText(QRectF(r.left() - 124, yy, 120, h), Qt.AlignRight | Qt.AlignVCenter, marke)
            self._ziele.append((QRectF(0, yy, self.width(), h),
                                f"{t}: im Mittel {'+' if w >= 0 else '−'}{abs(w):.0f} % gegenüber automatisch, {n} Baugruppen"))
        p.setPen(grau)
        p.drawText(QRectF(g.left(), f.bottom() + 6, g.width(), 14), Qt.AlignCenter,
                   "mittlere Abweichung von der automatischen Zeit (Anzahl Baugruppen)")

    def _saeulen(self, p, f, text, grau, linie):
        """daten: [(Klasse, n)]"""
        hoch = max(1, max(n for _, n in self.daten))
        b = f.width() / len(self.daten)
        p.setPen(QPen(linie, 1))
        p.drawLine(QPointF(f.left(), f.bottom()), QPointF(f.right(), f.bottom()))
        for i, (t, n) in enumerate(self.daten):
            hh = n / hoch * (f.height() - 18)
            r = QRectF(f.left() + i * b + b * 0.2, f.bottom() - hh, b * 0.6, hh)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(FARBE_REIHE))
            if n:
                p.drawRoundedRect(r, 3, 3)
            p.setPen(text)
            p.drawText(QRectF(r.left() - 10, r.top() - 16, r.width() + 20, 14), Qt.AlignCenter, str(n))
            p.setPen(grau)
            p.drawText(QRectF(f.left() + i * b, f.bottom() + 2, b, 30), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, t)
            self._ziele.append((QRectF(f.left() + i * b, f.top(), b, f.height()), f"{t}: {n} Baugruppen"))

    def _linie(self, p, f, text, grau, linie):
        """daten: [(Datum, Faktor, laufendes Mittel)]"""
        werte = [(m - 1) * 100 for _, _, m in self.daten] + [(x - 1) * 100 for _, x, _ in self.daten]
        lo, hi = min(0.0, min(werte)), max(10.0, max(werte))
        lo, hi = lo - (hi - lo) * 0.08, hi + (hi - lo) * 0.08
        n = len(self.daten)

        def x(i):
            return f.left() + (i / (n - 1) if n > 1 else 0.5) * f.width()

        def y(w):
            return f.bottom() - (w - lo) / (hi - lo) * f.height()
        p.setPen(QPen(linie, 1))
        p.drawLine(QPointF(f.left(), y(0)), QPointF(f.right(), y(0)))
        p.setPen(grau)
        p.drawText(QRectF(0, y(0) - 8, f.left() - 6, 16), Qt.AlignRight | Qt.AlignVCenter, "0 %")
        p.drawText(QRectF(0, y(hi) - 2, f.left() - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{hi:+.0f} %")
        p.drawText(QRectF(f.left(), f.bottom() + 4, 120, 14), Qt.AlignLeft, self.daten[0][0])
        p.drawText(QRectF(f.right() - 120, f.bottom() + 4, 120, 14), Qt.AlignRight, self.daten[-1][0])
        p.drawText(QRectF(f.left(), f.bottom() + 18, f.width(), 14), Qt.AlignCenter,
                   "Linie = laufendes Mittel der Abweichung · Punkte = einzelne Entscheidungen")
        p.setPen(Qt.NoPen)
        p.setBrush(grau)
        for i, (d, fak, _) in enumerate(self.daten):
            c = QPointF(x(i), y((fak - 1) * 100))
            p.drawEllipse(c, 3, 3)
            self._ziele.append((QRectF(c.x() - 8, f.top(), 16, f.height()),
                                f"{d}: Entscheidung {_pct(fak)}, laufendes Mittel {_pct(self.daten[i][2])}"))
        p.setPen(QPen(QColor(FARBE_REIHE), 2))
        p.setBrush(Qt.NoBrush)
        for i in range(1, n):
            p.drawLine(QPointF(x(i - 1), y((self.daten[i - 1][2] - 1) * 100)), QPointF(x(i), y((self.daten[i][2] - 1) * 100)))
        p.setPen(text)
        p.drawText(QRectF(x(n - 1) - 80, y((self.daten[-1][2] - 1) * 100) - 18, 80, 14), Qt.AlignRight,
                   _pct(self.daten[-1][2]))


class AuswertungDialog(QDialog):
    """Auswertung der Zeiten von Hand aller Schweißbaugruppen (bg_zeitlernen.auswertung)."""

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Schweißbaugruppen: Auswertung der Zeiten von Hand")
        self.resize(1040, 640)
        lay = QVBoxLayout(self)
        self.kopf = QLabel()
        self.kopf.setObjectName("zeit_auswertung_kopf")
        self.kopf.setWordWrap(True)
        lay.addWidget(self.kopf)
        self.reiter = QTabWidget()
        lay.addWidget(self.reiter, 1)
        # Grafik
        w = QWidget()
        wl = QVBoxLayout(w)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Ansicht"))
        self.wahl = QComboBox()
        self.wahl.setObjectName("zeit_auswertung_wahl")
        for t in ("Automatisch gegen von Hand", "Vergleich der Baugruppenarten", "Vergleich nach Material",
                  "Vergleich nach Gewicht", "Häufigste Abweichungen", "Entwicklung"):
            self.wahl.addItem(t)
        self.wahl.currentIndexChanged.connect(self._grafik)
        zeile.addWidget(self.wahl)
        zeile.addStretch(1)
        wl.addLayout(zeile)
        self.diagramm = Diagramm()
        wl.addWidget(self.diagramm, 1)
        self.reiter.addTab(w, "Grafik")
        # Tabelle
        t = QWidget()
        tl = QVBoxLayout(t)
        self.tab = _tabelle(["Angebot", "Baugruppe", "Art", "Vorgabe", "Automatisch", "Von Hand", "Differenz",
                             "Differenz %", "Lernvorschlag", "Wer", "Geändert", "Status", "Grund"])
        self.tab.setObjectName("zeit_auswertung_tabelle")
        tl.addWidget(self.tab)
        kz = QHBoxLayout()
        self.sperren = QPushButton("Für Vorschläge sperren / freigeben")
        self.sperren.setObjectName("zeit_auswertung_sperren")
        self.sperren.setToolTip("Markierten Datensatz nicht mehr für Zeitvorschläge verwenden bzw. wieder freigeben. "
                                "Der Datensatz und das Protokoll der Baugruppe bleiben.")
        self.sperren.clicked.connect(self._sperren)
        self.sperren.setEnabled(not getattr(db, "nur_lesen", None))
        kz.addWidget(self.sperren)
        kz.addStretch(1)
        tl.addLayout(kz)
        self.reiter.addTab(t, "Alle Zeiten von Hand")
        # Hohe Korrekturen
        self.hoch = _tabelle(["Angebot", "Baugruppe", "Art", "Automatisch", "Von Hand", "Differenz %", "Grund"])
        self.hoch.setObjectName("zeit_auswertung_hoch")
        self.reiter.addTab(self.hoch, "Größte Korrekturen")
        k = QDialogButtonBox(QDialogButtonBox.Close)
        k.rejected.connect(self.reject)
        lay.addWidget(k)
        self.laden()

    def laden(self):
        self.a = a = zl.auswertung(self.db)
        if a["n"]:
            self.kopf.setText(
                f"<b>{a['n']} Schweißbaugruppen mit Zeit von Hand</b> (freigegeben) · im Mittel <b>{_pct(a['mittel'])}</b> "
                f"gegenüber der automatischen Zeit, Median {_pct(a['median'])} · {a['n_gesperrt']} gesperrt, "
                f"{a['n_zurueck']} zurückgesetzt.<br>Zeiten von Hand sind Kalkulationsvorgaben, keine gemessenen "
                "Ist-Zeiten; gemessene Zeiten stehen in der Nachkalkulation.")
        else:
            self.kopf.setText("Noch keine Zeit von Hand gespeichert. Sobald an Schweißbaugruppen Zeiten von Hand "
                              "eingetragen und gespeichert sind, erscheinen sie hier.")
        self.tab.setRowCount(0)
        for r in a["zeilen"]:
            i = self.tab.rowCount()
            self.tab.insertRow(i)
            status = {zl.FREI: "freigegeben", zl.AUS: "gesperrt"}.get(r.get("status") or "", r.get("status") or "")
            vs = r.get("vorschlag_min")
            for c, (text, rechts) in enumerate((
                    (r.get("angebot") or "", False), (r.get("titel") or "", False), (r.get("art") or "", False),
                    (r.get("quelle") or "", False), (bv.zeit_text(r["auto_min"]), True),
                    (bv.zeit_text(r["hand_min"]), True), (bv.abweichung_text(r["abw_min"]), True),
                    (_pct(r["faktor"]), True), (bv.zeit_text(vs) if vs else "", True), (r.get("kuerzel") or "", False),
                    (str(r.get("geaendert") or "")[:16].replace("T", " "), False), (status, False),
                    (r.get("grund") or "", False))):
                self.tab.setItem(i, c, _zelle(text, rechts, r if c == 0 else None))
        self.hoch.setRowCount(0)
        for r in a["hoch"]:
            i = self.hoch.rowCount()
            self.hoch.insertRow(i)
            for c, (text, rechts) in enumerate((
                    (r.get("angebot") or "", False), (r.get("titel") or "", False), (r.get("art") or "", False),
                    (bv.zeit_text(r["auto_min"]), True), (bv.zeit_text(r["hand_min"]), True),
                    (_pct(r["faktor"]) + (" (über 50 %)" if r["weit"] else ""), True), (r.get("grund") or "", False))):
                self.hoch.setItem(i, c, _zelle(text, rechts))
        self._grafik()

    def _grafik(self, *_):
        a, i = self.a, self.wahl.currentIndex()
        frei = [r for r in a["zeilen"] if (r.get("status") or "") == zl.FREI]
        if i == 0:
            aus = zl.ausreisser([r["faktor"] for r in frei])
            self.diagramm.setzen("punkte", [(r["auto_min"], r["hand_min"], f"{r.get('angebot')} {r.get('titel')}",
                                             j in aus) for j, r in enumerate(frei)])
        elif i in (1, 2, 3):
            self.diagramm.setzen("balken", a[("nach_art", "nach_material", "nach_gewicht")[i - 1]])
        elif i == 4:
            self.diagramm.setzen("saeulen", a["haeufig"] if a["n"] else [])
        else:
            self.diagramm.setzen("linie", a["verlauf"])

    def _sperren(self):
        it = self.tab.item(self.tab.currentRow(), 0) if self.tab.currentRow() >= 0 else None
        r = it.data(Qt.UserRole) if it is not None else None
        if not r or r.get("status") not in (zl.FREI, zl.AUS, None):
            return
        zl.status_setzen(self.db, r["id"], zl.AUS if (r.get("status") or "") == zl.FREI else zl.FREI)
        self.laden()
