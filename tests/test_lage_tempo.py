"""Lageabgleich gleicher Körper schneller (Patrick 06.11.2026 „langsamer Import“, Pizzaofen: 173 gleiche Schrauben,
als Satz/Schweißbaugruppe 34 von 43 Minuten im Lageabgleich).

Vorher: für jede gedrehte Kopie 61 Drehungen mit je 400 Punkten voll ausgewertet, Raster 2 mm (bei einer Schraube
Ø6,5 × 8 mit 1.900 Netzpunkten ~40 Punkte je Zelle). Jetzt: aussichtslose Drehungen brechen ab, sobald sie nicht
mehr gewinnen können, dichte Netze bekommen ein feineres Raster, gleiche Paare (Muster, eigenes Netz) werden nur
einmal gesucht. Die gefundene Lage ist dieselbe (geprüft gegen den alten Ablauf, unten nachgebaut).

Aufruf: python tests/test_lage_tempo.py
"""
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))

from rohrlaser import lage_abgleich as la  # noqa: E402
from rohrlaser.steckverbindung import lage_drehen  # noqa: E402


def alt_passende_lage(netz_muster, netz_k):
    """Der Ablauf vor dem 06.11.2026 (Raster 2 mm, alle Drehungen voll, ohne Merker)."""
    def raster(punkte):
        z = {}
        for q in punkte:
            z.setdefault(tuple(int(math.floor(c / 2.0)) for c in q), []).append(q)
        return z

    def abstand(z, q):
        k = [int(math.floor(c / 2.0)) for c in q]
        best = 25.0
        for ring in range(4):
            if ring and best <= ((ring - 1) * 2.0) ** 2:
                break
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    for dz in range(-ring, ring + 1):
                        if max(abs(dx), abs(dy), abs(dz)) != ring:
                            continue
                        for t in z.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                            best = min(best, (t[0] - q[0]) ** 2 + (t[1] - q[1]) ** 2 + (t[2] - q[2]) ** 2)
        return math.sqrt(best)

    def abw(pm, lage, z):
        ab = [abstand(z, q) for q in la.in_lage([c for q in la._proben(pm) for c in q], lage)]
        return sum(ab) / max(1, len(ab))
    lage, pm, pk = netz_k["lage"], netz_muster["p"], netz_k["p"]
    z = raster(la.in_lage(pk, lage))
    vorher = abw(pm, lage, z)
    if vorher <= la.GUT:
        return lage
    laenge = max(pm[2::3])
    beste = (vorher, lage)
    for wenden in (False, True):
        for d in range(0, 360, 15):
            k = lage_drehen(lage, float(d), wenden, laenge)
            a = abw(pm, k, z)
            if a < beste[0] - 1e-9:
                beste = (a, k)
    for schritt in (5.0, 1.0, 0.2):
        start = beste[1]
        for i in (-2, -1, 1, 2):
            k = lage_drehen(start, i * schritt, False, laenge)
            a = abw(pm, k, z)
            if a < beste[0] - 1e-9:
                beste = (a, k)
    if beste[0] < vorher * 0.5:
        return [round(float(c), 9) for c in beste[1]]
    return lage


def schraube(n=1200):
    """Punkte einer kleinen Schraube (Kopf Ø6,5 mit Schlitz, Schaft Ø4 bis 8 mm) im Rohrsystem, dicht."""
    rnd = random.Random(7)
    p = []
    for _ in range(n):
        z = rnd.uniform(0, 8)
        r = 3.25 if z < 2.5 else 2.0
        w = rnd.uniform(0, 2 * math.pi)
        if z < 1.0 and abs(math.sin(w)) < 0.15:          # Schlitz im Kopf: nicht drehsymmetrisch
            continue
        p += [r * math.cos(w), r * math.sin(w), z]
    return [round(c, 4) for c in p]


def gedreht(p, d, wenden, laenge):
    """Dieselben Punkte, wie sie ein um d gedrehter (und gewendeter) Körper in seinem Rohrsystem misst."""
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    out = []
    for i in range(0, len(p), 3):
        x, y, z = p[i:i + 3]
        if wenden:
            x, z = -x, laenge - z
        out += [round(c * x + s * y, 4), round(-s * x + c * y, 4), z]
    return out


def main():
    fehler = 0
    pm = schraube()
    muster = dict(p=pm, lage=[0, 0, 0, 0, 0, 1, 1, 0, 0])
    faelle = []
    for j, (d, w) in enumerate([(0, False), (30, False), (90, False), (200, True), (45, True), (30, False)] * 2):
        ex = (math.cos(j), math.sin(j), 0.0)
        lage = [100.0 * j, 5.0, -3.0, 0.0, 0.0, 1.0] + list(ex)
        faelle.append(dict(p=gedreht(pm, d, w, 8.0), lage=lage))
    la._GEFUNDEN.clear()
    t = time.time()
    neu = [la.passende_lage(muster, k)[0] for k in faelle]
    t_neu = time.time() - t
    t = time.time()
    alt = [alt_passende_lage(muster, k) for k in faelle]
    t_alt = time.time() - t
    gleich = sum(a == b for a, b in zip(neu, alt))
    if gleich != len(faelle):
        fehler += 1
        print(f"FEHLER Lage anders als vorher bei {len(faelle) - gleich} von {len(faelle)} Kopien")
    else:
        print(f"OK     {len(faelle)} gedrehte/gewendete Kopien: Lage wie vorher")
    if len(la._GEFUNDEN) != 5:
        fehler += 1
        print(f"FEHLER gleiche Paare nicht gemerkt: {len(la._GEFUNDEN)} Suchen statt 5")
    else:
        print(f"OK     gleiche Kopien nur einmal gesucht (5 statt {len(faelle)} Suchen)")
    if t_neu * 3 > t_alt:
        fehler += 1
        print(f"FEHLER nicht schneller: neu {t_neu:.1f} s, vorher {t_alt:.1f} s")
    else:
        print(f"OK     schneller: {t_neu:.1f} s statt {t_alt:.1f} s")
    print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
    return fehler


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
