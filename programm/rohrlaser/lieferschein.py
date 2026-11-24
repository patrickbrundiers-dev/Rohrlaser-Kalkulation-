"""Lieferschein mit Teillieferungen (Vorschlag F6a) und Werkszeugnisse beim Versand (F5a), 02.11.2026.

Je beauftragtem Angebot beliebig viele Lieferscheine (Zusatzdaten 'lieferscheine': [dict(nummer, datum, zeilen=
[dict(pid, pos, artikel, bezeichnung, menge)], bemerkung)]); Nummernkreis LS-JJJJ-00001 (Einstellung
'letzte_lieferscheinnummer', alle Arbeitsplätze gemeinsam über den Abgleich der Einstellungen). Vorgabe je Position:
die noch offene Menge. Positionen ohne Stückzahl, Musterteile mit Stückzahl zählen mit.

Werkszeugnisse: verlangt das Angebot „Werkszeugnis 3.1“, sammelt der Lieferschein die Zeugnisse der für den Auftrag
reservierten bzw. verbrauchten Lagerposten (lager.zeugnisse) in einen Ordner neben dem PDF und warnt, wenn eins fehlt.
Ohne Qt (bis auf das PDF über reportlab)."""
import datetime
import shutil
from pathlib import Path

EINSTELLUNG = "letzte_lieferscheinnummer"


def _n(w):
    try:
        return float(w) if w not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def scheine(db, angebot_id):
    return list(db.zusatz(angebot_id, "lieferscheine", []) or [])


def stand(positionen, liste):
    """Je Position mit Stückzahl: dict(pid, pos, artikel, bezeichnung, bestellt, geliefert, offen)."""
    from .angebot import aktiv as position_aktiv
    geliefert = {}
    for s in liste:
        for z in s.get("zeilen") or ():
            geliefert[z["pid"]] = geliefert.get(z["pid"], 0) + _n(z.get("menge"))
    out = []
    for p in positionen:
        n = _n(p.get("stueck"))
        if n <= 0 or not position_aktiv(p):
            continue
        g = geliefert.get(p["id"], 0)
        out.append(dict(pid=p["id"], pos=p.get("pos"), artikel=p.get("artikel") or "", bezeichnung=p.get("bezeichnung")
                        or "", bestellt=n, geliefert=g, offen=max(0.0, n - g)))
    return out


def offen_text(st):
    """'geliefert 300/500 Stk' für Listen; '' ohne Lieferschein, 'komplett' wenn alles geliefert."""
    if not st:
        return ""
    b, g = sum(z["bestellt"] for z in st), sum(z["geliefert"] for z in st)
    if g <= 0:
        return ""
    if g >= b - 1e-9:
        return "komplett geliefert"
    return f"geliefert {g:g}/{b:g} Stk"


def naechste_nummer(db, heute=None):
    """Nächste Nummer LS-JJJJ-00001; das Jahr beginnt neu bei 1."""
    jahr = (heute or datetime.date.today()).year
    alt = str(db.einstellung(EINSTELLUNG) or "")
    try:
        _, j, n = alt.split("-")
        nr = int(n) + 1 if int(j) == jahr else 1
    except ValueError:
        nr = 1
    return f"LS-{jahr}-{nr:05d}"


def anlegen(db, angebot_id, mengen, heute=None, bemerkung=""):
    """Lieferschein mit {Positions-ID: Menge} (0/leer = nicht dabei) anlegen. Mehr als offen geht nicht.
    Ergebnis: der Lieferschein (dict). ValueError ohne Menge."""
    heute = heute or datetime.date.today()
    pos = db.positionen(angebot_id)
    st = {z["pid"]: z for z in stand(pos, scheine(db, angebot_id))}
    zeilen = []
    for pid, menge in mengen.items():
        menge = _n(menge)
        if menge <= 0 or pid not in st:
            continue
        if menge > st[pid]["offen"] + 1e-9:
            raise ValueError(f"Pos. {st[pid]['pos']}: {menge:g} Stk. geliefert, offen sind nur {st[pid]['offen']:g}.")
        z = st[pid]
        zeilen.append(dict(pid=pid, pos=z["pos"], artikel=z["artikel"], bezeichnung=z["bezeichnung"], menge=menge))
    if not zeilen:
        raise ValueError("Keine Menge für den Lieferschein.")
    nummer = naechste_nummer(db, heute)
    schein = dict(nummer=nummer, datum=heute.isoformat(), zeilen=sorted(zeilen, key=lambda z: _n(z["pos"])),
                  bemerkung=bemerkung or "")
    db.zusatz_setzen(angebot_id, "lieferscheine", scheine(db, angebot_id) + [schein])
    db.einstellung_setzen(EINSTELLUNG, nummer)
    return schein


def zeugnisse_sammeln(db, angebot_id, ordner=None):
    """Werkszeugnisse der Lagerposten des Auftrags: dict(vorhanden=[Pfad], fehlt=[Text]); mit ordner werden die
    vorhandenen dorthin kopiert."""
    from . import lager
    vorhanden, fehlt = [], []
    for z in lager.zeugnisse(db, angebot_id):
        p = Path(z["zeugnis"]) if z.get("zeugnis") else None
        if p and p.is_file():
            vorhanden.append(p)
        else:
            fehlt.append(f"{z['kennung']} {z.get('profil') or ''} {z.get('werkstoff') or ''} Charge "
                         f"{z.get('charge') or '–'}".strip())
    if ordner and vorhanden:
        ziel = Path(ordner)
        ziel.mkdir(parents=True, exist_ok=True)
        for p in vorhanden:
            shutil.copy2(p, ziel / p.name)
    return dict(vorhanden=vorhanden, fehlt=fehlt)


def pdf(pfad, kopf, schein, einst, anschrift=None, offen=None):
    """Lieferschein als PDF (A4 hoch): Kopf, Anschrift, Positionen mit Menge, offene Restmengen."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer
    from . import pdf as p_
    from .ausgabe import datum_text
    titel = f"Lieferschein {schein['nummer']}"
    # Geschäftsbrief wie Angebot und Auftragsbestätigung (PDF-Design 12.11.2026): Anschrift im Fenster, Firma im Fuß
    doc, leinwand = p_._dokument(pfad, titel, p_._fuss(einst or {}, titel), spalten=p_.brief_spalten(einst or {}))
    daten = [("Lieferschein-Nr.", schein["nummer"]), ("Datum", datum_text(schein["datum"])),
             ("Unser Auftrag", kopf.get("nummer")), ("Kunden-Nr.", kopf.get("kundennr")),
             ("Ihre Bestellung", kopf.get("auftragsnr")), ("Ihre Anfrage", kopf.get("kundenreferenz"))]
    inhalt = p_.brief_kopf(einst or {}, anschrift or [kopf.get("kunde")], daten, titel)
    daten = [p_._kopfzeile(["Pos.", "Artikel", "Bezeichnung", "Menge"])]
    for z in schein["zeilen"]:
        daten.append([str(z["pos"] or ""), p_._p(z["artikel"], p_.S_ZELLE), p_._p(z["bezeichnung"], p_.S_ZELLE),
                      f"{z['menge']:g} Stk."])
    inhalt += [p_._tabelle(daten, [w * mm for w in (16, 50, 90, 30)], rechts=(3,)), Spacer(1, 5 * mm)]
    rest = [z for z in (offen or ()) if z["offen"] > 0]
    if rest:
        inhalt.append(p_._p("Noch offen (Teillieferung): " + ", ".join(f"Pos. {z['pos']} {z['offen']:g} Stk."
                                                                       for z in rest), p_.S))
    else:
        inhalt.append(p_._p("Mit dieser Lieferung ist der Auftrag vollständig geliefert.", p_.S))
    if schein.get("bemerkung"):
        inhalt.append(p_._p(schein["bemerkung"], p_.S))
    inhalt += [Spacer(1, 18 * mm), p_._p("Ware vollständig und unbeschädigt erhalten: ______________________ "
                                         "(Datum, Unterschrift)", p_.S)]
    doc.build(inhalt, canvasmaker=leinwand)
    return pfad
