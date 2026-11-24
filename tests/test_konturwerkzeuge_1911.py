"""Konturwerkzeuge (Patrick 19.11.2026, erweiterter Auftrag 3D-Editor, Priorität 1) mit Sollmaßen.

K1 Versatz (Offset): Bohrung, Langloch, Rechteck mit Radius, Polygon auf Gehrung – Schnittlänge = Sollwert
K2 Verlängern/Kürzen, Drehen, Richtung umkehren (Bogen bleibt Bogen, Länge gleich)
K3 Neue Formen: Ellipse 40 × 20 (Umfang wie Ramanujan, Hülle genau), Sechseck Umkreis 30
K4 Reihe mit verschiedenen Abständen, gleiche Konturen wählen, Rechnungen in Eingaben (sicher, kein eval)
K5 Im Teile-Editor (Rohr und Blech): Menü Bearbeiten auf markierte Zeilen, ein Schritt Rückgängig, STEP-Messung der
   übrigen Konturen bleibt
K6 Artikelnummer gravieren: Text aus dem Artikel, nur Schriftgröße, Lage automatisch mit 3 mm Sicherheitsabstand
   (Rohr und Blech), ersetzt die alte, meldet „kein Platz“

Aufruf: python tests/test_konturwerkzeuge_1911.py
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import editor_konturwerkzeuge as ekw, kontur_werkzeuge as kw, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.01):
    return abs(a - b) <= tol


def laenge(z):
    return sw.kontur(dict(z, anzahl=1))[0]


# ------------------------------------------------------------------ K1 Versatz
b = dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, gemessen=31.4, huelle_gemessen=10)
v = kw.versatz(b, 1)
assert v["d"] == 12 and "gemessen" not in v and nah(laenge(v), math.pi * 12), v
assert kw.versatz(b, -2)["d"] == 6
ll = dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10)
v = kw.versatz(ll, 1)
assert (v["l"], v["b"]) == (32, 12) and nah(laenge(v), 2 * (32 - 12) + math.pi * 12), (v, laenge(v))
re = dict(art=sw.RECHTECK, anzahl=1, b=40, h=20, r=3)
v = kw.versatz(re, 2)
assert (v["b"], v["h"], v["r"]) == (44, 24, 5), v
assert nah(laenge(v), 2 * (44 + 24) - 8 * 5 + 2 * math.pi * 5), laenge(v)
po = dict(art=sw.POLYGON, anzahl=1, punkte="0,0; 40,0; 40,20; 0,20")
v = kw.versatz(po, 1)
pk = sw.punkte(v["punkte"])
assert nah(laenge(v), 2 * (42 + 22)) and min(x for x, _ in pk) == -1 and max(y for _, y in pk) == 21, v
# Gegen den Uhrzeiger und im Uhrzeiger: außen bleibt außen
v2 = kw.versatz(dict(po, punkte="0,0; 0,20; 40,20; 40,0"), 1)
assert nah(laenge(v2), 2 * (42 + 22)), v2
for falsch, o in ((b, -5), (ll, -6), (dict(art=sw.GRAVUR, laenge=50), 1)):
    try:
        kw.versatz(falsch, o)
        raise AssertionError((falsch, o))
    except ValueError:
        pass
try:
    kw.versatz(po, -11)
    raise AssertionError("zu weit innen")
except ValueError as f:
    assert "verschwinden" in str(f) or "klein" in str(f), f
ok("K1 Versatz: Bohrung Ø10+1 = Ø12 (37,70), Langloch, Rechteck R3→R5, Polygon 40×20 → 42×22 (128), Grenzen")

# ------------------------------------------------------------------ K2 Verlängern, Drehen, Umkehren
v = kw.verlaengern(ll, 10)
assert v["l"] == 40 and nah(laenge(v), laenge(ll) + 20)
assert kw.verlaengern(dict(art=sw.SCHLITZ, l=20, b=5), -5)["l"] == 15
for falsch, dl in ((ll, -25), (b, 5)):
    try:
        kw.verlaengern(falsch, dl)
        raise AssertionError(falsch)
    except ValueError:
        pass
assert kw.drehen(re, 30)["drehung"] == 30 and kw.drehen(dict(re, drehung=350), 30)["drehung"] == 20
assert "drehung" not in kw.drehen(dict(re, drehung=270), 90)
try:
    kw.drehen(b, 45)
    raise AssertionError("Bohrung gedreht")
except ValueError:
    pass
bogen = dict(art=sw.POLYGON, anzahl=1, punkte="0,0; 40,0,0.4142; 40,20; 0,20")
u = kw.umkehren(bogen)
assert nah(laenge(u), laenge(bogen), 1e-6), (laenge(u), laenge(bogen))
assert kw.umkehren(u)["punkte"] == kw.umkehren(kw.umkehren(bogen))["punkte"]
assert sw.punkte_roh(kw.umkehren(u)["punkte"]) == sw.punkte_roh(bogen["punkte"])
assert kw.umkehren(dict(art=sw.SONDERKONTUR, umriss=[[0, 0], [1, 0], [1, 1]]))["umriss"] == [[1, 1], [1, 0], [0, 0]]
ok("K2 Verlängern/Kürzen (Langloch +10 = +20 Schnitt), Drehen (Bohrung nicht), Umkehren mit Bogen (Länge gleich)")

# ------------------------------------------------------------------ K3 Formen
e = kw.ellipse(40, 20, x=250)
pk = sw.punkte(e["punkte"])
assert e["art"] == sw.POLYGON and e["x"] == 250
assert nah(max(x for x, _ in pk) - min(x for x, _ in pk), 40, 1e-3) and nah(max(y for _, y in pk) -
                                                                           min(y for _, y in pk), 20, 1e-3)
assert nah(laenge(e), sw.ellipse(20, 10), 0.05), (laenge(e), sw.ellipse(20, 10))
s6 = kw.vieleck(6, 30)
assert len(sw.punkte(s6["punkte"])) == 6 and nah(laenge(s6), 6 * 15), laenge(s6)
for falsch in (lambda: kw.ellipse(0, 5), lambda: kw.vieleck(2, 10), lambda: kw.vieleck(5, 0)):
    try:
        falsch()
        raise AssertionError("Form")
    except ValueError:
        pass
ok("K3 Ellipse 40×20 (Umfang 96,88 wie Ramanujan, Hülle genau), Sechseck Umkreis 30 (Umfang 90)")

# ------------------------------------------------------------------ K4 Reihe, gleiche, Rechnungen
erste, neu = kw.reihe(dict(b, anzahl=3, abstand=20), [20, 35, 50])
assert erste["anzahl"] == 1 and "abstand" not in erste
assert [k["x"] for k in neu] == [120, 155, 205] and all("gemessen" not in k for k in neu)
assert kw.abstaende_lesen("20; 35,5; L/10", dict(L=500)) == [20, 35.5, 50]
for falsch in ("", "20; -3", "20; a"):
    try:
        kw.abstaende_lesen(falsch)
        raise AssertionError(falsch)
    except ValueError:
        pass
konturen = [b, dict(b, d=8), dict(b, x=300), ll, dict(b, seite="unten")]
assert kw.gleiche(konturen, 0, "art") == [0, 1, 2, 4] and kw.gleiche(konturen, 0, "masse") == [0, 2, 4]
assert kw.gleiche(konturen, 0, "seite") == [0, 1, 2, 3]
assert kw.zahl("L/2", dict(L=500)) == 250 and kw.zahl("3,5") == 3.5 and kw.zahl("") is None
for boese in ("__import__('os').system('x')", "open('a')", "(lambda: 1)()", "L.__class__"):
    try:
        kw.zahl(boese, dict(L=1))
        raise AssertionError(boese)
    except ValueError:
        pass
ok("K4 Reihe 20/35/50 ab x=100 → 120/155/205, gleiche Art/Maße/Seite, Rechnungen sicher (kein Programmcode)")

# ------------------------------------------------------------------ K5 im Teile-Editor
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
konturen = [dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, gemessen=31.5, huelle_gemessen=10),
            dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300)]
p = dict(id=9, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10,
         technik=json.dumps(dict(a={}, b={}, konturen=konturen, quelle=sw.QUELLE_STEP)))
d = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed = d.editor
d.tabelle.selectRow(1)
assert ed.markierte_zeilen() == [1]
vorher = d.eingaben()
assert ekw.verlaengern(ed, 10) == 1
e = d.eingaben()
assert e["konturen"][1]["l"] == 40 and e["konturen"][0] == vorher["konturen"][0], (vorher, e)
assert e["konturen"][0].get("gemessen") == 31.5 and {s: e[s] for s in ("a", "b")} == {s: vorher[s] for s in "ab"}
ed.verlauf.undo()
assert d.eingaben()["konturen"][1]["l"] == 30
ed.verlauf.redo()
assert d.eingaben()["konturen"][1]["l"] == 40
assert ekw.form_einfuegen(ed, "ellipse", [40, 20]) and d.tabelle.rowCount() == 3
assert d.eingaben()["konturen"][2]["art"] == sw.POLYGON
d.tabelle.selectRow(0)
assert ekw.reihe(ed, "20; 30") == 2 and [z["x"] for z in d.eingaben()["konturen"][3:]] == [120, 150]
assert ekw.gleiche_waehlen(ed, "masse") == [0, 3, 4]
assert ekw.versatz(ed, 1) == 3 and [z["d"] for z in d.eingaben()["konturen"] if z["art"] == sw.BOHRUNG] == [12] * 3
m = ekw.menue(ed)
texte = [a.text() for a in m.actions()]
assert "Versatz (Offset) …" in texte and "Ellipse einfügen …" in texte, texte
d.reject()
ok("K5 Rohr-Editor: Menü Bearbeiten auf markierte Zeilen, Rückgängig/Wiederholen, STEP-Messung der anderen bleibt")

from rohrlaser.blech_dialog import BlechDialog  # noqa: E402

bd = BlechDialog(None, db)
bd.kontur_neu(dict(art=sw.RECHTECK, anzahl=1, b=20, h=10, x=50, y=40))
bed = bd.editor
bd.tabelle.selectRow(0)
assert ekw.drehen(bed, 45) == 1 and bd.eingaben()["konturen"][0].get("drehung") == 45, bd.eingaben()["konturen"]
assert ekw.versatz(bed, 1) == 1 and (bd.eingaben()["konturen"][0]["b"], bd.eingaben()["konturen"][0]["h"]) == (22, 12)
assert ekw.reihe(bed, "30", "y") == 1 and bd.eingaben()["konturen"][1]["y"] == 70
bed.verlauf.undo()
assert len(bd.eingaben()["konturen"]) == 1
bd.reject()
ok("K5 Blech-Editor: Drehen, Versatz, Reihe in y, Rückgängig")
# ------------------------------------------------------------------ K6 Artikelnummer gravieren
from rohrlaser import gravur_text  # noqa: E402

assert db.einstellung("gravur_abstand") == 3.0
konturen = [dict(art=sw.BOHRUNG, anzahl=1, d=10, x=60), dict(art=sw.RECHTECK, anzahl=1, b=20, h=10, x=200)]
p = dict(id=11, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=300, stueck=10, artikel="A-4711",
         technik=json.dumps(dict(a={}, b={}, konturen=konturen, quelle=sw.QUELLE)))
d = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed = d.editor
assert ekw.artikel_gravieren(ed, 5)
g = [z for z in d.eingaben()["konturen"] if z["art"] == sw.TEXT_GRAVUR]
assert len(g) == 1 and g[0]["text"] == "A-4711" and g[0]["hoehe"] == 5 and g[0].get("artikel"), g
breite = gravur_text.masse("A-4711", 5)[0]
von, bis = g[0]["x"] - breite / 2, g[0]["x"] + breite / 2
assert von >= 65 + 3 - 1e-6 and bis <= 190 - 3 + 1e-6, (von, bis)       # zwischen Bohrung (bis 65) und Rechteck
assert ekw.artikel_gravieren(ed, 8)
g = [z for z in d.eingaben()["konturen"] if z["art"] == sw.TEXT_GRAVUR]
assert len(g) == 1 and g[0]["hoehe"] == 8, g                            # ersetzt, nicht doppelt
assert not ekw.artikel_gravieren(ed, 36)                                 # 36 + 2 × 3 > 40 mm Fläche: kein Platz
assert len([z for z in d.eingaben()["konturen"] if z["art"] == sw.TEXT_GRAVUR]) == 1
d.reject()
bd = BlechDialog(None, db)
bd.artikelnr.setText("B-12")
bd.kontur_neu(dict(art=sw.BOHRUNG, anzahl=1, d=10, x=50, y=40))
bed = bd.editor
assert ekw.artikel_gravieren(bed, 6)
g = [z for z in bd.eingaben()["konturen"] if z["art"] == sw.TEXT_GRAVUR]
assert len(g) == 1 and g[0]["text"] == "B-12" and g[0].get("artikel") and g[0].get("x") is not None, g
from rohrlaser import blech  # noqa: E402
e = bd.eingaben()
g = [z for z in e["konturen"] if z["art"] == sw.TEXT_GRAVUR]
frei = blech._gravur_frei(blech._gravur_hindernisse(e, g[0]), g[0]["x"], g[0]["y"], *blech.gravur_masse(g[0]))
assert frei is not None and frei >= 3 - 1e-6, frei
bd.reject()
ok("K6 Artikelnummer gravieren: Text aus dem Artikel, nur Schriftgröße, ≥ 3 mm Abstand (Rohr/Blech), ersetzt alte")
print("Alle Prüfungen bestanden.")
