"""Gewinn, Marge und Aufschlag eines gerechneten Angebots an einer Stelle (Master-Prompt Angebotserstellung, Patrick
21.11.2026, Punkt 4 „Aufschlag und Marge mathematisch korrekt unterscheiden“, Punkt 11 „keine doppelten
Berechnungslogiken“).

Begriffe (alle netto, aus den Summen von rechnen.kalkulation):
- Kosten K = Selbstkosten, dazu die Preisschicht-Korrekturen, die die Kosten ändern, aber nicht in den Selbstkosten
  stehen (mannlose Laufzeit: Kostenanteil ohne Gewinn; Neuteil-Zuschlag: Mehraufwand ohne Gewinn), wie die
  langfristige Preisuntergrenze (preisschicht, J1).
- Durchgereicht D = Verpackung, Finanzierung, Fracht, Frachtfrei-Umlage, Skonto und späterer Musterbetrag: Beträge,
  die der Preis nur weiterreicht.
- Warenwert W = Verkaufspreis − D. Gewinn G = W − K: was nach Rabatt, Rundung, Regeln, Mindestpreis, Preis von Hand
  und Mindestmarge wirklich bleibt.
- Marge m = G ÷ W (vom Warenwert), Aufschlag a = G ÷ K (auf die Kosten); m = a ÷ (1 + a), a = m ÷ (1 − m).
Ohne Rabatt und Preisschicht ist das genau die bisherige Marge des Angebots-Checks ((Gewinn + Anhebung) ÷ (Selbstkosten
+ Gewinn + Anhebung)); mit Rabatt zählt jetzt der gewährte Rabatt mit. Ohne Qt."""

DURCHGEREICHT = ("verpackung", "finanzierung", "fracht", "frachtfrei", "skonto", "muster_spaeter")


def _n(w):
    try:
        return float(w) if w not in (None, "") and not isinstance(w, bool) else 0.0
    except (TypeError, ValueError):
        return 0.0


def aus_aufschlag(a):
    """Marge zu einem Aufschlag auf die Kosten (0,25 → 0,2)."""
    return None if a is None or a <= -1 else a / (1 + a)


def aus_marge(m):
    """Aufschlag auf die Kosten zu einer Marge vom Warenwert (0,2 → 0,25)."""
    return None if m is None or m >= 1 else m / (1 - m)


def gewinn_satz(summen):
    """Gewinnsatz, mit dem die Kalkulation gerechnet hat (Gewinn ÷ Gewinnbasis), für die Korrektur mannlos."""
    s = summen or {}
    if isinstance(s.get("gewinn_satz"), (int, float)):
        return float(s["gewinn_satz"])
    basis = _n(s.get("gewinn_stufen_basis")) or (_n(s.get("selbst")) - _n(s.get("zukauf_einstand"))
                                                 - _n(s.get("zukauf_aufschlag")))
    return _n(s.get("gewinn")) / basis if basis > 0 else 0.0


def kosten(summen):
    """Kosten K: Selbstkosten mit den Kosten-Korrekturen der Preisschicht."""
    s = summen or {}
    # interne Kosten der allgemeinen Zusatzarbeiten (zusatz_global.py, 23.11.2026; ohne Einträge 0)
    return _n(s.get("selbst")) + _n(s.get("mannlos")) / ((1 + gewinn_satz(s)) or 1) + _n(s.get("neuteil")) \
        + _n(s.get("zusatz_global_kosten"))


def durchgereicht(summen):
    return sum(_n((summen or {}).get(n)) for n in DURCHGEREICHT)


def werte(summen):
    """dict(verkauf, kosten, durchgereicht, warenwert, gewinn, marge, aufschlag); marge/aufschlag None ohne Basis."""
    s = summen or {}
    verkauf = _n(s.get("verkauf"))
    k = kosten(s)
    d = durchgereicht(s)
    w = verkauf - d
    g = w - k
    return dict(verkauf=verkauf, kosten=k, durchgereicht=d, warenwert=w, gewinn=g,
                marge=g / w if w > 0 else None, aufschlag=g / k if k > 0 else None)


def marge(summen):
    """Marge vom Warenwert (None ohne Warenwert)."""
    return werte(summen)["marge"]


def preis_bei_marge(summen, m):
    """Netto-Verkaufspreis, bei dem die Marge m wäre (gleiche Kosten und durchgereichte Beträge, Skonto auf den Preis):
    (K ÷ (1 − m) + D ohne Skonto) ÷ (1 − Skontosatz). None bei m ≥ 1."""
    if m is None or m >= 1:
        return None
    s = summen or {}
    sk = _n(s.get("skonto_satz")) / 100
    ohne_skonto = durchgereicht(s) - _n(s.get("skonto"))
    roh = kosten(s) / (1 - m) + ohne_skonto
    return roh / (1 - sk) if sk < 1 else None
