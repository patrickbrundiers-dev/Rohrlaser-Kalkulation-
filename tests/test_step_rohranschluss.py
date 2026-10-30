"""Rohranschluss am Rundrohrende (Patrick 30.10.2026: „Rohranschluss von Rundrohrende erkennen und auch die 3D-
Bearbeitung möglich machen“): ein Ende, das mit einem Sattel-/Fischmaulschnitt auf einem runden Gegenrohr sitzt
(rechtwinklig, schräg, mit Versatz, in beliebiger Lage am Umfang), kommt aus der STEP als Gegenrohr in den Rohr-Editor
und ist dort wie jedes Gegenrohr bearbeitbar (Ø, Winkel, Versatz, Drehung). Vorher war es nur ein gemessener Umriss
(„komplex“), nicht änderbar.

Grundregel: das Ende liegt im Editor 100 % wie in der STEP (Lage und Form); trifft das Gegenrohr den gemessenen Umriss
nicht überall auf 0,1 mm, bleibt das Ende komplex wie gemessen.

R1 Messung: Zylinder als Schnittfläche -> "gegenrohr" (Ø, Richtung, Winkel, Versatz) genau wie konstruiert
R2 Rohr-Editor: Gegenrohr mit Ø/Winkel/Versatz/Drehung, 3D-Linien wie das STEP-Netz, Schneidweg wie gemessen
R3 Bearbeiten: Ø/Winkel im Dialog bzw. im Eigenschaftsfeld des 3D-Editors ändern -> neu gerechnet, gespeichert
R4 Gegenbeispiele: Gegenrohr kleiner als das Rohr (Rest eben) bleibt komplex mit Umriss

Aufruf: python tests/test_step_rohranschluss.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
from OCP.gp import gp_Trsf, gp_Vec  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_messen  # noqa: E402
import test_step_wie_modell as wie  # noqa: E402
from rohrlaser import ansicht3d, durchdringung as dd, rechnen, rohr3d, schneidweg as sw, skizze as sk, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py


def ok(text):
    print("OK:", text)


def anschluss(D, winkel=0.0, versatz=0.0, drehung=0.0, z=0.0, ende_a=False):
    """Werkzeug: Gegenrohr Ø D (Achse quer, um winkel geneigt, um versatz verschoben, um drehung um die Rohrachse
    gedreht), Achsen kreuzen bei z; alles jenseits der Gegenrohrachse fällt weg (das Rohr endet am Gegenrohr)."""
    t = BRepAlgoAPI_Fuse(et.zylinder((-400, versatz, 0), (1, 0, 0), D, 800),
                         wie.box(-400, -400, 0, 800, 800, 800)).Shape()
    for achse, w in (((0, 1, 0), -winkel), ((1, 0, 0), 180 if ende_a else 0), ((0, 0, 1), drehung)):
        if w:
            t = wie.dreh(t, w, achse)
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(0, 0, z))
    return BRepBuilderAPI_Transform(t, tr, True).Shape()


# Name: (Teil, Ende B erwartet (Ø, Winkel, Versatz) oder None = bleibt komplex, Ende A erwartet)
def teile():
    rr = et.rundrohr(48.3, 2.6, 1000)
    f = {
        "R_rechtwinklig": (et.cut(rr, anschluss(60.3, z=950)), (60.3, 0, 0), None),
        "R_schraeg30": (et.cut(rr, anschluss(88.9, 30, z=950)), (88.9, 30, 0), None),
        "R_versatz8": (et.cut(rr, anschluss(76.1, 0, 8, z=950)), (76.1, 0, 8), None),
        "R_gedreht30": (et.cut(rr, anschluss(60.3, 0, 0, 30, z=950)), (60.3, 0, 0), None),
        "R_alles": (et.cut(rr, anschluss(88.9, 15, 10, 40, z=950)), (88.9, 15, 10), None),
        "R_beide_Enden": (et.cut(et.cut(rr, anschluss(60.3, 0, 0, 0, z=950)),
                                 anschluss(114.3, 20, 0, 90, z=50, ende_a=True)), (60.3, 0, 0), (114.3, 20, 0)),
        "R_QR40_auf_RR76": (et.cut(et.kastenrohr(40, 40, 3, 1000, 4), anschluss(76.1, 0, 0, 0, z=950)),
                            (76.1, 0, 0), None),
        "R_RE60x40_auf_RR88_senkrecht": (et.cut(et.kastenrohr(60, 40, 3, 1000, 4),
                                                anschluss(88.9, 10, 0, 90, z=950)), (88.9, 10, 0), None),
        # Gegenrohr kleiner als das Rohr: teils Zylinder, teils eben -> bleibt komplex
        "R_zu_klein": (et.cut(rr, anschluss(40, z=950)), None, None),
    }
    return f


def pruefe_gegen(name, g, soll):
    d, w, v = soll
    assert g, f"{name}: kein Gegenrohr erkannt"
    assert abs(g["d"] - d) < 0.01, (name, g)
    assert abs(abs(sw._z(g.get("winkel"))) - w) < 0.05, (name, g)
    assert abs(abs(sw._z(g.get("versatz"))) - v) < 0.05, (name, g)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = Datenbank(tmp / "rohrlaser.db")
        f = teile()
        for n, (s, _, _) in f.items():
            et.schreibe(s, n, tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp)] + [str(tmp / (n + ".step")) for n in f])
        ms = {Path(m["datei"]).stem: m for m in step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)}
        assert len(ms) == len(f), sorted(ms)
        import json
        for n, (_, sb, sa) in f.items():
            kl = {x["art"]: x for x in json.loads(ms[n]["konturen_liste"])}
            for art, soll in (("Ende B", sb), ("Ende A", sa)):
                gm = kl[art].get("gegenrohr")
                if soll:
                    assert gm and abs(gm["d"] - soll[0]) < 0.01 and abs(gm["winkel"] - soll[1]) < 0.05 \
                        and abs(abs(gm["versatz"]) - soll[2]) < 0.05, (n, art, gm)
                elif n == "R_zu_klein":
                    assert not gm, (n, art, gm)
        ok("R1 Messung: Rohranschluss mit Ø, Richtung, Winkel und Versatz wie konstruiert")

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
            _, sb, sa = f[name]
            profil = k.profile[p["profil_id"]]
            d = SchneidwegDialog(None, p, profil, kopf, k, db.tabellen(), db)
            e = d.eingaben()
            for s, soll in (("b", sb), ("a", sa)):
                if soll:
                    pruefe_gegen(name, e[s].get("gegen"), soll)
                    assert e[s].get("form") == step.ROHRANSCHLUSS and not e[s].get("umriss"), (name, e[s])
                    assert "auf Ø" in d.gegen_knopf[s].text(), d.gegen_knopf[s].text()
                    # Schnittlänge des Gegenrohrs = gemessene Länge (auf 0,5 %)
                    qs = sk.Querschnitt(dict(profil, r_aussen=e.get("r_step")))     # Eckradius der STEP
                    lg = dd.ende_gegen(qs, e[s]["gegen"])["laenge"]
                    assert abs(lg - e[s]["gemessen"]) < 0.005 * e[s]["gemessen"], (name, lg, e[s]["gemessen"])
                elif name == "R_zu_klein" and s == "b":
                    assert not e[s].get("gegen") and e[s].get("umriss"), (name, e[s])
            n = wie.netz_wie_konstruiert(d)
            sn = ansicht3d.entpacken(m["_netz"])
            mod = [z for a in ("K", "EA", "EB") for z in n["l"].get(a, [])]
            st = [z for a in ("K", "EA", "EB") for z in sn["l"].get(a, [])]
            weit = max(wie._abstand(mod, st), wie._abstand(st, mod)) - rohr3d.ABSTAND
            print(f"  {name}: {weit:+.3f} mm  {e['b'].get('gegen')}  {e['a'].get('gegen')}")
            assert weit <= TOL, f"{name}: im Editor {weit:.3f} mm neben der STEP"
            r = sw.rechnen(e, profil, rechnen.kontur_regel(m_, rechnen.wand_schneiden(profil)), None, m_)
            assert not r["fehler"], (name, r["fehler"])
            if name == "R_alles":
                r3_bearbeiten(d, p, profil, kopf, k, db, float(m["laenge"]))
            d.deleteLater()
        assert gesehen == set(f), sorted(set(f) - gesehen)
        ok("R2 Rohr-Editor: Gegenrohr wie in der STEP (3D-Linien ±0,06 mm, Schneidweg wie gemessen)")
        ok("R4 zu kleines Gegenrohr bleibt komplex mit Umriss")
    print("Alles in Ordnung")


def r3_bearbeiten(d, p, profil, kopf, k, db, L):
    from rohrlaser.schneidweg_dialog import SchneidwegDialog
    e0 = d.eingaben()
    g = dict(e0["b"]["gegen"], d=114.3)
    d.gegenrohr("b", g)
    e = d.eingaben()
    assert e["b"]["gegen"]["d"] == 114.3 and not e["b"].get("gemessen"), e["b"]
    lg = dd.ende_gegen(d.qs, e["b"]["gegen"])["laenge"]
    assert abs(lg - e0["b"]["gemessen"]) > 1, "neues Gegenrohr nicht neu gerechnet"
    d2 = SchneidwegDialog(None, dict(p, technik=sw.speichern(e)), profil, kopf, k, db.tabellen(), db)
    assert d2.eingaben()["b"]["gegen"] == e["b"]["gegen"], "Gegenrohr beim erneuten Öffnen verloren"
    d2.deleteLater()
    # Eigenschaftsfeld des 3D-Editors: Ende B gewählt, Winkel und Drehung direkt eingeben
    from rohrlaser.editor_eigenschaften import Eigenschaften
    eig = Eigenschaften(d, "rohr")
    eig.zeigen("ende:b")
    for schl in ("gegen_d", "gegen_winkel", "gegen_versatz", "gegen_drehung"):
        assert schl in eig.felder, (schl, sorted(eig.felder))
    for schl, text, soll in (("gegen_winkel", "20", 20.0), ("gegen_drehung", "45", 45.0), ("gegen_versatz", "0", None)):
        eig.zeigen("ende:b")
        f_ = eig.felder[schl]
        f_.setText(text)
        f_.uebernehmen()
        assert d.gegen["b"].get(schl[6:]) == soll, (schl, d.gegen["b"])
    e = d.eingaben()
    assert e["b"]["gegen"] == dict(d=114.3, winkel=20.0, drehung=45.0), e["b"]["gegen"]
    eig.deleteLater()
    ok("R3 Gegenrohr aus der STEP geändert: neu gerechnet, gespeichert, beim Öffnen wieder da, im 3D-Editor änderbar")


def r5_hilfskoerper():
    """Pinker Hilfskörper (Gegenrohr im 3D) und Schnittkante liegen zusammen, auch gedreht und mit Versatz: jeder
    Punkt der Kante hat den Radius des Gegenrohrs zu dessen Achse (Mitte der beiden Ringe)."""
    qs = sk.Querschnitt(dict(form="Rundrohr", a=48.3, wand=2.6))
    L = 1000.0
    for g in (dict(d=88.9, winkel=15, versatz=10, drehung=-40), dict(d=60.3, drehung=90), dict(d=76.1, versatz=-8)):
        for seite in ("a", "b"):
            ringe = dd.gegen_koerper(qs, g, L, seite)[:2]
            c0, c1 = ([sum(p[i] for p in r[:-1]) / (len(r) - 1) for i in range(3)] for r in ringe)
            ax = [c1[i] - c0[i] for i in range(3)]
            lg = math.sqrt(sum(a * a for a in ax))
            ax = [a / lg for a in ax]
            for k in range(72):
                (u, v), _ = qs.s_zu_uv(qs.umfang * k / 72)
                x = dd.schnitt_x(qs, g, u, v)
                p = (x if seite == "a" else L - x, u, v)
                w = [p[i] - c0[i] for i in range(3)]
                t = sum(w[i] * ax[i] for i in range(3))
                r = math.sqrt(max(sum(a * a for a in w) - t * t, 0.0))
                assert abs(r - g["d"] / 2) < 0.05, (g, seite, k, r)
    ok("R5 Hilfskörper Gegenrohr im 3D liegt auf der Schnittkante (auch gedreht, mit Versatz, beide Enden)")


if __name__ == "__main__":
    r5_hilfskoerper()
    main()
