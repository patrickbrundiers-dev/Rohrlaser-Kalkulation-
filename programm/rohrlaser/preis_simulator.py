"""Preis-Simulator (Plan 29.10.2026, neue Idee 3, Patrick): „Was wäre, wenn Edelstahl 8 % teurer wird oder der
Maschinenstundensatz um 10 € steigt?“ für die offenen Angebote.

Gerechnet wird jedes Angebot wie im Angebotsfenster (festgeschriebene Preise und Zeiten des Angebots, gespeicherter
Schnittplan, Einstellungen des Angebots) einmal unverändert und einmal mit dem Szenario. Nichts wird gespeichert:
das Szenario wirkt nur auf Kopien von Kontext, Tabellen, Kopf und Positionen. Der Schnittplan bleibt, wie er ist
(eine Preisänderung ändert die Einteilung der Stangen nicht).

Szenario (dict, alle Werte leer/0 = unverändert):
  material  {Kategorie: Prozent}  Materialpreise der Werkstoffe dieser Kategorie (Preise, Lieferlängen, Tonnenpreis,
                                  Materialpreis von Hand in der Position, fester €/kg-Teuerungszuschlag); die
                                  Oberflächen-Aufpreise bleiben
  maschine  €/h                   auf den Stundensatz der Maschine des Angebots
  saetze    Prozent               auf alle weiteren Stundensätze (Programmierung, Schweißen, Personal …)
  zukauf    Prozent               auf die Einkaufspreise der Zukaufteile (Preisstand in der Position)

Ergebnis je Angebot: Verkaufspreis und Selbstkosten vorher und mit dem Szenario, dazu die Marge bei unverändertem
Verkaufspreis (für verschickte Angebote, deren Preis beim Kunden schon steht).
"""
import copy
import dataclasses

from . import rechnen, zukauf
from .datenbank import VORGAENGE

OFFEN = VORGAENGE[:2]          # Entwurf, Verschickt
MIT_BEAUFTRAGT = VORGAENGE[:3]


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def leer(sz):
    """True, wenn das Szenario nichts ändert."""
    sz = sz or {}
    return not any(_n(v) for v in (sz.get("material") or {}).values()) and not any(
        _n(sz.get(n)) for n in ("maschine", "saetze", "zukauf"))


def _faktor(p):
    return 1 + _n(p) / 100


def anwenden(kopf, positionen, k, tabellen, sz):
    """Kopien (kopf, positionen, k, tabellen) mit dem Szenario sz. k, tabellen = gültige Werte des Angebots (nach
    rechnen.preisbasis_anwenden)."""
    sz = sz or {}
    kat_f = {kat: _faktor(p) for kat, p in (sz.get("material") or {}).items() if _n(p)}
    ws_f = {w: kat_f[z.get("kategorie")] for w, z in k.werkstoffe.items() if z.get("kategorie") in kat_f}
    tab = dict(tabellen)
    if ws_f:
        tab["preise"] = [dict(z, preis=_n(z.get("preis")) * ws_f[z["werkstoff_id"]])
                         if z.get("werkstoff_id") in ws_f and z.get("preis") is not None else z
                         for z in tabellen.get("preise") or ()]
        tab["lieferlaengen"] = [dict(z, preis=_n(z.get("preis")) * ws_f[z["werkstoff_id"]])
                                if z.get("werkstoff_id") in ws_f and z.get("preis") is not None else z
                                for z in tabellen.get("lieferlaengen") or ()]
        ws = {}
        for w, z in k.werkstoffe.items():
            if w in ws_f:
                z = dict(z)
                if z.get("tonnenpreis") is not None:
                    z["tonnenpreis"] = _n(z["tonnenpreis"]) * ws_f[w]
                if z.get("teuerung_art") == "€/kg" and z.get("teuerung_wert") is not None:
                    z["teuerung_wert"] = _n(z["teuerung_wert"]) * ws_f[w]
            ws[w] = z
        k = dataclasses.replace(k, werkstoffe=ws)
    pos = [dict(p) for p in positionen]
    if ws_f:
        for p in pos:
            if _n(p.get("preis_m")) > 0 and p.get("werkstoff_id") in ws_f:
                p["preis_m"] = p["preis_m"] * ws_f[p["werkstoff_id"]]
    if _n(sz.get("zukauf")):
        f = _faktor(sz["zukauf"])
        for p in pos:
            if p.get("zukauf"):
                p["zukauf"] = [_zukauf_teurer(z, f) for z in zukauf.json_liste(p["zukauf"])]
    kopf = dict(kopf)
    if _n(sz.get("maschine")) or _n(sz.get("saetze")):
        zb = rechnen.zeitbasis(kopf, k, tab)
        zb = dict(maschine=dict(zb.get("maschine") or {}), saetze=dict(zb.get("saetze") or {}),
                  schritte=copy.deepcopy(zb.get("schritte") or []))
        if _n(sz.get("maschine")) and zb["maschine"].get("stundensatz") is not None:
            zb["maschine"]["stundensatz"] = _n(zb["maschine"]["stundensatz"]) + sz["maschine"]
        if _n(sz.get("saetze")):
            f = _faktor(sz["saetze"])
            zb["saetze"] = {s: (_n(v) * f if v is not None else v) for s, v in zb["saetze"].items()}
            tab["stundensaetze"] = [dict(z, satz=_n(z.get("satz")) * f) if z.get("satz") is not None else z
                                    for z in tabellen.get("stundensaetze") or ()]
        kopf["zeitbasis"] = zb
        m = kopf.get("maschine")
        if _n(sz.get("maschine")) and m in k.maschinen and k.maschinen[m].get("stundensatz") is not None:
            k = dataclasses.replace(k, maschinen=dict(k.maschinen, **{m: dict(
                k.maschinen[m], stundensatz=_n(k.maschinen[m]["stundensatz"]) + sz["maschine"])}))
    return kopf, pos, k, tab


def _zukauf_teurer(z, f):
    """Zukauf-Eintrag einer Position mit um den Faktor f geänderten Staffelpreisen im Preisstand (Bezugskosten wie
    Versand bleiben)."""
    st = z.get("stand") if isinstance(z, dict) else None
    bezug = st.get("bezug") if isinstance(st, dict) else None
    if not isinstance(bezug, dict):
        return z
    preise = [dict(e, preis=e["preis"] * f) if isinstance(e.get("preis"), (int, float)) else e
              for e in zukauf.json_liste(bezug.get("preise"))]
    return dict(z, stand=dict(st, bezug=dict(bezug, preise=preise)))


def _werte(summen):
    return dict(verkauf=_n(summen.get("verkauf")), selbst=_n(summen.get("selbst")),
                material=_n(summen.get("material")), laser=_n(summen.get("laser")))


def angebot(db, angebot_id, sz, aktuell=None, einst=None):
    """Ein Angebot vorher/mit Szenario: dict(id, nummer, kunde, vorgang, datum, vorher, nachher) mit je dict(verkauf,
    selbst, material, laser), oder dict(..., fehlt=Text) ohne Schnittplan. aktuell = (k, tabellen) der Stammdaten,
    einst = Einstellungen (beides für viele Angebote einmal holen)."""
    a = db.angebot(angebot_id)
    kopf_info = dict(id=angebot_id, nummer=a.get("nummer"), kunde=a.get("kunde"), datum=a.get("datum"),
                     vorgang=a.get("vorgang") or VORGAENGE[0])
    if not a.get("ergebnis"):
        return dict(kopf_info, fehlt="nicht optimiert")
    pos = db.positionen(angebot_id)
    if not pos:
        return dict(kopf_info, fehlt="keine Positionen")
    k_akt, tab_akt = aktuell or (db.kontext(), db.tabellen())
    k, tab = rechnen.preisbasis_anwenden(a, k_akt, tab_akt)
    e = rechnen.einstellungen_angebot(a, rechnen.einstellungen_fest(tab, einst if einst is not None
                                                                     else db.einstellungen()))
    vorher = rechnen.kalkulation(a, pos, a["ergebnis"], k, tab, e)[1]
    kopf2, pos2, k2, tab2 = anwenden(a, pos, k, tab, sz)
    nachher = rechnen.kalkulation(kopf2, pos2, a["ergebnis"], k2, tab2, e)[1]
    return dict(kopf_info, vorher=_werte(vorher), nachher=_werte(nachher))


def auswahl(db, vorgaenge=OFFEN):
    """Eigene Angebote der Vorgänge (ohne ersetzte alte Fassungen und Angebote der Kollegen), neueste zuerst."""
    return [z for z in db.angebote() if (z.get("vorgang") or VORGAENGE[0]) in vorgaenge
            and not z.get("ersetzt_durch") and not z.get("fremd")]


def simulieren(db, sz, vorgaenge=OFFEN, fortschritt=None):
    """Alle Angebote der Auswahl: (Zeilen wie angebot() plus diff, marge_vorher, marge_gleich, marge_neu; Summen).
    marge_vorher = (Verkauf − Selbstkosten) / Verkauf, marge_gleich = Marge mit dem Szenario bei unverändertem
    Verkaufspreis, marge_neu = Marge mit neuem Verkaufspreis. fortschritt(i, n) wird je Angebot gerufen."""
    liste = auswahl(db, vorgaenge)
    aktuell, einst = (db.kontext(), db.tabellen()), db.einstellungen()
    zeilen = []
    for i, z in enumerate(liste):
        if fortschritt:
            fortschritt(i, len(liste))
        try:
            r = angebot(db, z["id"], sz, aktuell, einst)
        except Exception as fehler:        # ein beschädigtes Angebot hält die Übersicht nicht an
            r = dict(id=z["id"], nummer=z.get("nummer"), kunde=z.get("kunde"), datum=z.get("datum"),
                     vorgang=z.get("vorgang") or VORGAENGE[0], fehlt=f"Fehler: {fehler}")
        if "vorher" in r:
            v, n = r["vorher"], r["nachher"]
            r["diff"] = n["verkauf"] - v["verkauf"]
            r["marge_vorher"] = (v["verkauf"] - v["selbst"]) / v["verkauf"] if v["verkauf"] else None
            r["marge_gleich"] = (v["verkauf"] - n["selbst"]) / v["verkauf"] if v["verkauf"] else None
            r["marge_neu"] = (n["verkauf"] - n["selbst"]) / n["verkauf"] if n["verkauf"] else None
        zeilen.append(r)
    gerechnet = [r for r in zeilen if "vorher" in r]
    s = {n: sum(r[t][n] for r in gerechnet) for t in ("vorher",) for n in ("verkauf", "selbst")}
    s_neu = {n: sum(r["nachher"][n] for r in gerechnet) for n in ("verkauf", "selbst")}
    summen = dict(angebote=len(gerechnet), ohne=len(zeilen) - len(gerechnet),
                  verkauf_vorher=s["verkauf"], verkauf_nachher=s_neu["verkauf"],
                  selbst_vorher=s["selbst"], selbst_nachher=s_neu["selbst"],
                  diff=s_neu["verkauf"] - s["verkauf"],
                  marge_vorher=(s["verkauf"] - s["selbst"]) / s["verkauf"] if s["verkauf"] else None,
                  marge_gleich=(s["verkauf"] - s_neu["selbst"]) / s["verkauf"] if s["verkauf"] else None,
                  marge_neu=(s_neu["verkauf"] - s_neu["selbst"]) / s_neu["verkauf"] if s_neu["verkauf"] else None)
    return zeilen, summen


def szenario_text(sz):
    """Kurzer Text des Szenarios, z. B. 'Edelstahl +8 %, Maschine +10 €/h'."""
    from .stammdaten import zahl_als_text as zahl
    sz = sz or {}
    teile = [f"{kat} {'+' if _n(p) > 0 else ''}{zahl(_n(p))} %" for kat, p in (sz.get("material") or {}).items()
             if _n(p)]
    if _n(sz.get("maschine")):
        teile.append(f"Maschine {'+' if sz['maschine'] > 0 else ''}{zahl(sz['maschine'])} €/h")
    if _n(sz.get("saetze")):
        teile.append(f"weitere Stundensätze {'+' if sz['saetze'] > 0 else ''}{zahl(sz['saetze'])} %")
    if _n(sz.get("zukauf")):
        teile.append(f"Zukaufteile {'+' if sz['zukauf'] > 0 else ''}{zahl(sz['zukauf'])} %")
    return ", ".join(teile) or "keine Änderung"
