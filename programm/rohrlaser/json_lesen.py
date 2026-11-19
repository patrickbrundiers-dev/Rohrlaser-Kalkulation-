"""JSON-Text einmal lesen (Systemcheck vor dem Sammel-Update, Patrick 19.11.2026).

Befund: Beim Ändern einer Zelle las das Programm denselben Technik-Text der Positionen (Konturen, Enden, STEP-Werte)
rund 1.500-mal neu ein (Spiegelteile, „von Hand geändert“, Verbindungselemente …), beim Öffnen rund 1.000-mal: ein
Drittel bis die Hälfte der Rechenzeit dieser Vorgänge. nur_lesen(text) liest jeden Text einmal und gibt danach
dasselbe Ergebnis zurück.

Nur für Stellen, die das Ergebnis NUR LESEN (nie ändern, nie weitergeben, wo es geändert wird) – sonst json.loads.
Ein geänderter Text ist ein anderer Schlüssel und wird neu gelesen; Ergebnisse sind also immer die von json.loads.
"""
import json

MERKEN = 2048                   # so viele verschiedene Texte (danach wird von vorn begonnen)
_merk = {}
zaehler = {"gelesen": 0, "gemerkt": 0}
_FEHLER = object()


def nur_lesen(text):
    """json.loads(text) für Lesezugriffe; ValueError/TypeError wie json.loads (auch beim zweiten Mal)."""
    w = _merk.get(text, None) if isinstance(text, str) else None
    if w is None:
        try:
            w = json.loads(text)
        except (TypeError, ValueError):
            if not isinstance(text, str):
                raise
            w = _FEHLER
        if isinstance(text, str):
            if len(_merk) >= MERKEN:
                _merk.clear()
            _merk[text] = w
        zaehler["gelesen"] += 1
    else:
        zaehler["gemerkt"] += 1
    if w is _FEHLER:
        raise ValueError("kein gültiges JSON")
    return w
