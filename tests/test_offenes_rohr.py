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
import math
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
from erzeuge_testteile import bohrung_quer, cut, gehrung, kastenrohr, profil, rundrohr, schraeg_ende, schreibe  # noqa: E402
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


def zu_rohr():
    """Dasselbe Rohr geschlossen konstruiert (oben scharfkantig wie das U)."""
    aussen = profil([(-30, -20), (30, -20), (30, 20), (-30, 20)], L, {(-30, -20): 4, (30, -20): 4})
    innen = profil([(-28, -18), (28, -18), (28, 18), (-28, 18)], L, {(-28, -18): 2, (28, -18): 2})
    return cut(aussen, innen)


u = profil(U, L, R_U)
rohr = kastenrohr(60, 40, 2, L, 4)
spalt = cut(rohr, box(-1, 17, -1, 2, 5, L + 2))           # 2 mm Spalt oben mittig
TEILE = {
    # Spalt bis 2 mm: ganz geschlossen
    "A_spalt_2": spalt,
    "B_spalt_15": cut(rohr, box(7, 17, -1, 1.5, 5, L + 2)),
    "C_spalt_seite": cut(rohr, box(27, -1, -1, 4, 2, L + 2)),
    "D_spalt_bohrungen": bohrung_quer(bohrung_quer(spalt, 10, 100, (1, 0, 0)), 8, 200, (0, 1, 0)),
    "F_spalt_gehrung": gehrung(spalt, L, 45),
    "I_spalt_schraeg_x": schraeg_ende(spalt, L, 30, 0),
    "J_spalt_schraeg_y": schraeg_ende(spalt, L, 0, 30),
    # breiter: aus dem Rohr, je ein Steg 2 mm an Ende A und B, dazwischen Fenster
    "K_U_offen": u,
    "M_C_schlitz_20": cut(rohr, box(-10, 17, -1, 20, 5, L + 2)),
    "N_spalt_25": cut(rohr, box(-1.25, 17, -1, 2.5, 5, L + 2)),
    "O_eine_lasche": profil([(-30, -20), (30, -20), (30, 20), (10, 20), (10, 18), (28, 18), (28, -18), (-28, -18),
                             (-28, 20), (-30, 20)], L,
                            {(-30, -20): 4, (30, -20): 4, (30, 20): 4, (28, -18): 2, (-28, -18): 2, (28, 18): 2}),
    "P_U_gehrung": gehrung(u, L, 45),
    # wie Patricks Beispiel links: Seitenwände über ein Stück bis zum Boden ausgeschnitten, Bohrungen in den Laschen
    "Q_U_laschen": bohrung_quer(cut(u, box(-31, -15, 180, 62, 40, 60)), 16, 80, (1, 0, 0)),
    # nicht geschlossen
    "G_Rohr_fenster": cut(rohr, box(-25, 15, 50, 50, 10, 100)),
    "H_L_profil": profil([(0, 0), (50, 0), (50, 3), (3, 3), (3, 40), (0, 40)], L),
    # nächstes Normrohr: 59,4 × 39,4 -> RE 60x40; 58 × 38: Sondermaß
    "S_U_59": profil([(-29.7, -19.7), (29.7, -19.7), (29.7, 19.7), (27.7, 19.7), (27.7, -17.7), (-27.7, -17.7),
                      (-27.7, 19.7), (-29.7, 19.7)], L, {(-29.7, -19.7): 4, (29.7, -19.7): 4, (27.7, -17.7): 2,
                                                          (-27.7, -17.7): 2}),
    "T_U_58": profil([(-29, -19), (29, -19), (29, 19), (27, 19), (27, -17), (-27, -17), (-27, 19), (-29, 19)], L,
                     {(-29, -19): 4, (29, -19): 4, (27, -17): 2, (-27, -17): 2}),
    # Rundrohr Ø40 × 2: Halbschale, Drittel offen (Schnitt in einer Ebene), schmaler Schlitz 2 mm, schräges Ende
    "R_halb": cut(rundrohr(40, 2, L), box(-30, 0, -1, 60, 30, L + 2)),
    "R_drittel": cut(rundrohr(40, 2, L), box(-30, 10, -1, 60, 30, L + 2)),
    "R_spalt": cut(rundrohr(40, 2, L), box(-1, 0, -1, 2, 30, L + 2)),
    "R_halb_schraeg": schraeg_ende(cut(rundrohr(40, 2, L), box(-30, 0, -1, 60, 30, L + 2)), L, 30, 0),
    "R_halb_39": cut(rundrohr(39.6, 2, L), box(-30, 0, -1, 60, 30, L + 2)),
    # Schale 162° (mit Bohrung): zwei je Rohrumfang mit 5 mm Luft
    "R_schale_162": bohrung_quer(cut(rundrohr(40, 2, L), box(-30, -3, -1, 60, 33, L + 2)), 8, 200, (0, -1, 0)),
}
REF = {"F_spalt_gehrung": gehrung(rohr, L, 45), "I_spalt_schraeg_x": schraeg_ende(rohr, L, 30, 0),
       "J_spalt_schraeg_y": schraeg_ende(rohr, L, 0, 30), "A_spalt_2": rohr,
       # Stege: das Rohr (R4 wie das C) ohne das Fenster zwischen den Ringen
       "M_C_schlitz_20": cut(rohr, box(-10, 17.5, 2, 20, 3, L - 4))}
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
        assert z.profilform == "Rechteckrohr" and abs(z.abm_a - 60) < 0.01 and abs(z.abm_b - 40) < 0.01, \
            (name, z.abm_a, z.abm_b)
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


def geschlossen_koerper(name):
    """Der Körper, den schliessen misst: Teil ∪ Wand, mit Stegen ohne das Fenster."""
    s = g.datei_lesen(str(tmp / f"{name}.step")).koerper[0][1]
    e = step_offenes_rohr.erkennen(s, 2.0)
    zu = step_offenes_rohr._vereinen(s, step_offenes_rohr.wand(e, 2.0)[0], e["ax3"])
    if ERG[name].geschlossen.offene_seite["steg"]:
        zu = step_offenes_rohr._ausschneiden(zu, step_offenes_rohr.wand(e, 2.0, fenster=2.0)[0], e["ax3"])
    return zu


def enden():
    for name in ("F_spalt_gehrung", "I_spalt_schraeg_x", "J_spalt_schraeg_y"):
        z, r = ERG[name].geschlossen, g.analysiere_datei(str(tmp / f"REF_{name}.step"))[0]
        assert z is not None, name
        assert abs(z.laenge - r.laenge) < 0.05 and abs(z.ende_a - r.ende_a) < 0.05 and abs(z.ende_b - r.ende_b) < 0.05, \
            (name, z.laenge, r.laenge, z.ende_a, r.ende_a, z.ende_b, r.ende_b)
    for name in REF:        # Geometrie: wie das geschlossen konstruierte Rohr (mit Stegen: ohne Fenster)
        zu, ref = geschlossen_koerper(name), g.datei_lesen(str(tmp / f"REF_{name}.step")).koerper[0][1]
        for a, b in ((zu, ref), (ref, zu)):
            assert g._volumen(g._boolesch("cut", a, b)) < 0.01, name


def stege():
    # U mit scharfen Schenkelenden: nichts fällt weg, das Rohr wird quer zur offenen Seite größer (60 × 50, der Radius
    # beginnt erst nach den Schenkelenden); eine Lasche auf der offenen Seite läge dann nicht in der Wand: 60 × 40 mit
    # Überstand (wird Kantteil, siehe vorbelegen)
    for name, vorher, luecke, fenster, b in (("K_U_offen", "U-Profil", 56.0, 745.13, 50),
                                             ("M_C_schlitz_20", "C-Profil", 20.0, 632.0, 40),
                                             ("N_spalt_25", "C-Profil", 2.5, 597.0, 40),
                                             ("O_eine_lasche", "Blech gekantet", 38.0, 668.0, 40)):
        t = ERG[name]
        z = t.geschlossen
        assert t.profilform == vorher and z is not None, (name, t.profilform, z)
        assert z.profilform == "Rechteckrohr" and abs(z.abm_a - 60) < 0.01 and abs(z.abm_b - b) < 0.01, \
            (name, z.abm_a, z.abm_b)
        assert abs(z.wandstaerke - 2) < 0.01 and abs(z.laenge - 300) < 0.01 and z.pruefstatus == "prüfen", name
        assert z.offene_seite["steg"] == 2.0 and abs(z.offene_seite["breite"] - luecke) < 0.01, (name, z.offene_seite)
        assert abs(z.innen - fenster) < 0.05 and z.innen_konturen == 1, (name, z.innen, z.innen_konturen)
        assert any("Ring 2 mm an Ende A und B" in h for h in z.hinweise), z.hinweise
        assert "EO" in t.netz["t"] and len(t.netz["t"]["EO"]) >= 12, (name, list(t.netz["t"]))
    # Enden: Umfang des Rohrs 60 × 50, Radius aus der STEP (R4) an allen Ecken
    umfang = 2 * (60 + 50) - 4 * (2 - math.pi / 2) * 4
    z = ERG["K_U_offen"].geschlossen
    assert abs(z.ende_a - umfang) < 0.05 and abs(z.ende_b - umfang) < 0.05, (z.ende_a, z.ende_b, umfang)
    assert z.offene_seite["vergroessert"] == 10.0 and z.offene_seite["radius"] == 4.0, z.offene_seite
    assert any("damit nichts wegfällt" in h for h in z.hinweise), z.hinweise
    o = ERG["O_eine_lasche"].geschlossen
    assert o.offene_seite["ueberstand"] > 1 and "vergroessert" not in o.offene_seite, o.offene_seite
    p = ERG["P_U_gehrung"].geschlossen
    assert p is not None and p.profilform == "Rechteckrohr" and p.offene_seite["steg"] == 2.0, p
    assert abs(p.ende_b - p.ende_a) > 20 and p.innen_konturen == 1, (p.ende_a, p.ende_b, p.innen_konturen)
    q = ERG["Q_U_laschen"].geschlossen
    assert q is not None and q.profilform == "Rechteckrohr" and q.offene_seite["steg"] == 2.0, q
    assert q.bohrungen.get(16.0) == 2 and q.innen > 704, (q.bohrungen, q.innen)


def ringe():
    # Ring an den Enden: das ganze Rohr (hier wie das C), steg mm breit: dazu kommt nur der Schlitz in den Ringen
    zu = geschlossen_koerper("M_C_schlitz_20")
    s = g.datei_lesen(str(tmp / "M_C_schlitz_20.step")).koerper[0][1]
    dazu = g._volumen(zu) - g._volumen(s)
    assert abs(dazu - 2 * 2 * 20 * 2) < 0.5, dazu
    s59, s58 = ERG["S_U_59"].geschlossen, ERG["T_U_58"].geschlossen
    assert s59 is not None and (s59.abm_a, s59.abm_b) == (60.0, 50.0) and s59.offene_seite["normrohr"], s59
    assert s59.profil_id_vorschlag == "RE 60x50x2", s59.profil_id_vorschlag
    assert s58 is not None and abs(s58.abm_a - 58) < 0.01 and not s58.offene_seite["normrohr"], s58
    assert any("kein Normrohr" in h for h in s58.hinweise), s58.hinweise


def rund():
    for name, fenster, enden in (("R_halb", 592 + 4 * math.pi * 20 / 2, None),
                                 ("R_drittel", None, None), ("R_halb_schraeg", None, True)):
        t = ERG[name]
        z = t.geschlossen
        assert t.profilform == "offenes Sonderprofil" and z is not None, (name, t.profilform)
        assert z.profilform == "Rundrohr" and abs(z.abm_a - 40) < 0.01 and abs(z.wandstaerke - 2) < 0.01, name
        assert z.offene_seite["steg"] == 2.0 and z.innen_konturen == 1, (name, z.offene_seite, z.innen_konturen)
        assert abs(z.ende_a - 40 * math.pi) < 0.1, (name, z.ende_a)
        if fenster:
            assert abs(z.innen - fenster) < 0.5, (name, z.innen, fenster)
        if enden:
            assert z.ende_b > z.ende_a + 5, (name, z.ende_a, z.ende_b)
        assert "EO" in t.netz["t"], (name, list(t.netz["t"]))
    sp = ERG["R_spalt"].geschlossen
    assert sp is not None and sp.offene_seite["steg"] is None and sp.innen == 0, sp
    n = ERG["R_halb_39"].geschlossen
    assert n is not None and n.abm_a == 40.0 and n.profil_id_vorschlag.startswith("RR 40"), \
        (n and n.abm_a, n and n.profil_id_vorschlag)


def nicht_geschlossen():
    assert ERG["G_Rohr_fenster"].geschlossen is None and ERG["G_Rohr_fenster"].profilform == "Rechteckrohr"
    assert ERG["H_L_profil"].geschlossen is None and ERG["H_L_profil"].profilform == "L-Profil"


fall("Messung: Spalt 2 mm / 1,5 mm (oben, seitlich), mit Bohrungen -> RE 60x40x2, Spalt geschlossen", erkennung)
fall("Enden folgen den Nachbarwänden (Gehrung, schräg quer/längs); Körper wie das konstruierte Rohr", enden)
fall("Breiter als 2 mm: aus dem Rohr, je ein Steg 2 mm an den Enden, Fenster als Innenkontur (auch Gehrung, Laschen)", stege)
fall("Ringe des ganzen Rohrs mit Außenradius, nächstes Normrohr bzw. Sondermaß", ringe)
fall("Rundrohr: Halbschale, Drittel, Spalt, schräges Ende, nächstes Normrohr", rund)


def schalen():
    # Halbschale genau 180°: zwei passen mit 5 mm Luft nicht -> eine je Rohr (mit Ringen)
    assert ERG["R_halb"].geschlossen.offene_seite["je_umfang"] == 1, ERG["R_halb"].geschlossen.offene_seite
    z = ERG["R_schale_162"].geschlossen
    os_ = z.offene_seite
    grad = os_["schale_grad"]
    assert 150 < grad < 170 and os_["je_umfang"] == 2 and os_["luft"] == 5.0, os_
    # ganz freigeschnitten: zwei Längskanten + Bögen an den Enden + Bohrung
    soll = 2 * L + 2 * 40 * math.pi * grad / 360 + 8 * math.pi
    assert abs(os_["schale_schnitt"] - soll) < 3, (os_["schale_schnitt"], soll)
    assert any("2 Schalen je Rohrumfang" in h for h in z.hinweise), z.hinweise


fall("Halbschalen: mehrere je Rohrumfang mit 5 mm Luft, je Schale ganz freigeschnitten", schalen)
fall("nicht geschlossen: Fenster über einen Teil der Länge, L-Profil", nicht_geschlossen)

# Spalten und JSON
mw = []


def spalten():
    netze = tmp / "netze"
    aus = tmp / "m.txt"
    step_messen.main(["--ausgabe", str(aus), "--netze", str(netze), "--json", str(tmp / "m.json"),
                      str(tmp / "A_spalt_2.step"), str(tmp / "K_U_offen.step"), str(tmp / "H_L_profil.step"),
                      str(tmp / "R_schale_162.step")])
    mw.extend(step.lade_netze(step.lies_messwerte(aus), netze))
    a, c, h, _ = mw
    assert a["profilform"] == "C-Profil" and step.geschlossen(a)["profil_id_vorschlag"] == "RE 60x40x2"
    assert c["profilform"] == "U-Profil" and step.geschlossen(c)["profil_id_vorschlag"] == "RE 60x50x2"
    assert not h["geschlossen"] and step._stege(step.geschlossen(c)) and not step._stege(step.geschlossen(a))
    js = json.loads((tmp / "m.json").read_text(encoding="utf-8"))
    k = js["dateien"][0]["koerper"][0]
    assert js["schema_version"] == "1.19" and k["geschlossen"]["offene_seite"]["seite"] in ("oben", "unten", "links",
                                                                                        "rechts"), k["geschlossen"]
    assert k["offene_seite"] is None and js["dateien"][2]["koerper"][0]["geschlossen"] is None
    assert js["dateien"][1]["koerper"][0]["geschlossen"]["offene_seite"]["steg"] == 2.0


fall("Spalte „geschlossen“ in den Messwerten, JSON 1.19 mit offene_seite", spalten)

RE = {"RE 60x40x2": dict(form="Rechteckrohr", a=60, b=40, wand=2)}
UP = {"C 60x40x2": dict(form="C-Profil", a=60, b=40, wand=2)}


def vorbelegen():
    a = dict(mw[0])
    n = step.offene_rohre_vorbelegen([a], {})
    assert n == 1 and a["profilform"] == "Rechteckrohr", (n, a["profilform"])    # Vorschlag der Messung
    a = dict(mw[0])
    # immer Rohr (Patrick „c“), auch wenn das C in den Stammdaten steht
    n = step.offene_rohre_vorbelegen([a], dict(RE, **UP))
    assert n == 1 and a["profilform"] == "Rechteckrohr", (n, a["profilform"])
    a = dict(mw[0])                         # Rohr zu groß für die Maschine: Kantteil („darüber hinaus immer Kantteil“)
    n = step.offene_rohre_vorbelegen([a], RE, dict(max_huellkreis=50))
    assert n == 0 and a["profilform"] == "Blech gekantet", (n, a["profilform"])
    assert "größer als Maschine zulässt, bleibt Kantteil" in a["hinweise"], a["hinweise"]
    # kein Rohrmaß (Sondermaß) bzw. liegt nicht ganz im Rohr: automatisch Kantteil (Patrick)
    for schluessel, text in (("normrohr", "kein Rohrmaß"), ("ueberstand", "nicht ganz im Rohr")):
        u = dict(mw[1])
        zu = step.geschlossen(u)
        os_ = json.loads(zu["offene_seite"])
        os_.update(normrohr=False) if schluessel == "normrohr" else os_.update(ueberstand=3.0)
        u["geschlossen"] = json.dumps(dict(zu, offene_seite=json.dumps(os_)))
        n = step.offene_rohre_vorbelegen([u], RE)
        assert n == 0 and u["profilform"] == "Blech gekantet" and text in u["hinweise"], (n, u["profilform"])
    a = dict(mw[0])
    assert step.offene_rohre_vorbelegen([a], RE) == 1 and a["profilform"] == "Rechteckrohr" and step.rohr_geschlossen(a)
    assert step.offene_rohre_vorbelegen([a], {}) == 0 and a["profilform"] == "Rechteckrohr"    # nur einmal
    t = entpacken(a["_netz"])["t"]
    assert "EW" in t and "EO" not in t, list(t)
    assert step.art_text(a).endswith("Spalt geschlossen") and \
        step.art_text(step.geschlossen(a), a).endswith("mit Spalt (nicht geschlossen)")
    assert step.rohr_wechseln(a) and a["profilform"] == "C-Profil" and not step.rohr_geschlossen(a)
    assert "EO" in entpacken(a["_netz"])["t"] and step.geschlossen(a)["profilform"] == "Rechteckrohr"
    c = dict(mw[1])                         # U offen: aus dem Rohr mit Stegen
    n = step.offene_rohre_vorbelegen([c], RE)
    assert n == 1 and c["profilform"] == "Rechteckrohr", (n, c["profilform"])
    assert step.art_text(c).endswith("Ringe an den Enden (aus dem Rohr)") and \
        step.art_text(step.geschlossen(c), c).endswith("offen (ohne Ringe)")
    assert "EW" in entpacken(c["_netz"])["t"]
    os_ = json.loads(c["offene_seite"])
    assert os_["steg"] == 2.0 and os_["radius"] > 0, os_
    # anderes Rohr gewählt (Patrick: „einfach das Rohr ändern“): Fenster über der offenen Seite mit, 2 × Unterschied
    seite = os_["breite"] + 2 * float(c["wandstaerke"])
    groesser = dict(form="Rechteckrohr", profil_id="RE 70x40x2", a=seite + 10 if seite > 45 else 60,
                    b=40 if seite > 45 else seite + 10, wand=2)
    diff, text = step.fenster_neu(c, groesser)
    assert abs(diff - 20) < 0.01 and "Fenster" in text, (diff, text)


fall("Programm: immer Rohr (auch ohne Stammdaten, C im Stamm), zu groß für die Maschine Kantteil, U offen mit "
     "Stegen, rot/blassrot, anderes Rohr gewählt: Fenster umgerechnet", vorbelegen)


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
    # Kantteil immer als Auswahl (Patrick): das offene Teil in der anderen Art
    assert texte[cb.findData("offen_alt")] == "Kantteil (Blech gekantet)", texte
    d._zeigen(z.it)
    assert "EW" in d.ansicht.ansicht.netz["t"], list(d.ansicht.ansicht.netz["t"])
    d.ansicht.ansicht.grab()
    neu = d.art_gewaehlt(0, "zu")
    assert neu is not None and d.messwerte[0]["profilform"] == "C-Profil"
    d.art_gewaehlt(0, "zu")
    assert d.messwerte[0]["profilform"] == "Rechteckrohr"
    d.art_gewaehlt(0, "offen_alt")
    assert d.messwerte[0]["profilform"] == "Blech gekantet", d.messwerte[0]["profilform"]
    # ohne Blechliste steht das Kantteil nicht als Zeile im Dialog: zurück über die Messwerte
    assert step.art_wechseln(d.messwerte[0]) and step.rohr_wechseln(d.messwerte[0])
    assert d.messwerte[0]["profilform"] == "Rechteckrohr", d.messwerte[0]["profilform"]
    erg = step.uebernehmen(d.messwerte, [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
    p = erg["positionen"][0]
    assert p["profil_id"] == "RE 60x40x2" and abs(p["laenge"] - 300) < 0.01, p


fall("Prüfdialog: Rohr vorbelegt, Art umschaltbar (Spalt offen ↔ geschlossen), 3D rot, Übernahme als RE 60x40x2", dialog)


def schalen_programm():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import rechnen
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.step_dialog import StepPruefDialog
    QApplication.instance() or QApplication([])
    db = Datenbank(tmp / "rohrlaser2.db")
    k = db.kontext()
    m = [dict(mw[3])]
    d = StepPruefDialog(None, m, k, "S235-10219", 5)
    assert step.schalen_gewaehlt(m[0]) and m[0]["profilform"] == "Rundrohr", m[0]["profilform"]
    cb = d.baum.itemWidget(d.zeilen[0].it, d.SP_ART)
    texte = [cb.itemText(n) for n in range(cb.count())]
    assert texte[0].endswith("2 Schalen je Umfang (ganz freigeschnitten)") and cb.findData("schalen") > 0, texte
    sch = step.schalen(m[0])
    erg = step.uebernehmen(d.messwerte, [], k, db.zeilen("gewinde"), None, "S235-10219", 5)
    p = erg["positionen"][0]
    assert p["je_umfang"] == 2 and abs(p["schneidweg"] - sch["schale_schnitt"]) < 0.2, p
    assert abs(p["a_schnitt"] + p["b_schnitt"] + p["innen"] - p["schneidweg"]) < 0.3, p
    assert any("Halbschalen: 2 je Rohrumfang" in b for b in erg["bericht"]), erg["bericht"]
    # Rohrstücke = Stückzahl ÷ 2 aufgerundet (2a): 5 Schalen -> 3 Rohrstücke in der Optimierung
    p = dict(p, profil_id="RR 40x2", werkstoff_id="S235-10219", stueck=5)
    assert rechnen.rohrstuecke(p) == 3 and rechnen.rohrstuecke(dict(p, je_umfang=None)) == 5
    gr, fehl, _ = rechnen.gruppen_bilden(dict(maschine="T03", stange=6000), [p], k)
    assert not fehl and sum(len(g.teile) for g in gr) == 3, (fehl, gr)
    # eine je Rohr (mit Ringen) umgeschaltet, bzw. nur 1 Stück: keine Schalen
    d.art_gewaehlt(0, "schalen")
    assert not step.schalen_gewaehlt(d.messwerte[0])
    assert step.art_text(d.messwerte[0]).endswith("Ringe an den Enden (aus dem Rohr)")
    erg = step.uebernehmen(d.messwerte, [], k, db.zeilen("gewinde"), None, "S235-10219", 5)
    assert not erg["positionen"][0].get("je_umfang"), erg["positionen"][0]
    m1 = [dict(mw[3])]
    StepPruefDialog(None, m1, k, "S235-10219", 1)
    erg = step.uebernehmen(m1, [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
    assert not erg["positionen"][0].get("je_umfang"), erg["positionen"][0]


fall("Halbschalen im Programm: Art umschaltbar, je Umfang in der Position, Rohrstücke = Stück ÷ je Umfang", schalen_programm)


def winkel_aus_groesserem():
    # Winkel gibt es nur größer (Patrick: „Winkel 33x30x6 gab es nur als 60x40x6“, ein Winkelprofil): von Hand das
    # größere Profil gewählt -> je Schenkel ein Längsschnitt zwischen den Stegen 2 mm + zwei Querschnitte um die Stege
    from rohrlaser.datenbank import Datenbank
    db = Datenbank(tmp / "rohrlaser3.db")
    k = db.kontext()
    k.profile["L 60x50x3"] = dict(profil_id="L 60x50x3", form="L-Profil", a=60, b=50, wand=3)
    w = dict(mw[2])
    assert w["profilform"] == "L-Profil" and round(float(w["abm_a"])) == 50 and round(float(w["abm_b"])) == 40, w
    diff, text = step.fenster_neu(w, dict(k.profile["L 60x50x3"], profil_id="L 60x50x3"))
    assert abs(diff - 2 * (300 - 4 + 2 * 10)) < 0.01 and "2 Schenkel gekürzt" in text, (diff, text)
    ohne = step.uebernehmen([dict(w, _uebernehmen=True)], [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
    mit = step.uebernehmen([dict(w, _uebernehmen=True, _profil="L 60x50x3")], [], k, db.zeilen("gewinde"), None,
                           "S235-10219", 1)
    p0, p1 = ohne["positionen"][0], mit["positionen"][0]
    assert p1["innen"] >= p0["innen"] + diff - 0.1 and p1["schneidweg"] > p0["schneidweg"] + diff, \
        ({x: p0.get(x) for x in ("profil_id", "schneidweg", "innen")}, {x: p1.get(x) for x in ("profil_id", "schneidweg", "innen")}, mit["bericht"])
    assert any("L-Profil aus L 60x50x3" in b for b in mit["bericht"]), mit["bericht"]
    # U: Steg gleich, beide Schenkel kürzer; Steghöhe anders -> Hinweis
    u = dict(w, profilform="U-Profil", abm_a="60", abm_b="30")
    assert abs(step.fenster_neu(u, dict(form="U-Profil", a=60, b=40, profil_id="U 60x40"))[0] - 2 * (296 + 20)) < 0.01
    assert step.fenster_neu(u, dict(form="U-Profil", a=80, b=40, profil_id="U 80x40"))[0] == 0.0
    # gibt es das Profil gar nicht: Rohr gewählt -> 2 Längsschnitte zwischen den Ringen + je Ring der freie Umfang
    from rohrlaser import optimierung as opt
    diff, text = step.fenster_neu(w, dict(form="Rechteckrohr", a=60, b=50, wand=3, profil_id="RE 60x50x3"))
    soll = 2 * (300 - 4) + 2 * (opt.schnittlaenge("Rechteckrohr", 60, 50, 3) -
                                opt.schnittlaenge("L-Profil", float(w["abm_a"]), float(w["abm_b"]), 3))
    assert abs(diff - soll) < 0.01 and "Ring 2 mm" in text, (diff, soll, text)


fall("Winkel/U/C aus größerem Profil (Schenkel gekürzt, Stege 2 mm) oder aus dem Rohr (Ringe + Fenster)", winkel_aus_groesserem)


def winkel_33_auf_60():
    # Patricks Fall 25.10.2026: Winkel 33x30x6 auf 60x40x6 geändert, die 2 mm Stege kamen nicht. (1) Profil fehlt in
    # den Stammdaten und wird angelegt: Maße aus dem Namen, nicht aus der Messung; (2) Rohr-Editor rechnet dasselbe;
    # (3) Profil erst nach dem Import in der Positionstabelle geändert: Schneidweg automatisch mit den Stegen
    from rohrlaser import rechnen, schneidweg as sw
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.fenster import Hauptfenster
    schreibe(profil([(0, 0), (33, 0), (33, 6), (6, 6), (6, 30), (0, 30)], 500), "W33", tmp)
    step_messen.main(["--ausgabe", str(tmp / "w33.txt"), "--netze", str(tmp / "w33"), str(tmp / "W33.step")])
    w = step.lade_netze(step.lies_messwerte(tmp / "w33.txt"), tmp / "w33")[0]
    assert w["profilform"] == "L-Profil" and w["profil_id_vorschlag"] == "L 33x30x6", w["profil_id_vorschlag"]
    db = Datenbank(tmp / "w33.db")
    k = db.kontext()
    assert "L 60x40x6" not in k.profile
    soll = 2 * (500 - 4) + 2 * (27 + 10)            # Längsschnitte zwischen den Stegen + Querschnitte um die Stege
    erg = step.uebernehmen([dict(w, _uebernehmen=True, _profil="L 60x40x6")], [], k, db.zeilen("gewinde"), None,
                           "S235-10219", 1, neue_profile=True)
    p = erg["positionen"][0]
    neu = next(x for x in erg["profile"] if x["profil_id"] == "L 60x40x6")
    assert (neu["a"], neu["b"], neu["wand"]) == (60, 40, 6), neu
    assert abs(p["innen"] - soll) < 0.1 and abs(p["schneidweg"] - (soll + 200)) < 0.1, (p["innen"], p["schneidweg"])
    assert any("2 Schenkel gekürzt" in b for b in erg["bericht"]), erg["bericht"]
    pr = dict(profil_id="L 60x40x6", form="L-Profil", a=60, b=40, wand=6)
    r = sw.rechnen(sw.lesen(p["technik"]), pr, rechnen.kontur_regel(None, 6))
    assert abs(r["felder"]["schneidweg"] - p["schneidweg"]) < 0.1 and abs(r["felder"]["innen"] - soll) < 0.1, r["felder"]
    assert sum(1 for x in r["schritte"] if x.get("art") == "Längsschnitt") == 2 and r["felder"]["gross_n"] == 2, r
    # ohne Profilwechsel: wie gemessen
    ohne = step.uebernehmen([dict(w, _uebernehmen=True)], [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
    p0 = ohne["positionen"][0]
    assert p0["profil_id"] == "L 33x30x6" and not p0["innen"], p0
    r = sw.rechnen(sw.lesen(p0["technik"]), dict(pr, profil_id="L 33x30x6", a=33, b=30), rechnen.kontur_regel(None, 6))
    assert abs(r["felder"]["schneidweg"] - p0["schneidweg"]) < 0.1 and not r["felder"]["innen"], r["felder"]
    # in der Positionstabelle geändert
    db.profile_anlegen([dict(profil_id="L 33x30x6", form="L-Profil", a=33, b=30, wand=6),
                        dict(profil_id="L 60x40x6", form="L-Profil", a=60, b=40, wand=6)])
    fenster = Hauptfenster(db, tmp, stumm=True)
    an = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
    werte = {x: p0.get(x) for x in ("pos", "artikel", "profil_id", "werkstoff_id", "laenge", "stueck", "schneidweg",
                                    "einstiche", "innen", "technik", "a_schnitt", "b_schnitt", "a_gerade", "b_gerade",
                                    "konturen", "kontur_grenzen") if p0.get(x) is not None}
    db.position_neu(an, dict(werte, stueck=1))
    s = fenster.angebot_oeffnen(an)
    spalte = next(i for i, (art, f) in enumerate(s.pos_modell.spalten) if art == "feld" and f.name == "profil_id")
    assert s.pos_modell.setData(s.pos_modell.index(0, spalte), "L 60x40x6")
    q = s.positionen[0]
    assert q["profil_id"] == "L 60x40x6" and abs(q["innen"] - soll) < 0.1, {x: q.get(x) for x in werte}
    assert abs(q["schneidweg"] - (soll + 200)) < 0.1 and q["a_schnitt"] == 100, q["schneidweg"]
    assert s.pos_modell.setData(s.pos_modell.index(0, spalte), "L 33x30x6")     # zurück: wie gemessen
    q = s.positionen[0]
    assert abs(q["schneidweg"] - p0["schneidweg"]) < 0.1 and not q["innen"], q["schneidweg"]
    fenster.close()


fall("Winkel 33x30x6 → 60x40x6: Profil aus dem Namen angelegt, Stege 2 mm im Import, Rohr-Editor und in der Tabelle",
     winkel_33_auf_60)

print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
sys.exit(1 if fehler else 0)
