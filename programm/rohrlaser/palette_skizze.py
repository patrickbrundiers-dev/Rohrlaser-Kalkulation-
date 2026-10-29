"""Skizze der Packliste (paletten.packen) je Ladungsträger: Draufsicht der untersten Lage und Seitenansicht des
Stapels mit Höhe, dazu der Aufbau als Text (Patrick 29.10.2026, Pack-Logik im Frachtrechner, 2a).

Gezeichnet wird maßstäblich je Ladungsträger: Draufsicht Länge × Breite mit den Teilen der ersten Position
(Reihen längs × Teile quer, Überstand über die Stirnseiten), Seitenansicht Länge × Höhe mit allen Positionen der
Palette übereinander (Lagenhöhe aus dem Lagenplan, Zwischenlagen eingerechnet) und der zulässigen Höhe gestrichelt.
Teile ohne Maße erscheinen schraffiert (nur nach Gewicht gepackt).
"""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import stil
from .stammdaten import zahl_als_text

HOLZ = "#C8A675"
ZEICHNUNG = 150          # Höhe der Zeichnungen [px]
TITEL = 22
ABSTAND = 14


def _mm(w):
    return zahl_als_text(round(w or 0), 0)


def schicht_hoehen(pal, stuecke):
    """[(Position-Index k, Stück, Lagen, Höhe mm oder None)] von unten nach oben."""
    out = []
    for s in pal.get("schichten") or ():
        geo = stuecke[s["k"]].get("plan_geo")
        h = None
        if geo and s["lagen"]:
            h = geo["erste"] + (s["lagen"] - 1) * geo["abstand"]
        out.append((s["k"], s["stueck"], s["lagen"], h))
    return out


class PacklisteAnsicht(QWidget):
    """Alle Ladungsträger der Packliste untereinander: Titel, Draufsicht, Seitenansicht, Aufbau."""

    def __init__(self):
        super().__init__()
        self.packliste = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, packliste):
        self.packliste = packliste
        self.updateGeometry()
        self.setMinimumHeight(self._gesamt_hoehe(max(self.width(), 400)))
        self.update()

    def _textzeilen(self, pal):
        return list(pal.get("aufbau") or [])

    def _text_hoehe(self, pal, breite):
        fm = QFontMetrics(self.font())
        return sum(fm.boundingRect(0, 0, breite, 1000, Qt.TextWordWrap, t).height() + 2 for t in self._textzeilen(pal))

    def _gesamt_hoehe(self, breite):
        if not self.packliste or not self.packliste.get("paletten"):
            return 0
        return sum(TITEL + ZEICHNUNG + 6 + self._text_hoehe(p, breite - 8) + ABSTAND
                   for p in self.packliste["paletten"])

    def sizeHint(self):
        return QSize(500, self._gesamt_hoehe(max(self.width(), 400)))

    def resizeEvent(self, e):
        self.setMinimumHeight(self._gesamt_hoehe(max(e.size().width(), 400)))
        super().resizeEvent(e)

    def paintEvent(self, _):
        if not self.packliste or not self.packliste.get("paletten"):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = 0
        for pal in self.packliste["paletten"]:
            y = self.palette_zeichnen(p, pal, y, self.width())
        p.end()

    # ---------------------------------------------------------- eine Palette
    def palette_zeichnen(self, p, pal, y, breite):
        stuecke = self.packliste["stuecke"]
        text = stil.farbe("#1F2937")
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        p.setPen(text)
        hoehe = f", Höhe {_mm(pal['hoehe'])} mm" if pal.get("hoehe") else ""
        p.drawText(QRectF(4, y, breite - 8, TITEL), Qt.AlignVCenter | Qt.AlignLeft,
                   f"Ladungsträger {pal['nr']}: {pal['bezeichnung']} – {zahl_als_text(pal['brutto'], 0)} kg brutto"
                   + hoehe)
        f.setBold(False)
        p.setFont(f)
        y += TITEL
        halb = (breite - 24) / 2
        self.draufsicht(p, pal, stuecke, QRectF(4, y, halb, ZEICHNUNG))
        self.seitenansicht(p, pal, stuecke, QRectF(16 + halb, y, halb, ZEICHNUNG))
        y += ZEICHNUNG + 6
        p.setPen(text)
        fm = QFontMetrics(p.font())
        for t in self._textzeilen(pal):
            r = fm.boundingRect(0, 0, int(breite - 8), 1000, Qt.TextWordWrap, t)
            p.drawText(QRectF(4, y, breite - 8, r.height() + 2), Qt.TextWordWrap, t)
            y += r.height() + 2
        p.setPen(QPen(stil.farbe("#D5DBE3"), 1))
        p.drawLine(4, int(y + ABSTAND / 2), int(breite - 4), int(y + ABSTAND / 2))
        return y + ABSTAND

    @staticmethod
    def _farbe(k):
        return stil.farbe(stil.TEIL_FARBEN[k % len(stil.TEIL_FARBEN)])

    def draufsicht(self, p, pal, stuecke, r):
        """Draufsicht der untersten Lage (erste Position der Palette)."""
        L, B, _ = pal.get("masse") or (0, 0, 0)
        L, B = max(L, B), min(L, B)
        p.setPen(stil.farbe("#5F6B7A"))
        p.drawText(QRectF(r.x(), r.y(), r.width(), 16), Qt.AlignLeft, "Draufsicht (unterste Lage)")
        if not (L and B):
            return
        schichten = pal.get("schichten") or []
        geo = stuecke[schichten[0]["k"]].get("plan_geo") if schichten else None
        ueber = (geo or {}).get("ueber") or 0.0
        gesamt_l = L + ueber
        flaeche = QRectF(r.x(), r.y() + 18, r.width(), r.height() - 34)
        s = min(flaeche.width() / gesamt_l, flaeche.height() / B)
        ox = flaeche.x() + (flaeche.width() - gesamt_l * s) / 2 + ueber / 2 * s
        oy = flaeche.y() + (flaeche.height() - B * s) / 2
        p.setPen(QPen(stil.farbe("#7A5A30"), 1))
        p.setBrush(stil.farbe(HOLZ, 140))
        p.drawRect(QRectF(ox, oy, L * s, B * s))
        if geo:
            x, yq, _ = geo["teil"]
            reihen, quer = geo["reihen"], geo["quer_je"][0]
            n = min(schichten[0]["stueck"], geo["je_lage"][0])
            gx = ox + (L - min(reihen * x, gesamt_l)) / 2 * s if x <= L else ox - ueber / 2 * s
            gy = oy + (B - quer * yq) / 2 * s
            p.setPen(QPen(stil.farbe("#1F2937"), 0.6))
            p.setBrush(self._farbe(schichten[0]["k"]))
            gezeichnet = 0
            for i in range(reihen):
                for j in range(quer):
                    if gezeichnet >= n:
                        break
                    p.drawRect(QRectF(gx + i * x * s, gy + j * yq * s, x * s, yq * s))
                    gezeichnet += 1
        else:
            p.setBrush(QBrush(self._farbe(schichten[0]["k"]) if schichten else stil.farbe("#7F8A99"), Qt.BDiagPattern))
            p.drawRect(QRectF(ox, oy, L * s, B * s))
        p.setPen(stil.farbe("#5F6B7A"))
        unten = f"{_mm(L)} × {_mm(B)} mm" + (f", Überstand {_mm(ueber)} mm" if ueber else "")
        p.drawText(QRectF(r.x(), r.bottom() - 14, r.width(), 14), Qt.AlignHCenter, unten)

    def seitenansicht(self, p, pal, stuecke, r):
        """Seitenansicht: Ladungsträger, darauf die Positionen übereinander, zulässige Höhe gestrichelt."""
        L, B, hp = pal.get("masse") or (0, 0, 0)
        L = max(L, B)
        p.setPen(stil.farbe("#5F6B7A"))
        p.drawText(QRectF(r.x(), r.y(), r.width(), 16), Qt.AlignLeft, "Seitenansicht (Stapel)")
        if not L:
            return
        gitterbox = pal.get("art") == "Gitterbox"
        boden = 0.0 if gitterbox else (hp or 0.0)
        hmax = max(pal.get("hoehe_max") or 0.0, pal.get("hoehe") or 0.0, boden + 1)
        schichten = schicht_hoehen(pal, stuecke)
        ueber = max([(stuecke[k].get("plan_geo") or {}).get("ueber") or 0.0 for k, *_ in schichten] or [0.0])
        flaeche = QRectF(r.x() + 46, r.y() + 28, r.width() - 50, r.height() - 34)
        s = min(flaeche.width() / (L + ueber), flaeche.height() / hmax)
        ox = flaeche.x() + (flaeche.width() - (L + ueber) * s) / 2 + ueber / 2 * s
        grund = flaeche.bottom()
        if boden:
            p.setPen(QPen(stil.farbe("#7A5A30"), 1))
            p.setBrush(stil.farbe(HOLZ, 160))
            p.drawRect(QRectF(ox, grund - boden * s, L * s, boden * s))
        oben = boden
        zl = pal.get("zwischenlage") or 0.0
        for nr, (k, stk, lagen, h) in enumerate(schichten):
            geo = stuecke[k].get("plan_geo")
            if h is None:
                continue
            if nr and zl:
                oben += zl
            laenge = min(geo["teil"][0] * geo["reihen"], L + (geo.get("ueber") or 0.0)) if geo else L
            x0 = ox + (L - laenge) / 2 * s
            p.setPen(QPen(stil.farbe("#1F2937"), 0.6))
            p.setBrush(self._farbe(k))
            p.drawRect(QRectF(x0, grund - (oben + h) * s, laenge * s, h * s))
            if h * s >= 12:
                p.setPen(stil.farbe("#FFFFFF"))
                p.drawText(QRectF(x0, grund - (oben + h) * s, laenge * s, h * s), Qt.AlignCenter,
                           f"Pos. {stuecke[k]['pos'] or '?'}: {lagen} Lage{'n' if lagen != 1 else ''}")
            oben += h
        if gitterbox and hp:
            p.setPen(QPen(stil.farbe("#7A5A30"), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(ox, grund - hp * s, L * s, hp * s))
        if pal.get("hoehe_max"):
            yh = grund - pal["hoehe_max"] * s
            p.setPen(QPen(stil.farbe("#B42318"), 1, Qt.DashLine))
            p.drawLine(int(ox - 4), int(yh), int(ox + L * s + 4), int(yh))
        p.setPen(stil.farbe("#5F6B7A"))
        for wert in sorted({0.0, pal.get("hoehe") or 0.0, pal.get("hoehe_max") or 0.0}):
            yh = grund - wert * s
            p.drawText(QRectF(r.x(), yh - 8, 42, 16), Qt.AlignRight | Qt.AlignVCenter, _mm(wert))

