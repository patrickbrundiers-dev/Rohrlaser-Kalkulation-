"""Bestellung des Kunden erkennen und zuordnen (Automationen 03.11.2026, Vorschlag 1a).

Eine Mail (bzw. ein PDF mit Text) ohne STEP im Anfrage-Ordner, die nach einer Bestellung klingt („Bestellung“,
„bestellen“, „Auftrag erteilt“, „Purchase Order“ …) und eine eigene Angebotsnummer oder die Anfrage-Nr. eines
Angebots nennt, ist eine Bestellung zu diesem Angebot. Die Anfrage-Karte zeigt sie; das Fenster „Bestellung prüfen“
belegt Bestellnummer und Wunschtermin vor und gleicht jede Position ab (Menge und Preis je Stück aus der Bestellung
gegen das Angebot, Abweichungen gelb). Auf „Beauftragt“ setzt erst der Klick; das Programm beauftragt nie von allein.
Ohne Qt."""
import datetime
import re

WORTE = re.compile(r"\b(bestellung|bestellen|bestellt|bestell[-\s]?(?:nr|nummer)|beauftrag\w*|auftragserteilung|"
                   r"auftrag\s+(?:erteilt|vergeben)|erteilen\s+(?:wir\s+)?(?:ihnen\s+)?den\s+auftrag|purchase\s+order|"
                   r"order\s+no)", re.I)
NICHT = re.compile(r"\b(anfrage|angebot\s+(?:für|fuer|über|ueber)|bitte\s+um\s+(?:ein\s+)?angebot|preisanfrage)\b",
                   re.I)
BESTELLNR = re.compile(r"(?:Bestell(?:ung)?(?:s)?[-\s]?(?:Nr|Nummer|nummer|-Nr)\.?|Order\s*(?:No|Number)\.?|"
                       r"PO[-\s]?(?:Nr|No)?\.?|Auftrags?[-\s]?(?:Nr|Nummer)\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/.]{2,30})",
                       re.I)
PREIS = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2,4}|\d+\.\d{2,4})\s*(?:€|EUR|Euro)?", re.I)
TOL_PREIS = 0.005           # 0,5 % Abweichung im Preis je Stück gilt als gleich (Rundung)
OK, ABWEICHUNG, FEHLT = "ok", "abweichung", "fehlt"


def ist_bestellung(text):
    """True, wenn die neueste Nachricht nach einer Bestellung klingt (und nicht nach einer neuen Anfrage)."""
    from . import mail
    neu = mail.neuester_teil(text or "")
    kopf = "\n".join(neu.split("\n")[:3])       # Betreff und erste Zeilen
    if NICHT.search(kopf) and not WORTE.search(kopf):
        return False
    return bool(WORTE.search(neu))


def angebot_finden(db, text, kundennr=None):
    """Angebot, auf das sich die Bestellung bezieht: eigene, nicht abgelöste Angebote, deren Nummer im Text steht
    (sonst deren Anfrage-Nr.); bei mehreren das des Kunden, dann das neueste. Ergebnis: Angebotszeile oder None."""
    t = text or ""
    kandidaten = []
    for a in db.angebote():
        if a.get("fremd") or a.get("ersetzt_durch"):
            continue
        nr, ref = str(a.get("nummer") or ""), str(a.get("kundenreferenz") or "")
        if nr and re.search(rf"(?<![\w-]){re.escape(nr)}(?![\w-])", t):
            kandidaten.append((0, a))
        elif len(ref) >= 4 and re.search(rf"(?<![\w-]){re.escape(ref)}(?![\w-])", t):
            kandidaten.append((1, a))
    if not kandidaten:
        return None
    kandidaten.sort(key=lambda x: (x[0], str(x[1].get("kundennr")) != str(kundennr or ""),
                                   "" if x[1].get("vorgang") == "Beauftragt" else "0",
                                   -(x[1].get("id") or 0)))
    return kandidaten[0][1]


def bestellnummer(text):
    m = BESTELLNR.search(text or "")
    return m.group(1).rstrip(".-/") if m else None


def termin(text, heute=None):
    """Wunschtermin als ISO-Datum (aus mail.termin, Wochen/Arbeitstage ab heute) oder None."""
    from . import auftrag, mail
    art, wert, _ = mail.termin(text or "", heute)
    if not art:
        return None
    return auftrag.termin_vorschlag(dict(lieferzeit_art=art, lieferzeit_wert=wert), heute=heute).isoformat()


def _zahl(t):
    t = t.strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def preis_in_zeile(text, artikel):
    """Preis je Stück aus der Zeile mit der Artikelnummer: die erste Zahl mit Nachkommastellen nach der
    Artikelnummer (bei „Menge Einzelpreis Gesamtpreis“ der Einzelpreis), None ohne."""
    from .wiederholanfrage import _form
    ziel = _form(artikel)
    for z in (text or "").split("\n"):
        if ziel and ziel in _form(z):
            rest = z[z.casefold().find(str(artikel).casefold()) + len(str(artikel)):] \
                if str(artikel).casefold() in z.casefold() else z
            werte = [w for w in (_zahl(m.group(1)) for m in PREIS.finditer(rest)) if w is not None]
            if werte:
                return werte[0]
    return None


def abgleich(db, angebot_id, text):
    """Je Position mit Artikelnummer: dict(position_id, pos, artikel, stueck, bestellt, preis, preis_bestellt, status,
    hinweis). status: ok, abweichung (Menge oder Preis anders), fehlt (Artikel nicht in der Bestellung)."""
    import json
    from . import formular
    from .wiederholteile import preis_aus_staffeln
    a = db.angebot(angebot_id) or {}
    pos = [p for p in db.positionen(angebot_id) if str(p.get("artikel") or "").strip()]
    try:
        staffeln = a.get("staffelpreise")
        staffeln = json.loads(staffeln) if isinstance(staffeln, str) else staffeln
    except ValueError:
        staffeln = None
    mengen = formular.stueckzahlen(text or "", [str(p["artikel"]).strip() for p in pos])
    out = []
    for p in pos:
        art = str(p["artikel"]).strip()
        bestellt = (mengen.get(art) or (None,))[0]
        pm = preis_aus_staffeln(staffeln, p.get("pos"), bestellt or p.get("stueck"))
        preis = pm[1] if pm else None
        pb = preis_in_zeile(text, art)
        hinweis, status = [], OK
        if bestellt is None and pb is None and art.casefold() not in (text or "").casefold():
            status = FEHLT
            hinweis.append("nicht in der Bestellung")
        else:
            if bestellt is not None and int(bestellt) != int(p.get("stueck") or 0):
                status = ABWEICHUNG
                hinweis.append(f"Menge {bestellt} statt {p.get('stueck')}")
            if pb is not None and preis and abs(pb - preis) > TOL_PREIS * preis:
                status = ABWEICHUNG
                hinweis.append(f"Preis {pb:.2f} statt {preis:.2f} €/Stk".replace(".", ","))
        out.append(dict(position_id=p["id"], pos=p.get("pos"), artikel=art, stueck=p.get("stueck"), bestellt=bestellt,
                        preis=preis, preis_bestellt=pb, status=status, hinweis="; ".join(hinweis)))
    return out


def erkennen(db, text, kundennr=None):
    """Bestellung im Text: dict(angebot, bestellnr, termin) oder None (keine Bestellung bzw. kein Angebot)."""
    if not ist_bestellung(text):
        return None
    a = angebot_finden(db, text, kundennr)
    if a is None:
        return None
    return dict(angebot=a, bestellnr=bestellnummer(text), termin=termin(text))


def eintrag(datei, bestellnr, abweichungen):
    """Vermerk im Versandverlauf (art 'bestellung')."""
    return dict(art="bestellung", datum=datetime.date.today().isoformat(), datei=datei, bestellnr=bestellnr or "",
                abweichungen=abweichungen)
