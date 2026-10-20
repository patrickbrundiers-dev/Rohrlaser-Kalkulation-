"""Stangenoptimierung: teilt die Teile je Profil + Werkstoff + Stangenlänge auf möglichst wenige Stangen auf.

Regeln:
- Belegung = Endbeschnitt + Teile + Trennungen + Schnittverlust des letzten Schnitts;
  frei bleiben muss der Greiferrest.
- Trennung zwischen zwei Teilen: beide zugewandten Enden gerade = 1 gemeinsamer Schnitt
  (1 × Schnittverlust), sonst 2 Schnitte (2 × Schnittverlust + Abstand getrennte Schnitte).
- Teile dürfen gedreht werden. Keine Restlagerverwaltung: Reste sind Verschnitt.
"""
import math
from dataclasses import dataclass, field

EPS = 1e-6
EXAKT_MAX_TEILE = 60     # exakte Suche nur für Gruppen bis zu so vielen Teilen
EXAKT_MAX_KNOTEN = 20000  # Suchschritte je Gruppe, danach gilt das beste bis dahin gefundene Ergebnis


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
    ug = untergrenze(g)
    g.bewiesen = len(folgen) <= ug
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
    if g.bewiesen:
        return "optimal (alle Einteilungen geprüft)"
    return "nicht bewiesen (Suche begrenzt)"


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


# ------------------------------------------------------------------ Profile
OFFEN = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl")


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
    if form in OFFEN and wand and flaeche:
        return 2 * flaeche / wand + 2 * wand
    return 0.0


def schnittlaenge(form, a, b, wand=None, flaeche=None):
    """Länge eines geraden Trennschnitts: Rohre = Außenumfang, offene Profile = halber Umfang (der Laser schneidet
    jede Wand nur einmal)."""
    u = umfang(form, a, b, wand, flaeche)
    return u / 2 if form in OFFEN else u


PROFILFORM = {"RR": "Rundrohr", "QR": "Quadratrohr", "RE": "Rechteckrohr", "U": "U-Profil", "C": "C-Profil",
              "L": "L-Profil", "FL": "Flachstahl"}


def profil_aus_name(pid):
    """Profilform und Maße aus der Profil-ID, z. B. 'RR 42,4x2,0', 'QR 40x40x3', 'RE 60x40x3'.
    Ergebnis dict(form, a, b, wand) oder None, wenn der Name nicht nach dem Schema aufgebaut ist.
    """
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
