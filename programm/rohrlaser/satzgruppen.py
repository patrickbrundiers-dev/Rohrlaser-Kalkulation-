"""Sätze in Positionsliste und Kalkulation abheben (Patrick 27.10.2026): die Positionen eines Satzes stehen
zusammen, haben je Satz eine eigene Tönung (reihum sechs Farben, 04.11.2026), am Zeilenkopf eine Klammer (▾ │ └) und
lassen sich wie eine Schweißbaugruppe zuklappen. Schweißbaugruppen und ihre Teile haben ihre eigene Gruppierung
(baugruppe.gruppen_reihenfolge) und bleiben hier außen vor. Nur die Anzeige; Rechnung und PDF bleiben unverändert."""

# Farben im Theme „Hell“ (Dunkel über stil.UMSETZUNG): Fläche der Zeilen und Schrift des Satznamens je Tönung.
# Tönung 0 … TOENE-1 = Sätze, reihum je Satz eine eigene Farbe (Patrick 04.11.2026: „Farben kommen bei mir nicht an,
# alle gleiche Farbe“: vorher nur Blau/Violett im Wechsel und so blass, dass es fast weiß aussah);
# BG = Schweißbaugruppen (Grün, Patrick 03.11.2026).
FLAECHEN = ("#C7DAF3", "#FAD9BD", "#DDCDF1", "#C6E8E2", "#F5CEDA", "#E2EAC0", "#CDE8CF")
TEXTE = ("#1F4E8C", "#8A4300", "#5B2E91", "#0F6359", "#8E2049", "#4F5E10", "#2E6B30")
NAMEN = ("Blau", "Orange", "Violett", "Türkis", "Rosa", "Oliv", "Grün")
TOENE = 6
BG = 6
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
    """{Index: dict(name, ton, erste, letzte, teile, saetze)} je Position eines Satzes; ton 0 … TOENE-1 reihum je Satz."""
    out = {}
    for nr, (n, ix) in enumerate(gruppen.items()):
        menge = anzahl_saetze(positionen[ix[0]])
        for k, i in enumerate(ix):
            out[i] = dict(name=n, ton=nr % TOENE, erste=k == 0, letzte=k == len(ix) - 1, teile=len(ix), saetze=menge)
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
    'satz_ton' (0 … TOENE-1 Satz, BG Schweißbaugruppe, None sonst) und 'zeile' (Index der Position). Die Zeile einer
    Schweißbaugruppe zeigt „⚙ Name“, ihre Einzelteile den Namen der Baugruppe (Patrick 03.11.2026). Zeilen ohne
    Kalkulation (None) bleiben None."""
    gruppen = saetze(positionen, ausgenommen(positionen))
    ton = {n: nr % TOENE for nr, n in enumerate(gruppen)}
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


# ------------------------------------------------------------------ Kopfband je Satz (Patrick 04.11.2026)
def _eur(w):
    from .stammdaten import zahl_als_text
    return f"{zahl_als_text(float(w), 2)} €"


def _zahl(w, stellen):
    from .stammdaten import zahl_als_text
    return zahl_als_text(round(float(w), stellen), stellen)


def kopf_baender(positionen, zeilen=None, satz_zu=(), bg_zu=(), flaeche=None):
    """Kopfband über der ersten Zeile jedes Satzes und jeder Schweißbaugruppe: {Index: dict(titel, info, flaeche,
    text, art, name)}. zeilen = rechnen.kalkulation-Zeilen (gleiche Reihenfolge, für die Preise; None = ohne Preise),
    satz_zu / bg_zu = zugeklappte Sätze (Namen) bzw. Baugruppen (IDs), flaeche = {Satz: satz_flaeche.mengen}.

    Satz:        ▾ Regal R1   5 Sätze · 4 Positionen · 16 Teile je Satz · 2,65 m² · 61,8 kg je Satz · 142,30 € je
                 Satz · 711,50 € gesamt
    Baugruppe:   ▾ ⚙ Gestell G1   2 Stk. · 4 Einzelteile · 15,75 € je Stück · 31,50 € gesamt (mit Einzelteilen)"""
    from . import baugruppe
    zeilen = zeilen or [None] * len(positionen)
    flaeche = flaeche or {}

    def preis(ix, je):
        if any(not (zeilen[i] if i < len(zeilen) else None) for i in ix):
            return None, None
        teil = sum(float(zeilen[i].get("preis_teil") or 0) * je.get(i, 1) for i in ix)
        return teil, sum(float(zeilen[i].get("preis_position") or 0) for i in ix)

    out = {}
    gruppen = saetze(positionen, ausgenommen(positionen))
    for nr, (n, ix) in enumerate(gruppen.items()):
        from . import satz_menge
        je = {i: satz_menge.je_satz(positionen[i]) for i in ix}
        menge = anzahl_saetze(positionen[ix[0]])
        teile = [f"{menge} {'Satz' if menge == 1 else 'Sätze'}" if menge else "",
                 f"{len(ix)} {'Position' if len(ix) == 1 else 'Positionen'}",
                 f"{_zahl(sum(je.values()), 0)} Teile je Satz"]
        m = flaeche.get(n)
        if m and (m.get("flaeche") or m.get("gewicht")):
            teile.append(f"{_zahl(m['flaeche'], 2)} m² · {_zahl(m['gewicht'], 1)} kg je Satz")
        je_satz, gesamt = preis(ix, je)
        if je_satz is not None:
            teile += [f"{_eur(je_satz)} je Satz", f"{_eur(gesamt)} gesamt"]
        ton = nr % TOENE
        out[ix[0]] = dict(titel=("▸ " if n in satz_zu else "▾ ") + n, info=" · ".join(t for t in teile if t),
                          flaeche=FLAECHEN[ton], text=TEXTE[ton], art="satz", name=n)
    for bg_id, (i, _) in baugruppe.baugruppen(positionen).items():
        ix = baugruppe.teile(positionen, bg_id)
        n = baugruppe.name(positionen[i])
        stk = positionen[i].get("stueck")
        stk = stk if isinstance(stk, (int, float)) and not isinstance(stk, bool) and stk > 0 else None
        teile = [f"{_zahl(stk, 0)} Stk." if stk else "", f"{len(ix)} Einzelteile"]
        _, gesamt = preis([i] + ix, {})
        if gesamt is not None:
            if stk:
                teile.append(f"{_eur(gesamt / stk)} je Stück")
            teile.append(f"{_eur(gesamt)} gesamt (mit Einzelteilen)")
        out[i] = dict(titel=("▸ " if bg_id in bg_zu else "▾ ") + "⚙ " + n, info=" · ".join(t for t in teile if t),
                      flaeche=FLAECHEN[BG], text=TEXTE[BG], art="bg", name=n, bg_id=bg_id)
    return out
