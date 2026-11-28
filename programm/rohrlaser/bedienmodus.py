"""Bedienmodus je Arbeitsplatz und Benutzer: Einfacher Modus oder Experten-Pro-Modus (Patrick 25.11.2026,
Master-Auftrag „Vereinfachten Bedienmodus implementieren“). Nur Daten und Rechnungen, ohne Qt: die Oberfläche steht
in einfach_seite.py (geführte Kalkulation) und bedienmodus_seite.py (Einstellungsseite).

Grundsätze
- Beide Modi sind nur zwei Oberflächen auf DENSELBEN Kern: dieselbe Angebotsseite (angebot_fenster.AngebotSeite),
  dieselbe Datenbank, dieselbe Rechnung (rechnen.kalkulation), dieselbe Marge (marge.werte) und Ampel
  (preisleiter.bewertung). Hier steht keine eigene Preisrechnung: alle Beträge sind Summen der Kostenarten, die das
  Programm ohnehin rechnet (rechnen.KOSTENARTEN), nur anders gruppiert.
- Gemerkt wird je Benutzer (Kürzel des angemeldeten Benutzers, sonst dieses Arbeitsplatzes) in der eigenen
  Datendatei dieses Platzes, wie „Meine Werkzeugleiste“ (werkzeugleiste.benutzer). Der Name beginnt mit „leiste_“
  und steht nicht in stammdaten.EINSTELLUNGEN: er geht nie über den gemeinsamen Ordner, andere Plätze bleiben
  unberührt, das persönliche Profil nimmt ihn mit.
- Vorgabe ist der Experten-Pro-Modus: wer nichts wählt, arbeitet weiter wie bisher (rückwärtskompatibel).
"""

EXPERTE, EINFACH = "experte", "einfach"
MODI = ((EINFACH, "Einfacher Modus",
         "Geführte Kalkulation in fünf Schritten: Anfrage und Kunde, Bauteile, Material und Fertigung, Kalkulation, "
         "Angebot. Ruhige Oberfläche mit den wichtigen Angaben; alles Weitere rechnet das Programm im Hintergrund. "
         "Für Mitarbeiter ohne tiefe CAD- oder Kalkulationskenntnisse."),
        (EXPERTE, "Experten-Pro-Modus",
         "Die vollständige technische Arbeitsumgebung wie bisher: alle Reiter, Menüs, Editoren, Maschinen- und "
         "Kalkulationsparameter, Verschachtelung, Datenbank- und Systemeinstellungen."))
TITEL = {m: t for m, t, _ in MODI}
SPEICHER = "leiste_bedienmodus"         # {Kürzel: "einfach" | "experte"}; "" = dieser Arbeitsplatz ohne Anmeldung
HILFE_AN = "leiste_einfach_hilfe"       # {Kürzel: True/False}: Hilfebereich im einfachen Modus zeigen
WILLKOMMEN = "leiste_einfach_willkommen"    # {Kürzel: True}: Begrüßung im Schritt 1 ausgeblendet
SCHNELL_TASTE = "Ctrl+Shift+M"          # Umschalten zwischen den Modi von überall


# ------------------------------------------------------------------ Modus je Benutzer
def benutzer(db):
    from . import werkzeugleiste
    return werkzeugleiste.benutzer(db)


def _alle(db, name):
    try:
        v = db.einstellung(name)
    except Exception:           # noqa: BLE001 – ohne lesbare Einstellungen gilt die Vorgabe
        return {}
    return dict(v) if isinstance(v, dict) else {}


def modus(db, k=None):
    """Bedienmodus des Benutzers k (None = angemeldeter Benutzer bzw. dieser Arbeitsplatz). Ohne eigene Wahl gilt die
    Wahl des Arbeitsplatzes (Kürzel ""), sonst der Experten-Pro-Modus."""
    alle = _alle(db, SPEICHER)
    k = benutzer(db) if k is None else k
    for schl in (k, ""):
        if alle.get(schl) in (EINFACH, EXPERTE):
            return alle[schl]
    return EXPERTE


def einfach(db, k=None):
    return modus(db, k) == EINFACH


def setzen(db, neu, k=None):
    """Bedienmodus des Benutzers k merken (None = angemeldeter Benutzer bzw. Arbeitsplatz). Ohne Anmeldung gilt die
    Wahl für diesen Arbeitsplatz. Ergebnis: True = gespeichert (im Lesemodus der Datei nicht)."""
    if neu not in (EINFACH, EXPERTE):
        raise ValueError(f"Bedienmodus {neu!r} unbekannt")
    if getattr(db, "nur_lesen", False):
        return False
    alle = _alle(db, SPEICHER)
    alle[benutzer(db) if k is None else k] = neu
    db.einstellung_setzen(SPEICHER, alle)
    return True


def _je_benutzer(db, name, vorgabe):
    alle = _alle(db, name)
    return alle.get(benutzer(db), vorgabe)


def _je_benutzer_setzen(db, name, wert):
    if getattr(db, "nur_lesen", False):
        return False
    alle = _alle(db, name)
    alle[benutzer(db)] = wert
    db.einstellung_setzen(name, alle)
    return True


# Ebene der Einstellungen (Patrick 26.11.2026): Grundeinstellungen / Erweitert / Expertenbereich je Benutzer bzw.
# Arbeitsplatz, wie der Bedienmodus (leiste_* wird nie abgeglichen). Vorgabe: Grundeinstellungen.
EINSTELLUNGEN_EBENE = "leiste_einstellungen_ebene"


def einstellungen_ebene(db):
    from . import einstellungen_ordnung as o
    e = _je_benutzer(db, EINSTELLUNGEN_EBENE, None)
    if e not in o.EBENEN:
        e = _alle(db, EINSTELLUNGEN_EBENE).get("", o.GRUND)
    return e if e in o.EBENEN else o.GRUND


def einstellungen_ebene_setzen(db, ebene):
    from . import einstellungen_ordnung as o
    if ebene not in o.EBENEN:
        raise ValueError(f"Ebene {ebene!r} unbekannt")
    return _je_benutzer_setzen(db, EINSTELLUNGEN_EBENE, ebene)


def hilfe_an(db):
    """Erklärung zum Schritt eingeblendet? Vorgabe aus (Einfacher Modus 2.0: Hilfe auf Abruf über „?“)."""
    return bool(_je_benutzer(db, HILFE_AN, False))


def hilfe_setzen(db, an):
    return _je_benutzer_setzen(db, HILFE_AN, bool(an))


def willkommen_an(db):
    return not _je_benutzer(db, WILLKOMMEN, False)


def willkommen_aus(db):
    return _je_benutzer_setzen(db, WILLKOMMEN, True)


# ------------------------------------------------------------------ Schritte und Hilfe
# Einfacher Modus 2.0 (Patrick 27.11.2026): Übersicht (Start) und fünf Schritte in der Reihenfolge der Arbeit.
# BEARBEITUNG und ERGEBNIS bleiben als Namen der früheren Schritte (Bearbeitung steckt jetzt in „Material und
# Fertigung“, Ergebnis heißt „Kalkulation“).
START, KUNDE, BAUTEILE, MATERIAL, KALKULATION, ANGEBOT = range(6)
BEARBEITUNG, ERGEBNIS = MATERIAL, KALKULATION
SCHRITTE = (
    ("start", "Übersicht", "Neue Kalkulation anlegen oder eine bestehende öffnen.",
     "Hier beginnt jede Kalkulation: <i>Neue Kalkulation</i> legt ein leeres Angebot an und führt zum Kunden, "
     "<i>STEP importieren …</i> und <i>Andere CAD-Datei …</i> lesen gleich die Bauteile ein, <i>Aus "
     "Bauteilbibliothek …</i> holt ein gespeichertes Bauteil. Dateien lassen sich auch einfach ins Fenster ziehen. "
     "Darunter stehen die zuletzt bearbeiteten Kalkulationen mit Suche. Jede Kalkulation ist dasselbe Angebot, das "
     "auch der Pro-Modus zeigt."),
    ("kunde", "Anfrage und Kunde", "Kunden wählen oder anlegen, Projekt und Ansprechpartner eintragen.",
     "Kunden im Suchfeld eintippen (Name, Kundennummer oder Ort) und aus der Liste wählen. Name, Konditionen, "
     "Ansprechpartner und Lieferadresse kommen aus dem Kundenstamm. Einen neuen Kunden legen Sie mit <i>Neuer Kunde "
     "…</i> direkt hier an; die Kundennummer tragen Sie von Hand ein. Angebotsnummer, Datum und Bearbeiter vergibt "
     "das Programm."),
    ("bauteile", "Bauteile", "Bauteile importieren, Stückzahlen eintragen, Erkennung prüfen.",
     "Das Programm hat die Geometrie gelesen: Querschnitt, Abmessung, Wandstärke, Länge, Schnittkonturen sowie Norm- "
     "und Zukaufteile. Tragen Sie die Stückzahl ein und sehen Sie sich das gewählte Bauteil in 3D an. Rote oder "
     "gelbe Hinweise sagen, was fehlt, und bieten die Lösung mit einem Klick an."),
    ("material", "Material und Fertigung", "Werkstoff, Materialpreis, Maschine und Zusatzarbeiten.",
     "Je Abmessung stehen Werkstoff, Wandstärke, Preis je Meter, Preisstand und Verfügbarkeit. Das Programm schlägt "
     "das Material aus der erkannten Geometrie vor; ändern Sie den Werkstoff nur, wenn der Kunde etwas anderes "
     "möchte. Maschine, Schnittplan, Rüsten und Zeiten rechnet das Programm selbst. Eingreifen müssen Sie nur bei "
     "Zusatzarbeiten (Gewinde, Senken, Entgraten …) und, falls nötig, bei den Frachtkosten unter <i>Weitere "
     "Kosten</i>."),
    ("kalkulation", "Kalkulation", "Verkaufspreis, Stückpreise, Kosten und Marge.",
     "Oben stehen Verkaufspreis netto, Durchschnitt je Stück, Marge mit Ampel und Selbstkosten. Der Balken zeigt, "
     "woraus sich der Preis zusammensetzt, darunter der Preis je Position. Unter <i>Marge einstellen</i> tragen Sie "
     "die gewünschte Marge ein; das Programm stellt den Gewinn passend ein. Die Aufteilung nach Kostenarten klappen "
     "Sie bei Bedarf auf."),
    ("angebot", "Angebot", "Zusammenfassung prüfen, PDF ansehen und erstellen.",
     "Die Zusammenfassung zeigt Kunde, Projekt, Positionen und Summe, die Prüfliste sagt, ob das Angebot bereit ist, "
     "und rechts steht die Vorschau der ersten Seite des Angebots-PDFs. <i>Angebot erstellen (PDF)</i> schreibt es "
     "endgültig. Gespeichert wird jede Änderung sofort. Für Staffeln, Rabatte oder Sonderfälle öffnet <i>Im "
     "Pro-Modus weiterbearbeiten</i> dasselbe Angebot mit allen Funktionen."),
)
# Zu welchem Schritt ein Hinweis gehört (Aktion des Lösungsknopfs)
SCHRITT_DER_AKTION = {"kunde": KUNDE, "import": BAUTEILE, "stueck": BAUTEILE, "editor": BAUTEILE, "zukauf": BAUTEILE,
                      "material": MATERIAL, "optimieren": MATERIAL, "experte": KALKULATION}


def schritt_von(h):
    """Schritt, in dem ein Hinweis (stufe, text, aktion, zeile) gelöst wird: nach der Aktion; ein Hinweis zu einem
    Bauteil ohne eigene Aktion (Pro-Modus) gehört zu den Bauteilen."""
    if h[2] == "experte" and h[3] is not None:
        return BAUTEILE
    return SCHRITT_DER_AKTION.get(h[2], KALKULATION)

# kurze Erklärungen zu Feldern und Kennzahlen (Tooltips und Hilfe)
FELD_HILFE = {
    "kunde": "Kunde aus dem Kundenstamm: Name, Kundennummer oder Ort eintippen und aus der Liste wählen. Name, "
             "Konditionen, Ansprechpartner und Lieferadresse kommen mit.",
    "projekt": "Projekt oder Bauvorhaben des Kunden; steht im Angebot und hilft beim Wiederfinden.",
    "lieferzeit": "Lieferzeit in einem Feld, so wie man sie sagt: 10 AT, 3 Wochen, KW 50 oder ein Datum.",
    "maschine": "Maschine, mit der gerechnet wird. Vorbelegt aus den Einstellungen; ändern nur, wenn eine andere "
                "Anlage fertigen soll. Danach rechnet das Programm neu.",
    "stueck": "Wie viele Teile der Kunde von diesem Bauteil braucht. Ändern speichert sofort und rechnet neu.",
    "profil": "Querschnitt des Rohrs oder Profils mit Abmessung und Wandstärke, aus der STEP-Datei erkannt.",
    "laenge": "Länge des fertigen Teils in mm (gemessen, ohne Schnittzugabe).",
    "werkstoff": "Werkstoff (Güte) des Materials. Er bestimmt Preis, Gewicht und Schneiddaten.",
    "preis_m": "Materialpreis je Meter, so wie die Kalkulation rechnet (Preisliste, Lieferlänge oder Tonnenpreis).",
    "verfuegbar": "Bestand im Lager (wenn das Lager eingeschaltet ist) oder die bekannten Lieferanten.",
    "maschinenzeit": "Reine Laufzeit der Maschine für alle Teile (Schneiden, Einstechen, Stangenwechsel, Rüsten).",
    "schnitt": "Kosten fürs Laserschneiden mit Schneidgas und Stangenwechsel: Maschinenzeit × Stundensatz.",
    "ruesten": "Maschine rüsten, je Abmessung umrüsten und programmieren: fällt einmal je Angebot an.",
    "material": "Materialeinsatz aller Stangen inkl. Verschnitt, Materialzuschlag und Lagerzins.",
    "bearbeitung": "Gewinde, weitere Arbeitsschritte, Qualitätsprüfung und Schweißen in eigenen Baugruppen.",
    "zusatz": "Zusatzarbeiten (z. B. Entgraten, Senken, Biegen) und Fremdleistungen mit Zuschlag.",
    "zukauf": "Zukauf- und Normteile zum Einstandspreis plus Aufschlag.",
    "gemein": "Fertigungszuschlag, Ausschuss, Angebotsaufschlag, Verpackung und Finanzierung.",
    "gesamt": "Alle Kosten des Angebots (Selbstkosten ohne Gewinn), wie die Kachel „Gewinn und Marge“ im Expertenmodus.",
    "verkauf": "Netto-Verkaufspreis des ganzen Angebots, so wie er im PDF steht.",
    "gewinn": "Verkaufspreis minus Gesamtkosten; die Marge ist der Gewinn im Verhältnis zum Warenwert.",
    "fracht": "Frachtkosten des ganzen Angebots: von Hand oder berechnet (Paket/Palette, Tarif), auf die Bauteile "
              "verteilt je Stück oder nach Gewicht. Fracht wird ohne Gewinn durchgereicht.",
    "marge": "Gewünschte Marge vom Warenwert: das Programm stellt den Gewinnzuschlag so ein, dass der Verkaufspreis "
             "sie genau erreicht (wie „Auf Zielmarge setzen“ in der Preisleiter); rückgängig möglich.",
}

# ------------------------------------------------------------------ Kosten gruppiert
# Jede Einzel-Kostenart (rechnen.KOSTENARTEN ohne die fetten Summen) steht in genau EINER Gruppe; die Gruppen ergeben
# zusammen den Verkaufspreis. Eine neue Kostenart ohne Gruppe landet in „Sonstiges“ und der Test meldet sie.
GRUPPEN = (
    ("material", "Materialkosten", ("material", "schrott", "zuschlag_material", "lagerzins", "handling_beistellung")),
    ("schnitt", "Schnittkosten", ("laser_schneiden", "schneidgas", "stangenwechsel_kosten", "mannlos")),
    ("ruesten", "Rüstkosten", ("ruesten_maschine", "ruesten_abmessungen", "programmierung", "pauschalen")),
    ("bearbeitung", "Bearbeitung", ("gewinde", "arbeitsschritte", "qualitaet", "baugruppe_eigen")),
    ("zusatz", "Zusatzarbeiten", ("zusatz", "zusatz_global", "baugruppe_fremd", "zuschlag_fremdleistung",
                                  "muster_spaeter")),
    ("zukauf", "Zukaufteile", ("zukauf_einstand", "zukauf_aufschlag")),
    ("gemein", "Gemeinkosten und Zuschläge", ("zuschlag_fertigung", "ausschuss", "angebotsaufschlag", "neuteil",
                                               "verpackung", "finanzierung")),
    ("gewinn", "Gewinn", ("gewinn", "regel")),
    ("preis", "Fracht, Rabatt, Skonto, Rundung", ("fracht", "frachtfrei", "rabatt", "rundung", "skonto",
                                                  "mindestpreis_anhebung")),
)
GRUPPE_TITEL = {g: t for g, t, _ in GRUPPEN}
SONSTIGES = "sonstiges"


def _n(w):
    try:
        return float(w or 0)
    except (TypeError, ValueError):
        return 0.0


def einzel_kostenarten():
    """Schlüssel aller Einzel-Kostenarten (ohne die Summenzeilen Herstell-, Selbstkosten, Verkaufspreis)."""
    from .rechnen import KOSTENARTEN
    return [n for _, n, fett in KOSTENARTEN if not fett]


def kosten_gruppen(summen):
    """{Gruppe: Betrag} aus den Summen der Kalkulation (rechnen.kalkulation); dazu SONSTIGES für Kostenarten ohne
    Gruppe. Summe aller Gruppen = Verkaufspreis (die Einzel-Kostenarten ergeben ihn in rechnen.kalkulation)."""
    s = summen or {}
    zuordnung = {n: g for g, _, namen in GRUPPEN for n in namen}
    aus = {g: 0.0 for g, _, _ in GRUPPEN}
    aus[SONSTIGES] = 0.0
    for n in einzel_kostenarten():
        aus[zuordnung.get(n, SONSTIGES)] += _n(s.get(n))
    return aus


def ergebnis(summen, einst, zeiten=None, unsicher=None):
    """Kennzahlen der Ergebnisübersicht (Schritt 4 und 5) aus derselben Rechnung wie der Expertenmodus: dict mit
    gruppen ({Gruppe: €}), material, bearbeitung (Bearbeitung + Rüsten), maschine (Schnittkosten), zusatz
    (Zusatzarbeiten + Zukaufteile), gemein, gesamt (Gesamtkosten = marge.kosten), verkauf, gewinn, marge (0 … 1 oder
    None), stufe/ampel_text/gruende (preisleiter.bewertung), maschine_min (Maschinenzeit) und teile."""
    from . import marge, preisleiter
    g = kosten_gruppen(summen)
    w = marge.werte(summen)
    b = preisleiter.bewertung(summen, einst, unsicher) if summen else None
    zs = zeiten or {}
    return dict(gruppen=g, material=g["material"], bearbeitung=g["bearbeitung"] + g["ruesten"], maschine=g["schnitt"],
                zusatz=g["zusatz"] + g["zukauf"], gemein=g["gemein"], gesamt=w["kosten"], verkauf=w["verkauf"],
                gewinn=w["gewinn"], marge=w["marge"], stufe=(b or {}).get("stufe"), ampel_text=(b or {}).get("text") or "",
                gruende=list((b or {}).get("gruende") or ()), maschine_min=_n(zs.get("maschine_min")),
                bearbeitung_min=_n(zs.get("bearbeitung_min")), teile=int(_n((summen or {}).get("teile"))))


# ------------------------------------------------------------------ Bauteile
ARTEN = {"rohr": "Rohr/Profil", "blech": "Blechteil", "zukauf": "Zukaufteil", "normteil": "Normteil",
         "baugruppe": "Baugruppe", "drehfraes": "Dreh-/Frästeil"}
FORMEN = {"RR": "Rundrohr", "QR": "Quadratrohr", "RE": "Rechteckrohr", "FL": "Flachstahl", "RS": "Rundstahl",
          "L": "Winkel", "U": "U-Profil", "T": "T-Profil", "OV": "Ovalrohr", "HEA": "HEA-Träger", "HEB": "HEB-Träger",
          "IPE": "IPE-Träger"}


def ist_normteil(p):
    """Zukaufteil, das der STEP-Import als Normteil erkannt hat (Schraube, Mutter, Scheibe …)."""
    from . import zukauf
    from .step import NORMTEIL_KATEGORIE, NORMTEIL_TYP
    for e in zukauf.eintraege(p):
        st = e.get("stand") or {}
        if st.get("artikeltyp") == NORMTEIL_TYP or st.get("kategorie") == NORMTEIL_KATEGORIE:
            return True
    return "normteil" in str(p.get("bemerkung") or "").casefold()


def art(p, position_art):
    """Art einer Position für die Anzeige: position_art = AngebotSeite.position_art(p) (rohr, blech, zukauf,
    baugruppe, drehfraes); Normteile erkennt ist_normteil."""
    if position_art == "zukauf" and ist_normteil(p):
        return "normteil"
    return position_art


def form_text(profil):
    """„Rundrohr“, „Rechteckrohr“ … aus der Profilform (Kürzel wie in den Stammdaten); unbekannt: das Kürzel."""
    f = str((profil or {}).get("form") or "").strip()
    return FORMEN.get(f.upper(), f) if f else ""


def zahl(w, stellen=2):
    from .stammdaten import zahl_als_text
    try:
        return zahl_als_text(round(float(w), stellen), stellen)
    except (TypeError, ValueError):
        return "–"


def euro(w):
    return f"{zahl(w, 2)} €" if w is not None else "–"


def minuten_text(m):
    m = _n(m)
    if m >= 60:
        return f"{int(m // 60)} h {int(round(m % 60)):02d} min"
    return f"{zahl(m, 1)} min"


def bauteil(p, position_art, k, wert=None, status=""):
    """Kurzinfo einer Position für die Bauteilliste: dict(art, art_text, name, profil, form, abmessung, wand, laenge,
    werkstoff, stueck, konturen, schneidweg, stufe, status)."""
    a = art(p, position_art)
    pr = k.profile.get(p.get("profil_id")) if p.get("profil_id") else None
    wand = (wert or {}).get("wand") if wert else None
    if wand is None and pr:
        wand = pr.get("wand")
    name = " · ".join(str(x) for x in (p.get("bezeichnung"), p.get("artikel")) if x) or f"Position {p.get('pos') or ''}"
    return dict(art=a, art_text=ARTEN.get(a, a), name=name, profil=p.get("profil_id") or "",
                form=form_text(pr), wand=wand, laenge=p.get("laenge"), werkstoff=p.get("werkstoff_id") or "",
                stueck=p.get("stueck"), konturen=p.get("einstiche"), schneidweg=p.get("schneidweg"),
                stufe=stufe(status), status=status or "")


def stufe(status):
    """FEHLER, WARNUNG, HINWEIS oder OK aus einem Statustext der Positionsliste."""
    s = str(status or "")
    for st in ("FEHLER", "WARNUNG", "HINWEIS"):
        if s.startswith(st):
            return st
    return "OK"


# Lösung je Hinweis: (Muster im Statustext, verständlicher Text, Aktion). Aktionen kennt einfach_seite: stueck,
# material, editor, zukauf, optimieren, experte, kunde
LOESUNGEN = (
    ("Stückzahl fehlt", "Die Stückzahl fehlt. Bitte in der Spalte „Stück“ eintragen.", "stueck"),
    ("Profil unbekannt", "Die Abmessung ist im Programm noch nicht angelegt. Bitte im Editor eine Abmessung wählen "
                         "oder anlegen.", "editor"),
    ("Querschnitt fehlt", "Für diese Abmessung fehlt der Querschnitt. Bitte im Editor prüfen.", "editor"),
    ("Werkstoff unbekannt", "Der Werkstoff fehlt oder ist unbekannt. Bitte im Schritt Material wählen.", "material"),
    ("Teilelänge fehlt", "Die Teilelänge fehlt. Bitte im Editor die Länge eintragen.", "editor"),
    ("kein gültiger Materialpreis", "Für dieses Material ist kein Preis hinterlegt. Bitte den Preis eintragen.",
     "material"),
    ("nicht vollständig eingeplant", "Nicht alle Teile passen auf die Stangen. Bitte neu berechnen.", "optimieren"),
    ("Teil länger als Nutzlänge", "Das Teil ist länger als die nutzbare Stangenlänge. Bitte eine längere Lieferlänge "
                                  "wählen (Schritt Material) oder das Teil teilen.", "material"),
    ("EK fehlt", "Für dieses Zukaufteil fehlt der Einkaufspreis. Bitte eintragen.", "zukauf"),
    ("Zukaufartikel fehlt", "Dem Zukaufteil ist kein Artikel zugeordnet. Bitte auswählen.", "zukauf"),
    ("Maschine fehlt", "Für das Angebot ist keine Maschine gewählt. Bitte im Expertenmodus wählen.", "experte"),
    ("Schneidweg fehlt", "Der Schneidweg fehlt (kein STEP). Bitte im Editor prüfen oder eintragen.", "editor"),
    ("Bohrungen prüfen", "Die erkannten Bohrungen sind noch ungeprüft. Bitte im Editor kurz bestätigen.", "editor"),
    ("Anbauteile prüfen", "Die Anbauteile sind noch ungeprüft. Bitte im Editor kurz bestätigen.", "editor"),
)


def loesung(status):
    """(verständlicher Text, Aktion) zu einem Statustext; ohne bekanntes Muster der Originaltext und „experte“."""
    s = str(status or "")
    for muster, text, aktion in LOESUNGEN:
        if muster in s:
            return text, aktion
    roh = s.split(":", 1)[1].strip() if ":" in s else s
    return (roh[:1].upper() + roh[1:] + ". Bitte im Expertenmodus prüfen.") if roh else "", "experte"


def hinweise(bauteile, kopf=None, stand=None, ergebnis_=None, fehler_einplanen=0):
    """Hinweise mit Lösungsvorschlag für den einfachen Modus: [(stufe, text, aktion, zeile)] (zeile = Index der
    Position oder None). Fragt gezielt nach, statt Werte anzunehmen: fehlende Stückzahl, Abmessung, Werkstoff, Preis,
    Kunde, nicht eingeplante Teile, Preis unter den Kosten."""
    aus = []
    for i, b in enumerate(bauteile or ()):
        if b["stufe"] in ("FEHLER", "WARNUNG"):
            text, aktion = loesung(b["status"])
            aus.append((b["stufe"], f"{b['name']}: {text}", aktion, i))
    if not bauteile:
        aus.append(("FEHLER", "Die Kalkulation hat noch keine Bauteile. Bitte eine STEP- oder CAD-Datei importieren "
                              "oder ein Bauteil aus der Bibliothek wählen.", "import", None))
    if fehler_einplanen:
        aus.append(("WARNUNG", f"{fehler_einplanen} Teil(e) sind noch nicht auf Stangen eingeplant. Bitte neu "
                               "berechnen.", "optimieren", None))
    if kopf is not None and not kopf.get("kundennr") and not kopf.get("kunde"):
        aus.append(("HINWEIS", "Noch kein Kunde gewählt. Für das Angebot bitte den Kunden wählen.", "kunde", None))
    e = ergebnis_ or {}
    if e.get("verkauf") is not None and bauteile and e.get("verkauf", 0) <= 0:
        aus.append(("WARNUNG", "Der Verkaufspreis ist 0 €. Meist fehlen Stückzahl oder Materialpreis.", "material",
                    None))
    if e.get("stufe") == "kritisch":
        aus.append(("WARNUNG", "Der Preis ist wirtschaftlich kritisch: " + "; ".join(e.get("gruende") or ())
                    + ". Bitte Preis im Expertenmodus prüfen.", "experte", None))
    return aus


def naechster_schritt(schritt, hinw, hat_angebot, kunde=True):
    """Text der Benutzerführung in der Fußleiste: was als Nächstes zu tun ist (ein Satz)."""
    if not hat_angebot:
        return ("„Neue Kalkulation“ anlegen, eine STEP- oder CAD-Datei hineinziehen oder eine bestehende Kalkulation "
                "öffnen.")
    fehler = [h for h in hinw if h[0] == "FEHLER" and schritt_von(h) == BAUTEILE]
    if schritt == KUNDE:
        return ("Kunden wählen oder anlegen, dann weiter zu den Bauteilen." if not kunde else
                "Weiter zu Schritt 2: Bauteile importieren und Stückzahlen prüfen.")
    if schritt == BAUTEILE:
        if not any(h[2] == "import" for h in hinw) and fehler:
            return f"Bitte zuerst {len(fehler)} rot markierte Angabe(n) ergänzen, dann „Weiter“."
        if any(h[2] == "import" for h in hinw):
            return "Bauteile importieren: Knopf „Importieren …“ oder Dateien ins Fenster ziehen."
        return "Weiter zu Schritt 3: Material und Fertigung prüfen."
    if schritt == MATERIAL:
        return "Weiter zu Schritt 4: Preis und Marge ansehen."
    if schritt == KALKULATION:
        return "Preis passt? Weiter zu Schritt 5: Angebot prüfen und PDF erstellen."
    if schritt >= ANGEBOT:
        return "Angebot erstellen (PDF). Gespeichert wird jede Änderung sofort."
    return f"Weiter zu Schritt {schritt + 1}: {SCHRITTE[schritt + 1][1]}."


def bereitschaft(hinw, kopf, bauteile, stand, ergebnis_=None):
    """Stand der Kalkulation für Schrittleiste und Kopf (Einfacher Modus 2.0): dict(je_schritt={Schritt: "ok" |
    "fehlt" | "offen"}, offen=[Hinweise mit FEHLER/WARNUNG oder fehlendem Kunden], gerechnet=bool, bereit=bool,
    text, stufe (Chip: ok/warnung/info)). Fehlt nichts und ist der Schnittplan aktuell, ist das Angebot bereit zur
    Ausgabe."""
    kopf = kopf or {}
    e = ergebnis_ or {}
    offen = [h for h in hinw if h[0] in ("FEHLER", "WARNUNG") or h[2] == "kunde"]
    je = {s: "offen" for s in range(KUNDE, ANGEBOT + 1)}
    fehlt = {schritt_von(h) for h in offen}
    gerechnet = stand == "aktuell"
    hat_kunde = bool(kopf.get("kundennr") or kopf.get("kunde"))
    je[KUNDE] = "ok" if hat_kunde else "fehlt"
    je[BAUTEILE] = "fehlt" if BAUTEILE in fehlt else ("ok" if bauteile else "offen")
    je[MATERIAL] = "fehlt" if MATERIAL in fehlt else ("ok" if bauteile and gerechnet else "offen")
    je[KALKULATION] = "fehlt" if KALKULATION in fehlt else (
        "ok" if gerechnet and (e.get("verkauf") or 0) > 0 else "offen")
    bereit = not offen and gerechnet and bool(bauteile) and (e.get("verkauf") or 0) > 0
    je[ANGEBOT] = "ok" if bereit else "offen"
    if bereit:
        text, stufe = "Bereit zur Ausgabe", "ok"
    elif offen:
        text, stufe = (f"{len(offen)} Angabe fehlt" if len(offen) == 1 else f"{len(offen)} Angaben fehlen"), "warnung"
    elif not bauteile:
        text, stufe = "Noch keine Bauteile", "info"
    else:
        text, stufe = "Noch nicht berechnet", "info"
    return dict(je_schritt=je, offen=offen, gerechnet=gerechnet, bereit=bereit, text=text, stufe=stufe)


# ------------------------------------------------------------------ Material
def material_gruppen(positionen, bauteile, kopf, k, tabellen, varianten=None, meterpreis=None):
    """Materialgruppen des Angebots (Abmessung × Werkstoff, nur Rohrlaserteile) für Schritt 3: [dict(profil,
    werkstoff, form, wand, zeilen, stueck, preis_m, preis_kg, quelle, stand, alter_tage, lieferanten, bestand,
    fehlt_preis)] in der Reihenfolge der Positionen. varianten = materialplattform.varianten-Zeilen (Preisquelle,
    Lieferanten, Bestand), meterpreis(p) = rechnen.meterpreis (wirksamer Preis wie in der Kalkulation)."""
    var = {(z["profil_id"], z["werkstoff_id"]): z for z in varianten or ()}
    gruppen = {}
    for i, (p, b) in enumerate(zip(positionen, bauteile)):
        if b["art"] != "rohr" or not p.get("profil_id"):
            continue
        schl = (p.get("profil_id"), p.get("werkstoff_id") or "")
        g = gruppen.get(schl)
        if g is None:
            pr = k.profile.get(schl[0]) or {}
            v = var.get(schl) or {}
            g = gruppen[schl] = dict(profil=schl[0], werkstoff=schl[1], form=form_text(pr), wand=pr.get("wand"),
                                     zeilen=[], stueck=0, preis_m=None, preis_kg=v.get("preis_kg"),
                                     quelle=v.get("quelle") or "", stand=v.get("stand") or "",
                                     alter_tage=v.get("alter_tage"), lieferanten=list(v.get("lieferanten") or ()),
                                     bestand=v.get("bestand_stangen"), kgm=v.get("kgm"), fehlt_preis=False)
        g["zeilen"].append(i)
        g["stueck"] += int(_n(p.get("stueck")))
        if meterpreis is not None and g["preis_m"] is None:
            try:
                _, wirksam, fehlt = meterpreis(p)
            except Exception:       # noqa: BLE001 – Anzeige, die Kalkulation meldet es selbst
                wirksam, fehlt = None, True
            g["preis_m"] = wirksam
            g["fehlt_preis"] = wirksam is None or bool(fehlt)
            if wirksam is not None and g.get("kgm"):
                g["preis_kg"] = wirksam / g["kgm"]
    return list(gruppen.values())


def verfuegbar_text(g, lager_an):
    if lager_an and g.get("bestand") is not None:
        return f"Lager: {int(g['bestand'])} Stangen" if g["bestand"] else "Lager: nicht vorrätig"
    if g.get("lieferanten"):
        return "Lieferbar über " + ", ".join(g["lieferanten"][:3])
    return "Lieferant unbekannt – bitte anfragen"
