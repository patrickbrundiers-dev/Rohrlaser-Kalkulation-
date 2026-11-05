"""IGES-Import (Patrick 05.11.2026 „Iges import einbauen“, Freigabe „Ja, in Entwurf 0.9.263 mit rein“):
- I1 Kantteil als IGES (Flächenmodell, Biegungen als Drehflächen): genäht, Biegeflächen als Zylinder, gleiche Messung
  wie die STEP-Datei (Blech gekantet, Kantungen, Zuschnitt, Bohrungen).
- I2 Rechteckrohr mit Bohrung als IGES: gleiches Profil, gleiche Länge und Konturen wie STEP.
- I3 Kantteil mit runder Prägung (eingeprägte Tasche wie am Blech-Halter): Kantteil statt „3 statt 2 Blechhäute“,
  Öffnung der Prägung im Zuschnitt geschlossen (keine Innenkontur), Hinweis „Prägung“.
- I4 Dateiauswahl: Ordner, Ablegen, Anfragen und Dialoge nehmen .igs/.iges wie .step/.stp.
- I5 Einheit aus dem IGES-Kopf, kaputte IGES-Datei: klare Meldung.
- I6 IGES mit Volumenkörpern (Hubwagen aus SolidWorks: Zylinder als Drehflächen): Flächen umgewandelt, gleiche
  Messung wie STEP.

Aufruf: python tests/test_iges_import.py
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
from formen_baukasten import kant, ohne, plus, praegung, quader, schreibe, schreibe_iges, verschiebe, zyl  # noqa: E402
from step_geometrie import analysiere_datei, lies_step_info  # noqa: E402

fehler = 0
X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)


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


def nah(a, b, tol=0.05):
    return abs(a - b) <= tol


C_HALTER = ohne(kant([(60, 0), (0, 0), (0, 80), (60, 80)], 2, lg=70), zyl(5, 10, 35, -5, 40, X),
                zyl(4, 10, 20, 30, -5, Y))
ROHR = ohne(ohne(quader(60, 40, 400), quader(54, 34, 402, 3, 3, -1)), zyl(5, 10, 200, 20, -5, Y))
L_ = kant([(0, 60), (0, 0), (120, 0)], 2, lg=100)
# Prägung Ø50 in der Mitte des langen Schenkels (Ebene y = 0, Tasche 4 mm nach −y)
DELLE = verschiebe(praegung([(0, -4), (8, -4), (14, 0), (25, 0)], 2, 3), 60, 0, 50)
PRAEG = plus(ohne(L_, zyl(25, 20, 50, 60, -10, Y)), DELLE)
TMP = Path(tempfile.mkdtemp())
schreibe({"C_Halter": C_HALTER, "Rohr": ROHR, "Praeg": PRAEG}, TMP)
for n, f in (("C_Halter", C_HALTER), ("Rohr", ROHR), ("Praeg", PRAEG)):
    schreibe_iges(f, TMP / f"{n}.igs")
schreibe_iges(C_HALTER, TMP / "C_Halter_koerper.igs", koerper=True)
M = {}


def m(name):
    if name not in M:
        (M[name],) = analysiere_datei(TMP / name)
    return M[name]


@fall("I1 Kantteil als IGES: genäht, Biegungen als Zylinder, Messung wie STEP")
def _():
    a, b = m("C_Halter.step"), m("C_Halter.igs")
    assert b.profilform == a.profilform == "Blech gekantet" and b.koerperart == "aus Flächenmodell genäht", \
        (a.profilform, b.profilform, b.koerperart)
    wa, wb = a.blech["abwicklung"], b.blech["abwicklung"]
    assert wb["kantungen"] == wa["kantungen"] == 2, (wa["kantungen"], wb["kantungen"])
    assert nah(wa["laenge"], wb["laenge"], 0.05) and nah(wa["breite"], wb["breite"], 0.05), (wa, wb)
    assert b.blech["bohrungen"] == a.blech["bohrungen"] == {8.0: 1, 10.0: 1}, (a.blech["bohrungen"], b.blech["bohrungen"])
    assert nah(b.blech["dicke"], 2, 0.01)


@fall("I2 Rechteckrohr als IGES: gleiches Profil, gleiche Länge und Konturen")
def _():
    a, b = m("Rohr.step"), m("Rohr.igs")
    assert b.profilform == a.profilform == "Rechteckrohr", (a.profilform, b.profilform)
    assert nah(b.abm_a, a.abm_a) and nah(b.abm_b, a.abm_b) and nah(b.wandstaerke, a.wandstaerke), \
        ((a.abm_a, a.abm_b, a.wandstaerke), (b.abm_a, b.abm_b, b.wandstaerke))
    assert nah(b.laenge, a.laenge, 0.05) and b.konturen == a.konturen, ((a.laenge, a.konturen), (b.laenge, b.konturen))


@fall("I3 Kantteil mit Prägung: Kantteil, Öffnung im Zuschnitt geschlossen, Hinweis")
def _():
    for n in ("Praeg.step", "Praeg.igs"):
        t = m(n)
        assert t.profilform == "Blech gekantet", (n, t.profilform, t.hinweise)
        w = t.blech["abwicklung"]
        assert w.get("praegungen") == 1 and w["kantungen"] == 1, (n, w.get("praegungen"), w.get("fehler"))
        assert t.blech["innen"] == 0, (n, t.blech["innen"], t.blech.get("konturen_lage"))
        assert any("Prägung" in h for h in t.hinweise), (n, t.hinweise)
        ba = math.pi / 2 * (2 + 0.33 * 2)
        assert nah(max(w["laenge"], w["breite"]), (60 - 1 - 2) + (120 - 1 - 2) + ba, 0.2), (n, w["laenge"], w["breite"])


@fall("I4 Dateiauswahl: Ordner, Ablegen, Anfragen und Dialoge nehmen IGES")
def _():
    from rohrlaser import anfragen, step
    d = TMP / "ordner"
    (d / "unter").mkdir(parents=True)
    for n in ("a.IGS", "unter/b.iges", "c.stp", "d.txt"):
        (d / n).write_text("x")
    assert [p.name for p in step.step_dateien([d])] == ["a.IGS", "c.stp", "b.iges"], step.step_dateien([d])
    assert step.step_kandidaten([d / "a.IGS"]) and not step.step_kandidaten([d / "d.txt"])
    assert {".igs", ".iges"} <= anfragen.STEP and "*.igs" in step.CAD_FILTER and "*.IGES" in step.CAD_FILTER
    quelle = (HIER.parent / "programm" / "rohrlaser" / "angebot_fenster.py").read_text(encoding="utf-8")
    assert "STEP-Dateien (*.step *.stp *.STEP *.STP)" not in quelle


@fall("I5 Einheit aus dem IGES-Kopf, kaputte Datei mit klarer Meldung")
def _():
    _, info = lies_step_info(TMP / "Rohr.igs")
    assert info["einheit"] == "mm" and not info["baugruppe"], info
    kaputt = TMP / "kaputt.igs"
    kaputt.write_text("kein IGES\n")
    try:
        lies_step_info(kaputt)
        raise AssertionError("keine Fehlermeldung")
    except ValueError as e:
        assert "IGES-Datei nicht lesbar" in str(e), e


@fall("I6 IGES mit Volumenkörpern: Drehflächen als Zylinder, Messung wie STEP")
def _():
    from collections import Counter
    from step_geometrie import BRepAdaptor_Surface, TopAbs_FACE, TopoDS, _liste
    k, _ = lies_step_info(TMP / "C_Halter_koerper.igs")
    assert [a for a, _ in k] == ["Volumenkörper"], [a for a, _ in k]
    arten = Counter(str(BRepAdaptor_Surface(TopoDS.Face(f)).GetType()).split("_")[-1] for f in _liste(k[0][1], TopAbs_FACE))
    assert "SurfaceOfRevolution" not in arten and arten["Cylinder"] >= 4, arten
    a, b = m("C_Halter.step"), m("C_Halter_koerper.igs")
    assert b.profilform == a.profilform and b.blech["bohrungen"] == a.blech["bohrungen"], (b.profilform, b.blech)
    wa, wb = a.blech["abwicklung"], b.blech["abwicklung"]
    assert nah(wa["laenge"], wb["laenge"]) and nah(wa["breite"], wb["breite"]) and wa["kantungen"] == wb["kantungen"]


if fehler:
    print(f"{fehler} Fall/Fälle rot")
    sys.exit(1)
print("Alle IGES-Import-Tests bestanden.")
