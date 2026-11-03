"""Testreihe Kantteile U/C/L (Patrick 03.11.2026: „U-, C-, L-Kantteile Erkennung deutlich verbessern, dass es hier nicht
zu Missverständnissen kommt“, Bilder typischer Kantteile; Freigabe „Alle Empfehlungen“ 17:22). Alle Teile hier gebaut:
- K1 Standard-Kantprofile (U-Stahl, Kant-C) bleiben Profil, auch mit Löchern, Ausklinkung, schräg im Raum oder
  scharfkantig gezeichnet; das Walz-L bleibt L 50x50x5. Winkel (Patrick 03.11.2026 19:01): scharfkantig oder außen
  scharf/innen Radius = L-Profil, mit Biegeradius außen = innen + Dicke immer Kantteil (auch in Kant-L-Maßen, R1,5/R6).
- K2 andere Kantteile werden Blech gekantet: L ohne Standardmaß, U mit ungleichen Schenkeln, flaches U, C ohne
  Standardmaß, U mit krummem Maß.
- K3 offen gezeichnetes Rohr nur, wenn das Rohr genau die Außenmaße hat; C mit Lippen nur bis 20 mm Schlitz; das Rohr
  bleibt als Auswahl (Spalte geschlossen).
- K4 Kantteile nach Patricks Bildern (Hut, Z, Dachwinkel, Wanne, C mit Sicke, dickes S, Saum, mehrachsige Halter und
  Chassis) sind Blech gekantet; die Auswahl „Profil“ zeigt die echte Form (offenes Sonderprofil statt L, nie Träger).
- K5 Abwicklung: Hutprofil in 25 Lagen im Raum gleicher Zuschnitt (vorher 113–117 statt 172,7 mm).
- K6 Programm: Grund in der Hinweisspalte (step.kant_grund), Rohr in der Spalte Art wählbar; scharfkantiger Winkel
  bleibt L-Profil; die 3D-Ansicht zeigt die gewählte Art (Kantteil blau, Profil mit Anfangs-/Endschnitt).

Aufruf: python tests/test_kantteile_vielfalt.py
"""
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
import erzeuge_testteile as et  # noqa: E402
from formen_baukasten import lage, ohne, plus, quader, schreibe, zyl  # noqa: E402
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


def L(a, b, t, R=None, lg=500):
    R = t if R is None else R
    return et.profil([(0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b)], lg, {(0, 0): R + t, (t, t): R} if R else None)


def U(h, b, t, R=None, lg=500, b2=None):
    R = t if R is None else R
    b2 = b if b2 is None else b2
    p = [(0, 0), (h, 0), (h, b2), (h - t, b2), (h - t, t), (t, t), (t, b), (0, b)]
    return et.profil(p, lg, {(0, 0): R + t, (h, 0): R + t, (t, t): R, (h - t, t): R} if R else None)


def C(h, b, c, t, R=None, lg=500):
    R = t if R is None else R
    p = [(0, 0), (b, 0), (b, c), (b - t, c), (b - t, t), (t, t), (t, h - t), (b - t, h - t), (b - t, h - c), (b, h - c),
         (b, h), (0, h)]
    r = {(0, 0): R + t, (b, 0): R + t, (b, h): R + t, (0, h): R + t, (t, t): R, (b - t, t): R, (b - t, h - t): R,
         (t, h - t): R}
    return et.profil(p, lg, r if R else None)


def kant(mitte, t, R=None, lg=500):
    """Blech der Dicke t um die Mittellinie (offener Zug); Biegeradius innen R (Vorgabe t), außen R + t."""
    R = t if R is None else R
    def off(s):
        pts = []
        n = len(mitte)
        for i in range(n):
            if i == 0 or i == n - 1:
                a, b = (mitte[0], mitte[1]) if i == 0 else (mitte[-2], mitte[-1])
                dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy)
                nx, ny = -dy / L, dx / L
                pts.append((mitte[i][0] + s * nx * t / 2, mitte[i][1] + s * ny * t / 2))
            else:
                a, b, c = mitte[i - 1], mitte[i], mitte[i + 1]
                d1 = ((b[0] - a[0]), (b[1] - a[1])); l1 = math.hypot(*d1); d1 = (d1[0] / l1, d1[1] / l1)
                d2 = ((c[0] - b[0]), (c[1] - b[1])); l2 = math.hypot(*d2); d2 = (d2[0] / l2, d2[1] / l2)
                n1, n2 = (-d1[1], d1[0]), (-d2[1], d2[0])
                bx, by = n1[0] + n2[0], n1[1] + n2[1]; bl = math.hypot(bx, by)
                cosh = (n1[0] * bx + n1[1] * by) / bl
                f = s * t / 2 / cosh
                pts.append((round(b[0] + bx / bl * f, 6), round(b[1] + by / bl * f, 6)))
        return pts
    links, rechts = off(1), off(-1)
    radien = {}
    for i in range(1, len(mitte) - 1):
        a, b, c = mitte[i - 1], mitte[i], mitte[i + 1]
        kreuz = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if R > 0:
            radien[links[i]] = R if kreuz > 0 else R + t
            radien[rechts[i]] = R + t if kreuz > 0 else R
    poly = links + list(reversed(rechts))
    return et.profil(poly, lg, radien or None)


HUT = [(-50, 0), (-30, 0), (-30, 40), (30, 40), (30, 0), (50, 0)]
WALZ_L = et.profil([(0, 0), (50, 0), (50, 5), (5, 5), (5, 50), (0, 50)], 500, {(5, 5): 5})
PROFIL = {      # bleibt Profil: Name -> (Körper, Form, Normprofil)
    "L04_L_scharf": (L(50, 50, 3, 0), "L-Profil", ""),
    "L05_Walz_L50x50x5": (WALZ_L, "L-Profil", "L 50x50x5"),
    "L13_L_innen_R": (et.profil([(0, 0), (60, 0), (60, 4), (4, 4), (4, 40), (0, 40)], 500, {(4, 4): 4}), "L-Profil", ""),
    "L16_L_scharf_schraeg": (lage(L(40, 40, 3, 0)), "L-Profil", ""),
    "U01_UStahl_80x50x4": (U(80, 50, 4), "U-Profil", "U-Stahl 80x50x4"),
    "U05_UStahl_schraeg": (lage(U(40, 20, 3)), "U-Profil", "U-Stahl 40x20x3"),
    "U06_UStahl_Bohr_Ausklinkung": (ohne(U(80, 50, 4), zyl(5, 10, 250, 40, -2, (0, 1, 0)), quader(20, 30, 30, -1, 25, -1)),
                                    "U-Profil", "U-Stahl 80x50x4"),
    "U09_UStahl_scharf": (U(80, 50, 4, 0), "U-Profil", "U-Stahl 80x50x4"),
    "C01_KantC_100x50x20x3": (C(100, 50, 20, 3), "C-Profil", "Kant-C 100x50x20x3"),
    "C05_KantC_schraeg": (lage(C(100, 50, 20, 3)), "C-Profil", "Kant-C 100x50x20x3"),
    "C07_KantC_Bohrungen": (ohne(C(100, 50, 20, 3), zyl(5, 10, 250, 25, 47, (0, 1, 0))), "C-Profil", "Kant-C 100x50x20x3"),
}
t = 2.0
M1 = ohne(plus(quader(150, 60, t), quader(150, t, 80, 0, 60 - t, 0), quader(t, 60, 80, -t, 0, 0)),
          quader(t + 1, 10, 3, -t - 0.5, 20, 30), quader(t + 1, 10, 3, -t - 0.5, 20, 55))
M2 = ohne(plus(quader(60, 40, t), quader(60, t, 70), quader(60, t, 70, 0, 40 - t, 0), quader(60, 20, t, 0, -20, 70 - t),
               quader(60, 20, t, 0, 40, 70 - t)), zyl(4, 10, 30, 30, -5, (0, 1, 0)), zyl(4, 10, 30, 30, 35, (0, 1, 0)))
M5 = plus(quader(200, 100, t), quader(200, t, 40), quader(200, t, 40, 0, 100 - t, 0),
          quader(t, 95, 20, -t, t + 0.5, 0), quader(t, 95, 20, 200, t + 0.5, 0))
KANT = {        # Blech gekantet: Name -> (Körper, Form der Auswahl „Profil“ oder None)
    "K03_L_70x45x3": (L(70, 45, 3), "L-Profil"),
    "L01_KantL_50x50x3": (L(50, 50, 3), "L-Profil"),        # Winkel mit Biegeradius: immer Kantteil
    "L02_KantL_60x40x3": (L(60, 40, 3), "L-Profil"),
    "L06_KantL_Bohrungen": (ohne(L(50, 50, 3), zyl(4.5, 10, 100, 25, -2, (0, 1, 0)),
                                 zyl(4.5, 10, 400, 25, -2, (0, 1, 0))), None),
    "L07_KantL_schraeg": (lage(L(40, 40, 2)), "L-Profil"),
    "L08_KantL_Ausklinkung": (ohne(L(50, 50, 3), quader(30, 10, 20, 20, -1, -1)), None),
    "L09_KantL_R1,5": (L(50, 50, 3, 1.5), "L-Profil"),
    "L10_KantL_R6": (L(50, 50, 3, 6), "L-Profil"),
    "L12_KantL_kurz60": (L(50, 50, 3, lg=60), "L-Profil"),
    "K04_U_85x40,8x3": (U(85, 40.8, 3), "U-Profil"),
    "K07_U_ungleich": (U(80, 50, 3, b2=30), None),
    "K08_U_flach_200x20": (U(200, 20, 3), None),
    "K10_C_110x45x18x3": (C(110, 45, 18, 3), None),
    "B01_Hutprofil": (kant(HUT, 2), "offenes Sonderprofil"),
    "B02_Hut_Loecher": (ohne(kant([(-60, 0), (-40, 0), (-40, 40), (40, 40), (40, 0), (60, 0)], 2, lg=600),
                             zyl(10, 10, 150, 0, 35, (0, 1, 0)), zyl(3, 10, 300, -50, -5, (0, 1, 0))), None),
    "B03_Z_30-60-30x3": (kant([(0, 0), (30, 0), (30, 60), (60, 60)], 3), "offenes Sonderprofil"),
    "B04_Dachwinkel_120": (kant([(-50, -29), (0, 0), (50, -29)], 2), None),
    "B05_Wanne_300x15": (kant([(0, 15), (0, 0), (300, 0), (300, 15)], 2), None),
    "B06_C_mit_Sicke": (kant([(40, 0), (0, 0), (0, 30), (8, 40), (0, 50), (0, 80), (40, 80)], 2), "offenes Sonderprofil"),
    "B07_S_dick_t10": (kant([(0, 0), (50, 0), (50, 60), (100, 60)], 10, 15, lg=150), None),
    "B08_U_Saum": (kant([(0, 0), (0, 50), (80, 50), (80, 0), (70, 0)], 2), "offenes Sonderprofil"),
    "B10_Hut_schraeg": (lage(kant(HUT, 2)), None),
    "M1_Winkel_zwei_Achsen": (M1, None),
    "M2_U_Halter_Ohren": (M2, None),
    "M5_Chassis_Laschen": (M5, None),
}
OFFEN = {       # offen gezeichnet: Name -> (Körper, Rohr gilt?)
    "O1_U_60x40x3_R": (U(60, 40, 3), False),            # Rohr wäre RE 60x50: Kantteil
    "O2_C_120x60x20x3": (C(120, 60, 20, 3), False),      # Schlitz 80 mm: Kantteil
}
TMP = Path(tempfile.mkdtemp())
LAGEN = {f"H_{n}": lage(kant(HUT, 2), ax, gr, (0, 0, 0)) for n, ax, gr in
         (("x37", (1, 0, 0), 37), ("xz37", (1, 0, 1), 37), ("xz-37", (1, 0, 1), -37), ("yz37", (0, 1, 1), 37),
          ("yz-37", (0, 1, 1), -37), ("xy90", (1, 1, 0), 90))}
schreibe({**{n: v[0] for n, v in PROFIL.items()}, **{n: v[0] for n, v in KANT.items()},
          **{n: v[0] for n, v in OFFEN.items()}, **LAGEN}, TMP)
M = {}


def m(name):
    if name not in M:
        (M[name],) = analysiere_datei(TMP / f"{name}.step")
    return M[name]


@fall("K1 Standard-Kantprofile bleiben Profil (Löcher, Ausklinkung, schräg, scharfkantig), Walz-L, Winkel scharf = L")
def _():
    falsch = {n: (m(n).profilform, m(n).normprofil) for n, (_, f, norm) in PROFIL.items()
              if (m(n).profilform, m(n).normprofil) != (f, norm)}
    assert not falsch, falsch


@fall("K2/K4 andere Kantteile und Patricks Beispiele sind Blech gekantet, Auswahl mit echter Form (nie Träger)")
def _():
    falsch = {n: m(n).profilform for n in KANT if m(n).profilform != "Blech gekantet"}
    assert not falsch, falsch
    for n, (_, form) in KANT.items():
        alt = m(n).alternative
        assert alt is None or alt.profilform not in ("I-/H-Träger", "T-Profil"), (n, alt.profilform)
        if form:
            assert alt is not None and alt.profilform == form, (n, alt and alt.profilform)
    assert m("M1_Winkel_zwei_Achsen").blech["abwicklung"]["mehrachsig"]
    assert m("M5_Chassis_Laschen").blech["abwicklung"]["kantungen"] == 4


@fall("K3 offen gezeichnetes Rohr nur mit den Außenmaßen des Teils, C mit Lippen nur bis 20 mm Schlitz")
def _():
    for n, (_, rohr) in OFFEN.items():
        x = m(n)
        assert (x.profilform != "Blech gekantet") == rohr, (n, x.profilform)
        assert x.geschlossen is not None, n                     # das Rohr bleibt als Auswahl
        assert any("Offenes Rohr als Auswahl" in h for h in x.hinweise), x.hinweise
    import step_geometrie as g
    assert "größer als das Teil" in g.rohr_grund(m("O1_U_60x40x3_R").alternative)
    assert "Schlitz über 20 mm" in g.rohr_grund(m("O2_C_120x60x20x3").alternative)


@fall("K5 Abwicklung: Hutprofil in jeder Lage im Raum gleicher Zuschnitt 500 × 172,7 mm")
def _():
    soll = m("B01_Hutprofil").blech["abwicklung"]
    assert abs(soll["breite"] - 172.71) < 0.05, soll["breite"]
    for n in ("B10_Hut_schraeg", *LAGEN):
        a = m(n).blech["abwicklung"]
        assert abs(a["breite"] - soll["breite"]) < 0.05 and abs(a["laenge"] - 500) < 0.05, (n, a["laenge"], a["breite"])
        assert [s["laenge"] for s in a["schenkel"]] == [s["laenge"] for s in soll["schenkel"]], (n, a["schenkel"])


@fall("K6 Programm: Grund in der Hinweisspalte, Rohr in der Spalte Art wählbar")
def _():
    import contextlib
    import io
    import step_messen
    from PySide6.QtWidgets import QApplication
    from rohrlaser import step
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.step_dialog import StepPruefDialog
    app = QApplication.instance() or QApplication([])
    aus, js = TMP / "k.txt", TMP / "k.json"
    namen = ("L01_KantL_50x50x3", "K03_L_70x45x3", "O1_U_60x40x3_R", "L04_L_scharf")
    netze = TMP / "netze"
    netze.mkdir(exist_ok=True)
    with contextlib.redirect_stdout(io.StringIO()):
        step_messen.main(["--ausgabe", str(aus), "--json", str(js), "--netze", str(netze)]
                         + [str(TMP / f"{n}.step") for n in namen])
    mw = step.lade_netze(step.lies_messwerte(aus), netze)
    assert step.kant_grund(mw[0]).startswith("Winkel mit Biegeradius (außen = innen + Dicke): immer Kantteil"), \
        step.kant_grund(mw[0])
    assert "immer Kantteil (L-Profil als Auswahl)" in step.kant_grund(mw[1]), step.kant_grund(mw[1])
    assert step.kantteile_vorbelegen(mw, {}) == 0 and mw[3]["profilform"] == "L-Profil"    # Winkel scharf: L
    assert step.kant_grund(mw[3]).startswith("Winkel scharfkantig: L-Profil"), step.kant_grund(mw[3])
    from rohrlaser.ansicht3d import entpacken

    def arten(m):
        n = step.netz_der_art(m)
        return set((entpacken(n) if isinstance(n, bytes) else n)["t"])
    for x in (mw[0], mw[3]):            # 3D zeigt die Art: Kantteil blau, Profil mit Anfangs-/Endschnitt
        ist = arten(x)
        assert ("KB" in ist and not ist & {"A", "EA", "EB", "N"}) if x["profilform"] == "Blech gekantet" else \
            {"A", "EA", "EB"} <= ist, (x["datei"], x["profilform"], ist)
        assert step.art_wechseln(x)
        ist = arten(x)
        assert ("KB" in ist) == (x["profilform"] == "Blech gekantet") and ("EA" in ist) != ("KB" in ist), \
            (x["datei"], x["profilform"], ist)
        assert step.art_wechseln(x)
    assert "Rohr als Auswahl" in step.kant_grund(mw[2]) and step.geschlossen(mw[2]), step.kant_grund(mw[2])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "r.db")
        d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste())
        z = next(z for z in d.zeilen if z.datei.startswith("O1"))
        art = d.baum.itemWidget(z.it, d.SP_ART)
        assert art.currentText().startswith("Kantteil"), art.currentText()
        daten = [art.itemData(i) for i in range(art.count())]
        assert "zu" in daten and "Ringe an den Enden" in art.itemText(daten.index("zu")), \
            [art.itemText(i) for i in range(art.count())]
        assert "immer Kantteil" in next(x for x in d.zeilen if x.datei.startswith("L01")).it.text(d.SP_HINWEIS)
        art.setCurrentIndex(daten.index("zu"))                 # aus dem Rohr schneiden
        z = next(z for z in d.zeilen if z.datei.startswith("O1"))
        assert d.baum.itemWidget(z.it, d.SP_ART).currentText().startswith("Rechteckrohr"), \
            d.baum.itemWidget(z.it, d.SP_ART).currentText()
        d.close()
        app.processEvents()
        db.con.close()


if fehler:
    print(f"{fehler} Fall/Fälle rot")
    sys.exit(1)
print("Alle Kantteil-Testreihen bestanden.")
