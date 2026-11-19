"""Freie 3D-Navigation (Patrick 19.11.2026 „360°-Rotation im STEP-Viewer und 3D-Editor verbessern“). Ohne Qt.

Ursache der bisherigen Anschläge: Die Kamera aller 3D-Fenster (ansicht3d.Ansicht3D, auch STEP-Viewer, Teile-,
Blech-, Baugruppen- und Satz-Editor) bestand aus zwei Winkeln gier (um die Hochachse) und nick (Kippen); nick wurde
beim Ziehen auf ±1,55 rad (±89°) und mit Strg+Pfeil auf ±1,5 rad begrenzt. Über Kopf oder unter das Modell ging es
deshalb nicht, an der Grenze blieb die Drehung stehen. Eine Drehung um die Blickachse gab es nicht.

Jetzt: Lage = Drehmatrix aus drei Winkeln M = Rz(roll) · Rx(nick) · Ry(gier) · Grundstellung (ZXY, deckt jede Lage
ab). Beim Ziehen wird die kleine Drehung im Bildschirm (waagrecht um die Bildschirm-Hochachse, senkrecht um die
Bildschirm-Querachse) vor die Matrix gesetzt und die Matrix wieder in die drei Winkel zerlegt (zerlegen). Weil die
Matrix gerechnet wird und nicht die Winkel, gibt es keinen Anschlag, keinen Rücksprung und keine Gimbal-Sperre; jede
Umdrehung geht beliebig oft. Gezeichnet wird nur mit der Matrix: die Bauteilkoordinaten ändern sich nie.

Drehart „Drehteller“ (Einstellung): wie bisher um die Hochachse des Modells, Kippen jetzt aber ohne Grenze.
Einstellungen je Arbeitsplatz (teilen.LOKAL): Drehart, Drehtempo, Richtung waagrecht/senkrecht umkehren, Zoom- und
Verschiebetempo, Drehzentrum, Nachlauf (Trägheit, Vorgabe aus)."""
import math

DREH_GRUND = 0.012          # rad je Pixel bei Tempo 1 (wie bisher)
FREI, DREHTELLER = "frei (alle Achsen)", "Drehteller (Hochachse bleibt)"
DREHARTEN = (FREI, DREHTELLER)
UNTER_MAUS, MITTE, AUSWAHL = "Punkt unter der Maus", "Modellmitte", "Gewähltes (Auswahl)"
DREHZENTREN = (UNTER_MAUS, MITTE, AUSWAHL)
# Einstellungen (Name, Vorgabe)
VORGABEN = {"nav_drehart": FREI, "nav_dreh_tempo": 1.0, "nav_umkehren_h": "nein", "nav_umkehren_v": "nein",
            "nav_zoom_tempo": 1.0, "nav_schiebe_tempo": 1.0, "nav_drehzentrum": UNTER_MAUS, "nav_traegheit": "nein"}
NAMEN = tuple(VORGABEN)
BASIS = ((0, 0, 1), (0, 1, 0), (-1, 0, 0))      # Rohrachse Z in der Grundstellung waagerecht nach rechts
BASIS_T = tuple(tuple(BASIS[c][r] for c in range(3)) for r in range(3))


def mal(a, b):
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))


def rx(w):
    c, s = math.cos(w), math.sin(w)
    return ((1, 0, 0), (0, c, -s), (0, s, c))


def ry(w):
    c, s = math.cos(w), math.sin(w)
    return ((c, 0, s), (0, 1, 0), (-s, 0, c))


def rz(w):
    c, s = math.cos(w), math.sin(w)
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def matrix(gier, nick, roll=0.0):
    """Drehmatrix Modell -> Bildschirm (x rechts, y oben, z zum Betrachter)."""
    m = mal(rx(nick), mal(ry(gier), BASIS))
    return mal(rz(roll), m) if roll else m


def zerlegen(m):
    """(gier, nick, roll) zur Drehmatrix m (ohne Grundstellung gerechnet); nick in [−90°, 90°], bei ±90° roll aus
    der Matrix und gier = 0 (dieselbe Lage, keine Sperre)."""
    r = mal(m, BASIS_T)
    nick = math.atan2(r[2][1], math.hypot(r[2][0], r[2][2]))
    if math.cos(nick) > 1e-9 and math.hypot(r[2][0], r[2][2]) > 1e-9:
        gier = math.atan2(-r[2][0], r[2][2])
        roll = math.atan2(-r[0][1], r[1][1])
    else:
        gier = 0.0
        roll = math.atan2(r[1][0], r[0][0])
    return gier, nick, roll


def _winkel(w):
    return (w + math.pi) % (2 * math.pi) - math.pi


def ziehen(gier, nick, roll, dx, dy, werte=None):
    """Neue (gier, nick, roll) nach einer Mausbewegung um (dx, dy) Pixel (y nach unten)."""
    w = werte or {}
    k = DREH_GRUND * float(w.get("nav_dreh_tempo") or 1.0)
    a = dx * k * (-1 if w.get("nav_umkehren_h") == "ja" else 1)
    b = dy * k * (-1 if w.get("nav_umkehren_v") == "ja" else 1)
    if w.get("nav_drehart") == DREHTELLER:
        return _winkel(gier + a), _winkel(nick + b), roll
    m = mal(rx(b), mal(ry(a), matrix(gier, nick, roll)))
    return zerlegen(m)


def um_achse(gier, nick, roll, achse, winkel):
    """Um eine Bildschirmachse ('x' quer, 'y' hoch, 'z' Blickachse) um winkel [rad] drehen (Tastatur, Eingabe)."""
    d = {"x": rx, "y": ry, "z": rz}[achse](winkel)
    return zerlegen(mal(d, matrix(gier, nick, roll)))


def um_modellachse(gier, nick, roll, achse, winkel):
    """Um eine Achse des Modells ('X', 'Y', 'Z') um winkel [rad] drehen."""
    m = matrix(gier, nick, roll)
    n = [m[r]["XYZ".index(achse)] for r in range(3)]       # Modellachse im Bildschirm
    c, s = math.cos(winkel), math.sin(winkel)
    x, y, z = n
    d = ((c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s),
         (y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s),
         (z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)))
    return zerlegen(mal(d, m))


def werte_lesen(db):
    """Navigationseinstellungen dieses Arbeitsplatzes (Vorgaben, wenn nichts gespeichert oder lesbar)."""
    out = dict(VORGABEN)
    if db is None:
        return out
    for n in NAMEN:
        try:
            v = db.einstellung(n)
        except Exception:       # noqa: BLE001 – Lesemodus: Vorgabe
            v = None
        if v not in (None, ""):
            out[n] = v
    for n in ("nav_dreh_tempo", "nav_zoom_tempo", "nav_schiebe_tempo"):
        try:
            out[n] = min(5.0, max(0.1, float(out[n])))
        except (TypeError, ValueError):
            out[n] = 1.0
    return out
