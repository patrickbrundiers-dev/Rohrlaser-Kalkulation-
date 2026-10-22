"""Maschinenkalender und Kapazität: verfügbare Zeitfenster, Ende einer Belegung, Auslastung und Terminrisiko.

Reine Rechnung ohne Datenbank und ohne Oberfläche. Zeiten sind Ortszeit ohne Zeitzone (datetime ohne tzinfo,
als Text 'JJJJ-MM-TTTHH:MM'); bei der Zeitumstellung zählt eine Nachtschicht deshalb mit ihrer Wanduhr-Dauer.

Schichtmodell: je Maschine Zeitfenster je Wochentag (0 = Montag … 6 = Sonntag) mit Beginn und Ende ('06:00',
'14:00'); Ende ≤ Beginn heißt über Mitternacht. Pausen, in denen die Maschine steht, sind Lücken zwischen zwei
Fenstern. gueltig_ab/gueltig_bis (Datum, leer = unbegrenzt) erlauben einen Wechsel des Schichtmodells.
Ausnahmen je Tag (Maschine leer = alle): 'frei' (Feiertag, Betriebsruhe) streicht alle Fenster, die an diesem Tag
beginnen; 'zusatz' fügt ein Fenster beginn–ende hinzu. Stillstände (Wartung, Störung) sind Zeiträume, die aus den
Fenstern herausgeschnitten werden.

Kennzahlen (Bericht Abschnitt 5): geplante Auslastung = geplante Belegung ÷ verfügbare Zeit × 100, freie Kapazität =
verfügbar − geplant (negativ = überlastet), Terminrisiko aus dem Puffer zwischen geplantem Ende und Liefertermin in
Arbeitstagen. Gezählt wird nur Belegung, die in verfügbaren Fenstern liegt.
"""
import datetime

FORMAT = "%Y-%m-%dT%H:%M"
WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
RISIKEN = ("überschritten", "kritisch", "ok", "ohne Termin")


def zeit(text):
    """'2026-10-22T06:00' (auch mit Sekunden oder Leerzeichen) → datetime; None/'' → None."""
    if not text:
        return None
    if isinstance(text, datetime.datetime):
        return text.replace(second=0, microsecond=0)
    return datetime.datetime.fromisoformat(str(text).strip().replace(" ", "T")).replace(second=0, microsecond=0)


def zeit_text(t):
    return t.strftime(FORMAT) if t else None


def aufrunden(t):
    """Auf die volle Minute aufrunden (ein Ende 08:00:30 wird 08:01, damit nichts zu früh als frei gilt)."""
    if t is None or (t.second == 0 and t.microsecond == 0):
        return t
    return t.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)


def datum(text):
    if not text:
        return None
    if isinstance(text, datetime.date) and not isinstance(text, datetime.datetime):
        return text
    return datetime.date.fromisoformat(str(text).strip()[:10])


def uhrzeit(text):
    """'6:00' / '06:00' / '24:00' → Minuten seit Mitternacht."""
    h, m = str(text).strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h <= 24 and 0 <= m < 60) or h * 60 + m > 1440:
        raise ValueError(f"Ungültige Uhrzeit: {text}")
    return h * 60 + m


def minuten(a, b):
    return (b - a).total_seconds() / 60


def _gilt(z, tag):
    ab, bis = datum(z.get("gueltig_ab")), datum(z.get("gueltig_bis"))
    return (ab is None or tag >= ab) and (bis is None or tag <= bis)


def _fenster_des_tages(tag, beginn, ende):
    b, e = uhrzeit(beginn), uhrzeit(ende)
    start = datetime.datetime.combine(tag, datetime.time()) + datetime.timedelta(minutes=b)
    dauer = e - b if e > b else e + 1440 - b
    return start, start + datetime.timedelta(minutes=dauer)


def _zusammenfassen(fenster):
    out = []
    for a, b in sorted(fenster):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _abziehen(fenster, sperren):
    """Zeiträume `sperren` aus den Fenstern herausschneiden."""
    out = []
    sperren = _zusammenfassen(sperren)
    for a, b in fenster:
        teile = [(a, b)]
        for s, e in sperren:
            neu = []
            for x, y in teile:
                if e <= x or s >= y:
                    neu.append((x, y))
                    continue
                if s > x:
                    neu.append((x, s))
                if e < y:
                    neu.append((e, y))
            teile = neu
        out.extend(teile)
    return out


def verfuegbare_fenster(maschine, von, bis, schichten, ausnahmen=(), stillstaende=()):
    """Verfügbare Zeitfenster [(start, ende)] der Maschine im Zeitraum [von, bis), sortiert und überschneidungsfrei.
    schichten: [{maschine, wochentag, beginn, ende, gueltig_ab?, gueltig_bis?}], ausnahmen: [{datum, maschine?, art,
    beginn?, ende?}], stillstaende: [{maschine, beginn, ende}] (Zeiten als Text oder datetime)."""
    von, bis = zeit(von), zeit(bis)
    eigene = [z for z in schichten if z.get("maschine") == maschine]
    aus = [a for a in ausnahmen if not a.get("maschine") or a.get("maschine") == maschine]
    frei = {datum(a["datum"]) for a in aus if a.get("art") == "frei"}
    fenster = []
    tag = von.date() - datetime.timedelta(days=1)          # Nachtschicht des Vortags ragt in den Zeitraum
    while tag <= bis.date():
        if tag not in frei:
            for z in eigene:
                if int(z["wochentag"]) == tag.weekday() and _gilt(z, tag):
                    fenster.append(_fenster_des_tages(tag, z["beginn"], z["ende"]))
        for a in aus:
            if a.get("art") == "zusatz" and datum(a["datum"]) == tag and a.get("beginn") and a.get("ende"):
                fenster.append(_fenster_des_tages(tag, a["beginn"], a["ende"]))
        tag += datetime.timedelta(days=1)
    fenster = _zusammenfassen(fenster)
    sperren = [(zeit(s["beginn"]), zeit(s["ende"])) for s in stillstaende if s.get("maschine") == maschine]
    fenster = _abziehen(fenster, sperren)
    return [(max(a, von), min(b, bis)) for a, b in fenster if b > von and a < bis]


def summe(fenster):
    return sum(minuten(a, b) for a, b in fenster)


def ende_berechnen(start, dauer_min, fenster):
    """Belegung ab `start` mit `dauer_min` Minuten Maschinenzeit, verteilt auf die Fenster. Beginnt `start` außerhalb
    eines Fensters, beginnt die Belegung mit dem nächsten Fenster. Ergebnis: (Beginn, Ende) oder (Beginn, None),
    wenn die Fenster nicht reichen."""
    start = zeit(start)
    rest = float(dauer_min)
    beginn = None
    for a, b in fenster:
        if b <= start:
            continue
        a = max(a, start)
        if beginn is None:
            beginn = a
            if rest <= 0:
                return beginn, beginn
        frei = minuten(a, b)
        if rest <= frei + 1e-9:
            return beginn, a + datetime.timedelta(minutes=rest)
        rest -= frei
    return beginn or start, None


def belegte_minuten(beginn, ende, fenster, von=None, bis=None):
    """Minuten der Belegung [beginn, ende), die in den Fenstern und im Zeitraum [von, bis) liegen."""
    beginn, ende = zeit(beginn), zeit(ende)
    if von is not None:
        beginn = max(beginn, zeit(von))
    if bis is not None:
        ende = min(ende, zeit(bis))
    if ende <= beginn:
        return 0.0
    return sum(minuten(max(a, beginn), min(b, ende)) for a, b in fenster if b > beginn and a < ende)


def zeitraeume(von, bis, art):
    """Zeiträume für Kennzahlen: art 'tag', 'woche' (Montag–Sonntag, Kalenderwoche) oder 'monat'.
    Ergebnis: [(Name, Beginn, Ende)], erster und letzter Zeitraum ganz (nicht auf von/bis gekürzt)."""
    von, bis = datum(von), datum(bis)
    out = []
    if art == "tag":
        t = von
        while t <= bis:
            out.append((f"{WOCHENTAGE[t.weekday()]} {t:%d.%m.}", t, t + datetime.timedelta(days=1)))
            t += datetime.timedelta(days=1)
    elif art == "woche":
        t = von - datetime.timedelta(days=von.weekday())
        while t <= bis:
            jahr, kw, _ = t.isocalendar()
            out.append((f"KW {kw:02d}/{jahr}", t, t + datetime.timedelta(days=7)))
            t += datetime.timedelta(days=7)
    elif art == "monat":
        t = von.replace(day=1)
        while t <= bis:
            n = (t.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
            out.append((f"{t:%m/%Y}", t, n))
            t = n
    else:
        raise ValueError(f"Unbekannte Art: {art}")
    return [(n, datetime.datetime.combine(a, datetime.time()), datetime.datetime.combine(b, datetime.time()))
            for n, a, b in out]


def auslastung(maschine, von, bis, belegungen, schichten, ausnahmen=(), stillstaende=()):
    """Kennzahlen der Maschine im Zeitraum [von, bis): {verfuegbar_min, geplant_min, frei_min, auslastung (in %,
    None ohne verfügbare Zeit), ohne_schicht (True = kein Schichtmodell hinterlegt)}. belegungen: [{maschine, beginn,
    ende}] mit berechnetem Ende; Belegungen ohne Ende zählen nicht."""
    von, bis = zeit(von), zeit(bis)
    fenster = verfuegbare_fenster(maschine, von, bis, schichten, ausnahmen, stillstaende)
    verfuegbar = summe(fenster)
    geplant = sum(belegte_minuten(b["beginn"], b["ende"], fenster, von, bis) for b in belegungen
                  if b.get("maschine") == maschine and b.get("beginn") and b.get("ende"))
    return dict(verfuegbar_min=round(verfuegbar, 1), geplant_min=round(geplant, 1),
                frei_min=round(verfuegbar - geplant, 1),
                auslastung=round(geplant / verfuegbar * 100, 1) if verfuegbar else None,
                ohne_schicht=not any(z.get("maschine") == maschine for z in schichten))


def arbeitstage_zwischen(a, b, arbeitstage):
    """Anzahl Arbeitstage nach Tag a bis einschließlich Tag b (negativ, wenn b vor a liegt)."""
    a, b = datum(a), datum(b)
    if b >= a:
        return sum(1 for t in arbeitstage if a < t <= b)
    return -sum(1 for t in arbeitstage if b < t <= a)


def terminrisiko(ende, liefertermin, arbeitstage, schwelle_tage):
    """Terminrisiko einer Belegung: ('überschritten' | 'kritisch' | 'ok' | 'ohne Termin', Puffer in Arbeitstagen oder
    None). Der Liefertermin gilt bis Tagesende; arbeitstage = Menge der Tage mit verfügbarer Zeit. Ohne geplantes
    Ende (Fenster reichen nicht) gilt der Termin als überschritten."""
    lt = datum(liefertermin)
    if lt is None:
        return "ohne Termin", None
    if ende is None:
        return "überschritten", None
    ende = zeit(ende)
    tag = (ende - datetime.timedelta(minutes=1)).date() if ende.time() == datetime.time() else ende.date()
    puffer = arbeitstage_zwischen(tag, lt, arbeitstage)
    if tag > lt:
        return "überschritten", puffer
    return ("kritisch" if puffer < schwelle_tage else "ok"), puffer


def ueberschneidungen(belegungen):
    """Paare (id, id) von Belegungen derselben Maschine, deren Zeiträume sich überschneiden."""
    out = []
    nach = {}
    for b in belegungen:
        if b.get("beginn") and b.get("ende"):
            nach.setdefault(b["maschine"], []).append(b)
    for liste in nach.values():
        liste.sort(key=lambda b: zeit(b["beginn"]))
        for i, b in enumerate(liste):
            for c in liste[i + 1:]:
                if zeit(c["beginn"]) >= zeit(b["ende"]):
                    break
                out.append((b["id"], c["id"]))
    return out


def ostersonntag(jahr):
    """Gaußsche Osterformel (gregorianisch, Anonymer Algorithmus)."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat = (h + l - 7 * m + 114) // 31
    tag = (h + l - 7 * m + 114) % 31 + 1
    return datetime.date(jahr, monat, tag)


def bundesweite_feiertage(jahr):
    """Die neun gesetzlichen Feiertage, die in allen Bundesländern gelten: [(Datum, Name)]. Feiertage einzelner
    Bundesländer (z. B. Fronleichnam, Reformationstag) trägt man als Ausnahme selbst ein."""
    o = ostersonntag(jahr)
    t = datetime.timedelta
    return [(datetime.date(jahr, 1, 1), "Neujahr"), (o - t(days=2), "Karfreitag"), (o + t(days=1), "Ostermontag"),
            (datetime.date(jahr, 5, 1), "Tag der Arbeit"), (o + t(days=39), "Christi Himmelfahrt"),
            (o + t(days=50), "Pfingstmontag"), (datetime.date(jahr, 10, 3), "Tag der Deutschen Einheit"),
            (datetime.date(jahr, 12, 25), "1. Weihnachtstag"), (datetime.date(jahr, 12, 26), "2. Weihnachtstag")]
