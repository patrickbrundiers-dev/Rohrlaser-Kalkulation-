"""Bausteine des Dashboards (Startseite, Design- und Layout-Update 19.11.2026, Punkt 4).

Huelle: steckt um jede Karte der Startseite. Die Anordnung des Benutzers (werkzeugleiste.startseite) wählt, ob die
Hülle gezeigt wird (gewaehlt); die Karte selbst behält ihre eigene Sichtbarkeit (Rechte, Funktionen, „nur mit
Daten“). Gezeigt wird die Hülle nur, wenn beides zutrifft – so bleibt keine leere Lücke.

SchnellKarte: Karte „Schnellzugriffe“ mit den Knöpfen aus werkzeugleiste.schnellzugriffe (Aktionsbibliothek) und den
zuletzt verwendeten Funktionen.
"""
from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from . import aktionen, stil
from . import werkzeugleiste as wl

SPALTEN = 4


class Huelle(QWidget):
    def __init__(self, inhalt, bei_aenderung=None):
        super().__init__()
        self.inhalt = inhalt
        self.gewaehlt = False
        self.bei_aenderung = bei_aenderung
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(inhalt)
        inhalt.installEventFilter(self)

    def inhalt_sichtbar(self):
        return not self.inhalt.isHidden()

    def eventFilter(self, obj, e):
        if obj is self.inhalt and e.type() in (QEvent.ShowToParent, QEvent.HideToParent):
            self.aktualisieren()
        return False

    def aktualisieren(self):
        an = self.gewaehlt and self.inhalt_sichtbar()
        if an != (not self.isHidden()):
            self.setVisible(an)
            if self.bei_aenderung is not None:
                self.bei_aenderung()


class SchnellKarte(QWidget):
    """Karte Schnellzugriffe: große Knöpfe der gewählten Aktionen, darunter „Zuletzt verwendet“ als Links."""

    def __init__(self, f):
        super().__init__()
        from .angebot_oben import karte
        self.f = f
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        anpassen = QLabel("<a href='#'>Anpassen …</a>")
        anpassen.setToolTip("Schnellzugriffe wählen und sortieren (Meine Werkzeugleiste konfigurieren)")
        anpassen.linkActivated.connect(lambda _: f.werkzeugleiste_konfigurieren(reiter=2))
        self.karte, kl = karte("Schnellzugriffe", anpassen)
        lay.addWidget(self.karte)
        self.raster = QGridLayout()
        self.raster.setSpacing(6)
        kl.addLayout(self.raster)
        self.zuletzt = QLabel()
        self.zuletzt.setTextFormat(Qt.RichText)
        self.zuletzt.setWordWrap(True)
        self.zuletzt.linkActivated.connect(self._zuletzt)
        kl.addWidget(self.zuletzt)
        self.knoepfe = {}
        self._spalten = 0

    def neu_laden(self):
        while self.raster.count():
            w = self.raster.takeAt(0).widget()
            if w is not None:       # sofort weg (deleteLater allein greift erst in der Ereignisschleife)
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.knoepfe = {}
        from .werkzeugleiste_qt import icon
        ids = [a for a in wl.schnellzugriffe(self.f.db) if aktionen.sichtbar(aktionen.AKTION[a])]
        for n, aid in enumerate(ids):
            a = aktionen.AKTION[aid]
            b = QToolButton()
            b.setObjectName(f"schnell_{aid}")
            b.setText(a.titel)
            b.setIcon(icon(a.symbol, 22))
            b.setIconSize(QSize(22, 22))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setToolTip(a.tipp)
            if a.menue is not None:
                from PySide6.QtWidgets import QMenu
                m = QMenu(b)
                m.aboutToShow.connect(lambda m=m, a=a: self._menue(m, a))
                b.setMenu(m)
                b.setPopupMode(QToolButton.InstantPopup)
            else:
                b.clicked.connect(lambda _=False, a=a: aktionen.ausfuehren(self.f, a))
            self.knoepfe[aid] = b
        for b in self.knoepfe.values():
            b.setMinimumWidth(max(150, b.sizeHint().width()))     # Text nie abschneiden
        self._spalten = 0
        self.anordnen()
        self.zustand()

    def anordnen(self):
        """So viele Spalten, wie die Knöpfe ungekürzt nebeneinander passen (höchstens SPALTEN)."""
        knoepfe = list(self.knoepfe.values())
        if not knoepfe:
            return
        breit = max(b.minimumWidth() for b in knoepfe) + self.raster.spacing()
        platz = max(1, self.karte.contentsRect().width() - 24)
        spalten = max(1, min(SPALTEN, len(knoepfe), platz // breit))
        if spalten == self._spalten:
            return
        self._spalten = spalten
        for b in knoepfe:
            self.raster.removeWidget(b)
        for n, b in enumerate(knoepfe):
            self.raster.addWidget(b, n // spalten, n % spalten)
        # Generalüberholung 24.11.2026: Höhe der Karte neu melden. Ändert sich die Spaltenzahl während eines
        # Layoutdurchgangs (z. B. Startseite verdeckt beim Öffnen eines Angebots), blieb die Karte sonst auf der
        # alten Höhe stehen und die Knöpfe wurden auf 14 px zusammengedrückt.
        self.karte.updateGeometry()
        self.updateGeometry()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.anordnen()

    def _menue(self, m, a):
        m.clear()
        for titel, aufruf in a.menue(self.f) or [("(noch nichts)", None)]:
            x = m.addAction(titel)
            if aufruf is None:
                x.setEnabled(False)
            else:
                x.triggered.connect(lambda _=False, aufruf=aufruf: aufruf())

    def zustand(self):
        """Knöpfe frei/ausgegraut (Grund im Tooltip) und die Zeile „Zuletzt verwendet“."""
        for aid, b in self.knoepfe.items():
            a = aktionen.AKTION[aid]
            warum = aktionen.grund(self.f, a)
            b.setEnabled(not warum)
            b.setToolTip(a.tipp + (f"\n{warum}" if warum else ""))
        letzte = [aid for aid in wl.zuletzt(self.f.db) if aktionen.AKTION[aid].menue is None][:6]
        grau = stil.umsetzen("#5F6B7A")
        if letzte:
            links = " · ".join(f"<a href='{aid}'>{aktionen.AKTION[aid].titel}</a>" for aid in letzte)
            self.zuletzt.setText(f"<span style='color:{grau}'>Zuletzt verwendet:</span> {links}")
        else:
            self.zuletzt.setText(f"<span style='color:{grau}'>Zuletzt verwendet: noch nichts</span>")

    def _zuletzt(self, aid):
        a = aktionen.AKTION.get(aid)
        if a is not None:
            aktionen.ausfuehren(self.f, a)

    def showEvent(self, e):
        super().showEvent(e)
        self._spalten = 0               # Breite kann sich verdeckt geändert haben: Spalten neu bestimmen
        self.anordnen()
        self.zustand()
