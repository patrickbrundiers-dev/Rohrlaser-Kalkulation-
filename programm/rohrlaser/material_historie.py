"""Preishistorie und Preisvorschläge je Material (Patrick 23.11.2026: „Tiefgründige Historie aufbauen und daraus auch
Materialpreis-Vorschläge generieren“). Ohne Qt.

Quellen je Material (Profil + Werkstoff), alle in €/m umgerechnet (materialplattform.preis_punkte):
- Stammdaten: Preisstände aus preisverlauf (Preise, Lieferlängen),
- ERP-Einkauf: Käufe aus der EK-CSV (erp_preise, mit Ausreißer-Kennung „zählt“),
- Lieferantenpreise der Materialplattform (material_lieferanten, mit Gültigkeit).

monate() fasst das je Kalendermonat zusammen, trend() rechnet die Preisentwicklung, vorschlag() leitet daraus einen
Preis ab und begründet ihn. Ein Vorschlag ändert nichts: übernommen wird er nur per Klick (uebernehmen(), mit
Admin-Schutz in der Oberfläche und Eintrag im KI-Protokoll über material_ki). Güte und technische Werte bleiben.
"""
import datetime
import statistics

from . import materialplattform as mp

HALBWERT_TAGE = 90          # Gewicht eines Kaufs halbiert sich alle 90 Tage (neuere Käufe zählen mehr)
ZEITRAUM_TAGE = 365         # Käufe für Vorschlag und Trend: die letzten 12 Monate
TREND_MAX = 0.10            # Trendkorrektur höchstens ±10 % des gewichteten Durchschnitts
MIN_ABWEICHUNG = 3.0        # Vorschlag nur, wenn er mehr als 3 % vom heutigen Preis abweicht (oder keiner da ist)
HOCH, MITTEL, NIEDRIG = "hoch", "mittel", "niedrig"


def _heute(heute):
    return heute or datetime.date.today()


def _monat(d):
    return f"{d.year:04d}-{d.month:02d}"


def _stamm_am(stamm, tag):
    out = None
    for d, p in stamm:
        if d <= tag:
            out = p
    return out


def monate(pp, heute=None):
    """Historie je Monat, neuester zuerst: [dict(monat 'JJJJ-MM', kaeufe, meter, schnitt (nach Menge gewichtet, nur
    Käufe, die zählen), min, max, stamm (Stammdatenpreis am Monatsende), abw (% Ø zu Stamm), lieferanten (Anzahl
    Lieferantenpreise ab dem Monat), ereignisse [Text])]. Von der ersten Angabe bis heute, Monate ohne Angaben
    zählen mit (Stammdatenpreis läuft weiter)."""
    heute = _heute(heute)
    stamm, erp, lief = pp.get("stamm") or [], pp.get("erp") or [], pp.get("lieferanten") or []
    daten = [d for d, _ in stamm] + [x["datum"] for x in erp] + [x["datum"] for x in lief]
    if not daten:
        return []
    j, m = min(daten).year, min(daten).month
    out = []
    while (j, m) <= (heute.year, heute.month):
        ende = (datetime.date(j + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1))
        key = f"{j:04d}-{m:02d}"
        ks = [x for x in erp if _monat(x["datum"]) == key]
        zaehlt = [x for x in ks if x["zaehlt"]]
        meter = sum(x["menge"] for x in zaehlt)
        schnitt = sum(x["menge"] * x["preis"] for x in zaehlt) / meter if meter else None
        st = _stamm_am(stamm, min(ende, heute))
        ereignisse = [f"Stammdaten {mp._zelle(p, 2)} €/m" for d, p in stamm if _monat(d) == key]
        ereignisse += [f"Lieferant {x['lieferant']} {mp._zelle(x['preis'], 2)} €/m" for x in lief
                       if _monat(x["datum"]) == key]
        ausr = len(ks) - len(zaehlt)
        if ausr:
            ereignisse.append(f"{ausr} Kauf/Käufe zählt nicht (Ausreißer/Hand)")
        out.append(dict(monat=key, kaeufe=len(ks), meter=sum(x["menge"] for x in ks), schnitt=schnitt,
                        min=min((x["preis"] for x in ks), default=None), max=max((x["preis"] for x in ks), default=None),
                        stamm=st, abw=(schnitt / st - 1) * 100 if schnitt and st else None, ereignisse=ereignisse))
        j, m = (j + 1, 1) if m == 12 else (j, m + 1)
    return list(reversed(out))


def _kaeufe(pp, heute, tage=ZEITRAUM_TAGE):
    ab = heute - datetime.timedelta(days=tage)
    return [x for x in pp.get("erp") or () if x["zaehlt"] and ab <= x["datum"] <= heute and x["preis"] > 0]


def trend(pp, heute=None):
    """Preisentwicklung der ERP-Käufe (letzte 12 Monate, nach Menge gewichtete Regressionsgerade): dict(steigung
    (€/m je 30 Tage), pct_jahr (% je Jahr bezogen auf den Ø), n, mittel_3/6/12 (nach Menge gewichteter Ø der letzten
    3/6/12 Monate)) oder None ohne Käufe. Steigung erst ab 3 Käufen über mindestens 60 Tage."""
    heute = _heute(heute)
    ks = _kaeufe(pp, heute)
    if not ks:
        return None
    out = dict(n=len(ks), steigung=None, pct_jahr=None)
    for mon in (3, 6, 12):
        ab = heute - datetime.timedelta(days=round(mon * 30.44))
        t = [x for x in ks if x["datum"] >= ab]
        m = sum(x["menge"] for x in t)
        out[f"mittel_{mon}"] = sum(x["menge"] * x["preis"] for x in t) / m if m else None
    tage = [(x["datum"] - heute).days for x in ks]
    if len(ks) >= 3 and max(tage) - min(tage) >= 60:
        w = [max(x["menge"], 0.001) for x in ks]
        sw = sum(w)
        mx = sum(wi * t for wi, t in zip(w, tage)) / sw
        my = sum(wi * x["preis"] for wi, x in zip(w, ks)) / sw
        var = sum(wi * (t - mx) ** 2 for wi, t in zip(w, tage))
        if var > 0:
            b = sum(wi * (t - mx) * (x["preis"] - my) for wi, t, x in zip(w, tage, ks)) / var      # €/m je Tag
            out.update(steigung=b * 30, pct_jahr=b * 365 / my * 100 if my else None)
    return out


def _gewichtet(ks, heute):
    """Nach Menge und Alter gewichteter Durchschnitt (Halbwertszeit HALBWERT_TAGE) und gewichteter Kaufzeitpunkt."""
    w = [x["menge"] * 0.5 ** ((heute - x["datum"]).days / HALBWERT_TAGE) for x in ks]
    sw = sum(w)
    if sw <= 0:
        return None, None
    return (sum(wi * x["preis"] for wi, x in zip(w, ks)) / sw,
            sum(wi * (heute - x["datum"]).days for wi, x in zip(w, ks)) / sw)


def sicherheit(ks, heute):
    """hoch: mind. 4 Käufe, letzter jünger als 90 Tage, Streuung unter 10 %; niedrig: 1 Kauf oder letzter älter als
    180 Tage oder Streuung über 25 %; sonst mittel."""
    preise = [x["preis"] for x in ks]
    cv = statistics.pstdev(preise) / statistics.mean(preise) if len(preise) > 1 else None
    alter = (heute - max(x["datum"] for x in ks)).days
    if len(ks) >= 4 and alter <= 90 and cv is not None and cv < 0.10:
        return HOCH
    if len(ks) == 1 or alter > 180 or (cv is not None and cv > 0.25):
        return NIEDRIG
    return MITTEL


def kg_referenz(zeilen, erp_gruppen):
    """€/kg aus dem ERP-Einkauf je (Werkstoff, Profilart): Median über die gekauften Abmessungen (Rohware). Für
    Materialien ohne eigene Käufe."""
    je = {}
    for z in zeilen:
        g = erp_gruppen.get((z["profil_id"], z["werkstoff_id"]))
        if g and not g.get("oberflaeche") and g.get("durchschnitt") and z.get("kgm"):
            je.setdefault((z["werkstoff_id"], z["form"]), []).append((g["durchschnitt"] / z["kgm"], z["profil_id"]))
    return {k: (statistics.median(p for p, _ in v), [pid for _, pid in v]) for k, v in je.items()}


def vorschlag(z, pp, heute=None, kg_ref=None):
    """Preisvorschlag €/m für ein Material aus seiner Historie oder None.

    1. Eigene ERP-Käufe der letzten 12 Monate (nur Rohware, ohne Ausreißer): nach Menge und Alter gewichteter Ø
       (Halbwertszeit 90 Tage), bei klarem Trend (ab 3 Käufen über 60 Tage) bis heute fortgeschrieben, höchstens
       ±10 %.
    2. Sonst der günstigste heute gültige Lieferantenpreis.
    3. Sonst €/kg der gleichen Profilart und des gleichen Werkstoffs aus dem ERP-Einkauf × kg/m (Sicherheit niedrig).
    Ergebnis dict(preis_m, preis_kg, quelle, sicherheit, begruendung, abw (% zum heutigen Preis), kaeufe) – nur wenn
    der Vorschlag mehr als MIN_ABWEICHUNG % vom heutigen Preis abweicht oder es nur den Tonnenpreis/keinen gibt."""
    heute = _heute(heute)
    kgm = z.get("kgm")
    jetzt = z.get("preis_m") if z.get("quelle") in (mp.QUELLE_PREISE, mp.QUELLE_LIEFERLAENGE) else None
    roh = not (pp.get("erp") and pp["erp"][0].get("ober"))
    ks = _kaeufe(pp, heute) if roh else []
    preis, quelle, sich, gruende = None, None, None, []
    if ks:
        basis, alter = _gewichtet(ks, heute)
        tr = trend(pp, heute)
        preis = basis
        gruende.append(f"{len(ks)} ERP-Käufe der letzten 12 Monate ({mp._zelle(sum(x['menge'] for x in ks), 0)} m), "
                       f"nach Menge und Alter gewichtet {mp._zelle(basis, 2)} €/m")
        if tr and tr.get("steigung") is not None and alter:
            korr = max(-TREND_MAX * basis, min(TREND_MAX * basis, tr["steigung"] / 30 * alter))
            if abs(korr) >= 0.005:
                preis = basis + korr
                gruende.append(f"Trend {mp._zelle(tr['pct_jahr'], 1)} % je Jahr, bis heute fortgeschrieben "
                               f"{'+' if korr > 0 else ''}{mp._zelle(korr, 2)} €/m")
        quelle, sich = "ERP-Einkauf", sicherheit(ks, heute)
    if preis is None:
        gueltig = [x for x in pp.get("lieferanten") or () if x["datum"] <= heute]
        lief_z = [x for x in gueltig if x.get("gueltig", True)]
        if lief_z:
            best = min(lief_z, key=lambda x: x["preis"])
            preis, quelle, sich = best["preis"], f"Lieferant {best['lieferant']}", MITTEL
            gruende.append(f"günstigster gültiger Lieferantenpreis {best['lieferant']} ({mp._zelle(best['preis'], 2)} "
                           f"€/m, ab {best['datum'].strftime('%d.%m.%Y')})")
    if preis is None and kg_ref and kgm:
        ref = kg_ref.get((z["werkstoff_id"], z["form"]))
        if ref and z["profil_id"] not in ref[1]:
            preis, quelle, sich = ref[0] * kgm, "ERP-Einkauf ähnlicher Abmessungen", NIEDRIG
            gruende.append(f"{mp._zelle(ref[0], 2)} €/kg (Median aus {len(ref[1])} gekauften {z['form']} "
                           f"{z['werkstoff_id']}: {', '.join(ref[1][:4])}{' …' if len(ref[1]) > 4 else ''}) × "
                           f"{mp._zelle(kgm, 3)} kg/m")
    if preis is None:
        return None
    preis = round(preis, 2)
    abw = (preis / jetzt - 1) * 100 if jetzt else None
    if abw is not None and abs(abw) <= MIN_ABWEICHUNG:
        return None
    gruende.append(f"heute {mp._zelle(jetzt, 2)} €/m ({z['quelle']})" if jetzt else
                   f"heute nur {z['quelle']}" + (f" {mp._zelle(z['preis_m'], 2)} €/m" if z.get("preis_m") else ""))
    return dict(preis_m=preis, preis_kg=round(preis / kgm, 4) if kgm else None, quelle=quelle, sicherheit=sich,
                begruendung="; ".join(gruende), abw=abw, kaeufe=len(ks))


def uebernehmen(db, profil_id, werkstoff_id, preis_m, quelle="", heute=None):
    """Vorschlag als aktiven Preis in 'Preise' schreiben: vorhandene Zeile in ihrer Preisbasis (€/kg über kg/m,
    €/Stange über die Lieferlänge) mit Gültig ab heute und Bemerkung, sonst neue Zeile in €/m. Lieferant und
    Mindestabnahme bleiben. Ergebnis: Text für die Meldung. Offene Angebote meldet der Preiswächter."""
    heute = _heute(heute).isoformat()
    k = db.kontext()
    kgm = mp.kg_je_m(k.profile.get(profil_id) or {}, k.werkstoffe.get(werkstoff_id) or {})
    zeile = next((p for p in db.zeilen("preise") if mp.schluessel(p) == (profil_id, werkstoff_id)), None)
    bem = f"Vorschlag aus der Preishistorie ({quelle}), übernommen {heute[8:10]}.{heute[5:7]}.{heute[:4]}"
    if zeile is None:
        db.neu("preise", dict(profil_id=profil_id, werkstoff_id=werkstoff_id, basis="€/m", preis=round(preis_m, 2),
                              gueltig_ab=heute, bemerkung=bem))
        return f"{profil_id} · {werkstoff_id}: neuer Preis {mp._zelle(preis_m, 2)} €/m"
    basis = zeile.get("basis") or "€/kg"
    if basis == "€/kg":
        if not kgm:
            raise ValueError("Ohne kg/m lässt sich der Vorschlag nicht in €/kg umrechnen.")
        wert = round(preis_m / kgm, 4)
    elif basis == "€/Stange":
        lg = mp._n(zeile.get("lieferlaenge")) or 6000.0
        wert = round(preis_m * lg / 1000, 2)
    else:
        wert = round(preis_m, 2)
    for f, v in (("preis", wert), ("gueltig_ab", heute), ("bemerkung", bem)):
        db.aendern("preise", zeile["id"], f, v)
    return f"{profil_id} · {werkstoff_id}: Preis {mp._zelle(wert, 4 if basis == '€/kg' else 2)} {basis}"


def alle_vorschlaege(db, zeilen, erp_gruppen=None, heute=None):
    """{(profil, werkstoff): Vorschlag} für alle Materialien mit Historie (ERP-Käufe, Lieferantenpreise) und für
    verwendete Materialien ohne eigenen Preis (über €/kg ähnlicher Abmessungen)."""
    erp_gruppen = mp.erp_gruppen(db) if erp_gruppen is None else erp_gruppen
    kg_ref = kg_referenz(zeilen, erp_gruppen)
    lief = {mp.schluessel(z) for z in db.zeilen(mp.LIEFERANTEN_TABELLE)}
    out = {}
    for z in zeilen:
        schl = (z["profil_id"], z["werkstoff_id"])
        ohne = z.get("quelle") in (mp.QUELLE_TONNE, mp.QUELLE_FEHLT) and z.get("nutzung")
        if schl not in erp_gruppen and schl not in lief and not ohne:
            continue
        if z.get("archiviert"):
            continue
        pp = mp.preis_punkte(db, z["profil_id"], z["werkstoff_id"], gruppe=erp_gruppen.get(schl) or {})
        v = vorschlag(z, pp, heute, kg_ref)
        if v:
            out[schl] = v
    return out
