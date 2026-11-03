"""Lieferantenangebote (Vorschlag F4a) und Lieferantenbewertung (H7a), 02.11.2026.

Zu jeder Materialanfrage eines Angebots trägt man die Antworten der Lieferanten von Hand ein (Zusatzdaten
'lieferantenangebote': [dict(lieferant, datum, profil_id, werkstoff_id, basis, preis, laenge, lieferzeit, gueltig_bis,
gewaehlt, eingang)]). Der Vergleich rechnet jede Antwort auf €/m um (€/kg × kg/m, €/Stange ÷ Stangenlänge) und
markiert je Abmessung die günstigste. „Übernehmen“ schreibt Preis, Basis, Lieferant und „Gültig ab“ = heute in die
Stammdaten Preise (wie der ERP-Preisvorschlag) und merkt die Antwort als gewählt. „Wareneingang“ trägt das
Lieferdatum ein.

Bewertung je Lieferant über alle Angebote: Anzahl Antworten, mittlerer Preisrang (1 = günstigste je Abmessung),
Termintreue (Wareneingang bis Antwortdatum + Lieferzeit) und Reklamationen mit Ursache Material bei Aufträgen, für
die dieser Lieferant gewählt war. Ohne Qt."""
import datetime

SCHLUESSEL = "lieferantenangebote"


def _n(w):
    try:
        return float(w) if w not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _d(t):
    try:
        return datetime.date.fromisoformat(str(t)[:10])
    except (TypeError, ValueError):
        return None


def liste(db, angebot_id):
    return list(db.zusatz(angebot_id, SCHLUESSEL, []) or [])


def erfassen(db, angebot_id, lieferant, profil_id, werkstoff_id, basis, preis, lieferzeit=None, laenge=None,
             gueltig_bis=None, heute=None):
    """Antwort eintragen. Ergebnis: Index der Antwort. ValueError ohne Lieferant, Abmessung oder Preis."""
    from .stammdaten import PREISBASIS
    if not str(lieferant or "").strip() or not profil_id or not werkstoff_id:
        raise ValueError("Bitte Lieferant, Profil und Werkstoff angeben.")
    if _n(preis) <= 0 or basis not in PREISBASIS:
        raise ValueError("Bitte einen Preis und die Preisbasis (€/kg, €/m, €/Stange) angeben.")
    heute = heute or datetime.date.today()
    e = dict(lieferant=str(lieferant).strip(), datum=heute.isoformat(), profil_id=profil_id, werkstoff_id=werkstoff_id,
             basis=basis, preis=_n(preis), laenge=_n(laenge) or None, lieferzeit=int(_n(lieferzeit)) or None,
             gueltig_bis=gueltig_bis or None, gewaehlt=False, eingang=None)
    alle = liste(db, angebot_id) + [e]
    db.zusatz_setzen(angebot_id, SCHLUESSEL, alle)
    return len(alle) - 1


def je_m(e, k):
    """Preis der Antwort in €/m (None, wenn nicht umrechenbar)."""
    from .rechnen import kg_je_m
    if e["basis"] == "€/m":
        return e["preis"]
    if e["basis"] == "€/kg":
        kg = kg_je_m(e["profil_id"], e["werkstoff_id"], k)
        return e["preis"] * kg if kg else None
    if e["basis"] == "€/Stange" and _n(e.get("laenge")):
        return e["preis"] / (_n(e["laenge"]) / 1000)
    return None


def vergleich(antworten, k):
    """[dict(antwort, index, je_m, bester, rang)] nach Abmessung und Preis sortiert; rang 1 = günstigste der
    Abmessung."""
    zeilen = [dict(antwort=e, index=i, je_m=je_m(e, k)) for i, e in enumerate(antworten)]
    gruppen = {}
    for z in zeilen:
        gruppen.setdefault((z["antwort"]["profil_id"], z["antwort"]["werkstoff_id"]), []).append(z)
    out = []
    for _, g in sorted(gruppen.items()):
        g.sort(key=lambda z: (z["je_m"] is None, z["je_m"] or 0))
        for r, z in enumerate(g, 1):
            z.update(rang=r if z["je_m"] is not None else None, bester=r == 1 and z["je_m"] is not None)
        out += g
    return out


def uebernehmen(db, angebot_id, index, heute=None):
    """Antwort in die Stammdaten Preise (Profil + Werkstoff) und als gewählt merken. Ergebnis: ID der Preiszeile."""
    heute = heute or datetime.date.today()
    alle = liste(db, angebot_id)
    e = alle[index]
    werte = dict(basis=e["basis"], preis=e["preis"], gueltig_ab=heute.isoformat(), lieferant=e["lieferant"],
                 bemerkung=f"aus Lieferantenangebot vom {e['datum']}")
    if e["basis"] == "€/Stange" and e.get("laenge"):
        werte["lieferlaenge"] = int(e["laenge"])
    alt = next((z for z in db.zeilen("preise") if z.get("profil_id") == e["profil_id"]
                and z.get("werkstoff_id") == e["werkstoff_id"]), None)
    if alt:
        for f, w in werte.items():
            db.aendern("preise", alt["id"], f, w)
        i = alt["id"]
    else:
        i = db.neu("preise", dict(werte, profil_id=e["profil_id"], werkstoff_id=e["werkstoff_id"]))
    for j, x in enumerate(alle):
        if (x["profil_id"], x["werkstoff_id"]) == (e["profil_id"], e["werkstoff_id"]):
            x["gewaehlt"] = j == index
    db.zusatz_setzen(angebot_id, SCHLUESSEL, alle)
    return i


def eingang_setzen(db, angebot_id, index, datum=None):
    alle = liste(db, angebot_id)
    alle[index]["eingang"] = (datum or datetime.date.today()).isoformat()
    db.zusatz_setzen(angebot_id, SCHLUESSEL, alle)


def puenktlich(e):
    """True/False, ob der Wareneingang bis Antwortdatum + Lieferzeit (Kalendertage) kam; None ohne Angaben."""
    ein, ab = _d(e.get("eingang")), _d(e.get("datum"))
    if not ein or not ab or not e.get("lieferzeit"):
        return None
    return ein <= ab + datetime.timedelta(days=int(e["lieferzeit"]))


def bewertung(db, k):
    """Je Lieferant dict(lieferant, antworten, rang (Mittel), termintreue (Anteil oder None), lieferungen,
    reklamationen), nach Rang sortiert."""
    from . import reklamation
    je = {}
    for (aid,) in db.con.execute("SELECT id FROM angebote WHERE zusatz LIKE '%lieferantenangebote%'"):
        antworten = liste(db, aid)
        for z in vergleich(antworten, k):
            e = z["antwort"]
            b = je.setdefault(e["lieferant"], dict(lieferant=e["lieferant"], antworten=0, raenge=[], p=[], rekl=0))
            b["antworten"] += 1
            if z["rang"]:
                b["raenge"].append(z["rang"])
            p = puenktlich(e)
            if p is not None:
                b["p"].append(p)
        gewaehlt = {e["lieferant"] for e in antworten if e.get("gewaehlt")}
        if gewaehlt:
            try:
                rekl = [r for r in reklamation.liste(db, aid)
                        if "material" in f"{r.get('ursache') or ''} {r.get('fehlerart') or ''}".lower()]
            except Exception:       # ohne Reklamations-Tabelle keine Reklamationen
                rekl = []
            for name in gewaehlt:
                je[name]["rekl"] += len(rekl)
    out = []
    for b in je.values():
        out.append(dict(lieferant=b["lieferant"], antworten=b["antworten"],
                        rang=sum(b["raenge"]) / len(b["raenge"]) if b["raenge"] else None,
                        termintreue=sum(b["p"]) / len(b["p"]) if b["p"] else None, lieferungen=len(b["p"]),
                        reklamationen=b["rekl"]))
    return sorted(out, key=lambda b: (b["rang"] is None, b["rang"] or 0, b["lieferant"].casefold()))


def bewertung_text(b):
    from .stammdaten import zahl_als_text as zahl
    if not b:
        return ""
    teile = [f"Preisrang Ø {zahl(b['rang'], 1)}" if b["rang"] is not None else None,
             f"Termintreue {zahl(100 * b['termintreue'], 0)} %" if b["termintreue"] is not None else None,
             f"{b['reklamationen']} Reklamation(en)" if b["reklamationen"] else None]
    return " · ".join(t for t in teile if t)
