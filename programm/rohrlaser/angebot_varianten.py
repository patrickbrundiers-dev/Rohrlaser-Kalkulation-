"""Varianten A bis E eines Angebots nebeneinander (Angebotswesen P4, Patrick 20.11.2026).

Eine Variante ändert Kalkulationswerte des Angebots (Gewinn, Aufschläge, Rabatt, Rüst- und Programmierzeit …) und/oder
rechnet mit geänderten Preisen (Material, Maschinenstundensatz, weitere Stundensätze, Zukauf; preis_simulator). Jede
Variante wird mit der vollen Kalkulation des Angebots auf einer Kopie gerechnet (gleicher Schnittplan); das Original
bleibt unverändert. Die Varianten stehen als JSON im Kopffeld 'varianten' des Angebots.

„Als Fassung übernehmen“ legt eine neue Fassung des Angebots an (Nummer -2, -3 …) und schreibt dort die
Kalkulationswerte der Variante ein. Preisänderungen (Material, Stundensätze, Zukauf) sind nur ein Was-wäre-wenn und
werden nicht übernommen (die Fassung rechnet mit den aktuellen Stammdaten). Ohne Qt.
"""
import json

from . import preis_simulator, rechnen
from .angebot import KALKULATION
from .zahlen import ist_zahl as _zahl  # Audit 26.11.2026 R-01: gemeinsame Hilfsfunktion

BUCHSTABEN = "ABCDE"
# Kalkulationswerte, die eine Variante ändern darf (Kopffelder des Angebots, Prozentwerte in %)
KALK_FELDER = ("gewinn", "gewinn_material", "zuschlag_fremdleistung", "aufschlag_zukauf", "aufschlag_blech", "rabatt",
               "eilzuschlag", "ruesten_abmessung", "programmierung_zeit", "faktor_laserzeit", "angebotsaufschlag")
_TITEL = {f.name: f.titel for f in KALKULATION}
# Preis-Szenario (preis_simulator): Schlüssel, Titel
PREIS_FELDER = (("material", "Materialpreise alle Werkstoffe [%]"), ("maschine", "Maschinenstundensatz [± €/h]"),
                ("saetze", "Weitere Stundensätze [%]"), ("zukauf", "Einkaufspreise Zukauf [%]"))
FELDER = tuple((n, _TITEL[n]) for n in KALK_FELDER) + PREIS_FELDER
ERGEBNIS = (("herstell", "Herstellkosten"), ("selbst", "Selbstkosten"), ("gewinn", "Gewinn (nach Rabatt und Konditionen)"),
            ("verkauf", "Verkaufspreis netto"), ("marge", "Gewinnmarge (vom Verkaufspreis)"),
            ("deckungsbeitrag", "Deckungsbeitrag"), ("unterschied", "Unterschied zum Original"))


def lesen(kopf):
    """Varianten des Angebots: [dict(buchstabe, name, werte {Feld: Zahl})], höchstens fünf, A bis E."""
    try:
        roh = json.loads((kopf or {}).get("varianten") or "[]")
    except (TypeError, ValueError):
        return []
    out = []
    for v in roh if isinstance(roh, list) else ():
        if not isinstance(v, dict) or v.get("buchstabe") not in BUCHSTABEN:
            continue
        werte = {n: float(w) for n, w in (v.get("werte") or {}).items() if n in dict(FELDER) and _zahl(w)}
        out.append(dict(buchstabe=v["buchstabe"], name=str(v.get("name") or ""), werte=werte))
    return sorted(out, key=lambda v: v["buchstabe"])[:5]


def als_text(varianten):
    """JSON für das Kopffeld 'varianten' (leere Varianten ohne Namen und Werte entfallen; leer = None)."""
    liste = [dict(buchstabe=v["buchstabe"], name=v.get("name") or "", werte=v.get("werte") or {})
             for v in varianten if v.get("name") or v.get("werte")]
    return json.dumps(liste, ensure_ascii=False) if liste else None


def _werte(summen):
    n = rechnen._n
    verkauf = n(summen.get("verkauf"))
    variabel = sum(n(summen.get(x)) for x in ("material", "lagerzins", "schrott", "schneidgas", "zukauf_einstand",
                                               "baugruppe_fremd", "fracht", "frachtfrei", "skonto"))
    # Gewinn nach Rabatt, Rundung, Regeln und Mindestpreis und Marge vom Warenwert: zentral in marge.py
    from . import marge as mg
    w = mg.werte(summen)
    return dict(herstell=n(summen.get("herstell")), selbst=n(summen.get("selbst")), gewinn=w["gewinn"],
                verkauf=verkauf, marge=w["marge"], aufschlag=w["aufschlag"], deckungsbeitrag=verkauf - variabel)


def rechnen_variante(kopf, positionen, ergebnis, k, tabellen, einst, werte):
    """Summen einer Variante. kopf/positionen/ergebnis/k/tabellen/einst = Werte des Angebots wie im Angebotsfenster
    (einst mit den Kalkulationswerten des Angebots). werte = Felder der Variante."""
    werte = werte or {}
    kalk = {n: werte[n] for n in KALK_FELDER if _zahl(werte.get(n))}
    sz = dict(material={kat: werte["material"] for kat in {w.get("kategorie") for w in k.werkstoffe.values()}
                        if kat} if _zahl(werte.get("material")) else {},
              maschine=werte.get("maschine"), saetze=werte.get("saetze"), zukauf=werte.get("zukauf"))
    kopf2 = dict(kopf, **kalk)
    e2 = rechnen.einstellungen_angebot(kalk, einst)
    kopf2, pos2, k2, tab2 = preis_simulator.anwenden(kopf2, positionen, k, tabellen, sz)
    return rechnen.kalkulation(kopf2, pos2, ergebnis, k2, tab2, e2)[1]


def vergleich(kopf, positionen, ergebnis, k, tabellen, einst, summen_original, varianten):
    """Spalten Original + Varianten: [dict(buchstabe, name, werte, ergebnis {herstell … unterschied}, fehler)]."""
    orig = _werte(summen_original)
    out = [dict(buchstabe="", name="Original", werte={}, ergebnis=dict(orig, unterschied=0.0), fehler="")]
    for v in varianten:
        try:
            erg = _werte(rechnen_variante(kopf, positionen, ergebnis, k, tabellen, einst, v["werte"]))
            erg["unterschied"] = erg["verkauf"] - orig["verkauf"]
            out.append(dict(v, ergebnis=erg, fehler=""))
        except Exception as e:      # noqa: BLE001 – eine Variante nie am Vergleich scheitern lassen
            out.append(dict(v, ergebnis={}, fehler=f"{type(e).__name__}: {e}"))
    return out


def uebernehmen(db, angebot_id, variante):
    """Neue Fassung des Angebots mit den Kalkulationswerten der Variante. Ergebnis: (neue ID, [nicht übernommene
    Preisänderungen als Titel])."""
    neu = db.angebot_fassung(angebot_id)
    for n in KALK_FELDER:
        w = (variante.get("werte") or {}).get(n)
        if _zahl(w):
            db.angebot_aendern(neu, n, w)
    db.angebot_aendern(neu, "varianten", None)
    offen = [t for n, t in PREIS_FELDER if _zahl((variante.get("werte") or {}).get(n)) and variante["werte"][n]]
    return neu, offen
