"""Cockpit der Startseite (Layout-Plan L21): Wiedervorlagen, Pipeline je Vorgang und Kennzahlen (nur Admin).

Alles wird aus der Angebotsliste (Datenbank.angebote) gerechnet, damit die Summen hier genau denen der
Angebotsliste entsprechen: Verkaufspreis netto ist der beim letzten Öffnen gemerkte Wert (vk_netto).
"""
import datetime

from .datenbank import VORGAENGE

VORLAUF_TAGE = 7            # Wiedervorlage: verschickte Angebote, deren Gültigkeit in so vielen Tagen endet
ZEITRAUM_TAGE = 90          # Kennzahlen: Angebote mit Datum in den letzten so vielen Tagen


def _vorgang(z):
    return z.get("vorgang") or VORGAENGE[0]


def _datum(text):
    try:
        return datetime.date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


def _betrag(z):
    v = z.get("vk_netto")
    return v if isinstance(v, (int, float)) else 0.0


def pipeline(zeilen):
    """[(Vorgang, Anzahl, Summe Verkaufspreis netto)] in der Reihenfolge der Vorgänge (eigene Angebote)."""
    aus = []
    for v in VORGAENGE:
        auswahl = [z for z in zeilen if _vorgang(z) == v and not z.get("fremd")]
        aus.append((v, len(auswahl), round(sum(_betrag(z) for z in auswahl), 2)))
    return aus


def wiedervorlagen(zeilen, tage, heute=None, vorlauf=VORLAUF_TAGE):
    """Verschickte eigene Angebote, deren Gültigkeit abgelaufen ist oder in vorlauf Tagen endet, nach Datum:
    [(Zeile, Gültig bis, Resttage)]; Resttage < 0 = abgelaufen."""
    heute = heute or datetime.date.today()
    try:
        tage = int(tage or 0)
    except (TypeError, ValueError):
        tage = 0
    aus = []
    for z in zeilen:
        d = _datum(z.get("datum"))
        if _vorgang(z) != "Verschickt" or z.get("fremd") or d is None:
            continue
        bis = d + datetime.timedelta(days=tage)
        rest = (bis - heute).days
        if rest <= vorlauf:
            aus.append((z, bis, rest))
    return sorted(aus, key=lambda x: x[1])


def kennzahlen(zeilen, heute=None, zeitraum=ZEITRAUM_TAGE):
    """Kennzahlen der eigenen Angebote mit Datum in den letzten zeitraum Tagen (vordatierte zählen nicht mit)."""
    heute = heute or datetime.date.today()
    ab = heute - datetime.timedelta(days=zeitraum)
    auswahl = [z for z in zeilen if not z.get("fremd") and ab <= (_datum(z.get("datum")) or heute) <= heute]
    beauftragt = [z for z in auswahl if _vorgang(z) == "Beauftragt"]
    abgelehnt = [z for z in auswahl if _vorgang(z) == "Abgelehnt"]
    entschieden = len(beauftragt) + len(abgelehnt)
    werte = [_betrag(z) for z in auswahl if _betrag(z)]
    return dict(zeitraum=zeitraum, angebote=len(auswahl), summe=round(sum(werte), 2),
                durchschnitt=round(sum(werte) / len(werte), 2) if werte else None,
                beauftragt=len(beauftragt), auftragswert=round(sum(_betrag(z) for z in beauftragt), 2),
                trefferquote=round(len(beauftragt) / entschieden, 3) if entschieden else None)
