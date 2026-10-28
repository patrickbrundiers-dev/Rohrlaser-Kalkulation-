"""Material- und Fertigungsvarianten vergleichen (Wettbewerbsvergleich P1-5).

Je Stangengruppe (Profil, Werkstoff, Oberfläche) die ausführbaren Varianten nebeneinander:
  - Lieferlängen: Stangenlänge des Angebots und die anderen Lieferlängen (auch mit Zuschnitt beim Lieferanten), wie
    sie der Vergleich der Lieferlängen beim Optimieren schon plant (rechnen.laengen_bewerten)
  - Material aus dem Lager bzw. Reststücken (nur mit Einstellung 'lager_aktiv'): geplante Variante, Stangen aus dem
    Bestand statt Neukauf (lager.planen; der Lagerwert zählt als Kosten, Restwert aus den Einstellungen)
Kennzahlen je Variante: Kosten (Material, Stangenwechsel/Beladungen, Zuschnitt beim Lieferanten), Verschnitt [%],
Lieferstangen (Neukauf), Wechselzeit (Beladungen × Stangenwechsel der Maschine). Die Laserzeit ist in allen Varianten
gleich (gleiche Teile, gleiche Schnitte) und wird deshalb nicht verglichen.

Alle Varianten kommen aus derselben Optimierung mit denselben Fertigungsregeln (Teileabstand, Greiferrest,
Endbeschnitt, Gehrungen, Stecknasen); Varianten, die nicht ausführbar sind (z. B. Teil zu lang für die Beladelänge),
erscheinen mit Grund und werden nie empfohlen. Fehlende Preise zählen nie als 0 €: dann ist die Variante für das Ziel
Kosten nicht bewertbar.

Zielgröße: Kosten, Verschnitt, Stangenanzahl, Wechselzeit oder Ausgewogen (Gewichte GEWICHTE). Bewertung je
Kriterium = Wert ÷ bester Wert der ausführbaren Varianten (1,0 = beste), Punkte = gewichteter Mittelwert; empfohlen
wird die Variante mit den wenigsten Punkten (bei Gleichstand die günstigere, dann die mit weniger Stangen). Bei nur
einer Zielgröße ist die Empfehlung damit genau die Variante mit dem besten Wert dieser Größe.

Status der Optimierung je Gruppe aus der Auswertung des Optimierers: 'optimal (…)' ist bewiesen, sonst 'nicht
bewiesen (Suche begrenzt)'; Vergleichsrechnungen anderer Lieferlängen sind nie als optimal gekennzeichnet.
"""
from . import rechnen

KRITERIEN = (("kosten", "Kosten [€]"), ("verschnitt", "Verschnitt [%]"), ("stangen", "Lieferstangen (Neukauf)"),
             ("zeit", "Wechselzeit [min]"))
GEWICHTE = {"Kosten": dict(kosten=1.0), "Verschnitt": dict(verschnitt=1.0), "Stangenanzahl": dict(stangen=1.0),
            "Wechselzeit": dict(zeit=1.0),
            "Ausgewogen": dict(kosten=0.5, verschnitt=0.2, stangen=0.1, zeit=0.2)}
ZIELE = tuple(GEWICHTE)
NICHT_BEWIESEN = "nicht bewiesen (Vergleichsrechnung)"


def _ob(x):
    return x or ""


def _variante(name, kosten, verschnitt, stangen, beladungen, wechsel_s, status, geplant=False, fehler=None,
              fehlt=(), aus_lager=0, laenge=None):
    return dict(name=name, kosten=kosten, verschnitt=verschnitt, stangen=stangen, beladungen=beladungen,
                zeit=beladungen * wechsel_s / 60 if beladungen is not None else None, status=status, geplant=geplant,
                fehler=fehler, fehlt=list(fehlt), aus_lager=aus_lager, laenge=laenge)


def gruppen(kopf, positionen, ergebnis, k, tabellen, einst, lagerplan=None):
    """Varianten je Gruppe: [dict(profil, werkstoff, oberflaeche, stange, status, varianten=[…], laengen_index
    (Gruppe in ergebnis['laengen'] zum Übernehmen einer Lieferlänge oder None), grundlaenge)].
    lagerplan = lager.planen(…) für das aktuelle Ergebnis oder None (dann keine Lager-Variante)."""
    if not ergebnis:
        return []
    m = rechnen.maschine(kopf, k) or {}
    wechsel_s = rechnen.stangenwechsel_zeiten(m)[0]
    werte = rechnen.stangen_werte(ergebnis, kopf, positionen, k, tabellen)
    laengen = {(vg["profil"], vg["werkstoff"], _ob(vg["oberflaeche"]), vg["stange"]): (i, vg)
               for i, vg in enumerate(ergebnis.get("laengen") or ())}
    lager_nr = {b["nr"]: b for b in (lagerplan or {}).get("stangen") or ()}
    out = []
    for a in ergebnis.get("auswertung") or ():
        if a.get("beistellung"):              # Kundenmaterial: keine Materialvarianten
            continue
        schl = (a["profil"], a["werkstoff"], _ob(a["oberflaeche"]))
        grund = a.get("grundlaenge", a["stange"])
        st = [(s, w) for s, w in zip(ergebnis["stangen"], werte, strict=True)
              if (s["profil"], s["werkstoff"], _ob(s.get("oberflaeche"))) == schl and not s.get("beistellung")
              and (s["stange"] == a["stange"] or a.get("vorgegeben"))]
        varianten = []
        index, vg = laengen.get(schl + (grund,), (None, None))
        if vg:
            b = rechnen.laengen_bewerten(vg, kopf, positionen, k, tabellen, einst)
            for v in b["varianten"]:
                geplant = v["laenge"] == a["stange"]
                varianten.append(_variante(
                    f"{rechnen.m_text(v['laenge'])}-m-Stangen" + (" mit Zuschnitt" if v["zuschnitt"] else ""),
                    None if v["fehlt"] else v["gesamt"], 100 * v["verschnitt_anteil"], v["lieferstangen"],
                    v["werkstuecke"], wechsel_s, a["bewertung"] if geplant else NICHT_BEWIESEN, geplant,
                    v["fehler"], v["fehlt"], laenge=v["laenge"]))
        else:
            mat = sum(s["stange"] for s, _ in st)
            nutz = sum(w["summe"] for _, w in st)
            kosten = [w["kosten"] for _, w in st]
            je_ws, fehlt_ws = rechnen.je_werkstueck_kosten(kopf, k, tabellen)
            beladungen = sum(len(s.get("werkstuecke") or ()) or 1 for s, _ in st)
            ok = None not in kosten and not fehlt_ws
            varianten.append(_variante(
                f"{rechnen.m_text(a['stange'])}-m-Stangen (Angebot)" if not a.get("vorgegeben")
                else f"vorgegebene Stangen ({a['vorgegeben']})",
                sum(kosten) + je_ws * beladungen if ok else None, 100 * (mat - nutz) / mat if mat else 0.0,
                len(st), beladungen, wechsel_s, a["bewertung"], True, None,
                [] if ok else ["Preis der Stange fehlt" if None in kosten else fehlt_ws], laenge=a["stange"]))
        aus = [lager_nr[s["nr"]] for s, _ in st if s["nr"] in lager_nr and lager_nr[s["nr"]]["quelle"] != "Neukauf"]
        geplant = next((v for v in varianten if v["geplant"]), None)
        if aus and geplant and not geplant["fehler"]:
            spar = [b["ersparnis"] for b in aus]
            wert = [b["lagerwert"] for b in aus]
            ok = geplant["kosten"] is not None and None not in spar and None not in wert
            reste = sum(1 for b in aus if b["quelle"] == "Rest")
            varianten.append(dict(_variante(
                "wie geplant, " + (f"{len(aus) - reste} aus Lager" if len(aus) > reste else "")
                + (", " if reste and len(aus) > reste else "") + (f"{reste} aus Reststücken" if reste else ""),
                geplant["kosten"] - sum(spar) + sum(wert) if ok else None, geplant["verschnitt"],
                geplant["stangen"] - len(aus), geplant["beladungen"], wechsel_s, geplant["status"], False, None,
                [] if ok else ["Preis oder Lagerwert fehlt"], len(aus), geplant["laenge"]), lager=True))
        out.append(dict(profil=a["profil"], werkstoff=a["werkstoff"], oberflaeche=a["oberflaeche"],
                        stange=a["stange"], status=a["bewertung"], teile=a.get("teile"), varianten=varianten,
                        laengen_index=index, grundlaenge=grund))
    return out


def bewerten(varianten, ziel="Kosten", gewichte=None):
    """Punkte je Variante und Empfehlung. Ergebnis dict(beste=Index oder None, punkte=[…], gewichte, grund).
    Nicht ausführbare Varianten und Varianten ohne Wert eines gewichteten Kriteriums bekommen keine Punkte."""
    g = {n: w for n, w in (gewichte or GEWICHTE[ziel]).items() if w}
    summe = sum(g.values()) or 1.0
    ok = [i for i, v in enumerate(varianten) if not v.get("fehler") and all(v.get(n) is not None for n in g)]
    punkte = [None] * len(varianten)
    if not ok:
        return dict(beste=None, punkte=punkte, gewichte=g,
                    grund="keine Variante bewertbar (nicht ausführbar oder Angaben fehlen)")
    bestwert = {n: min(varianten[i][n] for i in ok) for n in g}

    def rel(n, x):
        b = bestwert[n]
        return x / b if b > 0 else (1.0 if x <= 1e-9 else 1.0 + x)
    for i in ok:
        punkte[i] = sum(w * rel(n, varianten[i][n]) for n, w in g.items()) / summe
    beste = min(ok, key=lambda i: (round(punkte[i], 9), varianten[i]["kosten"] if varianten[i]["kosten"] is not None
                                   else float("inf"), varianten[i]["stangen"]))
    namen = dict(KRITERIEN)
    grund = (f"Ziel {ziel}: " + ", ".join(f"{namen[n]} × {w:g}" for n, w in g.items())
             + f"; bewertet {len(ok)} von {len(varianten)} Varianten, je Kriterium Wert ÷ bester Wert")
    return dict(beste=beste, punkte=punkte, gewichte=g, grund=grund)
