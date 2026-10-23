"""Nachkalkulation: tatsächliche Werte nach dem Auftrag gegen die Kalkulation des Angebots (Soll).

Verglichen werden die Einzelkosten ohne Zuschläge und Gewinn, weil nur sie sich in der Fertigung messen lassen:
- Material: Ist-Stangen je Gruppe (Profil + Werkstoff + Stangenlänge) × Kosten je Stange; die Kosten je Stange
  kommen aus dem Ist-EK-Meterpreis × Stangenlänge, leer = kalkulierter Meterpreis laut Schnittplan
- Laserzeit [h] × Stundensatz der Maschine (Soll = Laserzeit netto aller Teile, Zusatzzeiten eingeschlossen)
- Rüsten + Stangenwechsel [min] × Stundensatz (Soll = Rüstzeit je Angebot + je Abmessung + Stangenwechsel)
- Gewinde und Zusatzarbeiten [€] (Soll = Gewinde + Zusatzarbeiten der Kalkulation, Ist z. B. laut Rechnung)
- Sonstige Kosten [€] (Soll 0, z. B. Nacharbeit)
Erlös: Ist laut Rechnung, leer = Verkaufspreis des Angebots. Deckungsbeitrag = Erlös − Einzelkosten.
Nicht erfasste Ist-Werte (leer) zählen wie das Soll und sind in der Spalte 'erfasst' als 'nein' markiert.

Schweißbaugruppen (nur, wenn das Angebot welche hat; sonst bleibt alles wie bisher): je Baugruppe
- Schweißen [h] (Soll = Schweißzeit der Nahtgruppen × Anzahl Baugruppen), Ist mit dem Satz des Solls bewertet
- Arbeitsgänge [h] (laufende Zeit + Rüstzeit, eigene Arbeitsgänge), Ist mit dem Satz des Solls bewertet
- Material und Einmalbeträge [€] (Kosten je Einheit, Vorrichtungen, Lehren der eigenen Arbeitsgänge)
- Fremdleistungen [€]
dazu der Abweichungsgrund (Text) und als Hinweis für die Kennwerte die Schweißzeit je Meter Naht Soll/Ist. Die Ist-
Werte ändern weder die Kalkulation noch die Stammdaten (Kennwerte nur von Hand nach Prüfung anpassen).

ist (gespeichert je Angebot): {stangen: {Gruppenschlüssel: Anzahl}, meterpreis: {Gruppenschlüssel: €/m}, laser_h, ruest_min, zusatz, zukauf, sonstiges, erloes,
bemerkung, am, baugruppen: {Baugruppen-ID: {schweiss_h, arbeit_h, material, fremd, grund}}};
Gruppenschlüssel = 'Profil|Werkstoff|Stangenlänge'.
"""
from . import rechnen

FELDER = (  # (Name, Titel, Nachkommastellen)
    ("laser_h", "Laserzeit Ist [h]", 2),
    ("ruest_min", "Rüsten + Stangenwechsel Ist [min]", 0),
    ("zusatz", "Gewinde und Zusatzarbeiten Ist [€]", 2),
    ("zukauf", "Zukaufteile Ist (Einkauf + Bezugskosten) [€]", 2),
    ("sonstiges", "Sonstige Kosten Ist [€]", 2),
    ("erloes", "Erlös laut Rechnung [€]", 2),
)


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def gruppenschluessel(profil, werkstoff, stange, oberflaeche=""):
    """'Profil|Werkstoff|Stangenlänge', mit Oberfläche (nicht roh) '…|Oberfläche' dahinter."""
    return (f"{profil}|{werkstoff}|{int(stange) if float(stange).is_integer() else stange}"
            + (f"|{oberflaeche}" if oberflaeche else ""))


def gruppen(ergebnis, kopf, positionen, k, tabellen):
    """Stangengruppen des Schnittplans: [{schluessel, profil, werkstoff, stange, soll, kosten_stange}]."""
    if not ergebnis or not ergebnis.get("stangen"):
        return []
    sw = rechnen.stangen_werte(ergebnis, kopf, positionen, k, tabellen)
    out = {}
    for s, w in zip(ergebnis["stangen"], sw):
        ob = s.get("oberflaeche") or ""
        g = out.setdefault(rechnen.gruppe_der_stange(s),
                           dict(schluessel=gruppenschluessel(s["profil"], s["werkstoff"], s["stange"], ob)
                                + ("|Kunde" if s.get("beistellung") else ""),
                                profil=s["profil"], werkstoff=rechnen.material_text(s["werkstoff"], ob)
                                + (" – Kundenmaterial" if s.get("beistellung") else ""),
                                stange=s["stange"], soll=0, kosten=0.0))
        g["soll"] += 1
        g["kosten"] += w["kosten"] or 0
    for g in out.values():
        g["kosten_stange"] = g["kosten"] / g["soll"]
        g["meterpreis"] = g["kosten_stange"] * 1000 / g["stange"] if g["stange"] else None
    return list(out.values())


def vergleich(kopf, positionen, ergebnis, k, tabellen, einst, ist, kalk=None):
    """Soll/Ist je Kostenart. Ergebnis: dict(gruppen=[… mit ist, soll_kosten, ist_kosten], zeilen=[{text, einheit,
    soll_menge, ist_menge, soll, ist, abweichung, prozent, erfasst}], summe=…, erloes=…, db=…, satz=Stundensatz)."""
    ist = ist or {}
    zeilen_k, summen = kalk or rechnen.kalkulation(kopf, positionen, ergebnis, k, tabellen, einst)
    satz = summen["satz_laser"]       # Stundensatz des Laserschneidens (Vorgabe: Maschine; Snapshot des Angebots)
    gr = gruppen(ergebnis, kopf, positionen, k, tabellen)
    ist_st, ist_mp = ist.get("stangen") or {}, ist.get("meterpreis") or {}
    for g in gr:
        n = _n(ist_st.get(g["schluessel"]))
        mp = _n(ist_mp.get(g["schluessel"]))
        g["ist"], g["meterpreis_ist"] = n, mp
        g["kosten_stange_ist"] = mp * g["stange"] / 1000 if mp is not None else g["kosten_stange"]
        g["soll_kosten"] = g["kosten"]
        g["ist_kosten"] = (n if n is not None else g["soll"]) * g["kosten_stange_ist"]
    laser_h = sum((z["laser_netto"] or 0) * z["stueck"] for z in zeilen_k if z) / 3600
    ruest_min = summen["ruestzeit"] + summen["abmessungen"] * summen["ruestzeit_abmessung"] \
        + summen.get("stangenwechsel_s", summen.get("beladungen", summen["stangen"]) * summen["stangenwechsel"]) / 60

    def zeile(text, einheit, soll_menge, ist_menge, soll, ist_betrag, erfasst):
        abw = ist_betrag - soll
        return dict(text=text, einheit=einheit, soll_menge=soll_menge, ist_menge=ist_menge, soll=soll, ist=ist_betrag,
                    abweichung=abw, prozent=100 * abw / soll if soll else None, erfasst="ja" if erfasst else "nein")
    stangen_ist = sum(g["ist"] if g["ist"] is not None else g["soll"] for g in gr)
    zeilen = [zeile("Material", "Stangen", summen["stangen"], stangen_ist, summen["material"],
                    sum(g["ist_kosten"] for g in gr) if gr else summen["material"],
                    bool(gr) and all(g["ist"] is not None for g in gr))]
    for name, text, einheit, soll_menge, soll, faktor in (
            ("laser_h", "Laserzeit", "h", laser_h, summen["laser_schneiden"], satz),
            ("ruest_min", "Rüsten + Stangenwechsel", "min", ruest_min,
             summen["ruesten_maschine"] + summen["ruesten_abmessungen"] + summen["stangenwechsel_kosten"],
             # Ist-Minuten mit dem mittleren Satz des Solls bewerten (Rüsten und Stangenwechsel können
             # verschiedene Stundensätze haben)
             (summen["ruesten_maschine"] + summen["ruesten_abmessungen"] + summen["stangenwechsel_kosten"]) / ruest_min
             if ruest_min else satz / 60)):
        m = _n(ist.get(name))
        zeilen.append(zeile(text, einheit, soll_menge, m if m is not None else soll_menge, soll,
                            m * faktor if m is not None else soll, m is not None))
    for name, text, soll in (("zusatz", "Gewinde und Zusatzarbeiten", summen["gewinde"] + summen["zusatz"]),
                             ("zukauf", "Zukaufteile (Einstand)", summen.get("zukauf_einstand", 0.0)),
                             ("sonstiges", "Sonstige Kosten", 0.0)):
        b = _n(ist.get(name))
        zeilen.append(zeile(text, "€", None, None, soll, b if b is not None else soll, b is not None))
    bg_soll = baugruppen_soll(positionen, zeilen_k)
    bg_zeilen, bg_info = _baugruppen_zeilen(bg_soll, ist, zeile)
    zeilen += bg_zeilen
    summe = zeile("Einzelkosten", "€", None, None, sum(z["soll"] for z in zeilen), sum(z["ist"] for z in zeilen),
                  all(z["erfasst"] == "ja" for z in zeilen))
    e = _n(ist.get("erloes"))
    erloes = zeile("Erlös", "€", None, None, summen["verkauf"], e if e is not None else summen["verkauf"], e is not None)
    db = zeile("Deckungsbeitrag (Erlös − Einzelkosten)", "€", None, None, erloes["soll"] - summe["soll"],
               erloes["ist"] - summe["ist"], summe["erfasst"] == "ja" and e is not None)
    return dict(gruppen=gr, zeilen=zeilen, summe=summe, erloes=erloes, db=db, satz=satz, verkauf=summen["verkauf"],
                herstell=summen["herstell"], baugruppen=bg_info)


BG_FELDER = (  # (Name, Titel, Einheit, Nachkommastellen)
    ("schweiss_h", "Schweißen", "h", 2),
    ("arbeit_h", "Arbeitsgänge", "h", 2),
    ("material", "Material und Einmalbeträge", "€", 2),
    ("fremd", "Fremdleistungen", "€", 2),
)


def baugruppen_soll(positionen, kalk_zeilen):
    """Soll je Schweißbaugruppe aus der Kalkulation: [{id, name, anzahl, naht_m, werte {Feld: (Menge, €)}}]; Menge
    in h bzw. None bei €-Feldern."""
    from . import baugruppe
    out = []
    for p, z in zip(positionen, kalk_zeilen):
        if not z or not z.get("baugruppe"):
            continue
        bg = baugruppe.lesen(p.get("baugruppe")) or {}
        c = z.get("stueck") or 0
        w = {n: [0.0, 0.0] for n, *_ in BG_FELDER}
        for x in z.get("bg_zeilen") or ():
            r = x.get("werte") or {}
            if x["art"] == "Naht":
                w["schweiss_h"][0] += x["zeit_min"] * c / 60
                w["schweiss_h"][1] += x["kosten"] * c
                continue
            satz = r.get("satz") if isinstance(r.get("satz"), (int, float)) else 0
            u = r.get("umlage_faktor") or 0
            zeit_eur = (r.get("laufend_min") or 0) / 60 * satz * x["faktor"] * c + (r.get("einmal_min") or 0) / 60 * satz * u
            gesamt = x["kosten"] * c + x["einmal"]
            if x["fremd"]:
                w["fremd"][1] += gesamt
            else:
                w["arbeit_h"][0] += (r.get("laufend_min") or 0) * x["faktor"] * c / 60 + (r.get("einmal_min") or 0) * u / 60
                w["arbeit_h"][1] += zeit_eur
                w["material"][1] += gesamt - zeit_eur
        out.append(dict(id=bg.get("id"), name=baugruppe.name(p, bg), anzahl=c,
                        naht_m=sum((z.get("bg_naht_m") or {}).values()) * c,
                        werte={n: (w[n][0] if e == "h" else None, w[n][1]) for n, _, e, _ in BG_FELDER}))
    return out


def _baugruppen_zeilen(soll, ist, zeile):
    """Vergleichszeilen und Kennwert-Hinweise der Schweißbaugruppen."""
    zeilen, info = [], []
    ist_bg = (ist or {}).get("baugruppen") or {}
    for b in soll:
        e = ist_bg.get(b["id"]) or {}
        for n, titel, einheit, _ in BG_FELDER:
            menge, betrag = b["werte"][n]
            m = _n(e.get(n))
            if einheit == "h":
                satz = betrag / menge if menge else None
                ist_betrag = betrag if m is None else (m * satz if satz is not None else betrag)
                zeilen.append(zeile(f"{b['name']}: {titel}", "h", menge, m if m is not None else menge, betrag,
                                    ist_betrag, m is not None and (satz is not None or not m)))
            else:
                zeilen.append(zeile(f"{b['name']}: {titel}", "€", None, None, betrag, m if m is not None else betrag,
                                    m is not None))
            zeilen[-1].update(bg_id=b["id"], bg_feld=n)       # eindeutig, auch bei gleichen Namen (rest_wie_geplant)
        sm, ih = b["werte"]["schweiss_h"][0], _n(e.get("schweiss_h"))
        info.append(dict(id=b["id"], name=b["name"], naht_m=b["naht_m"],
                         soll_min_m=sm * 60 / b["naht_m"] if b["naht_m"] else None,
                         ist_min_m=ih * 60 / b["naht_m"] if b["naht_m"] and ih is not None else None,
                         grund=e.get("grund") or ""))
    return zeilen, info


ABWEICHUNG_GRENZE = 0.10   # ab 10 % Abweichung Ist gegen Soll farbig (Reiter Nachkalkulation, Baugruppen)


def bewertung(soll, ist, grenze=ABWEICHUNG_GRENZE):
    """'hoch' (Ist mindestens grenze über Soll), 'niedrig' (darunter) oder None (im Rahmen bzw. kein Vergleich)."""
    if _n(soll) is None or _n(ist) is None or soll <= 0:
        return None
    a = (ist - soll) / soll
    return "hoch" if a >= grenze - 1e-9 else "niedrig" if a <= -grenze + 1e-9 else None


def rest_wie_geplant(v, ist):
    """Plan Arbeitsabläufe W9: alle noch leeren Ist-Werte auf das Soll setzen (Stangen je Gruppe, Laserzeit, Rüsten,
    Zusatzarbeiten, Zukauf, Sonstiges 0, Erlös = Verkaufspreis, Baugruppen); eingetragene Werte bleiben, die
    Meterpreise bleiben leer (= kalkuliert). v = vergleich(...) mit diesem ist. Ergebnis: (neues ist, Anzahl)."""
    ist = dict(ist or {})
    n = 0

    def setzen(d, name, wert):
        nonlocal n
        if _n(d.get(name)) is None and wert is not None:
            d[name] = wert
            n += 1
    stangen = dict(ist.get("stangen") or {})
    for g in v["gruppen"]:
        setzen(stangen, g["schluessel"], g["soll"])
    if stangen:
        ist["stangen"] = stangen
    z = {x["text"]: x for x in v["zeilen"]}
    setzen(ist, "laser_h", z["Laserzeit"]["soll_menge"])
    setzen(ist, "ruest_min", z["Rüsten + Stangenwechsel"]["soll_menge"])
    setzen(ist, "zusatz", z["Gewinde und Zusatzarbeiten"]["soll"])
    setzen(ist, "zukauf", z["Zukaufteile (Einstand)"]["soll"])
    setzen(ist, "sonstiges", 0.0)
    setzen(ist, "erloes", v["erloes"]["soll"])
    einheiten = {name: einheit for name, _, einheit, _ in BG_FELDER}
    bg_zeilen = [x for x in v["zeilen"] if x.get("bg_id") is not None]
    if bg_zeilen:
        bg = {k: dict(e) for k, e in (ist.get("baugruppen") or {}).items()}
        for x in bg_zeilen:
            setzen(bg.setdefault(x["bg_id"], {}), x["bg_feld"],
                   x["soll_menge"] if einheiten[x["bg_feld"]] == "h" else x["soll"])
        ist["baugruppen"] = bg
    return ist, n


def erfasst(ist):
    """True, wenn mindestens ein Ist-Wert eingetragen ist."""
    ist = ist or {}
    return any(_n(ist.get(n)) is not None for n, _, _ in FELDER) or \
        any(_n(v) is not None for n in ("stangen", "meterpreis") for v in (ist.get(n) or {}).values()) or \
        any(_n(e.get(n)) is not None or e.get("grund") for e in (ist.get("baugruppen") or {}).values()
            for n in [x[0] for x in BG_FELDER] + ["grund"])
