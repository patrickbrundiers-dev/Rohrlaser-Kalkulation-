"""Plantafel: Belegungen mit Ende und Terminrisiko aus dem aktuellen Kalender, Kennzahlen und die Vorschau einer
Planänderung (verschieben, auf andere Maschine, Dauer ändern, Nachrücken der Folgeaufträge).

Belegungsdauer (Bericht Abschnitt 5.1): Dauer der Belegung, wenn von Hand gesetzt, sonst Maschinenzeit + Rüstzeit
des Auftrags. Ohne beides ist die Dauer offen (0 Minuten, mit Warnung).
"""
import datetime

from . import kalender

VORLAUF_TAGE = 400        # so weit reicht die Suche nach freien Fenstern für das Ende einer Belegung


def anzeige(t):
    """'2026-10-21T06:00' → '21.10.2026 06:00'."""
    t = kalender.zeit(t)
    return f"{t:%d.%m.%Y %H:%M}" if t else "–"


def dauer(b):
    """(Minuten, Quelle) einer Belegung bzw. eines Auftrags (dict mit dauer_min, maschinenzeit_min, ruestzeit_min)."""
    if b.get("dauer_min") is not None:
        return float(b["dauer_min"]), "Belegung (von Hand)"
    if b.get("maschinenzeit_min") is None and b.get("ruestzeit_min") is None:
        return 0.0, "offen"
    return float(b.get("maschinenzeit_min") or 0) + float(b.get("ruestzeit_min") or 0), b.get("zeitquelle") or "manuell"


class Kalender:
    """Fenster je Maschine für einen Zeitraum, einmal gerechnet."""

    def __init__(self, kal, maschinen, von, bis):
        self.kal, self.von, self.bis = kal, kalender.zeit(von), kalender.zeit(bis)
        self.fenster = {m: kalender.verfuegbare_fenster(m, self.von, self.bis, kal["schichten"], kal["ausnahmen"],
                                                        kal["stillstaende"]) for m in maschinen}

    def arbeitstage(self, m):
        return {a.date() for a, b in self.fenster.get(m, [])}


def kalender_fuer(db, beginn_frueh=None):
    kal = db.kalender()
    heute = datetime.datetime.combine(datetime.date.today(), datetime.time())
    von = min(heute - datetime.timedelta(days=60), kalender.zeit(beginn_frueh) or heute)
    return Kalender(kal, [m["id"] for m in db.maschinen()], von, heute + datetime.timedelta(days=VORLAUF_TAGE))


def berechnen(belegungen, kal, schwelle):
    """Ergänzt jede Belegung um dauer, dauer_quelle, beginn_eff, ende, risiko, puffer_tage und warnungen."""
    for b in belegungen:
        d, quelle = dauer(b)
        fenster = kal.fenster.get(b["maschine"], [])
        beginn, ende = kalender.ende_berechnen(b["beginn"], d, fenster)
        ende = kalender.aufrunden(ende)
        b.update(dauer=d, dauer_quelle=quelle, beginn_eff=kalender.zeit_text(beginn), ende=kalender.zeit_text(ende))
        b["risiko"], b["puffer_tage"] = kalender.terminrisiko(ende, b.get("liefertermin"), kal.arbeitstage(b["maschine"]),
                                                              schwelle)
        w = []
        if not fenster:
            w.append(f"Für {b['maschine']} ist kein Schichtmodell hinterlegt (offene Konfiguration)")
        elif ende is None:
            w.append("Kein Ende innerhalb des Planungshorizonts (Schichten fehlen?)")
        if quelle == "offen":
            w.append("Maschinenzeit fehlt")
        erlaubt = [m for m in (b.get("maschinen_erlaubt") or "").split(",") if m]
        if erlaubt and b["maschine"] not in erlaubt:
            w.append(f"Auftrag ist nur für {', '.join(erlaubt)} freigegeben")
        if b.get("beginn_eff") and b["beginn_eff"] != b["beginn"]:
            w.append(f"Beginn liegt außerhalb der Schicht, gerechnet ab {anzeige(b['beginn_eff'])}")
        b["warnungen"] = w
    ueber = kalender.ueberschneidungen([dict(id=b["id"], maschine=b["maschine"], beginn=b["beginn_eff"], ende=b["ende"])
                                        for b in belegungen])
    nach_id = {b["id"]: b for b in belegungen}
    for x, y in ueber:
        nach_id[x]["warnungen"].append(f"Überschneidet sich mit Auftrag {nach_id[y]['auftragsnummer']}")
        nach_id[y]["warnungen"].append(f"Überschneidet sich mit Auftrag {nach_id[x]['auftragsnummer']}")
    return belegungen


def plan(db, von, bis):
    """Alles für die Plantafel und das Dashboard im Zeitraum [von, bis)."""
    von, bis = kalender.zeit(von), kalender.zeit(bis)
    belegungen = db.belegungen()
    frueh = min([kalender.zeit(b["beginn"]) for b in belegungen] + [von])
    kal = kalender_fuer(db, frueh)
    schwelle = int(db.einstellungen().get("termin_schwelle_tage") or 0)
    berechnen(belegungen, kal, schwelle)
    maschinen = db.maschinen()
    for m in maschinen:
        fenster = [(a, b) for a, b in kal.fenster.get(m["id"], []) if b > von and a < bis]
        m["fenster"] = [(kalender.zeit_text(max(a, von)), kalender.zeit_text(min(b, bis))) for a, b in fenster]
        m["kennzahlen"] = kennzahl(m["id"], von, bis, belegungen, kal)
        m["ohne_schicht"] = not any(s["maschine"] == m["id"] for s in kal.kal["schichten"])
    sichtbar = [b for b in belegungen if b["ende"] is None or (kalender.zeit(b["ende"]) > von
                                                                and kalender.zeit(b["beginn_eff"]) < bis)]
    stillstaende = [s for s in kal.kal["stillstaende"] if kalender.zeit(s["ende"]) > von and kalender.zeit(s["beginn"]) < bis]
    return dict(von=kalender.zeit_text(von), bis=kalender.zeit_text(bis), maschinen=maschinen, belegungen=sichtbar,
                stillstaende=stillstaende, schwelle=schwelle)


def kennzahl(m, von, bis, belegungen, kal):
    """Auslastung der Maschine m im Zeitraum mit den schon gerechneten Fenstern."""
    fenster = [(max(a, von), min(b, bis)) for a, b in kal.fenster.get(m, []) if b > von and a < bis]
    verfuegbar = kalender.summe(fenster)
    geplant = sum(kalender.belegte_minuten(b["beginn_eff"], b["ende"], fenster, von, bis) for b in belegungen
                  if b["maschine"] == m and b.get("ende"))
    return dict(verfuegbar_min=round(verfuegbar, 1), geplant_min=round(geplant, 1), frei_min=round(verfuegbar - geplant, 1),
                auslastung=round(geplant / verfuegbar * 100, 1) if verfuegbar else None)


def dashboard(db):
    """Kennzahlen je Maschine für heute, diese Woche und die nächsten vier Wochen; kritische Termine, ungeplante
    Aufträge, nächste Stillstände, offene Konfiguration."""
    heute = datetime.datetime.combine(datetime.date.today(), datetime.time())
    montag = heute - datetime.timedelta(days=heute.weekday())
    belegungen = db.belegungen()
    frueh = min([kalender.zeit(b["beginn"]) for b in belegungen] + [heute])
    kal = kalender_fuer(db, frueh)
    schwelle = int(db.einstellungen().get("termin_schwelle_tage") or 0)
    berechnen(belegungen, kal, schwelle)
    maschinen = db.maschinen()
    for m in maschinen:
        m["heute"] = kennzahl(m["id"], heute, heute + datetime.timedelta(days=1), belegungen, kal)
        m["wochen"] = []
        for i in range(5):
            a = montag + datetime.timedelta(days=7 * i)
            kw = a.isocalendar()[1]
            m["wochen"].append(dict(name=f"KW {kw:02d}", **kennzahl(m["id"], a, a + datetime.timedelta(days=7),
                                                                     belegungen, kal)))
        m["ohne_schicht"] = not any(s["maschine"] == m["id"] for s in kal.kal["schichten"])
    aktiv = [b for b in belegungen if b.get("status") not in ("fertig", "storniert")]
    kritisch = sorted([b for b in aktiv if b["risiko"] in ("überschritten", "kritisch")],
                      key=lambda b: (b["liefertermin"] or "", b["auftragsnummer"]))
    ungeplant = [a for a in db.auftraege() if a["belegung_id"] is None and a["status"] in ("offen", "in Arbeit")]
    stillstaende = [s for s in kal.kal["stillstaende"] if kalender.zeit(s["ende"]) >= heute][:10]
    warnungen = [b for b in aktiv if b["warnungen"]]
    return dict(maschinen=maschinen, kritisch=kritisch, ungeplant=ungeplant, stillstaende=stillstaende,
                warnungen=warnungen, schwelle=schwelle)


def vorschau(db, aenderung):
    """Was eine Planänderung bewirkt, ohne zu speichern.
    aenderung: {auftrag_id (neu einplanen) oder id (vorhandene Belegung), maschine, beginn, dauer_min? (leer = aus dem
    Auftrag), fixiert?, nachruecken (True = spätere, nicht fixierte Belegungen derselben Maschine rücken hinter die
    geänderte, falls sie sich überschneiden), entfernen?}.
    Ergebnis: {schritte (für Planungsdatenbank.belegungen_schreiben), maschinen_versionen, belegungen (betroffene,
    nachher, mit Ende und Risiko), warnungen, fehler (leer = speicherbar)}."""
    alle = db.belegungen()
    maschinen = {m["id"]: m for m in db.maschinen()}
    kal = kalender_fuer(db, min([kalender.zeit(b["beginn"]) for b in alle]
                                + [kalender.zeit(aenderung.get("beginn")) or datetime.datetime.now()]))
    schwelle = int(db.einstellungen().get("termin_schwelle_tage") or 0)
    nach_id = {b["id"]: b for b in alle}
    fehler, schritte = [], []
    ziel = aenderung.get("maschine")
    if ziel not in maschinen:
        return dict(fehler=[f"Unbekannte Maschine: {ziel}"], schritte=[], belegungen=[], warnungen=[],
                    maschinen_versionen={})
    if aenderung.get("id"):
        b = nach_id.get(int(aenderung["id"]))
        if not b:
            return dict(fehler=["Die Belegung gibt es nicht mehr."], schritte=[], belegungen=[], warnungen=[],
                        maschinen_versionen={})
        quelle = b["maschine"]
        if aenderung.get("entfernen"):
            schritte.append(dict(aktion="entfernen", id=b["id"], version=b["version"], maschine=quelle))
            return dict(fehler=[], schritte=schritte, belegungen=[], warnungen=[],
                        maschinen_versionen={quelle: maschinen[quelle]["version"]})
        neu = dict(b)
        neu.update(maschine=ziel, beginn=kalender.zeit_text(kalender.zeit(aenderung["beginn"])))
        if "dauer_min" in aenderung:
            neu["dauer_min"] = aenderung["dauer_min"] if aenderung["dauer_min"] not in ("", None) else None
        if "fixiert" in aenderung:
            neu["fixiert"] = 1 if aenderung["fixiert"] else 0
        for f in ("ist_beginn", "ist_ende"):
            if f in aenderung:
                neu[f] = aenderung[f] or None
    else:
        a = db.auftrag(int(aenderung.get("auftrag_id") or 0))
        if not a:
            return dict(fehler=["Auftrag nicht gefunden"], schritte=[], belegungen=[], warnungen=[],
                        maschinen_versionen={})
        if any(x["auftrag_id"] == a["id"] for x in alle):
            fehler.append(f"Auftrag {a['auftragsnummer']} ist schon eingeplant")
        quelle = ziel
        neu = dict(id=0, auftrag_id=a["id"], maschine=ziel, beginn=kalender.zeit_text(kalender.zeit(aenderung["beginn"])),
                   dauer_min=aenderung.get("dauer_min") if aenderung.get("dauer_min") not in ("", None) else None,
                   fixiert=1 if aenderung.get("fixiert") else 0, ist_beginn=None, ist_ende=None, version=None,
                   auftragsnummer=a["auftragsnummer"], kunde=a["kunde"], bezeichnung=a["bezeichnung"],
                   liefertermin=a["liefertermin"], prioritaet=a["prioritaet"], status=a["status"],
                   maschinenzeit_min=a["maschinenzeit_min"], ruestzeit_min=a["ruestzeit_min"],
                   zeitquelle=a["zeitquelle"], maschinen_erlaubt=a["maschinen_erlaubt"])
    berechnen([neu], kal, schwelle)
    if neu["beginn_eff"] and neu["beginn_eff"] != neu["beginn"] and not aenderung.get("entfernen"):
        neu["beginn"] = neu["beginn_eff"]            # gespeichert wird der Beginn der Schicht
        neu["warnungen"] = [w for w in neu["warnungen"] if not w.startswith("Beginn liegt außerhalb")]
        neu["warnungen"].append(f"Beginn auf den Schichtbeginn {anzeige(neu['beginn_eff'])} gelegt")
    if kalender.zeit(neu["beginn_eff"]) < datetime.datetime.now() - datetime.timedelta(minutes=5) and not neu.get("ist_beginn"):
        neu["warnungen"].append("Beginn liegt in der Vergangenheit")
    geaendert = [neu]
    if neu["ende"] and aenderung.get("nachruecken"):
        folge = sorted([b for b in alle if b["maschine"] == ziel and b["id"] != neu["id"]],
                       key=lambda b: kalender.zeit(b["beginn"]))
        berechnen(folge, kal, schwelle)
        grenze = kalender.zeit(neu["ende"])
        for b in folge:
            if kalender.zeit(b["beginn_eff"]) < kalender.zeit(neu["beginn_eff"]):
                continue                     # beginnt davor: bleibt (eine Überschneidung meldet die Prüfung unten)
            if kalender.zeit(b["beginn_eff"]) >= grenze:
                break                        # keine Überschneidung mehr, Rest bleibt
            if b["fixiert"]:
                fehler.append(f"Auftrag {b['auftragsnummer']} ist fixiert und würde überlappt")
                break
            v = dict(b, beginn=kalender.zeit_text(grenze))
            berechnen([v], kal, schwelle)
            v["beginn"] = v["beginn_eff"] or v["beginn"]
            geaendert.append(v)
            if not v["ende"]:
                break
            grenze = kalender.zeit(v["ende"])
    # Überschneidungen nach der Änderung (nur mit nicht verschobenen Belegungen der Zielmaschine)
    bleibend = [b for b in alle if b["maschine"] == ziel and b["id"] not in {g["id"] for g in geaendert}]
    berechnen(bleibend, kal, schwelle)
    test = [dict(id=g["id"], maschine=ziel, beginn=g["beginn_eff"], ende=g["ende"]) for g in geaendert] + \
           [dict(id=b["id"], maschine=ziel, beginn=b["beginn_eff"], ende=b["ende"]) for b in bleibend]
    namen = {g["id"]: g["auftragsnummer"] for g in geaendert + bleibend}
    for x, y in kalender.ueberschneidungen(test):
        fehler.append(f"Auftrag {namen[x]} überschneidet sich mit Auftrag {namen[y]}")
    for g in geaendert:
        if g["id"] == 0:
            schritte.append(dict(aktion="neu", auftrag_id=g["auftrag_id"], maschine=ziel, beginn=g["beginn"],
                                 dauer_min=g["dauer_min"], fixiert=g["fixiert"]))
        else:
            schritte.append(dict(aktion="ändern", id=g["id"], version=g["version"], maschine=ziel, beginn=g["beginn"],
                                 dauer_min=g["dauer_min"], fixiert=g["fixiert"], ist_beginn=g.get("ist_beginn"),
                                 ist_ende=g.get("ist_ende")))
    warnungen = [f"{g['auftragsnummer']}: {w}" for g in geaendert for w in g["warnungen"]
                 if not w.startswith("Überschneidet")]
    warnungen += [f"{g['auftragsnummer']}: Liefertermin {anzeige(g['liefertermin'])[:10]} wird überschritten"
                  for g in geaendert if g["risiko"] == "überschritten"]
    warnungen += [f"{g['auftragsnummer']}: Terminrisiko kritisch ({g['puffer_tage']} Arbeitstage Puffer)"
                  for g in geaendert if g["risiko"] == "kritisch"]
    if maschinen[ziel]["status"] == "außer Betrieb":
        warnungen.append(f"{ziel} ist als außer Betrieb markiert")
    versionen = {m: maschinen[m]["version"] for m in {quelle, ziel}}
    return dict(fehler=list(dict.fromkeys(fehler)), schritte=schritte, maschinen_versionen=versionen,
                belegungen=geaendert, warnungen=list(dict.fromkeys(warnungen)))
