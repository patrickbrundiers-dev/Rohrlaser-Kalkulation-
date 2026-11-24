"""Ausschnitt mit einstellbarer Tiefe (Patrick 12.11.2026, CAD-Entwicklungsplan Paket 4): eine Ausklinkung, deren
Tiefe eingestellt wird. Die Kontur (Rechteck, rund, Langloch, Polygon) liegt auf einer Fläche des Profils und wird
senkrecht zu dieser Fläche um die Tiefe t in das Profil geführt (ein Prisma). Der Laser trennt eine Wand immer ganz;
gerechnet wird deshalb, wo dieses Prisma die Außenhaut des Profils trifft:

    auf der gewählten Fläche        die Kontur, an den Flächenkanten abgeschnitten
    auf den Seitenwänden            ein Streifen von der Kante bis zur Tiefe t (so breit wie die Kontur an der Kante)
    auf dem Rundrohr                die Kontur bis zu der Stelle am Umfang, die t unter dem Scheitel liegt
    auf der Gegenwand               erst ab t = ganze Höhe (vollständiger Durchbruch)

Ein Ausschnitt mit 5 mm Tiefe wird damit nie von selbst zum Durchbruch. Was der Laser nicht kann, wird mit Grund
abgelehnt (ValueError): Tiefe kleiner als die Wand (Tasche, nur gefräst), Ende mitten in der Gegenwand, Trennen des
ganzen Teils, Sackloch im Vollmaterial, ungültige Kontur.

Ohne Qt. Ergebnis von umriss(): dict(umriss [[dx längs, dq am Umfang]] um die Mitte der Kontur, laenge, huelle,
tiefe_ist, beide, hinweise)."""
import math

FORMEN = ("Rechteck", "Rund", "Langloch", "Polygon")
EPS = 1e-6
SCHMAL = 0.05           # schmaler als das gilt ein Streifen als nicht vorhanden (Kontur berührt die Kante nur)
RUND_GRAD = 2.0         # Rundrohr: Umfang in Stücken von 2°


def _z(x):
    try:
        return float(str(x).replace(",", ".")) if x not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _zahl(x):
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def form(e):
    f = e.get("kontur_form")
    return f if f in FORMEN else FORMEN[0]


def _schneidet_sich(pk):
    """Polygon schneidet sich selbst (zwei nicht benachbarte Kanten kreuzen sich)."""
    def seite(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    n = len(pk)
    for i in range(n):
        a, b = pk[i], pk[(i + 1) % n]
        for j in range(i + 2, n):
            if (j + 1) % n == i:
                continue
            c, d = pk[j], pk[(j + 1) % n]
            if seite(a, b, c) * seite(a, b, d) < -1e-12 and seite(c, d, a) * seite(c, d, b) < -1e-12:
                return True
    return False


def basis(e, n=72):
    """Kontur [(x längs, y quer)] um ihre Mitte, ohne Drehung. ValueError mit Grund bei fehlenden Maßen oder
    ungültiger Kontur (zu wenige Punkte, schneidet sich selbst, keine Fläche)."""
    f = form(e)
    b, h, r = _z(e.get("b")), _z(e.get("h")), _z(e.get("eckradius"))
    if f == "Rund":
        if b <= 0:
            raise ValueError("Ausschnitt mit Tiefe: Ø (Maß 1) eingeben.")
        return [(b / 2 * math.cos(2 * math.pi * i / n), b / 2 * math.sin(2 * math.pi * i / n)) for i in range(n)]
    if f == "Langloch":
        if h <= 0 or b < h:
            raise ValueError("Ausschnitt mit Tiefe: Langloch Länge (Maß 1) ≥ Breite (Maß 2) > 0 eingeben.")
        rr, m, k = h / 2, (b - h) / 2, n // 2
        pts = [(m + rr * math.cos(math.radians(-90 + 180 * i / k)), rr * math.sin(math.radians(-90 + 180 * i / k)))
               for i in range(k + 1)]
        return pts + [(-m + rr * math.cos(math.radians(90 + 180 * i / k)),
                       rr * math.sin(math.radians(90 + 180 * i / k))) for i in range(k + 1)]
    if f == "Polygon":
        from .schneidweg import punkte
        try:
            pk = punkte(e.get("eckpunkte"))
        except ValueError:
            raise ValueError("Ausschnitt mit Tiefe: Die Eckpunkte sind nicht lesbar (x,y; x,y; …).") from None
        if len(pk) >= 2 and math.dist(pk[0], pk[-1]) < 1e-9:
            pk = pk[:-1]
        if len(pk) < 3:
            raise ValueError("Ausschnitt mit Tiefe: Die Kontur ist offen (mindestens 3 Eckpunkte, die eine "
                             "geschlossene Fläche bilden).")
        if _schneidet_sich(pk):
            raise ValueError("Ausschnitt mit Tiefe: Die Kontur schneidet sich selbst und ist damit ungültig.")
        fl = sum(pk[i][0] * pk[(i + 1) % len(pk)][1] - pk[(i + 1) % len(pk)][0] * pk[i][1] for i in range(len(pk)))
        if abs(fl) < 1e-6:
            raise ValueError("Ausschnitt mit Tiefe: Die Kontur hat keine Fläche (alle Punkte auf einer Linie).")
        cx = (max(x for x, _ in pk) + min(x for x, _ in pk)) / 2
        cy = (max(y for _, y in pk) + min(y for _, y in pk)) / 2
        return [(x - cx, y - cy) for x, y in pk]
    if b <= 0 or h <= 0:
        raise ValueError("Ausschnitt mit Tiefe: Länge längs (Maß 1) und Breite quer (Maß 2) eingeben.")
    if 2 * r > min(b, h) + 1e-9:
        raise ValueError("Ausschnitt mit Tiefe: Eckradius höchstens halbe Seite.")
    if r <= 0:
        return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]
    pts = []
    for cx, cy, w0 in ((b / 2 - r, -h / 2 + r, -90), (b / 2 - r, h / 2 - r, 0), (-b / 2 + r, h / 2 - r, 90),
                       (-b / 2 + r, -h / 2 + r, 180)):
        pts += [(cx + r * math.cos(math.radians(w0 + 90 * i / 6)), cy + r * math.sin(math.radians(w0 + 90 * i / 6)))
                for i in range(7)]
    return pts


def kontur_punkte(e):
    """Kontur mit Drehwinkel (+ = gegen den Uhrzeiger von außen), wie sie auf der Fläche liegt."""
    pts = basis(e)
    w = _z(e.get("drehung"))
    if w and form(e) != "Rund":
        c, s = math.cos(math.radians(w)), math.sin(math.radians(w))
        pts = [(x * c - y * s, x * s + y * c) for x, y in pts]
    return pts


def _strecken(pk, y):
    """x-Bereiche [(x0, x1)] des Polygons auf der Höhe y."""
    xs = []
    n = len(pk)
    for i in range(n):
        (x0, y0), (x1, y1) = pk[i], pk[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2) if xs[i + 1] - xs[i] > 1e-9]


class _Haut:
    """Außenhaut des Profils als Stücke entlang des Umfangs, von der Mitte der gewählten Fläche aus gemessen:
    (s0, s1, y0, y1, z0, z1) mit y = Lage quer in der Ebene der Fläche, z = Tiefe unter der Fläche. zu = Umfang
    geschlossen (Rohr), wand = Wand unter der Fläche, hoehe = ganze Höhe unter der Fläche, gegen = es gibt eine
    Gegenwand in dieser Höhe, frei = Stellen s an freien Kanten (dort ist der Ausschnitt offen)."""

    def __init__(self, qs, seite):
        self.stuecke, self.frei, self.zu, self.gegen, self.massiv, self.schmal = [], [], False, False, False, False
        self.wand = qs.wand if qs.form in ("Rundrohr", "Quadratrohr", "Rechteckrohr") or not qs.dicke else qs.dicke
        if qs.r:
            R, k = qs.r, int(round(360 / RUND_GRAD))
            for i in range(-k // 2, k // 2):
                p0, p1 = math.radians(i * RUND_GRAD), math.radians((i + 1) * RUND_GRAD)
                self.stuecke.append((R * p0, R * p1, R * math.sin(p0), R * math.sin(p1), R * (1 - math.cos(p0)),
                                     R * (1 - math.cos(p1))))
            self.zu, self.gegen, self.hoehe, self.umfang, self.breite = True, True, 2 * R, qs.umfang, 2 * R
            return
        fl = qs.flaechen
        if not fl:
            raise ValueError("Ausschnitt mit Tiefe: Für dieses Profil sind keine Flächen bekannt.")
        h = qs.flaeche(seite) if seite in [f.name for f in fl] else fl[0]
        self.breite, self.umfang = h.breite, qs.umfang
        i0 = fl.index(h)
        s_mitte = sum(f.breite for f in fl[:i0]) + h.breite / 2

        def lage(p):
            du, dv = p[0] - h.mitte[0], p[1] - h.mitte[1]
            return du * h.dir[0] + dv * h.dir[1], -(du * h.n[0] + dv * h.n[1])
        nah = lambda a, b: math.dist(a, b) < 1e-6          # noqa: E731
        self.zu = len(fl) == 4 and all(nah(fl[i].p1, fl[(i + 1) % 4].p0) for i in range(4))
        self.massiv = qs.form == "Flachstahl"
        if self.massiv:
            self.schmal = h.name in ("vorne", "hinten")
            self.hoehe = qs.B if self.schmal else qs.H
            if self.schmal:             # von der Schmalseite: der Laser schneidet die Kerbe von der Breitseite
                g = fl[(i0 + 1) % 4]
                (y0, z0), (y1, z1) = lage(g.p0), lage(g.p1)
                self.stuecke = [(h.breite / 2, h.breite / 2 + g.breite, y0, y1, z0, z1)]
                self.frei = [h.breite / 2]
            else:
                self.stuecke = [(-h.breite / 2, h.breite / 2, -h.breite / 2, h.breite / 2, 0.0, 0.0)]
                self.frei = [-h.breite / 2, h.breite / 2]
            self.zu = False
            return
        # zusammenhängende Flächen vor und hinter der gewählten (offene Profile: nur soweit sie aneinander stoßen)
        kette, s = [(h, -h.breite / 2)], h.breite / 2
        j = i0
        while True:
            k = (j + 1) % len(fl) if self.zu else j + 1
            if k >= len(fl) or k == i0 or not nah(fl[j].p1, fl[k].p0):
                break
            kette.append((fl[k], s))
            s += fl[k].breite
            j = k
        ende_plus = s
        j, s = i0, -h.breite / 2
        while not self.zu:
            k = j - 1
            if k < 0 or not nah(fl[k].p1, fl[j].p0):
                break
            s -= fl[k].breite
            kette.append((fl[k], s))
            j = k
        for f, s0 in kette:
            (y0, z0), (y1, z1) = lage(f.p0), lage(f.p1)
            self.stuecke.append((s0, s0 + f.breite, y0, y1, z0, z1))
        self.stuecke.sort()
        if not self.zu:
            self.frei = [s, ende_plus]
        self.hoehe = max(max(st[4], st[5]) for st in self.stuecke)
        if self.hoehe < 1e-6:           # nur die Fläche selbst bekannt (I-/H-Träger, T-Profil): Dicke als Höhe
            self.hoehe = self.wand
        self.gegen = any(abs(st[4] - self.hoehe) < 1e-6 and abs(st[5] - self.hoehe) < 1e-6 for st in self.stuecke)
        self.s_mitte = s_mitte


def umriss(qs, e):
    """Umriss des Ausschnitts mit Tiefe für die Konturzeile e auf dem Querschnitt qs (skizze.Querschnitt).
    Ergebnis dict(umriss, laenge, huelle, tiefe_ist, beide, hinweise); ValueError mit Grund, wenn der Ausschnitt nicht
    ausführbar ist."""
    pk = kontur_punkte(e)
    t = _z(e.get("tiefe"))
    if t <= 0:
        raise ValueError("Ausschnitt mit Tiefe: Tiefe (Maß 3) eingeben.")
    haut = _Haut(qs, e.get("seite"))
    q = 0.0 if qs.r else _z(e.get("q"))
    um = bool(e.get("umgekehrt"))
    H, wand = haut.hoehe, haut.wand
    if haut.massiv and not haut.schmal and t < H - EPS:
        raise ValueError(f"Ausschnitt mit Tiefe: {_zahl(t)} mm Tiefe in {_zahl(H)} mm Vollmaterial wäre eine Tasche "
                         "(Sackloch). Der Laser trennt das Material immer ganz: Tiefe mindestens die Dicke eingeben "
                         "oder den Ausschnitt von der Schmalseite setzen.")
    if wand and t < wand - EPS and not haut.schmal:
        raise ValueError(f"Ausschnitt mit Tiefe: {_zahl(t)} mm Tiefe ist weniger als die Wand ({_zahl(wand)} mm). "
                         "Der Laser trennt die Wand immer ganz, eine Tasche in der Wand ist nur gefräst möglich.")
    if haut.schmal and t >= H - EPS:
        raise ValueError(f"Ausschnitt mit Tiefe: {_zahl(t)} mm Tiefe trennt das Teil über die ganze Breite "
                         f"({_zahl(H)} mm). Dafür einen Trennschnitt (zwei Teile) verwenden.")
    stuecke = [(s0, s1, y0, y1, (H - z0 if um else z0), (H - z1 if um else z1))
               for s0, s1, y0, y1, z0, z1 in haut.stuecke]
    if haut.schmal:                     # Kontur muss die Schmalseite ganz überdecken (sonst Sackloch)
        halb = haut.breite / 2
        if not _strecken(pk, halb - EPS - q) or not _strecken(pk, -halb + EPS - q):
            raise ValueError("Ausschnitt mit Tiefe: Auf der Schmalseite muss die Kontur über die ganze Dicke reichen "
                             "(sonst entsteht ein Sackloch, das der Laser nicht schneidet).")
    ys = sorted({round(y + q, 9) for _, y in pk})
    # Stützstellen entlang des Umfangs: Stückgrenzen, Höhen der Konturpunkte, Tiefengrenze
    felder = []
    for s0, s1, y0, y1, z0, z1 in stuecke:
        st = {s0, s1}
        if abs(y1 - y0) > 1e-12:
            for y in ys:
                f = (y - y0) / (y1 - y0)
                if 0 < f < 1:
                    st.add(s0 + f * (s1 - s0))
        if abs(z1 - z0) > 1e-12:
            f = (t - z0) / (z1 - z0)
            if 0 < f < 1:
                st.add(s0 + f * (s1 - s0))
        st = sorted(st)
        for a, b in zip(st, st[1:]):
            if b - a < 1e-9:
                continue

            def bei(s, s0=s0, s1=s1, y0=y0, y1=y1, z0=z0, z1=z1):
                f = (s - s0) / (s1 - s0)
                return y0 + f * (y1 - y0), z0 + f * (z1 - z0)
            ym, zm = bei((a + b) / 2)
            if zm > t + EPS:
                continue
            fest = abs(y1 - y0) < 1e-12         # Seitenwand: Kontur an der Kante, knapp innen gemessen
            if fest:
                innen = y0 - math.copysign(EPS, y0)
                teile = [(x0, x1) for x0, x1 in _strecken(pk, innen - q) if x1 - x0 >= SCHMAL]
                if not teile:
                    continue
                if len(teile) > 1:
                    raise ValueError(_VERWINKELT)
                felder.append((a, b, teile[0], teile[0], max(bei(a)[1], bei(b)[1])))
                continue
            mitte = _strecken(pk, ym - q)
            if not mitte:
                continue
            if len(mitte) > 1:
                raise ValueError(_VERWINKELT)
            d = (b - a) * 1e-7
            la = _strecken(pk, bei(a + d)[0] - q)
            lb = _strecken(pk, bei(b - d)[0] - q)
            if len(la) != 1 or len(lb) != 1:
                raise ValueError(_VERWINKELT)
            felder.append((a, b, la[0], lb[0], max(bei(a)[1], bei(b)[1])))
    if not felder:
        raise ValueError("Ausschnitt mit Tiefe: Die Kontur trifft das Profil nicht (Lage quer und Seite prüfen).")
    felder.sort()
    # zusammenhängende Bereiche am Umfang; geschlossenes Profil: über die Naht der Abwicklung hinweg
    gruppen = [[felder[0]]]
    for f in felder[1:]:
        if abs(f[0] - gruppen[-1][-1][1]) < 1e-6:
            gruppen[-1].append(f)
        else:
            gruppen.append([f])
    if haut.zu and len(gruppen) > 1 and abs(gruppen[0][0][0] + haut.umfang - gruppen[-1][-1][1]) < 1e-6:
        erste = [(a + haut.umfang, b + haut.umfang, la, lb, z) for a, b, la, lb, z in gruppen.pop(0)]
        gruppen[-1] += erste
    elif haut.zu and len(gruppen) == 1 and abs(gruppen[0][-1][1] - gruppen[0][0][0] - haut.umfang) < 1e-6:
        raise ValueError(_TRENNT)
    if not haut.zu and not haut.massiv and len(gruppen) == 1 and len(haut.frei) == 2 \
            and abs(gruppen[0][0][0] - haut.frei[0]) < 1e-6 and abs(gruppen[0][-1][1] - haut.frei[1]) < 1e-6:
        raise ValueError(_TRENNT)
    if haut.massiv and not haut.schmal and abs(gruppen[0][0][0] - haut.frei[0]) < 1e-6 \
            and abs(gruppen[0][-1][1] - haut.frei[1]) < 1e-6:
        raise ValueError(_TRENNT)
    tief = max(f[4] for g in gruppen for f in g)
    if haut.gegen and wand and H - wand + EPS < t < H - EPS and tief > H - wand + EPS:
        raise ValueError(f"Ausschnitt mit Tiefe: {_zahl(t)} mm Tiefe endet mitten in der Gegenwand (Höhe "
                         f"{_zahl(H)} mm, Wand {_zahl(wand)} mm). Tiefe höchstens {_zahl(H - wand)} mm oder "
                         f"mindestens {_zahl(H)} mm (vollständiger Durchbruch) eingeben.")
    beide = False
    if len(gruppen) == 2 and t >= H - EPS:
        # diese Wand und die Gegenwand, ohne Seitenwand dazwischen: vollständiger Durchbruch (beide Wände)
        beide = True
        gruppen = [min(gruppen, key=lambda g: min(abs((f[0] + f[1]) / 2 - q) for f in g))]
    if len(gruppen) != 1:
        raise ValueError(_GETRENNT)
    g = gruppen[0]
    if haut.zu:                         # Lage am Umfang so, dass der Umriss möglichst nah an der Konturmitte liegt
        k = round(((g[0][0] + g[-1][1]) / 2 - q) / haut.umfang)
        g = [(a - k * haut.umfang, b - k * haut.umfang, la, lb, z) for a, b, la, lb, z in g]
    links, rechts = [], []
    for a, b, la, lb, _ in g:
        links += [(la[0], a - q), (lb[0], b - q)]
        rechts += [(la[1], a - q), (lb[1], b - q)]
    zug = []
    for p in rechts + links[::-1]:
        p = (round(p[0], 4), round(p[1], 4))
        if not zug or math.dist(zug[-1], p) > 1e-4:
            zug.append(p)
    if len(zug) > 1 and math.dist(zug[0], zug[-1]) <= 1e-4:
        zug.pop()
    zug = _ohne_gerade(zug)
    if len(zug) < 3:
        raise ValueError("Ausschnitt mit Tiefe: Die Kontur trifft das Profil nicht (Lage quer und Seite prüfen).")
    frei = [s - q for s in haut.frei]
    lg = 0.0
    for i, p in enumerate(zug):
        p1 = zug[(i + 1) % len(zug)]
        if any(abs(p[1] - s) < 1e-4 and abs(p1[1] - s) < 1e-4 for s in frei):
            continue                    # liegt auf der freien Kante: dort ist der Ausschnitt offen, kein Schnitt
        lg += math.dist(p, p1)
    hinweise = []
    if not beide and not haut.massiv and tief < wand + EPS and t > wand + EPS and not qs.r:
        rest = min(haut.breite / 2 - max(abs(dq + q) for _, dq in zug), haut.breite)
        text = (f"Die Kontur erreicht keine Kante der Fläche (Rest {_zahl(max(rest, 0))} mm): Die Tiefe "
                f"{_zahl(t)} mm wirkt nur in dieser Wand, die Gegenwand bleibt ganz.")
        if wand and 0 <= rest < wand:
            text += f" Der Steg zur Kante ist schmaler als die Wand ({_zahl(wand)} mm) und kann ausreißen."
        hinweise.append(text)
    if qs.r and not beide and tief < t - 0.01:
        hinweise.append(f"Die Kontur endet am Umfang {_zahl(tief)} mm unter dem Scheitel, bevor die Tiefe "
                        f"{_zahl(t)} mm erreicht ist: Der Ausschnitt wird nur so tief, wie die Kontur breit ist.")
    xs, qs_ = [p[0] for p in zug], [p[1] for p in zug]
    return dict(umriss=[[x, dq] for x, dq in zug], laenge=lg, huelle=max(max(xs) - min(xs), max(qs_) - min(qs_)),
                tiefe_ist=round(H if beide else min(t, max(tief, wand or 0.0)), 3),
                beide=beide, hinweise=hinweise)


_VERWINKELT = ("Ausschnitt mit Tiefe: Die Kontur ist über die Kante hinweg zu verwinkelt (sie träfe die Wand an "
               "mehreren getrennten Stellen). Bitte in einfache Konturen teilen.")
_GETRENNT = ("Ausschnitt mit Tiefe: Mit dieser Richtung entstünden mehrere getrennte Ausschnitte (zum Beispiel an "
             "beiden Flanschenden). Bitte je Fläche einen eigenen Ausschnitt setzen.")
_TRENNT = ("Ausschnitt mit Tiefe: Mit dieser Tiefe und Breite würde das Teil ganz durchgetrennt. Dafür einen "
           "Trennschnitt (zwei Teile) verwenden oder Tiefe bzw. Breite verkleinern.")


def _ohne_gerade(zug):
    """Punkte, die auf der Geraden zwischen ihren Nachbarn liegen, entfallen."""
    out = list(zug)
    i = 0
    while len(out) > 3 and i < len(out):
        a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
        kreuz = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(kreuz) < 2e-4 * (math.dist(a, b) + math.dist(b, c)) and (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) >= 0:
            out.pop(i)
            i = max(i - 1, 0)
        else:
            i += 1
    return out


def flaeche_zu_seite(qs, punkte_3d):
    """Seite des Profils zu einer im 3D gewählten Fläche (Modellpunkte (−u, v, x) wie rohr3d): (Seite, x längs,
    Versatz quer). ValueError, wenn die Fläche keine Außenfläche ist (Schnittfläche am Ende, Innenwand)."""
    pk = [(-float(p[0]), float(p[1]), float(p[2])) for p in punkte_3d]
    if not pk:
        raise ValueError("Ausschnitt mit Tiefe: Erst im 3D eine Außenfläche des Teils wählen.")
    u = sum(p[0] for p in pk) / len(pk)
    v = sum(p[1] for p in pk) / len(pk)
    x = sum(p[2] for p in pk) / len(pk)
    kein = ("Ausschnitt mit Tiefe: Die gewählte Fläche ist keine Außenfläche des Profils (Schnittfläche am Ende oder "
            "Innenwand). Bitte eine Außenfläche wählen.")
    if max(p[2] for p in pk) - min(p[2] for p in pk) < 1e-3:
        raise ValueError(kein)
    if qs.r:
        if any(abs(math.hypot(p[0], p[1]) - qs.r) > 0.6 for p in pk):
            raise ValueError(kein)
        # ganzer Mantel gewählt: Mitte liegt auf der Achse, dann oben
        w = math.degrees(math.atan2(u, v)) % 360 if math.hypot(u, v) > 0.2 * qs.r else 0.0
        return round(w, 1), round(x, 1), 0.0
    for f in qs.flaechen:
        ab = [(p[0] - f.mitte[0]) * f.n[0] + (p[1] - f.mitte[1]) * f.n[1] for p in pk]
        if max(abs(a) for a in ab) <= 0.6:
            q = (u - f.mitte[0]) * f.dir[0] + (v - f.mitte[1]) * f.dir[1]
            return f.name, round(x, 1), round(q, 1)
    raise ValueError(kein)


# ---------------------------------------------------------------------------------------------- Blech
KANTEN = ("unten", "rechts", "oben", "links")


def _blech_karte(kante, W, H):
    """Abbildung in ein Bild, in dem die gewählte Kante unten liegt (y = 0), und zurück; Maße (Breite, Höhe) dort."""
    if kante == "oben":
        return (lambda x, y: (x, H - y)), (lambda x, y: (x, H - y)), W, H
    if kante == "links":
        return (lambda x, y: (y, x)), (lambda x, y: (y, x)), H, W
    if kante == "rechts":
        return (lambda x, y: (y, W - x)), (lambda x, y: (W - y, x)), H, W
    return (lambda x, y: (x, y)), (lambda x, y: (x, y)), W, H


def blech_ausklinkung(punkte, kante, lage, breite, tiefe, radius=0.0, umgekehrt=False):
    """Außenkontur [(x, y)] eines Blechs (ab 0,0) mit einer Ausklinkung einstellbarer Tiefe an einer Kante des
    Hüllrechtecks: lage = Mitte der Ausklinkung entlang der Kante (ab links bzw. unten), breite entlang der Kante,
    tiefe von der Kante in das Blech, radius = Rundung der inneren Ecken; umgekehrt = von der gegenüberliegenden Kante.
    Ergebnis: neue Punkte (gegen den Uhrzeiger). ValueError mit Grund, wenn die Ausklinkung nicht ausführbar ist."""
    if kante not in KANTEN:
        raise ValueError("Ausklinkung mit Tiefe: Kante wählen (unten, rechts, oben, links).")
    if umgekehrt:
        kante = KANTEN[(KANTEN.index(kante) + 2) % 4]
    pk = [(float(x), float(y)) for x, y in punkte]
    if len(pk) < 3:
        raise ValueError("Ausklinkung mit Tiefe: Die Außenkontur ist offen (mindestens 3 Eckpunkte).")
    minx, miny = min(x for x, _ in pk), min(y for _, y in pk)
    pk = [(x - minx, y - miny) for x, y in pk]
    W, H = max(x for x, _ in pk), max(y for _, y in pk)
    hin, zurueck, B, T = _blech_karte(kante, W, H)
    q = [hin(x, y) for x, y in pk]
    if sum(q[i][0] * q[(i + 1) % len(q)][1] - q[(i + 1) % len(q)][0] * q[i][1] for i in range(len(q))) < 0:
        q.reverse()                     # gegen den Uhrzeiger: die untere Kante läuft von links nach rechts
    breite, tiefe, radius = _z(breite), _z(tiefe), _z(radius)
    if breite <= 0 or tiefe <= 0:
        raise ValueError("Ausklinkung mit Tiefe: Breite und Tiefe eingeben.")
    a, b = max(_z(lage) - breite / 2, 0.0), min(_z(lage) + breite / 2, B)
    if b - a < SCHMAL:
        raise ValueError("Ausklinkung mit Tiefe: Die Lage liegt neben der Kante (Lage und Breite prüfen).")
    if tiefe >= T - EPS:
        raise ValueError(f"Ausklinkung mit Tiefe: {_zahl(tiefe)} mm Tiefe trennt das Blech ganz durch (Maß quer "
                         f"{_zahl(T)} mm). Dafür zwei Teile anlegen oder die Tiefe verkleinern.")
    if a <= EPS and b >= B - EPS:
        raise ValueError("Ausklinkung mit Tiefe: Über die ganze Kante wäre das ein Kürzen des Blechs. Dafür Länge "
                         "bzw. Breite des Zuschnitts ändern.")
    if radius < 0 or radius > min(tiefe, (b - a) / 2) + 1e-9:
        raise ValueError("Ausklinkung mit Tiefe: Eckradius höchstens die Tiefe und die halbe Breite.")
    n = len(q)
    wirt = None
    for i in range(n):
        (x0, y0), (x1, y1) = q[i], q[(i + 1) % n]
        if abs(y0) < 1e-6 and abs(y1) < 1e-6 and x0 <= a + 1e-6 and x1 >= b - 1e-6:
            wirt = i
            break
    if wirt is None:
        raise ValueError("Ausklinkung mit Tiefe: An dieser Stelle trägt keine gerade Außenkante die ganze Breite "
                         "(dort liegt schon ein Ausschnitt, eine Schräge oder eine Rundung). Lage oder Breite ändern.")
    (x0, _), (x1, _) = q[wirt], q[(wirt + 1) % n]
    links_ecke, rechts_ecke = a <= x0 + 1e-6, b >= x1 - 1e-6
    vor, nach = q[(wirt - 1) % n], q[(wirt + 2) % n]
    ecke = ("Ausklinkung mit Tiefe: An der Ecke muss die anschließende Kante gerade und länger als die Tiefe sein. "
            "Lage, Breite oder Tiefe ändern.")
    if links_ecke and not (abs(vor[0] - x0) < 1e-6 and vor[1] >= tiefe - 1e-6):
        raise ValueError(ecke)
    if rechts_ecke and not (abs(nach[0] - x1) < 1e-6 and nach[1] >= tiefe - 1e-6):
        raise ValueError(ecke)
    # nichts anderes darf im Rechteck der Ausklinkung liegen (andere Kanten der Außenkontur)
    for i in range(n):
        if i == wirt:
            continue
        p0, p1 = q[i], q[(i + 1) % n]
        for k in range(21):             # Kante in Stücken prüfen: Punkt echt im Inneren des Rechtecks
            x = p0[0] + (p1[0] - p0[0]) * k / 20
            y = p0[1] + (p1[1] - p0[1]) * k / 20
            if a + 1e-4 < x < b - 1e-4 and -1e-4 < y < tiefe - 1e-4 and not (abs(y) < 1e-6 and i in
                                                                             ((wirt - 1) % n, (wirt + 1) % n)):
                raise ValueError("Ausklinkung mit Tiefe: Die Ausklinkung träfe eine andere Kante der Außenkontur "
                                 "(dort ist das Blech schon ausgeschnitten). Lage, Breite oder Tiefe ändern.")
    r = radius

    def bogen(cx, cy, w0, w1):
        return [(cx + r * math.cos(math.radians(w0 + (w1 - w0) * k / 6)),
                 cy + r * math.sin(math.radians(w0 + (w1 - w0) * k / 6))) for k in range(7)]
    neu = []
    if links_ecke:
        neu.append((x0, tiefe))
    else:
        neu += [(a, 0.0)] + (bogen(a + r, tiefe - r, 180, 90) if r > 1e-6 else [(a, tiefe)])
    if rechts_ecke:
        neu.append((x1, tiefe))
    else:
        neu += (bogen(b - r, tiefe - r, 90, 0) if r > 1e-6 else [(b, tiefe)]) + [(b, 0.0)]
    out = []
    for i in range(n):
        if i == wirt:
            if not links_ecke:
                out.append(q[i])
            out += neu
        elif i == (wirt + 1) % n:
            if not rechts_ecke:
                out.append(q[i])
        else:
            out.append(q[i])
    sauber = []
    for p in out:
        if not sauber or math.dist(sauber[-1], p) > 1e-6:
            sauber.append(p)
    if len(sauber) > 1 and math.dist(sauber[0], sauber[-1]) <= 1e-6:
        sauber.pop()
    erg = [zurueck(x, y) for x, y in _ohne_gerade(sauber)]
    if sum(erg[i][0] * erg[(i + 1) % len(erg)][1] - erg[(i + 1) % len(erg)][0] * erg[i][1]
           for i in range(len(erg))) < 0:
        erg.reverse()
    return [(round(x, 4), round(y, 4)) for x, y in erg]


def blech_ausklinken(e, kante, lage, breite, tiefe, radius=0.0, umgekehrt=False):
    """Blech-Eingaben e mit einer Ausklinkung einstellbarer Tiefe in der Außenkontur (Form wird Polygon; Innenkonturen,
    Schenkel und alle anderen Angaben bleiben). Ergebnis (neue Eingaben, Hinweise). ValueError mit Grund."""
    from . import blech, blech3d
    zs = blech.zuschnitt(e)
    alt = blech3d.aussenkontur(e, zs)
    neu = blech_ausklinkung(alt, kante, lage, breite, tiefe, radius, umgekehrt)
    hinweise = []
    k = KANTEN[(KANTEN.index(kante) + 2) % 4] if umgekehrt else kante
    W, H = max(x for x, _ in alt), max(y for _, y in alt)
    a, b, t = _z(lage) - _z(breite) / 2, _z(lage) + _z(breite) / 2, _z(tiefe)
    kasten = {"unten": (a, 0, b, t), "oben": (a, H - t, b, H), "links": (0, a, t, b), "rechts": (W - t, a, W, b)}[k]
    for z in e.get("konturen") or ():
        if isinstance(z, dict) and z.get("x") not in (None, "") and z.get("y") not in (None, ""):
            if kasten[0] <= _z(z["x"]) <= kasten[2] and kasten[1] <= _z(z["y"]) <= kasten[3]:
                hinweise.append(f"{z.get('art')} bei x {_zahl(_z(z['x']))} / y {_zahl(_z(z['y']))} mm liegt in der "
                                "Ausklinkung und entfällt dort nicht von selbst: bitte prüfen.")
    return dict(e, form=blech.POLYGON, punkte="; ".join(f"{_p(x)},{_p(y)}" for x, y in neu), eckradius=0), hinweise


def _p(x):
    """Koordinate für die Punktliste: höchstens vier Nachkommastellen, Punkt als Dezimalzeichen."""
    return f"{x:.4f}".rstrip("0").rstrip(".") or "0"
