"""Vorschläge je Baugruppe bzw. Satz (Plan „Baugruppen automatisch und innovativ“, P1; Patrick 25.10.2026 „Alle a“):
- Längsnaht automatisch ohne Fenster: frei von Konturen und Nasen, innen bevorzugt, ohne Mitte und Konturen kein
  Vorschlag
- Satz S03 (vier Stöße): Vorschläge Steckverbindung mit Laser-Mehrkosten, Längsnaht je Rohr; Übernehmen legt dieselben
  Verbindungen an wie „Alle Stöße stecken“, die Naht liegt danach nicht auf einem Schlitz
- Rahmen aus vier Rohren mit Gehrung als Satz: Vorschlag Knickrahmen mit Knicken × 3 und Laser; Übernehmen = Knickrahmen
  wie mit dem Knopf
- derselbe Rahmen als Schweißbaugruppe: Nahtgruppen aus den STEP-Vorschlägen (mit Paaren) verlieren mit dem Knickrahmen
  ihre Ecken, Lösen holt sie zurück; der Vorschlag rechnet die Ecknähte und das Positionieren

Aufruf: python tests/test_baugruppe_vorschlaege.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

from OCP.BRep import BRep_Builder  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism  # noqa: E402
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: E402
from OCP.TopoDS import TopoDS_Compound  # noqa: E402
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import step_messen  # noqa: E402
from rohrlaser import baugruppe, baugruppe_vorschlaege as bv, schneidweg as sw, skizze as sk, step  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.ansicht3d import entpacken  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ Längsnaht ohne Fenster
QR = dict(form="Quadratrohr", a=40.0, b=40.0, wand=2.0)
RE = dict(form="Rechteckrohr", a=60.0, b=40.0, wand=2.0)
oben = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, d=10.0, anzahl=1, x=100.0, seite="oben")])
w, grund = bv.naht_lage(QR, oben, 500.0, innen=0.0)
assert w in (90.0, 270.0) and "nächste freie" in grund, (w, grund)      # oben belegt, innen = oben
assert bv.naht_lage(QR, oben, 500.0, innen=180.0)[0] == 180.0           # unten frei und innen
assert bv.naht_lage(QR, dict(a={}, b={}, konturen=[]), 500.0)[0] is None   # nichts zu vermeiden, keine Mitte
assert bv.naht_lage(RE, dict(a={}, b={}, konturen=[]), 500.0, innen=90.0)[0] == 90.0
alle = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, d=10.0, anzahl=1, x=100.0, seite=s_)
                                   for s_ in sk.Querschnitt(QR).seiten()])
assert bv.naht_lage(QR, alle, 500.0, innen=0.0)[0] is None
qs = sk.Querschnitt(QR)
assert not bv._frei(sk.naht_s(qs, 0.0), bv.belegt(qs, oben, 500.0), qs.umfang)
assert bv._frei(sk.naht_s(qs, 90.0), bv.belegt(qs, oben, 500.0), qs.umfang)
v = bv.vorschlag(bv.KNICK, "x", [], {}, [("a", 3.0), ("b", -1.25)], ["c"])
assert v["saldo"] == 1.75 and "offen: c" in bv.rechnung_text(v) and bv.euro(1.75) == "1,75 €"
assert [x["art"] for x in bv.sortieren([bv.vorschlag(bv.NAHT, "n", [], {}), v])] == [bv.KNICK, bv.NAHT]
ok("Längsnaht automatisch: belegte Wand gemieden, innen bevorzugt, ohne Anlass kein Vorschlag; Saldo und Text")

# ------------------------------------------------------------------ Satz S03: Steckverbindungen und Längsnaht
tmp = Path(tempfile.mkdtemp())


def einlesen(datei, db, wie, **flags):
    ziel = tmp / datei.stem
    step_messen.main(["--ausgabe", str(ziel) + ".txt", "--json", str(ziel) + ".json", "--netze", str(ziel), str(datei)])
    mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(str(ziel) + ".txt"), ziel), str(ziel) + ".json")
    for x in mw:
        x.update(_stueck=1, _uebernehmen=True, **wie)
    k = db.kontext()
    erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                           zukauf_liste=[])
    db.profile_anlegen(erg["profile"])
    a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
    for q in erg["positionen"]:
        netz = q.pop("_netz", None)
        q.pop("_zukauf", None)
        pid = db.position_neu(a, q)
        if netz:
            db.netz_speichern(pid, netz)
    for satz, daten in (erg.get("satz_daten") or {}).items():
        db.satz_daten_speichern(a, satz, daten)
    return a, mw


db = Datenbank(tmp / "vorschlaege.db")
f = Hauptfenster(db, stumm=True)
a, _ = einlesen(HIER / "step_struktur" / "S03_Rahmen_geschweisst.step", db, dict(_saetze=1))
seite = f.angebot_oeffnen(a)
gesehen = {}


def satz_bedienen(d):
    gesehen["info"] = d.vorschlag_info.text()
    liste = d.vorschlaege_sammeln()
    gesehen["arten"] = [v["art"] for v in liste]
    gesehen["steck"] = [v for v in liste if v["art"] == bv.STECK]
    gesehen["n"] = d.vorschlaege_zeigen(dialog=lambda dlg: (dlg.anhaken(lambda v: True), QDialog.Accepted)[1])
    gesehen["verbindungen"] = len(d.bg["steckverbindungen"])
    gesehen["naehte"] = dict(d.laengsnaehte)
    gesehen["eingaben"] = d._rohr_eingaben()
    gesehen["profile"] = {pid: d._steck_profil(pid) for pid in d.laengsnaehte}
    gesehen["danach"] = d.vorschlaege_sammeln(laser=False)
    d._ok()
    return d.result()


assert seite.satz_3d(0, dialog=satz_bedienen)
st = gesehen["steck"]
assert len(st) == 3 and "Steckverbindung" in gesehen["info"], gesehen["info"]
assert all(any(t.startswith("Laser") for t, _ in v["posten"]) for v in st), [v["posten"] for v in st]
assert all(v["saldo"] is not None and v["saldo"] < 0 for v in st), [v["saldo"] for v in st]   # Satz: nur Laser mehr
assert not any(t.startswith("Stecker positionieren") for v in st for t, _ in v["posten"])       # kein Schweißen
n, nicht = gesehen["n"]
assert gesehen["verbindungen"] == 3 and n == 3 + len(gesehen["naehte"]) and not nicht, (gesehen["n"], nicht)
assert gesehen["naehte"], gesehen["arten"]
for pid, w in gesehen["naehte"].items():                                   # Naht nicht auf Schlitz oder Nase
    e, lg = gesehen["eingaben"][pid]
    q = sk.Querschnitt(gesehen["profile"][pid])
    assert bv._frei(sk.naht_s(q, w), bv.belegt(q, e, lg), q.umfang), (pid, w)
assert not [v for v in gesehen["danach"] if v["art"] in (bv.STECK, bv.NAHT)], gesehen["danach"]
pos = {q["id"]: q for q in db.positionen(a)}
assert all(pos[pid]["naht_vorgabe"] == "feste Position" and pos[pid]["naht_winkel"] == w
           for pid, w in gesehen["naehte"].items())
ok(f"Satz S03: 3 Steckverbindungen (nur Laser, Mehrkosten), {len(gesehen['naehte'])} Längsnähte; Übernehmen legt sie "
   "an, Nähte frei von Schlitzen und Nasen, danach keine Vorschläge mehr")


# ------------------------------------------------------------------ Rahmen mit Gehrung: Knickrahmen
def prisma(punkte, z0, z1):
    poly = BRepBuilderAPI_MakePolygon()
    for x, y in punkte:
        poly.Add(gp_Pnt(x, y, z0))
    poly.Close()
    return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(poly.Wire()).Face(), gp_Vec(0, 0, z1 - z0)).Shape()


def schenkel(L, a=40.0, s=2.0):
    aussen = prisma([(0, 0), (L, 0), (L - a, a), (a, a)], 0, a)
    innen = prisma([(s, s), (L - s, s), (L - a + s, a - s), (a - s, a - s)], s, a - s)
    return BRepAlgoAPI_Cut(aussen, innen).Shape()


def lage(shape, grad, dx, dy):
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(grad))
    v = gp_Trsf()
    v.SetTranslation(gp_Vec(dx, dy, 0))
    return BRepBuilderAPI_Transform(BRepBuilderAPI_Transform(shape, t).Shape(), v).Shape()


c, b = TopoDS_Compound(), BRep_Builder()
b.MakeCompound(c)
for t in (lage(schenkel(500), 0, 0, 0), lage(schenkel(300), 90, 500, 0), lage(schenkel(500), 180, 500, 300),
          lage(schenkel(300), 270, 0, 300)):
    b.Add(c, t)
rahmen = tmp / "Rahmen.step"
w_ = STEPControl_Writer()
w_.Transfer(c, STEPControl_AsIs)
w_.Write(str(rahmen))
a2, _ = einlesen(rahmen, db, dict(_saetze=1))
seite = f.angebot_oeffnen(a2)
knick = {}


def knick_bedienen(d):
    liste = d.vorschlaege_sammeln()
    knick["v"] = [v for v in liste if v["art"] == bv.KNICK]
    knick["n"] = d.vorschlaege_zeigen(dialog=lambda dlg: (dlg.anhaken(lambda v: v["art"] == bv.KNICK),
                                                           QDialog.Accepted)[1])
    knick["knicke"] = len(d.knicke)
    d._ok()
    return d.result()


assert seite.satz_3d(0, dialog=knick_bedienen)
(kv_,) = knick["v"]
texte = [t for t, _ in kv_["posten"]]
assert "3 × Knicken" in texte and any(t.startswith("Laser") for t in texte), kv_["posten"]
assert len(kv_["daten"]["koerper"]) == 4 and len(kv_["teile"]) == 2 and kv_["daten"]["knicke"] == 3 and knick["n"] == (1, []) and knick["knicke"] == 1
neu = max(db.positionen(a2), key=lambda q: q["laenge"])
assert neu["laenge"] == 1592.7 and len([z for z in sw.lesen(neu["technik"])["konturen"]
                                        if z["art"] == "V-Ausschnitt"]) == 3
ok("Rahmen mit Gehrung als Satz: Vorschlag Knickrahmen (4 Rohre, Knicken × 3, Laser), Übernehmen = Knickrahmen 1592,7 mm")

# ------------------------------------------------------------------ derselbe Rahmen als Schweißbaugruppe
for t_, zeilen_ in baugruppe.richtwerte_fehlend(db.tabellen()).items():    # Verfahren, Kennwerte, Regeln
    for z_ in zeilen_:
        db.neu(t_, z_)
a3, _ = einlesen(rahmen, db, dict(_saetze=1, _baugruppe=True))
seite = f.angebot_oeffnen(a3)
bgp = next(q for q in db.positionen(a3) if q.get("art") == BAUGRUPPE)
bg_ = {}


def editor(d):
    d.regel_haken.setChecked(True)                                         # a-Maß nach Regel
    d.vorschlaege_uebernehmen(list(range(len(d.bg["vorschlaege"]))))       # Nahtgruppen mit Paaren
    bg_["paare_vor"] = sum(len(n.get("paare") or ()) for n in d.bg["naehte"])
    liste = d.vorschlaege_sammeln()
    bg_["v"] = next(v for v in liste if v["art"] == bv.KNICK)
    bg_["n"] = d.vorschlaege_anwenden([dict(bg_["v"], an=True)])
    bg_["paare_nach"] = sum(len(n.get("paare") or ()) for n in d.bg["naehte"])
    d.teile_tab.selectAll()
    bg_["geloest"] = d.knick_loesen()
    bg_["paare_zurueck"] = sum(len(n.get("paare") or ()) for n in d.bg["naehte"])
    d.reject()
    return d.result()


zeile = next(r for r, q in enumerate(seite.positionen) if q["id"] == bgp["id"])
seite.baugruppe_bearbeiten([zeile], dialog=editor)
assert bg_["paare_vor"] >= 4 and bg_["paare_nach"] == bg_["paare_vor"] - 3, bg_
assert bg_["geloest"] == 1 and bg_["paare_zurueck"] == bg_["paare_vor"], bg_
texte = [t for t, w in bg_["v"]["posten"] if w > 0]
assert any("Ecknaht" in t for t in texte) and any("positionieren" in t for t in texte), bg_["v"]
assert baugruppe.vorschlag_naht(dict(teile=[[1, 2], [2, 3]], anzahl=2))["paare"] == [["1", "2"], ["2", "3"]]
assert entpacken(db.netz(next(q for q in db.positionen(a3) if q.get("art") != BAUGRUPPE)["id"]))
ok("Schweißbaugruppe: Nahtgruppen verlieren mit dem Knickrahmen 3 Ecken, Lösen holt sie zurück; Vorschlag rechnet "
   "Ecknähte und Positionieren")
# Nur einen späteren Vorschlag übernehmen: Schlitze/Nasen gegen das Vorhandene neu bestimmen
from types import SimpleNamespace  # noqa: E402

from rohrlaser.baugruppe_dialog import SteckEditor  # noqa: E402

ed = SimpleNamespace(bg=dict(steckverbindungen=[]))
spaet = dict(auf="1", st="2", ende="a", x=100.0, seite="oben", schlitze=False, nasen=False, schlitz_ort=True)
e = SteckEditor.steck_schnitte(ed, spaet)
assert e and e["schlitze"] and e["nasen"], e
ed.bg["steckverbindungen"].append(dict(_auf="1", _st="2", _ende="a", x=100.0, seite="oben"))
assert SteckEditor.steck_schnitte(ed, spaet) is None
assert not SteckEditor.steck_schnitte(ed, dict(spaet, ende="b"))["schlitze"]
assert SteckEditor.steck_schnitte(ed, dict(spaet, ende="b", schlitz_ort=False, x=300.0))["schlitze"] is False
ok("Einzelner späterer Vorschlag bekommt seine Schlitze und Nasen selbst, doppelte entfallen")
db.schliessen()
print("Vorschläge je Baugruppe: alle Tests bestanden.")
