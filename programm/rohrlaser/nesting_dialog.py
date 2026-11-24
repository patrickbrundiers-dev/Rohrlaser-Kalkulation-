"""Nesting-Arbeitsplatz 2.0 (Patrick 23.11.2026 Verschachtelung, 24.11.2026 Master-Auftrag „Nesting-Arbeitsplatz 2.0“:
neue Arbeitsplatzstruktur, Stangenbild wie in der Optimierung, Teile frei verschieben, von Hand verschachteln mit
Zurücksetzen, 2D und 3D aus denselben Daten, Optimierungsvergleich, Protokoll und Export).

Aufbau (Bereiche über Teiler frei in der Größe, links/rechts/unten über die Knöpfe oben ein- und ausblendbar):
- Kopf: Abmessung, Ansicht (Bearbeiten 2D | Stangenbild wie in der Optimierung | 3D), Zoom, Bereiche, Empfehlung,
  lokale Hinweise, Hinweis „veraltet“, wenn der gespeicherte Schnittplan nicht mehr zu den Eingaben passt.
- Links: Bauteile je Position (Stück, eingeplant), Material (Profil, Werkstoff, Lieferlängen mit Preis,
  Fertigungswerte), Reststücke (nur mit Lager und Reststücken), nicht eingeplante Teile (von Hand verschachteln).
- Mitte: NestingBild – maßstäblich je Stange die gemeinsame Zeichnung des Stangenbilds (stangen_ansicht.
  stange_zeichnen: Gehrungen schräg, ineinander grün, gemeinsamer Schnitt, Schnittfugen, Naht, Rest/Verschnitt,
  Greiferrest, Maßkette, Lineal). Teile mit der Maus ziehen: entlang der Stange, auf eine andere Stange oder unter die
  letzte Stange (neue Stange); jede Lage wird geprüft (nesting_vergleich.einfuegen). Klick wählt, Klick auf eine
  andere Stange setzt das Teil dorthin (wie bisher, die Optimierung ordnet die Stange dann selbst an). Strg + Mausrad
  zoomt, mittlere Maustaste verschiebt. Daneben das Stangenbild der Optimierung (StangenSeite) und die 3D-Ansicht
  (nesting_3d) derselben Stangen.
- Rechts: Kennzahlen des gezeigten Plans (Ausnutzung, Verschnitt, Stangen, Länge, Reste, Kosten, Einsparung gegen den
  gespeicherten bzw. bisherigen Plan, Untergrenze, Machbarkeit).
- Unten: Optimierungsvergleich (alle Strategien), Kosten je Position, Berechnungsprotokoll, Export (CSV).
- Knöpfe: Strategie übernehmen, Belegung von Hand übernehmen, Rückgängig, Wiederholen, Stange auflösen, Abmessung
  zurücksetzen, Alles zurücksetzen, Wie bisher rechnen, Übernehmen und neu optimieren.
Der Dialog ändert das Angebot nicht selbst: das Ergebnis steht in self.wahl ({Abmessung: Strategie}) und
self.hand ({Abmessung: Stangen oder None}); die Angebotsseite speichert und optimiert neu.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import nesting as ne, nesting_vergleich as nv, optimierung as opt, rechnen, stil
from .stangen_ansicht import MASS_HOEHE, LINEAL_HOEHE, bereiche, stange_zeichnen, teil_farben

BEARBEITEN, STANGENBILD, DREI_D = "Bearbeiten (2D)", "Stangenbild wie Optimierung", "3D"


def status_text(d):
    """Live-Stand der Rechnung für den Fortschritt (echte Werte aus nesting_vergleich.vergleich, nichts geschätzt)."""
    if not d:
        return ""
    z = rechnen.zahl
    b = d.get("beste") or {}
    return (f"\nAbmessung {d.get('gruppe_nr', 0)} von {d.get('gruppen', 0)} · geprüfte Pläne {d.get('plaene', 0)} · "
            f"Dauer {z(d.get('zeit', 0.0), 1)} s"
            + (f"\nBeste bisher: Strategie {b['strategie']} ({b['gruppe']}), Ausnutzung "
               f"{z(100 * b['ausnutzung'], 1)} %, Verschnitt {z(b['verschnitt_mm'], 0)} mm, {b['stangen']} Stangen"
               if b else ""))


def segmente(g, laenge, folge, min_rest=0.0, min_nutz=ne.REST_MIN_NUTZ):
    """Teile einer Stange für das Bild: [(art, von, bis, Teil oder None)] mit art 'end' | 'teil' | 'schnitt' |
    'rest' (verwertbar) | 'abfall' | 'greif'. Positionen in mm ab Stangenanfang, wie verbrauch rechnet."""
    h = opt.replace(g, stange=laenge, teile=[])
    out = [("end", 0.0, g.endbeschnitt, None)]
    pos, vorher = g.endbeschnitt, None
    for t, r in folge:
        if vorher is not None:
            tr = opt.trennung_teile(h, vorher[0], vorher[1], t, r)
            if tr > 0:
                out.append(("schnitt", pos, pos + tr, None))
            pos += tr
        out.append(("teil", pos, pos + t.laenge, t))
        pos += t.laenge
        vorher = (t, r)
    out.append(("schnitt", pos, pos + g.kerf, None))
    pos += g.kerf
    hinten = opt.hinten(h, folge)
    rest = laenge - pos
    art = "rest" if ne.verwertbar(g, rest, min_rest, min_nutz) else "abfall"
    if rest - hinten > 0:
        out.append((art, pos, laenge - hinten, None))
    out.append(("greif" if art == "abfall" else art, max(pos, laenge - hinten), laenge, None))
    return out


class NestingBild(QWidget):
    """Maßstäbliches, bearbeitbares Bild der Stangen eines Plans (gemeinsame Zeichnung des Stangenbilds).
    Signale: teil_gewaehlt(Stange, Teil), ziel(Stange; -1 = neue Stange) für Klick-Umsetzen, gezogen(von, Teil,
    nach, an) beim Ziehen (nach = -1: neue Stange; an = Platz auf der Zielstange), einsetzen(nach, an) im Modus
    „nicht eingeplantes Teil einsetzen“, stange_gewaehlt(Stange)."""
    ZEILE, LINKS, RECHTS, OBEN = 36 + 26 + MASS_HOEHE + LINEAL_HOEHE, 110, 96, 8
    BALKEN, KOPF = 26, 20
    teil_gewaehlt = Signal(int, int)
    ziel = Signal(int)
    gezogen = Signal(int, int, int, int)
    einsetzen = Signal(int, int)
    stange_gewaehlt = Signal(int)

    def __init__(self):
        super().__init__()
        self.g, self.stangen, self.auswahl = None, [], None
        self.anzeige, self.positionen, self.farben = [], None, {}
        self.min_rest, self.min_nutz = 0.0, ne.REST_MIN_NUTZ
        self.marken, self.gesperrt, self.einsetz_modus = [], False, False
        self.zoom, self.flaechen, self.stange_nr = 1.0, [], None
        self._druck, self._zieh, self._pan = None, None, None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setToolTip("Teil ziehen: auf der Stange verschieben, auf eine andere Stange oder unter die letzte Stange "
                        "(neue Stange) · Klick: wählen, Klick auf eine andere Stange: dorthin · Strg + Mausrad: Zoom · "
                        "mittlere Maustaste: verschieben")

    def setzen(self, g, stangen, min_rest=0.0, min_nutz=ne.REST_MIN_NUTZ, marken=None, gesperrt=False,
               positionen=None, reste=()):
        """marken: Beschriftung je Stange statt der Nummer (Zuschnitt: „12 m Nr. 3“); gesperrt: nur ansehen."""
        self.g, self.stangen, self.auswahl = g, list(stangen), None
        self.marken, self.gesperrt = list(marken or []), gesperrt
        self.min_rest, self.min_nutz = min_rest, min_nutz
        if positionen is not None:
            self.positionen = positionen
        self.anzeige = []
        if g is not None and self.positionen is not None:
            try:
                self.anzeige = nv.anzeige_stangen(g, [s for s in self.stangen if s[1]], self.positionen, reste)
            except (AssertionError, IndexError, KeyError, TypeError, ValueError):
                self.anzeige = []
        self.farben = {r: QColor(f) for r, f in teil_farben(self.anzeige).items()}
        self.setMinimumHeight(self.OBEN * 2 + self.ZEILE * (max(len(self.stangen), 1) + 1))
        self.update()

    def _skala(self):
        lang = max((laenge for laenge, _, _ in self.stangen), default=1)
        return max(self.width() - self.LINKS - self.RECHTS, 50) / lang

    def _farbe(self, t):
        return QColor(stil.TEIL_FARBEN[(t.zeile - rechnen.ZEILE0) % len(stil.TEIL_FARBEN)])

    def zoom_setzen(self, z, basis=None):
        self.zoom = max(1.0, min(40.0, z))
        b = basis or (self.parentWidget().width() if self.parentWidget() is not None else self.width())
        self.setMinimumWidth(int(b * self.zoom) if self.zoom > 1.0 else 0)
        self.update()

    # -------------------------------------------------------------- Zeichnen
    def _anzeige_von(self, i):
        """Stange i im Format des Schnittplans; leere oder unbekannte Stangen über die Abschnitte der Engine."""
        nichtleer = [j for j, s in enumerate(self.stangen) if s[1]]
        if i in nichtleer and len(self.anzeige) == len(nichtleer):
            return self.anzeige[nichtleer.index(i)]
        return None

    def paintEvent(self, _):
        if self.g is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        sk = self._skala()
        text = QColor(stil.farbe("#333333"))
        self.flaechen = []
        klein = QFont(self.font())
        klein.setPointSizeF(max(7.0, klein.pointSizeF() - 1))
        for i, (laenge, folge, rest) in enumerate(self.stangen):
            y = self.OBEN + i * self.ZEILE
            yb = y + self.KOPF
            if self.stange_nr == i:
                p.fillRect(QRectF(0, y, self.width(), self.ZEILE - 2), stil.farbe(stil.BLAU_FLAECHE))
            p.setPen(QPen(text))
            p.setFont(klein)
            p.drawText(QRectF(0, yb, self.LINKS - 6, self.BALKEN), Qt.AlignRight | Qt.AlignVCenter,
                       self.marken[i] if i < len(self.marken) else f"{i + 1}" + (f" {rest}" if rest else ""))
            s = self._anzeige_von(i)
            if s is not None:
                h = opt.replace(self.g, stange=laenge, teile=[])
                frei_rest = laenge - opt.verbrauch(h, folge)
                verw = ne.verwertbar(self.g, frei_rest, self.min_rest, self.min_nutz)
                gew = self.auswahl[1] if self.auswahl and self.auswahl[0] == i else None
                tl = sum(t.laenge for t, _ in folge)
                p.setPen(stil.farbe(stil.TEXT_GRAU))
                p.drawText(QRectF(self.LINKS, y, laenge * sk, self.KOPF - 7), Qt.AlignLeft | Qt.AlignVCenter,
                           f"{len(folge)} Teile · Rest {rechnen.zahl(frei_rest, 0)} mm "
                           f"({'verwertbar' if verw else 'Verschnitt'}) · Ausnutzung {rechnen.zahl(100 * tl / laenge, 1)} %"
                           + (f" · Gehrungen ineinander {rechnen.zahl(sum(t.get('material_gespart') or 0 for t in s['teile']), 1)} mm"
                              if any(t.get("material_gespart") for t in s["teile"]) else ""))
                for r, t, platz in stange_zeichnen(p, s, self.LINKS, yb, self.BALKEN, sk, self.farben, None, verw,
                                                   gewaehlt=gew, schrift=self.font()):
                    self.flaechen.append((r, i, platz))
            else:                               # Zuschnitt-Stück ohne Teile oder ohne Positionen (Tests)
                for art, von, bis, t in segmente(self.g, laenge, folge, self.min_rest, self.min_nutz):
                    r = QRectF(self.LINKS + von * sk, yb, max((bis - von) * sk, 1), self.BALKEN)
                    farbe = {"end": "#BBBBBB", "schnitt": "#333333", "rest": "#A5D6A7", "greif": "#7F7F7F"}.get(art)
                    if art == "teil":
                        p.fillRect(r, self._farbe(t))
                    elif art == "abfall":
                        p.fillRect(r, QBrush(stil.farbe("#E15759"), Qt.BDiagPattern))
                    else:
                        p.fillRect(r, stil.farbe(farbe or "#BBBBBB"))
                p.setPen(QPen(text))
                p.drawRect(QRectF(self.LINKS, yb, laenge * sk, self.BALKEN))
            p.setPen(QPen(text))
            p.drawText(QRectF(self.LINKS + laenge * sk + 4, yb, self.RECHTS - 6, self.BALKEN),
                       Qt.AlignLeft | Qt.AlignVCenter, f"{rechnen.m_text(laenge)} m")
        # Ablagefläche „neue Stange“ unter der letzten Stange
        if not self.gesperrt:
            y = self.OBEN + len(self.stangen) * self.ZEILE + self.KOPF
            r = QRectF(self.LINKS, y, max(self.width() - self.LINKS - self.RECHTS, 50), self.BALKEN)
            p.setPen(QPen(stil.farbe("#9AA4AF"), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            p.setPen(stil.farbe(stil.TEXT_GRAU))
            p.drawText(r, Qt.AlignCenter, "Teil hierher ziehen: neue Stange")
        if self._zieh is not None:              # Teil beim Ziehen: Umriss an der Maus, Einfügestelle als Linie
            von, n, punkt = self._zieh
            t = self.stangen[von][1][n][0]
            w = max(t.laenge * sk, 6)
            r = QRectF(punkt.x() - w / 2, punkt.y() - self.BALKEN / 2, w, self.BALKEN)
            p.setOpacity(0.6)
            p.fillRect(r, stil.farbe("#FF7F0E"))
            p.setOpacity(1.0)
            ziel, an = self.ablage(punkt, (von, n))
            if ziel is not None and ziel >= 0:
                x = self._x_einfuegen(ziel, an, (von, n))
                yz = self.OBEN + ziel * self.ZEILE + self.KOPF
                p.setPen(QPen(stil.farbe("#FF7F0E"), 3))
                p.drawLine(QPointF(x, yz - 3), QPointF(x, yz + self.BALKEN + 3))
        p.end()

    # -------------------------------------------------------------- Treffer
    def treffer(self, punkt):
        """(Stange, Teil oder None) unter dem Punkt; Stange -1 = rechts neben bzw. unter den Stangen (neue Stange)."""
        if self.g is None:
            return None, None
        i = int((punkt.y() - self.OBEN) // self.ZEILE)
        if i == len(self.stangen) and not self.gesperrt:
            return -1, None
        if not (0 <= i < len(self.stangen)):
            return None, None
        sk = self._skala()
        x = (punkt.x() - self.LINKS) / sk
        laenge, folge, _ = self.stangen[i]
        if x > laenge + (self.RECHTS * 0.5) / sk:
            return -1, None
        for r, j, platz in self.flaechen:
            if j == i and r.left() - 1 <= punkt.x() <= r.right() + 1:
                return i, platz
        n = 0
        for art, von, bis, _ in segmente(self.g, laenge, folge):
            if art == "teil":
                if von <= x <= bis:
                    return i, n
                n += 1
        return i, None

    def ablage(self, punkt, quelle=None):
        """(Zielstange, Platz) für eine Ablage an punkt: Platz = Zahl der Teile der Zielstange, deren Mitte links
        davon liegt (das gezogene Teil selbst nicht mitgezählt); Zielstange -1 = neue Stange, None = nichts."""
        i, _ = self.treffer(punkt)
        if i is None or i < 0:
            return i, 0
        sk = self._skala()
        x = (punkt.x() - self.LINKS) / sk
        laenge, folge, _ = self.stangen[i]
        h = opt.replace(self.g, stange=laenge, teile=[])
        pos, vorher, an = self.g.endbeschnitt, None, 0
        for k, (t, r) in enumerate(folge):
            if vorher is not None:
                pos += opt.trennung_teile(h, vorher[0], vorher[1], t, r)
            mitte = pos + t.laenge / 2
            if not (quelle and quelle == (i, k)) and mitte < x:
                an += 1
            pos += t.laenge
            vorher = (t, r)
        return i, an

    def _x_einfuegen(self, i, an, quelle=None):
        laenge, folge, _ = self.stangen[i]
        sk = self._skala()
        teile = [(k, t, r) for k, (t, r) in enumerate(folge) if not (quelle and quelle == (i, k))]
        h = opt.replace(self.g, stange=laenge, teile=[])
        pos, vorher = self.g.endbeschnitt, None
        for j, (_, t, r) in enumerate(teile):
            if vorher is not None:
                pos += opt.trennung_teile(h, vorher[0], vorher[1], t, r)
            if j == an:
                return self.LINKS + pos * sk
            pos += t.laenge
            vorher = (t, r)
        return self.LINKS + pos * sk

    # -------------------------------------------------------------- Maus
    def mousePressEvent(self, e):
        punkt = QPointF(e.position())
        if e.button() == Qt.MiddleButton:
            self._pan = punkt
            return
        if self.gesperrt:
            i, _ = self.treffer(punkt)
            if i is not None and i >= 0:
                self.stange_gewaehlt.emit(i)
            return
        i, n = self.treffer(punkt)
        if i is None:
            return
        if self.einsetz_modus:
            ziel, an = self.ablage(punkt)
            self.einsetzen.emit(-1 if ziel is None else ziel, an)
            return
        if i >= 0:
            self.stange_nr = i
            self.stange_gewaehlt.emit(i)
        if self.auswahl is not None and (n is None or i != self.auswahl[0]):
            self.ziel.emit(i)
            return
        if n is not None:
            self.auswahl = (i, n)
            self._druck = (i, n, punkt)
            self.teil_gewaehlt.emit(i, n)
            self.update()

    def mouseMoveEvent(self, e):
        punkt = QPointF(e.position())
        if self._pan is not None:
            rolle = self.parentWidget().parentWidget() if self.parentWidget() is not None else None
            if isinstance(rolle, QScrollArea):
                d = punkt - self._pan
                rolle.horizontalScrollBar().setValue(rolle.horizontalScrollBar().value() - int(d.x()))
                rolle.verticalScrollBar().setValue(rolle.verticalScrollBar().value() - int(d.y()))
            return
        if self._druck is not None and (e.buttons() & Qt.LeftButton):
            i, n, start = self._druck
            if self._zieh is not None or (punkt - start).manhattanLength() > 6:
                self._zieh = (i, n, punkt)
                self.update()

    def mouseReleaseEvent(self, e):
        self._pan = None
        if self._zieh is not None:
            von, n, _ = self._zieh
            self._zieh, self._druck = None, None
            ziel, an = self.ablage(QPointF(e.position()), (von, n))
            if ziel is not None:
                self.gezogen.emit(von, n, ziel, an)
            self.update()
            return
        self._druck = None

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.zoom_setzen(self.zoom * (1.25 if e.angleDelta().y() > 0 else 0.8))
            e.accept()
            return
        super().wheelEvent(e)


def _karte(titel):
    rahmen = QFrame()
    rahmen.setObjectName("karte")
    rahmen.setFrameShape(QFrame.StyledPanel)
    lay = QVBoxLayout(rahmen)
    lay.setContentsMargins(8, 6, 8, 6)
    kopf = QLabel(titel)
    kopf.setStyleSheet(f"color: {stil.TEXT_GRAU}; font-size: 8pt;")
    wert = QLabel("—")
    f = wert.font()
    f.setPointSizeF(f.pointSizeF() + 3)
    f.setBold(True)
    wert.setFont(f)
    wert.setWordWrap(True)
    lay.addWidget(kopf)
    lay.addWidget(wert)
    return rahmen, wert


class NestingDialog(QDialog):
    """vergleich: Ergebnis von nesting_vergleich.vergleich; positionen: Positionen des Angebots (Bezug je Teil).
    start = (Abmessungsschlüssel, Stangennummer im Schnittplan oder None): beim Öffnen diese Abmessung und den
    gespeicherten Plan zeigen (Sprung aus dem Stangenbild)."""

    def __init__(self, vergleich, positionen, parent=None, nur_lesen=False, start=None):
        super().__init__(parent)
        self.setWindowTitle("Nesting-Arbeitsplatz")
        self.resize(1440, 900)
        self.vergleich, self.positionen = vergleich, positionen
        self.wahl, self.hand = {}, {}           # Ergebnis: {Abmessung: Strategie}, {Abmessung: Stangen}
        self.hand_stangen, self.verlauf, self.wieder = None, [], []
        self.uebrig, self.fest = [], False       # nicht eingeplante Teile; True = Reihenfolge von Hand festgelegt
        self.nur_lesen = nur_lesen

        # ---------------- Kopf
        self.abm = QComboBox()
        for v in vergleich:
            self.abm.addItem(v["titel"])
        self.abm.currentIndexChanged.connect(lambda _: self.gruppe_zeigen())
        self.ansicht_knoepfe = QButtonGroup(self)
        kopf = QHBoxLayout()
        kopf.addWidget(QLabel("Abmessung:"))
        kopf.addWidget(self.abm, 1)
        kopf.addSpacing(12)
        for name in (BEARBEITEN, STANGENBILD, DREI_D):
            b = QPushButton(name)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, n=name: self.ansicht_setzen(n))
            self.ansicht_knoepfe.addButton(b)
            kopf.addWidget(b)
        kopf.addSpacing(12)
        for txt, f, tipp in (("−", 0.8, "verkleinern (Strg + Mausrad)"), ("Einpassen", None, "ganze Stange"),
                             ("+", 1.25, "vergrößern (Strg + Mausrad)")):
            b = QPushButton(txt)
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, f=f: self.bild.zoom_setzen(1.0 if f is None else self.bild.zoom * f))
            kopf.addWidget(b)
        kopf.addSpacing(12)
        self.bereich_knoepfe = {}
        for name in ("Links", "Rechts", "Unten"):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setChecked(True)
            b.setToolTip(f"Bereich {name.lower()} ein- oder ausblenden")
            b.toggled.connect(lambda an, n=name: self.bereich_zeigen(n, an))
            self.bereich_knoepfe[name] = b
            kopf.addWidget(b)
        self.empf = QLabel("")
        self.empf.setWordWrap(True)
        self.ki = QLabel("")
        self.ki.setWordWrap(True)
        self.veraltet = QLabel("")
        self.veraltet.setWordWrap(True)
        self.veraltet.setStyleSheet(stil.ROTER_RAHMEN)
        self.veraltet.setVisible(False)

        # ---------------- Links
        self.teile_tabelle = QTableWidget(0, 5)
        self.teile_tabelle.setHorizontalHeaderLabels(["Pos.", "Artikel", "Länge [mm]", "Stück", "auf Stangen"])
        self._tabelle_stil(self.teile_tabelle)
        self.material = QLabel("")
        self.material.setWordWrap(True)
        self.material.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.reste_liste = QListWidget()
        self.uebrig_liste = QListWidget()
        self.uebrig_liste.itemSelectionChanged.connect(self._einsetzen_waehlen)
        self.links = QTabWidget()
        self.links.addTab(self.teile_tabelle, "Bauteile")
        mat = QScrollArea()
        mat.setWidgetResizable(True)
        mat.setWidget(self.material)
        self.links.addTab(mat, "Material")
        self.links.addTab(self.reste_liste, "Reststücke")
        ue = QWidget()
        ul = QVBoxLayout(ue)
        ul.setContentsMargins(0, 0, 0, 0)
        hinweis_ue = QLabel("Von Hand verschachteln: Teil wählen, dann auf die Stelle einer Stange klicken (unter "
                            "der letzten Stange = neue Stange). Was hier bleibt, plant „Übernehmen“ mit Strategie B "
                            "dazu.")
        hinweis_ue.setWordWrap(True)
        ul.addWidget(hinweis_ue)
        ul.addWidget(self.uebrig_liste, 1)
        self.links.addTab(ue, "Nicht eingeplant")
        self.links.setMinimumWidth(240)

        # ---------------- Mitte
        self.bild = NestingBild()
        self.bild.teil_gewaehlt.connect(self.teil_gewaehlt)
        self.bild.ziel.connect(self.ziel_gewaehlt)
        self.bild.gezogen.connect(self.gezogen)
        self.bild.einsetzen.connect(self.eingesetzt)
        self.bild.stange_gewaehlt.connect(self.stange_gewaehlt)
        self.rahmen = QScrollArea()
        self.rahmen.setWidgetResizable(True)
        self.rahmen.setWidget(self.bild)
        from .nesting_3d import Nesting3D
        from .stangen_ansicht import UEBERSICHT, StangenSeite
        self.stangenseite = StangenSeite(UEBERSICHT)
        self.drei_d = Nesting3D()
        self.mitte = QStackedWidget()
        self.mitte.addWidget(self.rahmen)
        self.mitte.addWidget(self.stangenseite)
        self.mitte.addWidget(self.drei_d)
        self.hinweis = QLabel("")
        self.hinweis.setWordWrap(True)
        self.kennzahlen = QLabel("")
        self.kennzahlen.setWordWrap(True)
        mitte_w = QWidget()
        mw = QVBoxLayout(mitte_w)
        mw.setContentsMargins(0, 0, 0, 0)
        mw.addWidget(self.mitte, 1)
        mw.addWidget(self.kennzahlen)
        mw.addWidget(self.hinweis)

        # ---------------- Rechts
        self.rechts = QWidget()
        rg = QGridLayout(self.rechts)
        rg.setContentsMargins(4, 0, 4, 0)
        self.karten = {}
        for n, (schl, titel) in enumerate((("ausnutzung", "Materialausnutzung"), ("verschnitt", "Verschnitt"),
                                           ("stangen", "Benötigte Stangen"), ("laenge", "Eingekaufte Länge"),
                                           ("reste", "Verwertbare Reststücke"), ("kosten", "Materialkosten"),
                                           ("ersparnis", "Einsparung"), ("status", "Berechnungsstatus"),
                                           ("machbar", "Machbarkeit"))):
            k, w = _karte(titel)
            self.karten[schl] = w
            rg.addWidget(k, n // 2, n % 2)
        rg.setRowStretch(5, 1)
        self.rechts.setMinimumWidth(300)

        # ---------------- Unten
        self.tabelle = QTableWidget(0, len(nv.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels([t for _, t in nv.SPALTEN])
        self._tabelle_stil(self.tabelle)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.itemSelectionChanged.connect(self.zeile_gewaehlt)
        self.pos_tabelle = QTableWidget(0, 3)
        self.pos_tabelle.setHorizontalHeaderLabels(["Position", "Teilelänge [m]", "Material [€]"])
        self._tabelle_stil(self.pos_tabelle)
        self.protokoll = QPlainTextEdit()
        self.protokoll.setReadOnly(True)
        exp = QWidget()
        el = QHBoxLayout(exp)
        self.k_csv = QPushButton("Schnittplan als CSV speichern …")
        self.k_csv.clicked.connect(lambda: self.csv_speichern())
        el.addWidget(self.k_csv)
        el.addWidget(QLabel("Semikolon-getrennt, je Teil eine Zeile (Stange, Platz, Pos., Länge, von/bis, Trennung, "
                            "Rest), für Excel und die Arbeitsvorbereitung."), 1)
        self.unten = QTabWidget()
        self.unten.addTab(self.tabelle, "Optimierungsvergleich")
        self.unten.addTab(self.pos_tabelle, "Kosten je Position")
        self.unten.addTab(self.protokoll, "Berechnungsprotokoll")
        self.unten.addTab(exp, "Export")

        # ---------------- Knöpfe
        self.k_strategie = QPushButton("Strategie übernehmen")
        self.k_strategie.setObjectName("primaer")
        self.k_strategie.clicked.connect(lambda: self.strategie_uebernehmen())
        self.k_hand = QPushButton("Belegung von Hand übernehmen")
        self.k_hand.clicked.connect(lambda: self.hand_uebernehmen())
        self.k_zurueck = QPushButton("Rückgängig")
        self.k_zurueck.clicked.connect(lambda: self.rueckgaengig())
        self.k_wieder = QPushButton("Wiederholen")
        self.k_wieder.clicked.connect(lambda: self.wiederholen())
        self.k_aufloesen = QPushButton("Stange auflösen")
        self.k_aufloesen.setToolTip("Teile der gewählten Stange nach „Nicht eingeplant“ legen (von Hand verschachteln)")
        self.k_aufloesen.clicked.connect(lambda: self.stange_aufloesen())
        self.k_abm_zurueck = QPushButton("Abmessung zurücksetzen")
        self.k_abm_zurueck.setToolTip("Alle Änderungen dieser Abmessung verwerfen: Plan der gewählten Strategie; eine "
                                      "gespeicherte Belegung von Hand wird beim Übernehmen entfernt")
        self.k_abm_zurueck.clicked.connect(lambda: self.abmessung_zuruecksetzen())
        self.k_alles_zurueck = QPushButton("Alles zurücksetzen")
        self.k_alles_zurueck.setToolTip("Belegungen von Hand aller Abmessungen verwerfen: rechnet wie Optimieren (F9) "
                                        "mit der gewählten Strategie")
        self.k_alles_zurueck.clicked.connect(lambda: self.alles_zuruecksetzen())
        self.k_bisher = QPushButton("Wie bisher rechnen")
        self.k_bisher.clicked.connect(lambda: self.bisher_uebernehmen())
        self.k_ok = QPushButton("Übernehmen und neu optimieren")
        self.k_ok.clicked.connect(self.accept)
        k_zu = QPushButton("Schließen")
        k_zu.clicked.connect(self.reject)
        for k in (self.k_strategie, self.k_hand, self.k_bisher, self.k_abm_zurueck, self.k_alles_zurueck):
            k.setEnabled(not nur_lesen)
        self.k_ok.setEnabled(False)
        unten_k = QHBoxLayout()
        for k in (self.k_strategie, self.k_hand, self.k_zurueck, self.k_wieder, self.k_aufloesen, self.k_abm_zurueck,
                  self.k_alles_zurueck, self.k_bisher):
            unten_k.addWidget(k)
        unten_k.addStretch(1)
        unten_k.addWidget(self.k_ok)
        unten_k.addWidget(k_zu)

        # ---------------- Anordnung
        self.waagerecht = QSplitter(Qt.Horizontal)
        self.waagerecht.addWidget(self.links)
        self.waagerecht.addWidget(mitte_w)
        self.waagerecht.addWidget(self.rechts)
        self.waagerecht.setStretchFactor(1, 1)
        self.waagerecht.setSizes([280, 860, 320])
        self.senkrecht = QSplitter(Qt.Vertical)
        self.senkrecht.addWidget(self.waagerecht)
        self.senkrecht.addWidget(self.unten)
        self.senkrecht.setSizes([600, 260])
        lay = QVBoxLayout(self)
        lay.addLayout(kopf)
        lay.addWidget(self.empf)
        lay.addWidget(self.ki)
        lay.addWidget(self.veraltet)
        lay.addWidget(self.senkrecht, 1)
        lay.addLayout(unten_k)
        self.ansicht_setzen(BEARBEITEN)
        if vergleich:
            if start:
                i = next((n for n, v in enumerate(vergleich) if v["schluessel"] == start[0]), 0)
                self.abm.blockSignals(True)
                self.abm.setCurrentIndex(i)
                self.abm.blockSignals(False)
            self.gruppe_zeigen()
            if start and start[1] is not None:
                self.stange_anspringen(start[1])
        else:
            self.empf.setText("Keine Abmessung zum Verschachteln (Kundenmaterial, Muster und von Hand vorgegebene "
                              "Stangen rechnen wie bisher).")
        self._knoepfe()

    @staticmethod
    def _tabelle_stil(t):
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.setAlternatingRowColors(True)

    # -------------------------------------------------------------- Bereiche und Ansicht
    def bereich_zeigen(self, name, an):
        {"Links": self.links, "Rechts": self.rechts, "Unten": self.unten}[name].setVisible(an)

    def ansicht_setzen(self, name):
        for b in self.ansicht_knoepfe.buttons():
            b.setChecked(b.text() == name)
        self.mitte.setCurrentIndex((BEARBEITEN, STANGENBILD, DREI_D).index(name))
        self.ansicht = name
        self._nebenansichten()

    def _nebenansichten(self):
        """Stangenbild der Optimierung und 3D aus denselben Stangen wie das 2D-Bild."""
        anz = self.bild.anzeige
        if self.mitte.currentIndex() == 1:
            self.stangenseite.setzen([(s, None) for s in anz])
        elif self.mitte.currentIndex() == 2:
            i = self.bild.stange_nr if self.bild.stange_nr is not None else 0
            self._drei_d_stange(i)

    def _drei_d_stange(self, i):
        v = self.aktuell()
        s = self.bild._anzeige_von(i) if self.bild.stangen else None
        if s is None:
            self.drei_d.setzen(None, [])
            return
        self.drei_d.setzen(dict(s, nr=i + 1), bereiche(s), {r: f.name() for r, f in self.bild.farben.items()},
                           v["gruppe"].querschnitt if v else ())

    def stange_gewaehlt(self, i):
        self.bild.stange_nr = i
        self.bild.update()
        if self.mitte.currentIndex() == 2:
            self._drei_d_stange(i)
        self._knoepfe()

    def stange_anspringen(self, nr):
        """Stange nr (Nummer im Schnittplan) im Bild wählen und hinrollen (Sprung aus dem Stangenbild)."""
        v = self.aktuell()
        if v is None:
            return
        r = next((n for n, z in enumerate(v["zeilen"]) if z["strategie"] == nv.AKTUELL), None)
        if r is not None:
            self.tabelle.selectRow(r)
        nummern = v.get("aktuell_nummern") or []
        i = nummern.index(nr) if nr in nummern else None
        if i is not None and i < len(self.bild.stangen):
            self.stange_gewaehlt(i)
            self.rahmen.ensureVisible(0, self.bild.OBEN + i * self.bild.ZEILE, 0, self.bild.ZEILE)

    # -------------------------------------------------------------- Anzeige
    def aktuell(self):
        i = self.abm.currentIndex()
        return self.vergleich[i] if 0 <= i < len(self.vergleich) else None

    def gruppe_zeigen(self):
        v = self.aktuell()
        if v is None:
            return
        self.hand_stangen, self.verlauf, self.wieder, self.uebrig, self.fest = None, [], [], [], False
        s, text = v["empfehlung"]
        gew = self.wahl.get(v["schluessel"], v["gewaehlt"]) or "bisher"
        self.empf.setText(f"<b>Empfehlung:</b> {text}<br>Gewählt für diese Abmessung: <b>{gew}</b>")
        from . import nesting_hinweise
        hw = nesting_hinweise.hinweise(v)
        self.ki.setText(("<b>Hinweise (lokal, nur Vorschläge):</b> " + " · ".join(hw)) if hw else "")
        self.veraltet.setVisible(bool(v.get("veraltet")))
        self.veraltet.setText("Der gespeicherte Schnittplan passt nicht mehr zu den Eingaben (Teile, Mengen, Preise "
                              "oder Einstellungen geändert). Die Strategien unten sind neu gerechnet; „Übernehmen“ "
                              "optimiert das Angebot neu.")
        t = self.tabelle
        t.blockSignals(True)
        t.setRowCount(0)
        for z in v["zeilen"]:
            r = t.rowCount()
            t.insertRow(r)
            for c, (schl, _) in enumerate(nv.SPALTEN):
                it = QTableWidgetItem(nv.text(z, schl))
                if z["strategie"] == s:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                if not z.get("zulaessig", True):
                    it.setForeground(stil.farbe(stil.ROT))
                t.setItem(r, c, it)
        t.blockSignals(False)
        self._links_fuellen(v)
        self.protokoll.setPlainText("\n".join(nv.protokoll(v)))
        ziel = next((r for r, z in enumerate(v["zeilen"]) if z["strategie"] == s), 0)
        t.selectRow(ziel)
        self.zeile_gewaehlt()

    def _links_fuellen(self, v):
        g, d = v["gruppe"], v["daten"]
        je = {}
        for t in g.teile:
            je.setdefault(t.zeile, []).append(t)
        tt = self.teile_tabelle
        tt.setRowCount(0)
        self._teile_zeilen = list(je)
        for zeile, ts in je.items():
            r = tt.rowCount()
            tt.insertRow(r)
            p = self.positionen[zeile - rechnen.ZEILE0]
            laengen = sorted({round(t.laenge, 1) for t in ts})
            for c, txt in enumerate((str(p.get("pos") or ""), str(p.get("artikel") or ""),
                                     ", ".join(rechnen.zahl(x, 1) for x in laengen), str(len(ts)), "")):
                tt.setItem(r, c, QTableWidgetItem(txt))
        z = rechnen.zahl
        m = v.get("maschine") or {}
        laengen = "".join(f"<li>{z(x.laenge, 0)} mm: {z(x.preis) + ' € je Stange' if x.preis is not None else 'Preis fehlt'}"
                          + (f", Mindestabnahme {x.mindest} Stangen" if x.mindest else "") + "</li>"
                          for x in d["laengen"])
        zs = "".join(f"<li>{z(x.laenge, 0)} mm mit Zuschnitt beim Lieferanten: "
                     f"{z(x.preis) + ' €' if x.preis is not None else 'Preis fehlt'}</li>" for x in d.get("zuschnitt") or ())
        self.material.setText(
            f"<b>{g.profil}</b><br>Werkstoff {g.werkstoff}" + (f", Oberfläche {g.oberflaeche}" if g.oberflaeche else "")
            + f"<br>Stangenlänge des Angebots {z(g.stange, 0)} mm<br><b>Lieferlängen</b><ul>{laengen or '<li>keine</li>'}"
            f"{zs}</ul><b>Fertigungswerte</b><br>Endbeschnitt {z(g.endbeschnitt, 0)} mm · Greiferrest "
            f"{z(g.greiferrest, 0)} mm · Schnittverlust {z(g.kerf, 1)} mm · Abstand getrennte Schnitte {z(g.abstand, 1)} mm"
            + (f"<br>Maschine: max. Stangenlänge {z(m.get('max_stange'), 0)} mm" if m.get("max_stange") else "")
            + (f", Lademinimum {z(m.get('lademinimum'), 0)} mm" if m.get("lademinimum") else "")
            + f"<br>Rest verwertbar ab {z(max(d['min_rest'] or 0, g.endbeschnitt + g.greiferrest + g.kerf + (d['min_nutz'] or 0)), 0)} mm")
        self.reste_liste.clear()
        if d["reste"]:
            for r in d["reste"]:
                self.reste_liste.addItem(f"{r.kennung}: {z(r.laenge, 0)} mm, Wert {z(r.wert)} €")
        else:
            self.reste_liste.addItem("Reststücke im Nesting nur mit Lager und Reststücken eingeschaltet "
                                     "(Einstellungen), sonst keine passenden frei.")

    def _teile_eingeplant(self, stangen):
        n = {}
        for _, f, _ in stangen:
            for t, _ in f:
                n[t.zeile] = n.get(t.zeile, 0) + 1
        for r, zeile in enumerate(getattr(self, "_teile_zeilen", [])):
            it = self.teile_tabelle.item(r, 4)
            if it is not None:
                it.setText(str(n.get(zeile, 0)))
        self.uebrig_liste.clear()
        for t in self.uebrig:
            self.uebrig_liste.addItem(QListWidgetItem(f"Pos. {t.pos} · {rechnen.zahl(t.laenge, 1)} mm"))

    def strategie_der_zeile(self):
        v = self.aktuell()
        r = self.tabelle.currentRow()
        return v["zeilen"][r]["strategie"] if v and 0 <= r < len(v["zeilen"]) else None

    def plan_der_zeile(self):
        v = self.aktuell()
        s = self.strategie_der_zeile()
        return v["plaene"].get(s) if v and s else None

    def zeile_gewaehlt(self):
        v, p = self.aktuell(), self.plan_der_zeile()
        if v is None:
            return
        self.hand_stangen, self.verlauf, self.wieder, self.uebrig, self.fest = None, [], [], [], False
        zs = v["zuschnitt"].get(self.strategie_der_zeile())
        self.hinweis.setText("")
        if zs:
            self._bild_zuschnitt(zs)
        else:
            self._bild(p.stangen if p else [])
        self.k_hand.setEnabled(False)
        self._knoepfe()

    def _bild_zuschnitt(self, zs):
        """Zuschnitt-Variante: je Lieferstange (z. B. 12 m) die zugeschnittenen Stücke mit ihren Teilen, danach die
        übrigen ladbaren Stangen. Nur ansehen (die Stücke legt der Zuschnitt fest), Kennzahlen aus der Zeile."""
        v = self.aktuell()
        d, g = v["daten"], v["gruppe"]
        stangen, marken = [], []
        lm = rechnen.m_text(zs["laenge"])
        for j, lief in enumerate(zs["v"]["stangen"]):
            for n, (laenge, f) in enumerate(lief):
                stangen.append((laenge, f, ""))
                marken.append(f"{lm} m Nr. {j + 1}" if n == 0 else "↳")
            uebrig = zs["laenge"] - sum(laenge for laenge, _ in lief)
            if uebrig > 50.0:                              # nicht gebrauchtes Stück (ohne Sägeschnitte) der bezahlten Lieferstange
                stangen.append((uebrig, [], ""))
                marken.append("↳ übrig")
        rest = zs["plan"].stangen if zs["plan"] is not None else []
        for i, (laenge, f, r) in enumerate(rest):
            stangen.append((laenge, f, r))
            marken.append(f"{len(zs['v']['stangen']) + i + 1}")
        self.bild.setzen(g, stangen, d["min_rest"], d["min_nutz"], marken, gesperrt=True, positionen=self.positionen,
                         reste=d["reste"])
        z, w = rechnen.zahl, zs["werte"]
        teile = sum(t.laenge for _, f, _ in stangen for t, _ in f)
        ungenutzt = sum(laenge for laenge, f, _ in stangen if not f)
        self.kennzahlen.setText(
            f"{len(zs['v']['stangen'])} × {lm} m mit Zuschnitt beim Lieferanten (ganze Stange bezahlt)"
            + (f" + {ne.laengen_text(zs['plan'].werte['je_laenge'])}" if zs["plan"] is not None else "")
            + f": eingekauft {z(w['gekauft_mm'] / 1000)} m, Einkauf "
            f"{z(w['einkauf']) if w.get('einkauf') is not None else 'Preis fehlt'} €, Teile {z(teile / 1000)} m, "
            f"{w['beladungen']} Beladungen"
            + (f", davon {z(ungenutzt / 1000)} m bezahlt, aber nicht gebraucht (Reststücke)" if ungenutzt else "")
            + ".")
        self.hinweis.setText("Zuschnitt: Teile hier nicht umsetzbar, die Stücke legt der Zuschnitt fest. "
                             "Übernehmen plant genau so.")
        self.pos_tabelle.setRowCount(0)
        self._karten(None, zs)
        self._nebenansichten()

    def _werte(self, stangen):
        v = self.aktuell()
        d, g = v["daten"], v["gruppe"]
        return ne.kennzahlen(g, stangen, list(self.uebrig), ne._laengen_fuer(g, d["laengen"]) or [ne.Laenge(g.stange)],
                             d["reste"], d["je_beladung"], d["min_rest"], d["min_nutz"])

    def _bild(self, stangen):
        v = self.aktuell()
        d = v["daten"]
        self.bild.setzen(v["gruppe"], stangen, d["min_rest"], d["min_nutz"], positionen=self.positionen,
                         reste=d["reste"])
        self._teile_eingeplant(stangen)
        self._nebenansichten()
        if not stangen:
            self.kennzahlen.setText("")
            self.pos_tabelle.setRowCount(0)
            self._karten(None)
            return
        w = self._werte(stangen)
        z = rechnen.zahl
        self.kennzahlen.setText(
            f"{w['stangen']} Stangen ({ne.laengen_text(w['je_laenge'])}), eingekauft {z(w['gekauft_mm'] / 1000)} m, "
            f"Einkauf {z(w['einkauf']) if w['einkauf'] is not None else 'Preis fehlt'} €, Teile "
            f"{z(w['teile_mm'] / 1000)} m, Schnitt {z(w['schnitt_mm'], 0)} mm, verwertbarer Rest "
            f"{z(w['rest_verwertbar_mm'], 0)} mm, Verschnitt {z(w['verschnitt_mm'], 0)} mm, Ausnutzung "
            f"{z(100 * w['ausnutzung'], 1)} %. Bilanz: Teile + Schnitt + Rest + Verschnitt = "
            f"{z(w['gesamt_mm'], 0)} mm (geprüft)."
            + (f" {len(self.uebrig)} Teile nicht eingeplant." if self.uebrig else ""))
        pt = self.pos_tabelle
        pt.setRowCount(0)
        for zeile, mm in w["mm_position"].items():
            r = pt.rowCount()
            pt.insertRow(r)
            p = self.positionen[zeile - rechnen.ZEILE0]
            eur = w["eur_position"].get(zeile)
            for c, txt in enumerate((f"Pos. {p.get('pos')}", z(mm / 1000), z(eur) if eur is not None else "—")):
                pt.setItem(r, c, QTableWidgetItem(txt))
        self._karten(w, stangen=stangen)

    def _karten(self, w, zs=None, stangen=None):
        """Kennzahlen rechts; Einsparung gegen den gespeicherten Plan (sonst den bisherigen)."""
        v = self.aktuell()
        k = self.karten
        z = rechnen.zahl
        for x in k.values():
            x.setText("—")
        if v is None:
            return
        if zs is not None:
            w2 = zs["werte"]
            k["stangen"].setText(f"{w2['beladungen']} Beladungen")
            k["laenge"].setText(f"{z(w2['gekauft_mm'] / 1000)} m")
            k["kosten"].setText(f"{z(w2['einkauf'])} €" if w2.get("einkauf") is not None else "Preis fehlt")
            k["status"].setText("Zuschnitt-Variante")
            return
        if w is None:
            return
        basis = v["plaene"].get(nv.AKTUELL) or v["plaene"].get(nv.BISHER)
        k["ausnutzung"].setText(f"{z(100 * w['ausnutzung'], 1)} %")
        k["verschnitt"].setText(f"{z(w['verschnitt_mm'], 0)} mm ({z(100 * w['verschnitt'], 1)} %)")
        k["stangen"].setText(f"{w['stangen']} ({ne.laengen_text(w['je_laenge'])})")
        k["laenge"].setText(f"{z(w['gekauft_mm'] / 1000)} m")
        k["reste"].setText(", ".join(z(x, 0) for x in w["neue_reste"][:6]) + " mm" if w["neue_reste"] else "keine")
        k["kosten"].setText((f"{z(w['einkauf'])} € Einkauf" if w["einkauf"] is not None else "Preis fehlt")
                            + (f"\n{z(w['eur_teil'])} € je Teil" if w.get("eur_teil") is not None else ""))
        if basis is not None:
            bw = basis.werte
            name = "gespeichert" if basis.strategie == nv.AKTUELL else "bisher"
            teile = []
            if bw.get("einkauf") is not None and w["einkauf"] is not None:
                teile.append(f"{z(bw['einkauf'] - w['einkauf'])} €")
            teile.append(f"{z((bw['gekauft_mm'] - w['gekauft_mm']) / 1000)} m")
            teile.append(f"{bw['stangen'] - w['stangen']} Stangen")
            k["ersparnis"].setText(" · ".join(teile) + f"\nggü. {name}")
        ug = v.get("untergrenze")
        k["status"].setText(("bewiesen optimal (bisheriger Plan)" if v.get("bewiesen") else
                             f"Schranke {v.get('schranke', 0)} Stangen") + f"\nUntergrenze {ug} auf "
                            f"{rechnen.m_text(v['gruppe'].stange)} m")
        if stangen is not None:
            from . import nesting_machbarkeit as nm
            g = v["gruppe"]
            prof, kgm = v.get("profil_werte") or (None, None)
            b = nm.pruefen(g, stangen, v.get("maschine"), prof, kgm, self.uebrig, v["daten"]["reste"])
            k["machbar"].setText(nm.text(b, 2))
            k["machbar"].setStyleSheet(f"color: {stil.ROT};" if not nm.zulaessig(b) else "")

    # -------------------------------------------------------------- Belegung von Hand
    def _knoepfe(self):
        aend = not self.nur_lesen and not self.bild.gesperrt
        self.k_zurueck.setEnabled(bool(self.verlauf))
        self.k_wieder.setEnabled(bool(self.wieder))
        self.k_aufloesen.setEnabled(aend and self.bild.stange_nr is not None and
                                    0 <= self.bild.stange_nr < len(self.bild.stangen))

    def teil_gewaehlt(self, i, n):
        laenge, folge, _ = self.bild.stangen[i]
        t = folge[n][0]
        p = self.positionen[t.zeile - rechnen.ZEILE0]
        self.hinweis.setText(f"Gewählt: Pos. {p.get('pos')} {p.get('artikel') or ''}, {rechnen.zahl(t.laenge, 1)} mm "
                             f"auf Stange {i + 1}. Ziehen: an eine andere Stelle oder Stange; Klick auf eine andere "
                             "Stange: dorthin (rechts daneben = neue Stange).")

    def _neu(self, neu, uebrig, text, fest=None):
        self.verlauf.append((self.bild.stangen, list(self.uebrig), self.fest))
        self.wieder = []
        self.hand_stangen, self.uebrig = neu, list(uebrig)
        if fest is not None:
            self.fest = self.fest or fest
        self._bild(neu)
        self.hinweis.setText(text)
        self.k_hand.setEnabled(not self.nur_lesen)
        self._knoepfe()

    def ziel_gewaehlt(self, nach):
        v = self.aktuell()
        if v is None or self.bild.auswahl is None:
            return
        von, n = self.bild.auswahl
        neu, fehler = nv.verschieben(v["gruppe"], self.bild.stangen, von, n, None if nach < 0 else nach, v["daten"],
                                     self.uebrig)
        if fehler:
            self.hinweis.setText(fehler)
            self.bild.auswahl = None
            self.bild.update()
            return
        self._neu(neu, self.uebrig, "Teil umgesetzt und geprüft (keine Stange überbelegt). „Belegung von Hand "
                                    "übernehmen“ speichert diese Stangen für die Abmessung.")

    def gezogen(self, von, n, nach, an):
        """Teil frei verschoben (Ziehen mit der Maus): Reihenfolge bleibt wie abgelegt."""
        v = self.aktuell()
        if v is None or self.bild.gesperrt:
            return
        if nach == von and an == n:
            return
        neu, uebrig, fehler = nv.einfuegen(v["gruppe"], self.bild.stangen, von, n, None if nach < 0 else nach, an,
                                           v["daten"], self.uebrig)
        self.bild.auswahl = None
        if fehler:
            self.hinweis.setText(fehler + " Das Teil bleibt, wo es war.")
            self.bild.update()
            return
        self._neu(neu, uebrig, "Teil verschoben und geprüft (Reihenfolge wie abgelegt, gemeinsamer Schnitt und "
                               "Gehrungen ineinander ergeben sich daraus).", fest=True)

    def _einsetzen_waehlen(self):
        self.bild.einsetz_modus = bool(self.uebrig_liste.selectedItems()) and not self.bild.gesperrt
        if self.bild.einsetz_modus:
            self.hinweis.setText("Jetzt auf die Stelle einer Stange klicken (unter der letzten Stange = neue Stange).")

    def eingesetzt(self, nach, an):
        v = self.aktuell()
        rows = [self.uebrig_liste.row(i) for i in self.uebrig_liste.selectedItems()]
        self.bild.einsetz_modus = False
        if v is None or not rows:
            return
        neu, uebrig, fehler = nv.einfuegen(v["gruppe"], self.bild.stangen, None, rows[0], None if nach < 0 else nach,
                                           an, v["daten"], self.uebrig)
        if fehler:
            self.hinweis.setText(fehler)
            return
        self._neu(neu, uebrig, "Teil eingesetzt und geprüft.", fest=True)

    def stange_aufloesen(self):
        v, i = self.aktuell(), self.bild.stange_nr
        if v is None or i is None or not (0 <= i < len(self.bild.stangen)) or self.bild.gesperrt:
            return
        neu, uebrig = nv.aufloesen(v["gruppe"], self.bild.stangen, i, self.uebrig)
        self.bild.stange_nr = None
        self._neu(neu, uebrig, f"Stange {i + 1} aufgelöst: {len(uebrig) - len(self.uebrig)} Teile unter „Nicht "
                               "eingeplant“. Teil wählen und auf eine Stange klicken.", fest=True)
        self.links.setCurrentIndex(3)

    def rueckgaengig(self):
        if not self.verlauf:
            return
        self.wieder.append((self.bild.stangen, list(self.uebrig), self.fest))
        alt, self.uebrig, self.fest = self.verlauf.pop()
        self.hand_stangen = alt if self.verlauf else None
        self._bild(alt)
        self.k_hand.setEnabled(bool(self.verlauf) and self.k_strategie.isEnabled())
        self._knoepfe()

    def wiederholen(self):
        if not self.wieder:
            return
        self.verlauf.append((self.bild.stangen, list(self.uebrig), self.fest))
        neu, self.uebrig, self.fest = self.wieder.pop()
        self.hand_stangen = neu
        self._bild(neu)
        self.k_hand.setEnabled(self.k_strategie.isEnabled())
        self._knoepfe()

    def abmessung_zuruecksetzen(self):
        """Alle Änderungen dieser Abmessung verwerfen; eine gespeicherte Belegung von Hand wird beim Übernehmen
        entfernt (Abmessung rechnet wieder mit der gewählten Strategie)."""
        v = self.aktuell()
        if v is None:
            return None
        if v["gewaehlt"] == rechnen.NESTING_HAND or self.hand.get(v["schluessel"]):
            self.hand[v["schluessel"]] = None
            self.k_ok.setEnabled(True)
        self.zeile_gewaehlt()
        self.hinweis.setText(f"{v['titel']}: zurückgesetzt auf den Plan der gewählten Zeile"
                             + (" (gespeicherte Belegung von Hand wird beim Übernehmen entfernt)."
                                if v["schluessel"] in self.hand and self.hand[v["schluessel"]] is None else "."))
        return True

    def alles_zuruecksetzen(self):
        """Belegungen von Hand aller Abmessungen verwerfen (rechnet danach wie Optimieren mit der Strategie)."""
        n = 0
        for v in self.vergleich:
            if v["gewaehlt"] == rechnen.NESTING_HAND or self.hand.get(v["schluessel"]):
                self.hand[v["schluessel"]] = None
                n += 1
        self.zeile_gewaehlt()
        if n:
            self.k_ok.setEnabled(True)
        self.hinweis.setText(f"Alles zurückgesetzt: {n} Belegung(en) von Hand werden beim Übernehmen entfernt."
                             if n else "Alles zurückgesetzt: keine gespeicherte Belegung von Hand.")
        return n

    # -------------------------------------------------------------- Übernehmen
    def _gemerkt(self, text):
        self.k_ok.setEnabled(True)
        self.gruppe_zeigen()
        self.hinweis.setText(text + " Mit „Übernehmen und neu optimieren“ gilt es im Angebot.")

    def strategie_uebernehmen(self):
        v, s = self.aktuell(), self.strategie_der_zeile()
        if v is None or s is None:
            return None
        if s == nv.AKTUELL:
            self.hinweis.setText("Der gespeicherte Plan gilt schon; nichts zu übernehmen.")
            return s
        z = next((x for x in v["zeilen"] if x["strategie"] == s), {})
        if not z.get("zulaessig", True):
            self.hinweis.setText(f"Strategie {s} ist technisch nicht zulässig: {z.get('machbar')}")
            return None
        self.wahl[v["schluessel"]] = "bisher" if s == nv.BISHER else s
        self.hand[v["schluessel"]] = None
        self._gemerkt(f"{v['titel']}: Strategie {self.wahl[v['schluessel']]} vorgemerkt.")
        return s

    def hand_uebernehmen(self):
        v = self.aktuell()
        if v is None or not self.hand_stangen:
            return None
        self.hand[v["schluessel"]] = nv.hand_aus_plan(ne.Plan("Hand", self.hand_stangen), self.positionen,
                                                      fest=self.fest)
        rest = len(self.uebrig)
        self._gemerkt(f"{v['titel']}: Belegung von Hand ({len(self.hand_stangen)} Stangen) vorgemerkt"
                      + (f", {rest} nicht eingeplante Teile plant Strategie B dazu." if rest else "."))
        return self.hand[v["schluessel"]]

    def bisher_uebernehmen(self):
        v = self.aktuell()
        if v is None:
            return None
        self.wahl[v["schluessel"]] = "bisher"
        self.hand[v["schluessel"]] = None
        self._gemerkt(f"{v['titel']}: wieder wie bisher.")
        return True

    def csv_speichern(self, pfad=None):
        """Schnittplan der gezeigten Stangen als CSV (nesting_vergleich.export_csv). Ergebnis: Pfad oder None."""
        v = self.aktuell()
        if v is None or not self.bild.stangen:
            return None
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Schnittplan speichern", "Schnittplan.csv", "CSV (*.csv)")
            if not pfad:
                return None
        plan = ne.Plan(self.strategie_der_zeile() or "Hand", [s for s in self.bild.stangen if s[1]])
        with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
            f.write(nv.export_csv(v, plan, self.positionen))
        self.hinweis.setText(f"Gespeichert: {pfad}")
        return pfad
