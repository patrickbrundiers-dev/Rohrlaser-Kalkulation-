"""STEP-Import mit größeren Gravuren (Patrick 29.10.2026: „wenn größere Gravuren auf dem Teil sind, dauert es sehr
lange und er erkennt falsch“), nachgebaut mit OpenCascade:

G1 Schrift als eigene dünne Körper (0,1 mm auf der Rohrwand, je Zeichen ein Körper): früher je Zeichen ein Blech
   mit Flachstahl-Zweitmessung (Hunderte Querschnitte, 24 Zeichen über 4 Minuten), als Anbauteil nur mit dem
   Außenumriss (Innenkontur von „O“ fehlte). Jetzt Gravur des Rohrs: gleiche Zeilen, Länge und Lage wie dieselbe
   Schrift eingeprägt, die Zeichen werden keine Teile und keine Anbauteile, keine Profilmessung je Zeichen.
G2 Schrift als lose Flächen auf der Rohrwand: früher „Flächenmodell offen“ ohne Gravur, jetzt wie G1.
G3 Rundrohr: flache Schriftkörper auf dem Mantel ebenso.
G4 Querschnitte bei vielen Flächen (eingeprägte Schrift): nur die Flächen auf der Höhe des Schnitts, Ergebnis gleich
   wie der Schnitt durch den ganzen Körper.
G5 Editor: Gravurzeilen liegen genau auf den Gravurlinien der STEP; Übernehmen ergibt nur das Rohr.

Zeichen ohne Schriftart (läuft überall gleich): Ring „O“ (außen + innen), Balken „I“, Winkel „L“.
Aufruf: python tests/test_step_gravur.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.TopAbs import TopAbs_FACE  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_geometrie as g  # noqa: E402
import step_gravurkoerper  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, rohr3d, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py


def ok(text):
    print("OK:", text)


def zeichen(y0, z, dicke, rund=None):
    """Drei Zeichen „O“, „I“, „L“ (je 8 hoch) ab z, Unterseite in der Ebene y = y0, Normale +Y, dicke nach +Y (bei
    Vertiefungen dicke < 0: von y0 nach innen). Ergebnis: Liste der Körper."""
    y, h = (y0, dicke) if dicke > 0 else (y0 + dicke, -dicke + 2)
    o = et.cut(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, y, z + 4), gp_Dir(0, 1, 0)), 4, h).Shape(),
               BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, y - 1, z + 4), gp_Dir(0, 1, 0)), 2.5, h + 2).Shape())
    i = BRepPrimAPI_MakeBox(gp_Pnt(-4, y, z + 11), 8, h, 1.5).Shape()
    lw = BRepAlgoAPI_Fuse(BRepPrimAPI_MakeBox(gp_Pnt(-4, y, z + 16), 8, h, 1.5).Shape(),
                          BRepPrimAPI_MakeBox(gp_Pnt(-4, y, z + 16), 1.5, h, 6).Shape()).Shape()
    return [o, i, lw]


def flaechen(koerper, y0):
    """Unterseiten der Körper (Flächen in der Ebene y = y0) als lose Flächen."""
    out = []
    for k in koerper:
        for f in g._liste(k, TopAbs_FACE):
            pts = g._flaechen_punkte(f)
            if all(abs(p.Y() - y0) < 1e-6 for p in pts):
                out.append(f)
    return out


def teile():
    f = {}
    qr = et.kastenrohr(40, 40, 3, 300, 6)
    s = qr
    for z in (20, 60, 100, 140):                     # vier Gruppen „OIL“ in der Wand +Y, 0,3 tief eingeprägt
        for k in zeichen(20, z, -0.3):
            s = et.cut(s, k)
    f["G0_QR_eingepraegt"] = s
    koerper = [k for z in (20, 60, 100, 140) for k in zeichen(20, z, 0.1)]
    f["G1_QR_Schriftkoerper"] = et.baugruppe(qr, *koerper)
    f["G2_QR_Schriftflaechen"] = et.baugruppe(qr, *flaechen(koerper, 20))
    rr = et.rundrohr(60.3, 3, 300)
    f["G3_RR_Schriftkoerper"] = et.baugruppe(rr, *[k for z in (40, 120) for k in zeichen(30.15, z, 0.1)])
    return f


def zeilen(m):
    import json
    return [d for d in json.loads(m["konturen_liste"]) if d["art"] == "Gravur"]


def g4_schnitt():
    """Schnitt mit Flächenauswahl = Schnitt durch alles (Fläche und Konturen), Probe an vielen Höhen."""
    s = et.kastenrohr(40, 40, 3, 300, 6)
    for z in range(10, 280, 24):
        for k in zeichen(20, z - 2, -0.3):
            s = et.cut(s, k)
    n = len(g._liste(s, TopAbs_FACE))
    assert n >= g.SCHNITT_FILTER_AB, n
    alt = g.SCHNITT_FILTER_AB
    for z in (5.37, 12.0, 14.0, 63.21, 150.0, 151.5, 299.0):
        mit = g._schnitt(s, z)
        g.SCHNITT_FILTER_AB = 10 ** 9
        try:
            ohne = g._schnitt(s, z)
        finally:
            g.SCHNITT_FILTER_AB = alt
        assert len(mit) == len(ohne), (z, len(mit), len(ohne))
        for a, b in zip(mit, ohne):
            assert abs(a[0] - b[0]) < 1e-6 and abs(a[2] - b[2]) < 1e-6 and abs(a[3] - b[3]) < 1e-6, (z, a[0], b[0])
    ok(f"G4 Querschnitt mit Flächenauswahl ({n} Flächen) gleich wie durch den ganzen Körper")


def main():
    g4_schnitt()
    zaehler = {"n": 0}
    profil_messen = g._profil_messen

    def gezaehlt(*a, **k):
        zaehler["n"] += 1
        return profil_messen(*a, **k)
    g._profil_messen = gezaehlt
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        f = teile()
        for n, s in f.items():
            et.schreibe(s, n, tmp)
        # einzeln je Datei messen (ohne Zeitlimit im selben Prozess, damit die Profilmessungen gezählt werden)
        ms, profilmessungen = {}, {}
        for n in f:
            zaehler["n"] = 0
            step_messen.main(["--ausgabe", str(tmp / f"{n}.csv"), "--netze", str(tmp), "--flachstahl-bis", "0",
                              "--prozesse", "1", str(tmp / (n + ".step"))])
            profilmessungen[n] = zaehler["n"]
            ms[n] = step.lade_netze(step.lies_messwerte(tmp / f"{n}.csv"), tmp)
        g._profil_messen = profil_messen

        ref = ms["G0_QR_eingepraegt"][0]
        soll = zeilen(ref)
        assert len(soll) == 4 * 4, len(soll)       # je Gruppe: O außen, O innen, I, L
        for n in ("G1_QR_Schriftkoerper", "G2_QR_Schriftflaechen"):
            rohr, *rest = ms[n]
            assert rohr["profilform"] == "Quadratrohr", rohr["profilform"]
            assert all(r["profilform"] == step_gravurkoerper.GRAVURKOERPER for r in rest), \
                [r["profilform"] for r in rest]
            assert not rohr.get("anbauteile"), "Schrift ist kein Anbauteil"
            ist = zeilen(rohr)
            assert len(ist) == len(soll), (n, len(ist), len(soll))
            assert abs(step._z(rohr, "gravur") - step._z(ref, "gravur")) < 0.05, (rohr["gravur"], ref["gravur"])
            assert int(rohr["gravur_konturen"]) == int(ref["gravur_konturen"])
            assert abs(step._z(rohr, "schneidweg") - step._z(ref, "schneidweg")) < 0.01, "Gravur nie im Schneidweg"
            for a, b in zip(sorted(ist, key=lambda d: (d["z"], d["schnittlaenge"])),
                            sorted(soll, key=lambda d: (d["z"], d["schnittlaenge"]))):
                assert abs(a["z"] - b["z"]) < 0.05 and abs(a["u"] - b["u"]) < 0.05, (n, a, b)
                assert abs(a["schnittlaenge"] - b["schnittlaenge"]) < 0.05 and a.get("umriss"), (n, a, b)
            assert rohr["pruefstatus"] == "plausibel", rohr["hinweise"]
        assert profilmessungen["G1_QR_Schriftkoerper"] <= 2, profilmessungen   # nur das Rohr, nicht je Zeichen
        ok("G1/G2 Schrift als Körper bzw. Flächen = Gravur des Rohrs wie eingeprägt (Lage, Länge, Konturen), "
           f"Profilmessungen {profilmessungen['G1_QR_Schriftkoerper']} statt je Zeichen")

        rohr, *rest = ms["G3_RR_Schriftkoerper"]
        assert rohr["profilform"] == "Rundrohr" and len(zeilen(rohr)) == 8, (rohr["profilform"], len(zeilen(rohr)))
        assert all(r["profilform"] == step_gravurkoerper.GRAVURKOERPER for r in rest)
        je_gruppe = math.pi * 8 + math.pi * 5 + 2 * (8 + 1.5) + 2 * (8 + 6)     # O außen + innen, I, L
        assert abs(step._z(rohr, "gravur") - 2 * je_gruppe) < 0.1, (rohr["gravur"], 2 * je_gruppe)
        ok("G3 Rundrohr: flache Schriftkörper auf dem Mantel sind Gravur")

        from PySide6.QtWidgets import QApplication
        from rohrlaser.schneidweg_dialog import SchneidwegDialog
        app = QApplication.instance() or QApplication([])  # noqa: F841
        db = Datenbank(tmp / "rohrlaser.db")
        for n in ("G1_QR_Schriftkoerper", "G3_RR_Schriftkoerper"):
            k = db.kontext()
            erg = step.uebernehmen(ms[n], [], k, db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True)
            assert len(erg["positionen"]) == 1, [p["artikel"] for p in erg["positionen"]]
            db.profile_anlegen(erg["profile"])
            k = db.kontext()
            p = erg["positionen"][0]
            d = SchneidwegDialog(None, p, k.profile[p["profil_id"]], dict(maschine="T11", stange=6000), k,
                                 db.tabellen(), db)
            e = d.eingaben()
            assert sum(1 for z in e["konturen"] if z.get("art") == "Gravur") == len(zeilen(ms[n][0])), n
            mod = d.ansicht3d.ansicht.netz["l"].get("G", [])
            st = ansicht3d.entpacken(ms[n][0]["_netz"])["l"].get("G", [])
            assert mod and st, n
            weit = max(wie._abstand(mod, st), wie._abstand(st, mod)) - rohr3d.ABSTAND
            assert weit <= TOL, f"{n}: Gravur im Editor {weit:.3f} mm neben der STEP"
            d.deleteLater()
        ok("G5 Übernehmen: nur das Rohr; Editor: Gravurzeilen genau auf der STEP")
    print("Alles in Ordnung")


if __name__ == "__main__":
    main()
