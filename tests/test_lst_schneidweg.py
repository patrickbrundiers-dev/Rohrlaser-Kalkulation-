"""Programmierten Schneidweg aus einer TRUMPF-LST lesen (Patrick 24.11.2026: „So ist der programmierte Schneidweg.
Kannst du das aus der .lst auch so auslesen“; rohrlaser/lst_bahn.py, step_messung/step_lst.py):
- S1 Schneidweg: Konturen aus dem NC-Teil (TC_POS, TC_LASER_ON/OFF, G01/G02, A-Drehung), Anfahrt (;LeadIn) getrennt,
  Trennschnitte, halbe Schnittfuge aus den Trennschnitten, Bohrung an der Teilkante (Strahlmitte + halbe Fuge)
- S2 LST-Werte: Schnittlänge am Material wird Schneidweg, „Cutting length“ bleibt Maschinenweg, Laser-an-Zeit und
  Verfahrzeit aus CONSUMPTION_TIMES, Konturen je Klasse (Hüllmaß, Länge); unplausibler NC-Teil: Werte wie bisher
- S3 3D: Rohr aus dem Schneidweg exakt wie die STEP (Volumen, Profil, Länge, Bohrung)
- S4 Kalkulation: Laser-an-Zeit als reine Laserzeit, Verfahrzeit der LST statt Verfahren/Drehen, gemessene Zeit
  vor berechneter, nur das Fehlende (Nebenzeit, Entnahme) berechnet; (Patrick 24.11.: „als reine Laserzeit nutzen und die restlichen
  Werte dazurechnen wie jetzt auch“), Einstiche enthalten (Entscheidung Patrick) bzw. eigener Posten, Einstellung
  ganz/nein, Schneidzeit von Hand geht vor; Konturklassen als Text
- S5 BPF: Geschwindigkeitsstufe je Kontur im Bericht
Synthetische Dateien im Aufbau der echten (keine Kundendaten im Repo).

Aufruf: python tests/test_lst_schneidweg.py
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

from rohrlaser import lst_bahn, rechnen  # noqa: E402
from rohrlaser import trumpf_programm as tp  # noqa: E402

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


def abschnitt(name, namen, zeilen):
    mm = "\n".join(f"MM,AT,1,{10 * (i + 1):4d},1,1,,'{n}',,'',T" for i, n in enumerate(namen))
    da = ["DA," + ",".join(f"'{w}'" if isinstance(w, str) else str(w) for w in z) for z in zeilen]
    return f"BEGIN_{name}\nC\nZA,MM,{len(namen)}\n{mm}\nC\nZA,DA,{len(zeilen)}\n" + "\n".join(da) + \
        f"\nC\nENDE_{name}\nC\n"


B, WAND, RE, L, HALB, R_BOHR = 40.0, 2.0, 4.0, 200.0, 0.1, 5.0    # Quadratrohr 40×40×2 R4, Bohrung Ø10


def ring_nc(x):
    """Trennschnitt um das Quadratrohr bei x: je Seite G01 in Y, um die Ecken Y, Z und A zusammen (1°-Schritte, die
    Schneidkopf-Mitte bleibt senkrecht über der Kante wie bei TubeCAM)."""
    ay = B / 2 - RE
    out = [f"TC_POS({x},{-ay},0,0)", 'TC_LASER_ON(1,"ST020",1,100)']
    for seite in range(4):
        out.append(f"G01 Y{ay:.4f} A{90 * seite} ;Processing")
        for g in range(1, 91):
            a = math.radians(90 * seite + g)
            cy, cz = [(ay, ay), (ay, -ay), (-ay, -ay), (-ay, ay)][seite]
            y, z = cy + RE * math.sin(a), cz + RE * math.cos(a)
            out.append(f"G01 Y{y * math.cos(a) - z * math.sin(a):.4f} Z{y * math.sin(a) + z * math.cos(a):.4f} "
                       f"A{90 * seite + g}")
    return out + ["TC_LASER_OFF(2)"]


def lst(weg=420.0, nc=True, verbrauch=True):
    """LST eines Teils: Quadratrohr 40×40×2 R4, Länge 200, Trennschnitt vorn/hinten (Strahlmitte 0,1 mm im Abfall),
    Bohrung Ø10 oben (Strahl auf Ø9,8, mit Anfahrt aus der Mitte), Restzerteilung des Abfalls."""
    info = abschnitt("EINRICHTEPLAN_INFO", ["Maschine", "Programmnummer", "Maschinenzeit", "Cutting length",
                                            "viewer name machine"], [["T11", "TEST_QR", 0.12, weg, "Tube 5000"]])
    tech = abschnitt("TUBE_TECH", ["Rohr-ID", "Querschnitt", "Rohrlaenge", "Wandstaerke", "Eckenradius (Rechteckrohr)",
                                   "Hoehe (Rechteckrohr)", "Breite (Rechteckrohr)",
                                   "(Huellkreis-)Durchmesser (Rechteck-/Rundrohr)", "Material", "Mass Per Meter"],
                     [["1_400X400X40_1_20", 1, 6000.0, WAND, RE, B, B, 0.0, "St37", 2.31]])
    teil = abschnitt("TUBE_PART_TECH", ["Tabellenidentifikator", "Querschnitt", "OriginalProgrammedTubeLength",
                                        "MachiningLength", "Work Part Length"], [["TPT-1", 1, L, L + 5, L]])
    zeit = abschnitt("TUBE_PART_TIMES", ["Calculated First Cut Machine Time", "Calculated Contour Machine Time",
                                         "Calculated Cut Off Machine Time", "Data Set Name"], [[1.5, 3.5, 1.5, "TPT-1"]])
    verb = abschnitt("CONSUMPTION_TIMES", ["ConsumptionGroup", "LaserPower", "OnTime"],
                     [[1, 0, 4.4], [2, 3000, 4.0], [2, 1500, 0.5], [2, 0, 2.0]]) if verbrauch else ""
    r = R_BOHR - HALB
    zeilen = ["BEGIN_PROGRAMM", "START_TEXT",
              "; BLOCK: TcSeparationCutFeature", *ring_nc(-HALB),
              "; BLOCK: TcToolpathCuttingContour3D", "N20 TC_POS(100,0,0,0)", 'TC_LASER_ON(1,"ST020",2,100)',
              f"G01 X{100 + r:.3f} Y0 ;LeadIn", f"G02 X{100 + r:.3f} Y0 I{-r:.3f} J0 ;Processing", "TC_LASER_OFF(2)",
              "; BLOCK: TcSeparationCutFeature", *ring_nc(L + HALB),
              "; BLOCK: TcCutupScrapFeature", f"N40 TC_POS({L + 20},0,0,0)", 'TC_LASER_ON(1,"ST020",1,100)',
              f"G01 X{L + 40} ;Processing", "TC_LASER_OFF(2)", "ENDE_PROGRAMM"] if nc else \
        ["BEGIN_PROGRAMM", 'TC_LASER_ON(1,"ST020",1,100)', "G1 X10", "TC_LASER_OFF(2)", "ENDE_PROGRAMM"]
    return "BD\nSET_METRIC\nC\n" + info + tech + teil + zeit + verb + "\n".join(zeilen) + "\nC\nED\n"


TMP = Path(tempfile.mkdtemp())
(TMP / "TEST_QR.lst").write_text(lst(), encoding="cp1252")
RING = 4 * (B - 2 * RE) + 2 * math.pi * RE
BOHRUNG = 2 * math.pi * R_BOHR


@fall("S1 Schneidweg: Konturen, Anfahrt getrennt, Trennschnitte, halbe Fuge, Bohrung an der Teilkante")
def _s1():
    (p,) = lst_bahn.lesen(TMP / "TEST_QR.lst")
    assert p["teile_im_programm"] == 1 and p["laenge"] == L and not p["querschnitt"].rund, p
    arten = [k["art"] for k in p["konturen"]]
    assert arten == [lst_bahn.TRENN, lst_bahn.KONTUR, lst_bahn.TRENN, lst_bahn.REST], arten
    assert p["einstiche"] == 4 and abs(p["halbspalt"] - HALB) < 1e-6, (p["einstiche"], p["halbspalt"])
    loch = p["konturen"][1]
    assert not loch["offen"] and abs(loch["laenge"] - BOHRUNG) < 0.01, loch["laenge"]     # Ø10 an der Teilkante
    assert all(abs(math.hypot(q[0] - 100, q[1]) - R_BOHR) < 0.01 for q in loch["punkte"])
    assert abs(p["anfahrt"] - (R_BOHR - HALB)) < 0.01 and abs(p["restzerteilung"] - 20) < 0.01, p
    assert abs(p["schnittlaenge"] - (2 * RING + BOHRUNG)) < 0.1, p["schnittlaenge"]
    assert p["abweichung"] < 0.01, p["abweichung"]        # alle Punkte auf der Rohroberfläche


@fall("S2 LST-Werte: Schneidweg am Material, Maschinenweg, Laser-an-Zeit, Konturen je Klasse; unplausibel = wie bisher")
def _s2():
    (t,) = tp.lst_lesen(TMP / "TEST_QR.lst")
    assert t["profilform"] == "Quadratrohr" and t["a"] == B and t["laenge"] == L, t
    assert abs(t["schneidweg"] - round(2 * RING + BOHRUNG, 1)) < 0.15 and t["maschinenweg"] == 420.0, t
    assert t["laser_an_s"] == 4.5 and t["verfahren_s"] == 2.0 and t["zeit_s"] == 6.5, t
    assert [a for a, _g, _lg in t["enden"]] == ["A", "E"] and len(t["innen"]) == 1, (t["enden"], t["innen"])
    assert abs(t["innen"][0][0] - 2 * R_BOHR) < 0.05 and abs(t["innen"][0][1] - BOHRUNG) < 0.05, t["innen"]
    text = rechnen.konturen_text(t["innen"], t["enden"])
    assert text.startswith("A:") and "; E:" in text and text.endswith("x31,4"), text
    (k,) = tp.lst_lesen(text=lst(weg=5000.0), name="X.lst")           # NC passt nicht zum Maschinenweg
    assert k["schneidweg"] == 5000.0 and not k.get("schnittlaenge_material"), k
    (k,) = tp.lst_lesen(text=lst(nc=False, verbrauch=False), name="Y.lst")
    assert k["laser_an_s"] is None and k["schneidweg"] == 420.0, k


@fall("S3 3D: Rohr aus dem Schneidweg exakt wie die STEP (Volumen, Profil, Länge, Bohrung Ø10)")
def _s3():
    from step_geometrie import analysiere_datei
    import step_blm
    import step_lst
    koerper, info = step_lst.lies_lst_info(TMP / "TEST_QR.lst")
    flaeche = B * B - (4 - math.pi) * RE ** 2 - ((B - 2 * WAND) ** 2 - (4 - math.pi) * (RE - WAND) ** 2)
    vs = flaeche * L - math.pi * R_BOHR ** 2 * WAND             # Rohr exakt minus Bohrung Ø10 durch die obere Wand
    v = step_blm.volumen(koerper[0][1])
    assert abs(v - vs) < 1e-4 * vs, (v, vs)
    assert any("TRUMPF-LST" in m and "Maschinenweg laut LST 420" in m for m in info["meldungen"]), info["meldungen"]
    (t,) = analysiere_datei(TMP / "TEST_QR.lst")
    assert t.profilform == "Quadratrohr" and abs(t.abm_a - B) < 0.05 and abs(t.laenge - L) < 0.05, t
    assert dict(t.bohrungen) == {10.0: 1}, t.bohrungen


@fall("S4 Kalkulation: Laser-an-Zeit als reine Laserzeit, Einstiche enthalten/eigen, ganz/nein, Hand geht vor")
def _s4():
    (t,) = tp.lst_lesen(TMP / "TEST_QR.lst")
    p = dict(step_merkmale=json.dumps({"programm": {"laser_an_s": t["laser_an_s"], "verfahren_s": t["verfahren_s"]}}))
    assert rechnen.programm_laserzeit(p, {}) == (4.5, True, 2.0)               # Vorgabe: Einstiche enthalten
    assert rechnen.programm_laserzeit(p, {"programmzeit_einstiche": "eigen"}) == (4.5, False, 2.0)
    for w in ("ganz", "nein"):
        assert rechnen.programm_laserzeit(p, {"trumpf_zeit": w}) is None, w
    assert rechnen.programm_laserzeit(dict(p, zeit_manuell=9.0), {}) is None
    assert rechnen.programm_laserzeit({}, {}) is None
    g = dict(step_merkmale=json.dumps({"programm": {"laser_an_s": 4.5, "verfahren_s": 2.0, "gemessen_s": 7.8}}))
    s_, _e, v_ = rechnen.programm_laserzeit(g, {})                              # gemessen gilt, Anteile wie im Programm
    assert abs(s_ - 5.4) < 1e-9 and abs(v_ - 2.4) < 1e-9, (s_, v_)
    anteile = dict(gross=3.0, klein=1.0, einstiche=0.8, ecken=0.0, anfahren=1.5, drehen=0.5, neben=1.5, entnahme=2.0)
    neu = rechnen.laser_aus_programm(anteile, 4.5, True, 2.0)                  # alle Zeiten der LST übernommen
    assert abs(neu["gross"] - 4.5 * 0.75) < 1e-9 and abs(neu["klein"] - 4.5 * 0.25) < 1e-9 and neu["einstiche"] == 0
    assert abs(neu["anfahren"] - 1.5) < 1e-9 and abs(neu["drehen"] - 0.5) < 1e-9, neu   # Verfahren aus der LST
    assert (neu["neben"], neu["entnahme"]) == (1.5, 2.0), neu                  # nur das Fehlende berechnet
    neu = rechnen.laser_aus_programm(anteile, 4.5, True, 4.0)
    assert abs(neu["anfahren"] - 3.0) < 1e-9 and abs(neu["drehen"] - 1.0) < 1e-9, neu
    neu = rechnen.laser_aus_programm(anteile, 4.5, False)                      # Einstiche eigen, Verfahren berechnet
    assert neu["einstiche"] == 0.8 and abs(neu["gross"] + neu["klein"] - 3.7) < 1e-9 and neu["anfahren"] == 1.5, neu
    assert rechnen.laser_aus_programm(dict(bewegen=1.0), 2.0, True)["gross"] == 2.0
    assert rechnen.klassen_text(dict(gross_n=1, gross_mm=300.5, klein_n=2, klein_mm=62.8)) == \
        "groß 1 × 300,5 mm, klein 2 × 62,8 mm"
    assert rechnen.klassen_text({}) == "keine Innenkonturen"


@fall("S5 BPF: Geschwindigkeitsstufe je Kontur im Bericht")
def _s5():
    import step_blm
    teil = dict(querschnitt=dict(name="RE", a=60.0, b=40.0, wand=3.0), maschine="LT8", laenge=400.0, werkstoff="",
                volumen=0.0, konturen=[dict(velo="3"), dict(velo="3"), dict(velo="1"), dict()])
    t = step_blm._bpf_text(teil, None)
    assert "Geschwindigkeitsstufe 1 (1×), 3 (2×)" in t, t


print("Alle Tests bestanden." if not fehler else f"{fehler} Fehler")
sys.exit(1 if fehler else 0)
