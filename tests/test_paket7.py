"""Paket 7 des Plans „Unterlagen nochmals geprüft“ (Patrick 12.11.2026 „Alle, Reihenfolge 5, 6, K, 7“, offene Fragen
nachts nach Empfehlung beantwortet):
P1 Knick-Schließungen abgeschrägt, Radius symmetrisch und asymmetrisch, Verankerung (Nase/Aussparung).
P2 Lochfeld als Lochkreis und als Spirale um ein Rundrohr.
P3 Maßbezug und verlangte Genauigkeit je Kontur in Prüfplan und CAM-Paket (ohne Einfluss auf Zeit und Preis).

Aufruf: python tests/test_paket7.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import knickrahmen as kn, pruefplan, schneidweg as sw, skizze as sk  # noqa: E402


def ok(t):
    print("OK    ", t)


def fehler(f):
    try:
        f()
    except ValueError as x:
        return str(x)
    raise AssertionError("kein Fehler")


def nah(a, b, tol=0.01):
    return abs(a - b) <= tol


QR = dict(form="Quadratrohr", a=40, b=40, wand=2, profil_id="QR 40x40x2")
RR = dict(form="Rundrohr", a=60.3, wand=2, profil_id="RR 60,3x2")
t = 38.0


def drehen(p, beta):
    """Punkt (dx, Tiefe) um den Scheitel (0, t) um β gedreht (so schließt sich der V beim Knicken)."""
    w = math.radians(beta)
    x, y = p[0], p[1] - t
    return (x * math.cos(w) - y * math.sin(w), x * math.sin(w) + y * math.cos(w) + t)


# ------------------------------------------------------------------ P1 Schließungen
assert kn.v_masse(40, 40, 2, 90)["laenge"] == kn.v_masse(40, 40, 2, 90, sl=None)["laenge"]     # spitz wie bisher
g = kn.v_masse(40, 40, 2, 90, sl=kn.schliessung(dict(schliessung=kn.ABGESCHRAEGT, grat=2)))
assert nah(g["w"], 76 + 2) and nah(g["laenge"], 294.96 + 2 * 2), g          # V 2 mm breiter, 2 Gratstücke
halb = kn._halb_v(t, 90, 2, kn.schliessung(dict(schliessung=kn.ABGESCHRAEGT, grat=2)))
assert halb[1] == (-1.0, t) and halb[2] == (1.0, t)
sl_r = kn.schliessung(dict(schliessung=kn.RADIUS_SYM, radius=6))
assert nah(kn.deckel(90, 2, sl_r), math.pi / 2 * 5)                          # β · (R − s/2)
assert nah(kn.deckel(90, 2, dict(sl_r, korrektur=-1)), math.pi / 2 * 5 - 1)
assert not nah(kn.ausgleich(90, 2, sl=sl_r), kn.ausgleich(90, 2))      # mit Innenradius 4 anderer Ausgleich
# asymmetrisch: linke Seite gerade; was rechts fehlt, ist genau das, was die linke Wand nach dem Knicken überdeckt
for beta in (45.0, 60.0, 90.0, 120.0):
    h = kn._halb_v(t, beta, 2, kn.schliessung(dict(schliessung=kn.RADIUS_ASYM, radius=6)))
    d = kn.deckel(beta, 2, sl_r)
    assert h[0][0] == h[1][0] == -d / 2 and h[1][1] == t and h[-1][1] == 0.0, h
    ecke = drehen((0.0, 0.0), beta)                 # Ecke der geraden Seite an der Gegenwand nach dem Knicken
    if beta < 90:
        assert any(nah(p[0] - d / 2, ecke[0], 0.01) and nah(p[1], ecke[1], 0.01) for p in h), (beta, ecke, h)
assert kn._halb_v(t, 90, 2, kn.schliessung(dict(schliessung=kn.RADIUS_ASYM, radius=6)))[-2:] == [
    (kn.deckel(90, 2, sl_r) / 2 + t, t), (kn.deckel(90, 2, sl_r) / 2 + t, 0.0)]  # 90°: Kante entlang der Stegwand
# Verankerung: die Nase der linken Flanke liegt nach dem Knicken genau in der Aussparung der rechten
h = kn._halb_v(t, 90, 2, kn.schliessung(dict(anker_b=8, anker_h=3)))
nase, aussparung = h[1:5], h[6:10]
for p in nase:
    q = drehen(p, 90)
    assert any(nah(q[0], a[0]) and nah(q[1], a[1]) for a in aussparung), (q, aussparung)
for falsch, text in ((dict(schliessung=kn.ABGESCHRAEGT), "Grat"), (dict(schliessung=kn.RADIUS_SYM), "Außenradius"),
                     (dict(anker_b=5), "Breite und Höhe"), (dict(schliessung="eckig"), "unbekannte Schließung")):
    assert text in fehler(lambda: kn.schliessung(falsch)), falsch
assert "zu hoch" in fehler(lambda: kn._halb_v(t, 90, 2, kn.schliessung(dict(anker_b=8, anker_h=40))))
ok("P1 Schließungen: abgeschrägt (Grat 2 -> V 78 mm), Deckel β·(R − s/2) + Korrektur, asymmetrisch mit gerader "
   "Seite (bis 90° geneigte Flanke, ab 90° Kante entlang der Stegwand), Nase passt nach dem Knicken in die Aussparung")

# Rahmen, Schneidweg-Rechner, 3D
BLOCK = dict(schenkel=[500, 300, 500, 300], beta=90, geschlossen=True, steg="unten")
for extra in (dict(schliessung=kn.ABGESCHRAEGT, grat=1.5), dict(schliessung=kn.RADIUS_SYM, radius=5, korrektur=-0.5),
              dict(schliessung=kn.RADIUS_ASYM, radius=5), dict(anker_b=6, anker_h=2)):
    eing, r = kn.anwenden(dict(a={}, b={}, konturen=[]), dict(BLOCK, **extra), QR)
    vz = [z for z in eing["konturen"] if z["art"] == sw.V_AUSSCHNITT]
    assert len(vz) == 3 and all(all(z.get(k_) == v for k_, v in extra.items()) for z in vz), vz
    assert kn.passt(eing, r)
    erg = sw.rechnen(eing, QR, (10, 50))
    assert not erg["fehler"], erg["fehler"]
    um = kn.zeile_ergaenzen(vz[0], QR)["umriss"]
    umfang = sum(math.dist(um[i], um[i - 1]) for i in range(len(um)))
    vs = [s_ for s_ in erg["schritte"] if s_.get("art") == sw.V_AUSSCHNITT]
    assert nah(vs[0]["laenge"], umfang, 0.1), (vs[0]["laenge"], umfang)
    assert kn.schliessung_text(vz[0]).strip(", ") in vs[0]["text"], vs[0]["text"]
    from rohrlaser import rohr3d
    assert rohr3d.netz(eing, QR, r["laenge"])["p"]
ok("P1 Rahmen: Schließung und Verankerung in allen V-Zeilen, Schneidweg = Umfang des Umrisses, Text, 3D-Netz")
mit_r = kn.rahmen(dict(BLOCK, schliessung=kn.RADIUS_SYM, radius=6), QR)
assert mit_r["laenge"] < kn.rahmen(BLOCK, QR)["laenge"], "Radius: größerer Ausgleich, kürzeres gestrecktes Rohr"

# ------------------------------------------------------------------ P2 Lochkreis und Spirale
lk = dict(art=sw.LOCHFELD, anzahl=1, d=8, reihen=1, x=200, muster=sk.LOCHKREIS, lk_d=50, lk_n=6)
lg, _, n = sw.kontur(lk)
assert n == 6 and nah(lg, math.pi * 8)
loecher = sk.lochfeld(lk)
assert len(loecher) == 6 and all(nah(math.hypot(dx, dq), 25) for dx, dq in loecher) and loecher[0] == (25.0, 0.0)
assert sw.kontur(dict(lk, anzahl=3, abstand=100))[2] == 18
assert "berühren sich" in fehler(lambda: sw.kontur(dict(lk, lk_n=40)))
assert "Teilkreis" in fehler(lambda: sw.kontur(dict(lk, lk_d=6)))
sp = dict(art=sw.LOCHFELD, anzahl=1, d=6, reihen=1, muster=sk.SPIRALE, lk_n=12, sp_winkel=45, sp_steigung=120)
qs = sk.Querschnitt(RR)
pl = sk.lochfeld(sp, qs.umfang)
assert len(pl) == 12 and nah(pl[8][0], 120.0) and nah(pl[8][1], 0.0) and nah(pl[2][1], qs.umfang / 4), pl[:3]
lagen = [d_ for d_ in sk.lagen([sp], 1000, qs)]
xs = [d_["x"] + (d_["eingabe"].get("_dx") or 0) for d_ in lagen]
assert nah((min(xs) + max(xs)) / 2, 500.0), (min(xs), max(xs))         # ohne Lage mittig auf dem Teil
erg = sw.rechnen(dict(a={}, b={}, konturen=[sp, lk]), RR, (10, 50))
assert not erg["fehler"] and erg["einstiche"] == 2 + 12 + 6, (erg["fehler"], erg["einstiche"])
texte = " ".join(s_["text"] for s_ in erg["schritte"])
assert "Spirale 12 Löcher je 45°" in texte and "Lochkreis 6 × auf Ø 50" in texte, texte
from rohrlaser import rohr3d  # noqa: E402
assert rohr3d.netz(dict(a={}, b={}, konturen=[sp]), RR, 1000)["p"]
ok("P2 Lochkreis 6 × Ø 8 auf Ø 50 (wiederholt längs), Spirale 12 Löcher je 45° mit 120 mm Steigung mittig auf dem "
   "Rohr, Einstiche, Texte, 3D")

# ------------------------------------------------------------------ P3 Maßbezug und Genauigkeit
import json  # noqa: E402

p = dict(laenge=400, technik=json.dumps(dict(a={}, b={}, konturen=[
    dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="vorne", massbezug="Kante vorherige Fläche", genauigkeit=0.05),
    dict(art=sw.BOHRUNG, anzahl=1, d=10, x=300)])))
m = pruefplan.merkmale(p)
genau = [z for z in m if "(verlangt)" in z["toleranz"]]
assert len(genau) == 2 and all(z["toleranz"] == "± 0,05 mm (verlangt)" for z in genau), m
assert all("Bezug Kante vorherige Fläche" in z["lage"] for z in genau)
assert [z["toleranz"] for z in m if z["merkmal"].startswith("Bohrung") and "(verlangt)" not in z["toleranz"]] == [
    "± 0,2 mm", "± 0,5 mm"]
from rohrlaser import cam_paket  # noqa: E402

zeilen = cam_paket.massbezuege([dict(p, pos=10, artikel="R-1")])
assert zeilen == [[10, "R-1", "1: Bohrung", "100", "vorne", "Kante vorherige Fläche", "0,05"]], zeilen
ok("P3 Prüfplan: verlangte Genauigkeit ± 0,05 statt ISO 2768, Bezug in der Lage; CAM-Paket Massbezuege.csv")

# ------------------------------------------------------------------ Editoren
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.knickrahmen_dialog import KnickrahmenDialog  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

kd = KnickrahmenDialog(None, QR, None, {})
kd.schenkel.setText("500; 300; 500; 300")
kd.schliessung.art.setCurrentText(kn.RADIUS_SYM)
kd.schliessung.radius.setValue(6)
kd.schliessung.anker_b.setValue(6)
kd.schliessung.anker_h.setValue(2)
b = kd.block()
assert b["schliessung"] == kn.RADIUS_SYM and b["radius"] == 6 and b["anker_b"] == 6 and kd.ok_knopf.isEnabled(), b
ok("Knickrahmen-Fenster: Schließung, Außenradius und Verankerung im Block")

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "p7.db")
fenster = Hauptfenster(db, tmp, stumm=True)
nr = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(nr, dict(pos=10, artikel="P7", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1200,
                         stueck=2))
seite = fenster.angebot_oeffnen(nr)
d = SchneidwegDialog(seite, seite.positionen[0], seite.k.profile["QR 40x40x3"], seite.kopf, seite.k, seite.tabellen)
d.resize(1600, 950)
d.show()
app.processEvents()
d.zeile_neu(dict(art=sw.V_AUSSCHNITT, anzahl=1, beta=90, x=600, seite="unten"))
d.zeile_neu(dict(art=sw.LOCHFELD, anzahl=1, d=8, reihen=1, x=200, seite="oben"))
rahmen = d.editor
rahmen.aktualisieren()
app.processEvents()
ei = rahmen.eigenschaften
ei.zeigen("kontur:0")
assert "Schließung" in ei.felder and "Verankerung Breite" in ei.felder and "Maßbezug" in ei.felder
ei.felder["Schließung"].setCurrentText(kn.ABGESCHRAEGT)
ei.felder["Schließung"].activated.emit(1)
app.processEvents()
ei.zeigen("kontur:0")
assert "Grat" in ei.felder
ei.zeigen("kontur:1")
assert "Muster" in ei.felder and ei.felder["Muster"].findData(sk.SPIRALE) < 0       # Spirale nur am Rundrohr
ei.felder["Muster"].setCurrentIndex(ei.felder["Muster"].findData(sk.LOCHKREIS))
ei.felder["Muster"].activated.emit(1)
app.processEvents()
ei.zeigen("kontur:1")
assert "Teilkreis-Ø" in ei.felder and "Löcher im Kreis" in ei.felder and "Genauigkeit" in ei.felder
k0, k1 = d.eingaben()["konturen"][:2]
assert k0.get("schliessung") == kn.ABGESCHRAEGT and k1.get("muster") == sk.LOCHKREIS, (k0, k1)
d.close()
db.con.close()
ok("Rohr-Editor: Eigenschaften Schließung/Grat/Verankerung am V, Muster Lochkreis (Spirale nur am Rundrohr), "
   "Maßbezug und Genauigkeit je Kontur")
print("Paket 7: alle Tests bestanden.")
