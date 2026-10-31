"""Anfrageformular lesen (Plan W6b, Patrick 25.10.2026): Text aus einem PDF mit Text (aus ERP oder Word erzeugt) holen
und daraus Anfragenummer, Kunde und Stückzahlen je Artikelnummer lesen. Scans (PDF ohne Text, Bilder) liest ocr.py
mit Tesseract (W6c); deren Text geht durch dieselbe Auswertung. Es gibt keine Beispielformulare: die Erkennung sucht allgemein
nach Begriffen wie „Anfrage-Nr.“, „Menge“, „Stück“ und gleicht Artikelnummern mit den STEP-Dateien ab. Ergebnisse
sind Vorschläge, der Prüfdialog zeigt sie zum Bestätigen. Ohne Qt."""
import re
import unicodedata
from pathlib import Path

# „Anfrage-Nr.: A-4711“, „Anfragenummer 2026/123“, „Bestellnummer …“, „Projekt-Nr.“, „RFQ No.“
NUMMER_WOERTER = (r"anfrage[\s-]*(?:nr|nummer|no)?\.?|anfragenummer|unsere\s+anfrage|bestell[\s-]*(?:nr|nummer)\.?|"
                  r"projekt[\s-]*(?:nr|nummer)\.?|rfq(?:[\s-]*(?:no|nr))?\.?|request(?:\s+no)?\.?|inquiry(?:\s+no)?\.?|"
                  # 31.10.2026 (Patrick „PDF-Formular besser auswerten“): weitere Bezeichnungen aus ERP-Formularen
                  r"beleg[\s-]*(?:nr|nummer|no)\.?|belegnummer|vorgang(?:s)?[\s-]*(?:nr|nummer)?\.?|"
                  r"unser\s+zeichen|bestellanfrage[\s-]*(?:nr|nummer)?\.?")
NUMMER = re.compile(rf"(?:{NUMMER_WOERTER})\s*[:#.]?\s*([A-Z0-9][A-Z0-9/_.-]{{2,30}})", re.I)
# Menge: auch mit Tausenderpunkt („1.000 Stk“ = 1000) und Nachkommastellen aus dem ERP („20,000 ST“ = 20)
_MENGE = r"(\d{1,3}(?:\.\d{3})+|\d{1,6})(?:,0+)?"
STUECK = re.compile(rf"(?<![\d,.]){_MENGE}\s*(?:stk|stück|stuck|stck|st|sk|5tk|pcs|pc|x|ea)\b\.?", re.I)
ZAHL = re.compile(rf"(?<![\w,./-]){_MENGE}(?![\w,/-]|\.\d)")
LAENGE_DAVOR = re.compile(r"(?:l\s*=|länge|laenge|lg\.?|x)\s*$", re.I)
LAENGE_DANACH = re.compile(r"^\s*(?:mm|cm|m\b|°)", re.I)
DATUM = re.compile(r"^\d{1,2}\.\d{1,2}\.(?:\d{2}|\d{4})$")
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


def _nummer_ok(nr):
    """Kann das eine Anfrage-Nr. sein? Mit Ziffer, ab 3 Zeichen, kein Datum."""
    nr = (nr or "").strip(".-/_:")
    return nr if len(nr) >= 3 and any(c.isdigit() for c in nr) and not DATUM.match(nr) else None


def anfragenummer(text):
    """Erste Anfrage-/Bestell-/Projektnummer im Text oder None. Treffer dürfen sich überlappen: in
    „Angebotsanfrage⏎Anfrage-Nr.: A-1“ zählt die zweite Stelle, wenn die erste keine Nummer hat. Steht die Beschriftung
    in einer Kopfzeile („Anfrage-Nr.   Datum   Kunden-Nr.“) und der Wert in der Zeile darunter, zählt die Spalte
    darunter (31.10.2026). Ein Datum ist nie die Anfrage-Nr."""
    text, pos = text or "", 0
    while (m := NUMMER.search(text, pos)):
        if (nr := _nummer_ok(m.group(1))) and not re.match(r"\s*(?:vom|from|v\.)\b", text[m.end(1):], re.I):
            return nr
        pos = m.start() + 1
    zeilen = text.split("\n")
    for i, z in enumerate(zeilen[:-1]):
        kopf = [c.strip() for c in re.split(r"\t|\s{2,}", z.strip())]
        if len(kopf) < 2:
            continue
        for j, c in enumerate(kopf):
            if re.fullmatch(rf"(?:{NUMMER_WOERTER})\s*:?", c, re.I):
                werte = [w.strip() for w in re.split(r"\t|\s{2,}", zeilen[i + 1].strip())]
                if len(werte) == len(kopf) and (nr := _nummer_ok(werte[j])):
                    return nr
    return None


def nummer_aus_segmenten(segmente):
    """Anfrage-Nr. aus der Lage der Textstücke (PDF-Formular, Scan): Beschriftung „Anfrage-Nr.“ allein in einem Feld,
    der Wert rechts daneben in derselben Zeile oder direkt darunter in derselben Spalte. Sonst None."""
    seg = [s for s in segmente or () if (s.get("text") or "").strip()]
    for b in seg:
        if not re.fullmatch(rf"(?:{NUMMER_WOERTER})\s*:?", b["text"].strip(), re.I):
            continue
        h = max(b["y1"] - b["y0"], 1)
        rechts = [s for s in seg if s is not b and abs((s["y0"] + s["y1"]) / 2 - (b["y0"] + b["y1"]) / 2) < h * 0.6
                  and s["x0"] >= b["x1"] - h * 0.5]
        unten = [s for s in seg if s is not b and 0 < s["y0"] - b["y0"] < h * 3.5
                 and min(s["x1"], b["x1"]) - max(s["x0"], b["x0"]) > 0]
        for kand in (sorted(rechts, key=lambda s: s["x0"])[:1], sorted(unten, key=lambda s: s["y0"])[:1]):
            for s in kand:
                if nr := _nummer_ok(s["text"].split()[0] if s["text"].split() else ""):
                    return nr
    return None


def nummer_aus(gelesen):
    """Anfrage-Nr. aus gelesenen Formularen: erst über die Lage der Textstücke der Formularseiten, dann aus dem Text."""
    for g in gelesen or ():
        for s in g.get("seiten") or ():
            if s.get("art") != "Zeichnung" and (nr := nummer_aus_segmenten(s.get("segmente"))):
                return nr
    return anfragenummer("\n".join(g.get("text") or "" for g in gelesen or ()))


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
                rest = _ohne_name(z, name) if not ocr else _ohne_name_ocr(z, schl)
                w = _menge(rest, menge_spalte, unsicher, _pos_vorn(z, schl, ocr))
                if w is None and not ocr:   # Menge eine Zeile tiefer (mehrzeilige Zelle, 31.10.2026)
                    for z2 in zeilen[i + 1:i + 3]:
                        if any(k in ohne_zeichen(z2) for k in schluessel.values()):
                            break
                        if (m2 := STUECK.search(z2)) and (n2 := menge_zahl(m2.group(1))):
                            w = (n2, False)
                            break
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


def menge_zahl(t):
    """Ganze Stückzahl aus „20“, „1.000“, „20,000“, „1.000,00“; sonst None (auch 0)."""
    t = str(t or "").strip()
    m = re.fullmatch(r"(\d{1,3}(?:\.\d{3})+|\d{1,6})(?:,(\d+))?", t)
    if not m or (m.group(2) and set(m.group(2)) != {"0"}):
        return None
    n = int(m.group(1).replace(".", ""))
    return n or None


def _menge(rest, menge_spalte, unsicher, pos=False):
    """(Menge, sicher) aus dem Rest einer Zeile oder None. pos: die Zeile beginnt mit einer Positionsnummer (vor dem
    Namen), die erste Zahl zählt dann nie. Abmessungen und Längen (40x40x3, L=1250, 1250 mm) sind nie die Menge."""
    m = STUECK.search(rest)
    if m and (n := menge_zahl(m.group(1))):
        return n, m.group(1) not in unsicher
    zahlen = [(n, z.start()) for z in ZAHL.finditer(rest) if (n := menge_zahl(z.group(1)))
              and not LAENGE_DAVOR.search(rest[:z.start()]) and not LAENGE_DANACH.match(rest[z.end():])]
    vorn = bool(zahlen) and not rest[:zahlen[0][1]].strip()
    if vorn and (pos or len(zahlen) > 1):
        zahlen = zahlen[1:]          # erste Zahl am Zeilenanfang = Positionsnummer
    if not zahlen:
        return None
    if menge_spalte:
        return zahlen[-1][0], False
    # ohne Mengenspalte: erste Zahl, außer sie ist vierstellig und es folgt eine kleinere (Länge vor Menge)
    return (zahlen[-1][0] if len(zahlen) > 1 and zahlen[0][0] >= 1000 > zahlen[-1][0] else zahlen[0][0]), False


def _pos_vorn(zeile, schl, ocr=False):
    """Beginnt die Zeile mit einer Positionsnummer (1–4 Ziffern), die nicht zum Namen gehört?"""
    m = re.match(r"\s*(\d{1,4})[\s.)]+\S", zeile)
    return bool(m) and not schl.startswith(ohne_zeichen(m.group(1), ocr))


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
        tab = stueck_tabelle(f.get("tabelle") or [], namen)      # Tabelle über die Lage (31.10.2026) geht vor
        for n, w in list(tab.items()) + list(stueckzahlen(f.get("text"), namen, f.get("ocr", False),
                                                          f.get("unsicher", ())).items()):
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
    ocr, unsicher) oder None (nicht lesbar, kein Tesseract). Jede Seite wird eingeordnet (pdf_art, 28.10.2026): text
    nur aus Formular- und unklaren Seiten, Zeichnungsseiten liefern nur ihr Schriftfeld (zeichnungen); dazu datei,
    seiten und wahl für den Prüfdialog."""
    from . import pdf_art
    return pdf_art.lesen(pfad, programmordner)


def stueck_setzen(messwerte, stueck):
    """Stückzahlen aus dem Formular in die Messwerte (vor dem Prüfdialog): Abgleich über Dateiname und Artikelnummer
    (Bauteilname). Ein Satz (_saetze) bleibt unberührt. Setzt _stueck und _stueck_formular (True = sicher, False =
    unsicher). Ergebnis: Anzahl gesetzter Teile."""
    je = {_schluessel(n): w for n, w in (stueck or {}).items()}
    n = 0
    for m in messwerte:
        if m.get("_saetze"):
            continue
        for kandidat in (m.get("artikel"), m.get("bauteil"), m.get("datei")):     # Bauteilname auch unbereinigt
            w = je.get(_schluessel(kandidat)) if kandidat else None
            if w:
                m["_stueck"], m["_stueck_formular"] = w[0], w[1]
                n += 1
                break
    return n


# ---------------------------------------------------------------- Tabelle über die Lage lesen (31.10.2026)
# Patrick „PDF-Formular besser auswerten: Anfragenummer, Stückzahlen, Werkstoff“ (Freigabe „Alle Empfehlungen“):
# Textstücke mit Lage (PDF mit Text: pypdfium2, Scan: Tesseract) zu Zeilen bündeln, Spalten über die Kopfzeile
# zuordnen, mehrzeilige Zellen zusammenfügen. Ohne erkennbaren Tabellenkopf bleibt es bei der Zeilenlogik oben.

SPALTEN = (   # Reihenfolge = Vorrang (Material-Nr. ist eine Artikelnummer, Material allein der Werkstoff)
    ("pos", r"pos(?:ition)?\.?|lfd\.?\s*(?:nr\.?)?|item|nr\.?"),
    ("artikel", r"(?:art(?:ikel)?|teile?|sach|material|zeichnungs?|zeichn|ident|part|drawing|kunden[\s-]*art(?:ikel)?)"
                r"[\s.-]*(?:nr|nummer|no|number)\.?|zeichnung|ident|artikel|teil"),
    ("werkstoff", r"werkstoff|material|güte|guete|qualität|qualitaet|grade|werkst\.?"),
    ("menge", r"menge|anzahl|stückzahl|stueckzahl|stück|stueck|stk\.?|qty|quantity|anz\.?|bedarf"),
    ("me", r"me|einheit|unit|eh|mengeneinheit"),
    ("bezeichnung", r"bezeichnung|benennung|beschreibung|text|description|artikelbezeichnung|abmessung|kurztext"),
)
TABELLE_ENDE = re.compile(r"^\s*(?:summe|gesamt|total|zwischensumme|mit\s+freundlichen|freundliche\s+grü|bitte|"
                          r"lieferbedingung|zahlungsbedingung|seite\s+\d)", re.I)


def _spalte(text):
    t = re.sub(r"\s+", " ", (text or "").strip().lower()).strip(" :")
    for name, muster in SPALTEN:
        if re.fullmatch(muster, t):
            return name
    return None


def _zeilen(segmente):
    """Textstücke zu Zeilen (oben nach unten), jede Zeile links nach rechts."""
    seg = sorted((s for s in segmente or () if (s.get("text") or "").strip()), key=lambda s: (s["y0"] + s["y1"]) / 2)
    if not seg:
        return []
    hoehen = sorted(max(s["y1"] - s["y0"], 1) for s in seg)
    h = hoehen[len(hoehen) // 2]
    zeilen, mitte = [], None
    for s in seg:
        m = (s["y0"] + s["y1"]) / 2
        if zeilen and abs(m - mitte) <= h * 0.5:
            zeilen[-1].append(s)
        else:
            zeilen.append([s])
            mitte = m
    return [sorted(z, key=lambda s: s["x0"]) for z in zeilen]


def tabelle(segmente):
    """Positionen einer Tabelle mit Kopfzeile: [dict(pos, artikel, bezeichnung, werkstoff, menge, me, text)] (nur
    gefundene Spalten). Kopf = Zeile mit mindestens zwei erkannten Spalten, darunter Menge oder Artikel. Eine Zeile
    ohne Pos., Artikel und Menge gehört zur Position darüber (mehrzeilige Zelle). [] ohne Tabelle."""
    zeilen, out = _zeilen(segmente), []
    i = 0
    while i < len(zeilen):
        kopf = {}
        for s in zeilen[i]:
            if (n := _spalte(s["text"])) and n not in kopf:
                kopf[n] = s
        if len(kopf) < 2 or not ({"menge", "artikel"} & set(kopf)):
            i += 1
            continue
        spalten = sorted(kopf.items(), key=lambda kv: kv[1]["x0"])
        grenzen = []        # Spaltengrenze = Mitte zwischen Kopfende und nächstem Kopfanfang
        for j, (n, s) in enumerate(spalten):
            links = -1e9 if j == 0 else (spalten[j - 1][1]["x1"] + s["x0"]) / 2
            rechts = 1e9 if j == len(spalten) - 1 else (s["x1"] + spalten[j + 1][1]["x0"]) / 2
            grenzen.append((n, links, rechts))
        aktuell = None
        for z in zeilen[i + 1:]:
            text = " ".join(s["text"].strip() for s in z)
            if TABELLE_ENDE.match(text) or sum(1 for s in z if _spalte(s["text"])) >= 2:
                break
            werte = {}
            for s in z:
                for wort, mitte in _woerter(s, grenzen):
                    n = next((n for n, lo, hi in grenzen if lo <= mitte < hi), grenzen[-1][0])
                    werte[n] = (werte.get(n, "") + " " + wort).strip()
            neu = any(werte.get(k) for k in ("pos", "artikel")) or (
                _menge_zelle(werte.get("menge")) and (aktuell is None or _menge_zelle(aktuell.get("menge"))))
            if neu or aktuell is None:
                aktuell = dict(werte, text=text)
                out.append(aktuell)
            else:
                for k, v in werte.items():
                    aktuell[k] = (aktuell.get(k, "") + " " + v).strip()
                aktuell["text"] += " " + text
        break               # eine Tabelle je Seite
    return out


def _woerter(s, grenzen):
    """[(Text, Mitte)] eines Textstücks: liegt es über mehreren Spalten (Scan: Wörter mit kleiner Lücke zusammen),
    werden seine Wörter einzeln eingeordnet, ihre Lage geschätzt nach der Stelle im Text."""
    text = s["text"].strip()
    if not any(s["x0"] < lo < s["x1"] - 1 for _, lo, _ in grenzen if lo > -1e8):
        return [(text, (s["x0"] + s["x1"]) / 2)]
    out, breite = [], (s["x1"] - s["x0"]) / max(len(text), 1)
    for m in re.finditer(r"\S+", text):
        out.append((m.group(0), s["x0"] + breite * (m.start() + m.end()) / 2))
    return out


def _menge_zelle(t):
    """Menge aus einer Mengenzelle: '20', '1.000', '20,000 ST' -> Zahl, sonst None."""
    w = re.split(r"\s+", (t or "").strip())
    return menge_zahl(w[0]) if w and w[0] else None


def _teil_zu_zeile(namen, zeilen):
    """{Name: Zeile} – genau gleicher Schlüssel in Artikel/Bezeichnung/Zeile, sonst (F2 a) die Artikel-Nr. der Zeile
    steckt im Namen (MG-01 ↔ MG-01 Stiel.stp), wenn genau ein Name und genau eine Zeile passen."""
    out = {}
    schl = {n: k for n in namen if len(k := _schluessel(n)) >= 3}
    for n, k in schl.items():
        treffer = [z for z in zeilen if k in ohne_zeichen(z.get("artikel")) or k in ohne_zeichen(z.get("text"))]
        if len(treffer) >= 1:
            out[n] = treffer[0]
    for z in zeilen:
        a = ohne_zeichen(z.get("artikel"))
        if len(a) < 3 or any(o is z for o in out.values()):
            continue
        passend = [n for n, k in schl.items() if n not in out and (k.startswith(a) or a in k)]
        andere = [y for y in zeilen if y is not z and len(ohne_zeichen(y.get("artikel"))) >= 3
                  and any(_schluessel(n).startswith(ohne_zeichen(y.get("artikel"))) for n in passend)]
        if len({schl[n] for n in passend}) == 1 and not andere:     # ein Teil (Dateiname und Artikel zählen einmal)
            for n in passend:
                out[n] = dict(z, _teilweise=True)
    return out


def stueck_tabelle(zeilen, namen):
    """Stückzahlen aus Tabellenzeilen: {Name: (Menge, sicher)}; sicher bei Mengenspalte und genau gleichem Namen."""
    out = {}
    for n, z in _teil_zu_zeile(namen, zeilen).items():
        menge = _menge_zelle(z.get("menge"))
        if menge:
            out[n] = (menge, not z.get("_teilweise"))
    return out


def werkstoff_je_teil(formulare, namen, werkstoffe):
    """Werkstoff je Teil aus dem Formular (F1 a): Werkstoffspalte der Tabelle bzw. die Zeile mit dem Teil, nur wenn
    genau ein Werkstoff der Stammdaten passt. {Name: (Werkstoff-ID, Quelle)}."""
    from . import mail
    out = {}
    for f in formulare or ():
        if f.get("mail"):
            continue
        quelle = f"Anfrageformular {f.get('datei') or ''}".strip()
        zeilen = f.get("tabelle") or []
        for n, z in _teil_zu_zeile(namen, zeilen).items():
            text = z.get("werkstoff") or ("" if "werkstoff" in {k for y in zeilen for k in y} else z.get("text"))
            ws = mail.werkstoff(text, werkstoffe)[0] if text else None
            if ws and n not in out:
                out[n] = (ws, quelle + (f" Pos. {z['pos']}" if z.get("pos") else ""))
        if not zeilen:              # ohne Tabelle: die Textzeile mit dem Teil
            schl = {n: k for n in namen if len(k := _schluessel(n)) >= 3}
            for zeile in (f.get("text") or "").split("\n"):
                form = ohne_zeichen(zeile)
                for n, k in schl.items():
                    if n not in out and k in form and (ws := mail.werkstoff(zeile, werkstoffe)[0]):
                        out[n] = (ws, quelle)
    return out
