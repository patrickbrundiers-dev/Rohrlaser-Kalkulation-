"""Aufträge: Angebot in Auftrag übernehmen, Auftragsdaten mit lückenloser Historie (Plan Auftragsworkflow, Patrick
13.11.2026, Freigabe „Alle Empfehlungen“, Paket 1). Ohne Qt.

Ein Auftrag fasst ein oder mehrere beauftragte Angebote zusammen. Bei der Übernahme friert er ihren Stand ein: Kopf,
Positionen mit kalkulierten Zeiten, Kosten und Preisen, die Prüfsumme der Freigabe (fertigung.kennung) und die Dateien
des Angebotsordners (Zeichnungen, STEP/CAD). Das Angebot selbst bleibt, wie es ist; ändert es sich danach, zeigt der
Auftrag das an, und die Änderung kommt nur per „Änderung übernehmen“ (mit Vergleich) in den Auftrag.

Grundsatz: Alles, was am Auftrag geschieht, ist ein Ereignis (Tabelle auftrag_ereignisse), das nie geändert oder
gelöscht wird: angelegt, Angebot übernommen, Feld geändert (alt → neu), Status, Angebot aktualisiert … Jeder Eintrag
hat Zeitpunkt, Benutzer (Kürzel, Name), Rechner, Bemerkung und eine Prüfsumme, die den vorigen Eintrag desselben
Arbeitsplatzes einschließt; wer einen Eintrag nachträglich in der Datei ändert, fällt bei pruefen() auf. Die Tabellen
auftrag_kopf, auftrag_angebote und auftrag_positionen sind nur die daraus gerechnete Sicht (aufbauen()).

Mehrere Arbeitsplätze: Jeder Platz legt seine eigenen Ereignisse als Datei Auftraege/<Kürzel>.json in den gemeinsamen
Ordner (ordner_schreiben) und liest die der Kollegen (ordner_lesen); doppelte Ereignisse fallen über die Kennung (uid)
weg. Weil nie zwei Plätze denselben Eintrag überschreiben, gibt es dabei keine Konflikte. Später trägt dasselbe Format
den Abgleich über das Änderungsjournal der neuen Datenbank (Plan Datenbank 12.11.2026, „lokal speichern und
abgleichen“).

Auftragsnummer: eigener Nummernkreis AU-JJJJ-NNNNN, mit gemeinsamem Ordner dort reserviert (Unterordner AU-Nummern,
wie die Angebotsnummern), ohne Ordner lokal gezählt. Ist der Ordner gerade nicht erreichbar, bekommt der Auftrag eine
vorläufige Nummer AU-V-<Kürzel>-n; die endgültige kommt beim nächsten Abgleich (Ereignis „Nummer“).

Schutz gegen doppelte Aufträge: Ein Angebot gehört höchstens zu einem Auftrag (eindeutiger Index); die Übernahme
läuft in einer Transaktion und prüft das darin. Ein zweiter Klick liefert den schon angelegten Auftrag zurück.
"""
import datetime
import hashlib
import json
import re
import socket
import uuid

TABELLEN = ("auftrag_ereignisse", "auftrag_kopf", "auftrag_angebote", "auftrag_positionen")
TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS auftrag_ereignisse (id INTEGER PRIMARY KEY, uid TEXT NOT NULL UNIQUE, auftrag TEXT "
    "NOT NULL, art TEXT NOT NULL, ziel TEXT, feld TEXT, alt TEXT, neu TEXT, daten TEXT, bemerkung TEXT, wer TEXT, "
    "name TEXT, rechner TEXT, am TEXT NOT NULL, vorher TEXT, pruef TEXT)",
    "CREATE INDEX IF NOT EXISTS auftrag_ereignisse_auftrag ON auftrag_ereignisse (auftrag, am)",
    "CREATE TABLE IF NOT EXISTS auftrag_kopf (uid TEXT PRIMARY KEY, nummer TEXT, status TEXT, daten TEXT, angelegt TEXT, "
    "geaendert TEXT)",
    "CREATE TABLE IF NOT EXISTS auftrag_angebote (auftrag TEXT NOT NULL, angebot TEXT NOT NULL, nummer TEXT, "
    "kennung TEXT, stand TEXT, am TEXT, PRIMARY KEY (auftrag, angebot))",
    "CREATE UNIQUE INDEX IF NOT EXISTS auftrag_angebote_einmal ON auftrag_angebote (angebot)",
    "CREATE TABLE IF NOT EXISTS auftrag_positionen (uid TEXT PRIMARY KEY, auftrag TEXT NOT NULL, angebot TEXT, "
    "nr INTEGER, daten TEXT)",
    "CREATE INDEX IF NOT EXISTS auftrag_positionen_auftrag ON auftrag_positionen (auftrag, nr)",
)

# Ereignisarten (Text in der Historie)
ANGELEGT, UEBERNOMMEN, GEAENDERT, STATUS, AKTUALISIERT, NUMMER, MIGRIERT = (
    "angelegt", "angebot_uebernommen", "geaendert", "status", "angebot_aktualisiert", "nummer", "migriert")
POSITION_NEU, ANGEBOT_ENTFERNT = "position_neu", "angebot_entfernt"
ARBEITSGAENGE, PRUEFPUNKT, FREIGABE = "arbeitsgaenge", "av_pruefpunkt", "freigabe"     # Paket 3 (auftrag_av.py)
RUECKMELDUNG = "rueckmeldung"                                                         # Paket 4 (auftrag_produktion.py)
QS_PRUEFUNG, LIEFERUNG, DOKUMENT = "qs_pruefung", "lieferung", "dokument"            # Paket 5 (auftrag_qs.py)
ART_TEXT = {ANGELEGT: "Auftrag angelegt", UEBERNOMMEN: "Angebot übernommen", GEAENDERT: "Auftragsdaten geändert",
            STATUS: "Status geändert", AKTUALISIERT: "Änderung aus Angebot übernommen",
            NUMMER: "Endgültige Auftragsnummer", MIGRIERT: "Aus bestehendem Auftrag übernommen",
            POSITION_NEU: "Position im Auftrag ergänzt", ANGEBOT_ENTFERNT: "Angebot aus dem Auftrag gelöst",
            ARBEITSGAENGE: "Arbeitsgänge festgelegt", PRUEFPUNKT: "Arbeitsvorbereitung geprüft",
            FREIGABE: "Für die Produktion freigegeben", RUECKMELDUNG: "Rückmeldung",
            QS_PRUEFUNG: "Qualitätsprüfung", LIEFERUNG: "Auslieferung", DOKUMENT: "Dokument hinterlegt"}

# Auftragsstatus (Reihenfolge = Ablauf); „Verzögert“ ist ein Merkmal (Termin überschritten), kein Schritt
NEU, AV, MATERIAL_FEHLT, BEREIT, PRODUKTION, QS, TEILWEISE, FERTIG, AUSGELIEFERT, ABGESCHLOSSEN = (
    "Neu eingegangen", "Arbeitsvorbereitung", "Material fehlt", "Produktionsbereit", "In Produktion",
    "Qualitätskontrolle", "Teilweise fertiggestellt", "Fertiggestellt", "Ausgeliefert", "Abgeschlossen")
STATUS_LISTE = (NEU, AV, MATERIAL_FEHLT, BEREIT, PRODUKTION, QS, TEILWEISE, FERTIG, AUSGELIEFERT, ABGESCHLOSSEN)
OFFEN = tuple(s for s in STATUS_LISTE if s not in (AUSGELIEFERT, ABGESCHLOSSEN))
VERZOEGERT = "Verzögert"

# Kopffelder des Auftrags (Name, Titel); änderbar mit Historie
KOPF = (("kunde", "Kunde"), ("kundennr", "Kundennummer"), ("ansprechpartner", "Ansprechpartner"),
        ("projekt", "Projekt"), ("bestellnr", "Bestellnummer des Kunden"), ("auftragsdatum", "Auftragsdatum"),
        ("liefertermin", "Liefertermin"), ("verantwortlich", "Zuständig"),
        ("anforderungen", "Besondere Kundenanforderungen"), ("bemerkung", "Bemerkung"))
KOPF_TITEL = dict(KOPF)
POSITION_AENDERBAR = (("menge", "Menge"), ("liefertermin", "Liefertermin"), ("bemerkung", "Bemerkung"))

MUSTER = re.compile(r"^AU-(\d{4})-(\d{5,})$")
VORLAEUFIG = re.compile(r"^AU-V-")
NUMMERN_ORDNER = "AU-Nummern"
ORDNER = "Auftraege"
DATEI_FORMAT = 1


class AuftragFehler(ValueError):
    """Übernahme oder Änderung nicht möglich (Text für den Benutzer)."""


# ------------------------------------------------------------------ Einrichten
def einrichten(con):
    from . import db_verbindung
    da = set(db_verbindung.tabellen(con))
    for sql in TABELLEN_SQL:
        con.execute(sql)
    if (any(t not in da for t in TABELLEN[1:])
            and con.execute("SELECT 1 FROM auftrag_ereignisse LIMIT 1").fetchone()):
        _aufbauen(con)                  # Sicht fehlt (z. B. Tabelle verloren), Ereignisse sind da: neu rechnen


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _json(d):
    return json.dumps(d, ensure_ascii=False, sort_keys=True, default=str)


def _laden(text, vorgabe=None):
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
    """(Kürzel, Name) des angemeldeten Benutzers dieses Arbeitsplatzes (Einstellungen Benutzer)."""
    from . import teilen
    return teilen.kuerzel(db) or "", str(db.einstellung("benutzer_name") or "").strip()


# ------------------------------------------------------------------ Ereignisse
_FELDER = ("uid", "auftrag", "art", "ziel", "feld", "alt", "neu", "daten", "bemerkung", "wer", "name", "rechner", "am",
           "vorher")


def _pruefsumme(e):
    roh = _json({n: e.get(n) for n in _FELDER})
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()[:24]


def _letzte_pruef(con, rechner):
    r = con.execute("SELECT pruef FROM auftrag_ereignisse WHERE rechner=? ORDER BY id DESC LIMIT 1",
                    (rechner,)).fetchone()
    return r[0] if r else None


def _ereignis(db, auftrag, art, *, ziel=None, feld=None, alt=None, neu=None, daten=None, bemerkung="", am=None):
    """Ein Ereignis schreiben (innerhalb der laufenden Transaktion) und auf die Sicht anwenden."""
    wer, name = benutzer(db)
    rechner = socket.gethostname()
    e = dict(uid=uuid.uuid4().hex, auftrag=auftrag, art=art, ziel=ziel, feld=feld,
             alt=None if alt is None else str(alt), neu=None if neu is None else str(neu),
             daten=_json(daten) if daten is not None else None, bemerkung=str(bemerkung or "") or None, wer=wer,
             name=name or None, rechner=rechner, am=am or _jetzt(), vorher=_letzte_pruef(db.con, rechner))
    e["pruef"] = _pruefsumme(e)
    db.con.execute(f"INSERT INTO auftrag_ereignisse ({', '.join(_FELDER)}, pruef) VALUES "
                   f"({', '.join('?' * (len(_FELDER) + 1))})", [e[n] for n in _FELDER] + [e["pruef"]])
    _anwenden(db.con, e)
    return e


def ereignisse(db, auftrag=None):
    """Ereignisse (dict, Daten entpackt) nach Zeit; auftrag = uid oder None (alle)."""
    sql = "SELECT * FROM auftrag_ereignisse" + (" WHERE auftrag=?" if auftrag else "") + " ORDER BY am, id"
    out = []
    for r in db.con.execute(sql, (auftrag,) if auftrag else ()):
        e = dict(r)
        e["daten"] = _laden(e.get("daten"), None)
        out.append(e)
    return out


def pruefen(db, auftrag=None):
    """Einträge, deren Inhalt nicht mehr zur Prüfsumme passt (nachträglich in der Datei geändert): [uid]."""
    falsch = []
    for r in db.con.execute("SELECT * FROM auftrag_ereignisse" + (" WHERE auftrag=?" if auftrag else ""),
                            (auftrag,) if auftrag else ()):
        e = dict(r)
        if _pruefsumme(e) != e.get("pruef"):
            falsch.append(e["uid"])
    return falsch


# ------------------------------------------------------------------ Sicht aus den Ereignissen
def _anwenden(con, e):
    """Ein Ereignis auf die Tabellen auftraege, auftrag_angebote, auftrag_positionen anwenden."""
    a, art = e["auftrag"], e["art"]
    d = e["daten"] if isinstance(e.get("daten"), (dict, list)) else _laden(e.get("daten"), {})
    if art in (ANGELEGT, MIGRIERT):
        kopf = dict((d or {}).get("kopf") or {})
        con.execute("INSERT INTO auftrag_kopf (uid, nummer, status, daten, angelegt, geaendert) VALUES "
                    "(?, ?, ?, ?, ?, ?) ON CONFLICT (uid) DO NOTHING", (a, (d or {}).get("nummer"), (d or {}).get("status") or NEU, _json(kopf),
                                           e["am"], e["am"]))
        return
    r = con.execute("SELECT daten FROM auftrag_kopf WHERE uid=?", (a,)).fetchone()
    if r is None:
        return                  # Auftrag (noch) unbekannt: kommt beim nächsten Aufbauen in der richtigen Reihenfolge
    kopf = _laden(r[0], {})
    if art in (UEBERNOMMEN, AKTUALISIERT):
        ang = (d or {}).get("angebot") or {}
        erst = con.execute("SELECT am FROM auftrag_angebote WHERE auftrag=? AND angebot=?",
                           (a, ang.get("uid"))).fetchone()     # Zeitpunkt der ersten Übernahme bleibt
        con.execute("INSERT INTO auftrag_angebote (auftrag, angebot, nummer, kennung, stand, am) VALUES "
                    "(?, ?, ?, ?, ?, ?) ON CONFLICT (auftrag, angebot) DO UPDATE SET nummer=excluded.nummer, "
                    "kennung=excluded.kennung, stand=excluded.stand, am=excluded.am", (a, ang.get("uid"), ang.get("nummer"), ang.get("kennung"), _json(ang),
                                           erst[0] if erst else e["am"]))
        if art == AKTUALISIERT:
            alte = {p_uid: _laden(t, {}) for p_uid, t in con.execute(
                "SELECT uid, daten FROM auftrag_positionen WHERE auftrag=? AND angebot=?", (a, ang.get("uid")))}
            con.execute("DELETE FROM auftrag_positionen WHERE auftrag=? AND angebot=?", (a, ang.get("uid")))
        else:
            alte = {}
        n0 = con.execute("SELECT COALESCE(MAX(nr), 0) FROM auftrag_positionen WHERE auftrag=?", (a,)).fetchone()[0]
        for i, p in enumerate((d or {}).get("positionen") or ()):
            p = dict(p)
            vorher = alte.get(p.get("uid")) or {}
            for f, _ in POSITION_AENDERBAR:     # Ergänzungen im Auftrag bleiben bei einer Aktualisierung erhalten
                if f in (vorher.get("_hand") or {}):
                    p[f] = vorher[f]
                    p.setdefault("_hand", {})[f] = True
            for f in ("arbeitsgaenge", "_rm", "_qs"):  # Arbeitsvorbereitung, Rückmeldungen, QS gehören dem Auftrag
                if vorher.get(f):
                    p[f] = vorher[f]
            con.execute("INSERT INTO auftrag_positionen (uid, auftrag, angebot, nr, daten) VALUES "
                        "(?, ?, ?, ?, ?) ON CONFLICT (uid) DO UPDATE SET auftrag=excluded.auftrag, angebot=excluded.angebot, "
                        "nr=excluded.nr, daten=excluded.daten", (p.get("uid"), a, ang.get("uid"),
                                            vorher.get("_nr") or n0 + i + 1, _json(dict(p, _nr=vorher.get("_nr")
                                                                                          or n0 + i + 1))))
        for f in ("kunde", "kundennr", "ansprechpartner", "projekt", "bestellnr", "liefertermin",
                  "anforderungen"):       # leere Kopffelder aus dem (weiteren) Angebot ergänzen
            w = ((d or {}).get("kopf") or {}).get(f)
            if w and not kopf.get(f):
                kopf[f] = w
    elif art == POSITION_NEU:
        n = con.execute("SELECT COALESCE(MAX(nr), 0) FROM auftrag_positionen WHERE auftrag=?", (a,)).fetchone()[0]
        p = dict(d or {}, _nr=n + 1, _ergaenzt=True)
        con.execute("INSERT INTO auftrag_positionen (uid, auftrag, angebot, nr, daten) VALUES "
                    "(?, ?, NULL, ?, ?) ON CONFLICT (uid) DO UPDATE SET auftrag=excluded.auftrag, angebot=excluded.angebot, "
                        "nr=excluded.nr, daten=excluded.daten", (e.get("ziel"), a, n + 1, _json(p)))
    elif art == ANGEBOT_ENTFERNT:
        con.execute("DELETE FROM auftrag_positionen WHERE auftrag=? AND angebot=?", (a, e.get("ziel")))
        con.execute("DELETE FROM auftrag_angebote WHERE auftrag=? AND angebot=?", (a, e.get("ziel")))
    elif art == ARBEITSGAENGE:
        r2 = con.execute("SELECT daten FROM auftrag_positionen WHERE uid=?", (e.get("ziel"),)).fetchone()
        if r2 is not None:
            p = _laden(r2[0], {})
            p["arbeitsgaenge"] = list(d or [])
            con.execute("UPDATE auftrag_positionen SET daten=? WHERE uid=?", (_json(p), e["ziel"]))
    elif art == RUECKMELDUNG:
        r2 = con.execute("SELECT daten FROM auftrag_positionen WHERE uid=?", (e.get("ziel"),)).fetchone()
        if r2 is not None:
            p = _laden(r2[0], {})
            rm = [x for x in p.get("_rm") or () if x.get("uid") != e["uid"]]
            rm.append(dict(uid=e["uid"], ag=e.get("feld"), typ=e.get("neu"), daten=d or {}, wer=e.get("wer") or "",
                           name=e.get("name") or "", am=e["am"], bemerkung=e.get("bemerkung") or ""))
            p["_rm"] = rm
            con.execute("UPDATE auftrag_positionen SET daten=? WHERE uid=?", (_json(p), e["ziel"]))
    elif art == QS_PRUEFUNG:
        r2 = con.execute("SELECT daten FROM auftrag_positionen WHERE uid=?", (e.get("ziel"),)).fetchone()
        if r2 is not None:
            p = _laden(r2[0], {})
            qs = [x for x in p.get("_qs") or () if x.get("uid") != e["uid"]]
            qs.append(dict(d or {}, uid=e["uid"], wer=e.get("wer") or "", wer_name=e.get("name") or "", am=e["am"],
                           bemerkung=e.get("bemerkung") or ""))
            p["_qs"] = qs
            con.execute("UPDATE auftrag_positionen SET daten=? WHERE uid=?", (_json(p), e["ziel"]))
    elif art in (LIEFERUNG, DOKUMENT):
        schluessel = "_lieferungen" if art == LIEFERUNG else "_dokumente"
        liste_ = [x for x in kopf.get(schluessel) or () if x.get("uid") != e["uid"]]
        liste_.append(dict(d or {}, uid=e["uid"], wer=e.get("wer") or "", wer_name=e.get("name") or "", am=e["am"],
                           bemerkung=e.get("bemerkung") or ""))
        kopf[schluessel] = liste_
    elif art == PRUEFPUNKT:
        kopf.setdefault("_av", {})[e.get("feld")] = dict(wert=e.get("neu"), bemerkung=e.get("bemerkung") or "",
                                                        wer=e.get("wer") or "", am=e["am"])
    elif art == FREIGABE:
        kopf["_freigabe"] = dict(d or {}, wer=e.get("wer") or "", am=e["am"], grund=e.get("bemerkung") or "")
        con.execute("UPDATE auftrag_kopf SET status=? WHERE uid=?", (e.get("neu"), a))
    elif art == GEAENDERT and e.get("ziel"):
        r2 = con.execute("SELECT daten FROM auftrag_positionen WHERE uid=?", (e["ziel"],)).fetchone()
        if r2 is not None:
            p = _laden(r2[0], {})
            p[e["feld"]] = _wert(e["feld"], e.get("neu"))
            p.setdefault("_hand", {})[e["feld"]] = True
            con.execute("UPDATE auftrag_positionen SET daten=? WHERE uid=?", (_json(p), e["ziel"]))
    elif art == GEAENDERT:
        kopf[e["feld"]] = e.get("neu")
    elif art == STATUS:
        con.execute("UPDATE auftrag_kopf SET status=? WHERE uid=?", (e.get("neu"), a))
    elif art == NUMMER:
        con.execute("UPDATE auftrag_kopf SET nummer=? WHERE uid=?", (e.get("neu"), a))
    con.execute("UPDATE auftrag_kopf SET daten=?, geaendert=? WHERE uid=?", (_json(kopf), e["am"], a))


def _wert(feld, text):
    if feld == "menge":
        try:
            return float(str(text).replace(",", "."))
        except (TypeError, ValueError):
            return None
    return text


def aufbauen(db):
    """Sicht vollständig aus den Ereignissen neu rechnen (nach dem Lesen der Kollegen-Ereignisse)."""
    with db.con:
        _aufbauen(db.con)


def _aufbauen(con):
    for t in ("auftrag_kopf", "auftrag_angebote", "auftrag_positionen"):
        con.execute(f"DELETE FROM {t}")
    from . import db_verbindung
    spalten = db_verbindung.spalten(con, "auftrag_ereignisse")
    zeilen = [dict(zip(spalten, r)) for r in con.execute("SELECT * FROM auftrag_ereignisse ORDER BY am, id")]
    # erst Anlegen, dann der Rest (eine falsch gehende Uhr eines Kollegen bringt die Reihenfolge nicht durcheinander)
    for e in sorted(zeilen, key=lambda e: (e["art"] not in (ANGELEGT, MIGRIERT), e["am"], e["id"])):
        _anwenden(con, e)


# ------------------------------------------------------------------ Nummern
def zaehler(nr):
    m = MUSTER.match(str(nr or "").strip())
    return int(m.group(2)) if m else 0


def vorlaeufig(nr):
    return bool(VORLAEUFIG.match(str(nr or "")))


def _hoechster_lokal(db):
    werte = [r[0] for r in db.con.execute("SELECT nummer FROM auftrag_kopf")] + [db.einstellung("auftrag_letzte_nummer")]
    return max((zaehler(n) for n in werte), default=0)


def neue_nummer(db, datum=None):
    """Nächste Auftragsnummer AU-JJJJ-NNNNN (Zähler läuft über den Jahreswechsel weiter, wie die Angebotsnummern)."""
    from . import teilen
    jahr = str(datum or datetime.date.today().isoformat())[:4]
    n = _hoechster_lokal(db)
    if teilen.aktiv(db):
        w = teilen.weg(db)
        try:
            if w is None or not w.erreichbar():
                raise FileNotFoundError(str(w))
            n = max(n, w.nummer_hoechste(NUMMERN_ORDNER))
            while True:
                n += 1
                if w.nummer_belegen(NUMMERN_ORDNER, n, f"AU-{jahr}-{n:05d}\n{teilen.kuerzel(db)}\n"
                                                       f"{socket.gethostname()}\n{_jetzt()}\n"):
                    break
        except OSError:
            k = teilen.kuerzel(db)
            vor = [r[0] for r in db.con.execute("SELECT nummer FROM auftrag_kopf WHERE nummer LIKE ?",
                                                (f"AU-V-{k}-%",))]
            m = max((int(str(x).rsplit("-", 1)[-1]) for x in vor if str(x).rsplit("-", 1)[-1].isdigit()), default=0)
            return f"AU-V-{k}-{m + 1}"
    else:
        n += 1
    nr = f"AU-{jahr}-{n:05d}"
    db._einstellung_schreiben("auftrag_letzte_nummer", nr)
    return nr


def nummern_endgueltig(db):
    """Eigene Aufträge mit vorläufiger Nummer bekommen eine reservierte (Ordner wieder erreichbar). [(alt, neu)]"""
    from . import teilen
    k = teilen.kuerzel(db)
    out = []
    for uid, alt in db.con.execute("SELECT uid, nummer FROM auftrag_kopf WHERE nummer LIKE ? ORDER BY angelegt",
                                   (f"AU-V-{k}-%",)).fetchall():
        neu = neue_nummer(db)
        if vorlaeufig(neu):
            break
        with db.con:
            _ereignis(db, uid, NUMMER, feld="nummer", alt=alt, neu=neu)
        out.append((alt, neu))
    return out


# ------------------------------------------------------------------ Übernahme
def angebot_uid(db, angebot_id):
    r = db.con.execute("SELECT uid FROM angebote WHERE id=?", (angebot_id,)).fetchone()
    return r[0] if r else None


def angebot_id(db, uid):
    r = db.con.execute("SELECT id FROM angebote WHERE uid=?", (uid,)).fetchone()
    return r[0] if r else None


def von_angebot(db, angebot_id_):
    """uid des Auftrags, zu dem das Angebot gehört, oder None."""
    u = angebot_uid(db, angebot_id_)
    r = db.con.execute("SELECT auftrag FROM auftrag_angebote WHERE angebot=?", (u,)).fetchone() if u else None
    return r[0] if r else None


def _kalkulation(db, a, pos):
    """(zeilen, summen) der Kalkulation wie im Angebotsfenster oder (None, {}) ohne Schnittplan/bei Fehler."""
    if not a.get("ergebnis"):
        return None, {}
    try:
        from . import preis_simulator, rechnen
        k, tab, e = preis_simulator.grundlage(db, a, None)
        return rechnen.kalkulation(a, pos, a["ergebnis"], k, tab, e)
    except Exception:           # die Übernahme darf an der Kalkulation nie scheitern; Werte bleiben dann leer
        return None, {}


def _zeit_min(z, stueck):
    """Kalkulierte Zeiten einer Position in Minuten (Laser netto, Gewinde, Zusatzarbeiten, Schweißen)."""
    laser = _n(z.get("laser_netto")) * stueck / 60
    gewinde = _n(z.get("gewindezeit")) * stueck / 60
    zusatz = _n(z.get("zusatz_arbeit_s")) * stueck / 60
    schweissen = _n(z.get("bg_zeit_min")) * stueck
    ruesten = _n(z.get("zeit_ruest_abm")) + _n(z.get("zeit_ruest_maschine"))
    return dict(laser_min=round(laser, 2), gewinde_min=round(gewinde, 2), zusatz_min=round(zusatz, 2),
                schweissen_min=round(schweissen, 2), ruesten_min=round(ruesten / 60 * stueck, 2) if ruesten else 0.0,
                fertigung_min=round(laser + gewinde + zusatz + schweissen, 2))


def _dateien(ordner):
    """Zeichnungen und CAD-Dateien im Angebotsordner: [dict(name, groesse, art)]."""
    if ordner is None:
        return []
    out = []
    try:
        for p in sorted(ordner.rglob("*")):
            if p.is_file() and not p.name.startswith((".", "~$")):
                e = p.suffix.lower()
                art = ("CAD" if e in (".step", ".stp", ".dxf", ".dwg", ".igs", ".iges", ".sat", ".x_t", ".ipt",
                                      ".iam") else "Zeichnung" if e in (".pdf", ".tif", ".tiff", ".png", ".jpg")
                       else "Datei")
                out.append(dict(name=str(p.relative_to(ordner)), groesse=p.stat().st_size, art=art))
    except OSError:
        pass
    return out


def stand(db, angebot_id_, ordner=None, dateien=None):
    """Eingefrorener Stand eines Angebots für den Auftrag: dict(angebot=…, positionen=[…], kopf=…). dateien: Liste
    der Dateien, wenn kein Ordner da ist (Aktualisierung ohne Zugriff auf die Ablage)."""
    from . import fertigung
    from .angebot import aktiv
    a = db.angebot(angebot_id_)
    if not a:
        raise AuftragFehler("Das Angebot gibt es nicht mehr.")
    pos = db.positionen(angebot_id_)
    zeilen, summen = _kalkulation(db, a, pos)
    kunde = db.kunde(a.get("kundennr")) or {}
    dateien = _dateien(ordner) if ordner is not None or dateien is None else list(dateien)
    uids = {r[0]: r[1] for r in db.con.execute("SELECT id, uid FROM positionen WHERE angebot_id=?", (angebot_id_,))}
    positionen = []
    for i, p in enumerate(pos):
        if not aktiv(p):
            continue
        z = (zeilen[i] if zeilen and i < len(zeilen) else None) or {}
        stueck = _n(z.get("stueck")) or _n(p.get("stueck"))
        art_name = str(p.get("artikel") or "").lower()
        zeichnungen = [d["name"] for d in dateien if art_name and art_name in d["name"].lower()]
        positionen.append(dict(
            uid=uids.get(p["id"]) or f"{angebot_id_}-{p['id']}", angebot_pos=p.get("pos"), artikel=p.get("artikel"),
            bezeichnung=p.get("bezeichnung"), art=p.get("art") or "Rohrlaserteil", profil=p.get("profil_id"),
            werkstoff=p.get("werkstoff_id"), oberflaeche=p.get("oberflaeche"), laenge=p.get("laenge"),
            menge=stueck, menge_angebot=stueck, baugruppe=p.get("baugruppe"),
            zusatz=[str(x.get("name")) for x in _zusatzliste(p)], gewinde=p.get("gewinde"),
            material=round(_n(z.get("material_position")), 2),
            fertigung=round(_n(z.get("herstell_position")) - _n(z.get("material_position")), 2) if z else 0.0,
            selbstkosten=round(_n(z.get("selbst_position")), 2), preis_teil=round(_n(z.get("preis_teil")), 4),
            preis=round(_n(z.get("preis_position")), 2), zeichnungen=zeichnungen, **_zeit_min(z, stueck)))
    kopf = dict(kunde=a.get("kunde"), kundennr=a.get("kundennr"),
                ansprechpartner=kunde.get("ansprechpartner") or "", projekt=a.get("kundenreferenz") or "",
                bestellnr=a.get("auftragsnr") or "", liefertermin=a.get("liefertermin") or "",
                anforderungen=str(a.get("bemerkung") or "").strip(), maschine=a.get("maschine"))
    zeiten = [dict(schritt=x.get("schritt"), art=x.get("art"), minuten=round(_n(x.get("gesamt_min")), 2),
                   kosten=round(_n(x.get("kosten")), 2)) for x in summen.get("zeiten") or () if x.get("gesamt_min")]
    ang = dict(uid=angebot_uid(db, angebot_id_), id=angebot_id_, nummer=a.get("nummer"), datum=a.get("datum"),
               bearbeiter=a.get("bearbeiter"), kennung=fertigung.kennung(a, pos),
               netto=round(_n(summen.get("verkauf")) or _n(a.get("vk_netto")), 2),
               material=round(_n(summen.get("material")), 2), herstell=round(_n(summen.get("herstell")), 2),
               selbst=round(_n(summen.get("selbst")), 2), zeiten=zeiten, dateien=dateien,
               stangen=len((a.get("ergebnis") or {}).get("stangen") or ()), kopf=kopf)
    return dict(angebot=ang, positionen=positionen, kopf=kopf)


def _zusatzliste(p):
    try:
        from .rechnen import zusatz_liste
        return [x for x in zusatz_liste(p) if isinstance(x, dict)]
    except Exception:
        return []


def zusammenfassung(db, angebot_ids, ordner_von=None):
    """Was die Übernahme bringt, für das Fenster vor der Übernahme: dict(kopf, angebote, positionen, summen,
    hinweise). ordner_von(angebot_id) -> Pfad des Angebotsordners oder None."""
    staende, hinweise = [], []
    for i in angebot_ids:
        a = db.angebot(i) or {}
        if a.get("fremd"):
            raise AuftragFehler(f"Angebot {a.get('nummer')} gehört {a.get('fremd')}; übernehmen kann es nur der "
                                "Bearbeiter.")
        vorh = von_angebot(db, i)
        if vorh:
            raise AuftragFehler(f"Angebot {a.get('nummer')} ist schon im Auftrag {nummer(db, vorh)}.")
        s = stand(db, i, ordner_von(i) if ordner_von else None)
        staende.append(s)
        if not a.get("ergebnis"):
            hinweise.append(f"Angebot {a.get('nummer')}: noch nicht optimiert – Zeiten und Kosten fehlen.")
        if not s["angebot"]["dateien"]:
            hinweise.append(f"Angebot {a.get('nummer')}: keine Zeichnungen oder CAD-Dateien im Angebotsordner.")
    if not staende:
        raise AuftragFehler("Kein Angebot gewählt.")
    kunden = {s["kopf"].get("kundennr") or s["kopf"].get("kunde") for s in staende}
    if len(kunden) > 1:
        hinweise.append("Die Angebote haben verschiedene Kunden.")
    kopf = dict(staende[0]["kopf"])
    for s in staende[1:]:
        for f, w in s["kopf"].items():
            if w and not kopf.get(f):
                kopf[f] = w
    termine = sorted(t for t in (s["kopf"].get("liefertermin") for s in staende) if t)
    if termine:
        kopf["liefertermin"] = termine[0]
    pos = [p for s in staende for p in s["positionen"]]
    summen = {f: round(sum(_n(p.get(f)) for p in pos), 2) for f in
              ("preis", "material", "fertigung", "laser_min", "schweissen_min", "fertigung_min")}
    summen["netto"] = round(sum(_n(s["angebot"].get("netto")) for s in staende), 2)
    summen["dateien"] = sum(len(s["angebot"]["dateien"]) for s in staende)
    if not pos:
        hinweise.append("Keine aktiven Positionen.")
    return dict(kopf=kopf, angebote=staende, positionen=pos, summen=summen, hinweise=hinweise)


def uebernehmen(db, angebot_ids, kopf=None, bemerkung="", ordner_von=None, auftrag=None):
    """Angebote in einen neuen Auftrag übernehmen (auftrag = uid: zu einem bestehenden hinzufügen). kopf: Ergänzungen
    aus dem Fenster (Projekt, Ansprechpartner …). Ergebnis: uid des Auftrags. Ein Angebot, das schon in einem
    Auftrag ist, legt keinen zweiten an: es kommt dessen uid zurück (Doppelklick)."""
    if db.nur_lesen:
        raise AuftragFehler(f"Lesemodus – {db.nur_lesen}.")
    angebot_ids = [i for i in dict.fromkeys(angebot_ids)]
    vorh = [von_angebot(db, i) for i in angebot_ids]
    if any(vorh) and not auftrag:
        return next(v for v in vorh if v)
    for i, v in zip(angebot_ids, vorh):
        if v and v != auftrag:
            raise AuftragFehler(f"Angebot {(db.angebot(i) or {}).get('nummer')} ist schon im Auftrag {nummer(db, v)}.")
    rest = [i for i, v in zip(angebot_ids, vorh) if not v]
    if not rest:
        return auftrag                  # schon alle in diesem Auftrag (Doppelklick)
    z = zusammenfassung(db, rest, ordner_von)
    jetzt = _jetzt()
    with db.con:                        # alles oder nichts
        if auftrag is None:
            nr = neue_nummer(db, jetzt)
            k = {f: w for f, w in z["kopf"].items() if w not in (None, "")}
            k.update({f: w for f, w in (kopf or {}).items() if w not in (None, "")})
            k.setdefault("auftragsdatum", jetzt[:10])
            k.setdefault("verantwortlich", benutzer(db)[0])
            auftrag = uuid.uuid4().hex
            _ereignis(db, auftrag, ANGELEGT, daten=dict(nummer=nr, kopf=k, status=NEU), neu=nr,
                      bemerkung=bemerkung, am=jetzt)
        elif not db.con.execute("SELECT 1 FROM auftrag_kopf WHERE uid=?", (auftrag,)).fetchone():
            raise AuftragFehler("Den Auftrag gibt es nicht mehr.")
        for s in z["angebote"]:
            if db.con.execute("SELECT 1 FROM auftrag_angebote WHERE angebot=?", (s["angebot"]["uid"],)).fetchone():
                raise AuftragFehler(f"Angebot {s['angebot']['nummer']} ist schon in einem Auftrag.")
            _ereignis(db, auftrag, UEBERNOMMEN, ziel=s["angebot"]["uid"], neu=s["angebot"]["nummer"],
                      daten=dict(angebot=s["angebot"], positionen=s["positionen"], kopf=s["kopf"]), am=jetzt)
    return auftrag


# ------------------------------------------------------------------ Lesen
def auftrag(db, uid):
    """Auftrag mit Kopf, Angeboten (eingefrorener Stand) und Positionen oder None."""
    r = db.con.execute("SELECT * FROM auftrag_kopf WHERE uid=?", (uid,)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["kopf"] = _laden(d.pop("daten"), {})
    d["angebote"] = [dict(nummer=x[0], uid=x[1], kennung=x[2], stand=_laden(x[3], {}), am=x[4]) for x in db.con.execute(
        "SELECT nummer, angebot, kennung, stand, am FROM auftrag_angebote WHERE auftrag=? ORDER BY am, nummer",
        (uid,))]
    d["positionen"] = [dict(_laden(x[0], {}), uid=x[1], nr=x[2], angebot=x[3]) for x in db.con.execute(
        "SELECT daten, uid, nr, angebot FROM auftrag_positionen WHERE auftrag=? ORDER BY nr", (uid,))]
    d["wert"] = round(sum(_n(p.get("preis_teil")) * _n(p.get("menge")) if p.get("_hand", {}).get("menge")
                          else _n(p.get("preis")) for p in d["positionen"]), 2)
    return d


def nummer(db, uid):
    r = db.con.execute("SELECT nummer FROM auftrag_kopf WHERE uid=?", (uid,)).fetchone()
    return r[0] if r else ""


def verzoegert(a, heute=None):
    t = str((a.get("kopf") or {}).get("liefertermin") or "")[:10]
    return bool(t) and a.get("status") in OFFEN and t < (heute or datetime.date.today().isoformat())


TERMINE = ("Alle Termine", "Überfällig", "Diese Woche", "Nächste Woche", "Dieser Monat", "Später", "Ohne Termin")
FILTER = ("Offen", "Alle") + STATUS_LISTE + (VERZOEGERT,)


def fortschritt(a):
    """Fertigstellungsgrad 0–1 oder None (unbekannt). Paket 2: nur aus dem Status (fertig = 1); ab Paket 4 aus den
    zurückgemeldeten Mengen der Arbeitsgänge."""
    if a.get("status") in (FERTIG, AUSGELIEFERT, ABGESCHLOSSEN):
        return 1.0
    from .auftrag_produktion import fortschritt as aus_mengen
    return aus_mengen(a)


def termin_passt(termin, filter_, heute=None):
    """Liefertermin (ISO) im Terminfilter (TERMINE)?"""
    if filter_ in (None, "", TERMINE[0]):
        return True
    t = str(termin or "")[:10]
    if filter_ == "Ohne Termin":
        return not t
    if not t:
        return False
    h = datetime.date.fromisoformat(heute) if heute else datetime.date.today()
    try:
        d = datetime.date.fromisoformat(t)
    except ValueError:
        return False
    montag = h - datetime.timedelta(days=h.weekday())
    if filter_ == "Überfällig":
        return d < h
    if filter_ == "Diese Woche":
        return h <= d < montag + datetime.timedelta(days=7)
    if filter_ == "Nächste Woche":
        return montag + datetime.timedelta(days=7) <= d < montag + datetime.timedelta(days=14)
    if filter_ == "Dieser Monat":
        return h <= d and (d.year, d.month) == (h.year, h.month)
    if filter_ == "Später":
        return d >= montag + datetime.timedelta(days=14)
    return True


def _zeile(db, a, heute):
    k = a["kopf"]
    offen = (a["status"] or NEU) in OFFEN
    return dict(uid=a["uid"], nummer=a["nummer"], kunde=k.get("kunde") or "", kundennr=k.get("kundennr") or "",
                projekt=k.get("projekt") or "", auftragsdatum=k.get("auftragsdatum") or "",
                liefertermin=k.get("liefertermin") or "", positionen=len(a["positionen"]), wert=a["wert"],
                status=a["status"] or NEU, verzoegert=verzoegert(a, heute), verantwortlich=k.get("verantwortlich") or "",
                angebote=[x["nummer"] for x in a["angebote"]], fortschritt=fortschritt(a),
                bestellnr=k.get("bestellnr") or "", artikel=[str(p.get("artikel") or "") for p in a["positionen"]],
                geaendert_angebot=angebot_geaendert(db, a) if offen else [])


def status_passt(z, status):
    if status in (None, "", "Alle"):
        return True
    if status == "Offen":
        return z["status"] in OFFEN
    if status == VERZOEGERT:
        return z["verzoegert"]
    return z["status"] == status


def alle_zeilen(db, heute=None):
    """Alle Aufträge als Zeilen (neueste zuerst), ohne Filter."""
    return [_zeile(db, auftrag(db, uid), heute) for (uid,) in db.con.execute(
        "SELECT uid FROM auftrag_kopf ORDER BY angelegt DESC, nummer DESC").fetchall()]


def filtern(zeilen, suche="", status=None, termin=None, wer=None, heute=None):
    s = str(suche or "").strip().lower()
    out = []
    for z in zeilen:
        if s:
            text = " ".join([z["nummer"] or "", z["kunde"], z["kundennr"], z["projekt"], z["bestellnr"]]
                            + z["angebote"] + z["artikel"]).lower()
            if s not in text:
                continue
        if not status_passt(z, status) or not termin_passt(z["liefertermin"], termin, heute):
            continue
        if wer and z["verantwortlich"] != wer:
            continue
        out.append(z)
    return out


def liste(db, suche="", status=None, heute=None, termin=None, wer=None):
    """Aufträge für die Übersicht (neueste zuerst): [dict(uid, nummer, kunde, projekt, auftragsdatum, liefertermin,
    positionen, wert, status, verzoegert, verantwortlich, angebote, fortschritt, geaendert_angebot)]. suche:
    Auftragsnummer, Kunde, Projekt, Bestellnummer, Angebotsnummer oder Artikelnummer. status: ein Status, „Offen“,
    „Alle“ oder Verzögert; termin: TERMINE; wer: Kürzel des Zuständigen."""
    return filtern(alle_zeilen(db, heute), suche, status, termin, wer, heute)


def anzahl_je_filter(zeilen):
    """{Filter: Anzahl} für die Filterknöpfe."""
    return {f: sum(1 for z in zeilen if status_passt(z, f)) for f in FILTER}


def angebot_geaendert(db, a):
    """Nummern der Angebote des Auftrags, die sich seit der Übernahme geändert haben (eigene, noch vorhandene)."""
    from . import fertigung
    out = []
    for x in a["angebote"]:
        i = angebot_id(db, x["uid"])
        if i is None:
            continue
        ang = db.angebot(i) or {}
        if fertigung.kennung(ang, db.positionen(i)) != x["kennung"]:
            out.append(x["nummer"])
    return out


def historie(db, uid):
    """Historie als Zeilen: [dict(am, wer, ereignis, feld, alt, neu, bemerkung)] (älteste zuerst)."""
    out = []
    for e in ereignisse(db, uid):
        feld = KOPF_TITEL.get(e.get("feld")) or dict(POSITION_AENDERBAR).get(e.get("feld")) or e.get("feld") or ""
        if e["art"] == PRUEFPUNKT:
            from .auftrag_av import PUNKT_TITEL
            feld = PUNKT_TITEL.get(e.get("feld"), feld)
        if e["art"] in (GEAENDERT, ARBEITSGAENGE) and e.get("ziel"):
            p = db.con.execute("SELECT daten FROM auftrag_positionen WHERE uid=?", (e["ziel"],)).fetchone()
            pd = _laden(p[0], {}) if p else {}
            feld = f"Pos. {pd.get('_nr') or '?'} {pd.get('artikel') or ''}: {feld or 'Arbeitsgänge'}".strip()
        text = ART_TEXT.get(e["art"], e["art"])
        if e["art"] == RUECKMELDUNG:
            from .auftrag_produktion import TYP_TEXT
            p = db.con.execute("SELECT daten FROM auftrag_positionen WHERE uid=?", (e.get("ziel"),)).fetchone()
            pd = _laden(p[0], {}) if p else {}
            d = e.get("daten") or {}
            werte = [f"{k} {_n(d.get(f)):g}".replace(".", ",") for f, k in (("menge", "Menge"), ("ausschuss",
                     "Ausschuss"), ("minuten", "Minuten")) if d.get(f) not in (None, "")]
            out.append(dict(am=e["am"], wer=" ".join(x for x in (e.get("wer"), f"({e['name']})" if e.get("name")
                                                               else "") if x),
                            ereignis=TYP_TEXT.get(e.get("neu"), "Rückmeldung"),
                            feld=f"Pos. {pd.get('_nr') or '?'} {pd.get('artikel') or ''}: {e.get('alt') or ''}".strip(),
                            alt="", neu=" · ".join(werte + ([d["grund"]] if d.get("grund") else [])),
                            bemerkung=e.get("bemerkung") or ""))
            continue
        if e["art"] in (QS_PRUEFUNG, LIEFERUNG, DOKUMENT):
            from .auftrag_qs import historie_zeile
            out.append(dict(am=e["am"], wer=" ".join(x for x in (e.get("wer"), f"({e['name']})" if e.get("name")
                                                               else "") if x),
                            ereignis=text, bemerkung=e.get("bemerkung") or "", alt="",
                            **historie_zeile(db, e)))
            continue
        if e["art"] in (UEBERNOMMEN, AKTUALISIERT, ANGEBOT_ENTFERNT, POSITION_NEU):
            text += f" {e.get('neu') or ''}".rstrip()
        out.append(dict(am=e["am"], wer=" ".join(x for x in (e.get("wer"), f"({e['name']})" if e.get("name") else "")
                                                   if x), ereignis=text, feld=feld, alt=e.get("alt") or "",
                        neu=e.get("neu") if e["art"] not in (ANGELEGT, MIGRIERT, UEBERNOMMEN, AKTUALISIERT,
                                                             ANGEBOT_ENTFERNT, POSITION_NEU) else "",
                        bemerkung=e.get("bemerkung") or ""))
    return out


# ------------------------------------------------------------------ Ändern
def aendern(db, uid, feld, neu, bemerkung="", position=None):
    """Kopffeld (KOPF) bzw. Positionsfeld (POSITION_AENDERBAR, position = uid) ändern; Historie mit alt/neu. Kein
    Ereignis, wenn sich nichts ändert. Ergebnis: True, wenn geändert."""
    if db.nur_lesen:
        raise AuftragFehler(f"Lesemodus – {db.nur_lesen}.")
    a = auftrag(db, uid)
    if a is None:
        raise AuftragFehler("Den Auftrag gibt es nicht mehr.")
    if a["status"] == ABGESCHLOSSEN and not str(bemerkung or "").strip():
        raise AuftragFehler("Der Auftrag ist abgeschlossen; eine Änderung geht nur mit Grund (Bemerkung).")
    neu = "" if neu is None else str(neu).strip()
    if position:
        if feld not in dict(POSITION_AENDERBAR):
            raise AuftragFehler(f"Feld {feld} der Position lässt sich nicht ändern.")
        p = next((x for x in a["positionen"] if x["uid"] == position), None)
        if p is None:
            raise AuftragFehler("Die Position gibt es im Auftrag nicht.")
        if feld == "menge":
            w = _wert("menge", neu)
            if w is None or w < 0:
                raise AuftragFehler("Die Menge muss eine Zahl ab 0 sein.")
            neu = f"{w:g}"
        alt = "" if p.get(feld) is None else (f"{_n(p.get(feld)):g}" if feld == "menge" else str(p.get(feld)))
    else:
        if feld not in KOPF_TITEL:
            raise AuftragFehler(f"Feld {feld} lässt sich nicht ändern.")
        alt = str(a["kopf"].get(feld) or "")
    if alt == neu:
        return False
    with db.con:
        _ereignis(db, uid, GEAENDERT, ziel=position, feld=feld, alt=alt, neu=neu, bemerkung=bemerkung)
    return True


def status_setzen(db, uid, status, bemerkung=""):
    """Auftragsstatus von Hand (Paket 1: nur für die Übernahme bestehender Aufträge und Korrekturen; ab Paket 3/4
    rechnet das Programm ihn aus den Arbeitsgängen)."""
    if status not in STATUS_LISTE:
        raise AuftragFehler(f"Status „{status}“ gibt es nicht.")
    a = auftrag(db, uid)
    if a is None:
        raise AuftragFehler("Den Auftrag gibt es nicht mehr.")
    if a["status"] == status:
        return False
    if status == BEREIT and a["status"] in (NEU, AV, MATERIAL_FEHLT):
        from . import auftrag_av        # Produktionsbereit nur über die Prüfliste der Arbeitsvorbereitung
        auftrag_av.freigeben(db, uid, bemerkung)
        return True
    if STATUS_LISTE.index(status) < STATUS_LISTE.index(a["status"] or NEU) and not str(bemerkung or "").strip():
        raise AuftragFehler("Zurück im Ablauf geht nur mit Grund (Bemerkung).")
    with db.con:
        _ereignis(db, uid, STATUS, feld="status", alt=a["status"], neu=status, bemerkung=bemerkung)
    return True


def position_hinzufuegen(db, uid, artikel, bezeichnung="", menge=1, preis_teil=0.0, bemerkung="", grund=""):
    """Position nur im Auftrag ergänzen (z. B. Zukaufteil, Nacharbeit, Muster), ohne Angebot. Ergebnis: uid."""
    if db.nur_lesen:
        raise AuftragFehler(f"Lesemodus – {db.nur_lesen}.")
    a = auftrag(db, uid)
    if a is None:
        raise AuftragFehler("Den Auftrag gibt es nicht mehr.")
    if a["status"] == ABGESCHLOSSEN:
        raise AuftragFehler("Der Auftrag ist abgeschlossen.")
    if not str(artikel or bezeichnung or "").strip():
        raise AuftragFehler("Bitte Artikel oder Bezeichnung angeben.")
    m, pr = _wert("menge", menge), _wert("menge", preis_teil)
    if m is None or m <= 0 or pr is None or pr < 0:
        raise AuftragFehler("Menge muss größer 0 und Preis eine Zahl ab 0 sein.")
    p_uid = uuid.uuid4().hex
    p = dict(artikel=str(artikel or "").strip(), bezeichnung=str(bezeichnung or "").strip(), menge=m,
             menge_angebot=None, preis_teil=round(pr, 4), preis=round(m * pr, 2), bemerkung=str(bemerkung or ""),
             art="Ergänzt im Auftrag")
    with db.con:
        _ereignis(db, uid, POSITION_NEU, ziel=p_uid, neu=p["artikel"] or p["bezeichnung"], daten=p, bemerkung=grund)
    return p_uid


def angebot_entfernen(db, uid, angebot_uid_, grund):
    """Ein irrtümlich zugeordnetes Angebot wieder aus dem Auftrag lösen (nur vor der Produktion, nur mit Grund).
    Das Angebot kann danach in einen anderen Auftrag."""
    a = auftrag(db, uid)
    if a is None:
        raise AuftragFehler("Den Auftrag gibt es nicht mehr.")
    x = next((x for x in a["angebote"] if x["uid"] == angebot_uid_), None)
    if x is None:
        raise AuftragFehler("Das Angebot ist nicht in diesem Auftrag.")
    if not str(grund or "").strip():
        raise AuftragFehler("Bitte einen Grund angeben (steht in der Historie).")
    if a["status"] not in (NEU, AV, MATERIAL_FEHLT, BEREIT):
        raise AuftragFehler(f"Der Auftrag steht schon auf „{a['status']}“; lösen geht nur vor der Produktion.")
    with db.con:
        _ereignis(db, uid, ANGEBOT_ENTFERNT, ziel=angebot_uid_, neu=x["nummer"], bemerkung=grund)
    return True


def vergleich(db, uid, angebot_uid_, ordner=None):
    """Was „Änderung übernehmen“ bringen würde: [dict(was, artikel, alt, neu)] je geänderter Position."""
    a = auftrag(db, uid)
    i = angebot_id(db, angebot_uid_)
    if a is None or i is None:
        raise AuftragFehler("Auftrag oder Angebot gibt es nicht mehr.")
    neu = stand(db, i, ordner)
    alt = {p.get("uid"): p for p in a["positionen"] if p.get("angebot") == angebot_uid_}
    out = []
    neu_uids = set()
    for p in neu["positionen"]:
        neu_uids.add(p["uid"])
        q = alt.get(p["uid"])
        if q is None:
            out.append(dict(was="neu", artikel=p.get("artikel"), alt="", neu=f"{_n(p.get('menge')):g} Stk"))
            continue
        for f, t in (("menge_angebot", "Menge"), ("laenge", "Länge"), ("profil", "Profil"),
                     ("werkstoff", "Werkstoff"), ("preis", "Preis")):
            if str(q.get(f)) != str(p.get(f)):
                out.append(dict(was=t, artikel=p.get("artikel"), alt=q.get(f), neu=p.get(f)))
    for u, q in alt.items():
        if u not in neu_uids:
            out.append(dict(was="entfällt", artikel=q.get("artikel"), alt=f"{_n(q.get('menge')):g} Stk", neu=""))
    return out


def aktualisieren(db, uid, angebot_uid_, bemerkung="", ordner=None):
    """Den neuen Stand des Angebots in den Auftrag übernehmen (Knopf „Änderung übernehmen“). Von Hand im Auftrag
    geänderte Felder (Menge, Termin, Bemerkung einer Position) bleiben."""
    i = angebot_id(db, angebot_uid_)
    if i is None:
        raise AuftragFehler("Das Angebot gibt es hier nicht mehr.")
    alt = next((x["stand"] for x in (auftrag(db, uid) or {}).get("angebote") or () if x["uid"] == angebot_uid_), {})
    s = stand(db, i, ordner, alt.get("dateien"))
    with db.con:
        _ereignis(db, uid, AKTUALISIERT, ziel=angebot_uid_, neu=s["angebot"]["nummer"], bemerkung=bemerkung,
                  daten=dict(angebot=s["angebot"], positionen=s["positionen"], kopf=s["kopf"]))
    return True


# ------------------------------------------------------------------ Bestehende Aufträge übernehmen (F5a)
FERTIGUNG_ZU_STATUS = {"Freigegeben": AV, "Arbeitsvorbereitung": AV, "Material bereit": BEREIT,
                       "In Fertigung": PRODUKTION, "Fremdvergabe": PRODUKTION, "Qualitätsprüfung": QS,
                       "Fertig gemeldet": FERTIG}


def _status_bisher(db, angebot_id_):
    from . import fertigung, palettenschein
    try:
        versendet = palettenschein.ist_versendet(palettenschein.lesen((db.angebot(angebot_id_) or {})
                                                                      .get("palettenschein")))
    except Exception:
        versendet = False
    if versendet:
        return ABGESCHLOSSEN
    akt = fertigung.aktuell(db, angebot_id_)
    s = FERTIGUNG_ZU_STATUS.get((akt or {}).get("status"))
    if s == FERTIG:
        return ABGESCHLOSSEN
    return s or NEU


def migrieren(db, ordner_von=None):
    """Einmal je Arbeitsplatz: eigene beauftragte Angebote ohne Auftrag werden Aufträge (laufende mit ihrem Stand,
    versendete und fertig gemeldete als „Abgeschlossen“). Ergebnis: Anzahl."""
    if db.nur_lesen or db.einstellung("auftraege_migriert"):
        return 0
    n = 0
    ids = [r[0] for r in db.con.execute("SELECT id FROM angebote WHERE vorgang='Beauftragt' AND fremd IS NULL "
                                        "ORDER BY datum, id")]
    for i in ids:
        if von_angebot(db, i):
            continue
        try:
            s = stand(db, i, ordner_von(i) if ordner_von else None)
        except AuftragFehler:
            continue
        status = _status_bisher(db, i)
        a = db.angebot(i) or {}
        with db.con:
            uid = uuid.uuid4().hex
            k = {f: w for f, w in s["kopf"].items() if w not in (None, "")}
            k.setdefault("auftragsdatum", str(a.get("datum") or "")[:10])
            k.setdefault("verantwortlich", a.get("bearbeiter") or benutzer(db)[0])
            _ereignis(db, uid, MIGRIERT, daten=dict(nummer=neue_nummer(db, a.get("datum")), kopf=k, status=status),
                      bemerkung=f"aus Angebot {a.get('nummer')} (Vorgang Beauftragt, Stand {status})")
            _ereignis(db, uid, UEBERNOMMEN, ziel=s["angebot"]["uid"], neu=s["angebot"]["nummer"],
                      daten=dict(angebot=s["angebot"], positionen=s["positionen"], kopf=s["kopf"]))
        n += 1
    db.einstellung_setzen("auftraege_migriert", _jetzt())
    return n


# ------------------------------------------------------------------ Abgleich über den gemeinsamen Ordner
def _eigene(db):
    """Ereignisse dieses Arbeitsplatzes (geschrieben auf diesem Rechner, nicht von Kollegen eingelesen)."""
    return [dict(r) for r in db.con.execute("SELECT * FROM auftrag_ereignisse WHERE rechner=? ORDER BY id",
                                            (socket.gethostname(),))]


def ordner_schreiben(db):
    """Eigene Ereignisse als Auftraege/<Kürzel>.json in den gemeinsamen Ordner (atomar). Ergebnis: Anzahl."""
    from . import teilen
    if not teilen.aktiv(db):
        return 0
    w = teilen.weg(db)
    if w is None or not w.erreichbar():
        return 0
    nummern_endgueltig(db)
    eigene = [{n: e.get(n) for n in _FELDER + ("pruef",)} for e in _eigene(db)]
    roh = json.dumps(dict(format=DATEI_FORMAT, kuerzel=teilen.kuerzel(db), stand=_jetzt(), ereignisse=eigene),
                     ensure_ascii=False).encode("utf-8")
    if w.datei_lesen(ORDNER, f"{teilen.kuerzel(db)}.json") != roh:
        w.datei_schreiben(roh, ORDNER, f"{teilen.kuerzel(db)}.json")
    return len(eigene)


def ereignisse_einlesen(db, liste_):
    """Fremde Ereignisse übernehmen (bekannte über uid übergangen); danach Sicht neu. Ergebnis: Anzahl neu."""
    neu = 0
    with db.con:
        for e in liste_:
            if not isinstance(e, dict) or not e.get("uid") or not e.get("auftrag") or not e.get("art"):
                continue
            if db.con.execute("SELECT 1 FROM auftrag_ereignisse WHERE uid=?", (e["uid"],)).fetchone():
                continue
            db.con.execute(f"INSERT INTO auftrag_ereignisse ({', '.join(_FELDER)}, pruef) VALUES "
                           f"({', '.join('?' * (len(_FELDER) + 1))})", [e.get(n) for n in _FELDER] + [e.get("pruef")])
            neu += 1
    if neu:
        aufbauen(db)
    return neu


def ordner_lesen(db):
    """Ereignisse der Kollegen aus Auftraege/*.json lesen. Ergebnis: Anzahl neu übernommener Ereignisse."""
    from . import teilen
    if not teilen.aktiv(db):
        return 0
    o = teilen.weg(db)
    u = o.unterordner(ORDNER) if o is not None else None
    if u is None or not u.is_dir():
        return 0
    ich = teilen.kuerzel(db)
    alle = []
    for p in sorted(u.glob("*.json")):
        if p.stem == ich:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("format") == DATEI_FORMAT:
            alle += d.get("ereignisse") or []
    return ereignisse_einlesen(db, alle)
