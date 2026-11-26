"""Kennzahlen und Preisbalken über der Kalkulation (UI/UX Next Level Phase 3, Freigabe Patrick 26.11.2026).

Sechs Kennzahl-Kacheln (Material, Laser und Rüsten, Herstellkosten, Selbstkosten, Gewinn, Verkaufspreis) und ein
Balken „Woraus sich der Preis zusammensetzt“ mit Legende. Die Beträge kommen unverändert aus rechnen.kostenarten
(dieselben Zahlen wie der Preisaufbau), gruppiert nach rechnen.KOSTEN_GRUPPEN; hier wird nichts neu gerechnet.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import bausteine, design, rechnen

KACHELN = (("material", "Material", ("Material",)),
           ("maschine", "Laser und Rüsten", ("Laser schneiden", "Rüsten")),
           ("herstell", "Herstellkosten", ("Herstellkosten",)),
           ("selbst", "Selbstkosten", ("Selbstkosten",)),
           ("gewinn", "Gewinn", ("Gewinn",)),
           ("verkauf", "Verkaufspreis netto", ("Verkaufspreis",)))
GEWINN_GRUPPEN = ("Gewinn", "Skonto", "Kundenkonditionen und Rundung", "Angebotsregeln")


def _z(wert, stellen=2):
    return f"{wert:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def gruppen(kosten):
    """[(Gruppe, Betrag, Summenzeile)] aus rechnen.kostenarten in der Reihenfolge von rechnen.KOSTEN_GRUPPEN."""
    betrag = {n: (w or 0) for (_, w, _), (_, n, _) in zip(kosten, rechnen.KOSTENARTEN)}
    return [(titel, round(sum(betrag.get(n, 0) for n in namen), 2), summe)
            for titel, namen, summe in rechnen.KOSTEN_GRUPPEN]


def balken_teile(kosten):
    """[(Gruppe, Betrag)] aller Gruppen ohne Summenzeilen mit Betrag > 0 (Abzüge wie Rabatt zeigt der Preisaufbau)."""
    return [(t, b) for t, b, summe in gruppen(kosten) if not summe and b > 0.005]


class Preisbalken(QWidget):
    """Gestapelter Balken, Breite je Gruppe nach Betrag."""

    def __init__(self):
        super().__init__()
        self.teile = []
        self.setMinimumHeight(14)
        self.setMaximumHeight(14)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    @staticmethod
    def farbe(i, titel):
        from . import stil
        if titel in GEWINN_GRUPPEN:
            return stil.farbe(design.PREIS_BALKEN_GEWINN[0 if titel == "Gewinn" else 1])
        return stil.farbe(design.PREIS_BALKEN[min(i, len(design.PREIS_BALKEN) - 1)])

    def setzen(self, teile):
        self.teile = list(teile)
        self.update()

    def paintEvent(self, e):
        gesamt = sum(b for _, b in self.teile)
        if gesamt <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x, breite = 0.0, float(self.width())
        for i, (t, b) in enumerate(self.teile):
            w = breite * b / gesamt
            p.fillRect(QRectF(x, 0, w + 0.5, self.height()), self.farbe(i, t))
            x += w
        p.end()


class KalkKopf(QWidget):
    """Kacheln und Preisbalken; setzen(kosten, bewertung) nach jeder Rechnung."""

    def __init__(self):
        super().__init__()
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.setSpacing(design.ABSTAND)
        raster = QGridLayout()
        raster.setSpacing(design.ABSTAND)
        self.kacheln = {}
        for i, (name, titel, _) in enumerate(KACHELN):
            k = bausteine.kennzahl(titel, "–", "", hervor=name == "verkauf")
            self.kacheln[name] = k
            raster.addWidget(k, 0, i)
            raster.setColumnStretch(i, 1)
        aussen.addLayout(raster)
        self.karte = bausteine.karte("Woraus sich der Preis zusammensetzt")
        self.balken = Preisbalken()
        self.legende = QLabel()
        self.legende.setObjectName("nebentext")
        self.legende.setWordWrap(True)
        self.legende.setTextFormat(Qt.RichText)
        self.karte.inhalt.addWidget(self.balken)
        self.karte.inhalt.addWidget(self.legende)
        aussen.addWidget(self.karte)

    def setzen(self, kosten, bewertung=None, unter=None):
        """kosten: rechnen.kostenarten(...); bewertung: preisleiter.bewertung; unter: {Kachel: Text} (optional)."""
        g = {t: b for t, b, _ in gruppen(kosten)}
        unter = dict(unter or {})
        if bewertung and bewertung.get("marge") is not None:
            unter.setdefault("verkauf", f"Marge {_z(100 * bewertung['marge'], 1)} %"
                             + (f" · {bewertung['stufe']}" if bewertung.get("stufe") else ""))
        vk = g.get("Verkaufspreis") or 0
        for name, _, teile in KACHELN:
            wert = sum(g.get(t, 0) for t in teile)
            anteil = f"{_z(100 * wert / vk, 1)} % vom Verkaufspreis" if vk and name not in ("verkauf",) else ""
            self.kacheln[name].setzen(f"{_z(wert)} €", unter.get(name, anteil))
        teile = balken_teile(kosten)
        self.balken.setzen(teile)
        from . import stil
        punkte = []
        for i, (t, b) in enumerate(teile):
            farbe = self.balken.farbe(i, t).name()
            punkte.append(f"<span style='color:{farbe}'>■</span>&nbsp;{t}&nbsp;{_z(b)}&nbsp;€")
        self.legende.setText("&nbsp;&nbsp; ".join(punkte) if punkte else
                             f"<span style='color:{stil.umsetzen('#5F6B7A')}'>Noch keine Kosten</span>")
        return self
