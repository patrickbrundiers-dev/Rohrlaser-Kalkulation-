"""Anfrageformular lesen (Plan W6b, Patrick 25.10.2026): Text aus einem PDF mit Text (aus ERP oder Word erzeugt) holen
und daraus Anfragenummer, Kunde und Stückzahlen je Artikelnummer lesen. Scans (PDF ohne Text, Bilder) liest W6c mit
Tesseract; deren Text geht durch dieselbe Auswertung. Es gibt keine Beispielformulare: die Erkennung sucht allgemein
nach Begriffen wie „Anfrage-Nr.“, „Menge“, „Stück“ und gleicht Artikelnummern mit den STEP-Dateien ab. Ergebnisse
sind Vorschläge, der Prüfdialog zeigt sie zum Bestätigen. Ohne Qt."""
import re
from pathlib import Path

# „Anfrage-Nr.: A-4711“, „Anfragenummer 2026/123“, „Bestellnummer …“, „Projekt-Nr.“, „RFQ No.“
NUMMER_WOERTER = (r"anfrage[\s-]*(?:nr|nummer|no)?\.?|anfragenummer|unsere\s+anfrage|bestell[\s-]*(?:nr|nummer)\.?|"
                  r"projekt[\s-]*(?:nr|nummer)\.?|rfq(?:[\s-]*(?:no|nr))?\.?|request(?:\s+no)?\.?|inquiry(?:\s+no)?\.?")
NUMMER = re.compile(rf"(?:{NUMMER_WOERTER})\s*[:#.]?\s*([A-Z0-9][A-Z0-9/_.-]{{2,30}})", re.I)
STUECK = re.compile(r"(?<![\d,.])(\d{1,6})(?:[,.]0+)?\s*(?:stk|stück|stck|st|pcs|pc|x)\b\.?", re.I)
ZAHL = re.compile(r"(?<![\w,./-])(\d{1,6})(?:[,.]0+)?(?![\w,./-])")
KOPF_MENGE = re.compile(r"\b(menge|stück|stk|anzahl|qty|quantity)\b", re.I)


def ohne_zeichen(text):
    """Vergleichsform: Kleinbuchstaben und Ziffern, alles andere weg ('MG-01 Stiel.stp' -> 'mg01stielstp')."""
    return re.sub(r"[^0-9a-zäöüß]+", "", str(text or "").lower())


def pdf_text(pfad):
    """Text aller Seiten eines PDFs ('' = kein Text, z. B. Scan, oder nicht lesbar)."""
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(pfad))
    except Exception:           # kaputte oder verschlüsselte Datei: wie ohne Text
        return ""
    try:
        seiten = []
        for i in range(len(pdf)):
            seite = pdf[i]
            tp = seite.get_textpage()
            seiten.append(tp.get_text_range())
            tp.close()
            seite.close()
        return "\n".join(seiten).replace("\r\n", "\n").replace("\r", "\n")
    finally:
        pdf.close()


def anfragenummer(text):
    """Erste Anfrage-/Bestell-/Projektnummer im Text oder None."""
    for m in NUMMER.finditer(text or ""):
        nr = m.group(1).strip(".-/_")
        if any(c.isdigit() for c in nr) and len(nr) >= 3:
            return nr
    return None


def kunde(text, kunden, eigene=()):
    """Kundennummer, deren Name (ab 4 Zeichen) im Text steht, längster Name zuerst; eigene = Namen der eigenen Firma
    (Briefkopf), die nie als Kunde gelten. Sonst None."""
    t = ohne_zeichen(text)
    eigen = {ohne_zeichen(e) for e in eigene if e}
    treffer = [(len(n), k["kundennr"]) for k in kunden or ()
               if len(n := ohne_zeichen(k.get("name"))) >= 4 and n in t and n not in eigen]
    return max(treffer)[1] if treffer else None


def _schluessel(name):
    s = Path(str(name or "")).name
    s = re.sub(r"\.(step|stp)$", "", s, flags=re.I)
    return ohne_zeichen(s)


def stueckzahlen(text, namen):
    """Stückzahl je Name (STEP-Dateiname oder Artikelnummer) aus dem Text: eine Zeile, die den Namen enthält (ohne
    Leer- und Sonderzeichen verglichen), mit „20 Stk“ (sicher) oder sonst einer einzelnen Zahl, die nicht zum Namen
    gehört (unsicher; Positionsnummern 10, 20 … am Zeilenanfang zählen nicht). Ergebnis {Name: (Menge, sicher)}."""
    zeilen = [z for z in (text or "").split("\n") if z.strip()]
    menge_spalte = any(KOPF_MENGE.search(z) for z in zeilen)
    out = {}
    for name in namen:
        schl = _schluessel(name)
        if len(schl) < 3:
            continue
        for z in zeilen:
            if schl not in ohne_zeichen(z):
                continue
            rest = _ohne_name(z, name)
            m = STUECK.search(rest)
            if m and int(m.group(1)) > 0:
                out[name] = (int(m.group(1)), True)
                break
            zahlen = [int(x) for x in ZAHL.findall(rest) if int(x) > 0]
            if zahlen and re.match(r"\s*\d{1,4}\b", rest) and len(zahlen) > 1:
                zahlen = zahlen[1:]          # erste Zahl am Zeilenanfang = Positionsnummer
            if zahlen:
                out[name] = (zahlen[-1] if menge_spalte else zahlen[0], False)
                break
    return out


def _ohne_name(zeile, name):
    """Zeile ohne den Namen selbst (damit 'MG-01' keine 1 als Menge liefert); Vergleich ohne Sonderzeichen."""
    roh = Path(str(name)).stem
    teile = [t for t in re.split(r"[\s_.-]+", roh) if t]
    muster = r"[\s_.-]*".join(map(re.escape, teile))
    return re.sub(muster, " ", zeile, count=1, flags=re.I) if muster else zeile


def auswerten(text, kunden=(), namen=(), eigene=()):
    """Alles aus einem Formular: dict(nummer, kunde, stueck {Name: (Menge, sicher)}, text_da)."""
    return dict(nummer=anfragenummer(text), kunde=kunde(text, kunden, eigene), stueck=stueckzahlen(text, namen),
                text_da=bool((text or "").strip()))


def lesen(dateien, kunden=(), namen=(), eigene=()):
    """Formulare (PDF mit Text) einer Anfrage lesen und zusammenfassen; erste gefundene Nummer/Kunde gilt, Stückzahlen
    aus allen. Ergebnis wie auswerten, dazu ohne_text = Formulare ohne Text (Scans, Bilder; W6c)."""
    gesamt = dict(nummer=None, kunde=None, stueck={}, text_da=False, ohne_text=[])
    for d in dateien:
        text = pdf_text(d) if Path(d).suffix.lower() == ".pdf" else ""
        if not text.strip():
            gesamt["ohne_text"].append(Path(d))
            continue
        e = auswerten(text, kunden, namen, eigene)
        gesamt["nummer"] = gesamt["nummer"] or e["nummer"]
        gesamt["kunde"] = gesamt["kunde"] or e["kunde"]
        for n, w in e["stueck"].items():
            if n not in gesamt["stueck"] or (w[1] and not gesamt["stueck"][n][1]):
                gesamt["stueck"][n] = w
        gesamt["text_da"] = True
    return gesamt


def stueck_setzen(messwerte, stueck):
    """Stückzahlen aus dem Formular in die Messwerte (vor dem Prüfdialog): Abgleich über Dateiname und Artikelnummer
    (Bauteilname). Ein Satz (_saetze) bleibt unberührt. Setzt _stueck und _stueck_formular (True = sicher, False =
    unsicher). Ergebnis: Anzahl gesetzter Teile."""
    je = {_schluessel(n): w for n, w in (stueck or {}).items()}
    n = 0
    for m in messwerte:
        if m.get("_saetze"):
            continue
        for kandidat in (m.get("artikel"), m.get("datei")):
            w = je.get(_schluessel(kandidat)) if kandidat else None
            if w:
                m["_stueck"], m["_stueck_formular"] = w[0], w[1]
                n += 1
                break
    return n
