"""Absagegrund und Angebots-Auswertung (Plan 29.10.2026 Schritt 1b, Marktvergleich A1).

Beim Vorgang „Abgelehnt“ fragt das Programm nach dem Grund (Liste GRUENDE), optional nach dem Preis des Wettbewerbs
und einer Bemerkung. Der Eintrag steht im Versandverlauf des Angebots (angebote.versand, art 'absage'), wie Nachfassen
und Wiedervorlage, ohne neue Spalte.

Die Auswertung zählt die eigenen Angebote eines Zeitraums je Kunde, Werkstoff-Kategorie, Preisklasse und
Absagegrund: Angebote, beauftragt, abgelehnt, offen, Trefferquote (beauftragt / entschieden) und Summen netto. So
sieht man, wo man zu teuer (viele Absagen „Preis zu hoch“) oder vielleicht zu billig ist (sehr hohe Trefferquote).
"""
import datetime

GRUENDE = ("Preis zu hoch", "Lieferzeit zu lang", "Kunde fertigt selbst", "Anderer Lieferant (Beziehung)",
           "Projekt verschoben oder gestrichen", "Technisch nicht passend", "Keine Rückmeldung", "Sonstiges")
OHNE_GRUND = "ohne Angabe"
PREISKLASSEN = ((500, "bis 500 €"), (2000, "500 bis 2.000 €"), (10000, "2.000 bis 10.000 €"), (None, "über 10.000 €"))
ZEITRAEUME = ((90, "letzte 90 Tage"), (365, "letzte 12 Monate"), (None, "alle"))
MISCH = "gemischt"


def eintrag(grund, bemerkung="", preis=None, heute=None):
    """Eintrag für den Versandverlauf."""
    e = dict(art="absage", datum=(heute or datetime.date.today()).isoformat(), grund=grund or OHNE_GRUND)
    if bemerkung:
        e["bemerkung"] = bemerkung
    if isinstance(preis, (int, float)) and not isinstance(preis, bool) and preis > 0:
        e["preis"] = float(preis)
    return e


def letzte(z):
    """Letzter Absage-Eintrag eines Angebots (Zeile der Angebotsliste oder Kopf) oder None."""
    alle = [e for e in z.get("versand") or () if isinstance(e, dict) and e.get("art") == "absage"]
    return alle[-1] if alle else None


def _vorgang(z):
    from .cockpit import _vorgang
    return _vorgang(z)


def _datum(text):
    try:
        return datetime.date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


def preisklasse(netto):
    if not isinstance(netto, (int, float)) or netto <= 0:
        return "ohne Preis"
    return next(t for grenze, t in PREISKLASSEN if grenze is None or netto <= grenze)


def kategorie_des_angebots(werkstoffe, kategorien):
    """Werkstoff-Kategorie eines Angebots aus seinen Werkstoffen: eine Kategorie, 'gemischt' oder 'ohne Werkstoff'."""
    kats = {kategorien.get(w) or "ohne Kategorie" for w in werkstoffe or ()}
    return "ohne Werkstoff" if not kats else kats.pop() if len(kats) == 1 else MISCH


def auswahl(zeilen, heute=None, zeitraum=90):
    """Eigene Angebote (ohne ersetzte Fassungen) mit Datum im Zeitraum (Tage, None = alle)."""
    heute = heute or datetime.date.today()
    ab = heute - datetime.timedelta(days=zeitraum) if zeitraum else None
    out = []
    for z in zeilen:
        if z.get("fremd") or z.get("ersetzt_durch"):
            continue
        d = _datum(z.get("datum")) or heute
        if d <= heute and (ab is None or d >= ab):
            out.append(z)
    return out


def _gruppe():
    return dict(angebote=0, beauftragt=0, abgelehnt=0, offen=0, summe=0.0, auftragswert=0.0, abgelehnt_wert=0.0)


def _zaehlen(g, z):
    v = _vorgang(z)
    netto = z.get("vk_netto") if isinstance(z.get("vk_netto"), (int, float)) else 0.0
    g["angebote"] += 1
    g["summe"] += netto
    if v == "Beauftragt":
        g["beauftragt"] += 1
        g["auftragswert"] += netto
    elif v == "Abgelehnt":
        g["abgelehnt"] += 1
        g["abgelehnt_wert"] += netto
    else:
        g["offen"] += 1


def _fertig(gruppen):
    out = []
    for name, g in gruppen.items():
        entschieden = g["beauftragt"] + g["abgelehnt"]
        out.append(dict(g, name=name, trefferquote=g["beauftragt"] / entschieden if entschieden else None,
                        summe=round(g["summe"], 2), auftragswert=round(g["auftragswert"], 2),
                        abgelehnt_wert=round(g["abgelehnt_wert"], 2)))
    return sorted(out, key=lambda g: (-g["angebote"], -g["summe"], str(g["name"])))


def auswertung(zeilen, werkstoffe_je_angebot=None, kategorien=None, heute=None, zeitraum=90):
    """Auswertung der Angebotsliste (Datenbank.angebote): dict(gesamt, kunde, kategorie, preisklasse, grund,
    wettbewerb) – je Gruppe [dict(name, angebote, beauftragt, abgelehnt, offen, trefferquote, summe, auftragswert,
    abgelehnt_wert)], 'grund' nur über die abgelehnten Angebote; wettbewerb = [dict(nummer, kunde, netto, preis,
    abstand)] der Absagen mit Wettbewerbspreis (abstand = unser Preis / Wettbewerb − 1)."""
    werkstoffe_je_angebot = werkstoffe_je_angebot or {}
    kategorien = kategorien or {}
    auswahl_ = auswahl(zeilen, heute, zeitraum)
    gesamt, kunde, kat, klasse, grund = _gruppe(), {}, {}, {}, {}
    wettbewerb = []
    for z in auswahl_:
        _zaehlen(gesamt, z)
        name = (z.get("kunde") or "").strip() or "ohne Kunde"
        _zaehlen(kunde.setdefault(name, _gruppe()), z)
        _zaehlen(kat.setdefault(kategorie_des_angebots(werkstoffe_je_angebot.get(z["id"]), kategorien), _gruppe()), z)
        _zaehlen(klasse.setdefault(preisklasse(z.get("vk_netto")), _gruppe()), z)
        if _vorgang(z) == "Abgelehnt":
            a = letzte(z)
            _zaehlen(grund.setdefault((a or {}).get("grund") or OHNE_GRUND, _gruppe()), z)
            netto = z.get("vk_netto")
            if a and a.get("preis") and isinstance(netto, (int, float)) and netto > 0:
                wettbewerb.append(dict(nummer=z.get("nummer"), kunde=z.get("kunde"), netto=netto, preis=a["preis"],
                                       abstand=netto / a["preis"] - 1))
    reihenfolge = [t for _, t in PREISKLASSEN] + ["ohne Preis"]
    return dict(gesamt=_fertig({"Gesamt": gesamt})[0], kunde=_fertig(kunde), kategorie=_fertig(kat),
                preisklasse=sorted(_fertig(klasse), key=lambda g: reihenfolge.index(g["name"])),
                grund=_fertig(grund), wettbewerb=wettbewerb, zeitraum=zeitraum)
