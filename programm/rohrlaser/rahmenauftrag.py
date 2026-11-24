"""Rahmenaufträge und Abrufe (Patrick 20.11.2026, Master-Auftrag „Intelligente Rahmenauftrags- und
Abrufkalkulation“). Ohne Qt.

Ein Rahmenauftrag steht für sich (unabhängig vom Einzelauftrag): Kunde, Nummer RA-JJJJ-NNNN, Projekt, Laufzeit,
Positionen (meist aus einem Angebot: gemeinsame Datenbasis), Vertragsbedingungen, Preisbindung, Abrufe mit Plan- und
Ist-Termin, Fertigungslose, Materialkonto (nur das für diesen Rahmen gekaufte Material, kein Restelager) und
festgeschriebene Kalkulationsversionen.

Wie beim Auftrag (auftraege.py): Alles ist ein Ereignis (Tabelle rahmen_ereignisse), das nie geändert oder gelöscht
wird; jeder Eintrag hat Zeitpunkt, Benutzer, Rechner und eine Prüfsumme mit dem Vorgänger desselben Rechners. Die
Tabelle rahmen_kopf ist die daraus gerechnete Sicht (ein JSON je Rahmen). Mehrere Arbeitsplätze: jeder Platz legt
seine Ereignisse als Rahmen/<Kürzel>.json in den gemeinsamen Ordner und liest die der Kollegen (über uid ohne
Doppelte). Ändern zwei Plätze dasselbe Feld, gilt die spätere Änderung; beide stehen im Protokoll und der Rahmen
zeigt einen Konflikthinweis (alt-Wert passte nicht mehr).

Vertragspreise und Kalkulationsparameter ändern sich nie automatisch: eine Preisänderung ist erst ein Vorschlag
(Ereignis preis_vorschlag) und gilt erst mit Freigabe (preis_freigabe, mit Benutzer). Rechnungen bleiben im ERP.
"""
import copy
import datetime
import hashlib
import json
import re
import socket
import uuid

TABELLEN = ("rahmen_ereignisse", "rahmen_kopf")
TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS rahmen_ereignisse (id INTEGER PRIMARY KEY, uid TEXT NOT NULL UNIQUE, rahmen TEXT "
    "NOT NULL, art TEXT NOT NULL, ziel TEXT, feld TEXT, alt TEXT, neu TEXT, daten TEXT, bemerkung TEXT, wer TEXT, "
    "name TEXT, rechner TEXT, am TEXT NOT NULL, vorher TEXT, pruef TEXT)",
    "CREATE INDEX IF NOT EXISTS rahmen_ereignisse_rahmen ON rahmen_ereignisse (rahmen, am)",
    "CREATE TABLE IF NOT EXISTS rahmen_kopf (uid TEXT PRIMARY KEY, nummer TEXT, kunde TEXT, status TEXT, ende TEXT, "
    "daten TEXT, geaendert TEXT)",
    "CREATE INDEX IF NOT EXISTS rahmen_kopf_kunde ON rahmen_kopf (kunde, status)",
)

# Status des Rahmens
ENTWURF, ANGEBOTEN, AKTIV, ABGESCHLOSSEN, STORNIERT_R = "Entwurf", "Angeboten", "Aktiv", "Abgeschlossen", "Storniert"
STATUS_LISTE = (ENTWURF, ANGEBOTEN, AKTIV, ABGESCHLOSSEN, STORNIERT_R)
# Status eines Abrufs
GEPLANT, ABGERUFEN, TEILGELIEFERT, GELIEFERT, ABGESCHLOSSEN_A, STORNIERT = (
    "geplant", "abgerufen", "teilgeliefert", "geliefert", "abgeschlossen", "storniert")
ABRUF_STATUS = (GEPLANT, ABGERUFEN, TEILGELIEFERT, GELIEFERT, ABGESCHLOSSEN_A, STORNIERT)
OFFEN_A = (GEPLANT, ABGERUFEN, TEILGELIEFERT)

# Ereignisarten
(ANGELEGT, GEAENDERT, STATUS, POS_NEU, POS_GEAENDERT, POS_ENTFERNT, ABRUF_NEU, ABRUF_GEAENDERT, ABRUF_STATUS_E,
 LIEFERUNG, LOS_NEU, LOS_GEFERTIGT, LOS_STORNO, MATERIAL_KAUF, MATERIAL_VERBRAUCH, VERSION, PREIS_VORSCHLAG,
 PREIS_FREIGABE, PREIS_ABGELEHNT, PARAMETER, BINDUNG, NUMMER) = (
    "angelegt", "geaendert", "status", "position_neu", "position_geaendert", "position_entfernt", "abruf_neu",
    "abruf_geaendert", "abruf_status", "lieferung", "los_neu", "los_gefertigt", "los_storno", "material_kauf",
    "material_verbrauch", "kalkulation_version", "preis_vorschlag", "preis_freigabe", "preis_abgelehnt", "parameter",
    "preisbindung", "nummer")
ART_TEXT = {ANGELEGT: "Rahmenauftrag angelegt", GEAENDERT: "Vertragsdaten geändert", STATUS: "Status geändert",
            POS_NEU: "Position ergänzt", POS_GEAENDERT: "Position geändert", POS_ENTFERNT: "Position entfernt",
            ABRUF_NEU: "Abruf angelegt", ABRUF_GEAENDERT: "Abruf geändert", ABRUF_STATUS_E: "Abrufstatus",
            LIEFERUNG: "Lieferung", LOS_NEU: "Fertigungslos geplant", LOS_GEFERTIGT: "Fertigungslos gefertigt",
            LOS_STORNO: "Fertigungslos storniert", MATERIAL_KAUF: "Material gekauft",
            MATERIAL_VERBRAUCH: "Material verbraucht", VERSION: "Kalkulation festgeschrieben",
            PREIS_VORSCHLAG: "Preisänderung vorgeschlagen", PREIS_FREIGABE: "Preisänderung freigegeben",
            PREIS_ABGELEHNT: "Preisänderung abgelehnt", PARAMETER: "Kalkulationsparameter geändert",
            BINDUNG: "Preisbindung geändert", NUMMER: "Endgültige Nummer"}

# Vertragsfelder (Name, Titel)
KOPF = (("kunde", "Kunde"), ("kundennr", "Kundennummer"), ("projekt", "Projektbezeichnung"),
        ("kunden_nr", "Rahmennummer des Kunden"), ("start", "Startdatum"), ("ende", "Enddatum"),
        ("jahresbedarf", "Geplanter Jahresbedarf [Stk.]"), ("gesamtpreis", "Vereinbarter Gesamtpreis [€]"),
        ("min_abruf", "Mindestabrufmenge [Stk.]"), ("max_abruf", "Maximale Abrufmenge [Stk.]"),
        ("abrufe_geplant", "Geplante Anzahl Abrufe"), ("intervall", "Lieferintervall [Monate]"),
        ("lieferorte", "Lieferorte"), ("zahlung", "Zahlungsbedingungen"), ("preis_gueltig", "Preisgültigkeit bis"),
        ("lieferbedingungen", "Lieferbedingungen"), ("abrufbedingungen", "Abrufbedingungen"),
        ("bedingungen", "Individuelle Vertragsbedingungen"), ("angebot_uid", "Angebot"),
        ("menge_sperrt", "Rahmenmenge sperrt weitere Abrufe (ja/nein)"), ("bemerkung", "Bemerkung"))
KOPF_TITEL = dict(KOPF)
POS_FELDER = ("pos", "artikel", "bezeichnung", "menge", "preis", "kg_teil", "jahresbedarf")
ABRUF_FELDER = ("datum", "ist_datum", "mengen", "lieferort", "auftragsnr", "bemerkung")

MUSTER = re.compile(r"^RA-(\d{4})-(\d{4,})$")
NUMMERN_ORDNER = "RA-Nummern"
ORDNER = "Rahmen"
DATEI_FORMAT = 1


class RahmenFehler(ValueError):
    """Aktion nicht möglich (Text für den Benutzer)."""


def einrichten(con):
    from . import db_verbindung
    da = set(db_verbindung.tabellen(con))
    for sql in TABELLEN_SQL:
        con.execute(sql)
    if "rahmen_kopf" not in da and con.execute("SELECT 1 FROM rahmen_ereignisse LIMIT 1").fetchone():
        _aufbauen(con)


def _jetzt():
    # Mikrosekunden: mehrere Ereignisse derselben Sekunde behalten ihre Reihenfolge auch auf anderen Plätzen
    return datetime.datetime.now().isoformat(timespec="microseconds")


def _json(d):
    return json.dumps(d, ensure_ascii=False, sort_keys=True, default=str)


def _laden(text, vorgabe=None):
    if isinstance(text, (dict, list)):
        return text
    try:
        d = json.loads(text) if text else vorgabe
    except (TypeError, ValueError):
        return vorgabe
    return d if d is not None else vorgabe


def _n(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def benutzer(db):
    from . import teilen
    return teilen.kuerzel(db) or "", str(db.einstellung("benutzer_name") or "").strip()


# ------------------------------------------------------------------ Ereignisse
_FELDER = ("uid", "rahmen", "art", "ziel", "feld", "alt", "neu", "daten", "bemerkung", "wer", "name", "rechner", "am",
           "vorher")


def _pruefsumme(e):
    return hashlib.sha256(_json({n: e.get(n) for n in _FELDER}).encode("utf-8")).hexdigest()[:24]


def _letzte_pruef(con, rechner):
    r = con.execute("SELECT pruef FROM rahmen_ereignisse WHERE rechner=? ORDER BY id DESC LIMIT 1",
                    (rechner,)).fetchone()
    return r[0] if r else None


def _ereignis(db, rahmen, art, *, ziel=None, feld=None, alt=None, neu=None, daten=None, bemerkung="", am=None,
              rechner=None):
    wer, name = benutzer(db)
    rechner = rechner or socket.gethostname()
    e = dict(uid=uuid.uuid4().hex, rahmen=rahmen, art=art, ziel=ziel, feld=feld,
             alt=None if alt is None else _wert_text(alt), neu=None if neu is None else _wert_text(neu),
             daten=_json(daten) if daten is not None else None, bemerkung=str(bemerkung or "") or None, wer=wer,
             name=name or None, rechner=rechner, am=am or _jetzt(), vorher=_letzte_pruef(db.con, rechner))
    e["pruef"] = _pruefsumme(e)
    db.con.execute(f"INSERT INTO rahmen_ereignisse ({', '.join(_FELDER)}, pruef) VALUES "
                   f"({', '.join('?' * (len(_FELDER) + 1))})", [e[n] for n in _FELDER] + [e["pruef"]])
    _speichern(db.con, rahmen)
    return e


def _wert_text(w):
    return _json(w)          # immer JSON, damit „007“ Text bleibt und 7 eine Zahl


def _wert(text):
    """Feldwert aus dem Ereignis: JSON (Zahl, Liste, dict) oder Text."""
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def ereignisse(db, rahmen=None):
    sql = "SELECT * FROM rahmen_ereignisse" + (" WHERE rahmen=?" if rahmen else "") + " ORDER BY am, id"
    out = []
    for r in db.con.execute(sql, (rahmen,) if rahmen else ()):
        e = dict(r)
        e["daten"] = _laden(e.get("daten"), None)
        out.append(e)
    return out


def pruefen(db, rahmen=None):
    """uid der Einträge, deren Inhalt nicht mehr zur Prüfsumme passt (nachträglich geändert)."""
    return [e["uid"] for e in (dict(r) for r in db.con.execute(
        "SELECT * FROM rahmen_ereignisse" + (" WHERE rahmen=?" if rahmen else ""), (rahmen,) if rahmen else ()))
        if _pruefsumme(e) != e.get("pruef")]


# ------------------------------------------------------------------ Sicht (Zustand aus den Ereignissen)
def leer(uid):
    return dict(uid=uid, nummer=None, status=ENTWURF, positionen=[], abrufe=[], lose=[], material=dict(kaeufe=[],
                verbrauch=[]), versionen=[], version=None, preisbindung={}, parameter={}, vorschlaege=[],
                konflikte=[], angelegt=None, geaendert=None, **{n: None for n, _ in KOPF})


def _finde(liste, uid):
    return next((x for x in liste if x.get("uid") == uid), None)


def anwenden(z, e):
    """Ein Ereignis auf den Zustand z (dict) anwenden. Reine Funktion auf z (ändert z)."""
    art, d = e["art"], _laden(e.get("daten"), {}) or {}
    neu = _wert(e.get("neu"))
    z["geaendert"] = max(z.get("geaendert") or "", e["am"])

    def setzen(obj, feld):
        alt = _wert(e.get("alt"))
        if e.get("alt") is not None and obj.get(feld) != alt and obj.get(feld) != neu:
            z["konflikte"].append(dict(feld=feld, ziel=e.get("ziel"), war=obj.get(feld), erwartet=alt, neu=neu,
                                       wer=e.get("wer"), am=e["am"]))
        obj[feld] = neu
    if art == ANGELEGT:
        for n, w in (d.get("kopf") or {}).items():
            z[n] = w
        z["nummer"] = d.get("nummer")
        z["status"] = d.get("status") or ENTWURF
        z["angelegt"] = e["am"]
        for p in d.get("positionen") or ():
            z["positionen"].append(dict(p))
        z["parameter"] = dict(d.get("parameter") or {})
        z["preisbindung"] = dict(d.get("preisbindung") or {})
    elif art == GEAENDERT:
        setzen(z, e["feld"])
    elif art == STATUS:
        z["status"] = neu
    elif art == NUMMER:
        z["nummer"] = neu
    elif art == POS_NEU:
        if not _finde(z["positionen"], d.get("uid")):
            z["positionen"].append(dict(d))
    elif art == POS_GEAENDERT:
        p = _finde(z["positionen"], e.get("ziel"))
        if p is not None:
            setzen(p, e["feld"])
    elif art == POS_ENTFERNT:
        z["positionen"] = [p for p in z["positionen"] if p.get("uid") != e.get("ziel")]
    elif art == ABRUF_NEU:
        if not _finde(z["abrufe"], d.get("uid")):
            a = dict(d)
            a.setdefault("status", GEPLANT)
            a.setdefault("geliefert", {})
            a.setdefault("lieferungen", [])
            a["nr"] = max((x.get("nr") or 0 for x in z["abrufe"]), default=0) + 1
            z["abrufe"].append(a)
    elif art == ABRUF_GEAENDERT:
        a = _finde(z["abrufe"], e.get("ziel"))
        if a is not None:
            setzen(a, e["feld"])
    elif art == ABRUF_STATUS_E:
        a = _finde(z["abrufe"], e.get("ziel"))
        if a is not None:
            a["status"] = neu
            if neu == STORNIERT:
                a["storno_grund"] = e.get("bemerkung")
    elif art == LIEFERUNG:
        a = _finde(z["abrufe"], e.get("ziel"))
        if a is not None:
            for p, q in (d.get("mengen") or {}).items():
                a["geliefert"][p] = _n(a["geliefert"].get(p)) + _n(q)
            a["lieferungen"].append(dict(datum=d.get("datum"), mengen=d.get("mengen"), lieferschein=d.get("lieferschein")))
            a["ist_datum"] = d.get("datum") or a.get("ist_datum")
            voll = all(_n(a["geliefert"].get(p)) >= _n(q) - 1e-9 for p, q in (a.get("mengen") or {}).items())
            if a.get("status") not in (STORNIERT, ABGESCHLOSSEN_A):
                a["status"] = GELIEFERT if voll else TEILGELIEFERT
    elif art == LOS_NEU:
        if not _finde(z["lose"], d.get("uid")):
            z["lose"].append(dict(d, status="geplant", gefertigt={}))
    elif art == LOS_GEFERTIGT:
        los = _finde(z["lose"], e.get("ziel"))
        if los is not None:
            los["gefertigt"] = dict(d.get("mengen") or los.get("mengen") or {})
            los["status"] = "gefertigt"
            los["fertig_am"] = d.get("datum")
    elif art == LOS_STORNO:
        los = _finde(z["lose"], e.get("ziel"))
        if los is not None:
            los["status"] = "storniert"
    elif art == MATERIAL_KAUF:
        z["material"]["kaeufe"].append(dict(d, uid=e["uid"]))
    elif art == MATERIAL_VERBRAUCH:
        z["material"]["verbrauch"].append(dict(d, uid=e["uid"]))
    elif art == VERSION:
        v = dict(d, nr=len(z["versionen"]) + 1, am=e["am"], wer=e.get("wer"))
        z["versionen"].append(v)
        z["version"] = v
    elif art == PARAMETER:
        z["parameter"] = dict(d)
    elif art == BINDUNG:
        z["preisbindung"] = dict(d)
    elif art == PREIS_VORSCHLAG:
        z["vorschlaege"].append(dict(d, uid=e["uid"], am=e["am"], wer=e.get("wer"), status="offen",
                                     bemerkung=e.get("bemerkung")))
    elif art in (PREIS_FREIGABE, PREIS_ABGELEHNT):
        v = _finde(z["vorschlaege"], e.get("ziel"))
        if v is not None and v["status"] == "offen":
            v["status"] = "freigegeben" if art == PREIS_FREIGABE else "abgelehnt"
            v["entschieden"] = dict(am=e["am"], wer=e.get("wer"))
            if art == PREIS_FREIGABE:
                for p in z["positionen"]:
                    k = str(p.get("pos"))
                    if k in (v.get("preise") or {}):
                        p.setdefault("preis_verlauf", []).append(dict(alt=p.get("preis"), neu=v["preise"][k],
                                                                      ab=v.get("ab"), am=e["am"], wer=e.get("wer")))
                        p["preis"] = v["preise"][k]
    z["vorschlaege_offen"] = sum(1 for v in z["vorschlaege"] if v.get("status") == "offen")
    return z


def _zustand(con, rahmen):
    from . import db_verbindung
    spalten = db_verbindung.spalten(con, "rahmen_ereignisse")
    zeilen = [dict(zip(spalten, r)) for r in con.execute(
        "SELECT * FROM rahmen_ereignisse WHERE rahmen=? ORDER BY am, id", (rahmen,))]
    z = leer(rahmen)
    for e in sorted(zeilen, key=lambda e: (e["art"] != ANGELEGT, e["am"], e["id"])):
        anwenden(z, e)
    return z


def _speichern(con, rahmen):
    z = _zustand(con, rahmen)
    con.execute("DELETE FROM rahmen_kopf WHERE uid=?", (rahmen,))
    con.execute("INSERT INTO rahmen_kopf (uid, nummer, kunde, status, ende, daten, geaendert) VALUES "
                "(?, ?, ?, ?, ?, ?, ?)", (rahmen, z.get("nummer"), z.get("kunde"), z.get("status"), z.get("ende"),
                                          _json(z), z.get("geaendert")))


def _aufbauen(con):
    con.execute("DELETE FROM rahmen_kopf")
    for (r,) in con.execute("SELECT DISTINCT rahmen FROM rahmen_ereignisse").fetchall():
        _speichern(con, r)


def aufbauen(db):
    with db.con:
        _aufbauen(db.con)


def sicht(db, uid):
    r = db.con.execute("SELECT daten FROM rahmen_kopf WHERE uid=?", (uid,)).fetchone()
    return _laden(r[0], None) if r else None


def alle(db):
    return [_laden(r[0], {}) for r in db.con.execute("SELECT daten FROM rahmen_kopf ORDER BY nummer")]


# ------------------------------------------------------------------ Nummern
def zaehler(nr):
    m = MUSTER.match(str(nr or "").strip())
    return int(m.group(2)) if m else 0


def neue_nummer(db, datum=None):
    """Nächste Nummer RA-JJJJ-NNNN; mit gemeinsamem Ordner dort reserviert (wie die Auftragsnummern)."""
    from . import teilen
    jahr = str(datum or datetime.date.today().isoformat())[:4]
    n = max([zaehler(r[0]) for r in db.con.execute("SELECT nummer FROM rahmen_kopf")]
            + [zaehler(db.einstellung("rahmen_letzte_nummer"))], default=0)
    if teilen.aktiv(db):
        w = teilen.weg(db)
        try:
            if w is None or not w.erreichbar():
                raise FileNotFoundError(str(w))
            n = max(n, w.nummer_hoechste(NUMMERN_ORDNER))
            while True:
                n += 1
                if w.nummer_belegen(NUMMERN_ORDNER, n, f"RA-{jahr}-{n:04d}\n{teilen.kuerzel(db)}\n{_jetzt()}\n"):
                    break
        except OSError:
            k = teilen.kuerzel(db)
            return f"RA-V-{k}-{uuid.uuid4().hex[:6]}"
    else:
        n += 1
    nr = f"RA-{jahr}-{n:04d}"
    db._einstellung_schreiben("rahmen_letzte_nummer", nr)
    return nr


# ------------------------------------------------------------------ Aktionen
def _recht(db):
    from . import rollen
    rollen.pruefen(db, rollen.B_AUFTRAEGE, fehler=RahmenFehler)


def anlegen(db, kopf=None, positionen=(), parameter=None, preisbindung=None, bemerkung="", am=None):
    """Neuen Rahmenauftrag anlegen. positionen = [dict(pos, artikel, bezeichnung, menge, preis, kg_teil)].
    Ergebnis: uid."""
    _recht(db)
    kopf = {n: w for n, w in (kopf or {}).items() if n in KOPF_TITEL}
    if not str(kopf.get("kunde") or "").strip():
        raise RahmenFehler("Rahmenauftrag: Kunde fehlt.")
    uid = uuid.uuid4().hex
    pos = [dict({n: p.get(n) for n in POS_FELDER}, uid=p.get("uid") or uuid.uuid4().hex) for p in positionen]
    with db.con:
        nr = neue_nummer(db, kopf.get("start"))
        _ereignis(db, uid, ANGELEGT, daten=dict(kopf=kopf, nummer=nr, status=ENTWURF, positionen=pos,
                                                parameter=parameter or {}, preisbindung=preisbindung or {}),
                  bemerkung=bemerkung, am=am)
    return uid


def aus_angebot(db, angebot_id, kopf=None, mengen=None):
    """Rahmenauftrag aus einem Angebot: Kunde, Projekt, Positionen (ohne Muster) mit Stückpreis aus der
    Kalkulation; Rahmenmenge je Position aus mengen ({pos: Stück}) oder Jahresmenge des Abruf-Angebots."""
    from . import abruf, auftraege
    a = db.angebot(angebot_id)
    if not a:
        raise RahmenFehler("Angebot nicht gefunden.")
    ab = abruf.daten(a)
    pos = []
    for p in db.positionen(angebot_id):
        if p.get("muster") == "ja" or not p.get("pos"):
            continue
        k = str(p.get("pos"))
        menge = _n((mengen or {}).get(k)) or (abruf.jahr_stueck(p, ab) if ab else _n(p.get("stueck")))
        pos.append(dict(pos=k, artikel=p.get("artikel"), bezeichnung=p.get("bezeichnung"), menge=menge,
                        preis=p.get("preis_teil"), kg_teil=p.get("gewicht_teil")))
    start = datetime.date.today()
    lauf = int(_n(a.get("abruf_laufzeit")) or 12)
    k = dict(kunde=a.get("kunde"), kundennr=a.get("kundennr"), projekt=a.get("projekt") or a.get("bezeichnung"),
             start=start.isoformat(), ende=_plus_monate(start, lauf).isoformat(), angebot_uid=auftraege.angebot_uid(db, angebot_id),
             zahlung=a.get("zahlungsbedingung") or a.get("zahlung"))
    k.update(kopf or {})
    return anlegen(db, k, pos, bemerkung=f"aus Angebot {a.get('nummer') or angebot_id}")


def _plus_monate(d, n):
    m = d.month - 1 + n
    j, m = d.year + m // 12, m % 12 + 1
    import calendar
    return datetime.date(j, m, min(d.day, calendar.monthrange(j, m)[1]))


def _z(db, uid):
    z = sicht(db, uid)
    if z is None:
        raise RahmenFehler("Rahmenauftrag nicht gefunden.")
    return z


def aendern(db, uid, feld, wert, bemerkung=""):
    if feld not in KOPF_TITEL:
        raise RahmenFehler(f"Unbekanntes Feld {feld}.")
    z = _z(db, uid)
    if z.get(feld) == wert:
        return None
    with db.con:
        return _ereignis(db, uid, GEAENDERT, feld=feld, alt=z.get(feld), neu=wert, bemerkung=bemerkung)


def status_setzen(db, uid, status, bemerkung=""):
    if status not in STATUS_LISTE:
        raise RahmenFehler(f"Unbekannter Status {status}.")
    z = _z(db, uid)
    if z.get("status") == status:
        return None
    with db.con:
        return _ereignis(db, uid, STATUS, alt=z.get("status"), neu=status, bemerkung=bemerkung)


def position_neu(db, uid, werte):
    p = dict({n: werte.get(n) for n in POS_FELDER}, uid=uuid.uuid4().hex)
    with db.con:
        _ereignis(db, uid, POS_NEU, ziel=p["uid"], daten=p)
    return p["uid"]


def position_aendern(db, uid, pos_uid, feld, wert, bemerkung=""):
    if feld not in POS_FELDER:
        raise RahmenFehler(f"Unbekanntes Feld {feld}.")
    z = _z(db, uid)
    p = _finde(z["positionen"], pos_uid)
    if p is None:
        raise RahmenFehler("Position nicht gefunden.")
    if feld == "preis" and z.get("status") == AKTIV:
        # Vertragspreise ändern sich nie still: Änderung nur über Vorschlag + Freigabe
        raise RahmenFehler("Vertragspreis: Änderung nur über „Preisänderung vorschlagen“ mit Freigabe.")
    with db.con:
        return _ereignis(db, uid, POS_GEAENDERT, ziel=pos_uid, feld=feld, alt=p.get(feld), neu=wert,
                         bemerkung=bemerkung)


def position_entfernen(db, uid, pos_uid, bemerkung=""):
    z = _z(db, uid)
    p = _finde(z["positionen"], pos_uid)
    if p is None:
        return None
    if any(_n((a.get("mengen") or {}).get(str(p.get("pos")))) for a in z["abrufe"] if a.get("status") != STORNIERT):
        raise RahmenFehler("Position hat Abrufe: erst die Abrufe stornieren.")
    with db.con:
        return _ereignis(db, uid, POS_ENTFERNT, ziel=pos_uid, daten=p, bemerkung=bemerkung)


def _pruef_abruf(z, mengen, ohne=None):
    """Warnung (Text) oder RahmenFehler, wenn ein Abruf die Rahmenmenge überschreitet (sperrt nur mit
    menge_sperrt = ja, sonst Warnung wie SAP/Dynamics ohne „Max is enforced“)."""
    texte = []
    for p in z["positionen"]:
        k = str(p.get("pos"))
        q = _n(mengen.get(k))
        if not q:
            continue
        schon = sum(_n((a.get("mengen") or {}).get(k)) for a in z["abrufe"]
                    if a.get("status") != STORNIERT and a.get("uid") != ohne)
        if schon + q > _n(p.get("menge")) + 1e-9:
            texte.append(f"Pos. {k}: {schon + q:g} von {_n(p.get('menge')):g} Stück")
    if texte:
        t = "Rahmenmenge überschritten: " + "; ".join(texte)
        if str(z.get("menge_sperrt") or "").lower() == "ja":
            raise RahmenFehler(t)
        return t
    return ""


def abruf_neu(db, uid, datum, mengen, status=GEPLANT, lieferort=None, auftragsnr=None, bemerkung="", am=None):
    """Abruf anlegen (mengen = {pos: Stück}). Ergebnis (abruf_uid, Warnung)."""
    z = _z(db, uid)
    mengen = {str(p): _n(q) for p, q in (mengen or {}).items() if _n(q) > 0}
    if not mengen:
        raise RahmenFehler("Abruf ohne Menge.")
    unbekannt = set(mengen) - {str(p.get("pos")) for p in z["positionen"]}
    if unbekannt:
        raise RahmenFehler(f"Position {', '.join(sorted(unbekannt))} gehört nicht zum Rahmen.")
    warn = _pruef_abruf(z, mengen)
    a = dict(uid=uuid.uuid4().hex, datum=str(datum)[:10], mengen=mengen, status=status, lieferort=lieferort,
             auftragsnr=auftragsnr, bemerkung=bemerkung or None)
    with db.con:
        _ereignis(db, uid, ABRUF_NEU, ziel=a["uid"], daten=a, am=am)
    return a["uid"], warn


def plan_vorschlag(z, anzahl, erster, intervall=1, offen=True):
    """Gleichmäßiger Abrufplan: anzahl Abrufe ab erster (Datum) alle intervall Monate, die (noch nicht verplante)
    Rahmenmenge je Position ganzzahlig verteilt (Rest auf die ersten Abrufe). [(Datum ISO, {pos: Stück})]."""
    anzahl = max(int(anzahl or 0), 0)
    d0 = datetime.date.fromisoformat(str(erster)[:10])
    k = kennzahlen(z)
    out = [(_plus_monate(d0, int(i * (intervall or 1))).isoformat(), {}) for i in range(anzahl)]
    for p in k["positionen"]:
        menge = int(max(p["verfuegbar"], 0) if offen else p["menge"])
        if not anzahl or menge <= 0:
            continue
        je, rest = divmod(menge, anzahl)
        for i, (_, m) in enumerate(out):
            q = je + (1 if i < rest else 0)
            if q:
                m[p["pos"]] = q
    return [x for x in out if x[1]]


def abrufplan(db, uid, termine):
    """Mehrere geplante Abrufe auf einmal: termine = [(datum, {pos: Stück})]."""
    return [abruf_neu(db, uid, d, m)[0] for d, m in termine]


def abruf_aendern(db, uid, abruf_uid, feld, wert, bemerkung="", alt=None, rechner=None):
    """Abruf ändern (Menge = mengen, verschieben = datum, …). alt: der Wert, den der Benutzer gesehen hat (für die
    Konflikterkennung beim Abgleich; Vorgabe = aktueller Wert). Ergebnis Warnung (Text)."""
    if feld not in ABRUF_FELDER:
        raise RahmenFehler(f"Unbekanntes Feld {feld}.")
    z = _z(db, uid)
    a = _finde(z["abrufe"], abruf_uid)
    if a is None:
        raise RahmenFehler("Abruf nicht gefunden.")
    if a.get("status") in (STORNIERT, ABGESCHLOSSEN_A):
        raise RahmenFehler(f"Abruf {a['nr']} ist {a['status']}.")
    warn = ""
    if feld == "mengen":
        wert = {str(p): _n(q) for p, q in (wert or {}).items() if _n(q) > 0}
        warn = _pruef_abruf(z, wert, ohne=abruf_uid)
    if feld == "datum":
        wert = str(wert)[:10]
    with db.con:
        _ereignis(db, uid, ABRUF_GEAENDERT, ziel=abruf_uid, feld=feld, alt=a.get(feld) if alt is None else alt,
                  neu=wert, bemerkung=bemerkung, rechner=rechner)
    return warn


def abruf_status(db, uid, abruf_uid, status, bemerkung=""):
    if status not in ABRUF_STATUS:
        raise RahmenFehler(f"Unbekannter Abrufstatus {status}.")
    z = _z(db, uid)
    a = _finde(z["abrufe"], abruf_uid)
    if a is None:
        raise RahmenFehler("Abruf nicht gefunden.")
    if status == STORNIERT and any(_n(v) for v in (a.get("geliefert") or {}).values()):
        raise RahmenFehler(f"Abruf {a['nr']} ist schon (teilweise) geliefert und kann nicht storniert werden.")
    if a.get("status") == status:
        return None
    with db.con:
        return _ereignis(db, uid, ABRUF_STATUS_E, ziel=abruf_uid, alt=a.get("status"), neu=status,
                         bemerkung=bemerkung)


def abruf_stornieren(db, uid, abruf_uid, grund=""):
    return abruf_status(db, uid, abruf_uid, STORNIERT, grund)


def lieferung(db, uid, abruf_uid, mengen=None, datum=None, lieferschein=None):
    """Lieferung zu einem Abruf (mengen None = alles Offene des Abrufs)."""
    z = _z(db, uid)
    a = _finde(z["abrufe"], abruf_uid)
    if a is None or a.get("status") == STORNIERT:
        raise RahmenFehler("Abruf nicht gefunden oder storniert.")
    if mengen is None:
        mengen = {p: max(_n(q) - _n((a.get("geliefert") or {}).get(p)), 0) for p, q in (a.get("mengen") or {}).items()}
    mengen = {str(p): _n(q) for p, q in mengen.items() if _n(q) > 0}
    with db.con:
        return _ereignis(db, uid, LIEFERUNG, ziel=abruf_uid,
                         daten=dict(mengen=mengen, datum=str(datum or datetime.date.today())[:10],
                                    lieferschein=lieferschein))


def los_neu(db, uid, datum, mengen, abrufe=(), bemerkung=""):
    los = dict(uid=uuid.uuid4().hex, datum=str(datum)[:10], mengen={str(p): _n(q) for p, q in mengen.items()},
               abrufe=list(abrufe))
    with db.con:
        _ereignis(db, uid, LOS_NEU, ziel=los["uid"], daten=los, bemerkung=bemerkung)
    return los["uid"]


def los_gefertigt(db, uid, los_uid, mengen=None, datum=None):
    with db.con:
        return _ereignis(db, uid, LOS_GEFERTIGT, ziel=los_uid,
                         daten=dict(mengen=mengen, datum=str(datum or datetime.date.today())[:10]))


def los_stornieren(db, uid, los_uid, grund=""):
    with db.con:
        return _ereignis(db, uid, LOS_STORNO, ziel=los_uid, bemerkung=grund)


def material_kauf(db, uid, kg, eur, datum=None, lieferant=None, bemerkung=""):
    """Für diesen Rahmen gekauftes Material (Materialkonto, kein allgemeines Restelager)."""
    with db.con:
        return _ereignis(db, uid, MATERIAL_KAUF, daten=dict(kg=_n(kg), eur=_n(eur), lieferant=lieferant,
                                                            datum=str(datum or datetime.date.today())[:10]),
                         bemerkung=bemerkung)


def material_verbrauch(db, uid, kg, datum=None, los=None):
    with db.con:
        return _ereignis(db, uid, MATERIAL_VERBRAUCH, daten=dict(kg=_n(kg), los=los,
                                                                 datum=str(datum or datetime.date.today())[:10]))


def parameter_setzen(db, uid, werte, bemerkung=""):
    """Kalkulationsparameter des Rahmens (nur von Hand, mit Protokoll)."""
    z = _z(db, uid)
    if z.get("parameter") == werte:
        return None
    with db.con:
        return _ereignis(db, uid, PARAMETER, alt=z.get("parameter"), daten=dict(werte), bemerkung=bemerkung)


def preisbindung_setzen(db, uid, werte, bemerkung=""):
    from . import rahmen_kalk as rk
    if (werte or {}).get("modell") and werte["modell"] not in rk.PREISMODELLE:
        raise RahmenFehler("Unbekanntes Preismodell.")
    with db.con:
        return _ereignis(db, uid, BINDUNG, alt=_z(db, uid).get("preisbindung"), daten=dict(werte or {}),
                         bemerkung=bemerkung)


def version_festschreiben(db, uid, daten, bemerkung=""):
    """Kalkulation festschreiben (Eingaben, Kostenmodell, Parameter, Preisbasis des Angebots, Ergebnis). Spätere
    Änderungen an Stammdaten oder Einstellungen berühren diese Version nicht."""
    with db.con:
        _ereignis(db, uid, VERSION, daten=copy.deepcopy(daten), bemerkung=bemerkung)
    return _z(db, uid)["version"]["nr"]


def preis_vorschlagen(db, uid, preise, grund, ab=None, auswirkung=None):
    """Preisänderung vorschlagen ({pos: neuer Stückpreis}); gilt erst nach preis_freigeben."""
    with db.con:
        e = _ereignis(db, uid, PREIS_VORSCHLAG, daten=dict(preise={str(p): round(_n(v), 4) for p, v in preise.items()},
                                                           ab=ab, auswirkung=auswirkung), bemerkung=grund)
    return e["uid"]


def preis_freigeben(db, uid, vorschlag_uid, bemerkung=""):
    z = _z(db, uid)
    v = _finde(z["vorschlaege"], vorschlag_uid)
    if v is None or v.get("status") != "offen":
        raise RahmenFehler("Kein offener Vorschlag.")
    with db.con:
        return _ereignis(db, uid, PREIS_FREIGABE, ziel=vorschlag_uid, bemerkung=bemerkung)


def preis_ablehnen(db, uid, vorschlag_uid, bemerkung=""):
    with db.con:
        return _ereignis(db, uid, PREIS_ABGELEHNT, ziel=vorschlag_uid, bemerkung=bemerkung)


# ------------------------------------------------------------------ Kennzahlen
def abruf_menge(a):
    return sum(_n(v) for v in (a.get("mengen") or {}).values())


def kennzahlen(z, heute=None):
    """Mengen und Werte des Rahmens: je Position menge, abgerufen (vom Kunden abgerufen, ohne nur geplante), geplant,
    geliefert, offen (= menge − geliefert), verfuegbar (= menge − abgerufen − geplant), gefertigt, bestand
    (Fertigteile = gefertigt − geliefert, je Los nur die Lieferungen seiner Abrufe), restwert; dazu Summen, Abrufliste, überfällige Abrufe, Material."""
    heute = str(heute or datetime.date.today().isoformat())[:10]
    pos = []
    for p in z.get("positionen") or ():
        k = str(p.get("pos"))
        abg = gepl = gel = 0.0
        for a in z.get("abrufe") or ():
            q = _n((a.get("mengen") or {}).get(k))
            if a.get("status") == STORNIERT:
                continue
            if a.get("status") == GEPLANT:
                gepl += q
            else:
                abg += q
            gel += _n((a.get("geliefert") or {}).get(k))
        fertig = [los for los in z.get("lose") or () if los.get("status") == "gefertigt"]
        gef = sum(_n((los.get("gefertigt") or {}).get(k)) for los in fertig)
        # Fertigteilbestand: ein Los mit Abrufliste wird nur durch Lieferungen dieser Abrufe abgebaut; Lieferungen
        # vor jedem erfassten Los (ohne Los gefertigt) zählen nicht gegen spätere Lose
        nrs = {int(_n(x)) for los in fertig for x in los.get("abrufe") or ()}
        gef_mit = sum(_n((los.get("gefertigt") or {}).get(k)) for los in fertig if los.get("abrufe"))
        gel_mit = sum(_n((a.get("geliefert") or {}).get(k)) for a in z.get("abrufe") or ()
                      if int(_n(a.get("nr"))) in nrs)
        bestand = max(gef_mit - gel_mit, 0.0) + max(gef - gef_mit - (gel - gel_mit), 0.0)
        menge, preis = _n(p.get("menge")), _n(p.get("preis"))
        pos.append(dict(p, pos=k, menge=menge, abgerufen=abg, geplant=gepl, geliefert=gel, offen=max(menge - gel, 0.0),
                        verfuegbar=menge - abg - gepl, gefertigt=gef, bestand=bestand,
                        restwert=max(menge - gel, 0.0) * preis, wert=menge * preis, kg_teil=_n(p.get("kg_teil"))))
    kg_je = {p["pos"]: p["kg_teil"] for p in pos}
    abrufe = []
    for a in sorted(z.get("abrufe") or (), key=lambda a: (a.get("datum") or "", a.get("nr") or 0)):
        q = abruf_menge(a)
        abrufe.append(dict(a, menge=q, geliefert_menge=sum(_n(v) for v in (a.get("geliefert") or {}).values()),
                           kg=sum(_n(v) * kg_je.get(p, 0.0) for p, v in (a.get("mengen") or {}).items()),
                           wert=sum(_n(v) * _n(next((x["preis"] for x in pos if x["pos"] == p), 0))
                                    for p, v in (a.get("mengen") or {}).items())))
    ueberf = [a for a in abrufe if a.get("status") in OFFEN_A and (a.get("datum") or "9") < heute]
    m = z.get("material") or {}
    gek_kg = sum(_n(x.get("kg")) for x in m.get("kaeufe") or ())
    gek_eur = sum(_n(x.get("eur")) for x in m.get("kaeufe") or ())
    verb_kg = sum(_n(x.get("kg")) for x in m.get("verbrauch") or ())
    bestand_kg = gek_kg - verb_kg
    material = dict(gekauft_kg=gek_kg, gekauft_eur=gek_eur, verbraucht_kg=verb_kg, bestand_kg=bestand_kg,
                    bestand_eur=bestand_kg * (gek_eur / gek_kg) if gek_kg else 0.0,
                    bedarf_offen_kg=sum((p["offen"] - p["bestand"]) * p["kg_teil"] for p in pos))
    material["noch_kaufen_kg"] = max(material["bedarf_offen_kg"] - bestand_kg, 0.0)
    s = lambda n: sum(p[n] for p in pos)       # noqa: E731
    return dict(positionen=pos, abrufe=abrufe, ueberfaellig=ueberf, material=material,
                menge=s("menge"), abgerufen=s("abgerufen"), geplant=s("geplant"), geliefert=s("geliefert"),
                offen=s("offen"), verfuegbar=s("verfuegbar"), gefertigt=s("gefertigt"), bestand=s("bestand"),
                wert=s("wert"), restwert=s("restwert"),
                ueber=[f"Pos. {p['pos']}" for p in pos if p["abgerufen"] + p["geplant"] > p["menge"] + 1e-9],
                offene_abrufe=[a for a in abrufe if a.get("status") in OFFEN_A],
                abrufe_plan=sum(1 for a in abrufe if a.get("status") != STORNIERT),
                abrufe_ist=sum(1 for a in abrufe if a.get("status") in (GELIEFERT, ABGESCHLOSSEN_A, TEILGELIEFERT)),
                storniert=sum(1 for a in abrufe if a.get("status") == STORNIERT))


def offene_abrufe_fuer_plan(z):
    """Restplan: offene Abrufe mit noch nicht gelieferter Menge, Fertigteilbestand schon abgezogen (bereits
    gefertigt wird nicht noch einmal gefertigt)."""
    k = kennzahlen(z)
    bestand = {p["pos"]: p["bestand"] for p in k["positionen"]}
    out = []
    for a in k["offene_abrufe"]:
        rest = {}
        for p, q in (a.get("mengen") or {}).items():
            r = _n(q) - _n((a.get("geliefert") or {}).get(p))
            nimm = min(bestand.get(p, 0.0), r)
            bestand[p] = bestand.get(p, 0.0) - nimm
            if r - nimm > 0:
                rest[p] = r - nimm
        if rest:
            out.append(dict(a, mengen=rest))
    return out


# ------------------------------------------------------------------ Dashboard
def dashboard(db, heute=None, marge_min=0.0, filter_=None):
    """Zeilen für die Übersicht: je Rahmen Kennzahlen, Ampel, Warnungen; filter_ = dict(kunde, artikel, status,
    ende_bis)."""
    from . import rahmen_kalk as rk
    f = filter_ or {}
    out = []
    for z in alle(db):
        if f.get("kunde") and f["kunde"].lower() not in str(z.get("kunde") or "").lower():
            continue
        if f.get("status") and z.get("status") != f["status"]:
            continue
        if f.get("artikel") and not any(f["artikel"].lower() in f"{p.get('artikel')} {p.get('bezeichnung')}".lower()
                                        for p in z.get("positionen") or ()):
            continue
        if f.get("ende_bis") and str(z.get("ende") or "9999") > f["ende_bis"]:
            continue
        k = kennzahlen(z, heute)
        w = rk.warnungen(z, heute, marge_min)
        out.append(dict(uid=z["uid"], nummer=z.get("nummer"), kunde=z.get("kunde"), projekt=z.get("projekt"),
                        status=z.get("status"), start=z.get("start"), ende=z.get("ende"), menge=k["menge"],
                        abgerufen=k["abgerufen"], geliefert=k["geliefert"], offen=k["offen"], wert=k["wert"],
                        restwert=k["restwert"], abrufe_offen=len(k["offene_abrufe"]),
                        ueberfaellig=len(k["ueberfaellig"]), material_kg=k["material"]["bestand_kg"],
                        marge=((z.get("version") or {}).get("ergebnis") or {}).get("marge"),
                        ampel=rk.ampel(w), warnungen=w))
    return out


def summen(zeilen):
    akt = [z for z in zeilen if z["status"] == AKTIV]
    return dict(aktiv=len(akt), volumen=sum(z["wert"] for z in akt), restwert=sum(z["restwert"] for z in akt),
                abgerufen=sum(z["abgerufen"] for z in akt), offen=sum(z["offen"] for z in akt),
                ueberfaellig=sum(z["ueberfaellig"] for z in zeilen), rot=sum(1 for z in zeilen if z["ampel"] == "rot"),
                gelb=sum(1 for z in zeilen if z["ampel"] == "gelb"))


# ------------------------------------------------------------------ Abgleich über den gemeinsamen Ordner
def _eigene(db):
    return [dict(r) for r in db.con.execute("SELECT * FROM rahmen_ereignisse WHERE rechner=? ORDER BY id",
                                            (socket.gethostname(),))]


def ordner_schreiben(db, rechner=None):
    """Eigene Ereignisse als Rahmen/<Kürzel>.json in den gemeinsamen Ordner. Ergebnis: Anzahl."""
    from . import teilen
    if not teilen.aktiv(db):
        return 0
    w = teilen.weg(db)
    if w is None or not w.erreichbar():
        return 0
    eigene = [{n: e.get(n) for n in _FELDER + ("pruef",)} for e in _eigene(db)]
    roh = json.dumps(dict(format=DATEI_FORMAT, kuerzel=teilen.kuerzel(db), stand=_jetzt(), ereignisse=eigene),
                     ensure_ascii=False).encode("utf-8")
    if w.datei_lesen(ORDNER, f"{teilen.kuerzel(db)}.json") != roh:
        w.datei_schreiben(roh, ORDNER, f"{teilen.kuerzel(db)}.json")
    return len(eigene)


def ereignisse_einlesen(db, liste_):
    """Fremde Ereignisse übernehmen (bekannte über uid übergangen), betroffene Rahmen neu rechnen."""
    neu, betroffen = 0, set()
    with db.con:
        for e in liste_:
            if not isinstance(e, dict) or not e.get("uid") or not e.get("rahmen") or not e.get("art"):
                continue
            if db.con.execute("SELECT 1 FROM rahmen_ereignisse WHERE uid=?", (e["uid"],)).fetchone():
                continue
            db.con.execute(f"INSERT INTO rahmen_ereignisse ({', '.join(_FELDER)}, pruef) VALUES "
                           f"({', '.join('?' * (len(_FELDER) + 1))})", [e.get(n) for n in _FELDER] + [e.get("pruef")])
            neu += 1
            betroffen.add(e["rahmen"])
        for r in betroffen:
            _speichern(db.con, r)
    return neu


def ordner_lesen(db):
    from . import teilen
    if not teilen.aktiv(db):
        return 0
    o = teilen.weg(db)
    u = o.unterordner(ORDNER) if o is not None else None
    if u is None or not u.is_dir():
        return 0
    ich = teilen.kuerzel(db)
    liste_ = []
    for p in sorted(u.glob("*.json")):
        if p.stem == ich:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("format") == DATEI_FORMAT:
            liste_ += d.get("ereignisse") or []
    return ereignisse_einlesen(db, liste_)


def protokoll(db, uid):
    """Lesbares Änderungsprotokoll: [(Zeit, Benutzer, Rechner, Was, Detail)]."""
    out = []
    for e in ereignisse(db, uid):
        was = ART_TEXT.get(e["art"], e["art"])
        if e.get("feld"):
            was += f": {KOPF_TITEL.get(e['feld'], e['feld'])}"
        det = ""
        if e.get("alt") is not None or e.get("neu") is not None:
            det = f"{e.get('alt') or '–'} → {e.get('neu') or '–'}"
        if e.get("bemerkung"):
            det = (det + " · " if det else "") + e["bemerkung"]
        out.append((e["am"], e.get("name") or e.get("wer") or "", e.get("rechner") or "", was, det))
    return out
