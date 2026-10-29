"""Typische Laserteile sicher erkennen (Patrick 28.10.2026: „Step import und Editoren so robust machen, dass so etwas
sicher und korrekt erkannt wird, keine Ausnahme“, dazu fünf Beispielbilder; „Gewinde-Erkennung verbessern, Senkungen
auch erkennen, wenn diese durch die komplette Wandstärke gehen, und dann nur den Innendurchmesser der Bohrung
schneiden, nicht den Senkungsdurchmesser“).

Nachgebaut nach den Bildern: Kastenprofil mit Lochfeldern, Kreuzmustern und Sattelausschnitten über drei Wände (L1),
C-Profil mit T-Ausklinkung am Ende, Schlitzen und V-Ausschnitt durch die Schenkel (L2), Rechteckrohr mit
Sechskant, schrägen Langlöchern, gedrehtem Quadrat, Kammschlitzen am Ende und V-Kerbe unten (L3), U-Kantprofil mit
Lochfeld, tieferen Schenkeln an den Enden und Kerben zwischen Nasen (L4), Quadratrohre mit Gehrung, Mäander mit
Laschen und Schlüsselloch (L5). Grundregel: Konturen im Editor 100 % wie die STEP (Lage und Form).

Gefunden und behoben:
F1 Kontur über mehr als den halben Umfang (V-Kerbe unten über drei Wände) galt als „über die 0°-Naht“: Mitte auf der
   falschen Seite, im Editor 40 mm daneben (step_geometrie._u_entrollen)
F2 schräge Langlöcher/Rechtecke (30°, 45°) wurden längs gezeichnet (bis 8 mm daneben): Sonderkontur mit Umriss
F3 offene Profile: Ausklinkung am Ende, Kerben im Schenkel und V-Ausschnitte waren nur Kreis bzw. gerades Ende (bis
   45 mm daneben): die Messung liefert die Kanten (STEP-JSON 1.21 "zuege"), das Programm legt sie auf die Flächen
   der Skizze; T-Ausklinkung als Ende mit Ausflug, Kerbe am Rand mit offener Mündung
F4 Senkung durch die ganze Wand (Kegel ohne Bohrung) war „Bohrung Ø Senk-Ø“ mit 3D-Schwenk, im Rundrohr Sonderkontur;
   Zylindersenkung war Bohrung Ø groß; Bleche kannten keine Senkung: jetzt Senkung, geschnitten der kleinste Ø
F5 Gewinde: Kern-Ø nach ISO (Inventor/Creo: M8 = 6,647) gab keinen Vorschlag, ausmodellierte Gewinde (Rillen,
   Schraubenflächen) wurden schräge Bohrungen mit 3D-Schwenk: jetzt Kernloch mit Gewinde

Aufruf: python tests/test_step_laserteile.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_robust as rob  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, \
    BRepBuilderAPI_MakeWire  # noqa: E402
from OCP.BRepLib import BRepLib  # noqa: E402
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone, BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol  # noqa: E402
from OCP.Geom import Geom_CylindricalSurface  # noqa: E402
from OCP.Geom2d import Geom2d_Line  # noqa: E402
from OCP.gp import gp_Ax1, gp_Ax2, gp_Ax3, gp_Dir, gp_Dir2d, gp_Pnt, gp_Pnt2d, gp_Vec  # noqa: E402
from rohrlaser import ansicht3d, rohr3d, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py (geschlossene Rohre)
TOL_AUS = 0.8       # mm offene Profile nach dem Ausrichten an Ende A (STEP-Kanten auf beiden Seiten der Wand)
box = wie.box
Y_, X_ = (0, -1, 0), (-1, 0, 0)      # Bohrrichtung von oben (+Y) bzw. von der Seite (+X)


def ok(text):
    print("OK:", text)


# ------------------------------------------------------------------ Werkzeuge für die Testteile
def _basis(d, u):
    dot = sum(u[i] * d[i] for i in range(3))
    u = [u[i] - dot * d[i] for i in range(3)]
    lu = math.sqrt(sum(x * x for x in u))
    u = [x / lu for x in u]
    return u, [d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0]]


def prisma(p, d, u, pts, laenge):
    """Polygon pts (a längs u, b längs d × u) in der Ebene durch p, ab 1 mm vor p längs d extrudiert."""
    u, v = _basis(d, u)
    pol = BRepBuilderAPI_MakePolygon()
    for a, b in pts:
        pol.Add(gp_Pnt(*[p[i] - d[i] + a * u[i] + b * v[i] for i in range(3)]))
    pol.Close()
    return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(pol.Wire()).Face(),
                                 gp_Vec(*[d[i] * (laenge + 1) for i in range(3)])).Shape()


def loch(s, p, d, dm, tief=12):
    return et.cut(s, et.zylinder(tuple(p[i] - d[i] for i in range(3)), d, dm, tief))


def poly_loch(s, p, d, u, pts, tief=12):
    return et.cut(s, prisma(p, d, u, pts, tief))


def langloch(s, p, d, u, lg, b, w=0.0, tief=12):
    """Langloch Länge lg, Breite b, Mitte p, Längsrichtung u um w Grad (um d) gedreht."""
    uu, vv = _basis(d, u)
    c, sn = math.cos(math.radians(w)), math.sin(math.radians(w))
    r = [c * uu[i] + sn * vv[i] for i in range(3)]
    h = (lg - b) / 2
    s = loch(loch(s, [p[i] + h * r[i] for i in range(3)], d, b, tief), [p[i] - h * r[i] for i in range(3)], d, b, tief)
    return poly_loch(s, p, d, r, [(-h, -b / 2), (h, -b / 2), (h, b / 2), (-h, b / 2)], tief)


def rechteck(s, p, d, u, lg, b, w=0.0, tief=12):
    c, sn = math.cos(math.radians(w)), math.sin(math.radians(w))
    pts = [(-lg / 2, -b / 2), (lg / 2, -b / 2), (lg / 2, b / 2), (-lg / 2, b / 2)]
    return poly_loch(s, p, d, u, [(a * c - b_ * sn, a * sn + b_ * c) for a, b_ in pts], tief)


def sechskant(s, p, d, u, sw, tief=12):
    r = sw / math.sqrt(3)
    return poly_loch(s, p, d, u, [(r * math.cos(math.radians(60 * k)), r * math.sin(math.radians(60 * k)))
                                  for k in range(6)], tief)


def kegelloch(s, p, d, d_aussen, d_innen, wand):
    """Kegelsenkung durch die ganze Wand: außen Ø d_aussen, innen Ø d_innen, keine Bohrung."""
    e, k = 0.5, (d_aussen - d_innen) / 2 / wand
    p0 = gp_Pnt(p[0] - e * d[0], p[1] - e * d[1], p[2] - e * d[2])
    return et.cut(s, BRepPrimAPI_MakeCone(gp_Ax2(p0, gp_Dir(*d)), d_aussen / 2 + e * k, d_innen / 2 - e * k,
                                          wand + 2 * e).Shape())


def zylindersenkung(s, p, d, d_bohr, d_senk, tiefe, wand):
    s = et.cut(s, et.zylinder(tuple(p[i] - d[i] for i in range(3)), d, d_senk, tiefe + 1))
    return et.cut(s, et.zylinder(tuple(p[i] - d[i] for i in range(3)), d, d_bohr, wand + 2))


def gewinde_rillen(s, p, d, nenn, kern, wand, steigung):
    """Gewinde als umlaufende Rillen (Zickzack um die Achse gedreht): Kegel im Wechsel zwischen Kern- und Außen-Ø."""
    u, _ = _basis(d, (1, 0, 0) if abs(d[0]) < 0.9 else (0, 1, 0))

    def pkt(r, t):
        return gp_Pnt(*[p[i] + d[i] * t + u[i] * r for i in range(3)])
    pol, t = BRepBuilderAPI_MakePolygon(), -1.0
    pol.Add(pkt(0, t))
    pol.Add(pkt(kern / 2, t))
    for _ in range(int((wand + 2) / steigung) + 1):
        pol.Add(pkt(nenn / 2, t + steigung / 2))
        pol.Add(pkt(kern / 2, t + steigung))
        t += steigung
    pol.Add(pkt(0, t))
    pol.Close()
    rev = BRepPrimAPI_MakeRevol(BRepBuilderAPI_MakeFace(pol.Wire()).Face(), gp_Ax1(gp_Pnt(*p), gp_Dir(*d))).Shape()
    return et.cut(s, rev)


def gewinde_schraube(s, p, d, nenn, kern, steigung, laenge):
    """Ausmodelliertes Gewinde: Kernloch und schraubenförmige Nut (Schraubenflächen als Freiform)."""
    s = et.cut(s, et.zylinder(p, d, kern, laenge + 1))
    ax3 = gp_Ax3(gp_Pnt(*p), gp_Dir(*d))
    zyl = Geom_CylindricalSurface(ax3, kern / 2)
    n = laenge / steigung
    lin = Geom2d_Line(gp_Pnt2d(0, 0), gp_Dir2d(2 * math.pi, steigung))
    e = BRepBuilderAPI_MakeEdge(lin, zyl, 0.0, n * math.hypot(2 * math.pi, steigung)).Edge()
    BRepLib.BuildCurves3d_s(e)
    ex, ez, r, h = ax3.XDirection(), ax3.Direction(), kern / 2, steigung * 0.4

    def pkt(rr, zz):
        return gp_Pnt(*(p[i] + ex.Coord(i + 1) * rr + ez.Coord(i + 1) * zz for i in range(3)))
    pipe = BRepOffsetAPI_MakePipeShell(BRepBuilderAPI_MakeWire(e).Wire())
    pipe.SetMode(gp_Dir(*d))
    pipe.Add(BRepBuilderAPI_MakePolygon(pkt(r - 0.05, -h), pkt(nenn / 2, 0), pkt(r - 0.05, h), True).Wire())
    pipe.Build()
    pipe.MakeSolid()
    return et.cut(s, pipe.Shape())


# ------------------------------------------------------------------ Testteile
def teile():
    f = {}
    # Bild 1: Kasten 120x80x4 mit Lochfeldern, Kreuzmustern, Langlochreihe und Sattelausschnitten über drei Wände
    k = et.kastenrohr(120, 80, 4, 1000, 8)
    for z0 in (80, 420, 760):
        for i in range(3):
            for j in (-1, 1):
                k = loch(k, (j * 25, 40, z0 + 40 * i), Y_, 14 if i != 1 else 10)
    for z0 in (250, 600):
        k = loch(k, (60, 0, z0), X_, 10)
        for a, b in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            for n in (1, 2):
                k = loch(k, (60, 12 * n * a, z0 + 12 * n * b), X_, 5)
    for z0 in (200, 540, 880):
        k = et.cut(k, et.zylinder((-80, 55, z0), (1, 0, 0), 60, 160))
    for z0 in range(300, 361, 15):
        k = langloch(k, (60, -20, z0), X_, (0, 1, 0), 14, 4)
    f["L1_RE120_Lochbild_Sattel"] = loch(k, (60, -25, 970), X_, 20)
    # Bild 2: C-Profil 80x50x15x2, T-Ausklinkung im Steg an Ende A, Schlitze, Löcher, V-Ausschnitt bis vor den Steg
    c = et.profil([(0, 0), (80, 0), (80, 50), (65, 50), (65, 48), (78, 48), (78, 2), (2, 2), (2, 48), (15, 48),
                   (15, 50), (0, 50)], 700)
    c = et.cut(et.cut(c, box(30, -1, -1, 20, 10, 25)), box(22, -1, 15, 36, 10, 10))
    for z0 in (120, 180):
        c = rechteck(c, (40, 0, z0), (0, 1, 0), (1, 0, 0), 12, 2.5)
    for z0 in (250, 450, 600):
        c = loch(c, (-1, 25, z0), (1, 0, 0), 14, 6)
    f["L2_C80_T_Ausklinkung_V"] = et.cut(c, prisma((-5, 0, 350), (1, 0, 0), (0, 0, 1),
                                                   [(-45, -51), (45, -51), (0, -6)], 95))
    # Bild 3: RE 80x40x2, schräges Langloch (30°), Sechskant, Lochfeld, gedrehtes Quadrat, Kammschlitze, V-Kerbe unten
    r = et.kastenrohr(80, 40, 2, 800, 4)
    for z0 in (150, 600):
        r = langloch(r, (0, 20, z0), Y_, (0, 0, 1), 40, 8, 30)
        r = loch(sechskant(r, (40, 0, z0 - 60), X_, (0, 0, 1), 13), (40, 0, z0 - 30), X_, 14)
        for i in range(4):
            for j in range(3):
                r = loch(r, (-20 + 10 * j, 20, z0 + 35 + 8 * i), Y_, 4)
        r = rechteck(r, (0, 20, z0 + 90), Y_, (0, 0, 1), 8, 8, 45)
    for z0 in (10, 30, 50):
        r = et.cut(r, box(-50, 10, z0 - 3, 100, 20, 6))
    f["L3_RE80_Sechskant_Kamm_V"] = et.cut(r, prisma((-45, 0, 400), (1, 0, 0), (0, 0, 1),
                                                     [(-30, 22), (30, 22), (0, -18)], 90))
    # Bild 4: U-Kantprofil 120x40x3 mit Lochfeld im Steg, Löchern in den Schenkeln, tieferen Schenkeln an den Enden
    # und Kerben vom Schenkelrand (Nasen dazwischen)
    u = et.profil([(-60, 0), (60, 0), (60, 40), (57, 40), (57, 3), (-57, 3), (-57, 40), (-60, 40)], 300)
    for i in range(5):
        for j in (-1, 0, 1):
            u = loch(u, (35 * j, 4, 30 + 60 * i), (0, -1, 0), 20 if j == 0 else 8)
        for x in (-61, 56):
            u = loch(u, (x, 22, 30 + 60 * i), (1, 0, 0), 12)
    u = et.cut(et.cut(u, box(-70, 30, -1, 140, 20, 20)), box(-70, 30, 281, 140, 20, 20))
    for z0 in (60, 150, 240):
        u = et.cut(u, box(-70, 34, z0 - 20, 140, 10, 15))
    f["L4_U_Kantprofil_Nasen"] = u
    # Bild 5
    q = et.schraeg_ende(et.kastenrohr(60, 60, 3, 600, 6), 560, 0, 45)
    f["L5a_QR60_Gehrung_Loch"] = loch(q, (0, 30, 300), Y_, 14)
    q = et.kastenrohr(50, 50, 3, 600, 5)
    zick = [(-200, -4)]
    for i in range(4):
        x0 = -200 + 100 * i
        zick += [(x0 + 60, -4), (x0 + 60, -12), (x0 + 75, -12), (x0 + 75, -4)]
    q = poly_loch(q, (0, 25, 300), Y_, (0, 0, 1), zick + [(200, -4), (200, 4), (-200, 4)])
    for z0 in range(120, 481, 90):
        q = rechteck(q, (25, 0, z0), X_, (0, 0, 1), 6, 6)
    for k_ in range(4):
        q = langloch(q, (0, 25, 540 + 10 * k_), Y_, (1, 0, 0), 30, 4)
    f["L5b_QR50_Maeander_Laschen"] = q
    q = et.schraeg_ende(et.kastenrohr(40, 40, 2, 500, 4), 470, 45, 0)
    q = langloch(loch(q, (0, 20, 380), Y_, 12), (0, 20, 392), Y_, (0, 0, 1), 20, 5)
    f["L5c_QR40_Gehrung_Schluesselloch"] = loch(loch(q, (20, 0, 250), X_, 8), (20, 0, 150), X_, 8)
    # Senkungen und Gewinde
    k2, k3 = et.kastenrohr(80, 40, 2, 600, 4), et.kastenrohr(80, 40, 3, 600, 6)
    f["S1_Senkung_durch_Wand"] = kegelloch(et.senkung(k2, (0, 20, 150), Y_, 6.6, 12.4, 2), (0, 20, 300), Y_,
                                           12.4, 8.4, 2)
    f["S2_Zylindersenkung"] = zylindersenkung(k3, (0, 20, 150), Y_, 6.6, 11, 1.5, 3)
    f["S3_RR_Senkung_durch_Wand"] = et.senkung(et.rundrohr(60.3, 2, 600), (0, 30.15, 300), Y_, 6.6, 12.4, 2)
    g = k3
    for i, dd in enumerate([5.0, 4.917, 6.647, 8.376, 4.134, 10.106]):
        g = et.cut(g, et.zylinder((-30, 25, 60 + 60 * i), Y_, dd, 10))
    f["G1_Kern_ISO"] = g
    f["G2_Gewinde_Rillen"] = gewinde_rillen(k3, (0, 20, 300), Y_, 8.0, 6.647, 3, 1.25)
    f["G3_Gewinde_Schraube"] = gewinde_schraube(k3, (0, 21, 300), Y_, 8, 6.647, 1.25, 5)
    b = box(0, 0, 0, 200, 4, 100)
    b = loch(loch(et.senkung(b, (30, 4, 30), Y_, 6.6, 12.4, 4), (60, 4, 30), Y_, 6.647), (90, 4, 30), Y_, 5.0)
    f["B1_Blech_Senkung"] = b
    d = box(0, 0, 0, 200, 2, 100)
    f["B2_Blech_Senkung_durch"] = kegelloch(kegelloch(d, (40, 2, 50), Y_, 12.4, 8.4, 2), (80, 2, 50), Y_, 12.4, 8.4, 2)
    return f


def _nahe(linien, bis=40.0):
    """Linien, die ganz im Bereich bis 'bis' mm vom Ende A liegen."""
    return [z for z in linien if max(z[2::3]) <= bis]


def _liste(m):
    return [d for d in json.loads(m.get("konturen_liste") or "[]") if isinstance(d, dict)]


def messung_pruefen(ms):
    k3 = [d for d in _liste(ms["L3_RE80_Sechskant_Kamm_V"]) if d.get("z") == 400.0]
    assert len(k3) == 1 and k3[0]["art"] == "Sonderkontur" and k3[0]["seite"] == "180°", k3
    ok("F1 V-Kerbe über drei Wände unten: Mitte auf der Unterseite (nicht über die Naht)")
    for name, n in (("L2_C80_T_Ausklinkung_V", 2), ("L4_U_Kantprofil_Nasen", 6)):
        aus = [d for d in _liste(ms[name]) if d.get("art") == "Ausschnitt"]
        assert len([d for d in aus if d.get("zuege")]) >= n, (name, aus)
        assert all(d.get("zuege") for d in _liste(ms[name]) if d.get("form") == "komplex"), name
    s1 = [d for d in _liste(ms["S1_Senkung_durch_Wand"]) if d.get("art") == "Senkung"]
    assert sorted((d["durchmesser"], d["senk_durchmesser"]) for d in s1) == [(8.4, 12.4), (8.4, 12.4)], s1   # 90°-Senkung 12,4 in 2 mm Wand: Kegel endet bei 8,4
    assert all(not d.get("schwenk") for d in s1) and abs(float(ms["S1_Senkung_durch_Wand"]["innen"]) -
                                                         2 * math.pi * 8.4) < 0.05
    s2 = [d for d in _liste(ms["S2_Zylindersenkung"]) if d.get("durchgehend") and d.get("z") == 150.0]
    assert [(d["art"], d["durchmesser"], d["senk_durchmesser"]) for d in s2] == [("Senkung", 6.6, 11.0)], s2
    s3 = [d for d in _liste(ms["S3_RR_Senkung_durch_Wand"]) if d.get("z") == 300.0]
    assert s3[0]["art"] == "Senkung" and 7.5 < s3[0]["durchmesser"] <= 8.4 and s3[0]["senk_durchmesser"] == 12.4, s3
    for name in ("B1_Blech_Senkung", "B2_Blech_Senkung_durch"):
        bl = json.loads(ms[name]["blech"])
        soll = [[6.6, 12.4, 1]] if name == "B1_Blech_Senkung" else [[8.4, 12.4, 2]]
        assert bl["senkungen"] == soll, (name, bl["senkungen"])
        senk = [k for k in bl["konturen_lage"] if k.get("senk_durchmesser")]
        assert senk and all(k["durchmesser"] == soll[0][0] for k in senk), senk
    assert abs(float(ms["B2_Blech_Senkung_durch"]["innen"]) - 2 * math.pi * 8.4) < 0.05
    ok("F4 Senkung durch die ganze Wand (Rohr, Rundrohr, Blech) und Zylindersenkung: geschnitten nur der kleinste Ø")
    for name in ("G2_Gewinde_Rillen", "G3_Gewinde_Schraube"):
        g = [d for d in _liste(ms[name]) if d.get("z") and 299 < d["z"] < 301]
        assert len(g) == 1 and g[0]["art"] == "Bohrung" and g[0].get("gewinde") == "M8" and \
            abs(g[0]["durchmesser"] - 6.65) < 0.02 and not g[0].get("schwenk"), (name, g)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = Datenbank(tmp / "rohrlaser.db")
        f = teile()
        for n, s in f.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp)] + [str(tmp / (n + ".step")) for n in f])
        ms = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)}
        assert len(ms) == len(f), sorted(set(f) - set(ms))
        messung_pruefen(ms)

        from PySide6.QtWidgets import QApplication
        from rohrlaser.schneidweg_dialog import SchneidwegDialog
        app = QApplication.instance() or QApplication([])  # noqa: F841
        k = db.kontext()
        erg = step.uebernehmen(list(ms.values()), [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               neue_profile=True)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        pos = {p["artikel"]: p for p in erg["positionen"]}
        vorschlag = pos["G1_Kern_ISO"].get("gewinde_vorschlag") or ""
        for g in ("M6", "M8", "M10", "M5", "M12"):
            assert g in vorschlag, vorschlag
        assert vorschlag.count("M6") == 1 and "2xM6" in vorschlag, vorschlag    # Ø 5 (DIN 336) und Ø 4,917 (ISO)
        assert "M8" in (pos["G3_Gewinde_Schraube"].get("gewinde_vorschlag") or ""), pos["G3_Gewinde_Schraube"]
        ok("F5 Gewinde: Kern-Ø nach ISO und ausmodellierte Gewinde (Rillen, Schraubenflächen) mit Vorschlag")

        def linien(netz, *a):
            return [z for a_ in a for z in netz["l"].get(a_, [])]
        for name in sorted(n for n in f if n.startswith("L") or n.startswith("S")):
            p, m = pos[name], ms[name]
            profil = k.profile[p["profil_id"]]
            d = SchneidwegDialog(None, p, profil, dict(maschine="T11", stange=6000), k, db.tabellen(), db)
            e = d.eingaben()
            arten = [z.get("art") for z in e["konturen"]]
            n, sn = wie.netz_wie_konstruiert(d), ansicht3d.entpacken(m["_netz"])  # ebene Gehrung wie konstruiert
            assert "sonstige Kontur" not in arten, (name, arten)
            if name in ("L2_C80_T_Ausklinkung_V", "L4_U_Kantprofil_Nasen"):
                # Ende A mit Ausklinkung: der Editor zeichnet den Fuß der Ausklinkung als Ende, den Rest als Ausflug
                # (Kontur), die STEP alles als Ende -> ausrichten an Ende A bzw. an allen Linien bis 40 mm vom Ende,
                # die bessere Lage zählt
                st = linien(sn, "K", "EA", "EB")
                hin = min(wie._abstand(rob._bewegen(linien(n, "K", "EA", "EB"), *rob.ausrichten(a, b)[1:]), st)
                          for a, b in ((linien(n, "EA"), linien(sn, "EA")),
                                       (_nahe(linien(n, "K", "EA")), _nahe(linien(sn, "K", "EA"))))) - rohr3d.ABSTAND
                print(f"  {name}: Modell→STEP {hin:+.2f} mm")
                assert hin <= TOL_AUS, (name, hin)
                if name.startswith("L2"):
                    teil_a = [z for z in e["konturen"] if z.get("ende_teil") == "A"]
                    assert len(teil_a) == 2 and all(z.get("muendung") for z in teil_a), teil_a
                    assert e["a"].get("umriss"), e["a"]
                d.deleteLater()
                continue
            werte = []
            for art in ("K", "EA", "EB"):
                mod, st = linien(n, art), linien(sn, art)
                if not st:
                    continue
                hin, zur = wie._abstand(mod, st) - rohr3d.ABSTAND, wie._abstand(st, mod) - rohr3d.ABSTAND
                werte.append(f"{art} {hin:+.3f}/{zur:+.3f}")
                # Senkung im Rundrohr: Kegel und Rohrinnenseite schneiden sich nicht als Kreis, geschnitten wird
                # der Kreis mit dem kleinsten Ø (Senkung ist Nacharbeit)
                grenze = 0.3 if art == "K" and "Senkung" in arten and name.startswith("S3") else TOL
                assert zur <= grenze, f"{name}: STEP-Linie {art} fehlt im Editor ({zur:.2f} mm)"
                if not (art == "K" and "Senkung" in arten):     # Senkung: Bohrung liegt in der STEP unter dem Kegel
                    assert hin <= TOL, f"{name}: Editor {art} {hin:.2f} mm neben der STEP"
            print(f"  {name}: " + ", ".join(werte) + " mm")
            if name.startswith("L3"):
                assert arten.count("Sonderkontur") == 10 and "Langloch" not in arten and "Rechteck" not in arten, arten
            d.deleteLater()
        ok("F2 schräge Langlöcher und Rechtecke als Sonderkontur mit Umriss, Editor wie STEP")
        ok("F3 offene Profile: Ausklinkung am Ende (T mit Ausflug), Kerben mit Mündung, V-Ausschnitt mit Umriss")
        ok("L1-L5 Laserteile nach den Bildern: Konturen und Enden im Editor wie die STEP")
    print("Alles in Ordnung")


if __name__ == "__main__":
    main()
