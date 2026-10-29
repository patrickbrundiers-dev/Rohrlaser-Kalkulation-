"""Stammdaten der Frachtkosten: Länder, Frachtzonen, PLZ-Zuordnungen, Dienstleister, Tarife mit Preisstaffeln,
Ladehilfsmittel, Zuschläge, Dieselpreise, Währungen; dazu Beispieldaten und CSV-Import/-Export der PLZ.

Die Tabellen werden wie die übrigen Stammdaten mit Feld/Tabelle beschrieben (Schema, Anzeige und Prüfung aus
einer Quelle). Alle Beispielwerte sind als BEISPIEL gekennzeichnet und keine echten Tarife oder Zuschläge.
"""
import csv
import io
import re

from .stammdaten import Feld, Tabelle, zahl_als_text

BEISPIEL = "BEISPIEL – kein echter Tarif, bitte durch eigene Werte ersetzen"

ZONENARTEN = ("normal", "Insel", "Randgebiet", "Sondergebiet", "Ausland")
RICHTUNGEN = ("beide", "Empfang", "Versand")
TARIFARTEN = ("Standardtarif", "Rahmenvertrag", "Sondertarif", "Kundentarif", "interner Verrechnungstarif")
MODELLE = ("Gewichtstarif", "Palettentarif", "Gitterboxtarif", "Kombinationstarif", "Individueller Tarif")
BEZUG = ("Sendung", "kg", "100 kg", "Ladungsträger", "Stellplatz", "km", "Lademeter")
PREISARTEN = ("Festpreis", "je Einheit")
LHT_ARTEN = ("Europalette", "Einwegpalette", "Industriepalette", "Gitterbox", "Sonderpalette", "Langgut",
             "Sonderladung", "Karton")
LIEFERBEDINGUNGEN = ("frei Haus", "frei Frachtführer", "unfrei", "ab Werk", "Abholung")
# Lieferbedingungen, bei denen der Kunde die Fracht trägt: Frachtkosten 0 mit Hinweis
OHNE_FRACHT = ("unfrei", "ab Werk", "Abholung")
ZUSCHLAGTYPEN = ("Diesel", "Maut", "Energie", "Gefahrgut", "Langgut / Überlänge", "Sperrgut",
                 "Insel- und Randgebiet", "Avisierung", "Hebebühne", "Express", "Fixtermin", "Mindermenge",
                 "Wartezeit", "Be- und Entladung", "Sonderhandling", "sonstiger Zuschlag")
BERECHNUNGEN = ("%", "€ je Sendung", "€ je kg", "€ je 100 kg", "€ je Ladungsträger", "€ je Stellplatz",
                "€ je Stunde", "Dieselstaffel")
BASEN = ("Grundfracht", "Grundfracht + Leistungszuschläge", "gewählte Zuschläge")
BEDINGUNGEN = ("immer", "nur wenn gewählt", "Gewicht unter", "Gewicht über", "Gewicht je Stellplatz über",
               "Teillänge über", "Zonenart Insel/Randgebiet/Sondergebiet")

# feste Auswahllisten (stammdaten.Kontext.gruppiert fragt hier nach, wenn eine Quelle dort fehlt)
AUSWAHL_FEST = {"zonenart": ZONENARTEN, "richtung": RICHTUNGEN, "tarifart": TARIFARTEN, "modell": MODELLE,
                "bezug": BEZUG, "preisart": PREISARTEN, "lhtart": LHT_ARTEN,
                "lieferbedingung": LIEFERBEDINGUNGEN, "zuschlagtyp": ZUSCHLAGTYPEN, "berechnung": BERECHNUNGEN,
                "zuschlagbasis": BASEN, "bedingung": BEDINGUNGEN}

LAND_MUSTER = (r"^[A-Z]{2}$", "Land als zweistelliger Ländercode in Großbuchstaben, z. B. DE, AT, CH")
PLZ_MUSTER = (r"^[0-9A-Z]+\*?$", "PLZ nur aus Ziffern bzw. Buchstaben, Präfix mit *, z. B. 80331 oder 80*")
LISTE_MUSTER = (r"^[^;]+$", "mehrere Werte mit Komma trennen, z. B. Z1, Z2")


def _plz_pruefung(z, k):
    von, bis = z.get("plz_von"), z.get("plz_bis")
    if von and bis:
        if von.endswith("*") or bis.endswith("*"):
            return "FEHLER: Präfix (mit *) nur in PLZ von, PLZ bis dann leer lassen"
        if len(von) != len(bis):
            return "FEHLER: PLZ von und PLZ bis brauchen gleich viele Stellen"
        if plz_schluessel(bis) < plz_schluessel(von):
            return "FEHLER: PLZ bis liegt vor PLZ von"
    laenge = (k.listen.get("plz_laenge") or {}).get(z.get("land"))
    kurz = von and von.isdigit() and len(von) <= 3 and not bis      # '25' gilt wie '25*' (PLZ-Bereich)
    if laenge and von and not von.endswith("*") and not kurz and len(von) != laenge:
        return f"WARNUNG: PLZ hat in {z.get('land')} {laenge} Stellen"
    return None


def _tarif_pruefung(z, k):
    if z.get("gueltig_ab") and z.get("gueltig_bis") and z["gueltig_bis"] < z["gueltig_ab"]:
        return "FEHLER: Gültig bis liegt vor Gültig ab"
    if z.get("tarifart") == "Kundentarif" and not z.get("kundennr"):
        return "FEHLER: Kundentarif ohne Kundennummer"
    if "BEISPIEL" in (z.get("bemerkung") or "") + (z.get("tarif_id") or ""):
        return "WARNUNG: Beispieltarif, keine echten Preise"
    return None


def _preis_pruefung(z, k):
    if z.get("preis") is None:
        return "WARNUNG: Preis leer = individuelle Berechnung (das Programm rechnet diese Stufe nicht)"
    return None


def _lht_pruefung(z, k):
    if z.get("art") not in ("Sonderladung",) and not z.get("nutzlast"):
        return "WARNUNG: Nutzlast fehlt (Packvorschlag rechnet 1 Ladungsträger)"
    if z.get("stapelbar") == "ja" and not z.get("stapelfaktor"):
        return "WARNUNG: stapelbar ohne Stapelfaktor (zählt wie nicht stapelbar)"
    return None


def _zuschlag_pruefung(z, k):
    if z.get("berechnung") == "%" and not z.get("basis"):
        return "FEHLER: Prozentzuschlag braucht eine Basis"
    if z.get("basis") == "gewählte Zuschläge" and not z.get("basis_liste"):
        return "FEHLER: Basis 'gewählte Zuschläge' ohne Zuschläge"
    if z.get("zuschlag_id") and z.get("zuschlag_id") in liste(z.get("basis_liste")):
        return "FEHLER: Zuschlag kann nicht auf sich selbst rechnen"
    if z.get("bedingung") in ("Gewicht unter", "Gewicht über", "Gewicht je Stellplatz über", "Teillänge über") and \
            z.get("grenze") is None:
        return "FEHLER: Bedingung braucht eine Grenze"
    if z.get("mindest") is not None and z.get("hoechst") is not None and z["hoechst"] < z["mindest"]:
        return "FEHLER: Höchstbetrag kleiner als Mindestbetrag"
    if z.get("gueltig_ab") and z.get("gueltig_bis") and z["gueltig_bis"] < z["gueltig_ab"]:
        return "FEHLER: Gültig bis liegt vor Gültig ab"
    return None


LAENDER = Tabelle(
    "fracht_laender", "Länder",
    (Feld("land", "Land", pflicht=True, muster=LAND_MUSTER, breite=60),
     Feld("bezeichnung", "Bezeichnung", breite=150),
     Feld("plz_laenge", "PLZ-Stellen", "ganz", 2, 10, breite=70),
     Feld("waehrung", "Währung", breite=70),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("land",),
    "Länder und Regionen für Frachtzonen und Tarife. Währung leer = EUR. Aktiv leer = ja.")

ZONEN = Tabelle(
    "fracht_zonen", "Frachtzonen",
    (Feld("zone_id", "Zone", pflicht=True, breite=80),
     Feld("bezeichnung", "Bezeichnung", pflicht=True, breite=160),
     Feld("land", "Land", "auswahl", auswahl="land", pflicht=True, breite=60),
     Feld("art", "Zonenart", "auswahl", auswahl="zonenart", breite=100),
     Feld("standard", "Standardzone", "auswahl", auswahl="janein", breite=80),
     Feld("km", "Entfernung [km]", "zahl", 0, 100000, stellen=0, breite=80),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("zone_id",),
    "Frachtzonen mit frei wählbarer Bezeichnung. Die Standardzone gilt für PLZ des Landes ohne Zuordnung (mit "
    "Warnung). Entfernung: für Tarife mit Preisen je km. Inaktive Zonen werden nicht mehr zugeordnet.",
    pruefung=lambda z, k: "WARNUNG: inaktiv" if z.get("aktiv") == "nein" else None)

PLZ = Tabelle(
    "fracht_plz", "PLZ-Zuordnungen",
    (Feld("land", "Land", "auswahl", auswahl="land", pflicht=True, breite=60),
     Feld("plz_von", "PLZ von", pflicht=True, muster=PLZ_MUSTER, breite=80),
     Feld("plz_bis", "PLZ bis", muster=PLZ_MUSTER, breite=80),
     Feld("zone_id", "Zone", "auswahl", auswahl="zone", pflicht=True, breite=80),
     Feld("richtung", "Richtung", "auswahl", auswahl="richtung", breite=80),
     Feld("dienstleister", "Dienstleister", "auswahl", auswahl="dienstleister", breite=110),
     Feld("kundennr", "Kundennummer", "auswahl", auswahl="kunde", breite=100),
     Feld("prioritaet", "Priorität (1 = zuerst)", "ganz", 1, 999, breite=75),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("land", "plz_von", "plz_bis", "richtung", "dienstleister", "kundennr"),
    "Je Zeile eine PLZ (PLZ von), ein Bereich (PLZ von bis PLZ bis) oder ein Präfix (z. B. 80*). Treffen mehrere "
    "Zeilen zu, gilt: Kunde + Dienstleister vor Kunde vor Dienstleister vor allgemein; dann einzelne PLZ vor dem "
    "engsten Bereich vor dem kürzesten Präfix; dann die kleinere Priorität. Bleibt es gleich, meldet das Programm "
    "'mehrdeutig'. Richtung leer = beide.",
    pruefung=_plz_pruefung)

DIENSTLEISTER = Tabelle(
    "fracht_dienstleister", "Dienstleister",
    (Feld("dienstleister_id", "Dienstleister", pflicht=True, breite=110),
     Feld("name", "Name", breite=180),
     Feld("versandarten", "Versandarten", muster=LISTE_MUSTER, breite=200),
     Feld("kundennr_dl", "Unsere Kundennummer beim Dienstleister", breite=120),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("dienstleister_id",),
    "Frachtführer und Paketdienste. Versandarten mit Komma trennen (z. B. Stückgut, Palettenversand, Paket); sie "
    "erscheinen im Rechner zur Auswahl.")

TARIFE = Tabelle(
    "fracht_tarife", "Tarife",
    (Feld("tarif_id", "Tarif", pflicht=True, breite=160),
     Feld("bezeichnung", "Bezeichnung", breite=170),
     Feld("dienstleister", "Dienstleister", "auswahl", auswahl="dienstleister", breite=110),
     Feld("tarifart", "Tarifart", "auswahl", auswahl="tarifart", breite=120),
     Feld("modell", "Tarifmodell", "auswahl", auswahl="modell", pflicht=True, breite=120),
     Feld("versandart", "Versandart", breite=110),
     Feld("laender", "Länder", muster=LISTE_MUSTER, breite=80),
     Feld("zonen", "Zonen", muster=LISTE_MUSTER, breite=110),
     Feld("kundennr", "Kundennummer", "auswahl", auswahl="kunde", breite=100),
     Feld("gueltig_ab", "Gültig ab", "datum", breite=85),
     Feld("gueltig_bis", "Gültig bis", "datum", breite=85),
     Feld("waehrung", "Währung", breite=65),
     Feld("mindestfracht", "Mindestfracht", "zahl", 0, 1000000, stellen=2, breite=85),
     Feld("rabatt", "Rabatt [%]", "zahl", 0, 100, stellen=1, breite=65),
     Feld("faktor_m3", "Frachtpfl. Gewicht je m³ [kg]", "zahl", 0, 100000, stellen=0, breite=95),
     Feld("faktor_stellplatz", "Frachtpfl. Gewicht je Stellplatz [kg]", "zahl", 0, 100000, stellen=0, breite=95),
     Feld("faktor_ldm", "Frachtpfl. Gewicht je Lademeter [kg]", "zahl", 0, 100000, stellen=0, breite=95),
     Feld("rundung_kg", "Gewicht aufrunden auf [kg]", "zahl", 0, 10000, stellen=1, breite=85),
     Feld("prioritaet", "Priorität (1 = zuerst)", "ganz", 1, 999, breite=75),
     Feld("version", "Version", breite=70),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("tarif_id",),
    "Tarifkopf: wofür der Tarif gilt (Dienstleister, Versandart, Länder, Zonen, Kunde, Zeitraum) und wie er "
    "rechnet (Tarifmodell, Mindestfracht, Rabatt, frachtpflichtiges Gewicht). Leere Länder, Zonen, Versandart "
    "= alle. Die Preise stehen darunter in den Preisstaffeln. Tarifart leer = Standardtarif.",
    pruefung=_tarif_pruefung)

PREISE = Tabelle(
    "fracht_preise", "Preisstaffeln",
    (Feld("tarif_id", "Tarif", "auswahl", auswahl="tarif", pflicht=True, breite=160),
     Feld("zone_id", "Zone", "auswahl", auswahl="zone", breite=80),
     Feld("bezug", "Bezugseinheit", "auswahl", auswahl="bezug", pflicht=True, breite=100),
     Feld("lht_art", "Ladehilfsmittel", "auswahl", auswahl="lhtart_id", breite=110),
     Feld("bis", "bis Menge", "zahl", 0, 100000000, stellen=2, breite=80),
     Feld("preis", "Preis", "zahl", 0, 10000000, stellen=2, breite=80),
     Feld("preisart", "Preisart", "auswahl", auswahl="preisart", breite=90),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("tarif_id", "zone_id", "bezug", "lht_art", "bis"),
    "Je Zeile eine Stufe: gilt bis zur Menge 'bis Menge' in der Bezugseinheit (leer = ohne Obergrenze; bei kg und "
    "100 kg ist 'bis Menge' immer in kg, beide bilden eine Gewichtsstaffel). Preisart "
    "Festpreis = Preis der ganzen Stufe, je Einheit = Preis × Menge. Zone leer = alle Zonen, Ladehilfsmittel "
    "leer = alle übrigen; statt der Art kann auch ein einzelnes Ladehilfsmittel stehen (z. B. Karton K-M), es geht dann der Art vor. Preis leer = individuelle Berechnung. Preisart leer = Festpreis.",
    pruefung=_preis_pruefung)

LHT = Tabelle(
    "fracht_lht", "Ladehilfsmittel",
    (Feld("lht_id", "Ladehilfsmittel", pflicht=True, breite=120),
     Feld("bezeichnung", "Bezeichnung", breite=170),
     Feld("art", "Art", "auswahl", auswahl="lhtart", pflicht=True, breite=110),
     Feld("laenge", "Länge [mm]", "ganz", 0, 30000, breite=70),
     Feld("breite", "Breite [mm]", "ganz", 0, 5000, breite=70),
     Feld("hoehe", "Höhe [mm]", "ganz", 0, 5000, breite=70),
     Feld("eigengewicht", "Eigengewicht [kg]", "zahl", 0, 10000, stellen=1, breite=80),
     Feld("nutzlast", "Nutzlast [kg]", "zahl", 0, 100000, stellen=1, breite=75),
     Feld("max_laenge", "Max. Teillänge [mm]", "ganz", 0, 30000, breite=85),
     Feld("stapelbar", "Stapelbar", "auswahl", auswahl="janein", breite=65),
     Feld("stapelfaktor", "Stapelfaktor", "ganz", 1, 10, breite=65),
     Feld("stellplaetze", "Stellplätze je Stück", "zahl", 0, 100, stellen=2, breite=80),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("lht_id",),
    "Ladungsträger mit Maßen, Eigengewicht und Nutzlast. Max. Teillänge: längere Teile kommen im Packvorschlag "
    "auf Langgut; ist sie größer als die Länge, dürfen Teile längs überstehen, quer nie. Karton: Maße = Innenmaße, "
    "Nutzlast = Gewichtsklasse des Pakets − Eigengewicht. Stapelfaktor = wie viele übereinander einen Stellplatz teilen. Stellplätze je Stück leer = 1.",
    pruefung=_lht_pruefung)

ZUSCHLAEGE = Tabelle(
    "fracht_zuschlaege", "Zuschläge",
    (Feld("zuschlag_id", "Zuschlag", pflicht=True, breite=110),
     Feld("bezeichnung", "Bezeichnung", breite=170),
     Feld("typ", "Typ", "auswahl", auswahl="zuschlagtyp", pflicht=True, breite=120),
     Feld("berechnung", "Berechnungsart", "auswahl", auswahl="berechnung", pflicht=True, breite=110),
     Feld("basis", "Berechnungsgrundlage", "auswahl", auswahl="zuschlagbasis", breite=150),
     Feld("basis_liste", "Grundlage Zuschläge", muster=LISTE_MUSTER, breite=120),
     Feld("wert", "Wert [% bzw. €]", "zahl", -100000, 100000, stellen=2, breite=80),
     Feld("mindest", "Mindestbetrag [€]", "zahl", 0, 1000000, stellen=2, breite=80),
     Feld("hoechst", "Höchstbetrag [€]", "zahl", 0, 1000000, stellen=2, breite=80),
     Feld("gueltig_ab", "Gültig ab", "datum", breite=85),
     Feld("gueltig_bis", "Gültig bis", "datum", breite=85),
     Feld("laender", "Länder", muster=LISTE_MUSTER, breite=80),
     Feld("zonen", "Zonen", muster=LISTE_MUSTER, breite=100),
     Feld("tarife", "Tarife", muster=LISTE_MUSTER, breite=110),
     Feld("dienstleister", "Dienstleister", "auswahl", auswahl="dienstleister", breite=110),
     Feld("kundennr", "Kundennummer", "auswahl", auswahl="kunde", breite=100),
     Feld("bedingung", "Bedingung", "auswahl", auswahl="bedingung", breite=130),
     Feld("grenze", "Grenze [kg bzw. mm]", "zahl", 0, 1000000, stellen=1, breite=80),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("zuschlag_id",),
    "Zuschläge mit Berechnungsart und Grundlage. Prozentzuschläge rechnen nach den Zuschlägen in Euro auf ihre "
    "Grundlage, nie auf sich selbst. Leere Länder, Zonen, Tarife, Dienstleister, Kunde = alle. Bedingung leer = "
    "immer. Treffen zwei Zuschläge desselben Typs zu, gilt der speziellere (Kunde vor Dienstleister vor Tarif vor "
    "allgemein). Dieselstaffel: Zuschlag aus der Tabelle Dieselstaffel zum Dieselpreis am Datum.",
    pruefung=_zuschlag_pruefung)

DIESELPREISE = Tabelle(
    "fracht_dieselpreise", "Dieselpreise",
    (Feld("datum", "Gültig ab", "datum", pflicht=True, breite=90),
     Feld("preis", "Dieselpreis [€/l]", "zahl", 0, 100, stellen=3, breite=90),
     Feld("quelle", "Quelle", breite=200),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("datum",),
    "Dieselpreise von Hand pflegen (oder per CSV einlesen). Es gilt der letzte Preis bis zum Datum der Kalkulation. "
    "Das Programm holt keine Werte aus dem Internet.")

DIESELSTAFFEL = Tabelle(
    "fracht_dieselstaffel", "Dieselstaffel",
    (Feld("zuschlag_id", "Zuschlag", "auswahl", auswahl="zuschlag", pflicht=True, breite=110),
     Feld("preis_ab", "Dieselpreis ab [€/l]", "zahl", 0, 100, stellen=3, pflicht=True, breite=90),
     Feld("wert", "Zuschlag [% bzw. €]", "zahl", -1000, 100000, stellen=2, breite=90),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("zuschlag_id", "preis_ab"),
    "Schwellen eines Dieselzuschlags mit Berechnungsart Dieselstaffel: es gilt die höchste Schwelle, die der "
    "Dieselpreis erreicht. Der Wert ist % auf die Grundlage des Zuschlags.")

WAEHRUNGEN = Tabelle(
    "fracht_waehrungen", "Währungen",
    (Feld("waehrung", "Währung", pflicht=True, breite=70),
     Feld("kurs", "Kurs (1 Einheit = … €)", "zahl", 0, 100000, stellen=4, breite=90),
     Feld("stand", "Stand", "datum", breite=90),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("waehrung",),
    "Umrechnungskurse für Tarife in fremder Währung, von Hand gepflegt. EUR braucht keinen Eintrag.")

FRACHT_TABELLEN = (LAENDER, ZONEN, PLZ, DIENSTLEISTER, TARIFE, PREISE, LHT, ZUSCHLAEGE, DIESELPREISE, DIESELSTAFFEL,
                   WAEHRUNGEN)
FRACHT_TABELLE = {t.name: t for t in FRACHT_TABELLEN}
# Kurznamen für den Rechenkern (fracht.py)
KURZ = {"fracht_laender": "laender", "fracht_zonen": "zonen", "fracht_plz": "plz",
        "fracht_dienstleister": "dienstleister", "fracht_tarife": "tarife", "fracht_preise": "preise",
        "fracht_lht": "lht", "fracht_zuschlaege": "zuschlaege", "fracht_dieselpreise": "dieselpreise",
        "fracht_dieselstaffel": "dieselstaffel", "fracht_waehrungen": "waehrungen"}

FRACHT_VERWEISE = {
    ("fracht_laender", "land"): (("fracht_zonen", "land"), ("fracht_plz", "land")),
    ("fracht_zonen", "zone_id"): (("fracht_plz", "zone_id"), ("fracht_preise", "zone_id")),
    ("fracht_dienstleister", "dienstleister_id"): (("fracht_plz", "dienstleister"), ("fracht_tarife", "dienstleister"),
                                                   ("fracht_zuschlaege", "dienstleister")),
    ("fracht_tarife", "tarif_id"): (("fracht_preise", "tarif_id"),),
    ("fracht_zuschlaege", "zuschlag_id"): (("fracht_dieselstaffel", "zuschlag_id"),),
}


def liste(text):
    """'Z1, Z2;Z3' -> ['Z1', 'Z2', 'Z3']"""
    return [t.strip() for t in re.split(r"[,;\n]", text or "") if t.strip()]


def plz_schluessel(plz):
    """Vergleichswert einer PLZ: Ziffernfolgen als Zahl mit Stellenzahl (führende Nullen zählen), sonst Text."""
    t = str(plz or "").strip().upper().replace(" ", "")
    return (len(t), int(t)) if t.isdigit() else (len(t), t)


def listen_aus(daten, kunden=()):
    """Auswahllisten aus den Fracht-Stammdaten {Kurzname: [Zeilen]} für Kontext.listen."""
    def ids(tabelle, feld):
        return sorted({z[feld] for z in daten.get(tabelle, []) if z.get(feld)})
    return {"land": ids("laender", "land"), "zone": ids("zonen", "zone_id"),
            "dienstleister": ids("dienstleister", "dienstleister_id"), "tarif": ids("tarife", "tarif_id"),
            "lht": ids("lht", "lht_id"), "zuschlag": ids("zuschlaege", "zuschlag_id"),
            "lhtart_id": list(LHT_ARTEN) + [i for i in ids("lht", "lht_id") if i not in LHT_ARTEN],
            "kunde": sorted({k["kundennr"] for k in kunden if k.get("kundennr")}),
            "plz_laenge": {z["land"]: z["plz_laenge"] for z in daten.get("laender", [])
                           if z.get("land") and z.get("plz_laenge")}}


# ------------------------------------------------------------------ Beispieldaten
def beispieldaten():
    """Beispielwerte (BEISPIEL, keine echten Tarife): Länder, fünf Zonen, PLZ-Bereiche, ein Dienstleister,
    ein Gewichts- und ein Palettentarif mit Preisen je Zone, Ladehilfsmittel, Zuschläge; keine Dieselpreise und
    keine Währungskurse (die pflegt man selbst)."""
    def zeilen(t, werte):
        return [{f.name: (w[i] if i < len(w) else None) for i, f in enumerate(t.felder)} for w in werte]
    b = BEISPIEL
    laender = [("DE", "Deutschland", 5, "EUR", "ja", b), ("AT", "Österreich", 4, "EUR", "ja", b),
               ("CH", "Schweiz", 4, "CHF", "ja", b)]
    zonen = [("Z1", "Nahbereich", "DE", "normal", "nein", 50, "ja", b),
             ("Z2", "Regional", "DE", "normal", "nein", 150, "ja", b),
             ("Z3", "National", "DE", "normal", "ja", 400, "ja", b),
             ("Z4", "Fernbereich", "DE", "normal", "nein", 650, "ja", b),
             ("Z5", "Sondergebiet", "DE", "Insel", "nein", 600, "ja", b),
             ("AT1", "Österreich", "AT", "Ausland", "ja", 700, "ja", b)]
    plz = [("DE", "40000", "42999", "Z1", None, None, None, None, b),
           ("DE", "44000", "59999", "Z2", None, None, None, None, b),
           ("DE", "01000", "19999", "Z4", None, None, None, None, b),
           ("DE", "80000", "99999", "Z4", None, None, None, None, b),
           ("DE", "25938", "25999", "Z5", None, None, None, None, "BEISPIEL Inseln (Grenzen prüfen)"),
           ("DE", "18565", None, "Z5", None, None, None, None, "BEISPIEL Insel (Grenzen prüfen)"),
           ("AT", "1*", None, "AT1", None, None, None, None, b)]
    dl = [("SPED-BSP", "Beispiel-Spedition", "Stückgut, Palettenversand", None, "ja", b)]
    tarife = [("BEISPIEL-STUECKGUT", "Stückgut nach Gewicht", "SPED-BSP", "Standardtarif", "Gewichtstarif",
               "Stückgut", "DE", None, None, "2026-01-01", None, "EUR", 35.0, None, 250, None, None, 1.0, 10,
               "2026-1", "ja", b),
              ("BEISPIEL-PALETTE", "Palettenversand", "SPED-BSP", "Standardtarif", "Palettentarif",
               "Palettenversand", "DE", None, None, "2026-01-01", None, "EUR", 45.0, None, None, None, None, None, 10, "2026-1", "ja", b)]
    preise = []
    for zone, f in (("Z1", 1.0), ("Z2", 1.25), ("Z3", 1.6), ("Z4", 1.9), ("Z5", 2.6)):
        for bis, p in ((100, 38), (250, 55), (500, 85), (1000, 140)):
            preise.append(("BEISPIEL-STUECKGUT", zone, "kg", None, bis, round(p * f, 2), "Festpreis", b))
        preise.append(("BEISPIEL-STUECKGUT", zone, "100 kg", None, None, round(14.5 * f, 2), "je Einheit", b))
        for bis, p in ((1, 60), (3, 52), (6, 45)):
            preise.append(("BEISPIEL-PALETTE", zone, "Stellplatz", None, bis, round(p * f, 2), "je Einheit", b))
        preise.append(("BEISPIEL-PALETTE", zone, "Stellplatz", None, None, None, "je Einheit",
                       "BEISPIEL: mehr als 6 Stellplätze individuell"))
        for bis, p in ((1, 70), (3, 62), (6, 55)):
            preise.append(("BEISPIEL-PALETTE", zone, "Ladungsträger", "Gitterbox", bis, round(p * f, 2),
                           "je Einheit", b))
    lht = [("EUR", "Europalette 1200 × 800", "Europalette", 1200, 800, 144, 25, 1500, 1400, "nein", None, 1, "ja", b),
           ("EW", "Einwegpalette 1200 × 800", "Einwegpalette", 1200, 800, 140, 15, 1000, 1400, "nein", None, 1, "ja",
            b),
           ("IND", "Industriepalette 1200 × 1000", "Industriepalette", 1200, 1000, 144, 30, 1500, 1400, "nein", None,
            1.25, "ja", b),
           ("GB", "Gitterbox 1240 × 835 × 970", "Gitterbox", 1240, 835, 970, 85, 1500, 1200, "ja", 4, 1, "ja", b),
           ("SOND", "Sonderpalette 2000 × 1000", "Sonderpalette", 2000, 1000, 150, 40, 1500, 2400, "nein", None, 2.0,
            "ja", b),
           ("LG", "Langgut bis 6,5 m", "Langgut", 6500, 800, 300, 30, 2000, 6500, "nein", None, 3.0, "ja", b),
           ("SL", "Sonderladung (Maße je Sendung)", "Sonderladung", None, None, None, None, None, None, "nein", None,
            None, "ja", b)]
    zus = [("DIESEL-BSP", "Dieselzuschlag", "Diesel", "%", "Grundfracht", None, 12.0, None, None, None, None, None,
            None, None, "SPED-BSP", None, "immer", None, "ja", b),
           ("DIESEL-STAFFEL-BSP", "Dieselzuschlag nach Dieselpreis", "Diesel", "Dieselstaffel", "Grundfracht", None,
            None, None, None, None, None, None, None, None, None, None, "immer", None, "nein",
            "BEISPIEL inaktiv: Dieselpreise selbst pflegen, dann aktivieren"),
           ("MAUT-BSP", "Mautzuschlag", "Maut", "€ je 100 kg", None, None, 1.0, 2.0, None, None, None, "DE", None,
            None, None, None, "immer", None, "ja", b),
           ("AVIS-BSP", "Avisierung", "Avisierung", "€ je Sendung", None, None, 8.0, None, None, None, None, None, None,
            None, None, None, "nur wenn gewählt", None, "ja", b),
           ("HEBE-BSP", "Hebebühne", "Hebebühne", "€ je Sendung", None, None, 25.0, None, None, None, None, None, None,
            None, None, None, "nur wenn gewählt", None, "ja", b),
           ("WARTE-BSP", "Wartezeit", "Wartezeit", "€ je Stunde", None, None, 45.0, None, None, None, None, None, None,
            None, None, None, "nur wenn gewählt", None, "ja", b),
           ("LANG-BSP", "Langgut / Überlänge", "Langgut / Überlänge", "€ je Sendung", None, None, 15.0, None, None,
            None, None, None, None, None, None, None, "Teillänge über", 3000, "ja", b),
           ("INSEL-BSP", "Inselzuschlag", "Insel- und Randgebiet", "€ je Sendung", None, None, 30.0, None, None, None,
            None, None, None, None, None, None, "Zonenart Insel/Randgebiet/Sondergebiet", None, "ja", b),
           ("MINDER-BSP", "Mindermengenzuschlag", "Mindermenge", "€ je Sendung", None, None, 10.0, None, None, None,
            None, None, None, None, None, None, "Gewicht unter", 30, "ja", b)]
    staffel = [("DIESEL-STAFFEL-BSP", 1.40, 8.0, b), ("DIESEL-STAFFEL-BSP", 1.60, 10.0, b),
               ("DIESEL-STAFFEL-BSP", 1.80, 12.0, b)]
    return {"fracht_laender": zeilen(LAENDER, laender), "fracht_zonen": zeilen(ZONEN, zonen),
            "fracht_plz": zeilen(PLZ, plz), "fracht_dienstleister": zeilen(DIENSTLEISTER, dl),
            "fracht_tarife": zeilen(TARIFE, tarife), "fracht_preise": zeilen(PREISE, preise),
            "fracht_lht": zeilen(LHT, lht), "fracht_zuschlaege": zeilen(ZUSCHLAEGE, zus),
            "fracht_dieselstaffel": zeilen(DIESELSTAFFEL, staffel),
            "fracht_waehrungen": zeilen(WAEHRUNGEN, [("CHF", None, None, "BEISPIEL: Kurs selbst eintragen")])}


# ------------------------------------------------------------------ CSV
CSV_PLZ = ("land", "plz_von", "plz_bis", "zone_id", "richtung", "dienstleister", "kundennr", "prioritaet",
           "bemerkung")


def plz_csv(zeilen):
    """PLZ-Zuordnungen als CSV (Semikolon, UTF-8 mit BOM für Excel, Kopfzeile mit den Spaltentiteln)."""
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow([PLZ.feld(n).titel for n in CSV_PLZ])
    for z in zeilen:
        w.writerow(["" if z.get(n) is None else (zahl_als_text(z[n]) if isinstance(z[n], (int, float)) else z[n])
                    for n in CSV_PLZ])
    return "﻿" + puffer.getvalue()


def plz_csv_lesen(text, zonen, laender):
    """CSV der PLZ-Zuordnungen lesen und prüfen. zonen/laender: bekannte IDs. Ergebnis: (zeilen, fehler);
    fehler = ['Zeile 3: …']. Fehlerhafte Zeilen werden nicht übernommen."""
    from .stammdaten import wert_aus_text
    text = text.lstrip("﻿")
    probe = text.splitlines()[0] if text.strip() else ""
    trenner = ";" if probe.count(";") >= probe.count(",") else ","
    leser = csv.reader(io.StringIO(text, newline=""), delimiter=trenner)
    titel = {PLZ.feld(n).titel.lower(): n for n in CSV_PLZ} | {n: n for n in CSV_PLZ}
    zeilen, fehler, spalten = [], [], None
    for nr, roh in enumerate(leser, 1):
        if not any(c.strip() for c in roh):
            continue
        if spalten is None:
            spalten = [titel.get(c.strip().lower()) for c in roh]
            if "plz_von" not in spalten or "zone_id" not in spalten:
                return [], [f"Zeile {nr}: Kopfzeile mit mindestens 'PLZ von' und 'Zone' erwartet"]
            continue
        z, meldung = {}, None
        for name, wert in zip(spalten, roh):
            if not name:
                continue
            try:
                z[name] = wert_aus_text(PLZ.feld(name), wert.strip().upper() if name in ("land", "plz_von", "plz_bis")
                                        else wert)
            except ValueError as e:
                meldung = str(e)
                break
        z.setdefault("land", "DE")
        von = z.get("plz_von") or ""
        if von.isdigit() and len(von) <= 3 and not z.get("plz_bis"):      # '25' = alle PLZ mit 25… (Präfix)
            z["plz_von"] = von + "*"
        if not meldung:
            if not z.get("plz_von"):
                meldung = "PLZ von fehlt"
            elif z.get("zone_id") not in zonen:
                meldung = f"Zone '{z.get('zone_id') or ''}' unbekannt"
            elif laender and z.get("land") not in laender:
                meldung = f"Land '{z.get('land')}' unbekannt"
            elif z.get("richtung") and z["richtung"] not in RICHTUNGEN:
                meldung = f"Richtung '{z['richtung']}' unbekannt"
            else:
                from .stammdaten import Kontext
                p = _plz_pruefung(z, Kontext())
                if p and p.startswith("FEHLER"):
                    meldung = p[8:]
        if meldung:
            fehler.append(f"Zeile {nr}: {meldung}")
        else:
            zeilen.append({n: z.get(n) for n in CSV_PLZ})
    return zeilen, fehler
