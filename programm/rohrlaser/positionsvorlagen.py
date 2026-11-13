"""Positionsvorlagen (Vorschlag H6a, 02.11.2026): eine Position ohne Stückzahl, Positionsnummer, Satz/Baugruppe und
Preis als Vorlage speichern (Tabelle positionsvorlagen, mit den Stammdaten für alle Arbeitsplätze geteilt) und als
neue Position einsetzen. Ohne Qt."""
import datetime
import json

from .angebot import POSITIONEN

OHNE = ("pos", "stueck", "satz", "je_satz", "preis_m", "baugruppe", "bg_knoten", "je_knoten", "bg_hilfe", "bg_gravur", "bg_haupt",
        "je_umfang", "muster")
TABELLE = "positionsvorlagen"


def daten(p):
    """Werte einer Position für die Vorlage (ohne OHNE und ohne leere Werte)."""
    return {f.name: p.get(f.name) for f in POSITIONEN.felder
            if f.name not in OHNE and p.get(f.name) not in (None, "")}


def inhalt(d):
    teile = [d.get("profil_id"), d.get("werkstoff_id"),
             f"{d['laenge']:g} mm" if isinstance(d.get("laenge"), (int, float)) else None,
             d.get("gewinde") and f"Gewinde {d['gewinde']}", d.get("zusatz") and "Zusatzarbeiten",
             d.get("naht_vorgabe") and "Naht"]
    return ", ".join(str(t) for t in teile if t)


def speichern(db, p, name, ueberschreiben=True):
    """Vorlage name aus Position p; gleicher Name wird ersetzt (ueberschreiben). Ergebnis: ID."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Bitte einen Namen für die Vorlage eintragen.")
    d = daten(p)
    werte = dict(name=name, inhalt=inhalt(d), daten=json.dumps(d, ensure_ascii=False),
                 angelegt=datetime.datetime.now().isoformat(timespec="seconds"))
    alt = next((z for z in db.zeilen(TABELLE) if z["name"] == name), None)
    if alt and not ueberschreiben:
        raise ValueError(f"Die Vorlage '{name}' gibt es schon.")
    if alt:
        for feld in ("inhalt", "daten", "angelegt"):
            db.aendern(TABELLE, alt["id"], feld, werte[feld])
        return alt["id"]
    return db.neu(TABELLE, werte)


def werte(vorlage):
    """Positionswerte aus einer Vorlage oder None (leer/beschädigt)."""
    try:
        d = json.loads((vorlage or {}).get("daten") or "")
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    namen = {f.name for f in POSITIONEN.felder} - set(OHNE)
    return {n: w for n, w in d.items() if n in namen}
