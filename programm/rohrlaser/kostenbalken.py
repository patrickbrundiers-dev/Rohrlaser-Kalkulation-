"""Kostenbalken (Verbesserung D2): waagerechter, gestapelter Balken mit Legende, z. B. Kosten einer Schweißbaugruppe
nach Schweißen, Arbeitsgängen, Einmalkosten und Fremdleistung. Allgemein gehalten, damit andere Ansichten ihn
wiederverwenden (z. B. Kostenwasserfall): setzen([(Bezeichnung, Betrag, Farbe oder None)]); ohne Farbe kommen die
Farben der Reihe nach aus stil.BALKEN_FARBEN. Beträge ≤ 0 erscheinen nur in der Legende."""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from .stammdaten import zahl_als_text
from .stil import BALKEN_FARBEN, LINIE, TEXT, TEXT_GRAU
from .stil import farbe as thema_farbe

BALKEN_HOEHE = 14
ZEILE = 18


def _euro(w):
    return zahl_als_text(round(w or 0.0, 2), 2) + " €"


def abschnitte(teile):
    """[(Bezeichnung, Betrag, Farbe)] mit Farbe aus BALKEN_FARBEN, wo keine angegeben ist."""
    return [(t, float(w or 0.0), f or BALKEN_FARBEN[i % len(BALKEN_FARBEN)]) for i, (t, w, *rest) in enumerate(teile)
            for f in [rest[0] if rest else None]]


class Kostenbalken(QWidget):
    """Balken über die volle Breite, darunter die Legende (Farbe, Bezeichnung, Betrag, Anteil) in Zeilen."""

    def __init__(self, titel="", parent=None):
        super().__init__(parent)
        self.titel, self.teile = titel, []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, teile, titel=None):
        self.teile = abschnitte(teile)
        if titel is not None:
            self.titel = titel
        summe = self.summe()
        self.setToolTip("\n".join(f"{t}: {_euro(w)}" + (f" ({w / summe * 100:.0f} %)" if summe > 0 else "")
                                  for t, w, _ in self.teile))
        self.updateGeometry()
        self.update()

    def summe(self):
        return sum(w for _, w, _ in self.teile if w > 0)

    def _oben(self):
        return ZEILE if self.titel else 0

    def sizeHint(self):
        return QSize(260, self._oben() + BALKEN_HOEHE + 6 + ZEILE * len(self.teile))

    def minimumSizeHint(self):
        return QSize(120, self.sizeHint().height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        breite, y, summe = self.width(), self._oben(), self.summe()
        if self.titel:
            p.setPen(thema_farbe(TEXT))
            p.drawText(QRectF(0, 0, breite, ZEILE), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(self.font()).elidedText(f"{self.titel}  {_euro(summe)}", Qt.ElideRight, breite))
        p.setPen(Qt.NoPen)
        p.setBrush(thema_farbe(LINIE))
        p.drawRoundedRect(QRectF(0, y, breite, BALKEN_HOEHE), 3, 3)
        x = 0.0
        for _, w, farbe in self.teile:
            if w <= 0 or summe <= 0:
                continue
            b = breite * w / summe
            p.setBrush(QColor(farbe))
            p.drawRect(QRectF(x, y, max(b, 1.0), BALKEN_HOEHE))
            x += b
        y += BALKEN_HOEHE + 6
        for t, w, farbe in self.teile:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(farbe))
            p.drawRect(QRectF(0, y + 4, 10, 10))
            p.setPen(thema_farbe(TEXT if w > 0 else TEXT_GRAU))
            anteil = f"  {w / summe * 100:.0f} %" if summe > 0 and w > 0 else ""
            p.drawText(QRectF(16, y, breite - 16, ZEILE), Qt.AlignLeft | Qt.AlignVCenter, t)
            p.drawText(QRectF(16, y, breite - 16, ZEILE), Qt.AlignRight | Qt.AlignVCenter, _euro(w) + anteil)
            y += ZEILE


# ------------------------------------------------------------------ Kostenwasserfall (Layout-Plan L22)
def wasserfall(kosten):
    """Stufen des Preisaufbaus aus rechnen.kostenarten(...): [(Titel, von, bis, Summe ja/nein)] je Gruppe aus
    rechnen.KOSTEN_GRUPPEN mit Betrag ≠ 0. Eine Summenzeile (Herstellkosten, Selbstkosten, Verkaufspreis) reicht von 0 bis zu
    ihrem Betrag und setzt den laufenden Stand neu, sodass die letzte Zeile genau den Verkaufspreis trifft."""
    from . import rechnen
    betrag = {n: (w or 0.0) for (_, w, _), (_, n, _) in zip(kosten, rechnen.KOSTENARTEN, strict=True)}
    stand, aus = 0.0, []
    for titel, namen, summe in rechnen.KOSTEN_GRUPPEN:
        w = sum(betrag[n] for n in namen)
        if summe:
            aus.append((titel, 0.0, w, True))
            stand = w
        elif abs(w) >= 0.005:
            aus.append((titel, stand, stand + w, False))
            stand += w
    return aus


class Kostenwasserfall(QWidget):
    """Je Gruppe eine Zeile: Bezeichnung links, Balken vom bisherigen Stand um den Betrag weiter, Betrag rechts;
    Summenzeilen als voller Balken in der Akzentfarbe."""
    TEXT_BREITE = 0.36
    BETRAG_BREITE = 86

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stufen = []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, kosten):
        self.stufen = wasserfall(kosten)
        self.setToolTip("\n".join(f"{'= ' if s else '+ '}{t}: {_euro(b if s else b - v)}"
                                  for t, v, b, s in self.stufen))
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        return QSize(300, ZEILE * len(self.stufen) + 4)

    def minimumSizeHint(self):
        return QSize(160, self.sizeHint().height())

    def paintEvent(self, _):
        from .stil import AKZENT
        if not self.stufen:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(self.font())
        links = int(self.width() * self.TEXT_BREITE)
        flaeche = max(20, self.width() - links - self.BETRAG_BREITE - 8)
        hoch = max([max(v, b) for _, v, b, _ in self.stufen] + [0.01])
        x = lambda w: links + flaeche * max(w, 0.0) / hoch
        vorher, farbe_nr = None, 0
        for i, (titel, von, bis, summe) in enumerate(self.stufen):
            y = i * ZEILE
            p.setPen(thema_farbe(TEXT))
            f = p.font()
            f.setBold(summe)
            p.setFont(f)
            p.drawText(QRectF(0, y, links - 6, ZEILE), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(titel, Qt.ElideRight, links - 6))
            p.drawText(QRectF(self.width() - self.BETRAG_BREITE, y, self.BETRAG_BREITE, ZEILE),
                       Qt.AlignRight | Qt.AlignVCenter, _euro(bis if summe else bis - von))
            if summe:
                farbe = AKZENT
            else:
                farbe = BALKEN_FARBEN[1 + farbe_nr % (len(BALKEN_FARBEN) - 1)]
                farbe_nr += 1
            a, b = sorted((x(von), x(bis)))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(farbe))
            p.drawRect(QRectF(a, y + 3, max(b - a, 1.0), ZEILE - 6))
            if vorher is not None:                  # Verbindungslinie vom Ende der vorigen Stufe
                p.setPen(thema_farbe(TEXT_GRAU))
                p.drawLine(int(vorher), y - 3, int(vorher), y + 3)
            vorher = x(bis)
        p.setPen(thema_farbe(LINIE))
        p.drawLine(links, 0, links, ZEILE * len(self.stufen))
