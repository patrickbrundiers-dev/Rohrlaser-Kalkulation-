"""Nesting-Engine: Verschachtelungs-Strategien über der Stangenoptimierung (Master-Auftrag Verschachtelung auf
CAD/CAM-Niveau, Patrick 23.11.2026).

Bestandsanalyse (docs/system-audit/NESTING_2311.md): für EINE Stangenlänge ist optimierung.optimiere schon bewiesen
optimal (First-/Best-Fit-Decreasing, Schnittmuster nach Gilmore-Gomory, exakte Suche). Geld bleibt liegen, wo mehrere
Lieferlängen, ihre Preise und vorhandene Reststücke zusammenspielen. Diese Schicht rechnet deshalb je Stangengruppe
(Profil, Werkstoff, Oberfläche – nie gemischt) Pläne mit mehreren Längen und vergleicht sie:

  A  Minimaler Materialverbrauch   kleinste eingekaufte Stangenlänge in mm (Längen gemischt)
  B  Geringste Materialkosten      kleinster Einkaufspreis aus den Preisen je Lieferlänge (Längen gemischt)
  C  Maximale Reststückverwertung  vorhandene Reststücke zuerst (nur mit Lager UND Reststücken eingeschaltet,
                                   Patrick 23.11.2026 „Reste und Lager wie bisher nur optional“)
  D  Schnellste Fertigung          wenigste Beladungen, dann wenigste verschiedene Belegungen (Programme)
  E  Ausgewogen                    Bewertung in €: Material + Beladungen + € je verschiedene Belegung − Gutschrift
                                   für verwertbare Reststücke (nur mit Reststücken)

Verfahren (alle Grenzen sind Schrittzahlen, keine Zeiten: auf jedem Rechner dasselbe Ergebnis):
  - je Länge der bewiesene Einzelplan (optimiere),
  - Mischplan mit optimierung.vorrat_planen (mehrere Längen, beste Füllung, Schnittmuster),
  - „Schwanz neu verteilen“: die am schwächsten belegten 1 … SCHWANZ_MAX Stangen werden auf die günstigste
    Mischung der Längen verteilt (Mischungen nach Kosten aufsteigend, Materialschranke, je Mischung vorrat_planen),
  - Reststücke: je Rest das Schnittmuster mit der größten Teilelänge, der Rest der Teile wie Strategie B,
  - „Reste bündeln“: bei gleicher Stangenzahl Teile so umsetzen, dass der freie Platz auf wenigen Stangen
    zusammenkommt (verwertbares Reststück statt vieler kleiner Abfälle).
Jeder Plan wird unabhängig geprüft (pruefe): jedes Teil genau einmal, keine Stange überbelegt (Greiferrest bzw.
3D-Greifmaß frei), nicht mehr Stangen je Länge als verfügbar, jedes Reststück höchstens einmal, und die
Längenbilanz je Stange geht auf: Teile + Schnittverluste + Endbeschnitt + Rest = Stangenlänge.

Die Kosten kommen nur aus den Preisen, die der Aufrufer je Länge übergibt (rechnen: lieferstange_preis aus der
Materialdatenbank). Fehlt ein Preis, ist der Plan für Kosten „nicht bewertbar“ (nie 0 €). Ohne Qt, ohne Datenbank.
"""
import itertools
import math
from dataclasses import dataclass, field, replace

from . import optimierung as opt

EPS = 1e-6
A, B, C, D, E = "A", "B", "C", "D", "E"
# Nesting-Arbeitsplatz 2.0 (Patrick 24.11.2026): F wenigste Stangen, G geringster Verschnitt, H Schnellrechnung.
# E (ausgewogen) bewertet weiter nur A … D, damit gespeicherte Angebote mit E bitgleich bleiben.
F, G, H = "F", "G", "H"
# Universelle Konturverschachtelung (Patrick 25.11.2026): P Präzisionsoptimierung (mehr Reihenfolgen und Drehungen je
# Stange, längere exakte Suche). Die Strategien des Auftrags: A max. Materialausnutzung = A, B Schnelloptimierung = H,
# C Präzisionsoptimierung = P, D Fertigungsoptimierung = D (alle mit Konturverschachtelung).
P = "P"
# Nesting-Kern (Patrick 25.11.2026): N gleiche Teile nacheinander (Optimierung zum Stangenende), S satzweise
# schneiden, X automatisch (Mehrzielbewertung über alle Strategien mit einstellbaren Gewichten)
N, S, X = "N", "S", "X"
STRATEGIEN = {A: "Minimaler Materialverbrauch", B: "Geringste Materialkosten", C: "Maximale Reststückverwertung",
              D: "Schnellste Fertigung", E: "Ausgewogen", F: "Wenigste Stangen", G: "Geringster Verschnitt",
              H: "Schnellrechnung", P: "Präzisionsoptimierung", N: "Gleiche Teile nacheinander",
              S: "Satzweise schneiden", X: "Automatisch (alle Ziele)"}
KURZ = {A: "wenig Material", B: "günstigster Einkauf", C: "Reste zuerst", D: "schnell fertigen", E: "ausgewogen",
        F: "wenigste Stangen", G: "wenig Verschnitt", H: "schnell gerechnet", P: "präzise verschachtelt",
        N: "gleiche Teile am Stück", S: "fertige Sätze", X: "automatisch gewählt"}
REIHE = (A, B, C, D, E, F, G, H, P, N, S, X)     # Reihenfolge im Vergleich
SCHWANZ_MAX = 6          # so viele am schwächsten belegte Stangen werden höchstens neu auf Mischungen verteilt
MISCH_VERSUCHE = 30      # Mischungen je Schwanzgröße, die mit vorrat_planen geprüft werden
SCHWANZ_RUNDEN = 3       # so oft wird der Schwanz nach einer Verbesserung erneut probiert
MISCHPLAN_MAX_TEILE = 200   # Mischplan über alle Teile (vorrat_planen) nur bis zu so vielen Teilen; darüber mischt
                            # nur der Schwanz (große Aufträge: Rechenzeit, die Einzellängen sind dort schon dicht)
BUENDELN_SCHRITTE = 4000  # Prüfungen beim Bündeln der Reste je Plan
GEWICHTE = dict(belegung=5.0, rest_mm=0.0)   # Strategie E: € je verschiedene Belegung, € je mm verwertbarer Rest
# Strategie X (Mehrzielbewertung, Patrick 25.11.2026) zusätzlich: € je Artikelwechsel in der Schnittfolge (Umstellen,
# Sortieren bei der Entnahme), € je Teil im Zwischenlager (höchstens gleichzeitig liegende Teile unfertiger Sätze),
# € je Minute Maschinenzeit (planabhängig: Stangenwechsel und Trennschnitte). E liest nur belegung und rest_mm.
GEWICHTE_X = dict(artikelwechsel=0.5, zwischenlager=0.2, minute=0.0)
SATZ_MAX_ARTEN = 30      # Satz nur aus höchstens so vielen verschiedenen Teilen erkennen
REST_MIN_NUTZ = 100.0    # Vorgabe: ein Rest ist verwertbar, wenn nach Endbeschnitt und Greiferrest so viel bleibt


@dataclass(frozen=True)
class Laenge:
    """Lieferlänge einer Gruppe: Länge [mm], Preis je Lieferstange [€] (None = fehlt), verfügbar (None = beliebig)."""
    laenge: float
    preis: float = None
    anzahl: int = None
    mindest: int = 0        # Mindestabnahme [Stangen] (z. B. Walzlänge vom Werk): Länge nur, wenn so viele gebraucht


@dataclass(frozen=True)
class Rest:
    """Reststück aus dem Lager: Kennung (R-00012), Länge [mm], kalkulatorischer Wert [€], Lagerposten."""
    kennung: str
    laenge: float
    wert: float = 0.0
    bestand_id: int = None


@dataclass
class Plan:
    """Ergebnis einer Strategie: stangen [(Länge, Folge [(Teil, Drehung)], Rest-Kennung oder '')], nicht eingeplante
    Teile, Kennzahlen (kennzahlen) und eine Begründung."""
    strategie: str
    stangen: list
    uebrig: list = field(default_factory=list)
    werte: dict = field(default_factory=dict)
    warum: str = ""
    schritte: list = field(default_factory=list)


# ------------------------------------------------------------------ Grundbausteine
def _h(g, laenge, teile=None):
    return replace(g, stange=laenge, teile=list(g.teile if teile is None else teile), bewiesen=False, schranke=0)


def passt_auf(g, laenge, teile):
    """Passen die Teile zusammen auf eine Stange der Länge laenge (gleiche Fertigungsregeln wie der Schnittplan)?"""
    return bool(teile) and opt.passt(_h(g, laenge, []), list(teile))


def _folge(g, laenge, teile):
    return opt.anordnen(list(teile), _h(g, laenge, []))


def folge_fest(g, laenge, teile, drehungen=None):
    """Folge in genau dieser Reihenfolge (Teile von Hand verschoben, Nesting-Arbeitsplatz 2.0): Drehungen wie
    angegeben (drehungen) oder die besten für die Reihenfolge (optimierung._drehen). Ergebnis (Folge, '') oder
    (None, Grund), geprüft mit denselben Regeln wie jeder Schnittplan (optimierung.pruefe: Überbelegung mit
    Greiferrest/3D-Greifmaß, Drehung und Naht, Gehrungsabstand)."""
    teile = list(teile)
    if not teile:
        return [], ""
    h = _h(g, laenge, teile)
    if not opt.vertraeglich(h, teile):
        return None, "feste Naht auf Breit- und Schmalseite auf einer Stange"
    kands = []
    if drehungen is not None and len(drehungen) == len(teile):
        kands.append(list(zip(teile, drehungen)))
    kands.append(opt._drehen(h, teile))
    grund = ""
    for folge in kands:
        try:
            opt.pruefe([h], [[folge]])
            return folge, ""
        except AssertionError as e:
            grund = str(e).split(": ", 1)[-1]
    if "überbelegt" in grund:
        f = kands[-1]
        zu = opt.verbrauch(h, f) + opt.hinten(h, f) - laenge
        grund = f"Stange überbelegt um {zu:.0f} mm (mit Greiferrest bzw. 3D-Greifmaß)".replace(".", ",")
    return None, grund


def frei(g, laenge, folge):
    """Platz, der auf der Stange noch für Teile bleibt (nutzbar bis Greiferrest minus Belegung)."""
    h = _h(g, laenge, [])
    return h.nutzbar_bis - opt.belegt(h, folge)


def verwertbar(g, rest_mm, min_rest=0.0, min_nutz=REST_MIN_NUTZ):
    """Ist ein Reststück wiederverwendbar? Theoretischer Rest ist jede Länge; verwertbar ist er erst, wenn er
    mindestens min_rest lang ist UND nach Endbeschnitt, Greiferrest (Spannbereich) und einem Schnitt noch min_nutz
    für ein Teil bleibt (Patrick 23.11.2026: nicht verfügbar, wenn Spannbereich oder Maschine es verhindern)."""
    return rest_mm + EPS >= max(min_rest, g.endbeschnitt + g.greiferrest + g.kerf + max(min_nutz, EPS))


def _laengen_fuer(g, laengen):
    """Nur Längen, auf die jedes Teil allein passt, sonst die, auf die überhaupt ein Teil passt (Mischung)."""
    return sorted({x.laenge: x for x in laengen if x.laenge > 0}.values(), key=lambda x: x.laenge)


def _einzeln(g, laenge):
    h = _h(g, laenge)
    if any(not opt.passt(h, [t]) for t in h.teile):
        return None
    return [(laenge, f, "") for f in opt.optimiere(h)]


def _vorrat(g, vorrat, teile=None):
    h = _h(g, g.stange, teile)
    folgen, uebrig = opt.vorrat_planen(h, [(x, n) for x, n in vorrat if n > 0])
    return [(laenge, f, "") for laenge, f in folgen], uebrig


def _zaehlen(stangen):
    out = {}
    for laenge, _, rest in stangen:
        if not rest:
            out[laenge] = out.get(laenge, 0) + 1
    return out


def _preis(laengen, laenge):
    return next((x.preis for x in laengen if abs(x.laenge - laenge) < EPS), None)


def kosten(stangen, laengen, reste=()):
    """(Einkauf €, kalkulatorisch €, fehlt): Einkauf = gekaufte Lieferstangen × Preis je Länge; kalkulatorisch =
    Einkauf + Wert der eingesetzten Reststücke. fehlt = True, wenn für eine gekaufte Länge kein Preis vorliegt."""
    wert = {r.kennung: r.wert for r in reste}
    einkauf, kalk, fehlt = 0.0, 0.0, False
    for laenge, _, rest in stangen:
        if rest:
            kalk += wert.get(rest, 0.0) or 0.0
            continue
        p = _preis(laengen, laenge)
        if p is None:
            fehlt = True
            continue
        einkauf += p
        kalk += p
    return einkauf, kalk, fehlt


def _kostenwert(art, laengen):
    """Kosten einer Lieferstange für die Suche: 'mm' = Länge (Strategie A), 'eur' = Preis (B; ohne Preis die Länge
    zum Meterpreis der teuersten bekannten Länge, damit eine Länge ohne Preis nie als billig gilt)."""
    if art == "mm":
        return {x.laenge: x.laenge for x in laengen}
    bekannt = [x.preis / x.laenge for x in laengen if x.preis is not None and x.laenge > 0]
    teuer = max(bekannt) * 10 if bekannt else 1.0
    return {x.laenge: (x.preis if x.preis is not None else x.laenge * teuer) for x in laengen}


def _wert(stangen, kw):
    return sum(kw.get(laenge, laenge) for laenge, _, rest in stangen if not rest)


# ------------------------------------------------------------------ Schwanz neu verteilen (Längen mischen)
def _mischungen(laengen, bedarf_mm, grenze, kw, g, maximal):
    """Anzahlvektoren über laengen, deren nutzbare Länge den Bedarf deckt und deren Kosten unter grenze liegen,
    nach Kosten (dann Länge, dann Stangen) aufsteigend; höchstens MISCH_VERSUCHE."""
    nutz = [x.laenge - g.greiferrest + g.ende_bonus - g.endbeschnitt for x in laengen]
    obere = []
    for x, nu, mx in zip(laengen, nutz, maximal):
        k = math.ceil(bedarf_mm / nu) + 1 if nu > EPS else 0
        obere.append(max(0, min(k, mx if mx is not None else k)))
    out = []
    for c in itertools.product(*(range(o + 1) for o in obere)):
        if not any(c):
            continue
        if sum(n * nu for n, nu in zip(c, nutz)) + EPS < bedarf_mm:
            continue
        w = sum(n * kw[x.laenge] for n, x in zip(c, laengen))
        if w >= grenze - EPS:
            continue
        out.append((w, sum(n * x.laenge for n, x in zip(c, laengen)), sum(c), c))
    out.sort()
    return out[:MISCH_VERSUCHE]


def schwanz(g, stangen, laengen, kw, verfuegbar=None):
    """Die am schwächsten belegten Stangen (ohne Reststücke) auf eine günstigere Mischung der Längen verteilen.
    Ergebnis: neue Stangenliste (nie teurer, alle Teile eingeplant)."""
    laengen = _laengen_fuer(g, laengen)
    if not laengen:
        return stangen
    for _ in range(SCHWANZ_RUNDEN):
        neu = [s for s in stangen if not s[2]]
        fest = [s for s in stangen if s[2]]
        if not neu:
            return stangen
        neu.sort(key=lambda s: (sum(t.laenge for t, _ in s[1]) / s[0], s[0]))
        beste = None
        for k in range(1, min(SCHWANZ_MAX, len(neu)) + 1):
            teil_st, bleibt = neu[:k], neu[k:]
            teile = [t for _, f, _ in teil_st for t, _ in f]
            bisher = _wert(teil_st, kw)
            bedarf_mm = sum(opt.mindestbedarf(g, t) for t in teile)
            genutzt = _zaehlen(bleibt)
            maximal = [None if (verfuegbar or {}).get(x.laenge) is None
                       else verfuegbar[x.laenge] - genutzt.get(x.laenge, 0) for x in laengen]
            for w, _, _, c in _mischungen(laengen, bedarf_mm, bisher, kw, g, maximal):
                st, uebrig = _vorrat(g, [(x.laenge, n) for x, n in zip(laengen, c)], teile)
                if uebrig:
                    continue
                w = _wert(st, kw)
                if w < bisher - EPS and (beste is None or bisher - w > beste[0] + EPS):
                    beste = (bisher - w, bleibt + st)
                break       # günstigste ausführbare Mischung dieser Schwanzgröße gefunden
        if beste is None:
            return stangen
        stangen = fest + beste[1]
    return stangen


# ------------------------------------------------------------------ Reste bündeln
def buendeln(g, stangen, schritte=BUENDELN_SCHRITTE):
    """Bei gleicher Stangenzahl Teile umsetzen bzw. tauschen, damit der freie Platz auf wenigen Stangen zusammenkommt
    (Summe der Quadrate des freien Platzes wird größer). Jeder Schritt wird mit passt geprüft; eine leer gewordene
    Stange fällt weg. Ergebnis: neue Stangenliste."""
    st = [(laenge, [t for t, _ in f], rest) for laenge, f, rest in stangen]
    if len(st) < 2:
        return stangen

    def fr(i):
        return frei(g, st[i][0], _folge(g, st[i][0], st[i][1])) if st[i][1] else st[i][0]
    freis = [fr(i) for i in range(len(st))]
    n = 0
    besser = True
    while besser and n < schritte:
        besser = False
        ziel = max(range(len(st)), key=lambda i: (freis[i], -i))     # Stange, die zum Reststück wird
        for t in sorted(st[ziel][1], key=lambda t: (t.laenge, t.zeile, t.nr)):
            # 1) Teil auf eine andere Stange umsetzen (die vollste, auf die es passt)
            for j in sorted((j for j in range(len(st)) if j != ziel), key=lambda j: (freis[j], j)):
                n += 1
                if freis[j] + EPS < opt.mindestbedarf(g, t) or not passt_auf(g, st[j][0], st[j][1] + [t]):
                    continue
                st[j][1].append(t)
                st[ziel][1].remove(t)
                freis[j], freis[ziel] = fr(j), fr(ziel)
                besser = True
                break
            if besser or n >= schritte:
                break
            # 2) gegen ein kürzeres Teil einer anderen Stange tauschen
            for j in sorted((j for j in range(len(st)) if j != ziel), key=lambda j: (freis[j], j)):
                for q in sorted({(x.laenge, x.zeile): x for x in st[j][1] if x.laenge < t.laenge - EPS}.values(),
                                key=lambda x: (x.laenge, x.zeile, x.nr)):
                    n += 1
                    if n >= schritte:
                        break
                    a = [x for x in st[j][1] if x is not q] + [t]
                    b = [x for x in st[ziel][1] if x is not t] + [q]
                    if passt_auf(g, st[j][0], a) and passt_auf(g, st[ziel][0], b):
                        alt = freis[ziel] ** 2 + freis[j] ** 2
                        st[j] = (st[j][0], a, st[j][2])
                        st[ziel] = (st[ziel][0], b, st[ziel][2])
                        freis[j], freis[ziel] = fr(j), fr(ziel)
                        if freis[ziel] ** 2 + freis[j] ** 2 > alt + EPS:
                            besser = True
                            break
                        st[j] = (st[j][0], [x for x in a if x is not t] + [q], st[j][2])     # zurück
                        st[ziel] = (st[ziel][0], [x for x in b if x is not q] + [t], st[ziel][2])
                        freis[j], freis[ziel] = fr(j), fr(ziel)
                if besser or n >= schritte:
                    break
            if besser or n >= schritte:
                break
    out = [(laenge, _folge(g, laenge, teile), rest) for laenge, teile, rest in st if teile]
    return out


# ------------------------------------------------------------------ Reststücke zuerst
def reste_fuellen(g, teile, reste, reihenfolge="lang"):
    """Teile auf Reststücke: je Rest (längste bzw. kürzeste zuerst) das Schnittmuster mit der größten Teilelänge.
    Ergebnis: (Stangen auf Resten, übrige Teile)."""
    rest_teile = list(teile)
    out = []
    for r in sorted(reste, key=lambda r: (-r.laenge if reihenfolge == "lang" else r.laenge, r.kennung)):
        if not rest_teile:
            break
        if not any(passt_auf(g, r.laenge, [t]) for t in rest_teile):
            continue
        st = []
        h = _h(g, r.laenge, [])
        opt._muster_fuellen(h, rest_teile, {r.laenge: 1}, st, "quote", 1.0)
        if not st:
            opt._fuellen(h, rest_teile, {r.laenge: 1}, st)
        if not st:
            continue
        _, s = st[0]
        out.append((r.laenge, _folge(g, r.laenge, s), r.kennung))
        weg = {id(t) for t in s}
        rest_teile = [t for t in rest_teile if id(t) not in weg]
    return out, rest_teile


# ------------------------------------------------------------------ Kennzahlen und Prüfung
def kennzahlen(g, plan_stangen, uebrig, laengen, reste=(), je_beladung=0.0, min_rest=0.0, min_nutz=REST_MIN_NUTZ):
    """Kennzahlen eines Plans (Patrick 23.11.2026, Wirtschaftlichkeitsvergleich): Stangen, je Länge, eingekaufte
    Länge, eingesetzte Reststücke, Einkauf €, kalkulatorisch €, verarbeitete Teilelänge, Schnittverluste,
    Endbeschnitt und Greiferrest (technisch), verwertbare Reststücke, nicht verwertbarer Verschnitt, Ausnutzung,
    € je Teil, € je Position (nach Teilelänge verteilt), Beladungen, verschiedene Belegungen, Fertigungskosten der
    Beladungen und Gesamtkosten. Bilanz: Teile + Schnitt + verwertbar + nicht verwertbar = Stangenlänge gesamt."""
    einkauf, kalk, fehlt = kosten(plan_stangen, laengen, reste)
    gesamt_mm = sum(laenge for laenge, _, _ in plan_stangen)
    gekauft_mm = sum(laenge for laenge, _, rest in plan_stangen if not rest)
    teile_mm = schnitt_mm = verwertbar_mm = technik_mm = 0.0
    neue_reste = []
    je_zeile_mm, je_zeile_eur = {}, {}
    wert = {r.kennung: r.wert for r in reste}
    for laenge, f, rest in plan_stangen:
        h = _h(g, laenge, [])
        tl = sum(t.laenge for t, _ in f)
        teile_mm += tl
        v = opt.verbrauch(h, f)
        schnitt_mm += v - g.endbeschnitt - tl
        technik_mm += g.endbeschnitt
        r = laenge - v
        if verwertbar(g, r, min_rest, min_nutz):
            verwertbar_mm += r
            neue_reste.append(round(r, 1))
        p = wert.get(rest, 0.0) if rest else _preis(laengen, laenge)
        for t, _ in f:
            je_zeile_mm[t.zeile] = je_zeile_mm.get(t.zeile, 0.0) + t.laenge
            if p is not None and tl > 0:
                je_zeile_eur[t.zeile] = je_zeile_eur.get(t.zeile, 0.0) + p * t.laenge / tl
    nicht_mm = gesamt_mm - teile_mm - schnitt_mm - verwertbar_mm
    n_teile = sum(len(f) for _, f, _ in plan_stangen)
    n = len(plan_stangen)
    folgen = [f for _, f, _ in plan_stangen]
    return dict(
        stangen=n, je_laenge=dict(sorted(_zaehlen(plan_stangen).items(), reverse=True)),
        reste=sum(1 for _, _, r in plan_stangen if r), rest_kennungen=[r for _, _, r in plan_stangen if r],
        gekauft_mm=gekauft_mm, gesamt_mm=gesamt_mm, rest_eingesetzt_mm=gesamt_mm - gekauft_mm,
        einkauf=None if fehlt else einkauf, kalkulatorisch=None if fehlt else kalk, preis_fehlt=fehlt,
        teile_mm=teile_mm, schnitt_mm=schnitt_mm, technik_mm=technik_mm, rest_verwertbar_mm=verwertbar_mm,
        neue_reste=neue_reste, verschnitt_mm=nicht_mm,
        verschnitt=(nicht_mm / gesamt_mm) if gesamt_mm else 0.0, ausnutzung=(teile_mm / gesamt_mm) if gesamt_mm else 0.0,
        eur_teil=(kalk / n_teile) if n_teile and not fehlt else None,
        eur_position={z: round(e, 4) for z, e in sorted(je_zeile_eur.items())} if not fehlt else {},
        mm_position=dict(sorted(je_zeile_mm.items())),
        beladungen=n, belegungen=opt.belegungen(folgen) if folgen else 0,
        fertigung=je_beladung * n, gesamt=None if fehlt else kalk + je_beladung * n,
        nicht_eingeplant=len(uebrig), teile=n_teile,
        # Verschachtelung (Patrick 25.11.2026): Stellen mit ineinanderliegenden Enden, davon beliebige Endkonturen,
        # und Trennschnitte (gemeinsamer Schnitt = 1, sonst 2) als Maß für den Fertigungsaufwand
        ineinander=sum(opt.gehrungen_ineinander(g, f) for f in folgen),
        konturen=sum(opt.konturen_ineinander(g, f) for f in folgen),
        trennschnitte=sum(sum(1 if opt.lage(t1, r1)[1] and opt.lage(t2, r2)[0] else 2
                              for (t1, r1), (t2, r2) in zip(f, f[1:])) for f in folgen),
        **fertigung_kennzahlen(g, folgen))


def sorte(t):
    """Gleiche Teile: gleicher Artikel (ohne Artikel: gleiche Position) und gleiche Länge."""
    return ((t.artikel or "").strip().lower() or f"#{t.zeile}", round(t.laenge, 1))


def _sorten(teile):
    je = {}
    for t in opt.sortiert(teile):
        je.setdefault(sorte(t), []).append(t)
    return je


def satz_erkennen(teile, saetze=0):
    """Satz aus den Mengen (Patrick 25.11.2026): größter gemeinsamer Teiler der Stückzahlen je Sorte (20 A, 40 B,
    20 C = 20 Sätze aus 1 A + 2 B + 1 C) oder die vorgegebene Satzzahl, wenn sie alle Mengen teilt. Ergebnis
    (Sätze, [(Sorte, je Satz)]) oder None (nur eine Sorte, kein gemeinsamer Teiler ≥ 2, zu viele Sorten)."""
    je = _sorten(teile)
    if len(je) < 2 or len(je) > SATZ_MAX_ARTEN:
        return None
    mengen = [len(v) for v in je.values()]
    n = int(saetze or 0)
    if n < 2 or any(m % n for m in mengen):
        n = math.gcd(*mengen)
    if n < 2:
        return None
    return n, [(k, len(v) // n) for k, v in je.items()]


def fertigung_kennzahlen(g, folgen):
    """Kennzahlen der Schnittfolge (Patrick 25.11.2026): Artikelwechsel (Sorte ändert sich zum Vorgänger in der
    Folge aller Stangen), Schnitte (Trennschnitte + Anfang und Ende je Stange), geschnittene Endenlänge [mm]
    (Schätzung: je Ende der Mittelwert der Schnittlängen beider Enden, gemeinsamer Schnitt einmal) und bei
    erkennbarem Satz die höchste Zahl Teile, die gleichzeitig auf einen fertigen Satz warten (Zwischenlager)."""
    folge = [t for f in folgen for t, _ in f]
    wechsel = sum(1 for a, b in zip(folge, folge[1:]) if sorte(a) != sorte(b))
    enden_mm = 0.0
    schnitte = 0
    for f in folgen:
        if not f:
            continue
        e = [(t.a_schnitt + t.b_schnitt) / 2 for t, _ in f]
        enden_mm += e[0] + e[-1]
        schnitte += 2
        for i, ((t1, r1), (t2, r2)) in enumerate(zip(f, f[1:])):
            if opt.lage(t1, r1)[1] and opt.lage(t2, r2)[0]:
                enden_mm += max(e[i], e[i + 1])
                schnitte += 1
            else:
                enden_mm += e[i] + e[i + 1]
                schnitte += 2
    out = dict(artikelwechsel=wechsel, schnitte=schnitte, enden_mm=round(enden_mm, 1), zwischenlager=None,
               satz_erster=None)
    sz = satz_erkennen(g.teile)
    if sz is not None:
        n, aufbau = sz
        je = dict(aufbau)
        groesse = sum(je.values())
        zaehler = {k: 0 for k in je}
        hoch, erster = 0, None
        for i, t in enumerate(folge):
            k = sorte(t)
            if k not in zaehler:
                continue
            zaehler[k] += 1
            fertig_n = min(zaehler[x] // je[x] for x in je)
            if fertig_n and erster is None:
                erster = i
            hoch = max(hoch, sum(zaehler.values()) - fertig_n * groesse)
        out["zwischenlager"] = hoch
        if erster is not None:      # Stange, auf der der erste Satz fertig wird (1 = erste Stange)
            n_t = 0
            for j, f in enumerate(folgen, 1):
                n_t += len(f)
                if n_t > erster:
                    out["satz_erster"] = j
                    break
    return out


def maschinenzeit(werte, zeit):
    """Planabhängige Maschinenzeit [s] (Schätzung): Stangenwechsel je Beladung + geschnittene Endenlänge mit dem
    Vorschub + Einstiche je Schnitt. zeit = (s je Stangenwechsel, s je mm Schnitt, s je Schnitt) oder None (ohne
    Schneiddaten)."""
    if not zeit or werte.get("schnitte") is None:
        return None
    return werte["beladungen"] * zeit[0] + schnittzeit(werte, zeit)


def pruefe(g, plan_stangen, uebrig, laengen=None, reste=()):
    """Unabhängige Kontrolle (Patrick 23.11.2026: jede Verschachtelung muss mathematisch aufgehen). AssertionError,
    wenn ein Teil fehlt oder doppelt ist, eine Stange überbelegt ist (Greiferrest bzw. 3D-Greifmaß nicht frei), die
    Bilanz Teile + Schnittverluste + Endbeschnitt + Rest ≠ Stangenlänge ist, mehr Stangen einer Länge als verfügbar
    geplant sind oder ein Reststück doppelt, mit falscher Länge oder unbekannt eingeplant ist."""
    ids = sorted([(t.zeile, t.nr) for _, f, _ in plan_stangen for t, _ in f] + [(t.zeile, t.nr) for t in uebrig])
    if ids != sorted((t.zeile, t.nr) for t in g.teile):
        raise AssertionError(f"{g.profil}: Teile fehlen oder doppelt (Nesting)")
    rl = {r.kennung: r.laenge for r in reste}
    gesehen = set()
    for laenge, f, rest in plan_stangen:
        if not f:
            raise AssertionError(f"{g.profil}: leere Stange im Plan")
        if rest:
            if rest in gesehen:
                raise AssertionError(f"{g.profil}: Reststück {rest} doppelt eingeplant")
            if rest not in rl or abs(rl[rest] - laenge) > EPS:
                raise AssertionError(f"{g.profil}: Reststück {rest} unbekannt oder mit falscher Länge")
            gesehen.add(rest)
        h = _h(g, laenge, [t for t, _ in f])
        opt.pruefe([h], [[f]])
        v = opt.verbrauch(h, f)
        tl = sum(t.laenge for t, _ in f)
        bilanz = tl + (v - g.endbeschnitt - tl) + g.endbeschnitt + (laenge - v)
        if abs(bilanz - laenge) > 1e-6 or laenge - v + EPS < opt.hinten(h, f):
            raise AssertionError(f"{g.profil}: Längenbilanz der Stange {laenge:g} mm geht nicht auf")
    if laengen is not None:
        verf = {x.laenge: x.anzahl for x in laengen}
        for laenge, n in _zaehlen(plan_stangen).items():
            if laenge not in verf:
                raise AssertionError(f"{g.profil}: Länge {laenge:g} mm ist nicht lieferbar")
            if verf[laenge] is not None and n > verf[laenge]:
                raise AssertionError(f"{g.profil}: {n} Stangen {laenge:g} mm, verfügbar {verf[laenge]}")


# ------------------------------------------------------------------ Strategien
def _kandidaten_einzeln(g, laengen):
    out = {}
    for x in laengen:
        st = _einzeln(g, x.laenge)
        if st is not None and (x.anzahl is None or len(st) <= x.anzahl):
            out[x.laenge] = st
    return out


def _mischplan(g, laengen, einzeln):
    if len(laengen) < 2 or len(g.teile) > MISCHPLAN_MAX_TEILE:
        return None
    vorrat = []
    for x in laengen:
        n = len(einzeln[x.laenge]) if x.laenge in einzeln else len(g.teile)
        vorrat.append((x.laenge, n if x.anzahl is None else min(n, x.anzahl)))
    st, uebrig = _vorrat(g, vorrat)
    return None if uebrig else st


def _beste(kands, schluessel):
    kands = [k for k in kands if k is not None]
    return min(kands, key=schluessel) if kands else None


def _kosten_suche(g, laengen, art, einzeln, misch):
    kw = _kostenwert(art, laengen)
    verf = {x.laenge: x.anzahl for x in laengen}
    kands = list(einzeln.values()) + ([misch] if misch else [])
    start = _beste(kands, lambda st: (_wert(st, kw), len(st), sum(x for x, _, _ in st)))
    if start is None:
        return None
    return schwanz(g, start, laengen, kw, verf)


# ------------------------------------------------------------------ Fertigungsfolge (Patrick 25.11.2026)
# N „Gleiche Teile nacheinander – Optimierung zum Stangenende“: je Sorte (gleicher Artikel, gleiche Länge) so viele
# volle Stangen nur mit dieser Sorte wie möglich; die übrigen Teile jeder Sorte kommen ans Ende der vollen Stangen
# (Best Fit: die Stange mit dem kleinsten passenden freien Platz), was dann noch bleibt, plant die Kostensuche wie B.
# S „Satzweise“: die Teile werden Satz für Satz in Satzfolge auf die Stangen gelegt; passt das nächste Teil nicht mehr,
# füllt das längste passende Teil des laufenden oder des nächsten Satzes das Stangenende (Satz geteilt, wo am wenigsten
# Material bleibt). Beide rechnen je Lieferlänge und nehmen die günstigste; jede Stange bekommt danach die günstigste
# Länge, auf die ihre Teile passen. Gleiche Fertigungsregeln und Prüfung wie jeder Plan.
def _kapazitaet(g, laenge, ts):
    """So viele Teile dieser Sorte passen auf eine Stange (auch mehr, als es gibt: dann keine volle Stange)."""
    k = 0
    while k <= len(ts) and passt_auf(g, laenge, [ts[i % len(ts)] for i in range(k + 1)]):
        k += 1
    return k


def _folge_reihe(g, laenge, teile):
    """Folge möglichst in der gegebenen Reihenfolge (Schnittfolge), sonst wie optimiert, wenn das weniger braucht."""
    a = _folge(g, laenge, teile)
    f, _ = folge_fest(g, laenge, teile)
    h = _h(g, laenge, [])
    if f is None or opt.belegt(h, f) > opt.belegt(h, a) + EPS:
        return a
    return f


def _auf_laengen(g, stangen, laengen):
    """Je Stange (Teile in Schnittfolge) die günstigste passende Lieferlänge; None, wenn eine Länge nicht reicht."""
    kw = _kostenwert("eur", laengen)
    verf = {x.laenge: x.anzahl for x in laengen}
    n = {}
    out = []
    for teile in stangen:
        wahl = None
        for x in sorted(laengen, key=lambda x: (kw[x.laenge], x.laenge)):
            if verf[x.laenge] is not None and n.get(x.laenge, 0) >= verf[x.laenge]:
                continue
            if passt_auf(g, x.laenge, teile):
                wahl = x.laenge
                break
        if wahl is None:
            return None
        n[wahl] = n.get(wahl, 0) + 1
        out.append((wahl, _folge_reihe(g, wahl, teile), ""))
    return out


def _beste_laenge(g, laengen, bauen):
    kw = _kostenwert("eur", laengen)
    beste = None
    for x in laengen:
        st = bauen(x.laenge)
        st = _auf_laengen(g, st, laengen) if st is not None else None
        if st is None:
            continue
        schl = (_wert(st, kw), len(st), sum(y for y, _, _ in st))
        if beste is None or schl < beste[0]:
            beste = (schl, st)
    return beste[1] if beste else None


def sortenfolge(g, stangen):
    """Schnittfolge eines fertigen Plans nach Sorten ordnen (Material bleibt gleich): je Stange die Teile nach Sorte,
    die Stangen so, dass gleiche Teile möglichst direkt nacheinander geschnitten werden."""
    reihe = {k: i for i, k in enumerate(_sorten(g.teile))}
    neu = []
    for laenge, f, rest in stangen:
        teile = sorted((t for t, _ in f), key=lambda t: (reihe[sorte(t)], t.zeile, t.nr))
        neu.append((laenge, _folge_reihe(g, laenge, teile), rest))
    return sorted(neu, key=lambda x: (tuple(reihe[sorte(t)] for t, _ in x[1]), -x[0]))


def _gleiche_teile(g, laengen, reste=(), gewichte=None, basis=None):
    je = _sorten(g.teile)
    reihe = {k: i for i, k in enumerate(je)}

    def bauen(laenge):
        stangen, offen = [], []
        for ts in je.values():
            k = _kapazitaet(g, laenge, ts)
            if k == 0:
                return None
            voll = len(ts) // k
            stangen += [list(ts[i * k:(i + 1) * k]) for i in range(voll)]
            offen += ts[voll * k:]
        frei_ = [frei(g, laenge, _folge(g, laenge, s)) for s in stangen]
        nicht = []
        for t in opt.sortiert(offen):           # Reste zum Stangenende, Best Fit
            bedarf = opt.mindestbedarf(g, t)
            beste = None
            for i, s in enumerate(stangen):
                if frei_[i] + EPS >= bedarf and (beste is None or frei_[i] < frei_[beste]) and \
                        passt_auf(g, laenge, s + [t]):
                    beste = i
            if beste is None:
                nicht.append(t)
            else:
                stangen[beste].append(t)
                frei_[beste] = frei(g, laenge, _folge(g, laenge, stangen[beste]))
        if nicht:
            h = _h(g, g.stange, nicht)
            e2 = _kandidaten_einzeln(h, laengen)
            rest_st = _kosten_suche(h, laengen, "eur", e2, _mischplan(h, laengen, e2))
            if rest_st is None:
                return None
            neu = [sorted((t for t, _ in f), key=lambda t: (reihe[sorte(t)], t.zeile, t.nr)) for _, f, _ in rest_st]
            stangen += sorted(neu, key=lambda s: (reihe[sorte(s[0])], -len(s)))
        return stangen

    st = _beste_laenge(g, laengen, bauen)
    # Gegenkandidat: der Plan A mit nach Sorten geordneter Schnittfolge (gleiches Material wie A). Er ersetzt den
    # sortenreinen Plan nur, wenn er höchstens so viel kostet UND höchstens so viele Artikelwechsel hat
    a = sortenfolge(g, basis) if basis else None
    if a is not None:
        kw = _kostenwert("eur", laengen)

        def schl(x):
            return round(_wert(x, kw), 6), fertigung_kennzahlen(g, [f for _, f, _ in x])["artikelwechsel"]
        if st is None or all(u <= v for u, v in zip(schl(a), schl(st))):
            st = a
    return st, ("gleiche Teile nacheinander: je Artikel volle Stangen nur mit diesem Teil, die übrigen Teile am "
                "Stangenende mit der besten Füllung (Best Fit), Reihenfolge der Stangen = Schnittfolge")


def _satzweise(g, laengen, reste=(), gewichte=None):
    sz = satz_erkennen(g.teile, (gewichte or {}).get("saetze", 0))
    if sz is None:
        return None, ""
    n, aufbau = sz
    vorrat = {k: list(v) for k, v in _sorten(g.teile).items()}
    folge = []
    for i in range(n):
        for k, m in aufbau:
            folge += [(i, vorrat[k].pop(0)) for _ in range(m)]

    def bauen(laenge):
        rest = list(folge)
        stangen = []
        while rest:
            cur = []
            while rest and passt_auf(g, laenge, cur + [rest[0][1]]):
                cur.append(rest.pop(0)[1])
            if not cur:
                return None
            if rest:            # Stangenende: längstes passendes Teil des laufenden oder des nächsten Satzes
                grenze = rest[0][0] + 1
                kands = sorted((x for x in rest if x[0] <= grenze), key=lambda x: (-x[1].laenge, x[0]))
                fr = frei(g, laenge, _folge(g, laenge, cur))
                for x in kands:
                    if fr + EPS >= opt.mindestbedarf(g, x[1]) and passt_auf(g, laenge, cur + [x[1]]):
                        cur.append(x[1])
                        rest.remove(x)
                        fr = frei(g, laenge, _folge(g, laenge, cur))
            stangen.append(cur)
        return stangen

    st = _beste_laenge(g, laengen, bauen)
    return st, (f"satzweise: {n} Sätze nacheinander, ein Satz wird nur am Stangenende mit dem längsten passenden Teil "
                f"des laufenden oder nächsten Satzes geteilt, Reihenfolge der Stangen = Schnittfolge")


def satz_text(g, aufbau):
    namen = {}
    for t in g.teile:
        namen.setdefault(sorte(t), (t.artikel or f"Pos. {t.pos}") + f" {t.laenge:g} mm".replace(".", ","))
    return " + ".join(f"{m} × {namen.get(k, k[0])}" for k, m in aufbau)


# ------------------------------------------------------------------ Zwischenspeicher (Nesting-Arbeitsplatz 2.0)
# Patrick 24.11.2026: jede Strategie rechnete Einzel- und Mischplan derselben Gruppe neu (große Baugruppe 6/12 m:
# 7,9 s, davon ~90 % Doppelrechnung). Gemerkt wird das fertige, geprüfte Ergebnis je (Gruppe, Teile, Fertigungswerte,
# Strategie, Eingaben). Die Gruppe selbst wird mitgehalten, damit ihre Kennung nicht neu vergeben werden kann; die
# Teile werden über ihre Kennung (id) verglichen. Gleiche Eingaben → dasselbe Ergebnis (bitgleich), nur schneller.
MERKER_MAX = 256
_MERKER = {}


def merker_leeren():
    _MERKER.clear()


def _gkey(g):
    return (id(g), tuple(map(id, g.teile)), g.stange, g.endbeschnitt, g.greiferrest, g.kerf, g.abstand, g.ende_bonus,
            g.querschnitt, g.profil, g.werkstoff, g.oberflaeche)


def _skey(stangen):
    return None if stangen is None else tuple((laenge, tuple((id(t), r) for t, r in f), rest)
                                              for laenge, f, rest in stangen)


def _flach(v):
    return dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v


def _kopie(p):
    return None if p is None else Plan(p.strategie, list(p.stangen), list(p.uebrig),
                                       {k: _flach(v) for k, v in p.werte.items()}, p.warum, list(p.schritte))


def _grundplaene(g, laengen):
    """(Einzelpläne je Länge, Mischplan) der Gruppe, gemerkt: dieselben für A, B, C, D (vorher je Strategie neu)."""
    key = ("grund", _gkey(g), tuple(laengen)) + (("P",) if opt.praezision_an() else ())
    if key in _MERKER:
        einzeln, misch = _MERKER[key][1]
        opt.offen_dazu(_MERKER[key][2])
    else:
        with opt.offen_zaehlen() as z:
            einzeln = _kandidaten_einzeln(g, laengen)
            misch = _mischplan(g, laengen, einzeln)
        if len(_MERKER) >= MERKER_MAX:
            _MERKER.pop(next(iter(_MERKER)))
        _MERKER[key] = (g, (einzeln, misch), z.n)
    return {k: list(v) for k, v in einzeln.items()}, (list(misch) if misch is not None else None)


def planen(g, strategie, laengen, reste=(), je_beladung=0.0, min_rest=0.0, min_nutz=REST_MIN_NUTZ,
           mehrverschnitt=0.02, bisher=None, gewichte=None, buendeln_an=True):
    """Wie _plan_mindest, mit Zwischenspeicher (gleiche Eingaben = gleiches, schon geprüftes Ergebnis)."""
    key = (_gkey(g), strategie, tuple(laengen), tuple(reste), je_beladung, min_rest, min_nutz, mehrverschnitt,
           _skey(bisher), tuple(sorted((gewichte or {}).items())), buendeln_an)
    try:
        hash(key)
    except TypeError:
        key = None
    if key is not None and key in _MERKER:
        opt.offen_dazu(_MERKER[key][2])
        return _kopie(_MERKER[key][1])
    with opt.offen_zaehlen() as z:
        p = _plan_mindest(g, strategie, laengen, reste, je_beladung, min_rest, min_nutz, mehrverschnitt, bisher,
                          gewichte, buendeln_an)
    if key is not None:
        if len(_MERKER) >= MERKER_MAX:
            _MERKER.pop(next(iter(_MERKER)))
        _MERKER[key] = (g, _kopie(p), z.n)
    return p


def _plan_mindest(g, strategie, laengen, reste=(), je_beladung=0.0, min_rest=0.0, min_nutz=REST_MIN_NUTZ,
                  mehrverschnitt=0.02, bisher=None, gewichte=None, buendeln_an=True):
    """Wie _planen; eine Länge mit Mindestabnahme (Laenge.mindest, z. B. Walzlänge vom Werk ab ca. 20 t, Patrick
    23.11.2026) bleibt nur im Plan, wenn er mindestens so viele Stangen dieser Länge braucht, sonst wird ohne sie neu
    gerechnet. Zugeschnittene 12-m-Stangen gibt es hier nicht (nur ladbare Längen, jede Stange ganz gekauft)."""
    laengen = list(laengen)
    while True:
        p = _planen(g, strategie, laengen, reste, je_beladung, min_rest, min_nutz, mehrverschnitt, bisher, gewichte,
                    buendeln_an)
        if p is None:
            return None
        n = _zaehlen(p.stangen)
        weg = {x.laenge for x in laengen if x.mindest and 0 < n.get(x.laenge, 0) < x.mindest}
        if not weg:
            return p
        laengen = [x for x in laengen if x.laenge not in weg]
        if bisher and any(x in weg for x, _, _ in bisher):
            bisher = None


def _planen(g, strategie, laengen, reste=(), je_beladung=0.0, min_rest=0.0, min_nutz=REST_MIN_NUTZ,
            mehrverschnitt=0.02, bisher=None, gewichte=None, buendeln_an=True):
    """Plan einer Strategie A … E für die Gruppe g. laengen: [Laenge] (lieferbar und ladbar), reste: [Rest] (nur bei
    Strategie C/E und eingeschaltetem Lager mit Reststücken), je_beladung: € je geladener Stange (Stangenwechsel),
    bisher: Stangen des bisherigen Plans [(Länge, Folge, '')] als zusätzlicher Kandidat (nie schlechter als bisher).
    Ergebnis: Plan (geprüft) oder None, wenn keine Länge ausführbar ist."""
    laengen = _laengen_fuer(g, laengen)
    reste = [r for r in reste if verwertbar(g, r.laenge, 0.0, min_nutz)]
    einzeln, misch = _grundplaene(g, laengen)

    def kz(st, uebrig=()):
        return kennzahlen(g, st, list(uebrig), laengen, reste, je_beladung, min_rest, min_nutz)

    def fertig(s, st, warum, uebrig=(), ordnen=True):
        if st is None:
            return None
        if ordnen:      # N und S: Reihenfolge der Stangen ist die Schnittfolge, nichts umsetzen
            if buendeln_an:
                st = buendeln(g, st)
            st.sort(key=lambda x: (bool(x[2]), -x[0], -opt.verbrauch(_h(g, x[0], []), x[1]), x[1][0][0].zeile))
        pruefe(g, st, list(uebrig), laengen, reste)
        return Plan(s, st, list(uebrig), kz(st, uebrig), warum)

    if strategie == A:
        st = _kosten_suche(g, laengen, "mm", einzeln, misch)
        if bisher and st and _wert(bisher, _kostenwert("mm", laengen)) < _wert(st, _kostenwert("mm", laengen)) - EPS:
            st = bisher
        return fertig(A, st, "kleinste eingekaufte Stangenlänge (Längen gemischt, schwach belegte Stangen neu "
                             "auf die passendsten Längen verteilt)")
    if strategie == B:
        kw = _kostenwert("eur", laengen)
        st = _kosten_suche(g, laengen, "eur", einzeln, misch)
        if bisher and st and _wert(bisher, kw) < _wert(st, kw) - EPS:
            st = bisher
        return fertig(B, st, "kleinster Einkaufspreis aus den Preisen je Lieferlänge der Materialdatenbank")
    if strategie == C:
        basis = _kosten_suche(g, laengen, "eur", einzeln, misch)
        kw = _kostenwert("eur", laengen)
        kands = [(basis, 0.0)] if basis else []
        for reihe in ("lang", "kurz"):
            auf_rest, uebrig_t = reste_fuellen(g, g.teile, reste, reihe)
            if not auf_rest:
                continue
            if uebrig_t:
                h = _h(g, g.stange, uebrig_t)
                e2 = _kandidaten_einzeln(h, laengen)
                neu = _kosten_suche(h, laengen, "eur", e2, _mischplan(h, laengen, e2))
                if neu is None:
                    continue
            else:
                neu = []
            kands.append((auf_rest + neu, sum(x for x, _, r in auf_rest if r)))
        if not kands:
            return None
        st, _ = min(kands, key=lambda k: (_wert(k[0], kw), -k[1], len(k[0])))
        return fertig(C, st, "vorhandene Reststücke zuerst (je Rest das Muster mit der größten Teilelänge), der "
                             "Rest der Teile zum günstigsten Einkauf")
    if strategie == D:
        kands = []
        for st in list(einzeln.values()) + ([misch] if misch else []):
            kands.append(st)
            lang = {x for x, _, _ in st}
            if len(lang) == 1 and mehrverschnitt > 0:
                laenge = next(iter(lang))
                arm = opt.musterarm(_h(g, laenge), [f for _, f, _ in st], mehrverschnitt)
                if arm:
                    kands.append([(laenge, f, "") for f in arm])
        kw = _kostenwert("eur", laengen)
        st = _beste(kands, lambda st: (len(st), opt.belegungen([f for _, f, _ in st]), _wert(st, kw)))
        return fertig(D, st, "wenigste Beladungen der Maschine, dann wenigste verschiedene Belegungen (Programme)")
    if strategie in (F, G):
        kands = [planen(g, s, laengen, reste, je_beladung, min_rest, min_nutz, mehrverschnitt, bisher, gewichte,
                        buendeln_an) for s in (A, B, D)]
        kands = [p.stangen for p in kands if p is not None] + list(einzeln.values()) + ([misch] if misch else [])
        if bisher:
            kands.append(bisher)
        kw = _kostenwert("eur", laengen)
        if not kands:
            return None
        if strategie == F:
            st = _beste(kands, lambda st: (len(st), sum(x for x, _, r in st if not r), _wert(st, kw)))
            return fertig(F, st, "wenigste Stangen (Beladungen), dann wenigste eingekaufte Millimeter")
        werte = [(kz(buendeln(g, list(st)) if buendeln_an else list(st))["verschnitt_mm"], st) for st in kands]
        st = min(werte, key=lambda x: (round(x[0], 6), sum(y for y, _, r in x[1] if not r), _wert(x[1], kw)))[1]
        return fertig(G, list(st), "geringster nicht verwertbarer Verschnitt (Freiraum auf wenigen Stangen gebündelt, "
                                   "verwertbare Reststücke zählen nicht als Verschnitt)")
    if strategie == H:
        h = _h(g, g.stange)
        if not h.teile or any(not opt.passt(h, [t]) for t in h.teile):
            return None
        st = [(g.stange, opt.anordnen(s, h), "") for s in opt.aufloesen(h, opt.first_fit(h, h.teile))]
        p = fertig(H, st, "Schnellrechnung: nur First-Fit-Decreasing auf der Stangenlänge des Angebots, ohne "
                          "Schnittmuster-Suche und ohne Längen mischen")
        if p is not None:
            p.werte["untergrenze"] = opt.untergrenze(h)
        return p
    if strategie == P:
        # Präzision: dieselbe Suche wie A, aber jede Stange mit lokaler Suche über Reihenfolge und Drehung (mehr
        # Kombinationen der Endkonturen) und längerer exakter Suche; nie schlechter als A
        with opt.offen_zaehlen() as z:
            a = planen(g, A, laengen, reste, je_beladung, min_rest, min_nutz, mehrverschnitt, bisher, gewichte,
                       buendeln_an)
        st = None
        # Variantenlogik (Patrick 25.11.2026): ohne Enden zum Ineinanderlegen und mit vollständiger exakter Suche
        # rechnet die Präzision genau wie A (gleiches Ergebnis), die zweite Rechnung entfällt
        if a is None or z.n or opt.praezision_wirkt(g):
            with opt.praezision():
                e2, m2 = _grundplaene(g, laengen)
                st = _kosten_suche(g, laengen, "mm", e2, m2)
        kw = _kostenwert("mm", laengen)
        if a is not None and (st is None or (_wert(a.stangen, kw), len(a.stangen)) <= (_wert(st, kw), len(st))):
            st = [(x, list(f), r) for x, f, r in a.stangen]
        return fertig(P, st, "Präzisionsoptimierung: mehr Reihenfolgen, Drehungen und Konturkombinationen je Stange "
                             "(lokale Suche, längere exakte Suche); nie mehr Material als A")
    if strategie in (N, S):
        if strategie == N:
            a = planen(g, A, laengen, reste, je_beladung, min_rest, min_nutz, mehrverschnitt, bisher, gewichte,
                       buendeln_an)
            st, text = _gleiche_teile(g, laengen, reste, gewichte, a.stangen if a is not None else None)
        else:
            st, text = _satzweise(g, laengen, reste, gewichte)
        if st is None:
            return None
        p = fertig(strategie, st, text, ordnen=False)
        if strategie == S and p is not None:
            n, aufbau = satz_erkennen(g.teile, (gewichte or {}).get("saetze", 0))
            p.werte["saetze"] = n
            p.werte["satz_aufbau"] = satz_text(g, aufbau)
        return p
    if strategie == X:
        plaene = [planen(g, s, laengen, reste, je_beladung, min_rest, min_nutz, mehrverschnitt, bisher, gewichte,
                         buendeln_an) for s in (A, B, C, D, F, G, H, P, N, S) if s != C or reste]
        plaene = [p for p in plaene if p is not None]
        if bisher:
            plaene.append(Plan("bisher", bisher, [], kz(bisher)))
        if not plaene:
            return None
        p = bewerten_x(plaene, gewichte)[0]
        return Plan(X, p.stangen, p.uebrig, p.werte, f"automatisch nach allen Zielen bewertet "
                    f"({gewichte_x_text(gewichte)}); gewählt wie {STRATEGIEN.get(p.strategie, 'bisher')}",
                    [f"{q.strategie}: {_z(punkte_x(q, gewichte))} Punkte" for q in bewerten_x(plaene, gewichte)])
    if strategie == E:
        plaene = [planen(g, s, laengen, reste, je_beladung, min_rest, min_nutz, mehrverschnitt, bisher,
                         buendeln_an=buendeln_an) for s in (A, B, C, D) if s != C or reste]
        plaene = [p for p in plaene if p is not None]
        if bisher:
            plaene.append(Plan("bisher", bisher, [], kz(bisher)))
        if not plaene:
            return None
        beste = bewerten(plaene, gewichte)
        p = beste[0]
        return Plan(E, p.stangen, p.uebrig, p.werte, f"ausgewogen bewertet (Gewichte {gewichte_text(gewichte)}); "
                    f"gewählt wie {STRATEGIEN.get(p.strategie, 'bisher')}")
    raise ValueError(f"unbekannte Strategie {strategie}")


def gewichte_text(gewichte=None):
    g = dict(GEWICHTE, **(gewichte or {}))
    return (f"Material + Beladungen, {g['belegung']:.2f} € je verschiedene Belegung, verwertbarer Rest "
            f"{g['rest_mm'] * 1000:.2f} € je m").replace(".", ",")


def punkte(p, gewichte=None):
    """Ausgewogene Bewertung in €: Gesamtkosten (Material + Beladungen) + € je verschiedene Belegung (Programm,
    Rüsten, Sortieren) − Gutschrift für verwertbare Reststücke (nur mit Reststücken). Ohne Preis: unendlich."""
    g = dict(GEWICHTE, **(gewichte or {}))
    w = p.werte
    if w["gesamt"] is None:
        return math.inf
    return w["gesamt"] + g["belegung"] * w["belegungen"] - g["rest_mm"] * w["rest_verwertbar_mm"]


def schnittzeit(werte, zeit):
    """Planabhängige Schneidzeit der Trennschnitte [s] (ohne Stangenwechsel, die zählen die Beladungen in €)."""
    if not zeit or werte.get("schnitte") is None:
        return 0.0
    return werte["enden_mm"] * zeit[1] + werte["schnitte"] * zeit[2]


def punkte_x(p, gewichte=None):
    """Mehrzielbewertung in € (Strategie X): ausgewogene Punkte (Material, Beladungen, € je Belegung, Restgutschrift)
    + € je Artikelwechsel + € je Teil im Zwischenlager + € je Minute Schneidzeit der Trennschnitte."""
    b = punkte(p, gewichte)
    if b == math.inf:
        return b
    g = dict(GEWICHTE, **GEWICHTE_X)
    g.update(gewichte or {})
    w = p.werte
    return (b + g["artikelwechsel"] * (w.get("artikelwechsel") or 0) + g["zwischenlager"] * (w.get("zwischenlager") or 0)
            + g["minute"] * schnittzeit(w, g.get("zeit")) / 60)


def bewerten_x(plaene, gewichte=None):
    return sorted(plaene, key=lambda p: (punkte_x(p, gewichte),
                                         p.werte["gesamt"] if p.werte["gesamt"] is not None else math.inf,
                                         p.werte["stangen"]))


def gewichte_x_text(gewichte=None):
    g = dict(GEWICHTE, **GEWICHTE_X)
    g.update(gewichte or {})
    return (f"Material + Beladungen, {g['belegung']:.2f} € je Belegung, {g['artikelwechsel']:.2f} € je Artikelwechsel, "
            f"{g['zwischenlager']:.2f} € je Teil im Zwischenlager, {g['minute']:.2f} € je Minute Schneidzeit"
            ).replace(".", ",")


def bewerten(plaene, gewichte=None):
    """Pläne nach ausgewogenen Punkten (punkte), dann Kosten, dann Stangen."""
    return sorted(plaene, key=lambda p: (punkte(p, gewichte),
                                         p.werte["gesamt"] if p.werte["gesamt"] is not None else math.inf,
                                         p.werte["stangen"]))


def alle(g, laengen, reste=(), je_beladung=0.0, min_rest=0.0, min_nutz=REST_MIN_NUTZ, mehrverschnitt=0.02,
         bisher=None, abbruch=None, gewichte=None):
    """Alle Strategien einer Gruppe: {Strategie: Plan}; C nur mit Resten. abbruch() → True beendet nach der laufenden
    Strategie (Ergebnis bis dahin)."""
    out = {}
    for s in REIHE:
        if s == C and not reste:
            continue
        if abbruch and abbruch():
            break
        if s == E:
            kands = [p for x, p in out.items() if x in (A, B, C, D)]
            if bisher:
                kands.append(Plan("bisher", bisher, [], kennzahlen(g, bisher, [], _laengen_fuer(g, laengen), reste,
                                                                   je_beladung, min_rest, min_nutz)))
            if kands:
                p = bewerten(kands, gewichte)[0]
                out[E] = Plan(E, p.stangen, p.uebrig, p.werte, f"ausgewogen bewertet ({gewichte_text(gewichte)}); gewählt "
                                                               f"wie {STRATEGIEN.get(p.strategie, 'bisher')}")
            continue
        p = planen(g, s, laengen, reste, je_beladung, min_rest, min_nutz, mehrverschnitt, bisher)
        if p is not None:
            out[s] = p
    return out


def _z(w, stellen=2):
    return f"{w:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def empfehlung(plaene, bisher_werte=None):
    """(Strategie, Begründung): die ausgewogene Strategie, mit Zahlen gegenüber dem bisherigen Plan."""
    if not plaene:
        return None, "keine Strategie ausführbar"
    s = E if E in plaene else X if X in plaene else next(iter(plaene))
    p = plaene[s]
    w = p.werte
    teile = [f"{w['stangen']} Stangen ({laengen_text(w['je_laenge'])})"]
    if w.get("reste"):
        teile.append(f"{w['reste']} Reststück{'e' if w['reste'] > 1 else ''}")
    if bisher_werte:
        if w["einkauf"] is not None and bisher_werte.get("einkauf") is not None:
            d = bisher_werte["einkauf"] - w["einkauf"]
            if abs(d) > 0.005:
                teile.append(f"Einkauf {'−' if d > 0 else '+'}{_z(abs(d))} € gegenüber bisher")
        dm = bisher_werte["gekauft_mm"] - w["gekauft_mm"]
        if abs(dm) > EPS:
            teile.append(f"{'−' if dm > 0 else '+'}{_z(abs(dm), 0)} mm Material")
    teile.append(f"Ausnutzung {_z(100 * w['ausnutzung'], 1)} %")
    return s, f"{STRATEGIEN[s]}: " + ", ".join(teile) + f". {p.warum[:1].upper() + p.warum[1:]}."


def laengen_text(je_laenge):
    return " + ".join(f"{n} × {laenge / 1000:g} m".replace(".", ",") for laenge, n in je_laenge.items()) or "keine"
