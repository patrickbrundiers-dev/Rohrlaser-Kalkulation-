"""3D-Ansicht der Schweißbaugruppe wie im Rohr-Editor (Patrick 24.10.2026, Plan B1–B3 „1a 2a 3a“):
- Nasen einer Steckverbindung im Rohrmodell (rohr3d): Laschen der Wand über den Schnitt hinaus, Lage nach Vorgabe
  bzw. Winkel, Rundrohr als Bogenstück, Ende A verschoben; nasen_stuecke für den STEP-Export
- Nasenlage aus der Einbaulage (quer = hintereinander längs der Aufnahme)
- Eingaben mit den Steckverbindungen des Editors (Schlitze in der Aufnahme, Nasen am Stecker, Länge + Flanke)
- Schweißnaht als Raupe: Kehlnaht als Dreieck mit Schenkel a·√2 entlang der Flächen, Stumpfnaht flach
- Nahtverlauf aus dem Stoß (Schnittkante des Steckerendes)

Aufruf: python tests/test_baugruppe_ansicht.py
"""
import math
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import ansicht3d, rohr3d, steckverbindung as sv  # noqa: E402
from rohrlaser.baugruppe_ansicht import (BaugruppenAnsicht, Flaechen, eigenes_modell, eingaben_stecken,  # noqa: E402
                                         flaechen_an_naht, in_lage, naehte_einsetzen, nasen_winkel, rohr_netz,
                                         verlauf_aus_stoss)

app = QApplication.instance() or QApplication([])
PA = dict(form="Quadratrohr", a=40, b=40, wand=3)
PS = dict(form="Quadratrohr", a=30, b=30, wand=2)


def ok(text):
    print("OK    ", text)


def leer():
    return dict(konturen=[], a={}, b={})


def zs(netz, arten=None):
    p = netz["p"]
    idx = [i for a, t in netz["t"].items() if arten is None or a in arten for i in t]
    return [p[3 * i + 2] for i in idx]


# ------------------------------------------------------------------ Nasen im Rohrmodell
v = sv.neu({"id": 1}, {"id": 2}, PS, None, ende="b", x=200, seite="oben", kennung="S1")
_, s_b, plus = sv.anwenden(v, leer(), leer(), PA, PS)
assert plus == 3.0                                       # Flanke = Wand der Aufnahme
n = rohr3d.netz(s_b, PS, 100 + plus)
assert max(zs(n)) == 103.0 and len(n["nasen"]) == 2
assert sorted(x["winkel"] for x in n["nasen"]) == [0.0, 180.0]        # quer: oben und unten (Wand der Breite a)
for x in n["nasen"]:
    (fuss, spitze), = x["aussen"][:1]
    assert abs(fuss[2] - 100.0) < 1e-6 and abs(spitze[2] - 103.0) < 1e-6
    assert abs(abs(fuss[1]) - 15.0) < 1e-6                             # außen auf der Wand oben/unten
    breite = math.dist(x["aussen"][0][0], x["aussen"][-1][0])
    assert abs(breite - v["bN"]) < 1e-6, breite
# ohne Nasen bleibt das Rohr bis zum Ende, mit Nasen endet der Schnitt um die Flanke früher
ohne = rohr3d.netz(leer(), PS, 103)
assert max(zs(ohne, ("EB",))) == 103.0 and max(zs(n, ("A",))) == 103.0
assert rohr3d.nasen_stuecke(s_b, PS, 103) == n["nasen"]
# Winkel vorgegeben, 4 Nasen, Rundrohr als Bogen
n90 = rohr3d.netz(s_b, PS, 103, nasen_winkel={"b": 90})
assert sorted(x["winkel"] for x in n90["nasen"]) == [90.0, 270.0]
rund = dict(form="Rundrohr", a=30, wand=2)
v4 = dict(sv.neu({"id": 1}, {"id": 2}, rund, None, ende="a", x=100, seite="0°", kennung="S2"), anzahl=4)
_, s_a, plus4 = sv.anwenden(v4, leer(), leer(), dict(form="Rundrohr", a=48.3, wand=3), rund)
nr = rohr3d.netz(s_a, rund, 80 + plus4)
assert len(nr["nasen"]) == 4 and abs(min(zs(nr))) < 1e-6
assert all(abs(math.hypot(q[0][0], q[0][1]) - 15.0) < 0.05 for x in nr["nasen"] for q in x["aussen"])
ok("Nasen im Rohrmodell: Laschen über den Schnitt hinaus, Lage nach Vorgabe/Winkel, Rundrohr, für den STEP-Export")

# ------------------------------------------------------------------ Nasenlage aus der Einbaulage
LA = [0, 0, 0, 1, 0, 0, 0, 1, 0]                 # Aufnahme längs X, Y oben
LS = [40, 0, 20, 0, 0, 1, 1, 0, 0]               # Stecker steht senkrecht auf der Aufnahme
assert nasen_winkel(dict(waende="quer"), LA, LS, "Quadratrohr") == 270.0
assert nasen_winkel(dict(waende="längs"), LA, LS, "Quadratrohr") == 0.0
assert nasen_winkel(dict(waende="quer"), LA, LA, "Quadratrohr") is None      # gleiche Achse: keine Lage
assert nasen_winkel(dict(waende="quer"), None, LS, "Rundrohr") is None
assert in_lage((1, 2, 3), LS) == (41.0, 2.0, 23.0)
ok("Nasenlage aus der Einbaulage: quer = Nasen hintereinander längs der Aufnahme, längs um 90° gedreht")

# ------------------------------------------------------------------ Eingaben mit den Steckverbindungen des Editors
pos = {1: dict(laenge=80.0, technik=None), 2: dict(laenge=40.0, technik=None)}
prof = {1: PA, 2: PS}
v2 = sv.neu({"id": 1}, {"id": 2}, PS, None, ende="a", x=40, seite="oben", kennung="S9")
e = eingaben_stecken(pos, [v2], prof.get)
assert sum(1 for z in e[1][0]["konturen"] if z.get("art") == "Rechteck") == 2       # zwei Schlitze
assert e[2][0]["a"]["nasen"]["id"] == "S9" and e[2][1] == 43.0                      # Nasen, Länge + Flanke
assert eingaben_stecken(pos, [], prof.get)[2][1] == 40.0
assert eigenes_modell(e[2][0], None) and not eigenes_modell(dict(e[2][0], biegerohr={"r": 1}), None)
assert not eigenes_modell(e[2][0], {"t": {"AN": [0, 1, 2]}})
ok("Eingaben mit den Steckverbindungen des Editors: Schlitze, Nasen, Länge; Biegerohr/Anbauteile bleiben STEP")

# ------------------------------------------------------------------ Raupen
na = rohr_netz(e[1][0], PA, e[1][1])
ns = rohr_netz(e[2][0], PS, e[2][1], {"a": nasen_winkel(v2, LA, LS, "Quadratrohr")})
assert min(zs(ns)) < -2.9                       # Nasen an Ende A ragen unter das STEP-Ende (z = 0)
netz, _ = ansicht3d.baugruppe([dict(na, lage=LA), dict(ns, lage=LS)], farben=[0, 1])
f = Flaechen(netz)
normalen = flaechen_an_naht(f, (40.0, -15.0, 20.0))
assert any(abs(x[1] + 1) < 1e-6 for x in normalen) and any(x[2] > 0.9 for x in normalen), normalen   # Wand, oben
zug = [c for q in [(25, -15, 20), (55, -15, 20), (55, 15, 20), (25, 15, 20), (25, -15, 20)] for c in q]
kopie = dict(netz, p=list(netz["p"]), t=dict(netz["t"]))
assert naehte_einsetzen(kopie, [("SN", [zug], "Kehlnaht", 3.0)], f) == 1
raupe = [tuple(kopie["p"][3 * i:3 * i + 3]) for i in kopie["t"]["SN"]]
mitte = [q for q in raupe if 33 < q[0] < 47 and q[1] < 0]                  # gerades Stück an der Wand y = −15
assert mitte and max(q[2] for q in mitte) <= 20 + 3 * math.sqrt(2) + 1e-3 and min(q[1] for q in mitte) >= -15 - 3 * \
    math.sqrt(2) - 1e-3                     # Schenkel auf der Aufnahme folgt dort ihrer Rundung (Außenradius)
assert any(abs(q[2] - (20 + 3 * math.sqrt(2))) < 0.05 for q in mitte)     # Schenkel a·√2 an der Wand hoch
assert kopie["l"]["SN"] == [zug]                                           # Linie bleibt (von weitem sichtbar)
# Stumpfnaht flach, ohne Flächen an der Naht nur die Linie
k2 = dict(netz, p=list(netz["p"]), t=dict(netz["t"]))
assert naehte_einsetzen(k2, [("SH", [zug], "Stumpfnaht", 2.0), ("SV", [[500, 500, 500, 510, 500, 500]], "Kehlnaht",
                                                                     None)], f) == 1
assert "SH" in k2["t"] and "SV" not in k2["t"] and k2["l"]["SV"]
ok("Schweißnaht als Raupe: Kehlnaht als Dreieck (Schenkel a·√2), Stumpfnaht flach, Linie bleibt")

# ------------------------------------------------------------------ Nahtverlauf aus dem Stoß
stoss = [dict(stecker=7, aufnahme=6, ende="a", z=40.0)]
zuege = verlauf_aus_stoss(dict(koerper=["6", "7"]), stoss, {"7": (ns, LS)})
assert len(zuege) == 1
pk = [zuege[0][i:i + 3] for i in range(0, len(zuege[0]), 3)]
assert all(abs(q[2] - 20.0) < 0.5 for q in pk) and max(q[0] for q in pk) > 54 and min(q[0] for q in pk) < 26
assert verlauf_aus_stoss(dict(koerper=["6"]), stoss, {"7": (ns, LS)}) == []
ok("Nahtverlauf aus dem Stoß: Schnittkante des Steckerendes auf der Aufnahme")

# ------------------------------------------------------------------ Leiste
b = BaugruppenAnsicht()
b.setzen(netz, "T-Stoß", "Info")
assert b.ansicht.netz is not None and b.info.text() == "Info"
b.ansicht.gier = 1.0
b.setzen(kopie, "T-Stoß", "")                    # Blickrichtung bleibt beim neuen Netz
assert b.ansicht.gier == 1.0
b.messen_knopf.setChecked(True)
assert b.ansicht.messen and b.ansicht.mess_max == 2
b.winkel_knopf.setChecked(True)
assert not b.messen_knopf.isChecked() and b.ansicht.mess_max == 3
b.messen_aus()
assert not b.winkel_knopf.isChecked()
ok("Leiste wie im Teile-Editor: Blick, Darstellung, Nur Gewähltes, Nähte, Messen, Winkel")
print("3D-Ansicht der Schweißbaugruppe: alle Tests bestanden.")
