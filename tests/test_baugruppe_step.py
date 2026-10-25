"""Baugruppe und Satz als STEP-Baugruppe (Plan 3D-Editor 3E-14, Patrick 25.10.2026 „Alle a“):
- G1 Schweißbaugruppe mit Rohren und Blech (S03): jede Position einmal definiert, so oft eingesetzt wie in der
  Datei, Rohre aus den Eingaben in der Einbaulage, Blech am Netz der STEP-Messung ausgerichtet; Hüllmaße wie die
  Original-Datei, die eigene Messung findet alle Körper wieder
- G2 Rohr mit zwei Blechen (B14): Volumen der ganzen Baugruppe wie das Original (Bleche richtig ausgerichtet)
- G3 Unterbaugruppe (S01): STEP-Baugruppe mit der Unterbaugruppe „Rahmenseite“ und ihren Teilen
- G4 Teil ohne Lage (von Hand angelegt): neben die Baugruppe gelegt, mit Hinweis; Teil nur als Netz: facettiert
- G5 Fenster „Satz in 3D“: STEP speichern wie im Editor der Baugruppe
- G6 Bleche exakt an ihrer Stelle (Patrick 25.10.2026, Satz „Bauteil 1“: quadratische Wand-/Fußplatten verdreht,
  Flachstahl 40 mm versetzt): quadratische Platten mit symmetrischen Löchern und Flachstahl in vielen Lagen, auch
  um 30° gedreht, liegen nach dem Ausrichten genau auf dem Netz; Namen mit Umlauten bleiben lesbar

Aufruf: python tests/test_baugruppe_step.py
"""
import os
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path[:0] = [str(PROGRAMM), str(PROGRAMM / "step_messung")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if find_spec("OCP") is None:
    print("OCP fehlt: übersprungen")
    sys.exit(0)
import step_messen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import baugruppe_step, step  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.satz3d import Satz3dDialog  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


def einlesen(datei):
    """STEP wie im Programm übernehmen -> (Datenbank, Positionen, Netze, Profile)."""
    t = tmp / datei.stem
    t.mkdir()
    step_messen.main(["--ausgabe", str(t / "m.txt"), "--json", str(t / "m.json"), "--netze", str(t / "netze"),
                      str(datei)])
    mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(t / "m.txt"), t / "netze"), t / "m.json")
    for x in mw:
        x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True)
    db = Datenbank(t / "b.db")
    k = db.kontext()
    erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                           zukauf_liste=[])
    db.profile_anlegen(erg["profile"])
    a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
    for p in erg["positionen"]:
        netz = p.pop("_netz", None)
        p.pop("_zukauf", None)
        pid = db.position_neu(a, p)
        if netz:
            db.netz_speichern(pid, netz)
    return db, db.positionen(a), db.netze(a), db.kontext().profile


def editor(datei, ziel):
    db, positionen, netze, profile = einlesen(datei)
    bgp = next(p for p in positionen if p.get("art") == BAUGRUPPE)
    d = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0}, db=db, netze=netze,
                        profile=profile)
    d.stumm = True
    assert d.step_speichern(str(ziel)) == str(ziel) and ziel.is_file(), d.step_ergebnis
    return d, positionen, netze, profile


def masse(box):
    return sorted(round(box[i + 3] - box[i], 1) for i in range(3))


def hauptmasse(datei):
    """Hüllmaße [mm] aller Körper einer STEP-Datei (aus OpenCascade, ohne Messung)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.STEPControl import STEPControl_Reader
    r = STEPControl_Reader()
    r.ReadFile(str(datei))
    r.TransferRoots()
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(r.OneShape(), box, False, False)
    a, b = box.CornerMin(), box.CornerMax()
    return masse([a.X(), a.Y(), a.Z(), b.X(), b.Y(), b.Z()])


# ------------------------------------------------------------------ G1 Rohre und Blech
s03 = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
d, positionen, netze, profile = editor(s03, tmp / "s03.step")
e = d.step_ergebnis
orig = analysiere_datei(s03)
assert e["ok"] and e["einsaetze"] == len(orig) == 6 and not e["hinweise"], e
assert len(e["teile"]) == 4 and all(t["gueltig"] and t["koerper"] == 1 for t in e["teile"])
assert masse(e["box"]) == hauptmasse(s03), (masse(e["box"]), hauptmasse(s03))
neu = analysiere_datei(tmp / "s03.step")
assert sorted(x.profilform for x in neu) == sorted(x.profilform for x in orig), [x.profilform for x in neu]
assert d.step_knopf().text() == "STEP speichern …"
ok("G1 Baugruppe S03: 4 Teile, 6 Körper in Einbaulage, Hüllmaße wie das Original, Messung findet alle wieder")

# ------------------------------------------------------------------ G2 Bleche ausgerichtet
b14 = HIER / "step_bleche" / "B14_Baugruppe_Rohr_2Bleche.step"
d2, *_ = editor(b14, tmp / "b14.step")
e2 = d2.step_ergebnis
v_orig = sum(x.volumen for x in analysiere_datei(b14))
assert e2["ok"] and e2["einsaetze"] == 3 and abs(e2["volumen"] - v_orig) < 1, (e2, v_orig)
assert masse(e2["box"]) == hauptmasse(b14), (e2["box"], hauptmasse(b14))
ok("G2 Rohr mit zwei Blechen: Bleche am Netz der Messung ausgerichtet, Volumen und Hüllmaße wie das Original")

# ------------------------------------------------------------------ G3 Unterbaugruppe
s01 = HIER / "step_struktur" / "S01_Gestell_verschachtelt.step"
d3, *_ = editor(s01, tmp / "s01.step")
text = (tmp / "s01.step").read_text(encoding="utf-8", errors="replace")
assert "Rahmenseite" in text and text.count("NEXT_ASSEMBLY_USAGE_OCCURRENCE") == 1 + d3.step_ergebnis["einsaetze"]
# 3 Rohrteile (8 Einsätze) und seit 0.9.121 der Rundstahl-Bolzen Ø8 als Zukaufteil (4 Einsätze)
assert d3.step_ergebnis["einsaetze"] == 12 and len(d3.step_ergebnis["teile"]) == 4, d3.step_ergebnis
ok("G3 Unterbaugruppe Rahmenseite als eigene Baugruppe in der STEP-Datei, gleiche Teile nur einmal definiert")

# ------------------------------------------------------------------ G4 ohne Lage, nur Netz
eintraege = d.step_eintraege()
ohne = dict(eintraege[0], pid="neu", netz={}, q=dict(eintraege[0]["q"], artikel="VON-HAND"))
roh = next(x for x in eintraege if x["rohr"])
nur_netz = dict(roh, pid="netz", rohr=None, q=dict(roh["q"], artikel="NETZ", technik=None))
plan, hinweise = baugruppe_step.bauplan("Test", eintraege + [ohne, nur_netz])
assert any("facettiert" in h for h in hinweise), hinweise
from rohrlaser import step_export  # noqa: E402
e4 = step_export.schreiben(plan, tmp / "g4.step", PROGRAMM)
n_netz = len(nur_netz["netz"].get("lagen") or [nur_netz["netz"]["lage"]])
assert e4["ok"] and e4["einsaetze"] == 6 + 1 + n_netz, e4
assert any("neben die Baugruppe" in h for h in e4["hinweise"]), e4["hinweise"]
assert e4["box"][3] > e["box"][3] + 49, (e4["box"], e["box"])          # 50 mm daneben
assert "STEP-Baugruppe gespeichert" in baugruppe_step.ergebnis_text(e4, tmp / "g4.step", hinweise)
ok("G4 Teil ohne Lage neben der Baugruppe (Hinweis), Teil nur als Netz der Messung facettiert (Hinweis)")

# ------------------------------------------------------------------ G5 Satz in 3D
satz = [dict(q, satz="S1") for q in positionen if q.get("art") != BAUGRUPPE]
s = Satz3dDialog(None, "S1", satz, profile=profile, netze=netze, daten={})
s.stumm = True
assert s.step_speichern(str(tmp / "satz.step")) and s.step_ergebnis["einsaetze"] == 6, s.step_ergebnis
assert s.step_name() == "Satz S1" and masse(s.step_ergebnis["box"]) == masse(e["box"])
for w in (d, d2, d3, s):
    w.close()
ok("G5 Satz in 3D: STEP speichern mit allen Teilen in Einbaulage")

# ------------------------------------------------------------------ G6 Bleche exakt ausrichten
import math  # noqa: E402

import step_schreiben as ss  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402


def platte(a, b, s_, loecher=()):
    k = BRepPrimAPI_MakeBox(a, b, s_).Shape()
    for x, y, r in loecher:
        k = BRepAlgoAPI_Cut(k, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, -1), gp_Dir(0, 0, 1)), r, s_ + 2).Shape()
                            ).Shape()
    return k


def drehung(achse, w):
    c, s_ = math.cos(math.radians(w)), math.sin(math.radians(w))
    if achse == "z":
        return [[c, -s_, 0], [s_, c, 0], [0, 0, 1]]
    if achse == "x":
        return [[1, 0, 0], [0, c, -s_], [0, s_, c]]
    return [[c, 0, s_], [0, 1, 0], [-s_, 0, c]]


def mal(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def netz_von(k, r, t_):
    """Netz wie aus der STEP-Messung: Dreiecke des Körpers (feiner vernetzt), gedreht und verschoben."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    kopie = BRepBuilderAPI_Copy(k).Shape()
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    BRepMesh_IncrementalMesh(kopie, 0.05, False, 0.1, True)
    p, t = [], []
    for d in ss._dreiecke(kopie):
        for q in d:
            t.append(len(p) // 3)
            p += [sum(r[z][j] * q[j] for j in range(3)) + t_[z] for z in range(3)]
    return p, t


wand = platte(220, 220, 15, [(40, 40, 9), (180, 40, 9), (40, 180, 9), (180, 180, 9)])
fl = platte(40, 662.5, 8)
lagen = [(drehung("x", 90), [-70, 15, 2590]), (mal(drehung("x", 90), drehung("z", 90)), [2850, 15, 2590]),
         (drehung("z", 180), [3050, 1550, 0]), (mal(drehung("z", 30), drehung("y", 90)), [500, 200, 100]),
         (drehung("z", 90), [2960, 55, 3653.6]), (drehung("z", -90), [2920, 717.5, 3653.6])]
schief = platte(200, 150, 10, [(30, 30, 6), (170, 30, 6), (60, 110, 15)])     # unsymmetrisch: Lage eindeutig
for k in (wand, fl, schief):
    box_k = ss._box([k])
    ecken = [(x, y, z) for x in (box_k[0], box_k[3]) for y in (box_k[1], box_k[4]) for z in (box_k[2], box_k[5])]
    for r, t_ in lagen:
        p, t = netz_von(k, r, t_)
        m, fehler = ss.ausrichten(k, p, t)
        soll = [[sum(r[z][j] * q[j] for j in range(3)) + t_[z] for z in range(3)] for q in ecken]
        ist = [[sum(m[4 * z + j] * q[j] for j in range(3)) + m[4 * z + 3] for z in range(3)] for q in ecken]
        if k is schief:         # jede Ecke genau an ihrer Stelle
            assert all(max(abs(a_[i] - b_[i]) for i in range(3)) < 0.1 for a_, b_ in zip(soll, ist)), (r, t_, ist)
        else:                   # symmetrisch: dieselbe Hülle (Ecken als Menge)
            assert all(min(max(abs(a_[i] - b_[i]) for i in range(3)) for b_ in ist) < 0.1 for a_ in soll), (r, ist)
        assert fehler < 0.02 * max(box_k[i + 3] - box_k[i] for i in range(3)), fehler
text = str(tmp / "umlaut.step")
plan_u = dict(name="Satz Geländer", teile=[dict(name="Fußplatte", koerper=dict(art="netz", p=p, t=t), werkzeuge=[],
                                                rillen=[], meldungen=[])],
              baugruppe=dict(name="Satz Geländer", einsatz=[dict(teil=0, lage=[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0])],
                             kinder=[]))
e6 = step_export.schreiben(plan_u, text, PROGRAMM)
inhalt = Path(text).read_bytes()
assert e6["einsaetze"] == 1 and "Fußplatte".encode() in inhalt and "Fu\xc3\x83".encode().decode("unicode_escape").encode(
    "latin-1") not in inhalt, inhalt[:200]
ok("G6 Platten und Flachstahl exakt in Einbaulage (auch quadratisch, gedreht, gespiegelte Lage), Umlaute lesbar")
print("Alle Tests STEP-Baugruppe bestanden.")
