"""3D-Schnittbearbeitung mit geschwenktem Laserkopf (Patrick 22.10.2026).

3D gibt es nur, wenn es ausdrücklich gewählt ist: Häkchen „3D-Schnittbearbeitung“ am Bauteil (positionen.technik
{d3: true}) und je Bearbeitung „3D“. Bearbeitungen in 3D sind
- Gehrung in 3D an Ende A oder B (technik a/b {d3: true}): der Kopf wird auf den Gehrungswinkel geschwenkt, die
  Schnittfläche ist eben durch die ganze Wand. Eine Gehrung ohne 3D bleibt der heutige 2D-Schnitt.
- schräge Bohrung (Kontur Bohrung {d3: true, neigung_l, neigung_q}).
Fasen werden nicht in 3D bearbeitet (Patrick: in der Praxis nicht zuverlässig).

Zwei Winkel nie verwechseln:
- Umfangswinkel = Lage am Rohr (Kontur 'seite'): Blick von Ende A, 0° oben, 90° rechts, 180° unten, 270° links.
- Neigung = Schwenk des Kopfes bzw. der Bohrungsachse gegen die Wandnormale, 0° = senkrecht zur Wand.
  Längsneigung neigung_l: + = beim Eintritt Richtung Ende B, − = Richtung Ende A.
  Querneigung neigung_q: + = im Uhrzeigersinn (von Ende A gesehen, Richtung 90°), − = gegen den Uhrzeigersinn.
  Gesamtwinkel γ: tan²γ = tan²(längs) + tan²(quer).

Grenzen: Maschine (maschinen.schwenk_min/schwenk_max, Vorgabe −45/+45). Ein Winkel außerhalb wird auf die Grenze
begrenzt (begrenzen, neigung_begrenzen, gehrung_begrenzen); jede Rechnung nimmt nur den begrenzten Winkel. Die
Position bekommt dann eine WARNUNG (Kontur nicht maßhaltig). Eine Gehrung in 3D braucht beim Drehen des Rohrs
beide Schwenkrichtungen, sie ist deshalb durch die kleinere der beiden Grenzen begrenzt.

Geometrie: Kopf um β geschwenkt = wirksame Schnittdicke Wand / cos β. Schräge Bohrung Ø d: Kontur auf der Wand ist
eine Ellipse mit den Halbachsen d/2 und d / (2 cos γ); innen tritt sie um Wand × tan versetzt aus.

Greifmaß (maschinen.greif_3d, Vorgabe 300 mm): nur für das letzte Teil einer Stange. Hinter ihm muss so viel Rest
bleiben, dass jede 3D-Bearbeitung mindestens das Greifmaß vom Stangenende entfernt ist: Rest ≥ Greifmaß − Abstand
der Bearbeitung vom Ende B des Teils (Gehrung in 3D an Ende B: Abstand 0, also das volle Greifmaß; an Ende A:
Teillänge; Bohrung: Teillänge − Lage x; Lage unbekannt: 0). Mit dem Greiferrest zählt das Größere, nie die Summe
(optimierung)."""
import json
import math

VORGABE_MIN, VORGABE_MAX = -45.0, 45.0
GREIFMASS = 300.0
SCHNELLWAHL = (-45, -30, 0, 30, 45)
GRENZE_ABS = 89.0          # mehr ist geometrisch kein Schwenk mehr
ENDE_A, ENDE_B, BOHRUNG = "Gehrung 3D Ende A", "Gehrung 3D Ende B", "Bohrung 3D"


def _z(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _zahl(w, stellen=1):
    t = f"{w:.{stellen}f}"
    return (t.rstrip("0").rstrip(".") if "." in t else t).replace(".", ",").replace("-", "−")


def winkel_zahl(w):
    """Winkel aus Zahl oder Text ('+30°', '−45', '30,5') als float; leer = 0. ValueError bei Text ohne Zahl,
    NaN und ±∞."""
    if w is None or w == "":
        return 0.0
    if isinstance(w, bool):
        raise ValueError("Winkel ungültig")
    if isinstance(w, str):
        t = w.strip().replace("°", "").replace("−", "-").replace("–", "-").replace(",", ".").replace(" ", "")
        try:
            w = float(t)
        except ValueError:
            raise ValueError(f"Winkel '{w}' ist keine Zahl") from None
    try:
        w = float(w)
    except (TypeError, ValueError):
        raise ValueError("Winkel ungültig") from None
    if not math.isfinite(w):
        raise ValueError("Winkel ungültig (unendlich oder keine Zahl)")
    return w


def kann_3d(m):
    """Maschine mit 3D-Bearbeitung (maschinen.d3 = ja)."""
    return (m or {}).get("d3") == "ja"


def grenzen(m):
    """(kleinster, größter) Schwenkwinkel der Maschine [°]; leer = −45/+45, immer min ≤ 0 ≤ max."""
    lo, hi = (m or {}).get("schwenk_min"), (m or {}).get("schwenk_max")
    lo = float(lo) if isinstance(lo, (int, float)) and math.isfinite(lo) else VORGABE_MIN
    hi = float(hi) if isinstance(hi, (int, float)) and math.isfinite(hi) else VORGABE_MAX
    return max(-GRENZE_ABS, min(lo, 0.0)), min(GRENZE_ABS, max(hi, 0.0))


def greifmass(m):
    g = (m or {}).get("greif_3d")
    return float(g) if isinstance(g, (int, float)) and g >= 0 else GREIFMASS


def _hinweis(v):
    return f"Winkel wurde auf {'maximal' if v > 0 else 'minimal'} {_zahl(v)}° begrenzt."


def begrenzen(winkel, m=None):
    """Zentrale Winkelbegrenzung: (verwendeter Winkel, Hinweis oder None). Innerhalb der Grenzen der Maschine
    unverändert, darüber bzw. darunter die Grenze (+60° -> +45°, −55° -> −45°). ValueError bei ungültiger Eingabe."""
    w = winkel_zahl(winkel)
    lo, hi = grenzen(m)
    v = max(lo, min(hi, w))
    return v, (_hinweis(v) if v != w else None)


def gesamtwinkel(laengs, quer):
    """Gesamtneigung [°] aus Längs- und Querneigung: tan²γ = tan²(längs) + tan²(quer)."""
    return math.degrees(math.atan(math.hypot(math.tan(math.radians(laengs)), math.tan(math.radians(quer)))))


def neigung_begrenzen(laengs, quer, m=None):
    """Neigung einer Bohrung begrenzen: (längs, quer, gesamt, Hinweis oder None). Grenze = Grenze der Maschine in
    Richtung des größeren Anteils; ist der Gesamtwinkel größer, werden beide Anteile im gleichen Verhältnis (der
    Tangens) verkleinert, die Richtung der Bohrung bleibt."""
    l_, q_ = winkel_zahl(laengs), winkel_zahl(quer)
    if abs(l_) >= 90 or abs(q_) >= 90:
        raise ValueError("Neigung muss zwischen −90° und +90° liegen")
    g = gesamtwinkel(l_, q_)
    lo, hi = grenzen(m)
    groesser = l_ if abs(l_) >= abs(q_) else q_
    grenze = hi if groesser >= 0 else -lo
    if g <= grenze + 1e-9:
        return l_, q_, g, None
    f = math.tan(math.radians(grenze)) / math.tan(math.radians(g))
    l2 = math.degrees(math.atan(math.tan(math.radians(l_)) * f))
    q2 = math.degrees(math.atan(math.tan(math.radians(q_)) * f))
    return l2, q2, grenze, f"Neigung wurde auf {_zahl(grenze)}° begrenzt (Eingabe {_zahl(g)}°)."


def gehrung_begrenzen(winkel, m=None):
    """Gehrung in 3D: Kopfschwenk = Gehrungswinkel (Betrag). Beim Drehen des Rohrs schwenkt der Kopf in beide
    Richtungen, es gilt die kleinere Grenze der Maschine. (verwendet, Hinweis oder None)."""
    w = abs(winkel_zahl(winkel))
    lo, hi = grenzen(m)
    grenze = min(-lo, hi)
    v = min(w, grenze)
    return v, (f"Gehrung in 3D wurde auf {_zahl(v)}° begrenzt (Eingabe {_zahl(w)}°)." if v != w else None)


def wirksame_dicke(wand, winkel):
    """Schnittdicke bei geschwenktem Kopf: Wand / cos(Winkel)."""
    return _z(wand) / math.cos(math.radians(abs(winkel)))


def ellipse(a, b):
    """Umfang einer Ellipse mit den Halbachsen a, b (Ramanujan II, wie schneidweg.ellipse)."""
    h = ((a - b) / (a + b)) ** 2 if a + b else 0
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def bohrung_laenge(d, gesamt):
    """Schnittlänge einer schrägen Bohrung Ø d mit Gesamtneigung γ auf der Wand (Ellipse d/2 × d/(2 cos γ))."""
    return ellipse(d / 2, d / 2 / math.cos(math.radians(abs(gesamt))))


def bohrung_huelle(d, gesamt):
    """Hüllmaß (für die Konturklasse) der schrägen Bohrung: lange Achse d / cos γ."""
    return d / math.cos(math.radians(abs(gesamt)))


def austritt(wand, laengs, quer):
    """Versatz des Austritts innen gegen den Eintritt außen [mm]: (längs Richtung Ende B, quer Richtung 90°)."""
    return _z(wand) * math.tan(math.radians(laengs)), _z(wand) * math.tan(math.radians(quer))


def technik(p):
    """Eingaben des Schneidweg-Rechners bzw. STEP-Imports der Position (positionen.technik) als dict."""
    t = p.get("technik") if isinstance(p, dict) else None
    try:
        d = json.loads(t) if isinstance(t, str) and t else (t if isinstance(t, dict) else {})
    except ValueError:
        d = {}
    return d if isinstance(d, dict) else {}


def aktiv(p):
    """Bauteil mit eingeschalteter 3D-Schnittbearbeitung."""
    return technik(p).get("d3") is True


def bearbeitungen(p, m=None, einstiche_ende=1):
    """3D-Bearbeitungen eines Teils (nur mit Häkchen am Bauteil), je eine Zeile:
    dict(art, winkel_eingabe, winkel (verwendet = Kopfschwenk bzw. Gesamtneigung), laengs, quer, laenge (je Stück),
    anzahl, einstiche (je Stück), huelle, abstand_b (Abstand der hintersten Stelle vom Ende B [mm]), hinweis, fehler).
    Lage einer Bohrung unbekannt: abstand_b 0 (zur sicheren Seite)."""
    if not aktiv(p):
        return []
    t = technik(p)
    lg = _z(p.get("laenge"))
    erg = []
    for s, art, schnitt, abst in (("a", ENDE_A, "a_schnitt", lg), ("b", ENDE_B, "b_schnitt", 0.0)):
        e = t.get(s) or {}
        if not e.get("d3"):
            continue
        z = dict(art=art, winkel_eingabe=e.get("winkel"), laengs=None, quer=None, anzahl=1,
                 einstiche=einstiche_ende, huelle=None, abstand_b=abst, hinweis=None, fehler=None, ende=True)
        try:
            z["winkel"], z["hinweis"] = gehrung_begrenzen(e.get("winkel"), m)
        except ValueError as f:
            z.update(winkel=None, fehler=str(f))
        if z["winkel"] == 0 and not z["fehler"]:
            z["fehler"] = "Gehrung in 3D ohne Gehrungswinkel"
        z["laenge"] = _z(p.get(schnitt))
        erg.append(z)
    for e in t.get("konturen") or ():
        if not e.get("d3") or e.get("art") != "Bohrung":
            continue
        n = int(_z(e.get("anzahl")) or 0)
        d = _z(e.get("d"))
        z = dict(art=BOHRUNG, winkel_eingabe=(e.get("neigung_l"), e.get("neigung_q")), anzahl=max(n, 0),
                 einstiche=1, hinweis=None, fehler=None, ende=False, d=d)
        try:
            z["laengs"], z["quer"], z["winkel"], z["hinweis"] = neigung_begrenzen(e.get("neigung_l"),
                                                                                  e.get("neigung_q"), m)
        except ValueError as f:
            z.update(laengs=None, quer=None, winkel=None, fehler=str(f))
        if d <= 0 and not z["fehler"]:
            z["fehler"] = "Bohrung 3D: Ø fehlt"
        if z["fehler"]:
            z.update(laenge=0.0, huelle=None)
        else:
            gem = _z(e.get("gemessen"))
            z["laenge"] = gem if gem > 0 and not z["hinweis"] else bohrung_laenge(d, z["winkel"])
            z["huelle"] = bohrung_huelle(d, z["winkel"])
        x = e.get("x")
        if isinstance(x, (int, float)) and not isinstance(x, bool) and lg > 0:
            letzte = _z(x) + max(n - 1, 0) * _z(e.get("abstand"))
            z["abstand_b"] = max(0.0, lg - letzte - d / 2)
        else:
            z["abstand_b"] = 0.0
        erg.append(z)
    return erg


def rest_letztes(p, m=None, bearb=None):
    """Rest, der hinter diesem Teil mindestens bleiben muss, wenn es das letzte der Stange ist [mm]
    (Greifmaß − Abstand der nächsten 3D-Bearbeitung vom Ende B; 0 = kein Sonderfall). Nur auf Maschinen mit 3D;
    der Greiferrest wird hier nicht addiert (Maximum in der Optimierung)."""
    if not kann_3d(m):
        return 0.0
    bearb = bearbeitungen(p, m) if bearb is None else bearb
    gueltig = [b for b in bearb if not b["fehler"]]
    if not gueltig:
        return 0.0
    return max(0.0, greifmass(m) - min(b["abstand_b"] for b in gueltig))


def pruefen(p, m=None, bearb=None):
    """Status der 3D-Bearbeitung einer Position: 'FEHLER: …', 'WARNUNG: …', 'HINWEIS: …' oder None (kein 3D bzw.
    in Ordnung). Eine Maschine ohne 3D rechnet keine 3D-Bearbeitung, auch nicht stillschweigend als 2D."""
    if not aktiv(p):
        return None
    if not kann_3d(m):
        return f"FEHLER: Maschine {(m or {}).get('maschinen_id') or '?'} kann keine 3D-Bearbeitung"
    bearb = bearbeitungen(p, m) if bearb is None else bearb
    fehler = next((b for b in bearb if b["fehler"]), None)
    if fehler:
        return f"FEHLER: {fehler['art']}: {fehler['fehler']}"
    if any(b["hinweis"] for b in bearb):
        return "WARNUNG: 3D-Winkel begrenzt, Kontur nicht maßhaltig"
    if not bearb:
        return "HINWEIS: 3D aktiviert, aber keine Bearbeitung in 3D"
    return None
