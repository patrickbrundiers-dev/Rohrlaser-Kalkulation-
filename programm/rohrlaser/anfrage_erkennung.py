"""Anfragen Paket 6 (Patrick 14.11.2026 „Alle vier“): was das Programm in einer Anfrage aus Outlook erkannt hat, was
fehlt, die Rückfrage an den Kunden und Wiederholteile.

  erkannt(db, akte, text)      Anfrage-Nr., Wunschtermin, Werkstoff, Staffelmengen (mail_fundstellen: je Wert die
                               Fundstelle und sicher/prüfen/unsicher). Nur Anzeige: übernommen wird erst beim
                               Kalkulieren über den Prüfdialog.
  fehlt(werte, akte, text)     was für ein Angebot noch fehlt, z. B. „Werkstoff nicht genannt“.
  rueckfrage_text(...)         Text der Rückfrage (Anrede + fehlende Angaben); geöffnet wird sie in Outlook als
                               Antwort auf die Mail des Kunden, nie automatisch gesendet.
  wiederholt(db, akten, akte, text)
                               dieselbe STEP-Datei in einer früheren Anfrage mit Angebot oder bekannte Artikelnummern
                               des Kunden (wiederholanfrage.treffer): Angebot, Datum, Preis.
Ohne Qt, ohne Netz."""
import re

FELDER = ("anfrage_nr", "termin", "werkstoff", "staffel")
FEHLT = dict(werkstoff="Werkstoff nicht genannt", werkstoff_unsicher="Werkstoff nicht eindeutig",
             termin="Wunschtermin nicht genannt", menge="Stückzahl nicht genannt",
             zeichnung="Keine Zeichnung oder STEP-Datei")
FRAGE = dict(werkstoff="Welcher Werkstoff (Werkstoffnummer bzw. Güte) ist gewünscht?",
             werkstoff_unsicher="Welcher Werkstoff genau ist gemeint (bitte mit Werkstoffnummer)?",
             termin="Bis wann benötigen Sie die Teile (Wunschtermin)?",
             menge="Welche Stückzahl(en) sollen wir anbieten?",
             zeichnung="Bitte senden Sie uns eine Zeichnung oder STEP-Datei der Teile.")
_MENGE = re.compile(r"\b\d[\d.]*\s*(?:stk\.?|stück|st\.|pcs|teile)\b|\b(?:stückzahl|menge|anzahl)\s*:?\s*\d",
                    re.IGNORECASE)


def erkannt(db, akte, text, heute=None):
    """[dict(feld, titel, wert, fundstelle, sicherheit)] für die Felder FELDER, aus Mailtext und Betreff."""
    from . import mail_fundstellen
    try:
        werkstoffe = db.zeilen("werkstoffe")
    except Exception:       # noqa: BLE001
        werkstoffe = []
    quellen = [("Mail", text or "")]
    if akte is not None and akte.betreff:
        quellen.append(("Betreff", akte.betreff))
    try:
        werte = mail_fundstellen.zusammen(quellen, werkstoffe=werkstoffe, heute=heute)
    except Exception:       # noqa: BLE001 – Erkennung ist Hilfe, nie ein Fehler
        return []
    return [w for w in werte if w["feld"] in FELDER]


def fehlt(werte, akte, text=""):
    """Schlüssel der fehlenden Angaben (FEHLT/FRAGE), in fester Reihenfolge."""
    felder = {w["feld"]: w for w in werte}
    out = []
    w = felder.get("werkstoff")
    if w is None:
        out.append("werkstoff")
    elif w["sicherheit"] == "unsicher":
        out.append("werkstoff_unsicher")
    if "termin" not in felder:
        out.append("termin")
    if "staffel" not in felder and not _MENGE.search(text or ""):
        out.append("menge")
    if akte is not None and not any(d["art"] in ("step", "pdf", "dxf", "zip") for d in akte.dateien()):
        out.append("zeichnung")
    return out


def fehlt_text(schluessel):
    return [FEHLT[k] for k in schluessel]


def rueckfrage_text(kunde, akte, schluessel, absender=""):
    """Text der Rückfrage: Anrede, Bezug, je fehlender Angabe eine Frage, Gruß (die Signatur setzt Outlook)."""
    from . import angebot_mail
    betreff = (akte.betreff if akte is not None else "") or "Ihre Anfrage"
    zeilen = [angebot_mail.anrede(kunde), "",
              f"vielen Dank für Ihre Anfrage „{betreff}“. Damit wir Ihnen ein Angebot erstellen können, "
              "benötigen wir noch folgende Angaben:", ""]
    zeilen += [f"- {FRAGE[k]}" for k in schluessel] or ["- "]
    zeilen += ["", "Vielen Dank im Voraus.", "", "Mit freundlichen Grüßen"]
    if absender:
        zeilen.append(absender)
    return "\n".join(zeilen)


def rueckfrage_betreff(akte):
    b = (akte.betreff if akte is not None else "") or "Ihre Anfrage"
    return b if b.lower().startswith(("aw:", "re:")) else f"AW: {b}"


def _angebot(db, nummer):
    try:
        z = db.con.execute("SELECT id, nummer, datum, vk_netto, vorgang FROM angebote WHERE nummer=? "
                           "ORDER BY id DESC LIMIT 1", (nummer,)).fetchone()
    except Exception:       # noqa: BLE001
        return None
    return dict(id=z[0], nummer=z[1], datum=str(z[2] or "")[:10], preis=z[3], vorgang=z[4] or "Entwurf") if z else None


def wiederholt(db, akten, akte, text):
    """Wiederholteile: [dict(art='step'|'artikel', was, angebot_id, nummer, datum, preis, vorgang, quelle)],
    neueste zuerst; quelle = Katalogzeile (Artikel) bzw. None (ganzes Angebot der früheren Anfrage)."""
    from . import anfragen_akten as ak
    from . import wiederholanfrage
    out, gesehen = [], set()
    for frueher, name in ak.gleiche_step(akten, akte):
        for nummer in reversed(frueher.stand.get("angebote") or []):
            ang = _angebot(db, nummer)
            if ang and ang["id"] not in gesehen:
                gesehen.add(ang["id"])
                out.append(dict(art="step", was=f"{name} (wie Anfrage {frueher.nr})", angebot_id=ang["id"],
                                nummer=ang["nummer"], datum=ang["datum"], preis=ang["preis"],
                                vorgang=ang["vorgang"], quelle=None, menge=None))
                break
    try:
        treffer = wiederholanfrage.treffer(db, akte.kunde, text) if akte.kunde else []
    except Exception:       # noqa: BLE001
        treffer = []
    for r in treffer:
        a_id = (r.get("quelle") or (None, None))[0]
        if a_id in gesehen:
            continue
        out.append(dict(art="artikel", was=f"Artikel {r['artikel']}" + (f" {r['bezeichnung']}" if r.get("bezeichnung")
                                                                        else ""),
                        angebot_id=a_id, nummer=r.get("nummer") or "", datum=r.get("datum") or "",
                        preis=r.get("preis"), vorgang=r.get("vorgang") or "", quelle=r, menge=r.get("menge")))
    return out


def euro(wert):
    if wert in (None, ""):
        return ""
    return f"{float(wert):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
