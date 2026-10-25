"""Rohrteil aus einer DXF-Zeichnung mit Ansichten (Plan 3E-12, Patrick 25.10.2026 „b a a a a a a a“):
- R1 Patricks Zeichnung (dxf_Rohr_Patrick.dxf): Vorderansicht und Draufsicht 1:5, Schnitt 1:2, Maße als Linien und
  Text: QR 40 × 40 × 3 aus dem Schnitt, Länge 1018,8 (Text L = 1000 als Hinweis), Gehrung A 20° und B 30° länger
  unten, Bohrung Ø 10 unten bei 17,3, Ausklinkung 20 breit R 3 oben am Ende A, Bezeichnung und Werkstoff.
- R2 Patricks test.dxf (QR 40, 150 lang, 1:1): vier Bohrungen Ø 5 durch beide Wände an den bemaßten Stellen.
- R3 Hilfsfunktionen: Maßzahlen, Profiltext, Muster, kein Rohr bei einem Blech, Werkstoff mit Norm.
- R4 3D aus den Eingaben: Länge Spitze zu Spitze, Querschnitt 40 × 40.
- R5 Oberfläche: Angebot Aus DXF öffnet den Rohr-Editor mit allem vorbelegt und legt die Position an; im Rohr-Editor
  DXF importieren.

Aufruf: python tests/test_dxf_rohr.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import dxf_import as di, dxf_rohr as dr, rohr3d, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.15):
    return abs(a - b) <= tol


PATRICK = HIER / "dxf" / "rohr_gehrung_QR40_patrick.dxf"
TEST = HIER / "dxf" / "rohr_ansichten_QR40.dxf"

# ------------------------------------------------------------------ R1 Patricks Zeichnung
erg = dr.erkennen(di.datei_lesen(PATRICK), PATRICK.name)
assert erg["ok"], erg["warnungen"]
assert erg["profil"] == dict(form="Quadratrohr", a=40.0, b=40.0, wand=3.0) and erg["profil_quelle"] == "Schnitt (1:2)"
assert erg["laenge"] == 1018.8 and erg["laenge_text"] == 1000
assert any("L = 1000" in h for h in erg["hinweise"]) and not erg["warnungen"]
rollen = {a["rolle"]: a["massstab"] for a in erg["ansichten"]}
assert rollen["Vorderansicht"] == 5 and rollen["Draufsicht"] == 5 and rollen["Schnitt"] == 2
e = erg["eingaben"]
assert e["a"] == dict(winkel=20.0, richtung=180, achse=sw.ACHSEN[0]), e["a"]
assert e["b"] == dict(winkel=30.0, richtung=180, achse=sw.ACHSEN[0]), e["b"]
bohr = [z for z in e["konturen"] if z["art"] == sw.BOHRUNG]
assert len(bohr) == 1 and bohr[0]["d"] == 10 and bohr[0]["x"] == 17.3 and bohr[0]["seite"] == "unten" \
    and "q" not in bohr[0]
ausk = [z for z in e["konturen"] if z["art"] == sw.AUSKLINKUNG]
assert len(ausk) == 1 and ausk[0]["b"] == 20 and ausk[0]["r"] == 3 and "seite" not in ausk[0]
# Ausklinkung oben: endet bei 37,3 mm (gezeichnet 59,456 − 52 bei 1:5), offen über die Kante der Fläche hinaus
assert nah(ausk[0]["x"] + ausk[0]["l"] / 2, 37.3, 0.1) and ausk[0]["x"] - ausk[0]["l"] / 2 < 14.55 - 3
assert erg["name"] == "Bauteil 1" and erg["werkstoff_text"] == "Stahl S235JR" and erg["artikel"] is None
assert dr.werkstoff_id(erg, {"S235-10219": {}, "1.4301": {}}) == "S235-10219"
txt = dr.bericht(erg, "QR 40x40x3")
assert "QR 40 × 40 × 3" in txt[0] and "Gehrung 20°" in txt[0] and "Gehrung 30°" in txt[0] and "2 Konturen" in txt[0]
assert any("fehlt in den Stammdaten" in z for z in dr.bericht(erg, None))
ok("R1 Patricks Zeichnung: Maßstab je Ansicht (5/5/2), QR 40 × 40 × 3, Länge 1018,8, Gehrung 20°/30° länger unten, "
   "Bohrung Ø 10 unten bei 17,3, Ausklinkung 20 × R 3 oben, Schriftfeld")

# ------------------------------------------------------------------ R2 test.dxf
erg2 = dr.erkennen(di.datei_lesen(TEST), TEST.name)
assert erg2["ok"] and erg2["profil"]["form"] == "Quadratrohr" and erg2["laenge"] == 150
e2 = erg2["eingaben"]
assert e2["a"] == {} and e2["b"] == {}
assert [z["x"] for z in e2["konturen"]] == [18.6, 46.8, 79.2, 120.6]
assert all(z["art"] == sw.BOHRUNG and z["d"] == 5 and z["wand"] == "beide" and z.get("q") == 1.0
           for z in e2["konturen"])
ok("R2 test.dxf: vier Bohrungen Ø 5 durch beide Wände an den bemaßten Stellen, 1 mm nach vorne")

# ------------------------------------------------------------------ R3 Hilfsfunktionen
assert dr.zahl("1.018,8") == 1018.8 and dr.zahl("%%c10") == 10 and dr.zahl("40") == 40 and dr.zahl("R5") is None \
    and dr.zahl("2.5") == 2.5 and dr.zahl("1.000") == 1000 and dr.zahl("4× M6") is None
assert dr.profil_aus_text(["Quadratrohr 40x40x3 – L = 1000"]) == dict(form="Quadratrohr", a=40, b=40, wand=3)
assert dr.profil_aus_text(["RE 60 x 40 x 4"]) == dict(form="Rechteckrohr", a=60, b=40, wand=4)
assert dr.profil_aus_text(["RR 33,7x2"]) == dict(form="Rundrohr", a=33.7, b=33.7, wand=2)
assert dr.laenge_aus_text(["Quadratrohr 40x40x3 – L = 1000"]) == 1000
m = dr.muster([dict(art="Bohrung", d=8, x=x) for x in (10, 60, 110, 160, 300)])
assert m[0]["anzahl"] == 4 and m[0]["abstand"] == 50 and m[0]["x"] == 10 and m[1]["x"] == 300 and len(m) == 2


def g(*paare):
    return "\n".join(f"{c}\n{v}" for c, v in paare)


blech = g((0, "SECTION"), (2, "ENTITIES"), (0, "LWPOLYLINE"), (8, "0"), (90, 4), (70, 1),
          (10, 0), (20, 0), (10, 300), (20, 0), (10, 300), (20, 40), (10, 0), (20, 40),
          (0, "CIRCLE"), (8, "0"), (10, 50), (20, 20), (40, 4), (0, "ENDSEC"), (0, "EOF"))
assert not dr.erkennen(blech, "blech.dxf")["ok"] and not dr.ist_rohrzeichnung(blech)
ok("R3 Maßzahlen, Profil- und Längentext, Muster (Anzahl + Abstand), schmales Blech ist kein Rohr")

# ------------------------------------------------------------------ R4 3D
n = rohr3d.netz(e, dict(form="Quadratrohr", a=40, b=40, wand=3), erg["laenge"])
p = [n["p"][i:i + 3] for i in range(0, len(n["p"]), 3)]
for i, (lo, hi) in enumerate(((-20, 20), (-20, 20), (0, 1018.8))):
    assert nah(min(q[i] for q in p), lo, 0.01) and nah(max(q[i] for q in p), hi, 0.01)
ok("R4 3D aus den Eingaben: 40 × 40, Länge Spitze zu Spitze 1018,8")

# ------------------------------------------------------------------ R5 Oberfläche
from rohrlaser.fenster import Hauptfenster  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
vorher = len(db.positionen(a))
gesehen = {}


def rohr_ok(d):
    gesehen.update(profil=d.k_profil.currentText(), laenge=d.k_laenge.value(), bez=d.k_bezeichnung.text(),
                   wst=d.k_werkstoff.currentText(), info=d.step_info.text(), sichtbar=not d.step_info.isHidden())
    return QDialog.Accepted


assert s.blech_aus_dxf([str(PATRICK)], dialog=lambda d: 1 / 0, rohr_dialog=rohr_ok) == 1
assert gesehen["profil"] == "QR 40x40x3" and gesehen["laenge"] == 1018.8 and gesehen["bez"] == "Bauteil 1"
assert gesehen["wst"].startswith("S235") and "Aus DXF" in gesehen["info"] and gesehen["sichtbar"]
pos = db.positionen(a)[vorher:]
assert len(pos) == 1 and pos[0]["profil_id"] == "QR 40x40x3" and pos[0]["laenge"] == 1018.8
t = sw.lesen(pos[0]["technik"])
assert t["a"]["winkel"] == 20 and t["b"]["winkel"] == 30
assert sorted(z["art"] for z in t["konturen"]) == [sw.AUSKLINKUNG, sw.BOHRUNG]
assert pos[0]["schneidweg"] and pos[0]["schneidweg"] > 0
# Rohr-Editor einer bestehenden Position: DXF importieren
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

p0 = dict(pos[0], technik=None)
d = SchneidwegDialog(s, p0, s.k.profile["QR 40x40x3"], s.kopf, s.k, s.tabellen, db, [])
assert d.dxf_importieren(str(TEST))
e3 = d.eingaben()
assert [z["x"] for z in e3["konturen"]] == [18.6, 46.8, 79.2, 120.6] and d.p["laenge"] == 150
assert all(z.get("wand") == "beide" for z in e3["konturen"])
QMessageBox.warning = QMessageBox.information = staticmethod(lambda *a, **k: None)
assert not d.dxf_importieren(str(tmp / "fehlt.dxf"))
ok("R5 Angebot Aus DXF: Rohr-Editor mit Profil, Länge, Bezeichnung, Werkstoff und Bericht, Position angelegt; "
   "DXF importieren im Rohr-Editor")
print("Alle Tests DXF-Rohr bestanden.")
