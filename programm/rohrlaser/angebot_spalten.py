"""Spalten der Ergebnistabellen eines Angebots (Anzeige im Programm und Kalkulation-PDF):
[(Titel, Schlüssel oder Funktion(Zeile), Nachkommastellen, Breite in Pixeln)]."""
from .stammdaten import zahl_als_text

def _position(z, schluessel):
    """Betrag je Teil × Stückzahl (leer, wenn der Betrag fehlt)."""
    w = z.get(schluessel)
    return w * (z.get("stueck") or 0) if isinstance(w, (int, float)) else None


KALK_SPALTEN = [("Pos.", "pos", 0, 50), ("Artikelnummer", "artikel", None, 130), ("Satz", "satz", None, 120),
                ("Stückzahl", "stueck", 0, 60),
                ("Kundenmaterial", "kundenmaterial", None, 70),
                ("Material je Teil [€]", "material_teil", 3, 80), ("Laserzeit netto je Teil [s]", "laser_netto", 1, 80),
                ("Gewindezeit je Teil [s]", "gewindezeit", 1, 75),
                ("Laser schneiden je Teil [€]", "laser_schneiden_teil", 3, 80), ("Gewinde je Teil [€]", "gewinde_teil", 3, 75),
                ("Zusatzarbeiten je Teil [€]", "zusatz_teil", 3, 85),
                ("Weitere Arbeitsschritte je Teil [€]", "arbeit_teil", 3, 100),
                ("Rüsten Maschine je Teil [€]", "ruesten_maschine_teil", 3, 85),
                ("Rüsten je Abmessung je Teil [€]", "ruesten_abm_teil", 3, 90),
                ("Stangenwechsel je Teil [€]", "stangenwechsel_teil", 3, 85),
                ("Handling Kundenmaterial je Teil [€]", "handling_teil", 3, 100),
                ("Zuschlag Material je Teil [€]", "zuschlag_material_teil", 3, 85),
                ("Zuschlag Fertigung je Teil [€]", "zuschlag_fertigung_teil", 3, 85),
                ("Zuschlag Fremdleistung je Teil [€]", "zuschlag_fremdleistung_teil", 3, 95),
                ("Herstellkosten je Teil [€]", "herstell_teil", 3, 85),
                ("Programmierung je Teil [€]", "programmierung_anteil", 3, 85),
                ("Pauschale je Abmessung je Teil [€]", "pauschale_abm_teil", 3, 95),
                ("Angebotsaufschlag je Teil [€]", "angebotsaufschlag_teil", 3, 90),
                ("Zukaufteile Einstand je Teil [€]", "zukauf_einstand_teil", 3, 90),
                ("Aufschlag Zukaufteile je Teil [€]", "zukauf_aufschlag_teil", 3, 90),
                ("Gewinn je Teil [€]", "gewinn_teil", 3, 75), ("Fracht je Teil [€]", "fracht_teil", 3, 75),
                ("Skonto je Teil [€]", "skonto_teil", 3, 75),
                ("Musterumlage je Teil [€]", "muster_teil", 3, 85),
                ("Mindestpreis je Teil [€]", "mindestpreis_teil", 3, 85),
                ("Verkaufspreis je Teil [€]", "preis_teil", 3, 85),
                ("Verkaufspreis Position [€]", "preis_position", 2, 95), ("Herstellkosten Position [€]", "herstell_position", 2, 95),
                ("Hinweis", "hinweis", None, 190),
                ("Materialkosten Gruppe [€]", "material_gruppe", 2, 90), ("Längenanteil an Gruppe", lambda z: 100 * z["anteil"], 1, 75),
                ("Wandstärke-Stufe [mm]", "wand_stufe", 1, 85), ("Schneidgas", "gas", None, 60),
                ("Vorschub groß [mm/min]", "vorschub_gross", 0, 75),
                ("Vorschub mittel [mm/min]", "vorschub_mittel", 0, 75), ("Vorschub klein [mm/min]", "vorschub_klein", 0, 75),
                ("Vorschub Gravur [mm/min]", "vorschub_gravur", 0, 75), ("Einstechzeit [s]", "einstechzeit", 1, 65),
                ("Laserzeit brutto je Teil [s]", "laser_brutto", 1, 80),
                ("davon Kontur groß + Rest [s]", "zeit_gross", 1, 90),
                ("davon Kontur mittel [s]", "zeit_mittel", 1, 75), ("davon Kontur klein [s]", "zeit_klein", 1, 75),
                ("davon Gravur [s]", "zeit_gravur", 1, 70),
                ("davon Gravur Anbauteile [s]", "zeit_gravur_anbau", 1, 85),
                ("davon Einstiche [s]", "zeit_einstiche", 1, 70),
                ("davon Mehrzeit 3D [s]", "zeit_d3", 1, 80), ("davon Ecken [s]", "zeit_ecken", 1, 70),
                ("davon Anschlag doppelt [s]", "zeit_doppel", 1, 85),
                ("3D-Bearbeitung je Teil [s]", "zeit_3d_gesamt", 1, 85), ("3D-Schnittweg je Teil [mm]", "mm_3d", 1, 85),
                ("Einsparung gemeinsame Schnitte je Teil [s]", "einsparung", 1, 95),
                ("Schneidzeit manuell", "zeit_manuell", None, 70),
                ("Programmierzeit [min]", "prog_min", 1, 80),
                ("Zusatzzeit (z. B. Gravur extra) je Teil [s]", "zeit_extra", 1, 95),
                ("Prüfzeit Anbauteile je Teil [s]", "zeit_pruefung", 1, 85),
                ("Gewinde Festpreis je Teil [€]", "gewinde_preis", 3, 85),
                ("Zusatzarbeiten (Menge je Teil)", "zusatz_text", None, 220),
                ("Material Position [€]", "material_position", 2, 85), ("Laser schneiden Position [€]", lambda z: _position(z, "laser_schneiden_teil"), 2, 85),
                ("Gewinde Position [€]", lambda z: _position(z, "gewinde_teil"), 2, 80),
                ("Zusatzarbeiten Position [€]", "zusatz_position", 2, 85)]
STANGEN_SPALTEN = [("Stange Nr.", "nr", 0, 55), ("Profil-ID", "profil", None, 110), ("Werkstoff-ID", "werkstoff", None, 100),
                   ("Oberfläche", lambda z: z.get("oberflaeche") or "roh", None, 75),
                   ("Stangenlänge [mm]", "stange", 0, 90), ("Endbeschnitt [mm]", "end", 0, 90), ("Greiferrest [mm]", "greif", 0, 70),
                   ("Teile [Stk]", "teile", 0, 50), ("Summe Teilelängen [mm]", "summe", 1, 85),
                   ("Schnittverluste + Abstände [mm]", "verlust", 1, 90), ("Belegt bis [mm]", "belegt", 1, 75),
                   ("Rest / Verschnitt inkl. Greiferrest [mm]", "rest", 1, 100), ("Ausnutzung [%]", lambda z: 100 * z["ausnutzung"], 1, 75),
                   ("Prüfung", "pruefung", None, 85), ("Trennungen [Stk]", "trennungen", 0, 85),
                   ("davon gemeinsamer Schnitt", "gemeinsam", 0, 95), ("Stangengewicht [kg]", "gewicht", 2, 100),
                   ("Materialkosten Stange [€]", "kosten", 2, 105), ("Belegung (Pos. × Länge)", "belegung", None, 400)]
TEIL_SPALTEN = [("Platz", "platz", 0, 45), ("Pos.", "pos", 0, 50), ("Artikelnummer", "artikel", None, 140),
                ("Teilelänge [mm]", "laenge", 1, 80), ("Von [mm]", "von", 2, 80), ("Bis [mm]", "bis", 2, 80),
                ("Lage", "lage", None, 70), ("Schweißnaht", "naht_text", None, 120),
                ("Trennung zum Vorgänger", "trennung", None, 140),
                ("Eingesparter Schneidweg [mm]", "eingespart_mm", 1, 90), ("Eingesparte Einstiche", "eingespart_e", 0, 80),
                ("Eingespartes Material [mm]", lambda z: z.get("material_gespart") or None, 1, 90)]
AUSW_SPALTEN = [("Profil-ID", "profil", None, 110), ("Werkstoff-ID", "werkstoff", None, 100),
                ("Oberfläche", lambda z: z.get("oberflaeche") or "roh", None, 75), ("Stangenlänge [mm]", "stange", 0, 90),
                ("Teile [Stk]", "teile", 0, 55), ("Stangen optimiert", "stangen", 0, 70), ("Stangen manuell", "manuell", 0, 70),
                ("Untergrenze Stangen", "untergrenze", 0, 75), ("Ersparnis Stangen", lambda z: z["manuell"] - z["stangen"], 0, 70),
                ("Materialbedarf [m]", "bedarf", 2, 90), ("Teilelänge [m]", "laenge", 2, 75), ("Verschnitt [m]", "verschnitt", 2, 75),
                ("Ausnutzung optimiert [%]", lambda z: 100 * z["ausnutzung"], 1, 80),
                ("Ausnutzung manuell [%]", lambda z: 100 * z["ausnutzung_manuell"], 1, 80),
                ("Gemeinsame Schnitte", "gemeinsam", 0, 85), ("Stangen ohne Drehen", "ohne_drehung", 0, 75),
                ("Gehrungen ineinander [mm]", "gehrung_mm", 1, 85), ("Über Untergrenze [Stangen]", lambda z: z["stangen"] - z["untergrenze"], 0, 80),
                ("Bewertung", "bewertung", None, 230)]
FEHLER_SPALTEN = [("Pos.", "pos", 0, 50), ("Artikelnummer", "artikel", None, 150), ("Anzahl", "anzahl", 0, 60),
                  ("Grund", "grund", None, 300)]

# Kompakte Teileübersicht im Reiter Kalkulation (Patrick 23.10.2026): das Wichtigste je Bauteil auf einen Blick.
# Laserzeit berechnet = Schneidzeit aus den Konturen (brutto); genutzt = was in den Preis eingeht (nach gemeinsamen
# Schnitten, mit Zusatz- und Prüfzeit, bzw. die Zeit von Hand).
KOMPAKT_SPALTEN = [("Pos.", "pos", 0, 50), ("Artikelnummer", "artikel", None, 130), ("Satz", "satz", None, 130),
                   ("Profil", "profil", None, 130),
                   ("Stückzahl", "stueck", 0, 60), ("Länge [mm]", "laenge", 1, 75), ("Material", "material", None, 110),
                   ("Oberfläche", "oberflaeche", None, 85),
                   ("Laserzeit berechnet je Teil [s]", "laser_brutto", 1, 85),
                   ("Laserzeit genutzt je Teil [s]", "laser_netto", 1, 85), ("Schneidzeit manuell", "zeit_manuell", None, 70),
                   ("Laserzeit genutzt Position [min]", "laser_position_min", 1, 90),
                   ("Verkaufspreis je Teil [€]", "preis_teil", 3, 85), ("Verkaufspreis Position [€]", "preis_position", 2, 95),
                   ("Muster", "muster", None, 150), ("Hinweis", "hinweis", None, 190)]


def muster_info(z):
    """Spalte Muster der Kompaktansicht: Musterteil mit seinem Wert, Serienteil mit dem umgelegten Anteil je Teil."""
    z = z or {}
    if z.get("muster") == "ja":
        return f"Muster, Wert {zahl_als_text(round(z.get('muster_preis_position') or 0, 2), 2)} €"
    if z.get("muster_teil"):
        return f"+{zahl_als_text(round(z['muster_teil'], 3), 3)} € je Teil (Muster)"
    return ""


def kompakt_zeilen(positionen, zeilen):
    """Zeilen der kompakten Übersicht aus Positionen und Kalkulationszeilen (gleiche Reihenfolge, None = ohne
    Kalkulation); 'zeile' = Index der Position für den Sprung in die Positionsliste. Satz und Tönung kommen aus den
    Kalkulationszeilen (satzgruppen.zeilen_markieren)."""
    out = []
    for i, (p, z) in enumerate(zip(positionen, zeilen)):
        if not z:
            continue
        netto = z.get("laser_netto")
        stueck = z.get("stueck") or 0
        zukauf = not p.get("profil_id")
        out.append(dict(zeile=i, pos=z.get("pos"), artikel=z.get("artikel"), satz=z.get("satz") or "",
                        satz_ton=z.get("satz_ton"), profil=p.get("profil_id") or "",
                        stueck=z.get("stueck"), laenge=None if zukauf else p.get("laenge"),
                        material=p.get("werkstoff_id") or "",
                        oberflaeche="" if zukauf else (p.get("oberflaeche") or "roh"),
                        laser_brutto=z.get("laser_brutto"),
                        laser_netto=netto, zeit_manuell=z.get("zeit_manuell") or "",
                        laser_position_min=netto * stueck / 60 if isinstance(netto, (int, float)) else None,
                        preis_teil=z.get("preis_teil"), preis_position=z.get("preis_position"),
                        muster=muster_info(z), hinweis=z.get("hinweis") or ""))
    return out
