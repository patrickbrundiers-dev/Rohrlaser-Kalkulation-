"""Fracht im Angebot und in den Staffelpreisen (ohne Oberfläche).

Angebotskopf:
- fracht_modus: manuell (leer, wie bisher: Betrag 'fracht' von Hand), berechnet (Betrag aus der Frachtberechnung,
  Eingaben und Tarif-Snapshot in fracht_sendung), keine Fracht (Abholung, ab Werk) oder im Artikelpreis enthalten
  (beide 0 € in der Kalkulation, Hinweis im Angebot; so wird Fracht nie doppelt berechnet).
- fracht_umlage: je Stück (leer, wie bisher) oder nach Gewicht (Anteil des Teilegewichts am Gesamtgewicht; fehlt
  einer Position das Gewicht, wird im ganzen Angebot je Stück verteilt, mit Hinweis). Neue Angebote: nach Gewicht.
- fracht_sendung: JSON {sendung, snapshot, gesamt, text, lht_standard, lht_langgut} aus der Frachtberechnung.
- fracht_auto = ja ('Fracht automatisch berechnen', Vorgabe aus): Ziel-PLZ (zwei Stellen reichen) und Land
  (fracht_plz, fracht_land), Gewicht aus den Positionen, Ladungsträger per Packvorschlag, Tarif automatisch,
  Versandart aus den Einstellungen, nur Zuschläge mit Bedingung 'immer'. Zone und Tarif werden beim Setzen des
  Hakens bzw. beim Ändern der PLZ festgehalten (Tarifkopie); jede Änderung der Positionen rechnet damit neu.

Staffelpreise: Im Modus 'berechnet' rechnet jede Mengenstufe Nettogewicht, Ladungsträger (Packvorschlag) und
Fracht mit dem gespeicherten Tarif-Snapshot neu; in den übrigen Modi gilt der Betrag des Angebots für alle Mengen.
"""
import json

from . import paletten
from .angebot import ist_baugruppe

PALETTEN_EINST = ("palette_hoehe_gesamt", "palette_max_brutto", "palette_mischen", "palette_fuellgrad",
                  "palette_zwischenlage")

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


def auto(kopf):
    return kopf.get("fracht_auto") == "ja"


def betrag_angebot(kopf, positionen, werte):
    """Fracht des Angebots für die Kalkulation: (Betrag, Text, Fehler). Automatisch: aus den aktuellen Positionen
    mit der Tarifkopie (wie eine Staffelstufe); sonst der Betrag aus dem Kopf (wirksam)."""
    if auto(kopf) and modus(kopf) == BERECHNET:
        return stufe(kopf, positionen, werte)
    return wirksam(kopf), "", ""


def ziel_aus_kunde(kunde):
    """(PLZ, Land) aus der Lieferanschrift bzw. Anschrift des Kunden, sonst ('', 'DE'). Die volle PLZ trifft die Zone
    genau; von Hand reichen zwei Ziffern (dann gilt bei mehreren Zonen im Bereich die teurere)."""
    from . import fracht
    if not kunde:
        return "", "DE"
    if kunde.get("liefer_plz"):
        plz, land = kunde["liefer_plz"], kunde.get("liefer_land")
    else:
        plz, land = kunde.get("plz") or fracht.plz_aus_text(kunde.get("plz_ort")), kunde.get("land")
    plz = "".join(c for c in str(plz or "") if c.isdigit())
    return plz, (land or "DE").upper()


def auto_rechnen(fdaten, kopf, positionen, werte, kunde, einst):
    """Frachtberechnung für 'Fracht automatisch berechnen' mit den aktuellen Frachtdaten (fdaten) und Einstellungen
    (einst: absender_plz, absender_land, fracht_versandart, fracht_lht_standard, fracht_lht_langgut).
    Ergebnis: dict für fracht_sendung (mit snapshot, gesamt, text oder fehler)."""
    from . import fracht
    netto, laenge, fehlt = ware(positionen, werte)
    s = dict(datum=kopf.get("datum") or fracht.heute(), land=(kopf.get("fracht_land") or "DE").upper(),
             plz=(kopf.get("fracht_plz") or "").strip(), absender_plz=einst.get("absender_plz"),
             absender_land=einst.get("absender_land") or "DE", versandart=einst.get("fracht_versandart") or None,
             kundennr=kopf.get("kundennr"), lieferbedingung=(kunde or {}).get("lieferbedingung"),
             netto=netto, max_laenge=laenge or None, leistungen={}, auto=True)
    d = dict(sendung=s, snapshot=None, gesamt=None, text="", lht_standard=einst.get("fracht_lht_standard"),
             lht_langgut=einst.get("fracht_lht_langgut"))
    if not s["plz"]:
        d["fehler"] = "Ziel-PLZ fehlt"
        return d
    if fehlt:
        d["fehler"] = f"Gewicht fehlt bei Pos. {', '.join(fehlt)}"
        return d
    d["paletten"] = paletten_einst(einst)
    s["lht"], _ = paletten.ladung(positionen, werte, fdaten.get("lht", []), d["lht_standard"], d["lht_langgut"],
                                  d["paletten"])
    e = fracht.rechnen(fdaten, s)
    d.update(snapshot=e.get("snapshot"), gesamt=e.get("gesamt"), text=fracht.zusammenfassung(e),
             zone=(e.get("zone_empfang") or {}).get("text"), hinweise=e.get("hinweise", []) + e.get("warnungen", []))
    if e.get("gesamt") is None:
        d["fehler"] = "; ".join(e.get("fehler") or ["nicht berechnet"])
        if not s["versandart"] and "Mehrere Tarife" in d["fehler"]:
            d["fehler"] += " (Einstellungen › Frachtkosten: 'Versandart für automatische Fracht' festlegen)"
    return d


def paletten_einst(einst):
    """Rechenwerte der Paletten (Einstellungen palette_…) für die gespeicherte Frachtberechnung."""
    return {n: (einst or {}).get(n) for n in PALETTEN_EINST}


def _baugruppen_traeger(positionen, werte):
    """Mit Schweißbaugruppe im Angebot: {Index: (Stück, Gewicht je Stück oder None)} der Positionen, die Fracht tragen
    (paletten.packstuecke: die Baugruppe reist als ein Stück, Gewicht von Hand, sonst Summe ihrer Einzelteile; die
    Einzelteile nicht noch einmal). Ohne Baugruppe None (jede Position trägt sich selbst, wie bisher)."""
    if not any(ist_baugruppe(p) for p, w in zip(positionen, werte) if w is not None):
        return None
    return {x["i"]: (x["stueck"], x["gewicht"]) for x in paletten.packstuecke(positionen, werte)}


def ware(positionen, werte):
    """Nettogewicht und längstes Teil der Ware. werte[i] = rechnen.position_werte (None = Position ohne Profil).
    Eine Schweißbaugruppe zählt einmal (_baugruppen_traeger), ihre Einzelteile nicht doppelt.
    Ergebnis: (netto kg, max. Länge mm, [Pos. ohne Gewicht])."""
    netto, laenge, fehlt = 0.0, 0.0, []
    traeger = _baugruppen_traeger(positionen, werte)
    for i, (p, w) in enumerate(zip(positionen, werte)):
        if w is None or not p.get("stueck"):
            continue
        if traeger is not None:
            laenge = max(laenge, float(p.get("laenge") or 0))
            if i not in traeger:          # Einzelteil einer Baugruppe: reist in ihr
                continue
            stk, g = traeger[i]
            if g is None:
                fehlt.append(str(p.get("pos") or "?"))
            else:
                netto += g * stk
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
    out = [None] * len(positionen)
    hinweis = ""
    traeger = _baugruppen_traeger(positionen, werte)
    if traeger is not None:         # Schweißbaugruppe: trägt die Fracht ihrer Einzelteile (ein Packstück)
        for i in aktiv:
            out[i] = 0.0
        teile = sum(stk for stk, _ in traeger.values())
        if art == NACH_GEWICHT:
            fehlt = [str(positionen[i].get("pos") or "?") for i, (_, g) in traeger.items() if not g]
            if not fehlt:
                gesamt = sum(stk * g for stk, g in traeger.values())
                for i, (_, g) in traeger.items():
                    out[i] = betrag * g / gesamt if gesamt else 0.0
                return out, hinweis, NACH_GEWICHT
            hinweis = (f"Gewicht fehlt bei Pos. {', '.join(fehlt)}: Fracht in diesem Angebot je Stück verteilt"
                       if betrag else "")
        for i in traeger:
            out[i] = betrag / teile if teile else 0.0
        return out, hinweis, JE_STUECK
    teile = sum(positionen[i].get("stueck") or 0 for i in aktiv)
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


def sendung_der_menge(d, netto, max_laenge, positionen=None, werte=None):
    """Sendung einer Mengenstufe aus der gespeicherten Frachtberechnung d: neues Nettogewicht und längstes Teil,
    Ladungsträger per Packvorschlag (mit den Ladungsträgern des Snapshots); Verpackung und frachtpflichtiges
    Gewicht nach Tarif (von Hand eingetragene Werte gelten nur für die Menge des Angebots). Frachtberechnungen ab
    0.9.87 (mit 'paletten') packen nach Gewicht und Packraum (paletten.py), ältere wie bisher nur nach Gewicht."""
    from . import fracht        # erst hier: fracht -> ausgabe -> rechnen -> fracht_angebot
    s = dict(d.get("sendung") or {})
    s.update(netto=netto, max_laenge=max_laenge or None, verpackung=None, frachtpflichtig=None)
    if d.get("paletten") is not None and positionen is not None:
        lht, hinweise = paletten.ladung(positionen, werte, d["snapshot"].get("lht", []), d.get("lht_standard"),
                                        d.get("lht_langgut"), d["paletten"])
    else:
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
    if d and d.get("fehler"):
        return None, "", "Fracht nicht berechnet: " + d["fehler"]
    if d and not d.get("snapshot") and d.get("gesamt") == 0:      # Lieferbedingung ohne Fracht (unfrei, ab Werk …)
        return 0.0, d.get("text") or "", ""
    if not d or not d.get("snapshot"):
        return None, "", "Fracht nicht berechnet: im Angebot 'Fracht berechnen …' ausführen"
    netto, laenge, fehlt = ware(positionen, werte)
    if fehlt:
        return None, "", f"Fracht nicht berechnet: Gewicht fehlt bei Pos. {', '.join(fehlt)}"
    s, hinweise = sendung_der_menge(d, netto, laenge, positionen, werte)
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
