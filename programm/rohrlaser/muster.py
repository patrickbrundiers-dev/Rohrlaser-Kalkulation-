"""Muster in Handeinträgen finden (Plan „Mehr Intelligenz“ I3 + I4, Patrick 08.11.2026, Freigabe „Alle Empfehlungen“).

Trägt man eine Zusatzarbeit immer wieder von Hand nach, steckt oft eine Regel dahinter. vorschlaege() sucht in den
Positionen der letzten Angebote (eigene und der Kollegen, ohne ersetzte Fassungen, höchstens MAX_POS):
- I3 Erkennungswort: ein Wort aus der Bezeichnung (z. B. „gestrahlt“), bei dem die Zusatzarbeit fast immer dabei ist
  -> Vorschlag, das Wort bei der Zusatzarbeit als Erkennungswort einzutragen (zusatz_erkennung schlägt sie dann vor).
- I4 Arbeitsgang-Regel: eine Bedingung (Kunde, Werkstoff-Kategorie, Werkstoff, Profilform, Merkmal Gewinde/
  Bohrungen/Innenkonturen/Schräges Ende), bei der die Zusatzarbeit fast immer dabei ist -> Vorschlag einer Regel mit
  Zuordnung „Vorschlag“ (kostet nichts, bis man sie im Angebot annimmt).
Ein Muster zählt erst ab MIN_ANGEBOTE verschiedenen Angeboten mit der Zusatzarbeit von Hand und wenn sie bei
mindestens MIN_ANTEIL der Positionen mit dieser Bedingung dabei ist. Schon vorhandene Wörter und Regeln, abgelehnte
Vorschläge (Einstellung ABGELEHNT, über den gemeinsamen Ordner geteilt) und Baugruppen zählen nicht. Übernommen
wird nur auf Klick (Lernzentrale); nichts ändert sich von selbst. Ohne Qt."""
import json
import re

from . import zusatz_erkennung as ze
from . import zusatz_regeln as zr

MIN_ANGEBOTE = 3
MIN_ANTEIL = 0.8
MAX_POS = 5000
JE_ZUSATZ = 2                    # höchstens so viele Wort- bzw. Regel-Vorschläge je Zusatzarbeit
ABGELEHNT = "muster_abgelehnt"    # Einstellung {Schlüssel: Datum}
MERKMALE = ("Gewinde", "Bohrungen", "Innenkonturen", "Schräges Ende")
BEDINGUNGEN = ("kundennr", "kategorie", "werkstoff_id", "profilform")
TITEL = {"kundennr": "Kunde", "kategorie": "Werkstoff-Kategorie", "werkstoff_id": "Werkstoff",
         "profilform": "Profilform", "merkmal": "Merkmal", "stichwort": "Wort"}
WORT = re.compile(r"[A-Za-zÄÖÜäöüß]{4,}")
STOPP = {"rohr", "rohre", "profil", "teil", "teile", "blech", "laser", "laserteil", "lang", "kurz", "links", "rechts",
         "oben", "unten", "mit", "ohne", "und", "oder", "fuer", "für", "nach", "zeichnung", "pos", "position",
         "stahl", "edelstahl", "alu", "aluminium", "quadratrohr", "rundrohr", "rechteckrohr", "halter", "strebe"}


def _hand(p):
    """Namen der Zusatzarbeiten, die an der Position von Hand stehen (nicht aus Regel oder Erkennung)."""
    return {e["name"] for e in _liste(p) if not str(e.get("quelle") or "").startswith((zr.QUELLE, ze.ERKANNT))
            and not e.get("auto")}


def _liste(p):
    try:
        w = json.loads(p.get("zusatz") or "[]")
    except (TypeError, ValueError):
        return []
    return [e for e in w if isinstance(e, dict) and e.get("name")] if isinstance(w, list) else []


def worte(p):
    return {w.casefold() for w in WORT.findall(str(p.get("bezeichnung") or ""))} - STOPP


def daten(db):
    """Positionen der letzten Angebote mit Kundennummer und Angebots-ID (ohne Baugruppen)."""
    from .angebot import ist_baugruppe
    sql = ("SELECT p.*, a.kundennr AS _kundennr FROM positionen p JOIN angebote a ON a.id = p.angebot_id "
           "WHERE COALESCE(a.ersetzt_durch, '') = '' ORDER BY p.id DESC LIMIT ?")
    return [z for z in (dict(r) for r in db.con.execute(sql, (MAX_POS,))) if not ist_baugruppe(z)]


def _schluessel(art, zusatz, feld, wert):
    return f"{art}|{zusatz}|{feld}|{wert}"


def vorschlaege(db, k=None, tabellen=None, zeilen=None):
    """[dict(art 'wort'|'regel', schluessel, zusatz, feld, wert, text, angebote, anteil, positionen)], die stärksten
    zuerst."""
    from . import funktionen
    if not funktionen.an(funktionen.REGELVORSCHLAEGE, db):
        return []
    k = k if k is not None else db.kontext()
    tabellen = tabellen if tabellen is not None else db.tabellen()
    zeilen = zeilen if zeilen is not None else daten(db)
    katalog = {z.get("name"): z for z in tabellen.get("zusatzarbeiten") or () if z.get("name")
               and z.get("aktiv") != "nein"}
    bekannte_worte = {w.casefold() for z in katalog.values() for w in ze.woerter(z)}
    regeln = tabellen.get("arbeitsgang_regeln") or ()
    gewinde = tabellen.get("gewinde") or ()
    abgelehnt = _abgelehnt(db)
    hand, alle = {}, {}
    wort_je = [worte(p) for p in zeilen]
    # Bedingungen je Position einmal bestimmen (wie zusatz_regeln.trifft, ohne jede Regel einzeln zu prüfen)
    merkmale_je, index = [], {}
    for i, p in enumerate(zeilen):
        pr = (k.profile.get(p.get("profil_id")) if k else None) or {}
        fw = {(feld, str(wert)) for feld, wert in (
            ("kundennr", p.get("_kundennr")),
            ("kategorie", (k.werkstoffe.get(p.get("werkstoff_id")) or {}).get("kategorie") if k else None),
            ("werkstoff_id", p.get("werkstoff_id")), ("profilform", pr.get("form"))) if wert not in (None, "")}
        fw |= {("merkmal", m) for m in MERKMALE if zr.merkmal_trifft(m, p, gewinde)}
        merkmale_je.append(fw)
        for x in fw:
            index.setdefault(x, set()).add(i)
    for i, p in enumerate(zeilen):
        for n in _hand(p):
            hand.setdefault(n, set()).add(i)
        for e in _liste(p):
            alle.setdefault(e["name"], set()).add(i)
    out = []
    for name, mit_hand in hand.items():
        if name not in katalog or len({zeilen[i]["angebot_id"] for i in mit_hand}) < MIN_ANGEBOTE:
            continue
        mit = alle.get(name, set())
        kandidaten = []

        def pruefen(art, feld, wert, treffer, text):
            schl = _schluessel(art, name, feld, wert)
            if schl in abgelehnt or not treffer:
                return
            dabei = treffer & mit
            angebote = len({zeilen[i]["angebot_id"] for i in dabei & mit_hand})
            anteil = len(dabei) / len(treffer)
            if angebote >= MIN_ANGEBOTE and anteil >= MIN_ANTEIL:
                kandidaten.append(dict(art=art, schluessel=schl, zusatz=name, feld=feld, wert=wert, text=text,
                                       angebote=angebote, anteil=anteil, positionen=len(dabei)))
        # I3 Wörter der Bezeichnung
        eigene = {str(r.get("stichwort") or "").casefold() for r in regeln if r.get("zusatzarbeit") == name}
        for w in set().union(*(wort_je[i] for i in mit_hand)) - bekannte_worte:
            if any(w in s for s in eigene):
                continue
            treffer = {i for i, ws in enumerate(wort_je) if w in ws}
            pruefen("wort", "stichwort", w, treffer, f"Wort „{w}“ in der Bezeichnung")
        # I4 Bedingungen einer Arbeitsgang-Regel
        vorhanden = [r for r in regeln if r.get("zusatzarbeit") == name and zr.aktiv(r)]
        for feld, wert in sorted({fw for i in mit_hand for fw in merkmale_je[i]}):
            regel = dict(zusatzarbeit=name, aktiv="ja", **{feld: wert})
            if any(all(str(r.get(f) or "") == str(regel.get(f) or "") for f in BEDINGUNGEN + ("merkmal",))
                   and not r.get("stichwort") for r in vorhanden):
                continue
            pruefen("regel", feld, wert, index[(feld, wert)], f"{TITEL[feld]} {wert}")
        kandidaten.sort(key=lambda v: (-v["anteil"], -v["angebote"]))
        for art in ("wort", "regel"):
            out += [x for x in kandidaten if x["art"] == art][:JE_ZUSATZ]
    out.sort(key=lambda v: (-v["angebote"], -v["anteil"], v["zusatz"]))
    return out


def text(v):
    """Eine Zeile für Lernzentrale und Startseite."""
    was = ("als Erkennungswort eintragen" if v["art"] == "wort" else "als Arbeitsgang-Regel (Vorschlag) anlegen")
    return (f"„{v['zusatz']}“ bei {v['text']}: in {v['angebote']} Angeboten von Hand eingetragen, bei "
            f"{100 * v['anteil']:.0f} % dieser Teile – {was}?")


def _abgelehnt(db):
    try:
        w = db.einstellung(ABGELEHNT)
    except Exception:
        return {}
    return w if isinstance(w, dict) else {}


def ablehnen(db, v):
    import datetime
    d = dict(_abgelehnt(db))
    d[v["schluessel"]] = datetime.date.today().isoformat()
    db.einstellung_setzen(ABGELEHNT, d)
    return f"Nicht übernommen: {text(v)}"


def uebernehmen(db, v):
    """Wort bei der Zusatzarbeit eintragen bzw. Regel anlegen. Ergebnis: (Text, Rückgängig-Funktion)."""
    if v["art"] == "wort":
        z = next(z for z in db.zeilen("zusatzarbeiten") if z.get("name") == v["zusatz"])
        alt = z.get("erkennung")
        db.aendern("zusatzarbeiten", z["id"], "erkennung", "; ".join([*ze.woerter(z), v["wert"]]))
        return (f"Erkennungswort „{v['wert']}“ bei „{v['zusatz']}“ eingetragen – der Import schlägt sie jetzt vor.",
                lambda: db.aendern("zusatzarbeiten", z["id"], "erkennung", alt))
    namen = {r.get("name") for r in db.zeilen("arbeitsgang_regeln")}
    name, i = f"Gelernt: {v['zusatz']} bei {v['text']}"[:80], 2
    basis = name
    while name in namen:
        name, i = f"{basis} ({i})", i + 1
    rid = db.neu("arbeitsgang_regeln", dict(
        name=name, zusatzarbeit=v["zusatz"], zuordnung=zr.VORSCHLAG, aktiv="ja", menge_art="automatisch",
        bemerkung=f"aus Handeinträgen gelernt ({v['angebote']} Angebote, {100 * v['anteil']:.0f} %)",
        **{v["feld"]: v["wert"]}))
    return (f"Arbeitsgang-Regel „{name}“ angelegt (Zuordnung Vorschlag, kostet nichts bis zum Annehmen).",
            lambda: db.loeschen("arbeitsgang_regeln", [rid]))
