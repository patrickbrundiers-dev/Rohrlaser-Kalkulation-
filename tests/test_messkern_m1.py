"""Messkern und Direktmessung bei Auswahl (Messplan M1, Patrick 19.11.2026 „professionelles 3D-Messsystem“).

Geprüft wird gegen gerechnete Sollwerte, nicht gegen frühere Ausgaben:
M1 Vektor- und Abstandsgrundlagen: Strecke–Strecke, Punkt–Dreieck, Dreieck–Dreieck (auch Schnitt = 0)
M2 Elementwerte: Quader (Volumen, Schwerpunkt, Oberfläche), offener Körper ohne Volumen, Umfang auch mit T-Stoß,
   Bogenwinkel und Bogenlänge, Kreis Ø/R/Umfang
M3 Paare: parallele Ebenen, Ebene–Ebene-Winkel, Kante–Kante windschief, zwei Bohrungen (Mitte, Steg), Kante–Fläche
M4 Mindestabstand Körper–Körper, Grenze für sehr feine Netze, genäherte Werte mit „≈“
M5 Direktmessung im 3D-Fenster (Quadratrohr und Rundrohr mit Bohrungen): Volumen ≈ Profilquerschnitt × Länge,
   Umfang der Fläche, Steg zwischen Bohrungen, Winkel zur Rohrachse, Summen; Netz bleibt unverändert
M6 messen3d benutzt dieselben Rechenwege (keine zweite Messmaschine)

Aufruf: python tests/test_messkern_m1.py
"""
import copy
import math
import os
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import mess_kern as mk  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-9):
    return abs(a - b) <= tol


def quader(L, B, H, o=(0.0, 0.0, 0.0), dreh=False):
    """12 Dreiecke eines Quaders mit Normalen; dreh: Umlauf absichtlich falsch (Netze sind nicht immer gleich
    orientiert)."""
    P = {(x, y, z): (x * L + o[0], y * B + o[1], z * H + o[2]) for x in (0, 1) for y in (0, 1) for z in (0, 1)}
    tris, nor = [], []
    for ax in range(3):
        for s in (0, 1):
            andere = [a for a in range(3) if a != ax]
            q = []
            for u in (0, 1):
                for v in (0, 1):
                    c = [0, 0, 0]
                    c[ax], c[andere[0]], c[andere[1]] = s, u, v
                    q.append(P[tuple(c)])
            n = [0.0, 0.0, 0.0]
            n[ax] = 1.0 if s else -1.0
            tris += [(q[0], q[1], q[3]), (q[0], q[3], q[2]) if not dreh else (q[0], q[2], q[3])]
            nor += [tuple(n)] * 2
    return tris, nor


# ------------------------------------------------------------------ M1 Grundlagen
d, p, q = mk.strecke_strecke((0, 0, 0), (10, 0, 0), (5, 3, 4), (5, 3, 10))
assert nah(d, 5.0) and p == (5.0, 0.0, 0.0) and q == (5.0, 3.0, 4.0), (d, p, q)
d, p, q = mk.strecke_strecke((0, 0, 0), (10, 0, 0), (12, 0, 0), (20, 0, 0))     # auf einer Geraden
assert nah(d, 2.0)
assert mk.naechster_im_dreieck((1, 1, 5), (0, 0, 0), (10, 0, 0), (0, 10, 0)) == (1.0, 1.0, 0.0)
assert mk.naechster_im_dreieck((-3, -4, 0), (0, 0, 0), (10, 0, 0), (0, 10, 0)) == (0, 0, 0)
t1 = ((0, 0, 0), (10, 0, 0), (0, 10, 0))
assert nah(mk.dreieck_dreieck(t1, ((0, 0, 7), (10, 0, 7), (0, 10, 7)))[0], 7.0)
assert mk.dreieck_dreieck(t1, ((2, 2, -1), (2, 2, 1), (3, 3, 1)))[0] == 0.0             # durchstoßen
ok("M1 Strecke–Strecke, Punkt–Dreieck, Dreieck–Dreieck (Schnitt = 0) gegen Sollwerte")

# ------------------------------------------------------------------ M2 Elementwerte
for dreh in (False, True):
    t, n = quader(10, 20, 30, (5, -7, 100), dreh)
    w = mk.werte(dict(typ="koerper", dreiecke=t, normalen=n, eben=True))
    assert w["geschlossen"] and w["exakt"] and nah(w["volumen"], 6000.0, 1e-6), w
    assert all(nah(a, b, 1e-9) for a, b in zip(w["schwerpunkt"], (10.0, 3.0, 115.0))), w["schwerpunkt"]
    assert nah(w["flaeche"], 2 * (200 + 300 + 600), 1e-9)
w = mk.werte(dict(typ="koerper", dreiecke=t[:-2], normalen=n[:-2], eben=True))
assert not w["geschlossen"] and "volumen" not in w and nah(w["rand"], 2 * (10 + 20), 1e-9), w
assert any("Kein Volumen" in z for z in mk.zeilen_element(dict(typ="koerper", dreiecke=t[:-2], normalen=n[:-2])))
a_, b_, c_, d_, m_ = (0, 0, 0), (10, 0, 0), (10, 20, 0), (0, 20, 0), (5, 0, 0)
for tris in ([(a_, b_, d_), (b_, c_, d_)], [(a_, m_, d_), (m_, b_, c_), (m_, c_, d_)]):         # T-Stoß bei m
    w = mk.werte(dict(typ="ebene", dreiecke=tris, n=(0, 0, 1), mitte=(5, 10, 0)))
    assert nah(w["umfang"], 60.0) and nah(w["flaeche"], 200.0) and w["exakt"], w
bogen = [(10 * math.cos(math.radians(a)), 10 * math.sin(math.radians(a)), 0) for a in range(0, 91, 3)]
w = mk.werte(dict(typ="kreis", m=(0, 0, 0), n=(0, 0, 1), d=20, bogen=True, punkte=bogen))
assert nah(w["winkel"], 90.0, 1e-9) and nah(w["laenge"], 5 * math.pi, 1e-9), w
w = mk.werte(dict(typ="kreis", m=(0, 0, 0), n=(0, 0, 1), d=8, punkte=[]))
assert nah(w["r"], 4) and nah(w["laenge"], 8 * math.pi)
ok("M2 Quader 10×20×30: Volumen 6000, Schwerpunkt, Oberfläche (auch falsch orientiert); offen = kein Volumen; "
   "Umfang 60 auch mit T-Stoß; Bogen 90° = 5π")

# ------------------------------------------------------------------ M3 Paare
eb1 = dict(typ="ebene", dreiecke=[((0, 0, 0), (10, 0, 0), (0, 10, 0))], n=(0, 0, 1), mitte=(3, 3, 0))
eb2 = dict(typ="ebene", dreiecke=[((0, 0, 12.5), (10, 0, 12.5), (0, 10, 12.5))], n=(0, 0, -1), mitte=(3, 3, 12.5))
r = mk.paar(eb1, eb2)
assert r["haupt"][0].startswith("Abstand Fläche–Fläche") and nah(r["haupt"][1], 12.5), r
eb3 = dict(typ="ebene", dreiecke=[((0, 0, 0), (0, 10, 0), (0, 0, 10))], n=(1, 0, 0), mitte=(0, 3, 3))
r = mk.paar(eb1, eb3)
assert r["haupt"][0] == "Winkel Fläche–Fläche" and nah(r["haupt"][1], 90.0)
k1 = dict(typ="strecke", a=(0, 0, 0), b=(10, 0, 0))
k2 = dict(typ="strecke", a=(0, 5, 0), b=(0, 5, 10))
r = mk.paar(k1, k2)
assert r["haupt"] == ("Winkel Kante–Kante", 90.0, "°", True) and nah(r["werte"][0][1], 5.0), r
r = mk.paar(k1, dict(typ="strecke", a=(0, 3, 4), b=(20, 3, 4)))
assert r["haupt"][0] == "Abstand Kante–Kante (parallel)" and nah(r["haupt"][1], 5.0)
b1 = dict(typ="kreis", m=(100, 20, 0), n=(0, 1, 0), d=10, punkte=[])
b2 = dict(typ="kreis", m=(150, 20, 0), n=(0, 1, 0), d=8, punkte=[])
r = mk.paar(b1, b2)
werte = {e[0]: e[1] for e in r["werte"]}
assert nah(r["haupt"][1], 50.0) and nah(werte["Steg (Rand zu Rand)"], 41.0), r
r = mk.paar(dict(typ="strecke", a=(0, 0, 2), b=(10, 0, 2)), eb1)
assert r["haupt"][0] == "Abstand Kante–Fläche" and nah(r["haupt"][1], 2.0)
r = mk.paar(dict(typ="strecke", a=(0, 0, 0), b=(10, 0, 10)), eb1)
assert r["haupt"][0] == "Winkel Kante–Fläche" and nah(r["haupt"][1], 45.0, 1e-9)
r = mk.paar(dict(typ="punkt", p=(1, 1, 7)), eb1)
assert nah(r["haupt"][1], 7.0) and nah(r["werte"][-1][1], 7.0)
ok("M3 Paare: parallele Flächen 12,5, Winkel 90°/45°, Kanten windschief 5, parallel 5, Bohrungen Mitte 50/Steg 41")

# ------------------------------------------------------------------ M4 Mindestabstand Körper, Grenzen, ≈
t1, n1 = quader(10, 10, 10)
t2, n2 = quader(5, 5, 5, (13, 2, 2))
r = mk.paar(dict(typ="koerper", dreiecke=t1, normalen=n1, eben=True),
            dict(typ="koerper", dreiecke=t2, normalen=n2, eben=True))
assert r["haupt"][0] == "Mindestabstand" and nah(r["haupt"][1], 3.0) and r["haupt"][3], r
t3, n3 = quader(5, 5, 5, (8, 2, 2))                  # ragt hinein
r = mk.paar(dict(typ="koerper", dreiecke=t1, normalen=n1, eben=True),
            dict(typ="koerper", dreiecke=t3, normalen=n3, eben=True))
assert r["haupt"][1] == 0.0
viele = [((i, 0, 0), (i + 1, 0, 0), (i, 1, 0)) for i in range(800)]
m = mk.mindestabstand(dict(typ="flaeche", dreiecke=viele), dict(typ="flaeche", dreiecke=viele[:400]))
assert m["wert"] is None and "zu fein" in m["grund"]
gew = dict(typ="flaeche", dreiecke=[((0, 0, 0), (10, 0, 0), (0, 10, 1))], mitte=(3, 3, 0.3))
txt = mk.zeilen_paar(dict(typ="punkt", p=(0, 0, 5)), gew)
assert txt[0].startswith("≈ Mindestabstand"), txt
alt_max, mk.KOERPER_MAX = mk.KOERPER_MAX, 10
assert any("zu fein für die Direktmessung (12 Dreiecke)" in z
           for z in mk.zeilen_element(dict(typ="koerper", dreiecke=t1, normalen=n1, eben=True)))
mk.KOERPER_MAX = alt_max
assert mk.eintrag_text(("Abstand", 12.0, "mm", True)) == "Abstand 12,000 mm"
assert mk.eintrag_text(("Winkel", 45.0, "°", False)) == "≈ Winkel 45,00°"
ok("M4 Mindestabstand Körper 3,000 exakt, Überschneidung 0, sehr feine Netze mit Hinweis, Netzwerte mit „≈“")

# ------------------------------------------------------------------ M5 Direktmessung im 3D-Fenster
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, auswahl3d as aw, rohr3d, schneidweg as sw  # noqa: E402

ansicht3d.renderer_setzen("Software")
BOHR = [dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100), dict(art=sw.BOHRUNG, anzahl=1, d=8, x=150)]
for prof, querschnitt in ((dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3"), None),
                          (dict(form="Rundrohr", d=40, wand=2, profil_id="RR 40x2"), math.pi * (20 ** 2 - 18 ** 2))):
    netz = rohr3d.netz(dict(a={}, b={}, konturen=BOHR), prof, 500)
    roh = copy.deepcopy(netz)
    a = ansicht3d.Ansicht3D()
    a.setzen(netz)
    w = a.wahl
    me = w.messelement(w._koerper_el("k0"))
    werte_k = mk.werte(me)
    v = werte_k["volumen"]
    if querschnitt is None:              # Quadratrohr mit Eckradien: zwischen innen eckig und außen eckig
        assert (40 * 40 - 34 * 34 - 4 * 6 * 6) * 500 < v < (40 * 40 - 34 * 34) * 500, v
    else:                                # Rundrohr: Netz ist ein Vieleck, also etwas kleiner, unter 1 %
        soll = querschnitt * 500 - math.pi * (25 + 16) * 2
        assert 0.99 * soll < v <= soll, (v, soll)
    assert not werte_k["exakt"]
    w.gewaehlt = [w._koerper_el("k0")]
    zeilen = w.eigenschaften()
    assert any(z.startswith("≈ Volumen") for z in zeilen) and any("Schwerpunkt" in z for z in zeilen), zeilen
    geo = a.geometrie()
    ks = [dict(art=aw.KANTE, kreis=dict(m=k["m"], n=k["n"], d=k["d"], bogen=False, punkte=aw.kreis_punkte(k)))
          for k in geo.kreise if k["d"] < 12 and k["m"][1] > 0]
    ks = [next(k for k in ks if abs(k["kreis"]["d"] - 10) < 1e-6), next(k for k in ks if abs(k["kreis"]["d"] - 8) < 1e-6)]
    w.gewaehlt = ks
    zeilen = w.eigenschaften()
    assert "Abstand Mitte–Mitte 50,000 mm" in zeilen and "Steg (Rand zu Rand) 41,000 mm" in zeilen, zeilen
    w.gewaehlt = ks[:1]
    assert "Ø 10,000 mm · R 5,000 mm · Umfang 31,416 mm" in w.eigenschaften()
    if querschnitt is None:
        von, liste = w.elemente().flaechen()
        boden = next(w._flaeche_el(i) for i, f in enumerate(liste) if f["typ"] == "eben" and nah(f["flaeche"], 14000, 1e-6))
        w.gewaehlt = [boden]
        assert "Umfang (alle Ränder) 1056,000 mm" in w.eigenschaften()        # 2 × (500 + 28)
        w.gewaehlt = [boden, boden]
        assert "Gesamtfläche (2 Flächen) 28000,000 mm²" in w.eigenschaften()   # Summe bleibt auch bei zwei
        quer = next(g for g in geo.geraden if abs(g["a"][2]) < 1e-9 and abs(g["b"][2]) < 1e-9
                    and abs(abs(g["a"][0] - g["b"][0]) - 28) < 1e-6)
        w.gewaehlt = [dict(art=aw.KANTE, a=quer["a"], b=quer["b"])]
        assert "Winkel zur Rohrachse 90,00°" in w.eigenschaften()
        laengs = [g for g in geo.geraden if abs(g["a"][2] - g["b"][2]) > 400][:3]
        w.gewaehlt = [dict(art=aw.KANTE, a=g["a"], b=g["b"]) for g in laengs]
        assert "Gesamtlänge (3 Kanten) 1500,000 mm" in w.eigenschaften()
    assert netz == roh                  # Messen ändert nichts am Teil
ok("M5 Direktmessung Quadrat- und Rundrohr: ≈ Volumen im Querschnitt-Sollbereich, Bohrungen Mitte 50/Steg 41, "
   "Kreis Ø/R/Umfang, Flächenumfang 1056, Winkel zur Rohrachse 90°, Gesamtlänge 1500; Netz unverändert")

# ------------------------------------------------------------------ M6 nur ein Rechenweg
from rohrlaser import messen3d  # noqa: E402

for name, kern in (("_abstand_linie", "abstand_linie"), ("_abstand_strecke", "abstand_strecke"),
                   ("_abstand_windschief", "abstand_windschief"), ("schnittpunkt", "schnittpunkt"),
                   ("_strahl_dreieck", "strahl_dreieck"), ("winkel_zwischen", "winkel_zwischen"), ("zahl", "zahl")):
    assert getattr(messen3d, name) is getattr(mk, kern), name
assert "PySide6" not in Path(mk.__file__).read_text(encoding="utf-8")
ok("M6 messen3d rechnet mit dem Messkern (gleiche Funktionen), Messkern ohne Qt")
print("Alle Prüfungen bestanden.")
