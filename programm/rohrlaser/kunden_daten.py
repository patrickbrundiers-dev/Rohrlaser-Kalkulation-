"""Kundenverwaltung (Patrick 23.11.2026, Master-Auftrag „Kundenverwaltung mit eigenem Menü“). Ohne Qt.

Grundsatz: keine Parallelstruktur. Der Kundenstamm bleibt die Tabelle kunden (eine Zeile je Kunde, Schlüssel
Kundennummer); sie bekommt die neuen Felder der Eingabemaske (Firmenzusatz, Rechtsform, Kundentyp, Branche, Website,
Status, Kundengruppe, Ort, Bundesland, USt-ID, Steuernummer, Währung, Kreditlimit, Zahlungsbedingungen,
Preisvereinbarung, interne Notizen, Archiv). Rabatt, Gewinn, Mindestwert und Frachtfrei bleiben in kundenvorgaben,
weil das Angebot sie dort schon liest (kundenvorgabe.kopfwerte). Neu sind drei Tabellen, verknüpft über die
Kundennummer (wird sie umbenannt, ziehen sie mit, datenbank.ALLE_VERWEISE):

- kunden_ansprechpartner: mehrere Ansprechpartner je Kunde mit Rollen (Haupt, Einkauf, Technik, Buchhaltung).
  Der Hauptansprechpartner steht zusätzlich wie bisher in kunden.ansprechpartner (PDF „z. Hd.“, Aufträge, Mails).
- kunden_adressen: Rechnungsadresse, Lieferadressen (mehrere), Standorte.
- kunden_historie: Änderungsverfolgung (Feld alt → neu, wer, wann), Kontakte und Notizen; es wird nur angehängt.

Alle drei werden wie die übrigen Stammdaten über den gemeinsamen Ordner mit den Kollegen abgeglichen (teilen.GETEILT,
feste Kennung uid je Zeile). Speichern läuft je Vorgang in einer Transaktion; jedes geänderte Feld wird gegen den
angezeigten Wert geprüft (optimistische Sperre, Datenbank._konflikt_pruefen, unter PostgreSQL mit Zeilensperre):
hat ein Kollege dasselbe Feld inzwischen geändert, wird nichts geschrieben (AenderungsKonflikt).

Kennzahlen (Übersicht, Profil) kommen nur aus echten Daten: Angebote (Tabelle angebote, ohne ersetzte Fassungen,
auch die der Kollegen), Aufträge (auftrag_kopf), Umsatz = Verkaufspreis netto der beauftragten Angebote.
"""
import csv
import datetime
import io
import json
import re
import shutil
import unicodedata
from pathlib import Path

from . import protokoll
from .stammdaten import Feld, Tabelle
from .zahlen import jetzt_text as _jetzt  # Audit 26.11.2026 R-01: gemeinsame Hilfsfunktion

STATUS = ("Aktiv", "Inaktiv", "Gesperrt")
AKTIV, INAKTIV, GESPERRT = STATUS
KUNDENTYPEN = ("Firma", "Privatkunde", "Händler", "Lieferant")
WAEHRUNGEN = ("EUR", "CHF", "USD", "GBP", "PLN", "CZK")
ROLLEN = (("haupt", "Hauptansprechpartner"), ("einkauf", "Einkauf"), ("technik", "Technik"),
          ("buchhaltung", "Buchhaltung"))
ROLLE_TEXT = dict(ROLLEN)
RECHNUNG, LIEFERUNG, STANDORT = "Rechnungsadresse", "Lieferadresse", "Standort"
ADRESS_ARTEN = (RECHNUNG, LIEFERUNG, STANDORT)
NUMMERN_ORDNER = "Kundennummern"        # Reservierung im gemeinsamen Ordner (wie AU-Nummern)
NUMMER_START = 10001
DOKUMENTE_ORDNER = "Kundendokumente"    # je Kunde ein Unterordner <Kundennummer> in der Ablage
MIGRATION_STAND = "2026-11-23"          # Einstellung kunden_crm_stand: einmalige Übernahme der Altdaten

# Historie: Arten
H_ANGELEGT, H_GEAENDERT, H_ARCHIV, H_KONTAKT, H_NOTIZ, H_PERSON, H_ADRESSE, H_DOKUMENT, H_ZUSAMMEN = (
    "Angelegt", "Geändert", "Archiv", "Kontakt", "Notiz", "Ansprechpartner", "Adresse", "Dokument", "Zusammengeführt")
KONTAKT_ARTEN = ("Telefonat", "E-Mail", "Besuch", "Besprechung", "Sonstiges")

ANSPRECHPARTNER = Tabelle(
    "kunden_ansprechpartner", "Ansprechpartner",
    (Feld("kundennr", "Kunde", pflicht=True, breite=100),
     Feld("anrede", "Anrede", breite=60),
     Feld("vorname", "Vorname", breite=110),
     Feld("nachname", "Nachname", pflicht=True, breite=130),
     Feld("position", "Position", breite=120),
     Feld("abteilung", "Abteilung", breite=110),
     Feld("telefon", "Telefon", breite=110),
     Feld("mobil", "Mobil", breite=110),
     Feld("email", "E-Mail", breite=170),
     Feld("zustaendigkeit", "Zuständigkeit", breite=150),
     Feld("haupt", "Hauptansprechpartner", "auswahl", auswahl="janein", breite=70),
     Feld("einkauf", "Einkauf", "auswahl", auswahl="janein", breite=60),
     Feld("technik", "Technik", "auswahl", auswahl="janein", breite=60),
     Feld("buchhaltung", "Buchhaltung", "auswahl", auswahl="janein", breite=70),
     Feld("aktiv", "Aktiv", "auswahl", auswahl="janein", breite=50),
     Feld("bemerkung", "Bemerkung", breite=160),
     Feld("geaendert", "Geändert", breite=130)),
    (),
    "Ansprechpartner je Kunde (Kundenverwaltung, kunden_daten.py).")

ADRESSEN = Tabelle(
    "kunden_adressen", "Kundenadressen",
    (Feld("kundennr", "Kunde", pflicht=True, breite=100),
     Feld("art", "Art", breite=110),                  # Rechnungsadresse | Lieferadresse | Standort
     Feld("bezeichnung", "Bezeichnung", breite=140),  # z. B. „Werk 2“, „Baustelle Halle 3“
     Feld("name", "Name / Firma", breite=170),
     Feld("zusatz", "Zusatz", breite=130),
     Feld("strasse", "Straße", breite=160),
     Feld("plz", "PLZ", breite=60),
     Feld("ort", "Ort", breite=120),
     Feld("land", "Land", breite=50),
     Feld("standard", "Standard", "auswahl", auswahl="janein", breite=60),
     Feld("bemerkung", "Bemerkung", breite=160),
     Feld("geaendert", "Geändert", breite=130)),
    (),
    "Rechnungs-, Liefer- und Standortadressen je Kunde (Kundenverwaltung, kunden_daten.py).")

HISTORIE = Tabelle(
    "kunden_historie", "Kundenhistorie",
    (Feld("kundennr", "Kunde", pflicht=True, breite=100),
     Feld("zeit", "Zeit", breite=130),
     Feld("wer", "Wer", breite=60),
     Feld("art", "Art", breite=100),
     Feld("feld", "Feld", breite=110),
     Feld("alt", "Alt", breite=160),
     Feld("neu", "Neu", breite=160),
     Feld("text", "Text", breite=240)),
    (),
    "Änderungen, Kontakte und Notizen je Kunde; nur angehängt (Kundenverwaltung, kunden_daten.py).")

TABELLEN = (ANSPRECHPARTNER, ADRESSEN, HISTORIE)

# Felder der Eingabemaske je Bereich (Name in kunden, Titel); Konditionen kommen aus kundenvorgaben
ALLGEMEIN = (("kundennr", "Kundennummer"), ("name", "Firmenname"), ("firmenzusatz", "Firmenzusatz"),
             ("rechtsform", "Rechtsform"), ("kundentyp", "Kundentyp"), ("branche", "Branche"),
             ("website", "Website"), ("status", "Kundenstatus"), ("kundengruppe", "Kundengruppe"),
             ("zustaendig", "Zuständig (Kürzel)"))
ANSCHRIFT = (("strasse", "Straße und Hausnummer"), ("plz", "PLZ"), ("ort", "Ort"), ("bundesland", "Bundesland"),
             ("land", "Land"))
KONTAKT = (("telefon", "Telefon (Zentrale)"), ("email", "E-Mail (allgemein)"))
KAUFMAENNISCH = (("zahlungsziel", "Zahlungsziel netto [Tage]"), ("skonto", "Skonto [%]"),
                 ("skonto_tage", "Skontofrist [Tage]"), ("zahlungsbedingung", "Zahlungsbedingungen"),
                 ("ust_id", "Umsatzsteuer-ID"), ("steuernr", "Steuernummer"), ("waehrung", "Währung"),
                 ("kreditlimit", "Kreditlimit [€]"), ("lieferbedingung", "Lieferbedingung"))
VORGABEN = (("rabatt", "Kundenrabatt [%]"), ("gewinn", "Gewinn [%]"), ("rabatt_staffel", "Rabattstaffel"),
            ("mindestwert", "Mindestauftragswert [€]"), ("frachtfrei_ab", "Frachtfrei ab [€]"))
NOTIZEN = (("preisvereinbarung", "Individuelle Preisvereinbarungen"), ("notizen", "Interne Kundennotizen"),
           ("hinweis", "Kundenhinweis (im Angebot)"), ("hinweis_werkstatt", "Hinweis auf Werkstattpapiere"))
TITEL = dict(ALLGEMEIN + ANSCHRIFT + KONTAKT + KAUFMAENNISCH + VORGABEN + NOTIZEN)
ZAHLEN = {"zahlungsziel": int, "skonto_tage": int, "skonto": float, "kreditlimit": float, "rabatt": float,
          "gewinn": float, "mindestwert": float, "frachtfrei_ab": float}
GRENZEN = {"zahlungsziel": (0, 365), "skonto_tage": (0, 365), "skonto": (0, 20), "kreditlimit": (0, 1e9),
           "rabatt": (0, 50), "gewinn": (0, 500), "mindestwert": (0, 1e7), "frachtfrei_ab": (0, 1e7)}
VORGABE_FELDER = tuple(n for n, _ in VORGABEN)

# Rechtsformen und Füllwörter für den Namensvergleich (Dubletten, Mail-Erkennung): „Muster GmbH“, „Muster Gesellschaft
# mbH“ und „Muster GmbH & Co. KG“ sind derselbe Kern „muster“
RECHTSFORMEN = ("gesellschaft mit beschraenkter haftung", "gesellschaft mbh", "gmbh & co. kg", "gmbh & co kg",
                "gmbh u. co. kg", "gmbh und co. kg", "ug (haftungsbeschraenkt)", "ug haftungsbeschraenkt",
                "e. k.", "e.k.", "e.kfm.", "gmbh", "mbh", "ag", "kg", "ohg", "gbr", "ug", "se", "ltd", "inc", "llc",
                "s.a.", "sa", "sarl", "srl", "s.r.l.", "b.v.", "bv", "sp. z o.o.", "co.", "co", "& co", "und co",
                "gruppe", "group", "holding", "e.v.", "ev")
_RF = sorted(RECHTSFORMEN, key=len, reverse=True)


class KundenFehler(ValueError):
    """Eingabe oder Vorgang nicht möglich (Text für den Benutzer)."""


# ------------------------------------------------------------------ Hilfen
def _wer(db):
    from . import teilen
    try:
        return teilen.kuerzel(db) or ""
    except Exception:
        return ""


def _t(w):
    return "" if w is None else str(w).strip()


def _leer(w):
    return w is None or (isinstance(w, str) and not w.strip())


def _gleich(a, b):
    if _leer(a) and _leer(b):
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return _t(a) == _t(b)


def _schreibbar(db):
    if getattr(db, "nur_lesen", ""):
        from .datenbank import Lesemodus
        raise Lesemodus(f"Lesemodus – {db.nur_lesen}. Ändern ist erst mit gültiger Lizenz möglich.")


def falten(text):
    """Vergleichsform: Kleinbuchstaben, Umlaute ausgeschrieben, Akzente weg, Leerraum einfach."""
    t = str(text or "").lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return " ".join(t.split())


def namenskern(name):
    """Firmenname ohne Rechtsform und Sonderzeichen: 'Muster Gesellschaft mbH' -> 'muster',
    'Beispiel Metallbau GmbH & Co. KG' -> 'beispiel metallbau'."""
    t = " " + falten(name).replace("+", " & ") + " "
    geaendert = True
    while geaendert:
        geaendert = False
        for rf in _RF:
            neu = re.sub(r"(?<![0-9a-z])" + re.escape(rf) + r"(?![0-9a-z])", " ", t)
            if neu != t:
                t, geaendert = neu, True
    t = re.sub(r"[^0-9a-z]+", " ", t)
    return " ".join(t.split())


def _ziffern(t):
    z = re.sub(r"\D", "", str(t or ""))
    if z.startswith("0049"):
        z = "0" + z[4:]
    elif z.startswith("49") and len(z) > 10:
        z = "0" + z[2:]
    return z


def _ust(t):
    return re.sub(r"[^0-9A-Z]", "", str(t or "").upper())


def _strasse(t):
    s = falten(t).replace("strasse", "str").replace("str.", "str")
    return re.sub(r"[^0-9a-z]", "", s)


def mails(text):
    from .mail import ADRESSE
    return [a.lower() for a in ADRESSE.findall(str(text or ""))]


def plz_ort_teilen(plz_ort):
    """'12345 Musterstadt' -> ('12345', 'Musterstadt'); ohne PLZ ('', Text)."""
    m = re.match(r"^\s*(?:[A-Z]{1,2}\s*-\s*)?(\d{4,5})\s+(.+?)\s*$", str(plz_ort or ""))
    return (m.group(1), m.group(2)) if m else ("", _t(plz_ort))


def plz_ort(plz, ort):
    return " ".join(x for x in (_t(plz), _t(ort)) if x)


def name_voll(p):
    return " ".join(x for x in (_t(p.get("vorname")), _t(p.get("nachname"))) if x)


def name_teilen(name):
    """'Max Mustermann' -> ('Max', 'Mustermann'); 'Herr Dr. Max Mustermann' ohne Anrede/Titel; ein Wort = Nachname."""
    teile = [x for x in re.split(r"\s+", _t(name)) if x]
    anrede = ""
    while teile and teile[0].rstrip(".").lower() in ("herr", "frau", "hr", "fr", "dr", "prof", "dipl.-ing", "ing"):
        if teile[0].rstrip(".").lower() in ("herr", "hr"):
            anrede = "Herr"
        elif teile[0].rstrip(".").lower() in ("frau", "fr"):
            anrede = "Frau"
        teile.pop(0)
    if not teile:
        return anrede, "", ""
    if len(teile) == 1:
        return anrede, "", teile[0]
    return anrede, " ".join(teile[:-1]), teile[-1]


# ------------------------------------------------------------------ Einrichtung und Übernahme der Altdaten
def migrieren(db):
    """Einmalig (Einstellung kunden_crm_stand): bestehende Kunden ohne Verlust ergänzen. PLZ und Ort aus 'PLZ Ort',
    Status Aktiv, Kundentyp Firma, Ansprechpartner aus kunden.ansprechpartner (mit Telefon/E-Mail des Kunden) als
    Hauptansprechpartner, abweichende Liefer-PLZ als Lieferadresse. Nichts wird überschrieben oder gelöscht.
    Ergebnis: dict mit Zählern."""
    con = db.con
    out = dict(kunden=0, ansprechpartner=0, adressen=0)
    if db.einstellung("kunden_crm_stand") == MIGRATION_STAND:
        return out
    jetzt = _jetzt()
    for k in [dict(r) for r in con.execute("SELECT * FROM kunden ORDER BY id")]:
        aend = {}
        if _leer(k.get("ort")) and not _leer(k.get("plz_ort")):
            p, o = plz_ort_teilen(k["plz_ort"])
            aend["ort"] = o
            if _leer(k.get("plz")) and p:
                aend["plz"] = p
        if _leer(k.get("status")):
            aend["status"] = AKTIV
        if _leer(k.get("kundentyp")):
            aend["kundentyp"] = "Firma"
        if _leer(k.get("angelegt")):
            aend["angelegt"] = jetzt
        if aend:
            con.execute(f'UPDATE kunden SET {", ".join(chr(34) + n + chr(34) + "=?" for n in aend)} WHERE id=?',
                        [*aend.values(), k["id"]])
            out["kunden"] += 1
        nr = k.get("kundennr")
        if _leer(nr):
            continue
        da = con.execute("SELECT COUNT(*) FROM kunden_ansprechpartner WHERE kundennr=?", (nr,)).fetchone()[0]
        if not da and not _leer(k.get("ansprechpartner")):
            anrede, vor, nach = name_teilen(k["ansprechpartner"])
            con.execute("INSERT INTO kunden_ansprechpartner (kundennr, anrede, vorname, nachname, telefon, email, "
                        "haupt, aktiv, geaendert, bemerkung) VALUES (?, ?, ?, ?, ?, ?, 'ja', 'ja', ?, ?)",
                        (nr, anrede, vor, nach or k["ansprechpartner"], k.get("telefon"),
                         (mails(k.get("email")) or [None])[0], jetzt, "aus dem bisherigen Kundenstamm übernommen"))
            out["ansprechpartner"] += 1
        da = con.execute("SELECT COUNT(*) FROM kunden_adressen WHERE kundennr=?", (nr,)).fetchone()[0]
        if not da and not _leer(k.get("liefer_plz")):
            con.execute("INSERT INTO kunden_adressen (kundennr, art, bezeichnung, plz, land, standard, geaendert, "
                        "bemerkung) VALUES (?, ?, ?, ?, ?, 'ja', ?, ?)",
                        (nr, LIEFERUNG, "Lieferanschrift", k["liefer_plz"], k.get("liefer_land") or "DE", jetzt,
                         "aus „Liefer-PLZ abweichend“ übernommen"))
            out["adressen"] += 1
    db._einstellung_schreiben("kunden_crm_stand", MIGRATION_STAND)
    return out


# ------------------------------------------------------------------ Lesen
def kunde(db, kundennr):
    if _leer(kundennr):
        return None
    r = db.con.execute("SELECT * FROM kunden WHERE kundennr=?", (str(kundennr),)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d.pop("uid", None)
    return d


def vorgaben(db, kundennr):
    r = db.con.execute("SELECT * FROM kundenvorgaben WHERE kundennr=?", (str(kundennr),)).fetchone()
    return dict(r) if r else {}


def ansprechpartner(db, kundennr, nur_aktiv=False):
    """Ansprechpartner des Kunden, Hauptansprechpartner zuerst. Jede Zeile mit uid (Verweis aus dem Angebot)."""
    out = [dict(r) for r in db.con.execute("SELECT * FROM kunden_ansprechpartner WHERE kundennr=? ORDER BY id",
                                           (str(kundennr),))]
    if nur_aktiv:
        out = [p for p in out if p.get("aktiv") != "nein"]
    out.sort(key=lambda p: (p.get("haupt") != "ja", p.get("aktiv") == "nein", name_voll(p).lower()))
    return out


def adressen(db, kundennr, art=None):
    out = [dict(r) for r in db.con.execute("SELECT * FROM kunden_adressen WHERE kundennr=? ORDER BY id",
                                           (str(kundennr),))]
    if art:
        out = [a for a in out if a.get("art") == art]
    out.sort(key=lambda a: (ADRESS_ARTEN.index(a["art"]) if a.get("art") in ADRESS_ARTEN else 9,
                            a.get("standard") != "ja", _t(a.get("bezeichnung")).lower()))
    return out


def adresse_zeilen(a, kunde_=None):
    """Anschriftzeilen einer Adresse (Name, Zusatz, Straße, PLZ Ort, Land außer DE); fehlt der Name, der Kunde."""
    name = _t(a.get("name")) or _t((kunde_ or {}).get("name"))
    land = _t(a.get("land")).upper()
    z = [name, _t(a.get("zusatz")), _t(a.get("strasse")), plz_ort(a.get("plz"), a.get("ort")),
         land if land and land != "DE" else ""]
    return [x for x in z if x]


def adresse_text(a, kunde_=None):
    return ", ".join(adresse_zeilen(a, kunde_))


def historie(db, kundennr, mit_vorgaengen=True):
    """Historie des Kunden (neueste zuerst): eigene Einträge, dazu (mit_vorgaengen) Angebote und Aufträge.
    [dict(zeit, wer, art, text, feld, alt, neu, quelle)]"""
    out = [dict(r, quelle="kunde") for r in db.con.execute(
        "SELECT zeit, wer, art, feld, alt, neu, text, uid FROM kunden_historie WHERE kundennr=?", (str(kundennr),))]
    if mit_vorgaengen:
        for a in angebote(db, kundennr):
            out.append(dict(zeit=a.get("angelegt") or a.get("datum") or "", wer=a.get("bearbeiter") or "",
                            art="Angebot", text=f"Angebot {a['nummer']} angelegt ({a.get('vorgang') or 'Entwurf'})",
                            feld="", alt="", neu="", quelle="angebot"))
            if a.get("vk_am") and a.get("vorgang") in ("Verschickt", "Beauftragt", "Abgelehnt"):
                out.append(dict(zeit=a["vk_am"], wer=a.get("bearbeiter") or "", art="Angebot",
                                text=f"Angebot {a['nummer']}: {a['vorgang']}", feld="", alt="", neu="",
                                quelle="angebot"))
        for au in auftraege(db, kundennr):
            out.append(dict(zeit=au.get("angelegt") or "", wer="", art="Auftrag",
                            text=f"Auftrag {au['nummer']} ({au.get('status') or ''})", feld="", alt="", neu="",
                            quelle="auftrag"))
    out.sort(key=lambda e: str(e.get("zeit") or ""), reverse=True)
    return out


def _historie(db, kundennr, art, text="", feld="", alt=None, neu=None, zeit=None):
    db.con.execute("INSERT INTO kunden_historie (kundennr, zeit, wer, art, feld, alt, neu, text) VALUES "
                   "(?, ?, ?, ?, ?, ?, ?, ?)", (str(kundennr), zeit or _jetzt(), _wer(db), art, feld,
                                                None if alt is None else str(alt), None if neu is None else str(neu),
                                                text))


def eintrag(db, kundennr, art, text, zeit=None):
    """Kontakt oder Notiz in die Historie (Telefonat, Besuch …)."""
    _schreibbar(db)
    if not kunde(db, kundennr):
        raise KundenFehler(f"Kunde {kundennr} gibt es nicht.")
    if not _t(text):
        raise KundenFehler("Bitte einen Text eingeben.")
    with db.con:
        _historie(db, kundennr, art, _t(text), zeit=zeit)


def angebote(db, kundennr):
    """Angebote des Kunden (neueste zuerst), ohne ersetzte Fassungen; auch die der Kollegen."""
    return [dict(r) for r in db.con.execute(
        "SELECT id, nummer, datum, vorgang, vk_netto, vk_am, bearbeiter, fremd, kundenreferenz, projekt, angelegt, "
        "geaendert, auftragsnr FROM angebote WHERE kundennr=? AND COALESCE(ersetzt_durch, '')='' "
        "ORDER BY datum DESC, nummer DESC", (str(kundennr),))]


def _auftrag_zeilen(db):
    out = []
    for uid, nummer, status, daten, angelegt in db.con.execute(
            "SELECT uid, nummer, status, daten, angelegt FROM auftrag_kopf").fetchall():
        try:
            k = json.loads(daten) if daten else {}
        except (TypeError, ValueError):
            k = {}
        out.append(dict(uid=uid, nummer=nummer, status=status, angelegt=angelegt, kundennr=_t(k.get("kundennr")),
                        kunde=k.get("kunde") or "", auftragsdatum=k.get("auftragsdatum") or "",
                        liefertermin=k.get("liefertermin") or "", projekt=k.get("projekt") or "",
                        bestellnr=k.get("bestellnr") or ""))
    return out


def auftraege(db, kundennr):
    try:
        z = [a for a in _auftrag_zeilen(db) if a["kundennr"] == _t(kundennr)]
    except Exception:           # Datei ohne Auftragstabellen (sehr alte Stände)
        return []
    z.sort(key=lambda a: str(a.get("auftragsdatum") or a.get("angelegt") or ""), reverse=True)
    return z


def _n(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def kennzahlen_alle(db):
    """{Kundennummer: Kennzahlen} für alle Kunden in einem Durchgang (Übersicht)."""
    from . import auftraege as au
    je = {}

    def neu():
        return dict(angebote=0, beauftragt=0, abgelehnt=0, offen=0, entwurf=0, umsatz=0.0, offen_wert=0.0,
                    auftraege=0, laufend=0, letzter_auftrag="", letzter_kontakt="", quote=None)
    for nr, vorgang, vk, datum, geaendert, vk_am in db.con.execute(
            "SELECT kundennr, vorgang, vk_netto, datum, geaendert, vk_am FROM angebote "
            "WHERE COALESCE(ersetzt_durch, '')='' AND COALESCE(kundennr, '')<>''").fetchall():
        z = je.setdefault(str(nr), neu())
        z["angebote"] += 1
        v = vorgang or "Entwurf"
        if v == "Beauftragt":
            z["beauftragt"] += 1
            z["umsatz"] += _n(vk)
            z["letzter_auftrag"] = max(z["letzter_auftrag"], str(vk_am or datum or "")[:10])
        elif v == "Abgelehnt":
            z["abgelehnt"] += 1
        elif v == "Verschickt":
            z["offen"] += 1
            z["offen_wert"] += _n(vk)
        elif v == "Entwurf":
            z["entwurf"] += 1
        z["letzter_kontakt"] = max(z["letzter_kontakt"], str(vk_am or datum or "")[:10])
    try:
        for a in _auftrag_zeilen(db):
            if not a["kundennr"]:
                continue
            z = je.setdefault(a["kundennr"], neu())
            z["auftraege"] += 1
            if (a["status"] or au.NEU) in au.OFFEN:
                z["laufend"] += 1
            d = str(a.get("auftragsdatum") or a.get("angelegt") or "")[:10]
            z["letzter_auftrag"] = max(z["letzter_auftrag"], d)
    except Exception:       # noqa: BLE001 – nur Anzeige/Bequemlichkeit, weiter ohne
        protokoll.warnung("Kunden-Kennzahlen: Aufträge nicht lesbar")
    for nr, zeit in db.con.execute("SELECT kundennr, MAX(zeit) FROM kunden_historie WHERE art IN (?, ?) "
                                   "GROUP BY kundennr", (H_KONTAKT, H_NOTIZ)).fetchall():
        z = je.setdefault(str(nr), neu())
        z["letzter_kontakt"] = max(z["letzter_kontakt"], str(zeit or "")[:10])
    for z in je.values():
        entschieden = z["beauftragt"] + z["abgelehnt"]
        z["quote"] = round(z["beauftragt"] / entschieden, 3) if entschieden else None
        z["umsatz"] = round(z["umsatz"], 2)
        z["offen_wert"] = round(z["offen_wert"], 2)
    return je


def kennzahlen(db, kundennr):
    """Kennzahlen eines Kunden: Umsatz (beauftragte Angebote netto), Anzahl Angebote/Aufträge, Angebotsquote
    (beauftragt ÷ entschieden), letzter Auftrag, offene Angebote (verschickt), laufende Aufträge."""
    return kennzahlen_alle(db).get(_t(kundennr)) or dict(
        angebote=0, beauftragt=0, abgelehnt=0, offen=0, entwurf=0, umsatz=0.0, offen_wert=0.0, auftraege=0,
        laufend=0, letzter_auftrag="", letzter_kontakt="", quote=None)


def uebersicht(db, archiv=False):
    """Zeilen der Kundenübersicht: Kunde + Hauptansprechpartner + Kennzahlen. archiv=True: nur archivierte, sonst nur
    nicht archivierte."""
    kz = kennzahlen_alle(db)
    haupt = {}
    for p in [dict(r) for r in db.con.execute("SELECT kundennr, vorname, nachname, telefon, mobil, email, haupt, aktiv "
                                              "FROM kunden_ansprechpartner ORDER BY id")]:
        if p.get("aktiv") == "nein":
            continue
        alt = haupt.get(p["kundennr"])
        if alt is None or (p.get("haupt") == "ja" and alt.get("haupt") != "ja"):
            haupt[p["kundennr"]] = p
    out = []
    for k in db.con.execute("SELECT * FROM kunden ORDER BY kundennr").fetchall():
        k = dict(k)
        k.pop("uid", None)
        if (k.get("archiviert") == "ja") != bool(archiv):
            continue
        nr = _t(k.get("kundennr"))
        p = haupt.get(nr) or {}
        z = kz.get(nr) or {}
        out.append(dict(k, kontakt=name_voll(p) or _t(k.get("ansprechpartner")),
                        kontakt_telefon=_t(p.get("telefon")) or _t(p.get("mobil")),
                        kontakt_email=_t(p.get("email")),
                        telefon_anzeige=_t(k.get("telefon")) or _t(p.get("telefon")) or _t(p.get("mobil")),
                        email_anzeige=(mails(k.get("email")) or [""])[0] or _t(p.get("email")),
                        ort_anzeige=_t(k.get("ort")) or plz_ort_teilen(k.get("plz_ort"))[1],
                        status=_t(k.get("status")) or AKTIV, n_angebote=z.get("angebote", 0),
                        n_auftraege=z.get("auftraege", 0), letzter_kontakt=z.get("letzter_kontakt", ""),
                        umsatz=z.get("umsatz", 0.0), quote=z.get("quote")))
    return out


def filtern(zeilen, suche="", status=None, gruppe=None):
    """Live-Suche über Nummer, Name, Zusatz, Ort, Ansprechpartner, Telefon, E-Mail, Gruppe, Branche (ohne Groß-/
    Kleinschreibung, Umlaute gleich); status/gruppe None oder '' = alle."""
    worte = falten(suche).split()
    out = []
    for z in zeilen:
        if status and z.get("status") != status:
            continue
        if gruppe and _t(z.get("kundengruppe")) != gruppe:
            continue
        if worte:
            heu = falten(" ".join(_t(z.get(n)) for n in (
                "kundennr", "name", "firmenzusatz", "ort_anzeige", "plz", "kontakt", "telefon_anzeige",
                "email_anzeige", "kundengruppe", "branche", "ust_id", "email", "strasse")))
            if not all(w in heu for w in worte):
                continue
        out.append(z)
    return out


def gruppen(db):
    return sorted({_t(r[0]) for r in db.con.execute("SELECT kundengruppe FROM kunden") if _t(r[0])}, key=str.lower)


def mit_kontakten(db):
    """Kundenzeilen für die Erkennung (Mails, Dubletten): Feld email um die Adressen der Ansprechpartner ergänzt,
    Feld telefone mit allen Nummern."""
    je = {}
    for nr, mail_, tel, mob in db.con.execute("SELECT kundennr, email, telefon, mobil FROM kunden_ansprechpartner"):
        e = je.setdefault(_t(nr), dict(mails=[], tel=[]))
        e["mails"] += mails(mail_)
        e["tel"] += [x for x in (tel, mob) if _t(x)]
    out = []
    for k in db.zeilen("kunden"):
        e = je.get(_t(k.get("kundennr"))) or dict(mails=[], tel=[])
        alle = list(dict.fromkeys(mails(k.get("email")) + e["mails"]))
        out.append(dict(k, email="; ".join(alle) if alle else k.get("email"),
                        telefone=[x for x in [k.get("telefon")] + e["tel"] if _t(x)]))
    return out


# ------------------------------------------------------------------ Dubletten
def dubletten(db, daten, ohne=None):
    """Mögliche Dubletten zu neuen bzw. geänderten Kundendaten: [(Kunde, [Gründe], Punkte)], stärkste zuerst.
    Geprüft: Firmenname (Kern ohne Rechtsform), Anschrift (Straße + PLZ), PLZ + ähnlicher Name, Umsatzsteuer-ID,
    E-Mail-Adresse (Kunde und Ansprechpartner, auch gleiche Firmendomain), Telefon. ohne = eigene Kundennummer
    (beim Bearbeiten). Es wird nie etwas zusammengeführt."""
    from .mail import FREEMAIL, _domain
    d = daten or {}
    kern = namenskern(d.get("name"))
    plz = _t(d.get("plz")) or plz_ort_teilen(d.get("plz_ort"))[0]
    strasse = _strasse(d.get("strasse"))
    ust = _ust(d.get("ust_id"))
    neue_mails = set(mails(d.get("email")))
    for p in d.get("ansprechpartner") or ():
        neue_mails |= set(mails(p.get("email")))
    domains = {_domain(a) for a in neue_mails} - set(FREEMAIL) - {""}
    tel = {_ziffern(t) for t in [d.get("telefon")] + [p.get("telefon") for p in d.get("ansprechpartner") or ()]
           if len(_ziffern(t)) >= 6}
    out = []
    for k in mit_kontakten(db):
        if ohne is not None and _t(k.get("kundennr")) == _t(ohne):
            continue
        gruende, punkte = [], 0
        kk = namenskern(k.get("name"))
        if kern and kk:
            if kern == kk:
                gruende.append("gleicher Firmenname")
                punkte += 50
            elif min(len(kern), len(kk)) >= 5 and (kern in kk or kk in kern):
                gruende.append("ähnlicher Firmenname")
                punkte += 25
        kplz = _t(k.get("plz")) or plz_ort_teilen(k.get("plz_ort"))[0]
        if strasse and plz and kplz == plz and _strasse(k.get("strasse")) == strasse:
            gruende.append("gleiche Anschrift")
            punkte += 40
        elif plz and kplz == plz and gruende:
            gruende.append("gleiche PLZ")
            punkte += 10
        if ust and _ust(k.get("ust_id")) == ust:
            gruende.append("gleiche Umsatzsteuer-ID")
            punkte += 80
        km = set(mails(k.get("email")))
        if neue_mails & km:
            gruende.append("gleiche E-Mail-Adresse " + sorted(neue_mails & km)[0])
            punkte += 60
        elif domains and domains & {_domain(a) for a in km}:
            gruende.append("gleiche Firmendomain @" + sorted(domains & {_domain(a) for a in km})[0])
            punkte += 30
        if tel and tel & {_ziffern(t) for t in k.get("telefone") or ()}:
            gruende.append("gleiche Telefonnummer")
            punkte += 30
        if gruende and punkte >= 25:
            out.append((k, gruende, punkte))
    out.sort(key=lambda x: -x[2])
    return out


# ------------------------------------------------------------------ Kundennummer
def _numerisch(nr, praefix=""):
    t = _t(nr)
    if praefix and t.startswith(praefix):
        t = t[len(praefix):]
    return int(t) if t.isdigit() else 0


def nummern_schema(db):
    """(Präfix, höchste Zahl) der vorhandenen Kundennummern: der häufigste Vorsatz vor der Zahl (K-1001, K-1002 ->
    'K-'), damit neue Nummern wie die bisherigen aussehen, solange keine Einstellung etwas anderes sagt."""
    zaehler, hoechste = {}, {}
    for (nr,) in db.con.execute("SELECT kundennr FROM kunden"):
        m = re.fullmatch(r"(\D*)(\d+)", _t(nr))
        if m:
            zaehler[m.group(1)] = zaehler.get(m.group(1), 0) + 1
            hoechste[m.group(1)] = max(hoechste.get(m.group(1), 0), int(m.group(2)))
    if not zaehler:
        return "", 0
    p = max(zaehler, key=lambda x: (zaehler[x], x))
    return p, hoechste[p]


def nummer_hinweis(db):
    """Platzhalter für das Feld Kundennummer: „Pflichtfeld – zuletzt vergeben K-1002“ (nur Hinweis, die Nummer gibt
    man immer von Hand ein)."""
    try:
        praefix, hoechste = nummern_schema(db)
    except Exception:       # noqa: BLE001 – nur ein Hinweis
        hoechste = 0
    return f"Pflichtfeld – zuletzt vergeben {praefix}{hoechste}" if hoechste else "Pflichtfeld, z. B. 10001"


# ------------------------------------------------------------------ Prüfen und Speichern
def _wert(name, w):
    """Eingabe in den gespeicherten Typ (Zahl, Text, None für leer). KundenFehler bei falscher Zahl."""
    if _leer(w):
        return None
    if name in ZAHLEN:
        try:
            x = ZAHLEN[name](float(str(w).replace(",", ".").replace(" ", "")))
        except (TypeError, ValueError):
            raise KundenFehler(f"{TITEL.get(name, name)}: „{w}“ ist keine Zahl.")
        von, bis = GRENZEN[name]
        if not von <= x <= bis:
            raise KundenFehler(f"{TITEL.get(name, name)}: erlaubt ist {von:g} bis {bis:g}.")
        return x
    return _t(w)


def pruefen(db, werte, kundennr_alt=None):
    """Eingaben der Maske prüfen. Ergebnis: Liste der Fehlertexte (leer = in Ordnung)."""
    f = []
    if _leer(werte.get("name")):
        f.append("Firmenname fehlt.")
    nr = _t(werte.get("kundennr"))
    if not nr:
        f.append("Kundennummer fehlt.")
    elif nr != _t(kundennr_alt) and kunde(db, nr):
        f.append(f"Kundennummer {nr} ist schon vergeben.")
    land = _t(werte.get("land")).upper()
    if land and not re.match(r"^[A-Z]{2}$", land):
        f.append("Land als zweistelliger Ländercode, z. B. DE.")
    if not _leer(werte.get("email")) and not mails(werte.get("email")):
        f.append("E-Mail-Adresse ist ungültig.")
    if not _leer(werte.get("website")) and " " in _t(werte.get("website")):
        f.append("Website ohne Leerzeichen eingeben.")
    if land == "DE" and _t(werte.get("plz")) and not re.match(r"^\d{5}$", _t(werte.get("plz"))):
        f.append("PLZ in Deutschland hat 5 Ziffern.")
    ust = _ust(werte.get("ust_id"))
    if ust and not re.match(r"^[A-Z]{2}[0-9A-Z]{2,13}$", ust):
        f.append("Umsatzsteuer-ID beginnt mit dem Ländercode, z. B. DE123456789.")
    if _t(werte.get("status")) and _t(werte.get("status")) not in STATUS:
        f.append("Kundenstatus: Aktiv, Inaktiv oder Gesperrt.")
    for n in ZAHLEN:
        if n in werte:
            try:
                _wert(n, werte[n])
            except KundenFehler as e:
                f.append(str(e))
    return f


def _kunden_werte(werte):
    """Nur Felder der Tabelle kunden, in Typen; plz_ort aus PLZ und Ort (für alle bisherigen Ausgaben)."""
    from .stammdaten import KUNDEN
    namen = {f.name for f in KUNDEN.felder}
    out = {n: _wert(n, w) for n, w in werte.items() if n in namen and n not in VORGABE_FELDER}
    if "land" in out and out["land"]:
        out["land"] = out["land"].upper()
    if "ust_id" in out and out["ust_id"]:
        out["ust_id"] = _ust(out["ust_id"])
    if "plz" in werte or "ort" in werte:
        out["plz_ort"] = plz_ort(werte.get("plz"), werte.get("ort")) or None
    return out


def anlegen(db, werte, ansprechpartner_=(), adressen_=(), vorgaben_=None, dubletten_ok=False):
    """Neuen Kunden anlegen (eine Transaktion): Kundenzeile, Kundenvorgaben (Rabatt …), Ansprechpartner, Adressen,
    Historie „Angelegt“. Die Kundennummer gibt man immer von Hand ein (Patrick 23.11.2026), ohne Nummer
    KundenFehler. dubletten_ok=False: bei möglichen Dubletten
    KundenFehler (die Oberfläche fragt vorher). Ergebnis: Kundennummer."""
    _schreibbar(db)
    werte = dict(werte or {})
    if _leer(werte.get("kundennr")):
        raise KundenFehler("Bitte die Kundennummer eingeben (sie wird nicht automatisch vergeben).")
    werte.setdefault("status", AKTIV)
    werte.setdefault("kundentyp", "Firma")
    fehler = pruefen(db, werte)
    if fehler:
        raise KundenFehler(" ".join(fehler))
    if not dubletten_ok:
        d = dubletten(db, dict(werte, ansprechpartner=list(ansprechpartner_)))
        if d:
            k, gruende, _ = d[0]
            raise KundenFehler(f"Mögliche Dublette: {k.get('kundennr')} {k.get('name')} ({', '.join(gruende)}).")
    nr = _t(werte["kundennr"])
    kw = _kunden_werte(werte)
    jetzt = _jetzt()
    kw.update(angelegt=jetzt, geaendert=jetzt, angelegt_von=_wer(db))
    import sqlite3
    try:
        with db.con:
            db.con.execute(f'INSERT INTO kunden ({", ".join(chr(34) + n + chr(34) for n in kw)}) VALUES '
                           f'({", ".join("?" * len(kw))})', list(kw.values()))
            vg = {n: _wert(n, w) for n, w in (vorgaben_ or {}).items() if n in VORGABE_FELDER}
            vg = {n: w for n, w in vg.items() if w is not None}
            if vg:
                db.con.execute(f'INSERT INTO kundenvorgaben (kundennr, {", ".join(vg)}) VALUES '
                               f'(?, {", ".join("?" * len(vg))})', [nr, *vg.values()])
            for p in ansprechpartner_ or ():
                _person_schreiben(db, nr, p)
            for a in adressen_ or ():
                _adresse_schreiben(db, nr, a)
            if any(a.get("art") == LIEFERUNG for a in adressen_ or ()):
                _liefer_spiegeln(db, nr)
            _haupt_spiegeln(db, nr)
            _historie(db, nr, H_ANGELEGT, f"Kunde {nr} {kw.get('name') or ''} angelegt", zeit=jetzt)
            db._einstellung_schreiben("kunden_letzte_nummer", nr)
    except sqlite3.IntegrityError:
        raise KundenFehler(f"Kundennummer {nr} ist schon vergeben.")
    except Exception as e:      # PostgreSQL: UniqueViolation (psycopg) ohne gemeinsame Basisklasse
        if "unique" in type(e).__name__.lower() or "duplicate" in str(e).lower():
            raise KundenFehler(f"Kundennummer {nr} ist schon vergeben.")
        raise
    return nr


def speichern(db, kundennr, neu, alt, vorgaben_neu=None, vorgaben_alt=None):
    """Geänderte Felder eines Kunden speichern (eine Transaktion). neu/alt: Werte der Maske jetzt und beim Öffnen.
    Nur Felder, die sich gegenüber alt geändert haben, werden geschrieben; jedes davon wird gegen den gespeicherten
    Wert geprüft (AenderungsKonflikt, wenn ein Kollege es inzwischen anders geändert hat). Jede Änderung kommt in die
    Historie. Die Kundennummer bleibt (Umbenennen über die Tabellenansicht, mit allen Verweisen). Ergebnis: Liste der
    geänderten Feldtitel."""
    _schreibbar(db)
    from .datenbank import AenderungsKonflikt
    k = kunde(db, kundennr)
    if k is None:
        raise KundenFehler(f"Kunde {kundennr} gibt es nicht mehr (gelöscht oder umbenannt).")
    neu = dict(neu or {})
    neu["kundennr"] = kundennr
    basis = dict(k)                     # Teiländerung (Notizen, Übernahme aus einer Mail): Rest wie gespeichert
    basis.update(alt or {})
    basis.update(neu)
    fehler = pruefen(db, basis, kundennr)
    if fehler:
        raise KundenFehler(" ".join(fehler))
    alt = dict(alt or {})
    if "plz" in neu or "ort" in neu:    # „PLZ Ort“ immer aus beiden (nur Ort geändert: PLZ wie gespeichert)
        for f in ("plz", "ort"):
            if f not in neu:
                neu[f] = k.get(f)
                alt.setdefault(f, k.get(f))
    kw_neu, kw_alt = _kunden_werte(neu), _kunden_werte(alt)
    geaendert = []
    with db.con:
        sperre = "" if _sqlite(db) else " FOR UPDATE"
        jetzt_db = dict(db.con.execute(f"SELECT * FROM kunden WHERE kundennr=?{sperre}", (kundennr,)).fetchone())
        for n, w in kw_neu.items():
            if n == "kundennr" or _gleich(w, kw_alt.get(n)) and n in kw_alt:
                continue
            gespeichert = jetzt_db.get(n)
            if _gleich(gespeichert, w):
                continue
            if n in kw_alt and n != "plz_ort" and not _gleich(gespeichert, kw_alt.get(n)):   # plz_ort: abgeleitet
                raise AenderungsKonflikt("kunden", jetzt_db["id"], n, gespeichert, w)
            db.con.execute(f'UPDATE kunden SET "{n}"=? WHERE id=?', (w, jetzt_db["id"]))
            if n != "plz_ort":
                _historie(db, kundennr, H_GEAENDERT, "", feld=TITEL.get(n, n), alt=gespeichert, neu=w)
                geaendert.append(TITEL.get(n, n))
        if vorgaben_neu is not None:
            vz = db.con.execute(f"SELECT * FROM kundenvorgaben WHERE kundennr=?{sperre}", (kundennr,)).fetchone()
            vz = dict(vz) if vz else None
            for n in VORGABE_FELDER:
                if n not in vorgaben_neu:
                    continue
                w = _wert(n, vorgaben_neu.get(n))
                a = _wert(n, (vorgaben_alt or {}).get(n)) if vorgaben_alt is not None else None
                gespeichert = (vz or {}).get(n)
                if _gleich(gespeichert, w):
                    continue
                if vorgaben_alt is not None and not _gleich(gespeichert, a):
                    raise AenderungsKonflikt("kundenvorgaben", (vz or {}).get("id"), n, gespeichert, w)
                if vz is None:
                    db.con.execute(f'INSERT INTO kundenvorgaben (kundennr, "{n}") VALUES (?, ?)', (kundennr, w))
                    vz = dict(db.con.execute("SELECT * FROM kundenvorgaben WHERE kundennr=?", (kundennr,)).fetchone())
                else:
                    db.con.execute(f'UPDATE kundenvorgaben SET "{n}"=? WHERE id=?', (w, vz["id"]))
                _historie(db, kundennr, H_GEAENDERT, "", feld=TITEL.get(n, n), alt=gespeichert, neu=w)
                geaendert.append(TITEL.get(n, n))
        if geaendert:
            db.con.execute("UPDATE kunden SET geaendert=? WHERE id=?", (_jetzt(), jetzt_db["id"]))
    return geaendert


def _sqlite(db):
    from . import db_verbindung
    return db_verbindung.ist_sqlite(db.con)


def archivieren(db, kundennr, an=True, grund=""):
    """Kunden archivieren (aus der Übersicht und der Kundenauswahl im Angebot ausgeblendet, Daten bleiben) oder
    zurückholen."""
    _schreibbar(db)
    k = kunde(db, kundennr)
    if k is None:
        raise KundenFehler(f"Kunde {kundennr} gibt es nicht.")
    with db.con:
        db.con.execute("UPDATE kunden SET archiviert=?, geaendert=? WHERE id=?",
                       ("ja" if an else None, _jetzt(), k["id"]))
        _historie(db, kundennr, H_ARCHIV, ("archiviert" if an else "aus dem Archiv geholt")
                  + (f": {grund}" if _t(grund) else ""))


def duplizieren(db, kundennr, neue_nr=None):
    """Kopie eines Kunden mit neuer Nummer (Stammdaten, Konditionen, Ansprechpartner, Adressen; ohne Historie,
    Angebote und USt-ID). Ergebnis: neue Kundennummer."""
    k = kunde(db, kundennr)
    if k is None:
        raise KundenFehler(f"Kunde {kundennr} gibt es nicht.")
    if _leer(neue_nr):
        raise KundenFehler("Bitte die Kundennummer für die Kopie eingeben.")
    werte = {n: w for n, w in k.items() if n not in ("id", "kundennr", "angelegt", "geaendert", "angelegt_von",
                                                      "archiviert", "ust_id", "steuernr")}
    werte["name"] = f"{k.get('name') or ''} (Kopie)".strip()
    werte["kundennr"] = neue_nr
    personen = [{n: w for n, w in p.items() if n not in ("id", "uid", "kundennr")} for p in ansprechpartner(db, kundennr)]
    adr = [{n: w for n, w in a.items() if n not in ("id", "uid", "kundennr")} for a in adressen(db, kundennr)]
    vg = vorgaben(db, kundennr)
    nr = anlegen(db, werte, personen, adr, {n: vg.get(n) for n in VORGABE_FELDER}, dubletten_ok=True)
    with db.con:
        _historie(db, nr, H_ANGELEGT, f"als Kopie von {kundennr} angelegt")
    return nr


# ------------------------------------------------------------------ Ansprechpartner
PERSON_FELDER = tuple(f.name for f in ANSPRECHPARTNER.felder if f.name not in ("kundennr", "geaendert"))


def _person_schreiben(db, kundennr, p, pid=None):
    werte = {n: (_t(p.get(n)) or None) for n in PERSON_FELDER if n in p}
    if "email" in werte and werte["email"]:
        werte["email"] = (mails(werte["email"]) or [werte["email"]])[0]
    for r, _ in ROLLEN:
        if r in werte:
            werte[r] = "ja" if werte[r] in ("ja", "1", "True", "true") or p.get(r) is True else None
    werte.setdefault("aktiv", "ja") if pid is None else None
    werte["geaendert"] = _jetzt()
    if werte.get("haupt") == "ja":      # nur einer ist Hauptansprechpartner
        db.con.execute("UPDATE kunden_ansprechpartner SET haupt=NULL WHERE kundennr=? AND haupt='ja'"
                       + (" AND id<>?" if pid else ""), (kundennr, pid) if pid else (kundennr,))
    if pid is None:
        werte["kundennr"] = kundennr
        cur = db.con.execute(f'INSERT INTO kunden_ansprechpartner ({", ".join(chr(34) + n + chr(34) for n in werte)})'
                             f' VALUES ({", ".join("?" * len(werte))})', list(werte.values()))
        return cur.lastrowid
    db.con.execute(f'UPDATE kunden_ansprechpartner SET {", ".join(chr(34) + n + chr(34) + "=?" for n in werte)} '
                   "WHERE id=?", [*werte.values(), pid])
    return pid


def _haupt_spiegeln(db, kundennr):
    """Hauptansprechpartner (sonst der erste aktive) in kunden.ansprechpartner; Telefon/E-Mail des Kunden nur, wenn dort
    noch leer (die Zentrale bleibt)."""
    ps = ansprechpartner(db, kundennr, nur_aktiv=True)
    k = db.con.execute("SELECT id, ansprechpartner, telefon, email FROM kunden WHERE kundennr=?",
                       (kundennr,)).fetchone()
    if k is None:
        return
    p = next((x for x in ps if x.get("haupt") == "ja"), ps[0] if ps else None)
    name = name_voll(p) if p else None
    if (k[1] or None) != (name or None):
        db.con.execute("UPDATE kunden SET ansprechpartner=? WHERE id=?", (name, k[0]))
    if p and _leer(k[2]) and _t(p.get("telefon") or p.get("mobil")):
        db.con.execute("UPDATE kunden SET telefon=? WHERE id=?", (_t(p.get("telefon") or p.get("mobil")), k[0]))
    if p and _leer(k[3]) and _t(p.get("email")):
        db.con.execute("UPDATE kunden SET email=? WHERE id=?", (_t(p.get("email")), k[0]))


def person_speichern(db, kundennr, p, pid=None):
    """Ansprechpartner anlegen (pid None) oder ändern; Historie, Hauptansprechpartner gespiegelt. Ergebnis: id."""
    _schreibbar(db)
    if kunde(db, kundennr) is None:
        raise KundenFehler(f"Kunde {kundennr} gibt es nicht.")
    if _leer(p.get("nachname")) and _leer(p.get("vorname")):
        raise KundenFehler("Bitte mindestens den Namen des Ansprechpartners eingeben.")
    if _leer(p.get("nachname")):
        p = dict(p, nachname=p.get("vorname"), vorname=None)
    if not _leer(p.get("email")) and not mails(p.get("email")):
        raise KundenFehler("E-Mail-Adresse des Ansprechpartners ist ungültig.")
    with db.con:
        alt = None
        if pid is not None:
            r = db.con.execute("SELECT * FROM kunden_ansprechpartner WHERE id=?", (pid,)).fetchone()
            if r is None:
                raise KundenFehler("Der Ansprechpartner wurde inzwischen gelöscht.")
            alt = dict(r)
        i = _person_schreiben(db, kundennr, p, pid)
        name = name_voll(p)
        if alt is None:
            _historie(db, kundennr, H_PERSON, f"Ansprechpartner {name} angelegt")
        else:
            for n in PERSON_FELDER:
                if n in p and not _gleich(alt.get(n), p.get(n)) and not (n in dict(ROLLEN) and
                                                                         (alt.get(n) == "ja") == (p.get(n) == "ja")):
                    _historie(db, kundennr, H_PERSON, f"Ansprechpartner {name}",
                              feld=ANSPRECHPARTNER.feld(n).titel, alt=alt.get(n), neu=p.get(n))
        _haupt_spiegeln(db, kundennr)
    return i


def person_loeschen(db, kundennr, pid):
    _schreibbar(db)
    with db.con:
        r = db.con.execute("SELECT * FROM kunden_ansprechpartner WHERE id=? AND kundennr=?", (pid, kundennr)).fetchone()
        if r is None:
            return False
        db.con.execute("DELETE FROM kunden_ansprechpartner WHERE id=?", (pid,))
        _historie(db, kundennr, H_PERSON, f"Ansprechpartner {name_voll(dict(r))} entfernt")
        _haupt_spiegeln(db, kundennr)
    return True


def person_rollen_text(p):
    return ", ".join(t for r, t in ROLLEN if p.get(r) == "ja")


# ------------------------------------------------------------------ Adressen
ADRESS_FELDER = tuple(f.name for f in ADRESSEN.felder if f.name not in ("kundennr", "geaendert"))


def _adresse_schreiben(db, kundennr, a, aid=None):
    werte = {n: (_t(a.get(n)) or None) for n in ADRESS_FELDER if n in a}
    if werte.get("land"):
        werte["land"] = werte["land"].upper()
    werte.setdefault("art", LIEFERUNG) if aid is None else None
    werte["geaendert"] = _jetzt()
    if werte.get("standard") == "ja":       # ein Standard je Art
        art = werte.get("art") or (db.con.execute("SELECT art FROM kunden_adressen WHERE id=?", (aid,)).fetchone()
                                   or [None])[0]
        db.con.execute("UPDATE kunden_adressen SET standard=NULL WHERE kundennr=? AND art=? AND standard='ja'"
                       + (" AND id<>?" if aid else ""), (kundennr, art, aid) if aid else (kundennr, art))
    if aid is None:
        werte["kundennr"] = kundennr
        return db.con.execute(f'INSERT INTO kunden_adressen ({", ".join(chr(34) + n + chr(34) for n in werte)}) '
                              f'VALUES ({", ".join("?" * len(werte))})', list(werte.values())).lastrowid
    db.con.execute(f'UPDATE kunden_adressen SET {", ".join(chr(34) + n + chr(34) + "=?" for n in werte)} WHERE id=?',
                   [*werte.values(), aid])
    return aid


def adresse_speichern(db, kundennr, a, aid=None):
    _schreibbar(db)
    if kunde(db, kundennr) is None:
        raise KundenFehler(f"Kunde {kundennr} gibt es nicht.")
    if _t(a.get("art")) and _t(a.get("art")) not in ADRESS_ARTEN:
        raise KundenFehler("Art: Rechnungsadresse, Lieferadresse oder Standort.")
    if all(_leer(a.get(n)) for n in ("strasse", "plz", "ort", "name")):
        raise KundenFehler("Bitte mindestens Straße, PLZ oder Ort eingeben.")
    land = _t(a.get("land")).upper()
    if land and not re.match(r"^[A-Z]{2}$", land):
        raise KundenFehler("Land als zweistelliger Ländercode, z. B. DE.")
    with db.con:
        i = _adresse_schreiben(db, kundennr, a, aid)
        _historie(db, kundennr, H_ADRESSE, f"{a.get('art') or 'Adresse'} {'geändert' if aid else 'angelegt'}: "
                  + adresse_text(a))
        if (a.get("art") == LIEFERUNG and a.get("standard") == "ja") or aid is not None:
            _liefer_spiegeln(db, kundennr)
    return i


def _liefer_spiegeln(db, kundennr):
    """Standard-Lieferadresse in kunden.liefer_plz/liefer_land (Frachtzone wie bisher); ohne Lieferadresse leer."""
    li = adressen(db, kundennr, LIEFERUNG)
    a = next((x for x in li if x.get("standard") == "ja"), None)
    db.con.execute("UPDATE kunden SET liefer_plz=?, liefer_land=? WHERE kundennr=?",
                   ((a or {}).get("plz"), ((a or {}).get("land") or None) if a else None, kundennr))


def adresse_loeschen(db, kundennr, aid):
    _schreibbar(db)
    with db.con:
        r = db.con.execute("SELECT * FROM kunden_adressen WHERE id=? AND kundennr=?", (aid, kundennr)).fetchone()
        if r is None:
            return False
        db.con.execute("DELETE FROM kunden_adressen WHERE id=?", (aid,))
        _historie(db, kundennr, H_ADRESSE, f"{r['art'] or 'Adresse'} entfernt: {adresse_text(dict(r))}")
        _liefer_spiegeln(db, kundennr)
    return True


# ------------------------------------------------------------------ Angebot
def fuer_angebot(db, kundennr):
    """Auswahl im Angebot: aktive Ansprechpartner [(uid, Text)], Lieferadressen [(uid, Text)] und der Vorschlag
    (Hauptansprechpartner bzw. Standard-Lieferadresse)."""
    ps = ansprechpartner(db, kundennr, nur_aktiv=True)
    k = kunde(db, kundennr) or {}
    li = adressen(db, kundennr, LIEFERUNG) + adressen(db, kundennr, STANDORT)
    return dict(personen=[(p["uid"], name_voll(p) + (f" ({person_rollen_text(p)})" if person_rollen_text(p) else ""))
                          for p in ps],
                person_vorschlag=next((p["uid"] for p in ps if p.get("haupt") == "ja"), ps[0]["uid"] if ps else None),
                adressen=[(a["uid"], (f"{a['bezeichnung']}: " if a.get("bezeichnung") else "") + adresse_text(a, k))
                          for a in li],
                adresse_vorschlag=next((a["uid"] for a in li if a.get("art") == LIEFERUNG and a.get("standard") == "ja"),
                                       None),
                gesperrt=k.get("status") == GESPERRT, archiviert=k.get("archiviert") == "ja")


def person(db, uid):
    r = db.con.execute("SELECT * FROM kunden_ansprechpartner WHERE uid=?", (uid,)).fetchone() if uid else None
    return dict(r) if r else None


def adresse(db, uid):
    r = db.con.execute("SELECT * FROM kunden_adressen WHERE uid=?", (uid,)).fetchone() if uid else None
    return dict(r) if r else None


def angebot_kunde_setzen(db, angebot_id, kundennr):
    """Nach dem Wechsel des Kunden im Angebot: Ansprechpartner und Lieferadresse auf den Vorschlag des Kunden
    (Hauptansprechpartner, Standard-Lieferadresse); ohne Kunde leer. Ergebnis: (Ansprechpartner, Lieferadresse) als
    Text."""
    a = fuer_angebot(db, kundennr) if kundennr else dict(person_vorschlag=None, adresse_vorschlag=None)
    p = person(db, a["person_vorschlag"])
    ad = adresse(db, a["adresse_vorschlag"])
    k = kunde(db, kundennr) or {}
    werte = dict(kunde_ansprech_uid=a["person_vorschlag"], kunde_ansprech=name_voll(p) if p else None,
                 liefer_uid=a["adresse_vorschlag"], lieferadresse="\n".join(adresse_zeilen(ad, k)) if ad else None)
    for n, w in werte.items():
        db.angebot_aendern(angebot_id, n, w)
    return werte["kunde_ansprech"], werte["lieferadresse"]


def angebot_person_setzen(db, angebot_id, uid):
    p = person(db, uid)
    db.angebot_aendern(angebot_id, "kunde_ansprech_uid", uid if p else None)
    db.angebot_aendern(angebot_id, "kunde_ansprech", name_voll(p) if p else None)
    return p


def angebot_adresse_setzen(db, angebot_id, uid, kundennr=None):
    a = adresse(db, uid)
    db.angebot_aendern(angebot_id, "liefer_uid", uid if a else None)
    db.angebot_aendern(angebot_id, "lieferadresse", "\n".join(adresse_zeilen(a, kunde(db, kundennr))) if a else None)
    return a


def anschrift(kunde_, ansprechpartner_=None):
    """Anschriftzeilen fürs Angebot/die AB (ohne Name): Firmenzusatz, Straße, PLZ Ort, Land (außer DE),
    „z. Hd.“ des gewählten Ansprechpartners, sonst des Hauptansprechpartners aus dem Kundenstamm."""
    if not kunde_:
        return []
    land = _t(kunde_.get("land")).upper()
    zeilen = [_t(kunde_.get("firmenzusatz")), _t(kunde_.get("strasse")),
              _t(kunde_.get("plz_ort")) or plz_ort(kunde_.get("plz"), kunde_.get("ort")),
              land if land and land != "DE" else ""]
    ap = _t(ansprechpartner_) or _t(kunde_.get("ansprechpartner"))
    if ap:
        zeilen.append(f"z. Hd. {ap}")
    return [z for z in zeilen if z]


# ------------------------------------------------------------------ Dokumente
def dokumente_ordner(basis, kundennr, anlegen=False):
    """Ordner der Kundendokumente: <Ablage>/Kundendokumente/<Kundennummer> (mit gemeinsamem Ordner für alle)."""
    sicher = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", _t(kundennr)) or "_"
    o = Path(basis) / DOKUMENTE_ORDNER / sicher
    if anlegen:
        o.mkdir(parents=True, exist_ok=True)
    return o


def dokumente(basis, kundennr):
    """[dict(name, pfad, groesse, geaendert)] der Dateien im Kundenordner (neueste zuerst)."""
    o = dokumente_ordner(basis, kundennr)
    if not o.is_dir():
        return []
    out = []
    for p in o.iterdir():
        if p.is_file() and not p.name.startswith("~$"):
            st = p.stat()
            out.append(dict(name=p.name, pfad=str(p), groesse=st.st_size,
                            geaendert=datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")))
    out.sort(key=lambda d: d["geaendert"], reverse=True)
    return out


def dokument_ablegen(db, basis, kundennr, quelle):
    """Datei in den Kundenordner kopieren (gleicher Name: Zusatz _2, _3 …); Historie. Ergebnis: Zielpfad."""
    q = Path(quelle)
    if not q.is_file():
        raise KundenFehler(f"Datei nicht gefunden: {q}")
    o = dokumente_ordner(basis, kundennr, anlegen=True)
    ziel, i = o / q.name, 2
    while ziel.exists():
        ziel = o / f"{q.stem}_{i}{q.suffix}"
        i += 1
    shutil.copy2(q, ziel)
    if not getattr(db, "nur_lesen", ""):
        with db.con:
            _historie(db, kundennr, H_DOKUMENT, f"Dokument {ziel.name} abgelegt")
    return ziel


# ------------------------------------------------------------------ Export / Import
EXPORT_SPALTEN = (("kundennr", "Kundennummer"), ("name", "Firmenname"), ("firmenzusatz", "Firmenzusatz"),
                  ("rechtsform", "Rechtsform"), ("kundentyp", "Kundentyp"), ("status", "Status"),
                  ("kundengruppe", "Kundengruppe"), ("branche", "Branche"), ("strasse", "Straße"), ("plz", "PLZ"),
                  ("ort_anzeige", "Ort"), ("land", "Land"), ("kontakt", "Ansprechpartner"),
                  ("telefon_anzeige", "Telefon"), ("email_anzeige", "E-Mail"), ("ust_id", "USt-ID"),
                  ("zahlungsziel", "Zahlungsziel"), ("n_angebote", "Angebote"), ("n_auftraege", "Aufträge"),
                  ("umsatz", "Umsatz netto"), ("letzter_kontakt", "Letzter Kontakt"))


def export_csv(zeilen, pfad):
    """Übersicht als CSV (Semikolon, UTF-8 mit BOM, für Excel)."""
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow([t for _, t in EXPORT_SPALTEN])
    for z in zeilen:
        w.writerow([("" if z.get(n) is None else str(z.get(n)).replace(".", ",") if isinstance(z.get(n), float)
                     else str(z.get(n))) for n, _ in EXPORT_SPALTEN])
    Path(pfad).write_text(puffer.getvalue(), encoding="utf-8-sig")
    return pfad


def _xlsx_spalte(i):
    t = ""
    while i:
        i, r = divmod(i - 1, 26)
        t = chr(65 + r) + t
    return t


def export_xlsx(zeilen, pfad):
    """Übersicht als Excel-Datei (.xlsx, Office Open XML ohne Zusatzpaket: im Windows-Paket ist kein openpyxl).
    Kopfzeile fett und fixiert, Zahlen als Zahlen, Texte als Inline-Text."""
    import zipfile
    from xml.sax.saxutils import escape

    def zelle(r, c, w, stil=0):
        ref = f"{_xlsx_spalte(c)}{r}"
        if w is None or w == "":
            return ""
        if isinstance(w, (int, float)) and not isinstance(w, bool):
            return f'<c r="{ref}"><v>{w}</v></c>'
        t = escape(str(w)).replace("\n", "&#10;")
        t = "".join(ch for ch in t if ch in "\t&#10;" or ord(ch) >= 32)
        return f'<c r="{ref}" t="inlineStr"{f" s={chr(34)}{stil}{chr(34)}" if stil else ""}><is><t xml:space="preserve">{t}</t></is></c>'

    reihen = [[t for _, t in EXPORT_SPALTEN]] + [[z.get(n) for n, _ in EXPORT_SPALTEN] for z in zeilen]
    daten = "".join(f'<row r="{r}">' + "".join(zelle(r, c, w, 1 if r == 1 else 0) for c, w in enumerate(z, 1))
                    + "</row>" for r, z in enumerate(reihen, 1))
    breiten = "".join(f'<col min="{i}" max="{i}" width="{max(10, min(40, len(t) + 4))}" customWidth="1"/>'
                      for i, (_, t) in enumerate(EXPORT_SPALTEN, 1))
    blatt = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
             f'state="frozen"/></sheetView></sheetViews><cols>{breiten}</cols><sheetData>{daten}</sheetData>'
             '</worksheet>')
    ns = "http://schemas.openxmlformats.org"
    dateien = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="'
        f'{ns}/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
        'package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override '
        'PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.'
        'sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{ns}/package/'
        f'2006/relationships"><Relationship Id="rId1" Type="{ns}/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{ns}/'
        f'spreadsheetml/2006/main" xmlns:r="{ns}/officeDocument/2006/relationships"><sheets><sheet name="Kunden" '
        'sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
        f'xmlns="{ns}/package/2006/relationships"><Relationship Id="rId1" Type="{ns}/officeDocument/2006/'
        f'relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="{ns}/'
        'officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{ns}/'
        'spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/>'
        '<sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/>'
        '</fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/>'
        '<top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" '
        'fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" '
        'borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>',
        "xl/worksheets/sheet1.xml": blatt,
    }
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        for name, inhalt in dateien.items():
            z.writestr(name, inhalt)
    return pfad
