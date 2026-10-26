"""Sichtbarkeit von Feldern, Kennzahlen und Spalten: Nullwerte und leere optionale Werte ausblenden.

Nur die Anzeige wird gesteuert; gespeicherte Werte, Rechnung und Ausgaben (PDF, CSV) bleiben unverändert.

Rollen:
- PFLICHT, STAMM, MASCHINE: immer sichtbar, auch wenn der Wert 0 oder leer ist (Pflichtfelder, Stammdaten des
  Angebots, sicherheitsrelevante Maschinenparameter).
- SUMME: Ergebnis (Herstellkosten, Verkaufspreis), immer sichtbar.
- OPTIONAL: optionale Kosten, Zuschläge, Zusatzleistungen und Sonderparameter; bei 0 oder leer ausgeblendet.

Ob ein Wert null ist, entscheidet der Zahlenwert, nicht der Text: '0,00 €' und '0 %' sind null, '10,00 €' nicht.
"""
import re

PFLICHT, STAMM, MASCHINE, SUMME, OPTIONAL = "pflicht", "stamm", "maschine", "summe", "optional"
IMMER = {PFLICHT, STAMM, MASCHINE, SUMME}

# Rollen der Felder im Angebotskopf (angebot.KOPF)
KOPF_ROLLEN = {
    "nummer": PFLICHT, "maschine": PFLICHT, "stange": PFLICHT,
    "kundennr": STAMM, "kunde": STAMM, "datum": STAMM, "bemerkung": STAMM,
    "fracht": OPTIONAL, "skonto": OPTIONAL, "skonto_tage": OPTIONAL, "zahlungsziel": OPTIONAL,
    "zuschlag_fremdleistung": OPTIONAL, "aufschlag_blech": OPTIONAL, "aufschlag_zukauf": OPTIONAL,
    "gewinn": OPTIONAL, "ruesten_abmessung": OPTIONAL, "pauschale_abmessung": OPTIONAL,
    "programmierung_zeit": OPTIONAL, "programmierung_kontur": OPTIONAL, "programmierung_teil": OPTIONAL, "angebotsaufschlag": OPTIONAL,
    "handling_beistellung": OPTIONAL, "material_vorgabe": STAMM,
    "kundenreferenz": STAMM, "lieferzeit_art": STAMM, "lieferzeit_wert": STAMM, "lieferzeit_zusatz": STAMM,
    "bearbeiter": STAMM,
}

_ZAHL = re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$|^[+-]?\d+(\.\d+)?$")


def zahl(wert):
    """Zahlenwert einer Zahl oder eines formatierten Textes ('1.234,50 €', '10 %', '0,00'), sonst None.
    Texte, die außer Einheit und Leerzeichen noch anderes enthalten ('2 × 15 min', 'OK'), sind keine Zahl."""
    if isinstance(wert, bool) or wert is None:
        return None
    if isinstance(wert, (int, float)):
        return float(wert)
    t = re.sub(r"\s*(€|%|EUR|mm|min|kg|Stk|s|h|m)\s*$", "", str(wert).strip()).replace(" ", "").replace(" ", "")
    if not _ZAHL.match(t):
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    return float(t)


def ist_leer(wert):
    return wert is None or (isinstance(wert, str) and not wert.strip())


def ist_null(wert, genauigkeit=0.005):
    """True, wenn der Wert eine Zahl ist, die gerundet (Vorgabe: auf Cent bzw. 2 Stellen) 0 ergibt."""
    z = zahl(wert)
    return z is not None and abs(z) < genauigkeit


def ohne_wert(wert):
    """Leer oder numerisch null."""
    return ist_leer(wert) or ist_null(wert)


def sichtbar(wert, rolle=OPTIONAL):
    """Soll ein Feld bzw. eine Kennzahl mit diesem Wert angezeigt werden?"""
    return rolle in IMMER or not ohne_wert(wert)


def spalte_sichtbar(werte, rolle=OPTIONAL):
    """Spalte zeigen, wenn sie Pflicht ist oder mindestens eine Zeile einen Wert hat."""
    return rolle in IMMER or any(not ohne_wert(w) for w in werte)


def kopf_sichtbar(name, wert):
    return sichtbar(wert, KOPF_ROLLEN.get(name, STAMM))
