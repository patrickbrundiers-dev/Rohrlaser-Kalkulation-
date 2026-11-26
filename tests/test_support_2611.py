"""Supportpaket 26.11.2026 (0.9.516): Packvorschlag großer Sendungen (Angebot mit 40.000 Teilen, „Fracht berechnen …“
und „Packvorschlag“ hingen je 23 s).

1. Packkern-Prüfung mit schnellem Vorlauf meldet genau dasselbe wie die volle Prüfung (Zufallsfälle mit und ohne
   Überschneidungen, Rundrohre, Mindestabstand).
2. Merker in Reihe/Lage: nach jedem Anhängen neu gerechnet.
3. Gleiche Packrechnung wird gemerkt: Ergebnis bitgleich, jede Rückgabe eine eigene Kopie, Änderung rechnet neu.
Der Kundenimport-Absturz (Neukunde mit Kundennummer) steht in test_kunden_import.py.

Aufruf: python tests/test_support_2611.py
"""
import os
import random
import sys
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import fracht_richtwerte, packkern, paletten  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ 1 Prüfung: Vorlauf ändert keine Meldung
def faelle(seed, anzahl):
    rnd = random.Random(seed)
    for _ in range(anzahl):
        a = rnd.choice([0.0, 2.0, 5.0])
        pk = types.SimpleNamespace(p=dict(rand=0.0, pb=800.0, pl=1200.0, ueber=50.0), a=a, L=1300.0, lmax=1300.0,
                                   frei=1000.0)
        t = []
        if rnd.random() < 0.5:                      # wild verteilt: meist Überschneidungen
            for _i in range(rnd.randint(1, 50)):
                x0, y0 = rnd.uniform(-20, 1100), rnd.uniform(0, 750)
                z0 = rnd.choice([0.0, 20.0, 40.0, rnd.uniform(0, 60)])
                r = rnd.choice([None, None, 20.0, 30.0])
                w, h = r or rnd.uniform(5, 40), r or rnd.uniform(5, 30)
                t.append(dict(x0=x0, x1=x0 + rnd.uniform(20, 300), y0=y0, y1=y0 + w, z0=z0, z1=z0 + h, rund=r,
                              lage=int(z0 // 20) + 1, innen_von=None, quer=rnd.random() < 0.3))
        else:                                       # dicht gepackt wie der Packkern, ab und zu knapp daneben
            z = 0.0
            for lg in range(1, rnd.randint(2, 6)):
                y = 0.0
                while y < 760:
                    x = 0.0
                    for _j in range(rnd.randint(1, 3)):
                        t.append(dict(x0=x, x1=x + 300.0, y0=y, y1=y + 20.0, z0=z, z1=z + 20.0,
                                      rund=rnd.choice([None, 20.0]), lage=lg, innen_von=None, quer=False))
                        x += 300.0 + a - rnd.choice([0.0, 0.0, 0.0, 0.0, 0.5])
                    y += 20.0 + a - rnd.choice([0.0, 0.0, 0.0, 0.0, 0.0, 0.5])
                z += 20.0 - rnd.choice([0.0, 0.0, 0.0, 1.0])
        yield pk, t


schnell = [packkern.pruefen(pk, None, t) for pk, t in faelle(7, 1500)]
original = packkern._beruehrt
packkern._beruehrt = lambda aussen, a: True       # ohne Vorlauf = Prüfung wie bis 0.9.515
try:
    voll = [packkern.pruefen(pk, None, t) for pk, t in faelle(7, 1500)]
finally:
    packkern._beruehrt = original
assert schnell == voll
n_ok = sum(1 for f in voll if not f)
assert 100 < n_ok < 1400, n_ok
ok(f"Prüfung mit Vorlauf: 1.500 Zufallsfälle gleich wie ohne ({n_ok} ohne, {1500 - n_ok} mit Meldungen)")

# ------------------------------------------------------------------ 2 Merker in Reihe und Lage
rh = packkern.Reihe(20.0, 20.0)
rh.teile.append((0, 3, 100.0, (20.0, 20.0)))
assert rh.laenge(2.0) == 304.0 and rh.xl_grenzen() == (100.0, 100.0)
rh.teile.append((1, 2, 50.0, (20.0, 20.0)))
assert rh.laenge(2.0) == 3 * 100.0 + 2 * 50.0 + 4 * 2.0 and rh.laenge(0.0) == 400.0
assert rh.xl_grenzen() == (50.0, 100.0)
lg = packkern.Lage("l")
lg.reihen.append(rh)
assert lg.breite(2.0) == 20.0 and lg.b_min(2.0) == 20.0
lg.reihen.append(packkern.Reihe(10.0, 20.0))
assert lg.breite(2.0) == 32.0 and lg.b_min(2.0) == 10.0
ok("Reihe/Lage: Länge, kürzestes/längstes Teil und Breite nach jedem Anhängen neu")

# ------------------------------------------------------------------ 3 gleiche Packrechnung gemerkt
lht = fracht_richtwerte.richtwerte("33100")["fracht_lht"]
einst = {"palette_packkern": "ja", "palette_hoehe_gesamt": 1200, "palette_max_brutto": 1500.0,
         "palette_ueberstand": 50.0, "palette_max_teillaenge": 6500}
pos = [dict(id=1, pos=10, artikel="A1", stueck=12000, laenge=120.0),
       dict(id=2, pos=20, artikel="A2", stueck=6000, laenge=250.0)]
werte = [dict(gewicht=0.15, profil_abm=("Rundrohr", 20.0, 20.0, 1.5)),
         dict(gewicht=0.3, profil_abm=("Quadratrohr", 20.0, 20.0, 1.5))]
paletten._merker.clear()
t0 = time.time()
e1 = paletten.packen(pos, werte, lht, "EUR", "LG", einst)
d1 = time.time() - t0
roh = paletten._packen(pos, werte, lht, "EUR", "LG", einst)
assert repr(e1) == repr(roh)
t0 = time.time()
e2 = paletten.packen(pos, werte, lht, "EUR", "LG", einst)
d2 = time.time() - t0
assert repr(e2) == repr(e1) and e2 is not e1 and e2["paletten"] is not e1["paletten"]
assert d2 < d1 / 3, (d1, d2)
e2["paletten"].clear()
e3 = paletten.packen(pos, werte, lht, "EUR", "LG", einst)
assert repr(e3) == repr(e1)
e4 = paletten.packen([dict(pos[0], stueck=11999), pos[1]], werte, lht, "EUR", "LG", einst)
assert e4["gesamt_stueck"] == 17999
klein = paletten.packen([dict(pos[0], stueck=50)], werte[:1], lht, "EUR", "LG", einst)
assert klein["gesamt_stueck"] == 50 and len(paletten._merker) == 2       # kleine Sendungen nicht gemerkt
ok(f"gleiche Packrechnung gemerkt ({d1:.1f} s → {d2:.2f} s), bitgleich, eigene Kopie, Änderung rechnet neu")

print("Alle Prüfungen bestanden.")
