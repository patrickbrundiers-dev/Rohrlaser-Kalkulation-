"""Regressionstests der STEP-Messung: Fälle, die früher falsch gemessen wurden (Teile in tests/step_regression).

- R01/R02: Flächen als Freiformflächen (B-Spline). Früher: Achse falsch, Außenmantel als Schnittkontur gerechnet
  (R01 als „Sonderprofil“ mit 60 mm Länge) bzw. Messung hing (R02).
- R03/R04: Kastenrohr um die eigene Achse gedreht. Früher: Breite/Höhe aus einer achsparallelen Hüllbox, also zu groß.
- R05: Teil T07 (Bohrungen, Ausschnitt, Gravur, Ausklinkung) als Freiformflächen, gedreht und verschoben.
- R06: Körper 13 aus Patricks Baugruppe 00_Rahmengestell (22.10.2026): RE 40x30x3 mit je zwei gegenüberliegenden
  Langlöchern 30x9, drei von sieben Lageschnitten zerfallen in zwei Wandstücke gleicher Fläche. Früher: Netto-Fläche
  ≈ 0, Schwerpunkt weit außerhalb, Achse gekippt -> „Kein Profilquerschnitt gefunden“ (nicht übernehmbar).

Sollwerte sind aus den Konstruktionsmaßen in tests/erzeuge_testteile.py berechnet, nicht aus einer Messung.
Aufruf: python tests/test_step_regression.py
"""
import math
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from step_geometrie import analysiere_datei, gewinde_vorschlag, konturklassen  # noqa: E402

ORDNER = HIER / "step_regression"
pi = math.pi


def kasten(b, h, t, r):
    """Querschnittsfläche und Außenumfang eines Kastenprofils mit Außenradius r (Innenradius r - t)."""
    ri = max(r - t, 0)
    fl = (b * h - (4 - pi) * r * r) - ((b - 2 * t) * (h - 2 * t) - (4 - pi) * ri * ri)
    return fl, 2 * (b + h) - 8 * r + 2 * pi * r


re_fl, re_u = kasten(60, 40, 2, 4)
qr2_fl, qr2_u = kasten(40, 40, 2, 3)
qr3_fl, qr3_u = kasten(40, 40, 3, 6)
rr_fl, rr_u = pi / 4 * (42.4 ** 2 - 38.4 ** 2), pi * 42.4
re43_fl, re43_u = kasten(40, 30, 3, 4)
re43_fl += (4 - pi) * (1.5 ** 2 - 1 ** 2)                    # Innenradius in der Kundendatei 1,5 statt r - t = 1
r06_innen = 6 * pi * 6.8 + 4 * (2 * (30 - 9) + pi * 9)      # 6 Bohrungen Ø6,8, 4 Langlöcher 30x9

SOLL = {  # Profilform, A, B, Wand, Fläche, Länge, Schneidweg, Konturen
    "R01_RE60x40x2_L1000_Freiform": ("Rechteckrohr", 60, 40, 2, re_fl, 1000, 2 * re_u, 2),
    "R02_RR42-4x2_L1000_Freiform": ("Rundrohr", 42.4, 0, 2, rr_fl, 1000, 2 * rr_u, 2),
    "R03_RE60x40x2_L1000_gedreht": ("Rechteckrohr", 60, 40, 2, re_fl, 1000, 2 * re_u, 2),
    "R04_QR40x2_L800_45Grad": ("Quadratrohr", 40, 0, 2, qr2_fl, 800, 2 * qr2_u, 2),
    "R05_QR40x3_L1000_Merkmale_Freiform": ("Quadratrohr", 40, 0, 3, qr3_fl, 1000,
                                           2 * qr3_u + 30 + 4 * pi * 5 + 60, 7),
    "R06_RE40x30x3_L920_Langloecher": ("Rechteckrohr", 40, 30, 3, re43_fl, 920, 2 * re43_u + r06_innen, 12),
}
ZEIT_MAX = 60  # s je Datei; früher hing die Messung bei R02


def nah(ist, soll, tol, was, name):
    assert abs(ist - soll) <= tol, f"{name}: {was} ist {ist:.3f}, soll {soll:.3f}"


fehler = 0
for name, (form, a, b, w, fl, lg, sw, k) in SOLL.items():
    t0 = time.time()
    teile = analysiere_datei(ORDNER / f"{name}.step")
    dauer = time.time() - t0
    try:
        assert len(teile) == 1, f"{name}: {len(teile)} Körper"
        t = teile[0]
        assert not t.hinweise, f"{name}: Hinweise {t.hinweise}"
        assert t.profilform == form, f"{name}: Profilform {t.profilform!r}"
        nah(t.abm_a, a, 0.01, "Abm. A", name)
        nah(t.abm_b, b, 0.01, "Abm. B", name)
        nah(t.wandstaerke, w, 0.01, "Wandstärke", name)
        nah(t.flaeche, fl, 0.5, "Fläche", name)
        nah(t.laenge, lg, 0.01, "Länge", name)
        nah(t.schneidweg, sw, 0.05, "Schneidweg", name)
        assert t.konturen == k, f"{name}: Konturen {t.konturen}, soll {k}"
        if name.startswith("R05"):
            nah(t.ende_b, qr3_u + 30, 0.05, "Endschnitt", name)
            nah(t.innen, 4 * pi * 5 + 60, 0.05, "Innenkonturen", name)
            nah(t.gravur, 2 * (24 + 5), 0.05, "Gravur", name)
            assert t.ende_a_gerade and not t.ende_b_gerade, "R05: Enden"
            assert gewinde_vorschlag(t.bohrungen) == "4xM6", f"R05: Bohrungen {t.bohrungen}"
            kl = konturklassen(t.innen_liste)
            assert kl["klein"][0] == 4 and kl["mittel"][0] == 1, kl
        elif name.startswith("R06"):
            nah(t.innen, r06_innen, 0.05, "Innenkonturen", name)
            assert t.ende_a_gerade and t.ende_b_gerade and t.pruefstatus == "plausibel", f"{name}: {t.pruefstatus}"
            assert t.bohrungen == {6.8: 6}, f"{name}: Bohrungen {t.bohrungen}"
        else:
            assert t.ende_a_gerade and t.ende_b_gerade and t.innen == 0 and t.gravur == 0, \
                f"{name}: Enden/Innen {t.ende_a_gerade}/{t.ende_b_gerade}/{t.innen}/{t.gravur}"
        assert dauer < ZEIT_MAX, f"{name}: Messung dauerte {dauer:.0f} s"
        print(f"OK     {name} ({dauer:.1f} s)")
    except AssertionError as e:
        fehler += 1
        print(f"FEHLER {e}")

sys.exit(1 if fehler else 0)
