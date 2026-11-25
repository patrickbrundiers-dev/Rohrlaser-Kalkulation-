"""Rohr-, Kontur- und Fertigungsmessung, Flächenkatalog aus der STEP (Messplan M3, Patrick 19.11.2026
„professionelles 3D-Messsystem“).

T1 STEP-Messung schreibt den Flächenkatalog: je Fläche Art, Fläche, Radius (fk), je Dreieck die Nummer (tf);
   lageunabhängig, Anhängen und Verfeinern halten ihn passend (STEP-JSON 1.30)
T2 Programm: Flächen genau wie in der STEP, Ø/Fläche exakt, Zylinderachsen (Wandstärke radial, Achsabstand);
   unpassender Katalog fällt still weg, Baugruppe nimmt ihn mit
T3 Rohrmessung: Profilform, Breite/Höhe, Ø, Wand, Eckradius, Querschnitt, Masse (Dichte, Volumen) für Quadrat-,
   Rund-, Rechteckrohr und offene Profile
T4 Konturen und Fertigung: Bohrungen mit Ø, Lochabstand, Reststeg gegen Prüfregel „Steg zu schmal“, doppelte Kontur,
   Kanten der STEP zu Konturen verbunden, beide Wandseiten einmal gezählt
T5 Gehrung zur Bezugsebene mit Drehsinn, gerichteter Winkel um die Rohrachse
T6 Fenster „Teil messen“ (Leiste und Rechtsklick), Kopieren, PDF; Netz unverändert

Aufruf: python tests/test_teilmessung_m3.py
"""
import copy
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
import step_ergebnis  # noqa: E402
import step_geometrie as sg  # noqa: E402
import step_offenes_rohr  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402

from rohrlaser import ansicht3d, ansicht3d_leiste, dfm, mess_kern as mk, mess_teil, mess_teil_dialog  # noqa: E402
from rohrlaser import rohr3d, schneidweg as sw  # noqa: E402

ansicht3d.renderer_setzen("Software")
REF = HIER / "step_referenz"
TMP = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-3):
    return a is not None and abs(a - b) <= tol


def step_netz(name):
    return analysiere_datei(str(REF / f"{name}.step"), netz=True)[0].netz


# ------------------------------------------------------------------ T1 Katalog in der STEP-Messung
assert tuple(map(int, step_ergebnis.SCHEMA_VERSION.split("."))) >= (1, 30)     # Flächenkatalog seit 1.30
L16 = step_netz("REF16_L40x40x4_Bohrung")
fk, tf = L16["fk"], L16["tf"]
assert {a: len(v) // 3 for a, v in L16["t"].items()} == {a: len(v) for a, v in tf.items()}
assert all(0 <= n < len(fk) for v in tf.values() for n in v)
zyl = [e for e in fk if e["a"] == "Zylinder"]
assert len(zyl) == 1 and zyl[0]["r"] == 5.0 and nah(zyl[0]["f"], math.pi * 10 * 4, 1e-3), zyl
assert sum(1 for e in fk if e["a"] == "Ebene") == len(fk) - 1
RR = step_netz("REF03_RR42-4x2_L1000")
assert sorted(e["r"] for e in RR["fk"] if e["a"] == "Zylinder") == [19.2, 21.2]
BOGEN = step_netz("REF11_RR42-4x2_Bogen90")
assert any(e["a"] == "Torus" and e["r"] == 200.0 and e["r2"] == 21.2 for e in BOGEN["fk"])
n = copy.deepcopy(L16)
sg._netz_anhaengen(n, dict(p=[0, 0, 0, 1, 0, 0, 0, 1, 0], t={"EO": [0, 1, 2]}, l={}))
assert n["fk"][-1] == dict(a="Netz") and n["tf"]["EO"] == [len(n["fk"]) - 1]
n = dict(p=[0, 0, 0, 100, 0, 0, 0, 100, 0], t={"A": [0, 1, 2]}, tf={"A": [0]}, fk=[dict(a="Ebene", f=5000.0)], l={})
step_offenes_rohr._verfeinern(n, 25.0)
assert len(n["tf"]["A"]) == len(n["t"]["A"]) // 3 > 1 and set(n["tf"]["A"]) == {0}
ok(f"T1 Flächenkatalog: L-Profil {len(fk)} Flächen (1 Zylinder R 5, Rest eben), Rundrohr R 21,2/19,2, Bogen als "
   "Torus R 200; Anhängen (Eintrag „Netz“) und Verfeinern halten tf passend")

# ------------------------------------------------------------------ T2 Programm: exakte Werte
a = ansicht3d.Ansicht3D()
a.resize(900, 500)
roh = copy.deepcopy(L16)
a.setzen(L16)
w = a.wahl
von, liste = w.elemente().flaechen()
assert len(liste) == len(fk)              # Flächen genau wie in der STEP
bohr = next(i for i, f in enumerate(liste) if (f.get("katalog") or {}).get("a") == "Zylinder")
w.gewaehlt = [w._flaeche_el(bohr)]
z = w.eigenschaften()
assert "Fläche (Zylinder, Ø 10,000 mm): 125,7 mm²" in z and "Ø 10,000 mm · R 5,000 mm · innen (Bohrung/Innenwand)" in z, z
assert "Flächeninhalt 125,664 mm²" in z and "Zylinder Ø 10,000 mm, Länge 4,0 mm (ganz herum)" in z, z
me = w.messelement(w._flaeche_el(bohr))
zy = mk.zylinder(me)
assert nah(zy["o"][2], 150, 0.01) and abs(abs(zy["achse"][2])) < 1e-6, zy
b = ansicht3d.Ansicht3D()
b.setzen(RR)
wb = b.wahl
_, lr = wb.elemente().flaechen()
mantel = [wb._flaeche_el(i) for i, f in enumerate(lr) if (f.get("katalog") or {}).get("a") == "Zylinder"]
wb.gewaehlt = mantel
z = wb.eigenschaften()
assert "Abstand Achse–Achse (parallel) 0,000 mm" in z and "Wandstärke (radial) 2,000 mm" in z, z
r = mk.paar(wb.messelement(mantel[0]), dict(typ="punkt", p=(30.0, 0.0, 500.0)))
assert r["haupt"][0] == "Abstand Punkt–Zylinderachse" and nah(r["haupt"][1], 30, 0.02), r
kaputt = copy.deepcopy(RR)
kaputt["tf"]["A"] = kaputt["tf"]["A"][:-1]
netz2, meldung = ansicht3d.netz_pruefen(kaputt)
assert meldung == "" and "tf" not in netz2 and "fk" not in netz2
aus = ansicht3d.ohne_arten(RR, {"I"})
assert "I" not in aus["tf"] and ansicht3d._katalog_ok(aus, aus["t"])
lage = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]
bg, _ = ansicht3d.baugruppe([dict(RR, lage=lage), dict(L16, lage=lage)])
assert len(bg["fk"]) == len(RR["fk"]) + len(L16["fk"]) and ansicht3d._katalog_ok(bg, bg["t"])
ok("T2 Programm: 9 Flächen wie STEP, Bohrung Ø 10,000/Fläche 125,664 exakt, Achse bei längs 150; Rundrohr Wand "
   "radial 2,000, Punkt–Achse 30; unpassender Katalog fällt still weg, Ebenen ausblenden und Baugruppe halten ihn")

# ------------------------------------------------------------------ T3 Rohrmessung
BOHR = [dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100), dict(art=sw.BOHRUNG, anzahl=1, d=8, x=150)]


def ansicht_von(prof, konturen=BOHR, laenge=500):
    netz = rohr3d.netz(sw.v_ergaenzen(dict(a={}, b={}, laenge=laenge, konturen=konturen), prof), prof, laenge)
    x = ansicht3d.Ansicht3D()
    x.setzen(netz)
    return x, netz


QR = dict(form="Quadratrohr", a=40, b=40, wand=3)
x, _ = ansicht_von(QR)
rw = mess_teil.rohr_werte(mess_teil.material_dreiecke(x.modell), dichte=7.85)
assert rw["form"] == "Quadratrohr" and nah(rw["breite"], 40) and nah(rw["hoehe"], 40) and nah(rw["laenge"], 500)
assert nah(rw["breite_innen"], 34) and nah(rw["wand"], 3, 0.02) and 5 < rw["r_aussen"] < 7, rw
assert 1.5 < rw["gewicht"] < 1.7 and rw["gewicht_aus"] == "Querschnitt × Länge" and not rw["dichte_angenommen"]
x, _ = ansicht_von(dict(form="Rundrohr", a=40, wand=2))
rw = mess_teil.rohr_werte(mess_teil.material_dreiecke(x.modell))
assert rw["form"] == "Rundrohr" and nah(rw["d_aussen"], 40, 0.01) and nah(rw["d_innen"], 36, 0.01) and rw["dichte_angenommen"]
x, _ = ansicht_von(dict(form="Rechteckrohr", a=60, b=40, wand=2))
rw = mess_teil.rohr_werte(mess_teil.material_dreiecke(x.modell), volumen=1000.0, dichte=2.7)
assert rw["form"] == "Rechteckrohr" and nah(rw["breite"], 60) and nah(rw["hoehe"], 40)
assert nah(rw["gewicht"], 1000 * 2.7e-6, 1e-12) and rw["gewicht_aus"] == "Volumen"
t = ansicht3d.Ansicht3D()
t.setzen(step_netz("REF13_T50x40x5_L600"))
rw = mess_teil.rohr_werte(mess_teil.material_dreiecke(t.modell))
assert rw["form"].startswith("offenes Profil") and nah(rw["querschnitt"], 425, 0.01) and nah(rw["laenge"], 600)
zeilen = mess_teil.rohr_zeilen(rw)
assert "Querschnitt 425,000 mm²" in zeilen and any(z.startswith("Masse") or z.startswith("≈ Masse") for z in zeilen)
ok("T3 Rohrmessung: QR 40×40×3 (Wand 3, Eckradius ≈ 6, 1,6 kg), RR 40×2 (Ø 40/36), RE 60×40 (Masse aus Volumen "
   "und Dichte), T-Profil offen 425 mm² × 600")

# ------------------------------------------------------------------ T4 Konturen und Fertigung
x, netz = ansicht_von(QR, [dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100), dict(art=sw.BOHRUNG, anzahl=1, d=10, x=112),
                           dict(art=sw.BOHRUNG, anzahl=1, d=8, x=300)])
roh_netz = copy.deepcopy(netz)
m = mess_teil.messen(x.modell, x.netz, x.geometrie().kreise, regeln=dfm.regeln())
ds = sorted(k["kreis_d"] for k in m["konturen"] if "kreis_d" in k)
assert ds == [8, 10, 10], ds
i, j, d = m["loecher"][0]
assert nah(d, 12, 0.01)
assert nah(m["stege"][0][2], 2, 0.1), m["stege"][0]
assert any("Steg zu schmal" in t_ for _, t_ in m["befunde"]), m["befunde"]
gr = mess_teil.gruppen(m)
assert [g[0] for g in gr] == ["Rohr", "Konturen", "Fertigung"]
assert any(z.startswith("Lochabstand") and "Mitte–Mitte 12,000 mm" in z for z in gr[2][1]), gr[2][1]
doppel = copy.deepcopy(x.netz)
doppel["l"]["K"].append(list(doppel["l"]["K"][0]))
m2 = mess_teil.messen(x.modell, doppel, x.geometrie().kreise)
assert m2["doppelt"] and any("doppelte Kontur" in t_ for _, t_ in m2["befunde"])
u = ansicht3d.Ansicht3D()
u.setzen(step_netz("REF15_U50x30x3_Konturen"))
mu = mess_teil.messen(u.modell, u.netz, u.geometrie().kreise)
eckig = [k for k in mu["konturen"] if k["art"] == "K" and "kreis_d" not in k]
assert len(eckig) == 1 and len(eckig[0]["geraden"]) == 4 and len(eckig[0]["ecken"]) == 4, eckig
assert all(nah(e, 90, 0.01) for e in eckig[0]["ecken"]), eckig
assert nah(eckig[0]["flaeche"], 200, 0.01) and mu["beide_seiten"] >= 1
assert netz == roh_netz
ok(f"T4 Konturen: Bohrungen Ø 8/10/10, Lochabstand 12, Reststeg ≈ 2 < 1,5 × Wand gemeldet, doppelte Kontur erkannt; "
   f"U-Profil: STEP-Kanten zu Rechteck 20 × 10 verbunden (4 Geraden, 4 × 90°), {mu['beide_seiten']} beidseitig "
   "gezeichnete Konturen einmal gezählt")

# ------------------------------------------------------------------ T5 Gehrung und gerichteter Winkel
g = mk.gehrung(mk.norm((1.0, 0.0, 1.0)))
assert nah(g["gehrung"], 45) and nah(g["um_hoch"], 45) and nah(g["um_quer"], 0)
g = mk.gehrung(mk.norm((0.0, 1.0, -1.0)))       # Normale zum Ende A: gleicher Drehsinn wie zum Ende B
assert nah(g["gehrung"], 45) and nah(g["um_quer"], 45), g
assert nah(mk.drehwinkel((1, 0, 0), (0, 1, 0), (0, 0, 1)), 90) and nah(mk.drehwinkel((0, 1, 0), (1, 0, 0), (0, 0, 1)), -90)
geh = ansicht3d.Ansicht3D()
geh.setzen(step_netz("REF09_RE60x40x2_Gehrung45"))
wg = geh.wahl
_, lg = wg.elemente().flaechen()
texte = []
for nr, f in enumerate(lg):
    if f["typ"] == "eben" and abs(f["n"][2]) > 0.1:
        wg.gewaehlt = [wg._flaeche_el(nr)]
        texte += wg.eigenschaften()
assert "Gehrung zur Bezugsebene (senkrecht zur Rohrachse) 45,00°" in texte and \
    "Gerader Schnitt: Fläche senkrecht zur Rohrachse (Gehrung 0°)" in texte, texte
assert any(t_.startswith("Drehsinn: um hoch") for t_ in texte)
seiten = [nr for nr, f in enumerate(lg) if f["typ"] == "eben" and abs(f["n"][2]) < 0.01][:2]
wg.gewaehlt = [wg._flaeche_el(nr) for nr in seiten]
z = wg.eigenschaften()
assert any(t_.startswith("Winkel gerichtet um die Rohrachse") and "90,00°" in t_ for t_ in z), z
ok("T5 Gehrung 45° zur Bezugsebene mit Drehsinn um hoch, gerader Schnitt 0°, gerichteter Winkel ±90° um die "
   "Rohrachse")

# ------------------------------------------------------------------ T6 Fenster Teil messen
x.titel = "QR 40 Test"
d = mess_teil_dialog.TeilMessung(x)
assert d.baum.topLevelItemCount() == 3 and d.baum.topLevelItem(0).text(0) == "Rohr"
assert "Quadratrohr" in d.text()
d.kopieren()
assert "Lochabstand" in QApplication.clipboard().text()
pfad = d.pdf(str(TMP / "teil.pdf"))
assert Path(pfad).read_bytes().startswith(b"%PDF")
d.close()
x.mess_kontext = dict(dichte=2.7, werkstoff="AlMgSi0,5")
gr = x.teil_messung()
assert "Werkstoff: AlMgSi0,5" in gr[0][1] and any("bei 2,70 kg/dm³" in z_ for z_ in gr[0][1]), gr[0][1]
leiste = ansicht3d_leiste.Leiste3D(x)
assert leiste.teil.text() == "Teil messen"
menue = x.standard_menue(zeigen=False)
assert any(a_.text().startswith("Teil messen") for a_ in menue.actions())
assert netz == roh_netz and L16 == roh
ok("T6 Fenster „Teil messen“: Rohr/Konturen/Fertigung, Kopieren, PDF, Werkstoff/Dichte aus dem Fenster; Knopf in "
   "der Leiste und Rechtsklick; Netz unverändert")
print("Alle Prüfungen bestanden.")
