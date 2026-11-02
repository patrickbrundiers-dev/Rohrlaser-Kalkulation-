"""Teilekatalog je Kunde (Vorschlag F3a, Patrick 02.11.2026 „Alle weiter“).

Alle Teile, die ein Kunde je angefragt hat, eine Zeile je Artikel (Artikelnummer, ohne Artikelnummer Bezeichnung +
Profil + Länge): letzter Preis je Stück aus den gespeicherten Staffelpreisen des neuesten Angebots, Datum, Vorgang,
Anzahl Angebote und Aufträge, ob eine Nachkalkulation vorliegt. Abgelöste Fassungen (ersetzt_durch) zählen nicht.
„Neues Angebot aus Auswahl“ legt im Fenster ein Angebot für den Kunden an und übernimmt die gewählten Positionen
(position_kopie). Ohne Qt."""
import csv
import io
import json

from .wiederholteile import preis_aus_staffeln

SPALTEN = (("Artikel", "artikel"), ("Bezeichnung", "bezeichnung"), ("Profil", "profil_id"), ("Werkstoff", "werkstoff"),
           ("Länge [mm]", "laenge"), ("Letzter Preis [€/Stk]", "preis"), ("bei Menge", "menge"), ("Datum", "datum"),
           ("Angebot", "nummer"), ("Vorgang", "vorgang"), ("Angebote", "angebote"), ("Aufträge", "auftraege"),
           ("Nachkalkulation", "nachkalk"))


def _txt(w):
    return str(w or "").strip()


def schluessel(p):
    """Artikel eines Teils: Artikelnummer (ohne Groß/klein), sonst Bezeichnung + Profil + Länge."""
    art = _txt(p.get("artikel")).casefold()
    if art:
        return ("a", art)
    try:
        laenge = round(float(p.get("laenge") or 0), 1)
    except (TypeError, ValueError):
        laenge = 0.0
    return ("g", _txt(p.get("bezeichnung")).casefold(), _txt(p.get("profil_id")), laenge)


def katalog(db, kundennr):
    """[dict] je Artikel des Kunden, nach Artikel sortiert; jede Zeile mit quelle=(angebot_id, positions_id) des
    neuesten Angebots."""
    if not _txt(kundennr):
        return []
    sql = ("SELECT p.id, p.angebot_id, p.pos, p.artikel, p.bezeichnung, p.profil_id, p.werkstoff_id AS werkstoff, p.laenge, p.stueck, "
           "a.nummer, a.datum, a.vorgang, a.staffelpreise, a.nachkalkulation IS NOT NULL AS nk "
           "FROM positionen p JOIN angebote a ON a.id = p.angebot_id "
           "WHERE a.kundennr = ? AND (a.ersetzt_durch IS NULL OR a.ersetzt_durch = '')")
    zeilen = [dict(r) for r in db.con.execute(sql, [kundennr])]
    gruppen = {}
    for z in zeilen:
        if not (_txt(z["artikel"]) or _txt(z["bezeichnung"]) or _txt(z["profil_id"])):
            continue
        gruppen.setdefault(schluessel(z), []).append(z)
    out = []
    staffeln = {}
    for liste in gruppen.values():
        liste.sort(key=lambda z: (_txt(z["datum"]), z["angebot_id"]), reverse=True)
        neu = liste[0]
        preis = menge = None
        for z in liste:             # neuester Preis, den es gibt
            if z["angebot_id"] not in staffeln:
                try:
                    staffeln[z["angebot_id"]] = json.loads(z["staffelpreise"]) if z["staffelpreise"] else None
                except ValueError:
                    staffeln[z["angebot_id"]] = None
            pm = preis_aus_staffeln(staffeln[z["angebot_id"]], z["pos"], z["stueck"])
            if pm:
                menge, preis = pm
                break
        angebote = {z["angebot_id"] for z in liste}
        out.append(dict(artikel=_txt(neu["artikel"]), bezeichnung=_txt(neu["bezeichnung"]),
                        profil_id=_txt(neu["profil_id"]), werkstoff=_txt(neu["werkstoff"]), laenge=neu["laenge"],
                        preis=preis, menge=menge, datum=_txt(neu["datum"])[:10], nummer=neu["nummer"],
                        vorgang=neu["vorgang"] or "Entwurf", angebote=len(angebote),
                        auftraege=len({z["angebot_id"] for z in liste if z["vorgang"] == "Beauftragt"}),
                        nachkalk="ja" if any(z["nk"] for z in liste) else "",
                        quelle=(neu["angebot_id"], neu["id"])))
    out.sort(key=lambda r: (r["artikel"].casefold() or "~", r["bezeichnung"].casefold()))
    return out


def csv_text(liste):
    """Katalog als CSV (Semikolon, Dezimalkomma, für Excel)."""
    from .stammdaten import zahl_als_text as zahl
    f = io.StringIO()
    w = csv.writer(f, delimiter=";", lineterminator="\r\n")
    w.writerow([t for t, _ in SPALTEN])
    for r in liste:
        w.writerow([zahl(r[n], 2) if n in ("preis", "laenge") and r[n] is not None else
                    ("" if r[n] is None else r[n]) for _, n in SPALTEN])
    return f.getvalue()


def nach_angebot(auswahl):
    """{angebot_id: [Positions-ID]} der gewählten Katalogzeilen (für das Übernehmen je Quell-Angebot)."""
    out = {}
    for r in auswahl:
        a, p = r["quelle"]
        out.setdefault(a, []).append(p)
    return out
