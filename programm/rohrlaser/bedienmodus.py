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
         "Geführte Kalkulation in sechs Schritten: Bauteil importieren, prüfen, Material wählen, Kosten ansehen, "
         "Ergebnis, Angebot. Große Schaltflächen, nur die wichtigen Angaben; alles Weitere rechnet das Programm im "
         "Hintergrund. Für Mitarbeiter ohne tiefe CAD- oder Kalkulationskenntnisse."),
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


def hilfe_an(db):
    return bool(_je_benutzer(db, HILFE_AN, True))


def hilfe_setzen(db, an):
    return _je_benutzer_setzen(db, HILFE_AN, bool(an))


def willkommen_an(db):
    return not _je_benutzer(db, WILLKOMMEN, False)


def willkommen_aus(db):
    return _je_benutzer_setzen(db, WILLKOMMEN, True)


# ------------------------------------------------------------------ Schritte und Hilfe
START, BAUTEILE, MATERIAL, BEARBEITUNG, ERGEBNIS, ANGEBOT = range(6)
SCHRITTE = (
    ("start", "Start", "Neue Kalkulation erstellen oder eine bestehende öffnen.",
     "Wählen Sie, womit Sie beginnen: eine STEP-Datei (3D-Modell des Bauteils), eine andere CAD-Datei (DXF, TRUMPF "
     "LST, BLM ArTube/BPF, IGES), ein gespeichertes Bauteil aus der Bauteilbibliothek oder eine Kalkulation, die es "
     "schon gibt. Das Programm legt dafür ein Angebot an; es ist dasselbe Angebot, das auch der Expertenmodus "
     "zeigt."),
    ("bauteile", "Bauteile", "Erkannte Bauteile prüfen und Stückzahlen eintragen.",
     "Das Programm hat die Geometrie gelesen: Rohr- oder Profilquerschnitt, Abmessung, Wandstärke, Länge, "
     "Schnittkonturen sowie Norm- und Zukaufteile. Prüfen Sie die Liste, tragen Sie die Stückzahl ein und sehen Sie "
     "sich das Bauteil in 3D an. Rote oder gelbe Hinweise sagen, was fehlt, und bieten die Lösung mit einem Klick "
     "an."),
    ("material", "Material", "Werkstoff, Abmessung und Materialpreis kontrollieren.",
     "Je Abmessung steht hier der Werkstoff mit Wandstärke, Preis (aus der Preisliste, der Lieferlänge oder dem "
     "Tonnenpreis) und Verfügbarkeit. Das Programm schlägt das Material aus der erkannten Geometrie vor; ändern Sie "
     "den Werkstoff nur, wenn der Kunde etwas anderes möchte. Fehlt ein Preis, führt der Knopf direkt dorthin, wo "
     "er eingetragen wird."),
    ("bearbeitung", "Bearbeitung", "Maschinenzeit, Schnitt-, Rüst- und Zusatzkosten ansehen.",
     "Schnittwege, Maschinenzeiten, Rüsten und Gemeinkosten rechnet das Programm automatisch mit denselben Werten "
     "wie im Expertenmodus. Eingreifen müssen Sie nur bei Zusatzarbeiten (z. B. Gewinde, Senken, Entgraten) und "
     "Zukaufteilen. Vorgeschlagene Arbeiten übernehmen Sie mit einem Klick. Frachtkosten tragen Sie unter "
     "„Frachtkosten“ von Hand ein oder lassen sie mit „Fracht berechnen …“ (Paket oder Palette, Tarif) rechnen."),
    ("ergebnis", "Ergebnis", "Kosten, Verkaufspreis und Marge auf einen Blick.",
     "Die Ergebnisübersicht zeigt Material-, Bearbeitungs-, Maschinen- und Zusatzkosten, die Gesamtkosten, den "
     "Verkaufspreis und den Gewinn mit Marge. Die Ampel sagt, ob der Preis wirtschaftlich ist (grün gut, orange "
     "knapp, rot kritisch). Unter „Marge einstellen“ tragen Sie die gewünschte Marge ein; das Programm stellt den "
     "Gewinn passend ein. Darunter steht der Preis je Bauteil."),
    ("angebot", "Angebot", "Kunden wählen, Mengen und Preise prüfen, PDF erstellen.",
     "Wählen Sie den Kunden, kontrollieren Sie Mengen und Preise und erstellen Sie das Angebot als PDF. Gespeichert "
     "wird jede Änderung sofort; mit gemeinsamem Ordner sehen die Kollegen das Angebot nach dem Abgleich. Für "
     "Staffeln, Rabatte oder Sonderfälle öffnet „Im Expertenmodus weiterbearbeiten“ dasselbe Angebot mit allen "
     "Funktionen."),
)

# kurze Erklärungen zu Feldern und Kennzahlen (Tooltips und Hilfe)
FELD_HILFE = {
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


def naechster_schritt(schritt, hinw, hat_angebot):
    """Text der Benutzerführung unten: was als Nächstes zu tun ist."""
    if not hat_angebot:
        return "Mit „Neue Kalkulation erstellen“ beginnen oder eine bestehende Kalkulation öffnen."
    fehler = [h for h in hinw if h[0] == "FEHLER"]
    if fehler and schritt <= BAUTEILE:
        return f"Bitte zuerst {len(fehler)} rot markierte Angabe(n) ergänzen, dann „Weiter“."
    if schritt >= ANGEBOT:
        return "Angebot erstellen (PDF). Gespeichert wird jede Änderung sofort."
    return f"Weiter zu Schritt {schritt + 2}: {SCHRITTE[schritt + 1][1]}."


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
