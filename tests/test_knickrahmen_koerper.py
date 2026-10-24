"""Knickrahmen aus einem Körper (Plan K1-3, Fall A): derselbe Rahmen wie in test_knickverbindung.py (QR 40 × 40 × 2,
500 × 300 außen, Bohrung im dritten Schenkel), aber als ein verschmolzener Körper.
- R1 Messung: Körper erkannt, an den Ecken in vier Schenkel geteilt und je Schenkel gemessen, Prüfstatus „prüfen“,
  STEP-JSON 1.17 mit knick_schenkel; ein gerades Rohr bleibt ohne.
- R2 Übernahme: eine Position mit 1592,7 mm, 3 V-Ausschnitten, Bohrung an der richtigen Stelle, Knicken × 3,
  Herkunft STEP-Körper, Netz des Körpers.
- R3 U-Rahmen offen: drei Schenkel, zwei Knicke.
- R4 Prüfdialog: eine Zeile „Knickrahmen (3 Knicke) aus einem Körper“ mit der gestreckten Länge, bearbeiten.
- R5 gestreckt gezeichnet (gerades Rohr mit drei V-Ausschnitten, Enden 45°): Knickwinkel, Schenkel 500/300/500/300,
  geschlossen; Übernahme mit V-Ausschnitten statt Sonderkonturen und Knicken × 3; ein Schlitz ist kein V.
- R6 Teile-Editor: Gruppe „Knicke“ mit Rahmen und je Knick einem Eintrag (Herkunft STEP), Klick wählt die V-Zeile.

Aufruf: python tests/test_knickrahmen_koerper.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism  # noqa: E402
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: E402
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain  # noqa: E402
from OCP.TopoDS import TopoDS_Compound  # noqa: E402
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec  # noqa: E402

import step_ergebnis  # noqa: E402
import step_messen  # noqa: E402
from rohrlaser import knickrahmen as kn, knickverbindung as kv, schneidweg as sw, step  # noqa: E402
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
    """Rohr a × a × s entlang x von 0 bis L, Außenseite y = 0, 45°-Gehrung an beiden Enden."""
    aussen = prisma([(0, 0), (L, 0), (L - a, a), (a, a)], 0, a)
    innen = prisma([(s, s), (L - s, s), (L - a + s, a - s), (a - s, a - s)], s, a - s)
    k = BRepAlgoAPI_Cut(aussen, innen).Shape()
    if loch:
        k = BRepAlgoAPI_Cut(k, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(loch, a / 2, -5), gp_Dir(0, 0, 1)), 4.25,
                                                        a + 10).Shape()).Shape()
    return k


def lage(shape, grad, dx, dy):
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(grad))
    v = gp_Trsf()
    v.SetTranslation(gp_Vec(dx, dy, 0))
    return BRepBuilderAPI_Transform(BRepBuilderAPI_Transform(shape, t).Shape(), v).Shape()


def koerper(teile):
    """Teile zu einem Körper verschmelzen (gemeinsame Flächen zusammengefasst)."""
    s = teile[0]
    for t in teile[1:]:
        s = BRepAlgoAPI_Fuse(s, t).Shape()
    u = ShapeUpgrade_UnifySameDomain(s, True, True, True)
    u.Build()
    return u.Shape()


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
    mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(txt), netze), txt.with_suffix(".json"))
    return mw, json.loads(txt.with_suffix(".json").read_text(encoding="utf-8"))


tmp = Path(tempfile.mkdtemp())
RAHMEN = [lage(schenkel(500), 0, 0, 0), lage(schenkel(300), 90, 500, 0), lage(schenkel(500, loch=100), 180, 500, 300),
          lage(schenkel(300), 270, 0, 300)]
PROFIL = dict(form="Quadratrohr", a=40, b=40, wand=2)

# ------------------------------------------------------------------ R1 Messung
mw, js = messen(speichern([koerper(RAHMEN)], "rahmen"))
(m,) = mw
assert m["profilform"] == "Quadratrohr" and m["pruefstatus"] == "prüfen" and float(m["laenge"]) == 1600.0, m["laenge"]
teile = kv.stuecke(m)
assert len(teile) == 4 and sorted(round(float(t["laenge"]), 1) for t in teile) == [300.0, 300.0, 500.0, 500.0]
assert all(kv.lage(t) for t in teile) and "Knickrahmen aus einem Körper" in m["hinweise"]
assert sum(1 for t in teile if t["bohrungen"]) == 1
(kj,) = js["dateien"][0]["koerper"]
assert js["schema_version"] == step_ergebnis.SCHEMA_VERSION >= "1.17" and len(kj["knick_schenkel"]) == 4
mg, jg = messen(speichern([schenkel(500)], "gerade"))
assert not mg[0].get("knick_schenkel") and jg["dateien"][0]["koerper"][0]["knick_schenkel"] is None
ok("R1 Messung: ein Körper, vier Schenkel 500/300/500/300 je gemessen, prüfen, JSON 1.17; gerades Rohr ohne")

# ------------------------------------------------------------------ R2 Übernahme ins Angebot
db = Datenbank(tmp / "rohrlaser.db")
assert kv.koerper_vorbereiten(m, dict(k=0.5)) and m["_knick_laenge"] == 1592.7 and kv.ist_koerper(m)
k = kv.kette(teile, range(4))
assert k["geschlossen"] and k["beta"] == 90.0
m["_uebernehmen"] = True
erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", 2, neue_profile=True,
                       zusatz_katalog=db.zeilen("zusatzarbeiten"))
(p,) = erg["positionen"]
assert p["laenge"] == 1592.7, p["laenge"]
e = sw.lesen(p["technik"])
r = kn.rahmen(kn.lesen(e), PROFIL)
vs = [z for z in e["konturen"] if z["art"] == "V-Ausschnitt"]
assert [z["x"] for z in vs] == [x["x"] for x in r["knicke"]] and e["knickrahmen"]["herkunft"] == kv.HERKUNFT_KOERPER
nr3 = next(n for n, t in enumerate(m["_knick_teile"]) if teile[t["i"]]["bohrungen"])
start = sum(r["schenkel"][:nr3]) - nr3 * r["vs"][0]
bohr = [z for z in e["konturen"] if z["art"] == "Bohrung"]     # 100 mm hinter der Ecke, an der der Schenkel beginnt
assert len(bohr) == 2 and all(abs(z["x"] - (start + 100)) < 0.6 for z in bohr), (bohr, start)
assert abs(bohr[0]["x"] - 895.1) < 0.1      # wie aus vier Einzelrohren (test_knickverbindung.py)
assert p["einstiche"] == 2 + 3 + 2 and e["a"]["winkel"] == 45.0 and e["b"]["winkel"] == 45.0
(zu,) = json.loads(p["zusatz"])
assert zu["name"] == kn.ZUSATZ_KNICKEN and zu["menge"] == 3
assert "Knickrahmen aus einem Körper" in "; ".join(erg["bericht"])
from rohrlaser.ansicht3d import entpacken  # noqa: E402
assert entpacken(p["_netz"])["p"] and entpacken(p["_netz"])["lage"]
TECHNIK_R2 = p["technik"]
ok("R2 Übernahme: 1592,7 mm, 3 V-Ausschnitte, Bohrung am Schenkel, Knicken × 3, Herkunft STEP-Körper, Netz")

# ------------------------------------------------------------------ R3 offener U-Rahmen
mu, _ = messen(speichern([koerper(RAHMEN[:3])], "u_rahmen"))
assert kv.koerper_vorbereiten(mu[0]), mu[0].get("_knick_fehler")
blk = mu[0]["_knickrahmen"]
assert not blk["geschlossen"] and len(blk["schenkel"]) == 3 and blk["schenkel"][1] == 300.0, blk
assert "2 Knicke" in kv.text(mu[0]), kv.text(mu[0])
ok("R3 U-Rahmen: offen, drei Schenkel, zwei Knicke")

# ------------------------------------------------------------------ R4 Prüfdialog
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402
app = QApplication.instance() or QApplication([])
mw, _ = messen(speichern([koerper(RAHMEN)], "rahmen2"))
d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, knick_vorgaben=dict(z=0, freistich=0, k=0.5))
assert len(d.zeilen) == 1 and not d.fehler_gruppen and not d.knick_zeile.isVisibleTo(d)
it = d.zeilen[0].it
assert it.text(d.SP_LAENGE) == "1.592,7" and "Knickrahmen (3 Knicke) aus einem Körper" in it.text(d.SP_HINWEIS), \
    it.text(d.SP_HINWEIS)
vorher = [t["i"] for t in mw[0]["_knick_teile"]]
assert d.knick_bearbeiten(0, dialog=lambda dlg: (dlg.umkehren.setChecked(True), dlg.schraeg.setChecked(True),
                                                 QDialog.Accepted)[2])
nachher = [t["i"] for t in mw[0]["_knick_teile"]]
assert nachher[0] == vorher[0] and nachher[1:] == vorher[:0:-1] and mw[0]["_knickrahmen"]["schraeg"]
assert mw[0]["_knick_laenge"] == 1592.7 and len(d.zeilen) == 1
ok("R4 Prüfdialog: eine Zeile mit 1.592,7 mm, Knickrahmen (3 Knicke) aus einem Körper, bearbeiten")

# ------------------------------------------------------------------ R5 gestreckt gezeichnet (vor dem Knicken)
r = kn.rahmen(dict(schenkel=[500, 300, 500, 300], beta=90, geschlossen=True, steg="oben", k=0.5), PROFIL)
L, a, s_ = r["laenge"], 40.0, 2.0


def gestreckt(v_form=True):
    rohr = BRepAlgoAPI_Cut(prisma([(0, 0), (L, 0), (L, a), (0, a)], 0, a),
                           prisma([(0, s_), (L, s_), (L, a - s_), (0, a - s_)], s_, a - s_)).Shape()
    for kn_ in r["knicke"]:
        x, hw = kn_["x"], kn_["w"] / 2 * (a + 1 - s_) / (a - s_)
        form = [(x, s_), (x + hw, a + 1), (x - hw, a + 1)] if v_form else \
            [(x - 5, s_), (x + 5, s_), (x + 5, a + 1), (x - 5, a + 1)]
        rohr = BRepAlgoAPI_Cut(rohr, prisma(form, -1, a + 1)).Shape()
    rohr = BRepAlgoAPI_Cut(rohr, prisma([(-1, -1), (a + 1, a + 1), (-1, a + 1)], -1, a + 1)).Shape()
    return BRepAlgoAPI_Cut(rohr, prisma([(L + 1, -1), (L + 1, a + 1), (L - a - 1, a + 1)], -1, a + 1)).Shape()


mw, _ = messen(speichern([gestreckt()], "gestreckt"))
(m,) = mw
assert not m.get("knick_schenkel") and len(kv.v_ausschnitte(m)) == 3, m["konturen_liste"]
assert kv.koerper_vorbereiten(m, dict(k=0.5)) and m["_knick_v"] and m["pruefstatus"] == "prüfen"
blk = m["_knickrahmen"]
assert blk["beta"] == 90.0 and blk["geschlossen"] and [round(x) for x in blk["schenkel"]] == [500, 300, 500, 300], blk
assert abs(m["_knick_laenge"] - 1592.7) < 0.05 and "gestreckt gezeichnet" in kv.text(m)
m["_uebernehmen"] = True
erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", 2, neue_profile=True,
                       zusatz_katalog=db.zeilen("zusatzarbeiten"))
(p,) = erg["positionen"]
e = sw.lesen(p["technik"])
arten = [z["art"] for z in e["konturen"]]
assert arten.count("V-Ausschnitt") == 3 and "Sonderkontur" not in arten and abs(p["laenge"] - 1592.7) < 0.05, arten
(zu,) = json.loads(p["zusatz"])
assert zu["menge"] == 3 and p["einstiche"] == 2 + 3
schlitz, _ = messen(speichern([gestreckt(False)], "schlitz"))
assert not kv.v_ausschnitte(schlitz[0]) or not kv.koerper_vorbereiten(schlitz[0])
ok("R5 gestreckt gezeichnet: β 90°, Schenkel 500/300/500/300, geschlossen, V-Ausschnitte statt Sonderkonturen, "
   "Knicken × 3; Schlitz kein V")

# ------------------------------------------------------------------ R6 Teile-Editor, Gruppe Knicke
from rohrlaser import teile_editor as te  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402
e = sw.lesen(TECHNIK_R2)
knicke = [x for x in te.merkmale_rohr(e, 1592.7) if x.gruppe == "Knicke"]
assert len(knicke) == 4 and all(x.herkunft == te.STEP for x in knicke), knicke
assert knicke[-1].id == "knickrahmen" and "4 Schenkel 500 / 300 / 500 / 300" in knicke[-1].text, knicke[-1].text
assert not any(x.gruppe == "Innenkonturen" and "V-Ausschnitt" in x.text for x in te.merkmale_rohr(e, 1592.7))
k_ = db.kontext()
pd = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1592.7, stueck=10, technik=TECHNIK_R2)
dlg = SchneidwegDialog(None, pd, k_.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k_, db.tabellen(), db)
ed = dlg.editor
gruppen = [ed.baum.topLevelItem(i).text(0) for i in range(ed.baum.topLevelItemCount())]
assert gruppen.index("Knicke") == gruppen.index("Innenkonturen") + 1, gruppen
ed.waehlen(knicke[1].id)
r = int(knicke[1].id.split(":")[1])
assert dlg.tabelle.currentRow() == r or r in {i.row() for i in dlg.tabelle.selectedIndexes()}
ed.waehlen("knickrahmen")
dlg.reject()
ok("R6 Teile-Editor: Gruppe Knicke (3 Knicke + Rahmen, Herkunft STEP), Auswahl zeigt die V-Zeile")
