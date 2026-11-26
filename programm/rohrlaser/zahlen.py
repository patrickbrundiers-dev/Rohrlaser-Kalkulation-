"""Gemeinsame kleine Umwandlungen für Zahlen und Zeitstempel (Software-Audit 26.11.2026, Redundanz R-01).

Vorher stand dieselbe Hilfsfunktion als eigene Kopie in vielen Modulen (_n 77-mal in 11 verschiedenen Fassungen,
_jetzt 24-mal, _zahl 80-mal). Hier stehen nur die Fassungen, die in mindestens drei Modulen wörtlich gleich waren;
diese Module binden sie unter ihrem bisherigen Namen ein (from .zahlen import float_oder_0 as _n), Verhalten und
Ergebnisse bleiben bitgleich. Abweichende Fassungen bleiben bewusst in ihren Modulen: sie unterscheiden sich fachlich
(z. B. Text "1,5" lesen oder nicht, 0 statt None), eine Vereinheitlichung würde Ergebnisse ändern.
Ohne Qt, nur Standardbibliothek."""
import datetime


def float_oder_0(v):
    """Echte Zahl (int/float, nicht bool) als float, sonst 0.0. Texte werden nicht gelesen ("1,5" -> 0.0)."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def float_oder_none(v):
    """Echte Zahl (int/float, nicht bool) als float, sonst None."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def ist_zahl(w):
    """True für int/float (nicht bool); NaN und unendlich zählen mit."""
    return isinstance(w, (int, float)) and not isinstance(w, bool)


def jetzt_text():
    """Jetzt als ISO-Text auf Sekunden (Ortszeit), z. B. 2026-11-26T08:15:00."""
    return datetime.datetime.now().isoformat(timespec="seconds")
