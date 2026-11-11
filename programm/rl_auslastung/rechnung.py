"""Rechnung des Programms Rohrlaser Auslastung: Einlastung der offenen Aufträge (rohrlaser.einlastung), gemessene
Stunden vergangener Wochen aus den Fertigmeldungen und der Vergleich kalkuliert gegen tatsächlich. Ohne Qt."""
import datetime

from rohrlaser import einlastung, feiertage, wochen

from . import daten as D

ALLE = "alle"
LAEUFT_ZUERST = 10 ** 9


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None


UHRZEIT = None      # nur für Tests: feste Uhrzeit statt der Rechneruhr, damit laufende Aufträge immer gleich rechnen


def grundlage(db, heute=None, wochenzahl=8):
    """Eingabe für einlastung.rechnen aus der eigenen Datenbank (gleicher Aufbau wie auslastung.berechnen):
    offene und laufende Aufträge mit ihrer Restlaufzeit (kalkuliert minus schon gelaufen), Kapazität aus Stunden je
    Tag der Maschine, Samstag, Nutzungsgrad, Feiertagen und Betriebsruhe."""
    heute = heute or datetime.date.today()
    maschinen = [m["name"] for m in db.maschinen(nur_aktive=True)]
    tag = {m["name"]: float(m["stunden_tag"]) for m in db.maschinen()}
    auftraege = {}
    jetzt = datetime.datetime.combine(heute, UHRZEIT or datetime.datetime.now().time())
    faktor = {m: f for m, (f, _n) in erfahrung(db, heute).items()}   # N3: nur Maschinen mit Schalter
    mat = db.funktion("material")                 # M1 (Plan 2.3): aus = ohne Material, Rüstzeit und Rohrmaße
    teil_an = db.funktion("teillieferungen")
    prio, prio_tage = db.prioritaeten(), int(db.zahl("prio_tage", 3))
    rest_prozent, rest_min = max(0.0, db.zahl("rest_prozent", 15)), max(0.0, db.zahl("rest_min", 30))
    for a in db.auftraege((D.OFFEN, D.LAEUFT)):
        termin = _datum(a["liefertermin"])
        stufe = prio.get(str(a["kunde"] or "").strip().casefold(), "B")
        bis = _prio_bis(termin, stufe, prio_tage)  # V10: Reihenfolge, der Termin selbst bleibt
        fest = _datum(a["fest_ab"])
        ab = db.wartet_auf_material(a, heute)     # E8: vor diesem Tag wird nicht eingelastet
        if a["gaenge"]:                           # mehrteilig: jeder offene Arbeitsgang wird einzeln eingelastet
            laeuft = any(g["start_am"] for g in a["gaenge"])
            for g in a["gaenge"]:
                if g["status"] == D.FERTIG:
                    continue
                fremd = g["platz"] == D.FREMD
                lief = 0 if fremd else db.gelaufen(g, jetzt)
                kalk_g = round(int(g["kalk_min"]) * faktor.get(g["platz"], 1.0))
                rest = 0 if fremd else _rest(kalk_g, lief, rest_prozent, rest_min)
                auftraege.setdefault((g["platz"], ALLE), []).append(dict(
                    material=(a.get("material") or "") if mat else "", begonnen=bool(lief or g["start_am"]),
                    durchmesser=(a.get("durchmesser") or 0) if mat else 0, laenge=(a.get("laenge") or 0) if mat else 0,
                    id=a["id"], gang=g["id"], gang_name=g["name"], nummer=f"{a['nummer']} · {g['name']}",
                    auftragsnummer=a["nummer"], kunde=a["kunde"], art=einlastung.AUFTRAG, maschine=g["platz"],
                    h=rest / 60, termin=a["liefertermin"], bis=bis, status=a["status"], kalk_min=g["kalk_min"],
                    stufe=g["stufe"], pos=g["pos"], tage=int(g["tage"] or 0), fest=fest, ab=ab,
                    gestartet=_datum(str(g["start_am"] or "")[:10]) if fremd else None,
                    vorrang=LAEUFT_ZUERST if laeuft else int(a["vorrang"] or 0)))
            continue
        lief = db.gelaufen(a, jetzt)
        kalk = round(int(a["kalk_min"]) * faktor.get(a["maschine"], 1.0))
        rest = _rest(kalk, lief, rest_prozent, rest_min)
        eintrag = dict(
            id=a["id"], nummer=a["nummer"], kunde=a["kunde"], art=einlastung.AUFTRAG, maschine=a["maschine"],
            h=rest / 60, termin=a["liefertermin"], bis=bis, status=a["status"], kalk_min=a["kalk_min"], fest=fest,
            ab=ab, material=(a.get("material") or "") if mat else "", ruest_fest=a.get("ruest_min") if mat else None,
            begonnen=bool(lief or a["start_am"]),
            durchmesser=(a.get("durchmesser") or 0) if mat else 0, laenge=(a.get("laenge") or 0) if mat else 0,
            # Reihenfolge: was gerade läuft zuerst, dann von Hand vorgezogen, nach Termin, zurückgestellt
            vorrang=LAEUFT_ZUERST if a["start_am"] else int(a["vorrang"] or 0))
        ziel = auftraege.setdefault((a["maschine"], ALLE), [])
        teile = _teillieferungen(dict(a, kalk_min=kalk), lief) if teil_an else []
        if not teile:
            ziel.append(eintrag)
        for n, t in enumerate(teile):             # A5: jede offene Teillieferung mit eigenem Termin
            ziel.append(dict(
                eintrag, teil=t["teil"], teil_von=t["von"], menge=t["menge"], auftragsnummer=a["nummer"],
                nummer=f"{a['nummer']} · Lieferung {t['teil']}/{t['von']}", h=t["rest_min"] / 60,
                kalk_min=t["kalk_min"], termin=t["termin"], bis=_prio_bis(_datum(t["termin"]), stufe, prio_tage),
                fest=fest if n == 0 else None, begonnen=eintrag["begonnen"] and n == 0,
                vorrang=eintrag["vorrang"] if n == 0 or eintrag["vorrang"] != LAEUFT_ZUERST
                else int(a["vorrang"] or 0)))
    m0 = wochen.montag(heute)
    montage = [m0 + datetime.timedelta(weeks=i) for i in range(int(wochenzahl))]
    spalten = [(mo, f"KW {mo.isocalendar()[1]}", mo) for mo in montage] + [(wochen.SPAETER, "später", None)]
    aus = dict(maschinen=maschinen, auftraege=auftraege, spalten=spalten, kapazitaet={}, heute=heute,
                vorlauf=int(db.zahl("vorlauf_tage")), tag=tag, stunden=8.0, samstag=db.zahl("samstag_stunden"),
                anteil=max(0.0, min(1.0, db.zahl("nutzungsgrad", 100) / 100)), land=db.einstellung("bundesland"),
                ruhe=wochen.betriebsruhe(db.einstellung("betriebsruhe")),
                sperre={m["name"]: wochen.betriebsruhe(m["sperrtage"]) for m in db.maschinen() if m["sperrtage"]},
                uebergang={m["name"]: int(m["uebergang_tage"] or 0) for m in db.maschinen()},
                zusatz=db.zusatzstunden(m0),
                ausweich=[m["name"] for m in db.maschinen(nur_aktive=True) if m["ausweich"]],
                ruest={m["name"]: int(m.get("ruest_min") or 0) for m in db.maschinen()} if mat else {},
                eignung={m["name"]: m for m in db.maschinen()} if mat else {})
    aus["einfrieren"] = max(0, int(db.zahl("einfrieren_tage", 2)))   # N3: so viele Arbeitstage nicht umplanen
    aus["fremd_tage"] = db.fremd_tage()  # Plan 2.6: Fremdarbeit nur an diesen Wochentagen abholen und anliefern
    aus["kalender"] = Kalender(db)        # Schichten je Tag: Wochenwechsel, Samstag, Ausnahmen (tagesstunden)
    return aus


def _rest(kalk, lief, prozent, minimum):
    """N1: Restlaufzeit in Minuten. Ist die kalkulierte Zeit fast oder ganz verbraucht, bleibt bis zur Fertigmeldung
    eine Mindest-Restzeit stehen (prozent der Kalkulation, wenigstens minimum Minuten, nie mehr als die Kalkulation),
    sonst gälte die Maschine im Plan als frei, obwohl der Auftrag noch läuft."""
    rest = max(0, kalk - lief)
    if lief <= 0 or kalk <= 0:
        return rest
    return max(rest, min(kalk, max(kalk * prozent / 100, minimum)))


def _prio_bis(termin, stufe, tage):
    """V10: Datum für die Reihenfolge. A-Kunden rücken um tage Kalendertage vor, C-Kunden nach hinten."""
    if termin is None or stufe not in ("A", "C") or tage <= 0:
        return termin
    return termin + datetime.timedelta(days=-tage if stufe == "A" else tage)


def verschoben(aus, m, tag, n):
    """V4: tag um n Arbeitstage der Maschine verschoben (n < 0: zurück, höchstens ein Jahr gesucht)."""
    if n >= 0:
        return einlastung._spaeter(aus, m, tag, n)
    d, grenze = tag, tag - datetime.timedelta(days=366)
    while n < 0 and d > grenze:
        d -= datetime.timedelta(days=1)
        if einlastung.tagesstunden(aus, m, d) > 0:
            n += 1
    return d


def _teillieferungen(a, gelaufen=0):
    """A5: offene Teillieferungen eines einteiligen Auftrags. Die kalkulierte Laufzeit teilt sich nach den Mengen;
    was schon gelaufen ist, zählt für die frühesten Lieferungen. [dict(teil (ab 1), von, termin, menge, kalk_min,
    rest_min)] ohne die schon abgearbeiteten; die letzte bleibt immer stehen. [] ohne Teillieferungen."""
    lief = a.get("lieferungen") or []
    gesamt = sum(float(x["menge"] or 0) for x in lief)
    if len(lief) < 2 or gesamt <= 0 or a.get("gaenge"):
        return []
    out, verbraucht, summe = [], float(gelaufen or 0), 0.0
    for n, x in enumerate(lief, start=1):
        kalk = float(a["kalk_min"] or 0) * float(x["menge"] or 0) / gesamt
        if n == len(lief):
            kalk = float(a["kalk_min"] or 0) - summe          # Rundung: die Summe bleibt die Laufzeit des Auftrags
        summe += kalk
        nimm = min(kalk, verbraucht)
        verbraucht -= nimm
        if kalk - nimm > 1e-6 or n == len(lief):
            out.append(dict(teil=n, von=len(lief), termin=x["termin"], menge=x["menge"], kalk_min=int(kalk + 0.5),
                            rest_min=max(0.0, kalk - nimm)))
    return out


def passt(aus, a, m):
    """A3: Kann die Maschine m das Rohr des Auftrags (Durchmesser, Rohrlänge)? Ohne Angaben: ja."""
    return not D.passt_nicht((aus.get("eignung") or {}).get(m), a.get("durchmesser"), a.get("laenge"))


def ruestzeit(aus, a, m):
    """A1: Rüstzeit des Eintrags auf der Maschine m in Stunden, ohne die Ersparnis bei gleichem Material: die Zeit
    des Auftrags, sonst die der Maschine. Was schon läuft oder gelaufen ist, ist gerüstet; Fremdarbeit rüstet nicht."""
    if m == D.FREMD or a.get("begonnen") or a.get("art") != einlastung.AUFTRAG or a["id"] < 0:
        return 0.0
    fest = a.get("ruest_fest")
    return max(0, int((aus.get("ruest") or {}).get(m, 0) if fest is None else fest)) / 60


class Kalender:
    """Schichtkalender: Arbeitszeit je Maschine und Tag aus Schichten (Montag bis Freitag, auch im Wochenwechsel),
    Schichten am Samstag und Ausnahmen. Der Rechenkern der Kalkulation kennt je Maschine nur eine Stundenzahl;
    steht ein Kalender in der Grundlage (aus["kalender"]), fragt tagesstunden() stattdessen ihn."""

    def __init__(self, db):
        self.schicht = {x["name"]: x for x in db.schichten()}
        erste = next(iter(self.schicht.values()), None)
        self.beginn = D.uhrzeit(erste["beginn"]) if erste else 360
        self.samstag = float(db.zahl("samstag_stunden"))
        self.maschine = {m["name"]: dict(folge=D.schichtfolge(m), start=D._tag_iso(m.get("schicht_start")),
                                         sa=[n for n in (m.get("schichten_sa") or "").split(",") if n],
                                         stunden=float(m["stunden_tag"])) for m in db.maschinen()}
        self.ausnahmen = db.ausnahmen()

    def ausnahme(self, m, tag):
        """Die Ausnahme, die an diesem Tag für die Maschine gilt, oder None. Eine Ausnahme für die Maschine geht
        vor einer für alle, ein einzelner Tag vor einem Zeitraum, sonst die zuletzt angelegte. Ein Zeitraum gilt nur
        von Montag bis Freitag, ein einzelner Tag auch am Samstag; am Sonntag gilt nichts."""
        if tag.weekday() == 6:
            return None
        beste, rang = None, None
        for a in self.ausnahmen:
            if a["maschine"] not in ("", m) or not a["von"] <= tag <= a["bis"]:
                continue
            einzel = a["von"] == a["bis"]
            if not einzel and tag.weekday() == 5:
                continue
            r = (a["maschine"] != "", einzel, a["id"])
            if rang is None or r > rang:
                beste, rang = dict(a, einzel=einzel), r
        return beste

    def namen(self, m, tag):
        """Schichten der Maschine an diesem Tag; None = keine Schichten, es gilt die Stundenzahl von Hand."""
        a = self.ausnahme(m, tag)
        if a is not None:
            return a["namen"]
        info = self.maschine.get(m)
        if info is None:
            return None
        if tag.weekday() == 5:
            return info["sa"] or None
        folge = info["folge"]
        if not folge:
            return None
        montag = wochen.montag(tag)
        return folge[(((montag - (info["start"] or montag)).days // 7) % len(folge))]

    def stunden(self, m, tag):
        """Arbeitsstunden ohne Pause (vor Nutzungsgrad, Feiertagen und Sperrtagen)."""
        namen = self.namen(m, tag)
        if namen is None:
            if tag.weekday() == 5:
                return self.samstag
            return self.maschine[m]["stunden"] if m in self.maschine else 8.0
        return min(24.0, sum(self.schicht[n]["stunden"] for n in namen if n in self.schicht))

    def teile(self, m, tag):
        """Arbeitszeit des Tages als Uhrzeiten für die Tagesansicht: [(Beginn in Minuten seit Mitternacht, Dauer
        in Stunden, Name der Schicht oder '')]; ohne Schichten ein Block ab dem Beginn der ersten Schicht."""
        namen = self.namen(m, tag)
        if namen is None:
            h = self.stunden(m, tag)
            return [(self.beginn, h, "")] if h > 0 else []
        return [(D.uhrzeit(x["beginn"]), x["dauer"], x["name"]) for x in self.schicht.values() if x["name"] in namen]


_tagesstunden_kern = einlastung.tagesstunden


def tagesstunden(aus, m, d, szenario=None):
    """Wie einlastung.tagesstunden, mit Schichtkalender: Ohne aus["kalender"] (die Kalkulation setzt ihn nie)
    rechnet der Kern unverändert."""
    kal = aus.get("kalender")
    if kal is None:
        return _tagesstunden_kern(aus, m, d, szenario)
    if d.weekday() == 6 or d in (aus.get("ruhe") or ()) or d in ((aus.get("sperre") or {}).get(m) or ()):
        return 0.0
    a = kal.ausnahme(m, d)
    if feiertage.name(d, aus.get("land")) and not (a is not None and a["einzel"]):
        return 0.0
    if a is None and d.weekday() == 5 and szenario is not None and szenario.samstag is not None:
        return szenario.samstag * aus.get("anteil", 1.0)                    # Was-wäre-wenn: Samstag für alle
    return kal.stunden(m, d) * aus.get("anteil", 1.0)


einlastung.tagesstunden = tagesstunden     # der Kern ruft seine eigene Funktion über diesen Namen


def spannen(db):
    """Schichtkalender für die Tagesansicht (Kalender.teile)."""
    return Kalender(db)


def tag_ist(db, tag, jetzt=None):
    """Tatsächliches an einem Tag (V3) je Maschine: was gerade läuft und was an diesem Tag fertig gemeldet wurde.
    [dict(maschine, nummer, kunde, art 'laeuft'|'fertig', start, ende (datetime oder None, aus Start-Knopf und
    Verlauf), ist_min, kalk_min, abweichung = ist_min - kalk_min (bei 'laeuft' nur, wenn überzogen))]."""
    def zeit(text):
        try:
            return datetime.datetime.fromisoformat(str(text))
        except (TypeError, ValueError):
            return None

    jetzt = jetzt or datetime.datetime.now()
    iso = tag.isoformat()
    ids = {z[0] for z in db.con.execute(
        "SELECT id FROM auftraege WHERE geloescht_am IS NULL AND (start_am IS NOT NULL OR fertig_am = ?) UNION "
        "SELECT auftrag_id FROM gaenge WHERE start_am IS NOT NULL OR fertig_am = ?", (iso, iso))}
    out = []
    for i in sorted(ids):
        a = db.auftrag(i)
        if a is None:
            continue
        verlauf = list(reversed(db.verlauf(i)))               # älteste zuerst
        for g in (a["gaenge"] or [None]):
            teil = g if g is not None else a
            if g is not None and g["platz"] == D.FREMD:
                continue
            vor = f"{g['name']}: " if g is not None else ""
            name = a["nummer"] + (f" · {g['name']}" if g is not None else "")
            maschine = g["platz"] if g is not None else a["maschine"]
            kalk = int(teil["kalk_min"] or 0)
            if teil["status"] != D.FERTIG and teil["start_am"]:
                start = zeit(teil["start_am"])
                ist = db.gelaufen(teil, jetzt)
                out.append(dict(maschine=maschine, nummer=name, kunde=a["kunde"], art="laeuft", start=start, ende=None,
                                ist_min=ist, kalk_min=kalk, abweichung=ist - kalk if kalk and ist > kalk else 0))
            elif teil["status"] == D.FERTIG and str(teil["fertig_am"] or "")[:10] == iso:
                start = next((zeit(v["wann"]) for v in verlauf if v["was"] == vor + "gestartet"), None)
                ende = next((zeit(v["wann"]) for v in reversed(verlauf)
                             if v["was"].startswith(vor + "fertig gemeldet")), None)
                if teil.get("fertig_um"):             # eingegebene Uhrzeit der Fertigmeldung geht vor
                    ende = datetime.datetime.combine(tag, datetime.time(*divmod(D.uhrzeit(teil["fertig_um"]), 60)))
                ist = int(teil["ist_min"] or 0)
                out.append(dict(maschine=maschine, nummer=name, kunde=a["kunde"], art="fertig", start=start,
                                ende=ende if ende and ende.date() == tag else None, ist_min=ist, kalk_min=kalk,
                                abweichung=ist - kalk))
    out.sort(key=lambda x: (x["maschine"], x["art"] != "fertig", x["ende"] or x["start"] or jetzt))
    return out


def tag_ist_text(liste):
    """tag_ist() als Text je Maschine: {Maschine: ['A-1 läuft seit 07:12, 2 h 10 min von 3 h', …]}."""
    def hm(minuten):
        return f"{minuten // 60} h {minuten % 60:02d} min" if minuten >= 60 else f"{minuten} min"

    out = {}
    for x in liste:
        if x["art"] == "laeuft":
            t = f"{x['nummer']} läuft" + (f" seit {x['start']:%H:%M}" if x["start"] else "") + \
                f", {hm(x['ist_min'])} von {hm(x['kalk_min'])}"
            if x["abweichung"] > 0:
                t += f", überzieht um {hm(x['abweichung'])}"
        else:
            von = f"{x['start']:%H:%M} bis " if x["start"] and x["ende"] and x["start"].date() == x["ende"].date() \
                else ""
            t = f"{x['nummer']} fertig" + (f" {von}{x['ende']:%H:%M}" if x["ende"] else "") + \
                f", {hm(x['ist_min'])} statt {hm(x['kalk_min'])}"
            if x["abweichung"]:
                t += f" ({'+' if x['abweichung'] > 0 else '−'}{hm(abs(x['abweichung']))})"
        out.setdefault(x["maschine"], []).append(t)
    return out


def uhr_am(teile, anteil):
    """Uhrzeit (Minuten seit Mitternacht, über 1440 = nach Mitternacht) an der Stelle anteil (0 bis 1) der
    Arbeitszeit eines Tages; teile wie aus spannen(). None ohne Arbeitszeit."""
    gesamt = sum(d for _b, d, _n in teile)
    if gesamt <= 0:
        return None
    rest = max(0.0, min(1.0, anteil)) * gesamt
    tag = 0
    for i, (b, d, _n) in enumerate(teile):
        if i and b < teile[i - 1][0]:
            tag += 1440                           # Schicht beginnt nach Mitternacht des Folgetags
        if rest <= d + 1e-9 or i == len(teile) - 1:
            return tag + b + min(rest, d) * 60
        rest -= d
    return None


def fremd_tag(aus, tag, danach, szenario=None):
    """Plan 2.6: Abholung und Anlieferung der Fremdarbeit nur an den Wochentagen aus aus['fremd_tage'] (leer = jeder
    Tag). Ergebnis: der erste solche Arbeitstag ab tag (danach=True: frühestens am Tag nach tag, weil der Arbeitsgang
    davor erst im Laufe des Tages fertig wird)."""
    erlaubt = aus.get("fremd_tage") or set()
    if not erlaubt or tag is None:
        return tag
    d = tag + datetime.timedelta(days=1) if danach else tag
    for _i in range(21):
        if d.weekday() in erlaubt and einlastung.tagesstunden(aus, D.FREMD, d, szenario) > 0:
            return d
        d += datetime.timedelta(days=1)
    return d


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
        verkettet = (any("gang" in a or a.get("fest") or a.get("ab") or "teil" in a or a.get("ruest_fest")
                         for a in liste) or any((aus.get("ruest") or {}).values()))
    szenario = _szenario(aus, probe)
    ein = (planen(aus, schwelle, szenario=szenario) if verkettet
           else einlastung.rechnen(aus, szenario, schwelle=schwelle))
    plan = {}
    stufe = {einlastung.OHNE: 0, einlastung.OK: 1, einlastung.KNAPP: 2, einlastung.UEBER: 3}
    for a in ein["auftraege"]:
        p = plan.setdefault(a["id"], dict(start=None, fertig=a["fertig"], lieferbar=a["lieferbar"],
                                          puffer=a["puffer"], risiko=a["risiko"], offen=False))
        p["ruest_h"] = p.get("ruest_h", 0.0) + (a.get("ruest_h") or 0.0)
        if "teil" in a:                   # A5: der Auftrag ist so gut wie seine schlechteste Teillieferung
            p.setdefault("teile", []).append(dict(
                teil=a["teil"], von=a["teil_von"], termin=a.get("termin_datum"), menge=a.get("menge"),
                fertig=a["fertig"], lieferbar=a["lieferbar"], puffer=a["puffer"], risiko=a["risiko"]))
            if stufe[a["risiko"]] > stufe[p["risiko"]]:
                p["risiko"] = a["risiko"]
            if a["puffer"] is not None and (p["puffer"] is None or a["puffer"] < p["puffer"]):
                p["puffer"] = a["puffer"]
            if a["lieferbar"] is None:
                p["lieferbar"] = None
            elif p["lieferbar"] is not None and a["lieferbar"] > p["lieferbar"]:
                p["lieferbar"] = a["lieferbar"]
        if a["start"] and (p["start"] is None or a["start"] < p["start"]):
            p["start"], p["m_start"] = a["start"], a["maschine"]
        if a["fertig"] is None:
            p["offen"] = True
        elif p["fertig"] is not None and a["fertig"] > p["fertig"]:
            p["fertig"] = a["fertig"]
    for p in plan.values():
        if p.pop("offen"):
            p["fertig"] = None
        if "teile" in p:
            p["teile"].sort(key=lambda t: t["teil"])
        p["durchlauf"] = (einlastung._arbeitstage(aus, D.FREMD, p["start"], p["fertig"]) + 1
                          if p["start"] and p["fertig"] else None)
        # V4: spätester Start = geplanter Start + Puffer (Arbeitstage), wenn alles andere bleibt; negativ = hätte
        # schon früher anfangen müssen
        m0 = p.pop("m_start", None)
        p["spaetester_start"] = (verschoben(aus, m0 or D.FREMD, p["start"], int(p["puffer"]))
                                 if p["start"] and p["puffer"] is not None else None)
    ein["plan"] = plan
    ein["ruest_h"] = sum(a.get("ruest_h") or 0.0 for a in ein["auftraege"])
    ein["ruest_gespart_h"] = sum(a.get("ruest_gespart_h") or 0.0 for a in ein["auftraege"])
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
      Tage, und beginnen nicht vor ihrem Tag; alle anderen füllen die freien Stunden davor und danach.
    - Wartet ein Auftrag auf Material (ab = Tag), beginnt er nicht vor diesem Tag; seine Reihenfolge bleibt.
    - Rüsten (A1): vor jedem Auftrag, der noch nicht läuft, steht die Rüstzeit (ruestzeit()). Sie entfällt, wenn
      direkt davor auf der Maschine das gleiche Material lief oder eine Lieferung desselben Auftrags. Im Ergebnis
      enthält h die Rüstzeit; ruest_h = gerüstet, ruest_gespart_h = gespart.
    - Teillieferungen (A5, Einträge mit teil): jede Lieferung reiht sich mit ihrem eigenen Termin ein."""
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
        gruppen.setdefault((a["id"], a.get("teil")), []).append(a)
    gelegt = {}                 # {Maschine: [((Tag, Stunde) Ende, Material, Auftrag-ID)]} für das Rüsten

    def davor(m, d, h):
        """Was lief auf der Maschine zuletzt vor (d, h)? (Material, Auftrag-ID) oder None."""
        beste = None
        for ende, material, i in gelegt.get(m, ()):
            if ende <= (d, h + 1e-9) and (beste is None or ende > beste[0]):
                beste = (ende, material, i)
        return beste and beste[1:]

    def rang(gruppe):
        a = gruppe[0]
        fest = a.get("fest")
        return (fest is None, fest or heute) + einlastung._reihenfolge(
            dict(a, nummer=a.get("auftragsnummer", a.get("nummer"))))

    for gruppe in sorted(gruppen.values(), key=rang):
        # frühester Beginn der nächsten Stufe
        ab, ab_h, teile = max(heute, gruppe[0].get("fest") or heute, gruppe[0].get("ab") or heute), 0.0, []
        erste = min(a.get("stufe", 0) for a in gruppe)
        for stufe in sorted({a.get("stufe", 0) for a in gruppe}):
            ende, ende_h = ab, ab_h
            for a in sorted((x for x in gruppe if x.get("stufe", 0) == stufe), key=lambda x: x.get("pos", 0)):
                m, stuecke, start, fertig = a["maschine"], [], None, None
                if ab is None:                    # die Stufe davor passt nicht mehr in den Horizont
                    if m != D.FREMD:
                        spaeter[m] = spaeter.get(m, 0.0) + float(a.get("h") or 0.0)
                elif m == D.FREMD:
                    start = a.get("gestartet") or fremd_tag(aus, ab, stufe != erste or ab_h > 0, szenario)
                    fertig = max(heute, einlastung._spaeter(aus, D.FREMD, start, int(a.get("tage") or 0), szenario))
                    fertig = fremd_tag(aus, fertig, False, szenario)
                    fertig_h = 0.0
                else:
                    tag, tag_h = ab, ab_h
                    if stufe != erste and uebergang.get(m):
                        tag, tag_h = einlastung._spaeter(aus, m, ab, uebergang[m], szenario), 0.0
                    rest, i = max(0.0, float(a.get("h") or 0.0)), index.get(tag, len(tage))
                    ruest = ruestzeit(aus, a, m)
                    if ruest > 0 and rest > 1e-9:
                        j = i                         # erster freier Platz: was lief direkt davor?
                        while j < len(tage) and kap[(m, tage[j])] - max(
                                benutzt.get((m, tage[j]), 0.0), tag_h if tage[j] == tag else 0.0) <= 1e-9:
                            j += 1
                        vor = davor(m, tage[j], max(benutzt.get((m, tage[j]), 0.0),
                                                    tag_h if tage[j] == tag else 0.0)) if j < len(tage) else None
                        gleich = vor is not None and (vor[1] == a["id"] or (
                            a.get("material") and vor[0].casefold() == a["material"].casefold()))
                        a = dict(a, ruest_h=0.0 if gleich else ruest, ruest_gespart_h=ruest if gleich else 0.0,
                                 h=rest + (0.0 if gleich else ruest))
                        rest = a["h"]
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
                        if stuecke:
                            gelegt.setdefault(m, []).append(((fertig, fertig_h), a.get("material") or "", a["id"]))
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


def eingefroren(aus, ein):
    """N3: Aufträge, die in den nächsten aus['einfrieren'] Arbeitstagen (ab heute) beginnen. Optimieren und
    Ausweichmaschine schlagen für sie nichts vor und nehmen keinen Schritt, der ihren Start verschiebt."""
    n = int(aus.get("einfrieren") or 0)
    if n <= 0:
        return set()
    heute = ein.get("heute") or aus.get("heute") or datetime.date.today()
    erster = heute if einlastung.tagesstunden(aus, D.FREMD, heute) > 0 else verschoben(aus, D.FREMD, heute, 1)
    grenze = verschoben(aus, D.FREMD, erster, n - 1)
    return {i for i, p in ein["plan"].items() if p.get("start") and p["start"] <= grenze}


def _bleibt(ein, probe, fest):
    """N3: verschiebt die Probe den Start eines eingefrorenen Auftrags?"""
    return all((probe["plan"].get(i) or {}).get("start") == ein["plan"][i]["start"] for i in fest)


def ausweichen(aus, ein, schwelle=einlastung.SCHWELLE):
    """Vorschlag Ausweichmaschine (E3): Für jeden einteiligen, noch nicht laufenden Auftrag mit Terminrisiko die
    Maschine, auf der er bei gleicher Laufzeit am frühesten fertig wäre, ohne dass ein anderer Auftrag dadurch ein
    schlechteres Terminrisiko bekommt. {Auftrag-ID: dict(maschine, fertig, risiko, tage)} (tage = Arbeitstage früher)."""
    kandidaten = [m for m in aus.get("ausweich") or () if m in aus["maschinen"]]
    out = {}
    fest = eingefroren(aus, ein)
    for a in ein["auftraege"]:
        if a["id"] in fest:
            continue
        if (a["risiko"] not in (einlastung.KNAPP, einlastung.UEBER) or "gang" in a or a.get("fest")
                or a.get("vorrang") == LAEUFT_ZUERST or a["maschine"] not in kandidaten or "teil" in a):
            continue
        jetzt, beste = ein["plan"][a["id"]], None
        for m in kandidaten:
            if m == a["maschine"] or not passt(aus, a, m):
                continue
            probe = rechnen(aus, schwelle, probe=Probe(maschine={a["id"]: m}))
            neu = probe["plan"][a["id"]]
            if neu["fertig"] is None or (jetzt["fertig"] is not None and neu["fertig"] >= jetzt["fertig"]):
                continue
            if any(x["schlechter"] > 0 for x in vergleich(ein, probe) if x["id"] != a["id"]):
                continue
            if not _bleibt(ein, probe, fest):
                continue
            if beste is None or neu["fertig"] < beste["fertig"]:
                tage = (einlastung._arbeitstage(aus, D.FREMD, neu["fertig"], jetzt["fertig"])
                        if jetzt["fertig"] else None)
                beste = dict(maschine=m, fertig=neu["fertig"], risiko=neu["risiko"], tage=tage)
        if beste:
            out[a["id"]] = beste
    return out


def _guete(ein):
    """Güte einer Einlastung, kleiner ist besser: (Aufträge nicht zu halten, knapp, Arbeitstage Verspätung)."""
    plan = ein["plan"].values()
    return (sum(1 for x in plan if x["risiko"] == einlastung.UEBER),
            sum(1 for x in plan if x["risiko"] == einlastung.KNAPP),
            sum(-x["puffer"] for x in plan if x.get("puffer") is not None and x["puffer"] < 0)
            + 1000 * sum(1 for x in plan if x["fertig"] is None))


OPT_MASCHINE, OPT_VOR, OPT_TERMIN, OPT_FOLGE = "maschine", "vorziehen", "termin", "reihenfolge"
ZIEL_TERMIN, ZIEL_RUESTEN, ZIEL_GLEICH = "termin", "ruesten", "gleich"
ZIELE = ((ZIEL_TERMIN, "Wenige Verspätungen"), (ZIEL_RUESTEN, "Wenig Rüsten"),
         (ZIEL_GLEICH, "Gleichmäßige Auslastung"))


def reichweite(aus, ein, maschinen=None):
    """Arbeitsvorrat je Maschine in Arbeitstagen: eingelastete Stunden geteilt durch die Stunden eines üblichen
    Arbeitstags (Mittel der nächsten vier Wochen). {Maschine: Tage}."""
    out = {}
    for m in maschinen if maschinen is not None else ein["maschinen"]:
        tage = [ein["kapazitaet"].get((m, d), 0.0) for d in ein["tage"][:28]]
        tage = [h for h in tage if h > 1e-9]
        if not tage:
            continue
        stunden = sum(a.get("h") or 0.0 for a in ein["auftraege"] if a["maschine"] == m)
        out[m] = stunden / (sum(tage) / len(tage))
    return out


def _ungleich(aus, ein, maschinen):
    r = reichweite(aus, ein, maschinen)
    return round(max(r.values()) - min(r.values()), 3) if len(r) > 1 else 0.0


def optimieren(aus, ein, schwelle=einlastung.SCHWELLE, runden=25, versuche=600, ziel=ZIEL_TERMIN):
    """Automatische Optimierung (V5, A2), als Vorschlag: sucht Schritt für Schritt die Änderung, die dem Ziel am
    meisten hilft, bis keine mehr hilft. Nichts wird gespeichert. Angefasst werden nur einteilige, nicht laufende
    Aufträge ohne festen Platz und ohne Teillieferungen; auf eine andere Maschine nur, wenn das Rohr dort passt.

    - ZIEL_TERMIN: möglichst wenige Aufträge nicht zu halten oder knapp. Schritte: auf eine Ausweichmaschine legen,
      vorziehen, eine Reihenfolge von Hand wieder nach Liefertermin ordnen.
    - ZIEL_RUESTEN: möglichst wenig Rüstzeit, ohne dass ein Termin mehr reißt oder knapp wird. Schritt: einen Auftrag
      direkt hinter einen früheren mit gleichem Material auf derselben Maschine stellen (die Aufträge bis dorthin
      bekommen eine feste Reihenfolge).
    - ZIEL_GLEICH: Arbeitsvorrat der Ausweichmaschinen möglichst gleich (reichweite()), ohne dass ein Termin mehr
      reißt oder knapp wird. Schritt: auf eine Ausweichmaschine legen.

    Ergebnis None (nichts zu verbessern) oder dict(ziel, schritte=[dict(id, nummer, kunde, art, von, nach)], vorher,
    nachher (Güte: nicht zu halten, knapp, Arbeitstage Verspätung), ruest (Stunden vorher, nachher), ungleich
    (Arbeitstage Unterschied vorher, nachher), ein (Einlastung danach), aenderungen (vergleich))."""
    kandidaten = [m for m in aus.get("ausweich") or () if m in aus["maschinen"]]
    frei = {}
    fest = eingefroren(aus, ein)                     # N3: die nächsten Tage bleiben, wie sie sind
    for a in ein["auftraege"]:
        if ("gang" not in a and "teil" not in a and not a.get("fest") and a.get("vorrang") != LAEUFT_ZUERST
                and a["id"] not in fest):
            frei[a["id"]] = a
    maschine, vorrang = {}, {}                       # Stand der Schritte: {Auftrag-ID: Maschine}, {ID: Vorrang}

    def rechne(masch, vorr):
        if vorr:
            kopie = dict(aus, auftraege={k: [dict(x, vorrang=vorr[x["id"]]) if x["id"] in vorr and "gang" not in x
                                             and "teil" not in x else x for x in liste]
                                         for k, liste in aus["auftraege"].items()})
        else:
            kopie = aus
        return rechnen(kopie, schwelle, probe=Probe(maschine=masch) if masch else None)

    def wert(e):
        """Was das Ziel kleiner haben will; die Termine dürfen dabei nie schlechter werden."""
        g = _guete(e)
        if ziel == ZIEL_RUESTEN:
            return (round(e.get("ruest_h") or 0.0, 4),) + g
        if ziel == ZIEL_GLEICH:
            return (_ungleich(aus, e, kandidaten),) + g
        return g

    def folge_zuege(stand):
        """ZIEL_RUESTEN: (OPT_FOLGE, Auftrag, {ID: Vorrang}) – Auftrag direkt hinter den letzten davor mit gleichem
        Material auf seiner Maschine."""
        zuege = []
        for m in stand["maschinen"]:
            reihe = [a for a in arbeitsliste(stand, m) if a["id"] in frei]
            hoch = max([a.get("vorrang") or 0 for a in stand["auftraege"]
                        if a["maschine"] == m and a.get("vorrang") != LAEUFT_ZUERST] + [0])
            for k, b in enumerate(reihe):
                if not b.get("ruest_h") or not b.get("material"):
                    continue
                gleich = [n for n in range(k) if (reihe[n].get("material") or "").casefold()
                          == b["material"].casefold()]
                if not gleich:
                    continue
                n = gleich[-1]
                neu = reihe[:n + 1] + [b] + reihe[n + 1:k]          # bis hierher feste Reihenfolge
                zuege.append((OPT_FOLGE, b["id"], {x["id"]: hoch + len(neu) - pos for pos, x in enumerate(neu)}))
        return zuege

    stand, guete, ziel_wert = ein, _guete(ein), wert(ein)
    vorher, schritte, n = guete, [], 0
    for _runde in range(runden):
        if ziel == ZIEL_TERMIN and guete[:2] == (0, 0):
            break
        plan = stand["plan"]
        zuege = []
        hoch = max([v for v in list(vorrang.values()) + [a.get("vorrang") or 0 for a in frei.values()]
                    if v != LAEUFT_ZUERST] + [0]) + 1
        if ziel == ZIEL_RUESTEN:
            zuege = folge_zuege(stand)
        for i, a in frei.items():
            if ziel == ZIEL_RUESTEN:
                break
            risiko = plan[i]["risiko"]
            jetzt_m = maschine.get(i, a["maschine"])
            jetzt_v = vorrang.get(i, a.get("vorrang") or 0)
            if ziel == ZIEL_GLEICH:
                if a["maschine"] in kandidaten:
                    zuege += [(OPT_MASCHINE, i, m) for m in kandidaten if m != jetzt_m and passt(aus, a, m)]
                continue
            if risiko in (einlastung.KNAPP, einlastung.UEBER):
                if a["maschine"] in kandidaten:
                    zuege += [(OPT_MASCHINE, i, m) for m in kandidaten if m != jetzt_m and passt(aus, a, m)]
                if jetzt_v <= 0 or jetzt_v < hoch - 1:
                    zuege.append((OPT_VOR, i, hoch))
            if jetzt_v != 0:
                zuege.append((OPT_TERMIN, i, 0))
        beste = None
        for art, i, was in zuege:
            if n >= versuche:
                break
            n += 1
            masch, vorr = dict(maschine), dict(vorrang)
            if art == OPT_MASCHINE:
                masch[i] = was
            elif art == OPT_FOLGE:
                vorr.update(was)
            else:
                vorr[i] = was
            probe = rechne(masch, vorr)
            if not _bleibt(ein, probe, fest):
                continue
            g, w = _guete(probe), wert(probe)
            if ziel != ZIEL_TERMIN and g[:2] > guete[:2]:
                continue                                         # kein Termin darf dafür reißen oder knapp werden
            if w < ziel_wert and (beste is None or w < beste[0]):
                beste = (w, art, i, was, masch, vorr, probe, g)
        if beste is None:
            break
        ziel_wert, art, i, was, maschine, vorrang, stand, guete = beste
        a = frei[i]
        if art != OPT_FOLGE:
            schritte = [x for x in schritte if not (x["id"] == i and x["art"] == art)]  # derselbe Zug: der letzte gilt
        schritte.append(dict(id=i, nummer=a["nummer"], kunde=a.get("kunde") or "", art=art,
                             von=a["maschine"] if art == OPT_MASCHINE else None,
                             nach=was if art == OPT_MASCHINE else None, material=a.get("material") or "",
                             vorrang=dict(was) if art == OPT_FOLGE else None))
    schritte = [x for x in schritte if not (x["art"] == OPT_MASCHINE and x["nach"] == x["von"])]
    if not schritte:
        return None
    return dict(ziel=ziel, schritte=schritte, vorher=vorher, nachher=guete, ein=stand,
                ruest=(ein.get("ruest_h") or 0.0, stand.get("ruest_h") or 0.0),
                ungleich=(_ungleich(aus, ein, kandidaten), _ungleich(aus, stand, kandidaten)),
                aenderungen=vergleich(ein, stand))


def kritische(ein):
    """Aufträge mit Terminrisiko knapp oder überschritten, dringendste zuerst; ein mehrteiliger Auftrag steht einmal
    da (mit dem Arbeitsgang, der zuletzt fertig wird)."""
    je = {}
    for a in einlastung.kritische(ein):
        alt = je.get(a["id"])
        if alt is not None and "teil" in a:       # Teillieferungen: die dringendste steht da (kommt zuerst)
            continue
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


def unterbrechungen(db, von=None, bis=None):
    """Auswertung der Stopps mit Grund (E6): [dict(grund, anzahl, minuten, gemessen)] nach Dauer, dazu eine Zeile
    Gesamt. minuten = Stillstand bis zum Weiterlaufen, gezählt nur, wenn am selben Tag weitergearbeitet wurde
    (gemessen = so viele Stopps); über Nacht oder bis zur Fertigmeldung zählt nur die Anzahl."""
    je = {}
    for s in db.stopps(von, bis):
        z = je.setdefault(s["grund"], dict(grund=s["grund"], anzahl=0, minuten=0, gemessen=0))
        z["anzahl"] += 1
        if s["weiter_am"] and s["weiter_am"][:10] == s["wann"][:10]:
            dauer = (datetime.datetime.fromisoformat(s["weiter_am"]) - datetime.datetime.fromisoformat(s["wann"]))
            z["minuten"] += max(0, int(dauer.total_seconds() / 60 + 0.5))
            z["gemessen"] += 1
    liste = sorted(je.values(), key=lambda z: (-z["minuten"], -z["anzahl"], z["grund"]))
    if liste:
        liste.append(dict(grund="Gesamt", anzahl=sum(z["anzahl"] for z in liste),
                          minuten=sum(z["minuten"] for z in liste), gemessen=sum(z["gemessen"] for z in liste)))
    return liste


def kennzahlen(db, ein, gem, heute=None, von=None, bis=None):
    """Kennzahlen (E7) für die fertigen Aufträge im Zeitraum (nach Fertig-Datum) und den Stand von heute:
    dict(fertig, mit_termin, puenktlich, treue (%, None ohne Aufträge mit Termin), diff_prozent (Kalkulation),
    monate=[dict(monat 'JJJJ-MM', fertig, mit_termin, puenktlich, treue, kalk_min, ist_min, diff_prozent)],
    verspaetet=[dict(id, nummer, kunde, maschine, termin, fertig_plan, tage, art)], maschinen=[dict(maschine, ist_h,
    kap_h, ist_prozent, plan_h, plan_kap_h, plan_prozent)]).
    Pünktlich = am Liefertermin oder früher fertig gemeldet. Verspätet = offen und Liefertermin vorbei (art
    'überfällig') oder laut Plan erst nach dem Liefertermin lieferbar (art 'wird zu spät'); tage = Kalendertage.
    Auslastung: vergangene Wochen aus den Fertigmeldungen (gem), die nächsten vier Wochen aus der Einlastung."""
    heute = heute or datetime.date.today()
    si = soll_ist(db, von, bis)
    monate = {}
    for a in si["zeilen"]:
        m = monate.setdefault((a["fertig_am"] or "")[:7], dict(fertig=0, mit_termin=0, puenktlich=0, kalk_min=0,
                                                               ist_min=0))
        m["fertig"] += 1
        m["kalk_min"] += a["kalk_min"] or 0
        m["ist_min"] += a["ist_min"] or 0
        if a["liefertermin"] and a["fertig_am"]:
            m["mit_termin"] += 1
            m["puenktlich"] += a["fertig_am"] <= a["liefertermin"]
    liste = []
    for monat in sorted(monate):
        m = monate[monat]
        liste.append(dict(m, monat=monat, treue=100 * m["puenktlich"] / m["mit_termin"] if m["mit_termin"] else None,
                          diff_prozent=abweichung(m["kalk_min"], m["ist_min"])[1]))
    mit_termin = sum(m["mit_termin"] for m in liste)
    puenktlich = sum(m["puenktlich"] for m in liste)
    verspaetet = []
    plan = ein.get("plan", {})
    for a in db.auftraege((D.OFFEN, D.LAEUFT)):
        termin = _datum(a["liefertermin"])
        if termin is None:
            continue
        p = plan.get(a["id"], {})
        if termin < heute:
            art, tage = "überfällig", (heute - termin).days
        elif p.get("risiko") == einlastung.UEBER:
            art, tage = "wird zu spät", (p["lieferbar"] - termin).days if p.get("lieferbar") else None
        else:
            continue
        verspaetet.append(dict(id=a["id"], nummer=a["nummer"], kunde=a["kunde"], maschine=a["maschine"],
                               termin=termin, fertig_plan=p.get("fertig"), tage=tage, art=art))
    verspaetet.sort(key=lambda v: (v["termin"], v["nummer"]))
    m0 = wochen.montag(heute)
    kommende = [m0 + datetime.timedelta(weeks=i) for i in range(4)]
    maschinen = []
    for m in ein["maschinen"]:
        ist = sum(gem["stunden"].get((m, mo), 0.0) for mo in gem["montage"])
        kap = sum(gem["kapazitaet"].get((m, mo), 0.0) for mo in gem["montage"])
        plan_h = sum(sum(ein["woche"].get((m, mo), {}).values()) for mo in kommende)
        plan_kap = sum(ein["wochen_kap"].get((m, mo), 0.0) for mo in kommende)
        maschinen.append(dict(maschine=m, ist_h=ist, kap_h=kap, ist_prozent=100 * ist / kap if kap else None,
                              plan_h=plan_h, plan_kap_h=plan_kap,
                              plan_prozent=100 * plan_h / plan_kap if plan_kap else None))
    return dict(fertig=len(si["zeilen"]), mit_termin=mit_termin, puenktlich=puenktlich,
                treue=100 * puenktlich / mit_termin if mit_termin else None,
                diff_prozent=si["gesamt"]["diff_prozent"] if si["zeilen"] else None, monate=liste,
                verspaetet=verspaetet, maschinen=maschinen)


def abweichung(kalk_min, ist_min):
    """Abweichung tatsächlich gegen kalkuliert: (Minuten, Prozent oder None)."""
    if ist_min is None or kalk_min is None:
        return None, None
    diff = int(ist_min) - int(kalk_min)
    return diff, (diff / kalk_min * 100 if kalk_min else None)


ERFAHRUNG_MIN, ERFAHRUNG_TAGE, ERFAHRUNG_GRENZE = 5, 365, (0.5, 2.0)


def erfahrung(db, heute=None, alle=False):
    """N3 (Plan 2.2): Erfahrungswert je Maschine aus Soll und Ist der letzten 365 Tage: {Maschine: (Faktor, Anzahl)},
    Faktor = tatsächliche durch kalkulierte Laufzeit (begrenzt auf 0,5 bis 2), erst ab 5 fertigen Aufträgen.
    Ohne alle nur Maschinen, bei denen „Mit Erfahrungswert planen“ an ist."""
    heute = heute or datetime.date.today()
    an = {m["name"] for m in db.maschinen() if alle or m.get("erfahrung")}
    if not an:
        return {}
    out = {}
    for s in soll_ist(db, heute - datetime.timedelta(days=ERFAHRUNG_TAGE), heute)["maschinen"]:
        if s["maschine"] in an and s["anzahl"] >= ERFAHRUNG_MIN and s["kalk_min"] > 0:
            f = min(ERFAHRUNG_GRENZE[1], max(ERFAHRUNG_GRENZE[0], s["ist_min"] / s["kalk_min"]))
            out[s["maschine"]] = (f, s["anzahl"])
    return out


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


def monat(ein, jahr, monat_nr, maschinen=None):
    """Monatsplan wie die Excel-Plantafel (E2, Plan 2.3): Zeilen = Tage des Monats, Spalten = Maschinen.
    dict(tage=[Datum], maschinen=[Name], zellen={(Maschine, Tag): [dict(id, gang, nummer, kunde, minuten, risiko)]},
    kap={(Maschine, Tag): Stunden}, last={(Maschine, Tag): Stunden}, summe={Maschine: (geplant h, verfügbar h)}).
    Vergangene Tage haben keine Einlastung (die beginnt heute); was dort tatsächlich lief, steht in tag_ist()."""
    erster = datetime.date(int(jahr), int(monat_nr), 1)
    folgender = (erster + datetime.timedelta(days=32)).replace(day=1)
    tage = [erster + datetime.timedelta(days=i) for i in range((folgender - erster).days)]
    namen = list(ein["maschinen"] if maschinen is None else maschinen)
    im_monat = set(tage)
    zellen, last = {}, {}
    for a in ein["auftraege"]:
        m = a.get("maschine")
        if m not in namen:
            continue
        for d, von, bis in a.get("stuecke") or ():
            if d in im_monat and bis - von > 1e-9:
                zellen.setdefault((m, d), []).append(dict(id=a["id"], gang=a.get("gang"), nummer=a["nummer"],
                                                          kunde=a.get("kunde") or "",
                                                          minuten=int((bis - von) * 60 + 0.5),
                                                          risiko=a.get("risiko"), von=von))
                last[(m, d)] = last.get((m, d), 0.0) + (bis - von)
    for liste in zellen.values():
        liste.sort(key=lambda x: x["von"])
    kap = {(m, d): ein["kapazitaet"].get((m, d), 0.0) for m in namen for d in tage}
    summe = {m: (sum(last.get((m, d), 0.0) for d in tage),
                 sum(kap[(m, d)] for d in tage if d >= ein.get("heute", tage[0]))) for m in namen}
    return dict(tage=tage, maschinen=namen, zellen=zellen, kap=kap, last=last, summe=summe)
