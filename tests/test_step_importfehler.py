"""Fehler beim STEP-Import (Patrick 26.10.2026), nachgebaut mit OpenCascade:

F1 Geschlossenes Quadratrohr 40x40x2 mit vielen Langlöchern wurde Kantteil: bei 7 Probeschnitten trafen fast alle
   ein Langloch, die Achse galt nur als „wahrscheinlich“ und das Teil fiel auf „Blech gekantet“. Regel: ein
   geschlossenes Rohr ist immer ein Rohr, alle Schnitte werden übernommen (keine Ausnahme).
F2 Konturen im Editor neben der STEP: der Eckradius der STEP-Datei (r_step) ging beim Öffnen des Editors verloren.
F3 Rohr mit Ausklinkung im Editor gerade: Umriss des komplexen Endes ging beim Öffnen verloren.
F4 77 Positionen, Übernehmen übernahm nur eine: gleicher Bauteilname bei verschiedenen Teilen = gleiche
   Artikelnummer, jedes weitere Teil galt als „steht schon im Angebot“.

Aufruf: python tests/test_step_importfehler.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, importprofil, rohr3d, schneidweg as sw, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py


def ok(text):
    print("OK:", text)


def langloch(x0, achse_x, z, lg, b, quer=0.0):
    """Langloch lg × b längs zur Rohrachse durch die Wand bei x0 (achse_x: Wand ±X, sonst ±Y)."""
    r = b / 2
    teile = []
    for zz in (z - (lg / 2 - r), z + (lg / 2 - r)):
        p, d = ((x0, quer, zz), (1, 0, 0)) if achse_x else ((quer, x0, zz), (0, 1, 0))
        teile.append(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p), gp_Dir(*d)), r, 10).Shape())
    k = BRepPrimAPI_MakeBox(gp_Pnt(x0, quer - r, z - (lg / 2 - r)), 10, b, lg - b).Shape() if achse_x else \
        BRepPrimAPI_MakeBox(gp_Pnt(quer - r, x0, z - (lg / 2 - r)), b, 10, lg - b).Shape()
    return BRepAlgoAPI_Fuse(BRepAlgoAPI_Fuse(teile[0], teile[1]).Shape(), k).Shape()


def teile():
    f = {}
    s = et.kastenrohr(40, 40, 2, 1200, 4)          # F1: QR 40x40x2, 36 Langlöcher in drei Wänden
    for i in range(12):
        z = 60 + i * 90
        s = et.cut(s, langloch(15, True, z, 30, 8))
        s = et.cut(s, langloch(15, False, z + 45, 20, 6))
        s = et.cut(s, langloch(-25, True, z + 20, 40, 10))
    f["F1_QR40x2_Langloecher"] = s
    s = et.kastenrohr(40, 40, 2, 600, 7)            # F2: Eckradius 7 (Norm wäre 4), Konturen nah an den Ecken
    for i in range(5):
        s = et.cut(s, langloch(15, True, 80 + i * 100, 30, 8, quer=8))
        s = et.cut(s, BRepPrimAPI_MakeBox(gp_Pnt(10, 10, 120 + i * 100), 20, 20, 20).Shape())
    f["F2_QR40x2_r7"] = s
    s = et.kastenrohr(40, 40, 2, 800, 4)            # F3: Ausklinkungen an beiden Enden
    s = et.cut(s, BRepPrimAPI_MakeBox(gp_Pnt(-30, 5, 780), 60, 30, 30).Shape())
    s = et.cut(s, BRepPrimAPI_MakeBox(gp_Pnt(15, -8, -5), 10, 16, 20).Shape())
    f["F3_QR40x2_Ausklinkung"] = s
    return f


def koerper(nr, laenge, name="Rohr"):
    return dict(datei="Gestell.step", artikel=f"Gestell-K{nr}", koerper=str(nr), bauteil=name,
                profilform="Quadratrohr", abm_a="40", abm_b="0", wandstaerke="3", flaeche="430", laenge=str(laenge),
                schneidweg="300", konturen="2", ende_a="150", ende_a_gerade="1", ende_b="150", ende_b_gerade="1",
                innen="0", innen_konturen="0", gravur="0", gravur_konturen="0", bohrungen="", innen_liste="",
                profil_id_vorschlag="QR 40x40x3", hinweise="", fehler="")


def f4_gleicher_name(db):
    k, gew = db.kontext(), db.zeilen("gewinde")
    # 77 verschiedene Teile, alle mit Bauteilname „Rohr“, dazu dreimal dasselbe Teil „Strebe“
    mw = [koerper(i + 1, 300 + 10 * i) for i in range(77)] + [koerper(78 + i, 500, "Strebe") for i in range(3)]
    importprofil.anwenden(mw, None, {"step_benennung": "Bauteilname"})
    namen = [m["artikel"] for m in mw]
    assert namen[:3] == ["Rohr", "Rohr-2", "Rohr-3"] and namen[76] == "Rohr-77", namen[:3]
    assert namen[77:] == ["Strebe"] * 3, namen[77:]          # gleiches Teil, gleicher Name: bleibt eine Nummer
    erg = step.uebernehmen(mw, [], k, gew, None, "S235-10219", 2)
    pos = erg["positionen"]
    assert len(pos) == 78, len(pos)
    assert len({p["artikel"] for p in pos}) == 78
    strebe = next(p for p in pos if p["artikel"] == "Strebe")
    assert strebe["stueck"] == 6, strebe["stueck"]             # 3 Körper × 2 Stück
    # zweiter Import derselben Datei: dieselben Nummern, alles „steht schon im Angebot“
    mw2 = [koerper(i + 1, 300 + 10 * i) for i in range(77)]
    importprofil.anwenden(mw2, None, {"step_benennung": "Bauteilname"})
    assert step.uebernehmen(mw2, pos, k, gew, None)["positionen"] == []
    ok("F4 77 Teile mit gleichem Bauteilnamen: 77 Positionen (Rohr, Rohr-2 …), gleiche Teile zusammengezählt")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = Datenbank(tmp / "rohrlaser.db")
        f4_gleicher_name(db)
        f = teile()
        for n, s in f.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp), "--flachstahl-bis", "0"]
                         + [str(tmp / (n + ".step")) for n in f])
        ms = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)}

        m = ms["F1_QR40x2_Langloecher"]
        assert m["profilform"] == "Quadratrohr" and m["bauteiltyp"] == "Profil", (m["profilform"], m["bauteiltyp"])
        assert int(m["innen_konturen"]) == 36 and "achse=sicher" in m["sicherheit"], m["sicherheit"]
        assert not m.get("alternative"), "geschlossenes Rohr: keine Wahl Kantteil"
        assert all(step._z(ms[n], "kammern") >= 1 and ms[n]["bauteiltyp"] == "Profil" for n in ms)
        ok("F1 QR 40x40x2 mit 36 Langlöchern bleibt Rohr, alle Konturen gemessen")

        from PySide6.QtWidgets import QApplication
        from rohrlaser.schneidweg_dialog import SchneidwegDialog
        app = QApplication.instance() or QApplication([])  # noqa: F841
        k = db.kontext()
        erg = step.uebernehmen(list(ms.values()), [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               neue_profile=True)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        kopf = dict(maschine="T11", stange=6000)
        for p in erg["positionen"]:
            name = p["artikel"]
            m = ms[name]
            d = SchneidwegDialog(None, p, k.profile[p["profil_id"]], kopf, k, db.tabellen(), db)
            e = d.eingaben()
            assert len(e["konturen"]) == len(sw.lesen(p["technik"])["konturen"]), name
            n = d.ansicht3d.ansicht.netz
            sn = ansicht3d.entpacken(m["_netz"])
            for arten, soll in ((("K",), rohr3d.ABSTAND), (("EA", "EB"), 0.0)):
                mod = [z for a in arten for z in n["l"].get(a, [])]
                st = [z for a in arten for z in sn["l"].get(a, [])]
                if not st:
                    continue
                assert mod, (name, arten)
                weit = max(wie._abstand(mod, st), wie._abstand(st, mod)) - soll
                assert weit <= TOL, f"{name} {'/'.join(arten)}: im Editor {weit:.3f} mm neben der STEP"
            if name.startswith("F3"):
                assert all(e[s_].get("umriss") for s_ in ("a", "b")), "Umriss der Ausklinkung verloren"
            if name.startswith("F2"):
                assert e.get("r_step") == 7.0, e.get("r_step")
            d.deleteLater()
        ok("F2/F3 Editor: Konturen und Ausklinkungen wie in der STEP (Eckradius und Umriss bleiben)")
    print("Alles in Ordnung")


if __name__ == "__main__":
    main()
