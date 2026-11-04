"""Referenzangebote als Prüfrechnung (Optimierungsplan 04.11.2026, D1).

Bis zu fünf typische, bestätigte Angebote werden mit ihrem Verkaufspreis festgehalten (Menü Ausgaben → „Als
Referenzangebot festhalten“). Hilfe → „Referenzangebote prüfen …“ rechnet sie mit dem heutigen Programm und den
heutigen Stammdaten neu und zeigt je Angebot: gleich oder Abweichung in %. So fällt nach einem Update oder einer
Stammdaten-Änderung sofort auf, wenn sich Preise ungewollt verschieben. Gespeichert in der Einstellung
'referenzangebote' (Liste von dict(angebot_id, nummer, kunde, verkauf, am)).
"""
import datetime

EINSTELLUNG = "referenzangebote"
HOECHSTENS = 5
GLEICH_BIS = 0.005      # bis 0,5 Prozent Unterschied gilt als gleich (Rundung)


def liste(db):
    """Festgehaltene Referenzangebote, deren Angebot es noch gibt."""
    return [r for r in db.einstellung(EINSTELLUNG) or () if isinstance(r, dict) and db.angebot(r.get("angebot_id"))]


def ist_referenz(db, angebot_id):
    return any(r["angebot_id"] == angebot_id for r in liste(db))


def verkauf(db, angebot_id):
    """Verkaufspreis (netto, alle aktiven Positionen) wie im Angebotsfenster, frisch optimiert und gerechnet."""
    from . import preis_simulator, rechnen
    from .angebot import aktiv
    a = db.angebot(angebot_id)
    pos = [p for p in db.positionen(angebot_id) if aktiv(p)]
    k, tab, e = preis_simulator.grundlage(db, a)
    erg = rechnen.optimieren(a, pos, k, tab, e)
    _zeilen, s = rechnen.kalkulation(a, pos, erg, k, tab, e)
    return round(float(s.get("verkauf") or 0), 2)


def festhalten(db, angebot_id, jetzt=None):
    """Angebot mit seinem heutigen Verkaufspreis als Referenz festhalten (ersetzt einen alten Stand desselben
    Angebots). Mehr als HOECHSTENS: das älteste fällt heraus. Ergebnis: der neue Eintrag."""
    a = db.angebot(angebot_id)
    r = dict(angebot_id=angebot_id, nummer=a.get("nummer") or "", kunde=a.get("kunde") or "",
             verkauf=verkauf(db, angebot_id), am=(jetzt or datetime.datetime.now()).isoformat(timespec="minutes"))
    alle = [x for x in liste(db) if x["angebot_id"] != angebot_id] + [r]
    db.einstellung_setzen(EINSTELLUNG, alle[-HOECHSTENS:])
    return r


def entfernen(db, angebot_id):
    db.einstellung_setzen(EINSTELLUNG, [x for x in liste(db) if x["angebot_id"] != angebot_id])


def pruefen(db):
    """Alle Referenzangebote neu rechnen: [dict(Eintrag, neu, prozent, status='gleich' | 'abweichung' | 'fehler',
    fehler)]."""
    out = []
    for r in liste(db):
        try:
            neu = verkauf(db, r["angebot_id"])
        except Exception as f:          # Prüfrechnung darf nie abbrechen
            out.append(dict(r, neu=None, prozent=None, status="fehler", fehler=f"{type(f).__name__}: {f}"))
            continue
        alt = float(r.get("verkauf") or 0)
        prozent = 100 * (neu - alt) / alt if alt else (0.0 if neu == alt else None)
        gleich = prozent is not None and abs(prozent) <= 100 * GLEICH_BIS
        out.append(dict(r, neu=neu, prozent=prozent, status="gleich" if gleich else "abweichung", fehler=""))
    return out


def text(ergebnis):
    """Kurztext für Meldung und Anleitung, z. B. '5 Referenzangebote: 4 gleich, 1 abweichend'."""
    if not ergebnis:
        return "Keine Referenzangebote festgehalten (Angebot öffnen → Ausgaben → Als Referenzangebot festhalten)."
    n = {s: sum(1 for e in ergebnis if e["status"] == s) for s in ("gleich", "abweichung", "fehler")}
    teile = [f"{n['gleich']} gleich"] + ([f"{n['abweichung']} abweichend"] if n["abweichung"] else []) + \
        ([f"{n['fehler']} nicht rechenbar"] if n["fehler"] else [])
    return f"{len(ergebnis)} Referenzangebot{'e' if len(ergebnis) != 1 else ''}: " + ", ".join(teile)
