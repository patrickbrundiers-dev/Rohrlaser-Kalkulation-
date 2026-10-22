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

ist (gespeichert je Angebot): {stangen: {Gruppenschlüssel: Anzahl}, meterpreis: {Gruppenschlüssel: €/m}, laser_h, ruest_min, zusatz, zukauf, sonstiges, erloes,
bemerkung, am}; Gruppenschlüssel = 'Profil|Werkstoff|Stangenlänge'.
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


def vergleich(kopf, positionen, ergebnis, k, tabellen, einst, ist):
    """Soll/Ist je Kostenart. Ergebnis: dict(gruppen=[… mit ist, soll_kosten, ist_kosten], zeilen=[{text, einheit,
    soll_menge, ist_menge, soll, ist, abweichung, prozent, erfasst}], summe=…, erloes=…, db=…, satz=Stundensatz)."""
    ist = ist or {}
    zeilen_k, summen = rechnen.kalkulation(kopf, positionen, ergebnis, k, tabellen, einst)
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
    summe = zeile("Einzelkosten", "€", None, None, sum(z["soll"] for z in zeilen), sum(z["ist"] for z in zeilen),
                  all(z["erfasst"] == "ja" for z in zeilen))
    e = _n(ist.get("erloes"))
    erloes = zeile("Erlös", "€", None, None, summen["verkauf"], e if e is not None else summen["verkauf"], e is not None)
    db = zeile("Deckungsbeitrag (Erlös − Einzelkosten)", "€", None, None, erloes["soll"] - summe["soll"],
               erloes["ist"] - summe["ist"], summe["erfasst"] == "ja" and e is not None)
    return dict(gruppen=gr, zeilen=zeilen, summe=summe, erloes=erloes, db=db, satz=satz, verkauf=summen["verkauf"],
                herstell=summen["herstell"])


def erfasst(ist):
    """True, wenn mindestens ein Ist-Wert eingetragen ist."""
    ist = ist or {}
    return any(_n(ist.get(n)) is not None for n, _, _ in FELDER) or \
        any(_n(v) is not None for n in ("stangen", "meterpreis") for v in (ist.get(n) or {}).values())
