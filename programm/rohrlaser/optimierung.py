"""Stangenoptimierung: teilt die Teile je Profil + Werkstoff + Stangenlänge auf möglichst wenige Stangen auf.

Regeln:
- Belegung = Endbeschnitt + Teile + Trennungen + Schnittverlust des letzten Schnitts;
  frei bleiben muss der Greiferrest.
- Trennung zwischen zwei Teilen: beide zugewandten Enden gerade = 1 gemeinsamer Schnitt
  (1 × Schnittverlust), sonst 2 Schnitte (2 × Schnittverlust + Abstand getrennte Schnitte).
- Teile dürfen gedreht werden. Keine Restlagerverwaltung: Reste sind Verschnitt.

Verfahren: First-Fit- und Best-Fit-Decreasing mit Auflösen schwach belegter Stangen; ist das nicht nachweislich
optimal, rechnet die Schnittmuster-Optimierung (Spaltengenerierung nach Gilmore-Gomory: gleiche Teile als Typ,
Schnittmuster je Stange, lineares Programm über die Muster) eine Einteilung und eine Schranke; danach für kleine
Gruppen die exakte Suche. Alle Grenzen sind Schrittzahlen, keine Zeiten: das Ergebnis ist auf jedem Rechner gleich.
"""
import math
from dataclasses import dataclass, field, replace

from . import normprofile

EPS = 1e-6
EXAKT_MAX_TEILE = 60     # exakte Suche nur für Gruppen bis zu so vielen Teilen
EXAKT_MAX_KNOTEN = 20000  # Suchschritte je Gruppe, danach gilt das beste bis dahin gefundene Ergebnis
MUSTER_MAX_RUNDEN = 300    # neue Schnittmuster je Gruppe
MUSTER_MAX_KNOTEN = 50000  # Suchschritte je Suche nach dem besten Schnittmuster


@dataclass(frozen=True)
class Teil:
    zeile: int          # Bezug auf die Position (Index im Angebot)
    pos: object
    artikel: str
    nr: int             # laufende Nummer innerhalb der Position (1..Stückzahl)
    laenge: float
    a_gerade: bool      # Anfang (Ende A) gerade
    b_gerade: bool
    a_schnitt: float    # Schnittlänge Ende A [mm] (für Einsparung)
    b_schnitt: float


@dataclass
class Gruppe:
    profil: str
    werkstoff: str
    stange: float
    endbeschnitt: float
    greiferrest: float
    kerf: float
    abstand: float
    oberflaeche: str = ""    # leer = roh; unterschiedliche Oberflächen nie auf derselben Stange
    teile: list = field(default_factory=list)
    bewiesen: bool = False   # Stangenzahl ist nachweislich minimal
    schranke: int = 0        # nachgewiesene Mindestzahl Stangen (Untergrenze oder Schranke der Schnittmuster)

    @property
    def nutzbar_bis(self):
        return self.stange - self.greiferrest


# ------------------------------------------------------------------ Belegung einer Stange
def trennung(kerf, abstand, ende_gerade, anfang_gerade):
    """Materialverbrauch zwischen zwei Teilen."""
    return kerf if (ende_gerade and anfang_gerade) else 2 * kerf + abstand


def lage(teil, gedreht):
    """(Anfang gerade, Ende gerade, Schnitt Anfang, Schnitt Ende) in Lage auf der Stange."""
    if gedreht:
        return teil.b_gerade, teil.a_gerade, teil.b_schnitt, teil.a_schnitt
    return teil.a_gerade, teil.b_gerade, teil.a_schnitt, teil.b_schnitt


def anordnen(teile):
    """Reihenfolge und Lage so wählen, dass möglichst viele gerade Enden aneinanderliegen.
    Schräge Enden kommen an Stangenanfang/-ende, übrige schräge Enden werden paarweise
    gegeneinander gelegt. Ergebnis: Liste (Teil, gedreht)."""
    ss = [t for t in teile if t.a_gerade and t.b_gerade]
    sn = [t for t in teile if t.a_gerade != t.b_gerade]
    nn = [t for t in teile if not t.a_gerade and not t.b_gerade]
    # Lage so, dass das schräge Ende vorn (N_vorn) bzw. hinten (N_hinten) liegt
    n_vorn = lambda t: (t, t.a_gerade)       # gedreht, wenn A gerade ist -> B (schräg) vorn
    n_hinten = lambda t: (t, not t.a_gerade)  # gedreht, wenn A schräg ist -> A hinten
    folge, rest_sn, rest_nn = [], list(sn), list(nn)
    start = n_vorn(rest_sn.pop(0)) if rest_sn else ((rest_nn.pop(0), False) if rest_nn else None)
    ende = n_hinten(rest_sn.pop(0)) if rest_sn else ((rest_nn.pop(0), False) if rest_nn else None)
    if start:
        folge.append(start)
    folge += [(t, False) for t in ss]
    # restliche: S-N | N-N ... | N-S | S-N | N-S ...
    kette, i = [], 0
    while rest_sn:
        t = rest_sn.pop(0)
        if i % 2 == 0:
            kette.append(n_hinten(t))
            while rest_nn:
                kette.append((rest_nn.pop(0), False))
        else:
            kette.append(n_vorn(t))
        i += 1
    kette += [(t, False) for t in rest_nn]
    folge += kette
    if ende:
        folge.append(ende)
    return folge


def verbrauch(g, folge):
    """Position hinter dem letzten Schnitt (inkl. Schnittverlust) ab Stangenanfang."""
    pos = g.endbeschnitt
    vorher = None
    for t, gedreht in folge:
        a_ger, b_ger, _, _ = lage(t, gedreht)
        if vorher is not None:
            pos += trennung(g.kerf, g.abstand, vorher, a_ger)
        pos += t.laenge
        vorher = b_ger
    return pos + (g.kerf if folge else 0)


def passt(g, teile):
    return verbrauch(g, anordnen(teile)) <= g.nutzbar_bis + EPS


# ------------------------------------------------------------------ Packverfahren
def sortiert(teile):
    return sorted(teile, key=lambda t: (-t.laenge, t.zeile, t.nr))


def first_fit(g, teile):
    stangen = []
    for t in sortiert(teile):
        for s in stangen:
            if passt(g, s + [t]):
                s.append(t)
                break
        else:
            stangen.append([t])
    return stangen


def best_fit(g, teile):
    stangen = []
    for t in sortiert(teile):
        beste, rest_min = None, None
        for s in stangen:
            v = verbrauch(g, anordnen(s + [t]))
            if v <= g.nutzbar_bis + EPS and (rest_min is None or g.nutzbar_bis - v < rest_min):
                beste, rest_min = s, g.nutzbar_bis - v
        if beste is None:
            stangen.append([t])
        else:
            beste.append(t)
    return stangen


def aufloesen(g, stangen):
    """Schwach belegte Stangen auflösen, wenn alle ihre Teile in andere Stangen passen."""
    stangen = [list(s) for s in stangen]
    geaendert = True
    while geaendert and len(stangen) > 1:
        geaendert = False
        for s in sorted(stangen, key=lambda s: sum(t.laenge for t in s)):
            andere = [list(x) for x in stangen if x is not s]
            ok = True
            for t in sortiert(s):
                ziel = None
                for x in sorted(andere, key=lambda x: -verbrauch(g, anordnen(x))):
                    if passt(g, x + [t]):
                        ziel = x
                        break
                if ziel is None:
                    ok = False
                    break
                ziel.append(t)
            if ok:
                stangen = andere
                geaendert = True
                break
    return stangen


def gemeinsame_schnitte(folge):
    n = 0
    for (t1, d1), (t2, d2) in zip(folge, folge[1:]):
        if lage(t1, d1)[1] and lage(t2, d2)[0]:
            n += 1
    return n


def gleichartig(a, b):
    return a.laenge == b.laenge and a.a_gerade == b.a_gerade and a.b_gerade == b.b_gerade


def exakt(g, ziel):
    """Exakte Suche (Branch and Bound) nach einer Einteilung mit weniger als `ziel` Stangen.
    Teile in der Reihenfolge von sortiert(), jedes Teil der Reihe nach in jede vorhandene Stange,
    dann in eine neue. Abgeschnitten wird, wenn selbst bei voller Nutzung aller freien Längen
    nicht weniger Stangen als bisher bestes Ergebnis möglich sind. Ergebnis: (Stangen oder None,
    Suche vollständig)."""
    teile = sortiert(g.teile)
    n = len(teile)
    nutz = g.nutzbar_bis - g.endbeschnitt
    bedarf = [t.laenge + g.kerf for t in teile]
    rest = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        rest[i] = rest[i + 1] + bedarf[i]
    ug = untergrenze(g)
    stangen, belegt, zu = [], [], [0] * n
    zustand = dict(beste=None, beste_n=ziel, knoten=0, abbruch=False)

    def suche(i):
        if i == n:
            zustand["beste"] = [list(s) for s in stangen]
            zustand["beste_n"] = len(stangen)
            return
        zustand["knoten"] += 1
        if zustand["knoten"] > EXAKT_MAX_KNOTEN:
            zustand["abbruch"] = True
            return
        frei = 0.0
        for b in belegt:
            frei += nutz - b
        neu = 0
        if rest[i] > frei + EPS:
            neu = math.ceil((rest[i] - frei) / nutz - EPS)
        if len(stangen) + neu >= zustand["beste_n"]:
            return
        t = teile[i]
        start = zu[i - 1] if i > 0 and gleichartig(teile[i - 1], t) else 0
        for s in range(start, len(stangen)):
            if belegt[s] + bedarf[i] > nutz + EPS or not passt(g, stangen[s] + [t]):
                continue
            stangen[s].append(t)
            belegt[s] += bedarf[i]
            zu[i] = s
            suche(i + 1)
            stangen[s].pop()
            belegt[s] -= bedarf[i]
            if zustand["abbruch"] or zustand["beste_n"] <= ug:
                return
        if len(stangen) + 1 < zustand["beste_n"]:
            stangen.append([t])
            belegt.append(bedarf[i])
            zu[i] = len(stangen) - 1
            suche(i + 1)
            stangen.pop()
            belegt.pop()

    suche(0)
    return zustand["beste"], not zustand["abbruch"] or zustand["beste_n"] <= ug


def optimiere(g):
    """Ergebnis: Liste von Stangen, je Stange die angeordnete Folge [(Teil, gedreht)].
    Setzt g.bewiesen, wenn die Stangenzahl nachweislich minimal ist."""
    kandidaten = []
    for verfahren in (first_fit, best_fit):
        st = aufloesen(g, verfahren(g, g.teile))
        folgen = [anordnen(s) for s in st]
        kandidaten.append((len(folgen), -sum(gemeinsame_schnitte(f) for f in folgen), folgen))
    kandidaten.sort(key=lambda k: (k[0], k[1]))
    folgen = kandidaten[0][2]
    g.schranke = untergrenze(g)
    g.bewiesen = len(folgen) <= g.schranke
    if not g.bewiesen:
        st, schranke = muster_optimierung(g)
        g.schranke = max(g.schranke, schranke)
        neu = [anordnen(s) for s in st]
        if sum(len(s) for s in st) == len(g.teile) and (len(neu), -sum(gemeinsame_schnitte(f) for f in neu)) < \
                (len(folgen), -sum(gemeinsame_schnitte(f) for f in folgen)):
            folgen = neu
        g.bewiesen = len(folgen) <= g.schranke
    if not g.bewiesen and len(g.teile) <= EXAKT_MAX_TEILE:
        st, g.bewiesen = exakt(g, len(folgen))
        if st is not None:
            folgen = [anordnen(s) for s in st]
    # Stangen mit der höchsten Belegung zuerst (Reststange zuletzt)
    folgen.sort(key=lambda f: (-verbrauch(g, f), f[0][0].zeile))
    return folgen


def bewertung(g, n_stangen):
    """Text für die Auswertung: wie nah das Ergebnis am Optimum liegt."""
    if n_stangen <= untergrenze(g):
        return "optimal (Untergrenze erreicht)"
    if n_stangen <= g.schranke:
        return "optimal (Schranke der Schnittmuster erreicht)"
    if g.bewiesen:
        return "optimal (alle Einteilungen geprüft)"
    return "nicht bewiesen (Suche begrenzt)"


# ------------------------------------------------------------------ Schnittmuster (Spaltengenerierung)
def typ(t):
    """Gleiche Teile (Länge, Enden, Schnittlängen) sind für die Schnittmuster ein Typ."""
    return (t.laenge, t.a_gerade, t.b_gerade, t.a_schnitt, t.b_schnitt)


def bestes_muster(g, typen, bedarf, wert):
    """Schnittmuster (Anzahl je Typ, höchstens der Bedarf) mit dem größten Gesamtwert, das auf eine Stange passt.
    Tiefensuche, je Typ zuerst die größte mögliche Anzahl; abgeschnitten wird, wenn selbst die freie Länge mit dem
    besten Wert je mm nicht mehr reicht. Ergebnis: (Muster, Suche vollständig)."""
    n = len(typen)
    beste, zahl, knoten = [None, -1.0], [0] * n, [0]
    q_ab = [max([wert[j] / typen[j].laenge for j in range(i, n) if bedarf[j]] or [0.0]) for i in range(n + 1)]
    # Die Trennungen hängen nur davon ab, wie viele Teile beide, ein oder kein gerades Ende haben (anordnen ordnet
    # danach); der Verbrauch ist also Länge der Teile + Zuschlag je (Anzahl gerade-gerade, gerade-schräg, schräg).
    art = [2 if t.a_gerade and t.b_gerade else (1 if t.a_gerade or t.b_gerade else 0) for t in typen]
    vertreter = {a: next(t for t in typen if art[typen.index(t)] == a) for a in set(art)}
    zuschlag = {}

    def passt_zahl(anz, laenge):
        if anz not in zuschlag:
            null = [replace(vertreter[a], laenge=0.0) for a in (2, 1, 0) for _ in range(anz[2 - a])]
            zuschlag[anz] = verbrauch(g, anordnen(null))
        return zuschlag[anz] + laenge <= g.nutzbar_bis + EPS

    def suche(i, w, laenge):
        knoten[0] += 1
        if w > beste[1] + 1e-9:
            beste[0], beste[1] = list(zahl), w
        if i == n or knoten[0] > MUSTER_MAX_KNOTEN:
            return
        if w + q_ab[i] * (g.nutzbar_bis - g.endbeschnitt - laenge) <= beste[1] + 1e-9:
            return
        anz = [0, 0, 0]
        for j in range(i):
            anz[2 - art[j]] += zahl[j]
        while zahl[i] < bedarf[i]:
            anz[2 - art[i]] += 1
            if not passt_zahl(tuple(anz), laenge + typen[i].laenge * (zahl[i] + 1)):
                break
            zahl[i] += 1
        while True:
            suche(i + 1, w + wert[i] * zahl[i], laenge + typen[i].laenge * zahl[i])
            if zahl[i] == 0:
                break
            zahl[i] -= 1

    suche(0, 0.0, 0.0)
    return beste[0], knoten[0] <= MUSTER_MAX_KNOTEN


def simplex_max(c, a, b):
    """Lineares Programm max c·y unter a·y <= b, y >= 0 mit b >= 0 (Simplex mit Tableau, Regel von Bland gegen
    Kreisen). Ergebnis: (y, Zielwert, Schattenpreise der Zeilen, gelöst)."""
    m, n = len(a), len(c)
    tab = [list(a[i]) + [1.0 if j == i else 0.0 for j in range(m)] + [b[i]] for i in range(m)]
    z = [-x for x in c] + [0.0] * (m + 1)
    basis = [n + i for i in range(m)]
    geloest = False
    for _ in range(20 * (m + n) + 100):
        e = next((j for j in range(n + m) if z[j] < -1e-9), None)
        if e is None:
            geloest = True
            break
        r, best = None, None
        for i in range(m):
            if tab[i][e] > 1e-9:
                q = tab[i][-1] / tab[i][e]
                if best is None or q < best - 1e-12 or (abs(q - best) <= 1e-12 and basis[i] < basis[r]):
                    r, best = i, q
        if r is None:       # unbeschränkt: kommt bei Schnittmustern nicht vor (jeder Typ hat ein Muster)
            break
        p = tab[r][e]
        tab[r] = [x / p for x in tab[r]]
        for i in range(m):
            if i != r and abs(tab[i][e]) > 1e-12:
                f = tab[i][e]
                tab[i] = [x - f * y for x, y in zip(tab[i], tab[r])]
        f = z[e]
        z = [x - f * y for x, y in zip(z, tab[r])]
        basis[r] = e
    y = [0.0] * n
    for i, bi in enumerate(basis):
        if bi < n:
            y[bi] = tab[i][-1]
    return y, z[-1], z[n:n + m], geloest


def muster_optimierung(g):
    """Schnittmuster-Optimierung (Gilmore-Gomory). Das lineare Programm „möglichst wenige Stangen, jeder Typ
    mindestens so oft wie gebraucht“ wird über seine duale Form gelöst; neue Muster liefert bestes_muster mit den
    Schattenpreisen als Wert. Die abgerundete Lösung legt ganze Stangen fest, den Rest teilen Best-Fit, First-Fit
    und das beste Muster je Schritt auf. Ergebnis: (Stangen als Teilelisten, Schranke): die Schranke ist die
    aufgerundete LP-Lösung, wenn alle Suchen vollständig waren, sonst 0."""
    gruppen = {}
    for t in sortiert(g.teile):
        gruppen.setdefault(typ(t), []).append(t)
    keys = sorted(gruppen, key=lambda k: (-k[0], k))
    typen = [gruppen[k][0] for k in keys]
    bedarf = [len(gruppen[k]) for k in keys]
    n = len(typen)
    muster = []
    for i in range(n):              # Startmuster: je Typ so viele wie auf eine Stange passen
        k = 0
        while k < bedarf[i] and passt(g, [typen[i]] * (k + 1)):
            k += 1
        if k == 0:
            return [], 0            # passt nicht auf eine Stange (wird vorher aussortiert)
        muster.append(tuple(k if j == i else 0 for j in range(n)))
    vollstaendig = False
    for _ in range(MUSTER_MAX_RUNDEN):
        y, wert, x, geloest = simplex_max([float(d) for d in bedarf], [[float(v) for v in m] for m in muster],
                                          [1.0] * len(muster))
        if not geloest:
            break
        m, ganz = bestes_muster(g, typen, bedarf, [max(v, 0.0) for v in y])
        if m is None or sum(y[i] * m[i] for i in range(n)) <= 1 + 1e-7:
            vollstaendig = ganz
            break
        if tuple(m) in muster:
            break
        muster.append(tuple(m))
    schranke = math.ceil(wert - 1e-6) if vollstaendig and geloest else 0
    # ganze Stangen aus der LP-Lösung, Rest heuristisch
    rest, vorrat, stangen = list(bedarf), {k: list(v) for k, v in gruppen.items()}, []
    for m, xp in sorted(zip(muster, x), key=lambda a: (-a[1], a[0])):
        for _ in range(int(math.floor(xp + 1e-9))):
            if any(rest[i] < m[i] for i in range(n)):
                break
            stangen.append([vorrat[keys[i]].pop() for i in range(n) for _ in range(m[i])])
            rest = [r - c for r, c in zip(rest, m)]
    uebrig = [t for k in keys for t in vorrat[k]]
    if uebrig:
        h = Gruppe(g.profil, g.werkstoff, g.stange, g.endbeschnitt, g.greiferrest, g.kerf, g.abstand, g.oberflaeche,
                   uebrig)
        stangen += min((aufloesen(h, best_fit(h, uebrig)), aufloesen(h, first_fit(h, uebrig)), muster_folge(h)),
                       key=len)
    return aufloesen(g, stangen), schranke


def muster_folge(g):
    """Schritt für Schritt das Muster mit der größten belegten Länge (lange Teile etwas bevorzugt) so oft wie
    möglich schneiden."""
    gruppen = {}
    for t in sortiert(g.teile):
        gruppen.setdefault(typ(t), []).append(t)
    keys = sorted(gruppen, key=lambda k: (-k[0], k))
    typen = [gruppen[k][0] for k in keys]
    bedarf = [len(gruppen[k]) for k in keys]
    wert = [t.laenge ** 1.2 for t in typen]
    stangen = []
    while sum(bedarf):
        m, _ = bestes_muster(g, typen, bedarf, wert)
        if not m or not sum(m):         # kommt nicht vor (jedes Teil passt allein auf eine Stange)
            stangen += [[t] for k in keys for t in gruppen[k]]
            break
        for _ in range(min(bedarf[i] // m[i] for i in range(len(m)) if m[i])):
            stangen.append([gruppen[keys[i]].pop() for i in range(len(m)) for _ in range(m[i])])
            bedarf = [b - c for b, c in zip(bedarf, m)]
    return aufloesen(g, stangen)


def manuell(g):
    """Einfache manuelle Einteilung: Eingabereihenfolge, keine Drehung, Stange voll, dann nächste."""
    stangen, aktuell = [], []
    for t in sorted(g.teile, key=lambda t: (t.zeile, t.nr)):
        if aktuell and verbrauch(g, [(x, False) for x in aktuell + [t]]) > g.nutzbar_bis + EPS:
            stangen.append(aktuell)
            aktuell = []
        aktuell.append(t)
    if aktuell:
        stangen.append(aktuell)
    return stangen


def untergrenze(g):
    nutz = g.nutzbar_bis - g.endbeschnitt
    return math.ceil(sum(t.laenge + g.kerf for t in g.teile) / nutz - EPS) if g.teile else 0


# ------------------------------------------------------------------ Zuschnitt langer Lieferstangen
# Eine Lieferstange, die länger ist als die Maschine laden kann (z. B. 12.000 mm bei 6.500 mm), wird vom Lieferanten
# in Werkstücke geschnitten, die einzeln geladen werden. Werkstück = Endbeschnitt + Teile + Trennungen + letzter
# Schnittverlust + Greiferrest, auf ganze mm aufgerundet, höchstens die max. Stangenlänge der Maschine. Zwischen zwei
# Werkstücken geht der Schnittverlust des Zuschnitts verloren, der Rest der Lieferstange ist Verschnitt.
ZUSCHNITT_TEILUNG = 6    # Ziel-Werkstücklängen: Lieferlänge geteilt durch 1 … 6 (Schritte, keine Zeit)


def werkstueck_laenge(g, folge):
    """Länge des Werkstücks für eine Folge (ganze mm)."""
    return math.ceil(verbrauch(g, folge) + g.greiferrest - EPS)


def zuschnitt_belegt(laengen, saege):
    """Belegte Länge einer Lieferstange: Werkstücke + Zuschnitte dazwischen."""
    return sum(laengen) + saege * max(len(laengen) - 1, 0)


def zuschnitt_ziele(g, lieferlaenge, max_werkstueck, saege):
    """Ziel-Werkstücklängen, die ausprobiert werden: die max. Werkstücklänge und die Lieferlänge geteilt durch 2 … n
    (abzüglich der Zuschnitte), soweit das längste Teil hineinpasst. Längste zuerst."""
    noetig = g.endbeschnitt + max(t.laenge for t in g.teile) + g.kerf + g.greiferrest
    ziele = {int(min(max_werkstueck, math.floor((lieferlaenge - (n - 1) * saege) / n + EPS)))
             for n in range(1, ZUSCHNITT_TEILUNG + 1)}
    return sorted((z for z in ziele if z + EPS >= noetig), reverse=True)


def zuschnitt(g, lieferlaenge, max_werkstueck, saege):
    """Zweistufige Planung: Teile zu Werkstücken (Optimierung wie bei normalen Stangen, Stangenlänge = Ziel-
    Werkstücklänge), dann die Werkstücke auf Lieferstangen verteilen (dieselbe Optimierung: Werkstücke als Teile mit
    geraden Enden, Schnittverlust = Zuschnitt, ohne Endbeschnitt und Greiferrest). Je Ziel-Werkstücklänge eine
    Planung, es gilt die mit den wenigsten Lieferstangen, dann den wenigsten Werkstücken (Beladungen), dann den
    meisten gemeinsamen Schnitten. Ergebnis: Liste der Lieferstangen, je Lieferstange [(Werkstücklänge, Folge)];
    None, wenn ein Teil in kein Werkstück passt."""
    if not g.teile:
        return []
    beste = None
    for ziel in zuschnitt_ziele(g, lieferlaenge, max_werkstueck, saege):
        h = replace(g, stange=ziel, teile=list(g.teile))
        folgen = optimiere(h)
        laengen = [werkstueck_laenge(g, f) for f in folgen]
        # Stange um einen Zuschnitt länger: verbrauch() zählt nach dem letzten Werkstück noch einen Schnitt
        p = Gruppe(g.profil, g.werkstoff, lieferlaenge + saege, 0, 0, saege, 0, g.oberflaeche)
        p.teile = [Teil(i, None, "", 1, float(l), True, True, 0, 0) for i, l in enumerate(laengen)]
        if any(l > lieferlaenge + EPS for l in laengen):
            continue
        verteilt = optimiere(p)
        stangen = [[(laengen[t.zeile], folgen[t.zeile]) for t, _ in sorted(f, key=lambda x: (-x[0].laenge,
                                                                                            x[0].zeile))]
                   for f in verteilt]
        wert = (len(stangen), len(folgen), -sum(gemeinsame_schnitte(f) for f in folgen), -ziel)
        if beste is None or wert < beste[0]:
            beste = (wert, stangen)
    return beste[1] if beste else None


def pruefe_zuschnitt(g, stangen, lieferlaenge, max_werkstueck, saege):
    """Unabhängige Kontrolle des Zuschnitts: jedes Teil genau einmal, kein Werkstück über der max.
    Werkstücklänge oder kürzer als seine Belegung + Greiferrest, keine Lieferstange überbelegt."""
    ids = sorted((t.zeile, t.nr) for s in stangen for _, f in s for t, _ in f)
    if ids != sorted((t.zeile, t.nr) for t in g.teile):
        raise AssertionError(f"{g.profil}: Teile fehlen oder doppelt (Zuschnitt)")
    for s in stangen:
        for laenge, f in s:
            if laenge > max_werkstueck + EPS:
                raise AssertionError(f"{g.profil}: Werkstück {laenge:g} mm länger als die Maschine laden kann")
            if verbrauch(g, f) + g.greiferrest > laenge + EPS:
                raise AssertionError(f"{g.profil}: Werkstück überbelegt")
        if zuschnitt_belegt([l for l, _ in s], saege) > lieferlaenge + EPS:
            raise AssertionError(f"{g.profil}: Lieferstange überbelegt")


# ------------------------------------------------------------------ Profile
OFFEN = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl", "I-/H-Träger", "T-Profil")


def umfang(form, a, b, wand=None, flaeche=None):
    """Umfang des Querschnitts (Außenfläche je m Länge). Offene Profile: beide Seiten, aus Querschnittsfläche und
    Blechdicke (dünnwandig: 2 × Fläche / Dicke + 2 × Dicke an den Kanten), damit gilt es auch für C-Profile mit
    Abkantung und Profile mit Radien."""
    if form == "Rundrohr":
        return math.pi * a
    if form == "Quadratrohr":
        return 4 * a
    if form == "Rechteckrohr":
        return 2 * (a + (b or a))
    if form == "I-/H-Träger" and b:       # scharfkantig: Flansche außen und innen, Flanschkanten, Steg
        return 2 * a + 4 * b - 2 * (wand or 0)
    if form == "T-Profil" and b:
        return 2 * a + 2 * b
    if form in OFFEN and wand and flaeche:
        return 2 * flaeche / wand + 2 * wand
    return 0.0


def schnittlaenge(form, a, b, wand=None, flaeche=None):
    """Länge eines geraden Trennschnitts: Rohre = Außenumfang, offene Profile = halber Umfang (der Laser schneidet
    jede Wand nur einmal)."""
    u = umfang(form, a, b, wand, flaeche)
    return u / 2 if form in OFFEN else u


PROFILFORM = {"RR": "Rundrohr", "QR": "Quadratrohr", "RE": "Rechteckrohr", "U": "U-Profil", "C": "C-Profil",
              "L": "L-Profil", "FL": "Flachstahl", "I": "I-/H-Träger", "T": "T-Profil"}


def profil_aus_name(pid):
    """Profilform und Maße aus der Profil-ID, z. B. 'RR 42,4x2,0', 'QR 40x40x3', 'RE 60x40x3'.
    Ergebnis dict(form, a, b, wand) oder None, wenn der Name nicht nach dem Schema aufgebaut ist.
    """
    n = normprofile.daten(pid)
    if n is not None and n["flaeche"]:       # Normprofil, z. B. 'IPE 200', 'HEB 160', 'UPN 100', 'T 50'
        return dict(form=n["form"], a=n["h"], b=n["b"], wand=n["tw"], flaeche_manuell=n["flaeche"])
    kurz, _, rest = str(pid).strip().partition(" ")
    form = PROFILFORM.get(kurz.upper())
    zahlen = rest.replace(",", ".").replace("X", "x").split("x")
    try:
        z = [float(v) for v in zahlen]
    except ValueError:
        return None
    if form == "Rundrohr" and len(z) == 2:
        a, b, wand = z[0], None, z[1]
    elif form == "Quadratrohr" and len(z) == 3 and z[0] == z[1]:
        a, b, wand = z[0], None, z[2]
    elif form in ("Rechteckrohr", "U-Profil", "C-Profil", "L-Profil") and len(z) == 3:
        a, b, wand = z[0], z[1], z[2]
    elif form in ("I-/H-Träger", "T-Profil") and len(z) == 4:     # 'I h x b x Steg x Flansch'
        h, b, tw, tf = z
        if min(z) <= 0 or tw >= b or (2 if form == "I-/H-Träger" else 1) * tf >= h:
            return None
        fl = 2 * b * tf + (h - 2 * tf) * tw if form == "I-/H-Träger" else b * tf + (h - tf) * tw
        return dict(form=form, a=h, b=b, wand=tw, flaeche_manuell=round(fl, 1))
    elif form == "Flachstahl" and len(z) == 2:
        a, b, wand = z[0], None, z[1]
        return dict(form=form, a=a, b=b, wand=wand) if 0 < wand < a else None
    else:
        return None
    if a <= 0 or wand <= 0 or 2 * wand >= a:
        return None
    return dict(form=form, a=a, b=b, wand=wand)


def pruefe(gruppen, ergebnisse):
    """Unabhängige Kontrolle: keine Stange überbelegt, jedes Teil genau einmal eingeplant."""
    for g, folgen in zip(gruppen, ergebnisse):
        ids = sorted((t.zeile, t.nr) for f in folgen for t, _ in f)
        soll = sorted((t.zeile, t.nr) for t in g.teile)
        if ids != soll:
            raise AssertionError(f"{g.profil}: Teile fehlen oder doppelt")
        for f in folgen:
            if verbrauch(g, f) > g.nutzbar_bis + EPS:
                raise AssertionError(f"{g.profil}: Stange überbelegt")
