"""CSV-Export und -Import der Zukaufartikel: eine Zeile je Artikel und Lieferant (Semikolon, UTF-8 mit BOM für
Excel, Kopfzeile mit den Feldtiteln). Einkaufspreise als Staffel 'ab 1: 12,00 | ab 500: 9,00' je Preiseinheit.

Der Import prüft zuerst alles (vorschau) und schreibt erst nach Bestätigung (Datenbank.zukauf_importieren).
Artikel mit gleicher Artikelnummer werden aktualisiert: Stammdaten aus der Datei, Einkauf beim genannten
Lieferanten ersetzt, andere Lieferanten bleiben. Zeilen mit Fehler werden nicht übernommen."""
import csv
import io
import re

from . import zukauf
from .stammdaten import wert_aus_text, wert_als_text

ARTIKEL_SPALTEN = ("artikelnr", "bezeichnung", "kategorie", "einheit", "status", "beschreibung", "ean",
                   "aufschlag_quelle", "aufschlag_methode", "aufschlag_wert", "rest_lager", "angebotstext", "bemerkung")
BEZUG_SPALTEN = ("lieferant", "lieferanten_artnr", "preiseinheit", "preise", "mindestmenge", "vpe", "lieferzeit",
                 "verpackung", "mindermenge", "mindermenge_bis", "fracht", "fracht_einheit", "weitere", "rabatt",
                 "gueltig_von", "gueltig_bis")
PFLICHT = ("artikelnr", "bezeichnung")
NEU, AENDERN, GLEICH, FEHLER = "neu", "ändern", "unverändert", "Fehler"
AUSWAHL = {"status": zukauf.STATUS, "aufschlag_quelle": zukauf.QUELLEN, "aufschlag_methode": zukauf.METHODEN,
           "rest_lager": ("ja", "nein"), "angebotstext": ("ja", "nein")}


def _feld(name):
    return zukauf.ARTIKEL.feld(name) if name in ARTIKEL_SPALTEN else zukauf.BEZUG.feld(name)


def titel(name):
    return {"preise": "Einkaufspreise (ab Menge: Preis je Preiseinheit)"}.get(name, _feld(name).titel)


def staffel_lesen(text):
    """'ab 1: 12,00 | ab 500: 9,00' (auch '1: 12,00; 500: 9,00' oder nur '12,00') -> [{ab, preis}]."""
    from .stammdaten import zahl_aus_text
    t = (text or "").strip()
    if not t:
        return []
    out = []
    for teil in re.split(r"[|;]", t):
        teil = teil.strip()
        if not teil:
            continue
        m = re.fullmatch(r"(?:ab\s*)?([\d.,]+)\s*:\s*([-\d.,]+)\s*(?:€)?", teil, re.I)
        if m:
            ab, preis = m.group(1), m.group(2)
        elif len(out) == 0 and re.fullmatch(r"[-\d.,]+\s*(?:€)?", teil):
            ab, preis = "1", teil.rstrip("€ ")
        else:
            raise ValueError(f"Einkaufspreise: '{teil}' nicht lesbar (erwartet 'ab 1: 12,00 | ab 500: 9,00')")
        try:
            out.append(dict(ab=zahl_aus_text(ab), preis=zahl_aus_text(preis)))
        except ValueError:
            raise ValueError(f"Einkaufspreise: '{teil}' ist keine Zahl")
    return out


def exportieren(artikel):
    """Artikel (Datenbank.zukauf_artikel_liste) als CSV-Text; Artikel ohne Lieferant mit leeren Einkaufsspalten."""
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow([titel(n) for n in ARTIKEL_SPALTEN + BEZUG_SPALTEN])
    for a in artikel:
        for b in a.get("bezuege") or [{}]:
            zeile = []
            for n in ARTIKEL_SPALTEN + BEZUG_SPALTEN:
                q = a if n in ARTIKEL_SPALTEN else b
                if n == "preise":
                    zeile.append(zukauf.staffel_text(q.get(n)) if q.get(n) else "")
                else:
                    zeile.append(wert_als_text(_feld(n), q.get(n), bearbeiten=True) if q.get(n) is not None else "")
            w.writerow(zeile)
    return "﻿" + puffer.getvalue()


def _text(roh):
    if isinstance(roh, bytes):
        try:
            return roh.decode("utf-8-sig")
        except UnicodeDecodeError:
            return roh.decode("cp1252")
    return roh.lstrip("﻿")


def vorschau(roh, vorhandene, kategorien=()):
    """CSV lesen und prüfen, nichts schreiben. vorhandene: Datenbank.zukauf_artikel_liste().
    Ergebnis: dict(zeilen=[{nr, aktion, artikelnr, bezeichnung, lieferant, werte, bezug, fehler, hinweis, aenderung}],
    fehler=[allgemeine Fehler]). aktion: neu, ändern, unverändert oder Fehler."""
    text = _text(roh)
    probe = next((z for z in text.splitlines() if z.strip()), "")
    trenner = ";" if probe.count(";") >= probe.count(",") else ","
    leser = csv.reader(io.StringIO(text, newline=""), delimiter=trenner)
    namen = {titel(n).lower(): n for n in ARTIKEL_SPALTEN + BEZUG_SPALTEN}
    namen.update({_feld(n).titel.lower(): n for n in ARTIKEL_SPALTEN + BEZUG_SPALTEN})
    namen.update({n: n for n in ARTIKEL_SPALTEN + BEZUG_SPALTEN})
    nach_nr = {a.get("artikelnr"): a for a in vorhandene if a.get("artikelnr")}
    kategorien = set(kategorien)
    spalten, zeilen, gesehen = None, [], {}
    for nr, roh_zeile in enumerate(leser, 1):
        if not any(c.strip() for c in roh_zeile):
            continue
        if spalten is None:
            spalten = [namen.get(re.sub(r"\s+", " ", c.strip().lower())) for c in roh_zeile]
            fehlt = [titel(n) for n in PFLICHT if n not in spalten]
            if fehlt:
                return dict(zeilen=[], fehler=[f"Zeile {nr}: Kopfzeile ohne Spalte(n) {', '.join(fehlt)}"])
            continue
        z = dict(nr=nr, werte={}, bezug={}, fehler=[], hinweis=[], aenderung=[])
        for name, wert in zip(spalten, roh_zeile):
            if not name:
                continue
            wert = wert.strip()
            ziel = z["werte"] if name in ARTIKEL_SPALTEN else z["bezug"]
            try:
                ziel[name] = staffel_lesen(wert) if name == "preise" else wert_aus_text(_feld(name), wert)
            except ValueError as e:
                z["fehler"].append(str(e))
        w, b = z["werte"], z["bezug"]
        for n, erlaubt in AUSWAHL.items():
            if w.get(n) is not None and w[n] not in erlaubt:
                z["fehler"].append(f"{titel(n)}: '{w[n]}' nicht erlaubt ({', '.join(erlaubt)})")
        z.update(artikelnr=w.get("artikelnr"), bezeichnung=w.get("bezeichnung"), lieferant=b.get("lieferant"))
        for n in PFLICHT:
            if not w.get(n) and titel(n) not in " ".join(z["fehler"]):
                z["fehler"].append(f"{titel(n)} fehlt")
        if b.get("preise") is not None:
            z["fehler"] += zukauf.staffel_fehler(b["preise"])
        for n in ("preiseinheit",):
            if b.get(n) is not None and b[n] <= 0:
                z["fehler"].append(f"{titel(n)} muss größer als 0 sein")
        if any(b.get(n) not in (None, "", []) for n in BEZUG_SPALTEN if n != "lieferant") and not b.get("lieferant"):
            z["fehler"].append("Lieferant fehlt (Einkaufsdaten ohne Lieferant)")
        schl = (w.get("artikelnr"), b.get("lieferant") or "")
        if w.get("artikelnr"):
            if schl in gesehen:
                z["fehler"].append(f"doppelt in der Datei (wie Zeile {gesehen[schl]})")
            else:
                gesehen[schl] = nr
        if w.get("kategorie") and kategorien and w["kategorie"] not in kategorien:
            z["hinweis"].append(f"Kategorie '{w['kategorie']}' wird angelegt")
        if not z["fehler"]:
            alt = nach_nr.get(w.get("artikelnr"))
            neu_a, neu_b = zusammenfuehren(alt, w, b, spalten)
            z["fehler"] += zukauf.artikel_fehler(neu_a, neu_b)
            if alt is None:
                z["aktion"] = NEU
            else:
                z["aenderung"] = unterschiede(alt, neu_a, neu_b)
                z["aktion"] = AENDERN if z["aenderung"] else GLEICH
            z["artikel"], z["bezuege"], z["artikel_id"] = neu_a, neu_b, alt["id"] if alt else None
        if z["fehler"]:
            z["aktion"] = FEHLER
        zeilen.append(z)
    if spalten is None:
        return dict(zeilen=[], fehler=["Die Datei ist leer"])
    # mehrere Zeilen desselben Artikels (mehrere Lieferanten): Einkauf zusammenführen
    je = {}
    for z in zeilen:
        if z["aktion"] in (NEU, AENDERN, GLEICH):
            je.setdefault(z["artikelnr"], []).append(z)
    for gruppe in je.values():
        if len(gruppe) > 1:
            lieferanten = {z["lieferant"] for z in gruppe}
            basis = gruppe[0]           # Artikelangaben aus der ersten Zeile, Einkauf aus allen
            bezuege = [b for b in basis["bezuege"] if b.get("lieferant") not in lieferanten]
            bezuege += [next(b for b in z["bezuege"] if b.get("lieferant") == z["lieferant"]) for z in gruppe
                        if z["lieferant"]]
            for z in gruppe:
                z["artikel"], z["bezuege"] = basis["artikel"], bezuege
    return dict(zeilen=zeilen, fehler=[])


def zusammenfuehren(alt, werte, bezug, spalten):
    """Artikel aus der Datei auf den vorhandenen legen: nur Spalten, die in der Datei stehen, ändern den Artikel;
    der Einkauf beim genannten Lieferanten wird ersetzt. Ergebnis: (artikel, bezuege)."""
    a = {f.name: (alt or {}).get(f.name) for f in zukauf.ARTIKEL.felder}
    for n in ARTIKEL_SPALTEN:
        if n in spalten:
            a[n] = werte.get(n)
    if not alt:
        a["status"] = a.get("status") or "aktiv"
    bezuege = [dict(b) for b in (alt or {}).get("bezuege") or ()]
    if bezug.get("lieferant"):
        vorher = next((x for x in bezuege if x.get("lieferant") == bezug["lieferant"]), None)
        neu = {f.name: (vorher or {}).get(f.name) for f in zukauf.BEZUG.felder if f.name != "artikel_id"}
        for n in BEZUG_SPALTEN:
            if n in spalten:
                neu[n] = bezug.get(n)
        if neu.get("preiseinheit") is None:
            neu["preiseinheit"] = 1
        neu["preise"] = zukauf.json_liste(neu.get("preise"))
        bezuege = [x for x in bezuege if x is not vorher] + [neu] if vorher is None else \
            [neu if x is vorher else x for x in bezuege]
    for x in bezuege:
        x.pop("id", None)
        x.pop("artikel_id", None)
        x["preise"] = zukauf.json_liste(x.get("preise"))
    return a, bezuege


def unterschiede(alt, artikel, bezuege):
    """Kurztexte der Änderungen gegenüber dem vorhandenen Artikel, z. B. ['Einkaufspreise: ab 1: 12,00 → ab 1: 13,00']."""
    out = []
    leer = lambda v: None if v in (None, "", [], "[]") else v
    for n in ARTIKEL_SPALTEN:
        if leer(alt.get(n)) != leer(artikel.get(n)):
            out.append(f"{titel(n)}: {_kurz(n, alt.get(n))} → {_kurz(n, artikel.get(n))}")
    alt_b = {b.get("lieferant"): b for b in alt.get("bezuege") or ()}
    for b in bezuege:
        a = alt_b.get(b.get("lieferant"))
        if a is None:
            out.append(f"Lieferant {b.get('lieferant')} neu")
            continue
        for n in BEZUG_SPALTEN:
            x, y = a.get(n), b.get(n)
            if n == "preise":
                x, y = zukauf.staffel_sortiert(x), zukauf.staffel_sortiert(y)
            if leer(x) != leer(y):
                out.append(f"{b.get('lieferant')} {titel(n).split(' (')[0]}: {_kurz(n, a.get(n))} → {_kurz(n, b.get(n))}")
    return out


def _kurz(n, w):
    if w in (None, "", []):
        return "leer"
    if n == "preise":
        return zukauf.staffel_text(w)
    return wert_als_text(_feld(n), w)
