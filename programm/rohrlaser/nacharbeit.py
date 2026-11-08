"""Aus Nacharbeit lernen (Paket D, E5, 03.11.2026).

Ändert jemand nach dem STEP-Import beim selben Kunden immer wieder dasselbe – Werkstoff der Rohrlaserteile,
dieselbe Zusatzarbeit an Teilen, Stangenlänge im Kopf –, merkt das Programm das je Angebot. Ab dem dritten Angebot
mit derselben Änderung schlägt eine Einblendung vor, sie ins Importprofil des Kunden (Werkstoff, Zusatzarbeit) bzw. in
die Kundenvorgaben (Stangenlänge) zu übernehmen; künftig macht der Import das dann selbst. „Nicht mehr fragen“ merkt
die Ablehnung. Gemerkt wird in der Einstellung 'nacharbeit_gelernt' (seit 08.11.2026 über den gemeinsamen Ordner geteilt,
Lernzentrale lernen.py). Ohne Qt."""

SCHWELLE = 3
EINSTELLUNG = "nacharbeit_gelernt"
ARTEN = {"werkstoff": "Werkstoff", "zusatz": "Zusatzarbeit", "stange": "Stangenlänge"}


def _daten(db):
    d = db.einstellung(EINSTELLUNG)
    return d if isinstance(d, dict) else {}


def _schreiben(db, d):
    if getattr(db, "nur_lesen", None):
        return
    try:
        db.einstellung_setzen(EINSTELLUNG, d)
    except Exception:
        pass


def _schluessel(kundennr, art, wert):
    return f"{kundennr}|{art}|{wert}"


def schon_vorgabe(db, kundennr, art, wert):
    """True, wenn Importprofil bzw. Kundenvorgaben das schon so vorgeben."""
    from . import importprofil, kundenvorgabe
    if art == "stange":
        v = kundenvorgabe.fuer_kunde(db, kundennr) or {}
        try:
            return float(v.get("stange") or 0) == float(wert)
        except (TypeError, ValueError):
            return False
    vorg = importprofil.vorgaben(importprofil.fuer_kunde(db, kundennr))
    if art == "werkstoff":
        return vorg.get("werkstoff") == wert
    return str(wert).casefold() in {z.casefold() for z in vorg.get("zusatz") or ()}


def merken(db, kundennr, angebot_id, art, wert):
    """Eine Änderung nach dem Import merken. Ergebnis: Vorschlag dict(kundennr, art, wert, n) ab SCHWELLE Angeboten,
    sonst None."""
    if not kundennr or wert in (None, "") or art not in ARTEN or schon_vorgabe(db, kundennr, art, wert):
        return None
    d = _daten(db)
    k = _schluessel(kundennr, art, wert)
    e = d.get(k) or dict(angebote=[], status="")
    if e.get("status") == "vergessen":         # in der Lernzentrale vergessen: neu anfangen
        e = dict(angebote=[], status="")
    if angebot_id not in e["angebote"]:
        e["angebote"] = (e["angebote"] + [angebot_id])[-20:]
    d[k] = e
    _schreiben(db, d)
    if e["status"] or len(e["angebote"]) < SCHWELLE:
        return None
    return dict(kundennr=kundennr, art=art, wert=wert, n=len(e["angebote"]))


def text(v):
    w = f"{v['wert']} mm" if v["art"] == "stange" else v["wert"]
    return (f"{ARTEN[v['art']]} {w} haben Sie bei Kunde {v['kundennr']} schon in {v['n']} Angeboten nach dem Import "
            f"gesetzt. Künftig automatisch?")


def uebernehmen(db, v):
    """Vorschlag ins Importprofil bzw. die Kundenvorgaben schreiben. Ergebnis: Text."""
    from . import automatik, importprofil, kundenvorgabe
    if v["art"] == "stange":
        z = kundenvorgabe.fuer_kunde(db, v["kundennr"])
        if z is None:
            db.neu("kundenvorgaben", dict(kundennr=v["kundennr"], stange=float(v["wert"])))
        else:
            db.aendern("kundenvorgaben", z["id"], "stange", float(v["wert"]))
        t = f"Kundenvorgaben {v['kundennr']}: Stangenlänge {v['wert']} mm"
    else:
        t = importprofil.merken(db, v["kundennr"], {"werkstoff_id": v["wert"]} if v["art"] == "werkstoff"
                                else {"zusatz": [v["wert"]]})
    _status(db, v, "gelernt")
    automatik.merken(db, "nacharbeit", t)
    return t


def ablehnen(db, v):
    _status(db, v, "abgelehnt")


def _status(db, v, status):
    d = _daten(db)
    k = _schluessel(v["kundennr"], v["art"], v["wert"])
    d[k] = dict(d.get(k) or dict(angebote=[]), status=status)
    _schreiben(db, d)


def anbieten(seite, art, wert):
    """Aus der Angebotsseite: merken und ab der Schwelle die Einblendung „Übernehmen“ zeigen (nur für Angebote aus
    dem STEP-Import). Ergebnis: Vorschlag oder None."""
    try:
        if seite.fremd() or seite.db.nur_lesen or not any(p.get("step_datei") or p.get("schneidweg")
                                                          for p in seite.positionen):
            return None
        v = merken(seite.db, seite.kopf.get("kundennr"), seite.id, art, wert)
    except Exception:
        return None
    if v:
        _status(seite.db, v, "gefragt")         # einmal fragen; das Protokoll behält es
        seite.f.meldung(text(v), aktion=("Übernehmen", lambda: seite.f.meldung(uebernehmen(seite.db, v)
                                                                               + " – gilt ab dem nächsten Import.")))
    return v
