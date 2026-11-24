"""Anhänge einer Anfrage verstehen (Patrick 20.11.2026, Plan K4/K5, „Alles einbauen“).

dateityp(pfad)        Typ nach dem Inhalt (Dateikopf), nicht nur nach der Endung: STEP, PDF, DXF, DWG, ZIP/Office,
                      OLE (msg, doc, xls), Bild, Mail. Passt die Endung nicht zum Inhalt: Hinweis.
rolle(d, typ)         3D-Modell, Zeichnung, Stückliste, Anfrageformular, Bild, Archiv, Mail, Unbekannt, Beschädigt,
                      Zu groß (über GROSS_MB; wird nicht automatisch ausgewertet, Abruf läuft weiter).
revision_aus_name     „Halter_RevB.pdf“, „Halter-v2.step“, „Halter_Index_c.dxf“, „Halter (Rev. 03).pdf“
                      -> (Basis „halter“, Revision „B“/„2“/„C“/„03“).
analyse(dateien)      je Datei: typ, rolle, basis, revision, hinweise, neuer_stand_von (ältere Revision derselben
                      Basis in der Anfrage) und gruppe (STEP + Zeichnung zum selben Teil). Eine neue Revision ersetzt
                      nie eine alte: beide bleiben, die neue steht als „neuer Stand von …“.
nachtraege(mails)     Was ein späterer Nachtrag gegenüber der ersten Mail anders sagt (Stückzahl, Abmessung, Termin,
                      Revision …): [dict(feld, titel, alt, neu, fundstelle, mail, datum)]. Übernommen wird nichts von
                      allein, nur angezeigt („Neue Informationen dürfen vorhandene Daten nicht unkontrolliert
                      überschreiben“).
Ohne Qt. Dateien werden nur gelesen (die ersten Bytes), nie ausgeführt."""
import re
from pathlib import Path

GROSS_MB = 50
KOPF_BYTES = 4096

MODELL, ZEICHNUNG, STUECKLISTE, FORMULAR = "3D-Modell", "Zeichnung", "Stückliste", "Anfrageformular"
BILD, ARCHIV, MAIL, UNBEKANNT, KAPUTT, GROSS = "Bild", "Archiv", "Mail", "Unbekannt", "Beschädigt", "Zu groß"
ROLLEN = (MODELL, ZEICHNUNG, STUECKLISTE, FORMULAR, BILD, ARCHIV, MAIL, UNBEKANNT, KAPUTT, GROSS)

# Typ -> erwartete Endungen
ENDUNGEN = {"step": {".step", ".stp", ".igs", ".iges"}, "pdf": {".pdf"}, "dxf": {".dxf"}, "dwg": {".dwg"},
            "zip": {".zip", ".docx", ".docm", ".xlsx", ".xlsm", ".odt", ".ods", ".tubx"},
            "ole": {".msg", ".doc", ".xls"}, "png": {".png"}, "jpg": {".jpg", ".jpeg"}, "tif": {".tif", ".tiff"},
            "bmp": {".bmp"}, "eml": {".eml"}, "csv": {".csv", ".txt"}}
TYP_TEXT = {"step": "STEP", "pdf": "PDF", "dxf": "DXF", "dwg": "DWG", "zip": "ZIP/Office", "ole": "Outlook/Office",
            "png": "Bild (PNG)", "jpg": "Bild (JPG)", "tif": "Bild (TIFF)", "bmp": "Bild (BMP)", "eml": "Mail",
            "csv": "Text/CSV", "leer": "leer", "": "unbekannt"}

_STUECKLISTE = re.compile(r"st(?:ü|ue)ck\s*liste|stueckliste|\bbom\b|teileliste|positionsliste|mengenliste|"
                          r"bestellliste|materialliste", re.I)
_FORMULAR = re.compile(r"anfrage|formular|rfq|inquiry|bestellanfrage|leistungsverzeichnis|\blv\b", re.I)
_REV = [re.compile(r"[\s_.(-]+rev(?:ision)?[\s_.-]*([a-z]{1,2}\d{0,2}|\d{1,3})\)?$", re.I),
        re.compile(r"[\s_.(-]+(?:index|idx|ind)[\s_.-]*([a-z]{1,2}|\d{1,3})\)?$", re.I),
        re.compile(r"[\s_.(-]+v(?:ersion)?[\s_.-]*(\d{1,3})\)?$", re.I),
        re.compile(r"[\s_.(-]+(?:ä|ae)(?:nderung)?[\s_.-]*([a-z]|\d{1,2})\)?$", re.I),
        re.compile(r"[\s_]+([a-z])$", re.I)]       # „Halter_B“ (einzelner Buchstabe am Ende)


def kopf(pfad, n=KOPF_BYTES):
    try:
        with open(pfad, "rb") as f:
            return f.read(n)
    except OSError:
        return None


def dateityp(pfad):
    """(Typ, Hinweis) nach dem Dateikopf. Typ '' = unbekannt, 'leer' = 0 Byte, None = nicht lesbar."""
    b = kopf(pfad)
    if b is None:
        return None, "Datei nicht lesbar"
    if not b:
        return "leer", "Datei ist leer"
    t = ""
    s = b[:64].lstrip()
    if b.startswith(b"%PDF"):
        t = "pdf"
    elif s.startswith(b"ISO-10303-21") or b"FILE_SCHEMA" in b[:2048]:
        t = "step"
    elif b.startswith(b"PK\x03\x04"):
        t = "zip"
    elif b.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        t = "ole"
    elif b.startswith(b"\x89PNG"):
        t = "png"
    elif b.startswith(b"\xff\xd8\xff"):
        t = "jpg"
    elif b[:4] in (b"II*\x00", b"MM\x00*"):
        t = "tif"
    elif b.startswith(b"BM"):
        t = "bmp"
    elif b.startswith(b"AC10"):
        t = "dwg"
    elif re.match(rb"\s*0\s*\r?\n\s*SECTION", b) or b"\nSECTION" in b[:200] and b"HEADER" in b[:400]:
        t = "dxf"
    elif re.match(rb"(?:[\w-]+:[^\r\n]*\r?\n){2,}", b) and re.search(rb"(?im)^(from|subject|date):", b[:2048]):
        t = "eml"
    elif b"\x00" not in b[:1024]:
        t = "csv"
    endung = Path(str(pfad)).suffix.lower()
    hinweis = ""
    if t and t not in ("leer", "csv") and endung and endung not in ENDUNGEN.get(t, set()):
        erwartet = next((k for k, v in ENDUNGEN.items() if endung in v), "")
        if erwartet and erwartet != t:
            hinweis = f"Endung {endung} passt nicht zum Inhalt ({TYP_TEXT.get(t, t)})"
    return t, hinweis


def revision_aus_name(name):
    """(Basis, Revision) aus dem Dateinamen; Basis klein, ohne Trenner; Revision groß oder ''."""
    stamm = Path(str(name)).stem
    stamm = re.sub(r"\s*\(\d\)$", "", stamm)            # „Halter (1)“ = Kopie, keine Revision
    rev = ""
    for m in _REV:
        x = m.search(stamm)
        if x:
            rev = x.group(1).upper()
            stamm = stamm[:x.start()]
            break
    basis = re.sub(r"[\s_.\-]+", "", stamm).casefold()
    return basis, rev


def _rev_schl(r):
    """Sortierschlüssel einer Revision: Zahlen nach Wert, Buchstaben nach Alphabet ('' zuerst)."""
    if not r:
        return (0, 0, "")
    if r.isdigit():
        return (1, int(r), "")
    return (2, 0, r)


def rolle(d, typ=None):
    """Rolle einer Datei (d: dict mit name, pfad, groesse, art) – nach Typ, Endung und Name."""
    name = str(d.get("name") or "")
    endung = Path(name).suffix.lower()
    groesse = d.get("groesse")
    if groesse is None and d.get("pfad"):
        try:
            groesse = Path(d["pfad"]).stat().st_size
        except OSError:
            groesse = None
    if groesse is not None and groesse > GROSS_MB * 1024 * 1024:
        return GROSS
    if typ == "leer":
        return KAPUTT
    if endung in (".pdf",) and typ not in (None, "pdf"):
        return KAPUTT
    if endung in (".step", ".stp") and typ not in (None, "step"):
        return KAPUTT
    if endung in ENDUNGEN["step"] or endung in (".tubx", ".artube", ".bpf") or typ == "step":
        return MODELL
    if endung in (".msg", ".eml") or typ == "eml":
        return MAIL
    if endung in (".xlsx", ".xls", ".xlsm", ".ods", ".csv"):
        return STUECKLISTE if _STUECKLISTE.search(name) or endung != ".csv" else UNBEKANNT
    if endung in (".docx", ".docm", ".doc", ".odt"):
        return FORMULAR
    if endung == ".pdf":
        if _STUECKLISTE.search(name):
            return STUECKLISTE
        return FORMULAR if _FORMULAR.search(name) else ZEICHNUNG
    if endung in (".dxf", ".dwg"):
        return ZEICHNUNG
    if endung in (".tif", ".tiff"):
        return ZEICHNUNG
    if endung in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
        return BILD
    if endung in (".zip", ".7z", ".rar"):
        return ARCHIV
    return UNBEKANNT


def analyse(dateien, typen=True):
    """[dict(name, typ, typ_text, rolle, basis, revision, hinweise, neuer_stand_von, gruppe)] je Datei (dateien wie
    Akte.dateien()). typen=False liest keine Dateiköpfe (nur Name und Größe)."""
    out = []
    for d in dateien:
        typ, hinweis = (dateityp(d["pfad"]) if typen and d.get("pfad") else (None, ""))
        r = rolle(d, typ)
        basis, rev = revision_aus_name(d["name"])
        h = [x for x in (hinweis,) if x]
        if r == GROSS:
            h.append(f"über {GROSS_MB} MB: wird nicht automatisch ausgewertet")
        if r == KAPUTT:
            h.append("beschädigt oder leer: bitte beim Kunden neu anfordern")
        if r == UNBEKANNT:
            h.append("unbekannter Dateityp: wird nicht ausgewertet")
        if Path(d["name"]).suffix.lower() == ".dwg":
            h.append("DWG wird nicht eingelesen: bitte als DXF oder STEP anfordern")
        out.append(dict(name=d["name"], datei=d.get("datei", d["name"]), typ=typ or "",
                        typ_text=TYP_TEXT.get(typ or "", typ or ""), rolle=r, basis=basis, revision=rev,
                        hinweise=h, neuer_stand_von="", gruppe="", zeit=(d.get("herkunft") or {}).get("datum") or ""))
    # Revisionen: gleiche Basis + gleiche Rolle, höhere Revision = neuer Stand
    for x in out:
        if x["rolle"] not in (MODELL, ZEICHNUNG, STUECKLISTE) or not x["basis"]:
            continue
        aeltere = [y for y in out if y is not x and y["basis"] == x["basis"] and y["rolle"] == x["rolle"]
                   and _rev_schl(y["revision"]) < _rev_schl(x["revision"])]
        if aeltere:
            alt = max(aeltere, key=lambda y: _rev_schl(y["revision"]))
            x["neuer_stand_von"] = alt["name"]
    # Gruppen: Modell und Zeichnung mit gleicher Basis gehören zum selben Teil
    basen = {}
    for x in out:
        if x["rolle"] in (MODELL, ZEICHNUNG) and x["basis"]:
            basen.setdefault(x["basis"], set()).add(x["rolle"])
    for x in out:
        if len(basen.get(x["basis"], ())) == 2:
            x["gruppe"] = x["basis"]
    return out


def zusammenfassung(liste):
    """„2 3D-Modelle, 1 Zeichnung, 1 neuer Stand, 1 beschädigt“."""
    n = {}
    for x in liste:
        if x["rolle"] != MAIL:
            n[x["rolle"]] = n.get(x["rolle"], 0) + 1
    teile = [f"{v} {k}" for k, v in n.items()]
    neu = sum(1 for x in liste if x["neuer_stand_von"])
    if neu:
        teile.append(f"{neu} neuer Stand")
    return ", ".join(teile)


# ---------------------------------------------------------------------------------------------- Nachträge
VERGLEICH = ("stueckzahl", "abmessung", "wandstaerke", "blechdicke", "revision", "angebotsfrist", "zeichnung")


def _werte(text):
    from . import anfrage_art as aa
    w = {}
    for x in aa.technik(text):
        if x["feld"] in VERGLEICH:
            w.setdefault(x["feld"], x)
    try:
        from . import mail
        art, wert, satz = mail.termin(text)
        if art:
            w["termin"] = dict(feld="termin", titel="Wunschtermin", wert=f"{art} {wert}",
                               fundstelle=" ".join(satz.split())[:120])
    except Exception:           # noqa: BLE001 – Termin ist Zusatz
        w.pop("termin", None)
    return w


def nachtraege(mails):
    """mails: [(Name, Datum-Text, Text)] in Eingangsreihenfolge (erste = ursprüngliche Anfrage). Ergebnis: geänderte
    Werte späterer Mails gegenüber dem bisherigen Stand: [dict(feld, titel, alt, neu, fundstelle, mail, datum)]."""
    if len(mails) < 2:
        return []
    from . import mail as ml
    stand = _werte(ml.neuester_teil(mails[0][2]) or mails[0][2])
    out = []
    for name, datum, text in mails[1:]:
        neu = _werte(ml.neuester_teil(text) or text)
        for feld, x in neu.items():
            alt = stand.get(feld)
            if alt is None or str(alt["wert"]) != str(x["wert"]):
                out.append(dict(feld=feld, titel=x["titel"], alt=alt["wert"] if alt else "", neu=x["wert"],
                                fundstelle=x["fundstelle"], mail=name, datum=datum))
            stand[feld] = x
    return out
