"""Maßbilder (Plan 3D-Editor B1): kleine Zeichnung je Konturart, welches Maß welches ist. Ersetzt im
Eigenschaften-Feld den Erklärtext unter der Konturtabelle.

Gezeichnet mit QPainter (kein Bild im Paket), Farben aus stil.py (folgen dem Theme). Die Buchstaben an den
Maßpfeilen sind die Schlüssel aus schneidweg.MASSE (d, D, l, b, h, r, β), Längsrichtung des Rohrs = waagerecht.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from . import schneidweg as sw, stil

BREITE, HOEHE = 180, 100


def _pfeil(p, a, b, text, seite=1):
    """Maßlinie von a nach b mit Pfeilspitzen und Text daneben (seite: +1 über/rechts, −1 unter/links)."""
    a, b = QPointF(*a), QPointF(*b)
    p.drawLine(a, b)
    lg = math.hypot(b.x() - a.x(), b.y() - a.y()) or 1
    ux, uy = (b.x() - a.x()) / lg, (b.y() - a.y()) / lg
    for s, e in ((a, 1), (b, -1)):
        spitze = QPolygonF([s, QPointF(s.x() + e * (6 * ux - 3 * uy), s.y() + e * (6 * uy + 3 * ux)),
                            QPointF(s.x() + e * (6 * ux + 3 * uy), s.y() + e * (6 * uy - 3 * ux))])
        p.drawPolygon(spitze)
    if abs(uy) < 0.5:                       # waagerecht: Text darüber/darunter
        m = QPointF((a.x() + b.x()) / 2, a.y() - seite * 9)
    else:                                   # senkrecht: Text links/rechts
        m = QPointF(a.x() + seite * 10, (a.y() + b.y()) / 2)
    p.drawText(QRectF(m.x() - 14, m.y() - 8, 28, 16), Qt.AlignCenter, text)


def _langloch(l_, b):
    pfad = QPainterPath()
    pfad.addRoundedRect(QRectF(-l_ / 2, -b / 2, l_, b), b / 2, b / 2)
    return pfad


def zeichnen(p, art, breite=BREITE, hoehe=HOEHE):
    """Maßbild der Konturart art in das Rechteck (0, 0, breite, hoehe) zeichnen."""
    kontur, mass, flaeche = stil.farbe("#C00000"), stil.farbe(stil.TEXT), stil.farbe("#E9EEF4")
    p.setRenderHint(QPainter.Antialiasing)
    schrift = QFont(p.font())
    schrift.setPointSizeF(8.5)
    schrift.setItalic(True)
    p.setFont(schrift)
    cx, cy = breite / 2, hoehe / 2
    p.save()
    # Wandstreifen (Rohrfläche, Längsrichtung waagerecht)
    p.setPen(Qt.NoPen)
    p.setBrush(flaeche)
    p.drawRect(QRectF(4, 14, breite - 8, hoehe - 28))
    stift_k = QPen(kontur, 2)
    stift_m = QPen(mass, 1)

    def kontur_zeichnen(pfad, gestrichelt=False):
        s = QPen(stift_k)
        if gestrichelt:
            s.setStyle(Qt.DashLine)
        p.setPen(s)
        p.setBrush(Qt.NoBrush)
        p.drawPath(pfad)
        p.setPen(stift_m)
        p.setBrush(mass)

    p.translate(cx, cy)
    if art in (sw.BOHRUNG, sw.FLOWDRILL, sw.SENKUNG):
        r = 18
        pfad = QPainterPath()
        pfad.addEllipse(QPointF(0, 0), r, r)
        kontur_zeichnen(pfad, art == sw.FLOWDRILL)
        _pfeil(p, (-r, 0), (r, 0), "d")
        if art == sw.SENKUNG:
            aussen = QPainterPath()
            aussen.addEllipse(QPointF(0, 0), 30, 30)
            kontur_zeichnen(aussen, True)
            _pfeil(p, (-30, 26), (30, 26), "D", -1)
    elif art == sw.LANGLOCH:
        kontur_zeichnen(_langloch(100, 30))
        _pfeil(p, (-50, -22), (50, -22), "l")
        _pfeil(p, (58, -15), (58, 15), "b")
    elif art == sw.RECHTECK:
        pfad = QPainterPath()
        pfad.addRoundedRect(QRectF(-45, -20, 90, 40), 7, 7)
        kontur_zeichnen(pfad)
        _pfeil(p, (-45, -27), (45, -27), "b")
        _pfeil(p, (53, -20), (53, 20), "h")
        p.drawText(QRectF(-48, 8, 20, 14), Qt.AlignCenter, "r")
    elif art in (sw.SCHLITZ, sw.AUSKLINKUNG):
        rand = -breite / 2 + 4 if art == sw.AUSKLINKUNG else 0
        pfad = QPainterPath()
        if art == sw.AUSKLINKUNG:       # offen zum Ende (links)
            pfad.moveTo(rand, -18)
            pfad.lineTo(rand + 80, -18)
            pfad.lineTo(rand + 80, 18)
            pfad.lineTo(rand, 18)
            kontur_zeichnen(pfad)
            _pfeil(p, (rand, -26), (rand + 80, -26), "l")
            _pfeil(p, (rand + 88, -18), (rand + 88, 18), "b")
            p.drawText(QRectF(rand + 62, 4, 16, 14), Qt.AlignCenter, "r")
            p.drawText(QRectF(rand + 2, 20, 50, 14), Qt.AlignLeft, "Ende")
        else:                           # offen vom Rand (oben)
            top = -hoehe / 2 + 14
            pfad.moveTo(-12, top)
            pfad.lineTo(-12, top + 45)
            pfad.lineTo(12, top + 45)
            pfad.lineTo(12, top)
            kontur_zeichnen(pfad)
            _pfeil(p, (20, top), (20, top + 45), "l")
            _pfeil(p, (-12, top + 53), (12, top + 53), "b", -1)
    elif art == sw.POLYGON:
        pfad = QPainterPath()
        punkte = ((-40, 20), (30, 20), (45, -5), (0, -22), (-40, -10))
        pfad.addPolygon(QPolygonF([QPointF(x, y) for x, y in punkte]))
        pfad.closeSubpath()
        kontur_zeichnen(pfad)
        p.setPen(stift_m)
        for x, y in punkte:
            p.drawEllipse(QPointF(x, y), 2.5, 2.5)
        p.drawText(QRectF(-60, 20, 40, 14), Qt.AlignCenter, "x,y")
    elif art == sw.LOCHFELD:            # 4 × 2 Löcher, zweite Reihe versetzt
        for i in range(4):
            for j, dx in ((0, 0), (1, 12)):
                pfad = QPainterPath()
                pfad.addEllipse(QPointF(-42 + i * 24 + dx, -10 + j * 22), 6, 6)
                kontur_zeichnen(pfad)
        _pfeil(p, (-42, -24), (-18, -24), "Abstand")
        _pfeil(p, (62, -10), (62, 12), "Teilung q")
        p.drawText(QRectF(-60, 22, 70, 14), Qt.AlignLeft, "Ø d · Reihen")
    elif art == sw.DURCHBRUCH:          # Loch in der Wand, Gegenrohr (gestrichelt) schräg hindurch
        pfad = QPainterPath()
        pfad.addEllipse(QPointF(0, 0), 26, 16)
        kontur_zeichnen(pfad)
        gegen = QPainterPath(QPointF(-34, -hoehe / 2 + 10))
        gegen.lineTo(-10, hoehe / 2 - 10)
        gegen.moveTo(18, -hoehe / 2 + 10)
        gegen.lineTo(42, hoehe / 2 - 10)
        kontur_zeichnen(gegen, True)
        _pfeil(p, (-26, 24), (26, 24), "t längs", -1)
        _pfeil(p, (34, -16), (34, 16), "d")
        p.drawText(QRectF(-70, -hoehe / 2 + 8, 40, 14), Qt.AlignLeft, "Winkel")
    elif art == sw.V_AUSSCHNITT:
        pfad = QPainterPath()
        pfad.moveTo(-30, -hoehe / 2 + 14)
        pfad.lineTo(0, 22)
        pfad.lineTo(30, -hoehe / 2 + 14)
        kontur_zeichnen(pfad)
        p.drawText(QRectF(-14, -8, 28, 16), Qt.AlignCenter, "β")
    elif art == sw.GRAVUR:
        s = QPen(stil.farbe("#2E7D32"), 2)
        p.setPen(s)
        p.setBrush(Qt.NoBrush)
        pfad = QPainterPath(QPointF(-50, 0))
        for i in range(1, 11):
            pfad.lineTo(-50 + i * 10, -8 if i % 2 else 8)
        p.drawPath(pfad)
        p.setPen(stift_m)
        p.drawText(QRectF(-60, 12, 120, 14), Qt.AlignCenter, "Länge")
    else:                               # Sonderkontur, sonstige Kontur: freie Form, Länge + Hüllmaß
        pfad = QPainterPath(QPointF(-40, 10))
        pfad.cubicTo(-45, -25, 10, -30, 30, -10)
        pfad.cubicTo(50, 10, 10, 25, -40, 10)
        kontur_zeichnen(pfad)
        p.setPen(QPen(mass, 1, Qt.DotLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(-44, -24, 89, 44))
        p.setPen(stift_m)
        p.drawText(QRectF(-60, 22, 120, 14), Qt.AlignCenter, "Länge · Hüllmaß")
    p.restore()


def bild(art, breite=BREITE, hoehe=HOEHE, dpr=2.0):
    """QPixmap mit dem Maßbild (scharf auch bei 200 %)."""
    pm = QPixmap(int(breite * dpr), int(hoehe * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    zeichnen(p, art, breite, hoehe)
    p.end()
    return pm
