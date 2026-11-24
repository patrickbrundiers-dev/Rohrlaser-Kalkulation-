"""Schnittfläche der Enden in 2D und 3D (Plan 3E-10, Patrick 24.10.2026, „alle a“).

2D: Der Laserstrahl steht überall senkrecht (90°) zur Mantelfläche. Die Innenkante liegt deshalb genau unter der
Außenkante (gleiche Lage auf der Rohrachse); eine Gehrung ist innen nicht eben, sondern „verdreht“, so wie ein
2D-Laser wirklich schneidet.

3D: Der Kopf schwenkt in der Ebene aus Mantelnormale und Rohrachse so weit, dass die Innenkante auf der Soll-Fläche
liegt (Gehrung eben durch die Wand). Der nötige Winkel β ändert sich entlang des Umfangs (Rechteckrohr: an der Wand
quer zur Kippachse der volle Gehrungswinkel, an den Wänden parallel dazu 0°; Rundrohr stetig). Über der Grenze der
Maschine (Vorgabe ±45°) steht der Kopf auf der Grenze: ab dieser Stelle ist die Kontur nicht maßhaltig, die
Abschnitte werden gelb gezeigt (Art 'GB') und gemeldet.

Eine Quelle für 3D-Ansicht (rohr3d), Zeit (dreid/rechnen) und später den STEP-Export (3E-8): je Punkt der
Außenkante die Lage der Innenkante. Die Schnittlänge bleibt die der Außenkante (Plan G1 a).

Konturen (Patrick 26.10.2026, Variante C): Bei 90° zur Oberfläche (2D) gilt immer die Innenkante der Kontur. Innen
hat die Kontur die Maße der Zeichnung bzw. STEP, der Strahl steht je Punkt senkrecht zur Oberfläche, außen ist sie
deshalb auf Rundrohr und Eckradius breiter (wie dreid.bohrung_2d_rundrohr). Mit Schnittrichtung parallel (3D) ist die
Schnittfläche eben: außen wie gezeichnet, jeder Punkt parallel zur Normalen in der Konturmitte nach innen.
"""
import bisect
import math

from . import skizze as sk
from .schneidweg import BOHRUNG, LANGLOCH, LOCHFELD, POLYGON, RECHTECK, SCHLITZ, SENKUNG

GRENZE = 45.0           # Kopfschwenk höchstens [°], wenn keine Maschine bekannt ist
TOL = 0.05              # Grad: so viel über der Grenze zählt noch nicht als begrenzt
SCHRITT = 2.0           # Abschnitte der Außenkante für Länge/Zeit höchstens so lang [mm]


def punkt(qs, e, aussen, innen, d3, grenze=GRENZE):
    """Innenkante unter dem Punkt 'aussen' (u, v) der Außenkante; 'innen' = Punkt des Innenumrisses darunter
    (entlang der Mantelnormale). Ergebnis dict(x_aussen, x_innen, beta (nötiger Kopfwinkel für die Soll-Fläche),
    winkel (verwendet: 2D 0, 3D höchstens die Grenze), begrenzt). x = Abstand hinter der Spitze des Endes (wie
    skizze.schnitt_x)."""
    xa = sk.schnitt_x(qs, e, *aussen, aussen=True)     # auf der Soll-Fläche (Gehrung: Ebene)
    x2 = sk.schnitt_x(qs, e, *aussen) if not d3 else xa  # 2D: Innenkante maßhaltig (lange Seite kürzer)
    tiefe = math.dist(aussen, innen)
    if tiefe < 1e-9:
        return dict(x_aussen=x2, x_innen=x2, beta=0.0, winkel=0.0, begrenzt=False)
    delta = sk.schnitt_x(qs, e, *innen, aussen=True) - xa
    beta = math.degrees(math.atan2(abs(delta), tiefe))
    if not d3:
        return dict(x_aussen=x2, x_innen=x2, beta=beta, winkel=0.0, begrenzt=False)
    w = min(beta, grenze)
    xi = xa + math.copysign(tiefe * math.tan(math.radians(w)), delta) if delta else xa
    return dict(x_aussen=xa, x_innen=xi, beta=beta, winkel=w, begrenzt=beta > grenze + TOL)


def ringe(qs):
    """Außen- und Innenumriss (gleich viele Punkte, Punkt i innen unter Punkt i außen, beide gegen den Uhrzeigersinn)
    oder None (offenes bzw. volles Profil)."""
    umriss = qs.umriss_rund(12)
    if not umriss or len(umriss) < 2 or len(umriss[0]) != len(umriss[1]) or len(umriss[0]) < 3:
        return None

    def ccw(p):
        a = sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))
        return list(p) if a > 0 else list(p)[::-1]
    a, i = ccw(umriss[0]), ccw(umriss[1])
    k = min(range(len(i)), key=lambda j: math.dist(i[j], a[0]))
    return a, i[k:] + i[:k]


def abschnitte(qs, e, d3, grenze=GRENZE, schritt=SCHRITT):
    """Außenkante eines Endes in Stücke (höchstens 'schritt' mm im Querschnitt): [dict(laenge (echte Länge der
    Schnittkante, mit dem Weg längs der Achse), beta, winkel, begrenzt, u, v)] je Stück mit den Werten in seiner
    Mitte. Leer ohne Innenumriss (offenes/volles Profil)."""
    r = ringe(qs)
    if r is None:
        return []
    aussen, innen = r
    out = []
    n = len(aussen)
    for k in range(n):
        a0, a1, i0, i1 = aussen[k], aussen[(k + 1) % n], innen[k], innen[(k + 1) % n]
        lg = math.dist(a0, a1)
        m = max(1, math.ceil(lg / schritt))
        for j in range(m):
            f = (j + 0.5) / m
            pa = (a0[0] + f * (a1[0] - a0[0]), a0[1] + f * (a1[1] - a0[1]))
            pi = (i0[0] + f * (i1[0] - i0[0]), i0[1] + f * (i1[1] - i0[1]))
            d = punkt(qs, e, pa, pi, d3, grenze)
            f0, f1 = j / m, (j + 1) / m
            q0 = (a0[0] + f0 * (a1[0] - a0[0]), a0[1] + f0 * (a1[1] - a0[1]))
            q1 = (a0[0] + f1 * (a1[0] - a0[0]), a0[1] + f1 * (a1[1] - a0[1]))
            dx = sk.schnitt_x(qs, e, *q1, aussen=True) - sk.schnitt_x(qs, e, *q0, aussen=True)    # Länge wie bisher (G1)
            out.append(dict(laenge=math.hypot(lg / m, dx), beta=d["beta"], winkel=d["winkel"],
                            begrenzt=d["begrenzt"], u=pa[0], v=pa[1]))
    return out


def begrenzt(stuecke):
    """(Länge der begrenzten Stücke [mm], größter nötiger Winkel dort [°]) oder (0, 0)."""
    b = [s for s in stuecke if s["begrenzt"]]
    return (sum(s["laenge"] for s in b), max(s["beta"] for s in b)) if b else (0.0, 0.0)


def hinweis(name, stuecke, grenze=GRENZE):
    """Text für die begrenzten Stücke eines Endes oder None."""
    lg, beta = begrenzt(stuecke)
    if lg <= 0:
        return None
    return (f"{name}: {lg:.0f} mm des Schnitts brauchen bis {beta:.0f}°, auf {grenze:.0f}° begrenzt, Kontur dort "
            "nicht maßhaltig").replace(".", ",")


INNEN_ARTEN = (BOHRUNG, SENKUNG, LANGLOCH, RECHTECK, SCHLITZ, POLYGON, LOCHFELD)   # Innenkante maßhaltig (2D)


def eben_3d(z, e):
    """Kontur z mit Schnittrichtung parallel und 3D am Teil e: ebene Schnittfläche (Kopf hält die Richtung)."""
    return z.get("schnitt") == "parallel" and e.get("d3") is True


def innen_2d(z, e):
    """Kontur z wird senkrecht zur Oberfläche geschnitten (2D) und hat innen die Maße der Zeichnung: alle
    Innenkonturen außer 3D (eben, schräge Bohrung) und durchgehend durch beide Wände (ein Strahl durchs Profil)."""
    if z.get("art") not in INNEN_ARTEN or eben_3d(z, e) or z.get("wand") == "beide":
        return False
    if e.get("d3") is True and z.get("d3") and z.get("art") == BOHRUNG:
        return False
    return True


def _umrechnen(t, von, nach):
    """Bogenlänge t auf dem Umriss 'von' -> gleiche Stelle (gleiches Stück, gleicher Anteil) auf 'nach'."""
    k = max(0, min(len(von) - 2, bisect.bisect_right(von, t) - 1))
    f = 0.0 if von[k + 1] - von[k] < 1e-12 else (t - von[k]) / (von[k + 1] - von[k])
    return nach[k] + f * (nach[k + 1] - nach[k])


def innen_massgebend(q, cum, cum_i, tm=None):
    """Lochrand q [(t, x)] mit t = Konturmitte tm + gezeichneter Abstand am Umfang so umrechnen, dass die Kontur auf
    der Innenwand (Stücke cum_i, gleiche Teilung wie der Außenumriss cum) diese Abstände zur Mitte hat. Die Mitte
    bleibt (Vorgabe: Mitte von q); auf ebenen Wänden ändert sich nichts, auf Bogen und Rundrohr wird die Kontur außen
    breiter. Ergebnis: Bogenlänge t auf dem Außenumriss, gilt für außen und innen (gleicher Anteil je Stück)."""
    if not q or len(cum) != len(cum_i) or cum[-1] <= 0 or cum_i[-1] <= 0:
        return q
    T, Ti = cum[-1], cum_i[-1]
    if tm is None:
        tm = (min(p[0] for p in q) + max(p[0] for p in q)) / 2
    basis = T * math.floor(tm / T)
    ti_m = _umrechnen(tm - basis, cum, cum_i)
    out = []
    for t, x in q:
        ti = ti_m + (t - tm)
        k = math.floor(ti / Ti)
        out.append((_umrechnen(ti - k * Ti, cum_i, cum) + k * T + basis, x))
    return out


def strahl_bis(poly, p, d):
    """Abstand von p in Richtung d (Einheitsvektor) bis zum ersten Schnitt mit dem geschlossenen Polygon oder None."""
    beste = None
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ex, ey = b[0] - a[0], b[1] - a[1]
        nenner = d[0] * ey - d[1] * ex
        if abs(nenner) < 1e-12:
            continue
        wx, wy = a[0] - p[0], a[1] - p[1]
        s = (wx * ey - wy * ex) / nenner
        f = (wx * d[1] - wy * d[0]) / nenner
        if s > 1e-9 and -1e-9 <= f <= 1 + 1e-9 and (beste is None or s < beste):
            beste = s
    return beste
