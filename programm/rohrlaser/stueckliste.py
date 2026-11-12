"""Kunden-Stückliste als Anfrageformular (Roadmap Kalkulation, Phase 1, ERP-001; Freigabe Patrick 12.11.2026).

Eine Stückliste als CSV (Semikolon, Komma oder Tab; Excel „Speichern unter → CSV“) oder als Excel-Datei (.xlsx, erstes
Tabellenblatt) wird wie ein Anfrageformular gelesen: Kopfzeile mit Spalten wie Pos., Artikel-Nr./Zeichnungs-Nr.,
Bezeichnung, Werkstoff, Menge/Anzahl (dieselben Begriffe wie die Tabellen im PDF-Formular, formular.SPALTEN). Die Zeilen
gehen als Tabelle in die Anfrage: Stückzahlen und Werkstoff je Teil werden mit den STEP-Dateien abgeglichen
(Artikelnummer bzw. Dateiname), wie beim PDF-Formular; alles bleibt Vorschlag im Prüfdialog. Eine Spalte Datei/STEP
zählt als Artikel, wenn es keine Artikelspalte gibt. Ohne Qt, ohne zusätzliche Bibliothek."""
import csv
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ENDUNGEN = {".csv", ".xlsx"}
GRUND = "Stückliste (Tabelle)"
DATEI_SPALTE = re.compile(r"datei(?:name)?|step(?:[\s-]*datei)?|file(?:name)?|cad[\s-]*datei|modell", re.I)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _text(roh):
    for kod in ("utf-8-sig", "utf-16") if roh[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1252"):
        try:
            return roh.decode(kod)
        except UnicodeDecodeError:
            continue
    return roh.decode("latin-1")


def csv_zeilen(roh):
    """Zellen einer CSV-Datei [[str]]: Trennzeichen ; , oder Tab (auch 'sep=;' in Zeile 1)."""
    text = _text(roh)
    erste = text.split("\n", 1)[0].strip()
    if erste.lower().startswith("sep=") and len(erste) >= 5:
        trenner, text = erste[4], text.split("\n", 1)[1] if "\n" in text else ""
    else:
        probe = "\n".join(text.splitlines()[:20])
        trenner = max((";", "\t", ","), key=lambda t: probe.count(t))
    return [[z.strip() for z in r] for r in csv.reader(io.StringIO(text), delimiter=trenner)]


def _spalte_nr(ref):
    n = 0
    for c in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(c) - 64
    return n - 1


def xlsx_zeilen(roh):
    """Zellen des ersten Tabellenblatts einer .xlsx [[str]] (Texte, Zahlen; Formeln mit ihrem letzten Wert)."""
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        texte = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                texte.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        blatt = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if not blatt:
            return []
        wurzel = ElementTree.fromstring(z.read("xl/worksheets/sheet1.xml" if "xl/worksheets/sheet1.xml" in blatt
                                               else blatt[0]))
    out = []
    for r in wurzel.iter(f"{{{NS['m']}}}row"):
        zeile = []
        for c in r.findall("m:c", NS):
            i = _spalte_nr(c.get("r", "A1")) if c.get("r") else len(zeile)
            v = c.find("m:v", NS)
            t = c.get("t")
            if t == "s" and v is not None:
                wert = texte[int(v.text)] if v.text and int(v.text) < len(texte) else ""
            elif t == "inlineStr":
                wert = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
            else:
                wert = v.text if v is not None and v.text is not None else ""
                if re.fullmatch(r"-?\d+\.0+", wert):
                    wert = wert.split(".")[0]
            while len(zeile) < i:
                zeile.append("")
            zeile.append(str(wert).strip())
        out.append(zeile)
    return out


def zellen(pfad):
    """Zellen der Datei [[str]] oder None (nicht lesbar)."""
    pfad = Path(pfad)
    try:
        roh = pfad.read_bytes()
        return xlsx_zeilen(roh) if pfad.suffix.lower() == ".xlsx" else csv_zeilen(roh)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError, csv.Error):
        return None


def tabelle(zeilen):
    """Positionen [dict(pos, artikel, bezeichnung, werkstoff, menge, me, text)] wie formular.tabelle: Kopf = erste
    Zeile mit mindestens zwei erkannten Spalten, darunter Menge oder Artikel (bzw. Datei). [] ohne Kopf."""
    from .formular import TABELLE_ENDE, _spalte
    for i, z in enumerate(zeilen or ()):
        kopf = {}
        for j, zelle in enumerate(z):
            n = _spalte(zelle) or ("datei" if DATEI_SPALTE.fullmatch(zelle.strip().strip(":")) else None)
            if n and n not in kopf.values():
                kopf[j] = n
        if len(kopf) < 2 or not ({"menge", "artikel", "datei"} & set(kopf.values())):
            continue
        out = []
        for r in zeilen[i + 1:]:
            text = " ".join(x for x in r if x)
            if not text:
                continue
            if TABELLE_ENDE.match(text):
                break
            werte = {n: r[j].strip() for j, n in kopf.items() if j < len(r) and r[j].strip()}
            if "datei" in werte:
                d = werte.pop("datei")
                werte.setdefault("artikel", Path(d).stem if Path(d).suffix else d)
            if werte:
                out.append(dict(werte, text=text))
        return out
    return []


def lesen(pfad):
    """dict wie pdf_art.lesen (eine Seite, Art Formular, Tabelle direkt) oder None."""
    from . import pdf_art
    z = zellen(pfad)
    rows = tabelle(z) if z else []
    if not rows:
        return None
    # Text je Zeile „Artikel Bezeichnung Werkstoff 20 Stk“, damit auch die Zeilenlogik des Formulars greift
    text = "\n".join(" ".join(x for x in (r.get("pos"), r.get("artikel"), r.get("bezeichnung"), r.get("werkstoff"))
                              if x) + (f" {r['menge']} Stk" if r.get("menge") else "") for r in rows)
    seite = dict(nr=1, text=text, segmente=[], ocr=False, unsicher=set(), linien=0, art=pdf_art.FORMULAR,
                 grund=GRUND, tabelle_direkt=rows)
    return pdf_art.zusammen(dict(datei=Path(pfad).name, seiten=[seite], ocr=False))
