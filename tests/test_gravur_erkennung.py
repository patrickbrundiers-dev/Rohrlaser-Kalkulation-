"""Gravuren aus der STEP genauer erkennen (Patrick 16.11.2026: „Die Erkennung von Gravuren verbessern“).

Testteile mit OpenCascade (wie tests/erzeuge_testteile.py), gemessen mit step_messen, übernommen wie im Programm:
Rohre über step.rechner_eingaben und das 3D-Netz (rohr3d.netz, Gravurlinien Art G wie das STEP-Netz ±0,06 mm),
Bleche über blech.aus_step (Zeilen des Blech-Editors).

V1 Rohr: Strich, Rahmen, Schrift aus Strichen, Punkt, über die Ecke, 1 mm tief, nahe am Ende, Seite, Rundrohr längs
   und Punkt: Gravur mit Umriss, im 3D wie in der STEP (Bestand, darf nicht schlechter werden)
V2 Rundrohr mit umlaufender Gravur (Markierungsring 0,6 und 3 mm breit): bleibt Rundrohr, vorher Drehteil
V3 umlaufende Gravur an Rund- und Quadratrohr: Zeile Gravur mit Umriss um den ganzen Umfang, im 3D wie in der
   STEP (vorher ohne Umriss ein kurzer Strich an einer Stelle, bis 60 mm daneben)
V4 Gegenbeispiel: Welle/Buchse mit Einstich bleibt Drehteil
V5 Blech: Gravur oben und unten, Ringgravur (mit Insel), Punkt: Gravur (Länge, Lage, Linien), nie Innenkontur und nie
   im Schneidweg (vorher oben gar nicht erkannt, unten als geschnittene Innenkontur)
V6 Blech mit echter Bohrung und Gravur: Bohrung bleibt Innenkontur, Gravur bleibt Gravur

Aufruf: python tests/test_gravur_erkennung.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, blech, rohr3d, schneidweg as sw, step  # noqa: E402

TOL = 0.06
T = 0.3             # Gravurtiefe der Testteile [mm]
box = wie.box


def ok(text):
    print("OK:", text)


def rohre():
    re_ = lambda: et.kastenrohr(60, 40, 3, 600, 4.5)  # noqa: E731
    rr = lambda: et.rundrohr(60, 3, 600)  # noqa: E731
    qr = lambda: et.kastenrohr(40, 40, 3, 600, 6)  # noqa: E731
    ring = lambda d, b, x: et.cut(et.zylinder((0, 0, x), (0, 0, 1), d + 2, b),  # noqa: E731
                                  et.zylinder((0, 0, x - 1), (0, 0, 1), d - 2 * T, b + 2))
    s = re_()
    for b in (box(-12, 20 - T, 250, 0.6, 2, 8), box(-6, 20 - T, 250, 0.6, 2, 8), box(-12, 20 - T, 253.7, 6.6, 2, 0.6),
              box(-2, 20 - T, 250, 0.6, 2, 8)):
        s = et.cut(s, b)
    return {
        "R_Strich": et.cut(re_(), box(-10, 20 - T, 200, 0.6, 2, 30)),
        "R_Rahmen": et.cut(re_(), et.cut(box(-10, 20 - T, 300, 20, 2, 10), box(-9, 20 - T - 1, 301, 18, 4, 8))),
        "R_Schrift": s,
        "R_Punkt": et.cut(re_(), et.zylinder((0, 20 - T, 300), (0, 1, 0), 6, 5)),
        "R_1mm": et.cut(re_(), box(-10, 19, 200, 0.6, 2, 30)),
        "R_Ende": et.cut(re_(), box(-10, 20 - T, 3, 0.6, 2, 20)),
        "R_Seite": et.cut(re_(), box(30 - T, -5, 200, 2, 0.6, 20)),
        "RR_laengs": et.cut(rr(), box(-0.3, 30 - T, 200, 0.6, 2, 30)),
        "RR_Punkt": et.cut(rr(), et.zylinder((0, 30 - T, 300), (0, 1, 0), 4, 5)),
        "RR_Ring": et.cut(rr(), ring(60, 0.6, 300)),
        "RR_Ring_breit": et.cut(rr(), ring(60, 3, 300)),
        "QR_Ring": et.cut(qr(), et.cut(box(-25, -25, 300, 50, 50, 0.6),
                                       et.kastenrohr(40 - 2 * T, 40 - 2 * T, 16, 600, 6 - T))),
    }


RINGE = ("RR_Ring", "RR_Ring_breit", "QR_Ring")


def drehteile():
    welle = et.cut(et.zylinder((0, 0, 0), (0, 0, 1), 30, 80), et.cut(et.zylinder((0, 0, 40), (0, 0, 1), 32, 1.1),
                                                                     et.zylinder((0, 0, 39), (0, 0, 1), 28.6, 3)))
    buchse = et.cut(et.rundrohr(40, 8, 60), et.cut(et.zylinder((0, 0, 30), (0, 0, 1), 42, 1.1),
                                                   et.zylinder((0, 0, 29), (0, 0, 1), 39.2, 3)))
    return {"D_Welle_Einstich": welle, "D_Buchse_Einstich": buchse}


def bleche():
    pl = lambda: box(0, 0, 0, 200, 100, 5)  # noqa: E731
    return {
        # Name: (Teil, Anzahl Gravuren, Innenkonturen)
        "B_oben": (et.cut(pl(), box(20, 20, 5 - T, 30, 0.6, 1)), 1, 0),
        "B_unten": (et.cut(pl(), box(20, 60, -1, 30, 0.6, 1 + T)), 1, 0),
        "B_beide": (et.cut(et.cut(pl(), box(20, 20, 5 - T, 30, 0.6, 1)), box(20, 60, -1, 30, 0.6, 1 + T)), 2, 0),
        "B_Ring": (et.cut(pl(), et.cut(et.zylinder((100, 50, 5 - T), (0, 0, 1), 20, 1),
                                       et.zylinder((100, 50, 4), (0, 0, 1), 18.8, 3))), 2, 0),
        "B_Punkt": (et.cut(pl(), et.zylinder((150, 50, 4.2), (0, 0, 1), 3, 2)), 1, 0),
        "B_Bohrung_und_Gravur": (et.cut(et.cut(pl(), et.zylinder((150, 50, -1), (0, 0, 1), 10, 7)),
                                        box(20, 20, 5 - T, 30, 0.6, 1)), 1, 1),
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        r, d, b = rohre(), drehteile(), bleche()
        alle = dict(r, **d, **{n: s for n, (s, _, _) in b.items()})
        for n, s in alle.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp)] +
                         [str(tmp / (n + ".step")) for n in alle])
        ms = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)}
        assert set(ms) == set(alle), sorted(set(alle) - set(ms))

        fehler = []
        for name in r:
            m = ms[name]
            assert m["profilform"] in ("Rundrohr", "Quadratrohr", "Rechteckrohr"), (name, m["profilform"])
            a_, b_ = float(m["abm_a"]), float(m["abm_b"] or 0) or None
            profil = dict(form=m["profilform"], a=a_, b=b_, wand=float(m["wandstaerke"]), profil_id="X")
            e = step.rechner_eingaben(m, m["profilform"], a_, b_)
            g = [z for z in e["konturen"] if z["art"] == sw.GRAVUR]
            assert g and all(z.get("umriss") for z in g), (name, e["konturen"])
            assert not [z for z in e["konturen"] if z["art"] not in sw.GRAVUREN], (name, e["konturen"])
            n = rohr3d.netz(e, profil, float(m["laenge"]))
            sn = ansicht3d.entpacken(m["_netz"])
            mod, st = n["l"].get("G", []), sn["l"].get("G", [])
            weit = max(wie._abstand(mod, st), wie._abstand(st, mod)) - rohr3d.ABSTAND
            print(f"  {name}: {m['profilform']}, {len(g)} Gravur(en), 3D {weit:+.3f} mm")
            if weit > TOL:
                fehler.append(f"{name}: Gravur im 3D {weit:.3f} mm neben der STEP")
        assert not fehler, fehler
        ok("V1 Gravuren an Rohren mit Umriss, im 3D wie in der STEP")
        for name in ("RR_Ring", "RR_Ring_breit"):
            assert ms[name]["profilform"] == "Rundrohr", ms[name]["profilform"]
        ok("V2 Rundrohr mit umlaufender Gravur bleibt Rundrohr (vorher Drehteil)")
        ok("V3 umlaufende Gravur mit Umriss über den ganzen Umfang, im 3D wie in der STEP")
        for name in d:
            assert ms[name]["profilform"] == "Drehteil", (name, ms[name]["profilform"])
        ok("V4 Welle und Buchse mit Einstich bleiben Drehteil")

        for name, (_, n_g, n_i) in b.items():
            m = ms[name]
            assert m["profilform"] == "Blech", (name, m["profilform"])
            bl = step.blech(m) if hasattr(step, "blech") else json.loads(m.get("blech") or "{}")
            e = blech.aus_step(bl, "S235", 1)
            g = [z for z in e["konturen"] if z["art"] == sw.GRAVUR]
            i = [z for z in e["konturen"] if z["art"] not in sw.GRAVUREN]
            print(f"  {name}: {len(g)} Gravur(en) {[z['laenge'] for z in g]}, {len(i)} Innenkontur(en), "
                  f"innen {m['innen_konturen']}, Gravur {float(m['gravur']):.1f} mm")
            assert len(g) == n_g and len(i) == n_i, (name, e["konturen"])
            assert int(float(m["innen_konturen"])) == n_i, (name, m["innen_konturen"])
            assert all(z.get("linien") and z.get("x") is not None for z in g), g
            assert abs(float(m["gravur"]) - sum(z["laenge"] for z in g)) < 0.5, (name, m["gravur"])
            if name == "B_oben":
                assert abs(g[0]["laenge"] - 61.2) < 0.1 and abs(g[0]["x"] - 35) < 0.05 and abs(g[0]["y"] - 20.3) < 0.05, g
        ok("V5 Gravuren am Blech oben, unten, Ring und Punkt: Gravur, nie Innenkontur")
        ok("V6 echte Bohrung bleibt Innenkontur neben der Gravur")
    print("Alles in Ordnung")


if __name__ == "__main__":
    main()
