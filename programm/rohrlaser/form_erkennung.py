"""Form einer Sonderkontur aus dem gemessenen Umriss erkennen (Patrick 25.11.2026: „Sonderkonturen müssen auch erkannt
werden“).

Eine Sonderkontur aus dem STEP-Import ist ein geschlossener Umriss [[dx längs, ds am Umfang]] auf dem abgewickelten
Mantel (step._umriss_relativ). Der Umriss bleibt maßgebend (Grundregel 100 % wie die STEP); die Erkennung beschreibt
ihn nur – für die Bemerkung im Schneidweg, die Liste und den Editor:

1. Zerlegen in Geraden und Kreisbögen (jede Stelle auf ERKENNUNG_TOL genau, wie die Gehrung),
2. Grundform aus der Folge der Stücke: Kreis, Langloch, Rechteck (mit Eckradius), Dreieck, regelmäßiges Vieleck
   (Sechseck mit Schlüsselweite …) – in beliebiger Lage (Winkel zur Rohrachse); erkannt gilt eine Grundform nur, wenn
   die ideale Form den Umriss überall auf ERKENNUNG_TOL trifft (Abstand der Kurven),
3. sonst Freiform mit Anzahl Geraden/Bögen und den Radien.

Ohne Qt, ohne Datenbank.
"""
import math

ERKENNUNG_TOL = 0.1         # mm
KREIS, LANGLOCH, RECHTECK, DREIECK, VIELECK, FREIFORM = ("Kreis", "Langloch", "Rechteck", "Dreieck", "Vieleck",
                                                         "Freiform")
BOGEN_SCHRITT_MAX = 25.0    # Grad: größter Winkelschritt zwischen zwei Punkten eines Bogens (STEP-Netz feiner)
ZERLEGEN_TOL = 0.03         # mm: Geraden/Bögen beim Zerlegen enger als die Erkennung (sonst frisst ein Bogen das
                            # Ende der Nachbargeraden); Zusammenlegen und Formvergleich mit ERKENNUNG_TOL
BOGEN_SPANNE_MIN = 8.0      # Grad: ein Bogen über weniger (ab 4 Punkten) gilt als Gerade mit Messrauschen
VIELECK_NAMEN = {4: "Quadrat", 5: "Fünfeck", 6: "Sechseck", 8: "Achteck", 10: "Zehneck", 12: "Zwölfeck"}


def _zahl(x):
    return f"{round(float(x), 1):g}".replace(".", ",")


def _punkte(umriss):
    try:
        pts = [(float(a), float(b)) for a, b in umriss or ()]
    except (TypeError, ValueError, IndexError):
        return None
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-3:
            out.append(p)
    if len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-3:
        out.pop()
    return out if len(out) >= 3 else None


def _abstand_strecke(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    lg = dx * dx + dy * dy
    t = min(max(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lg, 0.0), 1.0) if lg > 1e-18 else 0.0
    return math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1])


def _kreis_fit(pts):
    """Ausgleichskreis (Kasa, kleinste Quadrate) -> (mx, my, r) oder None."""
    n = len(pts)
    if n < 3:
        return None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    suu = suv = svv = suuu = svvv = suvv = svuu = 0.0
    for x, y in pts:
        u, v = x - mx, y - my
        suu += u * u
        svv += v * v
        suv += u * v
        suuu += u ** 3
        svvv += v ** 3
        suvv += u * v * v
        svuu += v * u * u
    det = suu * svv - suv * suv
    if abs(det) < 1e-12:
        return None
    a = 0.5 * (suuu + suvv)
    b = 0.5 * (svvv + svuu)
    uc = (a * svv - b * suv) / det
    vc = (b * suu - a * suv) / det
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    return mx + uc, my + vc, r


def _gerade_ok(pts, i, j, tol):
    a, b = pts[i], pts[j]
    return all(_abstand_strecke(pts[k], a, b) <= tol for k in range(i + 1, j))


def _bogen_ok(pts, i, j, tol):
    teil = pts[i:j + 1]
    k = _kreis_fit(teil)
    if not k or k[2] > 5000:
        return None
    mx, my, r = k
    if any(abs(math.hypot(x - mx, y - my) - r) > tol for x, y in teil):
        return None
    # gleichmäßig in eine Richtung um den Mittelpunkt (kein Zickzack)
    winkel = [math.atan2(y - my, x - mx) for x, y in teil]
    schritte = [(b - a + math.pi) % (2 * math.pi) - math.pi for a, b in zip(winkel, winkel[1:])]
    if schritte and not (all(s > -1e-6 for s in schritte) or all(s < 1e-6 for s in schritte)):
        return None
    # echter Bogen: kleine, gleichmäßige Schritte (sonst passen z. B. die Ecken eines Rechtecks auf einen Kreis oder
    # eine Gerade mit dem Anfang des nächsten Bogens auf einen großen Kreis)
    if max(abs(s) for s in schritte) > math.radians(BOGEN_SCHRITT_MAX):
        return None
    sehnen = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(teil, teil[1:])]
    if max(sehnen) > 3 * sorted(sehnen)[(len(sehnen) - 1) // 2] + tol:
        return None
    if abs(sum(schritte)) < math.radians(BOGEN_SPANNE_MIN) and len(teil) > 3:
        return None                         # fast gerade (großer Radius über ein kurzes Stück): keine Bogenform
    return mx, my, r, sum(schritte)


def zerlegen(umriss, tol=ERKENNUNG_TOL, tol_zus=None):
    """Umriss -> Stücke [dict(art='Gerade', a, b, laenge, winkel) | dict(art='Bogen', m, r, spanne, a, b)] in
    Umlaufrichtung; None ohne brauchbaren Umriss."""
    pts = _punkte(umriss)
    if not pts:
        return None
    n = len(pts)

    def knick(i):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        w1 = math.atan2(b[1] - a[1], b[0] - a[0])
        w2 = math.atan2(c[1] - b[1], c[0] - b[0])
        return abs((w2 - w1 + math.pi) % (2 * math.pi) - math.pi)
    start = max(range(n), key=knick)
    def zerlege_ab(start):
        ring = pts[start:] + pts[:start] + [pts[start]]
        m = len(ring) - 1
        # je Startpunkt die größte Reichweite als Gerade bzw. als Bogen, dann die Zerlegung mit den wenigsten Stücken
        # (dynamische Programmierung; gierig vorwärts teilt sonst Bögen am Übergang zur Geraden)
        weit_g, weit_b = [0] * m, [0] * m
        for i in range(m):
            jg = i + 1
            while jg + 1 <= m and _gerade_ok(ring, i, jg + 1, tol):
                jg += 1
            weit_g[i] = jg
            jb, fehl, j = i, 0, i + 2
            while j <= m:
                if _bogen_ok(ring, i, j, tol):
                    jb, fehl = j, 0
                else:
                    fehl += 1
                    if fehl > 3:
                        break
                j += 1
            weit_b[i] = jb
        best = [0] + [None] * m                 # (Stücke, −Punkte auf Bögen) bis Punkt j: Bögen behalten ihre Punkte
        wahl = [None] * (m + 1)
        for i in range(m):
            if best[i] is None:
                continue
            for j in range(i + 1, max(weit_g[i], weit_b[i]) + 1):
                gerade = j <= weit_g[i]
                if not gerade and not (j >= i + 2 and _bogen_ok(ring, i, j, tol)):
                    continue
                wert = (best[i][0] + 1, best[i][1] - (j - i if not gerade else 0)) if best[i] else \
                    (1, -(j - i) if not gerade else 0)
                if best[j] is None or wert < best[j]:
                    best[j], wahl[j] = wert, (i, gerade)
        if best[m] is None:
            return None, None
        teile, j = [], m
        while j > 0:
            i, gerade = wahl[j]
            teile.append((i, j, gerade))
            j = i
        stuecke = []
        for i, j, gerade in reversed(teile):
            if gerade:
                a_, b_ = ring[i], ring[j]
                stuecke.append(dict(art="Gerade", a=a_, b=b_, laenge=math.hypot(b_[0] - a_[0], b_[1] - a_[1]),
                                    winkel=math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0])), n=j - i,
                                    punkte=ring[i:j + 1]))
            else:
                mx, my, r, sp = _bogen_ok(ring, i, j, tol)
                stuecke.append(dict(art="Bogen", m=(mx, my), r=r, spanne=math.degrees(sp), a=ring[i], b=ring[j],
                                    n=j - i, punkte=ring[i:j + 1]))
        return stuecke, teile[-1][1]

    stuecke, erstes = zerlege_ab(start)
    if stuecke and len(stuecke) > 1 and stuecke[0]["art"] == stuecke[-1]["art"]:
        # Anfang mitten in einem Stück: an der ersten Grenze neu beginnen
        st2, _ = zerlege_ab((start + erstes) % n)
        if st2 and len(st2) < len(stuecke):
            stuecke = st2
    if not stuecke:
        return None
    tz = tol_zus or tol
    return _boegen_ausdehnen(_zusammenfassen(stuecke, tz), tz)


def _zusammenfassen(st, tol):
    """Nachbarstücke derselben Geraden bzw. desselben Kreises zusammenlegen (auch über den Anfang hinweg)."""
    def gleich(x, y):
        if x["art"] != y["art"]:
            return False
        if x["art"] == "Gerade":
            return _abstand_strecke(x["b"], x["a"], y["b"]) <= tol and \
                abs((x["winkel"] - y["winkel"] + 180) % 360 - 180) < 2.0
        if x.get("punkte") and y.get("punkte"):     # derselbe Kreis, wenn alle Punkte zusammen einen Bogen bilden
            p = list(x["punkte"]) + list(y["punkte"][1:])
            return x["spanne"] * y["spanne"] > 0 and _bogen_ok(p, 0, len(p) - 1, tol) is not None
        return math.hypot(x["m"][0] - y["m"][0], x["m"][1] - y["m"][1]) <= 2 * tol and abs(x["r"] - y["r"]) <= tol \
            and x["spanne"] * y["spanne"] > 0

    def eins(x, y):
        if x["art"] == "Gerade":
            a, b = x["a"], y["b"]
            return dict(art="Gerade", a=a, b=b, laenge=math.hypot(b[0] - a[0], b[1] - a[1]),
                        winkel=math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), n=x["n"] + y["n"],
                        punkte=list(x.get("punkte") or ()) + list((y.get("punkte") or ())[1:]))
        if x.get("punkte") and y.get("punkte"):
            p = list(x["punkte"]) + list(y["punkte"][1:])
            b = _bogen_ok(p, 0, len(p) - 1, tol)
            if b:
                return dict(art="Bogen", m=(b[0], b[1]), r=b[2], spanne=math.degrees(b[3]), a=x["a"], b=y["b"],
                            n=x["n"] + y["n"], punkte=p)
        g = x["n"] + y["n"]
        return dict(art="Bogen", m=((x["m"][0] * x["n"] + y["m"][0] * y["n"]) / g,
                                    (x["m"][1] * x["n"] + y["m"][1] * y["n"]) / g),
                    r=(x["r"] * x["n"] + y["r"] * y["n"]) / g, spanne=x["spanne"] + y["spanne"], a=x["a"], b=y["b"],
                    n=g)
    out = []
    for s in st:
        if out and gleich(out[-1], s):
            out[-1] = eins(out[-1], s)
        else:
            out.append(s)
    while len(out) > 1 and gleich(out[-1], out[0]):
        out[0] = eins(out.pop(), out[0])
    return out


def _auf_kreis(p, b, tol):
    return abs(math.hypot(p[0] - b["m"][0], p[1] - b["m"][1]) - b["r"]) <= tol


def _bogen_bis(b, p, vorn):
    """Bogen b bis zum Punkt p verlängern (vorn = am Anfang a, sonst am Ende b)."""
    mx, my = b["m"]
    w = lambda q: math.atan2(q[1] - my, q[0] - mx)          # noqa: E731
    vz = 1 if b["spanne"] >= 0 else -1
    if vorn:
        d = (w(b["a"]) - w(p)) * vz % (2 * math.pi)
        d = d if d < math.pi else 0.0
        return dict(b, a=p, spanne=b["spanne"] + vz * math.degrees(d), n=b["n"] + 1)
    d = (w(p) - w(b["b"])) * vz % (2 * math.pi)
    d = d if d < math.pi else 0.0
    return dict(b, b=p, spanne=b["spanne"] + vz * math.degrees(d), n=b["n"] + 1)


def _boegen_ausdehnen(st, tol):
    """Eine Gerade nimmt beim Zerlegen gern den letzten Punkt eines Bogens mit (liegt auf tol genau auf beiden): kurze
    Geradenstücke, die ganz auf dem Kreis des Nachbarbogens liegen, gehören zum Bogen; der Bogen reicht bis zum
    Berührpunkt (Ende der Geraden, das auf dem Kreis liegt)."""
    n = len(st)
    if n < 2:
        return st
    out = [dict(x) for x in st]
    for i in range(n):
        g = out[i]
        if g["art"] != "Gerade":
            continue
        vor, nach = out[i - 1], out[(i + 1) % n]
        for nb, vorn in ((vor, False), (nach, True)):
            if nb["art"] != "Bogen":
                continue
            if _auf_kreis(g["a"], nb, tol) and _auf_kreis(g["b"], nb, tol) and g["laenge"] < 0.5 * nb["r"]:
                g["weg"] = True
                j = out.index(nb)
                out[j] = _bogen_bis(nb, g["a"] if vorn else g["b"], vorn)
                break
    out = [x for x in out if not x.get("weg")]
    return _zusammenfassen(out, tol) if len(out) != n else out


# ------------------------------------------------------------------ ideale Formen und Vergleich
def _abstand_kurven(pa, pb):
    """Größter Abstand zweier geschlossener Linienzüge (Hausdorff) [mm]."""
    def eins(a, b):
        ring = b + [b[0]]
        return max(min(_abstand_strecke(p, q, r) for q, r in zip(ring, ring[1:])) for p in a)
    return max(eins(pa, pb), eins(pb, pa))


def _langloch(mx, my, laenge, breite, winkel, n=24):
    r = breite / 2
    h = max(laenge / 2 - r, 0.0)
    c, s = math.cos(math.radians(winkel)), math.sin(math.radians(winkel))
    out = []
    for seite in (1, -1):
        for i in range(n + 1):
            t = math.radians(-90 + 180 * i / n) if seite == 1 else math.radians(90 + 180 * i / n)
            x, y = seite * h + r * math.cos(t), r * math.sin(t)
            out.append((mx + x * c - y * s, my + x * s + y * c))
    return out


def _rechteck(mx, my, laenge, breite, winkel, r=0.0, n=12):
    c, s = math.cos(math.radians(winkel)), math.sin(math.radians(winkel))
    hx, hy = laenge / 2 - r, breite / 2 - r
    out = []
    for k, (ex, ey) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        if r > 0:
            for i in range(n + 1):
                t = math.radians(90 * k + 90 * i / n)
                out.append((ex * hx + r * math.cos(t), ey * hy + r * math.sin(t)))
        else:
            out.append((ex * hx, ey * hy))
    return [(mx + x * c - y * s, my + x * s + y * c) for x, y in out]


def _geraden_winkel(g):
    """Richtung einer Geraden [°] aus dem Ausgleich über ihre inneren Punkte (Hauptachse); ohne Punkte a -> b."""
    p = g.get("punkte") or ()
    p = p[1:-1] if len(p) > 6 else p        # Endpunkte liegen oft schon auf dem Nachbarbogen
    if len(p) < 3:
        return g["winkel"]
    mx, my = _mitte(p)
    sxx = sum((x - mx) ** 2 for x, _ in p)
    syy = sum((y - my) ** 2 for _, y in p)
    sxy = sum((x - mx) * (y - my) for x, y in p)
    w = math.degrees(0.5 * math.atan2(2 * sxy, sxx - syy))
    return w if abs((w - g["winkel"] + 90) % 180 - 90) < 45 else w + 180


def _richtung_mod(geraden, mod):
    """Gemeinsame Richtung mehrerer Geraden modulo mod (90 = Rechteck, 180 = parallel), nach Länge gewichtet."""
    f = 360.0 / mod
    sx = sum(g["laenge"] * math.cos(math.radians(_geraden_winkel(g) * f)) for g in geraden)
    sy = sum(g["laenge"] * math.sin(math.radians(_geraden_winkel(g) * f)) for g in geraden)
    w = math.degrees(math.atan2(sy, sx)) / f
    w0 = geraden[0]["winkel"]
    return w + mod * round((w0 - w) / mod)


def _winkel_varianten(w):
    """Lage zuerst glatt (ganze Grad bis 0,2° daneben, halbe Grad bis 0,1°), dann wie gemessen – genommen wird die
    erste, die passt."""
    out = []
    for x, weit in ((round(w), 0.2), (round(w * 2) / 2, 0.1), (round(w, 2), 1.0)):
        if abs(x - w) <= weit and all(abs(x - y) > 1e-9 for y in out):    # nur Messrauschen glätten
            out.append(float(x))
    return out


def _mitte(pts):
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _lage(w):
    """Winkel zur Rohrachse (dx) in [0, 180) als Text-Zusatz."""
    w = w % 180
    w = 0.0 if min(w, 180 - w) < 0.25 else w
    return "" if w == 0 else (", quer" if abs(w - 90) < 0.25 else f", {_zahl(w)}° zur Achse")


def erkennen(umriss, tol=ERKENNUNG_TOL):
    """Form der Sonderkontur: dict(typ, text, abweichung, Maße …) oder None (zu wenig Punkte)."""
    pts = _punkte(umriss)
    st = zerlegen(umriss, min(tol, ZERLEGEN_TOL), tol)
    if not pts or not st:
        return None
    geraden = [s for s in st if s["art"] == "Gerade"]
    boegen = [s for s in st if s["art"] == "Bogen"]
    folge = "".join("G" if s["art"] == "Gerade" else "B" for s in st)
    kand = []
    # Kreis
    if not geraden and boegen:
        k = _kreis_fit(pts)
        if k:
            mx, my, r = k
            ideal = [(mx + r * math.cos(2 * math.pi * i / 180), my + r * math.sin(2 * math.pi * i / 180))
                     for i in range(180)]
            kand.append((dict(typ=KREIS, durchmesser=round(2 * r, 2), text=f"Kreis Ø{_zahl(2 * r)}"), ideal))
    # Langloch: Gerade, Halbkreis, Gerade, Halbkreis (Maße aus den Bogenmitten, robust gegen Punkte am Übergang)
    if folge in ("GBGB", "BGBG") and all(abs(abs(b["spanne"]) - 180) < 30 for b in boegen):
        r = sum(b["r"] for b in boegen) / 2
        (x1, y1), (x2, y2) = boegen[0]["m"], boegen[1]["m"]
        lg = math.hypot(x2 - x1, y2 - y1) + 2 * r
        w_fit = _richtung_mod(geraden, 180) if lg > 2 * r + 1e-6 else geraden[0]["winkel"]
        for w in _winkel_varianten(w_fit):
            kand.append((dict(typ=LANGLOCH, laenge=round(lg, 2), breite=round(2 * r, 2), winkel=round(w % 180, 2),
                              text=f"Langloch {_zahl(lg)} × {_zahl(2 * r)}{_lage(w)}"),
                         _langloch((x1 + x2) / 2, (y1 + y2) / 2, lg, 2 * r, w)))
    # Rechteck (scharf oder mit Eckradien): Maße aus dem Abstand gegenüberliegender Seiten
    if folge == "GGGG" or folge in ("GBGBGBGB", "BGBGBGBG") and all(abs(abs(b["spanne"]) - 90) < 20
                                                                     for b in boegen):
        r = sum(b["r"] for b in boegen) / len(boegen) if boegen else 0.0
        w_roh = geraden[0]["winkel"]
        if all(abs((g["winkel"] - w_roh + 45) % 90 - 45) < 1.5 for g in geraden):
            w_fit = _richtung_mod(geraden, 90)      # Lage aus allen Geraden (Ausgleich über ihre Punkte)
            for w0 in _winkel_varianten(w_fit):
                # Maße und Mitte aus der Ausdehnung des Umrisses quer zu den Seiten (die flachen Seiten liegen
                # außen, auch mit Eckradien; Geraden und Bogenmitten aus wenigen Punkten sind ungenauer)
                c_, s_ = math.cos(math.radians(w0)), math.sin(math.radians(w0))
                pa = [x * c_ + y * s_ for x, y in pts]
                pb = [-x * s_ + y * c_ for x, y in pts]
                l1, l2 = max(pa) - min(pa), max(pb) - min(pb)
                ma, mb = (max(pa) + min(pa)) / 2, (max(pb) + min(pb)) / 2
                if not boegen:                      # scharfe Ecken: Seitenlängen zwischen den Ecken genauer
                    seiten = [(g["laenge"], abs((g["winkel"] - w0 + 90) % 180 - 90) < 45) for g in geraden]
                    la = [x for x, parallel in seiten if parallel]
                    lb = [x for x, parallel in seiten if not parallel]
                    if len(la) == 2 and len(lb) == 2:
                        l1, l2 = sum(la) / 2, sum(lb) / 2
                mx, my = ma * c_ - mb * s_, ma * s_ + mb * c_
                wl = w0
                if l2 > l1:
                    l1, l2, wl = l2, l1, w0 + 90
                name = "Quadrat" if abs(l1 - l2) <= tol else RECHTECK
                masse = f"{_zahl(l1)}" if name == "Quadrat" else f"{_zahl(l1)} × {_zahl(l2)}"
                for rr in sorted({round(r, 2), round(r * 2) / 2, round(r * 10) / 10} if boegen else {0.0},
                                 key=lambda x: abs(x - round(x * 2) / 2)):
                    kand.append((dict(typ=RECHTECK, laenge=round(l1, 2), breite=round(l2, 2), radius=round(rr, 2),
                                      winkel=round(wl % 180, 2),
                                      text=f"{name} {masse}" + (f" R{_zahl(rr)}" if rr > 0.05 else "") + _lage(wl)),
                                 _rechteck(mx, my, l1, l2, wl, rr if rr > 0.05 else 0.0)))
    # Dreieck / Vieleck aus Geraden (Ecken ggf. gerundet)
    if geraden and (not boegen or (len(boegen) == len(geraden) and folge in ("GB" * len(geraden),
                                                                              "BG" * len(geraden)))):
        n = len(geraden)
        laengen = [g["laenge"] for g in geraden]
        r = sum(b["r"] for b in boegen) / len(boegen) if boegen else 0.0
        if n == 3:
            seiten = sorted((x + 2 * r * math.tan(math.radians(60)) if boegen else x) for x in laengen)
            text = "Dreieck " + " × ".join(_zahl(x) for x in seiten) + (f" R{_zahl(r)}" if r > 0.05 else "")
            kand.append((dict(typ=DREIECK, seiten=[round(x, 2) for x in seiten], radius=round(r, 2), text=text),
                         None))
        elif n >= 5 and max(laengen) - min(laengen) <= 4 * tol:
            innen = 180 - 360 / n
            ext = 2 * r / math.tan(math.radians(innen / 2)) if boegen else 0.0
            seite = sum(laengen) / n + ext
            name = VIELECK_NAMEN.get(n, f"{n}-Eck")
            apo = seite / (2 * math.tan(math.pi / n))
            text = f"{name} SW {_zahl(2 * apo)}" if n % 2 == 0 else f"{name} Seite {_zahl(seite)}"
            kand.append((dict(typ=VIELECK, ecken=n, seite=round(seite, 2), schluesselweite=round(2 * apo, 2),
                              radius=round(r, 2), text=text + (f" R{_zahl(r)}" if r > 0.05 else "")), None))
    for form, ideal in kand:
        x = _abstand_kurven(pts, ideal) if ideal else _stueck_abweichung(pts, st)
        if x <= tol:
            form["abweichung"] = round(x, 3)
            return form
    radien = sorted({round(b["r"], 1) for b in boegen})
    teile = []
    if geraden:
        teile.append(f"{len(geraden)} {'Gerade' if len(geraden) == 1 else 'Geraden'}")
    if boegen:
        teile.append(f"{len(boegen)} {'Bogen' if len(boegen) == 1 else 'Bögen'}"
                     + (" (" + ", ".join(f"R{_zahl(r)}" for r in radien[:4]) + (" …" if len(radien) > 4 else "")
                        + ")" if radien else ""))
    return dict(typ=FREIFORM, geraden=len(geraden), boegen=len(boegen), radien=radien,
                text=f"Freiform: {', '.join(teile)}", abweichung=round(_stueck_abweichung(pts, st), 3))


def _stueck_abweichung(pts, st):
    """Größte Abweichung des Umrisses von seinen Stücken (Geraden als Strecke, Bögen als Kreis)."""
    groesst = 0.0
    for p in pts:
        best = float("inf")
        for s in st:
            if s["art"] == "Gerade":
                best = min(best, _abstand_strecke(p, s["a"], s["b"]))
            else:
                best = min(best, abs(math.hypot(p[0] - s["m"][0], p[1] - s["m"][1]) - s["r"]))
        groesst = max(groesst, best)
    return groesst


def text(e):
    """Bemerkung zur Sonderkontur: erkannte Form + Hinweis, dass der Umriss wie in der STEP geschnitten wird."""
    f = e.get("form_erkannt") if isinstance(e, dict) else None
    return f"{f['text']}: Umriss wie STEP" if isinstance(f, dict) and f.get("text") else ""
