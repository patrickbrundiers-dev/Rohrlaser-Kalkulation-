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


def folge(lagen, m=None, laenge=None):
    """Anfahrpunkte [(x [mm], Winkel [°] oder None)] in Schneidfolge; None, wenn eine Kontur keine Lage hat. Ohne
    Dynamik längs des Rohrs sortiert; mit Eilgang und Drehzahl der Maschine (m) die Folge mit der kürzesten Leerzeit
    (schneidfolge.tour, Patrick 16.11.2026 „so wenig unnötige Wege wie nötig“) vom Anfangsschnitt (x = 0) zum
    Endschnitt (x = laenge)."""
    pkt = []
    for d in lagen:
        if d.get("x") is None or d.get("verteilt"):
            return None
        ein = d.get("eingabe") or {}
        pkt.append((_n(d["x"]) + _n(ein.get("_dx")), winkel_der_seite(ein.get("seite"))))
    pkt.sort(key=lambda t: t[0])
    if not aktiv_verfahren(m) or len(pkt) < 3:
        return pkt
    from .schneidfolge import tour
    v, a = _n(m["eilgang_x"]) / 60, _n(m["beschl_x"])
    dreh = aktiv_drehen(m)
    vw, aw = _n(m.get("drehzahl")) * 6.0, _n(m.get("beschl_dreh"))

    def t(p, q):
        tx = bewegung(abs(q[0] - p[0]) / 1000, v, a)
        tw = bewegung(abs((q[1] - p[1] + 180) % 360 - 180), vw, aw) \
            if dreh and p[1] is not None and q[1] is not None else 0.0
        return max(tx, tw)
    s = lambda j: t((0.0, None), pkt[j])                                  # noqa: E731
    e = (lambda i: t(pkt[i], (_n(laenge), None))) if laenge else None    # noqa: E731
    reihe = [pkt[i] for i in tour(len(pkt), lambda i, j: t(pkt[i], pkt[j]), s, e)]
    gesamt = lambda r: sum(t(p, q) for p, q in zip([(0.0, None)] + r, r + ([(_n(laenge), None)] if laenge  # noqa: E731
                                                                         else [r[-1]])))
    return reihe if gesamt(reihe) < gesamt(pkt) - 1e-9 else pkt


def _zahl(w):
    return isinstance(w, (int, float)) and not isinstance(w, bool)


def kopfweg_aktiv(m):
    """Phase 5: Leerwege mit Kopfweg rechnen (Feld 'Kopf heben ab Weg' und Kopfhub Z mit Eilgang/Beschleunigung Z)."""
    m = m or {}
    return _zahl(m.get("hub_ab_weg")) and _n(m.get("hub_z")) > 0 and _n(m.get("eilgang_z")) > 0 \
        and _n(m.get("beschl_z")) > 0


def _hub_t(h_mm, m):
    """Kopf um h [mm] heben oder senken [s] mit Eilgang und Beschleunigung Z."""
    return bewegung(_n(h_mm) / 1000, _n(m.get("eilgang_z")) / 60, _n(m.get("beschl_z")))


def _flaeche_abstand(profil, w):
    """Abstand Achse – Fläche [mm] der Seite mit Winkel w: oben/unten halbe Abmessung A, vorne/hinten halbe B."""
    a = _n(profil.get("a"))
    b = _n(profil.get("b")) or a
    return (a if round(_n(w)) % 180 == 0 else b) / 2


def eck_radius(profil):
    """Größter Abstand Achse – Außenkante [mm], den die Ecken beim Drehen überstreichen: Kastenprofil halbe
    Diagonale mit Eckradius, offene und sonstige Profile halber Hüllkreis; Rundrohr None (dreht ohne Hub)."""
    if not profil or profil.get("form") == "Rundrohr":
        return None
    a = _n(profil.get("a"))
    b = _n(profil.get("b")) or a
    if a <= 0:
        return None
    if profil.get("form") in ("Quadratrohr", "Rechteckrohr"):
        from .stammdaten import _radius_wirksam
        r = min(_n(_radius_wirksam(profil)), a / 2, b / 2)
        return math.hypot(a / 2 - r, b / 2 - r) + r
    return math.hypot(a, b) / 2


def stange_mittel_kg(p, m, k):
    """Mittleres bewegtes Gewicht [kg] beim Schneiden des Teils: kg/m × (Stangenlänge + Teillänge) ÷ 2 (die Stange
    wird beim Abarbeiten kürzer, ein langes Teil hängt länger am Futter); None ohne Gewicht."""
    from .rechnen import kg_je_m
    kgm = kg_je_m(p.get("profil_id"), p.get("werkstoff_id"), k) if k else None
    if not kgm:
        return None
    stange = _n((m or {}).get("max_stange")) or 6500.0
    return kgm * (stange + _n(p.get("laenge"))) / 2000


def last_faktoren(m, kg):
    """(Faktor Beschleunigung X, Faktor Drehbeschleunigung) bei bewegtem Gewicht kg (Phase 5, Patrick 16.11.2026 „je
    länger und schwerer, umso langsamer dreht und verfährt der Laser“): bis „volle Dynamik bis“ 1, darüber
    Drehbeschleunigung × Grenze ÷ Gewicht (Trägheit wächst mit der Masse), Beschleunigung X × √(Grenze ÷ Gewicht)
    (der Vorschubwagen trägt einen Teil selbst); nie unter dem Mindestanteil. Ohne Felder (1, 1)."""
    voll = _n((m or {}).get("dyn_voll_kg"))
    if voll <= 0 or not kg or kg <= voll:
        return 1.0, 1.0
    mind = _n((m or {}).get("dyn_min")) / 100 or 0.0
    q = voll / kg
    return max(mind, math.sqrt(q)), max(mind, q)


def mit_last(m, kg):
    """Maschine mit den Beschleunigungen für das bewegte Gewicht (last_faktoren); unverändert ohne Last."""
    fx, fd = last_faktoren(m, kg)
    if fx >= 1 and fd >= 1:
        return m
    m = dict(m)
    if _n(m.get("beschl_x")):
        m["beschl_x"] = _n(m["beschl_x"]) * fx
    if _n(m.get("beschl_dreh")):
        m["beschl_dreh"] = _n(m["beschl_dreh"]) * fd
    return m


def leerweg_art(p, q, m, profil=None):
    """Leerweg vom Punkt p zum Punkt q (je (x [mm], Winkel [°] oder None)) wie der Laserkopf fährt (Phase 5, Patrick
    16.11.2026 „Kopf um das Material heben bei einer Drehung, bei längeren Wegen Kopf heben“):
    - Drehung über eine Kante (Kasten- und offene Profile, Winkel ändert sich): Kopf heben, bis die Ecke mit dem
      Sicherheitsabstand darunter durchdreht (Eckradius − Abstand der Fläche + Sicherheit, mindestens Kopfhub),
      drehen und verfahren, senken auf die Zielfläche: t_hoch + max(tx, tw) + t_runter;
    - Weg ab „Kopf heben ab Weg“: Froschsprung (Heben während der Fahrt) max(tx, tw, Heben + Senken), ohne
      Froschsprung nacheinander;
    - kürzerer Weg: Kopf bleibt unten, max(tx, tw).
    Danach je Anfahrt das Einschwingen der Abstandsregelung. Ergebnis dict(hub='kein'|'sprung'|'drehen',
    hoehe_mm, weg_mm, t_s); ohne Dynamik X t_s = None."""
    m = m or {}
    (x0, w0), (x1, w1) = p, q
    v, a = _n(m.get("eilgang_x")) / 60, _n(m.get("beschl_x"))
    tx = bewegung((_n(x1) - _n(x0)) / 1000, v, a)
    dw = abs((_n(w1) - _n(w0) + 180) % 360 - 180) if w0 is not None and w1 is not None else 0.0
    tw = bewegung(dw, _n(m.get("drehzahl")) * 6.0, _n(m.get("beschl_dreh"))) if dw > EPS and aktiv_drehen(m) else 0.0
    r_quer = (_n((profil or {}).get("a")) / 2) if profil else 0.0
    weg = math.hypot(_n(x1) - _n(x0), r_quer * math.radians(dw))
    regel = _n(m.get("zeit_regelung"))
    t_s = max(tx, tw) + regel if aktiv_verfahren(m) else None
    if not kopfweg_aktiv(m):
        return dict(hub="kein", hoehe_mm=0.0, weg_mm=weg, t_s=t_s)
    hub = _n(m.get("hub_z"))
    eck = eck_radius(profil) if dw > EPS else None
    if eck is not None:
        s = _n(m.get("hub_sicherheit"))
        hoch = max(hub, eck - _flaeche_abstand(profil, w0) + s)
        runter = max(hub, eck - _flaeche_abstand(profil, w1) + s)
        t = _hub_t(hoch, m) + max(tx, tw) + _hub_t(runter, m) + regel
        return dict(hub="drehen", hoehe_mm=hoch, weg_mm=weg, t_s=t if t_s is not None else None)
    if weg >= _n(m.get("hub_ab_weg")) - EPS and weg > EPS:
        th = 2 * _hub_t(hub, m)
        t = (max(tx, tw, th) if m.get("froschsprung") != "nein" else th + max(tx, tw)) + regel
        return dict(hub="sprung", hoehe_mm=hub, weg_mm=weg, t_s=t if t_s is not None else None)
    return dict(hub="kein", hoehe_mm=0.0, weg_mm=weg, t_s=t_s)


def leerweg_s(p, q, m, profil=None):
    """Zeit des Leerwegs p → q [s] (leerweg_art), None ohne Dynamik X; Kostenfunktion für die Schneidfolge."""
    return leerweg_art(p, q, m, profil)["t_s"]


def verfahrzeit(m, lagen, laenge=None, profil=None):
    """Leerwege zwischen den Konturen eines Teils [s] (Verfahren längs und Drehen, gleichzeitig) oder None, wenn
    die Dynamik nicht eingetragen ist oder Lagen fehlen. Mit laenge: vom Anfangsschnitt (x = 0) zur ersten und von
    der letzten Kontur zum Endschnitt (x = Länge). Mit profil und Kopfweg (kopfweg_aktiv, Phase 5): je Leerweg
    leerweg_s mit Heben, Drehen über die Kante und Einschwingen."""
    if not aktiv_verfahren(m) or not lagen:
        return None
    pkt = folge(lagen, m, laenge)
    if pkt is None:
        return None
    if laenge:
        pkt = [(0.0, None)] + pkt + [(_n(laenge), None)]
    m = m or {}
    if profil is not None and kopfweg_aktiv(m):
        return sum(leerweg_s(p0, p1, m, profil) for p0, p1 in zip(pkt, pkt[1:]))
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
