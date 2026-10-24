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
"""
import math

from . import skizze as sk

GRENZE = 45.0           # Kopfschwenk höchstens [°], wenn keine Maschine bekannt ist
TOL = 0.05              # Grad: so viel über der Grenze zählt noch nicht als begrenzt
SCHRITT = 2.0           # Abschnitte der Außenkante für Länge/Zeit höchstens so lang [mm]


def punkt(qs, e, aussen, innen, d3, grenze=GRENZE):
    """Innenkante unter dem Punkt 'aussen' (u, v) der Außenkante; 'innen' = Punkt des Innenumrisses darunter
    (entlang der Mantelnormale). Ergebnis dict(x_aussen, x_innen, beta (nötiger Kopfwinkel für die Soll-Fläche),
    winkel (verwendet: 2D 0, 3D höchstens die Grenze), begrenzt). x = Abstand hinter der Spitze des Endes (wie
    skizze.schnitt_x)."""
    xa = sk.schnitt_x(qs, e, *aussen)
    tiefe = math.dist(aussen, innen)
    if tiefe < 1e-9:
        return dict(x_aussen=xa, x_innen=xa, beta=0.0, winkel=0.0, begrenzt=False)
    delta = sk.schnitt_x(qs, e, *innen) - xa
    beta = math.degrees(math.atan2(abs(delta), tiefe))
    if not d3:
        return dict(x_aussen=xa, x_innen=xa, beta=beta, winkel=0.0, begrenzt=False)
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
            dx = sk.schnitt_x(qs, e, *q1) - sk.schnitt_x(qs, e, *q0)
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
