"""Ovale Profilformen (Plan ArTube-Unterlagen G1, Patrick 12.11.2026 „Alles einbauen“): Flachoval, Halbflachoval und
Elliptisch. Maße wie beim Rechteckrohr: A = Breite (waagrecht, die lange Achse), B = Höhe, Wandstärke.

- Flachoval: zwei gerade Seiten (Länge A − B) oben und unten, an den Enden Halbkreise mit Ø B.
- Halbflachoval: unten gerade (Breite A), oben die obere Hälfte eines Flachovals der Höhe 2 × B (gerade Länge
  A − 2 × B, Viertelkreise mit Radius B); braucht A ≥ 2 × B.
- Elliptisch: Ellipse mit den Achsen A und B (Umfang nach Ramanujan).
Gewicht (Querschnitt außen − innen, innen um die Wandstärke kleiner), Umfang (gerader Trennschnitt) und Umriss für
Bilder. Ohne Qt."""
import math

FLACHOVAL, HALBFLACHOVAL, ELLIPTISCH = "Flachoval", "Halbflachoval", "Elliptisch"
FORMEN = (FLACHOVAL, HALBFLACHOVAL, ELLIPTISCH)
PUNKTE = 48


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _ellipse_umfang(a, b):
    p, q = a / 2, b / 2
    return math.pi * (3 * (p + q) - math.sqrt((3 * p + q) * (p + 3 * q)))


def gueltig(form, a, b):
    a, b = _n(a), _n(b)
    if a <= 0 or b <= 0:
        return False
    if form == FLACHOVAL:
        return a >= b
    if form == HALBFLACHOVAL:
        return a >= 2 * b
    return form == ELLIPTISCH


def umfang(form, a, b):
    """Außenumfang [mm] oder 0 bei ungültigen Maßen."""
    a, b = _n(a), _n(b)
    if not gueltig(form, a, b):
        return 0.0
    if form == FLACHOVAL:
        return 2 * (a - b) + math.pi * b
    if form == HALBFLACHOVAL:
        return a + (a - 2 * b) + math.pi * b
    return _ellipse_umfang(a, b)


def _flaeche_voll(form, a, b):
    if a <= 0 or b <= 0:
        return 0.0
    if form == FLACHOVAL:
        return (a - b) * b + math.pi * b * b / 4
    if form == HALBFLACHOVAL:
        return (a - 2 * b) * b + math.pi * b * b / 2
    return math.pi * a * b / 4


def flaeche(form, a, b, wand):
    """Querschnitt [mm²] (außen − innen) oder None bei ungültigen Maßen."""
    a, b, s = _n(a), _n(b), _n(wand)
    if not gueltig(form, a, b) or s <= 0:
        return None
    innen = _flaeche_voll(form, a - 2 * s, b - 2 * s) if _innen_gueltig(form, a, b, s) else 0.0
    return _flaeche_voll(form, a, b) - innen


def _innen_gueltig(form, a, b, s):
    return gueltig(form, a - 2 * s, b - 2 * s)


def _umriss(form, a, b, v0=0.0):
    """Polygon (u, v) außen, Mitte des Hüllrechtecks bei (0, v0)."""
    pts = []
    if form == FLACHOVAL:
        r, g = b / 2, (a - b) / 2
        for i in range(PUNKTE // 2 + 1):            # rechter Halbkreis von oben nach unten
            w = math.pi / 2 - math.pi * i / (PUNKTE // 2)
            pts.append((g + r * math.cos(w), v0 + r * math.sin(w)))
        for i in range(PUNKTE // 2 + 1):            # linker Halbkreis von unten nach oben
            w = -math.pi / 2 - math.pi * i / (PUNKTE // 2)
            pts.append((-g + r * math.cos(w), v0 + r * math.sin(w)))
    elif form == HALBFLACHOVAL:
        r, g, unten = b, (a - 2 * b) / 2, v0 - b / 2
        pts = [(-a / 2, unten), (a / 2, unten)]
        for i in range(PUNKTE // 4 + 1):            # rechts unten -> oben
            w = math.pi / 2 * i / (PUNKTE // 4)
            pts.append((g + r * math.cos(w), unten + r * math.sin(w)))
        for i in range(PUNKTE // 4 + 1):            # oben -> links unten
            w = math.pi / 2 + math.pi / 2 * i / (PUNKTE // 4)
            pts.append((-g + r * math.cos(w), unten + r * math.sin(w)))
    else:
        for i in range(PUNKTE):
            w = 2 * math.pi * i / PUNKTE
            pts.append((a / 2 * math.sin(w), v0 + b / 2 * math.cos(w)))
    return pts


def umriss(form, a, b, wand):
    """[außen, innen] als Polygone für Bilder (Ansicht von A), Mitte (0, 0); [] bei ungültigen Maßen."""
    a, b, s = _n(a), _n(b), _n(wand)
    if not gueltig(form, a, b):
        return []
    out = [_umriss(form, a, b)]
    if s > 0 and _innen_gueltig(form, a, b, s):      # innen überall um die Wand kleiner, gleiche Mitte
        out.append(_umriss(form, a - 2 * s, b - 2 * s))
    return out
