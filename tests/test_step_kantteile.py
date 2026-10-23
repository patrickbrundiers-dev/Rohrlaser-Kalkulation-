"""Prüft die STEP-Messung von Kantteilen, Sonderkonturen und Gravuren (Patrick 23.10.2026, Plan „Rohr- und
Blech-Editor, STEP robuster“, Freigabe 1a 2a 3b 4a):
- K1 Winkel 100 × 50 × 3 mit Biegeradius 3 und 6 Bohrungen Ø9: Kantteil mit Schenkeln 100/50, −90°, r 3,
  Zuschnitt 300 × 144,27 (k 0,33), Bohrungen mit Lage, Schneidweg = Außen- + Innenkontur der Abwicklung
- K2 derselbe Winkel scharfkantig: L-Profil, Kantteil als Alternative (Grenzfall, Frage 1 a), Radius = Blechdicke
- K3 Z 40/60/40 × 2 mit Radien: Schenkel 40/60/40, +90° / −90°
- K4 Hutprofil scharfkantig: Kantteil statt offenes Sonderprofil, 5 Schenkel 22/30/50/30/22
- K5 U 30/100/30 × 3 mit Ausklinkungen und Ausschnitt: Kantteil-Alternative mit freier Außenkontur und Rechteck
- K6 Schale 200 × 150 mit 4 Rändern 20 (Kanten in zwei Richtungen): mehrachsig gekantet, 4 Kantungen, Zuschnitt
  232,36 × 182,36 mit freigeschnittenen Ecken, keine Schenkel (Frage 2 a)
- K7 Winkel K1 beliebig im Raum gedreht: gleiche Werte
- K8 T-Stoß aus zwei gleich dicken Blechen: kein Kantteil
- S1 Rechteckrohr mit Ausschnitt über die Ecke: Sonderkontur, Wände 0°/270°, Umriss, Schnittlänge
- S2 Ausschnitt über drei Wände: Sonderkontur, Wände 90°/0°/270°
- S3 Ausklinkung am Ende über die Ecke: Ende komplex mit Umriss
- S4 Bohrung durch beide Wände: zwei Bohrungen, je eine Wand, Umriss als Kreis
- G1 Prägung 0,2 mm (Balken und runde Vertiefung Ø10) im Rechteckrohr: Gravur mit Tiefe 0,2, keine Sackbohrung,
  Prüfstatus plausibel
- G2 Prägung im Rundrohr: Gravur mit Tiefe 0,2 und Umriss um 0°
- V1 zwei gekreuzte Quadratrohre gleicher Hülle (Rahmengestell 23.10.2026): beide Quadratrohr, kein Verbundkern
- J1 STEP-JSON 1.12: Abwicklung, Umriss, Wände im Ergebnis
- E1 Blech-Editor aus der Messung (blech.aus_step): Winkel/Z als Kantteil mit Schenkeln und Bohrungen an ihrer
  Stelle, U mit Ausklinkungen mit Polygon-Außenkontur, Schale als Zuschnitt mit 4 Kantungen und Biegelinien; der
  Schneidweg des Editors ist der Schneidweg der STEP-Abwicklung; 3D-Ansicht gefaltet in den Außenmaßen
- R1 Rohr-Editor aus der Messung (step.rechner_eingaben): Sonderkontur mit Umriss und Wänden, Mitte über der Ecke
  richtig platziert, Gravur-Zeilen mit Tiefe (Summe = gemessene Gravur), komplexes Ende mit Umriss; Schneidweg und
  Gravur im Rechner wie gemessen

Teile werden mit OpenCascade erzeugt (tests/erzeuge_testteile.py) und mit step_messung gemessen.
Aufruf: python tests/test_step_kantteile.py
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER))

from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_ergebnis  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.05):
    return a is not None and abs(a - b) <= tol


def box(x, y, z, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def fuse(*s):
    a = s[0]
    for b in s[1:]:
        a = BRepAlgoAPI_Fuse(a, b).Shape()
    return a


tmp = Path(os.environ.get("TESTTMP") or tempfile.mkdtemp())
# Kantteile
w = et.profil([(0, 0), (100, 0), (100, 3), (3, 3), (3, 50), (0, 50)], 300, {(0, 0): 6, (3, 3): 3})
for z in (50, 250):
    for x in (30, 80):
        w = et.cut(w, et.zylinder((x, -1, z), (0, 1, 0), 9, 5))
    w = et.cut(w, et.zylinder((-1, 30, z), (1, 0, 0), 9, 5))
et.schreibe(w, "K1_Winkel", tmp)
et.schreibe(et.profil([(0, 0), (100, 0), (100, 3), (3, 3), (3, 50), (0, 50)], 300), "K2_Winkel_scharf", tmp)
et.schreibe(et.profil([(0, 0), (40, 0), (40, 2), (2, 2), (2, 60), (-38, 60), (-38, 58), (0, 58)], 400,
                      {(0, 0): 4, (2, 2): 2, (0, 58): 2, (2, 60): 4}), "K3_Z", tmp)
et.schreibe(et.profil([(0, 0), (22, 0), (22, 28), (68, 28), (68, 0), (90, 0), (90, 2), (70, 2), (70, 30), (20, 30),
                       (20, 2), (0, 2)], 500), "K4_Hut", tmp)
u = et.profil([(0, 0), (100, 0), (100, 30), (97, 30), (97, 3), (3, 3), (3, 30), (0, 30)], 600,
              {(0, 0): 6, (3, 3): 3, (100, 0): 6, (97, 3): 3})
u = et.cut(et.cut(et.cut(u, box(-1, 10, -1, 5, 25, 41)), box(96, 10, -1, 5, 25, 41)), box(30, -1, 250, 40, 5, 100))
et.schreibe(u, "K5_U_Ausklinkung", tmp)
et.schreibe(fuse(box(0, 0, 0, 200, 150, 2), box(0, 0, 0, 200, 2, 20), box(0, 148, 0, 200, 2, 20),
                 box(0, 2, 0, 2, 146, 20), box(198, 2, 0, 2, 146, 20)), "K6_Schale", tmp)
et.schreibe(et.drehe_beliebig(w), "K7_Winkel_gedreht", tmp)
et.schreibe(fuse(box(0, 0, 0, 100, 3, 300), box(48.5, 3, 0, 3, 50, 300)), "K8_T_Stoss", tmp)
# Sonderkonturen und Gravuren
r = et.kastenrohr(60, 40, 3, 1000, 4.5)
et.schreibe(et.cut(r, box(15, 5, 300, 20, 20, 40)), "S1_Ecke", tmp)
et.schreibe(et.cut(r, box(-35, -5, 500, 70, 30, 50)), "S2_drei_Waende", tmp)
et.schreibe(et.cut(r, box(10, 0, -1, 25, 25, 61)), "S3_Ausklinkung_Ende", tmp)
et.schreibe(et.cut(r, et.zylinder((0, -30, 600), (0, 1, 0), 12, 60)), "S4_Bohrung_durch", tmp)
g = r
for i in range(3):
    g = et.cut(g, box(-20 + i * 8, 19.8, 400, 4, 1, 30))
et.schreibe(et.cut(g, et.zylinder((10, 19.8, 415), (0, 1, 0), 10, 1)), "G1_Praegung", tmp)
et.schreibe(et.cut(et.rundrohr(42.4, 2, 800), box(-3, 21.0, 300, 6, 2, 40)), "G2_Praegung_RR", tmp)
# gekreuzte Streben: zwei Quadratrohre 30 × 3, je um ±40° in der XZ-Ebene gedreht, Mitte bei 0
streben = []
for wk in (40, -40):
    s_ = et.verschiebe(et.kastenrohr(30, 30, 3, 900, 3), 0, 0, -450)
    tr = gp_Trsf()
    tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), math.radians(wk))
    streben.append(BRepBuilderAPI_Transform(s_, tr, True).Shape())
et.schreibe(et.baugruppe(*streben), "V1_Kreuz", tmp)


def messen(name):
    return analysiere_datei(tmp / f"{name}.step")


def abw(t):
    return (t.blech or {}).get("abwicklung") or {}


(t,) = messen("K1_Winkel")
a = abw(t)
assert t.profilform == "Blech gekantet" and a["kantungen"] == 1 and not a["mehrachsig"], (t.profilform, a)
assert [(x["laenge"], x["winkel"], x["radius"]) for x in a["schenkel"]] == [(100.0, -90.0, 3.0), (50.0, 0.0, None)], \
    a["schenkel"]
assert nah(a["kantlaenge"], 300) and nah(a["breite"], 144.27, 0.02), (a["kantlaenge"], a["breite"])
lage = t.blech["konturen_lage"]
assert len(lage) == 6 and all(k["art"] == "Bohrung" and nah(k["durchmesser"], 9) for k in lage), lage
assert sorted({round(k["x"]) for k in lage}) == [50, 250], lage
assert nah(t.schneidweg, 2 * (300 + 144.27) + 6 * math.pi * 9, 0.2) and t.konturen == 7, t.schneidweg
ok("K1 Winkel mit Radius: Schenkel 100/50 −90° r 3, Zuschnitt 300 × 144,27, 6 Bohrungen mit Lage, Schneidweg")
(t,) = messen("K2_Winkel_scharf")
assert t.profilform == "L-Profil" and t.alternative is not None and t.alternative.profilform == "Blech gekantet"
a = abw(t.alternative)
assert [(x["laenge"], x["radius"]) for x in a["schenkel"]] == [(100.0, None), (50.0, None)] and a["scharf"], a
assert any("Innenradius 3 mm" in h for h in t.alternative.hinweise), t.alternative.hinweise
ok("K2 Winkel scharfkantig: L-Profil mit Kantteil als Alternative, Innenradius = Blechdicke angenommen")
(t,) = messen("K3_Z")
a = abw(t)
assert [(x["laenge"], x["winkel"]) for x in a["schenkel"]] == [(40.0, 90.0), (60.0, -90.0), (40.0, 0.0)], a
assert nah(a["breite"], 140 - 2 * (2 * 4 - math.pi / 2 * (2 + 0.33 * 2)), 0.02), a["breite"]
ok("K3 Z-Kantteil: Schenkel 40/60/40, +90°/−90°, Abwicklung = Σ Außenmaße − 2 × Ausgleich")
(t,) = messen("K4_Hut")
a = abw(t)
assert t.profilform == "Blech gekantet" and [x["laenge"] for x in a["schenkel"]] == [22, 30, 50, 30, 22], \
    (t.profilform, a.get("schenkel"))
ok("K4 Hutprofil scharfkantig: Kantteil mit 5 Schenkeln statt offenes Sonderprofil")
(t,) = messen("K5_U_Ausklinkung")
k = t if t.profilform == "Blech gekantet" else t.alternative
a = abw(k)
assert [x["laenge"] for x in a["schenkel"]] == [30, 100, 30] and len(k.blech["aussen_punkte"]) == 8, a
(r_,) = k.blech["konturen_lage"]
assert r_["art"] == "Rechteck" and {round(r_["laenge"]), round(r_["breite"])} == {40, 100}, r_
ok("K5 U mit Ausklinkungen: freie Außenkontur (8 Ecken) und Rechteckausschnitt in der Abwicklung")
(t,) = messen("K6_Schale")
a = abw(t)
assert t.profilform == "Blech gekantet" and a["mehrachsig"] and a["kantungen"] == 4 and a["schenkel"] is None, a
assert nah(a["laenge"], 232.36, 0.02) and nah(a["breite"], 182.36, 0.02) and len(t.blech["aussen_punkte"]) == 12
ok("K6 Schale: mehrachsig gekantet, 4 Kantungen, Zuschnitt 232,36 × 182,36 mit freien Ecken")
(t,) = messen("K7_Winkel_gedreht")
a = abw(t)
assert [(x["laenge"], x["winkel"]) for x in a["schenkel"]] == [(100.0, -90.0), (50.0, 0.0)] and \
    len(t.blech["konturen_lage"]) == 6, a
ok("K7 Winkel gedreht: gleiche Abwicklung")
(t,) = messen("K8_T_Stoss")
assert t.profilform != "Blech gekantet" and (t.alternative is None or t.alternative.profilform != "Blech gekantet"), \
    t.profilform
ok("K8 T-Stoß ist kein Kantteil")


def konturen(t):
    return [d for d in t.konturen_liste if d["art"] not in ("Ende A", "Ende B")]


(t,) = messen("S1_Ecke")
(d,) = konturen(t)
assert d["art"] == "Sonderkontur" and sorted(d["waende"]) == ["0°", "270°"] and nah(d["schnittlaenge"], 136.1, 0.2), d
assert len(d["umriss"]) >= 4 and t.pruefstatus == "plausibel", (d, t.pruefstatus)
ok("S1 Ausschnitt über die Ecke: Sonderkontur, Wände 0°/270°, Umriss, Schnittlänge 136,1")
(t,) = messen("S2_drei_Waende")
(d,) = konturen(t)
assert d["art"] == "Sonderkontur" and sorted(d["waende"]) == ["0°", "270°", "90°"] and \
    nah(d["schnittlaenge"], 312.3, 0.2), d
us = [u for u, _ in d["umriss"]]
assert nah(min(us), -53.07, 0.1) and nah(max(us), 53.07, 0.1), d["umriss"]
ok("S2 Ausschnitt über drei Wände: Sonderkontur, Umriss symmetrisch um 0°")
(t,) = messen("S3_Ausklinkung_Ende")
ea = t.konturen_liste[0]
assert ea["art"] == "Ende A" and ea["form"] == "komplex" and len(ea["umriss"]) >= 6, ea
ok("S3 Ausklinkung am Ende: Ende komplex mit Umriss")
(t,) = messen("S4_Bohrung_durch")
bo = konturen(t)
assert [d["art"] for d in bo] == ["Bohrung", "Bohrung"] and all(len(d["waende"]) == 1 for d in bo), bo
ok("S4 Bohrung durch beide Wände: zwei Bohrungen je auf einer Wand")
(t,) = messen("G1_Praegung")
gr = konturen(t)
assert all(d["art"] == "Gravur" and nah(d["tiefe"], 0.2) for d in gr) and len(gr) == 4, gr
assert any(nah(d.get("durchmesser"), 10) for d in gr) and t.pruefstatus == "plausibel" and t.innen == 0, \
    (t.pruefstatus, t.hinweise)
ok("G1 Prägung 0,2 mm: 4 Gravuren mit Tiefe (runde Ø10 keine Sackbohrung), plausibel, nicht im Schneidweg")
(t,) = messen("G2_Praegung_RR")
(d,) = konturen(t)
assert d["art"] == "Gravur" and nah(d["tiefe"], 0.2) and nah(sum(u for u, _ in d["umriss"]) / len(d["umriss"]), 0, 0.1)
ok("G2 Prägung im Rundrohr: Gravur mit Tiefe 0,2, Umriss um 0°")
teile = messen("V1_Kreuz")
assert [x.profilform for x in teile] == ["Quadratrohr", "Quadratrohr"] and not any(x.verbund for x in teile), \
    [(x.profilform, x.verbund) for x in teile]
ok("V1 gekreuzte Streben gleicher Hülle: beide Quadratrohr, kein Verbundkern")
j = step_ergebnis.koerper(messen("K1_Winkel")[0])
assert step_ergebnis.SCHEMA_VERSION == "1.12" and j["blech"]["abwicklung"]["schenkel"][0]["laenge"] == 100
j = step_ergebnis.koerper(messen("S1_Ecke")[0])
assert j["konturen"][0]["umriss"] and j["konturen"][0]["waende"]
json.dumps(j)
ok("J1 STEP-JSON 1.12: Abwicklung, Umriss und Wände im Ergebnis")
from rohrlaser import blech, blech3d  # noqa: E402
for name, art, n_kant in (("K1_Winkel", blech.KANTTEIL, 1), ("K3_Z", blech.KANTTEIL, 2),
                          ("K5_U_Ausklinkung", blech.KANTTEIL, 2), ("K6_Schale", blech.ZUSCHNITT, 4)):
    (t,) = messen(name)
    k = t if t.profilform == "Blech gekantet" else t.alternative
    b = json.loads(json.dumps(k.blech))         # wie aus der Messwert-Datei
    e = blech.aus_step(b, "S235JR")
    zs = blech.zuschnitt(e)
    sw_editor = zs["aussen"] + sum(blech.sw.kontur(z)[0] * z["anzahl"] for z in e["konturen"])
    assert e["art"] == art and blech.kantungen(e, zs) == n_kant, (name, e)
    assert nah(sw_editor, b["umfang_aussen"] + b["umfang_innen"], 0.5), (name, sw_editor, b["umfang_aussen"])
    netz = blech3d.netz(dict(e, dicke=b["dicke"]), zs)
    p = netz["p"]
    ausdehnung = sorted(max(p[i::3]) - min(p[i::3]) for i in range(3))
    soll = sorted((b["laenge"], b["breite"], b["hoehe"]))
    assert all(abs(x - y) <= b["dicke"] + 0.5 for x, y in zip(ausdehnung, soll)), (name, ausdehnung, soll)
    if name == "K1_Winkel":
        assert [x["laenge"] for x in e["schenkel"]] == [100, 50] and e["kantlaenge"] == 300
        assert len(e["konturen"]) == 6 and all(z["x"] is not None for z in e["konturen"])
    if name == "K5_U_Ausklinkung":
        assert e["form"] == blech.POLYGON and not zs["hinweise"], zs["hinweise"]
    if name == "K6_Schale":
        assert e["form"] == blech.POLYGON and len(e["biegelinien"]) == 4
ok("E1 Blech-Editor aus der Messung: Kantteil/Schale, Schneidweg wie STEP, 3D gefaltet in den Außenmaßen")
import step_messen  # noqa: E402
from rohrlaser import schneidweg as sw, skizze as sk, step  # noqa: E402
step_messen.main(["--ausgabe", str(tmp / "r1.csv")] + [str(tmp / f"{n}.step") for n in
                                                        ("S1_Ecke", "S2_drei_Waende", "S3_Ausklinkung_Ende",
                                                         "G1_Praegung", "G2_Praegung_RR")])
for m in step.lies_messwerte(tmp / "r1.csv"):
    name = Path(m["datei"]).stem
    a_, b_ = float(m["abm_a"]), float(m["abm_b"] or 0) or None
    profil = dict(form=m["profilform"], a=a_, b=b_, wand=float(m["wandstaerke"]), profil_id="X")
    e = step.rechner_eingaben(m, m["profilform"], a_, b_)
    erg = sw.rechnen(e, profil, (10, 50))
    assert not erg["fehler"] and nah(erg["schneidweg"], float(m["schneidweg"]), 0.15), (name, erg["fehler"])
    assert nah(erg["felder"]["gravur"] or 0, float(m["gravur"] or 0), 0.15), (name, erg["felder"]["gravur"])
    qs = sk.Querschnitt(profil)
    if name.startswith("S"):
        sonder = [k for k in e["konturen"] if k["art"] == sw.SONDERKONTUR]
        if name == "S3_Ausklinkung_Ende":
            assert e["a"].get("umriss") or e["b"].get("umriss"), e
            continue
        (k,) = sonder
        assert len(k["umriss"]) >= 4 and len(k["waende"]) == (2 if name == "S1_Ecke" else 3)
        d = sk.lagen([k], float(m["laenge"]))[0]
        n = {(round(x[0]), round(x[1])) for x in sk.normalen(qs, d)}
        assert len(n) >= len(k["waende"]), (name, n)
    else:
        gr = [k for k in e["konturen"] if k["art"] == sw.GRAVUR]
        assert gr and all(k["tiefe"] == 0.2 and k.get("umriss") for k in gr), gr
ok("R1 Rohr-Editor aus der Messung: Sonderkontur mit Umriss über die Wände, Gravur-Zeilen, komplexes Ende, "
   "Schneidweg und Gravur wie gemessen")
print("Alle Kantteil-, Sonderkontur- und Gravur-Tests bestanden.")
