"""Ladung in 2D und 3D (Packkern 3.0, Patrick 25.11.2026, Master-Auftrag „Ladegutberechnung und
Verpackungsvisualisierung“). Zeigt die Packliste aus paletten.packen mit Packkern 3.0 (Schlüssel 'teile', 'lagen'):

- 2D-Draufsicht je Lage oder alle Lagen (oberste sichtbar): Farben je Artikel, Pos.-/Artikelnummer, Überstände
  (rot schraffiert), freie Flächen (grün), nutzbare Breite (Sicherheitsabstand gestrichelt), Maße.
- 3D-Ansicht: Ladungsträger (Europalette mit Brettern und Klötzen, Gitterbox mit Gitter, Aufsetzrahmen, Karton),
  die Teile mit echtem Querschnitt (Rundrohr, Quadrat-/Rechteckrohr, U, Winkel, Flachstahl), Lagen und
  verschachtelte Teile; ziehen = drehen, Mausrad = Zoom.
- Klick auf ein Teil: Infos und alle Teile dieses Artikels hervorgehoben; Lagen ein/aus; Varianten A–D mit
  Kennzahlen (die beste markiert) umschalten.
- Von Hand: Position allein auf ein Packstück, Lage längs/quer festlegen, ganze Lage auf ein anderes Packstück
  verschieben; danach rechnet der Frachtrechner sofort neu (Rückruf aendern(hand)).
Ohne Packkern 3.0 (ältere Frachtberechnung) zeigt der Reiter einen Hinweis; die bisherige Skizze bleibt links.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
                               QWidget)

from . import packkern, stil
from .stammdaten import zahl_als_text

HOLZ = "#C8A675"
HOLZ_DUNKEL = "#8B6B3E"
MAX_3D = 4000                # mehr Teile: in 3D als Quader (schneller)


def _mm(x):
    return zahl_als_text(round(x or 0), 0)


def farbe_artikel(k):
    return stil.TEIL_FARBEN[k % len(stil.TEIL_FARBEN)]


# ------------------------------------------------------------------ Geometrie für 3D
def querschnitt(profil, b, h, stapel=None, verzahnt=False):
    """Querschnitt eines Teils als Polygon(e) in (s, t) mit Ursprung unten links, Breite b, Höhe h (Liegemaß):
    [[(s, t), …], …]. Rundrohr als 16-Eck; U und Winkel mit Wandstärke; sonst Rechteck."""
    if not profil:
        return [[(0, 0), (b, 0), (b, h), (0, h)]]
    form, a, bb, w = profil
    w = float(w or 0) or min(b, h) * 0.1
    if form == "Rundrohr":
        r = min(b, h) / 2
        return [[(b / 2 + r * math.cos(2 * math.pi * i / 16), h / 2 + r * math.sin(2 * math.pi * i / 16))
                 for i in range(16)]]
    if form == "U-Profil" and verzahnt and stapel and stapel > 1:
        # gleich große U abwechselnd offen und umgedreht: Breite ub, Höhe uh je U, Teilung (b − ub) / (m − 1)
        m = int(stapel)
        ub, uh = float(a), float(bb or a)
        t = (b - ub) / (m - 1)
        out = []
        for i in range(m):
            x0 = i * t
            if i % 2 == 0:
                out.append([(x0, 0), (x0 + ub, 0), (x0 + ub, uh), (x0 + ub - w, uh), (x0 + ub - w, w), (x0 + w, w),
                            (x0 + w, uh), (x0, uh)])
            else:
                z1 = h
                out.append([(x0, z1), (x0 + ub, z1), (x0 + ub, z1 - uh), (x0 + ub - w, z1 - uh),
                            (x0 + ub - w, z1 - w), (x0 + w, z1 - w), (x0 + w, z1 - uh), (x0, z1 - uh)])
        return out
    if form == "U-Profil":
        if b >= h:          # Öffnung nach oben
            return [[(0, 0), (b, 0), (b, h), (b - w, h), (b - w, w), (w, w), (w, h), (0, h)]]
        return [[(0, 0), (b, 0), (b, w), (w, w), (w, h - w), (b, h - w), (b, h), (0, h)]]
    if form == "L-Profil":       # gleiche Winkel ineinander: jeder weitere um die Wandstärke versetzt
        m = int(stapel or 1)
        b0, h0 = b - (m - 1) * w, h - (m - 1) * w
        return [[(i * w + q, i * w + r) for q, r in ((0, 0), (b0, 0), (b0, w), (w, w), (w, h0), (0, h0))]
                for i in range(m)]
    return [[(0, 0), (b, 0), (b, h), (0, h)]]


class Kamera:
    """Einfache Parallelprojektion: Drehung um die Hochachse (az), Neigung (el)."""

    def __init__(self, az=-35.0, el=28.0):
        self.az, self.el, self.zoom = az, el, 1.0

    def punkt(self, x, y, z):
        a, e = math.radians(self.az), math.radians(self.el)
        xr = x * math.cos(a) - y * math.sin(a)
        yr = x * math.sin(a) + y * math.cos(a)
        return xr, -(z * math.cos(e) + yr * math.sin(e)), yr * math.cos(e) - z * math.sin(e)   # (sx, sy, Tiefe)


# ------------------------------------------------------------------ Zeichenfläche
class Leinwand(QWidget):
    teil_gewaehlt = Signal(object)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(False)
        self.packliste, self.pal, self.modus3d, self.lage = None, None, False, 0   # lage 0 = alle
        self.aus = set()             # ausgeblendete Lagen
        self.wahl = None             # gewähltes Teil (Index in pal['teile'])
        self.kamera = Kamera()
        self._treffer = []           # (QPolygonF/QRectF, Index) für Klicks, oberstes zuletzt
        self._ziehen = None

    def setzen(self, packliste, pal):
        self.packliste, self.pal = packliste, pal
        self.wahl = None
        self.update()

    # -------- Maus
    def mousePressEvent(self, e):
        self._ziehen = (e.position(), self.kamera.az, self.kamera.el, False)

    def mouseMoveEvent(self, e):
        if self._ziehen and self.modus3d:
            p0, az, el, _ = self._ziehen
            d = e.position() - p0
            self.kamera.az = az + d.x() * 0.4
            self.kamera.el = max(5.0, min(85.0, el + d.y() * 0.3))
            self._ziehen = (p0, az, el, True)
            self.update()

    def mouseReleaseEvent(self, e):
        gezogen = self._ziehen and self._ziehen[3]
        self._ziehen = None
        if gezogen:
            return
        pos = e.position()
        for form, i in reversed(self._treffer):
            if (form.containsPoint(pos, Qt.OddEvenFill) if isinstance(form, QPolygonF) else form.contains(pos)):
                self.wahl = i
                self.teil_gewaehlt.emit(i)
                self.update()
                return
        self.wahl = None
        self.teil_gewaehlt.emit(None)
        self.update()

    def wheelEvent(self, e):
        if self.modus3d:
            self.kamera.zoom = max(0.3, min(6.0, self.kamera.zoom * (1.12 if e.angleDelta().y() > 0 else 1 / 1.12)))
            self.update()

    # -------- Zeichnen
    def _sichtbar(self, t):
        return t["lage"] not in self.aus and (not self.lage or t["lage"] == self.lage)

    def _artikel_gewaehlt(self):
        if self.wahl is None or not self.pal:
            return None
        return self.pal["teile"][self.wahl]["k"]

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), stil.farbe("#FFFFFF"))
        self._treffer = []
        if not self.pal or self.pal.get("teile") is None:
            p.setPen(stil.farbe("#5F6B7A"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Keine Ladung mit Packkern 3.0 – Fracht neu berechnen (Ware aus dem Angebot)")
            p.end()
            return
        if self.modus3d:
            self._zeichnen_3d(p)
        else:
            self._zeichnen_2d(p)
        p.end()

    # 2D ------------------------------------------------------------
    def _zeichnen_2d(self, p):
        g = self.pal["grenzen"]
        L, B, u, rand = g["laenge"], g["breite"], g["ueberstand"], g["rand"]
        teile = [dict(t, i=i) for i, t in enumerate(self.pal["teile"]) if self._sichtbar(t)]
        x0 = min([0.0, -u] + [t["x0"] for t in teile])
        x1 = max([L, L + u] + [t["x1"] for t in teile])
        rr = QRectF(60, 34, self.width() - 90, self.height() - 80)
        s = min(rr.width() / (x1 - x0), rr.height() / B) if x1 > x0 and B else 1.0
        ox = rr.x() + (rr.width() - (x1 - x0) * s) / 2 - x0 * s
        oy = rr.y() + (rr.height() - B * s) / 2

        def R(a, b, c, d):
            return QRectF(ox + a * s, oy + (B - d) * s, (b - a) * s, (d - c) * s)      # y nach oben
        p.setPen(stil.farbe("#1F2937"))
        titel = "Draufsicht " + (f"Lage {self.lage}" if self.lage else "alle Lagen (oberste sichtbar)")
        p.drawText(QRectF(8, 6, self.width() - 16, 20), Qt.AlignLeft | Qt.AlignVCenter, titel)
        # Überstandszonen
        if u:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(stil.farbe("#E15759", 110), Qt.BDiagPattern))
            p.drawRect(R(-u, 0, 0, B))
            p.drawRect(R(L, L + u, 0, B))
        # Ladungsträger, freie Fläche grün
        p.setPen(QPen(stil.farbe(HOLZ_DUNKEL), 1.5))
        p.setBrush(stil.farbe("#59A14F", 45))
        p.drawRect(R(0, L, 0, B))
        if rand:
            p.setPen(QPen(stil.farbe("#B42318"), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(R(-u, L + u, rand, B - rand))
        gew = self._artikel_gewaehlt()
        stuecke = self.packliste["stuecke"]
        fm = QFontMetrics(p.font())
        for t in sorted(teile, key=lambda t: (t["z1"], t["innen_von"] is not None)):
            i = t["i"]
            rect = R(t["x0"], t["x1"], t["y0"], t["y1"])
            c = QColor(stil.farbe(farbe_artikel(t["k"])))
            if gew is not None and t["k"] != gew:
                c.setAlpha(70)
            p.setBrush(c)
            p.setPen(QPen(stil.farbe("#111827" if i == self.wahl else "#1F2937"), 2.2 if i == self.wahl else 0.5))
            if t["rund"] and not t["quer"] and rect.height() > rect.width() * 0.9 and rect.width() < 6:
                p.drawEllipse(rect)
            else:
                p.drawRect(rect)
            self._treffer.append((rect, i))
            text = f"Pos. {stuecke[t['k']]['pos'] or '?'}"
            if rect.width() > fm.horizontalAdvance(text) + 6 and rect.height() > fm.height():
                p.setPen(stil.farbe("#FFFFFF"))
                p.drawText(rect, Qt.AlignCenter, text)
        p.setPen(QPen(stil.farbe(HOLZ_DUNKEL), 1.5, Qt.DashLine))      # Palettenrand über der Ladung
        p.setBrush(Qt.NoBrush)
        p.drawRect(R(0, L, 0, B))
        # Maße
        p.setPen(stil.farbe("#5F6B7A"))
        unten = oy + B * s + 6
        p.drawLine(QPointF(ox, unten), QPointF(ox + L * s, unten))
        p.drawText(QRectF(ox, unten + 2, L * s, 16), Qt.AlignHCenter, f"{_mm(L)} mm")
        p.save()
        p.translate(ox + x0 * s - 14, oy + B * s / 2)
        p.rotate(-90)
        p.drawText(QRectF(-B * s / 2, -8, B * s, 16), Qt.AlignCenter, f"{_mm(B)} mm (nie Überstand)")
        p.restore()
        ueber = max([0.0] + [max(-t["x0"], t["x1"] - L) for t in teile if t["innen_von"] is None])
        info = f"Überstand je Stirnseite höchstens {_mm(u)} mm"
        if ueber > u + 0.5:
            info += f"; lange Teile mittig bis zur max. Teillänge, {_mm(ueber)} mm je Seite"
        else:
            info += f", genutzt {_mm(ueber)} mm"
        if rand:
            info += f"; Sicherheitsabstand {_mm(rand)} mm"
        p.drawText(QRectF(8, self.height() - 22, self.width() - 16, 18), Qt.AlignLeft, info)

    # 3D ------------------------------------------------------------
    def _zeichnen_3d(self, p):
        g = self.pal["grenzen"]
        L, B = g["laenge"], g["breite"]
        k = self.kamera
        art = self.pal.get("art")
        boden = 0.0 if art in ("Gitterbox", "Karton", "Sonderbehälter") else float((self.pal.get("masse") or (0, 0, 0))[2]
                                                                                   or 0.0)
        flaechen = []        # (Polygon (Weltpunkte), Farbe, Index oder None, Rand, Gruppe)
        gruppe = [(0, 0.0, 0)]   # Zeichenfolge: Ladungsträger, dann Lage für Lage (unten zuerst), je Teil nach Tiefe
        teile = [dict(t, i=i) for i, t in enumerate(self.pal["teile"]) if self._sichtbar(t)]
        einfach = len(teile) > MAX_3D
        gew = self._artikel_gewaehlt()
        stuecke = self.packliste["stuecke"]

        def quader(a, b, c, d, e, f, farbe, idx=None, rand="#1F2937"):
            P = [(a, c, e), (b, c, e), (b, d, e), (a, d, e), (a, c, f), (b, c, f), (b, d, f), (a, d, f)]
            for ecken in ((4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (0, 3, 2, 1)):
                flaechen.append(([P[q] for q in ecken], farbe, idx, rand, gruppe[0]))

        # Ladungsträger
        holz = stil.farbe(HOLZ)
        if boden:
            hb = min(22.0, boden / 4)
            for j in range(5):                       # Deckbretter längs
                y = j * (B - 100) / 4
                quader(0, L, y, y + 100, boden - hb, boden, holz, rand=HOLZ_DUNKEL)
            for xi in (0, (L - 145) / 2, L - 145):  # Klötze
                for yi in (0, (B - 100) / 2, B - 100):
                    quader(xi, xi + 145, yi, yi + 100, hb, boden - hb, stil.farbe("#B8945F"), rand=HOLZ_DUNKEL)
            for yi in (0, (B - 100) / 2, B - 100):  # Bodenbretter
                quader(0, L, yi, yi + 100, 0, hb, holz, rand=HOLZ_DUNKEL)
        rahmen = self.pal.get("rahmen") or 0
        if art == "Palette mit Aufsetzrahmen" and rahmen:
            rh = (float(self.pal.get("hoehe") or 0) - boden) / rahmen
            for j in range(rahmen):
                z0 = boden + j * rh
                for a_, b_, c_, d_ in ((0, L, 0, 18), (0, L, B - 18, B), (0, 18, 0, B), (L - 18, L, 0, B)):
                    quader(a_, b_, c_, d_, z0, z0 + rh - 4, stil.farbe(HOLZ, 120), rand=HOLZ_DUNKEL)
        for t in sorted(teile, key=lambda t: t["innen_von"] is not None):
            i = t["i"]
            c = QColor(stil.farbe(farbe_artikel(t["k"])))
            if gew is not None and t["k"] != gew:
                c.setAlpha(60)
            if i == self.wahl:
                c = c.lighter(140)
            z0, z1 = t["z0"] + boden, t["z1"] + boden
            prof = stuecke[t["k"]].get("profil")
            gruppe[0] = (1 + t["lage"], k.punkt((t["x0"] + t["x1"]) / 2, (t["y0"] + t["y1"]) / 2, z0)[2] * -1,
                         t["innen_von"] is not None)
            if einfach or t["innen_von"] is not None and not prof:
                quader(t["x0"], t["x1"], t["y0"], t["y1"], z0, z1, c, i)
                continue
            if t["quer"]:
                b, h = t["x1"] - t["x0"], z1 - z0
            else:
                b, h = t["y1"] - t["y0"], z1 - z0
            for poly in querschnitt(prof, b, h, t.get("stapel"), t.get("verzahnt")):
                if t["quer"]:
                    vorne = [(t["x0"] + q, t["y0"], z0 + r) for q, r in poly]
                    hinten = [(t["x0"] + q, t["y1"], z0 + r) for q, r in poly]
                else:
                    vorne = [(t["x0"], t["y0"] + q, z0 + r) for q, r in poly]
                    hinten = [(t["x1"], t["y0"] + q, z0 + r) for q, r in poly]
                flaechen.append((vorne, c, i, "#1F2937", gruppe[0]))
                flaechen.append((hinten, c, i, "#1F2937", gruppe[0]))
                n = len(poly)
                for j in range(n):
                    flaechen.append(([vorne[j], vorne[(j + 1) % n], hinten[(j + 1) % n], hinten[j]],
                                     c.darker(115) if j % 2 else c, i, None if n > 8 else "#1F2937", gruppe[0]))
        if art == "Gitterbox":
            hg = float((self.pal.get("masse") or (0, 0, 0))[2] or 800)
            for a_, b_, c_, d_ in ((0, L, 0, 0), (0, L, B, B), (0, 0, 0, B), (L, L, 0, B)):
                flaechen.append(([(a_, c_, 0), (b_, d_, 0), (b_, d_, hg), (a_, c_, hg)],
                                 stil.farbe("#7F8A99", 35), None, "#5F6B7A", (10 ** 6, 0.0, 0)))
        # projizieren
        proj = []
        for pts, c, i, rand, gr in flaechen:
            q = [k.punkt(*pt) for pt in pts]
            proj.append(((gr, -sum(x[2] for x in q) / len(q)), q, c, i, rand))
        if not proj:
            return
        xs = [x for _, q, *_ in proj for x, _, _ in q]
        ys = [y for _, q, *_ in proj for _, y, _ in q]
        w, h = max(xs) - min(xs) or 1, max(ys) - min(ys) or 1
        s = min((self.width() - 40) / w, (self.height() - 50) / h) * k.zoom
        ox = self.width() / 2 - (min(xs) + w / 2) * s
        oy = (self.height() + 10) / 2 - (min(ys) + h / 2) * s
        proj.sort(key=lambda x: x[0])
        for _, q, c, i, rand in proj:
            poly = QPolygonF([QPointF(ox + x * s, oy + y * s) for x, y, _ in q])
            p.setBrush(c)
            p.setPen(QPen(stil.farbe(rand), 0.4) if rand else Qt.NoPen)
            p.drawPolygon(poly)
            if i is not None:
                self._treffer.append((poly, i))
        p.setPen(stil.farbe("#5F6B7A"))
        p.drawText(QRectF(8, 6, self.width() - 16, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   "3D – ziehen zum Drehen, Mausrad zum Zoomen" + (" (vereinfacht: viele Teile)" if einfach else ""))


# ------------------------------------------------------------------ Gesamtansicht
class PackAnsicht(QWidget):
    """Reiter „Ladung 2D/3D“ im Frachtrechner."""

    def __init__(self, aendern=None):
        super().__init__()
        self.aendern = aendern       # Rückruf(hand) -> neu packen
        self.packliste, self.hand = None, {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        oben = QHBoxLayout()
        self.variante = QComboBox()
        self.variante.setToolTip("Varianten des Packkerns; ★ = beste nach den Einstellungen. Wählen = von Hand")
        self.packstueck = QComboBox()
        self.lage = QComboBox()
        self.ansicht = QButtonGroup(self)
        self.k2d, self.k3d = QToolButton(), QToolButton()
        for i, (b, t) in enumerate(((self.k2d, "2D"), (self.k3d, "3D"))):
            b.setText(t)
            b.setCheckable(True)
            self.ansicht.addButton(b, i)
        self.k2d.setChecked(True)
        for w, t in ((QLabel("Variante"), None), (self.variante, 1), (QLabel("Packstück"), None), (self.packstueck, 0),
                     (QLabel("Lage"), None), (self.lage, 0), (self.k2d, None), (self.k3d, None)):
            oben.addWidget(w, t or 0)
        lay.addLayout(oben)
        self.kennzahlen = QTableWidget(0, 7)
        self.kennzahlen.setHorizontalHeaderLabels(["Variante", "Packstücke", "Fläche", "Volumen", "Artikel je Packstück",
                                                   "Überstand", "Prüfung"])
        self.kennzahlen.verticalHeader().hide()
        self.kennzahlen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.kennzahlen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.kennzahlen.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.kennzahlen.setMaximumHeight(150)
        lay.addWidget(self.kennzahlen)
        self.leinwand = Leinwand()
        lay.addWidget(self.leinwand, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.RichText)
        lay.addWidget(self.info)
        hand = QHBoxLayout()
        self.allein = QPushButton("Position allein auf ein Packstück")
        self.achse = QPushButton("Lage längs/quer drehen")
        self.ziel = QComboBox()
        self.schieben = QPushButton("Lage verschieben")
        self.zurueck = QPushButton("Von Hand zurücksetzen")
        for b in (self.allein, self.achse, QLabel("nach"), self.ziel, self.schieben, self.zurueck):
            hand.addWidget(b)
        hand.addStretch(1)
        lay.addLayout(hand)
        self.allein.setToolTip("Gewählte Position packt nur auf eigene Packstücke (keine anderen Artikel dazu)")
        self.achse.setToolTip("Gewählte Position: Teile längs bzw. quer zur langen Seite legen")
        self.schieben.setToolTip("Ganze Lage des gewählten Teils auf ein anderes oder ein neues Packstück; wird "
                                 "geprüft (Höhe, Gewicht, Artikel)")
        self.variante.activated.connect(self._variante_gewaehlt)
        self.packstueck.currentIndexChanged.connect(lambda *_: self._packstueck_zeigen())
        self.lage.currentIndexChanged.connect(lambda *_: self._lage_gewaehlt())
        self.ansicht.idClicked.connect(self._ansicht)
        self.leinwand.teil_gewaehlt.connect(self._teil_info)
        self.kennzahlen.cellClicked.connect(lambda r, _c: self._variante_gewaehlt(r))
        self.allein.clicked.connect(self._allein)
        self.achse.clicked.connect(self._achse)
        self.schieben.clicked.connect(self._schieben)
        self.zurueck.clicked.connect(self._zuruecksetzen)
        self._knoepfe()

    # -------- Daten
    def setzen(self, packliste, hand=None):
        self.packliste = packliste if packliste and packliste.get("kern") == 3 else None
        self.hand = dict(hand or {})
        self._laden = True
        self.variante.clear()
        self.kennzahlen.setRowCount(0)
        if self.packliste:
            for r, v in enumerate(self.packliste["varianten"]):
                stern = " ★" if v["beste"] else ""
                self.variante.addItem(f"{v['code']} – {v['name']}: {v['anzahl']} Packstück"
                                      f"{'e' if v['anzahl'] != 1 else ''}{stern}", v["code"])
                self.kennzahlen.insertRow(r)
                werte = [f"{v['code']} {v['name']}{stern}", str(v["anzahl"]), f"{v['flaeche'] * 100:.0f} %",
                         f"{v['volumen'] * 100:.0f} %", zahl_als_text(v["artikel_mittel"], 1),
                         f"{_mm(v['ueberstand'])} mm", "in Ordnung" if not v["fehler"] else f"{len(v['fehler'])} Fehler"]
                for c, w in enumerate(werte):
                    it = QTableWidgetItem(w)
                    if v["code"] == self.packliste["variante"]:
                        f = it.font()
                        f.setBold(True)
                        it.setFont(f)
                    if v["fehler"] and c == 6:
                        it.setForeground(stil.farbe("#B42318"))
                        it.setToolTip("\n".join(v["fehler"][:10]))
                    self.kennzahlen.setItem(r, c, it)
            self.variante.setCurrentIndex(self.variante.findData(self.packliste["variante"]))
        self.packstueck.clear()
        for pal in (self.packliste or {}).get("paletten") or ():
            self.packstueck.addItem(f"{pal['nr']}: {pal['bezeichnung']}, {zahl_als_text(pal['brutto'], 0)} kg", pal["nr"])
        self._laden = False
        self._packstueck_zeigen()

    def _pal(self):
        if not self.packliste:
            return None
        i = self.packstueck.currentIndex()
        pals = self.packliste["paletten"]
        return pals[i] if 0 <= i < len(pals) else None

    def _packstueck_zeigen(self):
        if getattr(self, "_laden", False):
            return
        pal = self._pal()
        self._laden = True
        self.lage.clear()
        self.lage.addItem("alle", 0)
        for lg in (pal or {}).get("lagen") or ():
            arts = ", ".join(f"Pos. {self.packliste['stuecke'][k]['pos'] or '?'} × {n}" for k, n in lg["stueck"].items())
            self.lage.addItem(f"{lg['nr']} ({lg['achse']}{', versetzt' if lg['versetzt'] else ''}): {arts}", lg["nr"])
        self.ziel.clear()
        self.ziel.addItem("neues Packstück", 0)
        for p in (self.packliste or {}).get("paletten") or ():
            if p is not pal:
                self.ziel.addItem(f"Packstück {p['nr']}", p["nr"])
        self._laden = False
        self.leinwand.lage = 0
        self.leinwand.setzen(self.packliste, pal)
        self._teil_info(None)

    def _lage_gewaehlt(self):
        if getattr(self, "_laden", False):
            return
        self.leinwand.lage = self.lage.currentData() or 0
        self.leinwand.update()
        self._knoepfe()

    def _ansicht(self, i):
        self.leinwand.modus3d = i == 1
        self.leinwand.update()

    def _teil_info(self, i):
        pal = self._pal()
        if i is None or pal is None:
            self.info.setText(self._legende(pal))
            self._knoepfe()
            return
        t = pal["teile"][i]
        s = self.packliste["stuecke"][t["k"]]
        m = s.get("masse") or (0, 0, 0)
        txt = (f"<b>Pos. {s['pos'] or '?'}</b> {s['artikel']} {s.get('bezeichnung') or ''}: "
               f"{' × '.join(_mm(x) for x in m)} mm, {zahl_als_text(s['gewicht'] or 0, 2)} kg; Lage {t['lage']}, "
               f"{'quer' if t['quer'] else 'längs'}, x {_mm(t['x0'])}…{_mm(t['x1'])} mm, y {_mm(t['y0'])}…"
               f"{_mm(t['y1'])} mm, z {_mm(t['z0'])}…{_mm(t['z1'])} mm")
        if t["innen_von"] is not None:
            o = self.packliste["stuecke"][pal["teile"][t["innen_von"]]["k"]]
            txt += f"; verschachtelt in Pos. {o['pos'] or '?'}"
        if t.get("stapel"):
            txt += f"; {t['stapel']} {'U verzahnt' if t.get('verzahnt') else 'Winkel ineinander'}"
        auf = sum(n for k, n in pal["inhalt"] if k == t["k"])
        txt += f". Auf diesem Packstück {auf} Stück."
        self.info.setText(txt)
        self._knoepfe()

    def _legende(self, pal):
        if not pal:
            return ("<i>Die Ansicht braucht eine Packliste mit Packkern 3.0 (Einstellung „Packkern 3.0“ = ja, Ware "
                    "aus dem Angebot).</i>" if not self.packliste else "")
        st = self.packliste["stuecke"]
        teile = [f"<span style='color:{farbe_artikel(k)}'>■</span> Pos. {st[k]['pos'] or '?'} {st[k]['artikel']} "
                 f"× {n}" for k, n in pal["inhalt"]]
        txt = "  ".join(teile)
        if pal.get("pruefung"):
            txt += "<br><span style='color:#B42318'>Prüfung: " + "; ".join(pal["pruefung"][:3]) + "</span>"
        else:
            txt += "<br>Geometrisch geprüft: keine Überschneidung, Breite und Überstand eingehalten."
        return txt + " Klick auf ein Teil zeigt Details."

    # -------- von Hand
    def _knoepfe(self):
        gewaehlt = self.leinwand.wahl is not None and self._pal() is not None
        for b in (self.allein, self.achse, self.schieben, self.ziel):
            b.setEnabled(bool(gewaehlt and self.aendern))
        self.zurueck.setEnabled(bool(self.hand and self.aendern))

    def _gewaehlte_position(self):
        pal = self._pal()
        t = pal["teile"][self.leinwand.wahl]
        return pal, t, str(self.packliste["stuecke"][t["k"]].get("id"))

    def _neu(self):
        if self.aendern:
            self.aendern(self.hand)

    def _variante_gewaehlt(self, r):
        if not self.packliste or not 0 <= r < len(self.packliste["varianten"]):
            return
        code = self.packliste["varianten"][r]["code"]
        if code == self.packliste["variante"]:
            return
        self.hand = dict(self.hand, variante=code, verschieben=[])
        self._neu()

    def _artikel(self, pid):
        a = dict((self.hand.get("artikel") or {}).get(pid) or {})
        return a

    def _allein(self):
        _, _, pid = self._gewaehlte_position()
        a = self._artikel(pid)
        a["allein"] = not a.get("allein")
        self.hand = dict(self.hand, artikel=dict(self.hand.get("artikel") or {}, **{pid: a}), verschieben=[])
        self._neu()

    def _achse(self):
        _, t, pid = self._gewaehlte_position()
        a = self._artikel(pid)
        a["achse"] = "l" if t["quer"] else "q"
        self.hand = dict(self.hand, artikel=dict(self.hand.get("artikel") or {}, **{pid: a}), verschieben=[])
        self._neu()

    def _schieben(self):
        pal, t, _ = self._gewaehlte_position()
        ops = list(self.hand.get("verschieben") or []) + [[pal["nr"], t["lage"], self.ziel.currentData() or 0]]
        self.hand = dict(self.hand, variante=self.packliste["variante"], verschieben=ops)
        self._neu()

    def _zuruecksetzen(self):
        self.hand = {}
        self._neu()


def hand_text(hand):
    """Kurzer Text der Änderungen von Hand (für die Packliste)."""
    if not hand:
        return ""
    teile = []
    if hand.get("variante"):
        teile.append(f"Variante {hand['variante']} ({packkern.VARIANTEN.get(hand['variante'], '')})")
    n = sum(1 for a in (hand.get("artikel") or {}).values() if a)
    if n:
        teile.append(f"{n} Position{'en' if n != 1 else ''} von Hand")
    if hand.get("verschieben"):
        teile.append(f"{len(hand['verschieben'])} Lage{'n' if len(hand['verschieben']) != 1 else ''} verschoben")
    return ", ".join(teile)


__all__ = ["PackAnsicht", "Leinwand", "querschnitt", "hand_text"]
