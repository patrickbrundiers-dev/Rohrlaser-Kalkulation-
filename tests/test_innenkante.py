"""Konturen bei 90° zur Oberfläche: Innenkante maßhaltig (Patrick 26.10.2026, Variante C), 3D eben.

- I1 Rundrohr 2D: Kontur innen wie gezeichnet, außen am Umfang um R/ri breiter; 3D parallel: außen wie gezeichnet
- I2 Quadratrohr mit Eckradius: Kontur bis in die Rundung 2D innen maßhaltig, 3D eben (parallel zur Wandnormale)
- I3 Schnittkörper folgen (Text, Breite innen/außen), ebene Wand ohne Rundung unverändert
- I4 Abwicklung (Rundrohr): 2D-Konturen außen breiter, 3D eben wie gezeichnet; Schneidweg Rundrohr außen länger
- I5 Hilfen: innen_massgebend auf ebener Wand unverändert, strahl_bis

Aufruf: python tests/test_innenkante.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import dreid, rohr3d, schneidweg as sw, schnittflaeche as sf  # noqa: E402

RR = dict(form="Rundrohr", a=60, wand=3)
QR = dict(form="Quadratrohr", a=80, b=80, wand=3)          # Außenradius 6 (Vorgabe), Ebene bis 34 ab Mitte
K = dict(art="Rechteck", anzahl=1, b=20, h=20, x=200, seite="oben", r=0)


def ok(t):
    print("OK    ", t)


def breite(e, profil):
    """Breite am Umfang (Abwicklung außen) der ersten Kontur."""
    bau = {}
    rohr3d.netz(e, profil, 400, bau=bau)
    q = bau["loch_zeile"][0][0]
    return max(p[0] for p in q) - min(p[0] for p in q)


# ------------------------------------------------------------------ I1 Rundrohr
b2 = breite(dict(konturen=[K]), RR)
b3 = breite(dict(d3=True, konturen=[dict(K, schnitt="parallel")]), RR)
assert abs(b2 - 20 * 30 / 27) < 0.05, b2                 # innen 20, außen 20·R/ri
assert abs(b3 - 20) < 0.05, b3                           # 3D eben: außen wie gezeichnet
assert abs(breite(dict(konturen=[dict(K, schnitt="parallel")]), RR) - b2) < 1e-6    # ohne 3D am Teil: 2D
ok("I1 Rundrohr: 2D innen maßhaltig, außen um R/ri breiter; 3D parallel außen wie gezeichnet")

# ------------------------------------------------------------------ I2 Eckradius
k_rand = dict(K, q=28)                                   # 18 … 38: 4 mm über die Ebene (34) in die Rundung
assert abs(breite(dict(konturen=[k_rand]), QR) - 24.0) < 0.05     # innen 16 eben + 4 auf r 3 → außen 4·6/3
eben = breite(dict(d3=True, konturen=[dict(k_rand, schnitt="parallel")]), QR)
assert abs(eben - (16 + 6 * math.asin(4 / 6))) < 0.05, eben        # parallel auf den Bogen gelegt
assert abs(breite(dict(konturen=[dict(K, q=0)]), QR) - 20) < 1e-6  # ebene Wand: unverändert
ok("I2 Eckradius: 2D innen maßhaltig (außen breiter), 3D eben parallel zur Wandnormale, ebene Wand unverändert")

# ------------------------------------------------------------------ I3 Schnittkörper


def koerper(e, profil):
    w = rohr3d.netz(e, profil, 400)["wk"][0]
    o = [w["o"][i:i + 3] for i in range(0, len(w["o"]), 3)]
    u = [w["u"][i:i + 3] for i in range(0, len(w["u"]), 3)]
    return w, o, u


w, o, u = koerper(dict(konturen=[dict(K, q=0)]), RR)
assert "Innenkante maßhaltig" in w["t"] and len(o) == len(u) and w["d"]
assert max(abs(p[0]) for p in o) > max(abs(p[0]) for p in u) + 1      # außen breiter als innen (Strahl radial)
w, o, u = koerper(dict(d3=True, konturen=[dict(K, q=0, schnitt="parallel")]), RR)
assert abs(max(p[0] for p in o) - max(p[0] for p in u)) < 0.01 and abs(min(p[0] for p in o) + max(p[0] for p in o)) < 0.01
w, o, u = koerper(dict(d3=True, konturen=[dict(k_rand, schnitt="parallel")]), QR)
assert "3D eben" in w["t"] and abs(max(abs(p[0]) for p in o) - max(abs(p[0]) for p in u)) < 0.01
w, o, u = koerper(dict(konturen=[dict(K, q=0)]), QR)
assert "Innenkante" not in w["t"] and len(o) == len(u)   # ebene Wand: Körper wie bisher
ok("I3 Schnittkörper: 2D außen breiter, 3D eben senkrecht durch, ebene Wand wie bisher")

# ------------------------------------------------------------------ I4 Abwicklung und Schneidweg
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import skizze_widget  # noqa: E402
app = QApplication.instance() or QApplication([])
s_ = skizze_widget.Skizze(RR, 400)
s_.eingaben = dict(konturen=[K])
assert abs(s_._faktor_aussen(K) - 30 / 27) < 1e-9
s_.eingaben = dict(d3=True, konturen=[dict(K, schnitt="parallel")])
assert s_._faktor_aussen(dict(K, schnitt="parallel")) == 1.0
assert s_._faktor_aussen(dict(art="Gravur", anzahl=1)) == 1.0
ll = dict(art=sw.LANGLOCH, anzahl=1, l=40, b=10, x=100)
zwei = sw.rechnen(dict(a={}, b={}, konturen=[ll]), RR, (10, 50))["schritte"][2]["laenge"]
drei = sw.rechnen(dict(a={}, b={}, d3=True, konturen=[dict(ll, schnitt="parallel")]), RR, (10, 50))
assert abs(drei["schritte"][2]["laenge"] - (2 * 30 + math.pi * 10)) < 0.01 and zwei > drei["schritte"][2]["laenge"] + 0.5
qr3 = sw.rechnen(dict(a={}, b={}, d3=True, konturen=[dict(ll, schnitt="parallel")]), QR, (10, 50))
assert "parallel (3D)" in qr3["schritte"][2]["text"]
ok("I4 Abwicklung Rundrohr außen breiter (2D), 3D wie gezeichnet; Schneidweg 2D länger, Quadratrohr parallel (3D)")

# ------------------------------------------------------------------ I5 Hilfen
cum = [0.0, 10.0, 20.0, 30.0]
assert sf.innen_massgebend([(5.0, 0.0), (15.0, 1.0)], cum, cum) == [(5.0, 0.0), (15.0, 1.0)]
quadrat = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
assert abs(sf.strahl_bis(quadrat, (0, 5), (0, -1)) - 4) < 1e-9 and sf.strahl_bis(quadrat, (0, 5), (0, 1)) is None
assert not sf.innen_2d(dict(art="Bohrung", wand="beide"), {}) and sf.innen_2d(dict(art="Bohrung"), {})
assert not sf.innen_2d(dict(art="Bohrung", d3=True), dict(d3=True))
assert dreid.umriss_2d_faktor([], 60, 3) == 1.0
ok("I5 Hilfen: innen_massgebend, strahl_bis, innen_2d, umriss_2d_faktor")
print("Alle Tests Innenkante bestanden.")
