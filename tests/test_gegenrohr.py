"""3D-Editor Schritt 3E-7 (Plan kalkulation/3d-editor, G2 G4 G5 G6, Patrick „Alle a“):
- G1 Gegenrohr am Ende: rund rechtwinklig = Sattel, rechteckig, schräg, mit Versatz, auf Quadrat-/Rechteckrohr;
  Fehler bei zu kleinem Gegenrohr und Gehrung + Gegenrohr; Text und „nicht gerade“ in der Position.
- G2 Schnittkante (skizze.schnitt_x): Spitze 0, Sattel oben/unten am längsten, Lage senkrecht dreht den Sattel.
- G3 Durchbruch: Länge wie durchdringung, flach rechtwinklig = Umfang des Gegenrohrs, beide Wände doppelt, Fehler.
- G4 Lochfeld: Löcher = Anzahl × Reihen, Lage je Loch (Reihen quer um die Mitte, versetzt), Langlöcher, Fehler.
- G5 Fase: Rechteck und Ausklinkung gefast (Länge, Umriss mit 8 Ecken).
- G6 3D: Gegenrohr pink (HK) am Ende und am Durchbruch, Löcher ausgeschnitten, Text-Gravur als Schrift.
- G7 Editor: Gegenrohr-Dialog, Menüband (Gegenrohr, Lochfeld, Ecken), Rechtsklick (Ecken, Gegenrohr), Eigenschaften
  (Fase, Lochfeld versetzt), Gegenrohr bleibt beim Speichern und nach Rückgängig, Maßbilder.

Aufruf: python tests/test_gegenrohr.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "programm"))

from rohrlaser import durchdringung as dd, rohr3d, schneidweg as sw, skizze as sk  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, tol=0.05):
    return abs(a - b) <= tol


QR = dict(form="Quadratrohr", a=60, b=60, wand=4)
RE = dict(form="Rechteckrohr", a=80, b=40, wand=3, r_aussen=0)
RR = dict(form="Rundrohr", a=60.3, wand=3)
GRENZEN = (10, 50)

# ------------------------------------------------------------------ G1 Gegenrohr am Ende
assert nah(sw.ende(RR, gegen=dict(d=80))[0], sw.sattel(60.3, 80), 0.01)
assert nah(sw.ende(RR, gegen=dict(d=80))[0], sw.ende(RR, gegenrohr=80)[0], 0.01)        # wie die alte Ausklinkung
gerade = sw.ende(QR)[0]
assert nah(sw.ende(QR, gegen=dict(d=200, t=200))[0], gerade, 0.01)       # flache Wand: wie ein gerader Schnitt
schraeg = sw.ende(QR, gegen=dict(d=200, t=200, winkel=30))[0]
assert nah(schraeg, sw.ende(QR, 30, sw.ACHSEN[1])[0], 0.5) or nah(schraeg, sw.ende(QR, 30)[0], 0.5)  # = Gehrung 30°
assert sw.ende(RR, gegen=dict(d=80, versatz=8))[0] > sw.sattel(60.3, 80)
assert sw.ende(RE, gegen=dict(d=100))[0] > sw.ende(RE)[0]
for falsch, text in ((dict(d=50), "Gegenrohr"), (dict(d=80, winkel=85), "Winkel")):
    try:
        sw.ende(RR, gegen=falsch)
        raise AssertionError(falsch)
    except ValueError as f:
        assert text in str(f), f
try:
    sw.ende(RR, 30, gegen=dict(d=80))
    raise AssertionError("Gehrung + Gegenrohr")
except ValueError as f:
    assert "Gehrungswinkel 0" in str(f)
try:
    sw.ende(dict(form="U-Profil", a=80, b=45, wand=6), gegen=dict(d=100))
    raise AssertionError("U-Profil")
except ValueError as f:
    assert "nur bei Rund-" in str(f)
r = sw.rechnen(dict(a=dict(gegen=dict(d=80, winkel=20, versatz=5)), b={}, konturen=[]), RR, GRENZEN)
assert not r["fehler"] and r["felder"]["a_gerade"] == "nein" and r["felder"]["a_ende"] is None
assert r["schritte"][0]["text"] == "Anfangsschnitt auf Gegenrohr Ø 80 schräg 20°, Versatz 5", r["schritte"][0]["text"]
assert nah(r["felder"]["a_schnitt"], sw.ende(RR, gegen=dict(d=80, winkel=20, versatz=5))[0], 0.1)
r = sw.rechnen(dict(a=dict(gegen=dict(d=50)), b={}, konturen=[]), RR, GRENZEN)
assert r["fehler"] and r["fehler"][0].startswith("Anfangsschnitt: ")
ok("G1 Gegenrohr am Ende: Sattel, flach, schräg = Gehrung, Versatz länger, Rechteckrohr, Fehler, Text der Position")

# ------------------------------------------------------------------ G2 Schnittkante
qr = sk.Querschnitt(RR)
R, r_ = 40.0, 30.15
assert nah(sk.schnitt_x(qr, dict(gegen=dict(d=80)), 0, r_), 0, 0.01)                    # oben: Horn, Spitze
assert nah(sk.schnitt_x(qr, dict(gegen=dict(d=80)), r_, 0), R - math.sqrt(R * R - r_ * r_), 0.02)
assert nah(sk.schnitt_x(qr, dict(gegen=dict(d=80, lage="senkrecht")), r_, 0), 0, 0.01)  # senkrecht: Hörner seitlich
qq = sk.Querschnitt(QR)
w = dict(gegen=dict(d=100, lage="senkrecht"))
assert nah(sk.schnitt_x(qq, w, 30, 0), 0, 0.05) and sk.schnitt_x(qq, w, 0, 30) > 5       # senkrecht: Sattel quer
s30 = dict(gegen=dict(d=500, t=500, winkel=30))
assert nah(sk.schnitt_x(qq, s30, 30, 0), 0, 0.01) and nah(sk.schnitt_x(qq, s30, -30, 0), 60 * math.tan(math.radians(30)),
                                                          0.05)                        # schräg: + = vorne länger
ok("G2 Schnittkante: Sattel oben/unten am längsten, Lage senkrecht, schräg wie eine Gehrung")

# ------------------------------------------------------------------ G3 Durchbruch
z = sw.durchbruch_ergaenzen(dict(art=sw.DURCHBRUCH, anzahl=1, d=40, x=200, seite=90), RR)
assert nah(z["laenge_dd"], dd.durchbruch(dd.Querschnitt("rund", 60.3), dd.Querschnitt("rund", 40))["laenge"], 0.01)
assert nah(sw.kontur(z)[0], z["laenge_dd"]) and nah(z["huelle_dd"], 40, 0.01) and len(z["umriss"]) >= 100
xs = [p[0] for p in z["umriss"]]
assert nah(min(xs), -20, 0.1) and nah(max(xs), 20, 0.1)
z30 = sw.durchbruch_ergaenzen(dict(art=sw.DURCHBRUCH, anzahl=1, d=20, winkel=30, x=200), RR)
xs = [p[0] for p in z30["umriss"]]
assert (min(xs) + max(xs)) / 2 > 10                     # + Winkel: Gegenrohr zu Ende B geneigt, Loch dorthin
zf = sw.durchbruch_ergaenzen(dict(art=sw.DURCHBRUCH, anzahl=1, d=30, t=20, x=200, seite="oben"), QR)
assert nah(zf["laenge_dd"], 2 * (30 + 20), 0.01)        # flache Wand rechtwinklig: Umfang des Gegenrohrs
zu = sw.durchbruch_ergaenzen(dict(art=sw.DURCHBRUCH, anzahl=1, d=80, x=200, seite="oben"), QR)
assert "fehler_dd" in zu and "umriss" not in zu
try:
    sw.kontur(zu)
    raise AssertionError("zu breit")
except ValueError as f:
    assert str(f).startswith("Durchbruch: ")
r = sw.rechnen(sw.v_ergaenzen(dict(a={}, b={}, konturen=[dict(art=sw.DURCHBRUCH, anzahl=1, d=30, t=20, x=200,
                                                                 seite="oben", wand="beide",
                                                                 kopien=sk.umlauf(qq, dict(seite="oben",
                                                                                            wand="beide")))]), QR),
               QR, GRENZEN)
st = r["schritte"][2]
assert not r["fehler"] and st["anzahl"] == 2 and nah(st["laenge"], 200, 0.05) and "Gegenrohr 30 × 20" in st["text"]
ok("G3 Durchbruch: Länge wie durchdringung, Lage längs, schräg geneigt, flach = Umfang, beide Wände, Fehler")

# ------------------------------------------------------------------ G4 Lochfeld
lf = dict(art=sw.LOCHFELD, anzahl=4, d=8, reihen=3, teilung_q=12, abstand=20, x=100, seite="oben")
lg, hk, n = sw.kontur(lf)
assert n == 12 and nah(lg, math.pi * 8) and hk == 8
assert sk.lochfeld(lf)[:5] == [(0.0, -12.0), (20.0, -12.0), (40.0, -12.0), (60.0, -12.0), (0.0, 0.0)]
assert sk.lochfeld(dict(lf, versetzt=True))[4] == (10.0, 0.0)
lagen = sk.lagen([lf], 500, qq)
assert len(lagen) == 12 and {d["x"] for d in lagen} == {100}
mitten = sorted((round(sum(p[0] for p in pts) / len(pts), 1), round(sum(p[1] for p in pts) / len(pts), 1))
                for pts in (sk.platzieren(qq, d)[0] for d in lagen))
assert mitten[0] == (100.0, -12.0) and mitten[-1] == (160.0, 12.0), mitten[:3]
mittig = sk.lagen([dict(lf, x=None)], 500, qq)
assert {d["x"] for d in mittig} == {(500 - 60) / 2}         # ohne Lage: Feld mittig
lang = dict(lf, lang=20)
assert nah(sw.kontur(lang)[0], 2 * 12 + math.pi * 8) and sw.kontur(lang)[1] == 20
assert nah(max(p[0] for p in sk.umriss_kontur(dict(lang, reihen=1))), 10, 0.05)
for falsch, text in ((dict(lf, d=0), "Ø fehlt"), (dict(lf, teilung_q=None), "Teilung quer"),
                     (dict(lf, reihen=1.5), "ganze Zahl"), (dict(lf, abstand=None), "Teilung längs"),
                     (dict(lf, lang=5), "Langloch")):
    try:
        sw.kontur(falsch)
        raise AssertionError(falsch)
    except ValueError as f:
        assert text in str(f), (text, f)
r = sw.rechnen(dict(a={}, b={}, konturen=[dict(lf, versetzt=True)]), QR, GRENZEN)
assert r["felder"]["einstiche"] == 2 + 12 and "4 längs × 3 Reihen, Teilung 20 × 12, versetzt" in r["schritte"][2]["text"]
ok("G4 Lochfeld: 12 Löcher, Reihen quer um die Mitte, versetzt, mittig ohne Lage, Langlöcher, Fehler, Einstiche")

# ------------------------------------------------------------------ G5 Fase
re_ = dict(art=sw.RECHTECK, anzahl=1, b=40, h=20, fase=4)
assert nah(sw.kontur(re_)[0], 2 * 60 - 32 + 16 * math.sqrt(2), 1e-6)
assert len(sk.umriss_kontur(re_)) == 8 and nah(sk.umriss_kontur(re_)[0][0], -16)
ak = dict(art=sw.AUSKLINKUNG, anzahl=1, l=30, b=20, fase=3)
assert nah(sw.kontur(ak)[0], 2 * 27 + 14 + 6 * math.sqrt(2), 1e-6)
try:
    sw.kontur(dict(re_, fase=11))
    raise AssertionError("Fase zu groß")
except ValueError as f:
    assert "Fase" in str(f)
assert "Ecken gefast 4" in sw.rechnen(dict(a={}, b={}, konturen=[dict(re_, x=100)]), QR, GRENZEN)["schritte"][2]["text"]
ok("G5 Fase: Rechteck und Ausklinkung gefast (Länge, 8 Ecken), zu große Fase gemeldet")

# ------------------------------------------------------------------ G6 3D
from rohrlaser import gravur_text  # noqa: E402

e = sw.v_ergaenzen(dict(a=dict(gegen=dict(d=100, winkel=20)), b={}, konturen=[
    dict(lf, versetzt=True), dict(re_, x=300), dict(art=sw.DURCHBRUCH, anzahl=1, d=30, winkel=25, x=420, seite="vorne"),
    dict(art=sw.TEXT_GRAVUR, anzahl=1, hoehe=8, text="AB12", x=220)]), QR)
n3 = rohr3d.netz(e, QR, 560)
assert "HK" in n3["l"] and "ende:a" in n3["li"]["HK"] and "kontur:2" in n3["li"]["HK"]
assert n3["li"]["K"].count("kontur:0") == 12 and n3["li"]["G"].count("kontur:3") == len(gravur_text.linien("AB12", 8))
assert {"kontur:0", "kontur:1", "kontur:2"} <= set(n3["ti"]["K"])          # alle drei ausgeschnitten
hk = [n3["l"]["HK"][i] for i, m in enumerate(n3["li"]["HK"]) if m == "ende:a"]
zs = [z_ for zug in hk for z_ in zug[2::3]]
assert min(zs) < -20                                    # Gegenrohr liegt vor Ende A (außerhalb des Teils)
pk = [n3["l"]["HK"][i] for i, m in enumerate(n3["li"]["HK"]) if m == "kontur:2"]
xs = [c for zug in pk for c in zug[0::3]]
assert min(xs) < -60 and max(xs) > 30                   # Durchbruch vorne (−X) bis durch das Rohr
assert "HK" not in rohr3d.netz(dict(a={}, b={}, konturen=[]), QR, 300)["l"]
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import ansicht3d  # noqa: E402

app = QApplication.instance() or QApplication([])
assert "HK" in ansicht3d.REIHE and ansicht3d.LINIE["HK"].name() == "#e377c2"
a3 = ansicht3d.Ansicht3D()
a3.resize(600, 400)
a3.setzen(n3, "3E-7")
assert not a3.grab().toImage().isNull()
ok("G6 3D: Gegenrohr pink am Ende und am Durchbruch, Lochfeld/Rechteck/Durchbruch ausgeschnitten, Schrift graviert")

# ------------------------------------------------------------------ G7 Editor
from rohrlaser import editor_griffe, massbild  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.gegenrohr_dialog import GegenrohrDialog  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

gd = GegenrohrDialog(RR, None, "Ende A")
assert gd.ok.isEnabled() and set(gd.wert()) == {"d"} and gd.wert()["d"] > 60.3
gd.d.setValue(40)
assert not gd.ok.isEnabled() and "Gegenrohr" in gd.ergebnis.text()
gd.d.setValue(80)
gd.winkel.setValue(15)
gd.form.setCurrentText("rechteckig")
gd.t.setValue(60)
assert gd.wert() == dict(d=80, t=60, winkel=15) and "Schnittlänge" in gd.ergebnis.text()
for art in sw.ARTEN:
    assert not massbild.bild(art).isNull(), art

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
pid = "QR 40x40x3"
p = dict(profil_id=pid, werkstoff_id="S235-10219", laenge=500, stueck=10, technik=json.dumps(dict(
    a={}, b={}, konturen=[dict(art=sw.RECHTECK, anzahl=1, b=20, h=10, x=200)], quelle=sw.QUELLE)))
d = SchneidwegDialog(None, p, k.profile[pid], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed = d.editor
for text in ("Gegenrohr", "Lochfeld", "Ecken"):
    assert ed.band.knopf(text) is not None, text
d.gegenrohr("b", dict(d=60, winkel=10))
eing = d.eingaben()
assert eing["b"]["gegen"] == dict(d=60, winkel=10) and "Ø 60" in d.gegen_knopf["b"].text()
assert d.ergebnis["felder"]["b_gerade"] == "nein" and not d.ergebnis["fehler"]
from rohrlaser.teile_editor import ende_text  # noqa: E402

assert ende_text(eing["b"]) == "auf Gegenrohr Ø 60 schräg 10°"
d.winkel["b"].setValue(30)                              # Gehrung von Hand: Gegenrohr fällt weg
assert d.gegen["b"] is None and "gegen" not in d.eingaben()["b"]
d.gegenrohr("a", dict(d=60))
d.eingaben_setzen(eing, mit_messung=True)                # Laden (Rückgängig, Vorlage) setzt das Gegenrohr wieder
assert d.gegen["b"] == dict(d=60, winkel=10) and d.gegen["a"] is None
menue = editor_griffe.menue_bauen(ed, "ende:b")
texte = [a.text() for a in menue.actions()]
assert "Gegenrohr …" in texte and "Gegenrohr entfernen" in texte
menue = editor_griffe.menue_bauen(ed, "kontur:0")
ecken = next(a for a in menue.actions() if a.text() == "Ecken")
assert [a.text() for a in ecken.menu().actions()] == ["Runden …", "Fasen …", "Scharf"]
assert ed.ecken(0, "fasen", 3)
z0 = d.eingaben()["konturen"][0]
assert z0["fase"] == 3 and not z0.get("r") and "Ecken gefast 3" in d.ergebnis["schritte"][2]["text"]
assert ed.ecken(0, "runden", 2)
z0 = d.eingaben()["konturen"][0]
assert z0["r"] == 2 and "fase" not in z0
ed.waehlen("kontur:0")
ed.eigenschaften.zeigen("kontur:0")
assert "Fase je Ecke" in ed.eigenschaften.felder
ed.kontur_einfuegen(sw.LOCHFELD)
r_lf = d.tabelle.rowCount() - 1
z_lf = d.eingaben()["konturen"][r_lf]
assert z_lf["art"] == sw.LOCHFELD and z_lf["reihen"] == 2 and sw.kontur(z_lf)[2] == 10
ed.eigenschaften.zeigen(f"kontur:{r_lf}")
ed.eigenschaften.felder["versetzt"].setChecked(True)
assert d.eingaben()["konturen"][r_lf]["versetzt"] is True
ed.kontur_einfuegen(sw.DURCHBRUCH)
z_db = d.eingaben()["konturen"][-1]
assert z_db["art"] == sw.DURCHBRUCH and z_db["d"] == 20 and z_db["laenge_dd"] > 0
assert not d.ergebnis["fehler"], d.ergebnis["fehler"]
ok("G7 Editor: Gegenrohr-Dialog, Menüband, Rechtsklick, Ecken runden/fasen, Lochfeld versetzt, Durchbruch, Laden")
print("Alle Tests Gegenrohr, Lochfeld, Text, Fase (3E-7) bestanden.")
