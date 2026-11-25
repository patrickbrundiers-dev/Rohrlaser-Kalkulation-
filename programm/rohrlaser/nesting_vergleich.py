"""Strategievergleich je Abmessung für den Nesting-Arbeitsplatz (Patrick 23.11.2026, nesting.py). Ohne Qt.

Je Stangengruppe des Angebots (Kundenmaterial, Musterteile und von Hand vorgegebene Stangen ausgenommen) werden
die Strategien A … E gerechnet und dem bisherigen Plan (Optimierung der Stangenlänge des Angebots, so wie das
Programm bisher rechnet) gegenübergestellt, mit denselben Fertigungsregeln, Preisen und Reststücken wie beim
Optimieren (rechnen.nesting_daten). Lieferlängen über der Beladelänge (12 m mit Zuschnitt) gehen wie beim Optimieren
ein (rechnen.nesting_zuschnitt): ist die Zuschnitt-Variante besser, zeigt die Zeile deren Werte.

Die Rechenzeit je Strategie wird gemessen und mitgegeben (nur Anzeige und Protokoll, die Rechnung selbst hat
Schrittgrenzen und ist auf jedem Rechner gleich). abbruch() → True beendet nach der laufenden Strategie.
"""
import csv
import io
import time

from . import masstext, nesting as ne, nesting_machbarkeit as nm, optimierung as opt, rechnen

BISHER = "bisher"
AKTUELL = "aktuell"     # gespeicherter Schnittplan (Ergebnis von Optimieren/F9), Nesting-Arbeitsplatz 2.0 (V1)
# Universelle Konturverschachtelung (Patrick 25.11.2026): Vergleich „ohne Konturverschachtelung“ (nur ebene Gehrungen
# ineinander, wie vor 0.9.487) je Abmessung mit Endkonturen – ursprüngliche gegen optimierte Stangenbelegung
OHNE_KONTUR = "ohne_kontur"
SPALTEN = (("name", "Strategie"), ("laengen", "Stangen"), ("gekauft_m", "Eingekauft [m]"),
           ("einkauf", "Einkauf [€]"), ("kalkulatorisch", "kalkulatorisch [€]"), ("teile_m", "Teile [m]"),
           ("schnitt_mm", "Schnittverluste [mm]"), ("rest_verwertbar_mm", "verwertbarer Rest [mm]"),
           ("verschnitt_mm", "Verschnitt [mm]"), ("ausnutzung", "Ausnutzung"), ("eur_teil", "€ je Teil"),
           ("beladungen", "Beladungen"), ("belegungen", "Belegungen"), ("ersparnis", "Einkauf ggü. bisher [€]"),
           ("ineinander", "Enden ineinander"), ("konturen", "davon Endkonturen"), ("trennschnitte", "Trennschnitte"),
           ("schnitte", "Schnitte"), ("artikelwechsel", "Artikelwechsel"), ("zwischenlager", "Zwischenlager [Teile]"),
           ("maschine_min", "Maschinenzeit planabh. [min]"), ("punkte", "Bewertung X [€]"),
           ("machbar", "Machbarkeit"), ("zeit", "Rechenzeit [s]"))
EIGENE = (BISHER, AKTUELL, OHNE_KONTUR)
# Kennzahlen für „übertroffen“ (Variantenlogik, Patrick 25.11.2026): kleiner ist besser
DOMINANZ = ("gekauft_m", "einkauf", "beladungen", "belegungen", "verschnitt_mm", "artikelwechsel", "zwischenlager",
            "maschine_min")


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
                ineinander=w.get("ineinander"), konturen=w.get("konturen"), trennschnitte=w.get("trennschnitte"),
                schnitte=w.get("schnitte"), artikelwechsel=w.get("artikelwechsel"),
                zwischenlager=w.get("zwischenlager"), zuschnitt=bool(zs), machbar="zulässig", zulaessig=True)


def abdruck(p):
    """Fingerabdruck eines Plans: Stangen in Reihenfolge mit Länge, Teilen, Drehung und Reststück."""
    return tuple((laenge, tuple((t.zeile, t.nr, r) for t, r in f), rest) for laenge, f, rest in p.stangen)


def zeile_von(v, s):
    """Tabellenzeile der Strategie s (auch wenn s mit einer anderen Strategie in einer Zeile steht) oder {}."""
    return next((z for z in v["zeilen"] if z["strategie"] == s or s in z.get("auch", ())), {})


def _uebertroffen(a, b):
    """Ist Zeile a in jeder Kennzahl höchstens so gut wie b und in einer schlechter (b übertrifft a)?"""
    schlechter = False
    for n in DOMINANZ:
        x, y = a.get(n), b.get(n)
        if x is None or y is None:
            if x is None and y is None:
                continue
            return False
        if y > x + 1e-6:
            return False
        if y < x - 1e-6:
            schlechter = True
    return schlechter


def varianten_ordnen(zeilen, empfohlen, gewaehlt="", hoechstens=0):
    """Variantenlogik (Patrick 25.11.2026): Strategien mit genau gleichem Plan stehen in einer Zeile (die empfohlene
    bzw. erste trägt die anderen unter „auch“), Zeilen, die eine andere in allen Kennzahlen übertrifft, werden
    markiert (uebertroffen), und mit hoechstens > 0 bleiben nur so viele Strategiezeilen (nach Bewertung X; die
    empfohlene, die gewählte und die eigenen Zeilen bisher/aktuell bleiben immer)."""
    gruppen = {}
    for z in zeilen:
        if z["strategie"] in EIGENE or z.get("abdruck") is None:
            continue
        gruppen.setdefault(z["abdruck"], []).append(z)
    weg = set()
    for liste in gruppen.values():
        if len(liste) < 2:
            continue
        kopf = next((z for z in liste if z["strategie"] == empfohlen), None) or \
            next((z for z in liste if z["strategie"] == gewaehlt), None) or liste[0]
        kopf["auch"] = [z["strategie"] for z in liste if z is not kopf]
        kopf["name"] += " (= " + ", ".join(kopf["auch"]) + ")"
        weg.update(id(z) for z in liste if z is not kopf)
    out = [z for z in zeilen if id(z) not in weg]
    strat = [z for z in out if z["strategie"] not in EIGENE]
    for z in strat:
        besser = next((y for y in strat if y is not z and y.get("zulaessig", True) and _uebertroffen(z, y)), None)
        if besser is not None:
            z["uebertroffen"] = besser["strategie"]
    if hoechstens and len(strat) > hoechstens:
        fest = {empfohlen, gewaehlt}
        reihe = sorted(strat, key=lambda z: (bool(z.get("uebertroffen")), z.get("punkte") is None,
                                             z.get("punkte") or 0.0))
        behalten = {id(z) for z in reihe[:hoechstens]} | {id(z) for z in strat if z["strategie"] in fest
                                                          or fest & set(z.get("auch", ()))}
        out = [z for z in out if z["strategie"] in EIGENE or id(z) in behalten]
    return out


def aktueller_plan(g, ergebnis, positionen):
    """Stangen der Gruppe g aus dem gespeicherten Schnittplan (ergebnis['stangen']) als Nesting-Stangen
    [(Länge, Folge, Rest)], zugeordnet über Bezug und Länge der Teile; None, wenn das Ergebnis fehlt, nicht zur
    Gruppe passt (Teile geändert) oder Zuschnitte enthält (die zeigt die Zuschnitt-Zeile)."""
    if not ergebnis or not ergebnis.get("stangen"):
        return None
    schl = rechnen.gruppe_schluessel(g)
    eigene = [s for s in ergebnis["stangen"] if rechnen.gruppe_der_stange(s) == schl]
    if not eigene or any(s.get("werkstuecke") or any("werkstueck" in t for t in s["teile"]) for s in eigene):
        return None
    vorrat = {}
    for t in opt.sortiert(g.teile):
        vorrat.setdefault((rechnen.schluessel(positionen[t.zeile - rechnen.ZEILE0], t.zeile - rechnen.ZEILE0),
                           round(t.laenge, 2)), []).append(t)
    out = []
    for s in eigene:
        folge = []
        for x in s["teile"]:
            liste = vorrat.get((x["ref"], round(x["laenge"], 2)))
            if not liste:
                return None
            folge.append((liste.pop(0), x.get("drehung") or 0))
        out.append((s["stange"], folge, str(s.get("rest") or "")))
    if any(vorrat.values()):
        return None
    try:
        ne.pruefe(g, out, [])
    except AssertionError:
        return None
    return out


def profil_werte(g, k):
    """(Profilzeile oder None, kg/m oder None) der Gruppe für die Machbarkeit."""
    prof = (k.profile.get(g.profil) if k is not None else None) or None
    kgm = rechnen.kg_je_m(g.profil, g.werkstoff, k) if k is not None else None
    return prof, kgm


def _machbarkeit(g, plan, m, k, reste):
    prof, kgm = profil_werte(g, k)
    return nm.pruefen(g, plan.stangen, m, prof, kgm, plan.uebrig, reste)


def vergleich(kopf, positionen, k, tabellen, einst, abbruch=None, fortschritt=None, ergebnis=None, status=None):
    """Je Gruppe dict(schluessel, titel, gruppe, daten, plaene {BISHER, A … E: nesting.Plan}, zuschnitt {Strategie:
    Variante}, zeilen [Tabellenzeile], empfehlung (Strategie, Text), gewaehlt (gespeicherte Wahl oder '')).
    fortschritt(schritt, schritte, text) vor jeder Gruppe und Strategie; status(dict) danach mit dem Live-Stand
    (geprüfte Pläne, beste Lösung bisher: Ausnutzung, Verschnitt, Stangen, Rechenzeit). ergebnis = gespeicherter
    Schnittplan: Zeile „aktuell“ (genau der Plan von Optimieren/F9) je Abmessung, wenn er zur Gruppe passt.
    Je Plan die Machbarkeit (nesting_machbarkeit); unzulässige Pläne werden nie empfohlen."""
    m = rechnen.maschine(kopf, k)
    saege = rechnen._n(rechnen.einstellung_wert(einst, "zuschnitt_verlust"))
    puffer = rechnen._n(rechnen.einstellung_wert(einst, "zuschnitt_puffer"))
    gruppen = _gruppen(kopf, positionen, k, tabellen, einst)
    out = []
    t_start = time.perf_counter()
    reihe = [s for s in ne.REIHE]
    schritte = max(1, len(gruppen) * (len(reihe) + 1))
    live = dict(plaene=0, gruppe="", strategie="", beste=None, zeit=0.0)
    vt = veraltet(ergebnis, kopf, positionen, k, tabellen, einst)
    for n, (g, mg, info) in enumerate(gruppen):
        if abbruch and abbruch():
            break
        if fortschritt:
            fortschritt(n * (len(reihe) + 1), schritte, f"{g.profil} / {g.werkstoff}")
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
            ohne = ohne_konturen(g)
            if ohne is not None:            # ursprüngliche Belegung ohne Konturverschachtelung zum Vergleich
                t = time.perf_counter()
                st0 = [(g.stange, f, "") for f in opt.optimiere(ohne)]
                plaene[OHNE_KONTUR] = ne.Plan(OHNE_KONTUR, st0, [], ne.kennzahlen(
                    ohne, st0, [], laengen or [ne.Laenge(g.stange)], daten["reste"], daten["je_beladung"],
                    daten["min_rest"], daten["min_nutz"]), "ohne Konturverschachtelung (nur ebene Gehrungen ineinander)")
                zeiten[OHNE_KONTUR] = time.perf_counter() - t
        akt = aktueller_plan(g, ergebnis, positionen)
        nummern = None
        if akt is not None:
            schl_g = rechnen.gruppe_schluessel(g)
            nummern = [i + 1 for i, x in enumerate(ergebnis["stangen"]) if rechnen.gruppe_der_stange(x) == schl_g]
            plaene[AKTUELL] = ne.Plan(AKTUELL, akt, [], ne.kennzahlen(g, akt, [], laengen or [ne.Laenge(g.stange)],
                                                                      daten["reste"], daten["je_beladung"],
                                                                      daten["min_rest"], daten["min_nutz"]),
                                      "gespeicherter Schnittplan (Optimieren/F9)")
        for j, s in enumerate(reihe):
            if abbruch and abbruch():
                break
            if s == ne.C and not daten["reste"]:
                continue
            if fortschritt:
                fortschritt(n * (len(reihe) + 1) + j + 1, schritte,
                            f"{g.profil} / {g.werkstoff}: {s} {ne.STRATEGIEN[s]}")
            t = time.perf_counter()
            p = rechnen.nesting_planen(g, s, daten, bisher_f) if daten["laengen"] else None
            z = rechnen.nesting_zuschnitt(g, p, s, daten, mg or m, saege, puffer)
            zeiten[s] = time.perf_counter() - t
            if p is not None:
                plaene[s] = p
            if z:
                zs[s] = z
            if status and p is not None:
                live["plaene"] += 1
                w = p.werte
                if live["beste"] is None or (w["ausnutzung"], -w["stangen"]) > (live["beste"]["ausnutzung"],
                                                                                -live["beste"]["stangen"]):
                    live["beste"] = dict(ausnutzung=w["ausnutzung"], verschnitt_mm=w["verschnitt_mm"],
                                         stangen=w["stangen"], strategie=s, gruppe=f"{g.profil} / {g.werkstoff}")
                live.update(gruppe=f"{g.profil} / {g.werkstoff}", strategie=s, zeit=time.perf_counter() - t_start,
                            gruppen=len(gruppen), gruppe_nr=n + 1)
                status(dict(live))
        wb = plaene[BISHER].werte if BISHER in plaene else None
        befunde, je_abdruck = {}, {}
        for s, p in plaene.items():      # Machbarkeit je verschiedenem Plan nur einmal (gleiche Pläne gleich)
            a = abdruck(p) if s != OHNE_KONTUR else None
            if a is None or a not in je_abdruck:
                b = _machbarkeit(g, p, mg or m, k, daten["reste"])
                if a is not None:
                    je_abdruck[a] = b
            befunde[s] = je_abdruck[a] if a is not None else b
        zeit = (daten.get("gewichte") or {}).get("zeit")
        zeilen = []
        for s, p in plaene.items():
            name = {BISHER: "bisher", AKTUELL: "aktuell (gespeichert)",
                    OHNE_KONTUR: "ohne Konturverschachtelung"}.get(s) or f"{s} {ne.STRATEGIEN[s]}"
            z_ = dict(zeile(name, p.werte, wb, zs.get(s), round(zeiten.get(s, 0.0), 2)), strategie=s)
            z_.update(machbar=nm.text(befunde[s], 2), zulaessig=nm.zulaessig(befunde[s]))
            mz = ne.maschinenzeit(p.werte, zeit)
            z_["maschine_min"] = round(mz / 60, 2) if mz is not None and not zs.get(s) else None
            pk = ne.punkte_x(p, daten.get("gewichte"))
            z_["punkte"] = round(pk, 2) if pk != float("inf") and not zs.get(s) else None
            if s not in EIGENE:
                z_["abdruck"] = (abdruck(p), repr(zs[s]["werte"]) if zs.get(s) else None)
            zeilen.append(z_)
        for s, z in zs.items():
            if s not in plaene:
                zeilen.append(dict(zeile(f"{s} {ne.STRATEGIEN[s]}", dict(je_laenge={}, gekauft_mm=0, beladungen=0,
                                                                         teile_mm=None), wb, z,
                                         round(zeiten.get(s, 0.0), 2)), strategie=s))
        kand = {s: p for s, p in plaene.items() if s not in (BISHER, AKTUELL, OHNE_KONTUR)
                and nm.zulaessig(befunde.get(s, ()))}
        emp = ne.empfehlung(kand, wb)
        # Mehrzielbewertung (Patrick 25.11.2026): X wird empfohlen, wenn es nach allen Zielen besser ist als E und E
        # keine bessere Zuschnitt-Variante hat (die rechnet X nicht)
        if ne.X in kand and emp[0] == ne.E and ne.E not in zs and \
                ne.punkte_x(kand[ne.X], daten.get("gewichte")) < ne.punkte_x(kand[ne.E], daten.get("gewichte")) - 0.005:
            emp = ne.empfehlung({ne.X: kand[ne.X]}, wb)
        if emp[0] in zs:                                   # Zeile zeigt die Zuschnitt-Variante: Text danach
            r = next(z for z in zeilen if z["strategie"] == emp[0])
            teile = [r["laengen"], f"eingekauft {rechnen.zahl(r['gekauft_m'], 2)} m"]
            if r.get("ersparnis") is not None and abs(r["ersparnis"]) > 0.005:
                teile.append(f"Einkauf {'−' if r['ersparnis'] > 0 else '+'}{rechnen.zahl(abs(r['ersparnis']), 2)} € "
                             f"gegenüber bisher")
            emp = (emp[0], f"{ne.STRATEGIEN[emp[0]]}: " + ", ".join(teile)
                   + ". Lieferlängen über der Beladelänge schneidet der Lieferant zu (ganze Stange bezahlt).")
        gew = (kopf.get("nesting") or {}).get(schl) or ""
        if (kopf.get("stangen_hand") or {}).get(schl):
            gew = rechnen.NESTING_HAND
        zeilen = varianten_ordnen(zeilen, emp[0], gew,
                                  int(rechnen._n(rechnen.einstellung_wert(einst, "nesting_varianten_max"))))
        out.append(dict(schluessel=schl, titel=f"{g.profil} / {g.werkstoff}" + (f" / {g.oberflaeche}"
                                                                                  if g.oberflaeche else "")
                        + f" ({rechnen.m_text(g.stange)} m)", gruppe=g, daten=daten, plaene=plaene, zuschnitt=zs,
                        zeilen=zeilen, empfehlung=emp, gewaehlt=gew, befunde=befunde, zeiten=zeiten,
                        maschine=mg or m, untergrenze=opt.untergrenze(g) if g.teile else 0,
                        schranke=g.schranke, bewiesen=bool(g.bewiesen and bisher_f is not None),
                        veraltet=vt, aktuell_nummern=nummern, profil_werte=profil_werte(g, k)))
    if fortschritt:
        fortschritt(schritte, schritte, "fertig")
    return out


def ohne_konturen(g):
    """Die Gruppe ohne Konturverschachtelung (Verläufe der Enden entfernt) oder None, wenn sie keine hat."""
    if not g.kontur_geo or not any(t.a_kontur or t.b_kontur for t in g.teile):
        return None
    from dataclasses import replace
    return replace(g, kontur_geo="", kontur_zugabe=0.0, bewiesen=False, schranke=0,
                   teile=[replace(t, a_kontur=None, b_kontur=None) for t in g.teile])


def kontur_einsparung(v):
    """Einsparung der Konturverschachtelung je Gruppe (Eintrag von vergleich): dict(stangen, mm, eur, prozent,
    stellen, ausnutzung_vorher, ausnutzung_nachher) des bisherigen Plans gegenüber „ohne Konturverschachtelung“ oder None."""
    ohne, mit = v["plaene"].get(OHNE_KONTUR), v["plaene"].get(BISHER)
    if ohne is None or mit is None:
        return None
    wo, wm = ohne.werte, mit.werte
    eur = (wo["einkauf"] - wm["einkauf"]) if wo.get("einkauf") is not None and wm.get("einkauf") is not None \
        else None
    mm = wo["gekauft_mm"] - wm["gekauft_mm"]
    return dict(stangen=wo["stangen"] - wm["stangen"], mm=mm, eur=eur, stellen=wm.get("konturen", 0),
                prozent=(mm / wo["gekauft_mm"]) if wo["gekauft_mm"] else 0.0,
                ausnutzung_vorher=wo["ausnutzung"], ausnutzung_nachher=wm["ausnutzung"])


def veraltet(ergebnis, kopf, positionen, k, tabellen, einst):
    """True, wenn der gespeicherte Schnittplan nicht mehr zu den Eingaben passt (Teile, Mengen, Preise, Maschine,
    Einstellungen geändert: rechnen.eingabe_kennung wie beim Speichern), None ohne Ergebnis oder Kennung."""
    if not ergebnis or not ergebnis.get("kennung"):
        return None
    try:
        return ergebnis["kennung"] != rechnen.eingabe_kennung(kopf, positionen, k, tabellen, einst)
    except Exception:       # noqa: BLE001 – ohne Kennung keine Aussage
        return None


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
    if schl in ("zeit", "maschine_min", "punkte"):
        return rechnen.zahl(w, 2)
    return str(w)


def hand_aus_plan(plan, positionen, fest=False):
    """Belegung von Hand zum Speichern (rechnen.hand_planen) aus den Stangen eines Plans. fest = Reihenfolge und
    Drehung je Teil bleiben genau so (Teile frei verschoben, Nesting-Arbeitsplatz 2.0); sonst ordnet die Optimierung
    die Teile einer Stange selbst an (wie bisher)."""
    out = []
    for laenge, f, rest in plan.stangen:
        teile = [[rechnen.schluessel(positionen[t.zeile - rechnen.ZEILE0], t.zeile - rechnen.ZEILE0),
                  round(t.laenge, 2)] + ([r] if fest else []) for t, r in f]
        out.append(dict(laenge=laenge, rest=rest or "", teile=teile, **({"fest": True} if fest else {})))
    return out


def neue_laenge(g, t, daten):
    """Länge einer neuen Stange für das Teil t: Stangenlänge der Gruppe, sonst die kleinste lieferbare, auf die es
    passt; None = keine."""
    laengen = sorted(x.laenge for x in daten["laengen"]) or [g.stange]
    if g.stange in laengen and ne.passt_auf(g, g.stange, [t]):
        return g.stange
    return next((x for x in laengen if ne.passt_auf(g, x, [t])), None)


def einfuegen(g, stangen, von, teil_index, nach, an, daten, uebrig=(), laenge_neu=None):
    """Teil frei verschieben (Nesting-Arbeitsplatz 2.0, Patrick 24.11.2026): Teil teil_index der Stange von (None =
    aus den nicht eingeplanten Teilen uebrig) an die Stelle an (0 = vorn) der Stange nach (None = neue Stange mit
    laenge_neu bzw. neue_laenge). Reihenfolge der übrigen Teile bleibt, die Stelle rastet am Nachbarn ein
    (gemeinsamer Schnitt bzw. Gehrung ineinander ergeben sich aus der Reihenfolge). Jede betroffene Stange wird mit
    nesting.folge_fest geprüft; eine leer gewordene Stange fällt weg.
    Ergebnis: (neue Stangen, neue übrige Teile, Fehlertext oder '')."""
    st = [(laenge, list(f), rest) for laenge, f, rest in stangen]
    rest_teile = list(uebrig)
    if von is None:
        if not (0 <= teil_index < len(rest_teile)):
            return stangen, list(uebrig), "Teil nicht gefunden"
        t, r = rest_teile.pop(teil_index), None
    else:
        if not (0 <= von < len(st)) or not (0 <= teil_index < len(st[von][1])):
            return stangen, list(uebrig), "Teil nicht gefunden"
        t, r = st[von][1][teil_index]
        st[von] = (st[von][0], [x for i, x in enumerate(st[von][1]) if i != teil_index], st[von][2])
    if nach is None:
        laenge = laenge_neu or neue_laenge(g, t, daten)
        if laenge is None:
            return stangen, list(uebrig), "Teil passt auf keine lieferbare Länge"
        st.append((laenge, [], ""))
        nach = len(st) - 1
    if not (0 <= nach < len(st)):
        return stangen, list(uebrig), "Stange nicht gefunden"
    laenge, ziel, rest = st[nach]
    an = max(0, min(len(ziel), an if an is not None else len(ziel)))
    ziel = ziel[:an] + [(t, r)] + ziel[an:]
    neu_ziel, grund = ne.folge_fest(g, laenge, [x for x, _ in ziel],
                                    [x for _, x in ziel] if all(x is not None for _, x in ziel) else None)
    if neu_ziel is None:
        frei_mm = None
        alt = [x for x, _ in st[nach][1]]
        if alt:
            f0, _ = ne.folge_fest(g, laenge, alt)
            if f0 is not None:
                frei_mm = ne.frei(g, laenge, f0)
        zusatz = (f" Frei sind {rechnen.zahl(max(frei_mm, 0), 0)} mm, das Teil braucht "
                  f"{rechnen.zahl(opt.mindestbedarf(g, t), 0)} mm (mit Schnitt).") if frei_mm is not None else ""
        return stangen, list(uebrig), f"Passt nicht auf Stange {nach + 1}: {grund}.{zusatz}"
    st[nach] = (laenge, neu_ziel, rest)
    if von is not None and von != nach and st[von][1]:
        f, grund = ne.folge_fest(g, st[von][0], [x for x, _ in st[von][1]], [x for _, x in st[von][1]])
        if f is None:
            return stangen, list(uebrig), f"Stange {von + 1} danach nicht zulässig: {grund}"
        st[von] = (st[von][0], f, st[von][2])
    neu = [s for s in st if s[1]]
    ne.pruefe(g, neu, rest_teile, None, daten["reste"])
    return neu, rest_teile, ""


def aufloesen(g, stangen, i, uebrig=()):
    """Stange i auflösen (von Hand verschachteln): ihre Teile werden nicht eingeplant (Liste links), bis sie auf
    eine Stange gezogen werden. Ergebnis (Stangen, übrige Teile)."""
    if not (0 <= i < len(stangen)):
        return stangen, list(uebrig)
    return [s for j, s in enumerate(stangen) if j != i], list(uebrig) + [t for t, _ in stangen[i][1]]


def anzeige_stangen(g, stangen, positionen, reste=(), strategie="Hand"):
    """Stangen eines Plans im Format des gespeicherten Schnittplans (rechnen._nesting_eintragen): dieselbe
    Darstellung wie im Reiter Stangenbild (Gehrungen, ineinander, gemeinsame Schnitte, Naht, Greiferrest)."""
    out, fehler, ausw = [], [], []
    rechnen._nesting_eintragen(g, ne.Plan(strategie, list(stangen), [], {}), "", positionen, fehler, out, ausw, 0,
                               reste, None, 0.0, strategie)
    return out


def export_csv(v, plan, positionen):
    """Schnittplan einer Abmessung als CSV (Semikolon, deutsch): Stange, Länge, Reststück, Platz, Pos., Artikel,
    Teillänge, von, bis, Trennung, Drehung, dann Rest und Verschnitt je Stange."""
    g, d = v["gruppe"], v["daten"]
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow(["Abmessung", "Stange", "Stangenlänge [mm]", "Reststück", "Platz", "Pos.", "Artikel", "Länge [mm]",
                "von [mm]", "bis [mm]", "Trennung", "Drehung [°]", "Rest [mm]", "verwertbar"])
    z = lambda x: rechnen.zahl(x, 1)        # noqa: E731
    for i, s in enumerate(anzeige_stangen(g, plan.stangen, positionen, d["reste"], plan.strategie), 1):
        h = opt.replace(g, stange=s["stange"], teile=[])
        folge = plan.stangen[i - 1][1]
        rest = s["stange"] - opt.verbrauch(h, folge)
        verw = "ja" if ne.verwertbar(g, rest, d["min_rest"], d["min_nutz"]) else "nein"
        for j, t in enumerate(s["teile"], 1):
            w.writerow([masstext.text(v["titel"]), i, z(s["stange"]), s.get("rest") or "", j, t.get("pos"), t.get("artikel") or "",
                        z(t["laenge"]), z(t["von"]), z(t["bis"]), t.get("trennung") or "", t.get("drehung") or 0,
                        z(rest) if j == len(s["teile"]) else "", verw if j == len(s["teile"]) else ""])
    return puffer.getvalue()


def protokoll(v):
    """Berechnungsprotokoll einer Abmessung (Zeilen): Eingaben, Verfahren je Strategie, Rechenzeit, Prüfung,
    Machbarkeit, Untergrenze."""
    g, d = v["gruppe"], v["daten"]
    z = rechnen.zahl
    zeilen = [f"Abmessung {v['titel']}: {len(g.teile)} Teile, Teilelänge {z(sum(t.laenge for t in g.teile) / 1000)} m",
              f"Fertigungswerte: Endbeschnitt {z(g.endbeschnitt, 0)} mm, Greiferrest {z(g.greiferrest, 0)} mm, "
              f"Schnittverlust {z(g.kerf, 1)} mm, Abstand getrennte Schnitte {z(g.abstand, 1)} mm"
              + (f", Teil am Stangenende {z(g.ende_bonus, 0)} mm" if g.ende_bonus else ""),
              "Lieferlängen: " + (", ".join(f"{z(x.laenge, 0)} mm ({z(x.preis) + ' €' if x.preis is not None else 'Preis fehlt'})"
                                           for x in d["laengen"]) or "keine")
              + (f"; Zuschnitt: {', '.join(z(x.laenge, 0) + ' mm' for x in d.get('zuschnitt') or ())}"
                 if d.get("zuschnitt") else ""),
              f"Reststücke im Nesting: {len(d['reste'])}" + (" (Lager und Reststücke eingeschaltet)" if d["reste"]
                                                              else " (aus oder keine passenden)"),
              f"Untergrenze Stangenzahl auf {z(g.stange, 0)} mm: {v.get('untergrenze', 0)}; bisheriger Plan "
              + ("nachweislich minimal" if v.get("bewiesen") else f"Schranke {v.get('schranke', 0)}")]
    if v.get("veraltet"):
        zeilen.append("Achtung: gespeicherter Schnittplan veraltet (Eingaben geändert), Optimieren (F9) rechnet neu.")
    for s, p in v["plaene"].items():
        w = p.werte
        b = v.get("befunde", {}).get(s, ())
        zeilen.append(f"{s}: {p.warum}. {w['stangen']} Stangen ({ne.laengen_text(w['je_laenge'])}), Ausnutzung "
                      f"{z(100 * w['ausnutzung'], 1)} %, Verschnitt {z(w['verschnitt_mm'], 0)} mm, Rechenzeit "
                      f"{z(v.get('zeiten', {}).get(s, 0.0), 2)} s; geprüft (jedes Teil einmal, keine Stange überbelegt, "
                      f"Längenbilanz); Machbarkeit: {nm.text(b)}"
                      + (f"; Enden ineinander {w['ineinander']}, davon Endkonturen {w['konturen']}"
                         if w.get("konturen") else "")
                      + (f"; Schnittfolge: {w['artikelwechsel']} Artikelwechsel, {w['schnitte']} Schnitte"
                         if w.get("schnitte") is not None else "")
                      + (f", höchstens {w['zwischenlager']} Teile warten auf einen fertigen Satz"
                         if w.get("zwischenlager") is not None else "")
                      + (f", erster Satz fertig auf Stange {w['satz_erster']}" if w.get("satz_erster") else "")
                      + (f"; Satz {w['satz_aufbau']}, {w['saetze']} Sätze" if w.get("satz_aufbau") else ""))
        if s == ne.X and p.schritte:
            zeilen.append("   Bewertung X (Punkte in €, kleiner ist besser): " + "; ".join(p.schritte))
    for z_ in v["zeilen"]:
        if z_.get("auch"):
            zeilen.append(f"Gleicher Plan: {z_['strategie']} = {', '.join(z_['auch'])} (eine Zeile im Vergleich, "
                          f"Machbarkeit einmal geprüft)")
        if z_.get("uebertroffen"):
            zeilen.append(f"{z_['strategie']} wird von {z_['uebertroffen']} in allen Kennzahlen erreicht oder "
                          f"übertroffen (grau)")
    ke = kontur_einsparung(v)
    if ke is not None:
        zeilen.append(f"Konturverschachtelung: {ke['stellen']} Stellen mit Endkonturen ineinander; gegenüber der "
                      f"Belegung ohne Konturverschachtelung {ke['stangen']} Stangen, {z(ke['mm'] / 1000)} m"
                      + (f", {z(ke['eur'])} €" if ke["eur"] is not None else "")
                      + f" weniger ({z(100 * ke['prozent'], 1)} %); Ausnutzung {z(100 * ke['ausnutzung_vorher'], 1)} %"
                      f" → {z(100 * ke['ausnutzung_nachher'], 1)} %")
    return zeilen


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
