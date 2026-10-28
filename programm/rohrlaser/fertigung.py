"""Freigabe und Fertigungsstatus beauftragter Angebote (Wettbewerbsvergleich P1-6 und P2).

Status je Auftrag aus der Einstellung 'fertigung_status' (eine Zeile je Status, Reihenfolge = Ablauf; Vorgabe
Freigegeben, Arbeitsvorbereitung, Material bereit, In Fertigung, Fremdvergabe, Qualitätsprüfung, Fertig gemeldet).
Der erste Status ist die Freigabe: sie hält den Angebotsstand fest (angebote.freigabe: Version, Zeitpunkt, Kürzel,
Prüfsumme über Kopf und Positionen, Positions-IDs). Werkstattpapiere nennen diesen Stand und warnen, wenn das Angebot
seitdem geändert wurde; dann ist eine neue Freigabe (Version + 1) nötig.

Regeln gegen widersprüchliche Zustände:
  - nur für Angebote mit Vorgang 'Beauftragt'
  - nur Status aus der Liste; derselbe Status zweimal hintereinander wird abgewiesen (außer einer neuen Freigabe)
  - vor der Freigabe kein anderer Status; vorwärts darf ein Status übersprungen werden (z. B. Fremdvergabe)
  - zurück in der Reihenfolge und erneute Freigabe (neue Version) nur mit Bemerkung (Grund)
Jeder Wechsel steht im Journal (Tabelle auftrag_status: Status, Zeitpunkt, Kürzel, Bemerkung, Freigabe-Version), das
nie geändert wird. Daraus rechnet durchlaufzeiten die Zeiten je Status (P2-Auswertung).
"""
import datetime
import hashlib
import json

TABELLEN = ("auftrag_status",)
TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS auftrag_status (id INTEGER PRIMARY KEY, angebot_id INTEGER NOT NULL, status TEXT "
    "NOT NULL, am TEXT, wer TEXT, bemerkung TEXT, version INTEGER)",
    "CREATE INDEX IF NOT EXISTS auftrag_status_angebot ON auftrag_status (angebot_id, id)",
)
VORGABE = ("Freigegeben", "Arbeitsvorbereitung", "Material bereit", "In Fertigung", "Fremdvergabe",
           "Qualitätsprüfung", "Fertig gemeldet")
# Kopffelder, die zum festgehaltenen Stand gehören (Fertigungsrelevantes; Texte und Preise ändern ihn nicht)
KOPF_FELDER = ("maschine", "stange", "laengenwahl", "liefertermin", "auftragsnr")
# Positionsfelder, die die Fertigung nicht betreffen (Prüfprotokolle, Vorschlagsstatus)
OHNE = ("step_merkmale", "arbeitsgaenge")


class FertigungFehler(ValueError):
    """Statuswechsel nicht möglich (Text für den Benutzer)."""


def einrichten(con):
    for sql in TABELLEN_SQL:
        con.execute(sql)
    if "freigabe" not in {r[1] for r in con.execute("PRAGMA table_info(angebote)")}:
        con.execute("ALTER TABLE angebote ADD COLUMN freigabe TEXT")


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def aktiv(db):
    return db.einstellung("fertigung_aktiv") != "nein"


def status_liste(db):
    """Status aus der Einstellung (leere Zeilen und doppelte weg); leer = Vorgabe."""
    out = []
    for z in str(db.einstellung("fertigung_status") or "").splitlines():
        z = z.strip()
        if z and z not in out:
            out.append(z)
    return out or list(VORGABE)


def kennung(kopf, positionen):
    """Prüfsumme des fertigungsrelevanten Angebotsstands (Positionen nach ID, ohne Prüfprotokolle)."""
    k = {n: (kopf or {}).get(n) for n in KOPF_FELDER}
    ps = sorted(({n: w for n, w in p.items() if n not in OHNE and not n.startswith("_")} for p in positionen),
                key=lambda p: p.get("id") or 0)
    roh = json.dumps(dict(kopf=k, positionen=ps), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()[:16]


def freigabe(db, angebot_id):
    """Festgehaltener Stand {version, am, wer, kennung, positionen=[ids]} oder None."""
    r = db.con.execute("SELECT freigabe FROM angebote WHERE id=?", (angebot_id,)).fetchone()
    try:
        d = json.loads(r[0]) if r and r[0] else None
    except (TypeError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def verlauf(db, angebot_id):
    return [dict(r) for r in db.con.execute("SELECT * FROM auftrag_status WHERE angebot_id=? ORDER BY id",
                                            (angebot_id,))]


def aktuell(db, angebot_id):
    """Letzter Status oder None."""
    r = db.con.execute("SELECT * FROM auftrag_status WHERE angebot_id=? ORDER BY id DESC LIMIT 1",
                       (angebot_id,)).fetchone()
    return dict(r) if r else None


def geaendert(db, angebot_id, kopf=None, positionen=None):
    """True, wenn es eine Freigabe gibt und das Angebot seitdem geändert wurde."""
    f = freigabe(db, angebot_id)
    if not f:
        return False
    kopf = kopf if kopf is not None else db.angebot(angebot_id)
    positionen = positionen if positionen is not None else db.positionen(angebot_id)
    return f.get("kennung") != kennung(kopf, positionen)


def stand_text(db, angebot_id, kopf=None, positionen=None):
    """(Text, Warnung) für Werkstattpapiere: festgehaltener Stand bzw. None ohne Freigabe."""
    f = freigabe(db, angebot_id)
    if not f:
        return None, None
    text = (f"Freigegebener Stand: Version {f['version']} vom {f['am'].replace('T', ' ')}"
            + (f" ({f['wer']})" if f.get("wer") else "") + f", Prüfsumme {f['kennung']}")
    warnung = ("ACHTUNG: Angebot nach der Freigabe geändert – Werkstattpapiere entsprechen nicht dem freigegebenen "
               "Stand. Bitte neu freigeben." if geaendert(db, angebot_id, kopf, positionen) else None)
    return text, warnung


def setzen(db, angebot_id, status, bemerkung="", wer=None):
    """Status wechseln (Regeln siehe Moduldoku). Ergebnis: neue Journalzeile. FertigungFehler sonst."""
    from .datenbank import Lesemodus
    if db.nur_lesen:
        raise Lesemodus(f"Lesemodus – {db.nur_lesen}. Ändern ist erst mit gültiger Lizenz möglich "
                        "(Hilfe → Lizenz …).")
    kopf = db.angebot(angebot_id)
    if not kopf:
        raise FertigungFehler("Angebot nicht gefunden.")
    if kopf.get("vorgang") != "Beauftragt":
        raise FertigungFehler("Fertigungsstatus nur für beauftragte Angebote (Vorgang „Beauftragt“).")
    liste = status_liste(db)
    if status not in liste:
        raise FertigungFehler(f"Status „{status}“ steht nicht in der Liste (Einstellungen → Fertigungsstatus).")
    bisher = aktuell(db, angebot_id)
    if bisher and bisher["status"] == status and status != liste[0]:
        raise FertigungFehler(f"Der Auftrag steht schon auf „{status}“.")
    if not bisher and status != liste[0]:
        raise FertigungFehler(f"Zuerst „{liste[0]}“ (Freigabe), dann die weiteren Status.")
    rueck = bisher and bisher["status"] in liste and liste.index(status) <= liste.index(bisher["status"])
    bemerkung = (bemerkung or "").strip()
    if rueck and not bemerkung:
        raise FertigungFehler(f"Zurück von „{bisher['status']}“ auf „{status}“ nur mit Grund (Bemerkung).")
    wer = wer if wer is not None else (db.einstellung("benutzer_kuerzel") or "")
    jetzt = _jetzt()
    with db.con:
        f = freigabe(db, angebot_id)
        version = (f or {}).get("version") or 0
        if status == liste[0]:
            positionen = db.positionen(angebot_id)
            version += 1
            db.con.execute("UPDATE angebote SET freigabe=? WHERE id=?", (json.dumps(dict(
                version=version, am=jetzt, wer=wer, kennung=kennung(kopf, positionen),
                positionen=[p["id"] for p in positionen]), ensure_ascii=False), angebot_id))
        i = db.con.execute("INSERT INTO auftrag_status (angebot_id, status, am, wer, bemerkung, version) VALUES "
                           "(?, ?, ?, ?, ?, ?)", (angebot_id, status, jetzt, wer, bemerkung, version)).lastrowid
    return dict(db.con.execute("SELECT * FROM auftrag_status WHERE id=?", (i,)).fetchone())


def angebot_geloescht(db, angebot_id):
    db.con.execute("DELETE FROM auftrag_status WHERE angebot_id=?", (angebot_id,))


def uebersicht(db):
    """Beauftragte Angebote für den Reiter Fertigung: [dict(id, nummer, kunde, liefertermin, status, am, version,
    geaendert)]."""
    out = []
    for a in db.angebote():
        if a.get("vorgang") != "Beauftragt":
            continue
        z = aktuell(db, a["id"])
        f = freigabe(db, a["id"])
        out.append(dict(id=a["id"], nummer=a.get("nummer"), kunde=a.get("kunde"), liefertermin=a.get("liefertermin"),
                        auftragsnr=a.get("auftragsnr"), status=(z or {}).get("status") or "nicht freigegeben",
                        am=(z or {}).get("am"), version=(f or {}).get("version"),
                        geaendert=geaendert(db, a["id"]) if f else False))
    return out


# ------------------------------------------------------------------ P2: Auswertungen und Export
def _zeit(s):
    return datetime.datetime.fromisoformat(s)


def durchlaufzeiten(db, angebot_id=None):
    """Zeiten je Status aus dem Journal: dict(auftraege=[{angebot_id, nummer, gesamt_h (Freigabe bis Fertig
    gemeldet bzw. None), je_status={Status: h}}], mittel={Status: h}, fertig=Anzahl). Zeit eines Status = bis zum
    nächsten Wechsel; der letzte offene Status zählt nicht (läuft noch)."""
    ids = [angebot_id] if angebot_id else [r[0] for r in db.con.execute(
        "SELECT DISTINCT angebot_id FROM auftrag_status ORDER BY angebot_id")]
    liste = status_liste(db)
    auftraege, summen = [], {}
    for aid in ids:
        v = verlauf(db, aid)
        if not v:
            continue
        je = {}
        for a, b in zip(v, v[1:], strict=False):
            je[a["status"]] = je.get(a["status"], 0.0) + (_zeit(b["am"]) - _zeit(a["am"])).total_seconds() / 3600
        fertig = v[-1]["status"] == liste[-1]
        start = next((x["am"] for x in v if x["status"] == liste[0]), v[0]["am"])
        gesamt = (_zeit(v[-1]["am"]) - _zeit(start)).total_seconds() / 3600 if fertig else None
        a = db.angebot(aid) or {}
        auftraege.append(dict(angebot_id=aid, nummer=a.get("nummer"), gesamt_h=gesamt, je_status=je, fertig=fertig))
        for s, h in je.items():
            summen.setdefault(s, []).append(h)
    return dict(auftraege=auftraege, mittel={s: sum(h) / len(h) for s, h in summen.items()},
                fertig=sum(1 for a in auftraege if a["fertig"]))


def export(db, angebot_id, ergebnis=None):
    """Fertigungsauftrag als dict für externe Systeme (JSON/CSV, ohne Preise): Kopf, Freigabe, Status, Positionen
    mit stabiler ID, Stangen des Schnittplans und Material aus dem Lager mit Charge."""
    from . import lager
    kopf = db.angebot(angebot_id) or {}
    positionen = db.positionen(angebot_id)
    la = lager.auftrag(db, angebot_id)
    return dict(
        format="rohrlaser-fertigungsauftrag", version=1, erstellt=_jetzt(),
        auftrag=dict(nummer=kopf.get("nummer"), kunde=kopf.get("kunde"), kundennr=kopf.get("kundennr"),
                     auftragsnr=kopf.get("auftragsnr"), liefertermin=kopf.get("liefertermin"),
                     maschine=kopf.get("maschine")),
        freigabe=freigabe(db, angebot_id), geaendert_seit_freigabe=geaendert(db, angebot_id, kopf, positionen),
        status=verlauf(db, angebot_id),
        positionen=[dict(id=p["id"], pos=p.get("pos"), artikel=p.get("artikel"), bezeichnung=p.get("bezeichnung"),
                         art=p.get("art") or "Rohrlaserteil", profil=p.get("profil_id"), werkstoff=p.get("werkstoff_id"),
                         oberflaeche=p.get("oberflaeche"), laenge=p.get("laenge"), stueck=p.get("stueck"),
                         gewinde=p.get("gewinde"), zusatz=[e.get("name") for e in _zusatz(p)]) for p in positionen],
        stangen=[dict(nr=s["nr"], profil=s["profil"], werkstoff=s["werkstoff"], oberflaeche=s.get("oberflaeche"),
                      stange=s["stange"], teile=[dict(pos=t.get("pos"), artikel=t.get("artikel"), laenge=t.get("laenge"),
                                                      von=t.get("von"), bis=t.get("bis")) for t in s["teile"]])
                 for s in (ergebnis or {}).get("stangen") or ()],
        lager=dict(status=la["status"], stangen=[dict(nr=b["nr"], quelle=b["quelle"], kennung=b.get("kennung"),
                                                     charge=b.get("charge"), lagerort=b.get("lagerort"))
                                                for b in la["plan"].get("stangen") or ()]) if la else None)


def _zusatz(p):
    from .rechnen import zusatz_liste
    return zusatz_liste(p)


def export_csv(daten):
    """Positionen des Exports als CSV-Text (Semikolon, für Tabellenprogramme)."""
    import csv
    import io
    f = io.StringIO()
    w = csv.writer(f, delimiter=";")
    spalten = ("id", "pos", "artikel", "bezeichnung", "art", "profil", "werkstoff", "oberflaeche", "laenge", "stueck",
               "gewinde", "zusatz")
    w.writerow(("auftrag",) + spalten)
    for p in daten["positionen"]:
        w.writerow((daten["auftrag"]["nummer"],) + tuple(
            "; ".join(p[n]) if n == "zusatz" else ("" if p[n] is None else p[n]) for n in spalten))
    return f.getvalue()
