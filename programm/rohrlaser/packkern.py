"""Packkern 3.0: Verpackungsoptimierung für Paletten, Gitterboxen und Kartons (Patrick 25.11.2026, Master-Auftrag
„Ladegutberechnung und Verpackungsvisualisierung“). Ohne Qt, reproduzierbar (keine Zufallswahl).

Modell (passend zu Rohrlaserteilen = lange Prismen): Ein Packstück ist ein Stapel aus **Lagen**. Eine Lage besteht aus
**Reihen** (Streifen) nebeneinander; in einer Reihe liegen Teile mit gleichem Querschnitt hintereinander.
- Achse „längs“: Teile liegen entlang der langen Palettenseite (1.200 mm), die Reihen füllen die Breite (800 mm).
- Achse „quer“: kurze Teile liegen quer über die Breite, die Reihen folgen hintereinander entlang der langen Seite.
Grenzen (je Packmittel einstellbar, sonst Einstellungen):
- Breite: höchstens Breite − 2 × Sicherheitsabstand, **nie ein Überstand auf der kurzen Seite** (800 mm).
- Länge: höchstens Länge + 2 × Überstand je Stirnseite (nur offene Ladungsträger; Gitterbox, Karton und
  Sonderbehälter: kein Überstand). Ein einzelnes Teil, das länger ist, liegt wie bisher bis zur „max. Teillänge“
  mittig (Langgut-Regel), mit Hinweis.
- Mindestabstand zwischen den Teilen; Höhe (max. Gesamthöhe bzw. Stapelhöhe), Gewicht (Nutzlast, max. Brutto).
Verfahren (Bericht https://claude.ai/artifact/UvbEeDSt2tAYrAB9z2JWCo):
- Streifenpacken über die Breite (gleiche Artikel als Block, Restbreite mit passenden Reihen anderer Artikel füllen),
  1D-Packen längs (kurze Teile hintereinander, Restlänge einer Reihe auffüllen), Lagenstapel mit Höhe und Gewicht,
  Blöcke in Ladungsträger per First-Fit-Decreasing (Varianten C/D).
- Verschachtelung: U in größerem U (Öffnung), gleiche Winkel ineinander gestapelt; NIE Rohr in Rohr (Patrick
  25.11.2026); mit Spiel, nur gerade Teile, inneres Teil nie länger als das äußere.
- Rundrohre versetzt in den Mulden der Lage darunter, wenn das mehr Teile ergibt (ohne Zwischenlage).
- Varianten: A sortenrein, B maximale Platzausnutzung, C minimale Anzahl Packstücke, D ausgewogen; automatisch gilt
  die beste (wenigste Packstücke, dann Sortenreinheit nach Einstellung, dann Auslastung).
- Jede Packliste wird geometrisch geprüft (pruefen): Teile innerhalb der Grenzen, keine Überschneidung (Rundrohre als
  Kreise), verschachtelte Teile im Inneren des äußeren.
Die Teile werden nur für Anzeige und Prüfung einzeln erzeugt (teile()); gerechnet wird mit Reihen und Anzahlen, so
bleiben auch 80.000 Teile schnell.
"""
import math

EPS = 1e-6
SPIEL = 3.0                     # Spiel beim Verschachteln je Seite [mm]
WURZEL3_2 = math.sqrt(3) / 2
OFFEN_NICHT = ("Gitterbox", "Karton", "Sonderbehälter")      # Innenmaße, kein Überstand
GESCHLOSSEN = ("Rundrohr", "Quadratrohr", "Rechteckrohr")
VARIANTEN = {"A": "möglichst sortenrein", "B": "maximale Platzausnutzung", "C": "minimale Anzahl Packstücke",
             "D": "Sortenreinheit und Platz ausgewogen"}
AUTOMATISCH = "automatisch (beste Variante)"
MODI = (AUTOMATISCH, "A – " + VARIANTEN["A"], "B – " + VARIANTEN["B"], "C – " + VARIANTEN["C"],
        "D – " + VARIANTEN["D"])
SORTEN = ("stark", "normal", "aus")
MAX_TEIL = 6500.0               # Vorgabe: lange Teile bis zur max. Teillänge der Maschine auf der Palette [mm]
UEBERSTAND = 50.0               # Vorgabe Überstand je Stirnseite der langen Seite [mm]


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _mm(x):
    from .stammdaten import zahl_als_text
    return zahl_als_text(round(x or 0), 0)


# ------------------------------------------------------------------ Parameter
def parameter(z, v):
    """Grenzen eines Ladungsträgers z mit den Vorgaben v (paletten.vorgaben): Werte des Packmittels vor den
    Einstellungen."""
    def wert(feld, schl):
        x = z.get(feld)
        return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 else v[schl]
    offen = z.get("art") not in OFFEN_NICHT
    pl, pb = _n(z.get("laenge")), _n(z.get("breite"))
    if pb > pl:
        pl, pb = pb, pl
    m = z.get("pack_max_artikel")
    return dict(pl=pl, pb=pb, ueber=wert("pack_ueberstand", "ueberstand") if offen else 0.0,
                rand=wert("pack_rand", "rand"), max_teil=float(v.get("max_teil") or MAX_TEIL), abstand=wert("pack_abstand", "abstand"),
                max_artikel=int(m) if isinstance(m, (int, float)) and m > 0 else int(v.get("max_artikel") or 0),
                verschachteln=v.get("verschachteln", True), drehen=v.get("drehen", True),
                zl=v.get("zwischenlage", 0.0), offen=offen, hand=v.get("hand") or {})


# ------------------------------------------------------------------ Verschachtelung
def _innen(profil):
    """Freier Innenraum eines Profils: ('kreis', D) bzw. ('rechteck', b, h) oder None."""
    if not profil:
        return None
    form, a, b, w = profil
    a, b, w = _n(a), _n(b) or _n(a), _n(w)
    if w <= 0 or a <= 0:
        return None
    # Patrick 25.11.2026: nie Rohr in Rohr, U-Profile nur gleich große verzahnt (einheiten), nicht klein in groß
    return None


def _aussen(profil):
    """Außenform eines Profils: ('kreis', d) bzw. ('rechteck', b, h)."""
    form, a, b, w = profil
    a, b = _n(a), _n(b) or _n(a)
    if form == "Rundrohr":
        return ("kreis", a)
    if form == "Flachstahl":
        return ("rechteck", a, _n(w) or a)
    if form == "Quadratrohr":
        return ("rechteck", a, a)
    return ("rechteck", a, b)


def passt_hinein(innen, aussen, spiel=SPIEL):
    """Passt die Außenform in den Innenraum (mit Spiel je Seite)?"""
    if innen is None or aussen is None:
        return False
    if innen[0] == "kreis":
        d = innen[1] - 2 * spiel
        return (aussen[1] if aussen[0] == "kreis" else math.hypot(aussen[1], aussen[2])) <= d + EPS
    ib, ih = sorted(innen[1:])
    ab, ah = (aussen[1], aussen[1]) if aussen[0] == "kreis" else sorted(aussen[1:])
    return ab <= ib - 2 * spiel + EPS and ah <= ih - 2 * spiel + EPS


def verschachteln(arten, spiel=SPIEL):
    """Sorten nach dem Verschachteln. arten: {k: dict(n, laenge, profil, gerade)}. Ergebnis: {Sorte: Anzahl}, Sorte =
    Tupel der Artikel von außen nach innen. Reproduzierbar: größere Teile zuerst, engste Passung zuerst."""
    sorten = {(k,): a["n"] for k, a in arten.items() if a["n"] > 0}
    fähig = [k for k, a in arten.items() if a.get("gerade") and a.get("profil")]
    fähig.sort(key=lambda k: (-max(_aussen(arten[k]["profil"])[1:]), k))
    for i in fähig:                                    # i als inneres Teil, große zuerst
        ai = _aussen(arten[i]["profil"])
        frei = sorten.get((i,), 0)
        if not frei:
            continue
        behaelter = []
        for s, n in sorten.items():
            j = s[-1]
            if n <= 0 or j == i or i in s or not arten[j].get("gerade") or not arten[j].get("profil"):
                continue
            innen = _innen(arten[j]["profil"])
            if arten[i]["laenge"] <= arten[j]["laenge"] + EPS and passt_hinein(innen, ai, spiel):
                rest = innen[1] if innen[0] == "kreis" else min(innen[1:])
                behaelter.append((rest, s))
        for _, s in sorted(behaelter, key=lambda x: (x[0], x[1])):
            m = min(sorten[s], frei)
            if m <= 0:
                continue
            sorten[s] -= m
            sorten[s + (i,)] = sorten.get(s + (i,), 0) + m
            sorten[(i,)] -= m
            frei -= m
            if not frei:
                break
    return {s: n for s, n in sorten.items() if n > 0}


def u_verzahnt(b, w, breite, n):
    """Gleich große U-Profile abwechselnd offen und umgedreht ineinander (Patrick 25.11.2026, Bild U-Stahl
    40 × 20 × 5): je weiteres U + (b − 2w + Spiel) Breite, Höhe h + w. Anzahl je Reihe über die nutzbare Breite;
    1 = geht nicht (Öffnung zu schmal für zwei Schenkel)."""
    if w <= 0 or b - 2 * w < 2 * w + 2 * SPIEL or b > breite + EPS:
        return 1
    teilung = b - 2 * w + SPIEL
    return max(1, min(n, int((breite - b + EPS) // teilung) + 1))


def winkel_stapel(a, b, w, hoehe_max):
    """Gleiche Winkel ineinander gestapelt: (Anzahl je Stapel, Querschnitt (b, h)). Jeder weitere Winkel liegt um die
    Wandstärke versetzt; gewählt wird die Anzahl mit der größten Dichte bis zur Höhe hoehe_max."""
    if w <= 0:
        return 1, (a, b)
    best = (1, (a, b), 1 / (a * b))
    for m in range(2, 41):
        q = (a + (m - 1) * w, b + (m - 1) * w)
        if max(q) > hoehe_max + EPS or max(q) > 2.5 * max(a, b):
            break
        dichte = m / (q[0] * q[1])
        if dichte > best[2] + EPS:
            best = (m, q, dichte)
    return best[0], best[1]


# ------------------------------------------------------------------ Einheiten (was als ein Stück gepackt wird)
def einheiten(stuecke, auswahl, p, stapel_max):
    """Packeinheiten der Artikel auswahl (Indizes in stuecke): [dict(sorte, artikel {k: Stück je Einheit}, n, x
    (Länge), quer (c1, c2), rund (Ø oder None), g (kg je Einheit), form)]."""
    arten = {}
    for k in auswahl:
        s = stuecke[k]
        m = s.get("masse")
        arten[k] = dict(n=s["stueck"], laenge=m[0] if m else 0.0, profil=s.get("profil"), gerade=s.get("gerade"))
    sorten = verschachteln(arten) if p["verschachteln"] else {(k,): a["n"] for k, a in arten.items()}
    out = []
    for sorte, n in sorted(sorten.items()):
        aussen = stuecke[sorte[0]]
        m = aussen.get("masse")
        g = sum(stuecke[k]["gewicht"] or 0.0 for k in sorte)
        e = dict(sorte=sorte, artikel={k: 1 for k in sorte}, n=n, x=m[0] if m else 0.0,
                 quer=(m[1], m[2]) if m else None, rund=None, g=g, form=(aussen.get("profil") or ("",))[0],
                 innen=[(k, _aussen(stuecke[k]["profil"])) for k in sorte[1:]] if len(sorte) > 1 else [],
                 aussen_form=_aussen(aussen["profil"]) if aussen.get("profil") else None)
        if aussen.get("rund") and len(sorte) >= 1 and m:
            e["rund"] = m[1]
        prof = aussen.get("profil")
        if (len(sorte) == 1 and p["verschachteln"] and prof and prof[0] == "U-Profil" and aussen.get("gerade")
                and m and n > 1):
            ub, uh, uw = _n(prof[1]), _n(prof[2]) or _n(prof[1]), _n(prof[3])
            je = u_verzahnt(ub, uw, p["pb"] - 2 * p["rand"], n)
            if je > 1:
                voll, rest = divmod(n, je)
                for anz, m_ in ((voll, je), (1 if rest > 1 else 0, rest)):
                    if anz:
                        out.append(dict(e, sorte=sorte + ("U", m_), artikel={sorte[0]: m_}, n=anz,
                                        quer=(ub + (m_ - 1) * (ub - 2 * uw + SPIEL), uh + uw), g=g * m_, stapel=m_,
                                        wand=uw, verzahnt=True, fest=True))
                if rest == 1:
                    out.append(dict(e, n=1))
                continue
        if (len(sorte) == 1 and p["verschachteln"] and prof and prof[0] == "L-Profil" and aussen.get("gerade")
                and m and n > 1):
            a_, b_, w_ = _n(prof[1]), _n(prof[2]) or _n(prof[1]), _n(prof[3])
            je, q = winkel_stapel(a_, b_, w_, stapel_max)
            if je > 1:
                voll, rest = divmod(n, je)
                if voll:
                    out.append(dict(e, sorte=sorte + ("L", je), artikel={sorte[0]: je}, n=voll, quer=q, g=g * je,
                                    stapel=je, wand=w_))
                if rest:
                    je2, q2 = (rest, (a_ + (rest - 1) * w_, b_ + (rest - 1) * w_))
                    out.append(dict(e, sorte=sorte + ("L", je2), artikel={sorte[0]: je2}, n=1, quer=q2, g=g * je2,
                                    stapel=je2, wand=w_))
                continue
        out.append(e)
    return out


# ------------------------------------------------------------------ Lagen
class Reihe:
    """Eine Reihe: Teile einer Einheit hintereinander (Achse längs) bzw. nebeneinander quer; dazu Füllteile anderer
    Einheiten am Ende (gleiche oder kleinere Breite und Höhe)."""
    __slots__ = ("teile", "b", "h")

    def __init__(self, b, h):
        self.teile, self.b, self.h = [], b, h      # teile: [(Einheit-Index, Stück, Länge, (b, h))]

    def laenge(self, a):
        n = sum(t[1] for t in self.teile)
        return sum(t[1] * t[2] for t in self.teile) + max(0, n - 1) * a


class Lage:
    __slots__ = ("achse", "reihen", "h", "versetzt", "dz")

    def __init__(self, achse):
        self.achse, self.reihen, self.h, self.versetzt, self.dz = achse, [], 0.0, False, None

    def breite(self, a):
        return sum(r.b for r in self.reihen) + max(0, len(self.reihen) - 1) * a

    def stueck(self):
        out = {}
        for r in self.reihen:
            for e, n, _, _ in r.teile:
                out[e] = out.get(e, 0) + n
        return out


def _orient(e, drehen):
    """Querschnitte (b quer zur Reihe, h hoch) einer Einheit: flach liegend zuerst, mit Drehen auch hochkant."""
    c1, c2 = e["quer"]
    if e.get("fest"):                  # verzahnte U: nur so, wie sie liegen
        return [(c1, c2)]
    o = [(max(c1, c2), min(c1, c2))]
    if drehen and abs(c1 - c2) > EPS:
        o.append((min(c1, c2), max(c1, c2)))
    return o


class Packer:
    """Packt Einheiten auf einen Ladungsträger-Typ."""

    def __init__(self, z, p, frei, last, einheiten_, stuecke):
        self.z, self.p, self.frei, self.last, self.E, self.S = z, p, frei, last, einheiten_, stuecke
        self.a = p["abstand"]
        self.W = p["pb"] - 2 * p["rand"]
        self.L = p["pl"] + 2 * p["ueber"]
        # Patrick 25.11.2026: lange Teile bis zur max. Teillänge der Maschine (6.500 mm) stehen an der langen Seite über
        self.lmax = max(self.L, _n(z.get("max_laenge")), p["max_teil"]) if p["offen"] else self.L
        self.hinweise = []
        self.uebrig = {}
        self.versetzen = True                # Einheit -> Stück, die in keine Lage passen (zu lang, zu hoch)
        # von Hand je Position (Packliste im Frachtrechner): allein = eigenes Packstück, achse = längs/quer fest
        hand = (p["hand"].get("artikel") or {}) if isinstance(p["hand"], dict) else {}

        def h(k):
            x = hand.get(str(stuecke[k].get("id")))
            return x if isinstance(x, dict) else {}
        self.allein_k = {k for e in einheiten_ for k in e["artikel"] if h(k).get("allein")}
        self.allein = {i for i, e in enumerate(einheiten_) if set(e["artikel"]) & self.allein_k}
        self.achse_fest = {}
        for i, e in enumerate(einheiten_):
            e["i"] = i
            a = h(e["sorte"][0]).get("achse")
            if a in ("l", "q"):
                self.achse_fest[i] = a

    # -------- Kennzahlen einer Einheit
    def je_reihe(self, e, achse, b):
        """Stück je Reihe einer Einheit (Achse längs: entlang L, quer: entlang W)."""
        x = e["x"]
        if achse == "l":
            if x <= self.L + EPS:
                return int((self.L + self.a + EPS) // (x + self.a))
            return 1 if x <= self.lmax + EPS else 0
        return int((self.W + self.a + EPS) // (x + self.a)) if x <= self.W + EPS else 0

    def reihen_platz(self, achse):
        """Platz für die Reihen nebeneinander: längs die nutzbare Breite, quer die Palettenlänge (quer liegende
        Teile stehen nicht über, sie lägen sonst auf ganzer Länge frei)."""
        return self.W if achse == "l" else self.p["pl"]

    def beste_lage(self, e, rest, versetzt_auf=None):
        """Beste sortenreine Lage für Einheit e: (achse, (b, h), je_reihe, reihen, dichte)."""
        best = None
        fest = self.achse_fest.get(e.get("i"))
        for achse in ((fest,) if fest else ("l", "q")):
            for b, h in _orient(e, self.p["drehen"]):
                if h > self.frei + EPS:
                    continue
                n = self.je_reihe(e, achse, b)
                r = int((self.reihen_platz(achse) + self.a + EPS) // (b + self.a))
                if n <= 0 or r <= 0:
                    continue
                stk = n * r
                dichte = min(stk, rest) / h
                key = (dichte, achse == "l", b >= h)
                if best is None or key > best[-1]:
                    best = (achse, (b, h), n, r, key)
        return best

    # -------- eine Lage bauen
    def lage(self, primaer, rest, mischen, nur_rest=None, vorher=None):
        """Eine Lage mit der Einheit primaer bauen; Restbreite und Restlänge der Reihen mit anderen Einheiten füllen
        (mischen = 'alle' oder 'rest': nur Teile, die sonst eine angefangene Lage bilden würden). rest: {Einheit:
        Stück}, wird verringert. Ergebnis: Lage oder None."""
        e = self.E[primaer]
        bl = self.beste_lage(e, rest[primaer])
        if bl is None:
            return None
        achse, (b, h), n, r, _ = bl
        lg = Lage(achse)
        lg.h = h
        # versetzt: gleiche Rundrohre wie die Lage darunter, ohne Zwischenlage
        d = e.get("rund")
        if (d and self.versetzen and vorher is not None and not self.p["zl"] and achse == "l" and abs(b - h) < EPS and
                vorher.achse == "l" and not vorher.versetzt and len(vorher.reihen) == r and
                all(len(rr.teile) == 1 and rr.teile[0][0] == primaer and rr.teile[0][1] == n for rr in vorher.reihen)):
            r2 = int((self.W - d / 2 + self.a + EPS) // (d + self.a))
            if r2 > 0 and r2 / (d * WURZEL3_2) > r / d + EPS and rest[primaer] >= n * r2:   # dichter, ganze Lage
                lg.versetzt, lg.dz, r = True, d * WURZEL3_2, r2
        platz = self.reihen_platz(achse)
        gewicht = 0.0
        last = self.last
        for _ in range(r):
            k = min(n, rest[primaer])
            if last is not None and e["g"] > EPS:
                k = min(k, int((last - gewicht + 1e-7) // e["g"]))
            if k <= 0:
                break
            rh = Reihe(b, h)
            rh.teile.append((primaer, k, e["x"], (b, h)))
            rest[primaer] -= k
            gewicht += k * e["g"]
            lg.reihen.append(rh)
        if not lg.reihen:                         # schwerer als die Zuladung: trotzdem 1 Stück
            rh = Reihe(b, h)
            rh.teile.append((primaer, 1, e["x"], (b, h)))
            rest[primaer] -= 1
            lg.reihen.append(rh)
            return lg
        if not mischen and not self.voll(lg):     # angefangene Lage mit anderen Profilen auffüllen
            mischen = "alle"
        if mischen and not lg.versetzt and primaer not in self.allein:
            gewicht = self._auffuellen(lg, primaer, rest, mischen, nur_rest, gewicht)
            self._breite_fuellen(lg, primaer, rest, mischen, nur_rest, platz, gewicht)
        return lg

    def _kandidaten(self, primaer, rest, mischen, nur_rest):
        for i, e in enumerate(self.E):
            if i == primaer or rest[i] <= 0 or e["quer"] is None or i in self.allein:
                continue
            if mischen == "rest" and nur_rest is not None and nur_rest.get(i, 0) <= 0:
                continue
            yield i, e

    def _artikel_ok(self, lg, i, extra=()):
        m = self.p["max_artikel"]
        if not m:
            return True
        arts = {k for r in lg.reihen for t in r.teile for k in self.E[t[0]]["artikel"]} | set(extra)
        return len(arts | set(self.E[i]["artikel"])) <= m

    def _auffuellen(self, lg, primaer, rest, mischen, nur_rest, gewicht):
        """Restlänge jeder Reihe mit kürzeren Teilen gleicher oder kleinerer Breite und Höhe füllen."""
        laenge = self.L if lg.achse == "l" else self.W
        for rh in lg.reihen:
            frei = laenge - rh.laenge(self.a)          # je weiteres Teil: Abstand + Länge
            if frei <= EPS or rh.teile[0][2] > laenge + EPS:
                continue
            for i, e in self._kandidaten(primaer, rest, mischen, nur_rest):
                if e["x"] + self.a > frei + EPS:
                    continue
                for b, h in _orient(e, self.p["drehen"]):
                    if b <= rh.b + EPS and h <= lg.h + EPS and self._artikel_ok(lg, i):
                        k = min(int((frei + EPS) // (e["x"] + self.a)), rest[i],
                                nur_rest.get(i, rest[i]) if (mischen == "rest" and nur_rest) else rest[i])
                        if self.last is not None and e["g"] > EPS:
                            k = min(k, int((self.last - gewicht + 1e-7) // e["g"]))
                        if k > 0:
                            rh.teile.append((i, k, e["x"], (b, h)))
                            rest[i] -= k
                            if mischen == "rest" and nur_rest:
                                nur_rest[i] -= k
                            gewicht += k * e["g"]
                            frei -= k * (e["x"] + self.a)
                        break
                if frei <= EPS:
                    break
        return gewicht

    def _breite_fuellen(self, lg, primaer, rest, mischen, nur_rest, platz, gewicht):
        """Restbreite (Achse längs) bzw. Restlänge (quer) mit Reihen anderer Einheiten füllen (Best Fit)."""
        laenge = self.L if lg.achse == "l" else self.W
        while True:
            frei = platz - lg.breite(self.a) - self.a
            best = None
            for i, e in self._kandidaten(primaer, rest, mischen, nur_rest):
                if e["x"] > laenge + EPS or not self._artikel_ok(lg, i):
                    continue
                for b, h in _orient(e, self.p["drehen"]):
                    # höhere Teile dürfen die Lage füllen (sie wird so hoch wie das höchste), lieber gleich hohe
                    if b <= frei + EPS and h <= self.frei + EPS:
                        n = self.je_reihe(e, lg.achse, b)
                        schl = (-max(0.0, round(h - lg.h, 3)), b, -i)
                        if n > 0 and (best is None or schl > best[-1]):
                            best = (i, b, h, n, schl)
            if best is None:
                return
            i, b, h, n, _ = best
            lg.h = max(lg.h, h)
            e = self.E[i]
            k = min(n, rest[i], nur_rest.get(i, rest[i]) if (mischen == "rest" and nur_rest) else rest[i])
            if self.last is not None and e["g"] > EPS:
                k = min(k, int((self.last - gewicht + 1e-7) // e["g"]))
            if k <= 0:
                return
            rh = Reihe(b, h)
            rh.teile.append((i, k, e["x"], (b, h)))
            lg.reihen.append(rh)
            rest[i] -= k
            if mischen == "rest" and nur_rest:
                nur_rest[i] -= k
            gewicht += k * e["g"]

    def voll(self, lg):
        """Komplett volle Lage (Patrick 25.11.2026: nur darauf darf die nächste Lage): keine Reihe passt mehr
        daneben und keine Reihe hat Platz für ein weiteres ihrer Teile."""
        if not lg.reihen:
            return False
        platz = self.reihen_platz(lg.achse) - (lg.reihen[0].b / 2 if lg.versetzt else 0.0)
        if platz - lg.breite(self.a) >= min(r.b for r in lg.reihen) + self.a - EPS:
            return False
        laenge = self.L if lg.achse == "l" else self.W
        for rh in lg.reihen:
            kuerzest = min(t[2] for t in rh.teile)
            if max(t[2] for t in rh.teile) <= laenge + EPS and laenge - rh.laenge(self.a) >= kuerzest + self.a - EPS:
                return False
        return True

    # -------- Gewicht und Höhe
    def gewicht(self, lg):
        return sum(n * self.E[e]["g"] for r in lg.reihen for e, n, _, _ in r.teile)


# ------------------------------------------------------------------ Varianten
def _lagen_bauen(pk, rest, reihenfolge, mischen):
    """Lagen in Blöcken (je Block gleiche Hauptsorte, untereinander gestapelt): [[Lage, …], …]."""
    bloecke = []
    voll = {}
    if mischen == "rest":                            # Stück einer vollen sortenreinen Lage je Einheit
        for j, e in enumerate(pk.E):
            bl = pk.beste_lage(e, e["n"]) if e["quer"] else None
            voll[j] = bl[2] * bl[3] if bl else 0
    for i in reihenfolge:
        block, vorher = [], None
        while rest[i] > 0:
            nur_rest = None
            if mischen == "rest":                    # nur Teile, die sonst eine angefangene Lage wären
                nur_rest = {j: (rest[j] % voll[j] if voll[j] else rest[j]) for j in range(len(pk.E)) if rest[j] > 0}
            vor = rest[i]
            lg = pk.lage(i, rest, mischen, nur_rest, vorher)
            if lg is None or rest[i] == vor and not lg.reihen:
                pk.uebrig[i] = pk.uebrig.get(i, 0) + rest[i]      # nie Teile verlieren: als Sonderladung
                rest[i] = 0
                break
            block.append(lg)
            vorher = lg
        if block:
            bloecke.append(block)
    return bloecke


def _hoehe(lagen, zl):
    """Höhe eines Lagenstapels (versetzte Lagen sitzen in den Mulden der Lage darunter)."""
    h = 0.0
    for j, lg in enumerate(lagen):
        if j == 0:
            h = lg.h
        elif lg.versetzt:
            h += lg.dz + lg.h - lagen[j - 1].h
        else:
            h += zl + lg.h
    return h


class _Stapel:
    """Lagen eines Ladungsträgers (oder ein Teilstapel) mit laufender Höhe, Gewicht und Artikeln."""
    __slots__ = ("lagen", "h", "g", "arts", "x")

    def __init__(self, pk, lagen=()):
        self.lagen, self.h, self.g, self.arts, self.x = [], 0.0, 0.0, set(), 0.0
        for lg in lagen:
            self.dazu(pk, lg)

    def dazu(self, pk, lg):
        if not self.lagen:
            self.h = lg.h
        elif lg.versetzt:
            self.h += lg.dz + lg.h - self.lagen[-1].h
        else:
            self.h += pk.p["zl"] + lg.h
        self.lagen.append(lg)
        self.g += pk.gewicht(lg)
        for r in lg.reihen:
            for t in r.teile:
                self.arts.update(pk.E[t[0]]["artikel"])
                self.x = max(self.x, pk.E[t[0]]["x"])

    def stapeln(self, pk, st):
        """st (eigener Stapel) obenauf; seine erste Lage ist nie versetzt."""
        self.h = (self.h + pk.p["zl"] + st.h) if self.lagen else st.h
        self.lagen += st.lagen
        self.g += st.g
        self.arts |= st.arts
        self.x = max(self.x, st.x)


def _passt(pk, pal, st):
    """Passt Stapel st (bzw. eine Lage) auf pal (Höhe, Gewicht, Artikel je Packstück)?"""
    if isinstance(st, Lage):
        h = pal.h + (st.dz + st.h - pal.lagen[-1].h if st.versetzt and pal.lagen else
                     (pk.p["zl"] if pal.lagen else 0.0) + st.h)
        g, arts = pk.gewicht(st), {k for r in st.reihen for t in r.teile for k in pk.E[t[0]]["artikel"]}
    else:
        h, g, arts = pal.h + (pk.p["zl"] if pal.lagen else 0.0) + st.h, st.g, st.arts
    if h > pk.frei + EPS:
        return False
    if pk.last is not None and pal.g + g > pk.last + 1e-6:
        return False
    if pal.lagen and not pk.voll(pal.lagen[-1]):           # nur auf eine komplett volle Lage
        return False
    alle = pal.arts | arts
    if pal.lagen and len(alle) > 1 and alle & pk.allein_k:      # von Hand: eigenes Packstück
        return False
    return not pk.p["max_artikel"] or len(alle) <= pk.p["max_artikel"]


def _teilen(pk, lg, g_frei):
    """Lage nach Gewicht teilen: (Teil bis g_frei kg, Rest) oder (None, lg)."""
    a, b = Lage(lg.achse), Lage(lg.achse)
    a.h = b.h = lg.h
    g = 0.0
    for rh in lg.reihen:
        ra, rb = Reihe(rh.b, rh.h), Reihe(rh.b, rh.h)
        for e_i, n, xl, q in rh.teile:
            ge = pk.E[e_i]["g"]
            k = n if ge <= EPS else max(0, min(n, int((g_frei - g + 1e-7) // ge)))
            if k:
                ra.teile.append((e_i, k, xl, q))
                g += k * ge
            if n - k:
                rb.teile.append((e_i, n - k, xl, q))
        if ra.teile:
            a.reihen.append(ra)
        if rb.teile:
            b.reihen.append(rb)
    return (a if a.reihen else None), b


def _in_paletten(pk, bloecke, art):
    """Lagen auf Ladungsträger verteilen. art 'sorte' (je Hauptsorte, angefangene zusammen), 'folge' (der Reihe
    nach), 'ffd' (First Fit Decreasing nach Länge und Höhe), 'paar' (wie ffd, gleiche Artikel bevorzugt).
    Ergebnis: [[Lage, …] je Ladungsträger]."""
    stapel = []                       # Blöcke in Stapel, die je auf einen Ladungsträger passen
    n_e = len(pk.E)

    def zurueck(lg, reste):
        for rh in lg.reihen:
            for e_i, n, _, _ in rh.teile:
                reste[e_i] += n

    for block in bloecke:
        akt, schlange, reste = _Stapel(pk), list(block), [0] * n_e
        while True:
            if not schlange:          # nach Gewicht geteilte Reste zu ganzen Lagen zusammenpacken (oben im Block)
                if not any(reste):
                    break
                for i in sorted(range(n_e), key=lambda i: (-pk.E[i]["x"], i)):
                    while reste[i] > 0:
                        vor = reste[i]
                        lg = pk.lage(i, reste, "alle")
                        if lg is None or reste[i] == vor and not lg.reihen:
                            pk.uebrig[i] = pk.uebrig.get(i, 0) + reste[i]
                            reste[i] = 0
                            break
                        schlange.append(lg)
                reste = [0] * n_e
                if not schlange:
                    break
            lg = schlange.pop(0)
            if not schlange and any(reste) and not pk.voll(lg):   # angefangene Lage mit den Resten zusammen
                zurueck(lg, reste)
                continue
            if akt.lagen and not _passt(pk, akt, lg):
                if pk.last is not None and pk.gewicht(lg) > pk.last - akt.g + 1e-6:   # Gewicht: Lage teilen
                    if lg.versetzt:
                        lg.versetzt, lg.dz = False, None
                    teil, rest_lg = _teilen(pk, lg, pk.last - akt.g)
                    if teil is not None and _passt(pk, akt, teil):
                        akt.dazu(pk, teil)
                    elif teil is not None:
                        zurueck(teil, reste)
                    zurueck(rest_lg, reste)
                    stapel.append(akt)
                    akt = _Stapel(pk)
                    continue
                stapel.append(akt)
                akt = _Stapel(pk)
                if lg.versetzt:
                    lg.versetzt, lg.dz = False, None
            akt.dazu(pk, lg)
        if akt.lagen:
            stapel.append(akt)
    min_h = min((st.lagen[0].h for st in stapel), default=0.0)
    min_g = min((pk.gewicht(lg) for st in stapel for lg in st.lagen), default=0.0)

    def offen(pal):
        return pal.h + pk.p["zl"] + min_h <= pk.frei + EPS and (pk.last is None or pal.g + min_g <= pk.last + 1e-6)

    pals, auf = [], []                # auf: Ladungsträger, die noch Platz haben könnten
    if art == "folge":
        for st in stapel:
            if pals and _passt(pk, pals[-1], st):
                pals[-1].stapeln(pk, st)
            else:
                pals.append(st)
        return [p.lagen for p in pals]
    if art == "sorte":                 # je Hauptsorte eigene Ladungsträger, angefangene aufeinander (wie bisher)
        voll = [st for st in stapel if not offen(st)]
        rest = sorted((st for st in stapel if offen(st)), key=lambda st: -st.h)
        for st in rest:
            ziel = next((q for q in auf if _passt(pk, q, st)), None)
            if ziel is None:
                pals.append(st)
                auf.append(st)
            else:
                ziel.stapeln(pk, st)
                if not offen(ziel):
                    auf.remove(ziel)
        return [p.lagen for p in voll + pals]
    stapel.sort(key=lambda st: (-st.lagen[0].reihen[0].teile[0][2], -st.h))
    for st in stapel:
        kand = [p for p in auf if _passt(pk, p, st)]
        if not kand:
            pals.append(st)
            if offen(st):
                auf.append(st)
            continue
        if art == "paar":
            kand = [p for p in kand if p.arts & st.arts] or kand
            ziel = min(kand, key=lambda p: pk.frei - p.h - st.h)
        else:
            ziel = kand[0]
        ziel.stapeln(pk, st)
        if not offen(ziel):
            auf.remove(ziel)
    return [p.lagen for p in pals]


def variante(z, p, frei, last, ein, stuecke, code, versetzen=True):
    """Eine Variante packen: (Packer, [[Lage]] je Ladungsträger). Neue Lagen nur auf komplett volle Lagen: liegt
    nach dem Verteilen eine angefangene Lage unter einer anderen (z. B. versetzte Rundrohre ohne ihre Vorlage), wird
    ohne Versatz neu gepackt; bleibt es, kommt alles darüber auf einen neuen Ladungsträger."""
    pk = Packer(z, p, frei, last, ein, stuecke)
    pk.versetzen = versetzen
    rest = [e["n"] for e in ein]
    reihenfolge = sorted(range(len(ein)), key=lambda i: (-ein[i]["x"], -(ein[i]["quer"] or (0, 0))[0], i))
    mischen = {"A": None, "B": "alle", "C": "alle", "D": "rest"}[code]
    if p["max_artikel"] == 1:
        mischen = None
    bloecke = _lagen_bauen(pk, rest, reihenfolge, mischen)
    art = {"A": "sorte", "B": "folge", "C": "ffd", "D": "paar"}[code]
    pals = _in_paletten(pk, bloecke, art)
    # unten das Lange und Schwere
    for pal in pals:                            # unten das Lange und Schwere, die angefangene Lage oben
        pal.sort(key=lambda lg: (not pk.voll(lg), -max(pk.E[t[0]]["x"] for r in lg.reihen for t in r.teile),
                                 -pk.gewicht(lg)))
        _versetzt_pruefen(pal)                  # Reihenfolge geändert: versetzt nur direkt über der Vorlage
    if any(not pk.voll(lg) for pal in pals for lg in pal[:-1]):
        if versetzen:
            return variante(z, p, frei, last, ein, stuecke, code, versetzen=False)
        neu = []
        for pal in pals:
            akt = []
            for lg in pal:
                akt.append(lg)
                if not pk.voll(lg):
                    neu.append(akt)
                    akt = []
            if akt:
                neu.append(akt)
        pals = neu
    return pk, pals


# ------------------------------------------------------------------ Teile (Geometrie) und Prüfung
def teile(pk, pal):
    """Einzelteile eines Ladungsträgers: [dict(e (Einheit), k (Artikel), x0, x1, y0, y1, z0, z1, rund (Ø oder None),
    lage (Nr. ab 1), innen_von (Index des äußeren Teils oder None))] im Koordinatensystem des Ladungsträgers
    (x entlang der langen Seite 0 … Länge, y quer 0 … Breite, z ab Ladefläche)."""
    p, a = pk.p, pk.a
    out = []
    z0 = 0.0
    for nr, lg in enumerate(pal, start=1):
        if nr > 1:
            z0 = z0 + (lg.dz if lg.versetzt else pal[nr - 2].h + p["zl"])
        if lg.achse == "l":
            y = p["rand"] + (lg.reihen[0].b / 2 if lg.versetzt else 0.0)
            for rh in lg.reihen:
                laenge = rh.laenge(a)
                x = (p["pl"] - laenge) / 2
                for e_i, n, xl, (b, h) in rh.teile:
                    for _ in range(n):
                        _teil(pk, out, e_i, x, x + xl, y, y + b, z0, z0 + h, nr)
                        x += xl + a
                y += rh.b + a
        else:
            gesamt = lg.breite(a)
            x = (p["pl"] - gesamt) / 2
            for rh in lg.reihen:
                y = p["rand"]
                for e_i, n, xl, (b, h) in rh.teile:
                    for _ in range(n):
                        _teil(pk, out, e_i, x, x + b, y, y + xl, z0, z0 + h, nr, quer=True)
                        y += xl + a
                x += rh.b + a
    return out


def _teil(pk, out, e_i, x0, x1, y0, y1, z0, z1, lage, quer=False):
    e = pk.E[e_i]
    rund = e.get("rund") if not e.get("stapel") else None
    out.append(dict(e=e_i, k=e["sorte"][0], x0=x0, x1=x1, y0=y0, y1=y1, z0=z0, z1=z1, rund=rund, lage=lage,
                    innen_von=None, quer=quer, stapel=e.get("stapel"), verzahnt=bool(e.get("verzahnt"))))
    # verschachtelt (U in U): jedes innere Teil liegt in der Öffnung des vorigen, auf dessen Steg, quer mittig
    for k, form in e.get("innen") or ():
        o = out[-1]
        oi = len(out) - 1
        w = _n((pk.S[o["k"]].get("profil") or (0, 0, 0, 0))[3])
        laenge = (pk.S[k].get("masse") or (0,))[0]
        ob = (o["x1"] - o["x0"]) if quer else (o["y1"] - o["y0"])       # Breite des äußeren quer zur Länge
        oh = o["z1"] - o["z0"]
        c1, c2 = (form[1], form[1]) if form[0] == "kreis" else sorted(form[1:])
        if ob >= oh:            # Öffnung oben: inneres flach, auf dem Steg
            qb, qh = c2, c1
            q0, zz = ((o["x0"] + o["x1"]) if quer else (o["y0"] + o["y1"])) / 2 - qb / 2, o["z0"] + w
        else:                   # Öffnung seitlich: inneres hochkant am Steg
            qb, qh = c1, c2
            q0, zz = (o["x0"] if quer else o["y0"]) + w, (o["z0"] + o["z1"]) / 2 - qh / 2
        rd = form[1] if form[0] == "kreis" else None
        if not quer:
            mx = (o["x0"] + o["x1"]) / 2
            out.append(dict(e=e_i, k=k, x0=mx - laenge / 2, x1=mx + laenge / 2, y0=q0, y1=q0 + qb, z0=zz,
                            z1=zz + qh, rund=rd, lage=lage, innen_von=oi, quer=False, stapel=None))
        else:
            my = (o["y0"] + o["y1"]) / 2
            out.append(dict(e=e_i, k=k, x0=q0, x1=q0 + qb, y0=my - laenge / 2, y1=my + laenge / 2, z0=zz,
                            z1=zz + qh, rund=rd, lage=lage, innen_von=oi, quer=True, stapel=None))


def pruefen(pk, pal, liste=None):
    """Geometrische Prüfung eines Ladungsträgers: [Fehlertext] (leer = in Ordnung)."""
    p = pk.p
    t = liste if liste is not None else teile(pk, pal)
    fehler = []
    ymin, ymax = p["rand"] - 1e-3, p["pb"] - p["rand"] + 1e-3
    for i, s in enumerate(t):
        if s["innen_von"] is not None:
            o = t[s["innen_von"]]
            if not (o["x0"] - 1e-3 <= s["x0"] and s["x1"] <= o["x1"] + 1e-3 and o["y0"] - 1e-3 <= s["y0"]
                    and s["y1"] <= o["y1"] + 1e-3 and o["z0"] - 1e-3 <= s["z0"] and s["z1"] <= o["z1"] + 1e-3):
                fehler.append(f"Teil {i + 1}: verschachteltes Teil ragt aus dem äußeren heraus")
            continue
        if s["y0"] < ymin or s["y1"] > ymax:
            fehler.append(f"Teil {i + 1}: über die Breite ({_mm(s['y0'])}–{_mm(s['y1'])} mm, erlaubt "
                          f"{_mm(p['rand'])}–{_mm(p['pb'] - p['rand'])} mm)")
        laenge = s["x1"] - s["x0"]
        grenze = p["ueber"] if laenge <= pk.L + EPS else max(p["ueber"], (pk.lmax - p["pl"]) / 2)
        if s["x0"] < -grenze - 1e-3 or s["x1"] > p["pl"] + grenze + 1e-3:
            fehler.append(f"Teil {i + 1}: Überstand {_mm(max(-s['x0'], s['x1'] - p['pl']))} mm über "
                          f"{_mm(grenze)} mm")
        if s["z1"] > pk.frei + 1e-3:
            fehler.append(f"Teil {i + 1}: höher als erlaubt ({_mm(s['z1'])} > {_mm(pk.frei)} mm)")
    aussen = sorted((s for s in t if s["innen_von"] is None), key=lambda s: s["y0"])
    aktiv, a = [], pk.a
    for s in aussen:
        aktiv = [o for o in aktiv if o["y1"] + a > s["y0"] + 1e-3]
        for o in aktiv:
            g = a if o["lage"] == s["lage"] else 0.0       # Mindestabstand in der Lage, Lagen liegen aufeinander
            if o["x1"] + g <= s["x0"] + 1e-3 or s["x1"] + g <= o["x0"] + 1e-3 or o["y1"] + g <= s["y0"] + 1e-3:
                continue
            if o["z1"] <= s["z0"] + 1e-3 or s["z1"] <= o["z0"] + 1e-3:
                continue
            if s["rund"] and o["rund"]:
                if s["quer"] == o["quer"]:
                    ds = (((s["y0"] + s["y1"]) - (o["y0"] + o["y1"])) / 2 if not s["quer"]
                          else ((s["x0"] + s["x1"]) - (o["x0"] + o["x1"])) / 2)
                    dz = ((s["z0"] + s["z1"]) - (o["z0"] + o["z1"])) / 2
                    if math.hypot(ds, dz) + 1e-3 >= (s["rund"] + o["rund"]) / 2 + (g if abs(dz) < 1e-3 else 0.0):
                        continue
            echt = not (o["x1"] <= s["x0"] + 1e-3 or s["x1"] <= o["x0"] + 1e-3 or o["y1"] <= s["y0"] + 1e-3)
            fehler.append(f"{'Überschneidung' if echt else 'Mindestabstand unterschritten'}: Teil {t.index(o) + 1} "
                          f"und Teil {t.index(s) + 1}")
            if len(fehler) > 20:
                return fehler
        aktiv.append(s)
    return fehler


# ------------------------------------------------------------------ Kennzahlen
def kennzahlen(pk, pals, stuecke):
    """Kennzahlen einer Variante."""
    p = pk.p
    flaeche_pal = (p["pl"] * p["pb"]) or 1.0
    fl, vol, arts, ueber = [], [], [], 0.0
    for pal in pals:
        lagen_fl = []
        for lg in pal:
            f = 0.0
            for rh in lg.reihen:
                f += rh.b * min(rh.laenge(pk.a), pk.L)
            lagen_fl.append(min(1.0, f / flaeche_pal))
        fl.append(sum(lagen_fl) / len(lagen_fl) if lagen_fl else 0.0)
        v = sum(n * xl * b * h for lg in pal for rh in lg.reihen for _, n, xl, (b, h) in rh.teile)
        hh = _hoehe(pal, p["zl"]) or 1.0
        vol.append(min(1.0, v / (flaeche_pal * hh)))
        arts.append(len({k for lg in pal for r in lg.reihen for x in r.teile for k in pk.E[x[0]]["artikel"]}))
        for lg in pal:
            if lg.achse == "l":
                for rh in lg.reihen:
                    ueber = max(ueber, (rh.laenge(pk.a) - p["pl"]) / 2)
    return dict(anzahl=len(pals), flaeche=sum(fl) / len(fl) if fl else 0.0, volumen=sum(vol) / len(vol) if vol
                else 0.0, artikel_max=max(arts) if arts else 0, artikel_mittel=sum(arts) / len(arts) if arts else 0.0,
                ueberstand=max(0.0, ueber))


def bewerten(kz, sorten):
    """Sortierschlüssel (kleiner = besser): wenigste Packstücke, dann je nach Sortenreinheit Artikel je Packstück
    bzw. Auslastung."""
    if sorten == "stark":
        return (kz["anzahl"], kz["artikel_mittel"], -kz["volumen"])
    if sorten == "aus":
        return (kz["anzahl"], -kz["volumen"], kz["artikel_mittel"])
    return (kz["anzahl"], round(kz["artikel_mittel"], 1), -round(kz["volumen"], 2))


# ------------------------------------------------------------------ Packliste (Anschluss an paletten.packen)
def _signatur(pal):
    return tuple((lg.achse, lg.versetzt, round(lg.h, 3), tuple((round(r.b, 3), tuple((t[0], t[1]) for t in r.teile))
                                                                for r in lg.reihen)) for lg in pal)


def _als_liste(pk, pal, cache):
    """Ladungsträger im Format von paletten._fertig, mit Lagen, Teilen und Prüfung (kern3)."""
    inhalt, lagen_je = {}, {}
    for nr, lg in enumerate(pal):
        for rh in lg.reihen:
            for e_i, n, _, _ in rh.teile:
                for k, je in pk.E[e_i]["artikel"].items():
                    inhalt[k] = inhalt.get(k, 0) + n * je
                    lagen_je.setdefault(k, set()).add(nr)
    sig = _signatur(pal)
    if sig not in cache:
        t = teile(pk, pal)
        cache[sig] = (t, pruefen(pk, pal, t))
    t, fehler = cache[sig]
    reihenfolge = sorted(inhalt, key=lambda k: (min(lagen_je[k]), k))
    lagen = [dict(nr=j + 1, achse="längs" if lg.achse == "l" else "quer", versetzt=lg.versetzt, hoehe=lg.h,
                  voll=pk.voll(lg),
                  stueck={k: sum(n * pk.E[e]["artikel"].get(k, 0) for r in lg.reihen for e, n, _, _ in r.teile)
                          for k in reihenfolge if j in lagen_je[k]}) for j, lg in enumerate(pal)]
    return dict(inhalt=[[k, inhalt[k]] for k in reihenfolge], aufbau=[(k, inhalt[k], len(lagen_je[k]))
                                                                      for k in reihenfolge],
                hoehe=_hoehe(pal, pk.p["zl"]), unbekannt=False,
                kern3=dict(kern=3, lagen=lagen, teile=t, pruefung=fehler, grenzen=dict(
                    laenge=pk.p["pl"], breite=pk.p["pb"], ueberstand=pk.p["ueber"], rand=pk.p["rand"],
                    abstand=pk.p["abstand"], hoehe=pk.frei)))


def _ohne(items, last):
    """Teile ohne Maße oder mit Stück je Palette von Hand: je Position eigene Ladungsträger (wie bisher)."""
    out = []
    for it in items:
        rest, plan = it["n"], it["plan"]
        while rest > 0:
            n = rest if plan is None else min(rest, plan.voll)
            if last is not None and it["g"] > EPS:
                n = min(n, int((last + 1e-7) // it["g"]))
            n = max(1, n)
            out.append(dict(inhalt=[[it["k"], n]], aufbau=[(it["k"], n, 1 if plan else 0)],
                            hoehe=plan.hoehe(1) if plan else 0.0, unbekannt=plan is None))
            rest -= n
    return out


def _lagen_text(pk, e):
    bl = pk.beste_lage(e, e["n"]) if e["quer"] else None
    if bl is None:
        return ""
    achse, _, n, r, _ = bl
    t = f"{n} × {r} Stück ({'längs' if achse == 'l' else 'quer'})" if n > 1 else f"{r} Stück nebeneinander"
    if e.get("innen"):
        t += ", darin " + ", ".join(f"Pos. {pk.S[k]['pos'] or '?'}" for k, _ in e["innen"])
    if e.get("verzahnt"):
        t += f", je {e['stapel']} U verzahnt"
    elif e.get("stapel"):
        t += f", je {e['stapel']} Winkel ineinander"
    return t


def _versetzt_pruefen(pal):
    """Versetzte Lagen nur direkt über ihrer vollen Vorlage."""
    for j, lg in enumerate(pal):
        if lg.versetzt and (j == 0 or pal[j - 1].versetzt or not pal[j - 1].reihen
                            or pal[j - 1].reihen[0].teile[0][0] != lg.reihen[0].teile[0][0]
                            or len(pal[j - 1].reihen) < len(lg.reihen)):
            lg.versetzt, lg.dz = False, None


def verschieben(pk, pals, ops, off=0):
    """Lagen von Hand verschieben: ops [[von Packstück, Lage, nach Packstück (0 = neues)]] (Nummern der ganzen
    Packliste, off = Packstücke davor). Jeder Schritt wird geprüft (Höhe, Gewicht, Artikel); was nicht passt, bleibt
    und kommt als Hinweis zurück. Leere Packstücke entfallen. Ergebnis: Hinweise."""
    hinweise = []
    for op in ops or ():
        try:
            von, lage, nach = (int(x) for x in op)
        except (TypeError, ValueError):
            continue
        i, j = von - 1 - off, nach - 1 - off
        if not (0 <= i < len(pals)) or not (0 < lage <= len(pals[i])) or (nach and not 0 <= j < len(pals)) or i == j:
            continue
        lg = pals[i][lage - 1]
        rest = pals[i][:lage - 1] + pals[i][lage:]
        ziel = (pals[j] if nach else []) + [lg]
        sicher = [(x, x.versetzt, x.dz) for x in rest + ziel]
        _versetzt_pruefen(rest)
        _versetzt_pruefen(ziel)
        ok = all(pk.voll(x) for x in ziel[:-1]) and all(pk.voll(x) for x in rest[:-1]) and \
            _hoehe(ziel, pk.p["zl"]) <= pk.frei + EPS and (
            pk.last is None or sum(pk.gewicht(x) for x in ziel) <= pk.last + 1e-6)
        if ok and pk.p["max_artikel"]:
            ok = len({k for x in ziel for r in x.reihen for t in r.teile for k in pk.E[t[0]]["artikel"]}) <= \
                pk.p["max_artikel"]
        if not ok:
            for x, vs, dz in sicher:
                x.versetzt, x.dz = vs, dz
            hinweise.append(f"Lage {lage} von Packstück {von} passt nicht auf "
                            f"{'Packstück ' + str(nach) if nach else 'ein neues Packstück'} (Höhe, Gewicht, Artikel "
                            "oder Lage darunter nicht voll): nicht verschoben")
            continue
        pals[i] = rest
        if nach:
            pals[j] = ziel
        else:
            pals.append(ziel)
    pals[:] = [p for p in pals if p]
    return hinweise


def packen(leer, stuecke, gruppen, std, v, hinweise, fertig, max_je=None):
    """Packliste mit Packkern 3.0 (aus paletten.packen, gleiche Ergebnisform) und den Varianten A–D."""
    from . import paletten as pt
    erg = {c: dict(paletten=[], je_lht={}, kz=[]) for c in VARIANTEN}
    hand = v.get("hand") if isinstance(v.get("hand"), dict) else {}
    hand_var = hand.get("variante") if hand.get("variante") in VARIANTEN else None
    for lht_id, (z, items) in sorted(gruppen.items(), key=lambda x: (x[0] != (std or {}).get("lht_id"), x[0])):
        p = parameter(z, v)
        frei, last = pt.stapelhoehe(z, v), pt.nutzlast(z, v)
        mit = [it for it in items if not (it["plan"] is not None and it["plan"].hand) and stuecke[it["k"]]["masse"]
               and p["pl"] and p["pb"] and frei > 0]
        ohne = [it for it in items if not any(it is m for m in mit)]
        # Patrick 25.11.2026: je Packstück nur ein Grundwerkstoff (Stahl zu Stahl, Edelstahl zu Edelstahl …)
        sorten = {}
        for it in mit:
            sorten.setdefault(stuecke[it["k"]].get("werkstoff") or "", []).append(it["k"])
        teile_ein = [einheiten(stuecke, ks, p, frei) for _, ks in sorted(sorten.items())]
        for c in VARIANTEN:
            liste, extra, cache = [], [], {}
            for ein in teile_ein:
                pk, pals = variante(z, p, frei, last, ein, stuecke, c)
                if c == hand_var and hand.get("verschieben"):
                    hinweise += verschieben(pk, pals, hand["verschieben"], len(erg[c]["paletten"]) + len(liste))
                for e_i, n in sorted(pk.uebrig.items()):
                    for k, je in pk.E[e_i]["artikel"].items():
                        extra.append(dict(k=k, n=n * je, g=stuecke[k]["gewicht"] or 0.0, plan=None))
                        if c == "A":
                            hinweise.append(f"Pos. {stuecke[k]['pos'] or '?'}: passt mit {_mm(pk.E[e_i]['x'])} mm "
                                            f"nicht auf {z.get('bezeichnung') or lht_id} (max. {_mm(pk.lmax)} mm bzw. "
                                            "Höhe): nur nach Gewicht, Sonderladung prüfen")
                liste += [_als_liste(pk, pal, cache) for pal in pals]
                if pals:
                    erg[c]["kz"].append(kennzahlen(pk, pals, stuecke))
                if c == "A":
                    for e in ein:
                        t = _lagen_text(pk, e)
                        if t:
                            stuecke[e["sorte"][0]]["plan_text"] = t
                        for k, _ in e.get("innen") or ():
                            stuecke[k]["plan_text"] = f"verschachtelt in Pos. {stuecke[e['sorte'][0]]['pos'] or '?'}"
            liste += _ohne(ohne + extra, last)
            erg[c]["paletten"] += fertig(liste, lht_id, z, stuecke, v)
            erg[c]["je_lht"][lht_id] = len(liste)
    varianten = []
    for c, name in VARIANTEN.items():
        kz = erg[c]["kz"]
        n = sum(k["anzahl"] for k in kz) or 1
        gesamt = dict(anzahl=len(erg[c]["paletten"]),
                      flaeche=sum(k["flaeche"] * k["anzahl"] for k in kz) / n,
                      volumen=sum(k["volumen"] * k["anzahl"] for k in kz) / n,
                      artikel_max=max((k["artikel_max"] for k in kz), default=0),
                      artikel_mittel=sum(k["artikel_mittel"] * k["anzahl"] for k in kz) / n,
                      ueberstand=max((k["ueberstand"] for k in kz), default=0.0))
        fehler = [f"Packstück {j + 1}: {f}" for j, pal in enumerate(erg[c]["paletten"]) for f in pal.get("pruefung")
                  or ()]
        varianten.append(dict(code=c, name=name, **gesamt, fehler=fehler, paletten=erg[c]["paletten"],
                              je_lht=erg[c]["je_lht"]))
    fest = hand_var or (v["modus"][0] if v["modus"] != AUTOMATISCH else None)
    ok = [x for x in varianten if not x["fehler"]] or varianten
    beste = min(ok, key=lambda x: (bewerten(x, v["sorten"]), x["code"]))
    for x in varianten:
        x["beste"] = x is beste
        for nr, pal in enumerate(x["paletten"], start=1):
            pal["nr"] = nr
    gewaehlt = next((x for x in varianten if x["code"] == fest), beste)
    if gewaehlt["fehler"]:
        hinweise.append("Packkern: geometrische Prüfung meldet " + "; ".join(gewaehlt["fehler"][:3]))
    netto = sum(s["gewicht"] * s["stueck"] for s in stuecke if s["gewicht"] is not None)
    return dict(leer, paletten=gewaehlt["paletten"], anzahl=len(gewaehlt["paletten"]), je_lht=gewaehlt["je_lht"],
                netto=netto, kern=3, variante=gewaehlt["code"], varianten=varianten)
