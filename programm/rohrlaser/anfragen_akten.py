"""Anfragenverwaltung: jede Anfrage als Akte mit Verlauf (Patrick 12.11.2026, Konzept „Outlook-Anbindung und
Anfragenverwaltung“, Paket 1, Freigabe 13.11.2026).

Eine Anfrage durchläuft Neu → In Bearbeitung → Erledigt. Ihr Stand liegt nicht in der Datendatei eines Arbeitsplatzes,
sondern als Akte in einem Ordner, den alle Arbeitsplätze sehen (Unterordner ORDNER im gemeinsamen Ordner, ohne
gemeinsamen Ordner neben der Datendatei). Damit sieht jeder Platz eine Übernahme beim nächsten Blick (30 s), ohne
Server und ohne Abgleich der Datendateien:

    Anfragen_Akten/2026/A-2026-00042/
        kopf.json             einmal beim Eingang geschrieben, nie geändert (Quelle, Absender, Betreff, Eingang,
                              Kurztext, Kunde, Dateien mit Größe und SHA-256)
        Dateien/              Kopie der Eingangsdateien (Mail, STEP, PDF …), nie gelöscht
        verlauf_PB.jsonl      Verlauf: jeder Mitarbeiter hängt nur an seine eigene Datei an (ein Schreiber je Datei)
        uebernahme_1.sperre   exklusiv angelegt: wer sie anlegt, hat die Anfrage (nach Zurückgeben: _2 …)
    Anfragen_Akten/_schluessel/<SHA>.akte   Doppel-Schutz: eine Mail bzw. Leitdatei ergibt nie zwei Akten

Der Stand einer Akte (Status, Bearbeiter, Priorität, Notizen, Angebote, Zeiten) ergibt sich aus allen Verlaufsdateien
(stand_aus_verlauf), sortiert nach Zeit. Das ist zugleich die vollständige Änderungshistorie. Löschen gibt es nicht.

Die Klasse OrdnerAblage ist die Zugriffsschicht (abgestimmt mit dem Plan PostgreSQL, 12.11.2026): alle(), lesen(nr),
anlegen(), ereignis(), uebernehmen(). Später kommt eine DbAblage mit denselben Aufrufen auf db_verbindung dazu
(Tabellen anfragen mit id/uid/version, anfrage_verlauf nur INSERT, anfrage_angebote; uebernehmen = UPDATE … WHERE
status='neu'); die Dateien bleiben im Ordner.

Ohne Qt; die Aktionen nehmen jetzt als Parameter, damit sie testbar sind."""
import datetime
import hashlib
import json
import os
import re
import shutil
import socket
import time
from pathlib import Path

ORDNER = "Anfragen_Akten"
KOPF = "kopf.json"
DATEIEN = "Dateien"
SCHLUESSEL = "_schluessel"
NUMMER = re.compile(r"^A-(\d{4})-(\d{5})$")
EINSTELLUNG = "anfragen_verwaltung"

NEU, BEARBEITUNG, ERLEDIGT = "neu", "in_bearbeitung", "erledigt"
STATUS = (NEU, BEARBEITUNG, ERLEDIGT)
STATUS_TEXT = {NEU: "Neu", BEARBEITUNG: "In Bearbeitung", ERLEDIGT: "Erledigt"}
PRIORITAETEN = ("niedrig", "normal", "hoch", "eilt")
PRIORITAET_TEXT = {"niedrig": "Niedrig", "normal": "Normal", "hoch": "Hoch", "eilt": "Eilt"}

# Aktionen im Verlauf
EINGEGANGEN, DATEI_DAZU, ZUGEWIESEN, UEBERNOMMEN = "eingegangen", "datei_dazu", "zugewiesen", "uebernommen"
BEARBEITER, PRIORITAET, NOTIZ, STAND = "bearbeiter", "prioritaet", "notiz", "stand"
ANGEBOT, ERLEDIGT_A, WIEDER, ZURUECK = "angebot_verknuepft", "erledigt", "wieder_geoeffnet", "zurueckgegeben"
AKTION_TEXT = {EINGEGANGEN: "Eingegangen", DATEI_DAZU: "Datei dazu", ZUGEWIESEN: "Zugewiesen",
               UEBERNOMMEN: "Übernommen", BEARBEITER: "Bearbeiter geändert", PRIORITAET: "Priorität",
               NOTIZ: "Notiz", STAND: "Bearbeitungsstand", ANGEBOT: "Angebot verknüpft",
               ERLEDIGT_A: "Als erledigt markiert", WIEDER: "Wieder geöffnet", ZURUECK: "Zurückgegeben"}

# Dateiarten (Anzeige als Kurzwort)
ARTEN = {"step": {".step", ".stp", ".igs", ".iges"}, "pdf": {".pdf"}, "dxf": {".dxf", ".dwg"},
         "excel": {".xlsx", ".xls", ".xlsm", ".csv"}, "bild": {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"},
         "mail": {".msg", ".eml"}, "zip": {".zip"}}
ART_TEXT = {"step": "STEP", "pdf": "PDF", "dxf": "DXF/DWG", "excel": "Excel", "bild": "Bild", "mail": "Mail",
            "zip": "ZIP", "sonst": "Datei"}
# nie öffnen oder in die Kalkulation übernehmen (Konzept, Sicherheit der Anhänge)
GEFAEHRLICH = {".exe", ".bat", ".cmd", ".com", ".js", ".jse", ".vbs", ".vbe", ".ps1", ".scr", ".lnk", ".msi", ".hta",
               ".pif", ".reg", ".wsf", ".cpl", ".jar"}
MAKRO = {".xlsm", ".xlsb", ".docm", ".pptm"}

ERINNERN_STUNDEN = 24       # neue Anfrage so lange ohne Übernahme: Hinweis „wartet seit …“
KURZ_ZEICHEN = 240          # Kurzbeschreibung in der Liste


class AblageFehler(Exception):
    """Text ist für den Benutzer gedacht."""


class SchonUebernommen(AblageFehler):
    def __init__(self, kuerzel, zeit=""):
        self.kuerzel, self.zeit = kuerzel, zeit
        z = _zeit_text(zeit)
        super().__init__(f"Die Anfrage hat schon {kuerzel or 'jemand'} übernommen" + (f" ({z})." if z else "."))


def art(name):
    e = Path(str(name)).suffix.lower()
    return next((a for a, endungen in ARTEN.items() if e in endungen), "sonst")


def warnung(name):
    e = Path(str(name)).suffix.lower()
    if e in GEFAEHRLICH:
        return "Ausführbare Datei: wird nicht geöffnet"
    if e in MAKRO:
        return "Enthält Makros: nur öffnen, wenn der Absender bekannt ist"
    return ""


def pruefsumme(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _jetzt(jetzt=None):
    return (jetzt or datetime.datetime.now()).replace(microsecond=0).isoformat()


def _zeit_text(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso)).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return ""


def _datum(iso):
    if isinstance(iso, datetime.datetime):
        return iso
    try:
        return datetime.datetime.fromisoformat(str(iso or ""))
    except ValueError:
        return None


def _json_schreiben(pfad, daten):
    tmp = pfad.with_name(pfad.name + ".neu")
    tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, pfad)


def _exklusiv(pfad, inhalt):
    """Datei nur anlegen, wenn es sie noch nicht gibt (atomar, auch auf Netzlaufwerken). Ergebnis: True = angelegt."""
    try:
        fd = os.open(pfad, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(inhalt)
    return True


def _frei(ziel):
    ziel, i = Path(ziel), 1
    neu = ziel
    while neu.exists():
        i += 1
        neu = ziel.with_name(f"{ziel.stem} ({i}){ziel.suffix}")
    return neu


def _sauber(text):
    return re.sub(r"[^0-9A-Za-z_-]", "_", str(text))


def kurztext(text, n=KURZ_ZEICHEN):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


# ------------------------------------------------------------------ Stand aus dem Verlauf
def stand_aus_verlauf(ereignisse):
    """Stand einer Akte aus ihren Ereignissen (beliebige Reihenfolge, sortiert nach Zeit, Kürzel, Nummer). Ein
    Übergang, der nicht passt (z. B. zweites „übernommen“ ohne Zurückgeben), zählt nicht und bekommt 'ungueltig'."""
    s = dict(status=NEU, bearbeiter="", zugewiesen="", zugewiesen_von="", prioritaet="normal", notizen=[],
             stand="", angebote=[], eingang="", uebernommen_am="", erledigt_am="", erledigt_von="", generation=1,
             dazu=[], letzte="")
    for e in sorted(ereignisse, key=lambda e: (e.get("zeit", ""), e.get("kuerzel", ""), e.get("nr", 0))):
        a, k, z = e.get("aktion"), e.get("kuerzel", ""), e.get("zeit", "")
        e["ungueltig"] = False
        if a == EINGEGANGEN:
            s["eingang"] = s["eingang"] or z
        elif a == DATEI_DAZU:
            namen = {d.get("name") for d in s["dazu"]}
            s["dazu"] += [d for d in e.get("dateien", []) if d.get("name") not in namen]
        elif a == ZUGEWIESEN:
            if s["status"] != NEU:
                e["ungueltig"] = True
                continue
            s["zugewiesen"], s["zugewiesen_von"] = e.get("neu", ""), k
        elif a == UEBERNOMMEN:
            if s["status"] != NEU or e.get("generation", 1) != s["generation"]:
                e["ungueltig"] = True
                continue
            s.update(status=BEARBEITUNG, bearbeiter=e.get("neu") or k, uebernommen_am=z, zugewiesen="")
        elif a == BEARBEITER:
            if s["status"] == NEU:
                e["ungueltig"] = True
                continue
            s["bearbeiter"] = e.get("neu", "")
        elif a == PRIORITAET:
            s["prioritaet"] = e.get("neu") if e.get("neu") in PRIORITAETEN else "normal"
        elif a == NOTIZ:
            s["notizen"].append(dict(zeit=z, kuerzel=k, text=e.get("neu", "")))
        elif a == STAND:
            s["stand"] = e.get("neu", "")
        elif a == ANGEBOT:
            n = e.get("neu", "")
            if n and n not in s["angebote"]:
                s["angebote"].append(n)
        elif a == ERLEDIGT_A:
            if s["status"] != BEARBEITUNG:
                e["ungueltig"] = True
                continue
            s.update(status=ERLEDIGT, erledigt_am=z, erledigt_von=k)
        elif a == WIEDER:
            if s["status"] != ERLEDIGT:
                e["ungueltig"] = True
                continue
            s.update(status=BEARBEITUNG, erledigt_am="", erledigt_von="")
        elif a == ZURUECK:
            if s["status"] != BEARBEITUNG:
                e["ungueltig"] = True
                continue
            s.update(status=NEU, bearbeiter="", uebernommen_am="", generation=s["generation"] + 1)
        s["letzte"] = z
    return s


# ------------------------------------------------------------------ Akte
class Akte:
    """Eine Anfrage: pfad (Ordner der Akte), nr (A-2026-00042), kopf (dict), verlauf [dict], stand (dict)."""

    def __init__(self, pfad, kopf, verlauf):
        self.pfad, self.kopf, self.verlauf = Path(pfad), kopf, verlauf
        self.nr = self.pfad.name
        self.stand = stand_aus_verlauf(verlauf)

    @property
    def absender(self):
        return self.kopf.get("absender_name") or self.kopf.get("absender") or ""

    @property
    def betreff(self):
        return self.kopf.get("betreff") or self.kopf.get("name") or self.nr

    @property
    def kunde(self):
        return str(self.kopf.get("kundennr") or "")

    @property
    def eingang(self):
        return _datum(self.kopf.get("eingang")) or _datum(self.stand["eingang"])

    def dateien(self):
        """[{name, pfad, art, groesse, sha256, warnung}] – Kopf und später dazugekommene, ohne Doppel."""
        out, gesehen = [], set()
        for d in list(self.kopf.get("dateien", [])) + list(self.stand["dazu"]):
            name = d.get("name") if isinstance(d, dict) else str(d)
            if not name or (d.get("datei", name) if isinstance(d, dict) else name) in gesehen:
                continue
            gesehen.add(d.get("datei", name) if isinstance(d, dict) else name)
            e = dict(d) if isinstance(d, dict) else dict(name=name)
            e["pfad"] = self.pfad / DATEIEN / e.get("datei", name)
            e.setdefault("art", art(name))
            e["warnung"] = warnung(name)
            out.append(e)
        return out

    @property
    def status(self):
        return self.stand["status"]

    @property
    def bearbeiter(self):
        return self.stand["bearbeiter"]

    @property
    def prioritaet(self):
        return self.stand["prioritaet"]

    def wartet(self, jetzt=None):
        """Neu und älter als ERINNERN_STUNDEN (Erinnerung)."""
        e = self.eingang
        return bool(self.status == NEU and e and (jetzt or datetime.datetime.now()) - e
                    > datetime.timedelta(hours=ERINNERN_STUNDEN))

    def suchtext(self):
        return " ".join([self.nr, self.absender, self.kopf.get("absender", ""), self.betreff,
                         self.kopf.get("kurz", ""), self.kopf.get("kunde_name", ""), self.kunde, self.bearbeiter,
                         " ".join(d["name"] for d in self.dateien()), " ".join(self.stand["angebote"])]).lower()

    def __repr__(self):
        return f"Akte({self.nr}, {self.status}, {self.bearbeiter!r})"


ANHAENGE = "Anhaenge"       # Unterordner von Dateien: aus den Mails ausgepackte Anhänge (zum Ansehen)


def anhaenge_auspacken(dateien_ordner, liste, vorhanden=()):
    """Anhänge der Mails in liste (Einträge wie im Kopf) nach Dateien/Anhaenge auspacken, damit man sie direkt sieht
    und öffnen kann. Die Mail bleibt das Original; Kalkulieren nimmt die Mail (sie wird dort ausgepackt). Kleine Bilder
    (Logo, Signatur) fehlen, ausführbare Dateien werden nur genannt, nicht gespeichert. Ergebnis: neue Einträge."""
    from . import anfragen, mail
    vorhanden = set(vorhanden)
    neu = []
    for e in list(liste):
        if e.get("art") != "mail":
            continue
        m = mail.lesen(Path(dateien_ordner) / e.get("datei", e["name"]))
        if m is None:
            continue
        for name, daten in m.anhaenge:
            name = Path(str(name)).name or "Anhang"
            endung = Path(name).suffix.lower()
            if endung in anfragen.BILD and len(daten) < anfragen.BILD_MIN:
                continue
            h = hashlib.sha256(daten).hexdigest()
            if h in vorhanden:
                continue
            vorhanden.add(h)
            eintrag = dict(name=name, art=art(name), groesse=len(daten), sha256=h, aus_mail=e["name"])
            if endung in GEFAEHRLICH:
                eintrag["gesperrt"] = True
            else:
                ziel = _frei(Path(dateien_ordner) / ANHAENGE / name)
                ziel.parent.mkdir(exist_ok=True)
                ziel.write_bytes(daten)
                eintrag["datei"] = f"{ANHAENGE}/{ziel.name}"
            neu.append(eintrag)
    return neu


# ------------------------------------------------------------------ Ablage im Ordner
class OrdnerAblage:
    """Akten in einem Ordner (gemeinsamer Ordner oder lokal). kuerzel: wer hier arbeitet (schreibt nur in
    verlauf_<kuerzel>.jsonl)."""

    def __init__(self, wurzel, kuerzel, platz=""):
        self.wurzel = Path(wurzel)
        self.kuerzel = (kuerzel or "").strip() or "?"
        self.platz = platz
        self._cache = {}        # Ordner -> (Prüfstempel, Akte)

    # ---------------------------------------------- lesen
    def _akten_ordner(self):
        try:
            jahre = [j for j in self.wurzel.iterdir() if j.is_dir() and j.name.isdigit()]
        except OSError:
            return []
        out = []
        for j in sorted(jahre):
            try:
                out += sorted(p for p in j.iterdir() if p.is_dir() and NUMMER.match(p.name))
            except OSError:
                continue
        return out

    @staticmethod
    def _stempel(o):
        st = []
        try:
            for p in o.iterdir():
                if p.name == KOPF or p.name.startswith("verlauf_"):
                    s = p.stat()
                    st.append((p.name, s.st_size, s.st_mtime_ns))
        except OSError:
            return None
        return tuple(sorted(st))

    def _akte_lesen(self, o):
        st = self._stempel(o)
        if st is None:
            return None
        alt = self._cache.get(o)
        if alt and alt[0] == st:
            return alt[1]
        try:
            kopf = json.loads((o / KOPF).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None         # wird gerade angelegt
        verlauf = []
        for v in sorted(o.glob("verlauf_*.jsonl")):
            try:
                zeilen = v.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for z in zeilen:
                try:
                    e = json.loads(z)
                except ValueError:
                    continue        # halb geschriebene letzte Zeile
                if isinstance(e, dict) and e.get("aktion"):
                    verlauf.append(e)
        a = Akte(o, kopf, verlauf)
        self._cache[o] = (st, a)
        return a

    def alle(self):
        """Alle Akten (älteste Nummer zuerst)."""
        return [a for a in map(self._akte_lesen, self._akten_ordner()) if a is not None]

    def lesen(self, nr):
        m = NUMMER.match(str(nr or ""))
        if not m:
            return None
        o = self.wurzel / m.group(1) / nr
        return self._akte_lesen(o) if o.is_dir() else None

    def neu_lesen(self, akte):
        self._cache.pop(akte.pfad, None)
        return self._akte_lesen(akte.pfad) or akte

    # ---------------------------------------------- anlegen
    def _neue_nummer(self, jahr):
        """Ordner A-<jahr>-<n> exklusiv anlegen (mkdir ist atomar, auch auf Netzlaufwerken)."""
        o = self.wurzel / str(jahr)
        o.mkdir(parents=True, exist_ok=True)
        hoch = max((int(m.group(2)) for p in o.iterdir() if (m := NUMMER.match(p.name))), default=0)
        for n in range(hoch + 1, hoch + 1000):
            ziel = o / f"A-{jahr}-{n:05d}"
            try:
                ziel.mkdir()
            except FileExistsError:
                continue
            return ziel
        raise AblageFehler("Keine freie Anfrage-Nummer gefunden.")

    def schluessel_akte(self, schluessel):
        """Nummer der Akte zu einem Doppel-Schlüssel oder None."""
        try:
            nr = (self.wurzel / SCHLUESSEL / f"{_sauber(schluessel)[:120]}.akte").read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return nr or None

    def anlegen(self, kopf, dateien, schluessel, jetzt=None):
        """Neue Akte aus kopf (dict) und den Eingangsdateien (Pfade, werden kopiert). schluessel verhindert doppelte
        Akten (SHA-256 der Leitdatei, später die Nachrichten-ID aus Outlook); gibt es ihn schon, kommt die vorhandene
        Akte zurück. Ergebnis: (Akte oder None, neu angelegt?)."""
        jetzt = jetzt or datetime.datetime.now()
        schluessel = _sauber(schluessel)[:120]
        sd = self.wurzel / SCHLUESSEL
        sd.mkdir(parents=True, exist_ok=True)
        sdatei = sd / f"{schluessel}.akte"
        if not _exklusiv(sdatei, ""):
            nr = self.schluessel_akte(schluessel)
            return (self.lesen(nr) if nr else None), False
        try:
            o = self._neue_nummer(jetzt.year)
            (o / DATEIEN).mkdir()
            liste = []
            for p in map(Path, dateien):
                z = _frei(o / DATEIEN / p.name)
                shutil.copy2(p, z)
                liste.append(dict(name=z.name, art=art(z.name), groesse=z.stat().st_size, sha256=pruefsumme(z)))
            liste += anhaenge_auspacken(o / DATEIEN, liste, {d["sha256"] for d in liste})
            k = dict(kopf)
            k.update(nr=o.name, angelegt=_jetzt(jetzt), angelegt_von=self.kuerzel, schluessel=schluessel,
                     dateien=liste, kurz=kurztext(k.get("kurz", "")))
            if isinstance(k.get("eingang"), datetime.datetime):
                k["eingang"] = _jetzt(k["eingang"].replace(tzinfo=None))
            _json_schreiben(o / KOPF, k)
            sdatei.write_text(o.name, encoding="utf-8")
        except OSError:
            sdatei.unlink(missing_ok=True)
            raise
        a = self._akte_lesen(o)
        self.ereignis(a, EINGEGANGEN, neu=k.get("quelle", ""), jetzt=jetzt)
        return self.neu_lesen(a), True

    def dateien_dazu(self, akte, pfade, jetzt=None):
        """Später gekommene Dateien (Nachtrag) in die Akte kopieren, gleiche Inhalte nur einmal. Ergebnis: neue Namen."""
        vorhanden = {d.get("sha256") for d in akte.dateien() if d.get("sha256")}
        neu = []
        for p in map(Path, pfade):
            try:
                h = pruefsumme(p)
            except OSError:
                continue
            if h in vorhanden:
                continue
            z = _frei(akte.pfad / DATEIEN / p.name)
            shutil.copy2(p, z)
            vorhanden.add(h)
            neu.append(dict(name=z.name, art=art(z.name), groesse=z.stat().st_size, sha256=h))
        if neu:
            neu += anhaenge_auspacken(akte.pfad / DATEIEN, neu, vorhanden)
            self.ereignis(akte, DATEI_DAZU, dateien=neu, jetzt=jetzt)
        return [d["name"] for d in neu]

    # ---------------------------------------------- Verlauf
    def ereignis(self, akte, aktion, alt=None, neu=None, jetzt=None, **weitere):
        """Ein Ereignis an die eigene Verlaufsdatei der Akte anhängen. Ergebnis: das Ereignis."""
        v = akte.pfad / f"verlauf_{_sauber(self.kuerzel)}.jsonl"
        nr = sum(1 for e in akte.verlauf if e.get("kuerzel") == self.kuerzel) + 1
        e = dict(zeit=_jetzt(jetzt), kuerzel=self.kuerzel, platz=self.platz, aktion=aktion, nr=nr)
        if alt is not None:
            e["alt"] = alt
        if neu is not None:
            e["neu"] = neu
        e.update(weitere)
        with open(v, "a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        akte.verlauf.append(e)
        akte.stand = stand_aus_verlauf(akte.verlauf)
        self._cache.pop(akte.pfad, None)
        return e

    # ---------------------------------------------- Aktionen
    def uebernehmen(self, akte, bearbeiter=None, jetzt=None):
        """Anfrage übernehmen: genau einer gewinnt (Sperrdatei exklusiv). bearbeiter: Kürzel (Vorgabe: ich).
        SchonUebernommen: ein anderer war schneller. Ergebnis: die Akte (neu gelesen)."""
        akte = self.neu_lesen(akte)
        if akte.status != NEU:
            raise SchonUebernommen(akte.bearbeiter, akte.stand["uebernommen_am"])
        bearbeiter = (bearbeiter or self.kuerzel).strip()
        sperre = akte.pfad / f"uebernahme_{akte.stand['generation']}.sperre"
        if not _exklusiv(sperre, f"{bearbeiter}|{self.kuerzel}|{_jetzt(jetzt)}"):
            k, z = "", ""
            for _ in range(20):         # der Gewinner schreibt seinen Namen gleich nach dem Anlegen hinein
                try:
                    k, _, z = sperre.read_text(encoding="utf-8").split("|", 2)
                    break
                except (OSError, ValueError):
                    time.sleep(0.05)
            raise SchonUebernommen(k, z)
        self.ereignis(akte, UEBERNOMMEN, neu=bearbeiter, generation=akte.stand["generation"], jetzt=jetzt)
        return self.neu_lesen(akte)

    def zuweisen(self, akte, an, jetzt=None):
        """Vorschlag: neue Anfrage einem Mitarbeiter zuweisen (an leer = aufheben). Bei einer übernommenen Anfrage
        ist das ein Bearbeiterwechsel."""
        akte = self.neu_lesen(akte)
        if akte.status != NEU:
            return self.bearbeiter_aendern(akte, an, jetzt=jetzt)
        if (an or "") != akte.stand["zugewiesen"]:
            self.ereignis(akte, ZUGEWIESEN, alt=akte.stand["zugewiesen"], neu=an or "", jetzt=jetzt)
        return self.neu_lesen(akte)

    def bearbeiter_aendern(self, akte, an, jetzt=None):
        if not an:
            raise AblageFehler("Bitte einen Bearbeiter wählen.")
        if akte.status == NEU:
            raise AblageFehler("Die Anfrage ist noch nicht übernommen.")
        if an != akte.bearbeiter:
            self.ereignis(akte, BEARBEITER, alt=akte.bearbeiter, neu=an, jetzt=jetzt)
        return self.neu_lesen(akte)

    def prioritaet(self, akte, wert, jetzt=None):
        if wert not in PRIORITAETEN:
            raise AblageFehler(f"Unbekannte Priorität: {wert}")
        if wert != akte.prioritaet:
            self.ereignis(akte, PRIORITAET, alt=akte.prioritaet, neu=wert, jetzt=jetzt)
        return self.neu_lesen(akte)

    def notiz(self, akte, text, jetzt=None):
        text = str(text or "").strip()
        if text:
            self.ereignis(akte, NOTIZ, neu=text, jetzt=jetzt)
        return self.neu_lesen(akte)

    def bearbeitungsstand(self, akte, text, jetzt=None):
        text = " ".join(str(text or "").split())
        if text != akte.stand["stand"]:
            self.ereignis(akte, STAND, alt=akte.stand["stand"], neu=text, jetzt=jetzt)
        return self.neu_lesen(akte)

    def angebot_verknuepfen(self, akte, nummer, jetzt=None, **werte):
        if nummer and nummer not in akte.stand["angebote"]:
            self.ereignis(akte, ANGEBOT, neu=nummer, jetzt=jetzt, **werte)
        return self.neu_lesen(akte)

    def erledigen(self, akte, jetzt=None):
        akte = self.neu_lesen(akte)
        if akte.status != BEARBEITUNG:
            raise AblageFehler("Nur eine Anfrage in Bearbeitung lässt sich als erledigt markieren.")
        self.ereignis(akte, ERLEDIGT_A, jetzt=jetzt)
        return self.neu_lesen(akte)

    def wieder_oeffnen(self, akte, jetzt=None):
        akte = self.neu_lesen(akte)
        if akte.status != ERLEDIGT:
            raise AblageFehler("Die Anfrage ist nicht erledigt.")
        self.ereignis(akte, WIEDER, jetzt=jetzt)
        return self.neu_lesen(akte)

    def zurueckgeben(self, akte, jetzt=None):
        """Übernommene Anfrage zurück nach Neu (danach kann sie wieder jemand übernehmen)."""
        akte = self.neu_lesen(akte)
        if akte.status != BEARBEITUNG:
            raise AblageFehler("Nur eine Anfrage in Bearbeitung lässt sich zurückgeben.")
        self.ereignis(akte, ZURUECK, alt=akte.bearbeiter, jetzt=jetzt)
        return self.neu_lesen(akte)


# ------------------------------------------------------------------ Auswertung
def ist_meine(a, ich):
    return bool(ich) and ((a.status == BEARBEITUNG and a.bearbeiter == ich)
                          or (a.status == NEU and a.stand["zugewiesen"] == ich))


def zaehlen(akten, ich=""):
    """{neu, in_bearbeitung, erledigt, meine} für die Zählerleiste; meine = mir zugewiesen (neu) oder meine offenen."""
    z = {NEU: 0, BEARBEITUNG: 0, ERLEDIGT: 0, "meine": 0}
    for a in akten:
        z[a.status] += 1
        z["meine"] += ist_meine(a, ich)
    return z


def filtern(akten, ordner=None, ich="", text="", bearbeiter="", prioritaet="", seit=None):
    """Akten für die Liste: ordner = neu / in_bearbeitung / erledigt / meine / None (alle); text sucht (alle Worte) in
    Nummer, Absender, Betreff, Kurztext, Kunde, Dateinamen, Angebotsnummern; seit (datetime): nur Eingang ab dann.
    Sortiert: Erledigt neueste zuerst, sonst nach Priorität und ältestem Eingang."""
    worte = [w for w in str(text or "").lower().split() if w]
    out = []
    for a in akten:
        if ordner == "meine":
            if not ist_meine(a, ich):
                continue
        elif ordner and a.status != ordner:
            continue
        if bearbeiter and bearbeiter not in (a.bearbeiter, a.stand["zugewiesen"]):
            continue
        if prioritaet and a.prioritaet != prioritaet:
            continue
        if seit and (a.eingang or datetime.datetime.min) < seit:
            continue
        if worte:
            t = a.suchtext()
            if not all(w in t for w in worte):
                continue
        out.append(a)
    if ordner == ERLEDIGT:
        return sorted(out, key=lambda a: a.stand["erledigt_am"], reverse=True)
    rang = {p: i for i, p in enumerate(reversed(PRIORITAETEN))}
    return sorted(out, key=lambda a: (rang.get(a.prioritaet, 9), a.eingang or datetime.datetime.max))


def mitarbeiter(akten):
    """Übersicht je Mitarbeiter: {Kürzel: dict(offen, erledigt, zugewiesen, std_bis_uebernahme, std_bearbeitung)}
    (Mittelwerte in Stunden, None ohne Werte)."""
    m = {}

    def e(k):
        return m.setdefault(k, dict(offen=0, erledigt=0, zugewiesen=0, _ue=[], _be=[]))

    for a in akten:
        s = a.stand
        if a.status == NEU and s["zugewiesen"]:
            e(s["zugewiesen"])["zugewiesen"] += 1
        if not a.bearbeiter:
            continue
        x = e(a.bearbeiter)
        x["offen" if a.status == BEARBEITUNG else "erledigt"] += 1
        ue, ein, erl = _datum(s["uebernommen_am"]), a.eingang, _datum(s["erledigt_am"])
        if ue and ein:
            x["_ue"].append(max(0.0, (ue - ein).total_seconds() / 3600))
        if ue and erl:
            x["_be"].append(max(0.0, (erl - ue).total_seconds() / 3600))
    for x in m.values():
        ue, be = x.pop("_ue"), x.pop("_be")
        x["std_bis_uebernahme"] = sum(ue) / len(ue) if ue else None
        x["std_bearbeitung"] = sum(be) / len(be) if be else None
    return dict(sorted(m.items()))


def dauer_text(stunden):
    if stunden is None:
        return "–"
    if stunden < 1:
        return f"{round(stunden * 60)} min"
    if stunden < 48:
        return f"{stunden:.1f} h".replace(".", ",")
    return f"{stunden / 24:.1f} Tage".replace(".", ",")


def verlauf_text(e):
    """Eine Zeile des Verlaufs für die Anzeige."""
    a = e.get("aktion")
    t = AKTION_TEXT.get(a, a or "")
    alt, neu = e.get("alt"), e.get("neu")
    if a == PRIORITAET:
        t += f": {PRIORITAET_TEXT.get(alt, alt or '–')} → {PRIORITAET_TEXT.get(neu, neu)}"
    elif a == BEARBEITER:
        t += f": {alt or '–'} → {neu or '–'}"
    elif a == ZUGEWIESEN:
        t += f" an {neu}" if neu else " (aufgehoben)"
    elif a == UEBERNOMMEN:
        t += f" für {neu}" if neu and neu != e.get("kuerzel") else ""
    elif a in (NOTIZ, STAND, ANGEBOT):
        t += f": {neu}"
    elif a == DATEI_DAZU:
        t += ": " + ", ".join(d.get("name", "") for d in e.get("dateien", []))
    elif a == EINGEGANGEN and neu:
        t += f" ({'Outlook' if neu == 'outlook' else 'Anfrage-Ordner' if neu == 'ordner' else neu})"
    if e.get("ungueltig"):
        t += " (zu spät, zählt nicht)"
    return f"{_zeit_text(e.get('zeit'))}  {e.get('kuerzel', '')}  {t}"


# ------------------------------------------------------------------ Programm: wo liegen die Akten?
def wurzel(db):
    """Ordner der Akten: im gemeinsamen Ordner, sonst neben der Datendatei."""
    from . import teilen
    o = teilen.ordner(db) if teilen.aktiv(db) else None
    if o is not None:
        return Path(o) / ORDNER
    return Path(db.pfad).parent / ORDNER


def kuerzel(db):
    from . import teilen
    return teilen.kuerzel(db) or (db.einstellung("benutzer_kuerzel") or "").strip() or "ICH"


def ablage(db):
    return OrdnerAblage(wurzel(db), kuerzel(db), platz=socket.gethostname())


def aktiv(db):
    """Anfragenverwaltung an (Einstellung EINSTELLUNG, Vorgabe ja)."""
    return (db.einstellung(EINSTELLUNG) or "ja") != "nein"


# ------------------------------------------------------------------ Eingang aus dem Anfrage-Ordner
_SUMME = {}     # (Pfad, Größe, Änderungszeit) -> SHA-256


def _summe(p):
    try:
        st = Path(p).stat()
    except OSError:
        return None
    k = (str(p), st.st_size, st.st_mtime_ns)
    if k not in _SUMME:
        if len(_SUMME) > 2000:
            _SUMME.clear()
        try:
            _SUMME[k] = pruefsumme(p)
        except OSError:
            return None
    return _SUMME[k]


def leitdatei(anfrage):
    """Datei, die eine Anfrage aus dem Ordner wiedererkennt: älteste Mail, sonst erste STEP-Datei, sonst erste Datei."""
    from . import anfragen
    mails = sorted(anfrage.mails, key=anfragen.quell_zeit)
    if mails:
        return mails[0]
    return (anfrage.step or anfrage.dateien or [None])[0]


def kopf_aus_ordner(anfrage, kunden=()):
    """Kopf einer Akte aus einer Anfrage im Anfrage-Ordner (anfragen.Anfrage)."""
    from . import anfrage_vorab, anfragen, mail
    m = None
    for d in sorted(anfrage.mails, key=anfragen.quell_zeit):
        m = mail.lesen(d)
        if m is not None:
            break
    kunde = str(anfrage.kunde or "")
    k = dict(quelle="ordner", name=anfrage.name, kundennr=kunde,
             kunde_name=anfragen.kunde_text(kunden, kunde) if kunde else "")
    if m is not None:
        k.update(absender=m.absender, absender_name=m.absender_name, betreff=m.betreff or anfrage.name,
                 kurz=mail.neuester_teil(m.text))
    else:
        k.update(betreff=anfrage.name, kurz="")
    try:
        k["eingang"] = anfrage_vorab.eingang(anfrage)
    except Exception:
        k["eingang"] = anfrage.zeit
    return k


def aus_ordner(abl, liste, kunden=(), jetzt=None):
    """Anfragen aus dem Anfrage-Ordner als Akten erfassen (einmal je Leitdatei); spätere Dateien einer schon erfassten,
    noch neuen Anfrage kommen dazu. Ergebnis: {Anfrage.schluessel: Akte}."""
    out = {}
    for a in liste:
        ld = leitdatei(a)
        h = _summe(ld) if ld else None
        if not h:
            continue
        nr = abl.schluessel_akte(h)
        akte = abl.lesen(nr) if nr else None
        # Ohne Mail (nur Dateien): dieselbe Datei nach Übernahme wieder im Ordner = neue Anfrage (z. B. Wiederholung
        # mit gleicher STEP), denn die Originale einer übernommenen Akte liegen nicht mehr im Eingang
        while akte is not None and akte.status != NEU and not a.mails:
            h = f"{h[:40]}-{akte.nr}"
            nr = abl.schluessel_akte(h)
            akte = abl.lesen(nr) if nr else None
        try:
            if akte is None:
                akte, _neu = abl.anlegen(kopf_aus_ordner(a, kunden), a.dateien, h, jetzt=jetzt)
            elif akte.status == NEU:
                bekannt = {d.get("sha256") for d in akte.dateien()}
                dazu = [d for d in a.dateien if _summe(d) not in bekannt]
                if dazu:
                    abl.dateien_dazu(akte, dazu, jetzt=jetzt)
                    akte = abl.neu_lesen(akte)
        except OSError:
            continue
        if akte is not None:
            out[a.schluessel] = akte
    return out


def akte_zu(abl, anfrage):
    """Akte zu einer Anfrage aus dem Ordner oder None."""
    ld = leitdatei(anfrage)
    h = _summe(ld) if ld else None
    nr = abl.schluessel_akte(h) if h else None
    return abl.lesen(nr) if nr else None


def arbeitskopie(akte, jetzt=None):
    """Dateien der Akte in einen neuen Arbeitsordner der Akte kopieren (für „Kalkulieren“: das Programm packt dort aus
    und verschiebt danach in den Angebotsordner, die Akte selbst bleibt vollständig). Gefährliche Dateien bleiben
    draußen. Ergebnis: anfragen.Anfrage über dem Arbeitsordner."""
    from . import anfragen
    jetzt = jetzt or datetime.datetime.now()
    o = _frei(akte.pfad / f"_arbeit_{jetzt.strftime('%Y%m%d_%H%M%S')}")
    o.mkdir(parents=True)
    neu = []
    for d in akte.dateien():
        if d.get("aus_mail") or Path(d["name"]).suffix.lower() in GEFAEHRLICH or not d["pfad"].exists():
            continue        # Anhänge packt das Programm aus der Mail selbst aus
        z = _frei(o / d["name"])
        shutil.copy2(d["pfad"], z)
        neu.append(z)
    return anfragen.Anfrage(akte.betreff, o, neu, akte.kunde or None)


def eingang_ablegen(anfrage, inbox, nr):
    """Nach dem Übernehmen auf der Seite Anfragen: die Originale im Anfrage-Ordner (Kopie liegt in der Akte) in den
    versteckten Unterordner .uebernommen/<nr> legen, damit die Karte „Neue Anfragen“ sie nicht mehr zeigt. Nichts wird
    gelöscht. Ergebnis: Anzahl verschobener Dateien."""
    ziel = Path(inbox) / ".uebernommen" / nr
    ziel.mkdir(parents=True, exist_ok=True)
    n = 0
    for d in anfrage.dateien:
        try:
            shutil.move(str(d), str(_frei(ziel / Path(d).name)))
            n += 1
        except OSError:
            continue
    o = anfrage.ordner
    if o and Path(o).is_dir() and Path(o) != Path(inbox):
        try:
            rest = [p for p in Path(o).rglob("*") if p.is_file() and not p.name.startswith(".")]
            if not rest:
                shutil.rmtree(o)
        except OSError:
            pass
    return n
