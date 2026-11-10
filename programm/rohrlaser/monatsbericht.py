"""Monatsbericht als PDF (Vorschlag H3b, 02.11.2026, nur per Knopf, nur Admin).

Eine Seite je Monat aus der Datendatei (eigene Angebote mit Angebotsdatum im Monat): Anzahl und Netto der Angebote,
Trefferquote, Auftragseingang (beauftragt), Deckungsbeitrag Soll/Ist der nachkalkulierten Aufträge, Laserstunden der
Aufträge je Maschine, Top-5-Kunden nach Auftragswert und die Absagegründe. Ohne Qt (bis auf das PDF)."""
import calendar
import datetime

from . import absage

MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember")


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0


def bericht(db, jahr, monat):
    """dict(titel, angebote, netto, beauftragt, auftragswert, abgelehnt, trefferquote, db_soll, db_ist, laser {Maschine:
    h}, kunden [(Name, €)], gruende [(Grund, Anzahl)])."""
    from . import auslastung
    von = datetime.date(jahr, monat, 1)
    bis = datetime.date(jahr, monat, calendar.monthrange(jahr, monat)[1])
    alle = [z for z in db.angebote() if not z.get("fremd") and not z.get("ersetzt_durch")
            and von.isoformat() <= str(z.get("datum") or "")[:10] <= bis.isoformat()]
    auftraege = [z for z in alle if z.get("vorgang") == "Beauftragt"]
    abgelehnt = [z for z in alle if z.get("vorgang") == "Abgelehnt"]
    entschieden = len(auftraege) + len(abgelehnt)
    kunden = {}
    for z in auftraege:
        kunden[z.get("kunde") or "ohne Kunde"] = kunden.get(z.get("kunde") or "ohne Kunde", 0.0) + _n(z.get("vk_netto"))
    gruende = {}
    for z in abgelehnt:
        g = (absage.letzte(z) or {}).get("grund") or absage.OHNE_GRUND
        gruende[g] = gruende.get(g, 0) + 1
    laser, db_soll, db_ist = {}, 0.0, 0.0
    aktuell, einst = (db.kontext(), db.tabellen()), db.einstellungen()
    for z in auftraege:
        a = db.angebot(z["id"]) or {}
        try:
            h, _ = auslastung.maschinenzeit(db, a, aktuell, einst)
        except (ValueError, KeyError, ZeroDivisionError, TypeError):
            h = None
        if h:
            laser[a.get("maschine") or "?"] = laser.get(a.get("maschine") or "?", 0.0) + h
        nk = a.get("nachkalkulation") or {}
        werte = ((nk.get("soll") or {}).get("db") or [None, None]) if isinstance(nk, dict) else [None, None]
        db_soll += _n(werte[0])
        db_ist += _n(werte[1])
    try:                        # I12: wo auffällig oft verloren wird (letzte 12 Monate bis Monatsende)
        from . import einsichten
        verlust = einsichten.verlustmuster(db, bis)
    except Exception:
        verlust = []
    return dict(verlust=verlust, titel=f"{MONATE[monat - 1]} {jahr}", von=von, bis=bis, angebote=len(alle),
                netto=sum(_n(z.get("vk_netto")) for z in alle), beauftragt=len(auftraege),
                auftragswert=sum(_n(z.get("vk_netto")) for z in auftraege), abgelehnt=len(abgelehnt),
                trefferquote=len(auftraege) / entschieden if entschieden else None, db_soll=db_soll, db_ist=db_ist,
                laser=laser, kunden=sorted(kunden.items(), key=lambda x: -x[1])[:5],
                gruende=sorted(gruende.items(), key=lambda x: -x[1]))


def pdf(pfad, b, einst):
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer
    from . import pdf as p_
    titel = f"Monatsbericht {b['titel']}"
    doc, leinwand = p_._dokument(pfad, titel, p_._fuss(einst or {}, titel))
    breite = 186 * mm
    z = p_._z
    inhalt = p_._dok_kopf("Monatsbericht", {}, einst or {}, breite,
                          [("Monat", b["titel"]), ("Erstellt", datetime.date.today().strftime("%d.%m.%Y"))])
    kenn = [p_._kopfzeile(["Kennzahl", "Wert"]),
            ["Angebote (Anzahl / netto)", f"{b['angebote']} / {z(b['netto'], 2)} €"],
            ["Auftragseingang (beauftragt)", f"{b['beauftragt']} / {z(b['auftragswert'], 2)} €"],
            ["Abgelehnt", str(b["abgelehnt"])],
            ["Trefferquote", f"{z(100 * b['trefferquote'], 0)} %" if b["trefferquote"] is not None else "–"],
            ["Deckungsbeitrag Soll / Ist (nachkalkuliert)", f"{z(b['db_soll'], 2)} € / {z(b['db_ist'], 2)} €"]]
    inhalt += [p_._tabelle(kenn, [110 * mm, 76 * mm], zebra=False), Spacer(1, 5 * mm)]
    inhalt.append(p_._p("Laserstunden der Aufträge je Maschine", p_.S_H2))
    daten = [p_._kopfzeile(["Maschine", "Stunden"])] + [[m, z(h, 1)] for m, h in sorted(b["laser"].items())]
    if len(daten) == 1:
        daten.append(["–", ""])
    inhalt += [p_._tabelle(daten, [110 * mm, 76 * mm], zebra=False), Spacer(1, 5 * mm)]
    inhalt.append(p_._p("Top-5-Kunden nach Auftragswert", p_.S_H2))
    daten = [p_._kopfzeile(["Kunde", "Auftragswert [€]"])] + [[k, z(w, 2)] for k, w in b["kunden"]]
    if len(daten) == 1:
        daten.append(["–", ""])
    inhalt += [p_._tabelle(daten, [110 * mm, 76 * mm], zebra=False), Spacer(1, 5 * mm)]
    inhalt.append(p_._p("Absagegründe", p_.S_H2))
    daten = [p_._kopfzeile(["Grund", "Anzahl"])] + [[g, str(n)] for g, n in b["gruende"]]
    if len(daten) == 1:
        daten.append(["–", ""])
    inhalt.append(p_._tabelle(daten, [110 * mm, 76 * mm], zebra=False))
    if b.get("verlust"):
        inhalt += [Spacer(1, 5 * mm), p_._p("Auffällig oft verloren (letzte 12 Monate)", p_.S_H2)]
        inhalt += [p_._p("• " + t, p_.S) for t in b["verlust"]]
    doc.build(inhalt, canvasmaker=leinwand)
    return pfad
