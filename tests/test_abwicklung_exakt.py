"""Exakte Rohrabwicklung (Plan 3D/Abwicklung P4.1–P4.3, Patrick 20.11.2026 „Alles einbauen“):

- X1 Mantel: echte Außenhaut mit Eckradien (Umfang 2 (B + H) − 8 r + 2 π r), s <-> t umkehrbar, t passt zur radialen
  Lage auf dem Bogen (skizze.rund_ort); ohne Radius (Rundrohr, Flachstahl, U-Profil) t = s
- X2 Geschnittene Konturen in der Abwicklung genau wie im 3D/Schnittkörper (rohr3d.loch_poly): Rundrohr 2D innen
  maßhaltig (außen d · R/ri), 3D eben wie gezeichnet; ebene Wand unverändert
- X3 linien: Kennungen ende/rand/kante/radius/kontur:<Zeile>:<Nr>, Kontur über die Naht bleibt geschlossen
- X4 Bemaßung: Seitenbreiten ergeben den Umfang, Lage je Kontur, Kettenmaß
- X5 DXF der Rohrabwicklung: Layer AUSSENKONTUR … BESCHRIFTUNG, Umriss = 2 L + 2 U, Bohrung = π d
- X6 Skizze im Modus Abwicklung: Höhe = echter Umfang, Ziehen quer bleibt auf der Außenhaut, Fenster speichert DXF
  und PDF
- X7 Keine zweite Rechnung: Schnittlänge (schneidweg) unverändert

Aufruf: python tests/test_abwicklung_exakt.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import abwicklung as ab, dxf, rohr3d, schneidweg as sw, skizze as sk, skizze_widget  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
RE = dict(form="Rechteckrohr", a=60, b=40, wand=3)
RR = dict(form="Rundrohr", a=42.4, wand=2)

# ------------------------------------------------------------------ X1 Mantel
qs = sk.Querschnitt(RE)
r = qs.radius
assert r > 0, r
m = ab.Mantel(qs)
assert m.exakt and abs(m.umfang - (2 * (60 + 40) - 8 * r + 2 * math.pi * r)) < 1e-9, m.umfang
for s in (0, 0.5, 3, r, 10, 30, 57, 60, 61, 99.9, 100, 140, 199.99, 200, 260, -7):
    assert abs(m.s(m.t(s)) - s) < 1e-9, s
assert all(m.t(a) < m.t(b) for a, b in zip(range(0, 200, 3), range(3, 203, 3)))     # streng steigend
# radial auf den Bogen (rund_ort) und die Bogenlänge ab der Bogenmitte: wie t
cu, cv = qs.B / 2 - r, qs.H / 2 - r
for c in (0.5, 2.0, 4.0):                       # Stelle c ab der scharfen Ecke oben hinten auf der Fläche oben
    u, v, _ = sk.rund_ort(qs, -qs.B / 2 + c, qs.H / 2)
    w = math.atan2(-(u + cu), v - cv)           # Winkel ab der Senkrechten am Bogenmittelpunkt (hinten +)
    soll = math.pi * r / 4 - r * w              # Bogenmitte (45°) = t 0
    assert abs(m.t(c) - soll) < 1e-9, (c, m.t(c), soll)
breiten = [t1 - t0 for _, t0, t1 in m.streifen()]
assert abs(breiten[0] - (60 - 2 * r + math.pi * r / 2)) < 1e-9 and abs(sum(breiten) - m.umfang) < 1e-9
assert [a for _, a in m.radius_linien()].count("radius") == 8
for prof in (RR, dict(form="Flachstahl", a=50, wand=8), dict(form="U-Profil", a=80, b=45, wand=6)):
    q = sk.Querschnitt(prof)
    mm = ab.Mantel(q)
    assert not mm.exakt and mm.t(12.3) == 12.3 and mm.umfang == q.umfang, prof
ok("X1 Mantel: Umfang mit Eckradien, s <-> t umkehrbar, passt zu rund_ort; ohne Radius t = s")

# ------------------------------------------------------------------ X2 Konturen wie im 3D
qr = sk.Querschnitt(RR)
ring = ab.ringe(qr)
B30 = dict(art=sw.BOHRUNG, anzahl=1, d=30, x=100)


def quer(qs_, e, k):
    d = sk.lagen([k], 300, qs_)[0]
    xs = ab.kontur_s(qs_, d, e, ab.ringe(qs_))
    ts = [ab.Mantel(qs_).t(s) for _, s in xs]
    return max(ts) - min(ts), xs, d


b2, xs, d = quer(qr, dict(konturen=[B30]), B30)
R, ri = 21.2, 19.2
assert abs(b2 - 2 * R * math.asin(15 / ri)) < 0.05, b2   # 2D: innen Ø 30 in der Draufsicht (Bolzen passt), außen breiter
b3, _, _ = quer(qr, dict(d3=True, konturen=[dict(B30, schnitt="parallel")]), dict(B30, schnitt="parallel"))
assert abs(b3 - 30) < 0.05, b3                           # 3D eben: außen wie gezeichnet
poly = rohr3d.loch_poly(d, dict(konturen=[B30]), qr, ring[0], ring[2], ring[3])
assert len(poly) == len(xs) and all(abs(p[1] - x) < 1e-9 for p, (x, _) in zip(poly, xs))   # dieselbe Rechnung
K = dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="vorne")
bk, _, _ = quer(qs, dict(konturen=[K]), K)
assert abs(bk - 10) < 0.02, bk                           # ebene Wand: wie gezeichnet
ok("X2 Konturen: Rundrohr-Bohrung 2D außen 2R·asin(r/ri), 3D eben wie gezeichnet, ebene Wand unverändert (rohr3d.loch_poly)")

# ------------------------------------------------------------------ X3 linien
ein = dict(konturen=[dict(art=sw.RECHTECK, anzahl=1, b=20, h=20, x=80, seite="oben", q=24),
                     dict(art=sw.BOHRUNG, anzahl=3, abstand=50, d=10, x=150, seite="vorne"),
                     dict(art=sw.BOHRUNG, anzahl=1, d=12, x=250, seite="oben", q=-29)])      # über die Ecke/Naht
li = ab.linien(qs, ein, 300)
kenn = [x["kennung"] for x in li]
assert {"ende:a", "ende:b", "rand:0", "rand:1"} <= set(kenn), kenn
assert {"kontur:0:0", "kontur:1:0", "kontur:1:1", "kontur:1:2", "kontur:2:0"} <= set(kenn), kenn
assert sum(k.startswith("radius:") for k in kenn) == 8 and sum(k.startswith("kante:") for k in kenn) == 3, kenn
naht = next(x for x in li if x["kennung"] == "kontur:2:0")
ts = [t for _, t in naht["punkte"]]
assert naht["geschlossen"] and min(ts) < 0 < max(ts) and 12 < max(ts) - min(ts) < 20, (min(ts), max(ts))
ok("X3 linien: Kennungen je Linie (wie im 3D kontur:<Zeile>), Kontur über die Naht stetig")

# ------------------------------------------------------------------ X4 Bemaßung
b = ab.bemassung(qs, ein, 300)
assert abs(sum(w for _, w in b["seiten"]) - b["umfang"]) < 0.01 and b["umfang_scharf"] == 200.0, b
assert b["kette"] == [80.0, 150.0, 200.0, 250.0], b["kette"]
k1 = next(k for k in b["konturen"] if k["kennung"] == "kontur:1:0")
t_vorne = b["seiten"][0][1] + b["seiten"][1][1] / 2      # Mitte der Seite vorne auf der Außenhaut
assert abs(k1["t"] - t_vorne) < 0.05 and k1["breite_x"] == 10.0 and k1["text"] == "Ø 10", k1
ok("X4 Bemaßung: Seiten = Umfang, Lage x/t je Kontur, Kettenmaß längs")

# ------------------------------------------------------------------ X5 DXF
tmp = Path(tempfile.mkdtemp())
einfach = dict(konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=150, seite="vorne"),
                         dict(art=sw.TEXT_GRAVUR, anzahl=1, text="A1", hoehe=6, x=60, seite="unten")])
ab.dxf_speichern(tmp / "r.dxf", qs, einfach, 300)
el = dxf.lesen((tmp / "r.dxf").read_text(encoding="cp1252"))
laengen = dxf.schnittlaenge(el)
assert set(laengen) == {"AUSSENKONTUR", "INNENKONTUR", "KANTE", "RADIUS", "GRAVUR", "BESCHRIFTUNG"}, laengen
assert abs(laengen["AUSSENKONTUR"] - (2 * 300 + 2 * m.umfang)) < 0.5, laengen
assert abs(laengen["INNENKONTUR"] - math.pi * 10) < 0.1, laengen
assert laengen["GRAVUR"] > 5 and abs(laengen["KANTE"] - 3 * 300) < 1e-6, laengen
ys = [p[1] for e_ in el if e_[0] == "LINE" for p in (e_[2], e_[3])]
assert min(ys) > -1e-6 and max(ys) < m.umfang + 1e-6, (min(ys), max(ys))
texte = [e_[4] for e_ in el if e_[0] == "TEXT"]
assert any("Umfang" in t for t in texte) and any("Ø 10" in t for t in texte), texte
ab.dxf_speichern(tmp / "o.dxf", qs, einfach, 300, mit_mass=False)
assert not [e_ for e_ in dxf.lesen((tmp / "o.dxf").read_text(encoding="cp1252")) if e_[0] == "TEXT"]
ok("X5 DXF: sechs Layer, Umriss 2 L + 2 U, Bohrung π d, Gravur als Schrift, Maße abschaltbar")

# ------------------------------------------------------------------ X6 Skizze und Fenster
sz = skizze_widget.Skizze(dict(profil_id=None, **RE), 300)
sz.modus = skizze_widget.ABWICKLUNG
sz.zeigen(dict(konturen=[dict(K)]))
sz.resize(900, 420)
assert abs(sz._welt_hoehe() - m.umfang) < 1e-9
a = sz._ansichten()[0]
oben, unten = sz._bild(a, 0, 0), sz._bild(a, 0, qs.umfang)
assert abs((unten.y() - oben.y()) / sz.massstab() - m.umfang) < 1e-6
sz.grab()
assert sz.treffer, "Kontur nicht gezeichnet"
d = sz.lagen()[0]
z = dict(art="kontur", start=QPointF(0, 0), lage=d, ansicht=a, e=dict(d["eingabe"]))
neu = sz.neue_lage(z, QPointF(0, 5 * sz.massstab()))     # 5 mm am Umfang weiter
t_alt, t_neu = m.t(sk.s_lage(qs, K)), m.t(sk.s_lage(qs, dict(K, **{k_: v for k_, v in neu.items() if k_ != "x"})))
assert abs(t_neu - t_alt - 5) < 0.06, (t_alt, t_neu, neu)
assert "am Umfang" in sz.beschreibung(d)


class _D:
    p = dict(pos=3, artikel="RE60")


class _Rahmen:
    art = "rohr"


from PySide6.QtWidgets import QWidget  # noqa: E402
from rohrlaser import editor_abwicklung  # noqa: E402

d_ = QWidget()
d_.p = _D.p
d_.skizze = sz
d_._auswahl_skizze = lambda *_: None
d_._verschoben = lambda *_: None
rahmen = _Rahmen()
rahmen.d = d_
f = editor_abwicklung.AbwicklungFenster(rahmen)
f.auffrischen()
assert f.dxf_speichern(str(tmp / "f.dxf")) and (tmp / "f.dxf").stat().st_size > 1000
assert f.pdf_speichern(str(tmp / "f.pdf")) and (tmp / "f.pdf").read_bytes()[:4] == b"%PDF"
ok("X6 Skizze: Höhe = echter Umfang, Ziehen quer auf der Außenhaut, Tooltip; Fenster speichert DXF und PDF")

# ------------------------------------------------------------------ X7 keine zweite Rechnung
src = (HIER.parent / "programm" / "rohrlaser" / "abwicklung.py").read_text(encoding="utf-8")
assert "schnittlaenge(" not in src.replace("dxf.schnittlaenge", "") and "schneidweg import" in src
ok("X7 Schnittlänge bleibt in schneidweg.py (Abwicklung rechnet keine zweite)")

# ------------------------------------------------------------------ X8 Abwicklung 1:1 drucken mit echter Außenhaut
from rohrlaser import abwicklung_druck  # noqa: E402

pos = dict(pos=10, artikel="RE60", laenge=300, technik=None)
dd = abwicklung_druck.daten(pos, dict(RE))
assert abs(dd["umfang"] - m.umfang) < 1e-9 and max(t for _, t in dd["umriss"]) <= m.umfang + 1e-6, dd["umfang"]
kz = abwicklung_druck.koordinaten(dd)
assert abs(kz[-1][0] - m.umfang) < 1e-9 and len(kz) == math.ceil(m.umfang / 10) + 1
b_ = abwicklung_druck.schreiben(tmp / "11.pdf", pos, dict(RE), "Pos. 10")
assert (tmp / "11.pdf").read_bytes()[:4] == b"%PDF" and b_["seiten"] >= 1
ok("X8 Abwicklung 1:1: Papier hat den echten Umfang (zum Umwickeln), Koordinaten je 10 mm Außenhaut")

# ------------------------------------------------------------------ X9 3D <-> 2D: Hover und Klick (P5.1/P5.2)
import json  # noqa: E402

from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
kx = db.kontext()
technik = dict(quelle=sw.QUELLE, a=dict(winkel=0), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben"),
                         dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="unten")])
pp = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, technik=json.dumps(technik))
dlg = SchneidwegDialog(None, pp, kx.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), kx, db.tabellen(), db)
ed = dlg.editor
dlg.show()
for _ in range(5):
    app.processEvents()
a3 = ed.ansicht()
gemeldet = []
dlg.skizze.ueber.connect(gemeldet.append)
ed._skizze_ueber(1)                                      # Maus über Kontur 2 in der Skizze -> 3D hebt hervor
assert a3.hover_id == "kontur:1"
ed._skizze_ueber(None)
assert a3.hover_id is None
ed._3d_ueber(dict(id="kontur:0", punkt=(0, 0, 0)))        # Maus über Kontur 1 im 3D -> Skizze hebt hervor
assert dlg.skizze.hover == 0
ed._3d_ueber(None)
assert dlg.skizze.hover is None
a3.resize(600, 400)
a3.grab()
li = a3.modell.linien
nr = next(i for i, k in enumerate(a3.modell.linien_id) if k == "kontur:1")
bp = a3.bildpunkt()(li[nr][0])
t = a3.linie_unter(bp[0], bp[1])
assert t is not None and t["id"] == "kontur:1", t
# STEP-Netz ohne Kennungen: zwei Bohrungen an derselben Stelle x, die Lage am Umfang entscheidet
mn, mx = a3.modell.min, a3.modell.max
oben = ((mn[0] + mx[0]) / 2, mx[1], mn[2] + 100)
unten = ((mn[0] + mx[0]) / 2, mn[1], mn[2] + 100)
assert ed._kennung_bei(oben) == "kontur:0" and ed._kennung_bei(unten) == "kontur:1", (ed._kennung_bei(oben),
                                                                                      ed._kennung_bei(unten))
assert ed._kennung_bei((0, 0, mn[2] + 1)) == "ende:a"
ok("X9 3D <-> 2D: Hover hebt dieselbe Kontur im 3D bzw. in Skizze/Abwicklung hervor; STEP-Netz: Klick nach Lage am "
   "Umfang")
# ------------------------------------------------------------------ X12 unsichere Merkmale gelb (P3.1, Analyse aus #596)
from rohrlaser import bauteil_analyse as ba  # noqa: E402

analyse = dict(merkmale=[dict(merkmal="Bohrung", abmessung="Ø 10 mm", x=100, seite="oben", konfidenz=75),
                         dict(merkmal="Freiform", abmessung="Hüllmaß 12 mm", x=300, konfidenz=60, hinweis="prüfen"),
                         dict(merkmal="Bohrung", abmessung="Ø 10 mm", x=200, seite="vorne", konfidenz=95),
                         dict(merkmal="Gehrung", ende="B", konfidenz=70)])
qq = sk.Querschnitt(dict(form="Quadratrohr", a=40, b=40, wand=3))
un = ab.unsichere(qq, analyse, 500)
assert [m["x"] for m in un] == [100.0, 300.0, 500.0], un
assert un[0]["s"] == sk.s_lage(qq, dict(seite="oben")) and un[1]["s"] is None and "bitte prüfen" in un[0]["text"]
assert ab.unsichere(qq, None) == [] and ab.unsichere(qq, dict(merkmale=[dict(x=5, konfidenz=ba.GRUEN_AB)])) == []
alt_aus = ba.aus_position
ba.aus_position = lambda _p: analyse
try:
    ed.pruefen_setzen()
finally:
    ba.aus_position = alt_aus
assert len(dlg.skizze.pruefen) == 3 and len(a3.pruef_punkte) == 3
a3.grab()
dlg.skizze.modus = skizze_widget.ABWICKLUNG
dlg.skizze.grab()
pa = dlg.skizze._pruefen_orte(dlg.skizze._ansichten()[0])
assert dlg.skizze.pruefen_bei(pa[0][0]) is un[0] or dlg.skizze.pruefen_bei(pa[0][0])["x"] == 100.0
ok("X12 Unsichere Merkmale (Konfidenz unter 90 %) gelb mit ? in 3D und Abwicklung, Hinweis beim Überfahren")
dlg.reject()

# ------------------------------------------------------------------ X10 Gegenprobe Konturlänge (P6.1, nur Hinweis)
eg = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, d=10, anzahl=2, abstand=50, x=100, seite="vorne"),
                                dict(art=sw.RECHTECK, b=20, h=20, anzahl=1, x=200, q=22, seite="oben"),
                                dict(art=sw.GRAVUR, anzahl=1, x=50)])
erg = sw.rechnen(eg, RE, (10, 50))
vorher = [st["laenge"] for st in erg["schritte"]]
# Patrick 20.11.2026: Rechteck bis in den Eckradius rechnet jetzt die Länge auf der Außenhaut (wie Abwicklung/3D)
st_r = next(st for st in erg["schritte"] if st.get("eingabe") is eg["konturen"][1])
assert abs(st_r["laenge_stueck"] - 89.43) < 0.05 and "Eckradius" in st_r["text"], st_r
assert ab.gegenprobe(qs, eg, 300, erg) == []                                          # Rechnung = Abwicklung
flach = dict(eg, konturen=[dict(eg["konturen"][1], q=0)])                             # ganz auf der Wand: Formel
assert sw.rechnen(flach, RE, (10, 50))["schritte"][2]["laenge_stueck"] == 80.0
alt = {**erg, "schritte": [dict(st, laenge_stueck=80.0) if st is st_r else st for st in erg["schritte"]]}
g = ab.gegenprobe(qs, eg, 300, alt)                                                   # alte Rechnung: Hinweis
assert [x["zeile"] for x in g] == [1] and g[0]["rechnung"] == 80.0 and g[0]["prozent"] > 1, g
assert [st["laenge"] for st in erg["schritte"]] == vorher                                        # nichts neu gerechnet
assert ab.gegenprobe(qs, eg, 300, alt, grenze=50) == [] and ab.gegenprobe(qs, eg, 300, None) == []
RR = dict(form="Rundrohr", a=42.4, wand=2)                                            # Bohrung Ø 30: Bolzen passt
eb = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, d=30, anzahl=1, x=100, seite="oben")])
assert ab.gegenprobe(sk.Querschnitt(RR), eb, 300, sw.rechnen(eb, RR, (10, 50))) == []
ok("X10 Gegenprobe: Rechteck im Eckradius und Rundrohr-Bohrung wie Abwicklung, alte Abweichung als Hinweis")

# ------------------------------------------------------------------ X11 Original gegen bearbeitet (P6.3)
gerufen = []
alt_ = sz._original_zeichnen
sz._original_zeichnen = lambda g_, a_: (gerufen.append(1), alt_(g_, a_))
sz.original = dict(konturen=[dict(K, x=60)])
img = sz.grab().toImage()
assert gerufen, "Original nicht gezeichnet"
sz.original = None
gerufen.clear()
sz.grab()
assert not gerufen
assert not f.original.isEnabled()                       # ohne Importstand: nichts zu vergleichen
ok("X11 Original (Import) gestrichelt über der bearbeiteten Abwicklung, nur mit Importstand")
print("Alles in Ordnung.")
