"""Aufbau der Stammdaten: Tabellen, Felder, Prüfregeln und berechnete Spalten.

Eine Beschreibung je Tabelle dient für alles: Datenbankschema, Anzeige im Programm und Prüfung.
"""
import datetime
import math
import re
from dataclasses import dataclass, field

from . import naht, normprofile, rp_profile

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
KATEGORIEN = ("Stahl", "Edelstahl", "Aluminium")
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
ZUKAUF_TYPEN = ("Blech",)              # besondere Artikeltypen (leer = normaler Zukaufartikel)
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
     Feld("laengenvergleich", "Lieferlängen vergleichen", "auswahl", auswahl="janein", breite=85)),
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
    "Stangenlänge des Angebots geplant, weitere Lieferlängen (z. B. 12 m) werden nicht verglichen.",
    berechnet=(("Fläche berechnet [mm²]", lambda z, k: flaeche_berechnet(z), 1),
               ("Fläche wirksam [mm²]", lambda z, k: flaeche_wirksam(z), 1),
               ("Hüllkreis-Ø [mm]", lambda z, k: huellkreis(z), 1)))

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
     Feld("anfrage_toleranz", "Anfrage: Maßtoleranzen nach Norm", "auswahl", auswahl="janein", breite=100)),
    ("werkstoff_id",),
    "Die Werkstoff-ID ist der Schlüssel für Preise, Schneiddaten und Angebot. Die Kategorie (Stahl, Edelstahl, "
    "Aluminium) ordnet die Auswahl im Angebot und liefert Schneiddaten und Oberflächen, wenn der Werkstoff keine "
    "eigenen hat. Der Tonnenpreis ergibt automatisch den Preis je kg, je m und je Stange; Abweichungen unter "
    "'Preise' eintragen. Die Spalten 'Anfrage: …' setzen die Anforderungen, die in der Materialanfrage unter dem "
    "Werkstoff stehen (Prüfbescheinigung nach EN 10204, Herkunft EU, Maßtoleranzen nach Norm).")

OBERFLAECHEN = Tabelle(
    "oberflaechen", "Oberflächen",
    (Feld("oberflaeche", "Oberfläche", pflicht=True, breite=120),
     Feld("kategorie", "Kategorie (leer = alle)", "auswahl", auswahl="kategorie", breite=110),
     Feld("aufpreis_m", "Aufpreis [€/m]", "zahl", 0, 10000, stellen=2, breite=80),
     Feld("angebotstext", "Text im Angebot", breite=160),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("oberflaeche",),
    "Oberfläche des Rohmaterials, je Position wählbar (leer = roh). Teile mit unterschiedlicher Oberfläche "
    "kommen nie auf dieselbe Stange. Der Aufpreis je m kommt auf den Materialpreis der Stange; ein "
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
     Feld("duese_min", "Mindestabstand Düse [mm]", "zahl", 0, 200, stellen=1, breite=85)),
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
    "darunter liegen und bekommen WARNUNG (prüfen), leer = keine Prüfung.")

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
     Feld("zeit_ecke", "Zeit je Ecke [s]", "zahl", 0, 60, stellen=2, breite=75)),
    ("maschinen_id", "werkstoff_id", "kategorie", "gas", "wand_bis"),
    "Je Maschine + Werkstoff (oder Kategorie) + Schneidgas gestaffelt nach Wandstärke: es gilt die Zeile mit der "
    "kleinsten 'Wandstärke bis', die mindestens der Profilwandstärke entspricht. Zeilen mit Werkstoff-ID gehen "
    "vor; hat der Werkstoff keine passende Zeile, gelten die Zeilen seiner Kategorie (Werkstoff-ID leer). "
    "Schneidgas: N₂, solange es eine N₂-Zeile für die Wandstärke gibt, darüber O₂ (so endet N₂ ab einer "
    "gewissen Wandstärke). Leere Vorschübe mittel/klein/Gravur nehmen den nächstgrößeren. Zeit je Ecke: Zuschlag "
    "je Ecke im Anfangs- und Endschnitt (der Laser bremst ab): RP-Profile nach ihrer Kontur, Quadrat- und "
    "Rechteckrohr 4, andere 0; leer = 0.")

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
     Feld("zuschlag_weitere_basis", "Weiterer Zuschlag auf", "auswahl", auswahl="zuschlagbasis", breite=110)),
    ("name",),
    "Auswahl für 'Zusatzarbeiten …' im Angebot. Abrechnung: €/kg (Teilegewicht), €/m² (Außenfläche = "
    "Umfang × Länge), €/m (Teilelänge), €/Stück, €/Angebot (einmal je Angebot, auf die Teile umgelegt), s/Stück "
    "(Zeit je Stück, wird zur Schneidzeit addiert, z. B. Gravur, die nicht im Teil ist), €/h (Zeit in Sekunden je "
    "Teil, im Angebot je Position eingetragen, × Stundensatz, z. B. Schweißen). Preis je Einheit = "
    "Festpreis + Zeitaufwand × Stundensatz + Material mit Materialzuschlag + weiterer Zuschlag. Mindestbetrag: "
    "liegt die Summe im Angebot darunter, wird auf den Mindestbetrag angehoben. Fremdleistung = ja: Zuschlag "
    "Fremdleistung, sonst Zuschlag Fertigung.")

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
     Feld("bemerkung", "Bemerkung", breite=160)),
    ("kategorie", "gas", "dicke_bis"),
    "Schneiddaten eines Flachbettlasers nur für den Richtpreis im Blech-Editor; sie gehören nicht zu den Rohrlaser-"
    "Maschinen. Je Kategorie und Schneidgas gestaffelt nach Blechdicke: es gilt die Zeile mit der kleinsten "
    "'Blechdicke bis', die mindestens der Blechdicke entspricht; N₂, solange es dafür eine Zeile gibt, darüber O₂. "
    "Leerer Vorschub Innenkonturen = halber Vorschub Außenkontur. Vorbelegt sind Richtwerte eines Faserlasers mit "
    "etwa 6 kW, bitte an den eigenen Blechlaser bzw. Lieferanten anpassen.")

TABELLEN = (KUNDEN, PROFILE, WERKSTOFFE, OBERFLAECHEN, PREISE, LIEFERLAENGEN, MASCHINEN, SCHNEIDDATEN, GEWINDE,
            ZUSATZARBEITEN, STUNDENSAETZE, ARBEITSSCHRITTE, BLECH_WERKSTOFFE, BLECHLASER)
TABELLE = {t.name: t for t in TABELLEN}

# Schlüssel, auf die andere Tabellen verweisen: beim Umbenennen werden die Verweise mitgeändert
VERWEISE = {
    ("kunden", "kundennr"): (("angebote", "kundennr"),),
    ("profile", "profil_id"): (("preise", "profil_id"), ("lieferlaengen", "profil_id")),
    ("werkstoffe", "werkstoff_id"): (("preise", "werkstoff_id"), ("lieferlaengen", "werkstoff_id"),
                                     ("schneiddaten", "werkstoff_id")),
    # Angebote: dazu die Snapshots im Angebot und die Standard-Maschine (Datenbank._maschine_umbenannt)
    ("maschinen", "maschinen_id"): (("schneiddaten", "maschinen_id"), ("angebote", "maschine")),
    ("stundensaetze", "satz_id"): (("arbeitsschritte", "satz"), ("zusatzarbeiten", "satz_id")),
}


# Lieferzeit im Angebot (angebot.lieferzeit_wert / lieferzeit_text): Art der Angabe
ARBEITSTAGE, WOCHEN, KALENDERWOCHE, LIEFERDATUM, NUR_TEXT = (
    "Arbeitstage", "Wochen", "Kalenderwoche", "Lieferdatum", "nur Text")
LIEFERZEIT_ARTEN = (ARBEITSTAGE, WOCHEN, KALENDERWOCHE, LIEFERDATUM, NUR_TEXT)
# Was der Laser an einer Fließlochbohrung (Flowdrill) macht (bohrbild.py): Markierung als Gravur oder kleines Loch
FLIESSLOCH_LASER = ("Gravur Ø0,5", "Loch Ø0,5")
# STEP-Import, Vorgabe für ebene flache Teile (Patrick 22.10.2026: vorerst immer Blech, Flachstahl im Prüfdialog wählbar)
FLACH_ALS = ("Blech", "Flachstahl bis Breite (Einstellung darunter)")
# Herkunft des Materials je Position (angebot.POSITIONEN 'material_herkunft'): leer = Eigenmaterial (wie bisher);
# Kundenmaterial: keine Materialkosten, eigene Stangengruppe, Bearbeitung wie sonst
EIGENMATERIAL, KUNDENMATERIAL = "Eigenmaterial", "Kunde beigestellt"
MATERIAL_HERKUNFT = (EIGENMATERIAL, KUNDENMATERIAL)


# ------------------------------------------------------------------ Einstellungen
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
    Einstellung("gewinn", "Gewinn", "Kalkulation", "anteil", 0.10, 0, 5),
    # Standardaufschlag der Anwendung für Zukaufteile (gilt, wenn weder Artikel noch Kategorie einen haben);
    # leer = keiner (das Programm warnt dann)
    Einstellung("zukauf_aufschlag", "Standardaufschlag Zukaufteile [% auf Einstand] (leer = keiner)", "Kalkulation",
                "zahl_leer", None, 0, 1000),
    Einstellung("ruesten_abmessung", "Rüstzeit je Abmessung [min]", "Kalkulation", "zahl", 15.0, 0, 1440),
    Einstellung("pauschale_abmessung", "Pauschale je Abmessung [€]", "Kalkulation", "zahl", 22.50, 0, 100000),
    # Programmierung als Zeit × Stundensatz 'Programmierung' (Patrick 22.10.2026; bis 0.8.21: 8,50 € je Position):
    # Grundzeit je Position + Zeit je Innenkontur, je Position von Hand überschreibbar
    Einstellung("programmierung_zeit", "Programmierzeit je Position [min]", "Kalkulation", "zahl", 5.0, 0, 1440),
    Einstellung("programmierung_kontur", "Programmierzeit je Innenkontur [min]", "Kalkulation", "zahl", 0.5, 0, 1440),
    Einstellung("angebotsaufschlag", "Angebotsaufschlag je Angebot [€]", "Kalkulation", "zahl", 50.0, 0, 100000),
    # Patrick 22.10.2026 (F4 a): eigene Zeit je Teil, dessen Anbauteile unsicher erkannt sind (Stundensatz Laser)
    Einstellung("pruefzeit_anbau", "Prüfzeit je Teil mit unsicher erkannten Anbauteilen [min]", "Kalkulation",
                "zahl", 0.0, 0, 1000),
    # Mindestangebotspreis netto (nach Skonto, vor MwSt) für neue Angebote; darunter werden die Stückpreise anteilig
    # angehoben. 0 = keiner.
    # Kundenmaterial (Spalte Material: Kunde beigestellt): keine Materialkosten; optional Handling je m der
    # beigestellten Stangen mit Zuschlag Fertigung und Gewinn. Vorgabe 0 = aus
    Einstellung("handling_beistellung", "Handling Kundenmaterial je m Stangenlänge [€/m] (0 = keins)",
                "Kalkulation", "zahl", 0.0, 0, 1000),
    # im Angebots-PDF: Hinweis, welche Stangen der Kunde beistellen muss
    Einstellung("beistellung_hinweis", "Angebots-PDF: Hinweis zum Kundenmaterial mit Stangenbedarf", "Angebots-PDF",
                "auswahl", "ja", auswahl="janein"),
    Einstellung("mindestpreis", "Mindestpreis je Angebot netto [€] (0 = keiner)", "Kalkulation", "zahl", 200.0, 0,
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
    Einstellung("blech_kantung", "Kanten: Preis je Kantung [€]", "Blech-Richtpreis", "zahl", 1.20, 0, 10000),
    Einstellung("blech_ruesten_kanten", "Kanten: Rüsten je Auftrag [€]", "Blech-Richtpreis", "zahl", 25.0, 0, 100000),
    Einstellung("blech_aufschlag", "Aufschlag des Lieferanten (Gewinn)", "Blech-Richtpreis", "anteil", 0.15, 0, 5),
    Einstellung("standard_maschine", "Standard-Maschine", "Angebot", "auswahl", "T03",
                auswahl="maschine"),
    Einstellung("standard_stange", "Standard-Stangenlänge [mm]", "Angebot", "ganz", 6000, 500, 20000),
    Einstellung("letzte_angebotsnummer", "Letzte Angebotsnummer", "Angebot", "text", "A-2026-0001"),
    Einstellung("flach_als", "STEP-Import: ebene flache Teile vorgeben als", "STEP-Import", "auswahl", FLACH_ALS[0],
                auswahl="flachals"),
    Einstellung("flachstahl_bis", "STEP-Import: Flachstahl bis Breite [mm] (breitere flache Teile sind Bleche)",
                "STEP-Import", "zahl", 150.0, 1, 10000),
    # Ordner, in dem der Dateidialog „STEP importieren …“ startet; leer = zuletzt benutzter STEP-Ordner
    Einstellung("step_ordner", "STEP-Import: Standardordner (leer = zuletzt benutzter Ordner)", "STEP-Import",
                "ordner",
                ""),
    # Vorbelegung im STEP-Prüfdialog für Rohre und Profile (nicht für Bleche); leer = keine Vorgabe
    Einstellung("step_werkstoff", "STEP-Import: Standard-Werkstoff für Rohre und Profile (leer = keiner)",
                "STEP-Import", "auswahl", "S235-10219", auswahl="werkstoff"),
    # Vorgabe im Bohrbild (Dialog Bohrungen prüfen) für Fließlochbohrungen aus dem STEP-Import
    Einstellung("fliessloch_laser", "STEP-Import: Flowdrill-Bohrung am Laser", "STEP-Import", "auswahl",
                FLIESSLOCH_LASER[0], auswahl="fliesslochlaser"),
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
    Einstellung("ablageordner", "Ablageordner (leer = Ordner 'Angebote' neben dem Programm)", "Ablage", "text", ""),
    Einstellung("sicherung_ordner2", "Zweiter Sicherungsordner (leer = keiner, z. B. Netzlaufwerk oder USB-Stick)",
                "Ablage", "text", ""),
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
    # Der Reiter Einstellungen (mit den Stammdaten außer Kunden) öffnet nur mit diesem Passwort; leer = ohne
    # Hilfetexte über den Tabellen: aufklappbar (erster Satz, 'ⓘ mehr') oder nur als Tooltip (siehe hilfe.py)
    Einstellung("ansicht_hilfe", "Hilfetexte über Tabellen und Seiten", "Ansicht", "auswahl", "aufklappbar",
                auswahl="hilfeart"),
    Einstellung("passwort", "Passwort für die Einstellungen (leer = ohne Passwort)", "Zugang", "passwort", "av"),
    # Benutzer dieses Arbeitsplatzes (teilen.py, Patrick 22.10.2026): das Kürzel steht vorn in der Angebotsnummer
    # (PB-2026-0001); über den gemeinsamen Ordner sehen alle die Angebote der anderen und teilen die Stammdaten.
    # Gelten nur für diesen Arbeitsplatz (teilen.LOKAL), werden also nicht mit den anderen abgeglichen.
    Einstellung("benutzer_name", "Name", "Benutzer", "text", ""),
    Einstellung("benutzer_kuerzel", "Kürzel (vorn in der Angebotsnummer, z. B. PB)", "Benutzer", "text", ""),
    Einstellung("benutzer_email", "E-Mail (im Angebots-PDF)", "Benutzer", "text", ""),
    Einstellung("benutzer_telefon", "Telefon (im Angebots-PDF)", "Benutzer", "text", ""),
    Einstellung("teilen_ordner", "Gemeinsamer Ordner der Mitarbeiter (leer = nicht teilen)", "Benutzer", "ordner", ""),
)
EINSTELLUNG = {e.name: e for e in EINSTELLUNGEN}


# ------------------------------------------------------------------ Werte lesen und anzeigen
def zahl_aus_text(text):
    """'1.234,5' / '1234,5' / '1234.5' -> 1234.5; '6.000' (Punkt als Tausendertrennung) -> 6000"""
    t = str(text).strip().replace(" ", "").replace(" ", "")
    if "," in t or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "").replace(",", ".")
    return float(t)


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
                         "zusatzart": list(ZUSATZARTEN), "profil": sorted(self.profile), "janein": ["ja", "nein"], "zeugnis": ["2.2", "3.1", "3.2"], "hilfeart": ["aufklappbar", "nur Tooltip"],
                         "maschine": sorted(self.maschinen), "kategorie": list(self.kategorien),
                         "gas": list(GASE), "stundensatz": [SATZ_MASCHINE] + sorted(self.stundensaetze),
                         "zeitart": list(ZEITARTEN), "ruestbezug": list(RUESTBEZUG),
                         "zeitbezug": list(ZEITBEZUG), "zeiteinheit": list(ZEITEINHEITEN),
                         "zusatzsatz": sorted(self.stundensaetze), "zuschlagart": list(ZUSCHLAG_ARTEN),
                         "zuschlagbasis": list(ZUSCHLAG_BASIS), "zukaufmethode": list(ZUKAUF_METHODEN),
                         "zukaufquelle": list(ZUKAUF_QUELLEN), "zukaufstatus": list(ZUKAUF_STATUS),
                         "zukauftyp": list(ZUKAUF_TYPEN), "positionsart": ["Rohrlaserteil", "Zukaufteil"],
                         "lieferzeitart": list(LIEFERZEIT_ARTEN), "fliesslochlaser": list(FLIESSLOCH_LASER),
                         "flachals": list(FLACH_ALS), "materialherkunft": list(MATERIAL_HERKUNFT),
                         "nahtquelle": list(naht.QUELLEN), "querschnittlage": list(naht.LAGEN),
                         "nahtstange": list(naht.NAHT_STANGE),
                         "zukaufkategorie": list(self.zukauf_kategorien),
                         "zukauflieferant": list(self.zukauf_lieferanten)}.get(quelle, []))]


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
    return k


def kategorie_raten(z):
    """Kategorie eines Werkstoffs ohne Angabe (ältere Datendateien): Dichte unter 4 = Aluminium,
    Werkstoff-Nr. 1.4… = Edelstahl, sonst Stahl."""
    texte = " ".join(str(z.get(n) or "") for n in ("werkstoff_id", "werkstoff", "werkstoff_nr"))
    if isinstance(z.get("dichte"), (int, float)) and z["dichte"] < 4:
        return "Aluminium"
    if re.search(r"(?<![\d.])1\.4\d{3}", texte) or re.search(r"(?i)\bX\d+Cr", texte):
        return "Edelstahl"
    return "Stahl"


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
    if t is MASCHINEN and z.get("stundensatz") is None:
        return "WARNUNG: Stundensatz fehlt"
    if t is MASCHINEN and k.schneiddaten:
        da = {s.get("kategorie") or (k.werkstoffe.get(s.get("werkstoff_id")) or {}).get("kategorie")
              for s in k.schneiddaten if s.get("maschinen_id") == z.get("maschinen_id")}
        fehlt = [kat for kat in k.kategorien if kat not in da]
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
    }


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


def beispiel_blechlaser():
    return [(kat, gas, d, v, round(v * 0.5, -1), ein, "Richtwert Faser 6 kW")
            for (kat, gas), stufen in BLECHLASER_RICHTWERTE.items() for d, v, ein in stufen]


def beispiel_werkstoffe():
    """Werkstoffe mit Kategorie (Beispiel-Tonnenpreise, bitte durch eigene ersetzen)."""
    st, es, al = "Stahl", "Edelstahl", "Aluminium"
    rohr_s, praez = "EN 10219 kaltgefertigt, geschweißt", "EN 10305-3 Präzisionsstahlrohr, geschweißt, maßgewalzt"
    rohr_e = "EN 10217-7 / ASTM A554"
    return [
        ("S235-10219", st, "S235JRH", "1.0039", rohr_s, 7.85, "Beispiel", 1000, "S235 EN10219"),
        ("S355-10219", st, "S355J2H", "1.0576", rohr_s, 7.85, "Beispiel", 1050, "S355 EN10219"),
        ("E235-10305", st, "E235", "1.0308", praez, 7.85, "Beispiel", 1150, "E235 EN10305-3"),
        ("E355-10305", st, "E355", "1.0580", praez, 7.85, "Beispiel", 1250, "E355 EN10305-3"),
        ("1.4301", es, "X5CrNi18-10", "1.4301", rohr_e, 7.90, "Beispiel", 4200, "1.4301 EN10217-7"),
        ("1.4307", es, "X2CrNi18-9", "1.4307", rohr_e, 7.90, "Beispiel", 4300, "1.4307 EN10217-7"),
        ("1.4404", es, "X2CrNiMo17-12-2", "1.4404", rohr_e, 8.00, "Beispiel", 5600, "1.4404 EN10217-7"),
        ("1.4571", es, "X6CrNiMoTi17-12-2", "1.4571", rohr_e, 8.00, "Beispiel", 5900, "1.4571 EN10217-7"),
        ("1.4509", es, "X2CrTiNb18", "1.4509", "EN 10296-2 (ferritisch)", 7.70, "Beispiel", 3600, "1.4509 EN10296-2"),
        ("AW6060-T66", al, "EN AW-6060 T66", "3.3206", "EN 755-2", 2.70, "Beispiel", 4500, "EN AW-6060 T66"),
        ("AW6063-T66", al, "EN AW-6063 T66", None, "EN 755-2", 2.70, "Beispiel", 4600, "EN AW-6063 T66"),
        ("AW6082-T6", al, "EN AW-6082 T6", "3.2315", "EN 755-2", 2.70, "Beispiel", 4800, "EN AW-6082 T6")]


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
RICHTWERTE = {"T03": _CO2, "T11": _FASER_4KW, "LT7": _FASER_3KW}
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


def beispiel_schneiddaten():
    """Schneiddaten je Kategorie (Werkstoff-ID leer) für T03 (CO₂) sowie T11 und LT7 (Faser) aus den Richtwerten.
    Vorschub mittel 60 %, klein 30 % von groß: kleine Konturen begrenzt am Rohr die Dynamik, nicht die Leistung."""
    out = []
    for m, laser in LASER.items():
        text = f"{RICHTWERT_TEXT[laser]} {zahl_als_text(LEISTUNG[m])} kW, Rohr"
        for (kat, gas), stufen in RICHTWERTE[m].items():
            for wand, v, ein in stufen:
                out.append((m, None, kat, gas, wand, v, round(v * 0.6, -1), round(v * 0.3, -1), ein, GRAVUR[laser],
                            text))
    return out


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
        + bohr_zusatzarbeiten() + schweiss_zusatzarbeiten()


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

