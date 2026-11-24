"""Kritische Konturen im STEP-Import und Editor (Patrick 31.10.2026: „Erweitere den STEP-Import und Editor mit weiteren
kritischen Konturen und Tests“; Grundregel: Konturen zu 100 % wie in der STEP, Lage und Form).

Probe mit 46 schwierigen Teilen (RE/QR/RR/L/U: Langlöcher längs, quer, schräg, Steckschlitze, Ausklinkungen an einem
und beiden Enden, Bohrung auf der Ecke, Konturen nahe/in der Gehrung, zweiachsiger Schnitt, Lochreihe, Steg 1 mm,
Durchbrüche, Fischmaul, Kreuzschlitz). Hier eine Auswahl, je Teil gemessen, übernommen, im Rohr-Editor geöffnet und
dessen 3D-Linien (Konturen, Enden) gegen die Linien des STEP-Netzes verglichen (±0,06 mm, beide Richtungen).

Vorher gefunden und behoben:
K1 Langloch quer im Rundrohr (läuft um den Umfang): abgewickelt sind die Enden keine Halbkreise – galt als
   Rechteckausschnitt, im Editor ein Rechteck, 1,9 mm neben der STEP. Jetzt: weicht der gemessene Umriss mehr als
   0,05 mm vom Langloch/Rechteck ab, wird die Zeile Sonderkontur mit dem Umriss der STEP (step._grundform_abweichung).
K2 außermittige Bohrung im Rundrohr (Achse nicht durch die Rohrmitte) und K3 Schrägbohrung in einer ebenen Wand: im
   Editor ein Kreis, außen ist es eine Ellipse (0,6–0,9 mm). Ohne 3D-Schnitt jetzt Sonderkontur mit Umriss (Text
   „schräge Bohrung …“); mit 3D bleibt es eine geneigte Bohrung, im Rundrohr mit dem gemessenen Umriss, solange Maße
   und Neigung wie gemessen bleiben (sonst Grundform, Schneidweg-Rechner).
K4 scharfkantiges U, das so in den Stammdaten steht, mit Ausklinkung am Flanschende: wurde Kantteil (passt in kein
   Rohr ganz), ohne Ausklinkung blieb es U-Profil. Jetzt wie kantteile_vorbelegen: in den Stammdaten = Profil.
Enden (Patrick 31.10.2026: „Gibt es noch mehr Konturen/Geometrie an Rohrende und -anfang? Bitte prüfen“): zweite
Probe mit 32 Enden (Gehrungen über Breite/Höhe/Eck, parallel und gegenläufig, Rundrohr 30/45/60°, zweiachsig, Spitze,
Dach, V-Kerbe, Zapfen, Rundkerbe, Gabel, Stufe, zwei Ausklinkungen, Gehrung mit Ausklinkung bzw. Bohrung an der Ecke,
Steckschlitz, Fischmaul auf Rundrohr gerade/schräg/mit Versatz/gleicher Ø, Rechteck- und Quadratrohr auf Rundrohr,
beide Enden verdreht): alle wie in der STEP, kein Fehler gefunden. Die Auswahl E… sichert sie; gekrümmte Enden (Sattel,
Rundrohr-Gehrung) bis TOL_ENDE, weil beide Linien Netze sind (Sehnenfehler).
K6 Rechteck mit Eckradien (dritte Probe, Patrick 31.10.2026 „Noch weiter Konturen finden und verbessern“; 18 Teile,
   alle wie in der STEP): ein Rechteckausschnitt mit R2/R3/R5 an den Ecken wurde Sonderkontur (nicht mit Maßen
   bearbeitbar). Jetzt Zeile Rechteck mit Eckradius aus der Schnittlänge (step._eckradius), wenn der Umriss damit auf
   0,05 mm passt; über eine Ecke bleibt es Sonderkontur.
K5 Gegenprobe beim Übernehmen (step_gegenprobe) auch für offene Profile (L, U, C, Flachstahl): Modell an Ende A
   ausgerichtet; eine um 2 mm verschobene Kontur gibt den Hinweis.

Aufruf: python tests/test_step_kritisch.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, rohr3d, step, step_gegenprobe  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py
TOL_ENDE = 0.1      # mm gekrümmte Enden (Sattel, Rundrohr-Gehrung): = step_gegenprobe.GRENZE
box, dreh = wie.box, wie.dreh


def langloch(p, achse, laenge, breite, richtung, tiefe=60):
    """Werkzeug für ein Langloch: Mitte p, Bohrrichtung achse, Längsrichtung richtung (Einheitsvektoren)."""
    r, h = breite / 2, laenge / 2 - breite / 2
    a = [p[i] - h * richtung[i] for i in range(3)]
    b = [p[i] + h * richtung[i] for i in range(3)]
    t = et.zylinder([a[i] - tiefe / 2 * achse[i] for i in range(3)], achse, breite, tiefe)
    t = BRepAlgoAPI_Fuse(t, et.zylinder([b[i] - tiefe / 2 * achse[i] for i in range(3)], achse, breite, tiefe)).Shape()
    q = [richtung[1] * achse[2] - richtung[2] * achse[1], richtung[2] * achse[0] - richtung[0] * achse[2],
         richtung[0] * achse[1] - richtung[1] * achse[0]]
    o = [a[i] - tiefe / 2 * achse[i] + r * q[i] for i in range(3)]
    k = BRepPrimAPI_MakeBox(gp_Ax2(gp_Pnt(*o), gp_Dir(*achse), gp_Dir(*richtung)), 2 * h, 2 * r, tiefe).Shape()
    return BRepAlgoAPI_Fuse(t, k).Shape()


def rrect(x0, y0, z0, dx, dy, dz, r, achse="y"):
    """Quader mit gerundeten Kanten parallel zur achse (Werkzeug für ein Rechteck mit Eckradius)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    b = box(x0, y0, z0, dx, dy, dz)
    f, ex = BRepFilletAPI_MakeFillet(b), TopExp_Explorer(b, TopAbs_EDGE)
    i = "xyz".index(achse)
    while ex.More():
        e = TopoDS.Edge(ex.Current())
        d = BRepAdaptor_Curve(e).Line().Direction()
        if abs(abs((d.X(), d.Y(), d.Z())[i]) - 1) < 1e-9:
            f.Add(r, e)
        ex.Next()
    return f.Shape()


def teile():
    f = {}
    re = et.kastenrohr(80, 40, 3, 600, 5)
    rr = et.rundrohr(60.3, 3, 600)
    qr = et.kastenrohr(50, 50, 3, 500, 6)
    # behoben (K1-K3)
    f["K1_RR_Langloch_quer"] = et.cut(rr, langloch((0, 30, 300), (0, -1, 0), 30, 10, (1, 0, 0)))
    f["K2_RR_Bohrung_aussermittig"] = et.cut(rr, et.zylinder((12, 40, 250), (0, -1, 0), 16, 30))
    f["K2_RR_Bohrung_aussermittig_durch"] = et.cut(rr, et.zylinder((10, 40, 350), (0, -1, 0), 8, 80))
    f["K3_RE_Schraegbohrung_30"] = et.cut(re, dreh(et.zylinder((0, 30, 300), (0, -1, 0), 12, 20), 30, (1, 0, 0),
                                                   (0, 20, 300)))
    # K6 Rechteck mit Eckradius: oben längs, oben quer, Seitenwand, im Raum gedreht; über die Ecke bleibt Sonderkontur
    f["K6a_RE_Rechteck_R3"] = et.cut(re, rrect(-15, 10, 200, 30, 20, 50, 3))
    f["K6b_RE_Rechteck_R5_quer"] = et.cut(re, rrect(-25, 10, 300, 50, 20, 20, 5))
    f["K6c_RE_Rechteck_R2_Seite"] = et.cut(re, rrect(35, -10, 420, 10, 20, 40, 2, "x"))
    f["K6d_RE_im_Raum_Rechteck_R3"] = et.drehe_beliebig(et.cut(re, rrect(-15, 10, 200, 30, 20, 50, 3)))
    f["K6e_RE_Rechteck_R3_Ecke"] = et.cut(re, rrect(25, 5, 300, 30, 30, 40, 3, "z"))
    # waren schon richtig, bleiben so (Auswahl der Probe)
    f["R01_RE_Langloch_laengs"] = et.cut(re, langloch((0, 20, 200), (0, -1, 0), 60, 12, (0, 0, 1)))
    f["R02_RE_Langloch_Seite_schraeg"] = et.cut(re, langloch((40, 0, 300), (-1, 0, 0), 40, 8,
                                                             (0, math.sin(math.radians(30)), math.cos(math.radians(30)))))
    f["R03_RE_Steckschlitz_2Waende"] = et.cut(re, box(-50, -10, 250, 100, 4, 40))
    f["R04_RE_Ausklinkung_Ecke_EndeB"] = et.cut(re, box(20, 5, 560, 30, 30, 41))
    f["R05_RE_Bohrung_auf_Ecke"] = et.cut(re, et.zylinder((60, 40, 300), (-1 / math.sqrt(2), -1 / math.sqrt(2), 0),
                                                          10, 40))
    f["R06_RE_Gehrung_schneidet_Langloch"] = et.cut(et.gehrung(re, 600, 30),
                                                    langloch((0, 20, 560), (0, -1, 0), 60, 12, (0, 0, 1)))
    f["R07_RE_Gehrung2achs_Langloch"] = et.cut(et.schraeg_ende(re, 560, 20, 30),
                                               langloch((0, 20, 250), (0, -1, 0), 40, 10, (0, 0, 1)))
    f["R08_RE_Steg_1mm"] = et.cut(et.cut(re, box(-30, 10, 100, 20, 20, 40)), box(-9, 10, 100, 20, 20, 40))
    f["R09_RE_Durchbruch_schraeg"] = et.cut(re, dreh(et.zylinder((0, -40, 300), (0, 1, 0), 24, 80), 45, (1, 0, 0),
                                                     (0, 0, 300)))
    f["R10_QR_Fischmaul"] = et.cut(qr, et.zylinder((-60, 0, 515), (1, 0, 0), 50, 120))
    f["R11_QR_Kreuzschlitz"] = et.cut(et.cut(qr, box(-30, -2, 200, 60, 4, 50)), box(-2, -30, 200, 4, 60, 50))
    f["R12_RE_Gehrung_Ausklinkung_gleiches_Ende"] = et.cut(et.gehrung(re, 600, 30), box(-20, 10, 540, 40, 20, 70))
    f["R13_RR_Schlitz_Ende_B"] = et.cut(rr, box(-3, -40, 560, 6, 80, 41))
    f["R14_RR_Fischmaul_beide_Bohrung"] = et.cut(et.cut(et.cut(
        rr, et.zylinder((-60, 0, -20), (1, 0, 0), 60.3, 120)), et.zylinder((-60, 0, 620), (1, 0, 0), 60.3, 120)),
        et.zylinder((0, 40, 300), (0, -1, 0), 10, 20))
    # Enden (zweite Probe)
    def fm(shape, cz, d, winkel=0, versatz=0, achse=(1, 0, 0)):
        """Fischmaul: Gegenrohr Ø d quer (achse), Mitte bei z = cz, dahinter alles weg; schräg um winkel."""
        q = (0, 1, 0) if achse == (1, 0, 0) else (1, 0, 0)
        z = et.zylinder(tuple(-200 * achse[i] + versatz * q[i] + (cz if i == 2 else 0) for i in range(3)), achse, d, 400)
        t = BRepAlgoAPI_Fuse(z, box(-200, -200, cz, 400, 400, 400)).Shape()
        return et.cut(shape, dreh(t, winkel, q, (0, 0, cz)) if winkel else t)
    f["E01_RE_Gehrung45_gegenlaeufig"] = et.schraeg_ende(et.schraeg_ende(re, 560, 0, 45), 40, 0, 45, ende_b=False)
    f["E03_QR_Gehrung_parallel"] = et.schraeg_ende(et.schraeg_ende(qr, 475, 0, 45), 25, 0, -45, ende_b=False)
    f["E05_RE_zweiachsig_beide"] = et.schraeg_ende(et.schraeg_ende(re, 560, 20, 30), 40, -15, 25, ende_b=False)
    f["E06_RE_Spitze"] = et.schraeg_ende(et.schraeg_ende(re, 580, 0, 30), 580, 0, -30)
    f["E07_RE_V_Kerbe"] = et.cut(re, wie_prisma([(-15, 601), (15, 601), (0, 575)], 30))
    f["E08_RE_Zapfen"] = et.cut(et.cut(re, box(-50, -30, 570, 30, 60, 40)), box(20, -30, 570, 30, 60, 40))
    f["E09_RE_Rundkerbe"] = et.cut(re, et.zylinder((0, -30, 600), (0, 1, 0), 30, 60))
    f["E10_RR_Gabel"] = et.cut(rr, box(-40, -4, 550, 80, 8, 60))
    f["E15_RE_Stufe"] = et.cut(re, box(-50, 0, 580, 100, 30, 30))
    f["E19_QR_Gehrung_ueber_Eck"] = et.schraeg_ende(qr, 470, 30, 30)
    f["E22_RE_Gehrung_Ausklinkung"] = et.cut(et.schraeg_ende(re, 560, 0, 30), box(-20, 10, 520, 40, 20, 60))
    f["E23_RR_Steckschlitz"] = et.cut(rr, box(-1.5, 0, 540, 3, 40, 70))
    f["E24_RE_Dach"] = et.schraeg_ende(et.schraeg_ende(re, 590, 30, 0), 590, -30, 0)
    f["E25_RR_Spitze"] = et.schraeg_ende(et.schraeg_ende(rr, 580, 0, 30), 580, 0, -30)
    f["E31_RR_Fischmaul_30_D80"] = fm(rr, 600, 80, 30)
    f["E32_RE_auf_RR100"] = fm(re, 600, 100, achse=(0, 1, 0))
    f["E33_RR_Fischmaul_Versatz"] = fm(rr, 600, 88.9, versatz=10)
    f["E34_RR_Gehrung45"] = et.schraeg_ende(rr, 569, 0, 45)
    f["E35_QR_auf_RR60"] = fm(qr, 500, 60)
    f["E36_RR_Fischmaul_beide_verdreht"] = fm(dreh(fm(rr, 600, 60.3), 180, (1, 0, 0), (0, 0, 300)), 600, 60.3,
                                              achse=(0, 1, 0))
    return f


def wie_prisma(punkte, dicke):
    """Dreieck o. ä. (x, z) quer durch die Oberseite (y von 0 bis dicke)."""
    from test_rohr_aufgeschnitten import prisma
    return prisma(punkte, "xz", 0, dicke)


ENDEN = {"E01": ("Gehrung", "Gehrung"), "E03": ("Gehrung", "Gehrung"),
         "E05": ("Schrägschnitt zweiachsig", "Schrägschnitt zweiachsig"), "E19": (None, "Schrägschnitt zweiachsig"),
         "E34": (None, "Gehrung"), "E31": (None, "Rohranschluss"), "E32": (None, "Rohranschluss"),
         "E33": (None, "Rohranschluss"), "E35": (None, "Rohranschluss"), "E36": ("Rohranschluss", "Rohranschluss")}
GEKRUEMMT = ("E09", "E10", "E23", "E24", "E25", "E31", "E32", "E33", "E34", "E35", "E36", "R10")   # Sattel, Bögen


SONDER = {"K1": "Sonderkontur", "K2": "Sonderkontur", "K3": "Sonderkontur", "K6e": "Sonderkontur"}
ECKRADIUS = {"K6a": (50, 30, 3), "K6b": (20, 50, 5), "K6c": (40, 20, 2), "K6d": (50, 30, 3)}   # b längs, h, r


def editor_pruefen(ms, d3, nur=None):
    """Übernehmen (mit/ohne 3D), Editor öffnen, Linien gegen die STEP; Ergebnis {Name: Konturen des Editors}."""
    from PySide6.QtWidgets import QApplication
    from rohrlaser.schneidweg_dialog import SchneidwegDialog
    app = QApplication.instance() or QApplication([])  # noqa: F841
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        auswahl = [m for n, m in ms.items() if nur is None or n.startswith(nur)]
        erg = step.uebernehmen(auswahl, [], k, db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True, d3=d3)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        kopf = dict(maschine="T11", stange=6000)
        out, fehler = {}, 0
        for p in erg["positionen"]:
            name = p["artikel"]
            assert p.get("_step_abweichung") is not None and p["_step_abweichung"] <= step_gegenprobe.GRENZE, \
                (name, p.get("_step_abweichung"))
            d = SchneidwegDialog(None, p, k.profile[p["profil_id"]], kopf, k, db.tabellen(), db)
            e = d.eingaben()
            n = wie.netz_wie_konstruiert(d)
            sn = ansicht3d.entpacken(ms[name]["_netz"])
            # Konturen liegen im Modell um rohr3d.ABSTAND über der Wand, Enden auf der Kante: getrennt messen
            weit = -1.0
            for arten, ab in ((("K",), rohr3d.ABSTAND), (("EA", "EB"), 0.0)):
                mod = [z for a in arten for z in n["l"].get(a, [])]
                st = [z for a in arten for z in sn["l"].get(a, [])]
                if mod or st:
                    assert mod and st, (name, arten, len(mod), len(st))
                    weit = max(weit, max(wie._abstand(mod, st), wie._abstand(st, mod)) - ab)
            if weit > (TOL_ENDE if name.startswith(GEKRUEMMT) else TOL):
                fehler += 1
                print(f"FEHLER {name}{' (3D)' if d3 else ''}: im Editor {weit:.3f} mm neben der STEP")
            else:
                print(f"OK     {name}{' (3D)' if d3 else ''}: {weit:+.3f} mm")
            out[name] = (e["konturen"], d)
            soll = ENDEN.get(name.split("_")[0])
            if soll:
                ist = (e["a"].get("form"), e["b"].get("form"))
                assert all(s_ is None or s_ == i_ for s_, i_ in zip(soll, ist)), (name, ist)
        return out, fehler


def k4_u_stammdaten(tmp):
    """Scharfkantiges U 80x40x5 mit/ohne Ausklinkung am Flanschende: ohne U in den Stammdaten Kantteil (beide),
    mit U in den Stammdaten U-Profil (beide)."""
    u = et.profil([(0, 0), (80, 0), (80, 40), (75, 40), (75, 5), (5, 5), (5, 40), (0, 40)], 500)
    f = {"U_ohne": u, "U_Ausklinkung": et.cut(u, box(-1, 10, -1, 10, 40, 41))}
    for n, s in f.items():
        et.schreibe(s, n, tmp)
    step_messen.main(["--ausgabe", str(tmp / "u.csv"), "--netze", str(tmp)] + [str(tmp / (n + ".step")) for n in f])
    for mit_u, soll in ((False, "Blech gekantet"), (True, "U-Profil")):
        ms = step.lade_netze(step.lies_messwerte(tmp / "u.csv"), tmp)
        prof = {"U80": dict(form="U-Profil", a=80.0, b=40.0, wand=5.0)} if mit_u else {}
        step.offene_rohre_vorbelegen(ms, prof, None)
        step.kantteile_vorbelegen(ms, prof)
        ist = {Path(m["datei"]).stem: m["profilform"] for m in ms}
        assert set(ist.values()) == {soll}, (mit_u, ist)
    print("OK     K4 scharfkantiges U mit Ausklinkung: U aus den Stammdaten bleibt U-Profil, sonst Kantteil")


def k5_offen(tmp):
    """Gegenprobe für offene Profile: L mit Walzradius, Langloch und Gehrung – kein Hinweis; Kontur 2 mm verschoben
    – Hinweis."""
    l_ = et.profil([(0, 0), (50, 0), (50, 5), (5, 5), (5, 50), (0, 50)], 400, {(5, 5): 5})
    l_ = et.cut(et.gehrung(l_, 400, 30), langloch((25, 10, 150), (0, -1, 0), 40, 10, (0, 0, 1)))
    et.schreibe(l_, "L_offen", tmp)
    step_messen.main(["--ausgabe", str(tmp / "l.csv"), "--netze", str(tmp), str(tmp / "L_offen.step")])
    m = step.lade_netze(step.lies_messwerte(tmp / "l.csv"), tmp)[0]
    assert m["profilform"] == "L-Profil", m["profilform"]
    with tempfile.TemporaryDirectory() as t2:
        db = Datenbank(Path(t2) / "rohrlaser.db")
        k = db.kontext()
        erg = step.uebernehmen([m], [], k, db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        p = erg["positionen"][0]
        assert p.get("_step_abweichung") is not None and p["_step_abweichung"] <= step_gegenprobe.GRENZE, \
            p.get("_step_abweichung")
        tech = json.loads(p["technik"])
        tech["konturen"][0]["x"] = float(tech["konturen"][0].get("x") or 0) + 2
        ab = step_gegenprobe.abweichung(m, k.profile[p["profil_id"]], tech, p["laenge"])
        h = step_gegenprobe.hinweis(*ab)
        assert h and h.startswith("Editor weicht bis "), (ab, h)
    print(f"OK     K5 Gegenprobe offenes Profil: {p['_step_abweichung']} mm, verschoben: {h[:30]}…")


def grundform():
    """step._grundform_abweichung: echtes Langloch/Rechteck ~0, Langloch gegen Rechteck deutlich."""
    r, h = 5.0, 10.0
    ll = [(h + r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in range(-90, 91, 5)] + \
         [(-h + r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in range(90, 271, 5)]
    assert step._grundform_abweichung(ll, "Langloch", 30, 10, True) < 0.02
    assert step._grundform_abweichung(ll, "Rechteckausschnitt", 30, 10, True) > 1.0
    re_ = [(-15, -5), (15, -5), (15, 5), (-15, 5)]
    assert step._grundform_abweichung(re_, "Rechteckausschnitt", 30, 10, True) < 1e-6
    assert step._grundform_abweichung([(y, x) for x, y in re_], "Rechteckausschnitt", 30, 10, False) < 1e-6
    rr = [(7 + 3 * math.cos(math.radians(a)), 2 + 3 * math.sin(math.radians(a))) for a in range(0, 91, 5)]
    rr += [(-x, y) for x, y in reversed(rr)]
    rr += [(-x, -y) for x, y in rr]                 # Rechteck 20 × 10 mit R3
    assert step._grundform_abweichung(rr, "Rechteckausschnitt", 20, 10, True) > 0.5
    assert step._grundform_abweichung(rr, "Rechteckausschnitt", 20, 10, True, r=3) < 0.02
    assert abs(step._eckradius(dict(laenge=20, breite=10, schnittlaenge=60 - (8 - 2 * math.pi) * 3)) - 3) < 1e-9
    assert step._eckradius(dict(laenge=20, breite=10, schnittlaenge=60)) == 0
    assert abs(step._bohrung_ellipse(12, 30) - 6 * (1 / math.cos(math.radians(30)) - 1)) < 1e-9
    print("OK     Grundform-Vergleich Langloch/Rechteck/Ellipse")


def main():
    grundform()
    fehler = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        f = teile()
        for n, s in f.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp)] + [str(tmp / (n + ".step")) for n in f])
        ms = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)}
        assert len(ms) == len(f), sorted(set(f) - set(ms))
        # Messung: außermittige Bohrung im Rundrohr ist kein Fließloch
        for n in ("K2_RR_Bohrung_aussermittig", "K2_RR_Bohrung_aussermittig_durch"):
            arten = [x["art"] for x in json.loads(ms[n]["konturen_liste"])]
            assert "Fließloch" not in arten and "Bohrung" in arten, (n, arten)
        out, fe = editor_pruefen(ms, False)
        fehler += fe
        assert set(out) == set(f), sorted(set(f) - set(out))
        for name, (konturen, _) in out.items():
            soll = SONDER.get(name.split("_")[0])
            if soll:
                assert [z.get("art") for z in konturen] == [soll] * len(konturen), (name, konturen)
            soll = ECKRADIUS.get(name.split("_")[0])
            if soll:
                assert len(konturen) == 1 and konturen[0].get("art") == "Rechteck", (name, konturen)
                ist = tuple(float(konturen[0].get(x) or 0) for x in ("b", "h", "r"))
                assert all(abs(i_ - s_) < 0.15 for i_, s_ in zip(ist, soll)), (name, ist)
        k3 = out["K3_RE_Schraegbohrung_30"][0][0]
        assert (k3.get("text") or "").startswith("schräge Bohrung Ø12 (30°)"), k3
        assert abs(float(k3["laenge"]) - 40.67) < 0.1, k3
        # mit 3D-Schnitt: geneigte Bohrung, im Rundrohr mit dem gemessenen Umriss (gilt nur mit gleichen Maßen)
        out3, fe = editor_pruefen(ms, True, nur=("K2", "K3"))
        fehler += fe
        for name, (konturen, d) in out3.items():
            assert all(z.get("art") == "Bohrung" and z.get("d3") for z in konturen), (name, konturen)
            if name.startswith("K2_RR_Bohrung_aussermittig") and not name.endswith("durch"):
                assert konturen[0].get("umriss"), (name, konturen[0])
                d.tabelle.item(0, 2).setText("20")          # Ø geändert: Grundform statt Umriss
                assert not d.eingaben()["konturen"][0].get("umriss"), d.eingaben()["konturen"][0]
        k4_u_stammdaten(tmp)
        k5_offen(tmp)
    print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
    return fehler


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
