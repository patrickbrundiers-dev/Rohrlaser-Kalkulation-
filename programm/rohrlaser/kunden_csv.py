"""CSV-Export und -Import der Kundenliste: eine Zeile je Kunde (Semikolon, UTF-8 mit BOM für Excel, Kopfzeile mit
den Spaltentiteln des Reiters Kunden, Zahlen mit Komma).

Der Import prüft zuerst alles (vorschau) und schreibt erst nach Bestätigung (Datenbank.kunden_importieren, vorher
Datensicherung). Kunden mit vorhandener Kundennummer werden geändert: Spalten aus der Datei ersetzen die alten Werte,
Spalten, die in der Datei fehlen, bleiben. Mit nur_neue=True bleiben vorhandene Kunden unverändert (übersprungen).
Zeilen mit Fehler und doppelte Kundennummern in der Datei werden nicht übernommen."""
import csv
import io
import re

from .stammdaten import KUNDEN, pruefen, wert_aus_text, wert_als_text

SPALTEN = tuple(f.name for f in KUNDEN.felder)
PFLICHT = ("kundennr", "name")
NEU, AENDERN, GLEICH, UEBERSPRUNGEN, FEHLER = "neu", "ändern", "unverändert", "übersprungen", "Fehler"
# weitere Kopfzeilen, die oft in Kundenlisten anderer Programme stehen
ALIAS = {"kundennr": "kundennr", "kundennr.": "kundennr", "kunden-nr.": "kundennr", "kunden-nr": "kundennr",
         "kd.-nr.": "kundennr", "kdnr": "kundennr", "name": "name", "firma": "name", "ort": "plz_ort",
         "plz/ort": "plz_ort", "email": "email", "mail": "email", "tel.": "telefon", "skonto": "skonto",
         "zahlungsziel": "zahlungsziel"}
PLZ_FELDER = (("plz", "land"), ("liefer_plz", "liefer_land"))


def titel(name):
    return KUNDEN.feld(name).titel


def exportieren(kunden):
    """Kunden (Datenbank.zeilen('kunden')) als CSV-Text, nach Kundennummer sortiert."""
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow([titel(n) for n in SPALTEN])
    for k in sorted(kunden, key=lambda k: str(k.get("kundennr") or "")):
        w.writerow([wert_als_text(KUNDEN.feld(n), k.get(n), bearbeiten=True) for n in SPALTEN])
    return "﻿" + puffer.getvalue()


def _text(roh):
    if isinstance(roh, bytes):
        try:
            return roh.decode("utf-8-sig")
        except UnicodeDecodeError:
            return roh.decode("cp1252")
    return roh.lstrip("﻿")


def _plz_auffuellen(w, hinweis):
    """Excel entfernt führende Nullen: deutsche PLZ mit 4 Ziffern (auch am Anfang von 'PLZ Ort') wieder auf 5."""
    for plz, land in PLZ_FELDER + (("plz_ort", "land"),):
        t = w.get(plz)
        if not t or (w.get(land) or "DE") != "DE":
            continue
        m = re.match(r"^(\d{4})(\s|$)", str(t))
        if m:
            neu = "0" + str(t)
            hinweis.append(f"{titel(plz)}: {t} → {neu} (führende Null ergänzt)")
            w[plz] = neu


def vorschau(roh, vorhandene, kontext=None, nur_neue=False):
    """CSV lesen und prüfen, nichts schreiben. vorhandene: Datenbank.zeilen('kunden'); kontext: Datenbank.kontext()
    für die Auswahllisten (Lieferbedingung). Ergebnis: dict(zeilen=[{nr, aktion, kundennr, name, kunde, kunden_id,
    fehler, hinweis, aenderung}], fehler=[allgemeine Fehler]). aktion: neu, ändern, unverändert, übersprungen, Fehler."""
    text = _text(roh)
    probe = next((z for z in text.splitlines() if z.strip()), "")
    trenner = ";" if probe.count(";") >= probe.count(",") else ","
    namen = dict(ALIAS)
    namen.update({titel(n).lower(): n for n in SPALTEN})
    namen.update({n: n for n in SPALTEN})
    nach_nr = {str(k.get("kundennr")): k for k in vorhandene if k.get("kundennr") not in (None, "")}
    spalten, zeilen, gesehen = None, [], {}
    for nr, roh_zeile in enumerate(csv.reader(io.StringIO(text), delimiter=trenner), 1):
        if not any(c.strip() for c in roh_zeile):
            continue
        if spalten is None:
            spalten = [namen.get(re.sub(r"\s+", " ", c.strip().lower())) for c in roh_zeile]
            fehlt = [titel(n) for n in PFLICHT if n not in spalten]
            if fehlt:
                return dict(zeilen=[], fehler=[f"Zeile {nr}: Kopfzeile ohne Spalte(n) {', '.join(fehlt)}"])
            continue
        z = dict(nr=nr, fehler=[], hinweis=[], aenderung=[])
        w = {}
        for name, wert in zip(spalten, roh_zeile):
            if name:
                try:
                    w[name] = wert_aus_text(KUNDEN.feld(name), wert)
                except ValueError as e:
                    z["fehler"].append(str(e))
        _plz_auffuellen(w, z["hinweis"])
        z.update(kundennr=w.get("kundennr"), name=w.get("name"))
        for n in PFLICHT:
            if not w.get(n) and titel(n) not in " ".join(z["fehler"]):
                z["fehler"].append(f"{titel(n)} fehlt")
        if w.get("kundennr"):
            if w["kundennr"] in gesehen:
                z["fehler"].append(f"Kundennummer doppelt in der Datei (wie Zeile {gesehen[w['kundennr']]})")
            else:
                gesehen[w["kundennr"]] = nr
        alt = nach_nr.get(str(w.get("kundennr")))
        kunde = {n: (alt or {}).get(n) for n in SPALTEN}
        for n in SPALTEN:
            if n in spalten:
                kunde[n] = w.get(n)
        if not z["fehler"] and kontext is not None:
            meldung = pruefen(KUNDEN, kunde, kontext)
            if meldung.startswith("FEHLER"):
                z["fehler"].append(meldung[len("FEHLER: "):])
        z.update(kunde=kunde, kunden_id=alt["id"] if alt else None)
        if z["fehler"]:
            z["aktion"] = FEHLER
        elif alt is None:
            z["aktion"] = NEU
        else:
            z["aenderung"] = unterschiede(alt, kunde)
            z["aktion"] = GLEICH if not z["aenderung"] else UEBERSPRUNGEN if nur_neue else AENDERN
        zeilen.append(z)
    if spalten is None:
        return dict(zeilen=[], fehler=["Die Datei ist leer"])
    return dict(zeilen=zeilen, fehler=[])


def unterschiede(alt, neu):
    """Kurztexte der Änderungen, z. B. ['Telefon: 05250 123 → 05250 456']."""
    leer = lambda v: None if v in (None, "") else v
    return [f"{titel(n)}: {_kurz(n, alt.get(n))} → {_kurz(n, neu.get(n))}" for n in SPALTEN
            if leer(alt.get(n)) != leer(neu.get(n))]


def _kurz(n, w):
    return "leer" if w in (None, "") else wert_als_text(KUNDEN.feld(n), w)
