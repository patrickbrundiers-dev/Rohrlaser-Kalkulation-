"""Programmierten Schneidweg aus einer TRUMPF-LST lesen (Patrick 24.11.2026: „So ist der programmierte Schneidweg.
Kannst du das aus der .lst auch so auslesen“). Ohne Qt und ohne OpenCascade.

Der NC-Teil (BEGIN_PROGRAMM … START_TEXT) beschreibt den Weg des Schneidkopfs in Maschinenkoordinaten: X entlang der
Rohrachse, Y quer, Z die Höhe des Schneidpunkts über der Rohrmitte, A die Drehung des Rohrs in Grad. Auf ebenen
Seiten fährt TubeCAM mit G01/G02/G03 in X/Y (I/J = Kreismitte relativ), um die Ecken mit Y, Z und A zusammen.
TC_POS(X, Y, A, …) setzt den Anfang einer Kontur, TC_LASER_ON(1, …) sticht ein, TC_LASER_OFF beendet die Kontur.
Bewegungen mit dem Kommentar ;LeadIn bzw. ;LeadInRounding sind die Anfahrt, „; BLOCK: Tc…“ nennt die Art
(TcToolpathCuttingContour3D Kontur, TcSeparationCutFeature Trennschnitt, TcCutupScrapFeature Restzerteilung).

Rohrkoordinaten: (y, z) = Drehung von (Y, Z) um −A (bei A = 0 liegt die Breite in y, die Höhe in z). Geprüft an
Patricks Programmen 10186133 P10/P20/P30: alle Punkte liegen auf 0,03 mm genau auf der Rohroberfläche.

„Cutting length“ der LST ist der Weg der Maschinenachsen (mit Anfahrten und dem Kopfweg um die Ecken); die
Schnittlänge am Material ist kürzer (P20: 1386 statt 1978 mm). Ergebnis je Programm siehe programme()."""
import math
import re

from . import trumpf_programm as tp

SEHNE = 0.002           # Bögen: größte Abweichung der Sehne vom Bogen [mm]
DREH = 1.0              # Bewegungen mit Drehung (Ecken): höchstens so viel Grad je Punkt
KONTUR, TRENN, REST = "kontur", "trennschnitt", "restzerteilung"
_WORT = re.compile(r"([XYZAIJ])(-?[\d.]+)")


# ------------------------------------------------------------------------------------------------ Querschnitt
class Querschnitt:
    """Außenkontur des Rohrs: Rechteck (Breite b in y, Höhe h in z, Eckenradius r) oder Kreis (Durchmesser d)."""

    def __init__(self, b=0.0, h=0.0, r=0.0, d=0.0, wand=0.0):
        self.rund = not (b > 0 and h > 0)
        self.b, self.h, self.r, self.d, self.wand = b, h, min(r, b / 2, h / 2) if not self.rund else 0.0, d, wand
        if self.rund:
            self.umfang = math.pi * d
        else:
            ay, az = b / 2 - self.r, h / 2 - self.r
            self.umfang = 4 * (ay + az) + 2 * math.pi * self.r

    def oben(self, a):
        """Höhe der oberen Seite über der Mitte bei Drehung a [Grad] (Rechteck nur in 90°-Schritten)."""
        if self.rund:
            return self.d / 2
        return self.h / 2 if round(a / 90.0) % 2 == 0 else self.b / 2

    def punkt(self, y, z):
        """(s, normale (ny, nz), abstand): Bogenlänge ab oben Mitte in Richtung +y, Flächennormale, Abstand."""
        if self.rund:
            rr = math.hypot(y, z) or 1e-12
            return (self.d / 2) * math.atan2(y, z) % self.umfang, (y / rr, z / rr), abs(rr - self.d / 2)
        ay, az, r = self.b / 2 - self.r, self.h / 2 - self.r, self.r
        cy, cz = max(-ay, min(ay, y)), max(-az, min(az, z))
        if abs(y) > ay and abs(z) > az and r > 0:         # Ecke
            v = (y - cy, z - cz)
            lv = math.hypot(*v) or 1e-12
            n = (v[0] / lv, v[1] / lv)
            ab = abs(lv - r)
        elif self.h / 2 - abs(z) <= self.b / 2 - abs(y):  # obere/untere Seite
            n, ab = (0.0, 1.0 if z >= 0 else -1.0), abs(abs(z) - self.h / 2)
        else:
            n, ab = (1.0 if y >= 0 else -1.0, 0.0), abs(abs(y) - self.b / 2)
        # Bogenlänge im Uhrzeigersinn (y nach rechts, z nach oben) ab oben Mitte
        q = math.pi / 2 * r
        stuecke = ((ay, "o"), (q, "or"), (2 * az, "r"), (q, "ur"), (2 * ay, "u"), (q, "ul"), (2 * az, "l"),
                   (q, "ol"), (ay, "o2"))
        w = math.atan2(n[1], n[0])          # Richtung der Normale
        if n == (0.0, 1.0):
            teil, lokal = ("o", y) if y >= 0 else ("o2", ay + y)
        elif n == (1.0, 0.0):
            teil, lokal = "r", az - z
        elif n == (0.0, -1.0):
            teil, lokal = "u", ay - y
        elif n == (-1.0, 0.0):
            teil, lokal = "l", az + z
        elif n[0] > 0 and n[1] > 0:
            teil, lokal = "or", r * (math.pi / 2 - w)
        elif n[0] > 0:
            teil, lokal = "ur", r * (-w)
        elif n[1] < 0:
            teil, lokal = "ul", r * (-w - math.pi / 2) if w < 0 else 0.0
        else:
            teil, lokal = "ol", r * (math.pi - w)
        s = 0.0
        for laenge, name in stuecke:
            if name == teil:
                return (s + max(0.0, min(laenge, lokal))) % self.umfang, n, ab
            s += laenge
        return 0.0, n, ab

    def ort(self, s):
        """Umkehrung von punkt(): Bogenlänge s → (y, z, (ny, nz)) auf der Außenseite."""
        s %= self.umfang
        if self.rund:
            w = s / (self.d / 2)
            return self.d / 2 * math.sin(w), self.d / 2 * math.cos(w), (math.sin(w), math.cos(w))
        ay, az, r = self.b / 2 - self.r, self.h / 2 - self.r, self.r
        q = math.pi / 2 * r

        def ecke(cy, cz, w0, t):        # Ecke ab Winkel w0 [rad] im Uhrzeigersinn um t
            w = w0 - (t / r if r else 0.0)
            return cy + r * math.cos(w), cz + r * math.sin(w), (math.cos(w), math.sin(w))
        for laenge, f in ((ay, lambda t: (t, self.h / 2, (0.0, 1.0))),
                          (q, lambda t: ecke(ay, az, math.pi / 2, t)),
                          (2 * az, lambda t: (self.b / 2, az - t, (1.0, 0.0))),
                          (q, lambda t: ecke(ay, -az, 0.0, t)),
                          (2 * ay, lambda t: (ay - t, -self.h / 2, (0.0, -1.0))),
                          (q, lambda t: ecke(-ay, -az, -math.pi / 2, t)),
                          (2 * az, lambda t: (-self.b / 2, -az + t, (-1.0, 0.0))),
                          (q, lambda t: ecke(-ay, az, math.pi, t)),
                          (ay, lambda t: (-ay + t, self.h / 2, (0.0, 1.0)))):
            if s <= laenge + 1e-12:
                return f(s)
            s -= laenge
        return 0.0, self.h / 2, (0.0, 1.0)

    def kanten(self):
        """Bogenlängen der Kantenmitten (Rechteck) für die Abwicklung: [(s, Name der folgenden Seite)]."""
        if self.rund:
            return []
        ay, az, q = self.b / 2 - self.r, self.h / 2 - self.r, math.pi / 4 * self.r
        s1 = ay + q
        s2 = s1 + q + 2 * az + q
        s3 = s2 + q + 2 * ay + q
        s4 = s3 + q + 2 * az + q
        return [(s1, "Seite +y"), (s2, "unten"), (s3, "Seite −y"), (s4, "oben")]


def rohr_punkt(y, z, a):
    """Maschinenpunkt (Y, Z) bei Drehung A [Grad] → Punkt im Rohr (y, z)."""
    u = math.radians(a)
    c, s = math.cos(u), math.sin(u)
    return y * c + z * s, -y * s + z * c


# ------------------------------------------------------------------------------------------------ NC lesen
def _art(block):
    b = block.lower()
    if "separation" in b or "cutoff" in b:
        return TRENN
    if "scrap" in b:
        return REST
    return KONTUR


def nc_wege(nc, qs):
    """Konturen aus dem NC-Text: [dict(block, art, wege [(art 'schnitt'|'anfahrt', [(x, y, z, a)])])] in
    Maschinenkoordinaten; Bögen auf SEHNE genau in Punkte zerlegt, Bewegungen mit Drehung in DREH-Schritte."""
    X = Y = A = 0.0
    Z = qs.oben(0.0)
    g = 1
    laser = False
    block = ""
    konturen = []
    akt = None
    for zeile in nc.splitlines():
        code, _, kom = zeile.partition(";")
        kom = kom.strip()
        if kom.startswith("BLOCK:"):
            block = kom[6:].strip()
            continue
        code = re.sub(r"^\s*N\d+\s*", "", code).strip()
        if not code:
            continue
        if code.startswith("TC_POS("):
            try:
                v = [float(t) for t in code[7:].split(")")[0].split(",")[:3]]
            except ValueError:
                continue
            X, Y, A = v
            Z = qs.oben(A)
            continue
        if code.startswith("TC_LASER_ON("):
            if code.startswith("TC_LASER_ON(1") and not laser:
                laser = True
                akt = dict(block=block, art=_art(block), bewegungen=[])
                konturen.append(akt)
            continue
        if code.startswith("TC_LASER_OFF"):
            laser, akt = False, None
            continue
        if code.startswith(("TC_", "AF", "DEF ", "MSG", "IF", "LOOP", "G71", "G90", "G91", "M")) or \
                ":" in code.split()[0]:
            continue
        for m in re.finditer(r"\bG0?([0-3])\b", code):
            g = int(m.group(1))
        w = {k: float(v) for k, v in _WORT.findall(re.sub(r"F=?\S*", "", code))}
        if not any(k in w for k in "XYZAIJ"):
            continue
        nx, ny, na = w.get("X", X), w.get("Y", Y), w.get("A", A)
        nz = w["Z"] if "Z" in w else (qs.oben(na) if "A" in w else Z)
        punkte = []
        if g in (2, 3) and ("I" in w or "J" in w):
            cx, cy = X + w.get("I", 0.0), Y + w.get("J", 0.0)
            r0 = math.hypot(X - cx, Y - cy)
            a0, a1 = math.atan2(Y - cy, X - cx), math.atan2(ny - cy, nx - cx)
            d = a1 - a0
            if g == 2:
                while d >= -1e-9:
                    d -= 2 * math.pi
            else:
                while d <= 1e-9:
                    d += 2 * math.pi
            schritt = 2 * math.acos(max(-1.0, 1 - SEHNE / r0)) if r0 > SEHNE else math.pi / 4
            n = max(8, math.ceil(abs(d) / schritt))
            punkte = [(cx + r0 * math.cos(a0 + d * k / n), cy + r0 * math.sin(a0 + d * k / n), Z, A)
                      for k in range(1, n + 1)]
        else:
            n = max(1, math.ceil(abs(na - A) / DREH))      # gerade ohne Drehung: nur der Endpunkt
            punkte = [(X + (nx - X) * k / n, Y + (ny - Y) * k / n, Z + (nz - Z) * k / n, A + (na - A) * k / n)
                      for k in range(1, n + 1)]
        if laser and akt is not None:
            akt["bewegungen"].append((kom, (X, Y, Z, A), punkte))
        X, Y, Z, A = nx, ny, nz, na
    # Anfahrt: alles bis zur letzten Bewegung mit ;LeadIn… (auch unkommentierte Zwischenstücke), dazu ;LeadOut…
    for k in konturen:
        bew = k.pop("bewegungen")
        rein = [i for i, b in enumerate(bew) if b[0].lower().startswith("leadin")]
        anfahr = [i <= (rein[-1] if rein else -1) or b[0].lower().startswith("leadout") for i, b in enumerate(bew)]
        wege = []
        for (kom, start, pk), an in zip(bew, anfahr):
            art = "anfahrt" if an else "schnitt"
            if not wege or wege[-1][0] != art:
                wege.append((art, [start]))
            wege[-1][1].extend(pk)
        k["wege"] = wege
    return konturen


def _laenge(pk):
    return sum(math.dist(pk[i - 1], pk[i]) for i in range(1, len(pk)))


def _halbspalt(konturen, laenge):
    """Halbe Schnittfuge: TubeCAM programmiert die Strahlmitte, um die halbe Fuge zum Abfall versetzt. Aus den
    Trennschnitten vorn und hinten und der Teillänge: (größtes x hinten − kleinstes x vorn − Länge) / 2; sonst None."""
    if not laenge:
        return None
    ringe = []
    for k in konturen:
        if k["art"] != TRENN:
            continue
        xs = [p[0] for p in k["punkte"]]
        ringe.append((sum(xs) / len(xs), min(xs), max(xs)))
    vorn = [r for r in ringe if r[0] < laenge / 2]
    hinten = [r for r in ringe if r[0] >= laenge / 2]
    if not vorn or not hinten:
        return None
    h = (max(r[2] for r in hinten) - min(r[1] for r in vorn) - laenge) / 2
    return round(h, 4) if -0.001 <= h < 0.5 else None


LUECKE = 2.0            # Kontur endet so nah am Anfang (Überschneidung mit der Anfahrt): als geschlossen behandeln [mm]


def _flach(pk, ss, u):
    """Abwicklung (x, Bogenlänge) ohne Sprung an der Naht."""
    flach = [(pk[0][0], ss[0])]
    for p, s in zip(pk[1:], ss[1:]):
        v = flach[-1][1]
        flach.append((p[0], s + round((v - s) / u) * u))
    return flach


def _verschoben(flach, abstand, zu):
    """Polylinie in der Abwicklung um abstand nach rechts (in Laufrichtung; negativ = links) versetzen."""
    n = len(flach)

    def nrm(i, j):
        dx, ds = flach[j][0] - flach[i][0], flach[j][1] - flach[i][1]
        lg = math.hypot(dx, ds) or 1e-12
        return ds / lg, -dx / lg
    out = []
    for i in range(n):
        if zu:      # geschlossen: erster und letzter Punkt sind derselbe
            a = nrm(i - 1, i) if i > 0 else nrm(n - 2, 0)
            b = nrm(i, i + 1) if i < n - 1 else nrm(0, 1)
        else:
            a = nrm(i - 1, i) if i > 0 else None
            b = nrm(i, i + 1) if i < n - 1 else None
        a, b = a or b, b or a
        m = (a[0] + b[0], a[1] + b[1])
        lm = math.hypot(*m)
        if lm < 1e-9:
            m, lm = a, 1.0
        m = (m[0] / lm, m[1] / lm)
        f = abstand / max(0.5, m[0] * a[0] + m[1] * a[1])
        out.append((flach[i][0] + f * m[0], flach[i][1] + f * m[1]))
    return out


def _raeumlich(flach, qs):
    pk, rk = [], []
    for x, s in flach:
        y, z, nn = qs.ort(s)
        pk.append((x, y, z))
        rk.append((0.0, nn[0], nn[1]))
    return pk, rk


def _versetzen(k, qs, halb, laenge):
    """Kontur um die halbe Fuge zur Teilseite versetzen (in der Abwicklung x/Bogenlänge): geschlossene Konturen
    (Abfall innen) nach außen, Ringe (Trennschnitte) zum Teil hin. Offene Konturen bleiben (Werkzeug = Fugenstreifen,
    streifen()). Ergebnis (punkte, richtung)."""
    pk, ss = k["punkte"], k["s"]
    if not halb or len(pk) < 3 or k.get("offen"):
        return pk, k["richtung"]
    u = qs.umfang
    flach = _flach(pk, ss, u)
    zu = math.dist(pk[0], pk[-1]) < 1e-3
    ring = abs(flach[-1][1] - flach[0][1]) > 0.8 * u
    if zu and not ring:
        fl = sum(flach[i - 1][0] * flach[i][1] - flach[i][0] * flach[i - 1][1] for i in range(1, len(flach)))
        seite = 1.0 if fl > 0 else -1.0       # gegen den Uhrzeigersinn: rechts ist außen
    elif ring:
        mitte = sum(p[0] for p in pk) / len(pk)
        richtung = 1.0 if flach[-1][1] > flach[0][1] else -1.0
        teil_minus = mitte > (laenge or 0) / 2      # hinteres Ende: Teil liegt bei kleinerem x
        seite = (-1.0 if teil_minus else 1.0) * richtung        # rechts = (ds, −dx): bei +s nach +x
    else:
        return pk, k["richtung"]
    return _raeumlich(_verschoben(flach, seite * halb, zu and not ring), qs)


def streifen(k, qs, halb):
    """Offene Kontur: beide Fugenränder ((punkte links, richtung), (punkte rechts, richtung)) im Abstand halb."""
    flach = _flach(k["bahn"], k["s_bahn"], qs.umfang)
    return _raeumlich(_verschoben(flach, -halb, False), qs), _raeumlich(_verschoben(flach, halb, False), qs)


KNICK = 60.0            # Richtungswechsel ab dem eine offene Kontur für die Schnittfuge geteilt wird [Grad]


def _gefaltet(flach, versetzt):
    """True, wenn ein Fugenrand gegen die Bahn zurückläuft (Rand faltet sich: ein Bahnstück zwischen zwei Knicken ist
    kürzer als die Fuge breit ist, z. B. 0,08 mm Grund einer Kerbe bei 0,2 mm Fuge). Daraus gebaut wäre das Werkzeug
    ein sich selbst schneidender Körper (Importengine 2.0, LST 10186133 P10: Nähen über 20 min, Volumen falsch)."""
    for i in range(1, len(flach)):
        bx, bs = flach[i][0] - flach[i - 1][0], flach[i][1] - flach[i - 1][1]
        vx, vs = versetzt[i][0] - versetzt[i - 1][0], versetzt[i][1] - versetzt[i - 1][1]
        if bx * vx + bs * vs < 0:
            return True
    return False


def _knicke(flach):
    out = []
    for i in range(1, len(flach) - 1):
        a = (flach[i][0] - flach[i - 1][0], flach[i][1] - flach[i - 1][1])
        b = (flach[i + 1][0] - flach[i][0], flach[i + 1][1] - flach[i][1])
        la, lb = math.hypot(*a), math.hypot(*b)
        if la < 1e-9 or lb < 1e-9:
            continue
        c = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (la * lb)))
        if math.degrees(math.acos(c)) > KNICK:
            out.append(i)
    return out


def _verlaengert(stueck, um):
    """Bahnstück an beiden Enden um um entlang der Endrichtung verlängern (die Teilstücke überlappen am Knick, die
    Fuge bleibt dort geschlossen)."""
    def weiter(p, q):
        dx, ds = p[0] - q[0], p[1] - q[1]
        lg = math.hypot(dx, ds) or 1e-12
        return (p[0] + um * dx / lg, p[1] + um * ds / lg)
    return [weiter(stueck[0], stueck[1])] + stueck[1:-1] + [weiter(stueck[-1], stueck[-2])]


def streifen_stuecke(k, qs, halb):
    """Fugenstreifen einer offenen Kontur als Liste [(links, rechts)] wie streifen(). Normalfall: ein Streifen (genau
    wie bisher). Faltet sich ein Fugenrand (_gefaltet), wird die Kontur an den Knicken (> KNICK) geteilt und jedes
    Stück an beiden Enden um die halbe Fuge verlängert; jedes Stück wird ein eigenes Werkzeug. Faltet auch ein Stück,
    bleibt es beim einen Streifen wie bisher."""
    flach = _flach(k["bahn"], k["s_bahn"], qs.umfang)
    links, rechts = _verschoben(flach, -halb, False), _verschoben(flach, halb, False)
    if len(flach) < 3 or not (_gefaltet(flach, links) or _gefaltet(flach, rechts)):
        return [(_raeumlich(links, qs), _raeumlich(rechts, qs))]
    grenzen = [0] + _knicke(flach) + [len(flach) - 1]
    out = []
    for a, b in zip(grenzen, grenzen[1:]):
        st = flach[a:b + 1]
        if len(st) < 2 or math.dist(st[0], st[-1]) < 1e-9:
            continue
        st = _verlaengert(st, halb)
        li, re = _verschoben(st, -halb, False), _verschoben(st, halb, False)
        if _gefaltet(st, li) or _gefaltet(st, re):
            return [(_raeumlich(links, qs), _raeumlich(rechts, qs))]
        out.append((_raeumlich(li, qs), _raeumlich(re, qs)))
    return out or [(_raeumlich(links, qs), _raeumlich(rechts, qs))]


def programme(text, name="LST"):
    """Je Programm der LST: dict(programm, querschnitt (Querschnitt), laenge, teile_im_programm, maschinenweg, halbspalt,
    schnittlaenge, anfahrt, restzerteilung, einstiche, abweichung, konturen [dict(nr, block, art, punkte [(x, y, z)],
    richtung [(0, ny, nz)], s [Bogenlänge], bahn [Strahlmitte], s_bahn, anfahrt [[(x, y, z, s)]], laenge, offen)]). punkte/richtung
    sind um die halbe Schnittfuge zur Teilkante versetzt (Kontur wie im Modell), bahn ist der programmierte Weg."""
    out = []
    bloecke = re.split(r"(?m)^BD\s*$", text)
    for b in bloecke:
        if "BEGIN_PROGRAMM" not in b:
            continue
        ab = {}
        for abschnitt, zeilen in tp._abschnitte(b):
            ab.setdefault(abschnitt, []).extend(zeilen)
        info = (ab.get("EINRICHTEPLAN_INFO") or [{}])[0]
        tt = (ab.get("TUBE_TECH") or [{}])[0]
        pt = ab.get("TUBE_PART_TECH") or [{}]
        h = tp._zahl(tt.get("Hoehe (Rechteckrohr)")) or 0.0
        br = tp._zahl(tt.get("Breite (Rechteckrohr)")) or 0.0
        d = tp._zahl(tt.get("(Huellkreis-)Durchmesser (Rechteck-/Rundrohr)")) or 0.0
        qs = Querschnitt(b=br, h=h, r=tp._zahl(tt.get("Eckenradius (Rechteckrohr)")) or 0.0, d=d,
                         wand=tp._zahl(tt.get("Wandstaerke")) or 0.0)
        if qs.rund and d <= 0:
            continue
        nc = b[b.find("BEGIN_PROGRAMM"):]
        nc = nc[nc.find("START_TEXT"):] if "START_TEXT" in nc else nc
        laenge = None
        for t in pt:
            laenge = tp._zahl(t.get("Work Part Length")) or tp._zahl(t.get("OriginalProgrammedTubeLength"))
            if laenge:
                break
        konturen, abw = [], 0.0
        summe = {KONTUR: 0.0, TRENN: 0.0, REST: 0.0, "anfahrt": 0.0}
        for i, k in enumerate(nc_wege(nc, qs), 1):
            pk, rk, ss, anf = [], [], [], []
            for art, punkte in k["wege"]:
                rohr = []
                for x, y, z, a in punkte:
                    py, pz = rohr_punkt(y, z, a)
                    s, n, ab_ = qs.punkt(py, pz)
                    abw = max(abw, ab_)
                    rohr.append(((x, py, pz), (0.0, n[0], n[1]), s))
                if art == "anfahrt":
                    anf.append([(p[0], p[1], p[2], s) for p, _, s in rohr])
                    summe["anfahrt"] += _laenge([p for p, _, _ in rohr])
                    continue
                for p, n, s in rohr:
                    if pk and math.dist(pk[-1], p) < 1e-6:
                        continue
                    pk.append(p)
                    rk.append(n)
                    ss.append(s)
            if len(pk) < 2:
                continue
            offen = False
            if math.dist(pk[0], pk[-1]) >= 1e-3:
                if math.dist(pk[0], pk[-1]) <= LUECKE:     # endet an der Anfahrt: schließen
                    pk.append(pk[0])
                    rk.append(rk[0])
                    ss.append(ss[0])
                elif abs(_flach(pk, ss, qs.umfang)[-1][1] - ss[0]) < 0.8 * qs.umfang:
                    offen = True
            lg = _laenge(pk)
            summe[k["art"]] += lg
            konturen.append(dict(nr=i, block=k["block"], art=k["art"], punkte=pk, richtung=rk, s=ss, anfahrt=anf,
                                 laenge=lg, offen=offen))
        if not konturen:
            continue
        halb = _halbspalt(konturen, laenge)
        for k in konturen:
            k["bahn"], k["s_bahn"] = k["punkte"], k["s"]
            if k["art"] != REST:
                k["punkte"], k["richtung"] = _versetzen(k, qs, halb, laenge)
                if k["punkte"] is not k["bahn"]:        # Länge an der Teilkante (wie die STEP-Messung)
                    neu = _laenge(k["punkte"])
                    summe[k["art"]] += neu - k["laenge"]
                    k["laenge"] = neu
                    k["s"] = [qs.punkt(p[1], p[2])[0] for p in k["punkte"]]
        out.append(dict(halbspalt=halb, programm=info.get("Programmnummer") or name, querschnitt=qs, laenge=laenge,
                        teile_im_programm=len(pt), maschinenweg=tp._zahl(info.get("Cutting length")),
                        schnittlaenge=round(summe[KONTUR] + summe[TRENN], 1), anfahrt=round(summe["anfahrt"], 1),
                        restzerteilung=round(summe[REST], 1), einstiche=len(konturen), abweichung=round(abw, 3),
                        konturen=konturen, werkstoff=tt.get("Material") or "",
                        maschine=info.get("viewer name machine") or info.get("Maschine") or ""))
    return out


def lesen(pfad):
    """programme() einer LST-Datei (UTF-8 oder Windows-1252)."""
    from pathlib import Path
    roh = Path(pfad).read_bytes()
    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError:
        text = roh.decode("cp1252", errors="replace")
    return programme(text, Path(pfad).stem)


def konturliste(prog):
    """Konturen für die Konturklassen der Kalkulation (wie die STEP-Messung): (enden [('A'|'E', Hüllmaß, Länge)],
    innen [(Hüllmaß, Länge)]). Hüllmaß innen = größere Seite der abgewickelten Kontur (Bohrung = Ø), Ende = größere
    Ausdehnung quer zum Rohr; Restzerteilung zählt nicht."""
    qs, laenge = prog["querschnitt"], prog.get("laenge") or 0.0
    enden, innen = [], []
    for k in prog["konturen"]:
        if k["art"] == REST:
            continue
        pk = k["punkte"]
        if k["art"] == TRENN:
            ys, zs = [p[1] for p in pk], [p[2] for p in pk]
            mitte = sum(p[0] for p in pk) / len(pk)
            enden.append(("A" if mitte < laenge / 2 else "E", round(max(max(ys) - min(ys), max(zs) - min(zs)), 2),
                          round(k["laenge"], 1)))
            continue
        flach = _flach(pk, k["s"], qs.umfang) if len(k["s"]) == len(pk) else [(p[0], s) for p, s in zip(pk, k["s"])]
        xs, ss = [f[0] for f in flach], [f[1] for f in flach]
        innen.append((round(max(max(xs) - min(xs), max(ss) - min(ss)), 2), round(k["laenge"], 1)))
    enden.sort(key=lambda e: e[0])
    return enden, innen
