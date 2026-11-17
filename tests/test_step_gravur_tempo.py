"""STEP 553591 (Patrick 17.11.2026): Rechteckrohr 80 × 40 × 2 mit vielen Gravuren war beim Import sehr langsam (etwa
5,5 min je Teil), 5 von 10 Teilen liefen ins Zeitlimit und kamen als Frästeil; der Rohr-Editor öffnete erst nach
13–16 s.

T1 Abwicklung (Blech-Gegenprüfung, step_abwicklung): die Vorprüfung über die Flächenhüllen ändert nichts am Ergebnis
   (Kantteile wie bisher abwickelbar, Rohr mit Gravuren gleich wie bisher) und spart den teuren Klassierer
   fast ganz (Rohr mit Gravuren: höchstens ein Viertel der Aufrufe)
T2 3D-Netz des Editors (rohr3d.zelle_frei): Kanten eines Lochs links oder rechts der Spalte werden übersprungen,
   die Zellen bleiben genau gleich (Vergleich mit der bisherigen Rechnung, zufällige Löcher)
T3 Schneidfolge (dynamik.folge): jedes Paar nur einmal gerechnet, gleiche Folge wie ohne Merker
T4 Zeitlimit (Patrick 17.11.2026 „Rohre mit Gravuren immer als Rohr erkennen, niemals als Frästeil, das wenn
   überhaupt nur als Option“): ein Rohr über dem Zeitlimit wird vereinfacht als Rohr gemessen (Profil, Maße, Wand,
   Länge aus dem Querschnitt, auch schräg im Raum), das Frästeil ist nur die Alternative; ein Klotz bleibt Frästeil
T5 Plan E2: ein sicheres geschlossenes Rohr wird für die Auswahl Blech gar nicht erst abgewickelt

Aufruf: python tests/test_step_gravur_tempo.py
"""
import random
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_abwicklung as sa  # noqa: E402
from rohrlaser import dynamik, rohr3d  # noqa: E402


def ok(text):
    print("OK:", text)


def box(x, y, z, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def abwickeln_beides(solid, dicke):
    """(Ergebnis mit Vorprüfung, ohne, Klassierer-Aufrufe mit, ohne)."""
    zaehler = {"n": 0}
    orig = sa.BRepClass3d_SolidClassifier

    class Zaehlend:
        def __init__(self, s):
            self.k = orig(s)

        def Perform(self, p, tol):
            zaehler["n"] += 1
            self.k.Perform(p, tol)

        def State(self):
            return self.k.State()
    sa.BRepClass3d_SolidClassifier = Zaehlend
    try:
        out = []
        for vor in (True, False):
            sa.VORPRUEFUNG, zaehler["n"] = vor, 0
            out.append((sa.abwickeln(solid, dicke), zaehler["n"]))
    finally:
        sa.BRepClass3d_SolidClassifier, sa.VORPRUEFUNG = orig, True
    (a, na), (b, nb) = out
    return a, b, na, nb


def gleich(a, b):
    """Ergebnisse der Abwicklung vergleichen (Zahlen auf 1 µm)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(gleich(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(gleich(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-6
    return a == b


def t1():
    teile = {
        "Winkel mit Radien": (et.profil([(0, 0), (100, 0), (100, 3), (3, 3), (3, 50), (0, 50)], 300,
                                        {(0, 0): 6, (3, 3): 3}), 3.0, True),
        "U mit Ausklinkung": (et.cut(et.profil([(0, 0), (100, 0), (100, 30), (97, 30), (97, 3), (3, 3), (3, 30),
                                                (0, 30)], 600, {(0, 0): 6, (3, 3): 3, (100, 0): 6, (97, 3): 3}),
                                     box(30, -1, 250, 40, 5, 100)), 3.0, True),
    }
    rohr = et.kastenrohr(80, 40, 2, 600, 4)
    for i in range(12):           # Gravur: Taschen 0,5 mm tief, teils rund (Freiformflächen wie Schrift)
        rohr = et.cut(rohr, box(-30 + i * 5, 19.5, 50 + i * 40, 3, 1, 8))
        rohr = et.cut(rohr, et.zylinder((-30 + i * 5, 19.5, 70 + i * 40), (0, 1, 0), 3, 1))
    teile["Rechteckrohr mit Gravuren"] = (rohr, 2.0, None)
    for name, (solid, dicke, kantteil) in teile.items():
        a, b, na, nb = abwickeln_beides(solid, dicke)
        assert gleich(a, b), (name, a.get("fehler"), b.get("fehler"))
        if kantteil is not None:
            assert ("fehler" not in a) == kantteil, (name, a.get("fehler"))
        assert na <= nb, (name, na, nb)
        if kantteil is None:        # Rohr mit Gravuren: der Klassierer fällt fast ganz weg
            assert na * 4 <= nb, (name, na, nb)
        ok(f"T1 {name}: Abwicklung gleich ({a.get('fehler') or 'abwickelbar'}), Klassierer {nb} -> {na}")


def zelle_frei_alt():
    """rohr3d.zelle_frei bis 0.9.368: derselbe Quelltext ohne das Überspringen der Kanten außerhalb der Spalte."""
    import inspect
    q = inspect.getsource(rohr3d.zelle_frei)
    von = q.index("            # Kante ganz links oder rechts der Spalte")
    bis = q.index("            for p, q in kanten_feld:")
    assert von < bis
    ns = dict(rohr3d.__dict__)
    exec(q[:von] + q[bis:], ns)     # noqa: S102 – Quelltext des Programms, nur im Test
    return ns["zelle_frei"]


def t2():
    import math
    alt = zelle_frei_alt()
    rnd = random.Random(17)
    for _ in range(300):
        t0, t1_ = rnd.uniform(0, 50), rnd.uniform(51, 120)
        feld = [(t0, rnd.uniform(-5, 5)), (t1_, rnd.uniform(-5, 5)), (t1_, rnd.uniform(500, 600)),
                (t0, rnd.uniform(500, 600))]
        loecher = []
        for _ in range(rnd.randint(1, 4)):
            cx, cy, r, k = rnd.uniform(-50, 200), rnd.uniform(0, 600), rnd.uniform(3, 80), rnd.randint(3, 40)
            loecher.append([(cx + r * rnd.uniform(0.5, 1) * math.cos(2 * math.pi * j / k),
                             cy + r * rnd.uniform(0.5, 1) * math.sin(2 * math.pi * j / k)) for j in range(k)])
        assert rohr3d.zelle_frei(feld, loecher) == alt(feld, loecher), (feld, loecher)
    ok("T2 zelle_frei: 300 zufällige Spalten mit Löchern, Zellen genau wie bisher")


def t3():
    m = dict(eilgang_x=60000, beschl_x=5, drehzahl=60, beschl_dreh=300, zeit_regelung=0.1)
    rnd = random.Random(3)
    lagen = [dict(x=rnd.uniform(0, 2000), eingabe=dict(seite=rnd.choice(["oben", "vorne", "unten", "hinten"])))
             for _ in range(60)]
    n = {"n": 0}
    orig = dynamik.bewegung

    def zaehlend(*a):
        n["n"] += 1
        return orig(*a)
    dynamik.bewegung = zaehlend
    try:
        r = dynamik.folge(lagen, m, 2000)
    finally:
        dynamik.bewegung = orig
    # ohne Merker: dieselbe Rechnung mit der Kostenfunktion direkt
    from rohrlaser.schneidfolge import tour
    pkt = sorted(((float(d["x"]), dynamik.winkel_der_seite(d["eingabe"]["seite"])) for d in lagen),
                 key=lambda t: t[0])
    v, a = m["eilgang_x"] / 60, m["beschl_x"]

    def t(p, q):
        tx = orig(abs(q[0] - p[0]) / 1000, v, a)
        tw = orig(abs((q[1] - p[1] + 180) % 360 - 180), m["drehzahl"] * 6.0, m["beschl_dreh"]) \
            if p[1] is not None and q[1] is not None else 0.0
        return max(tx, tw)
    reihe = [pkt[i] for i in tour(len(pkt), lambda i, j: t(pkt[i], pkt[j]), lambda j: t((0.0, None), pkt[j]),
                                  lambda i: t(pkt[i], (2000.0, None)))]
    gesamt = lambda rr: sum(t(p, q) for p, q in zip([(0.0, None)] + rr, rr + [(2000.0, None)]))  # noqa: E731
    erwartet = reihe if gesamt(reihe) < gesamt(pkt) - 1e-9 else pkt
    assert r == erwartet, "andere Folge"
    assert n["n"] < 2 * 60 * 60 * 2, n["n"]
    ok(f"T3 Schneidfolge 60 Konturen: gleiche Folge, {n['n']} Bewegungen gerechnet")


def t4():
    import tempfile
    import step_geometrie as g
    import step_messen
    from test_step_wie_modell import dreh
    tmp = Path(tempfile.mkdtemp())
    rohr = et.kastenrohr(80, 40, 2, 1965, 4)
    for i in range(10):
        rohr = et.cut(rohr, box(-30 + i * 5, 19.5, 100 + i * 150, 3, 1, 8))
    rohr = et.cut(rohr, box(-50, -25, 700, 100, 30, 570))       # langer Ausschnitt über drei Wände
    faelle = {"RE_Gravur": (rohr, ("Rechteckrohr", 80, 40, 2, 1965)),
              "RE_Gravur_Raum": (dreh(dreh(rohr, 33, (1, 1, 0)), 17, (0, 0, 1)), ("Rechteckrohr", 80, 40, 2, 1965)),
              "RR_Gravur": (et.cut(et.rundrohr(48.3, 2.6, 900), box(-3, 23.5, 300, 6, 2, 40)),
                            ("Rundrohr", 48.3, 0, 2.6, 900)),
              "Klotz": (box(0, 0, 0, 120, 80, 60), None)}
    for name, (s, soll) in faelle.items():
        et.schreibe(s, name, tmp)
        gel = step_messen._lesen(tmp / f"{name}.step")
        t = g.koerper_messen(gel, 1, auslassen={1: "Zeitlimit 600 s überschritten"})
        if soll is None:
            assert t.profilform == "Frästeil" and t.alternative is None, (name, t.profilform)
            ok(f"T4 {name}: über dem Zeitlimit weiter Frästeil (kein Rohr)")
            continue
        form, a, b, w, lg = soll
        assert t.bauteiltyp == "Profil" and t.profilform == form, (name, t.bauteiltyp, t.profilform)
        assert abs(t.abm_a - a) < 0.05 and abs(t.abm_b - b) < 0.05 and abs(t.wandstaerke - w) < 0.05, \
            (name, t.abm_a, t.abm_b, t.wandstaerke)
        assert abs(t.laenge - lg) < 0.1, (name, t.laenge)
        assert t.alternative is not None and t.alternative.profilform == "Frästeil", name
        assert any("vereinfacht gemessen (Zeitlimit" in h and "als Rohr" in h for h in t.hinweise), t.hinweise
        assert t.pruefstatus == "prüfen", t.pruefstatus
        ok(f"T4 {name}: über dem Zeitlimit {form} {t.abm_a:g}×{t.abm_b:g}×{t.wandstaerke:g}, L {t.laenge:g}, "
           "Frästeil nur als Auswahl")


def t5():
    """Plan E2: ein sicheres geschlossenes Rohr wird für die Auswahl Blech nicht abgewickelt (nie abwickelbar)."""
    import tempfile
    import step_geometrie as g
    tmp = Path(tempfile.mkdtemp())
    rohr = et.kastenrohr(80, 40, 2, 600, 4)
    for i in range(8):
        rohr = et.cut(rohr, et.zylinder((-30 + i * 6, 19.5, 70 + i * 50), (0, 1, 0), 3, 1))
    et.schreibe(rohr, "RE_Gravur_E2", tmp)
    n = {"n": 0}
    orig = sa.abwickeln

    def zaehlend(*a, **k):
        n["n"] += 1
        return orig(*a, **k)
    sa.abwickeln = zaehlend
    try:
        (t,) = g.analysiere_datei(tmp / "RE_Gravur_E2.step")
    finally:
        sa.abwickeln = orig
    assert t.profilform == "Rechteckrohr" and n["n"] == 0, (t.profilform, n["n"])
    assert "Blech" in (t.arten or {}) or "Blech" in (t.arten_grund or {}), (t.arten, t.arten_grund)
    ok("T5 geschlossenes Rohr mit Gravuren: keine Abwicklung für die Auswahl Blech")


if __name__ == "__main__":
    t1()
    t2()
    t3()
    t4()
    t5()
    print("Alle Tests bestanden.")
