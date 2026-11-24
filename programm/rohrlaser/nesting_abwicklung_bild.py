"""Abwicklung je Materialstange als Arbeitsansicht des Nesting-Arbeitsplatzes (Patrick 24.11.2026, Master-Auftrag
„Stangenabwicklung auf CAD/CAM-Niveau“). Zeichnet nesting_abwicklung.stange (exakte Außenhaut, Teile an ihrem Platz
aus dem Nesting-Ergebnis) und rechnet selbst nichts: alle Maße kommen aus den Daten.

Darstellung: Länge maßstäblich (waagerecht oder senkrecht), Umfang quer (Rundrohr mit Winkelskala 0–360°, Quadrat-/
Rechteckrohr mit Seiten und Eckradien als Bänder). Materialanfang/-ende, Endbeschnitt, Teile in Positionsfarbe mit
ihren Schnittkanten (Gehrung schräg), Schnittfugen, Rest (grün verwertbar, rot schraffiert Verschnitt), Greiferrest
(Einspannbereich), Konturen rot, Gravur grün, Schweißnaht. Ebenen einzeln ein-/ausblendbar: Bemaßung, Schnitte,
Konturen, Reste, Raster. Umfang 1:1 oder auf die Höhe gestreckt.

Bedienung: Mausrad zoomt um den Mauszeiger, Ziehen (links auf freier Fläche oder mittlere Taste) verschiebt,
Doppelklick auf freie Fläche passt ein. Klick auf ein Teil wählt es (Signal teil_gewaehlt), Klick auf Rest/Schnitt/
Endbeschnitt zeigt seine Länge (bereich_gewaehlt). Messen: zwei Klicks, Abstand längs und am Umfang. Rechtsklick auf
ein Teil: Kontextmenü (zur Position, gleiche Teile hervorheben, im 3D zeigen).
"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QMenu, QSizePolicy, QWidget

from . import rechnen, stil, stangen_abwicklung as sa

EBENEN = (("bemassung", "Bemaßung"), ("schnitte", "Schnittpositionen"), ("konturen", "Konturen"),
          ("reste", "Reste markieren"), ("raster", "Seiten/Winkel"))


def _z(v, n=1):
    return rechnen.zahl(v, n)


def _schritt(pixel_je_mm, ziel_px=70):
    """Runder Abstand der Lineal-Striche [mm] für etwa ziel_px Pixel."""
    roh = ziel_px / max(pixel_je_mm, 1e-9)
    for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if s >= roh:
            return s
    return 10000


class AbwicklungAnsicht(QWidget):
    teil_gewaehlt = Signal(int)         # Nummer des Teils in daten['teile'] (−1 = keins)
    bereich_gewaehlt = Signal(str)      # Text zum angeklickten Bereich (Rest, Schnittfuge …)
    gemessen = Signal(str)
    zur_position = Signal(str)          # Bezug (ref)
    im_3d = Signal(int)

    RAND_L, RAND_R, RAND_O, RAND_U = 74, 24, 34, 86

    def __init__(self, technisch=False):
        super().__init__()
        self.daten, self.farben, self.rest_ok = None, {}, None
        self.auswahl, self.markiert_ref = None, None
        self.ebenen = {k: True for k, _ in EBENEN}
        self.technisch = technisch
        self.senkrecht, self.eins_zu_eins = False, False
        self.zoom, self.versatz = 1.0, 0.0
        self.messen, self.messpunkte = False, []
        self._ziehen, self._flaechen, self._bereiche = None, [], []
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip("Mausrad: Zoom · Ziehen: verschieben · Doppelklick: einpassen · Klick: Teil wählen · "
                        "Rechtsklick: Menü")

    # ------------------------------------------------------------------ Daten
    def setzen(self, daten, farben, rest_ok=None):
        self.daten, self.rest_ok = daten, rest_ok
        self.farben = {r: QColor(f) for r, f in (farben or {}).items()}
        if self.auswahl is not None and (not daten or self.auswahl >= len(daten["teile"])):
            self.auswahl = None
        self.messpunkte = []
        self.update()

    def ebene(self, name, an):
        self.ebenen[name] = bool(an)
        self.update()

    def einpassen(self):
        self.zoom, self.versatz = 1.0, 0.0
        self.update()

    def zoom_um(self, faktor, mitte_px=None):
        """Zoom längs um faktor, der Punkt unter mitte_px bleibt stehen."""
        alt = self.zoom
        self.zoom = max(1.0, min(200.0, self.zoom * faktor))
        if mitte_px is not None:
            a = self._lang_px()
            rel = (mitte_px - a[0] - self.versatz)
            self.versatz -= rel * (self.zoom / alt - 1)
        self._grenzen()
        self.update()

    def teil_zeigen(self, i):
        """Teil i wählen und ins Bild holen."""
        if not self.daten or not (0 <= i < len(self.daten["teile"])):
            return
        self.auswahl = i
        t = self.daten["teile"][i]
        a0, a1 = self._lang_px()
        mm = self._mm()
        mitte = (t["von"] + t["bis"]) / 2 * mm
        if not (0 <= mitte + self.versatz <= a1 - a0):
            self.versatz = (a1 - a0) / 2 - mitte
            self._grenzen()
        self.update()

    # ------------------------------------------------------------------ Maßstab
    def _lang_px(self):
        """(Anfang, Ende) der Zeichenfläche in Längsrichtung [px]."""
        if self.senkrecht:
            return self.RAND_O + 18, self.height() - 24
        return self.RAND_L, self.width() - self.RAND_R

    def _quer_px(self):
        if self.senkrecht:
            return self.RAND_L + 30, self.width() - 160
        return self.RAND_O, self.height() - self.RAND_U

    def _mm(self):
        a0, a1 = self._lang_px()
        return max(a1 - a0, 50) / max(self.daten["laenge"], 1.0) * self.zoom

    def _mm_quer(self):
        if self.eins_zu_eins:
            return self._mm()
        q0, q1 = self._quer_px()
        return max(min(q1 - q0, 300), 40) / max(self.daten["umfang"], 1.0)

    def _grenzen(self):
        if not self.daten:
            return
        a0, a1 = self._lang_px()
        voll = self.daten["laenge"] * self._mm()
        self.versatz = min(0.0, max(self.versatz, (a1 - a0) - voll))

    def pkt(self, x, t):
        """Bildpunkt zu (x längs ab Materialanfang, t am Umfang) [mm]."""
        a0, _ = self._lang_px()
        q0, _ = self._quer_px()
        lx = a0 + self.versatz + x * self._mm()
        qy = q0 + t * self._mm_quer()
        return QPointF(qy, lx) if self.senkrecht else QPointF(lx, qy)

    def mm_bei(self, punkt):
        """(x, t) [mm] zum Bildpunkt."""
        a0, _ = self._lang_px()
        q0, _ = self._quer_px()
        lx, qy = (punkt.y(), punkt.x()) if self.senkrecht else (punkt.x(), punkt.y())
        return (lx - a0 - self.versatz) / self._mm(), (qy - q0) / self._mm_quer()

    def _rechteck(self, x0, x1, t0, t1):
        a, b = self.pkt(x0, t0), self.pkt(x1, t1)
        return QRectF(a, b).normalized()

    # ------------------------------------------------------------------ Zeichnen
    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), stil.farbe("#F7F9FB"))
        d = self.daten
        if not d:
            p.setPen(stil.farbe(stil.TEXT_GRAU))
            p.drawText(self.rect(), Qt.AlignCenter, "Stange wählen. Ohne Querschnitt (Profil unbekannt) keine "
                                                    "Abwicklung.")
            p.end()
            return
        self._grenzen()
        U, L = d["umfang"], d["laenge"]
        klein = QFont(self.font())
        klein.setPointSizeF(max(7.0, klein.pointSizeF() - 1.5))
        p.setFont(klein)
        band = self._rechteck(0, L, 0, U)
        p.save()
        p.setClipRect(QRectF(self.rect()))
        p.fillRect(band, stil.farbe("#E9EDF1"))
        self._flaechen, self._bereiche = [], []
        # Bereiche längs aus dem Schnittplan
        for art, von, bis in d["bereiche"]:
            r = self._rechteck(von, bis, 0, U)
            self._bereiche.append((r, art, von, bis))
            if art == "end":
                p.fillRect(r, stil.farbe("#A6A6A6"))
            elif art == "greif":
                p.fillRect(r, stil.farbe("#E06666"))
            elif art == "schnitt":
                p.fillRect(r if r.width() >= 1 or self.senkrecht else QRectF(r.left(), r.top(), 1, r.height()),
                           stil.farbe("#30363D"))
            elif art == "rest" and self.ebenen["reste"]:
                if self.rest_ok:
                    p.fillRect(r, stil.farbe("#A5D6A7"))
                else:
                    p.fillRect(r, stil.farbe("#F6D5D5"))
                    p.fillRect(r, QBrush(stil.farbe("#E15759"), Qt.BDiagPattern))
        # Teile
        p.setRenderHint(QPainter.Antialiasing, True)
        for i, t in enumerate(d["teile"]):
            poly = QPolygonF([self.pkt(x, s) for x, s in t["umriss"]])
            farbe = QColor(self.farben.get(t["ref"], stil.farbe("#4E79A7")))
            flaeche = QColor(farbe)
            gew = self.auswahl == i
            gleich = self.markiert_ref is not None and t["ref"] == self.markiert_ref
            flaeche.setAlpha(205 if gew else 150 if gleich else 120)
            p.setBrush(flaeche)
            p.setPen(QPen(stil.farbe(stil.ORANGE), 2.6) if gew else QPen(stil.farbe("#202020"), 1.1))
            p.drawPolygon(poly)
            self._flaechen.append((poly, i))
            # Beschriftung in der Mitte
            r = poly.boundingRect()
            if (r.height() if self.senkrecht else r.width()) > 34:
                p.setPen(stil.farbe("#111111"))
                p.drawText(r, Qt.AlignCenter, f"{t['pos'] if t.get('pos') is not None else t.get('artikel') or ''}\n"
                                              f"{_z(t['laenge'], 1)}")
        p.setBrush(Qt.NoBrush)
        # Konturen
        if self.ebenen["konturen"]:
            belegt = []         # Beschriftungen der technischen Ansicht: keine überdeckt eine andere (Zoom zeigt alle)
            for i, t in enumerate(d["teile"]):
                for k in t["konturen"]:
                    farbe = stil.farbe("#2E7D32") if k["gravur"] else stil.farbe("#B42318")
                    p.setPen(QPen(farbe, 1.5 if self.auswahl == i else 1.2))
                    for stueck in sa.kontur_teile(k["punkte"], U):
                        poly = QPolygonF([self.pkt(x, s) for x, s in stueck])
                        r = poly.boundingRect()
                        if r.width() < 3 and r.height() < 3:
                            p.drawEllipse(r.center(), 1.8, 1.8)
                        elif k["gravur"] or not k["geschlossen"]:
                            p.drawPolyline(poly)
                        else:
                            p.drawPolygon(poly)
                    if self.technisch:
                        q = self.pkt(k["x"], k["t"])
                        txt = f"x {_z(k['x'], 1)} · {_z(k['winkel'], 1)}°"
                        r = QRectF(q.x() + 4, q.y() - 14, p.fontMetrics().horizontalAdvance(txt) + 4, 13)
                        if not any(r.intersects(b) for b in belegt):
                            belegt.append(r)
                            p.setPen(stil.farbe("#7A1A12"))
                            p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, txt)
        p.setRenderHint(QPainter.Antialiasing, False)
        # Seitenkanten, Radiusübergänge, Naht
        if self.ebenen["raster"]:
            for t_, art in d["kanten"]:
                if t_ <= 1e-6:
                    continue
                p.setPen(QPen(stil.farbe("#5F6B7A" if art == "kante" else "#9AA4AF"), 0.8,
                              Qt.DashLine if art == "kante" else Qt.DotLine))
                p.drawLine(self.pkt(0, t_), self.pkt(L, t_))
        if d["naht"] is not None:
            p.setPen(QPen(stil.farbe("#D0021B"), 1.6, Qt.DashDotLine))
            p.drawLine(self.pkt(0, d["naht"]), self.pkt(L, d["naht"]))
        # Schnittpositionen
        if self.ebenen["schnitte"]:
            p.setPen(QPen(stil.farbe("#1F5FA8"), 1.0))
            for t in d["teile"]:
                for x in (t["von"], t["bis"]):
                    a, b = self.pkt(x, -U * 0.04), self.pkt(x, U * 1.04)
                    p.drawLine(a, b)
        p.setPen(QPen(stil.farbe("#5F6B7A"), 1))
        p.drawRect(band)
        # Messen
        if self.messpunkte:
            p.setPen(QPen(stil.farbe("#B42318"), 1.6, Qt.DashLine))
            pts = [self.pkt(x, t) for x, t in self.messpunkte]
            for q in pts:
                p.drawEllipse(q, 3, 3)
            if len(pts) == 2:
                p.drawLine(pts[0], pts[1])
                (x0, t0), (x1, t1) = self.messpunkte
                p.drawText(QRectF((pts[0] + pts[1]) / 2 + QPointF(6, -18), QPointF(0, 0)).normalized().adjusted(
                    0, 0, 260, 16), Qt.AlignLeft, f"Δ längs {_z(abs(x1 - x0), 1)} mm · Δ Umfang {_z(abs(t1 - t0), 1)} mm")
        p.restore()
        self._raender(p, d, klein)
        p.end()

    def _raender(self, p, d, klein):
        """Lineal, Seiten/Winkel, Bemaßung, Kopfzeile."""
        U, L = d["umfang"], d["laenge"]
        mm = self._mm()
        a0, a1 = self._lang_px()
        p.setPen(stil.farbe(stil.TEXT_GRAU))
        # Lineal längs
        sch = _schritt(mm)
        x = 0.0
        while x <= L + 1e-6:
            q = self.pkt(x, 0)
            pos = q.y() if self.senkrecht else q.x()
            if a0 - 1 <= pos <= a1 + 1:
                q2 = self.pkt(x, 0) - (QPointF(8, 0) if self.senkrecht else QPointF(0, 8))
                p.drawLine(q, q2)
                txt = f"{_z(x / 1000, 3 if sch < 1000 else 0)} m" if sch >= 100 else _z(x, 0)
                if self.senkrecht:
                    p.drawText(QRectF(q2.x() - 60, q2.y() - 7, 56, 14), Qt.AlignRight | Qt.AlignVCenter, txt)
                else:
                    p.drawText(QRectF(q2.x() - 40, q2.y() - 16, 80, 14), Qt.AlignCenter, txt)
            x += sch
        # Seiten bzw. Winkel quer
        if self.ebenen["raster"]:
            vorn = self.pkt(0, 0)
            if d["form"] in ("Rundrohr", "Rund") or not d["streifen"] or len(d["streifen"]) < 2:
                for w in (0, 90, 180, 270, 360):
                    t_ = U * w / 360
                    q = self.pkt(0, t_)
                    r = QRectF(4, q.y() - 7, self.RAND_L - 10, 14) if not self.senkrecht else \
                        QRectF(q.x() - 20, 4, 40, 14)
                    p.drawText(r, Qt.AlignRight | Qt.AlignVCenter if not self.senkrecht else Qt.AlignCenter, f"{w}°")
            else:
                for name, t0, t1 in d["streifen"]:
                    q0, q1 = self.pkt(0, t0), self.pkt(0, t1)
                    r = QRectF(4, q0.y(), self.RAND_L - 10, q1.y() - q0.y()) if not self.senkrecht else \
                        QRectF(q0.x(), 4, q1.x() - q0.x(), 14)
                    p.drawText(r, Qt.AlignRight | Qt.AlignVCenter if not self.senkrecht else Qt.AlignCenter, name)
            del vorn
        # Bemaßung: Kettenmaß der Schnitte unter dem Band
        if self.ebenen["bemassung"] and not self.senkrecht:
            stellen = sorted({0.0, L} | {round(t["von"], 3) for t in d["teile"]} | {round(t["bis"], 3)
                                                                                 for t in d["teile"]})
            y = self.pkt(0, U).y() + 16
            p.setPen(QPen(stil.farbe("#30363D"), 0.8))
            for x0, x1 in zip(stellen, stellen[1:]):
                q0, q1 = self.pkt(x0, U), self.pkt(x1, U)
                p.drawLine(QPointF(q0.x(), y - 4), QPointF(q0.x(), y + 4))
                p.drawLine(QPointF(q0.x(), y), QPointF(q1.x(), y))
                if q1.x() - q0.x() > 26:
                    p.drawText(QRectF(q0.x(), y - 15, q1.x() - q0.x(), 13), Qt.AlignCenter, _z(x1 - x0, 1))
            q = self.pkt(L, U)
            p.drawLine(QPointF(q.x(), y - 4), QPointF(q.x(), y + 4))
            # Gesamtmaß
            y2 = y + 22
            q0, q1 = self.pkt(0, U), self.pkt(L, U)
            p.drawLine(QPointF(q0.x(), y2), QPointF(q1.x(), y2))
            p.drawText(QRectF(q0.x(), y2 - 15, q1.x() - q0.x(), 13), Qt.AlignCenter,
                       f"Stange {_z(L, 0)} mm · Umfang {_z(U, 1)} mm (Außenhaut"
                       + (f", Eckradius {_z(d['radius'], 1)} mm)" if d["radius"] else ")"))
            if self.technisch:          # Koordinaten der Schnitte ab Materialanfang
                y3 = y2 + 18
                zeilen = [[], []]       # zwei Reihen: eng beieinander liegende Schnitte abwechselnd, sonst weglassen
                for xx in sorted({round(v, 1) for t in d["teile"] for v in (t["von"], t["bis"])}):
                    q = self.pkt(xx, U)
                    txt = _z(xx, 1)
                    w = p.fontMetrics().horizontalAdvance(txt) + 6
                    for n, reihe in enumerate(zeilen):
                        r = QRectF(q.x() - w / 2, y3 - 7 + 14 * n, w, 14)
                        if not any(r.intersects(b) for b in reihe):
                            reihe.append(r)
                            p.drawText(r, Qt.AlignCenter, txt)
                            break
        p.setPen(stil.farbe(stil.TEXT_GRAU))
        kopf = (f"Materialanfang (Ende A) · Umfang {'1:1' if self.eins_zu_eins else 'auf Höhe gestreckt'}"
                + (f" · Ohne Daten: Pos. {', '.join(str(x) for x in d['fehlt'])}" if d["fehlt"] else ""))
        p.drawText(QRectF(self.RAND_L, 2, max(self.width() - self.RAND_L - 10, 50), 14), Qt.AlignLeft | Qt.AlignVCenter,
                   kopf)

    # ------------------------------------------------------------------ Treffer und Maus
    def teil_bei(self, punkt):
        return next((i for poly, i in reversed(self._flaechen) if poly.containsPoint(punkt, Qt.OddEvenFill)), None)

    def bereich_bei(self, punkt):
        return next(((art, von, bis) for r, art, von, bis in self._bereiche if r.contains(punkt)), None)

    def bereich_text(self, art, von, bis):
        name = {"end": "Endbeschnitt", "schnitt": "Schnittfuge", "rest": "Rest" + (" (verwertbar)" if self.rest_ok else
                                                                              " (Verschnitt)"),
                "greif": "Greiferrest (Einspannbereich)", "teil": "Teil"}.get(art, art)
        return f"{name}: {_z(bis - von, 1)} mm (x {_z(von, 1)} bis {_z(bis, 1)} mm)"

    def mousePressEvent(self, e):
        punkt = QPointF(e.position())
        if e.button() == Qt.MiddleButton:
            self._ziehen = (punkt, self.versatz)
            return
        if e.button() != Qt.LeftButton or not self.daten:
            return
        if self.messen:
            x, t = self.mm_bei(punkt)
            x = max(0.0, min(self.daten["laenge"], x))
            self.messpunkte = (self.messpunkte if len(self.messpunkte) == 1 else []) + [(x, t)]
            if len(self.messpunkte) == 2:
                (x0, t0), (x1, t1) = self.messpunkte
                self.gemessen.emit(f"Gemessen: längs {_z(abs(x1 - x0), 1)} mm, am Umfang {_z(abs(t1 - t0), 1)} mm "
                                   f"(x {_z(min(x0, x1), 1)} bis {_z(max(x0, x1), 1)} mm)")
            self.update()
            return
        i = self.teil_bei(punkt)
        if i is not None:
            self.auswahl = i
            self.teil_gewaehlt.emit(i)
            self.update()
            return
        b = self.bereich_bei(punkt)
        if b is not None:
            self.bereich_gewaehlt.emit(self.bereich_text(*b))
        self._ziehen = (punkt, self.versatz)

    def mouseMoveEvent(self, e):
        if self._ziehen is not None and e.buttons() & (Qt.LeftButton | Qt.MiddleButton):
            start, alt = self._ziehen
            d = QPointF(e.position()) - start
            self.versatz = alt + (d.y() if self.senkrecht else d.x())
            self._grenzen()
            self.update()

    def mouseReleaseEvent(self, _):
        self._ziehen = None

    def mouseDoubleClickEvent(self, e):
        if self.teil_bei(QPointF(e.position())) is None:
            self.einpassen()

    def wheelEvent(self, e):
        q = QPointF(e.position())
        self.zoom_um(1.25 if e.angleDelta().y() > 0 else 0.8, q.y() if self.senkrecht else q.x())
        e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_F:
            self.einpassen()
        elif e.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_um(1.25)
        elif e.key() == Qt.Key_Minus:
            self.zoom_um(0.8)
        elif e.key() == Qt.Key_Escape:
            self.messpunkte = []
            self.update()
        else:
            super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        i = self.teil_bei(QPointF(e.pos()))
        if i is None:
            return
        t = self.daten["teile"][i]
        self.auswahl = i
        self.teil_gewaehlt.emit(i)
        m = QMenu(self)
        a_pos = m.addAction("Zur Position")
        a_gleich = m.addAction("Gleiche Teile hervorheben" if self.markiert_ref != t["ref"] else "Hervorhebung aus")
        a_3d = m.addAction("Im 3D zeigen")
        gew = m.exec(e.globalPos())
        if gew is a_pos:
            self.zur_position.emit(t["ref"] or "")
        elif gew is a_gleich:
            self.markiert_ref = None if self.markiert_ref == t["ref"] else t["ref"]
        elif gew is a_3d:
            self.im_3d.emit(i)
        self.update()

    def bild_pfad(self):
        """Umriss aller Teile als QPainterPath (Tests: Lage im Bild)."""
        path = QPainterPath()
        for poly, _ in self._flaechen:
            path.addPolygon(poly)
        return path
