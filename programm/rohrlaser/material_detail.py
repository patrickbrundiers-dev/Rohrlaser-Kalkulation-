"""Detailbereich rechts im Fenster „Material je Abmessung“ (UI/UX Next Level Phase 4, Variante A „Klar“).

Zeigt zur markierten Abmessung, was man sonst in Tooltips und Zusatzfenstern sucht: Meterpreis und woher er kommt,
Gewicht je Meter, Bedarf der Teile, Einkauf und Verschnitt laut Schnittplan, Ausnutzung als Balken und Chip, die
Lieferlängen der Stangen und Knöpfe zu Schnittplan, Preis und Lieferantenvergleich. Alle Zahlen kommen unverändert
aus rechnen.material_abmessungen (dieselben wie in der Tabelle), hier wird nichts gerechnet außer Differenzen für
die Anzeige (Verschnitt = Einkauf − Teile).
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from . import bausteine, design, stil

AUSNUTZUNG_GUT, AUSNUTZUNG_KNAPP = 0.85, 0.70     # Chip grün ab 85 %, gelb ab 70 %, darunter rot (nur Anzeige)


def _z(w, stellen=2):
    return f"{w:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def ausnutzung_stufe(a):
    """Stufe des Chips für die Ausnutzung (None = kein Schnittplan)."""
    if a is None:
        return "neutral"
    return "ok" if a >= AUSNUTZUNG_GUT else "warnung" if a >= AUSNUTZUNG_KNAPP else "fehler"


def meterpreis_text(g):
    """(Wert, Herkunft) des Meterpreises wie in der Tabelle: eigener Wert vor berechnetem; Kundenmaterial ohne."""
    if g.get("kunde"):
        return "–", "Kundenmaterial"
    if g.get("manuell") is not None:
        return f"{_z(g['manuell'])} €/m", "eigener Wert"
    if g.get("berechnet") is not None:
        return f"{_z(g['berechnet'])} €/m", "berechnet"
    return "fehlt", g.get("fehlt") or "kein Preis hinterlegt"


class NutzBalken(QWidget):
    """Balken Teile (Akzent) und Verschnitt (hell) im Verhältnis zum Einkauf."""

    def __init__(self):
        super().__init__()
        self.anteil = None
        self.setMinimumHeight(14)
        self.setMaximumHeight(14)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, anteil):
        self.anteil = anteil
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(stil.farbe(design.NEUTRAL_FLAECHE))
        p.drawRoundedRect(r, 4, 4)
        if self.anteil:
            teil = QRectF(r.left(), r.top(), r.width() * max(0.0, min(1.0, self.anteil)), r.height())
            p.setBrush(stil.farbe(design.AKZENT))
            p.drawRoundedRect(teil, 4, 4)
        p.end()


class AbmessungDetail(QFrame):
    """Rechter Bereich des Materialfensters. aktionen = {Text: Funktion(Zeile)} (nur mit offenem Angebot)."""

    def __init__(self, aktionen=None):
        super().__init__()
        self.setObjectName("detailbereich")
        self.setMinimumWidth(280)
        self.setMaximumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(design.ABSTAND_GROSS, design.ABSTAND_GROSS, design.ABSTAND_GROSS, design.ABSTAND_GROSS)
        lay.setSpacing(design.ABSTAND)
        self.titel = QLabel("–")
        self.titel.setObjectName("abschnitt")
        self.titel.setWordWrap(True)
        self.unter = QLabel()
        self.unter.setObjectName("nebentext")
        self.unter.setWordWrap(True)
        lay.addWidget(self.titel)
        lay.addWidget(self.unter)
        self.chip = bausteine.chip("Ausnutzung –", "neutral")
        self.werte = bausteine.wertzeilen([("Meterpreis", "–"), ("Preis", "–"), ("Gewicht je Meter", "–"),
                                           ("Teile", "–"), ("Einkauf", "–"), ("Material", "–"), ("Verschnitt", "–"),
                                           ("Stangen", "–"), ("Lieferlängen", "–")])
        lay.addWidget(self.werte)
        zeile = QHBoxLayout()
        nutz = QLabel("Ausnutzung")
        nutz.setObjectName("nebentext")
        zeile.addWidget(nutz)
        zeile.addStretch(1)
        zeile.addWidget(self.chip)
        lay.addLayout(zeile)
        self.balken = NutzBalken()
        lay.addWidget(self.balken)
        self.hinweis = QLabel()
        self.hinweis.setObjectName("nebentext")
        self.hinweis.setWordWrap(True)
        lay.addWidget(self.hinweis)
        lay.addStretch(1)
        self.knoepfe = {}
        self.zeile = None
        for text, fn in (aktionen or {}).items():
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn(self.zeile) if self.zeile is not None else None)
            lay.addWidget(b)
            self.knoepfe[text] = b

    def setzen(self, g, zeile=None, laengen_text=""):
        """Werte der Abmessung g (Eintrag aus rechnen.material_abmessungen) zeigen; g=None leert den Bereich."""
        self.zeile = zeile
        for b in self.knoepfe.values():
            b.setEnabled(g is not None)
        if g is None:
            self.titel.setText("Keine Abmessung markiert")
            self.unter.setText("")
            return self
        self.titel.setText(f"{g['profil']} · {g['werkstoff']}")
        self.unter.setText(" · ".join(x for x in (g.get("oberflaeche") or "roh",
                                                  f"Lieferlänge {_z(g['stange'], 0)} mm" if g.get("stange") else "",
                                                  "Kundenmaterial" if g.get("kunde") else "Eigenmaterial") if x))
        preis, herkunft = meterpreis_text(g)
        w = self.werte.werte
        w["Meterpreis"].setText(preis)
        w["Preis"].setText(herkunft)
        w["Preis"].setToolTip(herkunft)
        w["Gewicht je Meter"].setText(f"{_z(g['kg_m'], 2)} kg/m" if g.get("kg_m") else "–")
        w["Teile"].setText(f"{_z(g['teile_m'], 1)} m")
        geplant = bool(g.get("stangen"))
        w["Einkauf"].setText(f"{_z(g['meter'], 1)} m · {_z(g['kg'], 1)} kg" if geplant else "noch nicht optimiert")
        w["Material"].setText(f"{_z(g['kosten'])} €" if geplant else "–")
        verschnitt = g["meter"] - g.get("nutz_m", 0.0) if geplant else None
        w["Verschnitt"].setText(f"{_z(verschnitt, 1)} m" if verschnitt is not None else "–")
        w["Stangen"].setText(_z(g["stangen"], 0) if geplant else "–")
        w["Lieferlängen"].setText(laengen_text or "–")
        a = g.get("ausnutzung")
        bausteine.chip_setzen(self.chip, f"{_z(100 * a, 1)} %" if a else "–", ausnutzung_stufe(a))
        self.balken.setzen(a)
        self.hinweis.setText("" if geplant else "Stangen, Einkauf und Verschnitt folgen nach dem Optimieren.")
        return self
