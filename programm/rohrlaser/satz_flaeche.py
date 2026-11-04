"""Fläche und Gewicht eines ganzen Satzes (Patrick 03.11.2026: „Für pulverbeschichtet Fläche eines ganzen Satzes
berechnen und Gewicht für verzinken“, Freigabe 1a 2a 3a).

Gerechnet wird weiter je Teil (Summe gleich); hier nur die Summen je Satz für Anzeige und Belegung:
  Fläche je Satz = Σ Außenfläche je Teil × Stück je Satz (wie Pulverbeschichten €/m², rechnen.zusatz_menge_auto;
                   Bleche beide Seiten ohne Löcher),
  Gewicht je Satz = Σ Gewicht je Teil × Stück je Satz (wie Verzinken €/kg; Zukaufteile mit ihrem Gewicht).
Alle Positionen des Satzes zählen (auch Bleche und Zukaufteile), soweit Fläche bzw. Gewicht bekannt sind; die
übrigen stehen in ohne_flaeche / ohne_gewicht."""
from . import rechnen, satz_menge


def mengen(positionen, satz, k):
    """{flaeche, gewicht (je Satz), saetze, flaeche_alle, gewicht_alle, ohne_flaeche, ohne_gewicht (Pos.-Nummern)}
    des Satzes (Teile wie satz_menge.zusatz_positionen: Schweißbaugruppen im Satz mit ihren Einzelteilen, 04.11.2026)."""
    fl, kg, ohne_f, ohne_g = 0.0, 0.0, [], []
    for i, n in satz_menge.zusatz_positionen(positionen, satz):
        p = positionen[i]
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
    saetze = satz_menge.anzahl(positionen, satz) or _bg_saetze(positionen, satz) or 0
    # Arbeitsgänge einer Schweißbaugruppe des Satzes (Hinweis gegen doppelt eingetragenes Verzinken o. Ä., aus #395)
    from . import baugruppe
    ag = [str(a.get("name")) for i, bg in baugruppe.baugruppen(positionen).values()
          if satz_menge.name(positionen[i]) == satz for a in bg.get("arbeitsgaenge") or () if a.get("name")]
    return dict(flaeche=fl, gewicht=kg, saetze=saetze, flaeche_alle=fl * saetze, gewicht_alle=kg * saetze,
                ohne_flaeche=ohne_f, ohne_gewicht=ohne_g, arbeitsgaenge=ag)


def _bg_saetze(positionen, satz):
    """Anzahl Sätze aus den Schweißbaugruppen des Satzes (Satz nur aus Baugruppen), sonst None."""
    werte = [rechnen.saetze_von(p) for p in positionen if satz_menge.name(p) == satz and rechnen.ist_baugruppe(p)]
    werte = [w for w in werte if w]
    if not werte:
        return None
    w = max(werte)
    return int(w) if abs(w - round(w)) < 1e-6 else w


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
