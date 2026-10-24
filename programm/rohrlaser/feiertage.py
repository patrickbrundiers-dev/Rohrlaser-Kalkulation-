"""Gesetzliche Feiertage je Bundesland für Arbeitstage (Plan Palettenbegleitschein F10a, wie im Palettenschein-Tool
v97): Liefertermin-Vorschlag bei „Beauftragt“ und die Knöpfe +5/+10/+15 AT des Palettenscheins zählen nur Montag bis
Freitag ohne die Feiertage des Bundeslands aus der Einstellung 'versand_bundesland' (Vorgabe Nordrhein-Westfalen;
„keine Feiertage“ = nur Montag bis Freitag)."""
import datetime

KEINE = "Keine Feiertage berücksichtigen"
LAENDER = {"Baden-Württemberg": "BW", "Bayern": "BY", "Berlin": "BE", "Brandenburg": "BB", "Bremen": "HB",
           "Hamburg": "HH", "Hessen": "HE", "Mecklenburg-Vorpommern": "MV", "Niedersachsen": "NI",
           "Nordrhein-Westfalen": "NW", "Rheinland-Pfalz": "RP", "Saarland": "SL", "Sachsen": "SN",
           "Sachsen-Anhalt": "ST", "Schleswig-Holstein": "SH", "Thüringen": "TH"}
AUSWAHL = tuple(LAENDER) + (KEINE,)
VORGABE = "Nordrhein-Westfalen"

_CACHE = {}


def ostersonntag(jahr):
    """Ostersonntag nach Gauß (gregorianisch)."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    lw = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lw) // 451
    monat, tag = divmod(h + lw - 7 * m + 114, 31)
    return datetime.date(jahr, monat, tag + 1)


def feiertage(jahr, land):
    """{Datum: Name} der gesetzlichen Feiertage im Jahr; land = Name aus LAENDER (sonst keine)."""
    kz = LAENDER.get(land)
    schluessel = (jahr, kz)
    if schluessel in _CACHE:
        return _CACHE[schluessel]
    out = {}
    if kz:
        ost = ostersonntag(jahr)

        def fest(m, t, name):
            out[datetime.date(jahr, m, t)] = name

        def rel(n, name):
            out[ost + datetime.timedelta(days=n)] = name

        fest(1, 1, "Neujahr")
        if kz in ("BW", "BY", "ST"):
            fest(1, 6, "Heilige Drei Könige")
        if kz in ("BE", "MV"):
            fest(3, 8, "Internationaler Frauentag")
        rel(-2, "Karfreitag")
        rel(1, "Ostermontag")
        fest(5, 1, "Tag der Arbeit")
        rel(39, "Christi Himmelfahrt")
        rel(50, "Pfingstmontag")
        if kz in ("BW", "BY", "HE", "NW", "RP", "SL"):
            rel(60, "Fronleichnam")
        if kz == "SL":
            fest(8, 15, "Mariä Himmelfahrt")
        if kz == "TH":
            fest(9, 20, "Weltkindertag")
        fest(10, 3, "Tag der Deutschen Einheit")
        if kz in ("BB", "HB", "HH", "MV", "NI", "SN", "ST", "SH", "TH"):
            fest(10, 31, "Reformationstag")
        if kz in ("BW", "BY", "NW", "RP", "SL"):
            fest(11, 1, "Allerheiligen")
        if kz == "SN":          # Mittwoch vor dem 23. November
            d = datetime.date(jahr, 11, 22)
            out[d - datetime.timedelta(days=(d.weekday() - 2) % 7)] = "Buß- und Bettag"
        fest(12, 25, "1. Weihnachtstag")
        fest(12, 26, "2. Weihnachtstag")
    _CACHE[schluessel] = out
    return out


def name(datum, land):
    """Name des Feiertags oder ''."""
    return feiertage(datum.year, land).get(datum, "")


def ist_arbeitstag(datum, land=None):
    return datum.weekday() < 5 and not name(datum, land)


def arbeitstage_spaeter(start, n, land=None):
    """Datum n Arbeitstage nach start (Montag bis Freitag ohne Feiertage des Bundeslands)."""
    d = start
    while n > 0:
        d += datetime.timedelta(days=1)
        if ist_arbeitstag(d, land):
            n -= 1
    return d


def hinweis(datum, land=None):
    """'Samstag', 'Sonntag' oder der Feiertag, auf den das Datum fällt, sonst ''."""
    if datum is None:
        return ""
    if datum.weekday() == 5:
        return "Samstag"
    if datum.weekday() == 6:
        return "Sonntag"
    return name(datum, land)
