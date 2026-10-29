"""Stundensatz-Ermittlung je Maschine (Plan „Stundensatz-Ermittlung je Maschine“, Patrick 29.10.2026, „A b a a a“).

Maschinenstundensatz = feste Kosten je Jahr ÷ genutzte Stunden + Kosten je Laufstunde, dazu der Anteil des Bedieners
und der Gemeinkostenzuschlag:
- fest je Jahr: Abschreibung (Anschaffung ÷ Nutzungsdauer), kalkulatorische Zinsen (Zinssatz auf den halben
  Anschaffungswert), Raum (m² × €/m² im Monat × 12), Instandhaltung (% vom Anschaffungswert), Wartung/Versicherung;
- je Stunde: Strom (kW × €/kWh, Frage 1a: im Satz), Verschleiß (Düsen, Schutzgläser);
- Bediener (Frage 3a): Stundenlohn × Anteil der Betreuung;
- Gemeinkosten: Zuschlag in % auf die Summe.
Stunden je Jahr = Stunden je Arbeitstag (Maschine 'Schicht', sonst Einstellung) × Arbeitstage × Auslastung.
Strompreis, Raumkosten, Zinssatz, Bedienerlohn, Gemeinkosten, Arbeitstage und Auslastung stehen einmal in den
Einstellungen (Frage 4a), alles andere je Maschine. Gas zählt nie mit: es wird je Teil gerechnet (rechnen.gas_kosten).

Auswahl je Maschine 'Stundensatz': „von Hand“ (leer, alle Maschinen vor der Ermittlung, Frage 5a) = das Feld Stundensatz
gilt und enthält Gas und Strom; Gas kommt nur mit 'Gas zusätzlich zum Stundensatz' = ja dazu (Frage 2b).
„ermittelt“ = der hier gerechnete Satz gilt, Gas kommt immer dazu.
"""

SATZ_HAND, SATZ_ERMITTELT = "von Hand", "ermittelt"
SATZARTEN = (SATZ_HAND, SATZ_ERMITTELT)
# Maschinenfelder der Ermittlung (Snapshot der Zeitbasis braucht nur das Ergebnis)
FELDER = ("anschaffung", "nutzungsdauer", "flaeche", "instandhaltung", "wartung", "leistung_kw", "verschleiss",
          "bediener_anteil")
# Einstellungen der Ermittlung (für alle Maschinen gleich)
EINST = ("strompreis", "raumkosten", "zinssatz", "bediener_satz", "gemeinkosten", "arbeitstage", "auslastung_jahr")


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _e(einst, name):
    from .rechnen import einstellung_wert
    return _n(einstellung_wert(einst, name))


def ermittelt(m):
    """True, wenn die Maschine den ermittelten Stundensatz nutzt."""
    return (m or {}).get("satz_art") == SATZ_ERMITTELT


def gas_rechnen(m):
    """Schneidgas zusätzlich zum Stundensatz rechnen: beim ermittelten Satz immer, beim Satz von Hand nur mit
    'Gas zusätzlich zum Stundensatz' = ja (der Satz von Hand enthält sonst Gas und Strom)."""
    return ermittelt(m) or (m or {}).get("gas_zusatz") == "ja"


def stunden_jahr(m, einst):
    """Genutzte Stunden je Jahr: Stunden je Arbeitstag × Arbeitstage × Auslastung."""
    tag = _n((m or {}).get("schicht_stunden")) or _e(einst, "schicht_stunden")
    return tag * _e(einst, "arbeitstage") * _e(einst, "auslastung_jahr")


def posten(m, einst):
    """Rechenweg: (Zeilen, Stunden je Jahr, Stundensatz €/h oder None). Zeile = (Posten, Eingabe, €/Jahr oder None,
    €/h); Summenzeilen haben als Eingabe None. None, wenn keine Stunden je Jahr oder kein Posten eingetragen ist."""
    from .stammdaten import zahl_als_text as z
    m = m or {}
    h = stunden_jahr(m, einst)
    an, jahre = _n(m.get("anschaffung")), _n(m.get("nutzungsdauer"))
    zins, raum = _e(einst, "zinssatz"), _e(einst, "raumkosten")
    fest = [("Abschreibung", f"{z(an, 0)} € ÷ {z(jahre, 0)} Jahre", an / jahre if jahre else 0.0),
            ("Kalkulatorische Zinsen", f"{z(100 * zins, 1)} % auf den halben Anschaffungswert", an / 2 * zins),
            ("Raum", f"{z(_n(m.get('flaeche')), 0)} m² × {z(raum, 2)} €/m² im Monat", _n(m.get("flaeche")) * raum * 12),
            ("Instandhaltung", f"{z(_n(m.get('instandhaltung')), 1)} % vom Anschaffungswert",
             an * _n(m.get("instandhaltung")) / 100),
            ("Wartung, Versicherung", "Betrag je Jahr", _n(m.get("wartung")))]
    zeilen = [(t, e, j, j / h if h else 0.0) for t, e, j in fest]
    fest_j = sum(j for _, _, j in fest)
    zeilen.append(("Feste Kosten", None, fest_j, fest_j / h if h else 0.0))
    strom = _n(m.get("leistung_kw")) * _e(einst, "strompreis")
    zeilen += [("Strom", f"{z(_n(m.get('leistung_kw')), 1)} kW × {z(_e(einst, 'strompreis'), 3)} €/kWh", None, strom),
               ("Verschleiß (Düsen, Schutzgläser)", "€ je Laufstunde", None, _n(m.get("verschleiss")))]
    maschine = zeilen[5][3] + strom + _n(m.get("verschleiss"))
    zeilen.append(("Maschinenkosten", None, None, maschine))
    bed = _e(einst, "bediener_satz") * _n(m.get("bediener_anteil")) / 100
    zeilen.append(("Bediener", f"{z(_e(einst, 'bediener_satz'), 2)} €/h × {z(_n(m.get('bediener_anteil')), 0)} % "
                               "Betreuung", None, bed))
    gk = _e(einst, "gemeinkosten")
    gem = (maschine + bed) * gk
    zeilen.append(("Gemeinkosten", f"{z(100 * gk, 1)} % Zuschlag", None, gem))
    satz = maschine + bed + gem
    zeilen.append(("Stundensatz", None, None, satz))
    leer = not any(_n(m.get(n)) for n in FELDER)
    return zeilen, h, (None if leer or h <= 0 else satz)


def ermitteln(m, einst):
    """Ermittelter Stundensatz [€/h] oder None (keine Stunden, nichts eingetragen)."""
    return posten(m, einst)[2]


def wirksam(m, einst):
    """Stundensatz, mit dem die Kalkulation rechnet: ermittelt (wenn eingestellt und rechenbar), sonst das Feld
    Stundensatz."""
    if ermittelt(m):
        s = ermitteln(m, einst)
        if s is not None:
            return round(s, 2)
    return (m or {}).get("stundensatz")
