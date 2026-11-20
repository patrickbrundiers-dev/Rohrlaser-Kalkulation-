"""Produktionsdaten aus TRUMPF-LST sammeln (Lernsystem L1, Plan „Selbstlernende Kalkulation aus LST-Daten“,
Patrick 20.11.2026; Plan https://claude.ai/artifact/JBguAxDHTWJCPZEe7aNGQu). Ohne Qt.

ordner_einlesen() liest alle LST-Dateien eines Ordners (Einstellung lst_ordner, mit Unterordnern). Jede Datei zählt
einmal: erkannt an der Prüfsumme des Inhalts, eine umbenannte oder kopierte Datei kommt nicht doppelt. Wird eine LST
nach dem Lauf an der Maschine neu gespeichert (dann mit gemessenen Zeiten), ist der Inhalt anders: ihre Teile
ersetzen die der älteren Fassung desselben Programms (Schlüssel Programm + Teil), damit jedes Teil nur einmal zählt.

Je Teil: Programm, Fertigungsauftrag, PPEASE-Angebotsnummer (aus Jobname, Auftrag oder Dateiname, z. B.
2026-44094_1.lst), Maschine, Werkstoff, Profil, Länge, Stückzahl, Schneidweg, Einstiche, Zeitanteile berechnet und
gemessen (Anschnitt, Konturen, Abschnitt), Strahl-Ein, Maschinenzeit und die Datenqualität (trumpf_programm.qualitaet).
Gelernt wird erst in L4 und nur aus vollständigen Teilen; hier wird nichts an der Kalkulation geändert. Die Einstichzeit
bleibt ein eigener Posten (die LST weist sie nicht getrennt aus)."""
import datetime
import hashlib
import json
import re
from pathlib import Path

from . import trumpf_programm as tp

TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS lst_dateien (id INTEGER PRIMARY KEY, pruefsumme TEXT UNIQUE, name TEXT, pfad TEXT, "
    "groesse INTEGER, gelesen TEXT, teile INTEGER, fehler TEXT)",
    "CREATE TABLE IF NOT EXISTS lst_teile (id INTEGER PRIMARY KEY, programm TEXT, teil_nr INTEGER, datei TEXT, "
    "pruefsumme TEXT, gelesen TEXT, ppease TEXT, auftrag TEXT, artikel TEXT, maschine TEXT, datum TEXT, "
    "werkstoff TEXT, profilform TEXT, a REAL, b REAL, wand REAL, radius REAL, laenge REAL, stueck INTEGER, "
    "schneidweg REAL, einstiche INTEGER, zeiten_berechnet TEXT, zeiten_gemessen TEXT, messungen INTEGER, "
    "maschinenzeit_s REAL, strahl_s REAL, qualitaet TEXT, gruende TEXT, UNIQUE (programm, teil_nr))",
)
SPALTEN = ("programm", "teil_nr", "datei", "pruefsumme", "gelesen", "ppease", "auftrag", "artikel", "maschine", "datum",
           "werkstoff", "profilform", "a", "b", "wand", "radius", "laenge", "stueck", "schneidweg", "einstiche",
           "zeiten_berechnet", "zeiten_gemessen", "messungen", "maschinenzeit_s", "strahl_s", "qualitaet", "gruende")
_JSON = ("zeiten_berechnet", "zeiten_gemessen", "gruende")
PPEASE = re.compile(r"(?<!\d)(20\d\d-\d{5})(?!\d)")       # PPEASE-Angebotsnummer wie 2026-44094


def einrichten(con):
    from . import db_verbindung
    for sql in TABELLEN_SQL:
        con.execute(sql)
    if "mtime" not in set(db_verbindung.spalten(con, "lst_dateien")):     # L6: unveränderte Dateien nicht neu lesen
        con.execute("ALTER TABLE lst_dateien ADD COLUMN mtime REAL")


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def ppease(*texte):
    """Erste PPEASE-Angebotsnummer in den Texten (Jobname, Auftrag, Dateiname) oder ''."""
    for t in texte:
        m = PPEASE.search(str(t or ""))
        if m:
            return m.group(1)
    return ""


def pruefsumme(roh):
    return hashlib.sha1(roh).hexdigest()


def dateien_im_ordner(ordner):
    """Alle .lst-Dateien im Ordner und seinen Unterordnern, sortiert."""
    o = Path(str(ordner or ""))
    if not str(ordner or "").strip() or not o.is_dir():
        return []
    return sorted(p for p in o.rglob("*") if p.is_file() and p.suffix.lower() == ".lst")


def _zeile(t, datei, summe, jetzt):
    stufe, gruende = tp.qualitaet(t)
    z = dict(t, datei=datei, pruefsumme=summe, gelesen=jetzt, qualitaet=stufe, gruende=gruende,
             ppease=ppease(t.get("auftrag"), t.get("artikel"), datei, t.get("programm")))
    return [json.dumps(z.get(s), ensure_ascii=False) if s in _JSON else z.get(s) for s in SPALTEN]


def bekannt(db):
    """(Prüfsummen, {Pfad: (Größe, Änderungszeit)}) der schon gelesenen Dateien."""
    summen, dateien = set(), {}
    for summe, pfad, groesse, mtime in db.con.execute("SELECT pruefsumme, pfad, groesse, mtime FROM lst_dateien"):
        summen.add(summe)
        if pfad and mtime is not None:
            dateien[pfad] = (groesse, mtime)
    return summen, dateien


def vorbereiten(pfade, summen=(), dateien=None, abbrechen=None):
    """Dateien lesen und auswerten, ohne Datenbank (L6: läuft im Hintergrund). Unveränderte Dateien (gleicher Pfad,
    gleiche Größe und Änderungszeit) werden gar nicht geöffnet. Ergebnis: [dict(pfad, name, summe, groesse, mtime,
    teile, fehler, bekannt)]."""
    summen, dateien = set(summen), dateien or {}
    out = []
    for pfad in pfade:
        if abbrechen is not None and abbrechen():
            break
        p = Path(pfad)
        e = dict(pfad=str(p), name=p.name, summe=None, groesse=None, mtime=None, teile=[], fehler="", bekannt=False)
        out.append(e)
        try:
            st = p.stat()
            e["groesse"], e["mtime"] = st.st_size, round(st.st_mtime, 3)
            if dateien.get(str(p)) == (e["groesse"], e["mtime"]):
                e["bekannt"] = True
                continue
            roh = p.read_bytes()
        except OSError as ex:
            e["fehler"] = f"{p.name}: {ex}"
            e["lesefehler"] = True
            continue
        e["summe"] = pruefsumme(roh)
        if e["summe"] in summen:
            e["bekannt"] = True
            continue
        summen.add(e["summe"])
        try:
            e["teile"] = tp.lst_lesen(text=_text(roh), name=p.name)
        except tp.TrumpfFehler as ex:
            e["fehler"] = str(ex)
    return out


def schreiben(db, eintraege):
    """Vorbereitete Dateien speichern. Ergebnis dict(neu, bekannt, teile, fehler [Text])."""
    jetzt = _jetzt()
    erg = dict(neu=0, bekannt=0, teile=0, fehler=[])
    schon = bekannt(db)[0]
    platz = ", ".join("?" * len(SPALTEN))
    with db.con:
        for e in eintraege:
            if e.get("lesefehler"):
                erg["fehler"].append(e["fehler"])
                continue
            if e["bekannt"] or e["summe"] in schon:
                erg["bekannt"] += 1
                if e["summe"] in schon and e.get("mtime") is not None:     # umbenannt/kopiert: künftig nicht öffnen
                    db.con.execute("UPDATE lst_dateien SET mtime=? WHERE pruefsumme=? AND pfad=?",
                                   (e["mtime"], e["summe"], e["pfad"]))
                continue
            if e["fehler"]:
                erg["fehler"].append(e["fehler"])
            for t in e["teile"]:    # neuere Fassung desselben Programms ersetzt die ältere (je Teil einmal)
                db.con.execute("DELETE FROM lst_teile WHERE programm=? AND teil_nr=?", (t["programm"], t["teil_nr"]))
                db.con.execute(f"INSERT INTO lst_teile ({', '.join(SPALTEN)}) VALUES ({platz})",
                               _zeile(t, e["name"], e["summe"], jetzt))
            db.con.execute("INSERT INTO lst_dateien (pruefsumme, name, pfad, groesse, gelesen, teile, fehler, mtime) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (e["summe"], e["name"], e["pfad"], e["groesse"], jetzt,
                                                             len(e["teile"]), e["fehler"], e["mtime"]))
            schon.add(e["summe"])
            erg["neu"] += 1
            erg["teile"] += len(e["teile"])
    return erg


def einlesen(db, pfade):
    """LST-Dateien einlesen. Ergebnis dict(neu, bekannt, teile, fehler [Text]); bekannte Dateien (gleiche Prüfsumme)
    werden übersprungen."""
    return schreiben(db, vorbereiten(pfade, *bekannt(db)))


def _text(roh):
    try:
        return roh.decode("utf-8")
    except UnicodeDecodeError:
        return roh.decode("cp1252", errors="replace")


def ordner_einlesen(db, ordner=None):
    """Den LST-Ordner (Einstellung lst_ordner) einlesen; ohne Ordner: dict mit fehler."""
    ordner = ordner if ordner is not None else db.einstellung("lst_ordner")
    if not str(ordner or "").strip():
        return dict(neu=0, bekannt=0, teile=0, fehler=["Kein LST-Ordner eingestellt (Einstellungen, STEP-Import)."])
    if not Path(str(ordner)).is_dir():
        return dict(neu=0, bekannt=0, teile=0, fehler=[f"LST-Ordner nicht erreichbar: {ordner}"])
    return einlesen(db, dateien_im_ordner(ordner))


def teile(db, nur_voll=False):
    """Gespeicherte Teile (dicts, JSON-Felder gelesen), neueste zuerst."""
    sql = f"SELECT id, {', '.join(SPALTEN)} FROM lst_teile"
    werte = ()
    if nur_voll:
        sql += " WHERE qualitaet=?"
        werte = (tp.VOLL,)
    out = []
    for r in db.con.execute(sql + " ORDER BY gelesen DESC, programm, teil_nr", werte):
        z = dict(zip(("id",) + SPALTEN, r))
        for s in _JSON:
            try:
                z[s] = json.loads(z[s]) if z[s] else None
            except ValueError:
                z[s] = None
        out.append(z)
    return out


def zeit_s(teil, gemessen=True):
    """Laserzeit je Teil [s] = Anschnitt + Konturen + Abschnitt; gemessen, wenn vorhanden (sonst berechnet)."""
    z = (teil.get("zeiten_gemessen") if gemessen else None) or teil.get("zeiten_berechnet") or {}
    s = sum(v or 0.0 for v in z.values())
    return round(s, 2) if s else None


def ergebnis_text(erg):
    t = (f"{erg['neu']} LST-Datei{'en' if erg['neu'] != 1 else ''} neu gelesen ({erg['teile']} Teile), "
         f"{erg['bekannt']} schon bekannt")
    if erg["fehler"]:
        t += f"; {len(erg['fehler'])} Fehler: " + "; ".join(erg["fehler"][:3])
    return t


def uebersicht(db):
    """Zahlen für die Lernzentrale: dict(dateien, teile, voll, gemessen)."""
    tl = teile(db)
    return dict(dateien=db.con.execute("SELECT COUNT(*) FROM lst_dateien").fetchone()[0], teile=len(tl),
                voll=sum(1 for t in tl if t["qualitaet"] == tp.VOLL),
                gemessen=sum(1 for t in tl if t.get("zeiten_gemessen")))
