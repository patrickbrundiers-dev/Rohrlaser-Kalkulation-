"""Kostentreiber im 3D einfärben (CAD-005, Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“, E4 = a: Farbe
nach dem €-Anteil je Merkmal bzw. je Teil).

Die Werte kommen aus der Rechnung (Bearbeitungsliste des Teile-Editors bzw. Selbstkosten je Teil aus der
Angebotskalkulation); hier wird nichts geschätzt. Stufen nach dem Anteil an der Summe:

- ab 50 %       rot
- 25 bis 50 %   orange
- 10 bis 25 %   gelb
- unter 10 %    grün
"""

# (Art im 3D, Text der Legende, Farbe, untere Grenze Anteil)
STUFEN = (("KO0", "Kosten ab 50 %", "#C62828", 0.50),
          ("KO1", "Kosten 25 bis 50 %", "#EF6C00", 0.25),
          ("KO2", "Kosten 10 bis 25 %", "#F9A825", 0.10),
          ("KO3", "Kosten unter 10 %", "#2E7D32", 0.0))
ARTEN = tuple(s[0] for s in STUFEN)
TIPP = ("Kostentreiber farbig: jedes Merkmal (bzw. Teil) nach seinem Anteil an den Kosten – rot ab 50 %, orange "
        "25–50 %, gelb 10–25 %, grün unter 10 %. Werte aus der Bearbeitungsliste bzw. der Angebotskalkulation.")


def stufe(anteil):
    """Nummer der Stufe (0 = rot … 3 = grün) für einen Anteil 0 … 1."""
    for n, (_, _, _, ab) in enumerate(STUFEN):
        if anteil >= ab - 1e-9:
            return n
    return len(STUFEN) - 1


def stufen(werte):
    """{Schlüssel: €} -> {Schlüssel: (Stufe, Anteil)}; leer, wenn die Summe 0 ist (nichts einzufärben). Negative
    Werte zählen als 0."""
    w = {k: max(float(v or 0.0), 0.0) for k, v in (werte or {}).items() if isinstance(v, (int, float))}
    summe = sum(w.values())
    if summe <= 0:
        return {}
    return {k: (stufe(v / summe), v / summe) for k, v in w.items()}


def legende(belegt=None):
    """[(Text, Farbe)] der Stufen; belegt = Menge der vorkommenden Stufen (None = alle)."""
    return [(t, f) for n, (_, t, f, _) in enumerate(STUFEN) if belegt is None or n in belegt]


def farbe(n):
    return STUFEN[n][2]
