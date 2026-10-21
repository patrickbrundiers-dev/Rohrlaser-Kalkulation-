"""Prüft das Ineinanderlegen von Gehrungen mit Drehung um die eigene Achse (Patrick 21.10.2026):
- Rechnung: gleiche Gehrungen 45/45 und ungleiche 45/20 (Abstand senkrecht zur steileren Fläche, kein gemeinsamer
  Schnitt), gleiche Lage bringt nichts, gerades Ende neben Gehrung wie bisher; Rundrohr.
- Drehungen: Rechteckrohr 0/180, Quadrat- und Rundrohr 0/90/180/270; nie gewendet; feste Naht und unbekannte Naht
  sperren die freie Drehung; feste Naht auf Breit- und Schmalseite nie auf einer Stange.
- Optimierung: weniger Stangen nur mit freier Drehung, nie überbelegt, Untergrenze gültig, reproduzierbar,
  Laufzeit großer Aufträge in Schritten begrenzt.
- Angebot: Positionen mit Gehrung aus dem Schneidweg-Rechner, Ergebnis mit Drehung, Trennung 'Gehrung ineinander',
  eingespartem Material; Prüfsumme älterer Angebote ohne Gehrungen unverändert.

Aufruf: python tests/test_gehrung.py
"""
import math
import random
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import naht, optimierung as opt, rechnen  # noqa: E402
from rohrlaser.optimierung import FEST, FREI, UNBEKANNT, Gruppe, Teil  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.01):
    assert abs(a - b) <= tol, (a, b)


KERF, ABSTAND = 0.2, 10.0
D = 2 * KERF + ABSTAND                  # 2 Schnitte
G45 = D / math.cos(math.radians(45))    # Abstand entlang der Achse bei 45°


def gruppe(teile=(), stange=1000, q=("Kasten", 60, 40)):
    g = Gruppe("RE 60x40x3", "S235", stange, 10, 50, KERF, ABSTAND, querschnitt=q)
    g.teile = list(teile)
    return g


def rahmen(n, laenge=300, a=(45, 90), b=(45, 90), zeile=1, drehung=FREI, naht_w=None):
    """Rahmenteil: beide Enden 45° über die 60er Seite, an beiden Enden rechts (90°) am längsten (Trapez)."""
    return [Teil(zeile, 10 * zeile, f"R{zeile}", i, laenge, a is None, b is None, 200, 200, a, b, drehung, naht_w)
            for i in range(1, n + 1)]


# ------------------------------------------------------------------ G1 Rechnung
g = gruppe()
nah(opt.gehrung_trennung(g, (45, 90), 0, (45, 90), 0), G45)               # gleiche Lage: Trapeze stoßen nur an
nah(opt.gehrung_trennung(g, (45, 90), 0, (45, 90), 180), G45 - 60)        # 180° gedreht: 60 mm Überlappung
nah(opt.gehrung_trennung(g, (45, 90), 0, (45, 270), 0), G45 - 60)         # dasselbe ohne Drehung
t1, t2 = rahmen(1, zeile=1)[0], rahmen(1, zeile=2)[0]
nah(opt.trennung_teile(g, t1, 0, t2, 0), D)                                # nie länger als 2 Schnitte
nah(opt.trennung_teile(g, t1, 0, t2, 180), G45 - 60)
assert opt.ineinander(g, t1, 0, t2, 180) and not opt.ineinander(g, t1, 0, t2, 0)
# 45° neben 20° (beide über die 60er Seite): Überlappung etwa die Tiefe der flacheren Gehrung
t20 = rahmen(1, a=(20, 270), zeile=3)[0]
s = opt.trennung_teile(g, t1, 0, t20, 0)
nah(s, G45 + 30 * (1 - math.tan(math.radians(20))) - 30 - 30 * math.tan(math.radians(20)))
assert -8 < s < -7 and D - s > 17                                          # rund 17,5 mm gespart
# über die 40er Seite: Tiefe 40 mm
nah(opt.gehrung_trennung(g, (45, 0), 0, (45, 180), 0), G45 - 40)
# gerades Ende neben Gehrung: wie bisher 2 Schnitte; zwei gerade Enden: gemeinsamer Schnitt
gerade = Teil(4, 40, "G", 1, 300, True, True, 200, 200)
nah(opt.trennung_teile(g, t1, 0, gerade, 0), D)
nah(opt.trennung_teile(g, gerade, 0, gerade, 0), KERF)
# Rundrohr Ø 42,4: Tiefe = Radius × tan
r = gruppe(q=("Rund", 21.2))
nah(opt.gehrung_trennung(r, (30, 0), 0, (30, 180), 0), D / math.cos(math.radians(30)) - 2 * 21.2 * math.tan(
    math.radians(30)))
nah(opt.gehrung_tiefe(g, (45, 90)), 30)
nah(opt.gehrung_tiefe(g, (45, 0)), 20)
ok("G1 Gehrungen ineinander: 45/45 (60 bzw. 40 mm), 45/20, gleiche Lage ohne Gewinn, gerade wie bisher, Rundrohr")

# ------------------------------------------------------------------ G2 Drehungen und Naht
assert opt.drehungen(g, t1) == (0, 180) and opt.drehungen(gruppe(q=("Kasten", 40, 40)), t1) == (0, 90, 180, 270)
assert opt.drehungen(r, t1) == (0, 90, 180, 270) and opt.drehungen(gruppe(q=()), t1) == (0,)
unb = rahmen(1, drehung=UNBEKANNT)[0]
assert opt.drehungen(g, unb) == (0,)
f0, f180, f90 = (rahmen(1, drehung=FEST, naht_w=w)[0] for w in (0, 180, 90))
assert opt.drehungen(g, f0, 0) == (0,) and opt.drehungen(g, f0, 180) == (180,) and opt.drehungen(g, f180, 0) == (180,)
assert opt.naht_lagen(g, [f0, f180]) == [0, 180] and opt.naht_lagen(g, [f0, f90]) == []
assert not opt.vertraeglich(g, [f0, f90]) and opt.vertraeglich(gruppe(q=("Kasten", 40, 40)), [f0, f90])
ok("G2 Drehungen: RE 0/180, QR und RR 0/90/180/270, unbekannt 0, fest nach der Naht der Stange")

# ------------------------------------------------------------------ G3 Anordnen und Verbrauch
for art, teile_, ineinander_soll in (("frei", rahmen(3), 2), ("unbekannt", rahmen(3, drehung=UNBEKANNT), 0),
                                     ("fest 0°", rahmen(3, drehung=FEST, naht_w=0), 0)):
    g = gruppe(teile_)
    f = opt.anordnen(teile_, g)
    assert opt.gehrungen_ineinander(g, f) == ineinander_soll, (art, f)
    soll = 10 + 900 + (2 * (G45 - 60) if ineinander_soll else 2 * D) + KERF
    nah(opt.verbrauch(g, f), soll)
    opt.pruefe_drehungen(g, f)
f = opt.anordnen(rahmen(3), gruppe())
assert [d for _, d in f] in ([0, 180, 0], [180, 0, 180]), f                 # abwechselnd gedreht, nie gewendet
# feste Naht 0° und 180° im Wechsel: Naht der Stange bleibt, die Teile liegen trotzdem gegeneinander
wechsel = rahmen(1, drehung=FEST, naht_w=0, zeile=1) + rahmen(1, drehung=FEST, naht_w=180, zeile=2)
g = gruppe(wechsel)
assert opt.gehrungen_ineinander(g, opt.anordnen(wechsel, g)) == 1
# unzulässige Drehung wird von der Prüfung erkannt
try:
    opt.pruefe_drehungen(gruppe(), [(unb, 180)])
    raise AssertionError("Drehung eines Teils mit unbekannter Naht nicht erkannt")
except AssertionError as e:
    assert "unzulässige Drehung" in str(e)
ok("G3 Anordnen: frei abwechselnd 0°/180°, unbekannt und fest ohne Drehung, feste Naht 0/180 im Wechsel")

# ------------------------------------------------------------------ G4 Optimierung
# 7 Rahmenteile je 300 mm, Stange 1150: nutzbar bis 1100 ab Endbeschnitt 10. Ineinander passen 4 (1074 mm),
# ohne Drehung nur 3 (10 + 1200 + 3·10,4 > 1100)
for drehung, soll in ((FREI, 2), (UNBEKANNT, 3)):
    g = gruppe(rahmen(7, drehung=drehung), 1150)
    st = opt.optimiere(g)
    opt.pruefe([g], [st])
    assert len(st) == soll, (drehung, len(st), [len(s) for s in st])
    assert opt.untergrenze(g) <= len(st)
gerade_g = gruppe([Teil(1, 10, "G", i, 300, True, True, 200, 200) for i in range(1, 8)])
assert len(opt.optimiere(gerade_g)) == 3                                     # ohne Gehrung wie bisher
# Breit- und Schmalseite nie auf einer Stange
g = gruppe(rahmen(2, drehung=FEST, naht_w=0, zeile=1, laenge=100) + rahmen(2, drehung=FEST, naht_w=90, zeile=2,
                                                                             laenge=100))
st = opt.optimiere(g)
opt.pruefe([g], [st])
assert len(st) == 2 and all(len({t.naht for t, _ in s}) == 1 for s in st), st
# Zufallsaufträge: nie überbelegt, Untergrenze gültig, reproduzierbar
rnd = random.Random(2110)
for lauf in range(60):
    tl = []
    for z in range(rnd.randint(1, 5)):
        w = rnd.choice([0, 15, 30, 45])
        a = None if not w else (w, rnd.choice([0, 90, 180, 270]))
        b = None if rnd.random() < 0.3 else (rnd.choice([20, 30, 45]), rnd.choice([0, 90, 180, 270]))
        art = rnd.choice([FREI, FREI, UNBEKANNT, FEST])
        tl += [Teil(z + 1, z, f"Z{z}", i, round(rnd.uniform(80, 900), 1), a is None, b is None, 200, 200, a, b, art,
                    rnd.choice([0, 180]) if art == FEST else None) for i in range(1, rnd.randint(1, 12))]
    q = rnd.choice([("Kasten", 60, 40), ("Kasten", 40, 40), ("Rund", 21.2)])
    g = gruppe(tl, rnd.choice([2000, 3000, 6000]), q)
    st = opt.optimiere(g)
    opt.pruefe([g], [st])
    assert opt.untergrenze(g) <= len(st) <= len(opt.manuell(g)), lauf
    g2 = gruppe(list(reversed(tl)), g.stange, q)
    assert [[(t.zeile, t.nr, d) for t, d in s] for s in opt.optimiere(g2)] == \
        [[(t.zeile, t.nr, d) for t, d in s] for s in opt.optimiere(gruppe(list(reversed(tl)), g.stange, q))], lauf
ok("G4 Optimierung: freie Drehung spart eine Stange, gesperrt nicht; Breit/Schmal getrennt; 60 Zufallsaufträge")

# großer Auftrag: 6 Typen, 240 Teile mit Gehrungen
start = time.process_time()
tl = []
for z, (L, w) in enumerate(((620, 45), (480, 45), (1150, 30), (350, 45), (760, 20), (905, 45))):
    tl += rahmen(40, laenge=L, a=(w, 90), b=(w, 90), zeile=z + 1)
g = gruppe(tl, 6000)
st = opt.optimiere(g)
opt.pruefe([g], [st])
dauer = time.process_time() - start
ohne = gruppe([Teil(t.zeile, t.pos, t.artikel, t.nr, t.laenge, False, False, 200, 200) for t in tl], 6000)
n_ohne = len(opt.optimiere(ohne))
assert len(st) < n_ohne and dauer < 120, (len(st), n_ohne, dauer)
ok(f"G5 großer Auftrag (240 Teile mit Gehrung): {len(st)} statt {n_ohne} Stangen, {dauer:.1f} s Rechenzeit")

# ------------------------------------------------------------------ G6 Angebot (rechnen)
from rohrlaser.datenbank import Datenbank  # noqa: E402
import tempfile  # noqa: E402
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
kopf = dict(maschine="T03", stange=6000)
geh = dict(a_gerade="nein", b_gerade="nein", a_ende=naht.ende_text(45, 90), b_ende=naht.ende_text(45, 90))
pos = [dict(pos=10, artikel="Rahmen", profil_id="RE 60x40x3", werkstoff_id="S355-10219", laenge=1450, stueck=8, **geh),
       dict(pos=20, artikel="Rahmen fest", profil_id="RE 60x40x3", werkstoff_id="S355-10219", laenge=1450, stueck=4,
            naht_vorgabe=naht.FEST, naht_winkel=0, **geh),
       dict(pos=30, artikel="gerade", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=3)]
erg = rechnen.optimieren(kopf, pos, k)
teile = [t for s in erg["stangen"] for t in s["teile"]]
inein = [t for t in teile if t["trennung"] == "Gehrung ineinander"]
assert inein and all(t["material_gespart"] > 0 for t in inein), teile
assert {t["drehung"] for t in teile if t["pos"] == 10} == {0, 180}
assert all(t["drehfreigabe"] == opt.FEST and t["naht"] == 0 for t in teile if t["pos"] == 20)
assert all(t["lage"] == "normal" for t in teile if t["pos"] == 30)
for s, w in zip(erg["stangen"], rechnen.stangen_werte(erg, kopf, pos, k, db.tabellen())):
    assert w["pruefung"] == "OK", (s, w)
# Prüfsumme: Angebot ohne Gehrung und Naht wie vor 0.6.23 (nur die alten Werte je Teil)
alt = [dict(pos=10, artikel="A", profil_id="RE 60x40x3", werkstoff_id="S355-10219", laenge=800, stueck=2)]
gr, _, _ = rechnen.gruppen_bilden(kopf, alt, k)
assert all(len(rechnen.teil_kennung(t)) == 9 for t in gr[0].teile)
einseitig = [dict(alt[0], a_gerade="nein")]
gr, _, _ = rechnen.gruppen_bilden(kopf, einseitig, k)
assert all(rechnen.teil_kennung(t)[-1] == "nie wenden" for t in gr[0].teile)
ok("G6 Angebot: Drehung, Nahtvorgabe und eingespartes Material im Ergebnis, keine Stange überbelegt, Prüfsumme")

# ------------------------------------------------------------------ G7 Anzeige
g = gruppe()
nah(opt.kante(g, (45, 0), 0)[0], 0)
nah(opt.kante(g, (45, 0), 0)[1], 40)                                         # oben am längsten: unten zurück
nah(opt.kante(g, (45, 180), 0)[0], 40)
nah(opt.kante(g, (45, 180), 180)[1], 40)                                    # 180° gedreht = wie 0°
assert max(opt.kante(g, (45, 90), 0)) < 1e-9                                  # Schräge seitlich: von der Seite gerade
nah(opt.kante(g, (45, 90), 0, 270)[0], 60)                                     # von oben sichtbar (Breite 60)
assert opt.ansicht(g, [(t1, 0)]) == 270 and opt.ansicht(g, [(rahmen(1, a=(45, 0), b=(45, 0))[0], 0)]) == 0
for s_ in erg["stangen"]:
    for t1_, t2_ in zip(s_["teile"], s_["teile"][1:]):
        u1, u2 = rechnen.umriss(t1_), rechnen.umriss(t2_)
        assert u1[1] <= u2[0] + 0.1 and u1[2] <= u2[3] + 0.1, (t1_, t2_)       # gezeichnet ohne Überlappung
assert all(t.get("kante_a") and t["ansicht"] == "von oben" for t in teile if t["pos"] in (10, 20))
assert all("kante_a" not in t for t in teile if t["pos"] == 30)
assert all(t["naht_text"] == "Naht 0° fest" for t in teile if t["pos"] == 20)
aw = {a["profil"]: a for a in erg["auswertung"]}
assert aw["RE 60x40x3"]["gehrung_mm"] > 0 and aw["QR 40x40x3"]["ohne_drehung"] is None
assert aw["RE 60x40x3"]["ohne_drehung"] is not None and "Gehrungen ineinander" in aw["RE 60x40x3"]["bewertung"]
assert rechnen.drehung_text(3, 2, 90.4) == "; Drehen spart 1 Stange, Gehrungen ineinander 90 mm"
assert rechnen.drehung_text(2, 2, 0) == "; Drehen bringt keine Verbesserung"
from rohrlaser import ausgabe, pdf  # noqa: E402
wp = ausgabe.werkstatt(kopf, pos, erg, k, db.tabellen())
assert any(t["naht_text"] for m in wp["muster"] for t in m["teile"])
ziel = Path(tempfile.mkdtemp()) / "Werkstattpapiere.pdf"
pdf.werkstatt_pdf(ziel, kopf, wp)
assert ziel.stat().st_size > 5000
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.angebot_fenster import Stangenbild  # noqa: E402
app = QApplication.instance() or QApplication([])
bild = Stangenbild()
bild.resize(1200, 400)
bild.setzen(erg)
bild.grab()
ok("G7 Anzeige: Schnittkanten im Stangenbild ohne Überlappung, Naht im Schnittplan, Vergleich ohne Drehen, PDF")
print("OK: Gehrungen ineinander")
