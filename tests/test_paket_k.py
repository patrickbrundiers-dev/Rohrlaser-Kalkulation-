"""Paket K aus dem PROfirst-Plan (Patrick 12.11.2026 „alles umsetzten“, im STEP-Import-Thread als Paket K):
K1 Bohren, Gewinde, Senken aus Layer oder Farbe der DXF.
K2 Kontur aus Scan oder Raster-PDF nachzeichnen (Linienzeichnung und gefülltes Teil, Maßstab aus der Breite).
K3 Rohr auf Rohr ohne STEP: Gegenrohr mit Schweißspalt und Kontakt innen/außen; Werkzeug aus importiertem Körper.
K4 Rohrzug aus XYZ-Punkten: gerade Rohre mit Gehrungen, als Schweißbaugruppe.
K5 Export mit Bögen statt Kurven (dichte Punktfolgen als ARC, 0,01 mm genau), dazu STL aus dem 3D-Modell.

Aufruf: python tests/test_paket_k.py
"""
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import bohrbild, dxf_import as di  # noqa: E402


def ok(t):
    print("OK    ", t)


def g(*paare):
    return "\n".join(f"{c}\n{v}" for c, v in paare)


def datei(*entitaeten, tabellen=()):
    teile = []
    if tabellen:
        teile.append(g((0, "SECTION"), (2, "TABLES"), *tabellen, (0, "ENDSEC")))
    teile.append(g((0, "SECTION"), (2, "ENTITIES"), *[p for e in entitaeten for p in e], (0, "ENDSEC"), (0, "EOF")))
    return "\n".join(teile)


def lw(pk, layer="0", farbe=None):
    out = [(0, "LWPOLYLINE"), (8, layer)] + ([(62, farbe)] if farbe else []) + [(90, len(pk)), (70, 1)]
    for x, y in pk:
        out += [(10, x), (20, y)]
    return out


def kreis(c, r, layer="0", farbe=None):
    return [(0, "CIRCLE"), (8, layer)] + ([(62, farbe)] if farbe else []) + [(10, c[0]), (20, c[1]), (40, r)]


# ------------------------------------------------------------------ K1
LAYER = ((0, "TABLE"), (2, "LAYER"), (0, "LAYER"), (2, "SENKER"), (70, 0), (62, 6), (0, "ENDTAB"))
text = datei(lw([(0, 0), (200, 0), (200, 100), (0, 100)]),
             kreis((20, 20), 3.4, farbe=1),                 # Farbe 1 am Element
             kreis((50, 20), 4, "GEWINDE_M8"),              # Layername
             kreis((80, 20), 5, "SENKER"),                  # Farbe 6 vom Layer („VonLayer“)
             kreis((110, 20), 6),                           # ohne: nur lasern
             kreis((140, 20), 4, "BOHRUNGEN"),              # „BOHRUNG“ ist kein Bearbeitungs-Layer
             lw([(160, 15), (170, 15), (170, 25), (160, 25)], farbe=1),     # Rechteck in Farbe 1: bleibt Rechteck
             tabellen=LAYER)
farben = di.farben_aus(lambda n: {"dxf_farbe_gewinde": 1, "dxf_farbe_senkung": 6, "dxf_farbe_bohren": 0}.get(n))
assert farben == {1: bohrbild.GEWINDE_SCHNEIDEN, 6: bohrbild.SENKEN}, farben
t = di.importieren(text, "k1.dxf", farben=farben)["teile"][0]
aus = {k["x"]: k.get("aus") for k in t["e"]["konturen"]}
assert aus == {20.0: bohrbild.GEWINDE_SCHNEIDEN, 50.0: bohrbild.GEWINDE_SCHNEIDEN, 80.0: bohrbild.SENKEN, 110.0: None,
               140.0: None, 165.0: None}, aus
assert "davon 3 mit Bearbeitung aus Layer/Farbe" in t["zusammenfassung"], t["zusammenfassung"]
assert all(a in bohrbild.AUSFUEHRUNGEN for a in aus.values() if a)
ohne = di.importieren(text, "k1.dxf")["teile"][0]
assert {k["x"]: k.get("aus") for k in ohne["e"]["konturen"]}[20.0] is None          # Farben ohne Einstellung: aus
assert {k["x"]: k.get("aus") for k in ohne["e"]["konturen"]}[50.0] == bohrbild.GEWINDE_SCHNEIDEN
assert di.farben_aus(lambda n: None) == {}
ok("K1 DXF: Farbe am Element und vom Layer, Layername GEWINDE -> Ausführung; BOHRUNGEN und Rechteck bleiben; "
   "ohne Einstellung keine Farbe")

# ------------------------------------------------------------------ K5 Bögen statt Kurven
import math  # noqa: E402
import tempfile  # noqa: E402

from rohrlaser import blech, blech3d, dxf, rohr3d, schneidweg as sw, stl_export  # noqa: E402

# Langloch-ähnliche Kontur aus einer Spline (dichte Punkte): zwei Halbkreise R 10 und zwei Geraden
pk = [(40 + 10 * math.cos(math.radians(a)), 10 * math.sin(math.radians(a))) for a in range(-90, 91, 3)]
pk += [(10 * math.cos(math.radians(a)), 10 * math.sin(math.radians(a))) for a in range(90, 271, 3)]
el = dxf._polygon(dxf.INNEN, pk)
neu = dxf.boegen(el)
arten = [x[0] for x in neu]
assert arten.count("ARC") == 2 and arten.count("LINE") == 2, arten
for x in neu:
    if x[0] == "ARC":
        assert abs(x[3] - 10) <= 0.01, x
for q in pk:                # jeder alte Punkt liegt auf einem neuen Element (höchstens 0,01 mm)
    best = min((abs(math.dist(q, x[2]) - x[3]) if x[0] == "ARC" else
                abs((x[3][0] - x[2][0]) * (x[2][1] - q[1]) - (x[2][0] - q[0]) * (x[3][1] - x[2][1]))
                / math.dist(x[2], x[3])) for x in neu)
    assert best <= dxf.BOGEN_TOLERANZ + 1e-9, (q, best)
assert abs(sum(map(dxf.laenge, neu)) - (2 * math.pi * 10 + 80)) <= 0.05, sum(map(dxf.laenge, neu))
ring = [(120 + 25 * math.cos(math.radians(a)), 40 + 25 * math.sin(math.radians(a))) for a in range(0, 360, 5)]
kr = dxf.boegen(dxf._polygon(dxf.INNEN, ring))
assert [x[0] for x in kr] == ["CIRCLE"] and abs(kr[0][3] - 25) <= 0.01, kr      # Kreis aus 72 Stücken: ein Kreis
ecken = dxf._polygon(dxf.AUSSEN, [(0, 0), (100, 0), (100, 50), (0, 50)])
assert dxf.boegen(ecken) == ecken                       # Rechteck bleibt vier Linien
gerade = [dxf._linie(dxf.AUSSEN, (i, 0), (i + 1, 0)) for i in range(10)]
assert [x[0] for x in dxf.boegen(gerade)] == ["LINE"] * 10      # gerade Punktfolge wird kein Bogen
zick = [(i * 2.0, (i % 2) * 1.0) for i in range(8)]
assert all(x[0] == "LINE" for x in dxf.boegen(dxf._polygon(dxf.INNEN, zick)))    # Zickzack: keine Bögen
tmp = Path(tempfile.mkdtemp())
dxf.speichern(tmp / "k5.dxf", el)
zurueck = dxf.lesen((tmp / "k5.dxf").read_text(encoding="cp1252"))
assert sum(1 for x in zurueck if x[0] == "ARC") == 2, [x[0] for x in zurueck]
dxf.speichern(tmp / "k5_roh.dxf", el, mit_boegen=False)
assert not any(x[0] == "ARC" for x in dxf.lesen((tmp / "k5_roh.dxf").read_text(encoding="cp1252")))
ok("K5 DXF: Spline-Langloch (122 Stücke) -> 2 Bögen R 10 + 2 Linien, jeder Punkt <= 0,01 mm; Kreis aus 72 Stücken -> CIRCLE; Ecken, Geraden und "
   "Zickzack bleiben Linien")

# ------------------------------------------------------------------ K5 STL
QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
n = rohr3d.netz(dict(a={}, b={}, konturen=[]), QR, 500)
tri = stl_export.dreiecke(n, "rohr")
xs = [q[0] for t_ in tri for q in t_]
assert abs(min(xs)) <= 0.01 and abs(max(xs) - 500) <= 0.01            # X längs der Rohrachse, 0 bis 500 mm
v = stl_export.volumen(tri)
assert 200000 < v < 222000, v           # 40×40×3 mit Außenradius: knapp unter (40² - 34²) · 500 = 222000 mm³
n2 = rohr3d.netz(dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100)]), QR, 500)
v2 = stl_export.volumen(stl_export.dreiecke(n2, "rohr"))
assert abs((v - v2) - math.pi * 25 * 3) <= 3, v - v2         # Bohrung Ø 10 durch 3 mm Wand
e = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100,
         konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=8, x=50, y=30)])
tb = stl_export.dreiecke(blech3d.netz(e, blech.zuschnitt(e)), "blech")
assert abs(stl_export.volumen(tb) - (200 * 100 * 3 - math.pi * 16 * 3)) <= 5, stl_export.volumen(tb)
assert max(q[0] for t_ in tb for q in t_) - min(q[0] for t_ in tb for q in t_) == 200
assert stl_export.speichern(tmp / "r.stl", n, "rohr", "Pos 10") == len(tri)
roh = (tmp / "r.stl").read_bytes()
assert len(roh) == 84 + 50 * len(tri) and roh.startswith(b"Rohrlaser-Kalkulation Pos 10")
assert abs(stl_export.volumen(stl_export.lesen(roh)) - v) <= 1
hilfe = dict(n, t=dict(n["t"], HK=n["t"]["A"], WB=n["t"]["A"]))
assert len(stl_export.dreiecke(hilfe, "rohr")) == len(tri)       # Hilfs- und Schnittkörper nicht in der STL
assert stl_export.speichern(tmp / "leer.stl", None) == 0 and not (tmp / "leer.stl").exists()
ok("K5 STL: Rohr X 0-500 mm, Volumen geschlossen und positiv, Bohrung Ø 10 zieht 236 mm³ ab, Blech mit Bohrung; "
   "Hilfskörper fehlen, Datei liest sich zurück")

# ------------------------------------------------------------------ K5 Knöpfe in allen Editoren
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import baugruppe_step  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
nr = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(nr, dict(pos=10, artikel="K5-1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=300,
                         stueck=10))
seite = fenster.angebot_oeffnen(nr)
d = SchneidwegDialog(seite, seite.positionen[0], seite.k.profile["QR 40x40x3"], seite.kopf, seite.k, seite.tabellen)
d.show()
app.processEvents()
assert d.editor.band.knopf("STL speichern") is not None
assert d.editor.stl_speichern(str(tmp / "rohr.stl")) == str(tmp / "rohr.stl")
tr = stl_export.lesen((tmp / "rohr.stl").read_bytes())
assert abs(max(q[0] for t_ in tr for q in t_) - min(q[0] for t_ in tr for q in t_) - 300) <= 0.01
d.close()
werkstoff = sorted(z_["blech_werkstoff_id"] for z_ in db.zeilen("blech_werkstoffe"))[0]
dlg = BlechDialog(None, db, dict(e, werkstoff=werkstoff))
dlg.show()
app.processEvents()
assert dlg.editor.band.knopf("STL speichern") is not None
assert dlg.editor.stl_speichern(str(tmp / "blech.stl"))
assert abs(stl_export.volumen(stl_export.lesen((tmp / "blech.stl").read_bytes())) - stl_export.volumen(tb)) <= 1
dlg.close()


class _Bg(baugruppe_step.StepBaugruppe):        # Baugruppe/Satz in 3D: gemeinsamer Knopf und gemeinsames Speichern
    stumm = True

    def __init__(self, netz):
        self.ansicht3d = type("A", (), {"ansicht": type("N", (), {"netz": netz})()})()

    def step_name(self):
        return "BG 1"


bg_netz = dict(p=n["p"], t={"F0": n["t"]["A"] + n["t"]["I"], "SN": n["t"]["A"]})
assert _Bg(bg_netz).stl_speichern(str(tmp / "bg.stl"))
assert len(stl_export.lesen((tmp / "bg.stl").read_bytes())) == (len(n["t"]["A"]) + len(n["t"]["I"])) // 3
assert "STL" in _Bg(bg_netz).stl_knopf().text()

# ------------------------------------------------------------------ K2 Nachzeichnen
from PIL import Image, ImageDraw  # noqa: E402

from rohrlaser import nachzeichnen as nz, nachzeichnen_dialog as nzd  # noqa: E402


def scan(gefuellt, dpi=None):
    """Platte 300 × 150 mm (2 Pixel je mm), Ecken R 10, Loch Ø 40 bei (80, 75), Langloch 60 × 20 bei (200, 75);
    Linien 4 Pixel breit, daneben ein Schriftfeld (fällt weg)."""
    b = Image.new("L", (800, 520), 255)
    d_ = ImageDraw.Draw(b)
    ox, oy = 100, 100
    if gefuellt:
        d_.rounded_rectangle((ox, oy, ox + 600, oy + 300), radius=20, fill=0)
        d_.ellipse((ox + 120, oy + 110, ox + 200, oy + 190), fill=255)
        d_.rounded_rectangle((ox + 340, oy + 130, ox + 460, oy + 170), radius=20, fill=255)
    else:
        d_.rounded_rectangle((ox - 2, oy - 2, ox + 602, oy + 302), radius=22, outline=0, width=4)
        d_.ellipse((ox + 118, oy + 108, ox + 202, oy + 192), outline=0, width=4)
        d_.rounded_rectangle((ox + 338, oy + 128, ox + 462, oy + 172), radius=22, outline=0, width=4)
        d_.text((ox, oy + 340), "Zeichnung 4711  M 1:1", fill=0)
    pfad = tmp / f"scan_{int(gefuellt)}.png"
    b.save(pfad, dpi=dpi) if dpi else b.save(pfad)
    return pfad


for gefuellt in (False, True):
    bild_, mm_bild, _ = nz.laden(scan(gefuellt))
    erg = nz.nachzeichnen(bild_)
    assert erg["art"] == (nz.FLAECHE if gefuellt else nz.LINIEN) and len(erg["zuege"]) == 3, erg["art"]
    assert gefuellt or erg["strich"] == 4, erg["strich"]
    e_b, zus = nz.teil(erg, nz.mm_je_pixel(erg, 300))
    assert abs(e_b["laenge"] - 300) <= 1.0 and abs(e_b["breite"] - 150) <= 1.5, (e_b["laenge"], e_b["breite"])
    boh = [k for k in e_b["konturen"] if k["art"] == sw.BOHRUNG]
    assert len(boh) == 1 and abs(boh[0]["d"] - 40) <= 1.5 and abs(boh[0]["x"] - 80) <= 1.5, boh
    assert abs(boh[0]["y"] - 75) <= 1.5, boh
    lang = [k for k in e_b["konturen"] if k["art"] != sw.BOHRUNG]
    assert len(lang) == 1 and abs(lang[0]["x"] - 200) <= 1.5, lang          # Langloch (Polygon mit Bögen)
    pl = sw.punkte(lang[0]["punkte"])
    assert abs(max(x for x, _ in pl) - min(x for x, _ in pl) - 60) <= 1.5, pl
    assert abs(max(y for _, y in pl) - min(y for _, y in pl) - 20) <= 1.5, pl
    assert any(b_ for *_, b_ in sw.punkte_roh(lang[0]["punkte"])), "Rundungen als Bögen"
lasche = Image.new("L", (1000, 640), 255)                  # Ecken 90° und 135° bleiben scharf (keine Bögen)
ImageDraw.Draw(lasche).line([(100, 100), (700, 100), (820, 220), (820, 500), (100, 500), (100, 100)], fill=0, width=4,
                            joint="curve")
el_l = nz.elemente(nz.nachzeichnen(lasche)["zuege"][:1], 0.5, 640)
assert [x[0] for x in el_l] == ["LINE"] * 5, [x[0] for x in el_l]
ecken_l = sorted((round(x[2][0] - 50), round(x[2][1])) for x in el_l)
assert all(abs(a_ - b_) <= 1 for p_, q_ in zip(ecken_l, [(0, 70), (0, 270), (300, 270), (360, 70), (360, 209)])
           for a_, b_ in zip(p_, q_)), ecken_l
mit_dpi = nz.laden(scan(True, dpi=(50.8, 50.8)))[1]
assert mm_bild is None and abs(mit_dpi - 0.5) <= 1e-6, (mm_bild, mit_dpi)     # 50,8 dpi = 0,5 mm je Pixel
weiss = Image.new("L", (100, 100), 255)
try:
    nz.nachzeichnen(weiss)
    raise AssertionError("weißes Bild")
except ValueError:
    pass
ok("K2 Nachzeichnen: Linienzeichnung (Strich 4 Pixel, Mitte zählt) und gefüllte Fläche -> 300 × 150 mm, Bohrung "
   "Ø 40 ± 1,5, Langloch 60 × 20 mit Bögen, Schriftfeld fällt weg; Lasche mit 5 scharfen Ecken; Maßstab aus dpi; weißes Bild abgelehnt")

# PDF (Vektor-Zeichnung, wird gerastert) und Fenster
from reportlab.pdfgen import canvas  # noqa: E402

pdf = tmp / "scan.pdf"
c = canvas.Canvas(str(pdf), pagesize=(300 * 72 / 25.4 + 100, 200 * 72 / 25.4 + 100))
c.setLineWidth(1.2)
c.roundRect(50, 50, 200 * 72 / 25.4, 100 * 72 / 25.4, 10 * 72 / 25.4)
c.circle(50 + 50 * 72 / 25.4, 50 + 50 * 72 / 25.4, 15 * 72 / 25.4)
c.save()
dlg_n = nzd.NachzeichnenDialog(None, rohr=False, pfad=pdf)
assert dlg_n.ok_knopf.isEnabled() and abs(dlg_n.breite.value() - 200) <= 1.0, dlg_n.breite.value()   # 1:1 aus PDF
e_p, _ = dlg_n.ergebnis()
bp = [k for k in e_p["konturen"] if k["art"] == sw.BOHRUNG]
assert abs(e_p["laenge"] - 200) <= 1.0 and len(bp) == 1 and abs(bp[0]["d"] - 30) <= 1.0, (e_p["laenge"], bp)
assert "1 Loch" in dlg_n.info.text() and "Ein Pixel = 0,2" in dlg_n.info.text(), dlg_n.info.text()
dlg_n.close()
ok("K2 Raster-PDF: Platte 200 × 100 mit Ø 30 im Fenster, Breite 1:1 aus der Seite vorgeschlagen")

# Editoren: Blech ersetzen, Rohr Innenkonturen oben in der Mitte
d = SchneidwegDialog(seite, seite.positionen[0], seite.k.profile["QR 40x40x3"], seite.kopf, seite.k, seite.tabellen)
d.show()
app.processEvents()
assert d.editor.band.knopf(nzd.TITEL) is not None
klein = nz.teil(nz.nachzeichnen(nz.laden(scan(False))[0]), nz.mm_je_pixel(nz.nachzeichnen(nz.laden(scan(False))[0]),
                                                                            30))[0]
vor = len(d.eingaben()["konturen"] or [])
assert nzd.uebernehmen(d.editor, klein) == 2
kr = d.eingaben()["konturen"][vor:]
assert all(k_.get("seite") is None for k_ in kr) and any(k_["art"] == sw.BOHRUNG for k_ in kr), kr
assert all(abs(k_["x"] - 150) <= 12 for k_ in kr), [k_["x"] for k_ in kr]        # Rohr 300 mm: Mitte bei 150
d.close()
dlg = BlechDialog(None, db, dict(e, werkstoff=werkstoff))
dlg.show()
app.processEvents()
assert dlg.editor.band.knopf(nzd.TITEL) is not None
e_b, _ = nz.teil(nz.nachzeichnen(nz.laden(scan(False))[0]), 0.5)
nzd.uebernehmen(dlg.editor, e_b, ersetzen=True)
eb = dlg.eingaben()
assert eb["form"] == blech.POLYGON and len(eb["konturen"]) == 2 and abs(dlg.ergebnis["zuschnitt"]["laenge"] - 300) <= 1.5
nzd.uebernehmen(dlg.editor, e_b, ersetzen=False)
assert len(dlg.eingaben()["konturen"]) == 4
dlg.close()
ok("K2 Editoren: Knopf „Aus Scan/Bild“; Rohr bekommt Bohrung und Langloch oben in der Mitte, Blech wird ersetzt "
   "bzw. bekommt die Löcher dazu")

# ------------------------------------------------------------------ K3 Gegenrohr: Spalt und Kontakt
from rohrlaser import durchdringung as dd, gegenrohr_dialog, skizze as sk, werkzeug_koerper as wk  # noqa: E402

qs40 = sk.Querschnitt(dict(form="Rundrohr", a=40, wand=3))
t0 = dd.ende_gegen(qs40, dict(d=60))["tiefe"]
t_sp = dd.ende_gegen(qs40, dict(d=60, spalt=1))["tiefe"]
t_in = dd.ende_gegen(qs40, dict(d=60, kontakt=dd.KONTAKT_INNEN))["tiefe"]
assert abs(t0 - (30 - math.sqrt(30 ** 2 - 20 ** 2))) < 0.01                  # Sattel 40 auf 60
assert abs(t_sp - (31 - math.sqrt(31 ** 2 - 20 ** 2))) < 0.01, t_sp          # Spalt 1: Gegenrohr wie Ø 62
assert abs(t_in - (30 - math.sqrt(30 ** 2 - 17 ** 2))) < 0.01, t_in          # Innenkante Ø 34 liegt auf
assert abs(dd.schnitt_x(qs40, dict(d=60, kontakt="innen"), 20, 0) - t_in) < 0.01
gl = dd.ende_gegen(qs40, dict(d=40, kontakt="innen"))["tiefe"]
assert abs(gl - (20 - math.sqrt(400 - 289))) < 0.01, gl                       # gleich groß, Kontakt innen
qr_qs = sk.Querschnitt(dict(form="Quadratrohr", a=40, b=40, wand=3))
assert abs(dd.nach_innen(dd.querschnitt_rohr(qr_qs), 20, 5, 3)[0] - 17) < 1e-9    # flache Wand: senkrecht nach innen
gk = dd.gegen_koerper(qs40, dict(d=60, spalt=2), 500, "a")
assert abs(max(abs(p_[2]) for p_ in gk[0]) - 30) < 0.01, max(abs(p_[2]) for p_ in gk[0])  # gezeichnet ohne Spalt
assert sw.gegen_text(dict(d=60, spalt=1.5, kontakt="innen")) == "Ø 60, Spalt 1,5, Kontakt innen"
gd = gegenrohr_dialog.GegenrohrDialog(dict(form="Rundrohr", a=40, wand=3, profil_id="RR 40x3"), dict(d=60))
gd.spalt.setValue(1.0)
gd.kontakt.setCurrentIndex(1)
assert gd.wert() == dict(d=60.0, spalt=1.0, kontakt="innen"), gd.wert()
assert "Schnittlänge" in gd.ergebnis.text()
gd.close()
ok("K3 Gegenrohr: Schweißspalt 1 mm (Sattel wie auf Ø 62), Kontakt innen (Innenkante Ø 34 liegt auf), Text, Dialog")

# ------------------------------------------------------------------ K3 Werkzeug aus Körper
LAGE_R = [1000, 200, 50, 0, 0, 1, 1, 0, 0]


def zylinder(r, h, n=48):
    pk_, tri_ = [], []
    for k_ in (-h / 2, h / 2):
        for i_ in range(n):
            w_ = 2 * math.pi * i_ / n
            pk_ += [r * math.cos(w_), r * math.sin(w_), k_]
    for i_ in range(n):
        j_ = (i_ + 1) % n
        tri_ += [i_, j_, n + i_, j_, n + j_, n + i_]
    return dict(p=pk_, t={"A": tri_})


netz_r = dict(rohr3d.netz(dict(a={}, b={}, konturen=[]), QR, 300), lage=LAGE_R, mutter="bg.step")
netz_w = dict(zylinder(10, 120), lage=[1000, 200, 200, 0, 1, 0, 1, 0, 0], mutter="bg.step")   # senkrecht bei x 150
qs_h = sk.Querschnitt(rohr3d.mit_radius(QR, {}))
kz, hw = wk.konturen(sk.Querschnitt(QR), qs_h, 300, netz_r, netz_w)
assert len(kz) == 2 and not hw and {k_["seite"] for k_ in kz} == {"oben", "unten"}, (kz, hw)
for k_ in kz:
    um = k_["umriss"]
    assert abs(k_["x"] - 150) <= 0.1 and abs(k_["laenge"] - math.pi * 20) <= 0.3, k_
    assert abs(max(p_[0] for p_ in um) - min(p_[0] for p_ in um) - 20) <= 0.1
schraeg = dict(zylinder(10, 120), lage=[1000, 200, 120, 0, 1, 0, 1, 0, 0], mutter="bg.step")      # bei x 70
assert abs(wk.konturen(sk.Querschnitt(QR), qs_h, 300, netz_r, schraeg)[0][0]["x"] - 70) <= 0.1
am_ende = dict(zylinder(10, 120), lage=[1000, 200, 52, 0, 1, 0, 1, 0, 0], mutter="bg.step")       # über Ende A
k_e, h_e = wk.konturen(sk.Querschnitt(QR), qs_h, 300, netz_r, am_ende)
assert not k_e and h_e and "Rohrende" in h_e[0], (k_e, h_e)
weit = dict(zylinder(10, 120), lage=[1500, 200, 200, 0, 1, 0, 1, 0, 0], mutter="bg.step")
try:
    wk.konturen(sk.Querschnitt(QR), qs_h, 300, netz_r, weit)
    raise AssertionError("trifft nicht")
except ValueError as x:
    assert "berührt" in str(x)
assert abs(wk.abstand(qs_h, 20, 0)) < 1e-9 and wk.abstand(qs_h, 0, 0) < 0 and wk.abstand(qs_h, 30, 0) > 0

# im Rohr-Editor: zwei Positionen derselben STEP
from rohrlaser.ansicht3d import packen  # noqa: E402

nr2 = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
pid_r = db.position_neu(nr2, dict(pos=10, artikel="R-1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=300,
                                  stueck=2))
pid_w = db.position_neu(nr2, dict(pos=20, artikel="Stift", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                                  laenge=120, stueck=2))
db.netz_speichern(pid_r, packen(netz_r))
db.netz_speichern(pid_w, packen(netz_w))
seite2 = fenster.angebot_oeffnen(nr2)
pr = next(q for q in seite2.positionen if q["id"] == pid_r)
d = SchneidwegDialog(seite2, pr, seite2.k.profile["QR 40x40x3"], seite2.kopf, seite2.k, seite2.tabellen, seite2.db,
                     seite2.positionen)
d.show()
app.processEvents()
assert d.editor.werkzeug_aktion.text().startswith(wk.TITEL)
vor = len(d.eingaben()["konturen"] or [])
assert wk.aus_koerper(d.editor, "Pos 20 Stift") == 2
kn = d.eingaben()["konturen"][vor:]
assert [k_["art"] for k_ in kn] == [sw.SONDERKONTUR] * 2 and all(abs(k_["x"] - 150) <= 0.1 for k_ in kn), kn
assert d.ergebnis["felder"]["innen"] >= 2 * math.pi * 20 - 1, d.ergebnis["felder"]
d.close()
ok("K3 Werkzeug aus Körper: senkrechter Stift Ø 20 durch QR 40 -> 2 Sonderkonturen oben/unten bei x 150 "
   "(Länge 62,8), Lage folgt dem Körper, über das Rohrende abgelehnt, ohne Berührung Meldung; im Rohr-Editor angelegt")
# ------------------------------------------------------------------ K4 Rohrzug aus XYZ-Punkten
from rohrlaser import baugruppe as bgm, rahmen as rh, rohr3d, rohrzug as rz  # noqa: E402
from rohrlaser.neue_position import ROHRZUG  # noqa: E402

assert rz.punkte_lesen("X;Y;Z\n0;0;0\n100,5;0;0\n1,2,3\n4 1 2 3\n# Ende\n") == [
    (0, 0, 0), (100.5, 0, 0), (1, 2, 3), (1, 2, 3)]
try:
    rz.punkte_lesen("0 0 0\n1 2\n5 a 1")
    raise AssertionError("falsche Zeile nicht gemeldet")
except ValueError as x:
    assert "Zeile 3" in str(x), x
QR40 = dict(form="Quadratrohr", a=40, wand=2)
RR = dict(form="Rundrohr", a=33.7, wand=2)
# geschlossenes Rechteck = Rahmen-Assistent mit Gehrung (außen 1040 × 640)
zug = rz.bauen(QR40, [(0, 0, 0), (1000, 0, 0), (1000, 0, 600), (0, 0, 600), (0, 0, 0)])
ref = rh.bauen(QR40, rh.RAHMEN, 1040, 640, ecken=rh.GEHRUNG)
assert zug["geschlossen"] and zug["rohre"] == 4 and zug["knicke"] == [90.0] * 4
assert sorted((t["laenge"], len(t["lagen"])) for t in zug["teile"]) == sorted(
    (t["laenge"], len(t["lagen"])) for t in ref["teile"]) == [(640.0, 2), (1040.0, 2)]


def welt(erg, profil):
    out = {}
    for t in erg["teile"]:
        p = rohr3d.netz(t["eingaben"], profil, t["laenge"])["p"]
        for k_, lage in zip(t["koerper"], t["lagen"]):
            o, z, x = lage[0:3], lage[3:6], lage[6:9]
            y = rh._kreuz(z, x)
            out[k_] = [tuple(o[j] + p[i] * x[j] + p[i + 1] * y[j] + p[i + 2] * z[j] for j in range(3))
                       for i in range(0, len(p), 3)]
    return out


def gehrungen_pruefen(erg, profil):
    """Jedes Rohr endet genau in der Winkelhalbierenden seines Knicks (0,02 mm), die Querschnitte beider Rohre in
    der Ebene sind gleich groß."""
    w, pk, n = welt(erg, profil), erg["punkte"], len(erg["punkte"])
    for i in range(erg["rohre"]):
        for k_, ende in ((i, "a"), ((i + 1) % n, "b")):
            if not erg["geschlossen"] and (k_ == 0 and ende == "a" or k_ == n - 1 and ende == "b"):
                continue
            d1 = rz._norm(rz._sub(pk[k_], pk[k_ - 1]))
            d2 = rz._norm(rz._sub(pk[(k_ + 1) % n], pk[k_]))
            nm = rz._norm(tuple(d1[j] + d2[j] for j in range(3)))
            s_ = [sum((q[j] - pk[k_][j]) * nm[j] for j in range(3)) for q in w[i + 1]]
            assert abs(max(s_) if ende == "b" else min(s_)) < 0.02, (i, ende, max(s_), min(s_))
    return w


gehrungen_pruefen(zug, QR40)
u_zug = rz.bauen(QR40, [(0, 0, 0), (1000, 0, 0), (1000, 0, 800), (0, 0, 800)])
assert sorted((t["laenge"], len(t["lagen"])) for t in u_zug["teile"]) == [(840.0, 1), (1020.0, 2)], u_zug["teile"]
gehrungen_pruefen(u_zug, QR40)          # Schenkel gewendet eingebaut, Gehrung trotzdem an der Ecke
schraeg = rz.bauen(dict(form="Rechteckrohr", a=60, b=30, wand=2), [(0, 0, 0), (1000, 0, 0), (1500, 0, 500),
                                                                  (1500, 0, 1500)])
gehrungen_pruefen(schraeg, dict(form="Rechteckrohr", a=60, b=30, wand=2))
assert schraeg["knicke"] == [45.0, 45.0] and schraeg["teile"][0]["eingaben"]["a"] == {}
raum = rz.bauen(RR, [(0, 0, 0), (1000, 0, 0), (1000, 800, 300), (0, 800, 900)])
gehrungen_pruefen(raum, RR)
for falsch, text in (([(0, 0, 0), (1000, 0, 0), (1000, 500, 0), (1000, 500, 400)], "außerhalb der Ebene"),
                     ([(0, 0, 0), (1000, 0, 0), (0, 10, 0)], "höchstens"),
                     ([(0, 0, 0), (0, 0, 0)], "mindestens zwei"),
                     ([(0, 0, 0), (1000, 0, 0), (1000, 10, 0)], "zu kurz")):
    try:
        rz.bauen(QR40, falsch)
        raise AssertionError(f"nicht abgelehnt: {falsch}")
    except ValueError as x:
        assert text in str(x), x
ok("K4 Rohrzug: Punkte lesen (Komma/Semikolon/Leerzeichen, Kopfzeile), Rechteck = Rahmen-Assistent mit Gehrung, "
   "U mit gewendetem gleichen Schenkel, "
   "schräger Zug aus Rechteckrohr und räumlicher Zug aus Rundrohr enden genau in den Winkelhalbierenden, "
   "nicht ebene Quadratrohre, zu großer Knick und zu kurze Rohre abgelehnt")

nr3 = db.angebot_neu(dict(kunde="Test", maschine="T11"))
seite3 = fenster.angebot_oeffnen(nr3)
qr_id = next(pid for pid, p in seite3.k.profile.items() if p.get("form") == "Quadratrohr")
gesehen = {}


def zug_fuellen(d):
    d.profil.setCurrentText(qr_id)
    d.punkte.setPlainText("0;0;0\n1000;0;0\n1000;0;800\n0;0;800")
    d.saetze.setValue(2)
    d.name.setText("Geländer")
    gesehen["text"] = d.vorschau.text()
    gesehen["3d"] = bool(d.ansicht.ansicht.netz)
    d._ok()
    return d.result()


assert seite3.position_neu(ROHRZUG, dialog=zug_fuellen) == ROHRZUG
assert "3 Rohre, offen" in gesehen["text"] and gesehen["3d"], gesehen
bgs = bgm.baugruppen(seite3.positionen)
assert len(bgs) == 1, [p.get("baugruppe") for p in seite3.positionen]
i_bg, teile_bg = next(iter(bgs.values()))[0], [p for p in seite3.positionen if p.get("satz") or p.get("bg_id")]
assert bgm.name(seite3.positionen[i_bg]) == "Geländer" and seite3.positionen[i_bg]["stueck"] == 2
rohre = [p for p in seite3.positionen if p.get("profil_id") == qr_id]
assert len(rohre) == 2 and sorted(p["stueck"] for p in rohre) == [2, 4], [(p["laenge"], p["stueck"]) for p in rohre]
assert all(p.get("schneidweg") for p in rohre), [p.get("schneidweg") for p in rohre]
assert all(seite3.db.netz(p["id"]) for p in rohre)
ok("K4 im Angebot: Neue Position → Rohrzug aus Punkten legt 3 Rohre (2 gleiche) mit Gehrung, Schneidweg und 3D an "
   "und macht daraus die Schweißbaugruppe Geländer (2 Stück)")

db.con.close()
ok("K5 Knopf „STL speichern“ im Rohr-, Blech-, Baugruppen- und Satz-Editor, Datei wie die 3D-Ansicht")
print("Paket K: alle Tests bestanden.")
