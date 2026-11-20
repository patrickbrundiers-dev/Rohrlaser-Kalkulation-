"""3D-Ansicht mit OpenGL (zweite Darstellung neben QPainter, Plan S10, Patrick 23.10.2026 „6b“).

Zeichnet dasselbe Modell (ansicht3d.Modell) mit derselben Drehung, demselben Licht und denselben Farben, aber auf
der Grafikkarte: auch große Baugruppen bleiben beim Drehen fein. Verdeckung über den Tiefenpuffer statt Sortieren.
Läuft nur, wenn ein OpenGL-Kontext ab Version 2.0 entsteht und die Shader übersetzt werden (gl_moeglich); sonst und
bei jedem Fehler während des Zeichnens zeichnet die Ansicht wieder mit QPainter (ansicht3d.Ansicht3D). Ohne numpy:
die Puffer werden mit array('f') gefüllt.
"""
import math
from array import array

from PySide6.QtGui import QColor, QOffscreenSurface, QOpenGLContext, QPainter, QSurfaceFormat
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt

GL_LINES, GL_TRIANGLES, GL_FLOAT = 0x0001, 0x0004, 0x1406
GL_DEPTH_TEST, GL_LEQUAL, GL_SCISSOR_TEST, GL_GREATER = 0x0B71, 0x0203, 0x0C11, 0x0204
GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT = 0x4000, 0x0100
GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA = 0x0BE2, 0x0302, 0x0303
GL_VERSION, GL_RENDERER = 0x1F02, 0x1F01
GL_STENCIL_TEST, GL_CULL_FACE = 0x0B90, 0x0B44
MIT_VERLAUF = True      # Hintergrundverlauf (aus: einfarbig wie glClear)

# Licht wie ansicht3d.licht_wert (QPainter je Dreieck), hier je Ecke mit der glatten Normalen (Gouraud): Grundlicht
# oben heller, Hauptlicht links oben vorn, Fülllicht rechts unten, Glanzlicht wie bei blankem Metall.
# hg = 1: Hintergrundverlauf (pos.xy schon Bildschirmkoordinaten, Farbe unverändert, ganz hinten)
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
uniform float hg;
uniform float persp;    // 1 / Kameraabstand (0 = orthogonal)
uniform float kante;    // Körperkanten: Farbe kfarbe, col.x = Weg längs der Kante [mm] (Strichelung)
uniform vec3 kfarbe;
uniform vec3 licht;
uniform vec3 licht2;
uniform float grund;
uniform float neigung;
uniform float fuell;
uniform float glanz;
uniform float glanz_exp;
uniform float metall;   // gespiegelte Umgebung (visualisierung.umgebung): Himmel, Horizont, Boden
uniform float himmel;
uniform float horizont;
uniform float boden;
varying vec3 farbe;
varying float nz;
varying float weg;
void main() {
    weg = col.x;
    if (hg > 0.5) {
        farbe = col;
        nz = 1.0;
        gl_Position = vec4(pos.x, pos.y, 0.999, 1.0);
        return;
    }
    vec3 d = pos - mitte;
    vec3 q = vec3(dot(r0, d), dot(r1, d), dot(r2, d));
    vec3 n = vec3(dot(r0, nrm), dot(r1, nrm), dot(r2, nrm));
    float w = 1.0 - q.z * persp;   // Tiefe: z / w = -q.z * tiefe / w ist im Bild linear wie bei den Dreiecken
    nz = dot(n, vec3(-q.x * persp, -q.y * persp, w));      // zum Betrachter (perspektivisch: zur Kamera)
    vec3 c = mix(mix(col, kfarbe, kante), vec3(1.0, 1.0, 1.0), blass);
    if (linie > 0.5) {
        farbe = c;
    } else {
        if (nz < 0.0) n = -n;
        float diff = grund + neigung * n.y + (1.0 - grund) * max(0.0, dot(n, licht))
                     + fuell * max(0.0, dot(n, licht2));
        if (metall > 0.0) {
            float ry = 2.0 * n.z * n.y;
            float env = ry >= 0.0 ? horizont + (himmel - horizont) * (2.0 * ry - ry * ry)
                                  : horizont + (boden - horizont) * min(1.0, -ry);
            diff = diff * (1.0 - metall) + env * metall;
        }
        vec3 h = normalize(licht + vec3(0.0, 0.0, 1.0));
        float spec = glanz > 0.0 ? glanz * pow(max(0.0, dot(n, h)), glanz_exp) : 0.0;
        farbe = min(c * diff + vec3(spec, spec, spec), vec3(1.0, 1.0, 1.0));
    }
    gl_Position = vec4(abb.x * q.x + abb.y * w, abb.z * q.y + abb.w * w, -q.z * tiefe - linie * 0.002 * w, w);
}
"""
FRAGMENT = """
#version 120
varying vec3 farbe;
varying float nz;
varying float weg;
uniform float linie;
uniform float alle;     // Durchsichtig: Rückseiten und verdeckte Linien nicht verwerfen
uniform float alpha;
uniform float strich;   // > 0: gestrichelt, Striche je mm Weg (Verdeckt gestrichelt)
void main() {
    if (strich > 0.0 && mod(weg * strich, 1.0) > 0.55) discard;
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


def puffer_daten(modell, farben, linien_farben, kanten=False, arten=None, klar=None):
    """Modell -> (Dreiecke, Linien, Körperkanten außen, Körperkanten innen, durchsichtige Dreiecke) als array('f') je
    Ecke: Ort (3), Normale (3), Farbe (3). arten: je Dreieck eine andere Farbart (Darstellung Flächentypen) oder None.
    klar(nr, art) -> True: Dreieck durchsichtig (Teil durchsichtig geschaltet, Prüfmodus Rohrlaser) – eigener Puffer,
    der nach den deckenden mit Mischung gezeichnet wird."""
    p = modell.punkte
    dreiecke, durch = array("f"), array("f")
    glatt = modell.glatte_normalen()            # Rundungen glatt: Normale je Ecke (große Netze flach)
    for nr, (i, j, k, art, n) in enumerate(modell.dreiecke):
        c = farben.get(arten[nr] if arten is not None else art) or farben["K"]
        ziel = durch if klar is not None and klar(nr, art) else dreiecke
        for e, x in enumerate((i, j, k)):
            ziel.extend(p[x])
            ziel.extend(glatt[nr][e] if glatt else n)
            ziel.extend(c)
    linien = array("f")
    for a, b, art, n in modell.linien:
        c = linien_farben.get(art) or linien_farben["K"]
        for q in (a, b):
            linien.extend(q)
            linien.extend(n)
            linien.extend(c)
    kante, kante_i = array("f"), array("f")
    if kanten:                  # Farbe aus dem Programm (kfarbe), hier der Weg längs der Kante für die Strichelung
        from .ansicht3d import KANTE_INNEN
        klassen = modell.kanten_klassen()
        for nr, (a, b, n) in enumerate(modell.kanten()):
            ziel = kante_i if nr < len(klassen) and klassen[nr] == KANTE_INNEN else kante
            lg = math.dist(a, b)
            for q, w in ((a, 0.0), (b, lg)):
                ziel.extend(q)
                ziel.extend(n)
                ziel.extend((w, 0.0, 0.0))
    return dreiecke, linien, kante, kante_i, durch


def koerper_daten(koerper, gewaehlt, farben, linien_farben):
    """Schnittkörper -> {Name: array('f')} wie puffer_daten: 'wk'/'wk_g' Dreiecke (nicht gewählt/gewählt),
    'wkl'/'wkl_g' Umrisslinien der beiden Ringe."""
    out = {n: array("f") for n in ("wk", "wk_g", "wkl", "wkl_g")}
    for k in koerper:
        g = "_g" if k["id"] in gewaehlt else ""
        c, cl = farben.get(k["art"]) or farben["K"], linien_farben.get(k["art"]) or linien_farben["K"]
        d = out["wk" + g]
        for a, b, cc, n in k["dreiecke"]:
            for q in (a, b, cc):
                d.extend(q)
                d.extend(n)
                d.extend(c)
        li = out["wkl" + g]
        for ring in k["ringe"]:
            for a, b in zip(ring, ring[1:]):
                for q in (a, b):
                    li.extend(q)
                    li.extend((0.0, 0.0, 1.0))
                    li.extend(cl)
    return out


def abbildung(modell, breite, hoehe, m, zoom, verschiebung, persp=0.0):
    """Maßstab und Mitte des Bildes wie ansicht3d.zeichnen, aus den 8 Ecken des Hüllquaders (schnell; das
    QPainter-Bild nimmt alle Punkte, das Bild ist hier höchstens etwas kleiner). persp: 1 / Kameraabstand."""
    cx, cy, cz = modell.mitte
    ecken = [(x - cx, y - cy, z - cz) for x in (modell.min[0], modell.max[0]) for y in (modell.min[1], modell.max[1])
             for z in (modell.min[2], modell.max[2])]

    def f(x, y, z):
        return 1.0 / (1.0 - (m[2][0] * x + m[2][1] * y + m[2][2] * z) * persp) if persp else 1.0
    bx = max(abs(m[0][0] * x + m[0][1] * y + m[0][2] * z) * f(x, y, z) for x, y, z in ecken) * 2 or 1
    by = max(abs(m[1][0] * x + m[1][1] * y + m[1][2] * z) * f(x, y, z) for x, y, z in ecken) * 2 or 1
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
        self.puffer_hg = None
        self.puffer_umriss = None
        self._farben_schl = None
        self._kanten = False
        self.puffer_wk, self._wk_schl = {}, None       # Schnittkörper (je Auswahl neu)

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
        farben = {a: _farbe(c) for a, c in ansicht3d.flaechen_farben().items()}     # V2: Material
        modus = self._modus()
        if modus == "betont":       # V5 Konturen betont: Körperflächen hell, Konturflächen kräftig
            h = ansicht3d.BETONT_HELL
            for a in ansicht3d.NEUTRAL_ARTEN:
                if a in farben:
                    farben[a] = tuple(c + (1.0 - c) * h for c in farben[a])
        arten = ansicht3d.flaechentyp_arten(modell) if modus == "typen" else None
        linien = {a: _farbe(c) for a, c in ansicht3d.LINIE.items()}
        durch = getattr(modell, "durch", None) or frozenset()
        pruef = self.ansicht.darstellung == ansicht3d.PRUEFMODUS

        def klar(nr, art):
            return nr in durch or (pruef and art in ansicht3d.PRUEF_DURCH)
        for name, daten in zip(("dreiecke", "linien", "kanten", "kanten_i", "dreiecke_d"),
                               puffer_daten(modell, farben, linien, kanten, arten,
                                            klar if durch or pruef else None)):
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
        self._farben_schl = self._farben_schluessel()

    def _modus(self):
        from . import ansicht3d
        dar = self.ansicht.darstellung
        return "typen" if dar == ansicht3d.FLAECHENTYPEN else "betont" if dar == ansicht3d.KONTUREN_BETONT else ""

    def _farben_schluessel(self):
        from . import ansicht3d, visualisierung
        a = self.ansicht
        m = a.modell
        # Kantenwinkel (andere Kanten), Durchsicht je Teil und Prüfmodus (andere Puffer) laden neu
        return (visualisierung.aktuell()["ansicht3d_material"], self._modus(), visualisierung.kanten_stil()["cos"],
                id(getattr(m, "durch", None)), a.darstellung == ansicht3d.PRUEFMODUS)

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

    def _hintergrund(self, fn):
        """Verlauf oben → unten (ansicht3d.HINTERGRUND_OBEN → HINTERGRUND): zwei Dreiecke mit demselben Programm
        (hg = 1), ohne Tiefe."""
        from . import ansicht3d
        oben, unten = ansicht3d.hintergrund_farben()      # V2: Hintergrund nach dem Aussehen
        schl = (oben.name(), unten.name())
        if self.puffer_hg is not None and getattr(self, "_hg_schl", None) != schl:
            self.puffer_hg.destroy()
            self.puffer_hg = None
        if self.puffer_hg is None:
            self._hg_schl = schl
            o, u = _farbe(oben), _farbe(unten)
            ecken = [((-1, 1), o), ((1, 1), o), ((1, -1), u), ((-1, 1), o), ((1, -1), u), ((-1, -1), u)]
            daten = array("f", [c for (x, y), f in ecken for c in (x, y, 0.0, 0.0, 0.0, 1.0, *f)])
            b = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
            b.create()
            b.bind()
            roh = daten.tobytes()
            b.allocate(roh, len(roh))
            b.release()
            self.puffer_hg = b
        pr = self.prog
        pr.bind()
        pr.setUniformValue1f(pr.uniformLocation("hg"), 1.0)
        pr.setUniformValue1f(pr.uniformLocation("linie"), 1.0)
        pr.setUniformValue1f(pr.uniformLocation("alle"), 1.0)
        pr.setUniformValue1f(pr.uniformLocation("alpha"), 1.0)
        self._puffer_zeichnen(pr, self.puffer_hg, GL_TRIANGLES, 6, fn)
        pr.setUniformValue1f(pr.uniformLocation("hg"), 0.0)
        pr.release()

    @staticmethod
    def _puffer_zeichnen(pr, b, art, n, fn):
        b.bind()
        for k, attr in enumerate(("pos", "nrm", "col")):
            loc = pr.attributeLocation(attr)
            pr.enableAttributeArray(loc)
            pr.setAttributeBuffer(loc, GL_FLOAT, 12 * k, 3, 36)
        fn.glDrawArrays(art, 0, n)
        for attr in ("pos", "nrm", "col"):
            pr.disableAttributeArray(pr.attributeLocation(attr))
        b.release()

    def _koerper_zeichnen(self, fn, pr, wert1, modell, blass, draht, roentgen):
        """Schnittkörper halb durchsichtig über den Flächen: Tiefentest an (verdeckt bleibt verdeckt), ohne in den
        Tiefenpuffer zu schreiben; die gewählte Kontur kräftiger."""
        from . import ansicht3d
        a = self.ansicht
        ks = a.koerper()
        if not ks:
            return
        gewaehlt = {k["id"] for k in ks} & set(a.markiert)
        schl = (modell, tuple(sorted(gewaehlt)))
        if schl != self._wk_schl:
            for b in self.puffer_wk.values():
                b[0].destroy()
            self.puffer_wk = {}
            farben = {x: _farbe(c) for x, c in ansicht3d.FARBE.items()}
            linien = {x: _farbe(c) for x, c in ansicht3d.LINIE.items()}
            for name, daten in koerper_daten(ks, gewaehlt, farben, linien).items():
                if not daten:
                    continue
                b = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
                b.create()
                b.bind()
                roh = daten.tobytes()
                b.allocate(roh, len(roh))
                b.release()
                self.puffer_wk[name] = (b, len(daten) // 9)
            self._wk_schl = schl
        fn.glEnable(GL_BLEND)
        fn.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        fn.glDepthMask(False)
        wert1("alle", 1.0)
        wert1("kante", 0.0)
        wert1("strich", 0.0)
        for name, art, ist_linie, alpha, breite in (
                ("wk", GL_TRIANGLES, 0.0, ansicht3d.WK_ALPHA, 0), ("wkl", GL_LINES, 1.0, 0.55, 1.0),
                ("wk_g", GL_TRIANGLES, 0.0, ansicht3d.WK_ALPHA_GEWAEHLT, 0), ("wkl_g", GL_LINES, 1.0, 0.9, 2.0)):
            if name not in self.puffer_wk or (draht and not ist_linie):
                continue
            b, n = self.puffer_wk[name]
            wert1("linie", ist_linie)
            wert1("alpha", alpha)
            wert1("blass", 0.0 if name.endswith("_g") else blass)
            if ist_linie:
                fn.glLineWidth(breite)
            self._puffer_zeichnen(pr, b, art, n, fn)
        wert1("alle", 1.0 if roentgen or draht else 0.0)
        if not roentgen:
            fn.glDepthMask(True)
            fn.glDisable(GL_BLEND)

    def _zeichnen(self):
        from . import ansicht3d
        a = self.ansicht
        fn = self.context().functions()
        h = ansicht3d.hintergrund_farben()[1]
        # QPainter (Beschriftung) lässt das Schreiben in den Tiefenpuffer abgeschaltet: vor dem Löschen wieder an
        fn.glDepthMask(True)
        fn.glColorMask(True, True, True, True)
        for art in (GL_SCISSOR_TEST, GL_STENCIL_TEST, GL_CULL_FACE, GL_BLEND, GL_DEPTH_TEST):
            fn.glDisable(art)
        fn.glClearColor(h.redF(), h.greenF(), h.blueF(), 1.0)
        fn.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if MIT_VERLAUF:
            self._hintergrund(fn)
        modell = a.modell
        if modell is None:
            return
        if getattr(a, "raster_an", False) or a.schatten_lage() is not None:
            # A7 Raster und V2 Kontaktschatten mit QPainter hinter das Modell (ohne Tiefe)
            p = QPainter(self)
            try:
                a._schatten_malen(p)
                a._raster_malen(p)
            finally:
                p.end()
            fn.glDepthMask(True)
            fn.glColorMask(True, True, True, True)
            for art in (GL_SCISSOR_TEST, GL_STENCIL_TEST, GL_CULL_FACE, GL_BLEND, GL_DEPTH_TEST):
                fn.glDisable(art)
        dar = a.darstellung
        kanten = dar in ansicht3d.MIT_KOERPERKANTEN or dar == ansicht3d.NUR_KONTUREN
        if modell is not self._modell or kanten != self._kanten or self._farben_schluessel() != self._farben_schl:
            self._hochladen(modell, kanten)
        roentgen = dar in ansicht3d.ROENTGEN_ARTEN
        draht = dar in ansicht3d.DRAHT_ARTEN
        stil_k = ansicht3d.visualisierung.kanten_stil()
        pruef = dar == ansicht3d.PRUEFMODUS
        # verdeckte Kanten gestrichelt: Verdeckt gestrichelt, Technisch, Prüfmodus immer, sonst nach der Einstellung
        strich = not draht and not roentgen and (dar in ansicht3d.IMMER_VERDECKT or (
            stil_k["verdeckt"] and dar not in ansicht3d.OHNE_VERDECKT))
        weiss = ansicht3d.VERDECKT_HELL if dar == ansicht3d.VERDECKT else ansicht3d.WEISS_ANTEIL.get(dar, 0.0)
        kanten_an = stil_k["an"] or draht or dar in (ansicht3d.TECHNISCH, ansicht3d.PRUEFMODUS)
        innen_an = (stil_k["innen"] or pruef) and dar != ansicht3d.REALISTISCH
        dezent = dar == ansicht3d.REALISTISCH
        betont = dar == ansicht3d.KONTUREN_BETONT
        m = ansicht3d._drehung(a.gier, a.nick, getattr(a, "roll", 0.0))
        w, hh = max(1, self.width()), max(1, self.height())
        pz = ansicht3d.persp_faktor(modell, a.perspektive)
        s, ox, oy = abbildung(modell, w, hh, m, a.zoom, a.versatz, pz)
        fn.glEnable(GL_DEPTH_TEST)
        fn.glDepthFunc(GL_LEQUAL)
        pr = self.prog
        pr.bind()

        def wert1(name, v):
            # einzelne Zahlen ausdrücklich als float (setUniformValue nimmt sonst glUniform1i: GL-Fehler, Wert bleibt 0)
            pr.setUniformValue1f(pr.uniformLocation(name), float(v))
        from . import visualisierung
        l1, l2, *licht_zahlen = visualisierung.licht_werte()      # V2: Lichtprofil und Material
        for name, wert in (("r0", m[0]), ("r1", m[1]), ("r2", m[2]), ("mitte", modell.mitte),
                           ("licht", l1), ("licht2", l2),
                           ("kfarbe", _farbe(ansicht3d.HAUCH_FARBE if dar == ansicht3d.NUR_KONTUREN
                                             else QColor(ansicht3d.TECHNISCH_KANTE) if dar == ansicht3d.TECHNISCH
                                             else QColor(stil_k["farbe"])))):
            pr.setUniformValue(pr.uniformLocation(name), *map(float, wert))
        for name, wert in zip(("grund", "neigung", "fuell", "glanz", "glanz_exp", "metall", "himmel", "horizont", "boden"),
                              licht_zahlen):
            wert1(name, wert)
        pr.setUniformValue(pr.uniformLocation("abb"), 2 * s / w, 2 * ox / w - 1, 2 * s / hh, 1 - 2 * oy / hh)
        wert1("tiefe", 1.0 / max(1e-6, modell.groesse))
        wert1("persp", pz)
        blass = ansicht3d.BLASS if a.blass() else 0.0
        wert1("alle", 1.0 if roentgen or draht else 0.0)
        wert1("strich", 0.0)
        wert1("kante", 0.0)
        if roentgen:            # Röntgen: Flächen halb durchsichtig ohne Tiefenpuffer, Linien darüber
            fn.glEnable(GL_BLEND)
            fn.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            fn.glDepthMask(False)
        if draht:               # Drahtgitter: alle Kanten und Konturen, ohne Verdeckung
            fn.glDisable(GL_DEPTH_TEST)
        naht = set(modell.arten) & set(ansicht3d.NAEHTE)
        kfarbe = _farbe(ansicht3d.HAUCH_FARBE if dar == ansicht3d.NUR_KONTUREN else
                        QColor(ansicht3d.TECHNISCH_KANTE) if dar == ansicht3d.TECHNISCH else QColor(stil_k["farbe"]))
        ifarbe = _farbe(QColor(stil_k["innen_farbe"]))
        kbreite = stil_k["breite"]
        for name, art, ist_linie in (("dreiecke", GL_TRIANGLES, 0.0), ("kanten", GL_LINES, 1.0),
                                     ("kanten_i", GL_LINES, 1.0), ("linien", GL_LINES, 1.0)):
            if name not in self.puffer or (draht and name == "dreiecke"):
                continue
            if name.startswith("kanten") and not kanten_an or name == "kanten_i" and not (innen_an or draht):
                continue
            b, n = self.puffer[name]
            wert1("linie", ist_linie)
            wert1("kante", 1.0 if name.startswith("kanten") else 0.0)
            pr.setUniformValue(pr.uniformLocation("kfarbe"), *(ifarbe if name == "kanten_i" else kfarbe))
            wert1("blass", max(blass, weiss) if name == "dreiecke" else blass)
            dez = dezent and name == "kanten"
            wert1("alpha", ansicht3d.ALPHA if roentgen and not ist_linie else 0.47 if dez else 1.0)
            if dez and not roentgen:
                fn.glEnable(GL_BLEND)
                fn.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            if ist_linie:
                fn.glLineWidth(kbreite * (0.75 if dez else 0.9 if name == "kanten_i" else 1.0)
                               if name.startswith("kanten") else ansicht3d.NAHT_BREITE if naht else
                               ansicht3d.BETONT_BREITE if betont else 2.2)
            self._puffer_zeichnen(pr, b, art, n, fn)
            if dez and not roentgen:
                fn.glDisable(GL_BLEND)
        pr.setUniformValue(pr.uniformLocation("kfarbe"), *kfarbe)
        if "dreiecke_d" in self.puffer and not draht:
            # durchsichtige Teile (Durchsicht je Teil, Prüfmodus: Außenwand/Schnitte): nach den deckenden, gemischt,
            # ohne in den Tiefenpuffer zu schreiben – Innenwand, Bohrungsränder und Kanten dahinter bleiben sichtbar
            b, n = self.puffer["dreiecke_d"]
            fn.glEnable(GL_BLEND)
            fn.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            fn.glDepthMask(False)
            wert1("linie", 0.0)
            wert1("kante", 0.0)
            wert1("alle", 1.0)
            wert1("blass", max(blass, weiss))
            wert1("alpha", stil_k["alpha"])
            self._puffer_zeichnen(pr, b, GL_TRIANGLES, n, fn)
            wert1("alle", 1.0 if roentgen or draht else 0.0)
            if not roentgen:
                fn.glDepthMask(True)
                fn.glDisable(GL_BLEND)
        self._koerper_zeichnen(fn, pr, wert1, modell, blass, draht, roentgen)
        if dar in ansicht3d.UMRISS_ARTEN:     # Umriss der Rundungen hängt von der Blickrichtung ab
            # V3: beim Drehen den letzten Umriss zeigen, erst in Ruhe neu rechnen (Python-Schleife je Kante)
            bewegt = a._maus is not None or a._eilig
            schl = (modell, m, pz)
            if not bewegt or self.puffer_umriss is None or getattr(self, "_umriss_modell", None) is not modell:
                if getattr(self, "_umriss_schl", None) != schl:
                    daten = array("f")
                    for p0, p1, _ in ansicht3d.umriss(modell, m, pz):
                        for q in (p0, p1):
                            daten.extend(q)
                            daten.extend((0.0, 0.0, 1.0))
                            daten.extend((0.0, 0.0, 0.0))
                    if self.puffer_umriss is None:
                        self.puffer_umriss = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
                        self.puffer_umriss.create()
                    b = self.puffer_umriss
                    b.bind()
                    roh = daten.tobytes()
                    b.allocate(roh, len(roh))
                    b.release()
                    self._umriss_n, self._umriss_schl, self._umriss_modell = len(daten) // 9, schl, modell
            if getattr(self, "_umriss_n", 0):
                b = self.puffer_umriss
                wert1("linie", 1.0)
                wert1("kante", 1.0)
                wert1("alle", 1.0)
                wert1("blass", blass)
                fn.glLineWidth(kbreite)
                self._puffer_zeichnen(pr, b, GL_LINES, self._umriss_n, fn)
        if strich and kanten_an:        # verdeckte Kanten: hinter den Flächen, hell und gestrichelt (innen blau)
            fn.glDepthFunc(GL_GREATER)
            fn.glDepthMask(False)
            fn.glEnable(GL_BLEND)
            fn.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            wert1("alle", 1.0)
            wert1("kante", 1.0)
            wert1("linie", 1.0)
            wert1("blass", blass)
            wert1("strich", s / 7.0)            # ein Strich je 7 px
            for name, farbe, alpha in (("kanten", _farbe(ansicht3d.VERDECKT_FARBE), 1.0),
                                       ("kanten_i", ifarbe, 0.6)):
                if name not in self.puffer or name == "kanten_i" and not innen_an:
                    continue
                b, n = self.puffer[name]
                pr.setUniformValue(pr.uniformLocation("kfarbe"), *farbe)
                wert1("alpha", alpha)
                fn.glLineWidth(max(0.8, kbreite * 0.8))
                self._puffer_zeichnen(pr, b, GL_LINES, n, fn)
            wert1("strich", 0.0)
            wert1("alpha", 1.0)
            fn.glDisable(GL_BLEND)
            fn.glDepthMask(True)
            fn.glDepthFunc(GL_LEQUAL)
        pr.release()
        if roentgen:
            fn.glDepthMask(True)
            fn.glDisable(GL_BLEND)
        fn.glDisable(GL_DEPTH_TEST)

