"""Stangenabwicklung auf CAD/CAM-Niveau und 3D der echten Teile auf der Stange (Patrick 24.11.2026):

- Lage jedes Teils (von/bis, Drehung) und alle Bereiche (Endbeschnitt, Schnittfugen, Rest, Greiferrest) genau aus dem
  Nesting-Ergebnis, keine eigene Lagerechnung
- Rundrohr, Quadratrohr, Rechteckrohr, zwei Wandstärken: Umfang = echte Außenhaut mit Eckradien, Seiten
- Gehrung, Bohrung, Langloch, Gravur: Kontur auf der Stange = Kontur am Teil + von bzw. + Drehung am Umfang
- gewendete Teile (Ende B vorn): Enden tauschen, Abwicklung gespiegelt
- 3D: Lage je Teil (Ursprung, Achse, Drehung), STEP-Netz nur wenn es zur Teillänge passt, sonst aus den Eingaben;
  Rest/Endbeschnitt als eigene Art
- Oberfläche: Abwicklung, Technisch (Koordinaten), 3D, Stangenliste, Infopanel, Ansicht gemerkt; nach Ziehen neu
- Tempo: 2D je Stange schnell, gleiche Teile einmal gerechnet

Aufruf: python tests/test_nesting_abwicklung.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import abwicklung as aw, nesting_abwicklung as na, rechnen, schneidweg as sw  # noqa: E402
from rohrlaser import skizze as sk, rohr3d  # noqa: E402
from rohrlaser.nesting_abwicklung_bild import AbwicklungAnsicht  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
PROFILE = {"RR": dict(form="Rundrohr", a=42.4, wand=2),
           "QR": dict(form="Quadratrohr", a=40, b=40, wand=3),
           "QR5": dict(form="Quadratrohr", a=40, b=40, wand=5),
           "RE": dict(form="Rechteckrohr", a=60, b=40, wand=3)}


def technik(**k):
    return json.dumps(dict(quelle=sw.QUELLE, a=k.get("a", dict(winkel=0)), b=k.get("b", dict(winkel=0)),
                           konturen=k.get("konturen", [])))


def stange_aus(positionen, je, laenge=6000, end=10.0, fuge=2.0, greif=50.0, drehungen=None):
    """Schnittplan-Stange wie ergebnis['stangen']: Teile hintereinander mit Fuge, je = [(Index, Länge)]."""
    teile, x = [], end
    for n, (i, L) in enumerate(je):
        if n:
            x += fuge
        p = positionen[i]
        teile.append(dict(ref=rechnen.schluessel(p, i), pos=p["pos"], artikel=p["artikel"], laenge=L, von=x,
                          bis=x + L, drehung=(drehungen or {}).get(n, 0), lage=None, index=i, querschnitt=None))
        x += L
    return dict(stange=laenge, end=end, greif=greif, rest="", teile=teile)


BOHR = dict(art=sw.BOHRUNG, anzahl=1, d=12, x=100, seite="oben")
LANG = dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="vorne")
GRAV = dict(art=sw.GRAVUR, anzahl=1, laenge=20, x=50, seite="oben")
pos = [dict(id=1, pos=10, artikel="A", laenge=500, technik=technik(konturen=[BOHR, LANG])),
       dict(id=2, pos=20, artikel="B", laenge=800, technik=technik(a=dict(winkel=45), konturen=[BOHR])),
       dict(id=3, pos=30, artikel="C", laenge=400, technik=technik(konturen=[GRAV])),
       dict(id=4, pos=40, artikel="D", laenge=600, technik=technik(konturen=[BOHR]), gewendet="ja")]

# ------------------------------------------------------------------ Lage aus dem Nesting, alle Profile
for name, prof in PROFILE.items():
    s = stange_aus(pos, [(0, 500), (1, 800), (2, 400), (0, 500)], drehungen={3: 90 if name != "RE" else 180})
    d = na.stange(s, pos, lambda p, prof=prof: prof, {})
    assert d is not None and not d["fehlt"], (name, d and d["fehlt"])
    m = aw.Mantel(sk.Querschnitt(prof))
    assert abs(d["umfang"] - m.umfang) < 1e-9 and abs(sum(t1 - t0 for _, t0, t1 in d["streifen"]) - m.umfang) < 1e-6
    for t, soll in zip(d["teile"], s["teile"]):
        assert (t["von"], t["bis"], t["laenge"], t["drehung"]) == (soll["von"], soll["bis"], soll["laenge"],
                                                                   soll["drehung"]), name
        assert abs(t["dt"] - (soll["drehung"] % 360) / 360 * m.umfang) < 1e-9
        xs = [x for x, _ in t["umriss"]]
        assert min(xs) >= t["von"] - 50 and max(xs) <= t["bis"] + 50, name     # Gehrung bleibt im Teilbereich
    b = d["bereiche"]
    assert b[0] == ("end", 0.0, 10.0) and b[-1][0] == "greif" and b[-1][2] == 6000
    assert all(abs(b[i][2] - b[i + 1][1]) < 1e-9 for i in range(len(b) - 1))           # lückenlos
    k = na.kennzahlen(d, s)
    assert abs(k["teile_mm"] - 2200) < 1e-9 and k["schnitt_mm"] >= 3 * 2.0 - 1e-9 and k["teile"] == 4
    assert abs(k["teile_mm"] + k["schnitt_mm"] + k["end_mm"] + k["rest_mm"] + k["greif_mm"] - 6000) < 1e-6
    if prof["form"] == "Rundrohr":
        assert d["radius"] == 0 or not m.exakt
        assert abs(d["umfang"] - math.pi * 42.4) < 1e-6
    else:
        assert [n for n, _, _ in d["streifen"]] == ["oben", "vorne", "unten", "hinten"]
ok("Lage, Drehung und Bereiche genau aus dem Nesting; Umfang = Außenhaut mit Eckradien (RR, QR 3/5, RE)")

# ------------------------------------------------------------------ Konturen = Teil + Platz auf der Stange
prof = PROFILE["QR"]
qs = sk.Querschnitt(prof)
m = aw.Mantel(qs)
s = stange_aus(pos, [(0, 500), (0, 500)], drehungen={1: 90})
d = na.stange(s, pos, lambda p: prof, {})
form = na.teil_form(qs, sw.aus_position(sw.lesen(pos[0]["technik"]), pos[0], prof)[0], 500, m)
assert len(form["konturen"]) == 2 and len(d["teile"][0]["konturen"]) == 2
for t in d["teile"]:
    for k0, k in zip(form["konturen"], t["konturen"]):
        for (x0, q0), (x, q) in zip(k0["punkte"], k["punkte"]):
            assert abs(x - (x0 + t["von"])) < 1e-9
            assert abs((q - (q0 + t["dt"])) % m.umfang) < 1e-6 or abs((q - (q0 + t["dt"])) % m.umfang - m.umfang) < 1e-6
assert d["teile"][0]["konturen"][0]["seite"] == "oben" and d["teile"][0]["konturen"][1]["seite"] == "vorne"
assert d["teile"][1]["konturen"][0]["seite"] != "oben"        # um 90° gedreht: Bohrung auf einer anderen Seite
assert abs(d["teile"][0]["konturen"][0]["x"] - (10 + 100)) < 0.5      # Bohrung bei x = 100 am Teil
z = na.koordinaten(d)
assert z[0]["art"] == "1. Schnitt (Besäumen)" and z[0]["teil"] == "Stange" and z[0]["x"] == 10   # Besäumschnitt
z = z[1:]
assert [r["art"] for r in z[:4]] == ["Schnitt Anfang", "Kontur", "Kontur", "Schnitt Ende"]
assert z[0]["x"] == 10 and z[3]["x"] == 510
dx = na.dxf_elemente(d)
assert any(e[0] == "TEXT" and str(e[-1]).startswith("1. Schnitt Besäumen") for e in dx)
g = na.stange(stange_aus(pos, [(2, 400)]), pos, lambda p: prof, {})
assert g["teile"][0]["konturen"][0]["gravur"]
gz = na.stange(stange_aus(pos, [(1, 800)]), pos, lambda p: prof, {})
a = gz["teile"][0]["umriss"][: len(gz["teile"][0]["umriss"]) // 2]
assert max(x for x, _ in a) - min(x for x, _ in a) > 30            # Gehrung 45° an QR 40: Schnittkante schräg
ok("Bohrung, Langloch, Gravur, Gehrung: Kontur auf der Stange = Teil + von bzw. + Drehung am Umfang")

# ------------------------------------------------------------------ Verschnitt zwischen den Teilen (2D und 3D)
s2 = stange_aus(pos, [(2, 400), (2, 400)], fuge=2.0)          # gerade Enden: nur die Schnittfuge
d2 = na.stange(s2, pos, lambda p: prof, {})
fugen = [z for z in d2["zwischen"] if z["von_teil"] == 0 and z["bis_teil"] == 1]
assert len(fugen) == 1 and abs(fugen[0]["mm"] - 2.0) < 0.05, fugen
s3 = stange_aus(pos, [(1, 800), (1, 800)], fuge=2.0)          # Gehrung 45° an Ende A: Dreieck dazu
d3 = na.stange(s3, pos, lambda p: prof, {})
g = [z for z in d3["zwischen"] if z["von_teil"] == 0 and z["bis_teil"] == 1][0]
assert g["mm"] > 2.0 + 10, g["mm"]
assert abs(g["flaeche"] - g["mm"] * d3["umfang"]) < 1e-6
k3 = na.kennzahlen(d3, s3)
assert abs(k3["zwischen_mm"] - sum(z["mm"] for z in d3["zwischen"])) < 1e-9
vs = na.zwischen_netz(qs, m, d3["zwischen"])
assert vs and len(vs["t"]["VS"]) % 3 == 0 and vs["t"]["VS"]
zs = vs["p"][2::3]
assert min(zs) >= g["x0"] - 1e-6 or min(zs) >= 0
netz3, _ = na.netz_stange(s3, pos, lambda p: prof, None, {})
assert "VS" in netz3["t"] and netz3["t"]["VS"]
ok("Verschnitt zwischen den Teilen: Fuge 2 mm bei geraden Enden, Gehrung als Dreieck, Kennzahl, 3D-Netz (Art VS)")

# ------------------------------------------------------------------ gewendet
d = na.stange(stange_aus(pos, [(3, 600)]), pos, lambda p: prof, {})
t = d["teile"][0]
assert t["gewendet"] and abs(t["konturen"][0]["x"] - (10 + 600 - 100)) < 0.5
lg = na.lage_auf_stange(10, 0, 600, True)
assert lg[2] == 610 and lg[5] == -1.0
assert na.lage_auf_stange(10, 90, 600)[:6] == [0.0, 0.0, 10.0, 0.0, 0.0, 1.0]
assert abs(na.lage_auf_stange(10, 90)[6]) < 1e-12 and abs(na.lage_auf_stange(10, 90)[7] - 1) < 1e-12
ok("Gewendete Teile: Bohrung von Ende B gemessen, 3D-Lage gedreht")

# ------------------------------------------------------------------ 3D: STEP nur wenn passend
s = stange_aus(pos, [(0, 500), (2, 400)])
e0 = sw.aus_position(sw.lesen(pos[0]["technik"]), pos[0], prof)[0]
richtig = rohr3d.netz(e0, prof, 500)
falsch = rohr3d.netz(e0, prof, 350)
assert na.netz_passt(richtig, 500)[0] and not na.netz_passt(falsch, 500)[0]
netze = {1: richtig, 3: falsch}
netz, info = na.netz_stange(s, pos, lambda p: prof, lambda p: netze.get(p["id"]), {})
assert netz is not None and [x["quelle"] for x in info] == ["STEP", "Eingaben"], info
assert info[1]["hinweis"] and "Eingaben" in info[1]["hinweis"]
zs = netz["p"][2::3]
assert min(zs) > -1e-6 and abs(max(zs) - 6000) < 1e-6
arten = {a for a in netz.get("arten") or ()} if isinstance(netz.get("arten"), (list, tuple)) else set()
assert not arten or "RS" in arten or any(str(a).startswith("RS") for a in arten), arten
ok("3D: STEP-Netz nur bei passender Länge, sonst aus den Eingaben mit Hinweis; Stange 0 … 6000 mm")

# ------------------------------------------------------------------ Tempo und Merker
viele = stange_aus(pos, [(0, 500)] * 11)
merk = {}
t0 = time.perf_counter()
d = na.stange(viele, pos, lambda p: prof, merk)
t1 = time.perf_counter() - t0
assert len(d["teile"]) == 11 and len([k for k in merk if k[0] == "exakt"]) == 1
t0 = time.perf_counter()
na.stange(viele, pos, lambda p: prof, merk)
assert time.perf_counter() - t0 < max(0.2, t1), (t1, time.perf_counter() - t0)
ok(f"Tempo: 11 Teile {t1 * 1000:.0f} ms, gleiche Teile einmal gerechnet")

# ------------------------------------------------------------------ Zeichnung
a = AbwicklungAnsicht()
a.resize(1200, 400)
a.setzen(d, {}, True)
a.show()
app.processEvents()
assert not a.grab().isNull()
for n in ("bemassung", "schnitte", "konturen", "reste", "raster"):
    a.ebene(n, False)
    a.grab()
    a.ebene(n, True)
assert "1. Schnitt (Besäumschnitt) bei x 10" in a.bereich_text("end", 0, 10)
x, q = 10 + 250, d["umfang"] / 2
mm = a.mm_bei(a.pkt(x, q))
assert abs(mm[0] - x) < 1 and abs(mm[1] - q) < 1, mm
a.senkrecht = True
mm = a.mm_bei(a.pkt(x, q))
assert abs(mm[0] - x) < 1 and abs(mm[1] - q) < 1, mm
tech = AbwicklungAnsicht(technisch=True)
tech.resize(1200, 400)
tech.setzen(d, {}, False)
assert not tech.grab().isNull()
ok("Zeichnung waagerecht/senkrecht, Ebenen ein/aus, Bildpunkt <-> mm umkehrbar, technische Ansicht")
# ------------------------------------------------------------------ Moderne Ansichten (Plan M1-M7)
from rohrlaser import dxf, nesting_ansicht_ui as ui  # noqa: E402
from rohrlaser.nesting_abwicklung_bild import ruhig  # noqa: E402
c = ruhig("#4E79A7", 0.55)
assert c.red() > 0x4E and c.blue() > 0xA7 and c.blue() >= c.red()          # heller, Farbton bleibt
el = na.dxf_elemente(d)
assert sum(1 for e in el if e[0] == "LINE" and e[1] == dxf.AUSSEN) >= 11 * 4
assert any(e[0] == "TEXT" and "Stange 6000" in e[4] for e in el)
txt = dxf.schreiben(el, dxf.layer_namen(aw.ROHR_LAYER))
assert "AUSSENKONTUR" in txt and "INNENKONTUR" in txt
b = ui.balken_daten(0, viele, {}, True)
assert b["titel"].startswith("Stange 1 – ") and abs(b["abschnitte"][-1][2] - 6000) < 1e-9
assert [a for a, *_ in b["abschnitte"]].count("teil") == 11
k = ui.InfoKarte("Stange")
k.setzen("Stange 1", [("Profil", "QR 40×40×3"), ("Länge", "6000 mm")], 0.9, "")
k.setzen("Stange 2", [("Profil", "QR 40×40×3")])
assert "Stange 2" in k.text() and "6000" not in k.text() and not k.balken.isVisibleTo(k)
assert "QR 40×40×3" in k.inhalt.text()
a.hover = 0
a.punkt_markiert = (260, 20)
assert not a.grab().isNull() and "Pos. 10" in a.teil_text(0)
ok("Moderne Ansichten: ruhige Farben, DXF der Stange, Belegungsbalken, Infokarten, Zeigen/Markieren")
print("Alle Tests OK")
