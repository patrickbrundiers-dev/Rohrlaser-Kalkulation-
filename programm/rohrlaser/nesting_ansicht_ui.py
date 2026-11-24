"""Bausteine für die modernen Ansichten des Nesting-Arbeitsplatzes (Plan „Nesting-Ansichten moderner gestalten“,
Patrick 24.11.2026, Pakete M1/M5/M6): Werkzeugknöpfe mit Symbol, Segmentschalter der Ansichten, Stangenliste mit
Belegungsbalken, Infokarten für Stange und Teil. Nur Oberfläche: alle Werte kommen aus dem Nesting-Ergebnis."""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGridLayout, QLabel, QSizePolicy, QStyle, QStyledItemDelegate, QToolButton,
                               QVBoxLayout, QWidget)

from . import design, rechnen, stil

ROLLE_BALKEN = Qt.UserRole + 1          # Stangenliste: dict(laenge, abschnitte [(art, von, bis, Farbe)], titel, rechts)


def symbol(name, px=18):
    from .werkzeugleiste_qt import icon
    return icon(name, px)


def knopf(text, name=None, tipp="", umschalten=False, nur_symbol=False):
    """QToolButton im Stil der Werkzeugleiste: Symbol + Kurzname (oder nur Symbol), Tooltip, optional umschaltbar."""
    b = QToolButton()
    b.setText(text)
    if name:
        b.setIcon(symbol(name))
        b.setIconSize(QSize(18, 18))
    b.setToolButtonStyle(Qt.ToolButtonIconOnly if nur_symbol and name else
                         Qt.ToolButtonTextBesideIcon if name else Qt.ToolButtonTextOnly)
    b.setToolTip(tipp or text)
    b.setCheckable(umschalten)
    b.setAutoRaise(True)
    b.setObjectName("nestwz")
    return b


def leisten_stil():
    """Stylesheet: Werkzeugknöpfe flach, gewählt mit Akzentfläche; Segmentschalter als zusammenhängende Gruppe."""
    akzent, flaeche, linie = stil.umsetzen(design.AKZENT), stil.umsetzen(design.BLAU_FLAECHE), stil.umsetzen(design.LINIE)
    return (f"QToolButton#nestwz {{ padding: 3px 7px; border: 1px solid transparent; border-radius: 4px; }}"
            f"QToolButton#nestwz:hover {{ border-color: {linie}; }}"
            f"QToolButton#nestwz:checked {{ background: {flaeche}; border-color: {akzent}; color: {akzent}; }}"
            f"QFrame#segment {{ border: 1px solid {linie}; border-radius: 6px; }}"
            f"QFrame#segment QToolButton#nestwz {{ border-radius: 5px; margin: 1px; }}")


def segment(knoepfe):
    """Knöpfe in einem gemeinsamen Rahmen (Segmentschalter)."""
    from PySide6.QtWidgets import QHBoxLayout
    f = QFrame()
    f.setObjectName("segment")
    lay = QHBoxLayout(f)
    lay.setContentsMargins(1, 1, 1, 1)
    lay.setSpacing(0)
    for b in knoepfe:
        lay.addWidget(b)
    return f


# ------------------------------------------------------------------ M6 Stangenliste
class StangenDelegate(QStyledItemDelegate):
    """Zeile der Stangenliste: Titel links, Ausnutzung rechts, darunter die Belegung als Balken (Teile in Farbe,
    Schnittfugen dunkel, Rest grün bzw. rot, Endbeschnitt/Greiferrest grau/rot)."""
    HOEHE = 40

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.HOEHE)

    def paint(self, p, option, index):
        d = index.data(ROLLE_BALKEN)
        if not d:
            return super().paint(p, option, index)
        p.save()
        r = option.rect
        if option.state & QStyle.State_Selected:
            p.fillRect(r, stil.farbe(design.BLAU_FLAECHE))
            p.fillRect(QRectF(r.left(), r.top(), 3, r.height()), stil.farbe(design.AKZENT))
        elif option.state & QStyle.State_MouseOver:
            p.fillRect(r, stil.farbe("#F2F5F8"))
        p.setPen(stil.farbe(stil.TEXT))
        f = p.font()
        f.setBold(bool(option.state & QStyle.State_Selected))
        p.setFont(f)
        oben = QRectF(r.left() + 8, r.top() + 3, r.width() - 16, 17)
        p.drawText(oben, Qt.AlignLeft | Qt.AlignVCenter, d["titel"])
        p.setPen(stil.farbe(stil.TEXT_GRAU))
        p.drawText(oben, Qt.AlignRight | Qt.AlignVCenter, d["rechts"])
        balken = QRectF(r.left() + 8, r.top() + 23, r.width() - 16, 10)
        L = max(d["laenge"], 1.0)
        for art, von, bis, farbe in d["abschnitte"]:
            a = balken.left() + balken.width() * von / L
            b = balken.left() + balken.width() * bis / L
            p.fillRect(QRectF(a, balken.top(), max(b - a, 0.8), balken.height()), stil.farbe(farbe))
        p.setPen(QPen(stil.farbe("#8A96A3"), 0.8))
        p.drawRect(balken)
        p.restore()


def balken_daten(n, s, farben, rest_ok=None):
    """Daten der Zeile für StangenDelegate aus einer Stange des Schnittplans (stangen_ansicht.bereiche)."""
    from .stangen_ansicht import bereiche
    farben_art = {"end": "#A6A6A6", "schnitt": "#30363D", "greif": "#E06666"}
    abschnitte, teile = [], 0.0
    for art, von, bis, t in bereiche(s):
        if art == "teil":
            teile += bis - von
            f = farben.get(t["ref"], "#4E79A7") if t else "#4E79A7"
            abschnitte.append((art, von, bis, QColor(f).name()))
        elif art == "rest":
            abschnitte.append((art, von, bis, "#A5D6A7" if rest_ok else "#F0B4B4"))
        else:
            abschnitte.append((art, von, bis, farben_art.get(art, "#C7CDD4")))
    laenge = float(s["stange"])
    titel = (f"Reststück {s.get('rest')} – " if s.get("rest") else f"Stange {n + 1} – ") + \
        f"{rechnen.zahl(laenge, 0)} mm"
    return dict(laenge=laenge, abschnitte=abschnitte, titel=titel,
                rechts=f"{len(s['teile'])} Teile · {rechnen.zahl(100 * teile / laenge, 1) if laenge else '0'} %")


# ------------------------------------------------------------------ M5 Infokarten
class InfoKarte(QFrame):
    """Karte mit Titel, Zeilen (Bezeichnung, Wert) und optional einem Anteilsbalken (z. B. Ausnutzung)."""

    def __init__(self, titel):
        super().__init__()
        self.setObjectName("karte")
        self.setFrameShape(QFrame.StyledPanel)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(10, 8, 10, 8)
        self.lay.setSpacing(4)
        self.titel = QLabel(titel)
        self.titel.setObjectName("kartentitel")        # Designsystem: fett, Akzentfarbe
        self.lay.addWidget(self.titel)
        self.balken = AnteilBalken()
        self.lay.addWidget(self.balken)
        self.raster = QGridLayout()
        self.raster.setHorizontalSpacing(10)
        self.raster.setVerticalSpacing(3)
        self.lay.addLayout(self.raster)
        self.zusatz = QWidget()
        self.zusatz.setVisible(False)
        self.lay.addWidget(self.zusatz)
        self._zeilen = []
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

    def setzen(self, titel, zeilen, anteil=None, anteil_text=""):
        self.titel.setText(titel)
        self.balken.setzen(anteil, anteil_text)
        for w in self._zeilen:
            self.raster.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._zeilen = []
        for r, (name, wert) in enumerate(zeilen):
            a, b = QLabel(name), QLabel(str(wert))
            a.setStyleSheet(f"color: {stil.TEXT_GRAU};")
            b.setWordWrap(True)
            b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            b.setTextInteractionFlags(Qt.TextSelectableByMouse)
            a.setMinimumHeight(a.fontMetrics().height() + 2)
            b.setMinimumHeight(b.fontMetrics().height() + 2)
            self.raster.addWidget(a, r, 0, Qt.AlignTop)
            self.raster.addWidget(b, r, 1)
            self._zeilen += [a, b]
        self.raster.setColumnStretch(1, 1)

    def text(self):
        return " ".join(w.text() for w in [self.titel] + self._zeilen)


class AnteilBalken(QWidget):
    def __init__(self):
        super().__init__()
        self.anteil, self.text = None, ""
        self.setFixedHeight(16)
        self.setVisible(False)

    def setzen(self, anteil, text=""):
        self.anteil, self.text = anteil, text
        self.setVisible(anteil is not None)
        self.update()

    def paintEvent(self, _):
        if self.anteil is None:
            return
        p = QPainter(self)
        r = QRectF(0, 3, self.width() - 1, 10)
        p.fillRect(r, stil.farbe("#E3E8EE"))
        a = max(0.0, min(1.0, self.anteil))
        p.fillRect(QRectF(r.left(), r.top(), r.width() * a, r.height()),
                   stil.farbe(design.GRUEN if a >= 0.85 else "#B7791F" if a >= 0.6 else design.ROT))
        p.end()
