"""Paket K aus dem PROfirst-Plan (Patrick 12.11.2026 „alles umsetzten“, im STEP-Import-Thread als Paket K):
K1 Bohren, Gewinde, Senken aus Layer oder Farbe der DXF.

Aufruf: python tests/test_paket_k.py
"""
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import bohrbild, dxf_import as di  # noqa: E402


def ok(t):
    print("OK    ", t)


def g(*paare):
    return "\n".join(f"{c}\n{v}" for c, v in paare)


def datei(*entitaeten, tabellen=()):
    teile = []
    if tabellen:
        teile.append(g((0, "SECTION"), (2, "TABLES"), *tabellen, (0, "ENDSEC")))
    teile.append(g((0, "SECTION"), (2, "ENTITIES"), *[p for e in entitaeten for p in e], (0, "ENDSEC"), (0, "EOF")))
    return "\n".join(teile)


def lw(pk, layer="0", farbe=None):
    out = [(0, "LWPOLYLINE"), (8, layer)] + ([(62, farbe)] if farbe else []) + [(90, len(pk)), (70, 1)]
    for x, y in pk:
        out += [(10, x), (20, y)]
    return out


def kreis(c, r, layer="0", farbe=None):
    return [(0, "CIRCLE"), (8, layer)] + ([(62, farbe)] if farbe else []) + [(10, c[0]), (20, c[1]), (40, r)]


# ------------------------------------------------------------------ K1
LAYER = ((0, "TABLE"), (2, "LAYER"), (0, "LAYER"), (2, "SENKER"), (70, 0), (62, 6), (0, "ENDTAB"))
text = datei(lw([(0, 0), (200, 0), (200, 100), (0, 100)]),
             kreis((20, 20), 3.4, farbe=1),                 # Farbe 1 am Element
             kreis((50, 20), 4, "GEWINDE_M8"),              # Layername
             kreis((80, 20), 5, "SENKER"),                  # Farbe 6 vom Layer („VonLayer“)
             kreis((110, 20), 6),                           # ohne: nur lasern
             kreis((140, 20), 4, "BOHRUNGEN"),              # „BOHRUNG“ ist kein Bearbeitungs-Layer
             lw([(160, 15), (170, 15), (170, 25), (160, 25)], farbe=1),     # Rechteck in Farbe 1: bleibt Rechteck
             tabellen=LAYER)
farben = di.farben_aus(lambda n: {"dxf_farbe_gewinde": 1, "dxf_farbe_senkung": 6, "dxf_farbe_bohren": 0}.get(n))
assert farben == {1: bohrbild.GEWINDE_SCHNEIDEN, 6: bohrbild.SENKEN}, farben
t = di.importieren(text, "k1.dxf", farben=farben)["teile"][0]
aus = {k["x"]: k.get("aus") for k in t["e"]["konturen"]}
assert aus == {20.0: bohrbild.GEWINDE_SCHNEIDEN, 50.0: bohrbild.GEWINDE_SCHNEIDEN, 80.0: bohrbild.SENKEN, 110.0: None,
               140.0: None, 165.0: None}, aus
assert "davon 3 mit Bearbeitung aus Layer/Farbe" in t["zusammenfassung"], t["zusammenfassung"]
assert all(a in bohrbild.AUSFUEHRUNGEN for a in aus.values() if a)
ohne = di.importieren(text, "k1.dxf")["teile"][0]
assert {k["x"]: k.get("aus") for k in ohne["e"]["konturen"]}[20.0] is None          # Farben ohne Einstellung: aus
assert {k["x"]: k.get("aus") for k in ohne["e"]["konturen"]}[50.0] == bohrbild.GEWINDE_SCHNEIDEN
assert di.farben_aus(lambda n: None) == {}
ok("K1 DXF: Farbe am Element und vom Layer, Layername GEWINDE -> Ausführung; BOHRUNGEN und Rechteck bleiben; "
   "ohne Einstellung keine Farbe")
print("Paket K: alle Tests bestanden.")
