"""Prüft Messwerte und Import gegen analytisch berechnete Sollwerte.

Aufruf: python tests/test_step_import.py   (erzeugt die Testteile bei Bedarf)
"""
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "tools"))
from step_geometrie import analysiere_datei  # noqa: E402
from step_import import importiere  # noqa: E402

STEP = HIER / "step"
if not (STEP / "T05_RR33-7x2-6_L500.step").exists():
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
        gerade_b = not name.startswith("T04")  # nur T04 hat eine Gehrung
        assert teil.ende_a_gerade and teil.ende_b_gerade == gerade_b, f"{name}: Enden gerade {teil.ende_a_gerade}/{teil.ende_b_gerade}"
        print(f"OK     {name}")
    except AssertionError as e:
        fehler += 1
        print(f"FEHLER {e}")

# Import in eine Kopie der Mappe
with tempfile.TemporaryDirectory() as d:
    m = Path(d) / "m.xlsx"
    shutil.copy(HIER.parent / "mappe" / "Rohrlaser_Kalkulation_v01.xlsx", m)
    erg = importiere(m, [STEP], werkstoff="S235-10219", stueck=5)
    zeilen = [z for _, z, _ in erg]
    assert zeilen == [18, 19, 20, 21, 22], zeilen
    t05 = [i for a_, _, i in erg if a_.startswith("T05")][0]
    assert "Profil fehlt" in t05, t05
    erg2 = importiere(m, [STEP])
    assert all(z is None for _, z, _ in erg2), "Doppelimport nicht verhindert"
    shutil.copy(HIER.parent / "mappe" / "Rohrlaser_Kalkulation_v01.xlsx", m)
    erg3 = importiere(m, [STEP / "T05_RR33-7x2-6_L500.step"], neue_profile=True)
    assert "neu in Stammdaten" in erg3[0][2], erg3
    from openpyxl import load_workbook
    wb = load_workbook(m)
    assert wb["Profile"]["A10"].value == "RR 33,7x2,6", wb["Profile"]["A10"].value
    assert wb["Auftrag"]["D18"].value == "RR 33,7x2,6"
    assert wb["Auftrag"]["Y18"].value == "ja" and abs(wb["Auftrag"]["Z18"].value - 105.9) < 0.05
    print("OK     Import, Doppelimport-Sperre, Profil anlegen")

sys.exit(1 if fehler else 0)
