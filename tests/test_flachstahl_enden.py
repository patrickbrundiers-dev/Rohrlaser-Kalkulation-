"""Flachstahl mit geformten Enden (Patricks echte STEP-Dateien, 05.11.2026: Grill „BIELA SUPERIOR“ 30×5 mit
rundem Ende R15, Traktor „Кузов“ 80×12 mit gerundeten Ecken R10 an beiden Enden).

Vorher: der gemessene Umriss des Endes läuft über die Schmalseite des Flachstahls von s = Umfang nach s = 0 weiter.
Die Abwicklung offener Profile rechnete das als Weg einmal quer über den Umfang zurück – das galt als Schnitt vom Ende
ins Teil hinein und wieder heraus („Ausflug“). Ergebnis: das Ende fehlte im Editor ganz (gerade gezeichnet) und dafür
standen zwei Sonderkonturen „Teil von Ende B“ quer über das Teil, bis 17 mm neben der STEP.
Jetzt: beim Flachstahl ist der Umfang geschlossen, das Ende kommt als komplexes Ende mit Umriss wie in der STEP, ohne
Sonderkonturen; im Editor liegen Enden und Konturen auf den Linien der STEP.

Aufruf: python tests/test_flachstahl_enden.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_robust as rob  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, rohr3d, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.25          # mm wie der Editor-Vergleich offener Profile (Messraster der Enden)
box = wie.box


def fuse(*teile):
    s = teile[0]
    for t in teile[1:]:
        s = BRepAlgoAPI_Fuse(s, t).Shape()
    return s


def teile():
    f = {}
    # 30×5, Länge 310, Ende B rund R15, je eine Bohrung Ø11 bei 15 und 295 (Pleuel „BIELA SUPERIOR“)
    t = fuse(box(-15, -2.5, 0, 30, 5, 295), et.zylinder((0, -2.5, 295), (0, 1, 0), 30, 5))
    for z in (15, 295):
        t = et.cut(t, et.zylinder((0, -10, z), (0, 1, 0), 11, 20))
    f["F1_rund_R15"] = t
    # 80×12, Länge 400, alle vier Ecken R10 gerundet
    teil = [box(-30, -6, 0, 60, 12, 400), box(-40, -6, 10, 80, 12, 380)]
    teil += [et.zylinder((x, -6, z), (0, 1, 0), 20, 12) for x in (-30, 30) for z in (10, 390)]
    f["F2_Ecken_R10"] = fuse(*teil)
    return f


def linien(n, *arten):
    return [z for a in arten for z in (n.get("l") or {}).get(a, [])]


def _huelle(pts):
    return [(min(pts[i::3]) + max(pts[i::3])) / 2 for i in range(2)] + [min(pts[2::3])]


def ausrichten(n, sn):
    """Editor-Modell auf die STEP legen: Drehung um die Achse in 90°-Schritten, gespiegelt oder nicht, Mitte der
    Hülle (quer) und Ende A (längs) aufeinander; die Lage mit dem kleinsten Abstand der Linien."""
    alle_st = linien(sn, "EA", "EB", "K")
    ziel = _huelle(sn["p"])
    beste = None
    for c, s_ in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        for sp in (1, -1):
            hm = _huelle(rob._bewegen([n["p"]], c, s_, sp, (0, 0, 0))[0])
            sh = [ziel[i] - hm[i] for i in range(3)]
            mod = rob._bewegen(linien(n, "EA", "EB", "K"), c, s_, sp, sh)
            dd = max(wie._abstand(mod, alle_st), wie._abstand(alle_st, mod))
            if beste is None or dd < beste[0]:
                beste = (dd, c, s_, sp, sh)
    return beste[1:]


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
        for name, m in ms.items():
            assert m["profilform"] == "Flachstahl", (name, m["profilform"])
            e = step.rechner_eingaben(m, "Flachstahl", float(m["abm_a"]), float(m["abm_b"]))
            enden = ("b",) if name.startswith("F1") else ("a", "b")
            for s in enden:
                assert e[s].get("form") == "komplex" and len(e[s].get("umriss") or ()) > 10, (name, s, e[s])
                tief = max(p[1] for p in e[s]["umriss"])
                soll = 15.0 if name.startswith("F1") else 10.0
                assert abs(tief - soll) < 0.3, (name, s, tief)
            sonder = [k for k in e["konturen"] if k.get("art") == "Sonderkontur"]
            assert not sonder, (name, "Ende als Sonderkontur", [k.get("text") for k in sonder])
            print(f"OK     {name}: Ende(n) {', '.join(enden).upper()} komplex mit Umriss, keine Sonderkontur")

        from PySide6.QtWidgets import QApplication
        from rohrlaser.schneidweg_dialog import SchneidwegDialog
        app = QApplication.instance() or QApplication([])  # noqa: F841
        k = db.kontext()
        for m in ms.values():
            m["_uebernehmen"] = True
        erg = step.uebernehmen(list(ms.values()), [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               neue_profile=True)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        kopf = dict(maschine="T11", stange=6000)
        gesehen = set()
        for p in erg["positionen"]:
            name = p["artikel"]
            gesehen.add(name)
            profil = k.profile[p["profil_id"]]
            d = SchneidwegDialog(None, p, profil, kopf, k, db.tabellen(), db)
            n = wie.netz_wie_konstruiert(d)
            sn = ansicht3d.entpacken(p["_netz"])
            c, s_, sp, sh = ausrichten(n, sn)
            weit = 0.0
            for a in ("EA", "EB", "K"):
                st = linien(sn, a)
                if not st:
                    continue
                mod = rob._bewegen(linien(n, a), c, s_, sp, sh)
                assert mod, (name, a, "fehlt im Editor")
                h = wie._abstand(mod, st) - rohr3d.ABSTAND
                z = wie._abstand(st, mod) - rohr3d.ABSTAND - (float(profil.get("wand") or 0) if a == "K" else 0)
                weit = max(weit, h, z)
                if os.environ.get("DETAIL"):
                    print("  ", name, a, round(h, 2), round(z, 2))
            assert not linien(n, "K") or linien(sn, "K"), (name, "Konturen im Editor, die die STEP nicht hat")
            if weit > TOL:
                fehler += 1
                print(f"FEHLER {name}: im Editor {weit:.2f} mm neben der STEP")
            else:
                print(f"OK     {name}: Editor {weit:+.2f} mm neben der STEP")
            d.deleteLater()
        assert gesehen == set(f), sorted(set(f) - gesehen)
    print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
    return fehler


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
