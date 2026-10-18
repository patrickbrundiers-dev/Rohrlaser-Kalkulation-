"""Aufbau eines Auftrags: Kopf und Positionen (Spalten wie Blatt 'Auftrag' der Mappe)."""
import re

from .stammdaten import Feld, Tabelle

KOPF = (
    Feld("nummer", "Auftragsnummer", 0, pflicht=True),
    Feld("kundennr", "Kundennummer", 0),
    Feld("kunde", "Kundenname", 0),
    Feld("datum", "Datum", 0, "datum"),
    Feld("maschine", "Maschine", 0, "auswahl", auswahl="maschine", pflicht=True),
    Feld("stange", "Standard-Stangenlänge [mm]", 0, "ganz", 500, 20000, pflicht=True),
    Feld("bemerkung", "Bemerkung", 0),
    Feld("fracht", "Frachtkosten [€]", 0, "zahl", 0, 100000, stellen=2),
)
# Zelle des Auftragskopfs in der Mappe
KOPF_ZELLE = {"nummer": "C4", "kundennr": "C5", "kunde": "C6", "datum": "C7", "maschine": "C8", "stange": "C9"}

GEWINDE_MUSTER = (r"(?i)\dx\s*M", "Format Anzahl x Gewinde, mehrere mit Semikolon, z. B. 4xM6; 2xM8")

POSITIONEN = Tabelle(
    "positionen", "Positionen", "Auftrag",
    (Feld("pos", "Pos.", 1, "ganz", 1, 99999, breite=50),
     Feld("artikel", "Artikelnummer", 2, breite=140),
     Feld("bezeichnung", "Bezeichnung", 3, breite=150),
     Feld("profil_id", "Profil-ID", 4, "auswahl", auswahl="profil", breite=120),
     Feld("werkstoff_id", "Werkstoff-ID", 5, "auswahl", auswahl="werkstoff", breite=105),
     Feld("laenge", "Teilelänge [mm]", 6, "zahl", 1, 20000, stellen=1, breite=80),
     Feld("stueck", "Stückzahl", 7, "ganz", 1, 100000, breite=65),
     Feld("schneidweg", "Schneidweg je Teil [mm]", 8, "zahl", 0, 1000000, stellen=1, breite=85),
     Feld("einstiche", "Einstiche je Teil", 9, "ganz", 0, 1000, breite=65),
     Feld("stange", "Stangenlänge abweichend [mm]", 10, "ganz", 500, 20000, breite=85),
     Feld("satz", "Satz", 43, breite=90),
     Feld("je_satz", "Stück je Satz", 44, "ganz", 1, 100000, breite=60),
     Feld("preis_m", "Materialpreis abweichend [€/m]", 42, "zahl", 0, 100000, stellen=2, breite=85),
     Feld("gewinde", "Gewinde geprüft", 33, muster=GEWINDE_MUSTER, breite=110),
     Feld("zeit_manuell", "Schneidzeit manuell je Teil [s]", None, "zahl", 0, 100000, stellen=1, breite=85),
     # Zusatzarbeiten als JSON-Liste [{name, menge, preis, text}] (Dialog 'Zusatzarbeiten …')
     Feld("zusatz", "Zusatzarbeiten", None, "zusatz", breite=220),
     # STEP-Werte
     Feld("a_gerade", "Anfangsschnitt gerade", 25, "auswahl", auswahl="janein", breite=70),
     Feld("a_schnitt", "Anfangsschnitt [mm]", 26, "zahl", 0, 100000, stellen=1, breite=75),
     Feld("b_gerade", "Endschnitt gerade", 27, "auswahl", auswahl="janein", breite=70),
     Feld("b_schnitt", "Endschnitt [mm]", 28, "zahl", 0, 100000, stellen=1, breite=75),
     Feld("innen", "Innenkonturen [mm]", 29, "zahl", 0, 1000000, stellen=1, breite=75),
     Feld("gravur", "Gravur [mm]", 30, "zahl", 0, 1000000, stellen=1, breite=70),
     Feld("bohrungen", "Bohrungen", 31, breite=110),
     Feld("gewinde_vorschlag", "Gewinde-Vorschlag", 32, breite=110),
     Feld("klein_n", "Kontur klein [Stk]", 34, "ganz", 0, 10000, breite=60),
     Feld("klein_mm", "Kontur klein [mm]", 35, "zahl", 0, 1000000, stellen=1, breite=70),
     Feld("mittel_n", "Kontur mittel [Stk]", 36, "ganz", 0, 10000, breite=60),
     Feld("mittel_mm", "Kontur mittel [mm]", 37, "zahl", 0, 1000000, stellen=1, breite=70),
     Feld("gross_n", "Kontur groß [Stk]", 38, "ganz", 0, 10000, breite=60),
     Feld("gross_mm", "Kontur groß [mm]", 39, "zahl", 0, 1000000, stellen=1, breite=70)),
    (),
    "Positionen eintragen oder per STEP-Import übernehmen. Die Spalte Status zeigt wie in der Mappe "
    "FEHLER, WARNUNG, HINWEIS oder OK.",
    zeilen=(13, 512))
STEP_FELDER = {"a_gerade", "a_schnitt", "b_gerade", "b_schnitt", "innen", "gravur", "bohrungen", "gewinde_vorschlag",
               "klein_n", "klein_mm", "mittel_n", "mittel_mm", "gross_n", "gross_mm"}
assert STEP_FELDER <= {f.name for f in POSITIONEN.felder}


def naechste_nummer(nr):
    """'A-2026-0007' -> 'A-2026-0008': letzte Ziffernfolge um 1 erhöhen, Stellenzahl beibehalten
    (wie NaechsteNummer in vba/Bedienung.bas)."""
    nr = str(nr or "")
    treffer = list(re.finditer(r"\d+", nr))
    if not treffer:
        return nr
    m = treffer[-1]
    neu = str(int(m.group()) + 1).zfill(len(m.group()))
    return nr[:m.start()] + neu + nr[m.end():]
