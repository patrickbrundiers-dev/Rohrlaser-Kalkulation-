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
