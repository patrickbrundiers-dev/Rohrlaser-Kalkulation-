"""Positionsvorlagen (Vorschlag H6a, 02.11.2026): eine Position ohne Stückzahl, Positionsnummer, Satz/Baugruppe und
Preis als Vorlage speichern (Tabelle positionsvorlagen, mit den Stammdaten für alle Arbeitsplätze geteilt) und als
neue Position einsetzen. Ohne Qt.

Bauteilbibliothek (Großes UI- und Funktionsupdate 19.11.2026, Punkt 4.4): dieselben Vorlagen mit Kategorie, Favorit,
Suche, Kopieren und 3D-Vorschau (bibliothek_dialog.py) – keine zweite Ablage, die Vorlagen bleiben die Bibliothek."""
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


# ------------------------------------------------------------------ Bauteilbibliothek (19.11.2026)
OHNE_KATEGORIE = "Ohne Kategorie"


def kategorien(vorlagen):
    """Kategorien der Vorlagen, sortiert (ohne leere)."""
    return sorted({(v.get("kategorie") or "").strip() for v in vorlagen} - {""}, key=str.lower)


def ist_favorit(v):
    return str((v or {}).get("favorit") or "").strip().lower() in ("ja", "1", "true", "x")


def suchen(vorlagen, text="", kategorie=None, nur_favoriten=False):
    """Vorlagen filtern: Text (alle Wörter in Name, Inhalt, Kategorie, Bemerkung, Profil, Werkstoff, Artikel),
    Kategorie (OHNE_KATEGORIE = leere), nur Favoriten. Favoriten zuerst, dann nach Name."""
    worte = (text or "").lower().split()
    out = []
    for v in vorlagen:
        k = (v.get("kategorie") or "").strip()
        if kategorie and (k != kategorie if kategorie != OHNE_KATEGORIE else k):
            continue
        if nur_favoriten and not ist_favorit(v):
            continue
        d = werte(v) or {}
        alles = " ".join(str(x or "") for x in (v.get("name"), v.get("inhalt"), k, v.get("bemerkung"),
                                                  d.get("profil_id"), d.get("werkstoff_id"), d.get("artikel"),
                                                  d.get("bezeichnung"))).lower()
        if all(w in alles for w in worte):
            out.append(v)
    return sorted(out, key=lambda v: (not ist_favorit(v), str(v.get("name") or "").lower()))


def favorit_setzen(db, vorlage_id, an=True):
    db.aendern(TABELLE, vorlage_id, "favorit", "ja" if an else "")


def kategorie_setzen(db, vorlage_id, kategorie):
    db.aendern(TABELLE, vorlage_id, "kategorie", (kategorie or "").strip() or None)


def kopieren(db, vorlage_id, name):
    """Vorlage unter neuem Namen kopieren (zum Abwandeln). Ergebnis: neue ID."""
    name = (name or "").strip()
    alle = db.zeilen(TABELLE)
    v = next((x for x in alle if x["id"] == vorlage_id), None)
    if v is None:
        raise ValueError("Die Vorlage gibt es nicht mehr.")
    if not name:
        raise ValueError("Bitte einen Namen für die Kopie eintragen.")
    if any(x["name"] == name for x in alle):
        raise ValueError(f"Die Vorlage '{name}' gibt es schon.")
    neu = {k: v.get(k) for k in ("inhalt", "daten", "bemerkung", "kategorie")}
    neu.update(name=name, angelegt=datetime.datetime.now().isoformat(timespec="seconds"))
    return db.neu(TABELLE, neu)


def vorschau_netz(v, k):
    """3D-Netz einer Vorlage für die Vorschau (Rohr aus dem Schneidweg-Rechner, Blech gefaltet) oder None."""
    d = werte(v)
    if not d:
        return None
    from . import blech
    try:
        e = blech.lesen(d.get("technik"))
        if e:
            from . import blech3d
            return blech3d.netz(e, blech.zuschnitt(e))
        profil = k.profile.get(d.get("profil_id")) if k is not None else None
        laenge = d.get("laenge")
        if not profil or not isinstance(laenge, (int, float)) or laenge <= 0:
            return None
        from . import rohr3d, schneidweg
        e = schneidweg.aus_position(schneidweg.lesen(d.get("technik")), d, profil)[0]
        return rohr3d.netz(e, profil, laenge)
    except (ValueError, TypeError, KeyError, ZeroDivisionError, AttributeError, IndexError):
        return None
