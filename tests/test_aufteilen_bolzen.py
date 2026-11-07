"""Aufteilen auch für Bolzen und Gewindestangen (Vorschlag M5, Patrick 07.11.2026): ein angeschweißter Bolzen (Zylinder
rundum, ohne Absatz) macht den Körper gelb „mehrere Teile“, „Aufteilen“ trennt ihn ab (glatt: Drehteil/Rundstahl, kein
Normteil); Schraube = Sechskant + Schaft bleibt ein Teil. Rundungen (nur ein Bogen) und Wellen mit Absatz werden nicht
getrennt.

Aufruf: python tests/test_aufteilen_bolzen.py
"""
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

import step_aufteilen  # noqa: E402
import step_messen  # noqa: E402
from formen_baukasten import gerade_kanten_parallel, plus, prisma, quader, radius, schreibe, verschiebe, zyl  # noqa: E402

from rohrlaser import step  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def sechskant(sw, h, z, x, y):
    r = sw / math.sqrt(3)
    ecken = [(r * math.cos(math.radians(30 + 60 * i)), r * math.sin(math.radians(30 + 60 * i))) for i in range(6)]
    return verschiebe(prisma(ecken, h), x, y, z)


platte_bolzen = plus(quader(120, 60, 10), zyl(6, 40, 10, 30, 30))
teile = step_aufteilen.teilen(platte_bolzen)
assert [n for n, _ in teile] == ["Bolzen Ø12 × 40", "Grundteil"], teile
v = [step_aufteilen._volumen(s) for _, s in teile]
assert abs(v[0] - math.pi * 36 * 40) < 1 and abs(v[1] - 120 * 60 * 10) < 1, v
ok("Platte 120 × 60 × 10 mit Bolzen Ø12 × 40: Bolzen und Platte mit genau ihrem Volumen getrennt")

zwei = step_aufteilen.teilen(plus(quader(120, 60, 10), zyl(6, 40, 10, 30, 30), zyl(6, 40, 10, 90, 30)))
assert [n for n, _ in zwei] == ["Bolzen Ø12 × 40", "Bolzen Ø12 × 40", "Grundteil"], zwei
schraube = step_aufteilen.teilen(plus(quader(120, 60, 10), sechskant(19, 8, 40, 30, 30), zyl(6, 30, 10, 30, 30)))
assert [n for n, _ in schraube] == ["Schraube SW 19", "Grundteil"], schraube
assert abs(step_aufteilen._volumen(schraube[1][1]) - 120 * 60 * 10) < 1
ok("Zwei Bolzen: beide abgetrennt; Schraube (Sechskant + Schaft) bleibt ein Teil")

welle = plus(zyl(10, 50), zyl(15, 20, 50))
assert step_aufteilen.teilen(welle) == [], "Welle mit Absatz: ein Drehteil"
assert step_aufteilen.teilen(zyl(10, 50)) == [] and step_aufteilen.teilen(quader(100, 40, 10)) == []
gerundet = radius(quader(100, 40, 10), gerade_kanten_parallel((0, 0, 1)), 5)    # vier Ecken R5 (je ein Viertelbogen)
assert step_aufteilen._zylinder_gruppen(__import__("step_drehfraes").flaechen(gerundet)) == []
assert step_aufteilen.teilen(gerundet) == [], "Rundungen sind keine Bolzen"
ronde = zyl(100, 5)
assert step_aufteilen.bolzen(__import__("step_drehfraes").flaechen(ronde)) == [], "Ronde Ø200 × 5 ist eine Scheibe"
ok("Welle mit Absatz, Rundstahl allein, glatte Platte, Platte mit gerundeten Ecken, Ronde: nichts zu trennen")

schreibe({"Halter_Bolzen": platte_bolzen, "Welle": welle}, TMP)
aus = TMP / "m.txt"
step_messen.main(["--ausgabe", str(aus), str(TMP / "Halter_Bolzen.step"), str(TMP / "Welle.step")])
je = {Path(m["datei"]).stem: m for m in step.lies_messwerte(aus)}
assert step.MEHRTEILIG_HINWEIS in je["Halter_Bolzen"]["hinweise"] and "Bolzen Ø12" in je["Halter_Bolzen"]["hinweise"]
assert step.MEHRTEILIG_HINWEIS not in (je["Welle"].get("hinweise") or "")
ok("Messung: Platte mit Bolzen gelb „Mehrere Teile in einem Körper? Bolzen Ø12 …“, Welle mit Absatz nicht")

m = dict(je["Halter_Bolzen"], _pfad=str(TMP / "Halter_Bolzen.step"))
t = Path(tempfile.mkdtemp())
step_messen.main(["--ausgabe", str(t / "a.txt"), "--netze", str(t / "netze"), "--aufteilen",
                  str(int(float(m["koerper"]))), m["_pfad"]])
neu = step.aufteilen_ergebnis(m, t / "a.txt", t / "netze")
assert [n["bauteil"].split(" – ")[-1] for n in neu] == ["Bolzen Ø12 × 40", "Grundteil"], [n["bauteil"] for n in neu]
bolzen, grund = neu
assert not bolzen.get("_normteil"), "glatter Bolzen: kein Normteil"
assert bolzen.get("profilform") in ("Rundstahl", "Drehteil"), bolzen.get("profilform")
assert grund.get("profilform") in ("Blech", "Flachstahl") and step.MEHRTEILIG_HINWEIS not in (grund.get("hinweise") or "")
ok(f"--aufteilen: Bolzen als {bolzen['profilform']} (kein Normteil), Grundteil als {grund['profilform']}")
print("Aufteilen Bolzen: alle Tests bestanden.")
