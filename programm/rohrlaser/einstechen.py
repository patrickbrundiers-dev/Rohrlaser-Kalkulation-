"""Einstechzeit berechnet statt fester Tabellenwerte (Plan „Laserzeit vollständig berechnen“ Phase 1, E1, Patrick
16.11.2026 „Alle Empfehlungen“).

Einstechzeit [s] = Grundzeit (Gas und Abstandsregelung einschwingen, Maschinenfeld 'Einstechen berechnen: Grundzeit')
                   + 0,1 s × Wand^1,4 × √(6 kW ÷ Laserleistung) × Werkstofffaktor, mit Einstichüberwachung × 0,75.

Herkunft: Einstechzeiten Baustahl O₂ 6 kW (1 mm 0,1 s, 3 mm 0,4 s, 6 mm 1,0 s, 10 mm 2,0 s, 12 mm 3,0 s, 20 mm 8 s;
LaserCalc Pro), Edelstahl × 1,5–2, Aluminium × 1,5 (ebd.); die Umrechnung auf andere Leistungen mit der Wurzel ist
eine Annahme; Einstichüberwachung spart rund 25 % (Garcia u. a., Applied Sciences 2019; Trumpf PierceLine).
Grundzeit 0,15 s: progressives Einstechen 100 ms + Absenken auf Schneidhöhe (CypCut). Ohne Grundzeit oder
Laserleistung der Maschine gilt die Einstechzeit der Schneiddaten wie bisher. Ohne Qt."""
from .zahlen import float_oder_none as _n  # Audit 26.11.2026 R-01: gemeinsame Hilfsfunktion

K = 0.1                 # [s] bei 1 mm und 6 kW
EXPONENT = 1.4          # Wachstum mit der Wand
P_REF = 6.0             # [kW] Bezugsleistung der Kurve
WERKSTOFF = {"Stahl": 1.0, "Edelstahl": 1.75, "Aluminium": 1.5, "Buntmetall": 2.0}   # Buntmetall: Annahme
UEBERWACHUNG = 0.75     # Einstichüberwachung beendet das Einstechen, sobald es durch ist


def aktiv(m):
    """True, wenn die Maschine die Einstechzeit berechnet (Grundzeit und Laserleistung eingetragen)."""
    m = m or {}
    return _n(m.get("einstich_grund")) is not None and (_n(m.get("laser_kw")) or 0) > 0


def zeit(m, wand, kategorie, tabellenwert):
    """Einstechzeit [s] für die Wand [mm]; ohne Berechnung an der Maschine (aktiv) oder ohne Wand der Tabellenwert."""
    w = _n(wand)
    if not aktiv(m) or not w or w <= 0:
        return tabellenwert
    t = K * w ** EXPONENT * (P_REF / _n(m["laser_kw"])) ** 0.5 * WERKSTOFF.get(kategorie or "", 1.0)
    if (m or {}).get("einstich_ueberwachung") == "ja":
        t *= UEBERWACHUNG
    return round(_n(m["einstich_grund"]) + t, 3)
