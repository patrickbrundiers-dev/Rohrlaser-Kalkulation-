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
    # Entfernung von Hand (km); leer = aus den PLZ (entfernung.py, Patrick 11.11.2026)
    Feld("fracht_km", "Entfernung (Fracht) [km]", "zahl", 0, 5000, stellen=0),
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
    # Kürzel des Mitarbeiters, der das Angebot angelegt hat (Einstellung benutzer_kuerzel); leer = ältere Angebote
    Feld("bearbeiter", "Bearbeiter"),
    # Mindestauftragswert (Betrag aus den Einstellungen) für dieses Angebot anwenden: leer = ja, "nein" = aus
    # (Patrick 23.10.2026); der Betrag selbst bleibt nur in den Einstellungen änderbar
    Feld("mindestpreis_anwenden", "Mindestauftragswert anwenden", "auswahl", auswahl="janein"),
    # Musterteile (Patrick 28.10.2026): leer = Musterkosten auf die Serienpositionen umlegen, MUSTER_ZEILE = als
    # eigene Zeile „Musterkosten einmalig“ (ohne Serienposition immer so)
    Feld("muster_darstellung", "Musterkosten im Angebot", "auswahl", auswahl="musterdarstellung"),
    # Abruf-/Rahmenangebot (Schema 70, Patrick 30.10.2026; abruf.py): Haken, Jahresmenge und Abrufmenge von–bis,
    # Laufzeit, Material je Abruf (leer, Materialklausel) oder bevorratet mit Lagerzins
    Feld("abruf", "Abruf-/Rahmenangebot", "auswahl", auswahl="janein"),
    Feld("abruf_jahr_von", "Jahresmenge von [Stk.]", "ganz", 1, 100000000),
    Feld("abruf_jahr_bis", "Jahresmenge bis [Stk.]", "ganz", 1, 100000000),
    Feld("abruf_von", "Abrufmenge von [Stk.]", "ganz", 1, 10000000),
    Feld("abruf_bis", "Abrufmenge bis [Stk.]", "ganz", 1, 10000000),
    Feld("abruf_laufzeit", "Laufzeit / Preisbindung [Monate]", "ganz", 1, 120),
    Feld("abruf_material", "Material", "auswahl", auswahl="abrufmaterial"),
    Feld("abruf_lagerzins", "Lagerzins [% p. a.]", "zahl", 0, 100, stellen=1),
    # Vorschläge vom 02.11.2026: Verpackung je Angebot abschaltbar (G2, leer = ja), Neuteile für den Neuteil-Zuschlag
    # (J6, JSON-Liste der Positions-IDs, vom Angebotsfenster aus den Wiederholteilen gesetzt), Werkszeugnis (F5)
    Feld("verpackung", "Verpackung berechnen", "auswahl", auswahl="janein"),
    Feld("neuteile", "Neuteile (für den Neuteil-Zuschlag)"),
    # Prüfung Kalkulationsbasis 3 (02.11.2026): Wiederholteile mit vorhandenem Programm (JSON-Liste der Positions-IDs,
    # vom Angebotsfenster aus den Wiederholteilen gesetzt: gleich und aus einem beauftragten Angebot)
    Feld("wiederholt", "Wiederholteile mit Programm (für die Programmierzeit)"),
    Feld("zeugnis_31", "Werkszeugnis 3.1 verlangt", "auswahl", auswahl="janein"),
    # OFFER-007 (Roadmap Phase 1, 13.11.2026): Rüsten und Programmierung im Angebot als eigene Zeile „einmalig“ statt
    # in den Stückpreisen (ausgabe.einmal_abziehen); leer = in den Stückpreisen wie bisher
    Feld("einmal_zeile", "Rüsten und Programmierung als eigene Zeile", "auswahl", auswahl="janein"),
)
ZAHLUNG = ("skonto", "skonto_tage", "zahlungsziel")
# Kalkulationswerte je Angebot: beim Anlegen aus den Einstellungen übernommen, danach je Angebot änderbar;
# leer (ältere Angebote) = Wert der Einstellungen. Prozentwerte stehen hier in %, in den Einstellungen als Anteil.
KALKULATION = (
    # Zuschlag Material und Zuschlag Fertigung gelten immer aus den Einstellungen (Vorgabe 0, Patrick 21.10.2026);
    # die Spalten älterer Dateien werden nicht mehr gelesen.
    Feld("zuschlag_fremdleistung", "Zuschlag Fremdleistung [%]", "zahl", 0, 500, stellen=1),
    # Aufschlag auf den Einstand aller Bleche bzw. aller übrigen Zukaufteile dieses Angebots; ersetzt die Regeln von
    # Artikel, Kategorie und Standard (Patrick 25.10.2026, Vorgabe 10 %); ein Positionsaufschlag geht vor. Leer
    # (ältere Angebote) = Regeln wie bisher, nicht der Wert der Einstellungen (zukauf.mit_angebotsaufschlag)
    Feld("aufschlag_blech", "Aufschlag Bleche [%]", "zahl", 0, 1000, stellen=1),
    Feld("aufschlag_zukauf", "Aufschlag Zukaufteile [%]", "zahl", 0, 1000, stellen=1),
    Feld("gewinn", "Gewinn [%]", "zahl", 0, 500, stellen=1),
    # MAT-011 (Roadmap Phase 1, Schema 85): eigener Gewinn auf das Material je Angebot (aus Einstellungen bzw.
    # Kundenvorgaben); in % wie die Einstellung gewinn_material, leer = wie der Gewinn
    Feld("gewinn_material", "Gewinn auf Material [%]", "zahl", 0, 500, stellen=1),
    Feld("ruesten_abmessung", "Rüstzeit je Abmessung [min]", "zahl", 0, 1440, stellen=1),
    # Rüsten wahlweise als fester Betrag statt Minuten × Stundensatz (Patrick 26.10.2026); leer = Minuten
    Feld("ruesten_abmessung_eur", "Rüsten je Abmessung [€]", "zahl", 0, 100000, stellen=2),
    Feld("ruesten_angebot_eur", "Rüsten je Angebot [€]", "zahl", 0, 100000, stellen=2),
    Feld("pauschale_abmessung", "Pauschale je Abmessung [€]", "zahl", 0, 100000, stellen=2),
    # Programmierung: (Grundzeit je Position + Zeit je Innenkontur) × Stundensatz 'Programmierung'. Der Betrag je
    # Position (bis 0.8.21) zählt nur noch in vorher verschickten Angeboten (festgeschriebene Preisbasis)
    Feld("programmierung_zeit", "Programmierzeit je Position [min]", "zahl", 0, 1440, stellen=1),
    Feld("programmierung_kontur", "Programmierzeit je Innenkontur [min]", "zahl", 0, 1440, stellen=2),
    Feld("programmierung_teil", "Programmierkosten je Position (alt) [€]", "zahl", 0, 100000, stellen=2),
    Feld("angebotsaufschlag", "Angebotsaufschlag [€]", "zahl", 0, 100000, stellen=2),
    # Mindestpreis (Mindestauftragswert) gilt immer aus den Einstellungen, für alle Angebote (Patrick 21.10.2026);
    # die Spalte angebote.mindestpreis älterer Dateien wird nicht mehr gelesen.
    # Kundenmaterial: Handling (Prüfen, Einlagern, Transport) je m der beigestellten Stangen; 0 = keins
    Feld("handling_beistellung", "Handling Kundenmaterial [€/m]", "zahl", 0, 1000, stellen=3),
    # Eilzuschlag (Vorschlag K2, Patrick 02.11.2026): zusätzlich zum Zuschlag Fertigung auf Laser, Rüsten, Arbeitsgänge
    # und eigene Zusatzarbeiten, wenn der Wunschtermin vor dem frühesten freien Termin liegt; leer/0 = keiner
    Feld("eilzuschlag", "Eilzuschlag Fertigung [%]", "zahl", 0, 500, stellen=1),
    # Kundenkonditionen (Vorschlag G7): aus den Kundenvorgaben, je Angebot änderbar; leer/0 = keine
    Feld("rabatt", "Rabatt [%]", "zahl", 0, 50, stellen=1),
    Feld("frachtfrei_ab", "Frachtfrei ab Warenwert [€ netto]", "zahl", 0, 10000000, stellen=2),
    Feld("mindestwert", "Mindestauftragswert des Kunden [€ netto]", "zahl", 0, 10000000, stellen=2),
)
KALK_PROZENT = ("zuschlag_fremdleistung", "aufschlag_blech", "aufschlag_zukauf", "gewinn", "eilzuschlag", "rabatt")
# Kalkulationswerte, bei denen leer nicht „wie Einstellungen“ heißt, sondern „wie vor dem Feld“ (ältere Angebote)
KALK_OHNE_VORGABE = ("aufschlag_blech", "aufschlag_zukauf", "ruesten_abmessung_eur", "ruesten_angebot_eur", "eilzuschlag",
                     "rabatt", "frachtfrei_ab", "mindestwert")
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
# Schweißbaugruppe (Patrick 23.10.2026, Plan Schweißbaugruppen 1a): trägt nur die eigenen Leistungen der Baugruppe
# (Nahtgruppen, Arbeitsgänge, Vorrichtungen; baugruppe.py), ihre Einzelteile sind die Positionen, die ihr über
# bg_knoten zugeordnet sind; Preis je Baugruppe = Satz aus Teilen und Baugruppen-Position
BAUGRUPPE = "Schweißbaugruppe"
# Herkunft des Materials je Position: leer = Eigenmaterial (wie bisher); Kundenmaterial: keine Materialkosten,
# eigene Stangengruppe, Bearbeitung wie sonst

POSITIONSARTEN = (ROHRLASERTEIL, ZUKAUFTEIL, BAUGRUPPE)


def ist_zukaufteil(p):
    """True für eine Position der Art Zukaufteil (ohne Profil, wird nicht optimiert und nicht gelasert)."""
    return (p or {}).get("art") == ZUKAUFTEIL


def ist_baugruppe(p):
    """True für eine Position der Art Schweißbaugruppe (Leistungen der Baugruppe, ohne Profil und Laser)."""
    return (p or {}).get("art") == BAUGRUPPE


def kein_laserteil(p):
    """True für Positionen ohne Rohrlaser-Bearbeitung (Zukaufteil, Schweißbaugruppe): nicht optimiert, nicht gelasert."""
    return (p or {}).get("art") in (ZUKAUFTEIL, BAUGRUPPE)


def ist_muster(p):
    """True für ein Musterteil (Spalte Muster = ja): eigener Fertigungslauf, Preis 0, Kosten auf die Serie."""
    return (p or {}).get("muster") == "ja"


def aktiv(p):
    """Position, die kalkuliert wird: Rohrlaserteil mit Profil, Zukaufteil oder Schweißbaugruppe."""
    return kein_laserteil(p) or (p or {}).get("profil_id") not in (None, "")


# ------------------------------------------------------------------ Lieferzeit
LIEFERZEIT_HILFE = {ARBEITSTAGE: "Anzahl Arbeitstage, z. B. 10", WOCHEN: "Anzahl Wochen, z. B. 3",
                    KALENDERWOCHE: "KW/Jahr, z. B. 46/2026 (ohne Jahr: Jahr des Angebots)",
                    LIEFERDATUM: "Datum, z. B. 15.11.2026", NUR_TEXT: "nur Freitext"}


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


_LZ_REST = r"(?:\s*(?:nach\s+Auftragseingang|n\.\s*AE|ab\s+Auftrag(?:seingang)?))?\s*(?:[,;–\-]\s*)?(?P<rest>.*)$"
_LZ_MUSTER = (
    (ARBEITSTAGE, r"(?i)^(?:ca\.?\s*)?(?P<w>\d{1,3})\s*(?:AT|Arbeitstag(?:e|en)?|Werktag(?:e|en)?|Tag(?:e|en)?)\b"),
    (WOCHEN, r"(?i)^(?:ca\.?\s*)?(?P<w>\d{1,3}(?:\s*[-–]\s*\d{1,3})?)\s*(?:W|Wo\.?|Wochen?)(?![\wäöü])"),
    (KALENDERWOCHE, r"(?i)^(?:in\s+|bis\s+)?KW\s*(?P<w>\d{1,2}(?:\s*[/.\-]\s*\d{2,4})?)\b"),
    (LIEFERDATUM, r"(?i)^(?:bis\s+(?:zum\s+)?|am\s+)?(?P<w>\d{1,2}\.\s*\d{1,2}\.(?:\s*\d{2,4})?)"),
)


def lieferzeit_lesen(text, datum=None):
    """Lieferzeit aus einem Feld (Verbesserungsplan 06.11.2026, E3): „3 Wochen“, „10 AT“, „KW 48“, „15.11.“,
    „15.11.2026“ oder Freitext wie „nach Absprache“. Ergebnis (Art, Wert, Zusatz) wie gespeichert
    (lieferzeit_art, lieferzeit_wert, lieferzeit_zusatz); was hinter der Angabe steht, wird Zusatz. Leer = (None, None,
    None). „15.11.“ ohne Jahr: Jahr des Angebots, liegt der Tag davor, das Jahr danach. Spannen wie „2-3 Wochen“
    bleiben Freitext. ValueError bei einer ungültigen Kalenderwoche oder einem ungültigen Datum."""
    import datetime
    t = " ".join(str(text or "").split()).strip()
    if t.lower().startswith("lieferzeit"):
        t = re.sub(r"(?i)^lieferzeit\s*:?\s*", "", t)
    t = t.rstrip(".") if not re.search(r"\d\.$", t) else t
    if not t:
        return None, None, None
    for art, muster in _LZ_MUSTER:
        m = re.match(muster + _LZ_REST, t)
        if not m:
            continue
        w, rest = m.group("w"), (m.group("rest") or "").strip() or None
        if art == WOCHEN and re.search(r"[-–]", w):
            break                                   # Spanne: als Freitext übernehmen
        if art == LIEFERDATUM:
            tag, monat, jahr = (re.split(r"\.\s*", w.strip()) + [""])[:3]
            if not jahr:
                try:
                    bezug = datetime.date.fromisoformat(datum or "")
                except ValueError:
                    bezug = datetime.date.today()
                jahr = bezug.year
                try:
                    if datetime.date(jahr, int(monat), int(tag)) < bezug:
                        jahr += 1
                except ValueError:
                    pass
            w = f"{tag}.{monat}.{jahr}"
        return art, lieferzeit_wert(art, w, datum), rest
    return NUR_TEXT, None, t


def lieferzeit_eingabe(kopf):
    """Gespeicherte Lieferzeit als Text für das eine Feld (Gegenstück zu lieferzeit_lesen)."""
    import datetime
    kopf = kopf or {}
    art, w = kopf.get("lieferzeit_art"), kopf.get("lieferzeit_wert")
    zusatz = (kopf.get("lieferzeit_zusatz") or "").strip()
    teil = ""
    if w and art == ARBEITSTAGE:
        teil = f"{w} Arbeitstag{'' if w == '1' else 'e'}"
    elif w and art == WOCHEN:
        teil = f"{w} Woche{'' if w == '1' else 'n'}"
    elif w and art == KALENDERWOCHE:
        teil = f"KW {w}"
    elif w and art == LIEFERDATUM:
        try:
            teil = datetime.date.fromisoformat(w).strftime("%d.%m.%Y")
        except ValueError:
            teil = w
    return ", ".join(x for x in (teil, zusatz) if x)


def lieferzeit_text(kopf, lieferart=None):
    """Lieferzeit des Angebots als Satz für Angebot, Druck und E-Mail, z. B. 'Lieferzeit: ca. 10 Arbeitstage nach
    Auftragseingang.' bzw. '… KW 46/2026.' / '… bis 15.11.2026.' / '… nach Absprache.'; mit Freitext dahinter.
    Leer, wenn das Angebot keine Lieferzeit hat (ältere Angebote: es gilt der Text der Bedingungen).
    lieferart = 'frei Haus' bzw. 'ab Werk' (frachtzeit.art, Patrick 10.11.2026 F4a): steht in Klammern hinter der
    Angabe, z. B. 'Lieferzeit: KW 48/2026 (frei Haus).'."""
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
    if teil and lieferart:
        teil += f" ({lieferart})"
    text = "Lieferzeit: " + ", ".join(x for x in (teil, zusatz) if x)
    return text if text.endswith((".", "!", "?")) else text + "."


def bedingungen_text(kopf, bedingungen):
    """Text der Einstellung 'Bedingungen' für ein Angebot: hat das Angebot eine eigene Lieferzeit, fallen Sätze
    über die Lieferzeit ('Lieferzeit nach Absprache.') weg, damit das Angebot sich nicht widerspricht."""
    t = (bedingungen or "").strip()
    if lieferzeit_text(kopf):
        t = re.sub(r"(?i)(^|(?<=[.!?]))\s*Lieferzeit[^.!?]*[.!?]?", "", t).strip()
    return t


GEWINDE_MUSTER = (r"^\s*\d+\s*[xX×*]\s*\S+(\s*(;|,(?!\d)|\n)\s*\d+\s*[xX×*]\s*\S+)*\s*[;,]?\s*$",
                  "Format Anzahl x Gewinde (ganze Zahl), mehrere mit Semikolon oder Komma, z. B. 4xM6; 2xM8")

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
     # leer = Grundzeit + Zeit je Innenkontur (rechnen.programmier_zeit), sonst von Hand je Position
     Feld("prog_zeit", "Programmierzeit [min]", "zahl", 0, 1440, stellen=1, breite=80),
     # Zusatzarbeiten als JSON-Liste [{name, menge, preis, text}] (Dialog 'Zusatzarbeiten …')
     Feld("zusatz", "Zusatzarbeiten", "zusatz", breite=220),
     # Zukaufteile als JSON-Liste [{artikel_id, menge (je Teil), aufschlag (%), stand}] (Dialog 'Zukaufteile …')
     Feld("zukauf", "Zukaufteile", "zukauf", breite=220),
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
     # Bohrbild (bohrbild.py): Gewinde-Vorschläge, Senkungen, Fließlochbohrungen mit Prüfstatus als JSON, keine Spalte
     Feld("bohrbild", "Bohrungen prüfen", breite=120),
     # Prüfstatus je STEP-Merkmal mit Rohdaten und Korrekturen (step_pruefung.py, Schema 65), keine Spalte
     Feld("step_merkmale", "STEP-Merkmale", breite=120),
     # Arbeitsgangvorschläge (arbeitsgaenge.py, Schema 65): abgelehnte Vorschläge als JSON, keine Spalte
     Feld("arbeitsgaenge", "Arbeitsgangvorschläge", breite=120),
     # Anbauteile aus dem STEP-Import (anbau.py): aufgeschweißte Bolzen, Laschen … mit Bearbeitung, Gravur und
     # Prüfstatus als JSON; die Spalte zeigt die Kurzfassung, Doppelklick = Anbauteile prüfen
     Feld("anbauteile", "Anbauteile", "anbau", breite=170),
     # Schweißnaht (naht.py): Vorgabe leer = keine Vorgabe; Winkel im Bezug 'Breitseite oben', Blick von Ende A
     Feld("naht_vorgabe", "Schweißnaht", "naht", breite=190),
     Feld("naht_winkel", "Nahtwinkel [°]", "zahl", 0, 359.9, stellen=1, breite=70),
     Feld("naht_quelle", "Quelle Naht", "auswahl", auswahl="nahtquelle", breite=80),
     Feld("querschnitt_lage", "Querschnittslage", "auswahl", auswahl="querschnittlage", breite=110),
     # ebene schräge Enden (Gehrung) für das Ineinanderlegen: JSON {winkel, richtung}, richtung = Umfangswinkel, in
     # dem das Teil an diesem Ende am längsten ist (naht.py-Zählung); STEP-Import oder Schneidweg-Rechner
     Feld("a_ende", "Gehrung Anfang", breite=90),
     Feld("b_ende", "Gehrung Ende", breite=90),
     # Schweißbaugruppen (baugruppe.py, Schema 46): auf der Position der Art Schweißbaugruppe die Baugruppe als JSON
     # (Stammdaten, Unterbaugruppen, Arbeitsgänge, Nahtgruppen); auf Einzelteilen die Zuordnung 'Baugruppen-ID/Knoten'
     # und die Menge je direkt übergeordneter (Unter-)Baugruppe. Leer = keine Baugruppe (ältere Positionen)
     Feld("baugruppe", "Schweißbaugruppe", breite=150),
     Feld("bg_knoten", "Baugruppe (Zuordnung)", breite=120),
     Feld("je_knoten", "Stück je Baugruppe", "ganz", 1, 100000, breite=70),
     # Vorkalkulation (vorkalk.py, Schema 53): Positionierhilfe des Einzelteils beim Schweißen; leer = Vorschlag des
     # Programms (Steckverbindung, Vorrichtung, Gravur, frei), sonst bestätigt bzw. von Hand
     Feld("bg_hilfe", "Positionierhilfe", "auswahl", auswahl="positionierhilfe", breite=110),
     # Positionsgravur (Schema 56): Artikelnummer gravieren mit dieser Schrifthöhe [mm]; leer = noch nicht gewählt
     # (Einstellung gravur_artikel gibt das Häkchen im Baugruppen-Editor vor), 0 = nicht gravieren
     Feld("bg_gravur", "Gravur Artikelnr. h [mm]", "zahl", 0, 200, stellen=1, breite=90),
     # ASM-002 (Roadmap Phase 1, Schema 85): Hauptbauteil der Schweißbaugruppe (höchstens eins je Baugruppe), steht
     # in Stückliste und Angebot zuerst; leer = keins
     Feld("bg_haupt", "Hauptbauteil", "auswahl", auswahl="janein", breite=70),
     # Halbschalen aus dem Rundrohr (STEP-Import, offen gezeichnete Rohre): so viele Teile aus einem Rohrumfang,
     # Rohrstücke = Stückzahl ÷ je Umfang aufgerundet (rechnen.rohrstuecke); leer = 1 Teil je Rohrstück
     Feld("je_umfang", "Teile je Rohrumfang", "ganz", 1, 100, breite=70),
     # Musterteil (Schema 66, Patrick 28.10.2026): „ja“ = voll gerechnet, aber ohne eigenen Preis im Angebot; die
     # Kosten mit Gewinn gehen auf die Serienpositionen (bzw. als Musterkosten einmalig in eine eigene Zeile)
     Feld("muster", "Muster", "auswahl", auswahl="janein", breite=60),
     # Geometrie (Schema 83, geometrie.py): „nur kalkuliert“ = aus PDF-Zeichnung/Schnellpreis, nicht ins CAM;
     # „geprüft“ = von Hand bestätigt; leer = normal (STEP, DXF, von Hand eingegeben)
     Feld("geometrie", "Geometrie", "auswahl", auswahl="geometrie", breite=95),
     # Teil wenden (Schema 83, Plan PROfirst H4): „nein“ = Sichtseite, Folie oder Schliff, nie gedreht bzw. gewendet
     # (auch nicht als gedrehtes Duplikat); leer = Programm darf wenden, wo es die Regeln erlauben
     Feld("wenden", "Wenden erlaubt", "auswahl", auswahl="janein", breite=70),
     # Laserzeit genauer (Plan ArTube-Unterlagen B3, D4, G7; zeit_zusatz.py): Messzyklen für genaue Konturen und
     # Schnittqualität (Vorschub-Faktor); leer = keine Messung bzw. Standard (Kleines Rohr nach Maschine)
     Feld("messungen", "Messungen je Teil", "ganz", 0, 100, breite=65),
     Feld("messart", "Messzyklus", "auswahl", auswahl="messart", breite=80),
     Feld("schnittqualitaet", "Schnittqualität", "auswahl", auswahl="schnittqualitaet", breite=90),
     # Plan ArTube-Unterlagen D1: Kante ohne Oxidschicht (vor Pulver, Lack, Verzinken) = nur N₂ schneiden
     Feld("oxidfrei", "Kante oxidfrei (N₂)", "auswahl", auswahl="janein", breite=80),
     # Plan ArTube-Unterlagen E1: Freitext für den Bediener (Werkstattpapiere, Etikett, CAM-Paket)
     Feld("bediener", "Hinweis für den Bediener", breite=180),
     # Gravurtext mit Platzhaltern (gravur_platzhalter.py, Plan ArTube D2); leer = Artikelnummer wie bisher
     Feld("gravur_text", "Gravurtext (Platzhalter)", breite=160),
     # Teil wenden (wenden.py, Plan ArTube G8): gewendetes Duplikat, im Schnittplan Ende B vorn
     Feld("gewendet", "Gewendet (Ende B zuerst)", "auswahl", auswahl="janein", breite=80),
     # Qualitätskosten aus dem Prüfplan (Plan X4, Schema 84, qualitaet.py): Name der Qualitätsstufe; leer = keine
     Feld("qualitaet", "Qualitätsstufe", "auswahl", auswahl="qualitaetsstufe", breite=110),
     # OFFER-021: offene Frage mit Antworten, z. B. „Werkstoff: 1.4301 oder 1.4404“ (rueckfrage_wirkung.py)
     Feld("offene_frage", "Offene Frage (Antworten)", breite=180)),
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


def kuerzel_sauber(text):
    """Kürzel eines Mitarbeiters: nur Buchstaben und Ziffern, groß geschrieben, höchstens 5 Zeichen ('pb ' -> 'PB')."""
    return re.sub(r"[^A-Z0-9ÄÖÜ]", "", str(text or "").upper())[:5]
