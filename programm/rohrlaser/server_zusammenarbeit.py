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
FUNKTION_QUITTIEREN = "rl_vorgang_quittieren"
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
    # Quittieren (gesehen/erledigt) nur eigener Zeilen über eine Serverfunktion: wer nur ansehen darf, liest seine
    # Notizen und hakt sie ab, kann aber keine Zeile eines Kollegen ändern (kein UPDATE-Recht auf die Tabelle)
    con.execute(f"""CREATE OR REPLACE FUNCTION {FUNKTION_QUITTIEREN}(ids bigint[], fertig boolean)
        RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $f$
        DECLARE n integer;
        BEGIN
          UPDATE {VORGAENGE} SET gesehen = true, erledigt = erledigt OR fertig
           WHERE id = ANY(ids) AND (lower('{sb.LOGIN_PRAEFIX}' || an) = session_user::text
                                    OR upper(substr(session_user::text, {len(sb.LOGIN_PRAEFIX) + 1})) = an);
          GET DIAGNOSTICS n = ROW_COUNT;
          RETURN n;
        END $f$""")
    con.execute(f"REVOKE ALL ON FUNCTION {FUNKTION_QUITTIEREN}(bigint[], boolean) FROM PUBLIC")
    con.execute(f'REVOKE UPDATE ON {VORGAENGE} FROM "{sb.ROLLE_LESEN}"')
    con.execute(f'GRANT SELECT ON {VORGAENGE} TO "{sb.ROLLE_LESEN}"')
    for rolle in (sb.ROLLE_LESEN, sb.ROLLE_APP):
        con.execute(f'GRANT EXECUTE ON FUNCTION {FUNKTION_QUITTIEREN}(bigint[], boolean) TO "{rolle}"')


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


def _quittieren(db, ids, fertig=False):
    """Eigene Vorgänge als gesehen (fertig: erledigt) vermerken; nur Zeilen an den angemeldeten Mitarbeiter."""
    if not ids:
        return
    from . import db_verbindung
    lesen = bool(db.nur_lesen) and not db.con.in_transaction
    if lesen:       # Lesemodus: nur dieser Aufruf schreibt; was er darf, entscheidet der Server (nur eigene Zeilen)
        db_verbindung.nur_lesen(db.con, False)
    try:
        with db.con:
            db.con.execute(f"SELECT {FUNKTION_QUITTIEREN}(?::bigint[], ?)", (list(map(int, ids)), bool(fertig)))
    finally:
        if lesen:
            db_verbindung.nur_lesen(db.con, True)


# ------------------------------------------------------------------------------------------------ Kollegen
def kollegen(db, bearbeiten=False):
    """{Kürzel: Name} der anderen Mitarbeiter mit Login am Server (gesperrte nicht); bearbeiten: nur wer Angebote
    ändern darf (Ziel einer Übergabe; wer nur ansehen darf, bekommt nur Notizen)."""
    ich = _s(db).kuerzel
    rechte = (sb.RECHT_BEARBEITEN, sb.RECHT_VERWALTER) if bearbeiten else (sb.RECHT_BEARBEITEN, sb.RECHT_VERWALTER,
                                                                           sb.RECHT_LESEN)
    return {b["kuerzel"]: b.get("name") or "" for b in sb.benutzer_liste(db.con.v.con)
            if b["kuerzel"] and b["kuerzel"] != ich and not b.get("gesperrt") and b.get("recht") in rechte}


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
    if an not in kollegen(db, bearbeiten=True):
        raise Fehler(f"{an} hat keinen Zugang am Server, der Angebote bearbeiten darf (Einstellungen → Benutzer "
                     "und Rollen).")
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
    _quittieren(db, [anfrage["id"]], fertig=True)
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
    _quittieren(db, [nid], fertig=True)


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
        _quittieren(db, gesehen)
        _quittieren(db, erledigt, fertig=True)
    return out


def _protokoll(db, art, text, objekt=""):
    from . import server_mehrplatz
    server_mehrplatz.protokollieren(db, art, text, objekt)
