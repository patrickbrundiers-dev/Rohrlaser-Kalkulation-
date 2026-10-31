"""Aufbau der Stammdaten: Tabellen, Felder, Prüfregeln und berechnete Spalten.

Eine Beschreibung je Tabelle dient für alles: Datenbankschema, Anzeige im Programm und Prüfung.
"""
import datetime
import math
import re
from dataclasses import dataclass, field

from . import dfm, feiertage, funktionen, naht, normprofile, rp_profile
from .stil import DICHTEN, THEMES

EINGABE_RICHTUNGEN = ("nach unten", "nach rechts")      # Einstellung eingabe_richtung (tabellen_eingabe.py)

PREISBASIS = ("€/kg", "€/Stange", "€/m")
PROFILFORMEN = ("Rundrohr", "Quadratrohr", "Rechteckrohr", "U-Profil", "C-Profil", "L-Profil", "Flachstahl",
                "I-/H-Träger", "T-Profil", rp_profile.FORM, "Sonderprofil")
# Offene Profile: A = Höhe (U, C: Steg; L: längerer Schenkel; Flachstahl: Breite), B = Breite (U, C: Flansch; L:
# kürzerer Schenkel; Flachstahl leer), Wandstärke = Blechdicke. C-Profil: Querschnitt über 'Fläche manuell'
# (Abkantung nicht in den Maßen).
# I-/H-Träger und T-Profil (seit 20.10.2026): A = Höhe, B = Flanschbreite, Wandstärke = Stegdicke; Querschnitt aus
# der Normtabelle (Profil-ID wie 'IPE 200', 'HEB 160', 'T 50'), sonst über 'Fläche manuell' (der STEP-Import trägt
# sie ein), weil die Flanschdicke nicht in den Maßen steht.
TRAEGER = ("I-/H-Träger", "T-Profil")
OFFENE_PROFILE = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl") + TRAEGER
MIT_B = ("Rechteckrohr", "U-Profil", "C-Profil", "L-Profil", rp_profile.FORM) + TRAEGER
KATEGORIEN = ("Stahl", "Edelstahl", "Aluminium", "Buntmetall")
# Lasereigenschaften je Werkstoff (Patrick 24.10.2026 „Werkstoffliste spezifischer auf Rohrlaser“, alle leer = wie
# bisher): Schneidgas-Vorgabe, nur Faserlaser (reflektierende Werkstoffe), Rohrart (ohne Naht: keine Nahtvorgabe)
GAS_VORGABEN = ("automatisch", "nur N₂", "nur O₂")
LASERARTEN = ("Faser + CO₂", "nur Faser")
NUR_FASER = "nur Faser"
ROHRARTEN = ("geschweißt", "nahtlos", "stranggepresst")
OHNE_NAHT = ("nahtlos", "stranggepresst")
# Teuerungs-/Legierungszuschlag je Werkstoff (Plan 29.10.2026 1a, Patrick „4c“: Prozent oder €/kg wählbar)
TEUERUNG_PROZENT, TEUERUNG_KG = "%", "€/kg"
TEUERUNG_ARTEN = (TEUERUNG_PROZENT, TEUERUNG_KG)
# Schneidgas: N₂ gilt, solange es eine N₂-Zeile mit passender Wandstärke gibt, darüber O₂
GASE = ("N₂", "O₂")
ROH = "roh"     # Oberfläche ohne Aufpreis; leer in der Position heißt ebenfalls roh
# Abrechnung einer Zusatzarbeit: Betrag je kg, m² Außenfläche, m Länge, Stück oder einmal je Angebot (pauschal,
# auf die Teile umgelegt); 's/Stück' = Zeit in Sekunden je Stück, die zur Schneidzeit addiert wird (z. B. Gravur,
# die nicht im STEP-Modell ist); '€/h' = Zeit in Sekunden je Teil (je Position im Angebot) × Stundensatz (Schweißen)
ZUSATZARTEN = ("€/kg", "€/m²", "€/m", "€/Stück", "s/Stück", "€/Angebot", "€/h")
ZUSATZART_TEXT = {"€/Stück": "pro Stück", "€/Angebot": "pauschal je Angebot", "€/kg": "nach Gewicht",
                  "€/m²": "nach Außenfläche", "€/m": "nach Länge", "s/Stück": "Maschinenzeit zur Laserzeit",
                  "€/h": "Zeit in s je Teil × Stundensatz"}
ZEITEINHEITEN = {"s": 1, "min": 60, "h": 3600}
ZUSCHLAG_ARTEN = ("%", "€")
ZUSCHLAG_BASIS = ("Arbeit", "Material", "Arbeit und Material")
ZUSATZ_KATEGORIEN = ("Oberfläche", "Nachbearbeitung", "Laser", "Montage", "Prüfung", "Verpackung", "Sonstiges")
# Arbeitsschritte: Stundensatz 'Maschine' = Stundensatz der im Angebot gewählten Maschine (Stammdaten Maschinen)
SATZ_MASCHINE = "Maschine"
ZEITARTEN = ("Maschine", "Personal")
RUESTBEZUG = ("Angebot", "Abmessung")
ZEITBEZUG = ("Teil", "Stange", "Position")
# Arbeitsschritte, deren Zeit das Programm selbst ermittelt (Schneiddaten, Gewinde, Maschinen, Einstellungen):
# in der Tabelle Arbeitsschritte zählen für sie nur Stundensatz, Art und 'parallel'
SCHRITTE_FEST = {
    "Laser schneiden": "Schneidweg, Konturen und Einstiche mit den Schneiddaten bzw. Schneidzeit von Hand, dazu "
                       "Zusatzarbeiten in s/Stück",
    "Gewinde": "Gewinde rechnen nur mit Preis je Stück (Stammdaten Gewinde), ohne Zeit",
    "Rüsten Maschine": "Rüstzeit je Angebot der Maschine (Stammdaten Maschinen)",
    "Rüsten je Abmessung": "Rüstzeit je Abmessung aus dem Angebot (Vorgabe Einstellungen)",
    "Stangenwechsel": "Stangenwechsel je Stange der Maschine × Anzahl Stangen; Stangen mit einem Teil mit fester "
                      "Schweißnaht-Lage rechnen mit 'Stangenwechsel SN'",
    "Programmierung": "Programmierzeit je Position mit Stückzahl: Grundzeit + Zeit je Innenkontur aus dem Angebot "
                      "(Vorgabe Einstellungen) oder von Hand je Position; Stundensatz Vorgabe 'Programmierung'",
}
# Stundensatz der vom Programm gerechneten Schritte, wenn die Tabelle Arbeitsschritte keinen nennt (sonst Maschine)
SCHRITT_SATZ = {"Programmierung": "Programmierung"}
# Zukaufartikel (Rechnung in zukauf.py): Aufschlagsmethoden, Herkunft des Aufschlags am Artikel, Status
ZUKAUF_METHODEN = ("% auf Einstand", "€ je Einheit", "€ je Bestellung", "Mengenstaffel %", "Zielmarge %")
ZUKAUF_QUELLEN = ("Kategorie", "individuell", "Standard")
ZUKAUF_STATUS = ("aktiv", "archiviert")
ZUKAUF_TYPEN = ("Blech", "Rundstahl", "Vierkantstahl")   # besondere Artikeltypen (leer = normaler Zukaufartikel)
ZUSATZ_EINHEIT = {"€/kg": "kg", "€/m²": "m²", "€/m": "m", "€/Stück": "Stk", "s/Stück": "Stk", "€/Angebot": "Angebot",
                  "€/h": "s"}


@dataclass(frozen=True)
class Feld:
    name: str               # Spalte in der Datenbank
    titel: str              # Spaltenkopf im Programm
    art: str = "text"       # text | zahl | ganz | datum | auswahl
    von: float = None       # zulässiger Bereich
    bis: float = None
    auswahl: str = None     # Quelle der Auswahlliste: profilform, preisbasis, profil, werkstoff, maschine, …
    stellen: int = None     # Nachkommastellen in der Anzeige
    breite: int = 110       # Spaltenbreite in Pixeln
    pflicht: bool = False
    muster: tuple = None    # (regulärer Ausdruck, Meldung) für Textfelder


@dataclass(frozen=True)
class Tabelle:
    name: str               # Tabelle in der Datenbank
    titel: str              # Reiter im Programm
    felder: tuple
    schluessel: tuple       # eindeutige Felder (zusammen)
    hinweis: str
    berechnet: tuple = ()      # (Titel, Funktion(zeile, kontext), Nachkommastellen)
    pruefung: object = None    # weitere Prüfung: Funktion(zeile, kontext) -> 'WARNUNG: …'/'FEHLER: …' oder None

    def feld(self, name):
        return next(f for f in self.felder if f.name == name)


# ------------------------------------------------------------------ berechnete Werte
def flaeche_berechnet(p):
    """Querschnitt ohne Eckradien."""
    form, a, b, s = p.get("form"), p.get("a"), p.get("b"), p.get("wand")
    if not p.get("profil_id") or a is None or s is None:
        return None
    if form == "Rundrohr":
        return math.pi / 4 * (a ** 2 - (a - 2 * s) ** 2)
    if form == "Quadratrohr" or (form == "Rechteckrohr" and b is not None):
        hb = a if form == "Quadratrohr" else b
        return a * hb - (a - 2 * s) * (hb - 2 * s)
    if form == "U-Profil" and b is not None:
        return s * (a + 2 * (b - s))
    if form == "L-Profil" and b is not None:
        return s * (a + b - s)
    if form == "Flachstahl":
        return a * s
    if form in TRAEGER:
        n = normprofile.daten(p.get("profil_id"))
        return n["flaeche"] if n and n["form"] == form and n["flaeche"] else None
    if form == rp_profile.FORM:       # aus der Kontur (MegaCAD-Makro), mit Radien und Anschlägen
        r = rp_profile.daten(p.get("profil_id"))
        return r["flaeche"] if r else None
    return None


def wand_schneiden(p):
    """Wandstärke für die Schneiddaten (Schneidzeit, Vorschub, Gas): die größte Wandstärke des Profils, also die
    größere von Wandstärke und Wandstärke max.; ohne Wandstärke max. bei Normprofilen die Flanschdicke der Tabelle
    (Träger, T, UPN). None ohne beide Werte."""
    werte = [w for w in (p.get("wand"), p.get("wand_max")) if isinstance(w, (int, float))]
    if not isinstance(p.get("wand_max"), (int, float)):
        n = normprofile.daten(p.get("profil_id"))
        if n and n.get("tf") and n["form"] == p.get("form"):
            werte.append(n["tf"])
    return max(werte) if werte else None


def huellkreis(p):
    """Durchmesser des Kreises um den Profilquerschnitt: Rundrohr Ø, Quadrat-/Rechteckrohr Diagonale, RP-Profil
    Diagonale des Hüllmaßes. Sonderprofile ohne Angabe (None)."""
    form, a, b = p.get("form"), p.get("a"), p.get("b")
    if a is None:
        return None
    if form == "Rundrohr":
        return a
    if form == "Quadratrohr":
        return a * math.sqrt(2)
    if form in ("Rechteckrohr", "U-Profil", "C-Profil", "L-Profil", rp_profile.FORM) + TRAEGER and b is not None:
        return math.hypot(a, b)
    if form == "Flachstahl" and p.get("wand") is not None:
        return math.hypot(a, p["wand"])
    return None


def _radius_wirksam(z):
    from .optimierung import aussenradius
    if z.get("form") not in ("Quadratrohr", "Rechteckrohr"):
        return None
    return aussenradius(z.get("form"), z.get("a"), z.get("b"), z.get("wand"), z.get("r_aussen"))


def flaeche_wirksam(p):
    """Herstellerwert (Fläche manuell) vor berechnetem Querschnitt."""
    if not p.get("profil_id"):
        return None
    return p["flaeche_manuell"] if p.get("flaeche_manuell") is not None else flaeche_berechnet(p)


def preis_je_m_automatisch(z, k):
    """Preis €/m aus Querschnitt × Dichte × Tonnenpreis."""
    p, w = k.profile.get(z.get("profil_id")), k.werkstoffe.get(z.get("werkstoff_id"))
    if not p or not w:
        return None
    fl, dichte, tonne = flaeche_wirksam(p), w.get("dichte"), w.get("tonnenpreis")
    if fl is None or dichte is None or tonne is None:
        return None
    return fl * dichte / 1000 * tonne / 1000


# ------------------------------------------------------------------ Tabellen
KUNDEN = Tabelle(
    "kunden", "Kunden",
    (Feld("kundennr", "Kundennummer", pflicht=True, breite=100),
     Feld("name", "Kundenname", pflicht=True, breite=200),
     Feld("strasse", "Straße", breite=170),
     Feld("plz_ort", "PLZ Ort", breite=150),
     Feld("plz", "PLZ", breite=65),
     Feld("land", "Land", muster=(r"^[A-Z]{2}$", "Land als zweistelliger Ländercode, z. B. DE"), breite=50),
     Feld("ansprechpartner", "Ansprechpartner", breite=130),
     Feld("telefon", "Telefon", breite=110),
     Feld("email", "E-Mail", breite=170),
     Feld("skonto", "Skonto [%]", "zahl", 0, 20, stellen=1, breite=70),
     Feld("skonto_tage", "Skontofrist [Tage]", "ganz", 0, 365, breite=75),
     Feld("zahlungsziel", "Zahlungsziel netto [Tage]", "ganz", 0, 365, breite=85),
     Feld("liefer_plz", "Liefer-PLZ abweichend", breite=85),
     Feld("liefer_land", "Lieferland abweichend", muster=(r"^[A-Z]{2}$", "Land als zweistelliger Ländercode, z. B. DE"),
          breite=70),
     Feld("lieferbedingung", "Lieferbedingung", "auswahl", auswahl="lieferbedingung", breite=110),
     Feld("bemerkung", "Bemerkung", breite=200)),
    ("kundennr",),
    "Kunden für den Angebotskopf: Kundennummer wählen, dann kommen Name, Anschrift und Zahlungsbedingungen ins "
    "Angebot. Skonto, Skontofrist und Zahlungsziel leer = Vorgabe aus den Einstellungen. PLZ und Land (leer = PLZ aus "
    "'PLZ Ort' und DE) bzw. die abweichende Lieferanschrift bestimmen die Frachtzone. Doppelklick auf einen Kunden "
    "zeigt seine Angebote; ändern durch Tippen oder F2.")

PROFILE = Tabelle(
    "profile", "Profile",
    (Feld("profil_id", "Profil-ID", pflicht=True, breite=130),
     Feld("form", "Profilform", "auswahl", auswahl="profilform", pflicht=True),
     Feld("a", "Abmessung A [mm]", "zahl", 1, 1000, stellen=1, pflicht=True),
     Feld("b", "Abmessung B [mm]", "zahl", 1, 1000, stellen=1),
     Feld("wand", "Wandstärke [mm]", "zahl", 0, 500, stellen=2, pflicht=True),
     Feld("flaeche_manuell", "Fläche manuell [mm²]", "zahl", 1, 100000, stellen=1),
     Feld("endbeschnitt", "Endbeschnitt abweichend [mm]", "zahl", 0, 2000, stellen=0),
     Feld("greiferrest", "Greiferrest abweichend [mm]", "zahl", 0, 2000, stellen=0),
     Feld("bemerkung", "Bemerkung", breite=220),
     # hinten angefügt: Beispieldaten und Import älterer Dateien zählen die Felder nach Reihenfolge
     Feld("wand_max", "Wandstärke max. [mm]", "zahl", 0, 500, stellen=2),
     Feld("laengenvergleich", "Lieferlängen vergleichen", "auswahl", auswahl="janein", breite=85),
     Feld("r_aussen", "Außenradius [mm]", "zahl", 0, 100, stellen=1)),
    ("profil_id",),
    "Abmessung A = Ø (Rundrohr) bzw. Breite, Abmessung B = Höhe (nur Rechteckrohr). U- und C-Profil: A = Steg, "
    "B = Flansch; L-Profil: A und B = Schenkel; Flachstahl: A = Breite, Wandstärke = Dicke; I-/H-Träger und "
    "T-Profil: A = Höhe, B = Flanschbreite, Wandstärke = Stegdicke (Querschnitt aus der Normtabelle bei IPE, IPN, "
    "HEA, HEB, HEM, T, sonst Fläche manuell). Wandstärke max. = dickste Stelle (z. B. Flanschdicke): die "
    "Schneidzeit rechnet mit der größeren der beiden Wandstärken; leer = Normtabelle bzw. Wandstärke. RP-Profil (Rohr "
    "mit Anschlag, Profil-ID 'RP 0106-35'): A = Breite, B = Höhe, Wandstärke = Blechdicke; Fläche, Umfang und "
    "Schnittlänge aus der Kontur der RP-Bibliothek bzw. des geladenen MegaCAD-Makros. Endbeschnitt und "
    "Greiferrest nur eintragen, wenn sie vom Maschinenwert abweichen. Fläche manuell = Herstellerwert "
    "(Eckradien, Sonderprofile, C-Profil). Lieferlängen vergleichen = nein: das Profil wird nur mit der "
    "Stangenlänge des Angebots geplant, weitere Lieferlängen (z. B. 12 m) werden nicht verglichen. Außenradius "
    "(Quadrat- und Rechteckrohr): Radius der Außenecken für Schnittlänge, Skizze und 3D; leer = Vorgabe nach EN 10219 "
    "(2 × Wand bis 6 mm, 2,5 × Wand bis 10 mm, darüber 3 × Wand), bei Werkstoff Aluminium leer = 0; "
    "0 = scharfkantig; je Teil im Schneidweg-Rechner änderbar.",
    berechnet=(("Fläche berechnet [mm²]", lambda z, k: flaeche_berechnet(z), 1),
               ("Fläche wirksam [mm²]", lambda z, k: flaeche_wirksam(z), 1),
               ("Hüllkreis-Ø [mm]", lambda z, k: huellkreis(z), 1),
               ("Außenradius wirksam [mm]", lambda z, k: _radius_wirksam(z), 1)))

WERKSTOFFE = Tabelle(
    "werkstoffe", "Werkstoffe",
    (Feld("werkstoff_id", "Werkstoff-ID", pflicht=True, breite=120),
     Feld("kategorie", "Kategorie", "auswahl", auswahl="kategorie", breite=90),
     Feld("werkstoff", "Werkstoff", breite=130),
     Feld("werkstoff_nr", "Werkstoff-Nr."),
     Feld("norm", "Norm / Qualität", breite=220),
     Feld("dichte", "Dichte [kg/dm³]", "zahl", 0.5, 25, stellen=2, pflicht=True),
     Feld("bemerkung", "Bemerkung", breite=160),
     Feld("tonnenpreis", "Tonnenpreis [€/t]", "zahl", 0.01, 1000000, stellen=0),
     Feld("angebotstext", "Text im Angebot", breite=160),
     # Anforderungen in der Materialanfrage (unter der Materialzeile); leer = keine
     Feld("anfrage_zeugnis", "Anfrage: Prüfbescheinigung", "auswahl", auswahl="zeugnis", breite=100),
     Feld("anfrage_herkunft_eu", "Anfrage: Herkunft EU", "auswahl", auswahl="janein", breite=80),
     Feld("anfrage_toleranz", "Anfrage: Maßtoleranzen nach Norm", "auswahl", auswahl="janein", breite=100),
     # Rohrlaser (Schema 55, leer = wie bisher)
     Feld("rohrart", "Rohrart", "auswahl", auswahl="rohrart", breite=95),
     Feld("gas_vorgabe", "Schneidgas", "auswahl", auswahl="gasvorgabe", breite=90),
     Feld("vorschub_faktor", "Vorschub-Faktor", "zahl", 0.1, 3, stellen=2, breite=75),
     Feld("laser", "Laser", "auswahl", auswahl="laserart", breite=85),
     Feld("laser_hinweis", "Laser-Hinweis", breite=220),
     # Teuerungs-/Legierungszuschlag (Schema 68, leer = kein Zuschlag; Plan 29.10.2026 1a)
     Feld("teuerung_art", "Teuerungszuschlag je", "auswahl", auswahl="teuerung", breite=95),
     Feld("teuerung_wert", "Teuerungszuschlag", "zahl", -50, 10000, stellen=2, breite=85),
     Feld("teuerung_stand", "Teuerung Stand", "datum", breite=95)),
    ("werkstoff_id",),
    "Die Werkstoff-ID ist der Schlüssel für Preise, Schneiddaten und Angebot. Die Kategorie (Stahl, Edelstahl, "
    "Aluminium) ordnet die Auswahl im Angebot und liefert Schneiddaten und Oberflächen, wenn der Werkstoff keine "
    "eigenen hat. Der Tonnenpreis ergibt automatisch den Preis je kg, je m und je Stange; Abweichungen unter "
    "'Preise' eintragen. Die Spalten 'Anfrage: …' setzen die Anforderungen, die in der Materialanfrage unter dem "
    "Werkstoff stehen (Prüfbescheinigung nach EN 10204, Herkunft EU, Maßtoleranzen nach Norm). Rohrlaser: "
    "Rohrart nahtlos oder stranggepresst = ohne Schweißnaht (eine Nahtvorgabe der Teile entfällt, kein "
    "Stangenwechsel SN); Schneidgas 'nur N₂'/'nur O₂' nimmt nur die Schneiddaten-Zeilen dieses Gases; "
    "Vorschub-Faktor wirkt auf die Schneiddaten der Kategorie (nicht auf eigene Zeilen des Werkstoffs); Laser "
    "'nur Faser' warnt auf einer CO₂-Maschine; der Laser-Hinweis steht in Werkstoffwahl, Angebots-Check, "
    "Kalkulation und Werkstattpapieren. Teuerungszuschlag (Legierungs-/Materialteuerungszuschlag, z. B. bei "
    "Edelstahl und Aluminium): je '%' auf den Materialpreis aus Lieferlängen, Preisen oder Tonnenpreis oder je "
    "'€/kg' auf das Stangengewicht; nicht auf Preise von Hand und Oberflächen-Aufpreise. Stand = Stichtag des "
    "Zuschlags (z. B. Monat des Lieferanten); festgeschriebene Angebote behalten ihren Zuschlag.")

OBERFLAECHEN = Tabelle(
    "oberflaechen", "Oberflächen",
    (Feld("oberflaeche", "Oberfläche", pflicht=True, breite=120),
     Feld("kategorie", "Kategorie (leer = alle)", "auswahl", auswahl="kategorie", breite=110),
     Feld("aufpreis_m", "Aufpreis [€ je Basis]", "zahl", 0, 10000, stellen=2, breite=80),
     Feld("angebotstext", "Text im Angebot", breite=160),
     Feld("bemerkung", "Bemerkung", breite=260),
     # Plan Abrechnungsregeln 28.10.2026 (Schritt 1): Basis des Aufpreises, leer = €/m wie bisher
     Feld("aufpreis_basis", "Aufpreis je", "auswahl", auswahl="aufpreisbasis", breite=70)),
    ("oberflaeche",),
    "Oberfläche des Rohmaterials, je Position wählbar (leer = roh). Teile mit unterschiedlicher Oberfläche "
    "kommen nie auf dieselbe Stange. Der Aufpreis kommt auf den Materialpreis der Stange (mit Verschnitt), je "
    "nach 'Aufpreis je' in €/m (leer, wie bisher), €/kg (× Metergewicht) oder €/m² (× Umfang); ein "
    "abweichender Materialpreis in der Position ersetzt Preis und Aufpreis. Kategorie: für welche Werkstoffe "
    "die Oberfläche passt (sonst Warnung im Angebot).")

PREISE = Tabelle(
    "preise", "Preise",
    (Feld("profil_id", "Profil-ID", "auswahl", auswahl="profil", pflicht=True, breite=130),
     Feld("werkstoff_id", "Werkstoff-ID", "auswahl", auswahl="werkstoff", pflicht=True, breite=120),
     Feld("basis", "Preisbasis", "auswahl", auswahl="preisbasis", pflicht=True, breite=80),
     Feld("preis", "Preis [€]", "zahl", 0.01, 100000, stellen=2, pflicht=True, breite=80),
     Feld("lieferlaenge", "Liefer-Stangenlänge [mm]", "ganz", 500, 20000),
     Feld("gueltig_ab", "Gültig ab", "datum", breite=90),
     Feld("lieferant", "Lieferant", breite=140),
     Feld("bemerkung", "Bemerkung", breite=160)),
    ("profil_id", "werkstoff_id"),
    "Je Kombination Profil + Werkstoff höchstens eine Zeile. Preisbasis €/kg, €/m oder €/Stange "
    "(bezogen auf die Liefer-Stangenlänge). Ohne Zeile gilt der Tonnenpreis des Werkstoffs.",
    berechnet=(("Preis €/m automatisch", preis_je_m_automatisch, 2),))

LIEFERLAENGEN = Tabelle(
    "lieferlaengen", "Lieferlängen",
    (Feld("profil_id", "Profil-ID", "auswahl", auswahl="profil", pflicht=True, breite=130),
     Feld("werkstoff_id", "Werkstoff-ID", "auswahl", auswahl="werkstoff", pflicht=True, breite=120),
     Feld("laenge", "Lieferlänge [mm]", "ganz", 500, 30000, pflicht=True, breite=90),
     Feld("basis", "Preisbasis (leer = wie Preise)", "auswahl", auswahl="preisbasis", breite=95),
     Feld("preis", "Preis [€]", "zahl", 0.01, 100000, stellen=2, breite=80),
     Feld("gueltig_ab", "Gültig ab", "datum", breite=90),
     Feld("lieferant", "Lieferant", breite=140),
     Feld("bemerkung", "Bemerkung", breite=200)),
    ("profil_id", "werkstoff_id", "laenge"),
    "Weitere lieferbare Stangenlängen je Profil + Werkstoff (z. B. 12.000 mm). Das Angebot vergleicht sie mit der "
    "Stangenlänge des Angebots und empfiehlt sie nur bei ausreichender Kostenersparnis (Einstellungen, Gruppe "
    "Lieferlängen). Längen über der max. Stangenlänge der Maschine schneidet der Lieferant auf die geplanten "
    "Stangenlängen zu. Preis leer = €/kg- bzw. €/m-Preis aus 'Preise', ohne Zeile dort der Tonnenpreis. Gibt es "
    "für Profil + Werkstoff Zeilen, ist die Stangenlänge des Angebots nur lieferbar, wenn sie hier oder als "
    "Liefer-Stangenlänge in 'Preise' steht. Ohne Zeile gelten Profile über dem Hüllkreis-Ø aus den Einstellungen "
    "(Vorgabe 70 mm) zusätzlich als 12 m lieferbar, Preis wie 'Preise'; kleinere ohne Zeile nie. Profile: "
    "Lieferlängen vergleichen = nein schließt ein Profil ganz aus.")

MASCHINEN = Tabelle(
    "maschinen", "Maschinen",
    (Feld("maschinen_id", "Maschinen-ID", pflicht=True, breite=100),
     Feld("bezeichnung", "Bezeichnung", breite=170),
     Feld("endbeschnitt", "Endbeschnitt [mm]", "zahl", 0, 2000, stellen=0),
     Feld("greiferrest", "Greiferrest [mm]", "zahl", 0, 2000, stellen=0),
     Feld("schnittverlust", "Schnittverlust je Schnitt [mm]", "zahl", 0, 20, stellen=1),
     Feld("max_stange", "Max. Stangenlänge [mm]", "ganz", 500, 20000),
     Feld("stundensatz", "Stundensatz [€/h]", "zahl", 0, 10000, stellen=2),
     Feld("kontur_klein", "Kontur klein bis [mm]", "zahl", 0.1, 5000, stellen=1),
     Feld("kontur_mittel", "Kontur mittel bis [mm]", "zahl", 0.1, 5000, stellen=1),
     Feld("kontur_klein_wand", "Kontur klein bis [× Wand]", "zahl", 0.1, 1000, stellen=1),
     Feld("kontur_mittel_wand", "Kontur mittel bis [× Wand]", "zahl", 0.1, 1000, stellen=1),
     Feld("abstand", "Abstand getrennte Schnitte [mm]", "zahl", 0, 100, stellen=1),
     Feld("ruestzeit", "Rüstzeit je Angebot [min]", "zahl", 0, 1440, stellen=0),
     Feld("stangenwechsel", "Stangenwechsel je Stange [s]", "zahl", 0, 3600, stellen=0),
     Feld("stangenwechsel_sn", "Stangenwechsel SN je Stange [s]", "zahl", 0, 3600, stellen=0),
     Feld("bemerkung", "Bemerkung", breite=160),
     Feld("max_huellkreis", "Max. Hüllkreis-Ø [mm]", "zahl", 1, 2000, stellen=1),
     Feld("max_kg_m", "Max. Metergewicht [kg/m]", "zahl", 0.1, 1000, stellen=1),
     Feld("min_stange", "Min. Stangenlänge Zuschnitt [mm]", "ganz", 0, 20000),
     Feld("d3", "3D: Bearbeitung verfügbar", "auswahl", auswahl="janein", breite=80),
     Feld("schwenk_min", "3D: Schwenkwinkel min. [°]", "zahl", -89, 0, stellen=0, breite=85),
     Feld("schwenk_max", "3D: Schwenkwinkel max. [°]", "zahl", 0, 89, stellen=0, breite=85),
     Feld("greif_3d", "3D: Greifmaß [mm]", "zahl", 0, 5000, stellen=0, breite=80),
     Feld("zeit_3d", "3D: Zusatzzeit je Bearbeitung [s]", "zahl", 0, 600, stellen=1, breite=95),
     Feld("faktor_3d", "3D: Faktor Schneidzeit", "zahl", 0.1, 10, stellen=2, breite=80),
     Feld("sonder_spannbar", "RP-/Sonderprofile spannbar", "auswahl", auswahl="janein", breite=85),
     Feld("ruest_sonder", "Rüstzuschlag Sonderprofil [min je Abmessung]", "zahl", 0, 1440, stellen=0, breite=95),
     Feld("duese_min", "Mindestabstand Düse [mm]", "zahl", 0, 200, stellen=1, breite=85),
     Feld("min_teil", "Kürzestes Teil [mm]", "zahl", 0, 20000, stellen=0, breite=80),
     Feld("zeit_kontur", "Zeit je Kontur (Anfahren/Drehen) [s]", "zahl", 0, 60, stellen=2, breite=95),
     # Plan „Kalkulation und Berechnung verbessern“ (Patrick 29.10.2026, alles a): Nebenzeit, Schneidgas, Profilwechsel
     Feld("zeit_teil", "Nebenzeit je Teil (Ausschieben/Entnehmen) [s]", "zahl", 0, 600, stellen=1, breite=95),
     Feld("gas_n2", "Schneidgas N₂ [€/h]", "zahl", 0, 1000, stellen=2, breite=85),
     Feld("gas_o2", "Schneidgas O₂ [€/h]", "zahl", 0, 1000, stellen=2, breite=85),
     Feld("ruest_form", "Rüstzuschlag je weiterer Profilform [min]", "zahl", 0, 1440, stellen=0, breite=95),
     # Schichtkalender der Wochenauslastung (Plan 29.10.2026 2b, auslastung.py); leer = Einstellung
     Feld("schicht_stunden", "Schicht: Stunden je Arbeitstag", "zahl", 0, 24, stellen=1, breite=90),
     # Stundensatz-Ermittlung je Maschine (Patrick 29.10.2026, stundensatz.py): von Hand (leer) oder ermittelt
     Feld("satz_art", "Stundensatz von Hand/ermittelt", "auswahl", auswahl="satzart", breite=95),
     Feld("gas_zusatz", "Gas zusätzlich zum Stundensatz", "auswahl", auswahl="janein", breite=90),
     Feld("anschaffung", "Ermittlung: Anschaffung [€]", "zahl", 0, 1e8, stellen=0, breite=95),
     Feld("nutzungsdauer", "Ermittlung: Nutzungsdauer [Jahre]", "zahl", 0, 50, stellen=0, breite=90),
     Feld("flaeche", "Ermittlung: Fläche [m²]", "zahl", 0, 10000, stellen=0, breite=80),
     Feld("instandhaltung", "Ermittlung: Instandhaltung [% je Jahr]", "zahl", 0, 50, stellen=1, breite=95),
     Feld("wartung", "Ermittlung: Wartung, Versicherung [€/Jahr]", "zahl", 0, 1e7, stellen=0, breite=100),
     Feld("leistung_kw", "Ermittlung: Anschlussleistung [kW]", "zahl", 0, 1000, stellen=1, breite=90),
     Feld("verschleiss", "Ermittlung: Verschleiß [€/h]", "zahl", 0, 1000, stellen=2, breite=85),
     Feld("bediener_anteil", "Ermittlung: Bediener [% Betreuung]", "zahl", 0, 100, stellen=0, breite=90)),
    ("maschinen_id",),
    "Endbeschnitt = Anschnitt am Stangenanfang, Greiferrest = nicht nutzbares Ende im Greifer, "
    "Schnittverlust = Materialverlust je Trennschnitt. Konturgrenzen: größtes Hüllmaß der Innenkontur. Kontur "
    "klein/mittel bis × Wand: zusätzlich nach Hüllmaß ÷ Wandstärke (Vorgabe 3 und 8), die strengere Klasse gilt. "
    "Max. Hüllkreis-Ø und max. Metergewicht: größere oder schwerere Profile bekommen im Angebot FEHLER "
    "und werden nicht eingeplant (leer = keine Grenze). Min. Stangenlänge Zuschnitt: kürzeste Stange, die die "
    "automatische Stangenladung nimmt; keine aus einer Lieferstange (z. B. 12 m) zugeschnittene Stange wird kürzer "
    "(leer oder 0 = keine Grenze). Stangenwechsel SN: Zeit je Stange, auf der ein Teil eine feste "
    "Schweißnaht-Lage hat (Naht ausrichten), alle anderen Stangen mit 'Stangenwechsel' (leer = wie Stangenwechsel). "
    "3D (geschwenkter Laserkopf für Gehrungen in 3D und schräge Bohrungen): nur mit 'ja' kalkuliert; Winkel "
    "außerhalb min./max. werden auf die Grenze begrenzt. Greifmaß: Abstand, den eine 3D-Bearbeitung am letzten Teil "
    "einer Stange vom Stangenende braucht (zählt statt des Greiferrests, wenn größer, nie zusätzlich). Schneidzeit "
    "3D = Schneiddaten bei Wand ÷ cos(Winkel) × Faktor + Zusatzzeit je Bearbeitung. RP-/Sonderprofile spannbar: "
    "'nein' = Positionen mit RP-Profil oder Sonderprofil bekommen WARNUNG (Maschine prüfen), leer = ja. "
    "Rüstzuschlag Sonderprofil: zusätzliche Rüstzeit je RP-/Sonderprofil-Abmessung (wie Rüsten je Abmessung). "
    "Mindestabstand Düse: tiefer als dieses Maß steht der Anschlag eines RP-Profils über; Innenkonturen können "
    "darunter liegen und bekommen WARNUNG (prüfen), leer = keine Prüfung. Kürzestes Teil: kürzere Teile kann die "
    "Maschine nicht fertigen; sie bekommen die Stufe der Prüfregel 'Teil zu kurz für die Maschine' (leer = keine "
    "Grenze). Zeit je Kontur (Anfahren/Drehen): Zuschlag je Einstich für das Anfahren der Kontur und das Drehen des "
    "Rohrs dazwischen (jede Innenkontur und jedes Ende), leer = 0; mit echten Schnittzeiten abgleichen. "
    "Nebenzeit je Teil: Ausschieben, Abtrennen und Entnehmen jedes Teils, leer = 0. Schneidgas N₂/O₂: Gaskosten je "
    "Stunde Laserzeit zusätzlich zum Stundensatz, je nach Gas der Schneiddaten (Stickstoff für Edelstahl und Alu ist "
    "teurer), leer = 0; nur bei Stundensatz 'ermittelt' oder 'Gas zusätzlich zum Stundensatz' = ja. Rüstzuschlag je weiterer Profilform: Spannbacken bzw. Spannmittel tauschen, wenn ein Angebot "
    "mehrere Profilformen hat (z. B. Rundrohr und Rechteckrohr), je Form ab der zweiten, leer = 0. "
    "Schicht: Stunden je Arbeitstag für die Wochenauslastung (Datei → Maschinenauslastung …; leer = Einstellung). "
    "Stundensatz von Hand/ermittelt: leer bzw. 'von Hand' = der eingetragene Stundensatz gilt und enthält Gas und "
    "Strom (Schneidgas nur mit 'Gas zusätzlich zum Stundensatz' = ja); 'ermittelt' = der Satz aus den Feldern "
    "'Ermittlung: …' und den Einstellungen (Knopf 'Stundensatz ermitteln …'), Schneidgas kommt je Teil dazu.")

SCHNEIDDATEN = Tabelle(
    "schneiddaten", "Schneiddaten",
    (Feld("maschinen_id", "Maschinen-ID", "auswahl", auswahl="maschine", pflicht=True, breite=100),
     Feld("werkstoff_id", "Werkstoff-ID", "auswahl", auswahl="werkstoff", breite=120),
     Feld("kategorie", "Kategorie", "auswahl", auswahl="kategorie", breite=90),
     Feld("gas", "Schneidgas", "auswahl", auswahl="gas", breite=70),
     Feld("wand_bis", "Wandstärke bis [mm]", "zahl", 0.1, 50, stellen=1, pflicht=True),
     Feld("vorschub_gross", "Vorschub groß / Trennschnitt [mm/min]", "zahl", 1, 100000, stellen=0, pflicht=True),
     Feld("vorschub_mittel", "Vorschub mittel [mm/min]", "zahl", 1, 100000, stellen=0),
     Feld("vorschub_klein", "Vorschub klein [mm/min]", "zahl", 1, 100000, stellen=0),
     Feld("einstechzeit", "Einstechzeit [s]", "zahl", 0, 60, stellen=1),
     Feld("vorschub_gravur", "Vorschub Gravur [mm/min]", "zahl", 1, 100000, stellen=0),
     Feld("bemerkung", "Bemerkung", breite=160),
     Feld("zeit_ecke", "Zeit je Ecke [s]", "zahl", 0, 60, stellen=2, breite=75),
     Feld("duese", "Düse Ø [mm]", "zahl", 0.3, 10, stellen=1, breite=65),
     Feld("gasdruck", "Gasdruck [bar]", "zahl", 0.1, 40, stellen=1, breite=70)),
    ("maschinen_id", "werkstoff_id", "kategorie", "gas", "wand_bis"),
    "Je Maschine + Werkstoff (oder Kategorie) + Schneidgas gestaffelt nach Wandstärke: es gilt die Zeile mit der "
    "kleinsten 'Wandstärke bis', die mindestens der Profilwandstärke entspricht. Zeilen mit Werkstoff-ID gehen "
    "vor; hat der Werkstoff keine passende Zeile, gelten die Zeilen seiner Kategorie (Werkstoff-ID leer). "
    "Schneidgas: N₂, solange es eine N₂-Zeile für die Wandstärke gibt, darüber O₂ (so endet N₂ ab einer "
    "gewissen Wandstärke). Leere Vorschübe mittel/klein/Gravur nehmen den nächstgrößeren. Zeit je Ecke: Zuschlag "
    "je Ecke im Anfangs- und Endschnitt (der Laser bremst ab): RP-Profile nach ihrer Kontur, Quadrat- und "
    "Rechteckrohr 4, andere 0; leer = 0. Düse Ø und Gasdruck (Überdruck): daraus rechnet das Programm den "
    "Gasverbrauch in m³/h, wenn in den Einstellungen ein Gaspreis €/m³ für das Gas steht (Richtwerte N₂ 1,5-3 mm bei "
    "10-20 bar, O₂ 1-2 mm bei 0,5-1,5 bar); leer = Schneidgas-Zuschlag €/h der Maschine.")

GEWINDE = Tabelle(
    "gewinde", "Gewinde",
    (Feld("gewinde", "Gewinde", pflicht=True, breite=80),
     Feld("kernloch", "Kernloch Ø [mm]", "zahl", 0.5, 100, stellen=1, pflicht=True),
     Feld("zeit", "Zeit je Gewinde [s] (wird nicht gerechnet)", "zahl", 0, 3600, stellen=0),
     Feld("bemerkung", "Bemerkung", breite=260),
     Feld("preis", "Preis je Gewinde [€]", "zahl", 0, 1000, stellen=2, breite=90)),
    ("gewinde",),
    "ISO-Regelgewinde, Kernloch nach DIN 336. Der STEP-Import vergleicht Bohrungsdurchmesser mit dieser "
    "Tabelle (±0,05 mm). In der Kalkulation zählt nur der Preis je Gewinde (€ je Stück); in 'Bohrungen prüfen' "
    "lässt er sich je Position ändern. Ohne Preis rechnet das Gewinde mit 0 € (Warnung).")

def _pruefung_zusatz(z, k):
    from .zusatz_regeln import pruefung_zusatz
    return pruefung_zusatz(z, k)


def _pruefung_regel(z, k):
    from .zusatz_regeln import pruefung
    return pruefung(z, k)


ZUSATZARBEITEN = Tabelle(
    "zusatzarbeiten", "Zusatzarbeiten",
    (Feld("name", "Zusatzarbeit", pflicht=True, breite=160),
     Feld("art", "Abrechnung", "auswahl", auswahl="zusatzart", pflicht=True, breite=80),
     Feld("preis", "Festpreis [€] bzw. Zeit [s] je Einheit", "zahl", 0, 100000, stellen=2, breite=95),
     Feld("mindest", "Mindestbetrag je Angebot [€]", "zahl", 0, 100000, stellen=2, breite=95),
     Feld("fremd", "Fremdleistung", "auswahl", auswahl="janein", breite=80),
     Feld("angebotstext", "Text im Angebot", breite=170),
     Feld("bemerkung", "Beschreibung", breite=260),
     # Schema 15 (alle leer = wie bisher nur Festpreis): Kategorie, Status, Arbeitszeit × Stundensatz, Material mit
     # Zuschlag, weiterer Zuschlag; rechnen.zusatz_preis bildet daraus den Preis je Einheit
     Feld("kategorie", "Kategorie", breite=110),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("zeit", "Zeitaufwand je Einheit", "zahl", 0, 100000, stellen=2, breite=80),
     Feld("zeit_einheit", "Zeiteinheit", "auswahl", auswahl="zeiteinheit", breite=60),
     Feld("satz_id", "Stundensatz-ID", "auswahl", auswahl="zusatzsatz", breite=110),
     Feld("satz", "Stundensatz eigener [€/h]", "zahl", 0, 10000, stellen=2, breite=80),
     Feld("material", "Materialkosten je Einheit [€]", "zahl", 0, 100000, stellen=2, breite=80),
     Feld("zuschlag_material", "Materialzuschlag", "zahl", 0, 100000, stellen=2, breite=80),
     Feld("zuschlag_material_art", "Materialzuschlag in", "auswahl", auswahl="zuschlagart", breite=60),
     Feld("zuschlag_weitere", "Weiterer Zuschlag [%]", "zahl", 0, 1000, stellen=2, breite=80),
     Feld("zuschlag_weitere_basis", "Weiterer Zuschlag auf", "auswahl", auswahl="zuschlagbasis", breite=110),
     # Plan Abrechnungsregeln 28.10.2026 (leer = wie bisher): Menge aus (Bezug), Faktor, Mindestbetrag je Teil
     Feld("bezug", "Menge aus", "auswahl", auswahl="regelmenge", breite=120),
     Feld("faktor", "Faktor Menge", "zahl", 0.01, 100, stellen=3, breite=70),
     Feld("mindest_teil", "Mindestbetrag je Teil [€]", "zahl", 0, 100000, stellen=2, breite=90)),
    ("name",),
    "Auswahl für 'Zusatzarbeiten …' im Angebot. Abrechnung: €/kg (Teilegewicht), €/m² (Außenfläche = "
    "Umfang × Länge), €/m (Teilelänge), €/Stück, €/Angebot (einmal je Angebot, auf die Teile umgelegt), s/Stück "
    "(Zeit je Stück, wird zur Schneidzeit addiert, z. B. Gravur, die nicht im Teil ist), €/h (Zeit in Sekunden je "
    "Teil, im Angebot je Position eingetragen, × Stundensatz, z. B. Schweißen). Preis je Einheit = "
    "Festpreis + Zeitaufwand × Stundensatz + Material mit Materialzuschlag + weiterer Zuschlag. Mindestbetrag: "
    "liegt die Summe im Angebot darunter, wird auf den Mindestbetrag angehoben. Fremdleistung = ja: Zuschlag "
    "Fremdleistung, sonst Zuschlag Fertigung. Menge aus: leer = nach der Abrechnung, sonst z. B. Innen- + "
    "Außenfläche (Strahlen, Verzinken innen) oder Anzahl Bohrungen; Faktor: Menge × Faktor (z. B. 1,05 für "
    "Gehänge); Mindestbetrag je Teil: ein Teil kostet mindestens diesen Betrag. Abweichende Preise je Werkstoff, "
    "Profil oder Kunde und automatisches Zuordnen: Arbeitsgang-Regeln. Gewinde, Senken, Flowdrill und Bohren "
    "rechnen nur € je Stück.",
    pruefung=_pruefung_zusatz)

STUNDENSAETZE = Tabelle(
    "stundensaetze", "Stundensätze",
    (Feld("satz_id", "Stundensatz-ID", pflicht=True, breite=130),
     Feld("bezeichnung", "Bezeichnung", breite=180),
     Feld("satz", "Stundensatz [€/h]", "zahl", 0, 10000, stellen=2, pflicht=True, breite=90),
     Feld("bemerkung", "Bemerkung", breite=300)),
    ("satz_id",),
    "Stundensätze für die Arbeitsschritte. Der Satz 'Maschine' steht nicht hier: er ist immer der Stundensatz der "
    "im Angebot gewählten Maschine (Stammdaten Maschinen). Neue Angebote übernehmen die Sätze beim Anlegen; "
    "spätere Änderungen wirken nur auf neue Angebote (oder im Angebot nach 'Stundensätze aus Einstellungen').")

ARBEITSSCHRITTE = Tabelle(
    "arbeitsschritte", "Arbeitsschritte",
    (Feld("schritt", "Arbeitsschritt", pflicht=True, breite=170),
     Feld("satz", "Stundensatz", "auswahl", auswahl="stundensatz", pflicht=True, breite=130),
     Feld("art", "Art", "auswahl", auswahl="zeitart", pflicht=True, breite=75),
     Feld("parallel", "Parallel zur Maschine", "auswahl", auswahl="janein", breite=75),
     Feld("ruestzeit", "Rüstzeit [min]", "zahl", 0, 100000, stellen=1, breite=70),
     Feld("ruest_bezug", "Rüstzeit je", "auswahl", auswahl="ruestbezug", breite=80),
     Feld("zeit", "Zeit je Einheit [s]", "zahl", 0, 100000, stellen=1, breite=75),
     Feld("bezug", "Einheit", "auswahl", auswahl="zeitbezug", breite=70),
     Feld("bemerkung", "Bemerkung", breite=330)),
    ("schritt",),
    "Zeitvorgaben je Arbeitsschritt. Gesamtzeit = Rüstzeit × Anzahl (je Angebot einmal, je Abmessung je Profil-ID) "
    "+ Zeit je Einheit × Menge (je Teil = Stückzahl, je Stange, je Position); Kosten = Gesamtzeit / 60 × "
    "Stundensatz, mit Zuschlag Fertigung in die Herstellkosten. Laser schneiden, Gewinde, Rüsten Maschine, "
    "Rüsten je Abmessung und Stangenwechsel rechnet das Programm selbst; bei ihnen zählen nur Stundensatz, Art "
    "und Parallel. Art Personal mit Parallel = ja läuft neben der Maschine und verlängert die Durchlaufzeit nicht.")

# Blech-Editor (Patrick 22.10.2026): nur Richtpreis für Blech- und Kantteile vom Blechlaser (Zukaufteil), eigene
# Werkstoffe und Schneiddaten, getrennt von den Rohrlaser-Daten
BLECH_WERKSTOFFE = Tabelle(
    "blech_werkstoffe", "Blech-Werkstoffe",
    (Feld("blech_werkstoff_id", "Blech-Werkstoff", pflicht=True, breite=140),
     Feld("kategorie", "Kategorie", "auswahl", auswahl="kategorie", pflicht=True, breite=90),
     Feld("bezeichnung", "Bezeichnung / Norm", breite=220),
     Feld("dichte", "Dichte [kg/dm³]", "zahl", 0.5, 25, stellen=2, pflicht=True),
     Feld("preis_kg", "Preis [€/kg]", "zahl", 0.01, 1000, stellen=2, pflicht=True),
     Feld("k_faktor", "K-Faktor", "zahl", 0.1, 0.5, stellen=2),
     Feld("bemerkung", "Bemerkung", breite=160)),
    ("blech_werkstoff_id",),
    "Werkstoffe nur für den Blech-Editor (Richtpreis für Blech- und Kantteile als Zukaufteil), getrennt von den "
    "Rohr-Werkstoffen. Preis je kg Tafelmaterial; die Kategorie wählt die Blechlaser-Richtwerte. K-Faktor = Lage der "
    "neutralen Faser (Anteil der Blechdicke von innen) für die Abwicklung von Kantteilen; leer = 0,33.")

BLECHLASER = Tabelle(
    "blechlaser", "Blechlaser (Richtwerte)",
    (Feld("kategorie", "Kategorie", "auswahl", auswahl="kategorie", pflicht=True, breite=90),
     Feld("gas", "Schneidgas", "auswahl", auswahl="gas", pflicht=True, breite=70),
     Feld("dicke_bis", "Blechdicke bis [mm]", "zahl", 0.1, 100, stellen=1, pflicht=True),
     Feld("vorschub", "Vorschub Außenkontur [mm/min]", "zahl", 1, 200000, stellen=0, pflicht=True),
     Feld("vorschub_innen", "Vorschub Innenkonturen [mm/min]", "zahl", 1, 200000, stellen=0),
     Feld("einstechzeit", "Einstechzeit [s]", "zahl", 0, 60, stellen=1),
     Feld("vorschub_gravur", "Vorschub Gravur [mm/min]", "zahl", 1, 200000, stellen=0),
     Feld("bemerkung", "Bemerkung", breite=160)),
    ("kategorie", "gas", "dicke_bis"),
    "Schneiddaten eines Flachbettlasers nur für den Richtpreis im Blech-Editor; sie gehören nicht zu den Rohrlaser-"
    "Maschinen. Je Kategorie und Schneidgas gestaffelt nach Blechdicke: es gilt die Zeile mit der kleinsten "
    "'Blechdicke bis', die mindestens der Blechdicke entspricht; N₂, solange es dafür eine Zeile gibt, darüber O₂. "
    "Leerer Vorschub Innenkonturen = halber Vorschub Außenkontur. Vorschub Gravur gilt für Text-Gravuren (z. B. "
    "Artikelnummer); leer = die Gravur kostet keine Zeit, der Blech-Editor zeigt einen Hinweis. Vorbelegt sind Richtwerte eines Faserlasers mit "
    "etwa 6 kW, bitte an den eigenen Blechlaser bzw. Lieferanten anpassen.")

# K-Faktoren der Abwicklung je Kategorie, Blechdicke und Innenradius ÷ Dicke (Plan S4, Patrick 23.10.2026 „2a“)
BLECH_KFAKTOREN = Tabelle(
    "blech_kfaktoren", "K-Faktoren (Abwicklung)",
    (Feld("kategorie", "Kategorie", "auswahl", auswahl="kategorie", pflicht=True, breite=90),
     Feld("dicke_bis", "Blechdicke bis [mm]", "zahl", 0.1, 100, stellen=1, pflicht=True),
     Feld("ri_s_bis", "Innenradius ÷ Dicke bis", "zahl", 0.01, 1000, stellen=2, pflicht=True),
     Feld("k_faktor", "K-Faktor", "zahl", 0.1, 0.5, stellen=3, pflicht=True),
     Feld("bemerkung", "Bemerkung", breite=200)),
    ("kategorie", "dicke_bis", "ri_s_bis"),
    "K-Faktor = Lage der neutralen Faser (Anteil der Blechdicke von innen) für die Abwicklung von Kantteilen im "
    "Blech-Editor, je Biegung nachgeschlagen: Zeile der Kategorie mit der kleinsten 'Blechdicke bis' ≥ Dicke, darin "
    "die kleinste 'Innenradius ÷ Dicke bis' ≥ Innenradius ÷ Dicke (größer als alle: die größte). Ohne passende Zeile "
    "gilt der K-Faktor des Blech-Werkstoffs. Vorbelegt sind Beispielwerte nach DIN 6935, bitte an die eigene "
    "Abkantpresse bzw. den Lieferanten anpassen. Einstellung 'Abwicklung: K-Faktor aus' = je Werkstoff schaltet "
    "die Tabelle ab.")

# Fertigungsprüfung (dfm.py, Plan S5): Regel, aktiv, Grenzwert, Stufe; Vorgaben und Beispielzeilen in dfm.REGELN
PRUEFREGELN = Tabelle(
    "pruefregeln", "Prüfregeln (Fertigung)",
    (Feld("regel", "Regel", "auswahl", auswahl="pruefregel", pflicht=True, breite=190),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("grenzwert", "Grenzwert [× Wand bzw. Dicke]", "zahl", 0, 100, stellen=2, breite=95),
     Feld("stufe", "Stufe", "auswahl", auswahl="pruefstufe", breite=90),
     Feld("bemerkung", "Bemerkung", breite=360)),
    ("regel",),
    "Fertigungsprüfung für Rohr- und Blechteile: jede Regel einzeln an- oder abschaltbar, mit Grenzwert und Stufe "
    "(HINWEIS, WARNUNG oder FEHLER), die im Status der Position erscheint. Bohrung zu klein, Steg zu schmal und "
    "Kontur zu nah am Rand rechnen mit Grenzwert × Wandstärke bzw. Blechdicke; Teil zu kurz mit 'Kürzestes Teil' "
    "der Maschine; Kantbarkeit mit den Faktoren unter Einstellungen. Fehlt eine Regel, gilt ihre Vorgabe; leerer "
    "Grenzwert = Vorgabe. Alle Vorgaben sind Startwerte, bitte an die eigene Fertigung anpassen.")

# Schweißbaugruppen (Patrick 23.10.2026, Plan 3a/4a): Schweißzeit je Nahtgruppe aus Lichtbogenzeit je m Naht
# (Verfahren × Nahtart × a-Maß bzw. Blechdicke) × Faktoren, geteilt durch den Lichtbogenzeitfaktor des Verfahrens,
# dazu Heftpunkte. Neue Dateien bekommen die Tabellen leer; 'Richtwerte laden' (baugruppe.richtwerte) trägt
# hergeleitete Richtwerte mit Status 'Richtwert' ein, die die Kalkulation als HINWEIS kennzeichnet.
NAHTARTEN = ("Kehlnaht", "Stumpfnaht", "Ecknaht")
SCHWEISS_FAKTORARTEN = ("Schweißlage", "Zugänglichkeit", "Qualität", "Werkstoff")    # Werkstoff: Plan 28.10.2026
KENNWERT_STATUS = ("Richtwert", "geprüft")

SCHWEISSVERFAHREN = Tabelle(
    "schweissverfahren", "Schweißverfahren",
    (Feld("verfahren", "Verfahren", pflicht=True, breite=110),
     Feld("bezeichnung", "Bezeichnung", breite=220),
     Feld("satz_id", "Stundensatz-ID", "auswahl", auswahl="zusatzsatz", pflicht=True, breite=110),
     Feld("lichtbogen", "Lichtbogenzeitfaktor [%]", "zahl", 1, 100, stellen=0, pflicht=True, breite=95),
     Feld("heft_s", "Zeit je Heftpunkt [s]", "zahl", 0, 600, stellen=1, breite=80),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("status", "Status", "auswahl", auswahl="kennwertstatus", breite=85),
     Feld("bemerkung", "Bemerkung", breite=260),
     # Verbrauch (P5, Schema 50): leer = Schweißzusatz und Gas stecken im Stundensatz
     Feld("dichte", "Dichte Schweißzusatz [kg/dm³]", "zahl", 0.5, 25, stellen=2, breite=90),
     Feld("draht_eur_kg", "Preis Schweißzusatz [€/kg]", "zahl", 0, 1000, stellen=2, breite=90),
     Feld("gas_l_min", "Schutzgas [l/min]", "zahl", 0, 100, stellen=1, breite=80),
     Feld("gas_eur_l", "Preis Schutzgas [€/l]", "zahl", 0, 100, stellen=4, breite=80)),
    ("verfahren",),
    "Schweißverfahren der Baugruppen-Kalkulation (MAG, MIG, WIG, E-Hand, Heften, Roboter … frei erweiterbar). "
    "Lichtbogenzeitfaktor = Anteil der Lichtbogenzeit an der Schweißarbeitszeit: Arbeitszeit = Lichtbogenzeit ÷ "
    "Faktor (Nebenzeiten wie Brenner ansetzen, Schlacke entfernen, Drahtwechsel). Heftpunkte rechnen mit der Zeit "
    "je Heftpunkt. Kosten = Zeit × Stundensatz. Status 'Richtwert' = noch nicht an der eigenen Fertigung geprüft. "
    "Schweißzusatz und Schutzgas (optional): Draht = Nahtquerschnitt × Nahtlänge × Dichte, Gas = Lichtbogenzeit × "
    "l/min, jeweils × Preis; leer = steckt im Stundensatz. Fehlt nur ein Teil der Werte, zählt er 0 € mit Hinweis.")

SCHWEISS_KENNWERTE = Tabelle(
    "schweiss_kennwerte", "Schweiß-Kennwerte",
    (Feld("verfahren", "Verfahren", "auswahl", auswahl="schweissverfahren", pflicht=True, breite=100),
     Feld("nahtart", "Nahtart", "auswahl", auswahl="nahtart", pflicht=True, breite=100),
     Feld("mass_bis", "a-Maß bzw. Blechdicke bis [mm]", "zahl", 0.5, 100, stellen=1, pflicht=True, breite=95),
     Feld("min_m", "Lichtbogenzeit [min je m Naht]", "zahl", 0.01, 1000, stellen=2, pflicht=True, breite=100),
     Feld("status", "Status", "auswahl", auswahl="kennwertstatus", breite=85),
     Feld("bemerkung", "Herkunft / Bemerkung", breite=300)),
    ("verfahren", "nahtart", "mass_bis"),
    "Lichtbogenzeit je m Naht (eine Lage bzw. alle Lagen zusammen) nach Verfahren, Nahtart und Nahtgröße: Kehlnaht "
    "nach a-Maß, Stumpf- und Ecknaht nach Blechdicke. Es gilt die Zeile mit dem kleinsten 'bis', das mindestens der "
    "Nahtgröße entspricht; größer als alle Zeilen = kein Kennwert (Warnung, Zeit von Hand eintragen). Beidseitige "
    "Nähte zählen doppelt.")

SCHWEISS_FAKTOREN = Tabelle(
    "schweiss_faktoren", "Schweiß-Faktoren",
    (Feld("art", "Art", "auswahl", auswahl="schweissfaktorart", pflicht=True, breite=110),
     Feld("wert", "Ausprägung", pflicht=True, breite=200),
     Feld("faktor", "Faktor auf die Lichtbogenzeit", "zahl", 0.1, 10, stellen=2, pflicht=True, breite=100),
     Feld("status", "Status", "auswahl", auswahl="kennwertstatus", breite=85),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("art", "wert"),
    "Zuschläge auf die Lichtbogenzeit je Nahtgruppe: Schweißlage (PA Wannenlage … PE Überkopf), Zugänglichkeit, "
    "Qualitätsanforderung und Werkstoff (Kategorie der Teile: Stahl, Edelstahl, Aluminium, Buntmetall). Leer bzw. "
    "nicht gefunden = Faktor 1.")

# Vorkalkulation der Schweißbaugruppe (Plan Vorkalkulation, Patrick 24.10.2026 „alles a außer 8b“, vorkalk.py):
# Regelwerte für Rüsten, Positionieren je Positionierhilfe, Heften, Wenden und Nacharbeit; neue Dateien leer,
# 'Richtwerte laden' trägt Richtwerte mit Status 'Richtwert' ein
SCHWEISSREGEL_ARTEN = ("Rüsten", "Positionieren", "Heften", "Heftabstand", "Wenden", "Nacharbeit",
                       "Nachbehandlung", "Richten", "Prüfen",         # Plan 28.10.2026, Schritt 2
                       "Heftzeit", "Mehrlagig")                       # Plan 28.10.2026, Schritt 5
POSITIONIERHILFEN = ("Steckverbindung", "Vorrichtung", "Gravur", "frei")      # beste zuerst
NACHARBEIT_STUFEN = ("keine", "Spritzer entfernen", "Naht verschleifen", "bündig planschleifen")

SCHWEISS_REGELN = Tabelle(
    "schweiss_regeln", "Schweiß-Vorkalkulation",
    (Feld("art", "Art", "auswahl", auswahl="schweissregelart", pflicht=True, breite=100),
     Feld("wert", "Ausprägung", pflicht=True, breite=190),
     Feld("bis", "bis Wanddicke [mm] bzw. Gewicht [kg]", "zahl", 0, 100000, stellen=1, breite=95),
     Feld("zahl", "Wert", "zahl", 0, 100000, stellen=2, pflicht=True, breite=80),
     Feld("einheit", "Einheit", breite=90),
     Feld("status", "Status", "auswahl", auswahl="kennwertstatus", breite=85),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("art", "wert"),
    "Regeln der Vorkalkulation im Baugruppen-Editor (Knopf 'Vorkalkulation rechnen'): Rüsten einmalig je Auftrag = "
    "Grundrüstzeit + Zeit je Teilenummer (+ Vorrichtung); Positionieren je Baugruppe = Teile × Zeit je Teil nach "
    "Positionierhilfe (Steckverbindung, Vorrichtung, Gravur, frei; das erste Teil jeder Unterbaugruppe als Basisteil); "
    "Heftpunkte je Naht = größer von Mindestzahl und aufrunden(Nahtlänge ÷ Heftabstand) + 1 für die Enden (nach "
    "kleinerer Wanddicke, gesteckt bzw. Edelstahl/Aluminium × Faktor; rundum ohne + 1, mindestens Umfang ÷ Umfang je "
    "Heftpunkt); Heftzeit × Faktor nach Wanddicke; Mehrlagig: Nähte über 'a je Lage' mit Zeit je Zusatzlage; Wenden = Anzahl × Zeit × Faktor nach Gewicht; Nacharbeit in min je m Naht je Stufe; Beizen bei "
    "Edelstahl, Richten (viel Naht je kg bei dünner Wand) und Sichtprüfung in min je m Naht. Das Ergebnis sind "
    "Vorschläge, die man im Editor bestätigt oder überschreibt. Status 'Richtwert' = noch nicht geprüft.")

# STEP-Import je Kunde (importprofil.py): wie Artikelnummern entstehen, Normteile, Vorgaben des Prüfdialogs
BENENNUNGEN = ("Bauteilname", "Dateiname", "Dateiname + Bauteilname")
DARSTELLUNG_3D = ("Automatisch", "Software", "OpenGL")       # wie ansicht3d.RENDERER
ABWICKLUNG_K = ("K-Faktor-Tabelle", "je Werkstoff")            # wie blech.ABWICKLUNG_K
MATERIAL_AUS = ("Tafelausnutzung", "pauschaler Verschnitt")    # wie blech.MATERIAL_AUS
IMPORTPROFILE = Tabelle(
    "importprofile", "Importprofile (STEP)",
    (Feld("kundennr", "Kunde", "auswahl", auswahl="kunde", pflicht=True, breite=110),
     Feld("benennung", "Artikel aus", "auswahl", auswahl="benennung", breite=170),
     Feld("muster", "Artikelnummer im Namen (Muster)", breite=170),
     Feld("normteile", "Normteile zusätzlich (Begriffe mit ; getrennt)", breite=200),
     Feld("werkstoff_id", "Werkstoff Rohre/Profile", "auswahl", auswahl="werkstoff", breite=120),
     Feld("flach_als", "Flache Teile als", "auswahl", auswahl="flachals", breite=150),
     Feld("anbau_weglassen", "Anbauteile nicht übernehmen", "auswahl", auswahl="janein", breite=90),
     # Plan Angebotsablauf V4: Zusatzarbeiten für alle Teile dieses Kunden (Namen mit ; getrennt, z. B. Feuerverzinken)
     Feld("zusatz", "Zusatzarbeiten für alle Teile (mit ; getrennt)", breite=180),
     Feld("bemerkung", "Bemerkung", breite=160)),
    ("kundennr",),
    "Vorgaben für den STEP-Import je Kunde; sie gelten in Angeboten dieses Kunden, leere Felder wie in den "
    "Einstellungen. Artikel aus: Bauteilname (Name in der Konstruktion, ohne Namen wie bisher der Dateiname), "
    "Dateiname oder beides. Artikelnummer im Namen: regulärer Ausdruck, sein erster Klammerausdruck (sonst der ganze "
    "Treffer) wird die Artikelnummer und der ganze Name die Bezeichnung, z. B. ^(\\d+) für führende Ziffern. "
    "Normteile zusätzlich: Begriffe zu denen aus der Einstellung, Teile mit diesen Wörtern im Namen sind im "
    "Prüfdialog abgewählt.")

# Regeln für Arbeitsgang-Vorschläge (Wettbewerbsvergleich P1-4, arbeitsgaenge.py): Bedingungen aus Profil, Werkstoff,
# Oberfläche, Kunde, Stichwort und Merkmal der Position schlagen eine Zusatzarbeit vor; gerechnet wird sie erst, wenn
# sie im Angebot angenommen ist (dann steht sie mit Preisstand in den Zusatzarbeiten der Position)
REGEL_MERKMALE = ("immer", "Gewinde", "Bohrungen", "Innenkonturen", "Schräges Ende", "Zukaufteil",
                  "Schweißbaugruppe", "Rohr/Profil", "Blech")
REGEL_MENGEN = ("automatisch", "Innen- + Außenfläche", "Anzahl Gewinde", "Anzahl Bohrungen", "Anzahl Innenkonturen")
# Plan Abrechnungsregeln 28.10.2026: Zuordnung der Regel (leer = Vorschlag wie bisher), siehe zusatz_regeln.py
REGEL_ZUORDNUNGEN = ("Vorschlag", "automatisch", "nur Preis")
AUFPREIS_BASEN = ("€/m", "€/kg", "€/m²")
ARBEITSGANG_REGELN = Tabelle(
    "arbeitsgang_regeln", "Arbeitsgang-Regeln",
    (Feld("name", "Regel", pflicht=True, breite=150),
     Feld("zusatzarbeit", "Zusatzarbeit", pflicht=True, breite=150),
     Feld("zuordnung", "Zuordnung", "auswahl", auswahl="regelzuordnung", breite=95),
     Feld("merkmal", "Wenn Merkmal", "auswahl", auswahl="regelmerkmal", breite=110),
     Feld("stichwort", "Stichwörter in Bezeichnung/Artikel (; getrennt)", breite=170),
     Feld("profilform", "Profilform", "auswahl", auswahl="profilform", breite=100),
     Feld("kategorie", "Werkstoff-Kategorie", "auswahl", auswahl="kategorie", breite=100),
     Feld("werkstoff_id", "Werkstoff-ID", "auswahl", auswahl="werkstoff", breite=110),
     Feld("oberflaeche", "Oberfläche", "auswahl", auswahl="oberflaeche", breite=90),
     Feld("kundennr", "Kunde", "auswahl", auswahl="kunde", breite=100),
     Feld("min_stueck", "ab Stückzahl", "ganz", 0, 1000000, breite=70),
     Feld("menge_art", "Menge je Teil", "auswahl", auswahl="regelmenge", breite=120),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=60),
     Feld("bemerkung", "Bemerkung", breite=200),
     # Plan Abrechnungsregeln 28.10.2026 (leer = wie die Zusatzarbeit): Abmessung, Preis, Faktor, Mindest je Teil
     Feld("a_von", "Abmessung von [mm]", "zahl", 0, 100000, stellen=1, breite=75),
     Feld("a_bis", "Abmessung bis [mm]", "zahl", 0, 100000, stellen=1, breite=75),
     Feld("art", "Abrechnung (leer = wie Zusatzarbeit)", "auswahl", auswahl="zusatzart", breite=90),
     Feld("preis", "Preis je Einheit [€] (leer = wie Zusatzarbeit)", "zahl", 0, 100000, stellen=2, breite=95),
     Feld("faktor", "Faktor Menge", "zahl", 0.01, 100, stellen=3, breite=70),
     Feld("mindest_teil", "Mindestbetrag je Teil [€]", "zahl", 0, 100000, stellen=2, breite=90)),
    ("name",),
    "Regeln für „Arbeitsgänge vorschlagen …“ im Angebot: Trifft eine Position alle ausgefüllten Bedingungen "
    "(leer = egal; Stichwörter: eines genügt, Groß-/Kleinschreibung egal), schlägt das Programm die Zusatzarbeit vor. "
    "Ein Vorschlag kostet nichts, bis er im Angebot angenommen ist; dann steht er mit Preisstand und Herkunft "
    "„Regel: …“ in den Zusatzarbeiten der Position. Abgelehnte Vorschläge merkt sich die Position. Menge je Teil: "
    "automatisch = wie in den Zusatzarbeiten (kg, m², m bzw. 1 Stück), sonst Innen- + Außenfläche oder die Anzahl "
    "Gewinde, Bohrungen oder Innenkonturen des Teils. Zuordnung: Vorschlag (leer, wie bisher), automatisch (die "
    "Zusatzarbeit gilt ohne Klick, gelb markiert „automatisch“, abwählbar in „Arbeitsgänge vorschlagen …“) oder "
    "nur Preis (ordnet nichts zu). Abrechnung, Preis je Einheit, Faktor und Mindestbetrag je Teil gelten für die "
    "Zusatzarbeit an jeder passenden Position, gleich wie sie dorthin kam (leer = wie die Zusatzarbeit); "
    "Abmessung = größtes Außenmaß des Profils (Ø, Höhe oder Breite). Passen mehrere Regeln, gewinnt die genaueste "
    "(meiste Bedingungen), bei Gleichstand die obere. Beispiel: Strahlen Stahl 0,35 €/kg, Edelstahl 0,55 €/kg. "
    "Gewinde, Senken, Flowdrill und Bohren rechnen immer € je Stück.",
    pruefung=_pruefung_regel)


# Plan Arbeitsabläufe W2 (Freigabe F3b): Vorgaben je Kunde für den Angebotskopf, getrennt von den Importprofilen;
# angewandt von kundenvorgabe.py beim Anlegen eines Angebots und beim Wählen des Kunden
KUNDENVORGABEN = Tabelle(
    "kundenvorgaben", "Kundenvorgaben",
    (Feld("kundennr", "Kunde", "auswahl", auswahl="kunde", pflicht=True, breite=110),
     Feld("maschine", "Maschine", "auswahl", auswahl="maschine", breite=110),
     Feld("stange", "Stangenlänge [mm]", "ganz", 500, 20000, breite=85),
     Feld("gewinn", "Gewinn [%]", "zahl", 0, 500, stellen=1, breite=70),
     Feld("lieferzeit_art", "Lieferzeit als", "auswahl", auswahl="lieferzeitart", breite=110),
     Feld("lieferzeit_wert", "Lieferzeit", breite=80),
     Feld("lieferzeit_zusatz", "Lieferbedingungen (Freitext)", breite=170),
     Feld("material_vorgabe", "Material neuer Positionen", "auswahl", auswahl="materialherkunft", breite=120),
     Feld("staffeln", "Standard-Staffeln (Faktoren, 0 = keine)", breite=120),
     Feld("bemerkung", "Bemerkung", breite=160)),
    ("kundennr",),
    "Vorgaben je Kunde für neue Angebote: Wählen Sie im Angebot den Kunden, übernimmt das Programm Maschine, "
    "Stangenlänge, Gewinn, Lieferzeit, Material und Standard-Staffeln von hier. Ein Feld im Angebot wird nur "
    "ersetzt, solange es noch die Vorgabe aus den Einstellungen (oder des vorher gewählten Kunden) hat. Leere "
    "Felder = Einstellungen.")

# Baugruppen-Vorlagen (Verbesserung P1): Struktur, Nahtgruppen und Arbeitsgänge einer Schweißbaugruppe ohne
# Einzelteile (JSON in 'daten', baugruppe.vorlage_aus). Gepflegt im Editor der Baugruppe, nicht als Stammdaten-Reiter;
# mit den übrigen Stammdaten zwischen Arbeitsplätzen geteilt.
BAUGRUPPEN_VORLAGEN = Tabelle(
    "baugruppen_vorlagen", "Baugruppen-Vorlagen",
    (Feld("name", "Vorlage", pflicht=True, breite=200),
     Feld("inhalt", "Inhalt", breite=260),
     Feld("daten", "Daten", breite=100),
     Feld("angelegt", "Angelegt", breite=130),
     Feld("bemerkung", "Bemerkung", breite=200)),
    ("name",),
    "Vorlagen für Schweißbaugruppen: im Editor der Baugruppe speichern und in neue Baugruppen einsetzen.")


# Kontur-Vorlagen (Plan 3D-Editor E1, Schritt 3E-6): Konturzeilen als JSON in 'konturen' (konturvorlagen.py). Gepflegt
# im Teile-Editor, nicht als Stammdaten-Reiter; mit den übrigen Stammdaten zwischen Arbeitsplätzen geteilt.
KONTUR_VORLAGEN = Tabelle(
    "kontur_vorlagen", "Kontur-Vorlagen",
    (Feld("name", "Vorlage", pflicht=True, breite=200),
     Feld("art", "Rohr/Blech", breite=70),
     Feld("kunde", "Nur für Kunde", breite=110),
     Feld("profilform", "Profilform", breite=110),
     Feld("inhalt", "Inhalt", breite=260),
     Feld("konturen", "Konturen", breite=100),
     Feld("angelegt", "Angelegt", breite=130),
     Feld("bemerkung", "Bemerkung", breite=200)),
    ("name", "art", "kunde"),
    "Kontur-Vorlagen (z. B. Bohrbild, Steckverbindung): im Teile-Editor speichern und in andere Teile einsetzen.")

TABELLEN = (KUNDEN, PROFILE, WERKSTOFFE, OBERFLAECHEN, PREISE, LIEFERLAENGEN, MASCHINEN, SCHNEIDDATEN, GEWINDE,
            ZUSATZARBEITEN, STUNDENSAETZE, ARBEITSSCHRITTE, BLECH_WERKSTOFFE, BLECHLASER, BLECH_KFAKTOREN,
            PRUEFREGELN, SCHWEISSVERFAHREN,
            SCHWEISS_KENNWERTE, SCHWEISS_FAKTOREN, SCHWEISS_REGELN, IMPORTPROFILE, KUNDENVORGABEN,
            ARBEITSGANG_REGELN)
TABELLE = {t.name: t for t in TABELLEN}

# Schlüssel, auf die andere Tabellen verweisen: beim Umbenennen werden die Verweise mitgeändert
VERWEISE = {
    ("kunden", "kundennr"): (("angebote", "kundennr"), ("importprofile", "kundennr"), ("kundenvorgaben", "kundennr")),
    ("profile", "profil_id"): (("preise", "profil_id"), ("lieferlaengen", "profil_id")),
    ("werkstoffe", "werkstoff_id"): (("preise", "werkstoff_id"), ("lieferlaengen", "werkstoff_id"),
                                     ("schneiddaten", "werkstoff_id")),
    # Angebote: dazu die Snapshots im Angebot und die Standard-Maschine (Datenbank._maschine_umbenannt)
    ("maschinen", "maschinen_id"): (("schneiddaten", "maschinen_id"), ("angebote", "maschine"),
                                    ("kundenvorgaben", "maschine")),
    ("stundensaetze", "satz_id"): (("arbeitsschritte", "satz"), ("zusatzarbeiten", "satz_id"),
                                   ("schweissverfahren", "satz_id")),
    ("schweissverfahren", "verfahren"): (("schweiss_kennwerte", "verfahren"),),
}


# Lieferzeit im Angebot (angebot.lieferzeit_wert / lieferzeit_text): Art der Angabe
ARBEITSTAGE, WOCHEN, KALENDERWOCHE, LIEFERDATUM, NUR_TEXT = (
    "Arbeitstage", "Wochen", "Kalenderwoche", "Lieferdatum", "nur Text")
LIEFERZEIT_ARTEN = (ARBEITSTAGE, WOCHEN, KALENDERWOCHE, LIEFERDATUM, NUR_TEXT)
# Was der Laser an einer Fließlochbohrung (Flowdrill) macht (bohrbild.py): Markierung als Gravur oder kleines Loch
FLIESSLOCH_LASER = ("Gravur Ø0,5", "Loch Ø0,5")
# Bohrung kleiner als 0,7 × Wand (Bohren): wie Flowdrill markieren und aufbohren, oder als 3. Option den Ø trotzdem
# schneiden, ohne anschließendes Bohren (Patrick 27.10.2026)
BOHREN_SCHNEIDEN = "Ø schneiden (ohne Bohren)"
BOHREN_LASER = FLIESSLOCH_LASER + (BOHREN_SCHNEIDEN,)
# STEP-Import, Vorgabe für ebene flache Teile (Patrick 22.10.2026: vorerst immer Blech, Flachstahl im Prüfdialog wählbar)
FLACH_ALS = ("Blech", "Flachstahl bis Breite (Einstellung darunter)")
# Herkunft des Materials je Position (angebot.POSITIONEN 'material_herkunft'): leer = Eigenmaterial (wie bisher);
# Kundenmaterial: keine Materialkosten, eigene Stangengruppe, Bearbeitung wie sonst
EIGENMATERIAL, KUNDENMATERIAL = "Eigenmaterial", "Kunde beigestellt"
MATERIAL_HERKUNFT = (EIGENMATERIAL, KUNDENMATERIAL)
# Musterkosten im Angebot (angebot.KOPF 'muster_darstellung'): leer = auf die Serie umlegen (Patrick 28.10.2026, F1 a)
MUSTER_UMLEGEN, MUSTER_ZEILE = "auf die Serie umlegen", "eigene Zeile Musterkosten"
MUSTER_DARSTELLUNG = (MUSTER_UMLEGEN, MUSTER_ZEILE)
# Abruf-/Rahmenangebot (angebot.KOPF 'abruf_material', Patrick 30.10.2026, 4 a und b): leer = Material je Abruf zum
# Tagespreis mit Materialklausel, ABRUF_LAGER = Jahresbedarf bevorraten mit Lagerzins
ABRUF_JE, ABRUF_LAGER = "je Abruf (Materialklausel)", "Jahresbedarf bevorraten"
ABRUF_MATERIAL = (ABRUF_JE, ABRUF_LAGER)
# Löschschutz der Angebote (Patrick 28.10.2026): einmal optimierte Angebote lassen sich nicht mehr löschen (Admin schon)
LOESCHSCHUTZ_AUS, LOESCHSCHUTZ_JEDES, LOESCHSCHUTZ_HAND = "aus", "immer", "nur von Hand"
LOESCHSCHUTZ = (LOESCHSCHUTZ_AUS, LOESCHSCHUTZ_JEDES, LOESCHSCHUTZ_HAND)
# Zeitraum der Angebotsliste (Patrick 29.10.2026): Angebote mit Datum oder Änderung in den letzten N Tagen
ZEITRAUM_ALLE = "Alle"
ZEITRAUM = {"30 Tage": 30, "60 Tage": 60, "100 Tage": 100, "150 Tage": 150, "365 Tage": 365, ZEITRAUM_ALLE: None}


# ------------------------------------------------------------------ Einstellungen
# Arbeitsschritte des Palettenscheins (wie im Palettenschein-Tool v97): je Zeile 'Gruppe: Schritt'
VERSAND_SCHRITTE = "\n".join(
    [f"Intern: {x}" for x in ("Rohrlaser", "Entgraten", "Bohren", "Flowdrill", "Senken", "Passungen", "Gewinde",
                              "Schweißen", "Schleifen", "Einziehmuttern")]
    + [f"Extern: {x}" for x in ("Blechzukauf", "CNC-Bearbeitung", "Rohr biegen", "Schweißen", "Glühen")]
    + [f"Oberfläche: {x}" for x in ("Strahlen", "Feuerverzinken", "galvanisch Verzinken", "Lackieren",
                                    "Pulverbeschichten", "Polieren", "Brünieren", "Bürsten", "Gleitschleifen",
                                    "KTL-Beschichtung", "Nasslackierung", "Grundieren", "Beizen", "Passivieren",
                                    "Elektropolieren", "Eloxieren", "Harteloxieren", "Phosphatieren", "Laserpolieren",
                                    "Verchromen", "Vernickeln")])


@dataclass(frozen=True)
class Einstellung:
    name: str
    titel: str
    gruppe: str
    art: str                # text | zahl | ganz | anteil | mehrzeilig | auswahl | passwort | bild | ordner
    vorgabe: object
    von: float = None
    bis: float = None
    auswahl: str = None


EINSTELLUNGEN = (
    Einstellung("zuschlag_material", "Zuschlag Material", "Kalkulation", "anteil", 0, 0, 5),
    Einstellung("zuschlag_fertigung", "Zuschlag Fertigung", "Kalkulation", "anteil", 0, 0, 5),
    Einstellung("zuschlag_fremdleistung", "Zuschlag Fremdleistung", "Kalkulation", "anteil", 0.10, 0, 5),
    # Vorgabe neuer Angebote: Aufschlag auf alle Bleche bzw. alle übrigen Zukaufteile (ersetzt Artikel-/Kategorie-
    # und Standardaufschlag im Angebot; Patrick 25.10.2026)
    Einstellung("aufschlag_blech", "Aufschlag Bleche im Angebot", "Kalkulation", "anteil", 0.10, 0, 10),
    Einstellung("aufschlag_zukauf", "Aufschlag Zukaufteile im Angebot", "Kalkulation", "anteil", 0.10, 0, 10),
    Einstellung("gewinn", "Gewinn", "Kalkulation", "anteil", 0.10, 0, 5),
    # Standardaufschlag der Anwendung für Zukaufteile (gilt, wenn weder Artikel noch Kategorie einen haben);
    # leer = keiner (das Programm warnt dann)
    Einstellung("zukauf_aufschlag", "Standardaufschlag Zukaufteile [% auf Einstand] (leer = keiner)", "Kalkulation",
                "zahl_leer", None, 0, 1000),
    Einstellung("ruesten_abmessung", "Rüstzeit je Abmessung [min]", "Kalkulation", "zahl", 15.0, 0, 1440),
    # Rüsten als fester Betrag statt Minuten × Stundensatz (Patrick 26.10.2026), Vorgabe neuer Angebote; leer = Minuten
    Einstellung("ruesten_abmessung_eur", "Rüsten je Abmessung als Betrag [€] (leer = Minuten)", "Kalkulation",
                "zahl_leer", None, 0, 100000),
    Einstellung("ruesten_angebot_eur", "Rüsten je Angebot als Betrag [€] (leer = Minuten der Maschine)", "Kalkulation",
                "zahl_leer", None, 0, 100000),
    Einstellung("pauschale_abmessung", "Pauschale je Abmessung [€]", "Kalkulation", "zahl", 0.0, 0, 100000),
    # Programmierung als Zeit × Stundensatz 'Programmierung' (Patrick 22.10.2026; bis 0.8.21: 8,50 € je Position):
    # Grundzeit je Position + Zeit je Innenkontur, je Position von Hand überschreibbar
    Einstellung("programmierung_zeit", "Programmierzeit je Position [min]", "Kalkulation", "zahl", 5.0, 0, 1440),
    Einstellung("programmierung_kontur", "Programmierzeit je Innenkontur [min]", "Kalkulation", "zahl", 0.5, 0, 1440),
    Einstellung("angebotsaufschlag", "Angebotsaufschlag je Angebot [€]", "Kalkulation", "zahl", 50.0, 0, 100000),
    # Patrick 22.10.2026 (F4 a): eigene Zeit je Teil, dessen Anbauteile unsicher erkannt sind (Stundensatz Laser)
    Einstellung("pruefzeit_anbau", "Prüfzeit je Teil mit unsicher erkannten Anbauteilen [min]", "Kalkulation",
                "zahl", 0.0, 0, 1000),
    # Plan „Kalkulation und Berechnung verbessern“ (Patrick 29.10.2026): Ausschuss auf Material und Laserzeit,
    # Schrotterlös des Verschnitts als Gutschrift, Preiseinheit 100/1000 Stück für Kleinteile im Angebots-PDF
    Einstellung("ausschuss", "Ausschuss Rohrlaserteile [%]", "Kalkulation",
                "anteil", 0, 0, 0.5),
    Einstellung("schrott_anteil", "Schrotterlös Verschnitt [%]",
                "Kalkulation", "anteil", 0, 0, 1),
    Einstellung("preiseinheit_ab", "Preis je 100 Stück unter [€]", "Kalkulation", "zahl", 0.0, 0, 100),
    # Schneidgas aus Düse und Gasdruck der Schneiddaten (Patrick 29.10.2026): Preis je Norm-m³, 0 = Zuschlag €/h der
    # Maschine; Korrekturfaktor gleicht die Rechnung an den gemessenen Verbrauch an
    # Gestaffelter Gewinn (Patrick 29.10.2026): bis Auftragswert (Selbstkosten des Angebots bzw. der Staffelstufe ohne
    # Zukaufteile) Grenze 1 gilt Satz 1 usw.; Grenze 1 = 0 (Vorgabe) = aus, dann gilt der feste Gewinn
    Einstellung("gewinn_bis_1", "Gewinn gestaffelt: Grenze 1 bis Auftragswert [€]", "Kalkulation", "zahl", 0.0, 0, 1e7),
    Einstellung("gewinn_satz_1", "Gewinn gestaffelt: Satz 1 bis Grenze 1", "Kalkulation", "anteil", 0.0, 0, 5),
    Einstellung("gewinn_bis_2", "Gewinn gestaffelt: Grenze 2 bis Auftragswert [€]", "Kalkulation", "zahl", 0.0, 0, 1e7),
    Einstellung("gewinn_satz_2", "Gewinn gestaffelt: Satz 2 bis Grenze 2", "Kalkulation", "anteil", 0.0, 0, 5),
    Einstellung("gewinn_bis_3", "Gewinn gestaffelt: Grenze 3 bis Auftragswert [€]", "Kalkulation", "zahl", 0.0, 0, 1e7),
    Einstellung("gewinn_satz_3", "Gewinn gestaffelt: Satz 3 bis Grenze 3", "Kalkulation", "anteil", 0.0, 0, 5),
    Einstellung("gewinn_bis_4", "Gewinn gestaffelt: Grenze 4 bis Auftragswert [€]", "Kalkulation", "zahl", 0.0, 0, 1e7),
    Einstellung("gewinn_satz_4", "Gewinn gestaffelt: Satz 4 bis Grenze 4", "Kalkulation", "anteil", 0.0, 0, 5),
    Einstellung("gewinn_satz_5", "Gewinn gestaffelt: Satz über der letzten Grenze", "Kalkulation", "anteil", 0.0, 0, 5),
    Einstellung("gas_rechnen", "Schneidgas rechnen (nein = für alle Maschinen aus)", "Kalkulation", "auswahl", "ja",
                auswahl="janein"),
    Einstellung("gaspreis_n2", "Gaspreis N₂ [€/m³]", "Kalkulation", "zahl", 0.0, 0, 100),
    Einstellung("gaspreis_o2", "Gaspreis O₂ [€/m³]", "Kalkulation", "zahl", 0.0, 0, 100),
    Einstellung("gas_faktor", "Korrekturfaktor Gasverbrauch", "Kalkulation", "zahl", 1.0, 0.1, 5),
    # Stundensatz-Ermittlung je Maschine (Patrick 29.10.2026, stundensatz.py): für alle Maschinen gleich
    Einstellung("strompreis", "Stundensatz-Ermittlung: Strompreis [€/kWh]", "Kalkulation", "zahl", 0.25, 0, 10),
    Einstellung("raumkosten", "Stundensatz-Ermittlung: Raumkosten [€/m² im Monat]", "Kalkulation", "zahl", 8.0, 0,
                1000),
    Einstellung("zinssatz", "Stundensatz-Ermittlung: Zinssatz [%]", "Kalkulation", "anteil", 0.06, 0, 0.5),
    Einstellung("bediener_satz", "Stundensatz-Ermittlung: Bedienerlohn [€/h]", "Kalkulation", "zahl", 38.0, 0, 1000),
    Einstellung("gemeinkosten", "Stundensatz-Ermittlung: Gemeinkosten [%]", "Kalkulation", "anteil", 0.25, 0, 5),
    Einstellung("arbeitstage", "Stundensatz-Ermittlung: Arbeitstage je Jahr", "Kalkulation", "zahl", 220.0, 0, 366),
    Einstellung("auslastung_jahr", "Stundensatz-Ermittlung: Auslastung [%]", "Kalkulation", "anteil", 0.75, 0, 1),
    # Mindestangebotspreis netto (nach Skonto, vor MwSt) für neue Angebote; darunter werden die Stückpreise anteilig
    # angehoben. 0 = keiner.
    # Kundenmaterial (Spalte Material: Kunde beigestellt): keine Materialkosten; optional Handling je m der
    # beigestellten Stangen mit Zuschlag Fertigung und Gewinn. Vorgabe 0 = aus
    Einstellung("handling_beistellung", "Handling Kundenmaterial je m Stangenlänge [€/m] (0 = keins)",
                "Kalkulation", "zahl", 0.0, 0, 1000),
    # im Angebots-PDF: Hinweis, welche Stangen der Kunde beistellen muss
    Einstellung("beistellung_hinweis", "Angebots-PDF: Hinweis zum Kundenmaterial mit Stangenbedarf", "Angebots-PDF",
                "auswahl", "ja", auswahl="janein"),
    # Musterteile (Patrick 28.10.2026, F6 a): Hinweis im Angebots-PDF, was die Muster ohne Serienbestellung kosten;
    # {betrag} = Musterkosten netto, {datum} = Angebotsdatum + Frist, {pos} = Positionen der Muster. Leer = kein Hinweis
    Einstellung("muster_hinweis", "Angebots-PDF: Hinweis zu Musterteilen (leer = keiner)", "Angebots-PDF", "mehrzeilig",
                "Die Muster (Pos. {pos}) sind im Serienpreis enthalten. Wird bis {datum} keine Serie bestellt, "
                "berechnen wir die Muster mit {betrag} € netto."),
    Einstellung("muster_frist", "Angebots-PDF: Frist für die Serienbestellung nach Musterlieferung [Tage]",
                "Angebots-PDF", "ganz", 90, 0, 3650),
    # Abruf-/Rahmenangebot (Patrick 30.10.2026, 4 und 6a): Vorgaben für neue Abruf-Angebote und Textbausteine des
    # Blocks „Rahmenbedingungen“ im Angebots-PDF. Platzhalter siehe abruf.rahmentext
    Einstellung("abruf_lagerzins", "Abruf-Angebot: Lagerzins bei bevorratetem Material [% p. a.]", "Kalkulation",
                "zahl", 8.0, 0, 100),
    Einstellung("abruf_laufzeit", "Abruf-Angebot: Laufzeit und Preisbindung [Monate]", "Kalkulation", "ganz", 12, 1,
                120),
    Einstellung("abruf_klausel", "Abruf-Angebot: Materialklausel ab Preisänderung [%]", "Angebots-PDF", "zahl", 5.0, 0,
                100),
    Einstellung("abruf_text", "Abruf-Angebot: Rahmenbedingungen im PDF", "Angebots-PDF", "mehrzeilig",
                "Rahmenangebot über {jahr} Stück je Jahr, Abruf in Losen von {abruf} Stück (ca. {abrufe} Abrufe je "
                "Jahr). Die Preise gelten {laufzeit} Monate ab Auftrag je Abruf ab der kleinsten Abrufmenge; die "
                "Lieferzeit gilt je Abruf. {material} {muster} Wird die Mindestjahresmenge bis zum Ende der Laufzeit "
                "nicht abgenommen, behalten wir uns vor, die anteiligen Einmalkosten nachzuberechnen."),
    Einstellung("abruf_text_klausel", "Abruf-Angebot: Text Material je Abruf (Materialklausel)", "Angebots-PDF",
                "mehrzeilig", "Die Preise beruhen auf den Materialpreisen vom {datum}; ändern sich diese um mehr als "
                "{klausel} %, passen wir die Preise entsprechend an."),
    Einstellung("abruf_text_lager", "Abruf-Angebot: Text Material bevorratet", "Angebots-PDF", "mehrzeilig",
                "Das Material für die Mindestjahresmenge kaufen wir nach Auftrag ein und halten es für Ihre Abrufe "
                "vor; die Materialpreise sind für die Laufzeit fest."),
    Einstellung("abruf_text_muster", "Abruf-Angebot: Text Muster vorab", "Angebots-PDF", "mehrzeilig",
                "Die Muster liefern wir vorab; die Serie fertigen wir nach Ihrer Musterfreigabe."),
    Einstellung("mindestpreis", "Mindestpreis je Angebot netto, Ware ohne Fracht nach Skonto [€] (0 = keiner)", "Kalkulation", "zahl", 200.0, 0,
                1000000),
    # Lieferlängen-Vergleich (z. B. 6 m gegen 12 m): eine andere Lieferlänge wird nur empfohlen, wenn beide
    # Mindestwerte erreicht sind
    # Vergleich mit anderen Lieferlängen (z. B. 12 m) beim Optimieren: kostet bei großen Gruppen Zeit, daher
    # Vorgabe aus (Patrick 22.10.2026). Ist die Stangenlänge des Angebots nicht lieferbar, wird trotzdem mit einer
    # lieferbaren Länge geplant.
    Einstellung("laenge_vergleich", "Lieferlängen: beim Optimieren andere Lieferlängen vergleichen (z. B. 12 m)",
                "Lieferlängen", "auswahl", "nein", auswahl="janein"),
    Einstellung("laenge_mindest_eur", "Lieferlängen: Mindestersparnis je Gruppe in €", "Lieferlängen", "zahl", 20.0,
                0, 100000),
    Einstellung("laenge_mindest_anteil", "Lieferlängen: Mindestersparnis je Gruppe in %", "Lieferlängen", "anteil",
                0.03, 0, 1),
    Einstellung("laenge_auto_huellkreis", "Lieferlängen: ohne Eintrag lieferbar ab Hüllkreis-Ø [mm] (0 = aus)",
                "Lieferlängen", "zahl", 70.0, 0, 2000),
    Einstellung("laenge_auto", "Lieferlängen: Länge für Profile ab diesem Hüllkreis-Ø [mm]", "Lieferlängen", "ganz",
                12000, 500, 30000),
    Einstellung("zuschnitt_verlust", "Lieferlängen: Schnittverlust je Zuschnitt beim Lieferanten [mm]",
                "Lieferlängen", "zahl", 3.0, 0, 50),
    Einstellung("zuschnitt_puffer", "Lieferlängen: Puffer je zugeschnittener Stange [mm]", "Lieferlängen", "ganz",
                50, 0, 1000),
    Einstellung("haendler_mehr_kurz", "Materialpreis: Mehrlänge je Stange, die der Händler berechnet, bis zur "
                "Grenze (z. B. 6 m) [mm]", "Lieferlängen", "ganz", 50, 0, 1000),
    Einstellung("haendler_mehr_lang", "Materialpreis: Mehrlänge je Stange über der Grenze (z. B. 12 m) [mm]",
                "Lieferlängen", "ganz", 100, 0, 1000),
    Einstellung("haendler_mehr_grenze", "Materialpreis: Grenze kurze/lange Stange [mm]", "Lieferlängen", "ganz",
                6500, 0, 30000),
    Einstellung("zuschnitt_kosten", "Lieferlängen: Kosten je Zuschnitt beim Lieferanten [€]", "Lieferlängen", "zahl",
                0.0, 0, 10000),
    # Blech-Editor: Richtpreis je Blech-/Kantteil = (Material + Laser + Kanten + Rüsten je Stück) × (1 + Aufschlag)
    Einstellung("blech_stundensatz", "Stundensatz Blechlaser [€/h]", "Blech-Richtpreis", "zahl", 120.0, 0, 10000),
    Einstellung("blech_ruesten", "Rüsten und Programmieren Blechlaser je Auftrag [€]", "Blech-Richtpreis", "zahl",
                30.0, 0, 100000),
    Einstellung("blech_verschnitt", "Verschnitt Tafel (auf das Hüllrechteck)", "Blech-Richtpreis", "anteil", 0.15,
                0, 5),
    # Tafelausnutzung (blech.tafelbedarf): Material je Losgröße aus den Tafelformaten statt pauschalem Verschnitt
    Einstellung("blech_material", "Material: Tafelausnutzung oder pauschaler Verschnitt", "Blech-Richtpreis",
                "auswahl", MATERIAL_AUS[0], auswahl="blechmaterial"),
    Einstellung("blech_tafeln", "Tafelformate: Länge × Breite in mm, mit ; getrennt (Beispiel, bitte anpassen)",
                "Blech-Richtpreis", "text", "3000 × 1500; 2500 × 1250"),
    Einstellung("blech_tafel_rand", "Tafel: Randabstand [mm]", "Blech-Richtpreis", "zahl", 10.0, 0, 200),
    Einstellung("blech_tafel_steg", "Tafel: Steg zwischen den Teilen [mm]", "Blech-Richtpreis", "zahl", 5.0, 0, 100),
    Einstellung("blech_kantung", "Kanten: Preis je Kantung [€]", "Blech-Richtpreis", "zahl", 1.20, 0, 10000),
    Einstellung("blech_ruesten_kanten", "Kanten: Rüsten je Auftrag [€]", "Blech-Richtpreis", "zahl", 25.0, 0, 100000),
    Einstellung("blech_aufschlag", "Aufschlag des Lieferanten (Gewinn)", "Blech-Richtpreis", "anteil", 0.15, 0, 5),
    # Kantbarkeit (blech.kantbarkeit): nur Hinweise im Blech-Editor, Faktor 0 = Regel aus
    Einstellung("blech_kant_v", "Kantbarkeit: V-Öffnung = Faktor × Blechdicke", "Blech-Richtpreis", "zahl", 8.0, 0,
                50),
    Einstellung("blech_kant_schenkel", "Kantbarkeit: kleinstes Schenkel-Außenmaß = Faktor × V-Öffnung",
                "Blech-Richtpreis", "zahl", 0.7, 0, 5),
    Einstellung("blech_kant_loch", "Kantbarkeit: Abstand Innenkontur–Biegelinie mindestens Innenradius + Faktor × "
                "Dicke", "Blech-Richtpreis", "zahl", 2.0, 0, 20),
    Einstellung("blech_kant_radius", "Kantbarkeit: kleinster Innenradius = Faktor × Dicke", "Blech-Richtpreis",
                "zahl", 0.5, 0, 20),
    Einstellung("blech_abwicklung", "Abwicklung: K-Faktor aus (K-Faktor-Tabelle oder je Werkstoff)",
                "Blech-Richtpreis", "auswahl", ABWICKLUNG_K[0], auswahl="abwicklung"),
    # DXF-Export der Abwicklung (Blech-Editor, dxf.py): Layernamen in fester Reihenfolge, Biegelinien ja/nein
    Einstellung("blech_dxf_layer", "DXF: Layernamen (Außenkontur; Innenkontur; Biegelinie hoch; Biegelinie runter; "
                "Gravur; Beschriftung)", "Blech-Richtpreis", "text",
                "AUSSENKONTUR; INNENKONTUR; BIEGUNG_HOCH; BIEGUNG_RUNTER; GRAVUR; BESCHRIFTUNG"),
    Einstellung("blech_dxf_biegelinien", "DXF: Biegelinien ausgeben", "Blech-Richtpreis", "auswahl", "ja",
                auswahl="janein"),
    # DXF-Import (Plan DXF-Import verbessern, Patrick 25.10.2026): Layer MASSE, VERDECKT, SCHRAFFUR, RAHMEN … sind fest
    Einstellung("dxf_weg_layer", "DXF-Import: weitere Layer ohne Schnitt (Namen oder Wortteile, mit ; getrennt)",
                "Blech-Richtpreis", "text", ""),
    Einstellung("dxf_splitter", "DXF-Import: Teile kleiner als [mm] nicht anhaken (Maßpfeile, Splitter)",
                "Blech-Richtpreis", "zahl", 5.0, 0, 100),
    Einstellung("standard_maschine", "Standard-Maschine", "Angebot", "auswahl", "T03",
                auswahl="maschine"),
    Einstellung("standard_stange", "Standard-Stangenlänge [mm]", "Angebot", "ganz", 6000, 500, 20000),
    Einstellung("letzte_angebotsnummer", "Letzte Angebotsnummer", "Angebot", "text", "A-2026-0001"),
    Einstellung("flach_als", "STEP-Import: ebene flache Teile vorgeben als", "STEP-Import", "auswahl", FLACH_ALS[0],
                auswahl="flachals"),
    # Schweißbaugruppen (P6): a-Maß-Vorschlag für Kehlnaht-Kandidaten aus STEP, nur mit Häkchen im Editor
    Einstellung("schweiss_a_regel", "Schweißbaugruppen: a-Maß-Regel, a = Faktor × kleinere Wanddicke (Vorschlag)",
                "Schweißbaugruppen", "zahl", 0.7, 0.1, 2),
    Einstellung("schweiss_a_min", "Schweißbaugruppen: a-Maß-Regel mindestens [mm] (EN 1993-1-8: 3 mm, höchstens die "
                "dünnere Wand; 0 = aus)", "Schweißbaugruppen", "zahl", 3.0, 0, 10),
    # Spalt zwischen zwei Teilen (Patrick 26.10.2026): bis step_naht_spalt noch Naht und Gravur aus dem STEP, über
    # schweiss_spalt_max eine Warnung „Konstruktion prüfen“
    Einstellung("step_naht_spalt", "STEP-Import: Spalt zwischen zwei Teilen bis [mm] gilt noch als Schweißstoß (Naht "
                "und Gravur)", "STEP-Import", "zahl", 3.0, 0, 10),
    Einstellung("schweiss_spalt_max", "Schweißbaugruppen: Warnung, wenn der Spalt einer Naht größer ist als [mm]",
                "Schweißbaugruppen", "zahl", 2.0, 0, 10),
    # Vorkalkulation (vorkalk.py): Stundensätze der vorgeschlagenen Arbeitsgänge
    Einstellung("schweiss_vk_satz", "Schweißbaugruppen: Stundensatz für Rüsten, Positionieren und Wenden",
                "Schweißbaugruppen", "auswahl", "Schweißen", auswahl="zusatzsatz"),
    Einstellung("schweiss_vk_satz_nacharbeit", "Schweißbaugruppen: Stundensatz für Verputzen und Schleifen",
                "Schweißbaugruppen", "auswahl", "Schweißen", auswahl="zusatzsatz"),
    Einstellung("schweiss_vk_step", "Schweißbaugruppen: Vorkalkulation automatisch (Vorgabe je Baugruppe, auch beim "
                "STEP-Import: Nahtvorschläge, a-Maß nach Regel, Schweißen, Heften, Verputzen, Rüsten)",
                "Schweißbaugruppen", "auswahl", "nein", auswahl="janein"),
    # Positionsgravur (gravur_text.py): Artikelnummer auf Bleche und Rohre gravieren, Höhe je Teil änderbar
    Einstellung("gravur_artikel", "Gravur: Artikelnummer auf Bleche und Rohre einer Schweißbaugruppe gravieren "
                "(Vorgabe des Häkchens im Baugruppen-Editor)", "Schweißbaugruppen", "auswahl", "nein", auswahl="janein"),
    Einstellung("gravur_schrifthoehe", "Gravur: Schrifthöhe der Artikelnummer [mm]", "Schweißbaugruppen", "zahl", 10.0,
                1, 200),
    # Plan W7 Stufe 1 (Patrick 26.10.2026: erst optional zum Testen): Neue Position aus dem Schriftfeld einer PDF
    Einstellung("pdf_zeichnung", "Testfunktion PDF-Zeichnungen: Neue Position „Aus PDF-Zeichnung“", "STEP-Import",
                "auswahl", "nein", auswahl="janein"),
    Einstellung("flachstahl_bis", "STEP-Import: Flachstahl bis Breite [mm] (breitere flache Teile sind Bleche)",
                "STEP-Import", "zahl", 150.0, 1, 10000),
    # Ordner, in dem der Dateidialog „STEP importieren …“ startet; leer = zuletzt benutzter STEP-Ordner
    Einstellung("step_ordner", "STEP-Import: Standardordner (leer = zuletzt benutzter Ordner)", "STEP-Import",
                "ordner",
                ""),
    # Ordner je Angebot (B3): Vorgabe für das Häkchen im STEP-Prüfdialog (Kopie in <Angebotsordner>\\STEP)
    Einstellung("step_kopieren", "STEP-Import: STEP-Dateien in den Ordner des Angebots kopieren (Vorgabe)",
                "STEP-Import", "auswahl", "nein", auswahl="janein"),
    # Vorbelegung im STEP-Prüfdialog für Rohre und Profile (nicht für Bleche); leer = keine Vorgabe
    Einstellung("step_werkstoff", "STEP-Import: Standard-Werkstoff für Rohre und Profile (leer = keiner)",
                "STEP-Import", "auswahl", "S235-10219", auswahl="werkstoff"),
    # Vorgabe im Bohrbild (Dialog Bohrungen prüfen) für Fließlochbohrungen aus dem STEP-Import
    Einstellung("fliessloch_laser", "STEP-Import: Flowdrill-Bohrung am Laser", "STEP-Import", "auswahl",
                FLIESSLOCH_LASER[0], auswahl="fliesslochlaser"),
    # Vorgabe für Bohrungen kleiner als 0,7 × Wandstärke (STEP-Import und alle Editoren): markieren + Bohren oder
    # den Ø trotzdem schneiden, ohne Bohren (bohrbild.SCHNEIDEN)
    Einstellung("bohren_laser", "Bohrung kleiner als 0,7 × Wandstärke am Laser", "STEP-Import", "auswahl",
                BOHREN_LASER[0], auswahl="bohrenlaser"),
    # Teile mit diesen Wörtern im Bauteilnamen sind Normteile: im Prüfdialog abgewählt (importprofil.py)
    Einstellung("step_normteile", "Normteile: Begriffe im Bauteilnamen (mit ; getrennt)", "STEP-Import", "text",
                "ISO; DIN; Schraube; Mutter; Scheibe; Stift; Niet; Normteil"),
    Einstellung("step_benennung", "Artikelnummer aus (Bauteilname, Dateiname oder beides)", "STEP-Import", "auswahl", BENENNUNGEN[0], auswahl="benennung"),
    # Messung (STEP-Import.exe): Prozesse, Zeitlimit je Körper, Zwischenspeicher; siehe step_einstellungen.py
    Einstellung("step_prozesse", "Messung: gleichzeitige Messprozesse (0 = automatisch, Kerne − 1)", "STEP-Import",
                "ganz", 0, 0, 64),
    Einstellung("step_zeitlimit", "Messung: Zeitlimit je Körper [s] (0 = ohne; länger = Körper nicht gemessen)",
                "STEP-Import", "ganz", 120, 0, 3600),
    Einstellung("step_cache", "Messung: Zwischenspeicher (gleiche Datei nicht neu messen)", "STEP-Import", "auswahl",
                "ja", auswahl="janein"),
    Einstellung("step_cache_mb", "Messung: Zwischenspeicher höchstens [MB]", "STEP-Import", "ganz", 500, 10, 100000),
    # Toleranzen der Erkennung (Vorgaben = bisher feste Werte)
    Einstellung("step_tol_profil", "Toleranz Profil aus den Stammdaten ± [mm]", "STEP-Import", "zahl", 0.15, 0, 5),
    Einstellung("step_tol_gleich", "Toleranz gleiche Teile einer Baugruppe ± [mm]", "STEP-Import", "zahl", 0.2, 0, 5),
    Einstellung("step_tol_kernloch", "Toleranz Kernloch für Gewinde-Vorschlag ± [mm]", "STEP-Import", "zahl", 0.05, 0,
                1),
    Einstellung("biegerohr_faktor", "Biegerohr: Faktor neutrale Faser für die gestreckte Länge (1,0 = Rohrmitte)",
                "STEP-Import", "zahl", 1.0, 0.5, 1.5),
    Einstellung("knick_z", "Knickrahmen: Knickzugabe je Knick [mm] (+ = Rohr länger)", "Knickrahmen", "zahl", 0.0,
                -20, 20),
    Einstellung("knick_freistich", "Knickrahmen: Freistich-Ø an den Spitzen des V [mm] (0 = ohne)", "Knickrahmen",
                "zahl", 0.0, 0, 20),
    Einstellung("knick_k", "Knickrahmen: K-Faktor der Stegwand (0,5 = Wandmitte)", "Knickrahmen", "zahl", 0.5, 0.1,
                1),
    Einstellung("steck_anzahl", "Steckverbindung: Nasen je Verbindung (1, 2 oder 4)", "Steckverbindung", "ganz", 2,
                1, 4),
    Einstellung("steck_nase_min", "Steckverbindung: Nasenbreite mindestens [mm] (Vorgabe halbe Wandbreite)",
                "Steckverbindung", "zahl", 10.0, 1, 100),
    Einstellung("steck_nase_rand", "Steckverbindung: Abstand der Nase zum Eckradius je Seite [mm] (größte Nase = "
                "gerade Wandfläche − 2 × Wert)", "Steckverbindung", "zahl", 2.0, 0, 50),
    Einstellung("steck_spiel", "Steckverbindung: Spiel je Seite im Schlitz [mm]", "Steckverbindung", "zahl", 0.1, 0,
                2),
    Einstellung("steck_ueberstand", "Steckverbindung: Überstand der Nase über die Aufnahme [mm]", "Steckverbindung",
                "zahl", 0.0, 0, 20),
    # Montagemarke (Plan Baugruppen automatisch A4, Patrick 25.10.2026 „4a“: Zahl je Verbindung, Vorgabe aus)
    Einstellung("steck_marke", "Steckverbindung: neue Verbindungen bekommen eine Montagemarke (Zahl als Gravur an "
                "Schlitz und Nase)", "Steckverbindung", "auswahl", "nein", auswahl="janein"),
    Einstellung("step_flach_laenge", "Experte: Flachstahl ab Länge × Breite", "STEP-Import", "zahl", 3.0, 1, 100),
    Einstellung("step_gekantet_anteil", "Experte: gekantetes Blech statt Profil, wenn Volumen unter Anteil von Querschnitt × Länge", "STEP-Import",
                "anteil", 0.85, 0.1, 1),
    # Zahlungsbedingungen neuer Angebote, wenn der Kunde keine eigenen hat. Skonto wird in den Preis eingerechnet.
    Einstellung("skonto", "Skonto [%]", "Angebot", "zahl", 2.0, 0, 20),
    Einstellung("skonto_tage", "Skontofrist [Tage]", "Angebot", "ganz", 10, 0, 365),
    Einstellung("zahlungsziel", "Zahlungsziel netto [Tage]", "Angebot", "ganz", 30, 0, 365),
    # Lieferzeit neuer Angebote (im Angebot änderbar); 'nur Text' + 'nach Absprache' entspricht dem bisherigen Satz
    Einstellung("lieferzeit_art", "Lieferzeit neuer Angebote: Angabe als", "Angebot", "auswahl", "nur Text",
                auswahl="lieferzeitart"),
    Einstellung("lieferzeit_wert", "Lieferzeit neuer Angebote: Wert (Arbeitstage, Wochen, KW/Jahr oder Datum)",
                "Angebot", "text", ""),
    Einstellung("lieferzeit_zusatz", "Lieferzeit neuer Angebote: Freitext", "Angebot", "text", "nach Absprache"),
    # Patrick 28.10.2026: einmal optimierte Angebote nicht mehr löschbar (Positionen schon; der Admin darf löschen).
    # Vorgabe aus; „von Hand“ zählt nur F9/Optimieren, nicht das automatische Optimieren der Entwürfe
    Einstellung("loeschschutz", "Löschschutz: optimierte Angebote nicht löschbar (immer = auch automatisch "
                "optimierte)", "Angebot", "auswahl", LOESCHSCHUTZ_AUS, auswahl="loeschschutz"),
    # Zeitraum der Angebotsliste (Patrick 29.10.2026, nur dieser Arbeitsplatz): ältere Angebote ausblenden; offene
    # Wiedervorlagen, nicht versendete Aufträge und geöffnete bleiben, die Suche findet alle
    Einstellung("angebote_zeitraum", "Angebotsliste: Zeitraum (Angebote mit Datum oder Änderung in den letzten Tagen)",
                "Angebot", "auswahl", "150 Tage", auswahl="zeitraum"),
    # Plan Arbeitsabläufe W1: Entwürfe bis zu so vielen Positionen nach jeder Änderung selbst optimieren
    Einstellung("auto_optimieren_bis", "Automatisch optimieren: Entwürfe bis Positionen (0 = aus)", "Angebot", "ganz",
                100, 0, 10000),
    # Angebots-Check (Plan A2): Warnung, wenn der Gewinn unter diesem Anteil am Verkaufspreis liegt
    Einstellung("mindestmarge", "Angebots-Check: Mindestmarge (Gewinn am Warenwert ohne Fracht und Skonto, 0 = aus)", "Angebot", "anteil",
                0.0, 0, 1),
    # Standard-Staffeln (Plan Arbeitsabläufe W3): Faktoren auf die Bestellmenge, angelegt per Knopf
    Einstellung("staffeln_standard", "Standard-Staffeln: Faktoren auf die Bestellmenge, z. B. 1; 2; 5 (leer = aus)",
                "Angebot", "text", "1; 2; 5"),
    Einstellung("briefkopf_1", "Briefkopf Zeile 1 (Firma)", "Angebots-PDF", "text", "Firmenname"),
    Einstellung("briefkopf_2", "Briefkopf Zeile 2", "Angebots-PDF", "text", "Straße Nr."),
    Einstellung("briefkopf_3", "Briefkopf Zeile 3", "Angebots-PDF", "text", "PLZ Ort"),
    Einstellung("briefkopf_4", "Briefkopf Zeile 4", "Angebots-PDF", "text", "Telefon / E-Mail"),
    # Bild als Base64-PNG in der Datendatei (wandert mit Sicherung und Export mit); leer = ohne Logo
    Einstellung("logo", "Firmenlogo (rechts oben im Angebot)", "Angebots-PDF", "bild", ""),
    Einstellung("mwst", "MwSt.-Satz", "Angebots-PDF", "anteil", 0.19, 0, 1),
    Einstellung("gueltigkeit", "Gültigkeit [Tage]", "Angebots-PDF", "ganz", 30, 0, 3650),
    Einstellung("bedingungen", "Bedingungen", "Angebots-PDF", "mehrzeilig",
                "Lieferzeit nach Absprache. Preise in Euro zuzüglich Mehrwertsteuer."),
    # Auftragsbestätigung (Plan 29.10.2026 1c): Nummer wie das Angebot oder eigener Nummernkreis AB-2026-00001
    Einstellung("ab_nummer", "Auftragsbestätigung: Nummer", "Angebots-PDF", "auswahl", "wie Angebot",
                auswahl="abnummer"),
    Einstellung("ab_text", "Auftragsbestätigung: Text über den Positionen", "Angebots-PDF", "mehrzeilig",
                "Vielen Dank für Ihren Auftrag. Wir bestätigen ihn zu den folgenden Preisen und Bedingungen."),
    # Materialanfrage per Outlook: Vorlagen mit Platzhaltern, Signatur
    Einstellung("anfrage_betreff", "Materialanfrage: Betreff", "Materialanfrage", "text",
                "Materialanfrage zu Angebot {angebot}"),
    Einstellung("anfrage_text", "Materialanfrage: Text der E-Mail", "Materialanfrage", "mehrzeilig",
                "Sehr geehrte Damen und Herren,\n\nbitte senden Sie uns ein Angebot für folgendes Material "
                "(unser Angebot {angebot}):\n\n{positionen}\n\nBitte mit Preis, Lieferzeit und Angabe der "
                "Lieferlänge.\n\nMit freundlichen Grüßen"),
    Einstellung("anfrage_outlook_signatur", "Materialanfrage: Signatur aus Outlook verwenden", "Materialanfrage",
                "auswahl", "ja", auswahl="janein"),
    Einstellung("anfrage_signatur", "Materialanfrage: eigene Signatur (E-Mail-Datei; leer = Briefkopf)",
                "Materialanfrage", "mehrzeilig", ""),
    # Angebot per E-Mail an den Kunden (Vorschlag V1, 31.10.2026, angebot_mail.py): Vorlagen mit Platzhaltern
    Einstellung("angebot_mail_betreff", "Angebot per E-Mail: Betreff (neue E-Mail; Antwort behält den Betreff)",
                "Angebot per E-Mail", "text", "Angebot {angebot}{referenz}"),
    Einstellung("angebot_mail_text", "Angebot per E-Mail: Text", "Angebot per E-Mail", "mehrzeilig",
                "{anrede}\n\nvielen Dank für Ihre Anfrage. Anbei erhalten Sie unser Angebot {angebot}{referenz}.\n\n"
                "Das Angebot gilt bis {gueltig}. Für Rückfragen stehen wir Ihnen gerne zur Verfügung.\n\n"
                "Mit freundlichen Grüßen"),
    # Nachfassen verschickter Angebote (Plan A9): Wiedervorlage nach Tagen ohne Entscheidung
    Einstellung("nachfassen_tage", "Nachfassen: Wiedervorlage nach Tagen ohne Entscheidung (0 = aus)", "Nachfassen",
                "ganz", 10, 0, 365),
    # je Angebot ein Ordner darin (angebotsordner.py): '2026-00042 Kunde', Fassungen als 'Fassung 2'
    Einstellung("ablageordner", "Ablageordner (leer = Ordner 'Angebote' neben dem Programm)", "Ablage", "ordner", ""),
    # Anfrage-Ordner (Plan W6a): neue STEP-Anfragen erscheinen auf der Startseite (anfragen.py)
    Einstellung("anfrage_ordner", "Anfrage-Ordner (leer = aus)", "Ablage", "ordner", ""),
    # CSV-Export (Patrick 24.10.2026): zuletzt gewählter Zielordner, nur dieser Arbeitsplatz
    Einstellung("csv_ordner", "CSV-Export: zuletzt gewählter Ordner (leer = Ordner des Angebots)", "Ablage", "ordner",
                ""),
    Einstellung("sicherung_ordner2", "Zweiter Sicherungsordner (leer = keiner, z. B. Netzlaufwerk oder USB-Stick)",
                "Ablage", "text", ""),
    # Archiv alter Angebote (archiv.py, Vorschlag 5b 28.10.2026): Angebote älter als so viele volle Jahre
    Einstellung("archiv_jahre", "Archiv: archivierbar ab Alter in Jahren",
                "Ablage", "ganz", 2, 1, 20),
    Einstellung("profilformen", "Profilformen (eine je Zeile)", "Auswahllisten", "mehrzeilig",
                "\n".join(PROFILFORMEN)),
    Einstellung("kategorien", "Werkstoff-Kategorien (eine je Zeile)", "Auswahllisten", "mehrzeilig",
                "\n".join(KATEGORIEN)),
    # Frachtkosten (Reiter Frachtkosten → Historie und Einstellungen)
    Einstellung("absender_plz", "Absender-PLZ (Versandort)", "Frachtkosten", "text", ""),
    Einstellung("absender_land", "Absender-Land", "Frachtkosten", "text", "DE"),
    Einstellung("fracht_versandart", "Versandart für automatische Fracht", "Frachtkosten", "text", None),
    Einstellung("fracht_lht_standard", "Ladungsträger im Packvorschlag", "Frachtkosten", "auswahl", "EUR",
                auswahl="lht"),
    Einstellung("fracht_lht_langgut", "Ladungsträger für lange Teile (Langgut)", "Frachtkosten", "auswahl", "LG",
                auswahl="lht"),
    # Versand und Palettenschein (Plan Palettenbegleitschein 24.10.2026): Paletten nach Gewicht und Packraum
    # (paletten.py, auch im Packvorschlag der Fracht), Feiertage für Arbeitstage, Arbeitsschritte des Scheins
    # Richtwerte Stückgut/Palettennetz (Recherche 24.10.2026): Europalette 1200 × 800, Eigenhöhe 144 mm, Nutzlast
    # 1.500 kg; Sammelgut meist bis 2,20 m und 1.200 kg je Vollpalette, stapelbar oft nur bis 1,20 m. Vorgabe nach
    # Patrick 24.10.: 1.200 mm und 1.500 kg, Positionen einzeln packen, angefangene Paletten zusammen, wenn Platz ist
    # Reiter Versand mit Palettenschein ein/aus (Patrick 25.10.): aus = Reiter, Menüeinträge „Palettenbegleitschein …“,
    # Hinweis bei Beauftragt und Anhang an die Werkstattpapiere ausgeblendet; gespeicherte Versanddaten bleiben
    Einstellung("versand_aktiv", "Reiter Versand und Palettenbegleitschein verwenden", "Versand", "auswahl", "ja",
                auswahl="janein"),
    # Materialbestand und Reststücke (Wettbewerbsvergleich P0-1, lager.py; Patrick 27.10.2026: Reststücke optional,
    # Vorgabe aus). Ohne 'lager_aktiv' kein Reiter Lager, Angebote wie bisher
    Einstellung("lager_aktiv", "Materialbestand verwenden (Reiter Lager)", "Lager und Fertigung", "auswahl", "nein",
                auswahl="janein"),
    Einstellung("reste_aktiv", "Reststücke verwalten (lagern und wieder einplanen)", "Lager und Fertigung", "auswahl",
                "nein", auswahl="janein"),
    Einstellung("rest_min_laenge", "Reststücke: kürzester Rest, der ins Lager kommt [mm]", "Lager und Fertigung",
                "zahl", 500.0, 0, 20000),
    Einstellung("restwert_anteil", "Reststücke und Lagerstangen: Wert in Prozent des Materialpreises",
                "Lager und Fertigung", "anteil", 1.0, 0, 1),
    # Fertigungsstatus beauftragter Angebote (Wettbewerbsvergleich P1-6, fertigung.py)
    Einstellung("fertigung_aktiv", "Reiter Fertigung verwenden (Status beauftragter Angebote)", "Lager und Fertigung",
                "auswahl", "ja", auswahl="janein"),
    Einstellung("fertigung_status", "Fertigungsstatus (je Zeile ein Status, in dieser Reihenfolge)",
                "Lager und Fertigung", "mehrzeilig", "Freigegeben\nArbeitsvorbereitung\nMaterial bereit\nIn Fertigung\n"
                "Fremdvergabe\nQualitätsprüfung\nFertig gemeldet"),
    # Etiketten mit QR-Code und Rückmeldung per Scan (Plan 29.10.2026 2a, etiketten.py)
    Einstellung("etikett_format", "Etiketten: Format", "Lager und Fertigung",
                "auswahl", "A4, 3 × 8 Etiketten (70 × 37 mm)",
                auswahl="etikettformat"),
    Einstellung("rueckmeldung_schritte", "Rückmeldung per Scan: Arbeitsschritte (eine Zeile je Schritt, der letzte "
                "= fertig)", "Lager und Fertigung", "mehrzeilig", "Geschnitten\nEntgratet\nVerpackt"),
    # Reklamationen (Plan 29.10.2026 2c, reklamation.py)
    Einstellung("reklamation_fehlerarten", "Reklamationen: Fehlerarten (eine Zeile je Fehlerart)",
                "Lager und Fertigung", "mehrzeilig", "Maß außerhalb der Toleranz\nKontur fehlt oder falsch\nGrat oder "
                "Schlacke\nOberfläche, Kratzer, Anlauffarben\nFalscher Werkstoff oder falsches Profil\nFalsche "
                "Menge\nTransportschaden\nSonstiges"),
    # Wochenauslastung je Maschine mit Schichtkalender (Plan 29.10.2026 2b, auslastung.py)
    Einstellung("schicht_stunden", "Auslastung: Stunden je Arbeitstag und Maschine (Maschine leer = dieser Wert)",
                "Lager und Fertigung", "zahl", 8.0, 0, 24),
    Einstellung("schicht_samstag", "Auslastung: Stunden am Samstag", "Lager und Fertigung", "zahl", 0.0, 0, 24),
    Einstellung("schicht_verfuegbar", "Auslastung: nutzbarer Anteil der Schichtzeit (Wartung, Störungen)",
                "Lager und Fertigung", "anteil", 0.85, 0.1, 1),
    Einstellung("betriebsruhe", "Auslastung: Betriebsruhe (Tage und Zeiträume, z. B. 24.12.2026-31.12.2026; "
                "02.10.2026)", "Lager und Fertigung", "text", ""),
    Einstellung("auslastung_vorlauf", "Auslastung: Laserzeit so viele Arbeitstage vor dem Liefertermin",
                "Lager und Fertigung", "ganz", 2, 0, 60),
    Einstellung("palette_hoehe_gesamt", "Paletten: max. Höhe beladen inkl. Ladungsträger [mm]", "Versand", "ganz",
                1200, 200, 3000),
    Einstellung("palette_max_brutto", "Paletten: max. Bruttogewicht je Palette [kg] (leer = Nutzlast)", "Versand",
                "zahl_leer", 1500.0, 0, 100000),
    Einstellung("palette_mischen", "Paletten: verschiedene Positionen gemeinsam auf eine Palette", "Versand",
                "auswahl", "Reste zusammenpacken", auswahl="palettenmischen"),
    Einstellung("palette_fuellgrad", "Paletten: Lagenausnutzung (Bündel, Umreifung, Kantenschutz)", "Versand",
                "anteil", 0.9, 0.1, 1),
    Einstellung("palette_zwischenlage", "Paletten: Zwischenlage zwischen zwei Lagen [mm] (0 = keine)", "Versand",
                "zahl", 0.0, 0, 200),
    Einstellung("versand_bundesland", "Feiertage für Arbeitstage (Bundesland)", "Versand", "auswahl",
                "Nordrhein-Westfalen", auswahl="bundesland"),
    Einstellung("versand_schritte", "Palettenschein: Arbeitsschritte (je Zeile 'Gruppe: Schritt')", "Versand",
                "mehrzeilig", VERSAND_SCHRITTE),
    Einstellung("palettenschein_werkstatt", "Palettenscheine an die Werkstattpapiere anhängen (beauftragte Angebote)",
                "Versand", "auswahl", "ja", auswahl="janein"),
    # Der Reiter Einstellungen (mit den Stammdaten außer Kunden) öffnet nur mit diesem Passwort; leer = ohne
    # Hilfetexte über den Tabellen: aufklappbar (erster Satz, 'ⓘ mehr') oder nur als Tooltip (siehe hilfe.py)
    Einstellung("ansicht_hilfe", "Hilfetexte über Tabellen und Seiten", "Ansicht", "auswahl", "aufklappbar",
                auswahl="hilfeart"),
    # 3D-Ansicht zeichnen mit OpenGL (Grafikkarte) oder QPainter (Software); Automatisch = OpenGL, wenn möglich
    Einstellung("ansicht_3d", "3D-Ansicht: Darstellung (Automatisch, Software oder OpenGL)", "Ansicht", "auswahl",
                DARSTELLUNG_3D[0], auswahl="renderer"),
    # Theme, Schriftgröße und Dichte (stil.anwenden, Layout-Plan D2): nur dieser Arbeitsplatz, gelten sofort (Hauptfenster.ansicht_anwenden)
    Einstellung("ansicht_thema", "Farbschema (Hell, Dunkel, Hoher Kontrast, Wie Windows)", "Ansicht", "auswahl", "Hell",
                auswahl="thema"),
    Einstellung("ansicht_schrift", "Schriftgröße [%] (90 bis 150)", "Ansicht", "ganz", 100, 90, 150),
    Einstellung("ansicht_dichte", "Dichte (kompakt, normal, komfortabel)", "Ansicht", "auswahl", "normal",
                auswahl="dichte"),
    # Tabellen-Eingabe wie Excel (Plan Arbeitsabläufe W5, tabellen_eingabe.py): wohin Eingabe in der Positionsliste springt
    Einstellung("eingabe_richtung", "Positionsliste: Eingabe springt (nach unten oder nach rechts)", "Ansicht",
                "auswahl", EINGABE_RICHTUNGEN[0], auswahl="eingaberichtung"),
    # Stangenbild, Ansicht Übersicht: Maus so lange auf einer Stange, dann ihre Detail-Ansicht im kleinen Fenster
    # (Patrick 26.10.2026: „Zeit einstellbar machen“)
    Einstellung("stangenbild_popup", "Stangenbild: Detail-Fenster nach so vielen Sekunden auf einer Stange (0 = aus)",
                "Ansicht", "zahl", 1.0, 0, 10),
    Einstellung("passwort", "Admin-Passwort (gilt an allen Arbeitsplätzen; leer = kein Admin-Schutz)", "Zugang",
                "passwort", "av"),
    # Benutzer dieses Arbeitsplatzes (teilen.py, Patrick 22.10.2026): das Kürzel zeigt den Bearbeiter (die Nummer ist
    # seit 23.10.2026 ohne Kürzel, nummern.py); über den gemeinsamen Ordner sehen alle die Angebote der anderen und
    # teilen die Stammdaten.
    # Gelten nur für diesen Arbeitsplatz (teilen.LOKAL), werden also nicht mit den anderen abgeglichen.
    Einstellung("benutzer_name", "Name", "Benutzer", "text", ""),
    Einstellung("benutzer_kuerzel", "Kürzel (Bearbeiter, z. B. PB)", "Benutzer", "text", ""),
    Einstellung("benutzer_email", "E-Mail (im Angebots-PDF)", "Benutzer", "text", ""),
    Einstellung("benutzer_telefon", "Telefon (im Angebots-PDF)", "Benutzer", "text", ""),
    Einstellung("teilen_ordner", "Gemeinsamer Ordner der Mitarbeiter (leer = nicht teilen)", "Benutzer", "ordner", ""),
    Einstellung("teilen_takt", "Automatischer Abgleich alle [min] (0 = aus)", "Benutzer", "zahl", 1.0, 0, 60),
    # Was zusätzlich im gemeinsamen Ordner liegt (Patrick 28.10.2026 „Alle“); gilt für alle Mitarbeiter
    Einstellung("teilen_anfragen", "Anfrage-Ordner im gemeinsamen Ordner (wenn oben keiner eingetragen ist)",
                "Benutzer", "auswahl", "ja", auswahl="janein"),
    Einstellung("teilen_ablage", "Angebotsordner im gemeinsamen Ordner (PDF, CSV, STEP)",
                "Benutzer", "auswahl", "ja", auswahl="janein"),
    Einstellung("teilen_sicherung", "Sicherung beim Beenden auch im gemeinsamen Ordner",
                "Benutzer", "auswahl", "ja", auswahl="janein"),
) + tuple(
    # Funktionen ein/aus (funktionen.py, Patrick 29.10.2026): ja = sichtbar, nein = ausgeblendet, Daten bleiben
    Einstellung(f.name, f.titel, "Funktionen", "auswahl", "ja", auswahl="janein") for f in funktionen.FUNKTIONEN)
EINSTELLUNG = {e.name: e for e in EINSTELLUNGEN}


# ------------------------------------------------------------------ Werte lesen und anzeigen
def zahl_aus_text(text):
    """'1.234,5' / '1234,5' / '1234.5' -> 1234.5; '6.000' (Punkt als Tausendertrennung) -> 6000"""
    t = str(text).strip().replace(" ", "").replace(" ", "")
    if "," in t or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "").replace(",", ".")
    return float(t)


def rechnung_aus_text(text):
    """Wert einer Rechnung wie „6000/4“ oder „1.250 − 2×3“ (Punkt vor drei Ziffern = Tausender); keine Rechnung
    oder nicht auswertbar = None."""
    t = str(text).strip()
    if not re.fullmatch(r"[\d\s.,+\-−*/×÷:()xX]+", t) or not re.search(r"(?<=[\d)\s])[+\-−*/×÷:xX]|[()]", t):
        return None
    t = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", t)
    from .rechenfeld import auswerten
    try:
        return auswerten(t)
    except ValueError:
        return None


def wert_aus_text(f, text):
    """Eingabe im Programm in den gespeicherten Wert umwandeln. ValueError mit Meldung bei ungültiger
    Eingabe. Leere Eingabe = None."""
    t = "" if text is None else str(text).strip()
    if t == "":
        return None
    if f.art in ("zahl", "ganz"):
        try:
            w = zahl_aus_text(t)
        except ValueError:
            w = rechnung_aus_text(t)        # Rechnen im Feld, z. B. „6000/4“ (Plan Eingabefelder E4)
            if w is None:
                raise ValueError(f"{f.titel}: '{t}' ist keine Zahl.")
        if f.art == "ganz":
            if w != int(w):
                raise ValueError(f"{f.titel}: bitte eine ganze Zahl eingeben.")
            w = int(w)
        if (f.von is not None and w < f.von) or (f.bis is not None and w > f.bis):
            raise ValueError(f"{f.titel}: Wert zwischen {zahl_als_text(f.von)} und {zahl_als_text(f.bis)} eingeben.")
        return w
    if f.art == "datum":
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(t, fmt).date().isoformat()
            except ValueError:
                pass
        raise ValueError(f"{f.titel}: Datum als TT.MM.JJJJ eingeben.")
    if f.muster and not re.search(f.muster[0], t):
        raise ValueError(f"{f.titel}: {f.muster[1]}")
    return t


def zahl_als_text(w, stellen=None, tausender=True):
    if w is None:
        return ""
    g = "," if tausender else ""
    if stellen is None:
        s = f"{w:{g}.6f}".rstrip("0").rstrip(".") if isinstance(w, float) else f"{w:{g}}"
    else:
        s = f"{w:{g}.{stellen}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def wert_als_text(f, w, bearbeiten=False):
    """Anzeige mit Tausenderpunkt; zum Bearbeiten ohne Tausenderpunkt und mit allen Stellen."""
    if w is None:
        return ""
    if f.art in ("zahl", "ganz"):
        if bearbeiten:
            return zahl_als_text(w, None, tausender=False)
        return zahl_als_text(w, 0 if f.art == "ganz" else f.stellen)
    if f.art == "datum":
        try:
            return datetime.date.fromisoformat(w).strftime("%d.%m.%Y")
        except ValueError:
            return str(w)
    return str(w)


# ------------------------------------------------------------------ Prüfung
def _leer(v):
    return v is None or v == ""


@dataclass
class Kontext:
    """Nachschlagewerte für Prüfung, berechnete Spalten und Auswahllisten."""
    profile: dict = field(default_factory=dict)       # Profil-ID -> Zeile
    werkstoffe: dict = field(default_factory=dict)
    maschinen: dict = field(default_factory=dict)
    oberflaechen: dict = field(default_factory=dict)
    stundensaetze: dict = field(default_factory=dict)
    schneiddaten: tuple = ()        # Zeilen der Schneiddaten (Plausibilität in der Prüfspalte)
    profilformen: tuple = PROFILFORMEN
    kategorien: tuple = KATEGORIEN
    zukauf_kategorien: tuple = ()     # Namen der Kategorien und Lieferanten der Zukaufartikel
    zukauf_lieferanten: tuple = ()
    listen: dict = field(default_factory=dict)        # weitere Auswahllisten (Frachtkosten: Zonen, Tarife …)
    schweissverfahren: tuple = ()     # Namen der Schweißverfahren (Auswahl in den Schweiß-Kennwerten)

    def auswahl(self, quelle):
        return [w for _, werte in self.gruppiert(quelle) for w in werte]

    def gruppiert(self, quelle):
        """Auswahlliste in Gruppen [(Überschrift oder None, [Werte])]: Werkstoffe und Oberflächen nach Kategorie."""
        if quelle in ("werkstoff", "oberflaeche"):
            zeilen = self.werkstoffe if quelle == "werkstoff" else self.oberflaechen
            reihe = {kat: i for i, kat in enumerate(self.kategorien)}
            kat = lambda z: z.get("kategorie") or ("ohne Kategorie" if quelle == "werkstoff" else "alle Werkstoffe")
            gruppen = {}
            for name, z in zeilen.items():
                gruppen.setdefault(kat(z), []).append(name)
            # Oberflächen: 'roh' und die für alle Werkstoffe zuerst
            erst = (lambda g: 0 if g == "alle Werkstoffe" else 1) if quelle == "oberflaeche" else (lambda g: 0)
            folge = sorted(gruppen, key=lambda g: (erst(g), reihe.get(g, len(reihe)), g))
            return [(g, sorted(gruppen[g], key=lambda n: (n != ROH, n.lower()))) for g in folge]
        if quelle in self.listen:
            return [(None, list(self.listen[quelle]))]
        from .fracht_daten import AUSWAHL_FEST
        if quelle in AUSWAHL_FEST:
            return [(None, list(AUSWAHL_FEST[quelle]))]
        return [(None, {"profilform": list(self.profilformen), "preisbasis": list(PREISBASIS),
                         "zusatzart": list(ZUSATZARTEN), "profil": sorted(self.profile), "janein": ["ja", "nein"], "zeugnis": ["2.2", "3.1", "3.2"], "teuerung": list(TEUERUNG_ARTEN), "hilfeart": ["aufklappbar", "nur Tooltip"],
                         "maschine": sorted(self.maschinen), "kategorie": list(self.kategorien),
                         "gas": list(GASE), "gasvorgabe": list(GAS_VORGABEN), "satzart": ["von Hand", "ermittelt"],
                         "laserart": list(LASERARTEN), "rohrart": list(ROHRARTEN), "stundensatz": [SATZ_MASCHINE] + sorted(self.stundensaetze),
                         "zeitart": list(ZEITARTEN), "ruestbezug": list(RUESTBEZUG),
                         "zeitbezug": list(ZEITBEZUG), "zeiteinheit": list(ZEITEINHEITEN),
                         "zusatzsatz": sorted(self.stundensaetze), "zuschlagart": list(ZUSCHLAG_ARTEN),
                         "zuschlagbasis": list(ZUSCHLAG_BASIS), "zukaufmethode": list(ZUKAUF_METHODEN),
                         "zukaufquelle": list(ZUKAUF_QUELLEN), "zukaufstatus": list(ZUKAUF_STATUS),
                         "zukauftyp": list(ZUKAUF_TYPEN), "positionsart": ["Rohrlaserteil", "Zukaufteil", "Schweißbaugruppe"],
                         "lieferzeitart": list(LIEFERZEIT_ARTEN),
                         "loeschschutz": list(LOESCHSCHUTZ), "zeitraum": list(ZEITRAUM),
                         "abnummer": ["wie Angebot", "eigener Nummernkreis"],
                         "etikettformat": ["A4, 3 × 8 Etiketten (70 × 37 mm)", "A4, 2 × 7 Etiketten (105 × 42,3 mm)",
                                           "Etikettendrucker 100 × 50 mm", "Etikettendrucker 62 × 29 mm"], "fliesslochlaser": list(FLIESSLOCH_LASER),
                         "bohrenlaser": list(BOHREN_LASER),
                         "flachals": list(FLACH_ALS), "benennung": list(BENENNUNGEN), "renderer": list(DARSTELLUNG_3D), "thema": list(THEMES), "dichte": list(DICHTEN), "eingaberichtung": list(EINGABE_RICHTUNGEN), "abwicklung": list(ABWICKLUNG_K), "blechmaterial": list(MATERIAL_AUS), "pruefregel": list(dfm.REGELN), "pruefstufe": list(dfm.STUFEN), "materialherkunft": list(MATERIAL_HERKUNFT), "musterdarstellung": list(MUSTER_DARSTELLUNG), "abrufmaterial": list(ABRUF_MATERIAL),
                         "nahtquelle": list(naht.QUELLEN), "querschnittlage": list(naht.LAGEN),
                         "nahtstange": list(naht.NAHT_STANGE),
                         "zukaufkategorie": list(self.zukauf_kategorien),
                         "zukauflieferant": list(self.zukauf_lieferanten),
                         "schweissverfahren": list(self.schweissverfahren), "nahtart": list(NAHTARTEN),
                         "schweissfaktorart": list(SCHWEISS_FAKTORARTEN),
                         "kennwertstatus": list(KENNWERT_STATUS),
                         "regelmerkmal": list(REGEL_MERKMALE), "regelmenge": list(REGEL_MENGEN),
                         "regelzuordnung": list(REGEL_ZUORDNUNGEN), "aufpreisbasis": list(AUFPREIS_BASEN),
                         "schweissregelart": list(SCHWEISSREGEL_ARTEN),
                         "positionierhilfe": list(POSITIONIERHILFEN), "bundesland": list(feiertage.AUSWAHL),
                         "palettenmischen": ["Reste zusammenpacken", "nie", "immer"], "nacharbeitsstufe": list(NACHARBEIT_STUFEN)}.get(quelle, []))]


def kontext_aus(daten, profilformen=PROFILFORMEN, kategorien=KATEGORIEN):
    """Kontext aus Stammdatenzeilen {Tabelle: [Zeile]} (Zukaufartikel: zukauf_kategorien, zukauf_lieferanten)."""
    k = Kontext()
    k.profile = {z["profil_id"]: z for z in daten.get("profile", []) if z.get("profil_id")}
    k.werkstoffe = {z["werkstoff_id"]: z for z in daten.get("werkstoffe", []) if z.get("werkstoff_id")}
    k.maschinen = {z["maschinen_id"]: z for z in daten.get("maschinen", []) if z.get("maschinen_id")}
    k.oberflaechen = {z["oberflaeche"]: z for z in daten.get("oberflaechen", []) if z.get("oberflaeche")}
    k.stundensaetze = {z["satz_id"]: z for z in daten.get("stundensaetze", []) if z.get("satz_id")}
    k.schneiddaten = tuple(daten.get("schneiddaten", []))
    k.profilformen = tuple(profilformen)
    k.kategorien = tuple(kategorien)
    k.zukauf_kategorien = tuple(z["name"] for z in daten.get("zukauf_kategorien", []) if z.get("name"))
    k.zukauf_lieferanten = tuple(z["name"] for z in daten.get("zukauf_lieferanten", []) if z.get("name"))
    k.schweissverfahren = tuple(z["verfahren"] for z in daten.get("schweissverfahren", []) if z.get("verfahren"))
    return k


def kategorie_raten(z):
    """Kategorie eines Werkstoffs ohne Angabe (ältere Datendateien): Dichte unter 4 = Aluminium,
    Werkstoff-Nr. 1.4… = Edelstahl, Kupfer und Messing (CW…, Cu…) = Buntmetall, sonst Stahl."""
    texte = " ".join(str(z.get(n) or "") for n in ("werkstoff_id", "werkstoff", "werkstoff_nr"))
    if isinstance(z.get("dichte"), (int, float)) and z["dichte"] < 4:
        return "Aluminium"
    if re.search(r"(?<![\d.])1\.4\d{3}", texte) or re.search(r"(?i)\bX\d+Cr", texte):
        return "Edelstahl"
    if re.search(r"\bCW\d{3}[A-Z]\b|\bCu(Zn|-|\b)|(?i:messing|kupfer)", texte):
        return "Buntmetall"
    return "Stahl"


def co2_maschine(m):
    """Maschine mit CO₂-Laser: ID, Bezeichnung oder Bemerkung nennt CO₂ (z. B. T03 'CO₂-Laser')."""
    m = m or {}
    text = " ".join(str(m.get(n) or "") for n in ("maschinen_id", "bezeichnung", "bemerkung")).upper()
    return "CO₂" in text or "CO2" in text or LASER.get(m.get("maschinen_id")) == "CO₂"


def werkstoff_info(z):
    """Kurzinfo eines Werkstoffs für den Tooltip der Werkstoffwahl: Norm, Rohrart, Schneidgas, Faktor, Laser und
    Laser-Hinweis (leer = nichts zu sagen)."""
    z = z or {}
    teile = [str(z[n]) for n in ("werkstoff", "norm") if z.get(n)]
    laser = [str(z["rohrart"])] if z.get("rohrart") else []
    if z.get("gas_vorgabe") in GAS_VORGABEN[1:]:
        laser.append(z["gas_vorgabe"])
    f = z.get("vorschub_faktor")
    if isinstance(f, (int, float)) and f > 0 and abs(f - 1) > 1e-9:
        laser.append(f"Vorschub × {zahl_als_text(f)}")
    if z.get("laser") == NUR_FASER:
        laser.append(NUR_FASER)
    zeilen = [" · ".join(teile)] if teile else []
    if laser:
        zeilen.append("Rohrlaser: " + ", ".join(laser))
    if z.get("laser_hinweis"):
        zeilen.append(str(z["laser_hinweis"]))
    return "\n".join(zeilen)


def pruefen(t, z, k):
    """Prüftext je Zeile (Spalte 'Prüfung'): 'OK', 'WARNUNG: …' oder 'FEHLER: …'."""
    for f in t.felder:
        if f.pflicht and z.get(f.name) in (None, ""):
            if t is PROFILE and f.name in ("a", "wand") and z.get("form") == "Sonderprofil":
                continue
            return f"FEHLER: {f.titel} fehlt"
        w = z.get(f.name)
        if w is not None and f.art in ("zahl", "ganz") and (
                (f.von is not None and w < f.von) or (f.bis is not None and w > f.bis)):
            return f"FEHLER: {f.titel} außerhalb {zahl_als_text(f.von)}–{zahl_als_text(f.bis)}"
        if w not in (None, "") and f.art == "auswahl" and w not in k.auswahl(f.auswahl):
            return f"FEHLER: {f.titel} unbekannt"
    if t is ZUSATZARBEITEN:
        if z.get("art") == "s/Stück":
            if z.get("preis") in (None, ""):
                return "FEHLER: Zeit je Stück fehlt"
        elif z.get("art") == "€/h":
            if z.get("satz_id") in (None, "") and z.get("satz") in (None, ""):
                return "FEHLER: Stundensatz fehlt"
        elif all(z.get(n) in (None, "", 0) for n in ("preis", "zeit", "material")):
            return "FEHLER: Festpreis, Zeitaufwand oder Materialkosten fehlen"
        if z.get("zeit") and z.get("satz_id") in (None, "") and z.get("satz") in (None, ""):
            return "FEHLER: Stundensatz fehlt"
    if t.name == "zukauf_kategorien":
        m = z.get("aufschlag_methode")
        if m == "Mengenstaffel %":
            return "FEHLER: Mengenstaffeln nur am Artikel"
        if m == "Zielmarge %" and (z.get("aufschlag_wert") or 0) >= 100:
            return "FEHLER: Zielmarge muss unter 100 % liegen"
        if z.get("aufschlag_wert") is not None and not m:
            return "WARNUNG: Methode fehlt, es gilt % auf Einstand"
    if t is ARBEITSSCHRITTE:
        if z.get("schritt") in SCHRITTE_FEST and (z.get("ruestzeit") or z.get("zeit")):
            return "WARNUNG: Zeit rechnet das Programm selbst, Rüstzeit und Zeit je Einheit hier werden nicht verwendet"
        if z.get("zeit") and not z.get("bezug"):
            return "FEHLER: Einheit fehlt"
    if t is PROFILE:
        a, s = z.get("a"), z.get("wand")
        if z.get("form") == "Flachstahl":
            if a is not None and s is not None and not 0 < s < a:
                return "FEHLER: Dicke muss kleiner als die Breite sein"
        elif a is not None and s is not None and not (0 < s and 2 * s < a):
            return "FEHLER: Wandstärke muss kleiner als die halbe Abmessung A sein"
        if z.get("form") in MIT_B and z.get("b") is None and z.get("flaeche_manuell") is None:
            return "FEHLER: Abmessung B fehlt"
        if flaeche_wirksam(z) is None:
            return "FEHLER: Querschnitt fehlt (Fläche manuell eintragen)"
        wm = z.get("wand_max")
        if wm is not None and s is not None and wm < s:
            return "FEHLER: Wandstärke max. kleiner als die Wandstärke"
        if wand_schneiden(z) is None:
            return "WARNUNG: Wandstärke fehlt, ohne sie keine Schneidzeit (Wandstärke max. eintragen)"
    if t is PREISE and z.get("basis") == "€/Stange" and not z.get("lieferlaenge"):
        return "FEHLER: Stangenlänge fehlt"
    if t is LIEFERLAENGEN:
        if _leer(z.get("basis")) != _leer(z.get("preis")):
            return "FEHLER: Preisbasis und Preis nur zusammen (beide leer = Preis wie 'Preise')"
    if t is SCHNEIDDATEN:
        if _leer(z.get("werkstoff_id")) == _leer(z.get("kategorie")):
            return "FEHLER: Werkstoff-ID oder Kategorie eintragen (eins von beiden)"
        if _leer(z.get("gas")):
            return "WARNUNG: Schneidgas fehlt"
        meldung = schneiddaten_plausibel(z, k)
        if meldung:
            return meldung
    if t is WERKSTOFFE and _leer(z.get("kategorie")):
        return "WARNUNG: Kategorie fehlt"
    if t is WERKSTOFFE and z.get("tonnenpreis") is None:
        return "WARNUNG: kein Tonnenpreis (Preis nur über 'Preise')"
    if t is MASCHINEN and z.get("satz_art") == "ermittelt" and not any(
            isinstance(z.get(n), (int, float)) and z.get(n) for n in ("anschaffung", "wartung", "leistung_kw",
                                                                         "verschleiss", "bediener_anteil", "flaeche")):
        return "WARNUNG: Stundensatz ermittelt, aber keine Werte 'Ermittlung: …' (es gilt der eingetragene Satz)"
    if t is MASCHINEN and z.get("stundensatz") is None and z.get("satz_art") != "ermittelt":
        return "WARNUNG: Stundensatz fehlt"
    if t is MASCHINEN and k.schneiddaten:
        da = {s.get("kategorie") or (k.werkstoffe.get(s.get("werkstoff_id")) or {}).get("kategorie")
              for s in k.schneiddaten if s.get("maschinen_id") == z.get("maschinen_id")}
        # auf einem CO₂-Laser fehlen Kategorien nicht, deren Werkstoffe alle nur mit Faserlaser gehen (Buntmetall)
        nur_faser = {kat for kat in k.kategorien if co2_maschine(z) and (ws := [w for w in k.werkstoffe.values()
                     if w.get("kategorie") == kat]) and all(w.get("laser") == NUR_FASER for w in ws)}
        fehlt = [kat for kat in k.kategorien if kat not in da and kat not in nur_faser]
        if len(fehlt) == len(k.kategorien):
            return "WARNUNG: keine Schneiddaten"
        if fehlt:
            return "WARNUNG: keine Schneiddaten für " + ", ".join(fehlt)
    if t.pruefung:
        meldung = t.pruefung(z, k)
        if meldung:
            return meldung
    return "OK"


def schneiddaten_plausibel(z, k):
    """Warnung, wenn der Vorschub nicht zur Wandstärke passt: mittel/klein schneller als groß, oder schneller als
    eine dünnere Stufe derselben Maschine, desselben Werkstoffs bzw. derselben Kategorie und desselben Gases."""
    g = z.get("vorschub_gross")
    if g is None:
        return None
    for name, titel in (("vorschub_mittel", "mittel"), ("vorschub_klein", "klein")):
        if z.get(name) is not None and z[name] > g:
            return f"WARNUNG: Vorschub {titel} größer als groß"
    if z.get("wand_bis") is None:
        return None
    schl = lambda s: tuple(s.get(n) or None for n in ("maschinen_id", "werkstoff_id", "kategorie", "gas"))
    duenner = [s for s in k.schneiddaten if schl(s) == schl(z) and s.get("wand_bis") is not None
               and s["wand_bis"] < z["wand_bis"] and s.get("vorschub_gross") is not None]
    if duenner:
        s = max(duenner, key=lambda s: s["wand_bis"])
        if g > s["vorschub_gross"]:
            return f"WARNUNG: Vorschub höher als bei {zahl_als_text(s['wand_bis'])} mm"
    return None


# ------------------------------------------------------------------ Beispieldaten
def beispieldaten():
    """Beispielwerte einer neuen Datenbank."""
    def zeilen(t, werte):
        return [{f.name: (w[i] if i < len(w) else None) for i, f in enumerate(t.felder)} for w in werte]
    d = datetime.date(2026, 10, 1).isoformat()
    gewinde = [("M3", 2.5, 0.60), ("M4", 3.3, 0.70), ("M5", 4.2, 0.80), ("M6", 5.0, 0.90), ("M8", 6.8, 1.10),
               ("M10", 8.5, 1.30), ("M12", 10.2, 1.60), ("M14", 12.0, 1.90), ("M16", 14.0, 2.20), ("M20", 17.5, 2.80)]
    return {
        "kunden": zeilen(KUNDEN, [
            ("K-1001", "Beispiel Metallbau GmbH", "Musterstraße 1", "12345 Musterstadt", "12345", "DE", "Herr Muster",
             "01234 56789", "info@beispiel-metallbau.de", 2, 10, 30, None, None, "frei Haus", "Beispiel"),
            ("K-1002", "Muster Anlagenbau KG", "Industrieweg 5", "54321 Beispielstadt", "54321", "DE", "Frau Beispiel",
             "05432 1234", "einkauf@muster-anlagenbau.de", 3, 14, 45, None, None, "frei Haus", "Beispiel")]),
        "profile": zeilen(PROFILE, [
            ("RR 42,4x2,0", "Rundrohr", 42.4, None, 2.0, None, None, None, "Beispiel"),
            ("RR 48,3x2,6", "Rundrohr", 48.3, None, 2.6, None, None, None, "Beispiel"),
            ("QR 40x40x3", "Quadratrohr", 40, None, 3.0, None, None, None, "Beispiel"),
            ("RE 60x40x3", "Rechteckrohr", 60, 40, 3.0, None, None, None, "Beispiel"),
            ("RE 120x60x4", "Rechteckrohr", 120, 60, 4.0, None, 30, 120,
             "Beispiel: profilspezifischer Endbeschnitt/Greiferrest")]),
        "werkstoffe": zeilen(WERKSTOFFE, beispiel_werkstoffe()),
        "oberflaechen": zeilen(OBERFLAECHEN, beispiel_oberflaechen()),
        "preise": zeilen(PREISE, [
            ("RR 42,4x2,0", "S235-10219", "€/kg", 1.45, 6000, d, "Beispiel-Lieferant", "Beispiel"),
            ("RR 48,3x2,6", "S235-10219", "€/kg", 1.45, 6000, d, "Beispiel-Lieferant", "Beispiel"),
            ("QR 40x40x3", "S235-10219", "€/kg", 1.50, 6000, d, "Beispiel-Lieferant", "Beispiel"),
            ("RE 60x40x3", "S355-10219", "€/kg", 1.60, 6000, d, "Beispiel-Lieferant", "Beispiel"),
            ("RR 42,4x2,0", "1.4301", "€/Stange", 62.00, 6000, d, "Beispiel-Lieferant", "Beispiel")]),
        "maschinen": zeilen(MASCHINEN, [
            *BEISPIEL_MASCHINEN]),
        "schneiddaten": zeilen(SCHNEIDDATEN, beispiel_schneiddaten()),
        "gewinde": zeilen(GEWINDE, [(g, k, None, "Zeit je Gewinde für Kalkulation in Schritt 4" if i == 0 else None, p)
                                    for i, (g, k, p) in enumerate(gewinde)]),
        "zusatzarbeiten": beispiel_zusatzarbeiten(),
        "stundensaetze": beispiel_stundensaetze(),
        "arbeitsschritte": beispiel_arbeitsschritte(),
        "blech_werkstoffe": zeilen(BLECH_WERKSTOFFE, beispiel_blech_werkstoffe()),
        "blechlaser": zeilen(BLECHLASER, beispiel_blechlaser()),
        "blech_kfaktoren": zeilen(BLECH_KFAKTOREN, beispiel_blech_kfaktoren()),
        "pruefregeln": zeilen(PRUEFREGELN, dfm.beispiel_regeln()),
        "arbeitsgang_regeln": beispiel_arbeitsgang_regeln(),
    }


def beispiel_arbeitsgang_regeln():
    """Vorbelegung Arbeitsgang-Regeln (Beispiele, bitte an die eigene Fertigung anpassen)."""
    def r(name, zusatzarbeit, **w):
        return dict({f.name: None for f in ARBEITSGANG_REGELN.felder}, **dict(
            dict(name=name, zusatzarbeit=zusatzarbeit, aktiv="ja", menge_art="automatisch"), **w))
    return [r("Verzinkt laut Bezeichnung", "Feuerverzinken", stichwort="verzinkt;feuerverzinkt;fvz",
              kategorie="Stahl", bemerkung="Beispiel: Stichwort in Bezeichnung oder Artikelnummer"),
            r("Pulver laut Bezeichnung", "Pulverbeschichten", stichwort="pulver;RAL",
              bemerkung="Beispiel: Farbe je Position als Text ergänzen"),
            r("Entgraten bei Innenkonturen", "Entgraten", merkmal="Innenkonturen", aktiv="nein",
              bemerkung="Beispiel, aus: bei Bedarf aktivieren")] + strahl_regeln()


def beispiel_blech_werkstoffe():
    """Blech-Werkstoffe für den Richtpreis (Beispielpreise je kg Tafel, bitte durch eigene ersetzen)."""
    st, es, al, b = "Stahl", "Edelstahl", "Aluminium", "Richtwert, bitte anpassen"
    return [("S235JR", st, "S235JR EN 10025-2 warmgewalzt", 7.85, 1.10, 0.33, b),
            ("S355MC", st, "S355MC EN 10149-2", 7.85, 1.25, 0.33, b),
            ("DC01", st, "DC01 EN 10130 kaltgewalzt", 7.85, 1.20, 0.33, b),
            ("DX51D+Z275", st, "DX51D+Z275 feuerverzinkt", 7.85, 1.35, 0.33, b),
            ("1.4301 2B", es, "X5CrNi18-10 kaltgewalzt 2B", 7.90, 3.80, 0.33, b),
            ("1.4301 K240", es, "X5CrNi18-10 geschliffen K240, foliert", 7.90, 4.40, 0.33, b),
            ("1.4571 2B", es, "X6CrNiMoTi17-12-2 kaltgewalzt 2B", 8.00, 5.50, 0.33, b),
            ("AlMg3", al, "EN AW-5754 H111", 2.66, 4.20, 0.33, b),
            ("AlMg4,5Mn", al, "EN AW-5083 H111", 2.66, 4.80, 0.33, b)]


# Richtwerte Faserlaser etwa 6 kW, Flachbett: (Dicke bis, Vorschub Außenkontur, Einstechzeit); Innenkonturen halb
BLECHLASER_RICHTWERTE = {
    ("Stahl", "N₂"): [(1, 30000, 0.2), (2, 18000, 0.3), (3, 10000, 0.3), (4, 6500, 0.5), (5, 4500, 0.6),
                      (6, 3200, 0.8)],
    ("Stahl", "O₂"): [(8, 2600, 1.0), (10, 2000, 1.5), (12, 1600, 2.0), (15, 1200, 3.0), (20, 800, 4.0)],
    ("Edelstahl", "N₂"): [(1, 32000, 0.2), (2, 16000, 0.3), (3, 8500, 0.3), (4, 5500, 0.5), (5, 3800, 0.6),
                          (6, 2600, 0.8), (8, 1400, 1.2), (10, 900, 1.8), (12, 600, 2.5), (15, 400, 3.5),
                          (20, 200, 5.0)],
    ("Aluminium", "N₂"): [(1, 30000, 0.2), (2, 15000, 0.3), (3, 8000, 0.3), (4, 5500, 0.5), (5, 3800, 0.6),
                          (6, 2500, 0.8), (8, 1300, 1.2), (10, 800, 1.8), (12, 550, 2.5), (15, 350, 3.5),
                          (20, 180, 5.0)]}


def beispiel_blech_kfaktoren():
    """K-Faktoren nach DIN 6935 (k = (0,65 + 0,5·lg(ri/s)) / 2, höchstens 0,5) an der oberen Grenze je Bereich
    Innenradius ÷ Dicke; ri = s ergibt wie bisher 0,33. Beispielwerte, gleich für alle Kategorien und Dicken."""
    b = "Beispiel nach DIN 6935, bitte anpassen"
    stufen = ((0.5, 0.25), (1, 0.33), (2, 0.4), (3, 0.44), (5, 0.5), (1000, 0.5))
    return [(kat, 100, ri, k, b) for kat in ("Stahl", "Edelstahl", "Aluminium") for ri, k in stufen]


def beispiel_blechlaser():
    return [(kat, gas, d, v, round(v * 0.5, -1), ein, None, "Richtwert Faser 6 kW")
            for (kat, gas), stufen in BLECHLASER_RICHTWERTE.items() for d, v, ein in stufen]


def beispiel_werkstoffe():
    """Werkstoffe mit Kategorie (Beispiel-Tonnenpreise, bitte durch eigene ersetzen) und Lasereigenschaften
    (Rohrart, Schneidgas, Vorschub-Faktor, Laser, Laser-Hinweis; Richtwerte, Patrick 24.10.2026). Je Zeile alle
    Felder der Tabelle Werkstoffe in deren Reihenfolge (Anfrage-Spalten und Teuerungszuschlag leer)."""
    return [w[:9] + (None, None, None) + w[9:] + (None, None, None) for w in _BEISPIEL_WERKSTOFFE]


_ST, _ES, _AL, _BM = "Stahl", "Edelstahl", "Aluminium", "Buntmetall"
_ROHR_S, _PRAEZ = "EN 10219 kaltgefertigt, geschweißt", "EN 10305-3 Präzisionsstahlrohr, geschweißt, maßgewalzt"
_ROHR_W, _ROHR_E = "EN 10210 warmgefertigt", "EN 10217-7 / ASTM A554"
_GS, _NL, _SP = ROHRARTEN
_N2, _O2 = GAS_VORGABEN[1:]
_ZINK = "verzinkt: Zinkdampf, Absaugung prüfen; nur N₂ (O₂ brennt die Zinkschicht ab), leichter Grat innen"
_ZUNDER = "warmgefertigt: Zunder auf der Oberfläche, Vorschub etwas geringer, Einstich unruhiger"
_HOCHFEST = "hochfest: Vorschub etwas geringer, Kante bei O₂ härter (Gewinde/Senkungen prüfen)"
_BUNT = "stark reflektierend: nur Faserlaser"
# (Werkstoff-ID, Kategorie, Werkstoff, Werkstoff-Nr., Norm, Dichte, Bemerkung, Tonnenpreis, Angebotstext,
#  Rohrart, Schneidgas, Vorschub-Faktor, Laser, Laser-Hinweis)
_BEISPIEL_WERKSTOFFE = [
    ("S235-10219", _ST, "S235JRH", "1.0039", _ROHR_S, 7.85, "Beispiel", 1000, "S235 EN10219", _GS),
    ("S355-10219", _ST, "S355J2H", "1.0576", _ROHR_S, 7.85, "Beispiel", 1050, "S355 EN10219", _GS),
    ("E235-10305", _ST, "E235", "1.0308", _PRAEZ, 7.85, "Beispiel", 1150, "E235 EN10305-3", _GS),
    ("E355-10305", _ST, "E355", "1.0580", _PRAEZ, 7.85, "Beispiel", 1250, "E355 EN10305-3", _GS),
    ("1.4301", _ES, "X5CrNi18-10", "1.4301", _ROHR_E, 7.90, "Beispiel", 4200, "1.4301 EN10217-7", _GS),
    ("1.4307", _ES, "X2CrNi18-9", "1.4307", _ROHR_E, 7.90, "Beispiel", 4300, "1.4307 EN10217-7", _GS),
    ("1.4404", _ES, "X2CrNiMo17-12-2", "1.4404", _ROHR_E, 8.00, "Beispiel", 5600, "1.4404 EN10217-7", _GS),
    ("1.4571", _ES, "X6CrNiMoTi17-12-2", "1.4571", _ROHR_E, 8.00, "Beispiel", 5900, "1.4571 EN10217-7", _GS, None,
     0.95),
    ("1.4509", _ES, "X2CrTiNb18", "1.4509", "EN 10296-2 (ferritisch)", 7.70, "Beispiel", 3600, "1.4509 EN10296-2",
     _GS),
    ("AW6060-T66", _AL, "EN AW-6060 T66", "3.3206", "EN 755-2", 2.70, "Beispiel", 4500, "EN AW-6060 T66", _SP),
    ("AW6063-T66", _AL, "EN AW-6063 T66", None, "EN 755-2", 2.70, "Beispiel", 4600, "EN AW-6063 T66", _SP),
    ("AW6082-T6", _AL, "EN AW-6082 T6", "3.2315", "EN 755-2", 2.70, "Beispiel", 4800, "EN AW-6082 T6", _SP),
    # seit 24.10.2026: typische Rohr- und Profilwerkstoffe am Rohrlaser
    ("S235-10210", _ST, "S235JRH", "1.0039", _ROHR_W, 7.85, "Beispiel", 1050, "S235 EN10210", _GS, None, 0.95, None,
     _ZUNDER),
    ("S355-10210", _ST, "S355J2H", "1.0576", _ROHR_W, 7.85, "Beispiel", 1100, "S355 EN10210", _GS, None, 0.95, None,
     _ZUNDER),
    ("DX51D+Z275", _ST, "DX51D+Z275", "1.0226", "EN 10305-3 / EN 10346 sendzimirverzinkt", 7.85, "Beispiel", 1300,
     "DX51D+Z275 sendzimirverzinkt", _GS, _N2, 0.90, None, _ZINK),
    ("E195-10305", _ST, "E195", "1.0034", _PRAEZ, 7.85, "Beispiel", 1150, "E195 EN10305-3", _GS),
    ("P235TR1", _ST, "P235TR1", "1.0254", "EN 10217-1 geschweißt (Leitungsrohr)", 7.85, "Beispiel", 1100,
     "P235TR1 EN10217-1", _GS),
    ("P235GH-10216", _ST, "P235GH", "1.0345", "EN 10216-2 nahtlos (Kesselrohr)", 7.85, "Beispiel", 1400,
     "P235GH EN10216-2 nahtlos", _NL),
    ("S420MH", _ST, "S420MH", "1.8750", _ROHR_S + " (Feinkorn)", 7.85, "Beispiel", 1250, "S420MH EN10219", _GS, None,
     0.95, None, _HOCHFEST),
    ("S460MH", _ST, "S460MH", "1.8953", _ROHR_S + " (Feinkorn)", 7.85, "Beispiel", 1350, "S460MH EN10219", _GS, None,
     0.95, None, _HOCHFEST),
    ("S355J2WH", _ST, "S355J2WH", "1.8965", "EN 10219 wetterfest (Corten)", 7.85, "Beispiel", 1600,
     "S355J2WH wetterfest", _GS, None, 0.95, None, "wetterfest: Kante mit N₂ schneiden, damit die Patina gleichmäßig "
     "wächst"),
    ("1.4541", _ES, "X6CrNiTi18-10", "1.4541", _ROHR_E, 7.90, "Beispiel", 4600, "1.4541 EN10217-7", _GS, None, 0.95),
    ("1.4016", _ES, "X6Cr17", "1.4016", "EN 10296-2 (ferritisch)", 7.70, "Beispiel", 2900, "1.4016 EN10296-2", _GS),
    ("1.4003", _ES, "X2CrNi12", "1.4003", "EN 10296-2 (ferritisch, 3CR12)", 7.70, "Beispiel", 2600,
     "1.4003 EN10296-2", _GS, None, 0.95),
    ("1.4462", _ES, "X2CrNiMoN22-5-3", "1.4462", "EN 10217-7 (Duplex)", 7.80, "Beispiel", 8000, "1.4462 Duplex", _GS,
     _N2, 0.80, None, "Duplex: zäh, Vorschub rund 20 % geringer, nur N₂"),
    ("AW6061-T6", _AL, "EN AW-6061 T6", "3.3211", "EN 755-2", 2.70, "Beispiel", 5000, "EN AW-6061 T6", _SP),
    ("AW6005A-T6", _AL, "EN AW-6005A T6", "3.3210", "EN 755-2", 2.70, "Beispiel", 4700, "EN AW-6005A T6", _SP),
    ("CuZn37", _BM, "CuZn37 (Messing)", "CW508L", "EN 12449 nahtlos gezogen", 8.44, "Beispiel", 7500,
     "Messing CuZn37", _NL, _N2, None, NUR_FASER, "Messing " + _BUNT + ", N₂"),
    ("Cu-DHP", _BM, "Cu-DHP (Kupfer)", "CW024A", "EN 12449 / EN 1057 nahtlos", 8.94, "Beispiel", 9500,
     "Kupfer Cu-DHP", _NL, _O2, None, NUR_FASER, "Kupfer " + _BUNT + ", mit O₂, Vorschub gering")]
_BEISPIEL_WERKSTOFFE = [w + (None,) * (14 - len(w)) for w in _BEISPIEL_WERKSTOFFE]
# bis Schema 54 vorhandene Beispielwerkstoffe (bekommen beim Update nur ihre leeren Lasereigenschaften)
ALTE_BEISPIEL_WERKSTOFFE = tuple(w[0] for w in _BEISPIEL_WERKSTOFFE[:12])


def beispiel_oberflaechen():
    """Oberflächen des Rohmaterials (Beispiel-Aufpreise, bitte durch eigene ersetzen)."""
    return [(ROH, None, 0.0, None, "ohne Aufpreis; leer in der Position heißt ebenfalls roh"),
            ("gestrahlt", None, 1.50, "gestrahlt", "Beispielpreis; Stahl SA 2½, Edelstahl glasperlgestrahlt"),
            ("K240", "Edelstahl", 2.20, "Oberfläche K240 geschliffen", "Beispielpreis"),
            ("K320", "Edelstahl", 2.80, "Oberfläche K320 geschliffen", "Beispielpreis"),
            ("gebeizt", "Edelstahl", 1.20, "gebeizt und passiviert", "Beispielpreis"),
            ("E6/EV1", "Aluminium", 3.50, "E6/EV1 eloxiert", "Beispielpreis")]


# 3D-Bearbeitung je Maschine (Patrick 22.10.2026, F2 a): keine vorbelegt; Grenzen ±45°, Greifmaß 300 mm, Zusatzzeit
# 0 s, Faktor 1 – (verfügbar, Schwenk min., Schwenk max., Greifmaß, Zusatzzeit, Faktor)
MASCHINE_3D = ("nein", -45, 45, 300, 0, 1.0)
# Maschinen (Werte von Patrick, 20.10.2026): T03 Trumpf CO₂-Laser, T11 Trumpf und LT7 Adige Faserlaser
BEISPIEL_MASCHINEN = [
    ("T03", "Trumpf", 10, 142, 0.2, 6500, 150.00, 10, 50, 3, 8, 5, 5, 24, 29, "CO₂-Laser", 255, 36, 2500, *MASCHINE_3D),
    ("T11", "Trumpf", 10, 142, 0.2, 6500, 150.00, 10, 50, 3, 8, 5, 5, 24, 29, "Faserlaser", 255, 36, 2500, *MASCHINE_3D),
    ("LT7", "Adige", 10, 120, 0.2, 6500, 150.00, 10, 50, 3, 8, 5, 5, 24, 29, "Faserlaser", 214, 23, 2500, *MASCHINE_3D)]
# Stangenwechsel bis 0.8.9 (ein Wert je Maschine); seit 0.8.10 normal 24 s und mit Schweißnaht-Vorgabe (SN) 29 s
ALTER_STANGENWECHSEL = {"T03": 29, "T11": 29, "LT7": 25}
LASER = {"T03": "CO₂", "T11": "Faser", "LT7": "Faser"}
# Laserleistung laut Patrick (20.10.2026): T03 3,2 kW, T11 4 kW, LT7 3 kW
LEISTUNG = {"T03": 3.2, "T11": 4.0, "LT7": 3.0}

# Bis 0.5.8: Beispielmaschinen RL-1/RL-2 (Werte ab 'endbeschnitt'); unverändert werden sie beim Update zu T03/T11
ALTE_MASCHINEN = {"RL-1": ("T03", (20, 80, 0.3, 6500, 120.00, 10, 50, 2, 15, 30)),
                  "RL-2": ("T11", (15, 120, 0.3, 8500, 140.00, 10, 50, 2, 20, 40))}
MASCHINE_WERTE = ("endbeschnitt", "greiferrest", "schnittverlust", "max_stange", "stundensatz", "kontur_klein",
                  "kontur_mittel", "abstand", "ruestzeit", "stangenwechsel")

# Richtwerte Schneiddaten je Maschine, Kategorie und Gas: [(Wandstärke bis, Vorschub groß, Einstechzeit)].
# Herkunft (Stand 21.10.2026): Rohr-Schnitttabellen Faserlaser 3 und 4 kW (GWEIKE, Fiber Laser Tube Cutting
# Parameters), keine Trumpf- oder Adige-Werte. Am Rohr begrenzt bei dünnen Wänden die Drehachse (bis 2 mm höchstens
# 7.000–8.000 mm/min), mehr Leistung hilft erst ab 3 mm: T11 (4 kW) hat bis 2 mm die Werte von LT7 (3 kW), darüber
# rund 30 % mehr. Stahl mit N₂ bis 4 mm (Patrick 21.10.2026: saubere Kante), darüber O₂; Edelstahl und Aluminium nur
# N₂. CO₂ (T03): Schätzwerte (keine öffentliche Tabelle), Stahl mit N₂ bis 2 mm, Aluminium nur bis 6 mm.
_FASER_3KW = {
    ("Stahl", "N₂"): [(1, 8000, 0.1), (1.5, 7500, 0.15), (2, 7000, 0.2), (3, 4500, 0.3), (4, 3500, 0.5)],
    ("Stahl", "O₂"): [(5, 2200, 0.8), (6, 2000, 1.0), (8, 1300, 1.5), (10, 1200, 2.0), (12, 800, 3.0)],
    ("Edelstahl", "N₂"): [(1, 7000, 0.1), (1.5, 6500, 0.15), (2, 6000, 0.2), (3, 4500, 0.3), (4, 3500, 0.5),
                          (5, 2200, 0.7), (6, 1500, 0.8), (8, 800, 1.2), (10, 500, 1.6)],
    ("Aluminium", "N₂"): [(1, 7000, 0.1), (1.5, 6500, 0.15), (2, 6000, 0.2), (3, 4000, 0.3), (4, 3000, 0.5),
                          (5, 2000, 0.7), (6, 1100, 0.8), (8, 550, 1.2)]}
_FASER_4KW = {
    ("Stahl", "N₂"): [(1, 8000, 0.1), (1.5, 7500, 0.15), (2, 7000, 0.2), (3, 5800, 0.3), (4, 4500, 0.5)],
    ("Stahl", "O₂"): [(5, 2700, 0.8), (6, 2600, 1.0), (8, 2100, 1.5), (10, 1300, 2.0), (12, 1100, 3.0)],
    ("Edelstahl", "N₂"): [(1, 7000, 0.1), (1.5, 6500, 0.15), (2, 6000, 0.2), (3, 5800, 0.3), (4, 4500, 0.5),
                          (5, 2900, 0.7), (6, 2000, 0.8), (8, 1000, 1.2), (10, 650, 1.6)],
    ("Aluminium", "N₂"): [(1, 7000, 0.1), (1.5, 6500, 0.15), (2, 6000, 0.2), (3, 5200, 0.3), (4, 3900, 0.5),
                          (5, 2600, 0.7), (6, 1400, 0.8), (8, 700, 1.2)]}
_CO2 = {
    ("Stahl", "N₂"): [(1, 6000, 0.15), (1.5, 5000, 0.2), (2, 4000, 0.3)],
    ("Stahl", "O₂"): [(3, 3000, 0.5), (4, 2600, 0.7), (5, 2300, 1.0), (6, 2000, 1.3), (8, 1500, 1.8),
                      (10, 1100, 2.5), (12, 850, 3.5)],
    ("Edelstahl", "N₂"): [(1, 6000, 0.15), (1.5, 5000, 0.2), (2, 4000, 0.3), (3, 2500, 0.5), (4, 1700, 0.8),
                          (5, 1200, 1.0), (6, 900, 1.2), (8, 500, 1.8)],
    ("Aluminium", "N₂"): [(1, 5500, 0.15), (1.5, 4500, 0.2), (2, 3500, 0.3), (3, 2000, 0.5), (4, 1300, 0.8),
                          (5, 900, 1.0), (6, 600, 1.2)]}
# Buntmetall (24.10.2026): nur Faser (CO₂ reflektiert), Messing mit N₂, Kupfer mit O₂; Schätzwerte nach Faser-
# Rohrtabellen, bitte mit echten Schnitten abgleichen. T03 (CO₂) bekommt keine Zeilen.
_FASER_3KW[("Buntmetall", "N₂")] = [(1, 6000, 0.2), (1.5, 5000, 0.3), (2, 3500, 0.4), (3, 1800, 0.6), (4, 1000, 0.8),
                                   (5, 600, 1.0)]
_FASER_3KW[("Buntmetall", "O₂")] = [(1, 4000, 0.2), (1.5, 3000, 0.3), (2, 1800, 0.5), (3, 900, 0.8), (4, 500, 1.2)]
_FASER_4KW[("Buntmetall", "N₂")] = [(1, 6000, 0.2), (1.5, 5000, 0.3), (2, 3500, 0.4), (3, 2300, 0.6), (4, 1300, 0.8),
                                   (5, 800, 1.0)]
_FASER_4KW[("Buntmetall", "O₂")] = [(1, 4000, 0.2), (1.5, 3000, 0.3), (2, 1800, 0.5), (3, 1200, 0.8), (4, 650, 1.2)]
# Stand 21.10.2026 (0.6.19 bis 0.9.196): unveränderte Zeilen dieser Fassung ersetzt das Update einmalig
_RICHTWERTE_2110 = {m: {k: list(v) for k, v in t.items()} for m, t in
                    (("T03", _CO2), ("T11", _FASER_4KW), ("LT7", _FASER_3KW))}
# Abgleich mit Schneidtabellen 29.10.2026 (Freigabe Patrick „1a 2a 3a 4a 5c“): V1 Stahl N₂ 3–4 mm vorsichtig
# geschätzt (keine Herstellerwerte bei 3–4 kW, N₂ bleibt bis 4 mm), V2/V3 Edelstahl auf die Untergrenze der GWEIKE-
# Rohrtabellen, V5 Einstechzeit Edelstahl nach Hypertherm HFL030 (3 kW, Flachbett)
_VORSCHUB_2910 = {("LT7", "Stahl", "N₂"): {3: 3500, 4: 2500}, ("T11", "Stahl", "N₂"): {3: 4000, 4: 3000},
                  ("LT7", "Edelstahl", "N₂"): {3: 5000, 4: 4500}, ("T11", "Edelstahl", "N₂"): {6: 2200}}
EINSTECHEN_EDELSTAHL = {1: 0.2, 1.5: 0.2, 2: 0.2, 3: 0.5, 4: 0.5, 5: 0.5, 6: 1.0, 8: 1.5, 10: 2.0}
# V4: Trumpf TruLaser Tube 5000 fiber mit TruFiber 4001 (T11) schneidet am Rohr höchstens 10 mm Baustahl, 6 mm
# Edelstahl und Aluminium, 5 mm Kupfer/Messing (Technische Daten Trumpf); Zeilen darüber entfallen, das Programm
# warnt dann statt zu rechnen (rechnen.wand_ueber_schneiddaten)
GRENZE_WAND = {"T11": {"Stahl": 10, "Edelstahl": 6, "Aluminium": 6, "Buntmetall": 5}}
GRENZE_TEXT = {"T11": "Grenze Trumpf TruLaser Tube 5000 fiber 4 kW"}
for (_m, _kat, _gas), _neu in _VORSCHUB_2910.items():
    {"LT7": _FASER_3KW, "T11": _FASER_4KW}[_m][(_kat, _gas)] = [
        (w, _neu.get(w, v), e) for w, v, e in {"LT7": _FASER_3KW, "T11": _FASER_4KW}[_m][(_kat, _gas)]]
for _t in (_FASER_3KW, _FASER_4KW):
    _t[("Edelstahl", "N₂")] = [(w, v, EINSTECHEN_EDELSTAHL.get(w, e)) for w, v, e in _t[("Edelstahl", "N₂")]]
for _m, _grenzen in GRENZE_WAND.items():
    _t = {"T11": _FASER_4KW}[_m]
    for (_kat, _gas), _stufen in list(_t.items()):
        _t[(_kat, _gas)] = [z for z in _stufen if z[0] <= _grenzen.get(_kat, 1000)]
RICHTWERTE = {"T03": _CO2, "T11": _FASER_4KW, "LT7": _FASER_3KW}
# Herkunft je Zeile für die Bemerkung (V6): Wandstärken mit Werten aus den GWEIKE-Rohrtabellen je Leistung
_GWEIKE = {("Stahl", "N₂"): {3: (1, 1.5, 2), 4: (1, 1.5, 2)}, ("Stahl", "O₂"): {3: (6, 8, 10, 12), 4: (6, 8, 10, 12)},
           ("Edelstahl", "N₂"): {3: (1, 1.5, 2, 3, 4, 6), 4: (1, 1.5, 2, 3, 4, 6)}}
# Richtwerte 0.5.13 bis 0.6.18 (Flachbett-Tabellen mit ≈ 40 % Rohrabschlag, T11 = Faser × 1,2); unveränderte Zeilen
# dieser Fassung ersetzt das Update einmalig (Datenbank._richtwerte_anpassen)
_ALTE_FAKTOR = {"T03": 1.0, "T11": 1.2, "LT7": 1.0}
_ALTE_RICHTWERTE = {
    "Faser": {
        ("Stahl", "N₂"): [(1, 12000, 0.1), (1.5, 10000, 0.15), (2, 8000, 0.2), (3, 5000, 0.3), (4, 3200, 0.5)],
        ("Stahl", "O₂"): [(5, 2600, 0.8), (6, 2200, 1.0), (8, 1600, 1.5), (10, 1200, 2.0), (12, 900, 3.0)],
        ("Edelstahl", "N₂"): [(1, 11000, 0.1), (1.5, 9000, 0.15), (2, 7000, 0.2), (3, 4200, 0.3), (4, 2800, 0.5),
                              (5, 1900, 0.7), (6, 1300, 0.8), (8, 700, 1.2), (10, 450, 1.6)],
        ("Aluminium", "N₂"): [(1, 10000, 0.1), (1.5, 8500, 0.15), (2, 7000, 0.2), (3, 4000, 0.3), (4, 2600, 0.5),
                              (5, 1700, 0.7), (6, 1100, 0.8), (8, 550, 1.2)]},
    "CO₂": {
        ("Stahl", "N₂"): [(1, 6000, 0.15), (1.5, 5000, 0.2), (2, 4000, 0.3)],
        ("Stahl", "O₂"): [(3, 3000, 0.5), (4, 2600, 0.7), (5, 2300, 1.0), (6, 2000, 1.3), (8, 1500, 1.8),
                          (10, 1100, 2.5), (12, 850, 3.5)],
        ("Edelstahl", "N₂"): [(1, 6000, 0.15), (1.5, 5000, 0.2), (2, 4000, 0.3), (3, 2500, 0.5), (4, 1700, 0.8),
                              (5, 1200, 1.0), (6, 900, 1.2), (8, 500, 1.8)],
        ("Aluminium", "N₂"): [(1, 5500, 0.15), (1.5, 4500, 0.2), (2, 3500, 0.3), (3, 2000, 0.5), (4, 1300, 0.8),
                              (5, 900, 1.0), (6, 600, 1.2)]}}
# Vorschub Gravur: 3.000 mm/min für alle Maschinen (Patrick, 21.10.2026); bis 0.6.3 Faser 15.000, CO₂ 10.000
GRAVUR = {"Faser": 3000, "CO₂": 3000}
ALTE_GRAVUR = (15000, 10000)
RICHTWERT_TEXT = {"Faser": "Beispiel: Richtwert Faserlaser", "CO₂": "Beispiel: Richtwert CO₂-Laser"}


def richtwert_quelle(m, kat, gas, wand):
    """Herkunft einer Richtwert-Zeile für die Bemerkung (Patrick 29.10.2026, V6): Herstellerwert oder Schätzung."""
    if LASER.get(m) != "Faser":
        return "Vorschub: Schätzung; Einstechen: Schätzung"
    kw = round(LEISTUNG[m])
    if float(wand) in _GWEIKE.get((kat, gas), {}).get(kw, ()):
        v = f"GWEIKE Rohr {3 if (kat, gas) == ('Stahl', 'N₂') else kw} kW"    # Stahl N₂ dünn: Drehachse begrenzt
    elif (kat, gas) == ("Stahl", "N₂"):
        v = "Schätzung (N₂ bis 4 mm, kein Herstellerwert)"
    else:
        v = "Schätzung"
    e = "Hypertherm 3 kW Flachbett" if kat == "Edelstahl" else "Schätzung"
    text = f"Vorschub: {v}; Einstechen: {e}"
    if wand == GRENZE_WAND.get(m, {}).get(kat):
        text += f"; {GRENZE_TEXT[m]}: bis {zahl_als_text(wand)} mm"
    return text
# Zeit je Ecke im Anfangs- und Endschnitt (Patrick 29.10.2026, S2 „nach Wandstärke“): 0,2 s + 0,05 s je mm
# 'Wandstärke bis' der Zeile (1 mm 0,25 s, 3 mm 0,35 s, 8 mm 0,6 s, 12 mm 0,8 s); bis 0.9.195 leer
ECKE_GRUND, ECKE_JE_MM = 0.2, 0.05


def zeit_ecke(wand_bis):
    """Standard 'Zeit je Ecke' [s] einer Schneiddaten-Zeile mit dieser 'Wandstärke bis' [mm]."""
    return round(ECKE_GRUND + ECKE_JE_MM * float(wand_bis), 2)


def beispiel_schneiddaten():
    """Schneiddaten je Kategorie (Werkstoff-ID leer) für T03 (CO₂) sowie T11 und LT7 (Faser) aus den Richtwerten.
    Vorschub mittel 60 %, klein 30 % von groß: kleine Konturen begrenzt am Rohr die Dynamik, nicht die Leistung.
    Zeit je Ecke nach Wandstärke (zeit_ecke: Quadrat-/Rechteckrohr bremsen und drehen an jeder Ecke)."""
    out = []
    for m, laser in LASER.items():
        text = f"{RICHTWERT_TEXT[laser]} {zahl_als_text(LEISTUNG[m])} kW, Rohr"
        for (kat, gas), stufen in RICHTWERTE[m].items():
            for wand, v, ein in stufen:
                out.append((m, None, kat, gas, wand, v, round(v * 0.6, -1), round(v * 0.3, -1), ein, GRAVUR[laser],
                            f"{text}; {richtwert_quelle(m, kat, gas, wand)}", zeit_ecke(wand)))
    return out


def richtwerte_2110():
    """{(Maschine, Kategorie, Gas, Wandstärke bis): (Vorschub groß, mittel, klein, Einstechzeit)} der Richtwerte
    0.6.19 bis 0.9.196 (Stand 21.10.2026)."""
    return {(m, kat, gas, float(wand)): (float(v), float(round(v * 0.6, -1)), float(round(v * 0.3, -1)), float(ein))
            for m, tab in _RICHTWERTE_2110.items() for (kat, gas), stufen in tab.items() for wand, v, ein in stufen}


def alte_richtwerte():
    """{(Maschine, Kategorie, Gas, Wandstärke bis): (Vorschub groß, mittel, klein, Einstechzeit)} der Richtwerte 0.5.13
    bis 0.6.18."""
    out = {}
    for m, laser in LASER.items():
        for (kat, gas), stufen in _ALTE_RICHTWERTE[laser].items():
            for wand, v, ein in stufen:
                v = round(v * _ALTE_FAKTOR[m], -1)
                out[(m, kat, gas, float(wand))] = (float(v), float(round(v * 0.6, -1)), float(round(v * 0.3, -1)),
                                                   float(ein))
    return out


# Bis 0.5.8: Beispiel-Schneiddaten (RL-1, RL-2 = RL-1 × 1,2); unveränderte Zeilen ersetzt das Update
ALTE_VORSCHUB = {
    ("Stahl", "N₂"): [(1, 9000), (1.5, 8000), (2, 7000), (3, 5000), (4, 3500)],
    ("Stahl", "O₂"): [(1, 5500), (1.5, 5000), (2, 4500), (3, 3600), (4, 3000), (5, 2500), (6, 2100), (8, 1500),
                      (10, 1100)],
    ("Edelstahl", "N₂"): [(1, 8000), (1.5, 7000), (2, 6000), (3, 4000), (4, 3000), (5, 2200), (6, 1700), (8, 1000)],
    ("Edelstahl", "O₂"): [(10, 900)],
    ("Aluminium", "N₂"): [(1, 10000), (1.5, 9000), (2, 8000), (3, 5500), (4, 4000), (5, 3000), (6, 2300)],
    ("Aluminium", "O₂"): [(8, 1400), (10, 1000)],
}


def alte_beispiel_schneiddaten():
    """Werte (kategorie, gas, wand_bis, vorschub groß, mittel, klein, einstechzeit, gravur) der Beispielzeilen bis
    0.5.8, unabhängig von der Maschinen-ID (RL-1/RL-2 können von Hand umbenannt sein)."""
    out = set()
    for faktor in (1.0, 1.2):
        for (kat, gas), stufen in ALTE_VORSCHUB.items():
            for wand, v in stufen:
                v = round(v * faktor, -1)
                ein = round(0.1 + wand * (0.18 if gas == "O₂" else 0.12), 1)
                out.add((kat, gas, float(wand), float(v), float(round(v * 0.7, -1)), float(round(v * 0.4, -1)),
                         float(ein), float(12000 if gas == "N₂" else 10000)))
    return out


def beispiel_stundensaetze():
    """Vorbelegung der Stundensätze (Beispielwerte, bitte durch eigene ersetzen)."""
    werte = [("Programmierung", "Programmierung / CAD", 60.0), ("Rüstpersonal", "Rüsten und Materialbereitstellung", 48.0),
             ("Nachbearbeitung", "Entgraten, manuelle Nacharbeit", 45.0), ("Qualitätskontrolle", "Prüfen, Messen", 50.0),
             ("Verpackung", "Verpacken, Kommissionieren", 40.0), ("Sonstige", "Sonstige Arbeitsplätze", 45.0),
             (SATZ_SCHWEISSEN, "Schweißen (Zusatzarbeit Schweißen)", 75.0)]
    return [dict(satz_id=i, bezeichnung=b, satz=w, bemerkung="Beispielwert, bitte anpassen") for i, b, w in werte]


def beispiel_arbeitsschritte():
    """Vorbelegung der Arbeitsschritte: die vom Programm gerechneten mit dem Maschinenstundensatz (wie bisher),
    weitere Schritte mit Zeit 0 (rechnen erst, wenn eine Zeit eingetragen ist)."""
    fest = [dict(schritt=n, satz=SCHRITT_SATZ.get(n, SATZ_MASCHINE), art="Personal" if n in SCHRITT_SATZ else "Maschine",
                 parallel="ja" if n in SCHRITT_SATZ else "nein", bemerkung="Zeit: " + t)
            for n, t in SCHRITTE_FEST.items()]
    weitere = [("Materialbereitstellung", "Rüstpersonal", "Personal", "ja", "Angebot", "Stange",
                "Stangen holen und auflegen, soweit nicht im Stangenwechsel enthalten"),
               ("Entgraten / Nachbearbeitung", "Nachbearbeitung", "Personal", "ja", "Angebot", "Teil",
                "nicht zusätzlich zur Zusatzarbeit Entgraten ansetzen"),
               ("Qualitätskontrolle", "Qualitätskontrolle", "Personal", "ja", "Angebot", "Position",
                "z. B. Erstteilprüfung je Position"),
               ("Verpackung", "Verpackung", "Personal", "nein", "Angebot", "Teil", ""),
               ("Sonstige Arbeiten", "Sonstige", "Personal", "nein", "Angebot", "Teil", "")]
    zeilen = fest + [dict(schritt=n, satz=s, art=a, parallel=p, ruestzeit=0.0, ruest_bezug=rb, zeit=0.0, bezug=b,
                          bemerkung=bem or None) for n, s, a, p, rb, b, bem in weitere]
    return [{f.name: z.get(f.name) for f in ARBEITSSCHRITTE.felder} for z in zeilen]


def beispiel_zusatzarbeiten():
    """Vorbelegung der Zusatzarbeiten (Beispielpreise, bitte durch eigene ersetzen)."""
    werte = [("Feuerverzinken", "€/kg", 0.65, 120.0, "ja", "feuerverzinkt", "Beispielpreis; Mindestbetrag der Verzinkerei",
              "Oberfläche"),
             ("Galvanisch verzinken", "€/kg", 1.20, 80.0, "ja", "galvanisch verzinkt", "Beispielpreis", "Oberfläche"),
             ("Pulverbeschichten", "€/m²", 18.00, 90.0, "ja", "pulverbeschichtet",
              "Beispielpreis; Farbe je Position als Text eintragen, z. B. RAL 7016", "Oberfläche"),
             ("Entgraten", "€/Stück", 0.50, None, "nein", "entgratet", "Beispielpreis", "Nachbearbeitung"),
             ("Gravur extra", "s/Stück", 20.0, None, "nein", "Gravur",
              "Zeit je Gravur in s, wird zur Schneidzeit addiert (Gravur, die nicht im STEP-Modell ist)", "Laser")]
    return [{f.name: (w[i] if i < len(w) else None) for i, f in enumerate(ZUSATZARBEITEN.felder)} for w in werte] \
        + bohr_zusatzarbeiten() + schweiss_zusatzarbeiten() + biege_zusatzarbeiten() + knick_zusatzarbeiten() \
        + saege_zusatzarbeiten() + stege_zusatzarbeiten() + strahl_zusatzarbeiten()


# Schweißen (Patrick 23.10.2026): Abrechnung nach Zeit, Sekunden je Teil im Angebot × Stundensatz 75 €/h
ZUSATZ_SCHWEISSEN = SATZ_SCHWEISSEN = "Schweißen"


def schweiss_zusatzarbeiten():
    """Vorbelegung Schweißen: Abrechnung €/h, die Sekunden je Teil stehen je Position im Angebot (keine
    Vorgabezeit), Stundensatz 'Schweißen' aus den Stundensätzen."""
    return [dict({f.name: None for f in ZUSATZARBEITEN.felder}, name=ZUSATZ_SCHWEISSEN, art="€/h",
                 zeit_einheit="s", satz_id=SATZ_SCHWEISSEN, fremd="nein", angebotstext="geschweißt",
                 bemerkung="Schweißzeit in Sekunden je Teil im Angebot eintragen (Zusatzarbeiten …)",
                 kategorie="Montage", aktiv="ja")]


# Zusatzarbeiten, die 'Bohrungen prüfen' (bohrbild.py) nach dem Bestätigen mit der Anzahl je Teil einträgt
ZUSATZ_SENKEN, ZUSATZ_FLOWDRILL, ZUSATZ_BOHREN = "Senken", "Flowdrill", "Bohren"


BOHR_PREISE = {ZUSATZ_SENKEN: 0.40, ZUSATZ_FLOWDRILL: 0.60, ZUSATZ_BOHREN: 0.40}   # Beispielpreise € je Stück


ZUSATZ_BIEGEN, BIEGEN_PREIS = "Biegen", 1.50     # € je Biegung (Beispielpreis)


def biege_zusatzarbeiten():
    """Vorbelegung Biegen (Biegerohre aus dem STEP-Import, Plan S9): € je Biegung, die Menge (Zahl der Biegungen
    je Teil) trägt der STEP-Import ein. Beispielpreis, bitte anpassen."""
    return [dict({f.name: None for f in ZUSATZARBEITEN.felder}, name=ZUSATZ_BIEGEN, art="€/Stück", preis=BIEGEN_PREIS,
                 fremd="nein", angebotstext="gebogen",
                 bemerkung="Preis je Biegung; Menge = Zahl der Biegungen je Teil (STEP-Import Biegerohr)",
                 kategorie="Nachbearbeitung", aktiv="ja")]


def saege_zusatzarbeiten():
    """Vorbelegung Sägen (Vollmaterial als Zukaufteil, Patrick 25.10.2026 F4 b): € je Schnitt, Menge 1 je Teil
    (STEP-Import und Schnellanlage tragen sie ein). Beispielpreis, bitte anpassen."""
    from .vollmaterial import SAEGEN_PREIS, ZUSATZ_SAEGEN
    return [dict({f.name: None for f in ZUSATZARBEITEN.felder}, name=ZUSATZ_SAEGEN, art="€/Stück",
                 preis=SAEGEN_PREIS, fremd="nein", angebotstext="gesägt",
                 bemerkung="Preis je Schnitt; Menge = Schnitte je Teil (Vollmaterial Rund-/Vierkantstahl)",
                 kategorie="Nachbearbeitung", aktiv="ja")]


def stege_zusatzarbeiten():
    """Vorbelegung Stege abtrennen (virtuelles Bauteil, Patrick 26.10.2026: je Position wählbar): € je Teil, Menge 1
    (Schneidweg-Rechner bzw. Rechtsklick trägt sie ein). Beispielpreis, bitte anpassen."""
    from .virtuell import STEGE_PREIS, ZUSATZ_STEGE
    return [dict({f.name: None for f in ZUSATZARBEITEN.felder}, name=ZUSATZ_STEGE, art="€/Stück",
                 preis=STEGE_PREIS, fremd="nein", angebotstext="Stege abgetrennt und entgratet",
                 bemerkung="Preis je Teil: Stege 2 mm an Ende A und B (virtuelles Bauteil) abtrennen und entgraten",
                 kategorie="Nachbearbeitung", aktiv="ja")]


# Strahlen (Patrick 28.10.2026, Plan Abrechnungsregeln): der Strahler rechnet nach Gewicht, also € je kg Fertigteil
ZUSATZ_STRAHLEN = "Strahlen"


def strahl_zusatzarbeiten():
    """Vorbelegung Strahlen: € je kg Teilegewicht (ohne Verschnitt), Fremdleistung. Beispielpreis, bitte anpassen;
    Preise je Werkstoff über die Arbeitsgang-Regeln (Beispielregeln, aus)."""
    return [dict({f.name: None for f in ZUSATZARBEITEN.felder}, name=ZUSATZ_STRAHLEN, art="€/kg", preis=0.40,
                 mindest=60.0, fremd="ja", angebotstext="gestrahlt",
                 bemerkung="Beispielpreis; Strahler rechnet nach Gewicht der fertigen Teile. Preise je Werkstoff: "
                           "Arbeitsgang-Regeln", kategorie="Oberfläche", aktiv="ja")]


def strahl_regeln():
    """Beispielregeln Strahlen (aus): Preis je Werkstoff-Kategorie und automatisch nach Stichwort."""
    def r(name, **w):
        return dict({f.name: None for f in ARBEITSGANG_REGELN.felder}, **dict(
            dict(name=name, zusatzarbeit=ZUSATZ_STRAHLEN, aktiv="nein", menge_art="automatisch"), **w))
    return [r("Strahlen Stahl", zuordnung="nur Preis", kategorie="Stahl", art="€/kg", preis=0.35, mindest_teil=0.50,
              bemerkung="Beispiel: Preis für Stahl, bei Bedarf aktivieren"),
            r("Strahlen Edelstahl", zuordnung="nur Preis", kategorie="Edelstahl", art="€/kg", preis=0.55,
              mindest_teil=0.80, bemerkung="Beispiel: Glasperlstrahlen Edelstahl teurer"),
            r("Strahlen laut Bezeichnung", zuordnung="automatisch", stichwort="gestrahlt;strahlen;SA 2",
              bemerkung="Beispiel: Strahlen automatisch, wenn es in Bezeichnung oder Artikel steht")]


def knick_zusatzarbeiten():
    """Vorbelegung Knicken (Knickrahmen, Plan K1): € je Knick, die Menge (Zahl der V-Ausschnitte je Teil) trägt der
    Schneidweg-Rechner ein. Beispielpreis, bitte anpassen."""
    from .knickrahmen import KNICKEN_PREIS, ZUSATZ_KNICKEN
    return [dict({f.name: None for f in ZUSATZARBEITEN.felder}, name=ZUSATZ_KNICKEN, art="€/Stück",
                 preis=KNICKEN_PREIS, fremd="nein", angebotstext="geknickt",
                 bemerkung="Preis je Knick; Menge = Zahl der Knicke je Teil (Knickrahmen im Schneidweg-Rechner)",
                 kategorie="Nachbearbeitung", aktiv="ja")]


def bohr_zusatzarbeiten():
    """Vorbelegung Senken, Flowdrill und Bohren: Festpreis € je Stück, keine Zeit (Patrick 22.10.2026;
    Beispielpreise, bitte anpassen)."""
    werte = [(ZUSATZ_SENKEN, "Senken", "Senkung nachträglich senken; Vorschlag aus 'Bohrungen prüfen'"),
             (ZUSATZ_FLOWDRILL, "Fließlochbohren (Flowdrill)",
              "Fließlochbohrung mit Kragen; Vorschlag aus 'Bohrungen prüfen'"),
             (ZUSATZ_BOHREN, "Bohren",
              "Bohrung kleiner 0,7 × Wandstärke: der Laser markiert nur, danach aufbohren; Vorschlag aus "
              "'Bohrungen prüfen'")]
    return [dict({f.name: None for f in ZUSATZARBEITEN.felder}, name=n, art="€/Stück", preis=BOHR_PREISE[n],
                 fremd="nein", angebotstext=t, bemerkung=b, kategorie="Nachbearbeitung", aktiv="ja")
            for n, t, b in werte]

