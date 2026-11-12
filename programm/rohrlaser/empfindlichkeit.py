"""Empfindlichkeit je Annahme (CALC-029, Patrick 12.11.2026 „Alle Empfehlungen“ zum Bericht
Entwicklungspotenziale).

Das Angebot wird je Annahme mit −10 % und +10 % neu gerechnet: Vorschub (alle Vorschübe der Schneiddaten),
Materialpreis (Preise und Lieferlängen-Preise, Tonnenpreise der Werkstoffe), Stundensatz (Maschinen, Stammdaten
Stundensätze und der Snapshot im Angebot; ein ermittelter Maschinensatz bleibt), Rüstzeit (Maschine, Abmessung,
Arbeitsschritte) und Zeitaufwand der Zusatzarbeiten. Ergebnis je Position
und für das Angebot: Änderung des Preises in €. Die drei größten Hebel stehen vorn. Ist die Änderung nach oben und
unten nicht gleich groß (z. B. weil eine Stange mehr oder weniger gebraucht wird oder eine andere Lieferlänge
günstiger wird), heißt die Annahme „nicht linear“. Beim Materialpreis wird neu optimiert (die Wahl der Lieferlänge
kann kippen), sonst nicht. Das Angebot bleibt unverändert. Ohne Qt."""
import copy

from . import rechnen

SCHRITT = 0.10
VORSCHUB, MATERIAL, SATZ, RUESTEN, ZUSATZ = "Vorschub", "Materialpreis", "Stundensatz", "Rüstzeit", \
    "Zeit Zusatzarbeiten"
HEBEL = (VORSCHUB, MATERIAL, SATZ, RUESTEN, ZUSATZ)
LINEAR_TOLERANZ = 0.02      # |Δ+ + Δ−| bis 2 % von max(|Δ+|, |Δ−|) gilt als linear
FELDER_SATZ = ("stundensatz", "stundensatz_sn")
FELDER_RUESTEN = ("ruestzeit", "stangenwechsel", "stangenwechsel_sn")


def _mal(z, felder, f):
    z = dict(z)
    for n in felder:
        if isinstance(z.get(n), (int, float)) and not isinstance(z.get(n), bool):
            z[n] = z[n] * f
    return z


def _variante(hebel, f, kopf, k, tabellen):
    """(kopf, k, tabellen) mit der Annahme × f."""
    kopf, tab = dict(kopf), dict(tabellen)
    k2 = copy.copy(k)
    if hebel == VORSCHUB:
        tab["schneiddaten"] = [_mal(z, rechnen.VORSCHUB_FELDER, f) for z in tabellen.get("schneiddaten") or ()]
    elif hebel == MATERIAL:
        tab["preise"] = [_mal(z, ("preis",), f) for z in tabellen.get("preise") or ()]
        tab["lieferlaengen"] = [_mal(z, ("preis",), f) for z in tabellen.get("lieferlaengen") or ()]
        k2.werkstoffe = {w: _mal(z, ("tonnenpreis",), f) for w, z in k.werkstoffe.items()}
        if not rechnen._leer(kopf.get("preis_m")):
            kopf["preis_m"] = kopf["preis_m"] * f
    elif hebel == SATZ:
        k2.maschinen = {m: _mal(z, FELDER_SATZ, f) for m, z in k.maschinen.items()}
        tab["stundensaetze"] = [_mal(z, ("satz",), f) for z in tabellen.get("stundensaetze") or ()]
        zb = kopf.get("zeitbasis")
        if isinstance(zb, dict):        # Snapshot der Stundensätze im Angebot
            kopf["zeitbasis"] = dict(zb, maschine=_mal(zb.get("maschine") or {}, FELDER_SATZ, f),
                                     saetze={n: (w * f if isinstance(w, (int, float)) else w)
                                             for n, w in (zb.get("saetze") or {}).items()})
    elif hebel == RUESTEN:
        k2.maschinen = {m: _mal(z, FELDER_RUESTEN, f) for m, z in k.maschinen.items()}
        kopf = _mal(kopf, ("ruesten_abmessung", "ruestzeit"), f)
        zb = kopf.get("zeitbasis")
        if isinstance(zb, dict):
            kopf["zeitbasis"] = dict(zb, maschine=_mal(zb.get("maschine") or {}, FELDER_RUESTEN, f),
                                     schritte=[_mal(z, ("ruestzeit", "zeit"), f) for z in zb.get("schritte") or ()])
        tab["arbeitsschritte"] = [_mal(z, ("ruestzeit",), f) for z in tabellen.get("arbeitsschritte") or ()]
    elif hebel == ZUSATZ:
        tab["zusatzarbeiten"] = [_mal(z, ("zeit", "ruestzeit") + (("preis",) if z.get("art") == "s/Stück" else ()), f)
                                 for z in tabellen.get("zusatzarbeiten") or ()]
    return kopf, k2, tab


def rechnen_alle(kopf, positionen, ergebnis, k, tabellen, einst_db, schritt=SCHRITT, hebel=HEBEL):
    """dict(angebot=[dict(hebel, plus, minus, linear, stangen)], positionen=[dict(pos, hebel=[...] top 3)],
    basis=Netto). plus/minus = Änderung des Netto-Preises in € bei +/− schritt."""
    einst = rechnen.einstellungen_angebot(kopf, einst_db)
    zeilen0, summen0 = rechnen.kalkulation(kopf, positionen, ergebnis, k, tabellen, einst)
    stangen0 = _stangen(ergebnis)
    halten = []                         # Varianten bis zum Ende behalten (Merker nach id(tabellen))
    je_pos = {i: [] for i in range(len(positionen))}
    ang = []
    for h in hebel:
        werte = {}
        for f in (1 + schritt, 1 - schritt):
            kp, k2, tab = _variante(h, f, kopf, k, tabellen)
            halten.append((kp, k2, tab))
            erg = rechnen.optimieren(kp, positionen, k2, tab, einst_db) if h == MATERIAL else ergebnis
            e2 = rechnen.einstellungen_angebot(kp, einst_db)
            z, s = rechnen.kalkulation(kp, positionen, erg, k2, tab, e2)
            werte[f] = (z, s, _stangen(erg))
        (zp, sp, stp), (zm, sm, stm) = werte[1 + schritt], werte[1 - schritt]
        plus, minus = sp["verkauf"] - summen0["verkauf"], sm["verkauf"] - summen0["verkauf"]
        vh = _verh(h, schritt)
        ang.append(dict(hebel=h, plus=plus, minus=minus, linear=_linear(plus, minus, vh),
                        stangen=(stm, stangen0, stp) if stp != stangen0 or stm != stangen0 else None))
        for i, (a, b, c) in enumerate(zip(zeilen0, zp, zm)):
            if a is None or b is None or c is None:
                continue
            p0 = a["preis_teil"] * a["stueck"]
            dp, dm = b["preis_teil"] * b["stueck"] - p0, c["preis_teil"] * c["stueck"] - p0
            je_pos[i].append(dict(hebel=h, plus=dp, minus=dm, linear=_linear(dp, dm, vh)))
    ang.sort(key=lambda x: -max(abs(x["plus"]), abs(x["minus"])))
    pos = []
    for i, liste in je_pos.items():
        liste.sort(key=lambda x: -max(abs(x["plus"]), abs(x["minus"])))
        pos.append(dict(pos=positionen[i].get("pos"), hebel=[x for x in liste if abs(x["plus"]) + abs(x["minus"])
                                                                > 0.005][:3]))
    return dict(angebot=ang, positionen=pos, basis=summen0["verkauf"])


def _stangen(ergebnis):
    try:
        return len((ergebnis or {}).get("stangen") or ())
    except TypeError:
        return None


def _linear(plus, minus, verh=1.0):
    """minus ≈ −plus × verh (verh ≠ 1 beim Vorschub: die Zeit geht mit 1/Vorschub)."""
    gross = max(abs(plus), abs(minus))
    return gross < 0.005 or abs(plus * verh + minus) <= LINEAR_TOLERANZ * gross


def _verh(hebel, schritt):
    if hebel != VORSCHUB:
        return 1.0
    return (1 / (1 - schritt) - 1) / (1 - 1 / (1 + schritt))


def text(x):
    """„+10 %: +12,30 €, −10 %: −12,30 €“ mit Zusatz „nicht linear“."""
    z = rechnen.zahl
    t = f"+10 %: {'+' if x['plus'] >= 0 else ''}{z(x['plus'])} €, −10 %: {'+' if x['minus'] >= 0 else ''}{z(x['minus'])} €"
    if not x["linear"]:
        t += " (nicht linear)"
    if x.get("stangen"):
        t += f", Stangen {x['stangen'][0]} / {x['stangen'][1]} / {x['stangen'][2]}"
    return t
