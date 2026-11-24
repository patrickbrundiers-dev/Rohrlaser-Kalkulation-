"""KI-Plattform: Protokoll aller KI-Aktionen und offene KI-Empfehlungen (Master-Prompt Patrick 20.11.2026, Punkt 10
„Protokollierung sämtlicher KI-Aktionen“). Beide Tabellen gelten nur für diesen Arbeitsplatz (wie online_abrufe) und
sind in jeder Datenbank-Sicherung enthalten.

ki_aktionen      jede Frage an den Assistenten, jede KI-Prüfung, jeder Modellaufruf, jede Übernahme/Ablehnung eines
                 KI-Vorschlags: zeit, benutzer, agent, aktion, angebot_id, frage, ergebnis, quellen (JSON), modell,
                 dauer, status
ki_empfehlungen  offene Empfehlungen der Agenten (Dashboard „Offene KI-Empfehlungen“): schluessel (gleiche Empfehlung
                 nur einmal offen), agent, art, angebot_id, ziel, text, begruendung, quellen, status (offen / erledigt /
                 abgelehnt), erstellt, erledigt_am, benutzer
Eine Empfehlung ändert nie selbst Daten: „Erledigen“ springt ins Programm (ziel) oder ruft eine vorhandene Aktion des
Angebots-Checks auf, die man dort wie bisher sieht. Ohne Qt."""
import datetime
import json
from . import protokoll

AKTIONEN, EMPFEHLUNGEN = "ki_aktionen", "ki_empfehlungen"
OFFEN, ERLEDIGT, ABGELEHNT = "offen", "erledigt", "abgelehnt"
MAX_TEXT = 4000


def einrichten(con):
    con.execute(f"CREATE TABLE IF NOT EXISTS {AKTIONEN} (id INTEGER PRIMARY KEY, zeit TEXT, benutzer TEXT, "
                "agent TEXT, aktion TEXT, angebot_id INTEGER, frage TEXT, ergebnis TEXT, quellen TEXT, modell TEXT, "
                "dauer REAL, status TEXT)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {EMPFEHLUNGEN} (id INTEGER PRIMARY KEY, schluessel TEXT, agent TEXT, "
                "art TEXT, angebot_id INTEGER, ziel TEXT, text TEXT, begruendung TEXT, quellen TEXT, status TEXT, "
                "erstellt TEXT, erledigt_am TEXT, benutzer TEXT)")


_BEREIT = set()


def bereit(db):
    """Tabellen anlegen, falls die Datenbank sie noch nicht hat (z. B. Schema-Schritt noch nicht gelaufen)."""
    if id(db) in _BEREIT or getattr(db, "nur_lesen", False):
        return
    try:
        einrichten(db.con)
        db.con.commit()
        _BEREIT.add(id(db))
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_protokoll: abgefangen")


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _wer(db):
    try:
        from . import rollen
        return rollen.angemeldet(db) or db.einstellung("benutzer_kuerzel") or ""
    except Exception:           # noqa: BLE001
        return ""


def schreiben(db, agent, aktion, frage="", ergebnis="", quellen=(), modell="", dauer=0.0, status="ok",
              angebot_id=None):
    """Eine KI-Aktion protokollieren; Fehler beim Schreiben (z. B. nur lesen) brechen nie die Arbeit ab."""
    bereit(db)
    try:
        db.con.execute(f"INSERT INTO {AKTIONEN} (zeit, benutzer, agent, aktion, angebot_id, frage, ergebnis, quellen, "
                       "modell, dauer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (_jetzt(), _wer(db), str(agent or ""), str(aktion or ""), angebot_id, str(frage or "")[:MAX_TEXT],
                        str(ergebnis or "")[:MAX_TEXT], json.dumps(list(quellen or ()), ensure_ascii=False,
                                                                     default=str)[:MAX_TEXT],
                        str(modell or ""), round(float(dauer or 0), 3), str(status or "")))
        db.con.commit()
        return True
    except Exception:           # noqa: BLE001 – Protokoll nie wichtiger als die Arbeit
        return False


NAMEN_A = ("id", "zeit", "benutzer", "agent", "aktion", "angebot_id", "frage", "ergebnis", "quellen", "modell", "dauer",
           "status")
NAMEN_E = ("id", "schluessel", "agent", "art", "angebot_id", "ziel", "text", "begruendung", "quellen", "status",
           "erstellt", "erledigt_am", "benutzer")


def _json(t):
    try:
        return json.loads(t) if t else []
    except ValueError:
        return []


def liste(db, anzahl=500, agent=None, aktion=None):
    bereit(db)
    sql, w = f"SELECT {', '.join(NAMEN_A)} FROM {AKTIONEN}", []
    bed = []
    if agent:
        bed.append("agent=?")
        w.append(agent)
    if aktion:
        bed.append("aktion=?")
        w.append(aktion)
    if bed:
        sql += " WHERE " + " AND ".join(bed)
    out = []
    for r in db.con.execute(sql + f" ORDER BY id DESC LIMIT {int(anzahl)}", w):
        d = dict(zip(NAMEN_A, r))
        d["quellen"] = _json(d["quellen"])
        out.append(d)
    return out


def zaehlen(db):
    """Kennzahlen für das Dashboard: dict(aktionen, fragen, pruefungen, angebote, befunde_fehler, modellaufrufe,
    uebernommen, abgelehnt, letzte)."""
    bereit(db)
    def eins(sql, w=()):
        try:
            return db.con.execute(sql, w).fetchone()[0] or 0
        except Exception:       # noqa: BLE001
            return 0
    return dict(aktionen=eins(f"SELECT COUNT(*) FROM {AKTIONEN}"),
                fragen=eins(f"SELECT COUNT(*) FROM {AKTIONEN} WHERE aktion='frage'"),
                pruefungen=eins(f"SELECT COUNT(*) FROM {AKTIONEN} WHERE aktion='pruefung'"),
                angebote=eins(f"SELECT COUNT(DISTINCT angebot_id) FROM {AKTIONEN} WHERE aktion='pruefung'"),
                befunde_fehler=eins(f"SELECT COUNT(*) FROM {EMPFEHLUNGEN} WHERE art IN ('FEHLER', 'WARNUNG')"),
                modellaufrufe=eins(f"SELECT COUNT(*) FROM {AKTIONEN} WHERE modell <> ''"),
                uebernommen=eins(f"SELECT COUNT(*) FROM {EMPFEHLUNGEN} WHERE status=?", (ERLEDIGT,)),
                abgelehnt=eins(f"SELECT COUNT(*) FROM {EMPFEHLUNGEN} WHERE status=?", (ABGELEHNT,)),
                letzte=(liste(db, 1) or [dict(zeit="")])[0]["zeit"])


# ------------------------------------------------------------------ Empfehlungen
def empfehlung_merken(db, befund, angebot_id=None):
    """Befund als offene Empfehlung merken (nur Fehler, Warnungen und Vorschläge; gleicher Schlüssel nur einmal offen,
    abgelehnte kommen nicht wieder). Ergebnis: ID oder None."""
    bereit(db)
    if befund.get("art") not in ("FEHLER", "WARNUNG", "VORSCHLAG"):
        return None
    schl = befund.get("schluessel") or f"{befund.get('agent')}|{angebot_id}|{befund.get('text')}"[:500]
    try:
        r = db.con.execute(f"SELECT id, status FROM {EMPFEHLUNGEN} WHERE schluessel=? ORDER BY id DESC LIMIT 1",
                           (schl,)).fetchone()
        if r and r[1] in (OFFEN, ABGELEHNT):
            return r[0] if r[1] == OFFEN else None
        cur = db.con.execute(f"INSERT INTO {EMPFEHLUNGEN} (schluessel, agent, art, angebot_id, ziel, text, begruendung, "
                             "quellen, status, erstellt, erledigt_am, benutzer) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (schl, befund.get("agent") or "", befund.get("art") or "", angebot_id,
                              befund.get("ziel") or "", str(befund.get("text") or "")[:MAX_TEXT],
                              str(befund.get("begruendung") or "")[:MAX_TEXT],
                              json.dumps(befund.get("quellen") or [], ensure_ascii=False, default=str), OFFEN,
                              _jetzt(), "", _wer(db)))
        i = cur.lastrowid
        db.con.commit()
        return i
    except Exception:           # noqa: BLE001
        return None


def empfehlungen(db, status=OFFEN, angebot_id=None, anzahl=500):
    bereit(db)
    sql, w = f"SELECT {', '.join(NAMEN_E)} FROM {EMPFEHLUNGEN}", []
    bed = []
    if status:
        bed.append("status=?")
        w.append(status)
    if angebot_id is not None:
        bed.append("angebot_id=?")
        w.append(angebot_id)
    if bed:
        sql += " WHERE " + " AND ".join(bed)
    out = []
    try:
        for r in db.con.execute(sql + f" ORDER BY id DESC LIMIT {int(anzahl)}", w):
            d = dict(zip(NAMEN_E, r))
            d["quellen"] = _json(d["quellen"])
            out.append(d)
    except Exception:           # noqa: BLE001
        return []
    return out


def empfehlung_setzen(db, empfehlung_id, status):
    if status not in (OFFEN, ERLEDIGT, ABGELEHNT):
        raise ValueError(status)
    db.con.execute(f"UPDATE {EMPFEHLUNGEN} SET status=?, erledigt_am=? WHERE id=?",
                   (status, "" if status == OFFEN else _jetzt(), empfehlung_id))
    db.con.commit()
    schreiben(db, "KI-Zentrale", "empfehlung_" + status, ergebnis=f"Empfehlung {empfehlung_id}")


def angebot_schliessen(db, angebot_id, offene_schluessel):
    """Empfehlungen eines Angebots, die eine neue Prüfung nicht mehr findet, als erledigt markieren."""
    try:
        for r in db.con.execute(f"SELECT id, schluessel FROM {EMPFEHLUNGEN} WHERE angebot_id=? AND status=?",
                                (angebot_id, OFFEN)).fetchall():
            if r[1] not in offene_schluessel:
                db.con.execute(f"UPDATE {EMPFEHLUNGEN} SET status=?, erledigt_am=? WHERE id=?",
                               (ERLEDIGT, _jetzt(), r[0]))
        db.con.commit()
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_protokoll: abgefangen")
