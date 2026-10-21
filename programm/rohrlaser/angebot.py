"""Aufbau eines Angebots: Kopf und Positionen."""
import re

from .stammdaten import (ARBEITSTAGE, EIGENMATERIAL, KUNDENMATERIAL, MATERIAL_HERKUNFT, KALENDERWOCHE, LIEFERDATUM, LIEFERZEIT_ARTEN, NUR_TEXT, WOCHEN,  # noqa: F401
                         Feld, Tabelle)

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
    Feld("fracht_auto", "Fracht automatisch berechnen", "auswahl", auswahl="janein"),
    Feld("fracht_plz", "Ziel-PLZ (Fracht)"),
    Feld("fracht_land", "Zielland (Fracht)"),
    # Zahlungsbedingungen: Vorgabe aus dem Kunden bzw. den Einstellungen; Skonto wird in den Preis eingerechnet
    Feld("skonto", "Skonto [%]", "zahl", 0, 20, stellen=1),
    Feld("skonto_tage", "Skontofrist [Tage]", "ganz", 0, 365),
    Feld("zahlungsziel", "Zahlungsziel netto [Tage]", "ganz", 0, 365),
    # Anfrage des Kunden (Zeichen, Anfragenummer), im Angebots-PDF und in der Materialanfrage
    Feld("kundenreferenz", "Ihre Anfrage / Zeichen"),
    # Lieferzeit je Angebot (lieferzeit_text): Art + Wert + Zusatz; leer (ältere Angebote) = wie bisher nur der Text
    # der Einstellung 'Bedingungen'. Ändert keine Preise.
    Feld("lieferzeit_art", "Lieferzeit als", "auswahl", auswahl="lieferzeitart"),
    Feld("lieferzeit_wert", "Lieferzeit"),
    Feld("lieferzeit_zusatz", "Lieferbedingungen (Freitext)"),
    # Vorgabe der Spalte Material für neue Positionen (leer = Eigenmaterial); jede Position bleibt änderbar
    Feld("material_vorgabe", "Material neuer Positionen", "auswahl", auswahl="materialherkunft"),
)
ZAHLUNG = ("skonto", "skonto_tage", "zahlungsziel")
# Kalkulationswerte je Angebot: beim Anlegen aus den Einstellungen übernommen, danach je Angebot änderbar;
# leer (ältere Angebote) = Wert der Einstellungen. Prozentwerte stehen hier in %, in den Einstellungen als Anteil.
KALKULATION = (
    # Zuschlag Material und Zuschlag Fertigung gelten immer aus den Einstellungen (Vorgabe 0, Patrick 21.10.2026);
    # die Spalten älterer Dateien werden nicht mehr gelesen.
    Feld("zuschlag_fremdleistung", "Zuschlag Fremdleistung [%]", "zahl", 0, 500, stellen=1),
    Feld("gewinn", "Gewinn [%]", "zahl", 0, 500, stellen=1),
    Feld("ruesten_abmessung", "Rüstzeit je Abmessung [min]", "zahl", 0, 1440, stellen=1),
    Feld("pauschale_abmessung", "Pauschale je Abmessung [€]", "zahl", 0, 100000, stellen=2),
    Feld("programmierung_teil", "Programmierkosten je Teil [€]", "zahl", 0, 100000, stellen=2),
    Feld("angebotsaufschlag", "Angebotsaufschlag [€]", "zahl", 0, 100000, stellen=2),
    # Mindestpreis (Mindestauftragswert) gilt immer aus den Einstellungen, für alle Angebote (Patrick 21.10.2026);
    # die Spalte angebote.mindestpreis älterer Dateien wird nicht mehr gelesen.
    # Kundenmaterial: Handling (Prüfen, Einlagern, Transport) je kg der beigestellten Stangen; 0 = keins
    Feld("handling_beistellung", "Handling Kundenmaterial [€/kg]", "zahl", 0, 1000, stellen=3),
)
KALK_PROZENT = ("zuschlag_fremdleistung", "gewinn")
KOPF = KOPF + KALKULATION


def kalk_abweichungen(kopf, vorgaben):
    """Kalkulationswerte des Angebots, die von den Einstellungen abweichen: [(Feld, Wert im Angebot, Standard)].
    vorgaben = Datenbank.kalkulation_vorgaben() (Prozent in %). Leere Werte (ältere Angebote) rechnen mit den
    Einstellungen und weichen nicht ab."""
    out = []
    for f in KALKULATION:
        w, std = (kopf or {}).get(f.name), vorgaben.get(f.name)
        if isinstance(w, (int, float)) and isinstance(std, (int, float)) and abs(w - std) > 1e-9:
            out.append((f, w, std))
    return out

# Positionsart: leer = Rohrlaserteil (Profil, Optimierung, Laser); Zukaufteil = eingekauftes Teil ohne Fertigung
# (z. B. Blech aus dem STEP-Import), Preis nur aus den Zukaufteilen der Position (Einstand + Aufschlag) und Fracht
ROHRLASERTEIL, ZUKAUFTEIL = "Rohrlaserteil", "Zukaufteil"
# Herkunft des Materials je Position: leer = Eigenmaterial (wie bisher); Kundenmaterial: keine Materialkosten,
# eigene Stangengruppe, Bearbeitung wie sonst

POSITIONSARTEN = (ROHRLASERTEIL, ZUKAUFTEIL)


def ist_zukaufteil(p):
    """True für eine Position der Art Zukaufteil (ohne Profil, wird nicht optimiert und nicht gelasert)."""
    return (p or {}).get("art") == ZUKAUFTEIL


def aktiv(p):
    """Position, die kalkuliert wird: Rohrlaserteil mit Profil oder Zukaufteil."""
    return ist_zukaufteil(p) or (p or {}).get("profil_id") not in (None, "")


# ------------------------------------------------------------------ Lieferzeit
LIEFERZEIT_HILFE = {ARBEITSTAGE: "Anzahl Arbeitstage, z. B. 10", WOCHEN: "Anzahl Wochen, z. B. 3",
                    KALENDERWOCHE: "KW/Jahr, z. B. 46/2026 (ohne Jahr: Jahr des Angebots)",
                    LIEFERDATUM: "Datum, z. B. 15.11.2026", NUR_TEXT: "kein Wert, nur der Freitext"}


def lieferzeit_wert(art, text, datum=None):
    """Eingabe der Lieferzeit prüfen und als gespeicherten Text liefern: Arbeitstage/Wochen = ganze Zahl,
    Kalenderwoche = 'KW/JJJJ' (Jahr fehlt: Jahr von datum bzw. heute), Lieferdatum = ISO-Datum, nur Text = None.
    Leer = None. ValueError mit Meldung bei ungültiger Eingabe (Freitext wird nie als Datum gelesen)."""
    import datetime
    t = "" if text is None else str(text).strip()
    if art in (None, "", NUR_TEXT) or t == "":
        return None
    if art in (ARBEITSTAGE, WOCHEN):
        if not re.fullmatch(r"\d{1,3}", t) or int(t) < 1:
            raise ValueError(f"Lieferzeit: {art} als ganze Zahl ab 1 eingeben (z. B. 10).")
        return str(int(t))
    if art == KALENDERWOCHE:
        m = re.fullmatch(r"(?i)(?:KW\s*)?(\d{1,2})(?:\s*[/.\-]\s*(\d{4}))?", t)
        if not m:
            raise ValueError("Lieferzeit: Kalenderwoche als KW/Jahr eingeben, z. B. 46/2026.")
        kw = int(m.group(1))
        try:
            jahr = int(m.group(2)) if m.group(2) else datetime.date.fromisoformat(datum or "").year
        except ValueError:
            jahr = datetime.date.today().year
        letzte = datetime.date(jahr, 12, 28).isocalendar()[1]
        if not 1 <= kw <= letzte:
            raise ValueError(f"Lieferzeit: Kalenderwoche {kw} gibt es {jahr} nicht (1 bis {letzte}).")
        return f"{kw}/{jahr}"
    if art == LIEFERDATUM:
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(t, fmt).date().isoformat()
            except ValueError:
                pass
        raise ValueError(f"Lieferzeit: '{t}' ist kein gültiges Datum (TT.MM.JJJJ).")
    raise ValueError(f"Lieferzeit: unbekannte Art '{art}'.")


def lieferzeit_text(kopf):
    """Lieferzeit des Angebots als Satz für Angebot, Druck und E-Mail, z. B. 'Lieferzeit: ca. 10 Arbeitstage nach
    Auftragseingang.' bzw. '… KW 46/2026.' / '… bis 15.11.2026.' / '… nach Absprache.'; mit Freitext dahinter.
    Leer, wenn das Angebot keine Lieferzeit hat (ältere Angebote: es gilt der Text der Bedingungen)."""
    import datetime
    kopf = kopf or {}
    art, w = kopf.get("lieferzeit_art"), kopf.get("lieferzeit_wert")
    zusatz = (kopf.get("lieferzeit_zusatz") or "").strip()
    teil = ""
    if w and art == ARBEITSTAGE:
        teil = f"ca. {w} Arbeitstag{'' if w == '1' else 'e'} nach Auftragseingang"
    elif w and art == WOCHEN:
        teil = f"ca. {w} Woche{'' if w == '1' else 'n'} nach Auftragseingang"
    elif w and art == KALENDERWOCHE:
        teil = f"KW {w}"
    elif w and art == LIEFERDATUM:
        try:
            teil = "bis " + datetime.date.fromisoformat(w).strftime("%d.%m.%Y")
        except ValueError:
            teil = ""
    if not teil and not zusatz:
        return ""
    text = "Lieferzeit: " + ", ".join(x for x in (teil, zusatz) if x)
    return text if text.endswith((".", "!", "?")) else text + "."


def bedingungen_text(kopf, bedingungen):
    """Text der Einstellung 'Bedingungen' für ein Angebot: hat das Angebot eine eigene Lieferzeit, fallen Sätze
    über die Lieferzeit ('Lieferzeit nach Absprache.') weg, damit das Angebot sich nicht widerspricht."""
    t = (bedingungen or "").strip()
    if lieferzeit_text(kopf):
        t = re.sub(r"(?i)(^|(?<=[.!?]))\s*Lieferzeit[^.!?]*[.!?]?", "", t).strip()
    return t


GEWINDE_MUSTER = (r"(?i)\dx\s*M", "Format Anzahl x Gewinde, mehrere mit Semikolon, z. B. 4xM6; 2xM8")

POSITIONEN = Tabelle(
    "positionen", "Positionen",
    (Feld("pos", "Pos.", "ganz", 1, 99999, breite=50),
     Feld("art", "Positionsart", "auswahl", auswahl="positionsart", breite=90),
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
     Feld("preis_m", "Materialpreis [€/m]", "zahl", 0, 100000, stellen=2, breite=85),
     Feld("material_herkunft", "Material", "auswahl", auswahl="materialherkunft", breite=110),
     Feld("gewinde", "Gewinde geprüft", muster=GEWINDE_MUSTER, breite=110),
     Feld("zeit_manuell", "Schneidzeit je Teil [s]", "zahl", 0, 100000, stellen=1, breite=85),
     # Zusatzarbeiten als JSON-Liste [{name, menge, preis, text}] (Dialog 'Zusatzarbeiten …')
     Feld("zusatz", "Zusatzarbeiten", "zusatz", breite=220),
     # Zukaufteile als JSON-Liste [{artikel_id, menge (je Teil), aufschlag (%), stand}] (Dialog 'Zukaufteile …')
     Feld("zukauf", "Zukaufteile", "zukauf", breite=220),
     # Zeichnungen/Dokumente als JSON-Liste der Dateinamen im Ordner des Angebots (dokumente.py, Doppelklick)
     Feld("dokumente", "Zeichnungen", "dokumente", breite=130),
     # Zukaufteil-Position: Gewicht je Teil für die Fracht nach Gewicht (STEP-Import: Volumen × Dichte, sonst leer)
     Feld("gewicht_teil", "Gewicht je Teil [kg]", "zahl", 0, 100000, stellen=3, breite=75),
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
     Feld("gross_mm", "Kontur groß [mm]", "zahl", 0, 1000000, stellen=1, breite=70),
     # je Innenkontur Hüllmaß x Schnittweg (STEP-Import) und die Grenzen, mit denen eingeteilt wurde
     Feld("konturen", "Konturen Hüllmaß x Schnittweg [mm]", breite=200),
     Feld("kontur_grenzen", "Konturgrenzen klein/mittel [mm]", breite=80),
     # Eingaben des Schneidweg-Rechners als JSON (Enden, Konturen; siehe schneidweg.py), keine eigene Spalte
     Feld("technik", "Schneidweg-Rechner", breite=120),
     # Schweißnaht (naht.py): Vorgabe leer = keine Vorgabe; Winkel im Bezug 'Breitseite oben', Blick von Ende A
     Feld("naht_vorgabe", "Schweißnaht", "naht", breite=190),
     Feld("naht_winkel", "Nahtwinkel [°]", "zahl", 0, 359.9, stellen=1, breite=70),
     Feld("naht_quelle", "Quelle Naht", "auswahl", auswahl="nahtquelle", breite=80),
     Feld("querschnitt_lage", "Querschnittslage", "auswahl", auswahl="querschnittlage", breite=110),
     # ebene schräge Enden (Gehrung) für das Ineinanderlegen: JSON {winkel, richtung}, richtung = Umfangswinkel, in
     # dem das Teil an diesem Ende am längsten ist (naht.py-Zählung); STEP-Import oder Schneidweg-Rechner
     Feld("a_ende", "Gehrung Anfang", breite=90),
     Feld("b_ende", "Gehrung Ende", breite=90)),
    (),
    "Positionen eintragen oder per STEP-Import übernehmen. Die Spalte Status zeigt "
    "FEHLER, WARNUNG, HINWEIS oder OK.")
STEP_FELDER = {"a_gerade", "a_schnitt", "b_gerade", "b_schnitt", "innen", "gravur", "bohrungen", "gewinde_vorschlag",
               "klein_n", "klein_mm", "mittel_n", "mittel_mm", "gross_n", "gross_mm", "konturen", "kontur_grenzen"}
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
