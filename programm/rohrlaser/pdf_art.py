"""PDF der Anfrage: Zeichnung oder Anfrageformular? (Patrick 28.10.2026, Freigabe F1 b, F2-F4 a)

Jede Seite (PDF mit Text, Scan oder Foto per Texterkennung) wird für sich eingeordnet: Punkte für eine Zeichnung
(Schriftfeld mit Maßstab, Blatt, Gezeichnet/Geprüft, Zeichnungs-Nr., Allgemeintoleranz, Projektion, viele Maßzahlen,
Ø/R, viele Linien, Querformat) und für ein Formular (Anrede und Gruß, „Anfrage“/„Angebot“, Tabelle mit Pos. und
Menge, Liefertermin, Stückzahlen, Fließtext). Ergebnis je Seite Zeichnung, Formular oder unklar, mit Grund.
- Formular-Seiten und unklare Seiten (F3 a, mit Hinweis) gehen in die Formular-Auswertung (formular.py).
- Zeichnungs-Seiten liefern nur das Schriftfeld: Artikel/Zeichnungs-Nr., Benennung, Werkstoff, Stückzahl (F2 a: für
  das passende STEP-Teil, gelb; Formular und Mail gehen vor). Positionen entstehen aus Zeichnungen nie (F1 b).
Die Einordnung lässt sich im Prüfdialog je Datei umschalten (zusammen()). Ohne Qt."""
import re
from pathlib import Path

ZEICHNUNG, FORMULAR, UNKLAR = "Zeichnung", "Formular", "unklar"
AUTO, NICHT = "auto", "nicht"       # Wahl im Prüfdialog: automatisch bzw. Datei nicht verwenden
ABSTAND = 3                         # so viele Punkte Vorsprung braucht eine Art, sonst unklar

# (Muster, Punkte, Grund) – Kleinschreibung, je Muster einmal gezählt
_Z = [(r"ma(?:ß|ss)stab\s*:?\s*\d+\s*:\s*\d+|\bscale\s*:?\s*\d+\s*:\s*\d+|\bm\s*1\s*:\s*\d+\b|ma(?:ß|ss)stab|"
       r"\bscale\b", 3, "Maßstab"),
      (r"halbzeug|rohmaterial|rohteil|format\s*a\d|\brev\.?\b|revision|änderungsindex|\bmasse\b|gewicht\s*\[?kg",
       1, "Schriftfeld-Begriffe"),
      (r"\b(?:gezeichnet|gez\.|geprüft|gepr\.|bearbeitet|bearb\.|drawn|checked|approved|freigabe)\b", 2,
       "Gezeichnet/Geprüft"),
      (r"allgemeintoleranz|iso\s*2768|din\s*iso|toleranz|tolerance", 2, "Toleranzangabe"),
      (r"zeichnungs[\s-]*(?:nr|nummer)|zeichn\.?[\s-]*nr|zchn|drawing\s*(?:no|number)|dwg", 2, "Zeichnungs-Nr."),
      (r"\bblatt\b|\bsheet\b", 1, "Blatt"),
      (r"projektion|projection|erstellt\s+mit|cad\b", 1, "Projektion/CAD"),
      (r"oberfläche|oberflaeche|surface|kanten\s+gebrochen|entgratet|\bra\s*\d", 1, "Oberflächenangabe"),
      (r"\bschnitt\s+[a-z]\s*[-–]\s*[a-z]\b|\bsection\s+[a-z]\s*[-–]\s*[a-z]\b|\bansicht\s+[a-z]\b|\bdetail\s+[a-z]\b",
       2, "Schnitt/Ansicht")]
_F = [(r"\banfrage\b|\banfragen\b|angebotsanfrage|preisanfrage|request\s+for\s+quot|\brfq\b|\binquiry\b", 2,
       "„Anfrage“"),
      (r"sehr\s+geehrte|guten\s+tag|\bhallo\b|mit\s+freundlichen|freundliche\s+grü|best\s+regards|\bdear\b", 2,
       "Anrede/Gruß"),
      (r"bitte\s+(?:um|senden|bieten)|bitten\s+(?:um|sie)|angebot\s+(?:bis|erbeten)|angebotsfrist|please\s+quote", 2,
       "Bitte um Angebot"),
      (r"liefertermin|lieferdatum|lieferzeit|wunschtermin|delivery\s+date", 1, "Liefertermin"),
      (r"\bpos\.?\b|\bposition\b|\bitem\b", 1, "Positionen"),
      (r"\bmenge\b|\banzahl\b|\bqty\b|\bquantity\b", 1, "Mengenspalte"),
      (r"zahlungsbedingung|lieferbedingung|incoterm|ust[\s.-]*id|\biban\b|bankverbindung|handelsregister", 1,
       "Geschäftsangaben")]
STUECK = re.compile(r"(?<![\d,.])\d{1,6}\s*(?:stk|stück|stck|pcs)\b", re.I)
MASSZAHL = re.compile(r"^(?:[Ø⌀R]\s*)?\d{1,4}(?:[.,]\d{1,2})?(?:\s*[±+-]\s*\d+(?:[.,]\d+)?)?°?$")
DURCHMESSER = re.compile(r"[Ø⌀]\s*\d|\bR\s?\d{1,3}(?:[.,]\d)?\b|\bM\d{1,2}\b")


def einordnen(seite):
    """Art einer Seite (dict text, segmente, linien, breite, hoehe, ocr): (Art, Grund, Punkte Zeichnung, Punkte
    Formular). Grund: die stärksten Merkmale, z. B. „Zeichnung: Maßstab, Gezeichnet/Geprüft, 34 Maßzahlen“."""
    text = (seite.get("text") or "").lower()
    if len(text.strip()) < 10 and not seite.get("linien"):
        return UNKLAR, "kein lesbarer Text", 0, 0
    z, f, gz, gf = 0, 0, [], []
    for muster, p, grund in _Z:
        if re.search(muster, text):
            z, gz = z + p, gz + [grund]
    for muster, p, grund in _F:
        if re.search(muster, text):
            f, gf = f + p, gf + [grund]
    stuecke = [s["text"].strip() for s in seite.get("segmente") or () if s.get("text", "").strip()]
    if not stuecke:
        stuecke = [w for w in re.split(r"\s+", seite.get("text") or "") if w]
    masse = sum(1 for s in stuecke if MASSZAHL.match(s))
    if len(stuecke) >= 8 and masse >= 8 and masse / len(stuecke) >= 0.25:
        z, gz = z + 3, gz + [f"{masse} Maßzahlen"]
    elif masse >= 5 and masse / max(len(stuecke), 1) >= 0.15:
        z, gz = z + 1, gz + [f"{masse} Maßzahlen"]
    if len(DURCHMESSER.findall(seite.get("text") or "")) >= 3:
        z, gz = z + 1, gz + ["Ø/R/Gewinde"]
    linien = seite.get("linien") or 0
    if linien >= 150:
        z, gz = z + (3 if linien >= 600 else 2), gz + [f"{linien} Linien"]
    if (seite.get("breite") or 0) > (seite.get("hoehe") or 0) * 1.15 and z:
        z, gz = z + 1, gz + ["Querformat"]
    n_stk = len(STUECK.findall(seite.get("text") or ""))
    if n_stk >= 2:
        f, gf = f + 2, gf + [f"{n_stk}× Stückzahl"]
    zeilen = [zl for zl in (seite.get("text") or "").split("\n") if zl.strip()]
    worte = [w for zl in zeilen for w in zl.split()]
    echt = sum(1 for w in worte if re.fullmatch(r"[a-zäöüß]{3,}[,.]?", w, re.I))    # Wörter, kein Lesemüll
    if zeilen and len(worte) >= 60 and len(worte) / len(zeilen) >= 4.5 and echt / len(worte) >= 0.6:
        f, gf = f + 2, gf + ["Fließtext"]
    if z >= 4 and z - f >= ABSTAND:
        return ZEICHNUNG, "Zeichnung: " + ", ".join(gz[:4]), z, f
    if f >= 3 and f - z >= ABSTAND:
        return FORMULAR, "Formular: " + ", ".join(gf[:4]), z, f
    teile = [t for t in (", ".join(gz[:3]) and "Zeichnung (" + ", ".join(gz[:3]) + ")",
                         ", ".join(gf[:3]) and "Formular (" + ", ".join(gf[:3]) + ")") if t]
    return UNKLAR, "unklar: " + (" gegen ".join(teile) if teile else "keine typischen Merkmale"), z, f


def _pdf_seiten(pfad):
    """Seiten eines PDFs mit Text: [dict(text, segmente (y nach unten), linien, breite, hoehe)] oder None."""
    try:
        import pypdfium2 as pdfium
        import pypdfium2.raw as roh
        pdf = pdfium.PdfDocument(str(pfad))
    except Exception:           # kaputte oder verschlüsselte Datei
        return None
    try:
        out = []
        for i in range(len(pdf)):
            seite = pdf[i]
            breite, hoehe = seite.get_size()
            tp = seite.get_textpage()
            segmente = []
            for j in range(tp.count_rects()):
                l_, b, r, t = tp.get_rect(j)
                text = tp.get_text_bounded(l_, b, r, t).strip()
                if text:
                    segmente.append(dict(text=text, x0=l_, y0=hoehe - t, x1=r, y1=hoehe - b))
            text = tp.get_text_range().replace("\r\n", "\n").replace("\r", "\n")
            tp.close()
            linien = 0
            for _ in seite.get_objects(filter=[roh.FPDF_PAGEOBJ_PATH], max_depth=4):
                linien += 1
                if linien >= 5000:
                    break
            out.append(dict(text=text, segmente=segmente, linien=linien, breite=breite, hoehe=hoehe, ocr=False,
                            unsicher=set()))
            seite.close()
        return out
    except Exception:
        return None
    finally:
        pdf.close()


def _scan_seiten(pfad, programmordner=None, schon=None):
    """Seiten ohne Text per Texterkennung (ocr.py): je Seite dict wie _pdf_seiten (ocr=True). schon: Seiten, die schon
    Text haben (werden übernommen). Ohne Tesseract: die Seiten bleiben leer."""
    from . import ocr
    exe = ocr.programm(programmordner)
    try:
        bilder = ocr.seiten(pfad)
    except Exception:
        return schon or []
    out = []
    for i, b in enumerate(bilder):
        if schon and i < len(schon) and (schon[i]["text"] or "").strip():
            out.append(schon[i])
            continue
        alt = schon[i] if schon and i < len(schon) else {}
        s = dict(text="", segmente=[], linien=alt.get("linien", 0), breite=alt.get("breite", b.width),
                 hoehe=alt.get("hoehe", b.height), ocr=True, unsicher=set())
        if exe:
            try:
                t, u, sg = ocr.bild_lesen(b, exe)
                s.update(text=t, unsicher=u, segmente=sg)
            except Exception:       # Tesseract abgestürzt oder zu langsam: Seite bleibt leer (unklar)
                pass
        out.append(s)
    return out


def seiten(pfad, programmordner=None):
    """Alle Seiten lesen und einordnen: [dict(nr (ab 1), text, segmente, ocr, unsicher, linien, art, grund)]."""
    pfad = Path(pfad)
    roh = _pdf_seiten(pfad) if pfad.suffix.lower() == ".pdf" else None
    if roh is None or any(not (s["text"] or "").strip() for s in roh):
        roh = _scan_seiten(pfad, programmordner, roh)
    out = []
    for i, s in enumerate(roh):
        art, grund, _, _ = einordnen(s)
        out.append(dict(s, nr=i + 1, art=art, grund=grund))
    return out


def schriftfeld(seite):
    """Werte aus dem Schriftfeld einer Zeichnungsseite: dict(artikel, name, werkstoff_text, stueck) (nur gefundene)."""
    from . import pdf_zeichnung as pz
    seg, ocr = seite.get("segmente") or [], bool(seite.get("ocr"))
    out = dict(artikel=pz.feld(seg, pz.FELDER["artikel"], lambda x: x.strip() if re.search(r"\d", x) else None, ocr),
               name=pz.feld(seg, pz.FELDER["name"], None, ocr),
               werkstoff_text=pz.feld(seg, pz.FELDER["werkstoff"], None, ocr),
               stueck=pz.feld(seg, pz.FELDER["stueck"], pz._stueck, ocr))
    return {k: v for k, v in out.items() if v}


def zusammen(gelesen, wahl=AUTO):
    """Formular-Ergebnis (dict text, ocr, unsicher, datei, seiten, zeichnungen) für eine Wahl: AUTO = je Seite wie
    erkannt (unklar zählt als Formular), FORMULAR/ZEICHNUNG = alle Seiten so, NICHT = Datei nicht verwenden (None).
    Die Seiten bleiben gelesen, umschalten liest nichts neu."""
    if wahl == NICHT or not gelesen:
        return None
    seiten_ = gelesen["seiten"]

    def art(s):
        return s["art"] if wahl == AUTO else wahl

    formular_s = [s for s in seiten_ if art(s) != ZEICHNUNG]
    zeichnung_s = [s for s in seiten_ if art(s) == ZEICHNUNG]
    return dict(gelesen, wahl=wahl, text="\n".join(s["text"] for s in formular_s),
                ocr=any(s["ocr"] for s in formular_s) if formular_s else gelesen.get("ocr", False),
                unsicher=set().union(*[s.get("unsicher") or set() for s in formular_s]) if formular_s else set(),
                zeichnungen=[dict(schriftfeld(s), seite=s["nr"], datei=gelesen.get("datei")) for s in zeichnung_s])


def lesen(pfad, programmordner=None):
    """Datei lesen und einordnen: dict wie formular.datei_lesen (text nur der Formular- und unklaren Seiten, ocr,
    unsicher) dazu datei, seiten [dict(nr, art, grund, text, …)], zeichnungen (Schriftfelder) und wahl. None = nicht
    lesbar."""
    pfad = Path(pfad)
    s = seiten(pfad, programmordner)
    if not s or not any((x["text"] or "").strip() for x in s):
        return None
    return zusammen(dict(datei=pfad.name, seiten=s, ocr=any(x["ocr"] for x in s)))


def _bereiche(nummern):
    """[1, 2, 3, 5] -> 'S. 1–3, 5'."""
    teile, start = [], None
    for i, n in enumerate(nummern):
        if start is None:
            start = n
        if i + 1 == len(nummern) or nummern[i + 1] != n + 1:
            teile.append(f"{start}–{n}" if n > start else str(n))
            start = None
    return "S. " + ", ".join(teile)


def beschreibung(gelesen):
    """Eine Zeile für den Prüfdialog: 'Bestellung.pdf: Formular (S. 1), Zeichnung (S. 2–3)'; unklare Seiten mit
    „bitte prüfen“. None ohne Seiten (z. B. E-Mail-Text)."""
    if not gelesen or not gelesen.get("seiten"):
        return None
    wahl = gelesen.get("wahl", AUTO)
    if wahl != AUTO:
        return f"{gelesen.get('datei')}: alles als {wahl} (von Hand)"
    je = {}
    for s in gelesen["seiten"]:
        je.setdefault(s["art"], []).append(s["nr"])
    teile = []
    for art in (FORMULAR, ZEICHNUNG, UNKLAR):
        if art in je:
            seiten_ = "" if len(gelesen["seiten"]) == 1 else f" ({_bereiche(je[art])})"
            teile.append(f"{art}{seiten_}" + (" – als Formular gelesen, bitte prüfen" if art == UNKLAR else ""))
    return f"{gelesen.get('datei')}: " + ", ".join(teile)


def gruende(gelesen):
    """Gründe je Seite für den Tooltip."""
    return "\n".join(f"S. {s['nr']}: {s['grund']}" for s in (gelesen or {}).get("seiten") or ())


def _schl(t):
    from .formular import ohne_zeichen
    return ohne_zeichen(Path(str(t or "")).stem if str(t or "").lower().endswith((".pdf", ".step", ".stp")) else t)


def zeichnung_zu_teilen(messwerte, zeichnungen, werkstoffe=None):
    """F2 a: Schriftfeld einer Zeichnung auf das passende STEP-Teil (Artikel/Zeichnungs-Nr., Benennung oder Name der
    PDF gleich Artikel bzw. Dateiname des Teils): Stückzahl (gelb, nur wenn kein Formular sie gesetzt hat) und
    Werkstoff (nur eindeutig, gelb). Setzt _stueck/_stueck_formular/_stueck_quelle bzw. _werkstoff/_werkstoff_quelle.
    Ergebnis: Anzahl der Teile mit Werten aus einer Zeichnung."""
    from . import mail, step
    n = 0
    for z in zeichnungen or ():
        schl = {k for k in (_schl(z.get("artikel")), _schl(z.get("name")), _schl(z.get("datei"))) if len(k) >= 3}
        if not schl:
            continue
        for m in messwerte:
            if m.get("_saetze"):
                continue
            teil = {k for k in (_schl(m.get("artikel")), _schl(m.get("datei")), _schl(m.get("bauteil"))) if k}
            if not (schl & teil or any(len(a) >= 5 and any(a in b or b in a for b in teil if len(b) >= 5)
                                       for a in schl)):
                continue
            gesetzt = False
            if z.get("stueck") and "_stueck_formular" not in m:
                m["_stueck"], m["_stueck_formular"], m["_stueck_quelle"] = int(z["stueck"]), False, \
                    f"Zeichnung {z.get('datei')} S. {z.get('seite')}"
                gesetzt = True
            if z.get("werkstoff_text") and werkstoffe and "_werkstoff" not in m and step.blech(m) is None:
                ws, _, _ = mail.werkstoff(z["werkstoff_text"], werkstoffe)
                if ws:
                    m["_werkstoff"], m["_werkstoff_quelle"] = ws, f"Zeichnung {z.get('datei')} S. {z.get('seite')}"
                    gesetzt = True
            n += gesetzt
    return n


AUTO_FELDER = ("_stueck", "_stueck_formular", "_stueck_quelle")


def anwenden(messwerte, formulare, werkstoffe=None):
    """Stückzahlen aus Formularen/Mail (formular.stueck_aus, gehen vor) und danach Schriftfelder der Zeichnungen
    (zeichnung_zu_teilen) in die Messwerte; vorher gesetzte Werte aus einer früheren Wahl werden zurückgenommen
    (Umschalten im Prüfdialog). werkstoffe = Werkstoffzeilen (None: kein Werkstoff aus Zeichnungen, z. B. weil die
    Mail einen nennt). Ergebnis dict(formular, unsicher, zeichnung) = Anzahl Teile."""
    from . import formular
    for m in messwerte:
        if "_stueck_formular" in m:
            for k in AUTO_FELDER:
                m.pop(k, None)
        if m.pop("_werkstoff_quelle", None):
            m.pop("_werkstoff", None)
    formulare = [f for f in formulare or () if f]
    namen = {n for m in messwerte for n in (m.get("artikel"), m.get("datei")) if n}
    n = formular.stueck_setzen(messwerte, formular.stueck_aus([f for f in formulare if f.get("text")], namen))
    unsicher = sum(1 for m in messwerte if m.get("_stueck_formular") is False)
    z = zeichnung_zu_teilen(messwerte, [z for f in formulare for z in f.get("zeichnungen") or ()], werkstoffe)
    return dict(formular=n, unsicher=unsicher, zeichnung=z)
