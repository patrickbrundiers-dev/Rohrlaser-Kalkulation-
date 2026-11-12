"""Paket K aus dem PROfirst-Plan (Patrick 12.11.2026 „alles umsetzten“, im STEP-Import-Thread als Paket K):
K1 Bohren, Gewinde, Senken aus Layer oder Farbe der DXF.
K5 Export mit Bögen statt Kurven (dichte Punktfolgen als ARC, 0,01 mm genau), dazu STL aus dem 3D-Modell.

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

# ------------------------------------------------------------------ K5 Bögen statt Kurven
import math  # noqa: E402
import tempfile  # noqa: E402

from rohrlaser import blech, blech3d, dxf, rohr3d, schneidweg as sw, stl_export  # noqa: E402

# Langloch-ähnliche Kontur aus einer Spline (dichte Punkte): zwei Halbkreise R 10 und zwei Geraden
pk = [(40 + 10 * math.cos(math.radians(a)), 10 * math.sin(math.radians(a))) for a in range(-90, 91, 3)]
pk += [(10 * math.cos(math.radians(a)), 10 * math.sin(math.radians(a))) for a in range(90, 271, 3)]
el = dxf._polygon(dxf.INNEN, pk)
neu = dxf.boegen(el)
arten = [x[0] for x in neu]
assert arten.count("ARC") == 2 and arten.count("LINE") == 2, arten
for x in neu:
    if x[0] == "ARC":
        assert abs(x[3] - 10) <= 0.01, x
for q in pk:                # jeder alte Punkt liegt auf einem neuen Element (höchstens 0,01 mm)
    best = min((abs(math.dist(q, x[2]) - x[3]) if x[0] == "ARC" else
                abs((x[3][0] - x[2][0]) * (x[2][1] - q[1]) - (x[2][0] - q[0]) * (x[3][1] - x[2][1]))
                / math.dist(x[2], x[3])) for x in neu)
    assert best <= dxf.BOGEN_TOLERANZ + 1e-9, (q, best)
assert abs(sum(map(dxf.laenge, neu)) - (2 * math.pi * 10 + 80)) <= 0.05, sum(map(dxf.laenge, neu))
ring = [(120 + 25 * math.cos(math.radians(a)), 40 + 25 * math.sin(math.radians(a))) for a in range(0, 360, 5)]
kr = dxf.boegen(dxf._polygon(dxf.INNEN, ring))
assert [x[0] for x in kr] == ["CIRCLE"] and abs(kr[0][3] - 25) <= 0.01, kr      # Kreis aus 72 Stücken: ein Kreis
ecken = dxf._polygon(dxf.AUSSEN, [(0, 0), (100, 0), (100, 50), (0, 50)])
assert dxf.boegen(ecken) == ecken                       # Rechteck bleibt vier Linien
gerade = [dxf._linie(dxf.AUSSEN, (i, 0), (i + 1, 0)) for i in range(10)]
assert [x[0] for x in dxf.boegen(gerade)] == ["LINE"] * 10      # gerade Punktfolge wird kein Bogen
zick = [(i * 2.0, (i % 2) * 1.0) for i in range(8)]
assert all(x[0] == "LINE" for x in dxf.boegen(dxf._polygon(dxf.INNEN, zick)))    # Zickzack: keine Bögen
tmp = Path(tempfile.mkdtemp())
dxf.speichern(tmp / "k5.dxf", el)
zurueck = dxf.lesen((tmp / "k5.dxf").read_text(encoding="cp1252"))
assert sum(1 for x in zurueck if x[0] == "ARC") == 2, [x[0] for x in zurueck]
dxf.speichern(tmp / "k5_roh.dxf", el, mit_boegen=False)
assert not any(x[0] == "ARC" for x in dxf.lesen((tmp / "k5_roh.dxf").read_text(encoding="cp1252")))
ok("K5 DXF: Spline-Langloch (122 Stücke) -> 2 Bögen R 10 + 2 Linien, jeder Punkt <= 0,01 mm; Kreis aus 72 Stücken -> CIRCLE; Ecken, Geraden und "
   "Zickzack bleiben Linien")

# ------------------------------------------------------------------ K5 STL
QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
n = rohr3d.netz(dict(a={}, b={}, konturen=[]), QR, 500)
tri = stl_export.dreiecke(n, "rohr")
xs = [q[0] for t_ in tri for q in t_]
assert abs(min(xs)) <= 0.01 and abs(max(xs) - 500) <= 0.01            # X längs der Rohrachse, 0 bis 500 mm
v = stl_export.volumen(tri)
assert 200000 < v < 222000, v           # 40×40×3 mit Außenradius: knapp unter (40² - 34²) · 500 = 222000 mm³
n2 = rohr3d.netz(dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100)]), QR, 500)
v2 = stl_export.volumen(stl_export.dreiecke(n2, "rohr"))
assert abs((v - v2) - math.pi * 25 * 3) <= 3, v - v2         # Bohrung Ø 10 durch 3 mm Wand
e = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100,
         konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=8, x=50, y=30)])
tb = stl_export.dreiecke(blech3d.netz(e, blech.zuschnitt(e)), "blech")
assert abs(stl_export.volumen(tb) - (200 * 100 * 3 - math.pi * 16 * 3)) <= 5, stl_export.volumen(tb)
assert max(q[0] for t_ in tb for q in t_) - min(q[0] for t_ in tb for q in t_) == 200
assert stl_export.speichern(tmp / "r.stl", n, "rohr", "Pos 10") == len(tri)
roh = (tmp / "r.stl").read_bytes()
assert len(roh) == 84 + 50 * len(tri) and roh.startswith(b"Rohrlaser-Kalkulation Pos 10")
assert abs(stl_export.volumen(stl_export.lesen(roh)) - v) <= 1
hilfe = dict(n, t=dict(n["t"], HK=n["t"]["A"], WB=n["t"]["A"]))
assert len(stl_export.dreiecke(hilfe, "rohr")) == len(tri)       # Hilfs- und Schnittkörper nicht in der STL
assert stl_export.speichern(tmp / "leer.stl", None) == 0 and not (tmp / "leer.stl").exists()
ok("K5 STL: Rohr X 0-500 mm, Volumen geschlossen und positiv, Bohrung Ø 10 zieht 236 mm³ ab, Blech mit Bohrung; "
   "Hilfskörper fehlen, Datei liest sich zurück")

# ------------------------------------------------------------------ K5 Knöpfe in allen Editoren
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import baugruppe_step  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
nr = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(nr, dict(pos=10, artikel="K5-1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=300,
                         stueck=10))
seite = fenster.angebot_oeffnen(nr)
d = SchneidwegDialog(seite, seite.positionen[0], seite.k.profile["QR 40x40x3"], seite.kopf, seite.k, seite.tabellen)
d.show()
app.processEvents()
assert d.editor.band.knopf("STL speichern") is not None
assert d.editor.stl_speichern(str(tmp / "rohr.stl")) == str(tmp / "rohr.stl")
tr = stl_export.lesen((tmp / "rohr.stl").read_bytes())
assert abs(max(q[0] for t_ in tr for q in t_) - min(q[0] for t_ in tr for q in t_) - 300) <= 0.01
d.close()
werkstoff = sorted(z_["blech_werkstoff_id"] for z_ in db.zeilen("blech_werkstoffe"))[0]
dlg = BlechDialog(None, db, dict(e, werkstoff=werkstoff))
dlg.show()
app.processEvents()
assert dlg.editor.band.knopf("STL speichern") is not None
assert dlg.editor.stl_speichern(str(tmp / "blech.stl"))
assert abs(stl_export.volumen(stl_export.lesen((tmp / "blech.stl").read_bytes())) - stl_export.volumen(tb)) <= 1
dlg.close()


class _Bg(baugruppe_step.StepBaugruppe):        # Baugruppe/Satz in 3D: gemeinsamer Knopf und gemeinsames Speichern
    stumm = True

    def __init__(self, netz):
        self.ansicht3d = type("A", (), {"ansicht": type("N", (), {"netz": netz})()})()

    def step_name(self):
        return "BG 1"


bg_netz = dict(p=n["p"], t={"F0": n["t"]["A"] + n["t"]["I"], "SN": n["t"]["A"]})
assert _Bg(bg_netz).stl_speichern(str(tmp / "bg.stl"))
assert len(stl_export.lesen((tmp / "bg.stl").read_bytes())) == (len(n["t"]["A"]) + len(n["t"]["I"])) // 3
assert "STL" in _Bg(bg_netz).stl_knopf().text()
db.con.close()
ok("K5 Knopf „STL speichern“ im Rohr-, Blech-, Baugruppen- und Satz-Editor, Datei wie die 3D-Ansicht")
print("Paket K: alle Tests bestanden.")
