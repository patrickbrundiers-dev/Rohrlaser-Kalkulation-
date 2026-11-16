"""Schneidvorschau, Anschnitt und Mikrostege (Recherche 3D-Editor 16.11.2026, V1 + V2, Patrick „Alle Empfehlungen“):

- Reihenfolge: Rohr Anfangsschnitt, Gravuren, Konturen von Ende A nach B, Endschnitt; Blech Gravuren, Innenkonturen,
  Außenkontur zuletzt; Platz (folge) je Kontur geht vor
- Schritte aus dem Netz der 3D-Ansicht (rohr3d, blech3d): Einstich auf der Kontur, Anschnitt in %, Mikrostege
  gleichmäßig, Leerweg, Zeit je Schritt aus der Bearbeitungsliste
- Ansicht3D zeichnet die Folge; Teile-Editor Rohr und Blech: Knopf „Schneidvorschau“, ◀ ▶, Abspielen
- Eigenschaften Schneidfolge/Anschnitt/Mikrostege werden gespeichert (Rohr, Blech, Blech-Außenkontur)
- CAM-Paket: Schneidfolge.csv und Spalte Mikrostege

Aufruf: python tests/test_schneidfolge.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import schneidfolge as sf, schneidweg as sw  # noqa: E402


def _mitte_(pk):
    return tuple(sum(p[i] for p in pk) / len(pk) for i in range(3))


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ Reihenfolge ohne Netz
e = dict(laenge=500, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=400, seite="oben"),
                               dict(art=sw.GRAVUR, anzahl=1, laenge=20, x=250, seite="oben"),
                               dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=100, seite="oben"),
                               dict(art=sw.BOHRUNG, anzahl=1, d=8, x=250, seite="oben")])
r = [m for m, _ in sf.reihenfolge(e, "rohr")]
assert r == ["ende:a", "kontur:1", "kontur:2", "kontur:3", "kontur:0", "ende:b"], r
e2 = json.loads(json.dumps(e))
e2["konturen"][0]["folge"] = 1          # Bohrung bei x 400 zuerst
r2 = [m for m, _ in sf.reihenfolge(e2, "rohr")]
assert r2 == ["ende:a", "kontur:0", "kontur:1", "kontur:2", "kontur:3", "ende:b"], r2
eb = dict(konturen=[dict(art=sw.BOHRUNG, d=10, x=50, y=150), dict(art=sw.BOHRUNG, d=10, x=200, y=20),
                    dict(art=sw.TEXT_GRAVUR, text="A1", x=100, y=100)])
assert [m for m, _ in sf.reihenfolge(eb, "blech")] == ["kontur:2", "kontur:1", "kontur:0", "teil"]
assert sf.werte(dict(folge=2, anschnitt=125, mikrostege=3)) == (2, 25.0, 3, sf.STEG_BREITE)
assert sf.werte({}) == (None, None, 0, sf.STEG_BREITE)
assert not sf.hat_vorgaben(e) and sf.hat_vorgaben(e2)
ok("Reihenfolge: Rohr Anfangsschnitt, Gravur, Konturen A→B, Endschnitt; Platz geht vor; Blech Außenkontur zuletzt")

# ------------------------------------------------------------------ Schritte am Rohr (Netz aus den Eingaben)
from rohrlaser import rohr3d  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
pr = k.profile["QR 40x40x3"]
netz = rohr3d.netz(dict(e, a=dict(winkel=0), b=dict(winkel=0)), pr, 500)
st = sf.schritte(e, netz, "rohr", {"kontur:0": 2.0, "ende:a": 1.0})
assert [x["mid"] for x in st] == r, [x["mid"] for x in st]
assert st[0]["leer"] == 0 and all(x["leer"] >= 0 for x in st)
assert st[0]["s"] == 1.0 and st[4]["s"] == 2.0 and st[1]["s"] is None
zz = sf.zuege(netz)


def auf_zug(q, pks):
    return min(math.dist(q, sf.punkt_bei(pk, sf._naechste(pk, q))) for pk in pks) < 1e-6


for x in st:
    assert auf_zug(x["start"], x["punkte"]), x["mid"]
e3 = json.loads(json.dumps(e))
e3["konturen"][2].update(anschnitt=50, mikrostege=4, steg_breite=1.0)
st3 = sf.schritte(e3, netz, "rohr")
ll = next(x for x in st3 if x["mid"] == "kontur:2")
pk = ll["punkte"][0]
assert math.dist(ll["start"], sf.punkt_bei(pk, sf._laenge(pk) * 0.5)) < 1e-6
assert len(ll["stege"]) == 4 and ll["stege_n"] == 4
lg = sf._laenge(pk)
for i, s_ in enumerate(ll["stege"]):     # je Steg 1 mm lang (Sehne), um eine Teilung versetzt
    assert abs(sum(math.dist(a, b) for a, b in zip(s_, s_[1:])) - 1.0) < 0.05
    assert auf_zug(s_[1], [pk])
assert abs(lg - sf._laenge(zz["kontur:2"][0])) < 1e-9
tx = sf.text_schritt(st3, 2)
assert tx.startswith("Schritt 3 von 6:") and "4 Mikrostege" in tx and "Leerweg" in tx, tx
assert sf.text_schritt(st3, None).startswith("Schneidvorschau: 6 Schritte")
ok(f"Rohr: 6 Schritte, Einstich auf der Kontur, Anschnitt 50 %, 4 Mikrostege à 1 mm, Leerweg "
   f"{sf.summen(st)[2]:.0f} mm")

# ------------------------------------------------------------------ Schritte am Blech
from rohrlaser import blech, blech3d  # noqa: E402

roh = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=300, breite=200, dicke=3, werkstoff="S235JR", stueck=5,
           konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=30, y=30), dict(art=sw.LANGLOCH, anzahl=1, l=40, b=10,
                                                                           x=150, y=100)],
           aussen_schneiden=dict(mikrostege=2, anschnitt=10))
zs = blech.zuschnitt(roh)
bn = blech3d.netz(roh, zs)
assert bn["geo"]["zuege"] and bn["geo"]["aussen"]
sb = sf.schritte(roh, bn, "blech")
assert [x["mid"] for x in sb] == ["kontur:0", "kontur:1", "teil"], [x["mid"] for x in sb]
assert len(sb[-1]["stege"]) == 2 and sb[-1]["text"].startswith("Außenkontur")
oben = max(p_[1] for pk in sb[0]["punkte"] for p_ in pk)
assert all(abs(p_[1] - oben) < 1e-6 for pk in sb[0]["punkte"] for p_ in pk)     # nur die obere Seite
ok("Blech: Innenkonturen von unten nach oben, Außenkontur zuletzt mit 2 Mikrostegen, nur die obere Seite")

# ------------------------------------------------------------------ Ansicht3D
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import ansicht3d as a3  # noqa: E402

app = QApplication.instance() or QApplication([])
v = a3.Ansicht3D()
v.resize(500, 350)
v.setzen(netz, "Test")
for akt in (None, 0, 2, 5):
    v.folge_setzen(st3, akt, sf.text_schritt(st3, akt))
    bild = QImage(500, 350, QImage.Format_ARGB32)
    p = QPainter(bild)
    v._beschriften(p)
    p.end()
assert v.folge and v.folge_text
v.folge_setzen()
assert not v.folge and not v.folge_text
ok("3D-Ansicht: Folge mit Nummern, Einstich, Mikrostegen und Leerweg gezeichnet; aus = weg")

# ------------------------------------------------------------------ Teile-Editor Rohr
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

technik = dict(quelle=sw.QUELLE, a=dict(winkel=0), b=dict(winkel=0), konturen=e3["konturen"])
p_ = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, technik=json.dumps(technik))
d = SchneidwegDialog(None, p_, pr, dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed = d.editor
z2 = d.eingaben()["konturen"][2]
assert z2.get("anschnitt") == 50 and z2.get("mikrostege") == 4 and z2.get("steg_breite") == 1.0, z2
assert not ed.folge_vor.isEnabled()
ed.folge_knopf.setChecked(True)
assert ed.folge_vor.isEnabled() and len(ed.folge_liste) == 6
a = ed.ansicht()
assert a.folge and a.folge_akt is None and a.folge_text.startswith("Schneidvorschau")
ed._folge_schritt(1)
assert a.folge_akt == 0 and a.folge_text.startswith("Schritt 1 von 6")
for _ in range(5):
    ed._folge_schritt(1)
assert a.folge_akt == 5
ed._folge_schritt(1)
assert a.folge_akt is None                  # nach dem letzten: Übersicht
ed._folge_schritt(-1)
assert a.folge_akt == 5
ed.folge_ablauf.setChecked(True)
assert ed.folge_takt.isActive() and a.folge_akt == 0        # Ablauf: nach dem letzten wieder von vorn
ed._folge_schritt(1, rundum=True)
assert a.folge_akt == 1
if ed._bearbeitungen():
    assert any(x["s"] for x in ed.folge_liste), "Zeiten fehlen"
ed.aktualisieren()
assert a.folge                              # bleibt beim Neurechnen an
ed.folge_knopf.setChecked(False)
assert not a.folge and not ed.folge_takt.isActive()
ok("Teile-Editor Rohr: Schneidvorschau, ◀ ▶ und Abspielen; Anschnitt/Mikrostege aus den Eingaben gespeichert")

# Eigenschaften: Felder je Kontur
ed.eigenschaften.zeigen("kontur:2")
f = ed.eigenschaften.felder
assert {"Schneidfolge", "Anschnitt", "Mikrostege", "Stegbreite"} <= set(f), set(f)
combo = d.tabelle.cellWidget(0, 0)
ed.eigenschaften._eig_setzen(combo, "folge", 2)
assert d.eingaben()["konturen"][0].get("folge") == 2
ed.eigenschaften.zeigen("kontur:1")         # Gravur: keine Schneidfelder
assert "Mikrostege" not in ed.eigenschaften.felder
ok("Eigenschaften Rohr: Schneidfolge, Anschnitt, Mikrostege, Stegbreite (nicht bei Gravur), gespeichert")

# Schneiden je Teil (Patrick 16.11.2026 20:33): Abfall, Abfallschnitte am Ende, Ende sichern ein/aus/um
ed.eigenschaften.zeigen("teil")
f = ed.eigenschaften.felder
assert {"Abfall großer Ausschnitte", "Abfallschnitte am Ende", "Ende mit Mikrostegen sichern"} <= set(f), set(f)
ed.eigenschaften._teil_setzen("abfall", sf.ZERSCHNEIDEN)
ed.eigenschaften._teil_setzen("ende_sichern", "ja")
assert d.eingaben()[sf.TEIL] == dict(abfall=sf.ZERSCHNEIDEN, ende_sichern="ja")
assert ed.eigenschaften.felder["Abfall großer Ausschnitte"].currentData() == sf.ZERSCHNEIDEN
ed.eigenschaften._teil_setzen("abfall", None)
ed.eigenschaften._teil_setzen("ende_sichern", None)
assert sf.TEIL not in d.eingaben()
ok("Eigenschaften Teil (Rohr): Schneiden je Teil gespeichert, wie Einstellung = nichts gespeichert")

# ------------------------------------------------------------------ Teile-Editor Blech
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402

roh["konturen"][1].update(folge=1, mikrostege=2)
bd = BlechDialog(None, db, json.loads(json.dumps(roh)), neu=False)
eb2 = bd.eingaben()
assert eb2.get("aussen_schneiden") == dict(mikrostege=2, anschnitt=10), eb2.get("aussen_schneiden")
assert eb2["konturen"][1].get("folge") == 1 and eb2["konturen"][1].get("mikrostege") == 2
be = bd.editor
be.aktualisieren()
be.folge_knopf.setChecked(True)
assert [x["mid"] for x in be.folge_liste] == ["kontur:1", "kontur:0", "teil"], [x["mid"] for x in be.folge_liste]
be.eigenschaften.zeigen("teil")
assert "Mikrostege" in be.eigenschaften.felder and "Schneidfolge" not in be.eigenschaften.felder
be.eigenschaften._aussen_setzen("mikrostege", 3)
assert bd.eingaben()["aussen_schneiden"]["mikrostege"] == 3
be.eigenschaften._aussen_setzen("mikrostege", None)
be.eigenschaften._aussen_setzen("anschnitt", None)
assert "aussen_schneiden" not in bd.eingaben()
be.eigenschaften.zeigen("teil")
assert "Abfall großer Ausschnitte" in be.eigenschaften.felder and "Abfallschnitte am Ende" not in be.eigenschaften.felder
be.eigenschaften._teil_setzen("abfall", sf.MIKROSTEGE)
assert bd.eingaben()[sf.TEIL] == dict(abfall=sf.MIKROSTEGE)
assert BlechDialog(None, db, bd.eingaben(), neu=False).teil_schneiden == dict(abfall=sf.MIKROSTEGE)
ok("Teile-Editor Blech: Folge mit Platz, Außenkontur mit Anschnitt/Mikrostegen und Schneiden je Teil")

# ------------------------------------------------------------------ CAM-Paket
from rohrlaser import cam_paket  # noqa: E402

pr_rohr = dict(pos=1, artikel="R-1", technik=json.dumps(technik))
pr_blech = dict(pos=2, artikel="B-1", technik=blech.speichern(roh) if hasattr(blech, "speichern") else json.dumps(roh))
art, zeilen = cam_paket.schneidfolge(pr_rohr)
assert art == "rohr" and [x["merkmal"] for x in zeilen][0] == "ende:a" and zeilen[-1]["merkmal"] == "ende:b"
ll = next(x for x in zeilen if x["merkmal"] == "kontur:2")
assert ll["anschnitt"] == "50 %" and ll["mikrostege"] == 4 and ll["steg_breite"] == 1.0
assert "4 × 1 mm" in cam_paket._stege(pr_rohr), cam_paket._stege(pr_rohr)
art_b, zb = cam_paket.schneidfolge(pr_blech)
assert art_b == "blech" and zb[-1]["merkmal"] == "teil" and zb[-1]["mikrostege"] == 2, zb
art_o, zo = cam_paket.schneidfolge(dict(technik=json.dumps(dict(quelle=sw.QUELLE, konturen=e["konturen"]))))
assert art_o == "rohr" and len(zo) == 6 and all(x["abfall"] == "" for x in zo)
p_k = dict(pr_rohr, profil_id="QR 40x40x3", laenge=500)
_, zk = cam_paket.schneidfolge(p_k, k, dict(maschine="T11"), db.einstellungen())
assert {x["merkmal"] for x in zk} == {x["merkmal"] for x in zeilen} and zk[0]["merkmal"] == "ende:a"
assert next(x for x in zk if x["merkmal"] == "kontur:0")["anfahrweg"] == "4 mm"          # Ø10, Wand 3 + 1
ok("CAM-Paket: Schneidfolge.csv je Merkmal (Rohr und Blech) mit Anfahrweg und Abfall, Mikrostege in der Stückliste")

# ------------------------------------------------------------------ Patrick 16.11.2026: Leerwege, Abfall, Anfahrweg
rg = sf.regel()
assert rg["anfahr_zuschlag"] == 1.0 and rg["abfall_art"] == sf.MIKROSTEGE and rg["abfall_ab"] == 80.0 and rg["mikrosteg_anteil"] == 1.0
assert sf.regel(dict(abfall_ab=50), dict(abfall_max=80))["abfall_ab"] == 80          # Maschinenfeld geht vor
schlitz = dict(art=sw.LANGLOCH, l=200, b=30)
assert sf.abfall(schlitz) == dict(art=sf.MIKROSTEGE, stege=3, schnitte=[])          # zu gleichen Teilen festgesetzt
assert sf.abfall(dict(schlitz, abfall=sf.ZERSCHNEIDEN))["schnitte"] == [(2, 30.0, False)]   # 3 Stücke ≤ 80 mm
assert sf.zerschneiden_mm(dict(schlitz, l=450, abfall=sf.ZERSCHNEIDEN)) == (5, 150.0)       # 6 Stücke ≤ 80 mm
assert sf.zerschneiden_mm(dict(schlitz, abfall=sf.ZERSCHNEIDEN), sf.regel(dict(abfall_ab=100))) == (1, 30.0)
assert sf.mikrostege_n(schlitz) == 3 and sf.mikrostege_n(dict(schlitz, abfall=sf.ZERSCHNEIDEN)) == 0
assert sf.regel(dict(mikrosteg_einstich=50))["mikrosteg_anteil"] == 0.5
# Stegbreite nach Dicke (Patrick 16.11.2026): bis 1,5 mm 0,3; ab 2 mm 0,5; ab 4 mm 0,7; ab 6 mm 0,8; ab 10 mm 1,2
assert [sf.steg_breite(rg, w) for w in (1, 1.5, 2, 3, 4, 6, 8, 10, 15)] == [0.3, 0.3, 0.5, 0.5, 0.7, 0.8, 0.8, 1.2, 1.2]
assert sf.staffel(sf.STEG_STAFFEL_TEXT) == sf.STEG_STAFFEL and sf.staffel("1") == ((0.0, 1.0),)
assert sf.staffel("quatsch") == sf.STEG_STAFFEL and sf.steg_breite(rg, 3, dict(steg_breite=1.0)) == 1.0
assert sf.steg_breite(sf.regel(dict(steg_staffel="ab 0: 0,4; ab 5 mm: 1")), 6) == 1.0
assert sf.abfall(dict(schlitz, abfall=sf.FREI))["art"] is None
assert sf.abfall(dict(art=sw.BOHRUNG, d=40))["art"] is None                          # klein: fällt frei
assert sf.abfall(dict(schlitz, mikrostege=5))["stege"] == 5                          # von Hand gilt
assert sf.anfahrweg(dict(art=sw.BOHRUNG, d=10), 3) == 4.0                            # Wand 3 + 1 mm
assert sf.anfahrweg(dict(art=sw.BOHRUNG, d=6), 3) == 0.0                             # passt nicht: Punktanfahrt
assert sf.anfahrweg(dict(art=sw.SCHLITZ, l=20, b=5), 1) == 0.0
assert sf.anfahrweg(dict(art=sw.BOHRUNG, d=10), 3, sf.regel(None, dict(anfahrweg=2))) == 2.0
e4 = dict(laenge=600, a=dict(winkel=0), b=dict(winkel=0), konturen=[
    dict(art=sw.BOHRUNG, anzahl=1, d=12, x=100, seite="oben"), dict(art=sw.BOHRUNG, anzahl=1, d=12, x=110, seite="unten"),
    dict(art=sw.BOHRUNG, anzahl=1, d=12, x=120, seite="oben"), dict(art=sw.BOHRUNG, anzahl=1, d=12, x=130, seite="unten"),
    dict(art=sw.LANGLOCH, anzahl=1, l=200, b=30, x=400, seite="oben", abfall=sf.ZERSCHNEIDEN),
    dict(art=sw.BOHRUNG, anzahl=1, d=6, x=550, seite="vorne")])
n4 = rohr3d.netz(e4, pr, 600)
opt_ = sf.schritte(e4, n4, "rohr", wand=3)
ohne = sf.schritte(e4, n4, "rohr", wand=3, optimieren=False)
lo, la = sf.summen(opt_)[2], sf.summen(ohne)[2]
assert lo < la - 20, (lo, la)            # oben, oben, unten, unten statt viermal drehen
assert [x["mid"] for x in opt_][0] == "ende:a" and opt_[-1]["mid"] == "ende:b"
ll4 = next(x for x in opt_ if x["mid"] == "kontur:4")
assert ll4["abfall"] == sf.ZERSCHNEIDEN and len(ll4["schnitte"]) == 2 and not ll4["stege"]
a_, b_ = ll4["schnitte"][0]
assert 28 < math.dist(a_, b_) < 32, math.dist(a_, b_)        # quer durch den Schlitz
assert ll4["anfahr_mm"] == 4.0 and ll4["anfahrt"] and abs(math.dist(*ll4["anfahrt"]) - 4.0) < 1e-6
assert next(x for x in opt_ if x["mid"] == "kontur:5")["anfahrt"] is None                 # Ø6: Punkt
assert "Punktanfahrt" in sf.text_schritt(opt_, [x["mid"] for x in opt_].index("kontur:5"))
ok(f"Leerwege kürzer ({la:.0f} → {lo:.0f} mm), Schlitz 200 × 30 mit 2 Querschnitten zerschnitten, Anfahrweg Wand + 1 mm, "
   "Ø6 Punktanfahrt")

# Patrick 16.11.2026 20:12: Einstich mittig auf der Kontur, an der Seite zum nächsten Rohrende; Mikrostege dadurch
# symmetrisch (Langloch: gegenüber), Abstand einstellbar; kritische Enden mit Abfallschnitten, auf Wunsch gesichert
ll0 = next(x for x in opt_ if x["mid"] == "kontur:4")       # Langloch längs bei x = 400 (näher an Ende B)
assert abs(ll0["start"][0]) < 1.0 and ll0["start"][2] > 400 + 90, ll0["start"]       # mittig, Seite zu Ende B
e5 = dict(e4, konturen=[dict(art=sw.LANGLOCH, anzahl=1, l=200, b=30, x=150, seite="oben")])
s5 = sf.schritte(e5, rohr3d.netz(e5, pr, 600), "rohr", wand=3)[1]
assert abs(s5["start"][0]) < 1.0 and s5["start"][2] < 150 - 90, s5["start"]           # Seite zu Ende A
s5b = sf.schritte(e5, rohr3d.netz(e5, pr, 600), "rohr", rg=sf.regel(dict(abfall_ab=80)), wand=3)[1]
st2 = [_mitte_(pk) for pk in s5b["stege"]]
assert len(st2) == 3 and abs(st2[1][0]) < 1.0 and abs(st2[0][2] - st2[2][2]) < 1.0, st2  # symmetrisch zur Mitte
assert sf.abfall(schlitz, sf.regel(dict(steg_abstand=50)))["stege"] == 10            # U 460 / 50 mm
um_breit = [[s_, 30.0 if 10 < s_ < 130 else 0.0] for s_ in range(0, 160, 5)]
e6 = dict(laenge=600, a=dict(gemessen=160.0, form="komplex", umriss=um_breit), b=dict(winkel=0), konturen=[])
n6 = rohr3d.netz(e6, pr, 600)
assert sf.ende_sonder(e6["a"]) and not sf.ende_sonder(dict(winkel=30)) and sf.ende_sonder(dict(sattel=60))
a6 = sf.schritte(e6, n6, "rohr", wand=3)[0]
zug6 = a6["schnitte"][0]          # quer am Umfang durch den Abfall (Patrick 16.11.2026), halbe Tiefe
assert a6["ende_n"] == 1 and not a6["stege_n"] and 100 < sf._laenge(zug6) < 125 and all(abs(q[2] - 15) < 1e-6 for q in zug6)
assert "1 Abfallschnitt am Ende" in sf.text_schritt([a6], 0)
a6s = sf.schritte(e6, n6, "rohr", rg=sf.regel(dict(ende_sichern="ja")), wand=3)[0]
assert a6s["ende_n"] == 1 and a6s["stege_n"] == 1                                   # Steg auf dem Abfallschnitt
st6 = a6s["stege"][0]
assert all(abs(q[2] - 15) < 1e-6 for q in st6), st6          # auf dem Querschnitt, nicht auf dem Endschnitt
assert sf.schritte(e6, n6, "rohr", rg=sf.regel(dict(ende_abfall_ab=40)), wand=3)[0]["ende_n"] == 0   # flacher
ring = [[s_, 16 + 15 * math.cos(s_ / 160 * 4 * math.pi)] for s_ in range(0, 160, 5)]
e7 = dict(e6, a=dict(gemessen=160.0, form="komplex", umriss=ring))
n7 = rohr3d.netz(e7, pr, 600)          # Sattelform: zwei Lappen je ~80 mm breit
assert sf.schritte(e7, n7, "rohr", wand=3)[0]["ende_n"] == 2                          # je Lappen ein Querschnitt
assert sf.schritte(e7, n7, "rohr", rg=sf.regel(dict(abfall_ab=12)), wand=3)[0]["ende_n"] == 4   # tiefer: zwei je Lappen
t6 = sf.tabelle(e6, "rohr", n6, sf.regel(dict(ende_sichern="ja")), 3)
assert t6[0]["abfall"] == "1 Abfallschnitt, gesichert mit 1 Mikrosteg (Teil fällt ganz ab)" and t6[0]["mikrostege"] == 1, t6[0]
from rohrlaser import zeit_zusatz as zz  # noqa: E402

# je Teil: Vorgaben des Teils statt Einstellung, Kontur geht vor
rg_t = sf.mit_teil(sf.regel(), dict(teil_schneiden=dict(abfall=sf.ZERSCHNEIDEN, ende_abfall="nein", ende_sichern="ja")))
assert rg_t["abfall_art"] == sf.ZERSCHNEIDEN and rg_t["ende_abfall_ab"] == 0 and rg_t["ende_sichern"]
assert sf.abfall(schlitz, rg_t)["art"] == sf.ZERSCHNEIDEN and sf.abfall(dict(schlitz, abfall=sf.MIKROSTEGE), rg_t)["stege"]
rg_f = sf.mit_teil(sf.regel(), dict(teil_schneiden=dict(abfall=sf.FREI)))
assert sf.abfall(schlitz, rg_f)["art"] is None and sf.abfall(dict(schlitz, mikrostege=2), rg_f)["stege"] == 2
assert sf.mit_teil(sf.regel(dict(ende_abfall_ab=0)), dict(teil_schneiden=dict(ende_abfall="ja")))["ende_abfall_ab"] == 20
assert sf.mit_teil(sf.regel(), {}) == sf.regel()
assert sf.schritte(dict(e6, teil_schneiden=dict(ende_abfall="nein")), n6, "rohr", wand=3)[0]["ende_n"] == 0
p6n = dict(laenge=600, profil_id="QR 40x40x3",
           technik=json.dumps(dict(e6, quelle="x", teil_schneiden=dict(ende_abfall="nein"))))
p6 = dict(laenge=600, profil_id="QR 40x40x3", technik=json.dumps(dict(e6, quelle="Schneidweg-Rechner")))
n_e, mm_e, st_e = zz.ende_abfall(p6, {}, db.kontext(), 3)
assert n_e == 1 and 100 < mm_e < 125 and st_e == 0 and zz.ende_abfall(p6, {}, db.kontext(), 3, dict(ende_sichern="ja"))[2] == 1
assert zz.ende_abfall(dict(p6, technik=json.dumps(dict(e4, quelle="x"))), {}, db.kontext(), 3) == (0, 0.0, 0)
assert zz.ende_abfall(p6n, {}, db.kontext(), 3) == (0, 0.0, 0)                      # je Teil aus
p_sl = dict(laenge=600, technik=json.dumps(dict(e4, quelle="x", konturen=[dict(art=sw.LANGLOCH, anzahl=1, l=200, b=30, x=300, seite="oben")],
                                                teil_schneiden=dict(abfall=sf.ZERSCHNEIDEN))))
assert zz.mikrostege(p_sl, {})[0] == 0 and zz.abfall_zerteilen(p_sl, {}) == (2, 60.0)  # je Teil klein schneiden
ok("Einstich mittig zum nächsten Rohrende, Mikrostege symmetrisch und mit Abstand, kritisches Ende mit Abfallschnitt "
   "und Mikrostegen, Zeit dafür")

from rohrlaser import dynamik  # noqa: E402

m_dyn = dict(eilgang_x=60000, beschl_x=5, drehzahl=60, beschl_dreh=600)
lagen4 = [dict(x=100, eingabe=dict(seite="oben")), dict(x=110, eingabe=dict(seite="unten")),
          dict(x=120, eingabe=dict(seite="oben")), dict(x=130, eingabe=dict(seite="unten"))]
t_neu = dynamik.verfahrzeit(m_dyn, lagen4, 600)
t_alt = sum(max(dynamik.bewegung(abs(q[0] - p_[0]) / 1000, 1000, 5),
                dynamik.bewegung(abs(((q[1] or 0) - (p_[1] or 0) + 180) % 360 - 180), 360, 600)
                if p_[1] is not None and q[1] is not None else 0.0)
            for p_, q in zip([(0, None)] + [(100, 0), (110, 180), (120, 0), (130, 180)],
                             [(100, 0), (110, 180), (120, 0), (130, 180)] + [(600, None)]))
assert t_neu < t_alt - 0.1, (t_neu, t_alt)
assert dynamik.folge(lagen4) == sorted(dynamik.folge(lagen4))          # ohne Dynamik wie bisher längs
ok(f"Laserzeit: Leerwege in der kürzesten Folge ({t_alt:.2f} → {t_neu:.2f} s)")
# Leerwege wie der Kopf fährt (Laserzeit Phase 5): Zeit statt mm als Kosten, Kopfhub je Schritt
from rohrlaser import rohr3d  # noqa: E402

pr_rr = dict(form="Rechteckrohr", a=60, b=40, wand=2)
e_k = dict(laenge=500, konturen=[dict(art=sw.BOHRUNG, d=10, x=100, seite="oben", anzahl=1),
                                 dict(art=sw.BOHRUNG, d=10, x=110, seite="vorne", anzahl=1),
                                 dict(art=sw.BOHRUNG, d=10, x=400, seite="oben", anzahl=1),
                                 dict(art=sw.BOHRUNG, d=10, x=120, seite="oben", anzahl=1)])
n_k = rohr3d.netz(e_k, pr_rr, 500)
m_k = dict(eilgang_x=60000, beschl_x=10, drehzahl=60, beschl_dreh=3000, hub_ab_weg=20, hub_z=5, eilgang_z=30000,
           beschl_z=10, hub_sicherheit=5, zeit_regelung=0.1)
assert sf.lage((0.0, 20.0, 50.0), pr_rr) == (50.0, 0.0) and sf.lage((-30.0, 5.0, 0.0), pr_rr)[1] == 90.0
assert sf.lage((-3.0, 20.0, 0.0), pr_rr)[1] == 0.0          # auf der Fläche: kein Drehen
ohne = sf.schritte(e_k, n_k, "rohr", rg=sf.regel(), wand=2, profil=pr_rr)
mit = sf.schritte(e_k, n_k, "rohr", rg=sf.regel(None, m_k), wand=2, profil=pr_rr)
assert all(x["hub"] is None and x["leer_s"] is None for x in ohne)
hube = [x["hub"] for x in mit[1:]]
assert "drehen" in hube and "sprung" in hube, hube
assert all(x["hub_mm"] >= 5 for x in mit[1:] if x["hub"] in ("sprung", "drehen"))
# Kosten in Zeit: so wenig Drehen über die Kante wie möglich (vorne einmal hin und zurück)
seiten = [e_k["konturen"][int(x["mid"].split(":")[1])]["seite"] for x in mit if x["mid"].startswith("kontur:")]
wechsel = sum(1 for a_, b_ in zip(seiten, seiten[1:]) if a_ != b_)
assert wechsel <= 2, seiten
t_ges = sum(x["leer_s"] for x in mit[1:])
assert t_ges > 0 and "Kopf heben" in sf.text_schritt(mit, None)
txt = " ".join(sf.text_schritt(mit, i) for i in range(len(mit)))
assert "zum Drehen über die Kante" in txt and "Kopf heben (5 mm)" in txt
rund = sf.schritte(e_k, rohr3d.netz(e_k, dict(form="Rundrohr", a=50, wand=2), 500), "rohr",
                   rg=sf.regel(None, m_k), wand=2, profil=dict(form="Rundrohr", a=50, wand=2))
assert "drehen" not in [x["hub"] for x in rund]             # Rundrohr dreht ohne Hub
e_mix = dict(laenge=500, konturen=[dict(art=sw.BOHRUNG, d=10, x=x, seite=s_, anzahl=1) for x, s_ in
                                   ((100, "oben"), (140, "vorne"), (180, "oben"), (220, "vorne"), (260, "oben"),
                                    (300, "vorne"), (340, "oben"))])
n_mix = rohr3d.netz(e_mix, pr_rr, 500)
rg_k = sf.regel(None, m_k)
t_mm, t_zeit = (sum(sf.kopf_art(a_["start"], b_["start"], rg_k, pr_rr)["t_s"] for a_, b_ in zip(st_, st_[1:]))
                for st_ in (sf.schritte(e_mix, n_mix, "rohr", rg=r_, wand=2, profil=pr_rr) for r_ in (sf.regel(), rg_k)))
assert t_zeit < 0.8 * t_mm, (t_mm, t_zeit)       # oben/vorne im Wechsel: erst alle oben, dann vorne zurück
ok(f"Schneidvorschau wie der Kopf fährt: Zeit statt mm, Kopfhub je Schritt, Wechsel oben/vorne {t_mm:.2f} → {t_zeit:.2f} s")
print("alle Prüfungen bestanden")
