"""Preis-Plausibilität im Angebots-Check (Plan „Kalkulation und Berechnung verbessern“ C3, Patrick 29.10.2026).

Fängt Tippfehler bei Stückzahl, Länge oder Preis vor dem Versand ab, ohne einen Preis zu ändern:
1. Stückpreis unter den Materialkosten des Teils (WARNUNG): fast immer ein Eingabefehler.
2. Preis je kg einer Position weicht stark vom Preis je kg derselben Abmessung (Profil + Werkstoff) in früher
   verschickten Angeboten ab (HINWEIS, Median der letzten VERGLEICH_MAX Werte; mehr als FAKTOR-mal teurer oder
   billiger). Die Werte je Position merkt sich das Programm beim Angebots-PDF im Versandverlauf (kennwerte).
2b. Feiner (Plan „Mehr Intelligenz“ I1, Patrick 08.11.2026): gibt es mindestens FEIN_MIN frühere Teile derselben
   Abmessung mit ähnlicher Länge (Faktor LAENGE_BAND), meldet der Check schon ab FEIN_FAKTOR Abweichung, mit Prozent
   und Anzahl („62 % teurer als 8 frühere Teile ähnlicher Länge“). Die Länge merkt sich das Programm seit 0.9.276 mit.
3. Ertrag je Laserstunde: der Verkaufspreis ohne Material, Zukaufteile und Fracht deckt die Laserzeit zum
   Stundensatz nicht (HINWEIS).
"""
import statistics

from . import rechnen

FAKTOR = 3.0            # so viel teurer bzw. billiger je kg als der Median früherer Angebote
VERGLEICH_MIN = 2       # so viele frühere Werte braucht der Vergleich mindestens
VERGLEICH_MAX = 20      # die letzten so vielen Werte je Abmessung
FEIN_FAKTOR = 1.5       # I1: Teile ähnlicher Länge, so viel teurer bzw. billiger je kg
FEIN_MIN = 5            # I1: so viele frühere Teile ähnlicher Länge mindestens
FEIN_MAX = 60           # I1: die letzten so vielen Werte je Abmessung
LAENGE_BAND = 1.5       # I1: ähnliche Länge = höchstens 1,5-mal länger bzw. kürzer


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _laserteil(p, z):
    return z and not z.get("zukaufteil") and not z.get("baugruppe") and z.get("muster") != "ja" and _n(z.get("stueck"))


def kennwerte(positionen, zeilen, k):
    """Preis je kg je Rohrlaserteil für den Versandverlauf: [{profil_id, werkstoff_id, kg, preis_teil, eur_kg}]
    (ohne Musterteile, Zukaufteile, Baugruppen und Teile ohne Gewicht)."""
    out = []
    for p, z in zip(positionen, zeilen):
        if not _laserteil(p, z):
            continue
        kgm = rechnen.kg_je_m(p.get("profil_id"), p.get("werkstoff_id"), k)
        kg = kgm * _n(p.get("laenge")) / 1000 if kgm else 0.0
        if kg > 0 and _n(z.get("preis_teil")) > 0:
            out.append(dict(profil_id=p.get("profil_id"), werkstoff_id=p.get("werkstoff_id"), kg=round(kg, 4),
                            preis_teil=round(z["preis_teil"], 4), eur_kg=round(z["preis_teil"] / kg, 4),
                            laenge=round(_n(p.get("laenge")), 1)))
    return out


def vergleich_aus(verlaeufe):
    """{(profil_id, werkstoff_id): [€/kg, neueste zuerst]} aus Versandverläufen [[Eintrag]] (je Angebot ein Verlauf,
    neueste Angebote zuerst)."""
    out = {}
    for verlauf in verlaeufe:
        for e in reversed(verlauf or ()):
            for w in (e or {}).get("kennwerte") or ():
                schl = (w.get("profil_id"), w.get("werkstoff_id"))
                if _n(w.get("eur_kg")) > 0 and len(out.setdefault(schl, [])) < VERGLEICH_MAX:
                    out[schl].append(w["eur_kg"])
            if (e or {}).get("kennwerte"):
                break               # je Angebot nur der letzte Versand
    return out


def fein_aus(verlaeufe):
    """I1: {(profil_id, werkstoff_id): [(Länge, €/kg), neueste zuerst]} aus Versandverläufen (nur Einträge mit
    Länge, je Angebot der letzte Versand)."""
    out = {}
    for verlauf in verlaeufe:
        for e in reversed(verlauf or ()):
            for w in (e or {}).get("kennwerte") or ():
                schl = (w.get("profil_id"), w.get("werkstoff_id"))
                if _n(w.get("eur_kg")) > 0 and _n(w.get("laenge")) > 0 and len(out.setdefault(schl, [])) < FEIN_MAX:
                    out[schl].append((w["laenge"], w["eur_kg"]))
            if (e or {}).get("kennwerte"):
                break
    return out


def _fein(w, fein):
    """(Abweichung als Faktor, Median €/kg, Anzahl) gegen frühere Teile ähnlicher Länge oder None."""
    if not fein or _n(w.get("laenge")) <= 0:
        return None
    alt = [e for la, e in fein.get((w["profil_id"], w["werkstoff_id"])) or ()
           if 1 / LAENGE_BAND <= la / w["laenge"] <= LAENGE_BAND]
    if len(alt) < FEIN_MIN:
        return None
    median = statistics.median(alt)
    return (w["eur_kg"] / median, median, len(alt)) if median > 0 else None


def punkte(positionen, zeilen, summen, k, vergleich=None, fein=None):
    """[(Art, Text, Zeilenindex oder None)] der Plausibilitätsprüfung; Art 'WARNUNG' oder 'HINWEIS'. fein: frühere
    Teile mit Länge (fein_aus, I1)."""
    from .stammdaten import zahl_als_text as zahl
    out = []
    skonto = _n(summen.get("skonto_satz")) / 100
    unter = [i for i, (p, z) in enumerate(zip(positionen, zeilen))
             if _laserteil(p, z) and not z.get("kundenmaterial") and _n(z.get("material_teil")) > 0
             and _n(z.get("preis_teil")) * (1 - skonto) < _n(z.get("material_teil")) - 1e-9]
    if unter:
        z = zeilen[unter[0]]
        out.append(("WARNUNG", f"Preis unter den Materialkosten (z. B. Pos. {z.get('pos')}: "
                               f"{zahl(z['preis_teil'], 2)} € je Teil, Material {zahl(z['material_teil'], 2)} €)",
                    unter[0]))
    if vergleich or fein:
        for w in kennwerte(positionen, zeilen, k):

            def zeile_i():
                return next(j for j, (p, z) in enumerate(zip(positionen, zeilen)) if _laserteil(p, z)
                            and p.get("profil_id") == w["profil_id"] and p.get("werkstoff_id") == w["werkstoff_id"]
                            and round(z["preis_teil"], 4) == w["preis_teil"])
            f = _fein(w, fein)
            if f and not 1 / FEIN_FAKTOR <= f[0] <= FEIN_FAKTOR:
                i = zeile_i()
                wie = (f"{zahl(100 * (f[0] - 1), 0)} % teurer" if f[0] > 1 else
                       f"{zahl(100 * (1 - f[0]), 0)} % billiger")
                out.append(("HINWEIS", f"Pos. {zeilen[i].get('pos')}: {wie} als {f[2]} frühere Teile "
                                       f"{w['profil_id']} {w['werkstoff_id']} ähnlicher Länge ({zahl(w['eur_kg'], 2)} "
                                       f"statt im Mittel {zahl(f[1], 2)} €/kg; Zeiten, Stückzahl und Preis prüfen)", i))
                continue
            if f:
                continue            # genug ähnliche Teile und im Rahmen: der grobe Vergleich zählt nicht
            alt = (vergleich or {}).get((w["profil_id"], w["werkstoff_id"])) or []
            if len(alt) < VERGLEICH_MIN:
                continue
            median = statistics.median(alt)
            if median > 0 and not 1 / FAKTOR <= w["eur_kg"] / median <= FAKTOR:
                i = zeile_i()
                out.append(("HINWEIS", f"Pos. {zeilen[i].get('pos')}: {zahl(w['eur_kg'], 2)} €/kg, frühere Angebote "
                                       f"{w['profil_id']} {w['werkstoff_id']} im Mittel {zahl(median, 2)} €/kg "
                                       "(Stückzahl, Länge und Preis prüfen)", i))
    laser_h, ertrag = ertrag_laser(zeilen, summen)
    satz = _n(summen.get("satz_laser"))
    if laser_h > 0 and satz > 0 and ertrag < laser_h * satz - 0.005:
        out.append(("HINWEIS", f"Ertrag je Laserstunde {zahl(ertrag / laser_h, 2)} € liegt unter dem Stundensatz "
                               f"{zahl(satz, 2)} €/h (Verkaufspreis ohne Material, Zukaufteile und Fracht)", None))
    return out


def ertrag_laser(zeilen, summen):
    """(Laserstunden, Ertrag €) eines Angebots: Verkaufspreis nach Skonto ohne Material, Zukaufteile und Fracht; der
    Ertrag je Laserstunde ist Ertrag ÷ Laserstunden (auch in der Angebots-Auswertung je Kunde, Vorschlag K5)."""
    skonto = _n(summen.get("skonto_satz")) / 100
    laser_h = sum(_n(z.get("laser_netto")) * _n(z.get("stueck")) for z in zeilen if z) / 3600
    ertrag = (_n(summen.get("verkauf")) * (1 - skonto) - _n(summen.get("material")) - _n(summen.get("zukauf_einstand"))
              - _n(summen.get("zukauf_aufschlag")) - _n(summen.get("fracht")))
    return laser_h, ertrag
