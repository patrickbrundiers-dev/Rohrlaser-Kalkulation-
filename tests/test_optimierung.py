"""Prüft die Stangenoptimierung: Schnittregel, Drehen, Überbelegung, Zufallsangebote.

Aufruf: python tests/test_optimierung.py
"""
import random
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser.optimierung import (Gruppe, Teil, manuell, optimiere, pruefe, untergrenze,  # noqa: E402
                         verbrauch, gemeinsame_schnitte)


def gruppe(teile, stange=1000):
    # Endbeschnitt 20, Greiferrest 80 -> belegbar bis 920; Schnittverlust 0,3; Abstand 2
    g = Gruppe("P", "W", stange, 20, 80, 0.3, 2)
    g.teile = teile
    return g


def teile(n, laenge, a=True, b=True, zeile=13):
    return [Teil(zeile, 10, "A", i, laenge, a, b, 100, 100) for i in range(1, n + 1)]


# 1) Gemeinsamer Schnitt: 2 × 449 mit geraden Enden passen (20+449+0,3+449+0,3 = 918,6 ≤ 920),
#    mit schrägen Enden nicht (20+449+2,6+449+0,3 = 920,9 > 920)
g = gruppe(teile(2, 449))
r = optimiere(g)
assert len(r) == 1 and gemeinsame_schnitte(r[0]) == 1, r
assert abs(verbrauch(g, r[0]) - 918.6) < 1e-6, verbrauch(g, r[0])
g = gruppe(teile(2, 449, a=False, b=False))
assert len(optimiere(g)) == 2

# 2) Drehen: Teile mit einem schrägen Ende (A schräg). Ohne Drehen liegt schräg an gerade -> 2 Stangen;
#    gedreht liegen die geraden Enden aneinander -> 1 Stange
g = gruppe(teile(2, 449, a=False, b=True))
r = optimiere(g)
assert len(r) == 1 and gemeinsame_schnitte(r[0]) == 1, r
assert len(manuell(g)) == 2

# 3) Gemischt: schräge Enden an Stangenanfang/-ende, gerade in der Mitte
g = gruppe(teile(1, 200, a=False, b=True, zeile=13) + teile(3, 150, zeile=14) + teile(1, 200, a=True, b=False, zeile=15))
r = optimiere(g)
assert len(r) == 1 and gemeinsame_schnitte(r[0]) == 4, [(t.zeile, d) for t, d in r[0]]

# 4) Zufallsangebote: nie überbelegt, jedes Teil genau einmal, Untergrenze ≤ optimiert ≤ manuell
rnd = random.Random(4711)
for lauf in range(150):
    stange = rnd.choice([3000, 6000, 6500])
    tl = []
    for z in range(rnd.randint(1, 6)):
        L = round(rnd.uniform(40, stange - 101), 1) if rnd.random() < 0.15 else round(rnd.uniform(40, 1900), 1)
        tl += teile(rnd.randint(1, 25), L, a=rnd.random() < 0.8, b=rnd.random() < 0.8, zeile=13 + z)
    g = gruppe(tl, stange)
    r = optimiere(g)
    pruefe([g], [r])
    assert untergrenze(g) <= len(r) <= len(manuell(g)), (lauf, untergrenze(g), len(r), len(manuell(g)))

print("OK: Optimierung")
