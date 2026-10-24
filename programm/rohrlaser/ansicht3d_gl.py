"""3D-Ansicht mit OpenGL (zweite Darstellung neben QPainter, Plan S10, Patrick 23.10.2026 „6b“).

Zeichnet dasselbe Modell (ansicht3d.Modell) mit derselben Drehung, demselben Licht und denselben Farben, aber auf
der Grafikkarte: auch große Baugruppen bleiben beim Drehen fein. Verdeckung über den Tiefenpuffer statt Sortieren.
Läuft nur, wenn ein OpenGL-Kontext ab Version 2.0 entsteht und die Shader übersetzt werden (gl_moeglich); sonst und
bei jedem Fehler während des Zeichnens zeichnet die Ansicht wieder mit QPainter (ansicht3d.Ansicht3D). Ohne numpy:
die Puffer werden mit array('f') gefüllt.
"""
from array import array

from PySide6.QtGui import QOffscreenSurface, QOpenGLContext, QPainter, QSurfaceFormat
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt

GL_LINES, GL_TRIANGLES, GL_FLOAT = 0x0001, 0x0004, 0x1406
GL_DEPTH_TEST, GL_LEQUAL, GL_SCISSOR_TEST = 0x0B71, 0x0203, 0x0C11
GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT = 0x4000, 0x0100
GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA = 0x0BE2, 0x0302, 0x0303
GL_VERSION, GL_RENDERER = 0x1F02, 0x1F01

VERTEX = """
#version 120
attribute vec3 pos;
attribute vec3 nrm;
attribute vec3 col;
uniform vec3 r0;
uniform vec3 r1;
uniform vec3 r2;
uniform vec3 mitte;
uniform vec4 abb;       // x = ax, y = bx, z = ay, w = by: Bildschirm aus gedrehten Koordinaten (NDC)
uniform float tiefe;
uniform float linie;
uniform float blass;    // „nur Gewähltes hervorheben“: Anteil Weiß
uniform vec3 licht;
varying vec3 farbe;
varying float nz;
void main() {
    vec3 d = pos - mitte;
    vec3 q = vec3(dot(r0, d), dot(r1, d), dot(r2, d));
    vec3 n = vec3(dot(r0, nrm), dot(r1, nrm), dot(r2, nrm));
    nz = n.z;
    float hell = linie > 0.5 ? 1.0 : 0.42 + 0.58 * max(0.0, dot(n.z < 0.0 ? -n : n, licht));
    farbe = mix(col, vec3(1.0, 1.0, 1.0), blass) * hell;
    gl_Position = vec4(abb.x * q.x + abb.y, abb.z * q.y + abb.w, -q.z * tiefe - linie * 0.002, 1.0);
}
"""
FRAGMENT = """
#version 120
varying vec3 farbe;
varying float nz;
uniform float linie;
uniform float alle;     // Durchsichtig: Rückseiten und verdeckte Linien nicht verwerfen
uniform float alpha;
void main() {
    if (alle < 0.5 && (nz < 0.0 || (linie < 0.5 && nz <= 0.0))) discard;     // Rückseiten wie in ansicht3d.zeichnen
    gl_FragColor = vec4(farbe, alpha);
}
"""
_PRUEFUNG = None        # (möglich, Grund) – einmal je Programmstart


def gl_moeglich():
    """(True, Beschreibung der Grafik) oder (False, Grund): OpenGL-Kontext ab 2.0 und Shader übersetzbar.
    Ergebnis wird gemerkt (einmal je Programmstart)."""
    global _PRUEFUNG
    if _PRUEFUNG is not None:
        return _PRUEFUNG
    try:
        ctx = QOpenGLContext()
        if not ctx.create():
            _PRUEFUNG = (False, "kein OpenGL-Kontext")
            return _PRUEFUNG
        flaeche = QOffscreenSurface()
        flaeche.setFormat(ctx.format())
        flaeche.create()
        if not ctx.makeCurrent(flaeche):
            _PRUEFUNG = (False, "OpenGL-Kontext nicht nutzbar")
            return _PRUEFUNG
        f = ctx.format()
        if (f.majorVersion(), f.minorVersion()) < (2, 0):
            _PRUEFUNG = (False, f"OpenGL {f.majorVersion()}.{f.minorVersion()} zu alt (mindestens 2.0)")
        else:
            prog = QOpenGLShaderProgram()
            if not (prog.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX) and
                    prog.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAGMENT) and prog.link()):
                _PRUEFUNG = (False, "Shader nicht übersetzbar: " + (prog.log() or "").strip()[:200])
            else:
                fn = ctx.functions()
                _PRUEFUNG = (True, f"{fn.glGetString(GL_RENDERER)}, OpenGL {fn.glGetString(GL_VERSION)}")
        ctx.doneCurrent()
    except Exception as e:  # jede Panne: QPainter
        _PRUEFUNG = (False, f"OpenGL-Fehler: {e or type(e).__name__}")
    return _PRUEFUNG


def _farbe(c):
    return (c.redF(), c.greenF(), c.blueF())


def puffer_daten(modell, farben, linien_farben, kanten=False):
    """Modell -> (Dreiecke, Linien, Körperkanten) als array('f') je Ecke: Ort (3), Normale (3), Farbe (3)."""
    p = modell.punkte
    dreiecke = array("f")
    glatt = modell.glatte_normalen()            # Rundungen glatt: Normale je Ecke (große Netze flach)
    for nr, (i, j, k, art, n) in enumerate(modell.dreiecke):
        c = farben.get(art) or farben["K"]
        for e, x in enumerate((i, j, k)):
            dreiecke.extend(p[x])
            dreiecke.extend(glatt[nr][e] if glatt else n)
            dreiecke.extend(c)
    linien = array("f")
    for a, b, art, n in modell.linien:
        c = linien_farben.get(art) or linien_farben["K"]
        for q in (a, b):
            linien.extend(q)
            linien.extend(n)
            linien.extend(c)
    kante = array("f")
    if kanten:
        from .ansicht3d import KANTE
        c = _farbe(KANTE)
        for a, b, n in modell.kanten():
            for q in (a, b):
                kante.extend(q)
                kante.extend(n)
                kante.extend(c)
    return dreiecke, linien, kante


def abbildung(modell, breite, hoehe, m, zoom, verschiebung):
    """Maßstab und Mitte des Bildes wie ansicht3d.zeichnen, aus den 8 Ecken des Hüllquaders (schnell; das
    QPainter-Bild nimmt alle Punkte, das Bild ist hier höchstens etwas kleiner)."""
    cx, cy, cz = modell.mitte
    ecken = [(x - cx, y - cy, z - cz) for x in (modell.min[0], modell.max[0]) for y in (modell.min[1], modell.max[1])
             for z in (modell.min[2], modell.max[2])]
    bx = max(abs(m[0][0] * x + m[0][1] * y + m[0][2] * z) for x, y, z in ecken) * 2 or 1
    by = max(abs(m[1][0] * x + m[1][1] * y + m[1][2] * z) for x, y, z in ecken) * 2 or 1
    massstab = zoom * 0.9 * min(breite / bx, hoehe / by)
    return massstab, breite / 2 + verschiebung[0], hoehe / 2 + verschiebung[1]


class GLFlaeche(QOpenGLWidget):
    """Zeichenfläche der Ansicht3D mit OpenGL. Maus und Rad gehen an die Ansicht (durchlässig); Titel und Legende
    zeichnet die Ansicht mit QPainter darüber (_beschriften). Schlägt OpenGL fehl, ruft sie ansicht._gl_aus(Grund)."""

    def __init__(self, ansicht):
        super().__init__(ansicht)
        self.ansicht = ansicht
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.prog, self.puffer, self._modell, self.fehler = None, {}, None, None
        self._kanten = False

    def initializeGL(self):
        try:
            self.prog = QOpenGLShaderProgram(self)
            if not (self.prog.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX) and
                    self.prog.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAGMENT) and self.prog.link()):
                raise RuntimeError("Shader: " + (self.prog.log() or "").strip()[:200])
        except Exception as e:  # OpenGL nicht nutzbar: zurück zu QPainter
            self._fehler(e)

    def _fehler(self, e):
        self.fehler = str(e) or type(e).__name__
        self.ansicht._gl_aus(self.fehler)

    def _hochladen(self, modell, kanten=False):
        from . import ansicht3d
        for b in self.puffer.values():
            b[0].destroy()
        self.puffer = {}
        farben = {a: _farbe(c) for a, c in ansicht3d.FARBE.items()}
        linien = {a: _farbe(c) for a, c in ansicht3d.LINIE.items()}
        for name, daten in zip(("dreiecke", "linien", "kanten"), puffer_daten(modell, farben, linien, kanten)):
            if not daten:
                continue
            b = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
            b.create()
            b.bind()
            roh = daten.tobytes()
            b.allocate(roh, len(roh))
            b.release()
            self.puffer[name] = (b, len(daten) // 9)
        self._modell, self._kanten = modell, kanten

    def paintGL(self):
        if self.fehler:
            return
        try:
            self._zeichnen()
        except Exception as e:  # z. B. Treiberfehler: zurück zu QPainter
            self._fehler(e)
            return
        p = QPainter(self)
        self.ansicht._beschriften(p)
        p.end()

    def _zeichnen(self):
        from . import ansicht3d
        a = self.ansicht
        fn = self.context().functions()
        h = ansicht3d.HINTERGRUND
        # QPainter (Beschriftung) lässt das Schreiben in den Tiefenpuffer abgeschaltet: vor dem Löschen wieder an
        fn.glDepthMask(True)
        fn.glDisable(GL_SCISSOR_TEST)
        fn.glClearColor(h.redF(), h.greenF(), h.blueF(), 1.0)
        fn.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        modell = a.modell
        if modell is None:
            return
        kanten = a.darstellung == ansicht3d.MIT_KANTEN
        if modell is not self._modell or kanten != self._kanten:
            self._hochladen(modell, kanten)
        roentgen = a.darstellung == ansicht3d.DURCHSICHTIG
        m = ansicht3d._drehung(a.gier, a.nick)
        w, hh = max(1, self.width()), max(1, self.height())
        s, ox, oy = abbildung(modell, w, hh, m, a.zoom, a.versatz)
        fn.glEnable(GL_DEPTH_TEST)
        fn.glDepthFunc(GL_LEQUAL)
        pr = self.prog
        pr.bind()
        for name, wert in (("r0", m[0]), ("r1", m[1]), ("r2", m[2]), ("mitte", modell.mitte),
                           ("licht", (-0.35, 0.45, 0.82))):
            pr.setUniformValue(pr.uniformLocation(name), *map(float, wert))
        pr.setUniformValue(pr.uniformLocation("abb"), 2 * s / w, 2 * ox / w - 1, 2 * s / hh, 1 - 2 * oy / hh)
        # einzelne Zahlen ausdrücklich als float (setUniformValue nimmt sonst glUniform1i: GL-Fehler, Wert bleibt 0)
        pr.setUniformValue1f(pr.uniformLocation("tiefe"), 1.0 / max(1e-6, modell.groesse))
        pr.setUniformValue1f(pr.uniformLocation("blass"), ansicht3d.BLASS if a.blass() else 0.0)
        pr.setUniformValue1f(pr.uniformLocation("alle"), 1.0 if roentgen else 0.0)
        if roentgen:            # Röntgen: Flächen halb durchsichtig ohne Tiefenpuffer, Linien darüber
            fn.glEnable(GL_BLEND)
            fn.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            fn.glDepthMask(False)
        for name, art, ist_linie in (("dreiecke", GL_TRIANGLES, 0.0), ("kanten", GL_LINES, 1.0),
                                     ("linien", GL_LINES, 1.0)):
            if name not in self.puffer:
                continue
            b, n = self.puffer[name]
            pr.setUniformValue1f(pr.uniformLocation("linie"), ist_linie)
            pr.setUniformValue1f(pr.uniformLocation("alpha"), ansicht3d.ALPHA if roentgen and not ist_linie else 1.0)
            if ist_linie:
                fn.glLineWidth(1.1 if name == "kanten" else
                               ansicht3d.NAHT_BREITE if set(modell.arten) & set(ansicht3d.NAEHTE) else 2.2)
            b.bind()
            for k, attr in enumerate(("pos", "nrm", "col")):
                loc = pr.attributeLocation(attr)
                pr.enableAttributeArray(loc)
                pr.setAttributeBuffer(loc, GL_FLOAT, 12 * k, 3, 36)
            fn.glDrawArrays(art, 0, n)
            for attr in ("pos", "nrm", "col"):
                pr.disableAttributeArray(pr.attributeLocation(attr))
            b.release()
        pr.release()
        if roentgen:
            fn.glDepthMask(True)
            fn.glDisable(GL_BLEND)
        fn.glDisable(GL_DEPTH_TEST)

