"""Einlastung der Maschinen Tag für Tag (Plan Maschinenauslastung, Patrick 10.11.2026, Schritte 1 und 4).

Die Wochenauslastung (auslastung.py) legt die ganze Laserzeit eines Auftrags in die Woche seines Liefertermins minus
Vorlauf: eine überlastete Woche bleibt rot stehen. Die Einlastung rechnet dazu die zweite Sicht: Die Aufträge einer
Maschine laufen ab heute nacheinander durch die freien Stunden des Schichtkalenders (Reihenfolge: Liefertermin, dann
Angebotsnummer; Aufträge ohne Termin zuletzt; verschickte Angebote gewichtet erst nach allen Aufträgen). Was in
einer Woche keinen Platz hat, rutscht in die nächste. Jeder Auftrag bekommt so

- den Tag, an dem er auf dem Laser fertig wird (fertig), und den Tag, an dem er lieferbar ist (fertig + Vorlauf),
- den Puffer in Arbeitstagen bis zum Liefertermin und daraus das Terminrisiko: „ok“, „knapp“ (Puffer unter
  SCHWELLE Arbeitstagen), „überschritten“ (lieferbar nach dem Liefertermin) oder „ohne Termin“.

Dazu die gemessene Auslastung vergangener Wochen aus den Scans „Laser Start“ / „Laser Ende“ (etiketten.py, H4b).

Was-wäre-wenn (Schritt 4): ein Szenario ändert nur die Rechnung, nie die Daten: Auftrag auf einer anderen Maschine
(mit deren Laserzeit), Zusatzstunden je Maschine und Woche, Samstagsstunden. Ohne Qt."""
import datetime

from . import feiertage
from .wochen import montag as _montag

OK, KNAPP, UEBER, OHNE = "ok", "knapp", "überschritten", "ohne Termin"
SCHWELLE = 2                   # Puffer unter so vielen Arbeitstagen = knapp
HORIZONT = 400                 # so viele Tage voraus wird eingelastet; danach „später“
AUFTRAG, ANGEBOT = "Auftrag", "Angebot"


class Szenario:
    """Was-wäre-wenn: maschine {Angebots-ID: (Maschine, Laserstunden oder None)}, zusatz {(Maschine, Montag):
    Stunden zusätzlich in dieser Woche}, samstag = Stunden an jedem Samstag (None = wie eingestellt)."""

    def __init__(self):
        self.maschine, self.zusatz, self.samstag = {}, {}, None

    def leer(self):
        return not self.maschine and not self.zusatz and self.samstag is None

    def text(self):
        teile = []
        if self.maschine:
            teile.append(f"{len(self.maschine)} Auftrag/Aufträge auf anderer Maschine")
        if self.zusatz:
            teile.append("Zusatzstunden " + ", ".join(
                f"{m} KW {mo.isocalendar()[1]} +{h:g} h".replace(".", ",") for (m, mo), h in sorted(self.zusatz.items())))
        if self.samstag is not None:
            teile.append(f"Samstag {self.samstag:g} h".replace(".", ","))
        return "; ".join(teile)


def tagesstunden(aus, m, d, szenario=None):
    """Nutzbare Stunden der Maschine m am Tag d (wie auslastung.kapazitaet, aber je Tag)."""
    if d.weekday() == 6 or d in (aus.get("ruhe") or ()) or d in ((aus.get("sperre") or {}).get(m) or ()):
        return 0.0
    if feiertage.name(d, aus.get("land")):
        return 0.0
    anteil = aus.get("anteil", 1.0)
    if d.weekday() == 5:
        sa = aus.get("samstag", 0.0) if szenario is None or szenario.samstag is None else szenario.samstag
        h = sa * anteil
    else:
        h = (aus.get("tag") or {}).get(m, aus.get("stunden", 8.0)) * anteil
    return h


def _zusatz_je_tag(aus, m, szenario, tage):
    """Zusatzstunden des Szenarios auf die Arbeitstage ihrer Woche verteilt (ohne Arbeitstag: auf den Montag)."""
    out = {}
    if szenario is None:
        return out
    for (zm, mo), h in szenario.zusatz.items():
        if zm != m or h <= 0:
            continue
        woche = [d for d in tage if _montag(d) == mo]
        arbeit = [d for d in woche if tagesstunden(aus, m, d, szenario) > 0] or woche[:1]
        for d in arbeit:
            out[d] = out.get(d, 0.0) + h / len(arbeit)
    return out


def _arbeitstage(aus, m, von, bis, szenario=None):
    """Arbeitstage der Maschine nach von bis einschließlich bis; negativ, wenn bis vor von liegt."""
    if bis == von:
        return 0
    a, b, vz = (von, bis, 1) if bis > von else (bis, von, -1)
    n, d = 0, a
    while d < b:
        d += datetime.timedelta(days=1)
        if tagesstunden(aus, m, d, szenario) > 0:
            n += 1
    return n * vz


def _spaeter(aus, m, start, n, szenario=None):
    """n Arbeitstage der Maschine nach start (höchstens ein Jahr gesucht)."""
    d, grenze = start, start + datetime.timedelta(days=366)
    while n > 0 and d < grenze:
        d += datetime.timedelta(days=1)
        if tagesstunden(aus, m, d, szenario) > 0:
            n -= 1
    return d


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None


def auftragsliste(aus, szenario=None):
    """Alle Aufträge der Auslastung als flache Liste (Kopien), mit der Maschine des Szenarios."""
    liste = []
    for (m, _s), auftraege in aus["auftraege"].items():
        for a in auftraege:
            a = dict(a, maschine=a.get("maschine") or m, ursprung=a.get("maschine") or m)
            # Maschine je Position (MACH-006): das Szenario verlegt nur den Teil auf der Maschine des Angebotskopfs
            if szenario is not None and a["id"] in szenario.maschine and a.get("maschine") == a.get(
                    "kopf_maschine", a.get("maschine")):
                neu, h = szenario.maschine[a["id"]]
                a["maschine"] = neu
                if h is not None:
                    a["h"] = h
            liste.append(a)
    return liste


def _reihenfolge(a):
    # vorrang (nur das eigene Programm Rohrlaser Auslastung): von Hand vorgezogen (> 0) oder zurückgestellt (< 0)
    return (0 if a.get("art") != ANGEBOT else 1, -(a.get("vorrang") or 0), a.get("bis") is None,
            a.get("bis") or datetime.date.max,
            str(a.get("nummer") or ""), a.get("id") or 0)


def rechnen(aus, szenario=None, schwelle=SCHWELLE, horizont=HORIZONT):
    """Einlastung zu einem Ergebnis von auslastung.berechnen. dict(
    maschinen=[ID], tage=[Datum ab heute], kapazitaet={(m, Tag): h}, belegt={(m, Tag): {Art: h}},
    woche={(m, Montag): {Art: h}}, wochen_kap={(m, Montag): h}, spaeter={m: h} (passt nicht in den Horizont),
    auftraege=[dict(id, nummer, kunde, art, maschine, h, termin, start, fertig, lieferbar, puffer, risiko,
    stuecke=[(Tag, von_h, bis_h)])], risiko={Stufe: Anzahl})."""
    heute = aus.get("heute") or datetime.date.today()
    vorlauf = int(aus.get("vorlauf") or 0)
    tage = [heute + datetime.timedelta(days=i) for i in range(horizont)]
    liste = auftragsliste(aus, szenario)
    maschinen = list(aus["maschinen"])
    for a in liste:
        if a["maschine"] not in maschinen:
            maschinen.append(a["maschine"])
    kap, belegt, woche, wochen_kap, spaeter, ergebnis = {}, {}, {}, {}, {}, []
    for m in maschinen:
        zusatz = _zusatz_je_tag(aus, m, szenario, tage)
        for d in tage:
            kap[(m, d)] = tagesstunden(aus, m, d, szenario) + zusatz.get(d, 0.0)
            mo = _montag(d)
            wochen_kap[(m, mo)] = wochen_kap.get((m, mo), 0.0) + kap[(m, d)]
        i, im_tag = 0, 0.0                 # Zeiger: Tag und schon belegte Stunden dieses Tages
        for a in sorted((x for x in liste if x["maschine"] == m), key=_reihenfolge):
            rest, stuecke = max(0.0, float(a.get("h") or 0.0)), []
            while rest > 1e-9 and i < len(tage):
                frei = kap[(m, tage[i])] - im_tag
                if frei <= 1e-9:
                    i, im_tag = i + 1, 0.0
                    continue
                nimm = min(rest, frei)
                stuecke.append((tage[i], im_tag, im_tag + nimm))
                b = belegt.setdefault((m, tage[i]), {})
                b[a["art"]] = b.get(a["art"], 0.0) + nimm
                w = woche.setdefault((m, _montag(tage[i])), {})
                w[a["art"]] = w.get(a["art"], 0.0) + nimm
                im_tag += nimm
                rest -= nimm
            termin = _datum(a.get("termin"))
            if rest > 1e-9:                # passt nicht mehr in den Horizont
                spaeter[m] = spaeter.get(m, 0.0) + rest
                fertig = lieferbar = None
                puffer, risiko = None, (UEBER if termin else OHNE)
            else:
                fertig = stuecke[-1][0] if stuecke else heute
                lieferbar = _spaeter(aus, m, fertig, vorlauf, szenario) if vorlauf > 0 else fertig
                if termin is None:
                    puffer, risiko = None, OHNE
                else:
                    puffer = _arbeitstage(aus, m, lieferbar, termin, szenario)
                    risiko = UEBER if lieferbar > termin else KNAPP if puffer < schwelle else OK
            ergebnis.append(dict(a, start=stuecke[0][0] if stuecke else None, fertig=fertig, lieferbar=lieferbar,
                                 puffer=puffer, risiko=risiko, stuecke=stuecke, termin_datum=termin))
    zahl = {s: sum(1 for a in ergebnis if a["risiko"] == s and a["art"] == AUFTRAG) for s in (OK, KNAPP, UEBER, OHNE)}
    return dict(maschinen=maschinen, tage=tage, heute=heute, kapazitaet=kap, belegt=belegt, woche=woche,
                wochen_kap=wochen_kap, spaeter=spaeter, auftraege=ergebnis, risiko=zahl,
                szenario=szenario if szenario is not None and not szenario.leer() else None)


def wochenwerte(aus, ein, m, montag_):
    """Eingelastete Stunden einer Woche: (Aufträge, gewichtete Angebote, Kapazität). Die Kapazität der laufenden
    Woche zählt ab heute (vergangene Tage sind nicht mehr planbar)."""
    w = ein["woche"].get((m, montag_), {})
    return w.get(AUFTRAG, 0.0), w.get(ANGEBOT, 0.0), ein["wochen_kap"].get((m, montag_), 0.0)


def terminwerte(aus, m, schluessel):
    """Bedarf einer Spalte der Terminwochen-Sicht: (Aufträge, gewichtete Angebote)."""
    liste = aus["auftraege"].get((m, schluessel), ())
    return (sum(a["h"] for a in liste if a["art"] != ANGEBOT), sum(a["h"] for a in liste if a["art"] == ANGEBOT))


def kritische(ein, nur_auftraege=True):
    """Aufträge mit Terminrisiko knapp oder überschritten, dringendste zuerst."""
    liste = [a for a in ein["auftraege"] if a["risiko"] in (KNAPP, UEBER) and (a["art"] == AUFTRAG or not nur_auftraege)]
    return sorted(liste, key=lambda a: (a["risiko"] != UEBER, a["puffer"] if a["puffer"] is not None else -999,
                                        str(a.get("termin") or "")))


def gemessen(db, heute=None, wochen=4, aus=None):
    """Gemessene Laserstunden vergangener Wochen aus den Scans „Laser Start“ / „Laser Ende“ (H4b):
    dict(montage=[Montag …] (die letzten wochen vor dieser Woche, älteste zuerst), stunden={(m, Montag): h},
    kapazitaet={(m, Montag): h}, laeufe=Anzahl). Ein Lauf zählt in der Woche seines Starts, auf der Maschine des
    Angebots."""
    from . import etiketten
    heute = heute or datetime.date.today()
    m0 = _montag(heute)
    montage = [m0 - datetime.timedelta(weeks=i) for i in range(max(0, int(wochen)), 0, -1)]
    stunden, laeufe = {}, 0
    if montage:
        maschine = {}
        offen = {}
        for aid, schritt, am in db.con.execute(
                "SELECT angebot_id, schritt, am FROM rueckmeldungen WHERE schritt IN (?, ?) AND am >= ? "
                "ORDER BY angebot_id, am, id", (etiketten.LASER_START, etiketten.LASER_ENDE, montage[0].isoformat())):
            try:
                t = datetime.datetime.fromisoformat(str(am))
            except (TypeError, ValueError):
                continue
            if schritt == etiketten.LASER_START:
                offen.setdefault(aid, t)
            elif aid in offen and t > offen[aid]:
                start = offen.pop(aid)
                mo = _montag(start.date())
                if mo in montage:
                    if aid not in maschine:
                        maschine[aid] = (db.angebot(aid) or {}).get("maschine") or "?"
                    key = (maschine[aid], mo)
                    stunden[key] = stunden.get(key, 0.0) + (t - start).total_seconds() / 3600
                    laeufe += 1
    kap = {}
    if aus is not None:
        for m in aus["maschinen"]:
            for mo in montage:
                kap[(m, mo)] = sum(tagesstunden(aus, m, mo + datetime.timedelta(days=i)) for i in range(6))
    return dict(montage=montage, stunden=stunden, kapazitaet=kap, laeufe=laeufe)


def frei_bis(aus, ein, m, bis):
    """Freie Stunden der Maschine m von heute bis einschließlich bis (Angebotskopf, Kachel)."""
    return sum(max(0.0, ein["kapazitaet"][(m, d)] - sum(ein["belegt"].get((m, d), {}).values()))
               for d in ein["tage"] if d <= bis and (m, d) in ein["kapazitaet"])


def andere_maschine(db, angebot_id, maschine):
    """Laserstunden des Angebots auf einer anderen Maschine (für das Szenario); None, wenn nicht rechenbar."""
    from . import auslastung
    a = db.angebot(angebot_id) or {}
    try:
        vorher = auslastung.maschinenzeit_je(db, a)
        if len(vorher) <= 1:
            h, fertig = auslastung.maschinenzeit(db, dict(a, maschine=maschine))
            return None if h is None else h * (1 - fertig)
        # Maschine je Position: nur der Teil des Kopfs wandert; Positionen, die schon auf der neuen Maschine stehen,
        # bleiben ihr eigener Teil
        nachher = auslastung.maschinenzeit_je(db, dict(a, maschine=maschine))
    except Exception:
        return None
    if maschine not in nachher:
        return None
    h, fertig = nachher[maschine]
    h0, fertig0 = vorher.get(maschine, (0.0, 0.0))
    return max(0.0, h * (1 - fertig) - h0 * (1 - fertig0))
