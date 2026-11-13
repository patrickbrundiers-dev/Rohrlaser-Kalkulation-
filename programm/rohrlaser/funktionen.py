"""Funktionen ein- und ausschalten (Plan „Funktionen ein/aus“, Patrick 29.10.2026, Freigabe „Alle a“).

Jede Funktion ist eine ja/nein-Einstellung (Gruppe „Funktionen“, Vorgabe ja, gilt für alle Arbeitsplätze). Ausschalten
blendet nur aus: Reiter, Menüpunkte, Knöpfe und die zugehörigen Seiten der Einstellungen. Gespeicherte Daten bleiben,
Angebote, die die Funktion schon nutzen, zeigen und rechnen sie weiter; nur die Neuanlage fehlt.

Ohne Qt, damit Rechnung, Tests und Stammdaten das Verzeichnis lesen können."""
from collections import namedtuple

# name = Einstellung, seiten = Seiten der Einstellungen (einstellungen_nav.GRUPPEN), die mit ausgeblendet werden,
# datei = Einträge im Menü Datei, reiter = Hauptreiter (Attribut des Hauptfensters)
# vorgabe = Wert für neue Dateien (fast alle „ja“; neue Zusatzfunktionen wie die CO₂-Bilanz „nein“)
Funktion = namedtuple("Funktion", "name titel text seiten datei reiter vorgabe", defaults=((), (), None, "ja"))

FUNKTIONEN = (
    Funktion("funktion_blech", "Bleche und Kantteile",
             "Neue Position „Blech / Kantteil“, Blech-Richtpreis, Blech-Werkstoffe, Blechlaser und K-Faktoren",
             seiten=("e_blech", "blech_werkstoffe", "blechlaser", "blech_kfaktoren")),
    Funktion("funktion_zukauf", "Zukaufteile",
             "Reiter Zukaufartikel, Knopf „Zukaufteile …“, neue Position „Zukaufteil“ und der Richtpreis für Dreh- und "
             "Frästeile mit seinen Einstellungen", reiter="zukauf",
             seiten=("e_drehfraes", "e_drehfraes_grenzen", "drehfraes_werkstoffe")),
    Funktion("funktion_fracht", "Frachtkosten",
             "Reiter Frachtkosten und Knopf „Fracht berechnen …“ (der Frachtbetrag von Hand bleibt)",
             reiter="fracht"),
    Funktion("funktion_schweissen", "Schweißbaugruppen",
             "Neue Position „Schweißbaugruppe“, „Schweißnaht …“ und die Seiten zum Schweißen",
             seiten=("e_schweissen", "schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren", "schweiss_regeln")),
    Funktion("funktion_knick_steck", "Knickrahmen und Steckverbindung",
             "Knöpfe „Knickrahmen“ in den Editoren und die Seite mit ihren Vorgaben", seiten=("e_knick_steck",)),
    Funktion("funktion_materialanfrage", "Materialanfrage per E-Mail",
             "„Materialanfrage (E-Mail)“ unter Ausgaben, die Seiten mit Betreff, Text und E-Mail-Vorlagen und der "
             "Reiter Materialanfragen", seiten=("e_materialanfrage", "e_mail_vorlagen"), reiter="materialanfragen"),
    Funktion("funktion_angebot_mail", "Angebot per E-Mail",
             "„Angebot per E-Mail …“ unter Ausgaben und die Seite mit Betreff und Text", seiten=("e_angebot_mail",)),
    Funktion("funktion_nachfassen", "Nachfassen und Wiedervorlage",
             "„Nachfassen vermerken …“, „Wiedervorlage …“ und die Wiedervorlage auf der Startseite"),
    Funktion("funktion_nachkalkulation", "Nachkalkulation",
             "Reiter Nachkalkulation im Angebot und „Kennwerte aus Nachkalkulation …“"),
    Funktion("funktion_auslastung", "Maschinenauslastung",
             "Datei → Maschinenauslastung und die Seite mit Schichten und Betriebsruhe",
             seiten=("e_auslastung",), datei=("Maschinenauslastung …",)),
    Funktion("funktion_reklamation", "Reklamationen",
             "„Reklamation erfassen …“ und Datei → Reklamationen", datei=("Reklamationen …",)),
    Funktion("funktion_etiketten", "Etiketten mit QR-Code", "„Etiketten mit QR-Code (PDF) …“ unter Ausgaben"),
    Funktion("funktion_ab", "Auftragsbestätigung", "„Auftragsbestätigung (PDF)“ unter Ausgaben"),
    Funktion("funktion_schnellpreis", "Schnellpreis", "Datei → Schnellpreis (Richtpreis für Telefonanfragen)",
             datei=("Schnellpreis …",)),
    Funktion("funktion_simulator", "Preis-Simulator und Varianten",
             "Datei → Preis-Simulator und „Varianten vergleichen …“", datei=("Preis-Simulator …",)),
    Funktion("funktion_vergleich", "Angebotsvergleich",
             "Datei → Angebote vergleichen … und „Vergleichen …“ in der Angebotsliste (zwei Angebote, auch aus CSV)",
             datei=("Angebote vergleichen …",)),
    Funktion("funktion_teuerung", "Teuerungszuschlag",
             "Spalten Teuerungszuschlag bei den Werkstoffen (eingetragene Zuschläge bleiben sichtbar und gelten)"),
    Funktion("funktion_muster", "Musterteile",
             "Häkchen „Muster“ in den Editoren und „Muster an/aus“ (vorhandene Muster bleiben)"),
    Funktion("funktion_abruf", "Abruf-/Rahmenangebote",
             "Haken „Abruf-/Rahmenangebot“ im Angebotskopf (vorhandene Abruf-Angebote bleiben)"),
    # Vorschlag K3 (Patrick 02.11.2026 „K3b“): nur intern, Vorgabe aus
    Funktion("funktion_co2", "CO₂-Bilanz (intern)",
             "CO₂ je Teil im Preisaufbau und im Kalkulations-PDF, Spalte CO₂ bei den Werkstoffen", vorgabe="nein"),
    # Intelligenz einzeln schaltbar (Patrick 09./10.11.2026, Plan F5 „Alle Empfehlungen“: vier Schalter, Vorgabe an).
    # Aus = keine Hinweise und kein Dazulernen; Gelerntes bleibt gespeichert und gilt wieder nach dem Einschalten.
    Funktion("funktion_lernen", "Lernen und selbst anwenden",
             "Das Programm lernt aus ✓/✗ bei Zusatzarbeit-Vorschlägen je Kunde und wendet Gelerntes beim Import "
             "selbst an (auch Werte aus Wiederholteilen); Hinweis auf Kennwert-Vorschläge auf der Startseite"),
    Funktion("funktion_regelvorschlaege", "Vorschläge aus Handeinträgen",
             "Erkennungswörter und Arbeitsgang-Regeln aus immer wieder von Hand eingetragenen Zusatzarbeiten, "
             "Kundenvorgaben aus gleichen Kopfwerten, Programmierzeit-Vorgabe (Lernzentrale, Startseite)"),
    Funktion("funktion_preis_hinweise", "Preis- und Termin-Hinweise",
             "Trefferquote und Wettbewerbsabstand unter den Preisen, Preis je kg gegen Teile ähnlicher Länge und "
             "Lieferzeit gegen die echte Durchlaufzeit im Angebots-Check (die grobe €/kg-Prüfung bleibt); "
             "Reklamationen bei Wiederholteilen, Nachkalkulation ähnlicher Aufträge, Verlustmuster"),
    Funktion("funktion_chance", "Auftragschance",
             "Geschätzte Auftragschance in der Wiedervorlage (die lohnendsten Angebote zuerst) und als Ampel-Spalte "
             "in der Angebotsliste"),
)
LERNEN, REGELVORSCHLAEGE, PREIS_HINWEISE, CHANCE = ("funktion_lernen", "funktion_regelvorschlaege",
                                                    "funktion_preis_hinweise", "funktion_chance")
INTELLIGENZ = (LERNEN, REGELVORSCHLAEGE, PREIS_HINWEISE, CHANCE)     # eigener Abschnitt auf der Seite Funktionen
# Menü-Einträge, die sichtbar bleiben, solange EINE der Funktionen an ist
DATEI_ODER = {"Lernzentrale …": (LERNEN, REGELVORSCHLAEGE)}
FUNKTION = {f.name: f for f in FUNKTIONEN}

# Schon vorhandene Schalter, die die Seite Funktionen zusätzlich zeigt (Frage 5a: auch am alten Platz)
VORHANDEN = ("versand_aktiv", "fertigung_aktiv", "lager_aktiv", "reste_aktiv", "pdf_zeichnung")

_db = None


def db_setzen(db):
    """Datenbank, aus der an() ohne db liest (das Hauptfenster beim Start)."""
    global _db
    _db = db


def an(name, db=None):
    """Funktion eingeschaltet? Ohne Datenbank (Tests, Dialoge allein) immer ja."""
    d = db if db is not None else _db
    if d is None:
        return True
    try:
        return d.einstellung(name) != "nein"
    except Exception:           # geschlossene Datenbank (Programmende): nichts ausblenden
        return True


def seite_an(schluessel, db=None):
    """Seite der Einstellungen sichtbar? Aus, wenn eine ausgeschaltete Funktion sie mitnimmt."""
    return all(an(f.name, db) for f in FUNKTIONEN if schluessel in f.seiten)


def datei_an(text, db=None):
    """Eintrag im Menü Datei sichtbar?"""
    if text in DATEI_ODER:
        return any(an(n, db) for n in DATEI_ODER[text])
    return all(an(f.name, db) for f in FUNKTIONEN if text in f.datei)
