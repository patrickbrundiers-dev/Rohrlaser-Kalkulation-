"""Ertrag nach Einkauf und nach Herstellkosten (Plan PROfirst-/LogiTRACE-Handbücher 12.11.2026, G2).

PROfirst zeigt „Marge brutto“ (Preis minus Einkauf) und „Marge netto“ (Preis minus Herstellkosten). Hier:
- Warenwert = Verkaufspreis ohne Fracht (Fracht trägt keinen Gewinn).
- Ertrag nach Einkauf = Warenwert − Material (abzüglich Schrotterlös) − Zukaufteile (Einstand) − Fremdleistungen der
  Schweißbaugruppen: was nach dem Einkauf für Maschine, Personal und Gewinn bleibt.
- Ertrag nach Herstellkosten = Warenwert − Herstellkosten − Zukaufteile (Einstand): Deckungsbeitrag nach der Fertigung.
Je Angebot (Preisaufbau der Übersicht) und je Position (Spalten der Kalkulation). Nur Anzeige, ändert keine Preise."""


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0


def _anteil(w, ware):
    return w / ware if ware else None


def angebot(betrag):
    """betrag: {Schlüssel der Kostenart (rechnen.KOSTENARTEN): Betrag}. Ergebnis dict(ware, einkauf, brutto,
    brutto_anteil, netto, netto_anteil)."""
    b = {k: _n(v) for k, v in (betrag or {}).items()}
    ware = b.get("verkauf", 0.0) - b.get("fracht", 0.0) - b.get("frachtfrei", 0.0)
    einkauf = b.get("material", 0.0) + b.get("schrott", 0.0) + b.get("zukauf_einstand", 0.0) \
        + b.get("baugruppe_fremd", 0.0)
    brutto = ware - einkauf
    netto = ware - b.get("herstell", 0.0) - b.get("zukauf_einstand", 0.0)
    return dict(ware=ware, einkauf=einkauf, brutto=brutto, brutto_anteil=_anteil(brutto, ware), netto=netto,
                netto_anteil=_anteil(netto, ware))


def _ware_position(z):
    st = _n(z.get("stueck"))
    return _n(z.get("preis_position")) - _n(z.get("fracht_teil")) * st


def position_brutto(z):
    """Ertrag nach Einkauf einer Kalkulationszeile (Position) in € oder None ohne Preis."""
    if not isinstance(z.get("preis_position"), (int, float)):
        return None
    st = _n(z.get("stueck"))
    return _ware_position(z) - _n(z.get("material_position")) - _n(z.get("zukauf_einstand_teil")) * st


def position_netto(z):
    """Ertrag nach Herstellkosten einer Kalkulationszeile (Position) in € oder None ohne Preis."""
    if not isinstance(z.get("preis_position"), (int, float)):
        return None
    st = _n(z.get("stueck"))
    return _ware_position(z) - _n(z.get("herstell_position")) - _n(z.get("zukauf_einstand_teil")) * st


def position_anteil(z, wert):
    """Anteil am Warenwert der Position in % (für die Spalte) oder None."""
    ware = _ware_position(z)
    return 100 * wert / ware if wert is not None and ware else None


def text(e, zahl):
    """Zwei Zeilen für den Preisaufbau: [(Bezeichnung, Betrag)]."""
    def p(a):
        return f" ({zahl(100 * a, 1)} % vom Warenwert)" if a is not None else ""
    return [("Ertrag nach Einkauf" + p(e["brutto_anteil"]), e["brutto"]),
            ("Ertrag nach Herstellkosten" + p(e["netto_anteil"]), e["netto"])]
