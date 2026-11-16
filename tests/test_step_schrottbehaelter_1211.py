"""STEP-Probe mit Patricks Schrottbehälter (SolidWorks, 12.11.2026): zwei Fehler, die echte Teile verfälschten.

1 Die Mutter ISO 4032 hat in der Datei umgedrehte Flächen (Normale zeigt teils nach innen). Der Sechskant wurde
  nicht erkannt, die Mutter als Rundrohr 13 × 3,1 gemessen. Jetzt: Normalen nach außen gedreht, Mutter = Normteil,
  auch wenn sie an den Fasen kleine Außenzylinder hat.
2 Die Lasche 92 × 44 × 4 lag an dieser „Rohr“-Mutter und fiel als ihr Anbauteil still weg. Jetzt: ein Normteil, das
  nicht übernommen wird, trägt keine Anbauteile, und ein Körper größer als sein „Rohr“ ist nie dessen Anbauteil.

Aufruf: python tests/test_step_schrottbehaelter_1211.py
"""
import json
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

import step_drehfraes as df  # noqa: E402
from rohrlaser import step  # noqa: E402


def ok(t):
    print("OK  ", t)


# ------------------------------------------------------------------ 1 Sechskant mit umgedrehten Flächen
SW = 13.0
o, d = (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
flaechen = []
for k in range(6):
    w = math.radians(60 * k)
    n = (math.cos(w), math.sin(w), 0.0)
    p = tuple(SW / 2 * x for x in n)
    if k in (1, 4):         # wie in der Datei: zwei Flächen mit Normale nach innen
        n = tuple(-x for x in n)
    flaechen.append(dict(typ="eben", normale=n, punkt=p, flaeche=45.0))
kante, rest = df.sechskante(flaechen, o, d)
assert len(kante) == 1 and not rest and abs(kante[0]["schluessel"] - SW) < 1e-6, (kante, rest)
ok("Sechskant SW 13 auch mit zwei nach innen zeigenden Flächen erkannt")

# ------------------------------------------------------------------ 2 kein Anbauteil an Normteil / an Kleinerem


def mw(koerper, volumen, anbau_an=None, **w):
    a = json.dumps([dict(nr=1, art="Sonstiges", quelle=f"Körper {anbau_an}", z=3)]) if anbau_an else ""
    return dict(datei="bin.step", koerper=koerper, volumen=str(volumen), anbauteile=a, artikel=f"T{koerper}", **w)


lasche = mw(5, 16192.0)
mutter = mw(9, 520.0, anbau_an=5, _normteil="ISO")
assert step.anbau_von([lasche, mutter]) == {}
mutter_ohne_name = mw(9, 520.0, anbau_an=5)
assert step.anbau_von([lasche, mutter_ohne_name]) == {}, "größerer Körper ist kein Anbauteil"
rohr, knoten = mw(1, 250000.0, anbau_an=2), mw(2, 3000.0)
assert step.anbau_von([rohr, knoten]) == {1: "T1"}                 # wie bisher: kleines Blech am Rohr
assert step.anbau_von([lasche, dict(mutter, _uebernehmen=True)]) == {}     # größer bleibt größer
ok("Lasche an der Mutter bleibt Laserteil; kleines Anbauteil am Rohr wie bisher")

print("STEP-Probe Schrottbehälter: alle Tests bestanden.")
