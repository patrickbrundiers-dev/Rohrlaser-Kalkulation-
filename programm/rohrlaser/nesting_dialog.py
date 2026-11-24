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
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import nesting as ne, nesting_abwicklung as na, nesting_vergleich as nv, optimierung as opt, rechnen, stil
from . import stangen_abwicklung as sa
from . import nesting_ansicht_ui as ui
from .nesting_abwicklung_bild import EBENEN, AbwicklungAnsicht
from .stangen_ansicht import MASS_HOEHE, LINEAL_HOEHE, stange_zeichnen, teil_farben

BEARBEITEN, STANGENBILD, DREI_D = "Alle Stangen", "Stangenbild", "3D"
ABWICKLUNG, TECHNISCH = "Abwicklung", "Technisch"
ANSICHTEN = (ABWICKLUNG, DREI_D, TECHNISCH, BEARBEITEN, STANGENBILD)     # Reihenfolge der Knöpfe und Seiten
SYMBOLE = {ABWICKLUNG: "abwicklung", DREI_D: "ansicht3d", TECHNISCH: "lineal", BEARBEITEN: "liste",
           STANGENBILD: "muster"}
ANSICHT_EINSTELLUNG = "nesting_ansicht"     # zuletzt benutzte Ansicht (Patrick 24.11.2026)


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
                                                   gewaehlt=gew, schrift=self.font(), ruhig=True):
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
    f.setPointSizeF(f.pointSizeF() + 1.5)
    f.setBold(True)
    wert.setFont(f)
    wert.setWordWrap(True)
    wert.setMinimumWidth(40)
    wert.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)     # bricht um statt die Spalte zu verbreitern
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
        tipps = {ABWICKLUNG: "Abwicklung der gewählten Stange: Teile, Schnitte, Konturen am Umfang (Hauptansicht)",
                 DREI_D: "Echte Bauteile (STEP bzw. aus den Eingaben) auf der gewählten Stange",
                 TECHNISCH: "Maßhaltige Abwicklung mit Koordinaten der Schnitte und Konturen",
                 BEARBEITEN: "Alle Stangen untereinander: Teile ziehen, von Hand verschachteln",
                 STANGENBILD: "Stangenbild wie im Reiter Optimierung"}
        self.setStyleSheet(ui.leisten_stil())
        seg = []
        for n, name in enumerate(ANSICHTEN, 1):
            b = ui.knopf(name, SYMBOLE[name], f"{tipps[name]} (Strg+{n})", umschalten=True)
            b.clicked.connect(lambda _=False, n=name: self.ansicht_setzen(n))
            QShortcut(QKeySequence(f"Ctrl+{n}"), self, activated=lambda n=name: self.ansicht_setzen(n))
            self.ansicht_knoepfe.addButton(b)
            seg.append(b)
        kopf.addWidget(ui.segment(seg))
        kopf.addSpacing(10)
        for txt, sym, f, tipp in (("−", None, 0.8, "Verkleinern (Mausrad, Taste −)"),
                                  ("Einpassen", "einpassen", None, "Ganze Stange zeigen (Taste F, Doppelklick)"),
                                  ("+", None, 1.25, "Vergrößern (Mausrad, Taste +)")):
            b = ui.knopf(txt, sym, tipp, nur_symbol=True)
            b.clicked.connect(lambda _=False, f=f: self._zoom(f))
            kopf.addWidget(b)
        kopf.addSpacing(10)
        self.bereich_knoepfe = {}
        for name in ("Links", "Rechts", "Unten"):
            b = ui.knopf(name)
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
        self.stangen_liste = QListWidget()
        self.stangen_liste.setItemDelegate(ui.StangenDelegate(self.stangen_liste))
        self.stangen_liste.setMouseTracking(True)
        self.stangen_liste.setToolTip("Stange wählen (Pfeiltasten): alle Ansichten zeigen diese Stange")
        self.stangen_liste.currentRowChanged.connect(lambda r: self.stange_gewaehlt(r) if r >= 0 else None)
        self.links = QTabWidget()
        self.links.addTab(self.stangen_liste, "Stangen")
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
        from .stangen_ansicht import UEBERSICHT, StangenSeite
        self.stangenseite = StangenSeite(UEBERSICHT)
        self._quelle(parent)
        self.abw = AbwicklungAnsicht()
        self.tech = AbwicklungAnsicht(technisch=True)
        for a in (self.abw, self.tech):
            a.teil_gewaehlt.connect(self.abwicklung_teil)
            a.bereich_gewaehlt.connect(lambda t: self.hinweis.setText(t))
            a.gemessen.connect(lambda t: self.hinweis.setText(t))
            a.zur_position.connect(self.zur_position)
            a.im_3d.connect(self.teil_im_3d)
        self.koord = QTableWidget(0, 7)
        self.koord.setHorizontalHeaderLabels(["Teil", "Art", "Kontur", "x von [mm]", "x bis [mm]", "Umfang [mm]",
                                              "Winkel [°] / Seite"])
        self._tabelle_stil(self.koord)
        self.koord.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.koord.setSelectionMode(QAbstractItemView.SingleSelection)
        self.koord.horizontalHeader().setStretchLastSection(True)
        self.koord.itemSelectionChanged.connect(self._koord_gewaehlt)
        self._koord_zeilen = []
        tech_teiler = QSplitter(Qt.Vertical)
        tech_teiler.addWidget(self.tech)
        tech_teiler.addWidget(self.koord)
        tech_teiler.setSizes([420, 200])
        tech_w = QWidget()
        tl = QVBoxLayout(tech_w)
        tl.setContentsMargins(0, 0, 0, 0)
        tleiste = QHBoxLayout()
        tleiste.addWidget(QLabel("Zeile anklicken: Stelle im Bild; Teil im Bild anklicken: seine Zeilen."), 1)
        self.k_pdf = ui.knopf("PDF", "pdf", "Abwicklung der Stange als PDF speichern (A4 quer, maßstäblich)")
        self.k_pdf.clicked.connect(lambda: self.abwicklung_speichern("pdf"))
        self.k_dxf = ui.knopf("DXF", "dxf", "Abwicklung der Stange als DXF speichern (x längs, y Umfang, mm)")
        self.k_dxf.clicked.connect(lambda: self.abwicklung_speichern("dxf"))
        tleiste.addWidget(self.k_pdf)
        tleiste.addWidget(self.k_dxf)
        tl.addLayout(tleiste)
        tl.addWidget(tech_teiler, 1)
        from .ansicht3d import Ansicht3DMitKnoepfen
        self.drei_d = Ansicht3DMitKnoepfen()
        self.drei_d.ansicht.angeklickt.connect(self._drei_d_klick)
        self.drei_d_info, self._drei_d_stand = [], None
        drei_w = QWidget()
        dl = QVBoxLayout(drei_w)
        dl.setContentsMargins(0, 0, 0, 0)
        dleiste = QHBoxLayout()
        dleiste.addWidget(QLabel("Teil anklicken: in allen Ansichten wählen."), 1)
        self.k_ganz = ui.knopf("Ganze Stange", "einpassen", "Ganze Stange zeigen statt nur das gewählte Teil",
                               umschalten=True)
        self.k_ganz.toggled.connect(lambda _: self._drei_d_einpassen())
        self.k_auf_teil = ui.knopf("Auf Teil", "auswahl", "Auf das gewählte Teil zoomen")
        self.k_auf_teil.clicked.connect(lambda: (self.k_ganz.setChecked(False), self._drei_d_einpassen()))
        dleiste.addWidget(self.k_auf_teil)
        dleiste.addWidget(self.k_ganz)
        dl.addLayout(dleiste)
        dl.addWidget(self.drei_d, 1)
        self.mitte = QStackedWidget()
        self.seiten = {ABWICKLUNG: self._abw_seite(), DREI_D: drei_w, TECHNISCH: tech_w,
                       BEARBEITEN: self.rahmen, STANGENBILD: self.stangenseite}
        for name in ANSICHTEN:
            self.mitte.addWidget(self.seiten[name])
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
        rechts_innen = QWidget()
        rg = QGridLayout(rechts_innen)
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
        self.karte_stange = ui.InfoKarte("Stange")
        self.karte_teil = ui.InfoKarte("Teil")
        from .ansicht3d import Ansicht3D
        self.teil_vorschau = Ansicht3D()
        self.teil_vorschau.legende_an = False
        self.teil_vorschau.setMinimumHeight(150)
        self.teil_vorschau.setMaximumHeight(170)
        self.teil_vorschau.setMinimumWidth(120)
        self.teil_vorschau.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.karte_teil.lay.insertWidget(1, self.teil_vorschau)
        self.karte_teil.setVisible(False)
        info_w = QWidget()
        il = QVBoxLayout(info_w)
        il.setContentsMargins(0, 4, 0, 0)
        il.addWidget(self.karte_stange)
        il.addWidget(self.karte_teil)
        il.addStretch(1)
        rg.addWidget(info_w, 5, 0, 1, 2)
        rg.setRowStretch(6, 1)
        self.rechts = QScrollArea()         # Kennzahlen und Infokarten rollen gemeinsam (nichts wird gestaucht)
        self.rechts.setWidgetResizable(True)
        self.rechts.setFrameShape(QFrame.NoFrame)
        self.rechts.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rechts.setWidget(rechts_innen)
        self.rechts.setMinimumWidth(320)

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
        self.ansicht_setzen(self._ansicht_gemerkt(), merken=False)
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

    def _quelle(self, parent):
        """Profil und STEP-Netz je Position von der Angebotsseite (kopf, k, db); ohne sie keine Abwicklung/3D."""
        self.profil_von, self.netz_von, self._db = None, None, getattr(parent, "db", None)
        if parent is not None and getattr(parent, "k", None) is not None and getattr(parent, "kopf", None) is not None:
            self.profil_von = sa.profil_funktion(parent.kopf, parent.k)
            db = parent.db
            self.netz_von = lambda p: db.netz(p["id"]) if p.get("id") else None
        self._merker, self._merker3d, self._abw_cache = {}, {}, {}

    def _ansicht_gemerkt(self):
        try:
            w = self._db.einstellung(ANSICHT_EINSTELLUNG) if self._db is not None else None
        except Exception:       # noqa: BLE001 – ohne Datenbank: Abwicklung
            w = None
        return w if w in ANSICHTEN else ABWICKLUNG

    def _abw_seite(self):
        """Seite Abwicklung: Werkzeugleiste (Stangenwahl, Ebenen-Menü, Richtung, 1:1, Messen) über der Zeichnung."""
        from PySide6.QtWidgets import QMenu, QToolButton
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        leiste = QHBoxLayout()
        leiste.setSpacing(4)
        self.k_voriger = ui.knopf("◀", None, "Vorige Stange (Bild auf)")
        self.k_voriger.clicked.connect(lambda: self._blaettern(-1))
        self.k_naechster = ui.knopf("▶", None, "Nächste Stange (Bild ab)")
        self.k_naechster.clicked.connect(lambda: self._blaettern(1))
        self.stange_wahl = QComboBox()
        self.stange_wahl.setMinimumContentsLength(18)
        self.stange_wahl.setToolTip("Stange wählen")
        self.stange_wahl.currentIndexChanged.connect(lambda i: self.stange_gewaehlt(i) if i >= 0 else None)
        self.stange_titel = QLabel("")
        self.stange_titel.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        for x in (self.k_voriger, self.stange_wahl, self.k_naechster):
            leiste.addWidget(x)
        leiste.addWidget(self.stange_titel, 1)
        self.k_ebenen = ui.knopf("Ebenen", "raster", "Ebenen ein- und ausblenden")
        self.k_ebenen.setPopupMode(QToolButton.InstantPopup)
        menue = QMenu(self.k_ebenen)
        self.ebenen_knoepfe = {}
        for schl, name in EBENEN:
            a = menue.addAction(name)
            a.setCheckable(True)
            a.setChecked(True)
            a.toggled.connect(lambda an, k=schl: (self.abw.ebene(k, an), self.tech.ebene(k, an)))
            self.ebenen_knoepfe[schl] = a
        self.k_ebenen.setMenu(menue)
        self.k_senkrecht = ui.knopf("Senkrecht", None, "Stange senkrecht statt waagerecht zeigen (Taste S)", True)
        self.k_senkrecht.toggled.connect(lambda an: (setattr(self.abw, "senkrecht", an), self.abw.update()))
        self.k_eins = ui.knopf("Umfang 1:1", None, "Umfang im selben Maßstab wie die Länge (sonst auf die Höhe "
                               "gestreckt)", True)
        self.k_eins.toggled.connect(lambda an: [(setattr(a, "eins_zu_eins", an), a.update()) for a in (self.abw,
                                                                                                        self.tech)])
        self.k_messen = ui.knopf("Messen", "messen", "Zwei Punkte anklicken: Abstand längs und am Umfang (Taste M, "
                                 "Esc löscht)", True)
        self.k_messen.toggled.connect(self._messen)
        for k in (self.k_ebenen, self.k_senkrecht, self.k_eins, self.k_messen):
            leiste.addWidget(k)
        QShortcut(QKeySequence("M"), w, activated=self.k_messen.toggle)
        QShortcut(QKeySequence("S"), w, activated=self.k_senkrecht.toggle)
        lay.addLayout(leiste)
        lay.addWidget(self.abw, 1)
        return w

    def _messen(self, an):
        for a in (self.abw, self.tech):
            a.messen, a.messpunkte = an, []
            a.update()
        if an:
            self.hinweis.setText("Messen: zwei Punkte in der Abwicklung anklicken.")

    def _zoom(self, f):
        name = getattr(self, "ansicht", BEARBEITEN)
        if name in (ABWICKLUNG, TECHNISCH):
            a = self.abw if name == ABWICKLUNG else self.tech
            a.einpassen() if f is None else a.zoom_um(f)
        elif name == DREI_D:
            self.drei_d.ansicht.einpassen() if f is None and hasattr(self.drei_d.ansicht, "einpassen") else None
        else:
            self.bild.zoom_setzen(1.0 if f is None else self.bild.zoom * f)

    def ansicht_setzen(self, name, merken=True):
        for b in self.ansicht_knoepfe.buttons():
            b.setChecked(b.text() == name)
        self.mitte.setCurrentIndex(ANSICHTEN.index(name))
        self.ansicht = name
        if merken and self._db is not None:
            try:
                self._db.einstellung_setzen(ANSICHT_EINSTELLUNG, name)
            except Exception:       # noqa: BLE001 – nur lesen: Ansicht nicht merken
                pass
        self._nebenansichten()

    def _stange_nr(self):
        n = len(self.bild.stangen)
        i = self.bild.stange_nr if self.bild.stange_nr is not None else 0
        return i if 0 <= i < n else (0 if n else None)

    def _nebenansichten(self):
        """Die sichtbare Ansicht aus denselben Stangen wie das 2D-Bild (nur die sichtbare wird gerechnet)."""
        anz = self.bild.anzeige
        name = getattr(self, "ansicht", BEARBEITEN)
        i = self._stange_nr()
        if name == STANGENBILD:
            self.stangenseite.setzen([(s, None) for s in anz])
        elif name in (ABWICKLUNG, TECHNISCH):
            self._abwicklung_zeigen(i)
        elif name == DREI_D:
            self._drei_d_stange(i)
        self._stange_info(i)

    def stange_daten(self, i):
        """Abwicklung der Stange i des gezeigten Plans (nesting_abwicklung.stange) oder None; je Plan zwischengemerkt."""
        s = self.bild._anzeige_von(i) if i is not None and self.bild.stangen else None
        if s is None or self.profil_von is None:
            return None, s
        schl = (id(s), i)
        if schl not in self._abw_cache:
            if len(self._abw_cache) > 64:
                self._abw_cache.clear()
            try:
                self._abw_cache[schl] = (s, na.stange(s, self.positionen, self.profil_von, self._merker))
            except (ValueError, KeyError, TypeError, ZeroDivisionError, AttributeError, IndexError):
                self._abw_cache[schl] = (s, None)
        return self._abw_cache[schl][1], s

    def _rest_ok(self, s):
        v = self.aktuell()
        if v is None or s is None:
            return None
        from .stangen_ansicht import rest_regel
        d = v["daten"]
        einst = {"rest_min_laenge": d["min_rest"], "rest_min_nutz": d["min_nutz"]}
        return rest_regel(lambda: einst)(s)

    def _abwicklung_zeigen(self, i):
        d, s = self.stange_daten(i)
        farben = {r: f.name() for r, f in self.bild.farben.items()}
        ok = self._rest_ok(s)
        self.abw.setzen(d, farben, ok)
        self.tech.setzen(d, farben, ok)
        n = len(self.bild.stangen)
        self.k_voriger.setEnabled(bool(i))
        self.k_naechster.setEnabled(i is not None and i + 1 < n)
        for k in (self.k_pdf, self.k_dxf):
            k.setEnabled(d is not None)
        if s is not None:
            self.stange_titel.setText(f"{len(s['teile'])} Teile" + (f" · Reststück {s.get('rest')}" if s.get("rest")
                                                                     else "") + (f" · ohne Daten: Pos. "
                                      f"{', '.join(str(x) for x in d['fehlt'])}" if d and d["fehlt"] else ""))
        else:
            self.stange_titel.setText("Zuschnitt bzw. leere Stange: keine Abwicklung" if n else "")
        self.koord.blockSignals(True)
        self.koord.setRowCount(0)
        self._koord_zeilen = []
        if d is not None:
            for z in na.koordinaten(d):
                r = self.koord.rowCount()
                self.koord.insertRow(r)
                werte = (z["teil"], z["art"], z["text"], rechnen.zahl(z["x"], 1),
                         rechnen.zahl(z["x_bis"], 1) if z["x_bis"] is not None else "",
                         rechnen.zahl(z["t"], 1) if z["t"] is not None else "",
                         (f"{rechnen.zahl(z['winkel'], 1)} / {z['seite']}" if z["winkel"] is not None else ""))
                for c, txt in enumerate(werte):
                    self.koord.setItem(r, c, QTableWidgetItem(txt))
                nr = int(str(z["teil"]).split(":")[0]) - 1
                self._koord_zeilen.append((nr, z["x"] if z["x_bis"] is None else (z["x"] + z["x_bis"]) / 2,
                                           z["t"] if z["t"] is not None else d["umfang"] / 2))
        self.koord.blockSignals(False)

    def _drei_d_stange(self, i):
        s = self.bild._anzeige_von(i) if i is not None and self.bild.stangen else None
        if s is None or self.profil_von is None:
            self.drei_d.setzen(None, "", "Keine 3D-Daten (Zuschnitt, leere Stange oder Profil unbekannt).")
            self.drei_d_info, self._drei_d_stand = [], None
            return
        stand = (id(s), i)
        if stand != self._drei_d_stand:
            from PySide6.QtWidgets import QApplication
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                netz, self.drei_d_info = na.netz_stange(s, self.positionen, self.profil_von, self.netz_von,
                                                        self._merker3d, {r: f.name() for r, f in self.bild.farben.items()})
            finally:
                QApplication.restoreOverrideCursor()
            step = sum(1 for x in self.drei_d_info if x["quelle"] == "STEP")
            eing = sum(1 for x in self.drei_d_info if x["quelle"] == "Eingaben")
            hinweise = [f"Teil {x['nr']}: {x['hinweis']}" for x in self.drei_d_info if x["hinweis"]]
            self.drei_d.setzen(netz, f"Stange {i + 1}: {rechnen.zahl(s['stange'], 0)} mm",
                               f"{step} Teile aus STEP, {eing} aus den Eingaben gebaut; Lage und Drehung aus dem "
                               "Nesting-Ergebnis." + (" " + " · ".join(hinweise) if hinweise else ""))
            farben = {r: f.name() for r, f in self.bild.farben.items()}
            self.drei_d.ansicht.schilder = [(x["mitte"], f"{x['nr']}: {x['pos']}", farben.get(x["ref"], "#4E79A7"))
                                            for x in self.drei_d_info if x.get("mitte")]
            self._drei_d_stand = stand
        self._drei_d_einpassen()

    def stange_gewaehlt(self, i):
        if i is None or not (0 <= i < len(self.bild.stangen)):
            return
        if self.bild.stange_nr != i:
            self.abw.auswahl = self.tech.auswahl = None
        self.bild.stange_nr = i
        self.bild.update()
        for liste, aktuell, setzen in ((self.stangen_liste, self.stangen_liste.currentRow,
                                        self.stangen_liste.setCurrentRow),
                                       (self.stange_wahl, self.stange_wahl.currentIndex,
                                        self.stange_wahl.setCurrentIndex)):
            if aktuell() != i:
                liste.blockSignals(True)
                setzen(i)
                liste.blockSignals(False)
        self._nebenansichten()
        self._knoepfe()

    def _blaettern(self, schritt):
        i = self._stange_nr()
        if i is not None:
            self.stange_gewaehlt(max(0, min(len(self.bild.stangen) - 1, i + schritt)))

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_PageDown, Qt.Key_PageUp):
            self._blaettern(1 if e.key() == Qt.Key_PageDown else -1)
            return
        super().keyPressEvent(e)

    def _stangen_liste_fuellen(self):
        """Stangenliste (mit Belegungsbalken) und Stangenwahl der Abwicklung aus den gezeigten Stangen."""
        sl, sw_ = self.stangen_liste, self.stange_wahl
        for x in (sl, sw_):
            x.blockSignals(True)
            x.clear()
        farben = {r: f.name() for r, f in self.bild.farben.items()}
        n_ges = len(self.bild.stangen)
        for n, (laenge, folge, rest) in enumerate(self.bild.stangen):
            teile = sum(t.laenge for t, _ in folge)
            name = f"Reststück {rest} – {rechnen.zahl(laenge, 0)} mm" if rest else \
                f"Stange {n + 1} – {rechnen.zahl(laenge, 0)} mm"
            item = QListWidgetItem(f"{name} · {len(folge)} Teile · "
                                   f"{rechnen.zahl(100 * teile / laenge, 1) if laenge else '0'} %")
            s = self.bild._anzeige_von(n)
            if s is not None:
                item.setData(ui.ROLLE_BALKEN, ui.balken_daten(n, s, farben, self._rest_ok(s)))
            sl.addItem(item)
            sw_.addItem(f"Stange {n + 1} von {n_ges} · {rechnen.zahl(laenge, 0)} mm" if not rest else
                        f"Reststück {rest} · {rechnen.zahl(laenge, 0)} mm")
        i = self._stange_nr()
        if i is not None:
            sl.setCurrentRow(i)
            sw_.setCurrentIndex(i)
        for x in (sl, sw_):
            x.blockSignals(False)

    def _stange_info(self, i):
        """Infokarten rechts: Stange (Material, Längen, Kennzahlen, Ausnutzung als Balken) und das gewählte Teil."""
        v = self.aktuell()
        s = self.bild._anzeige_von(i) if i is not None and self.bild.stangen else None
        if v is None or s is None:
            self.karte_stange.setzen("Stange", [])
            self.karte_teil.setVisible(False)
            return
        g, z = v["gruppe"], rechnen.zahl
        k = na.kennzahlen(None, s)
        prof = (v.get("profil_werte") or (None, None))[0] or {}
        wand = (prof.get("wand") or prof.get("s") or prof.get("wandstaerke")) if isinstance(prof, dict) else None
        kgm = (v.get("profil_werte") or (None, None))[1]
        preis = None
        for x in v["daten"]["laengen"]:
            if abs(x.laenge - s["stange"]) < 0.5 and x.preis is not None:
                preis = x.preis
        zeilen = [("Profil", f"{g.profil}" + (f", Wand {z(wand, 1)} mm" if wand else "")),
                  ("Werkstoff", f"{g.werkstoff}" + (f", {g.oberflaeche}" if g.oberflaeche else "")),
                  ("Länge", f"{z(s['stange'], 0)} mm" + (f" · {z(kgm * s['stange'] / 1000, 1)} kg" if kgm else "")),
                  ("Teile", f"{k['teile']} · Verbrauch {z(k['teile_mm'], 0)} mm"),
                  ("Schnittfugen", f"{z(k['schnitt_mm'], 1)} mm"),
                  ("Endbeschnitt", f"{z(k['end_mm'], 0)} mm"),
                  ("Rest", f"{z(k['rest_mm'], 0)} mm" + (" (verwertbar)" if self._rest_ok(s) else
                                                         " (Verschnitt)" if k["rest_mm"] > 0 else "")),
                  ("Greiferrest", f"{z(k['greif_mm'], 0)} mm"),
                  ("Kosten", f"{z(preis)} € (Lieferstange)" if preis is not None else "Preis fehlt")]
        titel = f"Stange {i + 1}" + (f" · Reststück {s.get('rest')}" if s.get("rest") else "")
        self.karte_stange.setzen(titel, zeilen, k["ausnutzung"], f"Ausnutzung {z(100 * k['ausnutzung'], 1)} %")
        self.karte_stange.titel.setText(f"{titel} · Ausnutzung {z(100 * k['ausnutzung'], 1)} %")
        self._teil_info()

    def _teil_info(self):
        a = self.abw if getattr(self, "ansicht", "") != TECHNISCH else self.tech
        if a.daten is None or a.auswahl is None or a.auswahl >= len(a.daten["teile"]):
            self.karte_teil.setVisible(False)
            return
        t = a.daten["teile"][a.auswahl]
        z = rechnen.zahl
        p = next((q for q in self.positionen if q.get("id") == t.get("position_id")), {}) or {}
        quelle = next((x["quelle"] for x in self.drei_d_info if x["nr"] == a.auswahl + 1), "")
        step = "STEP-Geometrie" if (p.get("step_merkmale") or quelle == "STEP") else "aus den Eingaben"
        self.karte_teil.setzen(f"Teil {a.auswahl + 1}: Pos. {t.get('pos')} {t.get('artikel') or ''}", [
            ("Bezeichnung", t.get("bezeichnung") or "—"),
            ("Geometrie", step),
            ("Länge", f"{z(t['laenge'], 1)} mm"),
            ("Lage", f"x {z(t['von'], 1)} bis {z(t['bis'], 1)} mm"),
            ("Umfangslage", f"+{z(t['dt'], 1)} mm"),
            ("Drehwinkel", f"{z(t['drehung'], 0)}°" + (" · gewendet (Ende B vorn)" if t.get("gewendet") else "")),
            ("Konturen", str(len(t["konturen"])))])
        self.karte_teil.setVisible(True)
        self._vorschau(t, p)

    def abwicklung_teil(self, i):
        self.abw.auswahl = self.tech.auswahl = i
        self.abw.update()
        self.tech.update()
        r = next((n for n, (nr, _, _) in enumerate(self._koord_zeilen) if nr == i), None)
        if r is not None and not self._koord_aktiv:
            self.koord.blockSignals(True)
            self.koord.selectRow(r)
            self.koord.scrollToItem(self.koord.item(r, 0))
            self.koord.blockSignals(False)
        self._stange_info(self._stange_nr())
        if getattr(self, "ansicht", "") == DREI_D:
            self._drei_d_einpassen()

    _koord_aktiv = False

    def _koord_gewaehlt(self):
        """Zeile der Koordinatentabelle: Teil wählen und die Stelle im Bild markieren und zeigen."""
        r = self.koord.currentRow()
        if not (0 <= r < len(self._koord_zeilen)):
            return
        nr, x, t = self._koord_zeilen[r]
        self._koord_aktiv = True
        try:
            self.abwicklung_teil(nr)
        finally:
            self._koord_aktiv = False
        self.tech.punkt_markiert = (x, t)
        self.tech.teil_zeigen(nr)

    def _drei_d_klick(self, treffer):
        """Klick im 3D: Teil an der Stelle z (Länge ab Materialanfang) in allen Ansichten wählen."""
        pk = (treffer or {}).get("punkt")
        if not pk or self.abw.daten is None:
            return
        z = pk[2]
        i = next((n for n, t in enumerate(self.abw.daten["teile"]) if t["von"] - 0.5 <= z <= t["bis"] + 0.5), None)
        if i is not None:
            self.abwicklung_teil(i)
            self.hinweis.setText(self.abw.teil_text(i).replace("<br>", " · ").replace("<b>", "").replace("</b>", ""))

    def _drei_d_einpassen(self):
        """3D auf das gewählte Teil (sonst die ersten 1,5 m) einpassen; mit „Ganze Stange“ die ganze Stange."""
        a = self.drei_d.ansicht
        if a.modell is None:
            return
        if self.k_ganz.isChecked():
            a.einpassen()
            return
        i = self.abw.auswahl
        info = self.drei_d_info
        if i is not None and 0 <= i < len(info) and info[i].get("ecken"):
            a.einpassen_auf(info[i]["ecken"], 0.7)
            return
        ecken = [e for x in info if x.get("ecken") and x["ecken"][0][2] < 1500 for e in x["ecken"]]
        a.einpassen_auf(ecken, 0.85) if ecken else a.einpassen()

    def _vorschau(self, t, p):
        """Kleine 3D-Vorschau des gewählten Teils im Infopanel (Netz wie im 3D der Stange, ohne Lage)."""
        netz = None
        if p and self.profil_von is not None:
            profil = self.profil_von(p)
            schl = ("vorschau", t.get("position_id"), t["laenge"])
            if schl not in self._merker3d:
                n = None
                try:
                    roh = self.netz_von(p) if self.netz_von else None
                    if roh is not None:
                        from .ansicht3d import entpacken
                        roh = roh if isinstance(roh, dict) else entpacken(bytes(roh))
                        if na.netz_passt(roh, t["laenge"], profil)[0]:
                            n = roh
                    if n is None and profil:
                        from . import rohr3d, schneidweg as sw_mod
                        e = sw_mod.aus_position(sw_mod.lesen(p.get("technik")), p, profil)[0]
                        n = rohr3d.netz(e, profil, float(t["laenge"]))
                except Exception:       # noqa: BLE001 – Vorschau ist nur Anzeige
                    n = None
                self._merker3d[schl] = n
            netz = self._merker3d[schl]
        self.teil_vorschau.setzen(netz, "")
        self.teil_vorschau.einpassen()

    def abwicklung_speichern(self, art, pfad=None):
        """Abwicklung der gewählten Stange als PDF (Zeichnung der technischen Ansicht, A4 quer) oder DXF."""
        d = self.tech.daten or self.abw.daten
        if d is None:
            return None
        i = self._stange_nr()
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Abwicklung speichern", f"Stange_{(i or 0) + 1}.{art}",
                                                  "PDF (*.pdf)" if art == "pdf" else "DXF (*.dxf)")
            if not pfad:
                return None
        if art == "dxf":
            from . import abwicklung as aw, dxf
            dxf.speichern(pfad, na.dxf_elemente(d), dxf.layer_namen(aw.ROHR_LAYER))
        else:
            from PySide6.QtCore import QMarginsF, QSize as _QSize
            from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter
            w = QPdfWriter(pfad)
            w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape, QMarginsF(10, 10, 10, 10)))
            w.setResolution(150)
            zeichnung = AbwicklungAnsicht(technisch=True)
            zeichnung.ebenen = dict(self.tech.ebenen)
            zeichnung.eins_zu_eins = self.tech.eins_zu_eins
            zeichnung.setzen(d, {r: f.name() for r, f in self.bild.farben.items()}, self.tech.rest_ok)
            zeichnung.resize(_QSize(1600, 1100))
            from PySide6.QtCore import QPoint
            p = QPainter(w)
            try:
                k = min(w.width() / 1600, w.height() / 1100)
                p.scale(k, k)
                zeichnung.render(p, QPoint(0, 0))
            finally:
                p.end()
        self.hinweis.setText(f"Abwicklung gespeichert: {pfad}")
        return pfad

    def teil_im_3d(self, i):
        self.k_ganz.setChecked(False)
        self.abw.auswahl = self.tech.auswahl = i
        self.ansicht_setzen(DREI_D)
        self.hinweis.setText(f"Teil {i + 1} der Stange im 3D (Farbe wie in der Abwicklung).")

    def zur_position(self, ref):
        """Rechtsklick „Zur Position“: Zeile der Position in „Bauteile“ wählen."""
        zeile = next((n for n, p in enumerate(self.positionen) if rechnen.schluessel(p, n) == ref), None)
        if zeile is None:
            return
        r = next((n for n, z_ in enumerate(getattr(self, "_teile_zeilen", [])) if z_ - rechnen.ZEILE0 == zeile), None)
        if r is not None:
            self.links.setCurrentWidget(self.teile_tabelle)
            self.teile_tabelle.selectRow(r)

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
            self.stangen_liste.scrollToItem(self.stangen_liste.item(i))

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
        self._abw_cache.clear()
        self._stangen_liste_fuellen()
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
        self._abw_cache.clear()     # Stangen geändert (Strategie, Ziehen, Auflösen): Abwicklung neu, Teil-Merker bleiben
        self._stangen_liste_fuellen()
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
        if self.uebrig:                         # unvollständiger Plan: keine Einsparung ausweisen
            k["ersparnis"].setText(f"— ({len(self.uebrig)} Teile nicht eingeplant)")
        elif basis is not None:
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
        self.links.setCurrentIndex(self.links.count() - 1)

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
