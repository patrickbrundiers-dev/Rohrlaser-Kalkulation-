"""Gehrung: Umstellen von 3D auf 2D im Editor (Patrick 28.10.2026, Bilder 2D- vs. 3D-Schnitt).

„Bei den Gehrungen, wenn man auf 2D umstellt, passt das immer noch nicht“: 3D = Schnittfläche eben durch die Wand
(Konstruktion), 2D = Strahl senkrecht zur Oberfläche, die Innenkante ist maßhaltig und die lange Seite wird um
Δl = Wand · tan(Winkel) kürzer; die kurze Seite bleibt.
U1 Häkchen „3D-Schnittbearbeitung“ am Bauteil aus, „Gehrung in 3D“ am Ende noch an: vorher blieben 3D-Ansicht,
   Skizze/Zeichnung und STEP-Export eben (3D). Jetzt überall 2D, gleich wie ohne Haken am Ende; Schnittlänge gleich.
   Rechteck-, Quadrat-, Rundrohr, ein und beide Enden, 30°/45°, über Höhe/Breite, zweiachsig.
U2 Offene Profile und Flachstahl in 2D: der Schenkel, der zur langen Seite zeigt und quer zur Kippachse dick ist,
   wird um Dicke · tan(Winkel) kürzer; Schenkel, deren Dicke längs der Kippachse liegt, bleiben (L, U, C, T, I, Flach).
U3 Editor (SchneidwegDialog): Bauteil-Häkchen aus -> Eingaben ohne „3D“ am Ende, 3D-Ansicht kürzer; eine in 3D
   übernommene ebene STEP-Gehrung wird beim Umstellen auf 2D ebenfalls kürzer. Entscheidung Patrick (Variante a):
   eine ebene STEP-Gehrung ohne 3D eingelesen ist wie gefertigt kürzer; nur eine schon 2D geschnittene STEP-Gehrung
   (Schwenk 0) bleibt wie die STEP.

Aufruf: python tests/test_gehrung_2d_umstellen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import rohr3d, schneidweg as sw, skizze as sk  # noqa: E402
from rohrlaser.schneidweg_dialog import ohne_3d  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, tol=1e-3):
    return abs(a - b) <= tol


def z_bereich(e, prof, L):
    n = rohr3d.netz(e, prof, L)
    z = [n["p"][i + 2] for i in range(0, len(n["p"]), 3)]
    return min(z), max(z)


def u1_umstellen():
    profile = [(dict(form="Rechteckrohr", a=80, b=40, wand=3), 3), (dict(form="Quadratrohr", a=40, wand=3), 3),
               (dict(form="Rundrohr", a=48.3, wand=2.6), 2.6)]
    enden = [dict(winkel=45, achse="über Höhe"), dict(winkel=30, achse="über Breite"),
             dict(winkel=20, achse=sw.ACHSE_ZWEI, winkel_h=15, winkel_b=10)]
    L = 600
    n = 0
    for prof, t in profile:
        for ende in enden:
            if prof["form"] == "Rundrohr" and ende["achse"] == sw.ACHSE_ZWEI:
                continue
            ende = dict(ende)
            if ende["achse"] == sw.ACHSE_ZWEI:
                ende["winkel"] = round(sw.gesamtwinkel(ende["winkel_h"], ende["winkel_b"]), 2)
            for beide in (False, True):
                def eing(global_3d, ende_3d):
                    x = dict(ende, d3=True) if ende_3d else dict(ende)
                    return dict(d3=global_3d, a=dict(x) if beide else {}, b=dict(x), konturen=[])
                drei = eing(True, True)
                um = eing(False, True)          # Bauteil auf 2D umgestellt, Haken am Ende steht noch
                zwei = eing(False, False)
                z3, z_um, z2 = (z_bereich(e, prof, L) for e in (drei, um, zwei))
                dl = t * math.tan(math.radians(ende["winkel"]))
                # zweiachsig liegt die Spitze am Eckradius (Normale schräg zur Richtung): Δl dort nur ungefähr
                tol = 0.05 if ende["achse"] == sw.ACHSE_ZWEI else 1e-3
                assert nah(z_um[0], z2[0], 1e-6) and nah(z_um[1], z2[1], 1e-6), (prof["form"], ende, z_um, z2)
                assert nah(z3[1], L, 0.01) and nah(z2[1], L - dl, tol), (prof["form"], ende, z3, z2, dl)
                if beide:
                    assert nah(z3[0], 0, 0.01) and nah(z2[0], dl, tol), (prof["form"], ende, z3, z2)
                # Skizze/Zeichnung (ohne_3d) und gespeicherte Eingaben (sw.lesen) wie 2D
                qs = sk.Querschnitt(sw.mit_radius(prof, um))
                for e_ in (ohne_3d(um), sw.lesen(json.dumps(um))):
                    assert "d3" not in e_["b"], e_["b"]
                    s_ = [qs.umfang * i / 200 for i in range(200)]
                    x_ = [sk.schnitt_x(qs, e_["b"], *qs.s_zu_uv(s)[0]) for s in s_]
                    assert nah(min(x_), dl), (prof["form"], min(x_), dl)
                # Schnittlänge (Schneidweg) 2D wie 3D: Außenkante wie bisher
                r3, r2 = (sw.rechnen(e, prof, (10, 50))["schneidweg"] for e in (drei, um))
                assert nah(r3, r2, 0.01), (prof["form"], ende, r3, r2)
                n += 1
    ok(f"U1 Umstellen auf 2D: 3D-Ansicht, Skizze, gespeicherte Eingaben kürzer um Wand · tan(Winkel), Schnittlänge "
       f"gleich ({n} Fälle: Rechteck-, Quadrat-, Rundrohr, ein/beide Enden, Höhe/Breite/zweiachsig)")


def u2_offene_profile():
    L = 500
    soll = [  # (Profil, Achse, Kürzung in 2D)
        (dict(form="L-Profil", a=50, b=50, wand=5), "über Höhe", 0.0),         # oben: Stirn des senkrechten Schenkels
        (dict(form="L-Profil", a=50, b=50, wand=5), "über Breite", 5.0),       # vorne: senkrechter Schenkel
        (dict(form="U-Profil", a=80, b=40, wand=6), "über Höhe", 6.0),
        (dict(form="U-Profil", a=80, b=40, wand=6), "über Breite", 6.0),
        (dict(form="C-Profil", a=80, b=40, wand=3), "über Höhe", 3.0),
        (dict(form="T-Profil", a=50, b=50, wand=6), "über Höhe", 6.0),
        (dict(form="T-Profil", a=50, b=50, wand=6), "über Breite", 0.0),
        (dict(form="I-/H-Träger", a=100, b=50, wand=5), "über Höhe", 5.0),
        (dict(form="I-/H-Träger", a=100, b=50, wand=5), "über Breite", 0.0),
        (dict(form="Flachstahl", a=60, wand=8), "über Höhe", 0.0),           # über die Breite des Flachs
        (dict(form="Flachstahl", a=60, wand=8), "über Breite", 8.0),         # über die Dicke
    ]
    for prof, achse, kurz in soll:
        for w in (45, 30):
            e3 = dict(d3=True, a={}, b=dict(winkel=w, achse=achse, d3=True), konturen=[])
            e2 = dict(d3=False, a={}, b=dict(winkel=w, achse=achse), konturen=[])
            dl = kurz * math.tan(math.radians(w))
            assert nah(z_bereich(e3, prof, L)[1], L), (prof["form"], achse)
            assert nah(z_bereich(e2, prof, L)[1], L - dl), (prof["form"], achse, w, z_bereich(e2, prof, L), dl)
    ok("U2 offene Profile und Flachstahl in 2D: Schenkel quer zur Kippachse um Dicke · tan(Winkel) kürzer, "
       "Schenkel längs der Kippachse unverändert, 3D wie gezeichnet")


def u3_editor():
    from PySide6.QtWidgets import QApplication
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.schneidweg_dialog import SchneidwegDialog
    app = QApplication.instance() or QApplication([])
    db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
    k = db.kontext()
    kopf = dict(maschine="T11", stange=6000)
    pid, L, t = "RE 60x40x3", 800, 3.0
    faelle = [
        ("von Hand", dict(winkel=45, achse="über Höhe", d3=True)),
        ("STEP eben in 3D", dict(winkel=45, achse="über Höhe", richtung=0.0, d3=True, aussen_mass=True,
                                 schwenk=45.0, gemessen=170.0, form="Gehrung")),
    ]
    for name, b in faelle:
        eing = dict(d3=True, a={}, b=b, konturen=[], quelle=sw.QUELLE)
        p = dict(profil_id=pid, werkstoff_id="S235-10219", laenge=L, stueck=1, technik=json.dumps(eing))
        d = SchneidwegDialog(None, p, k.profile[pid], kopf, k, db.tabellen(), db)
        e = d.eingaben()
        assert e["b"].get("d3") is True and not e["b"].get("aussen_mass"), (name, e["b"])
        zmax = max(d.ansicht3d.ansicht.netz["p"][i + 2] for i in range(0, len(d.ansicht3d.ansicht.netz["p"]), 3))
        assert nah(zmax, L), (name, zmax)
        d.d3.setChecked(False)          # auf 2D umstellen
        app.processEvents()
        e = d.eingaben()
        assert "d3" not in e["b"] and not e["b"].get("aussen_mass"), (name, e["b"])
        n = rohr3d.netz(e, k.profile[pid], L)
        zmax = max(n["p"][i + 2] for i in range(0, len(n["p"]), 3))
        assert nah(zmax, L - t), (name, zmax)
        d.deleteLater()
    # Patrick 28.10.2026 Variante a: ebene STEP-Gehrung ohne 3D eingelesen (auch ältere Importe mit 'aussen_mass')
    # wird wie gefertigt kürzer; schon in der STEP 2D geschnitten (schwenk 0) bleibt wie die STEP
    prof = k.profile[pid]
    for schwenk, soll in ((45.0, L - t), (0.0, L), (None, L)):     # ohne Schwenk (alte Messung): wie STEP
        b = dict(winkel=45, achse="über Höhe", richtung=0.0, aussen_mass=True, form="Gehrung")
        if schwenk is not None:
            b["schwenk"] = schwenk
        zmax = z_bereich(dict(a={}, b=b, konturen=[]), prof, L)[1]
        assert nah(zmax, soll), (schwenk, zmax, soll)
    ok("U3 Editor: Bauteil auf 2D umgestellt -> Ende ohne 3D, lange Seite um Wand · tan(Winkel) kürzer, auch bei "
       "einer in 3D übernommenen ebenen STEP-Gehrung")


def main():
    u1_umstellen()
    u2_offene_profile()
    u3_editor()
    print("Alle Tests Gehrung 2D umstellen bestanden.")


if __name__ == "__main__":
    main()
