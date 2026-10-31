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
    return f


SONDER = {"K1": "Sonderkontur", "K2": "Sonderkontur", "K3": "Sonderkontur"}


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
            mod = [z for a in ("K", "EA", "EB") for z in n["l"].get(a, [])]
            st = [z for a in ("K", "EA", "EB") for z in sn["l"].get(a, [])]
            weit = max(wie._abstand(mod, st), wie._abstand(st, mod)) - rohr3d.ABSTAND
            if weit > TOL:
                fehler += 1
                print(f"FEHLER {name}{' (3D)' if d3 else ''}: im Editor {weit:.3f} mm neben der STEP")
            else:
                print(f"OK     {name}{' (3D)' if d3 else ''}: {weit:+.3f} mm")
            out[name] = (e["konturen"], d)
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
