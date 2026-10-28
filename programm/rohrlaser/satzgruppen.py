"""Sätze in Positionsliste und Kalkulation abheben (Patrick 27.10.2026): die Positionen eines Satzes stehen
zusammen, haben je Satz eine eigene Tönung (abwechselnd Blau und Violett), am Zeilenkopf eine Klammer (▾ │ └) und
lassen sich wie eine Schweißbaugruppe zuklappen. Schweißbaugruppen und ihre Teile haben ihre eigene Gruppierung
(baugruppe.gruppen_reihenfolge) und bleiben hier außen vor. Nur die Anzeige; Rechnung und PDF bleiben unverändert."""

# Farben im Theme „Hell“ (Dunkel über stil.UMSETZUNG): Fläche der Zeilen und Schrift des Satznamens je Tönung
FLAECHEN = ("#E4EEFA", "#EEE6F7")
TEXTE = ("#285F9E", "#6E3FA3")
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


def mischen(unten, oben, anteil=ANTEIL):
    """Farbe oben mit Anteil über unten (QColor)."""
    from PySide6.QtGui import QColor
    return QColor(*(round(a * (1 - anteil) + b * anteil) for a, b in ((unten.red(), oben.red()),
                                                                       (unten.green(), oben.green()),
                                                                       (unten.blue(), oben.blue()))))


def zeilen_markieren(positionen, zeilen):
    """Kalkulationszeilen (gleiche Reihenfolge wie positionen) mit Satz und Tönung ergänzen: Schlüssel 'satz' und
    'satz_ton' (0/1, None ohne Satz). Zeilen ohne Kalkulation (None) bleiben None."""
    gruppen = saetze(positionen, ausgenommen(positionen))
    ton = {n: nr % 2 for nr, n in enumerate(gruppen)}
    out = []
    for p, z in zip(positionen, zeilen, strict=True):
        if z is not None:
            i = len(out)
            n = name(p) if any(i in ix for ix in gruppen.values()) else ""
            z = dict(z, satz=n, satz_ton=ton.get(n))
        out.append(z)
    return out
