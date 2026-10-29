"""Cockpit der Startseite (Layout-Plan L21, Plan A9): Wiedervorlagen, Pipeline je Vorgang und Kennzahlen (nur Admin).

Alles wird aus der Angebotsliste (Datenbank.angebote) gerechnet, damit die Summen hier genau denen der
Angebotsliste entsprechen: Verkaufspreis netto ist der beim letzten Öffnen gemerkte Wert (vk_netto).
"""
import datetime

from .datenbank import VORGAENGE

VORLAUF_TAGE = 7            # Wiedervorlage: verschickte Angebote, deren Gültigkeit in so vielen Tagen endet
ZEITRAUM_TAGE = 90          # Kennzahlen: Angebote mit Datum in den letzten so vielen Tagen


def _vorgang(z):
    if z.get("ersetzt_durch"):          # alte Fassung (W10): zählt in keinem Vorgang, keine Wiedervorlage
        return "Ersetzt"
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


class Wiedervorlage(tuple):
    """(Zeile, fällig am, Resttage) wie bisher, dazu gruende [Text] und bis (Gültig bis); Resttage < 0 = überfällig."""

    def __new__(cls, z, faellig, rest, gruende, bis):
        w = super().__new__(cls, (z, faellig, rest))
        w.gruende, w.bis = gruende, bis
        return w

    @property
    def z(self):
        return self[0]

    @property
    def faellig(self):
        return self[1]

    @property
    def rest(self):
        return self[2]


def verlauf(z):
    """Aus dem Versandverlauf (angebote.versand): (zuletzt verschickt, zuletzt nachgefasst, Wiedervorlage von Hand)
    als Datum oder None. Einträge: Angebots-PDF bzw. „als verschickt markiert“ (ohne art), art 'nachgefasst',
    art 'wiedervorlage' mit am (None = entfernt)."""
    versandt = nachgefasst = wv = None
    for e in z.get("versand") or ():
        if not isinstance(e, dict):
            continue
        d = _datum(e.get("datum"))
        art = e.get("art")
        if art == "nachgefasst":
            nachgefasst = max(nachgefasst, d) if nachgefasst and d else d or nachgefasst
        elif art == "wiedervorlage":
            wv = _datum(e.get("am"))
        elif art in ("csv", "absage", "ab"):  # CSV-Export, Absagegrund, Auftragsbestätigung: kein Versand
            continue
        elif d:
            versandt = max(versandt, d) if versandt else d
    return versandt, nachgefasst, wv


def wiedervorlagen(zeilen, tage, heute=None, vorlauf=VORLAUF_TAGE, nachfassen=0):
    """Eigene Angebote zum Nachfassen (Plan A9), nach Fälligkeit: [Wiedervorlage]. Gründe:
    - verschickt, Gültigkeit abgelaufen oder endet in vorlauf Tagen
    - verschickt und seit nachfassen Tagen (0 = aus) ohne Entscheidung, gerechnet ab dem letzten Versand bzw.
      Nachfassen
    - Wiedervorlage von Hand (Entwurf oder verschickt) erreicht; sie ersetzt bis dahin das automatische Nachfassen."""
    heute = heute or datetime.date.today()
    try:
        tage = int(tage or 0)
    except (TypeError, ValueError):
        tage = 0
    aus = []
    for z in zeilen:
        d = _datum(z.get("datum"))
        v = _vorgang(z)
        if z.get("fremd") or d is None or v not in ("Entwurf", "Verschickt"):
            continue
        versandt, nachgefasst, wv = verlauf(z)
        bis = d + datetime.timedelta(days=tage)
        faellig, gruende = [], []
        if v == "Verschickt" and (bis - heute).days <= vorlauf:
            faellig.append(bis)
            gruende.append(f"gültig bis {bis.strftime('%d.%m.%Y')}")
        if wv is not None:
            if wv <= heute:
                faellig.append(wv)
                gruende.append(f"Wiedervorlage {wv.strftime('%d.%m.%Y')}")
        elif v == "Verschickt" and nachfassen:
            basis = max(x for x in (versandt or d, nachgefasst) if x)
            seit = (heute - basis).days
            if seit >= nachfassen:
                faellig.append(basis + datetime.timedelta(days=nachfassen))
                gruende.append(f"seit {seit} Tagen ohne Antwort" + (
                    f" (nachgefasst am {nachgefasst.strftime('%d.%m.%Y')})" if nachgefasst else ""))
        if faellig:
            f = min(faellig)
            aus.append(Wiedervorlage(z, f, (f - heute).days, gruende, bis))
    return sorted(aus, key=lambda w: w.faellig)


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
