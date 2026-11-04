"""Sätze in Positionsliste und Kalkulation abheben (Patrick 27.10.2026): die Positionen eines Satzes stehen
zusammen, haben je Satz eine eigene Tönung (abwechselnd Blau und Violett), am Zeilenkopf eine Klammer (▾ │ └) und
lassen sich wie eine Schweißbaugruppe zuklappen. Schweißbaugruppen und ihre Teile haben ihre eigene Gruppierung
(baugruppe.gruppen_reihenfolge) und bleiben hier außen vor. Nur die Anzeige; Rechnung und PDF bleiben unverändert."""

# Farben im Theme „Hell“ (Dunkel über stil.UMSETZUNG): Fläche der Zeilen und Schrift des Satznamens je Tönung;
# Tönung 0/1 = Sätze (Blau/Violett abwechselnd), BG = Schweißbaugruppen (Grün, Patrick 03.11.2026)
FLAECHEN = ("#E4EEFA", "#EEE6F7", "#E2F2E4")
TEXTE = ("#285F9E", "#6E3FA3", "#2E6B30")
BG = 2
ANTEIL = 0.85           # so viel Tönung über der Zellfarbe (Eingabe- und berechnete Zellen bleiben unterscheidbar)


def name(p):
    return str((p or {}).get("satz") or "").strip()


def ausgenommen(positionen):
    """Indizes der Schweißbaugruppen und ihrer Teile (eigene Gruppierung)."""
    from . import baugruppe
    _, zu = baugruppe.gruppen_reihenfolge(positionen)
    return set(zu) | {i for i, _ in baugruppe.baugruppen(positionen).values()}


def saetze(positionen, aus=()):
    """{Satzname: [Indizes]} der Positionen mit Satz, Reihenfolge des ersten Auftretens; Indizes in aus (Schweiß-
    baugruppen und ihre Teile) zählen nicht."""
    out = {}
    for i, p in enumerate(positionen):
        n = name(p)
        if n and i not in aus:
            out.setdefault(n, []).append(i)
    return out


def ordnen(folge, gruppen):
    """Anzeige-Reihenfolge: die übrigen Positionen eines Satzes direkt unter seiner ersten (sonst wie folge)."""
    erste = {ix[0]: ix for ix in gruppen.values()}
    rest = {i for ix in gruppen.values() for i in ix[1:]}
    out = []
    for i in folge:
        if i in rest:
            continue
        out.append(i)
        out += erste.get(i, [])[1:]
    return out


def anzahl_saetze(p):
    """Anzahl Sätze wie in der Rechnung (rechnen.saetze_von: Stück je Satz leer = 1), gerundet; None ohne Stückzahl."""
    from . import rechnen
    n = rechnen.saetze_von(p)
    return round(n) if n else None


def info(positionen, gruppen):
    """{Index: dict(name, ton, erste, letzte, teile, saetze)} je Position eines Satzes; ton 0/1 wechselt je Satz."""
    out = {}
    for nr, (n, ix) in enumerate(gruppen.items()):
        menge = anzahl_saetze(positionen[ix[0]])
        for k, i in enumerate(ix):
            out[i] = dict(name=n, ton=nr % 2, erste=k == 0, letzte=k == len(ix) - 1, teile=len(ix), saetze=menge)
    return out


def kopf_texte(gruppen, zu=()):
    """Zeilenkopf {Index: Text}: ▾ (▸ zugeklappt) an der ersten Position, │ dazwischen, └ an der letzten; ein Satz
    mit nur einer Position bekommt keine Klammer."""
    out = {}
    for n, ix in gruppen.items():
        if len(ix) < 2:
            continue
        out[ix[0]] = ("▸ " if n in zu else "▾ ") + str(ix[0] + 1)
        for i in ix[1:-1]:
            out[i] = "│ " + str(i + 1)
        out[ix[-1]] = "└ " + str(ix[-1] + 1)
    return out


def zelltext(s, zu=False):
    """Text der Spalte Satz: an der ersten Position Name und Anzahl Sätze (zugeklappt mit Anzahl Teile), sonst der
    Name."""
    if not s["erste"]:
        return s["name"]
    t = "▣ " + s["name"]
    if s["saetze"]:
        t += f" · {s['saetze']} {'Satz' if s['saetze'] == 1 else 'Sätze'}"
    if zu and s["teile"] > 1:
        t += f" · {s['teile']} Positionen"
    return t


def bg_info(positionen, zu=()):
    """{Index: dict(name, ton=BG, erste, letzte, teile, saetze, bg=True, zu)} für jede Schweißbaugruppe (erste Zeile)
    und ihre Einzelteile; saetze = Anzahl Baugruppen, teile = Anzahl Einzelteile; zu = Baugruppen-IDs zugeklappt."""
    from . import baugruppe
    out = {}
    for bg_id, (i, _) in baugruppe.baugruppen(positionen).items():
        ix = [i] + baugruppe.teile(positionen, bg_id)
        n = baugruppe.name(positionen[i])
        menge = positionen[i].get("stueck")
        for k, j in enumerate(ix):
            out[j] = dict(name=n, ton=BG, erste=k == 0, letzte=k == len(ix) - 1, teile=len(ix) - 1,
                          saetze=round(menge) if isinstance(menge, (int, float)) and menge else None, bg=True,
                          zu=bg_id in zu)
    return out


def bg_zelltext(s, zu=False):
    """Spalte Satz einer Schweißbaugruppe: an der Baugruppe ⚙ Name und Anzahl, sonst der Name."""
    if not s["erste"]:
        return s["name"]
    t = "⚙ " + s["name"]
    if s["saetze"]:
        t += f" · {s['saetze']} Stk."
    if zu and s["teile"]:
        t += f" · {s['teile']} Einzelteile"
    return t


def kurz(text, laenge=34):
    """Statustext für die Liste kürzen (ganzer Text im Tooltip): an einer Wortgrenze mit …"""
    text = str(text or "")
    if len(text) <= laenge:
        return text
    t = text[:laenge - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return t + " …"


def mischen(unten, oben, anteil=ANTEIL):
    """Farbe oben mit Anteil über unten (QColor)."""
    from PySide6.QtGui import QColor
    return QColor(*(round(a * (1 - anteil) + b * anteil) for a, b in ((unten.red(), oben.red()),
                                                                       (unten.green(), oben.green()),
                                                                       (unten.blue(), oben.blue()))))


def zeilen_markieren(positionen, zeilen):
    """Kalkulationszeilen (gleiche Reihenfolge wie positionen) mit Satz und Tönung ergänzen: Schlüssel 'satz',
    'satz_ton' (0/1 Satz, BG Schweißbaugruppe, None sonst) und 'zeile' (Index der Position). Die Zeile einer
    Schweißbaugruppe zeigt „⚙ Name“, ihre Einzelteile den Namen der Baugruppe (Patrick 03.11.2026). Zeilen ohne
    Kalkulation (None) bleiben None."""
    gruppen = saetze(positionen, ausgenommen(positionen))
    ton = {n: nr % 2 for nr, n in enumerate(gruppen)}
    in_satz = {i for ix in gruppen.values() for i in ix}
    bgi = bg_info(positionen)
    out = []
    for i, (p, z) in enumerate(zip(positionen, zeilen)):
        if z is not None:
            if i in bgi:
                b = bgi[i]
                z = dict(z, satz=("⚙ " if b["erste"] else "") + b["name"], satz_ton=BG, zeile=i)
                if b["erste"] and not z.get("artikel"):
                    z["artikel"] = p.get("artikel") or b["name"]
            else:
                n = name(p) if i in in_satz else ""
                z = dict(z, satz=n, satz_ton=ton.get(n), zeile=i)
        out.append(z)
    return out


def anzeige_folge(positionen):
    """Indizes in der Reihenfolge der Positionsliste (Baugruppe mit Einzelteilen, Sätze zusammen)."""
    from . import reihenfolge
    return reihenfolge.anzeige(positionen)
