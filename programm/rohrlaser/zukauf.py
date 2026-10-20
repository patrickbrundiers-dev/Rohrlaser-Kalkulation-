"""Zukaufartikel: Tabellen und Rechenkern (Einkaufspreis, Bestellmenge, Einstandspreis, Aufschlag, Verkaufspreis).

Alle Preisformeln für Zukaufteile stehen hier; die Oberfläche (Vorschau, Angebot, Staffeln) ruft nur diese
Funktionen auf. Gerechnet wird mit Decimal und ungerundet; gerundet wird nur für die Anzeige (runden()) und am
Ende der Kalkulation wie bisher kaufmännisch (ausgabe.kaufm_runden).

Rechenweg je Artikel und Angebot (bzw. Mengenstufe):
  Verbrauch      = Σ Menge je Teil × Stückzahl der Positionen, die den Artikel mit gleichem Preisstand verwenden
  Bestellmenge   = max(Verbrauch, Mindestbestellmenge), aufgerundet auf die Verpackungseinheit
  EK je Einheit  = Staffelpreis für die Bestellmenge / Preiseinheit × (1 − Rabatt)
  Einkauf        = Bestellmenge × EK je Einheit (Rest ins Lager: Verbrauch × EK je Einheit)
  Bezugskosten   = Verpackung + Mindermengenzuschlag + Fracht + weitere (je Bestellung) + Fracht je Einheit ×
                   Bestellmenge, einmal je Bestellung (Rest ins Lager: anteilig Verbrauch / Bestellmenge)
  Einstand       = Einkauf + Bezugskosten
  Aufschlag      = nach der Aufschlagsregel (Position > Artikel individuell > Kategorie > Standard der Anwendung)
  Verkaufspreis  = Einstand + Aufschlag
Einstand, Aufschlag und Verkaufspreis werden nach dem Verbrauch auf die Positionen verteilt. Ein Aufschlag ist
nicht dasselbe wie eine Marge: 20 % Aufschlag auf 10,00 € ergibt 12,00 €, 20 % Zielmarge ergibt 12,50 €.
"""
import datetime
import hashlib
import json
import math
from decimal import Decimal, ROUND_HALF_UP

from .stammdaten import (TABELLE, VERWEISE, ZUKAUF_METHODEN, ZUKAUF_QUELLEN, ZUKAUF_STATUS, ZUKAUF_TYPEN, Feld,
                         Tabelle)

# ------------------------------------------------------------------ Auswahllisten
EINHEITEN = ("Stück", "Meter", "Kilogramm", "Satz")
EINHEIT_KURZ = {"Stück": "St", "Meter": "m", "Kilogramm": "kg", "Satz": "Satz"}
STATUS = ZUKAUF_STATUS
METHODEN = ZUKAUF_METHODEN
PROZENT, JE_EINHEIT, JE_BESTELLUNG, STAFFEL, MARGE = METHODEN
METHODE_TEXT = {PROZENT: "Aufschlag in % auf den Einstandspreis",
                JE_EINHEIT: "fester Aufschlag in € je Einheit",
                JE_BESTELLUNG: "fester Aufschlag in € je Bestellung (einmal je Angebot bzw. Staffel)",
                STAFFEL: "Aufschlag in % auf den Einstandspreis, gestaffelt nach Verbrauchsmenge",
                MARGE: "Zielmarge in % vom Verkaufspreis: VK = Einstand / (1 − Marge)"}
QUELLEN = ZUKAUF_QUELLEN       # Wahl am Artikel; leer = Kategorie
KATEGORIE, INDIVIDUELL, STANDARD = QUELLEN
POSITION = "Position"
# Startliste der Kategorien (nur Namen, ohne Aufschläge: die trägt der Anwender selbst ein)
KATEGORIEN_START = ("Blechteile", "Schrauben und Muttern", "Normteile", "Kaufteile", "Fremdfertigung",
                    "Profile und Rohre", "Sonstige Zukaufartikel")

ARTIKEL = Tabelle(
    "zukauf_artikel", "Zukaufartikel",
    (Feld("artikelnr", "Artikelnummer", breite=110),
     Feld("bezeichnung", "Artikelbezeichnung", pflicht=True, breite=200),
     Feld("kategorie", "Kategorie", "auswahl", auswahl="zukaufkategorie", breite=140),
     Feld("beschreibung", "Beschreibung", breite=200),
     Feld("einheit", "Mengeneinheit", breite=80),
     Feld("ean", "EAN / Referenzcode", breite=120),
     Feld("status", "Status", "auswahl", auswahl="zukaufstatus", breite=80),
     Feld("aufschlag_quelle", "Aufschlag aus", "auswahl", auswahl="zukaufquelle", breite=90),
     Feld("aufschlag_methode", "Aufschlagsmethode", "auswahl", auswahl="zukaufmethode", breite=130),
     Feld("aufschlag_wert", "Aufschlag [% bzw. €]", "zahl", 0, 1000000, stellen=2, breite=80),
     Feld("aufschlag_staffel", "Aufschlagsstaffel", breite=150),          # JSON [{ab, wert}]
     Feld("kombiniert", "Kategorie + individuell kombinieren", "auswahl", auswahl="janein", breite=80),
     Feld("rest_lager", "Mehrmenge geht ins Lager", "auswahl", auswahl="janein", breite=80),
     Feld("angebotstext", "Im Angebotstext nennen", "auswahl", auswahl="janein", breite=80),
     Feld("bemerkung", "Bemerkung", breite=200),
     # Blechteile (Schema 20): Maße, Werkstoff und Herkunft; vom STEP-Import angelegt oder von Hand eingetragen
     Feld("artikeltyp", "Artikeltyp", "auswahl", auswahl="zukauftyp", breite=70),
     Feld("laenge", "Länge [mm]", "zahl", 0, 100000, stellen=1, breite=70),
     Feld("breite", "Breite [mm]", "zahl", 0, 100000, stellen=1, breite=70),
     Feld("dicke", "Dicke [mm]", "zahl", 0, 1000, stellen=2, breite=60),
     Feld("werkstoff", "Werkstoff", breite=110),
     Feld("herkunft", "Angelegt aus", breite=90),
     Feld("step_datei", "STEP-Datei", breite=200),
     Feld("fingerabdruck", "Geometrie-Kennung", breite=120),
     Feld("angelegt", "Angelegt", breite=130),
     Feld("geaendert", "Geändert", breite=130)),
    (),
    "Zukaufartikel mit Einkaufspreisen je Lieferant und eigener Aufschlagsregel.")

KATEGORIEN = Tabelle(
    "zukauf_kategorien", "Kategorien",
    (Feld("name", "Kategorie", pflicht=True, breite=180),
     Feld("aufschlag_methode", "Standard-Aufschlagsmethode", "auswahl", auswahl="zukaufmethode", breite=140),
     Feld("aufschlag_wert", "Standardaufschlag [% bzw. €]", "zahl", 0, 1000000, stellen=2, breite=100),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("beschreibung", "Beschreibung", breite=300)),
    ("name",),
    "Kategorien der Zukaufartikel mit Standardaufschlag. Neue Artikel übernehmen den Aufschlag ihrer Kategorie; "
    "Artikel mit individuellem Aufschlag ändern sich nicht, wenn hier ein Wert geändert wird. Leer = es gilt der "
    "Standardaufschlag der Einstellungen. Methoden: % auf Einstand, € je Einheit, € je Bestellung, Zielmarge % "
    "(Mengenstaffeln nur am Artikel). Gespeicherte Angebote behalten ihren Preisstand.")

LIEFERANTEN = Tabelle(
    "zukauf_lieferanten", "Lieferanten",
    (Feld("name", "Lieferant", pflicht=True, breite=180),
     Feld("lieferantennr", "Lieferantennummer", breite=110),
     Feld("ansprechpartner", "Ansprechpartner", breite=140),
     Feld("telefon", "Telefon", breite=110),
     Feld("email", "E-Mail", breite=170),
     Feld("lieferzeit", "Lieferzeit [Tage]", "ganz", 0, 3650, breite=75),
     Feld("bemerkung", "Bemerkung", breite=250)),
    ("name",),
    "Lieferanten der Zukaufartikel. Preise, Mindestmengen und Lieferzeiten je Artikel stehen beim Artikel.")

BEZUG = Tabelle(
    "zukauf_bezug", "Einkauf je Lieferant",
    (Feld("artikel_id", "Artikel", "ganz", breite=60),
     Feld("lieferant", "Lieferant", "auswahl", auswahl="zukauflieferant", breite=150),
     Feld("lieferanten_artnr", "Lieferantenartikelnummer", breite=130),
     Feld("bevorzugt", "Bevorzugt", "auswahl", auswahl="janein", breite=60),
     Feld("preiseinheit", "Preiseinheit [Menge]", "zahl", 0.0001, 1000000, stellen=4, breite=80),
     Feld("preise", "Einkaufspreise", breite=150),                          # JSON [{ab, preis}] je Preiseinheit
     Feld("mindestmenge", "Mindestbestellmenge", "zahl", 0, 100000000, stellen=3, breite=80),
     Feld("vpe", "Verpackungseinheit", "zahl", 0, 100000000, stellen=3, breite=80),
     Feld("lieferzeit", "Lieferzeit [Tage]", "ganz", 0, 3650, breite=70),
     Feld("verpackung", "Verpackung je Bestellung [€]", "zahl", 0, 1000000, stellen=2, breite=80),
     Feld("mindermenge", "Mindermengenzuschlag [€]", "zahl", 0, 1000000, stellen=2, breite=80),
     Feld("mindermenge_bis", "Mindermengenzuschlag unter [Menge]", "zahl", 0, 100000000, stellen=3, breite=80),
     Feld("fracht", "Eingangsfracht je Bestellung [€]", "zahl", 0, 1000000, stellen=2, breite=80),
     Feld("fracht_einheit", "Eingangsfracht je Einheit [€]", "zahl", 0, 1000000, stellen=4, breite=80),
     Feld("weitere", "Weitere Bezugskosten je Bestellung [€]", "zahl", 0, 1000000, stellen=2, breite=80),
     Feld("rabatt", "Mengenrabatt [%]", "zahl", 0, 100, stellen=2, breite=70),
     Feld("gueltig_von", "Preis gültig von", "datum", breite=90),
     Feld("gueltig_bis", "Preis gültig bis", "datum", breite=90)),
    (),
    "Einkaufsbedingungen eines Artikels bei einem Lieferanten.")

HISTORIE = Tabelle(
    "zukauf_historie", "Preisänderungen",
    (Feld("datum", "Datum", breite=130),
     Feld("artikel_id", "Artikel-ID", "ganz", breite=60),
     Feld("artikel", "Artikel", breite=200),
     Feld("lieferant", "Lieferant", breite=150),
     Feld("feld", "Was", breite=150),
     Feld("alt", "Alt", breite=110),
     Feld("neu", "Neu", breite=110),
     Feld("bemerkung", "Bemerkung", breite=200)),
    (),
    "Protokoll aller Änderungen an Einkaufspreisen und Aufschlägen.")

TABELLEN = (ARTIKEL, KATEGORIEN, LIEFERANTEN, BEZUG, HISTORIE)
# Kategorien und Lieferanten lassen sich wie Stammdaten pflegen (fenster.StammdatenSeite); Umbenennen ändert die
# Verweise in Artikeln und Einkaufsbedingungen mit
TABELLE.update({t.name: t for t in TABELLEN})
VERWEISE.update({("zukauf_kategorien", "name"): (("zukauf_artikel", "kategorie"),),
                 ("zukauf_lieferanten", "name"): (("zukauf_bezug", "lieferant"),)})


# ------------------------------------------------------------------ Hilfen
def dez(w):
    """Zahl als Decimal (None, leer, Text und bool -> None)."""
    if w is None or isinstance(w, bool) or w == "":
        return None
    if isinstance(w, Decimal):
        return w
    if isinstance(w, (int, float)):
        return Decimal(repr(float(w))) if isinstance(w, float) else Decimal(w)
    try:
        return Decimal(str(w).replace(",", "."))
    except ArithmeticError:
        return None


def _d(w):
    return dez(w) or Decimal(0)


NULL = Decimal(0)
HUNDERT = Decimal(100)
STELLEN_EINHEIT = 4      # Einheitspreise (z. B. 0,0835 € je Schraube)
STELLEN_BETRAG = 2       # Beträge


def runden(w, stellen=STELLEN_BETRAG):
    """Zentrale Rundung für die Anzeige: kaufmännisch (halbe Einheit von null weg)."""
    if w is None:
        return None
    return float(_d(w).quantize(Decimal(1).scaleb(-stellen), rounding=ROUND_HALF_UP))


def json_liste(roh):
    """JSON-Text oder Liste -> Liste von dicts (ungültig -> [])."""
    if not roh:
        return []
    try:
        liste = json.loads(roh) if isinstance(roh, str) else roh
    except ValueError:
        return []
    return [e for e in liste if isinstance(e, dict)] if isinstance(liste, list) else []


def staffel_sortiert(roh, wert="preis"):
    """Staffel [{ab, preis bzw. wert}] aufsteigend nach ab; Zeilen ohne Wert fallen weg; ab leer = 0."""
    out = []
    for e in json_liste(roh):
        if dez(e.get(wert)) is None:
            continue
        out.append(dict(ab=_d(e.get("ab")), **{wert: dez(e.get(wert))}))
    return sorted(out, key=lambda e: e["ab"])


def staffel_fehler(roh, wert="preis"):
    """Prüfung einer Staffel: [Meldung] (negative Werte, doppelte Grenzen)."""
    out, gesehen = [], set()
    for e in json_liste(roh):
        ab, w = dez(e.get("ab")), dez(e.get(wert))
        if ab is not None and ab < 0:
            out.append("Staffelgrenze darf nicht negativ sein")
        if w is not None and w < 0:
            out.append("Preis darf nicht negativ sein" if wert == "preis" else "Aufschlag darf nicht negativ sein")
        if w is None and ab is not None:
            out.append("Staffel: Wert fehlt")
        if ab is not None:
            if ab in gesehen:
                out.append("Staffelgrenze doppelt")
            gesehen.add(ab)
    return out


def staffel_text(roh, wert="preis"):
    """Staffel als Text, z. B. 'ab 1: 1,20 | ab 100: 0,95' (Protokoll, Übersicht)."""
    def w(x):
        t = _zahl(x)
        return t + (",00" if "," not in t else "0" if len(t.split(",")[1]) == 1 else "") if wert == "preis" else t
    return " | ".join(f"ab {_zahl(e['ab'])}: {w(e[wert])}" for e in staffel_sortiert(roh, wert))


def staffel_wahl(staffel, menge):
    """Staffelzeile für die Menge: die mit der größten Grenze ab ≤ Menge; liegt die Menge unter allen Grenzen,
    die erste Zeile. None ohne Staffel."""
    if not staffel:
        return None
    m = _d(menge)
    gueltig = [e for e in staffel if e["ab"] <= m]
    return gueltig[-1] if gueltig else staffel[0]


def bestellmenge(verbrauch, mindestmenge=None, vpe=None):
    """Bestellmenge: mindestens die Mindestbestellmenge, aufgerundet auf ganze Verpackungseinheiten."""
    m = max(_d(verbrauch), _d(mindestmenge))
    v = _d(vpe)
    if v > 0 and m > 0:
        m = Decimal(math.ceil(m / v)) * v
    return m


def ek_je_einheit(bezug, menge):
    """Einkaufspreis je Mengeneinheit für die Bestellmenge: Staffelpreis / Preiseinheit × (1 − Rabatt).
    Beispiel: 12,00 € für 100 Stück -> 0,12 € je Stück. Ergebnis (Preis, Staffelzeile) oder (None, None)."""
    zeile = staffel_wahl(staffel_sortiert(bezug.get("preise")), menge)
    if zeile is None:
        return None, None
    pe = dez(bezug.get("preiseinheit")) or Decimal(1)
    return zeile["preis"] / pe * (1 - _d(bezug.get("rabatt")) / HUNDERT), zeile


def bezugskosten(bezug, bestellt):
    """Bezugskosten einer Bestellung (einmal je Bestellung): {Bezeichnung: Betrag}."""
    b = {"Verpackung": _d(bezug.get("verpackung")),
         "Eingangsfracht": _d(bezug.get("fracht")) + _d(bezug.get("fracht_einheit")) * _d(bestellt),
         "Weitere Bezugskosten": _d(bezug.get("weitere"))}
    grenze = dez(bezug.get("mindermenge_bis"))
    b["Mindermengenzuschlag"] = _d(bezug.get("mindermenge")) if grenze is not None and _d(bestellt) < grenze else NULL
    return b


def preis_gueltig(bezug, heute=None):
    """'' oder Warnung, wenn der Einkaufspreis abgelaufen oder noch nicht gültig ist."""
    heute = heute or datetime.date.today().isoformat()
    if bezug.get("gueltig_bis") and str(bezug["gueltig_bis"]) < heute:
        return f"Einkaufspreis abgelaufen ({_datum(bezug['gueltig_bis'])})"
    if bezug.get("gueltig_von") and str(bezug["gueltig_von"]) > heute:
        return f"Einkaufspreis erst gültig ab {_datum(bezug['gueltig_von'])}"
    return ""


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso)


def bezug_waehlen(bezuege, lieferant=None):
    """Einkaufsbedingungen: der genannte Lieferant, sonst der bevorzugte, sonst der erste."""
    bezuege = list(bezuege or ())
    if lieferant:
        for b in bezuege:
            if b.get("lieferant") == lieferant:
                return b
    return next((b for b in bezuege if b.get("bevorzugt") == "ja"), bezuege[0] if bezuege else None)


# ------------------------------------------------------------------ Aufschlagsregel
def regel(methode, wert, staffel=None, quelle=None, name=None):
    return dict(methode=methode, wert=None if dez(wert) is None else float(dez(wert)),
                staffel=json_liste(staffel), quelle=quelle, name=name)


def _hat_regel(methode, wert, staffel):
    if methode == STAFFEL:
        return bool(staffel_sortiert(staffel, "wert"))
    return methode in METHODEN and dez(wert) is not None


def aufschlagsregeln(artikel, kategorien=None, standard=None):
    """Wirksame Aufschlagsregel(n) eines Artikels nach Priorität: individueller Artikelaufschlag > Aufschlag der
    Kategorie > Standardaufschlag der Anwendung (% auf Einstand, standard in %). Die höhere Regel ersetzt die
    niedrigere; nur 'Kategorie + individuell kombinieren' = ja wendet beide an (Beträge addiert).
    kategorien: {Name: Zeile}. Ergebnis: [Regel] (leer = kein Aufschlag hinterlegt)."""
    kat = (kategorien or {}).get(artikel.get("kategorie")) or {}
    if kat.get("aktiv") == "nein":
        kat = {}
    km = kat.get("aufschlag_methode") or PROZENT
    r_kat = (regel(km, kat.get("aufschlag_wert"), quelle=KATEGORIE, name=kat.get("name"))
             if km != STAFFEL and _hat_regel(km, kat.get("aufschlag_wert"), None) else None)
    r_std = regel(PROZENT, standard, quelle=STANDARD) if dez(standard) is not None else None
    quelle = artikel.get("aufschlag_quelle") or KATEGORIE
    if quelle == INDIVIDUELL and _hat_regel(artikel.get("aufschlag_methode"), artikel.get("aufschlag_wert"),
                                            artikel.get("aufschlag_staffel")):
        r_ind = regel(artikel["aufschlag_methode"], artikel.get("aufschlag_wert"), artikel.get("aufschlag_staffel"),
                      INDIVIDUELL)
        return [r_kat, r_ind] if artikel.get("kombiniert") == "ja" and r_kat else [r_ind]
    if quelle in (KATEGORIE, INDIVIDUELL) and r_kat:
        return [r_kat]
    return [r_std] if r_std else []


def regel_text(r, verbrauch=None):
    """Kurztext einer Regel, z. B. '25 % auf Einstand (Kategorie Schrauben und Muttern)'."""
    if not r:
        return "kein Aufschlag hinterlegt"
    z = lambda w: _zahl(w)
    m, w = r.get("methode"), r.get("wert")
    if m == PROZENT:
        t = f"{z(w)} % auf Einstand"
    elif m == JE_EINHEIT:
        t = f"{z(w)} € je Einheit"
    elif m == JE_BESTELLUNG:
        t = f"{z(w)} € je Bestellung"
    elif m == MARGE:
        t = f"Zielmarge {z(w)} %"
    elif m == STAFFEL:
        zeile = staffel_wahl(staffel_sortiert(r.get("staffel"), "wert"), verbrauch or 0)
        t = f"Staffel: {z(zeile['wert'])} % auf Einstand (ab {z(zeile['ab'])})" if zeile else "Staffel ohne Werte"
    else:
        t = str(m or "")
    q = r.get("quelle")
    herkunft = {KATEGORIE: f"Kategorie {r.get('name') or ''}".strip(), INDIVIDUELL: "individuell",
                STANDARD: "Standard der Anwendung", POSITION: "Positionsaufschlag"}.get(q, q or "")
    return f"{t} ({herkunft})" if herkunft else t


def zahl_text(w):
    """Zahl ohne unnötige Nachkommastellen, mit Komma: 0,0835 / 12 / 1,5."""
    return _zahl(w)


def _zahl(w):
    s = f"{_d(w).quantize(Decimal('0.0001')):f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def aufschlag(r, einstand, verbrauch):
    """Aufschlagsbetrag einer Regel für einen Einstand (Decimal) und eine Verbrauchsmenge."""
    if not r:
        return NULL
    m, w = r.get("methode"), _d(r.get("wert"))
    if m == PROZENT:
        return einstand * w / HUNDERT
    if m == JE_EINHEIT:
        return _d(verbrauch) * w
    if m == JE_BESTELLUNG:
        return w
    if m == STAFFEL:
        zeile = staffel_wahl(staffel_sortiert(r.get("staffel"), "wert"), verbrauch)
        return einstand * zeile["wert"] / HUNDERT if zeile else NULL
    if m == MARGE:
        if w >= HUNDERT:
            raise ValueError("Zielmarge muss unter 100 % liegen")
        return einstand * w / (HUNDERT - w)
    return NULL


# ------------------------------------------------------------------ Preisstand und Rechnung
def stand(artikel, bezug, kategorien=None, standard=None, datum=None):
    """Preisstand eines Artikels für eine Position (wird beim Hinzufügen gespeichert, damit spätere Änderungen an
    Artikel, Kategorie, Lieferant oder Standardaufschlag gespeicherte Angebote nicht verändern)."""
    b = dict(bezug or {})
    b.pop("id", None)
    b.pop("artikel_id", None)
    b["preise"] = json_liste(b.get("preise"))
    return dict(artikelnr=artikel.get("artikelnr"), bezeichnung=artikel.get("bezeichnung"),
                einheit=artikel.get("einheit") or "Stück", kategorie=artikel.get("kategorie"),
                rest_lager=artikel.get("rest_lager"), angebotstext=artikel.get("angebotstext"),
                bezug=b if bezug else None, regeln=aufschlagsregeln(artikel, kategorien, standard),
                datum=datum or datetime.date.today().isoformat())


def stand_kennung(st):
    return hashlib.sha1(json.dumps({k: v for k, v in (st or {}).items() if k != "datum"}, sort_keys=True,
                                   ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def eintraege(p):
    """Zukaufteile einer Position: [{artikel_id, menge, aufschlag (Positionsaufschlag %), stand}]."""
    return [e for e in json_liste(p.get("zukauf")) if e.get("artikel_id") is not None or e.get("stand")]


def zukauf_text(p):
    """Kurzanzeige in der Positionstabelle, z. B. '4 St Schraube M6x20; 1 St Lasche'."""
    out = []
    for e in eintraege(p):
        st = e.get("stand") or {}
        out.append(f"{_zahl(e.get('menge'))} {EINHEIT_KURZ.get(st.get('einheit'), st.get('einheit') or '')} "
                   f"{st.get('bezeichnung') or st.get('artikelnr') or '?'}".replace("  ", " "))
    return "; ".join(out)


def bestellung(st, verbrauch, heute=None):
    """Einkauf eines Artikels für einen Verbrauch (Decimal). Ergebnis dict mit allen Zwischenwerten; fehler =
    'kein Einkaufspreis', wenn Lieferant oder Preis fehlt (dann ohne Beträge)."""
    bezug = st.get("bezug") or {}
    v = _d(verbrauch)
    out = dict(verbrauch=v, bestellt=NULL, ek=None, staffel=None, einkauf=NULL, bezug_einzeln={}, bezug=NULL,
               einstand=NULL, mehrmenge=NULL, lieferant=bezug.get("lieferant"), fehler="", warnung="")
    if v <= 0:
        return out
    bestellt = bestellmenge(v, bezug.get("mindestmenge"), bezug.get("vpe"))
    ek, zeile = ek_je_einheit(bezug, bestellt)
    out.update(bestellt=bestellt, mehrmenge=bestellt - v)
    if ek is None or ek <= 0:          # 0 € ist kein Einkaufspreis, sondern ein fehlender (EK fehlt)
        out["fehler"] = "kein Einkaufspreis"
        return out
    lager = st.get("rest_lager") == "ja"
    anteil = v / bestellt if lager and bestellt > 0 else Decimal(1)
    einzeln = {n: b * anteil for n, b in bezugskosten(bezug, bestellt).items()}
    einkauf = (v if lager else bestellt) * ek
    b = sum(einzeln.values(), NULL)
    out.update(ek=ek, staffel=zeile, einkauf=einkauf, bezug_einzeln=einzeln, bezug=b, einstand=einkauf + b,
               warnung=preis_gueltig(bezug, heute))
    return out


def rechnen(eintraege_mit_menge, heute=None):
    """Zukaufteile eines Angebots bzw. einer Mengenstufe.

    eintraege_mit_menge: [(Schlüssel, Eintrag, Stückzahl)] — Schlüssel eindeutig je Eintrag (z. B. (Position, Nr.)),
    Eintrag wie
    in eintraege(), Stückzahl der Position. Einträge mit gleichem Artikel und gleichem Preisstand werden zu einer
    Bestellung zusammengefasst (Verbrauch addiert, Staffel und Bezugskosten einmal).
    Ergebnis: (gruppen, je_eintrag). je_eintrag[Schlüssel] = dict(verbrauch, einstand,
    aufschlag, vk, fehler, warnung) mit Beträgen für die Position (nicht je Teil)."""
    gruppen = {}
    for schl, e, stueck in eintraege_mit_menge:
        st = e.get("stand") or {}
        g = gruppen.setdefault((e.get("artikel_id"), stand_kennung(st)), dict(stand=st, artikel_id=e.get("artikel_id"),
                                                                             teile=[]))
        menge = _d(e.get("menge")) * _d(stueck)
        g["teile"].append((schl, e, menge))
    je, ergebnis = {}, []
    for g in gruppen.values():
        st = g["stand"]
        verbrauch = sum((m for _, _, m in g["teile"]), NULL)
        bs = bestellung(st, verbrauch, heute)
        regeln = st.get("regeln") or []
        ohne_pos = [(s, e, m) for s, e, m in g["teile"] if dez(e.get("aufschlag")) is None]
        v_ohne = sum((m for _, _, m in ohne_pos), NULL)
        einst_ohne = bs["einstand"] * v_ohne / verbrauch if verbrauch else NULL
        # Regeln ohne Positionsaufschlag: auf den Einstand dieser Positionen, Staffel nach dem ganzen Verbrauch
        try:
            auf_ohne = sum((_aufschlag_gruppe(r, einst_ohne, v_ohne, verbrauch) for r in regeln), NULL) \
                if not bs["fehler"] and ohne_pos else NULL
            fehler_regel = ""
        except ValueError as ex:
            auf_ohne, fehler_regel = NULL, str(ex)
        zeilen = []
        for schl, e, m in g["teile"]:
            anteil = m / verbrauch if verbrauch else NULL
            einst = bs["einstand"] * anteil
            pa = dez(e.get("aufschlag"))
            if bs["fehler"]:
                auf = NULL
            elif pa is not None:
                auf = einst * pa / HUNDERT
            else:
                auf = auf_ohne * m / v_ohne if v_ohne else NULL
            z = dict(verbrauch=m, einstand=einst, aufschlag=auf, vk=einst + auf, fehler=bs["fehler"] or fehler_regel,
                     warnung=bs["warnung"] or ("" if regeln or pa is not None else "kein Aufschlag hinterlegt"),
                     regel=regel_text(dict(methode=PROZENT, wert=float(pa), quelle=POSITION)) if pa is not None
                     else ("; ".join(regel_text(r, verbrauch) for r in regeln) or regel_text(None)))
            je[schl] = z
            zeilen.append(z)
        einst = sum((z["einstand"] for z in zeilen), NULL)
        auf = sum((z["aufschlag"] for z in zeilen), NULL)
        ergebnis.append(dict(artikel_id=g["artikel_id"], stand=st, bestellung=bs, regeln=regeln,
                             regel="; ".join(regel_text(r, verbrauch) for r in regeln) or regel_text(None),
                             einstand=einst, aufschlag=auf, vk=einst + auf, positionen=len(g["teile"]),
                             fehler=bs["fehler"] or fehler_regel, warnung=zeilen[0]["warnung"] if zeilen else ""))
    return ergebnis, je


def _aufschlag_gruppe(r, einstand, verbrauch_teil, verbrauch_gesamt):
    if r.get("methode") == STAFFEL:          # Staffel nach dem ganzen Verbrauch des Artikels wählen
        zeile = staffel_wahl(staffel_sortiert(r.get("staffel"), "wert"), verbrauch_gesamt)
        return einstand * zeile["wert"] / HUNDERT if zeile else NULL
    return aufschlag(r, einstand, verbrauch_teil)


def vorschau(artikel, bezug, kategorien=None, standard=None, verbrauch=1, heute=None):
    """Preisvorschau eines Artikels für eine Verbrauchsmenge (dieselbe Rechnung wie im Angebot).
    Ergebnis: dict(bestellung, regeln, regel, einstand, aufschlag, vk, je_einheit: {ek, bezug, einstand, aufschlag,
    vk}, aufschlag_pct, marge_pct, fehler, warnung)."""
    st = stand(artikel, bezug, kategorien, standard)
    gruppen, _ = rechnen([(0, dict(artikel_id=artikel.get("id"), menge=verbrauch, stand=st), 1)], heute)
    g = gruppen[0]
    v = _d(verbrauch)
    je = {n: (g[n] / v if v else NULL) for n in ("einstand", "aufschlag", "vk")}
    je["bezug"] = g["bestellung"]["bezug"] / v if v else NULL
    je["ek"] = g["bestellung"]["einkauf"] / v if v else NULL
    return dict(g, je_einheit=je, aufschlag_pct=(g["aufschlag"] / g["einstand"] * HUNDERT) if g["einstand"] else None,
                marge_pct=(g["aufschlag"] / g["vk"] * HUNDERT) if g["vk"] else None)


def artikel_fehler(artikel, bezuege=()):
    """Prüfung eines Artikels vor dem Speichern: [Meldung]."""
    out = []
    if not (artikel.get("bezeichnung") or "").strip():
        out.append("Artikelbezeichnung fehlt")
    q = artikel.get("aufschlag_quelle") or KATEGORIE
    if q == INDIVIDUELL:
        m = artikel.get("aufschlag_methode")
        if m not in METHODEN:
            out.append("Aufschlagsmethode fehlt")
        elif m == STAFFEL:
            if not staffel_sortiert(artikel.get("aufschlag_staffel"), "wert"):
                out.append("Aufschlagsstaffel fehlt")
            out += staffel_fehler(artikel.get("aufschlag_staffel"), "wert")
        elif dez(artikel.get("aufschlag_wert")) is None:
            out.append("Aufschlag fehlt")
        elif dez(artikel["aufschlag_wert"]) < 0:
            out.append("Aufschlag darf nicht negativ sein")
        elif m == MARGE and dez(artikel["aufschlag_wert"]) >= HUNDERT:
            out.append("Zielmarge muss unter 100 % liegen")
    for b in bezuege:
        n = b.get("lieferant") or "ohne Lieferant"
        for meldung in staffel_fehler(b.get("preise")):
            out.append(f"{n}: {meldung}")
        if b.get("preiseinheit") is not None and _d(b["preiseinheit"]) <= 0:
            out.append(f"{n}: Preiseinheit muss größer als 0 sein")
        for f in ("mindestmenge", "vpe", "verpackung", "mindermenge", "fracht", "fracht_einheit", "weitere", "rabatt"):
            if b.get(f) is not None and _d(b[f]) < 0:
                out.append(f"{n}: {BEZUG.feld(f).titel} darf nicht negativ sein")
        if b.get("rabatt") is not None and _d(b["rabatt"]) >= HUNDERT:
            out.append(f"{n}: Mengenrabatt muss unter 100 % liegen")
        if b.get("gueltig_von") and b.get("gueltig_bis") and str(b["gueltig_bis"]) < str(b["gueltig_von"]):
            out.append(f"{n}: Gültig bis liegt vor Gültig von")
    lief = [b.get("lieferant") for b in bezuege if b.get("lieferant")]
    if len(lief) != len(set(lief)):
        out.append("Lieferant doppelt")
    return out


# ------------------------------------------------------------------ Blechteile
BLECH = "Blech"
STEP_IMPORT = "STEP-Import"
BLECH_FELDER = ("artikeltyp", "laenge", "breite", "dicke", "werkstoff", "herkunft", "step_datei", "fingerabdruck")
TOL_MASS = Decimal("0.5")       # Dubletten: Länge und Breite ± 0,5 mm (auch um 90° gedreht)
TOL_DICKE = Decimal("0.05")     # Dicke ± 0,05 mm


def ek_fehlt(artikel):
    """True, wenn kein Lieferant des Artikels einen Einkaufspreis über 0 € hat (0 € gilt nie als echter EK)."""
    return not any(e["preis"] > 0 for b in artikel.get("bezuege") or () for e in staffel_sortiert(b.get("preise")))


def _mm(x):
    t = _zahl(round(float(x), 1)) if isinstance(x, (int, float, Decimal)) else "?"
    return t


def blech_bezeichnung(laenge, breite, dicke, werkstoff=None):
    """Bezeichnung eines Blechartikels, z. B. 'Blech S235 500 × 300 × 5 mm'; ohne Werkstoff mit Hinweis
    '(Werkstoff offen)' — ein unbekannter Werkstoff wird nie angenommen."""
    masse = f"{_mm(laenge)} × {_mm(breite)} × {_mm(dicke)} mm"
    return f"Blech {werkstoff} {masse}" if werkstoff else f"Blech {masse} (Werkstoff offen)"


def blech_artikel(b, werkstoff=None, step_datei=None, kategorie="Blechteile", lieferant=None):
    """Neuer Zukaufartikel (Werte, Einkaufsbedingungen) für ein gemessenes Blech b (step.blech): Einheit Stück,
    Lieferant nach Vorgabe, ohne Einkaufspreis (EK fehlt, bis er eingetragen ist)."""
    werte = dict(bezeichnung=blech_bezeichnung(b.get("laenge"), b.get("breite"), b.get("dicke"), werkstoff),
                 kategorie=kategorie, einheit="Stück", status="aktiv", aufschlag_quelle=KATEGORIE,
                 angebotstext="nein", rest_lager="nein", kombiniert="nein", artikeltyp=BLECH,
                 laenge=b.get("laenge"), breite=b.get("breite"), dicke=b.get("dicke"), werkstoff=werkstoff or None,
                 herkunft=STEP_IMPORT, step_datei=step_datei or None, fingerabdruck=b.get("fingerabdruck") or None,
                 beschreibung=("freie Kontur" if b.get("kontur") == "frei" else None))
    if lieferant is None:
        lieferant = BLECH_LIEFERANT.get(kategorie, "")
    return werte, [dict(lieferant=lieferant or None, bevorzugt="ja", preiseinheit=1, preise=[])]


# vorgeschlagener Lieferant für neue Blechartikel (Patrick: Bleche kommen von "Technik")
BLECH_LIEFERANT = {"Blechteile": "Technik"}


def _nahe(a, b, tol):
    return dez(a) is not None and dez(b) is not None and abs(dez(a) - dez(b)) <= tol


def blech_dubletten(b, werkstoff, artikel_liste):
    """Vorhandene Blechartikel zu einem gemessenen Blech b: (gleich, ähnlich), je Liste von Artikeln.

    gleich: gleiche Dicke (± 0,05 mm), Länge und Breite ± 0,5 mm (auch vertauscht), gleicher Werkstoff (beide leer
    zählt als gleich) und gleiche Geometrie-Kennung (Kontur, Bohrungen, Ausschnitte; Artikel ohne Kennung zählen nur
    über die Maße). ähnlich: gleiche Maße, aber anderer bzw. offener Werkstoff oder andere Kontur (Wahl von Hand).
    Archivierte Artikel zählen nicht."""
    gleich, aehnlich = [], []
    for a in artikel_liste:
        if a.get("artikeltyp") != BLECH or a.get("status") == "archiviert":
            continue
        if not _nahe(a.get("dicke"), b.get("dicke"), TOL_DICKE):
            continue
        l, br = a.get("laenge"), a.get("breite")
        if not (_nahe(l, b.get("laenge"), TOL_MASS) and _nahe(br, b.get("breite"), TOL_MASS)
                or _nahe(l, b.get("breite"), TOL_MASS) and _nahe(br, b.get("laenge"), TOL_MASS)):
            continue
        # Kennung: Bohrungen, Ausschnitte und Kontur; ein von Hand angelegter Artikel ohne Kennung zählt nur über die Maße
        kennung_ok = not a.get("fingerabdruck") or a.get("fingerabdruck") == b.get("fingerabdruck")
        if (a.get("werkstoff") or "") == (werkstoff or "") and kennung_ok:
            gleich.append(a)
        else:
            aehnlich.append(a)
    return gleich, aehnlich
