"""DXF-Import im Blech-Editor (Schritt 3E-9, Plan kalkulation/3d-editor/Plan_DXF-Import_Blech.md, Freigabe Patrick
24.10.2026 „Alle a“ + genaue Kontur):
- X1 Polygon mit Bögen: Bulge im Feld Eckpunkte, Länge und Fläche wie der echte Bogen, DXF-Export mit echten Bögen.
- X2 Rundreise mit dem eigenen DXF-Export: Rechteck, Bohrung, Langloch (gedreht), Rechteck mit Radius, Rechteck 90°,
  Polygon an derselben Stelle; Text-Gravur wird Gravurlinien.
- X3 Lesen: LWPOLYLINE mit Bögen, Blöcke (auch skaliert), ausgeblendeter Layer, Mittellinie, offene Linie, MTEXT auf
  Gravur-Layer, Einheit; Werkstoff und Dicke aus Dateiname und Texten.
- X4 Kantteil: Biegelinien hoch/runter -> Schenkel, Abwicklung wie vorher.
- X5 Zeichenblatt: Rahmen und Schriftfeld fallen weg, Maßstab aus Schriftfeld bzw. Bemaßung, mehrere Teile,
  Kästchen mit Text nicht angehakt.
- X6 Oberfläche: Importfenster (je Teil Werkstoff/Dicke/Stückzahl, Maßstab neu einlesen), Blech-Editor „DXF
  importieren“, Angebot: Bleche aus DXF = je Teil eine Position; Ziehen einer DXF-Datei.

Aufruf: python tests/test_dxf_import.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import blech, dxf, dxf_import as di, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.01):
    return abs(a - b) <= tol


def g(*paare):
    return "\n".join(f"{c}\n{v}" for c, v in paare)


def datei(*entitaeten, kopf=(), bloecke=()):
    teile = []
    if kopf:
        teile.append(g((0, "SECTION"), (2, "HEADER"), *kopf, (0, "ENDSEC")))
    if bloecke:
        teile.append(g((0, "SECTION"), (2, "BLOCKS"), *bloecke, (0, "ENDSEC")))
    teile.append(g((0, "SECTION"), (2, "ENTITIES"), *[p for e in entitaeten for p in e], (0, "ENDSEC"), (0, "EOF")))
    return "\n".join(teile)


def lw(pk, layer="0", bulges=None):
    out = [(0, "LWPOLYLINE"), (8, layer), (90, len(pk)), (70, 1)]
    for i, (x, y) in enumerate(pk):
        out += [(10, x), (20, y)] + ([(42, bulges[i])] if bulges and bulges[i] else [])
    return out


def linie(a, b, layer="0", typ=None):
    return [(0, "LINE"), (8, layer)] + ([(6, typ)] if typ else []) + [(10, a[0]), (20, a[1]), (11, b[0]), (21, b[1])]


def text(p, t, h=3.5, layer="0"):
    return [(0, "TEXT"), (8, layer), (10, p[0]), (20, p[1]), (40, h), (1, t)]


def kreis(c, r, layer="0"):
    return [(0, "CIRCLE"), (8, layer), (10, c[0]), (20, c[1]), (40, r)]


# ------------------------------------------------------------------ X1 Polygon mit Bögen
roh = sw.punkte_roh("0,0; 100,0,1; 100,50; 0,50")
assert roh[1] == (100.0, 0.0, 1.0) and len(roh) == 4
pk = sw.punkte("0,0; 100,0,1; 100,50; 0,50")
assert len(pk) > 20 and max(x for x, _ in pk) > 124.99
e = dict(art=blech.ZUSCHNITT, form=blech.POLYGON, punkte="0,0; 100,0,1; 100,50; 0,50", dicke=2, konturen=[])
zs = blech.zuschnitt(e)
assert nah(zs["aussen"], 200 + 50 + math.pi * 25, 0.05) and nah(zs["flaeche"], 5000 + math.pi * 625 / 2, 2)
assert nah(zs["laenge"], 125, 0.001) and nah(zs["breite"], 50)
elem, _ = dxf.elemente(e, zs)
boegen = [x for x in elem if x[0] == "ARC"]
assert len(boegen) == 1 and nah(boegen[0][3], 25) and len([x for x in elem if x[0] == "LINE"]) == 3
assert sw.kontur(dict(art=sw.POLYGON, anzahl=1, punkte="0,0,1; 10,0,1"))[0] > 31.4
ok("X1 Polygon mit Bögen (Bulge): Schnittlänge und Fläche wie echter Bogen, DXF-Export mit echtem Bogen")

# ------------------------------------------------------------------ X2 Rundreise
e = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100,
         konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=30, y=30),
                   dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=100, y=50, drehung=30),
                   dict(art=sw.RECHTECK, anzahl=1, b=20, h=10, r=2, x=160, y=70),
                   dict(art=sw.RECHTECK, anzahl=1, b=20, h=10, r=0, x=160, y=20, drehung=90),
                   dict(art=sw.POLYGON, anzahl=1, punkte="0,0; 20,0; 10,15", x=60, y=75),
                   dict(art=sw.TEXT_GRAVUR, anzahl=1, text="AB", hoehe=8, x=130, y=85, winkel=0)])
elem, _ = dxf.elemente(e, blech.zuschnitt(e), beschriftung="Halter")
r = di.importieren(dxf.schreiben(elem), "Halter_3mm_1.4301.dxf")
assert len(r["teile"]) == 1 and r["dicke"] == 3
t = r["teile"][0]["e"]
assert (t["form"], t["laenge"], t["breite"]) == (blech.RECHTECK, 200, 100)
k = {z["art"] + str(z.get("drehung", "")) + str(z.get("r", "")): z for z in t["konturen"]}
assert k["Bohrung"]["d"] == 10 and (k["Bohrung"]["x"], k["Bohrung"]["y"]) == (30, 30)
ll = k["Langloch30.0"]
assert (ll["l"], ll["b"], ll["x"], ll["y"]) == (30, 10, 100, 50)
assert (k["Rechteck2.0"]["b"], k["Rechteck2.0"]["h"]) == (20, 10)
assert (k["Rechteck0"]["b"], k["Rechteck0"]["h"], k["Rechteck0"]["x"]) == (10, 20, 160)
poly = k["Polygon"]
assert (poly["x"], poly["y"]) == (60, 75)
assert k["Gravur"]["laenge"] > 20 and k["Gravur"]["linien"]
# gleiche Lage nach dem Import: dieselben DXF-Elemente der Innenkonturen (bis auf Rundung)
elem2, _ = dxf.elemente(dict(t, dicke=3), blech.zuschnitt(dict(t, dicke=3)))
assert nah(dxf.schnittlaenge(elem2)[dxf.INNEN], dxf.schnittlaenge(elem)[dxf.INNEN], 0.05)
ok("X2 Rundreise eigener DXF-Export: Bohrung, Langloch gedreht, Rechteck mit Radius / 90°, Polygon, Gravur")

# ------------------------------------------------------------------ X3 Lesen
werkstoffe = {"S235JR": {}, "1.4301 2B": {}, "1.4301 K240": {}, "AlMg3": {}, "DC01": {}}
assert di.werkstoff_aus(["Halter_3mm_1.4301.dxf"], werkstoffe) == "1.4301 2B"
assert di.werkstoff_aus(["Werkstoff: S235", "x"], werkstoffe) == "S235JR"
assert di.werkstoff_aus(["Blech V2A"], werkstoffe) == "1.4301 2B" and di.werkstoff_aus(["Alu 2mm"], werkstoffe) == "AlMg3"
assert di.werkstoff_aus(["Pos 3"], werkstoffe) is None
assert di.dicke_aus(["Halter_3mm.dxf"]) == 3 and di.dicke_aus(["t=2,5"]) == 2.5 and di.dicke_aus(["Dicke: 4"]) == 4
assert di.dicke_aus(["Pos 3", "Zeichn.-Nr. 4711"]) is None
t = datei(lw([(0, 0), (100, 0), (100, 50), (0, 50)], "KONTUR", [0, 1, 0, 0]),
          [(0, "INSERT"), (8, "KONTUR"), (2, "LOCH"), (10, 20), (20, 20)],
          [(0, "INSERT"), (8, "KONTUR"), (2, "LOCH"), (10, 40), (20, 20), (41, 2), (42, 2)],
          kreis((60, 20), 3, "AUS"), linie((0, 25), (100, 25), "MITTE", "CENTER"), linie((70, 10), (80, 10), "KONTUR"),
          [(0, "MTEXT"), (8, "GRAVUR"), (10, 10), (20, 45), (40, 5), (1, "Nr 7")],
          kopf=((9, "$INSUNITS"), (70, 4)),
          bloecke=((0, "BLOCK"), (8, "0"), (2, "LOCH"), (10, 0), (20, 0), (0, "CIRCLE"), (8, "0"), (10, 0), (20, 0),
                   (40, 3), (0, "ENDBLK")))
t = g((0, "SECTION"), (2, "TABLES"), (0, "TABLE"), (2, "LAYER"), (0, "LAYER"), (2, "AUS"), (70, 0), (62, -7),
      (0, "ENDTAB"), (0, "ENDSEC")) + "\n" + t
r = di.importieren(t, "x.dxf")
t1 = r["teile"][0]
e = t1["e"]
assert e["form"] == blech.POLYGON and e["punkte"] == "0,0; 100,0,1; 100,50; 0,50" and nah(e["laenge"], 125)
arten = sorted((z["art"], z.get("d")) for z in e["konturen"])
assert arten == [(sw.BOHRUNG, 6), (sw.BOHRUNG, 12), (sw.TEXT_GRAVUR, None), (sw.SONSTIGE, None)], arten
tg = next(z for z in e["konturen"] if z["art"] == sw.TEXT_GRAVUR)
assert tg["text"] == "Nr 7" and tg["hoehe"] == 5 and nah(tg["y"], 42.5)
assert any("offene Schnittlinie" in w for w in t1["warnungen"])
try:
    di.importieren(datei(linie((0, 0), (10, 0))), "leer.dxf")
    raise AssertionError("DxfFehler erwartet")
except di.DxfFehler:
    pass
zoll = di.importieren(datei(lw([(0, 0), (2, 0), (2, 1), (0, 1)]), kopf=((9, "$INSUNITS"), (70, 1))), "z.dxf")
assert nah(zoll["teile"][0]["e"]["laenge"], 50.8)
ok("X3 Lesen: Bögen, Blöcke (skaliert), ausgeblendeter Layer, Mittellinie, offene Linie, MTEXT-Gravur, Zoll; "
   "Werkstoff/Dicke aus Namen und Texten")

# ------------------------------------------------------------------ X4 Kantteil
e = dict(art=blech.KANTTEIL, form=blech.RECHTECK, dicke=2, kantlaenge=300,
         schenkel=[dict(laenge=40, winkel=90), dict(laenge=80, winkel=-90), dict(laenge=30, winkel=0)],
         konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=8, x=150, y=60)])
zs = blech.zuschnitt(e)
elem, _ = dxf.elemente(e, zs)
r = di.importieren(dxf.schreiben(elem), "k.dxf")
t = r["teile"][0]
assert [a for _, a in t["biegelinien"]] == ["biegung", "runter"]
assert [b["winkel"] for b in t["e"]["biegelinien_dxf"]] == [90, -90]
kt = di.als_kantteil(t["e"], [90, -90], 2)
assert kt["art"] == blech.KANTTEIL and [x["laenge"] for x in kt["schenkel"]] == [40, 80, 30] and kt["kantlaenge"] == 300
assert nah(blech.zuschnitt(kt)["breite"], zs["breite"], 0.001)
ok("X4 Kantteil aus Biegelinien (hoch/runter): Schenkel 40/80/30, Abwicklung wie vorher")

# ------------------------------------------------------------------ X5 Zeichenblatt
blatt = datei(lw([(10, 10), (410, 10), (410, 287), (10, 287)]),
              linie((230, 10), (230, 50)), linie((230, 50), (410, 50)), linie((230, 30), (410, 30)),
              linie((320, 10), (320, 50)),
              text((235, 40), "Halter"), text((235, 20), "M 1:2"), text((325, 40), "S235JR t=4"),
              text((325, 20), "Zeichn.-Nr. 4711"),
              lw([(30, 200), (130, 200), (130, 250), (30, 250)]), kreis((50, 225), 5), kreis((110, 225), 5),
              lw([(150, 200), (200, 200), (200, 260), (150, 260)]),
              lw([(30, 100), (80, 100), (80, 120), (30, 120)]), text((35, 105), "Pos 3"))
r = di.importieren(blatt, "blatt.dxf")
assert r["rahmen"] == 1 and r["massstab"] == 2 and r["massstab_quelle"] == "Schriftfeld" and r["dicke"] == 4
assert [(t["aktiv"], t["e"]["laenge"], t["e"]["breite"]) for t in r["teile"]] == \
    [(True, 100, 120), (True, 200, 100), (False, 100, 40)]
assert len(r["teile"][1]["e"]["konturen"]) == 2 and r["teile"][1]["e"]["konturen"][0]["d"] == 20
r1 = di.importieren(blatt, "blatt.dxf", massstab=1)
assert r1["teile"][1]["e"]["laenge"] == 100
bem = datei(lw([(0, 0), (50, 0), (50, 20), (0, 20)]),
            [(0, "DIMENSION"), (8, "BEM"), (70, 1), (13, 0), (23, 0), (14, 50), (24, 0), (42, 250)])
assert di.importieren(bem, "b.dxf")["massstab"] == 5
ok("X5 Zeichenblatt: Rahmen und Schriftfeld weg, Maßstab 1:2 aus Schriftfeld / 1:5 aus Bemaßung, mehrere Teile, "
   "Kästchen mit Text nicht angehakt")

# ------------------------------------------------------------------ X6 Oberfläche
from rohrlaser.dxf_import_dialog import DxfImportDialog, massstab_text, massstab_wert  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.neue_position import DXF  # noqa: E402

assert massstab_text(2) == "1:2" and massstab_text(0.5) == "2:1" and massstab_wert("1:2,5") == 2.5
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
pfad = tmp / "Blatt_1.4301.dxf"
pfad.write_text(blatt, encoding="utf-8")
d = DxfImportDialog(None, db, str(pfad))
assert d.fehler is None and d.liste.count() == 3 and len(d.gewaehlt()) == 2
assert d.werkstoff.currentText() == "1.4301 2B" and d.dicke.value() == 4
assert not d.liste.item(0).icon().isNull()
d.liste.setCurrentRow(1)
d.stueck.setValue(5)
d.dicke.setValue(3)
erg = d.ergebnisse()
assert [(e["laenge"], e["dicke"], kopf["stueck"]) for e, kopf in erg] == [(100, 4, 1), (200, 3, 5)]
assert erg[0][0]["werkstoff"] == "1.4301 2B" and erg[0][1]["bezeichnung"] == "Blatt_1.4301 Teil 1"
d.massstab.setCurrentText("1:1")
assert d.erg["teile"][1]["e"]["laenge"] == 100
d.accept()
assert db.einstellung("dxf_import_dicke") == 4
fehlt = DxfImportDialog(None, db, str(tmp / "gibt_es_nicht.dxf"))
assert fehlt.fehler

# Blech-Editor: DXF importieren
kpfad = tmp / "kant.dxf"
kpfad.write_text(dxf.schreiben(dxf.elemente(dict(art=blech.KANTTEIL, form=blech.RECHTECK, dicke=2, kantlaenge=300,
                                                 schenkel=[dict(laenge=40, winkel=90), dict(laenge=80, winkel=-90),
                                                           dict(laenge=30, winkel=0)], konturen=[]),
                                            zs)[0]), encoding="utf-8")
b = BlechDialog(None, db, dict(dicke=2, werkstoff="S235JR"))
assert b.editor.band.knopf("DXF importieren") is not None


def kant_ok(d):
    assert d.kant.isVisible() is False or d.kant.isChecked()
    assert d.dicke.value() == 2 and d.werkstoff.currentText() == "S235JR"     # Vorgabe aus dem Editor
    return QDialog.Accepted


assert b.dxf_importieren(str(kpfad), dialog=kant_ok)
ein = b.eingaben()
assert ein["art"] == blech.KANTTEIL and [x["laenge"] for x in ein["schenkel"]] == [40, 80, 30]
assert b.ergebnis.get("richtpreis") and not b.ergebnis["fehler"]
b2 = BlechDialog(None, db, dict(dicke=3, werkstoff="S235JR"))
rpfad = tmp / "rund.dxf"
rpfad.write_text(datei(lw([(0, 0), (100, 0), (100, 50), (0, 50)], "0", [0, 1, 0, 0]), kreis((30, 25), 4)),
                 encoding="utf-8")
assert b2.dxf_importieren(str(rpfad), dialog=lambda d: QDialog.Accepted)
assert b2.eingaben()["form"] == blech.POLYGON and b2.skizze.boegen()
b2.skizze.resize(600, 400)
b2.skizze.grab()
assert "Bögen in Eckpunkte umwandeln" in [a.text() for a in b2.skizze.menue(b2.skizze.rect().center()).actions()]
b2.skizze.boegen_aufloesen()
assert not b2.skizze.boegen()

# Angebot: Bleche aus DXF (je Teil eine Position) und Ziehen
a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
vorher = len(db.positionen(a))
assert s.blech_aus_dxf([str(pfad)], dialog=lambda d: QDialog.Accepted) == 2
pos = db.positionen(a)[vorher:]
assert len(pos) == 2 and all(blech.lesen(p["technik"])["dxf"] for p in pos)
assert pos[0]["bezeichnung"] == "Blatt_1.4301 Teil 1"
aufrufe = []
s.blech_aus_dxf, alt = (lambda pfade=None, dialog=None: aufrufe.append(pfade) or 1), s.blech_aus_dxf
assert s.position_neu(DXF) == DXF and aufrufe == [None]
s.blech_aus_dxf = alt
assert s._dxf_pfade(["a.DXF", "b.step", "c.dxf"]) == ["a.DXF", "c.dxf"]
ok("X6 Importfenster (je Teil Werkstoff/Dicke/Stückzahl, Maßstab), Blech-Editor DXF importieren (Kantteil, Bögen), "
   "Angebot: Bleche aus DXF je Teil eine Position")
print("Alle Tests DXF-Import bestanden.")
