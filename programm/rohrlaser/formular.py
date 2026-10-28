"""Anfrageformular lesen (Plan W6b, Patrick 25.10.2026): Text aus einem PDF mit Text (aus ERP oder Word erzeugt) holen
und daraus Anfragenummer, Kunde und Stückzahlen je Artikelnummer lesen. Scans (PDF ohne Text, Bilder) liest ocr.py
mit Tesseract (W6c); deren Text geht durch dieselbe Auswertung. Es gibt keine Beispielformulare: die Erkennung sucht allgemein
nach Begriffen wie „Anfrage-Nr.“, „Menge“, „Stück“ und gleicht Artikelnummern mit den STEP-Dateien ab. Ergebnisse
sind Vorschläge, der Prüfdialog zeigt sie zum Bestätigen. Ohne Qt."""
import re
import unicodedata
from pathlib import Path

from . import protokoll

# „Anfrage-Nr.: A-4711“, „Anfragenummer 2026/123“, „Bestellnummer …“, „Projekt-Nr.“, „RFQ No.“
NUMMER_WOERTER = (r"anfrage[\s-]*(?:nr|nummer|no)?\.?|anfragenummer|unsere\s+anfrage|bestell[\s-]*(?:nr|nummer)\.?|"
                  r"projekt[\s-]*(?:nr|nummer)\.?|rfq(?:[\s-]*(?:no|nr))?\.?|request(?:\s+no)?\.?|inquiry(?:\s+no)?\.?")
NUMMER = re.compile(rf"(?:{NUMMER_WOERTER})\s*[:#.]?\s*([A-Z0-9][A-Z0-9/_.-]{{2,30}})", re.I)
STUECK = re.compile(r"(?<![\d,.])(\d{1,6})(?:[,.]0+)?\s*(?:stk|stück|stuck|stck|st|sk|5tk|pcs|pc|x)\b\.?", re.I)
ZAHL = re.compile(r"(?<![\w,./-])(\d{1,6})(?:[,.]0+)?(?![\w,./-])")
KOPF_MENGE = re.compile(r"\b(menge|stück|stk|anzahl|qty|quantity)\b", re.I)


def ohne_zeichen(text, ocr=False):
    """Vergleichsform: Kleinbuchstaben und Ziffern, alles andere weg ('MG-01 Stiel.stp' -> 'mg01stielstp'). ocr: dazu
    Zeichen, die Tesseract leicht verwechselt, gleichsetzen (O/Q/0, I/l/1, S/5, B/8, Z/2, A/4, G/6)."""
    s = re.sub(r"[^0-9a-zäöüß]+", "", unicodedata.normalize("NFC", str(text or "")).lower())
    return s.translate(OCR_GLEICH) if ocr else s


OCR_GLEICH = str.maketrans("oqilsbzag", "001158246")


def pdf_text(pfad):
    """Text aller Seiten eines PDFs ('' = kein Text, z. B. Scan, oder nicht lesbar)."""
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(pfad))
    except Exception as e:  # noqa: BLE001 – kaputte oder verschlüsselte Datei: wie ohne Text
        protokoll.nebenbei(e, "PDF-Formular öffnen")
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


def _schluessel(name, ocr=False):
    s = Path(str(name or "")).name
    s = re.sub(r"\.(step|stp)$", "", s, flags=re.I)
    return ohne_zeichen(s, ocr)


def stueckzahlen(text, namen, ocr=False, unsicher=()):
    """Stückzahl je Name (STEP-Dateiname oder Artikelnummer) aus dem Text: eine Zeile, die den Namen enthält (ohne
    Leer- und Sonderzeichen verglichen), mit „20 Stk“ (sicher) oder sonst einer einzelnen Zahl, die nicht zum Namen
    gehört (unsicher; Positionsnummern 10, 20 … am Zeilenanfang zählen nicht). ocr (Text aus einem Scan): Namen mit
    verwechselbaren Zeichen gleichsetzen und, wo kein genauer Treffer ist, je 10 Zeichen ein falsches Zeichen
    erlauben (nur in Zeilen ohne genauen Treffer eines anderen Namens); unsicher = Wörter, die Tesseract nur unsicher
    erkannt hat (Menge daraus gilt als unsicher). Ergebnis {Name: (Menge, sicher)}."""
    zeilen = [z for z in (text or "").split("\n") if z.strip()]
    form = [ohne_zeichen(z, ocr) for z in zeilen]
    menge_spalte = any(KOPF_MENGE.search(z) for z in zeilen)
    schluessel = {n: _schluessel(n, ocr) for n in namen}
    schluessel = {n: k for n, k in schluessel.items() if len(k) >= 3}
    out, belegt = {}, set()
    for name, schl in schluessel.items():           # genaue Treffer
        for i, z in enumerate(zeilen):
            if schl in form[i]:
                belegt.add(i)
                w = _menge(_ohne_name(z, name) if not ocr else _ohne_name_ocr(z, schl), menge_spalte, unsicher)
                if w:
                    out[name] = w
                    break
    if ocr:                                         # Lesefehler im Namen (Scan)
        for name, schl in schluessel.items():
            fehler = len(schl) // 10
            if name in out or not fehler:
                continue
            for i, z in enumerate(zeilen):
                if i not in belegt and _abstand(schl, form[i]) <= fehler:
                    w = _menge(_ohne_name_ocr(z, schl, fehler), menge_spalte, unsicher)
                    if w:
                        out[name] = (w[0], False)
                        break
    return out


def _menge(rest, menge_spalte, unsicher):
    """(Menge, sicher) aus dem Rest einer Zeile oder None."""
    m = STUECK.search(rest)
    if m and int(m.group(1)) > 0:
        return int(m.group(1)), m.group(1) not in unsicher
    zahlen = [int(x) for x in ZAHL.findall(rest) if int(x) > 0]
    if zahlen and re.match(r"\s*\d{1,4}\b", rest) and len(zahlen) > 1:
        zahlen = zahlen[1:]          # erste Zahl am Zeilenanfang = Positionsnummer
    if zahlen:
        return (zahlen[-1] if menge_spalte else zahlen[0]), False
    return None


def _abstand(muster, text):
    """Kleinste Zahl falscher, fehlender oder zusätzlicher Zeichen, mit der muster irgendwo in text steht."""
    vorher = [0] * (len(text) + 1)
    for i, c in enumerate(muster, 1):
        jetzt = [i] + [0] * len(text)
        for j, t in enumerate(text, 1):
            jetzt[j] = min(vorher[j - 1] + (c != t), vorher[j] + 1, jetzt[j - 1] + 1)
        vorher = jetzt
    return min(vorher)


def _ohne_name(zeile, name):
    """Zeile ohne den Namen selbst (damit 'MG-01' keine 1 als Menge liefert); Vergleich ohne Sonderzeichen."""
    roh = Path(str(name)).stem
    teile = [t for t in re.split(r"[\s_.-]+", roh) if t]
    muster = r"[\s_.-]*".join(map(re.escape, teile))
    return re.sub(muster, " ", zeile, count=1, flags=re.I) if muster else zeile


def stueck_aus(formulare, namen):
    """Stückzahlen aus mehreren gelesenen Formularen (dict text, ocr, unsicher): sichere Werte gehen vor."""
    gesamt = {}
    for f in formulare or ():
        for n, w in stueckzahlen(f.get("text"), namen, f.get("ocr", False), f.get("unsicher", ())).items():
            if n not in gesamt or (w[1] and not gesamt[n][1]):
                gesamt[n] = w
    return gesamt


def _ohne_name_ocr(zeile, schl, fehler=0):
    """Wie _ohne_name für Scan-Text: die Wörter weglassen, die zusammen den Namen (OCR-Vergleichsform) ergeben, mit
    höchstens fehler falschen Zeichen."""
    woerter = zeile.split()
    form = [ohne_zeichen(w, True) for w in woerter]
    for i in range(len(woerter)):
        zusammen = ""
        for j in range(i, len(woerter)):
            zusammen += form[j]
            if schl in zusammen or (fehler and _abstand(schl, zusammen) <= fehler):
                return " ".join(woerter[:i] + [" "] + woerter[j + 1:])
            if len(zusammen) > len(schl) + 20:
                break
    return zeile


def auswerten(text, kunden=(), namen=(), eigene=(), ocr=False, unsicher=()):
    """Alles aus einem Formular: dict(nummer, kunde, stueck {Name: (Menge, sicher)}, text_da). ocr/unsicher: Text aus
    einem Scan (siehe stueckzahlen)."""
    return dict(nummer=anfragenummer(text), kunde=kunde(text, kunden, eigene),
                stueck=stueckzahlen(text, namen, ocr, unsicher), text_da=bool((text or "").strip()))


def datei_lesen(pfad, programmordner=None):
    """Ein Formular lesen: PDF mit Text direkt, Scan-PDF und Bilder mit Tesseract (ocr.py, W6c). Ergebnis dict(text,
    ocr, unsicher) oder None (nicht lesbar, kein Tesseract)."""
    pfad = Path(pfad)
    if pfad.suffix.lower() == ".pdf":
        text = pdf_text(pfad)
        if text.strip():
            return dict(text=text, ocr=False, unsicher=set())
    from . import ocr
    erg = ocr.lesen(pfad, programmordner)
    return dict(erg, ocr=True) if erg and erg["text"].strip() else None


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
