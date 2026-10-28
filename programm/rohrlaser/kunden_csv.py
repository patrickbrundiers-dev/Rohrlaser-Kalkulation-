"""CSV-Export und -Import der Kundenliste: eine Zeile je Kunde (Semikolon, UTF-8 mit BOM für Excel, Kopfzeile mit
den Spaltentiteln des Reiters Kunden, Zahlen mit Komma).

Der Import prüft zuerst alles (vorschau) und schreibt erst nach Bestätigung (Datenbank.kunden_importieren, vorher
Datensicherung). Kunden mit vorhandener Kundennummer werden geändert: Spalten aus der Datei ersetzen die alten Werte,
Spalten, die in der Datei fehlen, bleiben. Mit nur_neue=True bleiben vorhandene Kunden unverändert (übersprungen).
Zeilen mit Fehler und doppelte Kundennummern in der Datei werden nicht übernommen.

Robust gegen das, was Excel und andere Programme aus einer CSV machen: Trennzeichen ; , oder Tab (auch 'sep=;' in
der ersten Zeile), UTF-8 mit/ohne BOM, UTF-16 ('Unicode-Text'), Windows-1252, Zeilenenden CRLF/LF/CR (Mac),
Titelzeilen über der Kopfzeile, Zeilenumbrüche und Anführungszeichen in Feldern. Beim Export bekommen Texte, die
Excel beim Öffnen verändern würde (führende Null, +49 …, lange Ziffernfolgen, Datumsähnliches), die Form ="…"; der
Import entfernt sie wieder. Fehlermeldungen nennen Zeile (wie in Excel) und Spalte (Buchstabe und Titel)."""
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
TRENNER = {";": "Semikolon", ",": "Komma", "\t": "Tabulator"}
LAENDER = {"deutschland": "DE", "germany": "DE", "d": "DE", "österreich": "AT", "oesterreich": "AT", "austria": "AT",
           "a": "AT", "schweiz": "CH", "switzerland": "CH", "niederlande": "NL", "holland": "NL", "belgien": "BE",
           "frankreich": "FR", "polen": "PL", "tschechien": "CZ", "dänemark": "DK", "luxemburg": "LU",
           "italien": "IT"}
# Excel-Fehlerwerte (deutsch und englisch), z. B. #NAME? aus einer Telefonnummer +49 … ohne Hochkomma
EXCEL_FEHLER = re.compile(r"^#(NAME\?|NAMEN\?|WERT!|VALUE!|NULL!|BEZUG!|REF!|DIV/0!|NV|N/A|ZAHL!|NUM!|ÜBERLAUF!|SPILL!)$",
                          re.I)
# Texte, die Excel beim Öffnen umwandelt: Formelanfang, führende Null, lange Ziffern (1,23E+11), Datum (1-2, 3.4.)
EXCEL_WANDELT = re.compile(r"^([=+\-@].|0\d+$|\d{12,}$|\d{1,2}[-/.]\d{1,2}([-/.]\d{0,4})?$)", re.S)


def titel(name):
    return KUNDEN.feld(name).titel


def spalte(i):
    """Spaltenbuchstabe wie in Excel: 0 -> A, 26 -> AA."""
    t = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        t = chr(65 + r) + t
    return t


def _fuer_excel(f, t):
    """Text so schreiben, dass Excel ihn beim Öffnen nicht verändert (="…", max. 255 Zeichen in einer Formel)."""
    if f.art in ("zahl", "ganz") or not EXCEL_WANDELT.match(t) or len(t) > 250:
        return t
    return '="' + t.replace('"', '""') + '"'


def exportieren(kunden):
    """Kunden (Datenbank.zeilen('kunden')) als CSV-Text (mit BOM, Zeilenende CRLF), nach Kundennummer sortiert.
    Als Datei mit Path.write_bytes(text.encode('utf-8')) schreiben, nicht write_text: Windows machte aus CRLF CRCRLF
    (leere Zeilen in Excel)."""
    puffer = io.StringIO(newline="")
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow([titel(n) for n in SPALTEN])
    for k in sorted(kunden, key=lambda k: str(k.get("kundennr") or "")):
        w.writerow([_fuer_excel(KUNDEN.feld(n), wert_als_text(KUNDEN.feld(n), k.get(n), bearbeiten=True))
                    for n in SPALTEN])
    return "\ufeff" + puffer.getvalue()


def _text(roh):
    """Bytes einer CSV als Text: UTF-16 (Excel 'Unicode-Text'), UTF-8 mit/ohne BOM, sonst Windows-1252
    (Excel 'CSV (Trennzeichen-getrennt)'); Bytes, die es dort nicht gibt, als Latin-1 statt Abbruch."""
    if not isinstance(roh, bytes):
        return roh.lstrip("\ufeff")
    if roh.startswith((b"\xff\xfe", b"\xfe\xff")):
        return roh.decode("utf-16", errors="replace").lstrip("\ufeff")      # abgeschnittene Datei: kein Abbruch
    if roh[:400].count(b"\x00") > len(roh[:400]) // 4:          # UTF-16 ohne BOM
        try:
            return roh.decode("utf-16-le" if roh[1:2] == b"\x00" else "utf-16-be")
        except UnicodeDecodeError:
            pass
    for kodierung in ("utf-8-sig", "cp1252"):
        try:
            return roh.decode(kodierung)
        except UnicodeDecodeError:
            pass
    return roh.decode("latin-1")


def _excel_wert(t):
    """="…" (Export-Schutz für Excel) wieder zum reinen Text."""
    m = re.fullmatch(r'\s*="(.*)"\s*', t, re.S)
    return m.group(1).replace('""', '"') if m else t


def _trenner(zeilen):
    """Trennzeichen: 'sep=;' in der ersten Zeile, sonst das häufigste aus ; , Tab in den ersten Zeilen."""
    m = re.fullmatch(r'\s*"?sep=(.)"?\s*', zeilen[0], re.I) if zeilen else None
    if m:
        return m.group(1), True
    probe = zeilen[:10]
    return max(TRENNER, key=lambda c: (max((z.count(c) for z in probe), default=0), c == ";")), False


def _plz_auffuellen(w, hinweis, alt=None):
    """Excel entfernt führende Nullen: deutsche PLZ mit 4 Ziffern (auch am Anfang von 'PLZ Ort') wieder auf 5.
    Land aus der Datei, sonst vom vorhandenen Kunden (Lieferland leer = Land); unveränderte Werte bleiben."""
    alt = alt or {}

    def staat(x):
        return w[x] if x in w else alt.get(x)
    for plz, land in PLZ_FELDER + (("plz_ort", "land"),):
        t = w.get(plz)
        if not t or t == alt.get(plz):
            continue
        if (staat(land) or (staat("land") if land == "liefer_land" else None) or "DE") != "DE":
            continue
        m = re.match(r"^(\d{4})(\s|$)", str(t))
        if m:
            neu = "0" + str(t)
            hinweis.append(f"{titel(plz)}: {t} → {neu} (führende Null ergänzt)")
            w[plz] = neu


def vorschau(roh, vorhandene, kontext=None, nur_neue=False):
    """CSV lesen und prüfen, nichts schreiben. vorhandene: Datenbank.zeilen('kunden'); kontext: Datenbank.kontext()
    für die Auswahllisten (Lieferbedingung). Ergebnis: dict(zeilen=[{nr, aktion, kundennr, name, kunde, kunden_id,
    fehler, hinweis, aenderung}], fehler=[allgemeine Fehler]). aktion: neu, ändern, unverändert, übersprungen, Fehler.
    nr = Zeile wie in Excel (ein Feld mit Zeilenumbruch bleibt eine Zeile). Wirft keine Ausnahme bei kaputten Dateien."""
    text = _text(roh)
    nicht_leer = [z for z in text.splitlines() if z.strip()]
    if not nicht_leer:
        return dict(zeilen=[], fehler=["Die Datei ist leer"])
    trenner, sep_zeile = _trenner(nicht_leer)
    namen = dict(ALIAS)
    namen.update({titel(n).lower(): n for n in SPALTEN})
    namen.update({n: n for n in SPALTEN})
    nach_nr = {str(k.get("kundennr")): k for k in vorhandene if k.get("kundennr") not in (None, "")}
    ohne_null = {}
    for nr_alt, k in nach_nr.items():
        if nr_alt.isdigit():
            ohne_null.setdefault(nr_alt.lstrip("0"), []).append(k)
    spalten, kopf, zeilen, gesehen = None, [], [], {}
    leser = csv.reader(io.StringIO(text, newline=""), delimiter=trenner)
    nr, zeile_datei = 0, 1
    try:
        for roh_zeile in leser:
            nr += 1
            von, zeile_datei = zeile_datei, leser.line_num + 1
            if not any(c.strip() for c in roh_zeile):
                continue
            if sep_zeile:
                sep_zeile = False
                continue
            if spalten is None:
                kandidat = [namen.get(re.sub(r"\s+", " ", _excel_wert(c).strip().lower())) for c in roh_zeile]
                if not any(kandidat) and nr <= 10:
                    continue                    # Titelzeile über der Kopfzeile (z. B. 'Kundenliste Stand …')
                spalten, kopf = kandidat, roh_zeile
                fehlt = [titel(n) for n in PFLICHT if n not in spalten]
                if fehlt:
                    gefunden = ", ".join(c.strip() for c in roh_zeile if c.strip())[:200]
                    return dict(zeilen=[], fehler=[
                        f"Zeile {nr}: Kopfzeile ohne Spalte(n) {', '.join(fehlt)} (gelesen mit Trennzeichen "
                        f"{TRENNER.get(trenner, trenner)}: {gefunden}). Die erste Zeile muss die Spaltentitel "
                        "enthalten, wie beim Export."])
                continue
            zeilen.append(_zeile(nr, von, roh_zeile, spalten, kopf, trenner, nach_nr, ohne_null, gesehen, kontext,
                                 nur_neue))
    except csv.Error as e:
        return dict(zeilen=zeilen, fehler=[f"Zeile {nr} (Textzeile {leser.line_num} der Datei): Datei nicht lesbar "
                                           f"({e}). Bitte in Excel als 'CSV UTF-8' speichern."])
    if spalten is None:
        return dict(zeilen=[], fehler=["Keine Kopfzeile gefunden: die Datei braucht eine Zeile mit den Spaltentiteln "
                                       "(mindestens Kundennummer und Kundenname), wie beim Export."])
    return dict(zeilen=zeilen, fehler=[])


def _zeile(nr, von, roh_zeile, spalten, kopf, trenner, nach_nr, ohne_null, gesehen, kontext, nur_neue):
    """Eine Datenzeile prüfen (siehe vorschau)."""
    z = dict(nr=nr, fehler=[], hinweis=[], aenderung=[])
    index = {n: i for i, n in enumerate(spalten) if n}

    def ort(n):
        return f"Spalte {spalte(index[n])} ({titel(n)})" if n in index else titel(n)

    def mit_spalte(meldung):
        for n in sorted(index, key=lambda n: -len(titel(n))):
            if meldung.startswith(titel(n)):
                rest = meldung[len(titel(n)):].lstrip(": ")
                if rest == "unbekannt" and w.get(n):
                    rest = f"„{w[n]}“ unbekannt (Auswahlliste in den Einstellungen)"
                return f"{ort(n)}: {rest}"
        return meldung
    zuviel = [i for i, c in enumerate(roh_zeile) if i >= len(spalten) and c.strip()]
    if zuviel:
        z["fehler"].append(f"{len(roh_zeile)} Werte, aber nur {len(spalten)} Spalten in der Kopfzeile (Werte ab Spalte "
                           f"{spalte(zuviel[0])}): vermutlich ein {TRENNER.get(trenner, trenner)} im Text ohne "
                           "Anführungszeichen, die Werte sind verrutscht")
    for i, wert in enumerate(roh_zeile):
        if "\n" in wert or "\r" in wert:
            folge = wert.replace("\r\n", "\n").replace("\r", "\n").split("\n")[1:]
            if any(t.count(trenner) >= max(1, len(kopf) - 1) for t in folge):
                bis = von + wert.count("\n") + wert.count("\r") - wert.count("\r\n")
                z["fehler"].append(f"Spalte {spalte(i)}: Anführungszeichen \" nicht geschlossen, die Textzeilen "
                                   f"{von}–{bis} der Datei wurden zu einem Feld zusammengezogen")
    alt = nach_nr.get(_excel_wert(roh_zeile[index["kundennr"]]).strip()) if index["kundennr"] < len(roh_zeile) else None
    w = {}
    for name, wert in zip(spalten, roh_zeile):
        if not name:
            continue
        wert = re.sub(r"\r*\n|\r", "\n", _excel_wert(wert))       # Zeilenumbruch im Feld: immer \n
        if alt is not None and wert.strip() == wert_als_text(KUNDEN.feld(name), alt.get(name), bearbeiten=True):
            w[name] = alt.get(name)         # unverändert: alter Wert, auch wenn er die Prüfung heute nicht besteht
            continue
        if EXCEL_FEHLER.match(wert.strip()):
            z["fehler"].append(f"{ort(name)}: Excel-Fehlerwert {wert.strip()} statt Inhalt. In Excel den Wert als Text "
                               "eingeben (z. B. '+49 …) bzw. in der Quelldatei korrigieren")
            continue
        if re.fullmatch(r"\s*\d+([.,]\d+)?E\+\d+\s*", wert, re.I) and KUNDEN.feld(name).art not in ("zahl", "ganz"):
            z["fehler"].append(f"{ort(name)}: {wert.strip()} ist eine von Excel gekürzte Zahl. Spalte in Excel als "
                               "Text formatieren und den Wert neu eingeben")
            continue
        if name in ("land", "liefer_land") and wert.strip():
            kurz = LAENDER.get(wert.strip().lower(), wert.strip().upper() if len(wert.strip()) == 2 else None)
            if kurz and kurz != wert.strip():
                z["hinweis"].append(f"{titel(name)}: {wert.strip()} → {kurz}")
                wert = kurz
        try:
            w[name] = wert_aus_text(KUNDEN.feld(name), wert)
        except ValueError as e:
            z["fehler"].append(mit_spalte(str(e)))
    nr_text = w.get("kundennr")
    if nr_text and alt is None and str(nr_text).isdigit():
        treffer = ohne_null.get(str(nr_text).lstrip("0"), [])
        if len(treffer) == 1:
            alt = treffer[0]
            z["hinweis"].append(f"Kundennummer {nr_text} → {alt['kundennr']} (führende Null, die Excel entfernt hat)")
            w["kundennr"] = alt["kundennr"]
    _plz_auffuellen(w, z["hinweis"], alt)
    z.update(kundennr=w.get("kundennr"), name=w.get("name"))
    for n in PFLICHT:
        if not w.get(n) and titel(n) not in " ".join(z["fehler"]):
            z["fehler"].append(f"{ort(n)}: fehlt")
    if w.get("kundennr"):
        if w["kundennr"] in gesehen:
            z["fehler"].append(f"Kundennummer doppelt in der Datei (wie Zeile {gesehen[w['kundennr']]})")
        else:
            gesehen[w["kundennr"]] = nr
    kunde = {n: (alt or {}).get(n) for n in SPALTEN}
    for n in SPALTEN:
        if n in index:
            kunde[n] = w.get(n)
    aenderung = unterschiede(alt, kunde) if alt is not None else None
    if not z["fehler"] and kontext is not None:
        meldung = pruefen(KUNDEN, kunde, kontext)
        if meldung.startswith("FEHLER"):
            meldung = mit_spalte(meldung[len("FEHLER: "):])
            if aenderung == []:
                z["hinweis"].append(f"schon vorher im Programm: {meldung}")
            else:
                z["fehler"].append(meldung)
    z.update(kunde=kunde, kunden_id=alt["id"] if alt else None)
    if z["fehler"]:
        z["aktion"] = FEHLER
    elif alt is None:
        z["aktion"] = NEU
    else:
        z["aenderung"] = aenderung
        z["aktion"] = GLEICH if not aenderung else UEBERSPRUNGEN if nur_neue else AENDERN
    return z


def unterschiede(alt, neu):
    """Kurztexte der Änderungen, z. B. ['Telefon: 05250 123 → 05250 456']."""
    leer = lambda v: None if v in (None, "") else v
    return [f"{titel(n)}: {_kurz(n, alt.get(n))} → {_kurz(n, neu.get(n))}" for n in SPALTEN
            if leer(alt.get(n)) != leer(neu.get(n))]


def _kurz(n, w):
    return "leer" if w in (None, "") else wert_als_text(KUNDEN.feld(n), w)
