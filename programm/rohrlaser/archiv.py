"""Archiv alter Angebote, eine Datei je Jahr (Prüfung „Datenbank bei vielen Angeboten“, Vorschlag 5b, 28.10.2026).

Eigene Angebote, deren Angebotsdatum mindestens `archiv_jahre` volle Jahre zurückliegt (Einstellung, Vorgabe 2), wandern
mit Positionen, 3D-Modellen, Staffeln, STEP-Protokoll und Fertigungsstatus in Daten/Archiv/Rohrlaser_Archiv_<Jahr>.db.
Die Datendatei bleibt so klein und schnell (Angebotsliste, Wiederholteile, Sicherung, Abgleich); das Archiv wird nur
bei Bedarf gelesen: suchen() über alle Jahre, zurueckholen() legt ein Angebot wieder in die Datendatei (neue IDs,
gleiche Nummer). Nicht archiviert werden Angebote der Kollegen (die archiviert der Kollege selbst) und Angebote mit
Lagerauftrag oder Reservierung. Archivieren startet nur von Hand (Datei → Alte Angebote archivieren …), nach einer
Sicherung; die Archivdateien gehören in die Sicherung des Datenordners.
"""
import datetime
import json
import shutil
import sqlite3
from pathlib import Path

PRAEFIX, ENDUNG = "Rohrlaser_Archiv_", ".db"
JAHRE_VORGABE = 2
# Tabellen je Angebot (Spalte angebot_id), netze über die Positionen; auftrag_status = Fertigungsstatus (fertigung.py)
JE_ANGEBOT = ("positionen", "staffel_stufen", "staffeln", "step_protokoll", "auftrag_status")


def ordner(db):
    return Path(db.pfad).parent / "Archiv"


def datei(db, jahr):
    return ordner(db) / f"{PRAEFIX}{int(jahr)}{ENDUNG}"


def dateien(db):
    """{Jahr: Pfad} der vorhandenen Archivdateien."""
    o = ordner(db)
    if not o.is_dir():
        return {}
    out = {}
    for p in o.glob(f"{PRAEFIX}*{ENDUNG}"):
        jahr = p.name[len(PRAEFIX):-len(ENDUNG)]
        if jahr.isdigit():
            out[int(jahr)] = p
    return dict(sorted(out.items()))


def jahre_einstellung(db):
    try:
        return max(1, int(db.einstellung("archiv_jahre") or JAHRE_VORGABE))
    except (TypeError, ValueError):
        return JAHRE_VORGABE


def bis_jahr(db, heute=None):
    """Angebote bis zu diesem Jahr (einschließlich) kommen ins Archiv."""
    return (heute or datetime.date.today()).year - jahre_einstellung(db)


def kandidaten(db, heute=None, offen=()):
    """{Jahr: [Angebots-ID]} der Angebote, die archiviert werden können. offen: IDs geöffneter Angebote (bleiben)."""
    tabellen = {r[0] for r in db.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    sperre = set()
    if "lager_auftraege" in tabellen:
        sperre |= {r[0] for r in db.con.execute("SELECT angebot_id FROM lager_auftraege")}
    if "lager_reservierung" in tabellen:
        sperre |= {r[0] for r in db.con.execute("SELECT angebot_id FROM lager_reservierung WHERE angebot_id IS NOT NULL "
                                                "AND status='reserviert'")}
    grenze = bis_jahr(db, heute)
    out = {}
    for i, datum in db.con.execute("SELECT id, datum FROM angebote WHERE COALESCE(fremd, '')='' ORDER BY id"):
        jahr = str(datum or "")[:4]
        if not jahr.isdigit() or int(jahr) > grenze or i in sperre or i in offen:
            continue
        out.setdefault(int(jahr), []).append(i)
    return dict(sorted(out.items()))


def _tabellen_anlegen(quelle, ziel_schema):
    """Tabellen und Indizes der Angebote im angehängten Archiv anlegen (gleicher Aufbau wie die Datendatei)."""
    namen = ("angebote", "netze") + JE_ANGEBOT
    for typ, name, tabelle, sql in quelle.execute("SELECT type, name, tbl_name, sql FROM main.sqlite_master "
                                                  "WHERE sql IS NOT NULL AND type IN ('table', 'index')"):
        if tabelle not in namen:
            continue
        sql = sql.replace(f"CREATE TABLE {name}", f"CREATE TABLE IF NOT EXISTS {ziel_schema}.{name}", 1)
        sql = sql.replace(f'CREATE TABLE "{name}"', f'CREATE TABLE IF NOT EXISTS {ziel_schema}."{name}"', 1)
        sql = sql.replace(f"CREATE TABLE IF NOT EXISTS {name}", f"CREATE TABLE IF NOT EXISTS {ziel_schema}.{name}", 1)
        sql = sql.replace(f'CREATE TABLE IF NOT EXISTS "{name}"', f'CREATE TABLE IF NOT EXISTS {ziel_schema}."{name}"', 1)
        for art in ("CREATE INDEX", "CREATE UNIQUE INDEX"):
            for alt in (f"{art} IF NOT EXISTS {name}", f'{art} IF NOT EXISTS "{name}"', f"{art} {name}", f'{art} "{name}"'):
                if sql.startswith(alt):
                    sql = f'{art} IF NOT EXISTS {ziel_schema}."{name}"' + sql[len(alt):]
                    break
        quelle.execute(sql)
    quelle.execute(f"PRAGMA {ziel_schema}.user_version={quelle.execute('PRAGMA main.user_version').fetchone()[0]}")


def _spalten(con, schema, tabelle):
    return [r[1] for r in con.execute(f'PRAGMA {schema}.table_info("{tabelle}")')]


def _kopieren(con, von, nach, tabelle, bedingung, werte):
    """Zeilen mit allen Spalten, die es in beiden gibt (ältere Archive bekommen neue Spalten ergänzt)."""
    ziel = _spalten(con, nach, tabelle)
    for s in _spalten(con, von, tabelle):
        if s not in ziel:
            con.execute(f'ALTER TABLE {nach}."{tabelle}" ADD COLUMN "{s}"')
            ziel.append(s)
    gemeinsam = [s for s in _spalten(con, von, tabelle) if s in ziel]
    liste = ", ".join(f'"{s}"' for s in gemeinsam)
    con.execute(f'INSERT INTO {nach}."{tabelle}" ({liste}) SELECT {liste} FROM {von}."{tabelle}" WHERE {bedingung}',
                werte)


def archivieren(db, ids_je_jahr, fortschritt=None):
    """Angebote ins Archiv ihres Jahres verschieben (je Jahr eine Transaktion). Ergebnis: {Jahr: Anzahl}."""
    ordner(db).mkdir(parents=True, exist_ok=True)
    con = db.con
    ergebnis = {}
    for jahr, ids in ids_je_jahr.items():
        if not ids:
            continue
        con.execute("ATTACH DATABASE ? AS archiv", (str(datei(db, jahr)),))
        try:
            with con:
                _tabellen_anlegen(con, "archiv")
                for teil in range(0, len(ids), 500):
                    stueck = ids[teil:teil + 500]
                    frage = ", ".join("?" * len(stueck))
                    _kopieren(con, "main", "archiv", "angebote", f"id IN ({frage})", stueck)
                    for t in JE_ANGEBOT:
                        if t in {r[0] for r in con.execute("SELECT name FROM main.sqlite_master WHERE type='table'")}:
                            _kopieren(con, "main", "archiv", t, f"angebot_id IN ({frage})", stueck)
                    _kopieren(con, "main", "archiv", "netze",
                              f"position_id IN (SELECT id FROM main.positionen WHERE angebot_id IN ({frage}))", stueck)
                    con.execute(f"DELETE FROM main.auftrag_status WHERE angebot_id IN ({frage})", stueck)
                    con.execute(f"DELETE FROM main.angebote WHERE id IN ({frage})", stueck)     # Rest: ON DELETE CASCADE
                    if fortschritt:
                        fortschritt(jahr, min(teil + 500, len(ids)), len(ids))
        finally:
            con.execute("DETACH DATABASE archiv")
        ergebnis[jahr] = len(ids)
    if ergebnis:
        con.execute("VACUUM")          # Platz der verschobenen Angebote freigeben (Datendatei wird kleiner)
        sichern(db)
    return ergebnis


def sichern(db):
    """Archivdateien in Sicherung/Archiv und, falls eingestellt, in den zweiten Sicherungsordner kopieren (das Archiv
    ist sonst die einzige Kopie der verschobenen Angebote). Ergebnis: Fehlertext oder None."""
    ziele = [Path(db.pfad).parent / "Sicherung" / "Archiv"]
    ordner2 = (db.einstellung("sicherung_ordner2") or "").strip()
    if ordner2:
        ziele.append(Path(ordner2) / "Archiv")
    fehler = None
    for ziel in ziele:
        try:
            ziel.mkdir(parents=True, exist_ok=True)
            for pfad in dateien(db).values():
                neu = ziel / (pfad.name + ".neu")
                shutil.copy2(pfad, neu)
                neu.replace(ziel / pfad.name)
        except OSError as e:
            fehler = f"Archiv nicht gesichert ({ziel}): {e}"
    return fehler


def suchen(db, text="", grenze=500):
    """Angebote in allen Archivdateien: [dict(jahr, id, nummer, kunde, kundennr, datum, vorgang, vk_netto, positionen)],
    neueste zuerst; text sucht in Nummer, Kunde, Kundennummer, Bemerkung, Artikel und Bezeichnung."""
    out = []
    for jahr, pfad in sorted(dateien(db).items(), reverse=True):
        con = sqlite3.connect(pfad)
        try:
            sql = ("SELECT a.id, a.nummer, a.kunde, a.kundennr, a.datum, a.vorgang, a.vk_netto, "
                   "(SELECT COUNT(*) FROM positionen p WHERE p.angebot_id = a.id) FROM angebote a")
            werte = []
            if text:
                sql += (" WHERE a.nummer LIKE ? OR a.kunde LIKE ? OR a.kundennr LIKE ? OR a.bemerkung LIKE ? OR a.id IN "
                        "(SELECT angebot_id FROM positionen WHERE artikel LIKE ? OR bezeichnung LIKE ?)")
                werte = [f"%{text}%"] * 6
            sql += " ORDER BY a.datum DESC, a.id DESC LIMIT ?"
            for i, nummer, kunde, kundennr, datum, vorgang, vk, n in con.execute(sql, werte + [grenze - len(out)]):
                out.append(dict(jahr=jahr, id=i, nummer=nummer, kunde=kunde, kundennr=kundennr, datum=datum,
                                vorgang=vorgang or "Entwurf", vk_netto=vk, positionen=n))
        except sqlite3.DatabaseError:
            continue
        finally:
            con.close()
        if len(out) >= grenze:
            break
    return out


def anzahl(db):
    """{Jahr: Anzahl Angebote} je Archivdatei."""
    out = {}
    for jahr, pfad in dateien(db).items():
        con = sqlite3.connect(pfad)
        try:
            out[jahr] = con.execute("SELECT COUNT(*) FROM angebote").fetchone()[0]
        except sqlite3.DatabaseError:
            out[jahr] = 0
        finally:
            con.close()
    return out


def zurueckholen(db, jahr, archiv_id):
    """Angebot aus dem Archiv wieder in die Datendatei (neue IDs, Nummer bleibt). Ergebnis: neue Angebots-ID."""
    con = db.con
    con.execute("ATTACH DATABASE ? AS archiv", (str(datei(db, jahr)),))
    try:
        with con:
            hier = {t: _spalten(con, "main", t) for t in ("angebote", "netze") + JE_ANGEBOT}
            dort = {t: _spalten(con, "archiv", t) for t in hier}
            r = con.execute("SELECT nummer FROM archiv.angebote WHERE id=?", (archiv_id,)).fetchone()
            if r is None:
                raise ValueError("Das Angebot ist nicht mehr im Archiv.")
            if con.execute("SELECT 1 FROM main.angebote WHERE nummer=?", (r[0],)).fetchone():
                raise ValueError(f"Angebot {r[0]} gibt es schon in der Datendatei.")

            def einfuegen(tabelle, zeile, ersetzen):
                """Zeile übernehmen; die alte ID bleibt, wenn sie in der Datendatei frei ist (Freigabe-Kennung,
                Verweise), sonst neue ID."""
                frei = "id" in dort[tabelle] and not con.execute(f'SELECT 1 FROM main."{tabelle}" WHERE id=?',
                                                                  (zeile[dort[tabelle].index("id")],)).fetchone()
                namen = [s for s in dort[tabelle] if s in hier[tabelle] and (s != "id" or frei)]
                werte = [ersetzen.get(s, zeile[dort[tabelle].index(s)]) for s in namen]
                return con.execute(f'INSERT INTO main."{tabelle}" ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                                   f'VALUES ({", ".join("?" * len(namen))})', werte).lastrowid

            kopf = con.execute("SELECT * FROM archiv.angebote WHERE id=?", (archiv_id,)).fetchone()
            neu = einfuegen("angebote", kopf, {})
            pos_neu, stufe_neu = {}, {}
            for t in ("positionen", "staffel_stufen", "staffeln", "step_protokoll", "auftrag_status"):
                if t not in dort or not dort[t]:
                    continue
                for z in con.execute(f'SELECT * FROM archiv."{t}" WHERE angebot_id=? ORDER BY id', (archiv_id,)).fetchall():
                    ersetzen = {"angebot_id": neu}
                    if t == "staffeln" and "stufe_id" in dort[t]:
                        ersetzen["stufe_id"] = stufe_neu.get(z[dort[t].index("stufe_id")])
                    i = einfuegen(t, z, ersetzen)
                    if t == "positionen":
                        pos_neu[z[0]] = i
                    elif t == "staffel_stufen":
                        stufe_neu[z[0]] = i
            for alt, daten in con.execute("SELECT position_id, daten FROM archiv.netze WHERE position_id IN "
                                          "(SELECT id FROM archiv.positionen WHERE angebot_id=?)", (archiv_id,)).fetchall():
                if alt in pos_neu:
                    con.execute("INSERT INTO main.netze (position_id, daten) VALUES (?, ?)", (pos_neu[alt], daten))
            con.execute("DELETE FROM archiv.netze WHERE position_id IN (SELECT id FROM archiv.positionen WHERE "
                        "angebot_id=?)", (archiv_id,))
            for t in JE_ANGEBOT:
                if dort.get(t):
                    con.execute(f'DELETE FROM archiv."{t}" WHERE angebot_id=?', (archiv_id,))
            con.execute("DELETE FROM archiv.angebote WHERE id=?", (archiv_id,))
    finally:
        con.execute("DETACH DATABASE archiv")
    _freigabe_umschreiben(db, neu, {n: a for a, n in pos_neu.items()})
    sichern(db)
    return neu


def _freigabe_umschreiben(db, angebot_id, alt_von_neu):
    """Mussten Positionen neue IDs bekommen, die Freigabe (fertigung.py, Kennung über Positions-IDs) auf die neuen IDs
    umstellen – nur wenn der Stand vor dem Archivieren unverändert freigegeben war."""
    if all(a == n for n, a in alt_von_neu.items()):
        return
    from . import fertigung
    f = fertigung.freigabe(db, angebot_id)
    if not f:
        return
    kopf, positionen = db.angebot(angebot_id), db.positionen(angebot_id)
    alt = [dict(p, id=alt_von_neu.get(p["id"], p["id"])) for p in positionen]
    if f.get("kennung") == fertigung.kennung(kopf, alt):
        f["kennung"] = fertigung.kennung(kopf, positionen)
    f["positionen"] = [n for n, a in alt_von_neu.items() if a in (f.get("positionen") or [])]
    with db.con:
        db.con.execute("UPDATE angebote SET freigabe=? WHERE id=?", (json.dumps(f, ensure_ascii=False), angebot_id))


def bericht(ergebnis):
    n = sum(ergebnis.values())
    return (f"{n} Angebot{'e' if n != 1 else ''} archiviert (" +
            ", ".join(f"{j}: {k}" for j, k in sorted(ergebnis.items())) + ")") if n else "Nichts zu archivieren."

