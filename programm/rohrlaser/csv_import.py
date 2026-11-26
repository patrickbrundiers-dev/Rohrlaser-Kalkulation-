"""Gemeinsame Importbasis für CSV-Importe (Master-Aufträge Patrick 25.11.2026: „EK-CSV-Import grundlegend
verbessern“ und „Kundenlisten-CSV-Import … EK-CSV-Import als technische Vorlage“). Ohne Qt.

Eine Basis für alle Tabellen-Importe des Programms, damit EK-Einkäufe (erp_preise), Materialstamm/Preislisten
(material_import) und Kundenlisten (kunden_csv) gleich lesen, gleich erkennen und gleich protokollieren. Die
Datenmodelle und Prüfregeln bleiben in den jeweiligen Modulen.

1. datei_lesen(): Kodierung (UTF-8 mit/ohne BOM, UTF-16, Windows-1252), Trennzeichen (; , Tab |, auch „sep=;“) nach
   Gleichmäßigkeit über die ersten Zeilen, Kopfzeile (auch mit Titelzeilen davor) oder Datei ohne Kopfzeile,
   Dezimalkomma oder -punkt, Excel-Schutz ="…". Excel-Dateien (.xlsx) werden vorher als CSV gelesen.
2. spalten_erkennen(): Spalten nach Namen (deutsch/englisch, Schreibweisen egal) und nach Inhalt (Datum, Zahl,
   E-Mail, PLZ, Telefon, Abmessung …). Jede Zuordnung trägt „sicher“ oder ist nur ein Vorschlag (mehrdeutiger Name
   wie „Name“, nur am Inhalt erkannt, Inhalt passt nicht zum Namen): unsichere Zuordnungen bestätigt der Anwender im
   Assistenten, nie still.
3. Importprofile: gespeicherte Zuordnungen je Importart (Einstellung), erkannt am Spaltenkopf; die Spalten stehen
   zusätzlich mit ihrem Namen drin, damit eine Datei mit anderer Spaltenreihenfolge dasselbe Profil findet.
   Bearbeiten, kopieren, umbenennen, löschen.
4. Lauf: Importprotokoll mit Datum, Datei, Importart, Lieferant, Zählern und jeder Änderung samt altem Wert
   (Tabellen material_importe / material_import_posten, Spalte art); rueckgaengig() nimmt einen Lauf vollständig
   zurück. Posten werden gesammelt und in einem Schritt geschrieben (Batch statt Einzeloperationen).
"""
import csv
import datetime
import io
import json
import re
from .zahlen import jetzt_text as _jetzt  # Audit 26.11.2026 R-01: gemeinsame Hilfsfunktion

TRENNER = {";": "Semikolon", ",": "Komma", "\t": "Tabulator", "|": "senkrechter Strich"}
SICHER, VORSCHLAG = "sicher", "Vorschlag"


class ImportFehler(ValueError):
    """Datei nicht lesbar (Text für den Benutzer)."""


def norm(t):
    """Vergleichsform eines Spaltennamens: klein, nur Buchstaben und Ziffern (Umlaute bleiben)."""
    return re.sub(r"[^0-9a-zäöüß]+", "", str(t or "").lower())


def spalte(i):
    """Spaltenbuchstabe wie in Excel: 0 -> A, 26 -> AA."""
    t = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        t = chr(65 + r) + t
    return t


# ------------------------------------------------------------------ Zahlen und Datum
def zahl(t, dezimal=None):
    """Zahl aus Text: 1.234,56 / 1,234.56 / 12,5 / 12.5 / „3,45 €“ / „120 m“; None, wenn keine Zahl.
    dezimal = 'Punkt' (Datei mit Dezimalpunkt): „1.250“ ist 1,25 und „1,250“ ist 1250; sonst (None/'Komma') gilt
    die deutsche Schreibweise wie bisher („1.250“ = 1250)."""
    s = str(t or "").replace(" ", " ").strip()
    s = re.sub(r"(?i)\s*(€|eur|euro|€/m|m|lfm|lfdm|%)\.?$", "", s).replace("€", "").replace(" ", "").replace("'", "")
    if not re.fullmatch(r"[-+]?[\d.,]*\d[\d.,]*", s or "x"):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        if dezimal == "Punkt" and re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")          # 1,250 = 1250 (englische Tausenderkommas)
        else:
            s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    elif s.count(".") > 1 or (dezimal != "Punkt" and re.fullmatch(r"[-+]?\d{1,3}\.\d{3}", s)):
        s = s.replace(".", "")              # 1.250 = 1250 (deutsche Tausenderpunkte)
    try:
        return float(s)
    except ValueError:
        return None


def datum(t):
    """Datum aus TT.MM.JJJJ, TT.MM.JJ, JJJJ-MM-TT, TT/MM/JJJJ (auch mit Uhrzeit) oder Excel-Tageszahl; sonst None."""
    s = str(t or "").strip().split(" ")[0].split("T")[0]
    for f in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y.%m.%d", "%Y%m%d"):
        try:
            d = datetime.datetime.strptime(s, f).date()
            if 1990 <= d.year <= 2100:
                return d
        except ValueError:
            pass
    if re.fullmatch(r"\d{5}", s) and 30000 <= int(s) <= 60000:          # Excel: Tage seit 30.12.1899
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(s))
    return None


# ------------------------------------------------------------------ 1. Datei lesen
def text_lesen(roh):
    """(Text, Kodierung) aus Bytes: UTF-16 (Excel 'Unicode-Text', mit/ohne BOM), UTF-8 mit/ohne BOM, sonst
    Windows-1252 (Excel 'CSV (Trennzeichen-getrennt)'); Bytes, die es dort nicht gibt, als Latin-1 statt Abbruch."""
    if not isinstance(roh, bytes):
        return roh.lstrip("﻿"), "Text"
    if roh.startswith((b"\xff\xfe", b"\xfe\xff")):
        return roh.decode("utf-16", errors="replace").lstrip("﻿"), "UTF-16"
    if roh[:400].count(b"\x00") > len(roh[:400]) // 4:          # UTF-16 ohne BOM
        try:
            return roh.decode("utf-16-le" if roh[1:2] == b"\x00" else "utf-16-be"), "UTF-16"
        except UnicodeDecodeError:
            pass
    if roh.startswith(b"\xef\xbb\xbf"):
        try:
            return roh.decode("utf-8-sig"), "UTF-8 (mit BOM)"
        except UnicodeDecodeError:
            pass
    try:
        return roh.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        pass
    try:
        return roh.decode("cp1252"), "Windows-1252 (ANSI)"
    except UnicodeDecodeError:
        return roh.decode("latin-1"), "ISO-8859-1"


def excel_wert(t):
    """="…" (Export-Schutz für Excel) wieder zum reinen Text."""
    m = re.fullmatch(r'\s*="(.*)"\s*', t, re.S)
    return m.group(1).replace('""', '"') if m else t


def trenner_erkennen(zeilen):
    """(Trennzeichen, sep-Zeile): 'sep=;' in der ersten Zeile, sonst das Zeichen, das in den meisten der ersten Zeilen
    so oft steht wie in der ersten (Gleichmäßigkeit statt größter Anzahl: eine Zeile mit drei Dezimalkommas
    „Rohr 42,4x2,0 …;2,60“ gewinnt sonst gegen das Semikolon). Zeichen in Anführungszeichen zählen nicht."""
    erste = next((z for z in zeilen if z.strip()), "")
    m = re.fullmatch(r'\s*"?sep=(.)"?\s*', erste, re.I)
    if m:
        return m.group(1), True
    probe = [re.sub(r'"[^"]*"', "", z) for z in zeilen[:15] if z.strip()]
    if not probe:
        return ";", False

    def guete(c):
        n = probe[0].count(c)
        return (sum(1 for z in probe if z.count(c) == n) if n else 0, n, c == ";", c == "\t")
    return max(TRENNER, key=guete), False


def _kopfartig(c):
    """Sieht die Zelle wie ein Spaltenname aus (Text, kurz, keine Zahl/Datum/E-Mail/Abmessung)?"""
    c = c.strip()
    return bool(c) and len(c) <= 60 and zahl(c) is None and datum(c) is None and "@" not in c and \
        sum(ch.isdigit() for ch in c) <= 3 and not re.search(r"\d\s*[x×*/]\s*\d", c) and \
        bool(re.search(r"[A-Za-zÄÖÜäöüß]", c))


def dezimal_erkennen(zeilen, max_zeilen=200):
    """'Komma', 'Punkt' oder None: welches Dezimalzeichen die Zahlen der Datei benutzen (eindeutige Fälle: „3,10“,
    „1.234,56“ = Komma; „3.10“, „1,234.56“ = Punkt; „1.250“ allein ist unklar)."""
    komma = punkt = 0
    for z in zeilen[:max_zeilen]:
        for c in z:
            s = c.strip().replace(" ", "")
            if not re.fullmatch(r"[-+]?[\d.,]*\d", s) or len(s) > 20:
                continue
            if re.fullmatch(r"[-+]?\d+,\d{1,2}|[-+]?\d+,\d{4,}|[-+]?\d{1,3}(\.\d{3})+,\d+", s):
                komma += 1
            elif re.fullmatch(r"[-+]?\d+\.\d{1,2}|[-+]?\d+\.\d{4,}|[-+]?\d{1,3}(,\d{3})+\.\d+", s):
                punkt += 1
    if komma == punkt:
        return None
    return "Komma" if komma > punkt else "Punkt"


def datei_lesen(roh, dateiname="", bekannte=(), mindestens=3, ohne_kopf=True, kopf_ohne_bekannte=True):
    """Datei (Bytes oder Text) -> dict(kopf, zeilen, erste, mit_kopf, kodierung, trenner, dezimal, meldungen).

    Kopfzeile = die erste der ersten 15 Zeilen mit mindestens `mindestens` Zellen, die wie Spaltennamen aussehen;
    mit `bekannte` (Spaltennamen der Importart) zuerst eine solche Zeile, in der einer davon vorkommt; mit
    kopf_ohne_bekannte=False muss einer vorkommen (Kundenlisten: „Muster GmbH;Hauptstr. 1;Paderborn“ sieht sonst
    wie eine Kopfzeile aus). Ohne passende Zeile gilt die Datei als ohne Kopfzeile (kopf = „Spalte A“, „Spalte B“ …, alle Zeilen sind Daten). Eine Titelzeile über der
    Kopfzeile wird übersprungen; ohne_kopf=False: dann ImportFehler. erste = Dateizeile der ersten Datenzeile (wie
    in Excel)."""
    kodierung = None
    if str(dateiname).lower().endswith(".xlsx") or (isinstance(roh, bytes) and roh[:2] == b"PK"):
        import tempfile
        from pathlib import Path

        from . import materialplattform as mp
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "datei.xlsx"
            p.write_bytes(roh)
            roh = mp.xlsx_als_csv(p)
        if roh is None:
            raise ImportFehler("Die Excel-Datei ist nicht lesbar.")
        kodierung = "Excel (.xlsx)"
    text, kod = text_lesen(roh)
    kodierung = kodierung or kod
    zeilen = text.splitlines()
    if not any(z.strip() for z in zeilen):
        raise ImportFehler("Die Datei ist leer.")
    trenner, sep_zeile = trenner_erkennen(zeilen)
    versatz = 0
    if sep_zeile:
        i = next(i for i, z in enumerate(zeilen) if z.strip())
        zeilen = zeilen[i + 1:]
        versatz = i + 1
    try:
        alle = [[excel_wert(c).strip() for c in z] for z in csv.reader(io.StringIO("\n".join(zeilen)),
                                                                     delimiter=trenner)]
    except csv.Error as e:
        raise ImportFehler(f"Datei nicht lesbar ({e}). Bitte in Excel als „CSV UTF-8“ speichern.") from None
    bek = {norm(b) for b in bekannte if norm(b)}
    meldungen = []
    for mit_bekannten in ((True, False) if bek and kopf_ohne_bekannte else (bool(bek),)):
        for i, z in enumerate(alle[:15]):
            zellen = [c for c in z if c]
            kopfartig = [c for c in zellen if _kopfartig(c)]
            if len(kopfartig) < mindestens or len(kopfartig) < 0.6 * len(zellen):
                continue
            if mit_bekannten and not any(norm(c) in bek for c in kopfartig):
                continue
            daten = [r for r in alle[i + 1:] if any(c for c in r)]
            return dict(kopf=z, zeilen=daten, erste=i + 2 + versatz, mit_kopf=True, kodierung=kodierung,
                        trenner=trenner, dezimal=dezimal_erkennen(daten), meldungen=meldungen)
    if not ohne_kopf or not alle:
        raise ImportFehler("Keine Kopfzeile gefunden.")
    daten = [r for r in alle if any(c for c in r)]
    breite = max((len(r) for r in daten), default=0)
    if breite < 2:
        raise ImportFehler("Keine Spalten erkannt: die Datei hat nur eine Spalte (Trennzeichen ; , Tab oder |).")
    erste = next(i for i, r in enumerate(alle) if any(c for c in r)) + 1 + versatz
    meldungen.append("Keine Kopfzeile erkannt: Spalten werden am Inhalt erkannt, bitte im Schritt „Spalten“ prüfen.")
    return dict(kopf=[f"Spalte {spalte(i)}" for i in range(breite)], zeilen=daten, erste=erste, mit_kopf=False,
                kodierung=kodierung, trenner=trenner, dezimal=dezimal_erkennen(daten), meldungen=meldungen)


def format_text(daten):
    """„UTF-8 · Semikolon · Dezimalkomma · mit Kopfzeile · 1.234 Zeilen, 8 Spalten“ für Schritt 1."""
    teile = [daten.get("kodierung") or "?", TRENNER.get(daten.get("trenner"), repr(daten.get("trenner"))),
             {"Komma": "Dezimalkomma", "Punkt": "Dezimalpunkt"}.get(daten.get("dezimal"), "Dezimalzeichen offen"),
             "mit Kopfzeile" if daten.get("mit_kopf", True) else "ohne Kopfzeile",
             f"{len(daten.get('zeilen') or ()):,} Zeilen, {len(daten.get('kopf') or ())} Spalten".replace(",", ".")]
    return " · ".join(teile)


# ------------------------------------------------------------------ 2. Spalten erkennen
_EMAIL = re.compile(r"^[\w.+'-]+@[\w-]+(\.[\w-]+)+$")
_URL = re.compile(r"(?i)^(https?://|www\.)[\w.-]+\.[a-z]{2,}(/\S*)?$|^[\w-]+(\.[\w-]+)*\.(de|com|eu|at|ch|net|org)$")
_TELEFON = re.compile(r"^(\+|00|0)[\d\s/()\-–.]{6,}$")
_PLZ = re.compile(r"^(D-|A-|CH-)?\d{4,5}$")
_UST = re.compile(r"(?i)^(DE|AT|ATU|CH|NL|BE|FR|PL|CZ|DK|LU|IT|ES)[\s]?[\dA-Z]{8,12}(MWST|TVA|IVA)?$")
_MASS = re.compile(r"\d+(?:[.,]\d+)?\s*(?:mm)?\s*[x×*X/]\s*\d+(?:[.,]\d+)?")


def inhalt_art(werte):
    """Anteil je Inhaltsart einer Spalte (0..1): datum, zahl, ganz, email, url, telefon, plz, ust, masse, text,
    leer. Grundlage für Spalten ohne Kopfzeile und für die Gegenprobe (Spalte „Preis“ mit Datumswerten = unsicher)."""
    w = [str(x).strip() for x in werte]
    voll = [x for x in w if x]
    out = dict(leer=1 - len(voll) / len(w) if w else 1.0)
    if not voll:
        return dict(out, datum=0, zahl=0, ganz=0, email=0, url=0, telefon=0, plz=0, ust=0, masse=0, text=0)
    n = len(voll)

    def anteil(f):
        return sum(1 for x in voll if f(x)) / n
    out.update(datum=anteil(lambda x: datum(x) is not None and not re.fullmatch(r"\d{5}", x)),
               zahl=anteil(lambda x: zahl(x) is not None),
               ganz=anteil(lambda x: re.fullmatch(r"\d+", x) is not None),
               email=anteil(lambda x: _EMAIL.match(x) is not None),
               url=anteil(lambda x: _URL.match(x) is not None),
               telefon=anteil(lambda x: _TELEFON.match(x) is not None and sum(c.isdigit() for c in x) >= 6),
               plz=anteil(lambda x: _PLZ.match(x) is not None),
               ust=anteil(lambda x: _UST.match(x.replace(" ", "")) is not None),
               masse=anteil(lambda x: _MASS.search(x) is not None),
               text=anteil(lambda x: zahl(x) is None and datum(x) is None and re.search(r"[A-Za-zÄÖÜäöüß]", x)))
    out["eindeutig"] = len(set(voll)) / n
    return out


def spalten_werte(daten, i, max_zeilen=300):
    return [z[i] if i < len(z) else "" for z in daten["zeilen"][:max_zeilen]]


def spalten_erkennen(daten, felder, reihe=None, inhalt=None, mehrdeutig=None, kontext=None):
    """Spalten der Datei den Feldern zuordnen.

    felder = {Feld: (Spaltennamen …)}; erst gleicher Name, dann Name enthalten (ab 4 Zeichen), in der Reihenfolge
    reihe (spezifische Felder zuerst: „Meterpreis“ enthält „meter“). inhalt = {Feld: Funktion(inhalt_art) ->
    Anteil 0..1}: prüft, ob der Inhalt zum Feld passt (unter 0,5 = nur Vorschlag), und ordnet in Dateien ohne
    Kopfzeile die Spalten am Inhalt zu (immer nur Vorschlag). mehrdeutig = {normierter Name: (Feld, …)}: solche
    Spalten entscheidet kontext(feld_kandidaten, erkannt, kopf) -> Feld oder None und sie bleiben ein Vorschlag.
    Ergebnis {Feld: dict(spalte, sicherheit (SICHER/VORSCHLAG), grund)}."""
    kopf = daten["kopf"]
    reihe = list(reihe or felder)
    namen = [norm(k) for k in kopf]
    frei, out = set(range(len(kopf))), {}
    inhalt = inhalt or {}
    arten = {}

    def art(i):
        if i not in arten:
            arten[i] = inhalt_art(spalten_werte(daten, i))
        return arten[i]

    if daten.get("mit_kopf", True):
        mehr = {norm(k): v for k, v in (mehrdeutig or {}).items()}
        for gleich in (True, False):
            for feld in reihe:
                if feld in out:
                    continue
                for wort in felder.get(feld, ()):
                    w = norm(wort)
                    if not w or (not gleich and len(w) < 4):
                        continue
                    treffer = [i for i in sorted(frei) if (namen[i] == w if gleich else w in namen[i])
                               and namen[i] not in mehr]
                    if treffer:
                        i = treffer[0]
                        s, grund = SICHER, f"Spaltenname „{kopf[i]}“" + ("" if gleich else f" enthält „{wort}“")
                        if feld in inhalt and any(c.strip() for c in spalten_werte(daten, i)):
                            if inhalt[feld](art(i)) < 0.5:
                                s, grund = VORSCHLAG, grund + ", aber der Inhalt passt nicht dazu – bitte prüfen"
                        out[feld] = dict(spalte=i, sicherheit=s, grund=grund)
                        frei.discard(i)
                        break
        for i in sorted(frei):
            kand = mehr.get(namen[i])
            if not kand:
                continue
            feld = kontext(kand, out, kopf) if kontext else None
            feld = feld if feld in kand and feld not in out else next((f for f in kand if f not in out), None)
            if feld:
                out[feld] = dict(spalte=i, sicherheit=VORSCHLAG,
                                 grund=f"„{kopf[i]}“ ist mehrdeutig ({' oder '.join(kand)}) – bitte bestätigen")
                frei.discard(i)
    # am Inhalt: freie Spalten ohne passenden Namen (immer nur Vorschlag)
    for feld in reihe:
        if feld in out or feld not in inhalt:
            continue
        beste = None
        for i in sorted(frei):
            if daten.get("mit_kopf", True) and _kopfartig(kopf[i]) and namen[i]:
                if any(norm(w) == namen[i] for ff in felder.values() for w in ff):
                    continue            # Spalte hat einen bekannten Namen eines anderen Feldes
            a = art(i)
            if a["leer"] > 0.9:
                continue
            g = inhalt[feld](a)
            if g >= 0.8 and (beste is None or g > beste[0]):
                beste = (g, i)
        if beste:
            i = beste[1]
            out[feld] = dict(spalte=i, sicherheit=VORSCHLAG, grund=f"am Inhalt erkannt ({beste[0]:.0%} der Werte "
                             "passen) – bitte bestätigen")
            frei.discard(i)
    return out


def zuordnung(erkannt):
    """{Feld: Spaltennummer} aus spalten_erkennen()."""
    return {f: e["spalte"] for f, e in erkannt.items()}


def unsicher(erkannt):
    return [f for f, e in erkannt.items() if e.get("sicherheit") != SICHER]


# ------------------------------------------------------------------ 3. Importprofile
def kopf_schluessel(kopf):
    return "|".join(norm(k) for k in kopf)


def profile(db, einstellung):
    return dict(db.einstellung(einstellung) or {})


def profil_speichern(db, einstellung, name, kopf, spalten, **extra):
    """Importprofil speichern: Spaltenkopf (Erkennung), Spalten je Feld als Nummer und als Spaltenname (andere
    Reihenfolge), dazu extra (z. B. einheit, lieferant, dezimal). Ein vorhandenes Profil gleichen Namens wird
    ersetzt; Zähler und Anlagedatum bleiben."""
    alle = profile(db, einstellung)
    alt = alle.get(name) or {}
    alle[name] = dict(alt, kopf=kopf_schluessel(kopf), spalten={f: int(i) for f, i in spalten.items()},
                      namen={f: norm(kopf[i]) for f, i in spalten.items() if 0 <= int(i) < len(kopf)},
                      angelegt=alt.get("angelegt") or datetime.date.today().isoformat(),
                      geaendert=datetime.date.today().isoformat(), **{k: v for k, v in extra.items()})
    db.einstellung_setzen(einstellung, alle)
    return alle[name]


def profil_loeschen(db, einstellung, name):
    alle = profile(db, einstellung)
    alle.pop(name, None)
    db.einstellung_setzen(einstellung, alle)


def profil_umbenennen(db, einstellung, alt, neu):
    alle = profile(db, einstellung)
    if alt not in alle or not neu or neu in alle:
        return False
    alle[neu] = alle.pop(alt)
    db.einstellung_setzen(einstellung, alle)
    return True


def profil_kopieren(db, einstellung, name, neu=None):
    alle = profile(db, einstellung)
    if name not in alle:
        return None
    neu = neu or f"{name} (Kopie)"
    n = 2
    while neu in alle:
        neu = f"{name} (Kopie {n})"
        n += 1
    alle[neu] = dict(alle[name], angelegt=datetime.date.today().isoformat())
    db.einstellung_setzen(einstellung, alle)
    return neu


def profil_benutzt(db, einstellung, name):
    """Zähler und letzte Nutzung eines Profils (Lernen: häufig benutzte Profile zuerst)."""
    alle = profile(db, einstellung)
    if name in alle:
        alle[name] = dict(alle[name], benutzt=int(alle[name].get("benutzt") or 0) + 1,
                          zuletzt=datetime.date.today().isoformat())
        db.einstellung_setzen(einstellung, alle)


def profil_passend(alle, kopf, lieferant=None):
    """(Name, Profil, {Feld: Spalte}) des passenden Importprofils oder (None, None, None): erst genau gleicher
    Spaltenkopf (bei mehreren das des Lieferanten, sonst das meistbenutzte), dann ein Profil, dessen Spaltennamen
    alle in diesem Kopf vorkommen (andere Reihenfolge oder zusätzliche Spalten) – die Spalten werden dann über den
    Namen neu gesucht."""
    sig = kopf_schluessel(kopf)
    genau = [(n, p) for n, p in alle.items() if p.get("kopf") == sig and
             all(isinstance(i, int) and 0 <= i < len(kopf) for i in (p.get("spalten") or {}).values())]
    if genau:
        genau.sort(key=lambda x: (bool(lieferant) and x[1].get("lieferant") != lieferant,
                                  -int(x[1].get("benutzt") or 0), x[0]))
        n, p = genau[0]
        return n, p, dict(p["spalten"])
    namen = [norm(k) for k in kopf]
    beste = None
    for n, p in alle.items():
        nm = p.get("namen") or {}
        if not nm or len(nm) < len(p.get("spalten") or {}):
            continue
        sp = {}
        for f, w in nm.items():
            if w in namen and namen.count(w) == 1:
                sp[f] = namen.index(w)
        if len(sp) == len(nm) and (beste is None or len(sp) > len(beste[2])):
            beste = (n, p, sp)
    return beste or (None, None, None)


# ------------------------------------------------------------------ 4. Importprotokoll und Rückgängig
TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS material_importe (id INTEGER PRIMARY KEY, zeit TEXT, datei TEXT, importprofil TEXT, "
    "benutzer TEXT, zeilen INTEGER, neu INTEGER, aktualisiert INTEGER, preise INTEGER, unveraendert INTEGER, "
    "doppelt INTEGER, fehler INTEGER, offen INTEGER, status TEXT, protokoll TEXT)",
    "CREATE TABLE IF NOT EXISTS material_import_posten (id INTEGER PRIMARY KEY, import_id INTEGER, tabelle TEXT, "
    "zeilen_id INTEGER, aktion TEXT, alt TEXT, neu TEXT)",
)
ART_MATERIAL, ART_EK, ART_KUNDEN = "Materialstamm/Preise", "EK-Einkäufe", "Kunden"


def einrichten(con):
    from . import db_verbindung
    for sql in TABELLEN_SQL:
        con.execute(sql)
    sp = set(db_verbindung.spalten(con, "material_importe"))
    for name in ("art", "lieferant"):
        if name not in sp:
            con.execute(f"ALTER TABLE material_importe ADD COLUMN {name} TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS material_import_posten_lauf ON material_import_posten (import_id)")


class Lauf:
    """Ein Importlauf: merkt jede Änderung (neu angelegt, geändert mit altem Wert, Zeilen mit dieser Lauf-Nummer)
    und schreibt die Posten gesammelt (flush). neu/aendern gehen über die Datenbank-Funktionen (Verweise,
    Stammdaten-Stand)."""

    def __init__(self, db, import_id):
        self.db, self.id, self._posten = db, import_id, []

    def merken(self, tabelle, zeilen_id, aktion, alt=None, neu=None):
        self._posten.append((self.id, tabelle, zeilen_id, aktion, json.dumps(alt, default=str) if alt else None,
                             json.dumps(neu, default=str) if neu else None))

    def flush(self):
        if self._posten:
            with self.db.con:
                self.db.con.executemany("INSERT INTO material_import_posten (import_id, tabelle, zeilen_id, aktion, "
                                        "alt, neu) VALUES (?, ?, ?, ?, ?, ?)", self._posten)
            self._posten = []

    def neu(self, tabelle, werte):
        i = self.db.neu(tabelle, werte)
        self.merken(tabelle, i, "neu", neu=werte)
        return i

    def aendern(self, tabelle, zeile, werte):
        """Nur die Felder, die sich wirklich ändern; Ergebnis True, wenn etwas geändert wurde."""
        alt = {f: zeile.get(f) for f in werte if zeile.get(f) != werte[f]}
        if not alt:
            return False
        for f in alt:
            self.db.aendern(tabelle, zeile["id"], f, werte[f])
            zeile[f] = werte[f]
        kontext = {f: zeile.get(f) for f in ("profil_id", "werkstoff_id", "lieferant", "basis", "kundennr")
                   if zeile.get(f)}
        self.merken(tabelle, zeile["id"], "geaendert", alt=alt, neu=dict({f: werte[f] for f in alt},
                                                                          _kontext=kontext))
        return True

    def zeilen_mit_lauf(self, tabelle, spalte_name="import_id"):
        """Zeilen, die beim Schreiben die Lauf-Nummer bekommen (z. B. 10.000 EK-Käufe): ein Posten statt einer je
        Zeile; rueckgaengig löscht alle Zeilen dieser Tabelle mit dieser Nummer."""
        self.merken(tabelle, None, "lauf", neu=dict(spalte=spalte_name))


def lauf_beginnen(db, art, datei="", importprofil="", zeilen=0, lieferant="", zaehler=None):
    z = zaehler or {}
    benutzer = db.einstellung("benutzer_name") or ""
    with db.con:
        cur = db.con.execute(
            "INSERT INTO material_importe (zeit, datei, importprofil, benutzer, zeilen, neu, aktualisiert, preise, "
            "unveraendert, doppelt, fehler, offen, status, art, lieferant) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?)",
            (_jetzt(), str(datei), importprofil or "", benutzer, zeilen, 0, 0, 0, z.get("unveraendert", 0),
             z.get("doppelt", 0), z.get("fehler", 0), z.get("offen", 0), "läuft", art, lieferant or ""))
    i = cur.lastrowid if cur.lastrowid else db.con.execute("SELECT MAX(id) FROM material_importe").fetchone()[0]
    return Lauf(db, i)


def lauf_abschliessen(db, lauf, neu=0, aktualisiert=0, preise=0, protokoll=None, status="übernommen"):
    lauf.flush()
    with db.con:
        db.con.execute("UPDATE material_importe SET neu=?, aktualisiert=?, preise=?, status=?, protokoll=? WHERE id=?",
                       (neu, aktualisiert, preise, status, json.dumps(protokoll or {}, default=str), lauf.id))


def laeufe(db, art=None):
    """Importhistorie, neueste zuerst; art = nur diese Importart (Läufe von vor der Spalte art zählen als
    Materialstamm/Preise)."""
    zeilen = [dict(r) for r in db.con.execute("SELECT * FROM material_importe ORDER BY id DESC")]
    for z in zeilen:
        z["art"] = z.get("art") or ART_MATERIAL
    return [z for z in zeilen if art is None or z["art"] == art]


def posten_des_laufs(db, import_id):
    return [dict(r, alt=json.loads(r["alt"]) if r["alt"] else None, neu=json.loads(r["neu"]) if r["neu"] else None)
            for r in db.con.execute("SELECT * FROM material_import_posten WHERE import_id=? ORDER BY id",
                                    (import_id,))]


def rueckgaengig(db, import_id, status="rückgängig gemacht"):
    """Einen Importlauf zurücknehmen: in umgekehrter Reihenfolge neue Zeilen löschen, geänderte Felder auf den alten
    Wert setzen und Zeilen mit der Lauf-Nummer löschen. Später von Hand geänderte Felder werden nicht überschrieben
    (Meldung). Ergebnis: (Anzahl zurückgenommen, [Meldungen])."""
    n, meldungen, je_tabelle = 0, [], {}

    def zeile(tabelle, i):
        if tabelle not in je_tabelle:
            je_tabelle[tabelle] = {z.get("id"): z for z in db.zeilen(tabelle)}
        return je_tabelle[tabelle].get(i)
    for p in reversed(posten_des_laufs(db, import_id)):
        if p["aktion"] == "lauf":
            sp = (p["neu"] or {}).get("spalte") or "import_id"
            with db.con:
                cur = db.con.execute(f'DELETE FROM "{p["tabelle"]}" WHERE "{sp}"=?', (import_id,))
            n += max(cur.rowcount or 0, 0)
            continue
        if p["aktion"] not in ("neu", "geaendert"):
            continue                    # eigene Posten der Importart (z. B. erp_zuordnung), dort zurückgenommen
        z = zeile(p["tabelle"], p["zeilen_id"])
        if z is None:
            continue
        if p["aktion"] == "neu":
            db.loeschen(p["tabelle"], [p["zeilen_id"]])
            je_tabelle[p["tabelle"]].pop(p["zeilen_id"], None)
            n += 1
        else:
            for f, v in (p["alt"] or {}).items():
                if z.get(f) != (p["neu"] or {}).get(f):
                    meldungen.append(f"{p['tabelle']} Zeile {p['zeilen_id']}: {f} inzwischen von Hand geändert, "
                                     "bleibt")
                    continue
                db.aendern(p["tabelle"], p["zeilen_id"], f, v)
                z[f] = v
            n += 1
    with db.con:
        db.con.execute("UPDATE material_importe SET status=? WHERE id=?", (status, import_id))
    return n, meldungen


def fehlerbericht_csv(zeilen, kopf=None):
    """Fehlerbericht als CSV (Semikolon, UTF-8 mit BOM für Excel): zeilen = [(Dateizeile, Gruppe, Grund, [Zellen])]."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Zeile", "Gruppe", "Grund"] + list(kopf or ["Inhalt der Zeile …"]))
    for nr, gruppe, grund, roh in zeilen:
        w.writerow([nr, gruppe, grund] + list(roh or ()))
    return "﻿" + buf.getvalue()
