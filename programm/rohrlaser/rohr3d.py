"""3D-Modell eines Rohrs/Profils aus den Eingaben des Schneidweg-Rechners (Plan 3D-Editor A2/G3): damit hat der
Teile-Editor auch ohne STEP-Datei ein drehbares Modell, und jede Eingabe (Gehrung, Ausklinkung, Kontur) ist sofort
im 3D zu sehen – wie in den CAM-Programmen.

Grundlage ist dieselbe Geometrie wie für die Skizze (skizze.py): Querschnitt (Außen- und Innenumriss), Schnittkante
der Enden (skizze.schnitt_x) und Lage der Konturen (skizze.lagen/platzieren). Die Konturen werden als Linienzüge auf
der Außenwand gezeichnet (nicht ausgeschnitten); jede Linie trägt ihr Merkmal (li 'kontur:3', 'ende:a'), damit ein
Klick im 3D die Zeile wählt.

Netz wie ansicht3d: Rohrachse = Z ab Ende A, Y = oben, X = −u (vorne = −X, so zeigt die Ansicht „Vorn“ die Seite
vorne/90°).
"""
import math

from . import skizze as sk
from .blech3d import _flaeche2, _ohrschnitt
from .schneidweg import GRAVUR, _z, mit_radius

SCHRITT = 4.0           # Kanten des Querschnitts höchstens so lang [mm] (Ausklinkung, Sattel folgen der Kurve)
TEILE_MAX = 24          # je Kante höchstens so viele Stücke
ABSTAND = 0.4           # Linien so weit über der Wand [mm] (verdecken sich nicht mit der Fläche)


def _xyz(x, u, v):
    return (-u, v, x)


def _unterteilen(poly, teile=None):
    """Geschlossenes Polygon an den Kanten unterteilen; teile = Anzahl je Kante (für gleiche Teilung innen/außen)."""
    out, anzahl = [], []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        n = teile[i] if teile else max(1, min(TEILE_MAX, math.ceil(math.dist(a, b) / SCHRITT)))
        anzahl.append(n)
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    return out, anzahl


def netz(e, profil, laenge):
    """Netz der 3D-Ansicht aus Eingaben e (schneidweg), Profil und Teilelänge [mm]; None ohne Länge/Querschnitt."""
    L = _z(laenge)
    if L <= 0:
        return None
    qs = sk.Querschnitt(mit_radius(profil, e))
    umriss = qs.umriss_rund()               # Quadrat-/Rechteckrohr mit Außenradius
    if not umriss or len(umriss[0]) < 3:
        return None
    ea, eb = e.get("a") or {}, e.get("b") or {}
    punkte, dreiecke, linien, normalen, kennung = [], {}, {}, {}, {}

    def punkt(v):
        punkte.extend(round(c, 3) for c in v)
        return len(punkte) // 3 - 1

    def dreieck(art, a, b, c, soll):
        u = [b[i] - a[i] for i in range(3)]
        w = [c[i] - a[i] for i in range(3)]
        n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        if n[0] ** 2 + n[1] ** 2 + n[2] ** 2 < 1e-12:
            return
        if sum(n[i] * soll[i] for i in range(3)) < 0:
            b, c = c, b
        dreiecke.setdefault(art, []).extend((punkt(a), punkt(b), punkt(c)))

    def linie(art, zug, mitte_n, merkmal):
        linien.setdefault(art, []).append([round(c, 3) for p in zug for c in p])
        normalen.setdefault(art, []).append([round(c, 3) for c in mitte_n])
        kennung.setdefault(art, []).append(merkmal)

    def za(u, v):
        return sk.schnitt_x(qs, ea, u, v)

    def zb(u, v):
        return L - sk.schnitt_x(qs, eb, u, v)

    roh_a = list(umriss[0]) if _flaeche2(umriss[0]) > 0 else list(umriss[0])[::-1]     # ccw in (u, v)
    aussen, teile = _unterteilen(roh_a)
    innen = None
    if len(umriss) > 1 and len(umriss[1]) == len(umriss[0]):
        roh_i = list(umriss[1]) if _flaeche2(umriss[1]) > 0 else list(umriss[1])[::-1]
        # gleiche Ecke zuerst wie außen (nächster Punkt), damit Stirnfläche innen/außen zusammenpasst
        k = min(range(len(roh_i)), key=lambda i: math.dist(roh_i[i], roh_a[0]))
        innen, _ = _unterteilen(roh_i[k:] + roh_i[:k], teile)

    def mantel(poly, art, nach_aussen):
        n = len(poly)
        for i in range(n):
            (u0, v0), (u1, v1) = poly[i], poly[(i + 1) % n]
            du, dv = u1 - u0, v1 - v0
            nu, nv = (dv, -du) if nach_aussen else (-dv, du)        # Polygon ccw: rechts der Kante = außen
            soll = _xyz(0, nu, nv)
            a0, a1 = _xyz(za(u0, v0), u0, v0), _xyz(za(u1, v1), u1, v1)
            b0, b1 = _xyz(zb(u0, v0), u0, v0), _xyz(zb(u1, v1), u1, v1)
            dreieck(art, a0, a1, b1, soll)
            dreieck(art, a0, b1, b0, soll)

    mantel(aussen, "A", True)
    if innen:
        mantel(innen, "I", False)
    # Stirnflächen (Schnittflächen der Enden): Ring zwischen außen und innen bzw. volles Profil
    for art, z, soll in (("EA", za, (0, 0, -1)), ("EB", zb, (0, 0, 1))):
        if innen:
            n = len(aussen)
            for i in range(n):
                p0, p1, q0, q1 = aussen[i], aussen[(i + 1) % n], innen[i], innen[(i + 1) % n]
                a0, a1 = _xyz(z(*p0), *p0), _xyz(z(*p1), *p1)
                b0, b1 = _xyz(z(*q0), *q0), _xyz(z(*q1), *q1)
                dreieck(art, a0, a1, b1, soll)
                dreieck(art, a0, b1, b0, soll)
        elif not qs.r:
            for a, b, c in _ohrschnitt(aussen):
                dreieck(art, _xyz(z(*a), *a), _xyz(z(*b), *b), _xyz(z(*c), *c), soll)
        # Schnittkante als Linie (Merkmal Ende)
        zug = [_xyz(z(u, v), u, v) for u, v in aussen + aussen[:1]]
        linie(art, zug, (0, 1, 0), f"ende:{art[1].lower()}")
    # Konturen auf der Außenwand
    for d in sk.lagen(e.get("konturen") or [], L):
        try:
            pts, n_mitte = sk.platzieren(qs, d)
            ns = sk.normalen(qs, d)
        except (ValueError, TypeError, ZeroDivisionError):
            continue
        if len(pts) < 2:
            continue
        zug = [_xyz(x, u + nu * ABSTAND, v + nv * ABSTAND) for (x, u, v), (nu, nv) in zip(pts, ns + ns[-1:] * len(pts))]
        ein = d["eingabe"]
        if not (ein.get("art") == GRAVUR and not ein.get("umriss")):
            zug.append(zug[0])
        linie("G" if ein.get("art") == GRAVUR else "K", zug, _xyz(0, *n_mitte), f"kontur:{d['zeile']}")
    return dict(p=punkte, t=dreiecke, l=linien, ln=normalen, li=kennung, eingaben=True)
