"""DXF-Export der Abwicklung aus dem Blech-Editor (Plan S4, Patrick 23.10.2026 „3a: DXF mit Layern“).

Eigener schlanker Schreiber für DXF R12 (ASCII), ohne fremde Bibliothek: Linien, Bögen, Kreise und Texte auf den
Layern Außenkontur, Innenkontur, Biegelinie hoch, Biegelinie runter, Gravur und Beschriftung (Namen in der
Einstellung 'blech_dxf_layer'). Maße in mm, x längs der Biegekanten, y quer (wie die Skizze des Blech-Editors).

elemente(e, zs) baut die Geometrie aus den Eingaben und dem Zuschnitt (blech.zuschnitt), schreiben() macht daraus
den Dateitext, lesen() liest ihn wieder (für die Gegenprobe im Test und zum Prüfen fremder Dateien) und
schnittlaenge() summiert die Länge je Layer.
"""
import math

from . import blech
from . import schneidweg as sw

AUSSEN, INNEN, HOCH, RUNTER, GRAVUR, TEXT = "aussen", "innen", "hoch", "runter", "gravur", "text"
LAYER = (AUSSEN, INNEN, HOCH, RUNTER, GRAVUR, TEXT)
LAYER_VORGABE = "AUSSENKONTUR; INNENKONTUR; BIEGUNG_HOCH; BIEGUNG_RUNTER; GRAVUR; BESCHRIFTUNG"
FARBEN = {AUSSEN: 7, INNEN: 1, HOCH: 3, RUNTER: 5, GRAVUR: 4, TEXT: 8}     # AutoCAD-Farbnummern

_z = sw._z


def layer_namen(text=None):
    """{Layer: Name} aus der Einstellung (sechs Namen mit ; getrennt, leere = Vorgabe)."""
    vorgabe = [n.strip() for n in LAYER_VORGABE.split(";")]
    teile = [n.strip() for n in (text or "").split(";")]
    namen = {}
    for i, art in enumerate(LAYER):
        n = teile[i] if i < len(teile) and teile[i] else vorgabe[i]
        namen[art] = "".join(c if c.isalnum() or c in "_-" else "_" for c in n.upper())[:31] or vorgabe[i]
    return namen


# ------------------------------------------------------------------ Geometrie
def _linie(layer, a, b):
    return ("LINE", layer, (float(a[0]), float(a[1])), (float(b[0]), float(b[1])))


def _bogen(layer, c, r, a0, a1):
    """Bogen gegen den Uhrzeigersinn von a0 bis a1 [Grad]."""
    return ("ARC", layer, (float(c[0]), float(c[1])), float(r), a0 % 360, a1 % 360)


def _kreis(layer, c, r):
    return ("CIRCLE", layer, (float(c[0]), float(c[1])), float(r))


def _rechteck(layer, cx, cy, b, h, r):
    """Rechteck mit Eckradius r um die Mitte (cx, cy)."""
    x0, x1, y0, y1 = cx - b / 2, cx + b / 2, cy - h / 2, cy + h / 2
    r = max(0.0, min(r, b / 2, h / 2))
    out = []
    for a, b_ in (((x0 + r, y0), (x1 - r, y0)), ((x1, y0 + r), (x1, y1 - r)), ((x1 - r, y1), (x0 + r, y1)),
                  ((x0, y1 - r), (x0, y0 + r))):
        if math.dist(a, b_) > 1e-9:
            out.append(_linie(layer, a, b_))
    if r > 1e-9:
        for (mx, my), a0 in (((x1 - r, y0 + r), 270), ((x1 - r, y1 - r), 0), ((x0 + r, y1 - r), 90),
                             ((x0 + r, y0 + r), 180)):
            out.append(_bogen(layer, (mx, my), r, a0, a0 + 90))
    return out


def _polygon(layer, pk):
    return [_linie(layer, pk[i], pk[(i + 1) % len(pk)]) for i in range(len(pk))
            if math.dist(pk[i], pk[(i + 1) % len(pk)]) > 1e-9]


def _polygon_roh(layer, roh, dx=0.0, dy=0.0):
    """Polygon mit Bögen (schneidweg.punkte_roh: x, y, Bulge) als Linien und echte Bögen, um (dx, dy) verschoben."""
    out = []
    for i, (x, y, b) in enumerate(roh):
        q = roh[(i + 1) % len(roh)]
        p0, p1 = (x + dx, y + dy), (q[0] + dx, q[1] + dy)
        if math.dist(p0, p1) <= 1e-9:
            continue
        if not b:
            out.append(_linie(layer, p0, p1))
            continue
        c = math.dist(p0, p1)
        th = 4 * math.atan(b)
        r = c / (2 * math.sin(abs(th) / 2))
        d = r * math.cos(th / 2) * (1 if th > 0 else -1)
        m = ((p0[0] + p1[0]) / 2 - (p1[1] - p0[1]) / c * d, (p0[1] + p1[1]) / 2 + (p1[0] - p0[0]) / c * d)
        a0 = math.degrees(math.atan2(p0[1] - m[1], p0[0] - m[0]))
        a1 = math.degrees(math.atan2(p1[1] - m[1], p1[0] - m[0]))
        out.append(_bogen(layer, m, r, a0, a1) if th > 0 else _bogen(layer, m, r, a1, a0))
    return out


def _linien(layer, z, cx, cy):
    """Linienzüge einer Gravur oder offenen Schnittlinie aus dem DXF-Import (z['linien'], relativ zur Mitte)."""
    out = []
    for zug in z.get("linien") or ():
        pk = [(cx + float(x), cy + float(y)) for x, y in zug]
        out += [_linie(layer, a, b) for a, b in zip(pk, pk[1:], strict=False) if math.dist(a, b) > 1e-9]
    return out


def _gedreht(elemente, cx, cy, w):
    """Linien, Bögen und Kreise um (cx, cy) um w Grad gedreht."""
    def p(q):
        return blech.gedreht([(q[0] - cx, q[1] - cy)], w, cx, cy)[0]
    out = []
    for el in elemente:
        if el[0] == "LINE":
            out.append(_linie(el[1], p(el[2]), p(el[3])))
        elif el[0] == "ARC":
            out.append(_bogen(el[1], p(el[2]), el[3], el[4] + w, el[5] + w))
        elif el[0] == "CIRCLE":
            out.append(_kreis(el[1], p(el[2]), el[3]))
        else:
            out.append(el)
    return out


def kontur_elemente(z, cx, cy, layer=INNEN):
    """Elemente einer Innenkontur mit Mitte (cx, cy); [] bei sonstiger Kontur ohne Form. Mit Drehwinkel gedreht."""
    w = blech.drehung(z)
    if w:
        return _gedreht(kontur_elemente(dict(z, drehung=None), cx, cy, layer), cx, cy, w)
    art = z.get("art")
    if art in (sw.BOHRUNG, sw.SENKUNG):
        d = _z(z.get("d"))
        return [_kreis(layer, (cx, cy), d / 2)] if d > 0 else []
    if art == sw.LANGLOCH:
        lg, b = _z(z.get("l")), _z(z.get("b"))
        if b <= 0 or lg < b:
            return []
        if z.get("quer"):
            return _rechteck(layer, cx, cy, b, lg, b / 2)
        return _rechteck(layer, cx, cy, lg, b, b / 2)
    if art == sw.RECHTECK:
        b, h = _z(z.get("b")), _z(z.get("h"))
        return _rechteck(layer, cx, cy, b, h, _z(z.get("r"))) if b > 0 and h > 0 else []
    if art == sw.POLYGON:
        try:
            pk, roh = sw.punkte(z.get("punkte")), sw.punkte_roh(z.get("punkte"))
        except ValueError:
            return []
        if len(pk) < 3:
            return []
        mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
        return _polygon_roh(layer, roh, cx - mx, cy - my)       # Bögen bleiben Bögen (DXF-Import)
    if art in (sw.GRAVUR, sw.SONSTIGE) and z.get("linien"):
        return _linien(GRAVUR if art == sw.GRAVUR else layer, z, cx, cy)
    if art == sw.TEXT_GRAVUR:           # Einstrich-Schrift, immer auf dem Layer Gravur
        from . import gravur_text
        zuege = gravur_text.gedreht(gravur_text.linien(z.get("text"), _z(z.get("hoehe"))), z.get("winkel"), cx, cy)
        return [_linie(GRAVUR, a, b) for zug in zuege for a, b in zip(zug, zug[1:], strict=False) if math.dist(a, b) > 1e-9]
    return []


def konturen_lage(e, zs):
    """[(Kontur, x, y)] wie in der Skizze: Mitte aus x/y, ohne Angabe gleichmäßig auf der Mittellinie verteilt."""
    konturen = [z for z in e.get("konturen") or [] if z.get("art")]
    frei = [z for z in konturen if z.get("x") is None or z.get("y") is None]
    out = []
    for z in konturen:
        if any(z is f for f in frei):
            k = next(i for i, f in enumerate(frei) if f is z)
            out.append((z, zs["laenge"] * (k + 1) / (len(frei) + 1), zs["breite"] / 2))
        else:
            out.append((z, _z(z["x"]), _z(z["y"])))
    return out


def elemente(e, zs, beschriftung=None, biegelinien=True):
    """(Elemente, Hinweise) der Abwicklung. zs: blech.zuschnitt(e). Hinweise nennen, was die Datei nicht genau
    enthält (Konturen ohne Lage, mehrfache Konturen mit einer Lage, sonstige Konturen ohne Form)."""
    out, hinweise = [], []
    lg, br = zs["laenge"], zs["breite"]
    minx = miny = 0.0
    if zs.get("punkte"):
        minx, miny = min(x for x, _ in zs["punkte"]), min(y for _, y in zs["punkte"])
        try:
            roh = sw.punkte_roh(e.get("punkte")) if e.get("form") == blech.POLYGON else []
        except ValueError:
            roh = []
        if any(b for *_, b in roh):         # mit Bögen (DXF-Import): echte Bögen statt vieler Linien
            out += _polygon_roh(AUSSEN, roh, -minx, -miny)
        else:
            out += _polygon(AUSSEN, [(x - minx, y - miny) for x, y in zs["punkte"]])
    else:
        r = _z(e.get("eckradius")) if e.get("art") != blech.KANTTEIL else 0.0
        out += _rechteck(AUSSEN, lg / 2, br / 2, lg, br, r)
    if biegelinien:
        for lage, winkel, _, _ in zs.get("biegungen") or ():
            out.append(_linie(HOCH if winkel > 0 else RUNTER, (0, lage), (lg, lage)))
        if e.get("art") != blech.KANTTEIL:
            for x in e.get("biegelinien") or ():
                try:
                    (x1, y1), (x2, y2) = x["punkte"]
                except (TypeError, ValueError, KeyError):
                    continue
                out.append(_linie(HOCH if _z(x.get("winkel")) >= 0 else RUNTER, (x1 - minx, y1 - miny),
                                  (x2 - minx, y2 - miny)))
    ohne_lage = mehrfach = ohne_form = 0
    for z, cx, cy in konturen_lage(e, zs):
        if z.get("x") is not None and z.get("y") is not None:      # im System der Außenkontur, wie sie ab 0, 0
            cx, cy = cx - minx, cy - miny
        teile = kontur_elemente(z, cx, cy, GRAVUR if z.get("gravur") else INNEN)
        if not teile:
            ohne_form += 1
            continue
        out += teile
        if z.get("x") is None or z.get("y") is None:
            ohne_lage += 1
        if int(_z(z.get("anzahl")) or 1) > 1:
            mehrfach += 1
    if ohne_lage:
        hinweise.append(f"{ohne_lage} Innenkontur(en) ohne Lage (Mitte x/y): in der Datei nur verteilt eingezeichnet")
    if mehrfach:
        hinweise.append(f"{mehrfach} Innenkontur(en) mit Anzahl > 1 nur einmal eingezeichnet (Lage je Stück fehlt)")
    if ohne_form:
        hinweise.append(f"{ohne_form} sonstige Kontur(en) ohne Form fehlen in der Datei")
    if beschriftung:
        out.append(("TEXT", TEXT, (0.0, -max(5.0, 0.04 * max(lg, br)) - 3.0), max(2.5, 0.02 * max(lg, br)),
                    str(beschriftung)))
    return out, hinweise


# ------------------------------------------------------------------ Schreiben und Lesen
def _zahl(x):
    t = f"{float(x):.6f}".rstrip("0").rstrip(".")
    return "0" if t in ("-0", "") else t


def _text(s):
    """Text für DXF R12 (Codepage ANSI_1252); Zeichen außerhalb als \\U+XXXX."""
    out = []
    for c in str(s).replace("\n", " "):
        try:
            c.encode("cp1252")
            out.append(c)
        except UnicodeEncodeError:
            out.append(f"\\U+{ord(c):04X}")
    return "".join(out)


def schreiben(elem, namen=None):
    """DXF-R12-Text (Zeilenenden CRLF beim Speichern mit speichern())."""
    namen = namen or layer_namen()
    z = []

    def g(code, wert):
        z.append(f"{code:>3}")
        z.append(str(wert))
    xs = [p for el in elem for p in _punkte(el)]
    lo = (min(x for x, _ in xs), min(y for _, y in xs)) if xs else (0.0, 0.0)
    hi = (max(x for x, _ in xs), max(y for _, y in xs)) if xs else (0.0, 0.0)
    g(0, "SECTION"), g(2, "HEADER")
    g(9, "$ACADVER"), g(1, "AC1009")
    g(9, "$DWGCODEPAGE"), g(3, "ANSI_1252")
    g(9, "$INSUNITS"), g(70, 4)
    g(9, "$EXTMIN"), g(10, _zahl(lo[0])), g(20, _zahl(lo[1]))
    g(9, "$EXTMAX"), g(10, _zahl(hi[0])), g(20, _zahl(hi[1]))
    g(0, "ENDSEC")
    g(0, "SECTION"), g(2, "TABLES")
    g(0, "TABLE"), g(2, "LTYPE"), g(70, 1)
    g(0, "LTYPE"), g(2, "CONTINUOUS"), g(70, 0), g(3, "Solid line"), g(72, 65), g(73, 0), g(40, "0.0")
    g(0, "ENDTAB")
    g(0, "TABLE"), g(2, "LAYER"), g(70, len(LAYER) + 1)
    g(0, "LAYER"), g(2, "0"), g(70, 0), g(62, 7), g(6, "CONTINUOUS")
    for art in LAYER:
        g(0, "LAYER"), g(2, namen[art]), g(70, 0), g(62, FARBEN[art]), g(6, "CONTINUOUS")
    g(0, "ENDTAB")
    g(0, "ENDSEC")
    g(0, "SECTION"), g(2, "ENTITIES")
    for el in elem:
        typ, layer = el[0], namen[el[1]]
        g(0, typ), g(8, layer)
        if typ == "LINE":
            g(10, _zahl(el[2][0])), g(20, _zahl(el[2][1])), g(30, 0)
            g(11, _zahl(el[3][0])), g(21, _zahl(el[3][1])), g(31, 0)
        elif typ in ("ARC", "CIRCLE"):
            g(10, _zahl(el[2][0])), g(20, _zahl(el[2][1])), g(30, 0), g(40, _zahl(el[3]))
            if typ == "ARC":
                g(50, _zahl(el[4])), g(51, _zahl(el[5]))
        elif typ == "TEXT":
            g(10, _zahl(el[2][0])), g(20, _zahl(el[2][1])), g(30, 0), g(40, _zahl(el[3])), g(1, _text(el[4]))
    g(0, "ENDSEC")
    g(0, "EOF")
    return "\n".join(z) + "\n"


def speichern(pfad, elem, namen=None):
    with open(pfad, "w", encoding="cp1252", errors="replace", newline="\r\n") as f:
        f.write(schreiben(elem, namen))


def lesen(text):
    """Elemente (LINE, ARC, CIRCLE, TEXT) aus einem DXF-Text; Layer als Name der Datei."""
    zeilen = text.splitlines()
    paare = [(zeilen[i].strip(), zeilen[i + 1].rstrip("\r")) for i in range(0, len(zeilen) - 1, 2)]
    out, i, in_entities = [], 0, False
    while i < len(paare):
        code, wert = paare[i]
        if code == "2" and wert.strip() == "ENTITIES":
            in_entities = True
        elif code == "0" and wert.strip() == "ENDSEC":
            in_entities = False
        if in_entities and code == "0" and wert.strip() in ("LINE", "ARC", "CIRCLE", "TEXT"):
            typ, daten = wert.strip(), {}
            i += 1
            while i < len(paare) and paare[i][0] != "0":
                daten[int(paare[i][0])] = paare[i][1]
                i += 1
            f = lambda c: float(daten.get(c, 0))  # noqa: E731
            layer = daten.get(8, "0").strip()
            if typ == "LINE":
                out.append((typ, layer, (f(10), f(20)), (f(11), f(21))))
            elif typ == "ARC":
                out.append((typ, layer, (f(10), f(20)), f(40), f(50), f(51)))
            elif typ == "CIRCLE":
                out.append((typ, layer, (f(10), f(20)), f(40)))
            else:
                out.append((typ, layer, (f(10), f(20)), f(40), daten.get(1, "")))
            continue
        i += 1
    return out


def _punkte(el):
    if el[0] == "LINE":
        return [el[2], el[3]]
    if el[0] in ("ARC", "CIRCLE"):
        (cx, cy), r = el[2], el[3]
        return [(cx - r, cy - r), (cx + r, cy + r)]
    return [el[2]]


def laenge(el):
    if el[0] == "LINE":
        return math.dist(el[2], el[3])
    if el[0] == "CIRCLE":
        return 2 * math.pi * el[3]
    if el[0] == "ARC":
        return math.radians((el[5] - el[4]) % 360 or 360) * el[3]
    return 0.0


def schnittlaenge(elem):
    """{Layer: Länge [mm]}."""
    out = {}
    for el in elem:
        out[el[1]] = out.get(el[1], 0.0) + laenge(el)
    return out
