"""Schnitt „auf 0“ (Supportpaket Patrick 25.11.2026, Transportschiene QR 100×5): die Ausklinkung des Kunden endet genau
in der Ebene der Innenwand oben und unten, der Schnitt läuft an der Innenseite entlang. Patrick gibt im CAD 0,1 mm
Aufmaß (44,9 statt 45). Der STEP-Import erkennt solche Schnitte und misst sie mit dem Aufmaß der Einstellung
step_null_aufmass (Vorgabe 0,1 mm) – mit Hinweis am Teil; 0 = wie STEP, nur Hinweis mit Vorschlag.
Geprüft: Erkennung, Messung gleich der von Hand geänderten Datei, Hinweis, aus = unverändert, normales Rohr und
Ausklinkung mit Abstand ohne Hinweis.
Aufruf: python tests/test_step_null_schnitt.py
"""
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

import step_geometrie as g  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("ok    " if bedingung else "FEHLER ") + text)
    if not bedingung:
        fehler.append(text)


def kasten(x0, y0, z0, x1, y1, z1):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), gp_Pnt(x1, y1, z1)).Shape()


def rohr(tief=None):
    """QR 100×5, L 300, Ausklinkung der Seitenwand y 45…50 über x 0…120 bis ±tief (45 = genau auf die Innenwand)."""
    s = g.boolesch("minus", kasten(0, -50, -50, 300, 50, 50), kasten(-1, -45, -45, 301, 45, 45)).Shape()
    if tief is not None:
        s = g.boolesch("minus", s, kasten(-1, 44, -tief, 120, 51, tief)).Shape()
    return TopoDS.Solid(g._liste(s, g.TopAbs_SOLID)[0])


def null(t):
    return [h for h in t.hinweise if h.startswith(g.NULL_HINWEIS)]


g.einstellen({})
pruefe(g.NULL_AUFMASS == 0.1, "Vorgabe Aufmaß 0,1 mm")
auf0 = g.analysiere(rohr(45), "auf0")
hand = g.analysiere(rohr(44.9), "hand")
pruefe(auf0.profilform == "Quadratrohr" and abs(auf0.laenge - 300) < 1e-6, "Profil und Länge erkannt")
pruefe(len(null(auf0)) == 1 and "0,1 mm Aufmaß gemessen" in null(auf0)[0] and "abweichend" in null(auf0)[0],
       f"Hinweis am Teil: {null(auf0)}")
pruefe(abs(auf0.ende_a - hand.ende_a) < 1e-6 and abs(auf0.ende_b - hand.ende_b) < 1e-6,
       f"Schnittlängen wie die Datei mit 0,1 mm Aufmaß von Hand ({auf0.ende_a:.3f} / {hand.ende_a:.3f})")
pruefe(not null(hand), "von Hand mit Aufmaß: kein Hinweis")
pruefe(not null(g.analysiere(rohr(), "glatt")), "glattes Rohr: kein Hinweis")
pruefe(not null(g.analysiere(rohr(30), "tiefer")), "Ausklinkung mit Abstand zur Innenwand: kein Hinweis")

g.einstellen({"null_aufmass": 0})
aus = g.analysiere(rohr(45), "aus")
pruefe(len(null(aus)) == 1 and "Vorschlag" in null(aus)[0], f"aus: nur Hinweis mit Vorschlag ({null(aus)})")
g.einstellen({})

print("Alle Tests bestanden." if not fehler else f"{len(fehler)} Fehler")
sys.exit(1 if fehler else 0)
