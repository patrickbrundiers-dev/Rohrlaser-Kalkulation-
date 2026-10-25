"""DXF-Import im Blech-Editor (Schritt 3E-9, Plan kalkulation/3d-editor/Plan_DXF-Import_Blech.md, Freigabe Patrick
24.10.2026 „Alle a“ + genaue Kontur): eine DXF-Abwicklung wird ein Blech.

- Lesen ohne Zusatzbibliothek: LINE, ARC, CIRCLE, LWPOLYLINE/POLYLINE (mit Bögen), ELLIPSE, SPLINE, TEXT/MTEXT,
  Blöcke (INSERT, auch verschachtelt), Einheit aus $INSUNITS; ausgeblendete/gefrorene Layer und Bemaßung fallen weg.
- Konturen: Elemente zu geschlossenen Zügen verketten (Lücken bis TOL). Größter Zug = Außenkontur, die darin = Innen-
  konturen. Bögen bleiben echte Bögen (Bulge im Polygon, schneidweg.punkte_roh). Bohrung, Langloch, Rechteck nur bei
  exakt dieser Form, sonst die Originalkontur als Polygon.
- Layer: Gravur (GRAV, MARK, ETCH, Layername Gravur aus der Einstellung DXF-Layer) wird graviert, Biegelinien (BIEG,
  BEND, KANT, Layernamen aus der Einstellung) machen ein Kantteil; Texte auf Gravur-Layern = Text-Gravur.
- Werkstoff und Dicke stehen in der DXF meist nicht als Wert: Vorschlag aus Dateiname und Texten der DXF.

Hier nur die Rechnung (ohne Oberfläche); das Fenster ist dxf_import_dialog.DxfImportDialog.
"""
import math
import re

from . import blech, dxf, dxf_ansichten as da, schneidweg as sw

TOL = 0.05              # mm: Lücke, die beim Verketten noch als geschlossen gilt
FORM_TOL = 0.01         # mm: so genau muss eine Kontur Kreis, Langloch oder Rechteck sein
EINHEITEN = {0: 1.0, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 8: 0.0000254, 9: 0.0254, 10: 914.4, 13: 0.001,
             14: 100.0}
GRAVUR_WORTE = ("GRAV", "MARK", "ETCH", "SIGN", "BESCHRIFTUNG_LASER")
BIEGE_WORTE = ("BIEG", "BEND", "KANT", "FOLD")
RUNTER_WORTE = ("RUNTER", "DOWN", "UNTEN", "NEG")
WEG_WORTE = ("BEMA", "DIM", "HILF", "MITTEL", "CENTER", "ACHS", "RAHMEN", "SCHRIFTFELD", "TITLE", "DEFPOINTS",
             "MASSE", "MASS_", "MASSLIN", "MASSHILF", "MASZ", "VERDECK", "HIDDEN", "SCHRAFF", "HATCH", "BORDER",
             "FRAME", "TEXT")      # Maße, verdeckte Kanten, Schraffur, Rahmen, Texte (Patrick 25.10.2026, B3)
SPLITTER = 5.0          # mm: kleinere Teile (Maßpfeile, Splitter) nicht anhaken (Einstellung dxf_splitter)
STRICH_LINIEN = ("CENTER", "DASH", "HIDDEN", "PHANTOM", "STRICH", "DIVIDE", "DOT")


class DxfFehler(ValueError):
    pass


# ------------------------------------------------------------------ Lesen
def _paare(text):
    zeilen = text.splitlines()
    if len(zeilen) < 2:
        raise DxfFehler("Die Datei ist leer oder keine DXF-Datei.")
    out = []
    for i in range(0, len(zeilen) - 1, 2):
        try:
            out.append((int(zeilen[i].strip()), zeilen[i + 1].rstrip("\r")))
        except ValueError:
            raise DxfFehler(f"Keine DXF-Textdatei (Zeile {i + 1}). Binäre DXF bitte als ASCII-DXF speichern.")
    return out


def _entitaeten(paare, i, ende):
    """Ab paare[i] Entitäten [(Typ, [(Code, Wert)])] bis zu einem der Typen in ende; Ergebnis (Liste, i)."""
    out = []
    while i < len(paare):
        code, wert = paare[i]
        if code == 0:
            typ = wert.strip()
            if typ in ende:
                return out, i
            daten = []
            i += 1
            while i < len(paare) and paare[i][0] != 0:
                daten.append(paare[i])
                i += 1
            out.append((typ, daten))
            continue
        i += 1
    return out, i


def _wert(daten, code, vorgabe=None, typ=float):
    for c, w in daten:
        if c == code:
            try:
                return typ(w.strip()) if typ is not str else w.strip()
            except ValueError:
                return vorgabe
    return vorgabe


def _alle(daten, code):
    out = []
    for c, w in daten:
        if c == code:
            try:
                out.append(float(w.strip()))
            except ValueError:
                pass
    return out


def roh_lesen(text):
    """{'einheit': mm je Zeichnungseinheit, 'layer': {Name: dict(aus, linientyp)}, 'bloecke': {Name: (Basis,
    Entitäten)}, 'entitaeten': [(Typ, Daten)]}."""
    paare = _paare(text)
    erg = dict(einheit=1.0, layer={}, bloecke={}, entitaeten=[])
    i = 0
    while i < len(paare):
        code, wert = paare[i]
        if code == 0 and wert.strip() == "SECTION" and i + 1 < len(paare) and paare[i + 1][0] == 2:
            name = paare[i + 1][1].strip()
            i += 2
            if name == "HEADER":
                while i < len(paare) and not (paare[i][0] == 0 and paare[i][1].strip() == "ENDSEC"):
                    if paare[i] == (9, "$INSUNITS") or (paare[i][0] == 9 and paare[i][1].strip() == "$INSUNITS"):
                        try:
                            erg["einheit"] = EINHEITEN.get(int(paare[i + 1][1].strip()), 1.0)
                        except (ValueError, IndexError):
                            pass
                    i += 1
            elif name == "TABLES":
                ents, i = _entitaeten(paare, i, ("ENDSEC",))
                for typ, d in ents:
                    if typ == "LAYER":
                        n = _wert(d, 2, "", str)
                        farbe = _wert(d, 62, 7, int)
                        erg["layer"][n.upper()] = dict(aus=(farbe or 0) < 0 or bool(int(_wert(d, 70, 0, int) or 0) & 1),
                                                       linientyp=(_wert(d, 6, "", str) or "").upper())
            elif name == "BLOCKS":
                while i < len(paare) and not (paare[i][0] == 0 and paare[i][1].strip() == "ENDSEC"):
                    if paare[i][0] == 0 and paare[i][1].strip() == "BLOCK":
                        d = []
                        i += 1
                        while i < len(paare) and paare[i][0] != 0:
                            d.append(paare[i])
                            i += 1
                        ents, i = _entitaeten(paare, i, ("ENDBLK",))
                        erg["bloecke"][_wert(d, 2, "", str)] = ((_wert(d, 10, 0.0), _wert(d, 20, 0.0)), ents)
                        continue
                    i += 1
            elif name == "ENTITIES":
                ents, i = _entitaeten(paare, i, ("ENDSEC",))
                erg["entitaeten"] = ents
            continue
        i += 1
    return erg


# ------------------------------------------------------------------ Elemente in mm, Weltsystem
# Strecke: ("S", layer, p, q, bulge); Kreis: ("K", layer, c, r); Text: ("T", layer, p, hoehe, winkel, text)

class _Trafo:
    """p' = verschub + Drehung(w) · (Maßstab · (p − basis)); setzt sich bei verschachtelten Blöcken zusammen."""

    def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0):
        self.m = (a, b, c, d, e, f)       # x' = a x + b y + e, y' = c x + d y + f

    def __call__(self, p):
        a, b, c, d, e, f = self.m
        return (a * p[0] + b * p[1] + e, c * p[0] + d * p[1] + f)

    def mal(self, o):
        a, b, c, d, e, f = self.m
        a2, b2, c2, d2, e2, f2 = o.m
        return _Trafo(a * a2 + b * c2, a * b2 + b * d2, c * a2 + d * c2, c * b2 + d * d2,
                      a * e2 + b * f2 + e, c * e2 + d * f2 + f)

    @property
    def spiegelt(self):
        a, b, c, d, *_ = self.m
        return a * d - b * c < 0

    @property
    def gleichmaessig(self):
        a, b, c, d, *_ = self.m
        return abs(math.hypot(a, c) - math.hypot(b, d)) < 1e-9 and abs(a * b + c * d) < 1e-9

    @property
    def mass(self):
        a, _, c, *_ = self.m
        return math.hypot(a, c)

    @property
    def winkel(self):
        a, _, c, *_ = self.m
        return math.degrees(math.atan2(c, a))


def _ellipse_punkte(c, achse, verh, t0, t1, n_min=16):
    while t1 <= t0:
        t1 += 2 * math.pi
    ra = math.hypot(*achse)
    n = max(n_min, math.ceil((t1 - t0) / max(2 * math.acos(max(-1.0, 1 - sw.BOGEN_SEHNE / max(ra, 1e-9))),
                                              math.radians(0.5))))
    n = min(n, 2000)
    nx, ny = -achse[1] * verh, achse[0] * verh
    return [(c[0] + math.cos(t0 + (t1 - t0) * k / n) * achse[0] + math.sin(t0 + (t1 - t0) * k / n) * nx,
             c[1] + math.cos(t0 + (t1 - t0) * k / n) * achse[1] + math.sin(t0 + (t1 - t0) * k / n) * ny)
            for k in range(n + 1)]


def _spline_punkte(d):
    grad = int(_wert(d, 71, 3, int) or 3)
    knoten = _alle(d, 40)
    gew = _alle(d, 41)
    xs, ys = _alle(d, 10), _alle(d, 20)
    ctrl = list(zip(xs, ys))
    if len(ctrl) >= grad + 1 and len(knoten) == len(ctrl) + grad + 1:
        if len(gew) != len(ctrl):
            gew = [1.0] * len(ctrl)
        u0, u1 = knoten[grad], knoten[len(ctrl)]
        n = min(4000, max(64, 24 * len(ctrl)))
        out = []
        for k in range(n + 1):
            u = u0 + (u1 - u0) * k / n
            s = grad
            while s < len(ctrl) - 1 and knoten[s + 1] <= u:
                s += 1
            pts = [(ctrl[j][0] * gew[j], ctrl[j][1] * gew[j], gew[j]) for j in range(s - grad, s + 1)]
            for r in range(1, grad + 1):            # de Boor
                for j in range(grad, r - 1, -1):
                    i = j + s - grad
                    nenner = knoten[i + grad - r + 1] - knoten[i]
                    a = (u - knoten[i]) / nenner if nenner else 0.0
                    pts[j] = tuple((1 - a) * pts[j - 1][m] + a * pts[j][m] for m in range(3))
            x, y, w = pts[grad]
            out.append((x / w, y / w) if w else (x, y))
        return out
    fit = list(zip(_alle(d, 11), _alle(d, 21)))
    return fit if len(fit) >= 2 else ctrl


def _ocs(d):
    """Spiegelung durch Extrusion (0, 0, −1): x wird negativ."""
    return (_wert(d, 230, 1.0) or 1.0) < 0


def elemente(roh, trafo=None, tiefe=0, layer_vorgabe="0"):
    """Elemente in mm im Weltsystem (Blöcke aufgelöst)."""
    s = roh["einheit"]
    trafo = trafo or _Trafo(s, 0, 0, s, 0, 0)
    out = []
    ents = roh["entitaeten"] if tiefe == 0 else roh["_block"]
    for typ, d in ents:
        layer = _wert(d, 8, layer_vorgabe, str) or layer_vorgabe
        if layer == "0" and tiefe:
            layer = layer_vorgabe
        info = roh["layer"].get(layer.upper(), {})
        if info.get("aus"):
            continue
        lt = (_wert(d, 6, "", str) or info.get("linientyp") or "").upper()
        if typ == "INSERT":
            if tiefe > 8:
                continue
            blk = roh["bloecke"].get(_wert(d, 2, "", str))
            if not blk:
                continue
            (bx, by), bents = blk
            sx, sy = _wert(d, 41, 1.0) or 1.0, _wert(d, 42, 1.0) or 1.0
            w = math.radians(_wert(d, 50, 0.0) or 0.0)
            px, py = _wert(d, 10, 0.0), _wert(d, 20, 0.0)
            if _ocs(d):
                px, w, sx = -px, math.pi - w, -sx
            cw, sn = math.cos(w), math.sin(w)
            t = _Trafo(cw * sx, -sn * sy, sn * sx, cw * sy, px - (cw * sx * bx - sn * sy * by),
                       py - (sn * sx * bx + cw * sy * by))
            unter = dict(roh, _block=bents)
            out += elemente(unter, trafo.mal(t), tiefe + 1, layer)
            continue
        strich = any(w_ in lt for w_ in STRICH_LINIEN)
        out += [(*el, strich) for el in _element(typ, d, layer, trafo)]
    return out


def _strecken(pk, layer, trafo, geschlossen=False, bulges=None):
    """Polylinie (Punkte im Objektsystem) -> Strecken im Weltsystem; Bögen bleiben, wenn die Abbildung sie erhält."""
    out = []
    n = len(pk)
    bulges = bulges or [0.0] * n
    spiegel = trafo.spiegelt
    for i in range(n if geschlossen else n - 1):
        p, q, b = pk[i], pk[(i + 1) % n], bulges[i]
        if b and not trafo.gleichmaessig:
            zug = [p] + sw.bogen_punkte(p, q, b)
            out += [("S", layer, trafo(a), trafo(c), 0.0) for a, c in zip(zug, zug[1:])]
        else:
            out.append(("S", layer, trafo(p), trafo(q), -b if spiegel else b))
    return out


def _element(typ, d, layer, trafo):
    m = -1.0 if _ocs(d) else 1.0
    if typ == "LINE":
        return [("S", layer, trafo((m * _wert(d, 10, 0.0), _wert(d, 20, 0.0))),
                 trafo((m * _wert(d, 11, 0.0), _wert(d, 21, 0.0))), 0.0)]
    if typ in ("CIRCLE", "ARC"):
        c, r = (_wert(d, 10, 0.0), _wert(d, 20, 0.0)), _wert(d, 40, 0.0)
        if r <= 0:
            return []
        if typ == "CIRCLE" or abs(((_wert(d, 51, 360.0) - _wert(d, 50, 0.0)) % 360)) < 1e-9:
            if trafo.gleichmaessig:
                cc = trafo((m * c[0], c[1]))
                return [("K", layer, cc, r * trafo.mass)]
            zug = _ellipse_punkte((m * c[0], c[1]), (r, 0.0), 1.0, 0.0, 2 * math.pi)
            return _strecken(zug[:-1], layer, trafo, geschlossen=True)
        a0, a1 = math.radians(_wert(d, 50, 0.0)), math.radians(_wert(d, 51, 0.0))
        auf = (a1 - a0) % (2 * math.pi)
        p = (c[0] + r * math.cos(a0), c[1] + r * math.sin(a0))
        q = (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1))
        b = math.tan(auf / 4)
        if m < 0:
            p, q, b = (-p[0], p[1]), (-q[0], q[1]), -b
        return _strecken([p, q], layer, trafo, bulges=[b, 0.0])
    if typ == "LWPOLYLINE":
        pk, bulges = [], []
        for c, w in d:                       # 10/20 je Punkt, 42 gehört zum letzten Punkt
            try:
                if c == 10:
                    pk.append([float(w), 0.0])
                    bulges.append(0.0)
                elif c == 20 and pk:
                    pk[-1][1] = float(w)
                elif c == 42 and bulges:
                    bulges[-1] = float(w)
            except ValueError:
                continue
        pk = [(m * x, y) for x, y in pk]
        if m < 0:
            bulges = [-b for b in bulges]
        zu = bool(int(_wert(d, 70, 0, int) or 0) & 1)
        return _strecken(pk, layer, trafo, geschlossen=zu, bulges=bulges) if len(pk) >= 2 else []
    if typ == "_POLYLINE":
        pk, bulges, zu = d.poly
        pk = [(m * x, y) for x, y in pk]
        if m < 0:
            bulges = [-b for b in bulges]
        return _strecken(pk, layer, trafo, geschlossen=zu, bulges=bulges) if len(pk) >= 2 else []
    if typ == "ELLIPSE":
        c = (_wert(d, 10, 0.0), _wert(d, 20, 0.0))
        achse = (_wert(d, 11, 0.0), _wert(d, 21, 0.0))
        zug = _ellipse_punkte(c, achse, _wert(d, 40, 1.0), _wert(d, 41, 0.0), _wert(d, 42, 2 * math.pi))
        zug = [(m * x, y) for x, y in zug]
        return _strecken(zug, layer, trafo)
    if typ == "SPLINE":
        zug = [(m * x, y) for x, y in _spline_punkte(d)]
        zu = bool(int(_wert(d, 70, 0, int) or 0) & 1)
        return _strecken(zug, layer, trafo, geschlossen=zu and math.dist(zug[0], zug[-1]) > TOL) if len(zug) >= 2 \
            else []
    if typ in ("TEXT", "MTEXT"):
        text = _wert(d, 1, "", str) or ""
        if typ == "MTEXT":
            text = (text + "".join(w for c, w in d if c == 3)).replace("\\P", " ")
            text = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", text)
        h = (_wert(d, 40, 0.0) or 0.0) * trafo.mass
        w = (_wert(d, 50, 0.0) or 0.0) + trafo.winkel
        if typ == "MTEXT" and _wert(d, 11) is not None:
            w = math.degrees(math.atan2(_wert(d, 21, 0.0), _wert(d, 11, 1.0))) + trafo.winkel
        p = trafo((m * _wert(d, 10, 0.0), _wert(d, 20, 0.0)))
        if typ == "MTEXT":           # Einfügepunkt oben links: auf die Grundlinie der ersten Zeile
            p = (p[0] + h * math.sin(math.radians(w)), p[1] - h * math.cos(math.radians(w)))
        return [("T", layer, p, h, w, text.strip())] if text.strip() else []
    return []


def _polylinien_zusammen(ents):
    """Alte POLYLINE mit VERTEX … SEQEND zu einer Entität ('_POLYLINE', Daten) zusammenfassen."""
    out, i = [], 0
    while i < len(ents):
        typ, d = ents[i]
        if typ == "POLYLINE":
            flags = int(_wert(d, 70, 0, int) or 0)
            pk, bulges = [], []
            i += 1
            while i < len(ents) and ents[i][0] == "VERTEX":
                vd = ents[i][1]
                pk.append((_wert(vd, 10, 0.0), _wert(vd, 20, 0.0)))
                bulges.append(_wert(vd, 42, 0.0) or 0.0)
                i += 1
            if i < len(ents) and ents[i][0] == "SEQEND":
                i += 1
            if not flags & (16 | 64):        # keine Netze
                kopf = [x for x in d if x[0] in (8, 6, 230)]
                out.append(("_POLYLINE", _PolyDaten(kopf, (pk, bulges, bool(flags & 1)))))
            continue
        out.append((typ, d))
        i += 1
    return out


class _PolyDaten(list):
    """Daten einer zusammengefassten POLYLINE: Liste (Layer usw.) und .poly = (Punkte, Bulges, geschlossen)."""

    def __init__(self, kopf, poly):
        super().__init__(kopf)
        self.poly = poly


# ------------------------------------------------------------------ Verketten
def _rund(p):
    return (round(p[0] / TOL), round(p[1] / TOL))


def _bulge_flaeche(p, q, b):
    """Fläche des Kreisabschnitts zwischen Sehne p-q und Bogen (Vorzeichen wie der Bulge)."""
    if not b:
        return 0.0
    c = math.dist(p, q)
    th = 4 * math.atan(abs(b))
    r = c / (2 * math.sin(th / 2)) if c else 0.0
    return math.copysign(r * r / 2 * (th - math.sin(th)), b)


class Zug:
    """Geschlossener oder offener Linienzug: punkte [(x, y)], bulges [b je Punkt zum nächsten]."""

    def __init__(self, layer, punkte, bulges, geschlossen):
        self.layer, self.punkte, self.bulges, self.geschlossen = layer, punkte, bulges, geschlossen

    @property
    def flaeche(self):
        """Fläche mit Vorzeichen (+ = gegen den Uhrzeiger)."""
        pk, n = self.punkte, len(self.punkte)
        a = sum(pk[i][0] * pk[(i + 1) % n][1] - pk[(i + 1) % n][0] * pk[i][1] for i in range(n)) / 2
        return a + sum(_bulge_flaeche(pk[i], pk[(i + 1) % n], self.bulges[i]) for i in range(n))

    def dicht(self):
        out = []
        n = len(self.punkte)
        for i in range(n if self.geschlossen else n - 1):
            p, q = self.punkte[i], self.punkte[(i + 1) % n]
            if not out:
                out.append(p)
            out += sw.bogen_punkte(p, q, self.bulges[i])
        if self.geschlossen and len(out) > 1 and math.dist(out[0], out[-1]) < 1e-9:
            out.pop()
        return out

    def laenge(self):
        d = self.dicht()
        return sum(math.dist(a, b) for a, b in zip(d, d[1:] + (d[:1] if self.geschlossen else [])))

    def umgedreht(self):
        n = len(self.punkte)
        if self.geschlossen:
            pk = [self.punkte[0]] + self.punkte[:0:-1]
            bg = [-self.bulges[-1]] + [-self.bulges[i] for i in range(n - 2, -1, -1)]
            return Zug(self.layer, pk, bg, True)
        return Zug(self.layer, self.punkte[::-1], [-b for b in self.bulges[-2::-1]] + [0.0], False)


def verketten(strecken):
    """Strecken [(p, q, b, layer)] zu Zügen; Ergebnis [Zug] (geschlossene und offene)."""
    offen = list(range(len(strecken)))
    an = {}
    for i, (p, q, *_r) in enumerate(strecken):
        for k in (p, q):
            an.setdefault(_rund(k), []).append(i)
    benutzt = [False] * len(strecken)

    def nachbar(pt):
        kx, ky = _rund(pt)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in an.get((kx + dx, ky + dy), ()):
                    if benutzt[j]:
                        continue
                    p, q = strecken[j][0], strecken[j][1]
                    for ende, d in ((0, math.dist(pt, p)), (1, math.dist(pt, q))):
                        if d <= TOL and (best is None or d < best[0]):
                            best = (d, j, ende)
        return best

    zuege = []
    for start in offen:
        if benutzt[start]:
            continue
        benutzt[start] = True
        p, q, b, layer = strecken[start]
        pk, bg = [p, q], [b]
        for richtung in (1, 0):               # erst vorwärts, dann am Anfang rückwärts verlängern
            while True:
                ende = pk[-1] if richtung else pk[0]
                if len(pk) > 2 and math.dist(pk[0], pk[-1]) <= TOL:
                    break
                n = nachbar(ende)
                if n is None:
                    break
                _, j, e = n
                benutzt[j] = True
                p2, q2, b2, _l = strecken[j]
                if richtung:
                    if e == 0:
                        pk.append(q2)
                        bg.append(b2)
                    else:
                        pk.append(p2)
                        bg.append(-b2)
                else:
                    if e == 1:
                        pk.insert(0, p2)
                        bg.insert(0, b2)
                    else:
                        pk.insert(0, q2)
                        bg.insert(0, -b2)
            if len(pk) > 2 and math.dist(pk[0], pk[-1]) <= TOL:
                break
        if len(pk) > 2 and math.dist(pk[0], pk[-1]) <= TOL:
            zuege.append(Zug(layer, pk[:-1], bg, True))
        elif len(pk) == 2 and abs(b) > 1e-9 and math.dist(p, q) < TOL:
            continue
        else:
            zuege.append(Zug(layer, pk, bg + [0.0], False))
    return zuege


# ------------------------------------------------------------------ Formen erkennen
def _kreis_aus(z):
    """Zug aus zwei Halbkreisen o. ä. (alle Bögen, gleicher Mittelpunkt und Radius): (Mitte, r) oder None."""
    if not all(abs(b) > 1e-9 for b in z.bulges):
        return None
    pk = z.dicht()
    mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
    rs = [math.dist((mx, my), p) for p in pk]
    if max(rs) - min(rs) <= FORM_TOL and abs(abs(z.flaeche) - math.pi * (sum(rs) / len(rs)) ** 2) < \
            max(0.5, 0.002 * abs(z.flaeche)):
        return (mx, my), sum(rs) / len(rs)
    return None


def _bogen_mitte(p, q, b):
    """(Mittelpunkt, Radius) des Bogens p->q mit Bulge b."""
    c = math.dist(p, q)
    th = 4 * math.atan(b)
    r = c / (2 * math.sin(abs(th) / 2))
    d = r * math.cos(th / 2) * (1 if th > 0 else -1)
    return ((p[0] + q[0]) / 2 - (q[1] - p[1]) / c * d, (p[1] + q[1]) / 2 + (q[0] - p[0]) / c * d), r


def _ohne_flucht(z):
    """Punkte ohne Zwischenpunkte auf geraden Strecken (gleiche Richtung, kein Bogen), Strecken der Länge 0 weg und
    aufeinanderfolgende Bögen um denselben Mittelpunkt zu einem Bogen zusammengefasst."""
    pk, bg = list(z.punkte), list(z.bulges)
    i = 0
    while len(pk) > 2 and i < len(pk):                          # Länge 0 (z. B. Langloch als Rechteck mit r = b/2)
        if math.dist(pk[i], pk[(i + 1) % len(pk)]) <= 1e-6 and not bg[i]:
            del pk[i]                                           # Punkt i = Punkt i+1: Bogen davor bleibt
            del bg[i]
            continue
        i += 1
    i = 0
    while len(pk) > 2 and i < len(pk):                          # Bögen zusammenfassen
        j = (i + 1) % len(pk)
        if bg[i] and bg[j] and bg[i] * bg[j] > 0:
            c1, r1 = _bogen_mitte(pk[i], pk[j], bg[i])
            c2, r2 = _bogen_mitte(pk[j], pk[(j + 1) % len(pk)], bg[j])
            th = 4 * math.atan(bg[i]) + 4 * math.atan(bg[j])
            if math.dist(c1, c2) <= FORM_TOL and abs(r1 - r2) <= FORM_TOL and abs(th) < 2 * math.pi - 1e-6:
                bg[i] = math.tan(th / 4)
                del pk[j]
                del bg[j]
                if j < i:
                    i -= 1
                continue
        i += 1
    i = 0
    while len(pk) > 3 and i < len(pk):
        a, b, c = pk[i - 1], pk[i], pk[(i + 1) % len(pk)]
        if not bg[i - 1] and not bg[i]:
            kreuz = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if abs(kreuz) <= FORM_TOL * max(math.dist(a, c), 1e-9) and \
                    (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) > 0:
                del pk[i]
                del bg[i]
                continue
        i += 1
    return Zug(z.layer, pk, bg, z.geschlossen)


def _winkel(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _norm_dreh(w):
    """Drehwinkel auf (−90, 90] (Langloch, Rechteck sind symmetrisch)."""
    w = (w + 90) % 180 - 90
    return 90.0 if abs(w + 90) < 1e-6 else (0.0 if abs(w) < 1e-6 else round(w, 4))


def _rechteck_dreh(f):
    """Rechteck mit 90° als Breite/Höhe getauscht, 0° ohne Drehwinkel."""
    if f.get("drehung") == 90:
        f["b"], f["h"] = f["h"], f["b"]
    if f.get("drehung") in (0, 90):
        f.pop("drehung")
    return f


def _form_aus(z):
    """Innenkontur als dict (Art und Maße, Mitte cx/cy) bei exakter Normform, sonst None."""
    k = _kreis_aus(z)
    if k:
        return dict(art=sw.BOHRUNG, d=round(2 * k[1], 4), cx=k[0][0], cy=k[0][1])
    z = _ohne_flucht(z)
    pk, bg, n = z.punkte, z.bulges, len(z.punkte)
    if n == 4 and all(not b for b in bg):                       # Rechteck ohne Radien
        seiten = [math.dist(pk[i], pk[(i + 1) % 4]) for i in range(4)]
        diag = math.dist(pk[0], pk[2]), math.dist(pk[1], pk[3])
        if abs(seiten[0] - seiten[2]) <= FORM_TOL and abs(seiten[1] - seiten[3]) <= FORM_TOL and \
                abs(diag[0] - diag[1]) <= FORM_TOL:
            return _rechteck_dreh(dict(art=sw.RECHTECK, b=round(seiten[0], 4), h=round(seiten[1], 4), r=0,
                                       drehung=_norm_dreh(_winkel(pk[0], pk[1])),
                                       cx=sum(x for x, _ in pk) / 4, cy=sum(y for _, y in pk) / 4))
    halb = math.tan(math.pi / 4)                                # Bulge eines Halbkreises = 1
    if n == 4 and sum(1 for b in bg if abs(abs(b) - halb) < 1e-4) == 2 and sum(1 for b in bg if not b) == 2:
        i = next(i for i, b in enumerate(bg) if not b)          # Langloch: Gerade, Halbkreis, Gerade, Halbkreis
        if bg[(i + 2) % 4] == 0 and abs(bg[(i + 1) % 4]) > 0:
            a, b_, c, d = pk[i], pk[(i + 1) % 4], pk[(i + 2) % 4], pk[(i + 3) % 4]
            r1, r2 = math.dist(b_, c) / 2, math.dist(d, a) / 2
            l1, l2 = math.dist(a, b_), math.dist(c, d)
            if abs(r1 - r2) <= FORM_TOL and abs(l1 - l2) <= FORM_TOL and bg[(i + 1) % 4] * bg[(i + 3) % 4] > 0:
                w = _norm_dreh(_winkel(a, b_))
                out = dict(art=sw.LANGLOCH, l=round(l1 + 2 * r1, 4), b=round(2 * r1, 4),
                           cx=sum(x for x, _ in pk) / 4, cy=sum(y for _, y in pk) / 4)
                if w == 90:
                    out["quer"] = True
                elif w:
                    out["drehung"] = w
                return out
    viertel = math.tan(math.pi / 8)
    if n == 8:                                                  # Rechteck mit vier gleichen Eckradien
        for s in (0, 1):
            if all(not bg[(s + 2 * j) % 8] for j in range(4)) and \
                    all(abs(abs(bg[(s + 2 * j + 1) % 8]) - viertel) < 1e-4 for j in range(4)):
                kanten = [math.dist(pk[(s + 2 * j) % 8], pk[(s + 2 * j + 1) % 8]) for j in range(4)]
                radien = [math.dist(pk[(s + 2 * j + 1) % 8], pk[(s + 2 * j + 2) % 8]) / math.sqrt(2) for j in range(4)]
                if max(radien) - min(radien) <= FORM_TOL and abs(kanten[0] - kanten[2]) <= FORM_TOL and \
                        abs(kanten[1] - kanten[3]) <= FORM_TOL:
                    r = sum(radien) / 4
                    return _rechteck_dreh(dict(
                        art=sw.RECHTECK, b=round(kanten[0] + 2 * r, 4), h=round(kanten[1] + 2 * r, 4), r=round(r, 4),
                        drehung=_norm_dreh(_winkel(pk[s], pk[(s + 1) % 8])),
                        cx=sum(p[0] for p in pk) / 8, cy=sum(p[1] for p in pk) / 8))
    return None


def _zahl(v, stellen=4):
    v = round(v, stellen)
    if v == 0:
        v = 0.0
    return f"{v:.{stellen}f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def punkte_text(pk, bulges, dx=0.0, dy=0.0):
    """Eckpunkte mit Bulge als Text für das Feld Eckpunkte (schneidweg.punkte_roh)."""
    return "; ".join(f"{_zahl(x - dx)},{_zahl(y - dy)}" + (f",{_zahl(b, 6)}" if abs(b) > 1e-9 else "")
                     for (x, y), b in zip(pk, bulges))


def _polygon_kontur(z):
    """Freie Innenkontur: Eckpunkte relativ, Mitte x/y so, dass der Editor sie wieder an dieselbe Stelle setzt (er
    mittelt die Punkte aus schneidweg.punkte)."""
    z = _ohne_flucht(z)
    xs = [x for x, _ in z.punkte]
    ys = [y for _, y in z.punkte]
    ox, oy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    text = punkte_text(z.punkte, z.bulges, ox, oy)
    pk = sw.punkte(text)
    mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
    return dict(art=sw.POLYGON, punkte=text, cx=ox + mx, cy=oy + my)


# ------------------------------------------------------------------ Layer
def _hat(name, worte):
    n = (name or "").upper()
    return any(w in n for w in worte)


def weg_worte(text):
    """Weitere Layernamen bzw. Wortteile aus der Einstellung dxf_weg_layer (mit ; oder , getrennt)."""
    return tuple(w.strip().upper() for w in str(text or "").replace(",", ";").split(";") if w.strip())


def layer_art(name, namen=None, weg=()):
    """'gravur', 'biegung', 'runter' (Biegung nach unten), 'text', 'weg' oder 'schnitt'. weg: weitere Wortteile von
    Layern, die nicht geschnitten werden (Einstellung dxf_weg_layer)."""
    namen = namen or dxf.layer_namen()
    n = (name or "").upper()                   # „Maße“ -> „MASSE“
    if n == namen[dxf.GRAVUR] or _hat(n, GRAVUR_WORTE):
        return "gravur"
    if n == namen[dxf.RUNTER] or (_hat(n, BIEGE_WORTE) and _hat(n, RUNTER_WORTE)):
        return "runter"
    if n == namen[dxf.HOCH] or _hat(n, BIEGE_WORTE):
        return "biegung"
    if n == namen[dxf.TEXT]:
        return "text"
    if _hat(n, WEG_WORTE) or _hat(n, weg):
        return "weg"
    return "schnitt"


# ------------------------------------------------------------------ Werkstoff und Dicke
ERSATZ = {"V2A": "1.4301", "V4A": "1.4571", "ST37": "S235", "ST52": "S355", "EDELSTAHL": "1.4301",
          "ALU": "ALMG3", "VERZINKT": "DX51D"}


def dicke_aus(texte):
    """Blechdicke [mm] aus Texten wie 't=3', 'S=2,5', 'Dicke 4 mm', 'Blech 3mm', '_3mm' oder None."""
    muster = (r"(?<![A-Za-z])(?:[ts]\s*[=:]|(?:dicke|st[äa]rke|blechst[äa]rke|thickness)\s*[=:]?)\s*(\d+(?:[.,]\d+)?)"
              r"\s*(?:mm)?(?![A-Za-z\d])",
              r"(?:^|[^\d.,x×])(\d+(?:[.,]\d+)?)\s*mm(?![A-Za-z])")
    for m_ in muster:
        for t in texte:
            for treffer in re.finditer(m_, str(t or ""), re.IGNORECASE):
                try:
                    v = float(treffer.group(1).replace(",", "."))
                except ValueError:
                    continue
                if 0.3 <= v <= 50:
                    return v
    return None


def werkstoff_aus(texte, werkstoffe):
    """Werkstoff-ID aus Texten (Dateiname, DXF-Texte): längster passender Name (S235JR auch für 'S235', 1.4301 2B
    für '1.4301', V2A = 1.4301 …) oder None. werkstoffe: {ID: Zeile} der Tabelle blech_werkstoffe."""
    alle = " ".join(str(t or "") for t in texte).upper().replace("_", " ")
    for alt, neu in ERSATZ.items():
        if re.search(rf"(?<![A-Z0-9]){alt}(?![A-Z0-9])", alle):
            alle += " " + neu
    best = None
    for wid in werkstoffe:
        kandidaten = {wid.upper(), wid.upper().split()[0]}
        kandidaten.add(re.sub(r"(JR|J0|J2|MC|\+.*)$", "", wid.upper().split()[0]))
        for k in kandidaten:
            if len(k) >= 3 and re.search(rf"(?<![A-Z0-9.]){re.escape(k)}(?![0-9])", alle):
                if best is None or len(k) > best[0] or (len(k) == best[0] and len(wid) < len(best[1])):
                    best = (len(k), wid)
    return best[1] if best else None


# ------------------------------------------------------------------ Maßstab
MASSSTAEBE = (1, 2, 2.5, 4, 5, 10, 20, 0.5, 0.2, 0.1)


def massstab_vorschlag(roh, texte):
    """(Faktor Zeichnung -> echt, Quelle) aus Bemaßungen (gemessener Wert ÷ gezeichnete Länge) oder aus dem
    Schriftfeld ('M 1:2', 'Maßstab 1:5'); (1, None) ohne Hinweis."""
    werte = []
    for typ, d in roh["entitaeten"]:
        if typ != "DIMENSION" or (int(_wert(d, 70, 0, int) or 0) & 7) not in (0, 1):
            continue
        p1, p2, mess = (_wert(d, 13), _wert(d, 23)), (_wert(d, 14), _wert(d, 24)), _wert(d, 42)
        if None in p1 + p2 or not mess:
            continue
        w = math.radians(_wert(d, 50, 0.0) or 0.0)
        lg = (abs((p2[0] - p1[0]) * math.cos(w) + (p2[1] - p1[1]) * math.sin(w))
              if int(_wert(d, 70, 0, int) or 0) & 7 == 0 else math.dist(p1, p2)) * roh["einheit"]
        if lg > 1e-6:
            werte.append(mess * roh["einheit"] / lg)
    if werte:
        werte.sort()
        f = werte[len(werte) // 2]
        best = min(MASSSTAEBE, key=lambda m: abs(m - f) / m)
        if abs(best - f) / best < 0.01:
            return (best, "Bemaßung") if best != 1 else (1, None)
    for t in texte:
        m = re.search(r"(?:\bM|ma(?:ß|ss)stab|scale)\s*[:.=]?\s*(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)",
                      str(t), re.IGNORECASE)
        if m:
            a, b = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
            if a > 0 and b > 0 and abs(a / b - 1) > 1e-9:
                return b / a, "Schriftfeld"
    return 1, None


# ------------------------------------------------------------------ Teile finden
def _bbox(pk):
    xs, ys = [x for x, _ in pk], [y for _, y in pk]
    return min(xs), min(ys), max(xs), max(ys)


def _in_bbox(p, bb, tol=0.0):
    return bb[0] - tol <= p[0] <= bb[2] + tol and bb[1] - tol <= p[1] <= bb[3] + tol


class _Kontur:
    """Geschlossener Zug mit dichtem Polygon, Fläche, Hüllrechteck, Eltern/Kindern (Enthaltensein)."""

    def __init__(self, zug):
        self.zug, self.dicht = zug, zug.dicht()
        self.flaeche = abs(zug.flaeche)
        self.bb = _bbox(self.dicht)
        self.eltern, self.kinder = None, []

    def enthaelt(self, p):
        return _in_bbox(p, self.bb) and blech._innen(p, self.dicht)

    @property
    def rechteck(self):
        z = _ohne_flucht(self.zug)
        return len(z.punkte) == 4 and not any(z.bulges) and all(
            abs(a[0] - b[0]) <= FORM_TOL or abs(a[1] - b[1]) <= FORM_TOL
            for a, b in zip(z.punkte, z.punkte[1:] + z.punkte[:1]))


def _baum(konturen):
    """Eltern = kleinste Kontur, die den ersten Punkt enthält."""
    nach_groesse = sorted(konturen, key=lambda k: k.flaeche)
    for i, k in enumerate(nach_groesse):
        p = k.dicht[0]
        k.eltern = next((o for o in nach_groesse[i + 1:] if o.flaeche > k.flaeche and o.enthaelt(p)), None)
        k.kinder = []
    for k in konturen:
        if k.eltern is not None:
            k.eltern.kinder.append(k)


def _teile(konturen, texte, offene):
    """[(Außenkontur, [Innenkonturen], Grund oder None)] ohne Rahmen; Grund = warum es kein Blech sein dürfte."""
    _baum(konturen)
    rahmen = set()
    for k in sorted(konturen, key=lambda k: -k.flaeche):     # Rahmen von außen nach innen
        if k.eltern is not None and k.eltern not in rahmen:
            continue
        n_text = sum(1 for t in texte if k.enthaelt(t))
        offen_lg = sum(z.laenge() for z in offene if k.enthaelt(z.dicht()[0]))
        umfang = 2 * (k.bb[2] - k.bb[0] + k.bb[3] - k.bb[1])
        if any(c.kinder for c in k.kinder) or (k.rechteck and k.kinder and (n_text >= 3 or offen_lg > 0.3 * umfang)):
            rahmen.add(k)
    out = []
    for k in konturen:
        if k in rahmen:
            continue
        tiefe, e = 0, k.eltern
        while e is not None:
            if e not in rahmen:
                tiefe += 1
            e = e.eltern
        if tiefe % 2:
            continue                                        # Innenkontur
        grund = None
        if not k.kinder and k.rechteck and any(k.enthaelt(t) for t in texte):
            grund = "Kästchen mit Text (Schriftfeld?)"
        elif max(k.bb[2] - k.bb[0], k.bb[3] - k.bb[1]) < 1:
            grund = "kleiner als 1 mm"
        out.append((k, list(k.kinder), grund))
    return sorted(out, key=lambda t: (t[2] is not None, -t[0].bb[3], t[0].bb[0])), len(rahmen)


# ------------------------------------------------------------------ Gesamt
def importieren(text, dateiname="", namen=None, massstab=None, weg=(), splitter=SPLITTER):
    """DXF-Text -> dict(teile [dict(e, name, zusammenfassung, warnungen, biegelinien, aktiv, grund)], texte (alle
    Texte), warnungen, dicke (Vorschlag), dicke_quelle, massstab, massstab_quelle, rahmen (Anzahl), rohr (dict aus
    dxf_ansichten.rohr_erkennen oder None)). massstab None: Vorschlag aus Bemaßung bzw. Schriftfeld. weg: weitere
    Layer, die nicht geschnitten werden; splitter: kleinere Teile [mm] nicht anhaken.
    Ansichten (dxf_ansichten): Teile in einer Isometrie oder Seitenansicht und Teile einer Rohrzeichnung sind nicht
    angehakt (mit Grund), die Dicke kommt sonst aus der Seitenansicht."""
    roh = roh_lesen(text)
    roh["entitaeten"] = _polylinien_zusammen(roh["entitaeten"])
    roh["bloecke"] = {n: (b, _polylinien_zusammen(ents)) for n, (b, ents) in roh["bloecke"].items()}
    namen = namen or dxf.layer_namen()
    texte0 = [el[5] for el in elemente(roh) if el[0] == "T"]
    quelle = None
    if massstab is None:
        massstab, quelle = massstab_vorschlag(roh, texte0)
    f = roh["einheit"] * massstab
    els = elemente(roh, _Trafo(f, 0, 0, f, 0, 0))
    warn = []
    texte = [el for el in els if el[0] == "T"]
    schnitt, gravur, biegung, kreise, gravtexte = [], [], [], [], []
    for el in els:
        art = layer_art(el[1], namen, weg)
        if art == "weg":
            continue
        if el[0] == "T":
            if art == "gravur":
                gravtexte.append(el)
            continue
        if art in ("biegung", "runter"):
            if el[0] == "S":
                biegung.append((el[2], el[3], art))
            continue
        if art == "text":
            continue
        if el[-1] and art == "schnitt":          # Strich-Punkt-Linien (Mittellinien, Hilfslinien)
            continue
        if el[0] == "K":
            (kreise if art == "schnitt" else gravur).append(("K", el[2], el[3]))
        elif math.dist(el[2], el[3]) > 1e-9:
            (schnitt if art == "schnitt" else gravur).append((el[2], el[3], el[4], el[1]))
    schnitt = _ohne_doppelte(schnitt)
    zuege = verketten(schnitt)
    offen = [z for z in zuege if not z.geschlossen and z.laenge() > TOL]
    # geschlossene Züge ohne Fläche (Linie hin und zurück, z. B. aus Ansichten anderer CAD-Programme) fallen weg
    konturen = [_Kontur(z) for z in zuege if z.geschlossen and abs(z.flaeche) > 1e-6] + \
        [_Kontur(Zug("K", [(c[0] + r, c[1]), (c[0] - r, c[1])], [1.0, 1.0], True)) for _, c, r in kreise]
    if not konturen:
        raise DxfFehler("In der DXF wurde keine geschlossene Außenkontur gefunden.")
    text_punkte = [t[2] for t in texte if layer_art(t[1], namen, weg) != "gravur"]
    gefunden, n_rahmen = _teile(konturen, text_punkte, offen)
    ansichten, rohr = _ansichten(schnitt, kreise, gefunden)
    stamm = re.sub(r"\.dxf$", "", str(dateiname or "").replace("\\", "/").split("/")[-1], flags=re.IGNORECASE)
    teile = []
    for nr, (k, innen, grund) in enumerate(gefunden, 1):
        def drin(p, k=k):
            return k.enthaelt(p) and not any(c.enthaelt(p) for c in innen)
        t = _teil(k.zug, [c.zug for c in innen], [z for z in offen if drin(z.dicht()[0])],
                  [g for g in gravur if drin(g[1] if g[0] == "K" else g[0])],
                  [g for g in gravtexte if drin(g[2])], [b for b in biegung if k.enthaelt(b[0]) or k.enthaelt(b[1])
                                                          or k.enthaelt(((b[0][0] + b[1][0]) / 2,
                                                                         (b[0][1] + b[1][1]) / 2))])
        beschr = [x[5] for x in texte if layer_art(x[1], namen, weg) != "gravur" and k.enthaelt(x[2])]
        grund = grund or _grund(k, ansichten, rohr, t, splitter)
        t.update(name=(beschr[0] if len(beschr) == 1 and len(beschr[0]) <= 40 else
                       (stamm or "DXF") + (f" Teil {nr}" if len(gefunden) > 1 else "")),
                 aktiv=grund is None, grund=grund)
        t["e"]["dxf"] = dateiname or True
        teile.append(t)
    rest = sum(1 for z in offen if not any(k.enthaelt(z.dicht()[0]) for k, *_ in gefunden))
    if n_rahmen:
        warn.append(f"Zeichnungsrahmen erkannt ({n_rahmen}×): nicht übernommen.")
    if rest:
        warn.append(f"{rest} offene Linie{'n' if rest > 1 else ''} außerhalb der Teile (Schriftfeld, Hilfslinien) "
                    "nicht übernommen.")
    if rohr:
        warn.insert(0, f"Die Zeichnung zeigt ein Rohr ({rohr['text']}), kein Blech: als Blech wird nichts "
                       "übernommen. Den Import von Rohrzeichnungen bringt Schritt 3E-12.")
    n_iso = sum(1 for a in ansichten if a.iso)
    if n_iso and not rohr:
        warn.append(f"Isometrische Ansicht erkannt ({n_iso}×): ihre Konturen sind nicht angehakt.")
    dicke, d_quelle = dicke_aus([dateiname] + texte0), "Text"
    seiten = sorted({a.seitenansicht for a in ansichten if a.seitenansicht})
    if dicke is None and len(seiten) == 1 and not rohr:
        dicke, d_quelle = seiten[0], "Seitenansicht"
    return dict(teile=teile, texte=texte0, warnungen=warn, dicke=dicke, dicke_quelle=d_quelle if dicke else None,
                massstab=massstab, massstab_quelle=quelle, rahmen=n_rahmen, rohr=rohr)


def _ohne_doppelte(schnitt):
    """Gleiche Strecke doppelt (auch umgekehrt, auf 0,001 mm) nur einmal."""
    gesehen, out = set(), []
    for el in schnitt:
        p, q, b = (round(el[0][0], 3), round(el[0][1], 3)), (round(el[1][0], 3), round(el[1][1], 3)), round(el[2], 6)
        k = (p, q, b) if (p, q) <= (q, p) else (q, p, -b)
        if k not in gesehen:
            gesehen.add(k)
            out.append(el)
    return out


def _ansichten(schnitt, kreise, gefunden):
    """Ansichten der Zeichnung (dxf_ansichten) aus allen Schnittlinien und Kreisen und die Rohrerkennung aus den
    gefundenen Teilen mit genau einer Innenkontur."""
    strecken = []
    for p, q, b, _l in schnitt:
        if b:
            zug = [p] + sw.bogen_punkte(p, q, b)
            strecken += list(zip(zug, zug[1:]))
        else:
            strecken.append((p, q))
    ansichten = da.seitenansichten(da.gruppen(strecken, [(c, r) for _, c, r in kreise]))
    querschnitte = []
    for k, innen, grund in gefunden:
        if grund is None and len(innen) == 1:
            qs = da.rohr_querschnitt(dict(bb=k.bb, rund=_rund_kontur(k)), dict(bb=innen[0].bb, rund=_rund_kontur(innen[0])))
            ans = _ansicht_von(k, ansichten)
            if qs and ans is not None and not ans.iso:
                querschnitte.append((ans, qs))
    return ansichten, da.rohr_erkennen(querschnitte, ansichten)


def _rund_kontur(k):
    """Kreis (Kreis-Element oder alle Punkte gleich weit von der Mitte)?"""
    if k.zug.layer == "K":
        return True
    cx, cy = (k.bb[0] + k.bb[2]) / 2, (k.bb[1] + k.bb[3]) / 2
    r = [math.hypot(x - cx, y - cy) for x, y in k.dicht]
    return bool(r) and max(r) - min(r) <= max(0.05, 0.01 * max(r))


def _ansicht_von(k, ansichten):
    p = ((k.bb[0] + k.bb[2]) / 2, (k.bb[1] + k.bb[3]) / 2)
    return next((a for a in ansichten if a.enthaelt(p)), None)


def _grund(k, ansichten, rohr, t, splitter):
    """Warum ein gefundenes Teil nicht angehakt wird (Patrick 25.10.2026 B1, B2, B4) oder None."""
    if rohr:
        return "Rohrzeichnung, kein Blech"
    ans = _ansicht_von(k, ansichten)
    if ans is not None and ans.iso:
        return "Isometrie, keine Abwicklung"
    if ans is not None and ans.seitenansicht:
        return f"Seitenansicht (Dicke {_zahl(ans.seitenansicht, 2)} mm)"
    if splitter and max(k.bb[2] - k.bb[0], k.bb[3] - k.bb[1]) < splitter:
        return f"kleiner als {_zahl(splitter, 1)} mm (Maßpfeil, Splitter?)"
    if any(x["art"] == sw.SONSTIGE and x.get("linien") for x in t["e"]["konturen"]):
        return "offene Linien in der Kontur, bitte prüfen"
    return None


def _teil(aussen, innen, offen, gravur, gravtexte, biegung):
    """Ein Blech aus Außenkontur, Innenkonturen, offenen Schnittlinien, Gravur, Gravurtexten und Biegelinien."""
    warn = []
    dreh = 0.0
    if biegung:
        ws = {round(_norm_dreh(_winkel(p, q)), 2) for p, q, _ in biegung}
        if len(ws) > 1:
            warn.append("Biegelinien sind nicht parallel: das Teil wird als flacher Zuschnitt übernommen.")
            biegung = []
        else:
            dreh = -ws.pop()            # Biegelinien waagerecht (Kantteil: Biegelinien laufen entlang x)

    def dr(p):
        c, s = math.cos(math.radians(dreh)), math.sin(math.radians(dreh))
        return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)

    def dr_zug(z):
        return Zug(z.layer, [dr(p) for p in z.punkte], z.bulges, z.geschlossen)

    if dreh:
        aussen, innen, offen = dr_zug(aussen), [dr_zug(z) for z in innen], [dr_zug(z) for z in offen]
        gravur = [(("K", dr(g[1]), g[2]) if g[0] == "K" else (dr(g[0]), dr(g[1]), g[2], g[3])) for g in gravur]
        gravtexte = [(t[0], t[1], dr(t[2]), t[3], t[4] + dreh, t[5]) for t in gravtexte]
        biegung = [(dr(p), dr(q), a) for p, q, a in biegung]
    if aussen.flaeche < 0:
        aussen = aussen.umgedreht()
    aussen = _ohne_flucht(aussen)
    dicht = aussen.dicht()
    ox, oy = min(x for x, _ in dicht), min(y for _, y in dicht)
    lg, br = max(x for x, _ in dicht) - ox, max(y for _, y in dicht) - oy
    e = dict(art=blech.ZUSCHNITT, konturen=[])
    if len(aussen.punkte) == 4 and not any(aussen.bulges) and all(
            abs(a[0] - b[0]) <= FORM_TOL or abs(a[1] - b[1]) <= FORM_TOL
            for a, b in zip(aussen.punkte, aussen.punkte[1:] + aussen.punkte[:1])):
        e.update(form=blech.RECHTECK, laenge=round(lg, 4), breite=round(br, 4), eckradius=0)
    else:
        e.update(form=blech.POLYGON, punkte=punkte_text(aussen.punkte, aussen.bulges, ox, oy),
                 laenge=round(lg, 4), breite=round(br, 4))
    zahl = dict(norm=0, polygon=0, offen=0, gravur=0)
    for z in innen:
        if z.layer == "K":
            c = ((z.punkte[0][0] + z.punkte[1][0]) / 2, (z.punkte[0][1] + z.punkte[1][1]) / 2)
            f = dict(art=sw.BOHRUNG, d=round(math.dist(*z.punkte), 4), cx=c[0], cy=c[1])
        else:
            f = _form_aus(z) or _polygon_kontur(z)
        zahl["polygon" if f["art"] == sw.POLYGON else "norm"] += 1
        cx, cy = f.pop("cx"), f.pop("cy")
        e["konturen"].append(dict(f, anzahl=1, x=round(cx - ox, 4), y=round(cy - oy, 4)))
    for z in offen:                       # offene Schnittlinien: als sonstige Kontur mit Länge (und Linien)
        zahl["offen"] += 1
        d = z.dicht()
        cx, cy = (min(x for x, _ in d) + max(x for x, _ in d)) / 2, (min(y for _, y in d) + max(y for _, y in d)) / 2
        e["konturen"].append(dict(art=sw.SONSTIGE, anzahl=1, laenge=round(z.laenge(), 2), x=round(cx - ox, 4),
                                  y=round(cy - oy, 4), linien=[[[round(x - cx, 4), round(y - cy, 4)] for x, y in d]]))
    if zahl["offen"]:
        warn.append(f"{zahl['offen']} offene Schnittlinie{'n' if zahl['offen'] > 1 else ''} (Kontur nicht "
                    "geschlossen): als sonstige Kontur mit Länge übernommen, bitte prüfen.")
    if gravur:                            # alle Gravurlinien als eine Gravur-Zeile mit Länge und Linien
        gz = verketten([g for g in gravur if g[0] != "K"])
        linien = [z.dicht() + (z.dicht()[:1] if z.geschlossen else []) for z in gz]
        linien += [[(g[1][0] + g[2] * math.cos(math.radians(a)), g[1][1] + g[2] * math.sin(math.radians(a)))
                    for a in range(0, 361, 5)] for g in gravur if g[0] == "K"]
        pk = [p for zug in linien for p in zug]
        cx, cy = (min(x for x, _ in pk) + max(x for x, _ in pk)) / 2, (min(y for _, y in pk) + max(y for _, y in pk)) / 2
        e["konturen"].append(dict(art=sw.GRAVUR, anzahl=1,
                                  laenge=round(sum(math.dist(a, b) for zug in linien for a, b in zip(zug, zug[1:])), 2),
                                  x=round(cx - ox, 4), y=round(cy - oy, 4),
                                  linien=[[[round(x - cx, 4), round(y - cy, 4)] for x, y in zug] for zug in linien]))
        zahl["gravur"] += 1
    from . import gravur_text
    for _t, _l, p, h, w, text_, *_ in gravtexte:
        if h <= 0:
            continue
        b, hh = gravur_text.masse(text_, h)
        c, s = math.cos(math.radians(w)), math.sin(math.radians(w))
        mx, my = p[0] + b / 2 * c - hh / 2 * s, p[1] + b / 2 * s + hh / 2 * c
        e["konturen"].append(dict(art=sw.TEXT_GRAVUR, anzahl=1, text=text_, hoehe=round(h, 3),
                                  winkel=round(w % 360, 3), x=round(mx - ox, 4), y=round(my - oy, 4)))
        zahl["gravur"] += 1
    biegelinien = sorted({(round(p[1] - oy, 4), a) for p, _q, a in biegung})
    if biegelinien:
        e["biegelinien_dxf"] = [dict(y=y, winkel=-90 if a == "runter" else 90) for y, a in biegelinien]
    zusammen = (f"{_zahl(lg, 1)} × {_zahl(br, 1)} mm "
                f"({'Rechteck' if e['form'] == blech.RECHTECK else f'{len(aussen.punkte)} Eckpunkte'}"
                f"{', mit Bögen' if any(aussen.bulges) else ''}), {zahl['norm']} Bohrung/Langloch/Rechteck, "
                f"{zahl['polygon']} Originalkontur, {zahl['gravur']} Gravur"
                + (f", {len(biegelinien)} Biegelinien" if biegelinien else ""))
    return dict(e=e, warnungen=warn, zusammenfassung=zusammen, biegelinien=biegelinien)


def als_kantteil(e, winkel, dicke, k=blech.K_FAKTOR, radius=None):
    """Zuschnitt mit Biegelinien (e['biegelinien_dxf'], y ab Unterkante) als Kantteil: Schenkel-Außenmaße so, dass
    die Abwicklung (blech.biegungen) die Biegelinien an derselben Stelle hat. winkel: je Biegelinie [Grad]."""
    lagen = [b["y"] for b in e.get("biegelinien_dxf") or ()]
    if not lagen:
        return e
    br = _z(e.get("breite"))
    s = _z(dicke)
    r = s if radius in (None, "") else _z(radius)
    schenkel, vorher = [], 0.0          # vorher: Lage des Schenkelanfangs in der Abwicklung
    for lage, w in zip(lagen, winkel):
        v = blech.ausgleich(w, r, s, k(r) if callable(k) else k)
        schenkel.append(dict(laenge=round(lage + v / 2 - vorher, 3), winkel=w, radius=None))
        vorher = lage + v / 2 - v
    schenkel.append(dict(laenge=round(br - vorher, 3), winkel=0, radius=None))
    return dict(e, art=blech.KANTTEIL, kantlaenge=e.get("laenge"), schenkel=schenkel, dicke=dicke)


_z = sw._z


def datei_lesen(pfad):
    """DXF-Datei als Text (UTF-8, sonst cp1252 wie ältere AutoCAD-Versionen)."""
    with open(pfad, "rb") as f:
        roh = f.read()
    if roh.startswith(b"AutoCAD Binary DXF"):
        raise DxfFehler("Binäre DXF wird nicht unterstützt: bitte im CAD als ASCII-DXF speichern.")
    for kod in ("utf-8", "cp1252"):
        try:
            return roh.decode(kod)
        except UnicodeDecodeError:
            continue
    return roh.decode("latin-1")
