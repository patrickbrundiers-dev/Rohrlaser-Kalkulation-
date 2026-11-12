"""3D-Gegenprobe schon vor dem Prüfdialog und schnellere Übergabe an die Editoren (Patrick 12.11.2026: „STEP-Import
und Übergabe an den Editor überprüfen, schneller machen, Erkennung verbessern“, „Konturen und Darstellung oft falsch
bei komplizierten Teilen“, „den Rohr-Import genauso umbauen“).

- F1 Faltung mehrachsig gekanteter Teile (blech3d.falten): eine Lasche an einer kurzen Biegelinie hängt an der Fläche
  hinter einer anderen Biegung und geht mit ihr mit (vorher blieb sie in der Ebene der Grundfläche liegen)
- F2 Biegelinien auf einer Geraden (durch Schlitze unterbrochen) falten einen Punkt nur einmal
- F3 der STEP-Export bekommt dieselben Angaben (Freischnitt, Vorgänger, Tiefe, Linie)
- G1 Kennwerte der Gegenprobe (Fläche, Trägheitsradien) exakt aus den Dreiecken: gedreht und verschoben gleich
- G2 anders gefaltet (60° statt 90°) fällt auf, kleine Abweichung nicht
- S1 schnellere Suche der Gegenprobe Rohr (step_gegenprobe._Raster): gleiche Abstände wie die Suche über alle Strecken
- S2 Lageabgleich (lage_abgleich._Raster) mit grobem Raster für ferne Punkte: gleiche Abstände
- S3 Anbauteil-Auswertung (step_geometrie._max_abstand_zug): gleicher Wert wie über alle Punkte
- K1 Kantteil aus der STEP, das gefaltet zur STEP passt: nicht mehr gelb (Prüfstatus plausibel), Hinweis
  „Abwicklung mit 3D-Gegenprobe bestätigt“; mit weiterem Hinweis (scharfkantig) bleibt es gelb
- K2 Kantteil, dessen Abwicklung nicht zur STEP passt: bleibt gelb, Abweichung im Hinweis
- R1 Rohr: Gegenprobe vor dem Prüfdialog, Ergebnis gemerkt (beim Übernehmen nicht noch einmal gerechnet)
- R2 Rohr, nur wegen eines Anbauteils aus einem eigenen Körper gelb: nach bestandener Gegenprobe grün
- R3 Rohr, dessen Editor-Modell abweicht: gelb mit Abweichung im Hinweis

Aufruf: python tests/test_step_gegenprobe_vorab.py
"""
import copy
import json
import math
import random
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

HIER = Path(__file__).resolve().parent
PROGRAMM = HIER.parent / "programm"
sys.path.insert(0, str(PROGRAMM))
sys.path.insert(0, str(PROGRAMM / "step_messung"))
sys.path.insert(0, str(HIER))

from rohrlaser import blech, blech3d, lage_abgleich as la, step, step_export as se, step_gegenprobe as sg  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ------------------------------------------------------------------ F1 Lasche hinter einer anderen Biegung
# Grundfläche 200 × 100, Rand A (y 100…150) um die Linie y = 100 hoch, daran eine Lasche (x 200…240) um x = 205
lasche = dict(art=blech.ZUSCHNITT, form=blech.POLYGON, dicke=2, konturen=[],
              punkte="0,0; 200,0; 200,110; 240,110; 240,150; 0,150",
              biegelinien=[dict(punkte=[[0, 100], [200, 100]], winkel=90, ba=3, radius=1),
                           dict(punkte=[[205, 110], [205, 150]], winkel=90, ba=3, radius=1)])
zs = blech.zuschnitt(lasche)
bg = blech3d.biegungen(lasche, zs, blech3d.aussenkontur(lasche, zs))
rand, la_ = bg
assert rand["tiefe"] == 0 and la_["vor"] == [rand] and la_["tiefe"] == 1, [(b["tiefe"], len(b["vor"])) for b in bg]
(grund, _), (auf_rand, n_rand), (auf_lasche, n_lasche) = (blech3d.falten(q, bg) for q in ((100, 50), (190, 130),
                                                                                         (230, 130)))
assert nah(grund[2], 0) and auf_rand[2] > 25, (grund, auf_rand)
assert nah(auf_lasche[2], auf_rand[2], 3), (auf_lasche, auf_rand)       # die Lasche steht auf der Höhe des Rands …
assert abs(sum(a * b for a, b in zip(n_rand, n_lasche))) < 1e-6           # … und rechtwinklig zu ihm
# die Abwicklung ist längentreu: der Weg über die Biegung ist höchstens so lang wie in der Ebene
assert math.dist(auf_lasche, auf_rand) <= 40 + 1e-6
ok("F1 Lasche an einer kurzen Biegelinie geht mit der Biegung davor mit (Vorgänger, Tiefe)")

# ------------------------------------------------------------------ F2 Biegelinien auf einer Geraden
schlitz = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=400, breite=200, konturen=[],
               biegelinien=[dict(punkte=[[0, 150], [180, 150]], winkel=45, ba=10, radius=8),
                            dict(punkte=[[220, 150], [400, 150]], winkel=45, ba=10, radius=8)])
zs2 = blech.zuschnitt(schlitz)
bg2 = blech3d.biegungen(schlitz, zs2, blech3d.aussenkontur(schlitz, zs2))
assert bg2[0]["linie"] == bg2[1]["linie"] and all(b["tiefe"] == 0 for b in bg2)
mitte, nm = blech3d.falten((200, 190), bg2)       # zwischen den Linien, im Freischnitt beider
links, nl = blech3d.falten((100, 190), bg2)
assert nah(mitte[2], links[2]) and nah(nm[2], math.cos(math.radians(45)), 1e-9), (mitte, links, nm)
ok("F2 Biegelinien auf einer Geraden falten einen Punkt nur einmal (45°, nicht 90°)")

# ------------------------------------------------------------------ F3 Bauplan des STEP-Exports
plan = se.blech_teil(lasche, zs, "Lasche")["koerper"]["biegungen"]
assert [b["tiefe"] for b in plan] == [0, 1] and plan[1]["vor"] == [0] and plan[0]["vor"] == [] \
    and all(b["frei"] > 0 and len(b["linie"]) == 3 for b in plan), plan
kant = dict(art=blech.KANTTEIL, form=blech.RECHTECK, dicke=2, kantlaenge=300, konturen=[],
            schenkel=[dict(laenge=40, winkel=90), dict(laenge=60, winkel=90), dict(laenge=40)])
assert all("tiefe" not in b for b in se.blech_teil(kant, blech.zuschnitt(kant), "U")["koerper"]["biegungen"])
ok("F3 STEP-Export: Freischnitt, Vorgänger, Tiefe und Linie im Bauplan, Kantteil (Schenkel) unverändert")

# ------------------------------------------------------------------ G1/G2 Kennwerte der Gegenprobe
netz_u = blech3d.netz(kant, blech.zuschnitt(kant))
fl, radien = blech3d.kennwerte(netz_u)
w = math.radians(37)
gedreht = dict(netz_u, p=[c for i in range(0, len(netz_u["p"]), 3) for c in (
    netz_u["p"][i] * math.cos(w) - netz_u["p"][i + 1] * math.sin(w) + 500,
    netz_u["p"][i] * math.sin(w) + netz_u["p"][i + 1] * math.cos(w) - 80, netz_u["p"][i + 2] + 7)])
g = blech3d.gegenprobe(gedreht, netz_u)
assert g[0] < 1e-6 and nah(g[2], 1, 1e-9) and blech3d.gegenprobe_passt(g), g
quader = dict(p=[c for x in (0, 30) for y in (0, 20) for z in (0, 10) for c in (x, y, z)],
              t={"A": [0, 1, 3, 0, 3, 2, 4, 6, 7, 4, 7, 5, 0, 4, 5, 0, 5, 1, 2, 3, 7, 2, 7, 6, 0, 2, 6, 0, 6, 4,
                       1, 5, 7, 1, 7, 3]})
fq, rq = blech3d.kennwerte(quader)
assert nah(fq, 2 * (30 * 20 + 30 * 10 + 20 * 10)) and rq[0] > rq[1] > rq[2] > 0
assert blech3d.kennwerte(dict(p=[], t={})) is None and blech3d.gegenprobe(None, netz_u) is None
ok(f"G1 Kennwerte exakt aus den Dreiecken: U {fl:.0f} mm², Radien {radien[0]:.1f}/{radien[1]:.1f}/{radien[2]:.1f} mm, "
   "gedreht und verschoben gleich")
schief = dict(kant, schenkel=[dict(laenge=40, winkel=60), dict(laenge=60, winkel=90), dict(laenge=40)])
g2 = blech3d.gegenprobe(blech3d.netz(schief, blech.zuschnitt(schief)), netz_u)
assert not blech3d.gegenprobe_passt(g2) and g2[0] > g2[1], g2
knapp = dict(kant, schenkel=[dict(laenge=40.5, winkel=90), dict(laenge=60, winkel=90), dict(laenge=40)])
assert blech3d.gegenprobe_passt(blech3d.gegenprobe(blech3d.netz(knapp, blech.zuschnitt(knapp)), netz_u))
assert not blech3d.gegenprobe_passt(None)
ok(f"G2 60° statt 90° gekantet: {g2[0]:.1f} mm über der Grenze {g2[1]:.1f} mm; 0,5 mm längerer Schenkel passt")

# ------------------------------------------------------------------ S1 Raster der Gegenprobe Rohr
zufall = random.Random(3)
strecken = []
for _ in range(300):
    a = tuple(zufall.uniform(0, 300) for _ in range(3))
    lg = zufall.choice((0.0, 0.5, 5, 40, 600))
    strecken.append((a, tuple(a[i] + zufall.uniform(-1, 1) * lg for i in range(3))))
raster = sg._Raster(strecken, sg.WEITE)
for _ in range(3000):
    q = tuple(zufall.uniform(-5, 305) for _ in range(3))
    if zufall.random() < 0.5:           # nah an einer Strecke
        a, b = zufall.choice(strecken)
        f = zufall.random()
        q = tuple(a[i] + f * (b[i] - a[i]) + zufall.uniform(-2, 2) for i in range(3))
    soll = min(min(sg._abst(q, a, b) for a, b in strecken), sg.WEITE)
    assert nah(min(raster.abstand(q), sg.WEITE), soll, 1e-9), (q, raster.abstand(q), soll)
ok("S1 Gegenprobe Rohr: Raster mit Bereich je Strecke liefert dieselben Abstände wie die Suche über alle Strecken")

# ------------------------------------------------------------------ S2 Lageabgleich mit grobem Raster
punkte = [tuple(zufall.uniform(0, 80) for _ in range(3)) for _ in range(1500)]
r2 = la._Raster(punkte)
for _ in range(2000):
    q = tuple(zufall.uniform(-30, 110) for _ in range(3))
    soll = min(min(math.dist(q, x) for x in punkte), la.KAPPE)
    assert nah(r2.abstand(q), soll, 1e-9), (q, r2.abstand(q), soll)
ok("S2 Lageabgleich: grobes Raster für ferne Punkte, gleiche Abstände")

if find_spec("OCP") is None:
    print("OCP fehlt: S3, K1, K2, R1–R3 übersprungen")
    sys.exit(0)

# ------------------------------------------------------------------ S3 größter Abstand zum Linienzug
import step_geometrie as geo  # noqa: E402

zug = [(math.cos(i / 40 * 2 * math.pi) * 50, math.sin(i / 40 * 2 * math.pi) * 30,
        math.cos((i + 1) / 40 * 2 * math.pi) * 50, math.sin((i + 1) / 40 * 2 * math.pi) * 30) for i in range(40)]
for n in (0, 1, 7, 400):
    pk = [(zufall.uniform(-120, 120), zufall.uniform(-90, 90)) for _ in range(n)]
    soll = max((geo._abstand_zug(x, y, zug) for x, y in pk), default=0.0)
    assert geo._max_abstand_zug(pk, zug) == soll, (n, geo._max_abstand_zug(pk, zug), soll)
assert geo._max_abstand_zug([(1, 1)], []) == 0.0
ok("S3 Anbauteil-Höhe: größter Abstand mit Schranke, gleicher Wert wie über alle Punkte")

# ------------------------------------------------------------------ K1/K2 Kantteile aus der STEP
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def box(x, y, z, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def fuse(*s):
    a = s[0]
    for b in s[1:]:
        a = BRepAlgoAPI_Fuse(a, b).Shape()
    return a


tmp = Path(tempfile.mkdtemp())
et.schreibe(et.profil([(0, 0), (40, 0), (40, 2), (2, 2), (2, 60), (-38, 60), (-38, 58), (0, 58)], 400,
                      {(0, 0): 4, (2, 2): 2, (2, 60): 4, (0, 58): 2}), "K3_Z", tmp)
et.schreibe(fuse(box(0, 0, 0, 200, 150, 2), box(0, 0, 0, 200, 2, 20), box(0, 148, 0, 200, 2, 20),
                 box(0, 2, 0, 2, 146, 20), box(198, 2, 0, 2, 146, 20)), "K6_Schale", tmp)
(tmp / "netze").mkdir()
step_messen.main(["--ausgabe", str(tmp / "m.txt"), "--netze", str(tmp / "netze"), str(tmp / "K3_Z.step"),
                  str(tmp / "K6_Schale.step"), str(HIER / "step_konturen" / "K04_RE60x40x3_Senkung_Flowdrill.step")])
mw = step.lade_netze(step.lies_messwerte(tmp / "m.txt"), tmp / "netze")
z_teil, schale, rohr = mw
assert z_teil["profilform"] == schale["profilform"] == "Blech gekantet" and rohr["profilform"] == "Rechteckrohr", \
    [m["profilform"] for m in mw]
assert z_teil["pruefstatus"] == "prüfen" and step.KANT_HINWEIS in z_teil["hinweise"]
falsch = copy.deepcopy(z_teil)
b = json.loads(falsch["blech"])
b["abwicklung"]["schenkel"][0]["winkel"] = -b["abwicklung"]["schenkel"][0]["winkel"]      # Z als U gefaltet
falsch["blech"] = json.dumps(b)
n = step.kantteile_gegenprobe([z_teil, schale, falsch])
assert z_teil["pruefstatus"] == "plausibel" and step.KANT_GEPRUEFT in z_teil["hinweise"] \
    and "3D-Gegenprobe: gefaltet wie in der STEP" in z_teil["hinweise"] and step.ampel(z_teil)[0] == "gruen", z_teil["hinweise"]
assert schale["_kant_gegenprobe"][0] is True, schale["_kant_gegenprobe"]
assert n == (2 if schale["pruefstatus"] == "plausibel" else 1)
if schale["pruefstatus"] == "prüfen":      # scharfkantig gezeichnet: der Hinweis der Messung bleibt zu prüfen
    assert "scharfkantig" in schale["hinweise"]
hinweis = z_teil["hinweise"]
assert step.kantteile_gegenprobe([z_teil]) == 0 and z_teil["hinweise"] == hinweis       # nur einmal je Teil
ok("K1 Kantteil passt gefaltet zur STEP: Prüfstatus plausibel, Ampel grün, Hinweis „mit 3D-Gegenprobe bestätigt“")
assert falsch["pruefstatus"] == "prüfen" and falsch["_kant_gegenprobe"][0] is False \
    and "anders gefaltet" in falsch["hinweise"] and step.KANT_HINWEIS in falsch["hinweise"], falsch["hinweise"]
ok("K2 Abwicklung passt nicht zur STEP: bleibt gelb, " + falsch["_kant_gegenprobe"][1])

# ------------------------------------------------------------------ R1–R3 Rohr
db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
anbau = copy.deepcopy(rohr)
anbau.update(pruefstatus="prüfen", sicherheit=";".join(filter(None, [rohr.get("sicherheit"), "anbauteile=unsicher"])),
             hinweise="; ".join(filter(None, [rohr.get("hinweise"),
                                             "Anbauteil 1 (Sonstiges) bei z = 100.0 mm nicht sicher erkannt, prüfen"])))
verschoben = copy.deepcopy(rohr)
kl = json.loads(verschoben["konturen_liste"])
for x in kl:
    if isinstance(x.get("z"), (int, float)):
        x["z"] += 5.0
verschoben["konturen_liste"] = json.dumps(kl)
assert rohr["pruefstatus"] == "plausibel" and step.ampel(anbau)[0] == "gelb"
sg._MERKER.clear()
assert step.rohre_gegenprobe([rohr, anbau, verschoben, z_teil], k.profile) == 1
assert rohr["_rohr_gegenprobe"][0] is True and rohr["_rohr_gegenprobe"][2] <= sg.GRENZE \
    and step.ROHR_GEPRUEFT in rohr["hinweise"] and step.ampel(rohr)[0] == "gruen", rohr["hinweise"]
assert "_rohr_gegenprobe" not in z_teil                    # Bleche und Kantteile: kantteile_gegenprobe
assert len(sg._MERKER) == 2, len(sg._MERKER)                # rohr und anbau: einmal gerechnet, einmal gemerkt
ok(f"R1 Rohr vor dem Prüfdialog: Editor liegt wie die STEP ({rohr['_rohr_gegenprobe'][2]:.2f} mm), Ergebnis gemerkt")
assert anbau["pruefstatus"] == "plausibel" and anbau["_rohr_bestaetigt"] and step.ampel(anbau)[0] == "gruen", \
    step.ampel(anbau)
ok("R2 Rohr nur wegen eines Anbauteils (eigener Körper) gelb: nach bestandener Gegenprobe grün")
assert verschoben["pruefstatus"] == "prüfen" and verschoben["_rohr_gegenprobe"][0] is False \
    and "weicht" in verschoben["hinweise"] and step.ampel(verschoben)[0] == "gelb", verschoben["hinweise"]
ok("R3 Kontur 5 mm verschoben: gelb, " + verschoben["_rohr_gegenprobe"][1][:70])
print("Alle Prüfungen bestanden.")
