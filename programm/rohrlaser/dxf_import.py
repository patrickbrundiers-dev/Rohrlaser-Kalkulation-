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
import itertools
import math
import re

from . import blech, dxf, dxf_ansichten as da, schneidweg as sw

TOL = 0.05              # mm: Lücke, die beim Verketten noch als geschlossen gilt
LUECKE = 0.5            # mm: größere Lücken einer Kontur werden gerade geschlossen (mit Hinweis), noch größere nicht
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
    text = re.sub(r"\r+\n", "\n", text)               # auch doppelt umgewandelte Zeilenenden (\r\r\n)
    zeilen = text.split("\n") if "\n" in text else text.split("\r")
    while zeilen and not zeilen[-1].strip():
        zeilen.pop()
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
    erg = dict(einheit=1.0, insunits=None, measurement=None, layer={}, bloecke={}, entitaeten=[], papier=0,
               nur_papier=False, papier_texte=[], hinweise=set(), _zaehler=itertools.count())
    i = 0
    while i < len(paare):
        code, wert = paare[i]
        if code == 0 and wert.strip() == "SECTION" and i + 1 < len(paare) and paare[i + 1][0] == 2:
            name = paare[i + 1][1].strip()
            i += 2
            if name == "HEADER":
                while i < len(paare) and not (paare[i][0] == 0 and paare[i][1].strip() == "ENDSEC"):
                    if paare[i][0] == 9 and paare[i][1].strip() in ("$INSUNITS", "$MEASUREMENT"):
                        try:
                            v = int(paare[i + 1][1].strip())
                        except (ValueError, IndexError):
                            v = None
                        if v is not None and paare[i][1].strip() == "$INSUNITS":
                            erg["einheit"], erg["insunits"] = EINHEITEN.get(v, 1.0), v
                        elif v is not None:
                            erg["measurement"] = v
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
                        erg["bloecke"][_wert(d, 2, "", str)] = ((_wert(d, 10, 0.0), _wert(d, 20, 0.0)),
                                                              _polylinien_zusammen(ents))
                        continue
                    i += 1
            elif name == "ENTITIES":
                ents, i = _entitaeten(paare, i, ("ENDSEC",))
                modell, papier = _papierbereich(_polylinien_zusammen(ents))
                if any(t not in NICHT_GEZEICHNET for t, _ in modell):
                    erg["entitaeten"] = modell
                    erg["papier"] = sum(1 for t, _ in papier if t not in NICHT_GEZEICHNET)
                    if erg["papier"]:   # Schriftfeld im Layout: Texte für Werkstoff/Dicke/Profil, nie für den Maßstab
                        erg["papier_texte"] = [el[1:6] for el in elemente(dict(erg, entitaeten=papier))
                                               if el[0] == "T"]
                else:
                    erg["entitaeten"], erg["nur_papier"] = papier, bool(papier)
            continue
        i += 1
    return erg


NICHT_GEZEICHNET = ("VIEWPORT", "ATTRIB", "VERTEX", "SEQEND", "DIMENSION", "POINT", "HATCH", "SOLID", "LEADER",
                    "MULTILEADER", "IMAGE", "WIPEOUT", "OLE2FRAME")


def _papierbereich(ents):
    """(Modellbereich, Papierbereich): Elemente mit Code 67 = 1 liegen im Papierbereich (Layout mit Rahmen und
    Schriftfeld; die Geometrie im Modellbereich ist dann immer 1:1)."""
    modell, papier = [], []
    for typ, d in ents:
        (papier if _wert(d, 67, 0, int) == 1 else modell).append((typ, d))
    return modell, papier


def text_klar(t, mtext=False):
    """Text ohne DXF-Steuerzeichen: \\U+00E4 -> ä, %%c -> Ø, %%d -> °, %%p -> ±; MTEXT ohne Formatierung (\\P = neue
    Zeile -> Leerzeichen, \\S1^2; -> 1/2)."""
    t = re.sub(r"\\U\+([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), str(t or ""))
    t = re.sub(r"%%(\d{3})", lambda m: chr(int(m.group(1))), t)
    for a, b in (("%%c", "Ø"), ("%%d", "°"), ("%%p", "±"), ("%%%", "%")):
        t = re.sub(re.escape(a), b, t, flags=re.IGNORECASE)
    t = re.sub(r"%%[uok]", "", t, flags=re.IGNORECASE)
    if mtext:
        t = t.replace("\\P", " ").replace("\\~", " ").replace("\\\\", "\x00")
        t = re.sub(r"\\S([^;]*?)[\^#/]([^;]*);", r"\1/\2", t)
        t = re.sub(r"\\[ACFfHQTWp][^;]*;", "", t)
        t = re.sub(r"\\[LlOoKkNX]", "", t)
        t = re.sub(r"(?<!\\)[{}]", "", t).replace("\\{", "{").replace("\\}", "}").replace("\x00", "\\")
    return t


# ------------------------------------------------------------------ Elemente in mm, Weltsystem
# Strecke: ("S", layer, p, q, bulge, gruppe); Kreis: ("K", layer, c, r); Text: ("T", layer, p, hoehe, winkel, text);
# gruppe: Nummer des geschlossenen Elements (Polylinie, Spline, Ellipse), zu dem die Strecke gehört, sonst None

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


def _durch_punkte(pk, n_je=16):
    """Kubischer Spline durch die Stützpunkte (natürliche Enden, Parameter = Sehnenlänge): Splines, die nur mit
    Stützpunkten (Code 11/21) gespeichert sind."""
    if len(pk) < 3:
        return list(pk)
    t = [0.0]
    for a, b in zip(pk, pk[1:]):
        t.append(t[-1] + max(math.dist(a, b), 1e-9))
    n = len(pk)

    def zweite(werte):             # zweite Ableitungen (Thomas-Verfahren)
        h = [t[i + 1] - t[i] for i in range(n - 1)]
        a, b, c, r = [0.0] * n, [1.0] * n, [0.0] * n, [0.0] * n
        for i in range(1, n - 1):
            a[i], b[i], c[i] = h[i - 1], 2 * (h[i - 1] + h[i]), h[i]
            r[i] = 6 * ((werte[i + 1] - werte[i]) / h[i] - (werte[i] - werte[i - 1]) / h[i - 1])
        for i in range(1, n):
            m = a[i] / b[i - 1]
            b[i] -= m * c[i - 1]
            r[i] -= m * r[i - 1]
        z = [0.0] * n
        for i in range(n - 1, -1, -1):
            z[i] = (r[i] - (c[i] * z[i + 1] if i < n - 1 else 0.0)) / b[i]
        return z
    xs, ys = [p[0] for p in pk], [p[1] for p in pk]
    zx, zy = zweite(xs), zweite(ys)
    out = [pk[0]]
    for i in range(n - 1):
        h = t[i + 1] - t[i]
        for k in range(1, n_je + 1):
            u = t[i] + h * k / n_je
            A, B = (t[i + 1] - u) / h, (u - t[i]) / h
            out.append(tuple(A * v[i] + B * v[i + 1] + ((A ** 3 - A) * z[i] + (B ** 3 - B) * z[i + 1]) * h * h / 6
                             for v, z in ((xs, zx), (ys, zy))))
    return out


def _spline_punkte(d, hinweise=None):
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
    if len(fit) >= 3:
        if hinweise is not None:
            hinweise.add("Spline nur mit Stützpunkten gespeichert: Kurve durch die Punkte angenähert, bitte Kontur "
                         "prüfen (im CAD besser als Polylinie oder mit Kontrollpunkten speichern).")
        return _durch_punkte(fit)
    return fit if len(fit) >= 2 else ctrl


def _ocs(d):
    """Spiegelung durch Extrusion (0, 0, −1): x wird negativ."""
    return (_wert(d, 230, 1.0) or 1.0) < 0


def elemente(roh, trafo=None, tiefe=0, layer_vorgabe="0", lt_vorgabe=""):
    """Elemente in mm im Weltsystem (Blöcke aufgelöst, auch Mehrfach-Blöcke MINSERT und sichtbare Attribute)."""
    s = roh["einheit"]
    trafo = trafo or _Trafo(s, 0, 0, s, 0, 0)
    zaehler = roh.get("_zaehler") or itertools.count()
    hinweise = roh.get("hinweise")
    out = []
    ents = roh["entitaeten"] if tiefe == 0 else roh["_block"]
    for typ, d in ents:
        layer = _wert(d, 8, layer_vorgabe, str) or layer_vorgabe
        if layer == "0" and tiefe:
            layer = layer_vorgabe
        info = roh["layer"].get(layer.upper(), {})
        if info.get("aus"):
            continue
        lt = (_wert(d, 6, "", str) or "").upper()
        if lt in ("", "BYLAYER"):                 # „VonLayer“: Linientyp des Layers
            lt = info.get("linientyp") or ""
        elif lt == "BYBLOCK":                     # „VonBlock“: Linientyp der Blockreferenz
            lt = lt_vorgabe
        if typ == "INSERT":
            if tiefe > 8:
                continue
            for a in getattr(d, "attribute", ()):  # Attribute (Schriftfeld) liegen schon im Weltsystem der Referenz
                if not int(_wert(a, 70, 0, int) or 0) & 1:
                    a_layer = _wert(a, 8, layer, str) or layer
                    tag = (_wert(a, 2, "", str) or "").strip()
                    wert = (_wert(a, 1, "", str) or "").strip()
                    if not wert:
                        continue
                    if re.fullmatch(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß_.\-]{2,}", tag):  # Feldname als Beschriftung
                        a = [(c, w) for c, w in a if c != 1] + [(1, f"{tag.replace('_', ' ')}: {wert}")]
                    out += [(*el, False) for el in _element("TEXT", a, layer if a_layer == "0" else a_layer, trafo)]
            blk = roh["bloecke"].get(_wert(d, 2, "", str))
            if not blk:
                continue
            (bx, by), bents = blk
            sx, sy = _wert(d, 41, 1.0) or 1.0, _wert(d, 42, 1.0) or 1.0
            w0 = math.radians(_wert(d, 50, 0.0) or 0.0)
            spalten, zeilen = max(1, int(_wert(d, 70, 1, int) or 1)), max(1, int(_wert(d, 71, 1, int) or 1))
            ds, dz = _wert(d, 44, 0.0) or 0.0, _wert(d, 45, 0.0) or 0.0
            for i_s, i_z in itertools.product(range(spalten), range(zeilen)):
                ox, oy = i_s * ds, i_z * dz     # Mehrfach-Block: Raster im gedrehten System der Referenz
                px = _wert(d, 10, 0.0) + ox * math.cos(w0) - oy * math.sin(w0)
                py = _wert(d, 20, 0.0) + ox * math.sin(w0) + oy * math.cos(w0)
                w, sx_ = w0, sx
                if _ocs(d):
                    px, w, sx_ = -px, math.pi - w0, -sx
                cw, sn = math.cos(w), math.sin(w)
                t = _Trafo(cw * sx_, -sn * sy, sn * sx_, cw * sy, px - (cw * sx_ * bx - sn * sy * by),
                           py - (sn * sx_ * bx + cw * sy * by))
                unter = dict(roh, _block=bents)
                out += elemente(unter, trafo.mal(t), tiefe + 1, layer, lt)
            continue
        strich = any(w_ in lt for w_ in STRICH_LINIEN)
        out += [(*el, strich) for el in _element(typ, d, layer, trafo, next(zaehler), hinweise)]
    return out


def _strecken(pk, layer, trafo, geschlossen=False, bulges=None, gruppe=None):
    """Polylinie (Punkte im Objektsystem) -> Strecken im Weltsystem; Bögen bleiben, wenn die Abbildung sie erhält.
    Geschlossene Züge (auch offen gespeichert mit gleichem Anfangs- und Endpunkt) tragen die Nummer gruppe."""
    out = []
    n = len(pk)
    bulges = bulges or [0.0] * n
    spiegel = trafo.spiegelt
    if not geschlossen and n >= 3 and math.dist(pk[0], pk[-1]) <= 1e-6 * max(1.0, abs(pk[0][0]), abs(pk[0][1])):
        g = gruppe
    else:
        g = gruppe if geschlossen else None
    for i in range(n if geschlossen else n - 1):
        p, q, b = pk[i], pk[(i + 1) % n], bulges[i]
        if b and not trafo.gleichmaessig:
            zug = [p] + sw.bogen_punkte(p, q, b)
            out += [("S", layer, trafo(a), trafo(c), 0.0, g) for a, c in zip(zug, zug[1:])]
        else:
            out.append(("S", layer, trafo(p), trafo(q), -b if spiegel else b, g))
    return out


def _element(typ, d, layer, trafo, gruppe=None, hinweise=None):
    m = -1.0 if _ocs(d) else 1.0
    if typ == "LINE":
        return [("S", layer, trafo((m * _wert(d, 10, 0.0), _wert(d, 20, 0.0))),
                 trafo((m * _wert(d, 11, 0.0), _wert(d, 21, 0.0))), 0.0, None)]
    if typ in ("CIRCLE", "ARC"):
        c, r = (_wert(d, 10, 0.0), _wert(d, 20, 0.0)), _wert(d, 40, 0.0)
        if r <= 0:
            return []
        if typ == "CIRCLE" or abs(((_wert(d, 51, 360.0) - _wert(d, 50, 0.0)) % 360)) < 1e-9:
            if trafo.gleichmaessig:
                cc = trafo((m * c[0], c[1]))
                return [("K", layer, cc, r * trafo.mass)]
            zug = _ellipse_punkte((m * c[0], c[1]), (r, 0.0), 1.0, 0.0, 2 * math.pi)
            return _strecken(zug[:-1], layer, trafo, geschlossen=True, gruppe=gruppe)
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
        return _strecken(pk, layer, trafo, geschlossen=zu, bulges=bulges, gruppe=gruppe) if len(pk) >= 2 else []
    if typ == "_POLYLINE":
        pk, bulges, zu = d.poly
        pk = [(m * x, y) for x, y in pk]
        if m < 0:
            bulges = [-b for b in bulges]
        return _strecken(pk, layer, trafo, geschlossen=zu, bulges=bulges, gruppe=gruppe) if len(pk) >= 2 else []
    if typ == "ELLIPSE":
        c = (_wert(d, 10, 0.0), _wert(d, 20, 0.0))
        achse = (_wert(d, 11, 0.0), _wert(d, 21, 0.0))
        zug = _ellipse_punkte(c, achse, _wert(d, 40, 1.0), _wert(d, 41, 0.0), _wert(d, 42, 2 * math.pi))
        zug = [(m * x, y) for x, y in zug]
        return _strecken(zug, layer, trafo, gruppe=gruppe)
    if typ == "SPLINE":
        zug = [(m * x, y) for x, y in _spline_punkte(d, hinweise)]
        zu = bool(int(_wert(d, 70, 0, int) or 0) & 1)
        if zu and len(zug) >= 2 and math.dist(zug[0], zug[-1]) <= TOL:
            zug[-1] = zug[0]
        return _strecken(zug, layer, trafo, geschlossen=zu and math.dist(zug[0], zug[-1]) > TOL, gruppe=gruppe) \
            if len(zug) >= 2 else []
    if typ in ("TEXT", "MTEXT"):
        text = _wert(d, 1, "", str) or ""
        if typ == "MTEXT":
            text = text_klar("".join(w for c, w in d if c == 3) + text, mtext=True)
        else:
            text = text_klar(text)
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
                kopf = [x for x in d if x[0] in (8, 6, 67, 230)]
                out.append(("_POLYLINE", _PolyDaten(kopf, (pk, bulges, bool(flags & 1)))))
            continue
        if typ == "INSERT" and not isinstance(d, _InsertDaten):
            attribute = []
            i += 1
            while i < len(ents) and ents[i][0] == "ATTRIB":
                attribute.append(ents[i][1])
                i += 1
            if attribute and i < len(ents) and ents[i][0] == "SEQEND":
                i += 1
            out.append((typ, _InsertDaten(d, attribute)))
            continue
        out.append((typ, d))
        i += 1
    return out


class _InsertDaten(list):
    """Daten einer Blockreferenz und .attribute = Daten der folgenden ATTRIB (Schriftfeld-Werte)."""

    def __init__(self, daten, attribute):
        super().__init__(daten)
        self.attribute = attribute


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
        p, q, b, layer = strecken[start][:4]
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
                p2, q2, b2, _l = strecken[j][:4]
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


# ------------------------------------------------------------------ Konturen robust bilden
def _schluessel(p, q, b):
    p, q, b = (round(p[0], 3), round(p[1], 3)), (round(q[0], 3), round(q[1], 3)), round(b, 6)
    return (p, q, b) if (p, q) <= (q, p) else (q, p, -b)


def _gruppe_als_zug(segs):
    """Strecken eines geschlossenen Elements (in Reihenfolge) -> geschlossener Zug oder None (passt nicht)."""
    if len(segs) < 2 or any(math.dist(a[1], b[0]) > TOL for a, b in zip(segs, segs[1:])) or \
            math.dist(segs[-1][1], segs[0][0]) > TOL:
        return None
    return Zug(segs[0][3], [s_[0] for s_ in segs], [s_[2] for s_ in segs], True)


def _zug_schluessel(z):
    """Gleiche Kontur (auch anders herum oder mit anderem Startpunkt gezeichnet)."""
    pk = z.dicht()
    return (round(abs(z.flaeche), 1), round(z.laenge(), 1), round(min(x for x, _ in pk), 2),
            round(min(y for _, y in pk), 2), round(max(x for x, _ in pk), 2), round(max(y for _, y in pk), 2))


def _kreise_einmal(kreise):
    """Gleiche Kreise (übereinander gezeichnet) nur einmal: (Kreise, Anzahl weggelassen)."""
    gesehen, out = set(), []
    for k in kreise:
        s_ = (round(k[1][0], 3), round(k[1][1], 3), round(k[2], 3))
        if s_ not in gesehen:
            gesehen.add(s_)
            out.append(k)
    return out, len(kreise) - len(out)


def _geraden_bucket(p, q):
    """(Richtung, Abstand vom Ursprung, Einheitsvektor) der Geraden durch p, q."""
    w = math.atan2(q[1] - p[1], q[0] - p[0]) % math.pi
    if w > math.pi - 1e-4:
        w -= math.pi
    u = (math.cos(w), math.sin(w))
    return w, p[1] * u[0] - p[0] * u[1], u


def _ueberlappungen(lose, feste):
    """Gerade lose Strecken, die eine Kante eines geschlossenen Elements oder einander teilweise überdecken (doppelt
    gezeichnet, anders unterteilt): überdeckte Stücke weg, Überlappungen nur einmal (an allen Endpunkten geteilt).
    lose/feste: [(p, q, b, layer, gruppe)]. Ergebnis: (lose Strecken, Anzahl entfernter Doppelstücke)."""
    toepfe = {}
    for art, liste in (("fest", feste), ("lose", lose)):
        for i, s_ in enumerate(liste):
            if s_[2]:
                continue
            w, d, u = _geraden_bucket(s_[0], s_[1])
            toepfe.setdefault((round(w / 2e-4), round(d / TOL)), []).append((art, i, w, d, u))
    weg, neu, n = set(), [], 0
    for (kw, kd), eintraege in toepfe.items():
        if not any(e[0] == "lose" for e in eintraege):
            continue
        nachbarn = [e for dw in (-1, 0, 1) for dd in (-1, 0, 1) for e in toepfe.get((kw + dw, kd + dd), ())]
        for art, i, w, d, u in eintraege:
            if art != "lose" or i in weg:
                continue
            p, q = lose[i][0], lose[i][1]
            t0, t1 = sorted((p[0] * u[0] + p[1] * u[1], q[0] * u[0] + q[1] * u[1]))
            andere = []
            for a2, j, w2, d2, u2 in nachbarn:
                if (a2, j) == ("lose", i) or abs(w2 - w) > 4e-4 or abs(d2 - d) > TOL or (a2 == "lose" and j in weg):
                    continue
                s2 = (feste if a2 == "fest" else lose)[j]
                a, b = sorted((s2[0][0] * u[0] + s2[0][1] * u[1], s2[1][0] * u[0] + s2[1][1] * u[1]))
                if min(t1, b) - max(t0, a) > TOL:
                    andere.append((a2, j, a, b))
            if not andere:
                continue
            # Stücke dieser Strecke, die nicht unter einer festen Kante oder einer früheren losen Strecke liegen
            deck = sorted((a, b) for a2, j, a, b in andere if a2 == "fest" or j < i)
            stuecke, t = [], t0
            for a, b in deck:
                if a > t + TOL:
                    stuecke.append((t, min(a, t1)))
                t = max(t, b)
            if t1 > t + TOL:
                stuecke.append((t, t1))
            if stuecke == [(t0, t1)]:
                continue
            weg.add(i)
            n += 1
            nx, ny = -u[1], u[0]
            for a, b in stuecke:
                if b - a > TOL:
                    neu.append(((a * u[0] + d * nx, a * u[1] + d * ny), (b * u[0] + d * nx, b * u[1] + d * ny), 0.0,
                                lose[i][3], None))
    return [s_ for i, s_ in enumerate(lose) if i not in weg] + neu, n


def _luecken(zuege, groesste=LUECKE):
    """Brücken über kleine Lücken zwischen Enden offener Züge (TOL < Abstand <= groesste), nächste zuerst:
    [(p, q, 0, layer, None)]."""
    enden = []
    for nr, z in enumerate(zuege):
        if not z.geschlossen and len(z.punkte) >= 2:
            enden += [(nr, 0, z.punkte[0], z), (nr, 1, z.punkte[-1], z)]
    raster = {}
    for k, (_nr, _e, p, _z) in enumerate(enden):
        raster.setdefault((math.floor(p[0] / groesste), math.floor(p[1] / groesste)), []).append(k)
    paare = []
    for k, (nr, e, p, z) in enumerate(enden):
        gx, gy = math.floor(p[0] / groesste), math.floor(p[1] / groesste)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in raster.get((gx + dx, gy + dy), ()):
                    if j <= k:
                        continue
                    nr2, _e2, q, _z2 = enden[j]
                    d = math.dist(p, q)
                    if TOL < d <= groesste and (nr2 != nr or z.laenge() > 4 * d and len(z.punkte) >= 3):
                        paare.append((d, k, j))
    benutzt, out = set(), []
    for d, k, j in sorted(paare):
        if k in benutzt or j in benutzt:
            continue
        benutzt |= {k, j}
        out.append((enden[k][2], enden[j][2], 0.0, enden[k][3].layer, None))
    return out


def konturen_bilden(schnitt):
    """Schnittstrecken [(p, q, b, layer, gruppe)] -> (Züge, Strecken (p, q, b, layer) ohne Doppelte, Anzahl doppelt
    gezeichneter Konturen/Stücke, geschlossene Lücken [mm]). Geschlossene Elemente (Polylinie, Spline, Ellipse) bleiben
    eigene Konturen, auch wenn sie eine Kante mit einem Nachbarteil teilen; lose Linien werden verkettet, doppelte und
    teilweise überdeckte Stücke fallen weg, Lücken bis LUECKE werden gerade geschlossen."""
    gruppen, lose = {}, []
    for s_ in schnitt:
        (gruppen.setdefault(s_[4], []) if s_[4] is not None else lose).append(s_)
    feste, zuege, gesehen, n_doppelt = [], [], set(), 0
    for segs in gruppen.values():
        z = _gruppe_als_zug(segs)
        if z is None:
            lose += [(*s_[:4], None) for s_ in segs]
            continue
        k = _zug_schluessel(z)
        if k in gesehen:
            n_doppelt += 1
            continue
        gesehen.add(k)
        zuege.append(z)
        feste += segs
    kanten = {_schluessel(*s_[:3]) for s_ in feste}
    vorher = len(lose)
    lose = [s_ for s_ in _ohne_doppelte(lose) if _schluessel(*s_[:3]) not in kanten]
    n_doppelt += vorher - len(lose)
    lose, n_ueber = _ueberlappungen(lose, feste)
    n_doppelt += n_ueber
    lose_zuege = verketten(lose)
    bruecken = _luecken(lose_zuege)
    if bruecken:
        lose_zuege = verketten(lose + bruecken)
    zuege += lose_zuege
    luecken = [math.dist(b[0], b[1]) for b in bruecken]
    return zuege, [s_[:4] for s_ in feste + lose + bruecken], n_doppelt, luecken


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
        # Linien eines Schriftfelds: mindestens zwei achsparallele Linienzüge, zusammen > 30 % des Umfangs (einzelne
        # offene Schnittlinien in einem rechteckigen Blech machen es nicht zum Rahmen)
        felder = [z for z in offene if k.enthaelt(z.dicht()[0]) and not any(z.bulges) and all(
            abs(a[0] - b[0]) <= FORM_TOL or abs(a[1] - b[1]) <= FORM_TOL for a, b in zip(z.punkte, z.punkte[1:]))]
        offen_lg = sum(z.laenge() for z in felder)
        umfang = 2 * (k.bb[2] - k.bb[0] + k.bb[3] - k.bb[1])
        if any(c.kinder for c in k.kinder) or (k.rechteck and k.kinder and (
                n_text >= 3 or (len(felder) >= 2 and offen_lg > 0.3 * umfang))):
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
            (schnitt if art == "schnitt" else gravur).append((el[2], el[3], el[4], el[1], el[5]))
    zuege, schnitt, n_doppelt, luecken = konturen_bilden(schnitt)
    kreise, n_k = _kreise_einmal(kreise)
    n_doppelt += n_k
    offen = [z for z in zuege if not z.geschlossen and z.laenge() > TOL]
    # geschlossene Züge ohne Fläche (Linie hin und zurück, z. B. aus Ansichten anderer CAD-Programme) fallen weg
    konturen = [_Kontur(z) for z in zuege if z.geschlossen and abs(z.flaeche) > 1e-6] + \
        [_Kontur(Zug("K", [(c[0] + r, c[1]), (c[0] - r, c[1])], [1.0, 1.0], True)) for _, c, r in kreise]
    if not konturen:
        raise DxfFehler("In der DXF wurde keine geschlossene Außenkontur gefunden."
                        + (f" {len(offen)} offene Linienzüge (Lücken über {_zahl(LUECKE, 1)} mm?) bitte im CAD "
                           "schließen." if offen else ""))
    text_punkte = [t[2] for t in texte if layer_art(t[1], namen, weg) != "gravur"]
    gefunden, n_rahmen = _teile(konturen, text_punkte, offen)
    kreuz_grund, kreuz_warn = _ueberschneidungen(gefunden)
    ansichten, rohr = _ansichten(schnitt, kreise, gefunden)
    rohr_zweifel = None
    if rohr:                    # bestätigen mit der Rohr-Erkennung (dxf_rohr), sonst bleiben die Bleche angehakt
        from . import dxf_rohr
        try:
            r_erg = dxf_rohr.erkennen(text, dateiname, namen, weg)
        except (ValueError, KeyError, TypeError, ZeroDivisionError):
            r_erg = dict(ok=False)
        if not (r_erg.get("ok") and r_erg.get("belegt")):
            rohr_zweifel, rohr = rohr, None
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
        grund = grund or kreuz_grund.get(id(k)) or _grund(k, ansichten, rohr, t, splitter)
        t["warnungen"] += kreuz_warn.get(id(k), [])
        t["_kontur"] = (k, innen)
        t.update(name=(beschr[0] if len(beschr) == 1 and len(beschr[0]) <= 40 else
                       (stamm or "DXF") + (f" Teil {nr}" if len(gefunden) > 1 else "")),
                 aktiv=grund is None, grund=grund)
        t["e"]["dxf"] = dateiname or True
        teile.append(t)
    teile, n_gleich = _gleiche_zusammen(teile)
    rest = sum(1 for z in offen if not any(k.enthaelt(z.dicht()[0]) for k, *_ in gefunden))
    if n_rahmen:
        warn.append(f"Zeichnungsrahmen erkannt ({n_rahmen}×): nicht übernommen.")
    if rest:
        warn.append(f"{rest} offene Linie{'n' if rest > 1 else ''} außerhalb der Teile (Schriftfeld, Hilfslinien) "
                    "nicht übernommen.")
    if rohr:
        warn.insert(0, f"Die Zeichnung zeigt ein Rohr ({rohr['text']}), kein Blech: als Blech wird nichts "
                       "übernommen. Im Angebot öffnet „Neue Position → Aus DXF“ dafür den Rohr-Editor.")
    elif rohr_zweifel:
        warn.insert(0, f"Teile sehen aus wie Schnitt und Ansicht eines Rohrs ({rohr_zweifel['text']}), als "
                       "Rohrzeichnung aber nicht belegt (keine Bemaßung, verdeckten Kanten, Schraffur oder "
                       "Profiltext): als Bleche angehakt, bitte prüfen.")
    n_iso = sum(1 for a in ansichten if a.iso)
    if n_iso and not rohr:
        warn.append(f"Isometrische Ansicht erkannt ({n_iso}×): ihre Konturen sind nicht angehakt.")
    warn += _lese_hinweise(roh, luecken, n_doppelt, n_gleich, teile)
    papier = [t[4] for t in roh.get("papier_texte") or ()]
    dicke, d_quelle = dicke_aus([dateiname] + texte0 + papier), "Text"
    seiten = sorted({a.seitenansicht for a in ansichten if a.seitenansicht})
    if dicke is None and len(seiten) == 1 and not rohr:
        dicke, d_quelle = seiten[0], "Seitenansicht"
    return dict(teile=teile, texte=texte0 + papier, warnungen=warn, dicke=dicke, dicke_quelle=d_quelle if dicke else None,
                massstab=massstab, massstab_quelle=quelle, rahmen=n_rahmen, rohr=rohr)


def _lese_hinweise(roh, luecken, n_doppelt, n_gleich, teile):
    """Hinweise zum Lesen der Datei (nie still anders rechnen als gezeichnet)."""
    out = []
    if luecken:
        out.append(f"{len(luecken)} Lücke{'n' if len(luecken) > 1 else ''} in Konturen (bis "
                   f"{_zahl(max(luecken), 2).replace('.', ',')} mm) gerade geschlossen: bitte Kontur prüfen.")
    if n_doppelt:
        out.append(f"{n_doppelt} doppelt gezeichnete Kontur{'en' if n_doppelt > 1 else ''} bzw. Linien nur einmal "
                   "übernommen.")
    if n_gleich:
        out.append(f"{n_gleich} gleiche Teile zusammengefasst (Stückzahl im Teil, änderbar).")
    if roh.get("papier"):
        out.append(f"Papierbereich (Layout) mit {roh['papier']} Elementen nicht als Kontur übernommen "
                   "(Rahmen/Schriftfeld); die Geometrie im Modellbereich gilt 1:1.")
    if roh.get("nur_papier"):
        out.append("Die Zeichnung liegt nur im Papierbereich (Layout): von dort übernommen, Maßstab bitte prüfen.")
    iu = roh.get("insunits")
    if iu is not None and iu not in EINHEITEN:
        out.append(f"Unbekannte Zeichnungseinheit (Code {iu}): mm angenommen, bitte Maße prüfen.")
    elif iu in (None, 0) and roh.get("measurement") == 0:
        out.append("Die Zeichnung ist in Zoll angelegt und hat keine Einheit: mm angenommen. Sind die Maße in Zoll, "
                   "Maßstab 1:25,4 eingeben.")
    elif iu in (None, 0) and teile and max(max(t["e"].get("laenge") or 0, t["e"].get("breite") or 0)
                                           for t in teile) < 20:
        out.append("Alle Teile kleiner als 20 mm und keine Einheit in der DXF: Einheit (Zoll, cm?) bitte prüfen.")
    out += sorted(roh.get("hinweise") or ())
    return out


def _abstand_rand(p, pk):
    """Kleinster Abstand des Punkts p zum geschlossenen Polygon pk."""
    best = math.inf
    for a, b in zip(pk, pk[1:] + pk[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        lg = dx * dx + dy * dy
        t = 0.0 if not lg else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lg))
        best = min(best, math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy))
    return best


def _kreuzt(a, b):
    """Liegt Kontur b teils deutlich innerhalb, teils deutlich außerhalb von Kontur a (Konturen überschneiden sich)?"""
    if b.bb[0] > a.bb[2] or b.bb[2] < a.bb[0] or b.bb[1] > a.bb[3] or b.bb[3] < a.bb[1]:
        return False
    pk = b.dicht[:: max(1, len(b.dicht) // 200)]
    innen = aussen = False
    for p in pk:
        if _abstand_rand(p, a.dicht) <= 2 * TOL:
            continue
        if a.enthaelt(p):
            innen = True
        else:
            aussen = True
        if innen and aussen:
            return True
    return False


def _ueberschneidungen(gefunden):
    """Konturen, die sich schneiden (z. B. Kreis auf der Außenkante gezeichnet statt ausgeschnitten): ({id(Kontur):
    Grund}, {id(Kontur): [Warnungen]}). Die Form ergibt sich dann nicht eindeutig: nicht anhaken bzw. warnen."""
    grund, warn = {}, {}
    nach = sorted(gefunden, key=lambda t: -t[0].flaeche)
    for i, (gross, innen, _g) in enumerate(nach):
        for klein, _i2, _g2 in nach[i + 1:]:
            if id(klein) not in grund and _kreuzt(gross, klein):
                grund[id(klein)] = "überschneidet die Außenkontur eines anderen Teils: im CAD prüfen"
                warn.setdefault(id(gross), []).append(
                    "Eine Kontur überschneidet die Außenkontur (z. B. Kreis auf der Kante): sie ist nicht "
                    "ausgeschnitten, bitte Kontur im CAD bereinigen.")
        if any(_kreuzt(gross, c) for c in innen):
            warn.setdefault(id(gross), []).append("Eine Innenkontur ragt über die Außenkontur: bitte prüfen.")
        if any(_kreuzt(a, b) for j, a in enumerate(innen) for b in innen[j + 1:]):
            warn.setdefault(id(gross), []).append("Innenkonturen überschneiden sich: bitte prüfen.")
    return grund, warn


def _form_merkmal(t):
    """Grobe Kennung eines Teils, gleich bei Drehung: zum schnellen Vorsortieren gleicher Teile."""
    k, innen = t["_kontur"]
    return (round(k.flaeche, 1), round(k.zug.laenge(), 1), len(innen),
            tuple(sorted(round(c.flaeche, 1) for c in innen)),
            tuple(sorted((x["art"], round(x.get("laenge") or 0, 1), x.get("text") or "") for x in t["e"]["konturen"]
                         if x["art"] in (sw.SONSTIGE, sw.GRAVUR, sw.TEXT_GRAVUR))),
            len(t["biegelinien"]))


def _punkte_teil(t):
    """Punkte eines Teils zum Vergleich: Eckpunkte der Außenkontur und Mitten der Innenkonturen."""
    k, innen = t["_kontur"]
    return [p for p in k.dicht], [((c.bb[0] + c.bb[2]) / 2, (c.bb[1] + c.bb[3]) / 2) for c in innen]


def _schwerpunkt(pk):
    return sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)


def gleich_gedreht(t1, t2, tol=0.05):
    """Ist Teil t2 dasselbe wie t1, nur verschoben und gedreht (nicht gespiegelt)?"""
    a, ai = _punkte_teil(t1)
    b, bi = _punkte_teil(t2)
    if len(a) != len(b):
        return False
    ca, cb = _schwerpunkt(a), _schwerpunkt(b)
    fern = max(a, key=lambda p: math.dist(p, ca))
    r = math.dist(fern, ca)
    wa = math.atan2(fern[1] - ca[1], fern[0] - ca[0])
    raster = {}
    for q in b + bi:
        raster.setdefault((round(q[0] / (4 * tol)), round(q[1] / (4 * tol))), []).append(q)

    def da(q):
        gx, gy = round(q[0] / (4 * tol)), round(q[1] / (4 * tol))
        return any(math.dist(q, z) <= tol for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                   for z in raster.get((gx + dx, gy + dy), ()))
    for q in b:
        if abs(math.dist(q, cb) - r) > tol:
            continue
        w = math.atan2(q[1] - cb[1], q[0] - cb[0]) - wa
        c, s_ = math.cos(w), math.sin(w)

        def dreh(p):
            x, y = p[0] - ca[0], p[1] - ca[1]
            return (cb[0] + x * c - y * s_, cb[1] + x * s_ + y * c)
        if all(da(dreh(p)) for p in a + ai):
            return True
    return False


def _gleiche_zusammen(teile):
    """Gleiche angehakte Teile (auch gedreht, nicht gespiegelt; Patrick 28.10.2026 „a“) zu einem Teil mit Stückzahl:
    (Teile, Anzahl zusammengefasster)."""
    out, n = [], 0
    for t in teile:
        if t["aktiv"]:
            m = _form_merkmal(t)
            gleich = next((o for o in out if o["aktiv"] and o["_merkmal"] == m and gleich_gedreht(o, t)), None)
            if gleich is not None:
                gleich["anzahl"] += 1
                n += 1
                continue
            t["_merkmal"] = m
        t["anzahl"] = 1
        out.append(t)
    for t in out:
        t.pop("_kontur", None)
        t.pop("_merkmal", None)
        if t["anzahl"] > 1:
            t["zusammenfassung"] = f"{t['anzahl']}× gleich · " + t["zusammenfassung"]
    return out, n + sum(1 for t in out if t["anzahl"] > 1)


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
