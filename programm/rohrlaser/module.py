"""Lizenz-Module (Lizenz 2.0, Paket L2-4; Patrick 26.11.2026 „Basis plus 7 Module“).

Die Basis (Rohr-Kalkulation, Angebote, STEP-Import, PDF, Fracht, Schnellpreis …) gehört zu jeder Lizenz. Die sieben
Module schalten Gruppen von Funktionen (funktionen.FUNKTIONEN) frei. Die Prüfung sitzt an EINER Stelle:
funktionen.an() fragt erlaubt(); ein nicht lizenziertes Modul blendet seine Funktionen aus wie der Schalter „nein“.
Daten bleiben, vorhandene Angebote rechnen weiter (wie beim Ausschalten).

Bisherige Lizenzen und Lizenzen ohne Feld haben ['alle'] und behalten alles. Hauptadmin und „ohne Lizenzprüfung“
(Tests, Stufe 1) ebenfalls. Ohne Qt.
"""
from collections import namedtuple

Modul = namedtuple("Modul", "name titel funktionen text")

MODULE = (
    Modul("blech", "Blech", ("funktion_blech",), "Bleche und Kantteile"),
    Modul("baugruppen", "Baugruppen", ("funktion_schweissen", "funktion_knick_steck"),
          "Schweißbaugruppen, Knickrahmen und Steckverbindung"),
    Modul("auftrag", "Auftrag", ("funktion_ab", "funktion_nachkalkulation", "funktion_reklamation",
                                 "funktion_etiketten", "funktion_muster", "funktion_abruf"),
          "Auftragsbestätigung, Nachkalkulation, Reklamationen, Etiketten, Musterteile, Abruf-/Rahmenangebote"),
    Modul("vertrieb", "Vertrieb", ("funktion_angebot_mail", "funktion_nachfassen", "funktion_wiedervorlage",
                                   "funktion_simulator", "funktion_vergleich", "funktion_chance",
                                   "funktion_preis_hinweise"),
          "Angebot per E-Mail, Nachfassen/Wiedervorlage, Preis-Simulator, Angebotsvergleich, Auftragschance, "
          "Preis- und Termin-Hinweise"),
    Modul("einkauf", "Einkauf", ("funktion_zukauf", "funktion_zukauf_stamm", "funktion_materialanfrage",
                                 "funktion_onlinepreise", "funktion_teuerung", "funktion_erp_preise"),
          "Zukaufteile, Materialanfrage, Online-Preise, Teuerungszuschlag, Materialpreise aus ERP"),
    Modul("auslastung", "Auslastung", ("funktion_auslastung",), "Maschinenauslastung"),
    Modul("ki", "KI", ("funktion_lernen", "funktion_regelvorschlaege"),
          "Lernen und selbst anwenden, Vorschläge aus Handeinträgen"),
)
MODUL = {m.name: m for m in MODULE}
ZU_MODUL = {f: m.name for m in MODULE for f in m.funktionen}
NAMEN = tuple(m.name for m in MODULE)
ALLE = "alle"
BASIS = "basis"         # nur die Basis, kein Modul

_lizenz = None          # None = keine Einschränkung; sonst Menge der lizenzierten Modulnamen


def normal(liste):
    """Module einer Lizenz als sortierte Liste bekannter Namen; ['alle'], wenn alle (oder nichts angegeben)."""
    liste = [str(m).strip().lower() for m in (liste or []) if str(m).strip()]
    if not liste or ALLE in liste or set(NAMEN) <= set(liste):
        return [ALLE]
    return [m for m in NAMEN if m in liste] or [BASIS]


def setzen(module):
    """Lizenzierte Module für dieses Programm setzen (LizenzStelle.pruefen). None oder ['alle'] = alles."""
    global _lizenz
    n = normal(module) if module is not None else [ALLE]
    _lizenz = None if n == [ALLE] else set(n) - {BASIS}


def aus_zustand(z):
    """Module aus einem Lizenzzustand: Hauptadmin, Lesemodus-Stufe-1 und alte Lizenzen = alle."""
    if z is None or getattr(z, "hauptadmin", False) or not getattr(z, "inhalt", None):
        return None
    return z.inhalt.get("funktionen") or [ALLE]


def lizenziert(modul):
    return _lizenz is None or modul in _lizenz


def erlaubt(funktion):
    """Darf die Funktion laut Lizenz laufen? Basis-Funktionen (in keinem Modul) immer."""
    m = ZU_MODUL.get(funktion)
    return m is None or lizenziert(m)


def text(module=None):
    """Kurztext für den Lizenz-Dialog: „alle Module“ oder „Basis, Blech, KI“."""
    n = normal(module) if module is not None else ([ALLE] if _lizenz is None else sorted(_lizenz))
    if n == [ALLE]:
        return "Basis und alle Module"
    gewaehlt = [MODUL[m].titel for m in NAMEN if m in n]
    return "Basis, " + ", ".join(gewaehlt) if gewaehlt else "nur Basis"
