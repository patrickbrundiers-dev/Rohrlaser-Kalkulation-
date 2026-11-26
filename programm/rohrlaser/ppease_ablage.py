"""Dokumentenablage nach PPEASE-Angebotsnummer (Patrick 19.11.2026, Entwicklungsauftrag „Automatische
Dokumentenablage nach Angebotsnummer“).

Neben der eigenen Ablage des Programms (angebotsordner.py, Angebotsakte akte_ablage.py) gibt es einen frei wählbaren
Hauptordner für die Angebote aus PPEASE (lokal, Netzlaufwerk, NAS, \\\\SERVER\\Freigabe). Je PPEASE-Angebotsnummer
entsteht dort ein Ordner, in den der Benutzer ausgewählte Dokumente der Kalkulation kopiert:

    <Hauptordner>/[2026/][Vorsatz]2026-44327 [Kunde – Bezeichnung]/   (Vorgabe: Hauptordner/2026-44327)
        01_Angebot/ 02_Kalkulation/ 03_Schnittschema/ 04_Zeichnungen/ 05_3D_Modelle/ 06_Materiallisten/
        07_Kundenunterlagen/ 08_Sonstige_Dokumente/      (nur die benötigten; Namen in den Einstellungen änderbar)
        <Kategorie>/_Versionen/   ersetzte Fassungen: Name_V1_2026-11-19_1530.pdf (nie gelöscht)
        _Protokoll/ablage.json    Verzeichnis der abgelegten Dateien (Version, SHA-256, Zeit, Mitarbeiter, Quelle)
        _Protokoll/protokoll_<Kürzel>.jsonl   jede Speicheraktion (ein Schreiber je Datei, wie die Anfragen-Akten)
        _Protokoll/speichern.sperre           solange ein Platz speichert (älter als SPERRE_MIN: verwaist)

Sicher: kopiert wird in eine Zwischendatei (*.rl-teil), geprüft (Größe, SHA-256) und erst dann umbenannt; ein Absturz
hinterlässt höchstens eine Zwischendatei, die der nächste Aufruf entfernt und meldet. Nie überschreiben ohne
Bestätigung: gleiche Dateien (gleicher Inhalt) werden übersprungen, geänderte nur mit Aktion ERSETZEN (alte Fassung
nach _Versionen) oder als NEUE_VERSION daneben (Name_V2.pdf). Keine Datenbankeinträge außer der Einstellung und der
Nummer am Angebot (Zusatzdaten 'ppease', keine neue Spalte).

Verschieben statt kopieren (Patrick 26.11.2026 „ich möchte keine doppelten Daten“, vorerst nur von Hand): mit
verschieben=True werden die Kundendateien (Mail mit allen Anhängen, STEP, DXF, PDF …) und die Dokumente der
Angebotsakte in den PPEASE-Angebotsordner verschoben. Jede Datei wird erst sicher kopiert und geprüft (Größe,
SHA-256), erst danach wird das Original entfernt. Programminterne Dateien (JSON der Kalkulation und Akte, Zwischen-
speicher, Messungen, Sperren, Protokolle, Zwischendateien) werden nie verschoben (intern()). ablage.json merkt sich
unter „verschoben“ den alten Pfad jeder verschobenen Datei; wo() findet sie darüber wieder (Angebotsakte öffnen,
STEP der Position, Dateien der Anfrage). Ein gesperrtes Original bleibt liegen und wird beim nächsten Mal entfernt
(Inhalt gleich), ein abgebrochener Vorgang lässt höchstens eine Kopie zu viel zurück, nie eine fehlende Datei.

Für später vorbereitet: Quelle (PPEASE-Schnittstelle: Kunde und Bezeichnung zur Nummer), ablegen() ohne Fenster
(automatische Ablage bei Freigabe, Outlook-Zuordnung), suchen() (zentrale Suche). Ohne Qt."""
import datetime
import hashlib
import json
import os
import re
import shutil
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .angebotsordner import sauber

# ------------------------------------------------------------------ Einstellungen
E_ORDNER = "ppease_ordner"              # Hauptordner (für alle Plätze, über den gemeinsamen Ordner abgeglichen)
E_JAHR = "ppease_jahresordner"          # ja: Jahresordner 2026/ anlegen
E_NAME = "ppease_ordnername"            # nummer | kunde | kunde_bezeichnung
E_PRAEFIX = "ppease_praefix"            # Vorsatz des Ordnernamens (Vorgabe leer: Ordner = Nummer)
E_MUSTER = "ppease_nummer_muster"       # regulärer Ausdruck für die Plausibilität (leer = Vorgabe)
E_KATEGORIEN = "ppease_kategorien"      # je Zeile ein Ordnername; Zeilen 1–8 = feste Arten, weitere = eigene
E_QUELLE = "ppease_quelle"              # spätere Schnittstelle (leer/'keine' = manuell)
ZUSATZ = "ppease"                       # Zusatzdaten des Angebots: {nummer, kunde, bezeichnung, ordner, zuletzt}

PRAEFIX = ""                            # Patrick 19.11.: Ordner heißt wie die Nummer (2026-44327)
MUSTER = r"^\d{4}-\d{3,7}$"              # PPEASE-Angebotsnummer: Jahr-Nummer wie 2026-44327 (Abweichung nur Hinweis)
NAMEN = ("nummer", "kunde", "kunde_bezeichnung")
NAMEN_TEXT = {"nur Nummer": "nummer", "Nummer und Kunde": "kunde", "Nummer, Kunde und Bezeichnung": "kunde_bezeichnung"}

# feste Arten (Reihenfolge = Zeilen 1–8 der Einstellung)
ANGEBOT, KALKULATION, SCHNITT, ZEICHNUNG, MODELL, MATERIAL, KUNDE, SONSTIGE = (
    "angebot", "kalkulation", "schnitt", "zeichnung", "modell", "material", "kunde", "sonstige")
KATEGORIEN = ((ANGEBOT, "01_Angebot"), (KALKULATION, "02_Kalkulation"), (SCHNITT, "03_Schnittschema"),
              (ZEICHNUNG, "04_Zeichnungen"), (MODELL, "05_3D_Modelle"), (MATERIAL, "06_Materiallisten"),
              (KUNDE, "07_Kundenunterlagen"), (SONSTIGE, "08_Sonstige_Dokumente"))
KATEGORIEN_TEXT = "\n".join(n for _, n in KATEGORIEN)

PROTOKOLL = "_Protokoll"
VERSIONEN = "_Versionen"
VERZEICHNIS = "ablage.json"
SPERRE = "speichern.sperre"
TEIL = ".rl-teil"
SPERRE_MIN = 10                         # ältere Sperre gilt als verwaist (Absturz) und wird übernommen
PRUEF_SEK = 8                           # so lange darf die Prüfung des Hauptordners dauern (Netzlaufwerk weg)

# Status je Dokument im Zielordner
NEU, GLEICH, GEAENDERT, SCHON = "neu", "gleich", "geaendert", "schon"
STATUS_TEXT = {NEU: "Neu", GLEICH: "Schon abgelegt (gleich)", GEAENDERT: "Geändert (anderer Inhalt)",
               SCHON: "Schon abgelegt (anderer Name)"}
# Aktion bei geänderten Dateien
ERSETZEN, NEUE_VERSION, UEBERSPRINGEN = "ersetzen", "neue_version", "ueberspringen"
AKTION_TEXT = {ERSETZEN: "Ersetzen (alte Fassung sichern)", NEUE_VERSION: "Als neue Version daneben",
               UEBERSPRINGEN: "Überspringen"}

# Quelle eines Dokuments
Q_ANGEBOT, Q_AKTE, Q_ANFRAGE, Q_EXTERN = "Angebotsordner", "Angebotsakte", "Anfrage", "Hinzugefügt"
OHNE = {".tmp", ".neu", TEIL, ".lnk", ".ini", ".db", ".lock"}
DATEITYP = {".pdf": "PDF", ".step": "STEP", ".stp": "STEP", ".igs": "IGES", ".iges": "IGES", ".stl": "STL",
            ".x_t": "Parasolid", ".sat": "ACIS", ".3mf": "3MF", ".obj": "OBJ", ".dxf": "DXF", ".dwg": "DWG",
            ".xlsx": "Excel", ".xlsm": "Excel", ".xls": "Excel", ".ods": "Tabelle", ".csv": "CSV",
            ".docx": "Word", ".doc": "Word", ".txt": "Text", ".json": "Daten (JSON)", ".xml": "XML",
            ".png": "Bild", ".jpg": "Bild", ".jpeg": "Bild", ".bmp": "Bild", ".gif": "Bild", ".tif": "Bild",
            ".tiff": "Bild", ".webp": "Bild", ".msg": "E-Mail", ".eml": "E-Mail", ".zip": "ZIP-Archiv",
            ".mac": "Laserprogramm", ".nc": "Laserprogramm"}
MODELLE = {".step", ".stp", ".igs", ".iges", ".stl", ".x_t", ".sat", ".3mf", ".obj"}
ZEICHNUNGEN = {".dxf", ".dwg"}
TABELLEN = {".xlsx", ".xlsm", ".xls", ".ods", ".csv"}
BILDER = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}


@dataclass
class Vorgaben:
    ordner: str = ""
    jahresordner: bool = False
    ordnername: str = "nummer"
    praefix: str = PRAEFIX
    muster: str = MUSTER
    kategorien: list = field(default_factory=lambda: [n for _, n in KATEGORIEN])

    def kategorie_ordner(self, art):
        """Ordnername der Art (feste Art oder Name einer eigenen Kategorie)."""
        for i, (a, n) in enumerate(KATEGORIEN):
            if a == art:
                return self.kategorien[i] if i < len(self.kategorien) and self.kategorien[i] else n
        return sauber(art) or KATEGORIEN[-1][1]


def kategorien_lesen(text):
    """Zeilen der Einstellung: Zeilen 1–8 benennen die festen Arten (leer = Vorgabe), weitere sind eigene
    Kategorien. Ergebnis: [Ordnername] (mindestens 8)."""
    zeilen = [sauber(z) for z in str(text or "").splitlines()]
    while zeilen and not zeilen[-1]:
        zeilen.pop()
    out = [zeilen[i] if i < len(zeilen) and zeilen[i] else n for i, (_, n) in enumerate(KATEGORIEN)]
    return out + [z for z in zeilen[len(KATEGORIEN):] if z and z not in out]


def vorgaben(db):
    def e(n, v=""):
        try:
            w = db.einstellung(n)
        except Exception:       # noqa: BLE001 – alte Datei ohne Einstellung
            w = None
        return v if w in (None, "") else w
    name = str(e(E_NAME, "nummer"))
    name = NAMEN_TEXT.get(name, name)
    return Vorgaben(ordner=str(e(E_ORDNER, "")).strip(), jahresordner=str(e(E_JAHR, "nein")) == "ja",
                    ordnername=name if name in NAMEN else "nummer", praefix=sauber(e(E_PRAEFIX, PRAEFIX)) or "",
                    muster=str(e(E_MUSTER, MUSTER)) or MUSTER, kategorien=kategorien_lesen(e(E_KATEGORIEN, "")))


def alle_kategorien(v):
    """[(Art, Ordnername)]: feste Arten, dann die eigenen Kategorien (Art = Ordnername)."""
    out = [(a, v.kategorie_ordner(a)) for a, _ in KATEGORIEN]
    return out + [(n, n) for n in v.kategorien[len(KATEGORIEN):]]


# ------------------------------------------------------------------ Angebotsnummer
def nummer_pruefen(text, muster=MUSTER):
    """(Nummer, Fehler, Hinweis): Fehler = so nicht verwendbar (leer, Zeichen für Ordnernamen verboten, zu lang);
    Hinweis = passt nicht zum Muster der Einstellungen (verwendbar, aber bitte prüfen)."""
    nr = re.sub(r"\s+", "", str(text or ""))
    if not nr:
        return "", "Bitte die Angebotsnummer aus PPEASE eingeben.", None
    if sauber(nr) != nr or nr in (".", ".."):
        return nr, "Die Nummer enthält Zeichen, die in Ordnernamen nicht erlaubt sind (\\ / : * ? \" < > |).", None
    if len(nr) > 30:
        return nr, "Die Nummer ist länger als 30 Zeichen.", None
    try:
        passt = re.fullmatch(muster or MUSTER, nr) is not None
    except re.error:
        passt = re.fullmatch(MUSTER, nr) is not None
    return nr, None, None if passt else (f"„{nr}“ sieht nicht wie eine PPEASE-Angebotsnummer aus "
                                         f"(erwartet: {muster_text(muster)}). Bitte prüfen.")


def muster_text(muster):
    if str(muster or "") == MUSTER:
        return "Jahr-Nummer wie 2026-44327"
    m = re.fullmatch(r"\^\\d\{(\d+),(\d+)\}\$", str(muster or ""))
    return f"{m.group(1)} bis {m.group(2)} Ziffern" if m else f"Muster {muster}"


# ------------------------------------------------------------------ Hauptordner prüfen
@dataclass
class Pruefung:
    ok: bool
    text: str
    art: str = "ok"         # ok | leer | fehlt | kein_ordner | nur_lesen | zeit | fehler


def _mit_zeitlimit(arbeit, sek):
    """arbeit() in einem Hilfsfaden; hängt das Netzlaufwerk länger als sek: TimeoutError."""
    ergebnis = {}

    def lauf():
        try:
            ergebnis["wert"] = arbeit()
        except BaseException as e:  # noqa: BLE001
            ergebnis["fehler"] = e
    t = threading.Thread(target=lauf, daemon=True)
    t.start()
    t.join(sek)
    if t.is_alive():
        raise TimeoutError
    if "fehler" in ergebnis:
        raise ergebnis["fehler"]
    return ergebnis.get("wert")


def pfad_pruefen(pfad, sek=PRUEF_SEK):
    """Hauptordner erreichbar und beschreibbar? Schreibt und löscht eine kleine Prüfdatei."""
    if not str(pfad or "").strip():
        return Pruefung(False, "Noch kein Speicherpfad festgelegt.", "leer")
    p = Path(str(pfad).strip())

    def arbeit():
        if not p.exists():
            return Pruefung(False, f"Der Speicherort {p} ist nicht erreichbar (Netzlaufwerk getrennt, Server aus "
                                   "oder Ordner gelöscht?).", "fehlt")
        if not p.is_dir():
            return Pruefung(False, f"{p} ist kein Ordner.", "kein_ordner")
        test = p / f".rl_schreibtest_{sauber(socket.gethostname())}_{os.getpid()}"
        try:
            test.write_bytes(b"rohrlaser")
            if test.read_bytes() != b"rohrlaser":
                raise OSError("Prüfdatei nicht lesbar")
        except OSError as e:
            return Pruefung(False, f"Keine Schreibrechte im Speicherort {p}: {e}", "nur_lesen")
        finally:
            try:
                test.unlink()
            except OSError:
                pass
        return Pruefung(True, f"Speicherort erreichbar, Schreibrechte vorhanden: {p}")
    try:
        return _mit_zeitlimit(arbeit, sek)
    except TimeoutError:
        return Pruefung(False, f"Der Speicherort {p} antwortet nicht (nach {sek} s abgebrochen). Netzwerk prüfen.",
                        "zeit")
    except OSError as e:
        return Pruefung(False, f"Der Speicherort {p} ist nicht erreichbar: {e}", "fehler")


# ------------------------------------------------------------------ Angebotsordner
def ordnername(v, nummer, kunde="", bezeichnung=""):
    """'2026-44327' (mit Vorsatz 'Angebot_2026-44327'), mit Kunde '2026-44327 Muster GmbH', mit Bezeichnung
    '… – Gestell'."""
    teile = [f"{v.praefix}{sauber(nummer)}"]
    if v.ordnername in ("kunde", "kunde_bezeichnung") and sauber(kunde):
        teile.append(sauber(kunde)[:50].strip())
        if v.ordnername == "kunde_bezeichnung" and sauber(bezeichnung):
            teile.append("– " + sauber(bezeichnung)[:50].strip())
    return sauber(" ".join(teile))


def _passt(name, nummer, praefix):
    """Ordnername gehört zur Nummer: '2026-44327', '2026-44327 …', '2026-44327_…', mit Vorsatz auch
    'Angebot_2026-44327 …' (und ohne Vorsatz, falls von Hand angelegt). '2026-443270' gehört nicht zu 2026-44327."""
    n = sauber(nummer)
    for kopf in {f"{praefix}{n}", n}:
        if name == kopf or (name.startswith(kopf) and name[len(kopf)] in " _-"):
            return True
    return False


def _jahre(wurzel):
    try:
        return sorted((o for o in Path(wurzel).iterdir() if o.is_dir() and re.fullmatch(r"\d{4}", o.name)),
                      key=lambda o: o.name, reverse=True)
    except OSError:
        return []


def finden(wurzel, nummer, praefix=PRAEFIX):
    """Vorhandener Ordner der Nummer: in allen Jahresordnern (neuestes Jahr zuerst) und direkt im Hauptordner.
    Ergebnis: Pfad oder None."""
    for ort in _jahre(wurzel) + [Path(wurzel)]:
        try:
            treffer = sorted(o for o in ort.iterdir() if o.is_dir() and _passt(o.name, nummer, praefix))
        except OSError:
            continue
        if treffer:
            return treffer[0]
    return None


def neuer_ordner(v, nummer, kunde="", bezeichnung="", jahr=None):
    """Pfad, den ein neuer Ordner bekäme (noch nicht angelegt)."""
    o = Path(v.ordner)
    if v.jahresordner:
        o = o / str(jahr or datetime.date.today().year)
    return o / ordnername(v, nummer, kunde, bezeichnung)


def ordner_status(v, nummer, kunde="", bezeichnung="", jahr=None):
    """(Pfad, vorhanden): vorhandener Ordner der Nummer oder der, der angelegt würde."""
    o = finden(v.ordner, nummer, v.praefix) if v.ordner else None
    return (o, True) if o else (neuer_ordner(v, nummer, kunde, bezeichnung, jahr), False)


# ------------------------------------------------------------------ Dokumente
# Programminterne Dateien und Ordner: werden nie verschoben (und standardmäßig nicht abgelegt), 26.11.2026
INTERN_ENDUNGEN = {".json", ".jsonl", ".db", ".sqlite", ".tmp", ".neu", ".lock", ".sperre", ".marke", ".rlteil", TEIL,
                   ".ini", ".lnk", ".bak", ".pyc", ".log"}
INTERN_ORDNER = {"kalkulationsdaten", "_messung", "_protokoll", "_plattform", "_outlook", "_schluessel", "_journal",
                 "__pycache__", "cache", "step-cache", "zwischenspeicher"}


def intern(pfad):
    """Vom Programm erzeugte Verwaltungs-, Cache- und Hilfsdatei? (JSON der Akte/Kalkulation, Zwischenspeicher,
    Sperren, Protokolle, Zwischendateien, Office-Sperrdateien)"""
    p = Path(pfad)
    n = p.name.lower()
    if n.startswith(("~$", ".")) or any(n.endswith(e) for e in INTERN_ENDUNGEN):
        return True
    return any(t.lower() in INTERN_ORDNER or t.lower().startswith("_arbeit_") for t in p.parts[:-1])


@dataclass
class Dokument:
    pfad: Path
    quelle: str = Q_ANGEBOT
    kategorie: str = SONSTIGE           # Art (feste) oder Name einer eigenen Kategorie
    gewaehlt: bool = True
    name: str = ""                      # Name im Zielordner (Vorgabe: Dateiname)
    intern: bool = None                 # Programmdatei: nie verschieben, Vorgabe nicht gewählt (26.11.2026)

    def __post_init__(self):
        self.pfad = Path(self.pfad)
        self.name = self.name or self.pfad.name
        if self.intern is None:
            self.intern = intern(self.pfad)
        if self.intern:
            self.gewaehlt = False

    @property
    def typ(self):
        return dateityp(self.pfad)

    @property
    def groesse(self):
        try:
            return self.pfad.stat().st_size
        except OSError:
            return 0


def dateityp(pfad):
    s = Path(pfad).suffix.lower()
    return DATEITYP.get(s, (s[1:].upper() + "-Datei") if s else "Datei")


def groesse_text(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB".replace(".", ",")
    return f"{n / 1024 / 1024:.1f} MB".replace(".", ",")


def kategorie(pfad, quelle=Q_ANGEBOT):
    """Zielordner-Vorschlag nach Name, Endung und Herkunft."""
    p = Path(pfad)
    s, n = p.suffix.lower(), p.name.lower()
    teile = {t.lower() for t in p.parts}
    if s in MODELLE:
        return MODELL
    if s in ZEICHNUNGEN:
        return ZEICHNUNG
    if s in (".msg", ".eml"):
        return KUNDE
    if quelle == Q_ANFRAGE:
        return KUNDE
    if "schnittschemata" in teile or "schnitt" in n or "stangenplan" in n or "verschacht" in n:
        return SCHNITT
    if s in TABELLEN or "materialanfrage" in n or "stückliste" in n or "stueckliste" in n or "materialliste" in n:
        return MATERIAL
    if s == ".json" or "kalkulationsdaten" in teile:
        return KALKULATION
    if s in BILDER:
        return ZEICHNUNG if "technische_daten" in teile else SONSTIGE
    if s == ".pdf":
        if "_intern" in n or "kalkulation" in n:
            return KALKULATION
        if "zeichnung" in n or "abwicklung" in n or "massbild" in n or "maßbild" in n:
            return ZEICHNUNG
        if "angebot" in n or "_kunde" in n or "_gesamt" in n or "auftragsbest" in n:
            return ANGEBOT
    return SONSTIGE


def _ueberspringen(p, wurzel):
    rel = {t.lower() for t in p.relative_to(wurzel).parts[:-1]}
    return (p.name.startswith(("~$", ".")) or p.suffix.lower() in OHNE or p.name == "akte.json"
            or "versionen" in rel or VERSIONEN.lower() in rel or PROTOKOLL.lower() in rel)


def dokumente_sammeln(angebotsordner=None, anfrage_dateien=(), hoechstens=2000):
    """Alle Dateien der Kalkulation: Angebotsordner (mit Angebotsakte und STEP-Unterordner, ohne ältere Versionen
    und Hilfsdateien), dazu die Dateien der Kundenanfrage. Neueste zuerst je Quelle; gleiche Pfade nur einmal."""
    out, gesehen = [], set()
    if angebotsordner and Path(angebotsordner).is_dir():
        w = Path(angebotsordner)
        try:
            dateien = [p for p in w.rglob("*") if p.is_file() and not _ueberspringen(p, w)]
        except OSError:
            dateien = []
        dateien.sort(key=lambda p: (intern(p), 0 if "Angebotsakte" in p.parts else 1, str(p.relative_to(w)).lower()))
        for p in dateien[:hoechstens]:
            q = Q_AKTE if "Angebotsakte" in p.relative_to(w).parts else Q_ANGEBOT
            out.append(Dokument(p, q, kategorie(p, q)))
            gesehen.add(str(p.resolve()).lower())
    for p in anfrage_dateien or ():
        p = Path(p)
        if p.is_file() and str(p.resolve()).lower() not in gesehen:
            out.append(Dokument(p, Q_ANFRAGE, kategorie(p, Q_ANFRAGE)))
            gesehen.add(str(p.resolve()).lower())
    out.sort(key=lambda d: d.intern)            # Programmdateien (bleiben liegen) ganz unten, sonst Reihenfolge wie oben
    return out


def extern(pfade, vorhanden=()):
    """Weitere Dateien (Dateidialog, Ziehen): Ordner werden mit ihren Dateien aufgenommen; schon vorhandene Pfade
    nicht doppelt."""
    gesehen = {str(Path(d.pfad).resolve()).lower() for d in vorhanden}
    out = []
    for p in pfade:
        p = Path(p)
        liste = sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
        for x in liste:
            k = str(x.resolve()).lower()
            if x.is_file() and k not in gesehen and not x.name.startswith("~$"):
                gesehen.add(k)
                out.append(Dokument(x, Q_EXTERN, kategorie(x, Q_EXTERN)))
    return out


# ------------------------------------------------------------------ Verzeichnis, Protokoll, Sperre
_SHA = {}       # (Pfad, Größe, Änderungszeit) -> SHA-256 (das Fenster vergleicht nach jeder Änderung neu)


def pruefsumme(pfad, merken=True):
    st = os.stat(pfad)
    k = (str(pfad), st.st_size, st.st_mtime_ns)
    if merken and k in _SHA:
        return _SHA[k]
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    if not merken:
        return h.hexdigest()
    if len(_SHA) > 5000:
        _SHA.clear()
    _SHA[k] = h.hexdigest()
    return _SHA[k]


def verzeichnis(ordner):
    """ablage.json: {'dateien': {relativer Pfad: {version, sha256, groesse, gespeichert, von, quelle, ...}}}."""
    try:
        d = json.loads((Path(ordner) / PROTOKOLL / VERZEICHNIS).read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("dateien"), dict):
            return d
    except (OSError, ValueError):
        pass
    return dict(dateien={})


def _verzeichnis_schreiben(ordner, d):
    p = Path(ordner) / PROTOKOLL
    p.mkdir(parents=True, exist_ok=True)
    tmp = p / (VERZEICHNIS + f".{os.getpid()}.neu")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p / VERZEICHNIS)


def protokoll_schreiben(ordner, kuerzel, eintrag):
    """Eine Zeile an protokoll_<Kürzel>.jsonl anhängen (jeder Platz schreibt nur seine eigene Datei)."""
    p = Path(ordner) / PROTOKOLL
    p.mkdir(parents=True, exist_ok=True)
    e = dict(eintrag, zeit=datetime.datetime.now().isoformat(timespec="seconds"), von=kuerzel,
             platz=socket.gethostname())
    datei = p / f"protokoll_{sauber(kuerzel) or 'ICH'}.jsonl"
    anfang = ""
    try:
        with open(datei, "rb") as f:        # nach Absturz halbe letzte Zeile: neue Zeile beginnen
            f.seek(-1, os.SEEK_END)
            anfang = "" if f.read(1) == b"\n" else "\n"
    except OSError:
        pass
    with open(datei, "a", encoding="utf-8") as f:
        f.write(anfang + json.dumps(e, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return e


def protokoll(ordner):
    """Alle Einträge aller Plätze, nach Zeit."""
    out = []
    try:
        dateien = list((Path(ordner) / PROTOKOLL).glob("protokoll_*.jsonl"))
    except OSError:
        return out
    for d in dateien:
        try:
            for z in d.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(z)
                except ValueError:
                    continue        # halb geschriebene letzte Zeile nach Absturz
                if isinstance(e, dict):
                    out.append(e)
        except OSError:
            continue
    return sorted(out, key=lambda e: str(e.get("zeit") or ""))


class Gesperrt(Exception):
    """Ein anderer Platz speichert gerade in diesen Ordner."""


def sperren(ordner, kuerzel, jetzt=None):
    """Sperre exklusiv anlegen; eine verwaiste (älter als SPERRE_MIN) wird übernommen. Gesperrt: anderer Platz."""
    p = Path(ordner) / PROTOKOLL
    p.mkdir(parents=True, exist_ok=True)
    s = p / SPERRE
    jetzt = jetzt or datetime.datetime.now()
    inhalt = json.dumps(dict(von=kuerzel, platz=socket.gethostname(), pid=os.getpid(),
                             zeit=jetzt.isoformat(timespec="seconds")), ensure_ascii=False)
    for _ in range(2):
        try:
            fd = os.open(s, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            alt = sperre_lesen(ordner)
            zeit = _zeit(alt.get("zeit")) if alt else None
            if zeit is None or (jetzt - zeit).total_seconds() > SPERRE_MIN * 60 or (
                    alt.get("platz") == socket.gethostname() and alt.get("pid") == os.getpid()):
                try:
                    s.unlink()
                except OSError:
                    pass
                continue
            raise Gesperrt(f"{alt.get('von') or 'Ein Kollege'} ({alt.get('platz') or '?'}) speichert gerade in "
                           f"diesen Ordner (seit {str(alt.get('zeit'))[11:16]} Uhr). Bitte gleich noch einmal.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(inhalt)
        return s
    raise Gesperrt("Die Sperre des Ordners lässt sich nicht anlegen.")


def sperre_lesen(ordner):
    try:
        d = json.loads((Path(ordner) / PROTOKOLL / SPERRE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def entsperren(ordner):
    try:
        (Path(ordner) / PROTOKOLL / SPERRE).unlink()
    except OSError:
        pass


def _zeit(text):
    try:
        return datetime.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def aufraeumen(ordner):
    """Nach einem Absturz: übrig gebliebene Zwischendateien entfernen und den unterbrochenen Speichervorgang
    melden. Ergebnis: dict(entfernt [Namen], unterbrochen Protokolleintrag 'begonnen' ohne Ende oder None)."""
    o = Path(ordner)
    entfernt = []
    if o.is_dir():
        try:
            reste = [p for p in o.rglob("*" + TEIL) if p.is_file()]
        except OSError:
            reste = []
        for p in reste:
            try:
                p.unlink()
                entfernt.append(str(p.relative_to(o)))
            except OSError:
                pass
    offen = {}
    for e in protokoll(o):
        if e.get("aktion") == "begonnen":
            offen[e.get("vorgang")] = e
        elif e.get("aktion") in ("fertig", "abgebrochen"):
            offen.pop(e.get("vorgang"), None)
    unterbrochen = max(offen.values(), key=lambda e: str(e.get("zeit"))) if offen else None
    return dict(entfernt=entfernt, unterbrochen=unterbrochen)


def unterbrochen_vermerken(ordner, kuerzel, eintrag):
    """Unterbrochenen Vorgang als 'abgebrochen' abschließen (wird danach nicht mehr gemeldet)."""
    protokoll_schreiben(ordner, kuerzel, dict(aktion="abgebrochen", vorgang=eintrag.get("vorgang"),
                                              grund="nach Programmabsturz erkannt"))


# ------------------------------------------------------------------ Vergleich und Speichern
def ziel_relativ(v, dok):
    return f"{v.kategorie_ordner(dok.kategorie)}/{sauber(dok.name) or dok.pfad.name}"


def vorhandene(ordner):
    """Dateien im Angebotsordner (ohne _Protokoll, _Versionen, Zwischendateien): [(relativer Pfad, Größe, Zeit)]."""
    o = Path(ordner)
    out = []
    if not o.is_dir():
        return out
    try:
        for p in sorted(o.rglob("*")):
            if p.is_file() and not _ueberspringen(p, o):
                st = p.stat()
                out.append((p.relative_to(o).as_posix(), st.st_size, st.st_mtime))
    except OSError:
        pass
    return out


def vergleichen(v, ordner, dokumente):
    """Status je Dokument im Zielordner: {id(dok): (Status, Hinweis)}. GLEICH = gleiche Datei unter dem Zielnamen;
    SCHON = gleicher Inhalt liegt schon unter anderem Namen/Ordner (laut Verzeichnis); GEAENDERT = Zielname belegt,
    anderer Inhalt; NEU sonst."""
    o = Path(ordner) if ordner else None
    verz = verzeichnis(o)["dateien"] if o and o.is_dir() else {}
    nach_sha = {}
    for rel, e in verz.items():
        if isinstance(e, dict) and e.get("sha256"):
            nach_sha.setdefault(e["sha256"], rel)
    out = {}
    for d in dokumente:
        rel = ziel_relativ(v, d)
        ziel = o / rel if o else None
        try:
            sha = pruefsumme(d.pfad)
        except OSError:
            out[id(d)] = (NEU, "Quelle nicht lesbar")
            continue
        if ziel is not None and ziel.is_file():
            try:
                gleich = ziel.stat().st_size == d.groesse and pruefsumme(ziel) == sha
            except OSError:
                gleich = False
            if gleich:
                out[id(d)] = (GLEICH, rel)
                continue
            e = verz.get(rel) or {}
            out[id(d)] = (GEAENDERT, f"vorhanden: Version {e.get('version') or 1}"
                          + (f" vom {_kurz(e.get('gespeichert'))}" if e.get("gespeichert") else ""))
            continue
        if sha in nach_sha and o is not None and (o / nach_sha[sha]).is_file():
            out[id(d)] = (SCHON, nach_sha[sha])
            continue
        out[id(d)] = (NEU, "")
    return out


def _kurz(iso):
    z = _zeit(iso)
    return z.strftime("%d.%m.%Y %H:%M") if z else str(iso or "")


def _sicher_kopieren(quelle, ziel):
    """Kopie über Zwischendatei mit Prüfung; erst danach der endgültige Name. Gibt die Prüfsumme zurück."""
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    teil = ziel.with_name(ziel.name + TEIL)
    try:
        with open(quelle, "rb") as q, open(teil, "wb") as z:
            shutil.copyfileobj(q, z, 1 << 20)
            z.flush()
            os.fsync(z.fileno())
        try:
            shutil.copystat(quelle, teil)
        except OSError:
            pass
        sha = pruefsumme(quelle)
        if teil.stat().st_size != Path(quelle).stat().st_size or pruefsumme(teil, merken=False) != sha:
            raise OSError("Kopie stimmt nicht mit dem Original überein (Netzwerk unterbrochen?)")
        if ziel.exists():
            raise FileExistsError(str(ziel))
        os.replace(teil, ziel)
        return sha
    except BaseException:
        try:
            teil.unlink()
        except OSError:
            pass
        raise


def _frei(ziel):
    """Name_V2.pdf, Name_V3.pdf … – erster freier Name neben ziel."""
    ziel = Path(ziel)
    i = 2
    while True:
        k = ziel.with_name(f"{ziel.stem}_V{i}{ziel.suffix}")
        if not k.exists():
            return k, i
        i += 1


def _wegsichern(ziel, version):
    """Vorhandene Datei nach <Kategorie>/_Versionen/Name_V<n>_<Zeit>.ext verschieben (nie löschen)."""
    ziel = Path(ziel)
    zeit = datetime.datetime.fromtimestamp(ziel.stat().st_mtime).strftime("%Y-%m-%d_%H%M")
    vo = ziel.parent / VERSIONEN
    vo.mkdir(parents=True, exist_ok=True)
    neu = vo / f"{ziel.stem}_V{version}_{zeit}{ziel.suffix}"
    i = 1
    while neu.exists():
        i += 1
        neu = vo / f"{ziel.stem}_V{version}_{zeit}_{i}{ziel.suffix}"
    os.replace(ziel, neu)
    return neu


@dataclass
class Bericht:
    ordner: Path = None
    gespeichert: list = field(default_factory=list)     # [relativer Pfad]
    ersetzt: list = field(default_factory=list)         # [(relativer Pfad, gesicherte alte Fassung)]
    versionen: list = field(default_factory=list)       # [relativer Pfad der neuen Version daneben]
    uebersprungen: list = field(default_factory=list)   # [(Name, Grund)]
    fehler: list = field(default_factory=list)          # [(Name, Fehlertext)]
    abgebrochen: bool = False
    angelegt: bool = False
    verschoben: list = field(default_factory=list)      # [(alter Pfad, neuer Pfad)] Original entfernt (26.11.2026)
    nicht_entfernt: list = field(default_factory=list)  # [(Name, Grund)] Kopie geprüft, Original bleibt (gesperrt)

    @property
    def ok(self):
        return not self.fehler and not self.abgebrochen

    def text(self):
        t = [f"{len(self.gespeichert)} Datei(en) gespeichert"]
        if self.verschoben:
            t.append(f"{len(self.verschoben)} verschoben (Original entfernt)")
        if self.nicht_entfernt:
            t.append(f"{len(self.nicht_entfernt)} Original(e) noch nicht entfernt")
        if self.ersetzt:
            t.append(f"{len(self.ersetzt)} ersetzt (alte Fassung in {VERSIONEN})")
        if self.versionen:
            t.append(f"{len(self.versionen)} als neue Version")
        if self.uebersprungen:
            t.append(f"{len(self.uebersprungen)} übersprungen")
        if self.fehler:
            t.append(f"{len(self.fehler)} Fehler")
        return ", ".join(t) + "."


def _gleicher_pfad(a, b):
    try:
        return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))
    except OSError:
        return str(a).lower() == str(b).lower()


def _liegt_in(pfad, ordner):
    try:
        return Path(pfad).resolve().is_relative_to(Path(ordner).resolve())
    except (OSError, ValueError):
        return False


def _original_entfernen(b, verz, o, d, ziel):
    """Verschieben (26.11.2026): das Original erst löschen, wenn die Datei im Angebotsordner vollständig ist (Größe
    und SHA-256 gleich). Gesperrt oder nicht prüfbar: Original bleibt (b.nicht_entfernt), nie geht etwas verloren.
    Ergebnis: True = verschoben."""
    if d.intern:
        return False
    ziel = Path(ziel)
    if _gleicher_pfad(d.pfad, ziel):
        return False                # nie die abgelegte Datei selbst löschen
    try:
        if not ziel.is_file():
            raise OSError("die Datei fehlt im Angebotsordner")
        if ziel.stat().st_size != d.pfad.stat().st_size or \
                pruefsumme(ziel, merken=False) != pruefsumme(d.pfad, merken=False):
            raise OSError("die Datei im Angebotsordner weicht vom Original ab")
        os.unlink(d.pfad)
    except FileNotFoundError:
        if d.pfad.exists():
            b.nicht_entfernt.append((d.name, "nicht prüfbar"))
            return False
    except OSError as e:
        b.nicht_entfernt.append((d.name, f"Original bleibt liegen ({getattr(e, 'strerror', None) or e}), wird "
                                         "beim nächsten Mal entfernt"))
        return False
    verz.setdefault("verschoben", {})[str(d.pfad)] = ziel.relative_to(o).as_posix()
    b.verschoben.append((str(d.pfad), str(ziel)))
    return True


def ablegen(v, ordner, dokumente, kuerzel="ICH", aktionen=None, angebot="", nummer="", fortschritt=None,
            anlegen=False, verschieben=False):
    """Gewählte Dokumente in den Angebotsordner kopieren; verschieben=True (Patrick 26.11.2026): danach das Original
    entfernen (nur Kundendateien und Dokumente, nie programminterne Dateien, siehe _original_entfernen). aktionen = {id(dok): ERSETZEN | NEUE_VERSION |
    UEBERSPRINGEN} für geänderte Dateien (fehlt: UEBERSPRINGEN – nie ungefragt überschreiben). fortschritt(i, n,
    Name) -> False bricht ab. Der Angebotsordner muss vorhanden sein (legt PPEASE an, Patrick 19.11.); nur
    anlegen=True legt ihn an (für später/Tests). Unterordner der Kategorien entstehen bei Bedarf. Ein Netzwerkfehler bricht den Rest ab (schon kopierte bleiben vollständig).
    Ergebnis: Bericht."""
    o = Path(ordner)
    b = Bericht(ordner=o)
    gewaehlt = [d for d in dokumente if d.gewaehlt]
    if not o.exists():
        if not anlegen:
            b.fehler.append(("", f"Der Angebotsordner {o} fehlt (wird in PPEASE angelegt)."))
            return b
        o.mkdir(parents=True)
        b.angelegt = True
    aktionen = aktionen or {}
    sperren(o, kuerzel)
    vorgang = f"{datetime.datetime.now():%Y%m%d%H%M%S}-{os.getpid()}"
    try:
        protokoll_schreiben(o, kuerzel, dict(aktion="begonnen", vorgang=vorgang, angebot=angebot, nummer=nummer,
                                             dateien=[d.name for d in gewaehlt]))
        status = vergleichen(v, o, gewaehlt)
        verz = verzeichnis(o)
        for i, d in enumerate(gewaehlt):
            if fortschritt and fortschritt(i, len(gewaehlt), d.name) is False:
                b.abgebrochen = True
                break
            if _liegt_in(d.pfad, o):        # liegt schon im PPEASE-Angebotsordner (z. B. verschobene Anfrage)
                b.uebersprungen.append((d.name, "liegt schon im Angebotsordner"))
                continue
            st, hinweis = status[id(d)]
            rel = ziel_relativ(v, d)
            ziel = o / rel
            if st in (GLEICH, SCHON):
                if verschieben and _original_entfernen(b, verz, o, d, ziel if st == GLEICH else o / hinweis):
                    _verzeichnis_schreiben(o, dict(verz, nummer=nummer))
                    protokoll_schreiben(o, kuerzel, dict(aktion="verschoben", vorgang=vorgang, quelle=str(d.pfad),
                                                         datei=rel if st == GLEICH else hinweis))
                    continue
                b.uebersprungen.append((d.name, "schon abgelegt" + (f" als {hinweis}" if st == SCHON else "")))
                continue
            try:
                if st == GEAENDERT:
                    a = aktionen.get(id(d), UEBERSPRINGEN)
                    if a == UEBERSPRINGEN:
                        b.uebersprungen.append((d.name, "vorhanden mit anderem Inhalt, nicht ersetzt"))
                        continue
                    alt = verz["dateien"].get(rel) or {}
                    version = int(alt.get("version") or 1)
                    if a == ERSETZEN:
                        gesichert = _wegsichern(ziel, version)
                        sha = _sicher_kopieren(d.pfad, ziel)
                        b.ersetzt.append((rel, gesichert.relative_to(o).as_posix()))
                        neu_rel, neu_version = rel, version + 1
                    else:
                        k, n = _frei(ziel)
                        sha = _sicher_kopieren(d.pfad, k)
                        neu_rel, neu_version = k.relative_to(o).as_posix(), n
                        b.versionen.append(neu_rel)
                else:
                    sha = _sicher_kopieren(d.pfad, ziel)
                    neu_rel, neu_version = rel, 1
                    b.gespeichert.append(rel)
                if st == GEAENDERT and a == ERSETZEN:
                    b.gespeichert.append(rel)
                elif st == GEAENDERT:
                    b.gespeichert.append(neu_rel)
                verz["dateien"][neu_rel] = dict(
                    version=neu_version, sha256=sha, groesse=d.groesse, quelle=str(d.pfad), quelle_art=d.quelle,
                    gespeichert=datetime.datetime.now().isoformat(timespec="seconds"), von=kuerzel,
                    geaendert=datetime.datetime.fromtimestamp(d.pfad.stat().st_mtime).isoformat(timespec="seconds"),
                    angebot=angebot)
                _verzeichnis_schreiben(o, dict(verz, nummer=nummer))       # erst Verzeichnis, dann Original weg
                if verschieben and _original_entfernen(b, verz, o, d, o / neu_rel):
                    verz["dateien"][neu_rel]["verschoben"] = True
                    _verzeichnis_schreiben(o, dict(verz, nummer=nummer))
                protokoll_schreiben(o, kuerzel, dict(aktion="gespeichert", vorgang=vorgang, datei=neu_rel,
                                                     version=neu_version, quelle=str(d.pfad),
                                                     art=st if st != GEAENDERT else aktionen.get(id(d)),
                                                     sha256=sha))
            except FileExistsError:
                b.uebersprungen.append((d.name, "inzwischen von einem Kollegen abgelegt"))
            except OSError as e:
                b.fehler.append((d.name, str(e)))
                if not Path(v.ordner or o).exists() or not o.exists():
                    b.abgebrochen = True        # Netzlaufwerk weg: Rest nicht versuchen
                    break
        if fortschritt:
            fortschritt(len(gewaehlt), len(gewaehlt), "")
        protokoll_schreiben(o, kuerzel, dict(aktion="abgebrochen" if b.abgebrochen else "fertig", vorgang=vorgang,
                                             ergebnis=b.text()))
    except OSError as e:
        b.fehler.append(("", str(e)))
        b.abgebrochen = True
    finally:
        entsperren(o)
    return b


# ------------------------------------------------------------------ Angebot <-> PPEASE-Nummer
def merken(db, angebot_id, nummer, kunde="", bezeichnung="", ordner=""):
    """PPEASE-Nummer am Angebot merken (Zusatzdaten, keine neue Spalte)."""
    if not angebot_id:
        return
    db.zusatz_setzen(angebot_id, ZUSATZ, dict(nummer=nummer, kunde=kunde or "", bezeichnung=bezeichnung or "",
                                              ordner=str(ordner or ""),
                                              zuletzt=datetime.datetime.now().isoformat(timespec="seconds")))


def gemerkt(db, angebot_id):
    if not angebot_id:
        return {}
    try:
        w = db.zusatz(angebot_id, ZUSATZ)
    except Exception:       # noqa: BLE001
        return {}
    return w if isinstance(w, dict) else {}


def wo(db, angebot_id, pfad, ordner=None):
    """Wo liegt eine Datei jetzt? Gibt es pfad noch, pfad selbst; sonst die Stelle im PPEASE-Angebotsordner, wenn sie
    dorthin verschoben wurde (ablage.json „verschoben“, auch über den Dateinamen); sonst None."""
    p = Path(pfad)
    if p.exists():
        return p
    o = Path(ordner) if ordner else Path(gemerkt(db, angebot_id).get("ordner") or "") if angebot_id else None
    if not o or not str(o) or str(o) == "." or not o.is_dir():
        return None
    verschoben = verzeichnis(o).get("verschoben") or {}
    schluessel = {str(k).replace("\\", "/").lower(): r for k, r in verschoben.items()}
    rel = schluessel.get(str(p).replace("\\", "/").lower())
    if rel is None:         # Angebotsordner inzwischen woanders (gemeinsamer Ordner umgezogen): über den Namen
        rel = next((r for k, r in verschoben.items() if Path(str(k).replace("\\", "/")).name.lower() == p.name.lower()),
                   None)
    if rel and (o / rel).exists():
        return o / rel
    return None


# ------------------------------------------------------------------ Für später: Schnittstelle und Suche
class Quelle:
    """Anschluss für eine spätere PPEASE-Schnittstelle (API, Datenbank oder Export-Datei). angebot(nummer) liefert
    dict(kunde, bezeichnung, kundennr, datum) oder None. Neue Quellen in QUELLEN eintragen; die Einstellung
    ppease_quelle wählt sie."""
    name = "keine"
    titel = "Keine Schnittstelle (Nummer von Hand)"

    def verfuegbar(self):
        return False

    def angebot(self, nummer):  # noqa: ARG002
        return None


QUELLEN = {Quelle.name: Quelle}


def quelle(db):
    try:
        n = db.einstellung(E_QUELLE) or Quelle.name
    except Exception:       # noqa: BLE001
        n = Quelle.name
    return QUELLEN.get(n, Quelle)()


def suchen(v, text, hoechstens=200):
    """Zentrale Suche im Hauptordner nach Angebotsnummer, Kunde (Ordnername) oder Dokumentname.
    Ergebnis: [(Ordner, [passende relative Dateien])]."""
    t = str(text or "").strip().lower()
    if not t or not v.ordner:
        return []
    out = []
    for ort in _jahre(v.ordner) + [Path(v.ordner)]:
        try:
            ordner = [o for o in ort.iterdir() if o.is_dir() and not re.fullmatch(r"\d{4}", o.name)]
        except OSError:
            continue
        for o in sorted(ordner):
            dateien = [rel for rel, _, _ in vorhandene(o) if t in rel.lower()]
            if t in o.name.lower() or dateien:
                out.append((o, dateien))
                if len(out) >= hoechstens:
                    return out
    return out
