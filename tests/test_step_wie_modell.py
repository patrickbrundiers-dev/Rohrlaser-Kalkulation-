"""Konturen und Enden aus dem STEP-Import liegen im Modell des Programms genau wie in der STEP-Datei (Patrick 25.10.2026:
„Die Konturen sollten immer zu 100 % mit der STEP übereinstimmen“).

Je Testteil (erzeugt mit OpenCascade wie tests/erzeuge_testteile.py) wird gemessen, die Eingaben des Rechners gebildet
(step.rechner_eingaben) und das 3D-Modell daraus gerechnet (rohr3d.netz). Verglichen werden die Konturlinien (Art K)
und die Schnittkanten der Enden (EA/EB) mit den Linien des STEP-Netzes: größter Abstand in beide Richtungen.
Die Konturlinien des Modells liegen absichtlich rohr3d.ABSTAND über der Wand.

W1 Mapping Umfang der Messung (gerundete Ecken) -> Abwicklung der Skizze und zurück (skizze.rund_ort/uv_zu_s)
W2 Kastenprofile: Sonderkonturen über eine, zwei und drei Ecken, schräg, gedreht, liegend, QR mit Radius 6
W3 Bohrungen auf allen vier Seiten (vorher je Ecke 0,43 × Radius verschoben)
W4 Rundrohr: Rechteck, schräge Sonderkontur, Bohrungen rundum, Rohr in der Datei gedreht (Netz auf 0°)
W5 komplexes Ende über die Ecken (vorher im 3D gerade)
"""
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
from rohrlaser import ansicht3d, rohr3d, skizze as sk, step  # noqa: E402

TOL = 0.06          # mm über dem Abstand der Linien


def box(x, y, z, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def dreh(s, grad, achse=(0, 1, 0), um=(0, 0, 0)):
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(*um), gp_Dir(*achse)), math.radians(grad))
    return BRepBuilderAPI_Transform(s, t, True).Shape()


def teile():
    f = {}
    re = et.kastenrohr(60, 40, 3, 1000, 4.5)
    f["S1_Ecke"] = et.cut(re, box(15, 5, 300, 20, 20, 40))
    f["S2_drei_Waende"] = et.cut(re, box(-35, -5, 500, 70, 30, 50))
    f["S3_Ecke_schraeg"] = et.cut(re, dreh(box(12, 2, 300, 30, 30, 40), 20, (0, 1, 0), (25, 15, 320)))
    f["S4_unten_hinten"] = et.cut(re, box(-40, -30, 200, 25, 22, 30))
    s = re
    for i, (p, a) in enumerate((((0, 25, 100), (0, 1, 0)), ((35, 0, 200), (1, 0, 0)), ((0, -25, 300), (0, -1, 0)),
                                ((-35, 0, 400), (-1, 0, 0)))):
        s = et.cut(s, et.zylinder(p, [-c for c in a], 10 + 2 * i, 20))
    f["S5_Bohrungen_4_Seiten"] = s
    f["S6_QR_Ecke"] = et.cut(et.kastenrohr(40, 40, 3, 800, 6), box(10, 10, 300, 20, 20, 30))
    rr = et.rundrohr(60, 3, 800)
    f["S7_RR_Rechteck"] = et.cut(rr, box(10, 10, 300, 30, 30, 30))
    f["S8_Ecke_gedreht"] = dreh(f["S1_Ecke"], 180, (0, 0, 1))
    f["S9_RR_gedreht"] = dreh(et.cut(rr, dreh(box(5, 12, 400, 30, 30, 40), 25, (0, 1, 0), (20, 27, 420))), 90,
                              (0, 0, 1))
    s = rr
    for i, w in enumerate((0, 60, 135, 250)):
        a = (math.sin(math.radians(w)), math.cos(math.radians(w)), 0)
        s = et.cut(s, et.zylinder((a[0] * 40, a[1] * 40, 100 + 120 * i), [-c for c in a], 8 + 3 * i, 20))
    f["S10_RR_Bohrungen"] = s
    f["S11_RE_Ende_komplex"] = et.cut(re, dreh(box(-50, -10, 960, 100, 60, 100), 30, (1, 0, 0), (0, 0, 1000)))
    f["S12_RE_liegend"] = dreh(f["S2_drei_Waende"], 90, (0, 0, 1))
    return f


def _segs(zuege):
    out = []
    for z in zuege:
        p = [z[i:i + 3] for i in range(0, len(z) - 2, 3)]
        out += list(zip(p, p[1:]))
    return out


def _dseg(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    lg = sum(c * c for c in ab)
    f = 0 if lg < 1e-12 else max(0, min(1, sum((p[i] - a[i]) * ab[i] for i in range(3)) / lg))
    return math.dist(p, [a[i] + f * ab[i] for i in range(3)])


def _abstand(a, b):
    """Größter Abstand eines Punkts der Linien a (je 1 mm abgetastet) zu den Linien b."""
    sb, weit = _segs(b), 0.0
    for p, q in _segs(a):
        n = max(1, int(math.dist(p, q)))
        for k in range(n):
            x = [p[i] + (q[i] - p[i]) * k / n for i in range(3)]
            weit = max(weit, min(_dseg(x, s0, s1) for s0, s1 in sb))
    return weit


def w1_abbildung():
    s_von, umfang = step.umfang_skizze("Rechteckrohr", 60, 40, 60, 4.5)
    qs = sk.Querschnitt(dict(form="Rechteckrohr", a=60, b=40, wand=3, r_aussen=4.5))
    assert umfang == qs.umfang == 200
    u_umfang = 2 * (60 + 40) - (8 - 2 * math.pi) * 4.5
    for i in range(400):
        u = u_umfang * i / 400
        s = s_von(u)
        (us, vs), _ = qs.s_zu_uv(s)
        ur, vr, _ = sk.rund_ort(qs, us, vs)
        # Punkt auf der gerundeten Außenkontur in Bogenlänge ab Mitte oben = u
        assert abs(sk.uv_zu_s(qs, ur, vr) - s) < 1e-6 or abs(abs(sk.uv_zu_s(qs, ur, vr) - s) - 200) < 1e-6, (u, s)
    # Mitte oben, Ecken bei 45° genau auf der Ecke der Skizze
    assert abs(s_von(0) - 30) < 1e-9
    assert abs(s_von(25.5 + math.pi * 4.5 / 4) - 60) < 1e-9
    assert abs(s_von(25.5 + math.pi * 4.5 / 2) - 64.5) < 1e-9
    r = step.kasten_radius({"kontur_umfang": u_umfang}, 60, 40)
    assert abs(r - 4.5) < 0.01, r
    print("W1 Abbildung Umfang <-> Skizze ok")


def main():
    w1_abbildung()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        f = teile()
        for n, s in f.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp)] + [str(tmp / (n + ".step")) for n in f])
        ms = step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)
        assert len(ms) == len(f), len(ms)
        fehler = []
        for m in sorted(ms, key=lambda m: m["datei"]):
            name = Path(m["datei"]).stem
            a_, b_ = float(m["abm_a"]), float(m["abm_b"] or 0) or None
            profil = dict(form=m["profilform"], a=a_, b=b_, wand=float(m["wandstaerke"]), profil_id="X")
            e = step.rechner_eingaben(m, m["profilform"], a_, b_)
            n = rohr3d.netz(e, profil, float(m["laenge"]))
            sn = ansicht3d.entpacken(m["_netz"])
            zeile = [name]
            for arten, soll in ((("K",), rohr3d.ABSTAND), (("EA", "EB"), 0.0)):
                mod = [z for a in arten for z in n["l"].get(a, [])]
                st = [z for a in arten for z in sn["l"].get(a, [])]
                if not st:
                    continue
                assert mod, (name, arten)
                d = max(_abstand(mod, st), _abstand(st, mod))
                zeile.append(f"{'/'.join(arten)} {d - soll:+.3f} mm")
                if d > soll + TOL:
                    fehler.append(f"{name} {'/'.join(arten)}: {d - soll:.3f} mm daneben")
            print("  " + " · ".join(zeile))
        assert not fehler, fehler
    print("W2-W5 Konturen und Enden wie STEP ok")
    print("Alles in Ordnung")


if __name__ == "__main__":
    main()
