"""Stangen-Übersicht, Stangen-Detail und Abwicklung der Stange (Ideen aus Lantek Flex3d, Patrick 24.10.2026 „Alle a“):

- StangenUebersicht (L1): je Stange eine dünne Zeile, nach Abmessung gruppiert mit Kopfzeile; gleiche Stangen werden
  nicht zusammengefasst (F3a), damit man die echte Anzahl sieht.
- StangenDetail (L2): eine Stange groß mit Kennzahlen und den Teilen als Kacheln, darunter die Abwicklung der ganzen
  Stange (L4, AbwicklungBild).
- StangenSeite: Umschalter Stangenmuster / Übersicht / Detail (F2a) für den Reiter Stangenbild und das
  Abmessungs-Fenster. Klick auf eine Zeile der Übersicht zeigt diese Stange im Detail. Standard ist die Übersicht;
  bleibt die Maus 1 Sekunde auf einer Stange, zeigt ein kleines Fenster ihre Detail-Ansicht, Esc schließt es (Patrick
  26.10.2026, StangenPopup).

Farben je Position wie im Stangenbild (stil.TEIL_FARBEN), Rest grau, Greiferrest rot, gewählte Stange im Akzent,
hervorgehobenes Teil orange. Die Abwicklung rechnet stangen_abwicklung.py.
"""
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QToolTip, QVBoxLayout, QWidget)

from . import abmessung, rechnen, stil, stangen_abwicklung as sa
from .stammdaten import zahl_als_text

MUSTER, UEBERSICHT, DETAIL = "Stangenmuster", "Übersicht", "Detail"
ANSICHTEN = (MUSTER, UEBERSICHT, DETAIL)
TIPPS = {MUSTER: "Gleich belegte Stangen zusammengefasst, mit Naht, Drehung und Gehrungen",
         UEBERSICHT: "Jede Stange eine dünne Zeile, nach Abmessung gruppiert – Klick: Stange im Detail",
         DETAIL: "Eine Stange groß mit Kennzahlen, Teilen als Kacheln und der Abwicklung der ganzen Stange"}


def _z(w, stellen=2):
    return "" if w is None else zahl_als_text(w, stellen)


def teil_farben(stangen):
    """{ref: Farbe} je Position in der Reihenfolge des ersten Auftretens (wie das Stangenbild)."""
    out = {}
    for s in stangen:
        for t in s["teile"]:
            if t["ref"] not in out:
                out[t["ref"]] = stil.TEIL_FARBEN[len(out) % len(stil.TEIL_FARBEN)]
    return out


def pos_text(t):
    return str(t["pos"]) if t.get("pos") is not None else (t.get("artikel") or "")


def kennwerte(s, w=None):
    """Kennzahlen einer Stange: teile, summe, rest (= Verschnitt), nutzung, gewicht, kosten, gemeinsam."""
    summe = sum(t["laenge"] for t in s["teile"])
    rest = s["stange"] - s["end"] - summe - s["verlust"]
    w = w or {}
    return dict(teile=len(s["teile"]), summe=summe, rest=w.get("rest", rest),
                nutzung=summe / s["stange"] if s["stange"] else 0, gewicht=w.get("gewicht"), kosten=w.get("kosten"),
                gemeinsam=sum(1 for t in s["teile"] if t.get("trennung") == "gemeinsamer Schnitt"))


def gruppen(stangen):
    """Stangen nach Abmessung, Reihenfolge wie im Schnittplan: [(Kopftext, [Stange])]."""
    out = {}
    for s in stangen:
        out.setdefault(abmessung.gruppe_der_stange(s), []).append(s)
    liste = []
    for st in out.values():
        s = st[0]
        laengen = sorted({x["stange"] for x in st})
        summe = sum(t["laenge"] for x in st for t in x["teile"])
        gesamt = sum(x["stange"] for x in st)
        kopf = (f"{s['profil']} · {rechnen.material_text(s['werkstoff'], s.get('oberflaeche'))} · "
                f"{' / '.join(_z(x, 0) for x in laengen)} mm · {len(st)} {'Stange' if len(st) == 1 else 'Stangen'}"
                f" · Ausnutzung {_z(100 * summe / gesamt, 1) if gesamt else '–'} %"
                + (" · Kundenmaterial" if s.get("beistellung") else ""))
        liste.append((kopf, st))
    return liste


def _tipp_teil(s, t):
    zeilen = [f"Stange {s['nr']} · Pos. {pos_text(t)} · {_z(t['laenge'], 1)} mm"]
    _, text = rechnen.teil_zeichen(t)
    if text:
        zeilen.append(text)
    if t.get("trennung"):
        zeilen.append(f"Zum Vorgänger: {t['trennung']}")
    zeilen.append("Doppelklick: zur Position")
    return "\n".join(zeilen)


def _tipp_stange(s):
    k = kennwerte(s)
    return (f"Stange {s['nr']}: {k['teile']} Teile · Rest {_z(k['rest'], 1)} mm · Nutzung {_z(100 * k['nutzung'], 1)} %"
            "\nKlick: Stange im Detail")


def _punkt(ereignis):
    return ereignis.position() if hasattr(ereignis, "position") else QPointF(ereignis.pos())


# ---------------------------------------------------------------------------------------------- Übersicht (L1)
class StangenUebersicht(QWidget):
    """Je Stange eine dünne Zeile (F3a), gruppiert nach Abmessung. Signale: gewaehlt(Nummer der Stange; Klick oder
    Eingabetaste), vorgewaehlt(Nummer; Pfeiltasten), klick(ref), doppelklick(ref)."""
    ZEILE, KOPF, LINKS, RECHTS = 16, 24, 44, 52
    WARTEN_MS = 1000        # so lange auf einer Stange, dann das Fenster mit den Stangendetails (StangenPopup);
                            # warten() = Sekunden aus der Einstellung stangenbild_popup (0 = aus), None = WARTEN_MS
    gewaehlt = Signal(int)
    vorgewaehlt = Signal(int)
    klick = Signal(str)
    doppelklick = Signal(str)

    def __init__(self):
        super().__init__()
        self.zeilen = []            # [(art 'kopf'/'stange', y, Text bzw. Stange)]
        self.farben, self.flaechen, self.stangen_y = {}, [], {}
        self.gewaehlt_nr, self.markiert = None, None
        self.werte = {}             # {Nummer: Werte der Stange} für Gewicht und Kosten im Popup
        self.detail_daten = None    # nr -> Daten der Detail-Ansicht (StangenSeite, mit Abwicklung)
        self.warten = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setToolTip("Klick: Stange im Detail · Doppelklick auf ein Teil: zur Position · Pfeiltasten: blättern · "
                        "Maus 1 Sekunde auf einer Stange: Details (Esc schließt)")
        self.popup = StangenPopup(self)
        self.popup.daten = self._popup_daten
        self.popup.doppelklick.connect(self.doppelklick)
        self.uhr = QTimer(self)
        self.uhr.setSingleShot(True)
        self.uhr.setInterval(self.WARTEN_MS)
        self.uhr.timeout.connect(self.popup_zeigen)
        self._ueber, self._maus = None, QPoint()

    def setzen(self, stangen, farben=None, werte=None):
        self.popup_schliessen()
        self.werte = werte or {}
        self.farben = {r: QColor(f) for r, f in (farben or teil_farben(stangen)).items()}
        self.laenge = max((s["stange"] for s in stangen), default=1) or 1
        self.zeilen, self.stangen_y, y = [], {}, 6
        for kopf, st in gruppen(stangen):
            self.zeilen.append(("kopf", y, kopf))
            y += self.KOPF
            for s in st:
                self.zeilen.append(("stange", y, s))
                self.stangen_y[s["nr"]] = y
                y += self.ZEILE
            y += 4
        if self.gewaehlt_nr not in self.stangen_y:
            self.gewaehlt_nr = None
        self.setMinimumHeight(max(60, y + 6))
        self.update()

    def nummern(self):
        return [z[2]["nr"] for z in self.zeilen if z[0] == "stange"]

    def waehlen(self, nr):
        self.gewaehlt_nr = nr
        self.update()

    def markieren(self, ref):
        self.markiert = ref
        self.update()

    def _bei(self, punkt):
        """(Stange, Teil oder None) an der Stelle punkt, sonst (None, None)."""
        for r, t, s in self.flaechen:
            if r.contains(punkt):
                return s, t
        for art, y, x in self.zeilen:
            if art == "stange" and y <= punkt.y() < y + self.ZEILE:
                return x, None
        return None, None

    def mousePressEvent(self, ereignis):
        s, t = self._bei(_punkt(ereignis))
        if t is not None:
            self.klick.emit(t["ref"])
        if s is not None:
            self.waehlen(s["nr"])
            self.gewaehlt.emit(s["nr"])
        super().mousePressEvent(ereignis)

    def mouseDoubleClickEvent(self, ereignis):
        _, t = self._bei(_punkt(ereignis))
        if t is not None:
            self.doppelklick.emit(t["ref"])

    def mouseMoveEvent(self, ereignis):
        """Maus auf einer Stange: nach WARTEN_MS das Fenster mit den Stangendetails; auf einer anderen Stange neu."""
        s, _ = self._bei(_punkt(ereignis))
        nr = s["nr"] if s is not None else None
        self._maus = _punkt(ereignis).toPoint()
        if nr != self._ueber:
            self._ueber = nr
            self.uhr.stop()
            ms = self.wartezeit()
            if nr is not None and ms > 0 and not (self.popup.isVisible() and self.popup.nr == nr):
                self.uhr.start(ms)
        super().mouseMoveEvent(ereignis)

    def wartezeit(self):
        """Millisekunden bis zum Detail-Fenster (0 = aus); ohne oder mit ungültiger Einstellung WARTEN_MS."""
        try:
            w = self.warten() if self.warten is not None else None
            return self.WARTEN_MS if w is None or w == "" else max(0, int(round(1000 * float(w))))
        except (TypeError, ValueError):
            return self.WARTEN_MS

    def leaveEvent(self, ereignis):
        self._ueber = None
        self.uhr.stop()
        super().leaveEvent(ereignis)

    def hideEvent(self, ereignis):
        self.popup_schliessen()
        super().hideEvent(ereignis)

    def _popup_daten(self, nr):
        """Daten für die Detail-Ansicht im Popup; StangenSeite setzt dafür detail_daten (mit Abwicklung)."""
        if self.detail_daten is not None:
            return self.detail_daten(nr)
        s = next((z[2] for z in self.zeilen if z[0] == "stange" and z[2]["nr"] == nr), None)
        if s is None:
            return None
        return s, self.werte.get(nr), {r: f.name() for r, f in self.farben.items()}, self.nummern(), [nr], None

    def popup_zeigen(self, nr=None):
        """Detail-Ansicht der Stange nr (ohne Angabe: unter der Maus) als kleines Fenster neben der Maus zeigen."""
        nr = self._ueber if nr is None else nr
        if nr not in self.stangen_y:
            return None
        y = self.stangen_y[nr]
        wo = self.mapToGlobal(QPoint(max(self._maus.x(), self.LINKS) + 16, y + self.ZEILE + 4))
        QToolTip.hideText()
        self.setFocus()             # Esc kommt hier an (keyPressEvent)
        return self.popup.zeigen(nr, wo)

    def popup_schliessen(self):
        self.uhr.stop()
        self.popup.hide()
        self.popup.nr = None

    def keyPressEvent(self, ereignis):
        if ereignis.key() == Qt.Key_Escape and self.popup.isVisible():
            self.popup_schliessen()
            return
        nr = self.nummern()
        if ereignis.key() in (Qt.Key_Up, Qt.Key_Down) and nr:
            i = nr.index(self.gewaehlt_nr) if self.gewaehlt_nr in nr else -1
            i = max(0, min(len(nr) - 1, i + (1 if ereignis.key() == Qt.Key_Down else -1)))
            self.waehlen(nr[i])
            self.vorgewaehlt.emit(nr[i])
            return
        if ereignis.key() in (Qt.Key_Return, Qt.Key_Enter) and self.gewaehlt_nr is not None:
            self.gewaehlt.emit(self.gewaehlt_nr)
            return
        super().keyPressEvent(ereignis)

    def event(self, ereignis):
        if ereignis.type() == QEvent.ToolTip:
            s, t = self._bei(QPointF(ereignis.pos()))
            if s is not None and (self.uhr.isActive() or self.popup.isVisible()):
                return True             # auf einer Stange gilt das Fenster mit den Details
            text = _tipp_teil(s, t) if t is not None else _tipp_stange(s) if s is not None else self.toolTip()
            QToolTip.showText(ereignis.globalPos(), text, self)
            return True
        return super().event(ereignis)

    def paintEvent(self, _):
        p = QPainter(self)
        if not self.zeilen:
            p.drawText(self.rect(), Qt.AlignCenter, "Noch nicht optimiert.")
            return
        x0 = self.LINKS
        breite = max(100, self.width() - self.LINKS - self.RECHTS)
        m = breite / self.laenge
        klein = QFont(self.font())
        klein.setPointSizeF(max(7.0, klein.pointSizeF() - 1.5))
        fett = QFont(self.font())
        fett.setBold(True)
        self.flaechen = []
        rand = stil.farbe("#5F6B7A")
        for art, y, x in self.zeilen:
            if art == "kopf":
                p.setFont(fett)
                p.setPen(stil.farbe(stil.AKZENT))
                p.drawText(QRectF(6, y, self.width() - 12, self.KOPF - 4), Qt.AlignLeft | Qt.AlignBottom, x)
                p.setPen(QPen(stil.farbe(stil.RAHMEN), 1))
                p.drawLine(QPointF(6, y + self.KOPF - 2), QPointF(self.width() - 6, y + self.KOPF - 2))
                continue
            s = x
            yb, hb = y + 2, self.ZEILE - 4
            if s["nr"] == self.gewaehlt_nr:
                p.fillRect(QRectF(0, y, self.width(), self.ZEILE), stil.farbe(stil.BLAU_FLAECHE))
            p.setFont(klein)
            p.setPen(stil.farbe(stil.TEXT))
            p.drawText(QRectF(2, y, self.LINKS - 8, self.ZEILE), Qt.AlignRight | Qt.AlignVCenter, str(s["nr"]))
            k = kennwerte(s)
            p.setPen(stil.farbe(stil.TEXT_GRAU))
            p.drawText(QRectF(x0 + breite + 4, y, self.RECHTS - 6, self.ZEILE), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{_z(100 * k['nutzung'], 0)} %")

            def balken(von, bis, farbe):
                r = QRectF(x0 + von * m, yb, max(1.0, (bis - von) * m), hb)
                p.fillRect(r, farbe)
                return r
            ganz = balken(0, s["stange"], stil.farbe("#EDEDED"))
            balken(0, s["end"], stil.farbe("#A6A6A6"))
            balken(s["stange"] - s["greif"], s["stange"], stil.farbe("#E06666"))
            for t in s["teile"]:
                r = balken(t["von"], t["bis"], self.farben.get(t["ref"], stil.farbe("#4E79A7")))
                p.setPen(QPen(stil.farbe("#202020"), 1))
                p.drawLine(r.topLeft(), r.bottomLeft())
                p.drawLine(r.topRight(), r.bottomRight())
                if self.markiert is not None and t["ref"] == self.markiert:
                    p.setPen(QPen(stil.farbe(stil.ORANGE), 2))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(r.adjusted(0, -1, 0, 1))
                self.flaechen.append((r, t, s))
            p.setBrush(Qt.NoBrush)
            if s["nr"] == self.gewaehlt_nr:
                p.setPen(QPen(stil.farbe(stil.AKZENT), 2))
                p.drawRect(ganz.adjusted(-1, -1, 1, 1))
            else:
                p.setPen(QPen(rand, 1))
                p.drawRect(ganz)
        p.end()


# ---------------------------------------------------------------------------------------------- Kacheln (L2)
class Kacheln(QWidget):
    """Die Teile einer Stange als Kacheln in Positionsfarbe: Platz, Pos., Länge, Artikel, Naht/Drehung bzw. Trennung.
    Klick hebt hervor (klick), Doppelklick: zur Position (doppelklick)."""
    B, H, ABSTAND = 172, 54, 6
    klick = Signal(str)
    doppelklick = Signal(str)

    def __init__(self):
        super().__init__()
        self.teile, self.farben, self.flaechen, self.markiert = [], {}, [], None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("Klick: Teil hervorheben · Doppelklick: zur Position")

    def setzen(self, teile, farben):
        self.teile, self.farben = list(teile), {r: QColor(f) for r, f in farben.items()}
        self._hoehe()
        self.update()

    def markieren(self, ref):
        self.markiert = ref
        self.update()

    def _je_zeile(self, breite):
        return max(1, int((breite + self.ABSTAND) // (self.B + self.ABSTAND)))

    def hoehe_fuer(self, breite):
        n = len(self.teile)
        zeilen = -(-n // self._je_zeile(breite)) if n else 0
        return max(20, zeilen * (self.H + self.ABSTAND))

    def _hoehe(self):
        self.setMinimumHeight(self.hoehe_fuer(max(self.width(), self.B)))

    def resizeEvent(self, ereignis):
        self._hoehe()
        super().resizeEvent(ereignis)

    def _bei(self, punkt):
        return next((t for r, t in self.flaechen if r.contains(punkt)), None)

    def mousePressEvent(self, ereignis):
        t = self._bei(_punkt(ereignis))
        if t is not None:
            self.markieren(t["ref"])
            self.klick.emit(t["ref"])
        super().mousePressEvent(ereignis)

    def mouseDoubleClickEvent(self, ereignis):
        t = self._bei(_punkt(ereignis))
        if t is not None:
            self.doppelklick.emit(t["ref"])

    def paintEvent(self, _):
        p = QPainter(self)
        if not self.teile:
            p.setPen(stil.farbe(stil.TEXT_GRAU))
            p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, "Keine Teile auf dieser Stange.")
            return
        p.setRenderHint(QPainter.Antialiasing, True)
        n = self._je_zeile(self.width())
        klein = QFont(self.font())
        klein.setPointSizeF(max(7.0, klein.pointSizeF() - 1.5))
        fett = QFont(self.font())
        fett.setBold(True)
        self.flaechen = []
        for i, t in enumerate(self.teile):
            r = QRectF((i % n) * (self.B + self.ABSTAND) + 1, (i // n) * (self.H + self.ABSTAND) + 1, self.B, self.H)
            farbe = self.farben.get(t["ref"], stil.farbe("#4E79A7"))
            weg = QPainterPath()
            weg.addRoundedRect(r, 4, 4)
            p.fillPath(weg, stil.farbe(stil.FLAECHE))
            p.save()
            p.setClipPath(weg)
            p.fillRect(QRectF(r.left(), r.top(), 7, r.height()), farbe)
            p.restore()
            wahl = self.markiert is not None and t["ref"] == self.markiert
            p.setPen(QPen(stil.farbe(stil.ORANGE), 2.5) if wahl else QPen(stil.farbe(stil.RAHMEN), 1))
            p.drawPath(weg)
            innen = r.adjusted(12, 3, -6, -3)
            p.setFont(fett)
            p.setPen(stil.farbe(stil.TEXT))
            p.drawText(innen, Qt.AlignLeft | Qt.AlignTop, f"Pos. {pos_text(t)} · {_z(t['laenge'], 1)} mm")
            p.setFont(klein)
            p.setPen(stil.farbe(stil.TEXT_GRAU))
            p.drawText(innen, Qt.AlignRight | Qt.AlignTop, f"{i + 1}.")
            unten = rechnen.teil_zeichen(t)[1] or t.get("trennung") or ""
            p.drawText(innen, Qt.AlignLeft | Qt.AlignVCenter, p.fontMetrics().elidedText(
                str(t.get("artikel") or ""), Qt.ElideRight, int(innen.width())))
            p.drawText(innen, Qt.AlignLeft | Qt.AlignBottom, p.fontMetrics().elidedText(
                unten, Qt.ElideRight, int(innen.width())))
            self.flaechen.append((r, t))
        p.end()


# ---------------------------------------------------------------------------------------------- Abwicklung (L4)
class AbwicklungBild(QWidget):
    """Abwicklung der ganzen Stange (stangen_abwicklung.stange): Mantel als Band (Umfang quer, gestreckt auf eine
    feste Höhe), jedes Teil mit seinen Schnittkanten in Positionsfarbe, Konturen rot, Gravur grün, Schweißnaht der
    Stange rot strichpunktiert (SN). Klick: Teil hervorheben, Doppelklick: zur Position."""
    LINKS, RECHTS, OBEN, BAND = 58, 14, 18, 120
    klick = Signal(str)
    doppelklick = Signal(str)

    def __init__(self):
        super().__init__()
        self.daten, self.farben, self.flaechen, self.markiert = None, {}, [], None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self.OBEN + self.BAND + 26)
        self.setToolTip("Abwicklung der Stange: oben = Fläche oben, dann vorne, unten, hinten (Blick von Ende A). "
                        "Klick: Teil hervorheben · Doppelklick: zur Position")

    def setzen(self, daten, farben):
        self.daten, self.farben = daten, {r: QColor(f) for r, f in farben.items()}
        self.update()

    def markieren(self, ref):
        self.markiert = ref
        self.update()

    def _bei(self, punkt):
        return next((t for poly, t in self.flaechen if poly.containsPoint(punkt, Qt.OddEvenFill)), None)

    def mousePressEvent(self, ereignis):
        t = self._bei(_punkt(ereignis))
        if t is not None:
            self.markieren(t["ref"])
            self.klick.emit(t["ref"])
        super().mousePressEvent(ereignis)

    def mouseDoubleClickEvent(self, ereignis):
        t = self._bei(_punkt(ereignis))
        if t is not None:
            self.doppelklick.emit(t["ref"])

    def paintEvent(self, _):
        p = QPainter(self)
        d = self.daten
        if not d:
            p.setPen(stil.farbe(stil.TEXT_GRAU))
            p.drawText(self.rect(), Qt.AlignCenter, "Abwicklung nicht möglich (Profil ohne Querschnitt).")
            return
        breite = max(100, self.width() - self.LINKS - self.RECHTS)
        mx, my = breite / (d["laenge"] or 1), self.BAND / (d["umfang"] or 1)
        x0, y0 = self.LINKS, self.OBEN

        def pkt(x, s):
            return QPointF(x0 + x * mx, y0 + s * my)
        band = QRectF(x0, y0, breite, self.BAND)
        klein = QFont(self.font())
        klein.setPointSizeF(max(7.0, klein.pointSizeF() - 1.5))
        p.setFont(klein)
        p.fillRect(band, stil.farbe("#EDEDED"))
        p.fillRect(QRectF(x0, y0, d["end"] * mx, self.BAND), stil.farbe("#A6A6A6"))
        p.fillRect(QRectF(x0 + (d["laenge"] - d["greif"]) * mx, y0, d["greif"] * mx, self.BAND), stil.farbe("#E06666"))
        p.setRenderHint(QPainter.Antialiasing, True)
        self.flaechen = []
        for t in d["teile"]:
            poly = QPolygonF([pkt(x, s) for x, s in t["umriss"]])
            farbe = QColor(self.farben.get(t["ref"], stil.farbe("#4E79A7")))
            flaeche = QColor(farbe)
            flaeche.setAlpha(120)
            p.setBrush(flaeche)
            wahl = self.markiert is not None and t["ref"] == self.markiert
            p.setPen(QPen(stil.farbe(stil.ORANGE), 2.5) if wahl else QPen(stil.farbe("#202020"), 1.2))
            p.drawPolygon(poly)
            self.flaechen.append((poly, t))
        p.setBrush(Qt.NoBrush)
        p.save()
        p.setClipRect(band)
        for t in d["teile"]:
            for k in t["konturen"]:
                farbe = stil.farbe("#2E7D32") if k["gravur"] else stil.farbe("#B42318")
                p.setPen(QPen(farbe, 1.2, Qt.DashLine if k["verteilt"] else Qt.SolidLine))
                for stueck in sa.kontur_teile(k["punkte"], d["umfang"]):
                    poly = QPolygonF([pkt(x, s) for x, s in stueck])
                    r = poly.boundingRect()
                    if r.width() < 3 and r.height() < 3:
                        p.drawEllipse(r.center(), 1.8, 1.8)
                    elif k["gravur"]:
                        p.drawPolyline(poly)
                    else:
                        p.drawPolygon(poly)
        p.restore()
        p.setRenderHint(QPainter.Antialiasing, False)
        for i, (name, s0, s1) in enumerate(d["streifen"]):
            if i:
                p.setPen(QPen(stil.farbe("#7F7F7F"), 0.8, Qt.DashLine))
                p.drawLine(pkt(0, s0), pkt(d["laenge"], s0))
            p.setPen(stil.farbe(stil.TEXT_GRAU))
            p.drawText(QRectF(2, y0 + s0 * my, self.LINKS - 8, (s1 - s0) * my), Qt.AlignRight | Qt.AlignVCenter, name)
        if d["naht"] is not None:
            p.setPen(QPen(stil.farbe("#D0021B"), 1.6, Qt.DashDotLine))
            p.drawLine(pkt(0, d["naht"]), pkt(d["laenge"], d["naht"]))
            p.drawText(QRectF(x0 + 4, y0 + d["naht"] * my - 14, 40, 13), Qt.AlignLeft | Qt.AlignVCenter, "SN")
        p.setPen(QPen(stil.farbe("#5F6B7A"), 1))
        p.drawRect(band)
        p.setPen(stil.farbe(stil.TEXT_GRAU))
        p.drawText(QRectF(x0, 0, breite, self.OBEN - 2), Qt.AlignLeft | Qt.AlignVCenter,
                   f"Ende A · Umfang {_z(d['umfang'], 1)} mm (quer gestreckt)")
        p.drawText(QRectF(x0, 0, breite, self.OBEN - 2), Qt.AlignRight | Qt.AlignVCenter, f"{_z(d['laenge'], 0)} mm")
        if d["fehlt"]:
            p.setPen(stil.farbe(stil.ROT))
            p.drawText(QRectF(x0, y0 + self.BAND + 2, breite, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       "Ohne Daten (nicht gezeichnet): Pos. " + ", ".join(str(x) for x in d["fehlt"]))
        p.end()


# ---------------------------------------------------------------------------------------------- Detail (L2)
class StangenDetail(QWidget):
    """Eine Stange groß: Kopf mit Blättern, Kennzahlen, Stangenbild, Teile als Kacheln und Abwicklung.
    Signale: klick(ref), doppelklick(ref), blaettern(Nummer der Stange)."""
    klick = Signal(str)
    doppelklick = Signal(str)
    blaettern = Signal(int)

    def __init__(self):
        super().__init__()
        from .angebot_fenster import Stangenbild
        self.s, self.nummern = None, []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        kopf = QHBoxLayout()
        self.k_zurueck = QPushButton("◀")
        self.k_zurueck.setToolTip("Vorige Stange")
        self.k_zurueck.clicked.connect(lambda: self._blaettern(-1))
        self.k_vor = QPushButton("▶")
        self.k_vor.setToolTip("Nächste Stange")
        self.k_vor.clicked.connect(lambda: self._blaettern(1))
        for k_ in (self.k_zurueck, self.k_vor):
            k_.setFixedWidth(34)
        self.titel = QLabel()
        self.titel.setTextFormat(Qt.RichText)
        kopf.addWidget(self.k_zurueck)
        kopf.addWidget(self.titel, 1)
        kopf.addWidget(self.k_vor)
        lay.addLayout(kopf)
        self.werte = QLabel()
        self.werte.setTextFormat(Qt.RichText)
        self.werte.setWordWrap(True)
        lay.addWidget(self.werte)
        self.bild = Stangenbild()
        self.bild.klick.connect(self._teil)
        self.bild.doppelklick.connect(self.doppelklick)
        lay.addWidget(self.bild)
        lay.addWidget(self._ueberschrift("Teile auf der Stange"))
        self.kacheln = Kacheln()
        self.kacheln.klick.connect(self._teil)
        self.kacheln.doppelklick.connect(self.doppelklick)
        lay.addWidget(self.kacheln)
        lay.addWidget(self._ueberschrift("Abwicklung der Stange"))
        self.abwicklung = AbwicklungBild()
        self.abwicklung.klick.connect(self._teil)
        self.abwicklung.doppelklick.connect(self.doppelklick)
        lay.addWidget(self.abwicklung)
        lay.addStretch(1)

    @staticmethod
    def _ueberschrift(text):
        z = QLabel(f"<b>{text}</b>")
        z.setStyleSheet(f"color: {stil.AKZENT}; margin-top: 6px;")
        return z

    def setzen(self, s, w, farben, nummern, gleich=(), abwicklung=None):
        """s = Stange (oder None), w = Werte aus stangen_werte, nummern = alle Stangennummern (Blättern), gleich =
        Nummern der gleich belegten Stangen, abwicklung = stangen_abwicklung.stange(s, …)."""
        self.s, self.nummern = s, list(nummern)
        if s is None:
            self.titel.setText("<b>Keine Stange gewählt</b>")
            self.werte.setText("")
            self.bild.setzen(None, {})
            self.kacheln.setzen([], {})
            self.abwicklung.setzen(None, {})
            self.k_zurueck.setEnabled(False)
            self.k_vor.setEnabled(False)
            return
        i = self.nummern.index(s["nr"]) if s["nr"] in self.nummern else 0
        andere = [n for n in gleich if n != s["nr"]]
        self.titel.setText(f"<b>Stange {s['nr']}</b> ({i + 1} von {len(self.nummern)}) · {s['profil']} · "
                           f"{rechnen.material_text(s['werkstoff'], s.get('oberflaeche'))}"
                           + (f" · gleich belegt wie {abmessung.nummern_text(andere)}" if andere else ""))
        k = kennwerte(s, w)
        teile = [f"Lieferlänge <b>{_z(s['stange'], 0)} mm</b>", f"Teile <b>{k['teile']}</b>",
                 f"Nutzung <b>{_z(100 * k['nutzung'], 1)} %</b>", f"Rest (Verschnitt) {_z(k['rest'], 1)} mm",
                 f"Endbeschnitt {_z(s['end'], 1)} mm", f"Greiferrest {_z(s['greif'], 1)} mm"]
        if k["gewicht"] is not None:
            teile.append(f"Gewicht {_z(k['gewicht'], 1)} kg")
        if k["kosten"] is not None:
            teile.append("Kundenmaterial" if s.get("beistellung") else f"Material {_z(k['kosten'])} €")
        teile.append(f"gemeinsame Schnitte {k['gemeinsam']}")
        if rechnen.gehrung_gespart(s) > 0:
            teile.append(f"Gehrungen ineinander {_z(rechnen.gehrung_gespart(s), 1)} mm gespart")
        self.werte.setText(" · ".join(teile))
        self.bild.setzen(dict(stangen=[s]), farben)
        self.kacheln.setzen(s["teile"], farben)
        self.abwicklung.setzen(abwicklung, farben)
        self.k_zurueck.setEnabled(i > 0)
        self.k_vor.setEnabled(i < len(self.nummern) - 1)

    def markieren(self, ref):
        for w in (self.bild, self.kacheln, self.abwicklung):
            w.markieren(ref)

    def _teil(self, ref):
        self.markieren(ref)
        self.klick.emit(ref)

    def _blaettern(self, schritt):
        if self.s is None or self.s["nr"] not in self.nummern:
            return
        i = self.nummern.index(self.s["nr"]) + schritt
        if 0 <= i < len(self.nummern):
            self.blaettern.emit(self.nummern[i])


# ---------------------------------------------------------------------------------------------- Seite (F2a)
class StangenPopup(QFrame):
    """Kleines Fenster mit der Detail-Ansicht einer Stange (Übersicht, Maus 1 Sekunde auf der Stange; Patrick
    26.10.2026 „das meinte ich als Detail“): Kennzahlen, Stangenbild, Teile als Kacheln und Abwicklung wie die Ansicht
    Detail, mit eigenem Blättern. Esc schließt. Signal doppelklick(ref)."""
    BREITE, HOEHE = 760, 560
    doppelklick = Signal(str)

    def __init__(self, parent):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(f"StangenPopup {{ background: #FFFFFF; border: 1px solid {stil.AKZENT}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        self.detail = StangenDetail()
        self.detail.doppelklick.connect(self.doppelklick)
        self.detail.blaettern.connect(lambda nr: self.zeigen(nr))
        rolle = QScrollArea()
        rolle.setWidgetResizable(True)
        rolle.setFrameShape(QFrame.NoFrame)
        rolle.setWidget(self.detail)
        lay.addWidget(rolle, 1)
        hinweis = QLabel("Esc: schließen · Klick in der Übersicht: Stange in der Ansicht Detail")
        hinweis.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        lay.addWidget(hinweis)
        self.resize(self.BREITE, self.HOEHE)
        self.nr, self.daten = None, None

    def zeigen(self, nr, wo=None):
        """Stange nr zeigen; daten(nr) = (Stange, Werte, Farben, alle Nummern, gleich belegte, Abwicklung)."""
        d = self.daten(nr) if self.daten else None
        if d is None:
            return None
        self.nr = nr
        self.detail.setzen(*d)
        if wo is not None:
            bild = self.screen().availableGeometry() if self.screen() else None
            if bild is not None:        # ganz auf dem Bildschirm
                wo = QPoint(max(bild.left(), min(wo.x(), bild.right() - self.width())),
                            max(bild.top(), min(wo.y(), bild.bottom() - self.height())))
            self.move(wo)
        self.show()
        self.raise_()
        return self

    def keyPressEvent(self, ereignis):
        if ereignis.key() == Qt.Key_Escape:
            self.hide()
            self.nr = None
            return
        super().keyPressEvent(ereignis)


class StangenSeite(QWidget):
    """Reiter Stangenbild bzw. Bereich im Abmessungs-Fenster: Umschalter Stangenmuster / Übersicht / Detail.
    ansicht = Start-Ansicht, merken(Ansicht) wird bei jedem Umschalten gerufen. Signale: klick(ref), doppelklick(ref).
    bild = das klassische Stangenbild (Muster), rolle = sein Rollbereich."""
    klick = Signal(str)
    doppelklick = Signal(str)

    def __init__(self, ansicht=UEBERSICHT, merken=None, warten=None):
        super().__init__()
        from .angebot_fenster import Stangenbild
        self.merken = merken
        self.stangen, self.werte, self.farben, self.abw, self.abw_cache = [], {}, {}, None, {}
        self.nr, self.markiert = None, None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        leiste = QHBoxLayout()
        leiste.setSpacing(0)
        self.knoepfe = QButtonGroup(self)
        self.knoepfe.setExclusive(True)
        for name in ANSICHTEN:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setToolTip(TIPPS[name])
            b.clicked.connect(lambda _=False, n=name: self.ansicht_setzen(n))
            self.knoepfe.addButton(b)
            leiste.addWidget(b)
        leiste.addSpacing(12)
        self.info = QLabel()
        self.info.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        leiste.addWidget(self.info, 1)
        lay.addLayout(leiste)
        self.bild = Stangenbild()
        self.bild.klick.connect(self._teil)
        self.bild.doppelklick.connect(self.doppelklick)
        self.uebersicht = StangenUebersicht()
        self.uebersicht.gewaehlt.connect(lambda nr: self.stange_zeigen(nr, ansicht=DETAIL))
        self.uebersicht.vorgewaehlt.connect(lambda nr: (self.stange_zeigen(nr), self._hinscrollen()))
        self.uebersicht.klick.connect(self._teil_merken)
        self.uebersicht.doppelklick.connect(self.doppelklick)
        self.uebersicht.detail_daten = self._detail_daten
        self.uebersicht.warten = warten     # Sekunden bis zum Detail-Fenster (Einstellung stangenbild_popup)
        self.detail = StangenDetail()
        self.detail.klick.connect(self._teil)
        self.detail.doppelklick.connect(self.doppelklick)
        self.detail.blaettern.connect(self.stange_zeigen)
        self.stapel = QStackedWidget()
        self.rollen = {}
        for name, w in ((MUSTER, self.bild), (UEBERSICHT, self.uebersicht), (DETAIL, self.detail)):
            r = QScrollArea()
            r.setWidgetResizable(True)
            r.setWidget(w)
            self.rollen[name] = r
            self.stapel.addWidget(r)
        self.rolle = self.rollen[MUSTER]
        lay.addWidget(self.stapel, 1)
        self.ansicht = None
        self.ansicht_setzen(ansicht if ansicht in ANSICHTEN else UEBERSICHT, melden=False)

    # ------------------------------------------------------------------ Daten
    def setzen(self, paare, abwicklung=None):
        """paare = [(Stange, Werte oder None)] wie rechnen.anzeige_stangen(…, sw); abwicklung(s) = Daten der
        Abwicklung (stangen_abwicklung.stange) oder None."""
        self.stangen = [s for s, _ in paare]
        self.werte = {s["nr"]: w for s, w in paare}
        self.farben = teil_farben(self.stangen)
        self.abw, self.abw_cache = abwicklung, {}
        self.bild.setzen(dict(stangen=self.stangen) if self.stangen else None, self.farben)
        self.uebersicht.setzen(self.stangen, self.farben, self.werte)
        self.info.setText(f"{len(self.stangen)} {'Stange' if len(self.stangen) == 1 else 'Stangen'}"
                          if self.stangen else "")
        nummern = [s["nr"] for s in self.stangen]
        self.stange_zeigen(self.nr if self.nr in nummern else (nummern[0] if nummern else None))
        self.markieren(self.markiert if any(t["ref"] == self.markiert for s in self.stangen for t in s["teile"])
                       else None, springen=False)

    def stange(self, nr):
        return next((s for s in self.stangen if s["nr"] == nr), None)

    def _detail_daten(self, nr):
        """(Stange, Werte, Farben, alle Nummern, gleich belegte, Abwicklung) für die Detail-Ansicht im Popup."""
        s = self.stange(nr)
        if s is None:
            return None
        return s, self.werte.get(nr), self.farben, [x["nr"] for x in self.stangen], self.gleiche(s), self.abwicklung(s)

    def abwicklung(self, s):
        if self.abw is None or s is None:
            return None
        if s["nr"] not in self.abw_cache:
            try:
                self.abw_cache[s["nr"]] = self.abw(s)
            except (ValueError, KeyError, TypeError, ZeroDivisionError):
                self.abw_cache[s["nr"]] = None
        return self.abw_cache[s["nr"]]

    def gleiche(self, s):
        """Nummern der Stangen, die genauso belegt sind wie s (Stangenmuster)."""
        return next((nr for x, nr in self.bild.muster if s["nr"] in nr), [s["nr"]])

    # ------------------------------------------------------------------ Bedienung
    def ansicht_setzen(self, name, melden=True):
        if name not in ANSICHTEN:
            return
        self.ansicht = name
        if name != UEBERSICHT:
            self.uebersicht.popup_schliessen()
        for b in self.knoepfe.buttons():
            b.setChecked(b.text() == name)
        self.stapel.setCurrentWidget(self.rollen[name])
        if name == DETAIL and getattr(self, "_abw_offen", False):
            self.stange_zeigen(self.nr)
        if name == UEBERSICHT and self.nr is not None:
            self._hinscrollen()
        if melden and self.merken:
            self.merken(name)

    def stange_zeigen(self, nr, ansicht=None):
        """Stange nr im Detail zeigen (und in der Übersicht wählen); ansicht = dabei umschalten."""
        self.nr = nr
        s = self.stange(nr)
        self.uebersicht.waehlen(nr if s else None)
        # Abwicklung erst rechnen, wenn das Stangen-Detail zu sehen ist (Performance-Plan P9: bei einem Rohr mit
        # 1.000 Bohrungen kostete sie bei jedem Öffnen des Angebots 2,4 s, auch wenn niemand ins Detail schaute)
        self._abw_offen = self.ansicht != DETAIL
        self.detail.setzen(s, self.werte.get(nr), self.farben, [x["nr"] for x in self.stangen],
                           self.gleiche(s) if s else (), None if self._abw_offen else self.abwicklung(s))
        self.detail.markieren(self.markiert)
        if ansicht:
            self.ansicht_setzen(ansicht)

    def _hinscrollen(self):
        y = self.uebersicht.stangen_y.get(self.nr)
        if y is not None:
            self.rollen[UEBERSICHT].ensureVisible(0, y, 0, self.uebersicht.ZEILE * 3)

    def markieren(self, ref, springen=True):
        """Teil ref überall hervorheben; springen: Detail auf die erste Stange mit dem Teil, Muster hinscrollen."""
        self.markiert = ref
        self.bild.markieren(ref)
        self.uebersicht.markieren(ref)
        if springen and ref is not None and not (self.stange(self.nr) and any(
                t["ref"] == ref for t in self.stange(self.nr)["teile"])):
            nr = next((s["nr"] for s in self.stangen if any(t["ref"] == ref for t in s["teile"])), None)
            if nr is not None:
                self.stange_zeigen(nr)
        self.detail.markieren(ref)
        if springen and ref is not None:
            i = next((i for i, (s, _) in enumerate(self.bild.muster) if any(t["ref"] == ref for t in s["teile"])), None)
            if i is not None:
                self.rollen[MUSTER].ensureVisible(0, self.bild.muster_y(i), 0, self.bild.ZEILE)
            if self.ansicht == UEBERSICHT:
                self._hinscrollen()

    def muster_zeigen(self, i):
        """i-tes Stangenmuster zeigen (Schnittmuster-Tabelle im Abmessungs-Fenster): Muster hinscrollen, im Detail und
        in der Übersicht seine erste Stange."""
        self.markieren(None)
        if 0 <= i < len(self.bild.muster):
            self.rollen[MUSTER].ensureVisible(0, self.bild.muster_y(i), 0, self.bild.ZEILE)
            self.stange_zeigen(self.bild.muster[i][1][0])
            if self.ansicht == UEBERSICHT:
                self._hinscrollen()

    def _teil(self, ref):
        self.markieren(ref, springen=False)
        self.klick.emit(ref)

    def _teil_merken(self, ref):
        """Klick auf ein Teil in der Übersicht: hervorheben (die Stange öffnet gewaehlt im Detail)."""
        self.markiert = ref
        self.bild.markieren(ref)
        self.uebersicht.markieren(ref)
        self.klick.emit(ref)
