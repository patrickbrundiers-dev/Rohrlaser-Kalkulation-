"""Abwicklungskern (Master-Auftrag Patrick 24.11.2026 „STEP-Import durch abwicklungsbasierte Schnittwegberechnung
beschleunigen“, step_abwicklungskern.py).

A1 Rohrachse aus den Flächen: Rechteckrohr mit Bohrungen beliebig im Raum gedreht, Rundrohr mit Bohrung.
A2 Merkmalskarte der Abwicklung: freie Bereiche liegen nicht über einer Bohrung, Gehrung an beiden Enden (Wand kürzer
   als das Teil) blockiert nichts.
A3 Rückfall: Platte (zwei Längsrichtungen), Rohr mit langem Fenster (Volumen-Gegenprobe), Körper ohne Längsflächen.
A4 Endlinien in der Abwicklung bereinigen (step_offenes_rohr._gerade_raus): Punkte auf einer Geraden fallen weg,
   Knicke bleiben.
A5 Prüf-STEPs bisher gegen neu: gleiche Profile, Maße, Schneidwege und Konturen (Toleranzen des Kerns); offen
   gezeichnete U-Profile mit Messung als geschlossenes Rohr; I10: radiale Bohrung im Rundrohr jetzt gerade (2D).
A6 Modus vergleich: Ergebnis wie bisher, Protokoll mit beiden Zeiten.
A7 Einstellung step_abwicklungskern: Aufruf der Messung mit --abwicklungskern nur bei vergleich/an.

Aufruf: python tests/test_abwicklungskern.py
"""
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung")]

import step_abwicklungskern as ak  # noqa: E402
import step_geometrie as g  # noqa: E402
import step_offenes_rohr as o  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.TopAbs import TopAbs_SOLID  # noqa: E402
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec  # noqa: E402

TESTS = HIER


def ok(text):
    print("OK:", text)


def minus(a, b):
    c = BRepAlgoAPI_Cut(a, b)
    c.Build()
    return c.Shape()


def solid(s):
    return g._liste(s, TopAbs_SOLID)[0]


def re_rohr(l=600.0, a=60.0, b=40.0, s=3.0):
    aussen = BRepPrimAPI_MakeBox(gp_Pnt(-a / 2, -b / 2, 0), a, b, l).Shape()
    innen = BRepPrimAPI_MakeBox(gp_Pnt(-a / 2 + s, -b / 2 + s, -1), a - 2 * s, b - 2 * s, l + 2).Shape()
    return minus(aussen, innen)


def bohrung(form, z, d=10.0, laenge=100.0):
    return minus(form, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, -laenge / 2, z), gp_Dir(0, 1, 0)), d / 2,
                                                laenge).Shape())


def drehen(form):
    tr = gp_Trsf()
    tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 2, 3)), 0.7)
    tr2 = gp_Trsf()
    tr2.SetTranslation(gp_Vec(120, -40, 15))
    return BRepBuilderAPI_Transform(form, tr2.Multiplied(tr), True).Shape()


# A1 Achse
rohr = solid(bohrung(bohrung(re_rohr(), 100.0), 400.0, 16.0))
d, anteil = ak.achse(ak.flaechen(rohr))
assert d is not None and abs(abs(d.Z()) - 1) < 1e-9 and anteil > 0.9, (d, anteil)
gedreht = solid(drehen(rohr))
d2, _ = ak.achse(ak.flaechen(gedreht))
rt = gp_Trsf()
rt.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 2, 3)), 0.7)
soll = gp_Dir(0, 0, 1).Transformed(rt)
assert abs(abs(d2.Dot(soll)) - 1) < 1e-9, (d2.X(), d2.Y(), d2.Z())
rund = solid(bohrung(minus(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 21.2, 500).Shape(),
                           BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -1), gp_Dir(0, 0, 1)), 19.2, 502).Shape()),
                     250.0, 8.0))
d3, _ = ak.achse(ak.flaechen(rund))
assert d3 is not None and abs(abs(d3.Z()) - 1) < 1e-9
ok("A1 Rohrachse aus Ebenen/Zylindern (auch gedreht im Raum), Rundrohr")

# A2 Merkmalskarte
erg, grund = ak.lage(rohr)
assert erg is not None, grund
ax3, info = erg
zm = ax3.Location().Z()
for a_, b_ in info["frei"]:
    for z0, z1 in ((95.0, 105.0), (392.0, 408.0)):          # Bohrungen Ø10 bei 100, Ø16 bei 400
        assert b_ + zm <= z0 - 0.4 or a_ + zm >= z1 + 0.4, (info["frei"], zm)
assert info["schnitte"] == 3
t_alt = g._profil_messen_kern(rohr)
t_neu = g._profil_messen_kern(rohr, vorgabe=erg)
assert not ak.vergleichen(t_alt, t_neu), ak.vergleichen(t_alt, t_neu)
assert t_neu.profilform == "Rechteckrohr" and abs(t_neu.schneidweg - t_alt.schneidweg) < 1e-6
# Gehrung 45° an beiden Enden (Wand kürzer als das Teil): Endzonen aus den Gehrungsflächen
keil = BRepPrimAPI_MakeBox(gp_Pnt(-100, -100, -200), 200, 200, 200).Shape()
tr = gp_Trsf()
tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), math.radians(45))
geh = minus(re_rohr(), BRepBuilderAPI_Transform(keil, tr, True).Shape())
tr2 = gp_Trsf()
tr2.SetRotation(gp_Ax1(gp_Pnt(0, 0, 600), gp_Dir(0, 1, 0)), math.radians(-45))
tr3 = gp_Trsf()
tr3.SetTranslation(gp_Vec(0, 0, 800))
geh = solid(minus(geh, BRepBuilderAPI_Transform(keil, tr2.Multiplied(tr3), True).Shape()))
erg2, grund2 = ak.lage(geh)
assert erg2 is not None, grund2
assert not ak.vergleichen(g._profil_messen_kern(geh), g._profil_messen_kern(geh, vorgabe=erg2))
ok("A2 Merkmalskarte: Schnitte nur in freien Bereichen, Gehrung an beiden Enden, Ergebnis wie bisher")

# A3 Rückfall
platte = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 300, 200, 8).Shape()
assert ak.lage(solid(platte))[0] is None and "Platte" in ak.lage(solid(platte))[1]
fenster = solid(minus(re_rohr(), BRepPrimAPI_MakeBox(gp_Pnt(-20, 0, 2.5), 40, 40, 595).Shape()))
erg3, grund3 = ak.lage(fenster)
assert erg3 is None and ("Volumen" in grund3 or "merkmalsfrei" in grund3), grund3
kugelig = solid(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 40, 20).Shape())
assert ak.lage(kugelig)[0] is None          # Scheibe: Zylindermantel klein gegen die Stirnflächen
ok("A3 Rückfall: Platte, langes Fenster (Volumen-Gegenprobe), Scheibe")

# A4 Endlinien bereinigen
gerade = [(u * 0.5, 10.0 + 1e-9 * (u % 3)) for u in range(200)]
assert o._gerade_raus(gerade) == [gerade[0], gerade[-1]]
knick = [(float(u), 0.0 if u < 50 else (u - 50) * 0.3) for u in range(101)]
r = o._gerade_raus(knick)
assert r == [knick[0], knick[50], knick[-1]], r
assert o._gerade_raus([(0, 0), (1, 1)]) == [(0, 0), (1, 1)]
ok("A4 Endlinien in der Abwicklung: Geraden ohne Zwischenpunkte, Knick bleibt")

# A5 Prüf-STEPs bisher gegen neu
DATEIEN = ["step/T06_QR40x3_L1000_Langloch.step", "step_konturen/K01_RE60x40x3_Konturen.step",
           "step_konturen/K03_RR42-4x2_Konturen.step", "step_regression/R08_Rahmen_4xRE80x40x3_Gehrung.step",
           "step_konturen/K07_U80x40x4_Lage.step", "step_offen/OR1_U_offen_RE60x40x3.step",
           "step_regression/R02_RR42-4x2_L1000_Freiform.step"]
for name in DATEIEN:
    ak.modus_setzen("aus")
    alt = g.analysiere_datei(str(TESTS / name))
    ak.modus_setzen("an")
    del ak.PROTOKOLL[:]
    neu = g.analysiere_datei(str(TESTS / name))
    assert len(alt) == len(neu), name
    for a_, b_ in zip(alt, neu):
        u = ak.vergleichen(a_, b_)
        assert not u, (name, u[:4])
    meth = {e["methode"] for e in ak.PROTOKOLL}
    if "Freiform" in name:
        assert meth == {"bisher"}, (name, ak.PROTOKOLL)        # Freiform: Rückfall
    else:
        assert "abwicklung" in meth, (name, ak.PROTOKOLL)
    if name.startswith("step_konturen/K07") or name.startswith("step_offen/OR1"):
        assert alt[0].geschlossen is not None and neu[0].geschlossen is not None
        assert any(e["quer"] and e["methode"] == "abwicklung" for e in ak.PROTOKOLL), name
ak.modus_setzen("aus")
i10a = g.analysiere_datei(str(TESTS / "step_importengine/I10_RR40x2_L300_Loch25.step"))[0]
ak.modus_setzen("an")
i10n = g.analysiere_datei(str(TESTS / "step_importengine/I10_RR40x2_L300_Loch25.step"))[0]
b8a = [k for k in i10a.konturen_liste if k.get("durchmesser") == 8.0][0]
b8n = [k for k in i10n.konturen_liste if k.get("durchmesser") == 8.0][0]
assert b8a["schraeg"] > 0.5 and b8n["schraeg"] < 0.1, (b8a["schraeg"], b8n["schraeg"])
assert abs(b8n["schnittlaenge"] - 26.64) < 0.01                 # 2D-Rundrohr-Regel wie jede gerade Bohrung
ok(f"A5 {len(DATEIEN)} Prüf-STEPs bisher = neu (Rohre, Gehrungsrahmen, U offen als Rohr, Freiform-Rückfall); "
   "I10 radiale Bohrung gerade")

# A6 Vergleich
ak.modus_setzen("vergleich")
del ak.PROTOKOLL[:]
v = g.analysiere_datei(str(TESTS / "step_konturen/K01_RE60x40x3_Konturen.step"))[0]
ak.modus_setzen("aus")
a6 = g.analysiere_datei(str(TESTS / "step_konturen/K01_RE60x40x3_Konturen.step"))[0]
assert v.schneidweg == a6.schneidweg and v.konturen_liste == a6.konturen_liste
e = ak.PROTOKOLL[0]
assert e["methode"] == "vergleich" and e["gleich"] and e["neu_s"] > 0 and e["bisher_s"] > 0, e
ok("A6 Modus vergleich: Ergebnis wie bisher, Protokoll mit beiden Zeiten")

# A7 Einstellung
from rohrlaser import step_einstellungen  # noqa: E402


class DB:
    def __init__(self, werte):
        self.werte, self.pfad = werte, str(HIER / "x.db")

    def einstellung(self, n):
        return self.werte.get(n)


args = step_einstellungen.mess_argumente(DB({}))   # Vorgabe an (Patrick 24.11.2026)
assert args[args.index("--abwicklungskern") + 1] == "an"
assert "--abwicklungskern" not in step_einstellungen.mess_argumente(DB({"step_abwicklungskern": "aus"}))
args = step_einstellungen.mess_argumente(DB({"step_abwicklungskern": "an"}))
assert args[args.index("--abwicklungskern") + 1] == "an"
g.einstellen({"abwicklungskern": "vergleich"})
assert ak.MODUS == "vergleich"
g.einstellen({})
assert ak.MODUS == ak.MODUS_START
ok("A7 Einstellung step_abwicklungskern → --abwicklungskern → Messung")
print("Alle Tests bestanden.")
