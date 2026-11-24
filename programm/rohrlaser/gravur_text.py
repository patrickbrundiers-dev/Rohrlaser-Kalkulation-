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


# ------------------------------------------------------------------ Schablonenschrift (Plan ArTube D5)
def _auf_strecke(p, a, b, eps=1e-6):
    (px, py), (ax, ay), (bx, by) = p, a, b
    lg = math.dist(a, b)
    if lg < eps:
        return math.dist(p, a) < eps
    kreuz = abs((bx - ax) * (py - ay) - (by - ay) * (px - ax)) / lg
    t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / (lg * lg)
    return kreuz < eps and -eps <= t <= 1 + eps


def _schleife(zug):
    """Polylinie schließt eine Fläche ein (Anfang = Ende oder ein Ende liegt auf einem nicht benachbarten Stück)."""
    if len(zug) < 3:
        return False
    if math.dist(zug[0], zug[-1]) < 1e-6:
        return True
    st = list(zip(zug, zug[1:]))
    return any(_auf_strecke(zug[-1], a, b) for a, b in st[:-2]) or any(_auf_strecke(zug[0], a, b) for a, b in st[2:])


def _beruehren(z1, z2):
    """Anzahl Berührpunkte zweier Striche (Enden des einen auf dem anderen)."""
    st1, st2 = list(zip(z1, z1[1:])), list(zip(z2, z2[1:]))
    pkt = {p for p in (z1[0], z1[-1]) if any(_auf_strecke(p, a, b) for a, b in st2)}
    pkt |= {p for p in (z2[0], z2[-1]) if any(_auf_strecke(p, a, b) for a, b in st1)}
    return len(pkt)


def schablone(text, hoehe):
    """Text als durchgeschnittene Schablonenschrift (D5): jeder Strich der Einstrich-Schrift wird ein Schlitz der
    Strichbreite h/6, der an jeder Berührung mit einem anderen Strich durch einen Steg getrennt bleibt; ein Strich,
    der eine Fläche umschließt (O, 0, 8, P …), bekommt einen Steg, der das Innenteil hält.
    Ergebnis dict(laenge = Schnittlänge [mm] (beide Kanten jedes Schlitzes und die Enden), einstiche = Anzahl
    Schlitze, stege, breite = Strichbreite [mm])."""
    t = zeichen(text)
    s = float(hoehe or 0) / HOEHE
    if not t or s <= 0:
        return dict(laenge=0.0, einstiche=0, stege=0, breite=0.0)
    lg = stuecke = stege = 0
    for c in t:
        zuege = ZEICHEN[c]
        for i, zug in enumerate(zuege):
            lz = sum(math.dist(a, b) for a, b in zip(zug, zug[1:])) * s
            lg += 2 * lz + 2 * s                    # beide Kanten und die zwei Enden des Schlitzes
            stuecke += 1
            # Schleife: ein Steg hält das Innenteil; jede Berührung zweier Striche bleibt als Steg stehen
            stege += (1 if _schleife(zug) else 0) + sum(_beruehren(zug, z2) for z2 in zuege[i + 1:])
    return dict(laenge=round(lg, 3), einstiche=stuecke, stege=stege, breite=round(s, 3))
