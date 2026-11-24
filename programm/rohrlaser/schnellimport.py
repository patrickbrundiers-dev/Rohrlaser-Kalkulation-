"""Schnellimport „Schneidweg & Zusatzarbeiten“ (Master-Prompt Patrick 24.11.2026: Schnellimport und
Schneidweg-Kalkulation ohne editierbare 3D-Geometrie). Ohne Qt, damit Tests und Vergleichswerkzeug es nutzen können.

Zwei Importmodi:
- vollständig (MODUS_VOLL): Messung mit Dreiecksnetz und Flächenkatalog, Prüfdialog mit 3D, Körper der STEP in der
  3D-Ansicht und im 3D-Editor – wie bisher.
- Schnellkalkulation (MODUS_SCHNELL): dieselbe Messung mit --netze-linien. Die Messung rechnet Querschnitte,
  Konturen, Enden, Bohrungen und Schneidweg genauso (bitgleich, werkzeuge/schnellimport_vergleich.py), legt aber kein
  Dreiecksnetz und keinen Flächenkatalog an. Die Linienzüge der Konturen bleiben: mit ihnen läuft die 3D-Gegenprobe
  (Editor-Modell gegen STEP) wie im Vollimport. Statt des Prüfdialogs zeigt eine kompakte Übersicht Schneidweg,
  Konturen, Einstiche, Bearbeitungen, Zusatzarbeiten und die Genauigkeit; übernommen wird mit derselben Rechnung
  (step.uebernehmen, schneidweg.rechnen, rechnen.kalkulation). Die Position bekommt keinen STEP-Körper (die
  3D-Ansicht zeigt das Modell des Schneidweg-Rechners); „3D aus STEP nachladen“ holt ihn später, ohne die Werte zu
  ändern.

Was dauerhaft gespeichert wird (technik der Position, Schlüssel SCHLUESSEL): Modus, STEP-Datei und Körper (wie
step_herkunft), Programmversion, Zeitpunkt, Genauigkeit mit Gründen, Messwerte der Erkennung (Schneidweg,
Konturen, Einstiche, Bearbeitungen) und der Kalkulationsstatus.
"""
import datetime
import json

from . import step

MODUS_VOLL, MODUS_SCHNELL = "voll", "schnell"
# Einstellung step_importmodus (Auswahl „importmodus“)
EINSTELLUNG_TEXT = {MODUS_VOLL: "vollständig", MODUS_SCHNELL: "Schnellkalkulation"}
TITEL = {MODUS_VOLL: "Vollständiger CAD-Import", MODUS_SCHNELL: "Schneidweg & Zusatzarbeiten (Schnellkalkulation)"}
BESCHREIBUNG = {
    MODUS_VOLL: "Vollständige Geometrieanalyse mit 3D-Darstellung: Prüfdialog mit 3D-Ansicht, Bearbeitung im "
                "3D-Editor, Konturauswahl und alle CAD-Funktionen.",
    MODUS_SCHNELL: "Dieselbe Geometrieanalyse für Schneidweg, Konturen, Einstiche und Zusatzarbeiten, aber ohne "
                   "3D-Aufbereitung: kompakte Übersicht statt Prüfdialog, gleiche Kalkulation. Der STEP-Körper "
                   "lässt sich später nachladen."}
SCHLUESSEL = "step_import"
NACHGELADEN = "voll (3D nachgeladen)"

# Genauigkeitsanzeige (Abschnitt 7 des Auftrags), Reihenfolge = Stufe 0..3
STUFEN = ("Sicher erkannt", "Wahrscheinlich erkannt", "Nicht eindeutig erkannt", "Manuelle Prüfung erforderlich")
FARBEN = ("#2e7d32", "#558b2f", "#f9a825", "#c62828")
# Kalkulationsstatus (Abschnitt 9)
VOLLSTAENDIG, TEILWEISE, ERGAENZEN = ("Daten vollständig", "Daten teilweise erkannt", "Manuelle Ergänzung erforderlich")

# Konturarten der Messung (konturen_liste): Laserkonturen und Merkmale, die der Laser nicht schneidet
LASER_ARTEN = {"Bohrung": "Bohrungen", "Langloch": "Langlöcher", "Rechteckausschnitt": "Rechteckige Ausschnitte",
               "Ausschnitt": "Ausschnitte", "Sonderkontur": "Freiformkonturen", "Kontur": "Freiformkonturen",
               "Senkung": "Senkungen", "Fließloch": "Fließlöcher (Flowdrill)"}
NICHT_GELASERT = {"Sackbohrung": "Sackbohrungen (nicht laserbar)", "Gravur": "Gravuren"}
ENDE_FORMEN = {"gerade": "gerade", "Gehrung": "Gehrung", "Schrägschnitt zweiachsig": "Schrägschnitt",
               "komplex": "Freiform-Ende"}


def modus_aus_text(text):
    """Einstellung step_importmodus (Text) -> MODUS_VOLL / MODUS_SCHNELL."""
    return MODUS_SCHNELL if str(text or "").strip().lower().startswith("schnell") else MODUS_VOLL


def an(db):
    """Funktion Schnellimport eingeschaltet (funktionen.SCHNELLIMPORT, Vorgabe aus, Patrick 24.11.2026)? Ohne
    Datenbank aus."""
    if db is None:
        return False
    from . import funktionen
    return db.einstellung(funktionen.SCHNELLIMPORT) == "ja"


def vorgabe(db):
    """Importmodus als Vorgabe (Einstellung step_importmodus, Vorgabe vollständig); Funktion aus: immer vollständig."""
    if not an(db):
        return MODUS_VOLL
    return modus_aus_text(db.einstellung("step_importmodus"))


def fragen(db):
    """Bei jedem Import nach dem Modus fragen (Einstellung step_importmodus_fragen, Vorgabe ja); Funktion aus: nie."""
    return an(db) and db.einstellung("step_importmodus_fragen") != "nein"


def mess_argumente(modus):
    """Zusätzliche Aufrufargumente der Messung (STEP-Import.exe)."""
    return ["--netze-linien"] if modus == MODUS_SCHNELL else []


def nur_linien(netz):
    """True, wenn das Netz (dict oder komprimiert) nur Linienzüge hat (Messung des Schnellimports)."""
    if netz is None:
        return False
    if isinstance(netz, (bytes, bytearray, memoryview)):
        from .ansicht3d import entpacken
        try:
            netz = entpacken(bytes(netz))
        except (ValueError, TypeError, OSError):
            return False
    return isinstance(netz, dict) and bool(netz.get("nur_linien"))


def _liste(m):
    try:
        x = json.loads(m.get("konturen_liste") or "[]")
    except (TypeError, ValueError):
        return []
    return [d for d in x if isinstance(d, dict)] if isinstance(x, list) else []


def _zahl(m, name):
    try:
        return float(m.get(name) or 0)
    except (TypeError, ValueError):
        return 0.0


def merkmale(m):
    """Erkennung eines gemessenen Teils für Übersicht und Speicherung: Schneidweg, Schnittlängen, Konturen, Einstiche,
    Anfahrten (je Einstich eine, so rechnet die Kalkulation die Anfahrzeit), Schnittarten der Enden, Bearbeitungen je
    Art (aus der Konturliste der Messung), Zusatzarbeiten (Senkungen, Fließlöcher, Gewinde-Vorschlag, Fasen,
    Gravuren, nicht laserbare Sackbohrungen). Nichts wird geschätzt: was die Messung nicht kennt, fehlt."""
    liste = _liste(m)
    bearbeitungen, nicht_gelasert, enden = {}, {}, {}
    for d in liste:
        art = d.get("art") or ""
        if art in ("Ende A", "Ende B"):
            enden[art] = ENDE_FORMEN.get(d.get("form"), d.get("form") or "")
            continue
        if art in NICHT_GELASERT or d.get("durchgehend") is False:
            name = NICHT_GELASERT.get(art, art)
            nicht_gelasert[name] = nicht_gelasert.get(name, 0) + 1
            continue
        name = LASER_ARTEN.get(art, art or "Kontur")
        bearbeitungen[name] = bearbeitungen.get(name, 0) + 1
    hinweise = str(m.get("hinweise") or "")
    zusatz = {}
    for feld, name in (("senkungen", "Senkungen"), ("fliessloecher", "Fließlöcher (Flowdrill)")):
        n = sum(int(float(t.rpartition(":")[2] or 0)) for t in str(m.get(feld) or "").split("|") if ":" in t)
        if n:
            zusatz[name] = n
    fasen = sum(1 for e in ("Ende A", "Ende B") if f"{e}: {step.FASE_HINWEIS}" in hinweise)
    if fasen:
        zusatz["Fasen an den Enden"] = fasen
    if _zahl(m, "gravur") > 0:
        zusatz["Gravur [mm]"] = round(_zahl(m, "gravur"), 1)
    for name, n in nicht_gelasert.items():
        zusatz[name] = n
    gewinde = step.gewinde_vorschlag(m.get("bohrungen"), step.KERNLOCH) if m.get("bohrungen") else ""
    schnittarten = sorted({f for f in enden.values() if f})
    return dict(
        bauteil=m.get("bauteiltyp") or m.get("profilform") or "",
        profilform=m.get("profilform") or "", abm_a=round(_zahl(m, "abm_a"), 2), abm_b=round(_zahl(m, "abm_b"), 2),
        wand=round(_zahl(m, "abm_b") if m.get("profilform") == "Flachstahl" else _zahl(m, "wandstaerke"), 2),
        laenge=round(_zahl(m, "laenge"), 2), schneidweg=round(_zahl(m, "schneidweg"), 2),
        enden_mm=round(_zahl(m, "ende_a") + _zahl(m, "ende_b"), 2), innen_mm=round(_zahl(m, "innen"), 2),
        konturen=int(_zahl(m, "konturen")), einstiche=int(_zahl(m, "konturen")), anfahrten=int(_zahl(m, "konturen")),
        innen_konturen=int(_zahl(m, "innen_konturen")), enden=enden, schnittarten=schnittarten,
        bearbeitungen=bearbeitungen, zusatz=zusatz, gewinde=gewinde,
        bohrungen=step.bohrungen_text(m.get("bohrungen")) if m.get("bohrungen") else "")


def _gegenprobe(m):
    """Ergebnis der 3D-Gegenprobe (Rohr bzw. Kantteil): True passt, False weicht ab, None nicht verglichen."""
    for schl in ("_rohr_gegenprobe", "_kant_gegenprobe"):
        e = m.get(schl)
        if isinstance(e, (tuple, list)) and e:
            return bool(e[0])
    return None


def genauigkeit(m, profile=None):
    """Genauigkeit eines Teils (Stufe 0..3 nach STUFEN, Gründe). Grundlage sind dieselben Prüfungen wie im
    Prüfdialog (step.ampel, sperrt, Prüfstatus) und die 3D-Gegenprobe:
    0 sicher: Ampel grün und das Editor-Modell liegt wie die STEP (bzw. Blech/Dreh-/Frästeil ohne Gegenprobe),
    1 wahrscheinlich: grün ohne Gegenprobe oder nur Hinweise (Normteil, Fertigbarkeit, Plausibilität, Profil fehlt),
    2 nicht eindeutig: unsichere Messung oder Prüfstatus „prüfen“,
    3 manuelle Prüfung: Fehler, nicht messbar, Gegenprobe weicht ab oder das Teil wird ohne Haken nicht übernommen."""
    profil_fehlt = False
    if profile is not None and m.get("profilform") and step.blech(m) is None and not m.get("fehler"):
        try:
            profil_fehlt = step.finde_profil(m, profile) is None and not m.get("_profil")
        except (TypeError, ValueError, KeyError):
            profil_fehlt = False
    farbe, gruende = step.ampel(m, profil_fehlt)
    gp = _gegenprobe(m)
    if farbe == "rot":
        return 3, gruende
    if gp is False:
        return 3, gruende + ["3D-Gegenprobe: Editor-Modell weicht von der STEP ab"]
    if step.sperrt(m):
        return 3, gruende + ["unsichere Messung sperrt das Übernehmen ohne Haken"]
    if m.get("profilform") in step.BLECHE and m.get("pruefstatus") == "prüfen" and m.get("_uebernehmen") is not True:
        return 3, gruende + ["Blech mit Prüfstatus „prüfen“: erst nach Haken übernehmen"]
    if step.unsicher(m) and not m.get("_rohr_bestaetigt"):
        return 2, gruende
    if m.get("pruefstatus") == "prüfen":
        return 2, gruende
    if farbe == "gelb":
        return 1, gruende
    from .step_gegenprobe import FORMEN, OFFEN
    if gp is None and step.blech(m) is None and m.get("profilform") in FORMEN + OFFEN:
        return 1, ["ohne 3D-Gegenprobe (nicht vergleichbar)"]
    return 0, gruende + (["3D-Gegenprobe bestanden"] if gp else [])


def stufe_text(stufe):
    return STUFEN[max(0, min(3, int(stufe)))]


def status(messwerte, profile=None):
    """Kalkulationsstatus aller gewählten Teile: (Text, {Stufe: Anzahl})."""
    zaehler = {i: 0 for i in range(4)}
    for m in messwerte:
        if not step.gewaehlt(m):
            continue
        zaehler[genauigkeit(m, profile)[0]] += 1
    if not sum(zaehler.values()):
        return ERGAENZEN, zaehler
    if zaehler[3]:
        return ERGAENZEN, zaehler
    if zaehler[2] or zaehler[1]:
        return TEILWEISE, zaehler
    return VOLLSTAENDIG, zaehler


def zusammenfassung(messwerte, profile=None):
    """Summen der Übersicht: Teile, gewählt, Schneidweg, Konturen, Einstiche, Bohrungen, Zusatzarbeiten je Art."""
    gew = [m for m in messwerte if step.gewaehlt(m) and not m.get("fehler")]
    zusatz, bearb = {}, {}
    sw = ko = 0.0
    for m in gew:
        mm = merkmale(m)
        sw += mm["schneidweg"]
        ko += mm["konturen"]
        for k, v in mm["zusatz"].items():
            zusatz[k] = round(zusatz.get(k, 0) + v, 1)
        for k, v in mm["bearbeitungen"].items():
            bearb[k] = bearb.get(k, 0) + v
    text, zaehler = status(messwerte, profile)
    return dict(teile=len(messwerte), gewaehlt=len(gew), schneidweg=round(sw, 1), konturen=int(ko),
                einstiche=int(ko), bearbeitungen=bearb, zusatz=zusatz, status=text, stufen=zaehler)


def merken(p, m, version, profile=None, modus=MODUS_SCHNELL, jetzt=None):
    """Importmodus und Erkennung an die Position (technik, Schlüssel SCHLUESSEL) hängen; nur wenn technik ein
    JSON-Objekt ist (Rohre, Profile, Bleche mit Editor-Daten). Ergebnis: p."""
    try:
        d = json.loads(p["technik"]) if p.get("technik") else None
    except (TypeError, ValueError):
        return p
    if not isinstance(d, dict):
        return p
    stufe, gruende = genauigkeit(m, profile)
    mm = merkmale(m)
    d[SCHLUESSEL] = dict(
        modus=modus, version=version, datei=str(m.get("_pfad") or ""), name=m.get("datei") or "",
        koerper=int(_zahl(m, "koerper") or 1),
        zeit=(jetzt or datetime.datetime.now()).replace(microsecond=0).isoformat(),
        genauigkeit=stufe_text(stufe), gruende=gruende[:8],
        status=VOLLSTAENDIG if stufe == 0 else TEILWEISE if stufe in (1, 2) else ERGAENZEN,
        erkennung={k: mm[k] for k in ("schneidweg", "konturen", "einstiche", "anfahrten", "enden", "bearbeitungen",
                                      "zusatz", "gewinde")})
    p["technik"] = json.dumps(d, ensure_ascii=False)
    return p


def lesen(p):
    """Importdaten der Position (dict) oder None."""
    try:
        d = json.loads(p.get("technik") or "")
    except (TypeError, ValueError):
        return None
    x = d.get(SCHLUESSEL) if isinstance(d, dict) else None
    return x if isinstance(x, dict) else None


def ist_schnell(p):
    """Position aus dem Schnellimport ohne nachgeladenen STEP-Körper."""
    return (lesen(p) or {}).get("modus") == MODUS_SCHNELL


def nachgeladen(p, jetzt=None):
    """Nach „3D aus STEP nachladen“: Modus in technik umstellen (Erkennung bleibt). Ergebnis: p."""
    try:
        d = json.loads(p.get("technik") or "")
    except (TypeError, ValueError):
        return p
    if isinstance(d, dict) and isinstance(d.get(SCHLUESSEL), dict):
        d[SCHLUESSEL] = dict(d[SCHLUESSEL], modus=NACHGELADEN,
                             nachgeladen=(jetzt or datetime.datetime.now()).replace(microsecond=0).isoformat())
        p["technik"] = json.dumps(d, ensure_ascii=False)
    return p


def koerper_finden(messwerte, info):
    """Messwerte des Körpers aus der Herkunft (name, koerper) der Position oder None."""
    for i, m in enumerate(messwerte):
        if (not info.get("name") or m.get("datei") == info["name"]) and \
                int(_zahl(m, "koerper") or 1) == int(info.get("koerper") or 1):
            return i
    return None


VERGLEICH_FELDER = ("profilform", "abm_a", "abm_b", "wandstaerke", "laenge", "schneidweg", "konturen", "innen",
                    "innen_konturen", "bohrungen", "senkungen", "fliessloecher", "gravur", "ende_a", "ende_b")


def gleiche_messung(a, b):
    """Felder, in denen sich zwei Messungen desselben Körpers unterscheiden ([] = gleich), z. B. beim Nachladen."""
    return [f for f in VERGLEICH_FELDER if str(a.get(f) or "") != str(b.get(f) or "")]
