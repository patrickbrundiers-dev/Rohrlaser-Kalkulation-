"""Konturwerkzeuge des Teile-Editors (Patrick 19.11.2026 „Erweiterter Entwicklungsauftrag 3D-Editor“, Priorität 1).

Konturen sind im Programm Formelemente (Bohrung, Langloch, Rechteck, Polygon …) mit Maßen, Lage und Muster – keine
freien Linienzüge. Die Werkzeuge hier ändern deshalb nur diese Maße bzw. Punkte und geben eine neue Konturzeile
zurück; gerechnet wird wie immer im Schneidweg-Rechner bzw. Blech-Editor (kein zweiter Rechenweg). Ohne Fenster.

- drehen: Drehwinkel der Kontur auf ihrer Fläche (Feld drehung, wie im Eigenschaftenfeld) um w Grad weiter.
- versatz: Kontur um o mm nach außen (+) bzw. innen (−) versetzen (Offset): Ø, Breiten, Längen, Eckradius,
  Polygon-Ecken auf Gehrung.
- verlaengern: Länge (Langloch, Schlitz, Ausklinkung, Ausschnitt längs) um Δ ändern; − = kürzen.
- umkehren: Laufrichtung der Punkte (Polygon, Eckpunkte, echter Umriss) umdrehen, Bögen bleiben Bögen.
- ellipse / vieleck: neue Formen als Polygonzeile (um die Mitte, wie der DXF-Import), Fehler Sehne–Ellipse höchstens
  SEHNE mm.
- reihe: Kopien mit verschiedenen Abständen (z. B. „20; 35; 50“), je eine Zeile mit eigener Lage.
- gleiche: Zeilen mit gleicher Art, gleichen Maßen oder gleicher Seite (intelligente Auswahl).
- zahl: Eingabe als Zahl oder Rechnung („L/2“, „(L − 2×25)/3“) mit der sicheren Auswertung der Maßfelder
  (rechenfeld: nur Zahlen, + − × ÷, Klammern und die Größen des Teils – kein eval, kein Programmcode).

Fehler kommen als ValueError mit einem Text für die Einblendung. Ein geändertes Maß nimmt der Kontur ihre
STEP-Messung (gemessen/huelle_gemessen): die Länge kommt dann aus der Formel; alle anderen Konturen bleiben, wie sie
sind (Grundregel: Konturen 100 % wie STEP)."""
import math

from . import schneidweg as sw
from . import rechenfeld

SEHNE = 0.01            # mm: größter Abstand zwischen Ellipse und ihrem Vieleck
MESSUNG = ("gemessen", "huelle_gemessen")
DREH_OHNE = (sw.BOHRUNG, sw.SENKUNG, sw.FLOWDRILL, sw.GRAVUR)
LAENGE = {sw.LANGLOCH: "l", sw.SCHLITZ: "l", sw.AUSKLINKUNG: "l", sw.AUSSCHNITT: "b"}


def _r(x, n=3):
    return round(float(x), n) + 0.0


def _z(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _ohne_messung(z):
    return {k: v for k, v in z.items() if k not in MESSUNG}


# ------------------------------------------------------------------------------------------------ Eingabe
def zahl(text, groessen=None):
    """Zahl oder Rechnung wie in den Maßfeldern (rechenfeld: L, B, H, D, S); ValueError mit Text, None wenn leer."""
    return rechenfeld.auswerten(text, groessen)


# ------------------------------------------------------------------------------------------------ Punkte
def _punkte_text(roh):
    return "; ".join(f"{_r(x):g},{_r(y):g}" + (f",{_r(b, 6):g}" if b else "") for x, y, b in roh)


def _flaeche(pk):
    return sum(pk[i][0] * pk[(i + 1) % len(pk)][1] - pk[(i + 1) % len(pk)][0] * pk[i][1] for i in range(len(pk))) / 2


def punkte_versetzt(pk, o):
    """Geschlossenen Linienzug [(x, y)] um o nach außen versetzen (Ecken auf Gehrung). ValueError, wenn er dabei
    zerfällt (zu weit nach innen)."""
    n = len(pk)
    if n < 3:
        raise ValueError("Versatz: Der Linienzug braucht mindestens 3 Punkte.")
    s = 1.0 if _flaeche(pk) > 0 else -1.0       # gegen den Uhrzeiger: außen = rechts der Laufrichtung
    linien = []
    for i in range(n):
        (x1, y1), (x2, y2) = pk[i], pk[(i + 1) % n]
        lg = math.hypot(x2 - x1, y2 - y1)
        if lg < 1e-9:
            raise ValueError("Versatz: Der Linienzug hat doppelte Punkte.")
        nx, ny = s * (y2 - y1) / lg, -s * (x2 - x1) / lg
        linien.append(((x1 + nx * o, y1 + ny * o), (x2 - x1, y2 - y1)))
    out = []
    for i in range(n):
        (p, d1), (q, d2) = linien[i - 1], linien[i]
        det = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(det) < 1e-12:                    # gerade weiter: Punkt nur verschieben
            out.append(q)
            continue
        t = ((q[0] - p[0]) * d2[1] - (q[1] - p[1]) * d2[0]) / det
        out.append((p[0] + d1[0] * t, p[1] + d1[1] * t))
    a0, a1 = _flaeche(pk), _flaeche(out)
    if a0 * a1 <= 0 or abs(a1) < 1e-6:
        raise ValueError("Versatz: So weit nach innen geht nicht, die Kontur würde verschwinden.")
    return out


# ------------------------------------------------------------------------------------------------ Werkzeuge
def drehen(z, winkel):
    """Kontur auf ihrer Fläche um winkel [°] weiterdrehen (+ = gegen den Uhrzeiger von außen)."""
    if z.get("art") in DREH_OHNE:
        raise ValueError(f"Drehen: {z.get('art')} ist rund, Drehen ändert nichts.")
    w = (_z(z.get("drehung")) + float(winkel)) % 360
    w = _r(w, 3)
    neu = dict(z)
    if w and abs(w - 360) > 1e-6:
        neu["drehung"] = w
    else:
        neu.pop("drehung", None)
    return neu


def versatz(z, o):
    """Kontur um o [mm] nach außen (+) bzw. innen (−) versetzen."""
    o = float(o)
    art = z.get("art")
    neu = _ohne_messung(z)

    def mass(k, um):
        wert = _z(z.get(k)) + um
        if wert <= 0:
            raise ValueError(f"Versatz: {art} würde zu klein (Maß {k} ≤ 0).")
        neu[k] = _r(wert)

    if art in (sw.BOHRUNG, sw.SENKUNG, sw.FLOWDRILL, sw.LOCHFELD):
        mass("d", 2 * o)
    elif art == sw.LANGLOCH:
        mass("l", 2 * o)
        mass("b", 2 * o)
    elif art in (sw.RECHTECK, sw.AUSSCHNITT):
        mass("b", 2 * o)
        mass("h", 2 * o)
        if _z(z.get("r")):
            neu["r"] = _r(max(0.0, _z(z.get("r")) + o))
    elif art in (sw.SCHLITZ, sw.AUSKLINKUNG):
        mass("l", o)
        mass("b", 2 * o)
        if art == sw.AUSKLINKUNG and _z(z.get("r")):
            neu["r"] = _r(max(0.0, _z(z.get("r")) + o))
    elif art == sw.POLYGON or z.get("umriss") or z.get("eckpunkte"):
        geaendert = False
        for k in ("punkte", "eckpunkte"):
            if z.get(k):
                roh = sw.punkte_roh(z[k])
                if any(b for _, _, b in roh):
                    raise ValueError("Versatz: Polygone mit Bögen bitte über Skalieren anpassen.")
                neu[k] = _punkte_text([(x, y, 0.0) for x, y in punkte_versetzt([(x, y) for x, y, _ in roh], o)])
                geaendert = True
        if z.get("umriss"):
            neu["umriss"] = [[_r(a), _r(b)] for a, b in punkte_versetzt([tuple(map(float, p)) for p in z["umriss"]], o)]
            geaendert = True
        if not geaendert:
            raise ValueError(f"Versatz: {art} hat keine Punkte zum Versetzen.")
    else:
        raise ValueError(f"Versatz: {art or 'Diese Zeile'} hat keine Maße zum Versetzen.")
    return neu


def verlaengern(z, delta):
    """Länge der Kontur um delta [mm] ändern (− = kürzen)."""
    art = z.get("art")
    k = LAENGE.get(art)
    if k is None:
        raise ValueError("Verlängern/Kürzen geht bei Langloch, Schlitz, Ausklinkung und Ausschnitt mit Tiefe.")
    wert = _z(z.get(k)) + float(delta)
    if art == sw.LANGLOCH and wert < _z(z.get("b")):
        raise ValueError("Kürzen: Ein Langloch wird nicht kürzer als seine Breite (sonst eine Bohrung).")
    if wert <= 0:
        raise ValueError(f"Kürzen: {art} würde verschwinden.")
    return dict(_ohne_messung(z), **{k: _r(wert)})


def umkehren(z):
    """Laufrichtung der Punkte umdrehen; ein Bogen bleibt derselbe Bogen (Bulge mit Gegenzeichen am Gegenpunkt)."""
    neu = dict(z)
    geaendert = False
    for k in ("punkte", "eckpunkte"):
        if z.get(k):
            roh = sw.punkte_roh(z[k])
            n = len(roh)
            neu[k] = _punkte_text([(roh[n - 1 - j][0], roh[n - 1 - j][1], -roh[(n - 2 - j) % n][2])
                                   for j in range(n)])
            geaendert = True
    if z.get("umriss"):
        neu["umriss"] = [list(p) for p in reversed(z["umriss"])]
        geaendert = True
    if not geaendert:
        raise ValueError("Umkehren geht bei Polygonen und Konturen mit Umriss (Sonderkontur, Eckpunkte).")
    return neu


def ellipse_punkte(a, b, sehne=SEHNE):
    """Ellipse mit den Achsen a (längs) × b (quer) als Punkte um die Mitte."""
    a, b = float(a), float(b)
    if a <= 0 or b <= 0:
        raise ValueError("Ellipse: Beide Achsen müssen größer als 0 sein.")
    r = max(a, b) / 2
    n = max(12, int(math.ceil(math.pi / math.acos(max(-1.0, 1 - sehne / r)))) if sehne < r else 12)
    n += n % 4                                  # Scheitel auf Punkten (Maß a × b genau)
    return [(a / 2 * math.cos(2 * math.pi * i / n), b / 2 * math.sin(2 * math.pi * i / n)) for i in range(n)]


def ellipse(a, b, **lage):
    """Neue Polygonzeile Ellipse a × b."""
    pk = ellipse_punkte(a, b)
    return dict(lage, art=sw.POLYGON, anzahl=lage.get("anzahl") or 1,
                punkte=_punkte_text([(x, y, 0.0) for x, y in pk]))


def vieleck(n, d, start=90.0, **lage):
    """Regelmäßiges n-Eck auf dem Umkreis-Ø d (start: Winkel der ersten Ecke, 90° = oben)."""
    n = int(n)
    if n < 3:
        raise ValueError("Vieleck: mindestens 3 Ecken.")
    if float(d) <= 0:
        raise ValueError("Vieleck: Der Umkreis-Ø muss größer als 0 sein.")
    r = float(d) / 2
    pk = [(r * math.cos(math.radians(start + 360 * i / n)), r * math.sin(math.radians(start + 360 * i / n)))
          for i in range(n)]
    return dict(lage, art=sw.POLYGON, anzahl=lage.get("anzahl") or 1,
                punkte=_punkte_text([(x, y, 0.0) for x, y in pk]))


def abstaende_lesen(text, werte=None):
    """„20; 35; 50“ -> [20.0, 35.0, 50.0]; jede Zahl darf eine Formel sein. ValueError bei leeren oder ≤ 0."""
    out = []
    for t in str(text or "").replace("\n", ";").split(";"):
        if not t.strip():
            continue
        try:
            v = zahl(t, werte)
        except ValueError:
            v = None
        if v is None or v <= 0:
            raise ValueError(f"Reihe: „{t.strip()}“ ist kein Abstand > 0.")
        out.append(v)
    if not out:
        raise ValueError("Reihe: Bitte mindestens einen Abstand eingeben, z. B. 20; 35; 50.")
    return out


def reihe(z, abstaende, achse="x"):
    """Kopien der Kontur mit verschiedenen Abständen: je Abstand eine neue Zeile (Anzahl 1), Lage längs (Rohr x)
    bzw. x oder y (Blech) jeweils um den Abstand weiter. Die Kontur selbst wird ein Einzelstück."""
    x0 = _z(z.get(achse))
    erste = dict(z, anzahl=1)
    erste.pop("abstand", None)
    out, x = [], x0
    for a in abstaende:
        x += float(a)
        k = {s: v for s, v in erste.items() if s not in MESSUNG + (sw.URSPRUNG,)}
        k[achse] = _r(x)
        out.append(k)
    return erste, out


def _masse(z):
    art = z.get("art")
    return tuple(str(z.get(k)) for k, _ in sw.MASSE.get(art, ()))


def gleiche(konturen, r, wie="art"):
    """Zeilen wie Zeile r: wie = 'art' (gleiche Konturart), 'masse' (gleiche Art und Maße), 'seite' (gleiche
    Seite bzw. Fläche)."""
    if not 0 <= r < len(konturen):
        return []
    v = konturen[r]
    out = []
    for i, z in enumerate(konturen):
        if wie == "seite":
            ok = (z.get("seite") or None) == (v.get("seite") or None)
        elif wie == "masse":
            ok = z.get("art") == v.get("art") and _masse(z) == _masse(v)
        else:
            ok = z.get("art") == v.get("art")
        if ok:
            out.append(i)
    return out
