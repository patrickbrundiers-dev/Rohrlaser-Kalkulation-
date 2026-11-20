"""Was für eine Mail ist das? Mail-Art, Sachgebiet und technische Werte (Patrick 20.11.2026, Entwicklungsauftrag
„Outlook-Anfrage-Erkennungssystem intelligent erweitern“, Plan K1–K3, „Alles einbauen“).

einordnen(text, betreff, dateien, hat_angebot)
    Mail-Art (ARTEN: neue Anfrage, Angebotsnachfrage, Angebotsänderung, Bestellung, Auftragsänderung, technische
    Rückfrage, Reklamation, Lieferterminanfrage, Materialanfrage, allgemeine Mail, Werbung) mit Punkten aus
    Formulierungen, Anhängen und dem Thread. Ergebnis mit Sicherheit (sicher / wahrscheinlich / unklar) und Gründen
    (je Grund die zitierte Zeile). Ohne genügend Punkte bleibt die Mail „unklar“ – lieber prüfen als raten.
sachgebiete(text, dateien)
    Rohr, Blech, Profil, Schweißbaugruppe, Dreh-/Frästeil, Material (mehrere möglich), aus Text und Dateinamen.
technik(text)
    Abmessung, Wandstärke, Blechdicke, Stückzahl, Zeichnungs-Nr., Revision, Angebotsfrist, Verfahren und besondere
    Anforderungen, je mit Fundstelle (die Zeile des Texts) und Sicherheit wie mail_fundstellen. Ein Wert ohne
    Fundstelle erscheint nie; das Programm erfindet nichts.

Der Text einer Mail ist nur Daten: was darin steht, ändert nie Regeln, Rechte, Ordner oder Versand. Eingeordnet wird
nur zur Anzeige und für Filter; aussortiert oder zugewiesen wird nichts von allein. Ohne Qt, ohne Netz, ohne
Sprachmodell."""
import re

from .mail_fundstellen import PRUEFEN, SICHER, ZITAT_MAX

# Mail-Arten (Schlüssel, Titel)
ANFRAGE, NACHFRAGE, AENDERUNG = "anfrage", "angebotsnachfrage", "angebotsaenderung"
BESTELLUNG, AUFTRAG_AENDERUNG, TECHNIK = "bestellung", "auftragsaenderung", "technische_rueckfrage"
REKLAMATION, LIEFERTERMIN, MATERIAL = "reklamation", "liefertermin", "materialanfrage"
ALLGEMEIN, WERBUNG = "allgemein", "werbung"
ARTEN = {ANFRAGE: "Neue Kundenanfrage", NACHFRAGE: "Angebotsnachfrage", AENDERUNG: "Angebotsänderung",
         BESTELLUNG: "Bestellung", AUFTRAG_AENDERUNG: "Auftragsänderung", TECHNIK: "Technische Rückfrage",
         REKLAMATION: "Reklamation", LIEFERTERMIN: "Lieferterminanfrage", MATERIAL: "Materialanfrage",
         ALLGEMEIN: "Allgemeine E-Mail", WERBUNG: "Werbung / Spam"}
KURZ = {ANFRAGE: "Anfrage", NACHFRAGE: "Nachfrage", AENDERUNG: "Änderung", BESTELLUNG: "Bestellung",
        AUFTRAG_AENDERUNG: "Auftragsänderung", TECHNIK: "Rückfrage", REKLAMATION: "Reklamation",
        LIEFERTERMIN: "Liefertermin", MATERIAL: "Material", ALLGEMEIN: "Allgemein", WERBUNG: "Werbung?"}

# Sachgebiete
ROHR, BLECH, PROFIL, BAUGRUPPE, DREHFRAES, MATERIAL_SG = ("rohr", "blech", "profil", "baugruppe", "drehfraes",
                                                         "material")
SACHGEBIETE = {ROHR: "Rohrlaserteile", BLECH: "Blechlaserteile", PROFIL: "Profile", BAUGRUPPE: "Schweißbaugruppen",
               DREHFRAES: "Dreh- und Frästeile", MATERIAL_SG: "Material"}

ANFRAGE_ZU = {ROHR: "Rohrlaserteilen", BLECH: "Blechlaserteilen", PROFIL: "Profilen", BAUGRUPPE: "Schweißbaugruppen",
              DREHFRAES: "Dreh- und Frästeilen"}

SICHER_ART, WAHRSCHEINLICH, UNKLAR = "sicher", "wahrscheinlich", "unklar"
SICHER_PUNKTE = 6           # so viele Punkte und …
ABSTAND = 3                 # … so viel Vorsprung vor der nächsten Art = sicher
MIN_PUNKTE = 3              # darunter: unklar

# (Art, Muster, Punkte, Grund) – Kleinschreibung, je Muster einmal gezählt
_R = r"(?:sie|ihr|ihnen|uns)"
REGELN = [
    # neue Anfrage: die Formulierungen aus dem Auftrag und Verwandte
    (ANFRAGE, r"\bpreis\w*\s+(?:nennen|mitteilen|angeben|geben)|\bihr(?:en)?\s+(?:besten\s+)?preis", 4,
     "fragt nach einem Preis"),
    (ANFRAGE, r"\bkalkulier\w*|\bkalkulation\b", 4, "bittet um Kalkulation"),
    (ANFRAGE, r"\b(?:ihr|ein|um\s+ein|unverbindliches|freibleibendes)\s+angebot\b|\bangebot\s+(?:für|über|zu)\b|"
              r"\bbitte\s+(?:um\s+)?(?:ein\s+)?angebot|\banbieten\b|\bangebotsabgabe\b", 4, "bittet um ein Angebot"),
    (ANFRAGE, r"\bwas\s+(?:würde|wuerde|kostet|kosten)\b|\bwas\s+\w+\s+(?:kosten|kostet)\b|\bkosten\s+für\b", 4,
     "fragt nach den Kosten"),
    (ANFRAGE, r"\b(?:prüfen|pruefen|ansehen|anschauen)\b.{0,40}\b(?:step|stp|zeichnung|datei|anhang|anlage)|"
              r"\b(?:step|stp|zeichnung\w*|dateien)\b.{0,40}\b(?:prüfen|pruefen|ansehen)\b", 3,
     "bittet, Dateien zu prüfen"),
    (ANFRAGE, r"\banfrage\b|\brfq\b|\brequest\s+for\s+quot|\bquotation\b|\binquiry\b", 3, "nennt eine Anfrage"),
    (ANFRAGE, r"\bbenötigen\b.{0,40}\b\d+\s*(?:stk|stück|st\b|teile|pcs)|\b\d+\s*(?:stk|stück|teile|pcs)\b", 2,
     "nennt eine Stückzahl"),
    (ANFRAGE, r"\bbeigefügt\w*\b|\banbei\b|\bim\s+anhang\b|\bin\s+der\s+anlage\b", 1, "verweist auf Anlagen"),
    # Angebot: Nachfrage und Änderung (meist im Thread zu unserem Angebot)
    (NACHFRAGE, r"\b(?:stand|status)\b.{0,30}\bangebot|\bangebot\b.{0,40}\b(?:erhalten|bekommen|schon|noch\s+nicht"
                r"|wann)\b|\bwann\b.{0,40}\bangebot", 5, "fragt nach dem Angebot"),
    (NACHFRAGE, r"\bnachfass\w*|\berinner\w*\s+(?:an|sie)\b.{0,20}\banfrage", 3, "erinnert an die Anfrage"),
    (AENDERUNG, r"\bangebot\b.{0,60}\b(?:ändern|anpassen|aktualisieren|überarbeiten|neu\s+berechnen)\b|"
                r"\b(?:geänderte|neue|andere)\s+(?:stückzahl|menge|zeichnung|version|revision)\b|"
                r"\bstatt\s+\d+\s*(?:stk|stück)|\bjetzt\s+(?:doch\s+)?\d+\s*(?:stk|stück)", 5,
     "ändert Mengen oder Unterlagen"),
    # Bestellung / Auftrag
    (BESTELLUNG, r"\bbestellen\s+(?:wir\s+)?(?:hiermit|gemäß|laut)|\bhiermit\s+bestellen|\bbestellung\b|"
                 r"\bauftrag\s+(?:erteilen|erteilt|vergeben)|\bbeauftragen\b|\bpurchase\s+order\b|\bpo\s*(?:no|nr)",
     6, "bestellt bzw. erteilt den Auftrag"),
    (BESTELLUNG, r"\bbestell[\s-]*(?:nr|nummer)\b|\bihr\s+angebot\s+(?:nr\.?\s*)?\S+\s+vom\b", 2,
     "nennt Bestellnummer bzw. unser Angebot"),
    (AUFTRAG_AENDERUNG, r"\b(?:auftrag|bestellung)\b.{0,50}\b(?:ändern|änderung|storn\w*|verschieben|anpassen|"
                        r"erhöhen|reduzieren)\b", 7, "ändert einen Auftrag"),
    # Technik, Reklamation, Termin, Material
    (TECHNIK, r"\btechnische\s+(?:frage|rückfrage|klärung)|\brückfrage\b|\bkönnen\s+sie\b.{0,40}\b(?:fertigen|"
              r"schweißen|lasern|biegen|kanten)\b.{0,20}\?|\bist\s+es\s+möglich\b", 4, "stellt eine technische Frage"),
    (REKLAMATION, r"\breklamation\b|\breklamier\w*|\bmangel\w*\b|\bfehlerhaft\w*|\bbeschädigt\w*|\bnicht\s+maßhaltig"
                  r"|\bausschuss\b|\b8d[\s-]?report|\bmängelrüge", 7, "meldet eine Reklamation"),
    (LIEFERTERMIN, r"\bliefertermin\b.{0,40}\?|\bwann\b.{0,40}\b(?:geliefert|liefern|lieferung|versand|fertig)\b|"
                   r"\bversandstatus\b|\bsendungsverfolgung\b|\bwo\s+bleibt\b", 5, "fragt nach dem Liefertermin"),
    (MATERIAL, r"\bmaterialanfrage\b|\bnur\s+(?:das\s+)?material\b|\bstangenmaterial\b|\b(?:\d+\s*)?stangen?\s+(?:à|a|zu)"
               r"\s+\d|\bohne\s+bearbeitung\b|\bin\s+handelslänge", 5, "fragt nur Material an"),
    # Werbung / Spam
    (WERBUNG, r"\bnewsletter\b|\babmelden\b|\bunsubscribe\b|\bim\s+browser\s+(?:ansehen|anzeigen|öffnen)|"
              r"\bnicht\s+mehr\s+erhalten\b|\bwebinar\b", 6, "sieht aus wie ein Newsletter"),
    (WERBUNG, r"\brabatt\b|\bsonderangebot\b|\b\d+\s*%\s*(?:rabatt|sparen|nachlass)|\bjetzt\s+(?:bestellen|kaufen|"
              r"sichern)\b|\bgratis\b|\bgewinnspiel\b", 4, "bewirbt etwas"),
    (WERBUNG, r"\bseo\b|\bsuchmaschinen\w*|\bleads?\b|\bunsere\s+dienstleistung\w*\b|\bwir\s+bieten\s+ihnen\b", 3,
     "bietet eine Dienstleistung an"),
    # allgemein
    (ALLGEMEIN, r"\bvielen\s+dank\b.{0,40}\b(?:info|information|rückmeldung)|\bzur\s+info\b|\bfyi\b|"
                r"\burlaub\w*|\bbetriebsferien\b|\babwesen\w*|\bout\s+of\s+office\b", 2, "allgemeine Mitteilung"),
]
_REGELN = [(a, re.compile(m, re.IGNORECASE | re.DOTALL), p, g) for a, m, p, g in REGELN]

STEP_ENDUNGEN = (".step", ".stp", ".igs", ".iges", ".tubx")
ZEICHNUNG_ENDUNGEN = (".pdf", ".dxf", ".dwg", ".tif", ".tiff")

# Sachgebiet: (Sachgebiet, Muster, Punkte)
SACH = [
    (ROHR, r"\brohr\w*|\bquadratrohr|\brundrohr|\brechteckrohr|\bvierkantrohr|\b(?:ø|d)\s*\d+(?:[.,]\d+)?\s*[x×]\s*"
           r"\d+(?:[.,]\d+)?\b|\bhohlprofil|\brohrlaser", 3),
    (BLECH, r"\bblech\w*|\bkantteil|\bkanten\b|\bgekantet|\blaserzuschnitt|\bplatine\b|\bt\s*=\s*\d", 3),
    (PROFIL, r"\b(?:u|l|t|c|z)[\s-]profil|\bprofil\w*|\bwinkel(?:stahl|profil)?\b|\b(?:hea|heb|ipe|upn|unp|ipn)\s*"
             r"\d+|\bflachstahl|\bflacheisen", 3),
    (BAUGRUPPE, r"\bbaugruppe|\bschweißbaugruppe|\bschweisbaugruppe|\bgeschweißt|\bschweißkonstruktion|\bschweißen\b|"
                r"\bgestell\b|\brahmen\b|\bunterbau\b|\bkonstruktion\b", 3),
    (DREHFRAES, r"\bdrehteil|\bfrästeil|\bgedreht|\bgefräst|\bcnc[\s-]?(?:dreh|fräs)|\bdrehen\b|\bfräsen\b", 3),
    (MATERIAL_SG, r"\bmaterialanfrage|\bnur\s+(?:das\s+)?material|\bstangenmaterial|\bhandelslänge", 4),
]
_SACH = [(s, re.compile(m, re.IGNORECASE)) for s, m, _ in SACH]
_SACH_P = {s: p for s, _, p in SACH}


def _zeile(text, start):
    """Die Zeile um eine Fundstelle, ohne doppelte Leerzeichen, höchstens ZITAT_MAX Zeichen."""
    a = text.rfind("\n", 0, start) + 1
    e = text.find("\n", start)
    z = " ".join(text[a:e if e >= 0 else len(text)].split())
    if len(z) > ZITAT_MAX:
        i = max(0, start - a - 40)
        z = ("…" if i else "") + z[i:i + ZITAT_MAX] + "…"
    return z


def _dateiendungen(dateien):
    out = []
    for d in dateien or ():
        name = d if isinstance(d, str) else (d.get("name") or str(d.get("pfad") or ""))
        out.append(str(name).lower())
    return out


def einordnen(text, betreff="", dateien=(), hat_angebot=False, ist_antwort=False):
    """Mail-Art: dict(art, titel, kurz, sicherheit, punkte, gruende=[(Grund, Zitat)], alternativen=[(art, punkte)],
    sachgebiete=[…], sachgebiet_titel). dateien: Dateinamen (oder dicts mit name/pfad). hat_angebot: zu dieser
    Anfrage gibt es schon ein Angebot von uns; ist_antwort: die Mail ist eine Antwort (AW:/RE:, In-Reply-To)."""
    voll = f"{betreff or ''}\n{text or ''}"
    punkte, gruende = {}, {}
    for art, muster, p, grund in _REGELN:
        m = muster.search(voll)
        if m:
            punkte[art] = punkte.get(art, 0) + p
            gruende.setdefault(art, []).append((grund, _zeile(voll, m.start())))
    namen = _dateiendungen(dateien)
    if any(n.endswith(STEP_ENDUNGEN) for n in namen):
        punkte[ANFRAGE] = punkte.get(ANFRAGE, 0) + 4
        gruende.setdefault(ANFRAGE, []).append(("STEP-Datei im Anhang", ""))
    elif any(n.endswith(ZEICHNUNG_ENDUNGEN) for n in namen):
        punkte[ANFRAGE] = punkte.get(ANFRAGE, 0) + 2
        gruende.setdefault(ANFRAGE, []).append(("Zeichnung im Anhang", ""))
    if hat_angebot or ist_antwort:
        # im Thread zu unserem Angebot: „Angebot“ heißt eher Nachfrage/Änderung/Bestellung als neue Anfrage
        if ANFRAGE in punkte and (punkte.get(AENDERUNG) or punkte.get(BESTELLUNG) or punkte.get(NACHFRAGE)):
            punkte[ANFRAGE] -= 3
    if punkte.get(WERBUNG) and (any(n.endswith(STEP_ENDUNGEN) for n in namen) or punkte.get(BESTELLUNG)):
        punkte[WERBUNG] -= 4            # STEP oder Bestellung: kein Newsletter
    reihe = sorted(((a, p) for a, p in punkte.items() if p > 0), key=lambda x: -x[1])
    sg = sachgebiete(voll, dateien)
    if not reihe or reihe[0][1] < MIN_PUNKTE:
        art, p = (reihe[0] if reihe else (ALLGEMEIN, 0))
        sicher = UNKLAR
    else:
        art, p = reihe[0]
        zweiter = reihe[1][1] if len(reihe) > 1 else 0
        sicher = SICHER_ART if p >= SICHER_PUNKTE and p - zweiter >= ABSTAND else (
            WAHRSCHEINLICH if p - zweiter >= 1 else UNKLAR)
    if art == MATERIAL:
        sg = [MATERIAL_SG] + [s for s in sg if s != MATERIAL_SG]
    return dict(art=art, titel=titel(art, sg), kurz=KURZ[art], sicherheit=sicher, punkte=p,
                gruende=gruende.get(art, [])[:4], alternativen=[x for x in reihe[1:4]],
                sachgebiete=sg, sachgebiet_titel=", ".join(SACHGEBIETE[s] for s in sg))


def titel(art, sg=()):
    """„Anfrage zu Rohrlaserteilen“ bei genau einem Sachgebiet, sonst der Titel der Art."""
    if art == ANFRAGE and len(sg) == 1 and sg[0] in ANFRAGE_ZU:
        return f"Anfrage zu {ANFRAGE_ZU[sg[0]]}"
    return ARTEN.get(art, art)


def sachgebiete(text, dateien=()):
    """Sachgebiete nach Punkten (mehrere möglich, das stärkste zuerst)."""
    voll = text or ""
    p = {}
    for s, m in _SACH:
        n = len(m.findall(voll))
        if n:
            p[s] = p.get(s, 0) + _SACH_P[s] + min(n - 1, 3)
    namen = _dateiendungen(dateien)
    for n in namen:
        for s, m in _SACH:
            if m.search(n):
                p[s] = p.get(s, 0) + 2
    if any(n.endswith(".dxf") for n in namen):
        p[BLECH] = p.get(BLECH, 0) + 3
    reihe = sorted((s for s, v in p.items() if v >= 3), key=lambda s: -p[s])
    return reihe


def kurztext(e):
    """„Bestellung (sicher)“ für Liste und Verlauf."""
    if not e:
        return ""
    return f"{e.get('titel') or ARTEN.get(e.get('art'), '')} ({e.get('sicherheit', '')})"


def kompakt(e):
    """Was im Kopf der Akte gespeichert wird (kurz, ohne lange Zitate)."""
    return dict(art=e["art"], sicherheit=e["sicherheit"], punkte=e["punkte"], sachgebiete=list(e["sachgebiete"]),
                gruende=[[g, z[:ZITAT_MAX]] for g, z in e["gruende"][:3]],
                alternativen=[[a, p] for a, p in e["alternativen"]])


# ---------------------------------------------------------------------------------------------- technische Werte
TECHNIK_TITEL = {"abmessung": "Abmessung", "wandstaerke": "Wandstärke", "blechdicke": "Blechdicke",
                 "stueckzahl": "Stückzahl", "zeichnung": "Zeichnungs-Nr.", "revision": "Revision",
                 "angebotsfrist": "Angebot bis", "verfahren": "Verfahren", "anforderung": "Anforderung"}
_ZAHL = r"\d{1,4}(?:[.,]\d{1,2})?"
_ABM = re.compile(rf"(?<![\w.,])(?:(ø|Ø|d\s*=?|dm\.?)\s*)?({_ZAHL})\s*[x×*]\s*({_ZAHL})(?:\s*[x×*]\s*({_ZAHL}))?"
                  rf"(?:\s*mm)?(?!\w|[.,]\d)", re.IGNORECASE)
_WAND = re.compile(rf"\b(?:wandstärke|wandstaerke|wandung|ws|wd)\s*[=:]?\s*({_ZAHL})\s*(?:mm)?\b", re.IGNORECASE)
_DICKE = re.compile(rf"\b(?:blechdicke|blechstärke|materialstärke|materialdicke|stärke|dicke|t|s)\s*[=:]\s*"
                    rf"({_ZAHL})\s*(?:mm)?|(?<![\w.,])({_ZAHL})\s*mm\s+(?:blech|stark|dick)\b", re.IGNORECASE)
_STUECK = re.compile(r"(?<![\w.,/-])(\d{1,3}(?:\.\d{3})+|\d{1,6})\s*(?:stk|stück|stck|st\.|pcs|teile|x\s+(?=\w))\b\.?",
                     re.IGNORECASE)
_ZNR = re.compile(r"\b(?:zeichnungs?[\s-]*(?:nr|nummer|no)|zchn?g?[\s.-]*nr|zeich\.?[\s-]*nr|drawing\s*(?:no|number)"
                  r"|dwg[\s-]*no)\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9./_-]{2,30})", re.IGNORECASE)
_REV_I = re.compile(r"\b(?:rev(?:ision)?|index|ind\.|änderungs(?:stand|index)|ä[\s-]*stand|version)\s*[.:#]?\s*"
                  r"([A-Z]{1,2}\d{0,2}|\d{1,3}(?:\.\d{1,2})?)\b", re.IGNORECASE)
_DATUM = r"(\d{1,2}\.\s?\d{1,2}\.(?:\s?\d{2,4})?|kw\s*\d{1,2}(?:\s*/\s*\d{2,4})?)"
_FRIST = re.compile(rf"\bangebot\w*\b.{{0,40}}?\b(?:bis|bis\s+zum|spätestens(?:\s+bis)?(?:\s+zum)?)\s+{_DATUM}|"
                    rf"\b(?:angebotsfrist|abgabefrist|abgabe\s+bis|submission\s+deadline)\s*[:=]?\s*{_DATUM}",
                    re.IGNORECASE)
VERFAHREN = [("Laserschneiden", r"\blaser\w*"), ("Kanten", r"\bkant(?:en|teil)|\bgekantet"),
             ("Biegen", r"\bbieg\w*|\bgebogen"), ("Schweißen", r"\bschwei(?:ß|ss)\w*"),
             ("Gewinde", r"\bgewinde\b|\bm\d{1,2}\b"), ("Senken", r"\bsenk\w*"), ("Entgraten", r"\bentgrat\w*"),
             ("Drehen/Fräsen", r"\bdreh(?:en|teil)|\bfräs\w*"), ("Montage", r"\bmontage\b|\bmontiert")]
ANFORDERUNGEN = [("Pulverbeschichtung", r"\bpulver\w*|\bral\s*\d{4}"), ("Verzinkt", r"\bverzink\w*|\bfeuerverz\w*"),
                 ("Zeugnis 3.1", r"\b(?:apz|abnahmeprüfzeugnis|zeugnis)\s*3\.1|\b3\.1\s*zeugnis|\ben\s*10204"),
                 ("EN 1090", r"\ben\s*1090|\bexc\s*[1-4]\b"), ("Toleranz ISO 2768", r"\biso\s*2768\w*|\bdin\s*7168"),
                 ("Beizen/Passivieren", r"\bbeiz\w*|\bpassivier\w*"), ("Glasperlstrahlen", r"\bglasperl\w*|\bstrahl"
                                                                                         r"en\b"),
                 ("Erstmusterprüfbericht", r"\bempb\b|\berstmuster\w*|\bppap\b"),
                 ("Verpackungsvorschrift", r"\bverpack\w*\s+(?:gemäß|nach|laut)|\beinzeln\s+verpackt")]
_VERF = [(n, re.compile(m, re.IGNORECASE)) for n, m in VERFAHREN]
_ANF = [(n, re.compile(m, re.IGNORECASE)) for n, m in ANFORDERUNGEN]


def _t(feld, wert, zitat, sicherheit):
    return dict(feld=feld, titel=TECHNIK_TITEL[feld], wert=wert, fundstelle=zitat, sicherheit=sicherheit, quelle="")


def _zahl(t):
    return t.replace(",", ".")


def technik(text, hoechstens=6):
    """Technische Werte mit Fundstelle: [dict(feld, titel, wert, fundstelle, sicherheit)]. Je Feld höchstens
    `hoechstens` verschiedene Werte. Abmessungen wie 40x40x3 (Rohr/Profil), Ø48,3x2,6, Blech 3 mm."""
    text = text or ""
    out, gesehen = [], set()

    def dazu(feld, wert, start, sicherheit):
        schl = (feld, str(wert).lower())
        if schl in gesehen or sum(1 for x in out if x["feld"] == feld) >= hoechstens:
            return
        z = _zeile(text, start)
        if z:
            gesehen.add(schl)
            out.append(_t(feld, wert, z, sicherheit))

    for m in _ABM.finditer(text):
        rund, a, b, c = m.group(1), m.group(2), m.group(3), m.group(4)
        davor = text[max(0, m.start() - 25):m.start()].lower()
        if re.search(r"(?:tel|fax|mob|\+49)[\s.:\d/()+-]*$", davor) or a == b == "0":
            continue
        try:
            fa, fb = float(_zahl(a)), float(_zahl(b))
        except ValueError:
            continue
        if fa > 2000 or fb > 6000 or (c is None and fb > 1000 and not rund):
            continue
        if rund:
            wert = f"Ø{a}x{b}"
        else:
            wert = f"{a}x{b}" + (f"x{c}" if c else "")
        dazu("abmessung", wert, m.start(), SICHER if (rund or c) else PRUEFEN)
    for m in _WAND.finditer(text):
        dazu("wandstaerke", f"{m.group(1)} mm", m.start(), SICHER)
    for m in _DICKE.finditer(text):
        w = m.group(1) or m.group(2)
        dazu("blechdicke", f"{w} mm", m.start(), SICHER if m.group(1) else PRUEFEN)
    for m in _STUECK.finditer(text):
        n = int(m.group(1).replace(".", ""))
        if 0 < n <= 1_000_000:
            dazu("stueckzahl", str(n), m.start(), PRUEFEN)
    for m in _ZNR.finditer(text):
        dazu("zeichnung", m.group(1).rstrip(".,;"), m.start(), SICHER)
    for m in _REV_I.finditer(text):
        w = m.group(1)
        if re.fullmatch(r"\d{4}", w):           # Jahreszahl („Version 2026“)
            continue
        dazu("revision", w.upper(), m.start(), SICHER)
    for m in _FRIST.finditer(text):
        dazu("angebotsfrist", " ".join((m.group(1) or m.group(2)).split()), m.start(), SICHER)
    for name, m in _VERF:
        x = m.search(text)
        if x:
            dazu("verfahren", name, x.start(), PRUEFEN)
    for name, m in _ANF:
        x = m.search(text)
        if x:
            dazu("anforderung", name, x.start(), PRUEFEN)
    return [x for x in out if x["fundstelle"]]

