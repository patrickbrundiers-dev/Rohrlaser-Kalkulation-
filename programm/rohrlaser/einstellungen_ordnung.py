"""Ordnung der Einstellungen (Plan „Einstellungen aufräumen“, Patrick 29.10.2026, Freigabe „Alle a“).

Bis 0.9.196 standen alle Einstellungen auf einer Seite „Vorgaben“. Jetzt hat jedes Thema eine eigene Seite neben den
passenden Stammdaten; jede Seite besteht aus Abschnitten (Karten). Interne Namen, Werte und Rechnung bleiben gleich,
Einstellung.gruppe bleibt als Suchwort erhalten. Ohne Qt, damit Tests und Anleitung die Ordnung lesen können.

Abschnitte mit experte=True sind eingeklappt (selten geänderte Toleranzen und Faktoren). Eine Einstellung darf auf
zwei Seiten stehen: die Schalter der Bereiche (funktionen.VORHANDEN) auf der Seite Funktionen und beim Thema."""
import re
from collections import namedtuple

from . import funktionen

Abschnitt = namedtuple("Abschnitt", "titel namen experte", defaults=(False,))
Seite = namedtuple("Seite", "schluessel titel hinweis abschnitte")

ALLE_PLAETZE = "Gilt für alle Arbeitsplätze (wird über den gemeinsamen Ordner abgeglichen)."


def _a(titel, namen, experte=False):
    return Abschnitt(titel, tuple(namen.split()), experte)


SEITEN = (
    Seite("e_funktionen", "Funktionen",
          "Ausgeschaltete Funktionen verschwinden aus Reitern, Menüs und Einstellungen. Gespeicherte Daten bleiben, "
          "Angebote, die sie schon nutzen, zeigen und rechnen sie weiter. " + ALLE_PLAETZE,
          (Abschnitt("Bereiche", funktionen.VORHANDEN),
           Abschnitt("Funktionen", tuple(f.name for f in funktionen.FUNKTIONEN)))),
    Seite("e_firma", "Firma", ALLE_PLAETZE,
          (_a("Briefkopf und Logo", "briefkopf_1 briefkopf_2 briefkopf_3 briefkopf_4 logo"),
           _a("Zugang", "passwort"))),
    Seite("e_arbeitsplatz", "Mein Arbeitsplatz",
          "Gilt nur für diesen Arbeitsplatz; der Abgleich mit den Kollegen ändert diese Werte nicht.",
          (_a("Benutzer", "benutzer_name benutzer_kuerzel benutzer_email benutzer_telefon"),
           _a("Ansicht", "ansicht_thema ansicht_schrift ansicht_dichte ansicht_hilfe ansicht_3d eingabe_richtung "
                         "stangenbild_popup angebote_zeitraum"),
           _a("Ordner", "ablageordner step_ordner anfrage_ordner sicherung_ordner2"),
           _a("Gemeinsamer Ordner", "teilen_ordner teilen_takt"),
           _a("E-Mail-Signatur", "anfrage_outlook_signatur anfrage_signatur"),
           _a("Leistung STEP-Messung", "step_prozesse step_cache step_cache_mb"))),
    Seite("e_ablage", "Ablage und Teilen", ALLE_PLAETZE,
          (_a("Gemeinsamer Ordner", "teilen_anfragen teilen_ablage teilen_sicherung"),
           _a("Archiv", "archiv_jahre"))),
    Seite("e_zuschlaege", "Zuschläge und Preise",
          "Vorgaben für neue Angebote; im Angebot lassen sie sich je Angebot ändern. " + ALLE_PLAETZE,
          (_a("Zuschläge und Gewinn", "zuschlag_material zuschlag_fertigung zuschlag_fremdleistung aufschlag_blech "
                                      "aufschlag_zukauf zukauf_aufschlag gewinn"),
           _a("Rüsten und Programmieren", "ruesten_abmessung ruesten_abmessung_eur ruesten_angebot_eur "
                                          "pauschale_abmessung programmierung_zeit programmierung_kontur "
                                          "pruefzeit_anbau"),
           _a("Je Angebot", "angebotsaufschlag mindestpreis handling_beistellung mwst"))),
    Seite("e_neue_angebote", "Neue Angebote", ALLE_PLAETZE,
          (_a("Grundwerte", "standard_maschine standard_stange staffeln_standard lieferzeit_art lieferzeit_wert "
                            "lieferzeit_zusatz"),
           _a("Zahlung und Gültigkeit", "skonto skonto_tage zahlungsziel gueltigkeit bedingungen"),
           _a("Nummern", "letzte_angebotsnummer ab_nummer"))),
    Seite("e_pdf_texte", "Texte im PDF", ALLE_PLAETZE,
          (_a("Angebot", "beistellung_hinweis muster_hinweis muster_frist"),
           _a("Auftragsbestätigung", "ab_text"))),
    Seite("e_automatik", "Automatik und Prüfung", ALLE_PLAETZE,
          (_a("Automatik", "auto_optimieren_bis loeschschutz"),
           _a("Prüfung und Nachfassen", "mindestmarge nachfassen_tage"))),
    Seite("e_materialanfrage", "Materialanfrage", ALLE_PLAETZE,
          (_a("E-Mail an den Lieferanten", "anfrage_betreff anfrage_text"),)),
    Seite("e_lieferlaengen", "Lieferlängen-Regeln", ALLE_PLAETZE,
          (_a("Lieferlängen vergleichen", "laenge_vergleich laenge_mindest_eur laenge_mindest_anteil "
                                          "laenge_auto_huellkreis laenge_auto"),
           _a("Zuschnitt beim Lieferanten", "zuschnitt_verlust zuschnitt_puffer zuschnitt_kosten"),
           _a("Mehrlänge des Händlers", "haendler_mehr_kurz haendler_mehr_lang haendler_mehr_grenze"))),
    Seite("e_listen", "Auswahllisten", ALLE_PLAETZE,
          (_a("Listen", "profilformen kategorien"),)),
    Seite("e_blech", "Blech-Richtpreis", ALLE_PLAETZE,
          (_a("Kosten", "blech_stundensatz blech_ruesten blech_aufschlag blech_material blech_verschnitt"),
           _a("Tafel", "blech_tafeln blech_tafel_rand blech_tafel_steg"),
           _a("Kanten", "blech_kantung blech_ruesten_kanten blech_abwicklung"),
           _a("Kantbarkeit", "blech_kant_v blech_kant_schenkel blech_kant_loch blech_kant_radius", True),
           _a("DXF-Ausgabe", "blech_dxf_layer blech_dxf_biegelinien"))),
    Seite("e_schweissen", "Schweißbaugruppen", ALLE_PLAETZE,
          (_a("Vorkalkulation", "schweiss_vk_step schweiss_vk_satz schweiss_vk_satz_nacharbeit"),
           _a("a-Maß und Spalt", "schweiss_a_regel schweiss_a_min schweiss_spalt_max"),
           _a("Gravur", "gravur_artikel gravur_schrifthoehe"))),
    Seite("e_knick_steck", "Knickrahmen und Steckverbindung", ALLE_PLAETZE,
          (_a("Knickrahmen", "knick_z knick_freistich knick_k"),
           _a("Steckverbindung", "steck_anzahl steck_nase_min steck_nase_rand steck_spiel steck_ueberstand "
                                 "steck_marke"))),
    Seite("e_step", "STEP-Import", ALLE_PLAETZE,
          (_a("Erkennung", "flach_als flachstahl_bis step_naht_spalt step_normteile step_benennung step_werkstoff "
                           "biegerohr_faktor"),
           _a("Bohrungen", "bohren_laser fliessloch_laser"),
           _a("Dateien", "step_kopieren"),
           _a("Testfunktion", "pdf_zeichnung"),
           _a("Toleranzen", "step_tol_profil step_tol_gleich step_tol_kernloch step_flach_laenge "
                            "step_gekantet_anteil step_zeitlimit", True))),
    Seite("e_dxf", "DXF-Import", ALLE_PLAETZE,
          (_a("Layer und Splitter", "dxf_weg_layer dxf_splitter"),)),
    Seite("e_lager", "Lager", ALLE_PLAETZE,
          (_a("Lager und Reststücke", "lager_aktiv reste_aktiv rest_min_laenge restwert_anteil"),)),
    Seite("e_fertigung", "Fertigung", ALLE_PLAETZE,
          (_a("Status und Rückmeldung", "fertigung_aktiv fertigung_status rueckmeldung_schritte"),
           _a("Etiketten und Reklamationen", "etikett_format reklamation_fehlerarten"))),
    Seite("e_auslastung", "Auslastung", ALLE_PLAETZE,
          (_a("Schichten und Kalender", "schicht_stunden schicht_samstag schicht_verfuegbar betriebsruhe "
                                        "auslastung_vorlauf versand_bundesland"),)),
    Seite("e_versand", "Versand und Paletten", ALLE_PLAETZE,
          (_a("Versand", "versand_aktiv palettenschein_werkstatt versand_schritte"),
           _a("Paletten", "palette_hoehe_gesamt palette_max_brutto palette_mischen palette_fuellgrad "
                          "palette_zwischenlage"))),
)
SEITE = {s.schluessel: s for s in SEITEN}

# Stehen auf keiner Seite: Frachtkosten im eigenen Reiter, csv_ordner merkt sich das Programm selbst
EIGENER_REITER = "Frachtkosten"
INTERN = {"csv_ordner"}

# Vorsilben, die der Abschnitt schon sagt („Lieferlängen: Mindestersparnis …“ → „Mindestersparnis …“)
_VORSILBE = re.compile(
    r"^(Lieferlängen|Materialpreis|STEP-Import|Schweißbaugruppen|Knickrahmen|Steckverbindung|Materialanfrage|"
    r"Angebots-PDF|Paletten|Palettenschein|Auslastung|Reststücke|Etiketten|Reklamationen|Rückmeldung per Scan|"
    r"Messung|Kantbarkeit|Kanten|Tafel|Abwicklung|DXF-Import|DXF|Gravur|Biegerohr|Nachfassen|Experte|"
    r"Angebotsliste|Auftragsbestätigung|Lieferzeit neuer Angebote|Löschschutz|Automatisch optimieren|"
    r"Angebots-Check|Standard-Staffeln|Normteile): ")
EIGENE_TITEL = {
    "pdf_zeichnung": "Neue Position „Aus PDF-Zeichnung“ (Test)",
    "versand_aktiv": "Versand und Palettenschein (Reiter Versand)",
    "fertigung_aktiv": "Fertigung (Reiter Fertigung, Status beauftragter Angebote)",
    "lager_aktiv": "Lager (Reiter Lager, Materialbestand)",
    "reste_aktiv": "Reststücke lagern und wieder einplanen",
    "auto_optimieren_bis": "Automatisch optimieren: Entwürfe bis Positionen (0 = aus)",
    "ab_nummer": "Nummer der Auftragsbestätigung",
    "ab_text": "Text über den Positionen",
    "lieferzeit_art": "Lieferzeit: Angabe als",
    "lieferzeit_wert": "Lieferzeit: Wert (Arbeitstage, Wochen, KW/Jahr oder Datum)",
    "lieferzeit_zusatz": "Lieferzeit: Freitext",
    "etikett_format": "Etiketten: Format",
    "angebote_zeitraum": "Angebotsliste: Zeitraum (Angebote mit Datum oder Änderung in den letzten Tagen)",
    "loeschschutz": "Löschschutz: optimierte Angebote nicht löschbar (immer = auch automatisch optimierte)",
    "mindestmarge": "Angebots-Check: Mindestmarge (Gewinn am Warenwert ohne Fracht und Skonto, 0 = aus)",
    "nachfassen_tage": "Nachfassen: Wiedervorlage nach Tagen ohne Entscheidung (0 = aus)",
    "staffeln_standard": "Standard-Staffeln: Faktoren auf die Bestellmenge, z. B. 1; 2; 5 (leer = aus)",
    "reklamation_fehlerarten": "Reklamationen: Fehlerarten (eine Zeile je Fehlerart)",
    "rueckmeldung_schritte": "Rückmeldung per Scan: Arbeitsschritte (eine Zeile je Schritt, der letzte = fertig)",
    "step_normteile": "Normteile: Begriffe im Bauteilnamen (mit ; getrennt)",
}


def kurztitel(e):
    """Titel einer Einstellung auf ihrer Seite: ohne Vorsilbe, die der Abschnitt schon sagt (voller Titel = Tooltip
    und Suchwort)."""
    if e.name in EIGENE_TITEL:
        return EIGENE_TITEL[e.name]
    t = _VORSILBE.sub("", e.titel)
    return t if t.startswith("a-") else t[:1].upper() + t[1:]


def lokal():
    """Einstellungen, die nur für diesen Arbeitsplatz gelten (teilen.LOKAL)."""
    from .teilen import LOKAL
    return LOKAL


def seiten_von(name):
    """Schlüssel der Seiten, auf denen eine Einstellung steht."""
    return [s.schluessel for s in SEITEN for a in s.abschnitte if name in a.namen]
