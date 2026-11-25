"""Fracht im Angebot und in den Staffelpreisen (ohne Oberfläche).

Angebotskopf:
- fracht_modus: manuell (leer, wie bisher: Betrag 'fracht' von Hand), berechnet (Betrag aus der Frachtberechnung,
  Eingaben und Tarif-Snapshot in fracht_sendung), keine Fracht (Abholung, ab Werk) oder im Artikelpreis enthalten
  (beide 0 € in der Kalkulation, Hinweis im Angebot; so wird Fracht nie doppelt berechnet).
- fracht_umlage: je Stück (leer, wie bisher) oder nach Gewicht (Anteil des Teilegewichts am Gesamtgewicht; fehlt
  einer Position das Gewicht, wird im ganzen Angebot je Stück verteilt, mit Hinweis). Neue Angebote: nach Gewicht.
- fracht_sendung: JSON {sendung, snapshot, gesamt, text, lht_standard, lht_langgut, paletten, alternative} aus der
  Frachtberechnung (alternative: Tarifkopie der anderen Versandart Paket/Palette für die Staffeln, ab 0.9.381).
- fracht_auto = ja ('Fracht automatisch berechnen', Vorgabe aus): Ziel-PLZ (zwei Stellen reichen) und Land
  (fracht_plz, fracht_land), Gewicht aus den Positionen, Ladungsträger per Packvorschlag, Tarif automatisch,
  Versandart aus den Einstellungen, nur Zuschläge mit Bedingung 'immer'. Zone und Tarif werden beim Setzen des
  Hakens bzw. beim Ändern der PLZ festgehalten (Tarifkopie); jede Änderung der Positionen rechnet damit neu.

Staffelpreise: Im Modus 'berechnet' rechnet jede Mengenstufe Nettogewicht, Ladungsträger (Packvorschlag) und
Fracht mit dem gespeicherten Tarif-Snapshot neu; in den übrigen Modi gilt der Betrag des Angebots für alle Mengen.
"""
import json

from . import entfernung, paletten
from .angebot import ist_baugruppe

PALETTEN_EINST = ("palette_hoehe_gesamt", "palette_max_brutto", "palette_mischen", "palette_fuellgrad",
                  "palette_zwischenlage")

MANUELL, BERECHNET, KEINE, ENTHALTEN = "manuell", "berechnet", "keine Fracht", "im Artikelpreis enthalten"
MODI = (MANUELL, BERECHNET, KEINE, ENTHALTEN)
JE_STUECK, NACH_GEWICHT = "je Stück", "nach Gewicht"
# Fracht 2.0 (Patrick 25.11.2026): nach Packvolumen (paletten.packmass) bzw. als eigene Zeile im Angebot
NACH_VOLUMEN, EIGENE = "nach Volumen", "eigene Position"
UMLAGEN = (JE_STUECK, NACH_GEWICHT, NACH_VOLUMEN, EIGENE)
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
             netto=netto, max_laenge=laenge or None, leistungen={}, auto=True,
             umwegfaktor=(einst or {}).get("fracht_umwegfaktor"))
    if isinstance(kopf.get("fracht_km"), (int, float)) and kopf["fracht_km"] > 0:
        s.update(km=kopf["fracht_km"], km_quelle=entfernung.QUELLE_HAND)
    entfernung.ergaenzen(s)
    d = dict(sendung=s, snapshot=None, gesamt=None, text="", lht_standard=einst.get("fracht_lht_standard"),
             lht_langgut=einst.get("fracht_lht_langgut"))
    if (einst or {}).get("fracht_packmittel_kosten") == "ja":     # Fracht 2.0: Packmittelkosten aus der Packliste
        d["packmittel_aktiv"] = True
    if not s["plz"]:
        d["fehler"] = "Ziel-PLZ fehlt"
        return d
    if fehlt:
        d["fehler"] = f"Gewicht fehlt bei Pos. {', '.join(fehlt)}"
        return d
    d["paletten"] = paletten_einst(einst)
    if ist_paket(s):              # Paketversand: günstigster Karton, nie Palette (ein Paket-Tarif kennt keine)
        k = paletten.guenstigster_karton(positionen, werte, fdaten.get("lht", []), d["paletten"],
                                         lambda lht: fracht.rechnen(fdaten, dict(s, lht=lht)).get("gesamt"))
        if k is not None:
            s["lht"] = k["lht"]
        else:                     # passt in keinen Karton: als Palette (F1), Versandart ohne Paket
            s["versandart"] = None
            d["hinweis_paket"] = "Teile passen in keinen Karton: Fracht als Palette gerechnet"
    if not s.get("lht"):
        s["lht"], _ = paletten.ladung(positionen, werte, fdaten.get("lht", []), d["lht_standard"],
                                      d["lht_langgut"], d["paletten"])
    e = fracht.rechnen(fdaten, s)
    if e.get("snapshot"):
        d["alternative"] = alternative(fdaten, s, d["lht_standard"])
    d.update(snapshot=e.get("snapshot"), gesamt=e.get("gesamt"), text=fracht.zusammenfassung(e),
             zone=(e.get("zone_empfang") or {}).get("text"), km_text=s.get("km_text"), hinweise=e.get("hinweise", []) + e.get("warnungen", []))
    if d.get("hinweis_paket"):
        d["hinweise"].insert(0, d.pop("hinweis_paket"))
    if e.get("snapshot") and e.get("gesamt") is not None:
        # wie jede Staffelmenge die günstigste Ladung (F1/F2), damit Feld Frachtkosten und Stufe gleich rechnen
        v = _varianten(d, s, positionen, werte)
        if v and round(v[0]["gesamt"], 2) < round(e["gesamt"], 2):
            e2 = fracht.nachrechnen(v[0]["snapshot"], v[0]["sendung"])
            if e2.get("gesamt") is not None:
                if v[0]["haupt"]:
                    s["lht"] = v[0]["lht"]
                d.update(gesamt=e2["gesamt"], text=fracht.zusammenfassung(e2))
    if e.get("gesamt") is None:
        d["fehler"] = "; ".join(e.get("fehler") or ["nicht berechnet"])
        if not s["versandart"] and "Mehrere Tarife" in d["fehler"]:
            d["fehler"] += " (Einstellungen › Frachtkosten: 'Versandart für automatische Fracht' festlegen)"
    return d


KEIN_KARTON = ("Paketversand: die Teile passen in keinen Karton (zu lang, zu schwer oder ohne Maße/Gewicht) – "
               "Palette wählen oder Fracht von Hand")


def ist_paket(s, snapshot=None):
    """Wird die Sendung als Paket verschickt? Versandart Paket, oder (ältere Berechnungen) alle Ladungsträger der
    Sendung sind Kartons."""
    from .fracht import PAKET
    if (s or {}).get("versandart") == PAKET:
        return True
    arten = {z.get("lht_id"): z.get("art") for z in (snapshot or {}).get("lht", [])}
    lht = [x.get("lht_id") for x in (s or {}).get("lht") or ()]
    return bool(lht) and all(arten.get(i) == paletten.KARTON for i in lht)


def paletten_einst(einst):
    """Rechenwerte der Paletten (Einstellungen palette_…) für die gespeicherte Frachtberechnung."""
    return {n: (einst or {}).get(n) for n in PALETTEN_EINST}


def _baugruppen_traeger(positionen, werte):
    """Mit Schweißbaugruppe im Angebot: {Index: (Stück, Gewicht je Stück oder None, Packmaße (l, b, h) oder None)} der
    Positionen, die Fracht tragen
    (paletten.packstuecke: die Baugruppe reist als ein Stück, Gewicht von Hand, sonst Summe ihrer Einzelteile; die
    Einzelteile nicht noch einmal). Ohne Baugruppe None (jede Position trägt sich selbst, wie bisher)."""
    if not any(ist_baugruppe(p) for p, w in zip(positionen, werte) if w is not None):
        return None
    return {x["i"]: (x["stueck"], x["gewicht"], x.get("masse")) for x in paletten.packstuecke(positionen, werte)}


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
            stk, g, masse = traeger[i]
            if masse:                     # Packmaß der Baugruppe kann länger sein als jedes Einzelteil
                laenge = max(laenge, float(masse[0]))
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
        teile = sum(stk for stk, _, _ in traeger.values())
        if art == NACH_GEWICHT:
            fehlt = [str(positionen[i].get("pos") or "?") for i, (_, g, _) in traeger.items() if not g]
            if not fehlt:
                gesamt = sum(stk * g for stk, g, _ in traeger.values())
                for i, (_, g, _) in traeger.items():
                    out[i] = betrag * g / gesamt if gesamt else 0.0
                return out, hinweis, NACH_GEWICHT
            hinweis = (f"Gewicht fehlt bei Pos. {', '.join(fehlt)}: Fracht in diesem Angebot je Stück verteilt"
                       if betrag else "")
        for i in traeger:
            out[i] = betrag / teile if teile else 0.0
        return out, hinweis, JE_STUECK
    teile = sum(positionen[i].get("stueck") or 0 for i in aktiv)
    if art == EIGENE:               # Fracht als eigene Zeile im Angebot: nicht in den Stückpreisen (eigene_position)
        for i in aktiv:
            out[i] = 0.0
        return out, hinweis, EIGENE
    if art == NACH_VOLUMEN:         # Anteil des Packvolumens (Packmaß L × B × H) am Gesamtvolumen
        vol = {}
        for i in aktiv:
            m = paletten.packmass(positionen[i], werte[i])
            vol[i] = (m[0] * m[1] * m[2]) if m and all(m) else None
        fehlt = [str(positionen[i].get("pos") or "?") for i in aktiv
                 if (positionen[i].get("stueck") or 0) > 0 and not vol[i]]
        if not fehlt:
            gesamt = sum(vol[i] * (positionen[i].get("stueck") or 0) for i in aktiv)
            for i in aktiv:
                out[i] = betrag * vol[i] / gesamt if gesamt else 0.0
            return out, hinweis, NACH_VOLUMEN
        hinweis = (f"Packmaß fehlt bei Pos. {', '.join(fehlt)}: Fracht in diesem Angebot je Stück verteilt"
                   if betrag else "")
        for i in aktiv:
            out[i] = betrag / teile if teile else 0.0
        return out, hinweis, JE_STUECK
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


def alternative(fdaten, sendung, lht_standard=None):
    """Tarifkopie der anderen Versandart für die Staffeln (Patrick 17.11.2026, F1): ist die Fracht als Paket
    berechnet, die der Palette (Versandart wie eingestellt, ohne Paket), sonst die des Paketversands. Ergebnis:
    dict(snapshot, paket, versandart) oder None (kein passender Tarif)."""
    from . import fracht
    s = dict(sendung or {})
    paket = not ist_paket(s, dict(lht=fdaten.get("lht", [])))
    if paket:
        kt = paletten.kartons(fdaten.get("lht", []))
        if not kt:
            return None
        lht, versandart = [dict(lht_id=kt[0]["lht_id"], anzahl=1)], fracht.PAKET
    else:
        kand = paletten.kandidaten(fdaten.get("lht", []), None)
        ids = [z["lht_id"] for z in kand]
        if not ids:
            return None
        lht = [dict(lht_id=lht_standard if lht_standard in ids else ids[0], anzahl=1)]
        versandart = None
    s.update(lht=lht, versandart=versandart, tarif_id=None, dienstleister=None, verpackung=None,
             frachtpflichtig=None)
    e = fracht.rechnen(fdaten, s)
    if e.get("gesamt") is None or not e.get("snapshot"):
        return None
    return dict(snapshot=e["snapshot"], paket=paket, versandart=versandart)


def _varianten(d, s, positionen, werte):
    """Alle Ladungen einer Mengenstufe mit Preis: je Tarifkopie (die des Angebots und ggf. die der anderen
    Versandart) jeder Standard-Ladungsträger (lange Teile auf Langgut) bzw. jede Kartongröße (F1, F2).
    Ergebnis: Liste dict(gesamt, snapshot, sendung, paket, haupt, std_id, lht), günstigste zuerst."""
    from . import fracht
    haupt = d["snapshot"]
    quellen = [(haupt, ist_paket(d.get("sendung"), haupt), (d.get("sendung") or {}).get("versandart"), True)]
    alt = d.get("alternative")
    if alt and alt.get("snapshot"):
        quellen.append((alt["snapshot"], bool(alt.get("paket")), alt.get("versandart"), False))
    out = []
    for snap, paket, versandart, ist_haupt in quellen:
        s2 = dict(s, versandart=versandart)

        def preis(lht, snap=snap, s2=s2):
            return fracht.nachrechnen(snap, dict(s2, lht=lht)).get("gesamt")
        lz = snap.get("lht", [])
        if paket:
            liste = paletten.karton_varianten(positionen, werte, lz, d.get("paletten"), preis)
        else:
            liste = paletten.guenstigste(positionen, werte, lz, d.get("lht_standard"), d.get("lht_langgut"),
                                         d.get("paletten"), preis)
        for x in liste:
            if x["gesamt"] is not None:
                out.append(dict(gesamt=x["gesamt"], snapshot=snap, sendung=dict(s2, lht=x["lht"]), paket=paket,
                                haupt=ist_haupt, std_id=x["std_id"], lht=x["lht"]))
    out.sort(key=lambda x: (round(x["gesamt"], 2), not x["haupt"], x["std_id"] != d.get("lht_standard"),
                            sum(t["anzahl"] for t in x["lht"]), x["std_id"]))
    return out


def sendung_der_menge(d, netto, max_laenge, positionen=None, werte=None):
    """Sendung einer Mengenstufe aus der gespeicherten Frachtberechnung d: neues Nettogewicht und längstes Teil,
    Verpackung und frachtpflichtiges Gewicht nach Tarif (von Hand eingetragene Werte gelten nur für die Menge des
    Angebots). Mit Positionen (Frachtberechnungen ab 0.9.87, 'paletten'): die günstigste Ladung (Patrick
    17.11.2026, F1/F2) aus jedem Standard-Ladungsträger bzw. jeder Kartongröße, mit der Tarifkopie des Angebots und
    der der anderen Versandart (Paket oder Palette, 'alternative'). Ältere wie bisher nur nach Gewicht.
    Ergebnis: (Sendung oder None, Hinweise, Tarifkopie, Vergleichstext)."""
    from . import fracht        # erst hier: fracht -> ausgabe -> rechnen -> fracht_angebot
    s = dict(d.get("sendung") or {})
    s.update(netto=netto, max_laenge=max_laenge or None, verpackung=None, frachtpflichtig=None)
    snap = d["snapshot"]
    if d.get("paletten") is not None and positionen is not None:
        v = _varianten(d, s, positionen, werte)
        if v:
            beste = v[0]
            vergleich = ""
            andere = next((x for x in v if x["paket"] != beste["paket"]), None)
            if andere:
                vergleich = (f"{'Paket' if beste['paket'] else 'Palette'} günstiger als "
                             f"{'Paket' if andere['paket'] else 'Palette'} {fracht.euro(andere['gesamt'])}")
            return beste["sendung"], [], beste["snapshot"], vergleich
        if ist_paket(d.get("sendung"), snap) and not (d.get("alternative") or {}).get("snapshot"):
            return None, [KEIN_KARTON], snap, ""
        lht, hinweise = paletten.ladung(positionen, werte, snap.get("lht", []), d.get("lht_standard"),
                                        d.get("lht_langgut"), d["paletten"])
    else:
        lht, hinweise = fracht.packvorschlag([(netto, max_laenge)], snap.get("lht", []),
                                             d.get("lht_standard"), d.get("lht_langgut"))
    if lht:
        s["lht"] = lht
    else:
        hinweise = hinweise + ["Ladungsträger wie in der Frachtberechnung des Angebots"]
    return s, hinweise, snap, ""


def stufe_details(kopf, positionen, werte):
    """Fracht einer Mengenstufe (positionen mit den Stückzahlen der Stufe) mit Angaben für die Anzeige (F3):
    dict(betrag oder None, text, fehler, ladung z. B. '2 × EUR', versand 'Paket'/'Palette'/'', brutto kg)."""
    from . import fracht
    out = dict(betrag=None, text="", fehler="", ladung="", versand="", brutto=None)
    if modus(kopf) != BERECHNET:
        return dict(out, betrag=wirksam(kopf))
    d = daten(kopf)
    if d and d.get("fehler"):
        return dict(out, fehler="Fracht nicht berechnet: " + d["fehler"])
    if d and not d.get("snapshot") and d.get("gesamt") == 0:      # Lieferbedingung ohne Fracht (unfrei, ab Werk …)
        return dict(out, betrag=0.0, text=d.get("text") or "")
    if not d or not d.get("snapshot"):
        return dict(out, fehler="Fracht nicht berechnet: im Angebot 'Fracht berechnen …' ausführen")
    netto, laenge, fehlt = ware(positionen, werte)
    if fehlt:
        return dict(out, fehler=f"Fracht nicht berechnet: Gewicht fehlt bei Pos. {', '.join(fehlt)}")
    s, hinweise, snap, vergleich = sendung_der_menge(d, netto, laenge, positionen, werte)
    if s is None:
        return dict(out, fehler="Fracht nicht berechnet: " + "; ".join(hinweise))
    e = fracht.nachrechnen(snap, s)
    if e.get("gesamt") is None:
        return dict(out, fehler="Fracht nicht berechnet: " + "; ".join(e.get("fehler") or ["–"]))
    lw = e.get("lht") or {}
    g = e.get("gewicht") or {}
    lht = ", ".join(f"{x['anzahl']} × {x['lht_id']}" for x in lw.get("je", []))
    versand = "Paket" if ist_paket(s, snap) else ("Palette" if lht else "")
    text = f"Fracht {fracht.euro(e['gesamt'])}: {fracht.z2(g.get('brutto') or 0, 1)} kg brutto" + \
        (f", {lht}" if lht else "") + (f" ({vergleich})" if vergleich else "")
    return dict(out, betrag=e["gesamt"], text=text, ladung=lht, versand=versand, brutto=g.get("brutto"))


def stufe(kopf, positionen, werte):
    """Fracht einer Mengenstufe (positionen mit den Stückzahlen der Stufe).
    Ergebnis: (Betrag oder None, Text für die Stufe, Fehlertext oder '')."""
    x = stufe_details(kopf, positionen, werte)
    return x["betrag"], x["text"], x["fehler"]


def eigene_position(kopf, summen, einst=None):
    """Umlage „eigene Position“: Fracht (und Packmittel aus der Packliste) als eigene Zeile, Verkaufspreis um den
    Betrag erhöht (ohne Gewinn, wie umgelegte Fracht). Frachtfrei ab Warenwert gilt auch hier. Ohne diese Umlage
    unverändert. Setzt summen fracht_position."""
    if umlage(kopf) != EIGENE or kopf.get("fracht_position_aus") == "ja":    # Staffelstufen: Preise ohne Fracht
        return summen
    betrag = float(summen.get("fracht") or 0)
    if betrag <= 0:
        return summen
    frei_ab = float((einst or {}).get("frachtfrei_ab") or 0)
    if frei_ab > 0 and float(summen.get("verkauf") or 0) >= frei_ab:
        summen.update(fracht_position=0.0, fracht_position_text=f"frachtfrei ab {frei_ab:g} € Warenwert")
        return summen
    summen.update(fracht_position=betrag, verkauf=float(summen.get("verkauf") or 0) + betrag)
    return summen


def position_text(kopf):
    """Text der eigenen Frachtzeile im Angebot."""
    s = (daten(kopf) or {}).get("sendung") or {}
    ziel = " ".join(x for x in ((s.get("land") or "DE"), s.get("plz") or "") if x)
    return "Fracht und Verpackung" + (f" frei Haus nach {ziel}" if s.get("plz") else "")


def packmittel_aktiv(kopf):
    """Packmittelkosten aus der Packliste der gespeicherten Frachtberechnung (Fracht 2.0)? Nur wenn die Berechnung
    es festgehalten hat (Einstellung fracht_packmittel_kosten beim Rechnen) – ältere Angebote rechnen wie bisher."""
    d = daten(kopf)
    return bool(d and d.get("packmittel_aktiv") and modus(kopf) == BERECHNET)


def packmittel(kopf, positionen, werte, satz_verpackung=0.0):
    """Packmittelkosten (paletten.packmittel_kosten) der Sendung mit den Packmitteln der Tarifkopie; automatisch
    berechnete Fracht packt mit den aktuellen Mengen neu (wie jede Staffelstufe). None, wenn nicht aktiv."""
    if not packmittel_aktiv(kopf):
        return None
    d = daten(kopf)
    lht = ((d.get("snapshot") or {}).get("lht")) or []
    s = d.get("sendung") or {}
    eintraege = s.get("lht") or []
    if auto(kopf) and positionen is not None and werte is not None:
        eintraege, _ = paletten.ladung(positionen, werte, lht, d.get("lht_standard"), d.get("lht_langgut"),
                                       d.get("paletten"))
    return paletten.packmittel_kosten(eintraege, lht, satz_verpackung)


def angebotstext(kopf):
    """Hinweis zur Fracht im Angebots-PDF (leer im Modus manuell: wie bisher)."""
    m = modus(kopf)
    if m == KEINE:
        return "Lieferung ab Werk; Frachtkosten sind nicht enthalten."
    if m == ENTHALTEN:
        return "Die Frachtkosten sind in den Preisen enthalten."
    if umlage(kopf) == EIGENE and m in (MANUELL, BERECHNET) and wirksam(kopf):
        return "Fracht und Verpackung stehen als eigene Position im Angebot."
    if m == BERECHNET and wirksam(kopf):
        s = (daten(kopf) or {}).get("sendung") or {}
        ziel = " ".join(x for x in ((s.get("land") or "DE"), s.get("plz") or "") if x)
        return f"Die Preise enthalten die Fracht frei Haus{(' nach ' + ziel) if s.get('plz') else ''}."
    return ""
