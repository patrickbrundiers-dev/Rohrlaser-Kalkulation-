"""Datenschutz: Kunden anonymisieren und Auskunft (Vorschlag S3, Patrick 02.11.2026 „S3a“).

- Anonymisieren (nur Admin, von Hand im Reiter Kunden): Ansprechpartner, Telefon und Mail des Kunden werden geleert
  (Ansprechpartner = „anonymisiert TT.MM.JJJJ“), in seinen Angeboten die Mail-Adressen im Versandverlauf. Mit
  „auch Name und Anschrift“ (Privatperson) zusätzlich Name, Straße, PLZ/Ort und der Kundenname in den Angeboten.
  Preise, Mengen, Positionen und Zahlen bleiben für Auswertungen und Nachkalkulation.
- Auskunft (PDF): welche Daten zu einem Kunden gespeichert sind (Kundenstamm, Angebote mit Datum/Vorgang/Netto,
  Mail-Adressen aus dem Versandverlauf, Kundenvorgaben, Importprofile).
- Frist (Einstellung datenschutz_jahre, 0 = aus, Vorgabe aus): abgelehnte Angebote älter als so viele volle Jahre
  verlieren die Mail-Adressen im Versandverlauf; hat ein Kunde nur solche Angebote, wird er wie oben anonymisiert
  (ohne Name und Anschrift). Läuft beim Start höchstens einmal am Tag.
Die Änderungen stehen in der Datendatei und gehen über den gemeinsamen Ordner an alle Plätze wie jede Änderung.
Ohne Qt außer dem PDF (reportlab über pdf.py)."""
import datetime
import json

ANONYM = "anonymisiert"
KONTAKT = ("ansprechpartner", "telefon", "email")            # Personenbezug immer
ANSCHRIFT = ("name", "strasse", "plz_ort", "plz", "liefer_plz")   # nur „auch Name und Anschrift“
EINSTELLUNG = "datenschutz_jahre"
ZULETZT = "datenschutz_zuletzt"


def _heute(heute):
    return heute or datetime.date.today()


def _versand(wert):
    if isinstance(wert, list):
        return wert
    try:
        v = json.loads(wert or "[]")
    except (TypeError, ValueError):
        return []
    return v if isinstance(v, list) else []


def _angebote(db, kundennr):
    return [dict(r) for r in db.con.execute(
        "SELECT id, nummer, kunde, datum, vorgang, vk_netto, kundenreferenz, versand FROM angebote WHERE kundennr=? "
        "ORDER BY datum, nummer", (kundennr,))]


def _mails_entfernen(liste):
    """Versandverlauf ohne Mail-Adressen; Ergebnis (neue Liste, Anzahl entfernt)."""
    neu, n = [], 0
    for e in liste:
        if isinstance(e, dict) and e.get("an") and e.get("an") != ANONYM:
            e = dict(e, an=ANONYM)
            n += 1
        neu.append(e)
    return neu, n


def ist_anonym(kunde):
    return str((kunde or {}).get("ansprechpartner") or "").startswith(ANONYM)


def anonymisieren(db, kundennr, alles=False, heute=None, angebote=None):
    """Kunde anonymisieren (siehe oben). angebote: nur diese Angebots-IDs (Frist), None = alle des Kunden.
    Ergebnis dict(kunde=True/False, felder=[geleerte Felder], angebote=Anzahl geänderter Angebote, mails=Anzahl)."""
    heute = _heute(heute)
    k = db.kunde(kundennr)
    felder = []
    if k is not None:
        werte = {f: "" for f in KONTAKT}
        werte["ansprechpartner"] = f"{ANONYM} {heute:%d.%m.%Y}"
        if alles:
            werte.update({f: "" for f in ANSCHRIFT if f in k})
            werte["name"] = f"{ANONYM} {kundennr}"
        for f, w in werte.items():
            if f in k and (k.get(f) or "") != w and (f != "ansprechpartner" or not ist_anonym(k) or alles):
                db.aendern("kunden", k["id"], f, w)
                felder.append(f)
    n_ang = n_mail = 0
    for a in _angebote(db, kundennr):
        if angebote is not None and a["id"] not in angebote:
            continue
        neu, n = _mails_entfernen(_versand(a.get("versand")))
        geaendert = False
        if n:
            db.versand_setzen(a["id"], neu)
            n_mail += n
            geaendert = True
        if alles and a.get("kunde") != f"{ANONYM} {kundennr}":
            db.angebot_aendern(a["id"], "kunde", f"{ANONYM} {kundennr}")
            geaendert = True
        n_ang += geaendert
    return dict(kunde=k is not None, felder=felder, angebote=n_ang, mails=n_mail)


def auskunft(db, kundennr, heute=None):
    """Gespeicherte Daten zum Kunden: dict(kundennr, kunde={Feld: Wert}, angebote=[dict(nummer, datum, vorgang,
    netto, referenz)], mails=[Adressen], vorgaben=Anzahl, importprofile=Anzahl, erstellt)."""
    from .stammdaten import KUNDEN
    k = db.kunde(kundennr) or {}
    titel = {f.name: f.titel for f in KUNDEN.felder}
    kunde = {titel[f]: k.get(f) for f in titel if k.get(f) not in (None, "")}
    angebote, mails = [], []
    for a in _angebote(db, kundennr):
        angebote.append(dict(nummer=a["nummer"], datum=a["datum"], vorgang=a.get("vorgang") or "Entwurf",
                             netto=a.get("vk_netto"), referenz=a.get("kundenreferenz") or ""))
        for e in _versand(a.get("versand")):
            an = isinstance(e, dict) and e.get("an")
            if an and an != ANONYM and an not in mails:
                mails.append(an)

    def anzahl(tabelle):
        try:
            return db.con.execute(f'SELECT COUNT(*) FROM "{tabelle}" WHERE kundennr=?', (kundennr,)).fetchone()[0]
        except Exception:           # Tabelle oder Spalte fehlt (ältere Datei)
            return 0
    return dict(kundennr=kundennr, kunde=kunde, angebote=angebote, mails=mails, vorgaben=anzahl("kundenvorgaben"),
                importprofile=anzahl("importprofile"), erstellt=_heute(heute).isoformat())


def auskunft_pdf(pfad, a, einst):
    """Auskunft als PDF (A4 hoch)."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer
    from . import pdf as p_
    from .ausgabe import datum_text
    einst = einst or {}
    titel = f"Datenauskunft {a['kundennr']}"
    doc, leinwand = p_._dokument(pfad, titel, p_._fuss(einst, titel))
    breite = 186 * mm
    inhalt = p_._dok_kopf("Datenauskunft (Art. 15 DSGVO)", {}, einst, breite,
                          [("Kunde", a["kundennr"]), ("Stand", datum_text(a["erstellt"]))])
    inhalt.append(p_._p("Kundenstamm", p_.S_H2))
    daten = [p_._kopfzeile(["Feld", "gespeichert"])] + [[p_._p(f, p_.S_KLEIN), p_._p(str(w), p_.S_KLEIN)]
                                                       for f, w in a["kunde"].items()]
    if len(daten) == 1:
        daten.append(["–", "kein Eintrag im Kundenstamm"])
    inhalt += [p_._tabelle(daten, [60 * mm, 126 * mm], zebra=False), Spacer(1, 5 * mm)]
    inhalt.append(p_._p(f"Angebote ({len(a['angebote'])})", p_.S_H2))
    daten = [p_._kopfzeile(["Nummer", "Datum", "Vorgang", "Ihre Anfrage", "Netto [€]"])]
    for x in a["angebote"]:
        daten.append([x["nummer"] or "", datum_text(x["datum"]), x["vorgang"], p_._p(x["referenz"], p_.S_KLEIN),
                      p_._z(x["netto"], 2) if isinstance(x["netto"], (int, float)) else ""])
    if len(daten) == 1:
        daten.append(["–", "", "", "", ""])
    inhalt += [p_._tabelle(daten, [w * mm for w in (34, 26, 30, 66, 30)], zebra=False), Spacer(1, 5 * mm)]
    inhalt.append(p_._p("Weitere Daten", p_.S_H2))
    inhalt.append(p_._p("Mail-Adressen im Versandverlauf: " + (", ".join(a["mails"]) or "keine") + ". "
                        f"Kundenvorgaben: {a['vorgaben']}, Importprofile: {a['importprofile']}. "
                        "Angebote im Archiv (Datei → Archiv durchsuchen) sind hier nicht enthalten.", p_.S))
    doc.build(inhalt, canvasmaker=leinwand)
    return pfad


def frist_anwenden(db, jahre=None, heute=None):
    """Frist für abgelehnte Angebote (siehe oben). jahre None = Einstellung datenschutz_jahre (0 = aus).
    Ergebnis dict(angebote, mails, kunden) oder None (aus)."""
    heute = _heute(heute)
    try:
        jahre = int(jahre if jahre is not None else db.einstellung(EINSTELLUNG) or 0)
    except (TypeError, ValueError):
        jahre = 0
    if jahre <= 0:
        return None
    try:
        grenze = heute.replace(year=heute.year - jahre)
    except ValueError:          # 29. Februar
        grenze = heute.replace(year=heute.year - jahre, day=28)
    alle = [dict(r) for r in db.con.execute("SELECT id, kundennr, datum, vorgang, versand FROM angebote")]
    alt = [a for a in alle if a.get("vorgang") == "Abgelehnt" and str(a.get("datum") or "9") < grenze.isoformat()]
    out = dict(angebote=0, mails=0, kunden=0)
    for a in alt:
        neu, n = _mails_entfernen(_versand(a.get("versand")))
        if n:
            db.versand_setzen(a["id"], neu)
            out["angebote"] += 1
            out["mails"] += n
    alt_ids = {a["id"] for a in alt}
    for kn in sorted({a["kundennr"] for a in alt if a.get("kundennr")}):
        if all(a["id"] in alt_ids for a in alle if a.get("kundennr") == kn):
            k = db.kunde(kn)
            if k is not None and not ist_anonym(k):
                anonymisieren(db, kn, heute=heute, angebote=alt_ids)
                out["kunden"] += 1
    return out


def beim_start(db, heute=None):
    """Frist höchstens einmal am Tag anwenden (nicht im Lesemodus). Ergebnis wie frist_anwenden oder None."""
    heute = _heute(heute)
    if getattr(db, "nur_lesen", False) or db.einstellung(ZULETZT) == heute.isoformat():
        return None
    erg = frist_anwenden(db, heute=heute)
    if erg is not None:
        db.einstellung_setzen(ZULETZT, heute.isoformat())
    return erg


def text(e):
    if not e["kunde"] and not e["angebote"]:
        return "Kein Kunde und keine Angebote mit dieser Kundennummer."
    return (f"Anonymisiert: {', '.join(e['felder']) or 'Kundenstamm schon anonym'}; "
            f"{e['angebote']} Angebot(e) geändert, {e['mails']} Mail-Adresse(n) entfernt. Preise und Zahlen bleiben.")
