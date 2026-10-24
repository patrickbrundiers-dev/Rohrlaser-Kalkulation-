"""3D-Ansicht mit OpenGL als zweite Darstellung (Plan S10): Einstellung, Auswahl der Darstellung mit Rückfall auf
QPainter, Puffer und Abbildung, und – wenn ein Bildschirm mit OpenGL da ist (xvfb-run) – dasselbe Bild wie QPainter
mit richtiger Verdeckung über den Tiefenpuffer.

Aufruf: python tests/test_ansicht_gl.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen; den OpenGL-Teil startet der
Test selbst mit xvfb-run, wenn vorhanden)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
GL_KIND = os.environ.get("TEST_GL_KIND") == "1"         # Unterprozess unter xvfb mit OpenGL
if not GL_KIND:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import ansicht3d  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


def rechteck(x, h, laenge):
    """Rechteck in der Ebene x = konst., Normale -x (in der Ansicht 'Vorn' zum Betrachter)."""
    return [x, -h, 0, x, h, 0, x, h, laenge, x, -h, laenge]


# Zwei Flächen hintereinander: vorn Außenwand (klein), dahinter Innenwand (größer), Innenwand zuletzt im Puffer –
# ohne Tiefenpuffer läge sie im ganzen Bild vorn
NETZ = dict(p=rechteck(-10, 50, 100) + rechteck(10, 80, 100), t={"A": [0, 2, 1, 0, 3, 2], "I": [4, 6, 5, 4, 7, 6]},
            l={})


def bild(renderer, zoom=1.0):
    ansicht3d.renderer_setzen(renderer)
    w = ansicht3d.Ansicht3D()
    w.resize(400, 300)
    w.setzen(NETZ)
    w.ansicht(0.0, 0.0)
    w.zoom = zoom
    if w._gl is not None:
        w.show()
        app.processEvents()
        return w, w._gl.grabFramebuffer()
    return w, w.grab().toImage()


def farbe(img, x, y):
    c = QColor(img.pixel(x, y))
    return c.red(), c.green(), c.blue()


def abstand(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def nah(a, b, tol=14):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


if GL_KIND:
    # ------------------------------------------------------------ Unterprozess: OpenGL gegen QPainter
    from rohrlaser import ansicht3d_gl
    moeglich, grund = ansicht3d_gl.gl_moeglich()
    if not moeglich:
        print("KEIN_GL", grund)
        sys.exit(0)
    w_gl, gl = bild("OpenGL")
    assert w_gl.renderer == "OpenGL" and w_gl._gl is not None, w_gl.renderer_grund
    w_sw, sw = bild("Software")
    assert w_sw._gl is None
    mitte = (gl.width() // 2, gl.height() // 2)
    vorn, hinten = farbe(sw, *mitte), farbe(sw, gl.width() // 2, 60)
    assert not nah(vorn, hinten, 6), "Testbild: Außen- und Innenwand unterscheidbar"
    # Farben je nach Mesa-Version leicht anders (bis etwa 20 je Kanal): Verdeckung am Abstand zu vorn/hinten prüfen
    def vorn_sichtbar(img, v=vorn, h=hinten):
        g, gh = farbe(img, *mitte), farbe(img, gl.width() // 2, 60)
        return abstand(g, v) < abstand(g, h) and not nah(g, gh, 6) and nah(g, v, 30), (g, gh, v, h)

    ergebnis, werte = vorn_sichtbar(gl)
    if not ergebnis:
        print("DIAG", grund, werte, farbe(gl, 2, 2), flush=True)
    if not ergebnis:            # Hinweise für die Fehlersuche (Treiber, Hintergrund, Licht ohne Zusätze)
        diag, behalten = [grund, ("ecke", farbe(gl, 2, 2), farbe(sw, 2, 2))], []
        lw, l2 = ansicht3d.LICHT_WERTE, ansicht3d.LICHT2
        for name, werte_l, licht2 in (("ohne Glanz", (lw[0], lw[1], lw[2], 0.0, lw[4]), l2),
                                      ("alt", (0.42, 0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0))):
            ansicht3d.LICHT_WERTE, ansicht3d.LICHT2 = werte_l, licht2
            behalten.append(bild("OpenGL"))
            diag.append((name, farbe(behalten[-1][1], *mitte)))
            print("DIAG", diag, flush=True)
        ansicht3d.LICHT_WERTE, ansicht3d.LICHT2 = lw, l2
        print("DIAG", diag, flush=True)
    assert ergebnis, ("Tiefenpuffer: vordere Fläche verdeckt die hintere", werte, diag)
    # zweites Bild (QPainter der Beschriftung hat den Zustand verändert) und vergrößert: weiter richtig verdeckt
    gl2 = w_gl._gl.grabFramebuffer()
    assert vorn_sichtbar(gl2)[0], ("zweites Bild", vorn_sichtbar(gl2)[1])
    _, gl3 = bild("OpenGL", zoom=3.0)
    _, sw3 = bild("Software", zoom=3.0)
    g3, v3 = farbe(gl3, *mitte), farbe(sw3, *mitte)
    assert abstand(g3, v3) < abstand(g3, hinten) and nah(g3, v3, 30), ("vergrößert", g3, v3, hinten)
    # Umriss gleich (Bildpunkt Hintergrund oder Teil); Farbtöne hängen von der Mesa-Version ab
    h = ansicht3d.HINTERGRUND
    hg = (h.red(), h.green(), h.blue())
    abweichend = sum(nah(farbe(gl, x, y), hg, 10) != nah(farbe(sw, x, y), hg, 10)
                     for x in range(0, gl.width(), 8) for y in range(0, gl.height(), 8))
    assert abweichend < 0.05 * (gl.width() // 8) * (gl.height() // 8), f"{abweichend} Bildpunkte anders"
    # Fehler beim Zeichnen: diese und alle neuen Ansichten zurück zu QPainter
    w_gl._gl_aus("Test")
    assert w_gl._gl is None and w_gl.renderer == "Software"
    assert not w_gl.grab().isNull()
    ansicht3d.renderer_setzen("OpenGL")
    assert ansicht3d.renderer_waehlen() == ("Software", "OpenGL gescheitert: Test")
    print("GL_OK", grund)
    sys.exit(0)

# ---------------------------------------------------------------- Einstellung je Arbeitsplatz
from rohrlaser import stammdaten, teilen  # noqa: E402

e = {x.name: x for x in stammdaten.EINSTELLUNGEN}["ansicht_3d"]
assert e.vorgabe == "Automatisch" and e.gruppe == "Ansicht"
assert stammdaten.DARSTELLUNG_3D == ansicht3d.RENDERER
assert "ansicht_3d" in teilen.LOKAL and "ansicht_3d" not in teilen.EINSTELLUNGEN_GETEILT
ok("Einstellung 3D-Ansicht: Darstellung (Automatisch, Software, OpenGL), nur an diesem Arbeitsplatz")

# ---------------------------------------------------------------- Auswahl der Darstellung
ansicht3d.renderer_setzen("Unsinn")
assert ansicht3d._renderer == "Automatisch"
ansicht3d.renderer_setzen("Software")
assert ansicht3d.renderer_waehlen() == ("Software", "Einstellung Software")
w, img = bild("Software")
assert w._gl is None and farbe(img, 200, 150) != farbe(img, 2, 2)
ok("Software: immer QPainter")
for wert in ("Automatisch", "OpenGL"):
    ansicht3d.renderer_setzen(wert)
    r, grund = ansicht3d.renderer_waehlen()
    assert r in ("OpenGL", "Software") and grund
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        assert r == "Software", (wert, grund)              # offscreen: kein OpenGL -> QPainter
ok(f"Automatisch/OpenGL ohne OpenGL: Rückfall auf QPainter ({grund})")
ansicht3d._gl_fehler = "Treiber"
ansicht3d.renderer_setzen("OpenGL")
assert ansicht3d.renderer_waehlen() == ("Software", "OpenGL gescheitert: Treiber")
ansicht3d._gl_fehler = None
ok("einmal gescheitert: alle weiteren Ansichten mit QPainter")

# ---------------------------------------------------------------- Puffer und Abbildung (ohne Grafikkarte)
from rohrlaser import ansicht3d_gl  # noqa: E402

m = ansicht3d.Modell(NETZ)
farben = {a: (0.1, 0.2, 0.3) for a in ansicht3d.FARBE}
d, l, _ = ansicht3d_gl.puffer_daten(m, farben, farben)
assert len(d) == len(m.dreiecke) * 3 * 9 and len(l) == 0
assert tuple(d[0:3]) == m.punkte[m.dreiecke[0][0]] and tuple(round(x, 6) for x in d[3:6]) == (-1, 0, 0)
s, ox, oy = ansicht3d_gl.abbildung(m, 400, 300, ansicht3d._drehung(0.0, 0.0), 1.0, (5.0, -3.0))
assert (ox, oy) == (205.0, 147.0) and abs(s - 0.9 * min(400 / 100, 300 / 160)) < 1e-9
ok("Puffer je Ecke Ort/Normale/Farbe, Abbildung aus dem Hüllquader")

# ---------------------------------------------------------------- OpenGL-Bild (mit xvfb-run)
if sys.platform.startswith("linux") and shutil.which("xvfb-run"):
    env = dict(os.environ, TEST_GL_KIND="1", QT_QPA_PLATFORM="xcb")
    r = subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1280x1024x24", sys.executable, __file__],
                       capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    if "GL_OK" in r.stdout:
        ok("OpenGL wie QPainter, Verdeckung über Tiefenpuffer, Rückfall bei Fehler: "
           + r.stdout.split("GL_OK", 1)[1].strip())
    else:
        print("HINWEIS OpenGL-Bild nicht geprüft:", r.stdout.strip())
else:
    print("HINWEIS OpenGL-Bild nicht geprüft: kein xvfb-run")
