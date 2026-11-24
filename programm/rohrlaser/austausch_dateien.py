"""Austauschordner 2.0: Mitarbeiterplattform für Dateien, Anfragen und Projekte (Patrick 24.11.2026, Master-Auftrag
„Austauschordner 2.0“, Paket A). Ohne Qt.

Architektur (Patrick-Regel: PostgreSQL je PC + Abgleich über den gemeinsamen Ordner, kein zentraler Server):

- Dateien liegen im gemeinsamen Ordner, nie in der Datenbank. Neu ist der Unterordner Austausch/ (gemeinsame Dateien,
  darin _Persoenlich/<Kürzel>/ je Mitarbeiter). Die schon vorhandenen Bereiche Anfragen (Akten), Angebote (Ablage) und
  PPEASE-Ablage zeigt die Plattform mit an, ohne sie umzubauen (PPEASE-Angebotsordner legt nur PPEASE an).
- Metadaten (Zuordnung, Bearbeiter, Status, Priorität, Fälligkeit, Aufgabe, Notiz) stehen in der geteilten Tabelle
  austausch_dateien (Schlüssel: Datei-Schlüssel „bereich:pfad“), Kommentare und Verlauf in austausch_ereignisse (nur
  angehängt). Beide gehen mit dem normalen Abgleich an alle Plätze (teilen.GETEILT, feldweise, neueste gewinnt).
- Was sofort bei allen ankommen muss (Bearbeitungssperre, laufender Upload), steht als kleine JSON-Datei in
  <Bereich>/_Plattform/ – wie Lebenszeichen und Nummernreservierung.
- Schutz vor Datenverlust: Hochladen erst in eine Zwischendatei (.rlteil), Größe prüfen, dann in einem Schritt
  umbenennen. Eine vorhandene Datei wird nie still ersetzt: die alte kommt nach <Ordner>/_Versionen/ (Benennung wie
  die PPEASE-Ablage: Name_V<n>_<Zeit>_<Kürzel>.ext). Löschen verschiebt nach <Bereich>/_Papierkorb/ (mit Beschreibung
  .json), Wiederherstellen holt die Datei an ihren Platz zurück; endgültig löschen darf nur der Admin.

Ordner und Dateien, deren Name mit „_“ oder „.“ beginnt, Office-Sperrdateien (~$…) und Zwischendateien sind intern und
erscheinen nicht in der Liste (Office-Sperrdateien werden als „in Bearbeitung“ ausgewertet).
"""
import dataclasses
import datetime
import hashlib
import json
import os
import re
import shutil
import socket
import time
import unicodedata
from pathlib import Path

from .stammdaten import Feld, Tabelle

ORDNER = "Austausch"                # im gemeinsamen Ordner (ohne gemeinsamen Ordner neben der Datendatei)
PERSOENLICH_ORDNER = "_Persoenlich"
SYSTEM = "_Plattform"               # Sperren, laufende Uploads
VERSIONEN = "_Versionen"            # wie ppease_ablage.VERSIONEN
PAPIERKORB = "_Papierkorb"
ARCHIV = "_Archiv"
TEIL = ".rlteil"                    # Zwischendatei beim Hochladen
BLOCK = 1 << 20                     # Kopieren in Blöcken (Fortschritt, Abbrechen)
PAPIERKORB_TAGE = 30
SPERRE_MIN = 15                     # Bearbeitungssperre ohne Lebenszeichen so lange gültig
UPLOAD_ALT_S = 3600                 # Zwischendatei/Upload-Marker älter: Rest eines Abbruchs
VERSIONEN_HINWEIS_MB = 1024

DATEIEN, PERSOENLICH, ANFRAGEN, ANGEBOTE, PPEASE = "dateien", "persoenlich", "anfragen", "angebote", "ppease"
BEREICHE = ((DATEIEN, "Gemeinsame Dateien"), (PERSOENLICH, "Mein Ordner"), (ANFRAGEN, "Anfragen"),
            (ANGEBOTE, "Angebotsablage"), (PPEASE, "PPEASE-Ablage"))
BEREICH_TITEL = dict(BEREICHE)
NUR_LESEN = {ANFRAGEN}              # Akten der Anfragenverwaltung: Dateien kommen über die Anfragen-Seite dazu
OHNE_ORDNER_OBEN = {PPEASE}         # oberste Ebene: Angebotsordner legt PPEASE an, nie das Programm

# Status (Master-Auftrag Abschnitt 6); „Ungesehen“ ist zusätzlich je Mitarbeiter (gesehen-Merker)
NEU, UNGESEHEN, BEARBEITUNG, RUECKFRAGE, FERTIG, ARCHIVIERT = (
    "Neu", "Ungesehen", "In Bearbeitung", "Rückfrage erforderlich", "Fertiggestellt", "Archiviert")
STATUS = (NEU, UNGESEHEN, BEARBEITUNG, RUECKFRAGE, FERTIG, ARCHIVIERT)
PRIORITAETEN = ("niedrig", "normal", "hoch", "eilt")

# Dateitypen: Endung -> (Art, Text)
_ARTEN = (("step", "STEP/CAD", (".step", ".stp", ".igs", ".iges")),
          ("stl", "STL", (".stl",)),
          ("dxf", "DXF/DWG", (".dxf", ".dwg")),
          ("pdf", "PDF", (".pdf",)),
          ("excel", "Excel", (".xlsx", ".xls", ".xlsm", ".ods")),
          ("csv", "CSV", (".csv",)),
          ("laser", "LST/BPF/ArTube", (".lst", ".bpf", ".artube", ".tubx", ".mac")),
          ("mail", "E-Mail", (".msg", ".eml")),
          ("zip", "Archiv", (".zip", ".7z", ".rar")),
          ("bild", "Bild", (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")),
          ("word", "Word", (".docx", ".doc", ".docm", ".odt", ".rtf")),
          ("text", "Text", (".txt", ".log", ".xml", ".json", ".ini", ".nc")))
ENDUNG_ART = {e: a for a, _, es in _ARTEN for e in es}
ART_TEXT = {a: t for a, t, _ in _ARTEN}
ART_TEXT.update(ordner="Ordner", datei="Datei")
GEFAEHRLICH = {".exe", ".bat", ".cmd", ".com", ".js", ".jse", ".vbs", ".vbe", ".ps1", ".scr", ".lnk", ".msi", ".hta",
               ".pif", ".cpl", ".reg", ".wsf"}
VERBOTEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Rechte (Abschnitt 9). Solange die Benutzerverwaltung aus ist, darf jeder alles außer endgültig löschen (Admin).
LESEN, HOCHLADEN, BEARBEITEN, VERSCHIEBEN, LOESCHEN, FREIGEBEN, ARCHIVIEREN, VERWALTEN = (
    "lesen", "hochladen", "bearbeiten", "verschieben", "loeschen", "freigeben", "archivieren", "verwalten")
AKTIONEN = ((LESEN, "Lesen"), (HOCHLADEN, "Hochladen"), (BEARBEITEN, "Bearbeiten"), (VERSCHIEBEN, "Verschieben"),
            (LOESCHEN, "Löschen"), (FREIGEBEN, "Freigeben"), (ARCHIVIEREN, "Archivieren"), (VERWALTEN, "Verwalten"))
AKTION_TEXT = dict(AKTIONEN)
RECHTE = "austausch_rechte"         # Einstellung {Rolle: [Aktionen]}; leer = RECHTE_VORGABE
_ALLE = tuple(a for a, _ in AKTIONEN)
RECHTE_VORGABE = {"admin": _ALLE, "leitung": _ALLE[:-1], "kalkulation": _ALLE[:-1], "av": _ALLE[:-1],
                  "werkstatt": (LESEN, HOCHLADEN), "qs": (LESEN, HOCHLADEN, BEARBEITEN), "versand": (LESEN, HOCHLADEN)}

# ------------------------------------------------------------------ Tabellen (geteilt, Abgleich)
DATEIEN_T = Tabelle(
    "austausch_dateien", "Austausch: Dateien",
    (Feld("datei", "Datei", pflicht=True, breite=260),       # Schlüssel „bereich:pfad/name.ext“
     Feld("name", "Name", breite=180),
     Feld("art", "Art", breite=70),
     Feld("groesse", "Größe", "ganz", breite=70),
     Feld("pruefsumme", "Prüfsumme", breite=90),
     Feld("kundennr", "Kunde", breite=80),
     Feld("angebot", "Angebot", breite=90),
     Feld("auftrag", "Auftrag", breite=90),
     Feld("ppease", "PPEASE-Nr.", breite=90),
     Feld("anfrage", "Anfrage", breite=90),
     Feld("bauteil", "Bauteil/Artikel", breite=110),
     Feld("projekt", "Projekt", breite=120),
     Feld("vorschlag", "Vorschlag (unbestätigt)", breite=160),       # JSON [{feld, wert, grund}]
     Feld("bearbeiter", "Verantwortlich", breite=60),
     Feld("status", "Status", breite=100),
     Feld("prioritaet", "Priorität", breite=60),
     Feld("faellig", "Fällig", breite=80),
     Feld("aufgabe", "Aufgabe", breite=200),
     Feld("notiz", "Interne Notiz", breite=200),
     Feld("hochgeladen_von", "Hochgeladen von", breite=60),
     Feld("hochgeladen_am", "Hochgeladen am", breite=130),
     Feld("geaendert_von", "Geändert von", breite=60),
     Feld("geaendert_am", "Geändert am", breite=130),
     Feld("weg", "Gelöscht/verschoben", breite=60)),         # ja = Datei im Papierkorb
    ("datei",),
    "Metadaten der Dateien im Austauschordner (austausch_dateien.py); die Dateien selbst liegen im gemeinsamen Ordner.")
EREIGNISSE_T = Tabelle(
    "austausch_ereignisse", "Austausch: Verlauf",
    (Feld("datei", "Datei", pflicht=True, breite=260),
     Feld("zeit", "Zeit", breite=130),
     Feld("wer", "Wer", breite=60),
     Feld("art", "Art", breite=90),
     Feld("an", "An", breite=60),
     Feld("feld", "Feld", breite=90),
     Feld("alt", "Alt", breite=140),
     Feld("neu", "Neu", breite=140),
     Feld("text", "Text", breite=240)),
    (),
    "Kommentare und Verlauf je Datei im Austauschordner; nur angehängt (austausch_dateien.py).")
TABELLEN = (DATEIEN_T, EREIGNISSE_T)

ZUORDNUNG = (("kundennr", "Kunde"), ("angebot", "Angebot"), ("auftrag", "Auftrag"), ("ppease", "PPEASE-Nr."),
             ("anfrage", "Anfrage"), ("bauteil", "Bauteil/Artikel"), ("projekt", "Projekt"))
ARBEIT = (("bearbeiter", "Verantwortlich"), ("status", "Status"), ("prioritaet", "Priorität"),
          ("faellig", "Fällig"), ("aufgabe", "Aufgabe"), ("notiz", "Interne Notiz"))
FELD_TEXT = dict(ZUORDNUNG + ARBEIT)
FELDER = tuple(n for n, _ in ZUORDNUNG + ARBEIT)

# Ereignisarten
E_HOCH, E_VERSION, E_UMBENANNT, E_VERSCHOBEN, E_KOPIERT, E_GELOESCHT, E_ZURUECK, E_ARCHIV, E_FELD, E_KOMMENTAR, \
    E_ZUGEWIESEN, E_SPERRE, E_ENDGUELTIG, E_ORDNER = (
        "hochgeladen", "neue_version", "umbenannt", "verschoben", "kopiert", "geloescht", "wiederhergestellt",
        "archiviert", "geaendert", "kommentar", "zugewiesen", "bearbeitung", "endgueltig", "ordner")
E_TEXT = {E_HOCH: "Hochgeladen", E_VERSION: "Neue Version", E_UMBENANNT: "Umbenannt", E_VERSCHOBEN: "Verschoben",
          E_KOPIERT: "Kopiert", E_GELOESCHT: "In den Papierkorb", E_ZURUECK: "Wiederhergestellt",
          E_ARCHIV: "Archiviert", E_FELD: "Geändert", E_KOMMENTAR: "Kommentar", E_ZUGEWIESEN: "Zugewiesen",
          E_SPERRE: "Bearbeitung begonnen", E_ENDGUELTIG: "Endgültig gelöscht", E_ORDNER: "Ordner angelegt"}

# lokale Einstellungen (nicht in stammdaten.EINSTELLUNGEN, darum nur dieser Arbeitsplatz)
L_FAVORITEN, L_ZULETZT, L_GESEHEN, L_SUCHEN, L_ANSICHT = (
    "austausch_favoriten", "austausch_zuletzt", "austausch_gesehen", "austausch_suchen", "austausch_ansicht")
ZULETZT_MAX = 30


class AustauschFehler(Exception):
    """Für den Benutzer bestimmter Fehler einer Dateioperation."""


class Konflikt(AustauschFehler):
    """Die Datei wurde seit dem Öffnen von jemand anderem geändert (optimistische Prüfung über die Prüfsumme)."""
    def __init__(self, text, wer=""):
        super().__init__(text)
        self.wer = wer


# ------------------------------------------------------------------ Hilfen
def _merken(db, name, wert):
    """Eigene Ansichtsdaten dieses Platzes speichern (Favoriten, gesehen, Meldestand); im Lesemodus nicht."""
    if getattr(db, "nur_lesen", False):
        return
    db.einstellung_setzen(name, wert)


def jetzt():
    return datetime.datetime.now().isoformat(sep=" ", timespec="seconds")


def kuerzel(db):
    from . import rollen
    try:
        return rollen.angemeldet(db) or ""
    except Exception:           # noqa: BLE001 – alte Datei ohne Benutzerverwaltung
        from . import teilen
        return teilen.kuerzel(db)


def art(name, ordner=False):
    if ordner:
        return "ordner"
    return ENDUNG_ART.get(Path(name).suffix.lower(), "datei")


def groesse_text(n):
    n = float(n or 0)
    for e in ("B", "KB", "MB", "GB"):
        if n < 1024 or e == "GB":
            return f"{n:.0f} {e}" if e == "B" else f"{n:.1f} {e}".replace(".", ",")
        n /= 1024
    return ""


def name_pruefen(name):
    """Dateiname für Windows prüfen; Ergebnis: bereinigter Name. AustauschFehler bei unzulässigem Namen."""
    n = str(name or "").strip().rstrip(". ")
    if not n:
        raise AustauschFehler("Bitte einen Namen eingeben.")
    if VERBOTEN.search(n):
        raise AustauschFehler('Der Name darf diese Zeichen nicht enthalten: < > : " / \\ | ? *')
    if n.startswith(("_", ".", "~$")):
        raise AustauschFehler("Namen mit _ . oder ~$ am Anfang sind für das Programm reserviert.")
    if Path(n).stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                                *(f"LPT{i}" for i in range(1, 10))}:
        raise AustauschFehler(f"„{n}“ ist unter Windows als Name nicht erlaubt.")
    if len(n) > 180:
        raise AustauschFehler("Der Name ist zu lang (höchstens 180 Zeichen).")
    return n


def pruefsumme(pfad, block=BLOCK):
    h = hashlib.sha1()
    with open(pfad, "rb") as f:
        while True:
            b = f.read(block)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def suchtext(text):
    """Klein, Umlaute ausgeschrieben (ü -> ue: „mueller“ findet „Müller“), ohne übrige Akzente."""
    t = str(text or "").lower().translate(_UMLAUTE)
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def schluessel(bereich, rel):
    return f"{bereich}:{str(rel).replace(os.sep, '/').strip('/')}"


def zerlegen(datei):
    b, _, rel = str(datei).partition(":")
    return b, rel


def intern(name):
    return name.startswith(("_", ".", "~$")) or name.endswith((TEIL, ".neu", ".tmp")) or name in (
        "Thumbs.db", "desktop.ini", "kopf.json", "verlauf.json")


# ------------------------------------------------------------------ Bereiche
def gemeinsam(db):
    """Ordner der gemeinsamen Dateien: <gemeinsamer Ordner>/Austausch, ohne gemeinsamen Ordner neben der Datendatei."""
    from . import teilen
    o = teilen.ordner(db) if teilen.aktiv(db) else None
    if o is not None:
        return Path(o) / ORDNER
    return Path(getattr(db, "pfad", ".")).parent / ORDNER


def wurzeln(db, anlegen=False):
    """{Bereich: Ordner oder None}. anlegen: Austausch/ und den eigenen persönlichen Ordner anlegen."""
    g = gemeinsam(db)
    k = kuerzel(db) or "ICH"
    out = {DATEIEN: g, PERSOENLICH: g / PERSOENLICH_ORDNER / k}
    if anlegen:
        try:
            out[PERSOENLICH].mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    try:
        from . import anfragen_akten
        out[ANFRAGEN] = anfragen_akten.wurzel(db) if anfragen_akten.aktiv(db) else None
    except Exception:           # noqa: BLE001
        out[ANFRAGEN] = None
    try:
        from . import teilen
        a = teilen.unterordner(db, teilen.ANGEBOTE, "teilen_ablage")
        if a is None:
            from . import ausgabe
            eigen = db.einstellung("ablageordner")
            a = ausgabe.ablageordner(eigen, Path(getattr(db, "pfad", ".")).parent / ausgabe.ABLAGE) if eigen else None
        out[ANGEBOTE] = a
    except Exception:           # noqa: BLE001
        out[ANGEBOTE] = None
    try:
        from . import ppease_ablage
        p = ppease_ablage.vorgaben(db).ordner
        out[PPEASE] = Path(p) if p else None
    except Exception:           # noqa: BLE001
        out[PPEASE] = None
    return out


def pfad(db, datei, w=None):
    """Datei-Schlüssel -> Pfad (oder None, wenn der Bereich nicht eingerichtet ist)."""
    b, rel = zerlegen(datei)
    w = w if w is not None else wurzeln(db)
    if w.get(b) is None:
        return None
    p = Path(w[b]) / rel if rel else Path(w[b])
    return p


# ------------------------------------------------------------------ Dateiindex
@dataclasses.dataclass
class Eintrag:
    bereich: str
    rel: str                # relativ zum Bereich, mit /
    name: str
    ordner: bool
    groesse: int = 0
    zeit: float = 0.0       # Änderungszeit (Unix)
    archiv: bool = False    # liegt unter _Archiv
    office: str = ""        # Office-Sperrdatei gefunden: wer (laut Datei) bearbeitet sie gerade

    @property
    def datei(self):
        return schluessel(self.bereich, self.rel)

    @property
    def art(self):
        return art(self.name, self.ordner)

    @property
    def endung(self):
        return Path(self.name).suffix.lower()

    @property
    def ordner_rel(self):
        return self.rel.rpartition("/")[0]


def office_besitzer(p):
    """Name aus einer Office-Sperrdatei ~$… (erstes Byte Länge, dann der Benutzername); leer, wenn unlesbar."""
    try:
        b = Path(p).read_bytes()[:200]
    except OSError:
        return ""
    if not b:
        return ""
    n = b[0]
    t = b[1:1 + n].decode("latin-1", "ignore").strip()
    return t if t.isprintable() else ""


def _office_ziel(sperr, namen):
    """Zu welcher Datei gehört die Office-Sperrdatei? Excel: ~$ + Name; Word ersetzt bei längeren Namen die ersten
    zwei Zeichen durch ~$."""
    rest = sperr[2:]
    for n in namen:
        if n == rest or (len(n) > 2 and n[2:] == rest):
            return n
    return None


def einlesen(wurzel, bereich, abbrechen=None, tiefe=12):
    """Alle Dateien und Ordner eines Bereichs: [Eintrag]. Interne Ordner/Dateien bleiben weg; _Archiv wird
    mitgelesen (archiv=True). Bei den Anfragen-Akten nur deren Ordner Dateien."""
    wurzel = Path(wurzel)
    out = []
    if not wurzel.is_dir():
        return out

    def lauf(o, rel, stufe, archiv):
        if stufe > tiefe or (abbrechen and abbrechen()):
            return
        try:
            liste = list(os.scandir(o))
        except OSError:
            return
        namen = [e.name for e in liste]
        sperren = {}
        for e in liste:
            if e.name.startswith("~$"):
                z = _office_ziel(e.name, namen)
                if z:
                    sperren[z] = office_besitzer(e.path) or "Office"
        for e in sorted(liste, key=lambda x: x.name.lower()):
            n = e.name
            r = f"{rel}/{n}" if rel else n
            try:
                ist_ordner = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if n == ARCHIV and ist_ordner and not archiv:
                lauf(e.path, r, stufe + 1, True)
                continue
            if intern(n):
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            out.append(Eintrag(bereich, r, n, ist_ordner, 0 if ist_ordner else st.st_size, st.st_mtime, archiv,
                               sperren.get(n, "")))
            if ist_ordner:
                lauf(e.path, r, stufe + 1, archiv)

    lauf(wurzel, "", 0, False)
    return out


def alle(db, bereiche=None, abbrechen=None, w=None):
    """{Bereich: [Eintrag]} der eingerichteten Bereiche (ohne „Mein Ordner“ im Bereich Gemeinsame Dateien)."""
    w = w if w is not None else wurzeln(db, anlegen=True)
    out = {}
    for b, _ in BEREICHE:
        if (bereiche and b not in bereiche) or w.get(b) is None:
            continue
        out[b] = einlesen(w[b], b, abbrechen)
    return out


# ------------------------------------------------------------------ Rechte
def _rollen(db):
    from . import rollen
    k = rollen.angemeldet(db)
    e = rollen.benutzer(db).get(k) or {}
    return k, e


def rechte(db):
    t = db.einstellung(RECHTE) or {}
    return {r: tuple(t.get(r, v)) for r, v in RECHTE_VORGABE.items()} | {r: tuple(v) for r, v in t.items()
                                                                          if r not in RECHTE_VORGABE}


def darf(db, aktion):
    """Darf der angemeldete Benutzer diese Aktion im Austauschordner? Ohne Benutzerverwaltung alles außer
    endgültig löschen (nur Admin, siehe darf_endgueltig)."""
    from . import rollen
    try:
        if not rollen.aktiv(db) or rollen._admin_frei(db):
            return True
        _, e = _rollen(db)
    except Exception:           # noqa: BLE001
        return True
    if not e or not e.get("aktiv", True) or not e.get("rollen"):
        return aktion == LESEN
    t = rechte(db)
    return any(aktion in t.get(r, ()) for r in e["rollen"])


def darf_endgueltig(db):
    """Endgültig löschen und den Papierkorb leeren: Rolle Administrator (Benutzerverwaltung) oder freigeschalteter
    Admin (Admin-Schutz); ohne Admin-Passwort der Arbeitsplatz selbst (sonst sperrt sich ein Einzelplatz aus)."""
    from . import admin_schutz, rollen
    try:
        if rollen.aktiv(db) and "admin" in (_rollen(db)[1].get("rollen") or ()):
            return True
        return admin_schutz.ist_admin(db)
    except Exception:           # noqa: BLE001
        return False


def pruefen(db, aktion):
    if not darf(db, aktion):
        raise AustauschFehler(f"Keine Berechtigung zum {AKTION_TEXT[aktion]} im Austauschordner. Rechte vergibt der "
                              "Administrator (Einstellungen → Benutzer und Rollen).")


def _schreibbar(bereich, ordner_rel=None, neuer_ordner=False):
    if bereich in NUR_LESEN:
        raise AustauschFehler("Die Akten der Anfragen werden über die Seite Anfragen geändert. Hier kannst du sie "
                              "ansehen, herunterladen und kopieren.")
    if neuer_ordner and bereich in OHNE_ORDNER_OBEN and not ordner_rel:
        raise AustauschFehler("In der PPEASE-Ablage legt PPEASE die Angebotsordner an. Wähle zuerst einen "
                              "Angebotsordner.")


# ------------------------------------------------------------------ Metadaten
def _zeile(r, spalten):
    return {s: r[i] for i, s in enumerate(spalten)}


_SPALTEN = tuple(f.name for f in DATEIEN_T.felder)


def meta(db, datei=None):
    """Metadaten: mit datei ein dict (leer, wenn keine), sonst {Datei: dict} aller Dateien."""
    sql = f'SELECT {", ".join(chr(34) + s + chr(34) for s in _SPALTEN)} FROM austausch_dateien'
    if datei is not None:
        r = db.con.execute(sql + " WHERE datei=?", (datei,)).fetchone()
        return _zeile(r, _SPALTEN) if r else {}
    return {r[0]: _zeile(r, _SPALTEN) for r in db.con.execute(sql)}


def vorschlaege(m):
    try:
        return list(json.loads(m.get("vorschlag") or "[]"))
    except ValueError:
        return []


def ereignis(db, datei, art_, text="", an="", feld="", alt=None, neu=None, zeit=None, wer=None):
    db.con.execute("INSERT INTO austausch_ereignisse (datei, zeit, wer, art, an, feld, alt, neu, text) VALUES "
                   "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (datei, zeit or jetzt(), kuerzel(db) if wer is None else wer, art_, an or "", feld or "",
                    None if alt is None else str(alt), None if neu is None else str(neu), text or ""))


def _meta_schreiben(db, datei, werte):
    """Zeile anlegen oder die genannten Felder setzen (ohne Verlauf)."""
    if not werte:
        return
    vorhanden = db.con.execute("SELECT 1 FROM austausch_dateien WHERE datei=?", (datei,)).fetchone()
    if vorhanden:
        teile = ", ".join(f'"{k}"=?' for k in werte)
        db.con.execute(f"UPDATE austausch_dateien SET {teile} WHERE datei=?", (*werte.values(), datei))
    else:
        alle_ = dict(werte, datei=datei)
        alle_.setdefault("name", zerlegen(datei)[1].rpartition("/")[2])
        db.con.execute(f'INSERT INTO austausch_dateien ({", ".join(chr(34) + k + chr(34) for k in alle_)}) VALUES '
                       f'({", ".join("?" * len(alle_))})', tuple(alle_.values()))


def setzen(db, dateien, **werte):
    """Zuordnungs- und Arbeitsfelder für eine oder mehrere Dateien setzen; jede Änderung kommt in den Verlauf.
    Bestätigte Vorschläge verschwinden aus 'vorschlag'. Ergebnis: Anzahl geänderter Felder."""
    pruefen(db, BEARBEITEN)
    if isinstance(dateien, str):
        dateien = [dateien]
    for k in werte:
        if k not in FELDER:
            raise AustauschFehler(f"Unbekanntes Feld {k}.")
    if "status" in werte and werte["status"] and werte["status"] not in STATUS:
        raise AustauschFehler(f"Unbekannter Status {werte['status']}.")
    if "prioritaet" in werte and werte["prioritaet"] and werte["prioritaet"] not in PRIORITAETEN:
        raise AustauschFehler(f"Unbekannte Priorität {werte['prioritaet']}.")
    if werte.get("faellig"):
        try:
            datetime.date.fromisoformat(str(werte["faellig"])[:10])
        except ValueError as e:
            raise AustauschFehler("Fällig bitte als Datum JJJJ-MM-TT.") from e
    n = 0
    z = jetzt()
    ich = kuerzel(db)
    with db.con:
        for d in dateien:
            alt = meta(db, d)
            neu = {}
            for k, v in werte.items():
                v = None if v in ("", None) else str(v).strip()
                if (alt.get(k) or None) != v:
                    neu[k] = v
            if not neu:
                continue
            vs = [x for x in vorschlaege(alt) if x.get("feld") not in neu]
            if len(vs) != len(vorschlaege(alt)):
                neu["vorschlag"] = json.dumps(vs, ensure_ascii=False) if vs else None
            neu.update(geaendert_von=ich, geaendert_am=z)
            _meta_schreiben(db, d, neu)
            for k, v in neu.items():
                if k in FELDER:
                    n += 1
                    ereignis(db, d, E_ZUGEWIESEN if k == "bearbeiter" else E_FELD, feld=k, alt=alt.get(k), neu=v,
                             an=v if k == "bearbeiter" else "", zeit=z, wer=ich)
    return n


def vorschlag_bestaetigen(db, datei, felder=None):
    """Unsichere Vorschläge übernehmen (alle oder die genannten Felder)."""
    m = meta(db, datei)
    werte = {x["feld"]: x["wert"] for x in vorschlaege(m) if felder is None or x["feld"] in felder}
    return setzen(db, datei, **werte) if werte else 0


def vorschlag_verwerfen(db, datei, felder=None):
    m = meta(db, datei)
    vs = [x for x in vorschlaege(m) if felder is not None and x["feld"] not in felder]
    with db.con:
        _meta_schreiben(db, datei, {"vorschlag": json.dumps(vs, ensure_ascii=False) if vs else None})


def kommentar(db, datei, text, an=""):
    pruefen(db, LESEN)
    t = str(text or "").strip()
    if not t:
        raise AustauschFehler("Bitte einen Kommentar eingeben.")
    with db.con:
        if not meta(db, datei):
            _meta_schreiben(db, datei, {"geaendert_am": jetzt(), "geaendert_von": kuerzel(db)})
        ereignis(db, datei, E_KOMMENTAR, t, an=an)


def verlauf(db, datei=None, seit=None, arten=None, grenze=500):
    """Verlauf (neueste zuerst): [dict(datei, zeit, wer, art, an, feld, alt, neu, text)]."""
    sql, w = "SELECT datei, zeit, wer, art, an, feld, alt, neu, text FROM austausch_ereignisse", []
    bed = []
    if datei is not None:
        bed.append("datei=?")
        w.append(datei)
    if seit:
        bed.append("zeit>?")
        w.append(seit)
    if arten:
        bed.append(f"art IN ({', '.join('?' * len(arten))})")
        w.extend(arten)
    if bed:
        sql += " WHERE " + " AND ".join(bed)
    sql += " ORDER BY zeit DESC, id DESC LIMIT ?"
    w.append(int(grenze))
    k = ("datei", "zeit", "wer", "art", "an", "feld", "alt", "neu", "text")
    return [dict(zip(k, r)) for r in db.con.execute(sql, w)]


def verlauf_text(e):
    a = E_TEXT.get(e["art"], e["art"])
    if e["art"] in (E_FELD, E_ZUGEWIESEN):
        f = FELD_TEXT.get(e["feld"], e["feld"])
        return f"{f}: {e['alt'] or '–'} → {e['neu'] or '–'}"
    if e["art"] == E_KOMMENTAR:
        return f"Kommentar{(' an ' + e['an']) if e.get('an') else ''}: {e['text']}"
    return f"{a}{(': ' + e['text']) if e.get('text') else ''}"


def _umschluesseln(db, alt, neu, ordner=False):
    """Metadaten und Verlauf ziehen beim Umbenennen/Verschieben mit (bei Ordnern alle Dateien darin)."""
    paare = [(alt, neu)]
    if ordner:
        for (d,) in db.con.execute("SELECT datei FROM austausch_dateien WHERE datei LIKE ?", (alt + "/%",)).fetchall():
            paare.append((d, neu + d[len(alt):]))
    for a, n in paare:
        if db.con.execute("SELECT 1 FROM austausch_dateien WHERE datei=?", (n,)).fetchone():
            db.con.execute("DELETE FROM austausch_dateien WHERE datei=? AND (bearbeiter IS NULL AND status IS NULL "
                           "AND kundennr IS NULL AND angebot IS NULL AND auftrag IS NULL)", (n,))
        if not db.con.execute("SELECT 1 FROM austausch_dateien WHERE datei=?", (n,)).fetchone():
            db.con.execute("UPDATE austausch_dateien SET datei=?, name=? WHERE datei=?",
                           (n, n.rpartition("/")[2].partition(":")[2] or n.rpartition("/")[2], a))
        db.con.execute("UPDATE austausch_ereignisse SET datei=? WHERE datei=?", (n, a))


# ------------------------------------------------------------------ Dateioperationen
def _frei(ziel):
    """„name (2).ext“ … – erster freier Name neben ziel."""
    ziel = Path(ziel)
    if not ziel.exists():
        return ziel
    i = 2
    while True:
        k = ziel.with_name(f"{ziel.stem} ({i}){ziel.suffix}")
        if not k.exists():
            return k
        i += 1


def _kopieren(quelle, ziel, fortschritt=None, abbrechen=None, gesamt=None):
    """In ziel.rlteil kopieren, Größe prüfen, dann in einem Schritt umbenennen. Bei Abbruch/Fehler bleibt nichts
    Halbes liegen. Ergebnis: Bytes."""
    quelle, ziel = Path(quelle), Path(ziel)
    teil = ziel.with_name(ziel.name + TEIL)
    n = 0
    groesse = quelle.stat().st_size
    try:
        with open(quelle, "rb") as q, open(teil, "wb") as z:
            while True:
                if abbrechen and abbrechen():
                    raise AustauschFehler("Abgebrochen.")
                b = q.read(BLOCK)
                if not b:
                    break
                z.write(b)
                n += len(b)
                if fortschritt:
                    fortschritt(n, gesamt or groesse)
            z.flush()
            os.fsync(z.fileno())
        if teil.stat().st_size != groesse:
            raise AustauschFehler(f"{quelle.name}: Kopie unvollständig ({teil.stat().st_size} von {groesse} Bytes).")
        shutil.copystat(quelle, teil)
        os.replace(teil, ziel)
    except BaseException:
        try:
            teil.unlink()
        except OSError:
            pass
        raise
    return n


def version_name(ziel, nummer, k, zeit=None):
    zeit = zeit or datetime.datetime.fromtimestamp(Path(ziel).stat().st_mtime)
    return f"{Path(ziel).stem}_V{nummer}_{zeit:%Y-%m-%d_%H%M%S}_{k or 'X'}{Path(ziel).suffix}"


_VERSION = re.compile(r"^(?P<stem>.*)_V(?P<n>\d+)_(?P<zeit>\d{4}-\d{2}-\d{2}_\d{4,6})(?:_(?P<wer>[A-Z0-9ÄÖÜX]{1,5}))?"
                      r"(?:_\d+)?(?P<endung>\.[^.]*)?$")


def versionen(p):
    """Gesicherte Fassungen einer Datei (neueste zuerst): [dict(pfad, nummer, zeit, wer, groesse)]."""
    p = Path(p)
    vo = p.parent / VERSIONEN
    out = []
    if not vo.is_dir():
        return out
    for v in vo.iterdir():
        m = _VERSION.match(v.name)
        if not m or m.group("stem") != p.stem or (m.group("endung") or "") != p.suffix:
            continue
        try:
            st = v.stat()
        except OSError:
            continue
        out.append(dict(pfad=v, nummer=int(m.group("n")), zeit=m.group("zeit"), wer=m.group("wer") or "",
                        groesse=st.st_size))
    return sorted(out, key=lambda x: (x["nummer"], x["zeit"]), reverse=True)


def version_sichern(p, k, verschieben=False):
    """Aktuelle Fassung nach _Versionen kopieren (verschieben=True: verschieben). Ergebnis: Pfad der Version."""
    p = Path(p)
    vo = p.parent / VERSIONEN
    vo.mkdir(parents=True, exist_ok=True)
    nr = max((v["nummer"] for v in versionen(p)), default=0) + 1
    ziel = vo / version_name(p, nr, k)
    ziel = _frei(ziel)
    if verschieben:
        os.replace(p, ziel)
    else:
        _kopieren(p, ziel)
    return ziel


def system(w):
    """Ordner für Sperren und laufende Uploads aller Bereiche: Austausch/_Plattform (nie in der PPEASE-Ablage)."""
    return Path(w[DATEIEN]) / SYSTEM


def korb(w, bereich, rel=""):
    """Papierkorb: <Bereich>/_Papierkorb; in der PPEASE-Ablage im Angebotsordner (oberste Ebene bleibt PPEASE)."""
    if bereich == PPEASE:
        return Path(w[bereich]) / rel.split("/")[0] / PAPIERKORB
    return Path(w[bereich]) / PAPIERKORB


def _upload_marker(w, datei, k):
    """Exklusiver Marker „Upload läuft“ in Austausch/_Plattform/laeuft (O_EXCL); None, wenn schon jemand lädt."""
    o = system(w) / "laeuft"
    o.mkdir(parents=True, exist_ok=True)
    m = o / (hashlib.sha1(datei.encode()).hexdigest()[:20] + ".json")
    if m.exists() and time.time() - m.stat().st_mtime > UPLOAD_ALT_S:
        try:
            m.unlink()                  # Rest eines abgebrochenen Uploads
        except OSError:
            pass
    try:
        fd = os.open(m, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dict(datei=datei, wer=k, platz=socket.gethostname(), seit=jetzt()), f)
    return m


def laufende_uploads(db, w=None):
    """[dict(datei, wer, platz, seit)] der gerade laufenden Uploads aller Plätze."""
    w = w if w is not None else wurzeln(db)
    out = []
    lo = system(w) / "laeuft"
    if lo.is_dir():
        for m in lo.glob("*.json"):
            try:
                if time.time() - m.stat().st_mtime > UPLOAD_ALT_S:
                    continue
                out.append(json.loads(m.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return out


@dataclasses.dataclass
class Bericht:
    neu: list = dataclasses.field(default_factory=list)          # [Datei-Schlüssel]
    versionen: list = dataclasses.field(default_factory=list)    # [(Datei, gesicherte Fassung)]
    umbenannt: list = dataclasses.field(default_factory=list)    # [(Quelle-Name, neuer Datei-Schlüssel)] (beide behalten)
    uebersprungen: list = dataclasses.field(default_factory=list)  # [(Name, Grund)]
    fehler: list = dataclasses.field(default_factory=list)       # [(Name, Text)]
    abgebrochen: bool = False

    @property
    def ok(self):
        return not self.fehler and not self.abgebrochen

    def text(self):
        t = []
        if self.neu:
            t.append(f"{len(self.neu)} Datei(en) abgelegt")
        if self.versionen:
            t.append(f"{len(self.versionen)} als neue Version (alte Fassung gesichert)")
        if self.umbenannt:
            t.append(f"{len(self.umbenannt)} unter neuem Namen (Name war belegt)")
        if self.uebersprungen:
            t.append(f"{len(self.uebersprungen)} übersprungen")
        if self.fehler:
            t.append(f"{len(self.fehler)} Fehler: " + "; ".join(f"{n}: {e}" for n, e in self.fehler[:3]))
        if self.abgebrochen:
            t.append("abgebrochen")
        return ", ".join(t) or "Nichts zu tun."


VERSION, BEIDE, UEBERSPRINGEN = "version", "beide", "ueberspringen"


def _quellen(quellen):
    """[(Pfad, relativer Zielname)] – Ordner werden mit ihrem Inhalt übernommen."""
    out = []
    for q in quellen:
        q = Path(q)
        if q.is_dir():
            for p in sorted(q.rglob("*")):
                if p.is_file() and not intern(p.name):
                    out.append((p, f"{q.name}/{p.relative_to(q).as_posix()}"))
        elif q.is_file():
            out.append((q, q.name))
    return out


def hochladen(db, quellen, bereich, ordner_rel="", konflikt=None, fortschritt=None, abbrechen=None, erkennen=True,
              w=None):
    """Dateien (oder Ordner) in den Bereich kopieren. konflikt(name) -> VERSION | BEIDE | UEBERSPRINGEN entscheidet bei
    belegtem Namen (Vorgabe: beide behalten). fortschritt(bytes, gesamt, name). Danach Zuordnung erkennen (sichere
    Treffer gesetzt, unsichere als Vorschlag). Ergebnis: Bericht."""
    pruefen(db, HOCHLADEN)
    _schreibbar(bereich)
    w = w if w is not None else wurzeln(db, anlegen=True)
    if w.get(bereich) is None:
        raise AustauschFehler(f"{BEREICH_TITEL.get(bereich, bereich)} ist nicht eingerichtet.")
    basis = Path(w[bereich]) / ordner_rel if ordner_rel else Path(w[bereich])
    if bereich == PPEASE and not ordner_rel:
        raise AustauschFehler("In der PPEASE-Ablage bitte zuerst einen Angebotsordner wählen.")
    liste = _quellen(quellen)
    gesamt = sum(p.stat().st_size for p, _ in liste) or 1
    erledigt = 0
    b = Bericht()
    k = kuerzel(db)
    for q, rel_name in liste:
        if abbrechen and abbrechen():
            b.abgebrochen = True
            break
        if q.suffix.lower() in GEFAEHRLICH:
            b.uebersprungen.append((q.name, "ausführbare Datei, aus Sicherheitsgründen nicht übernommen"))
            continue
        try:
            for teil in rel_name.split("/"):
                name_pruefen(teil)
        except AustauschFehler as e:
            b.uebersprungen.append((q.name, str(e)))
            continue
        ziel = basis / rel_name
        try:
            if ziel.resolve() == q.resolve():
                b.uebersprungen.append((q.name, "liegt schon hier"))
                continue
        except OSError:
            pass
        ziel.parent.mkdir(parents=True, exist_ok=True)
        modus = None
        if ziel.exists():
            modus = konflikt(rel_name) if konflikt else BEIDE
            if modus == UEBERSPRINGEN or modus is None:
                b.uebersprungen.append((q.name, "Name schon vorhanden"))
                erledigt += q.stat().st_size
                continue
            if modus == BEIDE:
                ziel = _frei(ziel)
        rel = ziel.relative_to(Path(w[bereich])).as_posix()
        datei = schluessel(bereich, rel)
        marker = _upload_marker(w, datei, k)
        if marker is None:
            b.fehler.append((q.name, "Ein Kollege lädt diese Datei gerade hoch."))
            continue
        try:
            gesichert = None
            if modus == VERSION and ziel.exists():
                gesichert = version_sichern(ziel, k)

            def fs(n, _g, _n0=erledigt, _name=q.name):
                if fortschritt:
                    fortschritt(_n0 + n, gesamt, _name)
                if marker is not None and int(time.time()) % 5 == 0:
                    try:
                        os.utime(marker)
                    except OSError:
                        pass
            _kopieren(q, ziel, fs, abbrechen)
            erledigt += q.stat().st_size
            summe = pruefsumme(ziel) if ziel.stat().st_size <= 200 << 20 else None
            werte = dict(name=ziel.name, art=art(ziel.name), groesse=ziel.stat().st_size, pruefsumme=summe,
                         geaendert_von=k, geaendert_am=jetzt(), weg=None)
            with db.con:
                if gesichert is None:
                    werte.update(hochgeladen_von=k, hochgeladen_am=jetzt())
                    if not meta(db, datei).get("status"):
                        werte["status"] = NEU
                _meta_schreiben(db, datei, werte)
                ereignis(db, datei, E_VERSION if gesichert else E_HOCH, q.name if q.name != ziel.name else "")
            if gesichert is not None:
                b.versionen.append((datei, gesichert))
            elif modus == BEIDE:
                b.umbenannt.append((q.name, datei))
            else:
                b.neu.append(datei)
            if erkennen:
                try:
                    from . import austausch_zuordnung
                    austausch_zuordnung.anwenden(db, datei, ziel)
                except Exception as e:          # noqa: BLE001 – Zuordnung ist Zugabe, die Datei liegt
                    from . import protokoll
                    protokoll.warnung(f"Austausch: Zuordnung {datei}: {e!r}")
        except AustauschFehler as e:
            if str(e) == "Abgebrochen.":
                b.abgebrochen = True
                break
            b.fehler.append((q.name, str(e)))
        except OSError as e:
            b.fehler.append((q.name, f"{e.strerror or e}"))
        finally:
            try:
                marker.unlink()
            except OSError:
                pass
    return b


def neue_version(db, datei, quelle, basis_pruefsumme=None, w=None):
    """Bearbeitete Fassung als neue Version ablegen. Mit basis_pruefsumme (Stand beim Öffnen) wird geprüft, ob
    inzwischen jemand anderes eine neue Fassung abgelegt hat: dann Konflikt (nichts überschrieben)."""
    pruefen(db, BEARBEITEN)
    b, _ = zerlegen(datei)
    _schreibbar(b)
    p = pfad(db, datei, w)
    if p is None or not p.is_file():
        raise AustauschFehler("Die Datei gibt es nicht mehr (verschoben oder gelöscht?).")
    if basis_pruefsumme and pruefsumme(p) != basis_pruefsumme:
        v = versionen(p)[:1]            # wer zuletzt ersetzt hat, steht im Namen der gesicherten Fassung (sofort)
        m = meta(db, datei)
        wer = v[0]["wer"] if v and v[0]["wer"] != "X" else (m.get("geaendert_von") or "")
        zeit = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        raise Konflikt(f"{p.name} wurde inzwischen von {wer or 'jemand anderem'} geändert ({zeit}). Deine Fassung "
                       "wurde nicht abgelegt.", wer)
    k = kuerzel(db)
    gesichert = version_sichern(p, k)
    _kopieren(quelle, p)
    with db.con:
        _meta_schreiben(db, datei, dict(groesse=p.stat().st_size, pruefsumme=pruefsumme(p), geaendert_von=k,
                                        geaendert_am=jetzt()))
        ereignis(db, datei, E_VERSION, Path(quelle).name)
    return gesichert


def version_wiederherstellen(db, datei, version_pfad, w=None):
    """Ältere Fassung zurückholen; die aktuelle wird vorher selbst als Version gesichert (nichts geht verloren)."""
    pruefen(db, BEARBEITEN)
    b, _ = zerlegen(datei)
    _schreibbar(b)
    p = pfad(db, datei, w)
    if p is None:
        raise AustauschFehler("Bereich nicht eingerichtet.")
    k = kuerzel(db)
    if p.exists():
        version_sichern(p, k)
    _kopieren(version_pfad, p)
    with db.con:
        _meta_schreiben(db, datei, dict(groesse=p.stat().st_size, pruefsumme=pruefsumme(p), geaendert_von=k,
                                        geaendert_am=jetzt()))
        ereignis(db, datei, E_ZURUECK, f"Fassung {Path(version_pfad).name}")
    return p


def herunterladen(db, dateien, ziel_ordner, fortschritt=None, abbrechen=None, w=None):
    """Kopien in einen lokalen Ordner (vorhandene Dateien dort werden nie überschrieben). Ergebnis: [Pfad]."""
    pruefen(db, LESEN)
    w = w if w is not None else wurzeln(db)
    out = []
    ziel_ordner = Path(ziel_ordner)
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    for d in dateien:
        p = pfad(db, d, w)
        if p is None or not p.exists():
            continue
        if p.is_dir():
            z = _frei(ziel_ordner / p.name)
            shutil.copytree(p, z, ignore=lambda _o, n: [x for x in n if intern(x)])
        else:
            z = _frei(ziel_ordner / p.name)
            _kopieren(p, z, fortschritt, abbrechen)
        out.append(z)
    return out


def ordner_anlegen(db, bereich, ordner_rel, name, w=None):
    pruefen(db, HOCHLADEN)
    _schreibbar(bereich, ordner_rel, neuer_ordner=True)
    n = name_pruefen(name)
    w = w if w is not None else wurzeln(db, anlegen=True)
    if w.get(bereich) is None:
        raise AustauschFehler("Bereich nicht eingerichtet.")
    o = Path(w[bereich]) / ordner_rel / n if ordner_rel else Path(w[bereich]) / n
    if o.exists():
        raise AustauschFehler(f"„{n}“ gibt es hier schon.")
    o.mkdir(parents=True)
    rel = o.relative_to(Path(w[bereich])).as_posix()
    with db.con:
        ereignis(db, schluessel(bereich, rel), E_ORDNER)
    return schluessel(bereich, rel)


def umbenennen(db, datei, neuer_name, w=None):
    pruefen(db, BEARBEITEN)
    b, rel = zerlegen(datei)
    _schreibbar(b)
    if b == PPEASE and "/" not in rel:
        raise AustauschFehler("Angebotsordner der PPEASE-Ablage werden in PPEASE benannt.")
    n = name_pruefen(neuer_name)
    p = pfad(db, datei, w)
    if p is None or not p.exists():
        raise AustauschFehler("Die Datei gibt es nicht mehr.")
    if sperre(db, datei, w) and not sperre(db, datei, w).get("eigene"):
        raise AustauschFehler(f"{p.name} wird gerade von {sperre(db, datei, w)['wer']} bearbeitet.")
    z = p.with_name(n)
    if z.exists() and z.name.lower() != p.name.lower():
        raise AustauschFehler(f"„{n}“ gibt es hier schon.")
    os.replace(p, z)
    neu = schluessel(b, z.relative_to(pfad(db, schluessel(b, ""), w)).as_posix())
    with db.con:
        _umschluesseln(db, datei, neu, ordner=z.is_dir())
        ereignis(db, neu, E_UMBENANNT, f"{p.name} → {n}")
    return neu


def _ziel_ordner(db, bereich, ordner_rel, w):
    if w.get(bereich) is None:
        raise AustauschFehler("Zielbereich nicht eingerichtet.")
    _schreibbar(bereich)
    if bereich == PPEASE and not ordner_rel:
        raise AustauschFehler("In der PPEASE-Ablage bitte einen Angebotsordner als Ziel wählen.")
    o = Path(w[bereich]) / ordner_rel if ordner_rel else Path(w[bereich])
    o.mkdir(parents=True, exist_ok=True)
    return o


def kopieren(db, dateien, bereich, ordner_rel="", w=None):
    """Kopien in einen anderen Ordner (Zuordnung wird mitkopiert). Ergebnis: [neuer Schlüssel]."""
    pruefen(db, HOCHLADEN)
    w = w if w is not None else wurzeln(db, anlegen=True)
    o = _ziel_ordner(db, bereich, ordner_rel, w)
    out = []
    for d in dateien:
        p = pfad(db, d, w)
        if p is None or not p.exists():
            continue
        z = _frei(o / p.name)
        if p.is_dir():
            if o.resolve().is_relative_to(p.resolve()):
                raise AustauschFehler("Ein Ordner lässt sich nicht in sich selbst kopieren.")
            shutil.copytree(p, z, ignore=lambda _o, n: [x for x in n if intern(x)])
        else:
            _kopieren(p, z)
        neu = schluessel(bereich, z.relative_to(Path(w[bereich])).as_posix())
        m = {k: v for k, v in meta(db, d).items() if k in FELDER + ("art", "groesse", "pruefsumme")}
        with db.con:
            _meta_schreiben(db, neu, dict(m, name=z.name, hochgeladen_von=kuerzel(db), hochgeladen_am=jetzt()))
            ereignis(db, neu, E_KOPIERT, f"aus {d}")
        out.append(neu)
    return out


def verschieben(db, dateien, bereich, ordner_rel="", w=None):
    """Verschieben (gleiches Laufwerk: umbenennen; sonst kopieren, prüfen, dann Quelle entfernen). Metadaten und Verlauf
    ziehen mit. Ergebnis: [neuer Schlüssel]."""
    pruefen(db, VERSCHIEBEN)
    w = w if w is not None else wurzeln(db, anlegen=True)
    o = _ziel_ordner(db, bereich, ordner_rel, w)
    out = []
    for d in dateien:
        qb, qrel = zerlegen(d)
        _schreibbar(qb)
        if qb == PPEASE and "/" not in qrel:
            raise AustauschFehler("Angebotsordner der PPEASE-Ablage bleiben, wo PPEASE sie angelegt hat.")
        p = pfad(db, d, w)
        if p is None or not p.exists():
            continue
        s = sperre(db, d, w)
        if s and not s.get("eigene"):
            raise AustauschFehler(f"{p.name} wird gerade von {s['wer']} bearbeitet und bleibt, wo sie ist.")
        if p.is_dir() and o.resolve().is_relative_to(p.resolve()):
            raise AustauschFehler("Ein Ordner lässt sich nicht in sich selbst verschieben.")
        if p.parent.resolve() == o.resolve():
            continue
        z = _frei(o / p.name)
        try:
            os.replace(p, z)
        except OSError:
            if p.is_dir():
                shutil.copytree(p, z)
                shutil.rmtree(p)
            else:
                _kopieren(p, z)
                if z.stat().st_size != p.stat().st_size:
                    raise AustauschFehler(f"{p.name}: Kopie unvollständig, Original bleibt.")
                p.unlink()
        neu = schluessel(bereich, z.relative_to(Path(w[bereich])).as_posix())
        with db.con:
            _umschluesseln(db, d, neu, ordner=z.is_dir())
            ereignis(db, neu, E_VERSCHOBEN, f"aus {d}")
        out.append(neu)
    return out


def archivieren(db, dateien, w=None):
    """Nach <Bereich>/_Archiv/<gleicher Pfad> verschieben, Status Archiviert (bleibt suchbar, Schnellzugriff Archiv)."""
    pruefen(db, ARCHIVIEREN)
    w = w if w is not None else wurzeln(db, anlegen=True)
    out = []
    for d in dateien:
        b, rel = zerlegen(d)
        if rel.startswith(ARCHIV + "/"):
            continue
        neu = verschieben_intern(db, d, b, f"{ARCHIV}/{rel.rpartition('/')[0]}".rstrip("/"), w)
        if neu:
            with db.con:
                _meta_schreiben(db, neu, dict(status=ARCHIVIERT, geaendert_von=kuerzel(db), geaendert_am=jetzt()))
                ereignis(db, neu, E_ARCHIV)
            out.append(neu)
    return out


def verschieben_intern(db, d, bereich, ordner_rel, w):
    b, rel = zerlegen(d)
    _schreibbar(b)
    if b == PPEASE and "/" not in rel:
        raise AustauschFehler("Angebotsordner der PPEASE-Ablage bleiben, wo PPEASE sie angelegt hat.")
    p = pfad(db, d, w)
    if p is None or not p.exists():
        return None
    o = Path(w[bereich]) / ordner_rel
    o.mkdir(parents=True, exist_ok=True)
    z = _frei(o / p.name)
    os.replace(p, z)
    neu = schluessel(bereich, z.relative_to(Path(w[bereich])).as_posix())
    with db.con:
        _umschluesseln(db, d, neu, ordner=z.is_dir())
    return neu


def aus_archiv(db, datei, w=None):
    pruefen(db, ARCHIVIEREN)
    b, rel = zerlegen(datei)
    if not rel.startswith(ARCHIV + "/"):
        return datei
    w = w if w is not None else wurzeln(db)
    neu = verschieben_intern(db, datei, b, rel[len(ARCHIV) + 1:].rpartition("/")[0], w)
    with db.con:
        _meta_schreiben(db, neu, dict(status=BEARBEITUNG, geaendert_von=kuerzel(db), geaendert_am=jetzt()))
        ereignis(db, neu, E_ZURUECK, "aus dem Archiv")
    return neu


def loeschen(db, dateien, w=None):
    """In den Papierkorb des Bereichs verschieben (nie endgültig). Ergebnis: Anzahl."""
    pruefen(db, LOESCHEN)
    w = w if w is not None else wurzeln(db)
    n = 0
    k = kuerzel(db)
    for d in dateien:
        b, rel = zerlegen(d)
        _schreibbar(b)
        if b == PPEASE and "/" not in rel:
            raise AustauschFehler("Angebotsordner der PPEASE-Ablage werden nicht hier gelöscht.")
        p = pfad(db, d, w)
        if p is None or not p.exists():
            continue
        s = sperre(db, d, w)
        if s and not s.get("eigene"):
            raise AustauschFehler(f"{p.name} wird gerade von {s['wer']} bearbeitet und wird nicht gelöscht.")
        ko = korb(w, b, rel)
        ko.mkdir(parents=True, exist_ok=True)
        stempel = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        z = ko / f"{stempel}__{p.name}"
        os.replace(p, z)
        Path(str(z) + ".json").write_text(json.dumps(dict(datei=d, name=p.name, wer=k, zeit=jetzt(),
                                                          ordner=z.is_dir()),
                                                     ensure_ascii=False), encoding="utf-8")
        with db.con:
            _meta_schreiben(db, d, dict(weg="ja", geaendert_von=k, geaendert_am=jetzt()))
            ereignis(db, d, E_GELOESCHT)
        n += 1
    return n


def papierkorb(db, w=None):
    """[dict(pfad, datei, name, wer, zeit, bereich, alter_tage)] aller Papierkörbe, neueste zuerst."""
    w = w if w is not None else wurzeln(db)
    out = []
    heute = datetime.datetime.now()
    for b, o in w.items():
        if o is None or not Path(o).is_dir():
            continue
        muster = f"*/{PAPIERKORB}/*.json" if b == PPEASE else f"{PAPIERKORB}/*.json"
        for j in Path(o).glob(muster):
            try:
                info = json.loads(j.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            p = Path(str(j)[:-5])
            if not p.exists():
                continue
            try:
                alter = (heute - datetime.datetime.fromisoformat(info.get("zeit"))).days
            except (TypeError, ValueError):
                alter = 0
            out.append(dict(info, pfad=p, bereich=b, alter_tage=alter))
    return sorted(out, key=lambda x: x.get("zeit") or "", reverse=True)


def wiederherstellen(db, eintrag, w=None):
    """Datei aus dem Papierkorb an ihren alten Platz (Name belegt: „name (2)“). Ergebnis: Schlüssel."""
    pruefen(db, LOESCHEN)
    w = w if w is not None else wurzeln(db)
    b, rel = zerlegen(eintrag["datei"])
    ziel = _frei(Path(w[b]) / rel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    os.replace(eintrag["pfad"], ziel)
    try:
        Path(str(eintrag["pfad"]) + ".json").unlink()
    except OSError:
        pass
    neu = schluessel(b, ziel.relative_to(Path(w[b])).as_posix())
    with db.con:
        if neu != eintrag["datei"]:
            _umschluesseln(db, eintrag["datei"], neu)
        _meta_schreiben(db, neu, dict(weg=None, geaendert_von=kuerzel(db), geaendert_am=jetzt()))
        ereignis(db, neu, E_ZURUECK, "aus dem Papierkorb")
    return neu


def endgueltig_loeschen(db, eintraege):
    """Nur Admin: Einträge des Papierkorbs wirklich löschen (Verlauf bleibt). Ergebnis: Anzahl."""
    if not darf_endgueltig(db):
        raise AustauschFehler("Endgültig löschen darf nur der Administrator.")
    n = 0
    for e in eintraege:
        p = Path(e["pfad"])
        if PAPIERKORB not in p.parts:
            raise AustauschFehler("Endgültig gelöscht wird nur aus dem Papierkorb.")
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
        try:
            Path(str(p) + ".json").unlink()
        except OSError:
            pass
        with db.con:
            ereignis(db, e["datei"], E_ENDGUELTIG, e.get("name") or "")
        n += 1
    return n


def papierkorb_leeren(db, tage=PAPIERKORB_TAGE, w=None):
    """Nur Admin: Einträge älter als tage endgültig löschen."""
    alt = [e for e in papierkorb(db, w) if e["alter_tage"] >= tage]
    return endgueltig_loeschen(db, alt) if alt else 0


# ------------------------------------------------------------------ Bearbeitungssperre (weich)
def _sperr_datei(w, datei):
    b, _ = zerlegen(datei)
    if w.get(b) is None or w.get(DATEIEN) is None:
        return None
    return system(w) / "sperren" / (hashlib.sha1(datei.encode()).hexdigest()[:20] + ".json")


def sperre(db, datei, w=None, jetzt_=None):
    """Wer bearbeitet die Datei gerade? dict(wer, name, platz, seit, eigene, office) oder None. Gilt SPERRE_MIN ohne
    Lebenszeichen; Office-Sperrdateien (~$…) zählen auch."""
    w = w if w is not None else wurzeln(db)
    s = _sperr_datei(w, datei)
    jetzt_ = jetzt_ or time.time()
    ich = kuerzel(db)
    if s is not None and s.exists():
        try:
            d = json.loads(s.read_text(encoding="utf-8"))
            if jetzt_ - s.stat().st_mtime <= SPERRE_MIN * 60:
                d["eigene"] = d.get("wer") == ich and d.get("platz") == socket.gethostname()
                return d
        except (OSError, ValueError):
            pass
    p = pfad(db, datei, w)
    if p is not None and p.parent.is_dir():
        try:
            namen = [x for x in os.listdir(p.parent) if x.startswith("~$")]
        except OSError:
            namen = []
        for n in namen:
            if _office_ziel(n, [p.name]):
                return dict(wer=office_besitzer(p.parent / n) or "Office", name="", platz="", seit="", eigene=False,
                            office=True)
    return None


def sperren(db, datei, w=None):
    """Eigene Sperre setzen (oder erneuern). Ergebnis: fremde Sperre (dict) oder None (gesetzt)."""
    w = w if w is not None else wurzeln(db)
    fremd = sperre(db, datei, w)
    if fremd and not fremd.get("eigene"):
        return fremd
    s = _sperr_datei(w, datei)
    if s is None:
        return None
    s.parent.mkdir(parents=True, exist_ok=True)
    from . import teilen
    k = kuerzel(db)
    tmp = s.with_suffix(".neu")
    tmp.write_text(json.dumps(dict(datei=datei, wer=k, name=(teilen.mitarbeiter(db, k) or {}).get("name") or "",
                                   platz=socket.gethostname(), seit=(fremd or {}).get("seit") or jetzt()),
                              ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, s)
    return None


def entsperren(db, datei, w=None, auch_fremde=False):
    w = w if w is not None else wurzeln(db)
    s = _sperr_datei(w, datei)
    d = sperre(db, datei, w)
    if s is None or not s.exists() or (d and not d.get("eigene") and not auch_fremde):
        return False
    try:
        s.unlink()
    except OSError:
        return False
    return True


def eigene_sperren_erneuern(db, dateien, w=None):
    """Lebenszeichen der eigenen Sperren (alle paar Minuten aus der Oberfläche)."""
    w = w if w is not None else wurzeln(db)
    for d in dateien:
        s = _sperr_datei(w, d)
        if s is not None and s.exists():
            try:
                os.utime(s)
            except OSError:
                pass


def bearbeiten(db, datei, trotzdem=False, w=None):
    """Bearbeitung beginnen: weiche Sperre setzen und die aktuelle Fassung als Version sichern (falls sie noch nicht
    gesichert ist). Ergebnis: (Pfad, fremde Sperre oder None). Bei fremder Sperre ohne trotzdem passiert nichts."""
    pruefen(db, BEARBEITEN)
    b, _ = zerlegen(datei)
    _schreibbar(b)
    w = w if w is not None else wurzeln(db)
    p = pfad(db, datei, w)
    if p is None or not p.is_file():
        raise AustauschFehler("Die Datei gibt es nicht mehr.")
    fremd = sperre(db, datei, w)
    if fremd and not fremd.get("eigene") and not trotzdem:
        return p, fremd
    if not fremd or fremd.get("eigene") or not fremd.get("office"):
        _datei = _sperr_datei(w, datei)
        if fremd and not fremd.get("eigene") and _datei is not None:
            try:
                _datei.unlink()         # „Trotzdem bearbeiten“: Sperre geht auf mich über (steht im Verlauf)
            except OSError:
                pass
        sperren(db, datei, w)
    summe = pruefsumme(p)
    letzte = versionen(p)[:1]
    if not letzte or letzte[0]["groesse"] != p.stat().st_size or pruefsumme(letzte[0]["pfad"]) != summe:
        version_sichern(p, kuerzel(db))
    with db.con:
        _meta_schreiben(db, datei, dict(pruefsumme=summe))
        ereignis(db, datei, E_SPERRE, f"trotz Bearbeitung durch {fremd['wer']}" if fremd and not fremd.get("eigene")
                 else "")
    return p, fremd if fremd and not fremd.get("eigene") else None


# ------------------------------------------------------------------ Aufräumen
def reste(db, w=None, alter_s=UPLOAD_ALT_S):
    """Zwischendateien abgebrochener Uploads (.rlteil), älter als alter_s: [Pfad]."""
    w = w if w is not None else wurzeln(db)
    out = []
    jetzt_ = time.time()
    for b in (DATEIEN, ANGEBOTE, PPEASE):
        o = w.get(b)
        if o is None or not Path(o).is_dir():
            continue
        for p in Path(o).rglob("*" + TEIL):
            try:
                if jetzt_ - p.stat().st_mtime > alter_s:
                    out.append(p)
            except OSError:
                continue
    return out


def reste_entfernen(db, w=None):
    n = 0
    for p in reste(db, w):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n


def versionen_groesse(db, w=None):
    """Speicher der gesicherten Fassungen in MB (Hinweis ab VERSIONEN_HINWEIS_MB)."""
    w = w if w is not None else wurzeln(db)
    s = 0
    for b in (DATEIEN, ANGEBOTE):
        o = w.get(b)
        if o is None or not Path(o).is_dir():
            continue
        for v in Path(o).rglob(VERSIONEN):
            for f in v.glob("*"):
                try:
                    s += f.stat().st_size
                except OSError:
                    pass
    return s / (1 << 20)


# ------------------------------------------------------------------ Merker dieses Arbeitsplatzes
def _liste(db, name):
    v = db.einstellung(name)
    return list(v) if isinstance(v, list) else []


def favoriten(db):
    return _liste(db, L_FAVORITEN)


def favorit_umschalten(db, datei):
    f = favoriten(db)
    if datei in f:
        f.remove(datei)
    else:
        f.insert(0, datei)
    _merken(db, L_FAVORITEN, f)
    return datei in f


def zuletzt(db):
    return _liste(db, L_ZULETZT)


def benutzt(db, datei):
    z = [d for d in zuletzt(db) if d != datei]
    _merken(db, L_ZULETZT, ([datei] + z)[:ZULETZT_MAX])


def gesehen(db):
    v = db.einstellung(L_GESEHEN)
    return dict(v) if isinstance(v, dict) else {}


def gesehen_setzen(db, dateien, stand=None):
    """Dateien als gesehen merken (Stand = Änderungszeit; ändert sich die Datei, ist sie wieder neu für mich)."""
    g = gesehen(db)
    for d, t in (dateien.items() if isinstance(dateien, dict) else ((d, stand) for d in dateien)):
        g[d] = t if t is not None else time.time()
    if len(g) > 20000:
        g = dict(sorted(g.items(), key=lambda x: x[1])[-15000:])
    _merken(db, L_GESEHEN, g)


def stand_zeit(e, m=None):
    """Stand einer Datei für „neu“: Änderungszeit, beim Hochladen mindestens die Hochladezeit (das Kopieren behält die
    Änderungszeit der Quelle, eine alte Zeichnung wäre sonst nie neu)."""
    t = e.zeit
    h = (m or {}).get("hochgeladen_am")
    if h:
        try:
            t = max(t, datetime.datetime.fromisoformat(str(h)).timestamp())
        except ValueError:
            pass
    return t


def ist_neu(g, e, erststart=None, m=None):
    """Neu für mich: nie gesehen (oder seitdem geändert). Dateien vor dem ersten Öffnen der Plattform zählen nicht.
    m: Metadaten der Datei (Hochladezeit)."""
    t = g.get(e.datei)
    stand = stand_zeit(e, m)
    if t is None:
        return erststart is None or stand > erststart
    return stand > float(t) + 1


def gespeicherte_suchen(db):
    v = db.einstellung(L_SUCHEN)
    return list(v) if isinstance(v, list) else []


def suche_speichern(db, name, filter_):
    n = str(name or "").strip()
    if not n:
        raise AustauschFehler("Bitte einen Namen für die Suche eingeben.")
    s = [x for x in gespeicherte_suchen(db) if x.get("name") != n]
    s.append(dict(name=n, filter=dict(filter_)))
    _merken(db, L_SUCHEN, s)


def suche_loeschen(db, name):
    _merken(db, L_SUCHEN, [x for x in gespeicherte_suchen(db) if x.get("name") != name])


# ------------------------------------------------------------------ Suche und Filter
@dataclasses.dataclass
class Filter:
    text: str = ""
    art: str = ""               # Dateiart (step, pdf …) oder ""
    mitarbeiter: str = ""       # Verantwortlich, hochgeladen oder geändert von
    kunde: str = ""             # Kundennummer
    status: str = ""
    seit_tage: int = 0          # nur geändert in den letzten n Tagen
    nur_neu: bool = False
    nur_meine: bool = False     # mir zugewiesen
    archiv: bool = False        # True: nur Archiv; False: ohne Archiv
    ordner: bool = True         # Ordner in der Liste zeigen

    def als_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def aus(cls, d):
        felder = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in felder})


def _passt_text(worte, e, m, inhalt, kommentare):
    if not worte:
        return True
    teile = [e.rel, ART_TEXT.get(e.art, "")]
    if m:
        teile += [m.get(k) or "" for k in FELDER] + [m.get("hochgeladen_von") or "", m.get("geaendert_von") or ""]
    teile.append(kommentare.get(e.datei, ""))
    teile.append(inhalt.get(e.datei, ""))
    t = suchtext(" ".join(teile))
    return all(w in t for w in worte)


def filtern(eintraege, metas, f, ich="", gesehen_=None, inhalt=None, kommentare=None, erststart=None, jetzt_=None,
            kunden_namen=None):
    """Einträge nach Filter: [Eintrag]. metas {Datei: Metadaten}; inhalt {Datei: Text} (Inhaltssuche);
    kommentare {Datei: Text}; kunden_namen {Kundennr: Name} (Suche nach Kundenname)."""
    worte = suchtext(f.text).split()
    inhalt, kommentare = inhalt or {}, kommentare or {}
    grenze = (jetzt_ or time.time()) - f.seit_tage * 86400 if f.seit_tage else None
    out = []
    for e in eintraege:
        m = metas.get(e.datei) or {}
        if e.archiv != bool(f.archiv):
            continue
        if e.ordner and not f.ordner:
            continue
        if f.art and e.art != f.art:
            continue
        if f.status and (m.get("status") or "") != f.status:
            continue
        if f.kunde and (m.get("kundennr") or "") != f.kunde:
            continue
        if f.mitarbeiter and f.mitarbeiter not in (m.get("bearbeiter"), m.get("hochgeladen_von"),
                                                   m.get("geaendert_von")):
            continue
        if f.nur_meine and (not ich or m.get("bearbeiter") != ich):
            continue
        if grenze and e.zeit < grenze:
            continue
        if f.nur_neu and (e.ordner or gesehen_ is None or not ist_neu(gesehen_, e, erststart, metas.get(e.datei))):
            continue
        if worte:
            km = dict(kommentare)
            if kunden_namen and m.get("kundennr"):
                km[e.datei] = km.get(e.datei, "") + " " + (kunden_namen.get(m["kundennr"]) or "")
            if not _passt_text(worte, e, m, inhalt, km):
                continue
        out.append(e)
    return out


SORTIERUNG = (("name", "Name"), ("zeit", "Datum"), ("mitarbeiter", "Mitarbeiter"), ("kunde", "Kunde"),
              ("art", "Dateityp"), ("groesse", "Größe"))


def sortieren(eintraege, metas, nach="name", absteigend=False):
    def schl(e):
        m = metas.get(e.datei) or {}
        w = {"name": e.name.lower(), "zeit": e.zeit, "groesse": e.groesse, "art": e.art,
             "mitarbeiter": (m.get("bearbeiter") or m.get("geaendert_von") or m.get("hochgeladen_von") or "~"),
             "kunde": m.get("kundennr") or "~"}.get(nach, e.name.lower())
        return (not e.ordner, w, e.name.lower())
    liste = sorted(eintraege, key=schl, reverse=absteigend)
    if absteigend:                      # Ordner bleiben oben
        liste = [e for e in liste if e.ordner] + [e for e in liste if not e.ordner]
    return liste


def kommentare_text(db):
    """{Datei: alle Kommentare als Text} für die Suche."""
    out = {}
    for d, t in db.con.execute("SELECT datei, text FROM austausch_ereignisse WHERE art=?", (E_KOMMENTAR,)):
        out[d] = out.get(d, "") + " " + (t or "")
    return out


def wer_arbeitet(db, w=None, metas=None):
    """Übersicht „wer arbeitet woran“: [dict(wer, datei, seit, art)] aus Sperren und Status In Bearbeitung."""
    w = w if w is not None else wurzeln(db)
    out = []
    so = system(w) / "sperren"
    if so.is_dir():
        for s in so.glob("*.json"):
            try:
                if time.time() - s.stat().st_mtime > SPERRE_MIN * 60:
                    continue
                d = json.loads(s.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out.append(dict(wer=d.get("wer"), datei=d.get("datei"), seit=d.get("seit"), art="öffnet"))
    for d, m in (metas if metas is not None else meta(db)).items():
        if m.get("status") == BEARBEITUNG and m.get("bearbeiter") and not m.get("weg"):
            if not any(x["datei"] == d for x in out):
                out.append(dict(wer=m["bearbeiter"], datei=d, seit=m.get("geaendert_am"), art="verantwortlich"))
    return sorted(out, key=lambda x: (x["wer"] or "", x["datei"] or ""))


# ------------------------------------------------------------------ Inhaltssuche (soweit technisch möglich)
INHALT_MAX = 20000                  # Zeichen je Datei im Suchindex
INHALT_BIS_MB = {"text": 2, "csv": 5, "mail": 25, "pdf": 30, "step": 60, "word": 20, "laser": 5}
INHALT_DATEI = "austausch_inhalt.json"


def inhalt_lesen(p, art_=None):
    """Durchsuchbarer Text einer Datei ('' = keiner): Text/CSV/LST, Mail (Absender, Betreff, Text, Anhänge),
    PDF-Text, Word, STEP-Bauteilnamen. Nur lesen, nichts ausführen."""
    p = Path(p)
    art_ = art_ or art(p.name)
    try:
        if p.stat().st_size > INHALT_BIS_MB.get(art_, 0) * (1 << 20):
            return ""
        if art_ in ("text", "csv", "laser"):
            b = p.read_bytes()[:INHALT_MAX * 2]
            for kod in ("utf-8", "cp1252"):
                try:
                    return b.decode(kod)[:INHALT_MAX]
                except UnicodeDecodeError:
                    continue
            return ""
        if art_ == "mail":
            from . import mail
            m = mail.lesen(p)
            if m is None:
                return ""
            return " ".join([m.absender_name, m.absender, m.betreff, m.text[:INHALT_MAX],
                             " ".join(n for n, _ in m.anhaenge)])[:INHALT_MAX]
        if art_ == "pdf":
            from .formular import pdf_text
            return pdf_text(p)[:INHALT_MAX]
        if art_ == "word" and p.suffix.lower() in (".docx", ".docm"):
            from .anhang_vorschau import docx_text
            return docx_text(p)[:INHALT_MAX]
        if art_ == "step" and p.suffix.lower() in (".step", ".stp"):
            from . import step_vorschau
            roh = p.read_bytes().decode("latin-1")
            namen = dict.fromkeys(step_vorschau._dekodieren(n.replace("''", "'"))
                                  for n in re.findall(r"PRODUCT\s*\(\s*'((?:[^']|'')*)'", roh))
            return " ".join(namen)[:INHALT_MAX]
    except Exception:           # noqa: BLE001 – kaputte Datei: ohne Inhalt
        return ""
    return ""


class Inhalt:
    """Suchtext je Datei, im Hintergrund gelesen und lokal zwischengespeichert (Schlüssel Datei, Größe, Zeit)."""

    def __init__(self, ordner=None):
        self.datei = Path(ordner) / INHALT_DATEI if ordner else None
        self.texte = {}             # Datei -> [groesse, zeit, Text]
        if self.datei and self.datei.exists():
            try:
                self.texte = json.loads(self.datei.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.texte = {}
        self.geaendert = False

    def fehlend(self, eintraege):
        return [e for e in eintraege if not e.ordner and e.art in INHALT_BIS_MB
                and (self.texte.get(e.datei) or [None, None])[:2] != [e.groesse, round(e.zeit, 1)]]

    def lesen(self, eintraege, w, abbrechen=None, hoechstens=400):
        """Fehlende Texte lesen (höchstens so viele je Lauf). Ergebnis: Anzahl."""
        n = 0
        for e in self.fehlend(eintraege)[:hoechstens]:
            if abbrechen and abbrechen():
                break
            p = Path(w[e.bereich]) / e.rel if w.get(e.bereich) else None
            if p is None:
                continue
            self.texte[e.datei] = [e.groesse, round(e.zeit, 1), inhalt_lesen(p, e.art)]
            n += 1
        self.geaendert = self.geaendert or n > 0
        return n

    def text(self):
        return {d: v[2] for d, v in self.texte.items() if v and v[2]}

    def speichern(self):
        if not self.datei or not self.geaendert:
            return
        try:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.datei.with_suffix(".neu")
            tmp.write_text(json.dumps(self.texte, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.datei)
            self.geaendert = False
        except OSError:
            pass


# ------------------------------------------------------------------ Benachrichtigungen (Abschnitt 7)
M_DATEI, M_ANFRAGE, M_AUFGABE, M_ZUGEWIESEN, M_GEAENDERT, M_NACHRICHT, M_STATUS, M_FERTIG = (
    "neue_datei", "neue_anfrage", "neue_aufgabe", "zugewiesen", "geaendert", "nachricht", "status", "fertig")
MELDUNGEN = ((M_DATEI, "Neue Datei"), (M_ANFRAGE, "Neue Kundenanfrage"), (M_AUFGABE, "Neue Aufgabe für mich"),
             (M_ZUGEWIESEN, "Mir zugewiesen"), (M_GEAENDERT, "Geänderte Datei (meine)"),
             (M_NACHRICHT, "Neuer Kommentar an mich"), (M_STATUS, "Geänderter Status (meine)"),
             (M_FERTIG, "Fertiggestellt"))
L_MELDUNGEN, L_GEMELDET = "austausch_meldungen", "austausch_gemeldet"
MELDUNG_VORGABE = {M_DATEI: True, M_ANFRAGE: True, M_AUFGABE: True, M_ZUGEWIESEN: True, M_GEAENDERT: True,
                   M_NACHRICHT: True, M_STATUS: True, M_FERTIG: False}
RUHE_MIN = 30                       # dieselbe Datei als „geändert“ höchstens alle 30 min melden


def meldungen_an(db):
    v = db.einstellung(L_MELDUNGEN)
    return dict(MELDUNG_VORGABE, **(v if isinstance(v, dict) else {}))


def meldungen_setzen(db, werte):
    _merken(db, L_MELDUNGEN, {k: bool(v) for k, v in werte.items() if k in MELDUNG_VORGABE})


def benachrichtigungen(db, eintraege=None, jetzt_=None, merken=True):
    """Was ist seit der letzten Prüfung für mich passiert? [dict(art, datei, text)], je Datei und Art höchstens
    eine Meldung; eigene Änderungen nie. Beim ersten Aufruf wird nur der Stand gemerkt (keine Flut alter Meldungen).
    Gemerkt wird die letzte gelesene Zeilennummer dieses Platzes, nicht die Zeit: Ereignisse der Kollegen kommen erst
    mit dem Abgleich an (mit ihrer ursprünglichen, oft älteren Zeit) und dürfen trotzdem nicht verloren gehen."""
    ich = kuerzel(db)
    an = meldungen_an(db)
    stand = db.einstellung(L_GEMELDET)
    stand = dict(stand) if isinstance(stand, dict) else {}
    jetzt_ = jetzt_ or jetzt()
    erstmal = not stand.get("seit") or "bis" not in stand
    seit = stand.get("seit") or jetzt_
    bis = int(stand.get("bis") or 0)
    hoechste = db.con.execute("SELECT MAX(id) FROM austausch_ereignisse").fetchone()[0] or 0
    ruhe = dict(stand.get("ruhe") or {})
    out = []

    def dazu(a, datei, text):
        if not an.get(a) or any(x["datei"] == datei and x["art"] == a for x in out):
            return
        out.append(dict(art=a, datei=datei, text=text))
    if not erstmal:
        metas = meta(db)
        k = ("datei", "zeit", "wer", "art", "an", "feld", "alt", "neu", "text")
        neue_e = [dict(zip(k, r)) for r in db.con.execute(
            "SELECT datei, zeit, wer, art, an, feld, alt, neu, text FROM austausch_ereignisse WHERE id>? AND id<=? "
            "ORDER BY id LIMIT 5000", (bis, hoechste))]
        for e in neue_e:
            if e["wer"] == ich:
                continue
            m = metas.get(e["datei"]) or {}
            name = e["datei"].partition(":")[2].rpartition("/")[2] or e["datei"]
            meine = m.get("bearbeiter") == ich or m.get("hochgeladen_von") == ich
            if e["art"] == E_ZUGEWIESEN and e["neu"] == ich:
                dazu(M_ZUGEWIESEN, e["datei"], f"{e['wer']} hat dir {name} zugewiesen")
            elif e["art"] == E_FELD and e["feld"] == "aufgabe" and e["neu"] and m.get("bearbeiter") == ich:
                dazu(M_AUFGABE, e["datei"], f"Neue Aufgabe zu {name}: {e['neu']}")
            elif e["art"] == E_KOMMENTAR and (e["an"] == ich or (meine and not e["an"])):
                dazu(M_NACHRICHT, e["datei"], f"{e['wer']} zu {name}: {e['text'][:80]}")
            elif e["art"] == E_FELD and e["feld"] == "status" and e["neu"] == FERTIG:
                dazu(M_FERTIG, e["datei"], f"{name} ist fertiggestellt ({e['wer']})")
            elif e["art"] == E_FELD and e["feld"] == "status" and meine:
                dazu(M_STATUS, e["datei"], f"{name}: Status {e['neu'] or '–'} ({e['wer']})")
            elif e["art"] == E_VERSION and meine:
                if ruhe.get(e["datei"], "") < e["zeit"][:16]:
                    dazu(M_GEAENDERT, e["datei"], f"{e['wer']} hat {name} geändert")
                    t = datetime.datetime.fromisoformat(e["zeit"]) + datetime.timedelta(minutes=RUHE_MIN)
                    ruhe[e["datei"]] = t.isoformat(sep=" ", timespec="minutes")
            elif e["art"] == E_HOCH:
                b, _ = zerlegen(e["datei"])
                if b in (DATEIEN, PERSOENLICH, ANGEBOTE, PPEASE):
                    dazu(M_DATEI, e["datei"], f"Neue Datei von {e['wer']}: {name}")
        neue = [x for x in out if x["art"] == M_DATEI]
        if len(neue) > 3:                       # viele neue Dateien: eine Sammelmeldung
            out = [x for x in out if x["art"] != M_DATEI]
            out.append(dict(art=M_DATEI, datei=neue[0]["datei"], text=f"{len(neue)} neue Dateien im Austauschordner"))
        try:
            from . import anfragen_akten
            if an.get(M_ANFRAGE) and anfragen_akten.aktiv(db):
                neu_a = [a for a in anfragen_akten.ablage(db).alle()
                         if a.status == anfragen_akten.NEU and str(a.kopf.get("eingang") or "") > seit[:19]]
                if neu_a:
                    out.append(dict(art=M_ANFRAGE, datei="", text=(f"Neue Kundenanfrage: {neu_a[0].betreff}"
                                                                   if len(neu_a) == 1 else
                                                                   f"{len(neu_a)} neue Kundenanfragen")))
        except Exception as fehler:       # noqa: BLE001 – Anfragen sind Zugabe
            from . import protokoll
            protokoll.warnung(f"Austausch: {fehler!r}")
    if merken:
        heute = jetzt_[:16]
        _merken(db, L_GEMELDET, dict(seit=jetzt_, bis=hoechste,
                                               ruhe={d: t for d, t in ruhe.items() if t > heute}))
    return out


# ------------------------------------------------------------------ Übersicht (Abschnitt 13)
def uebersicht(db, eintraege, metas=None, gesehen_=None, jetzt_=None, erststart=None):
    """Zahlen und Listen für das Dashboard des Austauschordners."""
    ich = kuerzel(db)
    metas = metas if metas is not None else meta(db)
    gesehen_ = gesehen_ if gesehen_ is not None else gesehen(db)
    heute = (jetzt_ or jetzt())[:10]
    dateien = [e for e in eintraege if not e.ordner and not e.archiv]
    da = {e.datei for e in dateien}
    meine = [d for d, m in metas.items() if m.get("bearbeiter") == ich and d in da
             and m.get("status") not in (FERTIG, ARCHIVIERT)]
    faellig = [d for d in meine if (metas[d].get("faellig") or "9999") <= heute]
    rueck = [d for d, m in metas.items() if m.get("status") == RUECKFRAGE and d in da]
    bearb = [d for d, m in metas.items() if m.get("status") == BEARBEITUNG and d in da]
    fertig = [d for d, m in metas.items() if m.get("status") == FERTIG and d in da
              and (m.get("geaendert_am") or "") >= (datetime.date.fromisoformat(heute)
                                                    - datetime.timedelta(days=7)).isoformat()]
    neu = [e.datei for e in dateien if ist_neu(gesehen_, e, erststart, metas.get(e.datei))]
    vorschlag = [d for d, m in metas.items() if d in da and vorschlaege(m)]
    zuletzt_ = [e.datei for e in sorted(dateien, key=lambda e: -e.zeit)[:12]]
    return dict(neu=neu, meine=meine, faellig=faellig, rueckfrage=rueck, bearbeitung=bearb, fertig=fertig,
                vorschlag=vorschlag, zuletzt=zuletzt_, aktivitaet=verlauf(db, grenze=15),
                wer=wer_arbeitet(db, metas=metas))
