"""Knickverbindung aus Einzelrohren (Plan K1-2): Rahmen aus vier Rohren QR 40 × 40 × 2 mit 45°-Gehrungen
(500 × 300 außen) als STEP-Baugruppe.
- V1 Erkennung: Vorschlag aus den Einzelrohren, Kette geschlossen, Schenkel 500/300/500/300, β 90°, Stegwand außen,
  Laufrichtung umkehren; U-Rahmen aus drei Rohren offen; ungleiches Profil und fehlende Lage geben einen Grund.
- V2 Übernahme: eine Position mit gestreckter Länge 1592,7 mm, 3 V-Ausschnitten, Bohrung des dritten Schenkels an
  der richtigen Stelle, Zusatzarbeit Knicken × 3, Schenkel nicht einzeln, gefaltetes Netz; Nahtkandidaten nur am Stoß.
- V3 Innenwand schräg: V-Zeilen in 3D, 3D-Bearbeitungen je Knick, Text; ohne schräg wieder 2D.
- V4 Prüfdialog: Vorschlag sichtbar, Knickverbindung erstellen und lösen, Länge in der Liste.

Aufruf: python tests/test_knickverbindung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "programm"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "programm" / "step_messung"))

from OCP.BRep import BRep_Builder  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism  # noqa: E402
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: E402
from OCP.TopoDS import TopoDS_Compound  # noqa: E402
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec  # noqa: E402

import step_messen  # noqa: E402
from rohrlaser import dreid, knickrahmen as kn, knickverbindung as kv, schneidweg as sw, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK  ", t)


def prisma(punkte, z0, z1):
    poly = BRepBuilderAPI_MakePolygon()
    for x, y in punkte:
        poly.Add(gp_Pnt(x, y, z0))
    poly.Close()
    return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(poly.Wire()).Face(), gp_Vec(0, 0, z1 - z0)).Shape()


def schenkel(L, a=40.0, s=2.0, loch=None):
    """Rohr a × a × s entlang x von 0 bis L, Außenseite y = 0 (lange Kante), 45°-Gehrung an beiden Enden."""
    aussen = prisma([(0, 0), (L, 0), (L - a, a), (a, a)], 0, a)
    innen = prisma([(s, s), (L - s, s), (L - a + s, a - s), (a - s, a - s)], s, a - s)
    k = BRepAlgoAPI_Cut(aussen, innen).Shape()
    if loch:        # Bohrung von oben (z) bei x = loch
        k = BRepAlgoAPI_Cut(k, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(loch, a / 2, -5), gp_Dir(0, 0, 1)), 4.25,
                                                        a + 10).Shape()).Shape()
    return k


def lage(shape, grad, dx, dy):
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(grad))
    v = gp_Trsf()
    v.SetTranslation(gp_Vec(dx, dy, 0))
    return BRepBuilderAPI_Transform(BRepBuilderAPI_Transform(shape, t).Shape(), v).Shape()


def speichern(teile, name):
    c, b = TopoDS_Compound(), BRep_Builder()
    b.MakeCompound(c)
    for t in teile:
        b.Add(c, t)
    pfad = tmp / f"{name}.step"
    w = STEPControl_Writer()
    w.Transfer(c, STEPControl_AsIs)
    w.Write(str(pfad))
    return pfad


def messen(pfad):
    netze = tmp / f"netze_{pfad.stem}"
    netze.mkdir()
    txt = tmp / f"{pfad.stem}.txt"
    step_messen.main(["--ausgabe", str(txt), "--json", str(txt.with_suffix(".json")), "--netze", str(netze),
                      str(pfad)])
    return step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(txt), netze), txt.with_suffix(".json"))


tmp = Path(tempfile.mkdtemp())
RAHMEN = [lage(schenkel(500), 0, 0, 0), lage(schenkel(300), 90, 500, 0), lage(schenkel(500, loch=100), 180, 500, 300),
          lage(schenkel(300), 270, 0, 300)]
rahmen = speichern(RAHMEN, "rahmen")
u_rahmen = speichern(RAHMEN[:3], "u_rahmen")

# ------------------------------------------------------------------ V1 Erkennung
mw = messen(rahmen)
assert len(mw) == 4 and all(m["profilform"] == "Quadratrohr" for m in mw), [m["profilform"] for m in mw]
assert sorted(round(float(m["laenge"]), 1) for m in mw) == [300.0, 300.0, 500.0, 500.0]
assert kv.vorschlaege(mw) == [[0, 1, 2, 3]], kv.vorschlaege(mw)
k = kv.kette(mw, [0, 1, 2, 3])
assert k["geschlossen"] and k["beta"] == 90.0 and sorted(k["schenkel"]) == [300.0, 300.0, 500.0, 500.0], k
assert [t["i"] for t in k["teile"]][0] == 0 and len({t["i"] for t in k["teile"]}) == 4
rueck = kv.kette(mw, [0, 1, 2, 3], umkehren=True)
assert [t["i"] for t in rueck["teile"]] == [0] + [t["i"] for t in k["teile"]][:0:-1], (rueck, k)
mu = messen(u_rahmen)
ku = kv.kette(mu, [0, 1, 2])
assert not ku["geschlossen"] and len(ku["schenkel"]) == 3 and ku["schenkel"][1] == 300.0, ku
for kaputt, grund in ((dict(mw[1], abm_a="50", abm_b="50"), "dasselbe Profil"), (dict(mw[1], _netz=None), "Lage")):
    try:
        kv.kette([mw[0], kaputt, mw[2], mw[3]], [0, 1, 2, 3])
        raise AssertionError(grund)
    except ValueError as f:
        assert grund in str(f), f
ok("V1 Erkennung: Vorschlag, Kette geschlossen 500/300/500/300 β 90°, umkehren, U-Rahmen offen, Gründe")

# ------------------------------------------------------------------ V2 Übernahme ins Angebot
db = Datenbank(tmp / "rohrlaser.db")
katalog = db.zeilen("zusatzarbeiten")
leit = kv.erstellen(mw, k, kf=0.5)
assert leit == 0 and mw[0]["_knick_laenge"] == 1592.7 and all(mw[t["i"]]["_knick_von"] == 0 for t in k["teile"][1:])
for m in mw:
    m["_uebernehmen"] = True
erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", 2, neue_profile=True,
                       zusatz_katalog=katalog)
(p,) = erg["positionen"]
assert p["laenge"] == 1592.7, p["laenge"]
e = sw.lesen(p["technik"])
vs = [z for z in e["konturen"] if z["art"] == "V-Ausschnitt"]
assert [z["x"] for z in vs] == [r["x"] for r in kn.rahmen(kn.lesen(e), dict(form="Quadratrohr", a=40, b=40,
                                                                            wand=2))["knicke"]]
assert all(z.get("seite", "oben") == e["knickrahmen"]["steg"] for z in vs) and e["knickrahmen"]["herkunft"] == kv.HERKUNFT
bohr = [z for z in e["konturen"] if z["art"] == "Bohrung"]      # durch beide Seitenwände (z der Datei)
nr3 = next(n for n, t in enumerate(k["teile"]) if t["i"] == 2)       # Schenkel mit der Bohrung
r = kn.rahmen(kn.lesen(e), dict(form="Quadratrohr", a=40, b=40, wand=2))
start = sum(r["schenkel"][:nr3]) - nr3 * r["vs"][0]
soll = start + 100      # Bohrung 100 mm hinter der Ecke, an der der Rahmen den dritten Schenkel betritt
assert len(bohr) == 2 and all(abs(z["x"] - soll) < 0.6 for z in bohr), (bohr, soll, k)
steg = e["knickrahmen"]["steg"]
gegen = {"oben": "unten", "unten": "oben", "vorne": "hinten", "hinten": "vorne"}
assert sorted(z.get("seite", "oben") for z in bohr) == sorted(s_ for s_ in gegen if s_ not in (steg, gegen[steg])), \
    (bohr, steg)
assert p["einstiche"] == 2 + 3 + 2 and e["a"]["winkel"] == 45.0 and e["b"]["winkel"] == 45.0
assert abs(p["schneidweg"] - (p["a_schnitt"] + p["b_schnitt"] + 3 * 295.0 + p["innen"] - 3 * 295.0)) < 0.2
(zu,) = json.loads(p["zusatz"])
assert zu["name"] == kn.ZUSATZ_KNICKEN and zu["menge"] == 3
bericht = "; ".join(erg["bericht"])
assert bericht.count("Schenkel des Knickrahmens") == 3 and "Knickrahmen aus 4 Rohren" in bericht, bericht
from rohrlaser.ansicht3d import entpacken  # noqa: E402
netz = entpacken(p["_netz"])
assert len(netz["p"]) > 3 * len(entpacken(mw[0]["_netz"])["p"]) and netz["lage"]
kandidaten = mw[0].get("_nahtkandidaten") or []
rest = kv.kandidaten_filtern(kandidaten, mw, mw[0]["datei"])
assert len(kandidaten) >= 4 and len(rest) == len(kandidaten) - 3, (len(kandidaten), len(rest))
ok("V2 Übernahme: Länge 1592,7 mm, 3 V-Ausschnitte, Bohrung am dritten Schenkel, Knicken × 3, gefaltetes Netz, "
   "Nahtkandidaten nur am Stoß")

# ------------------------------------------------------------------ V3 Innenwand schräg (3D)
profil = dict(profil_id="QR 40x40x2", form="Quadratrohr", a=40, b=40, wand=2)
blk = dict(kn.lesen(e), schraeg=True)
neu, r = kn.anwenden(e, blk, profil)
neu = sw.v_ergaenzen(neu, profil)
assert neu["d3"] is True and all(z.get("d3") for z in neu["konturen"] if z["art"] == "V-Ausschnitt")
assert "Innenwand schräg (3D)" in kn.kurz(r)
erg3 = sw.rechnen(neu, profil, (10, 50))
assert not erg3["fehler"] and any("Innenwand schräg 3D (Kopf 45°)" in s_["text"] for s_ in erg3["schritte"])
b3 = [b for b in dreid.bearbeitungen(dict(technik=json.dumps(neu), laenge=r["laenge"])) if b["art"] == dreid.V_INNEN]
assert len(b3) == 3 and all(b["winkel"] == 45 and b["laenge"] == 80 for b in b3), b3
zurueck, _ = kn.anwenden(neu, dict(blk, schraeg=None), profil)
assert "d3" not in zurueck and not any(z.get("d3") for z in zurueck["konturen"])
ok("V3 Innenwand schräg: V-Zeilen 3D, Kopf β/2, 3D-Bearbeitung je Knick, ohne schräg wieder 2D")

# ------------------------------------------------------------------ V4 Prüfdialog
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402
app = QApplication.instance() or QApplication([])
mw = messen(speichern(RAHMEN, "rahmen2"))
d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, knick_vorgaben=dict(z=0, freistich=0, k=0.5))
assert d.knick_zeile.isVisibleTo(d) and "4 Rohre" in d.knick_info.text(), d.knick_info.text()
leit = d.knick_erstellen(dialog=lambda dlg: (dlg.schraeg.setChecked(True), QDialog.Accepted)[1])
assert leit == 0 and mw[0]["_knickrahmen"]["schraeg"] and len(d.zeilen) == 1, len(d.zeilen)
assert d.zeilen[0].it.text(d.SP_LAENGE) == "1.592,7" and "Knickrahmen aus 4 Rohren" in d.zeilen[0].it.text(d.SP_HINWEIS)
assert not d.knick_zeile.isVisibleTo(d) and not d.fehler_gruppen
d.knick_loesen(2)
assert not any(m.get("_knickrahmen") or m.get("_knick_von") is not None for m in mw) and len(d.zeilen) == 3
ok("V4 Prüfdialog: Vorschlag, erstellen mit schräger Innenwand, Länge in der Liste, lösen")
