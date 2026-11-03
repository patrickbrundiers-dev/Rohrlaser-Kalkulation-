"""Letzte Preisschicht der Kalkulation (Vorschläge vom 02.11.2026: G2 Verpackung, G3 Finanzierung, G6 Runden,
G7 Kundenkonditionen, J1 Preisuntergrenze, J3 mannlose Laufzeit, J6 Neuteil-Zuschlag).

rechnen.kalkulation ruft anwenden() nach der eigentlichen Rechnung auf. Jeder Baustein ist ohne Einstellung bzw.
Angebotswert aus (0 oder leer); dann bleibt jeder Preis bitgleich wie bisher. Reihenfolge:
  1. J3 mannlose Laufzeit: Laserstunden eines Laufs über „Mannlos: ab Laufzeit je Los“ der Maschine mit dem
     kleineren Stundensatz „Mannlos: Stundensatz“ (Unterschied mit Zuschlag Fertigung und Gewinn).
  2. J6 Neuteil-Zuschlag (Einstellung neuteil_zuschlag) auf Material und Laser der Positionen, die im Angebot als
     Neuteil vermerkt sind (Angebotsfenster: kein beauftragtes Wiederholteil), ohne Gewinn.
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

FELDER = ("mannlos", "neuteil", "verpackung", "finanzierung", "frachtfrei", "rabatt", "rundung")


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


def packmittel(verpackung, gewicht, laenge):
    """Billigstes Packmittel der Stammdaten, in das das längste Teil passt: (Zeile, Anzahl) oder None. Anzahl =
    Gewicht ÷ max. Gewicht aufgerundet, mindestens 1."""
    beste = None
    for z in verpackung or ():
        if str(z.get("aktiv") or "ja") == "nein" or not _n(z.get("preis")):
            continue
        if _n(z.get("max_laenge")) and laenge > _n(z["max_laenge"]) + 1e-6:
            continue
        n = max(1, math.ceil(gewicht / _n(z["max_kg"]) - 1e-9)) if _n(z.get("max_kg")) else 1
        kosten = n * _n(z["preis"])
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
    plus = {id(z): dict.fromkeys(FELDER, 0.0) for z in aktiv}
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

    # 3. G2 Verpackung
    verpackung = (tabellen or {}).get("verpackung") or ()
    if verpackung and kopf.get("verpackung") != "nein":
        werte = {id(z): rechnen.position_werte(p, kopf, k, tabellen) for p, z in zip(positionen, zeilen)
                 if z and z.get("stueck")}
        gewichte = {i: _n((w or {}).get("gewicht")) * next(z["stueck"] for z in aktiv if id(z) == i)
                    for i, w in werte.items()}
        laenge = max((_n(p.get("laenge")) for p, z in zip(positionen, zeilen) if z and z.get("stueck")), default=0.0)
        wahl = packmittel(verpackung, sum(gewichte.values()), laenge)
        if wahl:
            zeile, n = wahl
            betrag = n * _n(zeile["preis"])
            for i, w in _verteilen(aktiv, betrag, gewichte if sum(gewichte.values()) else
                                   {id(z): z["stueck"] for z in aktiv}).items():
                plus[i]["verpackung"] = w
            info.update(verpackung_text=f"{n} × {zeile.get('name') or 'Packmittel'}", verpackung_anzahl=n)

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

    geaendert = any(any(d.values()) for d in plus.values())
    if geaendert:
        alt = sum(z["preis_position"] for z in aktiv)
        for z in aktiv:
            z["preis_position"] = z["preis_teil"] * z["stueck"]
            z.update({f"{n}_teil": plus[id(z)][n] for n in FELDER})
        summen["verkauf"] = summen["verkauf"] + sum(z["preis_position"] for z in aktiv) - alt
        # Skonto der Bausteine in die Kostenart Skonto
        summen["skonto"] = sum(_n(z.get("skonto_teil")) * z["stueck"] for z in zeilen if z) + sum(
            sum(plus[id(z)].values()) / (1 - skonto) * skonto * z["stueck"] for z in aktiv)
    for n in FELDER:
        summen[n] = sum(plus[id(z)][n] * z["stueck"] for z in aktiv)
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


def untergrenze_text(summen):
    from .stammdaten import zahl_als_text as zahl
    return (f"Preisuntergrenze langfristig {zahl(summen.get('untergrenze_lang') or 0, 2)} € · kurzfristig "
            f"{zahl(summen.get('untergrenze_kurz') or 0, 2)} € netto")
