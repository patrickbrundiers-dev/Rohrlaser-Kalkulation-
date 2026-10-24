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
import itertools
import json
import math
import sys
import zlib

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF
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
    ("SN", "Schweißnähte", "#1A1A1A", "#1A1A1A"),        # Baugruppen-Ansicht: Nahtgruppen (schwarz: auf allen
    ("SV", "Nahtvorschläge (STEP)", "#D000D0", "#D000D0"),  # Teilfarben sichtbar), offene Nahtkandidaten magenta
    ("SH", "gewählte Naht", "#FF0000", "#FF0000"),
    ("NL", "Schweißnaht (Längsnaht)", "#E00000", "#E00000"),     # Rohr-Editor: Lage der Naht im Rohr
    ("GB", "3D über Grenze (begrenzt)", "#F2C200", "#C79A00"),  # Schnitt braucht mehr als die Schwenkgrenze
    ("HK", "Gegenrohr (Hilfskörper)", "#E377C2", "#E377C2"),   # Rohr-Editor: Gegenrohr am Ende / Durchbruch
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
HINTERGRUND = QColor("#FFFFFF")         # unten; oben HINTERGRUND_OBEN, dazwischen Verlauf (hintergrund_bei)
HINTERGRUND_OBEN = QColor("#DCE3EA")
# Licht (QPainter je Dreieck, OpenGL je Ecke, gleiche Formel): Hauptlicht links oben vorn, Fülllicht rechts unten;
# LICHT_WERTE = (Grundlicht, Neigung oben heller, Fülllicht, Glanz, Glanz-Exponent) – Metall-Look
LICHT = (-0.35, 0.45, 0.82)
LICHT2 = (0.55, -0.35, 0.76)
LICHT_WERTE = (0.38, 0.06, 0.16, 0.22, 36.0)
MARKIERT = QColor("#00A040")        # Teile-Editor: gewähltes Merkmal (grün umrandet wie im CAM, Plan G3)
KANTE = QColor("#3C4650")           # Darstellung „Mit Kanten“: Körperkanten
# Darstellungsarten (Plan 3D-Editor A4): Schattiert = Flächen und Schnittkonturen (wie bisher), Mit Kanten = dazu die
# Körperkanten dunkel, Durchsichtig = Röntgen (Rückseiten und verdeckte Konturen sichtbar)
SCHATTIERT, MIT_KANTEN, DURCHSICHTIG = "Schattiert", "Mit Kanten", "Durchsichtig"
# Plan 3D-Ansicht 3E-11 (M3): Drahtgitter = nur Körperkanten und Konturen (auch die hinteren), Verdeckt gestrichelt =
# helle Flächen, sichtbare Kanten durchgezogen, verdeckte gestrichelt (wie eine technische Zeichnung)
DRAHTGITTER, VERDECKT = "Drahtgitter", "Verdeckt gestrichelt"
DARSTELLUNGEN = (SCHATTIERT, MIT_KANTEN, DURCHSICHTIG, DRAHTGITTER, VERDECKT)
MIT_KOERPERKANTEN = (MIT_KANTEN, DRAHTGITTER, VERDECKT)
VERDECKT_HELL = 0.6     # „Verdeckt gestrichelt“: Flächen so weit zu Weiß gemischt
VERDECKT_FARBE = QColor("#7A8794")      # verdeckte Kanten (gestrichelt)
# Perspektive (M2): Kamera so viele Modellgrößen vor der Bildmitte; Vorgabe orthogonal, je Benutzer gemerkt
PERSPEKTIVE_ABSTAND = 2.4
PERSPEKTIVE_EINSTELLUNG = "ansicht_perspektive"
ALPHA = 0.32            # Deckkraft der Flächen bei „Durchsichtig“
BLASS = 0.72            # „nur Gewähltes hervorheben“: Rest so weit zu Weiß gemischt
KANTEN_MAX = 60000      # Körperkanten nur bis zu so vielen Dreiecken suchen (große Baugruppen: keine)
KANTEN_WINKEL = 0.9     # cos des Knickwinkels: darüber gilt ein Übergang als glatt (keine Kante), etwa 25°
GLATT_MAX = 150000      # Rundungen glatt schattieren (Normale je Ecke) nur bis zu so vielen Dreiecken
MESSEN = QColor("#B42318")
FANG = QColor("#0070C0")             # Messen: gefangenes Element unter der Maus
SCHNITT = QColor("#1F4E78")          # Querschnitt-Stelle (editor_schnitt)
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


def baugruppe(netze, hervor=(), farben=None, fehlend=(), bereiche=None):
    """Teile einer Baugruppe in ihrer Einbaulage zu einem Netz zusammensetzen. netze: Liste von Netzen (dict oder
    gepackt); farben: je Netz eine Nummer, gleiche Nummer = gleiche Farbe (z. B. gleiche Teile), sonst je Netz eine;
    hervor: Nummern in netze, die als 'gewählte Teile' (Art S) blau, alle anderen hellgrau gefärbt werden;
    fehlend: Nummern der nicht übernehmbaren Teile, immer magenta (Art N), außer sie sind gewählt. Ohne Innenwände und
    Schnittlinien (bei vielen Teilen verdeckt bzw. zu unruhig). Ergebnis: (Netz oder None, Anzahl Teile ohne
    Einbaulage, z. B. aus einer älteren Messung). bereiche: Liste, bekommt je Netz (Nummer, erster Punkt, Ende,
    Dreiecke als Punktnummern) für die Zuordnung eines Modellpunkts zu seinem Teil."""
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
        if bereiche is not None:
            bereiche.append((nr, basis, len(punkte) // 3, [basis + i for a, idx in (netz.get("t") or {}).items()
                                                            if a != "I" for i in idx]))
        for art, idx in (netz.get("t") or {}).items():
            if art == "I":
                continue
            art = "S" if nr in hervor else "N" if nr in fehlend else "X" if hervor else \
                f"F{(farben[nr] if farben else nr) % len(TEILFARBEN)}"
            dreiecke.setdefault(art, []).extend(basis + i for i in idx)
    return (dict(p=punkte, t=dreiecke, l={}) if punkte else None), ohne


MESS_ABSTAND, MESS_WINKEL = "Abstand", "Winkel"
# Feste Blickrichtungen (3E-11): Name -> Richtung im Modell, die zum Betrachter zeigt (wie der Ansichtswürfel: Rohrachse
# z, Ende A bei z = 0, oben = +y, vorne = −x)
ISOMETRIE = "Isometrie"
BLICKE = (("Vorn", (-1, 0, 0)), ("Hinten", (1, 0, 0)), ("Oben", (0, 1, 0)), ("Unten", (0, -1, 0)),
          ("Ende A", (0, 0, -1)), ("Ende B", (0, 0, 1)))
NICK_MAX = 1.5          # nie ganz senkrecht (die Drehung um die Blickachse bliebe unbestimmt)


def blick_auf(normale):
    """(gier, nick), damit die Modellrichtung normale zum Betrachter zeigt (_drehung dreht sie auf +z)."""
    nx, ny, nz = normale
    betrag = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    nx, ny, nz = nx / betrag, ny / betrag, nz / betrag
    a, b = nz, -nx                 # Grundstellung (x, y, z) -> (z, y, -x)
    r = math.hypot(a, b)
    gier = math.atan2(-a, b) if r > 1e-9 else 0.0
    nick = max(-NICK_MAX, min(NICK_MAX, math.atan2(ny, r)))
    return gier, nick


def winkel_bei(a, b, c):
    """Winkel [°] am Punkt b zwischen den Strecken b→a und b→c."""
    u = [a[i] - b[i] for i in range(3)]
    w = [c[i] - b[i] for i in range(3)]
    lu, lw = math.sqrt(sum(x * x for x in u)), math.sqrt(sum(x * x for x in w))
    if lu < 1e-12 or lw < 1e-12:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(u[i] * w[i] for i in range(3)) / (lu * lw)))))


def _zahl(w):
    return f"{w:.1f}".replace(".", ",")


_speicher = None        # Datenbank des Benutzers für gemerkte Ansicht-Einstellungen (Perspektive)


def speicher_setzen(db):
    """Datenbank, in der die 3D-Ansichten die Perspektive je Benutzer merken (fenster.py beim Start)."""
    global _speicher
    _speicher = db


def perspektive_vorgabe():
    try:
        return _speicher is not None and _speicher.einstellung(PERSPEKTIVE_EINSTELLUNG) is True
    except Exception:           # Lesemodus, alte Datei
        return False


def _perspektive_merken(an):
    try:
        if _speicher is not None:
            _speicher.einstellung_setzen(PERSPEKTIVE_EINSTELLUNG, bool(an))
    except Exception:           # Lesemodus: dann eben nicht merken
        pass


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
        self.dreiecke_id = []                   # je Dreieck: Merkmal (netz 'ti', Teile-Editor) – leer ohne 'ti'
        kennung = netz.get("ti") or {}
        for art, idx in (netz.get("t") or {}).items():
            kn = kennung.get(art) or []
            for n in range(0, len(idx) - 2, 3):
                if self._dreieck(idx[n], idx[n + 1], idx[n + 2], art) and kennung:
                    self.dreiecke_id.append(kn[n // 3] if n // 3 < len(kn) else None)
        self.linien = []
        self.linien_id = []                     # je Liniensegment: Merkmal (netz 'li', Teile-Editor) oder None
        self.mitten = []                        # Mitte je Konturlinie (Messen fängt Kreismitten)
        normalen = netz.get("ln") or {}         # Normale je Linienzug (Blech), sonst radial zur Rohrachse
        kennung = netz.get("li") or {}
        for art, zuege in (netz.get("l") or {}).items():
            for nr, zug in enumerate(zuege):
                pk = [(zug[i], zug[i + 1], zug[i + 2]) for i in range(0, len(zug) - 2, 3)]
                n = (normalen.get(art) or [])[nr] if nr < len(normalen.get(art) or []) else None
                kn = (kennung.get(art) or [])[nr] if nr < len(kennung.get(art) or []) else None
                self.linien_id += [kn] * max(len(pk) - 1, 0)
                if art in ("K", "G") and len(pk) >= 4:
                    ring = pk[:-1] if pk[0] == pk[-1] else pk
                    self.mitten.append(tuple(sum(q[i] for q in ring) / len(ring) for i in range(3)))
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
            g.linien, g.linien_id, g.dreiecke_id = [], [], []
            g._glatt = None
            g._grob = g
            self._grob = g
        return self._grob

    def glatte_normalen(self):
        """Normale je Ecke für glatte Rundungen (OpenGL schattiert zwischen den Ecken): Mittel der Flächennormalen
        aller Dreiecke an derselben Stelle, gewichtet mit der Fläche, nur über glatte Übergänge (Knick flacher als
        KANTEN_WINKEL) – Kanten wie Rohrwand/Stirnfläche oder scharfe Profilecken bleiben scharf. [(n_i, n_j, n_k)]
        je Dreieck; große Netze: None (flach)."""
        if getattr(self, "_glatt", 0) != 0:
            return self._glatt
        self._glatt = None
        if not self.dreiecke or len(self.dreiecke) > GLATT_MAX:
            return None
        p = self.punkte
        orte = {}
        gewicht = []
        for nr, (i, j, k, _, n) in enumerate(self.dreiecke):
            a, b, c = p[i], p[j], p[k]
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            f = math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                          + (u[0] * v[1] - u[1] * v[0]) ** 2)
            gewicht.append(f)
            for x in (i, j, k):
                orte.setdefault((round(p[x][0], 2), round(p[x][1], 2), round(p[x][2], 2)), []).append(nr)
        out = []
        for i, j, k, _, n in self.dreiecke:
            ecken = []
            for x in (i, j, k):
                s = [0.0, 0.0, 0.0]
                for m in orte[(round(p[x][0], 2), round(p[x][1], 2), round(p[x][2], 2))]:
                    q = self.dreiecke[m][4]
                    if q[0] * n[0] + q[1] * n[1] + q[2] * n[2] > KANTEN_WINKEL:
                        w = gewicht[m]
                        s[0] += q[0] * w
                        s[1] += q[1] * w
                        s[2] += q[2] * w
                betrag = math.sqrt(s[0] ** 2 + s[1] ** 2 + s[2] ** 2)
                ecken.append((s[0] / betrag, s[1] / betrag, s[2] / betrag) if betrag > 1e-12 else n)
            out.append(ecken)
        self._glatt = out
        return out

    def ebenen(self):
        """Ebene Flächen (3E-11, Messen und Tangentenkanten): (je Dreieck Nummer der Ebene, je Ebene dict(n, d,
        flaeche, dreiecke)) – Dreiecke gleicher Normale und gleichen Abstands vom Ursprung (n·p = d) gehören zu einer
        Ebene. Einmal je Modell gerechnet; große Netze: keine."""
        if getattr(self, "_ebenen", None) is not None:
            return self._ebenen
        nummer, liste, schl = [], [], {}
        if len(self.dreiecke) <= KANTEN_MAX:
            p = self.punkte
            for i, j, k, _, n in self.dreiecke:
                a, b, c = p[i], p[j], p[k]
                u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                f = math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                              + (u[0] * v[1] - u[1] * v[0]) ** 2) / 2
                d = sum(n[q] * (a[q] + b[q] + c[q]) / 3 for q in range(3))
                key = (round(n[0], 3), round(n[1], 3), round(n[2], 3), round(d, 1))
                nr = schl.get(key)
                if nr is None:
                    nr = schl[key] = len(liste)
                    liste.append(dict(n=n, d=d, flaeche=0.0, dreiecke=[]))
                liste[nr]["flaeche"] += f
                liste[nr]["dreiecke"].append(len(nummer))
                nummer.append(nr)
        self._ebenen = (nummer, liste)
        return self._ebenen

    def _kanten_bauen(self):
        """Körperkanten und glatte Übergänge (für Umrisslinien) einmal suchen."""
        self._kanten, self._glatt_kanten = [], []
        if len(self.dreiecke) > KANTEN_MAX:
            return
        p = self.punkte
        nummer, ebenen = self.ebenen()
        gross = 0.1 * max((e["flaeche"] for e in ebenen), default=0.0)     # „große“ ebene Fläche

        def schl(i):
            return (round(p[i][0], 2), round(p[i][1], 2), round(p[i][2], 2))
        seiten = {}
        for nr, (i, j, k, _, n) in enumerate(self.dreiecke):
            a, b, c = schl(i), schl(j), schl(k)
            for x, y in ((a, b), (b, c), (c, a)):
                if x != y:
                    seiten.setdefault((x, y) if x < y else (y, x), []).append(nr)
        for (a, b), drei in seiten.items():
            ns = [self.dreiecke[d][4] for d in drei]
            if len(ns) == 2:
                cos = sum(ns[0][q] * ns[1][q] for q in range(3))
                e0, e1 = ebenen[nummer[drei[0]]], ebenen[nummer[drei[1]]]
                # Tangentenkante: Übergang einer großen ebenen Fläche in eine Rundung (z. B. Eckradius eines
                # Quadratrohrs), wie die Kanten im CAD
                f0, f1 = sorted((e0["flaeche"], e1["flaeche"]))
                tangente = e0 is not e1 and cos < 0.99995 and f1 >= gross and f1 > 3 * f0
                if cos > KANTEN_WINKEL and not tangente:
                    self._glatt_kanten.append((a, b, ns[0], ns[1]))
                    continue
            n = tuple(sum(x[q] for x in ns[:2]) for q in range(3))
            betrag = math.sqrt(sum(c * c for c in n)) or 1.0
            self._kanten.append((a, b, tuple(c / betrag for c in n)))

    def kanten(self):
        """Körperkanten für „Mit Kanten“, Drahtgitter und Verdeckt: [(a, b, Normale)] – Ränder des Netzes, Knicke
        zwischen zwei Dreiecken (stumpfer als KANTEN_WINKEL) und Tangentenkanten (ebene Fläche → Rundung). Punkte
        gleicher Lage gelten als derselbe Punkt (das Netz hat je Dreieck eigene Punkte). Einmal je Modell gerechnet;
        große Netze: keine."""
        if getattr(self, "_kanten", None) is None:
            self._kanten_bauen()
        return self._kanten

    def glatte_kanten(self):
        """Glatte Übergänge [(a, b, Normale 1, Normale 2)]: wo eine Seite zum Betrachter zeigt und die andere nicht,
        liegt der Umriss (Rundrohr im Drahtgitter)."""
        if getattr(self, "_glatt_kanten", None) is None:
            self._kanten_bauen()
        return self._glatt_kanten

    def _dreieck(self, i, j, k, art):
        a, b, c = self.punkte[i], self.punkte[j], self.punkte[k]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        betrag = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        if betrag < 1e-12:
            return False
        self.dreiecke.append((i, j, k, art, (n[0] / betrag, n[1] / betrag, n[2] / betrag)))
        return True


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


def persp_faktor(modell, perspektive):
    """1 / Kameraabstand für die Perspektive (0 = orthogonal)."""
    return 1.0 / (PERSPEKTIVE_ABSTAND * modell.groesse) if perspektive else 0.0


def _projektion_roh(modell, breite, hoehe, gier, nick, zoom=1.0, verschiebung=(0.0, 0.0), perspektive=False):
    m = _drehung(gier, nick)
    cx, cy, cz = modell.mitte
    pz = persp_faktor(modell, perspektive)
    proj, roh = [], []
    for x, y, z in modell.punkte:
        x, y, z = x - cx, y - cy, z - cz
        q = (m[0][0] * x + m[0][1] * y + m[0][2] * z, m[1][0] * x + m[1][1] * y + m[1][2] * z,
             m[2][0] * x + m[2][1] * y + m[2][2] * z)
        roh.append(q)
        if pz:
            f = 1.0 / (1.0 - q[2] * pz)
            q = (q[0] * f, q[1] * f, q[2])
        proj.append(q)
    massstab = zoom * 0.92 * min(breite, hoehe * 3) / modell.groesse
    if proj:
        bx = max(abs(q[0]) for q in proj) * 2 or 1
        by = max(abs(q[1]) for q in proj) * 2 or 1
        massstab = zoom * 0.9 * min(breite / bx, hoehe / by)
    return m, proj, roh, massstab, breite / 2 + verschiebung[0], hoehe / 2 + verschiebung[1]


def projektion(modell, breite, hoehe, gier, nick, zoom=1.0, verschiebung=(0.0, 0.0), perspektive=False):
    """Gedrehte Punkte (x, y, Tiefe) um die Mitte, Maßstab und Bildmitte wie beim Zeichnen mit QPainter.
    perspektive: x, y schon mit dem Faktor der Perspektive (näher = größer)."""
    m, proj, _, massstab, ox, oy = _projektion_roh(modell, breite, hoehe, gier, nick, zoom, verschiebung, perspektive)
    return m, proj, massstab, ox, oy


def sicht(n, q, pz):
    """Anteil der gedrehten Normale n zum Betrachter am gedrehten Ort q (> 0 = Vorderseite); orthogonal n.z."""
    if not pz:
        return n[2]
    return -n[0] * q[0] * pz - n[1] * q[1] * pz + n[2] * (1.0 - q[2] * pz)


def _blass(c, an):
    """Farbe für „nur Gewähltes hervorheben“: zu Weiß gemischt."""
    if not an:
        return c
    return QColor(*(int(x + (255 - x) * BLASS) for x in (c.red(), c.green(), c.blue())))


def hintergrund_bei(y, hoehe):
    """Farbe des Hintergrundverlaufs in Bildzeile y (0 = oben)."""
    f = max(0.0, min(1.0, y / max(1, hoehe - 1)))
    o, u = HINTERGRUND_OBEN, HINTERGRUND
    return QColor(round(o.red() + (u.red() - o.red()) * f), round(o.green() + (u.green() - o.green()) * f),
                  round(o.blue() + (u.blue() - o.blue()) * f))


def hintergrund_malen(p, rechteck):
    verlauf = QLinearGradient(0, rechteck.top(), 0, rechteck.bottom())
    verlauf.setColorAt(0.0, HINTERGRUND_OBEN)
    verlauf.setColorAt(1.0, HINTERGRUND)
    p.fillRect(rechteck, QBrush(verlauf))


def licht_wert(nx, ny, nz):
    """(Faktor für die Farbe, Glanz-Zugabe 0..1) zur Normalen in Bildkoordinaten (zum Betrachter gedreht)."""
    a, neig, fuell, glanz, exp = LICHT_WERTE
    hell = a + neig * ny + (1 - a) * max(0.0, nx * LICHT[0] + ny * LICHT[1] + nz * LICHT[2]) \
        + fuell * max(0.0, nx * LICHT2[0] + ny * LICHT2[1] + nz * LICHT2[2])
    hx, hy, hz = LICHT[0], LICHT[1], LICHT[2] + 1.0
    b = math.sqrt(hx * hx + hy * hy + hz * hz)
    return hell, glanz * max(0.0, (nx * hx + ny * hy + nz * hz) / b) ** exp


def umriss(modell, m, pz=0.0):
    """Umrisslinien glatter Rundungen für die aktuelle Drehung m: [(a, b, True)] – Übergänge, an denen eine Seite
    zum Betrachter zeigt und die andere nicht."""
    cx, cy, cz = modell.mitte
    out = []
    for a, b, n1, n2 in modell.glatte_kanten():
        if pz:
            q = tuple(sum(m[r][c] * ((a[c] + b[c]) / 2 - (cx, cy, cz)[c]) for c in range(3)) for r in range(3))
        else:
            q = (0.0, 0.0, 0.0)
        s1 = sicht(tuple(m[r][0] * n1[0] + m[r][1] * n1[1] + m[r][2] * n1[2] for r in range(3)), q, pz)
        s2 = sicht(tuple(m[r][0] * n2[0] + m[r][1] * n2[1] + m[r][2] * n2[2] for r in range(3)), q, pz)
        if (s1 > 0) != (s2 > 0):
            out.append((a, b, True))
    return out


def zeichnen(p, modell, breite, hoehe, gier, nick, zoom=1.0, verschiebung=(0.0, 0.0), linien=True, glatt=True,
             darstellung=SCHATTIERT, blass=False, perspektive=False):
    """Modell in ein Rechteck (0, 0, breite, hoehe) zeichnen. glatt: Kantenglättung (aus = schneller). darstellung:
    DARSTELLUNGEN; blass: alles blass (der Teile-Editor zeichnet das Gewählte kräftig darüber); perspektive: Tiefe
    perspektivisch (sonst orthogonal)."""
    m, proj, roh, massstab, ox, oy = _projektion_roh(modell, breite, hoehe, gier, nick, zoom, verschiebung,
                                                     perspektive)
    cx, cy, cz = modell.mitte
    pz = persp_faktor(modell, perspektive)
    roentgen = darstellung == DURCHSICHTIG
    draht = darstellung == DRAHTGITTER
    verdeckt_strich = darstellung == VERDECKT
    # Einträge (Schicht, Tiefe, Punkte, Art, Licht bzw. sichtbar, Linie?): Schicht -1 verdeckte Kanten unter allem,
    # 0 Innenwand, 1 Flächen, 2 Linien und Kanten obenauf
    liste = []
    if not draht:
        for i, j, k, art, n in modell.dreiecke:
            nx = m[0][0] * n[0] + m[0][1] * n[1] + m[0][2] * n[2]
            ny = m[1][0] * n[0] + m[1][1] * n[1] + m[1][2] * n[2]
            nz = m[2][0] * n[0] + m[2][1] * n[1] + m[2][2] * n[2]
            if pz:
                ra, rb, rc = roh[i], roh[j], roh[k]
                sz = sicht((nx, ny, nz), ((ra[0] + rb[0] + rc[0]) / 3, (ra[1] + rb[1] + rc[1]) / 3,
                                          (ra[2] + rb[2] + rc[2]) / 3), pz)
            else:
                sz = nz
            if sz <= 0 and not roentgen:
                continue                     # Rückseite
            if sz <= 0:
                nx, ny, nz = -nx, -ny, -nz
            a, b, c = proj[i], proj[j], proj[k]
            # Schicht: Innenwand zuerst, dann Flächen, Schweißnaht-Raupen darüber (immer sichtbar wie ihre Linien)
            liste.append((1.5 if art in NAEHTE else 1 if roentgen else 0 if art == "I" else 1,
                          (a[2] + b[2] + c[2]) / 3, (a, b, c), art, licht_wert(nx, ny, nz), False))

    def gedreht(a):
        q = (m[0][0] * (a[0] - cx) + m[0][1] * (a[1] - cy) + m[0][2] * (a[2] - cz),
             m[1][0] * (a[0] - cx) + m[1][1] * (a[1] - cy) + m[1][2] * (a[2] - cz),
             m[2][0] * (a[0] - cx) + m[2][1] * (a[1] - cy) + m[2][2] * (a[2] - cz))
        if not pz:
            return q, q
        f = 1.0 / (1.0 - q[2] * pz)
        return (q[0] * f, q[1] * f, q[2]), q

    def nach_vorn(n, qa, qb):
        nr = tuple(m[r][0] * n[0] + m[r][1] * n[1] + m[r][2] * n[2] for r in range(3))
        return sicht(nr, tuple((qa[r] + qb[r]) / 2 for r in range(3)), pz)
    if linien:
        for a, b, art, n in modell.linien:
            (ra, qa), (rb, qb) = gedreht(a), gedreht(b)
            vorn = draht or nach_vorn(n, qa, qb) >= 0.0
            if not vorn and not (roentgen or verdeckt_strich):
                continue
            liste.append((2 if vorn or roentgen else -1, (ra[2] + rb[2]) / 2, (ra, rb), art, 1.0 if vorn else 0.0,
                          True))
    if linien and darstellung in MIT_KOERPERKANTEN:
        for a, b, n in modell.kanten():
            (ra, qa), (rb, qb) = gedreht(a), gedreht(b)
            vorn = draht or nach_vorn(n, qa, qb) >= -0.05
            if not vorn and not verdeckt_strich:
                continue
            liste.append((2 if vorn else -1, (ra[2] + rb[2]) / 2 - 1e-6, (ra, rb), "_kante" if vorn else "_verdeckt",
                          1.0, True))
    if linien and darstellung in (DRAHTGITTER, VERDECKT):
        for a, b, rand in umriss(modell, m, pz):
            (ra, _), (rb, _) = gedreht(a), gedreht(b)
            liste.append((2, (ra[2] + rb[2]) / 2 - 1e-6, (ra, rb), "_kante", 1.0, True))
    liste.sort(key=lambda e: (e[0], e[1]))
    p.setRenderHint(QPainter.Antialiasing, glatt)
    stift_linie = {a: QPen(_blass(LINIE.get(a, QColor("#C00000")), blass), NAHT_BREITE if a in NAEHTE else 2.2,
                           Qt.SolidLine, Qt.RoundCap) for a in LINIE}
    stift_linie["_kante"] = QPen(_blass(KANTE, blass), 1.1)
    stift_linie["_verdeckt"] = QPen(_blass(VERDECKT_FARBE, blass), 1.0, Qt.DashLine)
    verdeckt = {a: QPen(QColor(s.color().red(), s.color().green(), s.color().blue(), 110), 1.4, Qt.DashLine)
                for a, s in stift_linie.items()}
    for schicht, _, punkte, art, hell, ist_linie in liste:
        poly = [QPointF(ox + q[0] * massstab, oy - q[1] * massstab) for q in punkte]
        if ist_linie:
            p.setPen((stift_linie if hell else verdeckt).get(art, stift_linie["K"]))
            p.drawLine(poly[0], poly[1])
            continue
        f = _blass(FARBE.get(art, FARBE["K"]), blass)
        faktor, glanz = hell
        farbe = QColor(*(min(255, int(c * faktor + 255 * glanz)) for c in (f.red(), f.green(), f.blue())))
        if verdeckt_strich:
            farbe = QColor(*(int(c + (255 - c) * VERDECKT_HELL) for c in (farbe.red(), farbe.green(), farbe.blue())))
        if roentgen:
            farbe.setAlphaF(ALPHA)
            p.setPen(Qt.NoPen)
        else:
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
    messen_geaendert = Signal()     # Messen ein/aus bzw. Art gewechselt (gemeinsame Leiste stellt ihre Knöpfe)
    _gl = None              # OpenGL-Fläche (ansicht3d_gl.GLFlaeche) oder None = QPainter

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)
        self.modell, self.titel, self.netz, self.modus = None, "", None, MODI[0]
        # Teile-Editor: hervorgehobene Linien (Merkmale bzw. Bereich längs der Rohrachse), Messen Punkt–Punkt
        self.markiert, self.markiert_z, self.messen, self.messpunkte = set(), None, False, []
        self.mess_treffer = []                  # Fangpunkte zu den Messpunkten (messen3d: Art, Punkt, Element)
        self._schwebe = None                    # Fangpunkt unter der Maus (hervorgehoben)
        self._geo = None                        # messen3d.Geometrie des Modells (beim ersten Messen)
        self.mess_max = 2                       # Messen: 2 Punkte, Winkel 3; Naht zeichnen (Baugruppe): beliebig viele
        self.mess_art = MESS_ABSTAND
        self.masse_fest = []                    # fertige Messungen [(Punkte, Text)]: bleiben stehen bis gelöscht
        self.schnitt_linie = []                 # Querschnitt (editor_schnitt): Ring an der Stelle x
        self._druck = self._rechts = None
        self.darstellung, self.nur_gewaehlt = SCHATTIERT, False       # Darstellungsarten (A4)
        self.perspektive = perspektive_vorgabe()                        # 3E-11 M2: Vorgabe orthogonal
        # Werkzeug des Teile-Editors (editor_griffe): zeichnet Griffe/Maße über das Bild und bekommt Maus und Tasten
        # zuerst (druck/ziehen/loslassen/schweben/doppelklick/kontext/taste/zeichnen/hinweis)
        self.werkzeug, self._werkzeug_zieht = None, False
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
        from .messen3d import MessTafel
        self.tafel = MessTafel(self)            # Ergebnis des Messens mit Kernwerten (kopierbar)
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
        self.tafel.anordnen()
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
        self.messpunkte, self.mess_treffer, self._schwebe, self._geo = [], [], None, None
        self.tafel.zeigen([])
        self.zuruecksetzen()

    def darstellung_setzen(self, darstellung=None, nur_gewaehlt=None):
        """Darstellungsart (DARSTELLUNGEN) und „nur Gewähltes hervorheben“ (Rest blass)."""
        if darstellung in DARSTELLUNGEN:
            self.darstellung = darstellung
        if nur_gewaehlt is not None:
            self.nur_gewaehlt = bool(nur_gewaehlt)
        self.update()

    def blass(self):
        """Rest blass zeichnen: nur Gewähltes hervorheben und etwas ist gewählt."""
        return self.nur_gewaehlt and bool(self.markiert or self.markiert_z)

    def werkzeug_setzen(self, werkzeug):
        self.werkzeug = werkzeug
        self.setMouseTracking(werkzeug is not None or self.messen)
        self.update()

    def geometrie(self):
        """Fangbare Geometrie des Modells mit exakten Kernwerten (messen3d.Geometrie), einmal je Modell."""
        if self._geo is None or self._geo.modell is not self.modell:
            from .messen3d import Geometrie
            self._geo = Geometrie(self.modell, gefiltert(self.netz, self.modus))
        return self._geo

    def markieren(self, ids=(), z_bereich=None):
        """Linien der Merkmale ids (netz 'li') bzw. alle Linien mit z im Bereich (z0, z1) hervorheben."""
        self.markiert, self.markiert_z = set(ids or ()), z_bereich
        self.update()

    def messen_setzen(self, an, punkte=2, art=None):
        """Messen: zwei Punkte des Modells anklicken (fängt die nächste Ecke oder Konturmitte), Abstand in mm;
        art MESS_WINKEL: drei Punkte, Winkel am mittleren. punkte = 0: Linienzug mit beliebig vielen Punkten (Naht
        zeichnen), Signal gemessen nach jedem Punkt mit der Länge des Zugs. Fertige Messungen bleiben als Maß
        stehen (masse_loeschen)."""
        self.mess_art = art or MESS_ABSTAND
        if self.mess_art == MESS_WINKEL and punkte:
            punkte = 3
        self.messen, self.messpunkte, self.mess_max = bool(an), [], punkte or 0
        self.mess_treffer, self._schwebe = [], None
        self.setCursor(Qt.CrossCursor if an else Qt.ArrowCursor)
        self.setMouseTracking(self.werkzeug is not None or self.messen)
        if not an:
            self.tafel.zeigen([])
        self.update()
        self.messen_geaendert.emit()

    def schnitt_setzen(self, punkte):
        """Stelle des Querschnitts als Linienzug [(x, y, z)] hervorheben ([] = aus)."""
        self.schnitt_linie = list(punkte or ())
        self.update()

    def masse_loeschen(self):
        self.masse_fest, self.messpunkte, self.mess_treffer = [], [], []
        self.tafel.zeigen([])
        self.update()

    def abstand(self):
        """Gemessener Abstand [mm] (Linienzug: Länge des Zugs) oder None (auch beim Winkel)."""
        if self.mess_art == MESS_WINKEL:
            return None
        if len(self.messpunkte) == 2 or (not self.mess_max and len(self.messpunkte) > 1):
            return sum(math.dist(a, b) for a, b in zip(self.messpunkte, self.messpunkte[1:]))
        return None

    def winkel(self):
        """Gemessener Winkel [°] am mittleren von drei Punkten oder None."""
        if self.mess_art != MESS_WINKEL or len(self.messpunkte) != 3:
            return None
        return winkel_bei(*self.messpunkte)

    def mess_text(self, punkte=None):
        """Ergebnis als Text: Abstand mit Δx/Δy/Δz bzw. Winkel; None solange unvollständig."""
        pk = self.messpunkte if punkte is None else punkte
        tr = self.mess_treffer
        if punkte is None and self.mess_art == MESS_ABSTAND and len(pk) == 2 and len(tr) == 2 and \
                [tuple(t["punkt"]) for t in tr] == [tuple(q) for q in pk]:
            return self.geometrie().vergleich(*tr)[0]          # exakter Wert (Fläche, Kante, Achse …)
        if len(pk) == 3:
            return f"Winkel {_zahl(winkel_bei(*pk))}°"
        if len(pk) == 2:
            a, b = pk
            return (f"Abstand {_zahl(math.dist(a, b))} mm (Δx {_zahl(abs(b[0] - a[0]))}, "
                    f"Δy {_zahl(abs(b[1] - a[1]))}, Δz {_zahl(abs(b[2] - a[2]))})")
        return None

    def punkt_zurueck(self):
        """Letzten Punkt des Linienzugs entfernen."""
        self.messpunkte = self.messpunkte[:-1]
        self.mess_treffer = self.mess_treffer[:len(self.messpunkte)]
        self.update()
        self.gemessen.emit(self.abstand())

    def bildpunkt(self):
        """Funktion Modellpunkt (x, y, z) -> (Pixel x, Pixel y, Tiefe) für die aktuelle Ansicht (wie gezeichnet)."""
        modell = self.modell
        if self._gl is not None:
            from .ansicht3d_gl import abbildung
            m = _drehung(self.gier, self.nick)
            s, ox, oy = abbildung(modell, max(1, self.width()), max(1, self.height()), m, self.zoom, self.versatz,
                                  persp_faktor(modell, self.perspektive))
        else:
            m, _, s, ox, oy = projektion(modell, self.width(), self.height(), self.gier, self.nick, self.zoom,
                                         self.versatz, self.perspektive)
        cx, cy, cz = modell.mitte
        pz = persp_faktor(modell, self.perspektive)

        def bild(v):
            x, y, z = v[0] - cx, v[1] - cy, v[2] - cz
            t = m[2][0] * x + m[2][1] * y + m[2][2] * z
            f = s / (1.0 - t * pz) if pz else s
            return (ox + (m[0][0] * x + m[0][1] * y + m[0][2] * z) * f,
                    oy - (m[1][0] * x + m[1][1] * y + m[1][2] * z) * f, t)
        return bild

    def klicken(self, x, y):
        """Klick an Pixel (x, y): Messpunkt setzen bzw. nächste Linie wählen (Signal angeklickt)."""
        if self.modell is None:
            return None
        bild = self.bildpunkt()
        if self.messen and self.mess_max:
            return self._messen_klick(bild, x, y)
        if self.messen:             # Naht zeichnen (Linienzug): Ecken des Netzes und Punkte der Konturen
            beste = None
            # Ecken des Netzes und Punkte der Schnittkonturen (Mitte zwischen zwei Konturen messen)
            for v in itertools.chain(self.modell.punkte, (li[0] for li in self.modell.linien), self.modell.mitten):
                px, py, t = bild(v)
                d = math.hypot(px - x, py - y)
                if d <= 14 and (beste is None or (d - t * 1e-3) < beste[0]):
                    beste = (d - t * 1e-3, v)
            if beste is None:
                return None
            if not self.mess_max and self.messpunkte and self.messpunkte[-1] == tuple(beste[1]):
                return beste[1]                             # Linienzug: derselbe Punkt nochmal zählt nicht
            voll = self.mess_max and len(self.messpunkte) >= self.mess_max
            self.messpunkte = ([] if voll else self.messpunkte) + [tuple(beste[1])]
            fertig = self.mess_max and len(self.messpunkte) == self.mess_max
            if fertig:
                self.masse_fest.append((list(self.messpunkte), self.mess_text()))
            self.update()
            if fertig or not self.mess_max:
                self.gemessen.emit(self.winkel() if self.mess_art == MESS_WINKEL else self.abstand())
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
            treffer = self._flaeche_treffer(bild, x, y)
            if treffer is None:
                return None
            self.angeklickt.emit(treffer)
            return treffer
        kn = self.modell.linien_id[beste[1]] if beste[1] < len(self.modell.linien_id) else None
        treffer = dict(id=kn, punkt=beste[2])
        self.angeklickt.emit(treffer)
        return treffer

    def _flaeche_treffer(self, bild, x, y):
        """Vorderstes Dreieck mit Merkmal (netz 'ti') unter dem Pixel (x, y): dict(id, punkt) oder None."""
        mo = self.modell
        if not mo.dreiecke_id:
            return None
        beste = None
        for (i, j, k, _, _), kn in zip(mo.dreiecke, mo.dreiecke_id):
            if kn is None:
                continue
            a, b, c = bild(mo.punkte[i]), bild(mo.punkte[j]), bild(mo.punkte[k])
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-6:
                continue
            tiefe = l1 * a[2] + l2 * b[2] + l3 * c[2]           # größer = näher am Betrachter
            if beste is None or tiefe > beste[0]:
                pa, pb, pc = mo.punkte[i], mo.punkte[j], mo.punkte[k]
                beste = (tiefe, kn, tuple(l1 * pa[m] + l2 * pb[m] + l3 * pc[m] for m in range(3)))
        return None if beste is None else dict(id=beste[1], punkt=beste[2])

    def modus_setzen(self, modus):
        """Vorschau Original / Rohrgeometrie / Gravurkonturen (MODI); Blickrichtung bleibt."""
        self.modus = modus
        if self.netz:
            self.modell = Modell(gefiltert(self.netz, modus))
            self._geo = None
        self.update()

    def zuruecksetzen(self):
        self.gier, self.nick = self.GRUND
        self.zoom, self.versatz, self._maus = 1.0, (0.0, 0.0), None
        self.update()

    def ansicht(self, gier, nick):
        self.gier, self.nick, self.zoom, self.versatz = gier, nick, 1.0, (0.0, 0.0)
        self.update()
        self.gedreht.emit()

    def blick(self, name):
        """Feste Blickrichtung nach Namen (BLICKE: Isometrie, Vorn, Hinten, Oben, Unten, Ende A, Ende B)."""
        if name == ISOMETRIE:
            self.ansicht(*self.GRUND)
            return
        n = dict(BLICKE).get(name)
        if n is not None:
            self.ansicht(*blick_auf(n))

    def drehen(self, schritte_gier=0, schritte_nick=0):
        """Um 90° drehen (Strg + Pfeiltasten): um die Hochachse genau 90°, Kippen auf die nächste Vierteldrehung
        (von oben wieder genau nach vorn)."""
        viertel = math.pi / 2
        self.gier = (self.gier + schritte_gier * viertel + math.pi) % (2 * math.pi) - math.pi
        if schritte_nick:
            self.nick = max(-NICK_MAX, min(NICK_MAX, round((self.nick + schritte_nick * viertel) / viertel) * viertel))
        self.update()
        self.gedreht.emit()

    def perspektive_setzen(self, an, merken=True):
        """Perspektivisch (an) oder orthogonal zeichnen; merken: Wahl je Benutzer speichern."""
        self.perspektive = bool(an)
        if merken:
            _perspektive_merken(self.perspektive)
        self.update()
        self.gedreht.emit()

    def auswahl_punkte(self):
        """Punkte des Gewählten: markierte Merkmale (Linien) bzw. der markierte Bereich, sonst die Messpunkte."""
        mo = self.modell
        if mo is None:
            return [], None
        pk, normalen = [], []
        z = self.markiert_z
        for nr, (a, b, _, n) in enumerate(mo.linien):
            kn = mo.linien_id[nr] if nr < len(mo.linien_id) else None
            if (kn is not None and kn in self.markiert) or \
                    (z is not None and z[0] - 1e-6 <= a[2] <= z[1] + 1e-6 and z[0] - 1e-6 <= b[2] <= z[1] + 1e-6):
                pk += [a, b]
                normalen.append(n)
        if not pk and self.markiert:        # Merkmal nur als Fläche (netz 'ti')
            for (i, j, k, _, n), kn in zip(mo.dreiecke, mo.dreiecke_id):
                if kn in self.markiert:
                    pk += [mo.punkte[i], mo.punkte[j], mo.punkte[k]]
                    normalen.append(n)
        if not pk:
            pk = list(self.messpunkte) or [q for punkte, _ in self.masse_fest[-1:] for q in punkte]
        if not normalen:
            return pk, None
        s = [sum(n[i] for n in normalen) for i in range(3)]
        betrag = math.sqrt(sum(c * c for c in s))
        return pk, (tuple(c / betrag for c in s) if betrag > 1e-6 else None)

    def auf_auswahl(self):
        """„Auf Auswahl“: senkrecht auf das gewählte Merkmal schauen (mittlere Normale) und es groß in die Mitte
        holen. False, wenn nichts gewählt ist."""
        pk, n = self.auswahl_punkte()
        if not pk:
            return False
        if n is not None:
            self.gier, self.nick = blick_auf(n)
        self.zoom, self.versatz = 1.0, (0.0, 0.0)
        bild = self.bildpunkt()
        px = [bild(v) for v in pk]
        x0, x1 = min(q[0] for q in px), max(q[0] for q in px)
        y0, y1 = min(q[1] for q in px), max(q[1] for q in px)
        w, h = max(1, self.width()), max(1, self.height())
        k = max(1.0, min(40.0, 0.45 * min(w / max(x1 - x0, 4.0), h / max(y1 - y0, 4.0))))
        self.zoom = k
        self.versatz = (-((x0 + x1) / 2 - w / 2) * k, -((y0 + y1) / 2 - h / 2) * k)
        self.update()
        self.gedreht.emit()
        return True

    def paintEvent(self, _):
        if self._gl is not None:        # zeichnet die OpenGL-Fläche (mit _beschriften)
            return
        p = QPainter(self)
        hintergrund_malen(p, self.rect())
        if self.modell is None:
            p.setPen(QColor("#7F7F7F"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Keine 3D-Daten.\nDie 3D-Ansicht gibt es für Teile, die per STEP-Import übernommen wurden.")
            return
        grob = self._eilig or self._maus is not None
        modell = self.modell.grob() if grob else self.modell
        schluessel = (modell, self.width(), self.height(), self.devicePixelRatioF(), self.gier, self.nick,
                      self.zoom, self.versatz, self.darstellung, self.blass(), self.perspektive)
        if self._bild is None or self._bild[0] != schluessel:
            dpr = self.devicePixelRatioF()
            bild = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
            bild.setDevicePixelRatio(dpr)
            bild.fill(Qt.transparent)
            q = QPainter(bild)
            zeichnen(q, modell, self.width(), self.height(), self.gier, self.nick, self.zoom, self.versatz,
                     linien=modell is self.modell, glatt=not grob, darstellung=self.darstellung, blass=self.blass(),
                     perspektive=self.perspektive)
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
        hinweis = self.werkzeug.hinweis() if self.werkzeug is not None and not self.messen else None
        p.drawText(QRectF(10, self.height() - 22, self.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   ("Winkel: drei Punkte anklicken, der mittlere ist der Scheitel" if self.mess_art == MESS_WINKEL
                    else "Messen: zwei Punkte anklicken (fängt Kreismitte, Kantenmitte, Ecke oder Fläche)"
                    if self.mess_max else
                    "Naht zeichnen: Punkte entlang der Naht anklicken (fängt die nächste Ecke)") if self.messen else
                   hinweis or
                   "Linke Maustaste drehen · rechte verschieben · Mausrad zoomen · Doppelklick Ausgangsansicht")

    def _markierung_zeichnen(self, p):
        """Hervorgehobene Linien (Teile-Editor), Messung und Werkzeug (Griffe, Maße) über dem Bild."""
        if self.werkzeug is not None:
            p.save()
            self.werkzeug.zeichnen(p, self.bildpunkt())
            p.restore()
        if not (self.markiert or self.markiert_z or self.messpunkte or self.masse_fest or self.schnitt_linie or
                self._schwebe):
            return
        bild = self.bildpunkt()
        if self.messen and self.mess_max:
            from .messen3d import fang_zeichnen
            for t in self.mess_treffer:
                fang_zeichnen(p, bild, t, MESSEN)
            if self._schwebe is not None:
                fang_zeichnen(p, bild, self._schwebe, FANG, beschriften=True)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.schnitt_linie:
            p.setPen(QPen(SCHNITT, 2.5, Qt.DashLine))
            pk = [bild(v) for v in self.schnitt_linie]
            for a, b in zip(pk, pk[1:]):
                p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
        p.setPen(QPen(MARKIERT, 4.0, Qt.SolidLine, Qt.RoundCap))
        z = self.markiert_z
        for nr, (a, b, _, _) in enumerate(self.modell.linien):
            kn = self.modell.linien_id[nr] if nr < len(self.modell.linien_id) else None
            if (kn is not None and kn in self.markiert) or \
                    (z is not None and z[0] - 1e-6 <= a[2] <= z[1] + 1e-6 and z[0] - 1e-6 <= b[2] <= z[1] + 1e-6):
                pa, pb = bild(a), bild(b)
                p.drawLine(QPointF(pa[0], pa[1]), QPointF(pb[0], pb[1]))
        offen = [] if self.mess_max and len(self.messpunkte) == self.mess_max else [(self.messpunkte, None)]
        for punkte, text in self.masse_fest + offen:
            if not punkte:
                continue
            pk = [bild(v) for v in punkte]
            p.setPen(QPen(MESSEN, 2.0))
            for a, b in zip(pk, pk[1:]):
                p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
            p.setBrush(QBrush(MESSEN))
            for q in pk:
                p.drawEllipse(QPointF(q[0], q[1]), 4, 4)
            p.setBrush(Qt.NoBrush)
            if text:
                m = pk[1] if len(pk) == 3 else ((pk[0][0] + pk[1][0]) / 2, (pk[0][1] + pk[1][1]) / 2)
                p.drawText(QRectF(m[0] + 8, m[1] - 20, 360, 18), Qt.AlignLeft | Qt.AlignVCenter, text)

    def mousePressEvent(self, e):
        w = self.werkzeug
        if w is not None and self.modell is not None and not self.messen and w.druck(e.position(), e.button()):
            self._werkzeug_zieht = True
            return
        self._maus = (e.position(), e.button())
        self._druck = e.position() if e.button() == Qt.LeftButton else None
        self._rechts = e.position() if e.button() == Qt.RightButton else None

    def mouseMoveEvent(self, e):
        if self._werkzeug_zieht:
            self.werkzeug.ziehen(e.position(), e.modifiers())
            return
        if not self._maus:
            if self.werkzeug is not None and self.modell is not None and not self.messen:
                self.werkzeug.schweben(e.position())
            elif self.messen and self.mess_max and self.modell is not None:
                t = self.geometrie().fangen(self.bildpunkt(), e.position().x(), e.position().y(), mit_flaeche=False)
                if (t and (t["art"], tuple(t["punkt"]))) != (self._schwebe and (self._schwebe["art"],
                                                                               tuple(self._schwebe["punkt"]))):
                    self._schwebe = t
                    self.update()
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
        if self._werkzeug_zieht:
            self._werkzeug_zieht = False
            self.werkzeug.loslassen(e.position() if e is not None else None)
            self.update()
            return
        self._maus = None
        druck, self._druck = self._druck, None
        rechts, self._rechts = self._rechts, None
        if druck is not None and e is not None and (e.position() - druck).manhattanLength() < 4:
            self.klicken(e.position().x(), e.position().y())
        elif (rechts is not None and e is not None and self.werkzeug is not None
              and (e.position() - rechts).manhattanLength() < 4):
            self.werkzeug.kontext(e.position(), e.globalPosition().toPoint())      # Rechtsklick ohne Ziehen: Menü
        self.update()

    def _messen_klick(self, bild, x, y):
        """Messen (2 Punkte) bzw. Winkel (3): fängt Kreismitte, Kantenmitte, Ecke, Punkt auf einer Linie oder Fläche
        mit exakter Geometrie (messen3d); Kernwerte und Ergebnis in der Mess-Tafel."""
        geo = self.geometrie()
        t = geo.fangen(bild, x, y, self._dreieck_unter)
        if t is None:
            return None
        if len(self.messpunkte) >= self.mess_max:
            self.messpunkte, self.mess_treffer = [], []
        self.messpunkte.append(tuple(t["punkt"]))
        self.mess_treffer.append(t)
        fertig = len(self.messpunkte) == self.mess_max
        zeilen = []
        if fertig and self.mess_art == MESS_WINKEL:
            zeilen = [self.mess_text()] + [f"{n + 1}: {geo.kernwerte(q)[0]}" for n, q in enumerate(self.mess_treffer)]
        elif fertig:
            _, zeilen = geo.vergleich(*self.mess_treffer)
            zeilen += [f"{n + 1}: {geo.kernwerte(q)[0]}" for n, q in enumerate(self.mess_treffer)]
        else:
            zeilen = geo.kernwerte(t)
            if self.mess_max:
                zeilen.append(f"Punkt {len(self.messpunkte) + 1} von {self.mess_max} anklicken")
        self.tafel.zeigen(zeilen)
        if fertig:
            self.masse_fest.append((list(self.messpunkte), self.mess_text()))
        self.update()
        if fertig:
            self.gemessen.emit(self.winkel() if self.mess_art == MESS_WINKEL else self.abstand())
        return t["punkt"]

    def _dreieck_unter(self, bild, x, y):
        """Vorderstes Dreieck unter dem Pixel (x, y): (Nummer, Punkt im Modell) oder None."""
        mo = self.modell
        beste = None
        for nr, (i, j, k, _, _) in enumerate(mo.dreiecke):
            a, b, c = bild(mo.punkte[i]), bild(mo.punkte[j]), bild(mo.punkte[k])
            if min(a[0], b[0], c[0]) > x or max(a[0], b[0], c[0]) < x or min(a[1], b[1], c[1]) > y or \
                    max(a[1], b[1], c[1]) < y:
                continue
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-6:
                continue
            tiefe = l1 * a[2] + l2 * b[2] + l3 * c[2]
            if beste is None or tiefe > beste[0]:
                pa, pb, pc = mo.punkte[i], mo.punkte[j], mo.punkte[k]
                beste = (tiefe, nr, tuple(l1 * pa[m] + l2 * pb[m] + l3 * pc[m] for m in range(3)))
        return None if beste is None else (beste[1], beste[2])

    def mouseDoubleClickEvent(self, e):
        if self.werkzeug is not None and e is not None and self.werkzeug.doppelklick(e.position()):
            return
        ziel = getattr(self, "doppelklick_ziel", None)
        if ziel is not None and e is not None and self.auf_modell(e.position().x(), e.position().y()):
            ziel()                      # z. B. 3D-Ansicht der Positionen: Teil im Editor öffnen (Plan 3D-Editor F1)
            return
        self.zuruecksetzen()

    def auf_modell(self, x, y):
        """Liegt das Pixel (x, y) auf dem Modell (irgendeinem Dreieck)?"""
        mo = self.modell
        if mo is None:
            return False
        bild = self.bildpunkt()
        for i, j, k, _, _ in mo.dreiecke:
            a, b, c = bild(mo.punkte[i]), bild(mo.punkte[j]), bild(mo.punkte[k])
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
            if min(l1, l2, 1 - l1 - l2) >= -1e-6:
                return True
        return False

    def keyPressEvent(self, e):
        k = e.key()
        if e.modifiers() & Qt.ControlModifier and k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            self.drehen(-1 if k == Qt.Key_Left else 1 if k == Qt.Key_Right else 0,
                        1 if k == Qt.Key_Up else -1 if k == Qt.Key_Down else 0)
            e.accept()
            return
        if self.werkzeug is not None and self.werkzeug.taste(e):
            e.accept()
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        self.zoom = max(0.2, min(40.0, self.zoom * (1.15 ** (e.angleDelta().y() / 120))))
        self._eilig = True
        self._ruhe.start()
        self.update()


class Ansicht3DMitKnoepfen(QWidget):
    """Ansicht mit der gemeinsamen Leiste der 3D-Fenster (Blick, Darstellung, Perspektive, Messen) und dem
    Ansichtswürfel oben rechts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from .ansicht3d_leiste import Leiste3D
        from .ansichtswuerfel import Ansichtswuerfel, an_ecke
        self.ansicht = Ansicht3D()
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.knoepfe = QWidget()
        leiste = QHBoxLayout(self.knoepfe)
        leiste.setContentsMargins(0, 0, 0, 0)
        self.leiste = Leiste3D(self.ansicht)
        leiste.addWidget(self.leiste, 1)
        self.wuerfel = Ansichtswuerfel(self.ansicht)
        an_ecke(self.wuerfel)
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
