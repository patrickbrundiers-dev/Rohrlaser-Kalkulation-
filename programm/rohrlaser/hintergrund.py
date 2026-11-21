"""Überwachung der Hintergrundaufgaben (Master-Prompt Rechenkerne und Systemstabilität, Patrick 21.11.2026: „Blockierte
Hintergrundprozesse erkennen“, „Überwachung kritischer Systemprozesse“).

Die rechenintensiven Abläufe neben der Oberfläche (Optimieren, Staffelpreise, Maschinenvergleich, Wiederholteile,
Sicherung, Angebots-Cache) melden ihren Faden beim Start mit melden(). laufend() zeigt, was gerade läuft und seit wann;
befunde() nennt Aufgaben, die ungewöhnlich lange laufen (über LANG_S), als Hinweis für die Diagnose
(diagnose.befunde). Die Überwachung greift nie ein und hält keinen Faden fest (schwache Verweise); sie kostet nichts,
solange niemand den Bericht öffnet. Ohne Qt, ohne Datenbank.
"""
import threading
import time
import weakref

LANG_S = 600.0              # länger: „läuft ungewöhnlich lange“ (Optimieren XL braucht Sekunden, nicht Minuten)

_sperre = threading.Lock()
_gemeldet = weakref.WeakKeyDictionary()     # Thread -> (Name, Start monotonic)
_beendet = {}               # Name -> [Anzahl, Summe s, längste s] (fertige gemeldete Aufgaben)


def melden(faden, name=None):
    """Gestarteten Faden zur Überwachung melden (nach start()). Ergebnis: der Faden."""
    with _sperre:
        _gemeldet[faden] = (name or faden.name, time.monotonic())
    return faden


def _aufraeumen(jetzt):
    for t, (name, start) in list(_gemeldet.items()):
        if not t.is_alive():
            e = _beendet.setdefault(name, [0, 0.0, 0.0])
            d = max(0.0, jetzt - start)
            e[0] += 1
            e[1] += d
            e[2] = max(e[2], d)
            del _gemeldet[t]


def laufend(jetzt=None):
    """[(Name, seit s)] der gemeldeten Aufgaben, die noch laufen, älteste zuerst; dazu andere lebende Fäden ohne
    Meldung mit seit = None."""
    jetzt = time.monotonic() if jetzt is None else jetzt
    with _sperre:
        _aufraeumen(jetzt)
        bekannt = [(name, jetzt - start) for t, (name, start) in _gemeldet.items()]
        ids = {id(t) for t in _gemeldet}
    andere = [(t.name, None) for t in threading.enumerate()
              if t is not threading.main_thread() and id(t) not in ids and t.is_alive()]
    return sorted(bekannt, key=lambda x: -x[1]) + sorted(andere)


def beendet():
    """{Name: dict(anzahl, summe_s, max_s)} der fertigen gemeldeten Aufgaben seit dem Start."""
    with _sperre:
        _aufraeumen(time.monotonic())
        return {n: dict(anzahl=e[0], summe_s=e[1], max_s=e[2]) for n, e in _beendet.items()}


def befunde(jetzt=None):
    """[(Name, seit s)] gemeldeter Aufgaben, die länger als LANG_S laufen."""
    return [(n, s) for n, s in laufend(jetzt) if s is not None and s > LANG_S]


def zuruecksetzen():
    with _sperre:
        _beendet.clear()
