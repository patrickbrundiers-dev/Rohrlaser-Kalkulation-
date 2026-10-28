"""Querschnitt im Teile-Editor (Plan 3D-Editor D2, Schritt 3E-5): das Rohr an einer Stelle x quer geschnitten, von
Ende A gesehen – Wand des Profils und darin alle Konturen, die an dieser Stelle schneiden (auch auf mehreren
Wänden, Kopien am Umfang, Ausklinkungen). Die Stelle zeigt die 3D-Ansicht als Ring.

Gerechnet wird aus den Eingaben (Abwicklung wie skizze.lagen/umriss_kontur/s_lage), nicht aus dem STEP-Körper.
"""
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from . import rechnen, skizze as sk, schneidweg as sw, stil
from .eingabe import RechenSpin

WAND = stil.farbe_fest("#9AA5B1")
LOCH = stil.farbe_fest("#C62828")
OHNE = (sw.FLOWDRILL,) + sw.GRAVUREN       # nur markiert bzw. graviert: kein Loch in der Wand


def _schnitte(poly, y):
    """Schnittpunkte der Waagerechten dx = y mit dem geschlossenen Linienzug [(dx, dq)]: sortierte dq."""
    out = []
    for i, (ax, aq) in enumerate(poly):
        bx, bq = poly[(i + 1) % len(poly)]
        if (ax > y) != (bx > y):
            out.append(aq + (y - ax) * (bq - aq) / (bx - ax))
    return sorted(out)


def stellen(e, qs, L, x):
    """Konturen, die an der Stelle x [mm ab Ende A] durch die Wand gehen: [(s0, s1, Zeile, Art)] in der Abwicklung
    (s wie skizze.s_lage; Rundrohr s0 < s1 auch über die Naht hinaus)."""
    out = []
    for d in sk.lagen(e.get("konturen") or [], L, qs):
        ein = d["eingabe"]
        if ein.get("art") in OHNE:
            continue
        pts = sk.umriss_kontur(ein)
        if not pts or len(pts) < 3:
            continue
        try:
            s_c = sk.s_lage(qs, ein)
        except (ValueError, TypeError, ZeroDivisionError, AttributeError):
            continue
        dq = _schnitte(pts, x - d["x"])
        for a, b in zip(dq[0::2], dq[1::2], strict=False):
            out.append((s_c + a, s_c + b, d["zeile"], ein.get("art")))
    return out


def ring(qs, x):
    """Außenumriss an der Stelle x als 3D-Linienzug (Koordinaten wie rohr3d: (−u, v, x))."""
    um = qs.umriss_rund(12) if hasattr(qs, "umriss_rund") else qs.umriss
    if not um or not um[0]:
        return []
    pk = list(um[0])
    return [(-u, v, x) for u, v in pk + pk[:1]]


class SchnittBild(QWidget):
    """Zeichnung des Querschnitts: Wand grau, geschnittene Stellen rot (Loch), Blick von Ende A."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.qs, self.liste, self.x = None, [], 0.0
        self.setMinimumSize(260, 240)

    def setzen(self, qs, liste, x):
        self.qs, self.liste, self.x = qs, liste, x
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), stil.farbe("#FFFFFF"))
        qs = self.qs
        if qs is None or not qs.umriss:
            p.end()
            return
        p.setRenderHint(QPainter.Antialiasing, True)
        um = qs.umriss_rund(12) if hasattr(qs, "umriss_rund") else qs.umriss
        us = [u for poly in um for u, _ in poly]
        vs = [v for poly in um for _, v in poly]
        groesse = max(max(us) - min(us), max(vs) - min(vs), 1.0)
        rand = 30
        s = (min(self.width(), self.height()) - 2 * rand) / groesse
        cx, cy = self.width() / 2, self.height() / 2 + 8

        def bp(u, v):            # Blick von Ende A: u nach rechts = vorne (90°)
            return QPointF(cx + u * s, cy - v * s)
        pfad = QPainterPath()
        pfad.setFillRule(Qt.OddEvenFill)
        for poly in um:
            pfad.addPolygon(QPolygonF([bp(u, v) for u, v in poly] + [bp(*poly[0])]))
        p.fillPath(pfad, WAND)
        p.setPen(QPen(stil.farbe("#5A6470"), 1.2))
        p.drawPath(pfad)
        wand = qs.wand or 0.0
        for s0, s1, _, _ in self.liste:
            n = max(2, int(abs(s1 - s0) / 0.5) + 1)
            aussen, innen = [], []
            for k in range(n):
                (u, v), nv = qs.s_zu_uv((s0 + (s1 - s0) * k / (n - 1)) % qs.umfang)
                aussen.append(bp(u + nv[0] * 0.6, v + nv[1] * 0.6))
                innen.append(bp(u - nv[0] * (wand + 0.6), v - nv[1] * (wand + 0.6)))
            loch = QPolygonF(aussen + innen[::-1])
            p.setPen(Qt.NoPen)
            p.setBrush(stil.farbe("#FFFFFF"))
            p.drawPolygon(loch)
            p.setPen(QPen(LOCH, 2.0))
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(QPolygonF(aussen))
            p.drawPolyline(QPolygonF(innen))
        p.setPen(stil.farbe(stil.TEXT_GRAU))
        p.drawText(8, 18, f"Querschnitt bei x = {rechnen.zahl(self.x, 1)} mm, von Ende A gesehen")
        p.end()


class SchnittFenster(QDialog):
    """Nicht modales Fenster: Stelle x (Feld und Schieber), Querschnitt, getroffene Konturen; markiert die Stelle in
    der 3D-Ansicht des Teile-Editors."""
    geschlossen = Signal()

    def __init__(self, rahmen):
        super().__init__(rahmen if isinstance(rahmen, QWidget) else rahmen.d)
        self.r = rahmen
        self.setWindowTitle("Querschnitt")
        self.setWindowFlag(Qt.Tool, True)
        lay = QVBoxLayout(self)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Stelle x ab Ende A"))
        self.feld = RechenSpin()
        self.feld.setDecimals(1)
        self.feld.setSuffix(" mm")
        self.feld.setRange(0, 100000)
        self.feld.setToolTip("Stelle längs des Rohrs, an der quer geschnitten wird")
        zeile.addWidget(self.feld)
        lay.addLayout(zeile)
        self.schieber = QSlider(Qt.Horizontal)
        self.schieber.setRange(0, 1000)
        lay.addWidget(self.schieber)
        self.bild = SchnittBild()
        lay.addWidget(self.bild, 1)
        self.text = QLabel()
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        self.feld.valueChanged.connect(self._feld)
        self.schieber.valueChanged.connect(self._schieber)
        self._laenge = 0.0
        self.resize(360, 420)

    def laenge(self):
        return self.r.teil_laenge() or 0.0

    def _feld(self, v):
        L = self.laenge()
        if L > 0:
            self.schieber.blockSignals(True)
            self.schieber.setValue(int(round(v / L * 1000)))
            self.schieber.blockSignals(False)
        self.zeichnen()

    def _schieber(self, w):
        self.feld.setValue(self.laenge() * w / 1000)

    def setzen(self, x):
        self.feld.setValue(x)

    def auffrischen(self):
        L = self.laenge()
        self.feld.blockSignals(True)
        self.feld.setMaximum(max(L, 0.0))
        if L and self._laenge == 0.0:
            self.feld.setValue(L / 2)
        self.feld.blockSignals(False)
        self._laenge = L
        self._feld(self.feld.value())

    def ergebnis(self):
        d = self.r.d
        return stellen(d.eingaben(), d.qs, self.laenge(), self.feld.value())

    def zeichnen(self):
        d = self.r.d
        x = self.feld.value()
        liste = self.ergebnis()
        self.bild.setzen(d.qs, liste, x)
        zeilen = sorted({(z, a) for _, _, z, a in liste})
        self.text.setText("Geschnitten: " + ", ".join(f"Zeile {z + 1} {a}" for z, a in zeilen) if zeilen else
                          "An dieser Stelle schneidet keine Kontur die Wand.")
        a = self.r.ansicht()
        if a is not None:
            a.schnitt_setzen(ring(d.qs, x))

    def hideEvent(self, e):
        a = self.r.ansicht()
        if a is not None:
            a.schnitt_setzen([])
        super().hideEvent(e)

    def closeEvent(self, e):
        super().closeEvent(e)
        self.geschlossen.emit()

