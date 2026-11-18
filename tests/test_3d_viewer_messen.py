"""3D-Viewer als Arbeitswerkzeug, Teil 2 (Plan Patrick 18.11.2026, Pakete V2 Messen und V3 Bedienung).

V2 Messen präzise
- M1 Fangpunkt auf dem Rohrmantel liegt genau auf dem Profil-Ø (nicht auf der Sehne des Netzes).
- M2 Wandstärke: Rundrohr außen und innen genau die Profilwand (aus den Ø), Vierkantrohr über die ebenen Flächen.
- M3 Schnittpunkt zweier Kanten; windschiefe Kanten ohne Schnittpunkt.
- M4 Näherung: Punkte auf gewölbten, nicht erkannten Flächen sind mit „≈“ gekennzeichnet, exakte nicht.
- M5 Schnittlänge je Merkmal aus der Rechnung (Editor) in der Mess-Tafel, ohne eigene Rechnung.
V3 Bedienung
- B1 Tasten 1–6/0 Standardansichten, F einpassen (Blickrichtung bleibt, Modell im Bild), V Vorher-Nachher.
- B2 grobe Stufe beim Drehen passt sich der gemessenen Zeichenzeit an (Grenzen GROB_MIN/GROB_DREIECKE).
- B3 Leiste: Symbole gesetzt, Einpassen-Knopf, Vorher-Knopf nur mit gemerktem Stand.
- B4 Vorher-Nachher im Rohr-Editor: Stand beim Öffnen bleibt, nach einer Änderung gestrichelt darüber.

Aufruf: python tests/test_3d_viewer_messen.py
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, rohr3d, schneidweg as sw  # noqa: E402
from rohrlaser.ansicht3d import Ansicht3D, Modell  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.messen3d import FLAECHE, KREISMITTE, Geometrie, schnittpunkt  # noqa: E402


def ok(t):
    print("OK    ", t)


db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
rund = next(pr for n, pr in k.profile.items() if n.startswith("RR"))
D, T = float(rund["a"]), float(rund["wand"])

# ------------------------------------------------------------------ M1 Rohrmantel genau
netz = rohr3d.netz(dict(quelle=sw.QUELLE, konturen=[]), rund, 300)
mo = Modell(netz)
g = Geometrie(mo, netz)
aussen = innen = None
for nr, (i, j, kk, _, n) in enumerate(mo.dreiecke):
    z = g._zylinder(mo.punkte[i], mo.punkte[j], mo.punkte[kk], n)
    if z and z["aussen"] and aussen is None:
        aussen = nr
    if z and not z["aussen"] and innen is None:
        innen = nr


def mitte(nr):
    i, j, kk, _, _ = mo.dreiecke[nr]
    return tuple(sum(mo.punkte[q][a] for q in (i, j, kk)) / 3 for a in range(3))


fern = lambda q: (1e6, 1e6, 0.0)   # noqa: E731 – kein Kreis/keine Kante in Fangnähe, nur die Fläche zählt
treffer = {}
for name, nr in (("außen", aussen), ("innen", innen)):
    c = mitte(nr)
    assert abs(math.hypot(c[0], c[1]) - (D / 2 if name == "außen" else D / 2 - T)) > 1e-3   # Sehne: nicht auf dem Ø
    t = g.fangen(fern, 0, 0, flaeche_treffer=lambda b, x, y, nr=nr, c=c: (nr, c))
    assert t["art"] == FLAECHE and t["element"]["typ"] == "zylinder"
    soll = D / 2 if name == "außen" else D / 2 - T
    assert abs(math.hypot(t["punkt"][0], t["punkt"][1]) - soll) < 1e-9, (name, t["punkt"])
    assert abs(t["punkt"][2] - c[2]) < 1e-12           # längs unverändert
    treffer[name] = t
ok(f"M1 Rohrmantel: Fangpunkt genau auf Ø {D:g} bzw. innen Ø {D - 2 * T:g} (Netz: Sehne)")

# ------------------------------------------------------------------ M2 Wandstärke
for name, t in treffer.items():
    zeilen = g.kernwerte(t)
    w = [z for z in zeilen if z.startswith("Wandstärke")]
    assert w and w[0].startswith(f"Wandstärke {T:.3f}".replace(".", ",")) and "abweichend" not in w[0], zeilen
qr = k.profile["QR 40x40x3"]
nq = rohr3d.netz(dict(quelle=sw.QUELLE, konturen=[]), qr, 300)
mq = Modell(nq)
gq = Geometrie(mq, nq)
gefunden = 0
for nr, (i, j, kk, _, n) in enumerate(mq.dreiecke):
    if abs(n[0] - 1) < 1e-9 or abs(n[1] - 1) < 1e-9:     # ebene Außenwand (Normale +quer oder +hoch)
        c = tuple(sum(mq.punkte[q][a] for q in (i, j, kk)) / 3 for a in range(3))
        el = gq.flaeche(nr, c)
        if el["typ"] != "ebene" or abs(max(abs(c[0]), abs(c[1])) - 20) > 1e-6:
            continue
        zeilen = gq.kernwerte(dict(art=FLAECHE, punkt=c, element=el))
        w = [z for z in zeilen if z.startswith("Wandstärke")]
        assert w and w[0].startswith("Wandstärke 3,000") and "Profil 3,000" in w[0], zeilen
        gefunden += 1
        if gefunden >= 2:
            break
assert gefunden == 2
assert g.wandstaerke((0.0, 0.0, 150.0), (0.0, 0.0, 1.0)) == ""    # ins Leere (Rohrinneres längs): keine Wand
ok(f"M2 Wandstärke: Rundrohr außen und innen {T:g} mm, Vierkantrohr 3 mm, ohne Gegenfläche keine Angabe")

# ------------------------------------------------------------------ M3 Schnittpunkt
p1, p2 = schnittpunkt((0, 0, 0), (1, 0, 0), (5, -3, 0), (0, 1, 0))
assert math.dist(p1, (5, 0, 0)) < 1e-12 and math.dist(p2, (5, 0, 0)) < 1e-12
assert schnittpunkt((0, 0, 0), (1, 0, 0), (0, 1, 0), (2, 0, 0)) is None        # parallel
ka = dict(typ="gerade", a=(0.0, 0.0, 0.0), b=(10.0, 0.0, 0.0), r=(1.0, 0.0, 0.0), mitte=(5.0, 0.0, 0.0))
kb = dict(typ="gerade", a=(4.0, -5.0, 0.0), b=(4.0, 5.0, 0.0), r=(0.0, 1.0, 0.0), mitte=(4.0, 0.0, 0.0))
kc = dict(kb, a=(4.0, -5.0, 2.0), b=(4.0, 5.0, 2.0), mitte=(4.0, 0.0, 2.0))
from rohrlaser.messen3d import KANTENMITTE  # noqa: E402

haupt, zeilen = g.vergleich(dict(art=KANTENMITTE, punkt=ka["mitte"], element=ka),
                            dict(art=KANTENMITTE, punkt=kb["mitte"], element=kb))
assert "Winkel" in haupt and "90" in haupt and any(z.startswith("Schnittpunkt: ") for z in zeilen), zeilen
assert g.lage((4.0, 0.0, 0.0)) in next(z for z in zeilen if z.startswith("Schnittpunkt"))
_, zeilen = g.vergleich(dict(art=KANTENMITTE, punkt=ka["mitte"], element=ka),
                        dict(art=KANTENMITTE, punkt=kc["mitte"], element=kc))
assert not any(z.startswith("Schnittpunkt") for z in zeilen) and any("kürzester Abstand 2,000" in z for z in zeilen)
ok("M3 Schnittpunkt zweier Kanten (Lage), windschief nur kürzester Abstand")

# ------------------------------------------------------------------ M4 Näherung ≈
gewoelbt = dict(art=FLAECHE, punkt=(1.0, 2.0, 3.0), element=dict(typ="flaeche", n=(0, 0, 1), p=(1.0, 2.0, 3.0),
                                                                  naeherung=True))
exakt = treffer["außen"]
haupt, zeilen = g.vergleich(gewoelbt, exakt)
assert haupt.startswith("≈ ") and any(z.startswith("≈ Näherung") for z in zeilen), (haupt, zeilen)
haupt, zeilen = g.vergleich(exakt, treffer["innen"])
assert "≈" not in haupt and not any("≈" in z for z in zeilen), (haupt, zeilen)
assert any("≈" in z for z in g.kernwerte(gewoelbt))
ok("M4 Näherung: Punkt auf gewölbter Fläche mit ≈ gekennzeichnet, exakte Mantelpunkte ohne")

# ------------------------------------------------------------------ M5 Schnittlänge aus der Rechnung (Editor)
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

technik = dict(quelle=sw.QUELLE, a=dict(winkel=0), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=2, d=10, x=100, seite="oben")])
p = dict(id=1, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, technik=json.dumps(technik))
kopf = dict(maschine="T11", stange=6000)
d = SchneidwegDialog(None, p, qr, kopf, k, db.tabellen(), db)
sl = d.editor.schnitt_laengen()
assert "kontur:0" in sl and "ende:a" in sl, sl
je, ges = sl["kontur:0"]
assert abs(je - math.pi * 10) < 0.01 and abs(ges - 2 * je) < 0.01, sl      # je Bohrung Ø 10, zwei in der Zeile
a3 = d.editor.ansicht()
assert a3.schnitt_laengen == sl
geo3 = a3.geometrie()
kreis = next(kr for kr in geo3.kreise if kr.get("id") == "kontur:0")
zeilen = geo3.kernwerte(dict(art=KREISMITTE, punkt=kreis["m"], element=dict(kreis, typ="kreis")))
z = next(z for z in zeilen if z.startswith("Schnittlänge"))
assert "31,42 mm je Kontur, 62,83 mm für alle dieser Zeile (aus der Rechnung)" in z, z
schritte = d.ergebnis["schritte"]
assert len(schritte) >= 3                                       # Werte stammen aus der vorhandenen Rechnung
ok(f"M5 Schnittlänge Bohrung {je:.2f} mm je Kontur aus der Rechnung in der Mess-Tafel")

# ------------------------------------------------------------------ B1 Tasten
a = Ansicht3D()
a.resize(900, 600)
a.setzen(netz, "Rundrohr")
a.show()
for taste, ziel in ((Qt.Key_3, "Oben"), (Qt.Key_5, "Ende A"), (Qt.Key_1, "Vorn"), (Qt.Key_0, ansicht3d.ISOMETRIE)):
    QTest.keyClick(a, taste)
    ref = Ansicht3D()
    ref.blick(ziel)
    assert (round(a.gier, 9), round(a.nick, 9)) == (round(ref.gier, 9), round(ref.nick, 9)), ziel
a.zoomen(0.05, 450, 300)
a.versatz = (300.0, -200.0)
QTest.keyClick(a, Qt.Key_F)
bild = a.bildpunkt()
px = [bild(v) for v in a.modell.punkte]
assert min(q[0] for q in px) >= -1 and max(q[0] for q in px) <= 901, "Modell nach F nicht im Bild"
assert min(q[1] for q in px) >= -1 and max(q[1] for q in px) <= 601
assert max(q[0] for q in px) - min(q[0] for q in px) > 0.5 * 900 or max(q[1] for q in px) - min(q[1] for q in px) \
    > 0.5 * 540, "Modell nach F nicht bildfüllend"
QTest.keyClick(a, Qt.Key_V)
assert a.vorher_an is False                                  # ohne gemerkten Stand: nichts
ok("B1 Tasten: Ansichten, F passt das Modell bildfüllend ein, V ohne Vorher-Stand ohne Wirkung")

# ------------------------------------------------------------------ B2 grobe Stufe nach Zeichenzeit
a._zeit_je_dreieck = None
assert a._grob_anzahl() == ansicht3d.GROB_DREIECKE
a._zeit_je_dreieck = ansicht3d.GROB_ZEIT / 7400
assert a._grob_anzahl() == 7000
a._zeit_je_dreieck = 1.0
assert a._grob_anzahl() == ansicht3d.GROB_MIN
a._zeit_je_dreieck = 1e-12
assert a._grob_anzahl() == ansicht3d.GROB_DREIECKE
gross = Modell(dict(p=[c for i in range(30000) for c in (i, (i * 7) % 13, (i * 3) % 11)],
                    t={"A": [v for i in range(29998) for v in (i, i + 1, i + 2)]}, **{"global": True}))
for n_ in (3000, 9000):
    assert len(gross.grob(n_).dreiecke) <= n_ * 1.2, (n_, len(gross.grob(n_).dreiecke))
assert gross.grob(3000) is gross.grob(3000)                   # je Stufe gemerkt
a._bild = None
a.grab()
assert a._zeit_je_dreieck and a._zeit_je_dreieck > 0           # beim feinen Bild gemessen
ok("B2 grobe Stufe: aus der gemessenen Zeichenzeit, begrenzt, je Stufe gemerkt")

# ------------------------------------------------------------------ B3 Leiste
from rohrlaser.ansicht3d_leiste import Leiste3D  # noqa: E402

le = Leiste3D(a)
for knopf in (le.blick_knopf, le.perspektive, le.koerper, le.messen, le.winkel, le.einpassen, le.vorher):
    assert not knopf.icon().isNull()
le.stand()
assert le.vorher.isHidden()
a.vorher_netz = rohr3d.netz(dict(quelle=sw.QUELLE, konturen=[]), rund, 200)
le.stand()
assert not le.vorher.isHidden()
le.vorher.setChecked(True)
assert a.vorher_an and a._vorher_modell is not None
a._bild = None
assert a.grab().width() == 900                                 # zeichnet mit Vorher-Linien ohne Fehler
QTest.keyClick(a, Qt.Key_V)
le.stand()
assert not a.vorher_an and not le.vorher.isChecked()
a.zoomen(0.05, 450, 300)
le.einpassen.click()
assert a.zoom > 0.2
ok("B3 Leiste: Symbole, Einpassen, Vorher-Knopf nur mit gemerktem Stand und mit Taste V abgeglichen")

# ------------------------------------------------------------------ B4 Vorher-Nachher im Rohr-Editor
d = SchneidwegDialog(None, p, qr, kopf, k, db.tabellen(), db)
a3 = d.editor.ansicht()
v0 = a3.vorher_netz
assert v0 is not None and a3.vorher_auto
d.tabelle.item(0, 2).setText("12")                             # Bohrung Ø 10 -> 12
d.editor.aktualisieren()
assert a3.vorher_netz is v0                                     # Stand beim Öffnen bleibt
dm = lambda gg: sorted(round(kr["d"], 2) for kr in gg.kreise if str(kr.get("id")).startswith("kontur"))  # noqa: E731
assert dm(Geometrie(Modell(v0), v0)) == [10.0, 10.0] and dm(a3.geometrie()) == [12.0, 12.0]
assert a3.vorher_zeigen(True)
a3._bild = None
a3.grab()
from rohrlaser import editor_griffe  # noqa: E402,F401 – Rechtsklick-Eintrag „Vorher-Nachher“ (Darstellung)
ok("B4 Rohr-Editor: Stand beim Öffnen bleibt gemerkt und liegt nach der Änderung gestrichelt darüber")
print("Alle Tests bestanden.")
