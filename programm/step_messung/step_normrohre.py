"""Normreihe gängiger Rohrgrößen (Außenmaße in mm): Quadrat- und Rechteckrohr nach EN 10219/10305-5, Rundrohr nach
EN 10219/10220/10305. Für offen gezeichnete Rohre (step_offenes_rohr, Patrick 25.10.2026: „errechnen welches
nächstgrößere Rohr es ist“, „nicht aus den Stammdaten, da sind nicht viele drin“): das kleinste Normrohr, in das das
Teil passt. Die Wandstärke kommt aus der Zeichnung (Blechdicke); ob es das Rohr zu kaufen gibt, entscheiden die
Stammdaten im Programm (sonst nur Vorschlag)."""

QUADRAT = (15, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 120, 125, 140, 150, 160, 180, 200, 220, 250,
           260, 300, 350, 400)
RECHTECK = ((20, 10), (25, 15), (30, 15), (30, 20), (35, 20), (40, 15), (40, 20), (40, 25), (40, 30), (45, 25),
            (50, 20), (50, 25), (50, 30), (50, 35), (50, 40), (60, 20), (60, 30), (60, 40), (60, 50), (70, 30),
            (70, 40), (70, 50), (80, 20), (80, 30), (80, 40), (80, 50), (80, 60), (90, 50), (100, 30), (100, 40),
            (100, 50), (100, 60), (100, 80), (120, 40), (120, 60), (120, 80), (120, 100), (140, 60), (140, 70),
            (140, 80), (150, 50), (150, 100), (160, 80), (160, 90), (180, 100), (200, 100), (200, 120), (200, 150),
            (250, 100), (250, 150), (260, 140), (300, 100), (300, 150), (300, 200), (400, 200))
RUND = (10, 12, 13.5, 14, 15, 16, 17.2, 18, 20, 21.3, 22, 25, 26.9, 28, 30, 32, 33.7, 35, 38, 40, 42.4, 44.5, 48.3,
        50, 51, 54, 57, 60.3, 63.5, 70, 76.1, 80, 88.9, 101.6, 108, 114.3, 127, 133, 139.7, 152.4, 159, 168.3, 177.8,
        193.7, 219.1, 244.5, 273, 323.9)
TOL = 0.3       # mm, so viel darf das Teil größer sein als das Normrohr (Zeichengenauigkeit)
ABWEICHUNG = 1.0    # mm, so viel darf das Normrohr größer sein als das Teil; darüber passt die Wand nicht: Sondermaß


def naechstes_kasten(a, b):
    """Kleinstes Quadrat- oder Rechteckrohr (Form, A, B mit A ≥ B), das die Hülle a × b aufnimmt; None, wenn das Teil
    größer als die Reihe ist."""
    a, b = max(a, b), min(a, b)
    kandidaten = [("Quadratrohr", s, s) for s in QUADRAT] + [("Rechteckrohr", x, y) for x, y in RECHTECK]
    passend = [k for k in kandidaten if k[1] >= a - TOL and k[2] >= b - TOL]
    return min(passend, key=lambda k: (k[1] * k[2], k[1])) if passend else None


def naechstes_rund(d):
    """Kleinster Normdurchmesser ≥ d (Außendurchmesser); None, wenn das Teil größer als die Reihe ist."""
    passend = [x for x in RUND if x >= d - TOL]
    return min(passend) if passend else None
