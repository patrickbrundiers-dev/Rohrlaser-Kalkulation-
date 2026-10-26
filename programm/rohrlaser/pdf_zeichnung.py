"""PDF-Zeichnung eines Rohrteils -> Position im Rohr-Editor (Plan W7 Stufe 1, Patrick 25./26.10.2026: erst als
Testfunktion, Einstellung „pdf_zeichnung“).

Stufe 1 liest nur den Text der Zeichnung, keine Linien: aus einem PDF mit Text direkt (pypdfium2), aus Scans und Fotos
mit Tesseract (ocr.py, verstreuter Text). Gesucht wird im Schriftfeld und auf dem Blatt:
- Profil: „QR 40x40x3“, „Rechteckrohr 60x40x3“, „Ø42,4x2“, auch unter Halbzeug/Profil/Rohmaterial („40x40x3“),
- Länge: „L = 860“, „860 lg“, ein Wert unter Länge/Zuschnitt, oder ein vierter Wert am Profil („QR 40x40x3x860“);
  sonst die größte Maßzahl auf dem Blatt (unsicher, Hinweis),
- Werkstoff (Feld Werkstoff/Material, sonst irgendwo im Text), Artikel (Zeichnungs-/Artikel-/Teilenummer),
  Benennung, Stückzahl.
Das Ergebnis hat die Form von dxf_rohr.erkennen (profil, laenge, eingaben mit geraden Enden, ohne Konturen,
artikel, name, werkstoff_text, hinweise, warnungen, ok); der Rohr-Editor übernimmt es wie eine DXF
(SchneidwegDialog.dxf_uebernehmen), dort kommen Enden und Konturen von Hand dazu und auf Knopfdruck die STEP.
Stufe 2 (Konturen aus den Linien eines PDFs wie bei der DXF) braucht echte Zeichnungen. Ohne Qt."""
import re
from pathlib import Path

from . import dxf_rohr, formular

# Feldbeschriftungen im Schriftfeld (Anfang des Textes, ohne Groß/klein)
FELDER = {
    "name": ("benennung", "bezeichnung", "titel", "title", "description", "designation", "part name"),
    "artikel": ("zeichnungsnummer", "zeichnungs-nr", "zeichnungsnr", "zeich.-nr", "zeichn.-nr", "zchn.-nr",
                "artikelnummer", "artikel-nr", "artikelnr", "teilenummer", "teile-nr", "teilenr", "sachnummer",
                "sach-nr", "ident-nr", "identnummer", "part no", "part-no", "part number", "drawing no", "drawing number",
                "dwg no", "dwg. no", "dwg-no", "item no", "item number", "article no"),
    "werkstoff": ("werkstoff", "material"),
    "profil": ("halbzeug", "profil", "rohmaterial", "rohteil", "abmessung", "stock", "semi-finished", "raw material",
               "profile", "section", "dimension"),
    "laenge": ("länge", "laenge", "zuschnitt", "rohlänge", "schnittlänge", "length", "cut length"),
    "stueck": ("stückzahl", "stueckzahl", "stück", "menge", "anzahl", "qty", "quantity", "pcs"),
}
ZAHL = r"(\d+(?:[.,]\d+)?)"
MASS_X = r"\s*[xX×*]\s*"
LAENGE_LG = re.compile(ZAHL + r"\s*(?:mm\s*)?(?:lg\.?|lang)\b", re.I)
PROFIL_NACKT = re.compile(r"(?<![\d.,])(?:Ø|⌀)?\s*" + ZAHL + MASS_X + ZAHL + r"(?:" + MASS_X + ZAHL + r")?(?:"
                          + MASS_X + ZAHL + r")?")


def lesen(pfad, programmordner=None):
    """Text der ersten Seite: dict(text, segmente [dict(text, x0, y0, x1, y1)] mit y nach unten, ocr) oder None."""
    pfad = Path(pfad)
    if pfad.suffix.lower() == ".pdf":
        erg = _pdf_segmente(pfad)
        if erg and erg["text"].strip():
            return erg
    from . import ocr
    erg = ocr.lesen(pfad, programmordner, psm=11, nur_erste=True)
    if not erg or not erg["text"].strip():
        return None
    return dict(text=erg["text"], segmente=erg["segmente"], ocr=True)


def _pdf_segmente(pfad):
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(pfad))
    except Exception:
        return None
    try:
        seite = pdf[0]
        hoehe = seite.get_size()[1]
        tp = seite.get_textpage()
        segmente = []
        for i in range(tp.count_rects()):
            l_, b, r, t = tp.get_rect(i)
            text = tp.get_text_bounded(l_, b, r, t).strip()
            if text:
                segmente.append(dict(text=text, x0=l_, y0=hoehe - t, x1=r, y1=hoehe - b))
        text = tp.get_text_range()
        tp.close()
        return dict(text=text.replace("\r\n", "\n").replace("\r", "\n"), segmente=segmente, ocr=False)
    except Exception:
        return None
    finally:
        pdf.close()


def _label(text, worte, ocr=False):
    """Rest des Textes hinter einer Feldbeschriftung ('' = nur die Beschriftung) oder None. ocr: ein falsch gelesenes
    Zeichen je 6 Zeichen erlaubt (nur ganzes erstes Wort, 'Zerchnungsnummer')."""
    t = text.strip()
    for w in sorted(worte, key=len, reverse=True):
        if t.lower().startswith(w):
            rest = t[len(w):]
            if rest[:1].isalpha():                      # 'Materialnummer' ist nicht 'Material'
                continue
            return rest.lstrip(" .:#-/").strip()
    if ocr:
        erstes, _, rest = t.partition(" ")
        e = formular.ohne_zeichen(erstes)
        for w in worte:
            f = formular.ohne_zeichen(w)
            if len(f) >= 6 and abs(len(e) - len(f)) <= 1 and formular._abstand(f, e) <= len(f) // 6:
                return rest.lstrip(" .:#-/").strip()
    return None


def feld(segmente, worte, pruefen=None, ocr=False):
    """Wert einer Feldbeschriftung: im selben Textstück dahinter, sonst das nächste Textstück darunter (DIN EN ISO
    7200: Beschriftung klein oben im Feld) oder rechts daneben. pruefen(text) -> Wert oder None. Ergebnis: Wert/None."""
    pruefen = pruefen or (lambda x: x.strip() or None)
    for s in segmente:
        rest = _label(s["text"], worte, ocr)
        if rest is None:
            continue
        if rest and (w := pruefen(rest)) is not None:
            return w
        h = max(s["y1"] - s["y0"], 1.0)
        kandidaten = []
        for o in segmente:
            if o is s or _label(o["text"], sum(FELDER.values(), ()), ocr) is not None:
                continue
            dy, dx = o["y0"] - s["y1"], o["x0"] - s["x0"]
            if -0.3 * h <= dy <= 4 * h and -2 * h <= dx <= 6 * h and o["x0"] < s["x1"] + h:   # darunter
                kandidaten.append((dy + abs(dx) * 0.3, o))
            elif abs((o["y0"] + o["y1"]) / 2 - (s["y0"] + s["y1"]) / 2) <= 0.6 * h and 0 <= o["x0"] - s["x1"] <= 25 * h:
                kandidaten.append((o["x0"] - s["x1"] + h, o))                   # rechts daneben
        for _, o in sorted(kandidaten, key=lambda k: k[0]):
            if (w := pruefen(o["text"])) is not None:
                return w
    return None


def _profil(text):
    """Profil aus einem Text (dxf_rohr.profil_aus_text, auch ohne Kurzwort: '40x40x3', '60 x 40 x 3') und die Länge,
    wenn ein vierter Wert folgt: (profil, laenge) oder (None, None)."""
    p = dxf_rohr.profil_aus_text([text])
    m = PROFIL_NACKT.search(text)
    z = [float(g.replace(",", ".")) for g in m.groups() if g] if m else []
    laenge = None
    if p and len(z) >= (4 if p["form"] != "Rundrohr" else 3) and z[-1] > 3 * p["a"]:
        laenge = z[-1]
    if p:
        return p, laenge
    if len(z) >= 3 and z[2] < min(z[0], z[1]) / 2:             # a x b x Wand (x Länge)
        a, b, t = z[:3]
        form = "Quadratrohr" if abs(a - b) < 1e-6 else "Rechteckrohr"
        return dict(form=form, a=max(a, b), b=min(a, b), wand=t), (z[3] if len(z) > 3 and z[3] > 3 * a else None)
    if len(z) == 2 and m and re.match(r"\s*(?:Ø|⌀)", text[m.start():]) and z[1] < z[0] / 2:
        return dict(form="Rundrohr", a=z[0], b=z[0], wand=z[1]), None
    return None, None


SCHRIFTFELD_WORTE = sum(FELDER.values(), ()) + ("maßstab", "massstab", "scale", "datum", "date", "gezeichnet",
                                                 "geprüft", "gepr.", "norm", "blatt", "sheet", "gewicht", "masse",
                                                 "weight", "zust", "änderung", "aenderung", "rev", "format", "dept",
                                                 "technical reference", "created by", "approved by", "document type",
                                                 "document status", "date of issue")


def _schriftfeld_box(segmente):
    """Umriss des Schriftfelds: alle Feldbeschriftungen samt einem Rand (Zahlen darin sind keine Maße) oder None."""
    lab = [s for s in segmente if _label(s["text"], SCHRIFTFELD_WORTE) is not None]
    if len(lab) < 2:
        return None
    h = max(s["y1"] - s["y0"] for s in lab)
    return (min(s["x0"] for s in lab) - 2 * h, min(s["y0"] for s in lab) - 2 * h,
            max(s["x1"] for s in lab) + 15 * h, max(s["y1"] for s in lab) + 10 * h)


def _in_box(s, box):
    return box is not None and box[0] <= s["x0"] <= box[2] and box[1] <= s["y0"] <= box[3]


def _zahl(text):
    m = re.fullmatch(r"\s*(?:L\s*[=:]?\s*)?" + ZAHL + r"\s*(?:mm)?\s*", text or "", re.I)
    return float(m.group(1).replace(",", ".")) if m else None


def _stueck(text):
    m = re.fullmatch(r"\s*(\d{1,6})\s*(?:stk\.?|stück|st\.?|pcs)?\s*", text or "", re.I)
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def erkennen(pfad, programmordner=None, gelesen=None):
    """Zeichnung lesen und auswerten (siehe oben). gelesen: Ergebnis von lesen() (Tests). Ergebnis dict wie
    dxf_rohr.erkennen, dazu stueck und ocr; ok = False ohne Profil (warnungen sagen warum)."""
    pfad = Path(pfad)
    g = gelesen if gelesen is not None else lesen(pfad, programmordner)
    erg = dict(ok=False, profil=None, laenge=None, laenge_text=None, artikel=None, name=None, werkstoff_text=None,
               stueck=None, hinweise=[], warnungen=[], quelle_name="PDF-Zeichnung", ocr=bool(g and g.get("ocr")))
    if not g:
        erg["warnungen"].append("Kein Text in der Datei (auch die Texterkennung fand nichts oder fehlt).")
        return erg
    segmente, ocr = g.get("segmente") or [], bool(g.get("ocr"))
    zeilen = [z for z in g["text"].split("\n") if z.strip()]
    texte = [s["text"] for s in segmente] + zeilen
    # Profil: Feld Halbzeug/Profil, sonst irgendwo auf dem Blatt
    profil, laenge = None, None
    treffer = feld(segmente, FELDER["profil"], lambda x: x if _profil(x)[0] else None, ocr)
    if treffer:
        profil, laenge = _profil(treffer)
        erg["profil_quelle"] = f"Schriftfeld „{treffer.strip()}“"
    else:
        for t in texte:
            profil, laenge = _profil(t)
            if profil:
                erg["profil_quelle"] = f"Text „{t.strip()}“"
                break
    if not profil and ocr and gelesen is None:
        segmente = segmente + _senkrecht(pfad, programmordner)      # „30“ senkrecht am Schnitt liest psm 11 nicht
    if not profil:
        schnitt = _schnitt_profil(segmente)
        if schnitt:
            profil, (sa, sb) = schnitt
            erg["profil_quelle"] = f"Maße {dxf_rohr._z(sa)} und {dxf_rohr._z(sb)} am Schnitt"
            erg["warnungen"].append(f"Kein Profil im Text: {dxf_rohr._z(profil['a'])}×{dxf_rohr._z(profil['b'])} aus "
                                    "den Maßen am Schnitt, Wandstärke nicht angegeben: bitte prüfen.")
    if not profil:
        erg["warnungen"].append("Kein Rohrprofil im Text gefunden (z. B. „QR 40x40x3“ oder „Ø42,4x2“ im Schriftfeld).")
        return erg
    erg["profil"] = profil
    # Länge
    quelle = "am Profil" if laenge else None
    if not laenge:
        laenge = dxf_rohr.laenge_aus_text(texte)
        quelle = "L = … im Text" if laenge else None
    if not laenge:
        laenge = feld(segmente, FELDER["laenge"], _zahl, ocr)
        quelle = "Feld Länge" if laenge else None
    if not laenge:
        m = next((LAENGE_LG.search(t) for t in texte if LAENGE_LG.search(t)), None)
        laenge = float(m.group(1).replace(",", ".")) if m else None
        quelle = "„… lg“ im Text" if laenge else None
    if not laenge:
        feld_box = _schriftfeld_box(segmente)
        werte = [v for s in segmente if (v := dxf_rohr.zahl(s["text"])) and 3 * profil["a"] < v <= 20000
                 and not _in_box(s, feld_box) and not (ocr and _durchmesser_als_8(s["text"], profil))]
        if werte:
            laenge = max(werte)
            erg["warnungen"].append(f"Länge {dxf_rohr._z(laenge)} mm ist die größte Maßzahl der Zeichnung "
                                    "(nicht ausdrücklich angegeben): bitte prüfen.")
            quelle = "größte Maßzahl"
    if laenge:
        erg["laenge"] = erg["laenge_text"] = round(laenge, 1)
        erg["hinweise"].append(f"Länge {dxf_rohr._z(erg['laenge'])} mm ({quelle}).")
    else:
        erg["warnungen"].append("Keine Länge gefunden: bitte im Rohr-Editor eintragen.")
    # Werkstoff, Artikel, Benennung, Stückzahl
    erg["werkstoff_text"] = feld(segmente, FELDER["werkstoff"], None, ocr) or " ".join(texte)
    erg["artikel"] = feld(segmente, FELDER["artikel"], lambda x: x.strip() if re.search(r"\d", x) else None, ocr)
    erg["name"] = feld(segmente, FELDER["name"], None, ocr) or _groesste_schrift(segmente)
    erg["stueck"] = feld(segmente, FELDER["stueck"], _stueck, ocr)
    if erg["artikel"] is None:
        erg["artikel"] = re.sub(r"[_ ]+", " ", pfad.stem).strip() or None
        erg["hinweise"].append("Artikel aus dem Dateinamen (keine Zeichnungs-/Artikelnummer im Schriftfeld).")
    if erg["ocr"]:
        erg["warnungen"].append("Aus einem Scan gelesen (Texterkennung): Profil, Länge und Artikel bitte mit der "
                                "Zeichnung vergleichen.")
    erg["hinweise"].append("Stufe 1 (Test): Enden gerade, keine Konturen aus der Zeichnung; bitte im Rohr-Editor "
                           "ergänzen.")
    from . import schneidweg as sw
    erg["eingaben"] = dict(quelle=sw.QUELLE, a={}, b={}, konturen=[], pdf=pfad.name)
    erg["ok"] = True
    return erg


def mit_linien(linien, text):
    """Ergebnis aus den Linien (dxf_rohr.erkennen auf pdf_vektor.dxf_text, Stufe 2) mit dem aus dem Text (erkennen,
    Stufe 1) zusammen: Profil, Länge, Enden und Konturen aus den Linien; Stückzahl und fehlende Angaben (Artikel,
    Benennung, Werkstoff) aus dem Text."""
    erg = dict(linien, quelle_name="PDF-Zeichnung (Linien)", stueck=(text or {}).get("stueck"), ocr=False,
               hinweise=list(linien.get("hinweise") or []), warnungen=list(linien.get("warnungen") or []))
    for k in ("artikel", "name", "werkstoff_text"):
        if not erg.get(k) and (text or {}).get(k):
            erg[k] = text[k]
    eing = dict(erg.get("eingaben") or {})
    name = eing.pop("dxf", None)
    eing["pdf"] = name if isinstance(name, str) else True
    erg["eingaben"] = eing
    erg["hinweise"].append("Konturen und Enden aus den Linien der PDF-Zeichnung (Test): Linienart aus Strichstärke "
                           "und Strichmuster, bitte im Rohr-Editor prüfen.")
    return erg


def _senkrecht(pfad, programmordner=None):
    """Senkrecht geschriebene Texte eines Scans (Maße an senkrechten Maßlinien): Bild um 90° im Uhrzeigersinn gedreht
    lesen, Lage zurückgerechnet, mit senkrecht=True. Ohne Tesseract leer."""
    from . import ocr
    exe = ocr.programm(programmordner)
    if not exe:
        return []
    try:
        bild = ocr.seiten(pfad)[0]
        _t, _u, segmente = ocr.bild_lesen(bild.rotate(-90, expand=True), exe, psm=11)
    except Exception:
        return []
    h = bild.height
    return [dict(text=s["text"], x0=s["y0"], x1=s["y1"], y0=h - s["x1"], y1=h - s["x0"], seite=0, senkrecht=True)
            for s in segmente]


def _masszahl_text(s):
    """Maßzahl ohne Rahmen und Striche aus dem Scan („{180“, „50 |“), senkrecht ohne den davor gelesenen Maßpfeil
    („4 30“ -> „30“)."""
    t = s["text"].strip().strip("{}[]|()").strip()
    if s.get("senkrecht"):
        m = re.search(r"(?:^|\s)(\d+(?:[.,]\d+)?)$", t)
        return m.group(1) if m else t
    return t


def _ist_senkrecht(s):
    return s.get("senkrecht") or (s["y1"] - s["y0"]) > 1.15 * (s["x1"] - s["x0"]) and len(s["text"].strip()) >= 2


def _schnitt_profil(segmente):
    """Rechteck- oder Quadratrohr aus den Maßen am Querschnitt, wenn kein Profil im Text steht: eine waagrechte und
    eine senkrechte Maßzahl dicht beieinander (die senkrechte links oder rechts darunter, wie Breite über und Höhe
    neben dem Schnitt). (Profil ohne Wand, (waagrecht, senkrecht)) oder None."""
    box = _schriftfeld_box(segmente)
    zahlen = [(s, v) for s in segmente if (v := _zahl(_masszahl_text(s))) and 10 <= v <= 600 and not _in_box(s, box)]
    if len(zahlen) < 2:
        return None
    beste = None
    for s, a in zahlen:
        if _ist_senkrecht(s):
            continue
        h = max(s["y1"] - s["y0"], 1.0)
        for o, b in zahlen:
            if not _ist_senkrecht(o):
                continue
            dy = (o["y0"] + o["y1"]) / 2 - (s["y0"] + s["y1"]) / 2
            dx = (o["x0"] + o["x1"]) / 2 - (s["x0"] + s["x1"]) / 2
            d = (dx * dx + dy * dy) ** 0.5
            if 0 < dy <= 10 * h and abs(dx) <= 10 * h and (beste is None or d < beste[0]):
                beste = (d, a, b)
    if not beste:
        return None
    _d, a, b = beste
    form = "Quadratrohr" if abs(a - b) < 1e-6 else "Rechteckrohr"
    return dict(form=form, a=max(a, b), b=min(a, b), wand=None), (a, b)


def _groesste_schrift(segmente):
    """Benennung ohne erkannte Beschriftung: der Text mit der größten Schrift im Schriftfeld (kein Datum, keine Zahl)
    oder None."""
    box = _schriftfeld_box(segmente)
    if box is None:
        return None
    texte = [s for s in segmente if _in_box(s, box) and re.search(r"[A-Za-zÄÖÜäöü]{3}", s["text"])
             and _label(s["text"], SCHRIFTFELD_WORTE) is None and not re.search(r"\d{1,2}\.\d{1,2}\.\d{2,4}", s["text"])]
    if not texte:
        return None
    s = max(texte, key=lambda s: s["y1"] - s["y0"])
    return s["text"].strip()


def _durchmesser_als_8(text, profil):
    """Tesseract liest „Ø15“ oft als „815“: dreistellig mit 8 vorn und der Rest ein kleines Maß (bis Profilbreite)."""
    t = text.strip()
    return bool(re.fullmatch(r"8\d{2}", t)) and 0 < int(t[1:]) <= profil["a"]

