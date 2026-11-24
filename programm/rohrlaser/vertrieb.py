"""Vertriebs-Kennzahlen (Vorschläge 11.11.2026 nach der Recherche bei anderen Anbietern, Freigabe „Alle Empfehlungen“).

V1 Reaktionszeit: Eingang der Anfrage (Anfrage-Karte, angebote.zusatz 'anfrage_eingang') bis zum ersten Versand
   (Versandverlauf mit Uhrzeit 'zeit', ab 0.9.292), in Stunden an Arbeitstagen (Wochenende und Feiertage zählen
   nicht). Startseite: Mittel der letzten 30 Tage; Angebots-Auswertung: Trefferquote je Reaktionszeit.
V2 Wichtigste Anfragen zuerst (Einstellung anfragen_sortierung): erwarteter Auftragswert = Trefferquote des Kunden ×
   sein üblicher Angebotswert (Median); dringende Anfragen (Ampel rot) bleiben oben.
V3 Stille Stammkunden: Kunden mit mindestens STILL_AB Aufträgen, deren letzter Auftrag länger als STILL_FAKTOR × der
   übliche Abstand (Median) zurückliegt (mindestens STILL_MIN_TAGE); je Kunde ausblendbar.
V5 Trefferquote nach Teilemerkmalen: Profilform, Wand, Teilelänge, Innenkonturen je Teil und Stückzahl je Angebot.
Ohne Qt."""
import datetime
import json
import statistics

REAKTION_KLASSEN = ((4, "bis 4 Std."), (24, "bis 1 Arbeitstag"), (72, "1 bis 3 Arbeitstage"), (None, "länger"))
REAKTION_TAGE = 30
STILL_AB = 3                # so viele Aufträge mindestens
STILL_FAKTOR = 2.0          # letzter Auftrag länger her als so viel mal der übliche Abstand
STILL_MIN_TAGE = 30         # und mindestens so viele Tage
STILL_AUS = "stille_kunden_aus"         # Einstellung: JSON {Kundennr: ausgeblendet bis (ISO-Datum)}
SORT_DRINGLICH, SORT_WICHTIG = "Dringlichkeit", "Wichtigste zuerst"
SORTIERUNGEN = (SORT_DRINGLICH, SORT_WICHTIG)


def _datum(text):
    try:
        return datetime.date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


def _zeit(text):
    try:
        z = datetime.datetime.fromisoformat(str(text or ""))
    except ValueError:
        return None
    return z.replace(tzinfo=None) if z.tzinfo else z


def _betrag(z):
    v = z.get("vk_netto")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _vorgang(z):
    from .cockpit import _vorgang
    return _vorgang(z)


def _z(w, stellen=0):
    return f"{w:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


# ------------------------------------------------------------------ V1 Reaktionszeit
def arbeitsstunden(von, bis, land=None):
    """Stunden zwischen zwei Zeitpunkten, nur an Arbeitstagen (feiertage.ist_arbeitstag)."""
    from . import feiertage
    if not von or not bis or bis <= von:
        return 0.0
    h, t = 0.0, von
    while t < bis:
        ende = min(bis, datetime.datetime.combine(t.date() + datetime.timedelta(days=1), datetime.time()))
        if feiertage.ist_arbeitstag(t.date(), land):
            h += (ende - t).total_seconds() / 3600
        t = ende
    return h


def erster_versand(versand):
    """Zeitpunkt des ersten Versands mit Uhrzeit (Angebots-PDF, „als verschickt markiert“, E-Mail) oder None."""
    zeiten = []
    for e in versand or ():
        if isinstance(e, dict) and e.get("art") in (None, "mail") and e.get("zeit"):
            z = _zeit(e["zeit"])
            if z:
                zeiten.append(z)
    return min(zeiten) if zeiten else None


def reaktion(eingang, versand, land=None):
    """Reaktionszeit in Stunden an Arbeitstagen oder None (Eingang oder Versand mit Uhrzeit fehlt)."""
    e, v = _zeit(eingang), erster_versand(versand)
    if not e or not v or v < e:
        return None
    return arbeitsstunden(e, v, land)


def klasse(h):
    for grenze, text in REAKTION_KLASSEN:
        if grenze is None or h <= grenze + 1e-9:
            return text
    return REAKTION_KLASSEN[-1][1]


def reaktionen(zeilen, eingaenge, land=None):
    """{Angebots-ID: Stunden} der eigenen Angebote mit Eingang und Versand."""
    out = {}
    for z in zeilen:
        if z.get("fremd") or z.get("ersetzt_durch") or z.get("id") not in eingaenge:
            continue
        h = reaktion(eingaenge[z["id"]], z.get("versand"), land)
        if h is not None:
            out[z["id"]] = h
    return out


def stunden_text(h):
    return f"{_z(h, 1)} Std." if h < 24 else f"{_z(h / 24, 1)} Arbeitstage"


def reaktion_kennzahl(zeilen, eingaenge, land=None, heute=None, tage=REAKTION_TAGE):
    """dict(mittel, median, n) der Angebote mit Datum in den letzten tage Tagen oder None."""
    heute = heute or datetime.date.today()
    ab = heute - datetime.timedelta(days=tage)
    r = reaktionen([z for z in zeilen if ab <= (_datum(z.get("datum")) or heute) <= heute], eingaenge, land)
    if not r:
        return None
    w = list(r.values())
    return dict(mittel=sum(w) / len(w), median=statistics.median(w), n=len(w))


def eingang_merken(db, angebot_id, eingang):
    """Eingang der Anfrage am neuen Angebot merken (Anfrage-Karte)."""
    if eingang:
        db.zusatz_setzen(angebot_id, "anfrage_eingang", eingang.replace(microsecond=0).isoformat())


# ------------------------------------------------------------------ V5 Teilemerkmale
WAND_KLASSEN = ((2.0, "Wand bis 2 mm"), (4.0, "Wand über 2 bis 4 mm"), (None, "Wand über 4 mm"))
LAENGE_KLASSEN = ((1000, "Länge bis 1 m"), (3000, "Länge über 1 bis 3 m"), (None, "Länge über 3 m"))
KONTUR_KLASSEN = ((0, "keine Innenkonturen"), (5, "1 bis 5 Konturen"), (20, "6 bis 20 Konturen"),
                  (None, "über 20 Konturen"))
STUECK_KLASSEN = ((10, "bis 10 Stück"), (100, "11 bis 100 Stück"), (1000, "101 bis 1.000 Stück"),
                  (None, "über 1.000 Stück"))
OHNE = "ohne Angabe"
MERKMALE = (("form", "Je Profilform"), ("wand", "Je Wandstärke"), ("laenge", "Je Teilelänge"),
            ("konturen", "Je Komplexität"), ("stueck", "Je Stückzahl"))


def _klasse(w, klassen):
    if w is None:
        return OHNE
    for grenze, text in klassen:
        if grenze is None or w <= grenze + 1e-9:
            return text
    return klassen[-1][1]


def merkmale(positionen_je_angebot, k):
    """{Angebots-ID: {form, wand, laenge, konturen, stueck}} als Klassentexte aus den Positionen
    {ID: [Position]} (nur Rohrlaserteile; Größtwert je Angebot, Stückzahl als Summe)."""
    from .angebotsregeln import konturen
    out = {}
    for aid, liste in positionen_je_angebot.items():
        formen, waende, laengen, kont, stueck = set(), [], [], [], 0
        for p in liste:
            if p.get("art") not in (None, "", "Rohrlaserteil"):
                continue
            pr = k.profile.get(p.get("profil_id")) or {}
            if pr.get("form"):
                formen.add(pr["form"])
            if isinstance(pr.get("wand"), (int, float)):
                waende.append(pr["wand"])
            if isinstance(p.get("laenge"), (int, float)):
                laengen.append(p["laenge"])
            kont.append(konturen(p))
            stueck += int(p.get("stueck") or 0)
        if not (formen or laengen or stueck):
            continue
        out[aid] = dict(form=formen.pop() if len(formen) == 1 else "gemischt" if formen else OHNE,
                        wand=_klasse(max(waende) if waende else None, WAND_KLASSEN),
                        laenge=_klasse(max(laengen) if laengen else None, LAENGE_KLASSEN),
                        konturen=_klasse(max(kont) if kont else None, KONTUR_KLASSEN),
                        stueck=_klasse(stueck or None, STUECK_KLASSEN))
    return out


def reihenfolge(merkmal):
    """Anzeigereihenfolge der Klassen eines Merkmals (Profilform: nach Anzahl)."""
    klassen = {"wand": WAND_KLASSEN, "laenge": LAENGE_KLASSEN, "konturen": KONTUR_KLASSEN,
               "stueck": STUECK_KLASSEN}.get(merkmal)
    return [t for _, t in klassen] + [OHNE] if klassen else None


# ------------------------------------------------------------------ V2 Wichtigste Anfragen zuerst
def kunden_werte(zeilen):
    """{Kundennr: dict(quote, ueblich, n)} aus der Angebotsliste: Trefferquote (geglättet zur Gesamtquote) und
    Median der Angebotswerte (beauftragte, sonst alle)."""
    eigene = [z for z in zeilen if not z.get("fremd") and not z.get("ersetzt_durch") and z.get("kundennr")]
    ja = sum(1 for z in eigene if _vorgang(z) == "Beauftragt")
    nein = sum(1 for z in eigene if _vorgang(z) == "Abgelehnt")
    q0 = (ja + 1) / (ja + nein + 2)
    je = {}
    for z in eigene:
        je.setdefault(str(z["kundennr"]), []).append(z)
    out = {}
    for nr, liste in je.items():
        b = [z for z in liste if _vorgang(z) == "Beauftragt"]
        n = len(b) + sum(1 for z in liste if _vorgang(z) == "Abgelehnt")
        werte = [_betrag(z) for z in b if _betrag(z) > 0] or [_betrag(z) for z in liste if _betrag(z) > 0]
        out[nr] = dict(quote=(len(b) + 3 * q0) / (n + 3), ueblich=statistics.median(werte) if werte else 0.0, n=n)
    return out


def wichtigkeit(werte, kundennr):
    """(erwarteter Wert €, Text) einer Anfrage; ohne bekannten Kunden (0, '')."""
    w = werte.get(str(kundennr)) if kundennr else None
    if not w or not w["ueblich"]:
        return 0.0, ""
    return w["quote"] * w["ueblich"], (f"Kunde vergibt ca. {100 * w['quote']:.0f} %, üblich "
                                       f"{_z(w['ueblich'])} €")


def sortieren(anfragen_, werte, ampeln=None):
    """Anfragen „Wichtigste zuerst“: gesperrte ans Ende, dann rote Ampel, dann nach erwartetem Wert."""
    ampeln = ampeln or {}

    def schluessel(a):
        stufe = (ampeln.get(a.schluessel) or (None,))[0]
        return (bool(a.gesperrt), stufe != "rot", -wichtigkeit(werte, a.kunde)[0])
    return sorted(anfragen_, key=schluessel)


# ------------------------------------------------------------------ V3 Stille Stammkunden
def ausgeblendet(einst_wert, heute=None):
    heute = heute or datetime.date.today()
    try:
        d = json.loads(einst_wert) if einst_wert else {}
    except (TypeError, ValueError):
        d = {}
    return {k for k, bis in (d.items() if isinstance(d, dict) else ()) if (_datum(bis) or heute) >= heute}


def stille_kunden(zeilen, heute=None, aus=()):
    """[dict(kundennr, kunde, abstand (Tage, Median), seit (Tage), letzter (Datum), auftraege)] nach Dringlichkeit."""
    heute = heute or datetime.date.today()
    je = {}
    for z in zeilen:
        if z.get("fremd") or z.get("ersetzt_durch") or not z.get("kundennr") or _vorgang(z) != "Beauftragt":
            continue
        d = _datum(z.get("datum"))
        if d and d <= heute:
            je.setdefault(str(z["kundennr"]), (z.get("kunde") or "", set()))[1].add(d)
    out = []
    for nr, (name, tage) in je.items():
        if nr in aus or len(tage) < STILL_AB:
            continue
        folge = sorted(tage)
        abstand = statistics.median((b - a).days for a, b in zip(folge, folge[1:]))
        seit = (heute - folge[-1]).days
        if abstand > 0 and seit > max(STILL_FAKTOR * abstand, STILL_MIN_TAGE):
            out.append(dict(kundennr=nr, kunde=name, abstand=abstand, seit=seit, letzter=folge[-1],
                            auftraege=len(folge)))
    return sorted(out, key=lambda s: -s["seit"] / s["abstand"])


def _wochen(tage):
    return f"{tage / 7:.0f} Wochen" if tage >= 14 else f"{tage:.0f} Tage"


def still_text(s):
    return (f"{s['kunde'] or s['kundennr']}: bestellt sonst etwa alle {_wochen(s['abstand'])}, letzter Auftrag vor "
            f"{_wochen(s['seit'])} ({s['letzter']:%d.%m.%Y}, {s['auftraege']} Aufträge)")


def nachfass_text(kunde, artikel, absender=""):
    """Text der Nachfass-Mail an einen still gewordenen Kunden."""
    from .angebot_mail import anrede
    zeilen = [anrede(kunde), "", "wir haben länger nichts mehr voneinander gehört und wollten nachfragen, ob bei Ihnen "
              "wieder Laserteile anstehen."]
    if artikel:
        zeilen += ["", "Zuletzt haben wir für Sie unter anderem gefertigt:"] + [f"- {a}" for a in artikel]
    zeilen += ["", "Gern machen wir Ihnen kurzfristig ein Angebot, auch für Wiederholteile zum bekannten Stand.", "",
               "Mit freundlichen Grüßen"]
    if absender:
        zeilen.append(absender)
    return "\n".join(zeilen)


def letzte_artikel(db, kundennr, anzahl=5):
    """Artikel bzw. Bezeichnungen der zuletzt beauftragten Positionen des Kunden."""
    out = []
    for r in db.con.execute(
            "SELECT p.artikel, p.bezeichnung, p.profil_id FROM positionen p JOIN angebote a ON a.id = p.angebot_id "
            "WHERE a.kundennr=? AND a.vorgang='Beauftragt' ORDER BY a.datum DESC, p.nr", (str(kundennr),)):
        t = " ".join(str(x) for x in (r[0], r[1]) if x) or (r[2] or "")
        if t and t not in out:
            out.append(t)
        if len(out) >= anzahl:
            break
    return out
