"""Fasen an den Rohrenden und schräge Konturen im Editor und als 3D-Schnitt (Patrick 25.11.2026: „Nur wenn Fase durch
die komplette Wandstärke geht und 3D-Bearbeitung aktiviert ist“; „wenn 3D ausgewählt dann auch 3D-Schnitt anzeigen,
wenn nicht 3D dann wie gehabt projizieren an der Innenkante 90°“).

- G1 Messung: Fase durch die ganze Wand (Rundrohr Ø60 × 3, Ende B, 30°) ergibt fase_tiefe 1,732, fase_hoehe 3,
  fase_winkel 30°, fase_ganze_wand ja; eine Teilfase 1,5 × 45° (Ende B) fase_tiefe 1,5, fase_hoehe 1,5, nicht ganze
  Wand. Kandidat für 3D ist nur die Fase durch die ganze Wand.
- G2 Rechner-Eingaben: das Ende bekommt den Block 'fase' (Tiefe, Höhe, Winkel); 'd3' am Ende nur mit 3D-Häkchen UND
  ganzer Wand.
- G3 3D-Bearbeitung (dreid) und Schneidweg: ganze Wand + 3D = Zeile „Gehrung 3D Ende B“ mit 30° und Text „Fase 30°
  in 3D“; ohne 3D „Fase nicht gelasert“ mit Hinweis; Teilfase immer „nicht gelasert“, ohne 3D-Zeile.
- G4 Editor-Modell (rohr3d): mit 3D liegt der Außenring am Ende um die Fasentiefe zurück (wie die STEP); ohne 3D
  und bei der Teilfase gerade an der längsten Stelle (Innenkante 90°).
- G5 Schräges Fenster (L-Form, Wände parallel statt radial): gemessen umriss_innen; mit 3D Rand innen wie gemessen
  und Zeile „Kontur 3D“ mit dem Schwenk; ohne 3D Umriss = Innenkante (90°), Schnittlänge danach.

Aufruf: python tests/test_fase_3d.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from OCP.Bnd import Bnd_Box  # noqa: E402
from OCP.BRepBndLib import BRepBndLib  # noqa: E402
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCone, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402
from OCP.TopAbs import TopAbs_EDGE  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402

from rohrlaser import dreid, rechnen, rohr3d, schneidweg as sw, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.02):
    return a is not None and abs(float(a) - b) <= tol


TIEFE = 3 * 0.5773502691896258      # tan 30° × Wand 3


def ganze_wand_fase(l=300.0):
    """Rundrohr Ø60 × 3, Ende B kegelig von außen (z = l − TIEFE) bis innen (z = l): Fase durch die ganze Wand."""
    rohr = et.rundrohr(60, 3, l)
    z0 = l - TIEFE
    wkz = et.cut(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), 40, TIEFE + 1).Shape(),
                 BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), 30, 27, TIEFE).Shape())
    return et.cut(rohr, wkz)


def teilfase(l=300.0, mass=1.5):
    """Rundrohr Ø60 × 3 mit Fase mass × 45° außen an Ende B (nur ein Teil der Wand)."""
    shape = et.rundrohr(60, 3, l)
    f = BRepFilletAPI_MakeChamfer(shape)
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        e = TopoDS.Edge(ex.Current())
        bb = Bnd_Box()
        BRepBndLib.Add_s(e, bb)
        if abs(bb.CornerMin().Z() - l) < 1e-6 and abs(bb.CornerMax().Z() - l) < 1e-6 and bb.CornerMax().X() > 29:
            f.Add(mass, e)
        ex.Next()
    return f.Shape()


tmp = Path(tempfile.mkdtemp())
et.schreibe(ganze_wand_fase(), "G_ganz", tmp)
et.schreibe(teilfase(), "G_teil", tmp)


def ende_b(name):
    (t,) = analysiere_datei(tmp / f"{name}.step")
    return next(d for d in t.konturen_liste if d["art"] == "Ende B")


g, tf = ende_b("G_ganz"), ende_b("G_teil")
assert g.get("fase") and g["fase_ganze_wand"] is True and nah(g["fase_tiefe"], TIEFE) and nah(g["fase_hoehe"], 3) \
    and nah(g["fase_winkel"], 30, 0.1), g
assert tf.get("fase") and tf["fase_ganze_wand"] is False and nah(tf["fase_tiefe"], 1.5) and nah(tf["fase_hoehe"], 1.5) \
    and nah(tf["fase_winkel"], 45, 0.1), tf
assert step.fase_3d(g) and not step.fase_3d(tf)
ok("G1 Messung: ganze Wand 1,73 × 3 mm / 30°, Teilfase 1,5 × 1,5 / 45°; 3D-Kandidat nur die ganze Wand")

step_messen.main(["--ausgabe", str(tmp / "m.txt"), "--netze", str(tmp)] +
                 [str(tmp / f"{n}.step") for n in ("G_ganz", "G_teil")])
MW = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "m.txt"), tmp)}
assert step.kandidaten_3d(MW["G_ganz"])[0] == 1 and step.kandidaten_3d(MW["G_teil"])[0] == 0
e_ohne = step.rechner_eingaben(MW["G_ganz"], "Rundrohr", 60, None, d3=False)
e_mit = step.rechner_eingaben(MW["G_ganz"], "Rundrohr", 60, None, d3=True)
e_teil = step.rechner_eingaben(MW["G_teil"], "Rundrohr", 60, None, d3=True)
fb = e_mit["b"]["fase"]
assert fb["ganze_wand"] and nah(fb["tiefe"], TIEFE) and nah(fb["winkel"], 30, 0.1), fb
assert e_mit["b"].get("d3") and not e_ohne["b"].get("d3") and not e_teil["b"].get("d3"), (e_ohne["b"], e_teil["b"])
assert not e_teil["b"]["fase"]["ganze_wand"] and nah(e_teil["b"]["fase"]["hoehe"], 1.5)
ok("G2 Eingaben: Block 'fase' am Ende; 3D am Ende nur mit 3D-Häkchen und Fase durch die ganze Wand")

db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
mid = next(z["id"] for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
db.aendern("maschinen", mid, "d3", "ja")
k = db.kontext()
masch = rechnen.maschine(dict(maschine="T11"), k)
profil = dict(profil_id="RR 60x3", form="Rundrohr", a=60.0, wand=3.0)
grenzen = rechnen.kontur_regel(masch, 3.0)


def text_b(e, d3):
    erg = sw.rechnen(dict(e, d3=d3), profil, grenzen, None, masch, 300.0)
    tx = next(s["text"] for s in erg["schritte"] if s.get("klasse") == "Ende" and s["text"].startswith("Endschnitt"))
    return tx, " ".join(erg.get("hinweise_3d") or [])


tx, h = text_b(e_mit, True)
assert "Fase 30" in tx and "in 3D" in tx, tx
tx, h = text_b(e_ohne, False)
assert "Fase nicht gelasert" in tx and "durch die ganze Wand" in h, (tx, h)
tx, h = text_b(e_teil, True)
assert "Fase nicht gelasert" in tx and "in 3D" not in tx, tx
p_mit = dict(laenge=300.0, b_schnitt=e_mit["b"].get("gemessen") or 188.5, technik=json.dumps(dict(e_mit, d3=True)))
zeilen = dreid.bearbeitungen(p_mit, masch)
assert len(zeilen) == 1 and zeilen[0]["art"] == dreid.ENDE_B and nah(zeilen[0]["winkel"], 30, 0.1) \
    and zeilen[0].get("fase"), zeilen
p_teil = dict(laenge=300.0, b_schnitt=188.5, technik=json.dumps(dict(e_teil, d3=True)))
assert dreid.bearbeitungen(p_teil, masch) == []
ok("G3 Schneidweg/3D: ganze Wand + 3D = 3D-Schnitt 30° (Zeile Gehrung 3D Ende B); ohne 3D bzw. Teilfase nicht "
   "gelasert, mit Hinweis")

for e, tiefe in ((dict(e_mit, d3=True), TIEFE), (e_ohne, 0.0), (dict(e_teil, d3=True), 0.0)):
    bau = {}
    assert rohr3d.netz_rechnen(e, profil, 300.0, bau=bau)
    u, v = bau["umriss"][0][0]
    assert nah(300.0 - bau["zb"](u, v), tiefe, 0.03), (300.0 - bau["zb"](u, v), tiefe)
ok("G4 Editor: mit 3D Außenring um die Fasentiefe zurück (1,73 mm), ohne 3D und Teilfase gerade (Innenkante 90°)")

fenster = et.cut(et.rundrohr(60, 3, 300), et.verschiebe(BRepPrimAPI_MakeBox(8, 35, 100).Shape(), 8, 5, 100))
fenster = et.cut(fenster, et.verschiebe(BRepPrimAPI_MakeBox(16, 35, 30).Shape(), 8, 5, 100))
et.schreibe(fenster, "G_fenster", tmp)
step_messen.main(["--ausgabe", str(tmp / "f.txt"), "--netze", str(tmp), str(tmp / "G_fenster.step")])
(mf,) = step.lade_netze(step.lies_messwerte(tmp / "f.txt"), tmp)
kl = [d for d in json.loads(mf["konturen_liste"]) if d.get("umriss_innen")]
assert len(kl) == 1 and kl[0]["schwenk"] > 10 and step.sonder_3d(mf) == 1, [(d.get("art"), d.get("schwenk"))
                                                                              for d in json.loads(mf["konturen_liste"])]
f3 = step.rechner_eingaben(mf, "Rundrohr", 60, None, d3=True)
f2 = step.rechner_eingaben(mf, "Rundrohr", 60, None, d3=False)
k3 = next(z for z in f3["konturen"] if z.get("umriss_innen"))
k2 = next(z for z in f2["konturen"] if z.get("umriss_step"))
assert k3["d3"] and k3["schwenk"] > 10 and k3["umriss"] != k3["umriss_innen"]
assert k2["umriss"] != k2["umriss_step"] and k2["gemessen"] != k2["gemessen_step"] and not k2.get("d3"), k2
zeilen = dreid.bearbeitungen(dict(laenge=300.0, technik=json.dumps(dict(f3, d3=True))), masch)
assert [z["art"] for z in zeilen] == [dreid.KONTUR_3D] and nah(zeilen[0]["winkel_eingabe"], k3["schwenk"], 0.01) \
    and zeilen[0]["winkel"] <= 45, zeilen
n3 = rohr3d.netz_rechnen(dict(f3, d3=True), profil, 300.0)
n2 = rohr3d.netz_rechnen(f2, profil, 300.0)
assert n3 and n2 and n3 != n2
ok(f"G5 schräges Fenster ({kl[0]['schwenk']:g}°): mit 3D Rand innen wie gemessen + Zeile Kontur 3D; ohne 3D an der "
   f"Innenkante 90° ({k2['gemessen']:g} statt {k2['gemessen_step']:g} mm)")
print("Fasen in 3D und im Editor: alle Tests bestanden.")
