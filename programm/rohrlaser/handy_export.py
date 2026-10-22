"""Stammdaten für die Android-App: eine Datei (JSON), die die App mit „Stammdaten einlesen“ übernimmt.

Es gibt keinen Abgleich zwischen PC und Handy (Patrick 22.10.2026): Der PC bleibt die Stelle, an der Stammdaten
und Einstellungen gepflegt werden; das Handy bekommt eine Kopie und zeigt sie nur an. Neu einlesen ersetzt alles.
Angebote gehen nicht mit (auf dem Handy entstehen eigene).

Inhalt: alle Stammdatentabellen (auch Kunden, Fracht, Zukauf) mit Feldbeschreibung, dazu die Einstellungen.
Das Passwort der Einstellungen bleibt auf dem PC (die Datei geht oft per E-Mail).

Ohne Qt, damit Tests und Build es ohne Oberfläche benutzen können.
"""
import datetime
import json
import os
from pathlib import Path

from . import VERSION
from .datenbank import ALLE_TABELLEN, SCHEMA_VERSION
from .stammdaten import EINSTELLUNGEN

FORMAT = "rohrlaser-stammdaten"
FORMAT_VERSION = 1
NICHT_AUFS_HANDY = ("passwort",)      # Einstellungen, die nie in der Datei stehen
DATEINAME = "Rohrlaser-Stammdaten {datum}.json"


def stammdaten(db):
    """Inhalt der Datei als dict."""
    tabellen = {}
    for t in ALLE_TABELLEN:
        tabellen[t.name] = dict(
            titel=t.titel,
            felder=[dict(name=f.name, titel=f.titel, art=f.art, stellen=f.stellen) for f in t.felder],
            zeilen=[{k: v for k, v in z.items() if k != "id"} for z in db.zeilen(t.name)])
    werte = {e.name: e.vorgabe for e in EINSTELLUNGEN}
    for name, wert in db.con.execute("SELECT name, wert FROM einstellungen"):
        werte[name] = json.loads(wert)
    for name in NICHT_AUFS_HANDY:
        werte.pop(name, None)
    beschreibung = [dict(name=e.name, titel=e.titel, gruppe=e.gruppe, art=e.art) for e in EINSTELLUNGEN
                    if e.name not in NICHT_AUFS_HANDY]
    return dict(format=FORMAT, version=FORMAT_VERSION, programm=VERSION, schema=SCHEMA_VERSION,
                erstellt=datetime.datetime.now().isoformat(timespec="seconds"),
                tabellen=tabellen, einstellungen=werte, einstellungen_beschreibung=beschreibung)


def schreiben(db, ziel):
    """Datei schreiben (erst fertig unter neuem Namen, dann umbenennen). Ergebnis: {Tabelle: Anzahl Zeilen}."""
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    inhalt = stammdaten(db)
    neu = ziel.with_name(ziel.name + ".neu")
    neu.write_text(json.dumps(inhalt, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(neu, ziel)
    return {name: len(t["zeilen"]) for name, t in inhalt["tabellen"].items()}


def vorschlag(ordner):
    return Path(ordner) / DATEINAME.format(datum=datetime.date.today().isoformat())
