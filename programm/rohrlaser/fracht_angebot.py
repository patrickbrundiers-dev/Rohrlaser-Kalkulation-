"""Fracht im Angebot und in den Staffelpreisen (ohne Oberfläche).

Angebotskopf:
- fracht_modus: manuell (leer, wie bisher: Betrag 'fracht' von Hand), berechnet (Betrag aus der Frachtberechnung,
  Eingaben und Tarif-Snapshot in fracht_sendung), keine Fracht (Abholung, ab Werk) oder im Artikelpreis enthalten
  (beide 0 € in der Kalkulation, Hinweis im Angebot; so wird Fracht nie doppelt berechnet).
- fracht_umlage: je Stück (leer, wie bisher) oder nach Gewicht (Anteil des Teilegewichts am Gesamtgewicht; fehlt
  einer Position das Gewicht, wird im ganzen Angebot je Stück verteilt, mit Hinweis). Neue Angebote: nach Gewicht.
- fracht_sendung: JSON {sendung, snapshot, gesamt, text, lht_standard, lht_langgut} aus der Frachtberechnung.

Staffelpreise: Im Modus 'berechnet' rechnet jede Mengenstufe Nettogewicht, Ladungsträger (Packvorschlag) und
Fracht mit dem gespeicherten Tarif-Snapshot neu; in den übrigen Modi gilt der Betrag des Angebots für alle Mengen.
"""
import json

MANUELL, BERECHNET, KEINE, ENTHALTEN = "manuell", "berechnet", "keine Fracht", "im Artikelpreis enthalten"
MODI = (MANUELL, BERECHNET, KEINE, ENTHALTEN)
JE_STUECK, NACH_GEWICHT = "je Stück", "nach Gewicht"
UMLAGEN = (JE_STUECK, NACH_GEWICHT)
UMLAGE_NEU = NACH_GEWICHT          # Vorgabe für neue Angebote (Entscheidung 3B); ältere Angebote: leer = je Stück


def modus(kopf):
    return kopf.get("fracht_modus") or MANUELL


def umlage(kopf):
    return kopf.get("fracht_umlage") or JE_STUECK


def daten(kopf):
    """Gespeicherte Frachtberechnung des Angebots (dict) oder None."""
    d = kopf.get("fracht_sendung")
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except ValueError:
            return None
    return d if isinstance(d, dict) else None


def wirksam(kopf):
    """Frachtbetrag, der in die Kalkulation eingeht (€): manuell und berechnet = Feld 'fracht', sonst 0."""
    if modus(kopf) in (KEINE, ENTHALTEN):
        return 0.0
    w = kopf.get("fracht")
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0


def ware(positionen, werte):
    """Nettogewicht und längstes Teil der Ware. werte[i] = rechnen.position_werte (None = Position ohne Profil).
    Ergebnis: (netto kg, max. Länge mm, [Pos. ohne Gewicht])."""
    netto, laenge, fehlt = 0.0, 0.0, []
    for p, w in zip(positionen, werte):
        if w is None or not p.get("stueck"):
            continue
        if w.get("gewicht") is None:
            fehlt.append(str(p.get("pos") or "?"))
            continue
        netto += w["gewicht"] * p["stueck"]
        laenge = max(laenge, float(p.get("laenge") or 0))
    return netto, laenge, fehlt


def anteile(positionen, werte, betrag, art):
    """Fracht je Teil für jede Position (Liste, None = nicht aktiv) und Hinweis.
    je Stück: betrag / Teile; nach Gewicht: betrag × Teilegewicht / Gesamtgewicht der Teile."""
    aktiv = [i for i, w in enumerate(werte) if w is not None]
    teile = sum(positionen[i].get("stueck") or 0 for i in aktiv)
    out = [None] * len(positionen)
    hinweis = ""
    if art == NACH_GEWICHT:
        fehlt = [str(positionen[i].get("pos") or "?") for i in aktiv
                 if (positionen[i].get("stueck") or 0) > 0 and not werte[i].get("gewicht")]
        if fehlt:
            hinweis = (f"Gewicht fehlt bei Pos. {', '.join(fehlt)}: Fracht in diesem Angebot je Stück verteilt"
                       if betrag else "")
        else:
            gesamt = sum((werte[i].get("gewicht") or 0) * (positionen[i].get("stueck") or 0) for i in aktiv)
            for i in aktiv:
                out[i] = betrag * (werte[i].get("gewicht") or 0) / gesamt if gesamt else 0.0
            return out, hinweis, NACH_GEWICHT
    for i in aktiv:
        out[i] = betrag / teile if teile else 0.0
    return out, hinweis, JE_STUECK


def sendung_der_menge(d, netto, max_laenge):
    """Sendung einer Mengenstufe aus der gespeicherten Frachtberechnung d: neues Nettogewicht und längstes Teil,
    Ladungsträger per Packvorschlag (mit den Ladungsträgern des Snapshots); Verpackung und frachtpflichtiges
    Gewicht nach Tarif (von Hand eingetragene Werte gelten nur für die Menge des Angebots)."""
    from . import fracht        # erst hier: fracht -> ausgabe -> rechnen -> fracht_angebot
    s = dict(d.get("sendung") or {})
    s.update(netto=netto, max_laenge=max_laenge or None, verpackung=None, frachtpflichtig=None)
    lht, hinweise = fracht.packvorschlag([(netto, max_laenge)], d["snapshot"].get("lht", []),
                                         d.get("lht_standard"), d.get("lht_langgut"))
    if lht:
        s["lht"] = lht
    else:
        hinweise = hinweise + ["Ladungsträger wie in der Frachtberechnung des Angebots"]
    return s, hinweise


def stufe(kopf, positionen, werte):
    """Fracht einer Mengenstufe (positionen mit den Stückzahlen der Stufe).
    Ergebnis: (Betrag oder None, Text für die Stufe, Fehlertext oder '')."""
    from . import fracht
    if modus(kopf) != BERECHNET:
        return wirksam(kopf), "", ""
    d = daten(kopf)
    if not d or not d.get("snapshot"):
        return None, "", "Fracht nicht berechnet: im Angebot 'Fracht berechnen …' ausführen"
    netto, laenge, fehlt = ware(positionen, werte)
    if fehlt:
        return None, "", f"Fracht nicht berechnet: Gewicht fehlt bei Pos. {', '.join(fehlt)}"
    s, hinweise = sendung_der_menge(d, netto, laenge)
    e = fracht.nachrechnen(d["snapshot"], s)
    if e.get("gesamt") is None:
        return None, "", "Fracht nicht berechnet: " + "; ".join(e.get("fehler") or ["–"])
    lw = e.get("lht") or {}
    g = e.get("gewicht") or {}
    lht = ", ".join(f"{x['anzahl']} × {x['lht_id']}" for x in lw.get("je", []))
    text = f"Fracht {fracht.euro(e['gesamt'])}: {fracht.z2(g.get('brutto') or 0, 1)} kg brutto" + \
        (f", {lht}" if lht else "")
    return e["gesamt"], text, ""


def angebotstext(kopf):
    """Hinweis zur Fracht im Angebots-PDF (leer im Modus manuell: wie bisher)."""
    m = modus(kopf)
    if m == KEINE:
        return "Lieferung ab Werk; Frachtkosten sind nicht enthalten."
    if m == ENTHALTEN:
        return "Die Frachtkosten sind in den Preisen enthalten."
    if m == BERECHNET and wirksam(kopf):
        s = (daten(kopf) or {}).get("sendung") or {}
        ziel = " ".join(x for x in ((s.get("land") or "DE"), s.get("plz") or "") if x)
        return f"Die Preise enthalten die Fracht frei Haus{(' nach ' + ziel) if s.get('plz') else ''}."
    return ""
