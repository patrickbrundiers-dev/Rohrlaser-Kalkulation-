"""Aufgeschnittene Rohrteile (Patrick 30.10.2026, zwei Fotos: Rechteckrohre mit großem Ausschnitt über Oberseite und
Seitenwände, Schrägschnitt, Schlitzen und Nase; kurzer Rechteckrohr-Abschnitt in U-Form, eine Wand fast ganz weg):
„Solche Teile erkennen und auch im Editor erkennen, Editor darauf prüfen, dass die Konturen genauso sind wie in der
geladenen STEP-Datei.“ Keine STEP-Datei mitgeschickt, die Teile sind mit OpenCascade nachgebaut.

Je Teil: gemessen, wie im Prüfdialog vorbereitet (offene Rohre, Knickrahmen), übernommen, im Rohr-Editor geöffnet und
dessen 3D-Linien (Konturen und Enden) mit den Linien des STEP-Netzes verglichen (beide Richtungen, ±0,06 mm).

Vorher gefunden:
A1/A5 Ausschnitt durch Oberseite und beide Seitenwände, die Seitenwände nur teilweise weg (Trapez): galt als V-Ausschnitt
      eines gestreckt gezeichneten Knickrahmens (Schnittlänge passte zufällig zur Formel) – im Editor ein V statt des
      Ausschnitts, 16 mm neben der STEP. Jetzt nur ein V, wenn die Seitenwände bis an die Stegwand durchgeschnitten sind.
A3    Quadratrohr, Oberseite zwischen den Enden offen (Ringe in der STEP), Fenster in einer Seitenwand: der offene
      U-Querschnitt galt als Regelquerschnitt, Rohrachse im Schwerpunkt des U – Editor 13 mm neben der STEP. Jetzt wie
      beim langen Fenster: die geschlossenen Querschnitte an den Enden sind der Regelquerschnitt.
Teile-Editor: ein komplexes Ende aus der STEP hieß in den Merkmalen „gerade“, jetzt „komplex (Umriss wie STEP)“.
A2/A4/A6 (Ausschnitt mit Schlitzen und Nase, Seitenwand halb weg, U-Form mit Ring an einem Ende) waren schon richtig.

Aufruf: python tests/test_rohr_aufgeschnitten.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism  # noqa: E402
from OCP.gp import gp_Pnt, gp_Vec  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, knickverbindung, rohr3d, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.teile_editor import ende_text  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py
box = wie.box


def prisma(punkte, ebene, a0, d):
    """Polygon in der Ebene x = a0 (ebene 'yz', Punkte (y, z)) bzw. y = a0 ('xz', Punkte (x, z)), um d quer
    durchgezogen: Schnittkörper durch das ganze Rohr."""
    p = BRepBuilderAPI_MakePolygon()
    for u, v in punkte:
        p.Add(gp_Pnt(a0, u, v) if ebene == "yz" else gp_Pnt(u, a0, v))
    p.Close()
    return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(p.Wire()).Face(),
                                 gp_Vec(d, 0, 0) if ebene == "yz" else gp_Vec(0, d, 0)).Shape()


TRAPEZ = [(-5, 220), (-5, 380), (40, 450), (40, 150)]       # unten 160 mm, oben 300 mm, bis 20 mm über die Unterseite


def teile():
    f = {}
    re = et.kastenrohr(100, 50, 3, 600, 6)
    t = et.cut(re, prisma(TRAPEZ, "yz", -60, 120))
    t = et.cut(t, box(-60, 0, 80, 120, 15, 3))                         # Querschlitz in beiden Seitenwänden
    t = et.cut(t, box(-60, -10, 520, 120, 4, 15))                      # Längsschlitz beidseitig
    f["A1_RE_Trapez_Schlitze_Ecke"] = et.cut(t, prisma([(10, -1), (60, -1), (60, 60)], "xz", -40, 80))  # Ecke schräg
    t = et.cut(re, prisma([(-5, 200), (-5, 400), (40, 470), (40, 130)], "yz", -60, 120))
    for z in (200, 398):
        t = et.cut(t, box(-60, -15, z, 120, 11, 2))                    # Schlitze an der Ausschnittkante
    t = et.cut(t, box(-60, -22, 585, 120, 60, 20))                     # Ende B: nur die Unterseite steht vor (Nase)
    f["A2_RE_Ausschnitt_Nase"] = et.cut(t, box(-3, -40, 590, 6, 30, 20))   # Kerbe in der Nase
    q = et.kastenrohr(50, 50, 3, 120, 4)
    f["A3_QR_oben_offen_Fenster"] = et.cut(et.cut(q, box(-30, 10, 10, 60, 30, 100)), box(20, -15, 30, 10, 20, 60))
    f["A4_RE_Seite_halb"] = et.cut(et.kastenrohr(80, 40, 3, 500, 5), box(-10, 0, 100, 60, 30, 300))
    g = et.schraeg_ende(re, 600 - 50 * math.tan(math.radians(30)), 0, 30)   # Gehrung 30° über die ganze Breite
    f["A5_RE_Gehrung_Trapez"] = et.cut(g, prisma(TRAPEZ, "yz", -60, 120))
    r = et.kastenrohr(60, 40, 3, 100, 4)                               # Foto 2: Oberseite fast ganz weg, Seite halb
    f["A6_RE_U_Ring_einseitig"] = et.cut(et.cut(r, box(-26, 10, -1, 52, 20, 81)), box(-40, -5, -1, 15, 30, 61))
    return f


FORM = {"A3": "Quadratrohr"}
SONDER = {"A1": 1, "A2": 1, "A3": 1, "A4": 1, "A5": 1, "A6": 0}    # Ausschnitt als Sonderkontur (A6: Teil von Ende A)


def main():
    fehler = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = Datenbank(tmp / "rohrlaser.db")
        f = teile()
        for n, s in f.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp)] + [str(tmp / (n + ".step")) for n in f])
        ms = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)}
        assert len(ms) == len(f), sorted(ms)

        from PySide6.QtWidgets import QApplication
        from rohrlaser.schneidweg_dialog import SchneidwegDialog
        app = QApplication.instance() or QApplication([])  # noqa: F841
        k = db.kontext()
        step.offene_rohre_vorbelegen(list(ms.values()), k.profile, None)      # wie der Prüfdialog
        for name, m in ms.items():
            kurz = name[:2]
            assert m["profilform"] == FORM.get(kurz, "Rechteckrohr"), (name, m["profilform"], m.get("hinweise"))
            assert not knickverbindung.v_ausschnitte(m), (name, "Ausschnitt als V-Ausschnitt (Knickrahmen) gedeutet")
            assert not knickverbindung.koerper_vorbereiten(m, {}) and not m.get("_knickrahmen"), name
            sonder = [x for x in json.loads(m["konturen_liste"]) if x["art"] == "Sonderkontur"]
            assert len(sonder) == SONDER[kurz], (name, [x["art"] for x in json.loads(m["konturen_liste"])])
        erg = step.uebernehmen(list(ms.values()), [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               neue_profile=True)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        kopf = dict(maschine="T11", stange=6000)
        gesehen = set()
        for p in erg["positionen"]:
            name = p["artikel"]
            gesehen.add(name)
            d = SchneidwegDialog(None, p, k.profile[p["profil_id"]], kopf, k, db.tabellen(), db)
            e = d.eingaben()
            assert not any(z.get("art") == "V-Ausschnitt" for z in e["konturen"]), (name, e["konturen"])
            if name.startswith(("A1", "A6")):      # Ende A mit schräger Ecke bzw. Ausschnitt bis ans Ende: nicht „gerade“
                assert e["a"].get("form") == "komplex" and ende_text(e["a"]).startswith("komplex"), (name, e["a"])
            n = wie.netz_wie_konstruiert(d)
            sn = ansicht3d.entpacken(ms[name]["_netz"])
            mod = [z for a in ("K", "EA", "EB") for z in n["l"].get(a, [])]
            st = [z for a in ("K", "EA", "EB") for z in sn["l"].get(a, [])]
            weit = max(wie._abstand(mod, st), wie._abstand(st, mod)) - rohr3d.ABSTAND
            if weit > TOL:
                fehler += 1
                print(f"FEHLER {name}: im Editor {weit:.3f} mm neben der STEP")
            else:
                print(f"OK     {name}: {weit:+.3f} mm")
            d.deleteLater()
        assert gesehen == set(f), sorted(set(f) - gesehen)
    print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
    return fehler


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
