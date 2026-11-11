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
        rest = max(0, int(a["kalk_min"]) - db.gelaufen(a, jetzt))
        termin = _datum(a["liefertermin"])
        auftraege.setdefault((a["maschine"], ALLE), []).append(dict(
            id=a["id"], nummer=a["nummer"], kunde=a["kunde"], art=einlastung.AUFTRAG, maschine=a["maschine"],
            h=rest / 60, termin=a["liefertermin"], bis=termin, status=a["status"], kalk_min=a["kalk_min"],
            # Reihenfolge: was gerade läuft zuerst, dann von Hand vorgezogen, nach Termin, zurückgestellt
            vorrang=LAEUFT_ZUERST if a["start_am"] else int(a["vorrang"] or 0)))
    m0 = wochen.montag(heute)
    montage = [m0 + datetime.timedelta(weeks=i) for i in range(int(wochenzahl))]
    spalten = [(mo, f"KW {mo.isocalendar()[1]}", mo) for mo in montage] + [(wochen.SPAETER, "später", None)]
    return dict(maschinen=maschinen, auftraege=auftraege, spalten=spalten, kapazitaet={}, heute=heute,
                vorlauf=int(db.zahl("vorlauf_tage")), tag=tag, stunden=8.0, samstag=db.zahl("samstag_stunden"),
                anteil=max(0.0, min(1.0, db.zahl("nutzungsgrad", 100) / 100)), land=db.einstellung("bundesland"),
                ruhe=wochen.betriebsruhe(db.einstellung("betriebsruhe")),
                sperre={m["name"]: wochen.betriebsruhe(m["sperrtage"]) for m in db.maschinen() if m["sperrtage"]})


def einlasten(db, heute=None, wochenzahl=8):
    """(Grundlage, Einlastung) der offenen Aufträge."""
    aus = grundlage(db, heute, wochenzahl)
    return aus, einlastung.rechnen(aus, schwelle=int(db.zahl("schwelle_tage", 2)))


def auskunft(db, minuten, heute=None):
    """Terminauskunft (P6): Wann wäre ein neuer Auftrag mit dieser Laufzeit fertig, wenn er auf der Maschine hinter
    allen offenen Aufträgen läuft? Nichts wird gespeichert. Ergebnis je aktive Maschine, früheste zuerst:
    [dict(maschine, start, fertig, lieferbar)] (fertig None = passt nicht in die nächsten 400 Tage)."""
    aus = grundlage(db, heute)
    for m in aus["maschinen"]:
        aus["auftraege"].setdefault((m, ALLE), []).append(dict(
            id=-1, nummer="", kunde="", art=einlastung.AUFTRAG, maschine=m, h=max(0, int(minuten or 0)) / 60,
            termin=None, bis=None, vorrang=-LAEUFT_ZUERST))
    ein = einlastung.rechnen(aus)
    liste = [dict(maschine=a["maschine"], start=a["start"], fertig=a["fertig"], lieferbar=a["lieferbar"])
             for a in ein["auftraege"] if a["id"] == -1]
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
    for a in db.auftraege(D.FERTIG):
        tag = _datum(a["fertig_am"])
        if tag is None or wochen.montag(tag) not in montage:
            continue
        key = (a["maschine"], wochen.montag(tag))
        stunden[key] = stunden.get(key, 0.0) + (a["ist_min"] or 0) / 60
        laeufe += 1
    kap = {(m, mo): sum(einlastung.tagesstunden(aus, m, mo + datetime.timedelta(days=i)) for i in range(6))
           for m in aus["maschinen"] for mo in montage}
    return dict(montage=montage, stunden=stunden, kapazitaet=kap, laeufe=laeufe)


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
        s = je.setdefault(a["maschine"], dict(maschine=a["maschine"], anzahl=0, kalk_min=0, ist_min=0))
        s["anzahl"] += 1
        s["kalk_min"] += a["kalk_min"] or 0
        s["ist_min"] += a["ist_min"] or 0
    zeilen.sort(key=lambda a: (a["fertig_am"] or "", a["nummer"]), reverse=True)
    summen = sorted(je.values(), key=lambda s: s["maschine"])
    gesamt = dict(maschine="Gesamt", anzahl=sum(s["anzahl"] for s in summen),
                  kalk_min=sum(s["kalk_min"] for s in summen), ist_min=sum(s["ist_min"] for s in summen))
    for s in summen + [gesamt]:
        s["diff_min"], s["diff_prozent"] = abweichung(s["kalk_min"], s["ist_min"]) if s["anzahl"] else (0, None)
    return dict(zeilen=zeilen, maschinen=summen, gesamt=gesamt)
