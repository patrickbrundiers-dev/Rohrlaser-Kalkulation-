"""Erkennung aus dem Supportpaket STEP 553591 (Patrick 17.11.2026, Plan E3/E4):

E3 Flaches Rechteckrohr 40 × 15 × 1,5, L 786, mit einem Schlitz auf einer breiten Seite über fast die ganze Länge,
   je Seite 2 mm Rand (bis in den Eckradius): war „Blech gekantet, Bleche stoßen aneinander“. Die Enden sind in der
   STEP geschlossen, also ist es ein Rohr mit Ausschnitt (Kantteil nur als Auswahl), der Schlitz bleibt Kontur.
   Kürzerer Schlitz: wie bisher Rechteckrohr.
E4 Rundrohr Ø 40 × 2, L 35, in einer Baugruppe mit anliegendem Rohrbund und eingezeichneter Schweißnaht (eigener
   Körper, Kehlnaht als Dreieck um das Rohr): die Naht war ein „offenes Sonderprofil“; jetzt ist sie kein Teil
   (Schweißnaht als Körper), Rohr und Bund bleiben wie gemessen. Ein Blech, das zwei Rohre verbindet, bleibt ein Teil.

Aufruf: python tests/test_erkennung_schlitz_naht.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]

from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402
from test_step_wie_modell import box  # noqa: E402


def ok(text):
    print("OK:", text)


def zyl(r, z0, h):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), r, h).Shape()


def messen(shape, name, tmp):
    et.schreibe(shape, name, tmp)
    return analysiere_datei(tmp / f"{name}.step")


def e3(tmp):
    re = et.kastenrohr(40, 15, 1.5, 786, 2.5)
    for lz, schlitz_lang in ((766, True), (400, False)):
        z0 = (786 - lz) / 2
        (t,) = messen(et.cut(re, box(-18, 4, z0, 36, 5, lz)), f"RE_Schlitz{lz}", tmp)
        assert t.bauteiltyp == "Profil" and t.profilform == "Rechteckrohr", (lz, t.bauteiltyp, t.profilform,
                                                                             t.art_grund)
        assert (t.abm_a, t.abm_b) == (40, 15) and abs(t.wandstaerke - 1.5) < 0.02 and abs(t.laenge - 786) < 0.05, \
            (t.abm_a, t.abm_b, t.wandstaerke, t.laenge)
        innen = [d for d in t.konturen_liste if d.get("art") not in ("Ende A", "Ende B")]
        assert innen, "Schlitz fehlt als Kontur"
        lg = max(d.get("schnittlaenge") or 0 for d in innen)
        assert lg > 2 * lz, (lz, lg)
        if schlitz_lang:
            assert (t.offene_seite or {}).get("ringe_step"), t.offene_seite
            assert t.alternative is not None and t.alternative.bauteiltyp == "Blech gekantet", t.alternative
            assert "Enden in der STEP geschlossen" in t.art_grund, t.art_grund
        ok(f"E3 RE 40×15×1,5 mit Schlitz {lz} mm: Rechteckrohr, Schlitz als Kontur ({lg:.0f} mm)"
           + (", Kantteil nur als Auswahl" if schlitz_lang else ""))


def e4(tmp):
    rr = et.rundrohr(40, 2, 35)
    bund = et.cut(zyl(35, -8, 8), zyl(18, -9, 10))
    naht = et.cut(BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 24, 20, 4).Shape(), zyl(20, -1, 6))
    rohr, bund_t, naht_t = messen(et.baugruppe(rr, bund, naht), "RR_Bund_Naht", tmp)
    assert rohr.profilform == "Rundrohr" and abs(rohr.abm_a - 40) < 0.05 and abs(rohr.laenge - 35) < 0.05, \
        (rohr.profilform, rohr.abm_a, rohr.laenge)
    assert bund_t.bauteiltyp == "Blech", bund_t.bauteiltyp
    assert naht_t.profilform == "Schweißnaht (Körper)" and naht_t.bauteiltyp == "", (naht_t.profilform,
                                                                                     naht_t.bauteiltyp)
    assert any("Schweißnaht als Körper" in h for h in naht_t.hinweise), naht_t.hinweise
    ok("E4 Rundrohr mit Bund und Schweißnaht als Körper: Rohr und Bund gemessen, Naht kein Teil")
    # Gegenprobe: ein Blech zwischen zwei Rohren (Knotenblech) ist größer als eine Naht und bleibt ein Teil
    r1 = et.verschiebe(et.kastenrohr(40, 40, 2, 300, 4), 0, 0, 0)
    r2 = et.verschiebe(et.kastenrohr(40, 40, 2, 300, 4), 100, 0, 0)
    blech = box(20, -3, 50, 60, 6, 120)
    teile = messen(et.baugruppe(r1, r2, blech), "Knotenblech", tmp)
    assert all(t.profilform != "Schweißnaht (Körper)" for t in teile), [t.profilform for t in teile]
    ok("E4 Gegenprobe: Blech zwischen zwei Rohren bleibt ein Teil")


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    e3(tmp)
    e4(tmp)
    print("Alle Tests bestanden.")
