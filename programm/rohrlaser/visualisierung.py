"""Aussehen der 3D-Ansichten (3D-Visualisierungsupdate V2, Patrick 19.11.2026): Material, Lichtprofil, Hintergrund und
Kontaktschatten. Ohne Qt; die eine Quelle für beide Zeichenwege (ansicht3d.zeichnen mit QPainter und ansicht3d_gl mit
OpenGL), damit Software- und Grafikkarten-Bild gleich aussehen.

Grundregeln: Das Material färbt nur die neutralen Flächen (Außen-, Innenwand, Blech). Konturen, Gravuren, Schnitte,
Nähte, Kostentreiber und Teilfarben behalten ihre Signalfarben, sonst ginge Information verloren. Das Aussehen ändert
nie das Netz, die Konturen oder die Kalkulation. Einstellungen je Arbeitsplatz (teilen.LOKAL)."""
import math

STANDARD = "Standard (Farben nach Fläche)"
# Material: Farbe Außen (A, BL), Innen (I), Glanz, Glanz-Exponent (klein = breiter, weicher Glanz wie gebürstet)
MATERIALIEN = {
    STANDARD: dict(a="#B9C3CD", i="#8A96A3", glanz=0.22, exp=36.0),
    "Rohstahl": dict(a="#7E868F", i="#5F666D", glanz=0.12, exp=16.0),
    "Edelstahl": dict(a="#C3C9CF", i="#9AA1A8", glanz=0.40, exp=64.0),
    "Aluminium": dict(a="#CDD2D7", i="#A9AFB5", glanz=0.24, exp=26.0),
    "Lackiert (RAL 5010)": dict(a="#2F5F96", i="#244A75", glanz=0.38, exp=90.0),
    "Gebürstet": dict(a="#B4BAC0", i="#90979E", glanz=0.24, exp=9.0),
    "Matt": dict(a="#ABB3BB", i="#88919A", glanz=0.0, exp=1.0),
}
MATERIAL_ARTEN = ("A", "BL")    # Außenwand, Blech: Materialfarbe a; Innenwand I: Farbe i
# Licht: Hauptlicht, Fülllicht (Richtung im Bild: x rechts, y oben, z zum Betrachter), Grundlicht, Neigung (oben
# heller), Fülllicht-Stärke, Glanz-Faktor (mal Glanz des Materials)
LICHTPROFILE = {
    "Werkstatt": dict(licht=(-0.35, 0.45, 0.82), licht2=(0.55, -0.35, 0.76), grund=0.38, neigung=0.06, fuell=0.16,
                      glanz=1.0),
    "Studio": dict(licht=(-0.45, 0.6, 0.66), licht2=(0.7, 0.05, 0.71), grund=0.32, neigung=0.12, fuell=0.30,
                   glanz=1.25),
    "Hell": dict(licht=(-0.1, 0.35, 0.93), licht2=(0.5, -0.5, 0.71), grund=0.55, neigung=0.05, fuell=0.25, glanz=0.8),
    "Technisch (flach)": dict(licht=(-0.2, 0.3, 0.93), licht2=(0.0, 0.0, 1.0), grund=0.68, neigung=0.0, fuell=0.0,
                              glanz=0.0),
}
WERKSTATT = "Werkstatt"
# Hintergrund: Farbe oben, unten (Verlauf; gleich = einfarbig)
HINTERGRUENDE = {
    "Verlauf": ("#DCE3EA", "#FFFFFF"),
    "Weiß": ("#FFFFFF", "#FFFFFF"),
    "Hellgrau": ("#E9ECEF", "#E9ECEF"),
    "Studio (Blaugrau)": ("#B8C4D0", "#F4F6F8"),
}
VERLAUF = "Verlauf"
SCHATTEN_DECKKRAFT = 0.22       # Kontaktschatten unter dem Modell: Deckkraft in der Mitte (weich nach außen)
# Einstellungen (Name, Vorgabe) – nur dieser Arbeitsplatz
VORGABEN = {"ansicht3d_material": STANDARD, "ansicht3d_licht": WERKSTATT, "ansicht3d_hintergrund": VERLAUF,
            "ansicht3d_schatten": "ja"}
NAMEN = tuple(VORGABEN)
AUSWAHL = {"material3d": list(MATERIALIEN), "licht3d": list(LICHTPROFILE), "hintergrund3d": list(HINTERGRUENDE)}

_aktuell = dict(VORGABEN)


def setzen(werte):
    """Aussehen für alle 3D-Ansichten dieses Programmlaufs setzen; Unbekanntes fällt auf die Vorgabe zurück."""
    w = dict(VORGABEN)
    for n in NAMEN:
        v = (werte or {}).get(n)
        if v not in (None, ""):
            w[n] = v
    if w["ansicht3d_material"] not in MATERIALIEN:
        w["ansicht3d_material"] = STANDARD
    if w["ansicht3d_licht"] not in LICHTPROFILE:
        w["ansicht3d_licht"] = WERKSTATT
    if w["ansicht3d_hintergrund"] not in HINTERGRUENDE:
        w["ansicht3d_hintergrund"] = VERLAUF
    w["ansicht3d_schatten"] = "nein" if str(w["ansicht3d_schatten"]).lower() in ("nein", "false", "0", "aus") else "ja"
    _aktuell.clear()
    _aktuell.update(w)
    return dict(w)


def lesen(db):
    """Aussehen aus den Einstellungen dieses Arbeitsplatzes setzen (Vorgaben, wenn nichts lesbar)."""
    werte = {}
    for n in NAMEN:
        try:
            werte[n] = db.einstellung(n) if db is not None else None
        except Exception:       # noqa: BLE001 – Lesemodus: Vorgabe
            werte[n] = None
    return setzen(werte)


def aktuell():
    return dict(_aktuell)


def schluessel():
    """Merkmal des Aussehens für Bild-Zwischenspeicher (neues Aussehen = neu zeichnen)."""
    return tuple(_aktuell[n] for n in NAMEN)


def material():
    return MATERIALIEN[_aktuell["ansicht3d_material"]]


def licht():
    return LICHTPROFILE[_aktuell["ansicht3d_licht"]]


def hintergrund():
    """(oben, unten) als Hex-Farben."""
    return HINTERGRUENDE[_aktuell["ansicht3d_hintergrund"]]


def schatten_an():
    return _aktuell["ansicht3d_schatten"] == "ja"


def flaechenfarbe(art):
    """Hex-Farbe des Materials für eine neutrale Flächenart oder None (Signalfarbe der Art bleibt)."""
    if _aktuell["ansicht3d_material"] == STANDARD:
        return None
    m = material()
    if art in MATERIAL_ARTEN:
        return m["a"]
    if art == "I":
        return m["i"]
    return None


def _norm(v):
    b = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / b for c in v)


def licht_werte():
    """Werte für den Shader und licht_wert: (licht, licht2, grund, neigung, fuell, glanz, exp)."""
    li, m = licht(), material()
    return li["licht"], li["licht2"], li["grund"], li["neigung"], li["fuell"], m["glanz"] * li["glanz"], m["exp"]


def beleuchten(n, werte=None):
    """(Faktor für die Farbe, Glanz-Zugabe 0..1) zur Normalen n im Bild (zum Betrachter gedreht). Dieselbe Formel wie
    im OpenGL-Shader (ansicht3d_gl.VERTEX)."""
    l1, l2, grund, neig, fuell, glanz, exp = werte or licht_werte()
    nx, ny, nz = n
    hell = grund + neig * ny + (1 - grund) * max(0.0, nx * l1[0] + ny * l1[1] + nz * l1[2]) \
        + fuell * max(0.0, nx * l2[0] + ny * l2[1] + nz * l2[2])
    if glanz <= 0:
        return hell, 0.0
    h = _norm((l1[0], l1[1], l1[2] + 1.0))
    return hell, glanz * max(0.0, nx * h[0] + ny * h[1] + nz * h[2]) ** exp


def schatten_ellipse(punkte, breite, hoehe):
    """Kontaktschatten im Bild: (Mitte x, Mitte y, Halbachse x, Halbachse y) unter den Bildpunkten [(x, y)] des
    Modells, oder None (leer, ganz außerhalb). Nur Anzeige: weich, ohne Tiefe, hinter dem Modell."""
    if not punkte:
        return None
    xs = [p[0] for p in punkte]
    ys = [p[1] for p in punkte]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 < 0 or x0 > breite or y0 > hoehe or x1 - x0 < 2:
        return None
    rx = (x1 - x0) * 0.45
    ry = max(4.0, min((x1 - x0) * 0.045, 26.0))
    return (x0 + x1) / 2, y1 + ry * 0.35, rx, ry
