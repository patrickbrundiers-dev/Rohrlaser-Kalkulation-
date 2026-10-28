"""Mehrere Arbeitsplätze: Angebote und Stammdaten über einen gemeinsamen Ordner teilen (Patrick 22.10.2026, 1a 2a 3a 4a 5b).

Jeder Arbeitsplatz behält seine eigene Datendatei. Im gemeinsamen Ordner (Netzlaufwerk, NAS oder ein OneDrive-/
SharePoint-Ordner) schreibt jeder Mitarbeiter nur seine eigene Datei Rohrlaser_<Kürzel>.sqlite. Weil jede Datei nur
einen Schreiber hat, gibt es keine Schreibkonflikte und keine halb geschriebene Datenbank, auch nicht über OneDrive:
die Datei entsteht erst lokal (Ordner Daten/Teilen) und wird dann in einem Schritt ausgetauscht.

Inhalt einer Datei: alle eigenen Angebote (Kopf, Positionen, Staffeln, STEP-Protokoll, 3D-Netze), die Stammdaten
(Tabellen von stammdaten, fracht_daten und zukauf) und die gemeinsamen Einstellungen (alle außer LOKAL).

Abgleich (Knopf, beim Start lesen, beim Beenden schreiben):
1. erfassen: Was hat sich seit dem letzten Abgleich hier geändert? Jede Stammdatenzeile hat eine feste Kennung
   (Spalte uid, beim Einfügen von einem Trigger vergeben); teilen_basis merkt je Zeile Prüfsumme und Zeitpunkt der
   letzten Änderung. Neue, geänderte und gelöschte Zeilen bekommen den Zeitpunkt jetzt.
2. lesen: die Dateien der anderen. Je Zeile gewinnt die neueste Änderung (Zeitpunkt, bei Gleichstand das Kürzel);
   gelöschte Zeilen bleiben als Grabstein (daten leer), damit das Löschen bei allen ankommt. Legen zwei Mitarbeiter
   dieselbe Zeile (gleicher Schlüssel, z. B. Profil-ID) getrennt an, gilt die kleinere Kennung für beide. Angebote der
   anderen kommen als fremde Angebote (angebote.fremd = Kürzel) in die eigene Datei: nur zum Ansehen und Kopieren,
   beim nächsten Abgleich wieder auf den Stand des Bearbeiters gesetzt.
3. schreiben: eigene Datei aktualisieren (nur geänderte Angebote neu) und in den gemeinsamen Ordner legen.

Zusammenarbeit (Patrick 28.10.2026, Freigabe „Alles 1-4“): das Programm gleicht alle paar Minuten selbst ab
(teilen_fenster.auto_abgleich). In der Info der eigenen Datei stehen die gerade geöffneten eigenen Angebote (wer
arbeitet woran). Vorgänge zwischen zwei Mitarbeitern stehen in der Tabelle vorgaenge der Datei des Absenders:
- Übergabe: der Bearbeiter gibt ein Angebot samt Inhalt an einen Kollegen ab; der übernimmt es beim nächsten Lesen
  als eigenes. Bis dahin ist es beim Absender schon ein fremdes Angebot (nur ansehen, Übergabe zurücknehmen).
- Anfrage: ein Kollege möchte ein Angebot übernehmen; der Bearbeiter wird beim Abgleich gefragt (übergeben/ablehnen).
- Abgelehnt: Antwort auf eine Anfrage.
Erledigte Vorgänge anderer merkt sich jeder Arbeitsplatz (teilen_erledigt), eigene verschwinden, sobald der Empfänger
sie umgesetzt hat. Konflikte (dieselbe Stammdatenzeile hier und bei einem Kollegen seit dem letzten Lesen geändert)
werden gemerkt (teilen_konflikte) und lassen sich ansehen und umkehren.
"""
import datetime
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import uuid
from pathlib import Path

from . import VERSION, zukauf
from .angebot import kuerzel_sauber
from .fracht_daten import FRACHT_TABELLEN
from .stammdaten import BAUGRUPPEN_VORLAGEN, EINSTELLUNGEN, KONTUR_VORLAGEN, TABELLEN, VERWEISE

FORMAT = 1                      # Aufbau der geteilten Datei
PRAEFIX = "Rohrlaser_"
ENDUNG = ".sqlite"
GETEILT = tuple(TABELLEN) + tuple(FRACHT_TABELLEN) + tuple(zukauf.TABELLEN) + (BAUGRUPPEN_VORLAGEN, KONTUR_VORLAGEN)  # Artikel vor Bezug
GETEILT_NAME = {t.name: t for t in GETEILT}
# Verweise über die Zeilen-ID: in der geteilten Datei steht statt der ID die Kennung (uid) der Zielzeile
ID_VERWEISE = {"zukauf_bezug": {"artikel_id": "zukauf_artikel"}, "zukauf_historie": {"artikel_id": "zukauf_artikel"}}
# Einstellungen nur für diesen Arbeitsplatz (Benutzer, Ordner, Ansicht, persönliche Signatur, Messprozesse, 3D-Darstellung)
LOKAL = {"benutzer_name", "benutzer_kuerzel", "benutzer_email", "benutzer_telefon", "teilen_ordner",
         "letzte_angebotsnummer", "step_ordner", "ablageordner", "sicherung_ordner2", "ansicht_hilfe",
         "anfrage_signatur", "anfrage_outlook_signatur", "step_prozesse", "step_cache", "step_cache_mb", "ansicht_3d",
         "ansicht_thema", "ansicht_schrift", "ansicht_dichte", "eingabe_richtung", "csv_ordner",
         "anfrage_ordner", "stangenbild_popup", "teilen_takt"}
EINSTELLUNGEN_GETEILT = tuple(e.name for e in EINSTELLUNGEN if e.name not in LOKAL)
EINST = "einstellungen"         # Tabellenname in teilen_basis für die gemeinsamen Einstellungen (uid = Name)
# Spalten eines Angebots, die nur die Anzeige merkt (Liste) oder die nur hier gelten
ANGEBOT_OHNE = ("id", "fremd", "fremd_stand", "vk_netto", "stand", "vk_am", "geaendert")
UEBERNEHMEN, ZUSAMMENFUEHREN = "uebernehmen", "zusammenfuehren"
UEBERGABE, ANFRAGE, ABGELEHNT = "uebergabe", "anfrage", "abgelehnt"     # Vorgänge zwischen Mitarbeitern
VORGAENGE, ERLEDIGT, KONFLIKTE = "teilen_vorgaenge", "teilen_erledigt", "teilen_konflikte"   # lokale Merker
FRISCH_MIN = 20                 # geöffnete Angebote eines Kollegen gelten so lange nach seinem letzten Schreiben
KONFLIKTE_MAX = 100


class TeilenFehler(Exception):
    """Abgleich nicht möglich (Ordner fehlt, Datei gesperrt …); der Text steht für den Benutzer."""


class KuerzelBelegt(TeilenFehler):
    """Im gemeinsamen Ordner gibt es die Datei dieses Kürzels schon von einem anderen Arbeitsplatz."""
    def __init__(self, kuerzel, info):
        self.kuerzel, self.info = kuerzel, info
        wer = ", ".join(x for x in (info.get("name"), info.get("rechner"), info.get("benutzer")) if x)
        super().__init__(f"Das Kürzel {kuerzel} benutzt schon ein anderer Arbeitsplatz ({wer or 'unbekannt'}, "
                         f"Stand {info.get('stand') or '?'}).")


class ErstAbgleich(TeilenFehler):
    """Erster Abgleich eines Arbeitsplatzes, im Ordner gibt es schon Daten anderer: übernehmen oder zusammenführen?"""
    def __init__(self, andere):
        self.andere = andere
        super().__init__("Im gemeinsamen Ordner gibt es schon Stammdaten von " + ", ".join(andere) + ".")


# ------------------------------------------------------------------ Einrichten (aus Datenbank._anlegen)
def einrichten(con):
    """Kennung je Stammdatenzeile (Spalte uid, Trigger beim Einfügen), Merker teilen_basis, Spalten der fremden
    Angebote. Läuft bei jedem Öffnen; ändert vorhandene Daten nicht (nur fehlende Kennungen werden vergeben)."""
    for t in GETEILT:
        spalten = {r[1] for r in con.execute(f'PRAGMA table_info("{t.name}")')}
        if "uid" not in spalten:
            con.execute(f'ALTER TABLE "{t.name}" ADD COLUMN uid TEXT')
        con.execute(f'CREATE TRIGGER IF NOT EXISTS "{t.name}_uid" AFTER INSERT ON "{t.name}" WHEN NEW.uid IS NULL '
                    f'BEGIN UPDATE "{t.name}" SET uid = lower(hex(randomblob(16))) WHERE rowid = NEW.rowid; END')
        con.execute(f'UPDATE "{t.name}" SET uid = lower(hex(randomblob(16))) WHERE uid IS NULL')
        con.execute(f'CREATE INDEX IF NOT EXISTS "{t.name}_uid_index" ON "{t.name}" (uid)')
    con.execute("CREATE TABLE IF NOT EXISTS teilen_basis (tabelle TEXT, uid TEXT, hash TEXT, zeit TEXT, "
                "PRIMARY KEY (tabelle, uid))")
    spalten = {r[1] for r in con.execute("PRAGMA table_info(angebote)")}
    for n in ("fremd", "fremd_stand"):
        if n not in spalten:
            con.execute(f"ALTER TABLE angebote ADD COLUMN {n} TEXT")


# ------------------------------------------------------------------ Benutzer
def kuerzel(db):
    return kuerzel_sauber(db.einstellung("benutzer_kuerzel"))


def bearbeiter_nachtragen(db):
    """Nach dem ersten Eintragen des Kürzels: eigene ältere Angebote ohne Bearbeiter bekommen das Kürzel (bis dahin
    gab es nur diesen Arbeitsplatz). Ergebnis: Anzahl."""
    k = kuerzel(db)
    if not k:
        return 0
    with db.con:
        return db.con.execute("UPDATE angebote SET bearbeiter=? WHERE (bearbeiter IS NULL OR bearbeiter='') "
                              "AND fremd IS NULL", (k,)).rowcount


def ordner(db):
    o = str(db.einstellung("teilen_ordner") or "").strip()
    return Path(o) if o else None


def aktiv(db):
    """Teilen eingerichtet: Kürzel und gemeinsamer Ordner eingetragen."""
    return bool(kuerzel(db) and ordner(db))


def datei_name(k):
    return f"{PRAEFIX}{k}{ENDUNG}"


def installation(db):
    """Kennung dieses Arbeitsplatzes (zufällig, einmal vergeben): wem gehört die Datei eines Kürzels?"""
    i = db.einstellung("teilen_installation")
    if not i:
        i = uuid.uuid4().hex
        db.einstellung_setzen("teilen_installation", i)
    return i


def mitarbeiter(db, k=None):
    """{Kürzel: {name, email, telefon, stand, version}} aller bekannten Mitarbeiter (eigener Eintrag aus den
    Einstellungen); mit k nur dieser Eintrag (oder {})."""
    alle = dict(db.einstellung("teilen_mitarbeiter") or {})
    ich = kuerzel(db)
    if ich:
        alle[ich] = dict(alle.get(ich) or {}, name=db.einstellung("benutzer_name") or "",
                         email=db.einstellung("benutzer_email") or "", telefon=db.einstellung("benutzer_telefon") or "")
    if k is not None:
        return alle.get(kuerzel_sauber(k)) or {}
    return alle


def jetzt(k):
    """Zeitpunkt einer Änderung als Text, der sich richtig sortiert; das Kürzel entscheidet bei Gleichstand."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "|" + (k or "")


# ------------------------------------------------------------------ Zeilen als Werte
def _hash(daten):
    if daten is None:
        return None
    return hashlib.sha1(json.dumps(daten, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _ohne_leere(d):
    """Leere Werte zählen nicht: so vergleichen sich Dateien verschiedener Programmversionen (neue Spalten leer)."""
    return {k: v for k, v in d.items() if v is not None}


def _uid_karte(con, tabelle):
    return {r[0]: r[1] for r in con.execute(f'SELECT id, uid FROM "{tabelle}"')}


def lokale_zeilen(con):
    """{(Tabelle, uid): Werte} aller geteilten Stammdaten und Einstellungen dieses Arbeitsplatzes; ID-Verweise als
    Kennung der Zielzeile. Doppelte Kennungen (kopierte Zeilen) bekommen vorher eine neue."""
    out = {}
    karten = {}
    for t in GETEILT:
        for (u,) in con.execute(f'SELECT uid FROM "{t.name}" GROUP BY uid HAVING COUNT(*) > 1').fetchall():
            ids = [r[0] for r in con.execute(f'SELECT id FROM "{t.name}" WHERE uid=? ORDER BY id', (u,))]
            for i in ids[1:]:
                con.execute(f'UPDATE "{t.name}" SET uid = lower(hex(randomblob(16))) WHERE id=?', (i,))
    for t in GETEILT:
        verweise = ID_VERWEISE.get(t.name, {})
        for ziel in verweise.values():
            if ziel not in karten:
                karten[ziel] = _uid_karte(con, ziel)
        cur = con.execute(f'SELECT * FROM "{t.name}"')
        namen = [d[0] for d in cur.description]
        for r in cur:
            z = dict(zip(namen, r))
            u = z.pop("uid")
            z.pop("id", None)
            for feld, ziel in verweise.items():
                z[feld] = karten[ziel].get(z.get(feld))
            out[(t.name, u)] = _ohne_leere(z)
    for name, wert in con.execute("SELECT name, wert FROM einstellungen"):
        if name in EINSTELLUNGEN_GETEILT:
            out[(EINST, name)] = {"wert": wert}
    return out


def basis(con):
    return {(r[0], r[1]): (r[2], r[3]) for r in con.execute("SELECT tabelle, uid, hash, zeit FROM teilen_basis")}


def _basis_setzen(con, tabelle, u, h, zeit):
    con.execute("INSERT OR REPLACE INTO teilen_basis (tabelle, uid, hash, zeit) VALUES (?, ?, ?, ?)",
                (tabelle, u, h, zeit))


def erfassen(con, zeit):
    """Schritt 1: Änderungen seit dem letzten Abgleich mit dem Zeitpunkt zeit merken (neu, geändert, gelöscht).
    Ergebnis: Anzahl erfasster Änderungen."""
    b = basis(con)
    n = 0
    lokal = lokale_zeilen(con)
    for schl, daten in lokal.items():
        h = _hash(daten)
        if b.get(schl, (None, None))[0] != h:
            _basis_setzen(con, schl[0], schl[1], h, zeit)
            n += 1
    for schl, (h, _z) in b.items():
        if h is not None and schl not in lokal and schl[0] != EINST:
            _basis_setzen(con, schl[0], schl[1], None, zeit)      # gelöscht: Grabstein
            n += 1
    return n


# ------------------------------------------------------------------ Angebote als Werte
def _zukauf_uid(liste_json, karte):
    """positionen.zukauf mit Kennung des Artikels (artikel_uid) statt nur der ID."""
    try:
        liste = json.loads(liste_json) if liste_json else None
    except (TypeError, ValueError):
        return liste_json
    if not isinstance(liste, list):
        return liste_json
    for e in liste:
        if isinstance(e, dict):
            e["artikel_uid"] = karte.get(e.get("artikel_id"))
            e.pop("artikel_id", None)
    return json.dumps(liste, ensure_ascii=False, sort_keys=True)


def _zukauf_id(liste_json, karte):
    """Umkehrung von _zukauf_uid mit der Karte uid -> ID dieses Arbeitsplatzes (unbekannter Artikel: ID leer)."""
    try:
        liste = json.loads(liste_json) if liste_json else None
    except (TypeError, ValueError):
        return liste_json
    if not isinstance(liste, list):
        return liste_json
    for e in liste:
        if isinstance(e, dict) and "artikel_uid" in e:
            e["artikel_id"] = karte.get(e.pop("artikel_uid"))
    return json.dumps(liste, ensure_ascii=False)


def _zeilen(con, sql, wert):
    cur = con.execute(sql, (wert,))
    namen = [d[0] for d in cur.description]
    return [dict(zip(namen, r)) for r in cur]


def angebot_inhalt(con, angebot_id, artikel_uid=None):
    """Alles zu einem Angebot ohne die IDs dieses Arbeitsplatzes: (Inhalt, {Index der Position: Netz-Bytes}).
    Staffeln verweisen über den Index ihrer Stufe, Zukaufteile über die Kennung des Artikels."""
    karte = artikel_uid if artikel_uid is not None else _uid_karte(con, "zukauf_artikel")
    kopf = _zeilen(con, "SELECT * FROM angebote WHERE id=?", angebot_id)[0]
    kopf = _ohne_leere({k: v for k, v in kopf.items() if k not in ANGEBOT_OHNE})
    positionen, netze, pos_index = [], {}, {}
    for i, p in enumerate(_zeilen(con, "SELECT * FROM positionen WHERE angebot_id=? ORDER BY id", angebot_id)):
        pos_index[p["id"]] = i
        if p.get("zukauf"):
            p["zukauf"] = _zukauf_uid(p["zukauf"], karte)
        positionen.append(_ohne_leere({k: v for k, v in p.items() if k not in ("id", "angebot_id")}))
    for pid, daten in con.execute("SELECT n.position_id, n.daten FROM netze n JOIN positionen p ON p.id = n.position_id "
                                  "WHERE p.angebot_id=?", (angebot_id,)):
        if pid in pos_index and daten is not None:
            netze[pos_index[pid]] = bytes(daten)
    stufen, stufe_index = [], {}
    for i, s in enumerate(_zeilen(con, "SELECT * FROM staffel_stufen WHERE angebot_id=? ORDER BY id", angebot_id)):
        stufe_index[s["id"]] = i
        stufen.append(_ohne_leere({k: v for k, v in s.items() if k not in ("id", "angebot_id")}))
    staffeln = []
    for s in _zeilen(con, "SELECT * FROM staffeln WHERE angebot_id=? ORDER BY id", angebot_id):
        s = {k: v for k, v in s.items() if k not in ("id", "angebot_id")}
        s["stufe_id"] = stufe_index.get(s.get("stufe_id"))
        staffeln.append(_ohne_leere(s))
    protokoll = [r[0] for r in con.execute("SELECT zeile FROM step_protokoll WHERE angebot_id=? ORDER BY id",
                                           (angebot_id,))]
    inhalt = dict(kopf=kopf, positionen=positionen, stufen=stufen, staffeln=staffeln, protokoll=protokoll,
                  netze={str(i): hashlib.sha1(d).hexdigest() for i, d in sorted(netze.items())})
    return inhalt, netze


def _einfuegen(con, tabelle, werte, spalten):
    namen = [n for n in werte if n in spalten]
    return con.execute(f'INSERT INTO "{tabelle}" ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                       f'VALUES ({", ".join("?" * len(namen))})', [werte[n] for n in namen]).lastrowid


def angebot_einsetzen(con, inhalt, netze, fremd, stand, angebot_id=None, artikel_id=None):
    """Angebot aus angebot_inhalt hier anlegen (angebot_id None) oder ersetzen (die ID bleibt, offene Fenster laden
    es neu). fremd: Kürzel des Bearbeiters (None = eigenes Angebot). Ergebnis: ID."""
    karte = artikel_id if artikel_id is not None else {u: i for i, u in _uid_karte(con, "zukauf_artikel").items()}
    spalten = {t: {r[1] for r in con.execute(f'PRAGMA table_info("{t}")')}
               for t in ("angebote", "positionen", "staffeln", "staffel_stufen")}
    kopf = {k: v for k, v in inhalt["kopf"].items() if k in spalten["angebote"] and k not in ANGEBOT_OHNE}
    kopf.update(fremd=fremd, fremd_stand=stand, geaendert=datetime.datetime.now().isoformat(timespec="seconds"))
    if angebot_id is None:
        angebot_id = _einfuegen(con, "angebote", kopf, spalten["angebote"])
    else:
        leer = {n: None for n in spalten["angebote"] if n not in kopf and n not in ("id", "vk_netto", "stand", "vk_am")}
        werte = dict(leer, **kopf)
        con.execute(f'UPDATE angebote SET {", ".join(chr(34) + n + chr(34) + "=?" for n in werte)} WHERE id=?',
                    list(werte.values()) + [angebot_id])
        for t in ("positionen", "staffeln", "staffel_stufen", "step_protokoll"):     # Netze: ON DELETE CASCADE
            con.execute(f"DELETE FROM {t} WHERE angebot_id=?", (angebot_id,))
        con.execute("UPDATE angebote SET vk_netto=NULL, stand=NULL, vk_am=NULL WHERE id=?", (angebot_id,))
    pos_ids = []
    for p in inhalt["positionen"]:
        p = dict(p, angebot_id=angebot_id)
        if p.get("zukauf"):
            p["zukauf"] = _zukauf_id(p["zukauf"], karte)
        pos_ids.append(_einfuegen(con, "positionen", p, spalten["positionen"]))
    for i, daten in netze.items():
        if int(i) < len(pos_ids):
            con.execute("INSERT OR REPLACE INTO netze (position_id, daten) VALUES (?, ?)", (pos_ids[int(i)], daten))
    stufen = [_einfuegen(con, "staffel_stufen", dict(s, angebot_id=angebot_id), spalten["staffel_stufen"])
              for s in inhalt["stufen"]]
    for s in inhalt["staffeln"]:
        i = s.get("stufe_id")
        s = dict(s, angebot_id=angebot_id, stufe_id=stufen[i] if isinstance(i, int) and i < len(stufen) else None)
        _einfuegen(con, "staffeln", s, spalten["staffeln"])
    con.executemany("INSERT INTO step_protokoll (angebot_id, zeile) VALUES (?, ?)",
                    [(angebot_id, z) for z in inhalt["protokoll"]])
    return angebot_id


# ------------------------------------------------------------------ Geteilte Datei
def _datei_anlegen(con):
    con.execute("CREATE TABLE IF NOT EXISTS info (name TEXT PRIMARY KEY, wert TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS stammdaten (tabelle TEXT, uid TEXT, zeit TEXT, daten TEXT, "
                "PRIMARY KEY (tabelle, uid))")
    con.execute("CREATE TABLE IF NOT EXISTS angebote (nummer TEXT PRIMARY KEY, hash TEXT, inhalt TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS netze (nummer TEXT, idx INTEGER, daten BLOB, PRIMARY KEY (nummer, idx))")
    con.execute("CREATE TABLE IF NOT EXISTS vorgaenge (id TEXT PRIMARY KEY, art TEXT, nummer TEXT, an TEXT, zeit TEXT, "
                "notiz TEXT, bezug TEXT, inhalt TEXT)")


def info_lesen(pfad):
    """info einer geteilten Datei (kuerzel, name, installation, schema, version, stand …) oder {}."""
    try:
        con = sqlite3.connect(Path(pfad))
        try:
            return {n: json.loads(w) for n, w in con.execute("SELECT name, wert FROM info")}
        finally:
            con.close()
    except (sqlite3.DatabaseError, OSError, ValueError):
        return {}


def _cache(db):
    o = db.pfad.parent / "Teilen"
    o.mkdir(parents=True, exist_ok=True)
    return o


def _ordner_pruefen(db):
    o = ordner(db)
    if o is None:
        raise TeilenFehler("Kein gemeinsamer Ordner eingetragen (Datei → Benutzer und gemeinsamer Ordner …).")
    if not o.is_dir():
        raise TeilenFehler(f"Der gemeinsame Ordner ist nicht erreichbar:\n{o}")
    return o


def andere_dateien(db):
    """{Kürzel: Pfad} der Dateien anderer Mitarbeiter im gemeinsamen Ordner."""
    o, ich = _ordner_pruefen(db), kuerzel(db)
    out = {}
    for p in sorted(o.glob(f"{PRAEFIX}*{ENDUNG}")):
        k = kuerzel_sauber(p.name[len(PRAEFIX):-len(ENDUNG)])
        if k and k != ich and p.name == datei_name(k):
            out[k] = p
    return out


def _lokal_kopieren(db, quelle):
    """Fremde Datei in den Zwischenspeicher kopieren (nur wenn neu oder geändert): so liest das Programm nie eine
    Datei, die gerade ausgetauscht oder synchronisiert wird."""
    ziel = _cache(db) / ("fremd_" + quelle.name)
    st = quelle.stat()
    merk = ziel.with_suffix(".stand")
    stand = f"{st.st_size}|{st.st_mtime_ns}"
    if ziel.exists() and merk.exists() and merk.read_text() == stand:
        return ziel
    tmp = ziel.with_name(ziel.name + ".neu")
    shutil.copyfile(quelle, tmp)
    os.replace(tmp, ziel)
    merk.write_text(stand)
    return ziel


def schreiben(db, uebernehmen=False, offen=None):
    """Schritt 3: eigene Datei im Zwischenspeicher aktualisieren und in den gemeinsamen Ordner legen.
    uebernehmen: die Datei des Kürzels gehört einem anderen Arbeitsplatz (z. B. neuer Rechner) und wird übernommen;
    ihre Angebote, die es hier nicht gibt, kommen vorher als eigene Angebote herein. offen: {Nummer: seit} der hier
    gerade geöffneten eigenen Angebote (für die Kollegen). Ergebnis: Anzahl Angebote."""
    from . import nummern
    k, o = kuerzel(db), _ordner_pruefen(db)
    if not k:
        raise TeilenFehler("Kein Kürzel eingetragen.")
    nummern.endgueltig(db)          # vorläufige Nummern (Ordner war nicht erreichbar) jetzt endgültig vergeben
    ziel = o / datei_name(k)
    ich = installation(db)
    if ziel.exists():
        info = info_lesen(ziel)
        if info and info.get("installation") not in (None, ich):
            if not uebernehmen:
                raise KuerzelBelegt(k, info)
            _eigene_holen(db, ziel)
    con = db.con
    if not con.execute("SELECT 1 FROM teilen_basis LIMIT 1").fetchone() and andere_dateien(db):
        raise ErstAbgleich(sorted(andere_dateien(db)))     # erst lesen: sonst gälten die eigenen Werte als neuer
    with con:
        erfassen(con, jetzt(k))
        lokal = lokale_zeilen(con)
        stand_basis = basis(con)
    spiegel = _cache(db) / datei_name(k)
    sc = sqlite3.connect(spiegel)
    try:
        with sc:
            _datei_anlegen(sc)
            sc.execute("DELETE FROM stammdaten")
            zeilen = []
            for (t, u), (h, zeit) in stand_basis.items():
                daten = lokal.get((t, u)) if h is not None else None
                if h is not None and daten is None:
                    continue
                zeilen.append((t, u, zeit, json.dumps(daten, ensure_ascii=False) if daten is not None else None))
            sc.executemany("INSERT INTO stammdaten (tabelle, uid, zeit, daten) VALUES (?, ?, ?, ?)", zeilen)
            karte = _uid_karte(con, "zukauf_artikel")
            alt = dict(sc.execute("SELECT nummer, hash FROM angebote").fetchall())
            eigene = con.execute("SELECT id, nummer FROM angebote WHERE fremd IS NULL").fetchall()
            for i, nummer in eigene:
                inhalt, netze = angebot_inhalt(con, i, karte)
                h = _hash(inhalt)
                if alt.get(nummer) == h:
                    continue
                sc.execute("INSERT OR REPLACE INTO angebote (nummer, hash, inhalt) VALUES (?, ?, ?)",
                           (nummer, h, json.dumps(inhalt, ensure_ascii=False)))
                sc.execute("DELETE FROM netze WHERE nummer=?", (nummer,))
                sc.executemany("INSERT INTO netze (nummer, idx, daten) VALUES (?, ?, ?)",
                               [(nummer, idx, d) for idx, d in netze.items()])
            weg = set(alt) - {n for _, n in eigene}
            sc.executemany("DELETE FROM angebote WHERE nummer=?", [(n,) for n in weg])
            uebergaben = _vorgaenge_schreiben(db, sc, karte)
            sc.executemany("DELETE FROM netze WHERE nummer=?", [(n,) for n in weg - uebergaben])
            info = dict(kuerzel=k, name=db.einstellung("benutzer_name") or "", email=db.einstellung("benutzer_email") or "",
                        telefon=db.einstellung("benutzer_telefon") or "", installation=ich, rechner=socket.gethostname(),
                        benutzer=os.environ.get("USERNAME") or os.environ.get("USER") or "",
                        schema=con.execute("PRAGMA user_version").fetchone()[0], version=VERSION, format=FORMAT,
                        stand=datetime.datetime.now().isoformat(timespec="seconds"), angebote=len(eigene),
                        letzte=db.einstellung("letzte_angebotsnummer"), offen=dict(offen or {}))
            sc.executemany("INSERT OR REPLACE INTO info (name, wert) VALUES (?, ?)",
                           [(n, json.dumps(w, ensure_ascii=False)) for n, w in info.items()])
    finally:
        sc.close()
    tmp = o / (datei_name(k) + ".neu")
    try:
        shutil.copyfile(spiegel, tmp)
        os.replace(tmp, ziel)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise TeilenFehler(f"Die eigene Datei ließ sich nicht in den gemeinsamen Ordner schreiben:\n{e}") from e
    db.einstellung_setzen("teilen_geschrieben", info["stand"])
    return len(eigene)


def _eigene_holen(db, pfad):
    """Beim Übernehmen der Datei des eigenen Kürzels: deren Angebote, die es hier nicht gibt, als eigene anlegen."""
    from . import nummern
    kopie = _lokal_kopieren(db, pfad)
    fc = sqlite3.connect(kopie)
    try:
        vorhanden = {r[0] for r in db.con.execute("SELECT nummer FROM angebote")}
        letzte = info_lesen(kopie).get("letzte")
        with db.con:
            if nummern.zaehler(letzte) > nummern.zaehler(db.einstellung("letzte_angebotsnummer")):
                db._einstellung_schreiben("letzte_angebotsnummer", letzte)    # Zähler geht dort weiter
            entfernt = {(t, u): (zeit, json.loads(daten) if daten is not None else None)
                        for t, u, zeit, daten in fc.execute("SELECT tabelle, uid, zeit, daten FROM stammdaten")}
            zusammenfuehren(db, entfernt)          # Stammdaten dieses Kürzels (z. B. allein mit dem Teilen begonnen)
            for nummer, h, inhalt in fc.execute("SELECT nummer, hash, inhalt FROM angebote"):
                if nummer in vorhanden:
                    continue
                netze = {i: bytes(d) for i, d in fc.execute("SELECT idx, daten FROM netze WHERE nummer=?", (nummer,))}
                angebot_einsetzen(db.con, json.loads(inhalt), netze, None, None)
    finally:
        fc.close()


# ------------------------------------------------------------------ Lesen und zusammenführen
def _schluessel_treffer(con, t, daten, u):
    """Andere Zeile dieses Arbeitsplatzes mit demselben Schlüssel (z. B. Profil-ID) und anderer Kennung."""
    if not t.schluessel:
        return None
    bed, werte = [], []
    for s in t.schluessel:
        bed.append(f"""COALESCE("{s}", '') = COALESCE(?, '')""")
        werte.append(daten.get(s))
    r = con.execute(f'SELECT id, uid FROM "{t.name}" WHERE {" AND ".join(bed)} AND uid IS NOT ?', werte + [u]).fetchone()
    return r


def _zeile_schreiben(db, t, zeilen_id, daten, u):
    """Werte in die Zeile zeilen_id (None = neu anlegen) schreiben; Umbenennungen von Schlüsseln wie beim Ändern
    von Hand in die Angebote mitziehen (die übrigen Stammdaten kommen selbst mit dem Abgleich)."""
    con = db.con
    spalten = [r[1] for r in con.execute(f'PRAGMA table_info("{t.name}")') if r[1] not in ("id", "uid")]
    werte = {n: daten.get(n) for n in spalten}
    if zeilen_id is None:
        _einfuegen(con, t.name, dict(werte, uid=u), set(spalten) | {"uid"})
        return
    alt = dict(zip([d[0] for d in con.execute(f'SELECT * FROM "{t.name}" WHERE id=?', (zeilen_id,)).description],
                   con.execute(f'SELECT * FROM "{t.name}" WHERE id=?', (zeilen_id,)).fetchone()))
    for n in spalten:                 # Spalten, die die andere Version nicht kennt, bleiben
        if n not in daten:
            werte[n] = alt.get(n)
    con.execute(f'UPDATE "{t.name}" SET {", ".join(chr(34) + n + chr(34) + "=?" for n in werte)}, uid=? WHERE id=?',
                list(werte.values()) + [u, zeilen_id])
    for (quelle, feld), ziele in VERWEISE.items():
        if quelle != t.name or alt.get(feld) in (None, "") or werte.get(feld) in (None, "") or alt[feld] == werte[feld]:
            continue
        for ziel, zfeld in ziele:
            if ziel not in GETEILT_NAME:
                con.execute(f'UPDATE "{ziel}" SET "{zfeld}"=? WHERE "{zfeld}"=?', (werte[feld], alt[feld]))
        if (quelle, feld) == ("maschinen", "maschinen_id"):
            db._maschine_umbenannt(alt[feld], werte[feld])


def zusammenfuehren(db, entfernt, seit=None, konflikte=None):
    """Stammdaten und Einstellungen der anderen übernehmen, wo deren Änderung neuer ist. entfernt: {(Tabelle, uid):
    (zeit, daten)} – je Zeile die neueste Änderung aus allen fremden Dateien. seit: Zeitpunkt des letzten Lesens;
    wurde eine Zeile seitdem hier und bei einem Kollegen verschieden geändert, kommt ein Eintrag in die Liste
    konflikte. Ergebnis: Anzahl übernommener Zeilen."""
    con = db.con
    b = basis(con)
    n = 0
    karten = {}
    if seit and konflikte is not None:
        konflikte.extend(_konflikte_finden(con, entfernt, b, seit))

    def id_von(tabelle, u):
        if tabelle not in karten:
            karten[tabelle] = {uu: i for i, uu in _uid_karte(con, tabelle).items()}
        return karten[tabelle].get(u)

    # gemeinsame Einstellungen
    for (t, u), (zeit, daten) in entfernt.items():
        if t != EINST or u not in EINSTELLUNGEN_GETEILT or daten is None:
            continue
        if zeit > (b.get((t, u)) or (None, ""))[1]:
            con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES (?, ?)", (u, daten["wert"]))
            _basis_setzen(con, t, u, _hash({"wert": daten["wert"]}), zeit)
            n += 1
    for t in GETEILT:
        eintraege = [(u, zeit, daten) for (tt, u), (zeit, daten) in entfernt.items() if tt == t.name
                     and zeit > (b.get((tt, u)) or (None, ""))[1]]
        # erst Löschen, dann Ändern vorhandener Zeilen, dann neue: Umbenennungen machen Schlüssel frei
        eintraege.sort(key=lambda e: (e[2] is not None, id_von(t.name, e[0]) is None, e[0]))
        verweise = ID_VERWEISE.get(t.name, {})
        for u, zeit, daten in eintraege:
            hier = id_von(t.name, u)
            if daten is None:
                if hier is not None:
                    con.execute(f'DELETE FROM "{t.name}" WHERE id=?', (hier,))
                    karten.pop(t.name, None)
                _basis_setzen(con, t.name, u, None, zeit)
                n += 1
                continue
            werte = dict(daten)
            fehlt = False
            for feld, ziel in verweise.items():
                if werte.get(feld) is not None:
                    werte[feld] = id_von(ziel, werte[feld])
                    fehlt = fehlt or werte[feld] is None
            if fehlt:               # Zielzeile (Artikel) gelöscht: Zeile entfällt
                continue
            andere = _schluessel_treffer(con, t, werte, u)
            try:
                if andere is not None:
                    a_id, a_uid = andere
                    a_zeit = (b.get((t.name, a_uid)) or (None, ""))[1]
                    stein = max(zeit, a_zeit) + "~"
                    if a_uid < u:            # die vorhandene Zeile behält ihre Kennung, die fremde wird ein Grabstein
                        if hier is not None:
                            con.execute(f'DELETE FROM "{t.name}" WHERE id=?', (hier,))
                        if zeit > a_zeit:
                            _zeile_schreiben(db, t, a_id, werte, a_uid)
                            _basis_setzen(con, t.name, a_uid, None, zeit)
                        _basis_setzen(con, t.name, u, None, stein)
                    else:                    # die fremde Kennung gilt: vorhandene Zeile übernimmt sie
                        if hier is not None:
                            con.execute(f'DELETE FROM "{t.name}" WHERE id=?', (hier,))
                        if zeit >= a_zeit:
                            _zeile_schreiben(db, t, a_id, werte, u)
                            _basis_setzen(con, t.name, u, None, zeit)
                        else:
                            con.execute(f'UPDATE "{t.name}" SET uid=? WHERE id=?', (u, a_id))
                            _basis_setzen(con, t.name, u, None, a_zeit)
                        _basis_setzen(con, t.name, a_uid, None, stein)
                    karten.pop(t.name, None)
                else:
                    _zeile_schreiben(db, t, hier, werte, u)
                    if hier is None:
                        karten.pop(t.name, None)
                    _basis_setzen(con, t.name, u, None, zeit)
                n += 1
            except sqlite3.IntegrityError:
                continue            # Schlüssel doppelt (seltene Überschneidung): beim nächsten Abgleich wieder
    # Prüfsummen der übernommenen Zeilen nach dem Stand hier (eigene Spalten neuerer Versionen zählen mit)
    lokal = lokale_zeilen(con)
    for (t, u), (h, zeit) in basis(con).items():
        if h is None and (t, u) in lokal:
            _basis_setzen(con, t, u, _hash(lokal[(t, u)]), zeit)
    return n


def lesen(db, modus=None):
    """Schritt 2: Dateien der anderen lesen, Stammdaten zusammenführen, fremde Angebote aktualisieren.
    modus: beim ersten Abgleich dieses Arbeitsplatzes UEBERNEHMEN (Stammdaten der anderen statt der eigenen) oder
    ZUSAMMENFUEHREN; ohne Angabe löst der erste Abgleich ErstAbgleich aus. Ergebnis: Bericht (dict)."""
    con, k = db.con, kuerzel(db)
    if not k:
        raise TeilenFehler("Kein Kürzel eingetragen.")
    dateien = andere_dateien(db)
    erstmals = not con.execute("SELECT 1 FROM teilen_basis LIMIT 1").fetchone()
    bericht = dict(mitarbeiter=[], stammdaten=0, angebote_neu=0, angebote_geaendert=0, angebote_weg=0, hinweise=[],
                   geaenderte_ids=[], entfernte_ids=[], uebernommen=[], anfragen=[], abgelehnt=[], konflikte=[])
    gelesen = {}
    for k2, pfad in dateien.items():
        try:
            gelesen[k2] = _lokal_kopieren(db, pfad)
        except OSError as e:
            bericht["hinweise"].append(f"Datei von {k2} nicht lesbar: {e}")
    if erstmals and gelesen and modus is None:
        raise ErstAbgleich(sorted(gelesen))
    schema = con.execute("PRAGMA user_version").fetchone()[0]
    with con:
        if erstmals and gelesen and modus == UEBERNEHMEN:
            for t in GETEILT:            # Zukaufartikel bleiben (Angebote verweisen über die ID), sie werden zusammengeführt
                if t.schluessel:
                    con.execute(f'DELETE FROM "{t.name}"')
        seit = None if erstmals else db.einstellung("teilen_lese_zeit")
        lese_zeit = jetzt(k)
        erfassen(con, ("0000|" + k) if erstmals and gelesen else lese_zeit)
        entfernt = {}
        vorgaenge = {}          # Kürzel -> [Vorgang] aus den Dateien der anderen
        bekannt = dict(db.einstellung("teilen_mitarbeiter") or {})
        angebote = {}
        for k2, kopie in gelesen.items():
            fc = sqlite3.connect(kopie)
            try:
                info = {n: json.loads(w) for n, w in fc.execute("SELECT name, wert FROM info")}
                bekannt[k2] = {n: info.get(n) for n in ("name", "email", "telefon", "stand", "version", "offen")}
                bericht["mitarbeiter"].append(k2)
                if int(info.get("format") or 0) > FORMAT or int(info.get("schema") or 0) > schema:
                    bericht["hinweise"].append(
                        f"{k2} arbeitet mit einer neueren Programmversion ({info.get('version')}): Stammdaten von "
                        f"{k2} werden erst nach dem Update dieses Programms übernommen.")
                else:
                    for t, u, zeit, daten in fc.execute("SELECT tabelle, uid, zeit, daten FROM stammdaten"):
                        if (t, u) not in entfernt or zeit > entfernt[(t, u)][0]:
                            entfernt[(t, u)] = (zeit, json.loads(daten) if daten is not None else None)
                angebote[k2] = {nummer: (h, inhalt) for nummer, h, inhalt in
                                fc.execute("SELECT nummer, hash, NULL FROM angebote")}
                if fc.execute("SELECT 1 FROM sqlite_master WHERE name='vorgaenge'").fetchone():
                    cur = fc.execute("SELECT id, art, nummer, an, zeit, notiz, bezug FROM vorgaenge")
                    namen = [d[0] for d in cur.description]
                    vorgaenge[k2] = [dict(zip(namen, r), von=k2) for r in cur]
                else:
                    vorgaenge[k2] = []
            except (sqlite3.DatabaseError, ValueError) as e:
                bericht["hinweise"].append(f"Datei von {k2} nicht lesbar: {e}")
            finally:
                fc.close()
        bericht["stammdaten"] = zusammenfuehren(db, entfernt, seit, bericht["konflikte"])
        _konflikte_merken(db, bericht["konflikte"])
        db._einstellung_schreiben("teilen_mitarbeiter", bekannt)
        karte = _uid_karte(con, "zukauf_artikel")
        karte_id = {u: i for i, u in karte.items()}
        unterwegs = _vorgaenge_lesen(db, gelesen, vorgaenge, angebote, bericht, karte_id)
        for k2, liste in angebote.items():
            fc = sqlite3.connect(gelesen[k2])
            try:
                hier = {r[1]: (r[0], r[2]) for r in con.execute("SELECT id, nummer, fremd FROM angebote")}
                fremd_stand = dict(con.execute("SELECT id, fremd_stand FROM angebote WHERE fremd=?", (k2,)).fetchall())
                for nummer, (h, _) in liste.items():
                    a = hier.get(nummer)
                    if a is not None and a[1] not in (None, k2) and nummer not in angebote.get(a[1], {}):
                        a = (a[0], k2)          # beim bisherigen Bearbeiter nicht mehr: übergeben, jetzt von k2
                    if a is not None and a[1] != k2:
                        bericht["hinweise"].append(f"Angebot {nummer} von {k2} nicht übernommen: doppelte "
                                                   "Angebotsnummer, die Nummer gibt es hier schon. Bitte bei einem "
                                                   "der beiden Angebote die Nummer ändern.")
                        continue
                    if a is not None and fremd_stand.get(a[0]) == h:
                        continue            # unverändert (Stand des letzten Lesens), ohne den Inhalt zu vergleichen
                    if a is not None and _hash(angebot_inhalt(con, a[0], karte)[0]) == h:
                        con.execute("UPDATE angebote SET fremd=?, fremd_stand=? WHERE id=?", (k2, h, a[0]))
                        continue
                    inhalt = json.loads(fc.execute("SELECT inhalt FROM angebote WHERE nummer=?", (nummer,)).fetchone()[0])
                    netze = {i: bytes(d) for i, d in fc.execute("SELECT idx, daten FROM netze WHERE nummer=?", (nummer,))}
                    i = angebot_einsetzen(con, inhalt, netze, k2, h, a[0] if a else None, karte_id)
                    bericht["angebote_geaendert" if a else "angebote_neu"] += 1
                    bericht["geaenderte_ids"].append(i)
                for nummer, (i, fremd) in hier.items():
                    if fremd == k2 and nummer not in liste and nummer not in unterwegs:
                        con.execute("DELETE FROM angebote WHERE id=?", (i,))
                        bericht["angebote_weg"] += 1
                        bericht["entfernte_ids"].append(i)
            finally:
                fc.close()
        db._einstellung_schreiben("teilen_gelesen", datetime.datetime.now().isoformat(timespec="seconds"))
        db._einstellung_schreiben("teilen_lese_zeit", lese_zeit)
    return bericht


def abgleichen(db, modus=None, uebernehmen=False):
    """Knopf Abgleichen: lesen, dann schreiben. Ergebnis: Bericht von lesen plus 'eigene' (Anzahl geteilter Angebote)."""
    bericht = lesen(db, modus)
    bericht["eigene"] = schreiben(db, uebernehmen)
    return bericht


def bericht_text(b):
    """Kurzer Text für die Statuszeile."""
    teile = []
    if b.get("mitarbeiter"):
        teile.append("Abgeglichen mit " + ", ".join(b["mitarbeiter"]))
    else:
        teile.append("Noch keine Dateien anderer Mitarbeiter im gemeinsamen Ordner")
    neu, geaendert, weg = b.get("angebote_neu", 0), b.get("angebote_geaendert", 0), b.get("angebote_weg", 0)
    if neu or geaendert or weg:
        teile.append(f"Angebote: {neu} neu, {geaendert} geändert, {weg} entfernt")
    if b.get("stammdaten"):
        teile.append(f"{b['stammdaten']} Stammdaten übernommen")
    if b.get("uebernommen"):
        teile.append("übernommen: " + ", ".join(f"{u['nummer']} von {u['von']}" for u in b["uebernommen"]))
    if b.get("konflikte"):
        teile.append(f"{len(b['konflikte'])} Konflikte (Datei → Abgleich-Konflikte …)")
    if b.get("nummern"):
        teile.append("endgültige Nummer: " + ", ".join(f"{a} → {n}" for a, n in b["nummern"]))
    if "eigene" in b:
        teile.append(f"{b['eigene']} eigene Angebote geteilt")
    return "; ".join(teile) + "."


# ------------------------------------------------------------------ Konflikte (Schritt 4)
def _wer(zeit):
    return str(zeit or "").rpartition("|")[2]


def _bezeichnung(tabelle, daten):
    """Lesbarer Name einer Zeile: Reiter und Schlüssel (z. B. „Kunden 10042 Muster GmbH“)."""
    t = GETEILT_NAME.get(tabelle)
    if t is None:
        return tabelle
    d = daten or {}
    teile = [str(d.get(s)) for s in t.schluessel if d.get(s) not in (None, "")]
    for name in ("name", "bezeichnung", "kunde"):
        if d.get(name) not in (None, "") and str(d[name]) not in teile:
            teile.append(str(d[name]))
            break
    return f"{t.titel}: {' '.join(teile)}" if teile else t.titel


def _konflikte_finden(con, entfernt, b, seit):
    """Zeilen, die seit dem letzten Lesen (seit) hier und bei einem Kollegen verschieden geändert wurden. Es gewinnt
    die jüngere Änderung wie bisher; der Eintrag hält die verlorene Fassung zum Wiederherstellen fest."""
    from .stammdaten import EINSTELLUNG
    lokal = None
    out = []
    for (t, u), (zeit, daten) in entfernt.items():
        hier = b.get((t, u))
        if hier is None or zeit <= seit or hier[1] <= seit or zeit == hier[1]:
            continue
        if _hash(daten) == hier[0] or (t == EINST and u not in EINSTELLUNGEN_GETEILT):
            continue
        if lokal is None:
            lokal = lokale_zeilen(con)
        meine = lokal.get((t, u))
        if meine == daten:
            continue
        fremd_gewinnt = zeit > hier[1]
        if t == EINST:
            e = EINSTELLUNG.get(u)
            text = "Einstellung: " + (e.titel if e else u)
        else:
            text = _bezeichnung(t, daten or meine)
        out.append(dict(id=uuid.uuid4().hex, zeit=datetime.datetime.now().isoformat(timespec="seconds"), tabelle=t,
                        uid=u, text=text, gewinner=_wer(zeit) if fremd_gewinnt else _wer(hier[1]),
                        verlierer=_wer(hier[1]) if fremd_gewinnt else _wer(zeit),
                        verloren=meine if fremd_gewinnt else daten, gewonnen=daten if fremd_gewinnt else meine,
                        erledigt=False))
    return out


def _konflikte_merken(db, neu):
    if neu:
        alle = list(neu) + list(db.einstellung(KONFLIKTE) or [])
        db._einstellung_schreiben(KONFLIKTE, alle[:KONFLIKTE_MAX])


def konflikte(db, offen_nur=False):
    """Gemerkte Konflikte, neueste zuerst (offen_nur: nur nicht erledigte)."""
    return [k for k in (db.einstellung(KONFLIKTE) or []) if not (offen_nur and k.get("erledigt"))]


def konflikt_erledigt(db, kid, wiederherstellen=False):
    """Konflikt als erledigt markieren; wiederherstellen: die verlorene Fassung hier eintragen (geht beim nächsten
    Abgleich als neueste Änderung an alle). Ergebnis: True, wenn gefunden."""
    alle = list(db.einstellung(KONFLIKTE) or [])
    k = next((x for x in alle if x.get("id") == kid), None)
    if k is None:
        return False
    with db.con:
        if wiederherstellen:
            _zeile_setzen(db, k["tabelle"], k["uid"], k.get("verloren"))
        k["erledigt"] = True
        k["wiederhergestellt"] = bool(wiederherstellen)
        db._einstellung_schreiben(KONFLIKTE, alle)
    return True


def _zeile_setzen(db, tabelle, u, daten):
    """Werte einer geteilten Zeile (Form wie in der Datei: Verweise als Kennung) hier eintragen; None = löschen."""
    con = db.con
    if tabelle == EINST:
        if daten is not None:
            con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES (?, ?)", (u, daten["wert"]))
        return
    t = GETEILT_NAME.get(tabelle)
    if t is None:
        return
    hier = {uu: i for i, uu in _uid_karte(con, tabelle).items()}.get(u)
    if daten is None:
        if hier is not None:
            con.execute(f'DELETE FROM "{tabelle}" WHERE id=?', (hier,))
        return
    werte = dict(daten)
    for feld, ziel in ID_VERWEISE.get(tabelle, {}).items():
        if werte.get(feld) is not None:
            werte[feld] = {uu: i for i, uu in _uid_karte(con, ziel).items()}.get(werte[feld])
    _zeile_schreiben(db, t, hier, werte, u)


# ------------------------------------------------------------------ Wer arbeitet woran, Übergabe, Anfrage (2, 3)
def offen_bei(db, nummer, jetzt_=None):
    """Hat ein Kollege das Angebot gerade geöffnet? (Kürzel, seit) oder None. Gilt nur, solange seine Datei frisch ist
    (FRISCH_MIN nach seinem letzten Schreiben; das Programm schreibt bei geöffneten Angeboten regelmäßig)."""
    return kollegen_offen(db, jetzt_).get(nummer) if nummer else None


def kollegen_offen(db, jetzt_=None):
    """{Nummer: (Kürzel, seit)} der Angebote, die Kollegen gerade geöffnet haben (nur frische Dateien)."""
    jetzt_ = jetzt_ or datetime.datetime.now()
    ich = kuerzel(db)
    out = {}
    for k, m in (db.einstellung("teilen_mitarbeiter") or {}).items():
        if k == ich or not m.get("offen"):
            continue
        try:
            stand = datetime.datetime.fromisoformat(m.get("stand") or "")
        except ValueError:
            continue
        if jetzt_ - stand <= datetime.timedelta(minutes=FRISCH_MIN):
            for nummer, seit in m["offen"].items():
                out.setdefault(nummer, (k, seit))
    return out


def _vorgaenge(db):
    return dict(db.einstellung(VORGAENGE) or {})


def _vorgang_neu(db, **werte):
    v = _vorgaenge(db)
    i = uuid.uuid4().hex
    v[i] = dict(werte, zeit=datetime.datetime.now().isoformat(timespec="seconds"))
    db._einstellung_schreiben(VORGAENGE, v)
    return i


def vorgang_offen(db, nummer, art):
    """Eigener noch nicht umgesetzter Vorgang (Übergabe oder Anfrage) zu einer Nummer: dict mit id oder None."""
    for i, v in _vorgaenge(db).items():
        if v.get("nummer") == nummer and v.get("art") == art:
            return dict(v, id=i)
    return None


def kollegen(db):
    """{Kürzel: Name} der anderen Mitarbeiter (aus dem letzten Lesen)."""
    ich = kuerzel(db)
    return {k: (m or {}).get("name") or "" for k, m in sorted((db.einstellung("teilen_mitarbeiter") or {}).items())
            if k != ich}


def uebergeben(db, angebot_id, an, notiz="", bezug=None):
    """Eigenes Angebot an den Kollegen an übergeben: hier gleich nur noch zum Ansehen (fremd = an), der Kollege
    übernimmt es beim nächsten Abgleich als eigenes. bezug: beantwortete Anfrage. Ergebnis: Kennung des Vorgangs."""
    from . import nummern
    a = db.angebot(angebot_id) or {}
    an = kuerzel_sauber(an)
    if not a:
        raise TeilenFehler("Das Angebot gibt es nicht mehr.")
    if a.get("fremd"):
        raise TeilenFehler(f"Angebot {a['nummer']} gehört {a['fremd']}: übergeben kann nur der Bearbeiter.")
    if not an or an == kuerzel(db):
        raise TeilenFehler("Bitte einen Kollegen wählen.")
    if nummern.vorlaeufig(a.get("nummer")):
        raise TeilenFehler(f"Angebot {a['nummer']} hat noch eine vorläufige Nummer. Erst abgleichen, wenn der "
                           "gemeinsame Ordner erreichbar ist, dann übergeben.")
    with db.con:
        db.con.execute("UPDATE angebote SET fremd=?, fremd_stand=NULL, bearbeiter=? WHERE id=?", (an, an, angebot_id))
        return _vorgang_neu(db, art=UEBERGABE, nummer=a["nummer"], an=an, notiz=notiz or "", bezug=bezug)


def zuruecknehmen(db, angebot_id):
    """Übergabe, die der Kollege noch nicht übernommen hat, zurücknehmen: das Angebot ist wieder eigenes.
    Ergebnis: True, wenn eine offene Übergabe zurückgenommen wurde."""
    a = db.angebot(angebot_id) or {}
    v = vorgang_offen(db, a.get("nummer"), UEBERGABE)
    if v is None or a.get("fremd") != v.get("an"):
        return False
    with db.con:
        db.con.execute("UPDATE angebote SET fremd=NULL, fremd_stand=NULL, bearbeiter=? WHERE id=?",
                       (kuerzel(db), angebot_id))
        alle = _vorgaenge(db)
        alle.pop(v["id"], None)
        db._einstellung_schreiben(VORGAENGE, alle)
    return True


def anfragen(db, angebot_id, notiz=""):
    """Angebot eines Kollegen übernehmen wollen: Anfrage an den Bearbeiter (der wird beim Abgleich gefragt).
    Ergebnis: Kennung der Anfrage (eine schon offene bleibt)."""
    a = db.angebot(angebot_id) or {}
    if not a.get("fremd"):
        raise TeilenFehler("Das Angebot gehört schon Ihnen.")
    offen = vorgang_offen(db, a["nummer"], ANFRAGE)
    if offen:
        return offen["id"]
    with db.con:
        return _vorgang_neu(db, art=ANFRAGE, nummer=a["nummer"], an=a["fremd"], notiz=notiz or "")


def beantworten(db, anfrage, ja, notiz=""):
    """Anfrage eines Kollegen (aus bericht['anfragen']) beantworten: ja = Angebot übergeben, sonst ablehnen."""
    if ja:
        i = uebergeben(db, anfrage["angebot_id"], anfrage["von"], notiz or "auf Ihre Anfrage", bezug=anfrage["id"])
    else:
        with db.con:
            i = _vorgang_neu(db, art=ABGELEHNT, nummer=anfrage["nummer"], an=anfrage["von"], notiz=notiz or "",
                             bezug=anfrage["id"])
    with db.con:
        _erledigt(db, anfrage["id"], anfrage["von"])
    return i


def _erledigt(db, vid, von):
    e = dict(db.einstellung(ERLEDIGT) or {})
    e[vid] = von
    db._einstellung_schreiben(ERLEDIGT, e)


def _vorgaenge_schreiben(db, sc, karte):
    """Eigene offene Vorgänge in die geteilte Datei (Übergaben mit Inhalt und Netzen). Ergebnis: Nummern der
    übergebenen Angebote (deren Netze bleiben in der Datei)."""
    sc.execute("DELETE FROM vorgaenge")
    nummern_ = set()
    ids = dict(db.con.execute("SELECT nummer, id FROM angebote").fetchall())
    for i, v in _vorgaenge(db).items():
        inhalt = None
        if v.get("art") == UEBERGABE:
            aid = ids.get(v.get("nummer"))
            if aid is None:
                continue
            inh, netze = angebot_inhalt(db.con, aid, karte)
            inhalt = json.dumps(inh, ensure_ascii=False)
            sc.execute("DELETE FROM netze WHERE nummer=?", (v["nummer"],))
            sc.executemany("INSERT INTO netze (nummer, idx, daten) VALUES (?, ?, ?)",
                           [(v["nummer"], idx, d) for idx, d in netze.items()])
            nummern_.add(v["nummer"])
        sc.execute("INSERT INTO vorgaenge (id, art, nummer, an, zeit, notiz, bezug, inhalt) VALUES (?, ?, ?, ?, ?, ?, "
                   "?, ?)", (i, v.get("art"), v.get("nummer"), v.get("an"), v.get("zeit"), v.get("notiz"),
                             v.get("bezug"), inhalt))
    return nummern_


def _vorgaenge_lesen(db, gelesen, vorgaenge, angebote, bericht, karte_id):
    """Vorgänge der anderen umsetzen und eigene aufräumen (in lesen). Ergebnis: Nummern eigener Übergaben, die der
    Empfänger noch nicht übernommen hat (diese Angebote bleiben hier, obwohl sie in seiner Datei noch fehlen)."""
    con, ich = db.con, kuerzel(db)
    eigene = _vorgaenge(db)
    erledigt = dict(db.einstellung(ERLEDIGT) or {})
    hier = {r[1]: (r[0], r[2]) for r in con.execute("SELECT id, nummer, fremd FROM angebote")}
    for k2, liste in vorgaenge.items():
        for v in liste:
            if v.get("an") != ich or v["id"] in erledigt:
                continue
            nummer, a = v.get("nummer"), hier.get(v.get("nummer"))
            if v["art"] == UEBERGABE:
                if a is None or a[1] is not None:       # noch nicht eigenes: übernehmen
                    fc = sqlite3.connect(gelesen[k2])
                    try:
                        r = fc.execute("SELECT inhalt FROM vorgaenge WHERE id=?", (v["id"],)).fetchone()
                        netze = {i: bytes(d) for i, d in
                                 fc.execute("SELECT idx, daten FROM netze WHERE nummer=?", (nummer,))}
                    finally:
                        fc.close()
                    if not r or not r[0]:
                        continue
                    i = angebot_einsetzen(con, json.loads(r[0]), netze, None, None, a[0] if a else None, karte_id)
                    con.execute("UPDATE angebote SET bearbeiter=? WHERE id=?", (ich, i))
                    hier[nummer] = (i, None)
                    bericht["uebernommen"].append(dict(nummer=nummer, von=k2, notiz=v.get("notiz") or "", id=i))
                    bericht["geaenderte_ids"].append(i)
                for vid, e in list(eigene.items()):     # eigene Anfrage dazu ist damit erledigt
                    if e.get("art") == ANFRAGE and e.get("nummer") == nummer:
                        eigene.pop(vid)
                erledigt[v["id"]] = k2
            elif v["art"] == ANFRAGE:
                if a is not None and a[1] is None:
                    if vorgang_offen(db, nummer, UEBERGABE) is None:
                        bericht["anfragen"].append(dict(v, angebot_id=a[0]))
                    continue                            # gefragt wird bis zur Antwort bei jedem Abgleich
                erledigt[v["id"]] = k2                  # gehört nicht (mehr) mir: nichts zu tun
            elif v["art"] == ABGELEHNT:
                if v.get("bezug") in eigene:
                    eigene.pop(v["bezug"])
                    bericht["abgelehnt"].append(dict(nummer=nummer, von=k2, notiz=v.get("notiz") or ""))
                erledigt[v["id"]] = k2
    unterwegs = set()
    for vid, e in list(eigene.items()):
        an = e.get("an")
        if an not in gelesen:
            if e.get("art") == UEBERGABE:
                unterwegs.add(e.get("nummer"))
            continue
        ids_dort = {v["id"] for v in vorgaenge.get(an, ())}
        if e.get("art") == UEBERGABE:
            if e.get("nummer") in angebote.get(an, {}):
                eigene.pop(vid)                         # übernommen
            else:
                unterwegs.add(e.get("nummer"))
        elif e.get("art") == ANFRAGE:
            if e.get("nummer") not in angebote.get(an, {}):
                eigene.pop(vid)                         # gehört dem Kollegen nicht mehr
        elif e.get("art") == ABGELEHNT and e.get("bezug") not in ids_dort:
            eigene.pop(vid)                             # Kollege hat die Antwort gesehen
    for vid, k2 in list(erledigt.items()):              # nur Vorgänge merken, die es dort noch gibt
        if k2 in vorgaenge and vid not in {v["id"] for v in vorgaenge[k2]}:
            erledigt.pop(vid)
    db._einstellung_schreiben(VORGAENGE, eigene)
    db._einstellung_schreiben(ERLEDIGT, erledigt)
    return unterwegs


def dateien_stand(db):
    """Größe und Zeit der Dateien der Kollegen: unverändert = nichts Neues zu lesen."""
    out = []
    for k, p in andere_dateien(db).items():
        st = p.stat()
        out.append((k, st.st_size, st.st_mtime_ns))
    return tuple(out)
