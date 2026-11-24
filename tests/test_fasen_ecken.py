"""Verbesserungsplan 06.11.2026, Paket 1 (A2, A3): Querschnitt und Zuschnitt wie in der STEP.

A2 Flachstahl mit Längsfasen (Baggerschaufel „VOLVO EC 750 DL BUCKET“, Schneidkante 640 × 80 mit Fase 70 × 40):
   bis 0.9.266 galt jeder Querschnitt mit mindestens 97 % der Rechteckfläche als Flachstahl, die Fasen fielen weg und
   der Editor zeigte ein Rechteck. Jetzt: Hinweis „Querschnitt mit Längsfasen“ mit den Maßen, Profil unsicher (Ampel
   gelb), Querschnitt in Skizze und 3D wie gemessen (Eingabe querschnitt_step).
   F1 Flachstahl 120 × 20 × 1500 mit Fase 10 × 10, F2 ohne Fase (bleibt Rechteck, kein Hinweis).
A3 Zuschnitt mit kleinen Ecken (roof.stp Körper 2, Kantteil 380 × 206 mit Ecken R5/R10): die Fläche wich nur 0,07 %
   vom Hüllrechteck ab, der Zuschnitt galt als Rechteck und der Schneidweg im Blech-Editor lag 1 % über der STEP.
   Jetzt gilt er nur als Rechteck, wenn auch der Umfang passt (UMFANG_RECHTECK_TOL).
   B1 Winkel 100 × 50 × 3 (r 3), Länge 300, zwei Ecken des Zuschnitts R10; B2 ebenes Blech 300 × 200 × 3 mit vier
   Ecken R5. Der Schneidweg des Editors ohne Messwerte (nur aus der Kontur) muss der STEP entsprechen.

Aufruf: python tests/test_fasen_ecken.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_geometrie  # noqa: E402
import step_messen  # noqa: E402
from rohrlaser import blech, skizze, step  # noqa: E402
from rohrlaser.schneidweg import mit_radius  # noqa: E402


def box(x, y, z, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def ecke_rund(s, x, y0, dy, z, r, sx, sz):
    """Ecke des Zuschnitts bei (x, z) mit Radius r runden (sx, sz: Richtung ins Teil, ±1), Dicke y0 … y0 + dy."""
    x0, z0 = (x if sx > 0 else x - r), (z if sz > 0 else z - r)
    weg = box(x0, y0 - 1, z0, r, dy + 2, r)
    zyl = et.zylinder((x + sx * r, y0 - 1, z + sz * r), (0, 1, 0), 2 * r, dy + 2)
    return et.cut(s, et.cut(weg, zyl))


def teile():
    f = {"F1_Fase": et.profil([(0, 0), (120, 0), (120, 10), (110, 20), (0, 20)], 1500),
         "F2_ohne_Fase": et.profil([(0, 0), (120, 0), (120, 20), (0, 20)], 1500)}
    w = et.profil([(0, 0), (100, 0), (100, 3), (3, 3), (3, 50), (0, 50)], 300, {(0, 0): 6, (3, 3): 3})
    w = ecke_rund(w, 100, 0, 3, 0, 10, -1, 1)
    f["B1_Winkel_Ecken_R10"] = ecke_rund(w, 100, 0, 3, 300, 10, -1, -1)
    b = box(0, 0, 0, 300, 3, 200)
    for x, z, sx, sz in ((0, 0, 1, 1), (300, 0, -1, 1), (0, 200, 1, -1), (300, 200, -1, -1)):
        b = ecke_rund(b, x, 0, 3, z, 5, sx, sz)
    f["B2_Blech_Ecken_R5"] = b
    return f


def main():
    fehler = 0

    def pruefen(bed, text):
        nonlocal fehler
        print(("OK     " if bed else "FEHLER ") + text)
        fehler += not bed

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        f = teile()
        for n, s in f.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv")] + [str(tmp / (n + ".step")) for n in f])
        ms = {Path(m["datei"]).stem: m for m in step.lies_messwerte(tmp / "r.csv")}
        assert set(ms) == set(f), sorted(ms)

        m = ms["F1_Fase"]
        pruefen(m["profilform"] == "Flachstahl" and abs(float(m["abm_a"]) - 120) < 0.05,
                f"F1 Flachstahl 120 × 20 ({m['profilform']} {m['abm_a']})")
        pruefen(step_geometrie.LAENGSFASEN_TEXT + "10 × 10 mm" in m["hinweise"],
                f"F1 Hinweis Fase 10 × 10: {m['hinweise']}")
        stufe, gruende = step.ampel(m)
        pruefen(stufe == "gelb" and any("Profil" in g for g in gruende), f"F1 Ampel gelb: {stufe} {gruende}")
        e = step.rechner_eingaben(m, "Flachstahl", 120, 20)
        q = (e or {}).get("querschnitt_step")
        pruefen(q is not None and len(q) == 5, f"F1 Querschnitt der STEP im Editor: {q}")
        if q:
            us, vs = [p[0] for p in q], [p[1] for p in q]
            pruefen(abs(max(us) - min(us) - 120) < 0.05 and abs(max(vs) - min(vs) - 20) < 0.05,
                    "F1 Querschnitt 120 × 20 um die Mitte")
            # die Fase: eine Kante schräg mit den Schenkeln 10 und 10
            schraeg = [(abs(q[i][0] - q[i - 1][0]), abs(q[i][1] - q[i - 1][1])) for i in range(len(q))
                       if abs(q[i][0] - q[i - 1][0]) > 0.05 and abs(q[i][1] - q[i - 1][1]) > 0.05]
            pruefen(len(schraeg) == 1 and sorted(round(x, 1) for x in schraeg[0]) == [10.0, 10.0],
                    f"F1 Fase 10 × 10 im Querschnitt: {schraeg}")
            prof = dict(form="Flachstahl", a=120, wand=20)
            mp = e["querschnitt_step_profil"]
            pruefen(skizze.Querschnitt(mit_radius(prof, e)).umriss[0] == [tuple(p) for p in q],
                    f"F1 Skizze/3D mit dem gemessenen Querschnitt ({mp})")
            pruefen(len(skizze.Querschnitt(mit_radius(dict(form="Flachstahl", a=120, wand=25), e)).umriss[0]) == 4,
                    "F1 anderes Profil gewählt: wieder Rechteck")
            pruefen(len(skizze.Querschnitt(prof).flaechen) == 4, "F1 Flächen für Konturen bleiben die vier Seiten")

        m = ms["F2_ohne_Fase"]
        e = step.rechner_eingaben(m, "Flachstahl", 120, 20) or {}
        pruefen(m["profilform"] == "Flachstahl" and "Längsfasen" not in m["hinweise"] and
                "querschnitt_step" not in e, "F2 Flachstahl ohne Fase: Rechteck, kein Hinweis")

        for name in ("B1_Winkel_Ecken_R10", "B2_Blech_Ecken_R5"):
            m = ms[name]
            b = step.blech(m) if hasattr(step, "blech") else None
            if b is None:
                import json
                b = json.loads(m["blech"])
            pruefen(len(b.get("aussen_punkte") or ()) > 4, f"{name}: Zuschnitt mit gerundeten Ecken als Polygon")
            ed = blech.aus_step(b, 1)
            ed.pop("messung", None)         # Editor rechnet nur aus der Kontur
            erg = blech.rechnen(ed, {1: dict(id=1, dichte=7.85, kategorie="Stahl", preis_kg=1)}, [], {})
            sw, sw_step = erg.get("schneidweg") or 0.0, float(m["schneidweg"])
            pruefen(abs(sw - sw_step) <= 0.002 * sw_step,
                    f"{name}: Schneidweg Editor {sw:.1f} mm = STEP {sw_step:.1f} mm ({(sw / sw_step - 1) * 100:+.2f} %)")
            rechteck = 2 * (float(ed["laenge"]) + float(ed["breite"]))
            pruefen(sw_step < rechteck - 1, f"{name}: kürzer als das Hüllrechteck ({rechteck:.1f} mm)")
    print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
    return fehler


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
