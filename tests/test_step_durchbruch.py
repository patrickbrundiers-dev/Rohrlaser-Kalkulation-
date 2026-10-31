"""Durchbruch für einen Stutzen aus der STEP (Patrick 30./31.10.2026: Loch in der Wand eines Rohrs, durch das ein
abgehendes Rohr gesteckt wird, auch schräg, mit Versatz und in beliebiger Lage am Umfang): kommt als Zeile
„Durchbruch“ (Gegenrohr Ø, Winkel, Versatz, Seite, Lage) in den Rohr-Editor und ist dort wie jeder Durchbruch
bearbeitbar. Vorher war es eine „Bohrung“, die im Editor als flacher Kreis lag – im Rundrohr bis 5 mm neben der STEP.

Grundregel: der Durchbruch liegt im Editor 100 % wie in der STEP (Lage und Form); trifft er den gemessenen Umriss
nicht überall auf 0,1 mm, bleibt das Loch eine Bohrung. Kleine Löcher (unter 15 mm bzw. 30 % des Rohrs) bleiben
Bohrungen (Gewinde, Bohren, Preis je Stück).

D1 Messung: Bohrung trägt "stutzen" (Ø, Richtung, Winkel, Versatz, Lage) wie konstruiert
D2 Rohr-Editor: Durchbruch, 3D-Linien wie das STEP-Netz (±0,06 mm), Schneidweg ohne Fehler
D3 Bearbeiten: Versatz/Ø im Eigenschaftsfeld des 3D-Editors ändern -> neu gerechnet, gespeichert
D4 Gegenbeispiel: kleine Bohrung bleibt Bohrung

Aufruf: python tests/test_step_durchbruch.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
from OCP.gp import gp_Trsf, gp_Vec  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, rechnen, rohr3d, schneidweg as sw, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py


def ok(text):
    print("OK:", text)


def stutzen(d, x, winkel=0.0, versatz=0.0, dreh=0.0):
    """Werkzeug: Stutzen Ø d von der Rohrachse nach oben (+y) durch eine Wand, um winkel zu Ende B geneigt, quer um
    versatz verschoben, um dreh um die Rohrachse gedreht; Achsen kreuzen bei x."""
    s = et.zylinder((versatz, 0, 0), (0, 1, 0), d, 200)
    for achse, w in (((1, 0, 0), -winkel), ((0, 0, 1), dreh)):
        if w:
            s = wie.dreh(s, w, achse)
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(0, 0, x))
    return BRepBuilderAPI_Transform(s, tr, True).Shape()


# Name: (Teil, erwartet (Ø, |Winkel|, |Versatz|) oder None = bleibt Bohrung)
def teile():
    rr = et.rundrohr(88.9, 3, 600)
    q = et.kastenrohr(80, 80, 3, 600, 6)
    re_ = et.kastenrohr(100, 60, 3, 600, 6)
    return {
        "D_rechtwinklig": (et.cut(rr, stutzen(48.3, 300)), (48.3, 0, 0)),
        "D_schraeg30": (et.cut(rr, stutzen(48.3, 300, 30)), (48.3, 30, 0)),
        "D_versatz15": (et.cut(rr, stutzen(42.4, 250, 0, 15)), (42.4, 0, 15)),
        "D_gedreht50": (et.cut(rr, stutzen(48.3, 300, 0, 0, 50)), (48.3, 0, 0)),
        "D_alles": (et.cut(rr, stutzen(42.4, 320, 20, 10, 120)), (42.4, 20, 10)),
        "D_QR80": (et.cut(q, stutzen(48.3, 300)), (48.3, 0, 0)),
        "D_QR80_versatz": (et.cut(q, stutzen(40, 300, 0, 12)), (40, 0, 12)),
        "D_RE100x60_seite_schraeg": (et.cut(re_, stutzen(33.7, 300, 25, 0, 90)), (33.7, 25, 0)),
        "D_klein": (et.cut(rr, stutzen(10, 300)), None),
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = Datenbank(tmp / "rohrlaser.db")
        f = teile()
        for n, (s, _) in f.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp)] + [str(tmp / (n + ".step")) for n in f])
        ms = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)}
        assert len(ms) == len(f), sorted(ms)
        for n, (_, soll) in f.items():
            b = [x for x in json.loads(ms[n]["konturen_liste"]) if x["art"] == "Bohrung"]
            assert len(b) == 1, (n, b)
            st = b[0].get("stutzen")
            d, w, v = soll or (10, 0, 0)
            assert st and abs(st["d"] - d) < 0.01 and abs(abs(st["winkel"]) - w) < 0.05 \
                and abs(abs(st["versatz"]) - v) < 0.05, (n, st)
        ok("D1 Messung: Bohrung mit Stutzen-Achse (Ø, Winkel, Versatz) wie konstruiert")

        from PySide6.QtWidgets import QApplication
        from rohrlaser.schneidweg_dialog import SchneidwegDialog
        app = QApplication.instance() or QApplication([])  # noqa: F841
        k = db.kontext()
        erg = step.uebernehmen(list(ms.values()), [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               neue_profile=True)
        db.profile_anlegen(erg["profile"])
        k = db.kontext()
        kopf = dict(maschine="T11", stange=6000)
        m_ = rechnen.maschine(kopf, k)
        gesehen = set()
        for p in erg["positionen"]:
            name = p["artikel"]
            m = ms[name]
            gesehen.add(name)
            soll = f[name][1]
            profil = k.profile[p["profil_id"]]
            d = SchneidwegDialog(None, p, profil, kopf, k, db.tabellen(), db)
            e = d.eingaben()
            z = e["konturen"][0]
            if soll:
                assert z["art"] == sw.DURCHBRUCH, (name, z)
                assert abs(sw._z(z["d"]) - soll[0]) < 0.01 and abs(abs(sw._z(z.get("winkel"))) - soll[1]) < 0.05, z
                assert abs(abs(sw._z(z.get("versatz") if d.qs.r else z.get("q"))) - soll[2]) < 0.05, (name, z)
            else:
                assert z["art"] == sw.BOHRUNG, (name, z)
            n = wie.netz_wie_konstruiert(d)
            sn = ansicht3d.entpacken(m["_netz"])
            weit = max(wie._abstand(n["l"].get("K", []), sn["l"].get("K", [])),
                       wie._abstand(sn["l"].get("K", []), n["l"].get("K", []))) - rohr3d.ABSTAND
            print(f"  {name}: {weit:+.3f} mm  {({x: v for x, v in z.items() if x not in ('umriss', 'messprofil')})}")
            if soll:
                assert weit <= TOL, f"{name}: im Editor {weit:.3f} mm neben der STEP"
            r = sw.rechnen(e, profil, rechnen.kontur_regel(m_, rechnen.wand_schneiden(profil)), None, m_)
            assert not r["fehler"], (name, r["fehler"])
            if name == "D_alles":
                d3_bearbeiten(d, p, profil, kopf, k, db)
            d.deleteLater()
        assert gesehen == set(f), sorted(set(f) - gesehen)
        ok("D2 Rohr-Editor: Durchbruch wie in der STEP (3D-Linien ±0,06 mm), Schneidweg ohne Fehler")
        ok("D4 kleine Bohrung bleibt Bohrung")
    print("Alles in Ordnung")


def d3_bearbeiten(d, p, profil, kopf, k, db):
    from rohrlaser.editor_eigenschaften import Eigenschaften
    from rohrlaser.schneidweg_dialog import SchneidwegDialog
    e0 = d.eingaben()
    eig = Eigenschaften(d, "rohr")
    eig.zeigen("kontur:0")
    assert "Versatz" in eig.felder, sorted(eig.felder)
    f_ = eig.felder["Versatz"]
    f_.setText("0")
    f_.uebernehmen()
    e = d.eingaben()
    z = e["konturen"][0]
    assert z["art"] == sw.DURCHBRUCH and not sw._z(z.get("versatz")), z
    z0 = sw.durchbruch_ergaenzen(e0["konturen"][0], profil)
    z1 = sw.durchbruch_ergaenzen(z, profil)
    assert abs(z1["laenge_dd"] - z0["laenge_dd"]) > 0.5, "Durchbruch nach Änderung nicht neu gerechnet"
    d2 = SchneidwegDialog(None, dict(p, technik=sw.speichern(e)), profil, kopf, k, db.tabellen(), db)
    z2 = d2.eingaben()["konturen"][0]
    assert z2["art"] == sw.DURCHBRUCH and not sw._z(z2.get("versatz")) and z2["d"] == z["d"], z2
    d2.deleteLater()
    eig.deleteLater()
    ok("D3 Durchbruch aus der STEP im 3D-Editor geändert: neu gerechnet, gespeichert, beim Öffnen wieder da")


if __name__ == "__main__":
    main()
