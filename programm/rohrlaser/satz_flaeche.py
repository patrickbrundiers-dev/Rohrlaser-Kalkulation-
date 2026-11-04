"""Fläche und Gewicht eines ganzen Satzes (Patrick 03.11.2026: „Für pulverbeschichtet Fläche eines ganzen Satzes
berechnen und Gewicht für verzinken“, Freigabe 1a 2a 3a).

Gerechnet wird weiter je Teil (Summe gleich); hier nur die Summen je Satz für Anzeige und Belegung:
  Fläche je Satz = Σ Außenfläche je Teil × Stück je Satz (wie Pulverbeschichten €/m², rechnen.zusatz_menge_auto;
                   Bleche beide Seiten ohne Löcher),
  Gewicht je Satz = Σ Gewicht je Teil × Stück je Satz (wie Verzinken €/kg; Zukaufteile mit ihrem Gewicht).
Alle Positionen des Satzes zählen (auch Bleche und Zukaufteile), soweit Fläche bzw. Gewicht bekannt sind; die
übrigen stehen in ohne_flaeche / ohne_gewicht.

Schweißbaugruppe (Patrick 04.11.2026: „Satzauswahl Zusatzarbeiten funktioniert nicht“): ihr Satz ist der Name der
Baugruppe; „ganzer Satz“ sind dann ihre Einzelteile (die Zeile der Baugruppe selbst hat weder Fläche noch Gewicht),
Anzahl Sätze = Stückzahl der Baugruppe."""
from . import baugruppe, rechnen, satz_menge


def _baugruppen(positionen, satz):
    """{Baugruppen-ID: Index} der Schweißbaugruppen, deren Satz satz ist."""
    satz = str(satz or "").strip()
    return {b: i for b, (i, _) in baugruppe.baugruppen(positionen).items()
            if satz and satz_menge.name(positionen[i]) == satz}


def positionen_von(positionen, satz):
    """Indizes der Positionen, die „Zusatzarbeit für ganzen Satz“ belegt: die Positionen des Satzes
    (satz_menge.satz_positionen), bei einer Schweißbaugruppe deren Einzelteile."""
    ix = satz_menge.satz_positionen(positionen, satz)
    if ix:
        return ix
    return sorted(j for b in _baugruppen(positionen, satz) for j in baugruppe.teile(positionen, b))


def anzahl(positionen, satz):
    """Anzahl Sätze: wie satz_menge.anzahl, bei einer Schweißbaugruppe ihre Stückzahl. None ohne Stückzahl."""
    if satz_menge.satz_positionen(positionen, satz):
        return satz_menge.anzahl(positionen, satz)
    st = [positionen[i].get("stueck") for i in _baugruppen(positionen, satz).values()]
    st = [x for x in st if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0]
    return (int(st[0]) if float(st[0]).is_integer() else st[0]) if len(st) == 1 else (sum(st) or None)


def mengen(positionen, satz, k):
    """{flaeche, gewicht (je Satz), saetze, flaeche_alle, gewicht_alle, ohne_flaeche, ohne_gewicht (Pos.-Nummern)}
    des Satzes (Positionen wie positionen_von: Satzpositionen bzw. Einzelteile der Schweißbaugruppe); arbeitsgaenge =
    Namen der Arbeitsgänge einer Schweißbaugruppe (Hinweis gegen doppelt eingetragenes Verzinken o. Ä.)."""
    fl, kg, ohne_f, ohne_g = 0.0, 0.0, [], []
    for i in positionen_von(positionen, satz):
        p = positionen[i]
        n = satz_menge.je_satz(p)
        m2 = rechnen.zusatz_menge_auto("€/m²", p, k) if k is not None else None
        g = rechnen.zusatz_menge_auto("€/kg", p, k) if k is not None else None
        if isinstance(m2, (int, float)) and m2 > 0:
            fl += m2 * n
        else:
            ohne_f.append(p.get("pos"))
        if isinstance(g, (int, float)) and g > 0:
            kg += g * n
        else:
            ohne_g.append(p.get("pos"))
    saetze = anzahl(positionen, satz) or 0
    ag = [] if satz_menge.satz_positionen(positionen, satz) else [
        str(a.get("name")) for b in _baugruppen(positionen, satz)
        for a in (baugruppe.baugruppen(positionen)[b][1].get("arbeitsgaenge") or ()) if a.get("name")]
    return dict(flaeche=fl, gewicht=kg, saetze=saetze, flaeche_alle=fl * saetze, gewicht_alle=kg * saetze,
                ohne_flaeche=ohne_f, ohne_gewicht=ohne_g, arbeitsgaenge=ag)


def text(m, mit_alle=True):
    """„3,42 m² · 45,6 kg je Satz (2 Sätze: 6,84 m² · 91,2 kg)“."""
    t = f"{_zahl(m['flaeche'], 2)} m² · {_zahl(m['gewicht'], 1)} kg je Satz"
    if mit_alle and m["saetze"] and m["saetze"] != 1:
        t += f" ({m['saetze']:g} Sätze: {_zahl(m['flaeche_alle'], 2)} m² · {_zahl(m['gewicht_alle'], 1)} kg)"
    return t


def fehlt_text(m):
    """Hinweis auf Positionen ohne Fläche bzw. Gewicht, sonst ''."""
    teile = []
    if m["ohne_flaeche"]:
        teile.append("ohne Fläche: Pos. " + ", ".join(str(x) for x in m["ohne_flaeche"]))
    if m["ohne_gewicht"]:
        teile.append("ohne Gewicht: Pos. " + ", ".join(str(x) for x in m["ohne_gewicht"]))
    return "; ".join(teile)


def _zahl(w, stellen):
    return f"{w:,.{stellen}f}".replace(",", "#").replace(".", ",").replace("#", ".")
