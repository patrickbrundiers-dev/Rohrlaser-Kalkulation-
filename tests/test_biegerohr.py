"""Biegerohre (Plan S9, Abschnitt 5.4): erzeugte Biegerohre mit bekannter gestreckter Länge.
- B1 Messung: Rundrohr 40 × 2 mit 2 Biegungen (90° und 45°, Radius 80, Biegeebene um 90° gedreht): Länge der
  Mittellinie, Elemente, LRA, XYZ, Prüfstatus „prüfen“, STEP-JSON 1.15; ein gerades Rohr bleibt kein Biegerohr.
- B2 Konturen: Bohrungen auf der Geraden (Lage auf der Mittellinie, Winkel um die Achse), Bohrung im Bogen mit
  „biegezone“; Rohr, das mit einem Bogen beginnt.
- B3 Programm: gestreckte Länge mit Faktor neutrale Faser, Lage der Konturen am gestreckten Rohr, Biegezonen.
- B4 Übernahme ins Angebot: Länge gestreckt, Block 'biegerohr' in technik, Zusatzarbeit Biegen je Biegung, Hinweis;
  Schneidweg-Rechner behält den Block, Teile-Editor zeigt die Biegungen, Skizze zeichnet die Zonen.
- B5 Prüfregeln: Kontur in der Biegezone, Gerade zwischen Biegungen zu kurz; ältere Datei bekommt Zusatzarbeit und
  Regeln.

Aufruf: python tests/test_biegerohr.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeTorus  # noqa: E402
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

import step_ergebnis  # noqa: E402
import step_messen  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402
from rohrlaser import biegerohr, dfm, schneidweg as sw, step, teile_editor as te  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ Testteile erzeugen
def _add(a, b, k=1.0):
    return tuple(a[i] + k * b[i] for i in range(3))


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _einheit(a):
    n = math.sqrt(sum(x * x for x in a))
    return tuple(x / n for x in a)


def _drehen(v, k, w):
    c, s = math.cos(w), math.sin(w)
    kv, d = _kreuz(k, v), sum(k[i] * v[i] for i in range(3)) * (1 - c)
    return tuple(v[i] * c + kv[i] * s + k[i] * d for i in range(3))


def rohr(schritte, d, wand, t=(1.0, 0.0, 0.0), b=(0.0, 1.0, 0.0)):
    """Biegerohr aus Zylindern und Tori: schritte = [('L', Länge) | ('B', Radius, Winkel°, Drehung°)], Start im
    Ursprung in Richtung t, erste Biegung zur Seite b (Drehung = Biegeebene um die Achse gedreht)."""
    p, teile = (0.0, 0.0, 0.0), {"a": [], "i": []}
    for n, s in enumerate(schritte):
        if s[0] == "L":
            for k, r in (("a", d / 2), ("i", d / 2 - wand)):
                e0 = 0.5 if k == "i" and n == 0 else 0.0
                e1 = 0.5 if k == "i" and n == len(schritte) - 1 else 0.0
                teile[k].append(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*_add(p, t, -e0)), gp_Dir(*t)), r,
                                                         s[1] + e0 + e1).Shape())
            p = _add(p, t, s[1])
            continue
        _, radius, w, dreh = s
        b = _einheit(_drehen(b, t, math.radians(dreh)))
        c = _add(p, b, radius)
        z, x = _einheit(_kreuz(t, b)), tuple(-v for v in b)
        for k, r in (("a", d / 2), ("i", d / 2 - wand)):
            teile[k].append(BRepPrimAPI_MakeTorus(gp_Ax2(gp_Pnt(*c), gp_Dir(*z), gp_Dir(*x)), radius, r,
                                                  math.radians(w)).Shape())
        phi = math.radians(w)
        p = _add(c, tuple(radius * (-math.cos(phi) * b[i] + math.sin(phi) * t[i]) for i in range(3)))
        t, b = (_einheit(tuple(math.sin(phi) * b[i] + math.cos(phi) * t[i] for i in range(3))),
                _einheit(tuple(math.cos(phi) * b[i] - math.sin(phi) * t[i] for i in range(3))))

    def fuse(liste):
        s = liste[0]
        for x in liste[1:]:
            s = BRepAlgoAPI_Fuse(s, x).Shape()
        return s
    return BRepAlgoAPI_Cut(fuse(teile["a"]), fuse(teile["i"])).Shape()


def loch(shape, p, richtung, d):
    return BRepAlgoAPI_Cut(shape, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p), gp_Dir(*richtung)), d / 2,
                                                            25).Shape()).Shape()


def speichern(shape, name):
    pfad = tmp / f"{name}.step"
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    w.Write(str(pfad))
    return pfad


tmp = Path(tempfile.mkdtemp())
ZWEI = [("L", 200), ("B", 80, 90, 0), ("L", 150), ("B", 80, 45, 90), ("L", 100)]
SOLL = 450 + 80 * math.pi / 2 + 80 * math.pi / 4          # Mittellinie 638,50 mm
b1 = speichern(rohr(ZWEI, 40, 2), "b1")
s = loch(rohr(ZWEI, 40, 2), (100, 30, 0), (0, -1, 0), 8)
s = loch(s, (100, 0, 30), (0, 0, -1), 10)
b2 = speichern(loch(s, (200 + 80 * math.sin(math.pi / 4), 80 - 80 * math.cos(math.pi / 4), 30), (0, 0, -1), 6), "b2")
b4 = speichern(rohr([("B", 60, 90, 0), ("L", 30), ("B", 60, 90, 180)], 30, 1.5), "b4")
gerade = speichern(BRepAlgoAPI_Cut(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 20, 300).Shape(),
                                   BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -1), gp_Dir(0, 0, 1)), 18,
                                                            302).Shape()).Shape(), "gerade")

# ------------------------------------------------------------------ B1 Messung
(t,) = analysiere_datei(b1)
assert t.profilform == "Rundrohr" and abs(t.abm_a - 40) < 1e-3 and abs(t.wandstaerke - 2) < 1e-3, t
assert abs(t.laenge - SOLL) < 0.05 and t.pruefstatus == "prüfen", (t.laenge, t.pruefstatus)
br = t.biegerohr
assert [e["art"] for e in br["elemente"]] == ["gerade", "bogen", "gerade", "bogen", "gerade"]
assert [(z["gerade"], z["drehung"], z["winkel"]) for z in br["lra"]] == [(200, 0, 90), (150, 90, 45), (100, 0, 0)], \
    br["lra"]
assert [z["radius"] for z in br["lra"]] == [80, 80, None]
k = 80 * math.tan(math.radians(22.5))
soll_xyz = [(0, 0, 0), (0, 0, 280), (150 + 80 + k, 0, 280),
            (230 + k + (k + 100) / math.sqrt(2), (k + 100) / math.sqrt(2), 280)]
assert all(abs(a - b) < 0.02 for p, q in zip(br["xyz"], soll_xyz) for a, b in zip(p, q)), br["xyz"]
assert t.ende_a_gerade and t.ende_b_gerade and abs(t.ende_a - 40 * math.pi) < 0.05 and t.konturen == 2
j = step_ergebnis.koerper(t)
assert step_ergebnis.SCHEMA_VERSION >= "1.15" and j["biegerohr"]["mittellinie"] == round(SOLL, 2), j["biegerohr"]
(g,) = analysiere_datei(gerade)
assert g.biegerohr is None and g.profilform == "Rundrohr" and abs(g.laenge - 300) < 0.01
ok("B1 Messung: Mittellinie 638,5 mm, LRA, XYZ, Prüfstatus prüfen, JSON 1.15; gerades Rohr unverändert")

# ------------------------------------------------------------------ B2 Konturen
(t2,) = analysiere_datei(b2)
innen = [d for d in t2.konturen_liste if not d["art"].startswith("Ende")]
assert [(d["art"], d["durchmesser"], d["z"], d["winkel"]) for d in innen] == \
    [("Bohrung", 8.0, 100.0, 0.0), ("Bohrung", 10.0, 100.0, 90.0), ("Bohrung", 6.0, 262.83, 90.0)], innen
assert [bool(d.get("biegezone")) for d in innen] == [False, False, True]
assert t2.innen_konturen == 3 and t2.konturen == 5 and t2.bohrungen == {8.0: 1, 10.0: 1, 6.0: 1}
assert any("Biegezone" in h for h in t2.hinweise)
(t4,) = analysiere_datei(b4)
assert abs(t4.laenge - (60 * math.pi + 30)) < 0.05 and [z["gerade"] for z in t4.biegerohr["lra"]] == [0, 30, 0]
assert abs(t4.biegerohr["lra"][1]["drehung"]) == 180
# ein Bogen aus zwei Torusflächen beiderseits der Naht u = 0 (zweite Fläche mit eigener X-Richtung) bleibt eine Biegung
import step_biegerohr  # noqa: E402
w = -math.pi / 4
naht = {1: ("T", 20.0, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 80.0, 0.0, math.pi / 4),
        2: ("T", 20.0, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (math.cos(w), math.sin(w), 0.0), (-math.sin(w), math.cos(w), 0.0),
            80.0, 0.0, math.pi / 4)}
(bogen,) = step_biegerohr._elemente(naht, 20.0)
assert abs(bogen["winkel"] - 90) < 1e-6 and abs(bogen["laenge"] - 80 * math.pi / 2) < 1e-6, bogen
ok("B2 Konturen: Lage auf der Mittellinie, Winkel, Biegezone; Rohr beginnt mit einem Bogen; Bogen über die Torus-Naht")

# ------------------------------------------------------------------ B3 Programm: gestreckte Länge
assert abs(biegerohr.laenge(br) - SOLL) < 0.01
assert abs(biegerohr.laenge(br, 1.1) - (450 + 1.1 * (SOLL - 450))) < 0.01
assert abs(biegerohr.gestreckt(262.83, br, 1.1) - (200 + 1.1 * 62.83)) < 0.01
assert abs(biegerohr.gestreckt(400, br, 1.1) - (400 + 0.1 * 125.66)) < 0.01
zonen = biegerohr.biegungen(br, 1.0)
assert [(z["nr"], round(z["x0"], 1), round(z["x1"], 1)) for z in zonen] == [(1, 200, 325.7), (2, 475.7, 538.5)]
assert biegerohr.in_zone(250, 260, br) == [1] and biegerohr.in_zone(90, 110, br) == []
assert biegerohr.geraden_zwischen(br) == [(1, 150.0)]
assert biegerohr.lra_zeilen(br)[0] == "B1: L 200 · R 0° · A 90° · Radius 80" and biegerohr.lra_zeilen(br)[-1] == "Ende: L 100"
ok("B3 Programm: gestreckte Länge mit Faktor, Lage am gestreckten Rohr, Zonen")

# ------------------------------------------------------------------ B4 Übernahme ins Angebot
netze = tmp / "netze"
netze.mkdir()
step_messen.main(["--ausgabe", str(tmp / "b2.txt"), "--netze", str(netze), str(b2)])
mw = step.lade_netze(step.lies_messwerte(tmp / "b2.txt"), netze)
assert mw[0]["biegerohr"] and mw[0].get("_netz")
db = Datenbank(tmp / "rohrlaser.db")
katalog = db.zeilen("zusatzarbeiten")
assert any(z["name"] == biegerohr.ZUSATZ_BIEGEN and z["art"] == "€/Stück" for z in katalog)
mw[0]["_uebernehmen"] = True
erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", 5, neue_profile=True,
                       biegerohr_faktor=1.1, zusatz_katalog=katalog)
(p,) = erg["positionen"]
L11 = 450 + 1.1 * (SOLL - 450)
assert abs(p["laenge"] - L11) < 0.06, p["laenge"]
e = sw.lesen(p["technik"])
assert e["biegerohr"]["faktor"] == 1.1
xs = sorted(z["x"] for z in e["konturen"])
assert xs == [100.0, 100.0, round(200 + 1.1 * 62.83, 1)], xs
(zu,) = json.loads(p["zusatz"])
assert zu["name"] == "Biegen" and zu["menge"] == 2 and zu["stand"]["preis"] == 1.5
assert "Biegerohr: 2 Biegungen, gestreckt" in "; ".join(erg["bericht"]), erg["bericht"]
ohne = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", 5, neue_profile=True,
                        erneut=True, zusatz_katalog=[])
assert "Zusatzarbeit 'Biegen' fehlt" in "; ".join(ohne["bericht"]) and not ohne["positionen"][0].get("zusatz")
assert abs(ohne["positionen"][0]["laenge"] - SOLL) < 0.06    # Vorgabe Faktor 1,0

from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
profil = dict(form="Rundrohr", a=40, b=None, wand=2, profil_id="RR 40x2")
kopf = dict(maschine="T11", stange=6000)
d = SchneidwegDialog(None, dict(p, id=1), profil, kopf, db.kontext(), db.tabellen())
assert d.eingaben()["biegerohr"]["faktor"] == 1.1                     # bleibt beim Speichern erhalten
m = {x.id: x for x in te.merkmale_rohr(d.eingaben(), p["laenge"])}
assert m["biegung:0"].gruppe == "Biegungen" and m["biegung:0"].text.startswith("B1: L 200 · R 0° · A 90° · Radius 80")
assert m["teil"].text.endswith("gestreckt, Biegerohr") and m["xyz"].text.startswith("XYZ: P1: 0 / 0 / 0")
d.skizze.resize(900, 400)
d.skizze.bild(900, 400)                                                 # Biegezonen zeichnen ohne Fehler
ok("B4 Übernahme: gestreckte Länge, Konturen umgerechnet, Zusatzarbeit Biegen, Rechner und Teile-Editor")

# ------------------------------------------------------------------ B5 Prüfregeln
befunde = dfm.rohr(p, profil)
(bz,) = [b for b in befunde if b.regel == dfm.BIEGEZONE]
assert "Biegung 1" in bz.text and bz.stufe == dfm.WARNUNG and len(bz.zeilen) == 1, bz
assert not [b for b in befunde if b.regel == dfm.GERADE_KURZ]
step_messen.main(["--ausgabe", str(tmp / "b4.txt"), str(b4)])
mw4 = step.lies_messwerte(tmp / "b4.txt")
mw4[0]["_uebernehmen"] = True
(p4,) = step.uebernehmen(mw4, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", 5, neue_profile=True,
                         zusatz_katalog=katalog)["positionen"]
(gk,) = [b for b in dfm.rohr(p4, dict(form="Rundrohr", a=30, wand=1.5)) if b.regel == dfm.GERADE_KURZ]
assert "kürzeste 30 mm nach Biegung 1" in gk.text and "45 mm" in gk.text, gk
aus = [dict(regel=dfm.GERADE_KURZ, aktiv="nein"), dict(regel=dfm.BIEGEZONE, aktiv="ja", grenzwert=0, stufe=dfm.FEHLER)]
assert not [b for b in dfm.rohr(p4, dict(form="Rundrohr", a=30, wand=1.5), zeilen=aus) if b.regel == dfm.GERADE_KURZ]
assert [b.stufe for b in dfm.rohr(p, profil, zeilen=aus) if b.regel == dfm.BIEGEZONE] == [dfm.FEHLER]
regeln = [z["regel"] for z in db.zeilen("pruefregeln")]
assert dfm.BIEGEZONE in regeln and dfm.GERADE_KURZ in regeln
# ältere Datei: Zusatzarbeit und Regeln fehlen, Stand fehlt -> ergänzt
db.con.execute("DELETE FROM zusatzarbeiten WHERE name='Biegen'")
db.con.execute("DELETE FROM pruefregeln WHERE regel IN (?, ?)", (dfm.BIEGEZONE, dfm.GERADE_KURZ))
db.con.execute("DELETE FROM einstellungen WHERE name='biegerohr_stand'")
db.con.commit()
db.schliessen()
db = Datenbank(tmp / "rohrlaser.db")
assert any(z["name"] == "Biegen" for z in db.zeilen("zusatzarbeiten"))
assert {dfm.BIEGEZONE, dfm.GERADE_KURZ} <= {z["regel"] for z in db.zeilen("pruefregeln")}
db.schliessen()
ok("B5 Prüfregeln: Biegezone, kurze Gerade, abschaltbar; ältere Datei ergänzt")
