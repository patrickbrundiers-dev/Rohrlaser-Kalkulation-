"""Testreihe sichere Erkennung (Patrick 03.11.2026: „Test für verschiedene Dreh- und Frästeile für sichere Erkennung“,
„Blech-Erkennung weiter verbessern“). Alle Teile werden hier gebaut (tests/formen_baukasten.py):
- V1 14 Drehteile: Fase, Kopf, Distanzhülse, Innenabsatz, Querbohrung, Schlüsselfläche, Kegel, Rolle mit Radius,
  Flansch mit Absatz, Kugelende, Stufenwelle schräg im Raum, Buchse mit Fasen, Sackloch, lange Welle mit Einstichen.
- V2 7 Frästeile: Lagerbock, Nut, Fasen, Spannklotz schräg im Raum, Stufe, Gabelkopf, Platte mit zwei Taschen.
- V3 8 Laserteile und Vollmaterial bleiben wie bisher (Rohr mit Fase am Ende, kurzes und dickwandiges Rohr, QR mit
  Bohrungen, Rundstahl, L-Profil, Langloch, Sechskant).
- V4 Maße und Lage: Hüllmaße, Durchmesser; gleiches Teil in anderer Lage hat denselben Fingerabdruck.
- V5 17 Bleche in beiden Einstellungen „Flache Teile als“: Lochbleche, Ausschnitte, Kleinteile, Laschen, Ronde, Ring,
  Senkungen, Dreieck, Knotenblech, dicke Platte, Schweißfase, schräg im Raum (Dicke ohne Rundungsrest); Kantteile mit
  Biegeradien sind Blech gekantet (Profil als Auswahl), ein scharfkantiger Winkel bleibt L-Profil.
- V6 Kantprofile mit Standardmaß (U-Stahl nach Patricks Liste, Kant-C, Kant-L) bleiben Profil; ein Kantteil, dessen Profil in den Stammdaten steht,
  wird im Programm wieder Profil.
- V7 Datenbank: Kantprofile als Standard in den Profilen.

Aufruf: python tests/test_erkennung_vielfalt.py
"""
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
import erzeuge_testteile as et  # noqa: E402
from formen_baukasten import (fase, gerade_kanten_parallel, kegel, kreiskanten_bei, kugel, lage, ohne, plus,  # noqa: E402
                              prisma, quader, radius, schreibe, zyl)
from step_geometrie import analysiere_datei  # noqa: E402

fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


def sechseck(sw):
    r = sw / math.sqrt(3)
    return [(r * math.cos(math.radians(30 + 60 * i)), r * math.sin(math.radians(30 + 60 * i))) for i in range(6)]


def kegel_bei(r1, r2, h, x, y, z):
    from formen_baukasten import verschiebe
    return verschiebe(kegel(r1, r2, h, z), x, y, 0)


def loecher(s, dicke, pos, r):
    return ohne(s, *[zyl(r, dicke + 2, -1, x, y) for x, y in pos])


STUFENWELLE = plus(zyl(15, 40), zyl(10, 60, 40), zyl(8, 20, 100))
SPANNKLOTZ = ohne(quader(60, 40, 30), quader(40, 20, 10, 10, 10, 20), zyl(4, 30, 0, 8, 8))
DREH = {
    "DV01_Welle_Fase_beidseitig": fase(zyl(12.5, 100), kreiskanten_bei([0, 100]), 1.0),
    "DV02_Bolzen_mit_Kopf": plus(zyl(12.5, 8), zyl(8, 52, 8)),
    "DV03_Distanzhuelse_30_17": ohne(zyl(15, 20), zyl(8.5, 20)),
    "DV04_Huelse_Innenabsatz": ohne(zyl(20, 60), zyl(15, 20), zyl(10, 60)),
    "DV05_Achse_Querbohrung": ohne(plus(zyl(10, 30), zyl(7.5, 50, 30)), zyl(2.5, 30, 65, -15, 0, (1, 0, 0))),
    "DV06_Welle_Schluesselflaeche": ohne(plus(zyl(12.5, 60), zyl(10, 40, 60)), quader(30, 10, 30, -15, 10, 15)),
    "DV07_Kegelzapfen": plus(zyl(10, 40), kegel(10, 5, 20, 40)),
    "DV08_Rolle_Radius": radius(ohne(zyl(30, 25), zyl(10, 25)), kreiskanten_bei([0, 25], 20), 3.0),
    "DV09_Flansch_Absatz": ohne(plus(zyl(50, 12), zyl(30, 10, 12)), zyl(20, 22)),
    "DV10_Achse_Kugelende": plus(zyl(8, 60), kugel(8, 60)),
    "DV11_Stufenwelle_schraeg_im_Raum": lage(STUFENWELLE),
    "DV12_Buchse_Fase_innen_aussen": fase(ohne(zyl(20, 30), zyl(12.5, 30)), kreiskanten_bei([0, 30]), 1.0),
    "DV13_Gewindestift_Sackloch": ohne(zyl(10, 40), zyl(4, 15)),
    "DV14_Welle_Einstiche_lang": ohne(zyl(15, 300), ohne(zyl(16, 2, 50), zyl(13.5, 2, 50)),
                                      ohne(zyl(16, 2, 250), zyl(13.5, 2, 250))),
    "DV15_Stufenwelle": STUFENWELLE,
}
FRAES = {
    "FV01_Lagerbock_Absatz": ohne(quader(80, 40, 50), quader(80, 10, 20, 0, 30, 30), zyl(10, 40, 35, 40, 0, (0, 1, 0))),
    "FV02_Block_Nut": ohne(quader(60, 40, 25), quader(60, 12, 8, 0, 14, 17)),
    "FV03_Klotz_Fasen": fase(quader(50, 40, 30), gerade_kanten_parallel((1, 0, 0)), 3.0),
    "FV04_Spannklotz_schraeg_im_Raum": lage(SPANNKLOTZ),
    "FV05_Platte20_Stufe": ohne(quader(120, 80, 20), quader(40, 80, 10, 80, 0, 10)),
    "FV06_Gabelkopf": ohne(quader(40, 30, 30), quader(20, 30, 12, 10, 0, 18), zyl(4, 40, 24, 0, 15, (1, 0, 0))),
    "FV07_Platte_zwei_Taschen": ohne(quader(150, 100, 25), quader(40, 30, 10, 15, 15, 15), quader(40, 30, 10, 90, 50, 15)),
    "FV08_Spannklotz": SPANNKLOTZ,
}
LASER = {       # Name: erwartete Form (bleibt wie bisher)
    "LV01_RR60_Fase_Ende": (fase(ohne(zyl(30.15, 300), zyl(27.25, 300)), kreiskanten_bei([300], 29), 1.0), "Rundrohr"),
    "LV02_RR60_kurz_30": (ohne(zyl(30.15, 30), zyl(27.25, 30)), "Rundrohr"),
    "LV03_RR60x8_lang": (ohne(zyl(30.15, 400), zyl(22.15, 400)), "Rundrohr"),
    "LV04_QR40_Bohrungen": (ohne(quader(40, 40, 400), quader(34, 34, 400, 3, 3), zyl(4, 50, 100, 20, -5, (0, 1, 0)),
                                 zyl(4, 50, 300, 20, -5, (0, 1, 0))), "Quadratrohr"),
    "LV05_Rundstahl_lang": (zyl(10, 500), "Rundstahl"),
    "LV06_L50x5": (ohne(quader(50, 50, 500), quader(45, 45, 500, 5, 5)), "L-Profil"),
    "LV07_RR42_Langloch": (ohne(zyl(21.2, 400), zyl(18.6, 400), quader(10, 30, 40, -5, 0, 180)), "Rundrohr"),
    "LV08_Sechskant_SW22": (prisma(sechseck(22), 300), "offenes Sonderprofil"),
}
BLECH = {       # Name: (Form, Blech-Modus, Vorgabe 150 mm)
    "BV01_Blech3_20_Loecher": (loecher(quader(300, 200, 3), 3, [(20 + 30 * i, 30 + 40 * j) for i in range(5)
                                                                  for j in range(4)], 4), "Blech", "Blech"),
    "BV02_Blech2_Langloch_Ausschnitt": (ohne(quader(250, 150, 2), quader(60, 10, 4, 30, 30, -1),
                                             quader(80, 50, 4, 120, 60, -1)), "Blech", "Blech"),
    "BV03_Kleinteil_1mm": (loecher(quader(50, 20, 1), 1, [(10, 10)], 2.5), "Blech", "Blech"),
    "BV04_Lasche_100x30x8": (loecher(quader(100, 30, 8), 8, [(15, 15), (85, 15)], 6.5), "Blech", "Flachstahl"),
    "BV05_Flachstreifen_600x40x10": (quader(600, 40, 10), "Blech", "Flachstahl"),
    "BV06_Ronde_200x5": (loecher(zyl(100, 5), 5, [(0, 0)], 10), "Blech", "Blech"),
    "BV07_Ring_100_60x10": (ohne(zyl(50, 10), zyl(30, 10)), "Blech", "Blech"),
    "BV08_Blech5_Senkungen": (ohne(quader(200, 100, 5), *[plus(zyl(3.3, 7, -1, x, 50), kegel_bei(3.3, 6.3, 3, x, 50, 2))
                                                          for x in (40, 160)]), "Blech", "Blech"),
    "BV09_Kantteil_L_R3": (et.profil([(0, 0), (100, 0), (100, 3), (3, 3), (3, 50), (0, 50)], 200, {(0, 0): 6, (3, 3): 3}),
                           "Blech gekantet", "Blech gekantet"),
    "BV10_Kantteil_U_Loecher": (ohne(et.profil([(0, 0), (85, 0), (85, 40), (82, 40), (82, 3), (3, 3), (3, 40), (0, 40)],
                                               150, {(0, 0): 5, (85, 0): 5, (3, 3): 2, (82, 3): 2}),
                                     zyl(4, 100, 75, -10, 20, (1, 0, 0))), "Blech gekantet", "Blech gekantet"),
    # (Rohr wäre 85 × 45 statt 85 × 40: kein offenes Rohr, Patrick 03.11.2026 17:22)
    "BV18_Kantteil_U_85x40,8": (et.profil([(0, 0), (85, 0), (85, 40.8), (82, 40.8), (82, 3), (3, 3), (3, 40.8),
                                           (0, 40.8)], 150, {(0, 0): 5, (85, 0): 5, (3, 3): 2, (82, 3): 2}),
                                "Blech gekantet", "Blech gekantet"),    # krummes Außenmaß: kein Rohr (Patrick 03.11.)
    "BV11_Dreieckblech_4mm": (prisma([(0, 0), (200, 0), (0, 120)], 4), "Blech", "Blech"),
    "BV12_Blech_schraeg_im_Raum": (lage(loecher(quader(300, 150, 4), 4, [(30, 30), (270, 120)], 5)), "Blech", "Blech"),
    "BV13_Platte15_300x300": (loecher(quader(300, 300, 15), 15, [(20, 20), (280, 20), (20, 280), (280, 280)], 9),
                              "Blech", "Blech"),
    "BV14_Blech_Schweissfase": (fase(quader(200, 100, 10), gerade_kanten_parallel((0, 1, 0)), 3.0), "Blech", "Blech"),
    "BV15_Knotenblech_Polygon": (loecher(prisma([(0, 0), (150, 0), (150, 60), (90, 120), (0, 120)], 6), 6,
                                         [(30, 30), (120, 30), (30, 90)], 7), "Blech", "Blech"),
    "BV16_Winkel_scharfkantig": (et.profil([(0, 0), (60, 0), (60, 4), (4, 4), (4, 60), (0, 60)], 80), "L-Profil",
                                 "L-Profil"),
    "BV17_Flach_30x5_L80_kurz": (quader(80, 30, 5), "Blech", "Blech"),
}
KANT = {        # Standard-Kantprofile (Patrick 03.11.2026): bleiben Profil mit Normname
    "KV01_U_Stahl_80x50x4": (et.profil([(0, 0), (80, 0), (80, 50), (76, 50), (76, 4), (4, 4), (4, 50), (0, 50)], 600,
                                       {(0, 0): 8, (80, 0): 8, (4, 4): 4, (76, 4): 4}), "U-Profil", "U-Stahl 80x50x4"),
    "KV04_U_Stahl_40x20x3": (et.profil([(0, 0), (40, 0), (40, 20), (37, 20), (37, 3), (3, 3), (3, 20), (0, 20)], 300,
                                       {(0, 0): 6, (40, 0): 6, (3, 3): 3, (37, 3): 3}), "U-Profil", "U-Stahl 40x20x3"),
    "KV02_Kant_C_100x50x20x3": (et.profil([(0, 0), (50, 0), (50, 20), (47, 20), (47, 3), (3, 3), (3, 97), (47, 97),
                                           (47, 80), (50, 80), (50, 100), (0, 100)], 600,
                                          {(0, 0): 6, (50, 0): 6, (50, 100): 6, (0, 100): 6, (3, 3): 3, (47, 3): 3,
                                           (47, 97): 3, (3, 97): 3}), "C-Profil", "Kant-C 100x50x20x3"),
    "KV03_Kant_L_50x50x3": (et.profil([(0, 0), (50, 0), (50, 3), (3, 3), (3, 50), (0, 50)], 600, {(0, 0): 6, (3, 3): 3}),
                            "L-Profil", "Kant-L 50x50x3"),
}
TMP = Path(tempfile.mkdtemp())
schreibe({**DREH, **FRAES, **{n: f for n, (f, _) in LASER.items()}, **{n: v[0] for n, v in BLECH.items()},
           **{n: v[0] for n, v in KANT.items()}}, TMP)
M = {}


def m(name, fb=150):
    if (name, fb) not in M:
        (M[name, fb],) = analysiere_datei(TMP / f"{name}.step", flach_bis=fb)
    return M[name, fb]


def merk(t):
    return (t.drehfraes or {}).get("merkmale") or []


@fall("V1 Drehteile: 15 Formen (auch schräg im Raum) sind Drehteile mit dem passenden Merkmal")
def _():
    soll = {"DV01": "Fase", "DV02": "Außendurchmesser", "DV03": "Buchse", "DV04": "Innendurchmesser",
            "DV05": "Außendurchmesser", "DV06": "Außendurchmesser", "DV07": "Kegel", "DV08": "Radius",
            "DV09": "Außendurchmesser", "DV10": "Radius", "DV11": "Außendurchmesser", "DV12": "Fase",
            "DV13": "Sackbohrung", "DV14": "Außendurchmesser", "DV15": "Außendurchmesser"}
    falsch = {n: (m(n).profilform, merk(m(n))) for n in DREH
              if m(n).profilform != "Drehteil" or not any(soll[n[:4]] in x for x in merk(m(n)))}
    assert not falsch, falsch
    assert "Querbohrung" in m("DV05_Achse_Querbohrung").drehfraes["zusatz"]
    assert "Schlüsselfläche/Abflachung" in m("DV06_Welle_Schluesselflaeche").drehfraes["zusatz"]
    # nur die Buchse (glatt, nur nach den Maßen) ist unsicher, alle anderen sicher
    unsicher = sorted(n for n in DREH if m(n).pruefstatus != "plausibel")
    assert unsicher == ["DV03_Distanzhuelse_30_17"], unsicher


@fall("V2 Frästeile: 8 Formen (auch schräg im Raum) sind Frästeile, Tasche/Absatz/Fase erkannt")
def _():
    falsch = {n: m(n).profilform for n in FRAES if m(n).profilform != "Frästeil"}
    assert not falsch, falsch
    for n in ("FV01_Lagerbock_Absatz", "FV02_Block_Nut", "FV04_Spannklotz_schraeg_im_Raum", "FV05_Platte20_Stufe",
              "FV07_Platte_zwei_Taschen", "FV08_Spannklotz"):
        assert "Absatz/Tasche" in merk(m(n)) and m(n).pruefstatus == "plausibel", (n, merk(m(n)), m(n).pruefstatus)
    assert "Fase/Schräge" in merk(m("FV03_Klotz_Fasen"))
    assert m("FV06_Gabelkopf").drehfraes["nur_abmessung"] and m("FV06_Gabelkopf").pruefstatus == "prüfen"


@fall("V3 Laserteile und Vollmaterial bleiben wie bisher (kein Dreh-/Frästeil)")
def _():
    falsch = {n: m(n).profilform for n, (_, soll) in LASER.items() if m(n).profilform != soll or m(n).drehfraes}
    assert not falsch, falsch


@fall("V4 Maße: Durchmesser/Länge/Hüllmaße stimmen, gleiches Teil in anderer Lage = gleicher Fingerabdruck")
def _():
    for n, (da, la) in {"DV01_Welle_Fase_beidseitig": (25, 100), "DV02_Bolzen_mit_Kopf": (25, 60),
                        "DV09_Flansch_Absatz": (100, 22), "DV11_Stufenwelle_schraeg_im_Raum": (30, 120),
                        "DV14_Welle_Einstiche_lang": (30, 300)}.items():
        d = m(n).drehfraes
        assert abs(d["durchmesser"] - da) < 0.05 and abs(d["laenge"] - la) < 0.05, (n, d["durchmesser"], d["laenge"])
    for n, h in {"FV07_Platte_zwei_Taschen": (150, 100, 25), "FV04_Spannklotz_schraeg_im_Raum": (60, 40, 30),
                 "FV01_Lagerbock_Absatz": (80, 50, 40)}.items():
        d = m(n).drehfraes
        ist = (d["laenge"], d["breite"], d["hoehe"])
        assert all(abs(a - b) < 0.1 for a, b in zip(ist, h)), (n, ist)
    for a, b in (("DV11_Stufenwelle_schraeg_im_Raum", "DV15_Stufenwelle"),
                 ("FV04_Spannklotz_schraeg_im_Raum", "FV08_Spannklotz")):
        assert m(a).drehfraes["fingerabdruck"] == m(b).drehfraes["fingerabdruck"], \
            (m(a).drehfraes["fingerabdruck"], m(b).drehfraes["fingerabdruck"])


@fall("V5 Bleche in beiden Einstellungen: Blech, Flachstahl, Blech gekantet, Dicke ohne Rundungsrest")
def _():
    falsch = {}
    for n, (_, soll_blech, soll_vorgabe) in BLECH.items():
        for fb, soll in ((0, soll_blech), (150, soll_vorgabe)):
            if m(n, fb).profilform != soll or m(n, fb).drehfraes:
                falsch[n, fb] = m(n, fb).profilform
    assert not falsch, falsch
    assert m("BV12_Blech_schraeg_im_Raum", 0).blech["dicke"] == 4.0, m("BV12_Blech_schraeg_im_Raum", 0).blech["dicke"]
    t = m("BV09_Kantteil_L_R3")
    assert t.pruefstatus == "prüfen" and t.alternative and t.alternative.profilform == "L-Profil", t.alternative
    # U-Kantteil mit Radien: das Rohr wäre größer als das Teil (85 × 45) -> Blech gekantet, U-Profil und Rohr als
    # Auswahl (Patrick 03.11.2026 17:22)
    t = m("BV10_Kantteil_U_Loecher")
    assert t.geschlossen and t.alternative and t.alternative.profilform == "U-Profil", (t.geschlossen, t.alternative)
    assert m("BV16_Winkel_scharfkantig").alternative.profilform == "Blech gekantet"
    assert m("BV06_Ronde_200x5").blech["dicke"] == 5.0 and m("BV13_Platte15_300x300", 0).blech["dicke"] == 15.0


@fall("V6 Kantprofile: Standardmaße bleiben Profil (Kant-U/C/L), andere Kantteile Blech gekantet; Stammdaten")
def _():
    for n, (_, form, norm) in KANT.items():
        t = m(n)
        assert (t.profilform, t.normprofil) == (form, norm), (n, t.profilform, t.normprofil, t.abm_a, t.abm_b,
                                                             t.wandstaerke)
        assert t.profil_id_vorschlag == norm, t.profil_id_vorschlag
    # Programm: ein Kantteil, dessen Profil in den Stammdaten steht, wird wieder Profil (einmal, Wahl bleibt)
    import json
    import step_messen
    from rohrlaser import step
    aus, js = TMP / "k.txt", TMP / "k.json"
    step_messen.main(["--ausgabe", str(aus), "--json", str(js), str(TMP / "BV09_Kantteil_L_R3.step")])
    (mw,) = step.lies_messwerte(aus)
    assert mw["profilform"] == "Blech gekantet" and step.alternative(mw)["profilform"] == "L-Profil"
    assert step.kantprofil_vorbelegen([dict(mw)], {}) == 0
    profile = {"L 100x50x3": dict(form="L-Profil", a=100, b=50, wand=3)}
    assert step.kantprofil_vorbelegen([mw], profile) == 1 and mw["profilform"] == "L-Profil" and mw["_kp_zurueck"]
    assert step.kantprofil_vorbelegen([mw], profile) == 0, "nur einmal"
    json.loads(js.read_text(encoding="utf-8"))


@fall("V7 Datenbank: Kantprofile als Standard in den Profilen (neu und nachgetragen, gelöschte UPN bleiben weg)")
def _():
    from rohrlaser import normprofile
    from rohrlaser.datenbank import KANTPROFILE_STAND, Datenbank
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "r.db")
        prof = db.kontext().profile
        assert all(n in prof for n in normprofile.KANT_STAMMDATEN), "neue Datenbank"
        z = prof["U-Stahl 80x50x4"]
        assert z["form"] == "U-Profil" and float(z["wand"]) == 4 and abs(float(z["flaeche_manuell"]) - 675.16) < 0.1, z
        db.con.execute("DELETE FROM profile WHERE profil_id IN ('Kant-C 100x50x20x3', 'UPN 100')")
        db.con.execute("UPDATE einstellungen SET wert=? WHERE name='kantprofile_stand'", ('"alt"',))
        db.con.commit()
        db.schliessen()
        db = Datenbank(Path(tmp) / "r.db")
        prof = db.kontext().profile
        assert "Kant-C 100x50x20x3" in prof and "UPN 100" not in prof
        assert db.einstellung("kantprofile_stand") == KANTPROFILE_STAND
        formen = db.einstellung("profilformen") or ""
        assert not formen or all(f in formen for f in ("U-Profil", "C-Profil", "L-Profil")), formen
        db.schliessen()


if fehler:
    print(f"{fehler} Fall/Fälle rot")
    sys.exit(1)
print("Alle Erkennungs-Testreihen bestanden.")
