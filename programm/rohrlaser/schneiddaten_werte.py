"""Schneiddaten mit den mitgelieferten Richtwerten vergleichen, ohne Qt (Software-Audit 26.11.2026, Architektur A-01).
Vorher in schneiddaten_standard.py (Dialog); datenbank.schneiddaten_standard_setzen lud dadurch PySide6 nach.
schneiddaten_standard.py führt alle Namen unverändert weiter; Beschreibung des Vergleichs dort."""
from .stammdaten import LASER, SCHNEIDDATEN, beispieldaten, zahl_als_text

# Werte, die das Zurücksetzen auf den Standard setzt (die Schlüsselfelder bleiben)
WERTE = ("vorschub_gross", "vorschub_mittel", "vorschub_klein", "einstechzeit", "vorschub_gravur", "zeit_ecke",
         "bemerkung")
TITEL = {f.name: f.titel for f in SCHNEIDDATEN.felder}


def _leer(v):
    return v is None or v == ""


def schluessel(z):
    """(Maschine, Werkstoff-ID, Kategorie, Gas, Wandstärke bis) einer Zeile; leere Felder als None."""
    w = z.get("wand_bis")
    return (z.get("maschinen_id"), None if _leer(z.get("werkstoff_id")) else z["werkstoff_id"],
            None if _leer(z.get("kategorie")) else z["kategorie"], None if _leer(z.get("gas")) else z["gas"],
            round(float(w), 3) if isinstance(w, (int, float)) else w)


def standard_zeilen(maschinen=None):
    """Mitgelieferte Schneiddaten-Zeilen (dicts) der Maschinen (None = alle mit Richtwerten)."""
    return [z for z in beispieldaten()["schneiddaten"] if maschinen is None or z["maschinen_id"] in maschinen]


def standard_je_schluessel():
    """{schluessel: Standardzeile} aller Richtwerte (Markierung der abweichenden Zellen in der Tabelle)."""
    return {schluessel(z): z for z in standard_zeilen()}


def gleich(a, b):
    if _leer(a) and _leer(b):
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-9
    return a == b


def abweichungen(z, std):
    """{Feld: (jetzt, Standard)} der Werte, die von der Standardzeile abweichen."""
    return {f: (z.get(f), std.get(f)) for f in WERTE if not gleich(z.get(f), std.get(f))}


def vergleich(aktuell, maschinen=None, ids=None, eigene_behalten=False):
    """Was das Zurücksetzen ändern würde. aktuell = Zeilen der Tabelle (mit id). Umfang: ids (markierte Zeilen) oder
    maschinen (None = alle mit Richtwerten). Ergebnis dict(aendern=[(Zeile, {Feld: (jetzt, Standard)}, Standard)],
    gleich=Anzahl schon wie Standard, entfernen=[Zeile], ergaenzen=[Standardzeile], ohne_standard=[Zeile] (markierte
    oder behaltene eigene Zeilen ohne Richtwert, bleiben unverändert), maschinen=[betroffene Maschinen])."""
    if ids is not None:
        ids = set(ids)
        zeilen = [z for z in aktuell if z.get("id") in ids]
        maschinen = sorted({z.get("maschinen_id") for z in zeilen if z.get("maschinen_id") in LASER})
        std = {schluessel(s): s for s in standard_zeilen(maschinen)}
    else:
        maschinen = sorted(m for m in (maschinen if maschinen is not None else LASER) if m in LASER)
        std = {schluessel(s): s for s in standard_zeilen(maschinen)}
        zeilen = [z for z in aktuell if z.get("maschinen_id") in maschinen]
    out = dict(aendern=[], gleich=0, entfernen=[], ergaenzen=[], ohne_standard=[], maschinen=maschinen)
    gefunden = set()
    for z in zeilen:
        s = std.get(schluessel(z))
        if s is None:
            (out["ohne_standard"] if ids is not None or eigene_behalten else out["entfernen"]).append(z)
            continue
        gefunden.add(schluessel(z))
        ab = abweichungen(z, s)
        if ab:
            out["aendern"].append((z, ab, s))
        else:
            out["gleich"] += 1
    if ids is None:
        out["ergaenzen"] = [s for k, s in std.items() if k not in gefunden]
    return out


def zeile_text(z):
    """'T11 · Stahl · N₂ · bis 3 mm' bzw. mit Werkstoff-ID."""
    teile = [z.get("maschinen_id"), z.get("werkstoff_id") or z.get("kategorie"), z.get("gas")]
    w = z.get("wand_bis")
    teile.append(f"bis {zahl_als_text(w)} mm" if isinstance(w, (int, float)) else "")
    return " · ".join(str(t) for t in teile if t)


def wert_text(v):
    if _leer(v):
        return "leer"
    return zahl_als_text(v) if isinstance(v, (int, float)) else str(v)


def zusammenfassung(v):
    """Kurztext der Vorschau: Anzahl geänderte, entfernte, ergänzte, unveränderte Zeilen."""
    teile = [f"{len(v['aendern'])} Zeile(n) bekommen Standardwerte"]
    if v["entfernen"]:
        teile.append(f"{len(v['entfernen'])} eigene Zeile(n) werden entfernt")
    if v["ergaenzen"]:
        teile.append(f"{len(v['ergaenzen'])} fehlende Standardzeile(n) werden ergänzt")
    if v["ohne_standard"]:
        teile.append(f"{len(v['ohne_standard'])} Zeile(n) ohne Richtwert bleiben unverändert")
    teile.append(f"{v['gleich']} Zeile(n) sind schon Standard")
    return ", ".join(teile) + "."


def vorschau_zeilen(v):
    """[(Zeile, Was, Jetzt, Standard)] für die Vorschautabelle."""
    out = []
    for z, ab, _ in v["aendern"]:
        for f, (jetzt, std) in ab.items():
            out.append((zeile_text(z), TITEL.get(f, f), wert_text(jetzt), wert_text(std)))
    for z in v["entfernen"]:
        out.append((zeile_text(z), "eigene Zeile", "vorhanden", "wird entfernt"))
    for s in v["ergaenzen"]:
        out.append((zeile_text(s), "Standardzeile", "fehlt", "wird ergänzt"))
    for z in v["ohne_standard"]:
        out.append((zeile_text(z), "kein Richtwert", "bleibt", "unverändert"))
    return out
