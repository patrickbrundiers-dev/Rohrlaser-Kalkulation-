"""Dialog 'Schweißnaht …': Nahtvorgabe einer oder mehrerer Positionen am Rohrquerschnitt wählen (naht.py).

Das Querschnittsbild zeigt den Rohrquerschnitt von Ende A in Richtung Ende B gesehen in der gewählten Lage. Ein Klick
setzt den Winkel (Richtung vom Mittelpunkt zum Klickpunkt), alternativ das Zahlenfeld. Gespeichert wird der Winkel im
Bezug 'Breitseite oben'.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
                               QVBoxLayout, QWidget)

from . import hilfe, naht

GRAU = "#595959"
NAHT_FARBE = "#C0392B"


class Querschnitt(QWidget):
    """Querschnitt mit Naht. form: Rundrohr/Quadratrohr/Rechteckrohr oder None; winkel in der Ansicht."""
    gewaehlt = Signal(float)

    def __init__(self):
        super().__init__()
        self.form, self.breite, self.hoehe, self.lage, self.winkel, self.aktiv = None, 1.0, 1.0, naht.BREIT_OBEN, None, True
        self.setMinimumSize(260, 260)

    def setzen(self, profil, lage, winkel, aktiv=True):
        self.form = naht.form_von(profil)
        if self.form in ("Rechteckrohr", "Quadratrohr"):
            self.breite, self.hoehe = naht.seitenmasse(profil)
            if lage == naht.SCHMAL_OBEN:
                self.breite, self.hoehe = self.hoehe, self.breite
        else:
            self.breite = self.hoehe = 1.0
        self.lage, self.winkel, self.aktiv = lage, winkel, aktiv
        self.update()

    def _rahmen(self):
        rand = 46
        seite = min(self.width(), self.height()) - 2 * rand
        f = seite / max(self.breite, self.hoehe)
        w, h = self.breite * f, self.hoehe * f
        return QRectF(self.width() / 2 - w / 2, self.height() / 2 - h / 2, w, h)

    def _punkt(self, r, winkel):
        """Punkt auf dem Umriss in Richtung winkel (Ansicht: 0° oben, im Uhrzeigersinn)."""
        t = math.radians(winkel)
        dx, dy = math.sin(t), -math.cos(t)
        c = r.center()
        if self.form == "Rundrohr" or self.form is None:
            return QPointF(c.x() + dx * r.width() / 2, c.y() + dy * r.height() / 2)
        s = min(r.width() / 2 / abs(dx) if abs(dx) > 1e-9 else 1e9, r.height() / 2 / abs(dy) if abs(dy) > 1e-9 else 1e9)
        return QPointF(c.x() + dx * s, c.y() + dy * s)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self._rahmen()
        p.setPen(QPen(QColor("#1F2937"), 3))
        p.setBrush(QColor("#E8EEF5"))
        if self.form == "Rundrohr":
            p.drawEllipse(r)
        elif self.form:
            p.drawRect(r)
        else:
            p.setPen(QColor(GRAU))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, "Kein Rohrprofil:\nSeite nicht darstellbar")
            return
        p.setPen(QColor(GRAU))
        klein = QFont(self.font())
        klein.setPointSizeF(max(7.0, klein.pointSizeF() - 1))
        p.setFont(klein)
        c = r.center()
        for text, x, y, ausr in (("0° oben", c.x() - 60, r.top() - 40, Qt.AlignHCenter | Qt.AlignBottom),
                                 ("180° unten", c.x() - 60, r.bottom() + 4, Qt.AlignHCenter | Qt.AlignTop)):
            p.drawText(QRectF(x, y, 120, 36), ausr, text)
        p.drawText(QRectF(r.right() + 4, c.y() - 18, 44, 36), Qt.AlignLeft | Qt.AlignVCenter, "90°\nrechts")
        p.drawText(QRectF(r.left() - 48, c.y() - 18, 44, 36), Qt.AlignRight | Qt.AlignVCenter, "270°\nlinks")
        if self.form == "Rechteckrohr":          # Breit- und Schmalseite beschriften (innen)
            oben_breit = self.breite >= self.hoehe
            innen = r.adjusted(8, 8, -8, -8)
            p.drawText(innen, Qt.AlignHCenter | Qt.AlignTop, "Breitseite" if oben_breit else "Schmalseite")
            p.drawText(innen, Qt.AlignHCenter | Qt.AlignBottom, "Breitseite" if oben_breit else "Schmalseite")
            p.save()
            p.translate(innen.left() + 6, c.y())
            p.rotate(-90)
            p.drawText(QRectF(-60, -6, 120, 16), Qt.AlignCenter, "Schmalseite" if oben_breit else "Breitseite")
            p.restore()
        p.drawText(QRectF(0, self.height() - 18, self.width(), 18), Qt.AlignCenter,
                   "Blick von Ende A in Richtung Ende B")
        if self.winkel is not None:
            q = self._punkt(r, self.winkel)
            p.setPen(QPen(QColor(NAHT_FARBE), 2, Qt.DashLine))
            p.drawLine(c, q)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(NAHT_FARBE))
            p.drawEllipse(q, 7, 7)
        if not self.aktiv:
            p.setPen(QColor(GRAU))
            p.drawText(r, Qt.AlignCenter, "keine feste Position")

    def mousePressEvent(self, e):
        if not self.aktiv or not self.form:
            return
        c = self._rahmen().center()
        dx, dy = e.position().x() - c.x(), e.position().y() - c.y()
        if math.hypot(dx, dy) < 4:
            return
        w = naht.normieren(round(math.degrees(math.atan2(dx, -dy))))
        if self.form != "Rundrohr":          # Rechteck/Quadrat: auf 5° runden, die Seitenmitte rastet ein
            w = naht.normieren(round(w / 5) * 5)
        self.gewaehlt.emit(w)


class NahtDialog(QDialog):
    """Schweißnaht einer oder mehrerer Positionen. Nach OK: self.werte() = Felder der Position."""

    def __init__(self, parent, p, profil, anzahl=1):
        super().__init__(parent)
        self.profil = profil
        titel = f"Pos. {p.get('pos') or ''} {p.get('artikel') or ''}".strip() if anzahl == 1 else f"{anzahl} Positionen"
        self.setWindowTitle(f"Schweißnaht – {titel}")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.vorgabe = QComboBox()
        self.vorgabe.addItems(naht.VORGABEN)
        self.vorgabe.setCurrentText(naht.vorgabe(p))
        form.addRow("Nahtvorgabe", self.vorgabe)
        self.lage = QComboBox()
        self.lage.addItems(naht.LAGEN)
        self.lage.setCurrentText(p.get("querschnitt_lage") or naht.BREIT_OBEN)
        self.lage_zeile = QLabel("Querschnittslage")
        form.addRow(self.lage_zeile, self.lage)
        self.winkel = QDoubleSpinBox()
        self.winkel.setRange(-1, 360)       # -1/360 erlauben das Weiterdrehen über 0° hinweg (wird normiert)
        self.winkel.setDecimals(1)
        self.winkel.setSuffix(" °")
        self.winkel.setWrapping(True)
        w0 = p.get("naht_winkel")
        self.winkel.setValue(naht.in_ansicht(w0, self.lage.currentText()) if w0 is not None else 0.0)
        form.addRow("Nahtwinkel", self.winkel)
        self.quelle = QComboBox()
        self.quelle.addItems(naht.QUELLEN)
        self.quelle.setCurrentText(p.get("naht_quelle") or "Kunde")
        form.addRow("Quelle", self.quelle)
        lay.addLayout(form)
        self.bild = Querschnitt()
        lay.addWidget(self.bild, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        hinweis = hilfe.Hinweis("0° oben, 90° rechts, 180° unten, 270° links, von Ende A in Richtung Ende B gesehen. "
                                "Klick in das Bild setzt den Winkel. Gedreht wird nur um die eigene Achse, nie "
                                "gewendet.",
                                schluessel="naht")
        lay.addWidget(hinweis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        ist_re = naht.form_von(profil) == "Rechteckrohr"
        self.lage.setVisible(ist_re)
        self.lage_zeile.setVisible(ist_re)
        self._bezug = naht.aus_ansicht(self.winkel.value(), self.lage.currentText())
        self.bild.gewaehlt.connect(self.winkel.setValue)
        self.winkel.valueChanged.connect(lambda _: self._winkel_geaendert())
        self.lage.currentTextChanged.connect(lambda _: self._lage_geaendert())
        self.vorgabe.currentTextChanged.connect(lambda _: self._anzeigen())
        self._anzeigen()

    def _winkel_geaendert(self):
        w = naht.normieren(self.winkel.value())
        if abs(w - self.winkel.value()) > 1e-9:
            self.winkel.setValue(w)
            return
        self._bezug = naht.aus_ansicht(w, self.lage.currentText())
        self._anzeigen()

    def _lage_geaendert(self):
        """Lage umschalten: die Naht bleibt am Rohr, der Winkel der Ansicht wird umgerechnet."""
        self.winkel.blockSignals(True)
        self.winkel.setValue(naht.in_ansicht(self._bezug, self.lage.currentText()))
        self.winkel.blockSignals(False)
        self._anzeigen()

    def _anzeigen(self):
        fest = self.vorgabe.currentText() == naht.FEST
        for w in (self.winkel, self.quelle):
            w.setEnabled(fest)
        self.bild.setzen(self.profil, self.lage.currentText(), self.winkel.value() if fest else None, fest)
        v = self.vorgabe.currentText()
        if fest:
            s = naht.seite(self.profil, self._bezug, self.lage.currentText())
            text = f"Naht: {s['text']}. " + ("" if s["eindeutig"] else "Bitte auf eine Seite legen. ")
            text += "Drehung um die Längsachse gesperrt (Kundenvorgabe)."
            pr = naht.pruefen(self.werte(), self.profil)
            if pr:
                text += "\n" + pr
        elif v == naht.UNBEKANNT:
            text = "Nahtlage unbekannt: das Teil wird bei der Optimierung nicht gedreht."
        else:
            erlaubt = naht.DREHUNGEN.get(naht.form_von(self.profil), (0,))
            text = ("Keine Vorgabe: die Optimierung darf das Teil um die eigene Achse drehen ("
                    + ", ".join(f"{d}°" for d in erlaubt) + ").")
        self.info.setText(text)

    def werte(self):
        """Felder der Position. 'keine Vorgabe' leert alle Nahtfelder (leer = keine Vorgabe)."""
        v = self.vorgabe.currentText()
        if v == naht.KEINE:
            return dict(naht_vorgabe=None, naht_winkel=None, naht_quelle=None, querschnitt_lage=None)
        if v == naht.UNBEKANNT:
            return dict(naht_vorgabe=v, naht_winkel=None, naht_quelle=None, querschnitt_lage=None)
        lage = self.lage.currentText() if naht.form_von(self.profil) == "Rechteckrohr" else None
        return dict(naht_vorgabe=v, naht_winkel=self._bezug, naht_quelle=self.quelle.currentText(),
                    querschnitt_lage=None if lage == naht.BREIT_OBEN else lage)
