"""Aufbau der Stammdaten: Tabellen, Felder, Prüfregeln und berechnete Spalten.

Eine Beschreibung je Tabelle dient für alles: Datenbankschema, Anzeige im Programm und Prüfung.
"""
import datetime
import math
import re
from dataclasses import dataclass, field

PREISBASIS = ("€/kg", "€/Stange", "€/m")
PROFILFORMEN = ("Rundrohr", "Quadratrohr", "Rechteckrohr", "Sonderprofil")
KATEGORIEN = ("Stahl", "Edelstahl", "Aluminium")
# Schneidgas: N₂ gilt, solange es eine N₂-Zeile mit passender Wandstärke gibt, darüber O₂
GASE = ("N₂", "O₂")
ROH = "roh"     # Oberfläche ohne Aufpreis; leer in der Position heißt ebenfalls roh
# Abrechnung einer Zusatzarbeit: Betrag je kg, m² Außenfläche, m Länge oder Stück; 's/Stück' = Zeit in
# Sekunden je Stück, die zur Schneidzeit addiert wird (z. B. Gravur, die nicht im STEP-Modell ist)
ZUSATZARTEN = ("€/kg", "€/m²", "€/m", "€/Stück", "s/Stück")
ZUSATZ_EINHEIT = {"€/kg": "kg", "€/m²": "m²", "€/m": "m", "€/Stück": "Stk", "s/Stück": "Stk"}


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
    return None


def huellkreis(p):
    """Durchmesser des Kreises um den Profilquerschnitt: Rundrohr Ø, Quadrat-/Rechteckrohr Diagonale.
    Sonderprofile ohne Angabe (None)."""
    form, a, b = p.get("form"), p.get("a"), p.get("b")
    if a is None:
        return None
    if form == "Rundrohr":
        return a
    if form == "Quadratrohr":
        return a * math.sqrt(2)
    if form == "Rechteckrohr" and b is not None:
        return math.hypot(a, b)
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
     Feld("ansprechpartner", "Ansprechpartner", breite=130),
     Feld("telefon", "Telefon", breite=110),
     Feld("email", "E-Mail", breite=170),
     Feld("skonto", "Skonto [%]", "zahl", 0, 20, stellen=1, breite=70),
     Feld("skonto_tage", "Skontofrist [Tage]", "ganz", 0, 365, breite=75),
     Feld("zahlungsziel", "Zahlungsziel netto [Tage]", "ganz", 0, 365, breite=85),
     Feld("bemerkung", "Bemerkung", breite=200)),
    ("kundennr",),
    "Kunden für den Angebotskopf: Kundennummer wählen, dann kommen Name, Anschrift und Zahlungsbedingungen ins "
    "Angebot. Skonto, Skontofrist und Zahlungsziel leer = Vorgabe aus den Einstellungen.")

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
     Feld("bemerkung", "Bemerkung", breite=220)),
    ("profil_id",),
    "Abmessung A = Ø (Rundrohr) bzw. Breite, Abmessung B = Höhe (nur Rechteckrohr). Endbeschnitt und "
    "Greiferrest nur eintragen, wenn sie vom Maschinenwert abweichen. Fläche manuell = Herstellerwert "
    "(Eckradien, Sonderprofile).",
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
     Feld("angebotstext", "Text im Angebot", breite=160)),
    ("werkstoff_id",),
    "Die Werkstoff-ID ist der Schlüssel für Preise, Schneiddaten und Angebot. Die Kategorie (Stahl, Edelstahl, "
    "Aluminium) ordnet die Auswahl im Angebot und liefert Schneiddaten und Oberflächen, wenn der Werkstoff keine "
    "eigenen hat. Der Tonnenpreis ergibt automatisch den Preis je kg, je m und je Stange; Abweichungen unter "
    "'Preise' eintragen.")

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
     Feld("abstand", "Abstand getrennte Schnitte [mm]", "zahl", 0, 100, stellen=1),
     Feld("ruestzeit", "Rüstzeit je Angebot [min]", "zahl", 0, 1440, stellen=0),
     Feld("stangenwechsel", "Stangenwechsel je Stange [s]", "zahl", 0, 3600, stellen=0),
     Feld("bemerkung", "Bemerkung", breite=160),
     Feld("max_huellkreis", "Max. Hüllkreis-Ø [mm]", "zahl", 1, 2000, stellen=1),
     Feld("max_kg_m", "Max. Metergewicht [kg/m]", "zahl", 0.1, 1000, stellen=1)),
    ("maschinen_id",),
    "Endbeschnitt = Anschnitt am Stangenanfang, Greiferrest = nicht nutzbares Ende im Greifer, "
    "Schnittverlust = Materialverlust je Trennschnitt. Konturgrenzen: größtes Hüllmaß der Innenkontur. "
    "Max. Hüllkreis-Ø und max. Metergewicht: größere oder schwerere Profile bekommen im Angebot FEHLER "
    "und werden nicht eingeplant (leer = keine Grenze).")

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
     Feld("bemerkung", "Bemerkung", breite=160)),
    ("maschinen_id", "werkstoff_id", "kategorie", "gas", "wand_bis"),
    "Je Maschine + Werkstoff (oder Kategorie) + Schneidgas gestaffelt nach Wandstärke: es gilt die Zeile mit der "
    "kleinsten 'Wandstärke bis', die mindestens der Profilwandstärke entspricht. Zeilen mit Werkstoff-ID gehen "
    "vor; hat der Werkstoff keine passende Zeile, gelten die Zeilen seiner Kategorie (Werkstoff-ID leer). "
    "Schneidgas: N₂, solange es eine N₂-Zeile für die Wandstärke gibt, darüber O₂ (so endet N₂ ab einer "
    "gewissen Wandstärke). Leere Vorschübe mittel/klein/Gravur nehmen den nächstgrößeren.")

GEWINDE = Tabelle(
    "gewinde", "Gewinde",
    (Feld("gewinde", "Gewinde", pflicht=True, breite=80),
     Feld("kernloch", "Kernloch Ø [mm]", "zahl", 0.5, 100, stellen=1, pflicht=True),
     Feld("zeit", "Zeit je Gewinde [s]", "zahl", 0, 3600, stellen=0),
     Feld("bemerkung", "Bemerkung", breite=260),
     Feld("preis", "Preis je Gewinde [€]", "zahl", 0, 1000, stellen=2, breite=90)),
    ("gewinde",),
    "ISO-Regelgewinde, Kernloch nach DIN 336. Der STEP-Import vergleicht Bohrungsdurchmesser mit dieser "
    "Tabelle (±0,05 mm). In der Kalkulation zählt der feste Preis je Gewinde; ist er leer, die Zeit je "
    "Gewinde mit dem Maschinenstundensatz.")

ZUSATZARBEITEN = Tabelle(
    "zusatzarbeiten", "Zusatzarbeiten",
    (Feld("name", "Zusatzarbeit", pflicht=True, breite=160),
     Feld("art", "Abrechnung", "auswahl", auswahl="zusatzart", pflicht=True, breite=80),
     Feld("preis", "Preis [€] bzw. Zeit [s] je Einheit", "zahl", 0, 100000, stellen=2, pflicht=True, breite=95),
     Feld("mindest", "Mindestbetrag je Angebot [€]", "zahl", 0, 100000, stellen=2, breite=95),
     Feld("fremd", "Fremdleistung", "auswahl", auswahl="janein", breite=80),
     Feld("angebotstext", "Text im Angebot", breite=170),
     Feld("bemerkung", "Bemerkung", breite=260)),
    ("name",),
    "Auswahl für 'Zusatzarbeiten …' im Angebot. Abrechnung: €/kg (Teilegewicht), €/m² (Außenfläche = "
    "Umfang × Länge), €/m (Teilelänge), €/Stück, s/Stück (Zeit je Stück, wird zur Schneidzeit addiert, z. B. "
    "Gravur, die nicht im Teil ist). Mindestbetrag: liegt die Summe im Angebot darunter, wird auf den "
    "Mindestbetrag angehoben. Fremdleistung = ja: Zuschlag Fremdleistung, sonst Zuschlag Fertigung.")

TABELLEN = (KUNDEN, PROFILE, WERKSTOFFE, OBERFLAECHEN, PREISE, MASCHINEN, SCHNEIDDATEN, GEWINDE, ZUSATZARBEITEN)
TABELLE = {t.name: t for t in TABELLEN}

# Schlüssel, auf die andere Tabellen verweisen: beim Umbenennen werden die Verweise mitgeändert
VERWEISE = {
    ("kunden", "kundennr"): (("angebote", "kundennr"),),
    ("profile", "profil_id"): (("preise", "profil_id"),),
    ("werkstoffe", "werkstoff_id"): (("preise", "werkstoff_id"), ("schneiddaten", "werkstoff_id")),
    ("maschinen", "maschinen_id"): (("schneiddaten", "maschinen_id"),),
}


# ------------------------------------------------------------------ Einstellungen
@dataclass(frozen=True)
class Einstellung:
    name: str
    titel: str
    gruppe: str
    art: str                # text | zahl | ganz | anteil | mehrzeilig | auswahl | passwort
    vorgabe: object
    von: float = None
    bis: float = None
    auswahl: str = None


EINSTELLUNGEN = (
    Einstellung("zuschlag_material", "Zuschlag Material", "Kalkulation", "anteil", 0.10, 0, 5),
    Einstellung("zuschlag_fertigung", "Zuschlag Fertigung", "Kalkulation", "anteil", 0.15, 0, 5),
    Einstellung("zuschlag_fremdleistung", "Zuschlag Fremdleistung", "Kalkulation", "anteil", 0.10, 0, 5),
    Einstellung("gewinn", "Gewinn", "Kalkulation", "anteil", 0.10, 0, 5),
    Einstellung("ruesten_abmessung", "Rüstzeit je Abmessung [min]", "Kalkulation", "zahl", 15.0, 0, 1440),
    Einstellung("pauschale_abmessung", "Pauschale je Abmessung [€]", "Kalkulation", "zahl", 22.50, 0, 100000),
    Einstellung("programmierung_teil", "Programmierkosten je Teil (Position) [€]", "Kalkulation", "zahl", 8.50, 0,
                100000),
    Einstellung("angebotsaufschlag", "Angebotsaufschlag je Angebot [€]", "Kalkulation", "zahl", 50.0, 0, 100000),
    Einstellung("standard_maschine", "Standard-Maschine", "Angebot", "auswahl", "RL-1",
                auswahl="maschine"),
    Einstellung("standard_stange", "Standard-Stangenlänge [mm]", "Angebot", "ganz", 6000, 500, 20000),
    Einstellung("letzte_angebotsnummer", "Letzte Angebotsnummer", "Angebot", "text", "A-2026-0001"),
    # Zahlungsbedingungen neuer Angebote, wenn der Kunde keine eigenen hat. Skonto wird in den Preis eingerechnet.
    Einstellung("skonto", "Skonto [%]", "Angebot", "zahl", 2.0, 0, 20),
    Einstellung("skonto_tage", "Skontofrist [Tage]", "Angebot", "ganz", 10, 0, 365),
    Einstellung("zahlungsziel", "Zahlungsziel netto [Tage]", "Angebot", "ganz", 30, 0, 365),
    Einstellung("briefkopf_1", "Briefkopf Zeile 1 (Firma)", "Angebots-PDF", "text", "Firmenname"),
    Einstellung("briefkopf_2", "Briefkopf Zeile 2", "Angebots-PDF", "text", "Straße Nr."),
    Einstellung("briefkopf_3", "Briefkopf Zeile 3", "Angebots-PDF", "text", "PLZ Ort"),
    Einstellung("briefkopf_4", "Briefkopf Zeile 4", "Angebots-PDF", "text", "Telefon / E-Mail"),
    Einstellung("mwst", "MwSt.-Satz", "Angebots-PDF", "anteil", 0.19, 0, 1),
    Einstellung("gueltigkeit", "Gültigkeit [Tage]", "Angebots-PDF", "ganz", 30, 0, 3650),
    Einstellung("bedingungen", "Bedingungen", "Angebots-PDF", "mehrzeilig",
                "Lieferzeit nach Absprache. Preise in Euro zuzüglich Mehrwertsteuer."),
    Einstellung("ablageordner", "Ablageordner (leer = Ordner 'Angebote' neben dem Programm)", "Ablage", "text", ""),
    Einstellung("sicherung_ordner2", "Zweiter Sicherungsordner (leer = keiner, z. B. Netzlaufwerk oder USB-Stick)",
                "Ablage", "text", ""),
    Einstellung("profilformen", "Profilformen (eine je Zeile)", "Auswahllisten", "mehrzeilig",
                "\n".join(PROFILFORMEN)),
    Einstellung("kategorien", "Werkstoff-Kategorien (eine je Zeile)", "Auswahllisten", "mehrzeilig",
                "\n".join(KATEGORIEN)),
    # Der Reiter Einstellungen (mit den Stammdaten außer Kunden) öffnet nur mit diesem Passwort; leer = ohne
    Einstellung("passwort", "Passwort für die Einstellungen (leer = ohne Passwort)", "Zugang", "passwort", "av"),
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
    profilformen: tuple = PROFILFORMEN
    kategorien: tuple = KATEGORIEN

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
        return [(None, {"profilform": list(self.profilformen), "preisbasis": list(PREISBASIS),
                         "zusatzart": list(ZUSATZARTEN), "profil": sorted(self.profile), "janein": ["ja", "nein"],
                         "maschine": sorted(self.maschinen), "kategorie": list(self.kategorien),
                         "gas": list(GASE)}[quelle])]


def kontext_aus(daten, profilformen=PROFILFORMEN, kategorien=KATEGORIEN):
    """Kontext aus Stammdatenzeilen {Tabelle: [Zeile]}."""
    k = Kontext()
    k.profile = {z["profil_id"]: z for z in daten.get("profile", []) if z.get("profil_id")}
    k.werkstoffe = {z["werkstoff_id"]: z for z in daten.get("werkstoffe", []) if z.get("werkstoff_id")}
    k.maschinen = {z["maschinen_id"]: z for z in daten.get("maschinen", []) if z.get("maschinen_id")}
    k.oberflaechen = {z["oberflaeche"]: z for z in daten.get("oberflaechen", []) if z.get("oberflaeche")}
    k.profilformen = tuple(profilformen)
    k.kategorien = tuple(kategorien)
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
    if t is PROFILE:
        a, s = z.get("a"), z.get("wand")
        if a is not None and s is not None and not (0 < s and 2 * s < a):
            return "FEHLER: Wandstärke muss kleiner als die halbe Abmessung A sein"
        if z.get("form") == "Rechteckrohr" and z.get("b") is None and z.get("flaeche_manuell") is None:
            return "FEHLER: Abmessung B fehlt"
        if flaeche_wirksam(z) is None:
            return "FEHLER: Querschnitt fehlt (Fläche manuell eintragen)"
    if t is PREISE and z.get("basis") == "€/Stange" and not z.get("lieferlaenge"):
        return "FEHLER: Stangenlänge fehlt"
    if t is SCHNEIDDATEN:
        if _leer(z.get("werkstoff_id")) == _leer(z.get("kategorie")):
            return "FEHLER: Werkstoff-ID oder Kategorie eintragen (eins von beiden)"
        if _leer(z.get("gas")):
            return "WARNUNG: Schneidgas fehlt"
    if t is WERKSTOFFE and _leer(z.get("kategorie")):
        return "WARNUNG: Kategorie fehlt"
    if t is WERKSTOFFE and z.get("tonnenpreis") is None:
        return "WARNUNG: kein Tonnenpreis (Preis nur über 'Preise')"
    if t is MASCHINEN and z.get("stundensatz") is None:
        return "WARNUNG: Stundensatz fehlt"
    return "OK"


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
            ("K-1001", "Beispiel Metallbau GmbH", "Musterstraße 1", "12345 Musterstadt", "Herr Muster", "01234 56789",
             "info@beispiel-metallbau.de", 2, 10, 30, "Beispiel"),
            ("K-1002", "Muster Anlagenbau KG", "Industrieweg 5", "54321 Beispielstadt", "Frau Beispiel", "05432 1234",
             "einkauf@muster-anlagenbau.de", 3, 14, 45, "Beispiel")]),
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
            ("RL-1", "Rohrlaser 1 (Beispiel)", 20, 80, 0.3, 6500, 120.00, 10, 50, 2, 15, 30, "Beispielwerte"),
            ("RL-2", "Rohrlaser 2 (Beispiel)", 15, 120, 0.3, 8500, 140.00, 10, 50, 2, 20, 40, "Beispielwerte")]),
        "schneiddaten": zeilen(SCHNEIDDATEN, beispiel_schneiddaten()),
        "gewinde": zeilen(GEWINDE, [(g, k, None, "Zeit je Gewinde für Kalkulation in Schritt 4" if i == 0 else None, p)
                                    for i, (g, k, p) in enumerate(gewinde)]),
        "zusatzarbeiten": beispiel_zusatzarbeiten(),
    }


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


# Beispiel-Schneiddaten je Kategorie und Gas: [(Wandstärke bis, Vorschub groß)]; N₂ endet bei Stahl über 4 mm,
# bei Edelstahl über 8 mm, bei Aluminium über 6 mm, darüber gilt O₂
BEISPIEL_VORSCHUB = {
    ("Stahl", "N₂"): [(1, 9000), (1.5, 8000), (2, 7000), (3, 5000), (4, 3500)],
    ("Stahl", "O₂"): [(1, 5500), (1.5, 5000), (2, 4500), (3, 3600), (4, 3000), (5, 2500), (6, 2100), (8, 1500),
                      (10, 1100)],
    ("Edelstahl", "N₂"): [(1, 8000), (1.5, 7000), (2, 6000), (3, 4000), (4, 3000), (5, 2200), (6, 1700), (8, 1000)],
    ("Edelstahl", "O₂"): [(10, 900)],
    ("Aluminium", "N₂"): [(1, 10000), (1.5, 9000), (2, 8000), (3, 5500), (4, 4000), (5, 3000), (6, 2300)],
    ("Aluminium", "O₂"): [(8, 1400), (10, 1000)],
}


def beispiel_schneiddaten():
    """Schneiddaten je Kategorie (Werkstoff-ID leer) für RL-1 und RL-2 (RL-2 mit 20 % mehr Leistung).
    Einstechzeit mit O₂ länger als mit N₂."""
    out = []
    for m, faktor in (("RL-1", 1.0), ("RL-2", 1.2)):
        for (kat, gas), stufen in BEISPIEL_VORSCHUB.items():
            for wand, v in stufen:
                v = round(v * faktor, -1)
                ein = round(0.1 + wand * (0.18 if gas == "O₂" else 0.12), 1)
                out.append((m, None, kat, gas, wand, v, round(v * 0.7, -1), round(v * 0.4, -1), ein,
                            12000 if gas == "N₂" else 10000, "Beispiel"))
    return out


def beispiel_zusatzarbeiten():
    """Vorbelegung der Zusatzarbeiten (Beispielpreise, bitte durch eigene ersetzen)."""
    werte = [("Feuerverzinken", "€/kg", 0.65, 120.0, "ja", "feuerverzinkt", "Beispielpreis; Mindestbetrag der Verzinkerei"),
             ("Galvanisch verzinken", "€/kg", 1.20, 80.0, "ja", "galvanisch verzinkt", "Beispielpreis"),
             ("Pulverbeschichten", "€/m²", 18.00, 90.0, "ja", "pulverbeschichtet",
              "Beispielpreis; Farbe je Position als Text eintragen, z. B. RAL 7016"),
             ("Entgraten", "€/Stück", 0.50, None, "nein", "entgratet", "Beispielpreis"),
             ("Gravur extra", "s/Stück", 20.0, None, "nein", "Gravur",
              "Zeit je Gravur in s, wird zur Schneidzeit addiert (Gravur, die nicht im STEP-Modell ist)")]
    return [{f.name: (w[i] if i < len(w) else None) for i, f in enumerate(ZUSATZARBEITEN.felder)} for w in werte]
