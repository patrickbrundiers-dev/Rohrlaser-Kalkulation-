"""Fenster 'Blech-Editor': Blech- oder Kantteil beschreiben (Werkstoff, Dicke, Zuschnitt bzw. Schenkel mit
Biegungen, Innenkonturen), Abwicklung und Seitenansicht als Skizze, darunter das gefaltete Teil in 3D (blech3d),
Richtpreis je Stück als EK-Vorschlag des Zukaufteils (Rechnung in blech.py). Schreibt nichts in die
Rohrlaser-Daten."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import blech, blech3d, dfm, dxf, schneidweg as sw, zukauf
from .ansicht3d import Ansicht3DMitKnoepfen
from .leiste import UmbruchLeiste
from .teile_editor import EditorRahmen
from .stammdaten import zahl_als_text, zahl_aus_text

FARBE_BLECH, FARBE_LINIE, FARBE_KONTUR, FARBE_BIEGUNG = "#EAF1F8", "#1F4E78", "#B42318", "#2E7D32"
FARBE_MARKIERT = "#2E75B6"      # gewähltes Merkmal (Teile-Editor), wie in der 3D-Ansicht
KONTUR_SPALTEN = ("Art", "Anzahl", "Maß 1", "Maß 2", "Maß 3", "Mitte x [mm]", "Mitte y [mm]")
SCHENKEL_SPALTEN = ("Schenkel außen [mm]", "Biegewinkel danach [°]", "Innenradius [mm]")
# Vorlagen für Kantteile: [(Schenkel außen, Biegewinkel danach)]; Radius leer = Blechdicke
VORLAGEN = {"Winkel": [(50, 90), (50, 0)], "U-Profil": [(30, 90), (60, 90), (30, 0)],
            "Z-Profil": [(30, 90), (60, -90), (30, 0)], "Hutprofil": [(20, -90), (30, 90), (50, 90), (30, -90),
                                                                     (20, 0)]}


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


class BlechSkizze(QWidget):
    """Abwicklung (Zuschnitt mit Biegelinien und Innenkonturen) und beim Kantteil die Seitenansicht. mini=True:
    nur der Zuschnitt ohne Beschriftung und Rand (Vorschaubild der Positionsliste, siehe vorschau.py)."""

    def __init__(self, mini=False):
        super().__init__()
        self.eingaben, self.zuschnitt, self.mini = {}, None, mini
        self.markiert = None            # Teile-Editor: gewähltes Merkmal ('kontur:3', 'biegung:0') blau
        self.setMinimumHeight(0 if mini else 260)

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
            p.fillRect(self.rect(), QColor("white"))
        zs = self.zuschnitt
        if not zs:
            p.setPen(QColor("#5F6B7A"))
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

        def pkt(x, y):          # mm (y nach oben) -> Pixel
            return QPointF(x0 + x * m, y0 + (br - y) * m)

        p.setFont(QFont(self.font().family(), 8))
        p.setPen(QPen(QColor(FARBE_LINIE), 1.0 if self.mini else 1.6))
        p.setBrush(QColor(FARBE_BLECH))
        minx = miny = 0.0
        if zs.get("punkte"):
            minx, miny = min(x for x, _ in zs["punkte"]), min(y for _, y in zs["punkte"])
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
            p.setPen(QPen(QColor(FARBE_MARKIERT), 3.0) if self.markiert == f"biegung:{i - 1}" else
                     QPen(QColor(FARBE_BIEGUNG), 1.2, Qt.DashLine))
            a, b = pkt(0, lage), pkt(lg, lage)
            p.drawLine(a, b)
            if self.mini:
                continue
            p.setPen(QColor(FARBE_BIEGUNG))
            p.drawText(QPointF(b.x() + 4, b.y() + 4),
                       f"B{i} {zahl_als_text(abs(winkel), 0)}° {'↑' if winkel > 0 else '↓'} r{zahl_als_text(radius, 1)}")
        # mehrachsig gekantet (STEP-Import): Biegelinien in beliebiger Richtung
        if self.eingaben.get("art") != blech.KANTTEIL:
            for i, x in enumerate(self.eingaben.get("biegelinien") or (), 1):
                try:
                    (x1, y1), (x2, y2) = x["punkte"]
                except (TypeError, ValueError, KeyError):
                    continue
                p.setPen(QPen(QColor(FARBE_MARKIERT), 3.0) if self.markiert == f"biegung:{i - 1}" else
                         QPen(QColor(FARBE_BIEGUNG), 1.2, Qt.DashLine))
                a, b = pkt(x1 - minx, y1 - miny), pkt(x2 - minx, y2 - miny)
                p.drawLine(a, b)
                if not self.mini:
                    p.setPen(QColor(FARBE_BIEGUNG))
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
            p.setPen(QPen(QColor(FARBE_MARKIERT), 3.0) if self.markiert == f"kontur:{zeile[id(z)]}" else
                     QPen(QColor(FARBE_KONTUR), 1.2))
            self._kontur(p, z, pkt(cx, cy), m)
        if self.mini:
            return
        # Maße
        p.setPen(QColor("#333333"))
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

    def _kontur(self, p, z, c, m):
        art = z.get("art")
        if art in (sw.BOHRUNG, sw.SENKUNG):
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
        p.setPen(QColor("#333333"))
        p.drawText(QPointF(feld.x(), feld.y() - 8), "Seitenansicht (Außenmaße)")
        p.setPen(QPen(QColor(FARBE_LINIE), min(max(2.0, sw._z(self.eingaben.get("dicke")) * m), 8.0)))
        for (x1, y1), (x2, y2) in zip(pk, pk[1:]):
            p.drawLine(QPointF(ox + x1 * m, oy - y1 * m), QPointF(ox + x2 * m, oy - y2 * m))
        p.setPen(QColor("#333333"))
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
        self.stueck = QSpinBox()
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
        self.kantungen = QSpinBox()
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
        for text, ziel in (("+ Schenkel", lambda: self.schenkel_neu()), ("Schenkel entfernen", self._schenkel_weg)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            zeile.addWidget(b)
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
                                "Eckradius; Polygon Eckpunkte in Maß 1; sonstige Kontur Schnittlänge, Hüllmaß. "
                                "Mitte x/y in der Abwicklung (leer = nur für die Skizze verteilt)")
        self.tabelle.currentCellChanged.connect(lambda r, *_: self._spalten_erklaeren(r))
        bl.addWidget(self.tabelle, 1)
        knoepfe = UmbruchLeiste()           # bei schmaler Spalte rückt 'Markierte entfernen' in eine zweite Zeile
        for art in (sw.BOHRUNG, sw.LANGLOCH, sw.RECHTECK, sw.POLYGON, sw.SONSTIGE):
            b = QPushButton(f"+ {art}")
            b.clicked.connect(lambda _=False, art=art: self.kontur_neu(dict(art=art, anzahl=1)))
            knoepfe.links_layout.addWidget(b)
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(self._kontur_weg)
        knoepfe.rechts_layout.addWidget(weg)
        bl.addWidget(knoepfe)
        lay.addWidget(box, 3)
        for z in e.get("konturen") or []:
            self.kontur_neu(z, rechnen_=False)

        rechts = QWidget()
        lay = QVBoxLayout(rechts)
        lay.setContentsMargins(6, 0, 0, 0)
        self.teiler.addWidget(rechts)
        self.skizze = BlechSkizze()
        self.ansicht3d = Ansicht3DMitKnoepfen()
        self.ansicht3d.setToolTip("Das gefaltete Teil aus den Eingaben (zur Anschauung): Innenkonturen rot, "
                                  "Biegelinien grün")
        bilder = QSplitter(Qt.Vertical)
        bilder.setChildrenCollapsible(False)
        bilder.addWidget(self.skizze)
        bilder.addWidget(self.ansicht3d)
        lay.addWidget(bilder, 1)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        self.summe.setTextFormat(Qt.RichText)
        lay.addWidget(self.summe)
        hinweis = QLabel("Richtpreis zur Kostenschätzung vorab (EK-Vorschlag). Werkstoffe, Blechlaser-Richtwerte und "
                         "Sätze stehen unter Einstellungen; die Rohrlaser-Daten bleiben unverändert.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #5F6B7A;")
        lay.addWidget(hinweis)
        lay = haupt
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_knopf = self.knoepfe.button(QDialogButtonBox.Ok)
        self.ok_knopf.setText("Als Zukaufteil anlegen" if neu else "Richtpreis übernehmen")
        self.dxf_knopf = self.knoepfe.addButton("DXF speichern …", QDialogButtonBox.ActionRole)
        self.dxf_knopf.setToolTip("Abwicklung als DXF (R12) mit Layern für Außenkontur, Innenkonturen, Biegelinien "
                                  "und Beschriftung, z. B. für den Blechlaser oder den Lieferanten")
        self.dxf_knopf.clicked.connect(lambda: self.dxf_speichern())
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
        w = QDoubleSpinBox()
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
        art.currentTextChanged.connect(self.rechnen)
        self.tabelle.setCellWidget(r, 0, art)
        masse = [k for k, _ in sw.MASSE.get(z.get("art"), ())]
        werte = [z.get("anzahl", 1)] + [z.get(k) for k in masse] + [None] * (3 - len(masse)) + [z.get("x"), z.get("y")]
        for c, v in enumerate(werte, 1):
            self.tabelle.setItem(r, c, QTableWidgetItem(_feld(v)))
        self.tabelle.blockSignals(False)
        if rechnen_:
            self.rechnen()

    def _spalten_erklaeren(self, zeile):
        """Überschriften Maß 1–3 nach der Art der markierten Zeile (z. B. Langloch: Länge l, Breite b)."""
        art = self.tabelle.cellWidget(zeile, 0).currentText() if 0 <= zeile < self.tabelle.rowCount() else None
        titel = [f"{t} [mm]" if k != "punkte" else t for k, t in sw.MASSE.get(art, ())]
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
            for c, (k, _) in enumerate(sw.MASSE.get(art, ()), 2):
                t = self._text(self.tabelle, r, c)
                z[k] = t.strip() if k == "punkte" else _zahl_text(t)
            z["x"], z["y"] = _zahl_text(self._text(self.tabelle, r, 5)), _zahl_text(self._text(self.tabelle, r, 6))
            if art == sw.LANGLOCH and getattr(self.tabelle.cellWidget(r, 0), "quer", False):
                z["quer"] = True
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

    def kopf_werte(self):
        return dict(bezeichnung=self.bezeichnung.text().strip() or self.bezeichnung.placeholderText(),
                    artikelnr=self.artikelnr.text().strip() or None,
                    lieferant=self.lieferant.currentText().strip() or zukauf.lieferant_vorgabe("Blechteile"),
                    stueck=self.stueck.value())

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

    def dxf_speichern(self, pfad=None):
        """Abwicklung als DXF speichern (pfad None: Dateidialog). Rückgabe: Hinweise oder None (abgebrochen)."""
        erg = self.rechnen()
        # Fehler der Konturen sperren die Datei (sonst andere Geometrie als im Editor); fehlende Preisdaten nicht
        sperre = [f for f in erg["fehler"] if f.startswith("Kontur ")] if erg.get("zuschnitt") else erg["fehler"]
        if sperre:
            QMessageBox.warning(self, "DXF speichern", "Erst die Eingaben korrigieren: " + "; ".join(sperre))
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
            QMessageBox.information(self, "DXF gespeichert", "Gespeichert. Bitte prüfen:\n– " + "\n– ".join(hinweise))
        return hinweise

    def accept(self):
        if self.rechnen()["fehler"]:
            return
        super().accept()

