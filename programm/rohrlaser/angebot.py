"""Aufbau eines Angebots: Kopf und Positionen."""
import re

from .stammdaten import Feld, Tabelle

KOPF = (
    Feld("nummer", "Angebotsnummer", pflicht=True),
    Feld("kundennr", "Kundennummer"),
    Feld("kunde", "Kundenname"),
    Feld("datum", "Datum", "datum"),
    Feld("maschine", "Maschine", "auswahl", auswahl="maschine", pflicht=True),
    Feld("stange", "Standard-Stangenlänge [mm]", "ganz", 500, 20000, pflicht=True),
    Feld("bemerkung", "Bemerkung"),
    Feld("fracht", "Frachtkosten [€]", "zahl", 0, 100000, stellen=2),
    # Fracht (fracht_angebot.py): leer = manuell bzw. je Stück wie bisher; Frachtberechnung als JSON
    Feld("fracht_modus", "Frachtart", "auswahl", auswahl="frachtmodus"),
    Feld("fracht_umlage", "Fracht verteilen", "auswahl", auswahl="frachtumlage"),
    Feld("fracht_sendung", "Frachtberechnung (Eingaben und Tarif-Snapshot)"),
    # Zahlungsbedingungen: Vorgabe aus dem Kunden bzw. den Einstellungen; Skonto wird in den Preis eingerechnet
    Feld("skonto", "Skonto [%]", "zahl", 0, 20, stellen=1),
    Feld("skonto_tage", "Skontofrist [Tage]", "ganz", 0, 365),
    Feld("zahlungsziel", "Zahlungsziel netto [Tage]", "ganz", 0, 365),
)
ZAHLUNG = ("skonto", "skonto_tage", "zahlungsziel")
# Kalkulationswerte je Angebot: beim Anlegen aus den Einstellungen übernommen, danach je Angebot änderbar;
# leer (ältere Angebote) = Wert der Einstellungen. Prozentwerte stehen hier in %, in den Einstellungen als Anteil.
KALKULATION = (
    Feld("zuschlag_material", "Zuschlag Material [%]", "zahl", 0, 500, stellen=1),
    Feld("zuschlag_fertigung", "Zuschlag Fertigung [%]", "zahl", 0, 500, stellen=1),
    Feld("zuschlag_fremdleistung", "Zuschlag Fremdleistung [%]", "zahl", 0, 500, stellen=1),
    Feld("gewinn", "Gewinn [%]", "zahl", 0, 500, stellen=1),
    Feld("ruesten_abmessung", "Rüstzeit je Abmessung [min]", "zahl", 0, 1440, stellen=1),
    Feld("pauschale_abmessung", "Pauschale je Abmessung [€]", "zahl", 0, 100000, stellen=2),
    Feld("programmierung_teil", "Programmierkosten je Teil [€]", "zahl", 0, 100000, stellen=2),
    Feld("angebotsaufschlag", "Angebotsaufschlag [€]", "zahl", 0, 100000, stellen=2),
)
KALK_PROZENT = ("zuschlag_material", "zuschlag_fertigung", "zuschlag_fremdleistung", "gewinn")
KOPF = KOPF + KALKULATION

GEWINDE_MUSTER = (r"(?i)\dx\s*M", "Format Anzahl x Gewinde, mehrere mit Semikolon, z. B. 4xM6; 2xM8")

POSITIONEN = Tabelle(
    "positionen", "Positionen",
    (Feld("pos", "Pos.", "ganz", 1, 99999, breite=50),
     Feld("artikel", "Artikelnummer", breite=140),
     Feld("bezeichnung", "Bezeichnung", breite=150),
     Feld("profil_id", "Profil-ID", "auswahl", auswahl="profil", breite=120),
     Feld("werkstoff_id", "Werkstoff-ID", "auswahl", auswahl="werkstoff", breite=105),
     Feld("oberflaeche", "Oberfläche", "auswahl", auswahl="oberflaeche", breite=80),
     Feld("laenge", "Teilelänge [mm]", "zahl", 1, 20000, stellen=1, breite=80),
     Feld("stueck", "Stückzahl", "ganz", 1, 100000, breite=65),
     Feld("schneidweg", "Schneidweg je Teil [mm]", "zahl", 0, 1000000, stellen=1, breite=85),
     Feld("einstiche", "Einstiche je Teil", "ganz", 0, 1000, breite=65),
     Feld("stange", "Stangenlänge abweichend [mm]", "ganz", 500, 20000, breite=85),
     Feld("satz", "Satz", breite=90),
     Feld("je_satz", "Stück je Satz", "ganz", 1, 100000, breite=60),
     Feld("preis_m", "Materialpreis abweichend [€/m]", "zahl", 0, 100000, stellen=2, breite=85),
     Feld("gewinde", "Gewinde geprüft", muster=GEWINDE_MUSTER, breite=110),
     Feld("zeit_manuell", "Schneidzeit je Teil [s]", "zahl", 0, 100000, stellen=1, breite=85),
     # Zusatzarbeiten als JSON-Liste [{name, menge, preis, text}] (Dialog 'Zusatzarbeiten …')
     Feld("zusatz", "Zusatzarbeiten", "zusatz", breite=220),
     # Zukaufteile als JSON-Liste [{artikel_id, menge (je Teil), aufschlag (%), stand}] (Dialog 'Zukaufteile …')
     Feld("zukauf", "Zukaufteile", "zukauf", breite=220),
     # STEP-Werte
     Feld("a_gerade", "Anfangsschnitt gerade", "auswahl", auswahl="janein", breite=70),
     Feld("a_schnitt", "Anfangsschnitt [mm]", "zahl", 0, 100000, stellen=1, breite=75),
     Feld("b_gerade", "Endschnitt gerade", "auswahl", auswahl="janein", breite=70),
     Feld("b_schnitt", "Endschnitt [mm]", "zahl", 0, 100000, stellen=1, breite=75),
     Feld("innen", "Innenkonturen [mm]", "zahl", 0, 1000000, stellen=1, breite=75),
     Feld("gravur", "Gravur [mm]", "zahl", 0, 1000000, stellen=1, breite=70),
     Feld("bohrungen", "Bohrungen", breite=110),
     Feld("gewinde_vorschlag", "Gewinde-Vorschlag", breite=110),
     Feld("klein_n", "Kontur klein [Stk]", "ganz", 0, 10000, breite=60),
     Feld("klein_mm", "Kontur klein [mm]", "zahl", 0, 1000000, stellen=1, breite=70),
     Feld("mittel_n", "Kontur mittel [Stk]", "ganz", 0, 10000, breite=60),
     Feld("mittel_mm", "Kontur mittel [mm]", "zahl", 0, 1000000, stellen=1, breite=70),
     Feld("gross_n", "Kontur groß [Stk]", "ganz", 0, 10000, breite=60),
     Feld("gross_mm", "Kontur groß [mm]", "zahl", 0, 1000000, stellen=1, breite=70)),
    (),
    "Positionen eintragen oder per STEP-Import übernehmen. Die Spalte Status zeigt "
    "FEHLER, WARNUNG, HINWEIS oder OK.")
STEP_FELDER = {"a_gerade", "a_schnitt", "b_gerade", "b_schnitt", "innen", "gravur", "bohrungen", "gewinde_vorschlag",
               "klein_n", "klein_mm", "mittel_n", "mittel_mm", "gross_n", "gross_mm"}
assert STEP_FELDER <= {f.name for f in POSITIONEN.felder}


def naechste_nummer(nr):
    """'A-2026-0007' -> 'A-2026-0008': letzte Ziffernfolge um 1 erhöhen, Stellenzahl beibehalten."""
    nr = str(nr or "")
    treffer = list(re.finditer(r"\d+", nr))
    if not treffer:
        return nr
    m = treffer[-1]
    neu = str(int(m.group()) + 1).zfill(len(m.group()))
    return nr[:m.start()] + neu + nr[m.end():]
