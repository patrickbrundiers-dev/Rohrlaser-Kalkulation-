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
VIREN = "virenpruefung"     # Paket 3: Ergebnis des Windows-Virenschutzes je Datei
# Paket 5 (Freigabe 13.11.2026 „Alle fünf“)
AUSSORTIERT = "aussortiert"         # keine Anfrage (Werbung, Rechnung …): nach Erledigt, mit Grund, nie gelöscht
VORMESSUNG = "vormessung"           # Ergebnis der Vormessung (Teile, Profile, Richtpreis), einmal für alle Plätze
VERSENDET = "angebot_versendet"     # Angebot per E-Mail an den Kunden (als Antwort auf die Anfrage-Mail)
AKTION_TEXT = {EINGEGANGEN: "Eingegangen", DATEI_DAZU: "Datei dazu", ZUGEWIESEN: "Zugewiesen",
               UEBERNOMMEN: "Übernommen", BEARBEITER: "Bearbeiter geändert", PRIORITAET: "Priorität",
               NOTIZ: "Notiz", STAND: "Bearbeitungsstand", ANGEBOT: "Angebot verknüpft",
               ERLEDIGT_A: "Als erledigt markiert", WIEDER: "Wieder geöffnet", ZURUECK: "Zurückgegeben",
               VIREN: "Virenprüfung", AUSSORTIERT: "Keine Anfrage", VORMESSUNG: "Vormessung",
               VERSENDET: "Angebot per E-Mail"}
AUSSORTIER_GRUENDE = ("Werbung", "Rechnung", "Lieferant / Einkauf", "Bewerbung", "Sonstiges")
AUSSORTIER_VORSCHLAG = 2    # so oft vom selben Absender aussortiert: beim nächsten Mal „Keine Anfrage?“ vorschlagen
AUTO = "Automatik"          # Kürzel-Zusatz im Verlauf für automatische Zuweisungen

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


def pruefsumme_text(text):
    """Kurze Kennung eines Textes (Dateistand der Vormessung)."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16]


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
             dazu=[], letzte="", viren={}, mids=[], antworten=0, aussortiert="", vormessung="",
             vormessung_stempel="", versendet=[])
    for e in sorted(ereignisse, key=lambda e: (e.get("zeit", ""), e.get("kuerzel", ""), e.get("nr", 0))):
        a, k, z = e.get("aktion"), e.get("kuerzel", ""), e.get("zeit", "")
        e["ungueltig"] = False
        if a == EINGEGANGEN:
            s["eingang"] = s["eingang"] or z
        elif a == DATEI_DAZU:
            namen = {d.get("name") for d in s["dazu"]}
            s["dazu"] += [d for d in e.get("dateien", []) if d.get("name") not in namen]
            if e.get("nachrichten_id") and e["nachrichten_id"] not in s["mids"]:
                s["mids"].append(e["nachrichten_id"])
            s["antworten"] += bool(e.get("antwort"))
        elif a == VIREN:
            s["viren"].update(e.get("dateien") or {})
        elif a == VORMESSUNG:
            s["vormessung"], s["vormessung_stempel"] = e.get("neu", ""), e.get("stempel", "")
        elif a == VERSENDET:
            s["versendet"].append(dict(zeit=z, kuerzel=k, angebot=e.get("neu", ""), an=e.get("an", "")))
        elif a == AUSSORTIERT:
            if s["status"] == ERLEDIGT:
                e["ungueltig"] = True
                continue
            s.update(status=ERLEDIGT, erledigt_am=z, erledigt_von=k, aussortiert=e.get("neu") or "Sonstiges",
                     zugewiesen="")
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
            s.update(status=BEARBEITUNG if s["bearbeiter"] else NEU, erledigt_am="", erledigt_von="",
                     aussortiert="")
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
            e["viren"] = self.stand.get("viren", {}).get(e.get("datei", name))
            if e["viren"] == "fund":
                e.update(gesperrt=True, warnung="Virus gefunden: gesperrt")
            out.append(e)
        return out

    def ungeprueft(self):
        """Dateien ohne Ergebnis des Virenschutzes (vorhanden, nicht gesperrt)."""
        return [d for d in self.dateien() if not d.get("gesperrt") and d["viren"] is None and d["pfad"].is_file()]

    def virus(self):
        return any(d["viren"] == "fund" for d in self.dateien())

    @property
    def status(self):
        return self.stand["status"]

    @property
    def bearbeiter(self):
        return self.stand["bearbeiter"]

    @property
    def prioritaet(self):
        return self.stand["prioritaet"]

    @property
    def aussortiert(self):
        return self.stand.get("aussortiert", "")

    @property
    def adresse(self):
        return str(self.kopf.get("absender") or "").strip().lower()

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

    def dateien_dazu(self, akte, pfade, jetzt=None, **weitere):
        """Später gekommene Dateien (Nachtrag) in die Akte kopieren, gleiche Inhalte nur einmal. weitere: zusätzliche
        Felder im Ereignis (antwort=True bei einer Antwort des Kunden, nachrichten_id aus Outlook). Ergebnis: neue
        Namen."""
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
            self.ereignis(akte, DATEI_DAZU, dateien=neu, jetzt=jetzt, **weitere)
        return [d["name"] for d in neu]

    def schluessel_setzen(self, schluessel, nr):
        """Doppel-Schlüssel auf eine vorhandene Akte zeigen lassen (Antwort des Kunden: dieselbe Mail nie zweimal)."""
        sd = self.wurzel / SCHLUESSEL
        sd.mkdir(parents=True, exist_ok=True)
        return _exklusiv(sd / f"{_sauber(schluessel)[:120]}.akte", nr)

    def viren_pruefen(self, akte, exe=None, ausfuehren=None, jetzt=None):
        """Ungeprüfte Dateien der Akte mit dem Windows-Virenschutz prüfen; ein Fund wird gesperrt (Datei bekommt die
        Endung .gesperrt, nichts wird gelöscht). Ohne Virenschutz: nichts (bleibt „nicht geprüft“). Ergebnis:
        {Name: Ergebnis} der geprüften Dateien."""
        from . import virenpruefung as vp
        akte = self.neu_lesen(akte)
        offen = akte.ungeprueft()
        if not offen or (exe is None and ausfuehren is None and vp.programm() is None):
            return {}
        erg = vp.pruefen([d["pfad"] for d in offen], exe=exe or vp.programm(), ausfuehren=ausfuehren)
        werte = {}
        for d in offen:
            r = erg.get(d["pfad"], vp.UNGEPRUEFT)
            if r == vp.UNGEPRUEFT:
                continue
            werte[d.get("datei", d["name"])] = r
            if r == vp.FUND:
                try:
                    d["pfad"].replace(d["pfad"].with_name(d["pfad"].name + ".gesperrt"))
                except OSError:
                    pass                # der Virenschutz hat sie schon weggenommen
        if werte:
            self.ereignis(akte, VIREN, dateien=werte, jetzt=jetzt)
        return werte

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

    # ---------------------------------------------- Paket 5
    def aussortieren(self, akte, grund, jetzt=None):
        """Keine Anfrage (Werbung, Rechnung …): die Akte kommt mit Grund nach Erledigt (Filter „Keine Anfrage“), in
        Outlook nach „Erledigt“. Nichts wird gelöscht; „Wieder öffnen“ holt sie zurück."""
        akte = self.neu_lesen(akte)
        if akte.status == ERLEDIGT:
            raise AblageFehler("Die Anfrage ist schon erledigt.")
        self.ereignis(akte, AUSSORTIERT, neu=" ".join(str(grund or "").split()) or "Sonstiges", jetzt=jetzt)
        return self.neu_lesen(akte)

    def vormessung_merken(self, akte, text, stempel, jetzt=None):
        """Ergebnis der Vormessung in den Verlauf (einmal je Dateistand, alle Plätze sehen es)."""
        akte = self.neu_lesen(akte)
        if (akte.stand["vormessung"], akte.stand["vormessung_stempel"]) != (text, stempel):
            self.ereignis(akte, VORMESSUNG, neu=text, stempel=stempel, jetzt=jetzt)
        return self.neu_lesen(akte)

    def vormessung_nehmen(self, akte, stempel, frei_nach_min=30):
        """Nur ein Platz misst eine Akte: Sperrdatei je Dateistand (nach frei_nach_min Minuten verfällt sie, falls der
        messende Platz abgestürzt ist). Ergebnis: True = dieser Platz misst."""
        sp = akte.pfad / f"vormessung_{_sauber(stempel)[:40]}.sperre"
        if _exklusiv(sp, f"{self.kuerzel}|{self.platz}"):
            return True
        try:
            alt = time.time() - sp.stat().st_mtime > frei_nach_min * 60
        except OSError:
            return False
        if alt:
            sp.unlink(missing_ok=True)
            return _exklusiv(sp, f"{self.kuerzel}|{self.platz}")
        return False

    def angebot_versendet(self, akte, nummer, an="", erledigen=True, jetzt=None):
        """Angebot per E-Mail an den Kunden: im Verlauf vermerken und (erledigen) die Anfrage nach Erledigt legen;
        eine neue Anfrage wird dafür zuerst übernommen."""
        akte = self.neu_lesen(akte)
        if nummer and nummer not in akte.stand["angebote"]:
            akte = self.angebot_verknuepfen(akte, nummer, jetzt=jetzt)
        self.ereignis(akte, VERSENDET, neu=nummer or "", an=an or "", jetzt=jetzt)
        akte = self.neu_lesen(akte)
        if erledigen and akte.status == NEU:
            try:
                akte = self.uebernehmen(akte, jetzt=jetzt)
            except SchonUebernommen:
                akte = self.neu_lesen(akte)
        if erledigen and akte.status == BEARBEITUNG:
            akte = self.erledigen(akte, jetzt=jetzt)
        return akte

    def zustaendig_zuweisen(self, akten, kunden, jetzt=None):
        """Fester Bearbeiter je Kunde (Kundenstamm „Zuständig“): neue Anfragen dieses Kunden, die noch nie zugewiesen
        wurden, ihm zuweisen. Eine Sperrdatei je Akte sorgt dafür, dass nur ein Platz das tut; von Hand aufgehoben
        bleibt aufgehoben. Ergebnis: [(Nummer, Kürzel)]."""
        zust = {str(k.get("kundennr")): str(k.get("zustaendig") or "").strip().upper() for k in kunden or ()}
        out = []
        for a in akten:
            an = zust.get(a.kunde) if a.kunde else ""
            if not an or a.status != NEU or any(e.get("aktion") in (ZUGEWIESEN, UEBERNOMMEN) for e in a.verlauf):
                continue
            if not _exklusiv(a.pfad / "zuweisung_auto.sperre", an):
                continue
            self.ereignis(a, ZUGEWIESEN, alt="", neu=an, automatisch=True, jetzt=jetzt)
            out.append((a.nr, an))
        return out


# ------------------------------------------------------------------ Auswertung
def ist_meine(a, ich):
    return bool(ich) and ((a.status == BEARBEITUNG and a.bearbeiter == ich)
                          or (a.status == NEU and a.stand["zugewiesen"] == ich))


def zaehlen(akten, ich=""):
    """{neu, in_bearbeitung, erledigt, meine} für die Zählerleiste; meine = mir zugewiesen (neu) oder meine offenen."""
    z = {NEU: 0, BEARBEITUNG: 0, ERLEDIGT: 0, "meine": 0, AUSSORTIERT: 0}
    for a in akten:
        z[AUSSORTIERT if a.aussortiert else a.status] += 1
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
        elif ordner == AUSSORTIERT:
            if not a.aussortiert:
                continue
        elif ordner and (a.status != ordner or a.aussortiert):
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
    if ordner in (ERLEDIGT, AUSSORTIERT):
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


def aussortier_vorschlag(akten, akte):
    """Wie oft Anfragen vom selben Absender (Adresse) schon als „Keine Anfrage“ aussortiert wurden, wenn das
    mindestens AUSSORTIER_VORSCHLAG Mal war und akte noch neu ist; sonst 0. Ergebnis: (Anzahl, häufigster Grund)."""
    adr = akte.adresse
    if not adr or akte.status != NEU:
        return 0, ""
    gruende = [a.aussortiert for a in akten if a.nr != akte.nr and a.aussortiert and a.adresse == adr]
    if len(gruende) < AUSSORTIER_VORSCHLAG:
        return 0, ""
    return len(gruende), max(set(gruende), key=gruende.count)


def ampel(akte, tage, jetzt=None, land=None):
    """Anfrage-Ampel wie auf der Startseite (anfrage_vorab.ampel): Frist in Arbeitstagen ab Eingang, für neue und
    übernommene Anfragen, bis ein Angebot verschickt ist. Ohne Frist (0): rot nach ERINNERN_STUNDEN wie bisher.
    Ergebnis: (Stufe 'grün'/'gelb'/'rot' oder None, fällig am, Text)."""
    from . import anfrage_vorab as av
    if akte.status == ERLEDIGT or akte.stand.get("versendet"):
        return None, None, ""
    if not tage:
        return (av.ROT, None, f"wartet seit über {ERINNERN_STUNDEN} Std.") if akte.wartet(jetzt) else (None, None, "")
    return av.ampel(akte.eingang, tage, jetzt=jetzt, land=land)


def _woche(d):
    j, w, _ = d.isocalendar()
    return f"{j}-W{w:02d}"


def auswertung(akten, vorgaenge=None, jetzt=None, wochen=12):
    """Auswertung der Anfragen (Paket 5): wochen = [(Woche 'JJJJ-Www', Eingänge, davon Angebot, davon keine Anfrage)]
    der letzten wochen Wochen; std_bis_angebot = mittlere Zeit vom Eingang bis zum ersten Angebot (Stunden);
    mitarbeiter = {Kürzel: dict(…, std_bis_angebot, angebote, beauftragt)}; treffer = (Anfragen mit Angebot,
    davon beauftragt) über vorgaenge {Angebotsnummer: Vorgang} (Vorgang 'Beauftragt')."""
    jetzt = jetzt or datetime.datetime.now()
    vorgaenge = vorgaenge or {}
    start = (jetzt - datetime.timedelta(weeks=wochen - 1)).date()
    start -= datetime.timedelta(days=start.weekday())
    w = {}
    d = start
    while d <= jetzt.date():
        w[_woche(d)] = [0, 0, 0]
        d += datetime.timedelta(days=7)
    ma = mitarbeiter(akten)
    alle_std, mit_angebot, beauftragt = [], 0, 0
    je = {}
    for a in akten:
        ein = a.eingang
        erstes = min((_datum(e.get("zeit")) for e in a.verlauf if e.get("aktion") == ANGEBOT and _datum(e.get("zeit"))),
                     default=None)
        ang = bool(a.stand["angebote"])
        auftrag = any(vorgaenge.get(n) == "Beauftragt" for n in a.stand["angebote"])
        if ein and ein.date() >= start:
            x = w.setdefault(_woche(ein.date()), [0, 0, 0])
            x[0] += 1
            x[1] += ang
            x[2] += bool(a.aussortiert)
        if ang:
            mit_angebot += 1
            beauftragt += auftrag
        k = a.bearbeiter
        if k:
            y = je.setdefault(k, dict(_st=[], angebote=0, beauftragt=0))
            y["angebote"] += ang
            y["beauftragt"] += auftrag
        if ein and erstes:
            std = max(0.0, (erstes - ein).total_seconds() / 3600)
            alle_std.append(std)
            if k:
                je[k]["_st"].append(std)
    for k, y in je.items():
        st = y.pop("_st")
        x = ma.setdefault(k, dict(offen=0, erledigt=0, zugewiesen=0, std_bis_uebernahme=None, std_bearbeitung=None))
        x.update(y, std_bis_angebot=sum(st) / len(st) if st else None)
    for x in ma.values():
        x.setdefault("angebote", 0)
        x.setdefault("beauftragt", 0)
        x.setdefault("std_bis_angebot", None)
    return dict(wochen=sorted((k, *v) for k, v in w.items()), std_bis_angebot=sum(alle_std) / len(alle_std)
                if alle_std else None, mitarbeiter=dict(sorted(ma.items())), treffer=(mit_angebot, beauftragt),
                aussortiert=sum(1 for a in akten if a.aussortiert))


def quote_text(n, von):
    return f"{round(100 * n / von)} %" if von else "–"


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
        t += (f" an {neu}" if neu else " (aufgehoben)") + (" (zuständig für den Kunden)" if e.get("automatisch") else "")
    elif a == UEBERNOMMEN:
        t += f" für {neu}" if neu and neu != e.get("kuerzel") else ""
    elif a in (NOTIZ, STAND, ANGEBOT, AUSSORTIERT, VORMESSUNG):
        t += f": {neu}" if neu else ""
    elif a == VERSENDET:
        t += f": {neu}" + (f" an {e['an']}" if e.get("an") else "")
    elif a == DATEI_DAZU:
        t = ("Antwort des Kunden" if e.get("antwort") else t) + ": " + ", ".join(
            d.get("name", "") for d in e.get("dateien", []))
    elif a == VIREN:
        fund = [n for n, r in (e.get("dateien") or {}).items() if r == "fund"]
        t += f": Virus in {', '.join(fund)}, gesperrt" if fund else f": {len(e.get('dateien') or {})} Datei(en) sauber"
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


# ------------------------------------------------------------------ Angebot per E-Mail (Paket 5)
def akten_zum_angebot(db, angebot_id):
    """Nummern der Anfragen, aus denen das Angebot entstand (Zusatz anfrage_akte)."""
    try:
        w = db.zusatz(angebot_id, "anfrage_akte")
    except Exception:       # noqa: BLE001
        return []
    return [w] if isinstance(w, str) and w else [x for x in (w or []) if isinstance(x, str) and x]


def anfrage_mail(db, angebot_id):
    """Original-Mail der verknüpften Anfrage (.msg vor .eml) oder None – Ersatz, wenn im Angebotsordner keine liegt."""
    if not aktiv(db):
        return None
    abl = ablage(db)
    for nr in akten_zum_angebot(db, angebot_id):
        try:
            akte = abl.lesen(nr)
        except OSError:
            continue
        if akte is None:
            continue
        mails = [d["pfad"] for d in akte.dateien() if d["art"] == "mail" and not d.get("aus_mail")
                 and not d.get("gesperrt") and d["pfad"].is_file()]
        mails.sort(key=lambda p: p.suffix.lower() != ".msg")
        if mails:
            return mails[0]
    return None


def angebot_gemailt(db, angebot_id, nummer, an=""):
    """Nach „Angebot per E-Mail“: verknüpfte Anfragen vermerken und nach Erledigt legen (in Outlook zieht die Mail
    beim nächsten Abruf mit). Ergebnis: [Nummer der Anfrage]."""
    if getattr(db, "nur_lesen", False) or not aktiv(db):
        return []
    abl = ablage(db)
    out = []
    for nr in akten_zum_angebot(db, angebot_id):
        try:
            akte = abl.lesen(nr)
            if akte is None:
                continue
            abl.angebot_versendet(akte, nummer, an)
            out.append(nr)
        except (OSError, AblageFehler):
            continue
    return out


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


# ------------------------------------------------------------------ Antworten des Kunden (Paket 3)
ANTWORT = re.compile(r"^\s*(AW|RE|Antw|Antwort|R|SV)\s*(\[\d+\])?\s*:", re.I)
VORSILBEN = re.compile(r"^\s*((AW|RE|WG|FW|FWD|Antw|Antwort|R|SV|VS)\s*(\[\d+\])?\s*:\s*)+", re.I)
ANTWORT_TAGE = 120          # so lange nach dem Eingang zählt eine Antwort noch zur Anfrage


def betreff_kern(betreff):
    """Betreff ohne AW:/RE:/WG: …, klein, Leerraum vereinheitlicht."""
    return " ".join(VORSILBEN.sub("", str(betreff or "")).lower().split())


def _domain(adresse):
    a = str(adresse or "").strip().lower()
    return a.rpartition("@")[2] if "@" in a else ""


def antwort_zu(akten, betreff, absender, konversation="", jetzt=None):
    """Akte, zu der eine Mail als Antwort des Kunden gehört, oder None: gleiche Outlook-Konversation, sonst ein
    Antwort-Betreff (AW:, RE: …) mit gleichem Kern-Betreff vom selben Absender bzw. derselben Firma (Domain), jüngstens
    ANTWORT_TAGE nach dem Eingang. Mehrere Treffer: die jüngste Anfrage."""
    jetzt = jetzt or datetime.datetime.now()
    passt = []
    if konversation:
        passt = [a for a in akten if a.kopf.get("konversation") == konversation]
    if not passt and ANTWORT.match(str(betreff or "")):
        kern, dom = betreff_kern(betreff), _domain(absender)
        if len(kern) >= 4 and dom:
            passt = [a for a in akten if betreff_kern(a.betreff) == kern and _domain(a.kopf.get("absender")) == dom
                     and (not a.eingang or jetzt - a.eingang < datetime.timedelta(days=ANTWORT_TAGE))]
    return max(passt, key=lambda a: (a.eingang or datetime.datetime.min, a.nr), default=None)


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


def aus_ordner(abl, liste, kunden=(), jetzt=None, inbox=None):
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
            if akte is None and a.mails:
                akte = _als_antwort(abl, a, h, kunden, jetzt, inbox)
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


def _als_antwort(abl, anfrage, h, kunden, jetzt, inbox):
    """Anfrage aus dem Ordner, die eine Antwort des Kunden auf eine vorhandene Anfrage ist: Dateien dazu, Schlüssel
    auf diese Akte; die Originale kommen gleich nach .uebernommen/<Nr> (die Karte zeigt die Antwort nicht als eigene
    Anfrage). Ergebnis: Akte oder None."""
    k = kopf_aus_ordner(anfrage, kunden)
    ziel = antwort_zu(abl.alle(), k.get("betreff"), k.get("absender"), jetzt=jetzt)
    if ziel is None:
        return None
    abl.dateien_dazu(ziel, anfrage.dateien, jetzt=jetzt, antwort=True)
    abl.schluessel_setzen(h, ziel.nr)
    ziel = abl.neu_lesen(ziel)
    if inbox:
        eingang_ablegen(anfrage, inbox, ziel.nr)
    return ziel


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
    if akte.virus():
        raise AblageFehler("Der Virenschutz hat in dieser Anfrage einen Virus gefunden; bitte erst klären, dann die "
                           "Dateien von Hand prüfen.")
    jetzt = jetzt or datetime.datetime.now()
    o = _frei(akte.pfad / f"_arbeit_{jetzt.strftime('%Y%m%d_%H%M%S')}")
    o.mkdir(parents=True)
    neu = []
    for d in akte.dateien():
        if d.get("aus_mail") or d.get("gesperrt") or Path(d["name"]).suffix.lower() in GEFAEHRLICH \
                or not d["pfad"].exists():
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
