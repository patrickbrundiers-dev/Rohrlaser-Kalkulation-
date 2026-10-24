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
import sys
import zlib

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
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
    ("BL", "Blech", "#C9D6E3", None),               # Blech-Editor (blech3d)
    ("B", "Biegelinien", "#2E7D32", "#2E7D32"),
    ("SN", "Schweißnähte", "#E8590C", "#E8590C"),        # Baugruppen-Ansicht: Nahtgruppen
    ("SV", "Nahtvorschläge (STEP)", "#F2B880", "#E9A15C"),  # noch nicht übernommene Nahtkandidaten
    ("SH", "gewählte Naht", "#C00000", "#C00000"),
)
FARBE = {a: QColor(f) for a, _, f, _ in ARTEN}
REIHE = [a for a, *_ in ARTEN]          # Reihenfolge der Legende
# Darstellung (Einstellung 'ansicht_3d', je Arbeitsplatz): Automatisch = OpenGL, wenn möglich und nicht über
# Remote-Desktop; Software = immer QPainter; OpenGL = OpenGL, wenn möglich (Rückfall auf QPainter)
RENDERER = ("Automatisch", "Software", "OpenGL")
_renderer = RENDERER[0]
_gl_fehler = None       # OpenGL ist in diesem Programmlauf schon einmal gescheitert: Grund
GROB_DREIECKE = 10000   # beim Drehen/Zoomen höchstens so viele Dreiecke zeichnen (grobe Stufe, Modell.grob)
# Baugruppen-Ansicht: je Teil (Zeile gleicher Teile) eine Farbe, ohne Eintrag in der Legende
TEILFARBEN = ("#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#76B7B2", "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F",
              "#BAB0AC", "#2F4B7C", "#A05195")
FARBE.update({f"F{n}": QColor(f) for n, f in enumerate(TEILFARBEN)})
FARBE["X"] = QColor("#D9DDE2")         # nicht gewählte Teile, wenn andere hervorgehoben sind
LINIE = {a: QColor(l or f) for a, _, f, l in ARTEN}
NAEHTE, NAHT_BREITE = ("SN", "SV", "SH"), 4.5     # Schweißnähte dicker und immer sichtbar (Normale 0)
HINTERGRUND = QColor("#FFFFFF")
MARKIERT = QColor("#2E75B6")        # Teile-Editor: gewähltes Merkmal
MESSEN = QColor("#B42318")
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


def _zahl(w):
    return f"{w:.1f}".replace(".", ",")


def renderer_setzen(wert):
    """Darstellung für neu geöffnete 3D-Ansichten (RENDERER; Unbekanntes = Automatisch)."""
    global _renderer
    _renderer = wert if wert in RENDERER else RENDERER[0]


def _remote_desktop():
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetSystemMetrics(0x1000))       # SM_REMOTESESSION
    except (OSError, AttributeError):
        return False


def renderer_waehlen():
    """("OpenGL" | "Software", Grund) für eine neue Ansicht nach Einstellung, Rechner und bisherigen Fehlern."""
    if _renderer == "Software":
        return "Software", "Einstellung Software"
    if _gl_fehler:
        return "Software", f"OpenGL gescheitert: {_gl_fehler}"
    if _renderer == "Automatisch" and _remote_desktop():
        return "Software", "Remote-Desktop"
    try:
        from .ansicht3d_gl import gl_moeglich
    except ImportError as e:            # PySide6 ohne OpenGL-Module
        return "Software", f"OpenGL fehlt: {e}"
    ok, grund = gl_moeglich()
    return ("OpenGL", grund) if ok else ("Software", grund)


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
        self.linien_id = []                     # je Liniensegment: Merkmal (netz 'li', Teile-Editor) oder None
        normalen = netz.get("ln") or {}         # Normale je Linienzug (Blech), sonst radial zur Rohrachse
        kennung = netz.get("li") or {}
        for art, zuege in (netz.get("l") or {}).items():
            for nr, zug in enumerate(zuege):
                pk = [(zug[i], zug[i + 1], zug[i + 2]) for i in range(0, len(zug) - 2, 3)]
                n = (normalen.get(art) or [])[nr] if nr < len(normalen.get(art) or []) else None
                kn = (kennung.get(art) or [])[nr] if nr < len(kennung.get(art) or []) else None
                self.linien_id += [kn] * max(len(pk) - 1, 0)
                for a, b in zip(pk, pk[1:]):
                    if n is None:
                        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                        r = math.hypot(m[0], m[1]) or 1.0
                        self.linien.append((a, b, art, (m[0] / r, m[1] / r, 0.0)))
                    else:
                        self.linien.append((a, b, art, tuple(n)))
        self.arten = sorted({d[3] for d in self.dreiecke} | {l[2] for l in self.linien},
                            key=lambda a: REIHE.index(a) if a in REIHE else 99)
        self.laenge = laenge
        self._grob = None

    def grob(self):
        """Grobe Stufe für große Netze (Baugruppen) beim Drehen und Zoomen: nur die GROB_DREIECKE größten
        Dreiecke (lange Rohrwände, Blechflächen; kleine Rundungen, Bohrungen und Fasen fallen weg), ohne Linien.
        Punkte, Mitte und Größe bleiben, damit das Bild beim Umschalten nicht springt. Kleine Netze: das Modell."""
        if len(self.dreiecke) <= GROB_DREIECKE:
            return self
        if self._grob is None:
            p = self.punkte

            def flaeche(d):
                a, b, c = p[d[0]], p[d[1]], p[d[2]]
                u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                return ((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                        + (u[0] * v[1] - u[1] * v[0]) ** 2)
            g = Modell.__new__(Modell)
            g.__dict__.update(self.__dict__)
            neu, g.punkte, g.dreiecke = {}, [], []
            for i, j, k, art, n in sorted(self.dreiecke, key=flaeche, reverse=True)[:GROB_DREIECKE]:
                for x in (i, j, k):
                    if x not in neu:
                        neu[x] = len(g.punkte)
                        g.punkte.append(p[x])
                g.dreiecke.append((neu[i], neu[j], neu[k], art, n))
            g.linien, g.linien_id = [], []
            g._grob = g
            self._grob = g
        return self._grob

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


def projektion(modell, breite, hoehe, gier, nick, zoom=1.0, verschiebung=(0.0, 0.0)):
    """Gedrehte Punkte (x, y, Tiefe) um die Mitte, Maßstab und Bildmitte wie beim Zeichnen mit QPainter."""
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
    return m, proj, massstab, breite / 2 + verschiebung[0], hoehe / 2 + verschiebung[1]


def zeichnen(p, modell, breite, hoehe, gier, nick, zoom=1.0, verschiebung=(0.0, 0.0), linien=True, glatt=True):
    """Modell in ein Rechteck (0, 0, breite, hoehe) zeichnen. glatt: Kantenglättung (aus = schneller)."""
    m, proj, massstab, ox, oy = projektion(modell, breite, hoehe, gier, nick, zoom, verschiebung)
    cx, cy, cz = modell.mitte
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
            nz = m[2][0] * n[0] + m[2][1] * n[1] + m[2][2] * n[2]
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
    p.setRenderHint(QPainter.Antialiasing, glatt)
    stift_linie = {a: QPen(LINIE.get(a, QColor("#C00000")), NAHT_BREITE if a in NAEHTE else 2.2, Qt.SolidLine,
                           Qt.RoundCap) for a in LINIE}
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
    angeklickt = Signal(object)     # Klick ohne Ziehen auf eine Linie: dict(id=Merkmal oder None, punkt=(x, y, z))
    gemessen = Signal(object)       # Messen: Abstand [mm] nach dem zweiten Punkt
    _gl = None              # OpenGL-Fläche (ansicht3d_gl.GLFlaeche) oder None = QPainter

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)
        self.modell, self.titel, self.netz, self.modus = None, "", None, MODI[0]
        # Teile-Editor: hervorgehobene Linien (Merkmale bzw. Bereich längs der Rohrachse), Messen Punkt–Punkt
        self.markiert, self.markiert_z, self.messen, self.messpunkte = set(), None, False, []
        self._druck = None
        self._bild, self._eilig = None, False      # gezeichnetes Bild (solange sich die Ansicht nicht ändert)
        self._ruhe = QTimer(self)                   # nach dem Zoomen wieder fein zeichnen
        self._ruhe.setSingleShot(True)
        self._ruhe.setInterval(250)
        self._ruhe.timeout.connect(self._fein)
        self.renderer, self.renderer_grund = renderer_waehlen()
        self._gl = None
        if self.renderer == "OpenGL":
            from .ansicht3d_gl import GLFlaeche
            self._gl = GLFlaeche(self)
            self._gl.setGeometry(self.rect())
        self.zuruecksetzen()

    def _gl_aus(self, grund):
        """OpenGL gescheitert: diese und alle weiteren Ansichten zeichnen mit QPainter."""
        global _gl_fehler
        _gl_fehler = grund
        self.renderer, self.renderer_grund = "Software", f"OpenGL gescheitert: {grund}"
        if self._gl is not None:
            gl, self._gl = self._gl, None
            gl.hide()
            gl.deleteLater()
        QTimer.singleShot(0, self.update)

    def update(self, *args):
        super().update(*args)
        if self._gl is not None:
            self._gl.update()

    def resizeEvent(self, e):
        if self._gl is not None:
            self._gl.setGeometry(self.rect())
        super().resizeEvent(e)

    def _fein(self):
        self._eilig = False
        self.update()

    def setzen(self, netz, titel=""):
        """netz: dict, Bytes aus der Datenbank oder None (= keine 3D-Daten)."""
        if isinstance(netz, (bytes, bytearray, memoryview)):
            netz = entpacken(bytes(netz))
        self.netz = netz if netz and netz.get("p") else None
        self.modell = Modell(gefiltert(self.netz, self.modus)) if self.netz else None
        self.titel = titel
        self.messpunkte = []
        self.zuruecksetzen()

    def markieren(self, ids=(), z_bereich=None):
        """Linien der Merkmale ids (netz 'li') bzw. alle Linien mit z im Bereich (z0, z1) hervorheben."""
        self.markiert, self.markiert_z = set(ids or ()), z_bereich
        self.update()

    def messen_setzen(self, an):
        """Messen: zwei Punkte des Modells anklicken (fängt die nächste Ecke), Abstand in mm."""
        self.messen, self.messpunkte = bool(an), []
        self.setCursor(Qt.CrossCursor if an else Qt.ArrowCursor)
        self.update()

    def abstand(self):
        """Gemessener Abstand [mm] oder None."""
        if len(self.messpunkte) == 2:
            return math.dist(*self.messpunkte)
        return None

    def bildpunkt(self):
        """Funktion Modellpunkt (x, y, z) -> (Pixel x, Pixel y, Tiefe) für die aktuelle Ansicht (wie gezeichnet)."""
        modell = self.modell
        if self._gl is not None:
            from .ansicht3d_gl import abbildung
            m = _drehung(self.gier, self.nick)
            s, ox, oy = abbildung(modell, max(1, self.width()), max(1, self.height()), m, self.zoom, self.versatz)
        else:
            m, _, s, ox, oy = projektion(modell, self.width(), self.height(), self.gier, self.nick, self.zoom,
                                         self.versatz)
        cx, cy, cz = modell.mitte

        def bild(v):
            x, y, z = v[0] - cx, v[1] - cy, v[2] - cz
            return (ox + (m[0][0] * x + m[0][1] * y + m[0][2] * z) * s,
                    oy - (m[1][0] * x + m[1][1] * y + m[1][2] * z) * s,
                    m[2][0] * x + m[2][1] * y + m[2][2] * z)
        return bild

    def klicken(self, x, y):
        """Klick an Pixel (x, y): Messpunkt setzen bzw. nächste Linie wählen (Signal angeklickt)."""
        if self.modell is None:
            return None
        bild = self.bildpunkt()
        if self.messen:
            beste = None
            for v in self.modell.punkte:
                px, py, t = bild(v)
                d = math.hypot(px - x, py - y)
                if d <= 14 and (beste is None or (d - t * 1e-3) < beste[0]):
                    beste = (d - t * 1e-3, v)
            if beste is None:
                return None
            self.messpunkte = (self.messpunkte if len(self.messpunkte) < 2 else []) + [tuple(beste[1])]
            self.update()
            if len(self.messpunkte) == 2:
                self.gemessen.emit(self.abstand())
            return beste[1]
        beste = None
        for nr, (a, b, _, _) in enumerate(self.modell.linien):
            pa, pb = bild(a), bild(b)
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            lg = dx * dx + dy * dy
            t = 0.0 if lg < 1e-9 else max(0.0, min(1.0, ((x - pa[0]) * dx + (y - pa[1]) * dy) / lg))
            d = math.hypot(pa[0] + t * dx - x, pa[1] + t * dy - y)
            if d <= 8 and (beste is None or d < beste[0]):
                beste = (d, nr, tuple(a[k] + t * (b[k] - a[k]) for k in range(3)))
        if beste is None:
            return None
        kn = self.modell.linien_id[beste[1]] if beste[1] < len(self.modell.linien_id) else None
        treffer = dict(id=kn, punkt=beste[2])
        self.angeklickt.emit(treffer)
        return treffer

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
        if self._gl is not None:        # zeichnet die OpenGL-Fläche (mit _beschriften)
            return
        p = QPainter(self)
        p.fillRect(self.rect(), HINTERGRUND)
        if self.modell is None:
            p.setPen(QColor("#7F7F7F"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Keine 3D-Daten.\nDie 3D-Ansicht gibt es für Teile, die per STEP-Import übernommen wurden.")
            return
        grob = self._eilig or self._maus is not None
        modell = self.modell.grob() if grob else self.modell
        schluessel = (modell, self.width(), self.height(), self.devicePixelRatioF(), self.gier, self.nick,
                      self.zoom, self.versatz)
        if self._bild is None or self._bild[0] != schluessel:
            dpr = self.devicePixelRatioF()
            bild = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
            bild.setDevicePixelRatio(dpr)
            bild.fill(Qt.transparent)
            q = QPainter(bild)
            zeichnen(q, modell, self.width(), self.height(), self.gier, self.nick, self.zoom, self.versatz,
                     linien=modell is self.modell, glatt=not grob)
            q.end()
            self._bild = (schluessel, bild)
        p.drawPixmap(0, 0, self._bild[1])
        self._beschriften(p)

    def _beschriften(self, p):
        """Titel, Legende der Flächenarten und Bedienhinweis über dem Bild (QPainter und OpenGL)."""
        if self.modell is None:
            p.setPen(QColor("#7F7F7F"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Keine 3D-Daten.\nDie 3D-Ansicht gibt es für Teile, die per STEP-Import übernommen wurden.")
            return
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
        self._markierung_zeichnen(p)
        p.setPen(QColor("#7F7F7F"))
        p.drawText(QRectF(10, self.height() - 22, self.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   "Messen: zwei Punkte anklicken (fängt die nächste Ecke)" if self.messen else
                   "Linke Maustaste drehen · rechte verschieben · Mausrad zoomen · Doppelklick Ausgangsansicht")

    def _markierung_zeichnen(self, p):
        """Hervorgehobene Linien (Teile-Editor) und Messung über dem Bild."""
        if not (self.markiert or self.markiert_z or self.messpunkte):
            return
        bild = self.bildpunkt()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(MARKIERT, 4.0, Qt.SolidLine, Qt.RoundCap))
        z = self.markiert_z
        for nr, (a, b, _, _) in enumerate(self.modell.linien):
            kn = self.modell.linien_id[nr] if nr < len(self.modell.linien_id) else None
            if (kn is not None and kn in self.markiert) or \
                    (z is not None and z[0] - 1e-6 <= a[2] <= z[1] + 1e-6 and z[0] - 1e-6 <= b[2] <= z[1] + 1e-6):
                pa, pb = bild(a), bild(b)
                p.drawLine(QPointF(pa[0], pa[1]), QPointF(pb[0], pb[1]))
        if self.messpunkte:
            pk = [bild(v) for v in self.messpunkte]
            p.setPen(QPen(MESSEN, 2.0))
            if len(pk) == 2:
                p.drawLine(QPointF(pk[0][0], pk[0][1]), QPointF(pk[1][0], pk[1][1]))
            p.setBrush(QBrush(MESSEN))
            for q in pk:
                p.drawEllipse(QPointF(q[0], q[1]), 4, 4)
            p.setBrush(Qt.NoBrush)
            if len(pk) == 2:
                a, b = self.messpunkte
                text = (f"Abstand {_zahl(math.dist(a, b))} mm (Δx {_zahl(abs(b[0] - a[0]))}, "
                        f"Δy {_zahl(abs(b[1] - a[1]))}, Δz {_zahl(abs(b[2] - a[2]))})")
                p.drawText(QRectF((pk[0][0] + pk[1][0]) / 2 + 8, (pk[0][1] + pk[1][1]) / 2 - 20, 360, 18),
                           Qt.AlignLeft | Qt.AlignVCenter, text)

    def mousePressEvent(self, e):
        self._maus = (e.position(), e.button())
        self._druck = e.position() if e.button() == Qt.LeftButton else None

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

    def mouseReleaseEvent(self, e):
        self._maus = None
        druck, self._druck = self._druck, None
        if druck is not None and e is not None and (e.position() - druck).manhattanLength() < 4:
            self.klicken(e.position().x(), e.position().y())
        self.update()

    def mouseDoubleClickEvent(self, _):
        self.zuruecksetzen()

    def wheelEvent(self, e):
        self.zoom = max(0.2, min(40.0, self.zoom * (1.15 ** (e.angleDelta().y() / 120))))
        self._eilig = True
        self._ruhe.start()
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
