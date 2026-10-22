"""Prüft Fasen an den Rohrenden im STEP-Import (Patrick 22.10.2026): eine Fase wird nicht gelasert; das Programm gibt
einen Hinweis und nimmt Länge und Schneidweg an der längsten Stelle an (gerader Schnitt an der Außenkontur).
- F1 Rundrohr Ø42,4 × 2 mit Fase 1,5 × 45° außen an Ende B: Länge 500, Ende B gerade, Schnitt π × 42,4, keine
  Innenkontur, Hinweis, Prüfstatus plausibel
- F2 Rechteckrohr 60 × 40 × 3 mit Fase 2 × 45° außen an Ende A: Ende A gerade 200 mm
- F3 Rundrohr mit Fase innen an Ende B (Schweißnahtvorbereitung innen): ebenso
- F4 Übernahme: a_gerade/b_gerade "ja", Schneidweg, Hinweis im Bericht; Schlitz am Ende bleibt eine Kontur

Teile werden mit OpenCascade erzeugt (tests/erzeuge_testteile.py) und mit step_messung gemessen.
Aufruf: python tests/test_step_fase.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER))

from OCP.Bnd import Bnd_Box  # noqa: E402
from OCP.BRepBndLib import BRepBndLib  # noqa: E402
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.TopAbs import TopAbs_EDGE  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402

from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.05):
    return a is not None and abs(a - b) <= tol


def fase(shape, z, aussen, grenze, mass):
    """Fase mass × 45° an den Kanten bei z, außen (Abstand zur Achse > grenze) oder innen."""
    f = BRepFilletAPI_MakeChamfer(shape)
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        e = TopoDS.Edge(ex.Current())
        bb = Bnd_Box()
        BRepBndLib.Add_s(e, bb)
        r = max(abs(bb.CornerMax().X()), abs(bb.CornerMax().Y()), abs(bb.CornerMin().X()), abs(bb.CornerMin().Y()))
        if abs(bb.CornerMin().Z() - z) < 1e-6 and abs(bb.CornerMax().Z() - z) < 1e-6 and (r > grenze) == aussen:
            f.Add(mass, e)
        ex.Next()
    return f.Shape()


tmp = Path(os.environ.get("TESTTMP") or tempfile.mkdtemp())
et.schreibe(fase(et.rundrohr(42.4, 2, 500), 500, True, 20.5, 1.5), "F01_RR42-4x2_Fase_B", tmp)
et.schreibe(fase(et.kastenrohr(60, 40, 3, 600, 0), 0, True, 28.5, 2.0), "F02_RE60x40x3_Fase_A", tmp)
et.schreibe(fase(et.rundrohr(42.4, 2, 500), 500, False, 20.0, 1.0), "F03_RR42-4x2_Fase_innen", tmp)
schlitz = et.cut(et.rundrohr(42.4, 2, 500), et.zylinder((0, 0, 480), (0, 1, 0), 6, 40))
schlitz = et.cut(schlitz, et.verschiebe(BRepPrimAPI_MakeBox(6, 40, 30).Shape(), -3, 0, 480))   # offen bis Ende B
et.schreibe(schlitz, "F04_RR42-4x2_Schlitz_B", tmp)


def messen(name):
    (t,) = analysiere_datei(tmp / f"{name}.step")
    return t, {d["art"]: d for d in t.konturen_liste if d["art"] in ("Ende A", "Ende B")}


t, e = messen("F01_RR42-4x2_Fase_B")
assert nah(t.laenge, 500) and t.ende_b_gerade and nah(t.ende_b, math.pi * 42.4) and t.innen == 0, \
    (t.laenge, t.ende_b, t.innen)
assert e["Ende B"]["fase"] is True and e["Ende B"]["form"] == "gerade" and not e["Ende A"].get("fase")
assert nah(t.schneidweg, 2 * math.pi * 42.4) and t.konturen == 2 and t.pruefstatus == "plausibel", t.pruefstatus
assert any("Ende B: Fase erkannt" in h for h in t.hinweise), t.hinweise
ok("F1 Rundrohr Fase außen an Ende B: Länge 500, gerader Schnitt an der Außenkontur, Hinweis, plausibel")
t, e = messen("F02_RE60x40x3_Fase_A")
assert nah(t.laenge, 600) and t.ende_a_gerade and nah(t.ende_a, 200) and t.innen == 0 and e["Ende A"]["fase"]
ok("F2 Rechteckrohr Fase außen an Ende A: 200 mm gerade")
t, e = messen("F03_RR42-4x2_Fase_innen")
assert nah(t.laenge, 500) and t.ende_b_gerade and nah(t.ende_b, math.pi * 42.4) and t.innen == 0, \
    (t.laenge, t.ende_b, t.innen, t.konturen_liste)
ok("F3 Fase innen an Ende B: wie gerader Schnitt")
t, e = messen("F04_RR42-4x2_Schlitz_B")
assert not e["Ende B"].get("fase") and not any("Fase" in h for h in t.hinweise), (e, t.hinweise)
ok("F4 Schlitz am Ende ist keine Fase")

step_messen.main(["--ausgabe", str(tmp / "m.txt"), str(tmp / "F01_RR42-4x2_Fase_B.step")])
mw = step.lies_messwerte(tmp / "m.txt")
db = Datenbank(tmp / "rohrlaser.db")
erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", 5, neue_profile=True)
(p,) = erg["positionen"]
assert p["a_gerade"] == p["b_gerade"] == "ja" and nah(p["b_schnitt"], math.pi * 42.4, 0.1) and p["laenge"] == 500
assert "Fase erkannt" in erg["bericht"][0], erg["bericht"]
ok("F4 Übernahme: beide Enden gerade, Schneidweg an der längsten Stelle, Hinweis im Bericht")
print("Alle Fasen-Tests bestanden.")
