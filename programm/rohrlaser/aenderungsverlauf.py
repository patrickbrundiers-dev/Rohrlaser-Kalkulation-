"""Änderungsverlauf im gemeinsamen Ordner (Patrick 01.11.2026, Paket D): wer hat wann welches Feld eines Angebots oder
der Stammdaten von welchem auf welchen Wert geändert. Ohne Qt.

Ablauf: Jeder Arbeitsplatz merkt sich je Angebot und Stammdatenzeile den zuletzt bekannten Stand (Schnappschuss). Beim
Abgleich (lesen und schreiben) vergleicht er die eigenen Änderungen damit und trägt je geändertem Feld einen Eintrag
mit seinem Kürzel ein. Was ein Abgleich von den Kollegen einträgt, übernimmt er still in den Schnappschuss; deren
Einträge kommen aus ihren Dateien (Tabelle verlauf in der Hauptdatei). Einträge älter als TAGE fallen weg (Frage 3a).
Alte Werte zurückholen (Frage 4a): jeder für seine eigenen Angebote und seine eigenen Stammdaten-Änderungen, der Admin
auch für die Stammdaten-Änderungen der Kollegen."""
import datetime
import hashlib
import json
import uuid
from . import db_verbindung

TABELLE = "teilen_verlauf"          # lokal: alle bekannten Einträge (eigene und die der Kollegen)
STAND = "teilen_schnappschuss"      # lokal: zuletzt bekannter Stand je (Tabelle, Kennung)
START = ("_start", "")              # Zeile im Schnappschuss: seit wann der Verlauf läuft
TAGE = 365
ANGEBOT = "angebote"
KOPF, POS, STAFFELN = "kopf", "pos:", "staffeln"
# Felder des Angebots, die das Programm selbst setzt (Ergebnis, Zeitstempel, Kennung): nicht im Verlauf
OHNE_KOPF = {"uid", "ergebnis", "angelegt", "geaendert", "optimiert_am", "optimiert_erstmals", "optimiert_hand"}
OHNE_POS = {"uid", "nr"}
SPALTEN = ("id", "zeit", "wer", "tabelle", "uid", "bezug", "ziel", "feld", "art", "alt", "neu")
NEU, GEAENDERT, GELOESCHT = "neu", "geaendert", "geloescht"
ART_TEXT = {NEU: "neu", GEAENDERT: "geändert", GELOESCHT: "gelöscht"}


def einrichten(con):
    con.execute(f"CREATE TABLE IF NOT EXISTS {TABELLE} (id TEXT PRIMARY KEY, zeit TEXT, wer TEXT, tabelle TEXT, "
                "uid TEXT, bezug TEXT, ziel TEXT, feld TEXT, art TEXT, alt TEXT, neu TEXT)")
    con.execute(f"CREATE INDEX IF NOT EXISTS {TABELLE}_zeile ON {TABELLE} (tabelle, uid)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {STAND} (tabelle TEXT, uid TEXT, hash TEXT, daten TEXT, "
                "PRIMARY KEY (tabelle, uid))")
    grenze = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=TAGE)).isoformat()
    con.execute(f"DELETE FROM {TABELLE} WHERE zeit < ?", (grenze,))


def _hash(daten):
    return hashlib.sha1(json.dumps(daten, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _text(wert):
    return None if wert is None else json.dumps(wert, ensure_ascii=False, default=str)


def flach_angebot(inhalt):
    """Angebot (teilen.angebot_inhalt) als {"ziel|feld": Wert}: Kopf, je Position (über ihre Kennung) und Staffeln."""
    out = {}
    for f, v in (inhalt.get("kopf") or {}).items():
        if f not in OHNE_KOPF:
            out[f"{KOPF}|{f}"] = v
    for i, p in enumerate(inhalt.get("positionen") or ()):
        ziel = POS + str(p.get("uid") or f"#{i + 1}")
        out[f"{ziel}|"] = p.get("pos") or i + 1         # Merker: Position da (Wert = Pos.-Nr. für die Anzeige)
        for f, v in p.items():
            if f not in OHNE_POS:
                out[f"{ziel}|{f}"] = v
    st = [inhalt.get("stufen") or [], inhalt.get("staffeln") or []]
    if st != [[], []]:
        out[f"{STAFFELN}|"] = _hash(st)
    return out


def _stand(con, tabelle, uid):
    r = con.execute(f"SELECT daten FROM {STAND} WHERE tabelle=? AND uid=?", (tabelle, uid)).fetchone()
    return json.loads(r[0]) if r and r[0] is not None else None


def _stand_setzen(con, tabelle, uid, daten):
    if daten is None:
        con.execute(f"DELETE FROM {STAND} WHERE tabelle=? AND uid=?", (tabelle, uid))
    else:
        con.execute(f"INSERT INTO {STAND} (tabelle, uid, hash, daten) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (tabelle, uid) DO UPDATE SET hash=excluded.hash, daten=excluded.daten",
                    (tabelle, uid, _hash(daten), json.dumps(daten, ensure_ascii=False, default=str)))


def _start(con):
    r = con.execute(f"SELECT daten FROM {STAND} WHERE tabelle=? AND uid=?", START).fetchone()
    return json.loads(r[0]) if r else None


def _eintrag(con, zeit, wer, tabelle, uid, bezug, ziel, feld, art, alt=None, neu=None):
    con.execute(f"INSERT INTO {TABELLE} ({', '.join(SPALTEN)}) VALUES ({', '.join('?' * len(SPALTEN))})",
                (uuid.uuid4().hex, zeit, wer, tabelle, uid, bezug, ziel, feld, art, _text(alt), _text(neu)))


def _zeit(versatz=0):
    t = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=versatz or 0)
    return t.isoformat(timespec="seconds")


def _bezug_stamm(tabelle, daten):
    from . import teilen
    if tabelle == teilen.EINST:
        from .stammdaten import EINSTELLUNG
        return "Einstellung: " + (EINSTELLUNG[daten].titel if isinstance(daten, str) and daten in EINSTELLUNG
                                   else str(daten))
    return teilen._bezeichnung(tabelle, daten)


def _angebote(con, ids):
    """{uid: (Nummer, flacher Inhalt)} der Angebote mit den IDs."""
    from . import teilen
    out = {}
    karte = teilen._uid_karte(con, "zukauf_artikel")
    for i in ids:
        r = con.execute("SELECT uid, nummer FROM angebote WHERE id=?", (i,)).fetchone()
        if r and r[0]:
            out[r[0]] = (r[1], flach_angebot(teilen._inhalt_fuer_verlauf(con, i, karte)[0]))
    return out


def erfassen(con, wer, lokal, angebot_ids, versatz=0):
    """Eigene Änderungen seit dem letzten Abgleich eintragen. lokal: teilen.lokale_zeilen (Stammdaten und gemeinsame
    Einstellungen); angebot_ids: geänderte eigene Angebote. Beim ersten Mal (noch kein Stand) nur den Stand merken.
    Ergebnis: Anzahl neuer Einträge."""
    zeit = _zeit(versatz)
    start = _start(con)
    if start is None:
        con.execute(f"DELETE FROM {STAND}")
        for (t, u), daten in lokal.items():
            _stand_setzen(con, t, u, daten)
        _stand_setzen(con, *START, zeit)
        for u, (_n, flach) in _angebote(con, angebot_ids).items():
            _stand_setzen(con, ANGEBOT, u, flach)
        return 0
    n = 0
    alt_hash = {(t, u): h for t, u, h in con.execute(f"SELECT tabelle, uid, hash FROM {STAND} WHERE tabelle<>? "
                                                      "AND tabelle<>?", (ANGEBOT, START[0]))}
    for (t, u), daten in lokal.items():
        h = alt_hash.pop((t, u), None)
        if h == _hash(daten):
            continue
        alt = _stand(con, t, u) if h is not None else None
        if alt is None and t == _einst():       # Einstellung bisher auf der Vorgabe
            from .stammdaten import EINSTELLUNG
            e = EINSTELLUNG.get(u)
            alt = {"wert": json.dumps(e.vorgabe, ensure_ascii=False) if e is not None else None}
        if alt is None:
            _eintrag(con, zeit, wer, t, u, _bezug_stamm(t, daten if t != _einst() else u), "", "", NEU)
            n += 1
        else:
            for f in sorted(set(alt) | set(daten)):
                if alt.get(f) != daten.get(f):
                    va, vn = alt.get(f), daten.get(f)
                    if t == _einst():           # Einstellungen stehen als JSON-Text: Werte selbst vermerken
                        va, vn = wert(va), wert(vn)
                    _eintrag(con, zeit, wer, t, u, _bezug_stamm(t, daten if t != _einst() else u), "", f,
                             GEAENDERT, va, vn)
                    n += 1
        _stand_setzen(con, t, u, daten)
    from . import teilen
    for (t, u) in alt_hash:
        if t == teilen.EINST:
            continue                # Einstellungen werden nicht gelöscht, nur geändert
        alt = _stand(con, t, u)
        _eintrag(con, zeit, wer, t, u, _bezug_stamm(t, alt), "", "", GELOESCHT)
        _stand_setzen(con, t, u, None)
        n += 1
    for u, (nummer, flach) in _angebote(con, angebot_ids).items():
        alt = _stand(con, ANGEBOT, u)
        if alt is None:
            r = con.execute("SELECT angelegt FROM angebote WHERE uid=?", (u,)).fetchone()
            if r and str(r[0] or "") >= _lokal(start)[:19]:
                _eintrag(con, zeit, wer, ANGEBOT, u, nummer, KOPF, "", NEU)
                n += 1
        elif alt != flach:
            n += _angebot_vergleichen(con, zeit, wer, u, nummer, alt, flach)
        _stand_setzen(con, ANGEBOT, u, flach)
    return n


def _einst():
    from . import teilen
    return teilen.EINST


def _lokal(utc_text):
    """UTC-Zeit (ISO) als lokale Zeit ohne Zone (wie angebote.angelegt)."""
    try:
        t = datetime.datetime.fromisoformat(utc_text)
    except (TypeError, ValueError):
        return ""
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")


def _angebot_vergleichen(con, zeit, wer, u, nummer, alt, neu):
    n = 0
    ziele_alt = {k.split("|", 1)[0] for k in alt if k.startswith(POS) and k.endswith("|")}
    ziele_neu = {k.split("|", 1)[0] for k in neu if k.startswith(POS) and k.endswith("|")}
    for ziel in sorted(ziele_neu - ziele_alt):
        _eintrag(con, zeit, wer, ANGEBOT, u, nummer, ziel, "", NEU, None, _pos_name(neu, ziel))
        n += 1
    for ziel in sorted(ziele_alt - ziele_neu):
        _eintrag(con, zeit, wer, ANGEBOT, u, nummer, ziel, "", GELOESCHT, _pos_name(alt, ziel), None)
        n += 1
    for k in sorted(set(alt) | set(neu)):
        ziel, _, feld = k.partition("|")
        if not feld:
            if ziel == STAFFELN and alt.get(k) != neu.get(k):
                _eintrag(con, zeit, wer, ANGEBOT, u, nummer, STAFFELN, "", GEAENDERT)
                n += 1
            continue
        if ziel.startswith(POS) and (ziel not in ziele_alt or ziel not in ziele_neu):
            continue
        if alt.get(k) != neu.get(k):
            _eintrag(con, zeit, wer, ANGEBOT, u, nummer, ziel, feld, GEAENDERT, alt.get(k), neu.get(k))
            n += 1
    return n


def _pos_name(flach, ziel):
    teile = [f"Pos. {flach.get(ziel + '|')}"]
    for f in ("artikel", "bezeichnung"):
        if flach.get(f"{ziel}|{f}"):
            teile.append(str(flach[f"{ziel}|{f}"]))
    return " ".join(teile)


def angleichen(con, lokal=None, angebot_ids=()):
    """Was ein Abgleich von den Kollegen eingetragen hat, still in den Stand übernehmen (ohne Eintrag)."""
    if _start(con) is None:
        return
    if lokal is not None:
        alt_hash = {(t, u): h for t, u, h in con.execute(f"SELECT tabelle, uid, hash FROM {STAND} WHERE tabelle<>? "
                                                          "AND tabelle<>?", (ANGEBOT, START[0]))}
        for (t, u), daten in lokal.items():
            if alt_hash.pop((t, u), None) != _hash(daten):
                _stand_setzen(con, t, u, daten)
        for (t, u) in alt_hash:
            if t != _einst():
                _stand_setzen(con, t, u, None)
    for u, (_n, flach) in _angebote(con, angebot_ids).items():
        _stand_setzen(con, ANGEBOT, u, flach)


# ------------------------------------------------------------------ Austausch über die Hauptdatei
def fuer_datei(con, wer):
    """Eigene Einträge (Kürzel wer) für die Hauptdatei im gemeinsamen Ordner."""
    return con.execute(f"SELECT {', '.join(SPALTEN)} FROM {TABELLE} WHERE wer=?", (wer,)).fetchall()


def datei_anlegen(sc):
    sc.execute(f"CREATE TABLE IF NOT EXISTS verlauf ({', '.join(s + ' TEXT' for s in SPALTEN)}, PRIMARY KEY (id))")


def in_datei(sc, zeilen):
    datei_anlegen(sc)
    sc.execute("DELETE FROM verlauf")
    sc.executemany(f"INSERT OR IGNORE INTO verlauf ({', '.join(SPALTEN)}) VALUES ({', '.join('?' * len(SPALTEN))})",
                   zeilen)


def aus_datei(con, fc, wer):
    """Einträge eines Kollegen (Kürzel wer) aus seiner Hauptdatei übernehmen. Ergebnis: Anzahl neuer Einträge."""
    if not fc.execute("SELECT 1 FROM sqlite_master WHERE name='verlauf'").fetchone():
        return 0
    zeilen = [z for z in fc.execute(f"SELECT {', '.join(SPALTEN)} FROM verlauf WHERE wer=?", (wer,))]
    vorher = con.total_changes
    con.executemany(f"INSERT OR IGNORE INTO {TABELLE} ({', '.join(SPALTEN)}) VALUES "
                    f"({', '.join('?' * len(SPALTEN))})", zeilen)
    return con.total_changes - vorher


# ------------------------------------------------------------------ Lesen und zurückholen
def eintraege(con, tabelle=None, uid=None, ohne_angebote=False, text="", grenze=2000):
    """Einträge, neueste zuerst, als dicts. tabelle/uid: nur diese Zeile (z. B. ein Angebot); ohne_angebote: nur
    Stammdaten und Einstellungen (D2); text: Suche in Bezug, Feld, Kürzel und Werten."""
    bed, werte = [], []
    if tabelle:
        bed.append("tabelle=?")
        werte.append(tabelle)
    if uid:
        bed.append("uid=?")
        werte.append(uid)
    if ohne_angebote:
        bed.append("tabelle<>?")
        werte.append(ANGEBOT)
    if text:
        bed.append("(bezug LIKE ? OR feld LIKE ? OR wer LIKE ? OR alt LIKE ? OR neu LIKE ?)")
        werte += [f"%{text}%"] * 5
    sql = f"SELECT {', '.join(SPALTEN)} FROM {TABELLE}"
    if bed:
        sql += " WHERE " + " AND ".join(bed)
    folge = "rowid" if db_verbindung.ist_sqlite(con) else "id"       # gleiche Zeit: SQLite nach Einfügefolge
    cur = con.execute(sql + f" ORDER BY zeit DESC, {folge} DESC LIMIT ?", werte + [grenze])
    return [dict(zip(SPALTEN, r)) for r in cur]


def feld_titel(e):
    """Lesbarer Feldname eines Eintrags (Titel aus Angebotskopf, Position oder Stammdaten)."""
    from . import teilen
    feld, ziel = e.get("feld") or "", e.get("ziel") or ""
    if e.get("tabelle") == ANGEBOT:
        from .angebot import KOPF as KOPF_FELDER, POSITIONEN
        if ziel == STAFFELN:
            return "Staffeln"
        if ziel.startswith(POS):
            if not feld:
                return "Position"
            titel = {f.name: f.titel for f in POSITIONEN.felder}
            return titel.get(feld, feld)
        if not feld:
            return "Angebot"
        return {f.name: f.titel for f in KOPF_FELDER}.get(feld, feld)
    if e.get("tabelle") == teilen.EINST:
        return "Wert"
    t = teilen.GETEILT_NAME.get(e.get("tabelle"))
    if t is not None and feld:
        try:
            return t.feld(feld).titel
        except StopIteration:
            return feld
    return feld or "Zeile"


def wert(text):
    """Gespeicherter Wert (JSON-Text) zurück in Python."""
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def wert_text(text, laenge=80):
    w = wert(text)
    if w is None or w == "":
        return "–"
    if isinstance(w, bool):
        s = "ja" if w else "nein"
    elif isinstance(w, float):
        s = f"{w:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    else:
        s = str(w)
    return s if len(s) <= laenge else s[:laenge - 1] + "…"


def darf_zurueckholen(db, e, ich=None, admin=None):
    """(ja, Grund): alten Wert eines Eintrags zurückholen (Frage 4a)."""
    from . import admin_schutz, teilen
    ich = ich if ich is not None else teilen.kuerzel(db)
    admin = admin if admin is not None else admin_schutz.ist_admin(db)
    if e.get("art") != GEAENDERT or not e.get("feld"):
        return False, "Nur geänderte Felder lassen sich zurückholen (nicht neue oder gelöschte Zeilen, keine Staffeln)."
    if e.get("tabelle") == ANGEBOT:
        r = db.con.execute("SELECT fremd FROM angebote WHERE uid=?", (e.get("uid"),)).fetchone()
        if r is None:
            return False, "Das Angebot gibt es hier nicht mehr."
        if r[0]:
            return False, f"Das Angebot bearbeitet {r[0]}: nur der Bearbeiter kann alte Werte zurückholen."
        if e.get("ziel", "").startswith(POS):
            p = e["ziel"][len(POS):]
            if not db.con.execute("SELECT 1 FROM positionen WHERE uid=?", (p,)).fetchone():
                return False, "Die Position gibt es nicht mehr."
        return True, ""
    if e.get("tabelle") in teilen.ID_VERWEISE and e.get("feld") in teilen.ID_VERWEISE[e["tabelle"]]:
        return False, "Verweise auf andere Zeilen lassen sich nicht zurückholen."
    if e.get("tabelle") in admin_schutz.tabellen_geschuetzt(db) and not admin:
        return False, "Diese Stammdaten ändert nur der Admin."
    if e.get("tabelle") == teilen.EINST and e.get("uid") in admin_schutz.einstellungen_geschuetzt(db) and not admin:
        return False, "Diese Einstellung ändert nur der Admin."
    if e.get("wer") != ich and not admin:
        return False, f"Die Änderung hat {e.get('wer')} gemacht: nur er selbst oder der Admin kann sie zurückholen."
    if e.get("tabelle") != teilen.EINST and not db.con.execute(
            f'SELECT 1 FROM "{e["tabelle"]}" WHERE uid=?', (e.get("uid"),)).fetchone():
        return False, "Die Zeile gibt es nicht mehr."
    return True, ""


def zurueckholen(db, e):
    """Alten Wert des Eintrags e wieder eintragen. Der nächste Abgleich vermerkt das als neue Änderung (mit dem
    eigenen Kürzel) und gibt es an die Kollegen weiter."""
    from . import teilen
    ja, grund = darf_zurueckholen(db, e)
    if not ja:
        raise PermissionError(grund)
    alt, feld, con = wert(e.get("alt")), e["feld"], db.con
    with con:
        if e["tabelle"] == ANGEBOT:
            if e["ziel"].startswith(POS):
                con.execute(f'UPDATE positionen SET "{_spalte(con, "positionen", feld)}"=? WHERE uid=?',
                            (alt, e["ziel"][len(POS):]))
            else:
                con.execute(f'UPDATE angebote SET "{_spalte(con, "angebote", feld)}"=? WHERE uid=?', (alt, e["uid"]))
        elif e["tabelle"] == teilen.EINST:
            con.execute(db_verbindung.EINSTELLUNG_SETZEN,
                        (e["uid"], json.dumps(alt, ensure_ascii=False)))
        else:
            con.execute(f'UPDATE "{e["tabelle"]}" SET "{_spalte(con, e["tabelle"], feld)}"=? WHERE uid=?',
                        (alt, e["uid"]))
    if hasattr(db, "cache_leeren"):
        db.cache_leeren()
    return True


def _spalte(con, tabelle, feld):
    if feld not in set(db_verbindung.spalten(con, tabelle)):
        raise PermissionError(f"Das Feld {feld} gibt es in dieser Programmversion nicht.")
    return feld
