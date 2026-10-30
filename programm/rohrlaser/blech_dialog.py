"""Fenster 'Blech-Editor': Blech- oder Kantteil beschreiben (Werkstoff, Dicke, Zuschnitt bzw. Schenkel mit
Biegungen, Innenkonturen), Abwicklung und Seitenansicht als Skizze, darunter das gefaltete Teil in 3D (blech3d),
Richtpreis je Stück als EK-Vorschlag des Zukaufteils (Rechnung in blech.py). Schreibt nichts in die
Rohrlaser-Daten."""
import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu,
                               QMessageBox,
                               QPushButton, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import einblendung, hilfe, stil
from . import blech, blech3d, blech_zeichnen as bz, dfm, dxf, gravur_text, schneidweg as sw, zukauf
from .muster_haken import MusterHaken
from .ansicht3d import Ansicht3DMitKnoepfen
from .leiste import UmbruchLeiste
from .teile_editor import EditorRahmen
from .stammdaten import zahl_als_text, zahl_aus_text
from .eingabe import RechenSpin, RechenSpinGanz

FARBE_BLECH, FARBE_LINIE, FARBE_KONTUR, FARBE_BIEGUNG = "#EAF1F8", "#1F4E78", "#B42318", "#2E7D32"
FARBE_MARKIERT = "#2E75B6"      # gewähltes Merkmal (Teile-Editor), wie in der 3D-Ansicht
KONTUR_SPALTEN = ("Art", "Anzahl", "Maß 1", "Maß 2", "Maß 3", "Mitte x [mm]", "Mitte y [mm]")
SCHENKEL_SPALTEN = ("Schenkel außen [mm]", "Biegewinkel danach [°]", "Innenradius [mm]")
# Vorlagen für Kantteile: [(Schenkel außen, Biegewinkel danach)]; Radius leer = Blechdicke
VORLAGEN = {"Winkel": [(50, 90), (50, 0)], "U-Profil": [(30, 90), (60, 90), (30, 0)],
            "Z-Profil": [(30, 90), (60, -90), (30, 0)], "Hutprofil": [(20, -90), (30, 90), (50, 90), (30, -90),
                                                                     (20, 0)]}


# Maße je Kontur-Art in der Tabelle; Text-Gravur: Text in Maß 1 (der Rohr-Rechner hat dafür die Spalte Bemerkung)
MASSE = dict(sw.MASSE, **{sw.TEXT_GRAVUR: (("text", "Text"),) + sw.MASSE[sw.TEXT_GRAVUR]})
TEXT_MASSE = ("punkte", "text")         # bleiben Text, keine Zahl


def _euro(w):
    return f"{zahl_als_text(round(w or 0, 2), 2)} €"


def _zahl_text(text):
    t = (text or "").strip()
    try:
        return zahl_aus_text(t) if t else None
    except ValueError:
        return None


def _feld(v):
    """Zahl für eine Tabellenzelle (ohne Tausenderpunkt, ohne unnötige Nullen)."""
    return "" if v in (None, "") else (v if isinstance(v, str) else zahl_als_text(float(v), None, tausender=False))


def _z_pos(alt, delta):
    neu = sw._z(alt) + delta
    if neu <= 0:
        raise ValueError("Maß würde 0")
    return neu


class BlechSkizze(QWidget):
    """Abwicklung (Zuschnitt mit Biegelinien und Innenkonturen) und beim Kantteil die Seitenansicht. mini=True:
    nur der Zuschnitt ohne Beschriftung und Rand (Vorschaubild der Positionsliste, siehe vorschau.py)."""

    gewaehlt = Signal(str)          # Merkmal unter der Maus ('kontur:3', 'biegung:0', 'teil')
    geaendert = Signal(dict)        # neue Eingaben nach Ziehen oder Zeichnen (Plan 3D-Editor C5)

    def __init__(self, mini=False):
        super().__init__()
        self.eingaben, self.zuschnitt, self.mini = {}, None, mini
        self.markiert = None            # Teile-Editor: gewähltes Merkmal ('kontur:3', 'biegung:0') blau
        self.raster = 1.0               # mm: Fangraster beim Ziehen und Zeichnen
        self._rahmen = self._fest = None    # (x0, y0, m, br, minx, miny) der letzten Zeichnung; fest beim Ziehen
        self._ziehen = None
        self._neu = None                # beim Zeichnen der Außenkontur: Punkte [(x, y)]
        self._maus = None
        self.setMinimumHeight(0 if mini else 260)
        if not mini:
            self.setMouseTracking(True)
            self.setFocusPolicy(Qt.ClickFocus)

    def markieren(self, merkmal):
        self.markiert = merkmal
        self.update()

    def setzen(self, eingaben, zuschnitt):
        self.eingaben, self.zuschnitt = eingaben, zuschnitt
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.mini:
            p.fillRect(self.rect(), stil.farbe("#FFFFFF"))
        zs = self.zuschnitt
        if not zs:
            p.setPen(stil.farbe("#5F6B7A"))
            p.drawText(self.rect(), Qt.AlignCenter, "Maße eingeben, dann erscheint hier die Abwicklung.")
            return
        kant = self.eingaben.get("art") == blech.KANTTEIL and not self.mini
        # Kantteil: Seitenansicht rechts daneben, in einer hohen Skizze (Editor zweispaltig) darunter
        untereinander = kant and self.height() >= self.width() * 0.75
        breite_abw = self.width() * (0.62 if kant and not untereinander else 1.0)
        hoehe_abw = self.height() * (0.58 if untereinander else 1.0)
        rand = 1.5 if self.mini else 46
        lg, br = max(zs["laenge"], 1), max(zs["breite"], 1)
        m = min((breite_abw - 2 * rand) / lg, (hoehe_abw - 2 * rand) / br)
        x0 = rand + ((breite_abw - 2 * rand - lg * m) / 2 if self.mini else 0)      # Vorschau mittig
        y0 = rand + (hoehe_abw - 2 * rand - br * m) / 2
        minx = miny = 0.0
        if zs.get("punkte"):
            minx, miny = min(x for x, _ in zs["punkte"]), min(y for _, y in zs["punkte"])
        if self._fest:          # beim Ziehen bleibt der Maßstab stehen
            x0, y0, m, br0, fx, fy = self._fest
            y0 += (br0 - br) * m
            x0, y0 = x0 + (minx - fx) * m, y0 - (miny - fy) * m
        self.m = m              # Pixel je mm der Abwicklung (Maßstab der Zeichnung als PDF)
        self._rahmen = (x0, y0, m, br, minx, miny)

        def pkt(x, y):          # mm (y nach oben) -> Pixel
            return QPointF(x0 + x * m, y0 + (br - y) * m)

        p.setFont(QFont(self.font().family(), 8))
        p.setPen(QPen(stil.farbe(FARBE_LINIE), 1.0 if self.mini else 1.6))
        p.setBrush(stil.farbe(FARBE_BLECH))
        if zs.get("punkte"):
            pfad = QPainterPath(pkt(zs["punkte"][0][0] - minx, zs["punkte"][0][1] - miny))
            for x, y in zs["punkte"][1:]:
                pfad.lineTo(pkt(x - minx, y - miny))
            pfad.closeSubpath()
            p.drawPath(pfad)
        else:
            r = sw._z(self.eingaben.get("eckradius")) * m if self.eingaben.get("art") != blech.KANTTEIL else 0
            p.drawRoundedRect(QRectF(pkt(0, br), pkt(lg, 0)), r, r)
        # Biegelinien quer zur Abwicklungsbreite (parallel zur Kantlänge)
        for i, (lage, winkel, radius, _) in enumerate(zs.get("biegungen") or [], 1):
            p.setPen(QPen(stil.farbe(FARBE_MARKIERT), 3.0) if self.markiert == f"biegung:{i - 1}" else
                     QPen(stil.farbe(FARBE_BIEGUNG), 1.2, Qt.DashLine))
            a, b = pkt(0, lage), pkt(lg, lage)
            p.drawLine(a, b)
            if self.mini:
                continue
            p.setPen(stil.farbe(FARBE_BIEGUNG))
            p.drawText(QPointF(b.x() + 4, b.y() + 4),
                       f"B{i} {zahl_als_text(abs(winkel), 0)}° {'↑' if winkel > 0 else '↓'} r{zahl_als_text(radius, 1)}")
        # mehrachsig gekantet (STEP-Import): Biegelinien in beliebiger Richtung
        if self.eingaben.get("art") != blech.KANTTEIL:
            for i, x in enumerate(self.eingaben.get("biegelinien") or (), 1):
                try:
                    (x1, y1), (x2, y2) = x["punkte"]
                except (TypeError, ValueError, KeyError):
                    continue
                p.setPen(QPen(stil.farbe(FARBE_MARKIERT), 3.0) if self.markiert == f"biegung:{i - 1}" else
                         QPen(stil.farbe(FARBE_BIEGUNG), 1.2, Qt.DashLine))
                a, b = pkt(x1 - minx, y1 - miny), pkt(x2 - minx, y2 - miny)
                p.drawLine(a, b)
                if not self.mini:
                    p.setPen(stil.farbe(FARBE_BIEGUNG))
                    w = sw._z(x.get("winkel"))
                    p.drawText(QPointF((a.x() + b.x()) / 2 + 4, (a.y() + b.y()) / 2 - 4),
                               f"B{i} {zahl_als_text(abs(w), 0)}° {'↑' if w > 0 else '↓'}")
        # Innenkonturen: Mitte x/y, ohne Angabe gleichmäßig auf der Mittellinie
        alle = self.eingaben.get("konturen") or []
        konturen = [z for z in alle if z.get("art")]
        frei = [z for z in konturen if z.get("x") is None or z.get("y") is None]
        zeile = {id(z): i for i, z in enumerate(alle)}
        p.setBrush(Qt.NoBrush)
        for z in konturen:
            if z in frei:
                k = frei.index(z)
                cx, cy = lg * (k + 1) / (len(frei) + 1), br / 2
            else:               # im System der Außenkontur (Polygon ab 0, 0 gezeichnet)
                cx, cy = z["x"] - minx, z["y"] - miny
            p.setPen(QPen(stil.farbe(FARBE_MARKIERT), 3.0) if self.markiert == f"kontur:{zeile[id(z)]}" else
                     QPen(stil.farbe(FARBE_KONTUR), 1.2))
            # ausgeschnitten wie in der Abwicklung des Rohrs (Patrick 25.10.2026): Grund scheint durch, Gravur nicht
            p.setBrush(Qt.NoBrush if z.get("art") in sw.GRAVUREN or z.get("linien") else stil.farbe("#FFFFFF"))
            self._kontur(p, z, pkt(cx, cy), m)
        if self.mini:
            return
        self._griffe_zeichnen(p)
        # Maße
        p.setPen(stil.farbe("#333333"))
        p.drawText(QRectF(x0, y0 + br * m + 4, lg * m, 16), Qt.AlignCenter, f"{zahl_als_text(lg, 1)} mm")
        p.save()
        p.translate(x0 - 6, y0 + br * m / 2)
        p.rotate(-90)
        p.drawText(QRectF(-80, -16, 160, 14), Qt.AlignCenter,
                   f"{zahl_als_text(br, 1)} mm" + (" (Abwicklung)" if kant else ""))
        p.restore()
        mehr = not kant and blech.kantungen(self.eingaben)
        p.drawText(QPointF(x0, 16), "Abwicklung (Zuschnitt)" if kant else
                   f"Abwicklung, mehrachsig gekantet ({mehr} Kantungen)" if mehr else "Zuschnitt")
        if kant and untereinander:
            self._seitenansicht(p, QRectF(10, hoehe_abw + 16, self.width() - 20, self.height() - hoehe_abw - 24), m)
        elif kant:
            self._seitenansicht(p, QRectF(breite_abw + 10, 24, self.width() - breite_abw - 20, self.height() - 40), m)

    # ------------------------------------------------------------------ Zeichnen und Ziehen (Plan 3D-Editor C5)
    def px(self, x, y):
        """mm im System der Eingaben -> Pixel (nach dem letzten Zeichnen)."""
        x0, y0, m, br, minx, miny = self._rahmen
        return QPointF(x0 + (x - minx) * m, y0 + (br - (y - miny)) * m)

    def mm(self, pos):
        """Pixel -> mm im System der Eingaben."""
        x0, y0, m, br, minx, miny = self._rahmen
        return (pos.x() - x0) / m + minx, br - (pos.y() - y0) / m + miny

    def _tol(self):
        return bz.FANG_PX / (self._rahmen[2] or 1)

    def _griffe_zeichnen(self, p):
        zs = self.zuschnitt
        p.setBrush(stil.farbe("#FFFFFF"))
        if self._neu is None and zs.get("punkte") and self.markiert == "teil" and not self.boegen():
            p.setPen(QPen(stil.farbe(FARBE_MARKIERT), 1.4))
            for x, y in zs["punkte"]:
                q = self.px(x, y)
                p.drawRect(QRectF(q.x() - 3.5, q.y() - 3.5, 7, 7))
        if self._neu is not None:
            pk = list(self._neu) + ([self._maus] if self._maus else [])
            p.setPen(QPen(stil.farbe(FARBE_MARKIERT), 1.8, Qt.DashLine if self._maus else Qt.SolidLine))
            if len(pk) > 1:
                p.drawPolyline([self.px(*q) for q in pk])
            p.setPen(QPen(stil.farbe(FARBE_MARKIERT), 1.4))
            for i, q in enumerate(self._neu):
                c = self.px(*q)
                p.drawRect(QRectF(c.x() - 3.5, c.y() - 3.5, 7, 7))
                if i == 0 and len(self._neu) >= 3:
                    p.drawEllipse(c, 7, 7)
            p.setPen(stil.farbe("#333333"))
            text = ("Außenkontur zeichnen: Punkte anklicken (Umschalt = waagerecht/senkrecht), auf den ersten Punkt, "
                    "Doppelklick oder Eingabe schließt; Rücktaste nimmt den letzten zurück, Esc bricht ab")
            if self._maus:
                text += f"  ·  x {zahl_als_text(self._maus[0], 1)}  y {zahl_als_text(self._maus[1], 1)}"
            p.drawText(QRectF(8, self.height() - 22, self.width() - 16, 18), Qt.AlignLeft | Qt.AlignVCenter, text)

    def boegen(self):
        """Außenkontur mit Bögen (DXF-Import)? Dann keine Eckgriffe, erst 'Bögen in Eckpunkte umwandeln'."""
        try:
            return self.eingaben.get("form") == blech.POLYGON and \
                any(b for *_, b in sw.punkte_roh(self.eingaben.get("punkte")))
        except ValueError:
            return False

    def boegen_aufloesen(self):
        """Bögen der Außenkontur in Eckpunkte (wie gerechnet, höchstens 0,02 mm Abweichung) zum Bearbeiten."""
        self._melden(dict(self.eingaben, punkte=bz.text(sw.punkte(self.eingaben.get("punkte")))))

    def zeichnen_starten(self):
        """Außenkontur neu mit Klicks zeichnen (ersetzt Rechteck bzw. Polygon beim Schließen)."""
        if self._rahmen is None:
            return
        self._neu, self._maus = [], None
        self.setCursor(Qt.CrossCursor)
        self.setFocus()
        self.update()

    def zeichnen_abbrechen(self):
        self._neu, self._maus = None, None
        self.unsetCursor()
        self.update()

    def zeichnen_schliessen(self):
        pk = self._neu or []
        if len(pk) >= 2 and math.dist(pk[0], pk[-1]) < 1e-6:
            pk = pk[:-1]
        self.zeichnen_abbrechen()
        if len(pk) >= 3:
            self._melden(dict(self.eingaben, form=blech.POLYGON, punkte=bz.text(pk)))

    def als_polygon(self):
        """Rechteck (bzw. Abwicklung des Kantteils) als Polygon mit vier Ecken übernehmen, z. B. zum Abrunden."""
        if self.zuschnitt and not self.zuschnitt.get("punkte"):
            self._melden(dict(self.eingaben, form=blech.POLYGON,
                              punkte=bz.text(bz.polygon_aus(self.eingaben, self.zuschnitt))))

    def _melden(self, e):
        self.eingaben = e
        try:
            self.zuschnitt = blech.zuschnitt(e)
        except ValueError:
            pass
        self.update()
        self.geaendert.emit(e)

    def _punkt(self, pos, tasten=Qt.NoModifier):
        x, y = self.mm(pos)
        q = (bz.fangen(x, self.raster), bz.fangen(y, self.raster))
        if tasten & Qt.ShiftModifier and self._neu:
            q = bz.rechtwinklig(self._neu[-1], q)
        return q

    def treffer(self, pos):
        """Was liegt unter der Maus: ('ecke', i), ('kontur', Zeile), ('biegung', i), ('kante', Name) oder None."""
        zs = self.zuschnitt
        if not zs or self._rahmen is None:
            return None
        q, tol = self.mm(pos), self._tol()
        e = self.eingaben
        if zs.get("punkte") and not self.boegen():
            i = bz.naechste_ecke(zs["punkte"], q, tol)
            if i is not None:
                return ("ecke", i)
        kand = [(math.dist(q, (x, y)), r) for r, x, y in bz.kontur_mitten(e, zs)
                if math.dist(q, (x, y)) <= bz.kontur_radius(e["konturen"][r]) + tol]
        if kand:
            return ("kontur", min(kand)[1])
        minx = min((x for x, _ in zs.get("punkte") or ()), default=0.0)
        miny = min((y for _, y in zs.get("punkte") or ()), default=0.0)
        for i, (lage, *_rest) in enumerate(zs.get("biegungen") or ()):
            if abs(q[1] - miny - lage) <= tol and minx - tol <= q[0] <= minx + zs["laenge"] + tol:
                return ("biegung", i)
        if not zs.get("punkte"):
            lg, br = zs["laenge"], zs["breite"]
            if abs(q[0] - lg) <= tol and -tol <= q[1] <= br + tol:
                return ("kante", "rechts")
            if abs(q[1] - br) <= tol and -tol <= q[0] <= lg + tol:
                return ("kante", "oben")
            if abs(q[1]) <= tol and -tol <= q[0] <= lg + tol and e.get("art") == blech.KANTTEIL:
                return ("kante", "unten")
        return None

    def mousePressEvent(self, ereignis):
        if self.mini or self._rahmen is None:
            return
        pos = ereignis.position()
        if self._neu is not None:
            if ereignis.button() == Qt.LeftButton:
                q = self._punkt(pos, ereignis.modifiers())
                if len(self._neu) >= 3 and (self.px(*self._neu[0]) - pos).manhattanLength() <= 2 * bz.FANG_PX:
                    self.zeichnen_schliessen()
                    return
                if not self._neu or q != self._neu[-1]:
                    self._neu.append(q)
                self.update()
            return
        if ereignis.button() != Qt.LeftButton:
            return
        t = self.treffer(pos)
        art = t[0] if t else None
        mid = {"kontur": f"kontur:{t[1]}" if t else None, "biegung": f"biegung:{t[1]}" if t else None}.get(art, "teil")
        self.markieren(mid)
        self.gewaehlt.emit(mid)
        if t:
            self._ziehen = dict(t=t, start=self.mm(pos), e=json.loads(json.dumps(self.eingaben)), neu=None)
            self._fest = self._rahmen

    def mouseMoveEvent(self, ereignis):
        if self.mini or self._rahmen is None:
            return
        pos = ereignis.position()
        if self._neu is not None:
            self._maus = self._punkt(pos, ereignis.modifiers())
            self.update()
            return
        z = self._ziehen
        if z is None:
            t = self.treffer(pos)
            self.setCursor(Qt.SizeAllCursor if t and t[0] in ("ecke", "kontur") else
                           Qt.SizeVerCursor if t and (t[0] == "biegung" or t[1] in ("oben", "unten")) else
                           Qt.SizeHorCursor if t else Qt.ArrowCursor)
            return
        x, y = self.mm(pos)
        dx = bz.fangen(x - z["start"][0], self.raster)
        dy = bz.fangen(y - z["start"][1], self.raster)
        try:
            neu = self.gezogen(z["e"], z["t"], dx, dy)
            zs = blech.zuschnitt(neu)
        except (ValueError, TypeError, IndexError):
            return
        z["neu"] = neu
        self.eingaben, self.zuschnitt = neu, zs
        self.update()

    def gezogen(self, e, t, dx, dy):
        """Eingaben e, nachdem das Merkmal t um (dx, dy) mm gezogen wurde (ValueError, wenn es so nicht geht)."""
        e = json.loads(json.dumps(e))
        art, i = t
        if art == "ecke":
            pk = sw.punkte(e.get("punkte"))
            pk[i] = (round(pk[i][0] + dx, 3), round(pk[i][1] + dy, 3))
            e["punkte"] = bz.text(pk)
        elif art == "kontur":
            zs = blech.zuschnitt(e)
            _, cx, cy = next(m for m in bz.kontur_mitten(e, zs) if m[0] == i)
            e["konturen"][i].update(x=round(cx + dx, 3), y=round(cy + dy, 3))
        elif art == "biegung":
            e["schenkel"] = bz.schenkel_ziehen(e.get("schenkel") or [], i, dy)
        elif i == "unten":
            e["schenkel"] = bz.schenkel_ziehen(e.get("schenkel") or [], -1, -dy)
        elif i == "oben" and e.get("art") == blech.KANTTEIL:
            e["schenkel"] = bz.schenkel_ziehen(e.get("schenkel") or [], len(e.get("schenkel") or []), dy)
        elif i == "oben":
            e["breite"] = round(_z_pos(e.get("breite"), dy), 3)
        else:
            schl = "kantlaenge" if e.get("art") == blech.KANTTEIL else "laenge"
            e[schl] = round(_z_pos(e.get(schl), dx), 3)
        return e

    def mouseReleaseEvent(self, ereignis):
        z, self._ziehen = self._ziehen, None
        self._fest = None
        if z and z.get("neu"):
            self._melden(z["neu"])
        self.update()

    def mouseDoubleClickEvent(self, ereignis):
        if self._neu is not None:
            self.zeichnen_schliessen()

    def keyPressEvent(self, ereignis):
        if self._neu is None:
            return super().keyPressEvent(ereignis)
        k = ereignis.key()
        if k == Qt.Key_Escape:
            self.zeichnen_abbrechen()
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.zeichnen_schliessen()
        elif k == Qt.Key_Backspace and self._neu:
            self._neu.pop()
            self.update()

    def contextMenuEvent(self, ereignis):
        if self.mini or self._rahmen is None or self._neu is not None:
            return
        menue = self.menue(ereignis.pos())
        if menue is not None and not menue.isEmpty():
            menue.exec(ereignis.globalPos())

    def menue(self, pos):
        """Kontextmenü an der Stelle pos: Ecke abrunden/fasen, Punkt löschen/einfügen, Außenkontur zeichnen."""
        zs = self.zuschnitt
        if not zs:
            return None
        m = QMenu(self)
        q, tol = self.mm(QPointF(pos)), self._tol()
        pk = list(zs.get("punkte") or ()) if not self.boegen() else []
        if self.boegen():
            m.addAction("Bögen in Eckpunkte umwandeln", self.boegen_aufloesen)
        i = bz.naechste_ecke(pk, q, tol) if pk else None
        if i is not None:
            m.addAction("Ecke abrunden …", lambda: self._ecke_fragen(i, "runden"))
            m.addAction("Ecke fasen …", lambda: self._ecke_fragen(i, "fasen"))
            a = m.addAction("Punkt löschen", lambda: self.ecke_aendern(bz.punkt_weg, i))
            a.setEnabled(len(pk) > 3)
        elif pk and (k := bz.naechste_kante(pk, q, tol)) is not None:
            f = (round(bz.fangen(k[1][0], self.raster), 3), round(bz.fangen(k[1][1], self.raster), 3))
            m.addAction("Punkt einfügen", lambda: self.ecke_aendern(bz.punkt_einfuegen, k[0], f))
        if not zs.get("punkte"):
            m.addAction("Als Polygon bearbeiten", self.als_polygon)
        m.addAction("Außenkontur neu zeichnen", self.zeichnen_starten)
        return m

    def _ecke_fragen(self, i, art):
        w, ok = QInputDialog.getDouble(self, "Ecke abrunden" if art == "runden" else "Ecke fasen",
                                       "Radius [mm]" if art == "runden" else "Fase je Kante [mm]", 5.0, 0.1, 10000, 1)
        if ok:
            self.ecke_aendern(bz.ecke_runden if art == "runden" else bz.ecke_fasen, i, w)

    def ecke_aendern(self, fn, *args):
        """Außenkontur mit fn(Punkte, *args) ändern; Fehler als Meldung."""
        try:
            pk = fn(sw.punkte(self.eingaben.get("punkte")), *args)
        except ValueError as x:
            einblendung.melden(self, str(x))
            return False
        self._melden(dict(self.eingaben, form=blech.POLYGON, punkte=bz.text(pk)))
        return True

    def _kontur(self, p, z, c, m):
        art = z.get("art")
        if z.get("linien"):                     # DXF-Import: Gravur bzw. offene Schnittlinie wie gezeichnet
            for zug in z["linien"]:
                p.drawPolyline([QPointF(c.x() + float(x) * m, c.y() - float(y) * m) for x, y in zug])
        elif blech.drehung(z):                    # gedreht (3E-4b): Umriss als Linienzug
            zug = blech.kontur_umriss(z, 10)
            if zug:
                p.drawPolyline([QPointF(c.x() + x * m, c.y() - y * m) for x, y in zug])
        elif art in (sw.BOHRUNG, sw.SENKUNG):
            r = sw._z(z.get("d")) / 2 * m
            p.drawEllipse(c, r, r)
        elif art == sw.LANGLOCH:
            lg, b = sw._z(z.get("l")) * m, sw._z(z.get("b")) * m
            if z.get("quer"):           # Längsrichtung quer zum Zuschnitt (aus dem STEP-Import)
                lg, b = b, lg
            p.drawRoundedRect(QRectF(c.x() - lg / 2, c.y() - b / 2, lg, b), min(lg, b) / 2, min(lg, b) / 2)
        elif art == sw.RECHTECK:
            b, h, r = sw._z(z.get("b")) * m, sw._z(z.get("h")) * m, sw._z(z.get("r")) * m
            p.drawRoundedRect(QRectF(c.x() - b / 2, c.y() - h / 2, b, h), r, r)
        elif art == sw.POLYGON:
            try:
                pk = sw.punkte(z.get("punkte"))
            except ValueError:
                return
            if len(pk) >= 3:
                mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
                pfad = QPainterPath(QPointF(c.x() + (pk[0][0] - mx) * m, c.y() - (pk[0][1] - my) * m))
                for x, y in pk[1:]:
                    pfad.lineTo(QPointF(c.x() + (x - mx) * m, c.y() - (y - my) * m))
                pfad.closeSubpath()
                p.drawPath(pfad)
        elif art == sw.TEXT_GRAVUR:      # Einstrich-Schrift wie graviert (y nach oben)
            for zug in gravur_text.gedreht(gravur_text.linien(z.get("text"), sw._z(z.get("hoehe"))), z.get("winkel")):
                p.drawPolyline([QPointF(c.x() + x * m, c.y() - y * m) for x, y in zug])
        else:
            p.drawRect(QRectF(c.x() - 4, c.y() - 4, 8, 8))
        n = int(sw._z(z.get("anzahl")) or 1)
        if n > 1 and not self.mini:
            p.drawText(QPointF(c.x() + 6, c.y() - 6), f"{n} ×")

    def _seitenansicht(self, p, feld, m_abw=None):
        """Seitenansicht im Maßstab der Abwicklung (kleiner, wenn sie sonst nicht passt); Maße außen an den
        Schenkeln."""
        pk = blech.querschnitt(self.eingaben)
        if len(pk) < 2:
            return
        xs, ys = [x for x, _ in pk], [y for _, y in pk]
        w, h = max(max(xs) - min(xs), 1), max(max(ys) - min(ys), 1)
        m = min((feld.width() - 80) / w, (feld.height() - 70) / h, m_abw or 1e9)
        ox = feld.x() + 20 + (feld.width() - 40 - w * m) / 2 - min(xs) * m
        oy = feld.y() + 30 + (feld.height() - 50 + h * m) / 2 + min(ys) * m
        p.setPen(stil.farbe("#333333"))
        p.drawText(QPointF(feld.x(), feld.y() - 8), "Seitenansicht (Außenmaße)")
        p.setPen(QPen(stil.farbe(FARBE_LINIE), min(max(2.0, sw._z(self.eingaben.get("dicke")) * m), 8.0)))
        for (x1, y1), (x2, y2) in zip(pk, pk[1:]):
            p.drawLine(QPointF(ox + x1 * m, oy - y1 * m), QPointF(ox + x2 * m, oy - y2 * m))
        p.setPen(stil.farbe("#333333"))
        schenkel = [z for z in self.eingaben.get("schenkel") or [] if sw._z(z.get("laenge")) > 0]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)          # Maße von der Mitte weg nach außen schieben
        for (x1, y1), (x2, y2), z in zip(pk, pk[1:], schenkel):
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            dx, dy = cx - mx, cy - my
            n = (dx * dx + dy * dy) ** 0.5 or 1
            px, py = ox + cx * m + dx / n * 16, oy - cy * m - dy / n * 16
            p.drawText(QRectF(px - 30, py - 8, 60, 16), Qt.AlignCenter, zahl_als_text(z["laenge"], 1))


class BlechDialog(QDialog):
    """Blech-Editor. eingaben: gespeicherte Eingaben (blech.lesen) oder None; kopf: Bezeichnung, Artikelnummer,
    Lieferant, Stückzahl vorbelegt; neu: Kopfzeile für ein neues Zukaufteil. Nach OK: eingaben(), ergebnis,
    kopf_werte()."""

    def __init__(self, parent, db, eingaben=None, kopf=None, neu=True):
        super().__init__(parent)
        self.db, self.neu = db, neu
        self.werkstoffe = {z["blech_werkstoff_id"]: z for z in db.zeilen("blech_werkstoffe")
                           if z.get("blech_werkstoff_id")}
        self.laserdaten = db.zeilen("blechlaser")
        self.einst = db.blech_einstellungen()
        self.ergebnis = {}
        self._bez_von_hand = bool((kopf or {}).get("bezeichnung"))
        e = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100, stueck=1, konturen=[],
                 schenkel=[dict(laenge=a, winkel=w) for a, w in VORLAGEN["Winkel"]], kantlaenge=200)
        e.update(eingaben or {})
        kopf = kopf or {}
        self.setWindowTitle("Blech-Editor (Richtpreis)")
        # links die Eingaben (Tabellen mit Platz für viele Zeilen), rechts Skizze und Richtpreis
        haupt = QVBoxLayout(self)
        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.setChildrenCollapsible(False)
        haupt.addWidget(self.teiler, 1)
        links = QWidget()
        self.eingabe_bereich = links    # Teile-Editor: Eingaben links neben den Ansichten
        lay = QVBoxLayout(links)
        lay.setContentsMargins(0, 0, 6, 0)
        self.teiler.addWidget(links)

        # Kopf: Bezeichnung, Artikelnummer, Lieferant, Stückzahl
        raster = QGridLayout()
        self.bezeichnung = QLineEdit(kopf.get("bezeichnung") or "")
        self.bezeichnung.setPlaceholderText("wird aus den Maßen vorgeschlagen")
        self.bezeichnung.textEdited.connect(lambda t: setattr(self, "_bez_von_hand", bool(t.strip())))
        self.artikelnr = QLineEdit(kopf.get("artikelnr") or "")
        self.artikelnr.setPlaceholderText("optional")
        self.lieferant = QComboBox()
        self.lieferant.setEditable(True)
        self.lieferant.addItems(sorted(z["name"] for z in db.zeilen("zukauf_lieferanten") if z.get("name")))
        self.lieferant.setCurrentText(kopf.get("lieferant") or zukauf.lieferant_vorgabe("Blechteile"))
        self.stueck = RechenSpinGanz()
        self.stueck.setRange(1, 10 ** 7)
        self.stueck.setValue(int(sw._z(kopf.get("stueck") or e.get("stueck")) or 1))
        self.stueck.setToolTip("Stückzahl der Position; Rüsten wird auf diese Menge umgelegt")
        self.werkstoff = QComboBox()
        for kat in ("Stahl", "Edelstahl", "Aluminium"):
            for n in sorted(x for x, z in self.werkstoffe.items() if z.get("kategorie") == kat):
                self.werkstoff.addItem(n)
        for n in sorted(x for x, z in self.werkstoffe.items() if self.werkstoff.findText(x) < 0):
            self.werkstoff.addItem(n)
        if e.get("werkstoff") in self.werkstoffe:
            self.werkstoff.setCurrentText(e["werkstoff"])
        self.dicke = self._spin(e.get("dicke"), 0.1, 100, 0.5, " mm", 2)
        self.art = QComboBox()
        self.art.addItems(list(blech.ARTEN))
        self.art.setCurrentText(e.get("art") or blech.ZUSCHNITT)
        # zwei Zeilen: Bezeichnung (breit), Artikelnummer, Stückzahl / Werkstoff, Dicke, Art, Lieferant
        felder = ((0, 0, 2, "Bezeichnung", self.bezeichnung), (0, 2, 1, "Artikelnummer", self.artikelnr),
                  (0, 3, 1, "Stückzahl", self.stueck), (2, 0, 1, "Blech-Werkstoff", self.werkstoff),
                  (2, 1, 1, "Dicke", self.dicke), (2, 2, 1, "Art", self.art), (2, 3, 1, "Lieferant", self.lieferant))
        for r, c, n, titel, w in felder:
            raster.addWidget(QLabel(f"<span style='color:#595959'>{titel}</span>"), r, c, 1, n)
            raster.addWidget(w, r + 1, c, 1, n)
        # Musterteil (Patrick 28.10.2026): in allen Editoren gleich (muster_haken.py)
        self.muster_haken = MusterHaken(kopf)
        raster.addWidget(self.muster_haken, 1, 4)
        for c in range(4):
            raster.setColumnStretch(c, 1)
        lay.addLayout(raster)

        # Geometrie: Zuschnitt oder Kantteil
        self.stapel = QStackedWidget()
        flach = QWidget()
        fl = QGridLayout(flach)
        fl.setContentsMargins(0, 0, 0, 0)
        self.laenge = self._spin(e.get("laenge"), 0, 100000, 10, " mm", 1)
        self.breite = self._spin(e.get("breite"), 0, 100000, 10, " mm", 1)
        self.eckradius = self._spin(e.get("eckradius"), 0, 10000, 1, " mm", 1)
        self.kantungen = RechenSpinGanz()
        self.kantungen.setRange(0, 99)
        self.kantungen.setValue(int(sw._z(e.get("kantungen"))))
        self.kantungen.setToolTip("Mehrachsig gekantetes Teil (z. B. Schale aus dem STEP-Import): Anzahl Kantungen "
                                  "für die Kosten Kanten; 0 = flaches Blech")
        self.biegelinien = list(e.get("biegelinien") or ())      # aus dem STEP-Import, nur Skizze und 3D
        for c, (titel, w) in enumerate((("Länge", self.laenge), ("Breite", self.breite),
                                        ("Eckradius", self.eckradius), ("Kantungen", self.kantungen))):
            fl.addWidget(QLabel(f"<span style='color:#595959'>{titel}</span>"), 0, c)
            fl.addWidget(w, 1, c)
        fl.setRowStretch(2, 1)
        self.stapel.addWidget(flach)
        kant = QWidget()
        kl = QVBoxLayout(kant)
        kl.setContentsMargins(0, 0, 0, 0)
        zeile = QHBoxLayout()
        self.kantlaenge = self._spin(e.get("kantlaenge"), 0, 100000, 10, " mm", 1)
        self.kantlaenge.setToolTip("Länge des Teils entlang der Biegekanten")
        zeile.addWidget(QLabel("Kantlänge"))
        zeile.addWidget(self.kantlaenge)
        self.vorlage = QComboBox()
        self.vorlage.addItems(["Vorlage …"] + list(VORLAGEN))
        self.vorlage.activated.connect(self._vorlage)
        zeile.addWidget(self.vorlage)
        self.schenkel_knoepfe = []
        for text, ziel in (("+ Schenkel", lambda: self.schenkel_neu()), ("Schenkel entfernen", self._schenkel_weg)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            zeile.addWidget(b)
            self.schenkel_knoepfe.append(b)
        zeile.addStretch(1)
        kl.addLayout(zeile)
        self.schenkel = QTableWidget(0, len(SCHENKEL_SPALTEN))
        self.schenkel.setHorizontalHeaderLabels(list(SCHENKEL_SPALTEN))
        self.schenkel.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.schenkel.verticalHeader().setDefaultSectionSize(26)
        self.schenkel.setMinimumHeight(self.schenkel.horizontalHeader().sizeHint().height() + 4 * 26 + 6)
        self.schenkel.setToolTip("Je Zeile ein Schenkel mit Außenmaß; Biegewinkel zum nächsten Schenkel (+ nach oben, "
                                 "− nach unten, 90 = rechter Winkel); Innenradius leer = Blechdicke")
        kl.addWidget(self.schenkel, 1)
        self.stapel.addWidget(kant)
        lay.addWidget(self.stapel, 2)
        # Außenkontur (Zuschnitt und Kantteil): Rechteck aus den Maßen oder freies Polygon der Abwicklung
        zeile = QHBoxLayout()
        self.form = QComboBox()
        self.form.addItems(list(blech.FORMEN))
        self.form.setCurrentText(e.get("form") or blech.RECHTECK)
        self.form.setToolTip("Rechteck: Länge × Breite (Kantteil: Kantlänge × Abwicklung); Polygon: freie "
                             "Außenkontur der Abwicklung mit Eckpunkten")
        self.punkte = QLineEdit(e.get("punkte") or "")
        self.punkte.setPlaceholderText("Eckpunkte x,y; x,y; … in mm, z. B. 0,0; 200,0; 200,80; 120,150; 0,150")
        zeile.addWidget(QLabel("<span style='color:#595959'>Außenkontur</span>"))
        zeile.addWidget(self.form)
        zeile.addWidget(self.punkte, 1)
        lay.addLayout(zeile)
        for x in e.get("schenkel") or []:
            self.schenkel_neu(x, rechnen_=False)

        # Innenkonturen
        box = QGroupBox("Innenkonturen")
        bl = QVBoxLayout(box)
        self.tabelle = QTableWidget(0, len(KONTUR_SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(list(KONTUR_SPALTEN))
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        self.tabelle.setMinimumHeight(self.tabelle.horizontalHeader().sizeHint().height() + 5 * 26 + 6)
        self.tabelle.setToolTip("Maße je Art: Bohrung Maß 1 = Ø; Langloch Länge, Breite; Rechteck Breite, Höhe, "
                                "Eckradius; Polygon Eckpunkte in Maß 1; sonstige Kontur Schnittlänge, Hüllmaß; "
                                "Text-Gravur Text, Schrifthöhe, Winkel (nur graviert). "
                                "Mitte x/y in der Abwicklung (leer = nur für die Skizze verteilt)")
        self.tabelle.currentCellChanged.connect(lambda r, *_: self._spalten_erklaeren(r))
        bl.addWidget(self.tabelle, 1)
        knoepfe = UmbruchLeiste()           # bei schmaler Spalte rückt 'Markierte entfernen' in eine zweite Zeile
        for art in (sw.BOHRUNG, sw.LANGLOCH, sw.RECHTECK, sw.POLYGON, sw.SONSTIGE, sw.TEXT_GRAVUR):
            b = QPushButton(f"+ {art}")
            b.clicked.connect(lambda _=False, art=art: self.kontur_neu(self._kontur_vorgabe(art)))
            knoepfe.links_layout.addWidget(b)
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(self._kontur_weg)
        knoepfe.rechts_layout.addWidget(weg)
        bl.addWidget(knoepfe)
        self.kontur_leiste = knoepfe    # Teile-Editor: die Befehle stehen im Menüband
        lay.addWidget(box, 3)
        for z in e.get("konturen") or []:
            self.kontur_neu(z, rechnen_=False)

        rechts = QWidget()
        lay = QVBoxLayout(rechts)
        lay.setContentsMargins(6, 0, 0, 0)
        self.teiler.addWidget(rechts)
        self.skizze = BlechSkizze()
        self.skizze.setToolTip("Abwicklung: Innenkonturen, Biegelinien, Außenkanten und Eckpunkte mit der Maus ziehen; "
                               "Rechtsklick auf eine Ecke rundet oder fast sie")
        self.skizze.geaendert.connect(self.skizze_geaendert)
        self.ansicht3d = Ansicht3DMitKnoepfen()
        self.ansicht3d.setToolTip("Das gefaltete Teil aus den Eingaben (zur Anschauung): Innenkonturen rot, "
                                  "Biegelinien grün")
        bilder = QSplitter(Qt.Vertical)
        bilder.setChildrenCollapsible(False)
        bilder.addWidget(self.skizze)
        bilder.addWidget(self.ansicht3d)
        lay.addWidget(bilder, 1)
        self.bilder_teiler, self.ergebnis_bereich = bilder, rechts
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        self.summe.setTextFormat(Qt.RichText)
        lay.addWidget(self.summe)
        hinweis = hilfe.Hinweis("Richtpreis zur Kostenschätzung vorab (EK-Vorschlag). Werkstoffe, Blechlaser-Richtwerte "
                                "und Sätze stehen unter Einstellungen; die Rohrlaser-Daten bleiben unverändert.",
                                schluessel="blech_editor")
        lay.addWidget(hinweis)
        lay = haupt
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_knopf = self.knoepfe.button(QDialogButtonBox.Ok)
        self.ok_knopf.setText("Als Zukaufteil anlegen" if neu else "Richtpreis übernehmen")
        self.dxf_knopf = self.knoepfe.addButton("DXF speichern …", QDialogButtonBox.ActionRole)
        self.dxf_knopf.setToolTip("Abwicklung als DXF (R12) mit Layern für Außenkontur, Innenkonturen, Biegelinien "
                                  "und Beschriftung, z. B. für den Blechlaser oder den Lieferanten")
        self.dxf_knopf.clicked.connect(lambda: self.dxf_speichern())
        self.zeichnung_knopf = self.knoepfe.addButton("Zeichnung als PDF …", QDialogButtonBox.ActionRole)
        self.zeichnung_knopf.setToolTip("Maßstäbliche Zeichnung: Abwicklung bzw. Zuschnitt mit Bemaßung, Biegelinien "
                                        "und Seitenansicht, Liste der Biegungen und Innenkonturen mit Lage")
        self.zeichnung_knopf.clicked.connect(lambda: self.zeichnung_pdf())
        self.knoepfe.accepted.connect(self.accept)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)

        for w in (self.dicke, self.laenge, self.breite, self.eckradius, self.kantlaenge, self.kantungen):
            w.valueChanged.connect(self.rechnen)
        self.stueck.valueChanged.connect(self.rechnen)
        for w in (self.werkstoff, self.art, self.form):
            w.currentTextChanged.connect(self.rechnen)
        self.punkte.textChanged.connect(self.rechnen)
        self.schenkel.itemChanged.connect(self.rechnen)
        self.tabelle.itemChanged.connect(self.rechnen)
        frei = self.screen().availableGeometry() if self.screen() else None
        breite, hoehe = (frei.width() - 40, frei.height() - 70) if frei else (1400, 900)
        self.resize(min(1500, breite), min(950, hoehe))
        self.teiler.setSizes([int(self.width() * 0.52), self.width() - int(self.width() * 0.52)])
        # Werte wie im STEP-Import gemessen (Teile-Editor: Herkunft, zurücksetzen); beim ersten Öffnen aus den Eingaben
        self.step_werte = e.get("step") if isinstance(e.get("step"), dict) else None
        if e.get("step") is True:
            self.step_werte = {k: v for k, v in self.eingaben().items() if k not in ("stueck", "step")}
        self.editor = None
        self.rechnen()
        EditorRahmen(self, "blech")

    @staticmethod
    def _spin(wert, von, bis, schritt, suffix, stellen):
        w = RechenSpin()
        w.setRange(von, bis)
        w.setSingleStep(schritt)
        w.setDecimals(stellen)
        w.setSuffix(suffix)
        w.setValue(sw._z(wert))
        return w

    # -------------------------------------------------------------- Tabellen
    def schenkel_neu(self, x=None, rechnen_=True):
        x = x or dict(laenge=30, winkel=90)
        r = self.schenkel.rowCount()
        self.schenkel.blockSignals(True)
        self.schenkel.insertRow(r)
        for c, n in enumerate(("laenge", "winkel", "radius")):
            v = x.get(n)
            self.schenkel.setItem(r, c, QTableWidgetItem(_feld(v)))
        self.schenkel.blockSignals(False)
        if rechnen_:
            self.rechnen()

    def _schenkel_weg(self):
        r = self.schenkel.currentRow()
        if r >= 0:
            self.schenkel.removeRow(r)
            self.rechnen()

    def _vorlage(self, i):
        if i <= 0:
            return
        self.schenkel.setRowCount(0)
        for a, w in VORLAGEN[self.vorlage.itemText(i)]:
            self.schenkel_neu(dict(laenge=a, winkel=w), rechnen_=False)
        self.vorlage.setCurrentIndex(0)
        self.art.setCurrentText(blech.KANTTEIL)
        self.rechnen()

    def kontur_neu(self, z, rechnen_=True):
        r = self.tabelle.rowCount()
        self.tabelle.blockSignals(True)
        self.tabelle.insertRow(r)
        art = QComboBox()
        art.addItems(list(blech.KONTUR_ARTEN))
        art.setCurrentText(z.get("art") or sw.BOHRUNG)
        art.quer = bool(z.get("quer"))      # Langloch quer (STEP-Import); bleibt beim Speichern erhalten
        art.artikel = bool(z.get("artikel"))    # Text-Gravur der Artikelnummer aus dem Baugruppen-Editor
        art.eig = {"drehung": z["drehung"]} if z.get("drehung") else {}     # Drehwinkel (Teile-Editor)
        art.linien = z.get("linien")        # Linien einer Gravur bzw. offenen Schnittlinie aus dem DXF-Import
        art.currentTextChanged.connect(self.rechnen)
        self.tabelle.setCellWidget(r, 0, art)
        masse = [k for k, _ in MASSE.get(z.get("art"), ())]
        werte = [z.get("anzahl", 1)] + [z.get(k) for k in masse] + [None] * (3 - len(masse)) + [z.get("x"), z.get("y")]
        for c, v in enumerate(werte, 1):
            self.tabelle.setItem(r, c, QTableWidgetItem(_feld(v)))
        self.tabelle.blockSignals(False)
        if rechnen_:
            self.rechnen()

    def _kontur_vorgabe(self, art):
        """Neue Zeile; Text-Gravur mit Artikelnummer (Kopf) und Schrifthöhe aus der Einstellung, Lage frei gesucht."""
        z = dict(art=art, anzahl=1)
        if art == sw.TEXT_GRAVUR:
            z.update(text=self.artikelnr.text().strip() if hasattr(self, "artikelnr") else "",
                     hoehe=self.db.einstellung("gravur_schrifthoehe") or 10, winkel=0)
            lage = blech.gravur_lage(self.eingaben(), z) or {}
            z.update({n: lage[n] for n in ("x", "y", "winkel") if n in lage})
        return z

    def _spalten_erklaeren(self, zeile):
        """Überschriften Maß 1–3 nach der Art der markierten Zeile (z. B. Langloch: Länge l, Breite b)."""
        art = self.tabelle.cellWidget(zeile, 0).currentText() if 0 <= zeile < self.tabelle.rowCount() else None
        titel = [f"{t} [mm]" if k not in TEXT_MASSE and "[" not in t else t for k, t in MASSE.get(art, ())]
        for c in range(3):
            self.tabelle.horizontalHeaderItem(2 + c).setText(titel[c] if c < len(titel) else f"Maß {c + 1}")

    def _kontur_weg(self):
        for r in sorted({i.row() for i in self.tabelle.selectedIndexes()}, reverse=True):
            self.tabelle.removeRow(r)
        self.rechnen()

    def _text(self, tabelle, r, c):
        it = tabelle.item(r, c)
        return it.text() if it else ""

    # -------------------------------------------------------------- Eingaben und Ergebnis
    def eingaben(self):
        konturen = []
        for r in range(self.tabelle.rowCount()):
            art = self.tabelle.cellWidget(r, 0).currentText()
            z = dict(art=art, anzahl=_zahl_text(self._text(self.tabelle, r, 1)) or 0)
            for c, (k, _) in enumerate(MASSE.get(art, ()), 2):
                t = self._text(self.tabelle, r, c)
                z[k] = t.strip() if k in TEXT_MASSE else _zahl_text(t)
            z["x"], z["y"] = _zahl_text(self._text(self.tabelle, r, 5)), _zahl_text(self._text(self.tabelle, r, 6))
            if art == sw.LANGLOCH and getattr(self.tabelle.cellWidget(r, 0), "quer", False):
                z["quer"] = True
            if art == sw.TEXT_GRAVUR and getattr(self.tabelle.cellWidget(r, 0), "artikel", False):
                z["artikel"] = True
            eig = getattr(self.tabelle.cellWidget(r, 0), "eig", None) or {}
            if eig.get("drehung") and art in blech.DREH_ARTEN:
                z["drehung"] = eig["drehung"]
            if getattr(self.tabelle.cellWidget(r, 0), "linien", None) and art in (sw.GRAVUR, sw.SONSTIGE):
                z["linien"] = self.tabelle.cellWidget(r, 0).linien
            konturen.append(z)
        schenkel = [dict(laenge=_zahl_text(self._text(self.schenkel, r, 0)),
                         winkel=_zahl_text(self._text(self.schenkel, r, 1)) or 0,
                         radius=_zahl_text(self._text(self.schenkel, r, 2)))
                    for r in range(self.schenkel.rowCount())]
        e = dict(werkstoff=self.werkstoff.currentText() or None, dicke=self.dicke.value(),
                 art=self.art.currentText(), form=self.form.currentText(), laenge=self.laenge.value(),
                 breite=self.breite.value(), eckradius=self.eckradius.value(),
                 punkte=self.punkte.text().strip() or None, kantlaenge=self.kantlaenge.value(),
                 schenkel=schenkel, konturen=konturen, stueck=self.stueck.value())
        if e["art"] != blech.KANTTEIL and self.kantungen.value():
            e.update(kantungen=self.kantungen.value(), biegelinien=self.biegelinien)
        if getattr(self, "step_werte", None):
            e["step"] = self.step_werte
        return e

    def eingaben_setzen(self, e):
        """Alle Eingaben aus e (wie eingaben()) setzen, dann einmal rechnen (Teile-Editor: Rückgängig)."""
        felder = (self.dicke, self.laenge, self.breite, self.eckradius, self.kantlaenge, self.kantungen, self.stueck,
                  self.werkstoff, self.art, self.form, self.punkte, self.schenkel, self.tabelle)
        for w in felder:
            w.blockSignals(True)
        try:
            if e.get("werkstoff") in self.werkstoffe:
                self.werkstoff.setCurrentText(e["werkstoff"])
            self.art.setCurrentText(e.get("art") or blech.ZUSCHNITT)
            self.form.setCurrentText(e.get("form") or blech.RECHTECK)
            for w, n in ((self.dicke, "dicke"), (self.laenge, "laenge"), (self.breite, "breite"),
                         (self.eckradius, "eckradius"), (self.kantlaenge, "kantlaenge")):
                w.setValue(sw._z(e.get(n)))
            self.kantungen.setValue(int(sw._z(e.get("kantungen"))))
            self.stueck.setValue(int(sw._z(e.get("stueck")) or 1))
            self.punkte.setText(e.get("punkte") or "")
            self.biegelinien = list(e.get("biegelinien") or self.biegelinien)
            self.schenkel.setRowCount(0)
            self.tabelle.setRowCount(0)
        finally:
            for w in felder:
                w.blockSignals(False)
        for x in e.get("schenkel") or []:
            self.schenkel_neu(x, rechnen_=False)
        for z in e.get("konturen") or []:
            self.kontur_neu(z, rechnen_=False)
        return self.rechnen()

    def skizze_geaendert(self, e):
        """In der Abwicklung gezogen oder gezeichnet: Eingaben übernehmen (Rückgängig wie jede Eingabe)."""
        e = dict(e)
        e["stueck"] = self.stueck.value()
        self.eingaben_setzen(e)
        if self.editor is not None:
            self.editor.aktualisieren()

    def kopf_werte(self):
        return dict(bezeichnung=self.bezeichnung.text().strip() or self.bezeichnung.placeholderText(),
                    artikelnr=self.artikelnr.text().strip() or None,
                    lieferant=self.lieferant.currentText().strip() or zukauf.lieferant_vorgabe("Blechteile"),
                    stueck=self.stueck.value(), muster=self.muster_haken.wert())

    def rechnen(self, *_):
        erg = self._rechnen()
        if getattr(self, "editor", None) is not None:
            self.editor.geaendert()
        return erg

    def _rechnen(self):
        kant = self.art.currentText() == blech.KANTTEIL
        self.stapel.setCurrentIndex(1 if kant else 0)
        poly = self.form.currentText() == blech.POLYGON
        for w in (self.laenge, self.breite, self.eckradius):
            w.setEnabled(not poly)
        self.punkte.setEnabled(poly)
        e = self.eingaben()
        erg = blech.rechnen(e, self.werkstoffe, self.laserdaten, self.einst)
        self.ergebnis = erg
        self.skizze.setzen(e, erg.get("zuschnitt"))
        try:
            netz = blech3d.netz(e, erg.get("zuschnitt"))
        except (ValueError, ZeroDivisionError):
            netz = None
        alt = self.ansicht3d.ansicht.netz is not None
        blick = (self.ansicht3d.ansicht.gier, self.ansicht3d.ansicht.nick, self.ansicht3d.ansicht.zoom)
        self.ansicht3d.setzen(netz, "3D-Ansicht (gefaltet aus den Eingaben)")
        if alt and netz:            # beim Tippen die Blickrichtung behalten
            a = self.ansicht3d.ansicht
            a.gier, a.nick, a.zoom = blick
            a.update()
        if erg.get("zuschnitt") and not self._bez_von_hand:
            self.bezeichnung.setPlaceholderText(blech.bezeichnung_vorschlag(e, erg["zuschnitt"]))
        self.ok_knopf.setEnabled(not erg["fehler"] and bool(erg.get("richtpreis")))
        if erg["fehler"]:
            self.summe.setText("<span style='color:#B42318'>" + "<br>".join(erg["fehler"]) + "</span>")
            return erg
        warn = "".join(f"<br><span style='color:#B26A00'>Hinweis: {h}</span>" for h in erg.get("hinweise") or ())
        farbe = {dfm.FEHLER: "#B42318", dfm.WARNUNG: "#B26A00", dfm.HINWEIS: "#7A5A00"}
        warn += "".join(f"<br><span style='color:{farbe[b.stufe]}'>Prüfung {b.stufe}: {b.zeile()}</span>"
                        for b in self.pruefung(e, erg["zuschnitt"]))
        zs, k = erg["zuschnitt"], erg["kosten"]
        kanten = f", {erg['kantungen']} Kantung{'en' if erg['kantungen'] != 1 else ''}" if erg["kantungen"] else ""
        t = erg.get("tafel")
        tafel = (f"<br>Tafel {t['format'][0]:g} × {t['format'][1]:g}: "
                 f"{t['je_tafel']} Stück je Tafel, Bedarf {zahl_als_text(t['tafeln'], 2)} Tafeln für "
                 f"{self.stueck.value()} Stück, Ausnutzung {zahl_als_text(t['ausnutzung'] * 100, 0)} %") if t else ""
        self.summe.setText(
            f"<b>Richtpreis {_euro(erg['richtpreis'])} je Stück</b> (EK-Vorschlag) · Zuschnitt "
            f"{zahl_als_text(zs['laenge'], 1)} × {zahl_als_text(zs['breite'], 1)} mm{kanten}, "
            f"{zahl_als_text(erg['gewicht'], 2)} kg je Teil, Material mit Verschnitt "
            f"{zahl_als_text(erg['gewicht_tafel'], 2)} kg je Teil{tafel}<br>Schneidweg {zahl_als_text(erg['schneidweg'], 0)} mm, "
            f"{erg['einstiche']} Einstiche, Laserzeit {zahl_als_text(erg['zeit'], 1)} s ({erg['gas']})"
            + (f", K-Faktor {' / '.join(zahl_als_text(x, 2) for x in erg['k_faktoren'])}" if erg["k_faktoren"] else "")
            + " · "
            + " · ".join(f"{n} {_euro(w)}" for n, w in k.items())
            + f" · Summe {_euro(erg['summe'])} + Aufschlag {zahl_als_text(sw._z(self.einst.get('blech_aufschlag')) * 100, 0)} %"
            + warn)
        return erg

    def pruefung(self, e=None, zs=None):
        """Befunde der Fertigungsprüfung (dfm.blech) ohne Kantbarkeit (steht schon bei den Hinweisen)."""
        e = e or self.eingaben()
        if zs is None:
            try:
                zs = blech.zuschnitt(e)
            except ValueError:
                return []
        return dfm.blech(e, zs, self.db.zeilen("pruefregeln") if self.db else None, kantbarkeit=False)

    def dxf_importieren(self, pfad=None, dialog=None):
        """Abwicklung aus einer DXF-Datei übernehmen (3E-9, dxf_import_dialog): ersetzt Außenkontur, Konturen, Art,
        Werkstoff und Dicke. dialog(d) bedient das Importfenster statt exec (Tests). Ergebnis: True = übernommen."""
        from .dxf_import_dialog import DxfImportDialog
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "DXF importieren", str(self.db.einstellung("dxf_ordner") or ""),
                                                  "DXF-Dateien (*.dxf *.DXF)")
            if not pfad:
                return False
            if not self.db.nur_lesen:
                self.db.einstellung_setzen("dxf_ordner", str(Path(pfad).parent))
        d = DxfImportDialog(self, self.db, pfad, vorgabe=dict(werkstoff=self.werkstoff.currentText(),
                                                              dicke=self.dicke.value()), mehrere=False)
        if d.fehler:
            QMessageBox.warning(self, "DXF importieren", d.fehler)
            return False
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or not d.ergebnisse():
            return False
        e, kopf = d.ergebnisse()[0]
        alt = self.eingaben()
        neu = dict(alt, form=blech.RECHTECK, punkte=None, eckradius=0, kantungen=0, biegelinien=[])
        neu.update(e)
        neu["stueck"] = kopf["stueck"] or alt.get("stueck")
        self.eingaben_setzen(neu)
        if kopf.get("bezeichnung") and not self.bezeichnung.text().strip():
            self.bezeichnung.setText(kopf["bezeichnung"])
            self._bez_von_hand = True
        if self.editor is not None:
            self.editor.aktualisieren()
        return True

    def dxf_speichern(self, pfad=None):
        """Abwicklung als DXF speichern (pfad None: Dateidialog). Rückgabe: Hinweise oder None (abgebrochen)."""
        erg = self.rechnen()
        # Fehler der Konturen sperren die Datei (sonst andere Geometrie als im Editor); fehlende Preisdaten nicht
        sperre = [f for f in erg["fehler"] if f.startswith("Kontur ")] if erg.get("zuschnitt") else erg["fehler"]
        if sperre:
            einblendung.melden(self, "Erst die Eingaben korrigieren: " + "; ".join(sperre), fehler=True)
            return None
        e = self.eingaben()
        kopf = self.kopf_werte()
        if pfad is None:
            name = "".join(c if c.isalnum() or c in " -_,." else "_" for c in kopf["artikelnr"] or kopf["bezeichnung"])
            pfad, _ = QFileDialog.getSaveFileName(self, "Abwicklung als DXF speichern",
                                                  f"{name.strip() or 'Blech'}.dxf", "DXF-Datei (*.dxf)")
            if not pfad:
                return None
        text = " ".join(x for x in (kopf["artikelnr"], kopf["bezeichnung"]) if x)
        elem, hinweise = dxf.elemente(e, erg["zuschnitt"], beschriftung=text,
                                      biegelinien=self.db.einstellung("blech_dxf_biegelinien") != "nein")
        try:
            dxf.speichern(pfad, elem, dxf.layer_namen(self.db.einstellung("blech_dxf_layer")))
        except OSError as x:
            QMessageBox.warning(self, "DXF speichern", f"Datei nicht gespeichert: {x}")
            return None
        if hinweise and not getattr(self, "stumm", False):
            einblendung.melden(self, "Gespeichert. Bitte prüfen:\n– " + "\n– ".join(hinweise))
        return hinweise

    def step_speichern(self, pfad=None):
        """Blech als STEP mit echtem Volumenkörper (step_export, Plan 3D-Editor 3E-8, gekantet 3E-13): Außen- und
        Innenkonturen mit echten Bögen, Gravuren als Rille, Kantteile gefaltet. Ohne pfad: Dateidialog im Ordner des
        Angebots."""
        from . import step_export
        erg = self.rechnen()
        sperre = [f for f in erg["fehler"] if f.startswith("Kontur ")] if erg.get("zuschnitt") else erg["fehler"]
        if sperre:
            einblendung.melden(self, "Erst die Eingaben korrigieren: " + "; ".join(sperre), fehler=True)
            return None
        kopf = self.kopf_werte()
        name = kopf["artikelnr"] or kopf["bezeichnung"] or "Blech"
        try:
            plan = step_export.blech_teil(self.eingaben(), erg["zuschnitt"], name)
        except ValueError as x:
            self.step_ergebnis = dict(ok=False, fehler=str(x), teile=[])
            if not getattr(self, "stumm", False):
                einblendung.melden(self, str(x))
            return None
        netz = None
        db, pid = getattr(self, "db", None), (getattr(self, "p", None) or {}).get("id")
        if db is not None and pid and hasattr(db, "netz"):      # Prüfung gegen die Mutter-STEP
            from .ansicht3d import entpacken
            netz = entpacken(db.netz(pid)) or None
        return step_export.speichern_dialog(self, plan, name, pfad, netz=netz)

    def zeichnung_pdf(self, pfad=None):
        """Zeichnung als PDF (zeichnung.blech_pdf). Ohne pfad: in die Ablage des Angebots schreiben und öffnen (ohne
        Angebot: Dateidialog). Ergebnis: Pfad oder None."""
        from . import zeichnung
        erg = self.rechnen()
        if not erg.get("zuschnitt"):
            einblendung.melden(self, "Erst die Maße eingeben: " + "; ".join(erg["fehler"]), fehler=True)
            return None
        seite = self.parent()
        einst = dict(getattr(seite, "einst", None) or {})
        if not einst and self.db is not None:
            einst = {n: self.db.einstellung(n) for n in ("briefkopf_1", "logo")}

        def schreiben(ziel):
            zeichnung.blech_pdf(ziel, getattr(seite, "kopf", None) or {}, self.kopf_werte(), self.eingaben(), erg,
                                einst)
        if pfad is not None:
            schreiben(pfad)
            return pfad
        kopf = self.kopf_werte()
        name = f"Zeichnung {kopf['artikelnr'] or kopf['bezeichnung'] or 'Blech'}".strip()
        if hasattr(seite, "_ziel"):
            return seite._schreiben("Zeichnung", seite._ziel(name, ".pdf"), schreiben)
        pfad, _ = QFileDialog.getSaveFileName(self, "Zeichnung als PDF speichern", f"{name}.pdf", "PDF (*.pdf)")
        if not pfad:
            return None
        schreiben(pfad)
        return pfad

    def accept(self):
        if self.rechnen()["fehler"]:
            return
        super().accept()

