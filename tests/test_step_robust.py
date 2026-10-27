"""STEP-Import und Übernahme in den Editor robuster (Patrick 27.10.2026: „step import und der anschließende import in
den Editor noch robuster, dass wirklich alles erkannt wird“; Grundregel: Konturen und Enden zu 100 % wie die STEP).

Aus der Testreihe über alle Testteile und Patricks Dateien (Editor-3D gegen die Linien des STEP-Netzes):
R1 Flowdrill (Fließloch) fehlte im Editor ganz (Schnittlänge 0 → Zeile übersprungen): jetzt Zeile Flowdrill mit
   Kernloch Ø an der gemessenen Stelle; Senkung zeigt den Senkrand Ø D auf der Außenwand wie die STEP
R2 Gehrung an offenen Profilen (U, L, Flach): die Richtung der Messung gilt im Querschnitt der Skizze (gedreht wie
   die Lage der Konturen), vorher lag die lange Seite bis 50 mm daneben
R3 Rechteck-Ausschnitte und Langlöcher in offenen Profilen (nur Hüllmaße gemessen) wurden als Kreis mit dem Hüllmaß
   gezeichnet: jetzt Rechteck bzw. Langloch, wenn die Schnittlänge genau passt, längs bzw. quer wie gemessen
R4 C-Profil: Abkantung (Lippe) wie gemessen in Skizze und 3D (vorher wie ein U-Profil, 17 mm daneben)

Offene Profile liegen im Editor anders im Raum als in der STEP (Querschnitt der Skizze): das Editor-Modell wird an
Ende A ausgerichtet (Drehung um die Achse 0/90/180/270°, gespiegelt, verschoben), dann werden Ende B und Konturen
verglichen. Die STEP hat bei offenen Profilen die Konturkanten auf beiden Seiten der Wand, das Modell nur außen:
STEP → Modell darf darum um die Wandstärke weiter weg liegen.

Aufruf: python tests/test_step_robust.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, rohr3d, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py (geschlossene Rohre, gleiche Lage im Raum)
TOL_AUS = 0.25      # mm offene Profile nach dem Ausrichten (Ausgleich über die Linien von Ende A)
box = wie.box


def ok(text):
    print("OK:", text)


def teile():
    f = {}
    u = et.profil([(-30, 0), (30, 0), (30, 30), (26, 30), (26, 4), (-26, 4), (-26, 30), (-30, 30)], 800)  # U60x30x4
    f["O1_U_Gehrung_xp"] = et.schraeg_ende(u, 760, 45, 0)
    f["O1_U_Gehrung_xm"] = et.schraeg_ende(u, 760, -45, 0)
    f["O1_U_Gehrung_yp"] = et.schraeg_ende(u, 760, 0, 45)
    f["O1_U_Gehrung_ym"] = et.schraeg_ende(u, 760, 0, -45)
    f["O2_U_Rechtecke"] = et.cut(et.cut(u, box(-15, -1, 200, 8, 10, 30)), box(25, 10, 500, 10, 8, 20))
    ll = et.cut(et.cut(u, et.zylinder((0, -1, 300), (0, 1, 0), 10, 10)), box(-5, -1, 300, 10, 10, 30))
    f["O2_U_Langloch"] = et.cut(ll, et.zylinder((0, -1, 330), (0, 1, 0), 10, 10))
    f["O3_U_Raum"] = et.drehe_beliebig(et.cut(et.schraeg_ende(u, 760, 0, 45), box(-15, -1, 200, 8, 10, 30)))
    w = et.profil([(0, 0), (50, 0), (50, 5), (5, 5), (5, 50), (0, 50)], 700)                         # L50x50x5
    f["O4_L_Gehrung_x"] = et.schraeg_ende(et.cut(w, et.zylinder((30, -1, 200), (0, 1, 0), 8, 10)), 620, 40, 0)
    f["O4_L_Gehrung_y"] = et.schraeg_ende(et.cut(w, et.zylinder((-1, 30, 300), (1, 0, 0), 8, 10)), 620, 0, -40)
    c = et.profil([(0, 0), (100, 0), (100, 50), (80, 50), (80, 47), (97, 47), (97, 3), (3, 3), (3, 47), (20, 47),
                   (20, 50), (0, 50)], 600)                                                             # C100x50x20x3
    f["O5_C_Lippe"] = et.cut(c, et.zylinder((50, -1, 300), (0, 1, 0), 10, 10))
    fl = et.profil([(-20, 0), (20, 0), (20, 5), (-20, 5)], 600)
    f["O6_FL_Gehrung_Langloch"] = et.schraeg_ende(et.cut(fl, box(-4, -1, 200, 8, 10, 40)), 560, 0, 30)
    k = et.kastenrohr(80, 40, 3, 900, 6)
    k = et.cut(et.cut(k, box(-10, 15, 150, 20, 10, 8)), box(30, -5, 300, 20, 10, 40))
    k = et.fliessloch(k, (0, -20, 450), (0, 1, 0), 7.3, 11, 3, 3)
    f["Z1_RE_Flowdrill"] = k
    f["Z1_RE_Flowdrill_Raum"] = et.drehe_beliebig(k)
    f["Z2_RE_Senkung"] = et.senkung(et.kastenrohr(80, 40, 3, 900, 6), (-40, 0, 600), (1, 0, 0), 6.6, 12.4, 3)
    rr = et.cut(et.rundrohr(60.3, 3, 800), box(-6, 20, 200, 12, 20, 40))
    f["Z3_RR_Rechteck_Flowdrill"] = et.fliessloch(rr, (0, -30.15, 400), (0, 1, 0), 7.3, 11, 3, 3)
    return f


def _punkte(linien):
    return [z[i:i + 3] for z in linien for i in range(0, len(z), 3)]


def _bewegen(linien, c, s, sp, sh):
    return [[v for i in range(0, len(z), 3) for v in (c * z[i] * sp - s * z[i + 1] + sh[0],
                                                       s * z[i] * sp + c * z[i + 1] + sh[1], z[i + 2] + sh[2])]
            for z in linien]


def ausrichten(mod_a, st_a):
    """Lage des Editor-Modells (Linien von Ende A) auf die STEP: Drehung um die Achse, Spiegelung, Verschiebung
    (Schwerpunkt, dann nächste Punkte ausgleichen). Ergebnis (c, s, sp, sh) mit dem kleinsten Abstand."""
    sp_ = _punkte(st_a)
    cs = [sum(q[i] for q in sp_) / len(sp_) for i in range(3)]
    beste = None
    for sp in (1, -1):
        for w in range(0, 360, 90):
            c, s = round(math.cos(math.radians(w))), round(math.sin(math.radians(w)))
            tp = _punkte(_bewegen(mod_a, c, s, sp, (0, 0, 0)))
            sh = [cs[i] - sum(q[i] for q in tp) / len(tp) for i in range(3)]
            for _ in range(4):          # nächste Punkte: Verschiebung nachziehen
                mp = _punkte(_bewegen(mod_a, c, s, sp, sh))
                d = [min(sp_, key=lambda q: math.dist(p, q)) for p in mp]
                sh = [sh[i] + sum(d[j][i] - mp[j][i] for j in range(len(mp))) / len(mp) for i in range(3)]
            t = _bewegen(mod_a, c, s, sp, sh)
            dd = max(wie._abstand(t, st_a), wie._abstand(st_a, t))
            if beste is None or dd < beste[0]:
                beste = (dd, c, s, sp, sh)
    return beste


def main():
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
        erg = step.uebernehmen(list(ms.values()), [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               neue_profile=True)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        kopf = dict(maschine="T11", stange=6000)
        gesehen = set()
        for p in erg["positionen"]:
            name = p["artikel"]
            m = ms[name]
            gesehen.add(name)
            profil = k.profile[p["profil_id"]]
            d = SchneidwegDialog(None, p, profil, kopf, k, db.tabellen(), db)
            e = d.eingaben()
            arten = [z.get("art") for z in e["konturen"]]
            n = d.ansicht3d.ansicht.netz
            sn = ansicht3d.entpacken(m["_netz"])

            def linien(netz, *a):
                return [z for a_ in a for z in netz["l"].get(a_, [])]
            if name.startswith("Z"):        # geschlossene Rohre: gleiche Lage wie die STEP
                mod, st = linien(n, "K", "EA", "EB"), linien(sn, "K", "EA", "EB")
                hin = wie._abstand(mod, st) - rohr3d.ABSTAND
                zurueck = wie._abstand(st, mod) - rohr3d.ABSTAND
                print(f"  {name}: Modell→STEP {hin:+.3f}, STEP→Modell {zurueck:+.3f} mm")
                assert zurueck <= TOL, f"{name}: STEP-Linie fehlt im Editor ({zurueck:.2f} mm)"
                if "Senkung" not in arten:  # Senkung: die Bohrung Ø d liegt in der STEP unter dem Kegel
                    assert hin <= TOL, f"{name}: Editor {hin:.2f} mm neben der STEP"
            else:                           # offene Profile: an Ende A ausrichten
                dd, c, s, sp, sh = ausrichten(linien(n, "EA"), linien(sn, "EA"))
                wand = float(profil.get("wand") or 0)
                werte = {}
                for art in ("EB", "K"):
                    mod, st = _bewegen(linien(n, art), c, s, sp, sh), linien(sn, art)
                    if not st:
                        assert not mod, (name, art)
                        continue
                    werte[art] = (wie._abstand(mod, st) - rohr3d.ABSTAND, wie._abstand(st, mod) - rohr3d.ABSTAND)
                print(f"  {name}: Ende A {dd - rohr3d.ABSTAND:+.3f}, "
                      + ", ".join(f"{a} {h:+.2f}/{z:+.2f}" for a, (h, z) in werte.items()) + " mm")
                assert dd - rohr3d.ABSTAND <= TOL_AUS, f"{name}: Querschnitt passt nicht ({dd:.2f} mm)"
                h, z = werte["EB"]
                assert max(h, z) <= TOL_AUS, f"{name}: Ende B {max(h, z):.2f} mm neben der STEP"
                if "K" in werte:
                    h, z = werte["K"]
                    assert h <= TOL_AUS and z <= wand + TOL_AUS, f"{name}: Konturen {h:.2f}/{z:.2f} mm daneben"
            if name.startswith(("Z1", "Z3")):
                fd = [z for z in e["konturen"] if z.get("art") == "Flowdrill"]
                assert len(fd) == 1 and abs(float(fd[0]["d"]) - 7.3) < 0.05, (name, e["konturen"])
                assert abs(float(fd[0]["x"]) - (450 if name.startswith("Z1") else 400)) < 0.2, fd
            if name == "Z2_RE_Senkung":
                sk_ = [z for z in e["konturen"] if z.get("art") == "Senkung"]
                assert sk_ and abs(float(sk_[0]["D"]) - 12.4) < 0.2, e["konturen"]
            if name.startswith("O2") or name.startswith("O6") or name == "O3_U_Raum":
                soll = {"O2_U_Rechtecke": ["Rechteck", "Rechteck"], "O2_U_Langloch": ["Langloch"],
                        "O6_FL_Gehrung_Langloch": ["Rechteck"], "O3_U_Raum": ["Rechteck"]}[name]
                assert sorted(arten) == soll, (name, arten)
            if name == "O5_C_Lippe":
                assert abs(float(e.get("c_lippe") or 0) - 20) < 0.1, e.get("c_lippe")
            d.deleteLater()
        assert gesehen == set(f), sorted(set(f) - gesehen)
        ok("R1 Flowdrill im Editor an der gemessenen Stelle, Senkung mit Senkrand wie die STEP")
        ok("R2 Gehrungen an U-, L- und Flachprofilen in allen Richtungen wie die STEP (auch im Raum gedreht)")
        ok("R3 Rechteck-Ausschnitte und Langlöcher in offenen Profilen als Rechteck bzw. Langloch")
        ok("R4 C-Profil mit der gemessenen Abkantung")
    print("Alles in Ordnung")


if __name__ == "__main__":
    main()
