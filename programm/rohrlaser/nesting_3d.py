"""3D-Ansicht einer Stange im Nesting-Arbeitsplatz (Nesting-Arbeitsplatz 2.0, Patrick 24.11.2026).

Zeichnet die gewählte Stange als Rohr (Rundrohr als Zylinder mit 24 Facetten, Quadrat-/Rechteckrohr als Kasten) in
einer Parallelprojektion mit QPainter (kein OpenGL nötig, läuft auf jedem PC). Die Abschnitte kommen aus genau
denselben Daten wie das 2D-Bild (nesting_vergleich.anzeige_stangen bzw. nesting_dialog.segmente): Endbeschnitt,
Teile in Positionsfarbe mit ihren Schnittkanten (Gehrungen schräg wie im Stangenbild), Schnittfugen, Rest grün bzw.
Verschnitt rot, Greiferrest grau. Maus links ziehen: drehen, Mausrad: Zoom, Klick auf ein Teil: hervorheben
(Signal teil_gewaehlt mit dem Platz auf der Stange), Doppelklick: Ansicht zurücksetzen.
"""
import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import stil

FACETTEN = 24


def _drehen(p, gier, nick):
    """Punkt (x längs, y quer, z hoch) drehen: um die Hochachse (gier), dann um die Querachse (nick)."""
    x, y, z = p
    cg, sg = math.cos(gier), math.sin(gier)
    x, y = x * cg - y * sg, x * sg + y * cg
    cn, sn = math.cos(nick), math.sin(nick)
    y, z = y * cn - z * sn, y * sn + z * cn
    return x, y, z


def querschnitt_punkte(q, b, h):
    """Umriss des Querschnitts [(y, z)]: Kasten 4 Ecken (b × h), sonst Kreis mit FACETTEN Ecken (Ø b)."""
    if q and q[0] == "Kasten":
        return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]
    r = b / 2
    return [(r * math.cos(2 * math.pi * i / FACETTEN), r * math.sin(2 * math.pi * i / FACETTEN))
            for i in range(FACETTEN)]


class Nesting3D(QWidget):
    """setzen(stange, segmente, farben, querschnitt): stange = Stange im Format des Schnittplans (anzeige_stangen),
    segmente = [(art, von, bis, Teil-Dict oder None)], farben = {ref: Farbe}, querschnitt = Gruppe.querschnitt."""
    teil_gewaehlt = Signal(int)

    def __init__(self):
        super().__init__()
        self.stange, self.segmente, self.farben, self.q = None, [], {}, ()
        self.gier, self.nick, self.zoom = math.radians(-28), math.radians(24), 1.0
        self.auswahl, self._maus, self._flaechen = None, None, []
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setToolTip("Ziehen: drehen · Mausrad: Zoom · Klick: Teil hervorheben · Doppelklick: Ansicht zurück")

    def setzen(self, stange, segmente, farben=None, querschnitt=()):
        self.stange, self.segmente, self.farben, self.q = stange, list(segmente), dict(farben or {}), querschnitt
        self.auswahl = None
        self.update()

    def zuruecksetzen(self):
        self.gier, self.nick, self.zoom = math.radians(-28), math.radians(24), 1.0
        self.update()

    # ------------------------------------------------------------------ Bedienung
    def mousePressEvent(self, e):
        self._maus = QPointF(e.position())
        for poly, nr in reversed(self._flaechen):
            if poly.containsPoint(QPointF(e.position()), Qt.OddEvenFill):
                self.auswahl = nr
                self.teil_gewaehlt.emit(nr)
                self.update()
                break

    def mouseMoveEvent(self, e):
        if self._maus is None or not (e.buttons() & Qt.LeftButton):
            return
        d = QPointF(e.position()) - self._maus
        self._maus = QPointF(e.position())
        self.gier += d.x() * 0.01
        self.nick = max(-1.45, min(1.45, self.nick + d.y() * 0.01))
        self.update()

    def mouseReleaseEvent(self, _):
        self._maus = None

    def mouseDoubleClickEvent(self, _):
        self.zuruecksetzen()

    def wheelEvent(self, e):
        self.zoom = max(0.3, min(40.0, self.zoom * (1.15 if e.angleDelta().y() > 0 else 1 / 1.15)))
        self.update()

    # ------------------------------------------------------------------ Zeichnen
    def _masse(self):
        q = self.q or ()
        if q and q[0] == "Kasten":
            return max(q[1], 1.0), max(q[2], 1.0)
        if q and q[0] == "Rund":
            return 2 * max(q[1], 0.5), 2 * max(q[1], 0.5)
        return 40.0, 40.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), stil.farbe("#F7F9FB"))
        if not self.stange:
            p.setPen(stil.farbe(stil.TEXT_GRAU))
            p.drawText(self.rect(), Qt.AlignCenter, "Stange im Bild wählen, um sie in 3D zu sehen.")
            return
        p.setRenderHint(QPainter.Antialiasing, True)
        laenge = self.stange["stange"]
        b, h = self._masse()
        # Maßstab: Stange füllt die Breite (Zoom ändert ihn), Querschnitt überhöht, damit man ihn sieht
        ueber = max(1.0, laenge / max(b, h) / 18.0)
        quer = [(y * ueber, z * ueber) for y, z in querschnitt_punkte(self.q, b, h)]
        m = 0.85 * self.width() / max(laenge, 1.0) * self.zoom
        mx, my = self.width() / 2, self.height() / 2

        def proj(x, y, z):
            x, y, z = _drehen((x - laenge / 2, y, z), self.gier, self.nick)
            return QPointF(mx + x * m, my - z * m), y          # y = Tiefe (größer = weiter hinten)

        flaechen = []        # (Tiefe, Polygon, Farbe, Rand, Teil-Platz)
        n_teil = 0
        for art, von, bis, t in self.segmente:
            if bis - von <= 0:
                continue
            if art == "teil":
                farbe = QColor(self.farben.get(t.get("ref"), stil.TEIL_FARBEN[0])) if t else QColor("#4E79A7")
                if self.auswahl == n_teil:
                    farbe = stil.farbe("#FF7F0E")
                platz = n_teil
                n_teil += 1
            else:
                farbe = {"end": stil.farbe("#A6A6A6"), "schnitt": stil.farbe("#333333"), "rest": stil.farbe("#A5D6A7"),
                         "abfall": stil.farbe("#E15759"), "greif": stil.farbe("#7F7F7F")}.get(art, stil.farbe("#BBBBBB"))
                platz = None
            for i in range(len(quer)):
                (y1, z1), (y2, z2) = quer[i], quer[(i + 1) % len(quer)]
                ecken = [proj(von, y1, z1), proj(bis, y1, z1), proj(bis, y2, z2), proj(von, y2, z2)]
                tiefe = sum(e[1] for e in ecken) / 4
                # Rückseiten nicht zeichnen (Normale zeigt vom Betrachter weg)
                a, bb, c = ecken[0][0], ecken[1][0], ecken[3][0]
                kreuz = (bb.x() - a.x()) * (c.y() - a.y()) - (bb.y() - a.y()) * (c.x() - a.x())
                if kreuz > 0:
                    continue
                licht = 0.62 + 0.38 * abs(math.cos(math.atan2(z1 + z2, y1 + y2) - self.nick))
                f = QColor(farbe)
                f = QColor(int(f.red() * licht), int(f.green() * licht), int(f.blue() * licht))
                flaechen.append((tiefe, QPolygonF([e[0] for e in ecken]), f, platz))
        # Stirnflächen (Anfang und Ende der Stange)
        for x in (0.0, laenge):
            pts = [proj(x, y, z) for y, z in quer]
            flaechen.append((sum(e[1] for e in pts) / len(pts) - 1e-3, QPolygonF([e[0] for e in pts]),
                             stil.farbe("#D9DEE4"), None))
        flaechen.sort(key=lambda f: -f[0])
        self._flaechen = []
        rand = QPen(stil.farbe("#30363D"), 0.6)
        for _, poly, f, platz in flaechen:
            p.setPen(rand)
            p.setBrush(f)
            p.drawPolygon(poly)
            if platz is not None:
                self._flaechen.append((poly, platz))
        p.setPen(stil.farbe(stil.TEXT))
        p.drawText(8, 18, f"Stange {self.stange.get('nr', '')}: {self.stange['profil']} · "
                          f"{self.stange['stange']:g} mm · Querschnitt {ueber:.0f}-fach überhöht".replace(".", ","))
        p.end()
