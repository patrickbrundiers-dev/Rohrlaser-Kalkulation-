"""Testreihe Kantteile nach Patricks Bildern (05.11.2026: „Blech und Kantteil Erkennung verbessern“, Freigabe
„Umsetzung“ 14:32). Alle Teile hier mit OpenCascade gebaut (Radius innen = Dicke, k = 0,33):
- B1 Bild-Teile: C-Halter mit Langlöchern und Ø40 (auch schräg im Raum), mit Lasche in zweiter Achse, Hut mit
  Langlöchern, Halter mit Z-Lippe/Ausrundungen/Ohr, U mit Lasche nach unten: Blech gekantet, Zuschnitt, Konturen.
- B2 Ausschnitt quer über einer Biegung (Fenster mitten in der Kante, auch schräg im Raum): die Biegezone zerfiel in
  zwei Stücke = zwei Biegungen; Zuschnitt mit Schlitz bis zum Rand, keine Innenkontur, keine Schenkel, Hinweis
  „geschlossene Kanten“. Jetzt eine Biegung, Biegezone echt abgerollt: Rechteck-Innenkontur, Fläche stimmt.
- B3 Bohrung über der Biegung: abgerollt, als Kontur „über Biegung“ gekennzeichnet, Hinweis.
- B4 Ellipsen im Blech (eben und gekantet) heißen Ellipse mit Achsen; Kreis bleibt Bohrung, Langloch Langloch.
- B5 Blech-Editor aus der Messung: Kantteil mit Schenkeln, Ausschnitt an seiner Stelle, Schneidweg wie STEP.
- B6 C gekantet, Schenkel vorne und hinten ungekantet (flach in der Ebene des Rückens, Freischnitt 2 mm; Patrick
  15:11): war U-Profil ohne Kantteil-Auswahl, weil die kleinen Stirnflächen des Freischnitts einem Schenkel die
  Gegenseite wegnahmen. Jetzt Blech gekantet mit Zuschnitt 200 × 196,36 und freier Außenkontur, auch schräg.
- B7 Blech rechts und links nur leicht angekantet (2°–30°, Patrick 15:23): Kantteil mit gleichem Vorzeichen beider
  Kantungen (bis 15° wechselte es: Z statt Wanne); 2°/5° waren Flachstahl mit Dicke 0.
- B8 Blech mit herausstehenden Stecknasen rechts und links (eben, schräg im Raum, an leicht angekanteten Schenkeln):
  die Nasen fehlten in der Außenkontur (Hauptfläche in Stücken, nur die größte gemessen).
- B9 Platte 12 mm mit Zylindersenkungen und gefasten Bohrungen (Schweißtischplatte aus Patricks STEP,
  05.11.2026): war Frästeil (Senkungsboden als Absatz gezählt), jetzt Blech mit Senkungen.
- B10 gleiche Teile in einer Baugruppe: die Kopie je Körper brach ab, wenn eine Auswahl-Messung noch eine
  OpenCascade-Form trug (Palettenwagen, Formenregal: ganzer Import abgebrochen).
- B11 geschlossen gemessenes Sonderprofil mit unsicherer Wand (C-Halter 1 mm mit eingerollten Enden aus Patricks
  Blechteilen): war Sonderprofil ohne Kalkulation, jetzt Kantteil, wenn Zuschnitt × Dicke das Volumen trifft.
- B12 warmgewalzter Winkel mit ganz gerundeten Schenkelenden (Zoll-Winkel im Master Tower, 220 Teile): war offenes
  Sonderprofil ohne Kalkulation, jetzt L-Profil mit Bohrungen.

Aufruf: python tests/test_kantteil_bilder.py
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,  # noqa: E402
                                BRepBuilderAPI_MakeWire, BRepBuilderAPI_Transform)
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Elips, gp_Pnt, gp_Trsf, gp_Vec  # noqa: E402

from formen_baukasten import blech_bogen, kant, lage, ohne, plus, quader, schreibe, verschiebe, zyl  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402

fehler = 0
X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
BA90 = math.pi / 2 * (2 + 0.33 * 2)       # Biegezugabe 90°, t 2, Ri 2


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


def nah(a, b, tol=0.05):
    return abs(a - b) <= tol


def achsen(s, m, v=(0, 0, 0)):
    """Lokale Achsen x, y, z des Körpers auf die globalen Richtungen m = (ex, ey, ez), dann um v verschieben."""
    t = gp_Trsf()
    (a, b, c), (d, e, f), (g, h, i) = m
    t.SetValues(a, d, g, v[0], b, e, h, v[1], c, f, i, v[2])
    return BRepBuilderAPI_Transform(s, t, True).Shape()


def langloch(p1, p2, r, d, h=10):
    """Werkzeug Langloch von Mitte p1 nach p2 (achsparallel), Breite 2r, Bohrrichtung d (Achse)."""
    mn = [min(p1[i], p2[i]) for i in range(3)]
    mx = [max(p1[i], p2[i]) for i in range(3)]
    for i in range(3):
        if d[i]:
            mn[i], mx[i] = p1[i], p1[i] + h
        elif mx[i] - mn[i] < 1e-9:
            mn[i], mx[i] = mn[i] - r, mx[i] + r
    return plus(zyl(r, h, p1[2], p1[0], p1[1], d), zyl(r, h, p2[2], p2[0], p2[1], d),
                quader(mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2], *mn))


def ellipse(c, a, b, d, xdir, h=20):
    el = gp_Elips(gp_Ax2(gp_Pnt(*c), gp_Dir(*d), gp_Dir(*xdir)), a, b)
    f = BRepBuilderAPI_MakeFace(BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(el).Edge()).Wire()).Face()
    return BRepPrimAPI_MakePrism(f, gp_Vec(d[0] * h, d[1] * h, d[2] * h)).Shape()


# Bild 1: C-Halter, Rücken Ø40 + 4 × Ø5, Schenkel je 2 Langlöcher 33 × 8
werkz = [zyl(20, 10, 35, -5, 40, X)] + [zyl(2.5, 10, z, -5, y, X) for y in (15, 65) for z in (12, 58)]
werkz += [langloch((20, y, z), (45, y, z), 4, Y) for y in (-5, 75) for z in (20, 50)]
C_HALTER = ohne(kant([(60, 0), (0, 0), (0, 80), (60, 80)], 2, lg=70), *werkz)
C_LASCHE = plus(ohne(C_HALTER, quader(10, 30, 12, -5, 25, 60)),
                achsen(kant([(55, 0), (70, 0), (70, 25)], 2, lg=30), (Z, X, Y), (0, 25, 0)))
# Bild 2 rechts: Hut mit Flanschen, 3 Langlöcher oben, 6 Bohrungen in den Flanschen
HUT = ohne(kant([(-50, 0), (-30, 0), (-30, 70), (30, 70), (30, 0), (50, 0)], 3, lg=150),
           *[langloch((-5, 65, z), (5, 65, z), 4, Y) for z in (30, 75, 120)],
           *[zyl(4, 10, z, x, -5, Y) for x in (-41, 41) for z in (20, 75, 130)])
# Bild 3: Rücken + Boden + Lippe, Ausrundungen im Rücken, Ohr mit Bohrung über das Ende
Z_LIPPE = ohne(plus(ohne(kant([(0, 80), (0, 0), (45, 0), (45, 10)], 2, lg=60), zyl(12, 10, 0, -5, 50, X),
                         zyl(12, 10, 60, -5, 50, X)), quader(2, 18, 14, -1, 62, 60)), zyl(4, 10, 67, -5, 71, X))
# Bild 4: U mit 4 × Ø14 und Lasche nach unten an einem Ende (zweite Achse)
U_LASCHE = plus(ohne(kant([(0, 50), (0, 0), (70, 0), (70, 50)], 2, lg=100), zyl(7, 10, 25, -5, 30, X),
                     zyl(7, 10, 75, -5, 30, X), zyl(7, 10, 50, 65, 30, X), zyl(7, 10, 50, 35, -5, Y)),
                achsen(kant([(95, 0), (120, 0), (120, -30)], 2, lg=30), (Z, Y, (-1, 0, 0)), (50, 0, 0)))
U = kant([(0, 50), (0, 0), (70, 0), (70, 50)], 2, lg=100)
FENSTER = ohne(U, quader(8, 8, 20, -4, -4, 40))                       # Fenster quer über die erste Biegung
L_ = kant([(0, 60), (0, 0), (60, 0)], 2, lg=100)
L_AUSSCHNITT = ohne(L_, quader(20, 20, 10, -5, -5, 65))               # Ausschnitt über die Biegung in beide Schenkel
L_BOHRUNG = ohne(L_, zyl(8, 20, 30, -10, 2, (1, 1, 0)))               # Ø16 schräg durch die Biegung
PLATTE_ELL = ohne(quader(200, 120, 3), ellipse((60, 60, -5), 30, 18, Z, X), ellipse((150, 60, -5), 20, 12, Z, (1, 1, 0)),
                  zyl(10, 10, -5, 110, 25), langloch((100, 95, -5), (130, 95, -5), 5, Z))
WANNE_ELL = ohne(kant([(0, 120), (0, 15), (15, 0), (85, 0), (100, 15), (100, 120)], 3, lg=110),
                 ellipse((-5, 80, 55), 25, 15, X, Y), ellipse((50, -5, 55), 30, 18, Y, X))
LF = 61         # flacher Schenkel an den Enden: Rücken bis 3 mm vor die Biegung + 58 mm
C_FLACH = plus(kant([(60, 0), (0, 0), (0, 80), (60, 80)], 2, lg=140), quader(2, 196, 28, -1, -LF + 3, -30),
               quader(2, 74, 2, -1, 3, -2), quader(2, 196, 28, -1, -LF + 3, 142), quader(2, 74, 2, -1, 3, 140))
C_FLACH = ohne(C_FLACH, zyl(5, 10, -16, -5, -40, X), zyl(5, 10, 156, -5, 120, X))


def leicht(w, f=40, b=300, lg=200, t=2):
    c, s_ = math.cos(math.radians(w)), math.sin(math.radians(w))
    return blech_bogen([(-f * c, f * s_), (0, 0), (b, 0), (b + f * c, f * s_)], t, t, lg)


NASEN = [quader(6, 12, 3, -6, 20, 0), quader(6, 12, 3, -6, 68, 0), quader(6, 12, 3, 200, 20, 0),
         quader(6, 12, 3, 200, 68, 0)]
NASEN_EBEN = ohne(plus(quader(200, 100, 3), *NASEN), zyl(5, 10, -5, 100, 50))
c15, s15 = math.cos(math.radians(15)), math.sin(math.radians(15))
NASEN_KANT = plus(leicht(15), *[verschiebe(blech_bogen([(-6 * c15, 6 * s15), (0, 0)], 2, 2, 20), -40 * c15, 40 * s15, z)
                                for z in (40, 140)],
                  *[verschiebe(blech_bogen([(0, 0), (6 * c15, 6 * s15)], 2, 2, 20), 300 + 40 * c15, 40 * s15, z)
                    for z in (40, 140)])
def _senk_platte():
    import erzeuge_testteile as et
    p = quader(400, 300, 12)
    for x in (50, 150, 250, 350):
        for y in (50, 150, 250):
            p = et.senkung(p, (x, y, 12), (0, 0, -1), 14, 16, 12)       # Fase oben
    for x in (100, 300):
        p = ohne(p, zyl(9.5, 7, 8.5, x, 100), zyl(6, 20, -1, x, 100))  # Zylindersenkung Ø19 × 3,5 / Ø12
    return p


SENK_PLATTE = _senk_platte()
# Zoll-Winkel 1 1/2" × 5/16" mit ganz gerundeten Schenkelenden (Master Tower), Länge 600, zwei Bohrungen Ø13
WINKEL_RUND = ohne(plus(quader(34.1, 8, 600), zyl(4, 600, 0, 34.1, 4), quader(8, 34.1, 600), zyl(4, 600, 0, 4, 34.1)),
                   zyl(6.5, 20, 100, 20, -5, Y), zyl(6.5, 20, 500, 20, -5, Y))
LEICHT = {f"Leicht_{w}": leicht(w) for w in (2, 5, 10, 15, 30)}
TEILE = {"Winkel_rund": WINKEL_RUND, "Winkel_rund_schraeg": lage(WINKEL_RUND), "Senk_Platte": SENK_PLATTE, **LEICHT, "Leicht_10_schraeg": lage(leicht(10)), "Nasen_eben": NASEN_EBEN, "Nasen_schraeg": lage(NASEN_EBEN),
         "Nasen_kant": NASEN_KANT, "C_Flach": C_FLACH, "C_Flach_schraeg": lage(C_FLACH), "C_Halter": C_HALTER, "C_Halter_schraeg": lage(C_HALTER), "C_Lasche": C_LASCHE, "Hut": HUT,
         "Z_Lippe": Z_LIPPE, "U_Lasche": U_LASCHE, "Fenster": FENSTER, "Fenster_schraeg": lage(FENSTER),
         "L_Ausschnitt": L_AUSSCHNITT, "L_Bohrung": L_BOHRUNG, "Platte_Ellipsen": PLATTE_ELL, "Wanne_Ellipsen": WANNE_ELL}
TMP = Path(tempfile.mkdtemp())
schreibe(TEILE, TMP)
M = {}


def m(name):
    if name not in M:
        (M[name],) = analysiere_datei(TMP / f"{name}.step")
    return M[name]


def abw(name):
    return m(name).blech["abwicklung"]


@fall("B1 Bild-Teile: Blech gekantet, Kantungen, Zuschnitt und Konturen (auch schräg im Raum)")
def _():
    for n in ("C_Halter", "C_Halter_schraeg"):
        a, b = abw(n), m(n).blech
        assert m(n).profilform == "Blech gekantet" and a["kantungen"] == 2, (n, m(n).profilform, a["kantungen"])
        assert nah(max(a["laenge"], a["breite"]), 188 + 2 * BA90) and nah(min(a["laenge"], a["breite"]), 70), a
        assert [x["laenge"] for x in a["schenkel"]] == [61, 82, 61], a["schenkel"]
        arten = sorted(k["art"] for k in b["konturen_lage"])
        assert arten == ["Bohrung"] * 5 + ["Langloch"] * 4, arten
    a = abw("C_Lasche")
    assert a["mehrachsig"] and a["kantungen"] == 3 and m("C_Lasche").blech["innen"] == 9, a
    assert abw("Hut")["kantungen"] == 4 and m("Hut").blech["innen"] == 9
    assert sorted(k["art"] for k in m("Hut").blech["konturen_lage"]) == ["Bohrung"] * 6 + ["Langloch"] * 3
    a, b = abw("Z_Lippe"), m("Z_Lippe").blech
    assert a["kantungen"] == 2 and b["aussen_punkte"] and b["bohrungen"] == {8.0: 1}, (a, b["bohrungen"])
    a = abw("U_Lasche")
    assert a["mehrachsig"] and a["kantungen"] == 3 and m("U_Lasche").blech["bohrungen"] == {14.0: 4}, a
    for n in ("C_Halter", "Hut", "U_Lasche"):
        assert not any("über einer Biegung" in h or "geschlossene Kanten" in h for h in m(n).hinweise), m(n).hinweise


@fall("B2 Ausschnitt quer über einer Biegung: eine Biegung, Innenkontur im Zuschnitt, Fläche stimmt, Schenkel da")
def _():
    for n in ("Fenster", "Fenster_schraeg"):
        a, b = abw(n), m(n).blech
        assert a["kantungen"] == 2 and not a["mehrachsig"] and [x["laenge"] for x in a["schenkel"]] == [51, 72, 51], a
        assert b["innen"] == 1 and b["aussen_punkte"] is None, (n, b["innen"], b["aussen_punkte"])
        (k,) = b["konturen_lage"]
        assert k["art"] == "Rechteck" and k["ueber_biegung"] and nah(k["laenge"], 20), k
        assert nah(b["abwicklung_flaeche"], 100 * (158 + 2 * BA90) - 20 * k["breite"], 0.5), b["abwicklung_flaeche"]
        assert not any("geschlossene Kanten" in h for h in m(n).hinweise), m(n).hinweise
        assert any("1 Innenkontur über einer Biegung" in h for h in m(n).hinweise), m(n).hinweise
    b = m("L_Ausschnitt").blech
    (k,) = b["konturen_lage"]
    assert abw("L_Ausschnitt")["kantungen"] == 1 and k["art"] == "Rechteck" and nah(k["breite"], 10), k
    assert nah(k["laenge"], 2 * (15 - 3) + BA90, 0.05), k        # je Schenkel bis 15 mm (Tangente bei 3) + BA
    assert nah(b["abwicklung_flaeche"], 100 * (114 + BA90) - k["laenge"] * 10, 0.5), b["abwicklung_flaeche"]


@fall("B3 Bohrung über der Biegung: abgerollt, gekennzeichnet, Hinweis")
def _():
    b = m("L_Bohrung").blech
    (k,) = b["konturen_lage"]
    assert k.get("ueber_biegung") and k["art"] == "Polygon", k
    assert any("über einer Biegung" in h for h in m("L_Bohrung").hinweise)
    assert not any(x.get("ueber_biegung") for x in m("C_Halter").blech["konturen_lage"])


@fall("B4 Ellipsen im Blech (eben und gekantet) mit Achsen; Kreis bleibt Bohrung, Langloch bleibt Langloch")
def _():
    b = m("Platte_Ellipsen").blech
    ell = sorted((k["achsen"] for k in b["konturen_lage"] if k.get("form") == "Ellipse"), reverse=True)
    assert ell == [[60.0, 36.0], [40.0, 24.0]], ell
    assert sorted(k["art"] for k in b["konturen_lage"] if not k.get("form")) == ["Bohrung", "Langloch"]
    assert all(k["abweichung"] <= 0.05 for k in b["konturen_lage"]), b["konturen_lage"]
    assert any(h.startswith("2 Ellipsen (") for h in m("Platte_Ellipsen").hinweise), m("Platte_Ellipsen").hinweise
    ell = sorted(k["achsen"] for k in m("Wanne_Ellipsen").blech["konturen_lage"] if k.get("form") == "Ellipse")
    assert ell == [[50.0, 30.0], [60.0, 36.0]], ell


@fall("B5 Blech-Editor aus der Messung: Kantteil mit Schenkeln, Ausschnitt über der Biegung, Schneidweg wie STEP")
def _():
    from rohrlaser import blech
    for n in ("Fenster", "L_Ausschnitt", "C_Halter"):
        b = json.loads(json.dumps(m(n).blech))
        e = blech.aus_step(b, "S235JR")
        zs = blech.zuschnitt(e)
        assert e["art"] == blech.KANTTEIL and e["schenkel"], (n, e["art"])
        sw_editor = zs["aussen"] + sum(blech.sw.kontur(z)[0] * z["anzahl"] for z in e["konturen"])
        assert nah(sw_editor, b["umfang_aussen"] + b["umfang_innen"], 0.5), (n, sw_editor, b["umfang_aussen"])


@fall("B6 C gekantet, Schenkel vorne und hinten ungekantet: Blech gekantet, Zuschnitt mit freier Außenkontur")
def _():
    for n in ("C_Flach", "C_Flach_schraeg"):
        t = m(n)
        assert t.profilform == "Blech gekantet" and t.alternative is not None, (n, t.profilform)
        a, b = abw(n), t.blech
        assert a["kantungen"] == 2 and nah(a["laenge"], 200) and nah(a["breite"], 188 + 2 * BA90), a
        assert [x["laenge"] for x in a["schenkel"]] == [61, 82, 61] and len(b["aussen_punkte"]) == 20, a["schenkel"]
        assert b["bohrungen"] == {10.0: 2}, b["bohrungen"]


@fall("B7 Blech rechts und links leicht angekantet (2°–30°): Kantteil, beide Kantungen in dieselbe Richtung")
def _():
    for n in (*LEICHT, "Leicht_10_schraeg"):
        w = int(n.split("_")[1])
        t = m(n)
        assert t.profilform == "Blech gekantet" and t.wandstaerke == 2, (n, t.profilform, t.wandstaerke)
        a = abw(n)
        winkel = [x["winkel"] for x in a["schenkel"][:2]]
        assert a["kantungen"] == 2 and winkel[0] == winkel[1] and abs(winkel[0]) == w, (n, winkel)
        soll = 380 - 4 * (2 + 1) * math.tan(math.radians(w) / 2) + 2 * math.radians(w) * (2 + 0.33 * 2)
        assert nah(max(a["laenge"], a["breite"]), soll, 0.05), (n, a["laenge"], a["breite"], soll)


@fall("B8 Stecknasen rechts und links: in der Außenkontur (eben, schräg, an leicht angekanteten Schenkeln)")
def _():
    for n in ("Nasen_eben", "Nasen_schraeg"):
        b = m(n).blech
        assert m(n).profilform == "Blech" and nah(b["laenge"], 212) and nah(b["breite"], 100), (n, b["laenge"])
        assert nah(b["umfang_aussen"], 600 + 4 * 12, 0.05) and len(b["aussen_punkte"]) >= 20, (n, b["umfang_aussen"])
        assert b["bohrungen"] == {10.0: 1}, b["bohrungen"]
    a, b = abw("Nasen_kant"), m("Nasen_kant").blech
    assert m("Nasen_kant").profilform == "Blech gekantet" and a["kantungen"] == 2 and len(b["aussen_punkte"]) == 20, a
    assert nah(max(a["laenge"], a["breite"]), abw("Leicht_15")["breite"] + 12, 0.1), (a["laenge"], a["breite"])


@fall("B9 Platte 12 mm mit Zylindersenkungen und Fasen: Blech mit Senkungen, kein Frästeil")
def _():
    t = m("Senk_Platte")
    assert t.profilform == "Blech" and t.wandstaerke == 12, (t.profilform, t.hinweise)
    assert t.senkungen == {(12.0, 19.0): 2, (14.0, 16.0): 12}, t.senkungen
    assert t.blech["bohrungen"] == {12.0: 2, 14.0: 12}, t.blech["bohrungen"]


@fall("B10 gleiche Teile in einer Baugruppe: Kopie je Körper auch mit OpenCascade-Form an der Auswahl")
def _():
    import step_geometrie as g
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    t = g.Teil(datei="x", koerper=1, ende_a_global=(0.0, 0.0, 0.0))
    t.alternative = g.Teil(datei="x", koerper=1)
    form = BRepPrimAPI_MakeBox(1, 2, 3).Shape()
    t.alternative._rahmen = dict(solid=form)
    t.alternative.fremd = [form]                         # irgendwo anders gemerkte Form
    k = g._instanz(t, 2, {"bauteile": {}}, (10.0, 0.0, 0.0))
    assert k.koerper == 2 and k.ende_a_global == (10.0, 0.0, 0.0) and k.alternative.fremd[0] is form
    assert t.alternative._rahmen["solid"] is form and "_rahmen" not in k.alternative.__dict__


@fall("B11 Sonderprofil mit unsicherer Wand, das sich als Kantteil abwickeln lässt: Blech gekantet, kein Rohr")
def _():
    import step_geometrie as g
    from formen_baukasten import kant
    solid = kant([(60, 0), (0, 0), (0, 80), (60, 80)], 2, lg=70)
    v = g._volumen(solid)
    t = g.Teil(datei="x", koerper=1, profilform="Sonderprofil")
    t.sicherheit = {"profil": "unsicher", "wandstaerke": "unsicher"}
    fl = {"art": "gekantet", "dicke": 2.0}
    assert g._kein_rohr(solid, t, fl, v) and fl["abwicklung"]["kantungen"] == 2, fl
    assert not g._kein_rohr(solid, t, {"art": "gekantet", "dicke": 2.0}, 1.3 * v)       # Volumen passt nicht
    t.sicherheit["wandstaerke"] = "sicher"
    assert not g._kein_rohr(solid, t, {"art": "gekantet", "dicke": 2.0}, v)            # echtes Rohr bleibt Rohr


@fall("B12 Winkel mit ganz gerundeten Schenkelenden: L-Profil, auch schräg im Raum")
def _():
    for n in ("Winkel_rund", "Winkel_rund_schraeg"):
        t = m(n)
        assert t.profilform == "L-Profil" and nah(t.abm_a, 38.1, 0.05) and nah(t.wandstaerke, 8, 0.1), \
            (n, t.profilform, t.abm_a, t.wandstaerke, t.hinweise)
        assert nah(t.laenge, 600, 0.1) and t.konturen >= 4, (n, t.laenge, t.konturen)


if fehler:
    print(f"{fehler} Fall/Fälle rot")
    sys.exit(1)
print("Alle Kantteil-Bilder-Tests bestanden.")
