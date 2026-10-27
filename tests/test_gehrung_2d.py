"""Gehrung in 2D und 2D-Gehrungen aus der STEP (Patrick 27.10.2026).

G1 „Bei Gehrungen in 2D wird die Länge von der Spitze genommen, richtig wäre, wenn das Teil an der langen Seite
   kürzer wird“: Strahl 90° zur Oberfläche, Innenkante maßhaltig. Die lange Seite wird um Wand · tan(Winkel) kürzer,
   die kurze Seite bleibt; 3D (eben durch die Wand) und Gehrungen aus der STEP ('aussen_mass') bleiben wie gezeichnet.
   Rundrohr je Punkt radial (Wand · cos · tan). Schnittlänge wie bisher (Plan 3E-10 G1).
G2 „Wenn die Datei schon Schnitte 90 Grad zur Oberfläche hat, soll das auch erkannt werden“: eine in der STEP schon
   2D geschnittene Gehrung (Außenkante auf der Ebene, Innenkante darunter) wird als Gehrung mit Winkel und Richtung
   übernommen (vorher komplexes Ende) und steht im Editor genau wie in der STEP; ebenso die ebene Gehrung. Ist die
   lange Seite in der STEP schon gekürzt, bleibt das Ende komplex (genau wie gemessen).
G3 Größere Ausschnitte: Rohr mit einem Fenster fast über die ganze Länge (Lage aus dem geschlossenen Querschnitt an
   den Enden, vorher 5,9 mm daneben), Rundrohr-Ende halb weggeschnitten (Stufe genau, vorher 1,3 mm daneben).

Aufruf: python tests/test_gehrung_2d.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon  # noqa: E402
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism  # noqa: E402
from OCP.gp import gp_Pnt, gp_Vec  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, rohr3d, schneidweg as sw, skizze as sk, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py
box = wie.box


def ok(text):
    print("OK    ", text)


def nah(a, b, tol=1e-6):
    return abs(a - b) <= tol


def umriss(rund, b, h, r):
    """Punkte der Außenkontur mit Normalen [(x, y, nx, ny)] gegen den Uhrzeigersinn (Rundrohr: Ø b)."""
    if rund:
        n = 720
        return [(b / 2 * math.cos(2 * math.pi * i / n), b / 2 * math.sin(2 * math.pi * i / n),
                 math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
    out, cu, cv = [], b / 2 - r, h / 2 - r
    ecken = [(cu, cv, 0), (-cu, cv, 90), (-cu, -cv, 180), (cu, -cv, 270)]
    for k, (mx, my, a0) in enumerate(ecken):
        for j in range(25):
            a = math.radians(a0 + 90 * j / 24)
            out.append((mx + r * math.cos(a), my + r * math.sin(a), math.cos(a), math.sin(a)))
        nx_, ny_, a1 = ecken[(k + 1) % 4]
        p0 = (mx + r * math.cos(math.radians(a0 + 90)), my + r * math.sin(math.radians(a0 + 90)))
        p1 = (nx_ + r * math.cos(math.radians(a1)), ny_ + r * math.sin(math.radians(a1)))
        nrm = (math.cos(math.radians(a0 + 90)), math.sin(math.radians(a0 + 90)))
        out += [(p0[0] + j / 40 * (p1[0] - p0[0]), p0[1] + j / 40 * (p1[1] - p0[1]), *nrm) for j in range(1, 40)]
    return out


def gehrung_2d(shape, rund, b, h, t, r, L, w, richtung=(0.0, 1.0)):
    """Ende bei z = L als Gehrung w° in 2D wie ein 2D-Laser: jeder Punkt der Außenkante liegt auf der Gehrungsebene
    (lange Seite in richtung), die Schnittfläche steht senkrecht zur Oberfläche (Innenkante unter der Außenkante)."""
    pts = umriss(rund, b, h, r)
    ext = max(x * richtung[0] + y * richtung[1] for x, y, _, _ in pts)
    tw = math.tan(math.radians(w))
    aussen, innen = BRepBuilderAPI_MakePolygon(), BRepBuilderAPI_MakePolygon()
    for x, y, nx, ny in pts:
        z = L - (ext - (x * richtung[0] + y * richtung[1])) * tw
        aussen.Add(gp_Pnt(x + nx, y + ny, z))
        innen.Add(gp_Pnt(x - (t + 1) * nx, y - (t + 1) * ny, z))
    aussen.Close()
    innen.Close()
    ts = BRepOffsetAPI_ThruSections(False, True)
    ts.AddWire(aussen.Wire())
    ts.AddWire(innen.Wire())
    ts.Build()
    return et.cut(shape, BRepPrimAPI_MakePrism(ts.Shape(), gp_Vec(0, 0, 2 * b + 50)).Shape())


def g1_regel():
    for prof, t in ((dict(form="Rechteckrohr", a=80, b=40, wand=3), 3), (dict(form="Quadratrohr", a=40, wand=3), 3),
                    (dict(form="Rundrohr", a=48.3, wand=2.6), 2.6)):
        qs = sk.Querschnitt(sw.mit_radius(prof, {}))
        for w, achse in ((45, "über Höhe"), (30, "über Breite")):
            e = dict(winkel=w, achse=achse)
            s_ = [qs.umfang * i / 400 for i in range(400)]
            x2 = [sk.schnitt_x(qs, e, *qs.s_zu_uv(s)[0]) for s in s_]
            for e_ in (dict(e, d3=True), dict(e, aussen_mass=True)):
                x_ = [sk.schnitt_x(qs, e_, *qs.s_zu_uv(s)[0]) for s in s_]
                assert nah(min(x_), 0) and nah(max(x_), max(x2)), (prof["form"], e_)
            kurz = t * math.tan(math.radians(w))
            assert nah(min(x2), kurz), (prof["form"], w, min(x2), kurz)          # Spitze um Wand · tan kürzer
        # 3D-Modell: lange Seite kürzer, kurze Seite wie bisher
        n = rohr3d.netz(dict(a={}, b=dict(winkel=45, achse="über Höhe"), konturen=[]), prof, 500)
        z = [n["p"][i + 2] for i in range(0, len(n["p"]), 3)]
        assert nah(max(z), 500 - t, 1e-3), (prof["form"], max(z))
    # Rundrohr: radial, an der Seite (90°) unverändert, oben Wand · tan
    qs = sk.Querschnitt(dict(form="Rundrohr", a=48.3, wand=2.6))
    e = dict(winkel=45)
    assert nah(sk.schnitt_x(qs, e, 0, 24.15), 2.6) and nah(sk.schnitt_x(qs, e, 24.15, 0), 24.15)
    assert nah(sk.schnitt_x(qs, e, 0, -24.15), 48.3)
    # Schnittlänge wie bisher (G1 Plan 3E-10)
    from rohrlaser import schnittflaeche as sf
    qr = dict(form="Quadratrohr", a=60, b=60, wand=5)
    st = sf.abschnitte(sk.Querschnitt(sw.mit_radius(qr, {})), dict(winkel=30, richtung=0), False)
    assert abs(sum(s["laenge"] for s in st) - sw.ende(qr, 30)[0]) < 0.5
    ok("G1 Gehrung 2D: Innenkante maßhaltig, lange Seite um Wand · tan(Winkel) kürzer (Rechteck-, Quadrat-, "
       "Rundrohr), 3D und STEP wie gezeichnet, Schnittlänge wie bisher")


def teile():
    re = et.kastenrohr(80, 40, 3, 1000, 6)
    rr = et.rundrohr(48.3, 2.6, 900)
    return {
        "Z1_RE_2D_aussen": gehrung_2d(re, False, 80, 40, 3, 6, 1000, 45),
        "Z2_RE_2D_30_Breite": gehrung_2d(re, False, 80, 40, 3, 6, 1000, 30, (1.0, 0.0)),
        "Z3_RR_2D_aussen": gehrung_2d(rr, True, 48.3, 48.3, 2.6, 0, 900, 45),
        "Z4_RE_2D_innen": et.cut(et.gehrung(re, 1000, 45), box(-50, -30, 997, 100, 60, 20)),
        "Z5_RE_eben": et.schraeg_ende(re, 960, 45, 0),
        "G3_QR_langes_Fenster": et.cut(et.kastenrohr(60, 60, 3, 900, 6), box(-20, 0, 50, 40, 40, 800)),
        "G3_RR_Ende_halb": et.cut(rr, box(-30, 0, 750, 60, 30, 200)),
    }


def main():
    g1_regel()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = Datenbank(tmp / "rohrlaser.db")
        f = teile()
        for n, s in f.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp)] + [str(tmp / (n + ".step")) for n in f])
        ms = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)}
        assert len(ms) == len(f), sorted(ms)

        from PySide6.QtWidgets import QApplication
        from rohrlaser.schneidweg_dialog import SchneidwegDialog
        app = QApplication.instance() or QApplication([])  # noqa: F841
        k = db.kontext()
        erg = step.uebernehmen(list(ms.values()), [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               neue_profile=True)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        kopf = dict(maschine="T11", stange=6000)
        for p in erg["positionen"]:
            name = p["artikel"]
            m = ms[name]
            d = SchneidwegDialog(None, p, k.profile[p["profil_id"]], kopf, k, db.tabellen(), db)
            e = d.eingaben()
            n = d.ansicht3d.ansicht.netz
            sn = ansicht3d.entpacken(m["_netz"])
            mod = [z for a in ("K", "EA", "EB") for z in n["l"].get(a, [])]
            st = [z for a in ("K", "EA", "EB") for z in sn["l"].get(a, [])]
            weit = max(wie._abstand(mod, st), wie._abstand(st, mod)) - rohr3d.ABSTAND
            print(f"  {name}: {weit:+.3f} mm, Ende B {e['b'].get('form')} {e['b'].get('winkel')}°")
            assert weit <= TOL, f"{name}: im Editor {weit:.3f} mm neben der STEP"
            if name.startswith("Z4"):          # lange Seite schon gekürzt: komplex, genau wie gemessen
                assert e["b"].get("umriss") and e["b"].get("form") == "komplex", e["b"].get("form")
            elif name.startswith("Z"):
                b = e["b"]
                soll = 30 if "30" in name else 45
                assert b.get("form") == "Gehrung" and nah(b.get("winkel"), soll, 0.05) and not b.get("umriss"), \
                    (name, b)
                assert b.get("aussen_mass") is True, (name, b.get("aussen_mass"))
            d.deleteLater()
        ok("G2 Gehrung schon 2D in der STEP (Außenkante auf der Ebene, Innenkante darunter) als Gehrung erkannt, "
           "Editor genau wie die STEP; lange Seite schon gekürzt bleibt komplex")
        ok("G3 größere Ausschnitte: langes Fenster im Quadratrohr, halbes Rundrohr-Ende genau wie in der STEP")
    print("Alle Tests Gehrung 2D bestanden.")


if __name__ == "__main__":
    main()
