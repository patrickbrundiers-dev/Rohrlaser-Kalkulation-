"""Einstellungen sichern, wiederherstellen und auf die Vorgabe zurücksetzen (Menü Hauptadmin, hauptadmin_menue.py).

Eigenes Modul, damit hauptadmin.py (Anmeldung, auch im Programm Rohrlaser Auslastung) die Stammdaten der Kalkulation
nicht mitzieht (programm/auslastung.spec prüft das).
"""
import datetime
import json
from pathlib import Path

from . import lizenz as L
from .hauptadmin import HauptadminFehler

# Nie über Sichern/Wiederherstellen/Zurücksetzen: Passwort, laufende Nummern, Kürzel und Ordner dieses Arbeitsplatzes
NIE_GRUPPEN = ("Benutzer", "Ablage", "Zugang")
NIE_NAMEN = ("passwort", "letzte_angebotsnummer", "ab_nummer")


def einstellungen_namen():
    from .stammdaten import EINSTELLUNGEN
    return [e.name for e in EINSTELLUNGEN if e.gruppe not in NIE_GRUPPEN and e.name not in NIE_NAMEN]


def einstellungen_sichern(db, ziel):
    """Alle Einstellungen (ohne Passwort, Nummern, Kürzel und Ordner) als JSON. Ergebnis: Anzahl."""
    werte = {n: db.einstellung(n) for n in einstellungen_namen()}
    L._schreiben(ziel, json.dumps(dict(art="rohrlaser-einstellungen", format=1,
                                       zeit=datetime.datetime.now().isoformat(timespec="seconds"), werte=werte),
                                  indent=1, ensure_ascii=False))
    return len(werte)


def einstellungen_wiederherstellen(db, quelle):
    """Einstellungen aus einer Datei von einstellungen_sichern übernehmen (nur bekannte, erlaubte Namen); vorher eine
    geschützte Datensicherung. Ergebnis: (Anzahl übernommen, Pfad der Sicherung)."""
    try:
        d = json.loads(Path(quelle).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise HauptadminFehler(f"Die Datei lässt sich nicht lesen: {e}") from None
    if not isinstance(d, dict) or d.get("art") != "rohrlaser-einstellungen" or not isinstance(d.get("werte"), dict):
        raise HauptadminFehler("Das ist keine Sicherung der Einstellungen.")
    erlaubt = set(einstellungen_namen())
    werte = {k: v for k, v in d["werte"].items() if k in erlaubt}
    sicherung = db.sicherung(zusatz="vor_einstellungen")
    for k, v in werte.items():
        if db.einstellung(k) != v:
            db.einstellung_setzen(k, v)
    return len(werte), sicherung


def einstellungen_zuruecksetzen(db):
    """Alle Einstellungen auf die Vorgabe (ohne Passwort, Nummern, Kürzel und Ordner); vorher eine geschützte
    Datensicherung. Stammdaten (Preise, Maschinen, Material) bleiben. Ergebnis: (Anzahl geändert, Pfad Sicherung)."""
    from .stammdaten import EINSTELLUNG
    sicherung = db.sicherung(zusatz="vor_einstellungen")
    n = 0
    for name in einstellungen_namen():
        vorgabe = EINSTELLUNG[name].vorgabe
        if db.einstellung(name) != vorgabe:
            db.einstellung_setzen(name, vorgabe)
            n += 1
    return n, sicherung
