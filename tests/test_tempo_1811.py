"""Supportpaket Patrick 18.11.2026 (Angebot mit 26 Rechteck-/Quadratrohren, viele Konturen): „Übernehmen“ dauerte
83 s, jedes Neuladen (z. B. nach „62 Vorschläge“) bis 49 s. Ursache: die Schneidfolge (dynamik.folge, Leerwege mit
2-opt) wurde für jedes Teil in jeder Kalkulation, im Maschinenvergleich und bei jedem Neuladen neu gesucht (26
Positionen: 468 Mal statt 26), dazu der Abstand Umriss ↔ Grundform der Gegenprobe (step._grundform_abweichung) mit
hypot je Paar. Beschleunigt, Ergebnisse unverändert:

T1 dynamik.folge merkt die Folge je Eingabe (Punkte, Maschine, Länge, Profil, Fenster): gleiche Folge wie ohne
   Merker, zweiter Aufruf rechnet nicht, andere Maschine/Länge/Fenster rechnet neu, Ändern des Ergebnisses ändert den
   Merker nicht
T2 step._grundform_abweichung gleich wie die bisherige Rechnung (hier als Referenz kopiert), Langloch, Rechteck mit
   und ohne Eckradius, zufällige Umrisse
T3 Gegenprobe/3D-Netz: das Profil der Stammdaten (mit Bemerkung, Fläche manuell, Wand max. …) trifft das Netz und die
   Gegenprobe des gemessenen Profils (vor dem Prüfdialog gerechnet) statt alles noch einmal zu rechnen; Maße und
   Außenradius gehören weiter zum Schlüssel

Aufruf: python tests/test_tempo_1811.py
"""
import math
import random
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm")]

from rohrlaser import dynamik, step  # noqa: E402


def ok(text):
    print("OK:", text)


def lagen_zufall(rnd, n):
    return [dict(x=rnd.uniform(0, 2000), eingabe=dict(seite=rnd.choice(["oben", "vorne", "unten", "hinten"])))
            for _ in range(n)]


def t1():
    m = dict(eilgang_x=60000, beschl_x=5, drehzahl=60, beschl_dreh=300, zeit_regelung=0.1)
    rnd = random.Random(18)
    zaehler = {"n": 0}
    orig = dynamik._folge_rechnen

    def zaehlend(*a):
        zaehler["n"] += 1
        return orig(*a)
    dynamik._folge_rechnen = zaehlend
    try:
        for _ in range(20):
            lagen = lagen_zufall(rnd, rnd.randint(3, 40))
            dynamik._FOLGE_MERK.clear()
            ohne = orig(sorted(((float(d["x"]), dynamik.winkel_der_seite(d["eingabe"]["seite"])) for d in lagen),
                               key=lambda t: t[0]), m, 2000, None, None)
            n0 = zaehler["n"]
            a = dynamik.folge(lagen, m, 2000)
            b = dynamik.folge(lagen, dict(m), 2000)
            assert a == ohne and b == ohne, "andere Folge"
            assert zaehler["n"] == n0 + 1, zaehler["n"] - n0
            a.reverse()
            assert dynamik.folge(lagen, m, 2000) == ohne, "Merker verändert"
            dynamik.folge(lagen, dict(m, eilgang_x=30000), 2000)
            dynamik.folge(lagen, m, 2500)
            dynamik.folge(lagen, m, 2000, fenster=100)
            assert zaehler["n"] == n0 + 4, zaehler["n"] - n0
        # mit Kopfweg und Profil: Profil gehört zum Schlüssel
        mk = dict(m, hub_ab_weg=50, hub_z=20, eilgang_z=30000, beschl_z=5)
        lagen = lagen_zufall(rnd, 25)
        n0 = zaehler["n"]
        r1 = dynamik.folge(lagen, mk, 2000, dict(form="Quadratrohr", a=80, b=80, wand=3))
        r2 = dynamik.folge(lagen, mk, 2000, dict(form="Quadratrohr", a=80, b=80, wand=3))
        dynamik.folge(lagen, mk, 2000, dict(form="Quadratrohr", a=100, b=100, wand=3))
        assert r1 == r2 and zaehler["n"] == n0 + 2, zaehler["n"] - n0
    finally:
        dynamik._folge_rechnen = orig
    ok("T1 Schneidfolge je Eingabe gemerkt: gleiche Folge, einmal gerechnet, andere Eingaben neu")


def ref_grundform(umriss, art, lg, br, laengs, schritt=0.5, r=0.0):
    """step._grundform_abweichung bis 0.9.384 (unverändert)."""
    a, b = (lg / 2, br / 2) if laengs else (br / 2, lg / 2)
    pts = [(float(x), float(y)) for x, y in umriss]
    if art == "Langloch" or r > 0:
        r = min(a, b) if art == "Langloch" else min(r, a, b)
        hx, hy = a - r, b - r

        def abst(x, y):
            ux, uy = abs(x) - hx, abs(y) - hy
            if ux > 0 and uy > 0 or art == "Langloch":
                return abs(math.hypot(max(ux, 0.0), max(uy, 0.0)) - r)
            return abs(max(ux, uy) - r)
        n = max(16, int(4 * (hx + hy + math.pi * r / 2) / schritt))
        soll = []
        for i in range(n):
            t = 2 * math.pi * i / n
            cx, cy = math.cos(t), math.sin(t)
            soll.append((math.copysign(hx, cx) + r * cx, math.copysign(hy, cy) + r * cy))
    else:
        def abst(x, y):
            dx, dy = abs(x) - a, abs(y) - b
            return math.hypot(max(dx, 0), max(dy, 0)) if dx > 0 or dy > 0 else -max(dx, dy)
        ecken = [(-a, -b), (a, -b), (a, b), (-a, b)]
        soll = []
        for i, (x0, y0) in enumerate(ecken):
            x1, y1 = ecken[(i + 1) % 4]
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / schritt))
            soll += [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n)]
    hin = max(abst(x, y) for x, y in pts)

    def zum_zug(x, y):
        best = math.inf
        for i, (x0, y0) in enumerate(pts):
            x1, y1 = pts[(i + 1) % len(pts)]
            vx, vy = x1 - x0, y1 - y0
            lq = vx * vx + vy * vy
            f = 0.0 if lq < 1e-12 else max(0.0, min(1.0, ((x - x0) * vx + (y - y0) * vy) / lq))
            best = min(best, math.hypot(x - x0 - f * vx, y - y0 - f * vy))
        return best
    return max(hin, max(zum_zug(x, y) for x, y in soll))


def t2():
    rnd = random.Random(1811)
    n = 0
    for _ in range(150):
        lg, br = rnd.uniform(4, 60), rnd.uniform(3, 30)
        art = rnd.choice(["Langloch", "Rechteck"])
        r = rnd.choice([0.0, 0.0, rnd.uniform(0.5, 5)])
        laengs = rnd.random() < 0.5
        k = rnd.randint(8, 120)
        umriss = []
        for i in range(k):
            w = 2 * math.pi * i / k
            umriss.append((lg / 2 * math.cos(w) + rnd.uniform(-0.3, 0.3), br / 2 * math.sin(w) + rnd.uniform(-0.3, 0.3)))
        if rnd.random() < 0.2:
            umriss.append(umriss[-1])           # doppelter Punkt (Strecke der Länge 0)
        alt = ref_grundform(umriss, art, lg, br, laengs, r=r)
        neu = step._grundform_abweichung(umriss, art, lg, br, laengs, r=r)
        assert abs(alt - neu) < 1e-9, (alt, neu)
        n += 1
    ok(f"T2 Grundform-Abweichung gleich wie bisher ({n} Umrisse)")


def t3():
    from rohrlaser import rohr3d, schneidweg as sw, step_gegenprobe as g
    gemessen = dict(form="Quadratrohr", a=50.0, b=None, wand=3.0, profil_id="QR 50x50x3")
    stamm = dict(gemessen, bemerkung="aus STEP-Import angelegt, bitte prüfen", flaeche_manuell=554.3, wand_max=None,
                 endbeschnitt=None, greiferrest=None, laengenvergleich="ja")
    assert g.profil_geometrie(stamm) == gemessen and g.profil_geometrie(None) is None
    e = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100),
                                   dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="vorne")])
    soll = rohr3d.netz_rechnen(e, gemessen, 559)
    rohr3d.netz_merker_leeren()
    n = {"n": 0}
    orig = rohr3d.netz_rechnen

    def zaehlend(*a, **k):
        n["n"] += 1
        return orig(*a, **k)
    rohr3d.netz_rechnen = zaehlend
    try:
        erst = rohr3d.netz(e, gemessen, 559)
        zweit = rohr3d.netz(e, stamm, 559)
        assert n["n"] == 1 and erst == soll and zweit == soll, n["n"]
        rohr3d.netz(e, dict(stamm, r_aussen=6.0), 559)
        rohr3d.netz(e, dict(stamm, wand=4.0), 559)
        assert n["n"] == 3, n["n"]
    finally:
        rohr3d.netz_rechnen = orig
    ok("T3 3D-Netz/Gegenprobe: Stammdaten-Felder ohne Einfluss rechnen nicht neu, Maße und Radius schon")


if __name__ == "__main__":
    t1()
    t2()
    t3()
    print("Alle Tests bestanden.")
