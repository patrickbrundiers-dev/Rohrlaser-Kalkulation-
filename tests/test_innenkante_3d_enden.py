"""Echte Innenkante bei 3D-Schnitten an den Enden (Master-Auftrag Patrick 25.11.2026 „Abwicklungskern für den
STEP-/CAD-Import grundlegend erweitern“, Paket P4; Regel Patrick 25.11.2026: mit 3D wie in der STEP, ohne 3D an der
Innenkante 90°).

Bisher nahm der Verlauf eines Endes für die Verschachtelung bei einem 3D-Schnitt die Innenkante pauschal Wand × tan
(Winkel) vor der Außenkante an. Jetzt rechnet endkontur.ende_verlauf_zellen sie je Stützstelle dort, wo die
Schnittebene die Innenwand trifft. Geprüft wird:
- sicher: an keiner Stelle des Umfangs (außen und innen fein abgetastet) reicht Material vor den Verlauf
- nie schlechter als bisher, im Mittel enger (Rund-, Quadrat-, Rechteckrohr; Gehrung und schräg in zwei Richtungen)
- ohne 3D (2D, Innenkante 90°) bitgleich wie bisher
- Gegenprobe mit der STEP: Lage der Innenkante der Schnittfläche (R02 Gehrung 45° genau, R03 schräg 20°/10°
  scharfkantig: das Programm nimmt die Innenkante höchstens früher an, nie später)

Aufruf: python tests/test_innenkante_3d_enden.py
"""
import math
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

from rohrlaser import endkontur as ek, schneidweg as sw, skizze as sk, step  # noqa: E402

fehler = []


def pruef(bed, text):
    print(("OK     " if bed else "FEHLER ") + text)
    if not bed:
        fehler.append(text)


def verlauf_ohne_innenkante(qs, gk, e):
    alt = ek._innen_3d
    ek._innen_3d = lambda q, e_: False
    try:
        return ek.ende_verlauf_zellen(qs, gk, e)
    finally:
        ek._innen_3d = alt


def unsicher(qs, gk, e, verlauf):
    """Stützstellen (21 je Zelle, außen und bei 3D innen), an denen Material vor dem Verlauf liegt."""
    g = ek.geo(gk)
    n = 0
    for i in range(g.n):
        for k in range(21):
            (u, v), nrm = qs.s_zu_uv(min((i + k / 20) * g.ds, qs.umfang - 1e-9))
            ln = math.hypot(*nrm) or 1.0
            pkt = [(u, v)] + ([(u - qs.wand * nrm[0] / ln, v - qs.wand * nrm[1] / ln)] if e.get("d3") else [])
            n += sum(sk.schnitt_x(qs, e, a, b) < verlauf[i] - 1e-6 for a, b in pkt)
    return n


PROFILE = [dict(form="Rundrohr", a=48.3, wand=3), dict(form="Quadratrohr", a=50, b=50, wand=3),
           dict(form="Rechteckrohr", a=80, b=40, wand=3)]
for prof in PROFILE:
    qs = sk.Querschnitt(sw.mit_radius(prof, {}))
    gk = ek.geo_schluessel(qs)
    for e in (dict(winkel=45, d3=True), dict(winkel=20, d3=True, richtung=30)):
        neu = ek.ende_verlauf_zellen(qs, gk, e)
        alt = verlauf_ohne_innenkante(qs, gk, e)
        diff = [a - b for a, b in zip(neu, alt)]
        zuschlag = 3 * math.tan(math.radians(e["winkel"]))
        pruef(unsicher(qs, gk, e, neu) == 0, f"{prof['form']} {e}: kein Material vor dem Verlauf")
        pruef(min(diff) >= -1e-9 and max(diff) <= zuschlag + 1e-6 and sum(diff) / len(diff) > 0.5 * zuschlag,
              f"{prof['form']} {e}: nie schlechter, im Mittel {sum(diff) / len(diff):.2f} von {zuschlag:.2f} mm "
              "Zuschlag gewonnen")
    e2 = dict(winkel=45)
    pruef(ek.ende_verlauf_zellen(qs, gk, e2) == verlauf_ohne_innenkante(qs, gk, e2),
          f"{prof['form']}: ohne 3D unverändert (Innenkante 90°)")
    kp = ek.kanten_punkte(qs, e2, n=90)
    pruef(all(a[2] == b[2] for a, b in zip(kp[0::2], kp[1::2])), f"{prof['form']}: Kantenpunkte 2D innen = außen")
    pruef(not ek._innen_3d(qs, dict(winkel=45, d3=True, umriss=[[0, 0], [1, 1]])) and
          not ek._innen_3d(qs, dict(winkel=0, d3=True)), f"{prof['form']}: nur ebene 3D-Schnitte")


# ---------------------------------------------------------------- Gegenprobe mit der STEP
def step_kanten(datei):
    """Abstand hinter der Spitze [mm] der Außen- und Innenkante der Schnittfläche an Ende B (ebene Fläche, äußerer
    Rand = Außenkante, innerer Rand = Innenkante) direkt aus der STEP."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    def punkte(w):
        out, ex = [], TopExp_Explorer(w, TopAbs_EDGE)
        while ex.More():
            c = BRepAdaptor_Curve(TopoDS.Edge(ex.Current()))
            a, b = c.FirstParameter(), c.LastParameter()
            out += [c.Value(a + (b - a) * i / 200).Z() for i in range(201)]
            ex.Next()
        return out
    rd = STEPControl_Reader()
    rd.ReadFile(str(datei))
    rd.TransferRoots()
    best, ex = None, TopExp_Explorer(rd.OneShape(), TopAbs_FACE)
    while ex.More():
        fa = TopoDS.Face(ex.Current())
        if BRepAdaptor_Surface(fa).GetType() == GeomAbs_Plane:
            z = punkte(BRepTools.OuterWire_s(fa))
            if best is None or sum(z) / len(z) > best[0]:
                best = (sum(z) / len(z), fa)
        ex.Next()
    fa = best[1]
    aussen_w = BRepTools.OuterWire_s(fa)
    aussen, innen, ex = punkte(aussen_w), [], TopExp_Explorer(fa, TopAbs_WIRE)
    while ex.More():
        if not ex.Current().IsSame(aussen_w):
            innen += punkte(ex.Current())
        ex.Next()
    spitze = max(aussen)
    return [spitze - z for z in aussen], [spitze - z for z in innen]


try:
    import step_messen as sm
except ImportError as e_:          # ohne OpenCascade (nur Kern) – in der CI vorhanden
    sm = None
    print(f"übersprungen: STEP-Gegenprobe ({e_})")
if sm:
    REF = HIER / "step_referenz_konturen"
    for name, genau in (("R02_RR48-3x3_Gehrung45", True), ("R03_QR50x3_schraeg_20_10", False)):
        f = REF / f"{name}.step"
        m = dict(zip(sm.SPALTEN, sm.zeilen(f)[0]))
        ein = step.rechner_eingaben(m, m["profilform"], d3=True)
        e = ein["b"]
        prof = dict(form=m["profilform"], a=float(m["abm_a"]), b=float(m["abm_b"] or m["abm_a"]),
                    wand=float(m["wandstaerke"]))
        qs = sk.Querschnitt(sw.mit_radius(prof, ein))
        kp = ek.kanten_punkte(qs, e, n=1440)
        p_aussen, p_innen = [p[2] for p in kp[0::2]], [p[2] for p in kp[1::2]]
        s_aussen, s_innen = step_kanten(f)
        pruef(e.get("d3") and ek._innen_3d(qs, e), f"{name}: Ende B ist ein ebener 3D-Schnitt")
        pruef(abs(max(p_aussen) - max(s_aussen)) < 0.05, f"{name}: Außenkante wie STEP ({max(p_aussen):.3f} / "
              f"{max(s_aussen):.3f} mm)")
        if genau:
            pruef(abs(min(p_innen) - min(s_innen)) < 0.02 and abs(max(p_innen) - max(s_innen)) < 0.02,
                  f"{name}: Innenkante genau wie STEP ({min(p_innen):.3f}..{max(p_innen):.3f} / "
                  f"{min(s_innen):.3f}..{max(s_innen):.3f} mm)")
        else:   # scharfkantig: Punkte im Eckblock liegen im Material, die Innenkante wird höchstens früher angenommen
            pruef(min(p_innen) <= min(s_innen) + 0.01,
                  f"{name}: Innenkante sicher, nie später als in der STEP ({min(p_innen):.3f} ≤ {min(s_innen):.3f} mm)")
        neu = ek.ende_verlauf_zellen(qs, ek.geo_schluessel(qs), e)
        pruef(min(neu) <= min(s_innen) + 0.01 and min(neu) <= min(s_aussen) + 0.01,
              f"{name}: Verlauf vor Außen- und Innenkante der STEP")

print("\nAlle Tests bestanden." if not fehler else f"\n{len(fehler)} Fehler")
sys.exit(1 if fehler else 0)
