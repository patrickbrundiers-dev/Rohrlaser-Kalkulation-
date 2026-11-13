"""Spiegelteile (GEO-013, Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“):

- linkes und rechtes Teil (längs, quer oder beides gespiegelt) werden erkannt, identische Teile nicht
- anderes Profil, andere Länge, anderer Schneidweg oder fehlende Konturen: kein Spiegelteil
- Programmierzeit zählt für das Paar einmal und wird nach Stückzahl verteilt; Einstellung „nein“ schaltet es ab

Aufruf: python tests/test_spiegel.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "programm"))
from rohrlaser import rechnen, spiegel  # noqa: E402


def ok(t):
    print("OK    ", t)


def teil(konturen, a=0, b=0, **w):
    tech = dict(quelle="Rechner", a=dict(winkel=a), b=dict(winkel=b), konturen=konturen)
    return dict(dict(profil_id="QR 40x40x3", werkstoff_id="S235", laenge=500, schneidweg=800, einstiche=3,
                     stueck=10, technik=json.dumps(tech)), **w)


links = teil([dict(art="Bohrung", d=10, anzahl=3, abstand=50, x=50, seite="vorne")], a=45)
# längs gespiegelt: Bohrbild vom anderen Ende, Gehrung am Ende B
rechts_laengs = teil([dict(art="Bohrung", d=10, anzahl=3, abstand=50, x=350, seite="vorne")], b=45)
# quer gespiegelt: gleiche Stelle, andere Seite (vorne ↔ hinten)
rechts_quer = teil([dict(art="Bohrung", d=10, anzahl=3, abstand=50, x=50, seite="hinten")], a=45)
beides = teil([dict(art="Bohrung", d=10, anzahl=3, abstand=50, x=350, seite="hinten")], b=45)

assert spiegel.art(links, rechts_laengs) == "längs", spiegel.art(links, rechts_laengs)
assert spiegel.art(links, rechts_quer) == "quer", spiegel.art(links, rechts_quer)
assert spiegel.art(links, beides) == "längs und quer"
assert spiegel.art(links, dict(links)) is None
ok("längs, quer und beides gespiegelt erkannt; identisches Teil ist kein Spiegelteil")

assert spiegel.art(links, dict(rechts_laengs, profil_id="QR 50x50x3")) is None
assert spiegel.art(links, dict(rechts_laengs, laenge=520)) is None
assert spiegel.art(links, dict(rechts_laengs, schneidweg=900)) is None
assert spiegel.art(links, dict(rechts_laengs, technik=None)) is None
anders = teil([dict(art="Bohrung", d=12, anzahl=3, abstand=50, x=350, seite="vorne")], b=45)
assert spiegel.art(links, anders) is None
ok("anderes Profil, Länge, Schneidweg, Bohrungsmaß oder fehlende Konturen: kein Spiegelteil")

pos = [dict(links, artikel="H-100-L", stueck=10), dict(rechts_laengs, artikel="H-100-R", stueck=30),
       dict(links, artikel="X-1", profil_id="QR 50x50x3", stueck=5)]
assert spiegel.paare(pos) == [(0, 1, "längs")]
pz = {0: (20.0, False), 1: (16.0, False), 2: (12.0, False)}
assert rechnen.programmierung_gleich(pos, pz, {}) == 2
assert abs(pz[0][0] - 5.0) < 1e-9 and abs(pz[1][0] - 15.0) < 1e-9 and pz[2] == (12.0, False), pz
ok("Spiegelpaar: Programmierzeit einmal (20 min), nach Stückzahl verteilt 5 + 15 min; anderes Teil unverändert")

pz = {0: (20.0, False), 1: (16.0, True)}
assert rechnen.programmierung_gleich(pos[:2], pz, {}) == 0 and pz[0] == (20.0, False)
pz = {0: (20.0, False), 1: (16.0, False)}
assert rechnen.programmierung_gleich(pos[:2], pz, {"programmierung_gleich": "nein"}) == 0
ok("von Hand eingetragene Zeit und Einstellung „nein“ bleiben je Position")
print("Alle Spiegelteil-Tests bestanden.")
