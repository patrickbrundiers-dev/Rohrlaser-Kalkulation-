"""Zeichenfläche des Schneidweg-Rechners: maßstäbliche Draufsicht und Seitenansicht oder Abwicklung, dazu die
Ansicht von A als kleines Bild. Bemaßung (Länge, Lage der Konturen ab Anfang), Zoom mit dem Mausrad, Verschieben des
Bildes mit gedrückter Maus auf freier Fläche, Doppelklick = einpassen. Klick auf eine Kontur markiert ihre Zeile,
Ziehen verschiebt sie (Lage längs; quer in der Abwicklung und auf Flächen, die man in der Ansicht von vorn sieht).
Jede Kontur trägt ihr Maß (Ø, Länge × Breite), die Schweißnaht (SN) erscheint rot strichpunktiert. bild() zeichnet
die Skizze ohne Bedienhinweise für die Zeichnung als PDF. Die Geometrie steht in skizze.py."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import rechnen, skizze as sk
from .schneidweg import MASSE, POLYGON, _z

ANSICHTEN, ABWICKLUNG = "Draufsicht und Seitenansicht", "Abwicklung"
MODI = (ANSICHTEN, ABWICKLUNG)
LINKS, RECHTS, OBEN, UNTEN = 96, 24, 52, 44     # Ränder [px] für Beschriftung und Bemaßung
ABSTAND_ANSICHTEN = 46                          # zwischen Draufsicht und Seitenansicht [px]
EINSATZ = 180                                   # Ansicht von A [px]

FARBE_TEIL, FARBE_FLAECHE, FARBE_SCHNITT = QColor("#1F3864"), QColor("#F4F7FB"), QColor("#DCE6F2")
FARBE_KONTUR, FARBE_WAHL, FARBE_MASS = QColor("#B42318"), QColor("#E67E00"), QColor("#595959")
FARBE_NAHT = QColor("#C0392B")


class Skizze(QWidget):
    """Skizze eines Teils. zeigen(eingaben, ergebnis) zeichnet neu; Signale: gewaehlt(Zeile der Konturtabelle),
    verschoben(Zeile, {x, abstand, seite, q}) nach dem Ziehen einer Kontur."""
    gewaehlt = Signal(int)
    verschoben = Signal(int, dict)

    def __init__(self, profil, laenge):
        super().__init__()
        self.profil, self.laenge = profil, laenge if isinstance(laenge, (int, float)) and laenge > 0 else None
        self.qs = sk.Querschnitt(profil)
        self.eingaben, self.ergebnis = {}, None
        self.modus, self.zoom, self.pan = ANSICHTEN, 1.0, QPointF(0, 0)
        self.markiert = None
        self.naht = None            # Winkel der Schweißnaht (Bezug Breitseite oben) oder None
        self.druck = False          # True: ohne Bedienhinweise und Markierung (Zeichnung als PDF)
        self.treffer = []           # [(QPolygonF Bildschirm, Lage-dict, Ansicht)] der letzten Zeichnung
        self._ziehen = None         # dict beim Ziehen einer Kontur bzw. des Bildes
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

    # ------------------------------------------------------------------ Daten
    @property
    def L(self):
        return self.laenge or 1000.0

    def zeigen(self, eingaben, ergebnis=None):
        self.eingaben, self.ergebnis = eingaben, ergebnis
        if self._ziehen is None or self._ziehen.get("art") != "kontur":
            self.update()

    def lagen(self):
        return sk.lagen(self.eingaben.get("konturen"), self.L)

    def formen(self):
        """[(x Mitte ab Anfang, Hüllmaß, Art)] je Kontur (Anzahl einzeln), x aus der Eingabe, als Muster oder
        verteilt."""
        return [(d["x"], d["huelle"], d["art"]) for d in self.lagen()]

    def modus_setzen(self, modus):
        self.modus = modus if modus in MODI else ANSICHTEN
        self.einpassen()

    def einpassen(self):
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        self.update()

    def markieren(self, zeile):
        if zeile != self.markiert:
            self.markiert = zeile
            self.update()

    # ------------------------------------------------------------------ Maßstab und Lage
    def _welt_hoehe(self):
        return self.qs.umfang if self.modus == ABWICKLUNG else self.qs.B + self.qs.H

    def massstab(self):
        """Pixel je mm (gleich in Länge und Höhe)."""
        frei_b = max(60, self.width() - LINKS - RECHTS - (EINSATZ + 12 if self.modus == ANSICHTEN else 0))
        frei_h = max(40, self.height() - OBEN - UNTEN - (ABSTAND_ANSICHTEN if self.modus == ANSICHTEN else 0))
        return min(frei_b / self.L, frei_h / max(self._welt_hoehe(), 1e-6)) * self.zoom

    def _ansichten(self):
        """[(Name, Titel, y oben [px], Querrichtung lo, hi)] der gezeichneten Bänder."""
        s, y = self.massstab(), OBEN + self.pan.y()
        if self.modus == ABWICKLUNG:
            return [("abw", "Abwicklung", y, 0.0, self.qs.umfang)]
        qs = self.qs
        return [("oben", "Draufsicht", y, -qs.B / 2, qs.B / 2),
                ("vorne", "Seitenansicht", y + qs.B * s + ABSTAND_ANSICHTEN, -qs.H / 2, qs.H / 2)]

    def _bild(self, ansicht, x, w):
        """Weltpunkt (x, Querrichtung w) -> Bildschirm. Draufsicht: w = u (vorne unten), Seitenansicht: w = v
        (oben oben), Abwicklung: w = s (von oben nach unten)."""
        s = self.massstab()
        name, _, y0, lo, hi = ansicht
        px = LINKS + self.pan.x() + x * s
        if name == "vorne":
            return QPointF(px, y0 + (hi - w) * s)
        return QPointF(px, y0 + (w - lo) * s)

    # ------------------------------------------------------------------ Zeichnen
    def paintEvent(self, _):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        g.fillRect(self.rect(), QColor("#FFFFFF"))
        self.treffer = []
        e_a, e_b = self.eingaben.get("a") or {}, self.eingaben.get("b") or {}
        lagen = self.lagen()
        ansichten = self._ansichten()
        klein = QFont(self.font())
        klein.setPointSizeF(max(7.0, self.font().pointSizeF() - 1))
        g.setFont(klein)
        for a in ansichten:
            if a[0] == "abw":
                self._abwicklung(g, a, e_a, e_b)
            else:
                self._ansicht(g, a, e_a, e_b)
            self._konturen(g, a, lagen)
            g.setPen(FARBE_MASS)
            g.drawText(QRectF(4, a[2] - 2, LINKS - 10, 18), Qt.AlignLeft, a[1])
        self._bemassung(g, ansichten, lagen)
        if self.modus == ANSICHTEN:
            self._ansicht_a(g, lagen)
        g.setPen(FARBE_MASS)
        if self.druck:
            g.end()
            return
        txt = (f"Maßstab 1 : {self._massstab_text()}" + ("" if self.laenge else "  ·  Teilelänge fehlt: Skizze mit "
                                                         "1000 mm")
               + "  ·  Mausrad = Zoom, Doppelklick = einpassen, Kontur ziehen = verschieben")
        g.drawText(QRectF(4, 4, self.width() - 8, 18), Qt.AlignLeft, txt)
        g.end()

    def _massstab_text(self):
        px_mm = self.logicalDpiX() / 25.4 or 3.78
        v = px_mm / max(self.massstab(), 1e-9)
        return rechnen.zahl(v, 1 if v < 10 else 0)

    def _ansicht(self, g, a, e_a, e_b):
        name = a[0]
        sil = sk.silhouette(self.qs, e_a, e_b, self.L, name)
        aussen = [self._bild(a, z[1], z[0]) for z in sil] + [self._bild(a, z[4], z[0]) for z in reversed(sil)]
        g.setPen(Qt.NoPen)
        g.setBrush(QBrush(FARBE_FLAECHE))
        g.drawPolygon(QPolygonF(aussen))
        for i_aus, i_sicht, i_hin in ((1, 2, 3), (4, 5, 6)):
            if any(abs(z[i_sicht] - z[i_aus]) > 1e-6 for z in sil):     # Schnittfläche des Endes sichtbar
                band = [self._bild(a, z[i_aus], z[0]) for z in sil] + \
                       [self._bild(a, z[i_sicht], z[0]) for z in reversed(sil)]
                g.setPen(Qt.NoPen)
                g.setBrush(QBrush(FARBE_SCHNITT))
                g.drawPolygon(QPolygonF(band))
                g.setPen(QPen(FARBE_TEIL, 0.8))
                g.drawPolyline(QPolygonF([self._bild(a, z[i_sicht], z[0]) for z in sil]))
            if any(abs(z[i_hin] - max(z[i_sicht], z[i_aus], key=abs)) > 1e-6 and
                   abs(z[i_hin] - z[i_sicht]) > 1e-6 for z in sil):          # verdeckte Kante hinten
                g.setPen(QPen(FARBE_TEIL, 0.6, Qt.DashLine))
                g.setBrush(Qt.NoBrush)
                g.drawPolyline(QPolygonF([self._bild(a, z[i_hin], z[0]) for z in sil]))
        g.setBrush(Qt.NoBrush)
        g.setPen(QPen(FARBE_TEIL, 1.4))
        g.drawPolygon(QPolygonF(aussen))
        # Längskanten (Flansche, Schenkel; Innenwand von Rohren und verdeckte Kanten gestrichelt)
        for w, sichtbar in sk.kanten(self.qs, name):
            g.setPen(QPen(FARBE_TEIL, 0.7, Qt.SolidLine if sichtbar else Qt.DashLine))
            g.drawLine(self._bild(a, self._x_bei(sil, w, 2 if sichtbar else 3), w),
                       self._bild(a, self._x_bei(sil, w, 5 if sichtbar else 6), w))
        # Ausklinkung: Gegenrohr andeuten (Seitenansicht)
        for e, links in ((e_a, True), (e_b, False)):
            sat = _z(e.get("sattel"))
            if sat and self.qs.r and name == "vorne":
                R, s = max(sat / 2, self.qs.r), self.massstab()
                m = self._bild(a, -R if links else self.L + R, 0)
                g.setPen(QPen(FARBE_MASS, 0.8, Qt.DashDotLine))
                g.drawEllipse(m, R * s, R * s)
        pt = sk.naht_punkt(self.qs, self.naht)
        if pt is not None:                  # Schweißnaht längs; auf der abgewandten Seite gestrichelt
            w, sicht = (pt[0], pt[1]) if name == "oben" else (pt[1], pt[0])
            g.setPen(QPen(FARBE_NAHT, 1.6, Qt.DashDotLine if sicht > -1e-6 else Qt.DotLine))
            p0, p1 = self._bild(a, self._x_bei(sil, w, 1), w), self._bild(a, self._x_bei(sil, w, 4), w)
            g.drawLine(p0, p1)
            g.drawText(QRectF(p0.x() + 4, p0.y() - 15, 40, 14), Qt.AlignLeft | Qt.AlignVCenter, "SN")
        g.setPen(FARBE_MASS)
        g.drawText(QRectF(4, a[2] + 14, LINKS - 10, 16), Qt.AlignLeft,
                   f"{'B' if name == 'oben' else 'H'} {rechnen.zahl(a[4] - a[3], 1)} mm")

    @staticmethod
    def _x_bei(sil, w, i):
        return min(sil, key=lambda z: abs(z[0] - w))[i]

    def _abwicklung(self, g, a, e_a, e_b):
        qs = self.qs
        la, lb = sk.ende_abwicklung(qs, e_a), sk.ende_abwicklung(qs, e_b)
        umriss = [self._bild(a, d, s) for s, d in la] + [self._bild(a, self.L - d, s) for s, d in reversed(lb)]
        g.setPen(QPen(FARBE_TEIL, 1.4))
        g.setBrush(QBrush(FARBE_FLAECHE))
        g.drawPolygon(QPolygonF(umriss))
        g.setBrush(Qt.NoBrush)
        for i, (name, s0, s1) in enumerate(qs.abwicklung_streifen()):
            if i:
                g.setPen(QPen(FARBE_TEIL, 0.7, Qt.DashLine))     # Kante bzw. Biegelinie
                g.drawLine(self._bild(a, self._d_bei(la, s0), s0), self._bild(a, self.L - self._d_bei(lb, s0), s0))
            p = self._bild(a, 0, (s0 + s1) / 2)
            g.setPen(FARBE_MASS)
            g.drawText(QRectF(4, p.y() - 8, LINKS - 12, 16), Qt.AlignRight | Qt.AlignVCenter, name)
            q = self._bild(a, self.L, s1)
            g.drawText(QRectF(q.x() + 6, (self._bild(a, 0, s0).y() + q.y()) / 2 - 8, RECHTS + 60, 16),
                       Qt.AlignLeft | Qt.AlignVCenter, rechnen.zahl(s1 - s0, 1))
        s_n = sk.naht_s(qs, self.naht)
        if s_n is not None:
            g.setPen(QPen(FARBE_NAHT, 1.6, Qt.DashDotLine))
            p0 = self._bild(a, self._d_bei(la, s_n), s_n)
            g.drawLine(p0, self._bild(a, self.L - self._d_bei(lb, s_n), s_n))
            g.drawText(QRectF(p0.x() + 4, p0.y() - 15, 40, 14), Qt.AlignLeft | Qt.AlignVCenter, "SN")

    @staticmethod
    def _d_bei(linie, s):
        return min(linie, key=lambda z: abs(z[0] - s))[1]

    def _konturen(self, g, a, lagen):
        qs = self.qs
        for d in lagen:
            pts3, n = sk.platzieren(qs, d)
            if a[0] == "abw":
                s0 = sk.s_lage(qs, d["eingabe"])
                if s0 > qs.umfang:
                    s0 -= qs.umfang
                umr = sk.umriss_kontur(d["eingabe"]) or [(0.0, 0.0)]
                poly = QPolygonF([self._bild(a, d["x"] + dx, s0 + dq) for dx, dq in umr])
                sicht = 1.0
            else:
                sicht = sk.sichtbar(n, a[0])
                if abs(sicht) < 0.12:
                    continue                # Fläche von der Kante gesehen
                idx = 1 if a[0] == "oben" else 2
                poly = QPolygonF([self._bild(a, p[0], p[idx]) for p in pts3])
            wahl = d["zeile"] == self.markiert and not self.druck
            farbe = FARBE_WAHL if wahl else FARBE_KONTUR
            if d.get("verteilt"):
                farbe = QColor(farbe).lighter(135)
            stift = QPen(farbe, 2.2 if wahl else 1.3, Qt.SolidLine if sicht > 0 else Qt.DashLine)
            g.setPen(stift)
            g.setBrush(QBrush(QColor(farbe.red(), farbe.green(), farbe.blue(), 40)) if sicht > 0 else Qt.NoBrush)
            r = poly.boundingRect()
            if r.width() < 3 and r.height() < 3:
                g.drawEllipse(r.center(), 2.5, 2.5)
            else:
                g.drawPolygon(poly)
            e = d["eingabe"]
            if e.get("art") == "Senkung" and _z(e.get("D")) > _z(e.get("d")) > 0:      # Senk-Ø dünn
                f, c = _z(e.get("D")) / _z(e.get("d")), r.center()
                g.setPen(QPen(farbe, 0.8, Qt.DotLine))
                g.setBrush(Qt.NoBrush)
                g.drawPolygon(QPolygonF([c + (pt - c) * f for pt in poly]))
            g.setBrush(Qt.NoBrush)
            if d["nr"] == 0 and sicht > 0:       # Maß an die erste Kontur der Zeile (Muster: Anzahl ×)
                n = int(_z(e.get("anzahl")) or 1)
                g.setPen(farbe)
                g.drawText(QRectF(r.right() + 3, r.top() - 14, 220, 14), Qt.AlignLeft | Qt.AlignVCenter,
                           (f"{n} × " if n > 1 else "") + sk.kurz(e))
            self.treffer.append((poly, d, a))

    def _bemassung(self, g, ansichten, lagen):
        oben, unten = ansichten[0], ansichten[-1]
        y_ende = max(self._bild(unten, 0, unten[3]).y(), self._bild(unten, 0, unten[4]).y())
        y = y_ende + 22
        x0, x1 = self._bild(unten, 0, 0).x(), self._bild(unten, self.L, 0).x()
        g.setPen(QPen(FARBE_MASS, 0.8))
        g.drawLine(QPointF(x0, y_ende + 4), QPointF(x0, y + 4))
        g.drawLine(QPointF(x1, y_ende + 4), QPointF(x1, y + 4))
        g.drawLine(QPointF(x0, y), QPointF(x1, y))
        for x, r in ((x0, 1), (x1, -1)):
            g.drawLine(QPointF(x, y), QPointF(x + 7 * r, y - 3))
            g.drawLine(QPointF(x, y), QPointF(x + 7 * r, y + 3))
        g.drawText(QRectF(x0, y + 1, max(x1 - x0, 80), 16), Qt.AlignHCenter, f"{rechnen.zahl(self.L, 1)} mm")
        # Lage der Konturen ab Anfang: Maßzahlen über der oberen Ansicht (nur angegebene Lagen, verteilt grau)
        y_top = min(self._bild(oben, 0, oben[3]).y(), self._bild(oben, 0, oben[4]).y())
        werte = sorted({round(d["x"], 1): d.get("verteilt", False) for d in lagen}.items())
        letzte = -1e9
        for x, verteilt in werte:
            px = self._bild(oben, x, 0).x()
            g.setPen(QPen(FARBE_MASS if not verteilt else QColor("#A0A0A0"), 0.6, Qt.DotLine))
            g.drawLine(QPointF(px, y_top - 2), QPointF(px, y_top - 10))
            if px - letzte >= 14:
                g.save()
                g.translate(px + 4, y_top - 12)
                g.rotate(-90)
                g.setPen(FARBE_MASS if not verteilt else QColor("#A0A0A0"))
                g.drawText(QRectF(0, -12, 40, 14), Qt.AlignLeft | Qt.AlignVCenter, rechnen.zahl(x, 1))
                g.restore()
                letzte = px

    def _ansicht_a(self, g, lagen):
        """Ansicht von A (Querschnitt) oben rechts mit Flächennamen und der Lage der Konturen."""
        qs = self.qs
        box = QRectF(self.width() - EINSATZ - 6, OBEN - 26, EINSATZ, EINSATZ)
        g.setPen(QPen(QColor("#D0D7E2"), 1))
        g.setBrush(QBrush(QColor("#FFFFFF")))
        g.drawRect(box)
        m = min((box.width() - 130) / max(qs.B, 1e-6), (box.height() - 80) / max(qs.H, 1e-6))
        c = box.center() - QPointF(0, 6)

        def p(u, v):
            return QPointF(c.x() + u * m, c.y() - v * m)
        pfad = QPainterPath()
        for poly in qs.umriss:
            pfad.addPolygon(QPolygonF([p(u, v) for u, v in poly] + [p(*poly[0])]))
        pfad.setFillRule(Qt.OddEvenFill)
        g.setPen(QPen(FARBE_TEIL, 1.2))
        g.setBrush(QBrush(FARBE_SCHNITT))
        g.drawPath(pfad)
        g.setPen(FARBE_MASS)
        if qs.r:
            marken = [(f"{w:g}° " + t.split(" ")[0], (math.sin(math.radians(w)), math.cos(math.radians(w))), w)
                      for t, w in sk.RUND_SEITEN.items()]
            for name, (nu, nv), _ in marken:
                self._marke(g, p(nu * (qs.r + 5 / m), nv * (qs.r + 5 / m)), (nu, nv), name)
        else:
            for f in qs.flaechen:
                self._marke(g, p(f.mitte[0] + f.n[0] * 5 / m, f.mitte[1] + f.n[1] * 5 / m), f.n,
                            sk.seite_anzeige(qs, f.name).replace("Flansch ", "Fl. ").replace("Schenkel ", "Schenkel\u00a0"))
        g.setPen(QPen(FARBE_KONTUR, 1))
        g.setBrush(QBrush(FARBE_KONTUR))
        for d in lagen:
            pts3, _ = sk.platzieren(qs, d)
            u = sum(x[1] for x in pts3) / len(pts3)
            v = sum(x[2] for x in pts3) / len(pts3)
            g.drawEllipse(p(u, v), 2.5, 2.5)
        pt = sk.naht_punkt(qs, self.naht)
        if pt is not None:
            g.setPen(QPen(FARBE_NAHT, 1))
            g.setBrush(QBrush(FARBE_NAHT))
            q = p(*pt)
            g.drawEllipse(q, 4, 4)
            g.drawText(QRectF(q.x() - 30, q.y() - 8, 26, 16), Qt.AlignRight | Qt.AlignVCenter, "SN")
        g.setPen(FARBE_MASS)
        g.setBrush(Qt.NoBrush)
        g.drawText(QRectF(box.x() + 4, box.bottom() - 15, box.width() - 8, 14), Qt.AlignCenter,
                   f"Ansicht von A · {rechnen.zahl(qs.B, 1)} × {rechnen.zahl(qs.H, 1)}" if not qs.r else
                   f"Ansicht von A · Ø {rechnen.zahl(qs.B, 1)}")

    @staticmethod
    def _marke(g, q, n, text):
        """Beschriftung neben einem Punkt, von der Fläche weg (Normale n)."""
        if n[0] > 0.5:
            g.drawText(QRectF(q.x(), q.y() - 7, 70, 14), Qt.AlignLeft | Qt.AlignVCenter, text)
        elif n[0] < -0.5:
            g.drawText(QRectF(q.x() - 70, q.y() - 7, 70, 14), Qt.AlignRight | Qt.AlignVCenter, text)
        elif n[1] > 0:
            g.drawText(QRectF(q.x() - 40, q.y() - 15, 80, 14), Qt.AlignCenter, text)
        else:
            g.drawText(QRectF(q.x() - 40, q.y() + 1, 80, 14), Qt.AlignCenter, text)

    def hoehe_fuer(self, breite, modus=ANSICHTEN):
        """Höhe [px], bei der die Skizze in der Breite breite den Platz füllt (Maßstab durch die Länge begrenzt)."""
        m = modus if modus in MODI else ANSICHTEN
        frei_b = max(60, breite - LINKS - RECHTS - (EINSATZ + 12 if m == ANSICHTEN else 0))
        welt = self.qs.umfang if m == ABWICKLUNG else self.qs.B + self.qs.H
        h = OBEN + UNTEN + (ABSTAND_ANSICHTEN if m == ANSICHTEN else 0) + welt * frei_b / self.L
        return max(h, EINSATZ + OBEN if m == ANSICHTEN else 0)

    def bild(self, breite, hoehe, modus=ANSICHTEN, faktor=2):
        """Skizze ohne Bedienhinweise als QImage (breite × hoehe Punkte, faktor-fach aufgelöst) für die Zeichnung.
        Ergebnis: (QImage, Pixel je mm in Punkten)."""
        from PySide6.QtGui import QImage
        alt = (self.size(), self.modus, self.zoom, self.pan, self.druck)
        self.resize(int(breite), int(hoehe))
        self.modus, self.zoom, self.pan, self.druck = modus if modus in MODI else ANSICHTEN, 1.0, QPointF(0, 0), True
        img = QImage(int(breite * faktor), int(hoehe * faktor), QImage.Format_ARGB32)
        img.setDevicePixelRatio(faktor)
        img.fill(QColor("#FFFFFF"))
        self.render(img)
        s = self.massstab()
        self.resize(alt[0])
        self.modus, self.zoom, self.pan, self.druck = alt[1:]
        return img, s

    # ------------------------------------------------------------------ Maus
    def treffer_bei(self, pos):
        """Kontur unter dem Mauszeiger: (Lage-dict, Ansicht) oder None (die kleinste, wenn mehrere)."""
        kand = []
        for poly, d, a in self.treffer:
            r = poly.boundingRect().adjusted(-4, -4, 4, 4)
            if r.contains(pos):
                kand.append((r.width() * r.height(), id(d), d, a))
        return min(kand, key=lambda k: (k[0], k[1]))[2:] if kand else None

    def mousePressEvent(self, ereignis):
        pos = ereignis.position()
        t = self.treffer_bei(pos) if ereignis.button() == Qt.LeftButton else None
        if t:
            d, a = t
            self.markieren(d["zeile"])
            self.gewaehlt.emit(d["zeile"])
            self._ziehen = dict(art="kontur", start=pos, lage=d, ansicht=a, e=dict(d["eingabe"]))
        else:
            self._ziehen = dict(art="bild", start=pos, pan=QPointF(self.pan))

    def mouseMoveEvent(self, ereignis):
        pos = ereignis.position()
        z = self._ziehen
        if z is None:
            t = self.treffer_bei(pos)
            self.setCursor(Qt.OpenHandCursor if t else Qt.ArrowCursor)
            if t:
                QToolTip.showText(ereignis.globalPosition().toPoint(), self.beschreibung(t[0]), self)
            return
        if z["art"] == "bild":
            self.pan = z["pan"] + (pos - z["start"])
            self.update()
            return
        neu = self.neue_lage(z, pos)
        if neu:
            z["neu"] = neu
            e = self.eingaben["konturen"][z["lage"]["zeile"]]
            e.update(neu)
            for k_, v in neu.items():
                if v is None:
                    e.pop(k_, None)
            self.update()

    def mouseReleaseEvent(self, ereignis):
        z, self._ziehen = self._ziehen, None
        if z and z["art"] == "kontur" and z.get("neu"):
            self.verschoben.emit(z["lage"]["zeile"], z["neu"])
        self.update()

    def mouseDoubleClickEvent(self, _):
        self.einpassen()

    def wheelEvent(self, ereignis):
        stufen = ereignis.angleDelta().y() / 120
        if not stufen:
            return
        alt = self.massstab()
        self.zoom = min(max(self.zoom * 1.25 ** stufen, 0.5), 400.0)
        neu = self.massstab()
        pos = ereignis.position()
        # Punkt unter dem Mauszeiger bleibt stehen
        bx = (pos.x() - LINKS - self.pan.x()) / alt
        by = (pos.y() - OBEN - self.pan.y()) / alt
        self.pan = QPointF(pos.x() - LINKS - bx * neu, pos.y() - OBEN - by * neu)
        self.update()

    def neue_lage(self, z, pos):
        """Neue Eingaben einer gezogenen Kontur: {x, abstand, seite, q}."""
        s = self.massstab()
        d, a, e = z["lage"], z["ansicht"], z["e"]
        dx, dy = (pos.x() - z["start"].x()) / s, (pos.y() - z["start"].y()) / s
        n = int(_z(e.get("anzahl")) or 1)
        neu = {}
        if e.get("x") is not None:
            neu["x"] = round(max(0.0, e["x"] + dx), 1)
        elif n == 1 or _z(e.get("abstand")):
            neu["x"] = round(max(0.0, d["x"] - d["nr"] * _z(e.get("abstand")) + dx), 1)
        else:                       # verteilte Reihe wird zum Muster mit gleichem Abstand
            ab = self.L / (n + 1)
            neu["x"], neu["abstand"] = round(max(0.0, d["x"] - d["nr"] * ab + dx), 1), round(ab, 1)
        qs = self.qs
        if a[0] == "abw":
            seite, q = sk.s_zu_seite(qs, (sk.s_lage(qs, e) + dy) % qs.umfang)
            neu.update(self._seite_werte(seite, q))
        elif qs.r:
            phi = math.radians(sk.winkel_aus_text(e.get("seite")) or 0.0)
            u, v = qs.r * math.sin(phi), qs.r * math.cos(phi)
            if a[0] == "oben":
                u = max(-qs.r, min(qs.r, u + dy))
                w = math.degrees(math.asin(u / qs.r))
                w = w if v >= 0 else 180 - w
            else:
                v = max(-qs.r, min(qs.r, v - dy))
                w = math.degrees(math.acos(v / qs.r))
                w = w if u >= 0 else 360 - w
            neu.update(self._seite_werte(sk.winkel_text(round(w % 360, 1)), 0.0))
        else:
            f = qs.flaeche(e.get("seite"))
            anteil = f.dir[0] if a[0] == "oben" else -f.dir[1]
            if f is not None and abs(anteil) > 0.7:
                q = _z(e.get("q")) + dy * anteil
                q = max(-f.breite / 2, min(f.breite / 2, q))
                neu.update(self._seite_werte(f.name, round(q, 1)))
        return neu

    def _seite_werte(self, seite, q):
        erste = self.qs.seiten()[0] if self.qs.seiten() else None
        if self.qs.r:
            w = sk.winkel_aus_text(seite)
            return dict(seite=None if not w else w, q=None)
        return dict(seite=None if seite == erste else seite, q=q or None)

    def beschreibung(self, d):
        e = d["eingabe"]
        masse = (f"{len(sk.punkte(e.get('punkte')))} Eckpunkte" if e.get("art") == POLYGON else
                 " × ".join(rechnen.zahl(_z(e.get(k_)), 2) for k_, _ in MASSE.get(e.get("art"), ()) if _z(e.get(k_))))
        if self.qs.r:
            seite = sk.winkel_text(sk.winkel_aus_text(e.get("seite")) or 0.0)
        else:
            f = self.qs.flaeche(e.get("seite"))
            seite = (f.name if f else "–") + (f", quer {rechnen.zahl(_z(e.get('q')), 1)} mm" if _z(e.get("q")) else "")
        return (f"{e.get('art')} {masse}\nLage ab Anfang {rechnen.zahl(d['x'], 1)} mm"
                + (" (nicht angegeben, verteilt)" if d.get("verteilt") else "") + f"\nSeite {seite}"
                + (f"\n{e['text']}" if e.get("text") else ""))
