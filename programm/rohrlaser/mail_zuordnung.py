"""Herkunft und Kunde einer Anfrage-Mail (Patrick 19.11.2026, Entwicklungsauftrag „Outlook-E-Mail-Integration
vollständig verbessern“; 20.11.2026 „Anfragen sammeln und zusammenführen“, Paket Z1).

Grundregel (Patrick): „Falsche Kundeninformationen konsequent verhindern. Lieber eine Anfrage zur manuellen Prüfung
vorlegen, als automatisch einen falschen Kunden oder Ansprechpartner zuzuordnen.“

Darum trennt das Modul die Rollen einer Mail (eigentlicher Kunde, ursprünglicher Absender, Weiterleiter, internes
Postfach, interner Anfragender, Ansprechpartner) und bewertet den Kunden in Stufen:

    eindeutig       Absenderadresse steht genau bei einem Kunden, gelernte Regel für die Adresse, oder Domain plus ein
                    zweites unabhängiges Merkmal (Firmenname bzw. Telefon in der Signatur, Kundennummer im Text)
    wahrscheinlich  ein Merkmal passt (z. B. nur die Domain): Vorschlag, der Mitarbeiter bestätigt mit einem Klick
    mehrdeutig      mehrere Kunden passen ähnlich gut: der Mitarbeiter wählt
    unbekannt       nichts passt (oder nur interne Absender): zur Prüfung

Nur „eindeutig“ setzt die Kundennummer der Akte; sonst steht der Kunde nur als Vorschlag da. Jede Zuordnung hält fest,
woran sie erkannt wurde (Kriterien, Punkte, Zeit, Message-ID). Gelernt wird nur über sichtbare Regeln (regeln.json im
Ordner _outlook der Akten), die ein Mitarbeiter beim Korrigieren ausdrücklich anlegt; der Kundenstamm wird nie ohne
Rückfrage geändert. Ohne Qt."""
import datetime
import json
import re
import uuid
from pathlib import Path

from . import mail

EINDEUTIG, WAHRSCHEINLICH, MEHRDEUTIG, UNBEKANNT = "eindeutig", "wahrscheinlich", "mehrdeutig", "unbekannt"
STUFEN = (EINDEUTIG, WAHRSCHEINLICH, MEHRDEUTIG, UNBEKANNT)
STUFE_TEXT = {EINDEUTIG: "eindeutig erkannt", WAHRSCHEINLICH: "wahrscheinlich – bitte prüfen",
              MEHRDEUTIG: "mehrdeutig – bitte wählen", UNBEKANNT: "nicht erkannt – bitte zuordnen"}
# Herkunft der Mail
DIREKT, WEITERGELEITET, INTERN = "direkt", "weitergeleitet", "intern"
ART_TEXT = {DIREKT: "direkt vom Kunden", WEITERGELEITET: "intern weitergeleitet",
            INTERN: "interne Anfrage (von einem Kollegen)"}

# Punkte je Merkmal (je Kunde zusammengezählt)
P_ADRESSE, P_REGEL_ADRESSE, P_REGEL_DOMAIN = 100, 100, 70
P_DOMAIN, P_DOMAIN_NAME, P_SIGNATUR, P_TELEFON, P_KUNDENNR, P_NAME_TEXT = 60, 40, 35, 35, 50, 30
EINDEUTIG_AB, ZWEI_MERKMALE_AB, VORSCHLAG_AB, ABSTAND = 100, 95, 30, 40

REGELN = "regeln.json"          # im Ordner _outlook der Akten
REGEL_ARTEN = {"adresse": "Adresse → Kunde", "domain": "Domain → Kunde", "intern": "Adresse ist intern",
               "nie": "Adresse nie automatisch zuordnen", "postfach": "Postfach → zuständig"}

KUNDENNR_TEXT = re.compile(r"\b(?:Kd\.?|Kunden)[\s-]*(?:Nr\.?|Nummer)\s*[:.]?\s*([A-Z]{0,3}\d{3,8})\b", re.I)


def _jetzt(jetzt=None):
    return (jetzt or datetime.datetime.now()).replace(microsecond=0).isoformat()


def _ziffern(t):
    return re.sub(r"\D", "", str(t or ""))[-8:]


def _person(name, adresse):
    """Name taugt als Ansprechpartner (nicht leer, keine Adresse, kein Sammelpostfach)?"""
    n = " ".join(str(name or "").split())
    if not n or "@" in n or mail.ist_zentral(adresse) and n.lower().split()[0] in mail.ZENTRAL:
        return ""
    return n


# ------------------------------------------------------------------ Regeln (kontrolliertes Lernen)
def regeln_pfad(wurzel):
    return Path(wurzel) / "_outlook" / REGELN


def regeln_lesen(wurzel):
    try:
        daten = json.loads(regeln_pfad(wurzel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in daten if isinstance(r, dict) and r.get("art") in REGEL_ARTEN and r.get("wert")]


def _regeln_schreiben(wurzel, liste):
    p = regeln_pfad(wurzel)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def regel_anlegen(wurzel, art, wert, kundennr="", kunde_name="", zustaendig="", von="", akte="", jetzt=None):
    """Regel anlegen (ersetzt eine gleiche Regel für denselben Wert). Ergebnis: die Regel."""
    if art not in REGEL_ARTEN:
        raise ValueError(f"Unbekannte Regel: {art}")
    wert = str(wert or "").strip().lower().lstrip("@")
    if not wert:
        raise ValueError("Regel ohne Adresse bzw. Domain")
    r = dict(id=uuid.uuid4().hex[:10], art=art, wert=wert, kundennr=str(kundennr or ""), kunde_name=kunde_name or "",
             zustaendig=str(zustaendig or "").upper(), von=von, akte=akte, zeit=_jetzt(jetzt))
    liste = [x for x in regeln_lesen(wurzel) if not (x["art"] == art and x["wert"] == wert)]
    _regeln_schreiben(wurzel, liste + [r])
    return r


def regel_loeschen(wurzel, regel_id):
    liste = regeln_lesen(wurzel)
    rest = [r for r in liste if r.get("id") != regel_id]
    if len(rest) != len(liste):
        _regeln_schreiben(wurzel, rest)
    return len(liste) - len(rest)


def regel_text(r):
    ziel = (f" → {r.get('kundennr')} {r.get('kunde_name') or ''}".rstrip() if r["art"] in ("adresse", "domain")
            else f" → {r.get('zustaendig')}" if r["art"] == "postfach" else "")
    return f"{REGEL_ARTEN[r['art']]}: {r['wert']}{ziel} (von {r.get('von') or '?'}, {str(r.get('zeit', ''))[:10]})"


def interne_adressen(regeln):
    return {r["wert"] for r in regeln or () if r["art"] == "intern"}


# ------------------------------------------------------------------ Herkunft
def herkunft(m, eigene=(), firma="", regeln=()):
    """Rollen der Mail: dict(art, original {name, adresse, datum}, weiterleiter [{name, adresse, datum}],
    anfragender_intern {name, adresse} (interne Anfrage), postfach (eigenes Postfach, an das geschrieben wurde),
    zentral (Sammelpostfach des Absenders?), antwort_an, notiz (Text des Kollegen, nur intern), mail (Mail des
    Kunden bzw. m))."""
    eigene = set(eigene or ())
    intern = interne_adressen(regeln)
    w = mail.weiterleitung(m, eigene, firma, intern)
    out = dict(art=DIREKT, original={}, weiterleiter=[], anfragender_intern={}, postfach="", zentral=False,
               antwort_an="", notiz="", mail=m)
    empf = [a for a in (m.empfaenger() if m is not None else []) if mail.ist_intern(a, eigene, intern)]
    if w is not None:
        out["weiterleiter"] = [dict(name=n, adresse=a, datum=d.isoformat() if d else "") for n, a, d in w.weiterleiter]
        out["notiz"] = w.notiz or ""
        o = w.original
        if o is not None and o.absender and not mail.ist_intern(o.absender, eigene, intern):
            out.update(art=WEITERGELEITET, mail=o, antwort_an=o.antwort_an or "")
            out["original"] = dict(name=o.absender_name, adresse=o.absender, datum=o.datum.isoformat() if o.datum
                                   else "")
            empf = w.empfaenger or empf
        else:                           # kein Kunde in der Weiterleitung: der Kollege fragt selbst an
            out.update(art=INTERN, mail=None)
            out["anfragender_intern"] = dict(name=m.absender_name, adresse=m.absender)
    elif m is not None and mail.ist_intern(m.absender, eigene, intern):
        out.update(art=INTERN, mail=None, notiz=mail.neuester_teil(m.text)[:300])
        out["anfragender_intern"] = dict(name=m.absender_name, adresse=m.absender)
    elif m is not None:
        out["original"] = dict(name=m.absender_name, adresse=m.absender, datum=m.datum.isoformat() if m.datum else "")
        out["antwort_an"] = m.antwort_an or ""
    a = out["original"].get("adresse", "")
    out["zentral"] = mail.ist_zentral(a)
    out["postfach"] = next((x for x in empf if mail.ist_zentral(x)), empf[0] if empf else "")
    return out


# ------------------------------------------------------------------ Kunde
def _stamm(kunden):
    out = []
    for k in kunden or ():
        for a in mail.ADRESSE.findall(str(k.get("email") or "")):
            out.append((a.lower(), str(k["kundennr"])))
    return out


def _kunden_im_text(text, kunden):
    """Kunden, deren Name (ab 6 Zeichen, ohne Rechtsform) im Text steht: {kundennr: Name}."""
    kt = mail._kompakt(text)
    out = {}
    for k in kunden or ():
        kern = mail._kompakt(re.sub(mail.FIRMA, "", str(k.get("name") or "")))
        if len(kern) >= 6 and kern in kt:
            out[str(k["kundennr"])] = k.get("name") or ""
    return out


def zuordnen(m, kunden, eigene=(), firma="", regeln=(), jetzt=None, nachrichten_id=""):
    """Kunde und Rollen einer Mail mit Stufe und Kriterien (dict, gespeichert im Kopf der Akte unter „zuordnung“):
    stufe, kundennr (nur bei eindeutig), kunde_name, vorschlaege [{kundennr, name, punkte, gruende}], ansprechpartner,
    art (direkt/weitergeleitet/intern), original, weiterleiter, anfragender_intern, postfach, zustaendig, kriterien,
    hinweise, zeit, automatisch, nachrichten_id, internet_id."""
    eigene = set(eigene or ())
    regeln = list(regeln or ())
    h = herkunft(m, eigene, firma, regeln)
    o = h["mail"]
    kunden = list(kunden or ())
    namen = {str(k["kundennr"]): k.get("name") or "" for k in kunden}
    punkte, gruende = {}, {}

    def dazu(nr, p, grund):
        nr = str(nr)
        if nr not in namen:
            return
        punkte[nr] = punkte.get(nr, 0) + p
        gruende.setdefault(nr, []).append(grund)

    hinweise = []
    adresse = h["original"].get("adresse", "")
    nie = adresse and any(r["art"] == "nie" and r["wert"] == adresse for r in regeln)
    if o is not None and adresse:
        stamm = _stamm(kunden)
        dom = mail._domain(adresse)
        for r in regeln:
            if r["art"] == "adresse" and r["wert"] == adresse:
                dazu(r["kundennr"], P_REGEL_ADRESSE, f"Regel: {adresse} gehört zu diesem Kunden ({r.get('von')})")
            elif r["art"] == "domain" and r["wert"] == dom and dom not in mail.FREEMAIL:
                dazu(r["kundennr"], P_REGEL_DOMAIN, f"Regel: Domain @{dom} gehört zu diesem Kunden ({r.get('von')})")
        genau = sorted({nr for s, nr in stamm if s == adresse})
        for nr in genau:
            dazu(nr, P_ADRESSE, f"Adresse {adresse} steht beim Kunden")
        if dom and dom not in mail.FREEMAIL and dom not in eigene and not genau:
            gleich = sorted({nr for s, nr in stamm if mail._domain(s) == dom})
            for nr in gleich:
                dazu(nr, P_DOMAIN if len(gleich) == 1 else P_DOMAIN // 2, f"Domain @{dom} beim Kunden")
            if not gleich:
                nr, _wie = mail.kunde_aus_domain(o, kunden, eigene)
                if nr:
                    dazu(nr, P_DOMAIN_NAME, f"Domain @{dom} passt zum Firmennamen")
        daten = mail.kunde_daten(o, "", eigene) or {}
        if daten.get("name") and "@" not in daten["name"]:
            kern = mail._kompakt(re.sub(mail.FIRMA, "", daten["name"]))
            for k in kunden:
                kk = mail._kompakt(re.sub(mail.FIRMA, "", str(k.get("name") or "")))
                if len(kern) >= 5 and kk and (kern == kk or (len(kk) >= 6 and (kk in kern or kern in kk))):
                    dazu(k["kundennr"], P_SIGNATUR, f"Firma „{daten['name']}“ in der Signatur")
        tel = _ziffern(daten.get("telefon"))
        if len(tel) >= 6:
            for k in kunden:
                if _ziffern(k.get("telefon")) == tel:
                    dazu(k["kundennr"], P_TELEFON, f"Telefon {daten['telefon']} wie beim Kunden")
    # Kundennummer bzw. Kundenname im Text (auch bei internen Anfragen: der Kollege nennt den Kunden)
    text = (o.volltext() if o is not None else (m.volltext() if m is not None else ""))
    for nr in dict.fromkeys(KUNDENNR_TEXT.findall(text)):
        dazu(nr, P_KUNDENNR, f"Kundennummer {nr} im Text")
    if h["art"] == INTERN or o is None or not punkte:
        for nr, name in _kunden_im_text(text, kunden).items():
            dazu(nr, P_NAME_TEXT, f"Kundenname „{name}“ im Text")
    liste = sorted(({"kundennr": nr, "name": namen.get(nr, ""), "punkte": p, "gruende": gruende[nr]}
                    for nr, p in punkte.items()), key=lambda x: (-x["punkte"], x["kundennr"]))
    beste = liste[0] if liste else None
    zweite = liste[1]["punkte"] if len(liste) > 1 else 0
    if beste is None or beste["punkte"] < VORSCHLAG_AB:
        stufe = UNBEKANNT
    elif zweite >= VORSCHLAG_AB and beste["punkte"] - zweite < ABSTAND:
        stufe = MEHRDEUTIG
    elif (beste["punkte"] >= EINDEUTIG_AB or (beste["punkte"] >= ZWEI_MERKMALE_AB and len(beste["gruende"]) >= 2)) \
            and h["art"] != INTERN:
        stufe = EINDEUTIG
    else:
        stufe = WAHRSCHEINLICH
    if nie and stufe == EINDEUTIG:
        stufe = WAHRSCHEINLICH
        hinweise.append(f"Regel: {adresse} nie automatisch zuordnen (schreibt für mehrere Kunden)")
    if h["art"] == INTERN:
        hinweise.append("Interne Anfrage: der Kollege ist nie Kunde oder Ansprechpartner"
                        + ("" if liste else "; Kunde wählen oder „Intern (ohne Kunde)“"))
    if h["art"] == WEITERGELEITET:
        hinweise.append("Kunde aus der weitergeleiteten Mail, nie aus der Adresse des Kollegen")
    if mail.ist_zentral(adresse):
        hinweise.append(f"{adresse} ist ein Sammelpostfach: Ansprechpartner bitte prüfen")
    if stufe == MEHRDEUTIG:
        hinweise.append("Mehrere Kunden passen: " + ", ".join(f"{x['kundennr']} {x['name']}" for x in liste[:3]))
    ansprechpartner = _person(h["original"].get("name"), adresse) if o is not None else ""
    if o is not None and not ansprechpartner:
        ansprechpartner = (mail.kunde_daten(o, "", eigene) or {}).get("ansprechpartner", "") \
            if not mail.ist_zentral(adresse) else ""
    kundennr = beste["kundennr"] if stufe == EINDEUTIG else ""
    zustaendig = next((r.get("zustaendig") for r in regeln if r["art"] == "postfach" and r["wert"] == h["postfach"]
                       and r.get("zustaendig")), "")
    if not zustaendig and kundennr:
        zustaendig = str(next((k.get("zustaendig") for k in kunden if str(k["kundennr"]) == kundennr), "") or "")
    kriterien = (beste["gruende"] if beste else []) + ([f"Herkunft: {ART_TEXT[h['art']]}"])
    return dict(stufe=stufe, kundennr=kundennr, kunde_name=namen.get(kundennr, "") if kundennr else "",
                vorschlaege=liste[:5], ansprechpartner=ansprechpartner if stufe != MEHRDEUTIG else "",
                art=h["art"], original=h["original"], weiterleiter=h["weiterleiter"],
                anfragender_intern=h["anfragender_intern"], postfach=h["postfach"], zentral=h["zentral"],
                antwort_an=h["antwort_an"], zustaendig=zustaendig.upper(), kriterien=kriterien, hinweise=hinweise,
                zeit=_jetzt(jetzt), automatisch=True, nachrichten_id=nachrichten_id or "",
                internet_id=(o.nachrichten_id if o is not None else "") or (m.nachrichten_id if m is not None else ""),
                in_reply_to=(m.in_reply_to if m is not None else ""),
                referenzen=list(m.referenzen if m is not None else [])[-20:])


def kurz_text(z):
    """Eine Zeile für Liste und Kopf: „wahrscheinlich – bitte prüfen: 10023 Krüger (Domain @krueger.de beim Kunden)“."""
    if not z:
        return ""
    t = STUFE_TEXT.get(z.get("stufe"), "")
    v = (z.get("vorschlaege") or [None])[0]
    if v and z.get("stufe") != UNBEKANNT:
        t += f": {v['kundennr']} {v['name']}".rstrip() + (f" ({v['gruende'][0]})" if v.get("gruende") else "")
    return t


# ------------------------------------------------------------------ Dubletten
def kunden_dubletten(kunden, daten):
    """Kunden im Stamm, die zu neuen Kundendaten (mail.kunde_daten) passen könnten: [(Kunde, Grund)] – vor „Neuen
    Kunden anlegen“ zeigen, nie selbst zusammenlegen."""
    daten = daten or {}
    out = []
    a = str(daten.get("email") or "").lower()
    dom = mail._domain(a) if "@" in a else ""
    tel = _ziffern(daten.get("telefon"))
    kern = mail._kompakt(re.sub(mail.FIRMA, "", str(daten.get("name") or "")))
    for k in kunden or ():
        stamm = [x.lower() for x in mail.ADRESSE.findall(str(k.get("email") or ""))]
        kk = mail._kompakt(re.sub(mail.FIRMA, "", str(k.get("name") or "")))
        if a and a in stamm:
            out.append((k, f"gleiche Adresse {a}"))
        elif dom and dom not in mail.FREEMAIL and any(mail._domain(s) == dom for s in stamm):
            out.append((k, f"gleiche Domain @{dom}"))
        elif len(tel) >= 6 and _ziffern(k.get("telefon")) == tel:
            out.append((k, "gleiche Telefonnummer"))
        elif len(kern) >= 5 and kk and (kern == kk or (len(kk) >= 6 and (kk in kern or kern in kk))):
            out.append((k, "ähnlicher Name"))
    return out


def dublette(akten, kopf, minuten=10):
    """Vorhandene Akte derselben Kundenmail (zweiter Weg, z. B. direkt an anfrage@ und zusätzlich von einem Kollegen
    weitergeleitet, oder dieselbe Mail zweimal importiert) oder None: (Akte, Grund). Gleich ist: dieselbe Internet-
    Message-ID, oder derselbe ursprüngliche Absender mit gleichem Kern-Betreff und Sendezeit höchstens minuten
    auseinander."""
    from . import anfragen_akten as ak
    z = kopf.get("zuordnung") or {}
    iid = z.get("internet_id") or ""
    adresse = (z.get("original") or {}).get("adresse") or ""
    zeit = _datum((z.get("original") or {}).get("datum"))
    kern = ak.betreff_kern(kopf.get("betreff"))
    for a in akten:
        az = a.kopf.get("zuordnung") or {}
        if iid and iid in a.internet_ids():
            return a, "dieselbe Mail (Message-ID) ist schon in dieser Anfrage"
        ao = az.get("original") or {}
        if adresse and ao.get("adresse") == adresse and kern and len(kern) >= 4 and ak.betreff_kern(a.betreff) == kern:
            az_zeit = _datum(ao.get("datum"))
            if zeit and az_zeit and abs((zeit - az_zeit).total_seconds()) <= minuten * 60:
                return a, "dieselbe Kundenmail kam auf einem zweiten Weg (z. B. weitergeleitet)"
    return None, ""


def antwort_ueber_kopf(akten, in_reply_to="", referenzen=()):
    """Akte, deren Mail die In-Reply-To- bzw. References-Kopfzeile nennt (Antwort im selben Mailverlauf), oder None.
    Das ist eindeutig: die Kopfzeilen schreibt das Mailprogramm, nicht der Mensch."""
    ids = {x for x in [in_reply_to, *(referenzen or ())] if x}
    if not ids:
        return None
    passt = [a for a in akten if a.internet_ids() & ids]
    return max(passt, key=lambda a: (a.eingang or datetime.datetime.min, a.nr), default=None)


def _datum(t):
    try:
        return datetime.datetime.fromisoformat(str(t)) if t else None
    except ValueError:
        return None


# ------------------------------------------------------------------ Antwort an den Kunden
def antwort_ziel(m, eigene=(), firma="", regeln=()):
    """Wohin eine Antwort an den Kunden geht, ohne interne Inhalte: (Adresse, als Antwort auf die Mail erlaubt?,
    Grund). Ist die Mail intern weitergeleitet oder eine interne Anfrage, enthält ihr Verlauf Notizen der Kollegen –
    dann nie „Antworten“ auf diese Mail (der Verlauf ginge mit), sondern eine neue Mail an den Kunden."""
    if m is None:
        return "", False, ""
    h = herkunft(m, eigene, firma, regeln)
    if h["art"] == WEITERGELEITET:
        return (h["antwort_an"] or h["original"].get("adresse", ""), False,
                "Intern weitergeleitet: neue E-Mail an den Kunden, ohne den internen Verlauf")
    if h["art"] == INTERN:
        return "", False, "Interne Anfrage: Kundenadresse bitte selbst eintragen (keine Antwort an den Kollegen)"
    return (m.antwort_an or m.absender), True, ""
