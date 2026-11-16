"""Letzte Preisschicht der Kalkulation (Vorschläge vom 02.11.2026: G2 Verpackung, G3 Finanzierung, G6 Runden,
G7 Kundenkonditionen, J1 Preisuntergrenze, J3 mannlose Laufzeit, J6 Neuteil-Zuschlag).

rechnen.kalkulation ruft anwenden() nach der eigentlichen Rechnung auf. Jeder Baustein ist ohne Einstellung bzw.
Angebotswert aus (0 oder leer); dann bleibt jeder Preis bitgleich wie bisher. Reihenfolge:
  1. J3 mannlose Laufzeit: Laserstunden eines Laufs über „Mannlos: ab Laufzeit je Los“ der Maschine mit dem
     kleineren Stundensatz „Mannlos: Stundensatz“ (Unterschied mit Zuschlag Fertigung und Gewinn).
  2. J6 Neuteil-Zuschlag (Einstellung neuteil_zuschlag) auf Material und Laser der Positionen, die im Angebot als
     Neuteil vermerkt sind (Angebotsfenster: kein beauftragtes Wiederholteil), ohne Gewinn.
  2b. V4 Angebotsregeln (Vorschläge 11.11.2026): Zuschlag [%] der Regeln mit Wirkung „Zuschlag“ auf den Preis der
     passenden Positionen ohne Fracht (Tabelle tabellen['angebotsregeln']; festgeschriebene Angebote: Regeln der
     Preisbasis, ältere ohne).
  3. G2 Verpackung aus den Stammdaten Verpackung (billigstes passendes Packmittel nach Gewicht und längstem Teil),
     je Angebot abschaltbar (Kopf „Verpackung berechnen“ = nein), ohne Gewinn, nach Gewicht verteilt.
  4. G3 Finanzierung: Selbstkosten × Zins × (Zahlungsziel + Tage Material bis Lieferung) ÷ 360, ohne Gewinn.
  5. G7 Frachtfrei ab Warenwert (Kunde/Angebot): Fracht entfällt; Rabatt [%] auf den Preis.
  6. G6 Runden: Stückpreis aufwärts auf „Stückpreis runden auf“; nur ohne Stückrundung der Gesamtpreis aufwärts auf
     „Gesamtpreis runden auf“ (anteilig auf die Positionen).
Danach J1: Preisuntergrenze kurzfristig (variable Kosten) und langfristig (Selbstkosten + Fracht und Verpackung)
je Teil und gesamt, nur zur Anzeige (Kopf, Angebots-Check, Zielpreis). Ohne Qt."""
import json
import math

FELDER = ("mannlos", "neuteil", "regel", "verpackung", "finanzierung", "frachtfrei", "rabatt", "rundung")
ZUSATZ_FELDER = ("preis_hand",)     # nur mit Wert in Zeilen und Summen (Preis von Hand je Baugruppe, 12.11.2026)


def _n(w):
    try:
        return float(w) if w not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def neuteile(kopf):
    """Positions-IDs, die als Neuteil vermerkt sind (Kopffeld neuteile, JSON-Liste)."""
    w = (kopf or {}).get("neuteile")
    if isinstance(w, (list, tuple, set)):
        return {int(x) for x in w}
    try:
        return {int(x) for x in json.loads(w)} if w else set()
    except (TypeError, ValueError):
        return set()


def stueckpreis(z, satz_verpackung=0.0):
    """Preis je Packmittel + CALC-026 Bündeln/Umreifen (Zeit × Stundensatz „Verpackung“) und Material."""
    return _n(z.get("preis")) + _n(z.get("material_bund")) + _n(z.get("zeit_bund")) / 60 * _n(satz_verpackung)


def packmittel(verpackung, gewicht, laenge, satz_verpackung=0.0):
    """Billigstes Packmittel der Stammdaten, in das das längste Teil passt: (Zeile, Anzahl) oder None. Anzahl =
    Gewicht ÷ max. Gewicht aufgerundet, mindestens 1."""
    beste = None
    for z in verpackung or ():
        if str(z.get("aktiv") or "ja") == "nein" or not stueckpreis(z, satz_verpackung):
            continue
        if _n(z.get("max_laenge")) and laenge > _n(z["max_laenge"]) + 1e-6:
            continue
        n = max(1, math.ceil(gewicht / _n(z["max_kg"]) - 1e-9)) if _n(z.get("max_kg")) else 1
        kosten = n * stueckpreis(z, satz_verpackung)
        if beste is None or kosten < beste[2]:
            beste = (z, n, kosten)
    return (beste[0], beste[1]) if beste else None


def _verteilen(zeilen, betrag, gewichte):
    """Betrag nach Gewichten (je Zeile, Summe je Position) auf die Teile: {id(z): € je Teil}."""
    ges = sum(gewichte.values())
    out = {}
    for z in zeilen:
        if z and z["stueck"]:
            anteil = gewichte.get(id(z), 0.0) / ges if ges else 0.0
            out[id(z)] = betrag * anteil / z["stueck"]
    return out


def anwenden(kopf, positionen, zeilen, summen, k, tabellen, einst):
    """Bausteine anwenden (zeilen und summen werden geändert). Ergebnis: summen."""
    from . import rechnen
    kopf = kopf or {}
    aktiv = [z for z in zeilen if z and z.get("stueck")]
    skonto = _n(summen.get("skonto_satz")) / 100
    gew = _n(summen.get("gewinn_satz")) if summen.get("gewinn_gestaffelt") else _n(einst.get("gewinn"))
    zf = _n(einst.get("zuschlag_fertigung")) + _n(einst.get("eilzuschlag"))
    plus = {id(z): dict.fromkeys(FELDER + ZUSATZ_FELDER, 0.0) for z in aktiv}
    info = {}

    # 1. J3 mannlose Laufzeit
    m = rechnen.maschine(kopf, k) or {}
    ab, satz_m = _n(m.get("mannlos_ab")), m.get("mannlos_satz")
    satz = _n(summen.get("satz_laser"))
    laser_h = sum(_n(z.get("laser_netto")) * z["stueck"] for z in aktiv) / 3600
    laeufe = max(1, int(_n(summen.get("laeufe")) or 1))
    if ab > 0 and satz_m not in (None, "") and satz > _n(satz_m) and laser_h / laeufe > ab:
        h_mannlos = laser_h - ab * laeufe
        betrag = -h_mannlos * (satz - _n(satz_m)) * (1 + zf) * (1 + gew)
        gewichte = {id(z): _n(z.get("laser_netto")) * z["stueck"] for z in aktiv}
        for i, w in _verteilen(aktiv, betrag, gewichte).items():
            plus[i]["mannlos"] = w
        info.update(mannlos_h=h_mannlos, mannlos_satz=_n(satz_m))

    # 2. J6 Neuteil-Zuschlag
    nz = _n(einst.get("neuteil_zuschlag"))
    neu_ids = neuteile(kopf)
    if nz > 0 and neu_ids:
        for p, z in zip(positionen, zeilen):
            if z and z.get("stueck") and p.get("id") in neu_ids:
                plus[id(z)]["neuteil"] = (_n(z.get("material_teil")) + _n(z.get("laser_teil"))) * nz
        info["neuteil_satz"] = 100 * nz

    # 2b. V4 Angebotsregeln: Zuschlag auf den Preis ohne Fracht der passenden Positionen
    regeln = (tabellen or {}).get("angebotsregeln") or ()
    if regeln:
        from . import angebotsregeln
        try:
            zu = angebotsregeln.zuschlaege(regeln, kopf, positionen, k, (tabellen or {}).get("gewinde") or ())
        except Exception:           # eine kaputte Regel darf die Rechnung nie anhalten
            zu = {}
        namen = []
        for i, (anteil, regel_namen) in zu.items():
            z = zeilen[i] if i < len(zeilen) else None
            if z and z.get("stueck"):
                plus[id(z)]["regel"] = (z["preis_teil"] * (1 - skonto) - _n(z.get("fracht_teil"))) * anteil
                namen += [n for n in regel_namen if n not in namen]
        if namen:
            info["regel_namen"] = namen

    # 3. G2 Verpackung
    verpackung = (tabellen or {}).get("verpackung") or ()
    if verpackung and kopf.get("verpackung") != "nein":
        werte = {id(z): rechnen.position_werte(p, kopf, k, tabellen) for p, z in zip(positionen, zeilen)
                 if z and z.get("stueck")}
        gewichte = {i: _n((w or {}).get("gewicht")) * next(z["stueck"] for z in aktiv if id(z) == i)
                    for i, w in werte.items()}
        laenge = max((_n(p.get("laenge")) for p, z in zip(positionen, zeilen) if z and z.get("stueck")), default=0.0)
        satz_v = _n(rechnen.stundensaetze(tabellen).get("Verpackung"))
        wahl = packmittel(verpackung, sum(gewichte.values()), laenge, satz_v)
        if wahl:
            zeile, n = wahl
            betrag = n * stueckpreis(zeile, satz_v)
            for i, w in _verteilen(aktiv, betrag, gewichte if sum(gewichte.values()) else
                                   {id(z): z["stueck"] for z in aktiv}).items():
                plus[i]["verpackung"] = w
            bund = _n(zeile.get("material_bund")) or _n(zeile.get("zeit_bund"))
            info.update(verpackung_text=f"{n} × {zeile.get('name') or 'Packmittel'}"
                        + (" inkl. Bündeln/Umreifen" if bund else ""), verpackung_anzahl=n)

    # 4. G3 Finanzierung
    zins = _n(einst.get("finanz_zins"))
    if zins > 0:
        tage = _n(kopf.get("zahlungsziel") if kopf.get("zahlungsziel") not in (None, "") else
                  einst.get("zahlungsziel")) + _n(einst.get("termin_material_tage"))
        for z in aktiv:
            plus[id(z)]["finanzierung"] = _n(z.get("selbst_teil")) * zins * tage / 360
        info.update(finanzierung_tage=tage, finanzierung_satz=100 * zins)

    # Zwischenstand je Teil (ohne Skonto), dann Skonto wie bisher im Hundert
    for z in aktiv:
        d = plus[id(z)]
        roh = sum(d.values())
        if roh:
            z["preis_teil"] += roh / (1 - skonto)

    # 5. G7 Frachtfrei und Rabatt
    frei_ab = _n(einst.get("frachtfrei_ab"))
    ware = sum((z["preis_teil"] * (1 - skonto) - _n(z.get("fracht_teil"))) * z["stueck"] for z in aktiv)
    if frei_ab > 0 and ware >= frei_ab and any(_n(z.get("fracht_teil")) for z in aktiv):
        for z in aktiv:
            w = -_n(z.get("fracht_teil"))
            plus[id(z)]["frachtfrei"] = w
            z["preis_teil"] += w / (1 - skonto)
        info["frachtfrei_ab"] = frei_ab
    rabatt = _n(einst.get("rabatt"))
    if rabatt > 0:
        for z in aktiv:
            w = -z["preis_teil"] * (1 - skonto) * rabatt
            plus[id(z)]["rabatt"] = w
            z["preis_teil"] += w / (1 - skonto)
        info["rabatt_satz"] = 100 * rabatt

    # 6. G6 Runden (aufwärts)
    r_stk, r_ges = _n(einst.get("runden_stueck")), _n(einst.get("runden_gesamt"))
    if r_stk > 0:
        for z in aktiv:
            neu = math.ceil(round(z["preis_teil"] / r_stk, 9)) * r_stk
            plus[id(z)]["rundung"] = (neu - z["preis_teil"]) * (1 - skonto)
            z["preis_teil"] = neu
        info["rundung_art"] = f"Stückpreis auf {r_stk:g} €".replace(".", ",")
    elif r_ges > 0 and aktiv:
        ges = sum(z["preis_teil"] * z["stueck"] for z in aktiv)
        ziel = math.ceil(round(ges / r_ges, 9)) * r_ges
        if ges > 0 and ziel > ges:
            f = ziel / ges
            for z in aktiv:
                plus[id(z)]["rundung"] = z["preis_teil"] * (f - 1) * (1 - skonto)
                z["preis_teil"] *= f
        info["rundung_art"] = f"Gesamtpreis auf {r_ges:g} €".replace(".", ",")

    # 7. Verkaufspreis von Hand je Schweißbaugruppe (12.11.2026, F4 a): Gesamtpreis je Baugruppe inkl. ihrer
    #    Einzelteile; der Unterschied zum berechneten Preis landet in der Baugruppen-Zeile (wie Gewinn)
    hand = _preis_hand(positionen, zeilen)
    for i, (ziel, berechnet, selbst) in hand.items():
        z = zeilen[i]
        diff = ziel - berechnet
        z["preis_teil"] += diff
        plus[id(z)]["preis_hand"] = diff * (1 - skonto)
        z["bg_preis_hand"] = dict(ziel=ziel, berechnet=berechnet, diff=diff, selbst=selbst)
        if ziel * (1 - skonto) < selbst - 1e-6:
            z["hinweis"] = (f"Preis von Hand {ziel:.2f} € unter Selbstkosten {selbst:.2f} € je Baugruppe"
                            .replace(".", ","))

    geaendert = any(any(d.values()) for d in plus.values())
    if geaendert:
        alt = sum(z["preis_position"] for z in aktiv)
        for z in aktiv:
            z["preis_position"] = z["preis_teil"] * z["stueck"]
            z.update({f"{n}_teil": plus[id(z)][n] for n in FELDER})
            z.update({f"{n}_teil": plus[id(z)][n] for n in ZUSATZ_FELDER if plus[id(z)][n]})
        summen["verkauf"] = summen["verkauf"] + sum(z["preis_position"] for z in aktiv) - alt
        # Skonto der Bausteine in die Kostenart Skonto
        summen["skonto"] = sum(_n(z.get("skonto_teil")) * z["stueck"] for z in zeilen if z) + sum(
            sum(plus[id(z)].values()) / (1 - skonto) * skonto * z["stueck"] for z in aktiv)
    for n in FELDER:
        summen[n] = sum(plus[id(z)][n] * z["stueck"] for z in aktiv)
    for n in ZUSATZ_FELDER:
        w = sum(plus[id(z)][n] * z["stueck"] for z in aktiv)
        if w:
            summen[n] = w
    summen.update(info)

    # J1 Preisuntergrenze (ohne Skonto, netto): kurzfristig variable Kosten, langfristig Selbstkosten
    var = _n(einst.get("untergrenze_variabel")) if einst.get("untergrenze_variabel") not in (None, "") else 0.30
    kurz_g = lang_g = 0.0
    for z in aktiv:
        d = plus[id(z)]
        weg = d["verpackung"] + d["finanzierung"] + d["frachtfrei"]
        fracht = _n(z.get("fracht_teil")) + d["frachtfrei"]
        kurz = (_n(z.get("material_teil")) + _n(z.get("schrott_teil")) + _n(z.get("ausschuss_mat_teil"))
                + _n(z.get("schneidgas_teil")) + _n(z.get("laser_schneiden_teil")) * var + _n(z.get("zukauf_einstand_teil"))
                + _n(z.get("zusatz_fremd_teil")) + _n(z.get("bg_fremd_teil")) + fracht + d["verpackung"])
        lang = _n(z.get("selbst_teil")) + d["mannlos"] / ((1 + gew) or 1) + d["neuteil"] + _n(z.get("fracht_teil")) \
            + weg
        z.update(untergrenze_kurz_teil=kurz, untergrenze_lang_teil=lang)
        kurz_g += kurz * z["stueck"]
        lang_g += lang * z["stueck"]
    summen.update(untergrenze_kurz=kurz_g, untergrenze_lang=lang_g, untergrenze_variabel=100 * var)
    return summen


def _preis_hand(positionen, zeilen):
    """{Index der Baugruppen-Zeile: (Ziel je BG, berechneter Preis je BG inkl. Einzelteile, Selbstkosten je BG)} für
    Baugruppen mit Verkaufspreis von Hand (bg_vorgabe.preis_hand) bei ihrer Anzahl."""
    from . import baugruppe, bg_vorgabe
    from .angebot import ist_baugruppe
    out = {}
    for i, (p, z) in enumerate(zip(positionen, zeilen)):
        if not z or not z.get("stueck") or not ist_baugruppe(p):
            continue
        bg = baugruppe.lesen(p.get("baugruppe"))
        ziel = bg_vorgabe.preis_hand(bg, z["stueck"])
        if ziel is None:
            continue
        preis, selbst = z["preis_teil"], _n(z.get("selbst_teil"))
        for j in baugruppe.teile(positionen, bg["id"]):
            q = zeilen[j]
            if q and q.get("stueck"):
                je = _n(positionen[j].get("stueck")) / z["stueck"]
                preis += q["preis_teil"] * je
                selbst += _n(q.get("selbst_teil")) * je
        out[i] = (ziel, preis, selbst)
    return out


def untergrenze_text(summen):
    from .stammdaten import zahl_als_text as zahl
    return (f"Preisuntergrenze langfristig {zahl(summen.get('untergrenze_lang') or 0, 2)} € · kurzfristig "
            f"{zahl(summen.get('untergrenze_kurz') or 0, 2)} € netto")
