"""Jede Kontur wie in der STEP (Patrick 03.11.2026: „Step Erkennung Konturen Bohrungen Ausbrüche etc verbessern, dass
wirklich jede Kontur erkannt wird“; Grundregel: Konturen zu 100 % wie in der STEP, Lage und Form).

Probe Runde 4 mit 59 ungewöhnlichen Konturen (Rechteck-, Quadrat-, Rundrohr, Flachstahl, L, Blech): Sechskant,
Dreieck, Schlüsselloch, Doppel-D, Kreuz, Bogenlangloch, Ellipse, freies Polygon, Fenster über die ganze Breite,
Bohrung Ø0,5/Ø1, Steg 0,3 mm, Bohrung auf der 0°-Naht, Langloch 500 mm, gedrehtes Rechteck, Rechteck mit Fasen –
die meisten wie in der STEP. Gefunden und behoben:
J1 zwei überlappende Bohrungen gleichen Ø („8“, Doppelbohrung) galten als eine Bohrung (gleicher Radius, aber zwei
   Achsen), bis 3 mm neben der STEP. Jetzt: Bohrung nur mit einer Achse (step_geometrie.gleiche_achse), sonst
   Sonderkontur mit dem Umriss.
J2 Bohrung ganz im Eckradius eines Quadratrohrs: als Kreis gezeichnet, 0,9 mm daneben. Jetzt Sonderkontur, wenn der
   gemessene Umriss mehr als 0,05 mm vom Kreis abweicht (step._kreis_abweichung).
J3 Flachstahl/L: Ausschnitt nur nach Hüllmaß und Schnittlänge eingeteilt – ein Sechskant wurde Langloch (0,6 mm).
   Jetzt wird Langloch/Rechteck gegen den gemessenen Umriss geprüft, sonst Sonderkontur.
J4 Bleche: Rechteck mit R3 ohne Radius (1,2 mm), Rechteck mit Fasen als Rechteck (3,5 mm), Polygone auf 0,05 mm
   genähert, Lage im Editor auf 0,1 mm gerundet, Kontur bei Fehler still weggelassen. Jetzt Rechteck mit Radius
   bzw. Polygon (0,02 mm), Lage auf 0,01 mm, keine Kontur geht verloren, und eine Blech-Gegenprobe (Hinweis).
Runde 5 (Patrick 03.11.2026 „Noch weitere kritische Konturen finden“, 28 Teile):
J5 Bohrung bis an die Rundung bzw. in einer Lochreihe mit Steg 0,5 mm galt als Fließloch (Schnittlänge 0, bis 3 mm
   daneben): Restflächen quer zur Achse lagen näher an der Achse als das Kernloch. Ein Fließloch braucht jetzt Kragen
   bzw. Ringfläche ganz um das Kernloch (step_geometrie.bohrung_art).
J6 Enden mit Hinterschnitt (T-Schlitz, Schlüsselloch-Schlitz, Schwalbenschwanz, Haken, Bohrung halb über das Ende):
   0,4 bis 3 mm daneben. Die Mündung des Ausflugs lag 0,01 mm neben der Stufe des Endumrisses (Stufe ganz
   gezeichnet), Hinterschnitte unter 0,5 mm Breite fielen weg (jetzt ab 0,12 mm), und die Gegenprobe verglich die
   Sonderkontur „Teil von Ende“ (um ABSTAND über der Wand) nur gegen Konturen, nicht gegen die Kanten des Endes.

Aufruf: python tests/test_step_jede_kontur.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Fuse  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from test_rohr_aufgeschnitten import prisma  # noqa: E402
from test_step_kritisch import rrect  # noqa: E402
from rohrlaser import ansicht3d, blech, rohr3d, step, step_gegenprobe  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py
box = wie.box


def fuse(*s):
    a = s[0]
    for b in s[1:]:
        a = BRepAlgoAPI_Fuse(a, b).Shape()
    return a


def zyl_y(x, z, dm, y0=0, lg=60):
    return et.zylinder((x, y0, z), (0, 1, 0), dm, lg)


def sechseck(r, cx, cz):
    return [(cx + r * math.cos(math.pi * i / 3), cz + r * math.sin(math.pi * i / 3)) for i in range(6)]


def rohre():
    re = et.kastenrohr(80, 40, 3, 600, 5)
    rr = et.rundrohr(60.3, 3, 600)
    qr = et.kastenrohr(50, 50, 3, 500, 6)
    return {
        "J1a_RE_Doppelbohrung": et.cut(re, fuse(zyl_y(-4, 300, 10), zyl_y(4, 300, 10))),
        "J1b_RR_Doppelbohrung": et.cut(rr, fuse(zyl_y(0, 296, 10, 10), zyl_y(0, 304, 10, 10))),
        "J2_QR_Bohrung_im_Eckradius": et.cut(qr, et.zylinder((40, 40, 250), (-1 / math.sqrt(2), -1 / math.sqrt(2), 0),
                                                             4, 30)),
        "R1_RE_Sechskant": et.cut(re, prisma(sechseck(12, 0, 200), "xz", 10, 40)),
        "R2_RE_Schluesselloch": et.cut(re, fuse(zyl_y(0, 200, 14), box(-3, 0, 200, 6, 60, 25))),
        "R3_RE_DoppelD": et.cut(re, BRepAlgoAPI_Common(zyl_y(0, 300, 20), box(-7, 0, 280, 14, 60, 40)).Shape()),
        "R4_RR_Bohrung_auf_Naht": et.cut(rr, zyl_y(0, 300, 12)),
    }


def offene():
    fl = et.profil([(-30, 0), (30, 0), (30, 8), (-30, 8)], 500)
    l_ = et.profil([(0, 0), (50, 0), (50, 5), (5, 5), (5, 50), (0, 50)], 500, {(5, 5): 5})
    return {"J3a_FL_Sechskant": et.cut(fl, prisma(sechseck(8, 0, 150), "xz", -5, 20)),
            "J3b_L_Doppelbohrung": et.cut(l_, fuse(zyl_y(24, 200, 8, -5, 20), zyl_y(30, 200, 8, -5, 20))),
            "R5_FL_Langloch": et.cut(fl, fuse(zyl_y(0, 300, 10, -5, 20), zyl_y(0, 330, 10, -5, 20),
                                              box(-5, -5, 300, 10, 20, 30)))}


def bleche():
    def platte():
        return box(0, 0, 0, 200, 100, 3)

    def zz(x, y, d):
        return et.zylinder((x, y, -1), (0, 0, 1), d, 5)
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Pnt, gp_Vec

    def pz(pts):
        p = BRepBuilderAPI_MakePolygon()
        for x, y in pts:
            p.Add(gp_Pnt(x, y, -1))
        p.Close()
        return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(p.Wire()).Face(), gp_Vec(0, 0, 5)).Shape()
    return {"J4a_BL_Rechteck_R3": et.cut(platte(), rrect(40, 40, -1, 40, 20, 5, 3, "z")),
            "J4b_BL_Rechteck_Fasen": et.cut(platte(), pz([(45, 40), (50, 35), (70, 35), (75, 40), (75, 60), (70, 65),
                                                          (50, 65), (45, 60)])),
            "J4c_BL_Doppelbohrung": et.cut(platte(), fuse(zz(46, 50, 10), zz(54, 50, 10))),
            "J4d_BL_Sechskant": et.cut(platte(), pz(sechseck(12, 50, 50))),
            "R6_BL_Rechteck": et.cut(platte(), box(120, 30, -1, 40, 20, 5))}


def messen(f, tmp):
    for n, s in f.items():
        et.schreibe(s, n, tmp)
    step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp)] + [str(tmp / (n + ".step")) for n in f])
    ms = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)}
    assert len(ms) == len(f), sorted(set(f) - set(ms))
    return ms


def runde5():
    re = et.kastenrohr(80, 40, 3, 600, 5)
    rr = et.rundrohr(60.3, 3, 600)
    qr = et.kastenrohr(50, 50, 3, 500, 6)
    s = re
    for i in range(6):                      # Steg 0,5 mm, die letzte Bohrung reicht in die Rundung
        s = et.cut(s, zyl_y(19 + i * 3.5, 200, 3))

    def oben(pts):
        return prisma(pts, "xz", 10, 40)
    return {"J5a_RE_Lochreihe_bis_Rundung": s,
            "J5b_RE_Bohrung_bis_Seite": et.cut(re, zyl_y(-35, 300, 10)),
            "J6a_RE_Bohrung_halb_ueber_Ende": et.cut(re, zyl_y(0, 598, 10)),
            "J6b_RE_T_Schlitz_Ende": et.cut(re, fuse(box(-3, 10, 580, 6, 20, 30), box(-10, 10, 570, 20, 20, 10))),
            "J6c_RR_Schluesselschlitz_Ende": et.cut(rr, fuse(box(-3, 15, 580, 6, 30, 30), zyl_y(0, 578, 12, 15, 30))),
            "J6d_RE_Schwalbenschwanz_Ende": et.cut(re, oben([(-5, 601), (5, 601), (10, 585), (-10, 585)])),
            "J6e_QR_Haken_Ende": et.cut(qr, oben([(-5, 501), (0, 501), (0, 490), (10, 490), (10, 480), (-5, 480)]))}


def editor(ms, offen=False):
    """Übernehmen, Editor öffnen; Gegenprobe (alle) und Linien gegen die STEP (geschlossene Rohre)."""
    from PySide6.QtWidgets import QApplication
    from rohrlaser.schneidweg_dialog import SchneidwegDialog
    app = QApplication.instance() or QApplication([])  # noqa: F841
    out, fehler = {}, 0
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        erg = step.uebernehmen(list(ms.values()), [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               neue_profile=True)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        for p in erg["positionen"]:
            name = p["artikel"]
            ab = p.get("_step_abweichung")
            d = SchneidwegDialog(None, p, k.profile[p["profil_id"]], dict(maschine="T11", stange=6000), k,
                                 db.tabellen(), db)
            e = d.eingaben()
            weit = ab if ab is not None else 99.0
            if not offen:
                n = wie.netz_wie_konstruiert(d)
                sn = ansicht3d.entpacken(ms[name]["_netz"])
                for arten, abst in ((("K",), rohr3d.ABSTAND), (("EA", "EB"), 0.0)):
                    mod = [z for a in arten for z in n["l"].get(a, [])]
                    st = [z for a in arten for z in sn["l"].get(a, [])]
                    if mod or st:
                        weit = max(weit, max(wie._abstand(mod, st), wie._abstand(st, mod)) - abst) if mod and st \
                            else 99.0
            grenze = step_gegenprobe.GRENZE if offen else TOL
            if weit > grenze:
                fehler += 1
                print(f"FEHLER {name}: {weit:.3f} mm neben der STEP")
            else:
                print(f"OK     {name}: {weit:+.3f} mm, {[z.get('art') for z in e['konturen']]}")
            out[name] = e["konturen"]
    return out, fehler


def einheiten():
    kreis = [(5 * math.cos(math.radians(w)), 5 * math.sin(math.radians(w))) for w in range(0, 360, 5)]
    assert step._kreis_abweichung(kreis, 10) < 0.01
    assert step._kreis_abweichung([(x * 1.1, y) for x, y in kreis], 10) > 0.4
    assert step._kreis_abweichung(kreis[:36], 10) > 4         # halber Kreis: Lücke
    b = dict(innen=2, konturen_lage=[dict(art="Bohrung", x=1, y=1, durchmesser=5, abweichung=0.0)])
    assert "1 von 2 Innenkonturen ohne Lage" in step.blech_gegenprobe(b)
    b = dict(innen=1, konturen_lage=[dict(art="Polygon", x=1, y=1, abweichung=0.3)])
    assert "0,3 mm" in step.blech_gegenprobe(b)
    b = dict(innen=1, konturen_lage=[dict(art="Kontur", x=1, y=1, schnittlaenge=40)])
    assert "ohne erkannte Form" in step.blech_gegenprobe(b)
    assert step.blech_gegenprobe(dict(innen=1, konturen_lage=[dict(art="Bohrung", x=1, y=1, durchmesser=5,
                                                                 abweichung=0.01)])) is None
    print("OK     Kreis-Abweichung, Blech-Gegenprobe")


def main():
    einheiten()
    fehler = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "r").mkdir()
        ms = messen(rohre(), tmp / "r")
        for n in ("J1a_RE_Doppelbohrung", "J1b_RR_Doppelbohrung"):
            arten = [x["art"] for x in json.loads(ms[n]["konturen_liste"]) if x["art"] not in ("Ende A", "Ende B")]
            assert arten == ["Sonderkontur"], (n, arten)       # keine Bohrung Ø10
            assert not json.loads(ms[n].get("bohrungen") or "{}") if isinstance(ms[n].get("bohrungen"), str) \
                else not ms[n].get("bohrungen"), (n, ms[n].get("bohrungen"))
        out, fe = editor(ms)
        fehler += fe
        for n in ("J1a", "J1b", "J2", "R1", "R2", "R3"):
            kn = next(v for k_, v in out.items() if k_.startswith(n))
            assert [z.get("art") for z in kn] == ["Sonderkontur"], (n, kn)
        assert [z.get("art") for z in out["R4_RR_Bohrung_auf_Naht"]] == ["Bohrung"], out["R4_RR_Bohrung_auf_Naht"]
        (tmp / "r5").mkdir()
        ms = messen(runde5(), tmp / "r5")
        for n, m in ms.items():
            arten = [x["art"] for x in json.loads(m["konturen_liste"])]
            assert "Fließloch" not in arten, (n, arten)
        out, fe = editor(ms, offen=True)        # Gegenprobe (Konturen und Enden zusammen)
        fehler += fe
        assert len(out["J5a_RE_Lochreihe_bis_Rundung"]) == 6, out["J5a_RE_Lochreihe_bis_Rundung"]
        for n in ("J6b", "J6c", "J6e"):
            kn = next(v for k_, v in out.items() if k_.startswith(n))
            assert kn and all(z.get("ende_teil") == "B" for z in kn), (n, kn)
        (tmp / "o").mkdir()
        ms = messen(offene(), tmp / "o")
        out, fe = editor(ms, offen=True)
        fehler += fe
        assert [z.get("art") for z in out["J3a_FL_Sechskant"]] == ["Sonderkontur"], out["J3a_FL_Sechskant"]
        assert [z.get("art") for z in out["J3b_L_Doppelbohrung"]] == ["Sonderkontur"], out["J3b_L_Doppelbohrung"]
        assert [z.get("art") for z in out["R5_FL_Langloch"]] == ["Langloch"], out["R5_FL_Langloch"]
        (tmp / "b").mkdir()
        ms = messen(bleche(), tmp / "b")
        soll = {"J4a": ("Rechteck", 3.0), "J4b": ("Polygon", None), "J4c": ("Polygon", None), "J4d": ("Polygon", None),
                "R6": ("Rechteck", None)}
        for n, m in ms.items():
            b = step.blech(m)
            kl = b["konturen_lage"]
            assert len(kl) == 1 and (kl[0]["art"], kl[0].get("radius")) == soll[n[:3].rstrip("_")], (n, kl)
            assert kl[0]["abweichung"] <= 0.03, (n, kl[0]["abweichung"])
            assert step.blech_gegenprobe(b) is None, (n, step.blech_gegenprobe(b))
            z = blech._konturen_mit_lage(kl)[0]
            if n.startswith("J4a"):
                assert z["r"] == 3.0, z
            print(f"OK     {n}: {kl[0]['art']}, {kl[0]['abweichung']} mm")
    print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
    return fehler


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
