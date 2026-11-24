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
STRATEGIEN = {A: "Minimaler Materialverbrauch", B: "Geringste Materialkosten", C: "Maximale Reststückverwertung",
              D: "Schnellste Fertigung", E: "Ausgewogen", F: "Wenigste Stangen", G: "Geringster Verschnitt",
              H: "Schnellrechnung"}
KURZ = {A: "wenig Material", B: "günstigster Einkauf", C: "Reste zuerst", D: "schnell fertigen", E: "ausgewogen",
        F: "wenigste Stangen", G: "wenig Verschnitt", H: "schnell gerechnet"}
REIHE = (A, B, C, D, E, F, G, H)        # Reihenfolge im Vergleich
SCHWANZ_MAX = 6          # so viele am schwächsten belegte Stangen werden höchstens neu auf Mischungen verteilt
MISCH_VERSUCHE = 30      # Mischungen je Schwanzgröße, die mit vorrat_planen geprüft werden
SCHWANZ_RUNDEN = 3       # so oft wird der Schwanz nach einer Verbesserung erneut probiert
MISCHPLAN_MAX_TEILE = 200   # Mischplan über alle Teile (vorrat_planen) nur bis zu so vielen Teilen; darüber mischt
                            # nur der Schwanz (große Aufträge: Rechenzeit, die Einzellängen sind dort schon dicht)
BUENDELN_SCHRITTE = 4000  # Prüfungen beim Bündeln der Reste je Plan
GEWICHTE = dict(belegung=5.0, rest_mm=0.0)   # Strategie E: € je verschiedene Belegung, € je mm verwertbarer Rest
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
        nicht_eingeplant=len(uebrig), teile=n_teile)


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
    key = ("grund", _gkey(g), tuple(laengen))
    if key in _MERKER:
        einzeln, misch = _MERKER[key][1]
    else:
        einzeln = _kandidaten_einzeln(g, laengen)
        misch = _mischplan(g, laengen, einzeln)
        if len(_MERKER) >= MERKER_MAX:
            _MERKER.pop(next(iter(_MERKER)))
        _MERKER[key] = (g, (einzeln, misch))
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
        return _kopie(_MERKER[key][1])
    p = _plan_mindest(g, strategie, laengen, reste, je_beladung, min_rest, min_nutz, mehrverschnitt, bisher, gewichte,
                      buendeln_an)
    if key is not None:
        if len(_MERKER) >= MERKER_MAX:
            _MERKER.pop(next(iter(_MERKER)))
        _MERKER[key] = (g, _kopie(p))
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

    def fertig(s, st, warum, uebrig=()):
        if st is None:
            return None
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
    s = E if E in plaene else next(iter(plaene))
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
