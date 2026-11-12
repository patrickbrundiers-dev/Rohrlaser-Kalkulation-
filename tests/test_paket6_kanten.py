"""CAD-Entwicklungsplan Paket 6 (Patrick 12.11.2026, „Alle, Reihenfolge 5, 6, K, 7“):
1. Verdeckte Elemente wählen: ein erneuter Klick an derselben Stelle nimmt das Element dahinter (CAD-Plan 3.3).
2. Flächendaten: Größe einer ebenen Fläche, Ø und Länge einer Zylinderfläche, dazu passende Knöpfe (5.2).
3. Kanten zu einer Kontur verbinden: offen/geschlossen, Abzweig, Selbstüberschneidung prüfen; als Sonderkontur
   (Rohr) bzw. Polygon (Blech) genau an der Stelle der Kanten (4.2). Abnahme: Kontur auf 0,1 mm am Modell.
4. Kontur skalieren (4.4).

Aufruf: python tests/test_paket6_kanten.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import auswahl3d as aw, blech, blech3d, editor_kanten, kanten_kontur as kk, rohr3d  # noqa: E402
from rohrlaser import schneidweg as sw, skizze as sk  # noqa: E402
from rohrlaser.ansicht3d import Ansicht3DMitKnoepfen  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


def K(a, b):
    return dict(art=aw.KANTE, a=tuple(a), b=tuple(b))


def ring(pk):
    return [K(pk[i], pk[(i + 1) % len(pk)]) for i in range(len(pk))]


# ------------------------------------------------------------------ T1 Verketten und prüfen
Q = [(0, 0, 0), (10, 0, 0), (10, 5, 0), (0, 5, 0)]
ks = ring(Q)
zug, zu = kk.verketten(kk.stuecke([ks[2], ks[0], ks[3], ks[1]]))           # Reihenfolge und Richtung egal
assert zu and len(zug) == 5, zug
zug, zu = kk.verketten(kk.stuecke(ks[:3]))
assert not zu and math.isclose(kk.luecke(zug)[1], 5.0)
for kanten, grund in ((ks + [K((0, 0, 0), (0, -3, 0))], "mehr als zwei Kanten"),
                      ([ks[0], ks[2]], "getrennte"), ([], "Erst im 3D")):
    try:
        kk.verketten(kk.stuecke(kanten))
        raise AssertionError(grund)
    except ValueError as f:
        assert grund in str(f), f
assert kk.selbstschnitt([(0, 0), (10, 10), (10, 0), (0, 10)]) is not None
assert kk.selbstschnitt([(0, 0), (10, 0), (10, 10), (0, 10)]) is None
ok("T1 Kanten in beliebiger Folge verkettet; Lücke, Abzweig, getrennte Züge und Selbstüberschneidung erkannt")

# ------------------------------------------------------------------ T2 Rohr: Kanten aus dem 3D-Modell
QR = dict(form="Quadratrohr", a=40, b=40, wand=3)
qs = sk.Querschnitt(QR)
L = 300
rechteck = dict(art=sw.RECHTECK, anzahl=1, b=30, h=20, x=120, seite="vorne", q=4)
e = sw.v_ergaenzen(dict(a={}, b={}, laenge=L, konturen=[rechteck]), QR)
n = rohr3d.netz(e, QR, L)
w = Ansicht3DMitKnoepfen()
w.resize(900, 600)
w.show()
w.setzen(n, "QR 40")
app.processEvents()
a = w.ansicht
geo = a.geometrie()
# Kanten des Rechtecks: Konturlinien auf der Fläche „vorne“ (Modellpunkte (−u, v, x): u = 20 -> x-Wert −20; die
# Linien liegen zur Sichtbarkeit 0,4 mm über der Fläche)
rand_k = [dict(art=aw.KANTE, a=g["a"], b=g["b"]) for g in geo.geraden
          if abs(g["a"][0] + 20.4) < 0.05 and abs(g["b"][0] + 20.4) < 0.05 and 100 <= g["a"][2] <= 140
          and 100 <= g["b"][2] <= 140]
assert len(rand_k) == 4, rand_k
z = kk.rohr(qs, rand_k)
assert z["art"] == sw.SONDERKONTUR and z["seite"] == "vorne", z
assert abs(z["x"] - 120) <= 0.1 and abs(z.get("q", 0) - 4) <= 0.1, z
um = z["umriss"]
assert abs(max(p[0] for p in um) - min(p[0] for p in um) - 30) <= 0.1, um
assert abs(max(p[1] for p in um) - min(p[1] for p in um) - 20) <= 0.1, um
assert abs(z["laenge"] - 100) <= 0.2 and abs(z["huelle"] - 30) <= 0.1
# Rückweg: die Sonderkontur im Modell liegt auf 0,1 mm an den gewählten Kanten
e2 = sw.v_ergaenzen(dict(a={}, b={}, laenge=L, konturen=[z]), QR)
n2 = rohr3d.netz(e2, QR, L)
pk2 = [tuple(zz[i:i + 3]) for zz in n2["l"].get("K", []) for i in range(0, len(zz), 3)]
ecken = {tuple(round(c, 1) for c in g[q]) for g in rand_k for q in ("a", "b")}
for p in ecken:
    assert min(math.dist(p, q) for q in pk2) <= 0.1, (p, min(math.dist(p, q) for q in pk2))
ok(f"T2 Rohr: {len(rand_k)} Kanten eines Rechtecks 30 × 20 -> Sonderkontur auf „vorne“, x 120, q 4; "
   "die neue Kontur liegt auf 0,1 mm an den Kanten")

over = [(0, 20, 100), (-20, 20, 100), (-20, 0, 100), (-20, 0, 130), (-20, 20, 130), (0, 20, 130)]
z = kk.rohr(qs, ring(over))
assert z["art"] == sw.SONDERKONTUR and abs(z["huelle"] - 40) <= 0.1 and abs(z["laenge"] - 140) <= 0.1, z
try:
    kk.rohr(qs, ring([(0, 0, 100), (10, 0, 100), (10, 0, 120)]))      # Mitte des Rohrs: keine Außenhaut
    raise AssertionError("innen")
except ValueError as f:
    assert "Außenhaut" in str(f)
kreis = dict(art=aw.KANTE, kreis=dict(m=(0, 20, 50), n=(0, 1, 0), d=10, punkte=[
    (5 * math.cos(2 * math.pi * i / 48), 20.0, 50 + 5 * math.sin(2 * math.pi * i / 48)) for i in range(49)]))
z = kk.rohr(qs, [kreis])
assert z["art"] == sw.BOHRUNG and z["d"] == 10 and z["x"] == 50 and z["seite"] == "oben", z
ok("T2 Rohr: Kontur über die Kante oben/vorne als eine Sonderkontur; Punkt innen abgelehnt; Kreis -> Bohrung Ø10")

# ------------------------------------------------------------------ T3 Blech: auch über eine Biegung
kant = dict(art=blech.KANTTEIL, form=blech.RECHTECK, dicke=2, kantlaenge=300, konturen=[],
            schenkel=[dict(laenge=40, winkel=90), dict(laenge=60, winkel=90), dict(laenge=40)])
zs = blech.zuschnitt(kant)
f, _, gebogen = kk._blech_flach(kant, zs)
assert gebogen


def P(q, h=1.0):
    m, nn = f(q)
    return tuple(m[i] + h * nn[i] for i in range(3))


R = [(100, 20), (140, 20), (140, 60), (100, 60)]                      # liegt über der ersten Biegelinie
ks = []
for i in range(4):
    p0, p1 = R[i], R[(i + 1) % 4]
    pts = [P((p0[0] + (p1[0] - p0[0]) * k / 20, p0[1] + (p1[1] - p0[1]) * k / 20)) for k in range(21)]
    ks += [K(p, q) for p, q in zip(pts, pts[1:])]
z = kk.blech(kant, zs, ks)
assert z["art"] == sw.POLYGON and abs(z["x"] - 120) <= 0.1 and abs(z["y"] - 40) <= 0.1, z
pk = sw.punkte(z["punkte"])
assert len(pk) == 4 and all(min(math.dist((x + 120, y + 40), r) for r in R) <= 0.1 for x, y in pk), pk
flach = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100, konturen=[])
zf = blech.zuschnitt(flach)
nf = blech3d.netz(flach, zf)
assert nf
# flach: Ansicht (y, z, x); Kreis Ø12 bei x 50, y 30 auf der Oberseite
kreis = dict(art=aw.KANTE, kreis=dict(m=(30, 1.5, 50), n=(0, 1, 0), d=12, punkte=[
    (30 + 6 * math.sin(2 * math.pi * i / 48), 1.5, 50 + 6 * math.cos(2 * math.pi * i / 48)) for i in range(49)]))
z = kk.blech(flach, zf, [kreis])
assert z["art"] == sw.BOHRUNG and z["d"] == 12 and abs(z["x"] - 50) <= 0.1 and abs(z["y"] - 30) <= 0.1, z
ok("T3 Blech: Rechteck über die Biegelinie in die Abwicklung zurückgerechnet (auf 0,1 mm), Kreis -> Bohrung Ø12")

# ------------------------------------------------------------------ T4 Skalieren
z = kk.skalieren(dict(art=sw.RECHTECK, anzahl=1, b=20, h=10, r=2, x=50, seite="oben", tiefe=5), 1.5)
assert (z["b"], z["h"], z["r"], z["x"], z["seite"], z["tiefe"]) == (30, 15, 3, 50, "oben", 5), z
z = kk.skalieren(dict(art=sw.POLYGON, punkte="0,0; 10,0,0.4; 10,10", x=5), 2)
assert z["punkte"] == "0,0; 20,0,0.4; 20,20", z["punkte"]
z = kk.skalieren(dict(art=sw.SONDERKONTUR, umriss=[[-1, -2], [1, -2], [1, 2]], laenge=10, huelle=4), 0.5)
assert z["umriss"] == [[-0.5, -1], [0.5, -1], [0.5, 1]] and z["laenge"] == 5 and z["huelle"] == 2
for zeile, faktor in ((dict(art=sw.BOHRUNG, d=8), 0), (dict(art=sw.V_AUSSCHNITT), 2), (dict(art=sw.GRAVUR), 2)):
    try:
        kk.skalieren(zeile, faktor)
        raise AssertionError(zeile)
    except ValueError:
        pass
ok("T4 Skalieren: Maße, Polygonpunkte (Bögen bleiben Bögen) und Umriss gestreckt; Lage, Seite, Tiefe bleiben")

# ------------------------------------------------------------------ T5 Durchschalten und Flächendaten
wahl = a.wahl
wahl.setzen(True, aw.FLAECHE)
app.processEvents()
stelle = None
for x in range(40, 860, 6):
    for y in range(40, 560, 6):
        if len(wahl.kandidaten(x, y)) >= 2:
            stelle = (x, y)
            break
    if stelle:
        break
assert stelle, "keine Stelle mit verdeckter Fläche gefunden"
kand = wahl.kandidaten(*stelle)
erst = wahl.klick(*stelle)
assert aw.schluessel(erst) == aw.schluessel(kand[0])
zweit = wahl.klick(*stelle)
assert aw.schluessel(zweit) == aw.schluessel(kand[1]) and len(wahl.gewaehlt) == 1
assert wahl.durchschalten_text().startswith(f"2 von {len(kand)}"), wahl.durchschalten_text()
for _ in range(len(kand) - 1):
    wahl.klick(*stelle)
assert aw.schluessel(wahl.gewaehlt[0]) == aw.schluessel(kand[0])          # nach dem hintersten wieder vorn
wahl.klick(stelle[0] + 40, stelle[1] + 40)
assert not wahl.durchschalten_text() or wahl.gewaehlt
ok(f"T5 Klick an derselben Stelle: {len(kand)} Flächen hintereinander der Reihe nach gewählt, dann wieder die vordere")

aussen = [e for e in (wahl._flaeche_el(i) for i in range(len(wahl.elemente().flaechen()[1])))
          if e["typ"] == "eben" and abs(e["mitte"][1] - 20) < 0.5]
assert aussen, "Außenfläche oben nicht gefunden"
zeilen = aw.flaeche_masse(aussen[0])
assert zeilen and zeilen[0].startswith("Größe: 300,") and "× 29," in zeilen[0], zeilen     # eben bis zum Eckradius
RU = dict(form="Rundrohr", a=40, wand=3)
nr_ = rohr3d.netz(sw.v_ergaenzen(dict(a={}, b={}, laenge=200, konturen=[]), RU), RU, 200)
w.setzen(nr_, "RR 40")
app.processEvents()
el = wahl.elemente()
mantel = max((wahl._flaeche_el(i) for i in range(len(el.flaechen()[1]))), key=lambda e: e["flaeche"])
zeilen = aw.flaeche_masse(mantel)
assert zeilen and zeilen[0].startswith("Zylinder Ø 40") and "Länge 200" in zeilen[0], zeilen
wahl.waehlen([mantel])
assert any(z_.startswith("Zylinder Ø 40") for z_ in wahl.eigenschaften()), wahl.eigenschaften()
ok("T5 Flächendaten: Außenfläche oben „Größe: 300 × 29,3 mm“ (zwischen den Eckradien), Rundrohr-Mantel „Zylinder Ø 40 mm, Länge 200 mm“")

# ------------------------------------------------------------------ T6 Rohr- und Blech-Editor
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
nr = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(nr, dict(pos=10, artikel="KK-1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=300,
                         stueck=10))
seite = fenster.angebot_oeffnen(nr)
pos = seite.positionen[0]
d = SchneidwegDialog(seite, pos, seite.k.profile["QR 40x40x3"], seite.kopf, seite.k, seite.tabellen)
d.resize(1600, 950)
d.show()
app.processEvents()
rahmen = d.editor
for titel in ("Aus Kanten", "Skalieren"):
    assert rahmen.band.knopf(titel) is not None, titel
a3 = rahmen.ansicht()
a3.wahl.setzen(True)
a3.wahl.waehlen(rand_k)
assert [t for t, *_ in a3.wahl.aktionen_liste()] == ["Kontur aus Kanten"], a3.wahl.aktionen_liste()
assert [b.text() for b in a3.tafel.aktionen] == ["Kontur aus Kanten"]
vor = len(d.eingaben()["konturen"] or [])
r = editor_kanten.aus_kanten(rahmen)
k = d.eingaben()["konturen"]
assert r == vor and len(k) == vor + 1 and k[r]["art"] == sw.SONDERKONTUR and k[r].get("umriss"), k[-1:]
assert rahmen.verlauf.canUndo()
assert editor_kanten.skalieren(rahmen, 2.0, r)
k2 = d.eingaben()["konturen"][r]
assert abs(max(p[0] for p in k2["umriss"]) - min(p[0] for p in k2["umriss"]) - 60) <= 0.2, k2["umriss"]
a3.wahl.waehlen([dict(art=aw.KANTE, a=(-20, 0, 10), b=(-20, 0, 20))])
assert editor_kanten.aus_kanten(rahmen) is None and len(d.eingaben()["konturen"]) == vor + 1     # offen: Meldung
d.close()
ok("T6 Rohr-Editor: Knöpfe „Aus Kanten“ und „Skalieren“, Tafel-Knopf zur Auswahl, Sonderkontur angelegt und "
   "auf 200 % skaliert, offene Kante abgelehnt")

werkstoff = sorted(z_["blech_werkstoff_id"] for z_ in db.zeilen("blech_werkstoffe"))[0]
dlg = BlechDialog(None, db, dict(kant, werkstoff=werkstoff))
dlg.resize(1500, 900)
dlg.show()
app.processEvents()
rb = dlg.editor
assert rb.band.knopf("Aus Kanten") is not None and rb.band.knopf("Skalieren") is not None
r = editor_kanten.aus_kanten(rb, ks)
kb = dlg.eingaben()["konturen"]
assert r is not None and kb[r]["art"] == sw.POLYGON, kb
assert editor_kanten.skalieren(rb, 0.5, r)
pk = sw.punkte(dlg.eingaben()["konturen"][r]["punkte"])
assert abs(max(x for x, _ in pk) - min(x for x, _ in pk) - 20) <= 0.1, pk
fl = dict(art=aw.FLAECHE, koerper="k0", typ="eben", flaeche=1, n=(0, 1, 0), mitte=(0, 0, 0), dreiecke=[])
assert [t for t, *_ in editor_kanten.aktionen(rb, [fl])] == ["Ausschnitt mit Tiefe …"]
dlg.close()
db.con.close()
ok("T6 Blech-Editor: Polygon aus Kanten über die Biegung, auf 50 % skaliert; Fläche gewählt -> Ausklinkung-Knopf")
print("Paket 6 Kanten und Konturen: alle Tests bestanden.")
