"""Online-Preise der Lieferanten (Entwicklungsauftrag Patrick 18.11.2026 „Automatisierter Online-Preisabruf“).

Recherche Phase 1 (Claude Doc „Online-Materialpreise: Lieferanten-Prüfung“): thyssenkrupp Materials Services,
ArcelorMittal und Klöckner bieten keine öffentliche Preis-API; Kundenpreise gibt es nur nach Login. Ein Programm, das
sich mit dem Shop-Login selbst anmeldet und Seiten ausliest, verstößt gegen die Shop-Bedingungen und wird nicht gebaut.
Erlaubt sind die Wege der Adapter (onlinepreise_adapter.py): OCI-Punchout (offizielle Shop-Schnittstelle, Zugang vom
Lieferanten freigeschaltet), Preislisten (CSV/Excel, auch EDI-PRICAT als Datei) und die Shop-Suche im Browser mit
Erfassen von Hand.

Datenmodell (gemeinsame Tabellen, über den gemeinsamen Ordner an allen Plätzen):
- online_lieferanten: je Lieferant Weg, Adressen, Aktualisierung und Konditionen (Rabatt, Fracht, Mindermengen-,
  Verpackungs-, Bearbeitungszuschlag, netto/brutto). Zugangsdaten stehen NIE hier, sondern in der
  Windows-Anmeldeinformationsverwaltung des PCs (zugang.py).
- online_preise: jeder Preisstand eines Artikels (Lieferant + Kennung) mit Quelle, Abrufzeit, Gültigkeit, Staffel,
  Verfügbarkeit, Lieferzeit und Zuordnung zu Profil + Werkstoff der Stammdaten. Ein unveränderter Preis bestätigt nur
  die Abrufzeit (keine neue Zeile); ein neuer Preis löst den alten Stand ab (Status 'abgelöst') und merkt die
  Änderung in %. So entsteht die Preishistorie.
- online_zuordnung: vom Anwender bestätigte Zuordnung Lieferant + Kennung -> Profil + Werkstoff.
- online_abrufe (nur dieser Platz): Protokoll jedes Abrufs.

Regeln (Auftrag Abschnitt 13): kein Preis wird erfunden oder geschätzt; jeder Preis trägt Quelle und Abrufzeit;
fehlende oder nicht umrechenbare Preise bleiben leer und werden so angezeigt; eine Zuordnung gilt nur als sicher, wenn
Profilform, alle Maße, Wandstärke und Werkstoff (bei mehreren Normen auch die Norm) genau passen, sonst 'prüfen' und
keine Übernahme; Übernahme schreibt nur die Stammdaten Preise (vorher Sicherung), festgeschriebene Angebote und
Aufträge (preisbasis/freigabe) bleiben unverändert. Kein Gewinn auf das Material, es gilt der Materialaufschlag.
Ohne Qt."""
import datetime
import hashlib
import json
import re

from .stammdaten import Feld, Tabelle

WEGE = ("Shop-Suche", "Preisliste", "OCI-Punchout")
INTERVALLE = ("manuell", "täglich", "wöchentlich", "beim Öffnen")
PREISARTEN = ("Kundenpreis", "Listenpreis")
BASEN = ("€/m", "€/kg", "€/Stange")
SICHER, BESTAETIGT, PRUEFEN, KEINE = "sicher", "bestätigt", "prüfen", "keine"
UEBERNEHMBAR = (SICHER, BESTAETIGT)
AKTUELL, ABGELOEST = "aktuell", "abgelöst"
VERALTET_TAGE = 7           # Einstellung online_veraltet_tage: Abruf älter = „veraltet“
SPRUNG = 10.0               # Einstellung online_sprung [%]: ungewöhnliche Preisänderung
MWST = 19.0

LIEFERANTEN = Tabelle(
    "online_lieferanten", "Online-Lieferanten",
    (Feld("name", "Lieferant", pflicht=True, breite=200),
     Feld("aktiv", "Aktiv", breite=55),
     Feld("weg", "Weg", breite=110),
     Feld("shop_adresse", "Shop-Adresse", breite=220),
     Feld("such_adresse", "Suchadresse ({suche})", breite=220),
     Feld("oci_adresse", "OCI-Einstiegsadresse", breite=220),
     Feld("oci_hintergrund", "OCI-Hintergrundsuche", breite=70),
     Feld("preisliste_ordner", "Preislisten-Ordner", breite=220),
     Feld("spalten", "Spaltenzuordnung", breite=120),
     Feld("aktualisierung", "Aktualisierung", breite=95),
     Feld("nur_verwendete", "Nur verwendete Materialien", breite=70),
     Feld("min_abstand_h", "Mindestabstand [h]", "zahl", 0, 1000, stellen=0, breite=70),
     Feld("preisart", "Preise sind", breite=95),
     Feld("brutto", "Preise brutto", breite=60),
     Feld("mwst", "MwSt [%]", "zahl", 0, 50, stellen=1, breite=60),
     Feld("rabatt", "Rabatt auf Listenpreis [%]", "zahl", 0, 100, stellen=1, breite=70),
     Feld("fracht", "Fracht je Bestellung [€]", "zahl", 0, 100000, stellen=2, breite=70),
     Feld("frei_ab", "Frachtfrei ab Warenwert [€]", "zahl", 0, 10000000, stellen=0, breite=80),
     Feld("mindermenge_bis", "Mindermenge bis Warenwert [€]", "zahl", 0, 10000000, stellen=0, breite=80),
     Feld("mindermenge_zuschlag", "Mindermengenzuschlag [€]", "zahl", 0, 100000, stellen=2, breite=80),
     Feld("verpackung", "Verpackung je Bestellung [€]", "zahl", 0, 100000, stellen=2, breite=70),
     Feld("bearbeitung", "Bearbeitung je Bestellung [€]", "zahl", 0, 100000, stellen=2, breite=70),
     Feld("kundennr", "Unsere Kundennummer", breite=110),
     Feld("bemerkung", "Bemerkung", breite=240)),
    ("name",),
    "Lieferanten für den Online-Preisabruf. Weg: Shop-Suche (Browser, Preis von Hand), Preisliste (CSV/Excel aus "
    "einem Ordner) oder OCI-Punchout (offizielle Shop-Schnittstelle, Zugang vom Lieferanten). Zugangsdaten nur im "
    "Fenster „Zugangsdaten …“ (Windows-Anmeldeinformationsverwaltung dieses PCs), nie in dieser Tabelle.")

PREISE = Tabelle(
    "online_preise", "Online-Preise",
    (Feld("lieferant", "Lieferant", pflicht=True, breite=160),
     Feld("kennung", "Kennung", pflicht=True, breite=140),
     Feld("seit", "Preis seit", pflicht=True, breite=130),
     Feld("abruf", "Letzter Abruf", breite=130),
     Feld("status", "Status", breite=70),
     Feld("artikelnr", "Artikelnummer", breite=110),
     Feld("bezeichnung", "Bezeichnung", breite=260),
     Feld("form", "Profilart", breite=100),
     Feld("a", "A [mm]", "zahl", 0, 10000, stellen=2, breite=60),
     Feld("b", "B [mm]", "zahl", 0, 10000, stellen=2, breite=60),
     Feld("wand", "Wand [mm]", "zahl", 0, 500, stellen=2, breite=60),
     Feld("laenge", "Länge [mm]", "zahl", 0, 100000, stellen=0, breite=70),
     Feld("werkstoff", "Güte laut Lieferant", breite=120),
     Feld("oberflaeche", "Oberfläche", breite=90),
     Feld("hersteller", "Hersteller", breite=100),
     Feld("profil_id", "Profil-ID", breite=120),
     Feld("werkstoff_id", "Werkstoff-ID", breite=110),
     Feld("zuordnung", "Zuordnung", breite=80),
     Feld("zuordnung_grund", "Zuordnung Grund", breite=220),
     Feld("basis", "Preisbasis", breite=70),
     Feld("preis", "Preis [€]", "zahl", 0, 10000000, stellen=4, breite=80),
     Feld("preisart", "Preisart", breite=90),
     Feld("brutto", "Brutto", breite=55),
     Feld("waehrung", "Währung", breite=55),
     Feld("staffel", "Staffel", breite=160),
     Feld("mindestmenge", "Mindestmenge", "zahl", 0, 10000000, stellen=2, breite=70),
     Feld("mengeneinheit", "Mengeneinheit", breite=60),
     Feld("ve", "Verpackungseinheit", breite=90),
     Feld("verfuegbarkeit", "Verfügbarkeit", breite=100),
     Feld("lieferzeit", "Lieferzeit [Tage]", "ganz", 0, 3650, breite=60),
     Feld("gueltig_bis", "Gültig bis", breite=90),
     Feld("quelle", "Quelle", breite=180),
     Feld("aenderung", "Änderung [%]", "zahl", -1000, 100000, stellen=1, breite=60),
     Feld("erfasst_von", "Erfasst von", breite=70),
     Feld("bemerkung", "Bemerkung", breite=200)),
    ("lieferant", "kennung", "seit"),
    "Preisstände aus dem Online-Preisabruf (nur Anzeige und Vergleich; gerechnet wird mit den Stammdaten Preise).")

ZUORDNUNG = Tabelle(
    "online_zuordnung", "Online-Zuordnung",
    (Feld("lieferant", "Lieferant", pflicht=True, breite=160),
     Feld("kennung", "Kennung", pflicht=True, breite=160),
     Feld("profil_id", "Profil-ID", breite=120),
     Feld("werkstoff_id", "Werkstoff-ID", breite=110),
     Feld("von", "Bestätigt von", breite=80),
     Feld("datum", "Datum", breite=90)),
    ("lieferant", "kennung"),
    "Vom Anwender bestätigte Zuordnung eines Lieferantenartikels zu Profil + Werkstoff (leer = gehört zu keinem).")

TABELLEN = (LIEFERANTEN, PREISE, ZUORDNUNG)
ABRUFE = "online_abrufe"

# Vorbelegung (nur Weg Shop-Suche mit der öffentlichen Startadresse; Suchadressen der SAP-Commerce-Shops e-steel und Schulte-Portal, 18.11.; OCI-Adresse und Preislisten-Ordner trägt der
# Anwender ein, sobald der Lieferant den Zugang freigeschaltet bzw. die Liste geschickt hat)
VORGABE = (
    dict(name="thyssenkrupp Materials Services (Schulte)", weg="Shop-Suche",
         shop_adresse="https://portal.thyssenkrupp-schulte.de",
         such_adresse="https://portal.thyssenkrupp-schulte.de/de/search?text={suche}"),
    dict(name="ArcelorMittal (e-steel)", weg="Shop-Suche", shop_adresse="https://e-steel.arcelormittal.com/DE/de",
         such_adresse="https://e-steel.arcelormittal.com/DE/de/search/?text={suche}"),
    dict(name="Klöckner & Co (Klöckner Shop)", weg="Shop-Suche", shop_adresse="https://shop.kloeckner.de"),
)
VORGABE_WERTE = dict(aktiv="ja", aktualisierung="manuell", nur_verwendete="nein", min_abstand_h=12,
                     preisart="Kundenpreis", brutto="nein", mwst=MWST, oci_hintergrund="nein")


def einrichten(con):
    """Protokolltabelle (nur dieser Platz); die gemeinsamen Tabellen legt die Datenbank über ALLE_TABELLEN an."""
    con.execute(f"CREATE TABLE IF NOT EXISTS {ABRUFE} (id INTEGER PRIMARY KEY, zeit TEXT, lieferant TEXT, weg TEXT, "
                "anlass TEXT, ergebnis TEXT, anzahl INTEGER, neu INTEGER, geaendert INTEGER, meldung TEXT, "
                "dauer REAL, benutzer TEXT)")


def vorbelegen(db):
    """Die drei Lieferanten einmal anlegen (Einstellung online_vorgabe); vorhandene Zeilen bleiben."""
    if db.einstellung("online_vorgabe") or db.nur_lesen:
        return 0
    da = {str(z.get("name") or "").casefold() for z in db.zeilen(LIEFERANTEN.name)}
    n = 0
    for v in VORGABE:
        if v["name"].casefold() not in da:
            db.neu(LIEFERANTEN.name, dict(VORGABE_WERTE, **v))
            n += 1
    db.einstellung_setzen("online_vorgabe", "2026-11-18")
    return n


# ------------------------------------------------------------------ Hilfen
def _n(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return zahl(v)


def zahl(t):
    """'1.234,56' / '1234.56' / '12,5 €' / '' -> float oder None."""
    if t is None:
        return None
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return float(t)
    s = re.sub(r"[^\d,.\-]", "", str(t))
    if not s or s in "-.,":
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def ja(v):
    return str(v or "").strip().lower() in ("ja", "j", "1", "true", "x", "yes")


def jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _zeit(t):
    try:
        return datetime.datetime.fromisoformat(str(t)[:19])
    except (TypeError, ValueError):
        return None


def _datum(t):
    t = str(t or "").strip()
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", t)
    if m:
        j = int(m.group(3))
        try:
            return datetime.date(j + 2000 if j < 100 else j, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    try:
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        return None


def kennung(e):
    """Schlüssel eines Lieferantenartikels: Artikelnummer, sonst die Bezeichnung (Kleinbuchstaben, ohne Leerraum)."""
    a = str(e.get("artikelnr") or "").strip()
    if a:
        return a
    return re.sub(r"\s+", " ", str(e.get("bezeichnung") or "").strip().lower())[:200]


# ------------------------------------------------------------------ Bezeichnung zerlegen
FORM_WOERTER = (
    (r"rechteck|recht\.|rhp|rechteckhohlprofil|rect", "Rechteckrohr"),
    (r"quadrat|vierkantrohr|vierkant-?rohr|qhp|quadr\.|square", "Quadratrohr"),
    (r"rundrohr|präzisions|praezisions|konstruktionsrohr|stahlrohr|rohr rund|siederohr|gewinderohr|rhs rund|"
     r"\bchs\b|round tube|ø", "Rundrohr"),
    (r"flachstahl|flach\b|flat bar|\bfl\b", "Flachstahl"),
    (r"winkel|l-profil|\bl\s*\d", "L-Profil"),
    (r"u-profil|\bupn\b|\bupe\b|\bu\s*\d", "U-Profil"),
    (r"rundstahl|rund\b|vollrund", "Rundstahl"),
    (r"vierkantstahl", "Vierkantstahl"),
)
OBERFLAECHE_WOERTER = (("feuerverzinkt", "feuerverzinkt"), ("sendzimir", "sendzimirverzinkt"),
                       ("verzinkt", "verzinkt"), ("gebeizt", "gebeizt"), ("geschliffen", "geschliffen"),
                       ("gebürstet", "gebürstet"), ("blank", "blank"), ("grundiert", "grundiert"),
                       ("gestrahlt", "gestrahlt"), ("lackiert", "lackiert"))
_ZAHL = r"\d+(?:[.,]\d+)?"


def zerlegen(text):
    """Profilart, Maße, Länge und Oberfläche aus einer Bezeichnung wie 'Rechteckrohr 80 x 40 x 3,0 mm S235JRH EN
    10219, 6000 mm' -> dict(form, a, b, wand, laenge, oberflaeche); fehlende Werte None. Nur was eindeutig im Text
    steht; nichts geraten (Länge ohne Einheit nur als 4. Maß hinter den Profilmaßen)."""
    t = " ".join(str(text or "").split())
    low = t.lower()
    form = next((f for muster, f in FORM_WOERTER if re.search(muster, low)), None)
    out = dict(form=form, a=None, b=None, wand=None, laenge=None, oberflaeche=None)
    for wort, ob in OBERFLAECHE_WOERTER:
        if wort in low:
            out["oberflaeche"] = ob
            break
    t2 = re.sub(r"\s*[x×*]\s*", "x", t, flags=re.I)
    m = re.search(rf"(?<![\d.,])({_ZAHL}(?:x{_ZAHL}){{1,3}})(?:\s*mm)?", t2)
    if m:
        z = [zahl(x) for x in m.group(1).split("x")]
        if form is None:
            form = {2: "Rundrohr", 3: "Quadratrohr" if z[0] == z[1] else "Rechteckrohr"}.get(len(z))
            out["form"] = form
        if form in ("Rundrohr", "Flachstahl"):
            out.update(a=z[0], wand=z[1])
            if form == "Flachstahl" and len(z) >= 2:
                out.update(a=max(z[0], z[1]), wand=min(z[0], z[1]))
            if len(z) == 3:
                out["laenge"] = z[2]
        elif form == "Quadratrohr":
            if len(z) == 2:
                out.update(a=z[0], wand=z[1])
            elif len(z) >= 3 and z[0] == z[1]:
                out.update(a=z[0], wand=z[2])
                if len(z) == 4:
                    out["laenge"] = z[3]
        elif form in ("Rechteckrohr", "L-Profil", "U-Profil"):
            if len(z) >= 3:
                out.update(a=z[0], b=z[1], wand=z[2])
                if len(z) == 4:
                    out["laenge"] = z[3]
            elif len(z) == 2 and form == "L-Profil":
                out.update(a=z[0], b=z[0], wand=z[1])
    m = re.search(r"(?:länge|laenge|lg\.?|\bl)\s*[=:]?\s*(\d[\d.,]*)\s*(mm|m)\b", low) or \
        re.search(r"(?<![x\d.,])(\d{1,2}(?:[.,]\d{3})|\d{4,5})\s*mm\b(?!\s*x)", low) or \
        re.search(r"(?<![x\d.,])(\d{1,2}(?:[.,]\d+)?)\s*m\b(?!m)", low)
    if m and out["laenge"] is None:
        w = zahl(m.group(1))
        einheit = m.group(2) if m.lastindex and m.lastindex >= 2 else ("mm" if "mm" in m.group(0) else "m")
        if w:
            w = w * 1000 if einheit == "m" else w
            if 500 <= w <= 30000 and not (out["a"] and abs(w - out["a"]) < 1e-9):
                out["laenge"] = w
    return out


def _norm_im_text(text):
    """Norm-Nummern im Text ('EN 10219', 'DIN EN 10305-1' -> {'10219', '10305'})."""
    return set(re.findall(r"\b(10\d{3})\b", str(text or "")))


def werkstoff_finden(text, k):
    """(werkstoff_id oder None, Grund): genau ein Werkstoff der Stammdaten passt zum Gütetext des Lieferanten. Gibt es
    mehrere (S235JRH nach EN 10219 und EN 10210), entscheidet eine Normnummer im Text; sonst None ('mehrdeutig')."""
    from . import werkstoff_namen
    from .werkstoff_namen import norm
    zeilen = list(getattr(k, "werkstoffe", {}).values())
    t = str(text or "")
    if not t.strip():
        return None, "keine Güte angegeben"
    nt = norm(t)
    worte = {norm(w) for w in re.split(r"[\s,;/()]+", t) if w}
    treffer = []
    for z in zeilen:
        namen = {norm(z.get(f)) for f in ("werkstoff_id", "werkstoff", "werkstoff_nr")} - {""}
        if namen & worte or (nt and nt in namen):
            treffer.append(z["werkstoff_id"])
    if not treffer:
        treffer = werkstoff_namen.passende_im_text(t, zeilen)
    treffer = list(dict.fromkeys(treffer))
    if len(treffer) > 1:
        normen = _norm_im_text(t)
        mit_norm = [w for w in treffer if any(n in str(w) for n in normen)]
        if len(mit_norm) == 1:
            return mit_norm[0], ""
        return None, f"Güte mehrdeutig ({', '.join(treffer[:4])}): Norm fehlt"
    if not treffer:
        return None, f"Güte „{t.strip()[:40]}“ nicht in den Werkstoffen"
    return treffer[0], ""


def zuordnen(e, k, bestaetigt=None):
    """Zuordnung eines Lieferantenartikels zu Profil + Werkstoff: dict(profil_id, werkstoff_id, zuordnung, grund).
    bestaetigt: Zeile aus online_zuordnung (vom Anwender bestätigt) geht vor. Sicher nur bei genauer Übereinstimmung
    von Profilform, allen Maßen, Wand und Güte; eine Oberfläche (verzinkt, geschliffen …) macht es zu 'prüfen'."""
    if bestaetigt is not None:
        if bestaetigt.get("profil_id") and bestaetigt.get("werkstoff_id"):
            return dict(profil_id=bestaetigt["profil_id"], werkstoff_id=bestaetigt["werkstoff_id"],
                        zuordnung=BESTAETIGT, grund=f"bestätigt von {bestaetigt.get('von') or '?'}")
        return dict(profil_id=None, werkstoff_id=None, zuordnung=KEINE, grund="als „gehört zu keinem“ bestätigt")
    text = " ".join(str(e.get(f) or "") for f in ("bezeichnung", "werkstoff", "abmessung"))
    z = zerlegen(text)
    form = e.get("form") or z["form"]
    a = _n(e.get("a")) if e.get("a") not in (None, "") else z["a"]
    b = _n(e.get("b")) if e.get("b") not in (None, "") else z["b"]
    wand = _n(e.get("wand")) if e.get("wand") not in (None, "") else z["wand"]
    if form == "Quadratrohr" and b and a and abs(a - b) > 1e-9:
        return dict(profil_id=None, werkstoff_id=None, zuordnung=PRUEFEN, grund="Quadratrohr mit A ≠ B")
    if not form or not a or not wand:
        return dict(profil_id=None, werkstoff_id=None, zuordnung=KEINE, grund="Profil oder Maße nicht erkennbar")
    profile = getattr(k, "profile", {})
    kandidat = pid(form, a, b if form not in ("Quadratrohr", "Rundrohr", "Flachstahl") else None, wand)
    p = profile.get(kandidat)
    if p is None:      # Stammdaten mit anderer Schreibweise der ID: über die Maße suchen
        p = next((q for q in profile.values() if q.get("form") == form and _gleich(q.get("a"), a)
                  and _gleich(q.get("wand"), wand)
                  and (form in ("Quadratrohr", "Rundrohr", "Flachstahl") or _gleich(q.get("b"), b))), None)
    if p is None:
        return dict(profil_id=None, werkstoff_id=None, zuordnung=PRUEFEN,
                    grund=f"Abmessung {kandidat} nicht in den Profilen")
    ws, grund = werkstoff_finden(e.get("werkstoff") or text, k)
    if ws is None:
        return dict(profil_id=p["profil_id"], werkstoff_id=None, zuordnung=PRUEFEN, grund=grund)
    ob = e.get("oberflaeche") or z["oberflaeche"]
    if ob and str(ob).lower() not in ("roh", "schwarz", "walzblank", "ohne"):
        return dict(profil_id=p["profil_id"], werkstoff_id=ws, zuordnung=PRUEFEN,
                    grund=f"Oberfläche „{ob}“: Rohpreis der Stammdaten nicht gleich")
    return dict(profil_id=p["profil_id"], werkstoff_id=ws, zuordnung=SICHER, grund="Profil, Maße und Güte genau gleich")


KUERZEL = {"Rundrohr": "RR", "Quadratrohr": "QR", "Rechteckrohr": "RE", "U-Profil": "U", "L-Profil": "L",
           "Flachstahl": "FL"}       # wie profil_neu.KUERZEL (dort mit Qt)


def pid(form, a, b=None, wand=None):
    """Profil-ID in der Schreibweise des STEP-Imports und von profil_neu.profil_id ('RE 60x40x3', 'RR 42,4x2')."""
    def mm(x):
        return f"{x:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    k = KUERZEL.get(form, "P")
    if form == "Quadratrohr":
        return f"{k} {mm(a)}x{mm(a)}x{mm(wand or 0)}"
    if form in ("Rechteckrohr", "U-Profil", "L-Profil") and b:
        return f"{k} {mm(a)}x{mm(b)}x{mm(wand or 0)}"
    return f"{k} {mm(a)}x{mm(wand or 0)}"


def _gleich(x, y):
    x, y = _n(x), _n(y)
    return x is not None and y is not None and abs(x - y) < 1e-6


# ------------------------------------------------------------------ Einheiten, Normalisierung
def basis_aus_einheit(einheit):
    """(Basis, Faktor) aus einer Preiseinheit: 'm', 'MTR', 'lfm', '€/m' -> ('€/m', 1); 'kg', 'KGM' -> ('€/kg', 1);
    't', 'TNE', '€/t' -> ('€/kg', 1/1000); '100 kg' -> ('€/kg', 1/100); 'St', 'Stk', 'PCE', 'Stange' -> ('€/Stange',
    1); '100 m' -> ('€/m', 1/100). None, wenn unbekannt."""
    t = str(einheit or "").strip().lower().replace("eur", "").replace("€", "").replace("/", " ").strip()
    m = re.fullmatch(r"(?:je|per|pro)?\s*(\d+(?:[.,]\d+)?)?\s*([a-zäöü.]+)", t)
    if not m:
        return None
    menge = zahl(m.group(1)) or 1.0
    e = m.group(2).rstrip(".")
    if e in ("m", "mtr", "lfm", "lfdm", "meter"):
        return "€/m", 1 / menge
    if e in ("kg", "kgm", "kilogramm"):
        return "€/kg", 1 / menge
    if e in ("t", "tne", "to", "tonne"):
        return "€/kg", 1 / (1000 * menge)
    if e in ("st", "stk", "stück", "stueck", "pce", "pc", "stange", "stg", "c62", "ea"):
        return "€/Stange", 1 / menge
    return None


def staffel_lesen(text):
    """'ab 1: 12,50 | ab 10: 11,90' -> [(ab, preis)] aufsteigend; leer/unklar -> []."""
    out = []
    for teil in re.split(r"[|;]", str(text or "")):
        m = re.fullmatch(r"\s*(?:ab\s*)?([\d.,]+)\s*(?:[a-zA-Zäöü]+)?\s*[:=]\s*([\d.,]+)\s*€?\s*", teil)
        if m and zahl(m.group(1)) is not None and zahl(m.group(2)) is not None:
            out.append((zahl(m.group(1)), zahl(m.group(2))))
    return sorted(out)


def staffel_text(staffel):
    from .stammdaten import zahl_als_text as z
    return " | ".join(f"ab {z(ab, 0)}: {z(p, 4)}" for ab, p in staffel)


def kg_je_m(e, k):
    from .rechnen import kg_je_m as kg
    if not e.get("profil_id") or not e.get("werkstoff_id"):
        return None
    try:
        return kg(e["profil_id"], e["werkstoff_id"], k)
    except Exception:
        return None


def normalisieren(e, k, lief=None, menge_m=None, stangenlaenge=None):
    """Einheitliche Vergleichsbasis eines Preisstands. Ergebnis dict:
    netto (Preis in seiner Basis ohne MwSt, nach Staffel und Rabatt), je_m, je_kg, je_stange (netto, None = nicht
    umrechenbar: ohne Zuordnung kein Metergewicht), laenge_mm, zusatz (Fracht + Mindermenge + Verpackung + Bearbeitung
    für die Menge, €), einstand_je_m (je_m + zusatz/Menge), bestellwert, hinweise [Text]. menge_m = benötigte Meter
    (für Staffel, Mindermenge, Fracht frei ab); ohne Menge keine Zusatzkosten je Meter."""
    lief = lief or {}
    hinweise = []
    preis, basis = _n(e.get("preis")), e.get("basis")
    out = dict(netto=None, je_m=None, je_kg=None, je_stange=None, laenge_mm=None, zusatz=0.0, einstand_je_m=None,
               bestellwert=None, hinweise=hinweise)
    if preis is None or preis <= 0 or basis not in BASEN:
        hinweise.append("kein Preis")
        return out
    kg = kg_je_m(e, k)
    laenge = _n(e.get("laenge")) or _n(stangenlaenge)
    out["laenge_mm"] = laenge
    # Staffel in der Mengeneinheit der Basis
    staffel = staffel_lesen(e.get("staffel"))
    if staffel and menge_m:
        menge_basis = {"€/m": menge_m, "€/kg": menge_m * kg if kg else None,
                       "€/Stange": menge_m / (laenge / 1000) if laenge else None}[basis]
        if menge_basis is not None:
            passend = [p for ab, p in staffel if ab <= menge_basis + 1e-9]
            if passend:
                preis = passend[-1]
                hinweise.append("Staffelpreis")
    brutto = ja(e.get("brutto"))
    if brutto:
        mwst = _n(lief.get("mwst"))
        preis = preis / (1 + (MWST if mwst is None else mwst) / 100)
        hinweise.append("aus Bruttopreis gerechnet")
    rabatt = _n(lief.get("rabatt")) or 0
    if rabatt and (e.get("preisart") or lief.get("preisart")) == "Listenpreis":
        preis *= 1 - rabatt / 100
        hinweise.append(f"Rabatt {rabatt:g} %")
    out["netto"] = preis
    if basis == "€/m":
        je_m = preis
    elif basis == "€/kg":
        je_m = preis * kg if kg else None
        out["je_kg"] = preis
    else:
        je_m = preis / (laenge / 1000) if laenge else None
        out["je_stange"] = preis
    out["je_m"] = je_m
    if je_m is not None:
        if out["je_kg"] is None and kg:
            out["je_kg"] = je_m / kg
        if out["je_stange"] is None and laenge:
            out["je_stange"] = je_m * laenge / 1000
    elif basis != "€/m":
        hinweise.append("nicht in €/m umrechenbar (ohne Zuordnung kein Metergewicht)" if basis == "€/kg"
                        else "Stangenlänge fehlt")
    if menge_m and je_m is not None:
        wert = je_m * menge_m
        out["bestellwert"] = wert
        zusatz = 0.0
        fracht, frei = _n(lief.get("fracht")) or 0, _n(lief.get("frei_ab"))
        if fracht and not (frei and wert >= frei):
            zusatz += fracht
        if _n(lief.get("mindermenge_bis")) and wert < _n(lief.get("mindermenge_bis")):
            zusatz += _n(lief.get("mindermenge_zuschlag")) or 0
        zusatz += (_n(lief.get("verpackung")) or 0) + (_n(lief.get("bearbeitung")) or 0)
        out["zusatz"] = zusatz
        out["einstand_je_m"] = je_m + zusatz / menge_m
        mind = _n(e.get("mindestmenge"))
        einheit = str(e.get("mengeneinheit") or "").lower()
        if mind:
            menge_e = {"m": menge_m, "kg": menge_m * kg if kg else None,
                       "stange": menge_m / (laenge / 1000) if laenge else None}.get(
                einheit if einheit in ("m", "kg") else "stange")
            if menge_e is not None and menge_e + 1e-9 < mind:
                hinweise.append(f"unter Mindestmenge {mind:g} {e.get('mengeneinheit') or 'Stangen'}")
    return out


def alter_tage(e, heute=None):
    t = _zeit(e.get("abruf") or e.get("seit"))
    if t is None:
        return None
    return ((heute or datetime.datetime.now()) - t).total_seconds() / 86400


def veraltet(e, tage=VERALTET_TAGE, heute=None):
    """True, wenn der letzte Abruf älter als tage ist oder die Gültigkeit abgelaufen ist."""
    heute = heute or datetime.datetime.now()
    a = alter_tage(e, heute)
    g = _datum(e.get("gueltig_bis"))
    return (a is not None and a > tage) or (g is not None and g < heute.date())


# ------------------------------------------------------------------ Speichern
def lieferant(db, name):
    return next((z for z in db.zeilen(LIEFERANTEN.name) if z.get("name") == name), None)


def lieferanten(db, nur_aktiv=False):
    return [z for z in db.zeilen(LIEFERANTEN.name) if not nur_aktiv or ja(z.get("aktiv") or "ja")]


def bestaetigungen(db):
    return {(z.get("lieferant"), z.get("kennung")): z for z in db.zeilen(ZUORDNUNG.name)}


def aktuelle(db, lieferant_name=None):
    return [z for z in db.zeilen(PREISE.name) if z.get("status") != ABGELOEST
            and (lieferant_name is None or z.get("lieferant") == lieferant_name)]


VERGLEICHSFELDER = ("preis", "basis", "staffel", "brutto", "preisart", "laenge")


def _preisgleich(alt, neu):
    for f in VERGLEICHSFELDER:
        a, b = alt.get(f), neu.get(f)
        if f in ("preis", "laenge"):
            if (_n(a) is None) != (_n(b) is None) or (_n(a) is not None and abs(_n(a) - _n(b)) > 1e-9):
                return False
        elif str(a or "") != str(b or ""):
            return False
    return True


FELDER = tuple(f.name for f in PREISE.felder)


def eintragen(db, lieferant_name, e, quelle, k, zeit=None, benutzer=None, bestaetigt=None):
    """Einen abgerufenen Preis speichern. Ergebnis ('neu' | 'geändert' | 'gleich', Zeilen-ID). Gleicher Preis: nur
    Abrufzeit, Verfügbarkeit, Lieferzeit und Gültigkeit aktualisieren; anderer Preis: alten Stand ablösen, neuen mit
    Änderung in % anlegen. ValueError ohne Preis bzw. Preisbasis (wird nie als Preis gespeichert)."""
    zeit = zeit or jetzt()
    preis = _n(e.get("preis"))
    if preis is None or preis <= 0 or e.get("basis") not in BASEN:
        raise ValueError("ohne Preis oder Preisbasis")
    kenn = kennung(e)
    if not kenn:
        raise ValueError("ohne Artikelnummer und Bezeichnung")
    if bestaetigt is None:
        bestaetigt = bestaetigungen(db).get((lieferant_name, kenn))
    zu = zuordnen(e, k, bestaetigt)
    werte = {f: e.get(f) for f in FELDER if f in e and e.get(f) not in (None, "")}
    werte.update(lieferant=lieferant_name, kennung=kenn, preis=preis, abruf=zeit, quelle=quelle, status=AKTUELL,
                 profil_id=zu["profil_id"], werkstoff_id=zu["werkstoff_id"], zuordnung=zu["zuordnung"],
                 zuordnung_grund=zu["grund"], erfasst_von=benutzer or e.get("erfasst_von"))
    werte.setdefault("brutto", "nein")
    werte.setdefault("preisart", "Kundenpreis")
    werte.setdefault("waehrung", "EUR")
    zl = zerlegen(" ".join(str(e.get(f) or "") for f in ("bezeichnung", "abmessung")))   # Maße für die Suche
    for f in ("form", "a", "b", "wand", "laenge", "oberflaeche"):
        if werte.get(f) in (None, "") and zl.get(f) not in (None, ""):
            werte[f] = zl[f]
    for f in ("a", "b", "wand", "laenge", "mindestmenge"):
        if f in werte:
            werte[f] = _n(werte[f])
    if "lieferzeit" in werte:
        werte["lieferzeit"] = int(_n(werte["lieferzeit"]) or 0) or None
    alt = next((z for z in aktuelle(db, lieferant_name) if z.get("kennung") == kenn), None)
    if alt is not None and _preisgleich(alt, werte):
        for f in ("abruf", "verfuegbarkeit", "lieferzeit", "gueltig_bis", "quelle", "profil_id", "werkstoff_id",
                  "zuordnung", "zuordnung_grund", "mindestmenge", "ve"):
            if f in werte and werte[f] != alt.get(f):
                db.aendern(PREISE.name, alt["id"], f, werte[f])
        return "gleich", alt["id"]
    if alt is not None:
        db.aendern(PREISE.name, alt["id"], "status", ABGELOEST)
        a_m, n_m = _vergleichspreis(alt, k), _vergleichspreis(werte, k)
        if a_m and n_m:
            werte["aenderung"] = round(100 * (n_m - a_m) / a_m, 2)
    # Preis seit: Abrufzeit, eindeutig je Artikel (zwei Stände in derselben Sekunde: mit Mikrosekunden)
    werte["seit"] = zeit if len(str(zeit)) > 19 else f"{zeit}.{datetime.datetime.now():%f}"
    i = db.neu(PREISE.name, werte)
    return ("geändert" if alt is not None else "neu"), i


def _vergleichspreis(e, k):
    """Preis eines Stands in €/m (für die Änderung in %), sonst der reine Preis bei gleicher Basis."""
    n = normalisieren(e, k)
    return n["je_m"] or n["netto"]


def zuordnung_bestaetigen(db, preis_id, profil_id, werkstoff_id, von=None, k=None):
    """Zuordnung eines Lieferantenartikels bestätigen (auch „gehört zu keinem“ mit leeren IDs); gilt für alle
    Stände dieses Artikels und künftige Abrufe."""
    z = next(r for r in db.zeilen(PREISE.name) if r["id"] == preis_id)
    alt = bestaetigungen(db).get((z["lieferant"], z["kennung"]))
    werte = dict(lieferant=z["lieferant"], kennung=z["kennung"], profil_id=profil_id or None,
                 werkstoff_id=werkstoff_id or None, von=von, datum=datetime.date.today().isoformat())
    if alt:
        for f, w in werte.items():
            db.aendern(ZUORDNUNG.name, alt["id"], f, w)
    else:
        db.neu(ZUORDNUNG.name, werte)
    zu = BESTAETIGT if profil_id and werkstoff_id else KEINE
    for r in db.zeilen(PREISE.name):
        if r["lieferant"] == z["lieferant"] and r["kennung"] == z["kennung"]:
            db.aendern(PREISE.name, r["id"], "profil_id", profil_id or None)
            db.aendern(PREISE.name, r["id"], "werkstoff_id", werkstoff_id or None)
            db.aendern(PREISE.name, r["id"], "zuordnung", zu)
            db.aendern(PREISE.name, r["id"], "zuordnung_grund", f"bestätigt von {von or '?'}")


# ------------------------------------------------------------------ Suche, Vergleich
def passt(z, suche):
    """Treffer der Suche (dict mit form, werkstoff_id, a, b, wand, laenge, oberflaeche, hersteller, artikelnr, text):
    jedes angegebene Feld muss genau passen (Maße auf 1/1000 mm)."""
    for f in ("form", "werkstoff_id", "profil_id"):
        if suche.get(f) and z.get(f) != suche[f]:
            return False
    for f in ("a", "b", "wand", "laenge"):
        if suche.get(f) not in (None, "") and not _gleich(z.get(f), suche[f]):
            if f == "b" and z.get("form") in ("Quadratrohr",) and _gleich(z.get("a"), suche[f]):
                continue
            return False
    for f in ("oberflaeche", "hersteller", "artikelnr"):
        if suche.get(f) and str(suche[f]).casefold() not in str(z.get(f) or "").casefold():
            return False
    if suche.get("text"):
        alles = " ".join(str(z.get(f) or "") for f in ("bezeichnung", "artikelnr", "werkstoff", "profil_id")).casefold()
        if not all(w in alles for w in str(suche["text"]).casefold().split()):
            return False
    return True


def suchen(db, suche, k):
    """Aktuelle Preisstände, die zur Suche passen. Ist nur profil_id + werkstoff_id gesucht, zählen nur sichere bzw.
    bestätigte Zuordnungen; Maße allein finden auch 'prüfen'-Zeilen (dann ohne Übernahme)."""
    out = []
    for z in aktuelle(db):
        if z.get("zuordnung") == KEINE and (suche.get("profil_id") or suche.get("werkstoff_id")):
            continue
        if passt(z, suche):
            out.append(z)
    return out


def vergleich(db, k, suche, menge_m=None, stangenlaenge=None, tage=None, heute=None):
    """Preisvergleich: [dict(zeile, norm, lieferant, veraltet, alter, uebernehmbar, rang, bester)] sortiert nach
    Einstand €/m (ohne Menge nach €/m); Zeilen ohne €/m ans Ende. Bester = günstigster übernehmbarer Preis."""
    tage = VERALTET_TAGE if tage is None else tage
    lief = {z["name"]: z for z in lieferanten(db)}
    zeilen = []
    for z in suchen(db, suche, k):
        n = normalisieren(z, k, lief.get(z["lieferant"]), menge_m, stangenlaenge)
        zeilen.append(dict(zeile=z, norm=n, lieferant=lief.get(z["lieferant"]) or {}, veraltet=veraltet(z, tage, heute),
                           alter=alter_tage(z, heute), uebernehmbar=z.get("zuordnung") in UEBERNEHMBAR
                           and n["je_m"] is not None, rang=None, bester=False))

    def wert(r):
        n = r["norm"]
        v = n["einstand_je_m"] if n["einstand_je_m"] is not None else n["je_m"]
        return (v is None, not r["uebernehmbar"], v or 0, r["zeile"].get("lieferant") or "")
    zeilen.sort(key=wert)
    rang = 0
    for r in zeilen:
        if r["norm"]["je_m"] is not None:
            rang += 1
            r["rang"] = rang
    beste = next((r for r in zeilen if r["uebernehmbar"]), None)
    if beste:
        beste["bester"] = True
    return zeilen


def stammdaten_je_m(db, k, profil_id, werkstoff_id):
    """Meterpreis laut Materialstamm (Preise, sonst Tonnenpreis) für den Vergleich oder None."""
    from .stammdaten import preis_je_m_automatisch
    z = next((r for r in db.zeilen("preise") if r.get("profil_id") == profil_id
              and r.get("werkstoff_id") == werkstoff_id), None)
    if z:
        e = dict(z, laenge=z.get("lieferlaenge"))
        n = normalisieren(e, k)
        if n["je_m"] is not None:
            return n["je_m"], f"Stammdaten Preise ({z.get('lieferant') or 'ohne Lieferant'}, ab {z.get('gueltig_ab') or '?'})"
    w = preis_je_m_automatisch(dict(profil_id=profil_id, werkstoff_id=werkstoff_id), k)
    return (w, "Tonnenpreis des Werkstoffs") if w else (None, "")


# ------------------------------------------------------------------ Historie, Auswertung
def verlauf(db, k, profil_id, werkstoff_id, lieferant_name=None):
    """Alle Stände (auch abgelöste) einer Abmessung, älteste zuerst: [dict(datum, lieferant, je_m, zeile)]."""
    out = []
    for z in db.zeilen(PREISE.name):
        if z.get("profil_id") != profil_id or z.get("werkstoff_id") != werkstoff_id:
            continue
        if z.get("zuordnung") not in UEBERNEHMBAR or (lieferant_name and z.get("lieferant") != lieferant_name):
            continue
        n = normalisieren(z, k, lieferant(db, z["lieferant"]))
        if n["je_m"] is None:
            continue
        out.append(dict(datum=str(z.get("seit") or "")[:10], lieferant=z.get("lieferant"), je_m=n["je_m"], zeile=z))
    return sorted(out, key=lambda r: (r["datum"], r["zeile"]["id"]))


def kennzahlen(db, k, profil_id, werkstoff_id):
    """dict(tiefst, tiefst_datum, tiefst_lieferant, aktuell (günstigster aktueller €/m), letzter_einkauf, letzter_text)."""
    from . import bestellpreis
    v = verlauf(db, k, profil_id, werkstoff_id)
    out = dict(tiefst=None, tiefst_datum=None, tiefst_lieferant=None, aktuell=None, letzter_einkauf=None,
               letzter_text="")
    if v:
        t = min(v, key=lambda r: r["je_m"])
        out.update(tiefst=t["je_m"], tiefst_datum=t["datum"], tiefst_lieferant=t["lieferant"])
        akt = [r["je_m"] for r in v if r["zeile"].get("status") != ABGELOEST]
        out["aktuell"] = min(akt) if akt else None
    try:
        le = bestellpreis.letzte(db, k).get((profil_id, werkstoff_id))
    except Exception:
        le = None
    if le:
        out.update(letzter_einkauf=le["je_m"], letzter_text=f"{le['lieferant']} am {le['datum']} (Angebot {le['nummer']})")
    return out


def auffaellige(db, schwelle=None, tage=30, heute=None):
    """Preisstände der letzten tage Tage mit einer Änderung über der Schwelle (Einstellung online_sprung, %)."""
    if schwelle is None:
        schwelle = _n(db.einstellung("online_sprung"))
        schwelle = SPRUNG if schwelle is None else schwelle
    if not schwelle:
        return []
    heute = heute or datetime.datetime.now()
    out = []
    for z in db.zeilen(PREISE.name):
        t = _zeit(z.get("seit"))
        if z.get("aenderung") is not None and abs(z["aenderung"]) >= schwelle and t and (heute - t).days <= tage:
            out.append(z)
    return sorted(out, key=lambda z: str(z.get("seit")), reverse=True)


# ------------------------------------------------------------------ Übernahme in die Stammdaten
def uebernehmen(db, k, preis_id, menge_m=None, einstand=False, sichern=True, heute=None):
    """Online-Preis in die Stammdaten Preise (Profil + Werkstoff) schreiben. Nur sichere/bestätigte Zuordnung mit
    Preis. Netto nach Staffel und Rabatt in der Basis des Lieferanten; einstand=True: Einstand €/m für menge_m (mit
    Fracht und Zuschlägen). Vorher eine Datensicherung (sichern=True). Bereits festgeschriebene Angebote und Aufträge
    ändern sich nicht (preisbasis); der Preiswächter meldet offene Angebote mit Abweichung. Ergebnis: ID der Zeile in
    'preise'. ValueError, wenn nicht übernehmbar."""
    heute = heute or datetime.date.today()
    z = next((r for r in db.zeilen(PREISE.name) if r["id"] == preis_id), None)
    if z is None:
        raise ValueError("Preis nicht gefunden")
    if z.get("zuordnung") not in UEBERNEHMBAR or not z.get("profil_id") or not z.get("werkstoff_id"):
        raise ValueError("Zuordnung nicht sicher: bitte zuerst „Zuordnung bestätigen …“")
    lief = lieferant(db, z["lieferant"]) or {}
    n = normalisieren(z, k, lief, menge_m)
    if n["netto"] is None:
        raise ValueError("Kein Preis")
    if einstand:
        if n["einstand_je_m"] is None:
            raise ValueError("Einstand €/m nicht berechenbar (Menge oder Metergewicht fehlt)")
        basis, preis = "€/m", n["einstand_je_m"]
    else:
        basis, preis = z["basis"], n["netto"]
    if sichern:
        db.sicherung(zusatz="vor_Onlinepreis")
    abruf = str(z.get("abruf") or z.get("seit") or "")[:16].replace("T", " ")
    werte = dict(basis=basis, preis=round(preis, 4), gueltig_ab=heute.isoformat(), lieferant=z["lieferant"],
                 bemerkung=f"Online-Preis ({z.get('quelle') or '?'}, Abruf {abruf}"
                           f"{', Einstand für ' + format(menge_m, '.0f') + ' m' if einstand else ''})")
    if basis == "€/Stange" and n["laenge_mm"]:
        werte["lieferlaenge"] = int(n["laenge_mm"])
    alt = next((r for r in db.zeilen("preise") if r.get("profil_id") == z["profil_id"]
                and r.get("werkstoff_id") == z["werkstoff_id"]), None)
    if alt:
        for f, w in werte.items():
            db.aendern("preise", alt["id"], f, w)
        return alt["id"]
    return db.neu("preise", dict(werte, profil_id=z["profil_id"], werkstoff_id=z["werkstoff_id"]))


# ------------------------------------------------------------------ Protokoll, Doppelabruf
def protokollieren(db, lieferant_name, weg, anlass, ergebnis, anzahl=0, neu=0, geaendert=0, meldung="", dauer=0.0):
    db.con.execute(f"INSERT INTO {ABRUFE} (zeit, lieferant, weg, anlass, ergebnis, anzahl, neu, geaendert, meldung, "
                   "dauer, benutzer) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (jetzt(), lieferant_name, weg, anlass, ergebnis, anzahl, neu, geaendert, str(meldung)[:2000],
                    round(dauer, 2), db.einstellung("benutzer_kuerzel") or ""))
    db.con.commit()


def protokoll(db, lieferant_name=None, anzahl=200):
    sql, w = f"SELECT zeit, lieferant, weg, anlass, ergebnis, anzahl, neu, geaendert, meldung, dauer, benutzer " \
             f"FROM {ABRUFE}", []
    if lieferant_name:
        sql += " WHERE lieferant=?"
        w.append(lieferant_name)
    namen = ("zeit", "lieferant", "weg", "anlass", "ergebnis", "anzahl", "neu", "geaendert", "meldung", "dauer",
             "benutzer")
    return [dict(zip(namen, r)) for r in db.con.execute(sql + f" ORDER BY id DESC LIMIT {int(anzahl)}", w)]


def letzter_abruf(db, lieferant_name, nur_ok=True):
    sql = f"SELECT zeit FROM {ABRUFE} WHERE lieferant=?" + (" AND ergebnis='ok'" if nur_ok else "") + \
        " ORDER BY id DESC LIMIT 1"
    r = db.con.execute(sql, (lieferant_name,)).fetchone()
    return _zeit(r[0]) if r else None


def faellig(db, lief, anlass, heute=None):
    """Soll für den Lieferanten jetzt automatisch abgerufen werden? Nur Wege ohne Bedienung (Preisliste, OCI mit
    Hintergrundsuche), nach Aktualisierung (täglich 24 h, wöchentlich 7 Tage, beim Öffnen) und nie öfter als der
    Mindestabstand (Vorgabe 12 h, gegen unnötige Anfragen und API-Limits)."""
    heute = heute or datetime.datetime.now()
    if not ja(lief.get("aktiv") or "ja"):
        return False
    weg = lief.get("weg")
    if weg == "Preisliste":
        if not lief.get("preisliste_ordner"):
            return False
    elif not (weg == "OCI-Punchout" and ja(lief.get("oci_hintergrund")) and lief.get("oci_adresse")):
        return False
    art = lief.get("aktualisierung") or "manuell"
    letzter = letzter_abruf(db, lief["name"], nur_ok=False)
    abstand = _n(lief.get("min_abstand_h"))
    abstand = 12 if abstand is None else abstand
    if letzter and (heute - letzter).total_seconds() < abstand * 3600 and weg != "Preisliste":
        return False
    if art == "beim Öffnen":
        return anlass == "oeffnen" and (letzter is None or (heute - letzter).total_seconds() >= 600)
    tage = {"täglich": 1, "wöchentlich": 7}.get(art)
    if tage is None or anlass not in ("start", "uhr"):
        return False
    ok = letzter_abruf(db, lief["name"])
    return ok is None or (heute - ok).total_seconds() >= tage * 86400 - 60


def verwendete(db, monate=6, dazu=()):
    """{(profil_id, werkstoff_id)} der Positionen in Angeboten der letzten monate Monate (für „nur verwendete
    Materialien“), dazu weitere Paare."""
    seit = (datetime.date.today() - datetime.timedelta(days=int(monate * 30.5))).isoformat()
    out = set(dazu)
    for p, w in db.con.execute("SELECT DISTINCT p.profil_id, p.werkstoff_id FROM positionen p JOIN angebote a "
                               "ON a.id = p.angebot_id WHERE COALESCE(a.datum, a.angelegt, '') >= ?", (seit,)):
        if p and w:
            out.add((p, w))
    return out


def datei_kennung(roh):
    return hashlib.sha256(roh).hexdigest()


def datei_bekannt(db, kennung_):
    """Schutz vor doppeltem Import: Prüfsummen schon gelesener Preislisten (Einstellung online_dateien, geteilt)."""
    return kennung_ in (db.einstellung("online_dateien") or {})


def datei_merken(db, kennung_, name):
    d = dict(db.einstellung("online_dateien") or {})
    d[kennung_] = dict(name=name, zeit=jetzt())
    if len(d) > 500:                       # nur die letzten 500
        d = dict(sorted(d.items(), key=lambda kv: kv[1].get("zeit", ""))[-500:])
    db.einstellung_setzen("online_dateien", d)


def spalten_laden(lief):
    try:
        return json.loads(lief.get("spalten") or "{}") or {}
    except (TypeError, ValueError):
        return {}
