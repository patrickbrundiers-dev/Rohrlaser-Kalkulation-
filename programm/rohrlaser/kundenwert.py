"""Kundenwert (OFFER-012, Plan Phase 3 und 4, Paket D, Patrick 13.11.2026 „Alles einbauen“): je Kunde und Jahr
Angebote, Aufträge, Auftragsquote, Umsatz und Deckungsbeitrag.

Herkunft je Zahl (nichts geschätzt):
- Angebote/Aufträge: alle eigenen Angebote des Jahres (Datum), ohne ersetzte Fassungen; Auftrag = Vorgang Beauftragt
- Umsatz: Verkaufspreis netto laut Angebot (beim letzten Öffnen gemerkt), nur Aufträge
- Deckungsbeitrag Ist und Soll: nur aus der Nachkalkulation (Erlös − Einzelkosten, wie dort gerechnet), mit der
  Zahl der nachkalkulierten Aufträge; ohne Nachkalkulation bleibt er leer statt geschätzt
Nur Anzeige, ändert nichts. Ohne Qt."""
import json


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else None


def zeilen(db, jahr=None):
    """[dict(kundennr, kunde, jahr, angebote, auftraege, quote, umsatz, db_ist, db_soll, nachkalkuliert,
    db_quote)] nach Deckungsbeitrag Ist, dann Umsatz (größter zuerst). jahr = '2026' filtert."""
    sql = ("SELECT kundennr, kunde, datum, vorgang, vk_netto, nachkalkulation FROM angebote "
           "WHERE COALESCE(fremd, 0) = 0 AND COALESCE(ersetzt_durch, '') = ''")
    je = {}
    for r in db.con.execute(sql):
        r = dict(r)
        j = str(r.get("datum") or "")[:4]
        if not j.isdigit() or (jahr and j != str(jahr)):
            continue
        name = str(r.get("kunde") or "").strip()
        schl = (str(r.get("kundennr") or "").strip() or name.lower(), j)
        z = je.setdefault(schl, dict(kundennr=str(r.get("kundennr") or ""), kunde=name, jahr=j, angebote=0,
                                     auftraege=0, umsatz=0.0, db_ist=0.0, db_soll=0.0, nachkalkuliert=0,
                                     erloes_nk=0.0))
        z["kunde"] = z["kunde"] or name
        z["angebote"] += 1
        if r.get("vorgang") != "Beauftragt":
            continue
        z["auftraege"] += 1
        z["umsatz"] += _n(r.get("vk_netto")) or 0.0
        try:
            nk = json.loads(r["nachkalkulation"]) if r.get("nachkalkulation") else None
        except ValueError:
            nk = None
        soll = (nk or {}).get("soll") if isinstance(nk, dict) else None
        d = (soll or {}).get("db") if isinstance(soll, dict) else None
        if isinstance(d, list) and len(d) == 2 and _n(d[1]) is not None:
            z["nachkalkuliert"] += 1
            z["db_ist"] += _n(d[1])
            z["db_soll"] += _n(d[0]) or 0.0
            e = (soll or {}).get("erloes")
            z["erloes_nk"] += _n(e[1]) if isinstance(e, list) and len(e) > 1 and _n(e[1]) is not None else 0.0
    out = []
    for z in je.values():
        z["quote"] = z["auftraege"] / z["angebote"] if z["angebote"] else None
        z["db_quote"] = z["db_ist"] / z["erloes_nk"] if z["nachkalkuliert"] and z["erloes_nk"] else None
        if not z["nachkalkuliert"]:
            z["db_ist"] = z["db_soll"] = None
        out.append(z)
    out.sort(key=lambda z: (-(z["db_ist"] if z["db_ist"] is not None else float("-inf")), -z["umsatz"],
                            z["kunde"].lower()))
    return out


def jahre(db):
    """Jahre mit Angeboten, neuestes zuerst."""
    j = {str(r[0] or "")[:4] for r in db.con.execute("SELECT datum FROM angebote")}
    return sorted((x for x in j if x.isdigit()), reverse=True)
