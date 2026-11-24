"""Blech zeichnen im Teile-Editor (Plan 3D-Editor C5, Schritt 3E-4b): Außenkontur der Abwicklung mit Klicks statt
Text, Eckpunkte am Griff ziehen, Ecke abrunden oder fasen, Punkt einfügen und löschen; Innenkonturen, Biegelinien
und Außenkanten in der Abwicklung ziehen.

Hier nur die Rechnung ohne Oberfläche (Punkte in mm, y nach oben wie blech.zuschnitt); die Maus bedient
blech_dialog.BlechSkizze.
"""
import math

from . import blech, schneidweg as sw

_z = sw._z
FANG_PX = 8         # Pixel: so nah muss der Mauszeiger an Ecke, Kante oder Linie sein


def fangen(wert, raster=1.0):
    """Auf das Raster [mm] runden (0 = nicht runden)."""
    return round(wert / raster) * raster if raster and raster > 0 else wert


def rechtwinklig(letzter, q):
    """Punkt q waagerecht oder senkrecht zum letzten Punkt ausgerichtet (Umschalt beim Zeichnen)."""
    if letzter is None:
        return q
    return (q[0], letzter[1]) if abs(q[0] - letzter[0]) >= abs(q[1] - letzter[1]) else (letzter[0], q[1])


def text(pk):
    """[(x, y)] -> '0,0; 200,0; …' (wie das Feld Eckpunkte; Dezimalpunkt)."""
    def z(v):
        v = round(v, 3)
        return f"{v:g}" if v != int(v) else str(int(v))
    return "; ".join(f"{z(x)},{z(y)}" for x, y in pk)


def _einheit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    if n < 1e-9:
        raise ValueError("Ecke: zwei Punkte liegen aufeinander.")
    return dx / n, dy / n, n


def _ecke(pk, i):
    n = len(pk)
    if n < 3:
        raise ValueError("Polygon: mindestens 3 Eckpunkte.")
    p = pk[i % n]
    ux, uy, la = _einheit(p, pk[(i - 1) % n])
    vx, vy, lb = _einheit(p, pk[(i + 1) % n])
    theta = math.acos(max(-1.0, min(1.0, ux * vx + uy * vy)))       # Innenwinkel der Ecke
    if theta < 1e-6 or abs(theta - math.pi) < 1e-6:
        raise ValueError("Ecke: die Kanten liegen in einer Flucht.")
    return p, (ux, uy, la), (vx, vy, lb), theta


def ecke_fasen(pk, i, a):
    """Ecke i mit einer Fase: auf beiden Kanten a [mm] von der Ecke abgeschnitten."""
    p, (ux, uy, la), (vx, vy, lb), _ = _ecke(pk, i)
    if not 0 < a < min(la, lb) - 1e-6:
        raise ValueError(f"Fase {a:g} mm ist zu groß für die Ecke (Kante {min(la, lb):g} mm).")
    t1, t2 = (p[0] + ux * a, p[1] + uy * a), (p[0] + vx * a, p[1] + vy * a)
    i %= len(pk)
    return pk[:i] + [t1, t2] + pk[i + 1:]


def ecke_runden(pk, i, r, schritt=15):
    """Ecke i mit Radius r [mm] abgerundet (Bogen als Punkte etwa alle `schritt` Grad)."""
    p, (ux, uy, la), (vx, vy, lb), theta = _ecke(pk, i)
    t = r / math.tan(theta / 2) if r > 0 else 0
    if not 0 < t < min(la, lb) - 1e-6:
        raise ValueError(f"Radius {r:g} mm ist zu groß für die Ecke (Kante {min(la, lb):g} mm).")
    wx, wy = ux + vx, uy + vy
    wn = math.hypot(wx, wy)
    c = (p[0] + wx / wn * r / math.sin(theta / 2), p[1] + wy / wn * r / math.sin(theta / 2))
    t1, t2 = (p[0] + ux * t, p[1] + uy * t), (p[0] + vx * t, p[1] + vy * t)
    a1, a2 = math.atan2(t1[1] - c[1], t1[0] - c[0]), math.atan2(t2[1] - c[1], t2[0] - c[0])
    d = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi                # kurzer Weg (Bogen = π − θ)
    n = max(2, math.ceil(abs(math.degrees(d)) / schritt))
    bogen = [(c[0] + r * math.cos(a1 + d * k / n), c[1] + r * math.sin(a1 + d * k / n)) for k in range(n + 1)]
    i %= len(pk)
    return pk[:i] + bogen + pk[i + 1:]


def punkt_weg(pk, i):
    if len(pk) <= 3:
        raise ValueError("Polygon: mindestens 3 Eckpunkte.")
    return pk[:i] + pk[i + 1:]


def punkt_einfuegen(pk, i, q):
    """Neuer Punkt q auf der Kante von Punkt i zu Punkt i+1."""
    return pk[:i + 1] + [q] + pk[i + 1:]


def _strecke(q, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / (dx * dx + dy * dy or 1.0)))
    f = (a[0] + t * dx, a[1] + t * dy)
    return math.dist(q, f), f


def naechste_ecke(pk, q, tol):
    """Index der Ecke höchstens tol [mm] von q entfernt (die nächste) oder None."""
    best = min(((math.dist(p, q), i) for i, p in enumerate(pk)), default=None)
    return best[1] if best and best[0] <= tol else None


def naechste_kante(pk, q, tol):
    """(i, Fußpunkt) der Kante i → i+1 höchstens tol [mm] von q entfernt oder None."""
    best = None
    for i in range(len(pk)):
        d, f = _strecke(q, pk[i], pk[(i + 1) % len(pk)])
        if d <= tol and (best is None or d < best[0]):
            best = (d, i, f)
    return best[1:] if best else None


def schenkel_ziehen(schenkel, i, delta):
    """Kantteil: Biegelinie i um delta [mm] in der Abwicklung verschoben (Schenkel i länger, i+1 kürzer);
    i = -1: Anfangskante (Schenkel 1 um delta länger), i = len: Endkante (letzter Schenkel länger)."""
    neu = [dict(x) for x in schenkel]
    if not neu:
        return neu
    if i < 0:
        neu[0]["laenge"] = round(_z(neu[0].get("laenge")) + delta, 3)
    elif i >= len(neu) - 1:
        neu[-1]["laenge"] = round(_z(neu[-1].get("laenge")) + delta, 3)
    else:
        neu[i]["laenge"] = round(_z(neu[i].get("laenge")) + delta, 3)
        neu[i + 1]["laenge"] = round(_z(neu[i + 1].get("laenge")) - delta, 3)
    if any(_z(x.get("laenge")) <= 0 for x in neu):
        raise ValueError("Schenkel würde zu kurz.")
    return neu


def polygon_aus(e, zs):
    """Eckpunkte der Außenkontur in Koordinaten der Abwicklung: Polygon wie eingegeben, sonst das Rechteck."""
    if zs.get("punkte"):
        return list(zs["punkte"])
    return [(0.0, 0.0), (zs["laenge"], 0.0), (zs["laenge"], zs["breite"]), (0.0, zs["breite"])]


def kontur_mitten(e, zs):
    """[(Zeile, x, y)] Mitten der Innenkonturen wie in der Skizze (ohne Lage gleichmäßig auf der Mittellinie);
    x/y im System der Eingaben (Polygon: wie die Eckpunkte)."""
    alle = e.get("konturen") or []
    konturen = [z for z in alle if z.get("art")]
    frei = [z for z in konturen if z.get("x") is None or z.get("y") is None]
    minx = min((x for x, _ in zs.get("punkte") or ()), default=0.0)
    miny = min((y for _, y in zs.get("punkte") or ()), default=0.0)
    out = []
    for r, z in enumerate(alle):
        if not z.get("art"):
            continue
        if any(z is f for f in frei):
            k = next(i for i, f in enumerate(frei) if f is z)
            out.append((r, minx + zs["laenge"] * (k + 1) / (len(frei) + 1), miny + zs["breite"] / 2))
        else:
            out.append((r, _z(z["x"]), _z(z["y"])))
    return out


def kontur_radius(z):
    """Ungefähre halbe Größe einer Innenkontur [mm] für den Treffer mit der Maus."""
    m = blech._halbmass(z)
    if m:
        return max(m[1], 2.0)
    if z.get("art") == sw.TEXT_GRAVUR:
        b, h = blech.gravur_masse(z)
        return max(b, h) / 2
    return 4.0
