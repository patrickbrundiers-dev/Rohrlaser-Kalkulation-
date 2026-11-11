"""Rechnung des Programms Rohrlaser Auslastung: Einlastung der offenen Aufträge (rohrlaser.einlastung), gemessene
Stunden vergangener Wochen aus den Fertigmeldungen und der Vergleich kalkuliert gegen tatsächlich. Ohne Qt."""
import datetime

from rohrlaser import einlastung, wochen

from . import daten as D

ALLE = "alle"
LAEUFT_ZUERST = 10 ** 9


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None


def grundlage(db, heute=None, wochenzahl=8):
    """Eingabe für einlastung.rechnen aus der eigenen Datenbank (gleicher Aufbau wie auslastung.berechnen):
    offene und laufende Aufträge mit ihrer Restlaufzeit (kalkuliert minus schon gelaufen), Kapazität aus Stunden je
    Tag der Maschine, Samstag, Nutzungsgrad, Feiertagen und Betriebsruhe."""
    heute = heute or datetime.date.today()
    maschinen = [m["name"] for m in db.maschinen(nur_aktive=True)]
    tag = {m["name"]: float(m["stunden_tag"]) for m in db.maschinen()}
    auftraege = {}
    jetzt = datetime.datetime.combine(heute, datetime.datetime.now().time())
    for a in db.auftraege((D.OFFEN, D.LAEUFT)):
        termin = _datum(a["liefertermin"])
        fest = _datum(a["fest_ab"])
        if a["gaenge"]:                           # mehrteilig: jeder offene Arbeitsgang wird einzeln eingelastet
            laeuft = any(g["start_am"] for g in a["gaenge"])
            for g in a["gaenge"]:
                if g["status"] == D.FERTIG:
                    continue
                fremd = g["platz"] == D.FREMD
                rest = 0 if fremd else max(0, int(g["kalk_min"]) - db.gelaufen(g, jetzt))
                auftraege.setdefault((g["platz"], ALLE), []).append(dict(
                    id=a["id"], gang=g["id"], gang_name=g["name"], nummer=f"{a['nummer']} · {g['name']}",
                    auftragsnummer=a["nummer"], kunde=a["kunde"], art=einlastung.AUFTRAG, maschine=g["platz"],
                    h=rest / 60, termin=a["liefertermin"], bis=termin, status=a["status"], kalk_min=g["kalk_min"],
                    stufe=g["stufe"], pos=g["pos"], tage=int(g["tage"] or 0), fest=fest,
                    gestartet=_datum(str(g["start_am"] or "")[:10]) if fremd else None,
                    vorrang=LAEUFT_ZUERST if laeuft else int(a["vorrang"] or 0)))
            continue
        rest = max(0, int(a["kalk_min"]) - db.gelaufen(a, jetzt))
        auftraege.setdefault((a["maschine"], ALLE), []).append(dict(
            id=a["id"], nummer=a["nummer"], kunde=a["kunde"], art=einlastung.AUFTRAG, maschine=a["maschine"],
            h=rest / 60, termin=a["liefertermin"], bis=termin, status=a["status"], kalk_min=a["kalk_min"], fest=fest,
            # Reihenfolge: was gerade läuft zuerst, dann von Hand vorgezogen, nach Termin, zurückgestellt
            vorrang=LAEUFT_ZUERST if a["start_am"] else int(a["vorrang"] or 0)))
    m0 = wochen.montag(heute)
    montage = [m0 + datetime.timedelta(weeks=i) for i in range(int(wochenzahl))]
    spalten = [(mo, f"KW {mo.isocalendar()[1]}", mo) for mo in montage] + [(wochen.SPAETER, "später", None)]
    return dict(maschinen=maschinen, auftraege=auftraege, spalten=spalten, kapazitaet={}, heute=heute,
                vorlauf=int(db.zahl("vorlauf_tage")), tag=tag, stunden=8.0, samstag=db.zahl("samstag_stunden"),
                anteil=max(0.0, min(1.0, db.zahl("nutzungsgrad", 100) / 100)), land=db.einstellung("bundesland"),
                ruhe=wochen.betriebsruhe(db.einstellung("betriebsruhe")),
                sperre={m["name"]: wochen.betriebsruhe(m["sperrtage"]) for m in db.maschinen() if m["sperrtage"]},
                uebergang={m["name"]: int(m["uebergang_tage"] or 0) for m in db.maschinen()},
                zusatz=db.zusatzstunden(m0),
                ausweich=[m["name"] for m in db.maschinen(nur_aktive=True) if m["ausweich"]])


def einlasten(db, heute=None, wochenzahl=8):
    """(Grundlage, Einlastung) der offenen Aufträge."""
    aus = grundlage(db, heute, wochenzahl)
    return aus, rechnen(aus, schwelle=int(db.zahl("schwelle_tage", 2)))


class Probe:
    """Was-wäre-wenn (E2): samstag = Stunden an jedem Samstag (None = wie eingestellt), zusatz = {(Maschine,
    Montag): Stunden zusätzlich in dieser Woche} (ersetzt die gespeicherten), maschine = {Auftrag-ID: Maschine}."""

    def __init__(self, samstag=None, zusatz=None, maschine=None):
        self.samstag, self.zusatz, self.maschine = samstag, zusatz, dict(maschine or {})


def _szenario(aus, probe=None):
    """Szenario für den Rechenkern aus gespeicherten Zusatzstunden und der Probe; None, wenn nichts abweicht."""
    s = einlastung.Szenario()
    s.zusatz = dict(aus.get("zusatz") or {}) if probe is None or probe.zusatz is None else dict(probe.zusatz)
    if probe is not None:
        s.samstag = probe.samstag
        s.maschine = {i: (m, None) for i, m in probe.maschine.items()}
    return None if s.leer() else s


def rechnen(aus, schwelle=einlastung.SCHWELLE, verkettet=None, probe=None):
    """Einlastung mit Übersicht je Auftrag. Ohne mehrteilige Aufträge und feste Plätze rechnet der Kern der
    Kalkulation (einlastung.rechnen); sobald Arbeitsgänge aufeinander warten, außer Haus laufen oder ein Auftrag
    einen festen Platz hat, rechnet planen(). probe: Was-wäre-wenn, ändert nur diese Rechnung.
    Dazu ein["plan"] = {Auftrag-ID: dict(start, fertig, lieferbar, puffer, risiko, durchlauf)}."""
    liste = [a for gruppe in aus["auftraege"].values() for a in gruppe]
    if verkettet is None:
        verkettet = any("gang" in a or a.get("fest") for a in liste)
    szenario = _szenario(aus, probe)
    ein = (planen(aus, schwelle, szenario=szenario) if verkettet
           else einlastung.rechnen(aus, szenario, schwelle=schwelle))
    plan = {}
    for a in ein["auftraege"]:
        p = plan.setdefault(a["id"], dict(start=None, fertig=a["fertig"], lieferbar=a["lieferbar"],
                                          puffer=a["puffer"], risiko=a["risiko"], offen=False))
        if a["start"] and (p["start"] is None or a["start"] < p["start"]):
            p["start"] = a["start"]
        if a["fertig"] is None:
            p["offen"] = True
        elif p["fertig"] is not None and a["fertig"] > p["fertig"]:
            p["fertig"] = a["fertig"]
    for p in plan.values():
        if p.pop("offen"):
            p["fertig"] = None
        p["durchlauf"] = (einlastung._arbeitstage(aus, D.FREMD, p["start"], p["fertig"]) + 1
                          if p["start"] and p["fertig"] else None)
    ein["plan"] = plan
    return ein


def planen(aus, schwelle=einlastung.SCHWELLE, horizont=einlastung.HORIZONT, szenario=None):
    """Einlastung mit Arbeitsgängen (Plan A2a, A3a). Gleiches Ergebnis wie einlastung.rechnen, zusätzlich gilt:

    - Die Aufträge kommen in ihrer Reihenfolge dran (läuft, von Hand vorgezogen, Liefertermin); jeder Arbeitsgang
      nimmt die frühesten freien Stunden seines Arbeitsplatzes.
    - Ein Arbeitsgang beginnt erst, wenn alle Arbeitsgänge der Stufe davor fertig sind (am selben Tag frühestens zur
      selben Tagesstunde), plus die Übergangszeit seines Arbeitsplatzes in Arbeitstagen.
    - Zeilen einer Stufe (gleichzeitig) laufen unabhängig voneinander: Teile auf mehreren Maschinen.
    - Fremdarbeit belegt keine Kapazität: sie dauert ihre Arbeitstage ab dem Ende der Stufe davor (oder ab ihrem
      Start, wenn sie schon weggegeben ist).
    - Terminrisiko, Puffer und „lieferbar“ gelten für den ganzen Auftrag: Ende des letzten Arbeitsgangs plus Vorlauf.
    - Aufträge mit festem Platz (fest = Tag, in der Plantafel verschoben) kommen zuerst dran, in der Reihenfolge ihrer
      Tage, und beginnen nicht vor ihrem Tag; alle anderen füllen die freien Stunden davor und danach."""
    heute = aus.get("heute") or datetime.date.today()
    vorlauf = int(aus.get("vorlauf") or 0)
    uebergang = aus.get("uebergang") or {}
    tage = [heute + datetime.timedelta(days=i) for i in range(horizont)]
    index = {d: i for i, d in enumerate(tage)}
    liste = einlastung.auftragsliste(aus, szenario)
    maschinen = list(aus["maschinen"])
    for a in liste:
        if a["maschine"] != D.FREMD and a["maschine"] not in maschinen:
            maschinen.append(a["maschine"])
    kap, belegt, woche, wochen_kap, spaeter, ergebnis, benutzt = {}, {}, {}, {}, {}, [], {}
    for m in maschinen:
        zusatz = einlastung._zusatz_je_tag(aus, m, szenario, tage)
        for d in tage:
            kap[(m, d)] = einlastung.tagesstunden(aus, m, d, szenario) + zusatz.get(d, 0.0)
            mo = wochen.montag(d)
            wochen_kap[(m, mo)] = wochen_kap.get((m, mo), 0.0) + kap[(m, d)]
    gruppen = {}
    for a in liste:
        gruppen.setdefault(a["id"], []).append(a)

    def rang(gruppe):
        a = gruppe[0]
        fest = a.get("fest")
        return (fest is None, fest or heute) + einlastung._reihenfolge(
            dict(a, nummer=a.get("auftragsnummer", a.get("nummer"))))

    for gruppe in sorted(gruppen.values(), key=rang):
        ab, ab_h, teile = max(heute, gruppe[0].get("fest") or heute), 0.0, []   # frühester Beginn der nächsten Stufe
        erste = min(a.get("stufe", 0) for a in gruppe)
        for stufe in sorted({a.get("stufe", 0) for a in gruppe}):
            ende, ende_h = ab, ab_h
            for a in sorted((x for x in gruppe if x.get("stufe", 0) == stufe), key=lambda x: x.get("pos", 0)):
                m, stuecke, start, fertig = a["maschine"], [], None, None
                if ab is None:                    # die Stufe davor passt nicht mehr in den Horizont
                    if m != D.FREMD:
                        spaeter[m] = spaeter.get(m, 0.0) + float(a.get("h") or 0.0)
                elif m == D.FREMD:
                    start = a.get("gestartet") or ab
                    fertig = max(heute, einlastung._spaeter(aus, D.FREMD, start, int(a.get("tage") or 0), szenario))
                    fertig_h = 0.0
                else:
                    tag, tag_h = ab, ab_h
                    if stufe != erste and uebergang.get(m):
                        tag, tag_h = einlastung._spaeter(aus, m, ab, uebergang[m], szenario), 0.0
                    rest, i = max(0.0, float(a.get("h") or 0.0)), index.get(tag, len(tage))
                    while rest > 1e-9 and i < len(tage):
                        d = tage[i]
                        von = max(benutzt.get((m, d), 0.0), tag_h if d == tag else 0.0)
                        frei = kap[(m, d)] - von
                        if frei > 1e-9:
                            nimm = min(rest, frei)
                            stuecke.append((d, von, von + nimm))
                            benutzt[(m, d)] = von + nimm
                            b = belegt.setdefault((m, d), {})
                            b[a["art"]] = b.get(a["art"], 0.0) + nimm
                            w = woche.setdefault((m, wochen.montag(d)), {})
                            w[a["art"]] = w.get(a["art"], 0.0) + nimm
                            rest -= nimm
                        if rest > 1e-9:
                            i += 1
                    if rest > 1e-9:
                        spaeter[m] = spaeter.get(m, 0.0) + rest
                    else:
                        start = stuecke[0][0] if stuecke else tag
                        fertig, fertig_h = (stuecke[-1][0], stuecke[-1][2]) if stuecke else (tag, tag_h)
                teile.append(dict(a, start=start, fertig=fertig, stuecke=stuecke))
                if fertig is None:
                    ende = None
                elif ende is not None and (fertig, fertig_h) > (ende, ende_h):
                    ende, ende_h = fertig, fertig_h
            ab, ab_h = ende, ende_h
        termin = _datum(gruppe[0].get("termin"))
        if any(t["fertig"] is None for t in teile):
            lieferbar, puffer, risiko = None, None, (einlastung.UEBER if termin else einlastung.OHNE)
        else:
            letzter = max(teile, key=lambda t: t["fertig"])
            m = letzter["maschine"]
            lieferbar = (einlastung._spaeter(aus, m, letzter["fertig"], vorlauf, szenario) if vorlauf > 0
                         else letzter["fertig"])
            if termin is None:
                puffer, risiko = None, einlastung.OHNE
            else:
                puffer = einlastung._arbeitstage(aus, m, lieferbar, termin, szenario)
                risiko = (einlastung.UEBER if lieferbar > termin else
                          einlastung.KNAPP if puffer < schwelle else einlastung.OK)
        for t in teile:
            ergebnis.append(dict(t, lieferbar=lieferbar, puffer=puffer, risiko=risiko, termin_datum=termin))
    stufen = (einlastung.OK, einlastung.KNAPP, einlastung.UEBER, einlastung.OHNE)
    je = {a["id"]: a["risiko"] for a in ergebnis if a["art"] == einlastung.AUFTRAG}
    zahl = {s: sum(1 for r in je.values() if r == s) for s in stufen}
    return dict(maschinen=maschinen, tage=tage, heute=heute, kapazitaet=kap, belegt=belegt, woche=woche,
                wochen_kap=wochen_kap, spaeter=spaeter, auftraege=ergebnis, risiko=zahl,
                szenario=szenario if szenario is not None and not szenario.leer() else None)


def vergleich(vorher, nachher):
    """Was ändert sich je Auftrag zwischen zwei Rechnungen? [dict(id, nummer, kunde, maschine, fertig_alt, fertig_neu,
    risiko_alt, risiko_neu, tage)] nur für Aufträge mit anderem Fertig-Tag oder Risiko; tage = Kalendertage früher
    (negativ) oder später (positiv), None wenn eine Seite nicht in den Horizont passt. Schlechter Gewordene zuerst."""
    name = {}
    for a in nachher["auftraege"]:
        name.setdefault(a["id"], a)
    stufe = {einlastung.OK: 0, einlastung.OHNE: 0, einlastung.KNAPP: 1, einlastung.UEBER: 2}
    out = []
    for i, n in nachher["plan"].items():
        v = vorher["plan"].get(i)
        if v is None or (v["fertig"], v["risiko"]) == (n["fertig"], n["risiko"]):
            continue
        a = name[i]
        out.append(dict(id=i, nummer=a.get("auftragsnummer", a.get("nummer")), kunde=a.get("kunde"),
                        maschine=a["maschine"], fertig_alt=v["fertig"], fertig_neu=n["fertig"],
                        risiko_alt=v["risiko"], risiko_neu=n["risiko"],
                        tage=(n["fertig"] - v["fertig"]).days if v["fertig"] and n["fertig"] else None,
                        schlechter=stufe[n["risiko"]] - stufe[v["risiko"]]))
    return sorted(out, key=lambda x: (-x["schlechter"], -(x["tage"] or 0), str(x["nummer"])))


def ausweichen(aus, ein, schwelle=einlastung.SCHWELLE):
    """Vorschlag Ausweichmaschine (E3): Für jeden einteiligen, noch nicht laufenden Auftrag mit Terminrisiko die
    Maschine, auf der er bei gleicher Laufzeit am frühesten fertig wäre, ohne dass ein anderer Auftrag dadurch ein
    schlechteres Terminrisiko bekommt. {Auftrag-ID: dict(maschine, fertig, risiko, tage)} (tage = Arbeitstage früher)."""
    kandidaten = [m for m in aus.get("ausweich") or () if m in aus["maschinen"]]
    out = {}
    for a in ein["auftraege"]:
        if (a["risiko"] not in (einlastung.KNAPP, einlastung.UEBER) or "gang" in a or a.get("fest")
                or a.get("vorrang") == LAEUFT_ZUERST or a["maschine"] not in kandidaten):
            continue
        jetzt, beste = ein["plan"][a["id"]], None
        for m in kandidaten:
            if m == a["maschine"]:
                continue
            probe = rechnen(aus, schwelle, probe=Probe(maschine={a["id"]: m}))
            neu = probe["plan"][a["id"]]
            if neu["fertig"] is None or (jetzt["fertig"] is not None and neu["fertig"] >= jetzt["fertig"]):
                continue
            if any(x["schlechter"] > 0 for x in vergleich(ein, probe) if x["id"] != a["id"]):
                continue
            if beste is None or neu["fertig"] < beste["fertig"]:
                tage = (einlastung._arbeitstage(aus, D.FREMD, neu["fertig"], jetzt["fertig"])
                        if jetzt["fertig"] else None)
                beste = dict(maschine=m, fertig=neu["fertig"], risiko=neu["risiko"], tage=tage)
        if beste:
            out[a["id"]] = beste
    return out


def kritische(ein):
    """Aufträge mit Terminrisiko knapp oder überschritten, dringendste zuerst; ein mehrteiliger Auftrag steht einmal
    da (mit dem Arbeitsgang, der zuletzt fertig wird)."""
    je = {}
    for a in einlastung.kritische(ein):
        alt = je.get(a["id"])
        if alt is None or (a.get("fertig") or datetime.date.max) > (alt.get("fertig") or datetime.date.max):
            je[a["id"]] = a
    return sorted(je.values(), key=lambda a: (a["risiko"] != einlastung.UEBER,
                                              a["puffer"] if a["puffer"] is not None else -999,
                                              str(a.get("termin") or "")))


def auskunft(db, minuten, heute=None):
    """Terminauskunft (P6): Wann wäre ein neuer Auftrag mit dieser Laufzeit fertig, wenn er auf der Maschine hinter
    allen offenen Aufträgen läuft? Nichts wird gespeichert. Ergebnis je aktive Maschine, früheste zuerst:
    [dict(maschine, start, fertig, lieferbar)] (fertig None = passt nicht in die nächsten 400 Tage)."""
    aus = grundlage(db, heute)
    for n, m in enumerate(aus["maschinen"], start=1):   # je Maschine ein eigener Probeauftrag (eigene id)
        aus["auftraege"].setdefault((m, ALLE), []).append(dict(
            id=-n, nummer="", kunde="", art=einlastung.AUFTRAG, maschine=m, h=max(0, int(minuten or 0)) / 60,
            termin=None, bis=None, vorrang=-LAEUFT_ZUERST))
    ein = rechnen(aus)
    liste = [dict(maschine=a["maschine"], start=a["start"], fertig=a["fertig"], lieferbar=a["lieferbar"])
             for a in ein["auftraege"] if a["id"] < 0]
    return sorted(liste, key=lambda x: (x["fertig"] is None, x["fertig"] or datetime.date.max,
                                        aus["maschinen"].index(x["maschine"])))


def arbeitsliste(ein, maschine):
    """Aufträge einer Maschine in der geplanten Reihenfolge (P7)."""
    liste = [a for a in ein["auftraege"] if a["maschine"] == maschine]
    return sorted(liste, key=lambda a: (a["start"] is None, a["start"] or datetime.date.max,
                                        a["stuecke"][0][1] if a["stuecke"] else 0.0, str(a["nummer"])))


def gemessen(db, aus, heute=None, wochenzahl=4):
    """Tatsächliche Stunden vergangener Wochen je Maschine aus den Fertigmeldungen (Woche des Fertig-Datums); gleicher
    Aufbau wie einlastung.gemessen."""
    heute = heute or datetime.date.today()
    m0 = wochen.montag(heute)
    montage = [m0 - datetime.timedelta(weeks=i) for i in range(max(0, int(wochenzahl)), 0, -1)]
    stunden, laeufe = {}, 0
    for a in _meldungen(db):
        tag = _datum(a["fertig_am"])
        if tag is None or wochen.montag(tag) not in montage:
            continue
        key = (a["maschine"], wochen.montag(tag))
        stunden[key] = stunden.get(key, 0.0) + (a["ist_min"] or 0) / 60
        laeufe += 1
    kap = {(m, mo): sum(einlastung.tagesstunden(aus, m, mo + datetime.timedelta(days=i)) for i in range(6))
           for m in aus["maschinen"] for mo in montage}
    return dict(montage=montage, stunden=stunden, kapazitaet=kap, laeufe=laeufe)


def _meldungen(db, nur_fertige_auftraege=False):
    """Fertigmeldungen je Arbeitsplatz: ein einteiliger Auftrag ist eine Meldung, ein mehrteiliger eine je fertigem
    Arbeitsgang mit Arbeitsplatz (Fremdarbeit zählt nicht): [dict(maschine, kalk_min, ist_min, fertig_am, auftrag)]."""
    out = []
    for a in db.auftraege(D.FERTIG if nur_fertige_auftraege else None):
        if not a["gaenge"]:
            if a["status"] == D.FERTIG:
                out.append(dict(maschine=a["maschine"], kalk_min=a["kalk_min"], ist_min=a["ist_min"],
                                fertig_am=a["fertig_am"], auftrag=a))
            continue
        for g in a["gaenge"]:
            if g["status"] == D.FERTIG and g["platz"] != D.FREMD:
                out.append(dict(maschine=g["platz"], kalk_min=g["kalk_min"], ist_min=g["ist_min"],
                                fertig_am=g["fertig_am"], auftrag=a))
    return out


def abweichung(kalk_min, ist_min):
    """Abweichung tatsächlich gegen kalkuliert: (Minuten, Prozent oder None)."""
    if ist_min is None or kalk_min is None:
        return None, None
    diff = int(ist_min) - int(kalk_min)
    return diff, (diff / kalk_min * 100 if kalk_min else None)


def soll_ist(db, von=None, bis=None):
    """Fertige Aufträge im Zeitraum (nach Fertig-Datum): dict(zeilen=[Auftrag + diff_min, diff_prozent],
    maschinen=[dict(maschine, anzahl, kalk_min, ist_min, diff_min, diff_prozent)], gesamt=dict(...))."""
    zeilen, je = [], {}
    for a in db.auftraege(D.FERTIG):
        tag = _datum(a["fertig_am"])
        if (von and (tag is None or tag < von)) or (bis and (tag is None or tag > bis)):
            continue
        diff, prozent = abweichung(a["kalk_min"], a["ist_min"])
        zeilen.append(dict(a, diff_min=diff, diff_prozent=prozent))
        teile = ([dict(maschine=g["platz"], kalk_min=g["kalk_min"], ist_min=g["ist_min"]) for g in a["gaenge"]
                  if g["platz"] != D.FREMD] if a["gaenge"] else [a])
        for t in teile:                           # je Maschine zählt jeder Arbeitsgang an seinem Arbeitsplatz
            s = je.setdefault(t["maschine"], dict(maschine=t["maschine"], anzahl=0, kalk_min=0, ist_min=0))
            s["anzahl"] += 1
            s["kalk_min"] += t["kalk_min"] or 0
            s["ist_min"] += t["ist_min"] or 0
    zeilen.sort(key=lambda a: (a["fertig_am"] or "", a["nummer"]), reverse=True)
    summen = sorted(je.values(), key=lambda s: s["maschine"])
    gesamt = dict(maschine="Gesamt", anzahl=len(zeilen),
                  kalk_min=sum(s["kalk_min"] for s in summen), ist_min=sum(s["ist_min"] for s in summen))
    for s in summen + [gesamt]:
        s["diff_min"], s["diff_prozent"] = abweichung(s["kalk_min"], s["ist_min"]) if s["anzahl"] else (0, None)
    return dict(zeilen=zeilen, maschinen=summen, gesamt=gesamt)
