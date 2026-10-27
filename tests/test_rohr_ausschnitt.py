"""Rohr mit großem Ausschnitt (Patrick 27.10.2026, nach 0.9.156: „Wird nicht als Rundrohr erkannt“): Rundrohr Ø48,
308 mm lang, fast über die ganze Länge zur Hälfte offen (Kerben am Rand), und ein kurzes Rundrohr mit Sattel und
Längsschlitz. Die Enden sind in der STEP als ganze Ringe gezeichnet, der Ausschnitt liegt dazwischen.

Fehler: die Querflächen am Rand des Ausschnitts (kurz vor dem Ende) galten als zweites Rohrende, die Enden „nicht in
einer Ebene“ – das Teil blieb offenes Sonderprofil. Jetzt: Rundrohr, Ausschnitt als Innenkontur genau wie gezeichnet;
Ringe aus der STEP werden nicht auf 2 mm verbreitert (auch Quadrat-/Rechteckrohr), es wird nichts ergänzt.

Aufruf: python tests/test_rohr_ausschnitt.py
"""
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402
from erzeuge_testteile import cut, kastenrohr, rundrohr, schreibe, zylinder  # noqa: E402
import step_geometrie as g  # noqa: E402

tmp = Path(tempfile.mkdtemp())


def box(x0, y0, z0, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), dx, dy, dz).Shape()


def rr48_kerben():
    t = cut(rundrohr(48, 1.5, 308), box(-30, 0, 2, 60, 30, 304))
    for z in (60, 150, 240):
        t = cut(t, box(-30, -3, z, 60, 3.5, 20))
    return t


def rr60_sattel():
    t = cut(rundrohr(60, 2, 100), zylinder((0, 60, 40), (0, -1, 0), 50, 60))     # Sattel quer
    return cut(t, box(-20, 0, 2, 40, 40, 96))                                       # Längsschlitz bis kurz vor die Enden


TEILE = {
    "A_rr48_kerben": rr48_kerben(),
    "B_rr60_sattel": rr60_sattel(),
    "C_rr48_ring1": cut(rundrohr(48, 1.5, 308), box(-30, 0, 1, 60, 30, 306)),
    "D_qr40_ring1": cut(kastenrohr(40, 40, 2, 300, 4), box(-15, 10, 1, 30, 20, 298)),
}
for name, form in TEILE.items():
    schreibe(form, name, tmp)
ERG = {name: g.analysiere_datei(str(tmp / f"{name}.step"), netz=True)[0] for name in TEILE}
fehler = 0


def fall(text, fn):
    global fehler
    try:
        fn()
        print(f"OK     {text}")
    except AssertionError as e:
        fehler += 1
        print(f"FEHLER {text}: {e}")


def wie_step(name, form, laenge, wand):
    t = ERG[name]
    z = t.geschlossen
    assert z is not None and z.profilform == form, (name, t.profilform, t.hinweise)
    assert abs(z.laenge - laenge) < 0.01 and abs(z.wandstaerke - wand) < 0.01, (name, z.laenge, z.wandstaerke)
    assert z.offene_seite.get("ringe_step") and z.sicherheit["offene_seite"] == "stege", (name, z.offene_seite)
    # nichts ergänzt: gelasert = gezeichnet
    assert abs(z.volumen - t.volumen) < 1e-3 * t.volumen, (name, z.volumen, t.volumen)
    assert any("Enden in der STEP geschlossen" in h for h in z.hinweise), z.hinweise
    assert not any("Ring 2 mm" in h for h in z.hinweise), z.hinweise
    return z


def rund_kerben():
    z = wie_step("A_rr48_kerben", "Rundrohr", 308, 1.5)
    assert z.abm_a in (48.0, 48.3), z.abm_a
    # Ausschnitt: 2 × 304 längs + 2 Halbkreise außen + 6 Kerben (je 2 × 3 mm Tiefe an beiden Rändern)
    lg = max(lg for _, lg in z.innen_liste)
    soll = 2 * 304 + 2 * math.pi * 24 + 6 * 2 * 3
    assert len(z.innen_liste) == 1 and abs(lg - soll) < 3, (z.innen_liste, soll)


def rund_sattel():
    z = wie_step("B_rr60_sattel", "Rundrohr", 100, 2)
    assert len(z.innen_liste) == 1 and z.innen_liste[0][0] > 90, z.innen_liste


def ring_schmal():
    z = wie_step("C_rr48_ring1", "Rundrohr", 308, 1.5)
    assert abs(z.innen_liste[0][0] - 306) < 0.05, z.innen_liste     # Ring 1 mm wie gezeichnet, nicht 2 mm
    z = wie_step("D_qr40_ring1", "Quadratrohr", 300, 2)
    assert abs(z.innen_liste[0][0] - 298) < 0.05, z.innen_liste


fall("Rundrohr Ø48 × 308 halb offen mit Kerben, Enden als Ringe gezeichnet -> Rundrohr, Ausschnitt als Kontur", rund_kerben)
fall("kurzes Rundrohr mit Sattel und Längsschlitz -> Rundrohr", rund_sattel)
fall("Ring 1 mm in der STEP bleibt 1 mm (Rund- und Quadratrohr), nichts ergänzt", ring_schmal)

print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
sys.exit(1 if fehler else 0)
