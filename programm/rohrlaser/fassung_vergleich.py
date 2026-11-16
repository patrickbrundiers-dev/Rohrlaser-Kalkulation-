"""Fassungen vergleichen (Vorschlag F2, Patrick 02.11.2026 „Alle weiter“ = F2a, nur intern).

Zu einer Fassung („2026-00517-2“) die vorige (die mit ersetzt_durch = diese Nummer) suchen und je Position zeigen,
was sich geändert hat: neu, entfällt, Menge, Länge, Profil, Werkstoff, Schneidweg, Bezeichnung und Preis je Teil,
dazu die Summe netto alt/neu. Positionen gehören zusammen über die Artikelnummer, ohne Artikelnummer über die
Positionsnummer. Gerechnet wird jede Fassung wie im Angebotsfenster (eigene festgeschriebene Preise, eigener
Schnittplan; ohne Schnittplan wird für den Vergleich optimiert, nichts gespeichert). Ohne Qt."""
from . import preis_simulator, rechnen
from .angebot import aktiv

FELDER = (("stueck", "Menge"), ("laenge", "Länge"), ("profil_id", "Profil"), ("werkstoff_id", "Werkstoff"),
          ("schneidweg", "Schneidweg"), ("bezeichnung", "Bezeichnung"))


def vorgaenger(db, angebot_id):
    """ID der vorigen Fassung oder None."""
    a = db.angebot(angebot_id) or {}
    r = db.con.execute("SELECT id FROM angebote WHERE ersetzt_durch=? ORDER BY id DESC", (a.get("nummer"),)).fetchone()
    return r[0] if r else None


def _preise(db, angebot_id, aktuell=None, einst=None):
    a = db.angebot(angebot_id)
    pos = [p for p in db.positionen(angebot_id) if aktiv(p)]
    k, tab, e = preis_simulator.grundlage(db, a, aktuell, einst)
    erg = a.get("ergebnis") or rechnen.optimieren(a, pos, k, tab, e)
    zeilen, s = rechnen.kalkulation(a, pos, erg, k, tab, e)
    return a, pos, {p["id"]: z for p, z in zip(pos, zeilen) if z}, s


def _schluessel(p):
    return ("A", str(p.get("artikel")).strip()) if p.get("artikel") else ("P", str(p.get("pos")))


def _t(w):
    from .stammdaten import zahl_als_text
    if isinstance(w, (int, float)) and not isinstance(w, bool):
        return zahl_als_text(w, 0 if float(w).is_integer() else 1)
    return str(w or "–")


def vergleich(db, alt_id, neu_id):
    """dict(alt=Nummer, neu=Nummer, netto_alt, netto_neu, zeilen=[dict(pos, artikel, bezeichnung, art ('neu',
    'entfällt', 'geändert', 'gleich'), aenderungen=[Text], preis_alt, preis_neu)])."""
    aktuell, einst = (db.kontext(), db.tabellen()), db.einstellungen()
    ka, pa, za, sa = _preise(db, alt_id, aktuell, einst)
    kn, pn, zn, sn = _preise(db, neu_id, aktuell, einst)
    alt = {_schluessel(p): p for p in pa}
    zeilen, gesehen = [], set()
    for p in pn:
        s = _schluessel(p)
        q = alt.get(s)
        gesehen.add(s)
        preis_neu = (zn.get(p["id"]) or {}).get("preis_teil")
        if q is None:
            zeilen.append(dict(pos=p.get("pos"), artikel=p.get("artikel") or "", bezeichnung=p.get("bezeichnung") or "",
                               art="neu", aenderungen=[], preis_alt=None, preis_neu=preis_neu))
            continue
        aend = [f"{titel} {_t(q.get(f))} → {_t(p.get(f))}" for f, titel in FELDER if q.get(f) != p.get(f)]
        preis_alt = (za.get(q["id"]) or {}).get("preis_teil")
        geaendert = aend or (preis_alt is not None and preis_neu is not None and abs(preis_alt - preis_neu) >= 0.005)
        zeilen.append(dict(pos=p.get("pos"), artikel=p.get("artikel") or "", bezeichnung=p.get("bezeichnung") or "",
                           art="geändert" if geaendert else "gleich", aenderungen=aend, preis_alt=preis_alt,
                           preis_neu=preis_neu))
    for s, q in alt.items():
        if s not in gesehen:
            zeilen.append(dict(pos=q.get("pos"), artikel=q.get("artikel") or "", bezeichnung=q.get("bezeichnung") or "",
                               art="entfällt", aenderungen=[], preis_alt=(za.get(q["id"]) or {}).get("preis_teil"),
                               preis_neu=None))
    return dict(alt=ka.get("nummer"), neu=kn.get("nummer"), netto_alt=sa.get("verkauf"), netto_neu=sn.get("verkauf"),
                zeilen=zeilen)


def html(v, nur_aenderungen=False):
    """Tabelle für das Fenster."""
    from html import escape
    from .stammdaten import zahl_als_text as zahl
    farbe = {"neu": "#1E6B34", "entfällt": "#B42318", "geändert": "#7A5A00", "gleich": "#5B6573"}
    reihen = ""
    for z in v["zeilen"]:
        if nur_aenderungen and z["art"] == "gleich":
            continue
        preis = " → ".join(zahl(p, 2) if p is not None else "–" for p in (z["preis_alt"], z["preis_neu"]))
        reihen += (f"<tr><td>{escape(str(z['pos'] or ''))}</td><td>{escape(z['artikel'])}</td>"
                   f"<td>{escape(z['bezeichnung'])}</td><td style='color:{farbe[z['art']]}'><b>{z['art']}</b></td>"
                   f"<td>{escape('; '.join(z['aenderungen']))}</td><td align='right'>{preis}</td></tr>")
    kopf = "".join(f"<th align='left'>{t}</th>" for t in ("Pos.", "Artikel", "Bezeichnung", "Art", "Änderung",
                                                          "Preis je Teil [€]"))
    na, nn = v["netto_alt"] or 0, v["netto_neu"] or 0
    p = 100 * (nn / na - 1) if na else 0
    return (f"<p><b>{escape(str(v['alt']))} → {escape(str(v['neu']))}</b>: netto {zahl(na, 2)} € → {zahl(nn, 2)} € "
            f"({'+' if p >= 0 else '−'}{zahl(abs(p), 1)} %)</p>"
            f"<table cellspacing='0' cellpadding='4' border='0'><tr>{kopf}</tr>{reihen}</table>")
