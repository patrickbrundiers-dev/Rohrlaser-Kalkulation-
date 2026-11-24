"""Schnittfläche der Enden in 2D und 3D (Plan 3E-10, Patrick 24.10.2026, „alle a“).

- F1 2D: Strahl senkrecht zur Mantelfläche, die Innenkante liegt unter der Außenkante; Länge = Außenkante
  (wie schneidweg.ende).
- F2 3D bis 45°: Kopfwinkel je Stelle (Wände parallel zur Kippachse 0°, quer dazu der Gehrungswinkel), nichts
  begrenzt; Innenkante auf der Soll-Ebene.
- F3 3D über 45°: nur die Stücke über der Grenze stehen auf 45° und werden gemeldet (Ende, Länge, Winkel);
  Rundrohr stetig.
- F4 3D-Ansicht: 2D-Innenkante unter der Außenkante, 3D über 45° gelb (Art GB) als Fläche und Linie.
- F5 Prüfung der Position: WARNUNG mit Ende und Länge; Skizze zeichnet die Abwicklung mit gelben Stücken.

Aufruf: python tests/test_schnittflaeche.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "programm"))

from rohrlaser import dreid, rohr3d, schneidweg as sw, schnittflaeche as sf, skizze as sk  # noqa: E402


def ok(text):
    print("OK    ", text)


QR = dict(form="Quadratrohr", a=60, b=60, wand=5)
RR = dict(form="Rundrohr", a=60.3, b=0, wand=4)
qs_qr = sk.Querschnitt(sw.mit_radius(QR, {}))
qs_rr = sk.Querschnitt(sw.mit_radius(RR, {}))

# ------------------------------------------------------------------ F1 2D
for w in (30, 60):
    e = dict(winkel=w, richtung=0)
    aussen, innen = sf.ringe(qs_qr)
    for pa, pi in zip(aussen, innen):
        d = sf.punkt(qs_qr, e, pa, pi, False)
        assert d["x_innen"] == d["x_aussen"] and d["winkel"] == 0 and not d["begrenzt"], d
    st = sf.abschnitte(qs_qr, e, False)
    assert abs(sum(s["laenge"] for s in st) - sw.ende(QR, w)[0]) < 0.5, (sum(s["laenge"] for s in st), sw.ende(QR, w))
    assert not any(s["begrenzt"] for s in st) and sf.hinweis("Ende B", st) is None
ok("F1 2D: Strahl senkrecht zum Mantel, Innenkante unter der Außenkante, Länge wie schneidweg.ende")

# ------------------------------------------------------------------ F2 3D bis 45°
e30 = dict(winkel=30, richtung=0)
st = sf.abschnitte(qs_qr, e30, True)
oben = [s for s in st if abs(s["v"] - 30) < 1e-6 and abs(s["u"]) < 15]
seite = [s for s in st if abs(abs(s["u"]) - 30) < 1e-6 and abs(s["v"]) < 15]
assert oben and all(abs(s["beta"] - 30) < 0.01 for s in oben), oben[:1]
assert seite and all(s["beta"] < 0.01 for s in seite), seite[:1]
assert not any(s["begrenzt"] for s in st) and max(s["winkel"] for s in st) <= 30.01
aussen, innen = sf.ringe(qs_qr)
for pa, pi in zip(aussen, innen):                   # Innenkante auf der Ebene (Schnitt eben durch die Wand)
    d = sf.punkt(qs_qr, e30, pa, pi, True)
    assert abs(d["x_innen"] - sk.schnitt_x(qs_qr, e30, *pi, aussen=True)) < 1e-6      # Soll-Ebene
ok("F2 3D 30°: oben/unten 30° Kopfwinkel, Seitenwände 0°, Innenkante auf der Soll-Ebene, nichts begrenzt")

# ------------------------------------------------------------------ F3 3D über 45°
e60 = dict(winkel=60, richtung=0)
st = sf.abschnitte(qs_qr, e60, True)
lg, beta = sf.begrenzt(st)
assert abs(beta - 60) < 0.01 and 2 * 30 < lg < sum(s["laenge"] for s in st) / 2, (lg, beta)
assert all(s["winkel"] <= 45 + 1e-9 for s in st)
assert not any(s["begrenzt"] for s in st if abs(abs(s["u"]) - 30) < 1e-6 and abs(s["v"]) < 15)   # Seiten nicht
h = sf.hinweis("Ende B", st)
assert h.startswith("Ende B: ") and "bis 60°, auf 45° begrenzt" in h, h
st_r = sf.abschnitte(qs_rr, e60, True)
lg_r, beta_r = sf.begrenzt(st_r)
assert abs(beta_r - 60) < 0.5 and 0 < lg_r < sum(s["laenge"] for s in st_r), (lg_r, beta_r)
assert min(s["beta"] for s in st_r) < 5.0           # an den Seiten (90°/270°) fast 0°
assert not sf.begrenzt(sf.abschnitte(qs_rr, e60, True, grenze=70))[0]
ok(f"F3 3D 60°: {lg:.0f} mm über 45° (oben/unten), Seiten 0°, Hinweis „{h}“; Rundrohr stetig")

# ------------------------------------------------------------------ F4 3D-Ansicht
for d3 in (False, True):
    e = dict(a={}, b=dict(winkel=60, richtung=0, d3=d3), konturen=[], d3=d3)
    n = rohr3d.netz(e, QR, 400)
    assert ("GB" in n["t"]) == d3 and ("GB" in n["l"]) == d3, (d3, list(n["t"]), list(n["l"]))
n30 = rohr3d.netz(dict(a={}, b=dict(winkel=30, richtung=0, d3=True), konturen=[], d3=True), QR, 400)
assert "GB" not in n30["t"]
assert "GB" not in rohr3d.netz(dict(a={}, b=dict(winkel=60, richtung=0, d3=True), konturen=[], d3=True), QR, 400,
                               grenze=60)["t"]
ok("F4 3D-Ansicht: gelb (GB) nur in 3D über der Grenze der Maschine")

# ------------------------------------------------------------------ F5 Prüfung und Skizze
M3 = dict(maschinen_id="T11", d3="ja", schwenk_min=-45, schwenk_max=45, greif_3d=300)
p = dict(laenge=400, b_schnitt=sw.ende(QR, 60)[0], technik=json.dumps(dict(d3=True, a={}, b=dict(
    winkel=60, richtung=0, d3=True), konturen=[])))
st_p = dreid.pruefen(p, M3, profil=QR)
assert st_p.startswith("WARNUNG: 3D-Winkel begrenzt, Kontur nicht maßhaltig – Gehrung 3D Ende B: "), st_p
(b,) = dreid.bearbeitungen(p, M3, profil=QR)
assert b["winkel"] == 45 and b["abschnitte"] and abs(sum(x["laenge"] for x in b["abschnitte"]) - p["b_schnitt"]) < 0.5
assert dreid.pruefen(p, M3) == "WARNUNG: 3D-Winkel begrenzt, Kontur nicht maßhaltig"     # ohne Profil wie bisher
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.skizze_widget import ABWICKLUNG, Skizze  # noqa: E402
app = QApplication.instance() or QApplication([])
s = Skizze(QR, 400)
s.zeigen(json.loads(p["technik"]))
s.resize(900, 500)
bild = s.bild(900, 500, ABWICKLUNG, faktor=1)[0]
gelb = sum(1 for x in range(0, bild.width(), 2) for y in range(0, bild.height(), 2)
           if bild.pixelColor(x, y).name() == "#f2c200")
assert gelb > 20, gelb
s.zeigen(dict(json.loads(p["technik"]), d3=False))
bild = s.bild(900, 500, ABWICKLUNG, faktor=1)[0]
assert not any(bild.pixelColor(x, y).name() == "#f2c200" for x in range(0, bild.width(), 2)
               for y in range(0, bild.height(), 2))
ok("F5 Position: WARNUNG mit Ende und Länge, Zeit je Stück; Skizze mit gelben Stücken ohne Fehler")

# Abwicklung: Konturen ausgeschnitten (Patrick 25.10.2026), Gravur nicht
s.zeigen(dict(a={}, b={}, konturen=[dict(art="Rechteck", anzahl=1, b=60, h=20, r=0, x=200, seite="oben"),
                                    dict(art="Text-Gravur", anzahl=1, text="4711", hoehe=8, x=100, seite="oben")]))
bild = s.bild(900, 500, ABWICKLUNG, faktor=1)[0]
mitte = {d["art"]: poly.boundingRect().center() for poly, d, an in s.treffer if an[0] == "abw"}
loch, grav = mitte["Rechteck"], mitte["Text-Gravur"]
assert bild.pixelColor(int(loch.x()), int(loch.y())).name() == "#ffffff", bild.pixelColor(int(loch.x()), int(loch.y())).name()
assert bild.pixelColor(int(grav.x()) + 30, int(grav.y()) + 25).name() == "#dce6f2"
gruen = sum(1 for x in range(bild.width()) for y in range(bild.height()) if bild.pixelColor(x, y).name() == "#2e7d32")
assert gruen > 10, gruen        # Text-Gravur als Schrift (Striche) statt Hüllrechteck
ok("F6 Abwicklung: Konturen ausgeschnitten (Grund scheint durch), Material kräftiger, Gravur nicht ausgeschnitten, Text-Gravur als Schrift")
print("Alle Tests Schnittfläche 2D/3D bestanden.")
