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


# --- Plan „Laserzeit vollständig berechnen“ Phase 2 (Patrick 16.11.2026): Radien, Ecken und kleine Konturen -------

def radius_s(vorschub_mm_min, r_mm, a_schnitt, m, winkel=90.0):
    """Mehrzeit [s] eines Radius bzw. einer Ecke (E2) gegenüber dem Bogen mit Vorschub: die Zeit am Radius ist der
    größte Wert aus Bogen ÷ Vorschub, Bogen ÷ √(Schneidbeschleunigung × Radius) (Querbeschleunigung) und dem
    Drehen um den Winkel mit Drehzahl und Drehbeschleunigung des Spannfutters (Kastenprofil: die Wand dreht an der
    Ecke um 90°). Scharfe Ecke (r = 0): Bremsen und Beschleunigen = Vorschub ÷ Schneidbeschleunigung. Ohne
    Schneidbeschleunigung und ohne Drehdynamik 0."""
    v = _n(vorschub_mm_min) / 60.0                       # [mm/s]
    if v <= 0:
        return 0.0
    r, a = max(0.0, _n(r_mm)), _n(a_schnitt) * 1000.0    # [mm], [mm/s²]
    bogen = math.pi / 2 * r * _n(winkel) / 90.0
    t_bahn = bogen / v
    t = t_bahn
    if a > 0:
        t = max(t, bogen / math.sqrt(a * r)) if r > EPS else t + v / a
    if aktiv_drehen(m):
        m = m or {}
        t = max(t, bewegung(_n(winkel), _n(m["drehzahl"]) * 6.0, _n(m["beschl_dreh"])))
    return max(0.0, t - t_bahn)


def kontur_dyn_s(lagen, vorschuebe, klasse, a_schnitt):
    """Mehrzeit [s] kleiner Konturen aus der Schneidbeschleunigung (E3): runde Teile (Bohrung, Senkung, Lochfeld,
    Langloch, Eckradien) laufen höchstens mit √(a × r), scharfe Ecken kosten Vorschub ÷ a. vorschuebe = (groß,
    mittel, klein) [mm/min], klasse(Hüllmaß) -> 0 klein, 1 mittel, 2 groß. Ohne Schneidbeschleunigung 0."""
    from .schneidweg import (AUSKLINKUNG, BOHRUNG, LANGLOCH, LOCHFELD, RECHTECK, SCHLITZ, SENKUNG, _z)
    a = _n(a_schnitt) * 1000.0
    if a <= 0:
        return 0.0
    h, i_, j = vorschuebe
    t = 0.0
    for d in lagen or ():
        e, art = d.get("eingabe") or {}, d.get("art")
        hk = _n(d.get("huelle"))
        v_mm_min = (j, i_, h)[klasse(hk)] if hk > 0 else h
        v = _n(v_mm_min) / 60.0
        if v <= 0:
            continue
        boegen, ecken = [], 0           # (Radius, Bogenlänge) und scharfe Ecken
        if art in (BOHRUNG, SENKUNG, LOCHFELD):
            r = _z(e.get("d")) / 2
            boegen.append((r, 2 * math.pi * r))
        elif art == LANGLOCH:
            r = _z(e.get("b")) / 2
            boegen.append((r, 2 * math.pi * r))
        elif art in (RECHTECK, AUSKLINKUNG):
            n_e = 4 if art == RECHTECK else 2
            r = _z(e.get("r"))
            if r > 0 and not _z(e.get("fase")):
                boegen += [(r, math.pi / 2 * r)] * n_e
            else:
                ecken += n_e * (2 if _z(e.get("fase")) else 1)
        elif art == SCHLITZ:
            ecken += 2
        for r, lg in boegen:
            if r <= EPS:
                continue
            v_max = math.sqrt(a * r)
            if v_max < v:
                t += lg / v_max - lg / v
        t += ecken * v / a
    return t
