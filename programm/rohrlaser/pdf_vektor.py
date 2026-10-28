"""Linien einer PDF-Zeichnung aus dem CAD (Plan W7 Stufe 2, Patrick 26.10.2026: Konturen auch aus PDF, erst als
Testfunktion): Pfade und Texte der ersten Seite werden zu einer kleinen DXF (Text), die dieselbe Rohrerkennung liest
wie eine echte DXF (dxf_rohr.erkennen: Ansichten, Maßstab aus der Bemaßung, Profil aus dem Schnitt, Enden, Konturen).

Ein PDF kennt keine Layer; die Art einer Linie ergibt sich aus Strichstärke und Strichmuster (DIN ISO 128):
- breit und durchgezogen: sichtbare Kante (Layer KONTUR),
- gestrichelt: verdeckte Kante (Layer VERDECKT, Linientyp HIDDEN),
- Strich-Punkt (langer und kurzer Strich): Mittellinie (Layer MITTELLINIE, Linientyp CENTER),
- schmal und durchgezogen: Maß-, Hilfs- und Schraffurlinien (Layer BEMASSUNG).
„Breit“ ist die größte Strichstärke der Zeichnung (nach Länge gewichtet), schmal alles unter 70 % davon. Haben alle
Linien dieselbe Stärke, sind alle durchgezogenen Linien sichtbar (Hinweis). Gefüllte Flächen (Maßpfeile, Schrift als
Kurven) fallen weg. Bézierkurven, die einem Kreisbogen folgen, werden ARC bzw. CIRCLE (Bohrungen), sonst kurze
Strecken. Einheit: Millimeter auf dem Papier (1 pt = 25,4/72 mm); den Maßstab liest die Rohrerkennung aus den Maßen
bzw. dem Schriftfeld. Texte mit Lage, Höhe und Drehung (Maßzahlen, Schriftfeld). Ohne Qt."""
import ctypes
import math

from . import protokoll

PT = 25.4 / 72              # mm je Punkt
SCHMAL_ANTEIL = 0.7         # Strichstärke darunter: schmale Linie
BOGEN_TOL = 0.02            # Bézier als Kreisbogen, wenn Abweichung höchstens so viel × Radius
MIN_LINIEN = 8              # weniger Strecken: keine Vektorzeichnung (z. B. Scan im PDF)


def _matrix(raw, obj):
    m = raw.FS_MATRIX()
    if not raw.FPDFPageObj_GetMatrix(obj, m):
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    return (m.a, m.b, m.c, m.d, m.e, m.f)


def _mal(m1, m2):
    """Erst m1, dann m2 (PDF-Matrizen a b c d e f)."""
    a, b, c, d, e, f = m1
    A, B, C, D, E, F = m2
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, e * A + f * C + E, e * B + f * D + F)


def _anwenden(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def _objekte(raw, seite):
    """(Pfadobjekt, Matrix bis zur Seite) aller Pfade, auch in Formularobjekten (XObject)."""
    out = []

    def gehen(obj, aussen, tiefe):
        typ = raw.FPDFPageObj_GetType(obj)
        m = _mal(_matrix(raw, obj), aussen)
        if typ == raw.FPDF_PAGEOBJ_PATH:
            out.append((obj, m))
        elif typ == raw.FPDF_PAGEOBJ_FORM and tiefe < 8:
            for i in range(raw.FPDFFormObj_CountObjects(obj)):
                gehen(raw.FPDFFormObj_GetObject(obj, i), m, tiefe + 1)

    for i in range(raw.FPDFPage_CountObjects(seite)):
        gehen(raw.FPDFPage_GetObject(seite, i), (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), 0)
    return out


def _segmente(raw, obj, m):
    """Teilpfade [[('M'|'L'|'C', Punkte…)], geschlossen] in Seitenkoordinaten (pt)."""
    zuege, zug = [], None
    x, y = ctypes.c_float(), ctypes.c_float()
    bez = []
    for i in range(raw.FPDFPath_CountSegments(obj)):
        seg = raw.FPDFPath_GetPathSegment(obj, i)
        raw.FPDFPathSegment_GetPoint(seg, ctypes.byref(x), ctypes.byref(y))
        p = _anwenden(m, x.value, y.value)
        typ = raw.FPDFPathSegment_GetType(seg)
        if typ == raw.FPDF_SEGMENT_MOVETO:
            zug = [[("M", p)], False]
            zuege.append(zug)
            bez = []
        elif zug is None:
            continue
        elif typ == raw.FPDF_SEGMENT_BEZIERTO:
            bez.append(p)
            if len(bez) == 3:
                zug[0].append(("C", *bez))
                bez = []
        else:
            zug[0].append(("L", p))
        if raw.FPDFPathSegment_GetClose(seg) and zug is not None:
            zug[1] = True
    return zuege


def _strich(raw, obj):
    """(Strichstärke [pt], Muster) mit Muster '' (durchgezogen), 'strich' oder 'mittel'."""
    breite = ctypes.c_float()
    w = breite.value if raw.FPDFPageObj_GetStrokeWidth(obj, ctypes.byref(breite)) else 1.0
    n = raw.FPDFPageObj_GetDashCount(obj)
    if n <= 0:
        return w, ""
    feld = (ctypes.c_float * n)()
    if not raw.FPDFPageObj_GetDashArray(obj, feld, n):
        return w, ""
    werte = [v for v in feld if v > 0]
    if not werte:
        return w, ""
    striche = werte[0::2]
    return w, ("mittel" if len(striche) >= 2 and max(striche) > 2.5 * min(striche) else "strich")


def _bezier(p0, p1, p2, p3, t):
    s = 1 - t
    return (s ** 3 * p0[0] + 3 * s * s * t * p1[0] + 3 * s * t * t * p2[0] + t ** 3 * p3[0],
            s ** 3 * p0[1] + 3 * s * s * t * p1[1] + 3 * s * t * t * p2[1] + t ** 3 * p3[1])


def _kreis3(a, b, c):
    """Mittelpunkt und Radius durch drei Punkte oder None (fast gerade)."""
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    ux = ((a[0] ** 2 + a[1] ** 2) * (b[1] - c[1]) + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1]) +
          (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])) / d
    uy = ((a[0] ** 2 + a[1] ** 2) * (c[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0]) +
          (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])) / d
    return (ux, uy), math.dist((ux, uy), a)


def _als_bogen(p0, p1, p2, p3):
    """Bézier als Kreisbogen: (Mitte, Radius, Startwinkel, Endwinkel [Grad, gegen den Uhrzeigersinn]) oder None."""
    k = _kreis3(p0, _bezier(p0, p1, p2, p3, 0.5), p3) if math.dist(p0, p3) > 1e-9 else \
        _kreis3(p0, _bezier(p0, p1, p2, p3, 1 / 3), _bezier(p0, p1, p2, p3, 2 / 3))
    if not k or k[1] > 1e5:
        return None
    c, r = k
    for t in (0.25, 0.75):
        if abs(math.dist(_bezier(p0, p1, p2, p3, t), c) - r) > BOGEN_TOL * r + 1e-3:
            return None
    w0 = math.degrees(math.atan2(p0[1] - c[1], p0[0] - c[0]))
    w1 = math.degrees(math.atan2(p3[1] - c[1], p3[0] - c[0]))
    wm = _bezier(p0, p1, p2, p3, 0.5)
    links = (p3[0] - p0[0]) * (wm[1] - p0[1]) - (p3[1] - p0[1]) * (wm[0] - p0[0]) < 0   # Mitte rechts: ccw
    return (c, r, w0, w1) if links else (c, r, w1, w0)


def _texte(raw, seite):
    """Wörter [(x, y, Höhe, Winkel [Grad], Text)] in pt: Zeichen gleicher Drehung ohne Lücke zusammen."""
    tp = raw.FPDFText_LoadPage(seite)
    if not tp:
        return []
    out, wort = [], None
    x, y = ctypes.c_double(), ctypes.c_double()
    try:
        for i in range(raw.FPDFText_CountChars(tp)):
            ch = chr(raw.FPDFText_GetUnicode(tp, i))
            if ch in "\r\n\x02" or ch.isspace():
                if wort and ch == " " and wort[5] < 3:      # ein Leerzeichen im Wort („Ø 42,4“, „L = 860“)
                    wort[4] += " "
                    wort[5] += 1
                    continue
                wort = None
                continue
            raw.FPDFText_GetCharOrigin(tp, i, ctypes.byref(x), ctypes.byref(y))
            w = round(math.degrees(raw.FPDFText_GetCharAngle(tp, i)), 1) % 360
            h = (raw.FPDFText_GetFontSize(tp, i) or 10.0) * _text_skala(raw, tp, i)
            if wort is not None and abs(wort[3] - w) < 1 and \
                    math.dist(wort[6], (x.value, y.value)) < 1.6 * h * (1 + wort[5]):
                wort[4] += ch
                wort[5] = 0
                wort[6] = (x.value, y.value)
            else:
                wort = [x.value, y.value, h, w, ch, 0, (x.value, y.value)]
                out.append(wort)
    finally:
        raw.FPDFText_ClosePage(tp)
    return [(a, b, h * 0.7, w, t.strip()) for a, b, h, w, t, _n, _l in out if t.strip()]


def _text_skala(raw, tp, i):
    """Vergrößerung der Schrift durch die Textmatrix (CAD zeichnet oft mit Schriftgröße 1 und skaliert)."""
    m = raw.FS_MATRIX()
    if not raw.FPDFText_GetMatrix(tp, i, m):
        return 1.0
    return math.sqrt(abs(m.a * m.d - m.b * m.c)) or 1.0


def lesen(pfad):
    """Linien und Texte der ersten Seite: dict(strecken [(p, q, Art)], boegen [(c, r, w0, w1, Art)], kreise
    [(c, r, Art)], texte [(p, h, w, text)], gleich_breit) in mm (y nach oben) oder None (keine Vektorzeichnung)."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    try:
        pdf = pdfium.PdfDocument(str(pfad))
    except Exception as e:  # noqa: BLE001 – PDF für Linien öffnen
        protokoll.nebenbei(e, "PDF für Linien öffnen")
        return None
    try:
        seite = pdf[0]
        roh = []                # (Stärke, Muster, Teilpfade)
        for obj, m in _objekte(raw, seite.raw):
            fuell, strich = ctypes.c_int(), ctypes.c_int()
            raw.FPDFPath_GetDrawMode(obj, ctypes.byref(fuell), ctypes.byref(strich))
            if not strich.value:
                continue        # nur gefüllt: Maßpfeil, Schrift als Kurve, Schraffurfläche
            w, muster = _strich(raw, obj)
            skala = math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) or 1.0
            roh.append((w * skala, muster, _segmente(raw, obj, m)))
        texte = _texte(raw, seite.raw)
    finally:
        pdf.close()
    laengen = {}
    for w, _muster, zuege in roh:
        for zug, _zu in zuege:
            lg = sum(math.dist(_ende(a), _ende(b)) for a, b in zip(zug, zug[1:], strict=False))
            laengen[round(w, 2)] = laengen.get(round(w, 2), 0.0) + lg
    if not laengen:
        return None
    breit = max(laengen)
    gleich = len([w for w in laengen if w < SCHMAL_ANTEIL * breit]) == 0
    erg = dict(strecken=[], boegen=[], kreise=[], texte=[], gleich_breit=gleich)

    def mm(p):
        return (p[0] * PT, p[1] * PT)

    for w, muster, zuege in roh:
        art = "verdeckt" if muster == "strich" else "mittel" if muster == "mittel" else \
            "sicht" if gleich or w >= SCHMAL_ANTEIL * breit else "mass"
        for zug, zu in zuege:
            if zu and _ende(zug[-1]) != _ende(zug[0]):
                zug = zug + [("L", _ende(zug[0]))]
            boegen = []
            for a, b in zip(zug, zug[1:], strict=False):
                p = _ende(a)
                if b[0] == "C":
                    bg = _als_bogen(p, b[1], b[2], b[3])
                    if bg:
                        boegen.append(bg)
                        continue
                    pk = [p] + [_bezier(p, b[1], b[2], b[3], t / 8) for t in range(1, 9)]
                    erg["strecken"] += [(mm(s), mm(e), art) for s, e in zip(pk, pk[1:], strict=False)]
                elif math.dist(p, b[1]) > 1e-6:
                    erg["strecken"].append((mm(p), mm(b[1]), art))
            erg["boegen"] += [(mm(c), r * PT, w0, w1, art) for c, r, w0, w1 in boegen]
    _kreise_zusammen(erg)
    erg["texte"] = [(mm((x, y)), h * PT, w, t) for x, y, h, w, t in texte]
    if len(erg["strecken"]) + len(erg["boegen"]) + len(erg["kreise"]) < MIN_LINIEN:
        return None
    return erg


def _ende(seg):
    return seg[-1] if seg[0] in ("L", "C") else seg[1]


def _kreise_zusammen(erg):
    """Bögen mit gleicher Mitte und gleichem Radius, die zusammen 360° ergeben, werden ein Kreis."""
    gruppen = {}
    for bg in erg["boegen"]:
        c, r, w0, w1, art = bg
        gruppen.setdefault((round(c[0], 2), round(c[1], 2), round(r, 2), art), []).append(bg)
    rest = []
    for (cx, cy, r, art), bs in gruppen.items():
        summe = sum((w1 - w0) % 360 or 360 for _c, _r, w0, w1, _a in bs)
        if abs(summe - 360) < 1:
            erg["kreise"].append(((bs[0][0][0], bs[0][0][1]), bs[0][1], art))
        else:
            rest += bs
    erg["boegen"] = rest


LAYER = {"sicht": ("KONTUR", ""), "verdeckt": ("VERDECKT", "HIDDEN"), "mittel": ("MITTELLINIE", "CENTER"),
         "mass": ("BEMASSUNG", "")}


def dxf_text(pfad):
    """Die Zeichnung als DXF-Text (R12, mm) für dxf_rohr.erkennen oder None (keine Vektorzeichnung)."""
    erg = lesen(pfad)
    if not erg:
        return None
    z = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
         "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER"]
    for name, lt in LAYER.values():
        z += ["0", "LAYER", "2", name, "70", "0", "62", "7", "6", lt or "CONTINUOUS"]
    z += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]

    def f(v):
        return f"{v:.4f}"

    for p, q, art in erg["strecken"]:
        z += ["0", "LINE", "8", LAYER[art][0], "10", f(p[0]), "20", f(p[1]), "11", f(q[0]), "21", f(q[1])]
    for c, r, w0, w1, art in erg["boegen"]:
        z += ["0", "ARC", "8", LAYER[art][0], "10", f(c[0]), "20", f(c[1]), "40", f(r), "50", f(w0 % 360),
              "51", f(w1 % 360)]
    for c, r, art in erg["kreise"]:
        z += ["0", "CIRCLE", "8", LAYER[art][0], "10", f(c[0]), "20", f(c[1]), "40", f(r)]
    for p, h, w, t in erg["texte"]:
        layer = "BEMASSUNG" if _ist_masszahl(t) else "TEXT"
        z += ["0", "TEXT", "8", layer, "10", f(p[0]), "20", f(p[1]), "40", f(h), "50", f(w), "1", t]
    z += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(z) + "\n"


def _ist_masszahl(t):
    from .dxf_rohr import zahl
    return zahl(t) is not None or str(t).strip()[:1] in ("Ø", "⌀")
