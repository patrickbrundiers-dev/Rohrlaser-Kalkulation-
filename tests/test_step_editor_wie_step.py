"""STEP-Import in den Rohr-Editor genau wie die STEP (Patrick 27.10.2026: „es fehlen immer Geometrien, Gehrungen und
Schnitte werden falsch dargestellt“; Grundregel: Konturen und Enden zu 100 % wie in der STEP, Lage und Form).

Je Testteil (OpenCascade wie tests/erzeuge_testteile.py) wird gemessen, übernommen, im Rohr-Editor geöffnet und dessen
3D-Modell mit den Linien des STEP-Netzes verglichen (alle Linien von Konturen und Enden zusammen, beide Richtungen).
Vorher lagen Gehrungen mit einer Kontur an der Spitze, Ausklinkungen und Schlitze, die in die Gehrung laufen, im
Editor als gerades Ende (bis 80 mm daneben, Baugruppe RE 140x80 von Patrick); die Kontur fehlte ganz.

E1 komplexes Ende: der gemessene Zug läuft einmal ums Rohr, der Rücksprung zum Anfang ist keine Kante
E2 Schlitz, der in die Gehrung läuft: Sonderkontur „Teil von Ende B“ mit echtem Umriss, zur Gehrung hin offen,
   kein eigener Einstich, Schneidweg gesamt wie gemessen; bleibt beim Speichern und erneuten Öffnen
E3 Schrägschnitt zweiachsig auf Quadratrohr mit Eckradius: Spitze auf der gerundeten Ecke (vorher 1,1 mm daneben)
E4 Gehrungen (beide Achsen, 30°, liegend, im Raum gedreht, Rundrohr), Ausklinkung, Sattel: weiter genau
E5 Skizze: Umriss der Abwicklung ohne die Mündung, Draufsicht mit der Stufe der Ausklinkung an der Kante (±0,1 mm)

Aufruf: python tests/test_step_editor_wie_step.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
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
from rohrlaser import ansicht3d, rechnen, rohr3d, schneidweg as sw, skizze as sk, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 0.06          # mm wie tests/test_step_wie_modell.py
box, dreh = wie.box, wie.dreh


def ok(text):
    print("OK:", text)


def teile():
    f = {}
    re = et.kastenrohr(80, 40, 3, 1000, 6)
    g = et.gehrung(re, 1000, 45)
    f["E1_RE_Ausklinkung_A"] = et.cut(re, box(-20, -30, -1, 40, 20, 26))
    f["E1_RE_Gehrung_Ausklinkung"] = et.cut(g, box(-50, -30, 950, 30, 60, 100))
    f["E2_RE_Gehrung_Schlitz"] = et.cut(g, box(-30, 15, 985, 60, 10, 5.2))
    f["E2_RE_Gehrung_2Schlitze"] = et.cut(et.cut(g, box(-30, 15, 985, 60, 10, 5.2)), box(-30, -25, 975, 60, 10, 4))
    rr = et.rundrohr(48.3, 2.6, 900)
    f["E2_RR_Gehrung_Schlitz"] = et.cut(et.schraeg_ende(rr, 880, 0, 45), box(-30, 10, 860, 60, 20, 6))
    f["E3_QR_zweiachsig"] = et.schraeg_ende(et.kastenrohr(40, 40, 3, 800, 4), 780, 20, 30)
    f["E4_RE_Gehrung_uY"] = g
    f["E4_RE_Gehrung_uX"] = et.schraeg_ende(re, 1000, 45, 0)
    f["E4_RE_Gehrung30_beide"] = et.schraeg_ende(et.schraeg_ende(re, 960, 0, 30), 40, 0, -30, ende_b=False)
    f["E4_RE_Gehrung_liegend"] = dreh(g, 90, (0, 0, 1))
    f["E4_RE_Gehrung_Raum"] = dreh(dreh(g, 33, (1, 1, 0)), 17, (0, 0, 1))
    f["E4_RR_Gehrung"] = et.schraeg_ende(rr, 880, 0, 45)
    f["E4_RR_Sattel"] = et.cut(rr, et.zylinder((-100, 0, 930), (1, 0, 0), 60, 200))
    return f


def e5_skizze(e, profil):
    """Abwicklung ohne Mündung und Stufe der Ausklinkung (Daten der Skizze, ohne Zeichnen)."""
    qs = sk.Querschnitt(dict(profil, r_aussen=e.get("r_step")))
    k = next(k for k in e["konturen"] if k.get("muendung"))
    lb = sk.ende_abwicklung(qs, e["b"])
    teile_ = sk.ohne_muendung(qs, lb, [k["muendung"]])
    assert len(teile_) == 2 and sum(len(t) for t in teile_) <= len(lb), "Mündung nicht offen"
    i = sk.muendung_ende(k, sk.umriss_kontur(k))
    assert i is not None and i < len(sk.umriss_kontur(k)) - 1, "Schließkante über der Mündung gezeichnet"


def e2_umstellen(k, profil):
    """Profil von Hand geändert (kontur_umstellen): die Mündung wandert mit dem Umriss, bleibt an dessen Enden."""
    neu = dict(profil, a=100.0, b=50.0, r_aussen=5.0)
    z, lg = sw.kontur_umstellen(k, neu)
    assert lg and z.get("muendung") and z["muendung"] != k["muendung"], (k["muendung"], z.get("muendung"))
    qs = sk.Querschnitt(neu)
    s_m = sk.s_lage(qs, z)
    um = z["umriss"]
    i = sk.muendung_ende(z, sk.umriss_kontur(z))
    assert i is not None and i < len(sk.umriss_kontur(z)) - 1, "Mündung nach dem Umstellen geschlossen"
    for p in (um[0], um[-1]):                   # Reihenfolge der Mündung: aufsteigend in s
        d = min(abs((s_m + float(p[1]) - s_ + qs.umfang / 2) % qs.umfang - qs.umfang / 2) for s_ in z["muendung"])
        assert d < 0.1, ("Mündung nicht an den Enden des Umrisses", p, z["muendung"], d)


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
        m_ = rechnen.maschine(kopf, k)
        gesehen = set()
        for p in erg["positionen"]:
            name = p["artikel"]
            m = ms[name]
            gesehen.add(name)
            profil = k.profile[p["profil_id"]]
            d = SchneidwegDialog(None, p, profil, kopf, k, db.tabellen(), db)
            e = d.eingaben()
            n = d.ansicht3d.ansicht.netz
            sn = ansicht3d.entpacken(m["_netz"])
            mod = [z for a in ("K", "EA", "EB") for z in n["l"].get(a, [])]
            st = [z for a in ("K", "EA", "EB") for z in sn["l"].get(a, [])]
            # Linien der Konturen liegen ABSTAND über der Wand, die der Enden auf der Kante
            weit = max(wie._abstand(mod, st), wie._abstand(st, mod)) - rohr3d.ABSTAND
            print(f"  {name}: {weit:+.3f} mm")
            if weit > TOL:
                print("   technik", {k_: v for k_, v in sw.lesen(p["technik"])["b"].items() if k_ not in ("flaechen", "umriss")})
                print("   editor ", {k_: v for k_, v in e["b"].items() if k_ not in ("flaechen", "umriss")})
            assert weit <= TOL, f"{name}: im Editor {weit:.3f} mm neben der STEP"
            teil = [z for z in e["konturen"] if z.get("ende_teil")]
            if name.startswith("E2"):
                assert teil and all(z.get("muendung") and z.get("umriss") for z in teil), (name, e["konturen"])
                assert len(teil) == (2 if "2Schlitze" in name else 1), (name, len(teil))
                gesamt = sum(float(z["gemessen"]) for z in teil) + float(e["b"]["gemessen"])
                ende_b = next(x for x in json.loads(m["konturen_liste"]) if x["art"] == "Ende B")
                assert abs(gesamt - float(ende_b["schnittlaenge"])) < 0.05, (gesamt, ende_b["schnittlaenge"])
                r = sw.rechnen(e, profil, rechnen.kontur_regel(m_, rechnen.wand_schneiden(profil)), None, m_)
                sch = [s for s in r["schritte"] if (s.get("eingabe") or {}).get("ende_teil")]
                assert sch and all(s["einstiche"] == 0 for s in sch), "Teil des Endes: kein eigener Einstich"
                d2 = SchneidwegDialog(None, dict(p, technik=sw.speichern(e)), profil, kopf, k, db.tabellen(), db)
                e2 = d2.eingaben()
                assert [z.get("muendung") for z in e2["konturen"] if z.get("ende_teil")] == \
                    [z["muendung"] for z in teil], "Mündung beim erneuten Öffnen verloren"
                d2.deleteLater()
                if name.startswith("E2_RE_Gehrung_Schlitz"):
                    e5_skizze(e, profil)
                    e2_umstellen(teil[0], profil)
            else:
                assert not teil, (name, teil)
            if name == "E1_RE_Ausklinkung_A":
                qs = sk.Querschnitt(dict(profil, r_aussen=e.get("r_step")))
                sil = sk.silhouette(qs, e["a"], e["b"], float(m["laenge"]), "oben")
                stufe = [z[3] for z in sil if 19.9 < abs(z[0]) < 20.1]      # Ausklinkung unten: verdeckt
                assert max(stufe) > 24.99 and min(stufe) < 0.01, "Draufsicht: Stufe der Ausklinkung nicht an der Kante"
            d.deleteLater()
        assert gesehen == set(f), sorted(set(f) - gesehen)
        ok("E1-E4 Rohr-Editor: Gehrungen, Ausklinkungen und Schlitze in der Gehrung genau wie in der STEP")
        ok("E2 Schlitz in der Gehrung: Teil von Ende B, offen, Schneidweg wie gemessen, kein eigener Einstich")
        ok("E5 Skizze: Mündung offen, Stufe der Ausklinkung an der Kante")
    print("Alles in Ordnung")


if __name__ == "__main__":
    main()
