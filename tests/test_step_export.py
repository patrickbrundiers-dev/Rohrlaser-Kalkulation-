"""STEP-Export (Plan 3D-Editor 3E-8, Patrick 24.10.2026): im Rohr- und Blech-Editor erstellte Teile als STEP mit
echtem Volumenkörper.
- X1 Bauplan Rohr: Querschnitt mit echtem Außenradius (Bulge), ebenes Ende = Halbraum, Sattel = Netz, Bohrung =
  Zylinder, Langloch auf ebener Wand exakt, Nasen der Steckverbindung bleiben stehen, Gravur als Rille mit 0,5 mm
  Abstand (zu nah am Ende gekürzt), Artikelnummer-Gravur.
- X2 Bauplan Blech: Außenkontur und Innenkonturen mit echten Bögen, Text-Gravur, gekantet = Hinweis.
- X3 STEP schreiben (OpenCascade wie die Messung): gültiger Volumenkörper, Volumen wie gerechnet, Messung der eigenen
  STEP-Datei findet Profil, Länge, Bohrung und Gravur wieder.
- X4 Rohr- und Blech-Editor: Knopf STEP speichern im Reiter Ausgabe schreibt die Datei.

Aufruf: python tests/test_step_export.py
"""
import json
import math
import os
import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path.insert(0, str(PROGRAMM))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import blech, step_export as se, schneidweg as sw  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    return abs(a - b) <= tol


QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3", r_aussen=6)
RR = dict(form="Rundrohr", a=48.3, wand=3)
FL = dict(form="Flachstahl", a=60, wand=8)

# ------------------------------------------------------------------ X1 Bauplan Rohr
gerade = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100),
                                    dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="vorne")])
plan = se.rohr_teil(gerade, QR, 500, "Pos 1")
k = plan["koerper"]
assert k["art"] == "rohr" and k["laenge"] == 500
assert len(k["aussen"]["punkte"]) == 8 and sum(1 for p in k["aussen"]["punkte"] if nah(p[2], se.BULGE_90)) == 4
assert sum(1 for p in k["innen"]["punkte"] if nah(p[2], se.BULGE_90)) == 4         # innen Radius 6 − 3
assert [w["art"] for w in plan["werkzeuge"]] == ["zylinder", "flach"], [w["art"] for w in plan["werkzeuge"]]
zyl, lang = plan["werkzeuge"]
assert nah(zyl["r"], 5) and nah(zyl["h"], 3 + 2 * se.UEBER) and zyl["achse"] == [0.0, -1.0, 0.0]
assert lang["kontur"]["punkte"][1][2] in (1.0, -1.0) and nah(abs(lang["n"][0]), 1)              # Bögen, Wand vorne
assert se.querschnitt(__import__("rohrlaser.skizze", fromlist=["x"]).Querschnitt(RR))[0] == {"kreis": [0.0, 0.0, 24.15]}
gehrung = se.rohr_teil(dict(a=dict(winkel=45, d3=True), b={}, d3=True, konturen=[]), QR, 300)
assert [w["art"] for w in gehrung["werkzeuge"]] == ["ebene"]
n = gehrung["werkzeuge"][0]["n"]
assert n[2] < 0 and nah(abs(n[2]), math.sqrt(0.5), 1e-6)                                   # 45°, weg zu Ende A hin
sattel = se.rohr_teil(dict(a=dict(gegen=dict(d=60.3)), b={}, konturen=[]), RR, 200)
assert [w["art"] for w in sattel["werkzeuge"]] == ["netz"] and len(sattel["werkzeuge"][0]["t"]) % 3 == 0
nasen = se.rohr_teil(dict(a=dict(nasen=dict(id="sv1", laenge_plus=5, bN=12, anzahl=2)), b={}, konturen=[]), QR, 300)
ende_a = nasen["werkzeuge"][0]
assert ende_a["art"] == "ebene" and nah(ende_a["p"][2], 5) and len(ende_a["ohne"]) == 2      # zwei Nasen bleiben
assert all(s["art"] == "prisma" and "ohne" not in s for s in ende_a["ohne"])                 # Spitze am Teilende
text = dict(art=sw.TEXT_GRAVUR, text="AB7", hoehe=8, x=100, seite="oben", q=0, anzahl=1)
g = se.rohr_teil(dict(a={}, b={}, konturen=[text]), QR, 300)
assert g["rillen"] and not g["meldungen"] and all(r["art"] == "quader" and nah(r["b"], se.GRAVUR_BREITE)
                                                   for r in g["rillen"])
tief = min(r["p"][1] for r in g["rillen"] if nah(r["z"][1], 1))
assert nah(tief, 20 - se.GRAVUR_TIEFE, 1e-6), tief                                     # 0,1 mm in die Oberseite
zu_nah = se.rohr_teil(dict(a={}, b={}, konturen=[dict(text, x=2)]), QR, 300)
assert zu_nah["meldungen"] and "gekürzt" in zu_nah["meldungen"][0]
assert all(r["p"][2] >= se.GRAVUR_ABSTAND - 1e-6 for r in zu_nah["rillen"])
art = se.rohr_teil(dict(a={}, b={}, konturen=[]), QR, 300, artikel="4711", gravur_h=10)
assert art["rillen"] and not art["meldungen"]
kurz = se.rohr_teil(dict(a={}, b={}, konturen=[]), QR, 20, artikel="4711-ABCDEF", gravur_h=10)
assert not kurz["rillen"] and "kein Platz" in kurz["meldungen"][0]
flach = se.rohr_teil(dict(a=dict(winkel=30), b={}, konturen=[dict(art=sw.LANGLOCH, l=20, b=8, x=120, anzahl=1)]),
                     FL, 200)
assert flach["koerper"]["innen"] is None and [w["art"] for w in flach["werkzeuge"]] == ["ebene", "flach"]
try:
    se.rohr_teil(dict(a={}, b={}, konturen=[]), QR, 0)
    raise AssertionError("ohne Länge")
except ValueError:
    pass
ok("X1 Bauplan Rohr: Radius als Bogen, Halbraum/Netz an den Enden, Zylinder, Langloch exakt, Nasen, Gravur 0,5 mm")

# ------------------------------------------------------------------ X2 Bauplan Blech
konturen = [dict(art=sw.BOHRUNG, anzahl=1, d=10, x=30, y=50),
            dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=80, y=50),
            dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=110, y=50, quer=True),
            dict(art=sw.RECHTECK, anzahl=1, b=20, h=15, r=2, x=150, y=30, drehung=30),
            dict(art=sw.POLYGON, anzahl=1, punkte="0,0; 20,0,0.5; 10,15", x=170, y=75),
            dict(art=sw.TEXT_GRAVUR, anzahl=1, text="POS 12", hoehe=8, x=60, y=20)]
eb = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100, eckradius=10, konturen=konturen)
bp = se.blech_teil(eb, blech.zuschnitt(eb), "Lasche")
kb = bp["koerper"]
assert kb["art"] == "platte" and kb["dicke"] == 3 and len(kb["loecher"]) == 5
assert sum(1 for p in kb["aussen"]["punkte"] if nah(p[2], se.BULGE_90)) == 4
assert kb["loecher"][0] == {"kreis": [30.0, 50.0, 5.0]}
lq = kb["loecher"][2]["punkte"]                                        # quer: 10 breit, 30 hoch
assert nah(max(p[1] for p in lq) - min(p[1] for p in lq), 20, 1e-6) and nah(max(p[0] for p in lq), 115, 1e-6)
assert any(nah(p[2], 0.5) for p in kb["loecher"][4]["punkte"])          # Bogen im Polygon bleibt Bogen
assert bp["rillen"] and all(nah(r["p"][2], 3 - se.GRAVUR_TIEFE) for r in bp["rillen"])
ep = dict(art=blech.ZUSCHNITT, form=blech.POLYGON, punkte="0,0; 100,0,1; 100,50; 0,50", dicke=2, konturen=[])
assert se.blech_teil(ep, blech.zuschnitt(ep))["koerper"]["aussen"]["punkte"][1][2] == 1.0
kant = dict(art=blech.KANTTEIL, form=blech.RECHTECK, dicke=2, kantlaenge=300,
            schenkel=[dict(laenge=40, winkel=90), dict(laenge=60)])
try:
    se.blech_teil(kant, blech.zuschnitt(kant))
    raise AssertionError("Kantteil")
except ValueError as x:
    assert "Gekantete" in str(x)
ok("X2 Bauplan Blech: Rundungen, Langloch quer, Rechteck gedreht, Polygon mit Bogen, Gravur 0,1 mm, Kantteil nicht")

# ------------------------------------------------------------------ X3 STEP schreiben und nachmessen
if find_spec("OCP") is None:
    print("OCP fehlt: X3/X4 übersprungen")
    sys.exit(0)
tmp = Path(tempfile.mkdtemp())
erg = se.schreiben([plan], tmp / "rohr.step", PROGRAMM)
t = erg["teile"][0]
assert erg["ok"] and t["gueltig"] and t["koerper"] == 1, erg
r, ri = 6.0, 3.0
flaeche = 40 * 40 - (4 - math.pi) * r * r - (34 * 34 - (4 - math.pi) * ri * ri)
soll = flaeche * 500 - math.pi * 25 * 3 - (math.pi * 25 + 20 * 10) * 3
assert abs(t["volumen"] - soll) < 1, (t["volumen"], soll)
for name, p_ in (("nasen", nasen), ("sattel", sattel), ("gravur", g), ("flach", flach), ("gehrung", gehrung)):
    e_ = se.schreiben([p_], tmp / f"{name}.step", PROGRAMM)
    assert e_["ok"] and e_["teile"][0]["koerper"] == 1 and e_["teile"][0]["volumen"] > 0, (name, e_)
eb_ = se.schreiben([bp], tmp / "blech.step", PROGRAMM)
assert eb_["ok"] and eb_["teile"][0]["koerper"] == 1
bsoll = (200 * 100 - (4 - math.pi) * 100) * 3
assert eb_["teile"][0]["volumen"] < bsoll - 4 * 3 * 100 and eb_["teile"][0]["volumen"] > bsoll * 0.8
# eigene Messung liest die Datei wie eine Kunden-STEP
messung = tmp / "m.txt"
subprocess.run([sys.executable, str(PROGRAMM / "step_messung" / "step_messen.py"), "--ausgabe", str(messung),
                str(tmp / "rohr.step"), str(tmp / "gravur.step")], capture_output=True, check=True)
zeilen = messung.read_text(encoding="utf-8").splitlines()
kopf_ = zeilen[0].split("\t")
werte = [dict(zip(kopf_, z.split("\t"))) for z in zeilen[1:]]
m1, m2 = werte
assert m1["profilform"] == "Quadratrohr" and nah(float(m1["abm_a"]), 40, 0.01) and nah(float(m1["laenge"]), 500, 0.01)
assert nah(float(m1["wandstaerke"]), 3, 0.01) and m1["bohrungen"] == "10.0:1" and m1["innen_konturen"] == "2"
assert float(m2["gravur"]) > 20
# dieselbe .exe: STEP-Import.exe --export (hier über step_messen.main wie in der .exe)
bauplan = tmp / "bauplan.json"
bauplan.write_text(json.dumps(dict(teile=[gehrung])), encoding="utf-8")
subprocess.run([sys.executable, str(PROGRAMM / "step_messung" / "step_messen.py"), "--export", str(bauplan),
                "--step", str(tmp / "exe.step"), "--ergebnis", str(tmp / "exe.json")], capture_output=True, check=True)
assert json.loads((tmp / "exe.json").read_text(encoding="utf-8"))["ok"] and (tmp / "exe.step").stat().st_size > 1000
assert "STEP gespeichert" in se.ergebnis_text(erg, tmp / "rohr.step")
ok("X3 STEP: gültiger Körper, Volumen wie gerechnet, Messung findet QR 40×40×3, 500 mm, Bohrung Ø 10 und Gravur")

# ------------------------------------------------------------------ X4 Editoren
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

db = Datenbank(tmp / "rohrlaser.db")
kx = db.kontext()
p = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, artikel="4711", bg_gravur=8,
         technik=json.dumps(dict(gerade, quelle=sw.QUELLE)))
d = SchneidwegDialog(None, p, kx.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), kx, db.tabellen(), db)
d.stumm = True
assert d.editor.band.knopf("STEP speichern") is not None
ziel = d.step_speichern(str(tmp / "editor.step"))
assert ziel and Path(ziel).is_file() and d.step_ergebnis["ok"] and d.step_ergebnis["teile"][0]["name"] == "4711"
bd = BlechDialog(None, db)
bd.stumm = True
assert bd.editor.band.knopf("STEP speichern") is not None
assert bd.step_speichern(str(tmp / "blech_editor.step")) and bd.step_ergebnis["ok"]
bd.art.setCurrentText("Kantteil")
bd._vorlage(bd.vorlage.findText("U-Profil"))
assert bd.step_speichern(str(tmp / "kant.step")) is None and not (tmp / "kant.step").exists()
for w in (d, bd):
    w.close()
db.con.close()
ok("X4 Rohr- und Blech-Editor: STEP speichern im Reiter Ausgabe, Name = Artikelnummer, Kantteil mit Hinweis")
print("Alle Tests STEP-Export bestanden.")
