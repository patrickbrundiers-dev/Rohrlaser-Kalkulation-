"""Strategievergleich je Abmessung für den Nesting-Arbeitsplatz (Patrick 23.11.2026, nesting.py). Ohne Qt.

Je Stangengruppe des Angebots (Kundenmaterial, Musterteile und von Hand vorgegebene Stangen ausgenommen) werden
die Strategien A … E gerechnet und dem bisherigen Plan (Optimierung der Stangenlänge des Angebots, so wie das
Programm bisher rechnet) gegenübergestellt, mit denselben Fertigungsregeln, Preisen und Reststücken wie beim
Optimieren (rechnen.nesting_daten). Lieferlängen über der Beladelänge (12 m mit Zuschnitt) gehen wie beim Optimieren
ein (rechnen.nesting_zuschnitt): ist die Zuschnitt-Variante besser, zeigt die Zeile deren Werte.

Die Rechenzeit je Strategie wird gemessen und mitgegeben (nur Anzeige und Protokoll, die Rechnung selbst hat
Schrittgrenzen und ist auf jedem Rechner gleich). abbruch() → True beendet nach der laufenden Strategie.
"""
import time

from . import nesting as ne, optimierung as opt, rechnen

BISHER = "bisher"
SPALTEN = (("name", "Strategie"), ("laengen", "Stangen"), ("gekauft_m", "Eingekauft [m]"),
           ("einkauf", "Einkauf [€]"), ("kalkulatorisch", "kalkulatorisch [€]"), ("teile_m", "Teile [m]"),
           ("schnitt_mm", "Schnittverluste [mm]"), ("rest_verwertbar_mm", "verwertbarer Rest [mm]"),
           ("verschnitt_mm", "Verschnitt [mm]"), ("ausnutzung", "Ausnutzung"), ("eur_teil", "€ je Teil"),
           ("beladungen", "Beladungen"), ("belegungen", "Belegungen"), ("ersparnis", "Einkauf ggü. bisher [€]"),
           ("zeit", "Rechenzeit [s]"))


def _gruppen(kopf, positionen, k, tabellen, einst):
    gruppen, _, _ = rechnen.gruppen_bilden(kopf, positionen, k, tabellen, einst)
    m = rechnen.maschine(kopf, k)
    out = []
    for g in gruppen:
        if g.beistellung or g.muster:
            continue
        mg = rechnen.maschine_gruppe(g, m, k)
        if rechnen.stangen_vorgabe(kopf, rechnen.gruppe_schluessel(g), (mg or {}).get("max_stange")):
            continue
        info = rechnen.laengen_info(g, k, tabellen, mg, einst) if tabellen else None
        out.append((g, mg, info))
    return out


def zeile(name, werte, bisher=None, zs=None, zeit=None):
    """Tabellenzeile aus Kennzahlen (nesting.kennzahlen); zs: bessere Zuschnitt-Variante (überschreibt Einkauf,
    Länge und Beladungen)."""
    w = dict(werte)
    laengen = ne.laengen_text(w["je_laenge"])
    if w.get("reste"):
        laengen += f" + {w['reste']} Rest{'e' if w['reste'] > 1 else ''}"
    if zs:
        w.update(zs["werte"])
        teile = [f"{len(zs['v']['stangen'])} × {rechnen.m_text(zs['laenge'])} m Zuschnitt"]
        if zs["plan"] is not None:
            teile.append(ne.laengen_text(zs["plan"].werte["je_laenge"]))
        laengen = " + ".join(teile)
        for n in ("kalkulatorisch", "teile_mm", "schnitt_mm", "rest_verwertbar_mm", "verschnitt_mm", "ausnutzung",
                  "eur_teil", "belegungen"):
            w[n] = None
        w["kalkulatorisch"] = w["einkauf"]
    ersparnis = None
    if bisher is not None and bisher.get("einkauf") is not None and w.get("einkauf") is not None:
        ersparnis = bisher["einkauf"] - w["einkauf"]
    return dict(name=name, laengen=laengen, gekauft_m=w["gekauft_mm"] / 1000, einkauf=w.get("einkauf"),
                kalkulatorisch=w.get("kalkulatorisch"),
                teile_m=w["teile_mm"] / 1000 if w.get("teile_mm") is not None else None,
                schnitt_mm=w.get("schnitt_mm"), rest_verwertbar_mm=w.get("rest_verwertbar_mm"),
                verschnitt_mm=w.get("verschnitt_mm"), ausnutzung=w.get("ausnutzung"), eur_teil=w.get("eur_teil"),
                beladungen=w["beladungen"], belegungen=w.get("belegungen"), ersparnis=ersparnis, zeit=zeit,
                zuschnitt=bool(zs))


def vergleich(kopf, positionen, k, tabellen, einst, abbruch=None, fortschritt=None):
    """Je Gruppe dict(schluessel, titel, gruppe, daten, plaene {BISHER, A … E: nesting.Plan}, zuschnitt {Strategie:
    Variante}, zeilen [Tabellenzeile], empfehlung (Strategie, Text), gewaehlt (gespeicherte Wahl oder '')).
    fortschritt(schritt, schritte, text) vor jeder Gruppe."""
    m = rechnen.maschine(kopf, k)
    saege = rechnen._n(rechnen.einstellung_wert(einst, "zuschnitt_verlust"))
    puffer = rechnen._n(rechnen.einstellung_wert(einst, "zuschnitt_puffer"))
    gruppen = _gruppen(kopf, positionen, k, tabellen, einst)
    out = []
    for n, (g, mg, info) in enumerate(gruppen):
        if abbruch and abbruch():
            break
        if fortschritt:
            fortschritt(n, len(gruppen), f"{g.profil} / {g.werkstoff}")
        schl = rechnen.laengen_schluessel(rechnen.gruppe_schluessel(g))
        daten = rechnen.nesting_daten(g, info, kopf, positionen, k, tabellen, einst, mg or m)
        laengen = ne._laengen_fuer(g, daten["laengen"])
        t = time.perf_counter()
        bisher_f = opt.optimiere(g) if info is None or info.get("basis_lieferbar", True) else None
        plaene, zeiten, zs = {}, {}, {}
        if bisher_f is not None:
            st = [(g.stange, f, "") for f in bisher_f]
            plaene[BISHER] = ne.Plan(BISHER, st, [], ne.kennzahlen(g, st, [], laengen or [ne.Laenge(g.stange)],
                                                                   daten["reste"], daten["je_beladung"],
                                                                   daten["min_rest"], daten["min_nutz"]),
                                     "so wie das Programm bisher rechnet (Stangenlänge des Angebots)")
            zeiten[BISHER] = time.perf_counter() - t
        for s in (ne.A, ne.B, ne.C, ne.D, ne.E):
            if abbruch and abbruch():
                break
            if s == ne.C and not daten["reste"]:
                continue
            t = time.perf_counter()
            p = rechnen.nesting_planen(g, s, daten, bisher_f) if daten["laengen"] else None
            z = rechnen.nesting_zuschnitt(g, p, s, daten, mg or m, saege, puffer)
            zeiten[s] = time.perf_counter() - t
            if p is not None:
                plaene[s] = p
            if z:
                zs[s] = z
        wb = plaene[BISHER].werte if BISHER in plaene else None
        zeilen = []
        for s, p in plaene.items():
            name = "bisher" if s == BISHER else f"{s} {ne.STRATEGIEN[s]}"
            zeilen.append(dict(zeile(name, p.werte, wb, zs.get(s), round(zeiten.get(s, 0.0), 2)), strategie=s))
        for s, z in zs.items():
            if s not in plaene:
                zeilen.append(dict(zeile(f"{s} {ne.STRATEGIEN[s]}", dict(je_laenge={}, gekauft_mm=0, beladungen=0,
                                                                         teile_mm=None), wb, z,
                                         round(zeiten.get(s, 0.0), 2)), strategie=s))
        emp = ne.empfehlung({s: p for s, p in plaene.items() if s != BISHER}, wb)
        gew = (kopf.get("nesting") or {}).get(schl) or ""
        if (kopf.get("stangen_hand") or {}).get(schl):
            gew = rechnen.NESTING_HAND
        out.append(dict(schluessel=schl, titel=f"{g.profil} / {g.werkstoff}" + (f" / {g.oberflaeche}"
                                                                                  if g.oberflaeche else "")
                        + f" ({rechnen.m_text(g.stange)} m)", gruppe=g, daten=daten, plaene=plaene, zuschnitt=zs,
                        zeilen=zeilen, empfehlung=emp, gewaehlt=gew))
    return out


def text(z, schl):
    """Zelltext einer Zeile."""
    w = z.get(schl)
    if w is None:
        return "—" if schl not in ("name", "laengen") else ""
    if schl == "ausnutzung":
        return f"{rechnen.zahl(100 * w, 1)} %"
    if schl in ("einkauf", "kalkulatorisch", "eur_teil", "ersparnis"):
        return rechnen.zahl(w, 2)
    if schl in ("gekauft_m", "teile_m"):
        return rechnen.zahl(w, 2)
    if schl in ("schnitt_mm", "rest_verwertbar_mm", "verschnitt_mm"):
        return rechnen.zahl(w, 0)
    if schl == "zeit":
        return rechnen.zahl(w, 2)
    return str(w)


def hand_aus_plan(plan, positionen):
    """Belegung von Hand zum Speichern (rechnen.hand_planen) aus den Stangen eines Plans."""
    return [dict(laenge=laenge, rest=rest or "",
                 teile=[[rechnen.schluessel(positionen[t.zeile - rechnen.ZEILE0], t.zeile - rechnen.ZEILE0),
                         round(t.laenge, 2)] for t, _ in f]) for laenge, f, rest in plan.stangen]


def verschieben(g, stangen, von, teil_index, nach, daten, uebrig=()):
    """Teil teil_index der Stange von auf die Stange nach umsetzen (nach = None: neue Stange der Stangenlänge der
    Gruppe bzw. der kleinsten Länge, auf die es passt). Geprüft mit denselben Regeln (nesting.passt_auf); eine leer
    gewordene Stange fällt weg. Ergebnis: (neue Stangen, Fehlertext oder '')."""
    st = [(laenge, [t for t, _ in f], rest) for laenge, f, rest in stangen]
    if not (0 <= von < len(st)) or not (0 <= teil_index < len(st[von][1])):
        return stangen, "Teil nicht gefunden"
    t = st[von][1][teil_index]
    if nach is None:
        laengen = sorted(x.laenge for x in daten["laengen"])
        laenge = g.stange if g.stange in laengen and ne.passt_auf(g, g.stange, [t]) else next(
            (x for x in laengen if ne.passt_auf(g, x, [t])), None)
        if laenge is None:
            return stangen, "Teil passt auf keine lieferbare Länge"
        st.append((laenge, [t], ""))
    else:
        if nach == von or not (0 <= nach < len(st)):
            return stangen, ""
        laenge, ziel, rest = st[nach]
        if not ne.passt_auf(g, laenge, ziel + [t]):
            h = opt.replace(g, stange=laenge, teile=[])
            frei = h.nutzbar_bis - opt.belegt(h, ne._folge(g, laenge, ziel))
            return stangen, (f"Passt nicht: auf Stange {nach + 1} sind noch {rechnen.zahl(max(frei, 0), 0)} mm frei, "
                             f"das Teil braucht {rechnen.zahl(opt.mindestbedarf(g, t), 0)} mm (mit Schnitt).")
        st[nach] = (laenge, ziel + [t], rest)
    st[von] = (st[von][0], [x for i, x in enumerate(st[von][1]) if i != teil_index], st[von][2])
    neu = [(laenge, ne._folge(g, laenge, teile), rest) for laenge, teile, rest in st if teile]
    ne.pruefe(g, neu, list(uebrig), None, daten["reste"])
    return neu, ""
