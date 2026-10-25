"""Offene Rohre im STEP schließen (Patrick 25.10.2026, Freigabe „Alle a“): Kunden zeichnen Quadrat-/Rechteckrohre als
gekantetes Blech mit einer offenen Seite. Die Messung ergänzt die fehlende Wand (Spalte/JSON „geschlossen“), das
Programm nimmt das Rohr, wenn es in den Stammdaten steht (1 a), im Prüfdialog umschaltbar, im 3D die Wand rot.

Testteile (RE 60x40x2, 300 mm, unten Biegeradien) werden hier erzeugt:
- U offen, C mit Längsschlitz (Lippen), U mit einer Lasche (sonst Kantteil), U mit Bohrungen
- Enden folgen den Nachbarwänden (2 a): Gehrung nur über einen Teil der Breite, schräg quer und längs zur offenen
  Seite; Vergleich mit dem geschlossen konstruierten Rohr (Volumen des Unterschieds 0, Schnittlängen gleich)
- nicht geschlossen: Rohr mit Fenster nur über einen Teil der Länge (3 a), L-Profil (zwei offene Seiten)

Aufruf: python tests/test_offenes_rohr.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402
from erzeuge_testteile import bohrung_quer, cut, gehrung, kastenrohr, profil, schraeg_ende, schreibe  # noqa: E402
import step_geometrie as g  # noqa: E402
import step_messen  # noqa: E402
import step_offenes_rohr  # noqa: E402
from rohrlaser import step  # noqa: E402
from rohrlaser.ansicht3d import entpacken  # noqa: E402

tmp = Path(tempfile.mkdtemp())
L = 300
U = [(-30, -20), (30, -20), (30, 20), (28, 20), (28, -18), (-28, -18), (-28, 20), (-30, 20)]
R_U = {(-30, -20): 4, (30, -20): 4, (28, -18): 2, (-28, -18): 2}


def box(x0, y0, z0, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), dx, dy, dz).Shape()


u = profil(U, L, R_U)
rohr = kastenrohr(60, 40, 2, L, 4)
spalt = cut(rohr, box(-1, 17, -1, 2, 5, L + 2))           # 2 mm Spalt oben mittig
TEILE = {
    "A_spalt_2": spalt,
    "B_spalt_15": cut(rohr, box(7, 17, -1, 1.5, 5, L + 2)),
    "C_spalt_seite": cut(rohr, box(27, -1, -1, 4, 2, L + 2)),
    "D_spalt_bohrungen": bohrung_quer(bohrung_quer(spalt, 10, 100, (1, 0, 0)), 8, 200, (0, 1, 0)),
    "F_spalt_gehrung": gehrung(spalt, L, 45),
    "I_spalt_schraeg_x": schraeg_ende(spalt, L, 30, 0),
    "J_spalt_schraeg_y": schraeg_ende(spalt, L, 0, 30),
    "G_Rohr_fenster": cut(rohr, box(-25, 15, 50, 50, 10, 100)),
    "H_L_profil": profil([(0, 0), (50, 0), (50, 3), (3, 3), (3, 40), (0, 40)], L),
    "K_U_offen": u,
    "M_C_schlitz_20": cut(rohr, box(-10, 17, -1, 20, 5, L + 2)),
    "N_spalt_25": cut(rohr, box(-1.25, 17, -1, 2.5, 5, L + 2)),
    "O_eine_lasche": profil([(-30, -20), (30, -20), (30, 20), (10, 20), (10, 18), (28, 18), (28, -18), (-28, -18),
                             (-28, 20), (-30, 20)], L,
                            {(-30, -20): 4, (30, -20): 4, (30, 20): 4, (28, -18): 2, (-28, -18): 2, (28, 18): 2}),
}
REF = {"F_spalt_gehrung": gehrung(rohr, L, 45), "I_spalt_schraeg_x": schraeg_ende(rohr, L, 30, 0),
       "J_spalt_schraeg_y": schraeg_ende(rohr, L, 0, 30), "A_spalt_2": rohr}
for name, s in TEILE.items():
    schreibe(s, name, tmp)
for name, s in REF.items():
    schreibe(s, "REF_" + name, tmp)

fehler = 0


def fall(text, fn):
    global fehler
    try:
        fn()
        print(f"OK     {text}")
    except AssertionError as e:
        fehler += 1
        print(f"FEHLER {text}: {e}")


def teil(name):
    return g.analysiere_datei(str(tmp / f"{name}.step"), netz=True)[0]


ERG = {name: teil(name) for name in TEILE}


def erkennung():
    for name, vorher, luecke in (("A_spalt_2", "C-Profil", 2.0), ("B_spalt_15", "C-Profil", 1.5),
                                 ("C_spalt_seite", "C-Profil", 2.0), ("D_spalt_bohrungen", "C-Profil", 2.0)):
        t = ERG[name]
        z = t.geschlossen
        assert t.profilform == vorher and z is not None, (name, t.profilform, z)
        assert z.profilform == "Rechteckrohr" and abs(z.abm_a - 60) < 0.01 and abs(z.abm_b - 40) < 0.01, name
        assert abs(z.wandstaerke - 2) < 0.01 and abs(z.laenge - 300) < 0.01 and z.pruefstatus == "prüfen", name
        assert z.offene_seite["vorher"] == vorher and abs(z.offene_seite["breite"] - luecke) < 0.01, \
            (name, z.offene_seite)
        assert z.sicherheit["offene_seite"] == "ergänzt" and any(step_offenes_rohr.HINWEIS in h for h in z.hinweise)
        assert "EO" in t.netz["t"] and len(t.netz["t"]["EO"]) >= 6, (name, list(t.netz["t"]))
    b = ERG["D_spalt_bohrungen"].geschlossen.bohrungen
    assert b == {10.0: 2, 8.0: 1}, b
    # Schnittlänge Ende = Umfang des Rohrs: wie das geschlossene Rohr
    ref = g.analysiere_datei(str(tmp / "REF_A_spalt_2.step"))[0]
    assert abs(ERG["A_spalt_2"].geschlossen.ende_a - ref.ende_a) < 0.05, (ERG["A_spalt_2"].geschlossen.ende_a, ref.ende_a)


def enden():
    for name in REF:
        z, r = ERG[name].geschlossen, g.analysiere_datei(str(tmp / f"REF_{name}.step"))[0]
        assert z is not None, name
        assert abs(z.laenge - r.laenge) < 0.05 and abs(z.ende_a - r.ende_a) < 0.05 and abs(z.ende_b - r.ende_b) < 0.05, \
            (name, z.laenge, r.laenge, z.ende_a, r.ende_a, z.ende_b, r.ende_b)
        # Geometrie: Körper ∪ ergänzte Wand = geschlossen konstruiertes Rohr
        s = g.datei_lesen(str(tmp / f"{name}.step")).koerper[0][1]
        e = step_offenes_rohr.erkennen(s, 2.0)
        zu = step_offenes_rohr._vereinen(s, step_offenes_rohr.wand(e, 2.0)[0], e["ax3"])
        ref = g.datei_lesen(str(tmp / f"REF_{name}.step")).koerper[0][1]
        for a, b in ((zu, ref), (ref, zu)):
            assert g._volumen(g._boolesch("cut", a, b)) < 0.01, name


def nicht_geschlossen():
    assert ERG["G_Rohr_fenster"].geschlossen is None and ERG["G_Rohr_fenster"].profilform == "Rechteckrohr"
    assert ERG["H_L_profil"].geschlossen is None and ERG["H_L_profil"].profilform == "L-Profil"
    # breiter als 2 mm: gewollt offen (Patrick 25.10.: nur etwa 2 mm schließen, nicht die ganze Seite)
    for name, form in (("K_U_offen", "U-Profil"), ("M_C_schlitz_20", "C-Profil"), ("N_spalt_25", "C-Profil"),
                       ("O_eine_lasche", "Blech gekantet")):
        assert ERG[name].geschlossen is None and ERG[name].profilform == form, (name, ERG[name].profilform)


fall("Messung: Spalt 2 mm / 1,5 mm (oben, seitlich), mit Bohrungen -> RE 60x40x2, Spalt geschlossen", erkennung)
fall("Enden folgen den Nachbarwänden (Gehrung über einen Teil, schräg quer/längs) wie das geschlossene Rohr", enden)
fall("nicht geschlossen: Fenster über einen Teil der Länge, L-Profil, Öffnung breiter als 2 mm", nicht_geschlossen)

# Spalten und JSON
mw = []


def spalten():
    netze = tmp / "netze"
    aus = tmp / "m.txt"
    step_messen.main(["--ausgabe", str(aus), "--netze", str(netze), "--json", str(tmp / "m.json"),
                      str(tmp / "A_spalt_2.step"), str(tmp / "K_U_offen.step"), str(tmp / "H_L_profil.step")])
    mw.extend(step.lade_netze(step.lies_messwerte(aus), netze))
    a, c, h = mw
    assert a["profilform"] == "C-Profil" and step.geschlossen(a)["profil_id_vorschlag"] == "RE 60x40x2"
    assert c["profilform"] == "U-Profil" and not c["geschlossen"] and not h["geschlossen"]
    js = json.loads((tmp / "m.json").read_text(encoding="utf-8"))
    k = js["dateien"][0]["koerper"][0]
    assert js["schema_version"] == "1.19" and k["geschlossen"]["offene_seite"]["seite"] in ("oben", "unten", "links",
                                                                                        "rechts"), k["geschlossen"]
    assert k["offene_seite"] is None and js["dateien"][1]["koerper"][0]["geschlossen"] is None


fall("Spalte „geschlossen“ in den Messwerten, JSON 1.19 mit offene_seite", spalten)

RE = {"RE 60x40x2": dict(form="Rechteckrohr", a=60, b=40, wand=2)}
UP = {"C 60x40x2": dict(form="C-Profil", a=60, b=40, wand=2)}


def vorbelegen():
    a = dict(mw[0])
    assert step.offene_rohre_vorbelegen([a], {}) == 0 and a["profilform"] == "C-Profil"        # Rohr nicht im Stamm
    a = dict(mw[0])
    assert step.offene_rohre_vorbelegen([a], dict(RE, **UP)) == 0 and a["profilform"] == "C-Profil"   # C im Stamm
    a = dict(mw[0])
    assert step.offene_rohre_vorbelegen([a], RE) == 1 and a["profilform"] == "Rechteckrohr" and step.rohr_geschlossen(a)
    assert step.offene_rohre_vorbelegen([a], {}) == 0 and a["profilform"] == "Rechteckrohr"    # nur einmal
    t = entpacken(a["_netz"])["t"]
    assert "EW" in t and "EO" not in t, list(t)
    assert step.art_text(a).endswith("Spalt geschlossen") and \
        step.art_text(step.geschlossen(a), a).endswith("mit Spalt (nicht geschlossen)")
    assert step.rohr_wechseln(a) and a["profilform"] == "C-Profil" and not step.rohr_geschlossen(a)
    assert "EO" in entpacken(a["_netz"])["t"] and step.geschlossen(a)["profilform"] == "Rechteckrohr"
    c = dict(mw[1])                         # U offen (breiter als 2 mm): bleibt U
    assert step.offene_rohre_vorbelegen([c], RE) == 0 and c["profilform"] == "U-Profil"


fall("Programm: Rohr nur aus den Stammdaten (1 a), C-Profil im Stamm bleibt C, U offen bleibt U, Spalt rot/blassrot", vorbelegen)


def dialog():
    from PySide6.QtWidgets import QApplication
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.step_dialog import StepPruefDialog
    QApplication.instance() or QApplication([])
    db = Datenbank(tmp / "rohrlaser.db")
    k = db.kontext()
    k.profile.pop("C 60x40x2", None)
    k.profile.update(RE)
    m = [dict(mw[0])]
    d = StepPruefDialog(None, m, k, "S235-10219", 1)
    assert m[0]["profilform"] == "Rechteckrohr", m[0]["profilform"]
    z = d.zeilen[0]
    cb = d.baum.itemWidget(z.it, d.SP_ART)
    texte = [cb.itemText(n) for n in range(cb.count())]
    assert texte[0].startswith("Rechteckrohr – Spalt geschlossen") and cb.findData("zu") > 0, texte
    assert cb.findData("alt") < 0, texte           # die Kantteil-/Profil-Alternative gehört zum offenen Teil
    d._zeigen(z.it)
    assert "EW" in d.ansicht.ansicht.netz["t"], list(d.ansicht.ansicht.netz["t"])
    d.ansicht.ansicht.grab()
    neu = d.art_gewaehlt(0, "zu")
    assert neu is not None and d.messwerte[0]["profilform"] == "C-Profil"
    d.art_gewaehlt(0, "zu")
    assert d.messwerte[0]["profilform"] == "Rechteckrohr"
    erg = step.uebernehmen(d.messwerte, [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
    p = erg["positionen"][0]
    assert p["profil_id"] == "RE 60x40x2" and abs(p["laenge"] - 300) < 0.01, p


fall("Prüfdialog: Rohr vorbelegt, Art umschaltbar (Spalt offen ↔ geschlossen), 3D rot, Übernahme als RE 60x40x2", dialog)

print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
sys.exit(1 if fehler else 0)
