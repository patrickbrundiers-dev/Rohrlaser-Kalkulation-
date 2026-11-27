"""Zusammenarbeit im Serverbetrieb (Serverversion S4b, Patrick 26.11.2026). Ohne Qt.

Im Ordnerbetrieb laufen Übergaben, Übernahme-Anfragen, Absagen und Notizen über die Dateien im gemeinsamen Ordner
(teilen._vorgaenge_schreiben/_vorgaenge_lesen) und kommen erst beim nächsten Abgleich an. Am zentralen Server liegen
alle Angebote in einer Datenbank: ein Vorgang ist eine Zeile in server_vorgaenge und beim Empfänger mit dem nächsten
Puls (höchstens PULS_S Sekunden) da.

- Übergabe: der Bearbeiter des Angebots wechselt sofort (angebote.bearbeiter), der Empfänger bekommt die Meldung
  „… hat Ihnen Angebot … übergeben“. Eine Rücknahme braucht es nicht (der Empfänger kann zurückgeben).
- Übernahme anfragen: geht an den Bearbeiter; er wird gefragt (übergeben, ablehnen, später). Die Absage kommt als
  Meldung zurück.
- Notiz (wahlweise mit Wiedervorlage) an einen Kollegen; erledigt wird je Empfänger am Server vermerkt, damit sie an
  jedem Arbeitsplatz dieses Mitarbeiters gleich ist.
- Kollegen = die Logins am Server (ohne gesperrte), Name aus der Benutzerverwaltung.
Dieselben Funktionsnamen und Ergebnisse wie in teilen.py, damit Oberfläche und Tests beide Betriebsarten gleich
behandeln (teilen.py ruft im Serverbetrieb diese Funktionen).
"""
import datetime

from . import server_betrieb as sb
from .teilen import TeilenFehler as Fehler

VORGAENGE = "server_vorgaenge"
UEBERGABE, ANFRAGE, ABGELEHNT, NOTIZ = "uebergabe", "anfrage", "abgelehnt", "notiz"     # wie teilen.py
NOTIZEN_MAX = 200
_SPALTEN = ("id", "art", "nummer", "angebot_id", "von", "an", "notiz", "faellig", "bezug", "zeit", "gesehen",
            "erledigt")


# ------------------------------------------------------------------------------------------------ Einrichten
def einrichten(con):
    """Tabelle und Rechte (als rohrlaser_app nach der Datenpflege; mehrfach aufrufbar)."""
    con.execute(f"CREATE TABLE IF NOT EXISTS {VORGAENGE} (id BIGSERIAL PRIMARY KEY, art TEXT NOT NULL, nummer TEXT, "
                "angebot_id BIGINT, von TEXT NOT NULL, an TEXT NOT NULL, notiz TEXT, faellig TEXT, bezug BIGINT, "
                "zeit TIMESTAMPTZ DEFAULT now(), gesehen BOOLEAN DEFAULT false, erledigt BOOLEAN DEFAULT false)")
    con.execute(f"CREATE INDEX IF NOT EXISTS {VORGAENGE}_an ON {VORGAENGE} (an, erledigt, id)")
    # wer nur ansehen darf, liest seine Notizen und hakt sie ab (schickt aber nichts)
    con.execute(f'GRANT SELECT, UPDATE ON {VORGAENGE} TO "{sb.ROLLE_LESEN}"')


def _s(db):
    return db.server


def _zeilen(db, where, werte=()):
    sql = (f"SELECT id, art, nummer, angebot_id, von, an, notiz, faellig, bezug, "
           f"to_char(zeit AT TIME ZONE current_setting('TimeZone'), 'YYYY-MM-DD\"T\"HH24:MI:SS'), gesehen, erledigt "
           f"FROM {VORGAENGE} WHERE {where} ORDER BY id")
    return [dict(zip(_SPALTEN, z)) for z in db.con.execute(sql, tuple(werte)).fetchall()]


def _neu(db, art, an, nummer=None, angebot_id=None, notiz="", faellig=None, bezug=None):
    r = db.con.execute(f"INSERT INTO {VORGAENGE} (art, nummer, angebot_id, von, an, notiz, faellig, bezug) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                       (art, nummer, angebot_id, _s(db).kuerzel, an, notiz or "", faellig, bezug)).fetchone()
    return int(r[0])


def _schreiben_pruefen(db):
    if _s(db).nur_lesen or db.nur_lesen:
        raise Fehler("Mit dem Zugang „nur ansehen“ lassen sich keine Angebote übergeben und keine Notizen senden.")


# ------------------------------------------------------------------------------------------------ Kollegen
def kollegen(db):
    """{Kürzel: Name} der anderen Mitarbeiter mit Login am Server (gesperrte nicht)."""
    ich = _s(db).kuerzel
    return {b["kuerzel"]: b.get("name") or "" for b in sb.benutzer_liste(db.con.v.con)
            if b["kuerzel"] and b["kuerzel"] != ich and not b.get("gesperrt") and b.get("recht")}


def name(db, k):
    return next((b.get("name") or "" for b in sb.benutzer_liste(db.con.v.con) if b["kuerzel"] == k), "")


# ------------------------------------------------------------------------------------------------ Vorgänge
def _angebot(db, angebot_id):
    r = db.con.execute("SELECT id, nummer, bearbeiter FROM angebote WHERE id=?", (angebot_id,)).fetchone()
    if r is None:
        raise Fehler("Das Angebot gibt es nicht mehr.")
    return dict(id=r[0], nummer=r[1], bearbeiter=r[2] or "")


def uebergeben(db, angebot_id, an, notiz="", bezug=None):
    """Angebot an den Kollegen an übergeben: er ist sofort der Bearbeiter. Nur der bisherige Bearbeiter (oder bei
    einem Angebot ohne Bearbeiter jeder, der ändern darf) und der Verwalter. Ergebnis: Kennung des Vorgangs."""
    from . import teilen
    _schreiben_pruefen(db)
    s = _s(db)
    a = _angebot(db, angebot_id)
    an = teilen.kuerzel_sauber(an)
    if not an or an == s.kuerzel:
        raise Fehler("Bitte einen Kollegen wählen.")
    if an not in kollegen(db):
        raise Fehler(f"{an} hat keinen Zugang am Server (Einstellungen → Benutzer und Rollen).")
    if a["bearbeiter"] and a["bearbeiter"] != s.kuerzel and not s.verwalter:
        raise Fehler(f"Angebot {a['nummer']} bearbeitet {a['bearbeiter']}: übergeben kann nur der Bearbeiter. "
                     "„Übernahme anfragen …“ fragt ihn.")
    with db.con:
        db.con.execute("UPDATE angebote SET bearbeiter=? WHERE id=?", (an, angebot_id))
        i = _neu(db, UEBERGABE, an, a["nummer"], angebot_id, notiz, bezug=bezug)
        # offene Anfragen zu diesem Angebot sind damit beantwortet
        db.con.execute(f"UPDATE {VORGAENGE} SET erledigt=true WHERE art=? AND angebot_id=? AND NOT erledigt",
                       (ANFRAGE, angebot_id))
    _protokoll(db, "uebergabe", f"Angebot {a['nummer']} an {an}", a["nummer"])
    return i


def anfragen(db, angebot_id, notiz=""):
    """Übernahme eines Angebots beim Bearbeiter anfragen. Ergebnis: Kennung (eine schon offene bleibt)."""
    _schreiben_pruefen(db)
    s = _s(db)
    a = _angebot(db, angebot_id)
    if not a["bearbeiter"] or a["bearbeiter"] == s.kuerzel:
        raise Fehler("Das Angebot gehört schon Ihnen.")
    offen = vorgang_offen(db, a["nummer"], ANFRAGE)
    if offen:
        return offen["id"]
    with db.con:
        return _neu(db, ANFRAGE, a["bearbeiter"], a["nummer"], angebot_id, notiz)


def beantworten(db, anfrage, ja, notiz=""):
    """Anfrage eines Kollegen (aus abholen()['anfragen']) beantworten: ja = übergeben, sonst ablehnen."""
    if ja:
        i = uebergeben(db, anfrage["angebot_id"], anfrage["von"], notiz or "auf Ihre Anfrage", bezug=anfrage["id"])
    else:
        _schreiben_pruefen(db)
        with db.con:
            i = _neu(db, ABGELEHNT, anfrage["von"], anfrage["nummer"], anfrage["angebot_id"], notiz,
                     bezug=anfrage["id"])
    with db.con:
        db.con.execute(f"UPDATE {VORGAENGE} SET erledigt=true, gesehen=true WHERE id=?", (anfrage["id"],))
    return i


def vorgang_offen(db, nummer, art):
    """Eigener offener Vorgang (nur Anfragen bleiben offen, eine Übergabe gilt sofort) oder None."""
    if art != ANFRAGE or not nummer:
        return None
    z = _zeilen(db, "art=? AND nummer=? AND von=? AND NOT erledigt", (ANFRAGE, nummer, _s(db).kuerzel))
    return z[-1] if z else None


def notiz_senden(db, an, text, nummer=None, faellig=None):
    from . import teilen
    _schreiben_pruefen(db)
    an, text = teilen.kuerzel_sauber(an), " ".join(str(text or "").split())
    if not an or an == _s(db).kuerzel:
        raise Fehler("Bitte einen Kollegen wählen.")
    if not text:
        raise Fehler("Bitte einen Text eingeben.")
    aid = None
    if nummer:
        r = db.con.execute("SELECT id FROM angebote WHERE nummer=?", (nummer,)).fetchone()
        aid = r[0] if r else None
    with db.con:
        return _neu(db, NOTIZ, an, nummer or None, aid, text, faellig=faellig or None)


def _notiz(v):
    return dict(id=v["id"], von=v["von"], nummer=v["nummer"], notiz=v["notiz"] or "", zeit=v["zeit"],
                faellig=v["faellig"], erledigt=bool(v["erledigt"]))


def notizen(db, offen_nur=False, heute=None):
    """Erhaltene Notizen, neueste zuerst (wie teilen.notizen)."""
    heute = (heute or datetime.date.today()).isoformat()
    z = _zeilen(db, "art=? AND an=?" + (" AND NOT erledigt" if offen_nur else ""), (NOTIZ, _s(db).kuerzel))
    out = [_notiz(v) for v in reversed(z)][:NOTIZEN_MAX]
    return [dict(n, faellig_jetzt=not n.get("faellig") or n["faellig"] <= heute) for n in out]


def notiz_erledigt(db, nid):
    with db.con:
        db.con.execute(f"UPDATE {VORGAENGE} SET erledigt=true, gesehen=true WHERE id=? AND an=?",
                       (nid, _s(db).kuerzel))


def abholen(db):
    """Neue Vorgänge für mich, Ergebnis wie der Abgleich-Bericht im Ordnerbetrieb: dict(uebernommen, notizen,
    abgelehnt, anfragen). Übergaben, Notizen und Absagen gelten danach als gesehen; Anfragen bleiben offen, bis sie
    beantwortet sind (gefragt wird je Sitzung einmal, siehe server_dialog)."""
    s = _s(db)
    out = dict(uebernommen=[], notizen=[], abgelehnt=[], anfragen=[], geaenderte_ids=[])
    neu = _zeilen(db, "an=? AND NOT gesehen", (s.kuerzel,))
    mein = {r[0]: r[1] or "" for r in db.con.execute("SELECT id, bearbeiter FROM angebote WHERE id IN (SELECT "
                                                     f"angebot_id FROM {VORGAENGE} WHERE an=? AND art=? AND NOT "
                                                     "erledigt)", (s.kuerzel, ANFRAGE)).fetchall()}
    gesehen = []
    for v in neu:
        if v["art"] == UEBERGABE:
            out["uebernommen"].append(dict(nummer=v["nummer"], von=v["von"], notiz=v["notiz"] or "",
                                           id=v["angebot_id"]))
            out["geaenderte_ids"].append(v["angebot_id"])
        elif v["art"] == NOTIZ:
            out["notizen"].append(_notiz(v))
        elif v["art"] == ABGELEHNT:
            out["abgelehnt"].append(dict(nummer=v["nummer"], von=v["von"], notiz=v["notiz"] or ""))
        if v["art"] != ANFRAGE:
            gesehen.append(v["id"])
    erledigt = []
    for v in _zeilen(db, "an=? AND art=? AND NOT erledigt", (s.kuerzel, ANFRAGE)):
        if mein.get(v["angebot_id"]) == s.kuerzel:
            out["anfragen"].append(dict(v, angebot_id=v["angebot_id"]))
        else:
            erledigt.append(v["id"])            # gehört (inzwischen) nicht mehr mir: nichts zu fragen
    if (gesehen or erledigt) and not db.con.in_transaction:
        with db.con:
            for i in gesehen:
                db.con.execute(f"UPDATE {VORGAENGE} SET gesehen=true WHERE id=?", (i,))
            for i in erledigt:
                db.con.execute(f"UPDATE {VORGAENGE} SET erledigt=true, gesehen=true WHERE id=?", (i,))
    return out


def _protokoll(db, art, text, objekt=""):
    from . import server_mehrplatz
    server_mehrplatz.protokollieren(db, art, text, objekt)
