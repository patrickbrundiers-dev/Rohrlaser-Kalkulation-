"""Richtwerte für den Palettenversand in Deutschland (Recherche 10/2026), lieber etwas zu teuer als zu günstig.

Quelle der Preise: Medianwerte der Online-Frachtrechner für eine Europalette (Cargolo, Auswertung 10.09.–09.10.2026,
netto inkl. Maut und Dieselzuschlag): bis 200 km 85 € (85–90), 200–450 km 95 € (85–105), 450–650 km 110 € (90–115),
über 650 km 120 € (95–125); 2–3 Paletten 190 €, 4–6 Paletten 285 € je Sendung. Langgut 6 m (225–900 kg, 100–900 km)
laut veröffentlichter Händlertabelle etwa 230–390 € netto; Überlänge 2,40–3,00 m etwa 59 € netto; Avis 15–35 €;
Inselzuschlag ab 25 €. Angesetzt: Obergrenze der üblichen Spanne + 10 % Puffer.

Zonen: vier Ringe nach Straßenentfernung (Luftlinie × 1,25) vom Versandort zum Mittelpunkt der zweistelligen
PLZ-Region, dazu eine Inselzone. Keine Speditionsangebote: alle Zeilen tragen RICHTWERT in der Bemerkung.
"""
import math

RICHTWERT = "RICHTWERT Recherche 10/2026 (Marktpreise + 10 % Puffer), kein Speditionsangebot"
STRASSE = 1.25          # Straßen-km je Luftlinien-km (grob)

# Mittelpunkt (Breite, Länge) der zweistelligen PLZ-Regionen (Leitregionen), gerundet auf die Hauptstadt der Region
REGIONEN = {
    "01": (51.05, 13.74), "02": (51.18, 14.42), "03": (51.76, 14.33), "04": (51.34, 12.37), "06": (51.48, 11.97),
    "07": (50.88, 12.08), "08": (50.72, 12.49), "09": (50.83, 12.92), "10": (52.52, 13.40), "12": (52.47, 13.45),
    "13": (52.56, 13.33), "14": (52.40, 13.06), "15": (52.34, 14.55), "16": (52.83, 13.82), "17": (53.56, 13.26),
    "18": (54.09, 12.13), "19": (53.63, 11.41), "20": (53.55, 10.00), "21": (53.40, 10.10), "22": (53.60, 10.05),
    "23": (53.87, 10.69), "24": (54.32, 10.14), "25": (54.10, 9.30), "26": (53.20, 7.90), "27": (53.30, 8.80),
    "28": (53.08, 8.80), "29": (52.75, 10.30), "30": (52.37, 9.73), "31": (52.15, 9.70), "32": (52.15, 8.75),
    "33": (51.85, 8.55), "34": (51.31, 9.48), "35": (50.65, 8.70), "36": (50.55, 9.68), "37": (51.53, 9.93),
    "38": (52.27, 10.52), "39": (52.13, 11.63), "40": (51.23, 6.78), "41": (51.19, 6.44), "42": (51.26, 7.15),
    "44": (51.51, 7.47), "45": (51.46, 7.01), "46": (51.60, 6.80), "47": (51.40, 6.65), "48": (51.96, 7.63),
    "49": (52.28, 8.05), "50": (50.94, 6.96), "51": (50.97, 7.10), "52": (50.78, 6.08), "53": (50.73, 7.10),
    "54": (49.75, 6.64), "55": (49.95, 7.70), "56": (50.36, 7.59), "57": (50.87, 8.02), "58": (51.36, 7.47),
    "59": (51.65, 7.95), "60": (50.11, 8.68), "61": (50.25, 8.70), "63": (50.00, 9.05), "64": (49.87, 8.65),
    "65": (50.08, 8.24), "66": (49.24, 7.00), "67": (49.45, 8.00), "68": (49.49, 8.47), "69": (49.40, 8.69),
    "70": (48.78, 9.18), "71": (48.80, 9.10), "72": (48.50, 9.05), "73": (48.75, 9.80), "74": (49.14, 9.22),
    "75": (48.89, 8.70), "76": (49.01, 8.40), "77": (48.47, 7.94), "78": (47.90, 8.70), "79": (47.99, 7.84),
    "80": (48.14, 11.58), "81": (48.12, 11.60), "82": (47.80, 11.20), "83": (47.85, 12.12), "84": (48.54, 12.15),
    "85": (48.60, 11.60), "86": (48.37, 10.90), "87": (47.73, 10.31), "88": (47.78, 9.61), "89": (48.40, 9.99),
    "90": (49.45, 11.08), "91": (49.60, 10.95), "92": (49.50, 12.00), "93": (49.01, 12.10), "94": (48.57, 13.43),
    "95": (50.00, 11.70), "96": (50.00, 10.95), "97": (49.79, 9.95), "98": (50.60, 10.70), "99": (50.98, 11.03),
}

# Inseln ohne feste Straßenverbindung (PLZ von, PLZ bis)
INSELN = (("25938", "25999", "Föhr, Amrum, Sylt"), ("25849", None, "Pellworm"), ("25859", None, "Hallig Hooge"),
          ("25863", None, "Halligen"), ("25869", None, "Hallig Gröde"), ("26465", None, "Langeoog"),
          ("26474", None, "Spiekeroog"), ("26486", None, "Wangerooge"), ("26548", None, "Norderney"),
          ("26571", None, "Juist"), ("26579", None, "Baltrum"), ("26757", None, "Borkum"),
          ("27498", None, "Helgoland"), ("27499", None, "Neuwerk"), ("18565", None, "Hiddensee"))

# Ringe: (Zone, Bezeichnung, bis Straßen-km, Preis 1 Palette); 2–3 Paletten je 85 %, 4–6 je 70 % des Preises
RINGE = (("RW1", "bis 200 km", 200, 100.0), ("RW2", "200–450 km", 450, 115.0), ("RW3", "450–650 km", 650, 125.0),
         ("RW4", "über 650 km", None, 140.0))
MENGEN = ((1, 1.0), (3, 0.85), (6, 0.70))
TARIF = "RW-PALETTE"
VERSANDART = "Palettenversand"


def entfernung(a, b):
    """Straßen-km (geschätzt) zwischen zwei Punkten (Breite, Länge)."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    d = math.radians(b[1] - a[1])
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(d)
    return 6371 * math.acos(max(-1.0, min(1.0, c))) * STRASSE


def ring(km):
    for zone, _, bis, _ in RINGE:
        if bis is None or km <= bis:
            return zone
    return RINGE[-1][0]


def richtwerte(absender_plz):
    """Frachtdaten {Tabelle: [Zeilen]} für den Palettenversand ab absender_plz (mindestens zwei Ziffern).
    ValueError, wenn die PLZ-Region unbekannt ist."""
    from .fracht_daten import DIENSTLEISTER, LAENDER, LHT, PLZ, PREISE, TARIFE, ZONEN, ZUSCHLAEGE

    def zeilen(t, werte):
        return [{f.name: (w[i] if i < len(w) else None) for i, f in enumerate(t.felder)} for w in werte]
    start = REGIONEN.get("".join(c for c in str(absender_plz or "") if c.isdigit())[:2])
    if start is None:
        raise ValueError(f"Versandort-PLZ {absender_plz or '(leer)'} unbekannt: zwei Ziffern einer deutschen PLZ nötig")
    r = RICHTWERT
    laender = [("DE", "Deutschland", 5, "EUR", "ja", r)]
    zonen = [(z, f"Palette {text}", "DE", "normal", "ja" if bis is None else "nein", bis, "ja", r)
             for z, text, bis, _ in RINGE]
    zonen.append(("RW-INSEL", "Inseln", "DE", "Insel", "nein", None, "ja", r + "; Preis wie über 650 km + Inselzuschlag"))
    plz = []
    for region, punkt in sorted(REGIONEN.items()):
        km = entfernung(start, punkt)
        plz.append(("DE", region + "*", None, ring(km), None, None, None, None, f"{r}; ca. {km:.0f} km"))
    plz += [("DE", von, bis, "RW-INSEL", None, None, None, None, f"{r}; {name}") for von, bis, name in INSELN]
    dl = [("RICHTWERT", "Richtwert Palettenversand (Marktpreise)", VERSANDART, None, "ja", r),
          ("SLH", "Spedition u. Logistik Haaren, Keimeier u. Finke GmbH (Bad Wünnenberg, CTL-Partner)", VERSANDART,
           None, "ja", "keine öffentlichen Preise gefunden; Tarif nach Angebot hier eintragen")]
    tarife = [(TARIF, "Palettenversand Deutschland (Richtwert, inkl. Maut und Diesel)", "RICHTWERT", "Standardtarif",
               "Palettentarif", VERSANDART, "DE", None, None, "2026-01-01", None, "EUR", None, None, None, None, None,
               None, 50, "2026-10", "ja", r)]
    preise = []
    for zone, _, _, p in RINGE + (("RW-INSEL", "", None, RINGE[-1][3]),):
        for bis, f in MENGEN:
            preise.append((TARIF, zone, "Stellplatz", None, bis, round(p * f, 2), "je Einheit", r))
        preise.append((TARIF, zone, "Stellplatz", None, None, None, "je Einheit",
                       "mehr als 6 Stellplätze: Teilladung, Preis anfragen"))
    lht = [("EUR", "Europalette 1200 × 800", "Europalette", 1200, 800, 144, 25, 800, 1400, "nein", None, 1, "ja",
            r + "; Nutzlast im Packvorschlag 800 kg"),
           ("EW", "Einwegpalette 1200 × 800", "Einwegpalette", 1200, 800, 140, 15, 800, 1400, "nein", None, 1, "ja", r),
           ("IND", "Industriepalette 1200 × 1000", "Industriepalette", 1200, 1000, 144, 30, 1000, 1400, "nein", None,
            1.25, "ja", r),
           ("GB", "Gitterbox 1240 × 835 × 970", "Gitterbox", 1240, 835, 970, 85, 1000, 1200, "ja", 4, 1, "ja", r),
           ("SOND", "Sonderpalette 2400 × 1000", "Sonderpalette", 2400, 1000, 150, 40, 1000, 2400, "nein", None, 2.0,
            "ja", r),
           ("LG", "Langgut bis 6,5 m", "Langgut", 6500, 800, 300, 30, 2000, 6500, "nein", None, 3.0, "ja",
            r + "; zählt als 3 Stellplätze"),
           ("SL", "Sonderladung (Maße je Sendung)", "Sonderladung", None, None, None, None, None, None, "nein", None,
            None, "ja", r)]
    zus = [("RW-SCHWER", "Schwere Palette (über 300 kg je Stellplatz)", "Sonderhandling", "€ je Stellplatz", None,
            None, 40.0, None, None, None, None, None, None, TARIF, None, None, "Gewicht je Stellplatz über", 300, "ja",
            r + "; Marktpreis 300–600 kg ca. 140 € statt 100 €"),
           ("RW-LANG", "Überlänge (Teile über 2,40 m)", "Langgut / Überlänge", "€ je Sendung", None, None, 60.0, None,
            None, None, None, None, None, TARIF, None, None, "Teillänge über", 2400, "ja", r),
           ("RW-INSEL", "Inselzuschlag", "Insel- und Randgebiet", "€ je Sendung", None, None, 60.0, None, None, None,
            None, None, None, TARIF, None, None, "Zonenart Insel/Randgebiet/Sondergebiet", None, "ja", r),
           ("RW-AVIS", "Avisierung", "Avisierung", "€ je Sendung", None, None, 25.0, None, None, None, None, None, None,
            TARIF, None, None, "nur wenn gewählt", None, "ja", r),
           ("RW-HEBE", "Hebebühne", "Hebebühne", "€ je Sendung", None, None, 40.0, None, None, None, None, None, None,
            TARIF, None, None, "nur wenn gewählt", None, "ja", r + "; Schätzwert, keine Marktdaten gefunden"),
           ("RW-WARTE", "Wartezeit", "Wartezeit", "€ je Stunde", None, None, 60.0, None, None, None, None, None, None,
            TARIF, None, None, "nur wenn gewählt", None, "ja", r + "; Schätzwert, keine Marktdaten gefunden")]
    return {"fracht_laender": zeilen(LAENDER, laender), "fracht_zonen": zeilen(ZONEN, zonen),
            "fracht_plz": zeilen(PLZ, plz), "fracht_dienstleister": zeilen(DIENSTLEISTER, dl),
            "fracht_tarife": zeilen(TARIFE, tarife), "fracht_preise": zeilen(PREISE, preise),
            "fracht_lht": zeilen(LHT, lht), "fracht_zuschlaege": zeilen(ZUSCHLAEGE, zus)}
