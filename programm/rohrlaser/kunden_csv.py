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

from . import csv_import
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
    (Excel 'CSV (Trennzeichen-getrennt)'); gemeinsame Importbasis (csv_import.text_lesen)."""
    return csv_import.text_lesen(roh)[0]


_excel_wert = csv_import.excel_wert      # ="…" (Export-Schutz für Excel) wieder zum reinen Text


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


# ====================================================================== Kundenimport-Assistent (25.11.2026)
# Master-Auftrag „Kundenlisten-CSV-Import grundlegend verbessern – EK-CSV-Import als technische Vorlage“: dieselbe
# Importbasis wie der EK-Import (csv_import: Lesen, Spaltenerkennung mit Sicherheit, Importprofile, Lauf mit
# Rückgängig, Fehlerbericht). Kundenfelder, Dublettenprüfung und Prüfregeln bleiben hier. Kundennummern werden nie
# erfunden (Patrick 23.11.2026: bei Neukunden immer von Hand) und nie geändert (Angebote, Aufträge, Vorgaben und
# Historie hängen an ihr).
IMPORTPROFILE = "kunden_importprofile"          # Einstellung (intern): Importprofile des Kundenimports
NEU_ANLEGEN, AKTUALISIEREN, UEBERSPRINGEN, ZUORDNEN = ("Als neuen Kunden anlegen", "Bestehenden Kunden aktualisieren",
                                                       "Überspringen", "Manuell zuordnen")
OPTIONEN = (AKTUALISIEREN, NEU_ANLEGEN, UEBERSPRINGEN, ZUORDNEN)
ERGAENZEN, UEBERSCHREIBEN = "nur leere Felder ergänzen", "Werte aus der Datei übernehmen"
G_NEU, G_AENDERN, G_GLEICH, G_DUBLETTE, G_FEHLER, G_UEBERSPRUNGEN = (
    "neue Kunden", "zu aktualisieren", "unverändert", "mögliche Dubletten", "fehlerhaft", "übersprungen")
GRUPPEN = (G_NEU, G_AENDERN, G_GLEICH, G_DUBLETTE, G_FEHLER, G_UEBERSPRUNGEN)
SICHER_PUNKTE, MOEGLICH_PUNKTE = 80, 25          # Dublette sicher (z. B. gleiche USt-ID) bzw. möglich

# Programmfelder (Titel) des Imports: Felder der Kundentabelle und zusätzliche, die in Ansprechpartner, Adressen,
# Kundenvorgaben oder Notizen gehen
_EXTRA = (("vorname", "Vorname"), ("nachname", "Nachname"), ("abteilung", "Abteilung"), ("position", "Position"),
          ("mobil", "Mobilnummer"), ("fax", "Fax"), ("hausnummer", "Hausnummer"), ("rabatt", "Rabatt [%]"),
          ("lieferadresse", "Lieferadresse"), ("rechnungsadresse", "Rechnungsadresse"))
_OHNE = ("angelegt", "angelegt_von", "geaendert", "archiviert")
FELDER = tuple((f.name, f.titel) for f in KUNDEN.felder if f.name not in _OHNE) + _EXTRA
FELD_TITEL = dict(FELDER)
FELD_TITEL.update(name="Firmenname", kundennr="Kundennummer", ort="Ort / Stadt", plz="Postleitzahl",
                  email="E-Mail-Adresse", telefon="Telefonnummer", ansprechpartner="Ansprechpartner (Name)")
IMPORT_PFLICHT = ("name",)          # Kundennummer: für Neukunden nötig, aber von Hand nachtragbar

# Spaltennamen je Feld (deutsch, englisch, aus anderen Programmen); normierter Vergleich (csv_import.norm)
SYNONYME = {
    "kundennr": ("kundennummer", "kundennr", "kdnr", "kdnummer", "kundenid", "debitor", "debitorennummer",
                 "debitornr", "debitorennr", "customerid", "customerno", "customernumber", "accountnumber",
                 "kontonummer", "personenkonto", "adressnummer"),
    "name": ("firmenname", "firma", "unternehmen", "unternehmensname", "company", "companyname", "customer",
             "customername", "kunde", "kundenname", "firmierung", "name1", "organisation", "organization",
             "accountname"),
    "firmenzusatz": ("firmenzusatz", "namenszusatz", "name2", "zusatz", "company2", "firmenname2"),
    "rechtsform": ("rechtsform", "legalform"),
    "kundengruppe": ("kundengruppe", "customergroup", "gruppe", "kundenkategorie"),
    "kundentyp": ("kundentyp", "kundenart", "customertype"),
    "branche": ("branche", "industry", "sector", "wirtschaftszweig"),
    "vorname": ("vorname", "firstname", "givenname", "ansprechpartnervorname"),
    "nachname": ("nachname", "lastname", "surname", "familienname", "zuname", "ansprechpartnernachname"),
    "ansprechpartner": ("ansprechpartner", "kontaktperson", "kontakt", "contact", "contactperson", "contactname",
                        "ansprechperson", "ap"),
    "abteilung": ("abteilung", "department", "bereich"),
    "position": ("position", "funktion", "jobtitle", "rolle", "stellung"),
    "email": ("email", "emailadresse", "mail", "mailadresse", "emailaddress", "eMail", "emailgeschaeftlich"),
    "telefon": ("telefon", "telefonnummer", "tel", "telefonzentrale", "festnetz", "phone", "telephone",
                "phonenumber", "telgeschaeftlich", "telefongeschaeftlich"),
    "mobil": ("mobil", "mobilnummer", "mobiltelefon", "handy", "mobile", "cell", "cellphone", "mobilephone"),
    "fax": ("fax", "telefax", "faxnummer", "faxnr"),
    "website": ("website", "webseite", "homepage", "internet", "web", "url", "www", "internetadresse"),
    "strasse": ("strasse", "straße", "str", "street", "anschrift", "adresse", "address", "addressline1",
                "strasseundhausnummer", "straßeundhausnummer", "strassehausnummer", "straßehausnr"),
    "hausnummer": ("hausnummer", "hausnr", "hnr", "housenumber", "streetnumber"),
    "plz": ("plz", "postleitzahl", "zip", "zipcode", "postcode", "postalcode"),
    "ort": ("ort", "stadt", "city", "town", "wohnort", "sitz"),
    "plz_ort": ("plzort", "plzundort"),
    "bundesland": ("bundesland", "state", "region", "kanton", "province"),
    "land": ("land", "country", "staat", "laenderkennzeichen", "länderkennzeichen", "countrycode"),
    "ust_id": ("ustid", "ustidnr", "ustidnummer", "umsatzsteuerid", "umsatzsteueridnr", "umsatzsteueridentnummer",
               "ustidentnr", "vatid", "vat", "vatnumber", "vatno", "uid"),
    "steuernr": ("steuernummer", "steuernr", "stnr", "taxnumber", "taxid"),
    "zahlungsbedingung": ("zahlungsbedingungen", "zahlungsbedingung", "zahlungskondition", "konditionen",
                          "paymentterms"),
    "zahlungsziel": ("zahlungsziel", "zahlungszieltage", "nettotage", "zieltage", "paymentdays", "dueindays"),
    "skonto": ("skonto", "skontoprozent", "skontosatz", "cashdiscount"),
    "skonto_tage": ("skontotage", "skontofrist", "skontoziel"),
    "rabatt": ("rabatt", "kundenrabatt", "rabattprozent", "discount"),
    "lieferadresse": ("lieferadresse", "lieferanschrift", "deliveryaddress", "shippingaddress"),
    "rechnungsadresse": ("rechnungsadresse", "rechnungsanschrift", "billingaddress", "invoiceaddress"),
    "notizen": ("notizen", "internenotizen", "internekundennotizen", "notiz", "notes", "kommentar", "comment"),
    "bemerkung": ("bemerkung", "bemerkungen", "remark", "remarks", "hinweistext"),
    "kreditlimit": ("kreditlimit", "creditlimit", "limit"),
    "waehrung": ("waehrung", "währung", "currency"),
    "zustaendig": ("zustaendig", "zuständig", "betreuer", "vertreter", "aussendienst", "accountmanager"),
}
for _f in KUNDEN.felder:            # die Titel des eigenen Exports gelten immer (Excel bearbeiten und zurückspielen)
    if _f.name not in _OHNE:
        SYNONYME.setdefault(_f.name, ())
        SYNONYME[_f.name] = (_f.titel,) + tuple(SYNONYME[_f.name])
# „Name“ ist Firma oder Person: entscheidet der Zusammenhang (kontext), bleibt immer ein Vorschlag
MEHRDEUTIG = {"name": ("name", "ansprechpartner", "nachname"), "nummer": ("kundennr",), "nr": ("kundennr",),
              "kontakt": ("ansprechpartner", "telefon", "email")}
for _w in MEHRDEUTIG:
    for _f2 in list(SYNONYME):
        SYNONYME[_f2] = tuple(x for x in SYNONYME[_f2] if csv_import.norm(x) != _w)
_REIHE_K = ("kundennr", "ust_id", "steuernr", "plz_ort", "skonto_tage", "skonto", "zahlungsziel", "zahlungsbedingung",
            "lieferadresse", "rechnungsadresse", "firmenzusatz", "name", "vorname", "nachname", "ansprechpartner",
            "email", "mobil", "fax", "telefon", "website", "hausnummer", "strasse", "plz", "ort", "bundesland",
            "land", "kundengruppe", "kundentyp", "branche", "abteilung", "position", "rabatt", "notizen",
            "bemerkung", "rechtsform", "kreditlimit", "waehrung", "zustaendig")
_REIHE_K = _REIHE_K + tuple(n for n in SYNONYME if n not in _REIHE_K)
INHALT = {"email": lambda a: a["email"], "website": lambda a: a["url"], "plz": lambda a: a["plz"],
          "telefon": lambda a: a["telefon"], "ust_id": lambda a: a["ust"],
          "zahlungsziel": lambda a: a["ganz"], "skonto": lambda a: a["zahl"], "rabatt": lambda a: a["zahl"]}


def _kontext(kand, erkannt, kopf):
    """„Name“: gibt es schon eine Firmenspalte, ist es die Person (mit Vorname: der Nachname), sonst die Firma."""
    if "name" in kand:
        if "name" in erkannt:
            return "nachname" if "vorname" in erkannt else "ansprechpartner"
        return "name"
    return kand[0]


def lesen(roh, dateiname=""):
    """Kundenliste lesen (gemeinsame Importbasis): Kodierung, Trennzeichen, Kopfzeile oder ohne Kopfzeile. Eine
    Kopfzeile braucht mindestens einen bekannten Spaltennamen (sonst sähe „Muster GmbH;Hauptstr. 1;Paderborn“
    wie eine Kopfzeile aus)."""
    bek = [w for ws in SYNONYME.values() for w in ws] + list(MEHRDEUTIG)
    return csv_import.datei_lesen(roh, dateiname, bekannte=bek, mindestens=2, kopf_ohne_bekannte=False)


def spalten_erkennen(daten):
    """{Feld: dict(spalte, sicherheit, grund)}: Namen (deutsch/englisch), mehrdeutige („Name“) und am Inhalt erkannte
    Spalten nur als Vorschlag; E-Mail, Website, PLZ, Telefon, USt-ID mit Gegenprobe am Inhalt."""
    return csv_import.spalten_erkennen(daten, SYNONYME, _REIHE_K, INHALT, MEHRDEUTIG, _kontext)


def eigener_export(kopf):
    """True, wenn die Datei der eigene Export ist (Spaltentitel wie im Reiter Kunden, Kundennummer und Name)."""
    t = {csv_import.norm(titel(n)) for n in SPALTEN}
    namen = {csv_import.norm(k) for k in kopf if k}
    return {csv_import.norm(titel("kundennr")), csv_import.norm(titel("name"))} <= namen and len(namen - t) == 0


# ------------------------------------------------------------------ Dublettenprüfung (Index statt Schleife je Zeile)
class Dublettenindex:
    """Vorhandene Kunden je Kundennummer, Namenskern, USt-ID, E-Mail, Firmendomain, Telefon und Anschrift (wie
    kunden_daten.dubletten, gleiche Punkte), einmal gebaut: 10.000 Zeilen gegen 10.000 Kunden ohne n × m Vergleiche.
    Ähnliche Namen allein machen keine Dublette sicher („Muster GmbH“ und „Muster Metallbau GmbH“ sind nur
    möglich), gleiche USt-ID oder gleicher Name an gleicher Anschrift schon."""

    def __init__(self, kunden, personen=()):
        from . import kunden_daten as kd
        from .mail import FREEMAIL, _domain
        self.kd, self._domain, self.freemail = kd, _domain, set(FREEMAIL)
        self.kunden = {}
        self.nr, self.ohne_null, self.kern, self.ust, self.mail, self.domain, self.tel, self.anschrift = \
            {}, {}, {}, {}, {}, {}, {}, {}
        je = {}
        for p in personen:
            je.setdefault(str(p.get("kundennr") or ""), []).append(p)
        for k in kunden:
            nr = str(k.get("kundennr") or "").strip()
            if not nr:
                continue
            self.kunden[nr] = k
            self.nr[nr] = nr
            if nr.isdigit():
                self.ohne_null.setdefault(nr.lstrip("0"), []).append(nr)
            kern = kd.namenskern(k.get("name"))
            if kern:
                self.kern.setdefault(kern, set()).add(nr)
            u = kd._ust(k.get("ust_id"))
            if u:
                self.ust.setdefault(u, set()).add(nr)
            ms = set(kd.mails(k.get("email")))
            tels = [k.get("telefon")]
            for p in je.get(nr, ()):
                ms |= set(kd.mails(p.get("email")))
                tels += [p.get("telefon"), p.get("mobil")]
            for m in ms:
                self.mail.setdefault(m, set()).add(nr)
                d = _domain(m)
                if d and d not in self.freemail:
                    self.domain.setdefault(d, set()).add(nr)
            for t in tels:
                z = kd._ziffern(t)
                if len(z) >= 6:
                    self.tel.setdefault(z, set()).add(nr)
            plz = str(k.get("plz") or "").strip() or kd.plz_ort_teilen(k.get("plz_ort"))[0]
            st = kd._strasse(k.get("strasse"))
            if plz and st:
                self.anschrift.setdefault((plz, st), set()).add(nr)

    def suchen(self, w):
        """[(Kundennummer, [Gründe], Punkte)] für die Werte w einer Zeile, stärkste zuerst; nur ab MOEGLICH_PUNKTE."""
        kd = self.kd
        punkte, gruende = {}, {}

        def plus(nrs, p, grund):
            for n in nrs:
                punkte[n] = punkte.get(n, 0) + p
                gruende.setdefault(n, []).append(grund)
        kern = kd.namenskern(w.get("name"))
        if kern:
            plus(self.kern.get(kern, ()), 50, "gleicher Firmenname")
            if len(kern) >= 5:
                aehnlich = set()
                for k2, nrs in self._kern_teile(kern):
                    aehnlich |= nrs
                plus(aehnlich - self.kern.get(kern, set()), 25, "ähnlicher Firmenname")
        plz = str(w.get("plz") or "").strip() or kd.plz_ort_teilen(w.get("plz_ort"))[0]
        st = kd._strasse(w.get("strasse"))
        if plz and st:
            plus(self.anschrift.get((plz, st), ()), 40, "gleiche Anschrift")
        u = kd._ust(w.get("ust_id"))
        if u:
            plus(self.ust.get(u, ()), 80, "gleiche Umsatzsteuer-ID")
        ms = set(kd.mails(w.get("email")))
        gleich_mail = set()
        for m in ms:
            nrs = self.mail.get(m, set())
            gleich_mail |= nrs
            plus(nrs, 60, f"gleiche E-Mail-Adresse {m}")
        doms = {self._domain(m) for m in ms} - self.freemail - {""}
        for d in doms:
            plus(self.domain.get(d, set()) - gleich_mail, 30, f"gleiche Firmendomain @{d}")
        tels = {kd._ziffern(w.get(f)) for f in ("telefon", "mobil")} - {""}
        for t in tels:
            if len(t) >= 6:
                plus(self.tel.get(t, ()), 30, "gleiche Telefonnummer")
        out = [(n, gruende[n], p) for n, p in punkte.items() if p >= MOEGLICH_PUNKTE]
        return sorted(out, key=lambda x: (-x[2], x[0]))

    def _kern_teile(self, kern):
        if not hasattr(self, "_lange"):
            self._lange = [(k, n) for k, n in self.kern.items() if len(k) >= 5]
        return [(k, n) for k, n in self._lange if k != kern and (kern in k or k in kern)]


# ------------------------------------------------------------------ Analyse (Vorschau ohne Datenbankänderung)
_ADRESSE = re.compile(r"^\s*(?P<strasse>.*?)[,;\n]+\s*(?:(?P<land>[A-Z]{1,2})\s*-\s*)?(?P<plz>\d{4,5})\s+(?P<ort>.+?)"
                      r"\s*$", re.S)


def adresse_teilen(text):
    """„Werkstr. 5, 33129 Delbrück“ -> dict(strasse, plz, ort[, land]) oder dict(name=text) wenn unklar."""
    t = str(text or "").strip()
    if not t:
        return None
    m = _ADRESSE.match(t)
    if not m:
        return dict(strasse=t)
    out = {k: v.strip() for k, v in m.groupdict().items() if v}
    if out.get("land"):
        out["land"] = {"D": "DE", "A": "AT"}.get(out["land"], out["land"])
    return out


def _werte_der_zeile(z, sp, dez=None):
    """Rohwerte je Feld (bereinigt): Excel-Schutz weg, Zeilenumbruch einheitlich, Land als Code, Hausnummer an die
    Straße, PLZ/Ort getrennt, Vor-/Nachname aus „Ansprechpartner“."""
    from . import kunden_daten as kd
    w, hinweis = {}, []
    for f, i in sp.items():
        if i is None or i >= len(z):
            continue
        t = re.sub(r"\r*\n|\r", "\n", csv_import.excel_wert(z[i])).strip()
        if t:
            w[f] = t
    if w.get("hausnummer"):
        if w.get("strasse") and not re.search(r"\d", w["strasse"].split()[-1]):
            w["strasse"] = f"{w['strasse']} {w['hausnummer']}"
        elif not w.get("strasse"):
            w["strasse"] = w["hausnummer"]
    if w.get("plz_ort") and not (w.get("plz") or w.get("ort")):
        w["plz"], w["ort"] = kd.plz_ort_teilen(w["plz_ort"])
    for f in ("land", "liefer_land"):
        if w.get(f):
            kurz = LAENDER.get(w[f].lower(), w[f].upper() if len(w[f]) == 2 else None)
            if kurz and kurz != w[f]:
                hinweis.append(f"{FELD_TITEL.get(f, f)}: {w[f]} → {kurz}")
                w[f] = kurz
    if w.get("ansprechpartner") and not (w.get("vorname") or w.get("nachname")):
        anrede, vor, nach = kd.name_teilen(w["ansprechpartner"])
        w.update({k: v for k, v in dict(anrede=anrede, vorname=vor, nachname=nach).items() if v})
    if w.get("plz") and re.fullmatch(r"\d{4}", w["plz"]) and (w.get("land") or "DE") == "DE":
        hinweis.append(f"PLZ: {w['plz']} → 0{w['plz']} (führende Null ergänzt)")
        w["plz"] = "0" + w["plz"]
    for f in ("skonto", "rabatt", "kreditlimit"):
        if w.get(f):
            x = csv_import.zahl(w[f].replace("%", ""), dez)
            if x is not None:
                w[f] = f"{x:g}".replace(".", ",")
    for f in ("zahlungsziel", "skonto_tage"):
        if w.get(f):
            m = re.search(r"\d+", w[f])
            if m and m.group(0) != w[f]:
                hinweis.append(f"{FELD_TITEL.get(f, f)}: „{w[f]}“ → {m.group(0)} Tage")
                w[f] = m.group(0)
    return w, hinweis


def _kundenwerte(w, fehler):
    """Werte für die Tabelle kunden (in Typen), Fehler je Feld in fehler."""
    out = {}
    for n in SPALTEN:
        if n in _OHNE or n not in w:
            continue
        try:
            out[n] = wert_aus_text(KUNDEN.feld(n), w[n])
        except ValueError as e:
            fehler.append(str(e))
    if "plz" in w or "ort" in w:
        out["plz_ort"] = " ".join(x for x in (w.get("plz"), w.get("ort")) if x) or None
    notiz = [f"Fax: {w['fax']}"] if w.get("fax") else []
    if w.get("mobil") and not (w.get("vorname") or w.get("nachname")):
        notiz.append(f"Mobil: {w['mobil']}")
    if notiz:
        out["notizen"] = "\n".join(x for x in [out.get("notizen")] + notiz if x)
    if out.get("ust_id"):
        out["ust_id"] = re.sub(r"[^0-9A-Z]", "", str(out["ust_id"]).upper())
    return out


def analysieren(db, daten, sp, modus=None, entscheidungen=None, kundennummern=None, fortschritt=None):
    """Vorschau des Kundenimports, ändert nichts. sp = {Feld: Spalte}; modus ERGAENZEN (Vorgabe für fremde Dateien:
    vorhandene Werte bleiben, nur leere Felder werden gefüllt) oder UEBERSCHREIBEN (Vorgabe für den eigenen Export:
    Werte der Datei ersetzen die alten; leere Zellen löschen nichts). entscheidungen = {Dateizeile: (Option,
    Kundennummer)} von Hand (OPTIONEN); kundennummern = {Dateizeile: Nummer} für Neukunden ohne Nummer.

    Ergebnis [dict(zeile, gruppe, option, kundennr, name, ziel (vorhandene Kundennummer), kunde (Werte), person,
    adressen, vorgaben, aenderungen [(Feld, alt, neu)], behalten [(Feld, alt, Datei)], treffer [(Nr, Gründe,
    Punkte)], fehler, hinweis, roh)]."""
    from . import kunden_daten as kd
    if modus is None:
        modus = UEBERSCHREIBEN if eigener_export(daten["kopf"]) else ERGAENZEN
    entscheidungen, kundennummern = entscheidungen or {}, kundennummern or {}
    vorhandene = db.zeilen("kunden")
    try:
        personen = db.zeilen("kunden_ansprechpartner")
    except Exception:           # noqa: BLE001  (Datei ohne Kundenverwaltung)
        personen = []
    index = Dublettenindex(vorhandene, personen)
    try:
        vorg = {str(v.get("kundennr")): v for v in db.zeilen("kundenvorgaben")}
    except Exception:           # noqa: BLE001
        vorg = {}
    kontext = db.kontext()
    dez = daten.get("dezimal")
    out, gesehen_nr, gesehen_kern = [], {}, {}
    for i, (n, z) in enumerate(enumerate(daten["zeilen"], daten.get("erste", 2))):
        if fortschritt and i % 500 == 0:
            fortschritt(i, len(daten["zeilen"]))
        w, hinweis = _werte_der_zeile(z, sp, dez)
        e = dict(zeile=n, roh=list(z), fehler=[], hinweis=hinweis, aenderungen=[], behalten=[], treffer=[], ziel=None,
                 person=None, adressen=[], vorgaben={}, name=w.get("name") or "", kundennr=w.get("kundennr") or "")
        out.append(e)
        if not w:
            e.update(gruppe=G_UEBERSPRUNGEN, option=UEBERSPRINGEN, hinweis=["leere Zeile"])
            continue
        if (entscheidungen.get(n) or (None,))[0] == UEBERSPRINGEN:      # von Hand übersprungen, auch fehlerhafte
            e.update(gruppe=G_UEBERSPRUNGEN, option=UEBERSPRINGEN, kunde={}, hinweis=["von Hand übersprungen"])
            continue
        for f in IMPORT_PFLICHT:
            if not w.get(f):
                e["fehler"].append(f"{FELD_TITEL[f]} fehlt (Pflichtangabe)")
        for f, t in w.items():
            if EXCEL_FEHLER.match(t):
                e["fehler"].append(f"{FELD_TITEL.get(f, f)}: Excel-Fehlerwert {t} statt Inhalt")
            elif re.fullmatch(r"\s*\d+([.,]\d+)?E\+\d+\s*", t, re.I) and f in ("telefon", "mobil", "fax", "kundennr",
                                                                               "plz", "ust_id"):
                e["fehler"].append(f"{FELD_TITEL.get(f, f)}: {t} ist eine von Excel gekürzte Zahl")
        kunde = _kundenwerte(w, e["fehler"])
        if w.get("email") and not kd.mails(w["email"]):
            e["fehler"].append(f"E-Mail-Adresse „{w['email']}“ ist ungültig")
        # Ansprechpartner, Adressen, Vorgaben
        if w.get("vorname") or w.get("nachname"):
            e["person"] = {k: w[k] for k in ("anrede", "vorname", "nachname", "abteilung", "position", "mobil")
                           if w.get(k)}
            if w.get("email"):
                e["person"]["email"] = (kd.mails(w["email"]) or [w["email"]])[0]
            if w.get("telefon"):
                e["person"]["telefon"] = w["telefon"]
            if not e["person"].get("nachname"):
                e["person"]["nachname"], e["person"]["vorname"] = e["person"].pop("vorname", ""), None
            kunde.setdefault("ansprechpartner", kd.name_voll(e["person"]))
        for f, art in (("lieferadresse", kd.LIEFERUNG), ("rechnungsadresse", kd.RECHNUNG)):
            a = adresse_teilen(w.get(f))
            if a:
                e["adressen"].append(dict(a, art=art, standard="ja", name=w.get("name")))
        if w.get("rabatt"):
            try:
                e["vorgaben"]["rabatt"] = kd._wert("rabatt", w["rabatt"])
            except kd.KundenFehler as ex:
                e["fehler"].append(str(ex))
        # Kundennummer und Dubletten
        nr = (w.get("kundennr") or "").strip() or str(kundennummern.get(n) or "").strip()
        if nr and nr not in index.kunden and nr.isdigit():
            alt_nr = index.ohne_null.get(nr.lstrip("0"), [])
            if len(alt_nr) == 1:
                e["hinweis"].append(f"Kundennummer {nr} → {alt_nr[0]} (führende Null, die Excel entfernt hat)")
                nr = alt_nr[0]
        e["kundennr"] = nr
        if not w.get("kundennr") and nr and nr in index.kunden:
            e["fehler"].append(f"Kundennummer {nr} ist schon vergeben ({index.kunden[nr].get('name')}): für einen "
                               f"neuen Kunden eine freie Nummer eintragen oder „{ZUORDNEN}“ wählen")
        if nr and nr in gesehen_nr:
            e["fehler"].append(f"Kundennummer {nr} doppelt in der Datei (wie Zeile {gesehen_nr[nr]})")
        elif nr:
            gesehen_nr[nr] = n
        kern = kd.namenskern(w.get("name"))
        if kern and kern in gesehen_kern and not nr:
            e["hinweis"].append(f"gleicher Firmenname wie Zeile {gesehen_kern[kern]} in der Datei")
        gesehen_kern.setdefault(kern, n)
        if nr and nr in index.kunden:
            e["treffer"] = [(nr, ["gleiche Kundennummer"], 1000)]
        else:
            e["treffer"] = index.suchen(dict(w, plz_ort=kunde.get("plz_ort")))
        # Option: von Hand, sonst Vorschlag
        hand = entscheidungen.get(n)
        if hand:
            option, ziel = hand[0], (hand[1] if len(hand) > 1 else None)
        elif nr and nr in index.kunden:
            option, ziel = AKTUALISIEREN, nr
        elif e["treffer"] and e["treffer"][0][2] >= SICHER_PUNKTE:
            option, ziel = AKTUALISIEREN, e["treffer"][0][0]
            e["hinweis"].append(f"sicher erkannt als Kunde {ziel} ({', '.join(e['treffer'][0][1])})")
        elif e["treffer"]:
            option, ziel = None, None           # mögliche Dublette: entscheidet der Anwender
        else:
            option, ziel = NEU_ANLEGEN, None
        if option in (AKTUALISIEREN, ZUORDNEN) and ziel not in index.kunden:
            e["fehler"].append(f"Kunde {ziel or '?'} zum Zuordnen gibt es nicht")
        e.update(option=option, ziel=ziel if option in (AKTUALISIEREN, ZUORDNEN) else None, kunde=kunde)
        if e["fehler"]:
            e["gruppe"] = G_FEHLER
            continue
        if option is None:
            t = e["treffer"][0]
            e["gruppe"] = G_DUBLETTE
            e["hinweis"].append(f"mögliche Dublette von {t[0]} {index.kunden[t[0]].get('name') or ''} "
                                f"({', '.join(t[1])}): bitte entscheiden")
            continue
        if option == UEBERSPRINGEN:
            e["gruppe"] = G_UEBERSPRUNGEN
            continue
        if option == NEU_ANLEGEN:
            if not nr:
                e["fehler"].append("Kundennummer fehlt: bei neuen Kunden bitte von Hand eintragen (wird nie "
                                   "automatisch vergeben)")
            elif nr in index.kunden:
                e["fehler"].append(f"Kundennummer {nr} ist schon vergeben ({index.kunden[nr].get('name')})")
            meld = kd.pruefen(db, dict(w, kundennr=""))
            e["fehler"] += [m for m in meld if "Kundennummer" not in m]
            if not e["fehler"] and kontext is not None:
                m = pruefen(KUNDEN, dict({n_: None for n_ in SPALTEN}, **kunde, kundennr=nr), kontext)
                if m.startswith("FEHLER"):
                    e["fehler"].append(m[len("FEHLER: "):])
            e["gruppe"] = G_FEHLER if e["fehler"] else G_NEU
            continue
        # aktualisieren / zuordnen: nie die Kundennummer, nur echte Unterschiede
        alt = index.kunden[ziel]
        e["kundennr"] = ziel
        for f, neu in kunde.items():
            if f in ("kundennr", "plz_ort") or neu in (None, ""):
                continue
            a = alt.get(f)
            if a not in (None, "") and str(a).strip() == str(neu).strip():
                continue
            if isinstance(a, (int, float)) and isinstance(neu, (int, float)) and abs(a - neu) < 1e-9:
                continue
            if a in (None, "") or modus == UEBERSCHREIBEN:
                e["aenderungen"].append((f, a, neu))
            else:
                e["behalten"].append((f, a, neu))
        if any(f in ("plz", "ort") for f, _a, _n in e["aenderungen"]):
            plz_ = next((x for f, _a, x in e["aenderungen"] if f == "plz"), alt.get("plz"))
            ort_ = next((x for f, _a, x in e["aenderungen"] if f == "ort"), alt.get("ort"))
            po = " ".join(x for x in (plz_, ort_) if x) or None
            if po != alt.get("plz_ort"):
                e["aenderungen"].append(("plz_ort", alt.get("plz_ort"), po))
        if e["vorgaben"].get("rabatt") is not None:
            ra = (vorg.get(ziel) or {}).get("rabatt")
            if ra is None or (modus == UEBERSCHREIBEN and abs(float(ra) - e["vorgaben"]["rabatt"]) > 1e-9):
                e["aenderungen"].append(("rabatt", ra, e["vorgaben"]["rabatt"]))
            elif abs(float(ra) - e["vorgaben"]["rabatt"]) > 1e-9:
                e["behalten"].append(("rabatt", ra, e["vorgaben"]["rabatt"]))
        if e["person"]:
            name = kd.name_voll(e["person"]).lower()
            schon = [p for p in personen if str(p.get("kundennr")) == ziel and kd.name_voll(p).lower() == name]
            if schon:
                e["person"] = None
            else:
                e["aenderungen"].append(("Ansprechpartner", None, kd.name_voll(e["person"])))
        neue_adr = []
        for a in e["adressen"]:
            schon = [x for x in _adressen_von(db, ziel) if x.get("art") == a["art"] and
                     kd._strasse(x.get("strasse")) == kd._strasse(a.get("strasse"))]
            if not schon:
                neue_adr.append(a)
                e["aenderungen"].append((a["art"], None, kd.adresse_text(a)))
        e["adressen"] = neue_adr
        if e["behalten"]:
            e["hinweis"].append("vorhandene Werte bleiben: " + ", ".join(
                f"{FELD_TITEL.get(f, f)} ({_kurz_wert(a)} statt {_kurz_wert(x)})" for f, a, x in e["behalten"][:4]))
        e["gruppe"] = G_AENDERN if e["aenderungen"] else G_GLEICH
    return out


_ADR_CACHE = {}


def _adressen_von(db, kundennr):
    try:
        k = id(db)
        if _ADR_CACHE.get("db") != k:
            _ADR_CACHE.clear()
            _ADR_CACHE["db"] = k
            je = {}
            for a in db.zeilen("kunden_adressen"):
                je.setdefault(str(a.get("kundennr")), []).append(a)
            _ADR_CACHE["je"] = je
        return _ADR_CACHE["je"].get(str(kundennr), [])
    except Exception:           # noqa: BLE001
        return []


def _kurz_wert(w):
    t = "leer" if w in (None, "") else str(w)
    return t if len(t) <= 30 else t[:28] + "…"


def zaehlen_import(posten):
    out = {g: 0 for g in GRUPPEN}
    for e in posten:
        out[e["gruppe"]] += 1
    return out


def fehlerbericht(posten, kopf=None):
    zeilen = [(e["zeile"], e["gruppe"], "; ".join(e["fehler"] or e["hinweis"]), e["roh"]) for e in posten
              if e["gruppe"] in (G_FEHLER, G_DUBLETTE)]
    return csv_import.fehlerbericht_csv(zeilen, kopf)


# ------------------------------------------------------------------ Übernehmen und Rückgängig
def uebernehmen(db, posten, datei="", importprofil="", sichern=True, fortschritt=None):
    """Neue und zu aktualisierende Kunden übernehmen, alles als ein Importlauf (Art „Kunden“, rueckgaengig()):
    neue Kunden mit Ansprechpartner, Adressen und Rabatt, bei vorhandenen nur die Änderungen der Vorschau; jede
    Änderung steht in der Kundenhistorie. Kundennummern werden nie geändert, Angebote und Aufträge bleiben mit
    ihren Kunden verknüpft. Vorher Datensicherung. Jeder Fehler nimmt den ganzen Lauf zurück. Ergebnis dict(import_id,
    neu, geaendert, personen, adressen, sicherung)."""
    from . import kunden_daten as kd
    kd._schreibbar(db)
    zu = [e for e in posten if e["gruppe"] in (G_NEU, G_AENDERN)]
    erg = dict(import_id=None, neu=0, geaendert=0, personen=0, adressen=0, sicherung=None)
    if not zu:
        return erg
    if sichern:
        try:
            erg["sicherung"] = db.sicherung(zusatz="vor_Kundenimport")
        except Exception:       # noqa: BLE001  (ohne Sicherungsordner, z. B. Tests: Rückgängig bleibt möglich)
            from . import protokoll
            protokoll.warnung("Kundenimport: Sicherung nicht möglich")
    z = zaehlen_import(posten)
    lauf = csv_import.lauf_beginnen(db, csv_import.ART_KUNDEN, datei, importprofil, len(posten), "",
                                    dict(unveraendert=z[G_GLEICH], doppelt=z[G_DUBLETTE], fehler=z[G_FEHLER],
                                         offen=z[G_UEBERSPRUNGEN]))
    erg["import_id"] = lauf.id
    jetzt = kd._jetzt()
    wer = kd._wer(db)
    kunden_je = {str(k.get("kundennr")): k for k in db.zeilen("kunden")}
    vorg_je = {str(v.get("kundennr")): v for v in db.zeilen("kundenvorgaben")}
    try:
        for i, e in enumerate(zu):
            if fortschritt and i % 200 == 0:
                fortschritt(i, len(zu))
            nr = e["kundennr"]
            if e["gruppe"] == G_NEU:
                kw = {k: v for k, v in e["kunde"].items() if v is not None}
                kw.update(kundennr=nr, angelegt=jetzt, geaendert=jetzt, angelegt_von=wer)
                kw.setdefault("status", kd.AKTIV)
                kw.setdefault("kundentyp", "Firma")
                kunden_je[nr] = dict(kw, id=lauf.neu("kunden", kw))
                if e["vorgaben"]:
                    lauf.neu("kundenvorgaben", dict(e["vorgaben"], kundennr=nr))
                with db.con:
                    kd._historie(db, nr, kd.H_ANGELEGT, f"Kunde {nr} {kw.get('name') or ''} angelegt (CSV-Import "
                                 f"{str(datei).replace(chr(92), '/').rsplit('/', 1)[-1]})", zeit=jetzt)
                erg["neu"] += 1
            else:
                k = kunden_je[nr]
                felder = {f: neu for f, _a, neu in e["aenderungen"] if f in SPALTEN}
                if felder:
                    lauf.aendern("kunden", k, dict(felder, geaendert=jetzt))
                if any(f == "rabatt" for f, _a, _n in e["aenderungen"]):
                    v = vorg_je.get(nr)
                    if v is None:
                        vorg_je[nr] = dict(id=lauf.neu("kundenvorgaben", dict(kundennr=nr,
                                                                              rabatt=e["vorgaben"]["rabatt"])))
                    else:
                        lauf.aendern("kundenvorgaben", v, dict(rabatt=e["vorgaben"]["rabatt"]))
                with db.con:
                    for f, a, neu in e["aenderungen"]:
                        if f == "plz_ort":
                            continue
                        kd._historie(db, nr, kd.H_GEAENDERT, "CSV-Import", feld=kd.TITEL.get(f, FELD_TITEL.get(f, f)),
                                     alt=a, neu=neu, zeit=jetzt)
                erg["geaendert"] += 1
            if e.get("person"):
                p = {kk: v for kk, v in e["person"].items() if v}
                p.update(kundennr=nr, aktiv="ja", geaendert=jetzt)
                if e["gruppe"] == G_NEU:
                    p["haupt"] = "ja"
                lauf.neu("kunden_ansprechpartner", p)
                erg["personen"] += 1
            for a in e.get("adressen") or ():
                lauf.neu("kunden_adressen", dict({kk: v for kk, v in a.items() if v}, kundennr=nr, geaendert=jetzt))
                erg["adressen"] += 1
        lauf.flush()
    except Exception as ex:     # noqa: BLE001  (alles zurücknehmen, dann melden)
        lauf.flush()
        rueckgaengig(db, lauf.id, status="abgebrochen, zurückgenommen")
        raise ValueError(f"Kundenimport abgebrochen und vollständig zurückgenommen: {ex}") from ex
    csv_import.lauf_abschliessen(db, lauf, erg["neu"], erg["geaendert"], 0,
                                 protokoll=dict(erg, fehler=[f"Zeile {e['zeile']}: {'; '.join(e['fehler'])}"
                                                             for e in posten if e["gruppe"] == G_FEHLER][:200]))
    _ADR_CACHE.clear()
    return erg


def _verweise(db, nr):
    """Was schon an der Kundennummer hängt (Angebote, Aufträge, Anfragen, Importprofile) als Text, sonst ""."""
    from . import db_verbindung
    da = set(db_verbindung.tabellen(db.con))
    out = []
    for sql, was in (("SELECT COUNT(*) FROM angebote WHERE kundennr=?", "Angebot(e)"),
                     ("SELECT COUNT(*) FROM auftrag_kopf WHERE daten LIKE ?", "Auftrag/Aufträge"),
                     ("SELECT COUNT(*) FROM anfragen WHERE kundennr=?", "Anfrage(n)"),
                     ("SELECT COUNT(*) FROM importprofile WHERE kundennr=?", "Importprofil(e)")):
        if sql.split(" FROM ")[1].split()[0] not in da:
            continue
        wert = f'%"kundennr": "{nr}"%' if "LIKE" in sql else nr
        n = db.con.execute(sql, (wert,)).fetchone()[0]
        if n:
            out.append(f"{n} {was}")
    return ", ".join(out)


def rueckgaengig(db, import_id, status="rückgängig gemacht"):
    """Kundenimport zurücknehmen: neu angelegte Kunden (nur solange kein Angebot und kein Auftrag an ihnen hängt),
    Ansprechpartner, Adressen und Vorgaben löschen, geänderte Felder auf den alten Wert; Vermerk in der Historie."""
    from . import kunden_daten as kd
    posten = csv_import.posten_des_laufs(db, import_id)
    meldungen, behalten = [], set()
    for p in posten:
        if p["tabelle"] == "kunden" and p["aktion"] == "neu":
            nr = str((p["neu"] or {}).get("kundennr") or "")
            n = _verweise(db, nr)
            if n:
                behalten.add(nr)
                meldungen.append(f"Kunde {nr} bleibt: {n} hängen schon an ihm")
    if behalten:
        with db.con:
            db.con.execute("DELETE FROM material_import_posten WHERE import_id=? AND aktion='neu' AND tabelle IN "
                           "('kunden', 'kunden_ansprechpartner', 'kunden_adressen', 'kundenvorgaben') AND ("
                           + " OR ".join(["neu LIKE ?"] * len(behalten)) + ")",
                           [import_id] + [f'%"kundennr": "{nr}"%' for nr in behalten])
    n, m2 = csv_import.rueckgaengig(db, import_id, status)
    nrs = {str((p["neu"] or {}).get("_kontext", {}).get("kundennr") or (p["neu"] or {}).get("kundennr") or "")
           for p in posten} - {""}
    with db.con:
        for nr in sorted(nrs):
            if kd.kunde(db, nr):
                kd._historie(db, nr, kd.H_GEAENDERT, f"CSV-Import (Lauf {import_id}) rückgängig gemacht")
    _ADR_CACHE.clear()
    return n, meldungen + m2
