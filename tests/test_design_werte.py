"""UI-Modernisierung U7 (Patrick 12.11.2026): gemeinsame Gestaltungswerte in design.py.

Prüft: die Oberfläche (stil.py) nimmt die Grundfarben aus design.py (dieselben wie die PDF-Ausgaben); die Farben der
Seitenleiste aus design.py stehen so im Stylesheet und haben im Dunkelmodus eine eigene Entsprechung; Abstände sind
ganze Pixel in aufsteigender Reihe.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))

from rohrlaser import design, stil  # noqa: E402


def ok(text):
    print("OK    ", text)


for name in ("AKZENT", "AKZENT_DUNKEL", "TEXT", "TEXT_GRAU", "ROT", "ROT_FLAECHE", "GELB_TEXT", "GELB_FLAECHE",
             "ORANGE", "GRUEN", "GRUEN_FLAECHE", "BLAU_FLAECHE", "RAHMEN", "LINIE", "FLAECHE"):
    assert getattr(stil, name) == getattr(design, name), name
ok("Grundfarben der Oberfläche = design.py (wie in den PDF-Ausgaben)")

nav = {n: getattr(design, n) for n in dir(design) if n.startswith("NAVIGATION")}
assert len(nav) == 6, nav
for n, farbe in nav.items():
    assert re.fullmatch(r"#[0-9A-F]{6}", farbe), (n, farbe)
    assert farbe in stil.STIL, f"{n} {farbe} nicht im Stylesheet"
dunkel = next(v for k, v in stil.__dict__.items() if isinstance(v, dict) and "Dunkel" in v)["Dunkel"]
for n in ("NAVIGATION", "NAVIGATION_HOVER", "NAVIGATION_GEWAEHLT"):
    assert dunkel.get(nav[n]) not in (None, nav[n]), f"{n}: im Dunkelmodus dunkler"
assert design.HAUPTKNOPF_DUNKEL in stil.STIL or any(design.HAUPTKNOPF_DUNKEL in str(v) for v in stil.__dict__.values())
ok("Seitenleiste: Farben aus design.py im Stylesheet, eigene Werte im Dunkelmodus")

assert 0 < design.ABSTAND_KLEIN < design.ABSTAND < design.ABSTAND_GROSS
assert all(isinstance(x, int) for x in (design.ABSTAND_KLEIN, design.ABSTAND, design.ABSTAND_GROSS))
ok("Abstände klein < normal < groß, ganze Pixel")
print("Alle Tests OK")
