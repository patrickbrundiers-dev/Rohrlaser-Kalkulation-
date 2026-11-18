"""Gemeinsame Merker für reine Rechnungen (Stabilitäts-Auftrag Patrick 18.11.2026, „doppelte Berechnungen
konsequent vermeiden“).

Ein Merker gilt für eine Rechnung, deren Ergebnis nur von ihren Eingaben abhängt. Der Schlüssel enthält alle
Eingaben (Inhalt, nicht Zeitstempel); gleiche Eingaben ergeben also dasselbe Ergebnis wie neu gerechnet. Jeder Merker
ist begrenzt (älteste Einträge fallen heraus), sicher für mehrere Threads und zählt Treffer und Neuberechnungen –
diese Zahlen zeigt die Diagnose (diagnose.py): ein Treffer ist eine vermiedene Doppelrechnung.

Ohne Qt, ohne Datenbank.
"""
import collections
import threading
import time

_alle = {}
_alle_sperre = threading.Lock()


class Merker:
    """Begrenzter Merker (LRU) mit Zählern. holen(schluessel, rechne) liefert das gemerkte Ergebnis oder rechnet es
    einmal. Das Ergebnis wird nicht kopiert: Aufrufer, die es verändern könnten, kopieren selbst (oder legen
    Unveränderliches ab)."""

    def __init__(self, name, groesse):
        self.name, self.groesse = name, groesse
        self._werte = collections.OrderedDict()
        self._sperre = threading.Lock()
        self.treffer = self.neu = 0
        self.dauer_s = 0.0          # Zeit der Neuberechnungen
        with _alle_sperre:
            _alle[name] = self

    def holen(self, schluessel, rechne):
        try:
            hash(schluessel)
        except TypeError:           # Schlüssel nicht hashbar: rechnen wie ohne Merker
            return rechne()
        with self._sperre:
            if schluessel in self._werte:
                self._werte.move_to_end(schluessel)
                self.treffer += 1
                return self._werte[schluessel]
        t = time.perf_counter()
        wert = rechne()
        with self._sperre:
            self.neu += 1
            self.dauer_s += time.perf_counter() - t
            self._werte[schluessel] = wert
            self._werte.move_to_end(schluessel)
            while len(self._werte) > self.groesse:
                self._werte.popitem(last=False)
        return wert

    def nur_holen(self, schluessel):
        """Gemerktes Ergebnis oder None, ohne zu rechnen (zählt als Treffer, wenn vorhanden)."""
        try:
            with self._sperre:
                if schluessel in self._werte:
                    self._werte.move_to_end(schluessel)
                    self.treffer += 1
                    return self._werte[schluessel]
        except TypeError:
            pass
        return None

    def leeren(self):
        with self._sperre:
            self._werte.clear()

    def __len__(self):
        return len(self._werte)


def alle():
    """{Name: Merker} aller Merker des Programms."""
    with _alle_sperre:
        return dict(_alle)


def stand():
    """Zähler aller Merker: [dict(name, eintraege, groesse, treffer, neu, dauer_s)] nach Name."""
    return [dict(name=m.name, eintraege=len(m), groesse=m.groesse, treffer=m.treffer, neu=m.neu,
                 dauer_s=round(m.dauer_s, 3)) for _, m in sorted(alle().items())]


def alle_leeren():
    for m in alle().values():
        m.leeren()
