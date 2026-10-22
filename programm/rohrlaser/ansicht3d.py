"""3D-Ansicht eines Rohrteils aus dem STEP-Import (Dreiecksnetz der STEP-Messung).

Gezeichnet wird ohne OpenGL mit QPainter, damit die Ansicht auf jedem Rechner läuft, auch über Remote-Desktop.
Rückseiten fallen weg; dann genügen zwei Schichten: zuerst die Innenwand, darüber alle anderen Flächen, von hinten
nach vorn sortiert (so überdecken sich auch bei offenen Profilen wie U oder L die Schenkel richtig). Bei Rohren ist
die Innenwand nur durch Öffnungen zu sehen, die in der Außenhaut ausgespart sind. Zuletzt die Schnittkonturen auf
der Außenhaut als kräftige Linien. Farben nach Art der Fläche.

Netz: {p: [x, y, z, …], t: {Art: [i, j, k, …]}, l: {Art: [[x, y, z, …], …]}} mit Rohrachse = Z ab 0 (siehe
step_messung/step_geometrie.py). Gespeichert wird es zlib-komprimiert je Position. Neuere Messungen haben dazu
lage = [Ende A, Rohrachse, X-Richtung] in der STEP-Datei; damit setzt baugruppe() die Teile einer Datei zusammen.
"""
import json
import math
import zlib

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

ARTEN = (  # (Art, Bezeichnung, Farbe Fläche, Farbe Linie)
    ("A", "Außenwand", "#B9C3CD", None),
    ("I", "Innenwand", "#8A96A3", None),
    ("EA", "Anfangsschnitt", "#F28E2B", "#D9660A"),
    ("EB", "Endschnitt", "#B07AA1", "#8E4F80"),
    ("K", "Innenkonturen", "#E15759", "#C00000"),
    ("G", "Gravur", "#59A14F", "#2E7D32"),
    ("AN", "Anbauteile", "#E8C77A", None),            # aufgeschweißte Teile (nicht gelasert)
    ("GA", "Gravur Anbauteile", "#59A14F", "#00897B"),
    ("S", "gewählte Teile", "#2E75B6", None),       # nur in der Baugruppen-Ansicht
    ("N", "nicht übernehmbar", "#FF00FF", None),    # nicht messbare Teile (Rohnetz in Dateilage), magenta
)
FARBE = {a: QColor(f) for a, _, f, _ in ARTEN}
REIHE = [a for a, *_ in ARTEN]          # Reihenfolge der Legende
# Baugruppen-Ansicht: je Teil (Zeile gleicher Teile) eine Farbe, ohne Eintrag in der Legende
TEILFARBEN = ("#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#76B7B2", "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F",
              "#BAB0AC", "#2F4B7C", "#A05195")
FARBE.update({f"F{n}": QColor(f) for n, f in enumerate(TEILFARBEN)})
FARBE["X"] = QColor("#D9DDE2")         # nicht gewählte Teile, wenn andere hervorgehoben sind
LINIE = {a: QColor(l or f) for a, _, f, l in ARTEN}
HINTERGRUND = QColor("#FFFFFF")
# Vorschau bei Anbauteilen: Original = Rohr mit Anbauteilen, Rohrgeometrie = nur was der Laser bearbeitet,
# Gravurkonturen = Rohr mit allen Gravurlinien (ohne Schnittlinien)
MODI = ("Original", "Rohrgeometrie", "Gravurkonturen")


def gefiltert(netz, modus):
    """Netz für eine Vorschau (MODI); Original gibt das Netz unverändert zurück."""
    if not netz or modus not in MODI[1:]:
        return netz
    out = dict(netz)
    out["t"] = {a: i for a, i in (netz.get("t") or {}).items() if a != "AN"}
    out["l"] = {a: z for a, z in (netz.get("l") or {}).items()
                if (a in ("G", "GA") if modus == "Gravurkonturen" else a != "GA")}
    return out


def mit_anbau(netz):
    return bool(netz) and ("AN" in (netz.get("t") or {}) or "GA" in (netz.get("l") or {}))


def packen(netz):
    """Netz (dict) -> Bytes für die Datenbank."""
    return zlib.compress(json.dumps(netz, separators=(",", ":")).encode("utf-8"), 6)


def entpacken(daten):
    if not daten:
        return None
    try:
        return json.loads(zlib.decompress(daten).decode("utf-8"))
    except (zlib.error, ValueError):
        return None


def baugruppe(netze, hervor=(), farben=None, fehlend=()):
    """Teile einer Baugruppe in ihrer Einbaulage zu einem Netz zusammensetzen. netze: Liste von Netzen (dict oder
    gepackt); farben: je Netz eine Nummer, gleiche Nummer = gleiche Farbe (z. B. gleiche Teile), sonst je Netz eine;
    hervor: Nummern in netze, die als 'gewählte Teile' (Art S) blau, alle anderen hellgrau gefärbt werden;
    fehlend: Nummern der nicht übernehmbaren Teile, immer magenta (Art N), außer sie sind gewählt. Ohne Innenwände und
    Schnittlinien (bei vielen Teilen verdeckt bzw. zu unruhig). Ergebnis: (Netz oder None, Anzahl Teile ohne
    Einbaulage, z. B. aus einer älteren Messung)."""
    punkte, dreiecke, ohne = [], {}, 0
    for nr, netz in enumerate(netze):
        if isinstance(netz, (bytes, bytearray, memoryview)):
            netz = entpacken(bytes(netz))
        lage = (netz or {}).get("lage")
        if not netz or not netz.get("p") or not lage or len(lage) != 9:
            ohne += 1
            continue
        o, z, x = lage[0:3], lage[3:6], lage[6:9]
        y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
        p = netz["p"]
        basis = len(punkte) // 3
        for i in range(0, len(p) - 2, 3):
            a, b, c = p[i], p[i + 1], p[i + 2]
            punkte += [round(o[k] + a * x[k] + b * y[k] + c * z[k], 2) for k in range(3)]
        for art, idx in (netz.get("t") or {}).items():
            if art == "I":
                continue
            art = "S" if nr in hervor else "N" if nr in fehlend else "X" if hervor else \
                f"F{(farben[nr] if farben else nr) % len(TEILFARBEN)}"
            dreiecke.setdefault(art, []).extend(basis + i for i in idx)
    return (dict(p=punkte, t=dreiecke, l={}) if punkte else None), ohne


class Modell:
    """Aufbereitetes Netz: Punkte, Dreiecke (i, j, k, Art, Normale), Liniensegmente (a, b, Art, Normale)."""

    def __init__(self, netz):
        p = netz.get("p") or []
        self.punkte = [(p[i], p[i + 1], p[i + 2]) for i in range(0, len(p) - 2, 3)]
        xs, ys, zs = ([q[k] for q in self.punkte] or [0] for k in range(3))
        self.min = (min(xs), min(ys), min(zs))
        self.max = (max(xs), max(ys), max(zs))
        self.mitte = tuple((a + b) / 2 for a, b in zip(self.min, self.max))
        self.groesse = max(1e-6, math.dist(self.min, self.max))
        laenge = self.max[2] - self.min[2]
        self.dreiecke = []
        for art, idx in (netz.get("t") or {}).items():
            for n in range(0, len(idx) - 2, 3):
                self._dreieck(idx[n], idx[n + 1], idx[n + 2], art)
        self.linien = []
        for art, zuege in (netz.get("l") or {}).items():
            for zug in zuege:
                pk = [(zug[i], zug[i + 1], zug[i + 2]) for i in range(0, len(zug) - 2, 3)]
                for a, b in zip(pk, pk[1:]):
                    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                    r = math.hypot(m[0], m[1]) or 1.0
                    self.linien.append((a, b, art, (m[0] / r, m[1] / r, 0.0)))
        self.arten = sorted({d[3] for d in self.dreiecke} | {l[2] for l in self.linien},
                            key=lambda a: REIHE.index(a) if a in REIHE else 99)
        self.laenge = laenge

    def _dreieck(self, i, j, k, art):
        a, b, c = self.punkte[i], self.punkte[j], self.punkte[k]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        betrag = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        if betrag < 1e-12:
            return
        self.dreiecke.append((i, j, k, art, (n[0] / betrag, n[1] / betrag, n[2] / betrag)))


def _drehung(gier, nick):
    """Drehmatrix: erst um die Hochachse (gier), dann kippen (nick). Bildschirm: x rechts, y oben, z zum Betrachter."""
    cg, sg, cn, sn = math.cos(gier), math.sin(gier), math.cos(nick), math.sin(nick)
    # Rohrachse Z liegt in der Grundstellung waagerecht (nach rechts): Modell (x, y, z) -> (z, y, -x)
    basis = ((0, 0, 1), (0, 1, 0), (-1, 0, 0))
    gm = ((cg, 0, sg), (0, 1, 0), (-sg, 0, cg))
    nm = ((1, 0, 0), (0, cn, -sn), (0, sn, cn))

    def mal(a, b):
        return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))
    return mal(nm, mal(gm, basis))


def zeichnen(p, modell, breite, hoehe, gier, nick, zoom=1.0, verschiebung=(0.0, 0.0), linien=True):
    """Modell in ein Rechteck (0, 0, breite, hoehe) zeichnen."""
    m = _drehung(gier, nick)
    cx, cy, cz = modell.mitte
    proj = []
    for x, y, z in modell.punkte:
        x, y, z = x - cx, y - cy, z - cz
        proj.append((m[0][0] * x + m[0][1] * y + m[0][2] * z, m[1][0] * x + m[1][1] * y + m[1][2] * z,
                     m[2][0] * x + m[2][1] * y + m[2][2] * z))
    massstab = zoom * 0.92 * min(breite, hoehe * 3) / modell.groesse
    if proj:
        bx = max(abs(q[0]) for q in proj) * 2 or 1
        by = max(abs(q[1]) for q in proj) * 2 or 1
        massstab = zoom * 0.9 * min(breite / bx, hoehe / by)
    ox, oy = breite / 2 + verschiebung[0], hoehe / 2 + verschiebung[1]
    licht = (-0.35, 0.45, 0.82)
    liste = []
    for i, j, k, art, n in modell.dreiecke:
        nz = m[2][0] * n[0] + m[2][1] * n[1] + m[2][2] * n[2]
        if nz <= 0:
            continue                     # Rückseite
        nx = m[0][0] * n[0] + m[0][1] * n[1] + m[0][2] * n[2]
        ny = m[1][0] * n[0] + m[1][1] * n[1] + m[1][2] * n[2]
        hell = 0.42 + 0.58 * max(0.0, nx * licht[0] + ny * licht[1] + nz * licht[2])
        a, b, c = proj[i], proj[j], proj[k]
        liste.append((0 if art == "I" else 1, (a[2] + b[2] + c[2]) / 3, (a, b, c), art, hell))
    if linien:
        for a, b, art, n in modell.linien:
            nz = m[2][0] * n[0] + m[2][1] * n[1]
            if nz < 0.0:
                continue
            ra = (m[0][0] * (a[0] - cx) + m[0][1] * (a[1] - cy) + m[0][2] * (a[2] - cz),
                  m[1][0] * (a[0] - cx) + m[1][1] * (a[1] - cy) + m[1][2] * (a[2] - cz),
                  m[2][0] * (a[0] - cx) + m[2][1] * (a[1] - cy) + m[2][2] * (a[2] - cz))
            rb = (m[0][0] * (b[0] - cx) + m[0][1] * (b[1] - cy) + m[0][2] * (b[2] - cz),
                  m[1][0] * (b[0] - cx) + m[1][1] * (b[1] - cy) + m[1][2] * (b[2] - cz),
                  m[2][0] * (b[0] - cx) + m[2][1] * (b[1] - cy) + m[2][2] * (b[2] - cz))
            liste.append((2, (ra[2] + rb[2]) / 2, (ra, rb), art, 1.0))
    liste.sort(key=lambda e: (e[0], e[1]))
    p.setRenderHint(QPainter.Antialiasing, True)
    stift_linie = {a: QPen(LINIE.get(a, QColor("#C00000")), 2.2, Qt.SolidLine, Qt.RoundCap) for a in LINIE}
    for schicht, _, punkte, art, hell in liste:
        poly = [QPointF(ox + q[0] * massstab, oy - q[1] * massstab) for q in punkte]
        if schicht == 2:
            p.setPen(stift_linie.get(art, stift_linie["K"]))
            p.drawLine(poly[0], poly[1])
            continue
        f = FARBE.get(art, FARBE["K"])
        farbe = QColor(int(f.red() * hell), int(f.green() * hell), int(f.blue() * hell))
        p.setPen(QPen(farbe, 0.8))
        p.setBrush(QBrush(farbe))
        p.drawPolygon(QPolygonF(poly))


def vorschaubild(netz, breite=96, hoehe=30, dpr=1.0):
    """Kleines Bild des Teils (schräg von vorn oben) für die Positionsliste, oder None."""
    if not netz or not netz.get("p"):
        return None
    bild = QPixmap(int(breite * dpr), int(hoehe * dpr))
    bild.setDevicePixelRatio(dpr)
    bild.fill(Qt.transparent)
    p = QPainter(bild)
    zeichnen(p, netz if isinstance(netz, Modell) else Modell(netz), breite, hoehe, -0.45, 0.45, linien=True)
    p.end()
    return bild


class Ansicht3D(QWidget):
    """Drehbare Ansicht: linke Maustaste drehen, rechte oder mittlere verschieben, Mausrad zoomen,
    Doppelklick = Ausgangsansicht."""
    GRUND = (-0.45, 0.45)
    gedreht = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)
        self.modell, self.titel, self.netz, self.modus = None, "", None, MODI[0]
        self.zuruecksetzen()

    def setzen(self, netz, titel=""):
        """netz: dict, Bytes aus der Datenbank oder None (= keine 3D-Daten)."""
        if isinstance(netz, (bytes, bytearray, memoryview)):
            netz = entpacken(bytes(netz))
        self.netz = netz if netz and netz.get("p") else None
        self.modell = Modell(gefiltert(self.netz, self.modus)) if self.netz else None
        self.titel = titel
        self.zuruecksetzen()

    def modus_setzen(self, modus):
        """Vorschau Original / Rohrgeometrie / Gravurkonturen (MODI); Blickrichtung bleibt."""
        self.modus = modus
        if self.netz:
            self.modell = Modell(gefiltert(self.netz, modus))
        self.update()

    def zuruecksetzen(self):
        self.gier, self.nick = self.GRUND
        self.zoom, self.versatz, self._maus = 1.0, (0.0, 0.0), None
        self.update()

    def ansicht(self, gier, nick):
        self.gier, self.nick, self.zoom, self.versatz = gier, nick, 1.0, (0.0, 0.0)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), HINTERGRUND)
        if self.modell is None:
            p.setPen(QColor("#7F7F7F"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Keine 3D-Daten.\nDie 3D-Ansicht gibt es für Teile, die per STEP-Import übernommen wurden.")
            return
        zeichnen(p, self.modell, self.width(), self.height(), self.gier, self.nick, self.zoom, self.versatz)
        p.setRenderHint(QPainter.Antialiasing, False)
        y = 8
        p.setPen(QColor("#202020"))
        if self.titel:
            p.drawText(QRectF(10, y, self.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, self.titel)
            y += 20
        for art, text, farbe, linie in ARTEN:
            if art not in self.modell.arten:
                continue
            p.fillRect(QRectF(10, y + 3, 12, 12), QColor(linie or farbe))
            p.setPen(QColor("#202020"))
            p.drawText(QRectF(28, y, 200, 18), Qt.AlignLeft | Qt.AlignVCenter, text)
            y += 18
        p.setPen(QColor("#7F7F7F"))
        p.drawText(QRectF(10, self.height() - 22, self.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   "Linke Maustaste drehen · rechte verschieben · Mausrad zoomen · Doppelklick Ausgangsansicht")

    def mousePressEvent(self, e):
        self._maus = (e.position(), e.button())

    def mouseMoveEvent(self, e):
        if not self._maus:
            return
        alt, knopf = self._maus
        d = e.position() - alt
        if knopf == Qt.LeftButton:
            self.gier += d.x() * 0.012
            self.nick = max(-1.55, min(1.55, self.nick + d.y() * 0.012))
        else:
            self.versatz = (self.versatz[0] + d.x(), self.versatz[1] + d.y())
        self._maus = (e.position(), knopf)
        self.update()
        self.gedreht.emit()

    def mouseReleaseEvent(self, _):
        self._maus = None

    def mouseDoubleClickEvent(self, _):
        self.zuruecksetzen()

    def wheelEvent(self, e):
        self.zoom = max(0.2, min(40.0, self.zoom * (1.15 ** (e.angleDelta().y() / 120))))
        self.update()


class Ansicht3DMitKnoepfen(QWidget):
    """Ansicht mit Knöpfen für feste Blickrichtungen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ansicht = Ansicht3D()
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.knoepfe = QWidget()
        leiste = QHBoxLayout(self.knoepfe)
        leiste.setContentsMargins(0, 0, 0, 0)
        for text, (g, n) in (("Schräg", Ansicht3D.GRUND), ("Vorn", (0.0, 0.0)), ("Oben", (0.0, 1.5)),
                             ("Stirnseite", (-1.5708, 0.0))):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, g=g, n=n: self.ansicht.ansicht(g, n))
            leiste.addWidget(b)
        leiste.addStretch(1)
        # Vorschau bei Anbauteilen (nur sichtbar, wenn das Teil welche hat)
        self.modi = QWidget()
        ml = QHBoxLayout(self.modi)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        self.modus_knoepfe = QButtonGroup(self.modi)
        for text, tipp in zip(MODI, ("Rohr mit Anbauteilen (sandfarben)", "Nur die Rohrlaser-Geometrie ohne Anbauteile",
                                     "Rohr mit allen Gravurlinien, ohne Schnittlinien")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setChecked(text == MODI[0])
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, t=text: self.ansicht.modus_setzen(t))
            self.modus_knoepfe.addButton(b)
            ml.addWidget(b)
        self.modi.setVisible(False)
        leiste.addWidget(self.modi)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ansicht, 1)
        lay.addWidget(self.knoepfe)
        lay.addWidget(self.info)

    def setzen(self, netz, titel="", info=""):
        self.ansicht.setzen(netz, titel)
        self.modi.setVisible(mit_anbau(self.ansicht.netz))
        self.info.setText(info)

    def modus_setzen(self, modus):
        """Vorschau wählen wie mit den Knöpfen (Tests, Bildschirmfotos)."""
        for b in self.modus_knoepfe.buttons():
            b.setChecked(b.text() == modus)
        self.ansicht.modus_setzen(modus)
