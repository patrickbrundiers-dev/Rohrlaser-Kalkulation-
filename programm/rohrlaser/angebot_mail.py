"""Angebot per E-Mail verschicken (Vorschlag V1, Patrick 31.10.2026).

Das Programm sendet nie selbst: „In Outlook öffnen“ zeigt die fertige E-Mail mit dem Angebots-PDF im Anhang, gesendet
wird in Outlook. Liegt die Anfrage-Mail des Kunden als .msg im Angebotsordner (Ordner „Anfrage“, aus dem Anfrage-Ordner
übernommen), wird die E-Mail als „Allen antworten“ auf diese Mail geöffnet (Verlauf bleibt beim Kunden zusammen).
Sonst eine neue E-Mail an den Absender der Anfrage bzw. an die E-Mail-Adresse des Kunden. Ohne klassisches Outlook
entsteht eine E-Mail-Datei (.eml) für das Standard-Mailprogramm.

Nach dem Öffnen steht im Versandverlauf art 'mail' (zählt für das Nachfassen wie ein verschicktes Angebot)."""
import datetime
from pathlib import Path

from . import anfragen, mail
from .ausgabe import datum_text, gueltig_bis
from .materialanfrage import _vorlage, absender
from .stammdaten import EINSTELLUNG

ENDUNGEN = (".msg", ".eml")
ORDNER = (anfragen.ZIEL_FORMULAR, ".")       # Unterordner „Anfrage“ zuerst, dann der Angebotsordner selbst


def _einst(einst, name):
    w = (einst or {}).get(name)
    return w if isinstance(w, str) and w.strip() else EINSTELLUNG[name].vorgabe


def anfrage_mails(ordner):
    """Anfrage-Mails (.msg/.eml) im Angebotsordner, neueste zuerst (ältere Versionen „(alt)“ nicht)."""
    if not ordner:
        return []
    out = []
    for unter in ORDNER:
        o = Path(ordner) / unter
        try:
            out += [p for p in o.iterdir() if p.is_file() and p.suffix.lower() in ENDUNGEN and not anfragen.ist_alt(p)]
        except OSError:
            continue

    def zeit(p):
        m = mail.lesen(p)
        d = (m.datum or getattr(m, "datei_zeit", None)) if m else None
        try:
            return d.replace(tzinfo=None) if d else datetime.datetime.fromtimestamp(p.stat().st_mtime)
        except OSError:
            return datetime.datetime.min
    return sorted(dict.fromkeys(out), key=zeit, reverse=True)


def anrede(kunde):
    """Anrede aus dem Ansprechpartner des Kunden („Herr Meier“ -> „Sehr geehrter Herr Meier,“), sonst allgemein."""
    a = " ".join(str((kunde or {}).get("ansprechpartner") or "").split())
    for vorne, text in (("herr ", "Sehr geehrter"), ("frau ", "Sehr geehrte")):
        if a.lower().startswith(vorne) and len(a) > len(vorne):
            return f"{text} {a[0].upper()}{a[1:]},"
    return "Sehr geehrte Damen und Herren,"


def werte(kopf, einst, kunde=None, netto=None):
    """Platzhalter der Vorlagen: {anrede} {angebot} {kunde} {referenz} {gueltig} {lieferzeit} {netto} {datum}
    {absender}."""
    from .angebot import lieferzeit_text
    g = gueltig_bis(kopf or {}, einst or {}) if (kopf or {}).get("datum") else None
    ref = str((kopf or {}).get("kundenreferenz") or "").strip()
    return dict(anrede=anrede(kunde), angebot=(kopf or {}).get("nummer") or "", kunde=(kopf or {}).get("kunde") or "",
                referenz=f" zu Ihrer Anfrage {ref}" if ref else "", gueltig=datum_text(g.isoformat()) if g else "",
                lieferzeit=lieferzeit_text(kopf or {}) or "",
                netto=(f"{netto:,.2f} €".replace(",", "#").replace(".", ",").replace("#", ".")
                       if isinstance(netto, (int, float)) else ""),
                datum=datetime.date.today().strftime("%d.%m.%Y"), absender=absender(einst))


def betreff(kopf, einst, anfrage=None):
    """Betreff: Antwort auf die Anfrage-Mail („AW: …“), sonst aus der Vorlage."""
    if anfrage is not None and anfrage.betreff:
        b = anfrage.betreff.strip()
        return b if anfragen.PRAEFIX.match(b) else f"AW: {b}"
    return _vorlage(_einst(einst, "angebot_mail_betreff"), werte(kopf, einst)).strip()


def text(kopf, einst, kunde=None, netto=None):
    return _vorlage(_einst(einst, "angebot_mail_text"), werte(kopf, einst, kunde, netto)).strip()


def empfaenger(kunde, anfrage=None):
    """An: Absender der Anfrage-Mail, sonst die E-Mail des Kunden."""
    if anfrage is not None and "@" in (anfrage.absender or ""):
        return anfrage.absender
    return str((kunde or {}).get("email") or "").strip()


def antwort_moeglich(pfad):
    """Nur eine .msg lässt sich in Outlook öffnen und beantworten (OpenSharedItem); .eml wird neue E-Mail."""
    return bool(pfad) and Path(pfad).suffix.lower() == ".msg"


def eintrag(an, antwort=False, datei=None):
    """Eintrag im Versandverlauf (angebote.versand)."""
    e = dict(art="mail", datum=datetime.date.today().isoformat(), an=an or "")
    if antwort:
        e["antwort"] = True
    if datei:
        e["datei"] = datei
    return e


def verlauf_text(v):
    """Zeile im Versandverlauf des Angebots."""
    t = f"{datum_text(v.get('datum'))}: per E-Mail {'(Antwort auf die Anfrage) ' if v.get('antwort') else ''}"
    return t + (f"an {v['an']}" if v.get("an") else "ohne Empfänger") + (f" ({v['datei']})" if v.get("datei") else "")
