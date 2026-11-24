"""Prüft die Stangenoptimierung: Schnittregel, nie wenden, Überbelegung, Zufallsangebote.

Aufruf: python tests/test_optimierung.py
"""
import random
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import optimierung as opt  # noqa: E402
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

# 2) Nie wenden (Patrick 21.10.2026): Teile mit schrägem Ende A liegen schräg an gerade -> 2 Stangen (früher wurde
#    ein Teil gewendet); Ende A gerade + Ende B schräg vor Ende A gerade ... schräg + gerade passt dagegen
g = gruppe(teile(2, 449, a=False, b=True))
r = optimiere(g)
assert len(r) == 2 and all(d == 0 for f in r for _, d in f), r
g = gruppe(teile(1, 449, a=False, b=True, zeile=13) + teile(1, 449, a=True, b=False, zeile=14))
r = optimiere(g)
assert len(r) == 1 and gemeinsame_schnitte(r[0]) == 1 and [t.zeile for t, _ in r[0]] == [13, 14], r

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

    assert untergrenze(g) <= g.schranke <= len(r), (lauf, g.schranke, len(r))
print("OK    Zufallsangebote: nie überbelegt, Untergrenze ≤ Schranke ≤ Stangen ≤ manuell")


# 5) Schranke der Schnittmuster ist eine echte Untergrenze: kleine Gruppen vollständig durchsuchen
def bisher(g):
    """Stangenzahl nur mit First-/Best-Fit (Verfahren vor den Schnittmustern)."""
    return min(len(opt.aufloesen(g, v(g, g.teile))) for v in (opt.first_fit, opt.best_fit))


rnd = random.Random(815)
geprueft = 0
for lauf in range(120):
    tl = []
    for z in range(rnd.randint(2, 4)):
        tl += teile(rnd.randint(1, 4), round(rnd.uniform(150, 800), 1), a=rnd.random() < 0.8, b=rnd.random() < 0.8,
                    zeile=13 + z)
    g = gruppe(tl)
    st, schranke = opt.muster_optimierung(g)
    pruefe([g], [[opt.anordnen(s) for s in st]])
    alt = opt.EXAKT_MAX_KNOTEN
    opt.EXAKT_MAX_KNOTEN = 10 ** 7
    beste, ganz = opt.exakt(g, len(st))
    opt.EXAKT_MAX_KNOTEN = alt
    assert ganz
    optimum = len(beste) if beste is not None else len(st)
    assert schranke <= optimum <= len(st), (lauf, schranke, optimum, len(st))
    geprueft += schranke > untergrenze(g)
print(f"OK    Schranke der Schnittmuster nie über dem Optimum (120 Gruppen vollständig durchsucht, "
      f"{geprueft} davon mit Schranke über der einfachen Untergrenze)")

# 6) Große Aufträge (40 Gruppen, 34–296 Teile, 3–12 Längen): reproduzierbar besser als First-/Best-Fit
rnd = random.Random(1)
summe = summe_bisher = bewiesen = 0
for lauf in range(40):
    laengen = [(rnd.choice([180, 250, 333, 420, 575, 780, 950, 1240, 1500, 1830, 2100, 2650]) + rnd.randint(0, 40),
                rnd.random() < 0.7) for _ in range(rnd.randint(3, 12))]
    g = Gruppe("P", "S", 6000, 10, 80, 2, 3)
    g.teile = [Teil(i, i, f"A{i}", k + 1, L, ger, ger, 100, 100) for i, (L, ger) in enumerate(laengen)
               for k in range(rnd.randint(2, 40))]
    r = optimiere(g)
    pruefe([g], [r])
    b = bisher(g)
    assert len(r) <= b, (lauf, len(r), b)
    summe, summe_bisher, bewiesen = summe + len(r), summe_bisher + b, bewiesen + g.bewiesen
assert (summe, summe_bisher, bewiesen) == (1250, 1271, 38), (summe, summe_bisher, bewiesen)
print(f"OK    40 große Gruppen: {summe} statt {summe_bisher} Stangen, {bewiesen} nachweislich optimal")

# Zwischenspeicher von anordnen/passt (0.8.5): gleiche Ergebnisse wie ohne, große Gruppe mit Gehrungen schnell
import time  # noqa: E402
rnd = random.Random(7)
g = Gruppe("RE 60x40x3", "S", 6000, 20, 80, 0.3, 2, querschnitt=("Kasten", 60, 40))
gehr = [((45, 0), (40, 0)), ((45, 0), (45, 180)), ((30, 90), None), (None, (20, 270))]
g.teile = [Teil(z, z, "A", i + 1, L, a is None, b is None, 60, 60, a, b, drehung=dr)
           for z, (L, (a, b), dr) in enumerate((rnd.choice([370, 420, 615, 850, 1450]), rnd.choice(gehr),
                                                rnd.choice([opt.FREI, opt.FREI, opt.UNBEKANNT])) for _ in range(12))
           for i in range(rnd.randint(30, 90))]
for _ in range(300):
    s_ = rnd.sample(g.teile, rnd.randint(1, 14))
    opt._ANORDNUNG.clear()
    frisch = opt.anordnen(s_, g)
    assert opt.anordnen(s_, g) == frisch and opt.anordnen(list(s_), g) == frisch
    assert opt.passt(g, s_) == (opt.vertraeglich(g, s_) and opt.verbrauch(g, frisch) <= g.nutzbar_bis + opt.EPS)
t0 = time.time()
r = optimiere(g)
pruefe([g], [r])
dauer = time.time() - t0
assert dauer < 60, dauer
print(f"OK    Zwischenspeicher: gleiche Anordnung, {len(g.teile)} Teile mit Gehrungen in {dauer:.1f} s")

print("OK: Optimierung")
