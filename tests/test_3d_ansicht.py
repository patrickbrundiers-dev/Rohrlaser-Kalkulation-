"""3D-Ansichten (Plan 3D-Ansicht 3E-11, Patrick 24.10.2026 „alle a“): Richtungen, Perspektive, Darstellungen und
Messen mit exakten Kernwerten in allen 3D-Fenstern.
- A1 Blick: Isometrie, sechs Seiten, um 90° drehen (Strg + Pfeiltasten), Auf Auswahl
- A2 Perspektive: Umschalter, Vorgabe orthogonal, je Benutzer gemerkt, Klick trifft auch perspektivisch
- A3 Darstellungen: Drahtgitter und Verdeckt gestrichelt, Tangentenkanten, Umriss des Rundrohrs
- A4 Messen exakt: Kreismitte, Kante, Fläche, Rohrmantel aus der Geometrie; Fangen nach Vorrang; Mess-Tafel
- A5 Gemeinsame Leiste und Würfel in jedem 3D-Fenster

Aufruf: python tests/test_3d_ansicht.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import (ansicht3d, ansicht3d_leiste, blech, blech3d, messen3d, rohr3d,  # noqa: E402
                       schneidweg as sw)


def ok(t):
    print("OK    ", t)


QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
RR = dict(form="Rundrohr", a=48.3, wand=3)
EING = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100),
                                  dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="vorne")])


def ansicht(netz, breite=900, hoehe=420):
    a = ansicht3d.Ansicht3D()
    a.resize(breite, hoehe)
    a.setzen(netz)
    return a


def zum_betrachter(a):
    """Modellrichtung, die in der aktuellen Drehung zum Betrachter zeigt."""
    m = ansicht3d._drehung(a.gier, a.nick)
    return tuple(m[2])


ansicht3d.renderer_setzen("Software")
# ------------------------------------------------------------------ A1 Blick
a = ansicht(rohr3d.netz(EING, QR, 500))
for name, n in ansicht3d.BLICKE:
    a.blick(name)
    assert sum(x * y for x, y in zip(zum_betrachter(a), n)) > 0.99, (name, zum_betrachter(a))
a.blick(ansicht3d.ISOMETRIE)
assert (a.gier, a.nick) == ansicht3d.Ansicht3D.GRUND
a.blick("Vorn")
a.drehen(1, 0)
assert abs(a.gier - math.pi / 2) < 1e-9 and a.nick == 0
a.drehen(0, 1)
assert a.nick == ansicht3d.NICK_MAX                     # nach oben gekippt: von oben
a.drehen(0, -1)
assert a.nick == 0                                      # zurück genau nach vorn
g0 = a.gier
a.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.ControlModifier))
assert abs((g0 - a.gier) % (2 * math.pi) - math.pi / 2) < 1e-9
assert not a.auf_auswahl()                              # nichts gewählt
a.markieren(["kontur:0"])
assert a.auf_auswahl()
assert zum_betrachter(a)[1] > 0.99 and a.zoom > 3       # Bohrung oben: von oben, groß
px, py, _ = a.bildpunkt()((0.0, 20.0, 100.0))
assert abs(px - a.width() / 2) < 30 and abs(py - a.height() / 2) < 30, (px, py)
a.markieren()
ok("A1 Blick: Isometrie, Vorn/Hinten/Oben/Unten/Ende A/Ende B, 90° drehen (auch Strg+Pfeil), Auf Auswahl")


# ------------------------------------------------------------------ A2 Perspektive
class Speicher(dict):
    def einstellung(self, name):
        return self.get(name)

    def einstellung_setzen(self, name, wert):
        self[name] = wert


sp = Speicher()
ansicht3d.speicher_setzen(sp)
a = ansicht(rohr3d.netz(EING, QR, 500))
assert a.perspektive is False                          # Vorgabe orthogonal
a.blick("Oben")
b_ortho = a.bildpunkt()
a.perspektive_setzen(True)
assert sp[ansicht3d.PERSPEKTIVE_EINSTELLUNG] is True and ansicht(rohr3d.netz(EING, QR, 500)).perspektive is True
b_persp = a.bildpunkt()
# von oben: obere Fläche (näher) erscheint größer als die untere


def breite(b, y):
    pa, pb = b((-20.0, y, 0.0)), b((20.0, y, 0.0))
    return math.hypot(pa[0] - pb[0], pa[1] - pb[1])


assert breite(b_persp, 20.0) > breite(b_persp, -20.0) + 1
assert abs(breite(b_ortho, 20.0) - breite(b_ortho, -20.0)) < 1e-6        # orthogonal: gleich groß
a.messen_setzen(True)
px, py, _ = b_persp((0.0, 20.0, 100.0))
a.klicken(px, py)
assert a.mess_treffer[-1]["art"] == messen3d.KREISMITTE and math.dist(a.messpunkte[-1], (0, 20, 100)) < 1e-6
assert not a.grab().isNull()
a.perspektive_setzen(False)
ansicht3d.speicher_setzen(None)
ok("A2 Perspektive: Umschalter, Vorgabe orthogonal, je Benutzer gemerkt, Fangen trifft auch perspektivisch")

# ------------------------------------------------------------------ A3 Darstellungen
assert ansicht3d.DARSTELLUNGEN[-2:] == (ansicht3d.DRAHTGITTER, ansicht3d.VERDECKT)
mo = ansicht3d.Modell(rohr3d.netz(EING, QR, 500))
laengs = {(round(p[0], 2), round(p[1], 2)) for p, q, _ in mo.kanten()
          if p[0] == q[0] and p[1] == q[1] and abs(p[2] - q[2]) > 50}
assert {(-20.0, 14.0), (-14.0, 20.0), (-17.0, 14.0), (-14.0, 17.0)} <= laengs, laengs   # Tangentenkanten außen/innen
assert len(laengs) == 16, laengs                       # 4 Ecken × 2 Tangenten × außen/innen, keine Zwischenlinien
mr = ansicht3d.Modell(rohr3d.netz(dict(a={}, b={}, konturen=[]), RR, 500))
assert mr.glatte_kanten()
um = ansicht3d.umriss(mr, ansicht3d._drehung(0.0, 0.0))            # von vorn: oben und unten
assert {round(abs(p[1]), 2) for p, _, _ in um} == {24.15, 21.15} and all(abs(p[0]) < 1e-6 for p, _, _ in um)
for netz in (rohr3d.netz(EING, QR, 500), rohr3d.netz(EING, RR, 500)):
    a = ansicht(netz)
    for dar in ansicht3d.DARSTELLUNGEN:
        for persp in (False, True):
            a.darstellung_setzen(dar)
            a.perspektive_setzen(persp, merken=False)
            assert not a.grab().isNull()
ok("A3 Darstellungen: Drahtgitter, Verdeckt gestrichelt, Tangentenkanten an Rundungen, Umriss des Rundrohrs")

# ------------------------------------------------------------------ A4 Messen exakt
a = ansicht(rohr3d.netz(EING, QR, 500))
geo = a.geometrie()
assert [(k["m"], k["d"], k["id"]) for k in geo.kreise] == [((0.0, 20.0, 100.0), 10.0, "kontur:0")]
assert geo.mitten[0]["p"] == (-20.0, 0.0, 300.0) and geo.mitten[0]["id"] == "kontur:1"
bild = a.bildpunkt()
a.messen_setzen(True)
px, py, _ = bild((0.4, 20.4, 100.0))            # neben der Mitte: fängt die Kreismitte (Vorrang vor Ecken)
a.klicken(px + 2, py - 2)
t1 = a.mess_treffer[0]
assert t1["art"] == messen3d.KREISMITTE and not a.tafel.isHidden()
assert "Kreis Ø 10,000 mm" in a.tafel.klartext() and "Bohrung" in a.tafel.klartext()
kante = next(g for g in geo.geraden if g["a"][:2] == (-14.0, 20.0) and g["laenge"] > 400)
px, py, _ = bild(kante["mitte"])
a.klicken(px, py)
assert a.mess_treffer[1]["art"] == messen3d.KANTENMITTE
text = a.tafel.klartext()
assert "Winkel Achse–Kante 90,000°" in text and "kürzester Abstand 14,000 mm" in text, text
assert a.mess_text().startswith("Abstand ") and len(a.masse_fest) == 1
a.tafel.in_zwischenablage()
assert QGuiApplication.clipboard().text() == text
# Schweben hebt hervor (ohne Klick)
px, py, _ = bild((-20.0, 0.0, 300.0))
a.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, QPointF(px + 2, py), QPointF(px + 2, py), Qt.NoButton, Qt.NoButton,
                             Qt.NoModifier))
assert a._schwebe and a._schwebe["art"] == messen3d.KONTURMITTE
assert not a.grab().isNull()
# Flächen: oben gegen unten (eben, parallel) = 40, Seite gegen Stirnfläche = 90°
nummer, ebenen = a.modell.ebenen()


def flaeche(n, d):
    nr = next(i for i, e in enumerate(nummer) if all(abs(ebenen[e]["n"][k] - n[k]) < 1e-6 for k in range(3))
              and abs(ebenen[e]["d"] - d) < 1e-3)
    i, j, k, _, _ = a.modell.dreiecke[nr]
    p = tuple(sum(a.modell.punkte[x][c] for x in (i, j, k)) / 3 for c in range(3))
    return dict(art=messen3d.FLAECHE, punkt=p, element=geo.flaeche(nr, p))


oben, unten = flaeche((0, 1, 0), 20), flaeche((0, -1, 0), 20)
assert oben["element"]["typ"] == "ebene"
haupt, _ = geo.vergleich(oben, unten)
assert haupt == "Abstand Fläche–Fläche 40,000 mm", haupt
haupt, _ = geo.vergleich(flaeche((-1, 0, 0), 20), flaeche((0, 0, -1), 0))
assert haupt == "Winkel Fläche–Fläche 90,000°", haupt
k1 = dict(art=messen3d.KANTENMITTE, punkt=kante["mitte"], element=dict(kante, typ="gerade"))
k2g = next(g for g in geo.geraden if g["a"][:2] == (14.0, 20.0) and g["laenge"] > 400)
k2 = dict(art=messen3d.KANTENMITTE, punkt=k2g["mitte"], element=dict(k2g, typ="gerade"))
assert geo.vergleich(k1, k2)[0] == "Abstand Kante–Kante 28,000 mm (parallel)"
haupt, zeilen = geo.vergleich(dict(art=messen3d.ECKE, punkt=(0.0, 20.0, 50.0), element=None), oben)
assert haupt == "Abstand Punkt–Fläche (senkrecht) 0,000 mm" and zeilen[1].startswith("Ecke – Fläche")
# Rundrohr: Mantel und Rohrende exakt aus dem Profil
a = ansicht(rohr3d.netz(EING, RR, 500))
geo = a.geometrie()
enden = [k for k in geo.kreise if k["id"] in ("ende:a", "ende:b")]
assert len(enden) == 2 and all(k["d"] == 48.3 for k in enden)
a.blick("Vorn")
a.messen_setzen(True)
a.klicken(a.width() / 2 + 40, a.height() / 2 + 20)
t = a.mess_treffer[-1]
assert t["art"] == messen3d.FLAECHE and t["element"]["typ"] == "zylinder" and t["element"]["d"] == 48.3
assert "Rohrmantel Ø 48,300 mm, Achse längs" in a.tafel.klartext()
a.messen_setzen(False)
assert a.tafel.isHidden()
# Blech: Bohrungen auf beiden Häuten, Dicke als Abstand der Flächen
e = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100,
         konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=8, x=50, y=30), dict(art=sw.BOHRUNG, anzahl=1, d=12, x=150, y=60)])
a = ansicht(blech3d.netz(e, blech.zuschnitt(e)))
geo = a.geometrie()
assert sorted({k["d"] for k in geo.kreise}) == [8.0, 12.0] and len(geo.kreise) == 4
kr = [dict(art=messen3d.KREISMITTE, punkt=k["m"], element=dict(k, typ="kreis")) for k in geo.kreise[::2]]
haupt, zeilen = geo.vergleich(*kr)
assert haupt == f"Abstand {messen3d.zahl(math.hypot(100, 30))} mm" and any("(parallel)" in z for z in zeilen)
# STEP-Netz (ohne Eingaben, auf 0,01 mm gerundet): Kreis eingepasst, zwei Stellen
ring = [(round(5 * math.cos(w), 2), 20.0, round(100 + 5 * math.sin(w), 2))
        for w in (2 * math.pi * i / 36 for i in range(37))]
k = messen3d.kreis_einpassen(ring)
assert abs(k["d"] - 10) < 0.01 and messen3d.stellen_fuer(k["abw"]) == 2 and abs(abs(k["n"][1]) - 1) < 1e-6
assert messen3d.kreis_einpassen([(x, 0.0, x * x) for x in range(12)]) is None      # kein Kreis
assert messen3d.zahl(-0.0001) == "0,000" and messen3d.zahl(8) == "8,000"
ok("A4 Messen exakt: Kreismitte, Kante, Fläche, Rohrmantel, Blech, STEP eingepasst; Fangen, Mess-Tafel, Kopieren")

# ------------------------------------------------------------------ A5 Gemeinsame Leiste und Würfel
w = ansicht3d.Ansicht3DMitKnoepfen()
w.resize(900, 500)
w.setzen(rohr3d.netz(EING, QR, 500))
w.show()
app.processEvents()
assert w.wuerfel.isVisibleTo(w) and w.wuerfel.x() > w.width() / 2
texte = [x.text() for x in w.leiste.blick_menue.actions()]
for t in (ansicht3d.ISOMETRIE,) + tuple(n for n, _ in ansicht3d.BLICKE) + (ansicht3d_leiste.AUF_AUSWAHL,
                                                                          ansicht3d_leiste.PERSPEKTIVISCH):
    assert t in texte, (t, texte)
next(x for x in w.leiste.blick_menue.actions() if x.text() == "Ende B").trigger()
assert zum_betrachter(w.ansicht)[2] > 0.99
w.leiste.messen.setChecked(True)
assert w.ansicht.messen and w.ansicht.mess_max == 2
w.leiste.winkel.setChecked(True)
assert w.ansicht.mess_art == ansicht3d.MESS_WINKEL and not w.leiste.messen.isChecked()
w.ansicht.messen_setzen(True, punkte=0)                 # z. B. Naht zeichnen: Leiste zeigt kein Messen
assert not w.leiste.messen.isChecked() and not w.leiste.winkel.isChecked()
w.leiste.darstellung.setCurrentText(ansicht3d.DRAHTGITTER)
assert w.ansicht.darstellung == ansicht3d.DRAHTGITTER
w.leiste.perspektive.setChecked(True)
assert w.ansicht.perspektive
assert not w.grab().isNull()
ok("A5 Gemeinsame Leiste (Blick, Darstellung, Perspektive, Messen) und Würfel in jedem 3D-Fenster")
print("Alle Tests 3D-Ansichten bestanden.")
