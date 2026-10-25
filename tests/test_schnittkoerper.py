"""Schnittkörper im 3D (Patrick 25.10.2026, Freigabe „A b b a a“): jede Kontur als halb durchsichtiger Körper, so
tief wie sie schneidet, Farbe je Konturart, Tiefe als Tooltip, Vorgabe an, gewählte Kontur kräftiger, in allen
3D-Fenstern (Rohr, Blech, Baugruppe/Satz über ansicht3d.baugruppe).

- K1 Rohr: eine Wand = Wandstärke, beide Wände bis zur Gegenwand (ohne Körper der Kopie), alle Seiten je ein Körper,
  schräge Bohrung entlang der Neigung, Gravur mit Tiefe, Texte; zu viele Konturen: keine Körper
- K2 Blech: durch die Dicke
- K3 Ansicht: Körper sichtbar (Farbe im Loch), abschaltbar und je Benutzer gemerkt, Legende, Tooltip-Text unter der
  Maus, Klick in den Körper wählt die Kontur, gewählte kräftiger
- K4 Baugruppe: Körper in Einbaulage, Verschieben längs der Achse
- K5 OpenGL (mit xvfb-run): Körper gezeichnet ohne Rückfall auf QPainter
- K6 V-Ausschnitt (Knickrahmen) eigene Farbe; unbekannte Kontur (Sonderkontur) mit der Form aus dem STEP-Netz

Aufruf: python tests/test_schnittkoerper.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
GL_KIND = os.environ.get("TEST_GL_KIND") == "1"
if not GL_KIND:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import ansicht3d, blech3d, rohr3d, schnittkoerper as sk3  # noqa: E402

app = QApplication.instance() or QApplication([])
QR = dict(form="Quadratrohr", a=80, b=80, wand=3)


def ok(t):
    print("OK    ", t)


def ringe(k):
    o = [tuple(k["o"][i:i + 3]) for i in range(0, len(k["o"]), 3)]
    u = [tuple(k["u"][i:i + 3]) for i in range(0, len(k["u"]), 3)]
    return o, u


def netz_bohrung():
    return rohr3d.netz(dict(konturen=[dict(art="Bohrung", anzahl=1, d=50, x=200, seite="oben")]), QR, 400)


def farbe(img, x, y):
    c = QColor(img.pixel(int(x), int(y)))
    return c.red(), c.green(), c.blue()


if GL_KIND:
    from rohrlaser import ansicht3d_gl
    if not ansicht3d_gl.gl_moeglich()[0]:
        print("KEIN_GL")
        sys.exit(0)
    ansicht3d.renderer_setzen("OpenGL")
    w = ansicht3d.Ansicht3D()
    w.resize(500, 300)
    w.setzen(netz_bohrung())
    w.blick("Oben")
    w.markieren(["kontur:0"])
    w.show()
    app.processEvents()
    img = w._gl.grabFramebuffer()
    assert w._gl is not None and not w._gl.fehler, w.renderer_grund
    x, y, _ = w.bildpunkt()((0.0, 40.0, 200.0))
    r, g, b = farbe(img, x, y)
    assert b > r + 30, (r, g, b)                # blau getönt (Schnittkörper Bohrung)
    w.koerper_setzen(False, merken=False)
    app.processEvents()
    r2, g2, b2 = farbe(w._gl.grabFramebuffer(), x, y)
    assert b2 - r2 < b - r - 20, ((r, g, b), (r2, g2, b2))
    print("GL_OK")
    sys.exit(0)

# ------------------------------------------------------------------ K1 Rohr
e = dict(konturen=[dict(art="Bohrung", anzahl=1, d=50, x=300, seite="oben"),
                   dict(art="Bohrung", anzahl=1, d=20, x=600, seite="oben", wand="beide"),
                   dict(art="Ausklinkung", anzahl=1, l=100, b=60, seite="oben"),
                   dict(art="Langloch", anzahl=1, l=40, b=10, x=500, seite="vorne", wand="alle"),
                   dict(art="Gravur", anzahl=1, x=800, seite="oben", tiefe=0.3, laenge=40,
                        umriss=[[-5, -5], [5, -5], [5, 5], [-5, 5]]),
                   dict(art="Text-Gravur", anzahl=1, x=900, seite="oben", text="AB", hoehe=10)])
wk = rohr3d.netz(e, QR, 1000)["wk"]
ids = [k["id"] for k in wk]
assert ids == ["kontur:0", "kontur:1", "kontur:2"] + ["kontur:3"] * 4 + ["kontur:4"], ids    # Text-Gravur ohne
arten = [k["art"] for k in wk]
assert arten[:4] == ["WB", "WB", "WA", "WL"] and arten[-1] == "WG", arten
o, u = ringe(wk[0])
assert len(o) == len(u) == 36 and len(wk[0]["d"]) == 3 * 34
assert all(math.isclose(a[1] - b[1], 3 + sk3.UEBERSTAND + sk3.UEBERSTAND_INNEN, abs_tol=1e-6) for a, b in zip(o, u))   # Wand + Überstand
assert all(math.isclose(a[1], 40 + sk3.UEBERSTAND) for a in o)
assert wk[0]["t"] == "Ø 50\n1 Wand · 3 mm", wk[0]["t"]
o, u = ringe(wk[1])                                 # beide Wände: bis unter die Gegenwand
assert all(math.isclose(b[1], -40 - sk3.UEBERSTAND_INNEN, abs_tol=1e-6) for b in u), u[:2]
assert "durch 2 Wände · 80 mm" in wk[1]["t"], wk[1]["t"]
seiten = sorted((round(ringe(k)[0][0][0]), round(ringe(k)[0][0][1])) for k in wk[3:7])
assert len(set(seiten)) == 4 and "alle 4 Seiten" in wk[3]["t"]
o, u = ringe(wk[-1])
assert all(math.isclose(a[1] - b[1], 0.3 + sk3.UEBERSTAND + sk3.UEBERSTAND_INNEN, abs_tol=1e-6) for a, b in zip(o, u))
assert "Gravur 0,3 mm tief" in wk[-1]["t"], wk[-1]["t"]
# schräge Bohrung: Ring innen um Wand × tan(längs) (+ Überstand) Richtung Ende B versetzt
e3 = dict(d3=True, konturen=[dict(art="Bohrung", anzahl=1, d=20, x=300, seite="0", d3=True, neigung_l=30)])
k = rohr3d.netz(e3, dict(form="Rundrohr", a=60, wand=2), 1000)["wk"][0]
o, u = ringe(k)
dx = sum(b[2] for b in u) / len(u) - sum(a[2] for a in o) / len(o)
w30 = math.radians(30)
assert math.isclose(dx, 2 * math.tan(w30) + (sk3.UEBERSTAND + sk3.UEBERSTAND_INNEN) * math.sin(w30), abs_tol=0.05), dx
assert "Neigung längs 30°" in k["t"], k["t"]
viele = dict(konturen=[dict(art="Bohrung", anzahl=1, d=5, x=10 + i * 2, seite="oben")
                       for i in range(sk3.MAX_KOERPER + 1)])
assert "wk" not in rohr3d.netz(viele, QR, 2000)
ok("K1 Rohr: 1 Wand, beide Wände, alle Seiten, schräge Bohrung, Gravurtiefe, Texte, Grenze")

# ------------------------------------------------------------------ K2 Blech
eb = dict(dicke=4, form="Rechteck", laenge=200, breite=100,
          konturen=[dict(art="Bohrung", d=20, x=50, y=50), dict(art="Langloch", l=40, b=10, x=140, y=50)])
from rohrlaser import blech  # noqa: E402
zs = blech.zuschnitt(eb)
nb = blech3d.netz(eb, zs)
assert [k["art"] for k in nb["wk"]] == ["WB", "WL"], nb.get("wk")
o, u = ringe(nb["wk"][0])
dick = math.dist(o[0], u[0])
assert math.isclose(dick, 4 + 2 * sk3.UEBERSTAND, abs_tol=1e-3), dick
assert "durch das Blech · 4 mm" in nb["wk"][0]["t"]
ok("K2 Blech: Körper durch die Dicke")

# ------------------------------------------------------------------ K3 Ansicht
ansicht3d.renderer_setzen("Software")


class Speicher:
    def __init__(self):
        self.werte = {}

    def einstellung(self, k):
        return self.werte.get(k)

    def einstellung_setzen(self, k, v):
        self.werte[k] = v


sp = Speicher()
ansicht3d.speicher_setzen(sp)
w = ansicht3d.Ansicht3D()
w.resize(500, 300)
assert w.koerper_an                                 # Vorgabe an
w.setzen(netz_bohrung())
w.blick("Oben")
assert w.hasMouseTracking()                         # Tooltip braucht die Maus
assert "WB" in w.modell.arten
x, y, _ = w.bildpunkt()((0.0, 40.0, 200.0))
r, g, b = farbe(w.grab().toImage(), x, y)
assert b > r + 30, (r, g, b)
t = w.koerper_unter(x, y)
assert t and t[1]["text"].startswith("Ø 50") and "1 Wand" in t[1]["text"]
assert w.koerper_unter(5, 5) is None
treffer = []
w.angeklickt.connect(treffer.append)
w.klicken(x, y)
assert treffer and treffer[-1]["id"] == "kontur:0", treffer
a0 = farbe(w.grab().toImage(), x, y)
w.markieren(["kontur:0"])                           # gewählt: kräftiger
a1 = farbe(w.grab().toImage(), x, y)
assert a1[2] - a1[0] > a0[2] - a0[0], (a0, a1)
w.koerper_setzen(False)
assert sp.werte[ansicht3d.KOERPER_EINSTELLUNG] is False and not ansicht3d.koerper_vorgabe()
r2, g2, b2 = farbe(w.grab().toImage(), x, y)
assert b2 - r2 < b - r - 20, ((r, g, b), (r2, g2, b2))
assert w.koerper_unter(x, y) is None and not w.hasMouseTracking()
w2 = ansicht3d.Ansicht3D()
assert not w2.koerper_an                            # gemerkt
w.koerper_setzen(True)
m = ansicht3d.Ansicht3DMitKnoepfen()
m.setzen(netz_bohrung())
assert m.leiste.koerper.isChecked()
m.leiste.koerper.setChecked(False)
assert not m.ansicht.koerper_an
from rohrlaser.ansicht3d_leiste import SCHNITTKOERPER  # noqa: E402
aktion = next(a for a in m.leiste.blick_menue.actions() if a.text() == SCHNITTKOERPER)
aktion.trigger()
assert m.ansicht.koerper_an and m.leiste.koerper.isChecked()
ansicht3d.speicher_setzen(None)
ok("K3 Ansicht: sichtbar, Tooltip, Klick wählt, gewählt kräftiger, aus/ein gemerkt, Leiste und Menü Blick")

# ------------------------------------------------------------------ K4 Baugruppe
n = netz_bohrung()
lage = [100, 0, 0, 1, 0, 0, 0, 0, 1]                # Rohrachse = x, Ursprung bei x = 100
gesamt, _ = ansicht3d.baugruppe([dict(n, lage=lage)])
o0 = ringe(n["wk"][0])[0][0]
o1 = ringe(gesamt["wk"][0])[0][0]
assert math.isclose(o1[0], 100 + o0[2]) and math.isclose(o1[2], -o0[0], abs_tol=1e-6), (o0, o1)
sk3.verschieben(n["wk"], -5)
assert math.isclose(ringe(n["wk"][0])[0][0][2], o0[2] - 5)
ok("K4 Baugruppe/Satz: Körper in Einbaulage, längs verschoben")

# ------------------------------------------------------------------ K6 V-Ausschnitt, unbekannte Kontur wie STEP
from rohrlaser import knickrahmen  # noqa: E402
pr = dict(form="Quadratrohr", a=40, b=40, wand=2)
v = knickrahmen.zeile_ergaenzen(dict(art="V-Ausschnitt", anzahl=1, beta=90, x=300), pr)
(kv,) = rohr3d.netz(dict(konturen=[v]), pr, 800)["wk"]
assert kv["art"] == "WV" and kv["d"] == [] and "V-Ausschnitt β 90°" in kv["t"], kv["t"]     # über Wände: ohne Deckel
es = dict(konturen=[dict(art="Sonderkontur", anzahl=1, x=300, seite="oben", laenge=80, huelle=20,
                         umriss=[[-10, -10], [10, -10], [10, 10], [-10, 10]]),
                    dict(art="Bohrung", anzahl=1, d=20, x=700, seite="oben")])
n = rohr3d.netz(es, QR, 1000)
assert [k["art"] for k in n["wk"]] == ["WU", "WB"]


def quad(x0, y0, z0, b):
    """Viereck (Wandstück) der STEP-Kontur: zwei Dreiecke, Art K."""
    return [x0, y0, z0, x0 + b, y0, z0, x0 + b, y0 - 3, z0, x0, y0 - 3, z0]


step_netz = dict(p=quad(-12, 40, 295, 6) + quad(-6, 40, 295, 6) + quad(-10, 40, 700, 20),
                 t={"K": [0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7, 8, 9, 10, 8, 10, 11]},
                 l={"K": [[-12, 40, 295, -6, 40, 295, 0, 40, 295]]})
n = rohr3d.mit_step(n, step_netz, es, QR, 1000)
wu = [k for k in n["wk"] if k["art"] == "WU"]
assert len(wu) == 1 and len(wu[0]["dr"]) == 4 * 9 and wu[0]["li"], wu      # nur die Stücke bei x 300, Linie dazu
assert "Form wie in der STEP-Datei" in wu[0]["t"] and wu[0]["auf"]
assert [k["art"] for k in n["wk"]] == ["WB", "WU"]                  # Bohrung bleibt aus den Eingaben
mo = ansicht3d.Modell(n)
assert [len(k["dreiecke"]) for k in mo.koerper if k["art"] == "WU"] == [4]
gesamt, _ = ansicht3d.baugruppe([dict(n, lage=[0, 0, 0, 0, 0, 1, 1, 0, 0])])
assert len([k for k in gesamt["wk"] if k["art"] == "WU"][0]["dr"]) == 36
ok("K6 V-Ausschnitt eigene Farbe ohne Deckel; unbekannte Kontur mit der Form aus der STEP-Datei (eigene Farbe)")

# ------------------------------------------------------------------ K5 OpenGL
if sys.platform.startswith("linux") and shutil.which("xvfb-run"):
    env = dict(os.environ, TEST_GL_KIND="1")
    env.pop("QT_QPA_PLATFORM", None)
    r = subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1280x1024x24", sys.executable, __file__],
                       capture_output=True, text=True, env=env, timeout=300)
    if "KEIN_GL" in r.stdout:
        print("HINWEIS OpenGL nicht geprüft: kein OpenGL unter xvfb")
    else:
        assert "GL_OK" in r.stdout, r.stdout + r.stderr
        ok("K5 OpenGL: Schnittkörper gezeichnet, aus = nicht mehr blau")
else:
    print("HINWEIS OpenGL nicht geprüft: kein xvfb-run")
print("Alle Tests Schnittkörper bestanden.")
