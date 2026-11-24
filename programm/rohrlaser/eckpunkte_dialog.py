"""Eckpunkte einer Kontur am Rohr bearbeiten (Plan 3D-Viewer 18.11.2026, Paket V4; Blech hat das schon in der
Skizze: Eckpunkte am Griff ziehen).

Für Polygon (Maß 1 = Eckpunkte, auch mit Bögen) und Sonderkontur mit Umriss aus dem STEP-Import. Im Fenster:
Tabelle der Punkte (x längs, y quer, bei Polygonen der Bogen zum nächsten Punkt), daneben die Form zum Ziehen.
Punkt am Griff ziehen, Doppelklick auf eine Kante setzt dort einen Punkt ein, Entf bzw. „Punkt löschen“ nimmt den
markierten weg; Zahlen in der Tabelle genau eingeben. Geprüft wird vor dem Übernehmen: mindestens 3 Punkte, keine
doppelten Punkte, Fläche nicht 0, Kanten schneiden sich nicht. Sonst bleibt OK aus und die Meldung sagt warum.

Übernehmen:
- Polygon: neue Eckpunkte; die Kontur liegt mit der Mitte ihres Hüllrechtecks an Lage/Seite, deshalb werden Lage
  und Versatz um die Verschiebung der Mitte nachgeführt, damit unveränderte Punkte am Rohr stehen bleiben.
- Sonderkontur: neuer Umriss; Schnittlänge = Umfang des neuen Umrisses, Hüllmaß = größte Ausdehnung (die gemessene
  STEP-Länge gilt nicht mehr). Das Merkmal gilt danach als von Hand geändert (Herkunft im Baum und im Preis).
Gerechnet wird wie bei jeder anderen Eingabe (schneidweg.rechnen); hier wird nichts zusätzlich gerechnet."""
import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import rechnen, schneidweg as sw, skizze as sk, stil
from .kanten_kontur import selbstschnitt

GRIFF_PX = 7


def bearbeitbar(e):
    """Hat die Kontur Eckpunkte, die man hier bearbeiten kann?"""
    try:
        return len(punkte_von(e)) >= 3
    except ValueError:
        return False


def punkte_von(e):
    """Eckpunkte [(x, y, bogen)] der Eingabe (Polygon: Maß 1; Sonderkontur: Umriss, ohne Bögen)."""
    art = e.get("art")
    if art == sw.POLYGON:
        return list(sw.punkte_roh(e.get("punkte")))
    if art == sw.SONDERKONTUR and len(e.get("umriss") or ()) >= 3:
        return [(float(x), float(y), 0.0) for x, y in e["umriss"]]
    return []


def zug(pk):
    """Linienzug mit Bögen als Punkte (wie schneidweg.punkte)."""
    out = []
    for i, (x, y, b) in enumerate(pk):
        out.append((x, y))
        if b:
            q = pk[(i + 1) % len(pk)]
            out += sw.bogen_punkte((x, y), (q[0], q[1]), b)[:-1]
    return out


def text(pk):
    """Eckpunkte als Text für Maß 1: '0,0; 40,0; 40,20,0.4142'."""
    def z(v):
        return rechnen.zahl(round(v, 3), 3).replace(",", ".")
    return "; ".join(f"{z(x)},{z(y)}" + (f",{round(b, 4)}" if b else "") for x, y, b in pk)


def pruefen(pk):
    """Fehlertext oder "" (gültig)."""
    if len(pk) < 3:
        return "Mindestens 3 Eckpunkte."
    for i, (x, y, b) in enumerate(pk):
        if not all(math.isfinite(v) for v in (x, y, b)):
            return f"Punkt {i + 1}: keine gültige Zahl."
    for i in range(len(pk)):
        a, c = pk[i], pk[(i + 1) % len(pk)]
        if math.dist(a[:2], c[:2]) < 0.01:
            return f"Punkt {i + 1} und {(i + 1) % len(pk) + 1} liegen aufeinander."
    z = zug(pk)
    flaeche = abs(sum(z[i][0] * z[(i + 1) % len(z)][1] - z[(i + 1) % len(z)][0] * z[i][1]
                      for i in range(len(z)))) / 2
    if flaeche < 0.01:
        return "Die Kontur hat keine Fläche (alle Punkte auf einer Linie)."
    s = selbstschnitt(z)
    if s is not None:
        return f"Kanten schneiden sich bei x {rechnen.zahl(s[0], 2)}, y {rechnen.zahl(s[1], 2)} – so lässt sich " \
               "die Kontur nicht schneiden."
    return ""


def _mitte(z):
    return ((max(x for x, _ in z) + min(x for x, _ in z)) / 2, (max(y for _, y in z) + min(y for _, y in z)) / 2)


def wie_kontur(e, v):
    """Richtung v (dx, dy) im Eckpunkt-System so gedreht, wie skizze.umriss_kontur die Kontur aufs Rohr legt:
    (längs, quer) [mm]."""
    x, q = v
    if e.get("quer"):
        x, q = -q, x
    w = sw._z(e.get("drehung"))
    if w and e.get("art") not in sk.DREH_OHNE:
        c, s_ = math.cos(math.radians(w)), math.sin(math.radians(w))
        x, q = x * c - q * s_, x * s_ + q * c
    if e.get("spiegeln"):
        q = -q
    return x, q


def ergebnis(e, pk):
    """(Änderung der Eingabe, Verschiebung längs, Verschiebung quer) [mm] für neue Eckpunkte pk."""
    z = zug(pk)
    if e.get("art") == sw.POLYGON:
        alt = sw.punkte(e.get("punkte"))
        m0, m1 = _mitte(alt), _mitte(z)
        dx, dq = wie_kontur(e, (m1[0] - m0[0], m1[1] - m0[1]))
        return dict(punkte=text(pk)), dx, dq
    umfang = sum(math.dist(z[i], z[(i + 1) % len(z)]) for i in range(len(z)))
    huelle = max(max(x for x, _ in z) - min(x for x, _ in z), max(y for _, y in z) - min(y for _, y in z))
    return dict(umriss=[[round(x, 3), round(y, 3)] for x, y in z], laenge=round(umfang, 2),
                huelle=round(huelle, 2)), 0.0, 0.0


class Form(QWidget):
    """Form zum Ziehen: Griffe an den Eckpunkten, Doppelklick auf eine Kante setzt einen Punkt ein."""
    geaendert = Signal()
    gewaehlt = Signal(int)

    def __init__(self, pk, vorher):
        super().__init__()
        self.pk, self.vorher, self.wahl, self._zieh = pk, vorher, None, None
        self.fehler_punkt = None
        self.setMinimumSize(360, 300)
        self.setMouseTracking(True)

    def _abb(self):
        z = zug(self.pk) + zug(self.vorher)
        x0, x1 = min(x for x, _ in z), max(x for x, _ in z)
        y0, y1 = min(y for _, y in z), max(y for _, y in z)
        w, h = max(1, self.width() - 40), max(1, self.height() - 40)
        s = min(w / max(x1 - x0, 1e-6), h / max(y1 - y0, 1e-6))
        ox = 20 + (w - (x1 - x0) * s) / 2 - x0 * s
        oy = 20 + (h - (y1 - y0) * s) / 2 + y1 * s
        return s, ox, oy

    def bild(self, x, y):
        s, ox, oy = self._abb()
        return QPointF(ox + x * s, oy - y * s)        # y nach oben

    def welt(self, pos):
        s, ox, oy = self._abb()
        return (pos.x() - ox) / s, (oy - pos.y()) / s

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), stil.farbe("#FFFFFF"))
        if len(self.pk) < 2:
            p.end()
            return
        stift = QPen(stil.farbe("#E07000"), 1.2, Qt.DashLine)
        p.setPen(stift)
        p.drawPolygon(QPolygonF([self.bild(x, y) for x, y in zug(self.vorher)]))
        p.setPen(QPen(stil.farbe("#B42318"), 2))
        p.setBrush(QBrush(QColor(180, 35, 24, 30)))
        p.drawPolygon(QPolygonF([self.bild(x, y) for x, y in zug(self.pk)]))
        for i, (x, y, _) in enumerate(self.pk):
            q = self.bild(x, y)
            p.setPen(QPen(stil.farbe("#1F4E78"), 1.5))
            p.setBrush(stil.farbe("#E67E00") if i == self.wahl else stil.farbe("#FFFFFF"))
            p.drawRect(int(q.x()) - GRIFF_PX // 2, int(q.y()) - GRIFF_PX // 2, GRIFF_PX, GRIFF_PX)
            p.drawText(q + QPointF(6, -6), str(i + 1))
        if self.fehler_punkt is not None:
            q = self.bild(*self.fehler_punkt)
            p.setPen(QPen(stil.farbe("#B42318"), 2))
            p.drawEllipse(q, 8, 8)
        p.setPen(stil.farbe("#595959"))
        p.drawText(8, self.height() - 8, "Griff ziehen · Doppelklick auf Kante: einfügen · Entf: löschen · "
                                         "orange: vorher")
        p.end()

    def punkt_bei(self, pos):
        for i, (x, y, _) in enumerate(self.pk):
            q = self.bild(x, y)
            if abs(q.x() - pos.x()) <= GRIFF_PX and abs(q.y() - pos.y()) <= GRIFF_PX:
                return i
        return None

    def kante_bei(self, pos, px=6):
        best = None
        for i in range(len(self.pk)):
            a, b = self.bild(*self.pk[i][:2]), self.bild(*self.pk[(i + 1) % len(self.pk)][:2])
            dx, dy = b.x() - a.x(), b.y() - a.y()
            lg = dx * dx + dy * dy
            t = 0.0 if lg < 1e-9 else max(0.0, min(1.0, ((pos.x() - a.x()) * dx + (pos.y() - a.y()) * dy) / lg))
            d = math.hypot(a.x() + t * dx - pos.x(), a.y() + t * dy - pos.y())
            if d <= px and (best is None or d < best[0]):
                best = (d, i)
        return None if best is None else best[1]

    def mousePressEvent(self, e):
        i = self.punkt_bei(e.position())
        self.wahl = i
        self._zieh = i
        if i is not None:
            self.gewaehlt.emit(i)
        self.update()

    def mouseMoveEvent(self, e):
        if self._zieh is None:
            self.setCursor(Qt.SizeAllCursor if self.punkt_bei(e.position()) is not None else Qt.ArrowCursor)
            return
        x, y = self.welt(e.position())
        b = self.pk[self._zieh][2]
        self.pk[self._zieh] = (round(x, 2), round(y, 2), b)
        self.geaendert.emit()
        self.update()

    def mouseReleaseEvent(self, _):
        self._zieh = None

    def mouseDoubleClickEvent(self, e):
        i = self.kante_bei(e.position())
        if i is None:
            return
        x, y = self.welt(e.position())
        a = self.pk[i]
        self.pk[i] = (a[0], a[1], 0.0)          # ein Bogen auf dieser Kante wird zur Geraden geteilt
        self.pk.insert(i + 1, (round(x, 2), round(y, 2), 0.0))
        self.wahl = i + 1
        self.geaendert.emit()
        self.gewaehlt.emit(i + 1)
        self.update()


class EckpunkteDialog(QDialog):
    """e: Eingabe der Kontur. Nach exec(): self.neu = (Änderung, dx, dq) oder None."""

    def __init__(self, parent, e, titel=""):
        super().__init__(parent)
        self.e = e
        self.neu = None
        self.setWindowTitle("Eckpunkte bearbeiten" + (f" – {titel}" if titel else ""))
        self.polygon = e.get("art") == sw.POLYGON
        self.pk = punkte_von(e)
        self.vorher = list(self.pk)
        lay = QVBoxLayout(self)
        oben = QHBoxLayout()
        lay.addLayout(oben, 1)
        links = QVBoxLayout()
        oben.addLayout(links)
        spalten = ["x längs [mm]", "y quer [mm]"] + (["Bogen"] if self.polygon else [])
        self.tab = QTableWidget(0, len(spalten))
        self.tab.setHorizontalHeaderLabels(spalten)
        self.tab.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tab.setToolTip("Eckpunkte im System der Kontur (x längs, y quer zur Mitte); Bogen = Ausbauchung zum "
                            "nächsten Punkt wie in DXF (0 = gerade)")
        self.tab.itemChanged.connect(self._tabelle_geaendert)
        self.tab.setMinimumWidth(280)
        links.addWidget(self.tab, 1)
        knoepfe = QHBoxLayout()
        self.k_neu = QPushButton("Punkt einfügen")
        self.k_neu.setToolTip("Nach dem markierten Punkt einen Punkt in der Mitte der Kante einfügen")
        self.k_neu.clicked.connect(self.einfuegen)
        self.k_weg = QPushButton("Punkt löschen")
        self.k_weg.setToolTip("Markierten Punkt löschen (Entf)")
        self.k_weg.clicked.connect(self.loeschen)
        knoepfe.addWidget(self.k_neu)
        knoepfe.addWidget(self.k_weg)
        links.addLayout(knoepfe)
        self.form = Form(self.pk, self.vorher)
        self.form.geaendert.connect(self._form_geaendert)
        self.form.gewaehlt.connect(lambda i: self.tab.selectRow(i))
        oben.addWidget(self.form, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        self.knoepfe.accepted.connect(self._ok)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        self.resize(820, 520)
        self._tabelle_fuellen()
        self._pruefen()

    # ------------------------------------------------------------ Tabelle <-> Punkte
    def _tabelle_fuellen(self):
        self.tab.blockSignals(True)
        self.tab.setRowCount(len(self.pk))
        for r, (x, y, b) in enumerate(self.pk):
            for c, v in enumerate((x, y, b)[:self.tab.columnCount()]):
                self.tab.setItem(r, c, QTableWidgetItem(rechnen.zahl(v, 3 if c < 2 else 4) if c < 2 or v else ""))
        self.tab.blockSignals(False)

    def _tabelle_geaendert(self, item):
        r, c = item.row(), item.column()
        try:
            v = float(item.text().replace(",", ".")) if item.text().strip() else 0.0
        except ValueError:
            self.info.setText(f"<span style='color:#B42318'>Punkt {r + 1}: „{item.text()}“ ist keine Zahl.</span>")
            self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(False)
            return
        x, y, b = self.pk[r]
        self.pk[r] = (v, y, b) if c == 0 else (x, v, b) if c == 1 else (x, y, v)
        self.form.update()
        self._pruefen()

    def _form_geaendert(self):
        self._tabelle_fuellen()
        self._pruefen()

    def einfuegen(self):
        r = self.tab.currentRow()
        r = len(self.pk) - 1 if r < 0 else r
        a, c = self.pk[r], self.pk[(r + 1) % len(self.pk)]
        self.pk[r] = (a[0], a[1], 0.0)
        self.pk.insert(r + 1, (round((a[0] + c[0]) / 2, 3), round((a[1] + c[1]) / 2, 3), 0.0))
        self._tabelle_fuellen()
        self.tab.selectRow(r + 1)
        self.form.wahl = r + 1
        self.form.update()
        self._pruefen()

    def loeschen(self):
        r = self.tab.currentRow()
        if r < 0 or len(self.pk) <= 3:
            self.info.setText("<span style='color:#B42318'>Mindestens 3 Eckpunkte bleiben.</span>"
                              if len(self.pk) <= 3 else "Erst einen Punkt markieren.")
            return
        del self.pk[r]
        self._tabelle_fuellen()
        self.form.wahl = None
        self.form.update()
        self._pruefen()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Delete and not self.tab.state() == QTableWidget.EditingState:
            self.loeschen()
            return
        super().keyPressEvent(e)

    # ------------------------------------------------------------ Prüfen und Übernehmen
    def _pruefen(self):
        f = pruefen(self.pk)
        z = zug(self.pk) if not f else []
        self.form.fehler_punkt = selbstschnitt(zug(self.pk)) if f.startswith("Kanten") else None
        self.form.update()
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(not f and self.pk != self.vorher)
        if f:
            self.info.setText(f"<span style='color:#B42318'>{f}</span>")
            return False
        umfang = sum(math.dist(z[i], z[(i + 1) % len(z)]) for i in range(len(z)))
        zeile = f"{len(self.pk)} Eckpunkte, Umfang {rechnen.zahl(umfang, 2)} mm"
        if not self.polygon:
            alt = sw._z(self.e.get("laenge"))
            zeile += (f". Schnittlänge bisher {rechnen.zahl(alt, 2)} mm (STEP), danach {rechnen.zahl(umfang, 2)} mm "
                      "aus den Punkten; das Merkmal gilt dann als von Hand geändert.")
        self.info.setText(zeile)
        return True

    def _ok(self):
        if not self._pruefen():
            return
        self.neu = ergebnis(self.e, self.pk)
        self.accept()
