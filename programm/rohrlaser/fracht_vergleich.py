"""Anbietervergleich (Fracht 2.0, Patrick 25.11.2026): dieselbe Sendung mit allen passenden Tarifen rechnen und eine
Empfehlung geben (günstigster, schnellster, bestes Preis-Leistungs-Verhältnis, Langgut, Paletten).

Grundsätze:
- Geschätzte Preise werden nie als Anbieterpreis gezeigt: Tarife mit Basis Richtwert/Schätzwert (oder RICHTWERT bzw.
  BEISPIEL in der Bemerkung) heißen „Richtwert – kein Anbieterpreis“.
- Tariflücken (kein Preis bekannt) stehen mit „Tarif fehlt – Angebot einholen“ in der Liste, ohne Betrag, und werden
  nie empfohlen.
- Ohne Live-Preise wird transparent mit dem zuletzt gespeicherten Tarif gerechnet (Preisstand je Zeile).
Ohne Qt, ohne Internet.
"""
from . import fracht, packmittel_tausch
from .fracht_daten import ECHTE_PREISE, LUECKE

FEHLT = "Tarif fehlt – Angebot einholen"
BEDINGUNG = "bedingung"           # Transportbedingung nicht erfüllt: mit Preis gezeigt, nie automatisch gewählt
RICHTWERT = "Richtwert – kein Anbieterpreis"


def preisart(t):
    """'Anbieterpreis', 'Richtwert' oder 'Tariflücke' eines Tarifs."""
    b = t.get("basis")
    if b == LUECKE:
        return LUECKE
    text = (t.get("bemerkung") or "") + (t.get("tarif_id") or "")
    if b in ECHTE_PREISE and "RICHTWERT" not in text and "BEISPIEL" not in text:
        return "Anbieterpreis"
    if b is None and "RICHTWERT" not in text and "BEISPIEL" not in text:
        return "Anbieterpreis"           # eigene Tarife ohne Basis = eigene Konditionen
    return "Richtwert"


def _sendung_fuer(t, sendungen):
    art = t.get("versandart")
    if art == fracht.PAKET:
        return sendungen.get(fracht.PAKET)
    if art and art in sendungen:
        return sendungen[art]
    return sendungen.get("Palette") or next((v for k, v in sendungen.items() if k != fracht.PAKET), None) \
        or (sendungen.get(fracht.PAKET) if not art else None)


def wert(z):
    """Vergleichswert einer Zeile: Fracht + Packmitteltausch des Anbieters (wenn Tauschregeln gepflegt sind)."""
    return z["gesamt_logistik"] if z.get("gesamt_logistik") is not None else z["gesamt"]


def bedingungen(dl, e, s, zuschlaege=()):
    """Transportbedingungen des Dienstleisters (fracht_dienstleister), die die Sendung nicht erfüllt: [Text]."""
    if not dl:
        return []
    out = []
    lw = e.get("lht") or {}
    je = lw.get("je") or []
    laenge = max([fracht._n(s.get("max_laenge"))] + [fracht._n((x.get("aussen") or (0,))[0]) for x in je])
    hoehe = max([fracht._n((x.get("aussen") or (0, 0, 0))[2]) for x in je] or [0.0])
    n = lw.get("anzahl") or 0
    kg = fracht._n((e.get("gewicht") or {}).get("brutto")) / n if n else 0.0
    name = dl.get("name") or dl.get("dienstleister_id")
    if fracht._n(dl.get("max_laenge")) and laenge > dl["max_laenge"] + 1e-6:
        out.append(f"{name}: Packstück {laenge:.0f} mm lang, erlaubt {dl['max_laenge']:.0f} mm")
    if fracht._n(dl.get("max_hoehe")) and hoehe > dl["max_hoehe"] + 1e-6:
        out.append(f"{name}: Packstück {hoehe:.0f} mm hoch, erlaubt {dl['max_hoehe']:.0f} mm")
    if fracht._n(dl.get("max_kg")) and kg > dl["max_kg"] + 1e-6:
        out.append(f"{name}: {fracht.z2(kg, 1)} kg je Packstück, erlaubt {fracht.z2(dl['max_kg'], 1)} kg")
    typen = {z.get("zuschlag_id"): z.get("typ") for z in zuschlaege}
    gewaehlt = {typen.get(k) for k, v in (s.get("leistungen") or {}).items() if v}
    if dl.get("hebebuehne") == "nein" and "Hebebühne" in gewaehlt:
        out.append(f"{name}: keine Hebebühne")
    if dl.get("gefahrgut") == "nein" and "Gefahrgut" in gewaehlt:
        out.append(f"{name}: kein Gefahrgut")
    return out


def vergleich(daten, sendungen, mit_luecken=True):
    """sendungen: {Versandart oder 'Palette': Sendung} (z. B. die Paket- und die Palettenvariante einer Menge). Jeder
    aktive Tarif, der für Land, Zone, Datum und Kunde passt, wird mit der Sendung seiner Versandart gerechnet.
    Ergebnis: dict(zeilen=[…], empfehlung={…}, hinweise=[…]); Zeile: tarif_id, bezeichnung, dienstleister,
    versandart, preisart, gesamt, zuschlaege, packstuecke, laufzeit, basis, quelle, stand, status, text."""
    zeilen, hinweise = [], []
    namen = {d.get("dienstleister_id"): d.get("name") for d in daten.get("dienstleister", [])}
    dls = {d.get("dienstleister_id"): d for d in daten.get("dienstleister", [])}
    regeln = daten.get("tauschregeln") or []
    for t in daten.get("tarife", []):
        if not t.get("tarif_id") or not fracht.aktiv(t):
            continue
        if fracht.RANG.get(t.get("tarifart"), 3) == 9:
            continue                     # interne Verrechnungstarife nicht vergleichen
        s0 = _sendung_fuer(t, sendungen)
        if s0 is None:
            continue
        s = dict(s0, tarif_id=t["tarif_id"], dienstleister=None, versandart=t.get("versandart") or s0.get("versandart"))
        z = dict(tarif_id=t["tarif_id"], bezeichnung=t.get("bezeichnung") or t["tarif_id"],
                 dienstleister=namen.get(t.get("dienstleister")) or t.get("dienstleister") or "–",
                 versandart=t.get("versandart") or s.get("versandart") or "–", preisart=preisart(t),
                 basis=t.get("basis") or "", quelle=t.get("quelle") or "", stand=t.get("stand") or "",
                 laufzeit=t.get("laufzeit_tage"), gesamt=None, zuschlaege=0.0, packstuecke=None, status="", text="")
        if z["preisart"] == LUECKE:
            land = (s.get("land") or "DE").upper()
            if fracht.liste(t.get("laender")) and land not in fracht.liste(t.get("laender")):
                continue
            if not mit_luecken:
                continue
            z.update(status="lücke", text=FEHLT)
            zeilen.append(z)
            continue
        e = fracht.rechnen(daten, s)
        if e.get("gesamt") is None:
            grund = (e.get("fehler") or ["nicht berechenbar"])[0]
            if "passt nicht" in grund:
                continue                 # Land, Zone, Datum, Kunde: gehört nicht in den Vergleich
            z.update(status="fehler", text=grund)
        else:
            lw = e.get("lht") or {}
            z.update(gesamt=e["gesamt"], zuschlaege=round(sum(x["betrag"] for x in e.get("zuschlaege") or []), 2),
                     packstuecke=lw.get("anzahl"), status="ok",
                     text=RICHTWERT if z["preisart"] == "Richtwert" else (
                         "Preisstand " + fracht._datum(z["stand"]) if z["stand"] else "eigener Tarif"),
                     ergebnis=e)
            if e.get("warnungen"):
                z["warnung"] = e["warnungen"][0]
            if regeln:                   # Packmitteltausch je Anbieter (26.11.2026): gehört zum Vergleich
                pt = packmittel_tausch.kosten(lw.get("je") or [], daten.get("lht", []), regeln,
                                              t.get("dienstleister"), s.get("kundennr"), s.get("datum"))
                z.update(packmittel=round(sum(pt["posten"].values()), 2), packmittel_posten=pt["posten"],
                         packmittel_hinweise=pt["hinweise"])
                z["gesamt_logistik"] = round(z["gesamt"] + z["packmittel"], 2)
            nicht = bedingungen(dls.get(t.get("dienstleister")), e, s, daten.get("zuschlaege", []))
            if nicht:
                z.update(status=BEDINGUNG, text="Bedingung nicht erfüllt: " + "; ".join(nicht))
        zeilen.append(z)
    zeilen.sort(key=lambda z: (z["gesamt"] is None, z["status"] == BEDINGUNG, wert(z) if z["gesamt"] is not None
                               else 0, z["tarif_id"]))
    if not any(z["status"] == "ok" for z in zeilen):
        hinweise.append("Kein Tarif mit Preis passt: Angebot einholen und als Tarif eintragen")
    return dict(zeilen=zeilen, empfehlung=empfehlung(zeilen, sendungen), hinweise=hinweise)


def _langgut(sendungen):
    """Langgut: ein Teil ab 2.500 mm (Sendung max_laenge)."""
    return any(fracht._n(s.get("max_laenge")) >= 2500 for s in sendungen.values())


def empfehlung(zeilen, sendungen=None):
    """Empfehlung aus den gerechneten Zeilen (Tariflücken nie): günstigster, schnellster (kleinste Laufzeit, bei
    gleicher die günstigere), Preis-Leistung (günstigster, der höchstens 1 Arbeitstag langsamer ist als der
    schnellste), Langgut und Paletten (günstigster Nicht-Paket-Tarif). Richtwerte nur, wenn kein Anbieterpreis da ist.
    Ergebnis: {art: Zeile} + 'automatisch' (Preis-Leistung, sonst günstigster) + 'begruendung'."""
    ok = [z for z in zeilen if z["status"] == "ok"]
    echt = [z for z in ok if z["preisart"] == "Anbieterpreis"]
    basis = echt or ok
    out = {}
    if not basis:
        return out
    out["guenstigster"] = min(basis, key=lambda z: (wert(z), z["tarif_id"]))
    mit_zeit = [z for z in basis if isinstance(z.get("laufzeit"), int)]
    if mit_zeit:
        out["schnellster"] = min(mit_zeit, key=lambda z: (z["laufzeit"], wert(z), z["tarif_id"]))
        grenze = out["schnellster"]["laufzeit"] + 1
        pl = [z for z in mit_zeit if z["laufzeit"] <= grenze]
        out["preis_leistung"] = min(pl, key=lambda z: (wert(z), z["laufzeit"], z["tarif_id"]))
    pal = [z for z in basis if z["versandart"] != fracht.PAKET]
    if pal:
        out["paletten"] = min(pal, key=lambda z: (wert(z), z["tarif_id"]))
        if sendungen and _langgut(sendungen):
            out["langgut"] = out["paletten"]
    wahl = out.get("preis_leistung") or out["guenstigster"]
    out["automatisch"] = wahl
    grund = [f"{wahl['bezeichnung']} ({fracht.euro(wahl['gesamt'])}" + (
        f" + Packmitteltausch {fracht.euro(wahl['packmittel'])}" if wahl.get('packmittel') else "") + ")"]
    if wahl is out.get("preis_leistung") and wahl is not out["guenstigster"]:
        grund.append(f"höchstens 1 Arbeitstag langsamer als der schnellste, günstigster wäre "
                     f"{out['guenstigster']['bezeichnung']} ({fracht.euro(out['guenstigster']['gesamt'])})")
    elif wahl is out["guenstigster"]:
        grund.append("günstigster Tarif")
    if not echt:
        grund.append("nur Richtwerte vorhanden – kein Anbieterpreis, Angebot einholen")
    out["begruendung"] = "; ".join(grund)
    return out
