"""Grundlagen der Wochenauslastung ohne Abhängigkeit zur Kalkulation: Spaltenschlüssel, Ampelgrenzen, Montag einer
Woche, Betriebsruhe. Genutzt von auslastung.py, einlastung.py, der Grafik (auslastung_grafik.py) und dem eigenen
Programm „Rohrlaser Auslastung“ (Patrick 11.11.2026)."""
import datetime
import re

UEBERFAELLIG, SPAETER, OHNE = "überfällig", "später", "ohne Termin"
GELB, ROT = 0.8, 1.0           # Auslastung ab 80 % gelb, über 100 % rot


def _datum(t):
    t = t.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def betriebsruhe(text):
    """'24.12.2026-31.12.2026; 02.10.2026' -> Menge der Tage. Unlesbares wird übergangen."""
    tage = set()
    for teil in re.split(r"[;,\n]+", str(text or "")):
        von, _, bis = teil.partition("-") if re.match(r"^\s*\d{1,2}\.\d", teil) else (teil, "", "")
        a, b = _datum(von) if von.strip() else None, _datum(bis) if bis.strip() else None
        if a is None:
            continue
        b = b or a
        while a <= b:
            tage.add(a)
            a += datetime.timedelta(days=1)
    return tage


def montag(d):
    return d - datetime.timedelta(days=d.weekday())
