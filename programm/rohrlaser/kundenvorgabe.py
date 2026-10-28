"""Vorgaben je Kunde (Plan Arbeitsabläufe W2, Tabelle kundenvorgaben): Kopfwerte neuer Angebote und Standard-Staffeln.

Beim Anlegen eines Angebots für einen Kunden gehen die Vorgaben den Einstellungen vor. Beim Wählen des Kunden in einem
Angebot (Datenbank.kunde_uebernehmen) ersetzt eine Vorgabe ein Kopffeld nur, solange es leer ist oder noch die
Vorgabe aus den Einstellungen bzw. des vorher gewählten Kunden hat; von Hand geänderte Werte bleiben. Leere Felder der
Kundenvorgabe = Einstellungen.
"""
from .angebot import lieferzeit_wert

FELDER = ("maschine", "stange", "gewinn", "lieferzeit_art", "lieferzeit_wert", "lieferzeit_zusatz", "material_vorgabe")
LIEFERZEIT = ("lieferzeit_art", "lieferzeit_wert", "lieferzeit_zusatz")


def fuer_kunde(db, kundennr):
    """Zeile der Kundenvorgaben des Kunden oder None."""
    if kundennr in (None, ""):
        return None
    return next((z for z in db.zeilen("kundenvorgaben") if str(z.get("kundennr")) == str(kundennr)), None)


def kopfwerte(db, kundennr, datum=None):
    """Gefüllte Vorgaben des Kunden als Kopfwerte {Feld: Wert}. Lieferzeit nur, wenn der Wert zur Art passt."""
    v = fuer_kunde(db, kundennr) or {}
    out = {n: v[n] for n in FELDER if v.get(n) not in (None, "") and n not in LIEFERZEIT}
    if v.get("lieferzeit_art"):
        try:
            out.update(lieferzeit_art=v["lieferzeit_art"],
                       lieferzeit_wert=lieferzeit_wert(v["lieferzeit_art"], v.get("lieferzeit_wert"), datum))
        except ValueError:
            pass
    if str(v.get("lieferzeit_zusatz") or "").strip():
        out["lieferzeit_zusatz"] = v["lieferzeit_zusatz"].strip()
    return out


def staffeln_text(db, kundennr):
    """Faktoren der Standard-Staffeln: aus der Kundenvorgabe, sonst aus der Einstellung 'staffeln_standard'."""
    t = str((fuer_kunde(db, kundennr) or {}).get("staffeln") or "").strip()
    return t or db.einstellung("staffeln_standard")


def gleich(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-9
    return (a if a not in ("",) else None) == (b if b not in ("",) else None)


def ersetzen(kopf, neu, *frueher):
    """Felder aus neu, die im Kopf noch leer sind oder einen der früheren Vorgabewerte haben (frueher: dicts, z. B.
    Einstellungen und vorheriger Kunde). Die Lieferzeit zählt als ein Feld (Art, Wert, Freitext zusammen).
    Ergebnis: {Feld: neuer Wert}, nur echte Änderungen."""
    out = {}
    for n in FELDER:
        if n in LIEFERZEIT or n not in neu:
            continue
        alt = kopf.get(n)
        if (alt in (None, "") or any(n in f and gleich(alt, f[n]) for f in frueher)) and not gleich(alt, neu[n]):
            out[n] = neu[n]
    if any(n in neu for n in LIEFERZEIT):
        jetzt = tuple(kopf.get(n) for n in LIEFERZEIT)
        ziel = tuple(neu.get(n, f_alt) for n, f_alt in zip(LIEFERZEIT, jetzt, strict=True))
        unberuehrt = all(w in (None, "") for w in jetzt) or any(
            all(gleich(kopf.get(n), f.get(n)) for n in LIEFERZEIT) for f in frueher)
        if unberuehrt and ziel != jetzt:
            out.update({n: w for n, w in zip(LIEFERZEIT, ziel, strict=True)})
    return out
