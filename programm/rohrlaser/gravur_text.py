"""Text-Gravur (Patrick 24.10.2026: Positions- bzw. Artikelnummer auf Bleche und Rohre gravieren): eine
Einstrich-Schrift, wie sie der Laser graviert (jede Linie einmal, keine Umrissschrift). Gemeinsam für Blech-Editor,
Schneidweg-Rechner (Konturart schneidweg.TEXT_GRAVUR) und STEP-Export (3D-Editor).

Raster je Zeichen 4 breit, 6 hoch (Versalhöhe = Schrifthöhe), Abstand 2. Kleinbuchstaben werden als Großbuchstaben
graviert, ä/ö/ü als A/O/U, ß als SS; unbekannte Zeichen als '?'. Die Gravurlänge ist die Länge aller Striche, ohne
Leerfahrten. Ganz ohne Annahmen über eine installierte Schrift: jeder Rechner rechnet dieselbe Länge.
"""
import math

BREITE, HOEHE, ABSTAND = 4.0, 6.0, 2.0
_O = [(1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)]
_P = [(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]
ZEICHEN = {
    "0": [_O, [(0, 1), (4, 5)]],
    "1": [[(1, 5), (2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "2": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (0, 0), (4, 0)]],
    "3": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "4": [[(3, 0), (3, 6), (0, 2), (4, 2)]],
    "5": [[(4, 6), (0, 6), (0, 3), (3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    "6": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]],
    "7": [[(0, 6), (4, 6), (1, 0)]],
    "8": [[(1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1, 3), (0, 2), (0, 1), (1, 0), (3, 0),
           (4, 1), (4, 2), (3, 3)]],
    "9": [[(4, 3), (1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "A": [[(0, 0), (0, 4), (2, 6), (4, 4), (4, 0)], [(0, 2), (4, 2)]],
    "B": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    "C": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "D": [[(0, 0), (0, 6), (2, 6), (4, 4), (4, 2), (2, 0), (0, 0)]],
    "E": [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]],
    "F": [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    "G": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (2, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(1, 6), (3, 6)], [(2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "J": [[(4, 6), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "K": [[(0, 0), (0, 6)], [(4, 6), (0, 2)], [(1, 3), (4, 0)]],
    "L": [[(0, 6), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    "N": [[(0, 0), (0, 6), (4, 0), (4, 6)]],
    "O": [_O],
    "P": [_P],
    "Q": [_O, [(2, 2), (4, 0)]],
    "R": [_P, [(2, 3), (4, 0)]],
    "S": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 4), (1, 3), (3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "T": [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    "U": [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    "V": [[(0, 6), (2, 0), (4, 6)]],
    "W": [[(0, 6), (1, 0), (2, 3), (3, 0), (4, 6)]],
    "X": [[(0, 0), (4, 6)], [(0, 6), (4, 0)]],
    "Y": [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]],
    "Z": [[(0, 6), (4, 6), (0, 0), (4, 0)]],
    "-": [[(1, 3), (3, 3)]],
    "_": [[(0, 0), (4, 0)]],
    ".": [[(2, 0), (2, 0.5)]],
    ",": [[(2, 0.5), (1.5, -1)]],
    "/": [[(0, 0), (4, 6)]],
    "+": [[(2, 1), (2, 5)], [(0, 3), (4, 3)]],
    "(": [[(3, 6), (2, 5), (2, 1), (3, 0)]],
    ")": [[(1, 6), (2, 5), (2, 1), (1, 0)]],
    "#": [[(1, 0), (1, 6)], [(3, 0), (3, 6)], [(0, 2), (4, 2)], [(0, 4), (4, 4)]],
    " ": [],
    "?": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (2, 3), (2, 2)], [(2, 0), (2, 0.5)]],
}
ERSATZ = {"Ä": "A", "Ö": "O", "Ü": "U", "ß": "SS", "×": "X", "Ø": "0"}


def zeichen(text):
    """Text so, wie er graviert wird (Großbuchstaben, Ersatzzeichen, unbekannte als '?')."""
    out = ""
    for c in str(text or "").upper():
        c = ERSATZ.get(c, c)
        out += "".join(x if x in ZEICHEN else "?" for x in c)
    return out


def linien(text, hoehe):
    """Striche des Texts als Polylinien [[(x, y), …], …] in mm bei Schrifthöhe hoehe (Versalhöhe), Mitte des Texts
    bei (0, 0), ohne Drehung (x nach rechts, y nach oben)."""
    t = zeichen(text)
    s = float(hoehe or 0) / HOEHE
    if not t or s <= 0:
        return []
    breite = len(t) * (BREITE + ABSTAND) - ABSTAND
    out = []
    for i, c in enumerate(t):
        x0 = i * (BREITE + ABSTAND) - breite / 2
        for zug in ZEICHEN[c]:
            out.append([(round((x0 + x) * s, 3), round((y - HOEHE / 2) * s, 3)) for x, y in zug])
    return out


def masse(text, hoehe):
    """(Breite, Höhe) des Texts in mm (Hüllrechteck der Schrift)."""
    t = zeichen(text)
    s = float(hoehe or 0) / HOEHE
    return (max(len(t) * (BREITE + ABSTAND) - ABSTAND, 0) * s, HOEHE * s if t else 0.0)


def laenge(text, hoehe):
    """Gravurlänge [mm]: Summe aller Striche."""
    return sum(math.dist(a, b) for zug in linien(text, hoehe) for a, b in zip(zug, zug[1:]))


def gedreht(zuege, winkel, x=0.0, y=0.0):
    """Polylinien um winkel [°] (gegen den Uhrzeigersinn) drehen und nach (x, y) schieben."""
    w = math.radians(float(winkel or 0))
    c, s = math.cos(w), math.sin(w)
    return [[(x + px * c - py * s, y + px * s + py * c) for px, py in zug] for zug in zuege]


def lage_laengs(laenge, belegt, breite, abstand=0.5):
    """Mitte x [mm] einer Gravur der Breite breite längs eines Rohrs der Länge laenge: dort, wo sie den größten
    Abstand zu Rohranfang, Rohrende und den belegten Bereichen [(x von, x bis)] (Konturen auf derselben Seite) hat.
    Ergebnis (x, Abstand [mm]) oder None, wenn kein Platz mit mindestens abstand bleibt."""
    lg = float(laenge or 0)
    if lg <= 0 or breite <= 0:
        return None
    sperr = sorted([(-1e9, 0.0), (lg, 1e9)] + [(min(a, b), max(a, b)) for a, b in belegt or ()])
    best = None
    ende = sperr[0][1]
    for a, b in sperr[1:]:
        luecke = a - ende
        frei = (luecke - breite) / 2
        if frei >= abstand and (best is None or frei > best[1]):
            best = (round(ende + luecke / 2, 1), round(frei, 2))
        ende = max(ende, b)
    return best
