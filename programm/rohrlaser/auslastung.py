"""Wochenauslastung je Maschine mit Schichtkalender (Plan 29.10.2026 Schritt 2b).

Bedarf: je beauftragtes Angebot die Laserzeit aus der Kalkulation (Arbeitsschritte Laser schneiden, Rüsten Maschine,
Rüsten je Abmessung, Stangenwechsel; gerechnet wie im Angebotsfenster mit dem gespeicherten Schnittplan) auf der
Maschine des Angebots. Schon gemeldete Teile (Rückmeldung per Scan, erster Arbeitsschritt, etiketten.py) ziehen ihren
Anteil an der Schneidzeit ab; Aufträge mit dem letzten Fertigungsstatus (Fertig gemeldet) zählen nicht mehr.
Die Zeit fällt in die Woche des Liefertermins minus Vorlauf (Einstellung 'auslastung_vorlauf', Arbeitstage für
Entgraten, Verpacken, Versand). Vor dieser Woche: Spalte „überfällig“; ohne Liefertermin: „ohne Termin“.
Auf Wunsch zählen verschickte Angebote gewichtet mit der Trefferquote (absage.py) mit; Termin dann aus der
Lieferzeit des Angebots ab heute (auftrag.termin_vorschlag).

Kapazität je Woche und Maschine = Arbeitstage × Stunden je Arbeitstag (Maschine 'schicht_stunden', sonst Einstellung
'schicht_stunden') + Samstag ('schicht_samstag') × nutzbarer Anteil ('schicht_verfuegbar'). Arbeitstage: Montag bis
Freitag ohne die Feiertage des Bundeslands ('versand_bundesland') und ohne Betriebsruhe ('betriebsruhe': Daten und
Zeiträume, z. B. '24.12.2026-31.12.2026; 02.10.2026')."""
import datetime
import re

from . import absage, auftrag, feiertage, preis_simulator, rechnen

UEBERFAELLIG, SPAETER, OHNE = "überfällig", "später", "ohne Termin"
GELB, ROT = 0.8, 1.0           # Auslastung ab 80 % gelb, über 100 % rot
GEWICHT_OHNE_QUOTE = 0.5       # verschickte Angebote, solange es noch keine Trefferquote gibt
LASER_SCHRITTE = ("Laser schneiden", "Rüsten Maschine", "Rüsten je Abmessung", "Stangenwechsel")


def _datum(t):
    t = t.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def betriebsruhe(text):
    """'24.12.2026-31.12.2026; 02.10.2026' -> Menge der Tage. Unlesbares wird übergangen."""
    tage = set()
    for teil in re.split(r"[;,\n]+", str(text or "")):
        von, _, bis = teil.partition("-") if re.match(r"^\s*\d{1,2}\.\d", teil) else (teil, "", "")
        a, b = _datum(von) if von.strip() else None, _datum(bis) if bis.strip() else None
        if a is None:
            continue
        b = b or a
        while a <= b:
            tage.add(a)
            a += datetime.timedelta(days=1)
    return tage


def montag(d):
    return d - datetime.timedelta(days=d.weekday())


def kapazitaet(montag_, stunden_tag, samstag, anteil, land, ruhe):
    """Nutzbare Stunden einer Woche ab Montag."""
    h = 0.0
    for i in range(6):
        d = montag_ + datetime.timedelta(days=i)
        if d in ruhe or feiertage.name(d, land):
            continue
        h += stunden_tag if i < 5 else samstag
    return h * anteil


def _f(v, vorgabe=0.0):
    try:
        return float(v) if v not in (None, "") else vorgabe
    except (TypeError, ValueError):
        return vorgabe


def maschinenzeit(db, a, aktuell=None, einst=None):
    """(Laserstunden, Anteil schon geschnitten 0..1) eines Angebots; (None, 0) ohne Schnittplan."""
    if not a.get("ergebnis"):
        return None, 0.0
    pos = db.positionen(a["id"])
    if not pos:
        return None, 0.0
    k, tab, e = preis_simulator.grundlage(db, a, aktuell, einst)
    zeilen, summen = rechnen.kalkulation(a, pos, a["ergebnis"], k, tab, e)
    h = sum(z["gesamt_min"] for z in summen.get("zeiten") or () if z.get("schritt") in LASER_SCHRITTE
            and z.get("gesamt_min")) / 60
    return h, _geschnitten(db, a["id"], pos, zeilen)


def _geschnitten(db, angebot_id, pos, zeilen):
    """Anteil der Schneidzeit, deren Teile im ersten Arbeitsschritt der Rückmeldung gemeldet sind."""
    from . import etiketten
    erster = etiketten.schritte(db)[0]
    gemeldet = {z["id"]: z["schritte"].get(erster, 0) for z in etiketten.stand_je_position(db, angebot_id)}
    gesamt = fertig = 0.0
    for p, z in zip(pos, zeilen):
        if not z:
            continue
        t = _f(z.get("laser_netto")) * _f(z.get("stueck"))
        gesamt += t
        stueck = _f(p.get("stueck"))
        if stueck > 0:
            fertig += t * min(1.0, gemeldet.get(p["id"], 0) / stueck)
    return fertig / gesamt if gesamt else 0.0


def _termin(a, vorlauf, land):
    try:
        d = datetime.date.fromisoformat(str(a.get("liefertermin")))
    except (TypeError, ValueError):
        return None
    n = vorlauf
    while n > 0:
        d -= datetime.timedelta(days=1)
        if feiertage.ist_arbeitstag(d, land):
            n -= 1
    return d


def berechnen(db, heute=None, wochen=8, offene=False, fortschritt=None):
    """Auslastung: dict(spalten=[(Schlüssel, Titel, Montag oder None)], maschinen=[ID], kapazitaet={(m, s): h},
    bedarf={(m, s): h}, auftraege={(m, s): [dict(id, nummer, kunde, h, termin, art, gewicht)]}, fehlt=[(Nummer,
    Grund)], gewicht=Gewicht der verschickten Angebote oder None). Spalten: überfällig, die Wochen ab dieser,
    später, ohne Termin."""
    heute = heute or datetime.date.today()
    k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
    land = db.einstellung("versand_bundesland") or feiertage.VORGABE
    ruhe = betriebsruhe(db.einstellung("betriebsruhe"))
    vorlauf = int(_f(db.einstellung("auslastung_vorlauf"), 2))
    std, sa = _f(db.einstellung("schicht_stunden"), 8), _f(db.einstellung("schicht_samstag"), 0)
    anteil = _f(db.einstellung("schicht_verfuegbar"), 0.85)
    m0 = montag(heute)
    montage = [m0 + datetime.timedelta(weeks=i) for i in range(max(1, int(wochen)))]
    spalten = ([(UEBERFAELLIG, UEBERFAELLIG, None)]
               + [(m, f"KW {m.isocalendar()[1]}", m) for m in montage] + [(SPAETER, SPAETER, None), (OHNE, OHNE, None)])
    maschinen = sorted(k.maschinen)
    kap = {}
    for m in maschinen:
        st = _f(k.maschinen[m].get("schicht_stunden"), std)
        for mo in montage:
            kap[(m, mo)] = kapazitaet(mo, st, sa, anteil, land, ruhe)
    from . import fertigung
    letzter = fertigung.status_liste(db)[-1]
    liste = [(a, "Auftrag", 1.0) for a in db.angebote() if a.get("vorgang") == "Beauftragt" and not a.get("fremd")
             and (fertigung.aktuell(db, a["id"]) or {}).get("status") != letzter]
    gewicht = None
    if offene:
        kat = {w: z.get("kategorie") for w, z in k.werkstoffe.items()}
        q = absage.auswertung(db.angebote(), db.angebot_werkstoffe(), kat, heute, 365)["gesamt"]["trefferquote"]
        gewicht = q if q is not None else GEWICHT_OHNE_QUOTE
        liste += [(a, "Angebot", gewicht) for a in db.angebote() if a.get("vorgang") == "Verschickt"
                  and not a.get("fremd") and not a.get("ersetzt_durch")]
    bedarf, auftraege, fehlt = {}, {}, []
    for i, (z, art, g) in enumerate(liste):
        if fortschritt:
            fortschritt(i, len(liste))
        a = db.angebot(z["id"]) or {}
        try:
            h, fertig = maschinenzeit(db, a, (k, tab), einst)
        except Exception as fehler:        # ein beschädigtes Angebot hält die Übersicht nicht an
            fehlt.append((a.get("nummer"), f"Fehler: {fehler}"))
            continue
        if h is None:
            fehlt.append((a.get("nummer"), "nicht optimiert"))
            continue
        h = h * (1 - fertig) * g
        if h <= 0:
            continue
        if art == "Angebot" and not a.get("liefertermin"):
            a = dict(a, liefertermin=auftrag.termin_vorschlag(a, heute, land).isoformat())
        t = _termin(a, vorlauf, land)
        s = OHNE if t is None else UEBERFAELLIG if t < m0 else montag(t) if montag(t) in montage else SPAETER
        m = a.get("maschine") or "?"
        if m not in maschinen:
            maschinen.append(m)
        bedarf[(m, s)] = bedarf.get((m, s), 0.0) + h
        auftraege.setdefault((m, s), []).append(dict(id=a["id"], nummer=a.get("nummer"), kunde=a.get("kunde"), h=h,
                                                    termin=a.get("liefertermin"), art=art, gewicht=g,
                                                    geschnitten=fertig))
    return dict(spalten=spalten, maschinen=maschinen, kapazitaet=kap, bedarf=bedarf, auftraege=auftraege,
                fehlt=fehlt, gewicht=gewicht)


def quote(bedarf, kapazitaet):
    return bedarf / kapazitaet if kapazitaet else None
