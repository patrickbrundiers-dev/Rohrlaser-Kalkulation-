"""Gemeinsame Gestaltungswerte für Oberfläche (stil.py) und PDF-Ausgaben (pdf.py): Farben, Schriftstufen, Abstände.

Nur Konstanten, keine Logik. Eine Farbe wird hier einmal festgelegt und gilt in Programm und Dokumenten gleich."""

# Farben
AKZENT = "#1F4E78"          # Dunkelblau: Titel, Linien unter Tabellenköpfen, Hauptknöpfe
AKZENT_DUNKEL = "#183E60"
TEXT = "#1F2937"
TEXT_GRAU = "#5F6B7A"       # Nebentext, Bezeichnungen über Werten, Hinweise
LINIE = "#E3E7EC"           # feine Linien zwischen Tabellenzeilen
RAHMEN = "#D5DBE3"
FLAECHE = "#F5F7FA"         # zurückhaltende Hinterlegung (Kennzahlen, Staffeln)
BLAU_FLAECHE = "#DDEBF7"    # Hervorhebung (Summe, Verkaufspreis)

# Statusfarben (Text, Fläche)
ROT, ROT_FLAECHE = "#B42318", "#FDECEA"
GELB_TEXT, GELB_FLAECHE = "#7A5A00", "#FFF4CE"
ORANGE = "#B35C00"
GRUEN, GRUEN_FLAECHE = "#1E6B34", "#E3F4E8"

# PDF-Schriftstufen [pt]: Titel, Abschnitt, Text, Tabelle, klein (Fußzeile, Bezeichnungen); kleiner als KLEIN nie
PDF_TITEL, PDF_ABSCHNITT, PDF_TEXT, PDF_TABELLE, PDF_KLEIN = 14, 10.5, 9, 8.5, 7.5

# Oberfläche (UI-Modernisierung U7, 13.11.2026): Werte der Seitenleiste und Abstände; stil.py nutzt dieselben
# Farbwerte im Stylesheet (Prüfung: tests/test_design_werte.py)
NAVIGATION = "#1B2735"              # Seitenleiste links
NAVIGATION_HOVER = "#26354A"
NAVIGATION_GEWAEHLT = "#2C3E55"
NAVIGATION_MARKE = "#6FA8DC"        # Strich links am gewählten Eintrag
NAVIGATION_TEXT = "#C8D2DE"         # Symbole und Text auf der dunklen Leiste
NAVIGATION_GRUPPE = "#8593A4"       # Gruppentitel (Arbeiten, Auftrag, Pflege)
HAUPTKNOPF_DUNKEL = "#2F6CA8"       # Hauptknöpfe im Dunkelmodus
ABSTAND_KLEIN, ABSTAND, ABSTAND_GROSS = 6, 10, 16       # px zwischen Feldern, Karten, Abschnitten

# Designsystem „Klar“ (UI/UX Next Level, Freigabe Patrick 26.11.2026, Variante A): eine Stelle für Flächen, Ecken,
# Größen und Schriftstufen der Oberfläche. stil.py baut daraus das Stylesheet, bausteine.py die Bausteine (Seitenkopf,
# Karte, Kennzahl, Status-Chip, Hinweisband). Neue Oberflächen nehmen nur diese Werte (Prüfung: test_bausteine.py).
ARBEITSFLAECHE = "#F2F4F7"          # Grund hinter Karten und Tabellen, leicht bläulich
KARTE = "#FFFFFF"
KARTE_RAHMEN = "#E3E7EC"
EINGABE_RAHMEN = "#C5CCD6"
AKZENT_FLAECHE = "#EAF1F8"          # Auswahl, gewählter Reiter-Chip, Info-Chip
AUSWAHL = "#DCE9F8"                 # gewählte Tabellenzeile
NEUTRAL_FLAECHE = "#EEF1F4"         # neutraler Chip (Entwurf, Zähler)
TABELLENKOPF = "#F7F9FB"
ECKE, ECKE_KARTE = 6, 8             # px Eckenradius Knöpfe/Eingaben bzw. Karten
CHIP_ECKE = 10
# Schriftstufen der Oberfläche [px bei 100 %]: Seitentitel, Abschnitt, Text, Nebentext; Kennzahl groß
UI_TITEL, UI_ABSCHNITT, UI_TEXT, UI_KLEIN, UI_KENNZAHL = 20, 15, 13, 12, 22
# Status-Chips: Stufe -> (Schrift, Fläche, Zeichen). Status nie nur über die Farbe (Zeichen ✓ ! ✕ i)
CHIPS = {
    "ok": (GRUEN, GRUEN_FLAECHE, "✓"),
    "warnung": (GELB_TEXT, GELB_FLAECHE, "!"),
    "fehler": (ROT, ROT_FLAECHE, "✕"),
    "info": (AKZENT, AKZENT_FLAECHE, "i"),
    "neutral": (TEXT_GRAU, NEUTRAL_FLAECHE, ""),
}

# Preisbalken der Kalkulation (UI Next Level Phase 3): Kostengruppen von dunkel (Material) nach hell, Gewinn grün
PREIS_BALKEN = ("#1F4E78", "#2E6DA4", "#5B8FC7", "#8DB3DC", "#A6C2E0", "#BCCAD9", "#9AA7B6", "#C5CCD6")
PREIS_BALKEN_GEWINN = ("#2E8B4A", "#8CCB9E")       # Gewinn, Skonto/Rundung
