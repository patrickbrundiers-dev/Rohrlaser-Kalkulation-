"""Materialpreise aus einer Einkaufs-CSV des ERP (Plan „Materialpreise aus ERP-CSV“, Patrick 30.10.2026, Freigabe
„Alle Empfehlungen“ = 1a 2a 3a 4a 5a 6a 7a 8a 9b 10a 11a).

Die CSV enthält je Kauf Kaufdatum, Menge [m], Meterpreis [€/m], Artikelnummer und die EK-Bezeichnung („Rohr
40x40x3 S235JRH feuerverzinkt“). Ablauf:
1. lesen() + spalten_vorschlag(): Spalten am Kopf erkennen, sonst Zuordnung von Hand (gespeichert als Vorlage je
   Spaltenkopf, Einstellung erp_vorlagen); kaeufe() prüft Datum und Zahlen je Zeile.
2. zerlegen(): Profil, Werkstoff und Oberfläche aus der Bezeichnung; Ampel grün (eindeutig), gelb (Werkstoff
   mehrdeutig/fehlt, Oberfläche unbekannt), rot (Profil fehlt oder nicht erkannt). Bestätigte Zuordnungen stehen je
   ERP-Artikel in erp_zuordnung (7a), auch „überspringen“.
3. auswerten(): Übersicht je Profil + Werkstoff + Oberfläche: gewichteter Durchschnitt nach Menge über die letzten
   erp_monate Monate, Ausreißer über ±erp_ausreisser vom Median zählen nicht (je Kauf änderbar), dazu letzter Preis,
   Min/Max und der heutige Preis aus den Stammdaten. Nur Anzeige: die Stammdaten-Preise bleiben unberührt.
4. angebot_vorschlag() (Patrick 30.10.2026 17:39, Freigabe „Alle Empfehlungen“ 17:44): nach dem Optimieren wählt das Angebot
   je Profil + Werkstoff + Oberfläche den passenden Kauf zur benötigten Menge (1a: neuester Kauf mit 0,5- bis
   2-facher Menge, sonst der neueste; 3a: nur Käufe der letzten erp_monate Monate) und speichert ihn mit Bemerkung
   in angebote.erp_preise. rechnen.lieferstange_preis nimmt ihn nach dem Preis von Hand (2a: eigener Wert geht vor),
   ohne passenden Kauf wie bisher Lieferlängen/Preise/Tonnenpreis. Die Bemerkung steht nur intern (4a).

Die Käufe stehen nur in der eigenen Datendatei (erp_kaeufe) und werden nicht mit den Kollegen abgeglichen; die im
Angebot gewählten Preise gehen mit dem Angebot an alle Plätze. Ohne Qt-Fenster."""
import datetime
import math
import re
from statistics import median

from . import csv_import, db_verbindung

FELDER = (("datum", "Kaufdatum"), ("menge", "Menge [m]"), ("preis", "Meterpreis [€/m]"),
          ("artikelnr", "Artikelnummer"), ("bezeichnung", "EK-Artikel (Bezeichnung)"),
          # Patricks ERP-Export (EKexport_S235/S355.csv, 20.11.2026): Zusatztext mit Norm, Güte und Oberfläche
          # („EN 10219- S235 HL 6m gestrahlt“), Preiseinheit PE (Preis je PE Meter)
          ("zusatz", "Zusatztext (Norm, Güte)"), ("pe", "Preiseinheit"),
          # Patrick 23.11.2026: Lieferzeit je Material = Liefertermin (L-Termin) minus Kaufdatum (Datum Erf.)
          ("liefertermin", "Liefertermin"),
          # Master-Auftrag EK-CSV-Import 25.11.2026: weitere Spalten aus ERP-, Warenwirtschafts- und Lieferantendateien
          ("lieferant", "Lieferant"), ("bestellnr", "Lieferantenartikelnummer"), ("werkstoff", "Werkstoff"),
          ("abmessung", "Abmessung / Profil"), ("oberflaeche", "Oberfläche"), ("einheit", "Mengeneinheit"),
          ("waehrung", "Währung"), ("laenge", "Stangenlänge [mm]"))
FELD_TITEL = dict(FELDER)
PFLICHT = ("datum", "menge", "preis", "bezeichnung")      # Artikelnummer darf fehlen (dann zählt die Bezeichnung)
VORLAGEN = "erp_vorlagen"       # Einstellung (intern): {Spaltenkopf mit | getrennt: {Feld: Spaltennummer}}
GRUEN, GELB, ROT = "grün", "gelb", "rot"

# Spaltenköpfe je Feld, normalisiert (klein, nur Buchstaben/Ziffern): erst gleich, dann enthalten
_KOPF = {"datum": ("kaufdatum", "datumerf", "bestelldatum", "datum", "belegdatum", "lieferdatum", "eingangsdatum",
                   "rechnungsdatum", "wareneingang", "buchungsdatum", "erfassungsdatum", "auftragsdatum", "date",
                   "orderdate", "purchasedate", "invoicedate"),
         "preis": ("meterpreis", "preisjem", "preism", "eurom", "ekpreis", "einkaufspreis", "einzelpreis",
                   "nettopreis", "nettoeinzelpreis", "stueckpreis", "preisjeeinheit", "preis", "ek", "price",
                   "unitprice", "netprice", "purchaseprice"),
         "artikelnr": ("artikelnummer", "artikelnr", "artnr", "materialnummer", "materialnr", "matnr", "sachnummer",
                       "itemno", "itemnumber", "articleno", "articlenumber", "sku", "nummer"),
         "menge": ("mengeinmeter", "mengem", "menge", "bestellmenge", "liefermenge", "eingangsmenge", "meter",
                   "quantity", "qty", "laenge", "länge"),
         "bezeichnung": ("ekartikel", "artikelbezeichnung", "materialbezeichnung", "bezeichnung", "artikeltext",
                         "kurztext", "beschreibung", "text", "description", "artikel", "material"),
         "zusatz": ("zusatztext", "zusatz", "langtext", "bezeichnung2", "zusatzbezeichnung"),
         "pe": ("pe", "preiseinheit", "preiseinh", "priceunit"),
         "liefertermin": ("ltermin", "liefertermin", "lieferterminbestaetigt", "liefertermingeplant", "wunschtermin"),
         "lieferant": ("lieferant", "lieferantenname", "lieferantname", "kreditor", "kreditorname", "supplier",
                       "vendor", "hersteller", "haendler", "händler"),
         "bestellnr": ("lieferantenartikelnummer", "lieferantenartikelnr", "lieferantenartnr", "artikelnrlieferant",
                       "artikelnummerlieferant", "herstellerartikelnummer", "supplierpartno", "vendorpartno",
                       "supplieritemno", "fremdartikelnummer", "fremdartnr"),
         "werkstoff": ("werkstoff", "werkstoffnummer", "guete", "güte", "stahlsorte", "stahlguete", "qualitaet",
                       "qualität", "grade", "materialqualitaet"),
         "abmessung": ("abmessung", "abmessungen", "dimension", "masse", "maße", "groesse", "größe", "profil",
                       "profilabmessung", "size"),
         "oberflaeche": ("oberflaeche", "oberfläche", "ausfuehrung", "ausführung", "finish", "surface"),
         "einheit": ("mengeneinheit", "me", "einheit", "unit", "uom", "basismengeneinheit"),
         "waehrung": ("waehrung", "währung", "whrg", "wahrung", "currency", "cur"),
         "laenge": ("stangenlaenge", "stangenlänge", "lieferlaenge", "lieferlänge", "fixlaenge", "laengemm")}
# spezifische Felder zuerst: „Meterpreis“ enthält „meter“, „Lieferantenartikelnummer“ enthält „artikelnummer“
_REIHE = ("preis", "bestellnr", "artikelnr", "liefertermin", "datum", "menge", "zusatz", "bezeichnung", "pe",
          "lieferant", "werkstoff", "abmessung", "oberflaeche", "einheit", "waehrung", "laenge")
NUR_GENAU = ("pe", "liefertermin", "einheit", "waehrung", "laenge")   # nur gleicher Name (kurze Wörter stecken in vielen)
IMPORTPROFILE = "ek_importprofile"      # Einstellung (intern): Importprofile des EK-Imports (csv_import.profil_*)
PREIS_MARKE = "ek_preis_markierung"     # Einstellung: Preisänderung ab so viel Prozent markieren (Vorgabe 10 %)
PREIS_MARKE_VORGABE = 10.0


class ErpFehler(ValueError):
    """Datei nicht lesbar (Text für den Benutzer)."""


def _norm(t):
    return re.sub(r"[^0-9a-zäöüß]+", "", str(t or "").lower())


# ------------------------------------------------------------------ 1. Datei lesen
def lesen(roh, dateiname=""):
    """CSV (Bytes oder Text, auch .xlsx) -> dict(kopf, zeilen [Zellen], erste = Dateizeile der ersten Datenzeile,
    mit_kopf, kodierung, trenner, dezimal, meldungen) über die gemeinsame Importbasis (csv_import.datei_lesen):
    Kodierung, Trennzeichen, Kopfzeile (Titelzeilen davor werden übersprungen) oder Datei ohne Kopfzeile (Spalten
    werden dann am Inhalt erkannt, spalten_erkennen)."""
    try:
        return csv_import.datei_lesen(roh, dateiname, bekannte=[w for ws in _KOPF.values() for w in ws])
    except csv_import.ImportFehler as e:
        raise ErpFehler(str(e)) from None


def _trenner(zeilen):
    """Trennzeichen nach Gleichmäßigkeit (csv_import.trenner_erkennen)."""
    return csv_import.trenner_erkennen(zeilen)


def spalten_vorschlag(kopf):
    """{Feld: Spaltennummer} aus den Spaltenköpfen; nicht erkannte Felder fehlen."""
    namen = [_norm(k) for k in kopf]
    frei, out = set(range(len(kopf))), {}
    for gleich in (True, False):
        for feld in _REIHE:
            if feld in out:
                continue
            for wort in _KOPF[feld]:
                if not gleich and (feld in NUR_GENAU or len(wort) < 3):
                    break               # „pe“ steckt in vielen Wörtern, der Liefertermin darf kein Datum wegnehmen: nur genau
                treffer = [i for i in sorted(frei) if (namen[i] == wort if gleich else wort in namen[i])]
                if treffer:
                    out[feld] = treffer[0]
                    frei.discard(treffer[0])
                    break
    return out


def _inhalt_bezeichnung(a):
    return max(a["masse"], 0.9 * a["text"] if a["masse"] >= 0.2 else 0)


def _inhalt_artikelnr(a):
    """Artikelnummern: Ziffern oder kurze Codes, meist verschieden, keine Abmessung, kein Datum."""
    if a["masse"] >= 0.1 or a["datum"] >= 0.1 or a["eindeutig"] < 0.05:
        return 0
    return 1.0 if a["ganz"] > 0.9 or (a["text"] > 0.5 and a["zahl"] < 0.1) else 0


# Gegenprobe und Erkennung ohne Kopfzeile: welcher Inhalt passt zu welchem Feld (csv_import.inhalt_art)
INHALT = {"datum": lambda a: a["datum"],
          "liefertermin": lambda a: a["datum"],
          "preis": lambda a: a["zahl"] if a["datum"] < 0.5 and a["ganz"] < 0.6 else (0.4 if a["zahl"] > 0.9 else 0),
          "menge": lambda a: a["zahl"] if a["datum"] < 0.5 else 0,
          "bezeichnung": _inhalt_bezeichnung,
          "artikelnr": _inhalt_artikelnr}


def spalten_erkennen(daten):
    """{Feld: dict(spalte, sicherheit, grund)} über die gemeinsame Spaltenerkennung: erst nach Spaltennamen (wie
    spalten_vorschlag), Gegenprobe am Inhalt (Spalte „Preis“ mit Datumswerten = nur Vorschlag); ohne Kopfzeile
    Datum, Preis, Menge, EK-Artikel und Artikelnummer am Inhalt (immer nur Vorschlag zum Bestätigen)."""
    if daten.get("mit_kopf", True):
        out = {}
        for f, i in spalten_vorschlag(daten["kopf"]).items():
            s, grund = csv_import.SICHER, f"Spaltenname „{daten['kopf'][i]}“"
            werte = csv_import.spalten_werte(daten, i)
            if f in INHALT and any(c.strip() for c in werte) and INHALT[f](csv_import.inhalt_art(werte)) < 0.5:
                s, grund = csv_import.VORSCHLAG, grund + ", aber der Inhalt passt nicht dazu – bitte prüfen"
            out[f] = dict(spalte=i, sicherheit=s, grund=grund)
        return out
    return csv_import.spalten_erkennen(daten, {f: () for f in _KOPF},
                                       reihe=("datum", "liefertermin", "bezeichnung", "preis", "menge", "artikelnr"),
                                       inhalt=INHALT)


def vorlage_schluessel(kopf):
    return "|".join(_norm(k) for k in kopf)


def zuordnung_fuer(kopf, vorlagen, profile=None):
    """Gespeicherte Zuordnung für genau diesen Spaltenkopf (Vorlage aus dem letzten Import), sonst ein passendes
    Importprofil (auch bei anderer Spaltenreihenfolge, csv_import.profil_passend), sonst der Vorschlag.
    Ergebnis (zuordnung, gespeichert)."""
    if profile and vorlage_schluessel(kopf) not in (vorlagen or {}):
        _n, _p, sp = csv_import.profil_passend(profile, kopf)
        if sp:
            return sp, True
    v = (vorlagen or {}).get(vorlage_schluessel(kopf))
    if v and all(isinstance(i, int) and 0 <= i < len(kopf) for i in v.values()):
        v = dict(v)
        if "liefertermin" not in v:         # Zuordnung von vor der Lieferzeit: Spalte L-Termin nachtragen
            i = spalten_vorschlag(kopf).get("liefertermin")
            if i is not None and i not in v.values():
                v["liefertermin"] = i
        return v, True
    return spalten_vorschlag(kopf), False


def fehlende(zuordnung):
    return [f for f in PFLICHT if f not in zuordnung]


zahl = csv_import.zahl          # 1.234,56 / 1,234.56 / „3,45 €“ (gemeinsame Importbasis)
datum = csv_import.datum        # TT.MM.JJJJ, ISO, Excel-Tageszahl


def schluessel(artikelnr, bezeichnung):
    """Kennung eines ERP-Artikels: Artikelnummer, ohne sie die Bezeichnung."""
    a = str(artikelnr or "").strip()
    return a if a else "#" + " ".join(str(bezeichnung or "").split()).lower()


# Mengeneinheiten (Spalte „Mengeneinheit“): Meter ist die Vorgabe
_ME_METER = ("m", "lfm", "lfdm", "meter", "mtr", "lm", "lfdmeter")
_ME_MM = ("mm", "millimeter")
_ME_STANGE = ("st", "stk", "stck", "stück", "stueck", "stange", "stangen", "stg", "pcs", "pc", "ea")
_ME_KG = ("kg", "kilogramm", "kilo")
_ME_T = ("t", "to", "tonne", "tonnen")
_EURO = ("", "eur", "euro", "€")


def kaeufe(daten, zuordnung, k=None, fehlerliste=None):
    """Käufe aus lesen() mit der Spaltenzuordnung: (Liste dict(zeile, datum, menge, preis, artikelnr, bezeichnung,
    schluessel, liefertermin, lieferant, bestellnr, waehrung), Meldungen). Zeilen mit Fehler (Datum, Menge, Preis
    nicht lesbar, Menge/Preis ≤ 0, z. B. Gutschrift, fremde Währung, Mengeneinheit nicht umrechenbar) werden
    übersprungen und gemeldet; leere Zeilen und Summenzeilen ohne Datum still. fehlerliste (Liste) bekommt je
    Fehlerzeile (Dateizeile, Grund, Zellen) für den Fehlerbericht.

    Mengeneinheit: Meter (Vorgabe), mm, Stück/Stangen (× Stangenlänge, ohne Spalte 6.000 mm), kg und t (über kg/m
    des erkannten Profils und Werkstoffs; dafür braucht es den Stammdaten-Kontext k). Der Preis gilt je
    Mengeneinheit (bzw. je PE) und wird mit umgerechnet, gespeichert wird immer Meter und €/m. Weitere Spalten
    (Abmessung, Werkstoff, Oberfläche) ergänzen die Bezeichnung für die Erkennung."""
    out, meldungen = [], []
    dez = daten.get("dezimal")
    fehlerliste = fehlerliste if fehlerliste is not None else []
    for n, z in enumerate(daten["zeilen"], daten.get("erste", 2)):
        def zelle(feld):
            i = zuordnung.get(feld)
            return z[i].strip() if i is not None and i < len(z) else ""

        def fehler_(texte):
            meldungen.append(f"Zeile {n}: " + ", ".join(texte) + " – übersprungen")
            fehlerliste.append((n, ", ".join(texte), list(z)))
        bez, d_text = zelle("bezeichnung"), zelle("datum")
        if not bez and not d_text:
            continue
        if not d_text and re.match(r"(?i)\s*(summe|gesamt|total)", " ".join(z)):
            continue
        d, m, p = datum(d_text), zahl(zelle("menge"), dez), zahl(zelle("preis"), dez)
        fehler = [f"{FELD_TITEL[f]} „{t}“ nicht lesbar" for f, w, t in
                  (("datum", d, d_text), ("menge", m, zelle("menge")), ("preis", p, zelle("preis"))) if w is None]
        if not bez:
            fehler.append("EK-Artikel leer")
        if not fehler and (m <= 0 or p <= 0):
            fehler.append("Menge oder Preis nicht größer 0 (Gutschrift/Storno?)")
        whrg = zelle("waehrung")
        if not fehler and whrg.lower().strip(". ") not in _EURO:
            fehler.append(f"Währung {whrg}: nur Euro wird übernommen (Preis bitte im ERP in Euro exportieren)")
        if fehler:
            fehler_(fehler)
            continue
        pe = zahl(zelle("pe"), dez) if zelle("pe") else None
        if pe and pe > 0 and pe != 1:
            p = p / pe          # Preis je PE (z. B. je 100 m)
        art = zelle("artikelnr")
        zus = _zusatz(zelle("zusatz"))
        extra = [x for x in (zelle("abmessung"), zelle("werkstoff"), zelle("oberflaeche"))
                 if x and x.lower() not in bez.lower()]
        text = " ".join((bez + (" " + " ".join(extra) if extra else "")).split())
        me = re.sub(r"[^a-zäöüß]", "", zelle("einheit").lower())
        hinweis = ""
        if me in _ME_MM:
            # Menge in mm: der Preis gilt je ME (mm). Ergäbe das über 1.000 €/m, ist er schon je Meter angegeben
            # (übliche ERP-Ausgabe „Menge mm, Preis €/m“) – dann bleibt er so, mit Hinweis
            if p * 1000 > 1000:
                m, hinweis = m / 1000, hinweis + " (Preis als €/m gelesen, je mm wäre er unplausibel)"
            else:
                m, p = m / 1000, p * 1000
        elif me in _ME_STANGE:
            lg = zahl(zelle("laenge"), dez)
            lg = lg * 1000 if lg and lg <= 30 else lg
            if not lg or not 500 <= lg <= 30000:
                lg, hinweis = 6000.0, " (Stangenlänge 6 m angenommen)"
            m, p = m * lg / 1000, p / (lg / 1000)
        elif me in _ME_KG or me in _ME_T:
            kgm = _kg_je_m_text(text + artikelnr_hinweis(art), k)
            if not kgm:
                fehler_([f"Menge in {zelle('einheit')}: Profil/Werkstoff nicht erkannt, nicht in Meter umrechenbar"])
                continue
            f = 1000.0 if me in _ME_T else 1.0
            m, p = m * f / kgm, p / f * kgm
        elif me and me not in _ME_METER:
            fehler_([f"Mengeneinheit „{zelle('einheit')}“ unbekannt (m, mm, Stück/Stange, kg, t)"])
            continue
        out.append(dict(zeile=n, datum=d, menge=m if not me or me in _ME_METER else round(m, 6),
                        preis=p if not me or me in _ME_METER else round(p, 6), artikelnr=art,
                        liefertermin=datum(zelle("liefertermin")),
                        bezeichnung=text + (f" · {zus}" if zus else ""), schluessel=schluessel(art, bez),
                        lieferant=zelle("lieferant"), bestellnr=zelle("bestellnr"), hinweis=hinweis.strip(" ()"),
                        roh=list(z)))
    return out, meldungen


def _kg_je_m_text(text, k):
    """kg/m für eine Bezeichnung (Profil und Werkstoff erkannt) oder None."""
    if k is None:
        return None
    from .rechnen import kg_je_m
    e = zerlegen(text, k)
    if not e["werkstoff_id"]:
        return None
    if e["profil_id"]:
        return kg_je_m(e["profil_id"], e["werkstoff_id"], k)
    v = e.get("vorschlag")
    if v:
        from .stammdaten import flaeche_berechnet
        fl = flaeche_berechnet(v)
        return fl * float(k.werkstoffe[e["werkstoff_id"]].get("dichte") or 7.85) / 1000 if fl else None
    return None


def _zusatz(t):
    """Zusatztext kurz: Sternchen-/Strichzeilen und Ausrufezeichen weg, höchstens 80 Zeichen."""
    t = re.sub(r"[*=_~!]{2,}|-{3,}", " ", str(t or ""))
    t = " ".join(t.split())
    return t[:80].rstrip() if len(t) <= 80 else t[:80].rsplit(" ", 1)[0]


# ERP-Artikelnummern wie EQRS355-50x50x3gs, ERRS235-80x60x6, ERS235D172x23N (Patrick 20.11.2026): Form, Güte und
# Oberfläche als Hinweis für die Erkennung, wenn die Bezeichnung sie nicht nennt („30x30x3 S355“)
_ARTNR = re.compile(r"(?i)^E(QR|RR|R)(S\d{3})(?:-|D)?[\d,x.]*([a-z]{2})?([A-Za-z]*)$")
_ARTNR_FORM = {"QR": "Quadratrohr", "RR": "Rechteckrohr", "R": "Rundrohr"}
_ARTNR_OBER = {"gs": "gestrahlt", "vz": "verzinkt", "bk": "blank"}


def artikelnr_hinweis(artikelnr):
    """' Quadratrohr S355 gestrahlt' aus der ERP-Artikelnummer oder ''."""
    m = _ARTNR.match(str(artikelnr or "").strip())
    if not m:
        return ""
    rest = (m.group(3) or "") + (m.group(4) or "")
    ober = next((w for k, w in _ARTNR_OBER.items() if k in rest.lower()), "")
    # Endung N / NBK = nahtlos, SNB/SNS (Schweißnaht Breit-/Schmalseite) und gn (geschabte Naht) = geschweißt
    naht = "geschweißt" if re.search(r"SN[BS]|gn", rest) else "nahtlos" if re.search(r"N(?![a-z])|N(?=BK)", rest) \
        else ""
    teile = [_ARTNR_FORM[m.group(1).upper()], m.group(2).upper(), ober, naht]
    return " " + " ".join(t for t in teile if t)


# ------------------------------------------------------------------ 2. Bezeichnung zerlegen
_Z = r"\d+(?:[.,]\d+)?"
_MASSE = re.compile(rf"(?<![\d.,])({_Z})\s*(?:mm)?\s*[x×*X]\s*({_Z})(?:\s*(?:mm)?\s*[x×*X]\s*({_Z}))?(?![\d])")
_FORM = (("Rundrohr", r"rund|ø|⌀|\brr\b|\bro\b|siederohr|präzisionsrohr|praezisionsrohr|gewinderohr|\bd\s*=?\s*\d"),
         ("Quadratrohr", r"quadrat|vierkantrohr|vierkant-rohr|\bqr\b|\bvk\b|\bqhp\b|\bmshq\b"),
         ("Rechteckrohr", r"rechteck|\bre\b|\brk\b|\brhp\b|\bmshr\b"),
         ("Flachstahl", r"flach|\bfl\b"),
         ("L-Profil", r"winkel|l-profil|\bl\s*\d"),
         ("U-Profil", r"u-profil|\bu\s*\d"))
_OBER_WORT = re.compile(r"(?i)(?<![\w])(feuerverzinkt|sendzimirverzinkt|galvanisch verzinkt|verzinkt|fvz|gebeizt|"
                        r"geschliffen|gestrahlt|kugelgestrahlt|lackiert|pulverbeschichtet|grundiert|eloxiert|"
                        r"E6/EV1|K\d{3}|geölt|poliert)(?![\w])")
_NORM = re.compile(r"(?<!\d)(102\d\d|103\d\d|10305|10296|10217)(?!\d)")       # EN 10219, 10210, 10305 …
# Ohne EN 10219/10210 im Text (Patricks ERP-Export 20.11.2026, 85 von 417 Artikeln „S235 mehrdeutig“): geschweißte
# Rohrnormen und „geschweißt“ gehören zu den kaltgefertigten (EN 10219), nahtlose zu den warmgefertigten (EN 10210)
_GESCHWEISST = re.compile(r"(?i)(?<!\d)(10217|10255|10296|2458|1615|2440|2394)(?!\d)|geschwei(ß|ss)t|\bSNB\b|\bSNS\b|"
                          r"schwei(ß|ss)naht")
_NAHTLOS = re.compile(r"(?i)(?<!\d)(10216|10297|2448|1629)(?!\d)|nahtlos")
_E_GUETE = re.compile(r"(?i)(?<![\w.])E(235|355|195)(\s*\+\s*C)?\b")     # Präzisionsrohr-Güte E235(+C)


def _sondergüte(wid, z, t):
    """Steht eine besondere Güte (nicht S235/S355 allein) dieses Werkstoffs wörtlich im Text?"""
    namen = {str(z.get("werkstoff") or ""), str(wid or "").split("-")[0]}
    for n in namen:
        if len(n) >= 4 and not re.fullmatch(r"(?i)S(235|355)(JRH?|J2H?|JR)?", n) and \
                re.search(rf"(?i)(?<![\w.]){re.escape(n)}(?![\w])", t):
            return not n.upper().startswith("E") or bool(_E_GUETE.search(t))
    return False


def _familie(t):
    """{'10219'} (geschweißt), {'10210'} (nahtlos) oder leer; beides im Text = offen."""
    g, n = bool(_GESCHWEISST.search(t)), bool(_NAHTLOS.search(t))
    return {"10219"} if g and not n else {"10210"} if n and not g else set()



def _f(x):
    return float(str(x).replace(",", "."))


# „RR 50/50/3“, „QR 40/40/3“: Maße mit Schrägstrich, nur mit drei Zahlen (zwei Zahlen „S235/S275“, „1/2 Zoll“
# sind keine Abmessung)
_MASSE_SCHRAEG = re.compile(rf"(?<![\d.,/])({_Z})\s*/\s*({_Z})\s*/\s*({_Z})(?![\d/])")
# Kürzel, die je nach ERP Rund- oder Rechteckrohr heißen („RR“): bei drei Maßen entscheidet die Zahl der Maße
_FORM_KURZ = re.compile(r"\brr\b|\bro\b")


def masse(text):
    """Profilform und Maße aus der Bezeichnung: dict(form, a, b, wand) oder None. Schreibweisen wie „50 x 50 x 3“,
    „50X50X3 mm“, „50×50×3“, „Ø 60 x 3“ und „50/50/3“ ergeben dieselben Maße (Schreibweise wie masstext)."""
    t = str(text or "")
    for z_ in "∅⌀":
        t = t.replace(z_, "Ø")
    # erste Abmessung ohne Längenangabe („16x 4500mm“ im Zusatztext ist Stückzahl × Länge, kein Profil)
    m = next((x for x in _MASSE.finditer(t) if all(_f(g) < 1000 for g in x.groups() if g)), None)
    if not m:
        m = next((x for x in _MASSE_SCHRAEG.finditer(t) if all(_f(g) < 1000 for g in x.groups())), None)
    if not m:
        return None
    z = [_f(x) for x in m.groups() if x]
    klein = t.lower()
    form = next((f for f, muster in _FORM if re.search(muster, klein)), None)
    if form == "Rundrohr" and len(z) == 3 and not re.search(r"rund|ø|siederohr|präzision|praezision|gewinderohr",
                                                            klein) and _FORM_KURZ.search(klein):
        form = None             # „RR 50/50/3“: drei Maße, also kein Rundrohr
    if form is None:
        form = "Rundrohr" if len(z) == 2 else ("Quadratrohr" if z[0] == z[1] else "Rechteckrohr")
    if form in ("Rundrohr", "Flachstahl"):
        a, b, wand = z[0], None, z[1]
    elif form == "Quadratrohr":
        if len(z) == 3 and z[0] != z[1]:
            form, a, b, wand = "Rechteckrohr", z[0], z[1], z[2]
        else:
            a, b, wand = z[0], None, z[-1]
    elif form == "L-Profil":
        a, b, wand = (z[0], z[0], z[1]) if len(z) == 2 else (z[0], z[1], z[2])
    elif len(z) == 3:
        a, b, wand = z
    else:
        return None
    if a <= 0 or wand <= 0:
        return None
    return dict(form=form, a=a, b=b, wand=wand)


def _gleich(x, y, tol=0.051):
    return x is not None and y is not None and abs(float(x) - float(y)) <= tol


_FLACH = {}


def _flache_ids(profile):
    """[(Profil-ID, Vergleichsform ohne Leerzeichen, klein, Punkt statt Komma)] ab 3 Zeichen, einmal je
    Profil-Tabelle (gleiche Profil-IDs) statt je EK-Artikel neu."""
    marke = tuple(profile)
    e = _FLACH.get("p")
    if e is None or e[0] != marke:
        liste = []
        for pid in profile:
            p = re.sub(r"\s+", "", str(pid)).lower().replace(",", ".")
            if len(p) >= 3:
                liste.append((pid, p))
        e = _FLACH["p"] = (marke, liste)
    return e[1]


def profil_finden(text, profile):
    """Profil-ID aus den Stammdaten: zuerst eine Profil-ID, die wörtlich in der Bezeichnung steht (IPE 200, RP
    0106-35, QR 40x40x3), sonst gleiche Form und Maße (±0,05 mm, Rechteckrohr auch gedreht). Ergebnis (Profil-ID
    oder None, erkannte Maße oder None)."""
    flach = re.sub(r"\s+", "", str(text or "")).lower().replace(",", ".")
    beste, beste_n = None, 0
    for pid, p in _flache_ids(profile):
        if p not in flach:          # schneller Vorfilter, gleiches Ergebnis (Supportpaket 24.11.2026)
            continue
        for m in re.finditer(re.escape(p), flach):
            if not re.match(r"[\d.]", flach[m.end():m.end() + 1]) and (m.start() == 0 or not flach[m.start() - 1].isdigit()):
                if beste is None or len(p) > beste_n:
                    beste, beste_n = pid, len(p)
    mas = masse(text)
    if beste is not None:
        return beste, mas
    if mas is None:
        return None, None
    for pid, p in profile.items():
        if p.get("form") != mas["form"] or not _gleich(p.get("wand"), mas["wand"]):
            continue
        if mas["form"] in ("Rundrohr", "Flachstahl", "Quadratrohr"):
            if _gleich(p.get("a"), mas["a"]):
                return pid, mas
        elif (_gleich(p.get("a"), mas["a"]) and _gleich(p.get("b"), mas["b"])) or \
                (mas["form"] == "Rechteckrohr" and _gleich(p.get("a"), mas["b"]) and _gleich(p.get("b"), mas["a"])):
            return pid, mas
    return None, mas


def werkstoff_finden(text, werkstoffe):
    """(Werkstoff-ID oder None, Wort, Kandidaten): Erkennung wie beim Outlook-Import (mail.werkstoff); passen mehrere,
    entscheidet eine Norm-Nummer in der Bezeichnung (EN 10219 / 10210), sonst bleibt es offen."""
    from .mail import werkstoff
    zeilen = [dict(z, werkstoff_id=wid) for wid, z in werkstoffe.items()]
    # Doppelzeugnis „S235/S275“, „E235/E195+CR1“: gekauft und gerechnet wird die erste Güte
    text = re.sub(r"(?i)\b([SEP]\d{3}\w*)\s*/\s*[SEP]\d{3}[\w+]*", r"\1", str(text or ""))
    wid, wort, kand = werkstoff(text, zeilen)
    if _E_GUETE.search(str(text or "")) and "10305" not in str(wid or ""):
        g = _E_GUETE.search(str(text or ""))
        e = [w for w in werkstoffe if "10305" in str(w) and str(werkstoffe[w].get("werkstoff") or "").upper()
             .startswith("E" + g.group(1))]
        if len(e) == 1:         # E235(+C) = Präzisionsrohr EN 10305, auch wenn die Artikelnummer „S235“ sagt
            return e[0], wort, kand
    if wid is None and len(kand) > 1:
        t = str(text or "")
        sonder = [w for w in kand if _sondergüte(w, werkstoffe.get(w, {}), t)]
        if len(sonder) == 1:    # P235GH, P235TR1, E235 im Text gehen vor dem „S235“ aus der Artikelnummer
            return sonder[0], wort, kand
        normen = set(_NORM.findall(t))
        if not normen:          # „kaltgefertigt“ = EN 10219, „warmgefertigt“ = EN 10210 (ERP-Export 20.11.2026)
            normen = {"10219"} if re.search(r"(?i)kalt\s*gefertigt", t) else \
                {"10210"} if re.search(r"(?i)warm\s*gefertigt|\bwarm\b", t) else set()
        if not any(n in ("10219", "10210") for n in normen):
            normen |= _familie(t)
        if normen:
            passt = [w for w in kand if any(n in " ".join(str(werkstoffe.get(w, {}).get(f) or "") for f in
                                                          ("norm", "angebotstext", "werkstoff_id")) for n in normen)]
            if len(passt) > 1:  # Sondergüten (wetterfest S355J2WH) nur, wenn sie in der Bezeichnung stehen
                eng = [w for w in passt if any(n in str(w) for n in normen)]
                passt = eng or passt
            if len(passt) == 1:
                return passt[0], wort, kand
    if wid is None and "10305" in _NORM.findall(str(text or "")):
        g = re.search(r"(?i)\b[ES](235|355)", str(text or ""))
        e = [w for w in werkstoffe if "10305" in str(w) and str(werkstoffe[w].get("werkstoff") or "").startswith(
            "E" + (g.group(1) if g else ""))]
        if len(e) == 1:         # Präzisionsrohr EN 10305 ist E235/E355, auch wenn das ERP „S235“ schreibt
            return e[0], wort, kand
    return wid, wort, kand


def oberflaeche_finden(text, oberflaechen, werkstoff=None):
    """(Oberfläche, unbekannt): Name aus den Stammdaten (längster, der in der Bezeichnung steht), roh/blank/schwarz
    = '' (roh); ein Oberflächenwort ohne Stammdatenzeile (z. B. verzinkt) kommt mit unbekannt=True zurück. Steht das
    Wort im Werkstoff selbst (DX51D+Z275 sendzimirverzinkt), ist es keine Oberfläche."""
    klein = str(text or "").lower()
    namen = sorted((n for n in oberflaechen if n and n.lower() != "roh"), key=len, reverse=True)
    for n in namen:
        if re.search(r"(?<![a-z0-9])" + re.escape(n.lower()) + r"(?![a-z0-9])", klein) or \
                (len(n) >= 6 and n.lower() in klein):
            return n, False
    m = _OBER_WORT.search(text or "")
    if m:
        w = (werkstoff or {})
        im_werkstoff = " ".join(str(w.get(f) or "") for f in ("werkstoff", "norm", "angebotstext")).lower()
        if m.group(1).lower() not in im_werkstoff:
            return m.group(1), True
    return "", False


def _merker(k):
    """Merker der Erkennung je Stammdaten-Kontext (Supportpaket 24.11.2026: jeder Klick „Optimieren“, „Material …“,
    der ERP-Import und der STEP-Import erkannten alle EK-Artikel neu, bei Patrick 9 s je Klick und 67 s + 157 s beim
    Import). Der Kontext wird neu gebaut, sobald sich Stammdaten ändern (Datenbank.kontext); zusätzlich zählen die
    Tabellen selbst und die eigenen Werkstoffnamen, damit ein von Hand geänderter Kontext nie Altes liefert.
    Ergebnis: dict {Text: Ergebnis} oder None (Kontext ohne Merker, z. B. in Tests)."""
    from . import werkstoff_namen
    marke = tuple((id(d), len(d)) for d in (k.profile, k.werkstoffe, k.oberflaechen)) + \
        (tuple(werkstoff_namen.eigene_namen()),)
    m = getattr(k, "_erp_erkennung", None)
    if m is None or m[0] != marke:
        m = (marke, {})
        try:
            k._erp_erkennung = m
        except AttributeError:
            return None
    return m[1]


def zerlegen(text, k):
    """Bezeichnung -> dict(profil_id, vorschlag (neues Profil: form, a, b, wand, profil_id), werkstoff_id,
    kandidaten, werkstoff_wort, oberflaeche, ober_unbekannt, ampel, hinweis). Gleiche Bezeichnung mit denselben
    Stammdaten: aus dem Merker (_merker), jede Ausgabe ist eine eigene Kopie."""
    m = _merker(k)
    if m is None:
        return _zerlegen(text, k)
    e = m.get(text)
    if e is None:
        e = m[text] = _zerlegen(text, k)
    return dict(e, kandidaten=list(e["kandidaten"]), vorschlag=dict(e["vorschlag"]) if e["vorschlag"] else None)


def _zerlegen(text, k):
    pid, mas = profil_finden(text, k.profile)
    wid, wort, kand = werkstoff_finden(text, k.werkstoffe)
    ober, unbekannt = oberflaeche_finden(text, k.oberflaechen, k.werkstoffe.get(wid))
    vorschlag = None
    if pid is None and mas is not None:
        from .profil_neu import profil_id
        vorschlag = dict(mas, profil_id=profil_id(mas["form"], mas["a"], mas["b"], mas["wand"]))
    hinweis = []
    if pid is None:
        hinweis.append(f"Profil {vorschlag['profil_id']} fehlt in den Stammdaten" if vorschlag else
                       "Abmessung nicht erkannt")
    if wid is None:
        hinweis.append(f"Werkstoff „{wort}“ mehrdeutig: {', '.join(kand)}" if len(kand) > 1 else
                       "Werkstoff nicht erkannt")
    if unbekannt:
        hinweis.append(f"Oberfläche „{ober}“ fehlt in den Stammdaten")
    ampel = ROT if pid is None else (GELB if wid is None or unbekannt else GRUEN)
    return dict(profil_id=pid, vorschlag=vorschlag, werkstoff_id=wid, kandidaten=kand, werkstoff_wort=wort,
                oberflaeche=ober, ober_unbekannt=unbekannt, ampel=ampel, hinweis="; ".join(hinweis))


# ------------------------------------------------------------------ Speicher (nur diese Datendatei, 6a)
TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS erp_kaeufe (id INTEGER PRIMARY KEY, datum TEXT, schluessel TEXT, artikelnr TEXT, "
    "bezeichnung TEXT, menge REAL, preis REAL, datei TEXT, importiert TEXT, rechnen INTEGER, "
    "UNIQUE (datum, schluessel, menge, preis))",
    "CREATE TABLE IF NOT EXISTS erp_zuordnung (schluessel TEXT PRIMARY KEY, artikelnr TEXT, bezeichnung TEXT, "
    "profil_id TEXT, werkstoff_id TEXT, oberflaeche TEXT, ignorieren INTEGER, geaendert TEXT)",
)


def einrichten(con):
    for sql in TABELLEN_SQL:
        con.execute(sql)
    sp = set(db_verbindung.spalten(con, "erp_kaeufe"))
    if "liefertermin" not in sp:
        con.execute("ALTER TABLE erp_kaeufe ADD COLUMN liefertermin TEXT")  # L-Termin des Kaufs (Lieferzeit)
    # Master-Auftrag EK-Import 25.11.2026: Lieferant und Lieferantenartikelnummer je Kauf, Lauf (Rückgängig)
    for name, art in (("lieferant", "TEXT"), ("bestellnr", "TEXT"), ("import_id", "INTEGER")):
        if name not in sp:
            con.execute(f"ALTER TABLE erp_kaeufe ADD COLUMN {name} {art}")
    con.execute("CREATE INDEX IF NOT EXISTS erp_kaeufe_lauf ON erp_kaeufe (import_id)")
    if "erp_preise" not in set(db_verbindung.spalten(con, "angebote")):
        con.execute("ALTER TABLE angebote ADD COLUMN erp_preise TEXT")      # gewählte ERP-Preise je Angebot (JSON)


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def speichern(db, liste, datei="", import_id=None):
    """Käufe in erp_kaeufe in einer Transaktion (alles oder nichts); gleiche Käufe (Datum, Artikel, Menge, Preis) nur
    einmal. import_id = Importlauf (csv_import.Lauf, Rückgängig). Ergebnis: Anzahl neu."""
    _KAEUFE_STAND[0] += 1
    zaehlen = "SELECT COUNT(*) FROM erp_kaeufe"
    vorher = db.con.execute(zaehlen).fetchone()[0]
    with db.con:
        db.con.executemany(
            "INSERT OR IGNORE INTO erp_kaeufe (datum, schluessel, artikelnr, bezeichnung, menge, preis, datei, "
            "importiert, lieferant, bestellnr, import_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(k["datum"].isoformat(), k["schluessel"], k["artikelnr"], k["bezeichnung"], k["menge"], k["preis"],
              datei, _jetzt(), k.get("lieferant") or None, k.get("bestellnr") or None, import_id) for k in liste])
        # schon gespeicherte Käufe bekommen den Liefertermin beim erneuten Einlesen nach (Menge/Preis wie gespeichert)
        db.con.executemany(
            "UPDATE erp_kaeufe SET liefertermin = ? WHERE datum = ? AND schluessel = ? AND menge = ? AND preis = ? "
            "AND (liefertermin IS NULL OR liefertermin <> ?)",
            [(k["liefertermin"].isoformat(), k["datum"].isoformat(), k["schluessel"], k["menge"], k["preis"],
              k["liefertermin"].isoformat()) for k in liste if k.get("liefertermin")])
    return db.con.execute(zaehlen).fetchone()[0] - vorher


_KAEUFE = {}            # gespeicherte(): {id(db): (Stand, Käufe)}; Stand = Anzahl, größte ID, eigene Änderungen
_KAEUFE_STAND = [0]     # zählt speichern() und kauf_rechnen() in diesem Programmlauf


def gespeicherte(db):
    """Alle gespeicherten Käufe (dict mit datum als date), älteste zuerst. Gemerkt, solange Anzahl, größte ID und
    die eigenen Änderungen (speichern, kauf_rechnen) gleich sind (Supportpaket 24.11.2026: die Seite Material las
    die 30.000 Käufe bei jedem Aufbau fünfmal); jede Ausgabe ist eine eigene Kopie."""
    try:
        n, groesste = db.con.execute("SELECT COUNT(*), MAX(id) FROM erp_kaeufe").fetchone()
    except Exception:           # noqa: BLE001  (Datei ohne Tabelle: wie bisher den Fehler beim Lesen zeigen)
        return _gespeicherte_lesen(db)
    stand = (n, groesste, _KAEUFE_STAND[0], getattr(db, "pfad", None))
    e = _KAEUFE.get(id(db))
    if e is None or e[0] != stand or e[2] is not db:
        e = (stand, _gespeicherte_lesen(db), db)
        _KAEUFE.clear()
        _KAEUFE[id(db)] = e
    return [dict(z) for z in e[1]]


def _gespeicherte_lesen(db):
    out = []
    for r in db.con.execute("SELECT * FROM erp_kaeufe ORDER BY datum, id"):
        z = dict(r)
        z["datum"] = datetime.date.fromisoformat(z["datum"])
        try:
            z["liefertermin"] = datetime.date.fromisoformat(z["liefertermin"]) if z.get("liefertermin") else None
        except ValueError:
            z["liefertermin"] = None
        out.append(z)
    return out


def kauf_rechnen(db, kauf_id, rechnen):
    """Ausreißer von Hand: rechnen True = immer mitrechnen, False = nie, None = automatisch (3a)."""
    _KAEUFE_STAND[0] += 1
    with db.con:
        db.con.execute("UPDATE erp_kaeufe SET rechnen=? WHERE id=?",
                       (None if rechnen is None else int(bool(rechnen)), kauf_id))


def zuordnungen(db):
    return {r["schluessel"]: dict(r) for r in db.con.execute("SELECT * FROM erp_zuordnung")}


def zuordnung_merken(db, schl, artikelnr, bezeichnung, profil_id=None, werkstoff_id=None, oberflaeche="",
                     ignorieren=False):
    with db.con:
        db.con.execute("INSERT INTO erp_zuordnung (schluessel, artikelnr, bezeichnung, profil_id, "
                       "werkstoff_id, oberflaeche, ignorieren, geaendert) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                       "ON CONFLICT (schluessel) DO UPDATE SET artikelnr=excluded.artikelnr, "
                       "bezeichnung=excluded.bezeichnung, profil_id=excluded.profil_id, "
                       "werkstoff_id=excluded.werkstoff_id, oberflaeche=excluded.oberflaeche, "
                       "ignorieren=excluded.ignorieren, geaendert=excluded.geaendert",
                       (schl, artikelnr, bezeichnung, profil_id, werkstoff_id, oberflaeche or "", int(ignorieren),
                        _jetzt()))


def zuordnung_vergessen(db, schluessel_liste):
    with db.con:
        db.con.executemany("DELETE FROM erp_zuordnung WHERE schluessel=?", [(s,) for s in schluessel_liste])


def nummern_von(db):
    """Artikel-/Bestellnummern vorhandener Materialien (material_stamm.nummern); ohne Materialstamm leer."""
    try:
        from . import material_stamm
        return material_stamm.nummern(db)
    except Exception:           # noqa: BLE001  (Datei ohne Materialstamm)
        from . import protokoll
        protokoll.warnung("ERP-Preise: Nummern des Materialstamms nicht lesbar")
        return {}


def artikel(kauf_liste, gemerkt, k, nummern=None):
    """Je ERP-Artikel (Schlüssel) eine Zeile der Prüfliste: dict(schluessel, artikelnr, bezeichnung, kaeufe, meter,
    profil_id, werkstoff_id, oberflaeche, ampel, hinweis, gemerkt, ignorieren, vorschlag, kandidaten). Gemerkte
    Zuordnungen gelten vor der Erkennung, solange Profil und Werkstoff noch in den Stammdaten stehen. Danach erkennt
    die Artikelnummer ein vorhandenes Material (nummern = material_stamm.nummern: Materialnummer im Materialstamm,
    Bestellnummer beim Lieferanten), erst dann die Bezeichnung (Patrick 23.11.2026)."""
    je = {}
    for kauf in kauf_liste:
        a = je.setdefault(kauf["schluessel"], dict(schluessel=kauf["schluessel"], artikelnr=kauf["artikelnr"],
                                                   bezeichnung=kauf["bezeichnung"], kaeufe=0, meter=0.0))
        a["kaeufe"] += 1
        a["meter"] += kauf["menge"]
        a["bezeichnung"] = kauf["bezeichnung"]          # neueste Schreibweise
    for a in je.values():
        z = gemerkt.get(a["schluessel"])
        if z and z.get("ignorieren"):
            a.update(profil_id=None, werkstoff_id=None, oberflaeche="", ampel=GRUEN, hinweis="übersprungen (gemerkt)",
                     gemerkt=True, ignorieren=True, vorschlag=None, kandidaten=[])
        elif z and z.get("profil_id") in k.profile and z.get("werkstoff_id") in k.werkstoffe:
            a.update(profil_id=z["profil_id"], werkstoff_id=z["werkstoff_id"], oberflaeche=z.get("oberflaeche") or "",
                     ampel=GRUEN, hinweis="gemerkt", gemerkt=True, ignorieren=False, vorschlag=None, kandidaten=[])
        elif nummern and a["artikelnr"] and nummern.get(str(a["artikelnr"]).strip()):
            n = nummern[str(a["artikelnr"]).strip()]
            a.update(profil_id=n["profil_id"], werkstoff_id=n["werkstoff_id"], oberflaeche=n.get("oberflaeche") or "",
                     ampel=GRUEN, hinweis=f"erkannt über {n['quelle']}", gemerkt=False, ignorieren=False,
                     vorschlag=None, kandidaten=[])
        else:
            e = zerlegen(a["bezeichnung"] + artikelnr_hinweis(a["artikelnr"]), k)
            a.update(profil_id=e["profil_id"], werkstoff_id=e["werkstoff_id"], oberflaeche=e["oberflaeche"],
                     ampel=e["ampel"], hinweis=e["hinweis"], gemerkt=False, ignorieren=False,
                     vorschlag=e["vorschlag"], kandidaten=e["kandidaten"])
    _stufen(je.values(), gemerkt, k)
    return sorted(je.values(), key=lambda a: ({ROT: 0, GELB: 1, GRUEN: 2}[a["ampel"]], a["bezeichnung"].lower()))


# ------------------------------------------------------------------ Zuordnungsstufen (Master-Auftrag 25.11.2026)
EXAKT, WAHRSCHEINLICH, KEIN_TREFFER = "exakter Treffer", "wahrscheinlicher Treffer", "kein Treffer"
STUFEN = (EXAKT, WAHRSCHEINLICH, KEIN_TREFFER)
_GUETE_WORT = re.compile(r"(?i)(?<![\w.])(?:[SEP]\d{3}[A-Z0-9+]*|1\.4\d{3}|AW-?\d{4}[A-Z0-9-]*|EN\s?10\d{3}(?:-\d)?)"
                         r"(?![\w])")


def merkmal(text):
    """Vergleichsform einer EK-Bezeichnung für das Wiedererkennen: Profilform und Maße (Schreibweise egal,
    Rechteckrohr gedreht gleich), Güten/Normen (S355J2H, 1.4301, EN10219) und Oberfläche – „Rohr 40 x 40 x 3
    S235JRH“ und „QR 40x40x3 S235JRH“ sind gleich, „… S355J2H“ oder „… S355MC“ nicht. None ohne Maße."""
    t = str(text or "")
    mas = masse(t)
    if mas is None:
        return None
    a, b = mas["a"], mas["b"]
    if mas["form"] == "Rechteckrohr" and b and b > a:
        a, b = b, a
    guete = sorted({re.sub(r"[\s-]", "", g).upper() for g in _GUETE_WORT.findall(t)})
    o = _OBER_WORT.search(t)
    return "|".join([mas["form"], f"{a:g}", f"{b:g}" if b else "", f"{mas['wand']:g}", ",".join(guete),
                     o.group(1).lower() if o else ""])


def _stufen(liste, gemerkt, k):
    """Je ERP-Artikel die Zuordnungsstufe (stufe, stufe_grund) und, wo nötig, ein Vorschlag zum Bestätigen
    (vorschlag_zuordnung = dict(profil_id, werkstoff_id, oberflaeche, quelle)):
    1. exakter Treffer: gemerkt, über die Artikelnummer gefunden oder Abmessung, Werkstoff und Oberfläche eindeutig
       erkannt – wird automatisch zugeordnet (wie bisher grün).
    2. wahrscheinlicher Treffer: das Profil gibt es, der Werkstoff ist nicht eindeutig, aber es gibt genau einen
       begründeten Vorschlag (gleiche Bezeichnung wie ein schon bestätigter Artikel; Hohlprofil ohne Normangabe ->
       EN 10219; nur Norm genannt, z. B. EN 10255 -> der eine Werkstoff dieser Norm). Nie automatisch: der Anwender
       bestätigt im Assistenten (Patrick: Werkstoff nie raten).
    3. kein Treffer: Profil oder Werkstoff fehlt in den Stammdaten -> neues Material zur Anlage vorschlagen."""
    sig = {}
    for z in gemerkt.values():
        if z.get("ignorieren") or z.get("profil_id") not in k.profile or z.get("werkstoff_id") not in k.werkstoffe:
            continue
        m = merkmal(z.get("bezeichnung"))
        if m:
            sig.setdefault(m, {})[(z["profil_id"], z["werkstoff_id"], z.get("oberflaeche") or "")] = z
    for a in liste:
        a["vorschlag_zuordnung"] = None
        if a.get("ignorieren"):
            a.update(stufe=EXAKT, stufe_grund="übersprungen (gemerkt)")
            continue
        if a["ampel"] == GRUEN:
            a.update(stufe=EXAKT, stufe_grund=a.get("hinweis") or "Abmessung, Werkstoff und Oberfläche eindeutig")
            continue
        text = a["bezeichnung"] + artikelnr_hinweis(a["artikelnr"])
        treffer = sig.get(merkmal(text)) or {}
        if len(treffer) == 1:
            (pid, wid, ober), z = next(iter(treffer.items()))
            a["vorschlag_zuordnung"] = dict(profil_id=pid, werkstoff_id=wid, oberflaeche=ober,
                                            quelle=f"gleiche Bezeichnung wie bestätigter Artikel "
                                                   f"{z.get('artikelnr') or z.get('bezeichnung')}")
        elif a.get("profil_id") and not a.get("werkstoff_id"):
            wv, grund = _werkstoff_vorschlag(text, a, k)
            if wv:
                a["vorschlag_zuordnung"] = dict(profil_id=a["profil_id"], werkstoff_id=wv,
                                                oberflaeche=a.get("oberflaeche") or "", quelle=grund)
        v = a["vorschlag_zuordnung"]
        if v and v["profil_id"] in k.profile and not (a.get("ober_unbekannt") and not v.get("oberflaeche")):
            a.update(stufe=WAHRSCHEINLICH, stufe_grund=f"Vorschlag {v['profil_id']} · {v['werkstoff_id']}"
                     + (f" · {v['oberflaeche']}" if v.get("oberflaeche") else "") + f" ({v['quelle']}) – bitte "
                     "bestätigen")
        else:
            neu = []
            if not a.get("profil_id"):
                neu.append(f"Profil {a['vorschlag']['profil_id']}" if a.get("vorschlag") else "Abmessung unklar")
            if not a.get("werkstoff_id"):
                neu.append("Werkstoff " + (f"(einer von {', '.join(a['kandidaten'][:4])})" if a.get("kandidaten")
                                           else "neu/unbekannt"))
            a.update(stufe=KEIN_TREFFER, stufe_grund=("neu anlegen: " + ", ".join(neu)) if neu else
                     (a.get("hinweis") or "bitte zuordnen"))


def _werkstoff_vorschlag(text, a, k):
    """(Werkstoff-ID, Begründung) oder (None, ''): ein begründeter Vorschlag für einen mehrdeutigen oder fehlenden
    Werkstoff – nie eine Zuordnung ohne Bestätigung."""
    from . import erp_anlegen
    form = (k.profile.get(a.get("profil_id")) or {}).get("form")
    kand = [w for w in (a.get("kandidaten") or []) if w in k.werkstoffe]
    if form in erp_anlegen.HOHLPROFILE:
        wid, _neu, _g = erp_anlegen.werkstoff_fuer(text, k)
        if wid in k.werkstoffe:
            return wid, "Güte und Norm-Familie aus der Bezeichnung"
        kalt = [w for w in kand if "10219" in " ".join(str(k.werkstoffe[w].get(f) or "") for f in
                                                          ("norm", "werkstoff_id")) + str(w)]
        if len(kand) > 1 and len(kalt) == 1:
            return kalt[0], "Hohlprofil ohne Normangabe: meist EN 10219 kaltgefertigt"
    normen = set(re.findall(r"(?<!\d)(10\d{3})(?!\d)", text))
    if not kand and len(normen) == 1:
        n = normen.pop()
        mit = [w for w, z in k.werkstoffe.items() if n in str(w) + " " + str(z.get("norm") or "")
               and z.get("archiviert") != "ja"]
        if len(mit) == 1:
            return mit[0], f"einziger Werkstoff der Norm EN {n}"
    return None, ""


def bestaetigen(db, a, profil_id=None, werkstoff_id=None, oberflaeche=None, lauf=None):
    """Zuordnung eines ERP-Artikels bestätigen und merken (Vorschlag oder eigene Wahl). Mit lauf wird der alte
    Stand gemerkt (Rückgängig des Imports)."""
    v = a.get("vorschlag_zuordnung") or {}
    pid = profil_id or v.get("profil_id") or a.get("profil_id")
    wid = werkstoff_id or v.get("werkstoff_id") or a.get("werkstoff_id")
    ober = oberflaeche if oberflaeche is not None else (v.get("oberflaeche") if v else a.get("oberflaeche")) or ""
    if lauf is not None:
        alt = db.con.execute("SELECT * FROM erp_zuordnung WHERE schluessel=?", (a["schluessel"],)).fetchone()
        lauf.merken("erp_zuordnung", None, "zuordnung", alt=dict(alt) if alt else None,
                    neu=dict(schluessel=a["schluessel"]))
    zuordnung_merken(db, a["schluessel"], a["artikelnr"], a["bezeichnung"], pid, wid, ober)
    return pid, wid, ober


# ------------------------------------------------------------------ 3. Preis ermitteln
def heute_preis_m(profil_id, werkstoff_id, k, tabellen):
    """Heutiger Materialpreis €/m aus den Stammdaten (Preise, sonst Tonnenpreis) ohne Oberfläche und Teuerung:
    (Preis oder None, Herkunft-Text)."""
    from .rechnen import kg_je_m, preis_zeile
    kgm = kg_je_m(profil_id, werkstoff_id, k)
    z = preis_zeile(profil_id, werkstoff_id, k, tabellen)
    if z is not None and z.get("preis"):
        b, p = z.get("basis"), z["preis"]
        wert = p if b == "€/m" else (p * kgm if b == "€/kg" and kgm else
                                     (p * 1000 / z["lieferlaenge"] if b == "€/Stange" and z.get("lieferlaenge")
                                      else None))
        return wert, f"Preise {_t(p)} {b}" + (f", {z['lieferant']}" if z.get("lieferant") else "") + \
            (f", ab {_datum_text(z.get('gueltig_ab'))}" if z.get("gueltig_ab") else "")
    t = (k.werkstoffe.get(werkstoff_id) or {}).get("tonnenpreis")
    if t and kgm:
        return t / 1000 * kgm, f"Tonnenpreis {_t(t, 0)} €/t"
    return None, "kein Preis"


def _datum_text(iso):
    try:
        return datetime.date.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso or "")


def _t(x, stellen=2):
    return f"{x:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


LIEFERZEIT_MAX = 365      # Tage: längere „Lieferzeiten“ sind Abrufe/Rahmenbestellungen oder Tippfehler


def lieferzeit(kauf_liste, heute=None, monate=12):
    """Zugesagte Lieferzeit aus den Käufen: Liefertermin minus Kaufdatum (Erfassung) in Tagen, über die letzten
    monate Monate. Käufe ohne Liefertermin, mit Termin vor dem Kaufdatum oder mehr als LIEFERZEIT_MAX Tagen zählen
    nicht. Ergebnis dict(tage Ø gerundet, min, max, anzahl, letzte) oder None."""
    heute = heute or datetime.date.today()
    ab = _monate_zurueck(heute, monate)
    tage = [((x["liefertermin"] - x["datum"]).days, x["datum"]) for x in kauf_liste
            if x.get("liefertermin") and x["datum"] >= ab and 0 <= (x["liefertermin"] - x["datum"]).days <= LIEFERZEIT_MAX]
    if not tage:
        return None
    werte = [t for t, _ in tage]
    return dict(tage=round(sum(werte) / len(werte)), min=min(werte), max=max(werte), anzahl=len(werte),
                letzte=max(tage, key=lambda x: x[1])[0])


def lieferzeit_text(lz, kurz=False):
    """„Ø 12 Tage (5 bis 21, 8 Käufe)“ bzw. kurz „12 Tage“; leer ohne Wert."""
    if not lz:
        return ""
    t = f"{lz['tage']} Tag" + ("" if lz["tage"] == 1 else "e")
    if kurz:
        return t
    return f"Ø {t} ({lz['min']} bis {lz['max']}, {lz['anzahl']} " + ("Kauf)" if lz["anzahl"] == 1 else "Käufe)")


def auswerten(kauf_liste, artikel_liste, k, tabellen, heute=None, monate=12, grenze=0.25):
    """Je Profil + Werkstoff + Oberfläche eine Gruppe aus den Käufen der zugeordneten Artikel (grün, nicht
    übersprungen): dict(profil_id, werkstoff_id, oberflaeche, kaeufe [Kauf + ausreisser, im_zeitraum, gerechnet],
    anzahl, meter, durchschnitt (gewichtet, = Vorschlag), letzter, letzter_datum, min, max, von, bis, heute,
    herkunft, abweichung, kg_m). Zeitraum = die letzten monate Monate vor heute; Ausreißer = mehr als grenze vom
    Median des Zeitraums (mit rechnen 1/0 je Kauf von Hand übersteuert)."""
    from .rechnen import kg_je_m
    heute = heute or datetime.date.today()
    ab = _monate_zurueck(heute, monate)
    zu = {a["schluessel"]: a for a in artikel_liste if a["ampel"] == GRUEN and not a.get("ignorieren")
          and a.get("profil_id") and a.get("werkstoff_id")}
    gruppen = {}
    for kauf in kauf_liste:
        a = zu.get(kauf["schluessel"])
        if a is None:
            continue
        g = gruppen.setdefault((a["profil_id"], a["werkstoff_id"], a["oberflaeche"] or ""), [])
        g.append(kauf)
    out = []
    for (pid, wid, ober), liste in gruppen.items():
        liste = sorted(liste, key=lambda x: x["datum"])
        im = [x for x in liste if x["datum"] >= ab]
        med = median([x["preis"] for x in im]) if im else None
        kaeufe_g = []
        for x in liste:
            drin = x["datum"] >= ab
            ausreisser = bool(drin and med and abs(x["preis"] / med - 1) > grenze)
            hand = x.get("rechnen")
            gerechnet = drin and (bool(hand) if hand is not None else not ausreisser)
            kaeufe_g.append(dict(x, im_zeitraum=drin, ausreisser=ausreisser, gerechnet=gerechnet))
        rech = [x for x in kaeufe_g if x["gerechnet"]]
        meter = sum(x["menge"] for x in rech)
        schnitt = round(sum(x["menge"] * x["preis"] for x in rech) / meter, 2) if meter else None   # wie gespeichert
        hp, herkunft = heute_preis_m(pid, wid, k, tabellen)
        roh = not ober
        abw = schnitt / hp - 1 if schnitt and hp and roh else None      # mit Oberfläche: kein Vergleich mit Rohpreis
        out.append(dict(profil_id=pid, werkstoff_id=wid, oberflaeche=ober, kaeufe=kaeufe_g, anzahl=len(rech),
                        meter=meter, durchschnitt=schnitt,
                        letzter=liste[-1]["preis"], letzter_datum=liste[-1]["datum"],
                        min=min((x["preis"] for x in im), default=None), max=max((x["preis"] for x in im), default=None),
                        von=rech[0]["datum"] if rech else None, bis=rech[-1]["datum"] if rech else None,
                        ausreisser=sum(1 for x in kaeufe_g if x["ausreisser"]), heute=hp, herkunft=herkunft,
                        abweichung=abw, kg_m=kg_je_m(pid, wid, k), lieferzeit=lieferzeit(liste, heute, monate)))
    return sorted(out, key=lambda g: (g["oberflaeche"] != "", g["profil_id"].lower(), g["werkstoff_id"].lower(),
                                      g["oberflaeche"].lower()))


def _monate_zurueck(d, monate):
    j, m = divmod(d.year * 12 + d.month - 1 - int(monate), 12)
    tag = min(d.day, 28)
    return datetime.date(j, m + 1, tag)


def aufpreise(gruppen, k):
    """Aufpreis-Vorschlag je Oberfläche in €/kg (5a, nur Anzeige): je Profil + Werkstoff (Durchschnitt mit Oberfläche
    − Rohpreis) ÷ kg/m, gewichtet nach Metern. Rohpreis = Durchschnitt der Rohware aus der Datei, sonst der heutige
    Preis. Ergebnis [dict(oberflaeche, aufpreis_kg, profile, meter, heute (Text aus den Stammdaten oder ''))]."""
    roh = {(g["profil_id"], g["werkstoff_id"]): g for g in gruppen if not g["oberflaeche"]}
    je = {}
    for g in gruppen:
        if not g["oberflaeche"] or not g["durchschnitt"] or not g["kg_m"]:
            continue
        r = roh.get((g["profil_id"], g["werkstoff_id"]))
        basis = r["durchschnitt"] if r and r["durchschnitt"] else g["heute"]
        if not basis:
            continue
        e = je.setdefault(g["oberflaeche"], dict(summe=0.0, meter=0.0, profile=0))
        e["summe"] += (g["durchschnitt"] - basis) / g["kg_m"] * g["meter"]
        e["meter"] += g["meter"]
        e["profile"] += 1
    out = []
    for ober, e in sorted(je.items()):
        z = k.oberflaechen.get(ober) or {}
        heute = f"{_t(z['aufpreis_m'])} {z.get('aufpreis_basis') or '€/m'}" if z.get("aufpreis_m") is not None else ""
        out.append(dict(oberflaeche=ober, aufpreis_kg=e["summe"] / e["meter"] if e["meter"] else None,
                        profile=e["profile"], meter=e["meter"], heute=heute))
    return out


# ------------------------------------------------------------------ 4. Vorschlag im Angebot
AEHNLICH = (0.5, 2.0)       # „ähnliche Menge“: 0,5- bis 2-fache der benötigten Meter (1a)


def kauf_waehlen(kaeufe_gruppe, bedarf_m, heute=None, monate=12, grenze=None):
    """Bestmöglicher Kauf für den Bedarf [m]: der neueste Kauf der letzten monate Monate mit ähnlicher Menge, sonst der
    neueste im Zeitraum; Käufe, die im Verlauf von Hand ausgeschlossen sind (rechnen = 0), zählen nicht, mit grenze
    auch keine Ausreißer (mehr als grenze vom Median des Zeitraums, z. B. Gutschrift-Rest, Sonderlänge), außer von Hand
    „immer mitrechnen“. None, wenn keiner passt (dann rechnet das Angebot wie bisher)."""
    ab = _monate_zurueck(heute or datetime.date.today(), monate)
    im = sorted((x for x in kaeufe_gruppe if x["datum"] >= ab and x.get("rechnen") != 0),
                key=lambda x: (x["datum"], x.get("id") or 0))
    if grenze and len(im) >= 3:
        med = median(x["preis"] for x in im)
        im = [x for x in im if x.get("rechnen") == 1 or abs(x["preis"] / med - 1) <= grenze] or im
    if not im:
        return None
    aehnlich = [x for x in im if bedarf_m and AEHNLICH[0] * bedarf_m <= x["menge"] <= AEHNLICH[1] * bedarf_m]
    return (aehnlich or im)[-1], bool(aehnlich)


DIREKT_TAGE, DIREKT_STANGEN = 28, 2      # Vorgaben der Einstellungen erp_direkt_tage / erp_direkt_stangen


def direkt_kauf(kaeufe_gruppe, bedarf_stangen, stange_mm, heute=None, tage=DIREKT_TAGE, stangen=DIREKT_STANGEN,
                grenze=None):
    """Kauf, dessen Preis das Angebot direkt einsetzt (Patrick 23.11.2026): höchstens tage alt und Stangenzahl des
    Kaufs (Menge ÷ Stangenlänge, gerundet) höchstens ±stangen vom Bedarf. Von mehreren der neueste, bei gleichem Tag
    der mit der passendsten Stangenzahl. Käufe, die von Hand ausgeschlossen sind, zählen nicht, mit grenze auch keine
    Ausreißer (wie kauf_waehlen, Median der letzten 12 Monate). None sonst."""
    if not stange_mm or bedarf_stangen is None:
        return None
    heute = heute or datetime.date.today()
    kandidaten = list(kaeufe_gruppe)
    if grenze:
        im = [x for x in kandidaten if x["datum"] >= _monate_zurueck(heute, 12) and x.get("rechnen") != 0]
        if len(im) >= 3:
            med = median(x["preis"] for x in im)
            kandidaten = [x for x in kandidaten if x.get("rechnen") == 1 or abs(x["preis"] / med - 1) <= grenze]
    passend = []
    for x in kandidaten:
        if x.get("rechnen") == 0 or not 0 <= (heute - x["datum"]).days <= tage:
            continue
        st = round(x["menge"] * 1000 / stange_mm)
        if abs(st - bedarf_stangen) <= stangen:
            passend.append((x["datum"], -abs(st - bedarf_stangen), x.get("id") or 0, x))
    return max(passend, key=lambda t: t[:3])[3] if passend else None


def schnitt(kaeufe_gruppe, heute=None, monate=12):
    """Nach Menge gewichteter Durchschnitt [€/m] der Käufe der letzten monate Monate (ohne „nie mitrechnen“) oder None."""
    ab = _monate_zurueck(heute or datetime.date.today(), monate)
    im = [x for x in kaeufe_gruppe if x["datum"] >= ab and x.get("rechnen") != 0]
    m = sum(x["menge"] for x in im)
    return sum(x["menge"] * x["preis"] for x in im) / m if m else None


ART_VERLAUF = "ERP-Einkauf"


def verlauf_eintraege(db, k):
    """Käufe der zugeordneten ERP-Artikel als Einträge für das Fenster „Preisverlauf“ (MAT-008, gleiche Felder wie
    preisverlauf.eintraege): art „ERP-Einkauf“ (+ Oberfläche), basis €/m, je Tag der nach Menge gewichtete Preis."""
    liste = gespeicherte(db)
    if not liste:
        return []
    zu = {a["schluessel"]: a for a in artikel(liste, zuordnungen(db), k, nummern_von(db))
          if a["ampel"] == GRUEN and not a.get("ignorieren") and a.get("profil_id") and a.get("werkstoff_id")}
    tage = {}
    for kauf in liste:
        a = zu.get(kauf["schluessel"])
        if a is None or kauf.get("rechnen") == 0:
            continue
        art = ART_VERLAUF + (f" {a['oberflaeche']}" if a["oberflaeche"] else "")
        t = tage.setdefault((art, a["profil_id"], a["werkstoff_id"], kauf["datum"]), [0.0, 0.0, []])
        t[0] += kauf["menge"]
        t[1] += kauf["menge"] * kauf["preis"]
        t[2].append(kauf.get("artikelnr") or "")
    out = []
    for (art, pid, wid, d), (m, summe, nr) in sorted(tage.items(), key=lambda x: x[0][3]):
        out.append(dict(id=None, zeit="", datum=d.isoformat(), art=art, profil_id=pid, werkstoff_id=wid, laenge=None,
                        basis="€/m", preis=round(summe / m, 4),
                        lieferant=f"{_t(m, 0)} m" + (f", {', '.join(dict.fromkeys(x for x in nr if x))}"
                                                     if any(nr) else "")))
    return out


def _stangen_text(meter, stange_mm):
    if not stange_mm:
        return ""
    n = meter * 1000 / stange_mm
    return f" (≈ {n:.0f} Stangen à {_t(stange_mm / 1000, 0 if float(stange_mm / 1000).is_integer() else 1)} m)" \
        if n >= 0.95 else ""


def angebot_vorschlag(db, kopf, positionen, ergebnis, k, tabellen, heute=None):
    """ERP-Preise für das Angebot: je Profil + Werkstoff + Oberfläche (eigenes Material) der Kauf zum Bedarf (Meter
    laut Schnittplan, ohne Plan die Teilelängen). Ergebnis {rechnen.erp_schluessel: dict(preis, datum, menge,
    artikelnr, bezeichnung, aehnlich, bedarf, bemerkung)}; leer ohne Käufe."""
    from . import rechnen
    liste = gespeicherte(db)
    if not liste:
        return {}
    monate = db.einstellung("erp_monate") or 12
    grenze = db.einstellung("erp_ausreisser") or 0.25
    gemerkt = zuordnungen(db)
    zu = {a["schluessel"]: a for a in artikel(liste, gemerkt, k, nummern_von(db))
          if a["ampel"] == GRUEN and not a.get("ignorieren") and a.get("profil_id") and a.get("werkstoff_id")}
    je = {}
    for kauf in liste:
        a = zu.get(kauf["schluessel"])
        if a is not None:
            je.setdefault(rechnen.erp_schluessel(a["profil_id"], a["werkstoff_id"], a["oberflaeche"]), []).append(kauf)
    tage = db.einstellung("erp_direkt_tage")
    tage = DIREKT_TAGE if tage is None else tage
    toleranz = db.einstellung("erp_direkt_stangen")
    toleranz = DIREKT_STANGEN if toleranz is None else toleranz
    bedarf, stange, stangen = {}, {}, {}
    ohne_erp = dict(kopf, erp_preise=None)
    for g in rechnen.material_abmessungen(ohne_erp, positionen, ergebnis, k, tabellen):
        if g["kunde"]:
            continue
        s = rechnen.erp_schluessel(g["profil"], g["werkstoff"], g["oberflaeche"])
        bedarf[s] = bedarf.get(s, 0.0) + (g["meter"] if g["stangen"] else g["teile_m"])
        stange.setdefault(s, g["stange"])
        # Stangen laut Schnittplan, ohne Plan aus den Teilemetern geschätzt
        stangen[s] = stangen.get(s, 0) + (g["stangen"] or (math.ceil(g["teile_m"] * 1000 / g["stange"])
                                                          if g["stange"] else 0))
    out = {}
    for s, m in bedarf.items():
        d = direkt_kauf(je.get(s, ()), stangen.get(s), stange.get(s), heute, tage, toleranz, grenze)
        w = (d, True) if d is not None else kauf_waehlen(je.get(s, ()), m, heute, monate, grenze)
        if w is None:
            continue
        kauf, aehnlich = w
        bem = (f"ERP-Preis vom {kauf['datum'].strftime('%d.%m.%Y')}, {_t(kauf['menge'], 0)} m"
               f"{_stangen_text(kauf['menge'], stange.get(s))}"
               + (f", Artikel {kauf['artikelnr']}" if kauf.get("artikelnr") else "")
               + ("" if aehnlich else f"; kein Kauf mit ähnlicher Menge (Bedarf {_t(m, 0)} m)"))
        mittel = schnitt(je.get(s, ()), heute, monate)
        if mittel and abs(mittel - kauf["preis"]) >= 0.005:
            bem += f"; Ø {monate} Monate {_t(mittel)} €/m"
        alter = ((heute or datetime.date.today()) - kauf["datum"]).days
        kauf_st = round(kauf["menge"] * 1000 / stange[s]) if stange.get(s) else None
        if d is None:
            gruende = []
            if alter > tage:
                gruende.append(f"Kauf {alter} Tage alt (direkt nur bis {int(tage)} Tage)")
            if kauf_st is not None and abs(kauf_st - stangen.get(s, 0)) > toleranz:
                gruende.append(f"{kauf_st} statt {stangen.get(s, 0)} Stangen (±{int(toleranz)})")
            bem += "; nur Vorschlag, nicht eingesetzt: " + (", ".join(gruende) or "passt nicht")
        else:
            bem += f"; direkt eingesetzt (Kauf {alter} Tage alt, {kauf_st} Stangen, Bedarf {stangen.get(s, 0)})"
        out[s] = dict(preis=kauf["preis"], datum=kauf["datum"].isoformat(), menge=kauf["menge"],
                      artikelnr=kauf.get("artikelnr") or "", bezeichnung=kauf["bezeichnung"], aehnlich=aehnlich,
                      bedarf=round(m, 1), bemerkung=bem, direkt=d is not None, stangen_kauf=kauf_st,
                      stangen_bedarf=stangen.get(s, 0))
    return out


def angebot_speichern(db, angebot_id, daten):
    """Gewählte ERP-Preise am Angebot speichern (leer = keine, das Angebot rechnet wie bisher)."""
    import json
    with db.con:
        db.con.execute("UPDATE angebote SET erp_preise=? WHERE id=?",
                       (json.dumps(daten, ensure_ascii=False) if daten else None, angebot_id))


# ------------------------------------------------------------------ 5. Importassistent (Master-Auftrag 25.11.2026)
NEU_KAUF, VORHANDEN, DOPPELT, FEHLERHAFT = "neu", "unverändert (schon eingelesen)", "doppelt in der Datei", "fehlerhaft"
ERHOEHUNG, SENKUNG, GLEICH, ERSTER = "Erhöhung", "Senkung", "gleich", "erster Preis"


def _kauf_schl(x):
    d = x["datum"].isoformat() if hasattr(x["datum"], "isoformat") else str(x["datum"])
    return (d, x["schluessel"], round(float(x["menge"]), 6), round(float(x["preis"]), 6))


def _material_schluessel(a):
    """(Profil, Werkstoff, Oberfläche) eines zugeordneten ERP-Artikels, sonst None."""
    if not a or a.get("ignorieren"):
        return None
    if a.get("ampel") == GRUEN and a.get("profil_id") and a.get("werkstoff_id"):
        return (a["profil_id"], a["werkstoff_id"], a.get("oberflaeche") or "")
    v = a.get("vorschlag_zuordnung")
    if v:
        return (v["profil_id"], v["werkstoff_id"], v.get("oberflaeche") or "")
    return None


def preis_pruefung(neue, bisher, artikel_neu, artikel_bisher, grenze_pct=PREIS_MARKE_VORGABE):
    """Preisprüfung (Schritt 4): je Material (Profil + Werkstoff + Oberfläche, sonst ERP-Artikel) und Lieferant der
    neueste EK aus der Datei gegen den letzten bisher gespeicherten EK davor. Ein Preis eines anderen Lieferanten
    gilt nur als Vergleich (Spalte alt_lieferant), er wird nie ersetzt: jeder Kauf bleibt mit seinem Lieferanten
    gespeichert. Ergebnis [dict(material, artikel, lieferant, neu, neu_datum, alt, alt_datum, alt_lieferant, euro,
    pct, richtung, markiert, zugeordnet)], größte Änderung zuerst."""
    zu_neu = {a["schluessel"]: a for a in artikel_neu}
    zu_alt = {a["schluessel"]: a for a in artikel_bisher}

    def mat(kauf, zu):
        a = zu.get(kauf["schluessel"])
        m = _material_schluessel(a)
        return (m, True) if m else (("#" + kauf["schluessel"], "", ""), False)
    alt_je = {}
    for x in bisher:
        m, _ = mat(x, zu_alt)
        alt_je.setdefault(m, []).append(x)
    for v in alt_je.values():
        v.sort(key=lambda x: (x["datum"], x.get("id") or 0))
    gruppen = {}
    for x in neue:
        m, zug = mat(x, zu_neu)
        lief = (x.get("lieferant") or "").strip()
        g = gruppen.setdefault((m, lief.lower()), dict(material=m, zugeordnet=zug, kaeufe=[], lieferant=lief))
        g["kaeufe"].append(x)
    schon = {_kauf_schl(x) for x in bisher}
    out = []
    for (m, lief_n), g in gruppen.items():
        neu_k = max(g["kaeufe"], key=lambda x: (x["datum"], x["zeile"]))
        vorher = [x for x in alt_je.get(m, []) if x["datum"] <= neu_k["datum"] and _kauf_schl(x) not in
                  {_kauf_schl(neu_k)}]
        gleich_l = [x for x in vorher if (x.get("lieferant") or "").strip().lower() == lief_n]
        alt_k = (gleich_l or vorher or [None])[-1]
        z = dict(material=m, zugeordnet=g["zugeordnet"], artikel=neu_k.get("artikelnr") or "",
                 bezeichnung=neu_k["bezeichnung"], lieferant=g["lieferant"], neu=neu_k["preis"],
                 neu_datum=neu_k["datum"], alt=None, alt_datum=None, alt_lieferant="", euro=None, pct=None,
                 richtung=ERSTER, markiert=False, schon_da=_kauf_schl(neu_k) in schon, anzahl=len(g["kaeufe"]))
        if alt_k is not None:
            z.update(alt=alt_k["preis"], alt_datum=alt_k["datum"], alt_lieferant=(alt_k.get("lieferant") or ""),
                     euro=neu_k["preis"] - alt_k["preis"])
            z["pct"] = (neu_k["preis"] / alt_k["preis"] - 1) * 100 if alt_k["preis"] else None
            z["richtung"] = GLEICH if abs(z["euro"]) < 0.005 else (ERHOEHUNG if z["euro"] > 0 else SENKUNG)
            z["markiert"] = z["pct"] is not None and abs(z["pct"]) >= float(grenze_pct or 0) and z["richtung"] != GLEICH
            z["anderer_lieferant"] = bool(not gleich_l and z["alt_lieferant"].strip().lower() != lief_n)
        out.append(z)
    return sorted(out, key=lambda z: (-(abs(z["pct"]) if z["pct"] is not None else -1), str(z["material"])))


def vorschau_import(db, daten, zuordnung, grenze_pct=None, fortschritt=None, lieferant=""):
    """Vorschau des EK-Imports ohne Datenbankänderung (Schritte 3 bis 5): Käufe, Gruppen (neu / unverändert /
    doppelt / fehlerhaft), ERP-Artikel mit Zuordnungsstufe, Preisprüfung, neue Materialien (erp_anlegen.plan).
    Ergebnis dict(kaeufe, gruppe {Dateizeile: Gruppe}, fehler [(Zeile, Grund, Zellen)], meldungen, artikel,
    pruefung, plan, zaehler)."""
    from . import erp_anlegen
    k = db.kontext()
    fehler = []
    if fortschritt:
        fortschritt(0, 4, "Zeilen prüfen")
    liste, meldungen = kaeufe(daten, zuordnung, k, fehler)
    if lieferant:                   # Lieferant aus Schritt 1 für Zeilen ohne eigene Lieferantenspalte
        for x in liste:
            x["lieferant"] = x.get("lieferant") or lieferant
    bisher = gespeicherte(db)
    schon = {_kauf_schl(x) for x in bisher}
    gruppe, gesehen = {}, {}
    for x in liste:
        s_ = _kauf_schl(x)
        if s_ in gesehen:
            gruppe[x["zeile"]] = DOPPELT
            x["doppelt_wie"] = gesehen[s_]
        elif s_ in schon:
            gruppe[x["zeile"]] = VORHANDEN
        else:
            gruppe[x["zeile"]] = NEU_KAUF
        gesehen.setdefault(s_, x["zeile"])
    for n, _g, _r in fehler:
        gruppe[n] = FEHLERHAFT
    if fortschritt:
        fortschritt(1, 4, "Materialien erkennen")
    gemerkt, nummern = zuordnungen(db), nummern_von(db)
    art_neu = artikel(liste, gemerkt, k, nummern)
    if fortschritt:
        fortschritt(2, 4, "Preise prüfen")
    art_alt = artikel(bisher, gemerkt, k, nummern) if bisher else []
    if grenze_pct is None:
        grenze_pct = db.einstellung(PREIS_MARKE)
        grenze_pct = PREIS_MARKE_VORGABE if grenze_pct in (None, "") else float(grenze_pct)
    pruef = preis_pruefung([x for x in liste if gruppe[x["zeile"]] == NEU_KAUF], bisher, art_neu, art_alt, grenze_pct)
    if fortschritt:
        fortschritt(3, 4, "Neue Materialien")
    plan = erp_anlegen.plan(db, kaeufe=liste) if liste else dict(profile=[], werkstoffe=[], zuordnungen=[], offen=[])
    z = {g: 0 for g in (NEU_KAUF, VORHANDEN, DOPPELT, FEHLERHAFT)}
    for g in gruppe.values():
        z[g] += 1
    z.update({s_: sum(1 for a in art_neu if a.get("stufe") == s_) for s_ in STUFEN})
    z["preise_geaendert"] = sum(1 for p in pruef if p["richtung"] in (ERHOEHUNG, SENKUNG))
    z["preise_markiert"] = sum(1 for p in pruef if p["markiert"])
    if fortschritt:
        fortschritt(4, 4, "fertig")
    return dict(kaeufe=liste, gruppe=gruppe, fehler=fehler, meldungen=meldungen, artikel=art_neu, pruefung=pruef,
                plan=plan, zaehler=z, grenze_pct=grenze_pct)


def uebernehmen(db, v, datei="", bestaetigt=(), anlegen=True, mit_werkstoffen=True, importprofil="", lieferant=""):
    """Import abschließen (Schritt 6) als ein Importlauf (csv_import.Lauf, Art „EK-Einkäufe“): neue Käufe in einer
    Transaktion speichern, bestätigte Zuordnungen (bestaetigt = [(ERP-Artikel, dict(profil_id, werkstoff_id,
    oberflaeche) oder None = Vorschlag)]) merken, neue Profile/Werkstoffe anlegen (erp_anlegen, anlegen=True).
    Bricht etwas ab, wird der ganze Lauf zurückgenommen (ErpFehler). Ergebnis dict(import_id, neu, zuordnungen,
    profile, werkstoffe, stamm_neu)."""
    from . import erp_anlegen
    from . import ki_protokoll
    z = v["zaehler"]
    lauf = csv_import.lauf_beginnen(db, csv_import.ART_EK, datei, importprofil, len(v["kaeufe"]) + len(v["fehler"]),
                                    lieferant, dict(unveraendert=z[VORHANDEN], doppelt=z[DOPPELT],
                                                    fehler=z[FEHLERHAFT], offen=z[KEIN_TREFFER]))
    erg = dict(import_id=lauf.id, neu=0, zuordnungen=0, profile=0, werkstoffe=0, stamm_neu=0)
    try:
        lauf.zeilen_mit_lauf("erp_kaeufe")
        lauf.flush()
        erg["neu"] = speichern(db, [x for x in v["kaeufe"] if v["gruppe"].get(x["zeile"]) == NEU_KAUF],
                               str(datei).replace("\\", "/").rsplit("/", 1)[-1], lauf.id)
        for a, wahl in bestaetigt:
            bestaetigen(db, a, lauf=lauf, **(wahl or {}))
            erg["zuordnungen"] += 1
        if anlegen:
            p = erp_anlegen.plan(db, kaeufe=v["kaeufe"])
            e = erp_anlegen.ausfuehren(db, p, mit_werkstoffen=mit_werkstoffen, lauf=lauf)
            erg.update(profile=e["profile"], werkstoffe=e["werkstoffe"], stamm_neu=e.get("stamm_neu") or 0)
            erg["zuordnungen"] += e["zuordnungen"]
    except Exception as ex:     # noqa: BLE001  (alles zurücknehmen, dann melden)
        lauf.flush()
        rueckgaengig(db, lauf.id, status="abgebrochen, zurückgenommen")
        raise ErpFehler(f"Import abgebrochen und vollständig zurückgenommen: {ex}") from ex
    csv_import.lauf_abschliessen(db, lauf, neu=erg["neu"], aktualisiert=erg["zuordnungen"],
                                 preise=v["zaehler"].get("preise_geaendert", 0),
                                 protokoll=dict(erg, preise_markiert=v["zaehler"].get("preise_markiert", 0),
                                                fehler=[f"Zeile {n}: {g}" for n, g, _ in v["fehler"][:200]]))
    _KAEUFE_STAND[0] += 1
    ki_protokoll.schreiben(db, "Materialprüfung", "EK-Import (Assistent)",
                           ergebnis=f"{erg['neu']} Käufe neu, {erg['zuordnungen']} Zuordnungen, {erg['profile']} "
                                    f"Profile, {erg['werkstoffe']} Werkstoffe", quellen=[str(datei)])
    return erg


def rueckgaengig(db, import_id, status="rückgängig gemacht"):
    """EK-Importlauf zurücknehmen: Käufe des Laufs löschen, gemerkte Zuordnungen auf den alten Stand, angelegte
    Profile, Werkstoffe und Materialstamm-Zeilen löschen (csv_import.rueckgaengig). Ergebnis (Anzahl, Meldungen)."""
    n = 0
    for p in reversed(csv_import.posten_des_laufs(db, import_id)):
        if p["tabelle"] != "erp_zuordnung" or p["aktion"] != "zuordnung":
            continue
        schl = (p["neu"] or {}).get("schluessel")
        alt = p["alt"]
        with db.con:
            if alt:
                db.con.execute("UPDATE erp_zuordnung SET artikelnr=?, bezeichnung=?, profil_id=?, werkstoff_id=?, "
                               "oberflaeche=?, ignorieren=?, geaendert=? WHERE schluessel=?",
                               (alt.get("artikelnr"), alt.get("bezeichnung"), alt.get("profil_id"),
                                alt.get("werkstoff_id"), alt.get("oberflaeche"), alt.get("ignorieren"),
                                alt.get("geaendert"), schl))
            else:
                db.con.execute("DELETE FROM erp_zuordnung WHERE schluessel=?", (schl,))
        n += 1
    m, meldungen = csv_import.rueckgaengig(db, import_id, status)
    _KAEUFE_STAND[0] += 1
    return n + m, meldungen


def fehlerbericht(v, kopf=None):
    """Fehlerhafte und doppelte Zeilen als CSV zum Nachbessern im ERP."""
    zeilen = [(n, FEHLERHAFT, g, roh) for n, g, roh in v["fehler"]]
    zeilen += [(x["zeile"], DOPPELT, f"gleicher Kauf wie Zeile {x.get('doppelt_wie')}", x.get("roh"))
               for x in v["kaeufe"] if v["gruppe"].get(x["zeile"]) == DOPPELT]
    return csv_import.fehlerbericht_csv(sorted(zeilen, key=lambda z: z[0]), kopf)
