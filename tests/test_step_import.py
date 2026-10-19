"""Prüft die STEP-Messwerte gegen analytisch berechnete Sollwerte.

Aufruf: python tests/test_step_import.py   (erzeugt die Testteile bei Bedarf)
"""
import math
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from step_geometrie import analysiere_datei, gewinde_vorschlag, konturklassen  # noqa: E402

STEP = HIER / "step"
if not (STEP / "T07_QR40x3_L1000_Gewinde_Gravur.step").exists():
    subprocess.run([sys.executable, str(HIER / "erzeuge_testteile.py")], check=True, capture_output=True)

pi = math.pi
qr_umfang = 4 * (40 - 12) + 2 * pi * 6
SOLL = {  # Profilform, A, B, t, Fläche, Länge, Schneidweg, Konturen
    "T01_RR42-4x2_L1250": ("Rundrohr", 42.4, 0, 2.0, pi / 4 * (42.4**2 - 38.4**2), 1250, 2 * pi * 42.4, 2),
    "T02_RR42-4x2_L860_Bohrung": ("Rundrohr", 42.4, 0, 2.0, pi / 4 * (42.4**2 - 38.4**2), 860, None, 4),
    "T03_QR40x3_L2150_Bohrung": ("Quadratrohr", 40, 0, 3.0, (1600 - (4 - pi) * 36) - (34**2 - (4 - pi) * 9),
                                 2150, 2 * qr_umfang + 8 * pi, 3),
    "T04_RE60x40x3_Gehrung": ("Rechteckrohr", 60, 40, 3.0, 60 * 40 - 54 * 34, 1825.5,
                              200 + 2 * 40 + 2 * 60 * math.sqrt(2), 2),
    "T05_RR33-7x2-6_L500": ("Rundrohr", 33.7, 0, 2.6, pi / 4 * (33.7**2 - 28.5**2), 500, 2 * pi * 33.7, 2),
    "T06_QR40x3_L1000_Langloch": ("Quadratrohr", 40, 0, 3.0, (1600 - (4 - pi) * 36) - (34**2 - (4 - pi) * 9),
                                  1000, 2 * qr_umfang + 2 * (800 + 20), 3),
    # 4xØ5 (M6), Ausschnitt 10x20, Ausklinkung am Ende B (+2x15), Gravur 24x5 separat
    "T07_QR40x3_L1000_Gewinde_Gravur": ("Quadratrohr", 40, 0, 3.0, (1600 - (4 - pi) * 36) - (34**2 - (4 - pi) * 9),
                                        1000, 2 * qr_umfang + 30 + 4 * pi * 5 + 60, 7),
}


def nah(ist, soll, tol, was, name):
    assert abs(ist - soll) <= tol, f"{name}: {was} ist {ist:.3f}, soll {soll:.3f}"


fehler = 0
for name, (form, a, b, t, fl, l, sw, k) in SOLL.items():
    teil = analysiere_datei(STEP / f"{name}.step")[0]
    try:
        assert teil.profilform == form, f"{name}: Profilform {teil.profilform}"
        nah(teil.abm_a, a, 0.01, "Abm. A", name)
        nah(teil.abm_b, b, 0.01, "Abm. B", name)
        nah(teil.wandstaerke, t, 0.01, "Wandstärke", name)
        nah(teil.flaeche, fl, 0.5, "Fläche", name)
        nah(teil.laenge, l, 0.01, "Länge", name)
        if sw is None:  # Querbohrung Ø10 durch beide Wände: Sattelkurve etwas länger als 2·π·10
            sw = 2 * pi * 42.4
            assert 2 * pi * 10 < teil.schneidweg - sw < 2 * pi * 10 * 1.03, f"{name}: Schneidweg {teil.schneidweg:.2f}"
        else:
            nah(teil.schneidweg, sw, 0.05, "Schneidweg", name)
        assert teil.konturen == k, f"{name}: Konturen {teil.konturen}, soll {k}"
        nah(teil.ende_a + teil.ende_b + teil.innen, teil.schneidweg, 0.01, "Summe Enden+innen", name)
        gerade_b = not name.startswith(("T04", "T07"))  # T04 Gehrung, T07 Ausklinkung
        assert teil.ende_a_gerade and teil.ende_b_gerade == gerade_b, f"{name}: Enden gerade {teil.ende_a_gerade}/{teil.ende_b_gerade}"
        if name.startswith("T07"):
            nah(teil.ende_b, qr_umfang + 30, 0.05, "Endschnitt", name)
            nah(teil.innen, 4 * pi * 5 + 60, 0.05, "Innenkonturen", name)
            nah(teil.gravur, 2 * (24 + 5), 0.05, "Gravur", name)
            assert teil.gravur_konturen == 1 and teil.innen_konturen == 5
            assert gewinde_vorschlag(teil.bohrungen) == "4xM6", gewinde_vorschlag(teil.bohrungen)
            kl = konturklassen(teil.innen_liste)  # 4x Ø5 klein, Ausschnitt 10x20 mittel
            assert kl["klein"][0] == 4 and kl["mittel"][0] == 1 and kl["gross"][0] == 0, kl
            nah(kl["klein"][1], 4 * pi * 5, 0.05, "Kontur klein", name)
            nah(kl["mittel"][1], 60, 0.05, "Kontur mittel", name)
        else:
            assert teil.gravur == 0, f"{name}: Gravur {teil.gravur}"
        if name.startswith("T06"):
            assert konturklassen(teil.innen_liste)["gross"][0] == 1, "Langloch muss groß sein"
        if name.startswith("T02"):
            assert konturklassen(teil.innen_liste)["klein"][0] == 2, "Ø10 auf der Grenze muss klein sein"
        print(f"OK     {name}")
    except AssertionError as e:
        fehler += 1
        print(f"FEHLER {e}")

sys.exit(1 if fehler else 0)
