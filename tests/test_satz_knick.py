"""Knickrahmen im Fenster „Satz in 3D“ (Patrick 24.10.2026, Schritt 2b): Rahmen aus vier Rohren QR 40 × 40 × 2 mit
45°-Gehrungen (500 × 300 außen) als Satz ohne Schweißbaugruppe eingelesen, ohne Knickverbindung im Prüfdialog.
- Rohre markieren, „Knickrahmen erstellen …“: Kette aus allen Körpern (die zwei gleichen Streben sind eine Position
  mit je Satz 2), Dialog wie im Prüfdialog, Rahmen in einer Farbe, lösen und wieder erstellen
- OK: eine neue Position mit gestreckter Länge 1592,7 mm, 3 V-Ausschnitten, Zusatzarbeit Knicken × 3 und gefaltetem
  Netz; die Rohre sind weg
- nicht markierte Rohre bleiben, ein Rohr allein gibt einen Grund
- dasselbe im Editor der Schweißbaugruppe (Regel: Schritte eines Editors auch in den anderen): Nahtvorschläge an den
  Ecken fallen weg, der Stoß bleibt; die neue Position gehört zur Baugruppe, Körper der Schenkel im Netz

Aufruf: python tests/test_satz_knick.py
"""
import json
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
from rohrlaser import knickrahmen as kn, schneidweg as sw, step  # noqa: E402
from rohrlaser.ansicht3d import entpacken  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


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


tmp = Path(tempfile.mkdtemp())
c, b = TopoDS_Compound(), BRep_Builder()
b.MakeCompound(c)
for t in (lage(schenkel(500), 0, 0, 0), lage(schenkel(300), 90, 500, 0), lage(schenkel(500), 180, 500, 300),
          lage(schenkel(300), 270, 0, 300), lage(schenkel(300), 90, 2000, 0)):     # dazu eine Strebe allein
    b.Add(c, t)
datei = tmp / "Rahmen.step"
w = STEPControl_Writer()
w.Transfer(c, STEPControl_AsIs)
w.Write(str(datei))
step_messen.main(["--ausgabe", str(tmp / "m.txt"), "--json", str(tmp / "m.json"), "--netze", str(tmp / "netze"),
                  str(datei)])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(tmp / "m.txt"), tmp / "netze"), tmp / "m.json")
assert len(mw) == 5
for x in mw:
    x.update(_saetze=1, _stueck=1, _uebernehmen=True)             # Satz, keine Knickverbindung im Prüfdialog
db = Datenbank(tmp / "knick.db")
k = db.kontext()
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True, zukauf_liste=[])
satz = step.satzname(datei)
db.profile_anlegen(erg["profile"])
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db.position_neu(a, q)
    if netz:
        db.netz_speichern(pid, netz)
vorher = db.positionen(a)
assert len(vorher) == 2 and sorted(q["je_satz"] for q in vorher) == [2, 3], [(q["artikel"], q["je_satz"]) for q in vorher]
strebe = next(q for q in vorher if q["je_satz"] == 3)
punkte = len(entpacken(db.netz(vorher[0]["id"]))["p"])
assert all(sw.lesen(q["technik"])["a"].get("winkel") == 45.0 for q in vorher)
ok("Satz eingelesen: 2 Positionen (Holm 2, Strebe 3 je Satz), Gehrung 45° in den Eingaben")

f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(a)
gesehen = {}


def bedienen(d):
    # Doppelklick im 3D (26.10.2026): ganze Gehrungskette gewählt, Rechtsklick-Menü erstellt den Knickrahmen
    nr = next(i for i, k in enumerate(d._koerper) if k[0] == strebe["id"])
    gesehen["kette"] = sorted(d.doppelt_geklickt(dict(id=f"teil:{nr}", punkt=(0, 0, 0))))
    gesehen["kette_mark"] = len(d.teile_tab.markierte())
    menue = d.kontext_menue(dict(id=f"teil:{nr}", punkt=(0, 0, 0)))
    gesehen["menue"] = dict(menue)
    d.knick_erstellen = (lambda alt: lambda **kw: alt(dialog=lambda dlg: QDialog.Accepted, melden=False))(
        d.knick_erstellen)
    d.kontext_menue(dict(id=f"teil:{nr}", punkt=(0, 0, 0)), wahl="Knickrahmen erstellen …")
    gesehen["menue_knick"] = len(d.knicke)
    gesehen["kette_neu"] = len(d.kette_zu(strebe["id"]))
    d.kontext_menue(dict(id=f"teil:{nr}", punkt=(0, 0, 0)), wahl="Knickrahmen lösen")
    gesehen["menue_los"] = len(d.knicke)
    del d.knick_erstellen
    d.kontext_menue(dict(id=f"teil:{nr}", punkt=(0, 0, 0)), wahl="Auswahl aufheben")
    gesehen["leer"] = d.teile_tab.markierte()
    # ein Rohr allein: Grund
    d.teile_tab.selectRow(0)
    gesehen["allein"] = d.knick_erstellen(melden=False)
    d.teile_tab.selectAll()
    gesehen["n"] = d.knick_erstellen(dialog=lambda dlg: (dlg.k.setValue(0.5), QDialog.Accepted)[1], melden=False)
    gesehen["text"] = d.teile_tab.item(0, 5).text()
    gesehen["farben"] = d.zeigen()
    gesehen["geloest"] = d.knick_loesen()
    gesehen["wieder"] = d.knick_erstellen(dialog=lambda dlg: (dlg.k.setValue(0.5), QDialog.Accepted)[1],
                                          melden=False)
    d._ok()
    return d.result()


assert seite.satz_3d(0, dialog=bedienen)
assert gesehen["kette"] == sorted(q["id"] for q in vorher) and gesehen["kette_mark"] == 2, gesehen
assert gesehen["menue"]["Knickrahmen erstellen …"] and not gesehen["menue"]["Knickrahmen lösen"], gesehen
assert gesehen["menue"]["Steckverbindung hinzufügen (erstes = Aufnahme)"], gesehen              # zwei Positionen
assert gesehen["menue_knick"] == 1 and gesehen["kette_neu"] == 2 and gesehen["menue_los"] == 0, gesehen
assert gesehen["leer"] == [], gesehen
ok("Satz in 3D: Doppelklick wählt die Gehrungskette, Rechtsklick-Menü erstellt und löst den Knickrahmen")
assert isinstance(gesehen["allein"], str) and gesehen["allein"], gesehen
assert gesehen["n"] == 1 and gesehen["geloest"] == 1 and gesehen["wieder"] == 1, gesehen
assert "Knickrahmen 1" in gesehen["text"] and gesehen["farben"] == 5, gesehen
p, rest = sorted(db.positionen(a), key=lambda q: -q["laenge"])
assert rest["id"] == strebe["id"] and rest["je_satz"] == 1 and rest["stueck"] == 1, rest
rn = entpacken(db.netz(rest["id"]))
assert "lagen" not in rn and rn["lage"] and len(rn.get("koerper") or ()) <= 1, rn.keys()
assert p["laenge"] == 1592.7, p["laenge"]
assert p["je_satz"] == 1 and p["stueck"] == 1 and p["satz"] == satz, (p["je_satz"], p["stueck"])
e = sw.lesen(p["technik"])
assert len([z for z in e["konturen"] if z["art"] == "V-Ausschnitt"]) == 3 and e["knickrahmen"]["geschlossen"]
(zu,) = json.loads(p["zusatz"])
assert zu["name"] == kn.ZUSATZ_KNICKEN and zu["menge"] == 3, zu
netz = entpacken(db.netz(p["id"]))
assert netz["lage"] and len(netz["p"]) > 3 * punkte
ok("Satz in 3D: Knickrahmen aus 4 Körpern (2 Positionen je 2), lösen, OK: 1 Position 1592,7 mm, 3 V, Knicken × 3, "
   "gefaltetes Netz, Holm entfernt, übrige Strebe 1 je Satz")

# ------------------------------------------------------------------ Editor der Schweißbaugruppe
from rohrlaser import baugruppe  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
for x in mw:
    for n in [n for n in x if n.startswith("_knick")]:
        x.pop(n)
    x.update(_baugruppe=True)
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True, zukauf_liste=[])
a2 = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db.position_neu(a2, q)
    if netz:
        db.netz_speichern(pid, netz)
pos2 = db.positionen(a2)
bgp = next(q for q in pos2 if q.get("art") == BAUGRUPPE)
vorschlaege = baugruppe.lesen(bgp["baugruppe"])["vorschlaege"]
paare = sum(len(v["teile"]) for v in vorschlaege)
assert paare >= 4, vorschlaege
seite = f.angebot_oeffnen(a2)
bg_seh = {}


def editor(d):
    rohre = [r for r, t in enumerate(d.teile) if t.get("drin")]
    d.teile_tab.clearSelection()
    sel = d.teile_tab.selectionModel()
    from PySide6.QtCore import QItemSelectionModel
    for r in rohre:
        sel.select(d.teile_tab.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
    bg_seh["n"] = d.knick_erstellen(dialog=lambda dlg: (dlg.k.setValue(0.5), QDialog.Accepted)[1], melden=False)
    bg_seh["paare"] = sum(len(v["teile"]) for v in d.bg["vorschlaege"])
    bg_seh["info"] = d.knick_info.text()
    d._ok()
    return d.result()


zeile = next(r for r, q in enumerate(seite.positionen) if q["id"] == bgp["id"])
assert seite.baugruppe_bearbeiten([zeile], dialog=editor)
assert bg_seh["n"] == 1 and bg_seh["paare"] == paare - 3 and "Knickrahmen 1" in bg_seh["info"], bg_seh
nach = db.positionen(a2)
rahmen = [q for q in nach if q.get("art") != BAUGRUPPE and q.get("bg_knoten")]
assert [q["laenge"] for q in rahmen if q["laenge"] > 1000] == [1592.7], [(q["artikel"], q["laenge"]) for q in nach]
rq = next(q for q in rahmen if q["laenge"] > 1000)
assert baugruppe.zuordnung(rq)[0] == baugruppe.lesen(bgp["baugruppe"])["id"] and rq["je_knoten"] == 1
assert len(entpacken(db.netz(rq["id"]))["koerper"]) == 4
rest = [q for q in rahmen if q is not rq]
assert len(rest) == 1 and rest[0]["je_knoten"] == 1, [(q["artikel"], q.get("je_knoten")) for q in rest]
ok("Schweißbaugruppe: Knickrahmen im Editor, Nahtvorschläge an 3 Ecken weg, Position in der Baugruppe, Strebe 1")
db.schliessen()
print("Knickrahmen im Satz: alle Tests bestanden.")
