"""Drehzeit, Verfahrwege und Eckzeit aus der Maschinendynamik statt fester Zeiten (Patrick 12.11.2026 „Ja,
berechnen“, Plan ArTube-Unterlagen).

Maschinenfelder (leer = feste Zeiten wie bisher):
- 'Eilgang X [m/min]' und 'Beschleunigung X [m/s²]': Leerweg längs des Rohrs zwischen zwei Konturen;
- 'Drehzahl Spannfutter [U/min]' und 'Drehbeschleunigung [°/s²]': Drehen zur Seite der nächsten Kontur;
- 'Schneidbeschleunigung [m/s²]': an jeder Ecke bremst der Kopf auf 0 und beschleunigt wieder; Zeitverlust gegen
  gleichmäßige Fahrt = Vorschub ÷ Beschleunigung. Mit N₂ ab 6 mm gilt höchstens die Grenze aus LT8.20 Tabelle 6-1.

Bewegung mit Trapezprofil: kurzer Weg s ≤ v²/a nur Beschleunigen und Bremsen (2 × √(s/a)), sonst s/v + v/a.
Längs- und Drehbewegung laufen gleichzeitig, es zählt die längere. Die Konturen werden in der Reihenfolge ihrer
Lage längs des Rohrs angefahren (wie die Maschine von Ende A nach Ende B). Konturen ohne Lage: feste Zeiten.
Ohne Qt."""
import math

EPS = 1e-9
# Beschleunigungsgrenze der Schneidwerkzeuge mit N₂ [m/s²] ab Wand [mm] (LT8.20 Tabelle 6-1)
SCHNEID_BESCHL = ((6.0, 3.0), (8.0, 1.0), (10.0, 0.75), (12.0, 0.2))
KASTEN_WINKEL = {"oben": 0.0, "vorne": 90.0, "unten": 180.0, "hinten": 270.0}


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def bewegung(s, v, a):
    """Zeit [s] für den Weg s mit Höchstgeschwindigkeit v und Beschleunigung a (gleiche Einheit, z. B. m, m/s,
    m/s²); 0 ohne Weg."""
    s, v, a = abs(_n(s)), _n(v), _n(a)
    if s <= EPS or v <= 0 or a <= 0:
        return 0.0
    if s <= v * v / a:
        return 2 * math.sqrt(s / a)
    return s / v + v / a


def aktiv_verfahren(m):
    m = m or {}
    return _n(m.get("eilgang_x")) > 0 and _n(m.get("beschl_x")) > 0


def aktiv_drehen(m):
    m = m or {}
    return _n(m.get("drehzahl")) > 0 and _n(m.get("beschl_dreh")) > 0


def winkel_der_seite(seite):
    """Drehwinkel [°] einer Seitenangabe (Kasten: oben/vorne/unten/hinten, Rundrohr: Winkeltext); None unbekannt."""
    from . import skizze as sk
    t = str(seite or "")
    for name, w in KASTEN_WINKEL.items():
        if t == name or t.endswith(name):
            return w
    return sk.winkel_aus_text(t) if t else None


def folge(lagen):
    """Anfahrpunkte [(x [mm], Winkel [°] oder None)] in Reihenfolge längs des Rohrs; None, wenn eine Kontur keine
    Lage hat."""
    pkt = []
    for d in lagen:
        if d.get("x") is None or d.get("verteilt"):
            return None
        ein = d.get("eingabe") or {}
        pkt.append((_n(d["x"]) + _n(ein.get("_dx")), winkel_der_seite(ein.get("seite"))))
    return sorted(pkt, key=lambda t: t[0])


def verfahrzeit(m, lagen, laenge=None):
    """Leerwege zwischen den Konturen eines Teils [s] (Verfahren längs und Drehen, gleichzeitig) oder None, wenn
    die Dynamik nicht eingetragen ist oder Lagen fehlen. Mit laenge: vom Anfangsschnitt (x = 0) zur ersten und von
    der letzten Kontur zum Endschnitt (x = Länge)."""
    if not aktiv_verfahren(m) or not lagen:
        return None
    pkt = folge(lagen)
    if pkt is None:
        return None
    if laenge:
        pkt = [(0.0, None)] + pkt + [(_n(laenge), None)]
    m = m or {}
    v, a = _n(m["eilgang_x"]) / 60, _n(m["beschl_x"])
    dreh = aktiv_drehen(m)
    vw, aw = _n(m.get("drehzahl")) * 6.0, _n(m.get("beschl_dreh"))     # U/min -> °/s
    t = 0.0
    for (x0, w0), (x1, w1) in zip(pkt, pkt[1:]):
        tx = bewegung((x1 - x0) / 1000, v, a)
        tw = 0.0
        if dreh and w0 is not None and w1 is not None:
            tw = bewegung(abs((w1 - w0 + 180) % 360 - 180), vw, aw)
        t += max(tx, tw)
    return t


def schneid_beschleunigung(m, wand, gas):
    """Beschleunigung an Ecken [m/s²]: Maschinenfeld, mit N₂ ab 6 mm höchstens Tabelle 6-1; None = nicht
    eingetragen."""
    a = _n((m or {}).get("beschl_schnitt"))
    if a <= 0:
        return None
    if gas == "N₂":
        for ab, grenze in SCHNEID_BESCHL:
            if _n(wand) >= ab - EPS:
                a = min(a, grenze) if grenze > 0 else a
    return a


def ecke_s(vorschub_mm_min, a):
    """Zeitverlust je Ecke [s]: Bremsen auf 0 und wieder Beschleunigen gegen gleichmäßige Fahrt = v / a."""
    v = _n(vorschub_mm_min) / 60000
    return v / a if a and v > 0 else 0.0
